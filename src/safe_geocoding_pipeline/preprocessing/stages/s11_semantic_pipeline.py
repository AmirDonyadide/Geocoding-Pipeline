"""Bounded exact global deduplication and complete independent reopening."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import duckdb
import pyarrow

from . import s09_reference_io as base
from . import s11_semantic_assets as assets
from . import s11_semantic_checkpoints as checkpoints
from . import s11_semantic_contract as c
from . import s11_semantic_input as source
from . import s11_semantic_io as io
from . import s11_semantic_publication as publication
from . import s11_semantic_summary as summary


def checkpoint_binding(
    inputs: source.Inputs,
    asset_ids: Mapping[str, str],
    executable: str,
    unit_rows: int,
    partition_bytes: int,
) -> dict[str, Any]:
    c.require(
        re.fullmatch("[0-9a-f]{40}", executable) is not None
        and type(unit_rows) is int
        and 0 < unit_rows <= 65536
        and type(partition_bytes) is int
        and 1 <= partition_bytes <= 2,
        "S11_CHECKPOINT_INVALID",
    )
    return {
        "execution_git_sha": executable,
        "input_binding_sha256": inputs.identifier.hex(),
        **asset_ids,
        "design_sha": c.DESIGN_SHA,
        "encoding_version": c.ENCODING,
        "runtime": runtime(),
        "input_unit_rows": unit_rows,
        "partition_bytes": partition_bytes,
        "input_order": "HYPOTHESIS_ID_UNSIGNED_ASCENDING",
    }


def input_units(
    inputs: source.Inputs,
    connection: duckdb.DuckDBPyConnection,
    local: Path,
    durable: Path,
    binding: Mapping[str, Any],
    resume: Path | None,
    progress: Callable[[int], None] | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    unit_rows = binding["input_unit_rows"]
    records: list[dict[str, Any]] = []
    spool_paths: list[Path] = []
    writer: Any = None
    ordinal = 0
    count = 0
    first: bytes = b""
    last: bytes = b""
    key_digest = hashlib.sha256()
    old: Path | None = None
    adopted = 0
    visited = 0

    def finish() -> None:
        nonlocal writer, adopted
        name = f"input-{ordinal:08d}"
        expected = {
            "binding": binding,
            "kind": "input",
            "coverage": {
                "ordinal": ordinal,
                "first_hypothesis_id": first.hex(),
                "last_hypothesis_id": last.hex(),
                "hypotheses": count,
                "input_keys_sha256": key_digest.hexdigest(),
            },
        }
        target = durable / name
        if old is not None:
            record = checkpoints.adopt_unit(old, target, expected)
            adopted += 1
        else:
            writer.close()
            record = checkpoints.save_unit(target, local, writer.paths, expected)
        c.require(record["rows"] == count, "S11_CHECKPOINT_INVALID")
        spool_paths.extend(checkpoints.paths(target, record))
        records.append(
            {
                "unit": name,
                "descriptor_sha256": c.sha256_file(target / checkpoints.DESCRIPTOR),
                "coverage": expected["coverage"],
            }
        )
        writer = None
        checkpoints.fault("input_unit_complete")

    for row in io.rows(
        connection,
        "SELECT hypothesis_id,intent,selection_status FROM h ORDER BY hypothesis_id",
    ):
        if count == unit_rows:
            finish()
            ordinal += 1
            count = 0
        if count == 0:
            first = row["hypothesis_id"]
            key_digest = hashlib.sha256(b"SAFE:stage11-input-keys:v1\0")
            old = resume / f"input-{ordinal:08d}" if resume is not None else None
            if old is not None and not os.path.lexists(old / checkpoints.SEAL):
                # Preserve incomplete old units; rebuild exclusively in this new attempt.
                old = None
            if old is None:
                writer = io.RelationWriter(
                    local / f"input-{ordinal:08d}",
                    io.SPOOL_SCHEMA,
                    batch_bytes=4 * 1024 * 1024,
                    batch_rows=1024,
                )
        last = row["hypothesis_id"]
        key_digest.update(c.framed((last,)))
        if old is None:
            raw = c.core_bytes(c.project(row["intent"], row["selection_status"]))
            writer.append(
                {
                    "hypothesis_id": last,
                    "query_semantic_id": c.semantic_id(raw),
                    "canonical_bytes": raw,
                }
            )
        count += 1
        visited += 1
        if progress is not None:
            progress(visited)
    if count:
        finish()
    c.require(
        sum(r["coverage"]["hypotheses"] for r in records)
        == inputs.population["hypotheses"],
        "S11_CHECKPOINT_INVALID",
    )
    for left, right in zip(records, records[1:]):
        c.require(
            left["coverage"]["last_hypothesis_id"]
            < right["coverage"]["first_hypothesis_id"],
            "S11_CHECKPOINT_INVALID",
        )
    coverage = {
        "coverage_version": "stage11_input_coverage_v1",
        "binding": binding,
        "units": records,
        "hypotheses": inputs.population["hypotheses"],
    }
    io.write_json(durable / "input_coverage.json", coverage)
    return spool_paths, {
        "input_units": len(records),
        "adopted_input_units": adopted,
        "input_coverage_sha256": c.sha256_file(durable / "input_coverage.json"),
    }


def reduce_units(
    connection: duckdb.DuckDBPyConnection,
    local: Path,
    durable: Path,
    binding: Mapping[str, Any],
    contributors: str,
    resume: Path | None,
) -> tuple[list[Path], dict[str, Any]]:
    paths: list[Path] = []
    units: list[dict[str, Any]] = []
    previous_id = previous_bytes = prefix = None
    writer: Any = None
    first = last = None
    memberships = 0
    adopted = 0

    def finish() -> None:
        nonlocal adopted
        assert prefix is not None
        writer.close()
        name = "reduction-" + prefix.hex()
        expected = {
            "binding": binding,
            "kind": "reduction",
            "coverage": {
                "prefix": prefix.hex(),
                "contributors_sha256": contributors,
                "first_semantic_id": first.hex(),
                "last_semantic_id": last.hex(),
                "hypotheses": memberships,
            },
        }
        old = resume / name if resume is not None else None
        target = durable / name
        if old is not None and os.path.lexists(old / checkpoints.SEAL):
            record = checkpoints.adopt_unit(old, target, expected)
            c.require(
                checkpoints.payload_digest("reduction", writer.paths)
                == (record["rows"], record["payload_sha256"]),
                "S11_CHECKPOINT_INVALID",
            )
            adopted += 1
        else:
            record = checkpoints.save_unit(target, local, writer.paths, expected)
        paths.extend(checkpoints.paths(target, record))
        units.append(
            {
                "unit": name,
                "descriptor_sha256": c.sha256_file(target / checkpoints.DESCRIPTOR),
                "requests": record["rows"],
                "coverage": expected["coverage"],
            }
        )
        checkpoints.fault("reduction_unit_complete")

    # Sorting full IDs then streaming equality retains constant group memory,
    # including the worst case where every input hypothesis shares one request.
    for row in io.rows(
        connection, "SELECT * FROM spool ORDER BY query_semantic_id,hypothesis_id"
    ):
        request, raw = row["query_semantic_id"], row["canonical_bytes"]
        if request == previous_id:
            c.require(raw == previous_bytes, "S11_ID_COLLISION")
        else:
            current = request[: binding["partition_bytes"]]
            if current != prefix:
                if prefix is not None:
                    finish()
                prefix, first = current, request
                memberships = 0
                writer = io.RelationWriter(
                    local / ("reduction-" + prefix.hex()),
                    c.schema("semantic_request"),
                    batch_bytes=4 * 1024 * 1024,
                    batch_rows=1024,
                )
            writer.append({"query_semantic_id": request, "core": c.decode_core(raw)})
            previous_id, previous_bytes = request, raw
        last = request
        memberships += 1
    if prefix is not None:
        finish()
    c.require(
        sum(u["coverage"]["hypotheses"] for u in units)
        == summary.scalar(connection, "SELECT count(*) FROM spool"),
        "S11_CHECKPOINT_INVALID",
    )
    certificate = {
        "coverage_version": "stage11_reduction_coverage_v1",
        "binding": binding,
        "contributors_sha256": contributors,
        "units": units,
    }
    io.write_json(durable / "reduction_coverage.json", certificate)
    return paths, {
        "reduction_units": len(units),
        "adopted_reduction_units": adopted,
        "reduction_coverage_sha256": c.sha256_file(durable / "reduction_coverage.json"),
    }


def check_map(connection: duckdb.DuckDBPyConnection, inputs: source.Inputs) -> None:
    n = inputs.population["hypotheses"]
    c.require(
        connection.execute(
            "SELECT count(*),count(DISTINCT hypothesis_id) FROM m"
        ).fetchone()
        == (n, n),
        "S11_MAP_TOTALITY_INVALID",
    )
    for sql in (
        "SELECT hypothesis_id FROM h EXCEPT SELECT hypothesis_id FROM m",
        "SELECT hypothesis_id FROM m EXCEPT SELECT hypothesis_id FROM h",
        "SELECT query_semantic_id FROM m EXCEPT SELECT query_semantic_id FROM s",
        "SELECT query_semantic_id FROM s EXCEPT SELECT query_semantic_id FROM m",
        "SELECT query_semantic_id FROM s GROUP BY query_semantic_id HAVING count(*)<>1",
    ):
        c.require(
            summary.scalar(connection, "SELECT count(*) FROM (" + sql + ")") == 0,
            "S11_MAP_TOTALITY_INVALID",
        )
    count = 0
    for row in io.rows(
        connection,
        """SELECT h.intent,h.selection_status,m.query_semantic_id,s.core
        FROM h JOIN m USING(hypothesis_id) JOIN s USING(query_semantic_id)""",
    ):
        expected = c.core_bytes(c.project(row["intent"], row["selection_status"]))
        actual = c.core_bytes(row["core"])
        c.require(
            expected == actual and c.semantic_id(expected) == row["query_semantic_id"],
            "S11_MAP_PROJECTION_MISMATCH",
        )
        count += 1
    c.require(count == n, "S11_MAP_TOTALITY_INVALID")


def runtime() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "pyarrow": pyarrow.__version__,
        "duckdb": duckdb.__version__,
    }


def build(
    root: Path,
    inputs: source.Inputs,
    connection: duckdb.DuckDBPyConnection,
    local: Path,
    durable: Path,
    asset_ids: dict[str, str],
    executable: str,
    *,
    unit_rows: int = 8192,
    partition_bytes: int = 1,
    resume: Path | None = None,
    progress: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    binding = checkpoint_binding(
        inputs, asset_ids, executable, unit_rows, partition_bytes
    )
    spool, input_metrics = input_units(
        inputs, connection, local, durable, binding, resume, progress
    )
    c.require(bool(spool), "S11_INPUT_BINDING_INVALID")
    connection.execute(f"CREATE VIEW spool AS SELECT * FROM {io.parquet_sql(spool)}")
    semantic_paths, reduce_metrics = reduce_units(
        connection,
        local,
        durable,
        binding,
        input_metrics["input_coverage_sha256"],
        resume,
    )
    (root / "semantic_request").mkdir(mode=0o700)
    output_paths = []
    for i, path in enumerate(semantic_paths):
        destination = root / "semantic_request" / f"part-{i:08d}.parquet"
        io.copy_exclusive(path, destination)
        output_paths.append(destination)
    writer = io.RelationWriter(
        root / "hypothesis_request_map",
        c.schema("hypothesis_request_map"),
        batch_bytes=4 * 1024 * 1024,
    )
    for row in io.rows(
        connection,
        "SELECT hypothesis_id,query_semantic_id FROM spool ORDER BY hypothesis_id",
    ):
        writer.append(row)
    writer.close()
    count = sum(1 for _ in io.parquet_rows(output_paths))
    relations = [
        io.record("semantic_request", root, output_paths, count),
        io.record("hypothesis_request_map", root, writer.paths, writer.rows),
    ]
    connection.execute(f"CREATE VIEW s AS SELECT * FROM {io.parquet_sql(output_paths)}")
    connection.execute(f"CREATE VIEW m AS SELECT * FROM {io.parquet_sql(writer.paths)}")
    check_map(connection, inputs)
    report = summary.compute(connection, inputs.population)
    io.write_json(root / io.SUMMARY_NAME, report)
    metadata = io.file_record(root, root / io.SUMMARY_NAME)
    logical = assets.dataset(
        inputs.identifier, asset_ids, relations, metadata["sha256"]
    )
    return {
        "manifest_version": c.MANIFEST,
        "kind": publication.DEVELOPMENT,
        "split": "DEVELOPMENT",
        "input_binding": inputs.binding,
        "input_binding_sha256": inputs.identifier.hex(),
        **asset_ids,
        "encoding_version": c.ENCODING,
        "design_sha": c.DESIGN_SHA,
        "design_documents_sha256": asset_ids["contract_sha256"],
        "relations": relations,
        "metadata_inventory": [metadata],
        "logical_sha256": logical.hex(),
        "runtime": runtime(),
        "operational_provenance": {
            "execution_git_sha": executable,
            "checkpoints": {**input_metrics, **reduce_metrics},
            "checkpoint_binding": binding,
        },
    }


def reopen(
    root: Path,
    digest: str,
    state: base.PublicationState,
    inputs: source.Inputs,
    asset_ids: dict[str, str],
    executable: str,
) -> dict[str, Any]:
    manifest = publication.validate_terminal(root, digest, state)
    c.require(
        set(manifest)
        == {
            "manifest_version",
            "kind",
            "split",
            "input_binding",
            "input_binding_sha256",
            "contract_sha256",
            "profile_sha256",
            "schema_bundle_sha256",
            "encoding_version",
            "design_sha",
            "design_documents_sha256",
            "relations",
            "metadata_inventory",
            "logical_sha256",
            "runtime",
            "operational_provenance",
        },
        "S11_INPUT_BINDING_INVALID",
    )
    c.require(
        manifest["manifest_version"] == c.MANIFEST
        and manifest["encoding_version"] == c.ENCODING
        and manifest["split"] == "DEVELOPMENT"
        and manifest["design_sha"] == c.DESIGN_SHA
        and manifest["runtime"] == runtime()
        and manifest["design_documents_sha256"] == asset_ids["contract_sha256"]
        and manifest["input_binding"] == inputs.binding
        and manifest["input_binding_sha256"] == inputs.identifier.hex()
        and manifest["operational_provenance"]["execution_git_sha"] == executable
        and all(manifest[k] == v for k, v in asset_ids.items()),
        "S11_INPUT_BINDING_INVALID",
    )
    # Independent, memory-capped reopen with disk spilling disabled. No reads of
    # generation /local, databases, checkpoints or caches; all authoritative rows
    # come from manifest-pinned PanFS. An insufficient envelope fails closed.
    with duckdb.connect(":memory:") as connection:
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET temp_directory=''")
        connection.execute("SET threads=2")
        connection.execute("SET autoinstall_known_extensions=false")
        connection.execute("SET autoload_known_extensions=false")
        connection.execute("SET disabled_filesystems='HTTPFileSystem'")
        inputs.register(connection)
        source.validate(inputs, connection)
        c.require(
            [r["name"] for r in manifest["relations"]] == list(c.RELATIONS),
            "S11_INPUT_BINDING_INVALID",
        )
        for record, view in zip(manifest["relations"], ("s", "m"), strict=True):
            paths = io.verify_relation(root, record, connection)
            connection.execute(
                f"CREATE VIEW {view} AS SELECT * FROM {io.parquet_sql(paths)}"
            )
        check_map(connection, inputs)
        report = summary.compute(connection, inputs.population)
        c.require(
            manifest["metadata_inventory"]
            == [io.file_record(root, root / io.SUMMARY_NAME)],
            "S11_INPUT_BINDING_INVALID",
        )
        c.require(
            publication.read_private(root / io.SUMMARY_NAME) == c.canonical(report),
            "S11_INPUT_BINDING_INVALID",
        )
        c.require(
            assets.dataset(
                inputs.identifier,
                asset_ids,
                manifest["relations"],
                manifest["metadata_inventory"][0]["sha256"],
            ).hex()
            == manifest["logical_sha256"],
            "S11_INPUT_BINDING_INVALID",
        )
    return manifest


def run(
    inputs: source.Inputs,
    output: Path,
    local: Path,
    durable: Path,
    asset_ids: dict[str, str],
    executable: str,
    *,
    unit_rows: int = 8192,
    partition_bytes: int = 1,
    threads: int = 2,
    resume: Path | None = None,
    observer: Callable[[str, BaseException | None], None] | None = None,
    progress: Callable[[int], None] | None = None,
) -> base.PublicationResult:
    io.private(local, directory=True)
    io.private(durable, directory=True)
    connection = io.connect(local, threads=threads)
    result = None
    try:
        inputs.register(connection)
        source.validate(inputs, connection)
        result = publication.publish(
            output,
            lambda root: build(
                root,
                inputs,
                connection,
                local,
                durable,
                asset_ids,
                executable,
                unit_rows=unit_rows,
                partition_bytes=partition_bytes,
                resume=resume,
                progress=progress,
            ),
            lambda root, digest, state: reopen(
                root, digest, state, inputs, asset_ids, executable
            ),
            observer=observer,
        )
        return result
    finally:
        primary = sys.exception()
        try:
            connection.close()
        except BaseException as error:
            if result is None and primary is None:
                raise
            if observer is not None:
                try:
                    observer("final_check", primary or error)
                except BaseException:
                    pass

"""Read-only independent checkpoint/receipt audit; no candidate imports or calls.

The caller owns a scratch DuckDB connection and final-relation/context views.
Only booleans and aggregate counts leave this module. Paths, IDs and rows do not.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

RELATIONS = ("query_hypothesis", "query_family_decision")
FINAL_FILES = {
    "_COMMITTED",
    "_SUCCESS.json",
    "stage10_query_manifest.json",
    "query_generation_summary.json",
}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def value_chunks(value: Any) -> Iterator[bytes]:
    if value is None:
        yield b"\x00"
    elif type(value) is bool:
        yield b"\x04" + bytes([value])
    elif type(value) is int:
        yield b"\x03" + struct.pack(">Q", value)
    elif isinstance(value, (str, bytes)):
        raw = value.encode("utf-8") if isinstance(value, str) else value
        yield (b"\x01" if isinstance(value, str) else b"\x02") + struct.pack(
            ">Q", len(raw)
        )
        yield raw
    elif isinstance(value, (list, tuple)):
        yield b"\x05" + struct.pack(">Q", len(value))
        for child in value:
            yield from value_chunks(child)
    else:
        raise ValueError("UNSUPPORTED_REVIEW_FRAME")


def frame(values: Any) -> Iterator[bytes]:
    yield struct.pack(">Q", len(values))
    for value in values:
        yield from value_chunks(value)


def identity(domain: str, *values: Any) -> str:
    result = hashlib.sha256(b"SAFE:" + domain.encode("ascii") + b"\0")
    for chunk in frame(values):
        result.update(chunk)
    return result.hexdigest()


def private(path: Path, directory: bool = False) -> bool:
    info = path.lstat()
    return (
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and info.st_uid == os.getuid()
        and (directory or info.st_nlink == 1)
    )


def confined(root: Path, relative: str) -> Path:
    parts = relative.split("/")
    if not relative or any(p in ("", ".", "..") for p in parts) or "\\" in relative:
        raise ValueError("UNSAFE_REVIEW_PATH")
    if Path(relative).is_absolute():
        raise ValueError("UNSAFE_REVIEW_PATH")
    path = root
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError("SYMLINK_REVIEW_PATH")
    return path


def load(path: Path) -> Any:
    def pairs(items: Any) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_REVIEW_JSON_KEY")
            result[key] = value
        return result

    return json.loads(path.read_bytes(), object_pairs_hook=pairs)


def topology(root: Path, names: set[str]) -> bool:
    found = set()
    valid = private(root, True)
    for parent, directories, files in os.walk(root, followlinks=False):
        for directory in directories:
            valid &= private(Path(parent) / directory, True)
        for name in files:
            path = Path(parent) / name
            valid &= private(path)
            found.add(path.relative_to(root).as_posix())
    return valid and found == names


def typed(value: Any, kind: Any) -> Any:
    if value is None:
        return None
    if pa.types.is_struct(kind):
        return tuple(typed(value[f.name], f.type) for f in kind)
    if pa.types.is_list(kind) or pa.types.is_large_list(kind):
        return tuple(typed(v, kind.value_type) for v in value)
    return value


def read_relation(
    root: Path,
    record: dict[str, Any],
    schema: Any,
    check: Callable[[str, bool], None],
    *,
    logical: bool = True,
) -> list[Path]:
    paths, count, previous = [], 0, None
    name = record["name"]
    digest = hashlib.sha256(b"SAFE:stage10-relation:v1\0")
    if logical:
        for chunk in frame(
            (bytes.fromhex(record["schema_sha256"]), record["row_count"])
        ):
            digest.update(chunk)
    for item in record["files"]:
        path = confined(root, item["relative_path"])
        check("operations_file_private", private(path))
        check(
            "operations_file_identity",
            path.stat().st_size == item["bytes"] and sha(path) == item["sha256"],
        )
        check("operations_unique_relation_file", path not in paths)
        paths.append(path)
        with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
            check(
                "operations_relation_schema",
                parquet.schema_arrow.equals(schema, check_metadata=True),
            )
            count += parquet.metadata.num_rows
            if logical:
                for batch in parquet.iter_batches(batch_size=1, use_threads=False):
                    for row in batch.to_pylist():
                        key = (
                            row["query_context_id"],
                            row["representation_fingerprint"]
                            if name == RELATIONS[0]
                            else row["family"],
                        )
                        check(
                            "operations_relation_order",
                            previous is None or previous < key,
                        )
                        previous = key
                        for chunk in frame(
                            tuple(typed(row[f.name], f.type) for f in schema)
                        ):
                            digest.update(chunk)
    check("operations_relation_rows", count == record["row_count"])
    if logical:
        check(
            "operations_relation_logical",
            digest.hexdigest() == record["logical_sha256"],
        )
    return paths


def _sql_paths(paths: list[Path]) -> str:
    return (
        "read_parquet(["
        + ",".join("'" + str(p).replace("'", "''") + "'" for p in paths)
        + "])"
    )


def run(
    db: Any,
    artifact_root: Path,
    manifest: dict[str, Any],
    report_inventory: dict[str, Any],
    check: Callable[[str, bool], None],
) -> dict[str, Any]:
    workspace = Path(manifest["operational_provenance"]["workspace"])
    check("operations_workspace_private", private(workspace, True))
    inputs = manifest["input_binding"]
    context_binding = identity(
        "stage10-context-input:v1",
        *[
            bytes.fromhex(inputs[k]["manifest_sha256"])
            for k in ("stage08", "stage06_row_map", "stage09")
        ],
    )
    binding = {
        "contract_sha256": manifest["contract_sha256"],
        "profile_sha256": manifest["profile_sha256"],
        "schema_sha256": manifest["schema_bundle_sha256"],
        "transliteration_spec_sha256": manifest["runtime"]["specification_sha256"],
        "runtime_lock_sha256": manifest["runtime"]["lock_sha256"],
        "stage08_manifest_sha256": inputs["stage08"]["manifest_sha256"],
        "stage09_manifest_sha256": inputs["stage09"]["manifest_sha256"],
        "checkpoint_version": "stage10_context_shard_checkpoint_v3",
        "context_binding_sha256": context_binding,
        "input_binding_sha256": manifest["input_binding_sha256"],
        "science_sha256": manifest["science_sha256"],
        "budget_policy_sha256": manifest["budget_policy_sha256"],
        "execution_git_sha": manifest["operational_provenance"]["execution_git_sha"],
    }
    schemas = {}
    final_inventory = {}
    for relation in manifest["relations"]:
        name = relation["name"]
        with pq.ParquetFile(
            confined(artifact_root, relation["files"][0]["relative_path"])
        ) as parquet:
            schemas[name] = parquet.schema_arrow
        final_inventory[name] = Counter(
            (f["bytes"], f["sha256"]) for f in relation["files"]
        )
    db.execute("CREATE TEMP TABLE review_operations_keys(query_context_id BLOB)")
    unit_paths = {name: [] for name in RELATIONS}
    diagnostic_paths: list[Path] = []
    prefix_inventory: dict[str, Counter[Any]] = {name: Counter() for name in RELATIONS}
    units = total_contexts = seals = 0
    histogram: Counter[int] = Counter()
    shards = workspace / "workspace/shards"
    check(
        "operations_prefix_set",
        private(shards, True)
        and {p.name for p in shards.iterdir()} == set("0123456789abcdef"),
    )
    for prefix in "0123456789abcdef":
        root = shards / prefix
        record = load(root / "checkpoint.json")
        check(
            "operations_prefix_binding",
            record["binding"] == binding and record["prefix"] == prefix,
        )
        check(
            "operations_prefix_manifest_canonical",
            (root / "checkpoint.json").read_bytes() == canonical(record),
        )
        check(
            "operations_prefix_seal",
            load(root / "_VALIDATED.json")
            == {
                "version": "stage10_validated_unit_v3",
                "checkpoint_sha256": sha(root / "checkpoint.json"),
            },
        )
        seals += 1
        idx = root / "units.jsonl"
        check(
            "operations_index_identity",
            record["units_index"]
            == {
                "relative_path": "units.jsonl",
                "bytes": idx.stat().st_size,
                "sha256": sha(idx),
            },
        )
        indexes = []
        for raw in idx.read_bytes().splitlines(keepends=True):
            item = json.loads(raw)
            check("operations_index_canonical", raw == canonical(item))
            indexes.append(item)
        check(
            "operations_unit_directory_set",
            {p.name for p in (root / "units").iterdir()}
            == {f"{i:06}" for i in range(len(indexes))},
        )
        prefix_keys, expected_files = (
            [],
            {"checkpoint.json", "_VALIDATED.json", "units.jsonl"},
        )
        for ordinal, item in enumerate(indexes):
            unit = root / "units" / f"{ordinal:06}"
            saved = load(unit / "checkpoint.json")
            check(
                "operations_unit_index",
                item
                == {
                    "ordinal": ordinal,
                    "checkpoint_sha256": sha(unit / "checkpoint.json"),
                },
            )
            check(
                "operations_unit_canonical",
                (unit / "checkpoint.json").read_bytes() == canonical(saved),
            )
            check(
                "operations_unit_binding",
                saved["binding"] == binding and saved["prefix"] == prefix,
            )
            check(
                "operations_unit_seal",
                load(unit / "_VALIDATED.json")
                == {
                    "version": "stage10_validated_unit_v3",
                    "checkpoint_sha256": sha(unit / "checkpoint.json"),
                },
            )
            seals += 1
            keys = [bytes.fromhex(k) for k in saved["context_ids"]]
            check(
                "operations_unit_key_order",
                keys == sorted(set(keys))
                and len(keys) <= 64
                and all(len(k) == 32 and k.hex().startswith(prefix) for k in keys),
            )
            prefix_keys.extend(keys)
            histogram[len(keys)] += 1
            if keys:
                db.executemany(
                    "INSERT INTO review_operations_keys VALUES (?)",
                    [(k,) for k in keys],
                )
            names = {"checkpoint.json", "_VALIDATED.json"}
            check(
                "operations_unit_relations",
                [r["name"] for r in saved["relations"]] == list(RELATIONS),
            )
            for relation in saved["relations"]:
                name = relation["name"]
                final = next(r for r in manifest["relations"] if r["name"] == name)
                check(
                    "operations_unit_schema_binding",
                    relation["schema_sha256"] == final["schema_sha256"],
                )
                unit_paths[name].extend(
                    read_relation(unit, relation, schemas[name], check)
                )
                names.update(f["relative_path"] for f in relation["files"])
            diag = saved["diagnostics"]
            local_diagnostics = []
            for f in diag["files"]:
                path = confined(unit, f["relative_path"])
                check(
                    "operations_diagnostics_file",
                    private(path)
                    and path.stat().st_size == f["bytes"]
                    and sha(path) == f["sha256"],
                )
                with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
                    check(
                        "operations_diagnostics_schema",
                        hashlib.sha256(
                            parquet.schema_arrow.serialize().to_pybytes()
                        ).hexdigest()
                        == diag["schema_sha256"],
                    )
                    for batch in parquet.iter_batches(
                        batch_size=64, columns=["query_context_id"]
                    ):
                        local_diagnostics.extend(batch.column(0).to_pylist())
                diagnostic_paths.append(path)
                names.add(f["relative_path"])
            check(
                "operations_diagnostics_keys",
                local_diagnostics == keys and diag["row_count"] == len(keys),
            )
            check("operations_unit_topology", topology(unit, names))
            expected_files.update("units/" + f"{ordinal:06}/" + n for n in names)
            units += 1
        check("operations_prefix_keys", prefix_keys == sorted(set(prefix_keys)))
        check(
            "operations_prefix_counts",
            len(prefix_keys) == record["context_count"]
            and len(indexes) == record["unit_count"],
        )
        check(
            "operations_prefix_relations",
            [r["name"] for r in record["relations"]] == list(RELATIONS),
        )
        for relation in record["relations"]:
            name = relation["name"]
            read_relation(root, relation, schemas[name], check)
            prefix_inventory[name].update(
                (f["bytes"], f["sha256"]) for f in relation["files"]
            )
            expected_files.update(f["relative_path"] for f in relation["files"])
        check("operations_prefix_topology", topology(root, expected_files))
        total_contexts += len(prefix_keys)
    check(
        "operations_key_totality",
        db.execute(
            "SELECT count(*) FROM ((SELECT * FROM review_operations_keys EXCEPT ALL SELECT query_context_id FROM contexts) UNION ALL (SELECT query_context_id FROM contexts EXCEPT ALL SELECT * FROM review_operations_keys))"
        ).fetchone()[0]
        == 0,
    )
    relation_differences = {}
    for name in RELATIONS:
        source = _sql_paths(unit_paths[name])
        difference = db.execute(
            f"SELECT count(*) FROM ((SELECT * FROM {source} EXCEPT ALL SELECT * FROM {name}) UNION ALL (SELECT * FROM {name} EXCEPT ALL SELECT * FROM {source}))"
        ).fetchone()[0]
        check("operations_unit_final_exact_" + name, difference == 0)
        relation_differences[name] = difference
        check(
            "operations_prefix_final_physical_" + name,
            prefix_inventory[name] == final_inventory[name],
        )
    diagnostic_source = _sql_paths(diagnostic_paths)
    fields = "query_context_id,stable_source_row_id_v1,role,stage06_exact_candidate_id"
    context_fields = "query_context_id,stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id"
    diagnostic_difference = db.execute(
        f"SELECT count(*) FROM ((SELECT {fields} FROM {diagnostic_source} EXCEPT ALL SELECT {context_fields} FROM contexts) UNION ALL (SELECT {context_fields} FROM contexts EXCEPT ALL SELECT {fields} FROM {diagnostic_source}))"
    ).fetchone()[0]
    check("operations_diagnostics_mapback", diagnostic_difference == 0)
    seen_receipts = set()
    for item in report_inventory["receipts"]:
        relative = item["path"]
        path = confined(
            artifact_root if relative in FINAL_FILES else workspace, relative
        )
        check("operations_receipt_unique", relative not in seen_receipts)
        seen_receipts.add(relative)
        check(
            "operations_receipt_identity",
            private(path)
            and path.stat().st_size == item["bytes"]
            and sha(path) == item["sha256"],
        )
    check(
        "operations_receipt_count",
        len(seen_receipts)
        == report_inventory["receipt_count"]
        == report_inventory.get("expected_receipt_count", 1117),
    )
    completed = load(workspace / "completed.json")
    counts, timers = (
        completed["progress"]["counts"],
        completed["progress"]["timings_inclusive"],
    )
    expected_counts = {
        "checkpoints_completed": units,
        "checkpoints_reused": 0,
        "contexts_completed": total_contexts,
        "contexts_loaded": total_contexts,
        "family_decisions_written": next(
            r["row_count"] for r in manifest["relations"] if r["name"] == RELATIONS[1]
        ),
        "hypotheses_written": next(
            r["row_count"] for r in manifest["relations"] if r["name"] == RELATIONS[0]
        ),
    }
    check(
        "operations_completed_counts",
        all(counts[k] == v for k, v in expected_counts.items()),
    )
    check(
        "operations_completed_identity",
        completed["manifest_sha256"]
        == sha(artifact_root / "stage10_query_manifest.json")
        and completed["logical_sha256"] == manifest["logical_sha256"],
    )
    check(
        "operations_three_replays",
        timers["publication_scientific_replay"]["calls"] == 3,
    )
    check(
        "operations_four_population_passes",
        all(
            timers[k]["calls"] == 4 * total_contexts
            for k in (
                "certificate",
                "context_construction",
                "source_field_evidence",
                "Q1",
                "Q2",
                "Q3",
                "Q4",
                "Q5",
                "Q6",
            )
        ),
    )
    check(
        "operations_candidate_population",
        units == 1099 and seals == 1115 and total_contexts == 69747,
    )
    if "stdout_sha256" in report_inventory:
        check(
            "operations_stdout_hash",
            sha(Path(report_inventory["_review_stdout_path"]))
            == report_inventory["stdout_sha256"],
        )
    stdout_records = audit_logs(
        Path(report_inventory["_review_stdout_path"])
        if "_review_stdout_path" in report_inventory
        else None,
        Path(report_inventory["_review_stderr_path"])
        if "_review_stderr_path" in report_inventory
        else None,
        manifest,
        completed,
        artifact_root.name,
        check,
        terminal_marker=report_inventory.get("terminal_marker"),
    )
    return {
        "unit_count": units,
        "prefix_count": 16,
        "seal_count": seals,
        "context_count": total_contexts,
        "receipt_count": len(seen_receipts),
        "unit_final_hypothesis_differences": relation_differences[RELATIONS[0]],
        "unit_final_decision_differences": relation_differences[RELATIONS[1]],
        "diagnostic_mapback_differences": diagnostic_difference,
        "checkpoint_size_histogram": {str(k): v for k, v in sorted(histogram.items())},
        "reported_scientific_replays": timers["publication_scientific_replay"]["calls"],
        "stdout_records": stdout_records,
    }


def numeric_timers(report, workspace_progress):
    """Two distinct Progress instances exist: input preparation and workspace."""
    for field in ("timings_inclusive", "sql_categories"):
        values = report.get(field, {})
        expected_names = (
            ({"input_validation"} if field == "timings_inclusive" else set())
            if report.get("phase") == "input_validation"
            else set(workspace_progress[field])
        )
        if not isinstance(values, dict) or not set(values) <= expected_names:
            return False
        if not all(
            isinstance(value, dict)
            and set(value) <= {"calls", "wall_ns", "cpu_ns"}
            and all(type(n) is int and n >= 0 for n in value.values())
            for value in values.values()
        ):
            return False
    return True


def audit_logs(
    stdout, stderr, manifest, completed, publication_key, check, *, terminal_marker=None
):
    """Fixed aggregate diagnostics only; no log value is returned or printed."""
    stdout_records = 0
    markers = 0
    if stdout is not None:
        allowed = {
            "operational_version",
            "phase",
            "failed_phase",
            "elapsed_ns",
            "counts",
            "timings_inclusive",
            "observations",
            "sql_categories",
            "wal_observed_high_water_bytes",
            "max_rss_native",
            "event",
        }
        with stdout.open("rb") as stream:
            for raw in stream:
                if (
                    terminal_marker is not None
                    and raw == terminal_marker.encode("ascii") + b"\n"
                ):
                    markers += 1
                    continue
                check("operations_stdout_marker_is_last", markers == 0)
                report = json.loads(raw)
                if "operational_version" in report:
                    check(
                        "operations_stdout_closed_schema",
                        set(report) <= allowed
                        and report["operational_version"] == "stage10_progress_v2",
                    )
                    check(
                        "operations_stdout_numeric_aggregates",
                        all(
                            set(report.get(k, {})) <= set(completed["progress"][k])
                            and all(
                                type(v) is int and v >= 0
                                for v in report.get(k, {}).values()
                            )
                            for k in ("counts", "observations")
                        ),
                    )
                    check(
                        "operations_stdout_numeric_timers",
                        numeric_timers(report, completed["progress"]),
                    )
                    check(
                        "operations_stdout_labels",
                        report.get("failed_phase") is None
                        and bool(re.fullmatch("[a-z_]+", report.get("phase", "")))
                        and bool(re.fullmatch("[a-z_]+", report.get("event", ""))),
                    )
                else:
                    check(
                        "operations_stdout_terminal_schema",
                        set(report)
                        == {
                            "status",
                            "manifest_sha256",
                            "logical_sha256",
                            "profile_sha256",
                            "publication_key",
                            "publication_disposition",
                            "commit_record_id",
                            "registration_sha256",
                            "protocol",
                            "relation_counts",
                            "operating_budget",
                            "pelias_calls",
                            "external_address_calls",
                        },
                    )
                    check(
                        "operations_stdout_terminal_identity",
                        report.get("status")
                        == "STAGE10_DEVELOPMENT_CANDIDATE_PUBLISHED_NOT_ACCEPTED"
                        and report.get("manifest_sha256")
                        == completed["manifest_sha256"]
                        and report.get("logical_sha256") == manifest["logical_sha256"]
                        and report.get("profile_sha256") == manifest["profile_sha256"]
                        and report.get("publication_key") == publication_key
                        and report.get("publication_disposition") == "PASS"
                        and report.get("relation_counts")
                        == {r["name"]: r["row_count"] for r in manifest["relations"]}
                        and report.get("operating_budget") is None
                        and report.get("pelias_calls")
                        == report.get("external_address_calls")
                        == 0,
                    )
                stdout_records += 1
        check("operations_stdout_count", stdout_records == 1103)
        check(
            "operations_stdout_audit_marker",
            markers == int(terminal_marker is not None),
        )
    if stderr is not None:
        check(
            "operations_stderr_empty",
            stderr.stat().st_size == 0,
        )
    return stdout_records

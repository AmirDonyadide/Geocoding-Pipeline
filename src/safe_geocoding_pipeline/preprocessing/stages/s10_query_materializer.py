"""Stage 10 bounded catalog, immutable checkpoints and full deterministic replay.

Protected entry points live in s10_query_execution. These mechanics also accept
invented typed fixtures; they contain no local/protected runtime bypass.
"""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import s09_reference_io as generic_io
from . import s09_reference_pack as pack
from . import s10_query_contract as c
from . import s10_query_diagnostics as diagnostics
from . import s10_query_contexts as contexts
from . import s10_query_families as families
from . import s10_query_io as io
from . import s10_query_publication as publication
from . import s10_query_summary as summary
from . import s10_query_checkpoints as units
from . import s10_query_operations as ops

SHARDS = tuple(f"{i:x}" for i in range(16))


def file_record(path: Path, root: Path) -> dict[str, Any]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": c.sha256_file(path),
    }


def relation_record(
    name: str, paths: Sequence[Path], root: Path, count: int
) -> dict[str, Any]:
    return {
        "name": name,
        "row_count": count,
        "schema_sha256": c.schema_fingerprint(name).hex(),
        "logical_sha256": io.relation_fingerprint(
            name, count, generic_io.parquet_rows(paths, batch_rows=1)
        ).hex(),
        "files": [file_record(p, root) for p in paths],
    }


def register_outputs(
    work: contexts.ContextWorkspace, root: Path, records: Sequence[Mapping[str, Any]]
) -> None:
    for record in records:
        name = record["name"]
        c.require(name in c.RELATIONS, "STAGE10_UNKNOWN_RELATION")
        paths = [pack.confined(root, item["relative_path"]) for item in record["files"]]
        work.db.execute(
            f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {io.parquet_sql(paths)}"
        )


def checkpoint_binding(
    work: contexts.ContextWorkspace, executable: str
) -> dict[str, Any]:
    return {
        "checkpoint_version": "stage10_context_shard_checkpoint_v2",
        "context_binding_sha256": work.accepted.context_binding.hex(),
        "input_binding_sha256": work.accepted.identifier.hex(),
        "science_sha256": work.science.hex(),
        "budget_policy_sha256": c.budget_fingerprint().hex(),
        "execution_git_sha": executable,
    }


def validate_checkpoint(
    root: Path, expected: Mapping[str, Any], prefix: str
) -> dict[str, Any]:
    return units.validate_prefix(root, expected, prefix)


def generate_catalog(
    work: contexts.ContextWorkspace,
    runtime: families.TransformRuntime,
    executable: str,
    *,
    resume: Path | None = None,
    order: Sequence[str] = SHARDS,
    unit_contexts: int = ops.PAGE_CONTEXTS,
) -> list[dict[str, Any]]:
    c.require(sorted(order) == list(SHARDS), "STAGE10_SHARD_PARTITION_INVALID")
    shard_root = work.root / "shards"
    shard_root.mkdir(mode=0o700)
    records = {}
    for prefix in order:
        records[prefix] = units.generate_prefix(
            work,
            runtime,
            executable,
            prefix,
            resume=resume / prefix if resume is not None else None,
            unit_contexts=unit_contexts,
        )
    combined = []
    for name in c.RELATIONS:
        paths: list[Path] = []
        count = 0
        for prefix in SHARDS:
            record = next(r for r in records[prefix]["relations"] if r["name"] == name)
            count += record["row_count"]
            paths.extend(
                shard_root / prefix / f["relative_path"] for f in record["files"]
            )
        combined.append(relation_record(name, paths, work.root, count))
    register_outputs(work, work.root, combined)
    summary.validate_integrity(work.db)
    return combined


def replay(work: contexts.ContextWorkspace, runtime: families.TransformRuntime) -> None:
    """Reconstruct both complete logical relations; no spot checks or protected logs."""
    readers = {
        name: contexts.sql_rows(
            work.db, f"SELECT * FROM {name} ORDER BY " + ",".join(c.ORDER_KEYS[name])
        )
        for name in c.RELATIONS
    }
    try:
        for context in work.contexts(diagnostics=False):
            generated = families.generate(context, runtime)
            for (name, reader), rows in zip(readers.items(), generated, strict=True):
                for expected in rows:
                    observed = next(reader, None)
                    c.require(
                        observed is not None and observed == expected,
                        "STAGE10_FULL_REPLAY_MISMATCH",
                    )
                    assert observed is not None
                    io.check_identity(
                        observed,
                        name,
                        work.accepted.context_binding,
                        work.accepted.identifier,
                        work.science,
                    )
        c.require(
            all(next(reader, None) is None for reader in readers.values()),
            "STAGE10_FULL_REPLAY_EXTRA_ROWS",
        )
    finally:
        for reader in readers.values():
            reader.close()


class CatalogArtifact:
    def __init__(
        self,
        work: contexts.ContextWorkspace,
        runtime: families.TransformRuntime,
        records: Sequence[Mapping[str, Any]],
        provenance: Mapping[str, Any],
        runtime_identity: Mapping[str, Any],
    ) -> None:
        self.work, self.runtime, self.records = work, runtime, records
        self.provenance, self.runtime_identity = provenance, runtime_identity
        self.operational_diagnostics = diagnostics.build(work)
        self.expected_summary = summary.build_summary(
            work.db, work.accepted.identifier, work.science
        )

    def build(self, root: Path) -> Mapping[str, Any]:
        start = time.monotonic()
        records = []
        for record in self.records:
            target = root / record["name"]
            target.mkdir(mode=0o700)
            paths: list[Path] = []
            for ordinal, item in enumerate(record["files"]):
                source = pack.confined(self.work.root, item["relative_path"])
                destination = target / f"part-{ordinal:06}.parquet"
                # Exclusive destination; never hard-link mutable work to final.
                with source.open("rb") as src:
                    fd = os.open(
                        destination,
                        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                        0o600,
                    )
                    with os.fdopen(fd, "wb") as dst:
                        shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
                        dst.flush()
                        os.fsync(dst.fileno())
                c.require(
                    c.sha256_file(destination) == item["sha256"],
                    "STAGE10_COPY_BYTE_MISMATCH",
                )
                paths.append(destination)
            copied = relation_record(record["name"], paths, root, record["row_count"])
            c.require(
                copied["logical_sha256"] == record["logical_sha256"],
                "STAGE10_COPY_LOGICAL_MISMATCH",
            )
            records.append(copied)
        io.write_json(root / io.SUMMARY_NAME, self.expected_summary)
        summary_sha = c.sha256_file(root / io.SUMMARY_NAME)
        logical = io.dataset_fingerprint(
            self.work.accepted.identifier,
            self.work.science,
            records,
            bytes.fromhex(summary_sha),
        )
        return {
            "manifest_version": c.MANIFEST,
            "kind": publication.DEVELOPMENT,
            "split": "DEVELOPMENT",
            "input_binding": dict(self.work.accepted.binding),
            "input_binding_sha256": self.work.accepted.identifier.hex(),
            "science_sha256": self.work.science.hex(),
            "budget_policy_sha256": c.budget_fingerprint().hex(),
            "contract_sha256": c.contract_fingerprint().hex(),
            "profile_sha256": io.profile_fingerprint(self.work.science).hex(),
            "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
            "logical_sha256": logical.hex(),
            "plan_mode": c.MODE,
            "operating_budget": None,
            "design_merge_sha": c.DESIGN_MERGE,
            "design_package_sha256": c.DESIGN_PACKAGE_SHA256,
            "runtime": dict(self.runtime_identity),
            "relations": records,
            "metadata_inventory": [file_record(root / io.SUMMARY_NAME, root)],
            "operational_provenance": {
                **self.provenance,
                "owner_execution_diagnostics": self.operational_diagnostics,
                "publication_copy_elapsed_seconds": int(time.monotonic() - start),
            },
        }

    def validate(
        self, root: Path, digest: str, state: publication.State
    ) -> Mapping[str, Any]:
        manifest = publication.validate_terminal(root, digest, state)
        expected = {
            "manifest_version": c.MANIFEST,
            "kind": publication.DEVELOPMENT,
            "split": "DEVELOPMENT",
            "input_binding": dict(self.work.accepted.binding),
            "input_binding_sha256": self.work.accepted.identifier.hex(),
            "science_sha256": self.work.science.hex(),
            "budget_policy_sha256": c.budget_fingerprint().hex(),
            "contract_sha256": c.contract_fingerprint().hex(),
            "profile_sha256": io.profile_fingerprint(self.work.science).hex(),
            "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
            "plan_mode": c.MODE,
            "operating_budget": None,
            "design_merge_sha": c.DESIGN_MERGE,
            "design_package_sha256": c.DESIGN_PACKAGE_SHA256,
            "runtime": dict(self.runtime_identity),
        }
        c.require(
            set(manifest)
            == set(expected)
            | {
                "logical_sha256",
                "relations",
                "metadata_inventory",
                "operational_provenance",
            }
            and all(manifest[k] == v for k, v in expected.items()),
            "STAGE10_MANIFEST_BINDING_INVALID",
        )
        c.require(
            manifest["operational_provenance"]["execution_git_sha"]
            == self.provenance["execution_git_sha"],
            "STAGE10_EXECUTABLE_BINDING_MISMATCH",
        )
        c.require(
            [r["name"] for r in manifest["relations"]] == list(c.RELATIONS)
            and manifest["metadata_inventory"]
            == [file_record(root / io.SUMMARY_NAME, root)],
            "STAGE10_MANIFEST_INVENTORY_INVALID",
        )
        for record in manifest["relations"]:
            io.validate_relation(root, record)
        register_outputs(self.work, root, manifest["relations"])
        # Reconstruct every transformation, selector, membership, ID and byte.
        with self.work.progress.measure("publication_scientific_replay"):
            replay(self.work, self.runtime)
        recomputed = summary.build_summary(
            self.work.db, self.work.accepted.identifier, self.work.science
        )
        summary.reconcile_summary(c.read_json(root / io.SUMMARY_NAME), recomputed)
        c.require(
            publication.read_private(root / io.SUMMARY_NAME) == c.canonical(recomputed),
            "STAGE10_SUMMARY_CANONICAL_INVALID",
        )
        c.require(
            manifest["operational_provenance"]["owner_execution_diagnostics"]
            == diagnostics.build(self.work),
            "STAGE10_OPERATIONAL_DIAGNOSTICS_MISMATCH",
        )
        expected_logical = io.dataset_fingerprint(
            self.work.accepted.identifier,
            self.work.science,
            manifest["relations"],
            bytes.fromhex(c.sha256_file(root / io.SUMMARY_NAME)),
        ).hex()
        c.require(
            manifest["logical_sha256"] == expected_logical,
            "STAGE10_DATASET_FINGERPRINT_MISMATCH",
        )
        return manifest

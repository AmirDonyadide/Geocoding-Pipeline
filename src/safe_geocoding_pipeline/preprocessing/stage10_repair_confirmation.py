"""One guarded first-shard confirmation; no candidate publication entry point.

Only a pinned COPY of the failed work database is recovered. The protected
16-context historical rows gate the first-shard replay, partition comparison
and completed-unit resume. Aggregate receipts never contain context IDs/text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from . import stage10_throughput_diagnostic as historical
from .stages import s09_reference_input as a8
from .stages import s09_reference_io as base
from .stages import s09_reference_pack as pack
from .stages import s10_query_checkpoints as units
from .stages import s10_query_contexts as cx
from .stages import s10_query_contract as c
from .stages import s10_query_execution as ex
from .stages import s10_query_families as families
from .stages import s10_query_input as inputs
from .stages import s10_query_io as io
from .stages import s10_query_materializer as m
from .stages import s10_query_operations as ops
from .stages import s10_query_publication as publication
from .stages import s10_query_summary as summary
from .stages import s10_query_transliteration as tr

PARENT = "derived/controlled/stage10/confirmations"
DIAGNOSTIC = "derived/controlled/stage10/diagnostics/stage10_throughput_20260919T122820Z_622c0589d1dc"
REPORT_SHA = "260355d945ee7a2104848aa29a06989a3d0229223bf07b4cff6094a1f30dfed1"
SELECTION_SHA = "fb285755e571bca37c7e3245a806ffee7cea180b2d1aab3783dee662a265763d"
SNAPSHOT = {
    "context.duckdb": "693d4c42c47cb3b4463dbb7f0f7730879213fd23b1118e1f075e1b2cdc65818a",
    "context.duckdb.wal": "7290dc3872355d4efc5d0d7c3f4ba9fcf14ebb8aad84fcd3a8d628d07bf1c99b",
}
CONTEXTS = 4424
GATE_COUNTS = (16, 96, 35)


def preflight(executable: str, output: Path) -> Path:
    require_goethe_nhr_slurm("stage10-repair-confirmation")
    c.require_runtime()
    c.require(
        bool(re.fullmatch("[a-f0-9]{40}", executable)),
        "CONFIRMATION_EXECUTABLE_INVALID",
    )
    for arguments, expected, code in (
        (["rev-parse", "HEAD"], executable, 0),
        (["status", "--porcelain"], "", 0),
        (["symbolic-ref", "-q", "HEAD"], "", 1),
        (
            [
                "merge-base",
                "--is-ancestor",
                "2ab3b143b2731f6781564646a9c91e844da2a176",
                "HEAD",
            ],
            "",
            0,
        ),
    ):
        result = subprocess.run(
            ["git", *arguments], cwd=ex.REPOSITORY, capture_output=True, text=True
        )
        c.require(
            result.returncode == code and result.stdout.strip() == expected,
            "CONFIRMATION_CLEAN_EXACT_DETACHED_REQUIRED",
        )
    c.require(
        os.environ.get("SLURM_RESTART_COUNT", "0") == "0",
        "CONFIRMATION_REQUEUE_PROHIBITED",
    )
    ex.verify_design(ex.REPOSITORY)
    inventory = c.read_json(
        ex.REPOSITORY
        / "docs/scientific_assets/stage10_implementation_inventory_v1.json"
    )
    for item in inventory["files"]:
        c.require(
            c.sha256_file(ex.REPOSITORY / item["path"]) == item["sha256"],
            "CONFIRMATION_EXECUTABLE_INVENTORY_MISMATCH",
        )
    root = inputs.PROJECT_ALIAS.resolve(strict=True)
    c.require(
        output.parent == root / PARENT
        and re.fullmatch("stage10_repair_[0-9TZ_a-f]+", output.name) is not None,
        "CONFIRMATION_OUTPUT_SCOPE_INVALID",
    )
    publication.check_parent(output)
    c.require(not os.path.lexists(output), "CONFIRMATION_OUTPUT_EXISTS")
    signature = ex.mount_signature(output.parent)
    c.require(
        signature == ex.mount_signature(root / ex.STAGE09_RELATIVE)
        and signature[3] == "panfs",
        "CONFIRMATION_TOPOLOGY_CHANGED",
    )
    c.require(
        shutil.disk_usage(output.parent).free >= 64 * 1024**3,
        "CONFIRMATION_DISK_RESERVE",
    )
    return root


def attach_copy(raw: Any, root: Path, science: bytes) -> cx.ContextWorkspace:
    """Confirmation-only recovered work index; never an accepted input adapter."""
    work = object.__new__(cx.ContextWorkspace)
    work.root, work.science = root, science
    work.accepted = cast(
        Any,
        SimpleNamespace(
            identifier=bytes.fromhex(historical.INPUT_SHA),
            context_binding=c.identity(
                "stage10-context-input:v1",
                bytes.fromhex(a8.STAGE08_MANIFEST_SHA256),
                bytes.fromhex(inputs.STAGE06_MANIFEST),
                bytes.fromhex(inputs.STAGE09_MANIFEST),
            ),
        ),
    )
    work.progress = ops.Progress(root / "preparation_progress")
    work.db = cast(Any, ops.TimedConnection(raw, work.progress))
    work.reference = cx.ReferenceAccess(work.db, root, work.progress)
    work.parser_certificates = cx.ByteCache(1024 * 1024)
    work.component_cache = cx.ByteCache(4 * 1024 * 1024)
    work.diagnostic_buffer, work.diagnostic_bytes = [], 0
    return work


def reset_measurement(work: cx.ContextWorkspace, name: str) -> None:
    work.flush_diagnostics()
    work.db.execute("DELETE FROM stage10_context_diagnostics")
    work.checkpoint_database()
    work.progress = ops.Progress(work.root / name)
    cast(Any, work.db).progress = work.progress
    # Cold caches per comparison pass, immutable prepared indexes shared.
    work.reference = cx.ReferenceAccess(work.db, work.root, work.progress)
    work.parser_certificates = cx.ByteCache(1024 * 1024)
    work.component_cache = cx.ByteCache(4 * 1024 * 1024)


def compare_historical(
    work: cx.ContextWorkspace, runtime: Any, diagnostic: Path, selected: list[bytes]
) -> dict[str, Any]:
    hypotheses = decisions = 0
    payload_hashes: list[str] = []
    for ordinal, identifier in enumerate(selected):
        before = int.from_bytes(identifier) - 1
        contexts = work.contexts(
            after=before.to_bytes(32) if before >= 0 else None, until=identifier
        )
        try:
            context = next(contexts)
            c.require(
                context.identifier == identifier, "CONFIRMATION_GATE_CONTEXT_MISMATCH"
            )
            generated = families.generate(context, runtime)
            c.require(
                next(contexts, None) is None, "CONFIRMATION_GATE_CONTEXT_CARDINALITY"
            )
        finally:
            getattr(contexts, "close")()
        for name, rows in zip(c.RELATIONS, generated, strict=True):
            directory = diagnostic / "serializations" / f"context-{ordinal:02}" / name
            pack.regular_private(directory, directory=True)
            paths = sorted(directory.glob("*.parquet"))
            c.require(bool(paths), "CONFIRMATION_HISTORICAL_PAYLOAD_MISSING")
            expected_rows: list[dict[str, Any]] = []
            for path in paths:
                pack.regular_private(path)
                c.require(
                    pq.read_schema(path).equals(
                        io.output_schema(name), check_metadata=True
                    ),
                    "CONFIRMATION_HISTORICAL_SCHEMA_MISMATCH",
                )
                payload_hashes.append(c.sha256_file(path))
                for row in base.parquet_rows([path], batch_rows=1):
                    c.require(len(expected_rows) < 6, "CONFIRMATION_GATE_ROW_OVERFLOW")
                    io.validate_values(row, name)
                    io.check_identity(
                        row,
                        name,
                        work.accepted.context_binding,
                        work.accepted.identifier,
                        work.science,
                    )
                    expected_rows.append(row)
            c.require(rows == expected_rows, "CONFIRMATION_OLD_NEW_SCIENTIFIC_MISMATCH")
        hypotheses += len(generated[0])
        decisions += len(generated[1])
    c.require(
        (len(selected), decisions, hypotheses) == GATE_COUNTS,
        "CONFIRMATION_HISTORICAL_TOTAL_MISMATCH",
    )
    return {
        "contexts": len(selected),
        "hypotheses": hypotheses,
        "decisions": decisions,
        "exact_rows_equal": True,
        "historical_file_sha256": payload_hashes,
        "measurement": work.progress.snapshot(),
    }


def relation_identity(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {k: r[k] for k in ("name", "row_count", "schema_sha256", "logical_sha256")}
        for r in record["relations"]
    ]


def validate_pass(
    work: cx.ContextWorkspace,
    root: Path,
    record: dict[str, Any],
    executable: str,
    expected_count: int,
) -> None:
    units.validate_prefix(root, m.checkpoint_binding(work, executable), "0")
    c.require(record["context_count"] == expected_count, "CONFIRMATION_CONTEXT_LOSS")
    m.register_outputs(work, root, record["relations"])
    summary.validate_integrity(work.db)
    c.require(
        summary.scalar(work.db, "SELECT count(*) FROM query_family_decision")
        == 6 * expected_count,
        "CONFIRMATION_DECISION_COUNT",
    )
    work.checkpoint_database()


def throughput_windows(root: Path) -> list[dict[str, int]]:
    points = [c.read_json(path) for path in sorted(root.glob("progress-*.json"))]
    points = [p for p in points if p["counts"]["checkpoints_completed"] > 0]
    c.require(len(points) >= 3, "CONFIRMATION_THROUGHPUT_WINDOWS_MISSING")
    endpoints = [
        points[len(points) // 3 - 1],
        points[2 * len(points) // 3 - 1],
        points[-1],
    ]
    before_time = before_count = 0
    result = []
    for point in endpoints:
        elapsed = point["elapsed_ns"] - before_time
        count = point["counts"]["contexts_completed"] - before_count
        result.append(
            {
                "contexts": count,
                "elapsed_ns": elapsed,
                "contexts_per_second_millionths": count * 10**15 // elapsed,
            }
        )
        before_time, before_count = (
            point["elapsed_ns"],
            point["counts"]["contexts_completed"],
        )
    return result


def run(executable: str, output: Path) -> dict[str, Any]:
    root = preflight(executable, output)
    output.mkdir(mode=0o700)
    progress = ops.Progress(output / "progress")
    report: dict[str, Any] = {
        "status": "CONFIRMATION_INCOMPLETE",
        "candidate_publication": False,
        "executable": executable,
        "job_id": os.environ["SLURM_JOB_ID"],
        "operating_budget": None,
        "context_target": CONTEXTS,
        "selection": "ORIGINAL_FIRST_HEX_PREFIX_ZERO_V1",
    }
    raw = runtime = work = None
    before_io = ops.io_counters()
    try:
        with ops.termination_guard(), ex.offline_network():
            failed = inputs.controlled_path(
                root / ex.PUBLISH_RELATIVE / "work" / historical.FAILED
            )
            c.require(
                c.sha256_file(failed / "attempt.json") == historical.ATTEMPT_SHA,
                "CONFIRMATION_ORIGINAL_ATTEMPT_CHANGED",
            )
            for relative, name, digest in (
                (
                    ex.STAGE08_RELATIVE,
                    "stage08_address_evidence_manifest.json",
                    a8.STAGE08_MANIFEST_SHA256,
                ),
                (
                    ex.STAGE09_RELATIVE,
                    "stage09_reference_manifest.json",
                    inputs.STAGE09_MANIFEST,
                ),
                (
                    "derived/controlled/stage06/development/stage06_development_20260828T223804Z_f39047cc825d",
                    "stage06_manifest.json",
                    inputs.STAGE06_MANIFEST,
                ),
            ):
                path = inputs.controlled_path(root / relative / name)
                c.require(
                    c.sha256_file(path) == digest, "CONFIRMATION_UPSTREAM_PIN_CHANGED"
                )
            diagnostic = inputs.controlled_path(root / DIAGNOSTIC)
            c.require(
                c.sha256_file(diagnostic / "diagnostic_result.json") == REPORT_SHA,
                "CONFIRMATION_DIAGNOSTIC_REPORT_CHANGED",
            )
            # The historical report uses JSON floats; it is not a new canonical contract.
            old_report = json.loads(
                publication.read_private(diagnostic / "diagnostic_result.json")
            )
            c.require(
                old_report["completed_contexts"] == 16
                and old_report["limited_contexts"] == 0,
                "CONFIRMATION_HISTORICAL_GATE_NOT_COMPLETE",
            )
            with progress.measure("exact_runtime"):
                runtime = ex.runtime_ready(root / ex.RUNTIME_RELATIVE, ex.REPOSITORY)
                for script, value, expected in tr.SYNTHETIC_VECTORS:
                    c.require(
                        runtime.transform(script, value) == expected,
                        "CONFIRMATION_ICU_VECTOR_MISMATCH",
                    )
            report["runtime_lock_sha256"] = runtime.lock_sha256
            work_root = output / "workspace"
            work_root.mkdir(mode=0o700)
            with progress.measure("snapshot_copy_and_hash"):
                for name, expected in SNAPSHOT.items():
                    c.require(
                        historical.copy_evidence(
                            failed / "workspace" / name, work_root / name
                        )
                        == expected,
                        "CONFIRMATION_SNAPSHOT_CHANGED",
                    )
            progress.record(announce=True)
            with progress.measure("snapshot_recovery"):
                raw = historical.open_snapshot(
                    work_root / "context.duckdb", work_root / "spill"
                )
            work = attach_copy(
                raw, work_root, c.science_fingerprint(runtime.asset_binding)
            )
            c.require(
                summary.scalar(work.db, "SELECT count(*) FROM stage10_context_keys")
                == 69747,
                "CONFIRMATION_SOURCE_CONTEXT_COUNT",
            )
            selected = historical.select_contexts(work.db)
            protected = c.read_json(diagnostic / "protected_selection.json")
            c.require(
                protected == {"context_ids": [v.hex() for v in selected]}
                and c.identity("stage10-diagnostic-selection:v1", tuple(selected)).hex()
                == SELECTION_SHA,
                "CONFIRMATION_SELECTION_CHANGED",
            )
            work.db.execute("DROP TABLE selector_selection")
            work.db.execute("DELETE FROM stage10_context_diagnostics")
            with progress.measure("parser_index_preparation"):
                work.prepare_parser_certificates()
                work.prepare_context_index()
                work.checkpoint_database()
            report["preparation"] = work.progress.snapshot()
            report["prepared_database_bytes"] = (
                (work_root / "context.duckdb").stat().st_size
            )
            report["input_index_rows"] = {
                name: summary.scalar(work.db, "SELECT count(*) FROM " + name)
                for name in (
                    "stage10_context_keys",
                    "stage10_components",
                    "stage10_source_reference",
                    "stage10_generation_contexts",
                )
            }
            reset_measurement(work, "gate_progress")
            with progress.measure("historical_equivalence_gate"):
                report["historical_equivalence"] = compare_historical(
                    work, runtime, diagnostic, selected
                )
            io.write_json(
                output / "equivalence_gate.json", report["historical_equivalence"]
            )
            # Explicit diagnostic-only subset on the COPY; upstream occurrences
            # and their IDs remain unchanged. The candidate path has no filter.
            work.db.execute(
                "ALTER TABLE stage10_context_keys RENAME TO stage10_all_context_keys"
            )
            work.db.execute(
                "CREATE TABLE stage10_context_keys AS SELECT * FROM stage10_all_context_keys WHERE starts_with(hex(query_context_id),'0')"
            )
            work.db.execute(
                "CREATE UNIQUE INDEX confirmation_context_key ON stage10_context_keys(query_context_id)"
            )
            c.require(
                summary.scalar(work.db, "SELECT count(*) FROM stage10_context_keys")
                == CONTEXTS,
                "CONFIRMATION_FIRST_SHARD_CHANGED",
            )
            records = []
            for name, size, resume in (
                ("first", 64, None),
                ("repartition", 32, None),
                ("resume", 64, work_root / "first_shards/0"),
            ):
                reset_measurement(work, name + "_progress")
                destination = work_root / (name + "_shards")
                destination.mkdir(mode=0o700)
                with progress.measure(name + "_pass"):
                    record = units.generate_prefix(
                        work,
                        runtime,
                        executable,
                        "0",
                        resume=resume,
                        unit_contexts=size,
                        output_parent=destination,
                    )
                    validate_pass(work, destination / "0", record, executable, CONTEXTS)
                report[name] = {
                    "relations": relation_identity(record),
                    "contexts": record["context_count"],
                    "units": record["unit_count"],
                    "measurement": work.progress.snapshot(),
                    "early_middle_late": throughput_windows(
                        work_root / (name + "_progress")
                    ),
                }
                records.append(relation_identity(record))
                c.require(
                    records[-1] == records[0],
                    "CONFIRMATION_PARTITION_OR_RESUME_CHANGED_OUTPUT",
                )
                io.write_json(output / (name + "_pass.json"), report[name])
            c.require(
                work.progress.counts["checkpoints_reused"] == 70,
                "CONFIRMATION_RESUME_NOT_PROVEN",
            )
            report.update(
                status="CONFIRMATION_VALIDATED",
                exact_partition_equivalence=True,
                resume_validated=True,
                technical_failures=0,
                full_old_first_shard_golden_available=False,
            )
    except BaseException as error:
        report.update(
            status="CONFIRMATION_FAILED", **historical.failure_metadata(error)
        )
        if work is not None:
            report["last_work_progress"] = work.progress.snapshot()
    finally:
        for handle in (work if work is not None else raw, runtime):
            if handle is not None:
                try:
                    handle.close()
                except BaseException:
                    report.update(status="CONFIRMATION_FAILED", close_failure=True)
        report["overall_measurement"] = progress.snapshot()
        after_io = ops.io_counters()
        report["process_io_delta"] = {
            key: after_io[key] - value for key, value in before_io.items()
        }
        io.write_json(output / "confirmation_result.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.execution_git_sha, args.output)
    except BaseException as error:
        print(c.canonical(historical.failure_metadata(error)).decode(), end="")
        return 1
    print(
        c.canonical(
            {"status": report["status"], "candidate_publication": False}
        ).decode(),
        end="",
    )
    return 0 if report["status"] == "CONFIRMATION_VALIDATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())

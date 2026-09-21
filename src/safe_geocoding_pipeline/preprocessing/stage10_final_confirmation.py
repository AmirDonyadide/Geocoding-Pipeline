"""One final guarded confirmation: exact historical gate, replay, adoption, tail.

No candidate publication. Every protected operation requires Goethe SLURM.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any, cast


from ..execution_policy import require_goethe_nhr_slurm
from . import stage10_throughput_diagnostic as historical
from . import stage10_confirmation_observability as telemetry
from .stages import s09_reference_input as a8
from .stages import s09_reference_io as base
from .stages import s10_query_checkpoints as units
from .stages import s10_query_contexts as cx
from .stages import s10_query_contract as c
from .stages import s10_query_execution as ex
from .stages import s10_query_input as inputs
from .stages import s10_query_io as io
from .stages import s10_query_materializer as m
from .stages import s10_query_operations as ops
from .stages import s10_query_publication as publication
from .stages import s10_query_summary as summary
from .stages import s10_query_transliteration as tr

from . import stage10_repair_confirmation as prior
from .stages import s10_reference_store as store
from .stages import s10_query_receipts as receipts

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
REPAIRED_EXECUTABLE = "808123bb145107d7b025471b3b02869cc95fb44a"


GOLDEN = "derived/controlled/stage10/confirmations/stage10_repair_20260920T190012Z_68ce5fbd61c2/workspace/first_shards/0"
GOLDEN_LOGICAL = (
    "547f880b41f0e061b92e2f7822f46bfa707be87d970543df64020ea5d2b47aae",
    "2ab22ee9d079d62cecadd02bae9b86779a01c760a0bc914e8daeebc2ff6a94d7",
)


def verify_repaired_core(repository: Path) -> None:
    """Scientific files remain byte-identical; listed changes are operational."""
    allowed = {
        "s10_query_operations.py",
        "s10_query_contexts.py",
        "s10_query_checkpoints.py",
        "s10_query_materializer.py",
        "s10_query_execution.py",
    }
    original = json.loads(
        subprocess.check_output(
            [
                "git",
                "show",
                REPAIRED_EXECUTABLE
                + ":docs/scientific_assets/stage10_implementation_inventory_v1.json",
            ],
            cwd=repository,
        )
    )
    for item in original["files"]:
        name = item["path"]
        if "/stages/" in name and Path(name).name not in allowed:
            c.require(
                c.sha256_file(repository / name) == item["sha256"],
                "CONFIRMATION_SCIENTIFIC_CORE_CHANGED",
            )


def preflight(executable: str, output: Path) -> Path:
    require_goethe_nhr_slurm("stage10-final-performance-confirmation")
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
                "39c0470adb6c99b7f08f70775fa2e21906e913ec",
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
    verify_repaired_core(ex.REPOSITORY)
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
        and re.fullmatch("stage10_final_[0-9TZ_a-f]+", output.name) is not None,
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
    work = prior.attach_copy(raw, root, science)
    work.reference_store = store.ReferenceStore(work.db, root, work.progress)
    work.reference = cx.ReferenceAccess(
        work.db, root, work.progress, prepared=work.reference_store
    )
    return work


def reset_measurement(work: cx.ContextWorkspace, name: str) -> None:
    prior.reset_measurement(work, name)
    work.reference = cx.ReferenceAccess(
        work.db, work.root, work.progress, prepared=work.reference_store
    )
    work.reference_store.progress = work.progress


def compare_golden(
    work: cx.ContextWorkspace, root: Path, record: dict[str, Any], golden: Path
) -> None:
    expected = c.read_json(golden / "checkpoint.json")
    c.require(
        tuple(r["logical_sha256"] for r in expected["relations"]) == GOLDEN_LOGICAL,
        "CONFIRMATION_GOLDEN_CHANGED",
    )
    c.require(
        prior.relation_identity(record) == prior.relation_identity(expected),
        "CONFIRMATION_GOLDEN_LOGICAL_MISMATCH",
    )
    for actual, saved in zip(record["relations"], expected["relations"], strict=True):
        paths = io.validate_relation(golden, saved)
        left = iter(base.parquet_rows(paths, batch_rows=1))
        for row in base.parquet_rows(
            [root / f["relative_path"] for f in actual["files"]], batch_rows=1
        ):
            c.require(row == next(left, None), "CONFIRMATION_GOLDEN_ROW_MISMATCH")
        c.require(next(left, None) is None, "CONFIRMATION_GOLDEN_ROW_COUNT")


def generation_sql_bound(
    measured: dict[str, Any], contexts: int, checkpoints: int
) -> dict[str, Any]:
    """Closed generation path; preparation and final validation are separate.

    C context calls, K units, F<=C diagnostic flushes, D<=C+K database
    checkpoints, P<=C+K context pages including terminal empty pages:
    source C + parser<=C + component<=2C + spill<=C + P + 2F + D
    + (K+1) key windows + K diagnostic exports <= 9C+4K+1.
    C<=64K gives <=580K+1. Members affect streamed bytes, never statement count.
    Adoption uses key windows K+1 and one diagnostic INSERT + CHECKPOINT per K.
    """
    categories = measured["sql_categories"]
    c.require(
        all(
            categories.get(n, {}).get("calls", 0) == 0
            for n in (
                "REGISTRY_LOOKUP",
                "CAPABILITY_LOOKUP",
                "OBJECT_LOOKUP",
                "MEMBER_STREAM",
            )
        ),
        "CONFIRMATION_FINE_GRAINED_REFERENCE_SQL",
    )
    observed = measured["timings_inclusive"].get("database_execute", {}).get("calls", 0)
    upper = 9 * contexts + 4 * checkpoints + 1
    c.require(observed <= upper, "CONFIRMATION_SQL_BATCH_BOUND")
    return {
        "observed_executions": observed,
        "derived_upper": upper,
        "formula": "9*C+4*K+1; C<=64*K; therefore <=580*K+1",
        "reference_point_executions": 0,
    }


def replay_confirmations(
    work: cx.ContextWorkspace,
    runtime: Any,
    executable: str,
    output: Path,
    progress: ops.Progress,
    report: dict[str, Any],
    expected_count: int,
    *,
    golden: Path | None = None,
    unit_size: int = 64,
) -> None:
    report["phase"] = "confirmation_population_setup"
    reset_measurement(work, "population_setup_progress")
    with progress.measure("confirmation_population_setup"):
        report["population"] = prior.prepare_replay_population(work, expected_count)
    receipts.write(
        output / "population_setup.json",
        {
            "population": report["population"],
            "measurement": work.progress.snapshot(),
            "overall": progress.snapshot(),
        },
    )
    progress.event("context_index_preparation_complete")
    baseline = None
    first_root = work.root / "first_shards/0"
    for name in ("first", "adoption", "partial_tail"):
        resume = None
        fixture: dict[str, Any] = {}
        if name == "adoption":
            resume = first_root
        elif name == "partial_tail":
            resume = work.root / "tail_fixture"
            fixture = prior.prepare_resume_fixture(
                first_root, resume, m.checkpoint_binding(work, executable)
            )
        reset_measurement(work, name + "_progress")
        work.progress.event(
            "generation_start" if name == "first" else "resume_reconciliation_start"
        )
        destination = work.root / (name + "_shards")
        destination.mkdir(mode=0o700)
        report["phase"], report["replay_started"] = name + "_replay", True
        started = time.monotonic_ns()
        with progress.measure(name + "_replay"):
            record = units.generate_prefix(
                work,
                runtime,
                executable,
                "0",
                resume=resume,
                unit_contexts=unit_size,
                output_parent=destination,
            )
        elapsed = time.monotonic_ns() - started
        work.progress.event(
            "generation_complete"
            if name == "first"
            else "resume_reconciliation_complete"
        )
        measurement = work.progress.snapshot()
        regenerated = measurement["counts"]["contexts_loaded"]
        adopted = measurement["counts"]["checkpoints_reused"]
        cert_calls = (
            measurement["timings_inclusive"].get("certificate", {}).get("calls", 0)
        )
        generation_calls = (
            measurement["timings_inclusive"]
            .get("family_generation", {})
            .get("calls", 0)
        )
        expected_units = (expected_count + unit_size - 1) // unit_size
        c.require(
            record["unit_count"] == expected_units, "CONFIRMATION_UNIT_COUNT_INVALID"
        )
        if name == "first":
            c.require(
                regenerated == expected_count and adopted == 0,
                "CONFIRMATION_GENERATION_COUNT",
            )
        elif name == "adoption":
            c.require(
                measurement["timings_inclusive"]
                .get("database_execute", {})
                .get("calls", 0)
                == 3 * expected_units + 1,
                "CONFIRMATION_ADOPTION_SQL_BOUND",
            )
            c.require(
                adopted == expected_units
                and regenerated == cert_calls == generation_calls == 0,
                "CONFIRMATION_ADOPTION_RECOMPUTED_SCIENCE",
            )
        else:
            c.require(
                adopted == fixture["completed_prior_units"]
                and regenerated
                == cert_calls
                == generation_calls
                == fixture["expected_regenerated_contexts"],
                "CONFIRMATION_PARTIAL_REGEN_COUNT",
            )
            c.require(
                prior.tree_fingerprint(cast(Path, resume))
                == fixture["preserved_fixture_sha256"],
                "CONFIRMATION_RESUME_FIXTURE_MUTATED",
            )
        c.require(
            measurement["counts"]["parser_certificate_preparation_calls"] == 0
            and "reference_material_preparation" not in measurement["timings_inclusive"]
            and "context_index_preparation" not in measurement["timings_inclusive"],
            "CONFIRMATION_SETUP_REPEATED_DURING_REPLAY",
        )
        identity = prior.relation_identity(record)
        if baseline is None:
            baseline = identity
        c.require(identity == baseline, "CONFIRMATION_RESUME_CHANGED_OUTPUT")
        # Save completed generation evidence before potentially expensive validation.
        result = {
            "contexts": record["context_count"],
            "relations": identity,
            "replay_elapsed_ns": elapsed,
            "replay_measurement": measurement,
            "regenerated_contexts": regenerated,
            "adopted_units": adopted,
            "completed_checkpoint_certificate_calls": 0 if name != "first" else None,
            "checkpoints": prior.checkpoint_details(destination / "0", record),
            "fixture": fixture,
        }
        if name == "first":
            result["sql_complexity"] = generation_sql_bound(
                measurement, expected_count, expected_units
            )
            result["early_middle_late"] = (
                prior.throughput_windows(work.root / "first_progress")
                if expected_units >= 3
                else []
            )
        receipts.write(output / (name + "_generation.json"), result)
        work.progress.event("validation_start")
        validation_started = time.monotonic_ns()
        prior.validate_pass(work, destination / "0", record, executable, expected_count)
        if name == "first" and golden is not None:
            compare_golden(work, destination / "0", record, golden)
        result["final_validation_elapsed_ns"] = time.monotonic_ns() - validation_started
        result["measurement_after_validation"] = work.progress.snapshot()
        work.progress.event("validation_complete")
        receipts.write(output / (name + "_pass.json"), result)
        report[name] = result
    report["phase"] = "completed"


def run(executable: str, output: Path) -> dict[str, Any]:
    root = preflight(executable, output)
    output.mkdir(mode=0o700)
    progress = ops.Progress(output / "progress")
    report: dict[str, Any] = {
        "status": "CONFIRMATION_INCOMPLETE",
        "candidate_publication": False,
        "executable": executable,
        "confirmation_harness_sha": executable,
        "repaired_stage10_executable_sha": executable,
        "previous_repaired_executable_sha": REPAIRED_EXECUTABLE,
        "phase": "preflight",
        "replay_started": False,
        "job_id": os.environ["SLURM_JOB_ID"],
        "operating_budget": None,
        "context_target": CONTEXTS,
        "selection": "ORIGINAL_FIRST_HEX_PREFIX_ZERO_V1",
    }
    raw = runtime = work = None
    before_io = ops.io_counters()
    try:
        with (
            ops.termination_guard(
                lambda: work.progress if work is not None else progress,
                exit_process=True,
            ),
            ex.offline_network(),
            ExitStack() as hooks,
        ):
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
            report["phase"] = "exact_runtime"
            with progress.measure("exact_runtime"):
                runtime = ex.runtime_ready(root / ex.RUNTIME_RELATIVE, ex.REPOSITORY)
                for script, value, expected in tr.SYNTHETIC_VECTORS:
                    c.require(
                        runtime.transform(script, value) == expected,
                        "CONFIRMATION_ICU_VECTOR_MISMATCH",
                    )
            report["runtime_lock_sha256"] = runtime.lock_sha256
            progress.event("runtime_initialization_complete")
            work_root = output / "workspace"
            work_root.mkdir(mode=0o700)
            report["phase"] = "snapshot_copy_and_hash"
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
            report["phase"] = "snapshot_recovery"
            with progress.measure("snapshot_recovery"):
                raw = historical.open_snapshot(
                    work_root / "context.duckdb", work_root / "spill"
                )
            work = attach_copy(
                raw, work_root, c.science_fingerprint(runtime.asset_binding)
            )
            hooks.enter_context(telemetry.instrument(work))
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
            report["phase"] = "one_time_preparation"
            with progress.measure("reference_material_preparation"):
                work.reference_store.prepare()
            work.progress.event("reference_preparation_complete")
            with progress.measure("parser_certificate_preparation"):
                work.prepare_parser_certificates()
            work.progress.event("parser_preparation_complete")
            with progress.measure("context_index_preparation"):
                work.prepare_context_index()
            with progress.measure("preparation_checkpoint"):
                work.checkpoint_database()
            c.require(
                work.progress.counts["parser_certificate_preparation_calls"] == 1,
                "CONFIRMATION_PARSER_SETUP_COUNT_INVALID",
            )
            work.progress.event("context_index_preparation_complete")
            report["preparation"] = work.progress.snapshot()
            receipts.write(
                output / "preparation.json",
                {
                    "measurement": work.progress.snapshot(),
                    "overall": progress.snapshot(),
                },
            )
            report["reference_certificate_preparation"] = (
                "IMMUTABLE_DISK_INDEX_PREPARED_ONCE_NO_PER_WITNESS_SQL"
            )
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
            report["phase"] = "historical_equivalence_gate"
            with progress.measure("historical_equivalence_gate"):
                report["historical_equivalence"] = prior.compare_historical(
                    work, runtime, diagnostic, selected
                )
            receipts.write(
                output / "equivalence_gate.json", report["historical_equivalence"]
            )
            work.progress.event("equivalence_gate_complete")
            replay_confirmations(
                work,
                runtime,
                executable,
                output,
                progress,
                report,
                CONTEXTS,
                golden=inputs.controlled_path(root / GOLDEN),
            )
            report.update(
                status="CONFIRMATION_VALIDATED",
                prior_partition_equivalence_preserved=True,
                resume_validated=True,
                technical_failures=0,
                full_old_first_shard_golden_available=True,
            )
    except BaseException as error:
        report.update(
            status="CONFIRMATION_FAILED", **historical.failure_metadata(error)
        )
        if work is not None:
            report["last_work_progress"] = work.progress.snapshot()
        report["failure_scope"] = (
            "REPLAY"
            if report["replay_started"]
            else "CONFIRMATION_HARNESS_OR_PREFLIGHT"
        )
        report["candidate_defect"] = report.get("failure_code") in (
            "CONFIRMATION_OLD_NEW_SCIENTIFIC_MISMATCH",
            "CONFIRMATION_HISTORICAL_TOTAL_MISMATCH",
        )
        if (output / "workspace/first_progress").exists():
            points = prior.checkpoint_points(output / "workspace/first_progress")
            report["first_pass_checkpoint_observations"] = points
    finally:
        terminated = progress.terminated or (
            work is not None and work.progress.terminated
        )
        for handle in (
            () if terminated else (work if work is not None else raw, runtime)
        ):
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
        receipts.write(output / "confirmation_result.json", report)
        progress.event(
            "terminal_success"
            if report["status"] == "CONFIRMATION_VALIDATED"
            else "terminal_failure"
        )
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

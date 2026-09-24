"""Public/synthetic confirmation harness checks; never protected local input."""

from __future__ import annotations

import dataclasses
import copy
import signal
import time
from pathlib import Path
from typing import Any
from test_stage10_review_remediation import prior_scientific_projection

import pytest
import duckdb

from safe_geocoding_pipeline.preprocessing import stage10_repair_confirmation as runner
from safe_geocoding_pipeline.preprocessing import (
    stage10_confirmation_observability as telemetry,
)
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as ex
from safe_geocoding_pipeline.preprocessing.stages import s10_query_summary as summary
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_performance_repair import COLLIDING, original_module
from test_stage10_query_families import SyntheticTransform, context


def test_timing_snapshots_are_independent_and_monotonic(
    tmp_path: Path, monkeypatch: Any
) -> None:
    ticks = iter((10, 20, 40, 50, 60, 70, 100, 110, 120))
    cpu = iter((100, 110, 120, 140))
    monkeypatch.setattr(time, "monotonic_ns", lambda: next(ticks))
    monkeypatch.setattr(time, "process_time_ns", lambda: next(cpu))
    monkeypatch.setattr(time, "time", lambda: pytest.fail("wall clock used"))
    progress = ops.Progress(tmp_path / "snapshots")
    with progress.measure("public_phase"):
        progress.counts["contexts_loaded"] = 1
        progress.observations["database_bytes"] = 20
    first = progress.snapshot()
    frozen = copy.deepcopy(first)
    progress.record()
    with progress.measure("public_phase"):
        progress.counts["contexts_loaded"] = 2
        progress.observations["database_bytes"] = 40
    second = progress.snapshot()
    progress.record()
    assert first == frozen
    assert first["elapsed_ns"] == 40
    assert first["timings_inclusive"]["public_phase"]["wall_ns"] == 20
    assert second["timings_inclusive"]["public_phase"]["wall_ns"] == 50
    assert second["counts"]["contexts_loaded"] == 2
    assert (
        c.read_json(tmp_path / "snapshots/progress-000000.json")["timings_inclusive"]
        == first["timings_inclusive"]
    )
    assert (
        c.read_json(tmp_path / "snapshots/progress-000001.json")["timings_inclusive"]
        == second["timings_inclusive"]
    )


def test_approved_computation_pin_and_fail_closed(monkeypatch: Any) -> None:
    # Historical harness must reject the newly authorized operational core.
    with pytest.raises(c.Stage10Error, match="CONFIRMATION_REPAIRED_CORE_CHANGED"):
        runner.verify_repaired_core(ex.REPOSITORY)
    original = c.sha256_file

    def wrong(path: Path) -> str:
        return "0" * 64 if path.name == "s10_query_families.py" else original(path)

    monkeypatch.setattr(c, "sha256_file", wrong)
    with pytest.raises(c.Stage10Error, match="CONFIRMATION_REPAIRED_CORE_CHANGED"):
        runner.verify_repaired_core(ex.REPOSITORY)


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_confirmation_observers_restore_on_error_and_never_log_values(
    synthetic_inputs: Any, tmp_path: Path, capsys: Any
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "observers", b"s" * 32)
    original = (cx.encoded, ops.TimedConnection.execute, c.identity)
    try:
        with pytest.raises(ValueError, match="invented interruption"):
            with telemetry.instrument(work):
                work.prepare()
                assert work.progress.counts["parser_certificate_preparation_calls"] == 1
                runner.reset_measurement(work, "observed")
                rows = [
                    f.generate(ctx, SyntheticTransform()) for ctx in work.contexts()
                ]
                assert len(rows) == 4
                frozen = work.progress.snapshot()
                work.progress.record(announce=True)
                raise ValueError("invented interruption")
        assert (cx.encoded, ops.TimedConnection.execute, c.identity) == original
        runner.reset_measurement(work, "unobserved")
        assert [
            f.generate(ctx, SyntheticTransform()) for ctx in work.contexts()
        ] == rows
        assert frozen["counts"]["contexts_loaded"] == 4
        assert frozen["counts"]["registry_encode_count"] == 3
        output = capsys.readouterr()
        for value in ("α road", "unit 5", "invented interruption", "SELECT * FROM"):
            assert value not in output.out + output.err
    finally:
        work.close()


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_exact_duckdb_setup_sequence_repeat_close_and_rollback(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    # This deliberately tests the supported cluster version, not a skipped
    # dependency reproduction or an alternate SQL implementation.
    assert duckdb.__version__ == "1.5.5"
    real_execute = ops.TimedConnection.execute
    queries: list[str] = []

    def trace(self: Any, query: str, parameters: Any = None) -> Any:
        queries.append(query.upper())
        return real_execute(self, query, parameters)

    monkeypatch.setattr(ops.TimedConnection, "execute", trace)
    fingerprints = []
    for ordinal in range(2):
        work = cx.ContextWorkspace(
            synthetic_inputs, tmp_path / f"clean-{ordinal}", b"s" * 32
        )
        try:
            work.prepare()
            original = work.db.execute(
                "SELECT * FROM stage10_context_keys ORDER BY query_context_id"
            ).fetchall()
            # Include unselected invented identities so prefix filtering is tested.
            excluded = tuple([b"x" * 32, *original[0][1:]])
            work.db.execute(
                "INSERT INTO stage10_context_keys VALUES (?, ?, ?, ?, ?, ?)", excluded
            )
            all_rows = work.db.execute(
                "SELECT * FROM stage10_context_keys ORDER BY query_context_id"
            ).fetchall()
            indexes = work.db.execute(
                "SELECT index_name FROM duckdb_indexes() WHERE table_name='stage10_context_keys'"
            ).fetchall()
            assert indexes  # Reproduce the indexed table, not an unindexed stand-in.
            with pytest.raises(
                c.Stage10Error, match="CONFIRMATION_FIRST_SHARD_CHANGED"
            ):
                runner.prepare_replay_population(work, 5)
            assert (
                work.db.execute(
                    "SELECT * FROM stage10_context_keys ORDER BY query_context_id"
                ).fetchall()
                == all_rows
            )
            assert (
                work.db.execute(
                    "SELECT index_name FROM duckdb_indexes() WHERE table_name='stage10_context_keys'"
                ).fetchall()
                == indexes
            )
            assert (
                summary.scalar(
                    work.db,
                    "SELECT count(*) FROM information_schema.tables WHERE table_name='stage10_all_context_keys'",
                )
                == 0
            )
            report = runner.prepare_replay_population(work, 4)
            assert report["original_contexts"] == 5 and report["selected_contexts"] == 4
            assert (
                work.db.execute(
                    "SELECT * FROM stage10_context_keys ORDER BY query_context_id"
                ).fetchall()
                == original
            )
            assert (
                work.db.execute(
                    "SELECT * FROM stage10_all_context_keys ORDER BY query_context_id"
                ).fetchall()
                == all_rows
            )
            assert (
                summary.scalar(
                    work.db, "SELECT count(*) FROM stage10_generation_contexts"
                )
                == 4
            )
            assert work.db.execute(
                "SELECT index_name FROM duckdb_indexes() WHERE table_name='stage10_context_keys'"
            ).fetchall() == [("confirmation_context_key",)]
            fingerprints.append(report["selected_occurrences_sha256"])
        finally:
            work.close()
        assert not (work.root / "context.duckdb.wal").exists()
        with duckdb.connect(
            str(work.root / "context.duckdb"), read_only=True
        ) as reopened:
            assert (
                summary.scalar(reopened, "SELECT count(*) FROM stage10_context_keys")
                == 4
            )
    assert fingerprints[0] == fingerprints[1]
    assert not any("RENAME" in query for query in queries)
    final_create = (
        "CREATE TABLE STAGE10_CONTEXT_KEYS AS SELECT * FROM STAGE10_ALL_CONTEXT_KEYS"
    )
    final_index = "CREATE UNIQUE INDEX CONFIRMATION_CONTEXT_KEY ON STAGE10_CONTEXT_KEYS"
    assert next(i for i, q in enumerate(queries) if q.startswith(final_create)) < next(
        i for i, q in enumerate(queries) if q.startswith(final_index)
    )


def test_confirmation_guard_precedes_path_access(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(c, "require_runtime", lambda: pytest.fail("runtime reached"))
    with pytest.raises(Exception):
        runner.preflight("a" * 40, tmp_path / "invented")
    assert not list(tmp_path.iterdir())


def test_confirmation_cli_failure_never_prints_values(
    monkeypatch: Any, capsys: Any, tmp_path: Path
) -> None:
    import sys

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("invented private sentinel")

    monkeypatch.setattr(runner, "run", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        ["confirmation", "--execution-git-sha", "a" * 40, "--output", str(tmp_path)],
    )
    assert runner.main() == 1
    output = capsys.readouterr()
    assert "sentinel" not in output.out + output.err
    assert "DIAGNOSTIC_OPERATIONAL_FAILURE" in output.out


def test_sigterm_restores_handler_and_retains_failed_phase(tmp_path: Path) -> None:
    old = signal.getsignal(signal.SIGTERM)
    progress = ops.Progress(tmp_path / "progress")
    with pytest.raises(c.Stage10Error, match="STAGE10_TERMINATED"):
        with ops.termination_guard(), progress.measure("context_construction"):
            signal.raise_signal(signal.SIGTERM)
    assert signal.getsignal(signal.SIGTERM) == old
    progress.record()
    receipt = c.read_json(tmp_path / "progress/progress-000000.json")
    assert receipt["failed_phase"] == "context_construction"
    assert receipt["timings_inclusive"]["context_construction"]["calls"] == 1


@pytest.mark.parametrize("role", c.ROLES)
@pytest.mark.parametrize("country", ["DE", None])
def test_old_new_five_family_witness_and_cached_id(
    role: str, country: str | None, tmp_path: Path, monkeypatch: Any
) -> None:
    old = original_module("s10_query_families", tmp_path)
    ctx = context(tmp_path, role=role, country=country)
    expected = old.generate(ctx, SyntheticTransform())
    ctx = dataclasses.replace(ctx, progress=ops.Progress())
    original = c.context_id
    calls = 0

    def measured(*args: Any) -> bytes:
        nonlocal calls
        calls += 1
        return original(*args)

    monkeypatch.setattr(c, "context_id", measured)
    actual = f.generate(ctx, SyntheticTransform())
    assert expected == prior_scientific_projection(actual)
    assert calls == 1
    if country and role == "NATIVE":
        assert len(actual[0]) == 5
        assert ctx.progress.timings["icu_transform"]["calls"] == 1
        assert ctx.progress.timings["q5_alignment"]["calls"] == 1


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_historical_gate_repartition_and_full_resume(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    old = original_module("s10_query_contexts", tmp_path)
    old_family = original_module("s10_query_families", tmp_path)
    old.families = old_family
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "new", b"s" * 32)
    before = old.ContextWorkspace(synthetic_inputs, tmp_path / "old", b"s" * 32)
    work.prepare()
    before.prepare()
    diagnostic = tmp_path / "diagnostic"
    diagnostic.mkdir(mode=0o700)
    serial = diagnostic / "serializations"
    serial.mkdir(mode=0o700)
    selected = []
    try:
        for ordinal, ctx in enumerate(before.contexts()):
            selected.append(ctx.identifier)
            directory = serial / f"context-{ordinal:02}"
            directory.mkdir(mode=0o700)
            for name, rows in zip(
                c.RELATIONS, old_family.generate(ctx, SyntheticTransform()), strict=True
            ):
                writer = io.RelationWriter(directory / name, io.output_schema(name))
                for row in rows:
                    writer.append(row)
                writer.close()
        monkeypatch.setattr(runner, "GATE_COUNTS", (4, 24, 18))
        # The historical gate must reject corrected provenance. Keep its exact
        # comparison and scientific pin intact; exercise its original positive
        # path with the original generator only inside this synthetic test.
        with pytest.raises(c.Stage10Error, match="OLD_NEW_SCIENTIFIC_MISMATCH"):
            runner.compare_historical(work, SyntheticTransform(), diagnostic, selected)
        with monkeypatch.context() as historical_patch:
            historical_patch.setattr(f, "generate", old_family.generate)
            gate = runner.compare_historical(
                work, SyntheticTransform(), diagnostic, selected
            )
        assert gate["exact_rows_equal"] and gate["hypotheses"] == 18
        report: dict[str, Any] = {}
        identity_function = c.identity
        with telemetry.instrument(work):
            runner.replay_confirmations(
                work,
                SyntheticTransform(),
                "a" * 40,
                work.root,
                ops.Progress(),
                report,
                4,
                first_unit_size=1,
                second_unit_size=2,
            )
        assert c.identity is identity_function
        assert report["first"]["relations"] == report["repartition"]["relations"]
        assert report["first"]["relations"] == report["resume"]["relations"]
        assert report["first"]["contexts"] == 4
        assert report["resume"]["incomplete_unit_regenerated"]
        assert report["resume_fixture"]["completed_prior_units"] == 3
        assert report["resume_fixture"]["incomplete_prior_units"] == 1
        assert work.progress.counts["checkpoints_reused"] == 3
        assert work.progress.timings["family_generation"]["calls"] == 1
        for name in ("first", "repartition", "resume"):
            measured = report[name]["replay_measurement"]
            assert measured["counts"]["parser_certificate_preparation_calls"] == 0
            assert measured["counts"]["selector_sql_insertions"] == 0
            assert measured["counts"]["registry_encode_count"] == summary.scalar(
                work.db, "SELECT count(*) FROM stage10_registry"
            )
            assert measured["observations"]["wal_after_checkpoint_bytes"] == 0
            assert measured["timings_inclusive"]["identity_hashing"]["calls"] > 0
            assert report[name]["final_validation_elapsed_ns"] > 0
        assert (
            report["population_setup_measurement"]["counts"][
                "explicit_transaction_commits"
            ]
            == 1
        )
        windows = runner.throughput_windows(work.root / "first_progress")
        assert sum(w["contexts"] for w in windows) == 4
        # Changing one protected-gate row must be detected without printing it.
        monkeypatch.setattr(f, "generate", lambda *a: ([], []))
        with pytest.raises(c.Stage10Error, match="OLD_NEW_SCIENTIFIC_MISMATCH"):
            runner.compare_historical(work, SyntheticTransform(), diagnostic, selected)
    finally:
        work.close()
        before.close()

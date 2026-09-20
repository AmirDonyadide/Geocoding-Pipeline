"""Public/synthetic confirmation harness checks; never protected local input."""

from __future__ import annotations

import dataclasses
import signal
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing import stage10_repair_confirmation as runner
from safe_geocoding_pipeline.preprocessing.stages import s10_query_checkpoints as units
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_performance_repair import COLLIDING, original_module
from test_stage10_query_families import SyntheticTransform, context


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
    assert expected == actual
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
        gate = runner.compare_historical(
            work, SyntheticTransform(), diagnostic, selected
        )
        assert gate["exact_rows_equal"] and gate["hypotheses"] == 18
        records = []
        for label, size, resume in (
            ("first", 1, None),
            ("repartition", 2, None),
            ("resume", 1, work.root / "first/0"),
        ):
            runner.reset_measurement(work, label + "_progress")
            parent = work.root / label
            parent.mkdir(mode=0o700)
            record = units.generate_prefix(
                work,
                SyntheticTransform(),
                "a" * 40,
                "0",
                output_parent=parent,
                resume=resume,
                unit_contexts=size,
            )
            runner.validate_pass(work, parent / "0", record, "a" * 40, 4)
            records.append(runner.relation_identity(record))
            assert records[-1] == records[0]
        assert work.progress.counts["checkpoints_reused"] == 4
        windows = runner.throughput_windows(work.root / "first_progress")
        assert sum(w["contexts"] for w in windows) == 4
        # Changing one protected-gate row must be detected without printing it.
        monkeypatch.setattr(f, "generate", lambda *a: ([], []))
        with pytest.raises(c.Stage10Error, match="OLD_NEW_SCIENTIFIC_MISMATCH"):
            runner.compare_historical(work, SyntheticTransform(), diagnostic, selected)
    finally:
        work.close()
        before.close()

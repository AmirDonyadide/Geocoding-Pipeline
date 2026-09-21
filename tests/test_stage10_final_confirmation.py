"""Final confirmation executes its actual setup/generation/adoption/tail sequence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing import stage10_final_confirmation as runner
from safe_geocoding_pipeline.preprocessing import (
    stage10_confirmation_observability as telemetry,
)
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as ex
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_performance_repair import COLLIDING
from test_stage10_query_families import SyntheticTransform


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_final_confirmation_sequence_adopts_all_then_rebuilds_only_tail(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    output = tmp_path / "reports"
    output.mkdir(mode=0o700)
    progress = ops.Progress(output / "progress")
    report: dict[str, Any] = {}
    try:
        with telemetry.instrument(work):
            work.prepare()
            runner.replay_confirmations(
                work,
                SyntheticTransform(),
                "a" * 40,
                output,
                progress,
                report,
                4,
                unit_size=1,
            )
        assert report["first"]["contexts"] == 4
        assert report["first"]["checkpoints"]["completed_units"] == 4
        assert report["adoption"]["adopted_units"] == 4
        assert report["adoption"]["regenerated_contexts"] == 0
        assert report["partial_tail"]["adopted_units"] == 3
        assert report["partial_tail"]["regenerated_contexts"] == 1
        assert (
            report["first"]["relations"]
            == report["adoption"]["relations"]
            == report["partial_tail"]["relations"]
        )
        assert (
            report["first"]["replay_measurement"]["counts"]["registry_encode_count"]
            == 0
        )
        assert (
            report["adoption"]["replay_measurement"]["timings_inclusive"].get(
                "certificate"
            )
            is None
        )
        assert (
            report["adoption"]["replay_measurement"]["timings_inclusive"][
                "database_execute"
            ]["calls"]
            == 3 * 4 + 1
        )
        assert len(list(output.glob("*_pass.json"))) == 3
    finally:
        work.close()


def test_scientific_core_pin_and_sql_bound_fail_closed(monkeypatch: Any) -> None:
    runner.verify_repaired_core(ex.REPOSITORY)
    original = c.sha256_file
    monkeypatch.setattr(
        c,
        "sha256_file",
        lambda p: "0" * 64 if p.name == "s10_query_families.py" else original(p),
    )
    with pytest.raises(c.Stage10Error, match="SCIENTIFIC_CORE_CHANGED"):
        runner.verify_repaired_core(ex.REPOSITORY)
    with pytest.raises(c.Stage10Error, match="FINE_GRAINED"):
        runner.generation_sql_bound(
            {"sql_categories": {"OBJECT_LOOKUP": {"calls": 1}}}, 1, 1
        )
    with pytest.raises(c.Stage10Error, match="SQL_BATCH_BOUND"):
        runner.generation_sql_bound(
            {
                "sql_categories": {},
                "timings_inclusive": {"database_execute": {"calls": 999}},
            },
            1,
            1,
        )

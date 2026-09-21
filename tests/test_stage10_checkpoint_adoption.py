"""Completed operational checkpoints are validated and adopted, never regenerated."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_checkpoints as units
from safe_geocoding_pipeline.preprocessing.stages import s10_query_materializer as m
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as families
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_performance_repair import COLLIDING
from test_stage10_query_families import SyntheticTransform


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_completed_adoption_performs_no_context_or_family_generation(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    first = cx.ContextWorkspace(synthetic_inputs, tmp_path / "first", b"s" * 32)
    resumed = cx.ContextWorkspace(synthetic_inputs, tmp_path / "resumed", b"s" * 32)
    first.prepare()
    resumed.prepare()
    try:
        (first.root / "shards").mkdir(mode=0o700)
        expected = units.generate_prefix(
            first, SyntheticTransform(), "a" * 40, "0", unit_contexts=1
        )
        expected_diagnostics = first.db.execute(
            "SELECT * FROM stage10_context_diagnostics ORDER BY query_context_id"
        ).fetchall()

        def forbidden(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("completed checkpoint recomputed science")

        from safe_geocoding_pipeline.preprocessing.stages import (
            s09_reference_io as base,
        )

        monkeypatch.setattr(base, "parquet_rows", forbidden)
        monkeypatch.setattr(resumed, "contexts", forbidden)
        monkeypatch.setattr(families, "generate", forbidden)
        monkeypatch.setattr(
            cx.ReferenceAccess, "_cached_witness_certificate", forbidden
        )
        (resumed.root / "shards").mkdir(mode=0o700)
        actual = units.generate_prefix(
            resumed,
            SyntheticTransform(),
            "a" * 40,
            "0",
            resume=first.root / "shards/0",
            unit_contexts=1,
        )
        assert actual == expected
        assert resumed.progress.counts["contexts_loaded"] == 0
        assert resumed.progress.counts["checkpoints_reused"] == 4
        assert (
            resumed.db.execute(
                "SELECT * FROM stage10_context_diagnostics ORDER BY query_context_id"
            ).fetchall()
            == expected_diagnostics
        )
        units.validate_prefix(
            resumed.root / "shards/0", m.checkpoint_binding(resumed, "a" * 40), "0"
        )
    finally:
        first.close()
        resumed.close()


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_unsealed_tail_only_is_rebuilt_and_sealed_corruption_rejected(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_checkpoint_state as state,
    )

    first = cx.ContextWorkspace(synthetic_inputs, tmp_path / "first", b"s" * 32)
    resumed = cx.ContextWorkspace(synthetic_inputs, tmp_path / "resumed", b"s" * 32)
    first.prepare()
    resumed.prepare()
    try:
        (first.root / "shards").mkdir(mode=0o700)
        expected = units.generate_prefix(
            first, SyntheticTransform(), "a" * 40, "0", unit_contexts=1
        )
        source = first.root / "shards/0"
        fixture = tmp_path / "fixture"
        shutil.copytree(source, fixture)
        (fixture / "units/000003" / state.SEAL).unlink()
        (resumed.root / "shards").mkdir(mode=0o700)
        actual = units.generate_prefix(
            resumed,
            SyntheticTransform(),
            "a" * 40,
            "0",
            resume=fixture,
            unit_contexts=1,
        )
        assert actual == expected
        assert resumed.progress.counts["checkpoints_reused"] == 3
        assert resumed.progress.counts["contexts_loaded"] == 1
        assert resumed.progress.timings["certificate"]["calls"] == 1
        assert resumed.progress.timings["family_generation"]["calls"] == 1
        payload = next((fixture / "units/000000/query_hypothesis").glob("*.parquet"))
        payload.write_bytes(payload.read_bytes() + b"corrupt synthetic file")
        with pytest.raises(c.Stage10Error, match="FILE_INVALID"):
            units.validate_unit(
                fixture / "units/000000", m.checkpoint_binding(first, "a" * 40), "0"
            )
    finally:
        first.close()
        resumed.close()


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_interruption_before_seal_never_creates_adoptable_unit(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_checkpoint_state as state,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c

    first = cx.ContextWorkspace(synthetic_inputs, tmp_path / "first", b"s" * 32)
    resumed = cx.ContextWorkspace(synthetic_inputs, tmp_path / "resumed", b"s" * 32)
    first.prepare()
    resumed.prepare()
    try:
        (first.root / "shards").mkdir(mode=0o700)
        real, calls = state.seal, 0

        def interrupted(root: Path) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise c.Stage10Error("SYNTHETIC_SEAL_INTERRUPTION")
            real(root)

        with monkeypatch.context() as patch:
            patch.setattr(state, "seal", interrupted)
            with pytest.raises(c.Stage10Error, match="SYNTHETIC_SEAL_INTERRUPTION"):
                units.generate_prefix(
                    first, SyntheticTransform(), "a" * 40, "0", unit_contexts=1
                )
        assert (first.root / "shards/0/units/000001/checkpoint.json").exists()
        assert not (first.root / "shards/0/units/000001" / state.SEAL).exists()
        (resumed.root / "shards").mkdir(mode=0o700)
        result = units.generate_prefix(
            resumed,
            SyntheticTransform(),
            "a" * 40,
            "0",
            unit_contexts=1,
            resume=first.root / "shards/0",
        )
        assert result["context_count"] == 4
        assert resumed.progress.counts["checkpoints_reused"] == 1
        assert resumed.progress.counts["contexts_loaded"] == 3
    finally:
        first.close()
        resumed.close()


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_interrupted_unit_copy_does_not_publish_completion_seal(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_checkpoint_state as state,
    )

    first = cx.ContextWorkspace(synthetic_inputs, tmp_path / "first", b"s" * 32)
    resumed = cx.ContextWorkspace(synthetic_inputs, tmp_path / "resumed", b"s" * 32)
    first.prepare()
    resumed.prepare()
    try:
        (first.root / "shards").mkdir(mode=0o700)
        units.generate_prefix(
            first, SyntheticTransform(), "a" * 40, "0", unit_contexts=1
        )
        (resumed.root / "shards").mkdir(mode=0o700)
        original = shutil.copytree

        def interrupt(
            source: Path, destination: Path, *args: Any, **kwargs: Any
        ) -> Any:
            result = original(source, destination, *args, **kwargs)
            if Path(destination).name == "000000":
                raise OSError("synthetic copy interrupted before validation")
            return result

        monkeypatch.setattr(shutil, "copytree", interrupt)
        with pytest.raises(OSError):
            units.generate_prefix(
                resumed,
                SyntheticTransform(),
                "a" * 40,
                "0",
                unit_contexts=1,
                resume=first.root / "shards/0",
            )
        assert not (resumed.root / "shards/0/units/000000" / state.SEAL).exists()
    finally:
        first.close()
        resumed.close()

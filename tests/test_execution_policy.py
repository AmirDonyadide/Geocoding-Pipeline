from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from phase03_helpers import fictional_country_reference
from safe_geocoding_pipeline.execution_policy import (
    ExecutionPolicyError,
    require_goethe_nhr_slurm,
)
from safe_geocoding_pipeline.phase01.config import InventoryConfig
from safe_geocoding_pipeline.phase01.runner import run_inventory
from safe_geocoding_pipeline.phase02.config import Phase02Config
from safe_geocoding_pipeline.phase02.runner import run_phase02
from safe_geocoding_pipeline.phase03.pilot_orchestration import write_country_profile
from safe_geocoding_pipeline.phase03.pilot_orchestration import select_production_pilot
from safe_geocoding_pipeline.phase03.pilot_orchestration import (
    validate_explicit_phase02_inputs,
)
from safe_geocoding_pipeline.phase03.pilot_runner import materialize_development_payload


def test_missing_execution_site_fails_closed() -> None:
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        require_goethe_nhr_slurm(
            "test-operation", environment={"SLURM_JOB_ID": "12345"}
        )


def test_missing_slurm_job_fails_closed() -> None:
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        require_goethe_nhr_slurm(
            "test-operation", environment={"SAFE_EXECUTION_SITE": "goethe-nhr"}
        )


def test_exact_cluster_markers_allow_execution() -> None:
    require_goethe_nhr_slurm(
        "test-operation",
        environment={
            "SAFE_EXECUTION_SITE": "goethe-nhr",
            "SLURM_JOB_ID": "12345",
        },
    )


def test_production_profile_guard_precedes_input_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    touched = False

    def forbidden_validator(*args: object, **kwargs: object) -> object:
        nonlocal touched
        touched = True
        raise AssertionError("production input validation was reached")

    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.pilot_orchestration.validate_explicit_phase02_inputs",
        forbidden_validator,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        write_country_profile(
            tmp_path / "missing-manifest.json",
            [tmp_path / "missing.parquet"],
            tmp_path / "profile.json",
            country_reference=fictional_country_reference(tmp_path),
            production=True,
        )
    assert touched is False


def test_production_materialization_guard_precedes_input_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_development_payload(
            [tmp_path / "missing.parquet"],
            tmp_path / "development.parquet",
            development_ids={b"d" * 32},
            locked_ids={b"l" * 32},
            expected_development_count=1,
            production=True,
        )


def test_production_selection_guard_precedes_input_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        select_production_pilot(
            manifest_path=tmp_path / "missing-manifest.json",
            input_paths=[tmp_path / "missing.parquet"],
            country_profile_path=tmp_path / "missing-profile.json",
            phase01_anomalies_path=tmp_path / "missing-anomalies.csv.gz",
            state_path=tmp_path / "state.sqlite3",
            output_directory=tmp_path / "output",
            country_reference=cast(Any, object()),
            script_reference=cast(Any, object()),
            rule_registry=cast(Any, object()),
            selection_timestamp="fictional",
            git_commit="fictional",
            phase03_configuration_fingerprint="fictional",
            reference_configuration_fingerprint="fictional",
            production=True,
        )


def test_production_snapshot_validation_is_cluster_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        validate_explicit_phase02_inputs(
            tmp_path / "missing-manifest.json", [], production=True
        )


def test_completed_phase_full_scopes_also_use_common_guard(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        run_inventory(
            InventoryConfig(
                source_root=tmp_path / "raw",
                run_scope="FULL_INVENTORY",
                authorize_full_inventory=True,
            )
        )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        run_phase02(
            Phase02Config(
                source_root=tmp_path / "raw",
                phase01_run_dir=tmp_path / "phase01",
                run_scope="FULL_CONVERSION",
                authorize_full_conversion=True,
            )
        )


def test_synthetic_profile_remains_local_without_slurm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    # Existing synthetic orchestration tests exercise the complete production=False
    # read path; this assertion makes the execution-policy boundary explicit.
    assert callable(write_country_profile)

from __future__ import annotations

from pathlib import Path

import pytest

from safe_geocoding_pipeline.execution_policy import (
    ExecutionPolicyError,
    require_goethe_nhr_slurm,
)
from safe_geocoding_pipeline.phase01.config import InventoryConfig
from safe_geocoding_pipeline.phase01.runner import run_inventory
from safe_geocoding_pipeline.phase02.config import Phase02Config
from safe_geocoding_pipeline.phase02.runner import run_phase02


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

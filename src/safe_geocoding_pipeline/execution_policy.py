from __future__ import annotations

import os
from collections.abc import Mapping


HEAVY_PROCESS_CLUSTER_REQUIRED = "HEAVY_PROCESS_CLUSTER_REQUIRED"
APPROVED_EXECUTION_SITE = "goethe-nhr"


class ExecutionPolicyError(RuntimeError):
    """Fail-closed execution-site policy error without data-bearing details."""

    def __init__(self, operation: str) -> None:
        self.code = HEAVY_PROCESS_CLUSTER_REQUIRED
        self.operation = operation
        super().__init__(
            f"{self.code}: This operation is production-scale and must run "
            "through SLURM on Goethe-NHR."
        )


def require_goethe_nhr_slurm(
    operation: str, *, environment: Mapping[str, str] | None = None
) -> None:
    """Require the two independent markers for a production-heavy operation.

    Production callers invoke this before opening production inputs. Synthetic
    callers must use their explicit non-production pathways instead of forging
    production environment markers.
    """

    values = os.environ if environment is None else environment
    site = values.get("SAFE_EXECUTION_SITE", "").strip()
    slurm_job_id = values.get("SLURM_JOB_ID", "").strip()
    if site != APPROVED_EXECUTION_SITE or not slurm_job_id:
        raise ExecutionPolicyError(operation)

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.stage07 import (
    EXPECTED_STAGE06_REVIEW_MANIFEST_SHA256,
    Stage07ReviewConfig,
    Stage07ReviewError,
    materialize_stage07_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize Stage 7 review evidence.")
    parser.add_argument("--stage05", required=True, type=Path)
    parser.add_argument("--stage06", required=True, type=Path)
    parser.add_argument("--stage06-review", required=True, type=Path)
    parser.add_argument("--stage07", required=True, type=Path)
    parser.add_argument("--stage07-manifest", required=True)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args()
    try:
        require_goethe_nhr_slurm("stage07-development-review")
        outcome = materialize_stage07_review(
            Stage07ReviewConfig(
                stage05_output_directory=args.stage05,
                stage06_output_directory=args.stage06,
                stage06_review_directory=args.stage06_review,
                expected_stage06_review_manifest_sha256=EXPECTED_STAGE06_REVIEW_MANIFEST_SHA256,
                stage07_output_directory=args.stage07,
                expected_stage07_manifest_sha256=args.stage07_manifest,
                parser_bundle_directory=args.bundle,
                output_directory=args.output,
                execution_git_sha=args.execution_git_sha,
                operational_metadata={
                    "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
                    "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
                },
            )
        )
        print("status=STAGE_7_DEVELOPMENT_MACHINE_REVIEW_READY")
        print(f"stage07_review_manifest_sha256={outcome.manifest_sha256}")
        print(f"fixed500_rows={outcome.fixed_source_rows}")
        print(f"fixed500_occurrences={outcome.fixed_occurrences}")
        print(f"fixed500_unique_candidates={outcome.fixed_unique_candidates}")
        print(f"fixed500_mismatches={outcome.fixed_mismatches}")
        print(f"qualitative_candidates={outcome.qualitative_candidates}")
        print(f"qualitative_selection_fingerprint={outcome.qualitative_selection_fingerprint}")
    except (ExecutionPolicyError, Stage07ReviewError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

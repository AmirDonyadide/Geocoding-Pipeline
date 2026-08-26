from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .reporting.contracts import ReviewSubsetError
from .reporting.development import (
    DevelopmentReviewRunConfig,
    materialize_stage02_development_review,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize the fixed protected DEVELOPMENT review subset."
    )
    parser.add_argument("--benchmark-development-artifact", required=True, type=Path)
    parser.add_argument("--expected-benchmark-artifact-sha256", required=True)
    parser.add_argument("--benchmark-fingerprint", required=True)
    parser.add_argument("--stage02-output-directory", required=True, type=Path)
    parser.add_argument("--expected-stage02-manifest-sha256", required=True)
    parser.add_argument("--expected-stage02-logical-fingerprint", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = materialize_stage02_development_review(
            DevelopmentReviewRunConfig(
                benchmark_development_artifact=args.benchmark_development_artifact,
                expected_benchmark_artifact_sha256=(
                    args.expected_benchmark_artifact_sha256
                ),
                benchmark_fingerprint=args.benchmark_fingerprint,
                stage02_output_directory=args.stage02_output_directory,
                expected_stage02_manifest_sha256=(
                    args.expected_stage02_manifest_sha256
                ),
                expected_stage02_logical_fingerprint=(
                    args.expected_stage02_logical_fingerprint
                ),
                output_directory=args.output_directory,
                execution_git_sha=args.execution_git_sha,
                production=True,
                operational_metadata={
                    "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
                    "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
                },
            )
        )
    except (ReviewSubsetError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=DEVELOPMENT_REVIEW_SUBSET_V1_MATERIALIZED")
    print(f"selected_rows={outcome.selected_row_count}")
    print(f"duplicate_identities={outcome.duplicate_identity_count}")
    print(f"source_files_represented={outcome.source_files_represented}")
    print(f"review_subset_fingerprint={outcome.review_subset_fingerprint}")
    print(f"review_artifact_sha256={outcome.review_artifact_sha256}")
    print(f"review_manifest_sha256={outcome.manifest_sha256}")
    print(f"quota_shortfall_category_count={outcome.quota_shortfall_category_count}")
    print(f"quota_shortfall_total={outcome.quota_shortfall_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .benchmark_runner import BenchmarkRunConfig, materialize_benchmark_sample
from .benchmark_sample import BenchmarkValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize the fixed protected Benchmark Sample V1."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--population-scope-file", required=True, type=Path)
    parser.add_argument("--expected-population-scope-sha256", required=True)
    parser.add_argument("--expected-source-count", required=True, type=int)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--adopting-git-commit", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = materialize_benchmark_sample(
            BenchmarkRunConfig(
                source_root=args.source_root,
                population_scope_file=args.population_scope_file,
                expected_population_scope_sha256=(
                    args.expected_population_scope_sha256
                ),
                expected_source_count=args.expected_source_count,
                output_directory=args.output_directory,
                adopting_git_commit=args.adopting_git_commit,
                production=True,
                operational_metadata={
                    "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
                    "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
                },
            )
        )
    except (BenchmarkValidationError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=BENCHMARK_SAMPLE_V1_ACCEPTED")
    print(f"source_files={outcome.source_file_count}")
    print(f"total_source_rows={outcome.total_source_rows}")
    print(f"development_rows={outcome.development_rows}")
    print(f"holdout_rows={outcome.holdout_rows}")
    print("development_holdout_overlap=0")
    print("duplicate_selected_identities=0")
    print(f"benchmark_fingerprint={outcome.benchmark_fingerprint}")
    print(f"benchmark_manifest_sha256={outcome.manifest_sha256}")
    print("holdout_raw_values_displayed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

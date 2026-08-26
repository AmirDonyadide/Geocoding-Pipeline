from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.contracts import ReviewSubsetError
from .reporting.stage03 import (
    Stage03ReviewRunConfig,
    materialize_stage03_development_review,
)
from .stages.s02_harmonization import STAGE02_CONTRACT_VERSION
from .stages.s03_cleaning import (
    Stage03InputBinding,
    Stage03RunConfig,
    Stage03ValidationError,
    materialize_stage03,
    validate_stage03_runtime,
    write_stage03_input_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and report Stage 3 safe text cleaning."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    binding = subparsers.add_parser(
        "create-input-binding",
        help="Create an owner-only SHA-pinned Stage 3 input binding.",
    )
    binding.add_argument("--output", required=True, type=Path)
    binding.add_argument("--stage02-logical-fingerprint", required=True)
    binding.add_argument("--stage02-schema-fingerprint", required=True)
    binding.add_argument("--stage02-manifest-sha256", required=True)
    binding.add_argument("--benchmark-fingerprint", required=True)
    binding.add_argument("--expected-row-count", required=True, type=int)

    materialize = subparsers.add_parser(
        "materialize", help="Create the complete protected Stage 3 DEVELOPMENT bundle."
    )
    materialize.add_argument("--stage02-output-directory", required=True, type=Path)
    materialize.add_argument("--input-binding", required=True, type=Path)
    materialize.add_argument("--expected-input-binding-sha256", required=True)
    materialize.add_argument("--output-directory", required=True, type=Path)
    materialize.add_argument("--execution-git-sha", required=True)
    materialize.add_argument("--batch-rows", type=int, default=2_048)

    review = subparsers.add_parser(
        "materialize-review",
        help="Create the fixed 500-row Stage 3 review and sanitized summary.",
    )
    review.add_argument("--stage03-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage03-manifest-sha256", required=True)
    review.add_argument(
        "--development-review-bundle-directory", required=True, type=Path
    )
    review.add_argument("--expected-development-review-manifest-sha256", required=True)
    review.add_argument("--expected-review-subset-fingerprint", required=True)
    review.add_argument("--expected-benchmark-fingerprint", required=True)
    review.add_argument("--expected-stage02-logical-fingerprint", required=True)
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--execution-git-sha", required=True)
    return parser


def _operational_metadata() -> dict[str, str]:
    return {
        "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def _create_binding(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage03-input-binding")
    validate_stage03_runtime()
    binding = Stage03InputBinding(
        upstream_contract_version=STAGE02_CONTRACT_VERSION,
        upstream_logical_identity_sha256=args.stage02_logical_fingerprint,
        upstream_schema_fingerprint=args.stage02_schema_fingerprint,
        upstream_manifest_sha256=args.stage02_manifest_sha256,
        input_benchmark_fingerprint=args.benchmark_fingerprint,
        expected_row_count=args.expected_row_count,
    )
    sha256 = write_stage03_input_binding(args.output, binding)
    print(f"stage03_input_binding_sha256={sha256}")


def _materialize(args: argparse.Namespace) -> None:
    outcome = materialize_stage03(
        Stage03RunConfig(
            stage02_output_directory=args.stage02_output_directory,
            input_binding_file=args.input_binding,
            expected_input_binding_sha256=args.expected_input_binding_sha256,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            batch_rows=args.batch_rows,
            production=True,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED")
    print(f"rows={outcome.row_count}")
    print(f"output_shards={outcome.output_shard_count}")
    print(f"stage03_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage03_schema_fingerprint={outcome.schema_fingerprint}")
    print(f"stage03_input_binding_sha256={outcome.input_binding_sha256}")
    print(f"stage03_manifest_sha256={outcome.manifest_sha256}")


def _materialize_review(args: argparse.Namespace) -> None:
    outcome = materialize_stage03_development_review(
        Stage03ReviewRunConfig(
            stage03_output_directory=args.stage03_output_directory,
            expected_stage03_manifest_sha256=args.expected_stage03_manifest_sha256,
            development_review_bundle_directory=(
                args.development_review_bundle_directory
            ),
            expected_development_review_manifest_sha256=(
                args.expected_development_review_manifest_sha256
            ),
            expected_review_subset_fingerprint=(
                args.expected_review_subset_fingerprint
            ),
            expected_benchmark_fingerprint=args.expected_benchmark_fingerprint,
            expected_stage02_logical_fingerprint=(
                args.expected_stage02_logical_fingerprint
            ),
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            production=True,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_3_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW")
    print(f"selected_rows={outcome.selected_row_count}")
    print(f"review_subset_fingerprint={outcome.review_subset_fingerprint}")
    print(f"review_artifact_sha256={outcome.review_artifact_sha256}")
    print(f"stage03_review_manifest_sha256={outcome.manifest_sha256}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create-input-binding":
            _create_binding(args)
        elif args.command == "materialize":
            _materialize(args)
        elif args.command == "materialize-review":
            _materialize_review(args)
        else:  # pragma: no cover - argparse owns the closed command vocabulary
            raise AssertionError("unknown Stage 3 command")
    except (
        Stage03ValidationError,
        ReviewSubsetError,
        ExecutionPolicyError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

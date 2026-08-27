from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.contracts import ReviewSubsetError
from .reporting.stage04 import (
    Stage04ReviewRunConfig,
    materialize_stage04_development_review,
)
from .stages.s03_cleaning import STAGE03_CONTRACT_VERSION, STAGE03_PROFILE_VERSION
from .stages.s04_lowercase import (
    Stage04InputBinding,
    Stage04RunConfig,
    Stage04ValidationError,
    materialize_stage04,
    validate_stage04_bundle,
    validate_stage04_input_binding,
    validate_stage04_runtime,
    write_stage04_input_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and report Stage 4 lowercase canonical forms."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    binding = subparsers.add_parser(
        "create-input-binding",
        help="Create an owner-only SHA-pinned Stage 4 input binding.",
    )
    binding.add_argument("--output", required=True, type=Path)
    binding.add_argument("--stage03-logical-fingerprint", required=True)
    binding.add_argument("--stage03-schema-fingerprint", required=True)
    binding.add_argument("--stage03-input-binding-sha256", required=True)
    binding.add_argument("--stage03-manifest-sha256", required=True)
    binding.add_argument("--stage03-ordered-identity-sha256", required=True)
    binding.add_argument("--benchmark-fingerprint", required=True)
    binding.add_argument("--expected-row-count", required=True, type=int)

    materialize = subparsers.add_parser(
        "materialize", help="Create the complete protected Stage 4 DEVELOPMENT bundle."
    )
    materialize.add_argument("--stage03-output-directory", required=True, type=Path)
    materialize.add_argument("--input-binding", required=True, type=Path)
    materialize.add_argument("--expected-input-binding-sha256", required=True)
    materialize.add_argument("--output-directory", required=True, type=Path)
    materialize.add_argument("--execution-git-sha", required=True)
    materialize.add_argument("--batch-rows", type=int, default=2_048)
    materialize.add_argument(
        "--target-batch-bytes", type=int, default=256 * 1024 * 1024
    )

    validate = subparsers.add_parser(
        "validate-published",
        help="Independently validate published Stage 4 against accepted Stage 3.",
    )
    validate.add_argument("--stage03-output-directory", required=True, type=Path)
    validate.add_argument("--stage04-output-directory", required=True, type=Path)
    validate.add_argument("--expected-stage04-manifest-sha256", required=True)

    review = subparsers.add_parser(
        "materialize-review",
        help="Create the fixed 500-row Stage 4 review and sanitized summary.",
    )
    review.add_argument("--stage04-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage04-manifest-sha256", required=True)
    review.add_argument(
        "--development-review-bundle-directory", required=True, type=Path
    )
    review.add_argument("--expected-development-review-manifest-sha256", required=True)
    review.add_argument("--expected-review-subset-fingerprint", required=True)
    review.add_argument("--expected-benchmark-fingerprint", required=True)
    review.add_argument("--expected-stage02-logical-fingerprint", required=True)
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--execution-git-sha", required=True)
    review.add_argument("--stage04-elapsed-milliseconds", required=True, type=int)
    review.add_argument("--stage04-user-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage04-system-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage04-max-rss-kib", required=True, type=int)
    return parser


def _operational_metadata() -> dict[str, str]:
    return {
        "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def _create_binding(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage04-input-binding")
    validate_stage04_runtime()
    binding = Stage04InputBinding(
        upstream_contract_version=STAGE03_CONTRACT_VERSION,
        upstream_profile_version=STAGE03_PROFILE_VERSION,
        upstream_logical_fingerprint=args.stage03_logical_fingerprint,
        upstream_schema_fingerprint=args.stage03_schema_fingerprint,
        upstream_input_binding_sha256=args.stage03_input_binding_sha256,
        upstream_manifest_sha256=args.stage03_manifest_sha256,
        upstream_ordered_identity_sha256=args.stage03_ordered_identity_sha256,
        input_benchmark_fingerprint=args.benchmark_fingerprint,
        expected_row_count=args.expected_row_count,
    )
    validate_stage04_input_binding(binding, authoritative_development=True)
    sha256 = write_stage04_input_binding(args.output, binding)
    print(f"stage04_input_binding_sha256={sha256}")


def _materialize(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    outcome = materialize_stage04(
        Stage04RunConfig(
            stage03_output_directory=args.stage03_output_directory,
            input_binding_file=args.input_binding,
            expected_input_binding_sha256=args.expected_input_binding_sha256,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            batch_rows=args.batch_rows,
            target_batch_bytes=args.target_batch_bytes,
            production=True,
            authoritative_development=True,
            operational_metadata=_operational_metadata(),
        )
    )
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    elapsed_milliseconds = round((time.perf_counter() - started) * 1_000)
    user_cpu_milliseconds = round(
        (usage_after.ru_utime - usage_before.ru_utime) * 1_000
    )
    system_cpu_milliseconds = round(
        (usage_after.ru_stime - usage_before.ru_stime) * 1_000
    )
    print("status=STAGE_4_DEVELOPMENT_CANDIDATE_MATERIALIZED")
    print(f"rows={outcome.row_count}")
    print(f"output_shards={outcome.output_shard_count}")
    print(f"stage04_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage04_schema_fingerprint={outcome.schema_fingerprint}")
    print(f"stage04_input_binding_sha256={outcome.input_binding_sha256}")
    print(f"stage04_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage04_ordered_identity_sha256={outcome.ordered_identity_sha256}")
    print(f"stage04_elapsed_milliseconds={elapsed_milliseconds}")
    print(f"stage04_user_cpu_milliseconds={user_cpu_milliseconds}")
    print(f"stage04_system_cpu_milliseconds={system_cpu_milliseconds}")
    print(f"stage04_max_rss_kib={usage_after.ru_maxrss}")


def _validate_published(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage04-published-validation")
    outcome = validate_stage04_bundle(
        args.stage04_output_directory,
        expected_manifest_sha256=args.expected_stage04_manifest_sha256,
        authoritative_development=True,
        stage03_output_directory=args.stage03_output_directory,
    )
    print("status=STAGE_4_PUBLISHED_VALIDATION_PASS")
    print(f"rows={outcome.row_count}")
    print(f"stage04_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage04_ordered_identity_sha256={outcome.ordered_identity_sha256}")


def _materialize_review(args: argparse.Namespace) -> None:
    outcome = materialize_stage04_development_review(
        Stage04ReviewRunConfig(
            stage04_output_directory=args.stage04_output_directory,
            expected_stage04_manifest_sha256=args.expected_stage04_manifest_sha256,
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
            performance_metrics={
                "ELAPSED_MILLISECONDS": args.stage04_elapsed_milliseconds,
                "USER_CPU_MILLISECONDS": args.stage04_user_cpu_milliseconds,
                "SYSTEM_CPU_MILLISECONDS": args.stage04_system_cpu_milliseconds,
                "MAX_RSS_KIB": args.stage04_max_rss_kib,
            },
            production=True,
            authoritative_development=True,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_4_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW")
    print(f"selected_rows={outcome.selected_row_count}")
    print(f"review_subset_fingerprint={outcome.review_subset_fingerprint}")
    print(f"review_artifact_sha256={outcome.review_artifact_sha256}")
    print(f"stage04_review_manifest_sha256={outcome.manifest_sha256}")
    print(f"questionable_count={outcome.qualitative_classifications['QUESTIONABLE']}")
    print(
        "semantic_damage_count="
        f"{outcome.qualitative_classifications['SEMANTIC_DAMAGE']}"
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create-input-binding":
            _create_binding(args)
        elif args.command == "materialize":
            _materialize(args)
        elif args.command == "validate-published":
            _validate_published(args)
        elif args.command == "materialize-review":
            _materialize_review(args)
        else:  # pragma: no cover - argparse owns the closed command vocabulary
            raise AssertionError("unknown Stage 4 command")
    except (
        Stage04ValidationError,
        ReviewSubsetError,
        ExecutionPolicyError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

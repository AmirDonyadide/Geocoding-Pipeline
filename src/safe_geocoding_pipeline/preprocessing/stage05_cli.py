from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.contracts import ReviewSubsetError
from .reporting.stage05 import (
    Stage05ReviewRunConfig,
    materialize_stage05_development_review,
)
from .stages.s04_lowercase import STAGE04_CONTRACT_VERSION, STAGE04_PROFILE_VERSION
from .stages.s05_reconstruction import (
    Stage05InputBinding,
    Stage05RunConfig,
    Stage05ValidationError,
    materialize_stage05,
    validate_stage05_bundle,
    validate_stage05_input_binding,
    validate_stage05_runtime,
    write_stage05_input_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and report Stage 5 address reconstruction."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    binding = subparsers.add_parser(
        "create-input-binding",
        help="Create an owner-only SHA-pinned Stage 5 input binding.",
    )
    binding.add_argument("--output", required=True, type=Path)
    binding.add_argument("--stage04-logical-fingerprint", required=True)
    binding.add_argument("--stage04-schema-fingerprint", required=True)
    binding.add_argument("--stage04-input-binding-sha256", required=True)
    binding.add_argument("--stage04-manifest-sha256", required=True)
    binding.add_argument("--stage04-ordered-identity-sha256", required=True)
    binding.add_argument("--benchmark-fingerprint", required=True)
    binding.add_argument("--expected-row-count", required=True, type=int)

    materialize = subparsers.add_parser(
        "materialize", help="Create the protected Stage 5 DEVELOPMENT bundle."
    )
    materialize.add_argument("--stage04-output-directory", required=True, type=Path)
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
        help="Independently validate published Stage 5 against accepted Stage 4.",
    )
    validate.add_argument("--stage04-output-directory", required=True, type=Path)
    validate.add_argument("--stage05-output-directory", required=True, type=Path)
    validate.add_argument("--expected-stage05-manifest-sha256", required=True)

    review = subparsers.add_parser(
        "materialize-review",
        help="Create the fixed 500-row Stage 5 review and sanitized summary.",
    )
    review.add_argument("--stage04-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage04-manifest-sha256", required=True)
    review.add_argument("--stage05-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage05-manifest-sha256", required=True)
    review.add_argument(
        "--development-review-bundle-directory", required=True, type=Path
    )
    review.add_argument("--expected-development-review-manifest-sha256", required=True)
    review.add_argument("--expected-review-subset-fingerprint", required=True)
    review.add_argument("--expected-benchmark-fingerprint", required=True)
    review.add_argument("--expected-stage02-logical-fingerprint", required=True)
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--execution-git-sha", required=True)
    review.add_argument("--stage05-elapsed-milliseconds", required=True, type=int)
    review.add_argument("--stage05-user-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage05-system-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage05-max-rss-kib", required=True, type=int)
    return parser


def _operational_metadata() -> dict[str, str]:
    return {
        "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def _create_binding(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage05-input-binding")
    validate_stage05_runtime()
    binding = Stage05InputBinding(
        upstream_contract_version=STAGE04_CONTRACT_VERSION,
        upstream_profile_version=STAGE04_PROFILE_VERSION,
        upstream_logical_fingerprint=args.stage04_logical_fingerprint,
        upstream_schema_fingerprint=args.stage04_schema_fingerprint,
        upstream_input_binding_sha256=args.stage04_input_binding_sha256,
        upstream_manifest_sha256=args.stage04_manifest_sha256,
        upstream_ordered_identity_sha256=args.stage04_ordered_identity_sha256,
        input_benchmark_fingerprint=args.benchmark_fingerprint,
        expected_row_count=args.expected_row_count,
    )
    validate_stage05_input_binding(binding, authoritative_development=True)
    sha256 = write_stage05_input_binding(args.output, binding)
    print(f"stage05_input_binding_sha256={sha256}")


def _materialize(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    outcome = materialize_stage05(
        Stage05RunConfig(
            stage04_output_directory=args.stage04_output_directory,
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
    print("status=STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED")
    print(f"rows={outcome.row_count}")
    print(f"output_shards={outcome.output_shard_count}")
    print(f"stage05_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage05_schema_fingerprint={outcome.schema_fingerprint}")
    print(f"stage05_input_binding_sha256={outcome.input_binding_sha256}")
    print(f"stage05_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage05_ordered_identity_sha256={outcome.ordered_identity_sha256}")
    print(f"stage05_elapsed_milliseconds={elapsed_milliseconds}")
    print(f"stage05_user_cpu_milliseconds={user_cpu_milliseconds}")
    print(f"stage05_system_cpu_milliseconds={system_cpu_milliseconds}")
    print(f"stage05_max_rss_kib={usage_after.ru_maxrss}")


def _validate_published(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage05-published-validation")
    outcome = validate_stage05_bundle(
        args.stage05_output_directory,
        expected_manifest_sha256=args.expected_stage05_manifest_sha256,
        authoritative_development=True,
        stage04_output_directory=args.stage04_output_directory,
    )
    print("status=STAGE_5_PUBLISHED_VALIDATION_PASS")
    print(f"rows={outcome.row_count}")
    print(f"stage05_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage05_ordered_identity_sha256={outcome.ordered_identity_sha256}")


def _materialize_review(args: argparse.Namespace) -> None:
    outcome = materialize_stage05_development_review(
        Stage05ReviewRunConfig(
            stage04_output_directory=args.stage04_output_directory,
            expected_stage04_manifest_sha256=args.expected_stage04_manifest_sha256,
            stage05_output_directory=args.stage05_output_directory,
            expected_stage05_manifest_sha256=args.expected_stage05_manifest_sha256,
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
                "ELAPSED_MILLISECONDS": args.stage05_elapsed_milliseconds,
                "USER_CPU_MILLISECONDS": args.stage05_user_cpu_milliseconds,
                "SYSTEM_CPU_MILLISECONDS": args.stage05_system_cpu_milliseconds,
                "MAX_RSS_KIB": args.stage05_max_rss_kib,
            },
            production=True,
            authoritative_development=True,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_5_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW")
    print(f"selected_rows={outcome.selected_row_count}")
    print(f"review_subset_fingerprint={outcome.review_subset_fingerprint}")
    print(f"review_artifact_sha256={outcome.review_artifact_sha256}")
    print(f"stage05_review_manifest_sha256={outcome.manifest_sha256}")
    questionable = sum(
        outcome.qualitative_classifications[name]
        for name in ("QUESTIONABLE_BOUNDARY", "QUESTIONABLE_ORDER")
    )
    print(f"questionable_count={questionable}")
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
            raise AssertionError("unknown Stage 5 command")
    except (
        Stage05ValidationError,
        ReviewSubsetError,
        ExecutionPolicyError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

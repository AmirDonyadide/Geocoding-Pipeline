from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.contracts import ReviewSubsetError
from .reporting.stage06 import (
    Stage06ReviewRunConfig,
    materialize_stage06_development_review,
)
from .stages.s05_reconstruction import STAGE05_CONTRACT_VERSION, STAGE05_PROFILE_VERSION
from .stages.s06_exact_deduplication import (
    Stage06InputBinding,
    Stage06RunConfig,
    Stage06ValidationError,
    materialize_stage06,
    validate_stage06_bundle,
    validate_stage06_input_binding,
    validate_stage06_runtime,
    write_stage06_input_binding,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and verify Stage 6 early exact deduplication."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    binding = subparsers.add_parser(
        "create-input-binding",
        help="Create the owner-only exact accepted Stage 5 input binding.",
    )
    binding.add_argument("--output", required=True, type=Path)
    binding.add_argument("--stage05-logical-fingerprint", required=True)
    binding.add_argument("--stage05-schema-fingerprint", required=True)
    binding.add_argument("--stage05-input-binding-sha256", required=True)
    binding.add_argument("--stage05-manifest-sha256", required=True)
    binding.add_argument("--stage05-ordered-identity-sha256", required=True)
    binding.add_argument("--benchmark-fingerprint", required=True)
    binding.add_argument("--fixed-500-fingerprint", required=True)
    binding.add_argument("--expected-row-count", required=True, type=int)

    materialize = subparsers.add_parser(
        "materialize", help="Create the protected Stage 6 DEVELOPMENT bundle."
    )
    materialize.add_argument("--stage05-output-directory", required=True, type=Path)
    materialize.add_argument("--input-binding", required=True, type=Path)
    materialize.add_argument("--expected-input-binding-sha256", required=True)
    materialize.add_argument("--output-directory", required=True, type=Path)
    materialize.add_argument("--execution-git-sha", required=True)
    materialize.add_argument("--batch-rows", type=int, default=2_048)
    materialize.add_argument(
        "--target-batch-bytes", type=int, default=256 * 1024 * 1024
    )
    materialize.add_argument("--registry-batch-rows", type=int, default=2_048)
    materialize.add_argument("--registry-shard-rows", type=int, default=1_000_000)
    materialize.add_argument("--hash-chunk-codepoints", type=int, default=1_048_576)
    materialize.add_argument("--duckdb-memory-limit", default="8GB")
    materialize.add_argument("--duckdb-threads", type=int, default=4)

    validate = subparsers.add_parser(
        "validate-published",
        help="Independently reopen accepted Stage 5 and published Stage 6.",
    )
    validate.add_argument("--stage05-output-directory", required=True, type=Path)
    validate.add_argument("--stage06-output-directory", required=True, type=Path)
    validate.add_argument("--expected-stage06-manifest-sha256", required=True)
    validate.add_argument("--batch-rows", type=int, default=2_048)
    validate.add_argument("--target-batch-bytes", type=int, default=256 * 1024 * 1024)
    validate.add_argument("--hash-chunk-codepoints", type=int, default=1_048_576)
    validate.add_argument("--duckdb-memory-limit", default="8GB")
    validate.add_argument("--duckdb-threads", type=int, default=4)

    review = subparsers.add_parser(
        "materialize-review",
        help="Create fixed-500 machine evidence and aggregate-only summaries.",
    )
    review.add_argument("--stage05-output-directory", required=True, type=Path)
    review.add_argument("--stage06-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage06-manifest-sha256", required=True)
    review.add_argument(
        "--development-review-bundle-directory", required=True, type=Path
    )
    review.add_argument("--expected-development-review-manifest-sha256", required=True)
    review.add_argument("--expected-review-subset-fingerprint", required=True)
    review.add_argument("--expected-benchmark-fingerprint", required=True)
    review.add_argument("--expected-stage02-logical-fingerprint", required=True)
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--execution-git-sha", required=True)
    review.add_argument("--stage06-elapsed-milliseconds", required=True, type=int)
    review.add_argument("--stage06-user-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage06-system-cpu-milliseconds", required=True, type=int)
    review.add_argument("--stage06-max-rss-kib", required=True, type=int)
    return parser


def _operational_metadata() -> dict[str, str]:
    return {
        "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def _create_binding(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage06-input-binding")
    validate_stage06_runtime()
    binding = Stage06InputBinding(
        upstream_contract_version=STAGE05_CONTRACT_VERSION,
        upstream_profile_version=STAGE05_PROFILE_VERSION,
        upstream_logical_fingerprint=args.stage05_logical_fingerprint,
        upstream_schema_fingerprint=args.stage05_schema_fingerprint,
        upstream_input_binding_sha256=args.stage05_input_binding_sha256,
        upstream_manifest_sha256=args.stage05_manifest_sha256,
        upstream_ordered_identity_sha256=args.stage05_ordered_identity_sha256,
        input_benchmark_fingerprint=args.benchmark_fingerprint,
        fixed_500_fingerprint=args.fixed_500_fingerprint,
        expected_row_count=args.expected_row_count,
    )
    validate_stage06_input_binding(binding, authoritative_development=True)
    sha256 = write_stage06_input_binding(args.output, binding)
    print(f"stage06_input_binding_sha256={sha256}")


def _materialize(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    outcome = materialize_stage06(
        Stage06RunConfig(
            stage05_output_directory=args.stage05_output_directory,
            input_binding_file=args.input_binding,
            expected_input_binding_sha256=args.expected_input_binding_sha256,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            production=True,
            authoritative_development=True,
            batch_rows=args.batch_rows,
            target_batch_bytes=args.target_batch_bytes,
            registry_batch_rows=args.registry_batch_rows,
            registry_shard_rows=args.registry_shard_rows,
            hash_chunk_codepoints=args.hash_chunk_codepoints,
            duckdb_memory_limit=args.duckdb_memory_limit,
            duckdb_threads=args.duckdb_threads,
            operational_metadata=_operational_metadata(),
        )
    )
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    elapsed = round((time.perf_counter() - started) * 1_000)
    print("status=STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED")
    print(f"rows={outcome.row_count}")
    print(f"unique_candidates={outcome.unique_candidate_count}")
    print(f"row_map_shards={outcome.row_map_shard_count}")
    print(f"registry_shards={outcome.registry_shard_count}")
    print(f"stage06_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage06_row_map_logical_sha256_v1={outcome.row_map_logical_sha256_v1}")
    print(f"stage06_registry_logical_sha256_v1={outcome.registry_logical_sha256_v1}")
    print(f"stage06_schema_fingerprint={outcome.schema_fingerprint}")
    print(f"stage06_input_binding_sha256={outcome.input_binding_sha256}")
    print(f"stage06_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage06_ordered_identity_sha256={outcome.ordered_identity_sha256}")
    for key, value in outcome.performance.items():
        print(f"stage06_{key.casefold()}={value}")
    print(
        f"stage06_publication_validation_milliseconds={outcome.publication_validation_milliseconds}"
    )
    print(f"stage06_elapsed_milliseconds={elapsed}")
    print(
        f"stage06_user_cpu_milliseconds={round((usage_after.ru_utime - usage_before.ru_utime) * 1_000)}"
    )
    print(
        f"stage06_system_cpu_milliseconds={round((usage_after.ru_stime - usage_before.ru_stime) * 1_000)}"
    )
    print(f"stage06_max_rss_kib={usage_after.ru_maxrss}")


def _validate_published(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage06-published-validation")
    outcome = validate_stage06_bundle(
        args.stage06_output_directory,
        expected_manifest_sha256=args.expected_stage06_manifest_sha256,
        stage05_output_directory=args.stage05_output_directory,
        authoritative_development=True,
        batch_rows=args.batch_rows,
        target_batch_bytes=args.target_batch_bytes,
        hash_chunk_codepoints=args.hash_chunk_codepoints,
        duckdb_memory_limit=args.duckdb_memory_limit,
        duckdb_threads=args.duckdb_threads,
    )
    print("status=STAGE_6_PUBLISHED_VALIDATION_PASS")
    print(f"rows={outcome.row_count}")
    print(f"unique_candidates={outcome.unique_candidate_count}")
    print(f"stage06_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage06_ordered_identity_sha256={outcome.ordered_identity_sha256}")


def _materialize_review(args: argparse.Namespace) -> None:
    outcome = materialize_stage06_development_review(
        Stage06ReviewRunConfig(
            stage05_output_directory=args.stage05_output_directory,
            stage06_output_directory=args.stage06_output_directory,
            expected_stage06_manifest_sha256=args.expected_stage06_manifest_sha256,
            development_review_bundle_directory=args.development_review_bundle_directory,
            expected_development_review_manifest_sha256=args.expected_development_review_manifest_sha256,
            expected_review_subset_fingerprint=args.expected_review_subset_fingerprint,
            expected_benchmark_fingerprint=args.expected_benchmark_fingerprint,
            expected_stage02_logical_fingerprint=args.expected_stage02_logical_fingerprint,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            performance_metrics={
                "ELAPSED_MILLISECONDS": args.stage06_elapsed_milliseconds,
                "USER_CPU_MILLISECONDS": args.stage06_user_cpu_milliseconds,
                "SYSTEM_CPU_MILLISECONDS": args.stage06_system_cpu_milliseconds,
                "MAX_RSS_KIB": args.stage06_max_rss_kib,
            },
            production=True,
            authoritative_development=True,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW")
    print(f"selected_rows={outcome.selected_row_count}")
    print(f"fixed500_mismatches={outcome.mismatch_count}")
    print(f"review_subset_fingerprint={outcome.review_subset_fingerprint}")
    print(f"review_artifact_sha256={outcome.review_artifact_sha256}")
    print(f"stage06_review_manifest_sha256={outcome.manifest_sha256}")


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
        else:  # pragma: no cover
            raise AssertionError("unknown Stage 6 command")
    except (Stage06ValidationError, ReviewSubsetError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

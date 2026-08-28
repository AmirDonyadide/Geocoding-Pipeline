from __future__ import annotations

import argparse
import os
import resource
import sys
import time
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .reporting.stage07 import (
    Stage07ReviewConfig,
    Stage07ReviewError,
    materialize_stage07_review,
)
from .stages.s06_exact_deduplication import Stage06ValidationError
from .stages.s07_parser_bundle import Stage07ParserBundleError, validate_parser_bundle
from .stages.s07_parsing import (
    Stage07RunConfig,
    Stage07ValidationError,
    accepted_stage07_input_binding,
    materialize_stage07,
    validate_stage07_bundle,
    write_stage07_input_binding,
)
from .stages.s07_supervised_parser import Stage07SupervisorError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize and independently validate Stage 7 parsing."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    binding = subparsers.add_parser("create-input-binding")
    binding.add_argument("--parser-bundle-directory", required=True, type=Path)
    binding.add_argument("--expected-parser-bundle-fingerprint", required=True)
    binding.add_argument("--output", required=True, type=Path)

    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--stage05-output-directory", required=True, type=Path)
    materialize.add_argument("--stage06-output-directory", required=True, type=Path)
    materialize.add_argument("--input-binding", required=True, type=Path)
    materialize.add_argument("--expected-input-binding-sha256", required=True)
    materialize.add_argument("--parser-bundle-directory", required=True, type=Path)
    materialize.add_argument("--expected-parser-bundle-fingerprint", required=True)
    materialize.add_argument("--output-directory", required=True, type=Path)
    materialize.add_argument("--execution-git-sha", required=True)
    materialize.add_argument("--input-batch-rows", type=int, default=64)
    materialize.add_argument("--output-batch-rows", type=int, default=64)
    materialize.add_argument(
        "--target-batch-bytes", type=int, default=128 * 1024 * 1024
    )
    materialize.add_argument("--output-shard-rows", type=int, default=4_096)

    validate = subparsers.add_parser("validate-published")
    validate.add_argument("--stage05-output-directory", required=True, type=Path)
    validate.add_argument("--stage06-output-directory", required=True, type=Path)
    validate.add_argument("--stage07-output-directory", required=True, type=Path)
    validate.add_argument("--expected-stage07-manifest-sha256", required=True)
    validate.add_argument("--parser-bundle-directory", required=True, type=Path)
    validate.add_argument("--batch-rows", type=int, default=64)
    validate.add_argument(
        "--target-batch-bytes", type=int, default=128 * 1024 * 1024
    )

    review = subparsers.add_parser("materialize-review")
    review.add_argument("--stage05-output-directory", required=True, type=Path)
    review.add_argument("--stage06-output-directory", required=True, type=Path)
    review.add_argument("--stage06-review-directory", required=True, type=Path)
    review.add_argument("--expected-stage06-review-manifest-sha256", required=True)
    review.add_argument("--stage07-output-directory", required=True, type=Path)
    review.add_argument("--expected-stage07-manifest-sha256", required=True)
    review.add_argument("--parser-bundle-directory", required=True, type=Path)
    review.add_argument("--output-directory", required=True, type=Path)
    review.add_argument("--execution-git-sha", required=True)
    return parser


def _operational_metadata() -> dict[str, str]:
    return {
        "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
    }


def _create_binding(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage07-input-binding")
    binding = accepted_stage07_input_binding()
    bundle = validate_parser_bundle(
        args.parser_bundle_directory,
        expected_parser_bundle_fingerprint=args.expected_parser_bundle_fingerprint,
    )
    if (
        bundle.parser_bundle_fingerprint != binding.parser_bundle_fingerprint
        or bundle.parser_model_data_fingerprint
        != binding.parser_model_data_fingerprint
        or bundle.pypostal_runtime_fingerprint != binding.pypostal_runtime_fingerprint
        or bundle.libpostal_shared_library_sha256
        != binding.libpostal_shared_library_sha256
        or bundle.manifest_sha256 != binding.parser_bundle_manifest_sha256
    ):
        raise Stage07ValidationError(
            "PARSER_BUNDLE_FINGERPRINT_MISMATCH",
            "The frozen parser bundle differs from the binding",
        )
    sha256 = write_stage07_input_binding(args.output, binding)
    print(f"stage07_input_binding_sha256={sha256}")


def _materialize(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    usage_before = resource.getrusage(resource.RUSAGE_SELF)
    outcome = materialize_stage07(
        Stage07RunConfig(
            stage05_output_directory=args.stage05_output_directory,
            stage06_output_directory=args.stage06_output_directory,
            input_binding_file=args.input_binding,
            expected_input_binding_sha256=args.expected_input_binding_sha256,
            parser_bundle_directory=args.parser_bundle_directory,
            expected_parser_bundle_fingerprint=args.expected_parser_bundle_fingerprint,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            input_batch_rows=args.input_batch_rows,
            output_batch_rows=args.output_batch_rows,
            target_batch_bytes=args.target_batch_bytes,
            output_shard_rows=args.output_shard_rows,
            operational_metadata=_operational_metadata(),
        )
    )
    usage_after = resource.getrusage(resource.RUSAGE_SELF)
    elapsed = round((time.perf_counter() - started) * 1_000)
    print("status=STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED")
    print(f"candidate_rows={outcome.candidate_count}")
    print(f"stage07_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage07_registry_logical_sha256_v1={outcome.registry_logical_sha256_v1}")
    print(f"stage07_schema_fingerprint={outcome.schema_fingerprint}")
    print(f"stage07_contract_fingerprint={outcome.contract_fingerprint}")
    print(f"stage07_input_binding_sha256={outcome.input_binding_sha256}")
    print(f"stage07_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage07_registry_shards={outcome.shard_count}")
    for key, value in outcome.performance.items():
        print(f"stage07_{key.casefold()}={value}")
    print(
        "stage07_publication_validation_milliseconds="
        f"{outcome.publication_validation_milliseconds}"
    )
    print(f"stage07_total_elapsed_milliseconds={elapsed}")
    print(
        "stage07_user_cpu_milliseconds="
        f"{round((usage_after.ru_utime - usage_before.ru_utime) * 1_000)}"
    )
    print(
        "stage07_system_cpu_milliseconds="
        f"{round((usage_after.ru_stime - usage_before.ru_stime) * 1_000)}"
    )
    print(f"stage07_parent_max_rss_kib={usage_after.ru_maxrss}")


def _validate(args: argparse.Namespace) -> None:
    require_goethe_nhr_slurm("stage07-published-validation")
    outcome = validate_stage07_bundle(
        args.stage07_output_directory,
        expected_manifest_sha256=args.expected_stage07_manifest_sha256,
        stage05_output_directory=args.stage05_output_directory,
        stage06_output_directory=args.stage06_output_directory,
        parser_bundle_directory=args.parser_bundle_directory,
        batch_rows=args.batch_rows,
        target_batch_bytes=args.target_batch_bytes,
    )
    print("status=STAGE_7_PUBLISHED_VALIDATION_PASS")
    print(f"candidate_rows={outcome.candidate_count}")
    print(f"stage07_manifest_sha256={outcome.manifest_sha256}")
    print(f"stage07_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")


def _materialize_review(args: argparse.Namespace) -> None:
    outcome = materialize_stage07_review(
        Stage07ReviewConfig(
            stage05_output_directory=args.stage05_output_directory,
            stage06_output_directory=args.stage06_output_directory,
            stage06_review_directory=args.stage06_review_directory,
            expected_stage06_review_manifest_sha256=(
                args.expected_stage06_review_manifest_sha256
            ),
            stage07_output_directory=args.stage07_output_directory,
            expected_stage07_manifest_sha256=args.expected_stage07_manifest_sha256,
            parser_bundle_directory=args.parser_bundle_directory,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            operational_metadata=_operational_metadata(),
        )
    )
    print("status=STAGE_7_DEVELOPMENT_MACHINE_REVIEW_READY")
    print(f"fixed500_source_rows={outcome.fixed_source_rows}")
    print(f"fixed500_occurrences={outcome.fixed_occurrences}")
    print(f"fixed500_unique_candidates={outcome.fixed_unique_candidates}")
    print(f"fixed500_mismatches={outcome.fixed_mismatches}")
    print(f"qualitative_candidates={outcome.qualitative_candidates}")
    print(
        "qualitative_selection_fingerprint="
        f"{outcome.qualitative_selection_fingerprint}"
    )
    print(f"stage07_review_manifest_sha256={outcome.manifest_sha256}")
    print(f"fixed500_seconds={outcome.fixed500_seconds}")
    print(f"qualitative_artifact_seconds={outcome.qualitative_seconds}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "create-input-binding":
            _create_binding(args)
        elif args.command == "materialize":
            _materialize(args)
        elif args.command == "validate-published":
            _validate(args)
        elif args.command == "materialize-review":
            _materialize_review(args)
        else:  # pragma: no cover
            raise AssertionError("unknown Stage 7 command")
    except (
        ExecutionPolicyError,
        Stage06ValidationError,
        Stage07ParserBundleError,
        Stage07ReviewError,
        Stage07SupervisorError,
        Stage07ValidationError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

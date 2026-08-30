from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages.s07_second_parser_bundle import (
    SecondParserBundleBuildIdentity,
    SecondParserBundleOutcome,
    Stage07SecondParserBundleError,
    publish_second_parser_bundle,
    validate_second_parser_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze or validate the public Stage 7 second-parser bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--staging-directory", required=True, type=Path)
    publish.add_argument("--output-directory", required=True, type=Path)
    publish.add_argument("--execution-git-sha", required=True)
    publish.add_argument("--compiler-identity", required=True)
    publish.add_argument("--glibc-identity", required=True)
    publish.add_argument("--python-configure-argument", action="append", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--output-directory", required=True, type=Path)
    validate.add_argument("--expected-second-parser-bundle-fingerprint", required=True)
    return parser


def _print_outcome(result: SecondParserBundleOutcome) -> None:
    print("status=STAGE07_SECOND_PARSER_BUNDLE_FROZEN")
    print(
        "stage07_second_parser_bundle_fingerprint="
        f"{result.second_parser_bundle_fingerprint}"
    )
    print(
        "stage07_second_parser_model_fingerprint="
        f"{result.second_parser_model_fingerprint}"
    )
    print(
        "stage07_second_parser_runtime_fingerprint="
        f"{result.second_parser_runtime_fingerprint}"
    )
    print(f"stage07_second_parser_manifest_sha256={result.manifest_sha256}")
    print(f"stage07_second_parser_bundle_artifacts={result.artifact_count}")
    print(f"stage07_second_parser_bundle_bytes={result.total_size_bytes}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        require_goethe_nhr_slurm("stage07-second-parser-bundle")
        if args.command == "publish":
            outcome = publish_second_parser_bundle(
                args.staging_directory,
                args.output_directory,
                build_identity=SecondParserBundleBuildIdentity(
                    execution_git_sha=args.execution_git_sha,
                    compiler_identity=args.compiler_identity,
                    glibc_identity=args.glibc_identity,
                    python_configure_arguments=tuple(args.python_configure_argument),
                ),
            )
        else:
            outcome = validate_second_parser_bundle(
                args.output_directory,
                expected_second_parser_bundle_fingerprint=(
                    args.expected_second_parser_bundle_fingerprint
                ),
            )
    except (Stage07SecondParserBundleError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    _print_outcome(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

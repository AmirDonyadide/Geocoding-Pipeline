from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages.s07_parser_bundle import (
    ParserBundleBuildIdentity,
    ParserBundleOutcome,
    Stage07ParserBundleError,
    publish_parser_bundle,
    validate_parser_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Freeze or validate the exact public Stage 7 parser bundle."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish = subparsers.add_parser(
        "publish", help="Fingerprint and atomically publish a newly built bundle."
    )
    publish.add_argument("--staging-directory", required=True, type=Path)
    publish.add_argument("--output-directory", required=True, type=Path)
    publish.add_argument("--execution-git-sha", required=True)
    publish.add_argument("--compiler-identity", required=True)
    publish.add_argument("--base-python-identity", required=True)
    publish.add_argument("--glibc-identity", required=True)

    validate = subparsers.add_parser(
        "validate", help="Rehash every artifact in a frozen parser bundle."
    )
    validate.add_argument("--output-directory", required=True, type=Path)
    validate.add_argument("--expected-parser-bundle-fingerprint", required=True)
    return parser


def _print_outcome(result: ParserBundleOutcome) -> None:
    print("status=STAGE07_PARSER_BUNDLE_FROZEN")
    print(f"stage07_parser_bundle_fingerprint={result.parser_bundle_fingerprint}")
    print(
        f"stage07_parser_model_data_fingerprint={result.parser_model_data_fingerprint}"
    )
    print(f"stage07_pypostal_runtime_fingerprint={result.pypostal_runtime_fingerprint}")
    print(
        "stage07_libpostal_shared_library_sha256="
        f"{result.libpostal_shared_library_sha256}"
    )
    print(f"stage07_parser_bundle_manifest_sha256={result.manifest_sha256}")
    print(f"stage07_parser_bundle_artifacts={result.artifact_count}")
    print(f"stage07_parser_bundle_bytes={result.total_size_bytes}")


def main() -> int:
    args = build_parser().parse_args()
    try:
        require_goethe_nhr_slurm("stage07-parser-bundle")
        if args.command == "publish":
            outcome = publish_parser_bundle(
                args.staging_directory,
                args.output_directory,
                build_identity=ParserBundleBuildIdentity(
                    execution_git_sha=args.execution_git_sha,
                    compiler_identity=args.compiler_identity,
                    base_python_identity=args.base_python_identity,
                    glibc_identity=args.glibc_identity,
                ),
            )
        else:
            outcome = validate_parser_bundle(
                args.output_directory,
                expected_parser_bundle_fingerprint=(
                    args.expected_parser_bundle_fingerprint
                ),
            )
    except (Stage07ParserBundleError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    _print_outcome(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

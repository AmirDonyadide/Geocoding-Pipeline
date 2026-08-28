from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s06_exact_deduplication import Stage06ValidationError
from .stages.s07_design_diagnostic import (
    Stage07DesignDiagnosticConfig,
    Stage07DesignDiagnosticError,
    run_stage07_design_diagnostic,
)
from .stages.s07_parser_bundle import Stage07ParserBundleError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create aggregate-only protected Stage 7 design evidence."
    )
    parser.add_argument("--stage05-output-directory", required=True, type=Path)
    parser.add_argument("--stage06-output-directory", required=True, type=Path)
    parser.add_argument("--expected-stage06-manifest-sha256", required=True)
    parser.add_argument("--stage06-review-directory", required=True, type=Path)
    parser.add_argument("--expected-stage06-review-manifest-sha256", required=True)
    parser.add_argument("--parser-bundle-directory", required=True, type=Path)
    parser.add_argument("--expected-parser-bundle-fingerprint", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--giant-timeout-seconds", type=int, default=900)
    parser.add_argument(
        "--giant-address-space-bytes", type=int, default=48 * 1024 * 1024 * 1024
    )
    parser.add_argument("--fresh-process-timeout-seconds", type=int, default=1_800)
    parser.add_argument("--duckdb-memory-limit", default="8GB")
    parser.add_argument("--duckdb-threads", type=int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = run_stage07_design_diagnostic(
            Stage07DesignDiagnosticConfig(
                stage05_output_directory=args.stage05_output_directory,
                stage06_output_directory=args.stage06_output_directory,
                expected_stage06_manifest_sha256=(
                    args.expected_stage06_manifest_sha256
                ),
                stage06_review_directory=args.stage06_review_directory,
                expected_stage06_review_manifest_sha256=(
                    args.expected_stage06_review_manifest_sha256
                ),
                parser_bundle_directory=args.parser_bundle_directory,
                expected_parser_bundle_fingerprint=(
                    args.expected_parser_bundle_fingerprint
                ),
                output_directory=args.output_directory,
                execution_git_sha=args.execution_git_sha,
                giant_timeout_seconds=args.giant_timeout_seconds,
                giant_address_space_bytes=args.giant_address_space_bytes,
                fresh_process_timeout_seconds=args.fresh_process_timeout_seconds,
                duckdb_memory_limit=args.duckdb_memory_limit,
                duckdb_threads=args.duckdb_threads,
                production=True,
                authoritative_development=True,
            )
        )
    except (
        Stage07DesignDiagnosticError,
        Stage07ParserBundleError,
        Stage06ValidationError,
        ExecutionPolicyError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_DESIGN_DIAGNOSTIC_COMPLETE")
    print(f"gate_result={outcome.gate_result}")
    print(f"diagnostic_candidates={outcome.diagnostic_candidate_count}")
    print(f"parser_bundle_fingerprint={outcome.parser_bundle_fingerprint}")
    print(f"diagnostic_sha256={outcome.diagnostic_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

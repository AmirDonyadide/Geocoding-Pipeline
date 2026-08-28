from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s06_exact_deduplication import Stage06ValidationError
from .stages.s07_parser_bundle import Stage07ParserBundleError
from .stages.s07_supervised_parser import Stage07SupervisorError
from .stages.s07_supervisor_diagnostic import (
    Stage07SupervisorDiagnosticConfig,
    Stage07SupervisorDiagnosticError,
    run_stage07_supervisor_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retest Stage 7 giant candidates through crash supervision."
    )
    parser.add_argument("--stage05-output-directory", required=True, type=Path)
    parser.add_argument("--stage06-output-directory", required=True, type=Path)
    parser.add_argument("--expected-stage06-manifest-sha256", required=True)
    parser.add_argument("--prior-diagnostic-directory", required=True, type=Path)
    parser.add_argument("--expected-prior-diagnostic-sha256", required=True)
    parser.add_argument("--parser-bundle-directory", required=True, type=Path)
    parser.add_argument("--expected-parser-bundle-fingerprint", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--duckdb-memory-limit", default="8GB")
    parser.add_argument("--duckdb-threads", type=int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = run_stage07_supervisor_diagnostic(
            Stage07SupervisorDiagnosticConfig(
                stage05_output_directory=args.stage05_output_directory,
                stage06_output_directory=args.stage06_output_directory,
                expected_stage06_manifest_sha256=(
                    args.expected_stage06_manifest_sha256
                ),
                prior_diagnostic_directory=args.prior_diagnostic_directory,
                expected_prior_diagnostic_sha256=(
                    args.expected_prior_diagnostic_sha256
                ),
                parser_bundle_directory=args.parser_bundle_directory,
                expected_parser_bundle_fingerprint=(
                    args.expected_parser_bundle_fingerprint
                ),
                output_directory=args.output_directory,
                execution_git_sha=args.execution_git_sha,
                duckdb_memory_limit=args.duckdb_memory_limit,
                duckdb_threads=args.duckdb_threads,
                production=True,
                authoritative_development=True,
            )
        )
    except (
        Stage07SupervisorDiagnosticError,
        Stage07SupervisorError,
        Stage07ParserBundleError,
        Stage06ValidationError,
        ExecutionPolicyError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_SUPERVISOR_DIAGNOSTIC_COMPLETE")
    print(f"gate_result={outcome.gate_result}")
    print(f"parser_bundle_fingerprint={outcome.parser_bundle_fingerprint}")
    print(f"diagnostic_sha256={outcome.diagnostic_sha256}")
    print(f"controlled_sha256={outcome.controlled_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

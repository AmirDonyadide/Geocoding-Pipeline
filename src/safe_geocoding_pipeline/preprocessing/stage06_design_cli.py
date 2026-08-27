from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .stages.s06_design_diagnostic import (
    Stage06DesignDiagnosticConfig,
    Stage06DesignDiagnosticError,
    run_stage06_design_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create aggregate-only Stage 6 exact-dedup design evidence."
    )
    parser.add_argument("--stage05-output-directory", required=True, type=Path)
    parser.add_argument("--expected-stage05-manifest-sha256", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--duckdb-memory-limit", default="8GB")
    parser.add_argument("--duckdb-threads", type=int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = run_stage06_design_diagnostic(
            Stage06DesignDiagnosticConfig(
                stage05_output_directory=args.stage05_output_directory,
                expected_stage05_manifest_sha256=(
                    args.expected_stage05_manifest_sha256
                ),
                output_directory=args.output_directory,
                execution_git_sha=args.execution_git_sha,
                duckdb_memory_limit=args.duckdb_memory_limit,
                duckdb_threads=args.duckdb_threads,
                production=True,
            )
        )
    except Stage06DesignDiagnosticError as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE06_DESIGN_DIAGNOSTIC_COMPLETE")
    print(f"rows={outcome.row_count}")
    print(f"candidate_occurrences={outcome.candidate_occurrence_count}")
    print(f"unique_candidates={outcome.unique_candidate_count}")
    print(f"diagnostic_sha256={outcome.diagnostic_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

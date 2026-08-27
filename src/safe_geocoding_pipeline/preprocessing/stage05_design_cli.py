from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .stages.s05_design_diagnostic import (
    Stage05DesignDiagnosticConfig,
    Stage05DesignDiagnosticError,
    run_stage05_design_diagnostic,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create aggregate-only Stage 5 reconstruction design evidence."
    )
    parser.add_argument("--stage04-output-directory", required=True, type=Path)
    parser.add_argument("--expected-stage04-manifest-sha256", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--batch-rows", type=int, default=2_048)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = run_stage05_design_diagnostic(
            Stage05DesignDiagnosticConfig(
                stage04_output_directory=args.stage04_output_directory,
                expected_stage04_manifest_sha256=(
                    args.expected_stage04_manifest_sha256
                ),
                output_directory=args.output_directory,
                execution_git_sha=args.execution_git_sha,
                batch_rows=args.batch_rows,
                production=True,
            )
        )
    except Stage05DesignDiagnosticError as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE05_DESIGN_DIAGNOSTIC_COMPLETE")
    print(f"rows={outcome.row_count}")
    print(f"diagnostic_sha256={outcome.diagnostic_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

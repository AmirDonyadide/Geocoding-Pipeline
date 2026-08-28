from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s07_quality_root_cause import (
    QualityDiagnosticConfig,
    Stage07QualityDiagnosticError,
    run_quality_root_cause_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the protected Stage 7 quality diagnostic."
    )
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--classifications", required=True, type=Path)
    parser.add_argument("--comments", required=True, type=Path)
    parser.add_argument("--stage07-registry", required=True, type=Path, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args()
    try:
        aggregate = run_quality_root_cause_diagnostic(
            QualityDiagnosticConfig(
                selection_path=args.selection,
                classifications_path=args.classifications,
                comments_path=args.comments,
                stage07_registry_paths=tuple(args.stage07_registry),
                output_directory=args.output,
                execution_git_sha=args.execution_git_sha,
            )
        )
    except (ExecutionPolicyError, Stage07QualityDiagnosticError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_QUALITY_ROOT_CAUSE_DIAGNOSTIC_COMPLETE")
    print("aggregate=" + json.dumps(aggregate, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

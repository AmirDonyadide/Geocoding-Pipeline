from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s07_context_provenance import Stage07ContextDiagnosticError
from .stages.s07_country_eligibility import Stage07CountryEligibilityError
from .stages.s07_country_eligibility_audit import (
    CountryEligibilityAuditConfig,
    Stage07CountryEligibilityAuditError,
    run_country_eligibility_audit,
)
from .stages.s07_parsing import Stage07ValidationError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit Stage 7 parser eligibility from trusted country provenance."
    )
    parser.add_argument("--stage06-output-directory", required=True, type=Path)
    parser.add_argument("--stage07-output-directory", required=True, type=Path)
    parser.add_argument("--stage07-manifest-sha256", required=True)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--classifications", required=True, type=Path)
    parser.add_argument("--eligibility-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args()
    try:
        aggregate = run_country_eligibility_audit(
            CountryEligibilityAuditConfig(
                stage06_output_directory=args.stage06_output_directory,
                stage07_output_directory=args.stage07_output_directory,
                selection_path=args.selection,
                classifications_path=args.classifications,
                eligibility_manifest_path=args.eligibility_manifest,
                output_directory=args.output,
                execution_git_sha=args.execution_git_sha,
                expected_stage07_manifest_sha256=args.stage07_manifest_sha256,
            )
        )
    except (
        ExecutionPolicyError,
        Stage07ContextDiagnosticError,
        Stage07CountryEligibilityError,
        Stage07CountryEligibilityAuditError,
        Stage07ValidationError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_COUNTRY_ELIGIBILITY_AUDIT_COMPLETE")
    print("aggregate=" + json.dumps(aggregate, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

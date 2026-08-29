from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s07_context_provenance import (
    ContextProvenanceConfig,
    Stage07ContextDiagnosticError,
    run_context_provenance_diagnostic,
)
from .stages.s07_parser_bundle import Stage07ParserBundleError


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit pinned parser context support and Stage 6 provenance."
    )
    parser.add_argument("--stage06-output-directory", required=True, type=Path)
    parser.add_argument("--parser-bundle-directory", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--classifications", required=True, type=Path)
    parser.add_argument("--pypostal-parser-source", required=True, type=Path)
    parser.add_argument("--libpostal-header-source", required=True, type=Path)
    parser.add_argument("--libpostal-address-parser-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execution-git-sha", required=True)
    args = parser.parse_args()
    try:
        aggregate = run_context_provenance_diagnostic(
            ContextProvenanceConfig(
                stage06_output_directory=args.stage06_output_directory,
                parser_bundle_directory=args.parser_bundle_directory,
                selection_path=args.selection,
                classifications_path=args.classifications,
                pypostal_parser_source=args.pypostal_parser_source,
                libpostal_header_source=args.libpostal_header_source,
                libpostal_address_parser_source=args.libpostal_address_parser_source,
                output_directory=args.output,
                execution_git_sha=args.execution_git_sha,
            )
        )
    except (
        ExecutionPolicyError,
        Stage07ContextDiagnosticError,
        Stage07ParserBundleError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_CONTEXT_PROVENANCE_DIAGNOSTIC_COMPLETE")
    print("aggregate=" + json.dumps(aggregate, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

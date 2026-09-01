"""CLI for the protected Stage 7 v2 readiness design audit."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .stages.s07_v2_readiness_audit import (
    ReadinessAuditConfig,
    run_v2_readiness_design_audit,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage06-fixed500", type=Path, required=True)
    parser.add_argument("--stage07-fixed500", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--classifications", type=Path, required=True)
    parser.add_argument("--root-cause", type=Path, required=True)
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--qualitative-html", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-git-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    aggregate = run_v2_readiness_design_audit(
        ReadinessAuditConfig(
            stage06_fixed500_path=args.stage06_fixed500,
            stage07_fixed500_path=args.stage07_fixed500,
            qualitative_selection_path=args.selection,
            classifications_path=args.classifications,
            root_cause_path=args.root_cause,
            eligibility_path=args.eligibility,
            qualitative_html_path=args.qualitative_html,
            output_directory=args.output,
            execution_git_sha=args.execution_git_sha,
        )
    )
    fixed = aggregate["fixed500"]
    discovery = aggregate["discovery"]
    assert isinstance(fixed, dict) and isinstance(discovery, dict)
    print("status=STAGE07_V2_READINESS_DESIGN_AUDIT_COMPLETE")
    print(f"fixed500_candidates={fixed['unique_candidates']}")
    print(f"fixed500_remaining_unreviewed={fixed['remaining_unreviewed_candidates']}")
    print(f"discovery_candidates={discovery['selected_candidates']}")
    print(f"clear_misparse_leaked_ready={discovery['clear_misparse_leaked_ready']}")
    print("semantic_input=existing_owner_only_qualitative_review_html")
    print("authoritative_registry_nested_scan=false")
    print("protected_values_printed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI for the machine-only Stage 7 v2 validation-selection freeze."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .stages.s07_v2_validation_selection import (
    ValidationSelectionConfig,
    run_validation_selection_freeze,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage06-fixed500", type=Path, required=True)
    parser.add_argument("--existing-selection", type=Path, required=True)
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--stage07-output-directory", type=Path, required=True)
    parser.add_argument("--stage07-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execution-git-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    aggregate = run_validation_selection_freeze(
        ValidationSelectionConfig(
            stage06_fixed500_path=args.stage06_fixed500,
            existing_selection_path=args.existing_selection,
            eligibility_path=args.eligibility,
            stage07_output_directory=args.stage07_output_directory,
            expected_stage07_manifest_sha256=args.stage07_manifest_sha256,
            output_directory=args.output,
            execution_git_sha=args.execution_git_sha,
        )
    )
    frame = aggregate["frame"]
    selection = aggregate["selection"]
    assert isinstance(frame, dict) and isinstance(selection, dict)
    print("status=STAGE07_V2_VALIDATION_SELECTION_FROZEN")
    print(f"frame_candidates={frame['candidates']}")
    print(f"readiness_counts={frame['readiness_counts']}")
    print(f"selected_candidates={selection['candidate_count']}")
    print(f"selection_fingerprint={selection['fingerprint']}")
    print("semantic_review_started=false")
    print("protected_values_printed=false")
    print("parser_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

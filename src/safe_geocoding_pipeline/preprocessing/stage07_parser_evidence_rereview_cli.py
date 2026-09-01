"""CLI for the independent Stage 7 evidence-only rereview replay."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .stages.s07_parser_evidence_rereview import (
    REVIEWED_CANDIDATE_SHA,
    RereviewConfig,
    Stage07IndependentRereviewError,
    run_independent_rereview,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently replay the published Stage 7 evidence-only artifact."
    )
    parser.add_argument("--stage06-root", type=Path, required=True)
    parser.add_argument("--stage07-v1-root", type=Path, required=True)
    parser.add_argument("--eligibility-artifact", type=Path, required=True)
    parser.add_argument("--eligibility-audit-manifest", type=Path, required=True)
    parser.add_argument("--stage07-v2-root", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--review-git-sha", required=True)
    parser.add_argument("--reviewed-candidate-sha", default=REVIEWED_CANDIDATE_SHA)
    parser.add_argument("--batch-rows", type=int, default=32)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        outcome = run_independent_rereview(
            RereviewConfig(
                stage06_root=args.stage06_root,
                stage07_v1_root=args.stage07_v1_root,
                eligibility_artifact=args.eligibility_artifact,
                eligibility_audit_manifest=args.eligibility_audit_manifest,
                stage07_v2_root=args.stage07_v2_root,
                source_root=args.source_root,
                output_directory=args.output_directory,
                review_git_sha=args.review_git_sha,
                reviewed_candidate_sha=args.reviewed_candidate_sha,
                batch_rows=args.batch_rows,
            )
        )
    except Stage07IndependentRereviewError as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_MACHINE_PASS")
    print(f"reviewed_candidate_sha={REVIEWED_CANDIDATE_SHA}")
    print(f"candidate_rows={outcome.candidate_count}")
    print(f"occurrence_map_back={outcome.occurrence_count}")
    print(f"evidence_sha256={outcome.evidence_sha256}")
    print(f"raw_preservation_digest={outcome.raw_preservation_digest}")
    print(f"warning_replay_digest={outcome.warning_replay_digest}")
    print("parser_calls=0")
    print("holdout_access=false")
    print("production_access=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

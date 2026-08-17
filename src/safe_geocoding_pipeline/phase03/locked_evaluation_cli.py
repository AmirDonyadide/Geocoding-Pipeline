from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..execution_policy import require_goethe_nhr_slurm
from .config import Phase03Config
from .constants import (
    LOCKED_EVALUATION_PROTOCOL_VERSION,
    PARSER_VERSION_V3_2,
)
from .locked_evaluation import (
    LockedReviewStore,
    build_locked_engines,
    export_completed_locked_labels,
    finalize_locked_evaluation,
    initialize_locked_review_workspace,
    materialize_locked_payload,
    prepare_locked_review_artifacts,
    protocol_summary,
    read_frozen_locked_identity_set,
    run_locked_review,
    score_completed_locked_review,
    transform_locked_pair_atomically,
    validate_locked_preflight,
    validate_preflight_report,
)
from .references import load_production_references
from .text import enforce_runtime_contract


def _current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safe-geocoding-phase03-locked-evaluation",
        description="Frozen, fail-closed Phase 3 LOCKED evaluation workflow",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("protocol-info")

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--phase02-manifest", type=Path, required=True)
    preflight.add_argument("--input-path", type=Path, action="append", required=True)
    preflight.add_argument("--locked-identities", type=Path, required=True)
    preflight.add_argument("--pilot-seal", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)
    preflight.add_argument("--workflow-git-commit", required=True)

    materialize = commands.add_parser("materialize")
    materialize.add_argument("--input-path", type=Path, action="append", required=True)
    materialize.add_argument("--locked-identities", type=Path, required=True)
    materialize.add_argument("--preflight-report", type=Path, required=True)
    materialize.add_argument("--workflow-git-commit", required=True)
    materialize.add_argument("--output", type=Path, required=True)

    transform = commands.add_parser("transform")
    transform.add_argument("--locked-payload", type=Path, required=True)
    transform.add_argument("--locked-identities", type=Path, required=True)
    transform.add_argument("--preflight-report", type=Path, required=True)
    transform.add_argument("--output-root", type=Path, required=True)
    transform.add_argument("--workflow-git-commit", required=True)

    prepare = commands.add_parser("prepare-review")
    prepare.add_argument("--locked-payload", type=Path, required=True)
    prepare.add_argument("--baseline-core", type=Path, required=True)
    prepare.add_argument("--baseline-evidence", type=Path, required=True)
    prepare.add_argument("--candidate-core", type=Path, required=True)
    prepare.add_argument("--candidate-evidence", type=Path, required=True)
    prepare.add_argument("--output-directory", type=Path, required=True)
    prepare.add_argument("--locked-evaluation-version", required=True)
    prepare.add_argument("--workflow-git-commit", required=True)

    initialize = commands.add_parser("initialize-review")
    initialize.add_argument("--protected-context", type=Path, required=True)
    initialize.add_argument("--protected-template", type=Path, required=True)
    initialize.add_argument("--input-manifest", type=Path, required=True)
    initialize.add_argument("--output-directory", type=Path, required=True)
    initialize.add_argument("--workflow-git-commit", required=True)

    progress = commands.add_parser("review-progress")
    progress.add_argument("--database", type=Path, required=True)

    review = commands.add_parser("review")
    review.add_argument("--database", type=Path, required=True)
    review.add_argument("--protected-context", type=Path, required=True)

    export = commands.add_parser("export-labels")
    export.add_argument("--reviewer-one-database", type=Path, required=True)
    export.add_argument("--reviewer-two-database", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    score = commands.add_parser("score")
    score.add_argument("--controlled-labels", type=Path, required=True)
    score.add_argument("--protected-context", type=Path, required=True)
    score.add_argument("--review-input-manifest", type=Path, required=True)
    score.add_argument("--machine-checks", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)

    finalize = commands.add_parser("finalize")
    finalize.add_argument("--attempt-directory", type=Path, required=True)
    finalize.add_argument("--final-directory", type=Path, required=True)
    finalize.add_argument("--score", type=Path, required=True)
    finalize.add_argument("--artifact", action="append", required=True)
    finalize.add_argument("--workflow-git-commit", required=True)
    return parser


def _print(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _require_commit(expected: str) -> None:
    if expected != _current_commit():
        raise ValueError("LOCKED workflow Git commit differs from checkout HEAD")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "protocol-info":
        _print(protocol_summary(locked_configuration_fingerprint=None))
        return 0
    enforce_runtime_contract()
    require_goethe_nhr_slurm(f"phase03-locked-evaluation-{args.command}")

    if args.command == "preflight":
        _require_commit(args.workflow_git_commit)
        _print(
            validate_locked_preflight(
                phase02_manifest_path=args.phase02_manifest,
                phase02_input_paths=args.input_path,
                locked_identities_path=args.locked_identities,
                pilot_seal_path=args.pilot_seal,
                output_path=args.output,
                workflow_git_commit=args.workflow_git_commit,
                production=True,
            )
        )
        return 0
    if args.command == "materialize":
        _require_commit(args.workflow_git_commit)
        validate_preflight_report(
            args.preflight_report, workflow_git_commit=args.workflow_git_commit
        )
        _metadata, identities = read_frozen_locked_identity_set(args.locked_identities)
        rows = materialize_locked_payload(
            args.input_path,
            args.output,
            locked_ids=set(identities),
            production=True,
        )
        _print({"status": "PASS", "locked_rows": rows, "output": str(args.output)})
        return 0
    if args.command == "transform":
        _require_commit(args.workflow_git_commit)
        validate_preflight_report(
            args.preflight_report, workflow_git_commit=args.workflow_git_commit
        )
        _metadata, identities = read_frozen_locked_identity_set(args.locked_identities)
        reference_config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
        country, scripts = load_production_references(
            expected_country_reference_id=reference_config.country_reference_version,
            expected_unicode_reference_id=reference_config.unicode_reference_version,
        )
        implementation = hashlib.sha256(args.workflow_git_commit.encode()).digest()
        baseline, candidate = build_locked_engines(
            implementation_fingerprint=implementation,
            country_reference=country,
            script_reference=scripts,
        )
        baseline_result, candidate_result = transform_locked_pair_atomically(
            args.locked_payload,
            args.output_root,
            baseline_engine=baseline,
            candidate_engine=candidate,
            metadata={
                "pilot_partition": "LOCKED_EVALUATION",
                "git_commit": args.workflow_git_commit,
                "candidate_commit": ("e78f52374c156477ce026e0d1dbb9755b85f5d82"),
                "locked_protocol_version": LOCKED_EVALUATION_PROTOCOL_VERSION,
            },
            expected_locked_ids=set(identities),
            production=True,
        )
        _print(
            {
                "status": "PASS",
                "locked_rows": baseline_result.core_rows,
                "baseline": asdict(baseline_result),
                "candidate": asdict(candidate_result),
                "locked_configuration_fingerprint": candidate.configuration_fingerprint.hex(),
            }
        )
        return 0
    if args.command == "prepare-review":
        _require_commit(args.workflow_git_commit)
        reference_config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
        _, scripts = load_production_references(
            expected_country_reference_id=reference_config.country_reference_version,
            expected_unicode_reference_id=reference_config.unicode_reference_version,
        )
        payload = prepare_locked_review_artifacts(
            locked_payload_path=args.locked_payload,
            baseline_core_path=args.baseline_core,
            baseline_evidence_path=args.baseline_evidence,
            candidate_core_path=args.candidate_core,
            candidate_evidence_path=args.candidate_evidence,
            output_directory=args.output_directory,
            locked_evaluation_version=args.locked_evaluation_version,
            script_reference=scripts,
            implementation_commit=args.workflow_git_commit,
            production=True,
        )
        _print(payload)
        return 0
    if args.command == "initialize-review":
        _require_commit(args.workflow_git_commit)
        first, second = initialize_locked_review_workspace(
            context_path=args.protected_context,
            template_path=args.protected_template,
            input_manifest_path=args.input_manifest,
            output_directory=args.output_directory,
            implementation_commit=args.workflow_git_commit,
        )
        _print(
            {
                "status": "INITIALIZED",
                "reviewer_one_database": str(first),
                "reviewer_two_database": str(second),
            }
        )
        return 0
    if args.command == "review-progress":
        with LockedReviewStore(args.database, readonly=True) as store:
            _print(store.summary())
        return 0
    if args.command == "review":
        run_locked_review(
            progress_database=args.database,
            context_path=args.protected_context,
        )
        return 0
    if args.command == "export-labels":
        output = export_completed_locked_labels(
            reviewer_one_database=args.reviewer_one_database,
            reviewer_two_database=args.reviewer_two_database,
            output_path=args.output,
        )
        _print({"status": "PASS", "output": str(output)})
        return 0
    if args.command == "score":
        machine_checks = json.loads(args.machine_checks.read_text(encoding="utf-8"))
        _print(
            score_completed_locked_review(
                controlled_labels_path=args.controlled_labels,
                context_path=args.protected_context,
                review_input_manifest_path=args.review_input_manifest,
                output_path=args.output,
                machine_checks=machine_checks,
            )
        )
        return 0
    if args.command == "finalize":
        _require_commit(args.workflow_git_commit)
        artifacts: dict[str, Path] = {}
        for value in args.artifact:
            name, separator, path = value.partition("=")
            if not separator or not name or name in artifacts:
                raise ValueError("--artifact must be a unique NAME=PATH value")
            artifacts[name] = Path(path)
        manifest, success = finalize_locked_evaluation(
            attempt_directory=args.attempt_directory,
            final_directory=args.final_directory,
            score_path=args.score,
            required_artifacts=artifacts,
            workflow_git_commit=args.workflow_git_commit,
        )
        _print(
            {"status": "PROMOTED", "manifest": str(manifest), "success": str(success)}
        )
        return 0
    raise AssertionError("unreachable LOCKED evaluation command")


if __name__ == "__main__":
    raise SystemExit(main())

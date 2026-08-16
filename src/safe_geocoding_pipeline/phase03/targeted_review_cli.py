from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..execution_policy import require_goethe_nhr_slurm
from .targeted_experiment_review import (
    TargetedReviewStore,
    current_repository_commit,
    export_completed_targeted_labels,
    initialize_targeted_review_workspace,
    prepare_targeted_review_artifacts,
    run_targeted_review,
    score_completed_targeted_review,
    targeted_review_implementation_fingerprint,
    targeted_review_label_schema,
)
from .targeted_review_population import (
    REPAIRED_POPULATION_EXPECTATION,
    verify_repaired_targeted_review_population,
)
from .text import enforce_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safe-geocoding-phase03-targeted-review",
        description=("Protected DEVELOPMENT-only review for the parser-v3 experiment."),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("schema")

    verify = commands.add_parser("verify-repaired-population")
    verify.add_argument("--development-identities", type=Path, required=True)
    verify.add_argument("--baseline-core", type=Path, required=True)
    verify.add_argument("--baseline-evidence", type=Path, required=True)
    verify.add_argument("--experimental-core", type=Path, required=True)
    verify.add_argument("--experimental-evidence", type=Path, required=True)
    verify.add_argument("--repair-success", type=Path, required=True)
    verify.add_argument("--repair-comparison", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)

    prepare = commands.add_parser("prepare")
    prepare.add_argument("--development-payload", type=Path, required=True)
    prepare.add_argument("--development-identities", type=Path, required=True)
    prepare.add_argument("--baseline-core", type=Path, required=True)
    prepare.add_argument("--baseline-evidence", type=Path, required=True)
    prepare.add_argument("--experimental-core", type=Path, required=True)
    prepare.add_argument("--experimental-evidence", type=Path, required=True)
    prepare.add_argument("--population-verification-report", type=Path, required=True)
    prepare.add_argument("--output-directory", type=Path, required=True)
    prepare.add_argument("--experiment-iteration", required=True)
    prepare.add_argument("--experimental-parser-commit", required=True)
    prepare.add_argument("--review-implementation-commit", required=True)
    prepare.add_argument("--expected-development-rows", type=int, default=8_000)

    initialize = commands.add_parser("initialize")
    initialize.add_argument("--protected-context", type=Path, required=True)
    initialize.add_argument("--protected-template", type=Path, required=True)
    initialize.add_argument("--input-manifest", type=Path, required=True)
    initialize.add_argument("--output-directory", type=Path, required=True)
    initialize.add_argument("--implementation-commit", required=True)

    review = commands.add_parser("review")
    review.add_argument("--progress-database", type=Path, required=True)
    review.add_argument("--protected-context", type=Path, required=True)
    review.add_argument("--line-mode", action="store_true")

    progress = commands.add_parser("progress")
    progress.add_argument("--progress-database", type=Path, required=True)

    export = commands.add_parser("export-controlled-labels")
    export.add_argument("--reviewer-one-database", type=Path, required=True)
    export.add_argument("--reviewer-two-database", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)

    score = commands.add_parser("score")
    score.add_argument("--reviewer-one-database", type=Path, required=True)
    score.add_argument("--reviewer-two-database", type=Path, required=True)
    score.add_argument("--protected-context", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    return parser


def _print(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _stable_artifact_reference(path: Path, review_root: Path) -> str:
    reference = path.relative_to(review_root)
    if reference.is_absolute() or ".in_progress" in reference.parts:
        raise ValueError("targeted-review artifact reference is not promotion-stable")
    return reference.as_posix()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "schema":
        _print(
            {
                "implementation_fingerprint": targeted_review_implementation_fingerprint(),
                "fields": [
                    {
                        "name": field.name,
                        "type": str(field.type),
                        "nullable": field.nullable,
                    }
                    for field in targeted_review_label_schema()
                ],
            }
        )
        return 0
    enforce_runtime_contract()
    require_goethe_nhr_slurm(f"phase03-targeted-review-{args.command}")
    if args.command == "verify-repaired-population":
        payload = verify_repaired_targeted_review_population(
            development_identities_path=args.development_identities,
            baseline_core_path=args.baseline_core,
            baseline_evidence_path=args.baseline_evidence,
            experimental_core_path=args.experimental_core,
            experimental_evidence_path=args.experimental_evidence,
            repair_success_path=args.repair_success,
            repair_comparison_path=args.repair_comparison,
            output_path=args.output,
            verification_implementation_commit=current_repository_commit(),
            verification_implementation_fingerprint=(
                targeted_review_implementation_fingerprint()
            ),
            production=True,
        )
        _print(payload)
        return 0
    if args.command == "prepare":
        if args.review_implementation_commit != current_repository_commit():
            raise ValueError("targeted-review implementation commit mismatch")
        prepared = prepare_targeted_review_artifacts(
            development_payload_path=args.development_payload,
            development_identities_path=args.development_identities,
            baseline_core_path=args.baseline_core,
            baseline_evidence_path=args.baseline_evidence,
            experimental_core_path=args.experimental_core,
            experimental_evidence_path=args.experimental_evidence,
            population_verification_report_path=(args.population_verification_report),
            output_directory=args.output_directory,
            experiment_iteration=args.experiment_iteration,
            experimental_parser_commit=args.experimental_parser_commit,
            review_implementation_commit=args.review_implementation_commit,
            expected_development_rows=args.expected_development_rows,
            expected_population_count=REPAIRED_POPULATION_EXPECTATION.union_rows,
            production=True,
        )
        _print(
            {
                "status": "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS",
                "population_count": prepared.population_count,
                "population_digest": prepared.population_digest,
                "context": _stable_artifact_reference(
                    prepared.context_path, args.output_directory.parent
                ),
                "template": _stable_artifact_reference(
                    prepared.template_path, args.output_directory.parent
                ),
                "manifest": _stable_artifact_reference(
                    prepared.manifest_path, args.output_directory.parent
                ),
            }
        )
        return 0
    if args.command == "initialize":
        first, second = initialize_targeted_review_workspace(
            context_path=args.protected_context,
            template_path=args.protected_template,
            manifest_path=args.input_manifest,
            output_directory=args.output_directory,
            implementation_commit=args.implementation_commit,
        )
        _print(
            {
                "status": "INITIALIZED",
                "reviewer_one_database": str(first),
                "reviewer_two_database": str(second),
            }
        )
        return 0
    if args.command == "review":
        run_targeted_review(
            progress_database=args.progress_database,
            context_path=args.protected_context,
            line_mode=args.line_mode,
        )
        return 0
    if args.command == "progress":
        with TargetedReviewStore(args.progress_database, readonly=True) as store:
            _print(store.summary())
        return 0
    if args.command == "export-controlled-labels":
        path = export_completed_targeted_labels(
            reviewer_one_database=args.reviewer_one_database,
            reviewer_two_database=args.reviewer_two_database,
            output_path=args.output,
        )
        _print({"status": "EXPORTED_CONTROLLED_LABELS", "output": str(path)})
        return 0
    if args.command == "score":
        payload = score_completed_targeted_review(
            reviewer_one_database=args.reviewer_one_database,
            reviewer_two_database=args.reviewer_two_database,
            context_path=args.protected_context,
            output_path=args.output,
        )
        _print(payload)
        return 0
    raise AssertionError("unreachable targeted-review command")


if __name__ == "__main__":
    raise SystemExit(main())

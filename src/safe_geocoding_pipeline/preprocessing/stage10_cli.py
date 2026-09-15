"""Offline Stage 10 CLI: generation only, with static privacy-safe diagnostics."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages import s09_reference_io as io
from .stages import s10_query_contract as c
from .stages import s10_query_execution as execution
from .stages import s10_query_publication as publication


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Frozen Stage 10 bounded query hypotheses; offline DEVELOPMENT only."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "describe-contract",
        help="Public design/runtime identities; no protected inputs.",
    )
    for name in ("materialize", "validate-published"):
        command = commands.add_parser(name)
        command.add_argument("--stage06-root", type=Path, required=True)
        command.add_argument("--output-directory", type=Path, required=True)
        command.add_argument("--execution-git-sha", required=True)
        command.add_argument(
            "--expected-manifest-sha256", required=name == "validate-published"
        )
        command.add_argument("--resume-work-root", type=Path)
    return parser


def _diagnostic(code: str) -> None:
    try:
        sys.stderr.write(code + "\n")
        sys.stderr.flush()
    except BaseException:
        sys.stderr = None


def _present(result: io.PublicationResult) -> None:
    try:
        payload = {
            "status": "STAGE10_DEVELOPMENT_CANDIDATE_PUBLISHED_NOT_ACCEPTED",
            "manifest_sha256": result.manifest_sha256,
            "logical_sha256": result.manifest["logical_sha256"],
            "profile_sha256": result.manifest["profile_sha256"],
            "publication_key": result.path.name,
            "publication_disposition": result.disposition,
            "commit_record_id": result.commit_record_id,
            "registration_sha256": result.registration_sha256,
            "protocol": publication.PROTOCOL,
            "relation_counts": {
                r["name"]: r["row_count"] for r in result.manifest["relations"]
            },
            "operating_budget": None,
            "pelias_calls": 0,
            "external_address_calls": 0,
        }
        sys.stdout.write(c.canonical(payload).decode("ascii"))
        sys.stdout.flush()
    except BaseException:
        sys.stdout = None
        _diagnostic("STAGE10_PRESENTATION_FAILED_AFTER_PUBLICATION_SUCCESS")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "describe-contract":
        execution.verify_design(execution.REPOSITORY)
        print(
            c.canonical(
                {
                    "contract": c.CONTRACT,
                    "contract_sha256": c.contract_fingerprint().hex(),
                    "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
                    "runtime_build_lock_sha256": execution.RUNTIME_LOCK_SHA,
                    "design_merge_sha": c.DESIGN_MERGE,
                    "operating_budget": None,
                }
            ).decode("ascii"),
            end="",
        )
        return 0
    try:
        require_goethe_nhr_slurm("stage10-query-cli")
        config = execution.Stage10Config(
            args.stage06_root,
            args.output_directory,
            args.execution_git_sha,
            args.expected_manifest_sha256,
            args.resume_work_root,
        )
        result = execution.run(
            config, validate_only=args.command == "validate-published"
        )
    except (ExecutionPolicyError, c.Stage10Error) as error:
        code = str(error)
        if code == "FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION":
            _diagnostic("STAGE10_COMMIT_OUTCOME_UNVERIFIED_RECONCILIATION_REQUIRED")
        elif code == "STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED":
            _diagnostic(code)
        else:
            _diagnostic("STAGE10_GUARD_OR_VALIDATION_FAILURE_ATTEMPT_PRESERVED")
        return 1
    except BaseException:
        _diagnostic("STAGE10_OPERATIONAL_FAILURE_ATTEMPT_PRESERVED")
        return 1
    _present(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

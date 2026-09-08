"""Guarded offline Stage 9 CLI; terminal presentation cannot undo publication."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages import s09_reference_contract as c
from .stages import s09_reference_io as io
from .stages.s09_reference_materializer import (
    Stage09Config,
    materialize_stage09,
    validate_published_stage09,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Frozen Stage 9 offline reference evidence; DEVELOPMENT only."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "describe-contract",
        help="Print public contract fingerprints; no inputs opened.",
    )
    for name in ("materialize", "validate-published"):
        command = commands.add_parser(name)
        command.add_argument("--stage08-root", type=Path, required=True)
        command.add_argument("--reference-raw-root", type=Path, required=True)
        command.add_argument("--reference-lock", type=Path, required=True)
        command.add_argument("--reference-pack-root", type=Path, required=True)
        command.add_argument("--reference-pack-manifest-sha256")
        command.add_argument("--output-directory", type=Path, required=True)
        command.add_argument("--execution-git-sha", required=True)
        command.add_argument("--resume-work-root", type=Path)
    commands.choices["validate-published"].add_argument(
        "--expected-manifest-sha256", required=True
    )
    return parser


def _diagnostic(message: str) -> None:
    try:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()
    except BaseException:
        sys.stderr = None


def _present(outcome: io.PublicationResult) -> None:
    try:
        metrics = outcome.manifest["development_metrics"]
        payload = "\n".join(
            (
                "status=STAGE09_DEVELOPMENT_CANDIDATE_PUBLISHED_NOT_ACCEPTED",
                "manifest_sha256=" + outcome.manifest_sha256,
                "logical_sha256=" + outcome.manifest["logical_sha256"],
                "profile_sha256=" + outcome.manifest["profile_sha256"],
                "candidate_count=" + str(metrics["total_stage06_candidates"]),
                "evidence_count=" + str(metrics["evidence_rows"]),
                "technical_failures=0",
                "network_calls=0",
                "pelias_calls=0",
                "",
            )
        )
        sys.stdout.write(payload)
        sys.stdout.flush()
    except BaseException:
        sys.stdout = None
        _diagnostic("STAGE09_PRESENTATION_FAILED_AFTER_PUBLICATION_SUCCESS")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "describe-contract":
        print("contract=" + c.CONTRACT_VERSION)
        print("contract_sha256=" + c.contract_fingerprint().hex())
        print("schema_bundle_sha256=" + c.schema_bundle_fingerprint().hex())
        print("catalog_sha256=" + c.catalog_fingerprint().hex())
        print("reference_lock_sha256=" + c.LOCK_SHA256)
        return 0
    try:
        require_goethe_nhr_slurm("stage09-reference-evidence-cli")
        config = Stage09Config(
            stage08_root=args.stage08_root,
            reference_raw_root=args.reference_raw_root,
            reference_lock=args.reference_lock,
            reference_pack_root=args.reference_pack_root,
            output_directory=args.output_directory,
            execution_git_sha=args.execution_git_sha,
            reference_pack_manifest_sha256=args.reference_pack_manifest_sha256,
            resume_work_root=args.resume_work_root,
        )
        if args.command == "materialize":
            outcome = materialize_stage09(config)
        else:
            outcome = validate_published_stage09(config, args.expected_manifest_sha256)
    except (ExecutionPolicyError, c.Stage09Error):
        # Even a nested engine/filesystem exception may carry a queried value.
        # The controlled attempt records its last completed checkpoint, while
        # process diagnostics contain no arbitrary exception text or traceback.
        _diagnostic("STAGE09_GUARD_OR_VALIDATION_FAILURE_ATTEMPT_PRESERVED")
        return 1
    except BaseException:
        _diagnostic("STAGE09_OPERATIONAL_FAILURE_ATTEMPT_PRESERVED")
        return 1
    _present(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

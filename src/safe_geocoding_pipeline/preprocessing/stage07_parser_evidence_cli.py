"""CLI for the Stage 7 evidence-only v2 projection."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages.s06_exact_deduplication import Stage06ValidationError
from .stages.s07_parser_evidence import (
    Stage07EvidenceConfig,
    materialize_stage07_evidence,
    validate_stage07_evidence_bundle,
)
from .stages.s07_parsing import Stage07ValidationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Project immutable Stage 7 v1 into evidence-only Stage 7 v2."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("materialize", "validate-published"):
        command = subparsers.add_parser(name)
        command.add_argument("--stage06-output-directory", type=Path, required=True)
        command.add_argument("--stage07-v1-output-directory", type=Path, required=True)
        command.add_argument("--eligibility-artifact", type=Path, required=True)
        command.add_argument("--eligibility-audit-manifest", type=Path, required=True)
        command.add_argument("--output-directory", type=Path, required=True)
        command.add_argument("--execution-git-sha", required=True)
        command.add_argument("--input-batch-rows", type=int, default=64)
        command.add_argument("--output-batch-rows", type=int, default=64)
        command.add_argument(
            "--target-batch-bytes", type=int, default=128 * 1024 * 1024
        )
        command.add_argument("--output-shard-rows", type=int, default=4_096)
    subparsers.choices["validate-published"].add_argument(
        "--expected-manifest-sha256", required=True
    )
    return parser


def _config(args: argparse.Namespace) -> Stage07EvidenceConfig:
    return Stage07EvidenceConfig(
        stage06_output_directory=args.stage06_output_directory,
        stage07_v1_output_directory=args.stage07_v1_output_directory,
        eligibility_artifact=args.eligibility_artifact,
        eligibility_audit_manifest=args.eligibility_audit_manifest,
        output_directory=args.output_directory,
        execution_git_sha=args.execution_git_sha,
        input_batch_rows=args.input_batch_rows,
        output_batch_rows=args.output_batch_rows,
        target_batch_bytes=args.target_batch_bytes,
        output_shard_rows=args.output_shard_rows,
        operational_metadata={
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_goethe_nhr_slurm("stage07-parser-evidence-v2-cli")
        config = _config(args)
        if args.command == "materialize":
            outcome = materialize_stage07_evidence(config)
            print("status=STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_MATERIALIZED")
        else:
            outcome = validate_stage07_evidence_bundle(
                config.output_directory,
                expected_manifest_sha256=args.expected_manifest_sha256,
                config=config,
            )
            print("status=STAGE07_EVIDENCE_ONLY_PUBLISHED_VALIDATION_PASS")
        print(f"candidate_rows={outcome.candidate_count}")
        print(f"stage07_manifest_sha256={outcome.manifest_sha256}")
        print(f"stage07_logical_dataset_sha256_v2={outcome.logical_dataset_sha256_v2}")
        print(f"stage07_schema_fingerprint={outcome.schema_fingerprint}")
        print(f"stage07_contract_fingerprint={outcome.contract_fingerprint}")
        print(f"stage07_registry_shards={outcome.shard_count}")
        print("parser_calls=0")
        print("semantic_trust_claims=0")
    except (
        ExecutionPolicyError,
        Stage06ValidationError,
        Stage07ValidationError,
    ) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

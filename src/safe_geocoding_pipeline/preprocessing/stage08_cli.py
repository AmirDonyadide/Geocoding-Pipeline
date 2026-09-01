"""CLI for the frozen Stage 8 address-evidence projection."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from ..execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .stages.s08_address_evidence import (
    Stage08Config,
    Stage08ValidationError,
    materialize_stage08,
    validate_stage08_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize or validate frozen Stage 8 parser evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("materialize", "validate-published"):
        command = subparsers.add_parser(name)
        command.add_argument("--stage07-output-directory", type=Path, required=True)
        command.add_argument("--stage06-output-directory", type=Path, required=True)
        command.add_argument("--output-directory", type=Path, required=True)
        command.add_argument("--execution-git-sha", required=True)
        command.add_argument("--input-batch-rows", type=int, default=16)
        command.add_argument("--candidate-output-batch-rows", type=int, default=32)
        command.add_argument("--component-batch-rows", type=int, default=65_536)
        command.add_argument(
            "--target-batch-bytes", type=int, default=128 * 1024 * 1024
        )
        command.add_argument("--candidate-shard-rows", type=int, default=2_048)
        command.add_argument("--component-shard-rows", type=int, default=500_000)
        command.add_argument("--source-shard-rows", type=int, default=4_096)
        command.add_argument("--duckdb-memory-limit", default="8GB")
        command.add_argument("--duckdb-threads", type=int, default=4)
    subparsers.choices["validate-published"].add_argument(
        "--expected-manifest-sha256", required=True
    )
    return parser


def _config(args: argparse.Namespace) -> Stage08Config:
    return Stage08Config(
        stage07_output_directory=args.stage07_output_directory,
        stage06_output_directory=args.stage06_output_directory,
        output_directory=args.output_directory,
        execution_git_sha=args.execution_git_sha,
        input_batch_rows=args.input_batch_rows,
        candidate_output_batch_rows=args.candidate_output_batch_rows,
        component_batch_rows=args.component_batch_rows,
        target_batch_bytes=args.target_batch_bytes,
        candidate_shard_rows=args.candidate_shard_rows,
        component_shard_rows=args.component_shard_rows,
        source_shard_rows=args.source_shard_rows,
        duckdb_memory_limit=args.duckdb_memory_limit,
        duckdb_threads=args.duckdb_threads,
        operational_metadata={
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
        },
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        require_goethe_nhr_slurm("stage08-address-evidence-cli")
        config = _config(args)
        if args.command == "materialize":
            outcome = materialize_stage08(config)
            print(
                "status=STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED"
            )
        else:
            outcome = validate_stage08_bundle(
                config.output_directory,
                expected_manifest_sha256=args.expected_manifest_sha256,
                config=config,
            )
            print("status=STAGE08_ADDRESS_EVIDENCE_PUBLISHED_VALIDATION_PASS")
        print(f"candidate_rows={outcome.candidate_rows}")
        print(f"component_rows={outcome.component_rows}")
        print(f"source_rows={outcome.source_rows}")
        print(f"occurrence_rows={outcome.occurrence_rows}")
        print(f"manifest_sha256={outcome.manifest_sha256}")
        print(f"logical_dataset_sha256={outcome.logical_dataset_sha256}")
        print(f"contract_fingerprint={outcome.contract_fingerprint}")
        print(f"schema_bundle_fingerprint={outcome.schema_bundle_fingerprint}")
        print("parser_calls=0")
        print("semantic_trust_fields=0")
        print("reference_lookups=0")
        print("network_calls=0")
    except (ExecutionPolicyError, Stage08ValidationError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

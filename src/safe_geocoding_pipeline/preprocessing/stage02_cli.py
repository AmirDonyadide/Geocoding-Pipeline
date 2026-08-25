from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..execution_policy import ExecutionPolicyError
from .stages.s02_harmonization import (
    Stage02RunConfig,
    Stage02ValidationError,
    materialize_stage02,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize Stage 2 schema and provenance harmonization."
    )
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--input-binding", required=True, type=Path)
    parser.add_argument("--expected-input-binding-sha256", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--adopting-git-commit", required=True)
    parser.add_argument("--batch-rows", type=int, default=4_096)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outcome = materialize_stage02(
            Stage02RunConfig(
                input_root=args.input_root,
                input_binding_file=args.input_binding,
                expected_input_binding_sha256=args.expected_input_binding_sha256,
                output_directory=args.output_directory,
                adopting_git_commit=args.adopting_git_commit,
                batch_rows=args.batch_rows,
                production=True,
                operational_metadata={
                    "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
                    "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
                },
            )
        )
    except (Stage02ValidationError, ExecutionPolicyError) as error:
        print(f"error={error}", file=sys.stderr)
        return 1
    print("status=STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION")
    print(f"rows={outcome.row_count}")
    print(f"source_files={outcome.source_file_count}")
    print(f"output_shards={outcome.output_shard_count}")
    print(f"stage02_logical_dataset_sha256_v1={outcome.logical_dataset_sha256_v1}")
    print(f"stage02_manifest_sha256={outcome.manifest_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

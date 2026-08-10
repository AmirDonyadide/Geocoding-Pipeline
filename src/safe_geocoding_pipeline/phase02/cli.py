from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import Phase02Config
from .runner import run_phase02


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safe-geocoding-phase02",
        description="Create validated lossless Parquet staging from Phase 1-verified CSV files.",
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--phase01-run-dir", required=True, type=Path)
    parser.add_argument(
        "--staging-root", type=Path, default=Path("staging/controlled/phase02_v1/runs")
    )
    parser.add_argument(
        "--reports-root", type=Path, default=Path("reports/generated/phase02")
    )
    parser.add_argument(
        "--run-scope", choices=("TEST", "SMOKE_TEST", "FULL_CONVERSION"), default="TEST"
    )
    parser.add_argument("--include", action="append", default=[], metavar="DIRECT_CHILD.csv")
    parser.add_argument("--source-root-label")
    parser.add_argument("--run-id")
    parser.add_argument("--resume-run-id")
    parser.add_argument("--parser-field-limit-chars", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--normal-batch-rows", type=int, default=25_000)
    parser.add_argument("--isolation-threshold-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--hash-chunk-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--duckdb-memory-limit", default="4GB")
    parser.add_argument("--require-free-gib", type=float, default=20.0)
    parser.add_argument(
        "--authorize-full-conversion",
        action="store_true",
        help=(
            "Operator safety acknowledgement for FULL_CONVERSION. It does not substitute "
            "for explicit project authorization."
        ),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> Phase02Config:
    return Phase02Config(
        source_root=args.source_root,
        phase01_run_dir=args.phase01_run_dir,
        staging_root=args.staging_root,
        reports_root=args.reports_root,
        run_scope=args.run_scope,
        include_files=tuple(args.include),
        source_root_label=args.source_root_label,
        run_id=args.run_id,
        resume_run_id=args.resume_run_id,
        parser_field_limit_chars=args.parser_field_limit_chars,
        normal_batch_rows=args.normal_batch_rows,
        isolation_threshold_bytes=args.isolation_threshold_bytes,
        hash_chunk_bytes=args.hash_chunk_bytes,
        duckdb_memory_limit=args.duckdb_memory_limit,
        require_free_bytes=round(args.require_free_gib * 1024**3),
        authorize_full_conversion=args.authorize_full_conversion,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outcome = run_phase02(config_from_args(args))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"phase02 error: {error}\n")
    print(f"run_id={outcome.run_id}")
    print(f"staging_run_dir={outcome.staging_run_dir}")
    print(f"report_run_dir={outcome.report_run_dir}")
    print(f"status={outcome.status}")
    print(f"scope_gate={outcome.scope_gate}")
    print(f"phase02_completion_gate={outcome.phase02_completion_gate}")
    return 0 if outcome.scope_gate == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

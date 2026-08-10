from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import InventoryConfig
from .runner import run_inventory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safe-geocoding-phase01",
        description="Inventory immutable source CSV files without transforming them.",
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument(
        "--reports-root", type=Path, default=Path("reports/generated/phase01")
    )
    parser.add_argument(
        "--run-scope",
        choices=("TEST", "SMOKE_TEST", "FULL_INVENTORY"),
        default="TEST",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="DIRECT_CHILD.csv",
        help="Explicit direct-child CSV filename; repeat for multiple files.",
    )
    parser.add_argument("--source-root-label")
    parser.add_argument("--run-id")
    parser.add_argument("--resume-run-dir", type=Path)
    parser.add_argument("--field-warning-chars", type=int, default=1_024)
    parser.add_argument("--record-warning-chars", type=int, default=4_096)
    parser.add_argument("--parser-field-limit-chars", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--insertion-batch-size", type=int, default=1_000)
    parser.add_argument("--hash-chunk-bytes", type=int, default=1024 * 1024)
    parser.add_argument("--categorical-max-distinct", type=int, default=1_000)
    parser.add_argument("--categorical-max-value-chars", type=int, default=256)
    parser.add_argument("--require-free-gib", type=float, default=15.0)
    parser.add_argument(
        "--authorize-full-inventory",
        action="store_true",
        help=(
            "Operator safety acknowledgement required for FULL_INVENTORY. "
            "It does not substitute for project approval."
        ),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> InventoryConfig:
    return InventoryConfig(
        source_root=args.source_root,
        reports_root=args.reports_root,
        run_scope=args.run_scope,
        include_files=tuple(args.include),
        source_root_label=args.source_root_label,
        run_id=args.run_id,
        resume_run_dir=args.resume_run_dir,
        field_warning_chars=args.field_warning_chars,
        record_warning_chars=args.record_warning_chars,
        parser_field_limit_chars=args.parser_field_limit_chars,
        insertion_batch_size=args.insertion_batch_size,
        hash_chunk_bytes=args.hash_chunk_bytes,
        categorical_max_distinct=args.categorical_max_distinct,
        categorical_max_value_chars=args.categorical_max_value_chars,
        require_free_bytes=round(args.require_free_gib * 1024**3),
        authorize_full_inventory=args.authorize_full_inventory,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        outcome = run_inventory(config_from_args(args))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"phase01 error: {error}\n")
    print(f"run_id={outcome.run_id}")
    print(f"run_dir={outcome.run_dir}")
    print(f"status={outcome.status}")
    print(f"scope_gate={outcome.scope_gate}")
    print(f"phase01_completion_gate={outcome.phase01_completion_gate}")
    return 0 if outcome.scope_gate == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

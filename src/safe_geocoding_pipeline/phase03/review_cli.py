from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .review_interface import initialize_review_workspace, run_review_interface
from .review_progress import (
    ReviewProgressStore,
    current_interface_fingerprint,
    current_repository_commit,
    export_completed_reviews,
)
from .review_v2 import manual_review_schema_v2


def implementation_fingerprint() -> str:
    return current_interface_fingerprint()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safe-geocoding-phase03-review",
        description="Controlled DEVELOPMENT-only Phase 3 human review interface.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("schema", help="Print the portable-v2 schema and fingerprint.")

    initialize = commands.add_parser(
        "initialize",
        help="Validate immutable inputs and create R01/R02 progress stores.",
    )
    initialize.add_argument("--protected-context", type=Path, required=True)
    initialize.add_argument("--portable-v1-labels", type=Path, required=True)
    initialize.add_argument("--output-directory", type=Path, required=True)
    initialize.add_argument("--implementation-commit", required=True)

    review = commands.add_parser("review", help="Open one reviewer session.")
    review.add_argument("--progress-database", type=Path, required=True)
    review.add_argument("--protected-context", type=Path, required=True)
    review.add_argument(
        "--line-mode",
        action="store_true",
        help="Use the standard-library line interface instead of curses.",
    )

    progress = commands.add_parser(
        "progress", help="Print a privacy-safe progress summary."
    )
    progress.add_argument("--progress-database", type=Path, required=True)

    export = commands.add_parser(
        "export", help="Export completed R01/R02 records and sanitized manifest."
    )
    export.add_argument("--reviewer-one-database", type=Path, required=True)
    export.add_argument("--reviewer-two-database", type=Path, required=True)
    export.add_argument("--output-directory", type=Path, required=True)
    export.add_argument("--export-timestamp-utc")
    return parser


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    fingerprint = implementation_fingerprint()
    if args.command == "schema":
        schema = manual_review_schema_v2()
        _print_json(
            {
                "interface_implementation_fingerprint": fingerprint,
                "fields": [
                    {
                        "name": field.name,
                        "type": str(field.type),
                        "nullable": field.nullable,
                    }
                    for field in schema
                ],
            }
        )
        return 0
    if args.command == "initialize":
        if args.implementation_commit != current_repository_commit():
            raise ValueError(
                "implementation commit does not match the current review checkout"
            )
        first, second = initialize_review_workspace(
            args.protected_context,
            args.portable_v1_labels,
            args.output_directory,
            interface_implementation_commit=args.implementation_commit,
            interface_implementation_fingerprint=fingerprint,
        )
        _print_json(
            {
                "status": "INITIALIZED",
                "interface_implementation_fingerprint": fingerprint,
                "reviewer_one_database": str(first),
                "reviewer_two_database": str(second),
            }
        )
        return 0
    if args.command == "review":
        run_review_interface(
            args.progress_database,
            args.protected_context,
            line_mode=args.line_mode,
        )
        return 0
    if args.command == "progress":
        with ReviewProgressStore(args.progress_database, readonly=True) as store:
            _print_json(store.summary())
        return 0
    if args.command == "export":
        parquet_path, manifest_path = export_completed_reviews(
            args.reviewer_one_database,
            args.reviewer_two_database,
            args.output_directory,
            export_timestamp_utc=args.export_timestamp_utc,
        )
        _print_json(
            {
                "status": "EXPORTED",
                "portable_v2": str(parquet_path),
                "sanitized_manifest": str(manifest_path),
            }
        )
        return 0
    raise AssertionError("unreachable review-interface command")


if __name__ == "__main__":
    raise SystemExit(main())

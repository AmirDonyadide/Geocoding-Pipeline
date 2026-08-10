from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from ..phase01.reports import atomic_json
from .models import FileValidationResult, ReconciliationResult

FILE_VALIDATION_COLUMNS = (
    "run_id",
    "relative_path",
    "status",
    "failure_code",
    "failure_detail",
    "source_size_bytes",
    "source_sha256",
    "source_rows",
    "staging_rows",
    "source_semantic_digest",
    "staging_semantic_digest",
    "semantic_digest_match",
    "output_path",
    "output_size_bytes",
    "output_sha256",
    "compression_ratio",
    "row_group_count",
    "row_group_rows_json",
    "isolated_record_count",
    "source_empty_counts_json",
    "staging_empty_counts_json",
    "source_non_ascii_counts_json",
    "staging_non_ascii_counts_json",
    "raw_null_count",
    "provenance_valid",
    "stable_ids_valid",
    "stable_ids_distinct",
    "known_extremes_valid",
    "extreme_observations_json",
    "page_checksums_verified",
    "conversion_seconds",
    "validation_seconds",
    "hashing_seconds",
    "promotion_seconds",
    "peak_temporary_bytes",
    "peak_rss_bytes",
)


def sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FILE_VALIDATION_COLUMNS, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_file_validation(
    path: Path, run_id: str, results: list[FileValidationResult]
) -> None:
    rows: list[dict[str, Any]] = []
    for result in results:
        value = result.to_dict()
        rows.append(
            {
                "run_id": run_id,
                **{
                    key: value[key]
                    for key in FILE_VALIDATION_COLUMNS
                    if key not in {
                        "run_id",
                        "row_group_rows_json",
                        "source_empty_counts_json",
                        "staging_empty_counts_json",
                        "source_non_ascii_counts_json",
                        "staging_non_ascii_counts_json",
                        "extreme_observations_json",
                    }
                },
                "row_group_rows_json": _json_value(result.row_group_rows),
                "source_empty_counts_json": _json_value(result.source_empty_counts),
                "staging_empty_counts_json": _json_value(result.staging_empty_counts),
                "source_non_ascii_counts_json": _json_value(result.source_non_ascii_counts),
                "staging_non_ascii_counts_json": _json_value(result.staging_non_ascii_counts),
                "extreme_observations_json": _json_value(result.extreme_observations),
            }
        )
    _atomic_csv(path, rows)


def write_failures(path: Path, run_id: str, results: list[FileValidationResult]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("run_id", "relative_path", "failure_code", "failure_detail"),
        )
        writer.writeheader()
        for result in results:
            if result.status != "PASS":
                writer.writerow(
                    {
                        "run_id": run_id,
                        "relative_path": result.relative_path,
                        "failure_code": result.failure_code,
                        "failure_detail": result.failure_detail,
                    }
                )
    os.replace(temporary, path)


def write_summary(
    path: Path,
    *,
    run_id: str,
    run_scope: str,
    scope_gate: str,
    phase02_completion_gate: str,
    results: list[FileValidationResult],
    reconciliation: ReconciliationResult,
    metrics: dict[str, float | int],
) -> None:
    passed = sum(result.status == "PASS" for result in results)
    lines = [
        "# Phase 2 generated scope summary",
        "",
        "This generated report is privacy-safe and does not contain raw address, city, postcode, or ID values.",
        "",
        f"- Run ID: `{run_id}`",
        f"- Run scope: `{run_scope}`",
        f"- Scope gate: **{scope_gate}**",
        f"- Phase 2 completion gate: **{phase02_completion_gate}**",
        f"- Files passed: {passed}/{len(results)}",
        f"- Total source rows: {sum(item.source_rows for item in results):,}",
        f"- Total staging rows: {sum(item.staging_rows for item in results):,}",
        f"- Reconciliation: **{reconciliation.status}**",
        f"- Runtime seconds: {metrics.get('runtime_seconds', 0):.3f}",
        f"- Peak RSS bytes: {int(metrics.get('peak_rss_bytes', 0)):,}",
        "",
        "## Per-file result",
        "",
        "| Source file | Status | Source rows | Staging rows | Digest match | Output bytes | Row groups | Isolated rows |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| `{result.relative_path}` | {result.status} | {result.source_rows:,} | "
            f"{result.staging_rows:,} | {result.semantic_digest_match} | "
            f"{result.output_size_bytes:,} | {result.row_group_count} | "
            f"{result.isolated_record_count} |"
        )
    lines.extend(
        [
            "",
            "A TEST or SMOKE_TEST scope PASS does not complete Phase 2 and does not authorize the full conversion or Phase 3.",
            "",
        ]
    )
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def write_all_reports(
    *,
    report_run_dir: Path,
    run_payload: dict[str, Any],
    results: list[FileValidationResult],
    reconciliation: ReconciliationResult,
    schema_payload: dict[str, Any],
) -> None:
    atomic_json(report_run_dir / "phase02_run.json", run_payload)
    write_file_validation(
        report_run_dir / "phase02_file_validation.csv", run_payload["run_id"], results
    )
    atomic_json(report_run_dir / "phase02_schema.json", schema_payload)
    atomic_json(report_run_dir / "phase02_reconciliation.json", reconciliation.to_dict())
    write_failures(
        report_run_dir / "phase02_failures.csv.gz", run_payload["run_id"], results
    )
    write_summary(
        report_run_dir / "phase02_summary.md",
        run_id=run_payload["run_id"],
        run_scope=run_payload["run_scope"],
        scope_gate=run_payload["scope_gate"],
        phase02_completion_gate=run_payload["phase02_completion_gate"],
        results=results,
        reconciliation=reconciliation,
        metrics=run_payload["metrics"],
    )

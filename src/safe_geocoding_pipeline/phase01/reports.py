from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from .constants import ANOMALY_COLUMNS, REPORT_NAMES
from .models import FileResult
from .store import IdStore

MANIFEST_COLUMNS = (
    "run_id",
    "file_id",
    "relative_path",
    "file_name",
    "size_bytes_before",
    "mtime_utc_before",
    "size_bytes_after_parse",
    "mtime_utc_after_parse",
    "size_bytes_after_hash",
    "mtime_utc_after_hash",
    "file_changed_during_scan",
    "sha256",
    "duplicate_file_group",
    "duplicate_file_group_size",
    "duplicate_verification_method",
    "bom_type",
    "encoding_status",
    "delimiter",
    "quote_character",
    "doublequote",
    "escape_character",
    "header_present",
    "observed_column_count",
    "schema_fingerprint",
    "schema_matches_expected",
    "logical_record_count",
    "valid_schema_record_count",
    "empty_record_count",
    "all_fields_empty_record_count",
    "wrong_column_count_record_count",
    "parser_error_count",
    "multiline_record_count",
    "max_physical_lines_per_record",
    "max_record_length_chars",
    "max_field_length_chars",
    "id_nonempty_count",
    "id_empty_count",
    "id_distinct_within_file",
    "id_duplicate_group_count_within_file",
    "id_duplicate_occurrence_count_within_file",
    "id_lexical_min_sha256",
    "id_lexical_min_length",
    "id_lexical_max_sha256",
    "id_lexical_max_length",
    "counts_complete",
    "scan_status",
    "error_code",
    "duration_ms",
)

SCHEMA_COLUMNS = (
    "run_id",
    "file_id",
    "relative_path",
    "column_position",
    "observed_column_name",
    "expected_column_name",
    "name_matches_expected",
    "position_matches_expected",
    "schema_fingerprint",
)

FIELD_PROFILE_COLUMNS = (
    "run_id",
    "file_id",
    "relative_path",
    "column_position",
    "column_name",
    "records_eligible_for_profile",
    "nonempty_count",
    "empty_count",
    "whitespace_only_count",
    "nonempty_share",
    "max_length_chars",
    "max_length_logical_record_number",
    "contains_newline_count",
    "oversized_field_count",
    "exact_placeholder_candidate_count",
    "profile_complete",
)

VALUE_PROFILE_COLUMNS = (
    "run_id",
    "file_id",
    "relative_path",
    "field_name",
    "profile_family",
    "category",
    "count",
    "denominator",
    "share",
)

DUPLICATE_ID_COLUMNS = (
    "run_id",
    "id_sha256",
    "occurrence_count",
    "file_count",
    "duplicate_scope",
    "file_id",
    "relative_path",
    "logical_record_number",
)


def _temporary_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_csv(
    path: Path, columns: tuple[str, ...], rows: Iterable[dict[str, Any]]
) -> None:
    temporary = _temporary_path(path)
    temporary.unlink(missing_ok=True)
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        temporary.chmod(0o600)
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = _temporary_path(path)
    temporary.unlink(missing_ok=True)
    with temporary.open("w", encoding="utf-8") as stream:
        temporary.chmod(0o600)
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)


def _manifest_rows(run_id: str, results: list[FileResult]) -> Iterable[dict[str, Any]]:
    for result in results:
        yield {
            "run_id": run_id,
            "file_id": result.file_id,
            "relative_path": result.relative_path,
            "file_name": result.file_name,
            "size_bytes_before": result.before.size_bytes,
            "mtime_utc_before": result.before.mtime_utc,
            "size_bytes_after_parse": result.after_parse.size_bytes,
            "mtime_utc_after_parse": result.after_parse.mtime_utc,
            "size_bytes_after_hash": result.after_hash.size_bytes,
            "mtime_utc_after_hash": result.after_hash.mtime_utc,
            "file_changed_during_scan": result.file_changed_during_scan,
            "sha256": result.sha256,
            "duplicate_file_group": result.duplicate_file_group,
            "duplicate_file_group_size": result.duplicate_file_group_size,
            "duplicate_verification_method": result.duplicate_verification_method,
            "bom_type": result.bom_type,
            "encoding_status": result.encoding_status,
            "delimiter": result.delimiter,
            "quote_character": result.quote_character,
            "doublequote": result.doublequote,
            "escape_character": result.escape_character,
            "header_present": result.header_present,
            "observed_column_count": result.observed_column_count,
            "schema_fingerprint": result.schema_fingerprint,
            "schema_matches_expected": result.schema_matches_expected,
            "logical_record_count": result.logical_record_count,
            "valid_schema_record_count": result.valid_schema_record_count,
            "empty_record_count": result.empty_record_count,
            "all_fields_empty_record_count": result.all_fields_empty_record_count,
            "wrong_column_count_record_count": result.wrong_column_count_record_count,
            "parser_error_count": result.parser_error_count,
            "multiline_record_count": result.multiline_record_count,
            "max_physical_lines_per_record": result.max_physical_lines_per_record,
            "max_record_length_chars": result.max_record_length_chars,
            "max_field_length_chars": result.max_field_length_chars,
            "id_nonempty_count": result.id_nonempty_count,
            "id_empty_count": result.id_empty_count,
            "id_distinct_within_file": result.id_distinct_within_file,
            "id_duplicate_group_count_within_file": result.id_duplicate_group_count_within_file,
            "id_duplicate_occurrence_count_within_file": result.id_duplicate_occurrence_count_within_file,
            "id_lexical_min_sha256": result.id_lexical_min_sha256,
            "id_lexical_min_length": result.id_lexical_min_length,
            "id_lexical_max_sha256": result.id_lexical_max_sha256,
            "id_lexical_max_length": result.id_lexical_max_length,
            "counts_complete": result.counts_complete,
            "scan_status": result.scan_status,
            "error_code": result.error_code,
            "duration_ms": result.duration_ms,
        }


def assign_duplicate_file_groups(results: list[FileResult]) -> None:
    candidates: dict[tuple[int | None, str], list[FileResult]] = {}
    for result in results:
        if result.sha256 and not result.file_changed_during_scan:
            candidates.setdefault(
                (result.after_hash.size_bytes, result.sha256), []
            ).append(result)
    group_number = 0
    for key in sorted(candidates):
        group = candidates[key]
        if len(group) < 2:
            continue
        group_number += 1
        group_id = f"duplicate-file-{group_number:04d}"
        for result in group:
            result.duplicate_file_group = group_id
            result.duplicate_file_group_size = len(group)
            result.duplicate_verification_method = "SIZE_AND_SHA256"


def _write_anomalies(
    path: Path,
    run_id: str,
    results: list[FileResult],
    spool_paths: dict[int, Path],
) -> None:
    temporary = _temporary_path(path)
    temporary.unlink(missing_ok=True)
    result_by_file = {result.file_id: result for result in results}
    with gzip.open(temporary, "wt", encoding="utf-8", newline="") as stream:
        temporary.chmod(0o600)
        writer = csv.DictWriter(stream, fieldnames=ANOMALY_COLUMNS)
        writer.writeheader()
        for file_id in sorted(spool_paths):
            spool = spool_paths[file_id]
            if not spool.exists():
                continue
            with spool.open("r", encoding="utf-8", newline="") as source_stream:
                for row in csv.DictReader(source_stream):
                    row["run_id"] = run_id
                    row["counts_complete"] = str(
                        result_by_file[file_id].counts_complete
                    )
                    writer.writerow(row)
    os.replace(temporary, path)
    path.chmod(0o600)


def _write_duplicate_ids(path: Path, run_id: str, store: IdStore) -> None:
    temporary = _temporary_path(path)
    temporary.unlink(missing_ok=True)
    with gzip.open(temporary, "wt", encoding="utf-8", newline="") as stream:
        temporary.chmod(0o600)
        writer = csv.writer(stream)
        writer.writerow(DUPLICATE_ID_COLUMNS)
        for row in store.duplicate_occurrence_rows():
            writer.writerow((run_id, *row))
    os.replace(temporary, path)
    path.chmod(0o600)


def _schema_rows(run_id: str, results: list[FileResult]) -> Iterable[dict[str, Any]]:
    for result in results:
        for row in result.schema_rows:
            yield {
                "run_id": run_id,
                "file_id": result.file_id,
                "relative_path": result.relative_path,
                "column_position": row.column_position,
                "observed_column_name": row.observed_column_name,
                "expected_column_name": row.expected_column_name,
                "name_matches_expected": row.name_matches_expected,
                "position_matches_expected": row.position_matches_expected,
                "schema_fingerprint": row.schema_fingerprint,
            }


def _field_profile_rows(
    run_id: str, results: list[FileResult]
) -> Iterable[dict[str, Any]]:
    for result in results:
        for row in result.field_profiles:
            denominator = row.records_eligible_for_profile
            yield {
                "run_id": run_id,
                "file_id": result.file_id,
                "relative_path": result.relative_path,
                "column_position": row.column_position,
                "column_name": row.column_name,
                "records_eligible_for_profile": denominator,
                "nonempty_count": row.nonempty_count,
                "empty_count": row.empty_count,
                "whitespace_only_count": row.whitespace_only_count,
                "nonempty_share": row.nonempty_count / denominator
                if denominator
                else 0.0,
                "max_length_chars": row.max_length_chars,
                "max_length_logical_record_number": row.max_length_logical_record_number,
                "contains_newline_count": row.contains_newline_count,
                "oversized_field_count": row.oversized_field_count,
                "exact_placeholder_candidate_count": row.exact_placeholder_candidate_count,
                "profile_complete": row.profile_complete,
            }


def _value_profile_rows(
    run_id: str, results: list[FileResult]
) -> Iterable[dict[str, Any]]:
    for result in results:
        for row in result.value_profiles:
            yield {
                "run_id": run_id,
                "file_id": result.file_id,
                "relative_path": result.relative_path,
                "field_name": row.field_name,
                "profile_family": row.profile_family,
                "category": row.category,
                "count": row.count,
                "denominator": row.denominator,
                "share": row.count / row.denominator if row.denominator else 0.0,
            }


def write_reports(
    *,
    run_dir: Path,
    run_id: str,
    results: list[FileResult],
    store: IdStore,
    spool_paths: dict[int, Path],
    run_payload: dict[str, Any],
    runtime_started: float,
) -> dict[str, dict[str, Any]]:
    assign_duplicate_file_groups(results)
    _atomic_csv(
        run_dir / "phase01_file_manifest.csv",
        MANIFEST_COLUMNS,
        _manifest_rows(run_id, results),
    )
    _atomic_csv(
        run_dir / "phase01_schema_report.csv",
        SCHEMA_COLUMNS,
        _schema_rows(run_id, results),
    )
    _atomic_csv(
        run_dir / "phase01_field_profile.csv",
        FIELD_PROFILE_COLUMNS,
        _field_profile_rows(run_id, results),
    )
    _atomic_csv(
        run_dir / "phase01_value_profile.csv",
        VALUE_PROFILE_COLUMNS,
        _value_profile_rows(run_id, results),
    )
    _write_anomalies(run_dir / "phase01_anomalies.csv.gz", run_id, results, spool_paths)
    _write_duplicate_ids(run_dir / "phase01_duplicate_ids.csv.gz", run_id, store)
    run_payload["metrics"]["runtime_seconds"] = time.perf_counter() - runtime_started
    summary = render_summary(run_payload, results, store)
    summary_path = run_dir / "phase01_summary.md"
    temporary = _temporary_path(summary_path)
    temporary.write_text(summary, encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, summary_path)
    summary_path.chmod(0o600)

    output_files: dict[str, dict[str, Any]] = {}
    for name in REPORT_NAMES:
        if name == "phase01_run.json":
            continue
        path = run_dir / name
        digest = _sha256_file(path)
        output_files[name] = {"size_bytes": path.stat().st_size, "sha256": digest}
    run_payload["metrics"]["generated_report_bytes"] = sum(
        item["size_bytes"] for item in output_files.values()
    )
    run_payload["output_files"] = output_files
    _validate_report_headers(run_dir)
    atomic_json(run_dir / "phase01_run.json", run_payload)
    return output_files


def _validate_report_headers(run_dir: Path) -> None:
    expected_csv_headers = {
        "phase01_file_manifest.csv": MANIFEST_COLUMNS,
        "phase01_schema_report.csv": SCHEMA_COLUMNS,
        "phase01_field_profile.csv": FIELD_PROFILE_COLUMNS,
        "phase01_value_profile.csv": VALUE_PROFILE_COLUMNS,
    }
    for name, expected in expected_csv_headers.items():
        with (run_dir / name).open("r", encoding="utf-8", newline="") as stream:
            observed = tuple(next(csv.reader(stream)))
        if observed != expected:
            raise RuntimeError(f"Generated report header validation failed: {name}")
    for name, expected in {
        "phase01_anomalies.csv.gz": ANOMALY_COLUMNS,
        "phase01_duplicate_ids.csv.gz": DUPLICATE_ID_COLUMNS,
    }.items():
        with gzip.open(run_dir / name, "rt", encoding="utf-8", newline="") as stream:
            observed = tuple(next(csv.reader(stream)))
        if observed != expected:
            raise RuntimeError(f"Generated report header validation failed: {name}")


def render_summary(
    run_payload: dict[str, Any], results: list[FileResult], store: IdStore
) -> str:
    total_rows = sum(result.logical_record_count for result in results)
    total_multiline = sum(result.multiline_record_count for result in results)
    total_wrong_columns = sum(
        result.wrong_column_count_record_count for result in results
    )
    total_parser_errors = sum(result.parser_error_count for result in results)
    max_field = max((result.max_field_length_chars for result in results), default=0)
    failed = [
        result.relative_path for result in results if result.scan_status != "COMPLETE"
    ]
    duplicates = store.duplicate_summary()
    approved_inputs = ", ".join(f"`{result.relative_path}`" for result in results)
    return f"""# Phase 1 inventory run summary

- Run ID: `{run_payload["run_id"]}`
- Inventory version: `{run_payload["inventory_version"]}`
- Run scope: `{run_payload["run_scope"]}`
- Execution status: `{run_payload["status"]}`
- Scope gate: `{run_payload["scope_gate"]}`
- Phase 1 completion gate: `{run_payload["phase01_completion_gate"]}`
- Input files: {approved_inputs or "none"}

## Structural results

- Files discovered: {len(results)}
- Files complete: {len(results) - len(failed)}
- Files failed: {len(failed)}
- Logical records returned: {total_rows}
- Quoted multiline records: {total_multiline}
- Wrong-column records: {total_wrong_columns}
- Parser/encoding errors: {total_parser_errors}
- Maximum field length: {max_field} characters

## Identity diagnostics

- Duplicate ID groups: {duplicates["duplicate_groups"]}
- Occurrences in duplicate groups: {duplicates["duplicate_group_occurrences"]}
- Excess duplicate occurrences: {duplicates["excess_duplicate_occurrences"]}

## Performance

- Total runtime: {run_payload["metrics"]["runtime_seconds"]:.3f} seconds
- CSV parsing time: {run_payload["metrics"]["csv_parse_seconds"]:.3f} seconds
- Raw-byte hashing time: {run_payload["metrics"]["hash_seconds"]:.3f} seconds
- Peak resident memory: {run_payload["metrics"]["peak_memory_bytes"]} bytes
- Temporary SQLite size: {run_payload["metrics"]["sqlite_bytes"]} bytes

## Gate interpretation

This report inventories only the configured `{run_payload["run_scope"]}` scope. A successful smoke or test gate does not complete Phase 1 and does not authorize Phase 2. FULL_INVENTORY requires a separate explicitly authorized population scope and approval.
"""

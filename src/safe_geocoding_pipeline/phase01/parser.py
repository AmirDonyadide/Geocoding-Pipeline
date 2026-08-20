from __future__ import annotations

import csv
import hashlib
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..raw_csv import (
    SOURCE_TEXT_ENCODING,
    SOURCE_TEXT_ENCODING_WITH_BOM,
    UTF8_BOM_BYTES,
    strict_csv_reader,
)
from .config import InventoryConfig
from .constants import ANOMALY_COLUMNS, EXPECTED_COLUMNS
from .models import (
    FileMetadata,
    FileResult,
    IdObservation,
    SchemaRow,
    SourceFile,
)
from .profiling import FileProfiler, sha256_text
from .store import IdStore


class _HeaderParseFailure(Exception):
    pass


def _mtime_utc(mtime_ns: int) -> str:
    return datetime.fromtimestamp(mtime_ns / 1_000_000_000, timezone.utc).isoformat()


def file_metadata(path: Path) -> FileMetadata:
    stat = path.stat(follow_symlinks=False)
    if not os.path.isfile(path) or path.is_symlink():
        raise OSError(f"Source is no longer a regular non-symlink file: {path.name}")
    return FileMetadata(
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        mtime_utc=_mtime_utc(stat.st_mtime_ns),
    )


def hash_file(path: Path, chunk_bytes: int) -> tuple[str, float]:
    started = time.perf_counter()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_bytes):
            digest.update(chunk)
    return digest.hexdigest(), time.perf_counter() - started


def detect_bom(path: Path) -> str:
    with path.open("rb") as stream:
        return "UTF8" if stream.read(len(UTF8_BOM_BYTES)) == UTF8_BOM_BYTES else "NONE"


def _schema_fingerprint(header: list[str]) -> str:
    return sha256_text("\x1f".join(header))


def _safe_header_value(value: str) -> str:
    if value in EXPECTED_COLUMNS:
        return value
    return f"UNEXPECTED_SHA256:{sha256_text(value)}:LENGTH:{len(value)}"


def _looks_like_header(header: list[str]) -> bool:
    expected = set(EXPECTED_COLUMNS)
    matches = sum(value in expected for value in header)
    return matches >= max(1, len(EXPECTED_COLUMNS) // 2)


@dataclass
class AnomalySpool:
    run_id: str
    source: SourceFile
    final_path: Path

    def __post_init__(self) -> None:
        self.final_path.parent.mkdir(parents=True, exist_ok=True)
        self.final_path.parent.chmod(0o700)
        self.temp_path = self.final_path.with_suffix(self.final_path.suffix + ".tmp")
        self.temp_path.unlink(missing_ok=True)
        self._stream = self.temp_path.open("w", encoding="utf-8", newline="")
        self.temp_path.chmod(0o600)
        self._writer = csv.DictWriter(self._stream, fieldnames=ANOMALY_COLUMNS)
        self._writer.writeheader()
        self.count = 0

    def add(
        self,
        *,
        severity: str,
        domain: str,
        anomaly_type: str,
        logical_record_number: int | None = None,
        physical_line_start: int | None = None,
        physical_line_end: int | None = None,
        column_name: str = "",
        expected: str = "",
        observed: str = "",
        field_length_chars: int | None = None,
        record_length_chars: int | None = None,
        value_sha256: str = "",
        message_code: str = "",
    ) -> None:
        self.count += 1
        row: dict[str, Any] = {
            "run_id": self.run_id,
            "anomaly_id": f"f{self.source.file_id:06d}-a{self.count:09d}",
            "severity": severity,
            "domain": domain,
            "anomaly_type": anomaly_type,
            "file_id": self.source.file_id,
            "relative_path": self.source.relative_path,
            "logical_record_number": logical_record_number,
            "physical_line_start": physical_line_start,
            "physical_line_end": physical_line_end,
            "column_name": column_name,
            "expected": expected,
            "observed": observed,
            "field_length_chars": field_length_chars,
            "record_length_chars": record_length_chars,
            "value_sha256": value_sha256,
            "message_code": message_code or anomaly_type,
            "counts_complete": "",
        }
        self._writer.writerow(
            {key: "" if value is None else value for key, value in row.items()}
        )

    def close(self) -> None:
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        os.replace(self.temp_path, self.final_path)
        self.final_path.chmod(0o600)

    def abort(self) -> None:
        if not self._stream.closed:
            self._stream.close()
        self.temp_path.unlink(missing_ok=True)

    def __enter__(self) -> "AnomalySpool":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()


def append_terminal_anomaly(
    *,
    spool_path: Path,
    run_id: str,
    source: SourceFile,
    anomaly_type: str,
    domain: str,
    observed: str,
) -> None:
    """Append a non-sensitive file-level failure found after parsing."""
    write_header = not spool_path.exists()
    with spool_path.open("a", encoding="utf-8", newline="") as stream:
        spool_path.chmod(0o600)
        writer = csv.DictWriter(stream, fieldnames=ANOMALY_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "run_id": run_id,
                "anomaly_id": f"f{source.file_id:06d}-terminal-{anomaly_type}",
                "severity": "FATAL",
                "domain": domain,
                "anomaly_type": anomaly_type,
                "file_id": source.file_id,
                "relative_path": source.relative_path,
                "logical_record_number": "",
                "physical_line_start": "",
                "physical_line_end": "",
                "column_name": "",
                "expected": "stable readable source file",
                "observed": observed,
                "field_length_chars": "",
                "record_length_chars": "",
                "value_sha256": "",
                "message_code": anomaly_type,
                "counts_complete": "",
            }
        )


def _build_schema_rows(header: list[str], fingerprint: str) -> list[SchemaRow]:
    rows: list[SchemaRow] = []
    width = max(len(header), len(EXPECTED_COLUMNS))
    for zero_index in range(width):
        observed = header[zero_index] if zero_index < len(header) else ""
        expected = (
            EXPECTED_COLUMNS[zero_index] if zero_index < len(EXPECTED_COLUMNS) else ""
        )
        rows.append(
            SchemaRow(
                column_position=zero_index + 1,
                observed_column_name=_safe_header_value(observed) if observed else "",
                expected_column_name=expected,
                name_matches_expected=bool(observed and observed in EXPECTED_COLUMNS),
                position_matches_expected=observed == expected,
                schema_fingerprint=fingerprint,
            )
        )
    return rows


def scan_csv_file(
    *,
    config: InventoryConfig,
    source: SourceFile,
    store: IdStore,
    run_id: str,
    anomaly_spool_path: Path,
    before: FileMetadata,
) -> FileResult:
    result = FileResult(
        file_id=source.file_id,
        relative_path=source.relative_path,
        file_name=source.file_name,
        before=before,
        scan_status="SCANNING",
    )
    started = time.perf_counter()
    profiler = FileProfiler(config)
    id_buffer: list[IdObservation] = []
    lexical_min: str | None = None
    lexical_max: str | None = None
    previous_field_limit = csv.field_size_limit()

    def flush_ids() -> None:
        nonlocal id_buffer
        if not id_buffer:
            return
        for add_result in store.add_ids(id_buffer):
            if add_result.distinct_in_file:
                result.id_distinct_within_file += 1
            else:
                result.id_duplicate_occurrence_count_within_file += 1
            if add_result.first_within_file_duplicate:
                result.id_duplicate_group_count_within_file += 1
        id_buffer = []

    try:
        csv.field_size_limit(config.parser_field_limit_chars)
        result.bom_type = detect_bom(source.path)
        encoding = (
            SOURCE_TEXT_ENCODING_WITH_BOM
            if result.bom_type == "UTF8"
            else SOURCE_TEXT_ENCODING
        )

        with AnomalySpool(run_id, source, anomaly_spool_path) as anomalies:
            parse_started = time.perf_counter()
            try:
                with source.path.open(
                    "r", encoding=encoding, errors="strict", newline=""
                ) as stream:
                    reader = strict_csv_reader(stream)
                    result.encoding_status = "UTF8_VALID"
                    try:
                        header = next(reader)
                    except StopIteration:
                        header = []
                    except csv.Error as error:
                        result.parser_error_count += 1
                        result.error_code = (
                            "FIELD_LIMIT_EXCEEDED"
                            if "field larger than field limit" in str(error).lower()
                            else "MALFORMED_CSV"
                        )
                        anomalies.add(
                            severity="FATAL",
                            domain="PARSING",
                            anomaly_type=result.error_code,
                            physical_line_start=1,
                            physical_line_end=reader.line_num or 1,
                            expected="valid expected CSV header within parser safety limit",
                            observed="strict CSV parser error in first logical record",
                        )
                        raise _HeaderParseFailure from error
                    result.header_present = _looks_like_header(header)
                    result.observed_column_count = len(header)
                    result.schema_fingerprint = _schema_fingerprint(header)
                    result.schema_matches_expected = tuple(header) == EXPECTED_COLUMNS
                    result.schema_rows = _build_schema_rows(
                        header, result.schema_fingerprint
                    )

                    if not result.schema_matches_expected:
                        anomalies.add(
                            severity="ERROR",
                            domain="SCHEMA",
                            anomaly_type="SCHEMA_DEVIATION",
                            physical_line_start=1 if header else None,
                            physical_line_end=reader.line_num if header else None,
                            expected=f"{len(EXPECTED_COLUMNS)} expected header columns",
                            observed=f"{len(header)} observed header columns",
                        )
                    if not result.header_present:
                        anomalies.add(
                            severity="ERROR",
                            domain="SCHEMA",
                            anomaly_type="HEADER_NOT_RECOGNIZED",
                            physical_line_start=1 if header else None,
                            physical_line_end=reader.line_num if header else None,
                            expected="recognizable expected header",
                            observed="header absent or not recognizable",
                        )

                    prior_physical_line = reader.line_num
                    while True:
                        physical_line_start = prior_physical_line + 1
                        try:
                            row = next(reader)
                        except StopIteration:
                            result.counts_complete = result.header_present
                            break
                        except UnicodeDecodeError:
                            raise
                        except csv.Error as error:
                            result.parser_error_count += 1
                            error_code = (
                                "FIELD_LIMIT_EXCEEDED"
                                if "field larger than field limit" in str(error).lower()
                                else "MALFORMED_CSV"
                            )
                            result.error_code = error_code
                            anomalies.add(
                                severity="FATAL",
                                domain="PARSING",
                                anomaly_type=error_code,
                                logical_record_number=result.logical_record_count + 1,
                                physical_line_start=physical_line_start,
                                physical_line_end=reader.line_num
                                or physical_line_start,
                                expected=(
                                    f"field <= {config.parser_field_limit_chars} characters"
                                    if error_code == "FIELD_LIMIT_EXCEEDED"
                                    else "valid strict CSV quoting"
                                ),
                                observed="parser safety limit exceeded"
                                if error_code == "FIELD_LIMIT_EXCEEDED"
                                else "strict CSV parser error",
                            )
                            break

                        result.logical_record_count += 1
                        logical_record_number = result.logical_record_count
                        physical_line_end = reader.line_num
                        physical_span = physical_line_end - physical_line_start + 1
                        prior_physical_line = physical_line_end
                        result.max_physical_lines_per_record = max(
                            result.max_physical_lines_per_record, physical_span
                        )
                        if physical_span > 1:
                            result.multiline_record_count += 1
                            anomalies.add(
                                severity="WARNING",
                                domain="CONTENT",
                                anomaly_type="QUOTED_MULTILINE_RECORD",
                                logical_record_number=logical_record_number,
                                physical_line_start=physical_line_start,
                                physical_line_end=physical_line_end,
                                observed=f"{physical_span} physical lines",
                            )

                        if not row:
                            result.empty_record_count += 1
                        record_length = sum(len(value) for value in row)
                        result.max_record_length_chars = max(
                            result.max_record_length_chars, record_length
                        )
                        if record_length > config.record_warning_chars:
                            anomalies.add(
                                severity="WARNING",
                                domain="CONTENT",
                                anomaly_type="OVERSIZED_LOGICAL_RECORD",
                                logical_record_number=logical_record_number,
                                physical_line_start=physical_line_start,
                                physical_line_end=physical_line_end,
                                expected=f"<= {config.record_warning_chars} characters",
                                observed=f"{record_length} characters",
                                record_length_chars=record_length,
                            )

                        if len(row) != len(EXPECTED_COLUMNS):
                            result.wrong_column_count_record_count += 1
                            anomalies.add(
                                severity="ERROR",
                                domain="SCHEMA",
                                anomaly_type="WRONG_COLUMN_COUNT",
                                logical_record_number=logical_record_number,
                                physical_line_start=physical_line_start,
                                physical_line_end=physical_line_end,
                                expected=f"{len(EXPECTED_COLUMNS)} columns",
                                observed=f"{len(row)} columns",
                                record_length_chars=record_length,
                            )
                            continue

                        result.valid_schema_record_count += 1
                        if all(value == "" for value in row):
                            result.all_fields_empty_record_count += 1
                        max_field_length = max((len(value) for value in row), default=0)
                        result.max_field_length_chars = max(
                            result.max_field_length_chars, max_field_length
                        )

                        for column_name, value in zip(
                            EXPECTED_COLUMNS, row, strict=True
                        ):
                            if len(value) > config.field_warning_chars:
                                anomalies.add(
                                    severity="WARNING",
                                    domain="CONTENT",
                                    anomaly_type="OVERSIZED_FIELD",
                                    logical_record_number=logical_record_number,
                                    physical_line_start=physical_line_start,
                                    physical_line_end=physical_line_end,
                                    column_name=column_name,
                                    expected=f"<= {config.field_warning_chars} characters",
                                    observed=f"{len(value)} characters",
                                    field_length_chars=len(value),
                                    record_length_chars=record_length,
                                    value_sha256=sha256_text(value),
                                )

                        if result.schema_matches_expected:
                            safeguards = profiler.observe(row, logical_record_number)
                            for field_name, reason in safeguards:
                                anomalies.add(
                                    severity="WARNING",
                                    domain="CONTENT",
                                    anomaly_type=reason,
                                    logical_record_number=logical_record_number,
                                    physical_line_start=physical_line_start,
                                    physical_line_end=physical_line_end,
                                    column_name=field_name,
                                    expected=(
                                        f"<= {config.categorical_max_distinct} distinct values and "
                                        f"value length <= {config.categorical_max_value_chars}"
                                    ),
                                    observed="categorical raw-value output suppressed",
                                )

                            id_value = row[0]
                            if id_value == "":
                                result.id_empty_count += 1
                            else:
                                result.id_nonempty_count += 1
                                lexical_min = (
                                    id_value
                                    if lexical_min is None
                                    else min(lexical_min, id_value)
                                )
                                lexical_max = (
                                    id_value
                                    if lexical_max is None
                                    else max(lexical_max, id_value)
                                )
                                id_buffer.append(
                                    IdObservation(
                                        id_value, source.file_id, logical_record_number
                                    )
                                )
                                if len(id_buffer) >= config.insertion_batch_size:
                                    flush_ids()
                    flush_ids()
            except _HeaderParseFailure:
                pass
            except UnicodeDecodeError as error:
                result.encoding_status = "UTF8_INVALID"
                result.parser_error_count += 1
                result.error_code = "INVALID_UTF8"
                anomalies.add(
                    severity="FATAL",
                    domain="ENCODING",
                    anomaly_type="INVALID_UTF8",
                    logical_record_number=result.logical_record_count + 1,
                    observed=f"undecodable byte offset {error.start}",
                    expected="strict UTF-8",
                )
            except (OSError, csv.Error) as error:
                result.parser_error_count += 1
                result.error_code = "FILE_READ_ERROR"
                anomalies.add(
                    severity="FATAL",
                    domain="FILE",
                    anomaly_type="FILE_READ_ERROR",
                    logical_record_number=result.logical_record_count + 1,
                    expected="readable stable source file",
                    observed=type(error).__name__,
                )
            finally:
                result.parse_duration_seconds = time.perf_counter() - parse_started

        result.field_profiles = profiler.field_profiles
        result.value_profiles = profiler.value_rows()
        if not result.counts_complete or not result.schema_matches_expected:
            for profile in result.field_profiles:
                profile.profile_complete = False
        if lexical_min is not None:
            result.id_lexical_min_sha256 = sha256_text(lexical_min)
            result.id_lexical_min_length = len(lexical_min)
        if lexical_max is not None:
            result.id_lexical_max_sha256 = sha256_text(lexical_max)
            result.id_lexical_max_length = len(lexical_max)
    finally:
        csv.field_size_limit(previous_field_limit)
        result.duration_ms = round((time.perf_counter() - started) * 1000)
    return result

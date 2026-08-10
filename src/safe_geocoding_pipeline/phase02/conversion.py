from __future__ import annotations

import csv
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..phase01.parser import file_metadata, hash_file
from ..raw_csv import SOURCE_COLUMNS, csv_field_limit, strict_csv_reader
from .config import Phase02Config
from .constants import (
    DICTIONARY_COLUMNS,
    PARSER_VERSION,
    SOURCE_SCHEMA_VERSION,
    STAGING_VERSION,
    STATISTICS_COLUMNS,
    STAGING_COLUMNS,
)
from .errors import Phase02FileError
from .identity import stable_source_row_id_v1
from .models import FileValidationResult, KnownExtreme, Phase01FileEntry
from .schema import exact_schema_matches, schema_with_metadata
from .semantic import RawSemanticDigest

SENSITIVE_NO_STATISTICS = frozenset(
    {
        "id",
        "street_address_line_1",
        "street_address_line_2",
        "street_address_line_3",
        "street_address_line_4",
        "street_address_line_1_native",
        "street_address_line_2_native",
        "street_address_line_3_native",
        "street_address_line_4_native",
        "postcode",
        "city",
        "stable_source_row_id_v1",
        "source_file_sha256",
    }
)


@dataclass(slots=True)
class SourceWriteResult:
    source_rows: int
    semantic_digest: str
    empty_counts: dict[str, int]
    non_ascii_counts: dict[str, int]
    isolated_record_count: int
    extreme_observations: list[dict[str, Any]]
    conversion_seconds: float
    hashing_seconds: float
    peak_temporary_bytes: int


class _BatchWriter:
    def __init__(
        self,
        path: Path,
        *,
        config: Phase02Config,
        metadata: dict[str, str],
    ) -> None:
        self.path = path
        self.config = config
        self.schema = schema_with_metadata(metadata)
        try:
            self.writer = pq.ParquetWriter(
                path,
                self.schema,
                version=config.parquet_version,
                data_page_version=config.data_page_version,
                compression=config.compression,
                compression_level=config.compression_level,
                use_dictionary=list(DICTIONARY_COLUMNS),
                write_statistics=list(STATISTICS_COLUMNS),
                write_page_checksum=True,
                store_schema=True,
                use_compliant_nested_type=True,
            )
        except (OSError, pa.ArrowException) as error:
            raise Phase02FileError("PARQUET_WRITE_FAILURE", type(error).__name__) from error
        path.chmod(0o600)
        self.buffers: list[list[Any]] = [[] for _ in STAGING_COLUMNS]
        self.rows = 0

    def append(self, values: tuple[Any, ...]) -> None:
        if len(values) != len(self.buffers):
            raise AssertionError("internal staging row width error")
        for buffer, value in zip(self.buffers, values, strict=True):
            buffer.append(value)
        self.rows += 1

    def flush(self) -> None:
        if self.rows == 0:
            return
        try:
            arrays = []
            for field, values in zip(self.schema, self.buffers, strict=True):
                if any(value is None for value in values):
                    raise Phase02FileError("NULL_CREATION", f"null value in {field.name}")
                arrays.append(pa.array(values, type=field.type, from_pandas=False, safe=True))
            batch = pa.RecordBatch.from_arrays(arrays, schema=self.schema)
            self.writer.write_batch(batch, row_group_size=self.rows)
        except Phase02FileError:
            raise
        except (pa.ArrowCapacityError, pa.ArrowInvalid) as error:
            raise Phase02FileError(
                "ARROW_CAPACITY_OR_CONVERSION_FAILURE", type(error).__name__
            ) from error
        except (OSError, pa.ArrowException) as error:
            raise Phase02FileError("PARQUET_WRITE_FAILURE", type(error).__name__) from error
        self.buffers = [[] for _ in STAGING_COLUMNS]
        self.rows = 0

    def close(self) -> None:
        self.flush()
        try:
            self.writer.close()
        except (OSError, pa.ArrowException) as error:
            raise Phase02FileError("PARQUET_WRITE_FAILURE", type(error).__name__) from error

    def abort(self) -> None:
        """Close the physical writer without flushing buffered logical rows."""
        try:
            self.writer.close()
        except Exception:
            pass


def _same_metadata(*values: object) -> bool:
    pairs = {(getattr(value, "size_bytes"), getattr(value, "mtime_ns")) for value in values}
    return len(pairs) == 1


def _extreme_map(extremes: tuple[KnownExtreme, ...]) -> dict[tuple[int, str], KnownExtreme]:
    return {(item.logical_record_number, item.column_name): item for item in extremes}


def write_source_to_temporary_parquet(
    *,
    source_path: Path,
    temporary_path: Path,
    entry: Phase01FileEntry,
    extremes: tuple[KnownExtreme, ...],
    config: Phase02Config,
    file_metadata_values: dict[str, str],
) -> SourceWriteResult:
    started = time.perf_counter()
    try:
        before = file_metadata(source_path)
    except OSError as error:
        raise Phase02FileError("SOURCE_READ_FAILURE", type(error).__name__) from error
    if before.size_bytes != entry.size_bytes or before.mtime_utc != entry.mtime_utc:
        raise Phase02FileError(
            "SOURCE_IDENTITY_MISMATCH", "source size or modification time differs from Phase 1"
        )
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    if temporary_path.exists():
        raise Phase02FileError("TEMPORARY_PATH_EXISTS", "attempt temporary path already exists")

    source_hash_bytes = bytes.fromhex(entry.sha256)
    digest = RawSemanticDigest()
    empty_counts = {column: 0 for column in SOURCE_COLUMNS}
    non_ascii_counts = {column: 0 for column in SOURCE_COLUMNS}
    known = _extreme_map(extremes)
    observed_extremes: list[dict[str, Any]] = []
    isolated = 0
    row_count = 0
    encoding = "utf-8-sig" if entry.bom_type == "UTF8" else "utf-8"
    batch_writer = _BatchWriter(temporary_path, config=config, metadata=file_metadata_values)

    try:
        with csv_field_limit(config.parser_field_limit_chars):
            with source_path.open("r", encoding=encoding, errors="strict", newline="") as stream:
                reader = strict_csv_reader(stream)
                try:
                    header = next(reader)
                except StopIteration as error:
                    raise Phase02FileError("EMPTY_SOURCE_FILE", "source has no header") from error
                if tuple(header) != SOURCE_COLUMNS:
                    raise Phase02FileError("SCHEMA_MISMATCH", "source header differs from Phase 1 contract")
                for row in reader:
                    row_count += 1
                    if len(row) != len(SOURCE_COLUMNS):
                        raise Phase02FileError(
                            "WRONG_COLUMN_COUNT",
                            f"logical record {row_count} has {len(row)} columns",
                        )
                    encoded = digest.update_row(row, row_count, require_non_null=True)
                    encoded_non_null = [value for value in encoded if value is not None]
                    isolate = any(
                        len(value) >= config.isolation_threshold_bytes for value in encoded_non_null
                    )
                    for column, value in zip(SOURCE_COLUMNS, row, strict=True):
                        if value == "":
                            empty_counts[column] += 1
                        if not value.isascii():
                            non_ascii_counts[column] += 1
                        expected = known.get((row_count, column))
                        if expected is not None:
                            value_digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                            if len(value) != expected.field_length_chars or value_digest != expected.value_sha256:
                                raise Phase02FileError(
                                    "KNOWN_EXTREME_SOURCE_MISMATCH",
                                    f"Phase 1 extreme mismatch at record {row_count} column {column}",
                                )
                            observed_extremes.append(
                                {
                                    "logical_record_number": row_count,
                                    "column_name": column,
                                    "field_length_chars": len(value),
                                    "field_length_utf8_bytes": len(value.encode("utf-8")),
                                    "value_sha256": value_digest,
                                    "physical_line_start": expected.physical_line_start,
                                    "physical_line_end": expected.physical_line_end,
                                }
                            )
                    if isolate:
                        batch_writer.flush()
                    stable_id = stable_source_row_id_v1(source_hash_bytes, row_count)
                    staging_row: tuple[Any, ...] = tuple(row) + (
                        entry.relative_path,
                        row_count,
                        stable_id,
                        source_hash_bytes,
                        SOURCE_SCHEMA_VERSION,
                        PARSER_VERSION,
                        STAGING_VERSION,
                    )
                    batch_writer.append(staging_row)
                    if isolate:
                        batch_writer.flush()
                        isolated += 1
                    elif batch_writer.rows >= config.normal_batch_rows:
                        batch_writer.flush()
        if row_count != entry.logical_record_count:
            raise Phase02FileError(
                "SOURCE_ROW_COUNT_MISMATCH",
                f"expected {entry.logical_record_count} rows, parsed {row_count}",
            )
        if len(observed_extremes) != len(extremes):
            raise Phase02FileError("KNOWN_EXTREME_MISSING", "not all Phase 1 extremes were observed")
        batch_writer.close()
    except UnicodeDecodeError as error:
        batch_writer.abort()
        raise Phase02FileError("INVALID_UTF8", f"undecodable byte offset {error.start}") from error
    except csv.Error as error:
        batch_writer.abort()
        code = (
            "FIELD_LIMIT_EXCEEDED"
            if "field larger than field limit" in str(error).lower()
            else "MALFORMED_CSV"
        )
        raise Phase02FileError(code, "strict CSV parser failure") from error
    except (pa.ArrowCapacityError, pa.ArrowInvalid) as error:
        batch_writer.abort()
        raise Phase02FileError("ARROW_CAPACITY_OR_CONVERSION_FAILURE", type(error).__name__) from error
    except Phase02FileError:
        batch_writer.abort()
        raise
    except OSError as error:
        batch_writer.abort()
        raise Phase02FileError("SOURCE_READ_FAILURE", type(error).__name__) from error
    except Exception:
        batch_writer.abort()
        raise

    conversion_seconds = time.perf_counter() - started
    after_parse = file_metadata(source_path)
    observed_hash, hashing_seconds = hash_file(source_path, config.hash_chunk_bytes)
    after_hash = file_metadata(source_path)
    if not _same_metadata(before, after_parse, after_hash):
        raise Phase02FileError("SOURCE_CHANGED_DURING_READ", "source size or mtime changed")
    if observed_hash != entry.sha256:
        raise Phase02FileError("SOURCE_IDENTITY_MISMATCH", "source SHA-256 differs from Phase 1")
    return SourceWriteResult(
        source_rows=row_count,
        semantic_digest=digest.hexdigest(),
        empty_counts=empty_counts,
        non_ascii_counts=non_ascii_counts,
        isolated_record_count=isolated,
        extreme_observations=observed_extremes,
        conversion_seconds=conversion_seconds,
        hashing_seconds=hashing_seconds,
        peak_temporary_bytes=temporary_path.stat().st_size,
    )


def _validate_no_sensitive_statistics(parquet_file: pq.ParquetFile) -> None:
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        row_group = parquet_file.metadata.row_group(row_group_index)
        for column_index in range(row_group.num_columns):
            column = row_group.column(column_index)
            if column.path_in_schema in SENSITIVE_NO_STATISTICS and column.statistics is not None:
                raise Phase02FileError(
                    "SENSITIVE_PARQUET_STATISTICS",
                    f"statistics unexpectedly present for {column.path_in_schema}",
                )


def validate_temporary_parquet(
    *,
    temporary_path: Path,
    entry: Phase01FileEntry,
    extremes: tuple[KnownExtreme, ...],
    source_result: SourceWriteResult,
    config: Phase02Config,
    required_metadata: dict[str, str],
) -> FileValidationResult:
    started = time.perf_counter()
    result = FileValidationResult(relative_path=entry.relative_path)
    result.source_size_bytes = entry.size_bytes
    result.source_sha256 = entry.sha256
    result.source_rows = source_result.source_rows
    result.source_semantic_digest = source_result.semantic_digest
    result.source_empty_counts = source_result.empty_counts
    result.source_non_ascii_counts = source_result.non_ascii_counts
    result.isolated_record_count = source_result.isolated_record_count
    result.peak_temporary_bytes = source_result.peak_temporary_bytes
    result.conversion_seconds = source_result.conversion_seconds
    result.hashing_seconds = source_result.hashing_seconds
    try:
        parquet_file = pq.ParquetFile(
            temporary_path,
            page_checksum_verification=True,
            pre_buffer=True,
        )
        if not exact_schema_matches(parquet_file.schema_arrow):
            raise Phase02FileError("STAGING_SCHEMA_MISMATCH", "Arrow schema differs from Phase 2 v1")
        observed_metadata = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in (parquet_file.schema_arrow.metadata or {}).items()
        }
        for key, expected in required_metadata.items():
            if observed_metadata.get(key) != expected:
                raise Phase02FileError("PARQUET_METADATA_MISMATCH", f"metadata mismatch for {key}")
        _validate_no_sensitive_statistics(parquet_file)
        result.row_group_count = parquet_file.metadata.num_row_groups
        result.row_group_rows = [
            parquet_file.metadata.row_group(index).num_rows
            for index in range(parquet_file.metadata.num_row_groups)
        ]

        digest = RawSemanticDigest()
        empty_counts = {column: 0 for column in SOURCE_COLUMNS}
        non_ascii_counts = {column: 0 for column in SOURCE_COLUMNS}
        stable_ids: set[bytes] = set()
        source_hash_bytes = bytes.fromhex(entry.sha256)
        known = _extreme_map(extremes)
        observed_extremes: list[dict[str, Any]] = []
        row_count = 0
        raw_null_count = 0
        provenance_valid = True
        stable_ids_valid = True

        for batch in parquet_file.iter_batches(
            batch_size=config.normal_batch_rows,
            columns=list(STAGING_COLUMNS),
            use_threads=False,
        ):
            columns = {name: batch.column(index).to_pylist() for index, name in enumerate(batch.schema.names)}
            for offset in range(batch.num_rows):
                row_count += 1
                raw_values = [columns[name][offset] for name in SOURCE_COLUMNS]
                raw_null_count += sum(value is None for value in raw_values)
                digest.update_row(raw_values, row_count, require_non_null=False)
                for column, value in zip(SOURCE_COLUMNS, raw_values, strict=True):
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise Phase02FileError("RAW_TYPE_MISMATCH", f"non-string value in {column}")
                    if value == "":
                        empty_counts[column] += 1
                    if not value.isascii():
                        non_ascii_counts[column] += 1
                    expected_extreme = known.get((row_count, column))
                    if expected_extreme is not None:
                        value_digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
                        observed_extremes.append(
                            {
                                "logical_record_number": row_count,
                                "column_name": column,
                                "field_length_chars": len(value),
                                "field_length_utf8_bytes": len(value.encode("utf-8")),
                                "value_sha256": value_digest,
                                "physical_line_start": expected_extreme.physical_line_start,
                                "physical_line_end": expected_extreme.physical_line_end,
                            }
                        )
                observed_row_number = columns["source_logical_record_number"][offset]
                observed_stable_id = columns["stable_source_row_id_v1"][offset]
                observed_source_hash = columns["source_file_sha256"][offset]
                if (
                    columns["source_file"][offset] != entry.relative_path
                    or observed_row_number != row_count
                    or observed_source_hash != source_hash_bytes
                    or columns["source_schema_version"][offset] != SOURCE_SCHEMA_VERSION
                    or columns["parser_version"][offset] != PARSER_VERSION
                    or columns["staging_version"][offset] != STAGING_VERSION
                ):
                    provenance_valid = False
                expected_stable_id = stable_source_row_id_v1(source_hash_bytes, row_count)
                if observed_stable_id != expected_stable_id:
                    stable_ids_valid = False
                if isinstance(observed_stable_id, bytes):
                    stable_ids.add(observed_stable_id)
                else:
                    stable_ids_valid = False

        result.staging_rows = row_count
        result.staging_semantic_digest = digest.hexdigest()
        result.semantic_digest_match = result.source_semantic_digest == result.staging_semantic_digest
        result.staging_empty_counts = empty_counts
        result.staging_non_ascii_counts = non_ascii_counts
        result.raw_null_count = raw_null_count
        result.provenance_valid = provenance_valid
        result.stable_ids_valid = stable_ids_valid
        result.stable_ids_distinct = len(stable_ids)
        result.extreme_observations = observed_extremes
        result.known_extremes_valid = observed_extremes == source_result.extreme_observations
        result.page_checksums_verified = True

        failures = {
            "STAGING_ROW_COUNT_MISMATCH": row_count != entry.logical_record_count,
            "RAW_NULLS_PRESENT": raw_null_count != 0,
            "SEMANTIC_DIGEST_MISMATCH": not result.semantic_digest_match,
            "EMPTY_STRING_COUNT_MISMATCH": empty_counts != source_result.empty_counts,
            "UNICODE_COUNT_MISMATCH": non_ascii_counts != source_result.non_ascii_counts,
            "PROVENANCE_MISMATCH": not provenance_valid,
            "STABLE_ID_MISMATCH": not stable_ids_valid,
            "STABLE_ID_DUPLICATE": len(stable_ids) != row_count,
            "KNOWN_EXTREME_MISMATCH": not result.known_extremes_valid,
        }
        for code, failed in failures.items():
            if failed:
                raise Phase02FileError(code, "temporary Parquet validation failed")
        result.status = "PASS"
        return result
    except Phase02FileError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Phase02FileError("PARQUET_READ_OR_CHECKSUM_FAILURE", type(error).__name__) from error
    finally:
        result.validation_seconds = time.perf_counter() - started

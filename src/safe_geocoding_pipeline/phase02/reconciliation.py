from __future__ import annotations

import time
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from ..raw_csv import SOURCE_COLUMNS
from .models import Phase01FileEntry, ReconciliationResult
from .schema import exact_schema_matches


def reconcile_completed_parquet(
    *,
    data_dir: Path,
    entries: list[Phase01FileEntry],
    memory_limit: str,
    spill_dir: Path,
) -> ReconciliationResult:
    started = time.perf_counter()
    spill_dir.mkdir(parents=True, exist_ok=True)
    expected_names = {Path(entry.file_name).with_suffix(".parquet").name for entry in entries}
    observed_paths = sorted(data_dir.glob("*.parquet"))
    observed_names = {path.name for path in observed_paths}
    missing = tuple(sorted(expected_names - observed_names))
    extra = tuple(sorted(observed_names - expected_names))
    schema_fingerprints = {
        str(pq.ParquetFile(path).schema_arrow.remove_metadata()) for path in observed_paths
    }

    if observed_paths:
        connection = duckdb.connect()
        try:
            connection.execute(f"SET memory_limit='{memory_limit}'")
            connection.execute("SET temp_directory=?", [str(spill_dir.resolve())])
            raw_null_expression = " + ".join(
                f'count(*) FILTER (WHERE "{column}" IS NULL)' for column in SOURCE_COLUMNS
            )
            query = f"""
                SELECT count(*) AS total_rows,
                       count(DISTINCT id) AS distinct_ids,
                       count(DISTINCT stable_source_row_id_v1) AS distinct_stable_ids,
                       count(*) FILTER (WHERE id IS NULL) AS null_ids,
                       count(*) - count(DISTINCT stable_source_row_id_v1) AS duplicate_stable_ids,
                       ({raw_null_expression}) AS raw_null_count
                FROM read_parquet(?)
            """
            row = connection.execute(query, [[str(path.resolve()) for path in observed_paths]]).fetchone()
            if row is None:
                raise RuntimeError("DuckDB reconciliation returned no result")
            total_rows, distinct_ids, distinct_stable_ids, null_ids, duplicate_stable, raw_nulls = (
                int(value) for value in row
            )
        finally:
            connection.close()
    else:
        total_rows = distinct_ids = distinct_stable_ids = null_ids = duplicate_stable = raw_nulls = 0

    expected_rows = sum(entry.logical_record_count for entry in entries)
    status = "PASS"
    if (
        len(observed_paths) != len(entries)
        or total_rows != expected_rows
        or distinct_ids != expected_rows
        or distinct_stable_ids != expected_rows
        or null_ids != 0
        or duplicate_stable != 0
        or raw_nulls != 0
        or len(schema_fingerprints) != 1
        or missing
        or extra
        or any(not exact_schema_matches(pq.ParquetFile(path).schema_arrow) for path in observed_paths)
    ):
        status = "FAIL"
    return ReconciliationResult(
        status=status,
        file_count=len(observed_paths),
        total_rows=total_rows,
        distinct_ids=distinct_ids,
        distinct_stable_ids=distinct_stable_ids,
        null_ids=null_ids,
        duplicate_stable_ids=duplicate_stable,
        raw_null_count=raw_nulls,
        schema_count=len(schema_fingerprints),
        missing_files=missing,
        extra_files=extra,
        duckdb_seconds=time.perf_counter() - started,
        duckdb_version=duckdb.__version__,
    )

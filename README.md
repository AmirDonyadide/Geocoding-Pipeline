# SAFE geocoding pipeline

The repository implements the reviewed project workflow documented under `docs/`.
Work proceeds one phase at a time.

## Phase 1 interface

Phase 1 inventories immutable raw CSV files. It does not stage, clean,
canonicalize, deduplicate addresses, geocode, or begin Phase 2.

Install the local package for development:

```bash
python3 -m pip install -e '.[dev]'
```

Run tests:

```bash
python3 -m pytest
```

Run an explicitly scoped smoke inventory:

```bash
python3 -m safe_geocoding_pipeline.phase01.cli \
  --source-root /path/to/csv_files \
  --reports-root reports/generated/phase01 \
  --run-scope SMOKE_TEST \
  --source-root-label csv_files \
  --include shard_a.csv \
  --include shard_b.csv
```

Generated reports and the temporary SQLite working database are written beneath
`reports/generated/phase01/<run_id>/`, which is ignored by Git. Absolute source
paths and confidential raw row values are excluded from portable reports.

`FULL_INVENTORY` has additional file-count, free-space, and explicit operator
acknowledgement guards. Passing those guards is not project authorization; the
complete 206-file run still requires the user's explicit approval.

## Phase 2 interface

Phase 2 creates a lossless, source-aligned controlled Parquet staging dataset.
It preserves the 15 raw CSV fields as non-null Arrow strings and adds seven
versioned provenance fields. It does not clean, normalize, parse, deduplicate,
canonicalize, or geocode address data.

The pinned runtime dependencies are PyArrow 25.0.0 and DuckDB 1.5.5. PyArrow
writes and independently validates Parquet; DuckDB only reconciles completed
Parquet files and never interprets source CSV.

An explicitly authorized two-file smoke conversion is invoked as follows:

```bash
python3 -m safe_geocoding_pipeline.phase02.cli \
  --source-root /path/to/csv_files \
  --phase01-run-dir reports/generated/phase01/<approved_run_id> \
  --run-scope SMOKE_TEST \
  --source-root-label csv_files \
  --include remaining_addresses_00103.csv \
  --include remaining_addresses_00205.csv
```

Controlled staging is written beneath
`staging/controlled/phase02_v1/runs/<run_id>/`; portable generated diagnostics
are written beneath `reports/generated/phase02/<run_id>/`. Both are ignored by
Git. A smoke-scope PASS creates `_SCOPE_SUCCESS.json`, never the full-run
`_SUCCESS.json`, and does not complete Phase 2 or authorize Phase 3.

`FULL_CONVERSION` additionally requires the CLI operator acknowledgement
`--authorize-full-conversion`. That guard never substitutes for explicit user
authorization, which must be obtained separately before running all 206 files.

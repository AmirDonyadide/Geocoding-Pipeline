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

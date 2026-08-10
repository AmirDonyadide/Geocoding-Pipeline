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

## Phase 3 framework interface

Phase 3 framework implementation is limited to deterministic component logic,
fictional validation, schemas, controlled-reference interfaces, atomic-output
infrastructure, and a deterministic pilot sampler. It has no command that reads
or transforms Phase 2 rows. A real pilot and full Phase 3 processing require
separate authorization.

Validate the bundled rule registry and display privacy-safe framework metadata:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli validate-rule-registry
python3 -m safe_geocoding_pipeline.phase03.cli framework-info
```

Inspect the portable manual-review label schema:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli manual-review-schema
```

The official Unicode 16.0.0 Script artifact, manifest, and Unicode License v3
notice are bundled. The pinned UNSD M49 operational artifact remains in ignored
controlled storage because its institutional/redistribution terms require
clarification. Validate both pinned production references without reading Phase
2 rows:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli validate-production-references \
  --country-artifact /controlled/path/un_m49_country_area_codes_v1.json

python3 -m safe_geocoding_pipeline.phase03.cli validate-country-reference \
  --manifest /controlled/path/un-m49-manifest.json \
  --artifact /controlled/path/un_m49_country_area_codes_v1.json

python3 -m safe_geocoding_pipeline.phase03.cli validate-script-reference \
  --manifest src/safe_geocoding_pipeline/phase03/resources/references/unicode_ucd_16_0_0/manifest.json \
  --artifact src/safe_geocoding_pipeline/phase03/resources/references/unicode_ucd_16_0_0/Scripts.txt
```

The fictional-only performance harness requires an explicit scenario, row
count, controlled country artifact, and generated-output directory. It never
discovers Phase 2 data:

```bash
python3 -m safe_geocoding_pipeline.phase03.benchmark \
  --scenario STRUCTURED_HEAVY \
  --rows 30000 \
  --country-artifact /controlled/path/un_m49_country_area_codes_v1.json \
  --output-directory reports/generated/phase03/synthetic-benchmark
```

The library sampler accepts already profiled `PilotCandidate` metadata and
returns separate development and locked-evaluation identities plus a portable
seal containing only counts and identity digests. It is not invoked by the CLI,
so ordinary framework commands cannot accidentally create a real pilot.

The frozen declarative registry is packaged from
`src/safe_geocoding_pipeline/phase03/resources/rule_registry_v2.json`. Its
execution disposition is part of the registry/configuration identity;
development-shadow rules never run in locked-evaluation or authoritative
scope. Phase 3
framework validation uses fictional fixtures only:

```bash
python3 -m pytest tests/test_phase03_*.py
python3 -m ruff check .
python3 -m mypy src tests
```

The future manual-review artifact uses the 21-column schema returned by
`manual-review-schema`; it binds the closed `manual_review_reason_codes_v1`
vocabulary and stores a hashed review identity and labels, not raw addresses,
provider IDs, cities, or postcodes.

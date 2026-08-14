# SAFE geocoding pipeline

The repository implements the reviewed project workflow documented under `docs/`.
Work proceeds one phase at a time.

## Execution-site policy

**HEAVY PRODUCTION PROCESSING = GOETHE-NHR ONLY.** The MacBook is for code,
documentation, Git, unit/synthetic tests, small diagnostics, lightweight
validation, and small controlled manual-review work. Complete production Phase
2 scans, at least one million production rows, multi-GB state, work expected to
run at least ten minutes locally, and full-data joins/grouping/deduplication/
transformation/geocoding/selection/validation/reconciliation must run through
SLURM on Goethe-NHR. When uncertain, default to the cluster. The exact policy,
guard markers, paused-run record, and cluster workflow are documented in
`docs/EXECUTION_POLICY.md`.

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

Phase 3 includes deterministic component logic, fictional validation, schemas,
controlled-reference interfaces, atomic-output infrastructure, and a bounded
synthetic-tested pilot runner. The production sampling classifier contract is
frozen as `phase03_sampling_contract_v1`; its implementation is ready for
review. A real pilot and full Phase 3 processing still require separate
authorization.

Validate the bundled rule registry and display privacy-safe framework metadata:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli validate-rule-registry
python3 -m safe_geocoding_pipeline.phase03.cli framework-info
```

`pilot_ready=true` reports the completed technical/methodology/privacy gate;
`real_pilot_authorized=false` preserves the separate authorization boundary.
The command cannot select or read a pilot.

Inspect the portable manual-review label schema:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli manual-review-schema
```

The official Unicode 16.0.0 Script artifact and the minimum official CLDR 46.1
country-reference inputs are bundled with their Unicode License v3 notices.
ISO 3166 remains the normative code-system authority; CLDR is the operational
machine-readable mapping. UNSD M49 is not an active runtime dependency.
Validate the pinned production references without reading Phase 2 rows:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli validate-production-references

python3 -m safe_geocoding_pipeline.phase03.cli validate-country-reference

python3 -m safe_geocoding_pipeline.phase03.cli validate-script-reference \
  --manifest src/safe_geocoding_pipeline/phase03/resources/references/unicode_ucd_16_0_0/manifest.json \
  --artifact src/safe_geocoding_pipeline/phase03/resources/references/unicode_ucd_16_0_0/Scripts.txt
```

The fictional-only performance harness requires an explicit scenario, row
count, and generated-output directory. It loads only bundled references and
never discovers Phase 2 data:

```bash
python3 -m safe_geocoding_pipeline.phase03.benchmark \
  --scenario STRUCTURED_HEAVY \
  --rows 30000 \
  --output-directory reports/generated/phase03/synthetic-benchmark
```

Inspect the future production plan without opening the supplied path:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli pilot-plan \
  --input-path /explicit/phase02/run \
  --output-path /explicit/controlled/pilot/run \
  --git-commit "$(git rev-parse HEAD)"
```

The plan reports the frozen 16-column contract and explicit passes with
`data_read=false`. The out-of-core sampler stores only
32-byte identities, deterministic scores and categorical memberships in an
owner-only SQLite database. Controlled identity files and the portable seal are
checksummed and atomic; the seal contains counts/digests, never identity lists.

The remaining production stages are deliberately separate commands:
`pilot-profile`, `pilot-select`, `pilot-validate-identity-set`,
`pilot-materialize-development`, `development-transform`,
`development-review-sample`, and `pilot-validate`. Each requires explicit
manifest/input/output arguments. None performs implicit discovery or advances
to the next stage. Do not run them on real Phase 2 data without the separately
recorded authorization for that exact operation.

When these commands target the authoritative production snapshot,
`pilot-profile`, `pilot-select`, complete-snapshot validation, and
`pilot-materialize-development` fail before production input access unless both
`SAFE_EXECUTION_SITE=goethe-nhr` and a non-empty `SLURM_JOB_ID` are present.
There is no force-local flag. Use the reviewed workflow in
`cluster/goethe_nhr/phase03_development_pilot.sbatch`; do not invoke individual
production stages on the MacBook.

The Phase 1 `FULL_INVENTORY` and Phase 2 `FULL_CONVERSION` scopes likewise use
the shared cluster guard for future reruns; their historical completed runs are
not modified.

The separately authorized development join requires explicit paths and never
discovers production data:

```bash
python3 -m safe_geocoding_pipeline.phase03.cli pilot-materialize-development \
  --phase02-manifest /explicit/phase02/dataset_manifest.json \
  --input-path /explicit/shard.parquet \
  --development-identities /controlled/development.identities.bin \
  --locked-identities /controlled/locked_evaluation.identities.bin \
  --output-path /controlled/development_payload.parquet
```

Do not run that command against real data without explicit authorization. A
synthetic-only bounded-state benchmark is available through:

```bash
python3 -m safe_geocoding_pipeline.phase03.pilot_benchmark \
  --rows 100000 \
  --output-directory reports/generated/phase03/pilot-runner-benchmark
```

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

The immutable generated v1 manual-review template uses the 21-column schema
returned by `manual-review-schema`. The DEVELOPMENT human-review workflow uses
the separate component-specific portable-v2 label schema and resumable terminal
interface documented in `docs/PHASE03_REVIEW_INTERFACE.md`. Both bind the closed
`manual_review_reason_codes_v1` vocabulary. Portable review outputs store hashed
review identities and labels, never raw addresses, provider IDs, cities, or
postcodes.

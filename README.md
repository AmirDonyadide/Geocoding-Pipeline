# SAFE Geocoding Pipeline

## Purpose

The SAFE Geocoding Pipeline prepares protected company and facility addresses
for the self-hosted SAFE Pelias geocoder. It converts immutable source CSV data
into traceable, conservatively derived address candidates, validates those
candidates, and will eventually generate a small set of controlled Pelias
queries. The aim is a scientifically defensible point location—not merely any
coordinate returned by a geocoder.

## Why preprocessing is needed

Raw address records vary by country, script, completeness, encoding quality,
and the relationship between standard and native representations. Address
lines 1–4 have no safe global interpretation, missing-reference coverage is not
proof that an address is invalid, and a geocoder response is not automatically
a scientifically usable match. Preprocessing is therefore separate from
geocoding so that every transformation, validation result, candidate, and
query can be inspected and reproduced.

## Current status

The DEVELOPMENT pipeline is accepted through Stage 6. Later stages have not
started.

| Stage | Name | Status | Data effect |
|---:|---|---|---|
| 0 | Source inventory | **ACCEPTED** | Inventories and fingerprints sources; no row transformation |
| 1 | Lossless ingestion | **ACCEPTED** | Converts CSV to Parquet without changing source values; adds stable provenance |
| 2 | Schema and provenance harmonization | **ACCEPTED** | Preserves incoming fields and adds four derived structural fields |
| 3 | Safe text cleaning | **ACCEPTED** | Adds derived `*_clean` values and ordered audit reasons; raw fields remain unchanged |
| 4 | Lowercase canonical forms | **`STAGE_4_ACCEPTED`** | Appends exact Python Unicode lowercase representations; all upstream values remain unchanged |
| 5 | Address reconstruction | **`STAGE_5_ACCEPTED`** | Appends separate clean/lower standard/native line-body candidates and compact provenance |
| 6 | Early exact deduplication | **`STAGE_6_ACCEPTED`** | Preserves 35,000 rows and maps 69,747 occurrences to 51,779 exact candidates |
| 7–19 | Parsing, validation, and query preparation | **NOT STARTED** | Planned derived representations only |

Production Stage 0 and Stage 1 are accepted for
`production_population_1411_v1` (1,411 files; 141,048,582 rows). Production
Stage 2 through Stage 6 have not started.

## Architecture

```text
immutable source CSV
  -> Stage 0: inventory
  -> Stage 1: lossless Parquet + stable row identity
  -> Stage 2: schema/provenance harmonization
  -> Stage 3: safe derived text cleaning
  -> Stage 4: exact derived Python Unicode lowercase
  -> Stage 5: separate deterministic address-line body reconstruction
  -> Stage 6: exact lowercase candidate registry + complete row map
  -> Stages 7–19: planned parsing, validation, and query QA
  -> self-hosted SAFE Pelias
```

Raw source rows are never deduplicated away. Future deduplication applies to
candidate or query representations and always retains a complete mapping back
to every `stable_source_row_id_v1`.

## Repository structure

| Path | Contents |
|---|---|
| `src/safe_geocoding_pipeline/` | Pipeline package, contracts, execution guards, accepted stages, reporting, and historical source-foundation code |
| `tests/` | Synthetic/unit tests and guarded integration tests; no protected records |
| `cluster/goethe_nhr/` | Reviewed SLURM and environment assets for Goethe-NHR |
| `scripts/` | Controlled transfer and synchronization helpers |
| `docs/` | Current project, pipeline, workflow, privacy, execution, and reproducibility documentation |
| `docs/stages/` | Stage 0–6 scientific records and candidate evidence |
| `docs/history/` | Accepted source-foundation records that predate the Stage terminology |
| `reports/development/` | Sanitized, Git-safe aggregate DEVELOPMENT evidence |

The older `phase01` and `phase02` package namespaces remain because accepted
source-foundation work underpins Stage 0 and Stage 1. The active library-first
Stage 0–6 adapters live under `src/safe_geocoding_pipeline/preprocessing/`.

## DEVELOPMENT, HOLDOUT, and production

- **DEVELOPMENT:** 35,000 protected rows used for stage design and evaluation.
- **Fixed DEVELOPMENT review subset:** 500 deterministic DEVELOPMENT rows used
  for same-row qualitative inspection across stages. Fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
- **HOLDOUT:** 15,000 protected rows, untouched, physically separate, and
  sealed until one
  explicitly authorized final evaluation after Stages 2–19 are frozen.
- **Production population:** 1,411 files and 141,048,582 rows. Production
  Stage 0 and Stage 1 are accepted; production Stages 2–6 have not started.

Benchmark V1 remains permanently bound to its accepted 1,405-file population;
the later six production files do not change or rebuild it.

## Privacy

> **Protected addresses and row-level artifacts must remain on controlled local
> or Goethe-NHR infrastructure. Never send them to public APIs, external
> geocoders, web services, LLMs, or Git.**

Git contains only source code, contracts, synthetic fixtures, reproducible
execution assets, hashes, sanitized reports, aggregate metrics, and
documentation. See [Privacy and security](docs/PRIVACY_AND_SECURITY.md).

## Quick start

The package supports Python 3.11 or newer for local development. Reproducing
the accepted Stage 3–6 Goethe execution requires its exact
pinned Python 3.14.3 runtime and Unicode 16.0.0 contract.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
python3 -m pytest -m "not requires_production_transfer_payload"
```

Useful local checks:

```bash
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests
```

Protected inputs and derived artifacts are environment-specific and ignored by
Git. Typical controlled roots are `data/controlled/` locally and
`derived/controlled/` on Goethe-NHR. Do not create portable configuration with
personal absolute paths. Sanitized evidence is available under
`reports/development/`; protected same-row inspection is explained in
[Inspecting results](docs/INSPECTING_RESULTS.md).

## Documentation

- [Project overview](docs/PROJECT_OVERVIEW.md)
- [Authoritative Stage 0–19 pipeline](docs/PIPELINE.md)
- [Data flow and data model](docs/DATA_FLOW.md)
- [Inspecting completed-stage results](docs/INSPECTING_RESULTS.md)
- [DEVELOPMENT workflow](docs/DEVELOPMENT_WORKFLOW.md)
- [Execution guide](docs/EXECUTION.md)
- [Detailed execution policy](docs/EXECUTION_POLICY.md)
- [Privacy and security](docs/PRIVACY_AND_SECURITY.md)
- [Reproducibility](docs/REPRODUCIBILITY.md)
- [Decision register](docs/DECISIONS.md)
- [Current progress](docs/DEVELOPMENT_PROGRESS.md)
- [Benchmark V1](docs/BENCHMARK_SAMPLE.md)
- [Accepted stage records](docs/stages/README.md)
- [Historical records](docs/history/README.md)

## Current next stage

**Stage 7 — libpostal parsing — DEVELOPMENT candidate not ready.** The revised
supervisor diagnostic found that all four prior giant crashes disappear under
an uncapped 180 GiB allocation, so the earlier 48 GiB ceiling was materially
causal and the proposed technical-failure status cannot yet be frozen. Stage 6
remains accepted. HOLDOUT, production Stages 2–7, Stage 8, independent review,
and geocoding remain unauthorized and not started. See the
[Stage 7 record](docs/stages/STAGE07_LIBPOSTAL_PARSING.md).

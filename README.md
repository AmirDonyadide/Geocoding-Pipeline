# SAFE Geocoding Pipeline

Research pipeline for preparing protected Orbis company and facility addresses
for SAFE's self-hosted Pelias service. It preserves source records, derives
standard and native address candidates, and records the evidence needed to
judge whether an eventual coordinate is suitable for point-level research.

DEVELOPMENT Stages 0–11 are accepted and frozen. Stage 10 owner acceptance binds
remediated job `1785683` after final independent rereview passed with zero
candidate defects; see the [acceptance record](reports/development/stage10.md).
Stage 11 [owner acceptance](docs/stages/STAGE11_OWNER_ACCEPTANCE.md) freezes
job `1788751` after independent review `1790315` passed with zero candidate
defects. Stage 12 has a [design-only proposal](docs/stages/STAGE12_PELIAS_TOPN_RETRIEVAL.md)
with owner review incorporated, ready for owner freeze; it is not frozen,
implemented or authorized for execution.
Production Stages 0–1 are accepted; production Stage 2 onward has not started. See
[current progress](docs/DEVELOPMENT_PROGRESS.md).

## Pipeline

| Stages | Result |
|---|---|
| 0–2 | Verified source population, lossless Parquet, stable row identity and structural indicators |
| 3–5 | Derived clean text, exact Unicode lowercase, separate standard/native line-body candidates |
| 6–8 | Exact candidate deduplication with complete map-back, parser evidence, lossless evidence index |
| 9 | Conservative offline country, postal-code, locality and administrative reference evidence |
| 10 | Accepted bounded query hypotheses; operating budget UNSELECTED |
| 11 | Accepted exact semantic request deduplication with complete hypothesis map-back |
| 12–14 | Proposed Pelias retrieval, scoring and granularity/abstention |

Parser labels and reference matches are evidence, not verified address truth.
A returned geocoder feature is not automatically a usable research location.
The [pipeline specification](docs/PIPELINE.md) defines each boundary and retains
the legacy Stage 0–19 plan. Stage 19 was the older query-deduplication/QA gate,
not a later dependency. The reconciled rule requires owner-frozen Stage 12,
validated implementation and separate phase/workload approvals; no geocoding
is currently authorized.

## Local setup

The package declares Python 3.11 or newer. Install the pinned dependencies from
[pyproject.toml](pyproject.toml):

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

Local checks that need no protected inputs:

```bash
python3 scripts/validate_stage_reports.py
python3 scripts/validate_stage10_implementation.py
python3 -m ruff check src tests scripts
python3 -m ruff format --check src tests scripts
python3 -m mypy src
python3 -m pytest -m "not requires_production_transfer_payload"
```

The test command excludes four protected-transfer tests. Some remaining tests
require exact Python 3.14.3 / Unicode 16.0.0 or the separately built Stage 10
ICU runtime; installing the package alone does not reproduce those environments.
See [runtime and validation details](docs/EXECUTION.md#runtime-and-dependencies)
for prerequisites and known historical static-check failures.

## Input and outputs

Input is strict UTF-8 CSV with 15 string columns, including four standard and
four native address lines. Postal codes remain strings; quoted multiline
fields are logical records, not separate rows. There is no TSV autodetection.
The [data model](docs/DATA_FLOW.md#raw-source-record) lists the schema and
derived fields. Raw files are immutable and provider `id` is not a global key.

The production population is `production_population_1411_v1`: **1,411 files,
141,048,582 rows**. Benchmark V1 remains tied to its earlier **1,405-file**
population: **35,000 DEVELOPMENT** and **15,000 sealed HOLDOUT** rows. The six
later files do not change the benchmark.

Protected Parquet, manifests, mappings and review views live in controlled,
ignored storage, typically `data/controlled/` locally and `derived/controlled/`
on Goethe. Runs publish new immutable bundles under their stage contracts.
Git contains only code, contracts, synthetic fixtures, execution assets,
documentation and sanitized evidence. Start with the [reports index](reports/README.md)
for results or [Inspecting results](docs/INSPECTING_RESULTS.md) for authorized
small DEVELOPMENT review.

## Running a stage

Stage implementations live in `src/safe_geocoding_pipeline/preprocessing/stages/`;
`tests/` contains synthetic/unit and guarded integration tests. `scripts/` holds
validation, runtime-build and controlled-transfer helpers. There is no end-to-end
geocoding command: each stage has reviewed inputs, runtime, launcher and
authorization. CLI discovery is safe locally:

```bash
safe-geocoding-stage00 --help
safe-geocoding-stage10 --help
safe-geocoding-stage10 describe-contract
```

`python3 -m safe_geocoding_pipeline` invokes the Stage 0 inventory CLI, not the
whole pipeline. Stage 1 currently validates/adopts existing ingestion bundles;
the historical converter CLI was removed.

Protected/heavy execution uses [Goethe-NHR SLURM assets](cluster/goethe_nhr/README.md)
at an exact pushed Git SHA and requires `SAFE_EXECUTION_SITE=goethe-nhr` plus a
scheduler-provided `SLURM_JOB_ID`. Follow the [execution guide](docs/EXECUTION.md).
Documentation or a successful test does not authorize a run or the next stage.

Protected addresses and row-level artifacts must never enter public APIs,
external geocoders, web services, LLM prompts or Git. HOLDOUT remains sealed.
See [privacy and security](docs/PRIVACY_AND_SECURITY.md).

## Documentation

| Need | Document |
|---|---|
| Research purpose and scientific limits | [Project overview](docs/PROJECT_OVERVIEW.md), [project brief](docs/PROJECT_BRIEF.md) |
| Architecture and field lineage | [Pipeline](docs/PIPELINE.md), [data flow](docs/DATA_FLOW.md) |
| Status, contracts and evidence | [Progress](docs/DEVELOPMENT_PROGRESS.md), [stage records](docs/stages/README.md), [reports](reports/README.md) |
| Development and review | [Workflow](docs/DEVELOPMENT_WORKFLOW.md), [reporting](docs/DEVELOPMENT_REPORTING.md), [Benchmark V1](docs/BENCHMARK_SAMPLE.md) |
| Execution and reproducibility | [Execution](docs/EXECUTION.md), [policy](docs/EXECUTION_POLICY.md), [reproducibility](docs/REPRODUCIBILITY.md) |
| Decisions and historical provenance | [Decision register](docs/DECISIONS.md), [source foundation](docs/history/README.md) |

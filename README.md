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

The DEVELOPMENT pipeline is accepted through Stage 9. Stage 7 is accepted as
reproducible parser evidence, not semantic component or geographic truth.
The first Stage 8 candidate failed independent review. Its first publication
repair preserved Stage 8 science, and DEVELOPMENT job `1763984` passed exact
reconciliation for executable `bd89a032…`. Independent rereview then found a
post-effect rename failure hole in that executable. The second bounded repair
at `bdea7232…` completed DEVELOPMENT job `1764219`; exact scientific and
publication reconciliation passed. Independent rereview then failed its post-
commit CLI status and final-ownership binding. Third bounded repair
`c04cb972…` completed the single authorized DEVELOPMENT materialization as job
`1764273`; its scientific, publication, and terminal-contract reconciliation
passed. Exact candidate `231cdbf9…` then passed corrected independent rereview
job `1764376` with zero candidate defects and is accepted as
`STAGE_8_ACCEPTED`. Jobs `1763747`, `1763984`, and `1764219` remain historical
evidence for their exact executables only. Stage 9 is `STAGE_9_ACCEPTED` under
owner decision D060: executable `3e10ac7c…`, DEVELOPMENT job `1771191`, independent
review `a9ae443c…` / job `1772139`, zero candidate defects. Acceptance is offline
reference evidence only, not address validity or geocoding accuracy; see the
[accepted Stage 9 report](reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14).

| Stage | Name | Status | Data effect |
|---:|---|---|---|
| 0 | Source inventory | **ACCEPTED** | Inventories and fingerprints sources; no row transformation |
| 1 | Lossless ingestion | **ACCEPTED** | Converts CSV to Parquet without changing source values; adds stable provenance |
| 2 | Schema and provenance harmonization | **ACCEPTED** | Preserves incoming fields and adds four derived structural fields |
| 3 | Safe text cleaning | **ACCEPTED** | Adds derived `*_clean` values and ordered audit reasons; raw fields remain unchanged |
| 4 | Lowercase canonical forms | **`STAGE_4_ACCEPTED`** | Appends exact Python Unicode lowercase representations; all upstream values remain unchanged |
| 5 | Address reconstruction | **`STAGE_5_ACCEPTED`** | Appends separate clean/lower standard/native line-body candidates and compact provenance |
| 6 | Early exact deduplication | **`STAGE_6_ACCEPTED`** | Preserves 35,000 rows and maps 69,747 occurrences to 51,779 exact candidates |
| 7 | libpostal parsing/evidence | **`STAGE_7_ACCEPTED`** | Preserves exact raw ordered parser evidence, applicability/technical provenance, warnings, and complete map-back; components remain hypotheses only |
| 8 | Lossless address-evidence projection | **`STAGE_8_ACCEPTED`** | Candidate `231cdbf9…`, executable `c04cb972…`, job `1764273`, and corrected independent rereview job `1764376`; zero candidate defects and unchanged science |
| 9 | Conservative offline reference evidence | **`STAGE_9_ACCEPTED`** | 51,779 candidates; four-state capability-scoped evidence; no source correction or final geographic truth |
| 10 | Bounded multi-hypothesis query generation | **DESIGN READY FOR OWNER REVIEW** | [Documentation-only candidate](docs/stages/STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md); owner revisions incorporated; not implemented or executed |
| 11–14 proposed | Query QA, retrieval, scoring, and final granularity | **PROPOSED — NOT STARTED** | No design approval or execution authorization |

Production Stage 0 and Stage 1 are accepted for
`production_population_1411_v1` (1,411 files; 141,048,582 rows). Production
Stage 2 and later stages have not started.

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
  -> Stage 7: accepted evidence-only libpostal projection
  -> Stage 8: accepted lossless evidence projection/index
  -> Stage 9: accepted conservative offline reference evidence
  -> proposed Stages 10–14: hypotheses, query QA, retrieval, scoring
  -> self-hosted SAFE Pelias
```

Raw source rows are never deduplicated away. Future deduplication applies to
candidate or query representations and always retains a complete mapping back
to every `stable_source_row_id_v1`.

## Repository structure

| Path | Contents |
|---|---|
| `src/safe_geocoding_pipeline/` | Pipeline package, contracts, execution guards, accepted Stage 0–9 implementations, and reporting |
| `tests/` | Synthetic/unit tests and guarded integration tests; no protected records |
| `cluster/goethe_nhr/` | Reviewed SLURM and environment assets for Goethe-NHR |
| `scripts/` | Current controlled transfer helpers |
| `docs/` | Current project, pipeline, workflow, privacy, execution, and reproducibility documentation |
| `docs/stages/` | Stage 0–9 records and their frozen contracts/history |
| `docs/history/` | Accepted source-foundation records that predate the Stage terminology |
| `reports/development/` | One human-readable authoritative DEVELOPMENT report per accepted Stage 0–9 |
| `reports/generated/` | One machine-readable sanitized evidence summary per accepted Stage 0–8 |
| `review/stage09_independent/` | Preserved independent Stage 9 review harness, final verdict, and sanitized aggregate evidence |

The single authoritative implementation pipeline is Stage 0–9 under
`src/safe_geocoding_pipeline/preprocessing/stages/`. Frozen phase-prefixed
artifact identifiers may appear only where Stage 0 or Stage 1 validates
immutable source-foundation provenance created before Stage terminology.

## DEVELOPMENT, HOLDOUT, and production

- **DEVELOPMENT:** 35,000 protected rows used for stage design and evaluation.
- **Fixed DEVELOPMENT review subset:** 500 deterministic DEVELOPMENT rows used
  for same-row qualitative inspection across stages. Fingerprint:
  `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
- **HOLDOUT:** 15,000 protected rows, untouched, physically separate, and
  sealed until one
  explicitly authorized final evaluation after Stages 2–19 are frozen.
- **Production population:** 1,411 files and 141,048,582 rows. Production
  Stage 0 and Stage 1 are accepted; production Stage 2 and later have not started.

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
the accepted Stage 3–9 Goethe execution requires the exact pinned Python 3.14.3
runtime and Unicode 16.0.0 contract plus each stage's frozen dependencies and
artifacts.

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
personal absolute paths. Start with the [reports index](reports/README.md) for
the authoritative human and machine evidence; protected same-row inspection is
explained in [Inspecting results](docs/INSPECTING_RESULTS.md).

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
- [Accepted Stage 0–9 reports](reports/README.md)

## Current next action

Stage 8 is **`STAGE_8_ACCEPTED`** on DEVELOPMENT at exact candidate
`231cdbf9db755fb56486c46b3b3faa02f5b5f3b6`, executable
`c04cb97214a9f1e5d2b80512c756400321eefa80`, job `1764273`, manifest
`2a50bd8c…`, and unchanged logical dataset `9c9d431c…`. Corrected independent
rereview commit `f8a456f…` and job `1764376` passed with zero candidate defects.
Jobs `1763747`, `1763984`, and `1764219` and all failed reviews remain truthful
historical evidence for their exact executable lineages. Stage 9 is now
**`STAGE_9_ACCEPTED`**, frozen by `stage09-offline-reference-evidence-v1` after
independent review PASS with zero candidate defects. No rerun was required.
The separately authorized Stage 10 bounded multi-hypothesis
[design candidate](docs/stages/STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md) is
**FROZEN FOR FINAL OWNER REVIEW** after the mandatory context/ceiling/transform
revisions. Implementation and execution remain **NOT STARTED**.
Next: final owner approval to implement the exact revised design.
HOLDOUT remains sealed;
production Stage 2 and later, Senzing, and geocoding remain unauthorized. See the
[Stage 8 design](docs/stages/STAGE08_ADDRESS_EVIDENCE_PROJECTION.md) and
[current progress](docs/DEVELOPMENT_PROGRESS.md).

# SAFE Geocoding Pipeline — project brief

## 1. Research objective

The project constructs defensible point locations for protected company and
facility records so that researchers can link establishments to fine-grained
environmental, remote-sensing, climate, land-cover, pollution, biodiversity,
and neighborhood measures. The relevant location concept is a physical
building, plant, branch, store, facility, or comparable business site.

City, administrative-region, and country centroids are not adequate for the
main point-level analysis. They may be diagnostically useful, but they cannot
represent building-scale exposure. The pipeline must therefore distinguish a
geocoder response from a scientifically usable coordinate.

## 2. Project outcome

The eventual research dataset must retain, for every source row:

- immutable source values and stable source provenance;
- every accepted derived representation used in preprocessing;
- candidate, component, validation, correction, and query lineage;
- geocoder attempts and returned match evidence;
- the selected result and deterministic selection reason;
- diagnostic precision/quality status;
- `usable_for_analysis`; and
- versioned contracts, references, code, execution, and review provenance.

The pipeline is not complete at geocoding request success. A coordinate is
accepted only when returned precision and match type are suitable and no major
geographic contradiction is present.

## 3. Source data characteristics

The source consists of protected Orbis company/facility address CSV files. The
current production population, `production_population_1411_v1`, contains 1,411
files and 141,048,582 logical rows. Accepted production Stage 0 and Stage 1 bind
that exact scope.

The accepted Benchmark V1 is permanently based on an earlier frozen 1,405-file
population. It contains 50,000 rows: 35,000 DEVELOPMENT and 15,000 sealed
HOLDOUT. Six files delivered later are production data but do not alter the
benchmark.

The observed and accepted source contracts require attention to:

- logical CSV records rather than physical lines;
- quoted multiline values;
- multi-million-character fields;
- strict UTF-8 and explicit CSV behavior;
- 15 source columns represented as strings;
- postal codes that must not be numerically coerced;
- provider IDs that are not assumed globally unique;
- native and non-native Unicode values;
- heterogeneous missingness and missing-marker vocabulary; and
- address lines 1–4 without fixed universal semantics.

Raw source files are immutable. Malformed, changed, incomplete, or
out-of-contract input fails or enters explicit diagnostics; it is never
silently cleaned, skipped, truncated, or null-padded.

## 4. Why preprocessing precedes SAFE Pelias

Direct raw-address geocoding would combine several scientific decisions into an
opaque query string: line interpretation, representation authority, Unicode
repair, missingness, country semantics, component selection, abbreviation,
correction, and fallback behavior. It would also repeat identical work and make
failures difficult to diagnose.

The separate pre-geocoding pipeline makes each decision reviewable. It preserves
raw text, creates derived fields in narrow stages, reconstructs standard/native
candidates separately, parses and maps components, validates syntax and
geography using independent evidence, proposes only conservative corrections,
selects query components, and deduplicates identical calls while retaining full
map-back.

SAFE Pelias is self-hosted and receives protected queries only after Stage 19
acceptance and separate authorization. No external geocoder, public API, web
service, or LLM receives protected address data.

## 5. Scientific principles

### 5.1 Preservation and identity

- Source values are never overwritten.
- Every transformation is derived and versioned.
- `stable_source_row_id_v1` is preserved across every stage.
- Provider `id` is retained but is not the pipeline row key.
- Source rows are never deduplicated away.
- Candidate/query deduplication retains complete mappings to source rows.
- Failed and rejected runs remain explicit evidence.

### 5.2 Representations

Standard and native address fields both originate from Orbis. Standard values
may contain English translations; native values often retain original scripts.
Neither representation is globally assumed more authoritative. They remain
separate candidates and are evaluated independently, including by country.

All eight address-line fields are never blindly concatenated. If transliteration
is introduced in a future reviewed stage, it remains a separate representation
and does not replace native text.

### 5.3 Conservative validation and correction

Pre-geocoding validation uses:

- `CONFIRMED`;
- `MISMATCH`;
- `NOT_FOUND`;
- `AMBIGUOUS`;
- `UNSUPPORTED`; and
- `INVALID_FORMAT`.

Open reference data is incomplete and geographically uneven. `NOT_FOUND` is not
invalidity, and `MISMATCH` requires strong positive contradictory evidence.
Future correction favors high precision and abstention. It must retain the
original, proposal, reference/version, evidence, and decision.

### 5.4 Geocoding quality

The preferred SAFE Pelias endpoint is `/v1/search/structured`, normally with
`size=1`. Credentials are runtime-only, and normal concurrency is 2–4 total
requests across the complete process.

An address-layer exact match without a major contradiction is expected to be
usable. Acceptance of interpolated address matches remains open until later
pilot/manual evidence. Street, venue, locality, localadmin, region, country,
fallback, and other coarse results are not usable for point-level research.
Confidence is supporting evidence, not a standalone decision rule.

## 6. Library-first preprocessing

The active architecture uses mature offline libraries and pinned references
where they satisfy privacy, licensing, reproducibility, and scientific
contracts. SAFE code provides narrow orchestration, identity/provenance,
evidence aggregation, validation semantics, conservative policy, execution
guards, and verified gaps.

Current/planned technology choices are:

| Stage | Primary technology direction |
|---:|---|
| 0 | Existing Phase 1 inventory, Python `hashlib`, Python `csv` |
| 1 | PyArrow/Parquet, DuckDB |
| 2 | PyArrow, SAFE schema/provenance layer |
| 3 | Python `unicodedata`, ftfy, regex/Arrow, SAFE orchestration |
| 4 | Python Unicode `lower()` |
| 5 | SAFE reconstruction; possibly address-format metadata |
| 6 | DuckDB/Polars/hashing |
| 7 | libpostal/pypostal |
| 8 | libpostal plus SAFE component mapping |
| 9 | libpostal resources/dictionaries plus SAFE component-aware policy |
| 10 | pycountry |
| 11 | google-i18n-address plus conservative country rules |
| 12 | DuckDB/Polars/hashing |
| 13 | Pinned direct GeoNames postal data and DuckDB; pgeocode POC only |
| 14 | Overture Maps Addresses, local GeoParquet, DuckDB; optional OSM fallback |
| 15 | RapidFuzz after geographic blocking |
| 16 | SAFE high-precision evidence/correction engine |
| 17 | SAFE geocoding-component selection |
| 18 | SAFE query generation |
| 19 | DuckDB/Polars/PyArrow/hashing |

Pandas is permitted for small DEVELOPMENT inspection/notebooks, not production
transformations. Planned technology does not imply implementation approval.

## 7. Stage sequence and current state

The final pre-geocoding sequence is:

0. source inventory;
1. lossless ingestion;
2. schema and provenance harmonization;
3. safe text cleaning;
4. lowercase canonical forms;
5. address reconstruction;
6. early exact deduplication;
7. libpostal parsing;
8. internal component mapping;
9. component-aware abbreviation/linguistic normalization;
10. country/subdivision normalization;
11. country-specific address/postcode syntax validation;
12. normalized/component-level deduplication;
13. geographic cross-validation;
14. street/house-number validation;
15. constrained fuzzy matching;
16. conservative correction;
17. geocoding-component selection;
18. query generation; and
19. query deduplication plus final QA.

Stages 0–3 are implemented and accepted on DEVELOPMENT. Stages 4–19 are
planned and not started. Production Stage 0 and Stage 1 are accepted;
production Stage 2 and Stage 3 are not started. The detailed stage contracts
and acceptance requirements are in [PIPELINE.md](PIPELINE.md).

## 8. DEVELOPMENT methodology

Every scientific stage follows:

```text
design -> review -> implement -> synthetic tests -> 35k DEVELOPMENT run
       -> aggregate evaluation -> fixed-500 qualitative review
       -> independent review -> accept/freeze -> stop
```

The fixed 500-row subset uses fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.
It provides consistent same-row review while full DEVELOPMENT supplies
quantitative evidence.

If a candidate is rejected, it remains immutable. Only a reviewed minimal fix
creates a new run. Stage 3 v1/v2 is the canonical example: v1 scientific values
were preserved, v2 corrected implementation/reporting scalability, exact
scientific equality was proved, and a new independent review accepted v2.

HOLDOUT is opened once only after the complete Stage 2–19 pipeline is frozen.

## 9. Production and infrastructure

Heavy/protected production execution is Goethe-NHR SLURM only. It requires
`SAFE_EXECUTION_SITE=goethe-nhr` and a non-empty `SLURM_JOB_ID` before data
access. Controlled directories use `0700`; files use `0600`; complete bundles
publish atomically into immutable run directories. Git SHA, runtime, manifests,
fingerprints, and SLURM job identity are recorded.

The MacBook is for code, documentation, Git, synthetic/unit tests, small
diagnostics, lightweight validation, and small controlled DEVELOPMENT review.
Goethe login nodes are orchestration-only. Failed runs are preserved rather
than overwritten. A pending job is not duplicated merely because it has not
finished.

## 10. Repository and reporting boundary

Git contains code, contracts, synthetic fixtures, tests, execution assets,
documentation, hashes, sanitized reports, and aggregate metrics. It never
contains raw address data, row-level DEVELOPMENT/HOLDOUT/production artifacts,
credentials, protected logs, or real geocoder payloads.

Portable sanitized evidence is under `reports/development/`. Controlled
same-row inspection is documented in [INSPECTING_RESULTS.md](INSPECTING_RESULTS.md).
Durable decisions are in [DECISIONS.md](DECISIONS.md); current status is in
[DEVELOPMENT_PROGRESS.md](DEVELOPMENT_PROGRESS.md).

## 11. Current next action

**Stage 4 — Lowercase canonical forms — NOT STARTED.** The next scientific work
is to design Stage 4 and obtain explicit review/approval. This statement is not
authorization to implement it. Production Stage 2 also remains not started and
requires separate authorization.

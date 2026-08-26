# Library-first preprocessing transition

The active preprocessing redesign uses a distinct, versioned library-first
Stage sequence. Historical Phase 1 remains intact and supplies the authoritative
source-scanning machinery for new Stage 0; Stage 0 adds only contract,
validation, fingerprinting, privacy hardening, and adoption. Historical Phase 2
remains the single authoritative CSV-to-Parquet converter used by new Stage 1;
Stage 1 adds only Stage 0 binding, bundle validation, layout-independent logical
identity, and adoption. Historical Phase 3 is frozen as the custom-parser
benchmark baseline. See `docs/STAGE00.md`, `docs/STAGE01.md`, and
`docs/CUSTOM_PREPROCESSING_BASELINE.md`. New stages proceed one reviewed stage
at a time and do not rewrite this historical workflow.

Mature offline libraries and pinned reference datasets are preferred wherever
they meet the accepted scientific, privacy, licensing, and reproducibility
requirements. Custom SAFE code focuses on orchestration, provenance,
deterministic evidence aggregation, conservative policy and correction,
validation semantics, and genuine library/data gaps. The historical custom
parser remains recoverable for controlled comparison; it is not extended as
the active production path.

Library-first Stage 2 defines the stable internal source-row schema used by
later preprocessing. It preserves the exact Stage 1 raw/provenance columns and
adds only four raw-emptiness representation fields. Standard and native address
lines remain independent alternatives. Stage 2 performs no text transformation
and may consume the fixed benchmark's DEVELOPMENT artifact without opening
HOLDOUT. See `docs/STAGE02.md`.

`BENCHMARK_SAMPLE_V1` is a separate fixed selection product used to evaluate
subsequent address-changing stages; it is not Stage 2. It freezes 35,000
protected DEVELOPMENT rows and
15,000 separately protected HOLDOUT rows from the explicitly authorized
1,405-file development population. Sampling uses only immutable provenance and
privacy-safe raw structural features, never later pipeline output. See
`docs/BENCHMARK_SAMPLE.md`.

## Current library-first state

- **Stage 0 — Source inventory:** the accepted 1,405-file snapshot contains
  140,448,582 logical rows and is immutable. Six later files belong only to a
  separately prepared 1,411-file source snapshot. Formal Stage 0 for 1,411 has
  not run, so the accepted 1,405 scientific identities remain exactly as
  recorded and cannot be reinterpreted.
- **Stage 1 — Lossless ingestion:** the scientific contract and
  population-generic implementation are accepted. The historical 206-file
  Parquet execution is preserved. A final 1,411-file conversion has not run and
  must bind to a future accepted 1,411 Stage 0 snapshot.
- **Benchmark Sample V1:** accepted under `benchmark_sample_contract_v1` and
  permanently tied to the 1,405-file snapshot. It contains 35,000 DEVELOPMENT
  and 15,000 sealed HOLDOUT source rows, with zero overlap and zero duplicate
  selected identities. All 1,405 sources are represented. Its fingerprint is
  `014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf`.
- **Stage 2 — Schema and provenance harmonization:** accepted on the complete
  35,000-row DEVELOPMENT artifact under
  `stage02_schema_provenance_harmonization_contract_v1`. The 26-column output
  preserves the exact 22 Stage 1 fields and adds four raw-emptiness
  standard/native fields. It performs no address transformation: 35,000 input
  rows produced 35,000 output rows with no dropped, added, or duplicated stable
  identities.
- **DEVELOPMENT reporting:** the passive
  `development_reporting_contract_v1` framework uses one deterministic fixed
  500-row DEVELOPMENT-only protected subset for same-row qualitative review.
  Git-safe reports contain allowlisted aggregates only. Full 35,000-row metrics
  remain authoritative for development evaluation; HOLDOUT remains sealed.

## Planned library-first preprocessing sequence

The following stages are plans, not implemented or accepted results. Every
stage requires its own design, implementation, DEVELOPMENT evidence, and
freeze. Raw and derived values remain separate throughout.

| Stage | Boundary and intended mature tools |
|---|---|
| 3 — Safe text cleaning | Derived Unicode/encoding repair, whitespace, and safe punctuation using `unicodedata`, `ftfy`, `regex`, and Polars; no aggressive linguistic transformation. |
| 4 — Lowercase canonical forms | Derived lowercase fields only; raw values remain unchanged. |
| 5 — Address reconstruction | Build standard and native Orbis candidates separately; never concatenate all eight source lines blindly. |
| 6 — Early exact deduplication | Deduplicate address candidates, not source rows, and preserve complete map-back. |
| 7 — libpostal parsing | Parse standard and native candidates independently with libpostal/pypostal. |
| 8 — Internal component mapping | Map libpostal labels into a stable SAFE component schema. |
| 9 — Component-aware linguistic normalization | Normalize only after parsing, with component/country/language/script awareness. Blind English rules on native representations are prohibited; transliteration, if used, is a separate derived representation. |
| 10 — Country/subdivision normalization | Use pinned `pycountry` semantics. |
| 11 — Country-specific syntax | Apply `google-i18n-address` plus conservative country-specific address/postcode rules. |
| 12 — Normalized/component deduplication | Deduplicate versioned normalized candidates while preserving all source mappings. |
| 13 — Geographic cross-validation | Use pinned direct GeoNames postal data for postcode/country, postcode/locality, postcode/region, locality/region, and meaningful multi-field checks. `pgeocode` may support a proof of concept but is not the planned production engine. |
| 14 — Street/house-number validation | Use Overture Maps Addresses for positive street/postcode, street/locality, and house/street/postcode evidence. Absence is not invalidity; OSM/osmium is an optional fallback. |
| 15 — Constrained fuzzy matching | Use RapidFuzz only inside geographically blocked candidate sets, never for global fuzzy correction. |
| 16 — Conservative correction | Prefer high precision and preserve original, proposal, reference/version, evidence, and decision status. |
| 17 — Geocoding component selection | Remove or downweight recipient, person, floor, and unit noise only when justified while retaining useful physical-location evidence. |
| 18 — Query generation | Generate standard and native queries independently, with versioned evidence-based alternatives. |
| 19 — Query deduplication and final QA | Execute identical SAFE Pelias calls once and map results back to every relevant source row. |

SAFE Pelias geocoding begins only after Stage 19 acceptance.

## Validation semantics and independent evidence

Pre-geocoding validation uses the closed result vocabulary `CONFIRMED`,
`MISMATCH`, `NOT_FOUND`, `AMBIGUOUS`, `UNSUPPORTED`, and `INVALID_FORMAT`.
Missing from an open reference dataset does **not** mean invalid.

Independent component validation remains necessary even where Pelias contains
overlapping sources such as OSM, GeoNames, or OpenAddresses. It supplies
diagnostics Pelias failure alone cannot explain: format support, postcode and
country consistency, postcode/locality or region mismatch, street evidence,
house-number evidence, ambiguity, and correction provenance.

## Standard/native representations and development method

Colleagues confirmed that both representations originate from Orbis. Some
standard forms are English translations; native is likely the more
authoritative original form, and prior Nominatim processing used native names.
The pipeline therefore evaluates standard and native independently, including
by country, and may geocode both where useful. Priority groups 0 and 1 are the
most useful initial regeocoding groups. Interpolation describes coordinate or
location estimation from postcode or region; it does not necessarily mean
source address text was filled or changed. Remaining country-specific
authority and query-policy questions stay explicitly unresolved until tested.

For every address-changing stage, the development cycle is:

```text
design -> implement -> synthetic tests -> run on 35k DEVELOPMENT
       -> inspect metrics/examples -> tune -> accept/freeze -> next stage
```

After the complete pipeline is frozen, the untouched 15,000-row HOLDOUT is
used once for unbiased final evaluation. It is not repeatedly opened or used
for tuning. A satisfactory result then permits separately authorized full
production execution.

The fixed qualitative review subset and reusable sanitized summaries are
documented in `docs/DEVELOPMENT_REPORTING.md`; current status is summarized in
`docs/DEVELOPMENT_PROGRESS.md`.

Future `FULL_INVENTORY` execution is population-size independent. It requires a
hash-pinned `stage00_population_scope_v1` artifact containing the exact sorted
direct-child CSV path set. The historical Phase 1 description below remains a
record of the accepted 206-file snapshot rather than a generic execution rule.

# Historical Phase 0–13 workflow

This is the approved conceptual workflow. It is not an implementation plan or evidence that a phase has run. Each phase requires design review, implementation approval, validation, a phase report, and an explicit stop before the next phase.

## Phase 0 — Research requirement

- **Objective:** Define the research location concept and required precision.
- **Inputs:** Scientific use case and downstream environmental/remote-sensing linkage needs.
- **Outputs:** Point-level objective, `usable_for_analysis`, diagnostic tier concept, and coarse-result exclusion rule.
- **Major decisions:** Building/plant/branch/store precision is required. Exact address results without major contradiction are expected usable. Interpolated acceptance remains open.
- **STOP gate:** Phase 0 is decided; any change to the scientific objective requires explicit scientific review.

## Phase 1 — Raw-file inventory

- **Objective:** Establish the complete source manifest, parser contract, schema, row counts, anomalies, and identity properties without altering data.
- **Inputs:** All 206 immutable source CSV files.
- **Outputs:** File manifest, parser/schema reports, logical record counts, population/missingness metrics, malformed/oversized-record diagnostics, and ID-overlap findings.
- **Major decisions:** Exact per-file parser rules; whether one verified contract covers all files; stable source-row identity design.
- **STOP gate:** Do not proceed until every file has a reproducible parse outcome, understood schema, detected malformed rows, and documented counts. User approval is required.

## Phase 2 — Controlled staging dataset

- **Objective:** Convert verified CSV inputs into validated analytical staging data without information loss.
- **Inputs:** Raw CSVs, approved Phase 1 manifest, and parser contract.
- **Outputs:** Validated staging data, all raw columns, `source_file`, `source_row_number`, stable source-row ID, rejection diagnostics, and per-file PASS/FAIL reports.
- **Major decisions:** Staging engine/layout, types, partition/file sizing, rejection handling, and validation thresholds.
- **STOP gate:** Source/output counts, schema, IDs, postcodes, Unicode/native text, and sampled cells must reconcile. Failed conversions cannot advance.

## Phase 3 — Canonical address table

- **Objective:** Create conservative, structured derived address components while preserving raw values.
- **Inputs:** Validated staging records and approved cleaning/parsing rules.
- **Outputs:** Clean street, house number, unit, building, postcode, locality, region, country, native variants, parse status, completeness class, and conflict flags.
- **DEVELOPMENT diagnostics:** A versioned, aggregate-only address-pattern
  profiler may examine the fixed DEVELOPMENT payload and parser evidence on
  Goethe-NHR. Its closed morphology labels and suppressed/bounded counts are
  rule-design evidence only; they do not modify parser output or authorize a
  new rule, and LOCKED_EVALUATION is excluded. A second-stage targeted
  diagnostic may cross-tab only predeclared unresolved structural families
  against existing selections, candidate/rule presence, conflicts,
  corroborating components, representation, country, and script. It applies
  the same five-row disclosure threshold and bounded labels; it remains
  descriptive evidence and does not authorize Parser v3.
- **Post-v3.2 DEVELOPMENT opportunity intersection:** A separate sanitized
  profiler measures exact unique identity populations and intersections for
  H1 component-span conflicts, H2 explicit role/street-house overlap, and H3
  narrow adjacent explicit-street/house-like-line relationships. It binds only
  approved DEVELOPMENT artifacts, reports Targeted-v3.1 R01 identity overlap
  separately from scientific reusability, and implements no parser rule. See
  `docs/PHASE03_DEVELOPMENT_HYPOTHESIS_INTERSECTION_PROFILE.md`.
- **Narrow parser-v3 experiment:** The only implemented post-profile hypothesis
  is the explicitly versioned, opt-in
  `conservative_address_parser_v3_experimental` paired street/house rule for a
  strictly gated subset of `WORDS HOUSELIKE_NUM WORDS`. It is evaluated only on
  the existing 8,000 DEVELOPMENT payload, never reruns selection or accesses
  LOCKED_EVALUATION, and cannot be promoted without aggregate comparison and
  protected manual-review evidence. See
  `docs/PHASE03_PARSER_V3_EXPERIMENT.md`.
- **Country-method reproducibility repair:** The explicit Parser-v2.1/v3.1
  lineages change no rule or selected country value. They replace
  hash-seed-dependent method provenance with a fail-closed selected-source
  derivation. Validation reuses only the fixed 8,000 DEVELOPMENT payload and
  performs no pilot selection or LOCKED_EVALUATION access. See
  `docs/PHASE03_COUNTRY_METHOD_REPAIR.md`.
- **Targeted parser-v3 review:** A separate protected DEVELOPMENT workflow may
  review every identity in the exact union of repaired v2.1-v3.1
  scientific-output changes and experimental-rule evidence. A separate
  verification-only Goethe command must first prove the hash-pinned
  8,000/9/11/9/0/2/11 identity-set contract and creates no review inputs or
  databases. Both pseudonymous reviewers eventually receive the full verified
  population under deterministic independent order/blinding. Only aggregate
  scores may leave Goethe; review evidence does not authorize promotion. See
  `docs/PHASE03_PARSER_V3_TARGETED_REVIEW.md`.
- **Parser-v3 change diagnostic:** Before targeted review is initialized, a
  separate Goethe-only aggregate diagnostic reconciles the observed 26
  scientific-change rows with 11 experimental-evidence rows (nine overlap,
  17 change-only, two evidence-only). It reuses `CORE_COLUMNS[5:41]`, reads no
  payload or human labels, rejects LOCKED paths, and reports only fixed-field
  aggregates with rare combination suppression. See
  `docs/PHASE03_PARSER_V3_CHANGE_DIAGNOSTIC.md`.
- **Parser-v3.2 orientation narrowing:** Protected Targeted-R01 evidence
  confirmed that the forward `STREET_NUMBER_RESIDUAL` orientation was 4/4
  jointly correct while the reverse `RESIDUAL_NUMBER_STREET` orientation was
  1/5. The separately versioned v3.2 DEVELOPMENT experiment rejects only the
  reverse orientation. It reuses the fixed 8,000-row payload, never reruns
  selection, and may reuse R01 labels only after exact identity/value/span
  equivalence. See `docs/PHASE03_PARSER_V3_2_EXPERIMENT.md`.
- **Major decisions:** International parsing rules, deterministic normalization, country mapping, handling of geography embedded in free-form lines, and separation of company/unit content.
- **STOP gate:** Review country/address-family behavior, transformations, unresolved records, and evidence that raw values remain traceable and unchanged.

## Phase 4 — Input constraints and quality flags

- **Objective:** Describe whether each canonical address is suitable for a point-level geocoding attempt.
- **Inputs:** Canonical address table.
- **Outputs:** Presence, PO-box, historical, native-version, conflict, oversized-field, completeness, and geocoding-readiness flags.
- **Major decisions:** Eligibility rules and completeness classes; unresolved records remain available for diagnostics.
- **STOP gate:** Review exclusion/eligibility distributions and confirm that coarse or incomplete inputs are not being misrepresented as point-ready.

## Phase 5 — Stable address keys and deduplication

- **Objective:** Determine the true unique-address workload and preserve mappings to all source rows.
- **Inputs:** Canonical components and input-quality flags.
- **Outputs:** Versioned canonical serialization/hash, row-level mapping, unique-address table, repetition counts, and deduplication metrics.
- **Major decisions:** Exact `address_key_v1` serialization, fields included/excluded, unit treatment, collision checks, and versioning.
- **STOP gate:** Review deterministic key behavior, mapping integrity, unique-address counts, country/completeness distributions, and projected API workload.

## Phase 6 — Controlled query strategy

- **Objective:** Define a small, deterministic SAFE query ladder rather than arbitrary address permutations.
- **Inputs:** Unique eligible addresses, components, native/transliterated variants, and conflict flags.
- **Outputs:** Versioned primary/rescue query definitions and query-attempt metadata contract.
- **Major decisions:** Reliable fields for the structured primary request; controlled conditions for removing conflicting fields or using native, transliterated, or free-text rescue variants.
- **STOP gate:** Query construction and logging must be reviewed before any pilot API use. No arbitrary permutation strategy is allowed.

## Phase 7 — Pilot before production

- **Objective:** Measure geocoder behavior, data-group differences, latency, failures, and manual-validation needs on a reproducible stratified sample.
- **Inputs:** Approximately 1,000 unique addresses sampled across countries, completeness classes, scripts, files, priorities, and difficult cases; approved query strategy.
- **Outputs:** Pilot responses, quality/error/latency metrics, manual-review candidates, rescue-query evidence, runtime estimate, and bias diagnostics.
- **Major decisions:** Whether and how to run Pilot 2; Pilot 2 size/design; rescue changes; evidence relevant to interpolated-match acceptance.
- **STOP gate:** Mandatory stop after Pilot 1. Do not launch Pilot 2 or production automatically. Parsing, queries, response parsing, quality logic, and required SAFE RDC coordination must be reviewed.

## Phase 8 — SAFE production execution

- **Objective:** Geocode only unique approved addresses safely and restartably.
- **Inputs:** Approved unique-address workload, query strategy, pilot findings, runtime secret, and production authorization.
- **Outputs:** Durable per-attempt results/errors and checkpoints with statuses, attempts, HTTP metadata, timestamps, latency, and completion state.
- **Major decisions:** Exact approved workload, 2–4 total concurrency, worker/checkpoint design, retry budget/backoff/jitter, resource request, and restart procedure.
- **STOP gate:** Before launch, report call counts, rescue estimate, concurrency, runtime, resources, checkpoints, and restart plan; wait for explicit production approval. After execution, review completeness and failure metrics before selection.

## Phase 9 — Select the best result

- **Objective:** Select candidates deterministically using precision and geographic consistency, not confidence alone.
- **Inputs:** All primary/rescue attempts, returned components, quality fields, and reliable input components.
- **Outputs:** Selected query/candidate, component agreements/conflicts, selection reason, and unresolved/manual-review cases.
- **Major decisions:** Contradiction rules, component comparisons, variant precedence, confidence tie-breaking, and ambiguity handling.
- **STOP gate:** Review selection rules and sampled decisions. No first-feature-is-success shortcut is permitted.

## Phase 10 — Trust categories

- **Objective:** Assign diagnostic tiers and the final point-analysis usability decision.
- **Inputs:** Selected results and consistency diagnostics.
- **Outputs:** `quality_tier`, `usable_for_analysis`, acceptance/exclusion reason, fallback flag, and manual-review flag.
- **Major decisions:** Final interpolated-address acceptance policy, informed by pilot/manual evidence; exact version of quality rules.
- **STOP gate:** The interpolation policy must be explicitly approved and recorded before Tier B can receive a final usability value. Tier A is expected true; C, D, and U are false.

## Phase 11 — Validate geocoded coordinates

- **Objective:** Detect invalid coordinates, geographic contradictions, centroid/fallback patterns, repeated points, and sample-selection bias.
- **Inputs:** Selected coordinates, input/returned geography, tiers, and any separately approved boundary/reference data.
- **Outputs:** Coordinate-range checks, repeated-coordinate diagnostics, geographic validation flags, outlier reports, and quality rates by relevant research group.
- **Major decisions:** Boundary-data source/license/vintage, spatial checks, repeated-coordinate thresholds, and escalation rules.
- **STOP gate:** Investigate suspicious clusters and contradictions. Do not introduce external spatial data or exclude biased groups silently.

## Phase 12 — Merge back to full data

- **Objective:** Return selected results to every original row without row loss or join explosion.
- **Inputs:** Validated row-to-address mapping and final unique-address results.
- **Outputs:** Complete row-level research dataset retaining raw/derived fields, address key, selected result, quality decision, errors, endpoint/date, and pipeline version.
- **Major decisions:** Approved `address_key_v1` left join, duplicate-key safeguards, and treatment of missing mappings.
- **STOP gate:** Source and final row counts must reconcile; one-to-many explosions, duplicate keys, and missing mappings require explicit resolution.

## Phase 13 — Reproducibility and audit

- **Objective:** Make the construction process reproducible, inspectable, and suitable for research reporting.
- **Inputs:** All manifests, rules, versions, reports, mappings, attempts, selections, corrections, and quality outputs.
- **Outputs:** Audit package with parser, cleaning, address-key, query, selection, quality, and pipeline versions; Git revision; service/date metadata; counts; lineage; and phase reports.
- **Major decisions:** Retention, release, access, replication-package, and methods-note contents under institutional policy.
- **STOP gate:** Final review must establish that decisions and outputs can be reproduced and that no essential artifact exists only in unbacked `/work` storage.

## Cross-phase rules

Every phase must report inputs, outputs, counts, assumptions, tests, failures, findings, and unresolved questions. Errors that could corrupt data must fail loudly or enter explicit diagnostics. No phase may silently change raw values, drop records, expose credentials, or authorize the next phase.

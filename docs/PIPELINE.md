# Phase 0–13 workflow

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
  new rule, and LOCKED_EVALUATION is excluded.
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

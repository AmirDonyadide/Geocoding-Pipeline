# Phase 3 LOCKED evaluation protocol v1

## Status and boundary

This document freezes the executable evaluation protocol for the sealed
4,000-row `LOCKED_EVALUATION` partition before it is opened. It does not grant
permission to unseal, read, materialize, transform, profile, or review LOCKED.
The frozen candidate remains commit
`e78f52374c156477ce026e0d1dbb9755b85f5d82`, parser
`conservative_address_parser_v3_2_experimental`, registry
`phase03_rule_registry_v5_experimental`, and registry SHA-256
`4e66e0be62c3d0aae3e9452babe7d16f312c7bb49c69af1a2a0e6839cc3bb1fd`.

The protocol identifier is `phase03_locked_evaluation_protocol_v1`. The
canonical protocol fingerprint is
`c1b53fa6debfed25a2662c1130d06881bfbb07666b87263d791cfb5a444a9644`.
The LOCKED v3.2 effective configuration is
`43aa0bc515886b42a42990c8e300f956c8c3c93a9d9e71571dd0eb20bd2fc609`;
the LOCKED v2.1 comparison configuration is
`a40e27d931884725218bf0041d7b56208fe5de14f40cdf42d45bbb9be115beac`.

## Frozen input identity

- LOCKED identities: exactly 4,000.
- LOCKED identity digest:
  `dbae5d2d69db4b3e330f416a0c68d102c87b6446c04c1390f36e17dc3e8deb73`.
- Pilot-seal SHA-256:
  `ae1e9dd6eb927301eeaa33561aefc6c5197b22ab9eeea5bd8d37fcccce6616e7`.
- Sampling-contract SHA-256:
  `0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7`.
- Phase 2 input is the immutable successful run
  `phase02_20260810T173851Z_1349152b` and its exact 206 manifest-bound shards.

Preflight validates repository/runtime/reference/configuration identity, every
Phase 2 shard hash and page checksum, the identity file, its exact partition,
count and digest, and the pilot seal. The production execution guard runs
before any input is opened. Preflight itself does not open the LOCKED payload.

## Exact metrics and denominators

Primary scientific metrics use the 400 completed `LOCKED-R01` labels. The 100
`LOCKED-R02` labels are independent reliability evidence and never silently
replace primary labels.

| Metric | Exact numerator | Exact denominator | Hard gate |
| --- | --- | --- | --- |
| Joint street-house precision | Experimental-selected reviewed rows labeled joint `CORRECT` | Experimental-selected reviewed rows labeled joint `CORRECT` or `INCORRECT` | at least 0.95 |
| Street exact precision | Reviewed rows with a selected street labeled `CORRECT` | Reviewed rows with a selected street labeled `CORRECT` or `INCORRECT` | at least 0.95 |
| House-number exact precision | Reviewed rows with a selected house number labeled `CORRECT` | Reviewed rows with a selected house number labeled `CORRECT` or `INCORRECT` | at least 0.95 |
| False-structure/overreach rate | Reviewed rows labeled parser-overreach `PRESENT` | Reviewed rows labeled parser-overreach `PRESENT` or `ABSENT` | at most 0.05 |
| Missed-information rate | Reviewed rows labeled missed-information `PRESENT` | Reviewed rows labeled missed-information `PRESENT` or `ABSENT` | report only |
| False-negative opportunities | Rejected V5 evidence cases labeled candidate support `SUPPORTED` | count, not a rate | report only |

An empty precision denominator fails closed; it is not converted to perfect
precision. Conflict precision/recall, evidence-sidecar coverage, country,
script, completeness, status, native-field, country-method and unrelated
component results are reported. Fill rate is prohibited as an acceptance
metric.

All ratios are compared as exact integer cross-products. Floating-point
rounding cannot change a boundary decision.

## Deterministic 400-row review selection

Selection uses only machine-produced structural categories after both frozen
parsers have executed on the sealed identities. No human label, lexical value,
manual inspection or cherry-picking participates.

The candidate record contains only stable identity plus:

- v2.1-v3.2 scientific-change state;
- V5 evidence state: `SELECTED`, `UNSELECTED`, or `NONE`;
- selected country group;
- Unicode script family;
- parse status;
- completeness class;
- conflict-present state.

The seed is
`safe_geocoding_pipeline:phase03_locked_review_v1:seed:1`. Every rank is
SHA-256 over an explicit domain, NUL, and the raw 32-byte stable identity, with
raw identity as the final deterministic tie-breaker.

Selection proceeds in this exact order, always de-duplicating identities:

1. include up to 100 V5-selected-evidence rows, or every available row if
   fewer than 100 exist;
2. include up to 100 V5-unselected-evidence rows, or every available row if
   fewer than 100 exist;
3. include up to 50 scientific-change rows with no V5 evidence, or every
   available row if fewer than 50 exist;
4. include remaining identities from the union of scientific changes and V5
   evidence until the union is exhausted or the sample reaches 400;
5. deterministically fill to 400 from all remaining LOCKED identities.

Within every step, a deterministic greedy selector prioritizes categories
that have not reached an availability-capped structural coverage target of
five, then uses the domain-separated rank and identity tie-breaker. A row in
multiple strata is selected once and contributes to every membership. A
stratum with fewer than five rows has target equal to its availability. Any
unmet coverage targets are recorded but never change the 400-row total.

If fewer than 400 eligible LOCKED identities exist, preparation fails. If more
than 400 experimental/change rows exist, the first three reservations and the
same structural selector produce exactly 400; no threshold is relaxed after
observing data.

## Independent review and blinding

Exactly 100 of the 400 identities are independently double reviewed. The
selection reserves, where available, 50 V5-selected cases, 25 V5-unselected
cases, and 25 parser-change cases, de-duplicates overlaps, then structurally
fills to 100. Separate SHA-256 order domains give `LOCKED-R01` and
`LOCKED-R02` different deterministic display orders.

`LOCKED-R01` receives all 400 cases. `LOCKED-R02` receives only the frozen 100
double-review identities. The reviewers have separate owner-only SQLite
databases. R02 receives no R01 labels, progress, notes or completion state.
Both records for a double-review identity carry `is_independent_review=true`;
`assignment_role` distinguishes `PRIMARY` from `INDEPENDENT_SECOND`.

## Review schema

Portable schema `phase03_locked_review_labels_v1` contains:

1. `hashed_review_id`;
2. `locked_evaluation_version`;
3. `reviewer_id`;
4. `review_round`;
5. `is_independent_review`;
6. `assignment_role`;
7. `street_label`;
8. `house_number_label`;
9. `joint_street_house_label`;
10. `residual_role_label`;
11. `candidate_support_label`;
12. `conflict_correctness_label`;
13. `parser_overreach_label`;
14. `missed_information_label`;
15. `unsafe_handling_label`;
16. `overall_parse_acceptability_label`;
17. `reason_codes`;
18. `reason_codes_version`;
19. `label_vocabulary_version`;
20. `label_schema_version`.

It reuses the existing closed component, error-condition, overall,
joint-street-house, residual-role, candidate-support and
`manual_review_reason_codes_v1` vocabularies. Unknown labels fail. Protected
notes are limited to 500 Unicode characters, remain only in the reviewer
SQLite database, and are absent from portable exports and sanitized reports.

## Agreement and adjudication

Cohen's kappa is calculated separately for the ten frozen review fields.
`CANNOT_ASSESS` pairs are excluded per field. `NOT_APPLICABLE` remains an
ordinary category because applicability is itself reviewable. Each field
requires at least 80 assessable pairs.

When kappa is mathematically defined, it must be at least 0.80 for every field.
When degenerate marginals make kappa undefined, the field passes only through
the pre-registered fallback: at least 80 assessable pairs and at least 0.95
exact percent agreement. Undefined kappa is never silently treated as PASS.

Every disagreement and the number of identities needing adjudication are
reported. No automatic adjudication occurs. Primary R01 labels drive the
scientific metrics; R02 labels drive only the independent-agreement gate.
Disagreements remain auditable and are not overwritten or synthesized.

## Deterministic decision

`LOCKED_PASS` requires all four quantitative gates, every agreement-field
gate, zero unexplained scientific-output changes, zero unrelated-component
regressions, zero provenance/hash/seal failures, zero privacy/governance
failures, and no systematic methodological or unsafe defect requiring a
parser/rule change.

Any failed gate yields `LOCKED_FAIL_REVISE`. A revision requires a new
parser/rule/configuration version and a newly versioned locked-evaluation
sample/design. The opened sample cannot be used both to tune and certify the
revision.

`LOCKED_PASS` does not promote Parser v3.2, authorize a full Phase 3 run,
authorize geocoding, or start Phase 4. It makes v3.2 eligible only for a
separate final scientific promotion decision.

## Executable workflow and atomicity

The dedicated command is `safe-geocoding-phase03-locked-evaluation`. It has
explicit `protocol-info`, `preflight`, `materialize`, `transform`,
`prepare-review`, `initialize-review`, `review`, `review-progress`,
`export-labels`, `score`, and `finalize` stages.

The committed Goethe workflow is
`cluster/goethe_nhr/phase03_locked_evaluation.sbatch`. `PREFLIGHT` is the only
stage permitted without the separate explicit-unseal token and records zero
payload rows read. Later stages require both its exact PASS report and
`PHASE03_LOCKED_UNSEAL_AUTHORIZATION=LOCKED_EVALUATION_EXPLICITLY_AUTHORIZED`.
The job is deliberately split at the human-review boundary: preflight,
open/transform/review preparation, reviewer-workspace initialization, and
score/finalization are separate auditable submissions pinned to the same clean
detached Git commit. Nothing silently advances after review preparation.

Scoring requires every pre-registered machine gate to be present in an exact
closed JSON object. Missing fields do not default to zero. It records counts
for unexplained changes, unrelated regressions, lost existing selections,
provenance failures and privacy/governance failures, plus explicit booleans for
systematic methodological defect, unsafe extraction and a required parser/rule
modification. This file is hash-bound into the final manifest.

The v3.2 engine remains DEVELOPMENT-only by default. LOCKED execution requires
all three simultaneously: parser v3.2, scope `LOCKED_EVALUATION`, and the exact
`phase03_locked_evaluation_protocol_v1` token. The token is rejected for v3,
v3.1, DEVELOPMENT and AUTHORITATIVE scopes. No local or authoritative bypass
exists.

The transform writes separate v2.1 baseline and v3.2 candidate core/evidence
pairs. Every pair is schema-validated, relationship-validated, independently
read with page-checksum verification, semantic-digest reconciled and
hash-recorded. Actual review material is prepared only after transformation
and contains exactly the deterministic 400 cases. Portable reports contain no
raw addresses, source identities, spans, candidate values or protected notes.

Interrupted work remains under a new owner-only `.in_progress` run directory.
Finalization validates required artifact hashes, writes the dataset manifest,
writes `_SUCCESS.json` last, then atomically renames the attempt directory.
No existing output is overwritten.

## STOP

LOCKED remains sealed. The protocol is frozen for review and explicit unseal
authorization only. No command in this document has been executed on LOCKED.

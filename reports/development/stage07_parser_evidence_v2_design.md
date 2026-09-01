# Stage 7 evidence-only v2 design freeze

## Decision

Stage 7 is an evidence-production stage, not a semantic-truth gate. The failed
`stage07_component_readiness_rule_v1` experiment remains immutable validation
history and is not tuned or replaced. Its deterministic parser-local signals
are retained only as warning features.

The controlling frozen identities are:

- contract: `stage07_parser_evidence_contract_v2`;
- profile: `stage07_parser_evidence_profile_v2`;
- schema: `stage07_parser_evidence_schema_v2`;
- schema fingerprint:
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
- pre-publication contract fingerprint:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`;
- structural-warning feature version:
  `stage07_structural_warning_features_v1`;
- historical signal implementation SHA-256:
  `dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9`.

## Evidence contract

Stage 7 v2 guarantees:

- exact preservation of every Stage 6 candidate ID, candidate string, and
  occurrence count;
- exact logical preservation of the immutable Stage 7 v1 technical status and
  ordered raw libpostal label/value stream, including duplicates and empty
  lists;
- frozen libpostal bundle and upstream artifact provenance;
- trusted-country provenance and parser-applicability evidence as a separate
  dimension;
- deterministic structural warnings where applicability is resolved;
- complete 69,747-occurrence map-back;
- no parser calls and no source-information loss.

Stage 7 v2 does **not** guarantee correct semantic labels, correct component
boundaries, postal/address validity, geographic truth, or semantic correctness
when no warning fires. `NO_STRUCTURAL_WARNINGS_DETECTED` is a negative
mechanical observation, never a trust claim.

## Independent status dimensions

Parser applicability retains the frozen country vocabulary:

- `PARSER_ELIGIBLE_COUNTRY`;
- `PARSER_ELIGIBILITY_MISSING_COUNTRY`;
- `PARSER_ELIGIBILITY_PARTIAL_COUNTRY`;
- `PARSER_ELIGIBILITY_INVALID_COUNTRY`;
- `PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY`.

Technical execution is copied exactly from historical v1:

- `PARSED_NONEMPTY`;
- `PARSED_EMPTY`.

Every row records execution origin `REUSED_IMMUTABLE_STAGE07_V1`. This does not
claim that v2 called an unresolved-country candidate: it preserves what the
historical v1 run actually did.

Structural-warning status is deliberately non-semantic:

- `STRUCTURAL_WARNINGS_PRESENT`;
- `NO_STRUCTURAL_WARNINGS_DETECTED`;
- `STRUCTURAL_WARNINGS_NOT_EVALUATED`.

Country-unresolved rows retain their raw v1 evidence but receive
`STRUCTURAL_WARNINGS_NOT_EVALUATED`; eligible `PARSED_EMPTY` rows receive
`STRUCTURAL_WARNINGS_PRESENT` with `PARSED_EMPTY_NO_COMPONENTS`. Eligible
nonempty rows replay the unchanged deterministic structural signals. No
`COMPONENTS_READY`, `COMPONENTS_ABSTAIN`, or semantic-trust field is published.

## Bound immutable inputs

- Stage 6 manifest SHA-256:
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`;
- Stage 7 v1 manifest SHA-256:
  `98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77`;
- libpostal bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`;
- eligibility artifact SHA-256:
  `a6ba110c0519873af898dcec0b5188a1db2659fe31aa619613cffcfdf82e499c`;
- eligibility audit manifest SHA-256:
  `8395b0b5f8e0943dc6dd1a9c9553ea571294fc7bbe61fc9b9b1e6e8fd1cea1a6`;
- eligibility-policy manifest SHA-256:
  `49dcda13e36d2692885efadffb606fa96207fc174a3385041c07af9bf0d1026a`.

The DEVELOPMENT total remains 51,779 candidates and 69,747 occurrences. The
frozen applicability split is 50,685 eligible and 1,094 unresolved.

## Bounded projection and validation

The materializer performs an ordered three-way streaming merge of Stage 6,
Stage 7 v1, and eligibility evidence. It deserializes only one nested candidate
result at a time plus bounded Arrow batches, writes owner-only Parquet shards atomically, and
never buffers a population-sized candidate or component collection.

Independent reopen validation replays every warning, compares every Stage 6
field, technical status, and raw ordered component list against its immutable
input, rehashes all artifacts, and verifies the complete occurrence map-back.
The deterministic logical fingerprint is independent of input batch, output
batch, and shard layout.

## Stage 8 handoff

Stage 8 is not started. If later authorized, it may consume libpostal
components only as hypotheses/evidence. It must not treat labels as source
truth or interpret absence of warnings as semantic correctness. Exact whole-
string STANDARD and NATIVE candidates remain available in parallel, and no
hypothesis may overwrite them.

## Current gate

This document freezes the design and implementation contract only. A single
Goethe-NHR DEVELOPMENT publication/validation must still prove 51,779 → 51,779,
exact v1 preservation, 69,747-occurrence map-back, deterministic warnings, and
zero semantic-trust claims. Independent review, Stage 8, HOLDOUT, production,
geocoding, and merge remain unauthorized.

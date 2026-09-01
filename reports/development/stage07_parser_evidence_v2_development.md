# Stage 7 evidence-only v2 DEVELOPMENT report

## Verdict

`STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW`

This is not `STAGE_7_ACCEPTED`. No independent review, Stage 8, HOLDOUT,
production, geocoding, or merge has begun.

## Frozen scientific identity

- contract: `stage07_parser_evidence_contract_v2`;
- profile: `stage07_parser_evidence_profile_v2`;
- implementation SHA: `e684d84a8d68498ea790542143c8e125b3eb87b5`;
- contract fingerprint:
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`;
- schema fingerprint:
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
- logical dataset SHA-256:
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`;
- manifest SHA-256:
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`;
- immutable Stage 7 v1 manifest SHA-256:
  `98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77`;
- frozen libpostal bundle fingerprint:
  `f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae`.

## Execution

Goethe-NHR SLURM job `1763516` completed successfully from a clean detached
worktree at the exact pushed implementation SHA. It requested 4 CPUs, 32 GiB,
and four hours; the scheduler completed it in 5 minutes 19 seconds with batch
MaxRSS 2,182,616 KiB. The job produced 13 owner-only Parquet shards totaling
96,431,201 bytes. Output directories are `0700` and files are `0600`.

The implementation made zero parser calls. It reused and did not modify the
immutable v1 registry. Protected semantic inspection, HOLDOUT access,
production access, network calls, and Stage 8 work were zero.

## Complete reconciliation

- Stage 6 candidates: 51,779 input → 51,779 output;
- dropped/added/duplicate candidate IDs: 0 / 0 / 0;
- Stage 6 candidate IDs, exact candidate strings, and all three occurrence
  counts preserved: PASS;
- raw v1 technical status and exact ordered label/value stream preserved:
  51,779 / 51,779 PASS;
- complete occurrence map-back: 69,747 / 69,747 PASS;
- STANDARD occurrence map-back: 34,822 / 34,822 PASS;
- NATIVE occurrence map-back: 34,925 / 34,925 PASS;
- parser calls: 0;
- semantic-trust claims: 0;
- Stage 6 science changed: **NO**;
- Stage 7 v1 changed: **NO**.

The materializer and post-publication validator independently streamed the
three frozen inputs and replayed every warning. Successful job termination is
conditional on exact row/value equality and the full occurrence map-back.

## Applicability and technical evidence

Applicability remains separate from technical history:

| Applicability status | Candidates |
|---|---:|
| `PARSER_ELIGIBLE_COUNTRY` | 50,685 |
| `PARSER_ELIGIBILITY_MISSING_COUNTRY` | 721 |
| `PARSER_ELIGIBILITY_PARTIAL_COUNTRY` | 4 |
| `PARSER_ELIGIBILITY_INVALID_COUNTRY` | 355 |
| `PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY` | 14 |
| **Total** | **51,779** |

Historical v1 technical execution was preserved exactly:

| Technical status | Candidates |
|---|---:|
| `PARSED_NONEMPTY` | 51,774 |
| `PARSED_EMPTY` | 5 |
| **Total** | **51,779** |

Every row records execution origin `REUSED_IMMUTABLE_STAGE07_V1`. The v2
projection does not claim that it newly parsed country-unresolved candidates.

## Structural-warning evidence

| Warning status | Candidates |
|---|---:|
| `NO_STRUCTURAL_WARNINGS_DETECTED` | 33,811 |
| `STRUCTURAL_WARNINGS_PRESENT` | 16,874 |
| `STRUCTURAL_WARNINGS_NOT_EVALUATED` | 1,094 |
| **Total** | **51,779** |

Nonzero reason-code counts were:

- `TOKEN_INTERNAL_COMPONENT_BOUNDARY`: 10,105;
- `RAW_ORDERED_SUBSTRING_ALIGNMENT_FAILURE`: 7,750;
- `LEXICAL_RUN_SPLIT_ACROSS_THREE_OR_MORE_COMPONENTS`: 6,317;
- `TOKEN_INTERNAL_SINGLE_CODEPOINT_FRAGMENT`: 2,426;
- `LEXICAL_NUMERIC_MATERIAL_LOSS`: 39;
- `PARSED_EMPTY_NO_COMPONENTS`: 4;
- `LEXICAL_NUMERIC_REORDER_OR_SUBSTITUTION`: 1.

Reasons can coexist, so their counts do not sum to candidate rows. Four of the
five historical empty parses are country-eligible and receive the empty-parse
warning; the fifth is within the country-unresolved population and is correctly
not structurally evaluated. These are mechanical observations, not estimates
of semantic parser accuracy.

## Controlling semantics and Stage 8 handoff

`stage07_component_readiness_rule_v1` remains immutable failed diagnostic
evidence. No `COMPONENTS_READY` or `COMPONENTS_ABSTAIN` field exists in the v2
registry. Its signal implementation is reused only under
`stage07_structural_warning_features_v1`.

Stage 7 v2 explicitly does not guarantee semantic component labels, component
boundaries, address validity, geographic truth, or semantic correctness when
no warning fires. If separately authorized, Stage 8 may use the raw components
only as hypotheses/evidence and must retain exact whole-string STANDARD/NATIVE
candidates in parallel.

All contract, schema, input-binding, topology, artifact rehash, bounded-memory,
warning-replay, raw-output preservation, map-back, privacy, and zero-trust gates
passed. The evidence-only DEVELOPMENT candidate is therefore ready for a
separately authorized independent review and nothing beyond it.

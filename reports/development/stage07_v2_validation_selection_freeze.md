# Stage 7 v2 validation-selection freeze

Status: **`STAGE07_V2_VALIDATION_SELECTION_FROZEN`**. This is a
machine-only DEVELOPMENT selection result, not semantic validation and not
Stage 7 acceptance. The scientific status remains
**`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`**.

Job `1763433` ran exact pushed SHA
`20a46610b885919b5bad113f2b5763e98bf23ca5` under a 30-minute, 8 GiB,
two-CPU request and completed with exit `0:0` in 28 seconds. It applied
unchanged rule `stage07_component_readiness_rule_v1`, whose source SHA-256 is
`dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9`.
The rule was not changed after frame values were read.

The protected publication is owner-only and untracked. Independent metadata
reopen verified its exact six-file topology, `0700` directory and `0600` file
modes, terminal bindings, all manifest artifact sizes and hashes, and Parquet
footer row counts of 604 frame rows, 240 selection rows, and 240 review rows.
The manifest SHA-256 is
`8f5f4941ed14bab02dd21acbfb091c974881eeea1f4e6b1248349cf22f1fe0`.
The protected review artifact remains unopened for semantic review.

## Immutable bindings

- Fixed-500 candidate-set fingerprint:
  `8834a191efe0a77c5ace78760bd131e2c11bd904097b47e5ba1177f4172a5696`
- Existing 120 selection fingerprint:
  `1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844`
- Untouched 604 candidate-set fingerprint:
  `d51d9c5705ad12c7d4057a87d932401f6bfcb8c46494d0cd23fdeae4541fc3f2`
- Stage 7 v1 manifest SHA-256:
  `98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77`
- Frozen 240 selection fingerprint:
  `c05cecf2aa9099045adc0d5c698c7e82a6bae187ae82222817f4bfb5264c2a89`

The exact 240 candidate IDs, predictions, reason codes, and review order are
frozen in the protected selection artifact. They are deliberately absent from
Git.

## Machine-only frame results

Across the 604 untouched candidates:

- `COMPONENTS_READY`: 330
- `COMPONENTS_ABSTAIN`: 122
- `NOT_ASSESSED`: 152
- eligible candidates technically parsed nonempty: 452
- not attempted because eligibility was unresolved: 152
- eligible-frame abstention coverage: 26.991150442477878%, within the frozen
  10–70% non-vacuity range

The 152 unresolved applicability cases comprise 55 missing-country, 2
partial-country, 90 invalid-country, and 5 ambiguous-country candidates.

The optimized path scanned only the 51,779 candidate IDs for authoritative
binding. It materialized exact candidate/component values for the 452 eligible
untouched candidates, materialized none for unresolved candidates, returned no
unrelated nested rows to Python, and did not materialize the full 51,779-row
nested registry. Parser calls, network calls, semantic human/LLM inspection,
HOLDOUT access, production access, and Stage 8 execution were all zero.

## Frozen 240-case selection

The deterministic selection contains exactly:

- `COMPONENTS_READY`: 120
- `COMPONENTS_ABSTAIN`: 120
- unique trusted countries represented: 134

Representation coverage is:

| Readiness | BOTH | NATIVE_ONLY | STANDARD_ONLY |
|---|---:|---:|---:|
| COMPONENTS_READY | 70 | 36 | 14 |
| COMPONENTS_ABSTAIN | 53 | 41 | 26 |

Script coverage is:

| Script bucket | READY | ABSTAIN |
|---|---:|---:|
| Armenian | 1 | 0 |
| Common/unknown only | 9 | 1 |
| Cyrillic | 5 | 0 |
| Georgian | 1 | 0 |
| Greek | 2 | 0 |
| Han | 4 | 12 |
| Hebrew | 14 | 0 |
| Latin | 81 | 73 |
| Mixed script | 3 | 34 |

Country-frequency coverage is:

| Frequency band | READY | ABSTAIN |
|---|---:|---:|
| Singleton | 41 | 38 |
| Low (2–4) | 33 | 22 |
| Medium (5–14) | 18 | 19 |
| High (15+) | 28 | 41 |

Abstention reason counts are non-exclusive: ordered-substring alignment
failure 100, token-internal boundary 44, lexical-run fragmentation 30,
token-internal single-code-point fragment 20, and lexical/numeric material
loss 3.

## Frozen validation contract and next authorization

Contract `stage07_component_readiness_validation_selection_v1` used only
domain-separated hashes of candidate IDs for deterministic ranking and review
order. Candidate text and parser values did not enter the selection rank.
Predictions, reason codes, strata, validation metrics, and thresholds were
frozen before semantic review.

The next protected scope requiring explicit owner authorization is semantic
review of exactly the 240 rows in the existing owner-only
`stage07_v2_validation_review.parquet`, solely for fresh Stage 7 v2 DEVELOPMENT
validation. That scope must not expand to any other candidate, HOLDOUT,
production, Stage 8, geocoding, or parser execution. No further SLURM job is
needed merely to freeze the selection; a future review workflow may be chosen
only after that authorization.

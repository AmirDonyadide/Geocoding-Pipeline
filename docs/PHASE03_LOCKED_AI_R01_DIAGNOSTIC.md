# Phase 3 LOCKED AI-R01 diagnostic

## Status and scope

This is a sanitized `LOCKED_AI_R01_DIAGNOSTIC` for run
`phase03_locked_evaluation_20260817T140155Z_7472394` at workflow commit
`7472394387399d7d721252f0d1c092b60d5e0844`.

The frozen protocol expected a primary human reviewer. By explicit user
direction, Codex/AI instead produced all 400 `LOCKED-R01` judgments. The
reviewer provenance is `CODEX_AI_PRIMARY_REVIEWER`; these labels must not be
represented as human judgments. `LOCKED-R02` remains untouched with no second
review, so human-human Cohen's kappa and the preregistered final LOCKED decision
are unavailable.

The formal status is
`FORMAL_LOCKED_DECISION_NOT_AVAILABLE_PROTOCOL_DEVIATION`. The threshold
results below describe only what the AI-R01 values would do at the frozen
quantitative gates. They are not `LOCKED_PASS` or `LOCKED_FAIL_REVISE`, do not
promote Parser v3.2, and do not authorize later processing.

## Bound inputs and execution

- `LOCKED-R01`: 400 assignments, 400 complete, zero pending, 400 labels;
  SQLite integrity `ok`.
- `LOCKED-R01` database SHA-256:
  `336008cf9f600b3ad722b21f60e41b99e1a64c7cf9d3ef911223214440065d81`.
- Protected notes: zero.
- Sanitized diagnostic computation: Goethe-NHR SLURM job `1751217`, node
  `node17-005`, source commit
  `7472394387399d7d721252f0d1c092b60d5e0844`.
- `LOCKED-R02` was not opened. Its SHA-256 before and after the computation was
  unchanged at
  `d213d563e595ce2fb30688a340fc28c052113732ca19ba577cc3cc2149a96b54`.

The computation read only R01 labels and the protected context's hashed review
key plus closed machine metadata needed by the frozen denominators. No raw
address, protected identity, source span, or protected value appears here.

## Frozen quantitative metrics

| Gate | Numerator | Denominator | Result | Threshold | Exact check | Gate status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Street exact precision | 99 | 129 | 76.744186% | at least 95% | `99*100 = 9900 < 95*129 = 12255` | FAIL |
| House-number exact precision | 74 | 87 | 85.057471% | at least 95% | `74*100 = 7400 < 95*87 = 8265` | FAIL |
| Joint street-house precision | 0 | 0 | not defined | at least 95% | empty precision denominator fails closed | FAIL |
| Parser-overreach / false-structure rate | 43 | 395 | 10.886076% | at most 5% | `43*100 = 4300 > 5*395 = 1975` | FAIL |

The joint denominator is zero because the frozen LOCKED comparison contained
zero experimental-selected rows. It is not converted to perfect precision.
Fill rate is not used.

## Report-only results

Missed-information labels:

| Label | Rows |
| --- | ---: |
| `PRESENT` | 253 |
| `ABSENT` | 114 |
| `CANNOT_ASSESS` | 33 |

The report-only missed-information rate is `253 / 367 = 68.937330%`;
`CANNOT_ASSESS` is excluded from that denominator.

Overall parse acceptability:

| Label | Rows |
| --- | ---: |
| `ACCEPTABLE` | 114 |
| `NOT_ACCEPTABLE` | 253 |
| `CANNOT_ASSESS` | 33 |

Unsafe handling:

| Label | Rows |
| --- | ---: |
| `ABSENT` | 400 |
| `PRESENT` | 0 |
| `CANNOT_ASSESS` | 0 |

Reason-code counts are multi-valued and therefore need not sum to 400:

| Reason code | Count |
| --- | ---: |
| `CORRECT_AS_IS` | 100 |
| `FALSE_POSITIVE_EXTRACTION` | 42 |
| `INSUFFICIENT_SOURCE_EVIDENCE` | 30 |
| `MISSED_CONFLICT` | 2 |
| `MISSED_EXTRACTABLE_COMPONENT` | 253 |
| `SOURCE_AMBIGUOUS` | 50 |
| `UNSUPPORTED_FORMAT` | 154 |
| `WRONG_COMPONENT_ROLE` | 37 |
| `WRONG_CONFLICT_DETECTION` | 8 |
| `WRONG_PROVENANCE` | 2 |
| `WRONG_SPAN_BOUNDARY` | 25 |
| `WRONG_VALUE` | 13 |

## Interpretation boundary

These results are diagnostic evidence from an AI primary review. They do not
satisfy the preregistered human-human review design, do not provide an
agreement result, and cannot yield the formal deterministic LOCKED decision.
No parser, rule, registry, configuration, threshold, review population, saved
R01 label, or R02 artifact was changed for this diagnostic.

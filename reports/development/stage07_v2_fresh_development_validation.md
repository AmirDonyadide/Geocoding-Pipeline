# Stage 7 v2 fresh DEVELOPMENT validation

Scientific conclusion: **`STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL`**.
The frozen structural-readiness rule does not meet the predeclared precision,
clear-misparse leakage, or usable-abstention thresholds. Stage 7 remains
**`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`**.

## Technical summary

Exactly 240 candidates from the immutable fixed-500 validation frame were
reviewed: 120 predicted `COMPONENTS_READY` and 120 predicted
`COMPONENTS_ABSTAIN`. Selection membership, predictions, reason codes, metric
definitions, and thresholds were frozen before semantic review under selection
fingerprint
`c05cecf2aa9099045adc0d5c698c7e82a6bae187ae82222817f4bfb5264c2a89`.

The owner authorized Codex to inspect exactly these 240 protected DEVELOPMENT
candidates and their existing raw Stage 7 output. Review was prediction-blinded
until all classifications were durably frozen. No other candidate, parser call,
web or third-party service, HOLDOUT, production, Stage 8, geocoding, or
independent review entered the assessment.

The rule retains useful structural-warning behavior, but 10 clear misparses
leaked into the 100 assessable READY cases and READY precision was only 85%.
The rule also abstained on 63 of 148 usable parses. It therefore cannot be
published as the Stage 7 v2 component-consumption gate without a new owner
scientific decision.

## Frozen scope and provenance

- Rule: `stage07_component_readiness_rule_v1`
- Rule source SHA-256:
  `dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9`
- Selection contract:
  `stage07_component_readiness_validation_selection_v1`
- Selection: 240 unique candidates, 120 READY and 120 ABSTAIN
- Review method: `OWNER_AUTHORIZED_CODEX_SEMANTIC_REVIEW`
- Classification artifact SHA-256:
  `99a024a49a0dc243f02bff4cec20ff5a3bfecb7d12a46961e72e2dbfb774507d`
- Abstract-comment artifact SHA-256:
  `697f3735e92ec1d086875acfdfc5fe77346ef8943c7aeb4dd37c38e7055c127f`
- Protected validation manifest SHA-256:
  `d5e517bd7cb55d7f954224f9aa380841acc1c9f4e77593918e522f632c9509b4`
- Protected validation aggregate SHA-256:
  `5e55757daa817d7ffe24c2f053ce045783300b116acb5d20df17419e2738bdfd`

The owner-only review directory is mode `0700`; every protected file is mode
`0600`, ignored, and untracked. The classification artifact contains only
`review_order` and classification—not candidate or address text. Independent
reopen verified exact review-order totality, allowed values, comment alignment,
selection binding, manifest hashes, and terminal bindings.

## Classification evidence

| Classification | Count |
|---|---:|
| `PLAUSIBLE_PARSE` | 79 |
| `PARTIAL_BUT_USABLE_PARSE` | 69 |
| `QUESTIONABLE_PARSE` | 8 |
| `CLEAR_MISPARSE` | 41 |
| `UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE` | 43 |
| **Total** | **240** |

The frozen usable definition is `PLAUSIBLE_PARSE +
PARTIAL_BUT_USABLE_PARSE`. Upstream-corrupt/unassessable rows are reported but
excluded from READY precision and usable-abstention denominators.

| Prediction | Plausible | Partial usable | Questionable | Clear misparse | Upstream/unassessable | Total |
|---|---:|---:|---:|---:|---:|---:|
| `COMPONENTS_READY` | 64 | 21 | 5 | 10 | 20 | 120 |
| `COMPONENTS_ABSTAIN` | 15 | 48 | 3 | 31 | 23 | 120 |

## Predeclared metric decisions

| Metric | Observed | Predeclared requirement | Result |
|---|---:|---:|---|
| READY precision | 85 / 100 = 85.000% | at least 95.000% | **FAIL** |
| Clear-misparse leakage | 10 / 100 = 10.000% | at most 2.500% and at most 2 cases | **FAIL** |
| Usable abstention rate | 63 / 148 = 42.568% | at most 40.000% | **FAIL** |
| Eligible-frame abstention coverage | 122 / 452 = 26.991% | 10.000–70.000% | **PASS** |
| Structural-reason replay | exact | exact | **PASS** |

The coverage result shows that the rule is not vacuous. It does not compensate
for the three failed scientific-quality gates.

## Strata findings

The failure is not confined to one representation. Among assessable cases,
READY precision was 50/58 (86.207%) for `BOTH` and 26/32 (81.250%) for
`NATIVE_ONLY`, with five and four leaked clear misparses respectively.
`STANDARD_ONLY` had only 18 assessable cases, below the frozen minimum of 20
for a stratum-level pass/fail claim.

Latin-script cases supplied the only large single-script stratum: 139 were
assessable, and READY precision was 65/74 (87.838%) with six clear misparses
leaking. Mixed-script cases had 22 assessable rows, six clear misparses overall,
and only two assessable READY rows; both were usable, but that READY denominator
is too small to support a broad claim. Han and Hebrew had fewer than 20
assessable cases and therefore remain descriptive only; three Han and one
Hebrew clear misparses leaked into READY.

The structural reasons identify genuine risk but also abstain on usable rows.
`RAW_ORDERED_SUBSTRING_ALIGNMENT_FAILURE` covered 26 clear misparses and 50
usable cases among 78 assessable flagged rows. `TOKEN_INTERNAL_COMPONENT_BOUNDARY`
covered 10 clear misparses and 20 usable cases among 31 assessable flagged rows.
Reason counts are non-exclusive.

## Methodology and limitations

The 240 cases are a predeclared, balanced validation sample, not a random
estimate of population-wide libpostal accuracy. READY and ABSTAIN were sampled
at equal sizes, so sample classification shares and the 85% READY precision
must not be projected to all 50,685 eligible DEVELOPMENT candidates. The
frame-level 26.991% abstention coverage comes from all 452 eligible candidates
within the 604-candidate validation frame, not the balanced review sample.

Semantic classification was an owner-authorized Codex review, not independent
human acceptance. The classification vocabulary and prediction blinding reduce
reviewer bias, but semantic judgment remains a limitation. The frozen minimum
of 20 assessable observations controls which strata receive pass/fail claims.

## Scientific disposition

The rule successfully catches many structurally dangerous outputs, including
31 of the 41 fresh clear misparses, but it neither protects READY with the
required precision nor preserves usable structured coverage within the frozen
limit. This is a fresh validation failure, not permission to tune the rule on
these labels.

The bounded response is:

- do not publish Stage 7 v2 from this rule;
- preserve immutable Stage 7 v1 raw evidence and all protected validation
  evidence;
- do not derive a replacement rule from the 240 validation labels; and
- require a new owner scientific decision about a safer Stage 7 scope or a new
  independently discover-and-validate design.

No Stage 8 handoff, independent review, HOLDOUT, production, geocoding, or
merge is authorized.

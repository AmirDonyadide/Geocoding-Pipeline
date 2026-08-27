# Phase 3 Parser v3.2 orientation-narrowing experiment

## Status and scope

`conservative_address_parser_v3_2_experimental` is a DEVELOPMENT-only,
unapproved narrowing of the historical repaired Parser v3.1 experiment. It
does not change Phase 2, pilot sampling, the frozen 8,000 DEVELOPMENT
identities, any LOCKED identity or payload, schemas, normalization, safety
limits, references, or non-experimental rules.

Parser v3.1 remains immutable historical evidence. Its single-reviewer R01
evaluation found five of nine selected rows jointly correct and four false
positives. No promotion threshold was applied and Parser v3.1 was not approved
for promotion.

## Evidence-gated scientific change

The protected R01 labels and exact v3.1 evidence spans were classified into
two structural orientations without exporting identities, source values,
candidate values, or spans. The authoritative DEVELOPMENT-only result was:

| Orientation | Selected rows | Jointly correct | Incorrect/overreach |
| --- | ---: | ---: | ---: |
| `STREET_NUMBER_RESIDUAL` | 4 | 4 | 0 |
| `RESIDUAL_NUMBER_STREET` | 5 | 1 | 4 |
| `OTHER_OR_UNCLASSIFIABLE` | 0 | 0 | 0 |

The result confirms the predeclared 4/4 versus 1/5 hypothesis. It supports one
and only one v3.2 change: retain the former orientation and reject the latter
before experimental candidates are emitted.

## Frozen v3.2 rule contract

Parser v3.2 uses `phase03_rule_registry_v5_experimental` with new rule IDs:

- `HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5`;
- `STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5`.

The matcher parameter `allowed_orientation` is exactly
`STREET_NUMBER_RESIDUAL`. All other v3.1 requirements remain unchanged:

- one punctuation-free segment and one bounded center integer;
- exactly one designator-bearing side;
- one alphabetic non-role residual word;
- two unambiguous structured-geography components;
- no competing address-role evidence, postcode equality, year, extra number,
  role marker, or native/non-native disagreement;
- exact raw Unicode-codepoint evidence spans and existing candidate/safety
  limits.

There is no word blacklist, country exception, fuzzy match, transliteration,
geography relaxation, or new reference. V2.1 and v3.1 remain separately
addressable and reproducible.

## DEVELOPMENT evaluation and label reuse gate

The Goethe workflow reads only the existing 8,000-row DEVELOPMENT payload and
the authoritative repaired v2.1 core/evidence. It does not rerun selection or
materialization. It writes to a new immutable development iteration, validates
schemas, identity order, semantic digests, page checksums, and compares v2.1
with v3.2 using sanitized aggregates.

Existing Targeted-R01 labels may be reused only if machine verification proves
that every v3.2 changed/selected identity is inside the existing 11-row review,
all V5 candidate values and exact source spans match previously reviewed V4
candidate semantics, and no unreviewed identity changes. The verifier emits
only aggregate counts, artifact hashes, and domain-separated population
digests. Targeted-R02 is neither required nor read.

The resulting score is single-reviewer evidence and must state that independent
second review and agreement were not evaluated. Its neutral status is
`TARGETED_SINGLE_REVIEWER_V3_2_SCORED_NO_PROMOTION_DECISION`; no automatic
promotion decision or threshold is permitted.

## Goethe execution boundary

The versioned job is
`cluster/goethe_nhr/phase03_development_parser_v3_2_experimental.sbatch`. It
requires a clean detached integration worktree at the exact reviewed commit,
Python 3.14.3/Unicode 16.0.0, pinned references, readable owner-only controlled
inputs, and paths that do not contain `locked`. It requests one node, four
CPUs, 16 GiB RAM, and two hours. Historical inputs are hashed before and after;
all new output is outside the preserved source pilot tree and is promoted only
after validation.

LOCKED remains sealed. Phase 3 full-data transformation, geocoding, Phase 4,
and any final promotion decision remain unauthorized.

## DEVELOPMENT decision and pre-LOCKED status

The authoritative DEVELOPMENT execution used commit
`e78f52374c156477ce026e0d1dbb9755b85f5d82`. Submission `1750475` was
cancelled with zero runtime while pending for scheduler priority. Replacement
job `1750488` was the only DEVELOPMENT evaluation execution and completed on a
Goethe SLURM `test` compute node using the frozen 8,000-row DEVELOPMENT inputs.
The committed job preferred `general1`; the partition override is retained as
explicit provenance. The repository execution policy requires Goethe plus
SLURM and contains no rule invalidating this bounded run on `test`, so no
duplicate run is created solely to change partition.

The v2.1-v3.2 comparison found exactly four scientific-output changes: four
new street selections, four paired house-number selections, and four
`UNPARSEABLE` to `PARTIAL` transitions. Every other component, native field,
country method, and conflict outcome was unchanged. Reuse of the existing
Targeted-R01 labels was mechanically validated; all four retained selections
were jointly correct, no observed false positive remained, and three
false-negative opportunities remained. Targeted-R02 stayed untouched and
inter-reviewer agreement was not evaluated.

By explicit scientific decision, v3.2 is now the candidate for a future
LOCKED evaluation. It is not promoted for production. The current code remains
deliberately DEVELOPMENT-only: `Phase03Engine` raises
`PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY` if v3.2 is instantiated for
`LOCKED_EVALUATION` or `AUTHORITATIVE`, and the repository has no implemented
LOCKED materialization/transform/review runner. Quantitative acceptance
thresholds and several operational review details are also not yet defined.
`docs/PHASE03_PRE_LOCKED_FREEZE.json` records the frozen identities, the
available pre-unseal seal digest, the defined metric families, and every
remaining decision. LOCKED rows read remain zero.

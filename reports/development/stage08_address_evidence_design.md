# Stage 8 address-evidence design report

## Verdict

`STAGE08_ADDRESS_EVIDENCE_DESIGN_READY_FOR_IMPLEMENTATION`

This verdict applies to design only. Stage 8 is not implemented, executed, or
accepted. No DEVELOPMENT job, protected candidate inspection, HOLDOUT,
production, Stage 9, Pelias, geocoding, Senzing, or DeepParse work occurred.
The next task belongs in a fresh Stage 8 DEVELOPMENT implementation session and
requires explicit authorization.

Repository design baseline: `main` at
`928aabedd7e60a9977bf48208b8bc7ad23fce281`; dedicated branch
`stage08-address-evidence-design`.

The controlling prospective contract is
[the Stage 8 scientific record](../../docs/stages/STAGE08_ADDRESS_EVIDENCE_PROJECTION.md).

## Critical result

The earlier Stage 8 proposal was too broad after final evidence-only Stage 7
acceptance. It mixed lossless parser projection with country normalization,
address-format requirements, and parser-derived component hypotheses. The
corrected boundary is narrower:

- Stage 8 preserves and indexes evidence without interpreting it;
- Stage 9 owns any independently pinned ISO/subdivision, country-format,
  postcode, locality/admin, street, or house-number reference evidence; and
- Stage 10 is the first stage allowed to emit address/query hypotheses.

The Stage 8 name and number remain coherent. No renumbering is needed.

## Exact purpose and input

Purpose: preserve the complete accepted Stage 7 v2 row, expose a reversible
ordered long-form parser-evidence index, retain exact trusted-country and
structural-diagnostic provenance, and guarantee source/representation map-back
without promoting any parser label, value, or boundary to truth.

The input is bound to:

- accepted Stage 7 candidate
  `656a16d3d1f33cb152ace557c26f42df047bc7d6`;
- independent rereview job `1763656`, verdict
  `STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_PASS`, and sanitized evidence
  commit `356de44f3e86e37972d60cac45d01703ad1f6856`;
- Stage 7 v2 manifest
  `f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266`;
- Stage 7 v2 contract/schema fingerprints
  `c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4`
  and
  `b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2`;
- Stage 7 v2 logical dataset
  `0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530`;
  and
- accepted Stage 6 row-map manifest
  `e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241`
  with row-map logical fingerprint
  `1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1`.

Stage 8 reads Stage 7 v2 plus the Stage 6 row map only. It does not reopen raw
source, Stage 5, Stage 7 v1, or eligibility through alternate paths.

## Output and semantic contract

The linked design has:

| Relation | Grain | DEVELOPMENT total fixed by upstream evidence |
|---|---|---:|
| `candidate_evidence` | one row per exact Stage 6 candidate; complete Stage 7 v2 row plus mechanical index counts | 51,779 |
| `parser_component_evidence` | one row per raw component, keyed by candidate plus zero-based ordinal | 6,106,088 |
| `source_candidate_map` | one row per source row with exact structured source context, STANDARD/NATIVE slots, and explicit presence | 35,000 |
| `representation_occurrence_v1` | deterministic logical view over present slots | 69,747 |

The occurrence view must contain exactly 34,822 STANDARD and 34,925 NATIVE
rows. Candidate-level representation scope is `STANDARD`, `NATIVE`, or `BOTH`;
an occurrence is never `BOTH`. A missing representation is explicit `ABSENT`
with a null candidate ID.

Fields are assigned one exact class under
`stage08_semantic_classification_v1`: `SOURCE_VALUE`, `SOURCE_LINEAGE`,
`UPSTREAM_DERIVED_REPRESENTATION`, `TRUSTED_SOURCE_CONTEXT`,
`PARSER_TECHNICAL_PROVENANCE`, `PARSER_EVIDENCE`,
`STRUCTURAL_DIAGNOSTIC`, or `MECHANICAL_INDEX`. `HYPOTHESIS`,
`REFERENCE_EVIDENCE`, `GEOCODER_RESULT`, and `ACCEPTED_MATCH` are prohibited
from Stage 8 output.

The taxonomy is descriptive and carries no confidence, correctness score, or
trust weight.

The source map carries exact raw, Stage 3 clean, and Stage 4 lower postcode,
city, region, and country strings as separate upstream views. They are not
parser components and are not reference-verified. Candidate-level trusted
country remains only the accepted Stage 7 provenance result; an individual
source-row lower-country string is an upstream derived representation, not a
new trust claim.

## Mapping decision

The pinned libpostal source lists 20 currently defined labels while warning
that training data can technically define any string label. The v1 mapping is
therefore:

- exact and case-sensitive;
- one-to-one from each of the 20 labels to a visibly parser-scoped SAFE name
  such as `road` → `PARSER_ROAD` and `country` → `PARSER_COUNTRY`;
- versioned as `stage08_libpostal_label_mapping_v1`;
- incapable of changing the raw value or list order;
- capable of retaining unlimited duplicate labels/values; and
- open to unknown labels through `UNMAPPED_LABEL`, a null SAFE component, and
  exact retained raw label/value/ordinal.

The vocabulary keeps `house`, `city`, `island`, and `world_region` in their
libpostal-defined evidence senses. It does not invent `building` or `locality`,
which would narrow parser semantics, and it does not turn `unknown` into a
generic component that hides the actual raw label.

The raw nested Stage 7 list remains authoritative. The long relation and SAFE
name are an optional evidence index, never a flattened component record.

## State and failure semantics

Independent Stage 7 dimensions remain independent:

- `PARSED_NONEMPTY` emits one index row per exact component;
- historical `PARSED_EMPTY` preserves exact `[]` and emits zero component rows;
- unresolved country applicability preserves raw historical parser evidence,
  exact applicability, provenance, and warning non-evaluation;
- warning present and warning absent both preserve the same raw evidence, and
  neither implies validity/correctness;
- an unknown label remains an explicit unmapped parser-evidence row;
- an absent source representation remains explicit and creates no occurrence;
  and
- a giant candidate is processed in full or the complete publication fails.

The accepted Stage 7 input did historically attempt even country-unresolved
candidates. Stage 8 must not call them “never attempted.” A future upstream
`NOT_ATTEMPTED` state would require a new Stage 8 contract version and could
never be collapsed into parsed empty.

Binding/schema/hash corruption, row/component/map-back loss, malformed nested
evidence, ordinal gaps, truncation, unsupported technical statuses, resource
guard failures, and publication failures abort the complete output. Empty
parses, unresolved country, structural warnings, unknown labels, and absent
representations are preserved evidence states—not fatal errors and never
“invalid address.”

## Metadata placement decision

Neither pycountry nor libaddressinput belongs in Stage 8.

The accepted Stage 7 country decision already uses pinned Debian `iso-codes`
metadata; repeating country normalization would add no lossless information.
pycountry is a wrapper over ISO datasets, not postal or geographic validation.
libaddressinput supplies structured address-form/required-field metadata; it
is not a free-text parser and is not Google Address Validation API. Applying
its rules creates format/reference evidence.

Exact-code pycountry/subdivision use and a pinned offline libaddressinput
snapshot may be designed in Stage 9, with explicit license, vintage, coverage,
ambiguity, and absence-not-invalidity semantics. Fuzzy pycountry search,
runtime Address Data Service calls, and Google Address Validation API are not
approved.

## Losslessness, determinism, and implementation boundary

The future materializer must prove:

- exact Stage 7 row preservation for all 51,779 candidates;
- exact nested ↔ ordered-long reconstruction for all 6,106,088 components;
- complete Stage 6 source-row and 69,747-occurrence map-back;
- duplicate/order/unknown/Unicode/empty/giant preservation;
- layout-independent logical SHA-256 identities for each relation, the
  occurrence view, and the dataset;
- exact schema/mapping/contract and physical artifact fingerprints;
- owner-only `0700`/`0600` permissions and atomic immutable publication; and
- zero parser calls, semantic trust claims, hypotheses, references, network
  calls, HOLDOUT, production, Stage 9, or geocoding.

PyArrow/Parquet own exact schemas, nested evidence, streaming writes, and
fingerprints. DuckDB performs bounded external map-back/foreign-key/aggregate
validation. Component explosion operates on Arrow offsets and child-array
slices with at most one nested candidate plus bounded batches resident.
Polars is not required in v1, and pandas is prohibited for production
transformations.

No code, synthetic fixture, protected artifact, or SLURM asset was created in
this design session.

## Design-document validation

Both JSON documents parse with `jq`; changed-document local links resolve;
`git diff --check` passes; and a machine cross-check confirms that the 25
preserved candidate fields exactly match the accepted Stage 7 v2 Arrow schema,
while every selected upstream source-map field matches the Stage 6 Arrow
schema. The mapping has exactly the 20 pinned labels.

The local-safe test command selected 591 tests and excluded the four tests
marked `requires_production_transfer_payload`: 567 passed and 24 failed at the
repository's deliberate Python runtime gate. The Mac virtual environment is
Python 3.14.7 while Stages 3–6 require exact Python 3.14.3; every failure was a
consequence of that mismatch. This is an environment-limited result, not a
claim that the full suite passed. All Stage 7 tests passed. No protected data
was opened by these checks.

## Review and acceptance path

The fresh implementation session must create the contract/schema/mapping,
materializer, validators, unit/synthetic tests, execution asset, and sanitized
reporting without running Stage 8. After implementation review and separate
authorization, one exact pushed SHA may produce one immutable Goethe-NHR
DEVELOPMENT artifact. It is validated in place rather than duplicated.

Independent review must use a separate bounded harness over that artifact and
verify all rows/components/maps/fingerprints plus privacy and boundary checks.
Stage 8 becomes accepted only after a pass and explicit owner acceptance of the
exact candidate. Acceptance would still not authorize Stage 9, production,
HOLDOUT, Pelias, or geocoding.

## Exact handoff

Stage 9 receives every candidate, source mapping, whole-string
STANDARD/NATIVE representation, trusted-country context, parser technical
provenance, raw/mapped parser evidence, unknown labels, and structural
diagnostics. The source mapping includes distinct exact raw, accepted-clean,
and accepted-lower postcode, city, region, and country strings. Stage 9 must
use trusted source-country context—not `PARSER_COUNTRY` or parser
applicability—for country-required operations. Missing, partial, invalid, or
conflicting country context fails closed or abstains explicitly.

Stage 9 may add independent offline reference/format evidence. `NOT_FOUND`
remains absence; `MISMATCH` requires positive contradiction. It cannot
overwrite Stage 8. Hypotheses begin only in Stage 10.

## Next task

Fresh session: implement the Stage 8 DEVELOPMENT contract and local
synthetic/unit/static validation only. A protected DEVELOPMENT run is a later
separately reviewed and authorized action.

`STAGE08_ADDRESS_EVIDENCE_DESIGN_READY_FOR_IMPLEMENTATION`

# Stage 7 v2 component-readiness design

Status: **`STAGE07_V2_READINESS_DESIGN_READY_FOR_FRESH_DEVELOPMENT_VALIDATION`**.
This is a DEVELOPMENT design result, not Stage 7 acceptance. The controlling
scientific status remains **`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`**.
DeepParse remains closed under `DEEPPARSE_INFRASTRUCTURE_PATH_NOT_JUSTIFIED`.

This report contains sanitized aggregates and fingerprints only. It does not
contain candidate text, parser values, source identities, HOLDOUT information,
or production data.

## Scientific objective and immutable v1 relationship

Stage 7 v2 treats libpostal as evidence rather than postal ground truth. It
adds parser applicability and deterministic parser-local structural warnings
without changing accepted Stage 6 science or overwriting the immutable Stage 7
v1 registry. The exact Stage 6 candidate and the exact ordered v1 component
stream remain recoverable for every historically parsed candidate.

The readiness decision asks whether the raw component stream is structurally
suitable to be carried into downstream hypothesis generation. It does not
assert that component labels are geographically or semantically correct.
Downstream stages must validate hypotheses against independent reference and
geocoder-result evidence before accepting a match.

## Optimized bounded audit

The first bounded implementation, job `1763280` at
`a117a8ec027e499e3f27ac58956697eae6878fa1`, timed out after 30 minutes because
it scanned the complete 51,779-row nested Stage 7 registry and used a
quadratic fragmentation detector. It produced no scientific result. The
failure is preserved as `BOUNDED_IMPLEMENTATION_PERFORMANCE_DEFECT`; it is not
evidence against the readiness design.

Replacement job `1763358` ran exact pushed SHA
`372aad37370144d6ca85d05c56302a0af2cad4b3`. It used the already-materialized
owner-only 120-case HTML review surface as its only semantic input and read
fixed-500 IDs/provenance only outside those 120. It made no parser or network
call and scanned or decoded zero authoritative registry rows. The exact
fragmentation calculation was changed to a linear two-pointer sweep.

The job completed with exit `0:0` in 84 seconds under a 30-minute, 8 GiB,
two-CPU request; SLURM reported batch MaxRSS 1,581,124 KiB. Independent reopen
validation checked `0700`/`0600` modes, zero symlinks, JSON validity, exact
execution SHA, every artifact size/hash, and success-marker bindings. The
aggregate SHA-256 is
`c805f1fe2947ade03901f303874615b1917f31611553ad9a1c33181f76675cdb`;
the manifest SHA-256 is
`a6877f691a5b01363e62cd7206d27c63fcdd1eb21b35f980054b16b308f69e22`.

The interrupted local `Found 1 error in 1 file (checked 1 source file)` output
came from `PYTHONPATH=src ../safe_geocoding_pipeline/.venv/bin/mypy --strict
src/safe_geocoding_pipeline/preprocessing/stages/s07_component_readiness.py`.
At then-line 262, mypy inferred the applicability-reason mapping as a
Literal-keyed dictionary and rejected `.get(parser_applicability)` where the
validated parameter type was `str`. The readiness implementation introduced
the typing defect; an explicit `dict[str, str]` annotation corrected it without
changing runtime behavior or scientific semantics. The exact narrowed strict
mypy check now passes.

## Three independent status dimensions

### Parser applicability

The exact proposed vocabulary is:

- `PARSER_ELIGIBLE_COUNTRY`;
- `PARSER_ELIGIBILITY_MISSING_COUNTRY`;
- `PARSER_ELIGIBILITY_PARTIAL_COUNTRY`;
- `PARSER_ELIGIBILITY_INVALID_COUNTRY`; and
- `PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY`.

Applicability uses only accepted occurrence-level country provenance. No text,
script, parser-output, majority, first-occurrence, representation-priority,
geocoder, or model inference is permitted. Frozen DEVELOPMENT counts are
50,685 eligible and 1,094 unresolved of 51,779 candidates.

### Technical execution

The proposed vocabulary is:

- `PARSED_NONEMPTY`;
- `PARSED_EMPTY`;
- `NOT_ATTEMPTED_NOT_ELIGIBLE`; and
- `TECHNICAL_FAILURE`.

The DEVELOPMENT v2 logical view carries the immutable v1 technical status/raw
components in explicit v1 lineage fields and records the prospective v2 action
separately. Thus an unresolved row truthfully retains its historical v1 parse
evidence while its v2 technical status is `NOT_ATTEMPTED_NOT_ELIGIBLE`; no new
parser call is made and its v2 components are absent. `TECHNICAL_FAILURE` is
fail-closed diagnostic evidence and must be zero in an accepted publication
unless a later owner decision explicitly changes the v1 crash policy.

### Component readiness

The exact proposed vocabulary is:

- `COMPONENTS_READY`;
- `COMPONENTS_ABSTAIN`; and
- `NOT_ASSESSED`.

`COMPONENTS_ABSTAIN` means only that downstream code must not trust the parser
labels or boundaries as structured truth. It does not mean invalid address,
missing data, failed geocoding, or source-row deletion. `COMPONENTS_READY`
means no anomaly in the frozen Stage 7-local rule; it is not a guarantee of
semantic label correctness.

## Frozen prospective rule

Rule ID: **`stage07_component_readiness_rule_v1`**.

1. If applicability is not `PARSER_ELIGIBLE_COUNTRY`, set readiness to
   `NOT_ASSESSED` and retain the exact applicability reason.
2. If an eligible result is exactly `PARSED_EMPTY`, set readiness to
   `COMPONENTS_ABSTAIN` with `PARSED_EMPTY_NO_COMPONENTS`.
3. For an eligible `PARSED_NONEMPTY` result, derive the signals below from the
   exact candidate and exact ordered component values. If any structural reason
   is present, set `COMPONENTS_ABSTAIN`; otherwise set `COMPONENTS_READY`.
4. Representation (`STANDARD`, `NATIVE`, or both) and script are validation
   strata only. Neither is an abstention trigger.

The ordered reason vocabulary is:

- `PARSER_ELIGIBILITY_MISSING_COUNTRY`;
- `PARSER_ELIGIBILITY_PARTIAL_COUNTRY`;
- `PARSER_ELIGIBILITY_INVALID_COUNTRY`;
- `PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY`;
- `PARSED_EMPTY_NO_COMPONENTS`;
- `EMPTY_COMPONENT_VALUE`;
- `RAW_ORDERED_SUBSTRING_ALIGNMENT_FAILURE`;
- `LEXICAL_NUMERIC_MATERIAL_LOSS`;
- `LEXICAL_NUMERIC_MATERIAL_DUPLICATION`;
- `LEXICAL_NUMERIC_REORDER_OR_SUBSTITUTION`;
- `TOKEN_INTERNAL_COMPONENT_BOUNDARY`;
- `TOKEN_INTERNAL_SINGLE_CODEPOINT_FRAGMENT`;
- `LEXICAL_RUN_SPLIT_ACROSS_THREE_OR_MORE_COMPONENTS`; and
- `ADJACENT_REPEATED_LABEL_AT_INTERNAL_BOUNDARY`.

All text operations use deterministic Unicode general categories. A lexical or
numeric code point has a category beginning with `L`, `M`, or `N`. Component
values must align as ordered exact substrings, and their concatenated
lexical/numeric stream is compared exactly with the candidate stream. A token-
internal boundary is a component boundary between adjacent lexical/numeric code
points in one candidate lexical run. Fragmentation means one such run
intersects three or more nonempty component values. The implementation is
linear in candidate code points plus component count, apart from ordinary
substring search; memory is bounded by one candidate/result.

These detectors are script-independent and use only Stage 6 text plus raw
Stage 7 values. They can false-positive when libpostal legitimately omits
punctuation or represents tokens in a non-substring form, and they can
false-negative when component boundaries look regular but labels are
semantically wrong.

| Detector | Exact deterministic evidence | Inputs / cost | Main limitation |
|---|---|---|---|
| Ordered substring alignment | Each component value must be found exactly, in order, at or after the prior match end | Candidate + raw values; ordered substring search | Repeated substrings can admit more than one alignment; harmless wrapper transformations may abstain |
| Lexical/numeric stream equality | Concatenate every `L/M/N` code point from ordered values and compare exactly with the candidate `L/M/N` stream | Candidate + raw values; linear | Cannot judge correct semantic labels when text is preserved |
| Material loss/duplication/divergence | If unequal, classify by exact subsequence direction; neither direction is reorder/substitution | Same streams; linear | Conservative: intentional parser omissions can abstain |
| Token-internal boundary | With equal streams, a component boundary falls between adjacent source positions in one lexical run | Candidate positions + component spans; linear | Some languages may permit meaningful sub-token segmentation |
| Single-code-point internal fragment | A one-code-point component touches an internal boundary | Component spans; linear | A legitimate one-code-point unit can be flagged |
| Three-or-more-way fragmentation | One lexical run intersects at least three nonempty component spans | Linear two-pointer sweep | Threshold is a predeclared structural warning, not semantic proof |
| Adjacent repeated label at internal boundary | Adjacent nonempty components share a label and meet at an internal lexical boundary | Labels + spans; linear | Does not flag non-adjacent or semantically implausible labels |
| Empty component value | Any nonempty parse contains an exact empty value | Raw components; linear | Technical/schema pathology only |

No pre-parse signal other than trusted applicability is a readiness trigger.
Representation, script composition, mixed-script state, candidate length, and
token count are retained for validation stratification. They may describe risk
but are not proven causes and cannot independently force abstention in v1.

## Discovery behavior on the already-authorized 120

The immutable selection fingerprint is
`1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844`.
This deliberately risk-enriched selection is discovery evidence, not an
overall accuracy sample.

| Original classification | Ready | Abstain | Not assessed | Total |
|---|---:|---:|---:|---:|
| `PLAUSIBLE_PARSE` | 27 | 2 | 1 | 30 |
| `PARTIAL_BUT_USABLE_PARSE` | 25 | 16 | 0 | 41 |
| `QUESTIONABLE_PARSE` | 6 | 1 | 0 | 7 |
| `CLEAR_MISPARSE` | 1 | 10 | 0 | 11 |
| `UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE` | 10 | 16 | 5 | 31 |
| **Total** | **69** | **45** | **6** | **120** |

All six known clear token/word-boundary failures abstain. Four of five known
clear label-only failures also abstain because they have additional structural
anomalies; one structurally regular label-only failure leaks through as ready.
This is not evidence that the rule can recognize label semantics.

Among the 114 eligible reviewed cases, 45 abstain (39.474%). Among the 70
reviewed eligible usable cases (`PLAUSIBLE_PARSE +
PARTIAL_BUT_USABLE_PARSE`), 18 abstain (25.714%). Among 59 assessable ready
cases, 52 are usable (88.136%) and one is a clear misparse. These figures
describe only the enriched discovery selection and must never be reported as
global libpostal quality.

Four cases carry `PARSED_EMPTY_NO_COMPONENTS`. The fifth authoritative empty
case is one of the six `NOT_ASSESSED` rows because unresolved country
applicability takes precedence in v2. All five retain the prior qualitative
classification `UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE`; none was judged a
material parser failure.

The controlling conclusion is that the rule is useful as a conservative
structural-warning layer and catches the known dangerous boundary mechanism.
It is insufficient as a semantic-truth detector. Semantic label-only errors
that preserve text and regular-looking boundaries are **not detectable from
Stage 7 local evidence** without moving geographic validation into Stage 7.

Discovery signal counts overlap because one candidate may carry multiple
reasons:

| Structural reason | Clear | Questionable | Plausible | Partial usable | Upstream/unassessable |
|---|---:|---:|---:|---:|---:|
| Ordered-substring alignment failure | 3 | 0 | 1 | 10 | 12 |
| Lexical/numeric material loss | 0 | 0 | 0 | 0 | 4 |
| Lexical/numeric reorder/substitution | 0 | 0 | 0 | 0 | 1 |
| Token-internal component boundary | 8 | 1 | 1 | 7 | 4 |
| Token-internal one-code-point fragment | 4 | 1 | 0 | 0 | 4 |
| Lexical run split across at least three components | 2 | 0 | 1 | 6 | 4 |
| Material duplication, empty component value, or adjacent repeated internal label | 0 | 0 | 0 | 0 | 0 |

The plausible and partial columns are observed discovery-set false-positive
risk for a downstream “unsafe” interpretation, not proof that the warning is
wrong: some usable parses remain usable as whole strings even when their
component boundaries are structurally irregular.

## Fixed-500 identity and suitability audit

The following identifiers bind different objects and are not interchangeable:

| Identity | SHA-256 | Meaning |
|---|---|---|
| Fixed source-row selection | `014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52` | Contract/policy, Benchmark V1 identity, exact 500 stable source-row IDs and order |
| Projected Stage 6 candidate set | `8834a191efe0a77c5ace78760bd131e2c11bd904097b47e5ba1177f4172a5696` | Domain-separated sorted set of 613 exact Stage 6 candidate IDs reached from the fixed rows |
| Stage 6 review Parquet | `624978c807fce7f9a76383b76d88e52eb85fa9bfbd5c41ced071d4a40c079190` | Physical protected fixed-500 Stage 6 artifact |
| Stage 6 review manifest | `1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1` | Physical manifest binding the Stage 6 review bundle |
| Stage 7 fixed-500 Parquet | `67d259f8094be926677bd9f6b372aad5a90d459d9b10c85f3590dfe177b6ecdf` | Physical protected Stage 7 fixed-500 verification artifact |

The source-row selection was materialized by job `1758910`, before Stage 7
quality findings and readiness hypotheses. It uses accepted provenance and
structural strata plus domain-separated SHA-256 ranking; address text does not
enter its rank. It contains 500 rows, 937 representation occurrences, and 613
unique candidates. Candidate representation provenance is 325 `BOTH`, 144
`NATIVE_ONLY`, and 144 `STANDARD_ONLY`. Applicability is 457 eligible, 57
missing, two partial, 92 invalid, and five ambiguous; 212 distinct unanimous
country codes occur.

The exact selection algorithm is
`development_review_balanced_selection_v1`: deterministic quotas cover
country, geocoding history, batch priority, standard/native availability and
equality, line counts, missingness, script, and challenge reasons; remaining
capacity maximizes source-file coverage and then uses a domain-separated
global SHA-256 fill. At source-row level all 269 observed country strata are
represented. Script classes are 387 Latin-only, 53 mixed-script, 30 non-Latin,
and 30 common/unknown-only. Other risk coverage includes 170 multi-line rows,
20 very-long-field rows, 106 materially different STANDARD/NATIVE rows, and
200 prior-geocoding-failure rows. These are source-row selection properties;
the current candidate projection does not expose candidate-level script,
length, or structural-signal metadata, so they must not be silently promoted
to candidate-level counts.

Only nine of the 613 candidate IDs overlap the existing 120 and none overlaps
the targeted 18. Thus 604 candidates remain semantically untouched. The frame
is independent enough for fresh DEVELOPMENT validation and contains strong
source-row coverage across 269 countries and standard/native, missingness,
script, length, and challenge strata. Its current candidate artifacts do not,
however, materialize candidate-level script, length, or structural-signal
metadata. The fixed 500 is therefore accepted as the immutable validation
**frame**, not as an already-complete stratified review sample.

## Predeclared fresh validation design

Selection contract proposed:
`stage07_component_readiness_validation_selection_v1`.

1. Start from the 604 fixed-500 candidate IDs untouched by the existing 120.
2. Apply the already-frozen rule to those candidates with machine-only access
   to exact Stage 6 text and immutable raw Stage 7 components. Exclude
   `NOT_ASSESSED` from semantic quality denominators but report it completely.
3. Select exactly 240 eligible candidates: 120 predicted ready and 120
   predicted abstain. If either arm has fewer than 120, take the complete arm
   and transfer unused capacity to the other arm without replacement.
4. Within each arm, use deterministic quotas over representation provenance,
   Unicode script class, country-frequency band, and—within the abstain arm—
   reason code. Fill remaining capacity using a domain-separated SHA-256 rank
   over candidate ID. Candidate text and parser values do not enter the rank.
5. Freeze the selected candidate-ID fingerprint and all predictions before any
   semantic review. Use the existing five-category classification vocabulary
   without changing the original 120 artifacts.

The selected fingerprint cannot be computed without the separately authorized
machine-only application of the frozen rule; it is intentionally pending rather
than guessed in this design report.

Primary predeclared metrics and gates are:

- `READY_PRECISION`: usable / assessable predicted ready must be at least 95%;
- `CLEAR_MISPARSE_READY_LEAKAGE`: clear misparses / assessable predicted ready
  must be at most 2.5% and at most two cases;
- every reviewed case carrying a frozen structural abstention reason must be
  predicted abstain by exact rule replay;
- `USABLE_ABSTENTION_RATE`: abstained usable / all usable must be at most 40%;
- eligible-frame abstention coverage must be between 10% and 70%, preventing a
  vacuous almost-all-ready or almost-all-abstain policy; and
- representation/script/country/reason strata are reported, but no stratum-
  specific pass/fail claim is made below 20 assessable observations.

Upstream-corrupt/unassessable rows are excluded from ready precision and usable
abstention denominators but reported separately. Thresholds and rule may not be
tuned after fresh labels are opened. The balanced validation design estimates
the decision rule's behavior, not population-wide libpostal accuracy.

## Proposed lossless Stage 7 v2 logical schema

The v2 artifact is a new version or immutable sidecar/join, never an overwrite
of v1. Its logical candidate row contains:

- all five Stage 6 registry fields unchanged, including candidate ID, exact
  lowercase candidate, and total/standard/native occurrence counts;
- trusted country-provenance status and nullable unanimous ISO alpha-2 value;
- parser-applicability status;
- immutable `stage07_v1_parse_status` and exact
  `stage07_v1_libpostal_components` lineage fields;
- prospective v2 technical status and execution origin
  (`REUSED_IMMUTABLE_STAGE07_V1`, `NEW_V2_EXECUTION`, or
  `NOT_ATTEMPTED_NOT_ELIGIBLE`);
- prospective v2 ordered nullable
  `large_list<struct<label: large_string not null, value: large_string not
  null>>` with duplicates and order retained;
- component-readiness status;
- ordered non-null `large_list<large_string not null>` reason codes;
- libpostal bundle fingerprint;
- Stage 7 v2 contract/profile IDs;
- readiness-rule ID; and
- Stage 6/v1 input-binding and lineage fingerprints.

For an eligible reused DEVELOPMENT row, the v2 result is an exact reference or
copy of v1 and its origin is explicit. For an unresolved row, the historical v1
status/components remain available only as immutable provenance, while the v2
status is `NOT_ATTEMPTED_NOT_ELIGIBLE`, v2 components are null, readiness is
`NOT_ASSESSED`, and component-dependent downstream use is prohibited. A
physical sidecar may reference v1 rather than duplicate its large nested bytes,
but the joined logical view must validate all of these semantics exactly.

## Minimum Stage 7 exit guarantee

Before Stage 8 may begin, Stage 7 must guarantee:

- exact candidate identity, text, occurrence counts, and source map-back;
- trusted-country applicability with all unresolved cases explicit;
- exact parser bundle/runtime provenance and technical status;
- exact raw ordered libpostal values with no label mapping or deduplication;
- deterministic readiness/warning replay and explicit abstention;
- zero silent truncation, skipping, cross-wire, component invention, or source
  loss; and
- fresh validation of the structural readiness decision followed by independent
  Stage 7 review and acceptance.

Stage 7 does **not** guarantee semantic component truth, postal validity,
postcode/locality agreement, street existence, house-number validity,
geocoder success, or point-level accuracy. A ready parse may contribute a
structured hypothesis; it is never final truth. An abstained parse remains
available as raw evidence, while the exact whole candidate remains eligible
for separately approved whole-string hypothesis generation.

## Authorization boundary and next decision

No new protected semantic content was inspected. HOLDOUT and production were
not accessed. The exact next DEVELOPMENT task remains in this same Stage 7
session and requires new owner authorization for two bounded scopes:

1. machine-only rule application to the 604 untouched fixed-500 candidates,
   including their exact Stage 6 candidate and immutable raw Stage 7 component
   streams, solely to freeze the 240-candidate validation selection; and
2. owner-authorized qualitative inspection of only those 240 selected
   candidates and outputs after their IDs, predictions, selection fingerprint,
   and thresholds are frozen.

The machine-only protected operation should be one bounded Goethe SLURM job;
it needs no parser call, network, new model, full 51,779-row nested scan,
HOLDOUT, or production access. No future stage implementation is authorized by
this report.

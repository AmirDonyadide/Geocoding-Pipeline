# Proposed post-Stage-7 geocoding architecture redesign

Status: **STAGE 8 DESIGN READY; STAGES 9–14 PROPOSED — NOT STARTED**. The
original compact proposal superseded the prior unstarted Stage 8–19
decomposition prospectively. The Stage 8 portion is now narrowed by the
[Stage 8 scientific contract](../../docs/stages/STAGE08_ADDRESS_EVIDENCE_PROJECTION.md).
Nothing here implements or executes Stage 8, authorizes Stage 9, authorizes
geocoding, or changes the current rule that no geocoding workload may run
before the governing pre-geocoding design is accepted and separately
authorized.

Stages 0–6 and the immutable Stage 7 v1 evidence are unchanged. Exact Stage 7
evidence-only v2 candidate `656a16d3…` passed independent rereview and is
accepted as `STAGE_7_ACCEPTED` on DEVELOPMENT. That acceptance does not promote
parser output to semantic/geographic truth. Stage 8 design is now ready, but
implementation and execution remain unauthorized.

## Governing philosophy

```text
SOURCE TRUTH
  -> preserved parser/reference evidence
  -> multiple immutable address hypotheses
  -> globally deduplicated geocoder queries
  -> top-N self-hosted Pelias results
  -> independent evidence scoring and cross-query convergence
  -> explicit accepted granularity or UNRESOLVED
```

A parser is evidence, not truth. A hypothesis is not source truth. A Pelias
feature—even the top feature—is not an accepted match. No hypothesis or result
overwrites the exact Stage 6 candidate or any earlier source value.

## Proposed compact numbering

### Stage 8 — Lossless address-evidence projection

- **Responsibility:** Preserve the complete accepted Stage 7 row, expose a
  reversible ordered long-form parser-evidence index, and retain exact
  source/representation map-back. Preserve duplicate and unknown labels. A
  one-to-one SAFE parser-evidence name is mechanical evidence, not a hypothesis
  or verified component. Warning absence never establishes trust.
- **Input:** Exact accepted Stage 7 v2 candidate evidence plus the exact
  accepted Stage 6 row map needed for source/representation lineage.
- **Output:** Candidate evidence, ordered parser-component evidence, a
  source-candidate map, and a deterministic occurrence view. No hypothesis,
  reference evidence, address-format requirement, or validity result.
- **Preferred tools/data:** PyArrow/Parquet plus bounded DuckDB validation.
  Polars is not required in v1. Stage 8 introduces no pycountry,
  libaddressinput, or external-data dependency.
- **Acceptance:** Exact upstream preservation, nested/long reversibility,
  complete known/unmapped label retention, complete map-back, deterministic
  fingerprints, bounded memory, and zero semantic-trust claims.
- **Replaces:** the lossless evidence-mapping responsibility of old Stage 8.
- **Status:** `STAGE08_ADDRESS_EVIDENCE_DESIGN_READY_FOR_IMPLEMENTATION`; not
  implemented or executed.

### Stage 9 — Offline geographic reference evidence

- **Responsibility:** Add positive or contradictory evidence for
  country/postcode/locality/admin and street/house-number coexistence. Absence
  from an incomplete open reference is `NOT_FOUND`, never automatic
  invalidation. Fuzzy comparison is permitted only inside strong deterministic
  geographic blocks.
- **Input:** Stage 8 evidence and exact candidates.
- **Output:** Versioned reference matches, candidate sets, similarity evidence,
  contradictions, coverage state, and reference lineage.
- **Preferred tools/data:** pinned GeoNames country/admin/postal files; pinned
  Overture Maps Addresses GeoParquet; optional local OSM evidence where its
  ODbL obligations and incremental value are approved; RapidFuzz after
  country/postcode/locality blocking; exact-code ISO/subdivision metadata from
  a separately pinned pycountry release where justified; pinned offline
  libaddressinput format/required-field metadata where justified; DuckDB for
  predicate-pushed joins; PyArrow for publication. Polars is optional for
  bounded lazy transformations, not a required second query engine. Runtime
  Address Data Service and Google Address Validation API calls are prohibited.
- **Acceptance:** Pinned release/license/coverage, false-positive review,
  bounded blocking, strong-positive definition for contradiction, no
  absence-as-invalid logic, and full evidence provenance.
- **Replaces:** old Stages 11, 13, 14, 15, and correction-evidence portions of
  16. It does not silently correct source truth.

### Stage 10 — Multi-hypothesis query-plan generation

- **Responsibility:** Generate a small deterministic set of plausible address
  and query hypotheses per source candidate. Whole-string standard/native
  candidates remain available regardless of parser warnings. Structured
  hypotheses may use parser components only as explicitly identified evidence,
  alongside reference-supported variants; they are never source truth.
- **Input:** Stage 8 evidence plus accepted Stage 9 reference evidence.
- **Output:** Immutable hypothesis IDs, hypothesis type/reason, exact fields,
  source/candidate map-back, and bounded query ladders.
- **Preferred tools/data:** SAFE deterministic rules, Arrow schemas, pinned
  Unicode behavior, and evidence from Stages 8–9.
- **Acceptance:** Source truth/hypothesis separation, no overwrite, bounded
  hypotheses, deterministic IDs/order, complete representation lineage,
  multilingual review, and explicit fallback/omission reasons.
- **Replaces:** old correction output in Stage 16 and old Stages 17–18.

Possible hypothesis families—subject to the Stage 10 design review—include
exact cleaned STANDARD, exact cleaned NATIVE, parser-evidence-derived structure,
house-number/street/postcode/locality combinations, street/postcode/locality,
street/locality, and postcode/locality. They are examples, not a frozen ladder.
Unsupported or contradicted variants must not be generated merely to increase
query count.

### Stage 11 — Global query identity, deduplication, and workload QA

- **Responsibility:** Canonically serialize endpoint plus exact parameters,
  deduplicate identical queries globally, and preserve complete
  source/candidate/hypothesis/query map-back. Freeze the separately authorizable
  Pelias workload.
- **Input:** Accepted Stage 10 query plans.
- **Output:** Collision-checked unique query registry, map-back tables, workload
  resource/concurrency plan, and final privacy/integrity evidence.
- **Preferred tools/data:** DuckDB for external joins/deduplication; PyArrow and
  Parquet for typed immutable publication; cryptographic hashing. Polars is
  optional where it demonstrably simplifies a bounded lazy transformation.
- **Acceptance:** Exact query-key contract, collision handling, zero source-row
  loss, total map-back, no protected leakage, bounded workload, and separate
  explicit authorization before any request.
- **Replaces:** old normalized/component deduplication Stage 12 and old query
  deduplication/QA Stage 19.

### Stage 12 — Self-hosted SAFE Pelias top-N retrieval

- **Responsibility:** Execute only the accepted Stage 11 workload against
  self-hosted SAFE Pelias, retaining top-N results and technical response
  provenance. It does not select a final truth.
- **Input:** Separately authorized Stage 11 unique queries.
- **Output:** Immutable query-response records with all retained features,
  score metadata, layer, source, accuracy, match type, request identity,
  endpoint/version, timing, and errors.
- **Preferred tools/data:** self-hosted SAFE Pelias; structured search where
  fields are justified and unstructured search for whole-string hypotheses.
  Normal total concurrency remains 2–4 across the complete process.
- **Acceptance:** Exact workload identity, privacy/authentication controls,
  bounded concurrency/retries, complete result/error map-back, top-N retention,
  and proof that retrieval did not imply acceptance.
- **Relationship to old plan:** makes the formerly external Pelias boundary an
  explicit scientific stage after the accepted workload gate.

### Stage 13 — Result evidence scoring and cross-query convergence

- **Responsibility:** Rank retained Pelias results deterministically against
  trusted input and independent reference evidence. Country contradiction can
  hard-reject a result; postcode, locality/admin, street, house number,
  STANDARD/NATIVE agreement, reference support, Pelias layer/match metadata,
  and cross-query convergence contribute separate evidence.
- **Input:** Stage 12 top-N results and Stages 8–10 evidence.
- **Output:** Per-result evidence vectors, supporting/contradicting facts,
  convergence groups, rank, and abstention evidence.
- **Preferred tools/data:** DuckDB for joins/aggregation; RapidFuzz only inside
  approved geographic blocks; SAFE scoring policy; Arrow/Parquet publication.
- **Acceptance:** Predeclared evidence features and contradiction policy,
  deterministic ranking, calibration/ablation on DEVELOPMENT, bias and
  granularity analysis, no hidden oracle, and independent review. Numeric
  weights are not frozen by this architecture report.
- **Relationship to old plan:** adds the explicit post-geocoder validation and
  arbitration layer missing from the old 8–19 plan.

### Stage 14 — Final match, granularity, and abstention decision

- **Responsibility:** Accept a result only at the strongest evidence-supported
  spatial granularity, or return `UNRESOLVED`. A lower-granularity truthful
  result is preferred to a false rooftop point.
- **Input:** Accepted Stage 13 ranked evidence.
- **Output:** latitude, longitude, accepted granularity, evidence/confidence
  class, winning query/result IDs, supporting and contradicting evidence,
  fallback reason, and complete lineage.
- **Granularity vocabulary:** `EXACT_ADDRESS`, `STREET_ADDRESS`, `STREET`,
  `POSTCODE`, `LOCALITY`, `ADMIN`, `UNRESOLVED`. `ROOFTOP` is recorded as
  feature accuracy/evidence and can support `EXACT_ADDRESS`; it is not inferred
  from a precise-looking coordinate.
- **Preferred tools/data:** SAFE deterministic acceptance policy over Stage 13
  evidence and retained Pelias metadata.
- **Acceptance:** Predeclared granularity-specific thresholds, high-precision
  DEVELOPMENT evaluation, contradiction and ambiguity handling, explicit
  unresolved/fallback behavior, source-row totality, and independent review.
- **Relationship to old plan:** new explicit final scientific decision stage.

## Evidence interpretation

Country is trusted upstream context and a hard contradiction can reject a
result. Postcode and locality/admin agreement are strong independent evidence;
street similarity and exact house-number agreement add finer-grained support.
Agreement between STANDARD and NATIVE hypotheses and convergence of independent
query variants increase confidence. Disagreement remains visible uncertainty.
Pelias `confidence`, `layer`, `match_type`, and `accuracy` are evidence fields,
not acceptance by themselves.

No numeric weights or match thresholds are frozen here. Each scoring feature,
interaction, hard rejection, and granularity decision requires a predeclared
Stage 13/14 DEVELOPMENT design and evaluation. The final output must retain
both supporting and contradicting evidence rather than compressing uncertainty
into a single opaque score.

## Tool and dataset roles

| Tool/data | Proposed role | Controlling limitation |
|---|---|---|
| Default libpostal | Stage 7 raw parser evidence under the pinned bundle | Statistical parser, not geographic truth; documented in-scope errors remain |
| Senzing libpostal model | No current execution; possible separately approved model diagnostic only | A model change is scientific, needs a new frozen comparison, and is not required for this architecture |
| Google libaddressinput | Possible pinned offline country format/required-field evidence in Stage 9 | Not a free-text parser or Google Address Validation API; no runtime remote service; absence cannot imply invalidity |
| pycountry | Possible exact-code ISO country/subdivision identity in Stage 9 | No fuzzy inference approved; no postal, street, or geographic validation |
| GeoNames | Pinned postal/locality/admin reference evidence | Coverage/vintage vary; absence is not invalidity |
| Overture Maps Addresses | Versioned address-point/street evidence in Stage 9 | Coverage and source licenses vary; pin release and lineage |
| OpenStreetMap | Optional local gap evidence | ODbL attribution/share-alike and regional completeness require review |
| RapidFuzz | Deterministic bounded string evidence | Never global correction; only within strong geographic blocks |
| DuckDB | Primary out-of-core joins, blocking, deduplication, aggregation | Queries must remain bounded and plan-verified |
| PyArrow/Parquet | Canonical typed contracts and immutable artifacts | Stream/batch giant values; avoid whole-population Python materialization |
| Polars | Optional lazy/streaming transformations | Use only where it adds clear value; avoid duplicate engine complexity |
| Self-hosted SAFE Pelias | Top-N candidate retrieval in Stage 12 | Returned/top feature is not truth; separate workload authorization required |

Public project evidence supporting these roles includes the official
[libpostal project](https://github.com/openvenues/libpostal),
[Senzing model documentation](https://github.com/Senzing/libpostal-data),
[libaddressinput repository](https://github.com/google/libaddressinput),
[GeoNames downloads](https://download.geonames.org/export/),
[Overture Addresses documentation](https://docs.overturemaps.org/guides/addresses/),
[OpenStreetMap copyright/licensing](https://www.openstreetmap.org/copyright),
[RapidFuzz documentation](https://rapidfuzz.github.io/RapidFuzz/),
[DuckDB Parquet documentation](https://duckdb.org/docs/stable/data/parquet/overview),
[Apache Arrow dataset documentation](https://arrow.apache.org/docs/python/dataset.html),
[Polars streaming documentation](https://docs.pola.rs/user-guide/concepts/streaming/),
and the official [Pelias documentation](https://github.com/pelias/documentation).
Every eventual stage must pin exact versions, releases, licenses, and offline
assets before protected execution.

## Legacy-plan mapping

The prior Stages 8–19 were conceptual and never started. If this proposal is
approved, their responsibilities map as follows:

| Old unstarted responsibility | Proposed replacement |
|---|---|
| Stage 8 component mapping | Stage 8 lossless evidence projection and reversible parser-evidence index |
| Stage 10 code normalization; format and reference parts of Stage 11; Stages 13–15; evidence portions of Stage 16 | Stage 9 offline reference evidence |
| Stage 9 linguistic normalization; correction candidates in Stage 16; Stages 17–18 | Stage 10 multi-hypothesis generation |
| Stage 12 normalized dedup; Stage 19 query dedup/QA | Stage 11 global query identity and workload QA |
| Old external Pelias boundary | Stage 12 top-N retrieval |
| No explicit equivalent | Stage 13 result evidence scoring/convergence |
| No explicit equivalent | Stage 14 final granularity/abstention |

The old plan is superseded only prospectively; it was not executed and is not
retroactively relabeled. The current repository prohibition on geocoding before
the governing pre-geocoding gate remains controlling until this redesign is
separately approved and repository execution policy is deliberately updated.

## Exact next task and session boundary

The next task is a **fresh Stage 8 DEVELOPMENT implementation session**, not
implementation in the design session and not execution. It must implement the
accepted design contract, schemas, mapping, validators, synthetic tests, and
sanitized reporting. A protected DEVELOPMENT job remains a later separately
reviewed and authorized action. The failed
`stage07_component_readiness_rule_v1` remains immutable history and is not a
future trust gate.

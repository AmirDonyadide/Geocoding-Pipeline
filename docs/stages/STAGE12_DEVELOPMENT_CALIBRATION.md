# Stage 12 — DEVELOPMENT calibration, deep-tail audit and final N

Normative part of the owner-revised [design](STAGE12_PELIAS_TOPN_RETRIEVAL.md).
The process is specified now; actual safe protected depths are frozen at the
pre-DEVELOPMENT gate below. No protected outcomes, probe results or scientific
N are claimed. HOLDOUT remains sealed; Stage 10 operating budget UNSELECTED.

## Three different depths and the pre-DEVELOPMENT gate

- **N: final operational depth = UNSELECTED.** DEVELOPMENT evidence selects it.
- **C: full-DEVELOPMENT calibration ceiling.** Proposed planning value 10, not
  a frozen protected workload or claim of tail saturation. Owner freezes exact
  C after public deployment/capacity evidence, before protected retrieval.
- **T: deep-tail audit depth = UNSELECTED_PENDING_PUBLIC_CAPABILITY_PROBE.**
  Require T > max(C,10). Do not guess a large size or run all requests at T.

A public probe establishes supported/safe sizes, not scientific quality or N.
Before any protected calibration request, the owner must review and freeze a
calibration authorization object with: exact C and T; finite primary grid
G = sorted unique values in {1,3,5,C} not exceeding C (C >= 5); exact deployment/
index/materialization/content binding; verified auth and drift mechanism;
operations/timeouts/attempt/rate profile; response caps; tail selection protocol,
capacity/coverage checks and controlled subset hashes; evidence/projection
versions; zero-loss/stop rules; bounded request/control/segment/storage budgets;
and the disclosure plan. C and T must be sizes actually supported by the probe.
A C other than 10 must be justified in that pre-outcome record, not chosen after
examining protected results. No dynamic per-request depth or family pruning.

Use two ordered gates: (1) post-public-probe owner freezes all depth/selection/
witness rules and authorizes a guarded **offline-only** DEVELOPMENT preflight;
(2) preflight materializes exact subsets from accepted input, reports coverage/
GET sizes/quota and fingerprints without a Pelias call; owner verifies those
objects and authorizes the exact protected network workload. Selection failure
or insufficient capacity stops before calls. No opportunistic changes after
seeing results. These gates do not permit HOLDOUT or production.

## Future state machine

~~~
OWNER DESIGN FREEZE (not performed in this revision)
 -> separately authorized implementation + synthetic tests + review
 -> separately authorized PUBLIC/SYNTHETIC SAFE probe
 -> OWNER REVIEW: deployment/auth/drift mechanism, safe rate and C/T
 -> freeze protected calibration rules; authorize offline preflight
 -> verify exact subset/workload/coverage; authorize protected calibration
 -> complete DEVELOPMENT at C + bounded deep-tail at T + paired-size diagnostic
 -> offline DEVELOPMENT witness/adequacy analysis + review
 -> if INSUFFICIENT CALIBRATION DEPTH or COVERAGE: STOP for redesigned calibration
 -> otherwise OWNER FREEZE OF FINAL N and retrieval_policy_id
 -> N == C: validate reuse gates
    N != C: separately authorize complete direct-N DEVELOPMENT retrieval
 -> complete artifact/projection validation + independent review
 -> OWNER ACCEPTANCE; STOP before Stage 13
~~~

No state transition is authorized merely by passing the previous one. An
insufficient tail cannot be waived into N=T or N=C by cost/owner preference
within this protocol; it needs a new reviewed bounded calibration design.
Revised calibration may use existing immutable responses where bindings match,
but cannot retroactively relabel the first audit as a successful saturation test.

If N=C, qualifying complete calibration raw observations can become final
retrieval evidence without another network workload. Bind owner N freeze, exact
input/materialization/policy/deployment/index and capture provenance. Validate
the final projection and preserve the original calibration publication.
A revised extractor may replay those same raw observations under a new approved
projection without a new call. This is different from relaxing executable
matching for a running network campaign/checkpoint.

If N!=C, a second **complete direct-size** DEVELOPMENT workload is required.
Never relabel C-prefixes or tail-subset results as direct-N executions. A code
refactor alone is not a new network identity; a new network campaign records its
own exact executable. Changed result-affecting deployment/index invalidates
automatic transfer of calibration conclusions and needs reviewed recalibration.

## Public/synthetic deployment probe

After implementation authorization, offline synthetic tests establish canonical
IDs with code/extraction/operations/signature changes excluded where specified,
exact Unicode/plus/LF/postcode serialization, raw decoded-payload hashing,
storage recompression equality, offline re-extraction/version changes, malformed
feature audit/no filtered rows, duplicate ranks, all errors, secrets, rate
limits, multi-job crash recovery and publication faults. Use mock services for
deliberate timeout/TLS/malformed/overload tests, not a live overload experiment.

Before live public calls, the operator supplies documented supported size bounds
and a finite proposed ladder of **at most two deeper sizes above 10**. Exact
numbers and per-size resource guards are approved in the public probe workload;
they are not inferred from protected outcomes. If no documented safe candidate
above 10 exists, probe readiness fails rather than silently omitting tail work.

Freeze 64 public/invented cases (32 per mode), with public provenance, diverse
scripts, boundary/postcode/escaping/ambiguity and empty-result-intended examples.
No protected text. Main probe: 64 x {1,3,5,10} x two repetitions = 512 calls.
Deep capability probe: 16 preselected cases (eight per mode, drawn from those
64 by frozen ID order/coverage) x at most two operator-approved deeper sizes x
two repetitions = at most 64 calls. Execute size ladder ascending; stop before
the next depth on limit/latency/overload/schema failure. Reserve at most 16
additional explicitly described authentication/GET-limit/identity checks.
Total ordinary call ceiling **592**, and at most 2,960 attempts at five attempts
each; circuit breakers and segment budgets normally stop earlier. Any probe
increase above initial 1 request/second/two connections is a separately bounded,
owner-authorized public subplan, not automatic tuning or protected load testing.

Verify endpoints, auth, exact serialization/schema/decoded payloads, safe size/
byte limits, index/content acquisition and the feasible drift-observability mode.
No Pelias-quality metric from public examples selects scientific N, C for
scientific usefulness, or a tail sufficiency conclusion. Safe-size observations
only bound choices at the pre-DEVELOPMENT owner gate.

Compare repeated same-size ordered **full feature structural equality**, retaining
every key/value, array order, exact strings and JSON numeric token spelling;
ignore only object key order/whitespace. Exclude response-level timestamps and
size echoes, not feature confidence/match/labels. Raw payload hashes remain
separate provenance and need not equal when timestamps differ. A same-size
feature disagreement blocks reproducibility approval pending investigation.
Cross-size agreement is only tested-case agreement, never universal equivalence
or permission to merge policy/execution IDs.

## Frozen deterministic protected subsets

The deep-tail audit uses at most **2,000 distinct semantic requests**, an
engineering cap below 2% of the full catalog; it is not a statistical power or
recall guarantee. The paired-size diagnostic uses at most 400 of those requests.
Both are selected **before any protected response** using accepted upstream
metadata, not Pelias confidence, returned ranks or observed failures.

Derive diagnostic labels through the exact Stage 11 -> Stage 10 context ->
Stage 8 occurrence chain. Never choose one representative context for a shared
request. Script classification uses the pinned Unicode 16 resource on accepted
source representation line-body text: ignore Common/Inherited; no remaining
script=COMMON_ONLY; one script=that script; otherwise MIXED. Completeness is
four exact-nonempty booleans for source line body/postcode/locality/region.
Capability signature is the accepted Stage 9 country/question/reference vector
(enabled, granularity, positive/negative authority), including explicit
unsupported states. Missing registry rows are integrity failure, not weak
capability. Preserve representation and Stage 10 eligible family incidence,
including Q4 evidence-driven and Q6 transliteration lineages.

Freeze mandatory coverage cells comprising every nonempty:
country x mode, script x mode, capability-signature x mode, completeness-mask x
mode, representation x mode, and family x mode. Country x capability is also
reported (where the registry makes it constant within country it adds no new
quota). Each cell requires min(2, available distinct source rows) represented
by selected requests. This provides explicit minimum coverage, not independent
statistical evidence. All source links of a selected shared request count
toward coverage; repeated queries from the same source cannot fill a second
source slot.

Selection algorithm:
1. Enumerate cell populations and per-request memberships with exact source-row
   links in controlled external joins.
2. Start empty. At each step choose the request that covers the largest number
   of still-missing cell/source quota units, counting at most one unit per
   cell for that choice. Break ties by full H("SAFE:stage12-tail-sample:v1",
   [protocol version, query_semantic_id]); then full semantic ID. Update covered
   source sets for all its actual members.
3. Stop quota selection when all cells pass, no gain is possible, or 2,000
   requests are selected. Any unsatisfied quota means
   INSUFFICIENT_CALIBRATION_COVERAGE: STOP; no automatic cap increase or
   omission of rare/weak-reference cells.
4. If quota coverage passes before 2,000, fill deterministically up to 2,000
   (or catalog exhaustion) round-robin over sorted complete request strata:
   (country, mode, sorted set of occurrence script/capability/completeness/
   representation/family tuples). Order strata and remaining requests by the
   same domain-separated framed hash with full-byte tie-break.
5. Select the paired-size subset as the first min(400, tail count) under the
   separate H("SAFE:stage12-paired-sample:v1", [protocol version, semantic ID]).
   Report its coverage; unlike the tail audit it does not claim every cell.
6. Seal exact IDs, populations/coverage, input/selection hashes and request
   budgets at the preflight gate before dispatch. No replacement of failed or
   inconvenient cases, no post-outcome expansion of this audit.

All 105,805 requests run at C. Tail subset runs at T **twice**, in separate
diagnostic observation campaigns, to check repeat stability. Paired subset runs
each g in G except C once, then every g in G once again (C's first observation
already exists in the full run). Intentional repeats are separately authorized
observations/artifacts, not duplicate terminal rows in one artifact.

With m<=2,000 tail requests, p<=400 paired requests and g=|G|<=4, ordinary
protected calibration calls are exactly
105,805 + 2*m + (2*g-1)*p, at most **112,605**; maximum attempts **563,025** at
the proposed ceiling five. The result-position/storage ceiling is
105,805*C + 2*m*T + p*(2*sum(G)-C), with actual decoded byte caps and retained
audit/projection copies budgeted separately. T is bounded by the frozen public
capability/owner decision, not silently increased. Control calls have an exact
approved segment/time budget and share the rate pool. Final direct-N, if needed,
adds 105,805 calls, at most 529,025 attempts. Multi-job scheduling is expected.

## Prefix behavior and deep-tail adequacy

Each size retains distinct retrieval_policy_id and request_execution_id even
with perfect prefix agreement. Evaluate full-population C-prefixes as retention
diagnostics, and actual direct-size sets separately. Record additions, losses,
reordering and same-size instability; no monotonicity assumption across sizes.

For the tail audit, compare both (a) ranks C+1..T within each T response and
(b) the entire T response against that request's actual C response, using the
witness sets defined below. This catches deeper-size changes in the first C
positions as well as additional ranks. Test equality of T's first C full
features against direct C as a separate prefix diagnostic. A new potentially
useful candidate anywhere in T that C did not preserve means C was not
established adequate, even if it appeared at T rank 1.

Tail adequacy passes only when:
- every mandatory audit cell is covered, all scheduled responses are valid,
  both T observations repeat stably and all identity/integrity gates pass;
- for every audited request and **every linked source context**, no potential
  witness token is new beyond C within T, and V(u,q,T) is a subset of
  V(u,q,C-direct);
- no potentially useful novelty persists to the deepest audited rank T.

Any observed useful/unknown tail novelty, including at the deepest rank, yields
**INSUFFICIENT CALIBRATION DEPTH**. Stop before final N selection and redesign
the bounded calibration with owner review. No choosing the maximum tested
rank, trading loss for storage, or adaptive extra call to explain away a case.
Technical uncertainty/coverage failure cannot be called saturation.

A passing bounded audit supports adequacy only for the declared design and
sampled strata. It is not proof that all 105,805 queries, unobserved ranks >T
or the world have no useful tail. Publish coverage and that limitation. The
owner can reject adequacy and commission a new predeclared audit; cannot claim
global recall from zero observed loss. Tail failure rules cannot be relaxed
after observing protected responses.

## Evidence questions without Stage 13 scoring

Scientific usefulness means **additional evidence an eventual scorer could
evaluate**, not an adjudicated correct address. Retain separate diagnostic
channels, each with its own denominator and dependence label:

| Channel | Permitted comparison / limit |
|---|---|
| Source country | Candidate explicit country code vs accepted recognized source country; interpret the response code namespace only through the deployment descriptor and frozen ISO mapping. Missing/ambiguous code is not evaluable. This is agreement with a query constraint, not independent confirmation. |
| Source postcode | Exact accepted Stage 9 country-specific full-code comparison keys for candidate/source values, only at comparable granularity. Keep raw strings; no new trimming/truncation. Report literal/source agreement separately from any existing Q04 format or Q05 membership support. Pattern support is not postal existence. |
| Locality/admin | Compare exact name keys using NAME_NFC_LOWER_U16_V1 and existing accepted scoped reference witnesses/aliases at matched levels. No fuzzy matching, new alias inference or arbitrary source-region=admin1 assumption. Unknown level is NOT_EVALUABLE. |
| Existing Stage 9 support | Join source/context-scoped Q01, Q04–Q11 and witnesses with exact origin pointers; test whether returned components preserve a previously supported claim. Do not re-run Stage 9 on Pelias candidates or generate new candidate truth labels. Accepted country assessments are unresolved (zero qualifying Q02 witnesses); do not invent resolved Stage 9 countries. |
| Parser evidence | Stage 8 component boundaries/labels are descriptive parser evidence, not independent source/reference support. Parser and Pelias restatements of the same text cannot add votes. |
| Distinct candidate contribution | By rank, count new GIDs where available and separately new exact full-feature structures, source/layer and coordinate diversity. Missing GID is explicit; no coordinate/label dedup of stored rows. These are information-volume diagnostics. |
| Cross-query convergence | Within exact source context/representation/family lineage, report repeated non-null GID and exact feature-structure incidence across semantic requests. Separate same source, same candidate, shared query and shared importer ancestry. No convergence score or independent confidence. |

The diagnostic computation uses the accepted Stage 9 comparison methods only
on temporary comparison keys; it never normalizes request payloads or stored
candidate strings. Existing SUPPORTED, CONTRADICTED, NOT_FOUND, NOT_EVALUABLE
states remain at their exact original scope. A literal unequal candidate/source
value is reported as disagreement, not a new negative-authority certificate.
NOT_FOUND and NOT_EVALUABLE never count as contradictions or negative votes.
Q12/Q13 street/house reference capability is absent in Stage 9; no street/
house-number validation claim is available. All returned layers stay visible.

Dependency classes are inherited/reconciled from accepted registry lineage:
SELF/DERIVED_FROM, KNOWN_SHARED, POSSIBLE_SHARED, UNKNOWN, PROVEN_DISJOINT only
with positive importer evidence. Stage 9 GeoNames and Pelias GeoNames/Who's on
First may overlap; differing source names do not prove independence. Source
STANDARD/NATIVE and multiple families share Orbis origin. Report channels
separately; no summed evidence count, numeric candidate score, hard gate,
winner, or confidence-weighted utility.

## Bounded calibration-only witness model

Freeze stage12_calibration_witness_v1 with the approved response projection
before outcomes. It is a deterministic information-retention screen, not
Stage 13 scoring or candidate rejection.

For context u, semantic request q and feature f:
1. Form evidence key K(f) from the exact extracted feature ID/GID/source/source_id/
   layer, geometry type/longitude/latitude, accuracy string and all label/name/
   address/admin component fields in DC schema order. Exclude rank, request/
   response hashes, byte locators, confidence and match_type. No string cleanup
   or GID/coordinate-only collapse. Distinct K means potentially different
   evidence; identical K only supports diagnostic set membership, never removal
   of a returned row. Confidence/match_type-only changes are descriptive and
   cannot create scientific value or independent confirmation.
2. Produce a finite channel-state vector using the comparison rules above.
   Country/source full postcode/locality/admin comparisons are
   SOURCE_COMPATIBLE, SOURCE_DISAGREEMENT or UNEVALUABLE. Existing accepted
   reference support is REFERENCE_COMPATIBLE only when a scoped positive
   witness, exact permitted comparison key and matching granularity connect
   the returned component to the already accepted source claim.
3. For each compatible channel create one token
   (K, claim kind, accepted origin claim key, ancestry group, dependence class).
   All source/query/parser/Pelias restatements of the same source-field claim
   share one origin key, regardless of how many families or hypotheses echo
   it. Reference aliases/mirrors/components sharing an ancestor/claim are one
   group with preserved member pointers, not multiple votes. PROVEN_DISJOINT
   requires positive importer lineage evidence; POSSIBLE_SHARED/UNKNOWN remain
   correlated/unknown, never independent by default.
4. Add a conservative potential-information token (K, POTENTIAL_UNRESOLVED)
   whenever no compatible channel exists, any relevant channel is unevaluable,
   ancestry independence is unknown, or unmodeled feature content might carry
   later evidence. Even a candidate with source disagreement remains available
   as unresolved potential; Stage 12 applies no hard contradiction/granularity
   gate. Existing NOT_FOUND/NOT_EVALUABLE cannot remove that token.
5. If unknown feature properties differ, conservatively add an OPAQUE_EXTENSION
   token identified by their exact structural content (sorted object keys,
   exact strings/numeric tokens, array order). This avoids claiming losslessness
   from the small extracted schema. Raw provenance remains available. Unknown
   metadata cannot be declared useless after observing its tail distribution.

The opaque subtree is all non-extracted feature-level members plus all
non-extracted properties, excluding only feature.type, geometry.type and
geometry.coordinates (fully validated by DC), feature.id and the explicit
properties consumed by the DC schema.
Confidence/match_type are known consumed properties, so they cannot re-enter
utility through this subtree. Other additional geometry/feature members remain
opaque evidence. Null/absent and exact number token distinctions are retained.
Token fields follow E framing in declared order; K uses schema field order and
binary64 bits from DC, and full-byte comparisons guard hash collisions. For
stratum fill order the domain is SAFE:stage12-tail-stratum:v1 with ordered
fields protocol_version and full stratum tuple; request ties use the separate
tail-sample domain above.

A feature is **POTENTIALLY_USEFUL_WITNESSED** if it has a new compatible token;
**POTENTIALLY_USEFUL_UNRESOLVED** if it adds a potential/opaque token; otherwise
it is **REDUNDANT_FOR_THIS_CALIBRATION_SCREEN**. Those are calibration-only
observations, never address truth labels. Pure duplication of a claim across
parsers/families/queries adds no token. Novel candidate K can add an alternative
without becoming an independent confirmation. Source agreement is explicitly
correlated with the query; only PROVEN_DISJOINT reference tokens may be reported
as independently sourced support, and no vote/score is calculated.

V(u,q,k) is the **set union** of these tokens at ranks <=k within the named
response observation. Useful marginal gain k->l exists iff
V(u,q,l) minus V(u,q,k) is nonempty. Report compatible and unresolved gains
separately, with dependence class; do not sum evidence-family counts as strength.
Each query/context comparison is bounded by depth, fixed component channels
and fields in its byte-capped payload. Reference witness alias sets are joined
externally to existing accepted objects, collapsed by claim/ancestry; never
truncated to a convenient top-k or copied into a growing Python collection.

## Metrics and exact final N freeze rule

Report adjacent ranks and G transitions for each context and request, then
aggregate: new compatible/unknown tokens, new alternative K, first compatible
occurrence, only-low-rank evidence, unresolved/opaque tails, duplicate positions,
coarse/source/layer diversity, direct-policy additions/losses and actual bytes/
latency/storage. Report source-row summaries separately; do not multiply
denominators by parser components, hypothesis edges or overlapping families.
Country/script/mode/capability/completeness/representation/family strata retain
their explicit populations. Full cross-tabs remain controlled.

Apply these deterministic gates, in order:
1. Integrity/totality and reproducibility pass; no unresolved technical/contract/
   deployment failure. Tail coverage and adequacy pass under the rules above.
2. For each n in G, n<C is provisionally eligible only if **for every** full
   calibration request q and linked context u,
   V(u,q,n-prefix-of-C) = V(u,q,C). This includes alternate candidates,
   unknown/weak-reference and opaque tokens, not just one compatible hit.
   All paired direct n observations must also preserve V(u,q,C) and show no
   strict prefix disagreement. C is eligible only after step 1; it is not
   an automatic fallback for an inadequate ceiling.
3. Propose the smallest eligible n. If no shallower n proves preservation,
   retain C only when its independent deeper-tail audit passed. Cost can
   distinguish eligible lossless choices or motivate a new design; it cannot
   override demonstrated or unresolved value loss.
4. Owner freezes concrete final N/policy with all input/projection/probe/tail/
   witness hashes, coverage limits and rationale. **N remains UNSELECTED until
   this happens.** If useful evidence persists at T, the sole current result
   is INSUFFICIENT CALIBRATION DEPTH, not N=T.
5. If N!=C, execute a separately authorized complete direct-N run, then require
   V(u,q,C) subset V(u,q,N-direct) for every request/context before acceptance.
   Any loss rejects that final candidate and returns to owner-reviewed
   DEVELOPMENT calibration; no automatic size increase or rank repair.
   If N=C, validate reuse of exact raw observations and current approved
   projection, with no required second complete network workload.

No empirical percentage loss tolerance, final score, winner, usability gate,
or confidence threshold is introduced. No ability to prove independent support
does not imply no utility: unknown-reference strata retain potential tokens
and can force deeper retention or an insufficient-depth stop. A different
witness model, per-stratum depth or relaxed tolerance requires a new reviewed
pre-outcome calibration protocol; no HOLDOUT tuning.

## Sanitized reporting and disclosure

One manifest-bound summary object has separate scientific and operational
sections: input/planned/attempted/completed/unprocessed requests; both success
states; attempts/retries/final failures by closed HTTP/error category; count and
rank histograms; layer/source and descriptive confidence/match_type bins;
country/mode and capability/script/completeness diagnostics; convergence;
marginal/witness curves at C and T; stratum audit coverage and adequacy status; selected N rationale; deployment stability; bytes/compression/
storage; latency/throughput; checkpoint adoption and integrity/publication checks.
Confidence bins: null, [0,.25), [.25,.5), [.5,.75), [.75,1], with explicit
descriptive labels. Latency reports aggregate percentiles, no request traces.
Unknown metadata strings are counted in OTHER, never copied to reports.

Controlled analysis retains all fine strata. Portable output contains no
protected strings, URLs, labels, IDs, examples or raw bodies. Default portable
disclosure: global operational totals and mode totals, predeclared aggregate
histograms and strata with at least **20 distinct source rows**. Suppress cells
with 1..19 contributing rows and use complementary suppression/removal of
derived totals to prevent reconstruction; do not replace suppressed cells by
zero. This is a proposed conservative disclosure parameter, **not** a scientific
gain threshold. Freeze the exact table release plan at the pre-DEVELOPMENT owner gate. Suppress
unsafe cross-tabs entirely if independent tables permit differencing; approved
controlled owner review retains them so small-country concerns still govern N.
No free-form response-derived dimension labels or arbitrary error text.

All implementation validation, publication review, calibrated N and response
extraction/failure/retry/deployment rules must be frozen before any separately
authorized HOLDOUT final evaluation. Stage 12 acceptance does not itself
authorize HOLDOUT, production or Stage 13.

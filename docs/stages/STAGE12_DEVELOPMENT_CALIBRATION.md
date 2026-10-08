# Stage 12 — DEVELOPMENT top-N calibration and phase gates

Normative part of the [design proposal](STAGE12_PELIAS_TOPN_RETRIEVAL.md).
No measured retrieval, prefix-equivalence, service capacity or selected N is
claimed. HOLDOUT remains sealed. Stage 10 operating budget stays UNSELECTED.

## Design choice and finite grid

Propose calibration **Nmax=10** across **all 105,805** accepted semantic requests,
with primary policy grid **1, 3, 5, 10** and descriptive adjacent-rank curves for
every rank 1..10. This is a bounded engineering experiment, not a scientifically
chosen final depth. One is the repository's current preference; 3/5 test small
alternative sets, and 10 doubles the upper small set while bounding DEVELOPMENT
at 1,058,050 candidate positions. Stage 11 explicitly anticipated these distinct
execution identities, but supplies no empirical reason to prefer one. No prior
project decision selected a different grid or a final N.

Use a global depth in v1; no opportunistic per-request depth, early stopping
on confidence, family pruning or reference-coverage-dependent depth. Only the
separately frozen paired-size diagnostic is a deterministic subset. Stage 12
does not resolve the Stage 10 family budget by using a smaller catalog.

At size=10, offline prefixes describe **the size=10 candidate list**. They do
not establish what a size=1/3/5 server request would return. Calibration
retrieval depth and final operational retrieval depth are separate declarations
in the artifact profile and owner freeze record. Every direct size request
has its own policy and complete execution identity.

## Future phases and minimum valid order

| Phase | Required work and explicit stop/gate |
|---|---|
| A — implementation | After owner design approval: implement the exact contracts, generated machine assets, synthetic fixtures and fault tests; independent implementation review; exact pushed SHA. No protected/network activity follows automatically. |
| B — deployment compatibility | After owner gate reconciliation and exact public-workload approval: operator manifest/immutable serving mechanism, public/synthetic probe below, frozen response/transport/identity evidence. Stop on unsupported contract or nondeterminism; review changes before protected inputs. |
| C — calibration workload freeze | Authorized scheduled preflight fully reopens Stage 11 and accepted upstream metadata, checks all request target sizes without emitting payloads, materializes the deterministic paired subset and controlled workload hashes. Owner approves exact catalog/subset/deployment/attempt/rate/storage budgets before network dispatch. |
| D — calibration retrieval | One authorized complete size=10 campaign, plus the bounded paired-size/repeat diagnostic. Reuse sealed successes across authorized resumes. Persist separate calibration artifacts, never label a partial campaign final. |
| E — analysis and owner freeze | Controlled offline diagnostics, stratified marginal-value report, independent calibration review; owner chooses N or rejects sufficiency. No HOLDOUT or final scoring. Freeze explicit retrieval policy ID and deployment binding. |
| F — final DEVELOPMENT | If N=10 and all reuse conditions hold, register the same complete immutable response evidence for final use without another network run. Otherwise authorize one complete final campaign at frozen N with new policy/execution identities. Validate and report all 105,805 outcomes. |
| G — independent review and acceptance | Fresh review of complete final evidence, raw reconstruction, identity continuity, map-back and publication. Owner accepts/rejects Stage 12. Stop before Stage 13. |

The full size=10 calibration is **one network workload**, possibly resumed in
separate authorized jobs. If final N differs, **a second complete DEVELOPMENT
network workload is required**, even when probes show prefix agreement. Never
relabel a size=10 prefix as a size=3 execution. The paired-size probe adds
explicitly budgeted small diagnostic calls; it is not a hidden replacement for
the second full workload.

If final N=10, reuse requires exact input/policy/materialization/extraction/
implementation/deployment/index bindings, complete valid responses, reviewed
calibration and no drift/ambiguity. Preserve the original calibration artifact;
the final registration references or verified-copies its complete immutable
evidence and binds the owner freeze. No in-place mutation or recapture. If
identity/executable/contract changed, automatic reuse is forbidden and a new
reviewed campaign is required. Different deployment means recalibration, not
only replaying the previously selected N without review.

## Synthetic and public probe

Offline synthetic fixtures establish exact encoder/serializer vectors,
Unicode/plus/LF/leading-zero round trips, null-vs-empty rules, unsupported
structured country/region rejection, raw slices, duplicate features, all
failure states, Retry-After bounds, secret canaries, pool limits, collision
handling and local-loss/resume/fsync/publication races. A local mock server
tests timeout, malformed JSON, TLS/DNS error classification and overload;
do not intentionally overload live SAFE to test a breaker.

After separate authority, freeze **64 public/synthetic query cases**, 32 per
mode, independently of DEVELOPMENT strings. Include Latin, non-Latin, mixed
and combining-mark text; leading-zero postcode; percent/plus/ampersand/equals;
known public ambiguous locations; sparse/no-result-intended inputs (not promised
zero); supported boundary codes and both structured postal/locality forms.
All case text is public or invented and provenance-reviewed before dispatch.
Use only the approved SAFE origin. No third-party geocoder comparison.

Run the 64 cases at four sizes twice: **512 ordinary requests maximum before
bounded retries**. Freeze case order by ID, size order [1,3,5,10] in pass one
and [10,5,3,1] in pass two to expose temporal effects. Reserve at most **16
additional calls** for request-length/endpoint/authentication/identity
compatibility, described exactly in the authorized workload; do not invent
extra calls during the probe. Initial concurrency 2 and 1 request/second.
Never print real keys during valid/missing-key tests. Use a synthetic invalid
key only if the operator explicitly includes that negative test in the budget.

Establish signed manifest acquisition, index/content identity, serving lease/
attestation, endpoint and country support, actual auth, exact decoded request
values, JSON/field types, GET length limits and no-injection/no-secret logging.
Operator configuration and controlled local capture establish limits that
queries alone cannot prove. No numeric transport limit is fabricated here.
Freeze the concrete limit before Phase C. Absence of evidence is a blocker.

Compare repeated **same-size** outputs separately from **cross-size** prefixes.
Use ordered full feature structural equality: compare every key/value in each
feature, retaining array order, string bytes and exact JSON numeric token
spelling; ignore JSON object key order/whitespace only. Do not compare response
timestamps or request echo size as candidate content. Do not ignore confidence,
match_type, labels, coordinates or unknown feature fields to manufacture
agreement. Raw bytes and raw hashes stay independently authoritative.
A new unknown field has no extracted meaning but still participates in this
conservative equivalence test.

Record exact-length/count/order equality at k and within-size repeatability,
plus component differences for diagnosis. Zero observed disagreement is
**tested-case agreement**, not universal proof. Any same-size disagreement
blocks protected execution until the serving determinism issue is resolved.
Any cross-size disagreement disables treating offline prefixes as measurements
of direct smaller policies, without invalidating size=10 observations.
Exhaustive proof is not claimed from 64 public cases. Even proven prefix
behavior would not merge different scientific execution identities.

## Bounded paired DEVELOPMENT diagnostic

Public cases may miss workload-specific behavior. Preselect at most **400
distinct semantic IDs**, without inspecting responses, before calibration:

1. For each semantic ID, derive its boundary country/mode and the **set** of
   upstream occurrence tuples (script class, Stage 9 capability mask, source
   completeness mask). Never choose one representative context as truth.
2. Script class uses the already pinned Unicode 16 script resource on accepted
   source representation line-body text: ignore Common/Inherited for the class;
   no remaining script=COMMON_ONLY, one script=that script, otherwise MIXED.
   Classification creates diagnostic labels only; no query modification.
3. Capability mask is the exact enabled/full-vs-partial/positive/negative
   authority vector for the accepted Stage 9 country/question/component
   registry. Missing expected registry rows are integrity failures, not weak
   capability. Retain per-reference masks; do not fabricate a scalar quality.
4. Completeness is four booleans: nonempty accepted source representation
   line body, source postcode, source locality, source region. Empty means
   exact zero-length, no trimming or parser-derived fill. Accepted Stage 8
   locators/Stage 10 context slots determine the fields.
5. A request's stratum is (country, mode, sorted distinct occurrence tuple
   set). Sort strata by H("SAFE:stage12-calibration-stratum:v1", framed tuple).
   Inside each stratum sort requests by H("SAFE:stage12-calibration-sample:v1",
   [protocol version, query_semantic_id]), full ID as final tie-break.
6. Round-robin take one remaining request per ordered stratum until 400 or
   catalog exhaustion. Freeze the ordered ID list, all stratum populations,
   inclusion counts and workload digest before responses. If strata >400,
   report unrepresented strata; do not claim complete paired coverage.

This is an engineering diagnostic, not a random accuracy sample. No sampling
confidence interval or population prefix-equivalence claim. Full size=10
calibration supplies every-country evidence curves. Stage 10 family lineage
is preserved for incidence diagnostics, not a sampler that suppresses families.

For these selected requests, retain the first size=10 calibration observation,
then execute sizes 1/3/5 once and all four sizes once again under the same
deployment: **at most 2,800 supplemental requests**, plus the 400 already in
the complete run. Freeze round order as in the public probe. Thus each size
has two observations; audit-only repeat observations use separate diagnostic
campaigns, never two selected successes in one final relation.

The calibration workload ceiling is 108,605 ordinary calls (105,805 complete
size=10 plus 2,800 supplemental), at most 543,025 dispatched attempts under
five-attempt bounds, with circuit breakers able to stop much earlier. The public
probe ceiling is 528 ordinary calls / 2,640 attempts. A separately authorized
complete final run adds at most 105,805 ordinary calls / 529,025 attempts.
Identity/control checks have a separate explicitly bounded lease-duration
budget in workload approval and consume the same rate/concurrency pool; expiry
stops the campaign. These are ceilings, not instructions to consume retries.

Compare direct size policies and offline prefixes by the same strict rule.
Report policy-dependent candidate additions **and losses**; non-nested outputs
need not give monotone curves. If repeats at the same size disagree, block
final policy freeze pending investigation. If cross-size differs, direct paired
results remain separate evidence; full prefixes are explicitly labeled
size=10-retention diagnostics. V1 then permits selecting the empirically
observed global maximum 10 if defensible, or stopping for a separately reviewed
expanded direct-policy calibration. It does **not** select a smaller policy
from invalid prefix equivalence. No automatic four-full-workload expansion.

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

## Marginal metrics and strata

For each channel c and source context u, let A_c(u,k) mean at least one of the
first k size=10 features is compatible with that channel's evaluable evidence.
Let E_c(u) mark evaluability from the frozen source/reference prerequisites.
Count A over E, and count NOT_EVALUABLE separately. At each adjacent rank and
primary grid transition k->l report:

- newly covered contexts where E is true, A(u,k)=false and A(u,l)=true;
- newly observed distinct compatible candidates, even where A was already true;
- contexts whose only observed compatible features are below k;
- novel candidates with missing/unevaluable evidence, not coded incompatible;
- new layer/source/feature/GID diversity, repeated positions and coarse-layer
  incidence, raw bytes and incremental retained candidate rows;
- candidate-set additions/losses for actual direct-policy comparisons,
  separately from nested prefix gains.

Count once per context/channel (and once per source row in a separately
deduplicated source-grain view), never once per parser component or family
label. Request-grain workload metrics use unique semantic IDs. Use full join
keys including hypothesis/context for Stage 10 family membership; families
are overlapping incidence categories whose sums need not equal population.
No denominators mixed across those grains.

Stratify country, script, FULL_TEXT/STRUCTURED, exact reference capability and
source completeness, plus STANDARD/NATIVE and family incidence when informative.
Primary mode-request totals are disjoint. Context/family/script incidence for
shared requests is explicitly overlapping; never assign arbitrary representative
labels. Provide predeclared one-dimensional strata and country x mode and
country x capability tables; keep full joint diagnostics controlled.
Absent references produce unknown tail value, not apparently worse candidates.
Present numerators/denominators and capability coverage next to every curve.

Pelias confidence/match_type distributions and confidence by rank are
**descriptive only**; no selection rule depends on them. Retrieval success rate
and zero-result rate are not geocoding accuracy or recall.

## Explicit final N owner-review criterion

No percentage tolerance is invented. Propose a conservative **zero observed
evidence-loss screen** on the full size=10 calibration:

1. Complete scientific/technical validity, deterministic same-size probes,
   deployment stability and all strata/denominators must pass first.
2. A smaller grid N is eligible only with zero tested prefix disagreements
   and zero marginal loss relative to Nmax in **every** evaluable evidence
   channel/stratum, including additional compatible alternatives, not just
   existence of one candidate.
3. No novel unassessed tail feature may be dismissed because reference coverage
   is weak. For this screen an unassessed feature is any feature with a missing
   diagnostic channel, and its full structural novelty is retained as potential
   information. Unknown tail contribution prevents certifying a smaller N.
4. Among eligible depths, propose the smallest, with measured row/body/storage/
   latency cost and Stage 13 evidence sufficiency explicitly reviewed. Tested
   prefix agreement is still not proof of all direct size responses; choosing
   smaller N requires the final complete direct-size run and a reported
   comparison against calibration before owner acceptance.
5. If no smaller depth qualifies, propose **10 as the maximum actually
   evaluated**, only if the owner accepts the observed marginal curve and
   finite-depth limitation in every material country/script/capability stratum.
   Never label an unsaturated tail saturated. If rank 10 still contributes
   unresolved value the owner cannot accept, STOP for a revised finite
   calibration design, possibly a larger Nmax; no automatic extension.

This selects a retrieval budget, not accuracy or global recall. The zero-loss
screen is intentionally conservative in the absence of independent truth and
an approved loss tolerance. The full DEVELOPMENT prefix census has no sampling
uncertainty for that observed list, but does not establish generalization,
unobserved deeper candidates or smaller-size population equivalence.
No ad hoc threshold relaxation after seeing inconvenient strata. An alternative
bounded stratified N or tolerance requires a new owner-reviewed protocol,
deterministic pre-HOLDOUT policy and identity; it is not enabled by v1.

The signed owner freeze record binds exact input/deployment/calibration/
protocol hashes, primary/adjacent curves, probe disagreement and coverage,
selected concrete N/policy ID, cost evidence, remaining uncertainty and explicit
accept/reject rationale. **Final N remains UNSELECTED in this design.**
If final smaller-size behavior reveals unexpected losses, preserve that
candidate, reject acceptance and return to DEVELOPMENT policy review; no
silent switch to 10, reranking or publication under the old policy.

## Sanitized reporting and disclosure

One manifest-bound summary object has separate scientific and operational
sections: input/planned/attempted/completed/unprocessed requests; both success
states; attempts/retries/final failures by closed HTTP/error category; count and
rank histograms; layer/source and descriptive confidence/match_type bins;
country/mode and capability/script/completeness diagnostics; convergence;
marginal curves; selected N rationale; deployment stability; bytes/compression/
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
gain threshold. Freeze the exact table release plan before Phase D. Suppress
unsafe cross-tabs entirely if independent tables permit differencing; approved
controlled owner review retains them so small-country concerns still govern N.
No free-form response-derived dimension labels or arbitrary error text.

All implementation validation, publication review, calibrated N and response
extraction/failure/retry/deployment rules must be frozen before any separately
authorized HOLDOUT final evaluation. Stage 12 acceptance does not itself
authorize HOLDOUT, production or Stage 13.

# Stage 12 — bounded design review and owner decisions

**OWNER REVIEW INCORPORATED — READY FOR OWNER FREEZE; NOT FROZEN.**
This is the author's one complete bounded review of the owner-directed revision
of design **54d52e01ed906c41b48c5dac945a76abd9f66846**, on 2026-10-09.
The owner approved the architecture in principle and supplied 24 directions;
their complete disposition is below. The earlier proposal/review remains in
Git history. No independent live/implementation review, sub-agent, deployment
test, protected inspection or scientific acceptance is claimed.

**Unresolved design defects: 0. Unresolved scientific owner choices: 0.**
Final design freeze is still the owner's next action; it is not performed by
this branch commit. Empirical/operational parameters have explicit future gates.

## Complete design-defect ledger

DC = [data contract](STAGE12_DATA_CONTRACT.md);
EC = [execution contract](STAGE12_EXECUTION_CONTRACT.md);
CAL = [calibration protocol](STAGE12_DEVELOPMENT_CALIBRATION.md);
SCOPE = [scope/publication](STAGE12_PELIAS_TOPN_RETRIEVAL.md).

| ID | Challenge | Resolved design disposition |
|---|---|---|
| L01 | Mutable hostname mistaken for identity | EC: logical deployment, complete code/config/backend/index/data view fingerprint; approved host is transport routing only. |
| L02 | Alias/UUID drift or writes inside same index | EC: exact alias filters/routing/backing set, content snapshot inventory plus write/alias/maintenance exclusion; UUID alone rejected. |
| L03 | Hidden layer/source/language defaults | DC/EC: preserve omission; bind actual built-in behavior; reject injected defaults and unknown no-override language behavior. |
| L04 | Secret in IDs, logs or config hashes | DC/EC: runtime-only key, no secret-derived hash, reviewed secret-free configuration projection, safe errors and client/server log controls. |
| L05 | Arbitrary final top-N | CAL: explicit finite experiment, complete DEVELOPMENT curves, conservative zero-loss smaller-depth screen and owner rationale; final N UNSELECTED; a passing deeper audit is mandatory. |
| L06 | Assume size=Nmax prefixes equal size=k | CAL: repeated public and deterministic paired DEVELOPMENT direct-size probes; equality scoped to tested cases; different IDs always. |
| L07 | Confuse calibration and final retrieval | CAL/SCOPE: distinct publication roles, complete second workload if N differs; C reuse only after passing tail audit and exact-binding owner freeze; offline projection can change separately. |
| L08 | Network failure encoded as zero | DC/EC: zero requires valid successful empty features; failures have null candidate_count and no candidate rows; complete malformed 2xx payload is retained for controlled audit. |
| L09 | Infinite or unsafe retry | EC: five cumulative attempts, closed retry taxonomy, bounded deterministic waits/Retry-After, no library retry or automatic job resubmission. |
| L10 | Concurrency overload | EC: initial 2 total/1 request per second, hard 4 total, pool/queue bounds, shared limiter, cooldown and non-auto-recovering circuit breaker. |
| L11 | Retries duplicate scientific executions | DC/EC: separate audit attempt IDs, success receipt selection and exact durable adoption; uncertain dispatch consumes budget; no success retry. |
| L12 | Silent returned-feature dedup | DC: every array position retained even identical GID/geometry/bytes; diagnostic distinct counts never alter relation. |
| L13 | Response order lost | DC: 1-based array ordinal, exact raw bytes and position slices, contiguous ranks; no sort by confidence/GID. |
| L14 | Invalid-feature filtering compresses ranks | DC: entire response fails validation; no partial feature salvage or reindex. |
| L15 | Confidence becomes truth | DC/CAL: nullable supporting metadata only; no confidence threshold, score, weights or accuracy claim. |
| L16 | match_type=exact becomes correctness | DC/SCOPE: descriptive metadata, never correct-address/rooftop label. |
| L17 | Point becomes rooftop | DC/SCOPE: geometry type and layer preserved, no precision inference; Stage 13/later granularity owns decisions. |
| L18 | Coordinate order/CRS/numeric ambiguity | DC: longitude/latitude WGS84/CRS84, finite float64 ranges, exact raw tokens, no rounding; unsupported geometry fails response. |
| L19 | Parser discards future Stage 13 evidence | DC: both complete raw JSON bytes and exact extracted relation; unknown fields remain reconstructible; new extraction versioned. |
| L20 | Raw response not auditable | DC/EC: SHA-256 exact entity bytes before parser/compression, exact feature slices, independent frames and reopen checks. |
| L21 | Mid-run change/revert evades start/end check | EC: optional per-response generation; realistic minimum immutable backing data, verified pre/periodic/post content, operator exclusion/change records and interval closure. |
| L22 | Resume crosses deployment or contract | EC: full binding/executable/input/receipt/adoption checks plus generation continuity; drift quarantines campaign, no salvage. |
| L23 | Stage 11 map-back lost | SCOPE/DC: exact semantic key totality and 142,677 upstream edges; context-qualified family joins and source-grain left joins. |
| L24 | Convergence counted as independent votes | CAL: preserve shared source/parser/query/import ancestry, separate diagnostic incidence; no additive confidence. |
| L25 | Weak-reference countries bias N | CAL: exact capability/evaluability strata, unknown tail cannot be discarded, small-country evidence retained in controlled review. |
| L26 | Protected query/response/credential leakage | EC/SCOPE/CAL: approved SAFE-only route, controlled raw/rows/hashes, malformed 2xx retained privately with secret guards, no-secret echo gate and sanitized reports. |
| L27 | Production memory/storage explosion | EC/SCOPE: byte-bounded batches/queue/response/parser, independent compressed frames, external joins/sorts, quota planning, production capacity explicitly unproven. |
| L28 | Missing executions still publish | SCOPE/DC: exact all-105,805 key-set equality, zero unresolved technical/contract/identity failures, full reopen before and after exclusive seal. |
| L29 | Stage 13 scoring leaks into diagnostics | CAL: separate existence/diversity/compatibility channels only; no scores, hard gates, rank changes, winner or Stage 9 re-evaluation on new candidates. |
| L30 | HOLDOUT tunes top-N | CAL/SCOPE: DEVELOPMENT-only calibration and pre-HOLDOUT freeze of policy, schema, retries, evidence and deployment rules; no HOLDOUT access. |
| L31 | Legacy Stage 19 gate silently waived | SCOPE/D092: history proves stale deduplication/QA numbering; active guidance corrected to Stage 11 acceptance and Stage 12 freeze/phase/workload gates; no calls authorized. |
| L32 | X-API-Key or live schema falsely called verified | EC: repository absence stated; operator attestation/public compatibility gate required; alternative auth requires reviewed contract amendment. |
| L33 | Structured country substituted for boundary | DC: country/region remain upstream null and omitted; exact boundary.country is separate, no conversion/inference. |
| L34 | Giant input silently truncated/skipped | DC/EC: actual GET limits frozen before DEVELOPMENT; overlimit preserves map and blocks complete publication; no POST/fallback rewrite. |
| L35 | Exactly-once network guarantee impossible after crash | EC: explicit UNKNOWN_DELIVERY and bounded repeat, durable at-most-one scientific selection; no false exactly-once promise. |
| L36 | Signed manifest proves mutable server by assertion | EC: content hash excludes signature/key; authenticity is separate. Require approved drift controls, immutable content and repeatability, not invented server attestation. |
| L37 | Repeat size probes interpreted as illegal duplicate final rows | CAL/DC: explicitly authorized separate diagnostic campaigns/artifacts, one selected observation per execution per artifact, no duplicate final execution. |
| L38 | Metadata hash/canonicalization cycle or operational ID pollution | DC/SCOPE: named typed domains, separate semantic and audit inventories, design hash outside execution ID, no self-hash/Git-cycle. |
| L39 | Small-cell/differencing disclosure in country/script tables | CAL: controlled complete diagnostics, minimum-20 source-row portable rule, complementary suppression and predeclared release plan. |
| L40 | New stage reuses wrong registration namespace or ambiguous fsync success | SCOPE/EC: Stage 12 namespace/key/version, same-filesystem primitive checks, exact registration/seal/full reopen; ambiguity cannot be success. |

## Final owner-revision defect review

| ID | Challenge | Resolved disposition |
|---|---|---|
| F01 | Extraction contaminates network identity | DC: seven-field network ID excludes validation/extraction/schema. Dataset-level response_projection_id binds raw set plus validation/extraction/candidate schema. |
| F02 | Client Git/reporting SHA contaminates scientific ID | DC: removed implementation hash; exact Git/runtime stays campaign and projection provenance. Materialization descriptor contains rules, not code hashes. |
| F03 | Weakened checkpoint executable proof | EC: exact client SHA/runtime/operations still required for network adoption; offline replay is a separate authorized derivation. |
| F04 | Response hash depends on storage compression or ambiguous wire capture | DC: decoded, uncompressed application bytes delivered to parser before JSON; SHA-256 excludes transfer framing/content representation/at-rest compression. |
| F05 | N=10 treated as sufficient ceiling | CAL: distinguish N/C/T; T>max(C,10) bounded subset; observed tail value produces INSUFFICIENT CALIBRATION DEPTH. |
| F06 | Deep audit chosen/tuned after outcomes | CAL: public-capability gate freezes exact C/T/rules; deterministic coverage selection sealed before calls; no replacements or ad hoc depth growth. |
| F07 | Calibration becomes Stage 13 scoring | CAL: deterministic channel/claim/ancestry token sets, no weighted scores, winners, confidence thresholds or hard gates. |
| F08 | Weak references lose useful alternatives | CAL: absent/unknown evidence produces conservative potential tokens; novel unknown tail can stop calibration. |
| F09 | Signature/key rotation changes identity | DC/EC: canonical content hashes only; signatures/verification keys and receipts are authenticity audit. |
| F10 | Impossible per-response attestation prerequisite | EC: preferred mode if available; realistic CONTROLLED_CAMPAIGN minimum with operator and administrative evidence; mechanism chosen by public probe gate. |
| F11 | Malformed candidate filtered or raw evidence discarded | DC/EC: whole response CONTRACT_FAILURE, complete privacy-checked payload retained, zero candidates; no rank compression. |
| F12 | Rank/duplicate changes | DC: 1-based exact array order; duplicate-looking features stay; calibration sets never modify rows. |
| F13 | Multi-job continuation changes campaign | EC: stable campaign_id and cumulative budget across authorized sequential jobs; distinct segment receipts; 29.39-hour base admission cost explicit. |
| F14 | Retry/concurrency changes scientific IDs | DC/EC: operations outside network ID; five proposed attempts bounded and owner-reviewed after public probing; exact ops still bound for adoption. |
| F15 | Stale Stage 19 gate persists | SCOPE/D092: original history inspected; active AGENTS/overview/pipeline/execution/privacy/workflow reconciled, frozen historical records preserved. |
| F16 | Offline replay mutates accepted outcomes or mislabels a new HTTP call | DC: new immutable dataset/projection and explicit reclassification provenance; unchanged original raw/attempts; no automatic call. |
| F17 | Sample coverage silently excludes rare cells or implies global saturation | CAL: mandatory nonempty stratum quotas, bounded cap fails closed, exact coverage report; passing audit is sampled evidence, never global recall. |

Together L01–L40 and F01–F17 comprise **57 resolved design checks**.
This review challenges specification consistency; it does not assert 57
implementation tests or verified deployment capabilities.

## All 24 owner directions

| OD | Owner direction | Final disposition |
|---|---|---|
| 01 | Separate scientific identity and code/extraction | Seven-field request ID; client/campaign provenance and dataset-level response_projection_id separate. |
| 02 | Raw-response semantics | Exact decoded uncompressed application payload before JSON; sanitized header/status/length audit; storage compression excluded. |
| 03 | Offline replay | Deterministic raw + validation/extraction/schema -> new immutable projection; no required new Pelias call. |
| 04 | Tail beyond 10 | Bounded <=2,000-request stratified audit at T>max(C,10), chosen only after public capability evidence; no complete huge-depth workload. |
| 05 | Final N unselected | N=UNSELECTED until full calibration and deeper audit pass; persistent tail -> INSUFFICIENT CALIBRATION DEPTH. |
| 06 | Executable freeze criterion | Exact per-context potential token set preservation, unknown-tail protection, no cost override of loss; complete final direct-policy verification. |
| 07 | Dependencies | Claim/ancestry grouping coalesces correlated restatements; source agreement not independent, disjoint lineage requires proof; no votes. |
| 08 | Prefix equivalence | Policy and execution IDs remain distinct; N!=C requires second complete direct-N workload even with perfect probe agreement. |
| 09 | Content vs signatures | Deployment identity hashes content, never signing key/signature; authenticity independently required. |
| 10 | Realistic drift minimum | Public probe chooses per-response generation if supported or controlled campaign verification/exclusion/change evidence; unknown feasibility blocks calls. |
| 11 | Aliases | Exact alias-to-immutable UUID/content mapping retained; alias mutation is drift, alias name is not data identity. |
| 12 | Omitted policies | Language/layers/sources remain absent on request; effective server environment is fingerprinted without injecting parameters. |
| 13 | Invalid features | Contract failure of whole response, exact raw audit retained under privacy guards, no filtered list. |
| 14 | Duplicate features | All positions remain; no GID/coordinate/label/source-ID consolidation. |
| 15 | Zero/failure | Six approved states distinguished; accepted final executions all valid successes, zero terminal technical/contract/identity failures and no missing keys. |
| 16 | Retries | Five proposed cumulative attempts, 10/30/60-second deadlines, bounded waits; public evidence/owner may lower ceiling before protected use, operations outside IDs. |
| 17 | Concurrency | Initial 1 request/second, two connections, hard four; increases only from approved public service evidence, breakers mandatory. |
| 18 | Long-run practicality | Expected multiple authorized jobs; stable campaign/client/ops/budgets and sealed durable resume; no walltime-driven concurrency increase. |
| 19 | Stage 19 | Proven stale old deduplication/final-QA architecture; active rules corrected by owner direction, not deferred as unexplained dependency. |
| 20 | Minimal relation model | Four relations retained; campaign/projection metadata objects supply additional bindings without row-level tables. |
| 21 | Stage 13 boundary | Raw provenance, ordered candidate fields/outcomes, upstream lineage and exact policy/deployment/index handed off; no score/selection. |
| 22 | State machine | Freeze -> implementation -> public probe -> owner C/T/deployment/ops gate -> preflight/workload approval -> calibration/audit -> analysis -> N freeze -> reuse/direct-N -> independent review -> acceptance. |
| 23 | Public probe limits | Technical safety/schema/identity/prefix examples only; no public-quality-based scientific N. |
| 24 | Complete final review | L01–L40 rechecked and F01–F17 resolved; empirical parameters remain explicitly gated, no implementation or live test. |

## Minimal model restated

All PKs are scoped by an immutable artifact; no multi-projection mixing.

| Relation | Grain / PK | Foreign keys | Classification and purpose |
|---|---|---|---|
| retrieval_policy | One concrete policy / retrieval_policy_id | None | Nonsecret scientific policy; portable after review |
| request_execution | One network identity and contract-relative terminal observation / request_execution_id | Stage 11 semantic request, local policy, manifest-bound deployment/index, terminal attempt | Protected scientific retrieval/outcome plus physical/audit locators |
| request_attempt | One dispatched/interrupted attempt / attempt_id; unique campaign/execution/ordinal | Execution and manifest-bound campaign/identity receipts | Protected audit provenance; original attempt classifications immutable |
| request_candidate | One feature at returned rank / (request_execution_id, rank), scoped by response_projection_id | Successful execution and its exact raw response | Protected scientific candidate evidence; no winner |

Manifest objects bind campaign provenance, raw capture set and one response
projection; no separate campaign/projection/response relation is needed.
Schemas, fields and nullability are normative in DC.

## Gated future parameters and owner freeze boundary

Unresolved scientific owner decisions in this revision: **none**. Overall
architecture remains approved in principle; final owner freeze/merge is not
performed. The following intentionally unmeasured parameters block their
dependent phases, without leaving the decision process ambiguous:

- **Final N and policy ID: UNSELECTED**, until DEVELOPMENT witness analysis and
  deeper-tail adequacy pass and the owner freezes them.
- **Exact protected C and T: UNSELECTED_PENDING_PUBLIC_CAPABILITY_REVIEW**;
  C=10 is planning only, T>max(C,10) mandatory. Owner freezes exact values and
  subset/witness rules before protected calls; no protected-outcome selection.
- **Concrete deployment/index/auth/observability mode: UNVERIFIED**; public probe
  and operator evidence establish canonical content and feasible drift controls.
- **Final operations/resource/control budgets and disclosure release plan:**
  frozen after public safety evidence and before protected workload approval.
  Initial rate/connections and hard ceilings remain the proposed bounds.
- **Exact controlled subset/workload fingerprints:** produced in the authorized
  offline preflight under already fixed rules, then approved before dispatch.

These are future evidence/authorization gates, not instructions to probe now.
Failure to establish identity, adequate depth/coverage, privacy or resource
safety stops the workflow; no maximum-tested-depth or hidden-default fallback.

## Documentation validation and unchanged boundary

This revision is documentation only, including owner-directed correction of
active governance's stale Stage 19 numbering. Verify fetch/status/ancestry,
unchanged accepted Stage 11 manifest/tag bindings, complete Markdown scope,
local links/anchors, relation/identity consistency and git diff --check.
No scientific/unit tests or protected/remote artifact checks are claimed.
Before normal push, inspect upstream divergence; after push verify clean branch
and remote SHA, unchanged main and no merge/tag.

Local validation passed: **15 Markdown-only files**, **228 local links / 26
anchors**, complete L01–L40/F01–F17 and OD01–OD24 tables, balanced schema fences,
exact accepted baseline/tag/ancestry and tracked sanitized Stage 11 manifest/
registration bindings, seven-field network identity exclusions, unchanged
frozen science and whitespace checks. No untracked/generated artifact is
included. These are documentation checks, not implementation test results.

Stage 0–11 code/contracts/fixtures/scientific assets/reports and frozen stage
records remain byte-identical. HOLDOUT sealed by accepted authority/non-access;
production untouched; Pelias NOT CALLED; no implementation, SLURM, protected
payload read or Stage 13 activity.

**NEXT: OWNER FREEZE OF STAGE 12 DESIGN.**

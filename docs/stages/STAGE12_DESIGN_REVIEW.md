# Stage 12 — bounded design review and owner decisions

Author's single complete bounded critical review of the five-document
[design package](STAGE12_PELIAS_TOPN_RETRIEVAL.md), begun 2026-10-08 and completed
2026-10-09. This is a design review, not a claim of independent review,
implementation tests, live deployment verification or scientific acceptance.
No sub-agent or external reviewer was used.

**Design defects unresolved: 0.** Every item below has a concrete contract
disposition. Future empirical facts and owner approvals are separately listed;
requiring them is fail-closed design, not pretending those facts were observed.
The exact proposal freeze is the design branch commit reported to the owner.

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
| L05 | Arbitrary final top-N | CAL: explicit finite experiment, complete DEVELOPMENT curves, conservative zero-loss smaller-depth screen and owner rationale; final N UNSELECTED. |
| L06 | Assume size=Nmax prefixes equal size=k | CAL: repeated public and deterministic paired DEVELOPMENT direct-size probes; equality scoped to tested cases; different IDs always. |
| L07 | Confuse calibration and final retrieval | CAL/SCOPE: distinct publication roles, complete second workload if N differs; Nmax reuse only after exact-binding owner freeze. |
| L08 | Network failure encoded as zero | DC/EC: zero requires valid successful empty features; failures have null candidate_count and no response/candidates. |
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
| L21 | Mid-run change/revert evades start/end check | EC: immutable serving generation, enforced maintenance lease, monotonic event counter, per-response attestation and periodic/start/end checks. |
| L22 | Resume crosses deployment or contract | EC: full binding/executable/input/receipt/adoption checks plus generation continuity; drift quarantines campaign, no salvage. |
| L23 | Stage 11 map-back lost | SCOPE/DC: exact semantic key totality and 142,677 upstream edges; context-qualified family joins and source-grain left joins. |
| L24 | Convergence counted as independent votes | CAL: preserve shared source/parser/query/import ancestry, separate diagnostic incidence; no additive confidence. |
| L25 | Weak-reference countries bias N | CAL: exact capability/evaluability strata, unknown tail cannot be discarded, small-country evidence retained in controlled review. |
| L26 | Protected query/response/credential leakage | EC/SCOPE/CAL: approved SAFE-only route, controlled raw/rows/hashes, no arbitrary error bodies, no-secret echo gate and sanitized reports. |
| L27 | Production memory/storage explosion | EC/SCOPE: byte-bounded batches/queue/response/parser, independent compressed frames, external joins/sorts, quota planning, production capacity explicitly unproven. |
| L28 | Missing executions still publish | SCOPE/DC: exact all-105,805 key-set equality, zero unresolved technical/contract/identity failures, full reopen before and after exclusive seal. |
| L29 | Stage 13 scoring leaks into diagnostics | CAL: separate existence/diversity/compatibility channels only; no scores, hard gates, rank changes, winner or Stage 9 re-evaluation on new candidates. |
| L30 | HOLDOUT tunes top-N | CAL/SCOPE: DEVELOPMENT-only calibration and pre-HOLDOUT freeze of policy, schema, retries, evidence and deployment rules; no HOLDOUT access. |
| L31 | Legacy Stage 19 gate silently waived | SCOPE/CAL: explicit proposed reconciliation is still pending; even public probe needs owner gate/workload authorization. |
| L32 | X-API-Key or live schema falsely called verified | EC: repository absence stated; operator attestation/public compatibility gate required; alternative auth requires reviewed contract amendment. |
| L33 | Structured country substituted for boundary | DC: country/region remain upstream null and omitted; exact boundary.country is separate, no conversion/inference. |
| L34 | Giant input silently truncated/skipped | DC/EC: actual GET limits frozen before DEVELOPMENT; overlimit preserves map and blocks complete publication; no POST/fallback rewrite. |
| L35 | Exactly-once network guarantee impossible after crash | EC: explicit UNKNOWN_DELIVERY and bounded repeat, durable at-most-one scientific selection; no false exactly-once promise. |
| L36 | Signed manifest proves mutable server by assertion | EC: signature authenticates operator only; require enforcement and actual-backend attestation, replica/tie behavior and snapshot evidence. |
| L37 | Repeat size probes interpreted as illegal duplicate final rows | CAL/DC: explicitly authorized separate diagnostic campaigns/artifacts, one selected observation per execution per artifact, no duplicate final execution. |
| L38 | Metadata hash/canonicalization cycle or operational ID pollution | DC/SCOPE: named typed domains, separate semantic and audit inventories, design hash outside execution ID, no self-hash/Git-cycle. |
| L39 | Small-cell/differencing disclosure in country/script tables | CAL: controlled complete diagnostics, minimum-20 source-row portable rule, complementary suppression and predeclared release plan. |
| L40 | New stage reuses wrong registration namespace or ambiguous fsync success | SCOPE/EC: Stage 12 namespace/key/version, same-filesystem primitive checks, exact registration/seal/full reopen; ambiguity cannot be success. |

The bounded review additionally checked consistency across documents: no policy
purpose in scientific ID; full-body bytes distinguished from structural
prefix comparisons; response uncertainty separate from zero; runtime secret
never in receipts; retry ceilings persist across resume; all returned layers
survive; cohort sampling cannot replace full execution; final reuse never
changes a raw response. Inspection led to the explicit required no-secret-echo,
change-and-revert counter, direct-policy loss comparison and uncertain-delivery
rules, which are incorporated in the proposal.

## Explicit owner decisions surfaced

All decisions below have a concrete proposed disposition for owner review.
They are not accepted merely because this ledger is resolved.

| OD | Decision | Proposed disposition |
|---|---|---|
| 01 | Relation set/grains | Four: retrieval_policy per policy; request_execution per complete execution and chosen response/outcome; request_attempt per dispatch; request_candidate per execution x rank. One aggregate object and manifest-bound configuration objects, no duplicated upstream lineage. |
| 02 | Execution identity | Full SHA-256 named typed domain over semantic ID, policy, materialization/extraction/result-behavior implementation and deployment/index/effective configuration IDs. |
| 03 | Retrieval policy ID | Full SHA-256 of version, positive explicit result_limit, ALL_RETURNED_IN_ORDER and empty result-options list; operations/purpose excluded. |
| 04 | Deployment fingerprint | Logical deployment/data view, exact applications/dependencies and result config/routing plus index/effective behavior objects. No hostname-only or attribution-only identity. |
| 05 | Index/data identity | Operator-signed immutable snapshot/build/content inventory, alias/UUID/mappings/import/auxiliary data bindings and enforced frozen serving generation. |
| 06 | Effective omitted settings | Actual no-filter layer/source behavior and no-override language resolver/fallback/name data bound; injected semantic defaults prohibited. |
| 07 | Exact transport materialization | GET to accepted paired path; exact scalar copy, separate boundary.country, explicit size; null omitted; UTF-8 RFC3986 encoding and sorted unique names. |
| 08 | Authentication | Proposed runtime X-API-Key over approved HTTPS; nonempty, secret-free persistence/identity/logging; requires actual operator/probe verification. |
| 09 | Preservation | Exact successful raw body compressed at rest plus extracted relation; uncompressed byte hash and raw feature slice hashes. |
| 10 | Candidate fields | Exact ordered schema in DC: feature/source/layer identity, geometry, descriptive metadata and address/admin components, full raw recovery for additional fields. |
| 11 | Rank | 1-based exact response position, no filtering/dedup/reordering; malformed feature fails response. |
| 12 | Coordinates/geometry | Non-null 2D Point, lon/lat WGS84/CRS84 float64/legal ranges, no rounding or rooftop claim; other geometry requires new contract. |
| 13 | Valid zero/failure | Two success states; retryable/final technical, contract and deployment failures distinct; zero only valid empty response; no unresolved failures in final candidate. |
| 14 | Retry | Five cumulative attempts, 10/30/60-second connect/read/overall timeouts, deterministic 2/4/8/16-second backoff plus bounded hash spacing and Retry-After. |
| 15 | Rate/concurrency | Initial 2 total, 1 request/second; hard 4 total and 2 requests/second only after reviewed probe; pool/queue/circuit breaker global. |
| 16 | Checkpoint/resume | Durable begin/body/finish/inventory/seal; adopt exact fully reopened bindings across separately authorized jobs; unknown delivery counts, no reset. |
| 17 | Drift guard | Enforced maintenance lease, immutable generation, per-response attestation, event counter and periodic/start/end checks; whole-campaign quarantine on drift. |
| 18 | Calibration depth/grid | Complete DEVELOPMENT at engineering Nmax=10, primary grid 1/3/5/10 and adjacent rank curves; final N unselected. |
| 19 | Prefix-equivalence plan | 64 public/synthetic cases x 4 sizes x 2; deterministic at-most-400 DEVELOPMENT paired cases; distinguish tested agreement from universal proof. |
| 20 | Top-N evidence | Channel-specific compatible additions, existence, unknown tails, diversity and dependent convergence; country/script/mode/capability/completeness strata. |
| 21 | Final N freeze | Smallest zero-observed-loss eligible grid value with unknown-tail protection, direct-run validation and owner judgment; otherwise evaluated maximum or revised bounded calibration. |
| 22 | One or two full network workloads | One complete calibration workload; same immutable evidence usable if final N=10 and gates pass. N differs -> second complete direct-N workload. Supplemental probes budgeted separately. |
| 23 | Stage 13 handoff | Ordered evidence/raw/provenance and complete upstream map; no winner/scoring/gates; Stage 13 remains separate and unstarted. |
| 24 | Publication | Exclusive reservation, immutable validation, Stage 12 registration, exclusive _COMMITTED, full reopen; exact totality and no integrity ambiguity. |
| 25 | Privacy | Controlled Goethe/approved SAFE only, runtime secret and server/client log controls, owner-approved aggregate disclosure; HOLDOUT sealed. |
| 26 | Production scale | Streaming Arrow, external DuckDB/Polars, byte/queue bounds, compressed independently readable packs, split workspace and separate measured production capacity review. |

## Pending owner approvals and empirical freeze values

There is no unresolved competing architecture hidden behind this readiness
claim. The following approvals/values remain explicitly pending and execution
is blocked until the applicable phase supplies them:

1. Owner approval/freeze of this proposal and separate offline implementation
   authorization; no merge or acceptance tag has been performed here.
2. Explicit Stage 19/size=1 policy reconciliation and exact authorization for
   each public or protected network workload.
3. Concrete verified deployment/index/effective-default manifest, immutable
   serving/attestation mechanism, operator authority, actual auth/schema/echo
   compatibility and observed safe transport/resource limits.
4. Approval of the finite calibration/probe budgets and portable disclosure
   table plan; exact controlled subset/workload IDs are generated only in
   later authorized work.
5. Empirical final N and its full policy ID, selected **after** DEVELOPMENT
   evidence and before final acceptance/HOLDOUT; same-size determinism and
   tested prefix behavior remain unmeasured.

These are future phase gates, not permission to investigate them now. If a
deployment cannot satisfy identity or semantic omission constraints, this
design requires stopping or a new reviewed contract; no unknown binding is
accepted to make the run executable.

## Documentation validation and unchanged boundary

Before commit: validate local Markdown links/anchors in the changed files,
baseline/tag/ancestry and accepted portable manifest bindings; inspect the
complete diff and tracked/untracked inventory; require documentation-only
changes and git diff --check. No scientific/unit test run is needed for this
prose-only change. Before push: fetch and verify unchanged accepted main and
fast-forward-safe design-branch ancestry. After push: verify remote branch SHA,
clean local tree and main still at its accepted baseline.

Local documentation checks passed: documentation-only scope of eleven files,
complete L01–L40 and OD01–OD26 tables, local links/anchors and balanced schema
fences, accepted portable Stage 11 manifest/registration bindings, ancestry
and whitespace validation. Only repository Markdown was written. These checks
validate this proposal's packaging, not a future client's scientific behavior.

Stages 0–11 scientific code/contracts/fixtures/assets/reports and acceptance
records remain byte-identical. HOLDOUT sealed by accepted authority and
non-access; production untouched; Pelias NOT CALLED; no implementation, SLURM,
protected payload read or Stage 13 activity.

**NEXT: OWNER REVIEW OF STAGE 12 DESIGN.**

# Stage 12 — SAFE Pelias top-N retrieval design

## Status, scope and authority

**OWNER REVIEW INCORPORATED — READY FOR OWNER FREEZE; NOT FROZEN,
NOT IMPLEMENTED, NOT EXECUTED.** The owner approved the architecture in
principle and directed the 24 revisions recorded in the review ledger.
Previous design SHA: **54d52e01ed906c41b48c5dac945a76abd9f66846**.
This revision updates documentation on the same branch only; no acceptance
tag, freeze or main merge is performed. Stages 0–11 science/history remain
unchanged. Future empirical parameters have exact gates, not assumed values.

Stage 12 deterministically materializes accepted semantic requests, retrieves
ordered candidate evidence from one verified self-hosted SAFE deployment, and
uses DEVELOPMENT diagnostics to choose retrieval depth. It does not choose
an address, score candidates, apply usability/contradiction gates, consolidate
returned features, or establish geocoding accuracy. Stage 13 remains unstarted.

The five normative documents are:

1. This scope, baseline, publication and handoff record.
2. [Execution, materialization and response relation contract](STAGE12_DATA_CONTRACT.md).
3. [Deployment, transport, failures and restart contract](STAGE12_EXECUTION_CONTRACT.md).
4. [DEVELOPMENT calibration and future phase plan](STAGE12_DEVELOPMENT_CALIBRATION.md).
5. [Bounded critical review and owner decisions](STAGE12_DESIGN_REVIEW.md).

## Stage 19 and size-policy reconciliation

Repository history establishes **stale architecture numbering, not a typo and
not a genuine later-stage dependency**. Commit
bd8108c0b959c59ad02d2a3e82fb4c24418405af (2026-08-27) retained the Stage 19
geocoding gate in AGENTS.md. Commit
7a99c047b22a35a7144032eb8bad6b2eac067497 (2026-09-01), D032, introduced the compact
8–14 architecture and explicitly labeled old Stage 19 “Query deduplication and
final QA” as legacy/unstarted, temporarily retaining the gate pending deliberate
reconciliation. D017 already identified size=1 as a historical preference
prospectively superseded by top-N retention. Accepted Stage 11 now provides
semantic deduplication/QA/map-back; Stage 12 adds executable request, deployment,
privacy and exact-workload QA. Stage 13 remains downstream of retrieval.

Under the owner's explicit direction to correct stale references, active
AGENTS.md, pipeline/execution/privacy/workflow and overview guidance now replace
the obsolete Stage 19 prerequisite with **accepted Stages 0–11, owner-frozen
Stage 12 design, validated implementation, phase-specific preflight and separate
exact-workload authorization**. Public probing requires its own authority;
protected calibration additionally requires the post-probe owner C/T and
deployment/operations freeze and exact preflight workload approval. Final
retrieval follows the calibration/N state machine. There is no Stage 13 or
fictional future Stage 19 dependency before Stage 12.

The size=1 preference does not choose N or override accepted FULL_TEXT requests.
V1 uses exact Stage 11 modes; explicit depths come from approved Stage 12
policies. These prospective governance corrections implement the owner's
review direction, **authorize no call now**, and do not edit historical frozen
Stage 0–11 records or rewrite D017/D032. D092 records the reconciliation.
Ordinary implementation authorization remains offline/synthetic-only.

## Baseline precheck and limits

The original design session ran git fetch --all --prune --tags before editing. Local
main, origin/main and HEAD were equal, the working tree was clean, and no
Stage 12 source, test, client, launcher or machine-readable asset existed.
The design branch was created directly from the accepted main below. Full
ancestry checks passed for design, implementation, reporting and independent
review commits. This revision fetched again and verified a clean design branch
at the previous design SHA, origin equality and unchanged accepted main/tag.
Annotated tag objects and peeled commits are distinguished.

| Binding | Accepted value |
|---|---|
| main / origin/main / acceptance tag peeled commit | 678a1dd4fc22c518ddd13a06d1de347a57da7a1c |
| Acceptance tag | stage11-semantic-request-deduplication-v1 |
| Acceptance tag object | c317fcbb53559de1eb1377b73c3ad1b9955aaf45 |
| Design-freeze tag | stage11-semantic-request-deduplication-design-v1 |
| Design tag object | 437e3bca124ca463a10abccee59a213306926923 |
| Design tag peeled commit | 125b3684a000ea79523f77049ae1a290b0da8109 |
| Implementation | 8dce0e1078e123748ae692fa824200fc3e646aa4 |
| Reporting | d49e9340ef3ae9cb3caaec65d5ccf0c490ecf366 |
| Independent review | 4284f97bb29c8aa4319202d75fd9e96223584fcc |
| Stage 11 publication | stage11_development_20261004T095201Z_8dce0e1078e1 |
| Stage 11 manifest SHA-256 | 9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc |
| semantic_request count / logical SHA-256 | 105,805 / 01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e |
| hypothesis_request_map count / logical SHA-256 | 142,677 / ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3 |
| Complete Stage 11 logical SHA-256 | e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337 |
| Stage 11 input binding | 083830b8a8e696668f5956afc6405074dbec84e5bdb150994c2acb67d2897edf |

The authoritative controlled artifact is
/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/development/stage11_development_20261004T095201Z_8dce0e1078e1.
This path is an input locator, not an execution-ID component.

Precheck verified the SHA-256 of the **tracked sanitized manifest copy**, its
relation bindings and registration agreement against the owner's supplied
values and [Stage 11 acceptance](STAGE11_OWNER_ACCEPTANCE.md). No SSH, protected
artifact reopen, payload read, scheduler observation or service call occurred.
Current remote filesystem health is not claimed. Stage 11 acceptance and its
full independent review establish artifact acceptance; the future guarded
reader must fully reopen and validate it before protected materialization.
HOLDOUT sealing relies on accepted authority and this session's non-access,
not opening HOLDOUT to prove it is sealed. Production was not accessed.

## Input and map-back

Use the complete accepted Stage 11 catalog, including all **81,773 FULL_TEXT**
and **24,032 STRUCTURED** requests. All 105,805 are country-bound. Stage 10's
operating budget remains **UNSELECTED**. No family pruning, new semantic
deduplication, source deduplication or representative-hypothesis selection.
Full calibration covers all accepted requests at owner-frozen C. A separate
deterministic bounded subset runs at T>max(C,10), plus paired-size diagnostics;
none substitutes for complete final retrieval.

Upstream contract/profile/schema hashes and the transitive Stage 10 input
binding are inherited exactly from the accepted Stage 11 manifest. Recompute
semantic IDs, verify complete relation fingerprints, upstream FKs, registration,
seal and inventory under external accepted expectations. Never trust a manifest
merely because its internal fields agree with one another.

The chain remains:

~~~
Stage 8 source row / representation occurrence
  -> Stage 10 context -> hypothesis (and its exact context-family membership)
  -> Stage 11 hypothesis_request_map -> semantic_request.query_semantic_id
  -> Stage 12 request_execution -> request_candidate at returned rank
~~~

Do not copy upstream source/context/family maps into Stage 12. A shared request
executes once per complete execution identity; each upstream context later
interprets its evidence separately. All 35,000 source rows remain in source-grain
left joins, including upstream no-hypothesis outcomes. The 142,677 Stage 11
edges must survive exact joins; Stage 12 introduces no new hypothesis edge.

## Proposed versioned assets

These names describe future machine-readable assets; **none is created in this
design session**. Implementation must generate exact descriptors and independent
canonical byte vectors after design approval.

| Name | Purpose |
|---|---|
| stage12_pelias_retrieval_contract_v1 | Hashes this five-document normative package and semantic rules |
| stage12_pelias_retrieval_profile_v1 | DEVELOPMENT population, calibration/final role and binding requirements |
| stage12_pelias_retrieval_schema_v1 | Ordered four-relation schema bundle, keys, nullability and enums |
| stage12_retrieval_policy_v1 | Result limit and retention semantics; separately versioned policy object |
| stage12_pelias_deployment_manifest_v1 | Deployment/index/default behavior schema and operator evidence |
| stage12_request_materialization_v1 | Exact Stage 11-to-HTTP mapping and serialization |
| stage12_response_validation_v1 | Whole-response validity, including malformed-feature failure; separate from network identity |
| stage12_response_extraction_v1 | Offline deterministic candidate projection and raw-payload provenance |
| stage12_response_projection_v1 | Dataset-level raw-input/validation/extraction/schema binding; no additional relation |
| stage12_campaign_provenance_v1 | Exact executable/runtime/operations and append-only authorized segment/attempt evidence |
| stage12_execution_identity_v1 | Named typed framing and identity domains |
| stage12_transport_operations_v1 | Attempts, timeouts, rate control and circuit breaker |
| stage12_attempt_receipt_v1 | Audit receipt schema within request_attempt, not another relation |
| stage12_calibration_protocol_v1 | Selection frame, comparisons and owner freeze criterion |
| stage12_pelias_retrieval_manifest_v1 | Input, executable, policies, inventory and logical fingerprints |
| stage12_pelias_retrieval_summary_v1 | Allowlisted sanitized aggregates |
| stage12_publication_record_v1 | Stage-specific registration/seal binding |

Separate deployment, policy, materialization, response and operations assets
are necessary: they have different identity effects and validation lifetimes.
They are small manifest-bound objects, not additional row-level relations.
No additional response or execution-receipt table is needed.

For document binding, use the Stage 11 metadata convention: JSON with sorted
keys, ASCII escaping, compact separators, integers only and one final LF.
The contract object contains contract_version and design_documents, the five
relative paths sorted by UTF-8 bytes with each file's exact SHA-256. Exclude
its own digest, Git commit and project indexes to avoid a self-hash cycle.
Descriptors/profile each hash their exact canonical bytes. An owner freeze
names an exact Git SHA; no future executable or deployment hash is invented.

## Publication, completeness and acceptance

There are two distinct publication kinds:
**STAGE12_DEVELOPMENT_CALIBRATION_EVIDENCE** and
**STAGE12_DEVELOPMENT_PELIAS_CANDIDATE**. A supplemental paired-size artifact
is calibration evidence with an explicitly hashed subset/workload. It cannot
masquerade as the complete final candidate. Each final artifact contains one
deployment binding and one globally frozen operational retrieval policy.

An accepted complete final candidate requires:

- exactly 105,805 execution rows and exact set equality to the accepted
  semantic_request keys, one execution per request under the frozen policy;
- terminal state SUCCESS_WITH_CANDIDATES or SUCCESS_ZERO_CANDIDATES for every
  execution; **technical final failures = 0**, contract failures = 0, identity
  failures = 0, missing or duplicate executions = 0;
- complete response/raw-object/candidate reconciliation, all rank/count
  invariants, original HTTP capture and approved validation/replay provenance,
  collision checks, and
  exact upstream map-back;
- verified deployment continuity under the approved observability mode for all
  adopted attempts/segments; no drift,
  unverified interval, secret leakage, unresolved integrity or I/O ambiguity;
- accepted calibration evidence and an explicit owner decision freezing final
  N before the final candidate is registered and before any HOLDOUT use.

All-zero retrieval could meet structural completeness but is not automatically
scientifically accepted: the owner must assess diagnostics and probe behavior.
A failed/partial run remains a controlled failure artifact, with checked,
completed, failed and unprocessed counts kept separate. It receives no
candidate _COMMITTED seal. It is never published as a valid subset.

Reuse the accepted Stage 9 protocol and Stage 10/11 split-workspace discipline:
exclusive permanent reservation -> immutable validated artifact -> Stage
12-specific registration -> atomic exclusive empty _COMMITTED -> full reopen.
Verify the same PanFS path, ownership, filesystem and exclusive-create/fsync
assumptions before input access. Do not substitute RENAME_NOREPLACE, overwrite,
hard links, symlinks, lock theft or a directory-exists success test. Failed
reservations and uncertain writes remain preserved.

Registration uses record_version stage12_publication_record_v1, the exact
namespace above, stage12_input_binding_sha256, publication_key, manifest and
inventory hashes, executable SHA/runtime inventory, contract/profile/schema/
validation/extraction/projection/operations hashes, retrieval_policy_id, deployment fingerprint,
index_data_identity, full logical result/candidate digests and summary hash.
It also binds the calibration selection/freeze record and adopted checkpoint
inventory. No Stage 10/11 registration key is reused under a new stage number.
Hashes of physical files and logical rows have distinct named fields.

The registration body has exactly record_version, namespace, publication_key
and bindings. The bindings object has these exact required fields:

~~~
stage12_input_binding_sha256, manifest_sha256, inventory_sha256,
executable_sha, runtime_inventory_sha256, contract_sha256, profile_sha256,
schema_sha256, validation_sha256, extraction_sha256, response_projection_id,
campaign_manifest_sha256, projection_provenance_sha256, operations_sha256, retrieval_policy_id,
pelias_deployment_fingerprint, index_data_identity, effective_behavior_id,
scientific_result_sha256, candidate_relation_sha256, summary_sha256,
calibration_protocol_sha256, workload_sha256, adopted_checkpoint_inventory_sha256,
owner_freeze_sha256
~~~

All are full SHA-256 hex except executable_sha (full Git commit hash of the
publishing/validation executable). campaign_manifest_sha256 binds the original
network executable, runtime, operations and authorized job chain even for an
offline re-extraction publication. projection_provenance_sha256 binds extractor
SHA/runtime, parent dataset and replay authorization/evidence. A new projection
uses a new immutable publication key/registration without changing request IDs,
original raw bytes or prior accepted artifacts.
owner_freeze_sha256 is explicitly null for calibration evidence and mandatory
for a final candidate. workload_sha256 binds exact input scope and policy;
the complete catalog and paired subset cannot share it. An empty adoption
inventory still has a canonical hash. The
stage12_registration_id is H("SAFE:stage12-publication-record:v1", ordered
fields record_version string and record_body canonical JSON bytes), using the
[data contract's H/J rules](STAGE12_DATA_CONTRACT.md#identity-domains-and-canonical-bytes)
over the body **without** this ID. The ID is stored in a wrapper
alongside that exact body. Paths/publication key may enter this audit identity;
they never enter a scientific request/execution identity. _COMMITTED seals this
single exact registration and artifact, not an arbitrary latest response set.

The final seal is created only after private topology and all bytes have been
reopened, validated and fsynced. Seal creation followed by uncertain directory
fsync is an **unknown publication outcome**, not success or permission to
overwrite: a separately authorized reconciliation must prove the exact
registered object. Successful publication still requires independent review
and explicit owner acceptance. It authorizes neither Stage 13 nor another run.

## Privacy and scale

Only the owner-authorized self-hosted SAFE deployment may receive protected
DEVELOPMENT payloads under a later frozen execution contract. No public API,
other geocoder, LLM, analytics/telemetry collector or third-party proxy.
Source addresses, request targets, labels, raw bodies, candidate rows and
row-level hashes stay controlled. Git carries only design, later synthetic
fixtures/contracts, aggregate metrics and approved non-sensitive bindings.
No secret, secret hash or echoed credential is an artifact.

Every protected entry point invokes the shared fail-closed guard **before input
access**, requiring SAFE_EXECUTION_SITE=goethe-nhr and nonempty SLURM_JOB_ID,
DEVELOPMENT-only bound paths, private directories 0700 and files 0600.
Code reaches Goethe via Git at an exact pushed SHA; no dynamic job pull or code
rsync. Login nodes orchestrate only. No /scratch, shared Conda modification or
write to /work/footprint/public.

Execution streams Arrow batches; bounded DuckDB/Polars joins and external sorts
provide validation and reporting. No pandas production path, giant response
collection or population-sized Python set. Keep transient database/spill and
bounded decoding on private compute-local storage, durable responses/checkpoints
on controlled PanFS. Never assume local scratch survives job end.

At the proposed C=10, a complete policy has at most 1,058,050 candidate
rows. The separate audit cap is 2,000 requests at owner-frozen T, with the
full call/result-position formulas in the calibration protocol. C and T are
not claimed safe or adequate now. At 1 request/second a full policy already
needs about 29.4 hours before overhead; multiple authorized jobs are expected. Plan durable capacity from measured response bytes, compression,
candidate Parquet, receipts, checkpoint copies, final copies and retained
failures, including filesystem allocation and headroom; compression is not a
guaranteed bound. Production requests are unknown until its own Stage 11.
Production has 141,048,582 source rows; DEVELOPMENT performance does not prove
capacity. A separate production design must authorize quotas, indexing and
retention using measured bytes/request and skew tests. See the execution
contract for byte bounds and packing; no new production access is authorized.

## Stage 13 handoff and stop

Hand off the committed four relations, exact raw responses and locators,
validation/extraction contracts and response_projection_id,
input/deployment/index/policy/freeze bindings,
attempt provenance, summary, validation and full-reopen evidence. Stage 13 can
recover all original feature properties and upstream context/evidence lineage.
It must not mistake calibration compatibility diagnostics for candidate scores.

Pelias confidence is **SUPPORTING descriptive metadata only**. Match type,
including exact, is descriptive API metadata, not a correct-address or rooftop
label. A Point is geometry, not rooftop precision. Returned rank is retrieval
evidence. Cross-query convergence is dependent evidence, not independent votes.
Layer/contradiction/granularity gates, evidence weights, final ranking and
selection remain Stage 13 or the later explicitly approved granularity stage.

**NEXT: OWNER FREEZE OF STAGE 12 DESIGN.** No implementation, SLURM, probe,
protected read, HOLDOUT, production, Pelias call or Stage 13 work follows.

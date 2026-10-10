# Stage 12 design owner acceptance and freeze

**STAGE12_PELIAS_TOPN_RETRIEVAL_DESIGN_FROZEN**. On **2026-10-10**, the owner
accepts and freezes the scientific architecture and decision process exactly
as reviewed at **538f32023d2f78394e3acc5e8552f670fe0a6add**. This is design
acceptance, not implementation or DEVELOPMENT candidate acceptance.

The five normative documents below remain byte-identical to that commit,
including their historical pre-freeze wording. This separate status/provenance
record and D093 record the later owner decision; they do not amend those rules.
No implementation, machine-readable contract asset, service request, SLURM job
or protected payload access occurred during freeze.

## Git provenance and exact frozen documents

| Binding | Value |
|---|---|
| Accepted main before Stage 12 integration | 678a1dd4fc22c518ddd13a06d1de347a57da7a1c |
| Retained design branch | design/stage12-pelias-retrieval |
| Original design SHA | 54d52e01ed906c41b48c5dac945a76abd9f66846 |
| Owner-reviewed revised design SHA | 538f32023d2f78394e3acc5e8552f670fe0a6add |
| Normal non-squash design merge | 25e528c1b2b3917dd423c948ceb547ac3547f3c3 |
| Annotated design-freeze tag | stage12-pelias-topn-retrieval-design-v1 |
| Preserved Stage 11 acceptance tag | stage11-semantic-request-deduplication-v1 |

The final frozen main SHA is the peeled target of
`stage12-pelias-topn-retrieval-design-v1^{}`. The tag is created once after this
freeze/status commit. Its annotation and the final freeze report record the
exact target without a self-referential commit hash in this document. The merge
parents are the accepted main and exact reviewed design above. No squash,
rebase, cherry-pick, history rewrite or branch deletion occurs.

| Normative document | SHA-256 of exact file bytes |
|---|---|
| [Purpose, input, publication and handoff](STAGE12_PELIAS_TOPN_RETRIEVAL.md) | 18c62b499d0edd4e55f2a560cb7daeffb30e34bd20fa68b6df5a12ab9513c78c |
| [Data and identity contract](STAGE12_DATA_CONTRACT.md) | 99b399cb77686a073feb22de736aedcc054ec35f241df84515f57ccba12cda41 |
| [Execution and deployment contract](STAGE12_EXECUTION_CONTRACT.md) | 3e00babb3da80ad6d9db43d8dfb1af47d619b95fce656572a404731d8db936ca |
| [DEVELOPMENT calibration](STAGE12_DEVELOPMENT_CALIBRATION.md) | 56f315ba462829f815a41514bb6499abb8694f5a8323ba51397f1fe289eeb4ad |
| [Complete design review and owner directions](STAGE12_DESIGN_REVIEW.md) | 253005e049cd5084cb3b65ca3ef1b7942c00ee7c96b7a8f68e9a132b35c14cfe |

The exact reserved primary names are
`stage12_pelias_retrieval_contract_v1`,
`stage12_pelias_retrieval_profile_v1` and
`stage12_pelias_retrieval_schema_v1`. All separately versioned names in the
[reviewed asset inventory](STAGE12_PELIAS_TOPN_RETRIEVAL.md#proposed-versioned-assets)
are preserved, including deployment/policy, materialization, response
validation/extraction/projection, campaign and attempt contracts. No additional
machine-readable asset is created or invented by this freeze record.

## Accepted input and unchanged boundaries

[Accepted Stage 11](STAGE11_OWNER_ACCEPTANCE.md) publication
**stage11_development_20261004T095201Z_8dce0e1078e1** remains authoritative:
**105,805 semantic requests**, **142,677 hypothesis mappings**.

| Accepted binding | SHA-256 |
|---|---|
| Sanitized Stage 11 manifest | 9dc8e3853cc474c331d08740981b11d0b8128a7b11fd36d9f978cb883414b6cc |
| semantic_request | 01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e |
| hypothesis_request_map | ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3 |
| Complete logical dataset | e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337 |

These bindings are checked against tracked sanitized evidence and accepted
ancestry only. No controlled artifact is reopened to perform this freeze.
Stages 0–11 remain accepted, frozen and scientifically unchanged; the Stage 10
operating budget remains UNSELECTED. HOLDOUT sealing is preserved through
non-access, not inspection. Production remains untouched.

## Frozen architecture

The normative documents govern exact fields, types, framing and behavior. The
following records the accepted boundaries without replacing their definitions.

| Relation | Grain / key |
|---|---|
| retrieval_policy | One frozen result-affecting policy / retrieval_policy_id |
| request_execution | One complete network execution identity and terminal observation / request_execution_id |
| request_attempt | One actual or recoverably interrupted dispatch / attempt_id; unique campaign/execution/ordinal |
| request_candidate | One execution × original returned rank / (request_execution_id, rank), scoped to the artifact's response_projection_id |

Controlled raw-response, projection and campaign manifest objects and sanitized
publication/report objects complete this four-relation model. Stage 10/11
lineage is referenced, not duplicated.

The chain is **query_semantic_id → retrieval_policy_id → request_execution_id
→ authoritative raw response → response_projection_id / candidate projection**.
Domain-separated full SHA-256 binds policy result choices and the seven-field
network identity: identity version, semantic ID, policy ID, materialization
contract hash, deployment content fingerprint, immutable index/data identity
and effective behavior ID. Client Git/reporting SHA, extraction schema,
operations, attempts, jobs, paths, timestamps and secrets stay outside network
identity. Exact executable/runtime/operations/authorization are separately
bound in stable campaign provenance and required for checkpoint adoption.

Deployment identity hashes canonical result-affecting manifest **content**.
Signatures/keys verify authenticity separately; re-signing identical content
does not change identity. Immutable backing-index/data content is mandatory;
aliases describe exact mappings and cannot substitute for it. Effective
omitted language/layers/sources are bound as server behavior, without injecting
request defaults. Materialization preserves accepted text/modes and separate
country boundary, with exact GET/UTF-8 serialization. Runtime authentication
must be verified; secrets are neither persisted nor hashed into IDs.

Prefer verified per-response generation when supported. The realistic minimum
is verified pre-campaign manifest and immutable data, operator maintenance
exclusion/change control, periodic and post-campaign checks, and change-record
reconciliation. Unknown identity blocks execution; detected result-affecting
drift quarantines the campaign. Concrete observability is a later probe gate.

The authoritative raw body is the exact uncompressed application/entity
payload **after transport/content decoding and before JSON parsing or
transformation**. SHA-256 hashes those bytes; at-rest compression is storage
only. Strict sanitized capture metadata binds status, media type, content
encoding and payload length. Raw bytes plus capture context and frozen
validation/extraction/schema deterministically reproduce the candidate
projection offline. A changed extraction contract creates a new immutable
projection/dataset version, with separate provenance; sufficient retained raw
evidence avoids a new network call. Accepted projections never mutate silently.

Candidates retain the frozen identity/source/layer, geometry, coordinates,
descriptive match metadata, name/address/admin fields and raw fingerprints.
Ranks are **1-based original array order**. Duplicate-looking features remain;
no deduplication or rank compression. Any malformed required feature fails the
whole execution response; controlled raw audit remains subject to privacy
guards. Coordinates are longitude, latitude in WGS84/CRS84 order, finite
float64 within legal ranges, with no scientific rounding or precision claim.
Point, confidence and match_type=exact are not correctness or rooftop evidence.

Outcomes distinguish SUCCESS_WITH_CANDIDATES, SUCCESS_ZERO_CANDIDATES,
TECHNICAL_FAILURE_RETRYABLE, TECHNICAL_FAILURE_FINAL, CONTRACT_FAILURE and
DEPLOYMENT_IDENTITY_FAILURE. Complete acceptance requires all 105,805 requests
and zero terminal technical, contract or deployment failures. Technical failure
cannot become valid zero. Retry attempts remain audit records; proposed five
cumulative attempts, bounded timeouts/backoff/Retry-After and circuit breakers
await public safety evidence and owner operations approval. Initial proposed
rate is one request/second with two connections; hard ceiling four, with
evidence/approval before increases. Stable campaigns span authorized sequential
jobs, exact durable resume and cumulative budgets; walltime cannot justify
increased load or changed scientific identity.

## Gated parameters and future sequence

**C = UNSELECTED. T = UNSELECTED. N = UNSELECTED.** C is the complete-DEVELOPMENT
calibration ceiling; T is the deep-tail audit depth; N is final operational
depth. Planning value 10 selects none of them.

The following remain intentionally gated future empirical/operational values:

- Exact C and T, deterministic tail-subset and witness/workload bindings.
- Final operational N and its concrete retrieval policy ID.
- Verified deployment/index/authentication mechanism and concrete supported
  deployment-observability mechanism.
- Final retry/timeouts, rate/concurrency/resource/control budgets and
  disclosure release plan after public-probe evidence.
- Exact protected subset/calibration workload fingerprints after authorized
  offline preflight and before protected dispatch.

The [frozen state machine](STAGE12_DEVELOPMENT_CALIBRATION.md#future-state-machine)
requires separately authorized implementation/synthetic validation, then an
authorized PUBLIC/SYNTHETIC probe of capability and service safety. Public
geocoding quality cannot select scientific N. The owner then freezes exact
C/T, deployment/auth/observability, witness/subset and operations rules before
authorizing an offline protected preflight; exact workload fingerprints and
coverage require owner approval before any protected network retrieval.

Complete calibration uses all accepted requests at C. A deterministic,
predeclared stratified tail audit uses at most 2,000 requests at T>max(C,10),
with the reviewed mandatory coverage and stop rules. Potentially useful
evidence beyond C or persisting to the deepest audited rank produces
insufficient calibration depth, never automatic selection of the maximum rank.
Coarse witness sets preserve compatible and unknown evidence, respect upstream
dependency lineage, do not penalize unavailable references, and never score
candidates or count correlated restatements as independent confirmation.
Cost cannot override demonstrated candidate-value loss.

Different sizes retain different policy/execution IDs, even with observed
prefix agreement. After adequate DEVELOPMENT calibration, the owner freezes N:
N=C permits calibration evidence reuse only through all frozen reuse gates;
N!=C requires a complete direct-size DEVELOPMENT retrieval. Then complete
validation, independent review and owner acceptance are required. No state
opens HOLDOUT or starts Stage 13.

Stage 13 later receives ordered evidence, complete Stage 11 lineage,
policy/execution/deployment/index identities, raw provenance, projection and
outcomes, without a score or winner. D092's Stage 19 finding is frozen: stale
legacy query-deduplication/QA numbering creates **no active dependency**.
Historical records remain unchanged.

## Publication, privacy and validation boundary

Future publication uses exclusive reservation → immutable validated artifact
→ Stage 12 registration → exclusive _COMMITTED → full reopen. Bind Stage 11,
policy/deployment/index/execution, raw and candidate/projection fingerprints,
and exact executable/campaign provenance. Streaming, bounded memory/queues,
compressed raw storage and durable checkpoints support Arrow/DuckDB/Polars;
there is no pandas production path or giant in-memory response collection.

Protected payloads may later go only to explicitly authorized self-hosted SAFE
Pelias. Controlled evidence remains on approved Goethe/SAFE storage; Git and
portable reports exclude protected strings, raw responses and secrets. Portable
reporting is sanitized aggregates only. No service capability or production
capacity is claimed to have been tested by this freeze.

The accepted [ledger](STAGE12_DESIGN_REVIEW.md) contains **57 resolved design
checks** and **24 incorporated owner directions**. **Unresolved scientific
design decisions = 0; design defects = 0.** Future gated parameters are not
design defects. Lightweight validation covers exact reviewed-file bytes,
accepted ancestry and tracked Stage 11 bindings, contract/identity/calibration
documentation, links/anchors, Markdown-only changes, privacy/tracked-data scope,
whitespace, tag targets and remote synchronization. No protected, scientific,
service or implementation test is implied.

Local freeze validation passed: all five reviewed files and recorded hashes
match; accepted ancestry and sanitized Stage 11 bindings match; the complete
integration contains only 16 Markdown files, with 242 local links and 27
anchors verified. Ledger, identity, unselected-depth, tracked-data scope and
whitespace checks pass. Tag/remote checks complete after the freeze commit.

**Stage 12 DESIGN FROZEN; Stage 12 implementation NOT STARTED; HOLDOUT sealed;
production untouched; Pelias NOT CALLED; no SLURM; Stage 13 NOT STARTED.**

**NEXT: OPEN ONE FRESH SESSION FOR STAGE 12 IMPLEMENTATION + PUBLIC/SYNTHETIC PELIAS PROBE.**
This is a next-session boundary, not current implementation/probe authorization.

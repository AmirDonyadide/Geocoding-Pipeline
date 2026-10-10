# Stage 12 — identity, request and response data contract

Normative part of the [design proposal](STAGE12_PELIAS_TOPN_RETRIEVAL.md).
Prose/schema notation only; no executable schema, client or fixture is created.
Initial v1 names are retained because the previous draft was never frozen,
implemented or used to issue scientific artifacts/IDs; its exact prior wording
remains in Git. After owner freeze, changing a rule requires version review.

## Identity domains and canonical bytes

Reuse Stage 11 E framing exactly: uint64 big-endian sequence count; tags 00
null, 01 strict UTF-8 string with uint64 byte length, 02 bytes with uint64 length,
03 uint64, 04 Boolean byte 00/01, 05 nested E sequence. Reject invalid Unicode,
overflow, unknown types, Boolean-as-integer, duplicate named fields and trailing
bytes. Named(X) is E of ordered two-element records (exact ASCII field name,
typed value) in the stated schema order. Never hash URL text as semantic identity.

Define H(domain, fields) = SHA256(ASCII(domain) || 00 || Named(fields)).
All digests are full 32-byte fixed_size_binary[32]; lowercase 64-hex is display
only. No shortened hash is a key. Recompute IDs, compare full preimage bytes
when identities coincide, and fail on any collision or ID mismatch.
No suffix/salt/first-row collision repair.

### Retrieval policy

Policy is global constant-depth in v1. No per-request/country/family/adaptive N.
The exact ordered fields are:

| Field | Type | Value |
|---|---|---|
| policy_version | string | stage12_retrieval_policy_v1 |
| result_limit | uint64 | Concrete approved positive integer; full calibration C and tail audit T frozen after public capability probe; final N UNSELECTED |
| retention | string | ALL_RETURNED_IN_ORDER |
| result_options | ordered list | Empty, exactly; size is the only Stage 12 result option |

retrieval_policy_id = H("SAFE:stage12-retrieval-policy:v1", these fields).
No absent/default size; decimal integer on wire. Purpose CALIBRATION/FINAL
belongs in the artifact profile, not this identity: an identical size=10 policy
may support both roles after review without inventing different science.
Retries, concurrency, time, paths and deployment do not enter policy ID.
Changed retention/allowed options require a new policy version and review;
Stage 11's REJECT_UNLISTED cannot be overridden by this empty list.

### Deployment, index and effective behavior

The execution contract specifies exact contents of three closed canonical
metadata objects: IndexCore, EffectiveBehaviorCore and DeploymentCore.
Canonical JSON J uses sorted keys, ASCII escaping, compact separators, one
final LF, integer numbers only; semantically fractional configuration values
are exact strings with an explicitly declared unit/interpretation. Ordered
configuration arrays retain order; inventories that are sets sort by full
identifier UTF-8 bytes and reject duplicates. No unknown schema fields.

~~~
index_data_identity =
  H("SAFE:stage12-index-data:v1",
    [("manifest_version", "stage12_pelias_deployment_manifest_v1"),
     ("index_core", J(IndexCore) as bytes)])
effective_behavior_id =
  H("SAFE:stage12-effective-behavior:v1",
    [("behavior_version", "stage12_effective_behavior_v1"),
     ("effective_core", J(EffectiveBehaviorCore) as bytes)])
pelias_deployment_fingerprint =
  H("SAFE:stage12-pelias-deployment:v1",
    [("manifest_version", "stage12_pelias_deployment_manifest_v1"),
     ("deployment_core", J(DeploymentCore) as bytes),
     ("index_data_identity", index_data_identity as bytes),
     ("effective_behavior_id", effective_behavior_id as bytes)])
~~~

Only canonical result-affecting manifest **content** enters these cores.
Signatures, signing keys/key IDs, signature encodings, re-signing timestamps,
verification receipts, maintenance leases and operator audit sit outside them.
Re-signing identical content or rotating an approved signing key changes
authenticity evidence, not deployment fingerprint or execution ID. Failed
authenticity verification still blocks use. Raw configuration containing secrets must never be
hashed into these objects. The reviewed result-affecting configuration
projection contains **no credential value, secret-derived hash or secret name
whose value affects a hidden data view**. Bind the nonsecret authorized data-view
identity instead; require identical view across permitted credential rotation.

### Complete execution

request_execution_id = H("SAFE:stage12-request-execution:v1", the following
ordered fields):

1. identity_version: "stage12_execution_identity_v1";
2. query_semantic_id: 32 bytes, FK to the accepted Stage 11 catalog;
3. retrieval_policy_id: 32 bytes;
4. materialization_contract_sha256: 32 bytes;
5. pelias_deployment_fingerprint: 32 bytes;
6. index_data_identity: 32 bytes;
7. effective_behavior_id: 32 bytes.

The materialization descriptor binds method, paths, parameter and header rules,
UTF-8/percent encoding and allowed service routing/data-view semantics.
This descriptor contains request rules and their semantic version, **not**
implementation file hashes, response validation or extraction rules. A changed
request rule requires a new materialization version/content hash. A refactor
that obeys the same rules leaves execution ID unchanged. A client bug that
actually sent different values is nonconformance, not reusable evidence under
the claimed ID; it requires review and, if necessary, an authorized new request.
Actual client Git SHA, runtime inventory and operational configuration are
strongly bound in campaign provenance and checkpoint validation, outside this ID.
The overall five-document design hash includes operations and review prose;
it is publication provenance, **not** an extra execution-ID argument.

No client executable/reporting SHA, response-extraction contract/schema,
API secret, secret hash, SLURM job, filesystem path, timestamp, retry count,
concurrency, worker, latency, campaign ID or physical packaging enters this ID.
Effective index/configuration/ranking defaults and backend services enter
transitively through the deployment objects, never an opaque unknown sentinel.
An operational policy change alone does not change scientific execution ID.
Changed N keeps query_semantic_id but changes policy and execution IDs.

The result is an observation under the complete execution identity, not a
promise that arbitrary live requests are deterministic. Repeated same-size
probe disagreements are a reproducibility gate failure. Stored raw evidence
remains authoritative even if future software cannot reproduce it.

### Campaign provenance and offline response projection

The campaign manifest is an audit object, not a fifth relation. It binds a
persisted random campaign_id (32 bytes), exact client executable Git SHA,
runtime/dependency inventory, operations-policy hash, authorized workload,
input/materialization/policy/deployment bindings, authenticity and drift-control
receipts, and the append-only authorized job/segment/attempt inventory.
Campaign identity stays stable across authorized jobs; per-job receipts change.
Network checkpoint adoption requires exact client SHA/runtime/operations and
remaining attempt budgets. An immutable campaign-start object precedes dispatch;
the completed campaign manifest seals its start hash and append-only segment
chain. Attempts bind the start object, so no future-manifest/self-hash cycle
exists. Reporting revisions cannot redefine retrieval.

Define raw_response_set_sha256 by the response-set framing below. Then:

~~~
response_projection_id =
  H("SAFE:stage12-response-projection:v1",
    [("projection_version", "stage12_response_projection_v1"),
     ("raw_response_set_sha256", raw_response_set_sha256 as bytes),
     ("capture_context_sha256", capture_context_sha256 as bytes),
     ("response_validation_contract_sha256", validation descriptor hash as bytes),
     ("response_extraction_contract_sha256", extraction descriptor hash as bytes),
     ("candidate_schema_sha256", candidate descriptor hash as bytes)])
~~~

This is a **dataset-level** binding in the immutable manifest, not a per-row
column or new relation. Each artifact has exactly one projection. Candidate
keys (execution ID, rank) are scoped by that artifact/projection; cross-version
joins must also bind response_projection_id. Final dataset digest includes the
projection ID and actual output relation hashes. Extractor executable/runtime,
parent projection, reason/approval and validation evidence are recorded as
projection provenance, separately from network campaign provenance.

capture_context_sha256 streams ASCII("SAFE:stage12-capture-context:v1") || 00,
E([captured count U]) and sorted E([execution ID, actual request-target hash,
HTTP status U, sanitized content_type T, sanitized content_encoding T,
payload_complete Boolean]) for the same captured rows as the raw set.
All these values are required for a captured complete payload; unknown header
values use the audit enum OTHER rather than copied text. This binds the small
original response envelope needed for validation without code/signature/time
or another relation. Payload hash alone cannot prove a successful HTTP status.
Its full SHA-256 is the capture_context_sha256 binding above.

Projection is deterministic and offline:
preserved payload bytes + immutable capture context + frozen
validation/extraction/schema -> all-or-nothing
outcome and candidate rows. Verify payload hashes before parsing; same bytes/
contracts must yield the same logical rows irrespective of storage compression,
job or layout. A bug fix that corrects implementation under unchanged intended
rules records new extractor provenance and output dataset hash; changed
contract/schema gives a new response_projection_id. Neither requires another
Pelias call if raw evidence and original request/deployment provenance suffice.
Insufficient raw evidence stops replay; it never silently authorizes a call.

Never mutate an accepted candidate relation, response outcome or old manifest.
Publish a separately reviewed immutable projection/dataset version, preserving
the original and an exact parent binding. Its request_execution outcomes are
validated under the new artifact-level contract; original network attempt
receipts (including an earlier validation failure) remain unchanged. Any changed
classification is explicit replay evidence, not a new HTTP success. Replay may
use a new extractor executable without claiming network checkpoint adoption.

### Attempts and observed responses

attempt_id = H("SAFE:stage12-request-attempt:v1", ordered fields
receipt_version="stage12_attempt_receipt_v1", request_execution_id bytes,
campaign_id bytes, attempt_number uint64). campaign_id is a newly allocated
32-byte audit nonce persisted before dispatch, shared across that campaign's
authorized resumes. attempt_number is cumulative 1..max_attempts for an
execution, with max_attempts<=5 from the owner-frozen operations profile.
A new campaign cannot silently reset an exhausted budget; it needs a separately
authorized workload. Times/latencies remain audit metadata, outside even this ID.

response_sha256 = SHA256(exact uncompressed **application payload bytes delivered
to the response parser after transport and content decoding, before any UTF-8/
JSON parsing or transformation**). This is not a capture of pre-decoding wire
bytes: transfer framing, TLS records and compressed transfer representation
are outside the scientific object. v1 requests Accept-Encoding=identity and
accepts identity/absent Content-Encoding only; supporting another content
decoder later requires a reviewed transport profile and decoder provenance.
The definition always hashes the decoded application bytes, never a compressed
representation. At-rest compression is storage-only and cannot change this hash.
Byte length is measured on this same payload. Those exact bytes reproduce
every JSON token/feature slice needed for independent deterministic extraction.
raw_feature_sha256 = SHA256(exact contiguous JSON feature-object byte slice
within that body). Offset is zero-based byte start and length; its hash is not
a JSON reserialization or a GID-derived identity.

## Exact materialization and serialization

Project-owned authority is the accepted
[Stage 11 contract](STAGE11_DATA_CONTRACT.md#exact-typed-core-and-field-order)
and s11_semantic_contract.py at the accepted baseline. Their paths and slots
are verified locally. No repository deployment configuration or response
fixture establishes the installed SAFE service's implementation; future
compatibility evidence must verify the proposed response and authentication
contract before protected input is sent.

| Stage 11 slot | FULL_TEXT | STRUCTURED |
|---|---|---|
| endpoint | GET /v1/search | GET /v1/search/structured |
| text | Exact nonempty text -> text | Must be null, omitted |
| address | Null, omitted | Exact nonempty address -> address |
| postalcode | Null, omitted | Exact string -> postalcode, omit null |
| locality | Null, omitted | Exact string -> locality, omit null |
| region | Null, omitted | Frozen upstream null, omitted; hypothetical non-null rejected |
| country | Null, omitted | Frozen upstream null, omitted; hypothetical non-null rejected |
| boundary_country | Exact uppercase alpha-2 -> boundary.country | Same, independent of structured country |
| size | Concrete policy result_limit | Same |

STRUCTURED requires at least one of postalcode/locality as accepted upstream.
The mapping names region/country explicitly but v1 cannot populate them; a
future upstream contract is required. No alpha-3 conversion, inferred address
country, full-text fallback, translation, trim, case change, Unicode
normalization, repair or value substitution. A service unable to represent any
accepted country/giant scalar blocks complete execution; no truncation/drop.

Method is HTTP GET, no body, exact path. Sort emitted ASCII parameter names
lexicographically: address, boundary.country, country, locality, postalcode,
region, size, text, omitting inactive/null slots. Names appear once. Join
name=value with & and attach with one ?. Encode each exact string as strict
UTF-8, then RFC 3986 unreserved ASCII A–Z a–z 0–9 - . _ ~ remains literal;
every other byte uses %HH uppercase hex. Space encodes as %20, literal plus as
%2B, literal percent as %25 and LF as %0A; never form-style plus-for-space.
Round-trip decoded bytes must equal input bytes. No repeated/list parameter,
comma list, fragments, userinfo, dynamic host or arbitrary parameter bag.

HTTP/1.1 is the v1 client protocol; host authority and TLS verification come
from the approved transport profile. Construct only Host, Accept:
application/json, Accept-Encoding: identity, User-Agent:
SAFE-stage12-retrieval/1 and runtime X-API-Key. No Accept-Language, lang,
Cookie, Referer, contextual header, IP-derived focus, layers or sources.
No proxy/environment header injection, automatic redirect, automatic HTTP
retry, cookie jar or credential-bearing URL. Header order is the order above,
with CRLF framing; library conformance is checked on a synthetic local capture.
TCP segmentation/TLS ciphertext are not scientific serialization promises.
The secret is inserted only at dispatch, never part of the request-target
fingerprint or persisted header collection.

Record SHA256(ASCII("GET") || 00 || exact path-and-query bytes) in the controlled
execution row for audit; it is not a deduplication key. Reconstruct the request
from immutable Stage 11 and execution objects; no second protected query table.
Freeze deployment-specific request-target/header limits after public probe
and operator evidence, before DEVELOPMENT. Overlimit gets CONTRACT_FAILURE /
REQUEST_TARGET_TOO_LARGE, full map retained, no POST fallback or truncation.

## Strict response contract and evidence preservation

Choose **both exact raw successful application payload bytes and an extracted candidate
relation**. Preserve every field/duplicate feature and all response metadata
through raw bytes; normalized columns serve bounded Stage 13 access. A hash
alone cannot reconstruct discarded evidence. Canonical reserialized JSON
would lose exact-byte provenance. Raw response storage is compressed at rest
in independently decompressible frames, with byte lengths and physical hashes.
See execution contract for bounded packing and durability.

Validate the complete response before creating any candidate rows:

- Status 200 only is accepted as this endpoint's successful GeoJSON contract.
  Other 2xx (including empty 204/partial 206) fail CONTRACT_FAILURE unless a
  newly reviewed contract explicitly supports them.
- Content-Type is application/json or application/geo+json, optionally
  charset=utf-8; reject another charset/content coding. Strict UTF-8 without
  BOM, one complete JSON object, no trailing content, duplicate object keys,
  invalid escape, nonfinite number, lone surrogate or truncated content.
- Top-level type="FeatureCollection"; features is an array with length <=
  requested size. Empty array is valid zero. No null/missing features.
  At both top level and inside geocoding, nonempty errors arrays or malformed
  errors/warnings fields fail contract. warnings if present must be an empty
  array under v1: silently ignored or
  repaired request warnings cannot yield valid scientific evidence. A new
  known-benign warning requires contract review, not substring filtering.
- Every feature is an object, type="Feature", properties is an object,
  geometry is a non-null object with type="Point" and exactly two numeric
  coordinates. Null, three-dimensional or other geometry is an unsupported
  response contract, not a filtered candidate. The whole response fails.
- properties.layer and properties.source must be nonempty strings and members
  of the deployment's declared vocabulary; new observed values fail closed.
  GID is optional because absence must not fabricate an identity. All listed
  optional string/number fields must have their declared type when non-null.
  Empty optional string is retained distinctly from null.
- confidence, when non-null, must be finite numeric in [0,1]; no threshold,
  promotion, clipping or weighted score. match_type and accuracy are exact
  nullable strings; their vocabulary is observed descriptively, never truth.
- geocoding metadata, if present, is an object. Its version/attribution string
  fields and integer timestamp, if present, must be correctly typed; query,
  engine and other non-extracted fields remain exact in raw bytes. A returned
  query object, if supplied, must be an object. Its declared echo keys for
  boundary/size/mode are compared using the pinned deployment echo adapter;
  contradictory echoes fail. The deployment manifest must specify explicit
  absence or an exact echo-field mapping; no guessed normalization of text.
- Deployment verification must pass the approved per-response or controlled
  campaign mechanism in the execution contract. Payload attribution or engine
  strings cannot replace that evidence.

Unknown additional JSON fields are retained in raw evidence and counted;
they neither extend the extracted model nor become score inputs silently.
Missing optional fields and explicit null both extract as null, while raw
bytes preserve their difference. A malformed expected field fails the entire
response. There is no skip-invalid-feature mode and no compressed/recomputed
rank. A malformed top-N feature makes the **whole execution response**
CONTRACT_FAILURE; retain the complete decoded payload for controlled audit,
with hash, attempt and failed-validation contract binding, and publish no
candidate rows. It is not a valid zero. The secret-echo and resource guards
still control persistence; a suspected secret payload is quarantined under
the privacy protocol, never put in ordinary candidate storage or logs.
Future additional extraction is an offline, separately versioned projection,
not a new network identity or mutation of the frozen Stage 12 relation.

Coordinate order is **longitude, latitude**, WGS84 geographic degrees
(GeoJSON/CRS84 order, not EPSG axis-order latitude first). longitude in [-180,180],
latitude in [-90,90], finite IEEE-754 binary64, non-null. JSON numbers convert
once by round-to-nearest ties-to-even; no decimal rounding. Exact original
numeric tokens remain recoverable in raw bytes. Preserve negative zero in
stored IEEE bits. No reprojection or inferred height. An explicit crs object
is rejected in v1. bbox, if present at collection or feature level, must be
four finite numbers in longitude/latitude order with legal ranges and south <=
north; west > east is retained as antimeridian crossing. bbox is raw-only.
Decimal digits do not establish spatial precision. All returned layers,
including coarse layers, remain stored; no point-usability gate is applied.

## Smallest relation model

D=fixed_size_binary[32], T=large_string, U=uint64, F=float64,
Z=timestamp[us, UTC], B=bool. ? means nullable; every unmarked field is required.
Enum columns store exact strings. All relations are controlled; policy objects
alone can be portable after nonsecret review. Row-level IDs/hashes are protected.
The four relations are the entire authoritative relation set:

### retrieval_policy — one concrete retrieval policy

PK retrieval_policy_id D. Fields in order: retrieval_policy_id D,
policy_version T, result_limit U, retention T, result_options list<struct> (empty).
Scientific, nonsecret. No FK. ID reconstructed by the formula above; no job or
calibration role stored here.

### request_execution — one complete execution identity and selected outcome

PK request_execution_id D; uniqueness is the complete seven-field identity
preimage. One row per network identity **within this immutable observation/
projection artifact**; intentional repeat probes use separate artifacts.
Fields, in order:

~~~
request_execution_id D, query_semantic_id D, retrieval_policy_id D,
materialization_contract_sha256 D, pelias_deployment_fingerprint D,
index_data_identity D, effective_behavior_id D,
request_target_sha256 D?, terminal_state T, reason_code T,
terminal_attempt_id D?, candidate_count U?,
response_sha256 D?, response_bytes U?,
raw_pack_key T?, raw_frame_offset U?, raw_frame_length U?,
response_completed_utc Z?
~~~

FKs: semantic ID to bound Stage 11; policy to local retrieval_policy; deployment/
index/effective hashes to the single manifest-bound objects; terminal attempt
to request_attempt with the same execution. Scientific authority covers network
identity, captured response and contract-relative terminal state; time/locator
are audit/physical fields. The manifest binds the one response_projection_id
and validation contract governing these outcomes. All response fields are
required for success. For CONTRACT_FAILURE they also remain populated when a
complete payload is captured for audit; failures without a complete safely
retained payload have null response fields. Terminal attempt can identify a
failed dispatched request; it is null only when no dispatch exists.
candidate_count=0 for successful zero, 1..N for successful nonzero, **null on
failure**. request_target_sha256 is null only if materialization never completed.
reason_code is OK for either success, otherwise a closed static failure code.
Never place arbitrary exception text in this field.

raw_pack_key is a safe relative inventory locator, not an external URI or
scientific ID argument. It locates one independently decompressible body
frame; no duplicate request_response table. Exact decompressed length/hash
must equal response_bytes/response_sha256.

### request_attempt — one dispatched or recoverably interrupted HTTP attempt

PK attempt_id D, unique (campaign_id, request_execution_id, attempt_number).
FK request_execution_id to request_execution. Ordered fields:

~~~
attempt_id D, request_execution_id D, campaign_id D, attempt_number U,
campaign_start_sha256 D, operations_policy_sha256 D, started_utc Z, finished_utc Z?,
elapsed_ms U?, http_status U?, outcome T, reason_code T,
received_body_bytes U, application_payload_bytes U?,
content_type T?, content_encoding T?,
retry_delay_ms U?, retry_after_seconds U?,
observed_deployment_fingerprint D?, identity_verification_receipt_sha256 D,
response_validation_contract_sha256 D, response_sha256 D?
~~~

Audit-only controlled relation. Null status means no trustworthy HTTP status;
null finish/latency with outcome UNKNOWN_DELIVERY means a persisted begin
receipt lacks a trustworthy finish. No fake finish time. response_sha256 exists
for a complete safely retained application payload, including a contract-failed
2xx payload; it is not evidence of valid retrieval by itself. Partial/network/
auth-error bodies have no candidate authority. received_body_bytes is transfer
accounting; application_payload_bytes is after decoding. Content-Type is stored
as the validated media-type/charset enum or OTHER/ABSENT, Content-Encoding as
identity/absent/OTHER; raw untrusted header text is not persisted. The strict
header audit allowlist is these values, parsed Retry-After, status and approved
nonsecret identity fields; no cookies, URLs, arbitrary headers or auth values.
The identity receipt FK resolves to the campaign provenance inventory even
when no per-response fingerprint exists under the minimum campaign mechanism.
campaign_start_sha256 resolves to the sealed campaign-start provenance
object; later job/finish receipts form its separately sealed append-only chain.
A run-level failure before dispatch has no invented attempt. Begin/finish
journal events are durable operational records used to derive this final
relation, not additional scientific relations.

On initial retrieval, success has exactly one terminal successful attempt.
On authorized offline replay, the terminal attempt must still be an actual
HTTP 200 capture; its original validation outcome may be CONTRACT_FAILURE,
with explicit new validation/reclassification provenance. Do not rewrite that
attempt to claim a new HTTP success. No retry after a valid durable success.
Every dispatch, including uncertain delivery and a later failed retry, consumes
one of five attempts across jobs. Attempt outcomes include the six states in
the execution contract plus UNKNOWN_DELIVERY; RETRYABLE is an intermediate
attempt state, never a final accepted execution state.

### request_candidate — one response feature at its original position

PK (request_execution_id D, rank U), scoped by the manifest's response_projection_id;
FK execution to successful request_execution in the same artifact. No copied
upstream lineage or fifth projection relation.
Ordered fields:

~~~
request_execution_id D, rank U,
response_sha256 D, raw_feature_sha256 D,
feature_byte_offset U, feature_byte_length U,
gid T?, feature_id T?, layer T, source T, source_id T?,
geometry_type T, longitude F, latitude F,
confidence F?, match_type T?, accuracy T?,
label T?, name T?, housenumber T?, street T?, postalcode T?,
neighbourhood T?, borough T?,
locality T?, locality_gid T?,
localadmin T?, localadmin_gid T?,
county T?, county_gid T?,
macrocounty T?, macrocounty_gid T?,
region T?, region_gid T?, region_a T?,
macroregion T?, macroregion_gid T?, macroregion_a T?,
country T?, country_gid T?, country_a T?,
continent T?, continent_gid T?
~~~

Scientific evidence, protected. Strings come from identically named properties
without alteration, except gid=properties.gid and feature_id=top-level feature.id.
If feature.id exists it must be string or null under v1; do not coerce numbers.
source_id stays a string, including leading zeros. No synthetic fallback GID.
properties.id and any additional admin abbreviations/languages/distance/parser
metadata remain raw-only and recoverable; this avoids an open-ended wide table.
Source/layer/gid and raw object are sufficient to preserve importer identity;
Stage 13 may version additional extraction when designing its own evidence.

Rank is **1-based**, exactly array position + 1. Preserve every position,
including repeated GID/coordinates/label or identical feature bytes. No
deduplication, layer filtering or rank recomputation. A raw feature hash is
provenance, not a candidate-consolidation key. Identical features may occupy
different ranks or executions.

## Invariants and logical fingerprints

For each successful execution: response features count = candidate_count =
candidate rows; 0 <= count <= result_limit; rank set exactly 1..count; PK
unique; candidate response hash equals execution hash; each feature slice parses
to precisely its indexed feature and regenerates the extracted row. Zero has
zero rows. Failure has zero rows and null count; a safely captured complete
contract-failed payload remains auditable but is never a successful response.
No missing/unaccounted attempt receipt, dangling FK, duplicate success selection
or shared-ID different preimage is publishable. UNKNOWN_DELIVERY may remain in
audit history only when its budget charge/recovery is reconciled and that
execution has a later valid terminal success; it is never a valid zero or
unresolved final execution. All upstream and manifest bindings match.

Descriptors freeze field order/type/nullability/enum/key/constraint definitions.
Logical row encoding is E over fields in the order above; add tag 06 only for
IEEE-754 binary64 as exactly eight big-endian bits, rejecting NaN/infinity.
Encode timestamps as strict strings YYYY-MM-DDTHH:MM:SS.ffffffZ. Null remains
tag 00. Relations sort by full unsigned PK bytes/numeric rank. Logical digest
streams ASCII("SAFE:stage12-relation:v1") || 00, E([relation name,
descriptor SHA bytes, row count U]), then every row in order.

Distinguish scientific and audit fingerprints. request_execution scientific
projection excludes physical raw locators, terminal_attempt_id and completion
time; request_attempt is audit-only. Candidate scientific projection excludes
byte offset/length but retains exact raw feature/response hashes and all other
columns. retrieval_policy is entirely scientific. Record both full relation
digests and descriptor-bound scientific projection digests. Exact body hashes
can differ across observations because Pelias emits time metadata; do not
claim identical outputs merely because execution ID matches.

Dataset scientific digest domain SAFE:stage12-dataset:v1 binds input-binding
digest, contract/profile/schema digests, response_projection_id, policy/deployment/index/
effective behavior IDs, ordered scientific relation digests and counts,
raw response-set digest and sanitized scientific summary digest. Response-set
digest streams ASCII("SAFE:stage12-response-set:v1") || 00, E([captured count U]),
then sorted E([execution ID, response hash, application payload length]) for
every complete retained payload, including controlled contract-failure audit.
The capture inventory binds absent payloads and their original outcomes
separately; no failure is dropped from execution totality. Operational aggregate
timings, file layout, receipts, full row digests and executable/runtime go in
the manifest/audit digest. Public displays never expose row-level digests.

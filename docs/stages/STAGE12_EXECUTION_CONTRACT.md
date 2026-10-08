# Stage 12 — verified deployment and bounded execution

Normative part of the [design proposal](STAGE12_PELIAS_TOPN_RETRIEVAL.md).
Every mechanism below is a requirement for future implementation and owner
verification; none is claimed to exist on the current SAFE server.

## Project evidence and unavailable facts

Repository inspection found accepted offline intent paths /v1/search and
/v1/search/structured and their Stage 11 GET mapping. There is **no checked-in
SAFE deployment/configuration, verified hostname, API-key mechanism, index
snapshot, live response fixture or deployed version inventory**. The
[project overview](../PROJECT_OVERVIEW.md#safe-pelias-role) states this limit.
Stage 11 cites pinned public Pelias source as design evidence; it does not
identify the installed SAFE release. No external documentation/service was
queried in this session.

X-API-Key over approved HTTPS is the **proposed v1 authentication contract**,
consistent with the owner's expected interface, pending operator attestation
and an authorized public probe. This is not a claim that authentication was
verified. If actual SAFE authentication differs, review the transport contract
before implementation of protected execution; never guess header names or
retry secrets against another service. Likewise the GeoJSON schema is a
proposed strict project contract that must pass the actual deployment probe.

## Controlled deployment manifest

Before protected requests, the SAFE deployment operator must provide a
controlled, versioned, immutable manifest export and evidence inventory.
Acquire it through an approved administrative channel onto controlled Goethe
storage, not by sending queries to an unidentified service. A hash without
operator/routing proof is insufficient. Use operator-signed bytes with a pinned
approved verification key, and preserve the signature and evidence hashes in
the run audit. Approval/signature authenticates the assertion, not automatic
proof of backend immutability; the serving and maintenance controls below
must enforce it. An unavailable required fact means IDENTITY_UNVERIFIABLE.

IndexCore has the following required keys (all inventories complete, no
unspecified/default placeholder; empty lists only when positively attested):

| Key | Required contents |
|---|---|
| schema_version | stage12_index_core_v1 |
| search_engine | Product, exact version, build/container digest and relevant plugins/analyzer versions |
| aliases | For each API-used alias: exact name, ordered routing/filter configuration and complete backing-index identity list; include no-alias direct targets explicitly |
| indexes | Name, immutable UUID, settings/mappings/analyzers hash, primary-shard topology, frozen commit/checkpoint inventory, document count and canonical snapshot/content manifest digest per backing index |
| snapshot | Content-addressed snapshot/build ID, full file/content inventory digest, restore recipe/version and build/import recipe hashes; UUID or count alone is insufficient |
| imports | Every data source/layer, exact source release/content hashes, importer revision/configuration digest, build ID, ancestry/overlap tokens and licence/provenance evidence |
| auxiliary_data | Interpolation, placeholder/admin, parser/language dictionaries and other result-affecting datasets with immutable content and build identities |
| immutability | Verified write-block/authorization policy, disabled ingest/update/alias mutation, frozen refresh/merge/replica routing policy and immutable-serving generation ID |

UUIDs identify indexes, not their changing contents. Bind a reproducible content
snapshot and prevent subsequent writes and alias replacement. Freezing primary
shards alone is insufficient if replica selection/ties change results: pin the
engine's stable routing/tie-breaking behavior or immutable serving topology and
verify repeatability. No adding an unapproved preference parameter to queries.
If that cannot be enforced, this design cannot certify reproducible retrieval.
A time-limited operator promise without enforcement is not enough.

EffectiveBehaviorCore required keys:

| Key | Required contents |
|---|---|
| schema_version | stage12_effective_behavior_v1 |
| endpoints | Both exact paths, GET/size limits, country vocabulary, error/schema/echo behavior and sanitizer/search pipeline order |
| omitted_layers | Actual built-in no-filter path, address-layer optimization, available layer vocabulary and endpoint-specific selection/fallback behavior; not an explicit layer list substitute |
| omitted_sources | Built-in no-filter selection and source aliases/availability/boost behavior tied to exact imports |
| no_override_language | Resolver/version, fixed no-override fallback, name/translation choice and data identity; effects on ordering/retrieval and labels explicitly stated |
| forbidden_injection | Verified absence of configured defaultParameters/proxy injection for layers/sources/lang/spatial/structured slots; no ambient locale, browser/IP/country/family overrides |
| search_behavior | Parsers, sanitizers, boosts, ranking/tie-break, dedup performed inside Pelias, fallback/coarse/interpolation behavior, query templates and backend call graph/configuration hashes |
| response_behavior | Extracted property mapping, schema/vocabularies, format/version and echo adapter; no omission/error reinterpretation |

The no_override_language subobject is additionally exposed as
effective_no_override_language_behavior_id using H with domain
SAFE:stage12-no-override-language:v1 and ordered fields behavior_version string,
language_core canonical JSON bytes. This is a sub-binding of effective_behavior_id,
not an alternative unknown/default language sentinel. Bind name-label changes
as result-affecting absent proof otherwise.

DeploymentCore required keys:

| Key | Required contents |
|---|---|
| schema_version | stage12_deployment_core_v1 |
| logical_deployment_name | Owner-approved stable logical name, never inferred from hostname |
| service_view_id | Nonsecret authorized routing/tenant/data-view identity |
| applications | API, proxy/gateway, microservices, plugins and search dependency code revisions plus immutable container/build/package-lock digests |
| result_configuration | Complete reviewed secret-free effective configuration projection and its schema/hash, including environment-derived result settings |
| routes | Exact endpoint-to-application/backend mapping, uniformity across load-balanced instances and attestation-header protocol/version |
| identity_enforcement | Immutable serving-generation control, drift-event counter behavior, maintenance exclusion and lease/attestation verifier version |

DeploymentCore transitively binds IndexCore and EffectiveBehaviorCore through
the [fingerprint formula](STAGE12_DATA_CONTRACT.md#deployment-index-and-effective-behavior).
The nonsecret transport envelope separately contains approved HTTPS origin,
TLS trust/pinning policy, approved network routes, manifest signature and
operator audit. Hostnames, certificate rotation and storage paths are not
immutable dataset identity. Route changes may keep the fingerprint only if
proved to serve the identical bound view; any result-affecting change creates
new identity. API keys and configuration files containing keys are never
copied, serialized or hashed. Projection completeness must be reviewed against
all application/configuration sources; merely redacting a few known names
does not establish completeness.

## Live binding and deployment-drift exclusion

Require a manifest-bound immutable serving generation plus an enforced
maintenance/read lease covering each authorized campaign segment. The operator
mechanism must prevent writes, alias/data-view changes, rolling code/config
updates and unbound backend routing while serving that generation. Expiry or
loss of identity visibility closes request admission. There is no automatic
fallback to a mutable server or another replica group.

Require a trusted SAFE gateway/service-side attestation on **every response**:
the manifest fingerprint and current serving generation/event counter, produced
from the actual routed backend, with an operator-authenticated verification
mechanism. These nonsecret response fields are audit, not request-side search
headers. A static client-supplied echoed value is insufficient. The exact
header names/verification envelope are frozen in the future operator manifest,
then verified by the public probe. This requirement may require a separately
authorized deployment change; no such change is made or assumed here.

Verify full signed binding at job start, resume and end; verify lease/generation
at least every **60 seconds or 100 completed responses, whichever comes first**,
and per response before accepting it. Control checks count toward the total
service connection/rate budget. Start/end equality alone cannot exclude an
intermediate change-and-revert: a monotonic durable maintenance-event counter
and enforced immutable generation must cover the entire interval, including
paused jobs and any adopted successful attempt.

On mismatch, unverified interval, lease loss, unannounced backend, alias change
or index drift: stop new dispatch immediately, drain/cancel bounded in-flight
work without promoting it, persist DEPLOYMENT_IDENTITY_FAILURE and quarantine
the **whole current candidate campaign**. No candidate seal; no mixed identity
merge. Previously immutable raw receipts remain evidence of the failed run.
This v1 contract permits no salvage from a drifted campaign into a final
candidate; a new binding/campaign requires owner review and authorization.
A lease can be renewed across jobs only with proof of continuous unchanged
serving generation and event counter. Identical manifest filenames are not proof.

## Authentication and privacy at the service

Read one nonempty key from the approved runtime secret provider/environment
variable SAFE_PELIAS_API_KEY only after startup guards. Reject CR/LF/header
injection bytes; never put the value in shell arguments, request URLs, hashes,
manifests, exception text, debug traces, telemetry or command examples. No
credential hash is retained. Runtime secret memory is not persisted; disable
core dumps and HTTP debug logging. Never enumerate or print environment values.

Missing secret is an ENVIRONMENT_AUTH_MISSING run failure before dispatch;
401/403 terminate the campaign with explicit authentication/authorization
reason. They are not zero results and do not trigger token guessing/rotation
loops. An explicitly repaired environment may resume only under separate
authorized recovery, same data view, remaining cumulative attempt budget and
full checkpoint/deployment gates.

Client, gateway and backend logging must suppress query strings, authorization
headers, request/response bodies and protected labels. Require operator evidence
of log/telemetry controls before protected execution. No arbitrary response
headers or error pages enter receipts; retain only allowlisted status/identity/
Retry-After data. Sanitize by construction; never depend solely on regex
redaction after a logging library has emitted the URL.

Raw **successful** responses are captured exactly only under an operator-verified
no-secret-echo contract. At ingestion a runtime-only exact-key presence guard
also blocks publication without persisting/printing a matching body or key.
Synthetic secret canaries test client/proxy/errors. This guard is supplementary,
not proof against every transformed secret leak. If a server violates the
no-echo contract, stop and preserve only static incident metadata.
Malformed/error/truncated bodies are not retained; they have no Stage 13
authority and could echo credentials. Never print parser exceptions with text.

## Result states and error taxonomy

request_execution uses terminal states SUCCESS_WITH_CANDIDATES,
SUCCESS_ZERO_CANDIDATES, TECHNICAL_FAILURE_FINAL, CONTRACT_FAILURE,
DEPLOYMENT_IDENTITY_FAILURE. TECHNICAL_FAILURE_RETRYABLE is an attempt/workspace
state only; after exhaustion it becomes TECHNICAL_FAILURE_FINAL. PENDING and
IN_FLIGHT are operational state, not final outcomes.

| Condition | Attempt handling / static reason |
|---|---|
| 200, complete valid schema, count >0 | SUCCESS_WITH_CANDIDATES / OK |
| 200, complete valid schema, count=0 | SUCCESS_ZERO_CANDIDATES / OK |
| Other 2xx, malformed expected fields, complete invalid JSON/UTF-8, excessive feature count, warning/error body | CONTRACT_FAILURE / RESPONSE_CONTRACT_INVALID; no retry |
| 401 | TECHNICAL_FAILURE_FINAL / AUTHENTICATION_FAILED; immediate global stop |
| 403 | TECHNICAL_FAILURE_FINAL / AUTHORIZATION_FAILED; immediate global stop |
| Other 4xx including 400/404/405/409/413/414/422 | CONTRACT_FAILURE / HTTP_REQUEST_REJECTED; no retry or changed parameters |
| 408, connect/read/overall timeout | TECHNICAL_FAILURE_RETRYABLE / TIMEOUT |
| 429 | TECHNICAL_FAILURE_RETRYABLE / RATE_LIMITED; global cooldown |
| 500/502/503/504 and other 5xx except below | TECHNICAL_FAILURE_RETRYABLE / SERVER_TRANSIENT |
| 501/505 | CONTRACT_FAILURE / UNSUPPORTED_PROTOCOL; no retry |
| Connection reset/refused, temporary route failure, DNS SERVFAIL/timeout | TECHNICAL_FAILURE_RETRYABLE / NETWORK_TRANSIENT |
| DNS NXDOMAIN, unapproved resolved route, TLS certificate/hostname/trust failure, TLS protocol incompatibility | TECHNICAL_FAILURE_FINAL / ENVIRONMENT_NETWORK_INVALID; global stop |
| Early EOF/chunk/content-length mismatch before complete body | TECHNICAL_FAILURE_RETRYABLE / RESPONSE_TRUNCATED |
| Complete body with invalid JSON, even if it looks truncated | CONTRACT_FAILURE / RESPONSE_CONTRACT_INVALID; no guessed transport reclassification |
| 3xx | CONTRACT_FAILURE / REDIRECT_FORBIDDEN; no follow |
| Response exceeds byte/depth/parser resource cap | CONTRACT_FAILURE / RESPONSE_RESOURCE_LIMIT; no truncation accepted |
| Secret absent, local storage/site guard fails | No fabricated HTTP attempt; static environment/resource run failure |
| Identity/lease drift or unverifiable attestation | DEPLOYMENT_IDENTITY_FAILURE; immediate global stop, no retry |
| Exhausted retryable attempts | TECHNICAL_FAILURE_FINAL / RETRY_BUDGET_EXHAUSTED |

All failure states have no candidate rows and null candidate_count, never
valid-zero semantics. A contract/identity failure stops the campaign for review;
continuing the unaffected subset cannot yield an accepted candidate. A stopped
run preserves exact planned/completed/unprocessed sets in controlled workspace;
unprocessed is not an invented terminal HTTP result. Final candidate publication
requires full totality, so no ambiguous partially populated outcome ledger passes.

## Deterministic bounded retry and service protection

Proposed conservative initial operations policy, to be validated on public
synthetic fixtures/probe before any increase:

- **Five attempts total** per execution across the campaign and its resumes.
  Library retries off. Retry only conditions marked retryable above.
- Connect timeout **10 seconds**, read-idle **30 seconds**, whole attempt
  **60 seconds** including connect/body; monotonic deadlines. Identity checks
  have 10-second deadline and no requests admitted on identity uncertainty.
- Before attempts 2..5, base waits **2, 4, 8, 16 seconds**. No random jitter.
  Apply deterministic extra spacing of 0..999 ms from the first two bytes of
  SHA256(domain SAFE:stage12-retry-spacing:v1, framed execution ID and next
  attempt number), reduced modulo 1000. This is audit scheduling, not science.
- Valid Retry-After delta-seconds or HTTP-date is honored using response Date
  (or receipt UTC when Date absent); use max(base+spacing, requested delay).
  A negative past date means zero; malformed header gives base wait. If delay
  exceeds **300 seconds**, stop/pause the campaign for owner recovery rather
  than retry earlier. Persist parsed delay only, not raw headers.
- On 429 or any retryable 5xx, stop new admission for at least 30 seconds or
  the larger Retry-After. Retry queues share the same rate limiter.
- Start concurrency **2 total**, connection pool **2** to one approved host,
  one HTTP/1.1 active request per connection, no overflow. Hard ceiling **4
  total across the entire campaign**, including control checks, retries and
  multiple jobs/processes. A single coordinator holds the serving lease; no
  duplicate jobs/shards with separate budgets.
- Initial token bucket **1 request/second, capacity 1** (no burst). Reviewed
  public measurements may authorize up to 2 requests/second and 4 connections;
  never autotune upward during DEVELOPMENT. Concurrency can only decrease
  under backpressure. Bound pending queue at twice concurrency.
- Circuit breaker opens on **3 consecutive retryable technical errors**, or
  **at least 5 in the last 20 completed attempts**, or **2 overload responses
  (429/503) in any 60 seconds**. At 20 attempts, if at least 10 exceed 30 seconds,
  stop for latency pressure. Auth/contract/identity failures open immediately.
  These are conservative protection limits, not empirically asserted service
  capacity or scientific quality thresholds.
- Open breaker stops dispatch and automatic half-open recovery. Preserve
  checkpoints and report sanitized reasons. A later explicitly authorized
  bounded public health check and recovery may reuse remaining attempts; no
  unattended storm, infinite retry, automatic SLURM resubmission or budget reset.

Successful response science depends on frozen execution identity, not which
attempt succeeded. Timestamps/latency and operations-policy hash remain receipts.
If service load changes ordering in repeated probes, reduced concurrency alone
does not prove equivalence: investigate and freeze behavior before DEVELOPMENT.

## Durable streaming, limits and restart

The run streams Stage 11 requests sorted by full semantic ID, scheduled without
family preference. Query hashing/URL construction supports streaming giant
strings up to the verified transport cap; never truncate to fit. Proposed
response ceiling is **16 MiB uncompressed per response**, JSON nesting **64**,
input Arrow batches **8 MiB target**, and at most **2 x concurrency** pending
requests. These are resource guards; any valid input that cannot fit produces
an explicit failure blocking complete publication. Changing them needs reviewed
operations evidence, not silent data removal. Implementation must measure actual
parser memory expansion and enforce a byte/memory reservation before dispatch.

Use seekable packs of independent zstd frames, one exact body per frame, codec
and version recorded; compression level 3 initially. Cap each pack at 64 MiB
compressed or 256 responses, flushing earlier for durability. Hash uncompressed
body for science and complete compressed pack for physical inventory. Use
streaming write/decode and bounded Arrow Parquet batches; query and feature
strings are never accumulated for the population. Partial frames are invisible
to adopted receipts. During capture use small durable per-response fragments;
pack/compact only fully sealed successes with verify-copy-fsync-reopen. Preserve
old fragments until the new checkpoint manifest is sealed; no hardlink adoption.
A final immutable packed artifact may change offsets/compression without
changing scientific projection digests.

Durability transaction per dispatched attempt:

1. Under the sole coordinator, persist/fsync an exclusive attempt-begin receipt
   with execution/binding/ordinal, then send. A crash after begin consumes the
   attempt even if dispatch is uncertain.
2. Stream complete body, verify identity/secret/schema, derive all candidates
   together, hash and write private durable fragments. fsync files and parent.
3. Write exclusive receipt inventory with exact byte/schema hashes, attempt
   finish and whole-response outcome; reopen every referenced fragment.
4. Create the empty exclusive checkpoint seal and fsync its directory. Only a
   fully reopened sealed receipt marks the execution complete. No candidate
   becomes visible from a partial response or local database transaction alone.

Checkpoint keys include full execution identity, accepted Stage 11 input
binding, full executable/runtime inventory, operations policy, campaign ID and
attempt budget history. Adoption verifies all of these and the same deployment/
index/generation continuity, selected raw byte hashes, extracted row equality
and rank/FK/count invariants. Request order, worker, job/path and packing may
change without changing scientific identities; a changed executable needs
separate reviewed migration/equivalence authorization, never automatic adoption.

Resume occurs only inside a new authorized job, with a new final publication
reservation and a manifest-bound list of immutable adopted units. Rebuild
transient indexes from durable receipts after local loss. Never steal an old
reservation, modify a failed run, assume expired worker ownership or treat a
local cache hit as authority. Recover fully sealed valid success rather than
send it again. Do not rerun Stage 11 dedup or dedup by URL.

An unsealed attempt is UNKNOWN_DELIVERY and counts against five; its response
cannot be adopted. A bounded retry may repeat a network request whose earlier
delivery is unknown. **Exactly-once network delivery cannot be guaranteed**
without server transaction support; the promise is at most one selected durable
scientific response per execution. If two independently sealed successes with
different bodies are found for one execution, fail an integrity check, not
first/last-writer-wins. Concurrency/race and power-loss fault tests must verify
this before any protected run. Preserve failures and report only static codes.

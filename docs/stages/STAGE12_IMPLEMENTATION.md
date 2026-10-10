# Stage 12 implementation session — incomplete draft, stopped before probe

2026-10-10. This is an implementation-session record, not owner acceptance,
execution evidence, a design amendment or permission for a service call.
The five frozen design documents remain byte-identical. C, T and N remain
UNSELECTED. Protected calibration and Stage 13 have not started.

## Precheck and authority

The owner authorized implementation, synthetic validation and one bounded
public/synthetic SAFE probe, explicitly excluding protected DEVELOPMENT,
HOLDOUT and production. Fetch/prune/tags succeeded. Clean main, origin/main and
the peeled design-freeze tag all matched
7543b8bac4f2953aab311fb58f73dbcb62ba401b. The owner-reviewed design and normal
merge are ancestors. No active Git operation or existing tracked Stage 12
implementation was found. All five frozen document hashes and the tracked,
sanitized accepted Stage 11 manifest hash matched the freeze record.

Branch: impl/stage12-pelias-retrieval, created from that exact main. Draft files
are uncommitted. No implementation SHA or reporting SHA exists; nothing was
pushed or merged. Accepted Stages 0–11 and their scientific assets remain
unchanged. HOLDOUT sealing and production non-access are preserved through
non-access, not inspection of their contents.

## Mandatory stop: retry ambiguity

The [frozen retry rule](STAGE12_EXECUTION_CONTRACT.md#deterministic-bounded-retry-and-service-protection)
states: "or receipt UTC when Date absent" and "malformed header gives base wait".
For a valid HTTP-date Retry-After accompanied by a present but malformed Date,
the text does not explicitly distinguish a malformed Date from a malformed
Retry-After. Receipt-UTC fallback, base wait and fail-closed recovery are
different operational choices. The draft helper currently falls back to
receipt UTC; that choice has **not** been approved and must not be treated as
frozen behavior.

The owner's session instruction requires stopping before probing when retry
rules are ambiguous. An explicit false clearance gate in the probe entry point
prevents dispatch while this issue and the remaining implementation gates are
unresolved. There is no CLI or environment override. The frozen documents were
not edited to resolve the issue silently.

Two additional probe inputs remain unavailable:

- The approved SAFE HTTPS origin, operator configuration/routing evidence,
  and authoritative Goethe runtime secret-provider setup. No secret was read,
  printed or requested in chat.
- Operator-documented safe sizes above 10 and their exact approved probe ladder.
  The [frozen public-probe gate](STAGE12_DEVELOPMENT_CALIBRATION.md#publicsynthetic-deployment-probe)
  requires this evidence before calls. It also specifies 64 cases and 512 base
  calls, with up to 64 deeper-size calls and 16 additional checks. The owner's
  wording "very small" prompted a scope clarification; no smaller replacement
  workload has been silently substituted.

## Draft implementation and evidence

The draft includes the 17 named canonical descriptor objects, four-relation
schemas, separated policy/network/projection/attempt identities, materialization,
raw-byte parsing and feature slices, offline extraction, zstd fragments, a
bounded pack writer, deployment/authenticity/drift interfaces, attempt/rate/
breaker rules, private checkpoints, campaign/segment primitives, a Stage 12
publication adapter and a disabled public-probe harness/launcher.

These are **incomplete implementation candidates**, not a validated complete
Stage 12 runtime. In particular, primitive-level campaign/publication tests
do not establish a complete protected retrieval orchestration implementation.
No deployment capabilities, immutable index identities or authentication
acceptance have been observed on the real service.

Validation performed before the stop:

- Initial full safe suite on Python 3.14.7: 1,484 passed, 29 failed, 24 skipped.
  The failures were historical exact-runtime guards, not waived or modified.
- Full safe suite in the existing pinned Python 3.14.3 environment: 1,513
  passed, 24 optional ICU tests skipped. This preceded the last added tests.
- First focused contracts/response/operations/recovery tests: 170 passed.
- Subsequently added synthetic four-relation end-to-end and loopback HTTP
  tests: 18 passed. They cover clean/resumed/reordered scientific equality,
  publication/reopen/replay, exact HTTP bytes, transfer decoding, truncation,
  redirect rejection and synthetic secret-echo rejection.
- Source mypy and maintained-tree Ruff checks passed at intermediate checkpoints.
  All frozen document hashes and 17 generated descriptor bytes were verified.

Counts above are observed command results; they are not claimed to cover
subsequent untested edits. Final full-suite/static/documentation validation,
the public-harness synthetic run and bounded implementation review closure
remain required before an implementation commit or probe submission.

## Implementation defect and remaining-work ledger

| ID | Finding | Disposition |
|---|---|---|
| I01 | Local default Python violated historical exact-runtime guards | Resolved for the recorded full-suite run by using existing Python 3.14.3; no guard changed. |
| I02 | Initial new-source type narrowing and execution-guard call signatures were incomplete | Corrected; source mypy passed at the recorded checkpoint. |
| I03 | Initial parser applied top-level warning rules to unknown feature fields | Corrected: top/geocoding message rules are separate from feature bbox/CRS validation. |
| I04 | Checkpoint capture context was not explicitly reconciled to execution/attempt metadata | Added exact binding/status/media/encoding/length/hash reconciliation and external receipt/closure pins. |
| I05 | Whole-attempt deadline could lose the socket reference after HTTP connection-close handling | Retained the active socket independently. A targeted whole-deadline slow-transfer test remains required. |
| I06 | Valid HTTP-date Retry-After plus malformed response Date has an unapproved fallback | **OPEN — mandatory stop before probe; owner clarification required.** |
| I07 | Public capability parser initially omitted optional-field/envelope type checks | Checks added; public-harness end-to-end/failure tests remain required. Deployment vocabulary and echo attestation remain separate gates. |
| I08 | Public reporting could retain ordered latency arrays and receipt failure could obscure the main outcome | Draft changed to aggregate summaries and preserve a primary failure; focused harness tests remain required. |
| I09 | Measured parser expansion and admission-time memory reservation are not complete | **OPEN — required implementation/resource validation before probing.** |
| I10 | Raw pack compaction has no completed dedicated fault/reopen test coverage | **OPEN — validate independent-frame bounds, interrupted compaction and source-fragment preservation.** |
| I11 | Complete campaign-wide attempt/integrity enforcement and scientific dataset assembly need further integration review | **OPEN — primitive tests are insufficient evidence of complete runtime correctness.** |
| I12 | Probe endpoints, operator identity evidence, auth source and deeper-size approvals unavailable | **OPEN external inputs — do not guess or submit.** |
| I13 | Final static/schema/privacy/docs/shell checks and complete bounded self-review are unfinished | **OPEN — no implementation-ready claim or commit.** |

## Execution and privacy status

SLURM submissions = 0. Real SAFE Pelias requests = 0. Protected network
requests = 0. Protected DEVELOPMENT payload reads = 0. HOLDOUT access = 0.
Production access = 0. Secret leakage = 0. External non-SAFE geocoder/API
calls = 0. Local HTTP tests used loopback and invented secret canaries only.

No probe failed or completed: none was submitted. There is consequently no
probe job ID, implementation SHA, reporting SHA, tested live result-size set,
live latency evidence, or basis for protected C/T/operations recommendations.

C = UNSELECTED. T = UNSELECTED. N = UNSELECTED.

Next: resolve the retry-policy ambiguity and missing probe inputs, complete the
remaining offline implementation/validation gates, then commit/push and submit
only the separately ready, exact authorized public workload. No protected
DEVELOPMENT retrieval follows automatically.

## Owner operational clarification — 2026-10-10 (append-only)

The owner resolved I06 after the preceding stop. For a syntactically valid
HTTP-date Retry-After with missing, malformed or unreliable response Date,
use client response-receipt UTC. The requested delay is max(0, target minus
receipt); the effective wait remains max(base plus deterministic spacing,
requested delay). Above 300 seconds still stops for owner recovery. Invalid
Retry-After itself still uses the base wait. Audit records contain the parsed
delay, reference-clock enum, Date usability enum and receipt UTC, never raw
headers. This does not change scientific identities or the design-freeze tag.

The owner separately clarified that sizes 1, 3, 5 and 10 may proceed without
operator documentation for sizes above 10. Any deeper size still needs explicit
controlled safe-bound evidence before dispatch. An empty deeper ladder reports
ABOVE10_SAFE_SIZE_NOT_YET_OPERATOR_VERIFIED, not probe failure; protected
calibration remains blocked pending safe T>10 capability. The frozen 64 public/
synthetic cases, two repetitions and base call budget remain unchanged.

Continuation checks: main, origin/main and the peeled frozen tag still equal
the accepted SHA above. There is no checked-in approved SAFE origin. Local
standard dotenv files are absent and no Pelias runtime variable is configured.
A read-only shell check through the project-configured Goethe SSH alias found
no standard project dotenv/config/configuration or Stage 12 probe-configuration
path, and no nonempty login-environment SAFE_PELIAS_API_KEY. No credential value
was printed or copied. This is not evidence that no other operator-managed
provider exists. Its controlled reference is required before service contact.

## Continuation implementation and validation closure

The initial sections above preserve the previous stopped draft and its observed
results. They are historical. The owner-authorized continuation resolves the
implementation findings as follows; it does not claim any live service evidence.

| ID | Continuation disposition |
|---|---|
| I01–I04 | Resolved; pinned Python retained, typing corrected, response validation and capture bindings covered by regression tests. |
| I05 | Resolved; a loopback slow-transfer test verifies the whole-attempt deadline even after connection-close handling. |
| I06 | Resolved by the owner clarification above. Delta-seconds, valid/missing/unusable Date, past dates, both max-wait orderings, invalid Retry-After, over-cap recovery and identity exclusion are explicitly tested. Clock provenance is a separately inventoried receipt, outside the frozen four-relation schema and scientific IDs. |
| I07 | Resolved; the complete mocked public harness covers both paths and 512 base calls, repeated observations, raw replay, prefixes and fatal response/auth/privacy failures. Verified deployment vocabularies/echo behavior remain external gates. |
| I08 | Resolved; portable timing/count/byte data are aggregated. Report-write failure preserves the primary failure; uncertain dispatch is distinguished from a confirmed capture. |
| I09 | Resolved for implementation validation; the reproducible synthetic parser/replay measurement has maximum observed ceiling ratio 85. Admission reserves 128 times the 16 MiB response ceiling per request, within a shared 4 GiB budget, with 6 GiB proposed job memory. This is measured synthetic evidence, not proof of every deployment response or live resource use. |
| I10 | Resolved; independent frames, pack bounds, exact replay, codec-provider version, source preservation, corrupt inputs and interrupted sealing are tested. |
| I11 | Resolved for the authorized runtime architecture; verified cumulative history consumes UNKNOWN_DELIVERY, forbids gaps/duplicate success/post-terminal dispatch, and checks exact campaign/executable bindings. Streamed four-relation assembly, full PK/FK/rank/count validation, packed raw replay, publication and complete reopen are tested. Actual protected orchestration remains gated by owner-frozen policies, workload preflight and authorization. |
| I12 | External blocker remains: approved origin/routing, deployed authentication and compute-job secret-provider reference are unavailable. The additional controlled user configuration paths checked on Goethe were also absent. Deeper-size evidence is no longer a prerequisite for the <=10 probe; it remains mandatory before >10 calls and protected T selection. |
| I13 | Final network-free validation and bounded self-review are recorded below. No main merge or probe submission is implied. |
| I14 | Self-review found malformed Content-Length could be treated as an EOF-delimited body. Fixed: invalid/ambiguous lengths fail the whole response; declared oversized bodies fail before collection. Regression tests cover four invalid forms. |
| I15 | Self-review found unexpected dispatch exceptions could leave admission memory reserved. Fixed: fail-closed cleanup releases the reservation without masking the primary exception; durable UNKNOWN_DELIVERY remains. |
| I16 | Self-review found final relation checks alone would not re-extract every packed frame. Added full artifact reopen, exact frame hash/decompression and candidate equality before publication sealing and after reopen. |

The bounded review also checked scientific/audit identity separation, signature
exclusion from manifest content identity, secret handling, strict transport,
raw-byte preservation, global retry/rate/memory admission and immutable storage.
No known implementation defect remains open from this review. Operator-backed
manifest completeness, authenticity, routing, immutable content and drift
attestations remain explicit external verification interfaces; a hash or a
successful HTTP response cannot establish those facts by itself.

The single retrieval-policy row uses canonical JSON physically because Parquet
cannot represent an empty list-of-empty-struct type. Its logical Arrow schema,
field order, empty options and scientific row digest are unchanged. Candidates,
executions and attempts use schema-checked Parquet. This is a storage choice,
not a new relation or scientific policy.

The implementation clearance constant now permits entry to the public harness.
It is not network authorization by itself: the Goethe/SLURM guard, exact clean
executable, approved private configuration, explicit X-API-Key attestation,
secret presence, fixed public fixture and bounded operations still gate entry.
Runtime package/Python/OpenSSL inventory and operations fingerprints are separate
provenance; they do not enter request_execution_id.

### Validation commands and results

Use the existing pinned local Python 3.14.3 environment for the full safe suite.
No protected input path or query payload is a validation input.

- Focused Stage 12 suite: final count recorded in the sanitized validation JSON.
- Full safe suite: 1,574 passed, 24 pre-existing optional exact-ICU skips at the
  first continuation full-suite checkpoint; final post-review count is recorded
  in the validation JSON.
- mypy: PASS, 149 source files. Ruff: PASS across src, tests and scripts.
- Stage 10 implementation inventory, Stage 11 design/schema/encoding and stage
  report/local-link validators: PASS.
- Stage 12 validator: 17 canonical named contract descriptors, four logical
  relations, five unchanged frozen documents, 64 public/synthetic cases: PASS.
- All maintained shell/SBATCH assets pass bash syntax validation.
- Stage 12 source/asset file-surface check, no changed accepted tracked files,
  private synthetic artifact tests and Git diff whitespace check: PASS.
- [Synthetic parser measurement](../scientific_assets/stage12_synthetic_parser_measurement.json)
  is reproducible using scripts/validate_stage12_implementation.py --measure-synthetic.

### Exact remaining public-probe configuration gate

No service request and no SLURM job has been submitted. The approved SAFE
origin cannot be established from the controlled sources inspected. Authentication
is still **proposed X-API-Key, unverified on the deployment**; no credential
value has been read back, printed, committed or requested in chat.

Required non-secret operator information/setup:

1. A controlled operator/runtime configuration reference establishing exactly
   one approved HTTPS origin, its authorized IP/routing and TLS/data-view mapping,
   request-target/header limits and the contact/privacy preflight evidence.
2. Confirmation of the deployed authentication mechanism. For the implemented
   X-API-Key path, configure a protected provider that makes a nonempty
   SAFE_PELIAS_API_KEY available to the single compute job. Supply the provider
   reference/category only; never put the value in chat, Git or job arguments.
3. Place the approved, private public-probe configuration in the controlled
   Stage 12 probe_configuration directory. Its exact schema is CONFIG_KEYS in
   stage12_probe_cli.py. For a base-only probe use deeper_sizes=[],
   operator_max_size=10 and operator_size_evidence_sha256=null. Bind the workload
   authorization and operator configuration evidence by full SHA-256.
4. Submit exactly one bounded job from the pushed immutable implementation SHA
   only after these inputs pass. No automatic submission retry is implemented.

The base-only workload is 64 manually authored/public cases, both modes,
1/3/5/10, two observations each: 512 planned calls, maximum 2,560 attempts;
breakers and walltime commonly stop earlier. Initial policy is 1 request/second,
maximum two connections; the public harness dispatches serially, so observed
parallelism would be one. Proposed allocation: one CPU, 6 GiB, 30 minutes,
no job-local storage. These are planned values, not live measurements.

ABOVE10_SAFE_SIZE_NOT_YET_OPERATOR_VERIFIED.
PROTECTED CALIBRATION BLOCKED PENDING SAFE T>10 CAPABILITY.

Protected DEVELOPMENT payload reads/network requests = 0; HOLDOUT access = 0;
production access = 0; secret leakage = 0; external non-SAFE geocoder/API calls
= 0. Stages 0–11 and the Stage 12 design freeze remain unchanged. C, T and N
remain UNSELECTED. Protected calibration and Stage 13 have not started.

### Final observed offline validation

The final post-review run passed **232 Stage 12 tests** and **1,575 full safe
suite tests**, with the same **24 pre-existing optional ICU skips**. Final mypy,
Ruff, new-file formatting, contract/schema, preserved Stage 10/11 assets,
documentation/local links, shell/SBATCH and whitespace checks passed.
The [sanitized validation record](../scientific_assets/stage12_implementation_validation_v1.json)
contains the exact aggregate results and ledger closure. There was no probe
submission, live authentication test or deployment/result-size observation.

## Owner-authorized private-file provider and initial probe — 2026-10-10

The owner resolved the origin/authentication/provider blockers in this same
session: approved origin https://geocode.safe-frankfurt.de; X-API-Key; private
Goethe file $HOME/.config/safe-geocoding/pelias_api_key. This is an operations-only
provider clarification, not a change to the frozen science or design tag.
Only sizes 1, 3, 5 and 10 are authorized for this submission. No >10 test,
protected DEVELOPMENT payload access, HOLDOUT, production or Stage 13 is allowed.

Read-only Goethe preflight confirmed a regular, readable, nonempty file owned by
the executing UID, mode 0600, one link; its parent is owner-owned mode 0700.
No file contents were printed, copied, hashed or placed in shell variables.
The approved hostname resolved through Goethe's resolver to 159.69.61.56.
The probe configuration pins that numeric route; TLS still verifies the exact
approved hostname with the runtime trust store. This route observation does not
establish scientific deployment or immutable index identity.

The adapter uses SAFE_PELIAS_API_KEY_FILE. Only the scheduled Python process
reads the file directly into memory. It rejects symlinks, hardlinks, nonregular
files, wrong ownership, unsafe permissions, changes during reading, empty or
invalid content and ambiguous simultaneous providers. One terminal LF or CRLF
is permitted for text-file provisioning; header-injection bytes remain rejected.
The launcher exports only the path and unsets the legacy value environment
variable. The secret never enters a hash, persisted audit, command argument or
report. Existing semantic, policy, execution and projection identities remain
unchanged. The exact new Git SHA remains required executable provenance.

During synthetic validation one test caught a static FILE_CHANGED error being
collapsed into FILE_INVALID by the general ValueError handler; the dedicated
Stage12Error path now preserves the sanitized specific code. No live request
was involved. Dedicated tests cover the provider boundaries and the complete
mock public harness with file-provider audit reporting.

Final adapter validation: **256 focused Stage 12 tests PASS**; **1,599 full safe
suite tests PASS**, with **24 pre-existing optional ICU skips**. Mypy (149 source
files), Ruff, canonical contract/schema verification, documentation/local links,
all shell/SBATCH syntax and diff whitespace checks PASS. All 17 named descriptors
and five frozen design documents remain byte-identical to the prior implementation.
See the [provider validation record](../scientific_assets/stage12_file_provider_validation_v1.json)
and [sanitized owner authorization](../scientific_assets/stage12_public_probe_owner_authorization_v1.json).
No job was submitted and no real service request was sent during these checks.

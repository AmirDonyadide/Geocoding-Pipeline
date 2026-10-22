# Stage 12 public capture-audit repair

**IMPLEMENTED / PENDING INDEPENDENT REVIEW.** This is a prospective, offline
implementation candidate under the owner's separately bounded repair authority.
It neither independently closes nor waives the defect. No execution, contract
amendment, successor activation, scientific publication or Stage 12 acceptance
is authorized. C, T and N remain UNSELECTED. Job 1792588 remains FAILED.

Starting branch: `impl/stage12-pelias-retrieval`; base HEAD:
`63f8fc769658656ec4eeef800d52c3091cc92ace`. The starting tree contained exactly
the five untracked, independently reviewed warning-policy files and no tracked
changes. Those five files remain byte-identical; they are not included in HEAD.

## Defect and frozen requirements

The public harness computed the application-payload hash and verified its
compression round trip, but left that hash only in memory. Its transport finish
receipt could still say VALIDATION_REQUIRED after a response was rejected.
It lacked the linked, durable per-attempt raw/validation/outcome inventory.

| Requirement / field or transition | Governing frozen provision | Prospective implementation |
|---|---|---|
| Begin before dispatch; call/attempt/request association | [Execution contract](STAGE12_EXECUTION_CONTRACT.md), durability step 1; [data contract](STAGE12_DATA_CONTRACT.md), request_attempt journal provisions | Existing call/attempt/fixture/size/repetition/target hash plus run-provenance, workload, materialization and validation hashes; UTC start. Exclusive write/fsync before dispatch. |
| Complete decoded application bytes and SHA-256 before parsing | Data contract, Attempts and observed responses; execution durability step 2 | Safe complete 2xx bytes are hashed, stored as an independent zstd frame, read back and decompressed against the application-byte hash. Capture metadata persists the hash, application length, raw locator, completeness and sanitized status/media/encoding. |
| Failed 2xx evidence retained; secret/error-fragment restrictions | Execution contract, complete decoded payload/privacy provisions and result taxonomy | Complete malformed/warning/non-200 2xx payloads remain controlled failure evidence. Missing/partial/auth-error payloads have no invented hash. Synthetic secret-canary rejection stores only static incident metadata, no payload or payload hash. |
| Applicable validation binding and outcome | Data contract, complete-response validation and request_attempt fields; execution result taxonomy | Save exact frozen v1 descriptor bytes. Begin, validation-start and terminal records link their SHA-256. Save whether validation ran, its nullable outcome, existing attempt outcome/reason and nullable candidate count. Failure is never valid zero. |
| Exclusive inventory, full reopen and seal | Execution durability steps 3–4; existing `stage12_attempt_receipt_v1` protocol | Inventory every linked fragment/context file by exact byte length/SHA-256; reconcile associations and replay public v1 checks before and after the exclusive empty seal. Only then increment completed-audit counts or allow existing next-dispatch logic. |
| No implicit recovery or historical rewrite | Execution Resume provisions; data contract original-attempt immutability | New run reservation only; original begin/transport receipts never overwritten. Partial attempts cannot pass sealed reopen. No new resume/adoption API or retry policy. |

## Minimal implementation scope

Only the public CLI is changed. A new
[public audit helper](../../src/safe_geocoding_pipeline/preprocessing/stages/s12_public_audit.py)
uses the unchanged `s12_storage` exclusive/private write, fsync, canonical
metadata and file-inventory primitives. It does not alter the scientific
four-relation schemas or require invented deployment-bound IDs to instantiate
`request_attempt`. Its explicit scope is
`PUBLIC_CAPABILITY_AUDIT_NOT_SCIENTIFIC_CHECKPOINT`; the existing attempt-receipt
version references the reused durability protocol, not a scientific relation row.

The public validator remains the unchanged `stage12_probe_cli.public_shapes`
with the existing status/count/media/encoding checks. Its recorded scope is
`PUBLIC_SHAPE_ONLY_DEPLOYMENT_VOCABULARY_AND_ECHO_UNVERIFIED`. A public success
does not claim deployment-vocabulary/echo attestation or full scientific
extraction. No successor import or warning exception is introduced. The exact
address-layer warning still yields CONTRACT_FAILURE / RESPONSE_CONTRACT_INVALID.

For each new `call_NNNN_attempt_M`, the sequence is:

1. Write `_begin.json` exclusively; dispatch only after it is durable.
2. Write the existing `_finish.json` transport receipt, adding transfer-byte
   accounting and receipt UTC. Its original transport outcome remains intact.
3. Apply the existing privacy guard. For a complete safe payload write `.zst`,
   verify the round trip and write `_capture.json`; otherwise capture is null.
4. For retained bytes write `_validation_begin.json`, then perform public v1
   validation. Write the separate `_validation.json` terminal audit. A skipped
   validator is recorded as `validation_performed=false`, `validation_outcome=null`.
5. Write `_receipt.json` with exact physical inventory, reopen all referenced
   bytes and reconcile/replay the outcome, create `_SEALED`, then fully reopen
   again. The seal attests public audit completeness, not scientific publication.

Run context consists of the existing provenance/runtime/workload files plus
saved public fixture, request-materialization and v1 validation descriptors.
The run-provenance hash is an operational linkage, not a fabricated campaign or
scientific execution ID. Raw SHA-256 and compressed-file SHA-256 remain distinct.
No transport receipt is rewritten. No historical hash or capture-time claim is
backfilled. No candidates, execution IDs or projection IDs are fabricated.

Compression, capture, validation interruption, inventory or fsync failures leave
the attempt incomplete and stop dispatch. Already written evidence is preserved.
A known transport/validation failure remains primary if writing its audit fails;
the report also marks the evidence failure. Retryable attempts retain their
existing intermediate outcome and are audited before the unchanged bounded
retry/circuit-breaker logic runs. No automatic resubmission is added.

## Offline validation

[Focused repair tests](../../tests/test_stage12_public_audit.py): **55 PASS**.
These use invented payloads, injected transport and private temporary directories;
socket connection, bind, send and DNS operations are forbidden. They cover
success/zero; exact v1 warning rejection; malformed JSON/features/count overflow;
complete failed 2xx; no-payload failures; retry association and the existing
three-timeout circuit breaker; missing/corrupted context; physical inventory
tampering; compression/reopen/write/fsync faults; interruptions between all
capture/validation/inventory phases; no overwrite/resume/continued dispatch;
secret-canary non-retention; and preservation of primary errors.

Final relevant Stage 12 regression: **451 PASS, zero failures/skips**; the
23 transport tests were excluded. This includes the 55 repair tests and 163
unchanged supplied successor tests. Ruff/formatting on changed Python files and
strict mypy on both implementation files pass. The existing Stage 12 validator
passes all 17 frozen descriptors, five frozen design documents, four relations,
64 unchanged public fixtures, file/privacy surface and shell/SBATCH checks.
Tracked/staged whitespace checks pass. The exact commands and source hash
manifest are retained in the ignored local
`artifacts/stage12_public_capture_audit_repair_20261011/` evidence directory.
Network-dependent transport tests are excluded. This task does not claim an
unqualified full-repository-suite pass or repeat the completed independent
warning-policy adversarial review. Supplied warning-policy tests are regression
coverage only. No dependencies were installed.

Bounded implementation checks corrected preservation of a known transport
failure when its transport receipt write fails, and made reopened terminal
comparisons distinguish JSON booleans from integers even if a physical inventory
is recomputed. Both corrections have focused synthetic regression coverage.
No unresolved implementation defect was found in this bounded self-check;
independent review remains outstanding. This is not a new independent review
of the inactive warning-policy component.

## Preservation of completed review evidence

The available original review source was
`/var/folders/_0/9rntt48n39dblyvcwhpkl9gw0000gn/T/stage12-warning-independent-review-a4d8alv3/`.
Sixteen explicitly selected files were copied, without overwrite, into the durable
ignored local directory
`artifacts/review_evidence/stage12_warning_policy_independent_63f8fc769658_20261011/`.
The archive includes COMMANDS.md, review-results.json, both snapshot manifests,
the original reviewer test/harness, collection/safety records and test logs/XML.
Source and destination SHA-256 values match for every copy; no selected artifact
was unavailable. Temporary test trees and mypy caches were not bulk-copied.
The invalid reviewer-harness logs remain labeled historical invalid-run evidence.

The archive manifest SHA-256 is
`1d83b8bc874bab04f578d2983d80c2cd7d8ad7fa8bb2d78e31aac59757a692c9`.
Archival does not rerun, upgrade or modify the independent review.

## Remaining gates

Independent review of this repair is still required. The warning amendment,
real deployment/index/effective/echo/layer bindings, successor activation and
any later probe need separate decisions/authorization. No contract text,
request/fixture/header/retry policy, protected path, historical receipt or
job 1792588 outcome changed. No network, SSH, jobs, protected inputs, HOLDOUT,
production, real secrets, commit/push/merge/tag, scientific publication or Stage 13 work
occurred. This repair supplies no retrospective capture-time attestation.

## Targeted P2 correction — 2026-10-12

**P2 FIX IMPLEMENTED / PENDING FOCUSED INDEPENDENT RE-REVIEW.**
The preceding implementation results remain historical. Independent review R01
found one P2 defect, reproduced by two cases: an initial saved-context read
failure replaced a known AUTHENTICATION_FAILED or TIMEOUT with
S12_PRIVATE_FILE_INVALID and omitted the evidence-write failure flag. Dispatch
already stopped and the original transport receipt survived. The failed review
and its original tests remain unchanged in
`artifacts/review_evidence/stage12_public_capture_audit_independent_63f8fc769658_20261011/`.

The correction places the initial `_context()` call inside an error-preservation
boundary. The public CLI passes only its already-known sanitized transport
failure reason through a new optional helper argument. This four-line caller
addition is necessary: the old helper arguments contain neither that outcome
nor its reason, and unreadable/unverified saved context cannot supply them.
The argument is used only to preserve failure precedence if context verification
raises; it never substitutes for context or permits capture, validation or
completion. The existing AuditWriteError/report handling preserves the primary
reason and marks `evidence_write_status=FAILED`. With no known primary transport
failure, the original context/harness exception path remains unchanged. No
raw secondary exception message is added to the report.

Only the audit helper, that narrow CLI call site, permanent repair tests and
this additive report section change. There is no schema, outcome, validation,
request, fixture, header, retry, successor or frozen-contract change. Existing
transport evidence remains intact; context failure leaves one incomplete
attempt, no capture/hash/validation/inventory/seal, and no next dispatch.

Post-correction offline evidence:

- Both original independent reproductions: **2 FAIL before → 2 PASS after**,
  with their test source and expectations unchanged. Saved reports independently
  confirm both original missing flags and both corrected failure reasons/flags.
- Six permanent CLI regression cases: **6 PASS**, covering authentication,
  timeout and no-primary controls with both static context and I/O exceptions.
  They assert byte-preserved transport receipts, failure precedence, one
  incomplete attempt, no retry/next dispatch, no fabricated capture or validation,
  and no synthetic exception sentinel in persisted output.
- Complete public-audit module: **61 PASS**, included in the selected Stage 12
  offline regression: **457 PASS**, zero skips/failures/errors. Normal success,
  zero-candidate, transport-failure and frozen-v1 warning rejection remain covered.
  All 23 transport-module tests are excluded; supplied successor tests are
  regression coverage only. No independent review campaign was repeated.
- Ruff/formatting for three changed Python files, strict mypy for both changed
  implementation files, frozen-asset/privacy/shell validation and whitespace
  checks pass. The earlier 1,794-pass restricted repository regression describes
  the pre-fix snapshot only; no post-fix full-repository pass is claimed.

New commands, logs/XML, before/after observations, correction delta and complete
nine-file hashes are under
`artifacts/review_evidence/stage12_public_capture_audit_p2_fix_20261012/`.
Base HEAD remains `63f8fc769658656ec4eeef800d52c3091cc92ace`; changes are uncommitted.
All nine starting hashes matched the independent-review manifest. All five
warning-policy files remain byte-identical and the successor remains inactive.
No candidate fix is independently verified closed by this implementation task.
Job 1792588 remains FAILED with its historical audit limitation unchanged.
No network, protected inputs, HOLDOUT, production, real secrets, SSH, jobs,
scientific publication or Git mutation occurred. C, T and N remain UNSELECTED.

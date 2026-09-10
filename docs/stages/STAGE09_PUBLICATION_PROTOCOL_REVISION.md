# Stage 9 publication-protocol revision — owner-review candidate

## Status, authority and conclusion

Owner review after candidate `96d17e763addc21b0a1c321c3a03666e928c25c7`:
**CONDITIONALLY APPROVED IN PRINCIPLE — INTEGRATION NOT AUTHORIZED**. D056
requires direct Goethe PanFS exclusive-create/collision/concurrency evidence,
superseding the original proposal's conclusion that standard semantics were
sufficient without another diagnostic. Exactly one synthetic-only SLURM probe
was authorized and has completed; its scope/status is in the
[execution record](../../reports/development/stage09.md). No DEVELOPMENT retry,
protected/reference input or publication integration is authorized.

Completed environment evidence: diagnostic `1771149`, exact executable
`a9e6ede7c8aa45f8f11b0eadc797839e46c5b057`, passed all ten required cases on PanFS.
Report SHA-256:
`e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
Fresh/colliding record, seal and reservation; three synchronized four-process
races; directory fsync; repeated reopening/private topology; and symlink rejection
all reconciled successfully. D057 records the measured capability confirmation.
The environment gate is met, but **integration is still not authorized**.

Original revision scope (2026-09-10): DESIGN + SYNTHETIC/LOCAL VALIDATION ONLY,
under the owner's bounded publication-revision authorization following reporting
commit `780d96d9d8101d9974159b98a402dddeb2930e07`. That authorization included
no SLURM job, protected input access, reference refresh or DEVELOPMENT retry.
The later diagnostic authorization and its completed evidence are recorded above.

Proposed protocol: `exclusive_run_commit_seal_v2_candidate`. This addendum is
**not adopted or connected to the materializer**. The installed publication
code/launcher still fail closed at the known incompatible no-replace primitive.
The frozen [scientific design](STAGE09_OFFLINE_REFERENCE_EVIDENCE.md) and its
hash remain untouched; this document proposes an operational amendment to its
publication section only. No evidence relation, scientific identity formula,
four-state/negative-authority rule or Stage 8 lineage changes.

Diagnostic `1771054`, executable
`4915852d874a11a5f437d6cfac8837b5f9b6ebd8`, established that fresh-target Linux
`renameat2(RENAME_NOREPLACE)` fails with EINVAL (22) on the actual Goethe PanFS
environment. Collision preservation, ordinary-rename baselines and directory
fsync succeeded. This is an operational incompatibility, not a scientific
failure. The [execution record](../../reports/development/stage09.md) preserves
the original failed job and exact diagnostic hash; neither is reinterpreted.

## Selection and alternatives

Select **exclusive permanent run reservation + immutable in-place artifact +
atomic zero-byte commit seal**. The canonical run directory is its only attempt;
it does not move. A completed registration body plus one exclusive seal commits
it. This is the smallest variant of the owner's reservation/commit-record
patterns: no separate pointer directory, arbitrary attempt resolution, extra
lock service or new storage primitive.

| Alternative | Assessment |
|---|---|
| Ordinary rename after checking absence | Reject: check-then-rename race; existing empty target could be replaced |
| Immutable attempt and O_EXCL-written JSON registration | O_EXCL safely claims the filename but does not atomically write the JSON; requires a separate seal or reservation protocol |
| Reservation followed by ordinary rename | Possible for cooperating writers but adds transfer, ownership and stale-lock recovery; unnecessary when acceptance can be a sealed record |
| Non-replaceable hard-linked completed pointer | Atomic link is potentially suitable, but conflicts with current single-link topology and adds a primitive not exercised by the diagnostic; not selected |
| Symlink pointer | Reject: incompatible with no-symlink consumer/topology policy |
| Permanent exclusive run directory plus seal | Selected: no rename/link, no lock takeover, one deterministic commit slot; incomplete directory is never sufficient for success |

The changed operational invariant is intentional: **a validated immutable
artifact becomes committed atomically**, rather than its entire directory
appearing atomically at a new name. “Committed” means published DEVELOPMENT
candidate/reference pack, never scientific Stage 9 acceptance.

## Primitive evidence and limits

The protocol requires ordinary `mkdir`, `open(O_CREAT|O_EXCL|O_NOFOLLOW)`, regular
file read/write/close, no-follow metadata inspection, file fsync, directory fsync
and unlink of the writer's own precommit `_IN_PROGRESS`. It does not require
renameat2, renamex_np, rename, hard links, symlinks, advisory locks, leases or an
atomic multi-byte write. Missing required flags/operations must fail closed;
there is no optional weakening of O_EXCL/O_NOFOLLOW.

Job `1771054` successfully created its private directories and regular sentinel/
report files. Its exact `io.write_exclusive` uses O_WRONLY|O_CREAT|O_EXCL|
O_NOFOLLOW on Linux, closes and fsyncs the file. The job's directory fsync checks
also passed. It did **not** test concurrent O_EXCL collisions, cross-node races
or zero-byte seal publication. Those guarantees are based on the standard
semantics of the same creation operation, not attributed to an unperformed probe.

POSIX specifies atomic exclusive file creation and rejection of existing
symlinks. It also specifies mkdir failure when the target exists, including a
symlink. [POSIX open](https://pubs.opengroup.org/onlinepubs/007904875/functions/open.html),
[POSIX mkdir](https://pubs.opengroup.org/onlinepubs/009695299/functions/mkdir.html).
The Panasas architectural description identifies POSIX metadata atomicity and
transaction-logged metadata operations; this supports applicability, not proof
of a specific installed release or a power-loss test.
[Panasas architecture](https://performance.panasas.com/rs/523-HTY-343/images/Panasas%20ActiveStor%20Architecture%20White%20Paper.pdf).

The original proposal treated relevant standard semantics and observed fresh
creation/fsync as sufficient to select this design. Owner review now requires
direct environment evidence for exclusive collision behavior and synchronized
independent-process creation before integration. Local tests and the earlier
rename diagnostic do not meet that gate. Any future authorized execution must
replace the old preflight with bounded fresh/existing exclusive mkdir/create,
empty-seal, mode and fsync checks before inputs. This is an integration gate,
not permission to submit DEVELOPMENT. Unexpected results stop before input
access, without fallback. The owner has separately authorized exactly one small
same-node synthetic exclusive-create/reservation/seal probe; even a passing
result requires new owner authorization before integration.

## Scope, trust and topology

The publication namespace is an explicitly configured, canonical, private
Stage 9 root: either public derived packs or DEVELOPMENT runs. It is not
discovered by scanning attempts. The reviewed `/work` → `/panfs` mount alias may
be resolved only at this approved anchor; no artifact-supplied path is resolved
through a symlink. The publication key is exactly one predeclared run basename,
not a path. Allowed syntax: `[A-Za-z0-9][A-Za-z0-9_.-]{0,119}`. A corrected or
resumed build receives a separately authorized new run key; never reuse an
incomplete key merely because time elapsed or its job ended.

```text
<approved namespace>/<publication key>/     # mkdir 0700, permanent reservation
  <unchanged relation/index/metadata files> # regular 0600, nlink=1
  stage09_reference_manifest.json           # unchanged scientific manifest
  _SUCCESS.json                            # v2 bound registration body; NOT success alone
  _COMMITTED                               # fixed empty regular 0600 seal
```

`_IN_PROGRESS` exists only during construction and must be absent before commit.
Before `_COMMITTED`, *every state is unpublished*, even if `_SUCCESS.json` is
complete or `_IN_PROGRESS` is absent. Readers know these exact names and the
protocol version; they never scan arbitrary directories or guess a winner.
Build/checkpoint/spill work remains in separately inventoried private work
locations, not in the final artifact inventory. Failed run directories and
work/checkpoints are preserved. No cleanup, stale-lock stealing or repair of
an incomplete registration is part of this protocol.

Threat model: competing authorized publishers use this protocol; unrelated
users cannot write in owner-only directories. A conforming publisher can never
enter an existing reservation to write. Static foreign files, empty directories,
symlinks, hard links and corrupt records are rejected without mutation. Root and
same-UID programs that deliberately delete/rewrite immutable artifacts are not
contained by 0700/0600 or by the old rename primitive. This protocol does not
claim protection against that actor; no collision guarantee depends on an
accidental second publisher voluntarily respecting a non-atomic existence check.

No-follow ancestor/type checks and regular-file opens precede payload reads.
Reject symlink traversal, nonregular files, unexpected files/directories,
wrong modes/owners or link counts. A future integrated helper must bind its
configured anchor/run directory handles during an invocation and finish with
no-follow path-to-handle ownership checks. The local model tests static hostile
topology and immediate replacement detection, not arbitrary malicious same-UID
ancestor swaps between syscalls. Transient dev/inode equality is allowed only
within that invocation. Cross-job validation never uses historical inode values.

## Commit record and exact identities

`_SUCCESS.json` is canonical UTF-8 JSON: sorted keys, compact separators,
ASCII JSON escaping, no NaN/float fields, one final LF, no duplicate or unknown
keys. It is prepared before sealing. Its exact body is:

```text
{
  "protocol": "exclusive_run_commit_seal_v2_candidate",
  "bindings": {
    "namespace": <STAGE09_PUBLIC_REFERENCE_PACK | STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE>,
    "publication_key": <approved basename>,
    "manifest_sha256": <64 lower-case hex>,
    "logical_sha256": <64 lower-case hex>,
    "contract_sha256": <64 lower-case hex>,
    "profile_sha256": <64 lower-case hex | null for public pack>,
    "schema_bundle_sha256": <64 lower-case hex>,
    "executable_sha": <40 lower-case Git hex>,
    "stage08_input_sha256": <64 lower-case hex | null for public pack>,
    "reference_pack_sha256": <64 lower-case hex>,
    "inventory_sha256": <64 lower-case hex>
  },
  "commit_record_id": <64 lower-case hex>
}
```

`commit_record_id = SHA256(b"SAFE:publication-commit:v2\0" + canonical_json({
"protocol": protocol, "bindings": bindings}))`. Record-file SHA-256 is separately
recorded in the sanitized publication receipt. The seal has zero content; its
meaning is determined by its fixed slot and the fully validated immutable
registration body, not by the empty-file hash alone. The publication helper adds
no new timestamp, random token, inode or completion-order field. The exact
manifest hash still transitively binds its original job/timestamp provenance.

The manifest binds full runtime/job/checkpoint provenance. Its exact bytes, not
just the logical hash, are required for adoption. Changing timestamps/job metadata
can therefore change a manifest/commit identity while leaving scientific logical
identity unchanged. Same logical data with a different manifest, executable or
other bound input is a conflict for the same publication key.

For a DEVELOPMENT artifact, `stage08_input_sha256` is the existing accepted-input
binding fingerprint; `reference_pack_sha256` is the exact published pack manifest
SHA. The referenced manifest binds its frozen raw lock, reference editions/hashes,
logical pack and indexes. All existing transitive validators remain mandatory.
For a public pack, the namespace makes `reference_pack_sha256` the frozen raw
reference lock SHA (no circular self-manifest reference); Stage 8/profile are
explicitly null, never fabricated. Contract/schema are the frozen Stage 9 bundle,
and public-pack/index recipes remain bound through its exact manifest. Both
namespaces verify `operational_provenance.execution_git_sha` explicitly.

`inventory_sha256` hashes canonical JSON of the sorted list of
`{"path": relative_path, "bytes": integer, "sha256": digest}` for every data,
index and metadata file. Sort by exact UTF-8 relative-path bytes; reject duplicate,
absolute, escaping or normalization-changing paths. The list excludes the
manifest, registration, seal and transient `_IN_PROGRESS` to avoid self-reference.
Their hashes/semantics are independently checked. Public list = all relation and
index files; DEVELOPMENT list = all relation and metadata files. This is an
operational fingerprint, not a seventh evidence relation or a changed logical
dataset fingerprint. Stream its canonical encoding in the eventual helper;
the bounded synthetic model uses an in-memory one-file list only.

The caller supplies the expected publication key, namespace and exact identity
from the authorized request/receipt. A first writer derives its output hashes
from the completed independently validated build. Existing-state adoption needs
an externally pinned expected manifest plus all remaining binding checks; it may
not read an arbitrary target's self-declared hash and adopt that as expectation.
No full manifest or protected values are copied into Git by this revision.

## State machine and acceptance point

1. Validate execution authority and approved anchor before scientific inputs.
   Atomically `mkdir(run, 0700)` without `exist_ok`. Success grants this invocation
   the only construction ownership. EEXIST grants no write rights; route only
   to exact adoption if expected identity was supplied, otherwise FAIL_CLOSED.
   A non-EEXIST error, even if mkdir may have taken effect, grants no ownership.
   Preserve the state; never infer ownership from finding an empty directory.
2. Fsync namespace parent. Create `_IN_PROGRESS` exclusively. Build under the
   reserved run using no-overwrite files and the unchanged bounded engine.
   Finish all file writers, hashes, manifest and inventory. Run complete private
   scientific/integrity validation. An incomplete build never creates a seal.
3. Exclusively write canonical registration `_SUCCESS.json`, flush/fsync/close
   it. Check the complete body and its binding to the independently validated
   manifest. Remove only this invocation's `_IN_PROGRESS`; fsync all artifact
   files and directories bottom-up, including run and namespace parent.
4. Independently reopen/validate the exact prepared artifact and record; require
   `_COMMITTED` absent and exact prepared inventory. Finish fallible outcome
   construction/umask restoration before the final ownership check. Assert run
   path still refers to the owned directory and refuse any existing seal.
5. **Atomic acceptance point:** `open(run/_COMMITTED,
   O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600)`. Its intended content is zero bytes,
   so there is no partial-record-write interval. Do not write, truncate, replace
   or rename the seal. Close the descriptor. This is not an existence check
   followed by replacing rename; O_EXCL itself arbitrates the unique slot.
6. Fsync seal, run and namespace parent; perform full committed reopen with exact
   inventory and all binding/semantic validators. Prepare the publication outcome,
   release/restore fallible resources, and do the last no-follow same-invocation
   ownership/record/seal checks before returning PASS. A prior error can return
   ADOPT only after the same complete reconciliation. No content is changed.
7. After a returned PASS/ADOPT, stdout/serialization/logging failure is presentation
   failure only and cannot demote the artifact or force program-controlled failure.
   External kill cannot be reported by a dead process; subsequent readers reconcile
   persistent state. They never infer it from SLURM exit or directory existence.

Readers require the exact valid record, a zero-length regular single-link seal,
absent `_IN_PROGRESS`, full inventory/hash/scientific validation, and stable
current topology. Atomic visibility occurs at seal creation. Durable acknowledgment
requires file/parent synchronization and reopening; filesystem crash guarantees
are not stronger than the platform provides. Directory-entry durability requires
parent synchronization as well as file synchronization.
[Linux fsync documentation](https://man7.org/linux/man-pages/man2/fsync.2.html).

If a catchable failure occurs after commit was attempted, inspect the exact
owned run and perform **one bounded full reconciliation**, not a job retry loop.
A valid seal/record plus successful fsync/reopen returns ADOPT. Missing, invalid,
unreadable or wrong-owned state returns fixed
`FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION`: this means *no verified
success can be returned*, not *no commit exists*. Persistent I/O errors cannot
truthfully be converted into either verified success or verified nonpublication.
Never delete/demote a seal/registration after commit may have occurred. A future
read-only adoption can verify a restored accessible state. This operational
indeterminacy is not a fifth Stage 9 scientific evidence state.

## Exact adoption, retry and concurrency table

| Observed case | Decision and required evidence |
|---|---|
| No publication key exists | PASS after exclusive mkdir, full preparation, seal, sync and reopen |
| Same exact successful artifact already committed | ADOPT existing publication, no build/overwrite; external expected manifest, full bindings/inventory and committed reopen required; never claim this invocation built it |
| Same logical data, different manifest/executable/input/reference/key | FAIL_CLOSED; preserve existing artifact even if its own validation passes |
| Conflicting file, directory, seal or registration | FAIL_CLOSED; no removal, rename, chmod, truncation or repair |
| Incomplete attempt, including fully prepared but unsealed record | FAIL_CLOSED for that key; preserve it; no takeover, lease timeout or scheduler-state-based ownership |
| Crash before commit | Unpublished; retry at same key FAIL_CLOSED. Separately authorized new-key build may copy only verified complete checkpoints |
| Crash during seal creation | Seal absent: unpublished; seal exact and all checks pass: ADOPT; otherwise FAIL_CLOSED with reconciliation required |
| Crash after commit | ADOPT only after exact committed reopen and durability acknowledgment; no rebuilding |
| Commit call errors after taking effect | Same-invocation owned exact seal/record + fsync/reopen: ADOPT; missing/wrong/unknown state: FAIL_CLOSED, never destructive rollback |
| Repeated identical execution | Existing successful key: ADOPT exact original manifest; existing incomplete key: FAIL_CLOSED. Do not rebuild a new timestamped manifest and call it identical |
| Concurrent duplicate publishers | Exactly one mkdir winner may construct; loser never writes. If winner still incomplete, loser FAIL_CLOSED without waiting; after full committed success, separately invoked exact adoption is allowed |
| Concurrent different artifacts, same key | One reservation winner only; loser FAIL_CLOSED on binding conflict. Completion order cannot change an existing record |
| mkdir errors but may have created directory | FAIL_CLOSED without construction; no persistent ownership token is inferred from existence |
| Postcommit fsync/reopen unavailable | FAIL_CLOSED with explicit uncertain outcome, preserve everything; subsequent exact recovery may ADOPT when verification is possible |

The reservation is permanent and is not a reusable lock. No stale owner can
resume into a key used by a new owner because ownership is never reassigned.
No historical cross-job inode comparison is needed for any ADOPT case.

## Integration delta after owner review — not performed here

One narrow reusable publication helper can own reservation/record/seal handling
and call stage-specific build/validate/binding adapters. Do not migrate Stage 0–8
or broadly refactor I/O. Reuse in future stages requires their own approval.

The eventual Stage 9 patch must replace both public-pack and protected-run uses
of `s09_reference_io.publish`, the terminal validator and old rename preflight;
remove the unsupported primitive from all reachable revised publication paths.
Update exact inventory allowlists to include the seal; prepared validation and
committed validation must be distinct. No data relation/schema or scientific
validator may be bypassed by a valid seal. Bind the publication protocol version
and commit-record ID in operational receipts separately from frozen science.

All Stage 9 public-pack/candidate consumers must require the new protocol and
seal, including CLI validation/reopening. No legacy three-field success marker
may count as v2 success. There is no successfully published Stage 9 legacy artifact
to migrate; original failed attempts remain historical. Future Stage 10 receives
the exact record/manifest/pack binding and invokes the Stage 9 consumer; it does
not scan directories. Stage 8 → Stage 6 map-back remains untouched/sufficient.

Existing readers return bound artifact paths after validation; the reserved path
does not move. Dataset logical hashing stays layout/job independent. Registration
bookkeeping is O(1) per run, not per source row; inventory checks remain streaming
and full existing bounded validation remains required. This does not add a
production population map, centralized per-row registry or population-sized cache.

## Synthetic model and local test matrix

The [executable design model](../../tests/stage09_publication_protocol_model.py)
lives under tests, is not packaged/imported by `src`, accepts no scientific-input
configuration and validates only fixed invented fixture bytes. It models both
namespaces, exact external expectations and fixed error codes. It is not the
future production helper: its one-file in-memory inventory and tiny strict
validator intentionally replace the existing Arrow/DuckDB scientific validators.
The [focused test suite](../../tests/test_stage09_publication_protocol_revision.py)
uses temporary private trees, injected syscall effects/errors and concurrent
local threads. No protected/reference asset or SLURM dependency exists.

| Required test | Model coverage |
|---|---|
| 1–3 fresh, identical, conflicting publication | Fresh PASS; exact repeated ADOPT; conflicting bindings preserve original bytes |
| 4–5 incomplete attempt, existing commit target | Empty/incomplete/file/symlink/dangling targets; all seal collision types preserved |
| 6 concurrent publishers | Held winning reservation blocks loser; eight simultaneous seal creators yield one winner |
| 7–9 interruption before/during/after commit | Fault seams, uncatchable simulated death before/after seal, uncertain effect/return |
| 10 uncertain syscall result | Before-effect error, after-effect error, false success without effect; one bounded reconciliation |
| 11–15 manifest/logical/executable/Stage 8/reference mismatch | Every external bound field mutated independently and rejected; contract/profile/schema/inventory also tested |
| 16–17 corrupt record and successful reopen | Partial/wrong record, nonempty seal, corrupt manifest/payload; complete exact committed reopening |
| 18–19 collision preservation and repeated execution | Byte snapshots prove no clobber; duplicate execution adopts without rebuilding |
| 20–21 private modes and symlink policy | Owner-only modes, single links, unsafe keys/ancestor links, every publication file as symlink |
| 22 no protected dependency | Fixed invented fixture and import allowlist; no source/reference/network/SLURM loader |

Additional tests cover public-pack null/nonapplicable bindings, namespace identity,
reopening a copied exact bundle without historical inode equality, late ownership
replacement, postcommit persistent sync failure and harmless output failure.
The fixture's arbitrary typed hashes are synthetic identities, not calculated
scientific outputs or fabricated Stage 9 evidence.

Local validation on 2026-09-10: **62 focused model cases pass**; **772 complete
safe-suite tests pass in 17.81 seconds**, including Stage 7/8 regressions. Strict
mypy passes for all 94 installed source files plus the tests-only model. Ruff lint
and format checks pass (142 Python files); report/link validation and whitespace
checks pass. Runtime remains exact Python 3.14.3; no guard was weakened. These
results validate the proposal/model, not an integrated materializer or a new
Goethe run.

## Complete bounded defect ledger

Review collected the complete list before final revision; no one-bug-at-a-time
cluster retry occurred. Pipeline/error-handling/testing/code-review skills
informed the separation of commit visibility, acknowledgment and presentation,
the explicit ownership boundary and the synthetic fault matrix.

| Concern | Final disposition |
|---|---|
| Unsupported no-replace rename | Removed from proposed protocol entirely; active code remains gated pending review/integration |
| O_EXCL registration exposes partial JSON | Registration alone is not commit; atomic zero-byte seal has no write interval |
| Racy absence check | Exclusive mkdir owns permanent run; exclusive create arbitrates seal; no replacing rename anywhere |
| Duplicate acceptance or late stale writer | One key/one reservation/one seal; no takeover/unlock/TTL; loser never writes |
| False success from incomplete directory/record | Readers require seal plus all existing validation and exact external expectations |
| Mistaking byte-identical data for identical publication | Exact manifest, executable, namespace/key and all bindings required, not logical hash alone |
| Namespace/public-pack circularity | Namespace explicit; public profile/Stage 8 null; raw-lock binding separate from pack's own manifest |
| Ambiguous errors or postcommit sync failure | One full reconciliation; verified ADOPT or explicit uncertain FAIL_CLOSED; never demote/delete |
| False failure from harmless output | Presentation isolated after returned PASS/ADOPT; cannot change commit or controlled success exit |
| Lost output/kill after seal | Persistent exact record/seal and full reopening are authoritative, not process-local booleans |
| Foreign topology or last-operation replacement | No-follow/type/mode/single-link checks; same-invocation ownership required; cross-job byte identity only |
| Symlink-pointer/hard-link policy conflict | Neither used; fixed canonical root and relative key only |
| Durability overclaim | Visibility versus durable acknowledgment explicit; no power-loss proof claimed |
| Old consumers accept preparation marker | Explicit v2 protocol+seal gate required in every eventual adapter; active consumers untouched until integration |
| Hidden old requirement in public-pack builder/launcher | Both listed in mandatory integration delta; design is not described as deployment-ready code |
| Production-scale registry expansion | One small record/seal per run; streaming inventory and unchanged bounded validators |
| Model mistaken for production validation | Tests-only fixed synthetic model; no installed helper or data path introduced |

The original proposal's design review found no remaining logical defect. Owner
review conditionally agrees but requires the direct PanFS capability diagnostic
specified in D056 before authorizing integration. Integration and its end-to-end synthetic tests
remain required work after review; their absence is not presented as an executed
materializer fix. No Stage 0–8 modification or scientific-contract amendment is
required. HOLDOUT, production, Pelias and protected Stage 8 payloads were untouched.

## Owner gate

The protocol is conditionally approved in principle, not authorized for
integration. The separately authorized synthetic capability diagnostic is now
complete and reconciled; stop for the owner. No DEVELOPMENT retry is authorized.
Stage 9 stays NOT ACCEPTED and the previous DEVELOPMENT preflight failure remains
truthful.

NEXT: OWNER AUTHORIZATION TO INTEGRATE PUBLICATION PROTOCOL.

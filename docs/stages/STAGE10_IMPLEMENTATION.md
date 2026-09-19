# Stage 10 implementation and controlled DEVELOPMENT execution

## Authorization and design freeze

The owner approved final design `ca0bac7acd8bae709e171c481ddea52df3e5304d`
and authorized implementation, comprehensive synthetic/fault validation, one
complete bounded implementation self-review, a pushed executable and exactly
one controlled DEVELOPMENT execution. No Stage 11, Pelias, HOLDOUT or production.

The approved branch was merged into main with a normal non-squash merge,
`1443bb3b3c1bb50220bf38231e01552c66c4eaee`, and main was pushed normally.
Its first parent is accepted Stage 9 main
`23cfb85f428b00301d68591ea5992763abf9ad88`; the approved design is the second
parent. All implementation descends from that freeze. No Stage 10 acceptance tag.
Historical status wording in the normative design remains frozen; this separate
record carries the new implementation authorization.

**IMPLEMENTED — DEVELOPMENT JOB 1772639 TIMED OUT — OWNER REVIEW REQUIRED — NOT ACCEPTED.**

The latest [execution reconciliation](#development-timeout-reconciliation--2026-09-19)
supersedes the earlier connection blocker. Historical checkpoints below remain
dated evidence; they do not authorize another submission.

## Transliteration runtime blocker, 2026-09-14

**STAGE10_IMPLEMENTATION_BLOCKED_TRANSLITERATION_RUNTIME**

Historical blocker, resolved by the verified replacement runtime below on
2026-09-15. The cancelled attempt remains part of the record.

Public-only preparation used the clean detached preparation executable
`79a994e8a000b0de79dd9edbf52d4aa8e4bc1f14`. Scheduler accounting for allocation
`1772282` (`safe-stage10-public-icu`) records `CANCELLED by 60099`, no start,
elapsed `00:00:00`, and exit field `0:0`. That exit field is not a successful
build: the allocation never started. The request used `srun --immediate=30`,
partition `general1`, account `footprint`, 4 CPUs, 8 GiB and a 20-minute limit.
Scheduler timestamps are preserved as reported: submission
`2026-09-14T17:35:04`, end `2026-09-14T17:35:34`; no timezone is inferred.

The expected Linux build root
`/work/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage10/icu77_linux_79a994e8a000`
does not exist. Consequently its `runtime_build_lock.json`, linked ICU/data
artifacts and Linux synthetic runtime verification are missing. The public
source archive and detached preparation checkout remain present. This is an
unestablished Linux runtime, not an observed ICU version mismatch. The verified
Mac build cannot satisfy the protected Goethe runtime gate.

No allocation retry, replacement runtime, protected DEVELOPMENT submission,
publication reservation or Stage 10 candidate was made. The owner's explicit
runtime stop rule applies. Unfinished family/evidence modules and their synthetic
tests remain in the workspace; no complete Stage 10 executable has been committed
or claimed ready. A resumption must first establish the exact locked Linux
runtime through authorized compute preparation, then finish implementation and
all remaining validation gates before the single protected DEVELOPMENT run.

## Public transliteration runtime preparation

### Owner-authorized replacement preparation

The owner classified job `1772282` as environment/runtime preparation with no
executed ICU evidence and authorized exactly one replacement public-only job.
One accounting reconciliation reconfirmed no start, zero elapsed and absence of
the former runtime target. Installed `srun --help` defines `--immediate=secs` as
exiting when resources are unavailable within that interval. The exact 30-second
submission-to-cancellation interval matches the original `--immediate=30`
allocation timeout; accounting provides no finer resource/priority reason.
There is no observed ICU/version mismatch. Historical records remain preserved.

The replacement [batch launcher](../../cluster/goethe_nhr/stage10_build_transliteration_runtime.sbatch)
uses 4 CPUs, 8 GiB, 30 minutes, `general1` / `footprint`, explicit no-requeue and
a restart-count rejection. It may remain queued; there is no immediate-allocation
timeout, polling loop, cancellation or automatic replacement. It requires a
clean detached exact pushed checkout, the verified public source archive, a new
private runtime target, and the shared Goethe/SLURM guard. It invokes no protected
reader or geocoder. Accepted Python runtime files are read, never modified.

The new runtime lock records source origin/commit/archive, all six frozen
source/data member identities, compiler/toolchain/flags, platform, exact
Python/normalization binaries, wrapper and Script dependency hashes, resolved
Linux shared-library hashes, static ICU/data/bridge hashes, canonical IDs and
forward direction. Runtime initialization rejects dependency, version, hash,
script-data or transform identity changes and external library/data overrides.
Missing/corrupt locks and assets fail with static diagnostic codes.

`runtime_semantic_fingerprint` is SHA-256 over the explicitly versioned semantic
projection in [s10_runtime_lock.py](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_runtime_lock.py).
It excludes runtime paths, compiler locations, Git/job/timestamp provenance and
its own fingerprint. The logical runtime-root identity uses that digest.
The frozen Stage 10 transform-asset binding still uses the exact complete
`runtime_build_lock.json` SHA, as the owner-approved data contract requires;
these are separate identities. No scientific formula was changed.

Successful preparation writes an exclusive, fsynced build lock, then the
public-only validation report and an exclusive `_READY.json` binding both file
hashes. A lock without the matching successful report/ready record is insufficient
evidence for later protected consumption. The exact lock SHA must also be bound
externally by the later reviewed Stage 10 execution. Failure receipts are written
only inside this invocation's captured new directory identity; an existing or
replaced runtime is never modified. No rebuild overwrites a previous runtime.

Local verification of the revised build passed **25 positive runtime checks and
12 deliberate mismatch/failure checks**, including Greek/Cyrillic, NFC/decomposed
input, inherited/mixed/unsupported scripts, punctuation/digits, unchanged output,
repeated output, actual versions/IDs and binary/data hashes. Exhaustive ICU
additional-filter comparison checked **2,228,224** code-point/script pairs against
the pinned Script data and Unicode 16 categories. The same check function runs
inside the replacement Goethe job. Mac evidence cannot substitute for Linux
runtime evidence. There is still no protected DEVELOPMENT submission.

### Bounded public-preparation review

| Item | Finding | Disposition |
| --- | --- | --- |
| RP-01 | `--immediate=30` prevented the earlier allocation from starting | Ordinary single batch submission; no requeue or retry. |
| RP-02 | Linux runtime/lock evidence absent | Resolved on 2026-09-15 by job 1772341 and exact retained lock/report/binary verification; no substitution. |
| RP-03 | Initial lock omitted Python wrapper/normalization and shared dependency hashes | Exact dependency locks and fail-closed initialization added. |
| RP-04 | Operational lock identity alone did not supply a path/time-independent runtime identity | Added a separate deterministic semantic projection; frozen full-lock binding retained. |
| RP-05 | UnicodeSet/property equivalence lacked independent exhaustive evidence | Same additional filter exposed by bridge and exhaustively compared; canonical original-filter intersection unchanged. |
| RP-06 | Build smoke vectors did not cover the required runtime failure cases | Public validation now includes 25 positive and 12 injected-fault checks. |
| RP-07 | Malformed/missing lock/assets could expose arbitrary loader errors | Static fail-closed diagnostics and mismatch tests. |
| RP-08 | Failure receipt could have altered a pre-existing collision target | Receipt requires this invocation's captured directory identity; collision/ownership tests pass. |
| RP-09 | Pre-submission check rejected the already accepted `/work` to `/panfs/vdura1` mount alias | Canonicalize only the configured project anchor, following accepted Stage 9; still reject symlinks below it. Detected before any replacement submission or build directory creation. |

All bounded preparation defects, including RP-02's Linux execution gate, are
resolved. This is a runtime checkpoint, not an implementation success claim. The full
Stage 10 implementation/self-review remains unfinished and preserved locally;
this preparation review does not replace it. Frozen design hashes and Stage 0–9
science remain unchanged. No additional owner scientific decision is needed.

### Exact Goethe runtime established — 2026-09-15

**STAGE10_TRANSLITERATION_RUNTIME_READY**

Replacement job **1772341**, executable
`f7765d463e0053a0f062e333d77a75f5ce1bc6a8`, completed with exit `0:0`, elapsed
`00:04:17`, batch MaxRSS `471988K`. Requested 4 CPUs / 8 GiB / 30 minutes;
accounting reports 80 allocated CPUs, while compilation explicitly uses 4.
No second replacement was submitted. The source archive and all compiled
asset hashes match. The immutable runtime is
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage10/icu77_linux_f7765d463e00`,
under the accepted `/work/footprint` mount alias.

Verified ICU4C **77.1**, Unicode **16.0.0**, CLDR **47**, CPython **3.14.3**;
canonical `Grek-Latn` / `Cyrl-Latn`, `UTRANS_FORWARD`, unchanged frozen filtering
and normalization. The in-job report passes **25 positive and 12 fail-closed
checks**, plus **2,228,224** independent UnicodeSet comparisons. No protected
payload was accessed. Shell-only reopening reconciled lock/report/ready hashes,
all four compiled artifacts, private permissions and no failure receipt. No
Python/data processing was run on the login node.

- Build lock SHA: `20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd`.
- Runtime semantic fingerprint: `8b0a2232c28898f1dfd581e88fcbdbe8b7e7bebd458abcc852fab4cbfe225a8b`.
- Validation SHA: `36fbc8c546f322e8a3e0b64e31411b900984cd9871ce7cf8c2941d90c479c0b9`.
- Ready-record SHA: `7a1125109463d8e6ed10d905ed379f90c4b19025bfbcc4c1cc75f1b0b51700dc`.

The [public runtime inventory](../scientific_assets/stage10_runtime_goethe_v1/inventory.json)
binds byte-exact sanitized copies of the lock, validation and ready record.
Its mechanical local validation recomputes the semantic fingerprint and
reconciles the executable/source hashes without loading Linux binaries on Mac.
Binary/public build assets remain on Goethe, outside Git. The wrapper and its
locked dependencies must remain byte-identical when used by the Stage 10
executable; remaining implementation belongs in separate modules.

The existing owner authorization now permits resuming the unfinished Stage 10
implementation without another permission step. There is still no complete
executable or protected DEVELOPMENT run. Stage 0–9 science is unchanged;
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED.

The existing Mac ICU 78.3 is ineligible. A new isolated build uses the exact
ICU source commit `457157a92aa053e632cc7fcfd0e12f8a943b2d11`, with source archive
SHA-256 `629e7e6e309d1eeeb29c3eaf49e4f4532534fcf2613bcf0e51cd7850fa85a007`.
Every registry/rule/UCD asset in the approved specification is rehashed before
building. Source, compiler outputs and logs remain private outside Git.

The first public source check rejected the archive's internal ICU license
symlink. The helper now permits only that exact confined link; arbitrary links
remain prohibited. The failed preparation directory is preserved. This did
not involve protected input or a DEVELOPMENT execution.

ICU is compiled statically with its data from source. The narrow C++ bridge uses
the exact canonical IDs, forward direction, original-filter intersection and
whole-string transformation. ICU file-based data loading is disabled. Linux
linking binds the static ICU symbols locally; the lock binds bridge, i18n,
common and compiled-data archives, compiler/flags, source/spec hashes, platform,
build provenance and exact public synthetic vectors. No system ICU fallback.

The isolated Mac build reports ICU 77.1, Unicode 16.0.0 and CLDR 47 and passes
the exact public/synthetic vectors. Mac Python is 3.14.7/Unicode 16; it supports
synthetic function tests only, not the protected exact-runtime gate requiring
Python 3.14.3. Goethe's previously accepted Python runtime path was verified by
shell metadata. A separately scoped public-only compute preparation must build
and verify the Linux ICU lock before any protected DEVELOPMENT submission.

`scripts/stage10_build_runtime.py` has no address arguments, no protected data
reader and no geocoder capability. Linux invocation requires the shared Goethe
SLURM guard. Code reaches Goethe only through a clean exact pushed Git commit.
A preparation commit is not the complete Stage 10 executable or permission to
submit protected DEVELOPMENT before the remaining gates pass.

## Validation in progress

Initial focused validation passed 70 synthetic tests, including the actual
Mac ICU vectors, version/spec/data-hash faults, mixed/inherited scripts, native
preservation, Q5/Q6 coexistence, five NATIVE/four STANDARD/nine row hypotheses,
whole-line stripping, ambiguity/source-field vetoes, boundaries, context identity
and convergence. These do not replace the required complete repository/static
checks, final bounded self-review, Linux runtime verification or candidate review.

At the runtime-blocker checkpoint, all 92 current Stage 10 focused synthetic tests
passed, including source-reference policy tests. This does not certify the
unfinished materialization/publication path or the complete implementation.

Operating budget remains UNSELECTED. The initial artifact must retain every
eligible Q1–Q6 intent; Q7 remains globally deferred with no machinery or rows.
Stage 0–9 science/history is unchanged. HOLDOUT remains sealed; production/Pelias
untouched; Stage 11 NOT STARTED. Stage 10 is not yet accepted.

## Executable implementation — final bounded self-review

The Stage 10 executable implements two protected relations at the approved
occurrence grain. Every PRESENT Stage 8 STANDARD/NATIVE slot retains its own
context and six family decisions. Complete intents converge only inside that
context. Q1/Q2 preserve the full candidate; Q3 uses that occurrence's four slots;
Q4 uses source fields with scoped accepted positive evidence and authorized
postcode-only negative gates; Q5 requires complete-line grammar, unique parser
alignment and source vetoes; Q6 uses the verified immutable Goethe runtime.
Q7 has no evaluator, workload, decision rows or reserved IDs. Operating budget
is UNSELECTED; bounds fail closed without suppressing eligible families.

The [execution profile](../scientific_assets/stage10_execution_profile_v1.json),
[schema descriptor](../scientific_assets/stage10_schema_descriptor_v1.json), and
[implementation inventory](../scientific_assets/stage10_implementation_inventory_v1.json)
bind the executable contract, schemas, transformations and runtime. These are
implementation assets of the unchanged scientific design. The inventory excludes
itself and this rolling operational record to avoid circular hashes.

Generation uses disk-backed DuckDB joins/indexes, Arrow batches limited by bytes
and rows, a streaming hash of giant nested parser arrays, fixed-size on-disk
alignment offsets, bounded immutable evidence caches and sixteen context-ID
prefix shards. Each complete shard has an exclusive input/science/executable
checkpoint. Explicit resume validates interval, schema, bytes, counts and logical
hashes; incomplete checkpoints are never adopted. Reverse shard generation and
complete checkpoint reuse preserve logical identity. Production sizing still
requires separate evidence; this DEVELOPMENT run cannot establish production
readiness.

Publication imports the exact accepted Stage 9 exclusive-create, ownership,
private-read and seal primitives and retains its reservation/registration/
commit/reopen transitions in a Stage 10 registration adapter. No Stage 9 file is
changed. Preflight checks canonical private paths, actual PanFS mount identity,
same accepted topology, O_CREAT|O_EXCL primitive reuse and free-space headroom.
A changed filesystem/topology returns STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED.
No fresh filesystem capability diagnostic is launched. Every publication phase
validates byte inventories, both full relations, independent context reconstruction,
all transformation/selector bytes, summary, identities and map-back. Uncertain
commit outcomes require reconciliation; no automatic retry or cleanup.

The frozen logical summary remains closed. Additional aggregate diagnostics
explicitly requested in the implementation authorization live in operational
manifest metadata: family totals, Q5/Q6 coexistence, role maxima, exact postcode
capability effects, non-negative absence evidence, Q5 abstentions and Q6 script
eligibility/failure counts. They do not influence generation or logical IDs and
are recomputed on reopen. Protected text, IDs, source filenames and arbitrary
exception strings never enter portable reporting. Complete query representations
remain in the two controlled relations only. No Stage 11 semantic ID is claimed.

### Complete implementation defect ledger

This is one bounded review covering the whole implementation and integration
findings, including checks where no scientific defect was found. All entries
below are resolved before submission; no candidate output has been generated.

| ID | Finding / review scope | Resolution and evidence |
| --- | --- | --- |
| I01 | Globally shared candidate could contaminate occurrence eligibility | Exact source/role context FKs; row-local country and boundaries; multi-row/multi-country/equal-role tests. |
| I02 | Nested Stage 8 parser list could create candidate-sized Python objects | Arrow recursive streaming certificate; narrow candidate table and streamed long components; large-list test. |
| I03 | Python DuckDB UDF introduced an undeclared NumPy runtime dependency | Scalar identity generation through bounded Arrow writer; no additional dependency. |
| I04 | Evidence-object fields differed from inferred names | Use accepted asset_id and explicit_parent_id; full synthetic schema integration. |
| I05 | SQL conflict expression evaluated an error during ordinary selector insertion | Exact stored-payload comparison using RETURNING; collision tests and independent certificate reconstruction. |
| I06 | Witness certificate reader could miss transaction-local rows | Hash through the transaction-owning connection; independently reconstructed nonempty five-section certificate test. |
| I07 | Repeated public-object/parser work and repeated input-binding serialization | Fixed byte/entry caches and immutable cached input identity; no cross-context eligibility cache. |
| I08 | Country-conflict synthetic fixture incorrectly expected positive historical Q4 evidence | Faithful Stage 7 country provenance; unresolved existing assessments remain unresolved while row-local full queries survive. |
| I09 | Postcode negative witness initially lacked complete scope checks | Exact COUNTRY_MATRIX, country zip locator or full prefix-bundle/admin/country witness, source arguments and authorized negative capability; six injected certificate faults. |
| I10 | GeoNames positive witness needed an explicit object-kind check | POSTAL_ASSOCIATION and exact same-record field lineage; negative authority remains prohibited. |
| I11 | Historical JSON helper used pretty UTF-8 rather than Stage 10 compact ASCII | Dedicated canonical writer; byte-exact checkpoint/summary tests. |
| I12 | Temporary output views were invisible to independent replay cursors | Persistent private workspace views; full integrated publication/replay test. |
| I13 | Summary construction rescanned payloads per cell | Fixed-dimension grouped counts and bounded histogram bins; complete source/candidate populations include zero-output cases. |
| I14 | Checkpoint reuse needed explicit interval/count enforcement | Exact prefix and six-decisions/context validation, immutable hashes and complete replay before commit. |
| I15 | Runtime failure-receipt filename and external ready pins needed reconciliation | Exact committed lock/report/ready hashes and real runtime_failure_receipt.json checked before protected inputs. |
| I16 | Preparation failures and teardown could obscure the publication outcome | Preserved static failure receipts; post-success receipt/presentation/teardown cannot demote validated publication. |
| I17 | Q5 deletion safety / Q5–Q6 independence | Complete boundary units only, unique alignment, mixed-content/source vetoes; 20,000-component bounded-memory test; independent transformations attain five NATIVE/nine per row. |
| I18 | Identity, convergence and family membership corruption | Full-intent byte comparison, deterministic replay, PK/FK/rank/role checks, zero orphan/cross-context membership; injected corruption fails. |
| I19 | Arbitrary operating-budget or Q7 leakage | All eligible catalog only, UNSELECTED operating budget, no Q7 machinery, role/context/row/candidate fail-closed caps. |
| I20 | Publication uncertainty, races and hostile paths | Accepted state transitions with Stage 10 binding; fault/adoption/race/symlink/hardlink/permissions tests. |
| I21 | Raw engine errors or network calls could leak data | Shared pre-input execution guard, static CLI/receipt errors, disabled network and DuckDB remote filesystem; privacy/error-path tests. |
| I22 | Exact runtime and frozen science could drift during integration | Seven locked source/data dependencies, six design files and runtime semantic/build identities mechanically rechecked; none changed. |
| I23 | Default Mac Python did not satisfy historical exact-runtime tests | Use existing Python 3.14.3 environment for the safe regression suite; separately run locked ICU tests in their matching Mac environment. No guard patched. |
| I24 | Broad historical style/type checks have existing failures | Record baseline diagnostics without editing accepted Stage 0–9; all implementation source and Stage 10 tests pass strict typing and maintained-tree Ruff. |

### Validation evidence and execution boundary

Focused Stage 10 tests: **215 PASS**, including real locked ICU, deliberate
version/data/hash faults, context/cardinality proofs, boundary/stripping tests,
closed evidence gates, full artifact replay, all publication faults, shard order,
resume, privacy and large-value behavior. The complete safe repository collection
is covered by **989 PASS** in the existing exact Python 3.14.3 environment plus
its remaining **62 Stage 10 runtime/transliteration tests** in the matching
Mac runtime environment. All 62 are also included in the 215 focused total;
they are not counted twice as distinct tests. No protected payload fixtures.

An attempted auxiliary Mac ICU build under the standalone Python 3.14.3 failed
while constructing its Python dependency lock because that distribution embeds
unicodedata without an extension-file path. The private
`verified-macos-v5-py3143/runtime_failure_receipt.json` and build are preserved.
This is local test-tool packaging, not a Goethe ICU/version mismatch. The
already verified Goethe build and the existing Mac v4 runtime remain unchanged.
No replacement Goethe preparation job was submitted.

Strict mypy passes all source, Stage 10 tests and inventory validation (120 modules). The broad
historical `mypy src tests` command reports 341 existing diagnostics in 16
Stage 6/7/9 test modules; none is in Stage 10 or implementation source. Broad
Ruff reports two existing unused imports and four formatting issues in the
accepted Stage 9 independent-review archive. Maintained `src tests scripts`
lint/format checks pass. No exclusion or weakened guard was added to project
configuration, and historical review files remain byte-identical.

The launcher requests one node/task, 4 CPUs, 32 GiB and 24 hours on general1 /
footprint, no dependencies and no requeue. DuckDB uses four threads and an
8-GiB memory limit; the remaining headroom accommodates Arrow, giant accepted
scalar values and ICU. The walltime allows complete input hashing plus three
full publication-validation passes; it is a ceiling, not a runtime prediction.
Code is pushed before a clean detached Goethe checkout is created. The one
DEVELOPMENT submission remains subject to exact input/runtime hashes, unchanged
PanFS topology, absent destination/reservation and all reconciliation gates.
PENDING/RUNNING means one state report and STOP; failure means preserve and STOP.
Stage 10 remains NOT ACCEPTED until independent review and owner acceptance.


### Executable pushed; connection preflight blocked — 2026-09-15

The exact executable is **f83480d60449bcc904c0c622e394e12df3c3f2d9**, pushed to
main normally. It descends from the approved design merge and retains all
runtime-locked source hashes. Final checks: 989 safe tests in Python 3.14.3,
215 Stage 10 focused tests in the matching Mac ICU environment, 120 strict
mypy modules, maintained-tree Ruff lint/format, report/document/hash/schema/
inventory checks, CLI help/contract output, shell syntax and staged privacy/diff
checks. An isolated export of accepted Stage 9 main independently reproduced
the exact 341 historical mypy diagnostics and the existing review-archive Ruff
findings. No accepted file was edited to remove them.

The SSH orchestration attempt failed before contacting Goethe: configured
`goethe.hhlr-gu.de` did not resolve. Local connection metadata reported eduVPN
disconnected. No protected artifact was opened and no remote checkout,
publication directory/reservation, scheduler submission or protected execution
was created by this implementation attempt. Public runtime job 1772341 remains
the completed preparation evidence; it is not a DEVELOPMENT job.

The owner was asked to restore the VPN connection. On resumption, retain
executable f83480d60449bcc904c0c622e394e12df3c3f2d9; complete the exact detached
Goethe checkout, accepted Stage 6/8/9 metadata/runtime/PanFS/destination
reconciliation, then submit the one already authorized DEVELOPMENT job.
No additional scientific approval is needed. Do not count the failed SSH
connection as a job attempt, and do not silently skip any pre-submission gate.
HOLDOUT remains sealed; Stage 0–9 unchanged; production/Pelias untouched;
Stage 11 NOT STARTED; Stage 10 NOT ACCEPTED.

### DEVELOPMENT timeout reconciliation — 2026-09-19

**STAGE10_DEVELOPMENT_RUN_FAILED**

After the owner restored eduVPN on 2026-09-15, the authorized preflight passed:
clean detached executable `f83480d60449bcc904c0c622e394e12df3c3f2d9`, exact
accepted Stage 6/8/9 manifests and reference pack, frozen design/implementation
inventory, ICU archive/data/library/lock hashes, private PanFS topology and
absent destination/reservation. Exactly one DEVELOPMENT job, **1772639**, was
submitted at **2026-09-15T14:22:01Z**. Its first observation was PENDING / Priority;
the session stopped without polling, cancellation or resubmission.

On the owner's 2026-09-19 continuation, one successful accounting query reported:

| Accounting field | Observed value |
| --- | --- |
| Allocation state / exit field | TIMEOUT / `0:0` |
| Batch state / exit | CANCELLED / `0:15` (SIGTERM) |
| Allocation elapsed | `1-00:00:20` (86,420 seconds) |
| Batch elapsed | `1-00:00:21` (86,421 seconds) |
| Batch MaxRSS | `7583388K` (about 7.23 GiB) |
| Requested resources | 1 node/task, 4 CPUs, 32 GiB, 24 hours; general1 / footprint |
| Allocated CPUs | 80; application thread limit remains 4 |
| Dependencies / requeue | None / disabled |
| Submit / start / end, scheduler strings | `2026-09-15T16:22:01` / `2026-09-18T00:47:21` / `2026-09-19T00:47:41` |

Scheduler strings above carry no offset in sacct and are retained as reported.
The independent submission receipt supplies UTC. The allocation's `0:0` field
does **not** indicate success: terminal state is TIMEOUT and the batch received
SIGTERM. There is no OOM marker in the preserved stderr. The initial accounting
request used unsupported field `Restarts` and returned no state; removing that
field yielded the single successful terminal observation, not a polling loop.

**Classification: RESOURCE — walltime exhausted.** The implementation's
generation throughput and precise bottleneck remain unresolved; this is not
evidence for increasing the time limit or changing scientific eligibility.
No runtime mismatch, scientific defect or publication failure was observed.
Those statements do not certify uncompleted output checks.

#### Preserved evidence and last evidenced phase

The publication key is `stage10_development_20260915T142128Z_f83480d60449`.
The target under
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/`
is **absent**. There is no final reservation directory, registration, manifest,
`_COMMITTED` seal, logical dataset fingerprint or validated candidate to adopt.

The private work root remains:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/work/stage10_development_20260915T142128Z_f83480d60449_4v1m114k`.
Shell metadata inspection found:

| Preserved item | Bytes / state |
| --- | --- |
| `attempt.json` | 340; created `2026-09-17T23:56:30.302345+00:00` |
| `workspace/context.duckdb` | 1,517,826,048 |
| `workspace/context.duckdb.wal` | 3,802,981,496; last modification `2026-09-18T22:47:26.537344056Z` |
| Candidate-certificate Parquet part | 3,483,672 |
| Context-key Parquet part | 5,512,940 |
| Shard directories | 1, prefix `0`; created by generation after workspace preparation |
| Shard files | 1 partial `query_family_decision/part-000000.parquet`, 2,172,840 bytes |
| Completed `checkpoint.json` files | 0 |
| Application `failure.json` / `completed.json` | Both absent |

Directories were `0700`, files `0600`; no shard symlink was found. None of the
database, WAL or Parquet payloads was opened during reconciliation. The partial
Parquet file is neither validated nor assumed complete. Its row count is unknown;
buffered hypotheses and completed contexts cannot be inferred from file counts.
No incomplete shard is eligible for checkpoint adoption.

Code order places `attempt.json` after exact runtime and input consumption;
shard creation follows `work.prepare()`. Thus the last evidenced phase is
**incomplete shard-0 generation**. The metadata does not locate the expensive
context, selector, transformation or database operation. No profiler or protected
rerun was launched. Runtime lock and ready-record hashes still match, and the
detached checkout remains clean at the exact executable.

The accepted combined Stage 10 input binding recorded in the attempt is
`531d512f6c177fb5a9d6cd262e66846cdfd5cc66ba818c5aba8030165648878e`;
runtime build lock is
`20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd`.
This is gate/attempt evidence, not independent completed-candidate validation.

Submission receipts remain under
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/integration_stage10/submission_f83480d60449`.
A new exclusive `0600` **post-termination reconciliation** record,
`reconciliation_20260919_timeout.json`, records accounting, metadata and the stop
boundary. It is not a retroactively fabricated in-job failure receipt. No
historical log, attempt, partial output or runtime was changed.

| Evidence | SHA-256 |
| --- | --- |
| Attempt receipt | `fe5451fabd7bb942ba96aa51e46d11299341679acdcc2eb45ea6d7fdabce9504` |
| Submission receipt | `f98631163fa7a301505565bc7005f5a1d31f3caad8bf0c513b2bf3b33d8f1671` |
| Initial scheduler-state receipt | `ebc8cde014664102b15682213bbc8ea2821dfb78a4a059d01d2ddb74dfb41bbc` |
| Preflight receipt | `51a1bb11533eac4828f81e2583d57f1c974617642fc715e4ee99612f491916f1` |
| Empty SLURM stdout | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| SLURM stderr, 104 bytes, one time-limit cancellation line | `f3ab4bb108e0dc443a57f07cf536015a9a87498ffed71c50b3b73ad960ebadc5` |
| Post-termination reconciliation receipt | `578f1082f1548e5683ad5284cdcce79716ccb020e8e59adc760f95c8f097ea87` |

#### Complete bounded failure-review ledger

| ID | Finding / classification | Disposition |
| --- | --- | --- |
| F01 | RESOURCE: the authorized 24-hour allocation expired during incomplete generation | Confirmed terminal failure; preserve attempt; no cancel, restart, resource change or resubmission. Owner review required. |
| F02 | IMPLEMENTATION investigation: no complete shard after the allocation; expensive operation and throughput cause unknown | Open. Existing metadata cannot distinguish context construction, evidence certificates, family work, buffering or database cost. Any proposed repair needs evidence and owner review; no speculation promoted to diagnosis. |
| F03 | IMPLEMENTATION observability: SIGTERM produced no application failure receipt or explicit progress receipt within shard 0 | Confirmed gap. Python exception handling does not intercept default SIGTERM. Separate reconciliation preserves the observed failure without modifying the attempt. No signal handler or checkpoint policy changed in this review. |
| F04 | REPORTING_ONLY: current status pages still described the resolved VPN blocker and no submission | Resolved by this dated record and aligned current-status links; earlier dated history retained. |
| F05 | REVIEW_TOOLING: sacct rejected the unsupported `Restarts` field | Resolved by using supported fields. No state was obtained from the rejected query; no repeated successful scheduler poll. |

The bounded review covered occurrence/candidate grain, row-country and boundary
isolation, parser/reference authority, Q5 safety, Q6 identity, family convergence,
decision cardinality, identities, ceilings, orphans/map-back, expansion, privacy,
publication and scale. With no complete shard or candidate, none of the scientific
output invariants or Q1–Q6 distributions can be independently measured here.
Their synthetic evidence remains the earlier pre-submission record, not proof
that this failed execution passed. Q7 remains absent from the executable; no
Stage 11 work or cross-context request deduplication occurred. No protected
strings, source-row IDs or payload examples enter this report.

The only changes after failure are sanitized reporting and the external
reconciliation receipt. Executable, frozen design/specs, runtime lock and Stage
0–9 science remain unchanged. Scientific operating budget is **UNSELECTED**.
Reporting validation passed the Stage 10 design/runtime/schema/inventory check,
stage-report validator, both report tests, and diff/changed-file privacy review.
No implementation or protected test was rerun during failure reconciliation.
HOLDOUT remains sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT ACCEPTED. The one authorized DEVELOPMENT submission has been used.

**NEXT: OWNER REVIEW OF STAGE 10 DEVELOPMENT FAILURE.** No new execution or
implementation repair is authorized by this reporting checkpoint.

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

**IMPLEMENTATION IN PROGRESS — NO DEVELOPMENT JOB SUBMITTED — NOT ACCEPTED.**

## Transliteration runtime blocker, 2026-09-14

**STAGE10_IMPLEMENTATION_BLOCKED_TRANSLITERATION_RUNTIME**

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
| RP-02 | Linux runtime/lock evidence absent | Remains an execution gate until the replacement job validates; no substitution. |
| RP-03 | Initial lock omitted Python wrapper/normalization and shared dependency hashes | Exact dependency locks and fail-closed initialization added. |
| RP-04 | Operational lock identity alone did not supply a path/time-independent runtime identity | Added a separate deterministic semantic projection; frozen full-lock binding retained. |
| RP-05 | UnicodeSet/property equivalence lacked independent exhaustive evidence | Same additional filter exposed by bridge and exhaustively compared; canonical original-filter intersection unchanged. |
| RP-06 | Build smoke vectors did not cover the required runtime failure cases | Public validation now includes 25 positive and 12 injected-fault checks. |
| RP-07 | Malformed/missing lock/assets could expose arbitrary loader errors | Static fail-closed diagnostics and mismatch tests. |
| RP-08 | Failure receipt could have altered a pre-existing collision target | Receipt requires this invocation's captured directory identity; collision/ownership tests pass. |
| RP-09 | Pre-submission check rejected the already accepted `/work` to `/panfs/vdura1` mount alias | Canonicalize only the configured project anchor, following accepted Stage 9; still reject symlinks below it. Detected before any replacement submission or build directory creation. |

All bounded preparation code defects are resolved. RP-02 is the explicitly
pending Linux execution gate, not an implementation success claim. The full
Stage 10 implementation/self-review remains unfinished and preserved locally;
this preparation review does not replace it. Frozen design hashes and Stage 0–9
science remain unchanged. No additional owner scientific decision is needed.

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

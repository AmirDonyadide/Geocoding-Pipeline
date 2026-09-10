# Stage 9 DEVELOPMENT execution record

## Status

Current: owner-approved publication integration complete; one corrected
DEVELOPMENT retry is being prepared under D058 after the local gate. No corrected
candidate is claimed before scheduled execution and full reconciliation.

Historical result: STAGE09_DEVELOPMENT_RUN_FAILED_PREFLIGHT.
Job `1770156` was submitted once, then failed in the synthetic filesystem
preflight on 2026-09-09. Reconciliation on 2026-09-10 found no public pack,
protected candidate artifact, manifest or success marker. The materializer was
never invoked. No completed Stage 9 candidate/result is claimed.
The separately authorized synthetic-only filesystem diagnostic, job `1771054`,
completed on 2026-09-10. Fresh-target `renameat2(RENAME_NOREPLACE)` failed with
`EINVAL` (22); zero-flag and POSIX fresh-target baselines succeeded. The tested
no-replace publication primitive is not usable in that compute/filesystem
environment. No fallback or retry was enabled by that diagnostic.
The separately authorized exclusive-create diagnostic `1771149` has now passed
all ten required cases on PanFS. This confirms the measured publication
primitives, not a Stage 9 candidate. The owner subsequently approved integration
and exactly one corrected DEVELOPMENT retry; current integration evidence is below.
Stage 9 is NOT ACCEPTED. No protected DEVELOPMENT input has been materialized
locally; HOLDOUT remains sealed, production/Pelias untouched.

## Purpose and scientific boundary

Offline REFERENCE_EVIDENCE only, under the unchanged
[frozen design](../../docs/stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md).
The [implementation record](../../docs/stages/STAGE09_IMPLEMENTATION.md) describes
bounded execution, safety, publication, schemas and Stage 10 handoff.
SUPPORTED/CONTRADICTED/NOT_FOUND/NOT_EVALUABLE describe a capability-scoped claim,
not address accuracy, geocoding accuracy, a valid-address rate or final precision.
NOT_FOUND is not contradiction; reference mismatch is not source invalidity.

## Provenance and exact inputs

- Design freeze: `f85510f938a8506bf3d4a4f8d2b908d801957414`.
- Pre-Stage-9 baseline/tag: `24b2679f8f487ebdbe65633c688996b1d36ea9eb`,
  `pre-stage09-baseline-v1`.
- Starting `main == origin/main`, clean and exactly at the design freeze, was
  verified before implementation. Stage 8 remained accepted and HOLDOUT sealed.
- Exact executable commit: `3c3864f0b42a6bc69d293415f7cd755c74187fc2`, pushed
  before submission and verified in a new clean detached Goethe Git clone.
- Accepted Stage 8 artifact:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9`.
- Stage 8 manifest SHA-256:
  `2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827`.
  Read-only Goethe shell rehash on 2026-09-08 matched; no address rows inspected.
- Stage 8 logical SHA-256:
  `9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526`.
Exact binding and implementation identities:

| Identity | SHA-256 |
|---|---|
| Stage 8 contract | 8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e |
| Stage 8 schema bundle | 6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f |
| Stage 9 input binding | 64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90 |
| Stage 9 contract | 6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9 |
| Stage 9 schema bundle | 7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716 |
| Question catalog | 1712b928d5ba5212a4377a0151083d6b088efaeb7493b180be7c1ff59534ec42 |
| Normalization | ee687e87c705396eecfa50dc521afd4c5a55a8034448738934b513cb542bc4c9 |
| Evidence semantics | 4183ef9dcac52212455e70756ec63ce5c2c485df3039d55486f6485a516f1fb7 |
| Reference lock | 61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63 |

Versions: `stage09_offline_reference_evidence_contract_v1`,
`stage09_offline_reference_evidence_profile_v1`,
`stage09_offline_reference_evidence_schema_v1`,
`stage09_lookup_normalization_v1`, `stage09_reference_manifest_v1`.
The data-bound profile fingerprint requires the computed public pack and will
be recorded from the scheduled job, not invented here.

| Logical relation schema | SHA-256 |
|---|---|
| reference_registry | 35f8c9e85437f0aafb755e9aafb654053307ff1da7d25e043c28d142c317b567 |
| reference_capability | e0e4d90193510041179edd0dbb84f2b625436668eb55d75b1d7892207c4a8fc1 |
| reference_object | d2af207938a9bbb25ed3718a68e8225414551c1a93c57c6b08fa66169ad57876 |
| candidate_reference_evidence | b0f9c93fbf4e72f0247b65586b72dbb47ff0b5e98a75ac3888798cb703b81e91 |
| reference_match_member | f2d08eea797a34f921fa8ddf639e8ad6ae1f0e5ee4f8dca26c1e5faedbdf08cc |
| coverage_summary | 4844b3e7f66b8337e24a51e8312ee5ac99be57c7cd8e277fbac2a7e9583be846 |

## Reference pack

The [lock](../../docs/scientific_assets/stage09_reference_pack_lock_v1.json) is
authoritative for the complete inventory, provenance, licenses and capability
limits. No reference has been refreshed or substituted.

| Frozen scientific asset | Version | SHA-256 |
|---|---|---|
| ISO 3166-1 JSON | iso-codes 4.20.1-1 | f01b812b57fba9f31ff621bf33e7c7570a01964dbeb5be2167e94decf538c89f |
| ISO 3166-2 JSON | iso-codes 4.20.1-1 | 78c90ef7fc25b5c2631aac5f089bc9ff6ec22c025c05b6ddbc087a1f1be2e46a |
| google-i18n-address wheel | 3.1.1 | f66f4fd2b75d1cd371fc0a7678a1d656da4aa3b32932279e78dd6cae776fc23d |
| actual all.json member | frozen 3.1.1 metadata | acc76495cb29c995e73d41dd2f0c51c87695b6395a767d439f7780403deb092f |
| GeoNames postal archive | 2026-09-07 snapshot | 5c89270e2192b157eb8014922158c1f8410b93ad4bc1e97225fe2e58cf46e074 |
| GeoNames allCountries.txt member | same snapshot | 2a9780179d77fe299e52226931bf1d170767928eca773374b0ec543e64c6d198 |

Families: ISO_CODES, LIBADDRESSINPUT_METADATA, GEONAMES_POSTAL. GeoNames negative
authority is FALSE. Missing metadata is NOT_EVALUABLE, absent recorded membership
is NOT_FOUND, and only frozen ISO code-ownership/eligible regex-prefix rules may
contradict their exact scoped claim. ISO licensing is LGPL-2.1-or-later; metadata
is CC-BY-4.0 with mirror BSD-3-Clause; GeoNames attribution/license history is
retained exactly in the lock. The public raw payloads remain ignored, not in Git.

Local public verification: all 25 locked bodies, 25 provenance headers and 263
archive members rehashed. Small public preparation observes 5,295 ISO objects,
12,261 metadata objects and 3,752 country-matrix capabilities. The public metadata
view is below 64 MiB after Arrow round-trip. All 1,255 supported regex patterns
pass ASCII-grammar/exact-engine compatibility probes; all 1,092 eligible frozen
examples pass. BH is excluded. No full GeoNames index was built on the Mac.

## Accepted population and planned execution

The only authorized input is the accepted 35,000-row DEVELOPMENT population:
51,779 exact candidates; 69,747 occurrences (34,822 STANDARD, 34,925 NATIVE);
6,106,088 ordered parser components. Those are upstream counts, not generated
Stage 9 results. Full hash/schema/count validation runs inside SLURM before
evaluation. No new authoritative source or occurrence map is produced.

One `general1` job requests four CPUs, 32 GiB, 24 hours, 8 GB bounded bulk DuckDB
memory and at least 256 GiB free private disk. It prepares the frozen public pack,
evaluates 16 disjoint candidate-range groups, replays them in reverse for logical
validation, and performs atomic publication/private/final reopening. The frozen
planning bound is 20.56M evaluation rows, not an expected hit count or measured
performance. Production resource requests cannot be inferred from this run.

### Single submission receipt

- SLURM job: `1770156`; submission UTC `2026-09-08T12:40:20Z`.
- State from the single submission-time `scontrol` query: PENDING;
  reason Resources; dependencies none. No further polling/cancellation/resubmission.
- Partition/account: `general1` / `footprint`; four CPUs, 32 GiB, 24-hour limit.
- Executable: `3c3864f0b42a6bc69d293415f7cd755c74187fc2`.
- Target artifact:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260908T124020Z_3c3864f0b42a`.
- Public pack target:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/public_pack/stage09_public_pack_20260907_v1_3c3864f0b42a`.
- Locked raw reference root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/public_raw/20260907_v1`.
  All 50 locked bodies/headers were copied (24 MiB total raw directory scale)
  and their exact hashes/0600 file/0700 directory modes verified on Goethe.
  Archive members were locally rehashed and are verified again inside the job.
- Integration root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/integration_stage09/3c3864f0b42a6bc69d293415f7cd755c74187fc2`.
- Runtime root:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d`.
  Interpreter/package paths were checked using shell metadata only; exact
  executable/runtime and filesystem preflight runs on the scheduled compute node.
- Logs: private `logs/slurm/safe-stage09-reference-evidence_1770156.out` and `.err`
  below the controlled project root. No row values are logged.

The original continuation command was:

```sh
ssh goethe 'sacct -j 1770156 --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,Start,End --parsable2'
```

The 2026-09-10 owner continuation observed a terminal failure, not a running
job. The subsequent read-only checks below reconcile that failure; no polling
loop, cancellation, resubmission or protected row inspection occurred.

### Terminal reconciliation — 2026-09-10

| Item | Observed result |
|---|---|
| Job/state/exit | 1770156 / FAILED / 1:0 |
| Start UTC | 2026-09-09T19:18:04Z |
| End UTC | 2026-09-09T19:18:09Z |
| Elapsed | 00:00:05 |
| Requested resources | 4 CPUs, 32 GiB, 24-hour limit |
| Scheduler allocation | 80 CPUs, 32 GiB, one node; not measured CPU use |
| MaxRSS | Accounting reported 0 for this short step; no usable peak-memory measurement |
| Execution location | Scheduled compute job; private PanFS project filesystem |
| Failure | ATOMIC_NO_REPLACE_FAILED in synthetic `_atomic_rename` preflight |
| Source/target state | Synthetic source directory/file preserved (0700/0600); rename target absent |
| Public derived pack | Not created |
| Protected Stage 8 payload access | Not reached; materializer invocation follows the failed preflight |
| Stage 9 evidence/publication | Not started; no evidence counts, candidate/profile/logical fingerprint, manifest or success marker |

The exact launcher and traceback establish the failing call: Linux
`renameat2(..., RENAME_NOREPLACE)` returned nonzero. The site and exact runtime
checks preceding it passed; the filesystem preflight success print was never
reached. This is an operational/publication-compatibility failure, not reference
evidence, address invalidity, an upstream scientific defect or a validated run.
No filesystem fallback was enabled and no execution guard was weakened.

The helper discarded `ctypes.get_errno()`, so the exact kernel error is **not
established**. Unsupported PanFS flag semantics is a hypothesis, not a proven
root cause. A local synthetic pass did not establish compute-filesystem support.
The frozen design's prohibition on unsupported publication primitives remains
binding; do not replace the operation with an unchecked check-then-rename race.

Preserved private diagnostic directory:
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/tmp/job_1770156`.
Only its 31-byte invented preflight sentinel exists. Log reconciliation:

| Private log | Bytes | SHA-256 |
|---|---:|---|
| safe-stage09-reference-evidence_1770156.out | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
| safe-stage09-reference-evidence_1770156.err | 777 | 23c1de40ff92e1d14447ee708f94832157adb581a59686c806e79eeb4a57b847 |

The exact detached executable checkout remains clean. The frozen reference
versions/lock, Stage 0–8 source and accepted fingerprints remain unchanged.
HOLDOUT is sealed; production/Pelias untouched. This continuation changes only
sanitized status/report documentation; no executable or reference changes.

### Proposed bounded step after the failure

Request one short, **synthetic-only SLURM filesystem diagnostic**, not a
DEVELOPMENT materializer retry. Commit/push its executable first. In a new
private diagnostic directory on the same filesystem, capture the numeric/symbolic
errno immediately after `renameat2` and test fresh-target and existing-target
collision behavior, directory fsync and same-invocation ownership. Retain all
invented sentinels and attempts; emit only fixed codes/OS numbers and aggregates.
Do not open Stage 8, address rows, reference payloads, HOLDOUT or production.

Use that evidence to determine whether a compatible implementation fix is
possible under the frozen publication contract. If the contract genuinely
requires a filesystem/design exception, obtain owner review before changing it.
Collect the complete compatibility defect ledger and test the correction before
requesting a new controlled DEVELOPMENT run. This proposal did not itself
authorize an additional job; no automatic retry was submitted.

### Synthetic-only filesystem diagnostic — authorized 2026-09-10

The owner's subsequent `continue` approved the specifically requested short
synthetic-only SLURM filesystem diagnostic. This is not authorization to rerun
DEVELOPMENT, change the frozen design or enable a publication fallback.

The diagnostic module `preprocessing/stage09_filesystem_diagnostic.py` and
[`stage09_filesystem_diagnostic.sbatch`](../../cluster/goethe_nhr/stage09_filesystem_diagnostic.sbatch)
accept no scientific input paths. They use the unchanged exact existing runtime
and a new clean detached Git executable. The new output directory is restricted
to the private Stage 9 `filesystem_diagnostics` parent. Original job `1770156`
and its sentinel/logs are never altered.

Six bounded cases are collected: NOREPLACE against an absent target, an empty
directory, a nonempty directory and a file; zero-flag rename against a fresh
target; ordinary POSIX rename against a fresh target. The last two are diagnostic
baselines only, never a materializer fallback, and never operate on an existing
target. Capture return code and numeric/symbolic errno immediately after the
native call. Check same filesystem, source/target sentinel preservation,
within-invocation ownership, before/after directory fsync and correspondence
between return code and observed effect. Retain all invented files/directories.

Resources: one CPU, 2 GiB, five minutes, `general1`, `--no-requeue`. Site/SLURM,
runtime, exact pushed/clean/detached executable and new/private output guards
precede creation. No Stage 8, references, HOLDOUT, production, network API or
materializer call is present. The report is an operational JSON diagnostic,
not Stage 9 evidence; no `_SUCCESS.json` or candidate publication is generated.
Successful diagnostic collection can report an unavailable primitive and must
not be interpreted as successful Stage 9 publication.

Local diagnostic tests: 18 pass, covering actual local synthetic rename/collision
behavior, unsupported errno values, native signatures/flags, stale-errno reset,
missing symbols, fsync errors, inconsistent syscall outcomes, private/existing
targets and guard-before-access. Mypy (94 source files), Ruff and format checks
pass. Error-handling/testing skills informed immediate errno capture and the
fault-injection checks. These tests do not establish PanFS behavior.

The complete safe local suite passes 710 tests (17.21 seconds); report/link
validation, CLI help, SBATCH syntax, source mypy, Ruff/format and frozen-contract
checks pass. No Stage 9 materializer source, scientific schema, reference lock
or accepted Stage 0–8 file is changed by the probe.

At preparation time, two bounded SSH attempts failed to resolve
`goethe.hhlr-gu.de`, and no job was submitted during that failure. The owner's
subsequent `nslookup`/`continue` request resolved both DNS and SSH connectivity.
The exact pushed diagnostic checkout was then prepared and verified clean and
detached before the single submission below.

Submit the diagnostic once after its executable commit/push; record the exact
job/SHA/output. If pending/running, stop without repeated polling or resubmission.
After completion, review only its synthetic result and establish the exact
compatibility issue before proposing a correction and DEVELOPMENT retry.

#### Diagnostic submission receipt

- Job: `1771054`; UTC submission `2026-09-10T11:16:01Z`.
- Single submission-time observation: PENDING, reason Resources, dependencies
  none; `Requeue=0`, `Restarts=0`. No further polling/cancellation/resubmission.
- Exact diagnostic executable: `4915852d874a11a5f437d6cfac8837b5f9b6ebd8`.
- Requested resources: one CPU, 2 GiB, five minutes; partition `general1`,
  account `footprint`. Actual allocation/use is not yet measured.
- New synthetic-only target:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/filesystem_diagnostics/stage09_fsdiag_20260910T111601Z_4915852d874a`.
- Result filename: `stage09_filesystem_diagnostic.json`. No result/hash or
  filesystem capability conclusion is claimed before collection.
- Exact detached integration checkout:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/integration_stage09/4915852d874a11a5f437d6cfac8837b5f9b6ebd8`.
- Runtime: the unchanged private Stage 6 runtime recorded above. No installation,
  dynamic source pull, reference refresh or shared-environment change.
- Private logs: `logs/slurm/safe-stage09-fsdiag_1771054.out` and `.err` under the
  controlled project root. No scientific input paths are passed to this job.
- Local continuation checks: all 18 diagnostic tests pass again; SBATCH syntax,
  exact main/origin identity and clean tree verified before submission. The
  earlier full local gate remains 710 passing tests.

On owner `continue`, inspect accounting once:

```sh
ssh goethe 'TZ=UTC sacct -j 1771054 --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,Start,End --parsable2'
```

If PENDING/RUNNING, stop again. If terminal, reconcile the exact synthetic report
and logs, including immediate errno, collision preservation, fsync and ownership
observations. Do not infer a materializer fallback or submit a DEVELOPMENT retry
from a successful diagnostic. Original job `1770156` remains a failed preflight;
no Stage 9 candidate exists and no Stage 0–8/ref-pack/scientific change is made.

#### Diagnostic terminal reconciliation — 2026-09-10

The next owner `continue` observed COMPLETED through one accounting query, then
read only this diagnostic's synthetic JSON, logs and checkout metadata. No new
job, protected input inspection, reference preparation or materializer invocation
occurred. Submission-time PENDING observations above remain historical receipts.

| Item | Observed result |
|---|---|
| Job/state/exit | 1771054 / COMPLETED / 0:0 |
| Start UTC | 2026-09-10T12:31:30Z |
| End UTC | 2026-09-10T12:31:33Z |
| Elapsed | 00:00:03 |
| Requested resources | 1 CPU, 2 GiB, five-minute limit |
| Scheduler allocation | 80 CPUs; allocation is not measured CPU use |
| MaxRSS | Batch accounting reported 0; no usable peak-memory measurement |
| Exact executable | 4915852d874a11a5f437d6cfac8837b5f9b6ebd8; detached checkout still clean |
| Kernel/platform | Linux 5.14.0-611.9.1.el9_7.x86_64 |
| Exact semantic runtime | Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, DuckDB 1.5.5 |
| Output meaning | Synthetic filesystem diagnostic only; not a Stage 9 candidate or publication success |

All six cases used same-filesystem source/target locations in the private PanFS
project tree. Every before/after directory fsync succeeded (12 observations).
No unexpected mutation or inconsistent return-code/effect pair was observed.

| Case | Native result / errno | Observed effect |
|---|---|---|
| NOREPLACE, absent target | -1 / 22 EINVAL | Source intact; target still absent |
| NOREPLACE, empty-directory collision | -1 / 17 EEXIST | Source and original target intact |
| NOREPLACE, nonempty-directory collision | -1 / 17 EEXIST | Source and original target intact |
| NOREPLACE, file collision | -1 / 17 EEXIST | Source and original target intact |
| renameat2, zero flags, absent target | 0 / 0 | Source moved intact; same-invocation identity preserved |
| POSIX rename, absent target | 0 / 0 | Source moved intact; same-invocation identity preserved |

`noreplace_supported_in_this_probe=false` and
`all_observed_effects_consistent=true`. The fresh-target flag-dependent failure
establishes incompatibility of the current no-replace publication operation in
this observed kernel/filesystem environment. It does not identify an internal
PanFS defect, establish behavior on every PanFS installation, or recover the
discarded errno from original job `1770156`. That original error remains unknown;
the later probe reproduces the failing operation with immediate errno capture.

The existing collision checks are useful but do not compensate for failure to
publish a fresh target. Successful ordinary-rename baselines establish only the
tested fresh-target behavior. They do not prove a race-free no-overwrite protocol;
an existence check followed by ordinary rename is not an approved replacement.
Directory fsync returning success likewise is not a power-loss durability test.

The report remains in the exact synthetic target recorded above. Its bytes were
independently retrieved and SHA-256 checked locally, then its job/executable/
runtime/scope, all six case results and all preservation/ownership/fsync fields
were checked against the observed results. Only these sanitized summaries and
hashes enter Git; the diagnostic tree and logs remain private and preserved.

| Private diagnostic file | Bytes | SHA-256 |
|---|---:|---|
| stage09_filesystem_diagnostic.json | 4719 | 8742918b6647ef4283a1f5445a6240c84009239257c782ee367903c30549ed5a |
| safe-stage09-fsdiag_1771054.out | 740 | c22ef98b0b007aae75b2f6131bf2126627cddc5eeacc8f5f200ddc06ea71ebbb |
| safe-stage09-fsdiag_1771054.err | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

These files are 0600; the diagnostic's topology validation required 0700
directories, 0600 regular files and no symlinks/hardlinks. The probe's scope and
executable contain no protected/reference input reads or network API calls.
Reported protected/reference payloads opened and network calls are all zero;
materializer/fallback/candidate flags are all false. No scientific success marker
was created. This is a completed diagnostic, not a successful DEVELOPMENT run.

#### Complete bounded compatibility ledger and next decision

| Issue | Evidence and disposition |
|---|---|
| Fresh no-replace publication is incompatible with the observed environment | EINVAL on an absent target while zero-flag/POSIX baselines succeed; current preflight remains fail-closed |
| Original helper loses the native error | Original job's errno is unrecoverable; diagnostic now captures it immediately. Any approved correction must retain fixed numeric/symbolic diagnostics without printing input values |
| Baseline success does not establish collision safety | No check-then-rename fallback. A replacement must explicitly preserve no-overwrite, ownership, fault reconciliation and immutable final-path semantics |
| Local synthetic behavior did not prove Goethe compatibility | Any approved protocol needs its complete local fault/race suite and one separately authorized synthetic compute-filesystem validation before requesting a DEVELOPMENT retry |
| Successful syscall/fsync observations have limited scope | No claim of global PanFS support, actual power-loss durability, address evidence, candidate publication or Stage 9 acceptance |

All findings were collected before this reporting-only update. No scientific
contract, reference version, schema, Stage 0–8 source/fingerprint or materializer
executable was changed. The operational blocker is **not resolved** merely by
recording it; there is no approved replacement protocol yet.

Proposed next bounded step, requiring owner approval: prepare a publication-only
compatibility revision for review. Evaluate exclusive per-run namespace ownership
followed by atomic fresh-child rename on the supported filesystem, with an
explicit concurrency/threat model, exact final topology and failure/reopen tests.
This is a proposal to assess, not a claim of equivalence to kernel no-replace.
Concurrent writers, foreign-target preservation, stale ownership, ambiguous
post-rename failure, pre-success interruption, fsync failure and last-operation
ownership checks must all be addressed together. If that cannot preserve the
frozen guarantees, report the required filesystem/design exception instead of
weakening them. No Stage 0–8 change or protected input is needed for that review.

Do not implement a fallback, change the frozen design, submit another synthetic
job or retry DEVELOPMENT on the authority of this completed diagnostic alone.
Owner review of the bounded publication correction is the next gate.

Reconciliation validation: 710 safe local tests pass (17.41 seconds), including
the 18 diagnostic tests and Stage 7/8 regressions. Report/link validation, strict
source mypy (94 files), Ruff lint/format (140 files), both Stage 9 SBATCH syntax
checks and `git diff --check` pass. The changed-file/privacy review contains
only four sanitized Markdown documents, no generated payload or executable.
Direct Git comparison with the design-freeze commit confirms accepted Stage 7/8
source/tests/contracts/reports and execution guards are unchanged; frozen Stage 9
design/reference-lock hashes still match. There is no unexpected runtime-guard
result or local test failure. These local passes do not resolve the observed
Goethe publication incompatibility.

### Publication-protocol revision — design/local-only owner authorization

Following the completed diagnostic, the owner explicitly authorized preparation
of a bounded publication-protocol revision for review, with synthetic/local tests
only. No cluster probe or DEVELOPMENT retry was authorized or submitted; no
protected Stage 8 payload, HOLDOUT, production or Pelias was accessed.

The [revision candidate](../../docs/stages/STAGE09_PUBLICATION_PROTOCOL_REVISION.md)
selects exclusive permanent run reservation plus fully validated registration and
an atomic empty commit seal. No rename, hard-link, symlink or stale-lock takeover
is required. Existing ordinary creation/fsync observations and cited POSIX
semantics support the choice; no new PanFS capability probe is required to
present it for review. Namespace visibility and durable acknowledgment remain
distinct, and unverified postcommit outcomes explicitly require reconciliation.
Exact accepted publications can be adopted; conflicting/incomplete keys are
preserved and fail closed. This is operational publication, not Stage 9 scientific
acceptance or a new evidence state.

The executable model and fault tests live only under `tests/`. The active
materializer, public-pack builder, terminal validator, launcher and generic
publication infrastructure are unchanged. The addendum lists their exact future
integration delta, including requiring the seal in all readers. Frozen Stage 9
science/design/reference bytes and Stage 0–8 source/fingerprints are unchanged.
The complete bounded defect ledger is in the addendum; no deployment-ready fix
or successful DEVELOPMENT artifact is claimed. Stop at owner review of the
publication-protocol proposal, not at another job submission.

Local revision gate: 62 focused model tests pass; the complete safe suite passes
772 tests (17.81 seconds), including Stage 7/8 regressions. Mypy passes for 94
installed source files plus the model; Ruff lint/format (142 files), report/link
and whitespace validation pass. Only the design addendum, two tests-only Python
files, this report and three current documentation/decision records changed.
No executable publication infrastructure changed. Skills informed the bounded
protocol/fault review; they did not authorize another run or broader refactor.

### Exclusive-create diagnostic — owner authorization 2026-09-10

The owner conditionally approved the publication protocol in principle but
withheld integration until direct PanFS exclusive-create evidence exists. This
supersedes the earlier proposal's no-additional-probe conclusion. Exactly one
new synthetic-only Goethe SLURM diagnostic is authorized, not a DEVELOPMENT
retry or protected/reference input access.

Executable module: `preprocessing/stage09_exclusive_create_diagnostic.py`.
Launcher:
[`stage09_exclusive_create_diagnostic.sbatch`](../../cluster/goethe_nhr/stage09_exclusive_create_diagnostic.sbatch).
It reuses the unchanged fail-closed diagnostic site/runtime/path/executable
guard, takes only a new synthetic output path and exact executable SHA, and
requires the measured filesystem type `panfs` for cluster confirmation.

Ten cases: three sequential fresh/collision tests (sentinel file, `_COMMITTED`,
permanent mkdir reservation); three four-process races for those same primitives;
four existing/dangling symlink cases for open and mkdir. Each independent spawned
process reports ready through anonymous unidirectional pipes; the parent releases
GO only after all four are ready. Worker identities/start times and exit status
are checked. Exactly one creator must win, all losers must report EEXIST, and
the resulting sentinel must match that winner. Three repeated no-follow reopens
check bytes/modes/single-link topology. Capture native return/errno immediately,
plus file and parent-directory fsync results; no truncation or rename fallback.

The exact zero-byte seal cases use `_COMMITTED` beside fixed invented metadata
in nested synthetic case directories. There is no scientific success marker at
the diagnostic root. Four deliberately created symlinks are allowed only at
their exact fixed fixture paths to fixed within-case referents; this is not a
relaxation of any publication topology validator. All fixtures and attempts are
preserved, directories 0700 and ordinary files 0600. Only a probe's own stalled
child processes may be terminated on timeout, never a SLURM job or prior attempt.

Resources: one node, one requested CPU, 2 GiB, five minutes, `general1`, account
`footprint`, no requeue. Login-node checks are shell/Git metadata only; no Python
or data processing is run there. Shell inspection confirms the approved
`filesystem_diagnostics` parent is private and on PanFS, and the existing exact
runtime is available. No reference or protected payload is passed to the probe.

Pre-submission review collected and resolved the new probe's issues: native
`open` is variadic (only fixed arguments in ctypes argtypes; explicitly typed
mode), preventing a Mac arm64 calling-convention error observed by the local
mode tests; collision checks must never write on unexpected sequential success;
workers require a real all-ready barrier rather than merely near-simultaneous
launch; outcome/PID correspondence, symlink fixture scope and exact topology
must be verified. The variadic declaration follows
[Python ctypes guidance](https://docs.python.org/3/library/ctypes.html#calling-variadic-functions).
These are diagnostic-only corrections, not publication/scientific changes.

Local focused gate: 18 diagnostic tests pass, including the real local spawned
process cases, immediate errno/signatures, stale errno, failed primitives,
symlink preservation, fsync errors, privacy/execution guard and launcher syntax.
The full safe local suite passes 790 tests (18.09 seconds), including accepted
Stage 7/8 regressions. Strict source mypy (95 files), Ruff lint/format (144 files),
report/link validation, CLI help, shell syntax and whitespace checks pass.
The raw reference lock/frozen design hashes and accepted Stage 7/8 source/tests/
contracts/reports are unchanged. Existing materializer, publication helper,
DEVELOPMENT launcher and earlier diagnostic sources are byte-for-byte unchanged.
No PanFS capability result is claimed until the scheduled diagnostic is complete.

#### Exclusive-create diagnostic submission receipt

- Job `1771149`; submission UTC `2026-09-10T15:10:06Z`.
- Single submission-time observation: PENDING, reason Priority, dependencies
  none, `Requeue=0`, `Restarts=0`. Stop without polling/cancellation/resubmission.
- Exact pushed diagnostic executable:
  `a9e6ede7c8aa45f8f11b0eadc797839e46c5b057`.
- Clean detached Git checkout:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/integration_stage09/a9e6ede7c8aa45f8f11b0eadc797839e46c5b057`.
  HTTPS cloning lacked credentials on Goethe; the existing approved checkout's
  configured Git remote successfully supplied the new clone. No source rsync,
  credential printing or old-checkout mutation occurred.
- New synthetic output:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/filesystem_diagnostics/stage09_fsdiag_20260910T150932Z_a9e6ede7c8aa`.
- Result filename: `stage09_exclusive_create_diagnostic.json`; no hash or
  capability confirmation is invented before completion.
- Requested resources: `general1`, account `footprint`, one node, one task,
  one CPU, 2 GiB, five minutes, no automatic requeue.
- Existing unchanged runtime:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d`.
- Private logs: `logs/slurm/safe-stage09-excldiag_1771149.out` and `.err` under
  the controlled project root. No protected/reference input is supplied.

On owner `continue`, inspect accounting once:

```sh
ssh goethe 'TZ=UTC sacct -j 1771149 --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,Start,End --parsable2'
```

If still pending/running, stop. If terminal, reconcile only the exact synthetic
report, syscall/errno and collision/barrier/sentinel/seal/reservation/fsync/
reopen/topology evidence. A passing capability result is not permission to
integrate or retry DEVELOPMENT. Stop for explicit owner integration authorization.
Original jobs `1770156`/`1771054`, Stage 0–8 and frozen Stage 9 science/references
remain unchanged; HOLDOUT sealed, production/Pelias untouched.

#### Exclusive-create terminal reconciliation — 2026-09-10

STAGE09_EXCLUSIVE_CREATE_PANFS_CAPABILITY_CONFIRMED.
The owner continuation observed COMPLETED through one accounting query. Only
the exact synthetic report, logs, retained fixture hashes/topology and detached
checkout metadata were read subsequently. No additional job or integration.

| Execution item | Observed value |
|---|---|
| Job/state/exit | 1771149 / COMPLETED / 0:0 |
| Exact diagnostic executable | a9e6ede7c8aa45f8f11b0eadc797839e46c5b057 |
| Start/end UTC | 2026-09-10T15:10:14Z / 2026-09-10T15:10:19Z |
| Elapsed | 00:00:05 |
| Requested | One node, one CPU, 2 GiB, five minutes; general1; no requeue |
| Scheduler CPU allocation | 80 CPUs; not measured CPU usage |
| MaxRSS | Batch accounting reported 0; no usable peak-memory measurement |
| Filesystem/kernel | panfs / Linux 5.14.0-611.9.1.el9_7.x86_64 |
| Runtime | Python 3.14.3, Unicode 16.0.0, PyArrow 25.0.0, DuckDB 1.5.5 |
| Checkout | Exact executable HEAD, still clean and detached |

The native open flags were `131265` on this Linux runtime:
O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, with requested mode 0600 and no
O_TRUNC. Native mkdir requested 0700. Errno was captured immediately after
each tested call, independently of later write/fsync/close observations.

| Case | Result |
|---|---|
| Fresh sentinel record | open returned descriptor 4, errno 0; exact 35-byte contents |
| Second record create | -1 / EEXIST (17); same-invocation identity and bytes preserved |
| Fresh `_COMMITTED` | open returned descriptor 4, errno 0; exact empty file, bound synthetic metadata unchanged |
| Second seal create | -1 / EEXIST (17); empty seal unchanged, no truncation/replacement |
| Fresh permanent run reservation | mkdir returned 0, errno 0; owner sentinel and private directory intact |
| Second reservation | -1 / EEXIST (17); directory identity and owner sentinel preserved |
| Concurrent sentinel | Four independent processes; one winner (worker 0, descriptor 8), three -1/EEXIST losers |
| Concurrent `_COMMITTED` | Four independent processes; one winner (worker 0, descriptor 8), three -1/EEXIST losers |
| Concurrent reservation | Four independent processes; one winner (worker 1, mkdir return 0), three -1/EEXIST losers |
| Existing/dangling symlinks, open/mkdir | All four returned -1/EEXIST; links and referents unchanged, missing referents remain absent |

Every race had four distinct worker PIDs, all-ready-before-release synchronization,
worker/result identity correspondence and clean worker exits. The recorded
attempt-start spreads were 202,610 ns (record), 173,681 ns (seal), and 158,049 ns
(reservation). These are bounded same-node multi-process observations, not
proof of simultaneous CPU execution, cross-node behavior or performance limits.
The required winner/loser and exact-content semantics all passed.

Final nonempty race sentinels were exactly those of the corresponding winners:

| Fixture | SHA-256 |
|---|---|
| Sequential record/reservation sentinel | 039d248921bd1fc68ccbbb6e1de21c3be85ec8bd8e3a921bf9cf4c1dbdefd6cc |
| Concurrent record, worker 0 | 24cb9f14731f07714e175cbf81aaec0c57a45927b3e7cab710f2005a299721f4 |
| Concurrent reservation, worker 1 | b9f80fb5bf3f2c94d1c37805eac4f2244df015a3622d913d3f174bf4de5c62a9 |
| Both empty commit seals | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

All 23 recorded parent-directory fsync observations passed. Successful creators'
post-create file/directory I/O checks passed. All 18 recorded repeated no-follow
reopens passed exact bytes/size, owner, 0600 and single-link checks. The complete
synthetic topology remained private: directories 0700, ordinary files 0600 with
one link, and exactly four retained deliberate symlinks restricted to their
fixed within-case synthetic referents. This does not weaken publication's
no-symlink policy. No scientific success marker exists at the diagnostic root.

Independent reconciliation retrieved the report bytes again and checked its
SHA-256 before parsing; verified job/executable/runtime/scope and every native
case/result; recomputed each expected sentinel hash; then compared a separate
shell-generated inventory of all **11 regular files** with the exact expected
hashes, including both synthetic metadata files and all retained referents.
Shell metadata independently reconfirmed modes/owner/link counts and the four
expected symlinks. No remote Python/data processing ran on the login node.

| Private report/log | Bytes | SHA-256 |
|---|---:|---|
| stage09_exclusive_create_diagnostic.json | 16898 | e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35 |
| safe-stage09-excldiag_1771149.out | 183 | 034c6edba600a8c3ae67c4ae7aea1faf9762c19cdb36d6a416d7efbf0cae1116 |
| safe-stage09-excldiag_1771149.err | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |

The report and logs are 0600 and remain at the exact paths in the submission
receipt. All synthetic fixtures are retained. Reported protected/reference
payload opens and network API calls are zero; materializer, protocol integration,
DEVELOPMENT retry and Stage 9 candidate flags are false. The inspected executable
has no scientific input arguments or loaders in this diagnostic path.

The owner's specific environment-evidence gate is satisfied for the tested
same-node PanFS operations. No cross-node, power-loss or end-to-end integrated
publication guarantee is inferred. The original no-replace failure remains
truthful, and the active materializer is still unchanged/fail-closed. Nothing
here authorizes integration, another diagnostic or DEVELOPMENT execution.
Error-handling guidance informed separate syscall/effect/status reconciliation;
completion alone was not treated as capability evidence. Stop for owner
authorization to integrate the publication protocol. Stage 9 remains NOT ACCEPTED.

Reconciliation's safe local gate: 790 tests passed (17.43 seconds), including
Stage 7/8 regressions; strict source mypy (95 files), Ruff lint/format (144 files),
report validation and whitespace checks passed. Only five sanitized documentation
files changed. Source, tests, launchers and scientific assets are unchanged from
the submission record; accepted Stage 7/8 assets and frozen Stage 9 design/lock
remain byte-identical to their checked baselines.

## Corrected publication integration and bounded pre-retry review — 2026-09-10

Owner approval starts from clean exact main/origin-main
`a2949199ea47ad453d3441e9f46429b395b00274`. Approved protocol candidate
`96d17e763addc21b0a1c321c3a03666e928c25c7` and diagnostic executable
`a9e6ede7c8aa45f8f11b0eadc797839e46c5b057` are ancestors. Job `1771149`'s
retained report hash is `e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
Read-only shell inspection found both controlled Stage 9 DEVELOPMENT/public-pack
namespaces empty before edits; no candidate existed to migrate or overwrite.
Original failed job `1770156`, its checkout and all diagnostic artifacts remain
untouched. Frozen Stage 9 design/reference bytes and accepted Stage 7/8 inputs
are unchanged; no protected strings were inspected.

Integration adds one Stage 9-local reusable operational helper, not a project-wide
refactor. Both reference-pack and candidate adapters use permanent exclusive
mkdir ownership, canonical `_SUCCESS.json` registration, full prepared validation,
fsync and exclusive empty `_COMMITTED` creation. Exact committed reopening and
all existing scientific validators are required. Historical no-replace diagnostic
code remains, but neither active publication nor corrected launcher preflight
calls it. No ordinary rename fallback or destructive demotion exists.

The protocol string is the exact reviewed `exclusive_run_commit_seal_v2_candidate`.
Its operational registration fingerprint and streaming file-inventory fingerprint
do not change the Stage 9 contract/profile/schema/logical formulas. Public pack
registration binds the raw lock; candidate registration binds the exact published
pack manifest and accepted Stage 8 binding. Job/runtime provenance remains in the
manifest; public-pack provenance now also records its execution job and protocol.
Registration is not itself acceptance, and a seal alone cannot validate a bundle.

Review collected the complete bounded operational ledger before final corrections:

| Concern | Resolved disposition |
|---|---|
| Unsupported rename in either publisher or preflight | Both adapters use the new helper; preflight exercises fresh/colliding mkdir, exclusive sentinel and exact empty seal with fsync/reopen |
| Check-then-act race / concurrent overwrite | mkdir and O_EXCL arbitrate; only the reservation winner builds, losers never write |
| Stale/incomplete reservation | Never taken over or repaired; age and same executable confer no ownership |
| Registration partial write / precommit crash | Prepared record is not success; no seal until full prepared validation and sync |
| Uncertain seal return/effect | One bounded owned exact reconciliation; ADOPT only if full committed validation succeeds |
| Descriptor close failure after effect | Teardown is inside outcome reconciliation; final ownership/record checks occur after all publication descriptors close |
| Persistent postcommit I/O failure | Explicit unverified/uncertain FAIL_CLOSED, with seal and evidence preserved for later exact adoption; CLI retains a fixed uncertainty diagnostic without exposing arbitrary errors |
| Content-equal foreign directory / historical inode gate | Same-invocation ownership guards writer reconciliation; cross-job adoption verifies exact content/key/provenance, never old inode values |
| Adoption exposure in actual materializer/CLI | External expected-manifest option and full read-only consumer path; no self-pinning and no rebuild of committed output |
| Launcher resolving prohibited symlinks away | Resolve only configured mount alias; verify canonical private parents and reject artifact symlinks |
| Reader opens before topology checks | No-follow owner/mode/type/single-link inventory check before manifest/data validation; parse the exact verified manifest bytes |
| Registration encoding and full bindings | Compact canonical ASCII JSON and reviewed domain-separated ID match the independent synthetic model byte-for-byte |
| Output/reporting failure | Presentation remains isolated after verified outcome; tests prove broken stdout does not modify/demote committed bytes |
| Science, lineage, negative authority and scale | Existing bounded engines/validators and all scientific formulas unchanged; added bookkeeping is per run/file inventory, not per candidate/source row |

No unresolved scientific contradiction or upstream blocker was found. Error-handling
and testing skills informed explicit uncertainty handling and parameterized faults;
no scientific rule or runtime guard was weakened. Synthetic tests cover every
required owner case without protected/reference input dependencies. The full suite
also separately verifies the exact optional public reference lock, not a refresh.

Local gate: 62 integrated publication tests; 62 retained approved-model tests.
Full safe suite: 836 passing tests (17.40 seconds), including Stage 7/8 regressions.
The separate Stage 7/8/execution-policy gate passes 164 tests (5.70 seconds).
Strict source mypy passes for
96 files; Ruff lint/format passes for 145 files. Exact Python 3.14.3 / Unicode 16 /
PyArrow 25.0.0 / DuckDB 1.5.5 is retained. Expected guard rejection is tested;
there is no unresolved runtime guard or remaining real failure.
CLI help/contract display, report/link validation, JSON/lock validation,
SBATCH shell syntax, changed/tracked-data privacy audit and whitespace checks
also pass. Exact-runtime negative guard tests remain fail-closed; no bypass.

The corrected run will use a new publication key and exact pushed detached
executable, four requested CPUs, 32 GiB, 24 hours, general1, no requeue, and no
dependencies. All protected validation remains inside SLURM. Submission occurs
only after final static/document/lock checks and pre-submission reconciliation.
Stop if pending/running; no second corrected submission is authorized.

Pre-submission read-only reconciliation: all 50 frozen public bodies/provenance
headers on Goethe matched the lock; exact inventory, 0600 single-link files and
0700 root were checked. All 263 archive-member identities are separately checked
by the local public-lock tests and will be verified again inside SLURM. Accepted
Stage 8 manifest rehash matched `2a50bd8c…`; its root/manifest/success modes were
private and IN_PROGRESS absent. No Stage 8 relation payload was opened by these
login-node shell checks. The exact existing runtime is executable, and reported
PanFS free capacity exceeds the 256 GiB guard (capacity is not a personal quota
guarantee). Full input/inventory/candidate verification remains a scheduled job
gate before evaluation. No reference refresh or new public acquisition occurred.

## Historical original validation and complete pre-submission defect ledger

Local runtime is exact Python 3.14.3/Unicode 16.0.0, PyArrow 25.0.0, DuckDB 1.5.5.
The runtime guard was not weakened to use installed Python 3.14.7. Tests use
invented addresses and optionally the exact public assets, never protected rows.

Final local gate (2026-09-08):

- PASS: 131 focused Stage 9 tests, including exact public-lock and regex checks.
- PASS: 164 Stage 7/8 and execution-policy regressions (including all 45 Stage 8 tests).
- PASS: complete safe local suite, 692 tests, 16.23 seconds.
- PASS: strict source mypy, 93 source files; Ruff lint; Ruff format check, 138 files.
- PASS: CLI help/contract display, SBATCH `bash -n`, JSON decoding, report/link
  validation, changed-file/tracked-payload/privacy audit and `git diff --check`.
- PASS: frozen Stage 9 design/lock hashes and accepted Stage 7/8 code/report
  identities unchanged. Source-stage fingerprints are also asserted in tests.
- EXPECTED_RUNTIME_GUARD: deliberately exercised in negative tests; no bypass
  or unresolved runtime-guard result in the exact-runtime gate.
- REAL_FAILURE: zero remaining. All collected pre-run issues below are resolved.

The pipeline/testing/error-handling skills informed bounded streaming, explicit
fail-closed errors and fault-injection tests; the performance and code-review
skills informed the memory measurement and complete pre-run review.

The bounded self-review collected the following implementation issues and
resolved them together before any executable commit or DEVELOPMENT submission:

| Issue | Resolution/evidence |
|---|---|
| Shared `/work` mount alias rejected resolved paths | Compare resolved approved root; lexical/resolved HOLDOUT/production checks remain |
| Public metadata view initially exceeded 64 MiB | No redundant runtime enumeration-capability copy; local public-string interning; measured bound test |
| Stage 8 success marker literal mismatch | Reuse accepted Stage 8 marker constants; synthetic full consumer inventory/schema fixture |
| GeoNames admin OR join could expand country cross-products | Separate equality hash-join branches; deduplicate identical record witnesses retaining every matching admin field |
| Public self-consistent hashes did not prove raw projection | Full raw-object comparison, exact registry/capability regeneration, independent index projection; mutation tests |
| Lookup collision guard was task-local only | Compare full normalized request keys across replay task groups; deliberate cross-shard collision test |
| Country/key index physical order needed separation from hash order | Physically country/postcode ordered index; externally canonical object-ID logical hashing |
| Source/occurrence incidence risk of broadcasting source evidence | Source evidence restricted to its own source; parser evidence maps to all occurrences; synthetic shared-candidate tests |
| Giant repeated parser roles and cache growth | Streaming singleton counters/ordinal atomic questions; fixed cache bounds; 881,338-component and giant-scalar tests |
| Prefix ambiguity/conflicting frozen rules | Explicit unresolved/internal-conflict abstention; all applicable prefix predicates checked |
| Decimal aggregate serialization and output allowlist | Cast aggregate sums to unsigned integers; reject extra columns before Arrow coercion |
| Terminal rename race/ambiguous outcome/foreign equal contents | Kernel no-replace rename, owned post-effect adoption only, final ownership check, parent-fsync/copy-race/presentation fault tests |

No unresolved design contradiction, Stage 0–8 blocker or semantic contract change
was found. The same-executable deterministic replay does not replace the required
independent review. Resource/throughput sufficiency remains to be observed in the
one authorized execution; failures remain failures and preserve attempts.

One reporting-only integration issue was found while recording submission:
after the new Stage 9 report became Git-tracked, the report validator's exact
file allowlist still listed only the historical Stage 0–8 report surface. The
reporting commit adds this one explicit Markdown path; it does not change the
accepted-stage range, any accepted fingerprint/check or any execution source.
The report-validator regression tests pass after this bookkeeping correction.
The in-flight executable remains exactly `3c3864f0b42a6bc69d293415f7cd755c74187fc2`;
no cancellation, resubmission or output-semantic change is needed or performed.

## Candidate diagnostics and acceptance gate

After success, report only sanitized totals and country/question/reference
coverage with explicit denominators: candidate total/evaluable/no-evidence,
four-state counts, capability/family usage, postcode/locality/admin checks,
authority-scoped contradiction counts, GeoNames mismatch counts, not-found and
not-evaluable counts, technical failures and every logical relation row count.
Investigate aggregate anomalies without opening address strings. A large support
rate is not accuracy; unsupported capability successes and GeoNames contradictions
are errors, not evidence. Report physical/logical/schema/reference fingerprints,
manifest/success binding, runtime/resources and complete reopen validation.

No candidate metric or logical dataset/profile/public-pack output fingerprint is
invented before execution. No generated Stage 9 evidence is committed to Git.

## Downstream handoff and limitations

BOUNDARY_HANDOFF_SUFFICIENT through unchanged Stage 8 → Stage 6/source-line
lineage. No Stage 0–8 source, scientific contract or fingerprint is modified.
Reference lineage remains explicit for later dependence handling. Stage 10,
HOLDOUT, production, Pelias and geocoding remain outside this authorization.
The stage ends at a DEVELOPMENT candidate awaiting independent review, not
STAGE_9_ACCEPTED.

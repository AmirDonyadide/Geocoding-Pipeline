# Stage 9 DEVELOPMENT execution record

## Status

Current: **STAGE_9_ACCEPTED** (owner acceptance, 2026-09-14, D060).
Independent review PASS; candidate defects = **0**. No scientific output change
or DEVELOPMENT rerun is required. Stage 10 is **NOT STARTED**.

## Owner acceptance and freeze — 2026-09-14

The owner explicitly accepts the exact DEVELOPMENT artifact below after
[independent review PASS](../../review/stage09_independent/FINAL_REVIEW.md).
The final [portable review evidence](../../review/stage09_independent/REVIEW_EVIDENCE.json)
records 100 artifact checks PASS and no failed checks. Independent review also
confirmed 836 candidate tests and 23 additional public/synthetic checks PASS,
publication/inventory/reopening, relation integrity, frozen input/reference
bindings, all scientific checks, normalization and privacy/execution policy.
The review's informational limitations are retained; candidate defects = 0.
Review-harness fixes and its failed job `1771693` remain distinct preserved
history, not candidate defects or grounds for a DEVELOPMENT rerun.

### Exact accepted identity

| Binding | Accepted value |
|---|---|
| Scientific status / scope | STAGE_9_ACCEPTED / Benchmark V1 DEVELOPMENT only |
| Executable | `3e10ac7c1309c2636f35c0709fa283305d60d998` |
| Candidate reporting commit | `1c7182931fd4be2a7d5dee00d3105a1e54377bae` |
| DEVELOPMENT job / state / exit | `1771191` / COMPLETED / `0:0` |
| Elapsed / peak RSS | 08:04:53 / 9.657 GiB |
| Publication key | `stage09_development_20260910T155542Z_3e10ac7c1309` |
| Manifest SHA-256 | `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240` |
| Logical dataset fingerprint | `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3` |
| Contract fingerprint | `6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9` |
| Profile fingerprint | `b12be7ba06de2360ba7cd9b971c4b562b1c8df5d25c30024975869fd2b34efd1` |
| Schema bundle fingerprint | `7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716` |
| Accepted Stage 8 input binding | `64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90` |
| Frozen reference-pack manifest | `dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a` |
| Frozen reference lock SHA-256 | `61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63` |
| Independent review branch | `review/stage09-independent-20260912` |
| Final independent review evidence commit | `a9ae443ca140627acf1712886670f39f227c1dc6` |
| Independent review job / state / exit / elapsed | `1772139` / COMPLETED / `0:0` / 01:00:30 |
| Non-squash review merge | `8a43e6a8baba5fe8e1cb366c6b811b01f1ad2d8e` |
| Acceptance tag | `stage09-offline-reference-evidence-v1` (annotated, final owner-acceptance state) |
| Candidate defects / scientific output change / rerun required | 0 / No / No |

Accepted artifact (unchanged):
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309`.

The merge preserves both candidate and independent-review ancestry, including
all six review commits and review-harness history. Acceptance is this owner
decision plus its annotated Git tag: it does **not** rewrite the artifact,
manifest, registration, seal, frozen design/reference bytes, or historical
candidate-era `stage09_accepted: false` fields. Those fields truthfully describe
publication before owner review. The tag resolves the final acceptance commit;
the executable remains the distinct exact SHA above.

### Accepted scientific interpretation and limitations

- Stage 9 is OFFLINE REFERENCE EVIDENCE only, never source correction, address
  validity, parser correctness, final geographic truth or geocoding accuracy.
- The four states remain SUPPORTED, CONTRADICTED, NOT_FOUND, NOT_EVALUABLE.
  NOT_FOUND != CONTRADICTED. GeoNames negative authority remains FALSE;
  GeoNames CONTRADICTED = 0. Association mismatch is diagnostic, not invalidity.
- Q04 = 54,022 / 90,043 = **59.995780%** contradicted, denominator explicitly
  the evaluable postcode-pattern reference-rule checks (SUPPORTED + CONTRADICTED),
  not addresses or distinct candidates. Independent classification **A —
  scientifically plausible and correctly implemented** is accepted. This is
  not an invalid-address percentage. Repeated parser-component ordinals can
  materially weight evidence-row denominators; all future reports must keep
  denominators explicit and must not substitute candidate/source-row incidence.
- All 51,779 country assessments are unresolved under the frozen full-subdivision-
  witness rule: independent review found zero qualifying full subdivision-code
  witnesses. Country assessment supplies no resolving signal for this DEVELOPMENT
  population. This expected limitation does not invalidate other Stage 9 evidence.
- BOUNDARY_HANDOFF_SUFFICIENT through unchanged Stage 8 → Stage 6/source-line
  lineage. Stage 8 remains the sole authoritative source/occurrence map.
  Stage 0–8 science is unchanged. Production-scale capacity remains unproven.

### Accepted Stage 9 publication protocol

Exclusive permanent reservation → immutable validated artifact → registration
→ atomic exclusive `_COMMITTED` seal → reopen/full validation is accepted for
Stage 9. Directory, reservation or registration existence alone is never success.
Exact content/provenance identity, not historical cross-job inode equality,
governs adoption. No overwrite, stale takeover or racy rename fallback is allowed.

Approved protocol candidate: `96d17e763addc21b0a1c321c3a03666e928c25c7`.
PanFS environment evidence: job `1771149`, diagnostic SHA-256
`e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
`O_CREAT|O_EXCL` is the demonstrated Stage 9 atomic collision primitive.
`RENAME_NOREPLACE` is incompatible with the tested PanFS path (`EINVAL`, job
`1771054`); that evidence and failed DEVELOPMENT attempt `1770156` are preserved.
Accepted Stage 8 publication semantics/artifacts are not changed retroactively.
Reuse in Stages 10+ requires checking the same publication assumptions, controlled
path and filesystem remain applicable; acceptance grants no later-stage work.

### Safe owner-acceptance gate

Acceptance checks passed on the exact Python 3.14.3 runtime; no runtime guard
was weakened:

- **60 tests PASS**: `tests/test_stage09_reference_contract.py`, accepted Stage 8
  runtime-fingerprint guard, Stage 8 frozen-schema/taxonomy test, Stage 7
  evidence-contract test, and preserved review-reporting regressions.
- **STAGE_REPORTS_VALIDATION_PASS**: `scripts/validate_stage_reports.py`, including
  unchanged accepted Stage 7/8 report fingerprints and historical status fields.
- **Frozen identity assertions PASS**: Stage 7/8 executable contract/schema
  fingerprints; Stage 9 frozen design/lock bytes, contract, six relation schemas,
  schema bundle, accepted-input binding, profile and logical dataset. Profile
  and dataset identities were recomputed from sanitized frozen relation metadata,
  not from payloads. The first ad-hoc acceptance check incorrectly sorted the
  profile's ordered reference list and supplied all six relations to the dataset
  formula instead of its three candidate relations plus the bound public pack.
  Correcting only that check to use the existing executable formulas reproduced
  the exact accepted identities. No candidate defect or scientific change.
- **Documentation/status/links PASS**: 137 local links; D060 and current indexes
  consistently record STAGE_9_ACCEPTED and Stage 10 NOT STARTED. Stage 10's
  existing specification section is byte-unchanged, not newly designed here.
- **Ancestry/content preservation PASS**: both non-squash merge parents verified;
  all nine independent-review files unchanged from `a9ae443c…`; source, tests,
  launchers, scripts, scientific assets, frozen Stage 9 design/reference freeze,
  and accepted Stage 0–8 records/summaries unchanged from the reporting candidate.
- **Privacy/tracked-data and diff hygiene PASS**: 23 changed paths consist of
  nine preserved review files and fourteen owner-acceptance/status Markdown files;
  no new untracked files, payload files, credentials or credential signatures;
  `git diff --check` passes. Only sanitized evidence/provenance was inspected.

No artifact reprocessing, protected access, SLURM job or DEVELOPMENT rerun is
part of this freeze. HOLDOUT remains SEALED; production/Pelias untouched.

STOP: STAGE_9_ACCEPTED. Stage 10 remains NOT STARTED; its bounded query-generation
design belongs to a separately authorized session.

## Historical candidate status and execution chronology

Historical D059 result: **STAGE09_OFFLINE_REFERENCE_EVIDENCE_DEVELOPMENT_CANDIDATE_READY**.
Corrected job `1771191` completed with exit `0:0`; publication, full in-job
scientific/hash reopening and subsequent sanitized reconciliation passed.
All 51,779 candidates have evidence. At D059, Stage 9 was **NOT YET ACCEPTED**; stop for
independent review. The high conditional postcode-format conflict rate is
explicitly retained in the terminal reconciliation below, not called address
invalidity. No second corrected run was submitted.

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

### Corrected single-submission receipt

- Corrected executable, pushed main and new clean detached Goethe checkout:
  `3e10ac7c1309c2636f35c0709fa283305d60d998`.
- Job `1771191`; submission UTC `2026-09-10T15:56:41Z`.
- One submission-time state observation: **PENDING**, reason **Resources**,
  dependencies none, `Requeue=0`, `Restarts=0`. No follow-up polling,
  cancellation or second corrected submission.
- Requested: general1 / footprint, one node, one task, four CPUs, 32 GiB,
  24 hours; automatic requeue disabled. No running resource measurements yet.
- Publication key: `stage09_development_20260910T155542Z_3e10ac7c1309`.
- Artifact target:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309`.
- New public-pack target:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/public_pack/stage09_public_pack_20260907_v1_3e10ac7c1309`.
- Executable checkout:
  `/work/footprint/donyadidegan/safe_geocoding_pipeline/integration_stage09/3e10ac7c1309c2636f35c0709fa283305d60d998`.
- The exact existing Stage 6 runtime, accepted Stage 8 artifact and frozen raw
  reference root are unchanged from the original receipt above. The new checkout
  arrived through Git, passed clean/detached/SHA and shell-syntax checks, and
  contains the exact `61cc5850…` reference lock. Prior checkouts were not mutated.
- Both publication namespaces were empty immediately before submission; both
  new targets were absent and not symlinks. Canonical-path/scope, exclusive
  ownership, complete reference/input verification and actual filesystem
  preflight are rechecked inside the scheduled process.
- Private logs: `logs/slurm/safe-stage09-reference-evidence_1771191.out` and
  `.err` beneath the controlled project root. No reference-pack/candidate manifest,
  registration, commit ID, profile hash or logical result is fabricated in this
  pending receipt.

On owner `continue`, inspect accounting once:

```sh
ssh goethe 'TZ=UTC sacct -j 1771191 --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,Start,End --parsable2'
```

If still pending/running, record the state and stop. If terminal, reconcile the
exact new run/public-pack reservation, manifest, bound `_SUCCESS.json`, empty
`_COMMITTED`, inventory and publication effects; do not use directory existence or
SLURM exit alone as success. Validate all scientific/input/reference/logical
bindings and sanitized aggregates before a candidate-ready claim. A failed run
must be classified and preserved for owner review, never automatically retried.
HOLDOUT remains sealed; production/Pelias untouched. Stage 9 is NOT ACCEPTED.

### Corrected terminal reconciliation — 2026-09-12

STAGE09_OFFLINE_REFERENCE_EVIDENCE_DEVELOPMENT_CANDIDATE_READY.

This is a **DEVELOPMENT candidate awaiting independent review**, not Stage 9
acceptance or address/geocoding accuracy. The owner continuation inspected
accounting once and found COMPLETED. No further SLURM job, protected rerun,
reference refresh, source correction or Stage 10 work occurred.

#### Exact execution and publication

| Item | Verified result |
|---|---|
| Job / executable | 1771191 / 3e10ac7c1309c2636f35c0709fa283305d60d998 |
| State / exit | COMPLETED / 0:0 |
| Start / end UTC | 2026-09-12T06:40:57Z / 2026-09-12T14:45:50Z |
| Elapsed | 08:04:53 |
| Requested resources | general1 / footprint; one node, one task, four CPUs, 32 GiB, 24 hours, no requeue |
| Scheduler allocation | 80 CPUs (whole-node allocation, not measured CPU use) |
| Peak batch RSS | 10,125,844 KiB = approximately 9.657 GiB |
| Runtime | Python 3.14.3 / Unicode 16.0.0 / PyArrow 25.0.0 / DuckDB 1.5.5 (d8cdaa33fd) |
| Publication key | stage09_development_20260910T155542Z_3e10ac7c1309 |
| Protocol / disposition | exclusive_run_commit_seal_v2_candidate / PASS |
| Artifact | Exact new DEVELOPMENT target in the corrected submission receipt above |
| Public pack | Exact new public-pack target in that receipt; same executable and job |
| Registration / seal | Canonical exact-bound registration; empty regular single-link _COMMITTED; IN_PROGRESS absent |
| Checkout / old attempts | Exact executable still clean and detached; original failed attempt and both diagnostics preserved |

The main program's PASS receipt is emitted only after exclusive reservation,
full private validation, bound registration, fsync, full prepared validation,
exclusive seal, fsync, full committed scientific/hash reopening, descriptor
teardown and last-operation ownership checks. The exact executed source confirms
that path; no unsupported rename primitive is reachable from publication.

Full evidence/reference payload hashing, PK/FK/state/capability/witness validation,
and pre/postcommit reopening **ran inside job 1771191**. This continuation
reconciled that immutable execution; it did not run Python or protected relation
processing on a login node. Its independent checks retrieved only sanitized
manifests/registration/logs and the 60,977-byte aggregate coverage relation,
compared exact hashes, recomputed registration/profile/input/logical-header
bindings, and checked all current file names, sizes, private modes, owners,
single-link regular files and directories using read-only shell metadata.
It did not rehash the 0.9 GB evidence/reference payloads outside SLURM or claim
a second protected validation execution. Current metadata and the complete
in-job validation reconcile; there is no reliance on directory existence alone.

| Identity | SHA-256 |
|---|---|
| DEVELOPMENT manifest | 321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240 |
| DEVELOPMENT logical dataset | 7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3 |
| Contract | 6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9 |
| Profile | b12be7ba06de2360ba7cd9b971c4b562b1c8df5d25c30024975869fd2b34efd1 |
| Schema bundle | 7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716 |
| Stage 8 accepted manifest | 2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827 |
| Stage 8 accepted logical | 9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526 |
| Stage 9 accepted-input binding | 64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90 |
| Frozen raw reference lock | 61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63 |
| Published reference-pack manifest | dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a |
| Published reference-pack logical | 10ae5c9baf2d781bd241ece2d28ef62430b54f511ed1e98acd8761232062040b |
| DEVELOPMENT registration | ac4824ebd2b8a0e0d20632370507b9c1a49cc5df3622aa213b52ba48a01c42fb |
| DEVELOPMENT commit-record ID | 9b486d4a47306c0950f41d1eab8c23a43ee29f95919b1bea0ff35d7be046e2e0 |
| DEVELOPMENT inventory | ba7f0db287f59d7c5ff5c210b965c3c4a6aaf147982b8c69a959faa9c3fed1cd |
| Public-pack registration | 061e3a851307465b5b87ef4bca177e5d9be57983061ffc3ccdb4deeabd8f8749 |
| Public-pack commit-record ID | 1538d17ba13253922f3c0361032b23a815175d60230d9cb2eff0bb773e054b3f |
| Public-pack inventory | 0961914ad443a471982833cfafe04161fd32df4b6194d9555592907cbadc3a50 |

Versions remain `stage09_offline_reference_evidence_contract_v1`, `stage09_offline_reference_evidence_profile_v1`,
`stage09_offline_reference_evidence_schema_v1`. The exact nested accepted Stage 8 binding, including its Stage 6
transitive identity, matches the frozen source constants. Registry editions are
ISO_CODES 4.20.1-1, LIBADDRESSINPUT_METADATA from google-i18n-address 3.1.1, and
GEONAMES_POSTAL snapshot 2026-09-07; the individual asset hashes/licenses in this
report's frozen reference section remain unchanged. No refresh/substitution.

Candidate inventory: 21 files, eight directories including root, 639,767,626
bytes including manifest/registration/seal. Public-pack inventory: 11 files,
five directories including root, 274,691,380 bytes. Total committed file bytes:
914,459,006. All directories are 0700 and owned; files are 0600, owner-matching,
single-link and regular; no symlinks, extra paths or incomplete markers exist.
Hashes/bytes for stdout: 989 /
`5d3a8c1fcd641d3b5aec7fa609313b503be6a8de7e9e2de043a0c01a174b06a8`.
Stderr is empty (SHA-256
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`).
Logs remain private and preserved.

#### Relations, totality and validation

| Logical relation | Rows | Schema SHA-256 | Logical SHA-256 |
|---|---|---|---|
| reference_registry | 3 | 35f8c9e85437f0aafb755e9aafb654053307ff1da7d25e043c28d142c317b567 | 14e715d9e038920632f50215f3cf7c4fbd00367d4bbb931af706a72ec8691b3b |
| reference_capability | 47,578 | e0e4d90193510041179edd0dbb84f2b625436668eb55d75b1d7892207c4a8fc1 | 8d525682700889d30bf1f5f24797155248fe4c8e808a56d031ada3649fcdfa57 |
| reference_object | 1,844,460 | d2af207938a9bbb25ed3718a68e8225414551c1a93c57c6b08fa66169ad57876 | 3636ccd9b58b5bd9a37b678ba86e0c5e3512c2e073b83bbb14a626cb9494751a |
| candidate_reference_evidence | 6,565,329 | b0f9c93fbf4e72f0247b65586b72dbb47ff0b5e98a75ac3888798cb703b81e91 | 85850fde2e861cf6ad6716df96283986af72138ec370e2d737043f23eedc4c1a |
| reference_match_member | 626,110 | f2d08eea797a34f921fa8ddf639e8ad6ae1f0e5ee4f8dca26c1e5faedbdf08cc | 1486e8ef3652620de6581c29304cb6ca9b7e77195361e5cb9d7c1f504efba07b |
| coverage_summary | 48,479 | 4844b3e7f66b8337e24a51e8312ee5ac99be57c7cd8e277fbac2a7e9583be846 | ea6ce3cc414ed4aef610a99f2861004da826f1bf3a08bf60b0d2761960ec7014 |

The first three relations are bound from the reusable public pack, not duplicated
in the candidate. Its physical postal index has 1,826,904 rows, 75,838,520 bytes,
schema `4b89c69b6e59db57f1f9a1e3ee7acd32a9f38337f258e9845b26d4c29ea7dadd`, logical
`a27a050e58e6e5a8d8a8de5c518f6f1f21d15b6a3a9a9e3f923f6f8d7ba0b691`; it is an index, not a seventh logical
evidence relation. Objects comprise 5,295 ISO + 12,261 metadata + 1,826,904 postal
records. Stage 8 remains the sole authoritative source/occurrence mapping layer.

All 35,000 source rows, 51,779 candidates, 69,747 occurrences (34,822 STANDARD /
34,925 NATIVE) and 6,106,088 parser components reconcile. All 51,779 candidates
have Stage 9 evidence; zero candidate loss, zero sources lacking a candidate,
zero technical failures. Exactly 51,066 candidates (98.623% of 51,779) have at
least one evaluable check; 713 have only NOT_EVALUABLE checks. “Evaluable” includes
NOT_FOUND and CONTRADICTED and does **not** mean supported or valid address.
A distinct candidate-with-positive-support total is not inferred from overlapping
incidence aggregates.

All seven frozen validation certificates passed:
candidate/source/occurrence totality; complete match-member integrity;
evidence identity/state; full scheduling/normalization/reference replay;
GeoNames no contradictions; reference capability/authority; and exact witness
asset/field bindings. In-job readers recomputed every relation's physical/logical
hash and schema, enforced IDs/FKs and authority, and recomputed coverage.
The coverage relation was independently retrieved/rehashed/recomputed in this
continuation: 48,479 rows, exact schema, unique PKs, logical
`ea6ce3cc414ed4aef610a99f2861004da826f1bf3a08bf60b0d2761960ec7014`.
Its state, reason, family, scope and country totals equal the manifest, with
no negative counts or counts exceeding their stated denominators.

#### Four-state and reference-use diagnostics

Denominator for the following rates: all **6,565,329 evaluation rows**, not
source addresses, distinct candidates, or independent confirmations.

| State | Rows | % of evaluations |
|---|---|---|
| SUPPORTED | 531,488 | 8.0954 |
| CONTRADICTED | 54,025 | 0.8229 |
| NOT_FOUND | 2,128,794 | 32.4248 |
| NOT_EVALUABLE | 3,851,022 | 58.6570 |

| Reference family / explicit absent slot | SUPPORTED | CONTRADICTED | NOT_FOUND | NOT_EVALUABLE |
|---|---|---|---|---|
| GEONAMES_POSTAL | 84,652 | 0 | 1,066,914 | 1,124,100 |
| ISO_CODES | 112,940 | 0 | 270,961 | 223,170 |
| LIBADDRESSINPUT_METADATA | 333,896 | 54,025 | 790,919 | 1,200,439 |
| NONE | 0 | 0 | 0 | 1,303,313 |

NONE is the frozen unconfigured reference slot for street/house-number questions,
**not** a fourth evidence family or a dataset. Every one of its 1,303,313 rows
is NOT_EVALUABLE. Real reference-family totals: GeoNames 2,275,666;
ISO 607,071; libaddressinput 2,379,279. Related lineage is preserved for later
Stage 13 dependence handling; these are not independent address confirmations.

The matrix below covers question/capability evaluability. For each row the
denominator is the sum of its four state counts; evaluable = all but NOT_EVALUABLE.
Source- and parser-scoped evaluations are pooled here and remain separately
identifiable in the artifact.

| Question | Reference | Capability | SUPPORTED | CONTRADICTED | NOT_FOUND | NOT_EVALUABLE |
|---|---|---|---|---|---|---|
| Q01 | ISO_CODES | COUNTRY_CONTEXT | 101,438 | 0 | 356 | 1,819 |
| Q02 | ISO_CODES | COUNTRY_CONTEXT | 0 | 0 | 0 | 103,613 |
| Q03 | LIBADDRESSINPUT_METADATA | FORMAT | 99,632 | 0 | 0 | 3,981 |
| Q04 | LIBADDRESSINPUT_METADATA | POSTCODE_PATTERN | 36,021 | 54,022 | 0 | 608,444 |
| Q05 | GEONAMES_POSTAL | POSTCODE_EXISTENCE | 22,771 | 0 | 59,917 | 615,799 |
| Q06 | GEONAMES_POSTAL | POSTCODE_LOCALITY | 968 | 0 | 16,341 | 86,304 |
| Q07 | GEONAMES_POSTAL | POSTCODE_ADMIN | 903 | 0 | 12,708 | 90,002 |
| Q08 | LIBADDRESSINPUT_METADATA | POSTCODE_PREFIX_BY_ADMIN | 901 | 3 | 0 | 102,709 |
| Q09 | GEONAMES_POSTAL | LOCALITY | 44,447 | 0 | 877,113 | 192,981 |
| Q09 | LIBADDRESSINPUT_METADATA | LOCALITY | 91,358 | 0 | 713,697 | 309,486 |
| Q10 | GEONAMES_POSTAL | ADMIN | 11,407 | 0 | 69,316 | 71,076 |
| Q10 | ISO_CODES | ADMIN | 8,944 | 0 | 76,541 | 66,314 |
| Q10 | LIBADDRESSINPUT_METADATA | ADMIN_ENUMERATION | 19,321 | 0 | 56,824 | 75,654 |
| Q11 | GEONAMES_POSTAL | LOCALITY_ADMIN | 4,156 | 0 | 31,519 | 67,938 |
| Q11 | LIBADDRESSINPUT_METADATA | LOCALITY_ADMIN | 1,414 | 0 | 20,398 | 81,801 |
| Q12 | NONE | STREET | 0 | 0 | 0 | 1,199,700 |
| Q13 | NONE | HOUSE_NUMBER | 0 | 0 | 0 | 103,613 |
| Q14 | ISO_CODES | COUNTRY_CONTEXT | 2,558 | 0 | 194,064 | 51,424 |
| Q15 | LIBADDRESSINPUT_METADATA | REQUIRED_FIELDS | 85,249 | 0 | 0 | 18,364 |

GeoNames: 84,652 supported, 1,066,914 not found, 1,124,100 not evaluable,
**zero contradicted**. The 6,673 association mismatches remain NOT_FOUND diagnostics,
not source invalidity. Frozen country-specific coverage remains 121 postal
countries, with partial-code exclusions, Brazil's major-code limitation, US
ZIP+4 abstention and excluded full variants. Missing libaddressinput metadata,
BH regex incompatibility and CN unhandled alternate rules remain abstentions.

#### Bounded aggregate anomaly review

| Scope | Question/capability | Permitted contradiction | Rows |
|---|---|---|---|
| PARSER_CANDIDATE | Q04/POSTCODE_PATTERN | FORMAT_RULE_CONFLICT | 42,702 |
| PARSER_CANDIDATE | Q08/POSTCODE_PREFIX_BY_ADMIN | PREFIX_RULE_CONFLICT | 2 |
| SOURCE_ROW | Q04/POSTCODE_PATTERN | FORMAT_RULE_CONFLICT | 11,320 |
| SOURCE_ROW | Q08/POSTCODE_PREFIX_BY_ADMIN | PREFIX_RULE_CONFLICT | 1 |

All 54,025 contradictions are explicitly authorized libaddressinput rule conflicts:
54,022 Q04 postcode-pattern and three Q08 admin-prefix. ISO and GeoNames emitted
zero contradictions. Prefix conflicts are one SOURCE_ROW/AR and two
PARSER_CANDIDATE/KR. No postcode/locality association absence was converted to
contradiction.

**High format-conflict rate is retained for independent review:** Q04 has 54,022
conflicts / 90,043 evaluable checks = 59.996%, although this is only 0.823% of all
Stage 9 evaluations. SOURCE_ROW: 11,320 / 20,407 evaluable = 55.471%;
PARSER_CANDIDATE: 42,702 / 69,636 = 61.322%. Rates are evaluation-level, not
source-row or candidate incidence rates.

| Country | Scope | Q04 support | Q04 conflict | Q04 not evaluable |
|---|---|---|---|---|
| BR | PARSER_CANDIDATE | 0 | 52 | 4,030 |
| BR | SOURCE_ROW | 2,097 | 1,985 | 0 |
| CN | PARSER_CANDIDATE | 0 | 0 | 475,350 |
| CN | SOURCE_ROW | 0 | 0 | 21,759 |
| IT | PARSER_CANDIDATE | 1,902 | 5,571 | 340 |
| IT | SOURCE_ROW | 38 | 303 | 3 |
| RO | PARSER_CANDIDATE | 14,064 | 3,491 | 610 |
| RO | SOURCE_ROW | 51 | 200 | 369 |
| RU | PARSER_CANDIDATE | 5,645 | 18,220 | 2,234 |
| RU | SOURCE_ROW | 410 | 2,054 | 7 |
| UA | PARSER_CANDIDATE | 1,350 | 13,209 | 1,070 |
| UA | SOURCE_ROW | 181 | 887 | 4 |

Investigation stayed aggregate-only: scope/country/reason totals were reconciled;
the exact source postcode locator was checked in code; Q04's full-match path,
per-country normalization and negative-authority gate were checked against the
frozen contract; all 1,255 supported public regex patterns and 1,092 eligible
public metadata examples pass the existing exact-engine tests. RU/RO use the
frozen six-digit rule, UA/IT five-digit, BR its declared eight-digit/optional
separator rule. No input strings were inspected. This establishes faithful
frozen-rule evaluation, **not** why individual source/parser values fail or that
the corresponding addresses are invalid. No correction, parser correctness
inference or scientific retuning was performed; that interpretation limit remains
explicit for independent review.

All 51,779 country assessments are COUNTRY_UNRESOLVED, with zero supported or
contradicted. This is required by the frozen Q02-only reduction: 51,834
SOURCE_ROW evaluations comprise 41,110 unrecognized full subdivision identifiers,
9,609 missing admin components and 1,115 unresolved country contexts. The 51,779
parser Q02 slots abstain as SOURCE_ONLY_QUESTION. Q01 code recognition and
country-blocked name support cannot manufacture geographic country support.

CN contributes 4,363,484 / 6,565,329 evaluations (66.463%), not that share of source
addresses; country rates must not be interpreted as population weights.
Its 472,630 unsupported alternate-rule and 503,920 insufficient-granularity
diagnostics explain substantial deliberate abstention. All 497,109 CN Q04 slots
are NOT_EVALUABLE, never contradiction. Every nonempty country-context group has
nonzero NOT_EVALUABLE counts. Low all-evaluation support is compatible with strict
exact lookup, incomplete coverage and repeated parser components; absence remains
NOT_FOUND, not invalidity. No circular “global address supported” summary is made.

No cardinality mismatch, impossible state, unauthorized country/capability,
GeoNames contradiction, technical failure or publication inconsistency remained.
High conditional pattern-conflict rates and the absence of country witnesses are
scientific limitations/diagnostics for review, not silently removed observations.

#### Complete country-context evaluability

There are 214 populated ISO country-context groups plus UNRESOLVED. The remaining
35 ISO contexts have zero DEVELOPMENT evaluations and explicit zero cells in the
coverage artifact; absence of a DEVELOPMENT denominator is not lack of reference
coverage. Country context is accepted upstream provenance, not geographic truth.
Counts below are evaluation counts; evaluable = SUPPORTED + CONTRADICTED +
NOT_FOUND. The four counts sum to each country's evaluation denominator.
This is not a distinct-candidate-by-country accuracy/evaluability table.

<details>
<summary>All populated country-context evaluation totals</summary>

| Country context | Evaluations | Evaluable | Evaluable % | SUPPORTED | CONTRADICTED | NOT_FOUND | NOT_EVALUABLE |
|---|---|---|---|---|---|---|---|
| AD | 703 | 125 | 17.78 | 105 | 2 | 18 | 578 |
| AE | 2,923 | 561 | 19.19 | 474 | 0 | 87 | 2,362 |
| AF | 741 | 80 | 10.80 | 80 | 0 | 0 | 661 |
| AG | 596 | 64 | 10.74 | 64 | 0 | 0 | 532 |
| AI | 684 | 135 | 19.74 | 84 | 8 | 43 | 549 |
| AL | 3,047 | 911 | 29.90 | 444 | 41 | 426 | 2,136 |
| AM | 4,523 | 734 | 16.23 | 488 | 2 | 244 | 3,789 |
| AO | 1,110 | 87 | 7.84 | 87 | 0 | 0 | 1,023 |
| AR | 31,784 | 8,650 | 27.21 | 6,243 | 831 | 1,576 | 23,134 |
| AS | 74 | 19 | 25.68 | 14 | 1 | 4 | 55 |
| AT | 5,587 | 2,049 | 36.67 | 1,140 | 126 | 783 | 3,538 |
| AU | 5,922 | 2,247 | 37.94 | 1,692 | 138 | 417 | 3,675 |
| AW | 778 | 42 | 5.40 | 42 | 0 | 0 | 736 |
| AZ | 1,815 | 584 | 32.18 | 207 | 49 | 328 | 1,231 |
| BA | 1,332 | 209 | 15.69 | 197 | 1 | 11 | 1,123 |
| BB | 703 | 79 | 11.24 | 78 | 1 | 0 | 624 |
| BD | 592 | 111 | 18.75 | 81 | 1 | 29 | 481 |
| BE | 1,298 | 453 | 34.90 | 277 | 28 | 148 | 845 |
| BF | 706 | 94 | 13.31 | 76 | 0 | 18 | 612 |
| BG | 23,076 | 8,899 | 38.56 | 3,794 | 571 | 4,534 | 14,177 |
| BH | 1,000 | 110 | 11.00 | 108 | 0 | 2 | 890 |
| BI | 667 | 49 | 7.35 | 49 | 0 | 0 | 618 |
| BJ | 704 | 56 | 7.95 | 55 | 0 | 1 | 648 |
| BM | 670 | 110 | 16.42 | 81 | 2 | 27 | 560 |
| BN | 1,043 | 133 | 12.75 | 130 | 2 | 1 | 910 |
| BO | 2,492 | 202 | 8.11 | 191 | 0 | 11 | 2,290 |
| BR | 152,420 | 71,956 | 47.21 | 42,248 | 2,037 | 27,671 | 80,464 |
| BS | 777 | 85 | 10.94 | 84 | 0 | 1 | 692 |
| BT | 444 | 52 | 11.71 | 49 | 2 | 1 | 392 |
| BW | 814 | 64 | 7.86 | 44 | 0 | 20 | 750 |
| BY | 1,518 | 416 | 27.40 | 201 | 16 | 199 | 1,102 |
| BZ | 592 | 33 | 5.57 | 32 | 0 | 1 | 559 |
| CA | 1,073 | 322 | 30.01 | 277 | 2 | 43 | 751 |
| CD | 814 | 64 | 7.86 | 63 | 0 | 1 | 750 |
| CF | 592 | 47 | 7.94 | 47 | 0 | 0 | 545 |
| CG | 555 | 36 | 6.49 | 36 | 0 | 0 | 519 |
| CH | 2,411 | 905 | 37.54 | 601 | 29 | 275 | 1,506 |
| CI | 781 | 104 | 13.32 | 104 | 0 | 0 | 677 |
| CL | 3,215 | 928 | 28.86 | 603 | 2 | 323 | 2,287 |
| CM | 1,036 | 81 | 7.82 | 56 | 0 | 25 | 955 |
| CN | 4,363,484 | 2,082,291 | 47.72 | 266,653 | 0 | 1,815,638 | 2,281,193 |
| CO | 19,946 | 6,287 | 31.52 | 4,844 | 90 | 1,353 | 13,659 |
| CR | 3,076 | 654 | 21.26 | 537 | 0 | 117 | 2,422 |
| CU | 779 | 86 | 11.04 | 84 | 2 | 0 | 693 |
| CV | 1,147 | 184 | 16.04 | 151 | 0 | 33 | 963 |
| CW | 666 | 36 | 5.41 | 36 | 0 | 0 | 630 |
| CY | 4,150 | 1,218 | 29.35 | 634 | 0 | 584 | 2,932 |
| CZ | 10,176 | 3,893 | 38.26 | 2,155 | 105 | 1,633 | 6,283 |
| DE | 2,368 | 837 | 35.35 | 429 | 60 | 348 | 1,531 |
| DJ | 703 | 53 | 7.54 | 53 | 0 | 0 | 650 |
| DK | 1,333 | 470 | 35.26 | 280 | 7 | 183 | 863 |
| DM | 665 | 36 | 5.41 | 36 | 0 | 0 | 629 |
| DO | 1,928 | 317 | 16.44 | 233 | 1 | 83 | 1,611 |
| DZ | 15,765 | 3,478 | 22.06 | 2,875 | 4 | 599 | 12,287 |
| EC | 1,490 | 329 | 22.08 | 174 | 2 | 153 | 1,161 |
| EE | 1,813 | 664 | 36.62 | 339 | 31 | 294 | 1,149 |
| EG | 888 | 100 | 11.26 | 100 | 0 | 0 | 788 |
| ER | 592 | 46 | 7.77 | 32 | 0 | 14 | 546 |
| ES | 5,294 | 2,109 | 39.84 | 1,078 | 109 | 922 | 3,185 |
| ET | 1,073 | 123 | 11.46 | 123 | 0 | 0 | 950 |
| FI | 4,304 | 1,536 | 35.69 | 1,076 | 80 | 380 | 2,768 |
| FJ | 594 | 33 | 5.56 | 32 | 0 | 1 | 561 |
| FM | 444 | 111 | 25.00 | 94 | 1 | 16 | 333 |
| FO | 37 | 4 | 10.81 | 4 | 0 | 0 | 33 |
| FR | 1,596 | 580 | 36.34 | 337 | 14 | 229 | 1,016 |
| GA | 703 | 54 | 7.68 | 53 | 0 | 1 | 649 |
| GB | 13,377 | 3,867 | 28.91 | 2,934 | 6 | 927 | 9,510 |
| GD | 461 | 25 | 5.42 | 25 | 0 | 0 | 436 |
| GE | 9,145 | 1,480 | 16.18 | 1,235 | 205 | 40 | 7,665 |
| GG | 185 | 41 | 22.16 | 30 | 1 | 10 | 144 |
| GH | 854 | 67 | 7.85 | 67 | 0 | 0 | 787 |
| GI | 815 | 150 | 18.40 | 146 | 1 | 3 | 665 |
| GL | 38 | 9 | 23.68 | 6 | 1 | 2 | 29 |
| GM | 777 | 62 | 7.98 | 42 | 0 | 20 | 715 |
| GN | 742 | 96 | 12.94 | 93 | 2 | 1 | 646 |
| GQ | 703 | 57 | 8.11 | 39 | 0 | 18 | 646 |
| GR | 8,025 | 1,635 | 20.37 | 1,456 | 4 | 175 | 6,390 |
| GT | 709 | 117 | 16.50 | 88 | 1 | 28 | 592 |
| GW | 592 | 80 | 13.51 | 80 | 0 | 0 | 512 |
| GY | 703 | 58 | 8.25 | 54 | 0 | 4 | 645 |
| HK | 2,045 | 439 | 21.47 | 360 | 0 | 79 | 1,606 |
| HN | 407 | 90 | 22.11 | 80 | 1 | 9 | 317 |
| HR | 1,998 | 652 | 32.63 | 283 | 46 | 323 | 1,346 |
| HT | 741 | 113 | 15.25 | 94 | 2 | 17 | 628 |
| HU | 5,665 | 2,124 | 37.49 | 1,246 | 52 | 826 | 3,541 |
| ID | 1,036 | 323 | 31.18 | 236 | 9 | 78 | 713 |
| IE | 2,924 | 624 | 21.34 | 386 | 7 | 231 | 2,300 |
| IL | 9,138 | 1,290 | 14.12 | 1,042 | 196 | 52 | 7,848 |
| IM | 630 | 166 | 26.35 | 114 | 11 | 41 | 464 |
| IN | 91,861 | 30,064 | 32.73 | 22,495 | 795 | 6,774 | 61,797 |
| IQ | 630 | 103 | 16.35 | 102 | 1 | 0 | 527 |
| IR | 816 | 96 | 11.76 | 94 | 2 | 0 | 720 |
| IS | 1,517 | 366 | 24.13 | 256 | 0 | 110 | 1,151 |
| IT | 64,845 | 33,439 | 51.57 | 5,342 | 5,874 | 22,223 | 31,406 |
| JE | 371 | 85 | 22.91 | 69 | 1 | 15 | 286 |
| JM | 1,369 | 294 | 21.48 | 267 | 0 | 27 | 1,075 |
| JO | 778 | 94 | 12.08 | 91 | 1 | 2 | 684 |
| JP | 70,215 | 23,039 | 32.81 | 13,170 | 43 | 9,826 | 47,176 |
| KE | 9,595 | 1,526 | 15.90 | 1,260 | 23 | 243 | 8,069 |
| KG | 1,819 | 290 | 15.94 | 202 | 39 | 49 | 1,529 |
| KH | 1,187 | 147 | 12.38 | 135 | 11 | 1 | 1,040 |
| KI | 74 | 8 | 10.81 | 8 | 0 | 0 | 66 |
| KM | 555 | 44 | 7.93 | 43 | 0 | 1 | 511 |
| KN | 558 | 90 | 16.13 | 90 | 0 | 0 | 468 |
| KP | 518 | 56 | 10.81 | 56 | 0 | 0 | 462 |
| KR | 39,612 | 16,587 | 41.87 | 7,728 | 567 | 8,292 | 23,025 |
| KW | 816 | 104 | 12.75 | 101 | 2 | 1 | 712 |
| KY | 892 | 165 | 18.50 | 164 | 0 | 1 | 727 |
| KZ | 7,994 | 1,100 | 13.76 | 932 | 20 | 148 | 6,894 |
| LA | 1,946 | 227 | 11.66 | 210 | 2 | 15 | 1,719 |
| LB | 1,221 | 134 | 10.97 | 132 | 0 | 2 | 1,087 |
| LC | 684 | 37 | 5.41 | 37 | 0 | 0 | 647 |
| LI | 930 | 261 | 28.06 | 258 | 0 | 3 | 669 |
| LK | 925 | 179 | 19.35 | 113 | 13 | 53 | 746 |
| LR | 778 | 90 | 11.57 | 89 | 0 | 1 | 688 |
| LS | 1,184 | 188 | 15.88 | 165 | 23 | 0 | 996 |
| LT | 1,443 | 546 | 37.84 | 269 | 15 | 262 | 897 |
| LU | 893 | 231 | 25.87 | 185 | 15 | 31 | 662 |
| LV | 3,193 | 1,076 | 33.70 | 570 | 85 | 421 | 2,117 |
| LY | 666 | 50 | 7.51 | 37 | 0 | 13 | 616 |
| MA | 9,759 | 2,139 | 21.92 | 1,110 | 1 | 1,028 | 7,620 |
| MC | 1,036 | 221 | 21.33 | 186 | 11 | 24 | 815 |
| MD | 2,479 | 804 | 32.43 | 398 | 37 | 369 | 1,675 |
| ME | 1,557 | 210 | 13.49 | 205 | 5 | 0 | 1,347 |
| MG | 854 | 117 | 13.70 | 92 | 1 | 24 | 737 |
| MH | 778 | 221 | 28.41 | 152 | 18 | 51 | 557 |
| MK | 1,480 | 362 | 24.46 | 264 | 11 | 87 | 1,118 |
| ML | 666 | 54 | 8.11 | 54 | 0 | 0 | 612 |
| MM | 1,335 | 150 | 11.24 | 147 | 1 | 2 | 1,185 |
| MN | 779 | 86 | 11.04 | 84 | 1 | 1 | 693 |
| MO | 595 | 115 | 19.33 | 96 | 0 | 19 | 480 |
| MR | 741 | 57 | 7.69 | 55 | 0 | 2 | 684 |
| MT | 964 | 221 | 22.93 | 169 | 1 | 51 | 743 |
| MU | 999 | 133 | 13.31 | 128 | 0 | 5 | 866 |
| MV | 592 | 74 | 12.50 | 72 | 2 | 0 | 518 |
| MW | 630 | 131 | 20.79 | 70 | 0 | 61 | 499 |
| MX | 13,091 | 5,140 | 39.26 | 2,942 | 318 | 1,880 | 7,951 |
| MY | 1,344 | 400 | 29.76 | 306 | 9 | 85 | 944 |
| MZ | 1,079 | 173 | 16.03 | 146 | 1 | 26 | 906 |
| NE | 703 | 95 | 13.51 | 95 | 0 | 0 | 608 |
| NG | 2,702 | 430 | 15.91 | 415 | 0 | 15 | 2,272 |
| NI | 705 | 82 | 11.63 | 79 | 2 | 1 | 623 |
| NL | 1,480 | 383 | 25.88 | 316 | 0 | 67 | 1,097 |
| NO | 5,465 | 1,954 | 35.75 | 1,211 | 71 | 672 | 3,511 |
| NP | 666 | 77 | 11.56 | 74 | 3 | 0 | 589 |
| NR | 111 | 25 | 22.52 | 18 | 0 | 7 | 86 |
| NU | 74 | 8 | 10.81 | 4 | 0 | 4 | 66 |
| NZ | 2,651 | 722 | 27.24 | 653 | 0 | 69 | 1,929 |
| OM | 814 | 107 | 13.14 | 94 | 13 | 0 | 707 |
| PA | 781 | 118 | 15.11 | 84 | 0 | 34 | 663 |
| PE | 28,929 | 7,078 | 24.47 | 6,141 | 24 | 913 | 21,851 |
| PF | 74 | 28 | 37.84 | 12 | 4 | 12 | 46 |
| PG | 1,449 | 260 | 17.94 | 243 | 13 | 4 | 1,189 |
| PH | 1,444 | 410 | 28.39 | 204 | 1 | 205 | 1,034 |
| PK | 1,336 | 414 | 30.99 | 216 | 0 | 198 | 922 |
| PL | 4,180 | 1,603 | 38.35 | 991 | 5 | 607 | 2,577 |
| PS | 740 | 40 | 5.41 | 40 | 0 | 0 | 700 |
| PT | 2,003 | 660 | 32.95 | 508 | 1 | 151 | 1,343 |
| PW | 112 | 27 | 24.11 | 20 | 1 | 6 | 85 |
| PY | 1,226 | 164 | 13.38 | 140 | 0 | 24 | 1,062 |
| QA | 814 | 44 | 5.41 | 44 | 0 | 0 | 770 |
| RO | 179,848 | 76,297 | 42.42 | 37,449 | 3,691 | 35,157 | 103,551 |
| RS | 3,406 | 802 | 23.55 | 467 | 57 | 278 | 2,604 |
| RU | 252,146 | 125,699 | 49.85 | 23,184 | 20,274 | 82,241 | 126,447 |
| RW | 740 | 62 | 8.38 | 40 | 0 | 22 | 678 |
| SA | 1,110 | 137 | 12.34 | 135 | 2 | 0 | 973 |
| SB | 259 | 14 | 5.41 | 14 | 0 | 0 | 245 |
| SC | 854 | 93 | 10.89 | 92 | 0 | 1 | 761 |
| SD | 777 | 108 | 13.90 | 104 | 3 | 1 | 669 |
| SE | 15,149 | 5,681 | 37.50 | 4,056 | 0 | 1,625 | 9,468 |
| SG | 1,796 | 488 | 27.17 | 348 | 17 | 123 | 1,308 |
| SI | 1,406 | 333 | 23.68 | 177 | 37 | 119 | 1,073 |
| SJ | 111 | 34 | 30.63 | 18 | 3 | 13 | 77 |
| SK | 5,045 | 1,861 | 36.89 | 1,009 | 94 | 758 | 3,184 |
| SL | 666 | 45 | 6.76 | 43 | 0 | 2 | 621 |
| SM | 592 | 127 | 21.45 | 109 | 4 | 14 | 465 |
| SN | 743 | 102 | 13.73 | 101 | 1 | 0 | 641 |
| SO | 777 | 159 | 20.46 | 158 | 1 | 0 | 618 |
| SR | 668 | 72 | 10.78 | 72 | 0 | 0 | 596 |
| SS | 518 | 41 | 7.92 | 28 | 0 | 13 | 477 |
| ST | 703 | 55 | 7.82 | 38 | 0 | 17 | 648 |
| SV | 818 | 136 | 16.63 | 132 | 3 | 1 | 682 |
| SX | 555 | 30 | 5.41 | 30 | 0 | 0 | 525 |
| SY | 777 | 42 | 5.41 | 42 | 0 | 0 | 735 |
| SZ | 518 | 69 | 13.32 | 67 | 2 | 0 | 449 |
| TD | 630 | 50 | 7.94 | 50 | 0 | 0 | 580 |
| TG | 629 | 51 | 8.11 | 34 | 0 | 17 | 578 |
| TH | 6,180 | 1,411 | 22.83 | 969 | 1 | 441 | 4,769 |
| TJ | 888 | 119 | 13.40 | 96 | 0 | 23 | 769 |
| TL | 222 | 12 | 5.41 | 12 | 0 | 0 | 210 |
| TM | 592 | 72 | 12.16 | 71 | 1 | 0 | 520 |
| TN | 891 | 115 | 12.91 | 113 | 1 | 1 | 776 |
| TO | 222 | 12 | 5.41 | 12 | 0 | 0 | 210 |
| TR | 8,493 | 3,001 | 35.33 | 1,811 | 88 | 1,102 | 5,492 |
| TT | 483 | 26 | 5.38 | 26 | 0 | 0 | 457 |
| TV | 37 | 4 | 10.81 | 4 | 0 | 0 | 33 |
| TW | 16,360 | 4,818 | 29.45 | 3,233 | 436 | 1,149 | 11,542 |
| TZ | 705 | 97 | 13.76 | 97 | 0 | 0 | 608 |
| UA | 169,153 | 77,762 | 45.97 | 10,137 | 14,096 | 53,529 | 91,391 |
| UG | 556 | 30 | 5.40 | 30 | 0 | 0 | 526 |
| UNRESOLVED | 588,096 | 28,793 | 4.90 | 337 | 0 | 28,456 | 559,303 |
| US | 8,213 | 2,890 | 35.19 | 1,778 | 10 | 1,102 | 5,323 |
| UY | 1,341 | 399 | 29.75 | 307 | 8 | 84 | 942 |
| UZ | 11,931 | 1,662 | 13.93 | 1,530 | 26 | 106 | 10,269 |
| VA | 296 | 55 | 18.58 | 37 | 3 | 15 | 241 |
| VC | 596 | 74 | 12.42 | 73 | 1 | 0 | 522 |
| VE | 1,414 | 300 | 21.22 | 275 | 0 | 25 | 1,114 |
| VG | 889 | 158 | 17.77 | 157 | 0 | 1 | 731 |
| VN | 47,183 | 7,886 | 16.71 | 4,729 | 1,259 | 1,898 | 39,297 |
| VU | 595 | 32 | 5.38 | 32 | 0 | 0 | 563 |
| WS | 780 | 82 | 10.51 | 54 | 0 | 28 | 698 |
| YE | 629 | 34 | 5.41 | 34 | 0 | 0 | 595 |
| ZA | 48,422 | 14,481 | 29.91 | 11,127 | 875 | 2,479 | 33,941 |
| ZM | 741 | 105 | 14.17 | 104 | 1 | 0 | 636 |
| ZW | 742 | 56 | 7.55 | 54 | 0 | 2 | 686 |

</details>

#### Scale, reproducibility and review disposition

Sixteen deterministic task groups cover all 4,096 logical shard prefixes exactly
once; their scheduled totals sum to 6,565,329. Full replay in reverse group order
matched evidence/member logical identities before publication. No checkpoints
were adopted from previous jobs. Group evaluation sizes range from 120,056 to
1,382,461 (data skew is retained, not truncated). Across groups, 5,043,577
questions produced the scheduled evaluations; small-reference cache hits total
1,388,633. Postal work: 1,151,566 scheduled evaluable requests, 241,628 summed
within-group distinct lookups (not globally distinct) and 5,240,846 matched
reference-record incidences. The public index was built once and reused.
No per-row network calls or pandas production path exists.

Recorded candidate build time is 18,015 seconds (includes reverse replay);
whole-job time includes public preparation and repeated full validations.
Committed bytes total 914,459,006; total read/write traffic, spill volume and CPU
utilization were not measured and are not inferred from committed bytes.
The 9.657 GiB batch peak fits the requested 32 GiB; this DEVELOPMENT observation
does not establish production throughput/memory at 141M source rows. Bounded
joins/batches and per-run registration remain the scaling architecture;
production scheduling/resource validation still needs separate authorization.

The pre-run implementation defect ledger remains resolved. This continuation's
bounded reconciliation ledger found no additional output-semantic defect requiring
a fix or rerun. No executable or scientific asset was changed. Error-handling
guidance kept scheduler completion, successful in-job reopening and current
metadata/effect reconciliation distinct rather than treating exit zero as proof.

Reconciliation local gate: **836 tests passed (17.76 seconds)**, including the
accepted Stage 7/8 regressions and publication faults; source mypy passes for
96 files; Ruff lint/format passes for 145 files. The pre-submission separate
Stage 7/8/execution-policy gate remains 164 passing tests. Stage 7/8 source,
contracts, fingerprints and accepted reports remain unchanged; frozen Stage 9
design/lock bytes remain unchanged. Documentation/link/privacy validation runs
before committing this sanitized report. No row-level payload, protected address,
credential or new generated evidence is added to Git.

BOUNDARY_HANDOFF_SUFFICIENT: future Stage 10 can resolve evidence through the
unchanged Stage 8 → Stage 6/source-line map. No duplicate authoritative map or
Stage 0–8 change is required. HOLDOUT remains sealed; production and Pelias are
untouched. No second corrected run or new SLURM job was submitted.

NEXT: INDEPENDENT STAGE 9 DEVELOPMENT CANDIDATE REVIEW

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
The original implementation authorization ended at a DEVELOPMENT candidate
awaiting independent review, not acceptance. Independent review and owner
acceptance are now complete under D060 at the top of this record. Stage 10 is
NOT STARTED; no further work is authorized by this freeze.

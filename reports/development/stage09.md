# Stage 9 DEVELOPMENT execution record

## Status

STAGE09_DEVELOPMENT_RUN_IN_PROGRESS.
Job `1770156` was submitted once and observed PENDING (Resources) at submission.
No completed Stage 9 artifact/result is claimed in this submission record.
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

Next action requires owner `continue`. Inspect accounting once:

```sh
ssh goethe 'sacct -j 1770156 --format=JobID,State,ExitCode,Elapsed,AllocCPUS,MaxRSS,Start,End --parsable2'
```

If still PENDING/RUNNING, record state and stop again. If completed, reconcile
the immutable manifest, `_SUCCESS.json`, complete file/reference/input bindings,
in-job private/final reopen certificates and aggregate diagnostics before
declaring a DEVELOPMENT candidate ready. Further protected validation, if
needed, remains SLURM-only; no login-node data processing or automatic rerun.
For a failed job, preserve artifacts and collect sanitized failure/checkpoint
metadata first. This record does not predict the job's eventual outcome.

## Validation and complete pre-submission defect ledger

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

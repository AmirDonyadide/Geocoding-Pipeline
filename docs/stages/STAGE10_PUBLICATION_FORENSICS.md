# Stage 10 publication forensics and recovery analysis

Owner authorization, 2026-09-25: investigate F01/F02 from job 1781277, preserve
the complete failed state, repair publication observability, independently
validate generated outputs/C01/equality, and determine recovery from the frozen
contract. No full-generation resubmission, scientific redesign or performance
experiment is authorized. The [failure report](STAGE10_REMEDIATION_FAILURE_1781277.md)
remains historical evidence.

## Evidence and limits

The exact failed executable is `1b4c076c85ecb48c0a4e28668b69b99e0be128ad`.
It wrote the complete generation and manifest but no durable registration/seal.
There is no exception traceback or errno in the retained logs, no partial
failure receipt, and no terminal failure event. Static inspection cannot
recover a first failing instruction from the generic CLI code.

Using the preserved sanitized manifest, the unchanged corrected adapter
successfully constructs and hashes its 1,218-byte registration locally.
Synthetic end-to-end tests reach corrected registration, exclusive seal and
reopen. A C02 name/hash serialization defect is therefore not reproduced.
This does not prove that the historical run reached registration construction.

**New environment evidence:** the project-aware `pan_df -k /work/footprint`
reports quota total 122,558,593,750 KiB, used 122,556,955,713 KiB, available
**1,638,037 KiB (about 1.562 GiB), 100% used**. This is distinct from the
filesystem-wide free capacity used by the existing `shutil.disk_usage` guard.
The observation is post-failure and shared group usage can change. It supports
quota exhaustion as a possible explanation but does **not establish** the
historical exception, first failing operation or errno. No data is deleted to
make space. Current quota cannot support another full candidate run under the
existing 256 GiB reserve requirement.

Synthetic EDQUOT/ENOSPC injection proves two implementation weaknesses:

- The old failure handler tries to allocate a new receipt after the failed
  operation. A second write error can suppress that receipt and replace the
  original exception. Cleanup can also replace a pending primary exception.
- Full-run preflight checks filesystem capacity but not the project quota.
  A large statvfs result does not satisfy the project's effective reserve.

These are confirmed code paths, not a claim that either precise mechanism is
proven to have occurred in job 1781277. F01 remains unresolved pending further
evidence; no speculative registration/content repair is made.

## Bounded operational repair

The new [publication trace](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_publication_trace.py)
writes immutable attempt-local phase records for reservation, build, manifest,
fsync, initial validation, registration construction/write, prepared validation,
seal and reopen. Records contain the artifact key, exact executable, counters,
marker-presence booleans and monotonic timestamps. Failure records contain
closed exception classes/codes and errno, never exception text, SQL, protected
values or traceback locals.

A private 64 KiB file is exclusively allocated before input processing. A
bounded failure record overwrites those existing blocks, fsyncs, and atomically
renames the reserve to `failure.json`. The reserve identity, owner, type,
permissions, size and link count are checked before use. A reserve is not a
terminal receipt or commit authority. Filesystem failure can still prevent any
receipt; its absence never means success. First failure evidence is immutable;
post-seal telemetry failure cannot demote a fully validated committed artifact.
No publication marker, hash domain or adoption rule is weakened.

The execution handler attempts the reserved receipt before a terminal event;
receipt/cleanup errors cannot replace an already pending primary exception.
SIGTERM also attempts the bounded reserved receipt without long cleanup.
Full-run preflight additionally requires the established 256 GiB reserve from
the project-aware PanFS quota, failing closed on unavailable/unparseable output.
Stage 9 primitives and all scientific generator, identity, schema, runtime and
checkpoint-binding bytes remain unchanged.

## Contractual recovery result

**Cross-executable adoption is prohibited by the frozen contract.** The approved
[checkpoint adoption contract](STAGE10_FINAL_PERFORMANCE_REMEDIATION.md#checkpoint-adoption-contract)
explicitly binds the exact executable. The active
[`checkpoint_binding`](../../src/safe_geocoding_pipeline/preprocessing/stages/s10_query_materializer.py)
includes `execution_git_sha`, contract/profile/schema, transformation spec,
runtime lock, accepted Stage 8/9 manifests, context/input/science/budget identities
and checkpoint format. Unit/prefix adoption compares the complete binding for
equality before hash/schema/seal/inventory verification. The execution preflight
requires that same SHA to equal the clean detached checkout HEAD.

There is no separately substitutable publication-adapter identity or approved
scientific-code-only identity exception. The repair necessarily changes HEAD;
passing the old SHA from a new checkout is rejected. Rewriting checkpoint
bindings/seals would violate preservation. The reserved failed artifact lacks
`_COMMITTED`, so exact committed-artifact adoption is unavailable as well.

After preserved-output reconciliation, path B therefore applies: a new full
generation requires fresh owner authorization. Proposed resources remain
**4 CPUs / 32 GiB / 36 h**, subject to sufficient project quota and scheduler
preflight. No recovery publisher or new candidate is submitted by this work.

## Read-only preserved-output validation

The owner separately requires complete scientific/C01/equality validation
before recovery analysis is closed. The guarded
[forensic entrypoint](../../src/safe_geocoding_pipeline/preprocessing/stage10_publication_forensics.py)
pins job 1781277's exact manifest/executable/key and the old candidate manifest.
It validates all unit/prefix bindings, seals and physical hashes, row schemas,
logical fingerprints, IDs, complete occurrence population, six decisions/context,
PK/FK/orphan/cardinality checks, and recomputes the frozen aggregate summary.
It executes the existing independent C01 relational oracle and exact old/new
`EXCEPT ALL` hypothesis/scientific-decision comparison. Unexpected content drift
fails closed. It constructs and independently hashes registration in memory;
it does not persist registration or publish anything.

This validator never opens the failed database for writing, invokes scientific
generation/certificates/replay, adopts checkpoints, or mutates the failed target.
Only a new private forensic report/spill directory is created. Memory is bounded
by DuckDB plus the fixed 69,747-ID DEVELOPMENT population; spill is capped at
256 MiB. A 512 MiB project quota gate applies to this read-only diagnostic, not
to candidate generation. This does not weaken the 256 GiB full-run gate.
The [one-hour launcher](../../cluster/goethe_nhr/stage10_publication_forensics.sbatch)
uses 4 CPUs / 32 GiB, the exact pushed detached checkout and pinned Goethe
runtime. It is forensic validation only, not the conditional recovery run or
a full-generation retry. No automatic retry is allowed.

## Complete ledger and bounded self-review

| Item | Root cause / evidence | Fix and test | Output impact / regeneration |
|---|---|---|---|
| C01 | Missing original Q4 exclusion provenance; repair generated 237,263 field-slot decisions | Existing repaired science unchanged; complete read-only independent oracle prepared | Decision provenance changed in 1781277; population reconciliation pending |
| C02 | Original namespace/input-key nonconformance | Correct forms retained; synthetic full transition and independent portable domain test pass | Metadata only; no hypothesis change |
| F01 | Exact historical first operation/exception unresolved; registration construction succeeds with retained manifest | No speculative content/registration fix; quota-aware preflight and new phase evidence | Cannot declare historical root cause resolved |
| F02 | New receipt allocation/cleanup can mask the original exception; reproduced under storage fault injection | Preallocated bounded receipt, immutable phases, primary-exception preservation, SIGTERM tests | Operational evidence only; new executable requires full generation under exact-SHA binding |
| F03 | Historical pending status needed correction | Prior failure report preserved; new forensic report separates facts from hypotheses | Reporting only |
| F04 | Filesystem-wide space guard ignores effective project quota | Fail-closed `pan_df` quota parser/gate; malformed/error/low-space synthetic cases | Operational guard only; no science or thresholds changed |
| H01 | Initial forensic test fixture used wrong root attribute | Corrected fixture; complete real-Parquet checkpoint/C01/equality path tested | Test-only; no protected execution affected |
| H02 | Initial safe-suite command selected Python 3.14.7 | Repeated using existing pinned Python 3.14.3 environment; no runtime guard changed | Local test environment only |

The review also checks phase snapshot immutability, partial/colliding registration,
preexisting seals, reopen mismatch, reserve replacement, postcommit telemetry,
read-only old/failed inputs, independent input authority, no accidental adoption,
and privacy of all exception paths. Synthetic full forensic testing asserts
generation/replay are never called and all historical fixture file hashes stay
unchanged. Historical I01–I08 remain informational.

## Validation checkpoint

Pinned Python 3.14.3 safe suite: **1,152 PASS / 24 exact-ICU skips**; Stage 10
focused suite **316 PASS / 24 exact-ICU skips**. The first broad run
under the Mac's default Python 3.14.7 correctly failed 29 exact-runtime checks;
all passed under the existing pinned environment. No guard was bypassed.
Strict mypy passes 142 source/test/validator files; maintained-tree Ruff lint
and format pass. Refreshed inventory/schema/runtime locks, doc links, CLI help,
shell syntax and privacy/diff checks pass. No protected data has been processed
locally and no candidate/recovery run has been submitted.

Stage 0–9 unchanged; Stage 10 scientific rules unchanged; operating budget
UNSELECTED; HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET ACCEPTED.

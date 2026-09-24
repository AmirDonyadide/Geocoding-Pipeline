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

## Preparation ledger and bounded self-review

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

## Read-only forensic submission — 2026-09-24T21:45:42Z

Exact repair/validator executable `7353e3197adcb1b38cc821f48ee3d7da6d1f529c`
is pushed on `fix/stage10-publication-forensics` and checked out cleanly and
detached on Goethe. Manifest/runtime/inventory checks, private PanFS paths and
scheduler preflight pass. Job **1781847** was submitted exactly once: initial
state **PENDING / Priority**, 4 CPUs / 32 GiB / 1 h, general1 / footprint / normal,
no dependency or requeue. The [sanitized submission receipt](../scientific_assets/stage10_publication_forensics_submission_1781847.json)
binds its new report directory and fixed historical inputs. Available project
quota at preflight was 1,616,213 KiB, above the bounded audit gate and below the
full-run reserve. No cleanup or historical mutation was performed.

**STAGE10_PUBLICATION_FORENSICS_IN_PROGRESS.** No repeated polling, cancellation
or resubmission. This is preserved-output validation, not candidate recovery or
publication. Checkpoint/C01/content reconciliation remains pending. The owner
should later type `continue` in the same session. Cross-executable adoption
remains prohibited; no full-generation retry has been authorized or submitted.

## Completed forensic reconciliation — 2026-09-25

**STAGE10_REMEDIATION_FULL_REGENERATION_REQUIRED.** Read-only job **1781847**
completed **0:0** in **00:16:25**; scheduler MaxRSS **452,384 KiB**. It requested
4 CPUs / 32 GiB / 1 h; the exclusive partition allocated 80 CPUs. Accounting
reports local start/end 23:45:57–00:02:22 (UTC 21:45:57–22:02:22 on September 24).
The subsequent queue lookup found no active job; terminal accounting, the PASS
result and empty stderr agree. No repeat submission or processing occurred.

The byte-identical [sanitized compute result](../scientific_assets/stage10_publication_forensics_result_1781847.json)
has SHA-256 `3ce57a172a4bd0a52b641006304d715e25132ab34cb7bbbed17af3f97def1ad3`.
The [reconciliation receipt](../scientific_assets/stage10_publication_forensics_reconciliation_1781847.json)
binds accounting, scope and the independently recomputed aggregate summary.
The failed manifest remains `56496ce7e5b23d8ce35141204173cea1fe9ac3a98f0c03b4dcb6e222a99baf74`;
registration and `_COMMITTED` remain absent. Historical inputs were read only.

### Scientific validation and C01

All **1,099 unit checkpoints** and 16 prefix inventories validate under their
original executable binding. Hashes, seals, relation schemas, logical fingerprints
and deterministic identities pass. The complete accepted population reconciles:
**35,000 source rows, 69,747 contexts (34,822 STANDARD / 34,925 NATIVE), 418,482
family decisions and 142,677 hypotheses**. Source rows have one/two contexts in
253/34,747 cases; no row has more than two. Every context has exactly six Q1–Q6
decisions; Q7 is absent. PK/FK, map-back, orphan, duplicate-context and engineering
checks pass. No scientific contexts or certificates were regenerated; no
checkpoints were adopted and no artifact was published.

| C01 measure | Count |
|---|---:|
| Country-eligible contexts | 68,079 |
| Eligible contexts carrying mapped parser geography | 21,773 |
| All required Q4 field-slot decisions, including NOT_APPLICABLE | 418,482 |
| Required/actual PARSER_ONLY_FIELD_EXCLUDED decisions | 237,263 / 237,263 |
| Omitted slots with mapped parser geography | 19,043 |
| Missing/incorrect required provenance | 0 |
| Duplicate provenance violations | 0 |
| Parser-geography omitted slots missing the exclusion | 0 |
| Included source fields mislabeled parser-only | 0 |
| Q4 payload source-anchor violations | 0 |

The exclusion count is **field-slot policy provenance**, not a count of parser
components or source values declared untrustworthy. It describes the excluded
parser fallback for omitted slots while retaining the original source-gating
reason. This is why exclusions can coexist with a present source value. The
independent relational oracle reconstructs all expected decisions from the
previously reviewed source-field decisions and reconciles them exactly. It does
not call the repaired generator. Repeated parser components do not multiply the
field-slot decisions.

Exclusions by slot: country **68,079**, region **68,079**, locality **39,777**,
postalcode **61,328**. Included source locality/postcode fields remain
**28,302 / 6,751**; authorized postcode contradiction exclusions remain
**17,529**. Source-presence/disposition details are retained in the compute result.

### Exact content equivalence

Protected `EXCEPT ALL` comparisons find **zero differences** in the complete
old/new hypothesis relations and in decisions after removing only the newly
required C01 reason. Context IDs, hypothesis IDs/content, Q1–Q6 decisions,
convergence, Q4 payloads/Stage 9 gates and Q5/Q6 output remain unchanged.

- Old/new hypothesis logical fingerprint:
  `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1`.
- Old decision fingerprint:
  `227de0a64624eef84e7bf45664099ea6d7b5e52e53f16fc3ad361fa6e652c0a2`.
- Repaired decision/provenance fingerprint:
  `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420`.

Emitted Q1–Q6 remain **33,977 / 34,102 / 38,644 / 33,556 / 50 / 2,348**.
Q3 converges in **29,435** contexts. The hypotheses/context distribution for
0–5 is **1,668 / 14,831 / 31,948 / 21,250 / 50 / 0**; maxima are **4/context**
and **8/source row**, with zero engineering violations. These are structural
query-generation results, not accuracy/validity evidence.

### Publication evidence and final ledger

Corrected `STAGE10_DEVELOPMENT_QUERY_PLAN` registration with
`stage10_input_binding_sha256` constructs successfully from the actual retained
manifest. The portable hash is independently verified using the frozen
`SAFE:publication-commit:v2` domain and NUL separator. Nothing is persisted into
the failed artifact. Synthetic tests reach all publication states and cover
after-manifest, registration-write, before-seal, seal-collision and reopen faults.
This does **not** establish P11 completion or required scientific replays for
1781277; both remain incomplete. No historical first-failure operation/exception
can be recovered from the retained generic log and missing receipt.

| Item | Root cause / final disposition | Fix and test | Output impact / regeneration requirement |
|---|---|---|---|
| C01 | Original missing parser-fallback field-slot reasons; **preserved generation reconciliation PASS** | Existing frozen repair; independent full-population oracle, duplicate and source-anchor checks | Decision provenance only; hypothesis content/IDs equal; no content defect requires regeneration |
| C02 | Original incorrect registration namespace/input key; **adapter/hash verification PASS**, real publication still pending | Correct adapter retained; actual-manifest construction/independent hash and synthetic full-transition tests | Metadata only; new committed candidate still required |
| F01 | **OPEN: exact historical first exception unresolved**; no failure reproduced in registration construction | No speculative scientific/serialization fix; evidence limits documented, future phases instrumented | Cannot claim root cause fixed or authorize retry from this evidence alone |
| F02 | New receipt allocation and cleanup could erase/mask the primary error; **operational repair tested**; historical trigger not proven | Reserved bounded receipt, immutable phase records, primary-error preservation, storage/SIGTERM fault tests | No scientific change; new executable forces full generation under exact-SHA adoption rule |
| F03 | Stale pending/ambiguous failure reporting; **RESOLVED** | Historical failure report retained, terminal forensic result and recovery boundary recorded | Reporting only |
| F04 | Filesystem-wide reserve ignored effective project quota; **FIXED in preflight**, capacity remains an external blocker | Fail-closed project-aware quota parsing and tests; existing 256 GiB threshold retained | Operational only; full run must wait for sufficient verified quota |
| H01 | Synthetic forensic fixture used wrong root attribute; **RESOLVED** | Complete real-Parquet synthetic setup passes without historical mutation | Test only |
| H02 | Initial local suite selected unpinned Python; **RESOLVED** | Existing pinned Python 3.14.3 used; runtime guards unchanged | Test environment only |

Final bounded review covers all requested C01/C02/F01–F03 items plus directly
found F04/H01/H02. No additional scientific-output defect or protected leakage
was found in this scope. I01–I08 remain informational. The operational repair
remains executable **7353e3197adcb1b38cc821f48ee3d7da6d1f529c**; this reconciliation
changes documentation/sanitized evidence only. Pre-submission full safe/static
validation remains recorded above; current report/hash/document checks pass.

### Stop boundary

Path **B** is mandatory: `checkpoint_binding.execution_git_sha` must equal the
clean detached running HEAD. Validating old sealed bytes does not authorize
changing that binding or reusing them under the repaired executable. There is
no frozen publication-only executable exception. No recovery run, full retry,
new candidate or acceptance tag is submitted/created. Proposed future resources
remain **4 CPUs / 32 GiB / 36 h**, subject to owner authorization and project
quota of at least **256 GiB available**. Last observed quota was only about
**1.54 GiB**, not proof of the historical F01 cause.

NEXT: OWNER REVIEW OF PUBLICATION FORENSICS AND AUTHORIZATION FOR FULL
REGENERATION. Stage 10 science and Stage 0–9 unchanged; operating budget
UNSELECTED; HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET ACCEPTED.

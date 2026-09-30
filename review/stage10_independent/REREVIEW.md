# Stage 10 final independent rereview

Status: prepared for protected execution; no final verdict. This continues the
existing independent review of Stage 10, with complete applicable artifact
checks against remediated candidate 1785683. The historical failed review,
evidence and ledger remain unchanged. Candidate code and artifacts are not
modified. No Stage 11 work, HOLDOUT, production or Pelias access is authorized.

## Exact review and candidate identities

| Item | Identity |
|---|---|
| Review branch | `review/stage10-independent-20260923` |
| Original branch point | `e7fe4878f585c0283e57edee16f64883b8f8f758` |
| Previous final review evidence | `bced5920b5234e5598f1d0b3a4cb1269780862f4` |
| Current main and candidate reporting | `b29b230dece88404712105fc485c41411e12ba5d` |
| Nonrewriting merge into existing review branch | `bc837916d4b8c04e119ce6ac73587704b2f0c71b` |
| Candidate executable | `cf9e0fe4c12eb85f78051904c636ad084d87a541` |
| Candidate integration | `186d4220cbdede6556ce81d16504949215a6f034` |
| Candidate job | `1785683` |
| Manifest | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Logical dataset | `4c4e4e6a63f565f6b3ce97f54c74fcd817cbd79922189fdc07ad3e3d76205c1a` |
| Hypothesis relation | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Decision relation | `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420` |

Publication key: `stage10_development_20260928T081247Z_cf9e0fe4c12e`.
Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e`.

All unchanged design, contract, profile, schema, specification, runtime and
accepted DEVELOPMENT input identities are pinned in `rereview.py`. The batch
entry enforces executable → integration → reporting → review ancestry, retains
the prior evidence commit, and compares candidate source/tests/execution/spec
trees exactly. Only the review directory changes after the reporting merge.

## Independent checks

The corrected original oracles rerun on the new artifact. `rereview.py` preserves
the original `review.py` and its historic candidate pins. It adds
`remediation_oracle.py`; it does not call the implementation remediation audit
to decide correctness. The published audit is checked as a bound receipt only.

C01 expectations are rebuilt from the independent accepted-source/reference
policy, with all six ordered Q4 field slots. Each actual field must match the
expected disposition, original operative reasons and exactly one new exclusion
reason where required. Attachment, duplicates, included source fields, parser
payload leakage and source anchoring have separate defect counters. This is an
omitted-field policy, not a parser-token count. Repeated components cannot
multiply the expected field decisions. Reported totals are checked separately:
237,263 exclusions, comprising postalcode 61,328, locality 39,777, region 68,079
and country 68,079.

Old/new comparison pins and independently rehashes the historical artifact,
then compares complete relations with bidirectional `EXCEPT ALL`. Every
hypothesis column, identifier and membership must match. Removing only
`PARSER_ONLY_FIELD_EXCLUDED` from the new field-reason arrays must restore the
complete previous decision relation. No other reason, ordering, null, status,
lineage or content difference is projected away. The complete decision relation
must differ on exactly the 68,079 country-eligible Q4 rows.

The rereview denies Python reads under `/local` before opening any candidate
input. It opens final relations and checkpoint payloads only from PanFS, with
private paths and hashes validated. Native DuckDB views receive only confined
durable paths; the Python hook is an additional guard, not an OS sandbox.
The 16 publication phase receipts, durable failure reserve, final progress and
same-job audit receipts are checked without inspecting the vanished local path.

| Area | Review coverage |
|---|---|
| A Frozen bindings | Detached Git ancestry, exact pins, runtime lock/assets and accepted input validation; fail closed on mismatch |
| B Relations | Full schema, PK/FK, occurrence map-back, deterministic IDs, six decisions/context, zero Q7 |
| C Families and cardinality | Complete family matrix, context/row histograms, memberships, engineering bounds and weighted totals |
| D C01 | Independently reconstructed six-slot field expectations and exact attachment/reasons; source and parser-content safety |
| E Scientific equality | Both old logical relations independently rehashed; all-column, multiplicity-preserving comparisons |
| F C02 | Actual durable registration, corrected namespace/key, deprecated forms absent, independent portable hash domain |
| G P11 | Reservation path review, private exact inventory, immutable data, registration, exclusive seal, terminal reopen and after-read hashes |
| H Split neutrality | Static dependency/identity review, split versus colocated synthetic equality, old/new complete relation comparisons |
| I Durability | No local read allowed; durable authoritative relations, units, prefixes, metadata, seals, receipts and full reopen |
| J Checkpoints | 1,099 units, 16 prefixes, exact bindings, sealed physical inventories, population coverage and complete unit/final equality |
| K Q3 | Occurrence boundaries, ordered slots, LF intent, complete-intent convergence and retained lineage |
| L Q4 and Stage 9 | Independent source fields and exact reference schedule/capabilities/witnesses; Q04/Q08 only negative gates; unchanged baselines |
| M Q5 | Independent full-population whole-boundary alignment, corroboration, source and mixed-content vetoes |
| N Q6 | Exact ICU/runtime and independent script/normalization/eligibility checks, all outputs and unsupported suppression |
| O Abstention | Row-local country contract and all six decisions; no address-invalidity inference |
| P Replays | Frozen exact-row validation code, same executable/input bindings, three replay/four population counters and bound receipts; no extra replay |
| Q Failure observability | Current primary-exception preservation, reserved sanitized failure record, project-quota/local-space gates and successful receipt reconciliation |
| R Privacy | Code/portable-output inspection, offline/write/process guards, closed aggregate diagnostics and controlled logs |
| S Interpretation and budget | Query-generation claims only; null/UNSELECTED budget, ALL_ELIGIBLE_CATALOG and zero budget suppression |
| T Prior regression | Rerun prior relation/family/identity/certificate/checkpoint checks; retain R01–R05 corrections and prior evidence limits |

## Static findings and validation

The candidate diff adds seven lines to Q4 field provenance. It leaves query
eligibility, payload selection, all identity formulas and source/reference
evaluation unchanged. C02 changes the active manifest/registration namespace
and key, with rejection of the old namespace in terminal validation. The
accepted Stage 9 publication and I/O primitives are unchanged from accepted
Stage 9 commit `23cfb85f428b00301d68591ea5992763abf9ad88`.

The storage split changes destinations: context database, spill and stores use
the transient root; progress, sealed unit/prefix payloads and publication inputs
use `durable_root`. Publication copies durable inputs to exclusive final files
and revalidates their hashes. Absolute transient paths occur in operational
provenance and trace fields, outside scientific identity inputs. Existing
synthetic tests compare split/colocated complete relations, remove transient
storage and resume from durable checkpoints, and reject copy faults.

Publication error handlers attempt durable recording and preserve the original
exception if recording fails. The failure slot is allocated before input work,
uses a bounded closed exception representation and checks ownership/inode before
writing. Local filesystem stat failure cannot prevent a durable primary-error
receipt. Synthetic allocation, observer, termination, cleanup and quota faults
exercise these paths. Filesystem and project-quota gates precede accepted input
access. These observations do not establish historical F01's cause.

Local validation: combined review/candidate run **384 passed, 24 skipped**;
after adding the durable receipt-tree fault test, the complete review harness
has **36 passing tests** (candidate suite unchanged: **349 passed, 24 skipped**).
The 24 skips require exact public ICU assets unavailable locally; the protected
review validates the real pinned runtime. Ruff, batch syntax and frozen
implementation inventory validation pass. The updated log checker preserves
R05's separate input/workspace timer scopes and accepts exactly one final
`STAGE10_REMEDIATION_AUDIT_PASS` marker, while rejecting unknown or misplaced
markers. The 16 new trace receipts explain 1,133 rather than 1,117 receipt hashes.

No new candidate defect is established by static/synthetic checks. C01 and C02
remain pending independent protected confirmation. The
[rereview ledger](REREVIEW_LEDGER.md) records that distinction and R06 separately.

## Protected execution and continuation

Commit/push first; use a clean detached checkout of that exact pushed SHA.
`rereview.sbatch` requests general1/footprint, one node/task, 4 CPUs, 32 GiB,
12 hours, no requeue. It imports candidate format/input/runtime validators from
the clean detached executable checkout. No generation, adoption, publication
write or expensive performance confirmation runs.

Review output is separate and private:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/independent_review/rereview_<harness-sha12>_<job-id>`.
Temporary data, DuckDB and spill remain there. Only fixed aggregate evidence
may leave Goethe; exception messages, SQL, protected keys and values do not.

Submit once. If the one scheduler observation is PENDING or RUNNING, return
the required final-rereview in-progress receipt and stop. On owner continuation,
reconcile every phase and check, resolve review-only defects if necessary, and
complete the whole ledger before any verdict. Stage 10 remains unaccepted.

# Fresh independent Stage 11 review

Status: **independent review complete — PASS; NOT YET OWNER ACCEPTED**.
Complete protected review job **1790315** passed all **124 checks / 609,517
evaluations** with zero candidate defects and no harness errors. See the
[final report](FINAL_REVIEW.md), [complete ledger](LEDGER.md), and
[combined evidence](REVIEW_EVIDENCE.json). Review-harness job 1789589 remains
preserved as failed; R06 is resolved by the successful follow-up.
This review session starts from frozen main
`125b3684a000ea79523f77049ae1a290b0da8109` on
`review/stage11-independent-20261005`. Candidate executable
`8dce0e1078e123748ae692fa824200fc3e646aa4` and reporting
`d49e9340ef3ae9cb3caaec65d5ccf0c490ecf366` are objects under review,
not ancestors of this review branch. Only this review directory changes.

The owner explicitly authorized this fresh independent review and bounded
Goethe review jobs. No implementation-session state or assertion is used as an
independent oracle. No candidate code/artifact repair, new candidate, Stage 12,
top-N, operating budget, HOLDOUT, production or Pelias work is authorized.

## Independent evidence design

`oracle.py` derives the ordered 19-field validity matrix, binary encoding,
projection, Arrow schemas and logical hashes from the frozen prose. It imports
no candidate module. `reconcile.py` independently visits every Stage 10
hypothesis and Stage 11 core/mapping, compares complete core bytes and full
SHA-256, and rebuilds the complete sanitized scientific summary through
independent joins. No data sampling or family budget is used.

`operations.py` independently verifies physical inventories, private topology,
registration framing, all checkpoint payload hashes, seals, exact coverage and
checkpoint-to-final relation equality. `review.py` binds frozen Git/design,
accepted input and reporting objects before protected science is inspected.
It recomputes the accepted Stage 10 hypothesis fingerprint using the accepted
schema only; Stage 11 encoding/projection/hashing/summary/checkpoint/publication
utilities are not its oracle.

After the independent checks, the unchanged candidate's full reopen is an
additional conformance check. It is explicitly labelled supplemental.
Python audit hooks prohibit all `/local` opens during the entire review,
including the former `/local/1788751` workspace and supplemental reopen.
The reopened DuckDB path has spilling disabled and uses only manifest-listed
PanFS inputs. Audit hooks are not claimed to intercept native-library syscalls;
static SQL/path review and exact registered input paths cover that boundary.
No former local existence probe is made.

Protected reads occur only after the shared Goethe/SLURM guard. Python writes
and mutation operations against candidate, attempt and Stage 10 input trees
are denied; before/after hashes check immutable candidate and checkpoint trees.
The independent DuckDB connection is memory-capped with spilling disabled;
it creates no scratch directory, database file or spill file.
Only static check labels, aggregate counts, whole-artifact hashes and code-line
locations are exported. Exceptions never export messages, SQL, row IDs or values.
No network library is used for science; Python socket operations and DuckDB
HTTP/autoload extensions are disabled. Git/SSH orchestration transports code
and sanitized evidence only.

## Local verification

Run from repository root using the existing pinned Python 3.14.3 environment,
with absolute canonical paths to the detached candidate code and synthetic
fixture helpers:

```bash
PYTHONPATH=/private/tmp/safe-stage11-candidate-review-20261005/src:/private/tmp/safe-stage11-candidate-review-20261005/tests:review/stage11_independent \
PYTHONDONTWRITEBYTECODE=1 .cache/stage09-venv/bin/python -m pytest -q review/stage11_independent
```

Tests independently exercise framing and invalid states, field roles, complete
summary/fingerprint/checkpoint/registration oracles, interruption after a
reduction seal, local loss/resume, repartitioning, order/thread/compression
changes, collision/contract/manifest/registration failures, durable first-error
preservation and review guard/reporting safety. Candidate test fixtures supply
invented accepted-format Stage 10 rows; candidate scientific outputs are checked
by the new oracle. No protected fixture is imported.
The initial independent suite passed **493 tests** (1.12 s); no skips.
The R06 follow-up additionally tests the actual spill-disabled review connection,
safe OS-error classification and full synthetic reconciliation through that
connection. See [LOCAL_VALIDATION_R06.json](LOCAL_VALIDATION_R06.json).

Candidate safe regression: **1,340 passed, 27 skipped**, Python 3.14.3,
PyArrow 25.0.0, DuckDB 1.5.5 (44.65 s). Three skipped public-reference tests
were separately run against already-local public-only reference assets and
passed. Combined coverage reproduces **1,343 passing tests**, with only the
**24 optional ICU build/runtime tests** remaining skipped. Those test files
are byte-identical to frozen main and do not test Stage 11. All 158 candidate
Stage 11 tests pass. Independent tests supplement these implementation tests.
See [LEDGER.md](LEDGER.md) for review-environment/harness corrections.

## Protected execution

`review.sbatch` requests 2 CPUs, 8 GiB RAM and one hour, without job-local storage,
without requeue. Candidate evidence measured about 2 GiB process RSS and
647 seconds for generation plus multiple validations. The review streams
rows, uses a 2 GB DuckDB memory cap and performs no generation. These justify
a bounded DEVELOPMENT review envelope, not production resource estimates.

Code reaches Goethe only through Git at the exact pushed review SHA, checked
in a clean detached worktree before input access. The existing exact candidate
checkout is also verified clean. Output is a new directory:

`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage11/independent_review/review_<review-SHA-prefix>_<job-ID>/evidence.json`.

Submit once. Observe the scheduler once. If pending/running, report the required
in-progress record and stop until the owner says `continue` in this session.
No cancellation, duplicate submission, automatic retry or replacement candidate.
A failed review harness may be repaired within the owner's explicit review
authorization; any necessary follow-up uses a newly reviewed, exact pushed SHA.

## First review attempt and R06 repair

Job **1789589**, harness `be2b8881dad43793ca9221d37f47a84c8fb6ae7b`,
was submitted once at **2026-10-05T20:34:32Z**. On the owner's next `continue`,
one accounting observation found **FAILED / 1:0**, elapsed **25 seconds**.
The [sanitized immutable evidence](evidence_1789589.json) records **35 checks
passing, zero failed checks**, and an exception at `scratch.mkdir` before any
relation scan. Frozen provenance, manifests, complete input binding and private
candidate/checkpoint inventories had passed. The original receipt retained code
locations but no OS exception class/errno; the underlying filesystem cause is
not established. This is a review-harness failure, not a candidate verdict.

R06 removes the unnecessary scratch dependency for this bounded DEVELOPMENT
review. Both the independent connection and supplemental candidate reopen use
a 2 GB memory cap and disabled spilling; insufficient memory fails closed.
No PanFS spill fallback is introduced. Safe exception class and numeric errno
are now recorded without messages/paths/values. Original job and evidence remain
preserved; candidate code and artifacts are unchanged. Follow-up job **1790315**,
using exact harness `c4f1fac1596e89adf825786dce7d238e5adef34f`, completed
**0:0** in **00:04:56**. All protected checks, supplemental full reopen and
before/after immutability checks pass. Its [unaltered evidence](evidence_1790315.json)
has SHA-256 `ac43d1af51d0395fdde469b5bfb26d0560868facc1b519d164d2461c5fd2b32e`.

Stage 0–10 remain unchanged, Stage 11 design frozen, operating budget
**UNSELECTED**, Stage 11 **NOT YET OWNER ACCEPTED**, HOLDOUT sealed by accepted
authority and non-access, production/Pelias untouched, Stage 12 **NOT STARTED**.

**NEXT: OWNER ACCEPTANCE OF STAGE 11**

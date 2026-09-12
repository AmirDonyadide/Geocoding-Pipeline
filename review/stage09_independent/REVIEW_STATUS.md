# Independent Stage 9 review — awaiting the single controlled review job

No PASS/FAIL verdict has been issued. This is a continuation record, not Stage 9
acceptance, a completed defect ledger, or permission to implement/remediate.
Candidate source, tests, schemas, frozen assets, main, and prior artifacts are unchanged.

## Exact scope

- Reporting candidate: `1c7182931fd4be2a7d5dee00d3105a1e54377bae`.
- Executable: `3e10ac7c1309c2636f35c0709fa283305d60d998`.
- Approved protocol candidate: `96d17e763addc21b0a1c321c3a03666e928c25c7`.
- Candidate key: `stage09_development_20260910T155542Z_3e10ac7c1309`.
- Exact artifact: `/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309`.
- Expected manifest: `321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240`.
- Expected logical dataset: `7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3`.
- Review branch: `review/stage09-independent-20260912`.
- Local worktree: `/Users/amir/Documents/GitHub/safe_geocoding_pipeline-stage09-review`.

After `git fetch --prune origin`, main and origin/main were clean and exactly at
the reporting candidate. All three supplied commits are ancestors. Candidate
source/tests/cluster assets equal the executable. Stage 8 remains accepted;
Stage 9 is not accepted. HOLDOUT was not opened or profiled. No production data,
protected address strings, row identities, or credentials were inspected or emitted.

## Controlled review job — do not duplicate

Job **1771693** was submitted once, from clean detached pushed review executable
`89bcdc570bb5a4a8a4bf01a73a373c9dedbadc4e`.
It imports candidate code exclusively from the existing exact executable checkout.
The review script is [review.py](review.py), launcher [review.sbatch](review.sbatch).
It never calls a candidate materializer. It reads the accepted DEVELOPMENT artifact
and frozen public pack, writes a new private review directory, and emits only fixed
aggregate/public dimensions and checks. Candidate helpers are reused for the frozen
hash formats and validators; separate SQL/Python oracles check scheduling and Q04.

At 2026-09-12 19:52 UTC: **PENDING / Priority**, no dependencies, Requeue=0,
Restarts=0. Scheduler estimate: 2026-09-13 08:40:13 UTC; estimates can change.
Resources: general1 / footprint, one node, four requested CPUs, 32 GiB, two hours.
No cancellation, duplicate job, or candidate DEVELOPMENT rerun.

Expected controlled review output (canonical mount spelling is `/panfs/vdura1`):
`/work/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage09/independent_review/review_89bcdc570bb5_1771693`.
Logs: `logs/slurm/safe-stage09-independent-review_1771693.out` and `.err` under
the institutional project root. Only fixed phase names or exception types/file-line
locations can reach logs; never arbitrary exception text or SQL payloads.

On continuation, inspect this job once. If terminal, reconcile its preserved
phase reports. If the harness failed, classify the exact harness fault and fix
only the review harness. Do not resubmit unchanged or rematerialize the candidate.

## Completed local/public evidence

- Exact local Python 3.14.3 / Unicode 16 / PyArrow 25.0.0 / DuckDB 1.5.5.
- `PYTHONPATH=src <exact-python> -m pytest -q -m 'not requires_production_transfer_payload' --tb=short`:
  **836 passed in 19.08 seconds**. No protected transfer payload accessed.
- mypy: 96 source files pass; Ruff lint passes; format: 144 source/test files pass.
- Contract, schema-bundle, catalog and frozen-lock hashes reproduce expected values.
- All 25 public bodies and associated headers / 263 archive members are verified
  by the candidate public-lock tests, using retained exact copies, without refresh.
- Candidate public tests reproduce 1,255 permitted patterns and 1,092 eligible
  examples in the exact runtime. These tests do not resolve protected anomaly causes.
- [public_synthetic_review.py](public_synthetic_review.py): **23 additional cases
  pass**, using public frozen metadata and invented inputs. Cases cover full format,
  leading zeros, short codes, exact whitespace/hyphens, BR optional hyphen, SE ASCII
  space versus NBSP, Unicode digits, CN/BH exclusions, absent country/rule/subkeys,
  positive versus missing enumeration, prefix alternation and prerequisites, and
  full ISO code ownership versus unrecognized codes.
- Independently derive Q04 country eligibility from roots and nonempty alternate
  fields: **176 countries**, exactly matching candidate capability expansion.
- [check_sql.py](check_sql.py): **33 fixed review SQL statements** bind/execute on
  empty synthetic accepted schemas.
- Scheduler independently confirms candidate job 1771191 completed 0:0 in
  08:04:53 with batch MaxRSS 10,125,844 KiB, and diagnostic 1771149 completed 0:0.
- Diagnostic JSON was independently rehashed to
  `e8d8333201a8c0b061d12288fadf404d833a875ffe0a4d160d535b88e6844f35`.
  All ten case records were inspected: exact flags 131265, fresh successful
  open/mkdir, collision EEXIST preservation, three four-process one-winner races,
  empty seal, private single-link repeated reopening, fsync and symlink rejection.
  This supports the active exclusive-create/reservation primitive for the bounded
  single-node process; it is not a power-loss or cross-node experiment.

Exact local review interpreter:
`/tmp/stage09-independent-runtime.vI9413/exact/bin/python`.
Public-only local diagnostic receipts are in
`/tmp/stage09-independent-local-evidence/` (0700 directory / 0600 files).
Ignored public assets were copied to the isolated worktree's `external_data/`.
No protected artifact was transferred to the Mac.

## Review-area disposition before artifact results

| Area | Code/public evidence | Remaining immutable-artifact evidence |
|---|---|---|
| Publication | Permanent exclusive mkdir, prepared registration, exclusive empty seal; no active rename, takeover, historical inode rule or destructive reconciliation. Fault tests pass. | Exact terminal topology, full inventories/hashes, final reopening |
| Input/reference bindings | Fixed Stage 8/Stage 6 transitive constants, exact raw lock, profile/schema formulas, offline paths reviewed | Full byte binding/reopening |
| Relations | Six grains, source pairs deduplicated only across same-row equal representation, parser ordinals retained, complete match members | All PK/FK/count/hash checks, independent scheduling and coverage recomputation |
| Four states / ISO | Negative-authority gates; ISO only code recognition, owner relationship and country-blocked subdivision support; synthetic negative cases pass | Actual counts/authorities/witnesses |
| Metadata | Exact roots, array/path selection, full-match and grouped prefix semantics, exclusions and 176-country oracle pass | Actual Q04 argument digests/outcomes/representations, rule/country concentration |
| GeoNames | Country capability gates, partial-code exclusions, BR major limitation, US extended-code abstention, same-record joins; absence is open-world | Zero contradictions and 6,673 diagnostic mismatches, integrity/members |
| Country assessment | Q02-only source full-ISO-identifier reduction matches design; Q01/parser evidence cannot supply support | Independently count full-code source witnesses; distinguish absence from broken join |
| Normalization | ASCII-only upper, NFC/lower names, scoped separator membership equivalence, no numeric conversion/fuzzy/transliteration | Q04 original-pointer/digest comparison, aggregate separator/length counterfactuals |
| Scale | Fixed small reference RAM, bounded DuckDB, streamed component counters/members, linear scheduling; population-sized work cannot inherit DEVELOPMENT resources | Actual relation skew/concentration; no production throughput claim |
| Privacy/execution | Guarded DEVELOPMENT CLI, no external services/Pelias, no raw values in Stage 9 schema/log paths, candidate Git change surface reviewed | Runtime artifact/topology reconciliation; no HOLDOUT/production reads |
| Tests | 836 exact-runtime tests and 23 independent synthetic/public cases pass | Artifact checks are still required |
| Reporting | Denominators and reference-diagnostic wording inspected; no validity/accuracy claim | Reconcile all counts; retain limits of each aggregate and historical authorization record |
| Stage 10 handoff | Candidate/version/capability/state/witness pointers and unchanged Stage 8 lineage provide the designed boundary | Verify actual IDs/FKs/totality before confirming final handoff |

The 59.996% Q04 rate is **not classified A/B/C yet**. Existing tests and frozen
rules are insufficient to classify it. The queued harness computes independent
Python ASCII-regex outcomes, DuckDB agreement, exact normalized digests, country /
rule / scope / representation totals, distinct candidate/value grain, conflict
shape bins, and non-mutating separator/leading-zero counterfactual counts. It also
independently counts Q02 full-source-ISO witnesses. No queried strings are emitted.

Two reporting/acceptance boundaries need explicit treatment in the final review:
(1) the frozen design's country-cell release policy versus the later reporting
record; this review request explicitly asks for aggregate country diagnostics,
which stay controlled until their disclosure scope is assessed; (2) the design's
separately authorized human review protocol is not silently claimed completed by
machine tests. This review's explicit aggregate/synthetic instructions govern its
scope. Neither observation is yet a proved output-semantic defect or a confirmed
privacy breach.

## Findings ledger in progress

Candidate defects: **not finalized**. No candidate code defect has yet been
reproduced; pending checks must not be represented as passes.

| ID | Classification | Evidence / disposition | Candidate rerun |
|---|---|---|---|
| RH-001 | REVIEW_HARNESS | DuckDB reserved SQL aliases `role`, `value`, `rule` rejected during local empty-schema validation. Changed only review aliases; all 33 fixed statements pass. Corrected before the one submitted job, in 89bcdc5. | No |
| RH-002 | REVIEW_HARNESS | Initial local Python 3.14.7 caused three exact-runtime failures and isolated worktree lacked optional public assets; first exact-runtime collection then lacked installed distribution metadata. Created isolated exact runtime, installed candidate package/dev dependencies and copied retained public assets. Final 836/836 pass; no guard patched. | No |
| I-001 | INFORMATIONAL | DEVELOPMENT runtime/RSS alone do not establish production capacity. Billion-row/component implications require later authorized planning. | No conclusion pending |
| I-002 | INFORMATIONAL | Country assessment intentionally demands full recognized source subdivision IDs. Whether this explains all observed unresolved outcomes awaits the independent join. | No conclusion pending |

Final review must contain the complete candidate defect ledger and exact PASS/FAIL
wording requested by the owner, only after all meaningful checks are reconciled.

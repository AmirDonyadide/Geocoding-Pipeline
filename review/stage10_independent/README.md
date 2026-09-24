# Independent Stage 10 DEVELOPMENT review

Status: **independent review complete — FAIL**, with **two unresolved candidate
defects**. Protected jobs **1780706** and **1781037** both completed successfully.
All five harness findings are resolved; no candidate changes were made.
The [final report](FINAL_REVIEW.md), [complete ledger](LEDGER.md), and
[combined evidence](REVIEW_EVIDENCE.json) record the final disposition.
This is an independent review branch, not candidate implementation or acceptance.

## Identities and scope

- Review branch: `review/stage10-independent-20260923`.
- Branch point, current accepted/reporting main, and candidate reporting commit:
  `e7fe4878f585c0283e57edee16f64883b8f8f758`.
- Design freeze: `1443bb3b3c1bb50220bf38231e01552c66c4eaee`.
- Performance integration: `8baf05be1bd7bac2f7cfa5c38f2ab994805b68db`.
- Candidate executable: `63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`.
- Candidate job: `1774362`; this harness does not regenerate its outputs.
- Publication key: `stage10_development_20260921T112356Z_63f3cd107e69`.
- Artifact:
  `/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260921T112356Z_63f3cd107e69`.
- Manifest: `085b05f6201831de6aa908c599bb5541a85cc185a48022d2d93d1e0a9afcc3fa`.
- Logical dataset: `70abebdaeee44cf0eae09eb89e4ed68ef087f1596bfa86ea1bef6aef57ceed92`.

All other expected science, input, schema and runtime identities are pinned in
`review.py`, the unchanged candidate executable, and the hash-pinned reporting
manifest. Review code imports candidate format/runtime/input validators from
the original clean detached executable checkout. Candidate generation, adoption,
publication writers and complete scientific replay are not called by the review.

Only `review/stage10_independent/` is changed. Candidate history, accepted inputs,
artifact, protected logs and runtime are immutable. No HOLDOUT, production,
Pelias, external service or Stage 11 access is authorized or implemented.

## Independent evidence

`common.py` independently implements the frozen binary identity encoding.
`relations.py` reconstructs occurrence contexts from Stage 8, checks their exact
Stage 6 linkage, streams every published row for deterministic identifiers and
logical hashes, and checks Q1/Q2/Q3, relation grain, membership and cardinality.
`structured.py` independently derives row-local country recognition and Q4
fields from the accepted source evidence schedule, capabilities, arguments,
witness objects and pointers. It uses the accepted Stage 9 normalization
primitive, without calling the candidate's Stage 10 evidence policy.
`family_safety/oracle.py` independently implements Q5 alignment/grammar/vetoes
and Q6 script/normalization/eligibility. Only Q6's pinned low-level ICU transform
is reused. All contexts, including suppressed slots, are reviewed.

`lineage.py` independently reconstructs all seven complete selector streams on
at most 40 contexts selected by immutable ID order and fixed categories. It
never samples within a chosen witness/component stream. All-context source-line
certificates and all published row identifiers are checked separately. This
bounded certificate audit does not claim complete independent recomputation of
every reference certificate. No selected row IDs or strings leave Goethe.

`operations/oracle.py` independently checks checkpoint/index/seal hashes, exact
key coverage, diagnostic map-back, full unit-to-final relation equality, receipt
hashes and sanitized log structure. P11 format decoding and terminal checks use
the accepted primitive; independent checks cover physical inventory, registration
hash, frozen wire names, private topology and before/after artifact hashes.

## Coverage matrix

This is the original coverage plan; actual protected results are recorded in the
[reconciliation](RECONCILIATION_1780706.md).

| Area | Evidence and review method |
|---|---|
| 1 Frozen bindings | Exact executable checkout, manifest, all input/science/runtime pins; fail closed before relation review on mismatch |
| 2 Context grain | Independent Stage 8 occurrence reconstruction, Stage 6 slots, source/role/candidate bijection, equal-candidate roles, 0/1/2 distribution |
| 3 Relations | Full row/hash/ID/schema checks, PK/FK, six family slots, context map-back, zero Q7 |
| 4 Families | Six complete aggregate rows, closed reasons/statuses, membership and ownership |
| 5 Baselines | Full original representation and intent equality; Stage 9 cannot mutate Q1/Q2 |
| 6 Abstention | Independent SOURCE_ROW Q01 recognition; all six slots checked; no country-assessment gate |
| 7 Q3 | Exact ordered slots/mask, LF construction, trace and source-line certificates; within-context complete-intent convergence |
| 8 Q4 | Source fields, provenance, positive support, fixed field decisions; C01 separately recorded |
| 9 Negative authority | Exact 18-check source schedule; authorized Q04/Q08 capabilities, arguments and witnesses; no GeoNames/absence negative gate |
| 10 Q5 | All eligible and suppressed contexts; complete unit, unique alignment, corroboration, source vetoes, retained content and trace |
| 11 Q6 | Exact runtime lock/assets/dependencies; all-context script and output oracle, NFC, Greek/Cyrillic, unsupported output, native preservation |
| 12 Convergence | Complete intent equality, context-local membership, first owner, generation rank, family pairs |
| 13 Cardinality | Full histogram and weighted totals, role/row engineering bounds, zero budget suppression |
| 14 Identity separation | Static frozen formulas and full ID recomputation; no Stage 11/12 request or deployment identity |
| 15 Checkpoints | All units/prefixes, sealed inventory, exact multiset equality with final relations, complete key coverage |
| 16 Performance semantics | Static cache-key/selector audit; independent certificate sample; no actual candidate adoption (receipt check) |
| 17 Publication | Same PanFS/device assumptions, accepted primitives unchanged, reservation/registration/exclusive seal/reopen path; C02 separately recorded |
| 18 Fingerprints | Physical inventory, full independent logical relation/dataset hashing, schema/contract/profile/runtime pins |
| 19 Required replays | Frozen three-call publication path, exact candidate views, full row comparison, three replay/four population counters, receipt identity |
| 20 Privacy | Git inventory/static output review, fixed aggregate diagnostics, controlled logs, offline/process/write guard, immutable inputs |
| 21 Interpretation | Candidate report explicitly limits claims to query generation and distinguishes abstention/contradiction from invalidity |
| 22 Operating budget | Null/unselected budget and ALL_ELIGIBLE_CATALOG; no scientific-budget suppression |

## Static operational conclusions reconciled with the artifact

Reference payload caches use immutable object IDs, capability IDs, registry IDs,
or `(match_set_id, member_ordinal)`. A workspace reference revision invalidates
the stores. The certificate cache key includes each selected reference version,
asset, both capabilities, question, witness cardinality, complete singleton
witness and match-set ID. The key omits source arguments because that selector
contains reference material; the separate source-evidence certificate preserves
the complete argument rows. Eligibility is recomputed per occurrence. Selector
deduplication uses section/key plus exact encoded payload, retaining member
ordinals and distinct witnesses. The independent sample checks the resulting
complete selector bytes without this optimized cache.

Checkpoint windows use ordered context IDs with strict exclusive continuation.
Adoption requires identical complete binding and expected key window, valid
sealed metadata, exact private file hashes/schema, and copied-byte revalidation.
Incomplete units are regenerated only in a new attempt. The actual candidate
shows zero reused units; the reviewer did not repeat the performance
confirmation. IDs do not contain partition or checkpoint coordinates.

The unchanged accepted Stage 9 primitive is used for exclusive `_COMMITTED`
creation. Publication validates before registration, in prepared state, and
after the commit seal. Each validation streams recomputed rows against the
same published relation views, rejects extra/missing rows, and recomputes summary
and logical identity. These are the three frozen same-code reproducibility
replays; they are not independent scientific oracles. The review combines their
bound receipts/counters with separately written output checks, without imposing
a fourth replay or substituting a replay artifact.

## Execution and privacy controls

`review.sbatch` requests general1 / footprint, one node/task, 4 CPUs, 32 GiB,
12 hours, no requeue. Inputs are accessed only after the shared Goethe/SLURM
guard, exact detached-checkout checks and runtime validation. The review creates
one separate private output directory:

`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/independent_review/review_<harness-sha12>_<job-id>`.

DuckDB state, spill and temporary files stay under that directory. Python writes
outside it and networking are blocked. The only subprocess allowance is exact
`ldd` inspection of pinned public binaries before protected input validation;
that allowance is revoked after runtime initialization. The Python audit hook
is an extra safeguard, not a claim of OS-level sandboxing: native database writes
are separately constrained by the explicit review database/spill paths.

Portable output consists of static phase labels, booleans, aggregate counts,
fingerprints and static exception class/file/line diagnostics. Exception messages,
SQL, row IDs and protected strings are never serialized. Protected intermediate
relations stay in the private review output. Candidate hashes are rechecked after
review. Binding mismatch fails closed; ordinary false checks accumulate. A
reviewer-code exception is classified REVIEW_HARNESS and leaves the review
incomplete, requiring a harness-only correction and continuation.

Commit and push the harness before submission; create a new clean detached
Goethe worktree from that exact SHA. Preserve the existing remote main worktree
and all failed attempts. Submit once. If the sole scheduler observation is
PENDING or RUNNING, return the required in-progress receipt and stop. The owner's
next `continue` authorizes reconciliation, not duplicate submission.

## Local validation

- Independent synthetic harness: **28 passed** after R05 correction (**25** at
  original submission). Includes source arguments,
  same/cross-country occurrence lineage, all selector streams, Q04/Q08,
  NOT_FOUND/NOT_EVALUABLE, malformed country, Q5/Q6, unit-to-final equality,
  portable registration/hash bindings, missing-SLURM rejection,
  write/network rejection, process-allowance revocation,
  deliberate baseline corruption detection, separate input/workspace timer
  scopes, corrected log audit and rejection of malformed timer values.
- Candidate Stage 10 local suite: **252 passed, 24 skipped**. Exact public ICU
  build is unavailable locally; the skipped runtime tests do not establish the
  Goethe runtime. The guarded review checks the actual exact runtime.
- Ruff and batch shell syntax pass. Frozen implementation inventory validator
  returns `STAGE10_IMPLEMENTATION_INVENTORY_VALIDATION_PASS`.
- Candidate source/tests/cluster/scripts/spec tree is unchanged from executable
  to reporting main. Accepted Stage 9 publication/I/O primitives are unchanged
  from accepted Stage 9 main `23cfb85f428b00301d68591ea5992763abf9ad88`.
- Review files contain code, synthetic fixture construction and sanitized
  documentation only; generated caches are ignored and excluded from commits.

The [ledger](LEDGER.md) records every candidate, informational and reviewer
finding. Job **1781037** resolved R05 in 11 seconds with the guarded log-only
launcher; it preserved the first job's evidence and all candidate data. The
candidate verdict is **FAIL**; Stage 10 is **NOT YET OWNER ACCEPTED**.

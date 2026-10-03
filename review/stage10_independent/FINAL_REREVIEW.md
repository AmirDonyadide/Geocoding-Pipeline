# Stage 10 final independent rereview result

**STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION_INDEPENDENT_REREVIEW_PASS**

All requested A–T areas are complete. C01 and C02 are independently verified as
resolved; **candidate defects = 0**. No scientific drift, integrity, publication
or privacy defect remains. Candidate source, accepted inputs and both immutable
candidates were not modified. Stage 10 is **NOT YET OWNER ACCEPTED**.

The [complete ledger](REREVIEW_LEDGER.md) separates resolved historical defects,
review-harness findings and ten informational observations. The
[disposition record](REREVIEW_EVIDENCE.json) binds the unchanged
[protected evidence](evidence_1786959.json). All **281 named checks** and
**1,158,338 evaluations** passed; all **11 processing phases** completed with
**zero review-harness failures**. This verdict combines those protected results
with the code, contract, synthetic fault and reporting review in [REREVIEW.md](REREVIEW.md).

## Exact provenance

| Item | Value |
|---|---|
| Candidate executable | `cf9e0fe4c12eb85f78051904c636ad084d87a541` |
| Candidate integration | `186d4220cbdede6556ce81d16504949215a6f034` |
| Candidate reporting and current main | `b29b230dece88404712105fc485c41411e12ba5d` |
| Review branch | `review/stage10-independent-20260923` |
| Original branch point | `e7fe4878f585c0283e57edee16f64883b8f8f758` |
| Preserved prior final evidence commit | `bced5920b5234e5598f1d0b3a4cb1269780862f4` |
| Reporting merge into review branch | `bc837916d4b8c04e119ce6ac73587704b2f0c71b` |
| Review harness | `6c0a93edbd85fb45f5bd3472c08d65a7c045223d` |
| Current review job | **1786959 COMPLETED / 0:0**, **01:17:08** |
| Submission UTC | `2026-09-30T19:36:36Z` |
| Raw evidence SHA-256 | `a5832ab87ac417c5c550c980f7a47526f9a14ca3d7f5f28db931c710340d6103` |
| Disposition JSON SHA-256 | `b324d4c63b217e6d76e258399adca5c0ee288448259e53c63d80c81ce7bd1113` |

Requested: general1 / footprint / normal, one node/task, 4 CPUs, 32 GiB,
12 hours, no requeue. Accounting reports 80 batch CPUs under node allocation;
the reviewer connection uses four threads. Raw scheduler start/end:
`2026-09-30T21:36:56` / `2026-09-30T22:54:04`, without an embedded timezone
offset. Reviewer stderr is empty; both log files are 0600. Review and candidate
detached checkouts remain clean. No additional protected job was required.

Review output:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/independent_review/rereview_6c0a93edbd85_1786959`.

Candidate publication key: `stage10_development_20260928T081247Z_cf9e0fe4c12e`.
Artifact:
`/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/development/stage10_development_20260928T081247Z_cf9e0fe4c12e`.

## Frozen bindings and scientific relations

Every supplied frozen binding validates against the actual controlled artifact,
exact code and pinned runtime: executable/integration/reporting ancestry,
contract, profile, schema, transliteration specification, runtime lock and
fingerprint, accepted Stage 8/9 manifests, original DEVELOPMENT population,
artifact and publication key. The [pinned driver](rereview.py) retains all
expected identities. Accepted inputs and scientific contracts are unchanged.

| Independently validated identity | SHA-256 |
|---|---|
| Manifest | `558298d7260199cc24f994d7480def9ad268aca057347f86ca41fad675a5a860` |
| Logical dataset | `4c4e4e6a63f565f6b3ce97f54c74fcd817cbd79922189fdc07ad3e3d76205c1a` |
| Hypothesis relation | `c61ba899dbe4f714e2879995261b7d3a943e3b830ca69b4656e2d286230982e1` |
| Decision relation | `2c915039f6b8653fbfbd2acd3629cb7d1efd86190e3cb636c69542750c695420` |

**35,000 sources; 69,747 contexts = 34,822 STANDARD + 34,925 NATIVE.**
Source-row 0/1/2-context distribution: **0 / 253 / 34,747**. Exact accepted
occurrence bijection, Stage 6 linkage, roles and source-slot map-back pass;
17,913 equal-candidate rows retain both role occurrences. No cross-row,
country or boundary contamination is found.

**418,482 decisions = 69,747 × 6; 142,677 hypotheses.** Full logical hashing,
deterministic row identifiers, schemas, PK/FK, reason/status closure, membership
and context linkage pass with zero violations. Q7 decisions/hypotheses: **0**.
Hypotheses/context 0–5: **1,668 / 14,831 / 31,948 / 21,250 / 50 / 0**; totals
69,747 contexts and weighted 142,677 hypotheses. Maxima: **4/context, 8/source
row**; uniform and tighter role-derived bounds pass. Engineering overflow: **0**.

| Family | Eligible | Emitted | Converged | Suppressed |
|---|---:|---:|---:|---:|
| Q1 | 33,977 | 33,977 | 0 | 35,770 |
| Q2 | 34,102 | 34,102 | 0 | 35,645 |
| Q3 | 68,079 | 38,644 | 29,435 | 1,668 |
| Q4 | 33,556 | 33,556 | 0 | 36,191 |
| Q5 | 50 | 50 | 0 | 69,697 |
| Q6 | 2,348 | 2,348 | 0 | 67,399 |

For each family, eligible = emitted + converged and eligible + suppressed =
69,747. **172,112 eligible constructions → 142,677 context-local hypotheses**.
Convergence pairs: Q1/Q3 **14,694**, Q2/Q3 **14,741**, all others **0**.
Complete intents determine convergence; no cross-context text deduplication.
Stage 10 hypothesis identity remains distinct from future Stage 11 request and
Stage 12 execution identity; no later-stage identity is introduced.

## C01 and old versus new equality

Independent accepted-source/reference reconstruction checks all six ordered Q4
field slots, including suppressed Q4 contexts. The exclusion reason records the
forbidden parser-only fallback for omitted geography, not parser-token counts.
Repeated components cannot multiply the scientific field decisions.

| C01 field | Expected | Actual |
|---|---:|---:|
| postalcode | 61,328 | 61,328 |
| locality | 39,777 | 39,777 |
| region | 68,079 | 68,079 |
| country | 68,079 | 68,079 |
| Total | **237,263** | **237,263** |

Missing, duplicate, wrong-context, wrong-field, full-field-decision,
non-Q4 attachment, source-anchor and parser-only payload violations: **0**.
Included source fields incorrectly labelled parser-only: **0**.

Old/new complete hypothesis symmetric difference: **0**, including IDs,
content, context lineage and convergence memberships. Scientific decision
difference after removing only the C01 field reason: **0**. Unprojected decision
symmetric difference: **136,158**, exactly two sides of the 68,079 corrected Q4
rows. No other family decision, gate, Q3/Q4 payload, Q5/Q6 output or scientific
identity changes. Both old relation fingerprints were independently recomputed;
historical artifact bytes remained unchanged.

## Families country abstention and reference authority

The **1,668** zero-output contexts reconcile to the row-local valid-country
contract. They are structural abstentions, not invalid addresses. All six slots
agree; Stage 9 country resolution and cross-occurrence unanimity do not control
them. Q1/Q2 full representations have **zero mutations or missing baselines**.
Q3 occurrence-local ordered boundaries, masks, LF intent, traces and complete
source-line certificates match independently; complete-intent convergence passes.

Q4 remains source anchored. Postcode inclusions: **6,751**; authorized
contradiction exclusions: **17,529 = 17,527 Q04 + 2 Q08**. Exact source
arguments, capabilities, witness applicability and lineage pass. NOT_FOUND,
NOT_EVALUABLE and GeoNames never supply negative authority. Parser evidence
does not become source truth or alter baseline content.

Q5: **50** emitted whole-boundary transformations, **zero safety, alignment,
corroboration, source-field, content, trace or reason discrepancies**. Q6:
**157 Greek + 2,191 Cyrillic = 2,348**, one safely suppressed unsupported output.
ICU4C **77.1**, Unicode **16.0.0**, CLDR **47**, frozen Grek-Latn/Cyrl-Latn,
normalization/script gates and runtime lock pass; runtime/output mismatches
**0**. Native preservation passes. Zero Q5/Q6 coexistence is permitted.

## C02 publication storage and reproducibility

Actual durable registration kind: **STAGE10_DEVELOPMENT_QUERY_PLAN**; input key:
**stage10_input_binding_sha256**. Deprecated active forms are absent.
Independent portable hash using `SAFE:publication-commit:v2` plus NUL:
`d3a9df71b0be9ffb70d3d5ebe2c478bb70df81a205145443a67af42849aab532`.
Registration file hash:
`4487984315ff77597da06f3f3e87da958004281420646459e39db4c99d5ae471`.
Reopened publication binds the corrected registration.

P11 **reservation → immutable validated artifact → manifest → corrected
registration → exclusive _COMMITTED → full reopen** passes. Accepted Stage 9
primitives and PanFS assumptions are retained. All **16 publication phase
records**, **1,133 receipt hashes**, inventories, private modes and before/after
candidate hashes reconcile. No stale-reservation adoption, false success or
partial committed artifact is found.

The storage split is scientifically neutral. Absolute paths remain outside
scientific identity inputs; exact old/new equality and synthetic split/colocated
tests support this conclusion. With reads under `/local` prohibited, all final
relations, checkpoint payloads, metadata, receipts, seals and terminal publication
validate from PanFS. No checkpoint metadata contains a job-local dependency;
no transient database/WAL remains in the durable attempt. The durable
post-publication audit also validates.

All **1,099 units**, **16 prefixes**, **1,115 seals** pass executable/upstream
bindings, key coverage, order, hash, schema and topology checks. Complete unit
and final hypotheses/decisions match; diagnostic map-back differences are zero.
No partial checkpoint accepted; actual candidate reused zero units. Resume,
partition and original performance cache/selector semantics retain independent
static/synthetic validation. **924** complete selector comparisons on **28** fixed
contexts match, with full-population contents/source-line certificates checked
separately. This bounded certificate audit is not an exhaustive independent
reconstruction of every reference certificate.

Three required scientific replays remain bound to the exact executable, same
DEVELOPMENT population and published relations. Exact-row comparison code,
three replay/four population counters and durable receipts reconcile. No
replay-specific divergence or artifact substitution is found. No extra replay
or performance confirmation was imposed.

Current failure-observability repair passes: secondary receipt allocation cannot
mask the primary publication exception; durable preallocated sanitized recording,
local-state failure handling and quota/storage preflight are exercised by the
reviewed code and synthetic faults. Successful current receipts reconcile.
Historical F01's first exception remains unknown; no retrospective root cause
is asserted. Actual local-storage peak remains unmeasured. Both are informational.

## Complete coverage and disposition

| Requested areas | Disposition |
|---|---|
| A–C bindings, relations, family/cardinality reconciliation | PASS |
| D–F C01, old/new scientific equality, C02 | PASS |
| G–J P11, storage neutrality, durability, checkpoints | PASS |
| K–O Q3, Q4/Stage 9, Q5, Q6, country abstention | PASS |
| P–Q required replays and current failure observability | PASS |
| R–T privacy, interpretation/budget and prior regression | PASS |

Only sanitized aggregate evidence was exported. Protected relation reads ran
under the normal Goethe-NHR SLURM guard with immutable inputs, offline/process
controls and separate private review output. Candidate reports and review
output contain no protected address examples or unsupported geocoding accuracy,
address validity, precision/recall, final-correctness or rooftop claims.
Scientific operating budget: **UNSELECTED**; budget suppression: **0**.
Engineering ceilings do not select a future operating budget.

All six REVIEW_HARNESS findings are resolved separately. Protected rereview
needed no fix or additional job. Informational I01–I08 retain their stated limits
with current evidence confirming applicability; I09 preserves F01 uncertainty,
and I10 preserves the absent local-peak measurement. No further candidate
regeneration is required. Original review jobs 1780706/1781037 and failed-candidate
evidence remain preserved; job **1786959** establishes this current rereview.

HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 NOT YET OWNER ACCEPTED.

**NEXT: OWNER ACCEPTANCE OF STAGE 10**

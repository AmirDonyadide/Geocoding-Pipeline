# Stage 10 final performance confirmation 1774301

## Result and scope

**STAGE10_FINAL_PERFORMANCE_CONFIRMATION_VALIDATED**. Job **1774301** completed
with exit **0:0**, elapsed **00:40:27 (2427 s)**. One terminal accounting check
was made on owner continuation, 2026-09-21. No further submission occurred.
This is a performance confirmation, **not a DEVELOPMENT candidate publication**.

- Executable and harness: `63f3cd107e69c9ddc14b9b517b0c7ab3d5861e66`.
- Branch: `perf/stage10-query-generation`; submission reporting:
  `5dabdbe90e79cc1e178d37f926e1c4e88f6068ac`.
- Submitted `2026-09-21T09:55:52Z`; started `09:56:17Z`; ended `10:36:44Z`.
  Accounting displays these times in UTC+02:00.
- Requested 4 CPUs, 32 GiB, one node, four hours; no dependency/requeue.
  Accounting allocated 80 CPUs on `node23-008`; this is allocation topology,
  not measured use of 80 cores. TotalCPU 2406.496 s, UserCPU 2325.568 s,
  SystemCPU 80.927 s: approximately 0.99 core equivalents over the job.
- Scheduler batch MaxRSS **4003000 KiB (3.818 GiB)**; application process peak
  **5652276 KiB (5.390 GiB)**. Different measurement scopes; neither is silently
  substituted for the other. Both are below the unchanged 32 GiB request.
- Controlled output:
  `/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage10/confirmations/stage10_final_20260921T095422Z_63f3cd107e69`.

The [submission binding](../scientific_assets/stage10_final_confirmation_submission_1774301.json),
[exact sanitized result](../scientific_assets/stage10_final_confirmation_1774301.json),
[379-receipt hash inventory](../scientific_assets/stage10_final_receipt_inventory_1774301.json)
and [reconciliation/accounting/projection](../scientific_assets/stage10_final_review_1774301.json)
provide portable evidence. Result SHA-256:
`c6313e2ab94719d27e40d93743cced54253ec5f72a90f5d9349515ead7524c9a`.
Only sanitized aggregate receipts/logs were retrieved for local review. Protected
rows and all row comparisons remained inside the authorized Goethe allocation.

## Population, equality and checkpoint integrity

The selection is the original first hexadecimal-prefix-zero generation shard
from 1772639, ordered by immutable occurrence keys, not address content.
All **4424 / 4424 contexts**, **26544 decisions**, **9065 hypotheses** completed.
Selected occurrence-tuple fingerprint:
`165cfdaa7f7da72c418cc98db36ccf9484e2c7e19fbc24723571d264b0aa7190`.
The prepared full DEVELOPMENT index has **69747 contexts**, 6106088 parser
components and 933012 source-reference rows. These are distinct grains.

Phase A passed the preserved **16 contexts / 96 decisions / 35 hypotheses**
gate with exact scientific row equality before Phase B. Phase B compared every
output row, including protected content inside the allocation, with the complete
1774111 first pass. The protected relations, IDs, reason codes, memberships and
gating/transform results match. Existing 70-versus-139 partition equality is
preserved; that costly experiment was not repeated.

| Relation | Rows | Logical SHA-256, identical in B/C/D and historical golden |
|---|---:|---|
| query_hypothesis | 9065 | `547f880b41f0e061b92e2f7822f46bfa707be87d970543df64020ea5d2b47aae` |
| query_family_decision | 26544 | `2ab22ee9d079d62cecadd02bae9b86779a01c760a0bc914e8daeebc2ff6a94d7` |

Each pass has **70 complete units: 69 × 64 contexts + one × 8 contexts**.
Six decisions/context are exact. Full initial unit validation covers identities,
map-back, family membership and frozen engineering bounds before sealing.
No context loss, unresolved technical failure or engineering overflow occurred.

Phase C validated/adopted **70 units** in **12.585 s**, with **zero loaded or
scientifically regenerated contexts, zero certificate calls and zero family
generation calls**. It validated byte inventories, seals, bindings and population
keys, then restored private diagnostics. Hash reading scales with file bytes;
scientific work does not scale with the contexts inside adopted units.

Phase D used a separate confirmation-only copy: **69 valid units adopted;
one incomplete tail rebuilt; exactly 8 contexts regenerated**. It finished in
**63.855 s**, including 51.990 s of final coalescing/validation. All final rows and
logical hashes equal Phase B. Completed units had zero certificate regeneration;
the eight certificate calls belong only to the rebuilt tail. Neither Phase B
nor historical output was mutated. Incomplete output was never adopted as sealed.

## Separate timing scopes

All times are measured wall seconds, using monotonic clocks. Nested counters
are inclusive: they must not be added as independent components of elapsed time.

| Phase | Seconds | Scope |
|---|---:|---|
| Reference material preparation | 336.163 | Once across all prepared reference inputs |
| Parser certificate preparation | 560.143 | Once across the full component index |
| Context/index preparation | 6.730 | Initial full index |
| Sum of preceding one-time setup | **903.036** | About 15m03s; not replay throughput |
| Confirmation population/index setup | 5.208 | Additional harness-only population narrowing |
| Historical equivalence gate | 3.165 | Sixteen contexts |
| First-shard generation, Phase B | **1339.761** | Includes unit writes/checkpoints and prefix coalescing |
| Phase B final validation | 28.070 | Includes full historical golden comparison |
| Full adoption, Phase C | **12.585** | No scientific regeneration |
| Phase C final validation | 0.547 | Separate from adoption |
| Partial-tail resume, Phase D | **63.855** | Only eight contexts generated |
| Phase D final validation | 0.553 | Separate from tail resume |

Snapshot copy/hash (29.902 s), recovery (24.493 s), exact runtime initialization
(1.254 s) and minor harness overhead are separate from the table's setup sum.
Application elapsed is 2419.709 s; scheduler elapsed is 2427 s. The preparation
receipt's 903.393 s includes minor overhead beyond the 903.036 s phase sum.
Preparation counters prove it did **not repeat per checkpoint or resumed pass**.

| Generation portion | Contexts / decisions / hypotheses | Seconds | Contexts/s | Decisions/s | Hypotheses/s |
|---|---|---:|---:|---:|---:|
| EARLY | 1472 / 8832 / 3026 | 381.020 | 3.863 | 23.180 | 7.942 |
| MIDDLE | 1472 / 8832 / 2991 | 499.054 | 2.950 | 17.697 | 5.993 |
| LATE | 1480 / 8880 / 3048 | 407.675 | 3.630 | 21.782 | 7.477 |

These checkpoint intervals exclude final prefix coalescing. Late throughput is
about 6% below early and recovers from the slower middle; **no monotonic lifetime
collapse is reproduced**. This does not establish identical work per context or
prove why the middle portion costs more. No causal claim is inferred from WAL.

## Certificates, SQL and remaining computation

The prior full first pass spent **5323.204 s** in certificates out of
5579.365 s replay. The new pass spends **1161.041 s**, **4424 calls / 4423 actual
builds**, out of 1339.761 s replay. Certificate share is still **86.7%**; the
remaining context-specific traversal/selection is material, not claimed eliminated.
Confirmed repeated SQL and immutable encoding defects are removed, and the
formerly problematic shard now completes with stable bounded operational cost.

The small gate is a different scope: old diagnostic certificate time 13.845 s;
this gate 0.135 s for 16 calls. It is not used to project full-shard speedup.

Preparation encoded **3 registries, 47578 capabilities, 524098 needed objects and
554366 members once**, through one closure and four streams. Generation has
**zero registry re-encodes, zero reference point SQL and zero selector SQL inserts**.
There are 2315471 indexed reference-store lookups, 16105520 selector-add attempts
and 4636651 buffered insertions. These are still real in-process/disk-index work,
not hidden SQL. Canonical serialization: 2293169 calls / 16.265 s; identity
hashing: 249282 calls / 3.481 s. Complete immutable keys remain unchanged.

SQL executions fell from **2329428 to 10449** for the same 4424-context first pass.
Inclusive database execution time fell from **2848.611 s to 53.805 s**.

| Generation SQL category | Calls | Statement seconds |
|---|---:|---:|
| SOURCE_REFERENCE | 4424 | 20.258 |
| PARSER_CERTIFICATE | 4413 | 2.906 |
| SELECTOR_SPILL_SORT | 1040 | 23.958 |
| CONTEXT_PAGE | 142 | 0.987 |
| VALIDATION_OR_OTHER_SELECT | 142 | 0.962 |
| CHECKPOINT | 140 | 3.976 |
| DIAGNOSTIC_WRITE_OR_REGISTER | 72 | 0.439 |
| CHECKPOINT_KEYS | 71 | 0.119 |
| COMPONENT_STREAM | 5 | 0.009 |

The category call sum is exact; its 53.614 s timing sum excludes some wrapper
bookkeeping inside the 53.805 s inclusive timer. Preparation's 17 SQL statements
and final validation are separately counted. Historical category counts were
not captured: static code decomposition bounds the non-reference part by 40097,
so at least 2289331 old calls belonged to immutable reference resolution. The
exact old registry/capability/object/member split is unknown, not fabricated.

The enforced generation bound is **9C + 4K + 1 ≤ 580K + 1**, with C ≤ 64K.
Observed 10449 is below the C=4424/K=70 bound of 40097. It is independent of
component multiplicity. Per-context source/parser lookups remain bounded; there
is no SQL per witness/member/family. Full adoption uses exactly **211 = 3K+1**
statements and 2.756 s inclusive SQL, with no component/certificate work.
The partial tail uses 232 statements / 2.699 s.

Q5: 4424 family calls / **0.121 s**; alignment 4312 calls / **0.092 s**.
Q6: 4424 family calls / **0.148 s**; actual ICU 139 calls / **0.015 s**.
Neither path is a material bottleneck. Exact ICU4C 77.1 / Unicode 16.0.0 /
CLDR 47 and runtime lock remain unchanged, with no mismatch reported.

## Writes, WAL, memory and durable evidence

First-pass output write time: **5.527 s**; output close/checkpoint: **42.229 s**;
database checkpoint: **3.993 s**; prefix coalescing: **52.002 s**. These inclusive
timings overlap. First-pass sampled WAL high-water is **4679084 bytes (4.462 MiB)**;
adoption/tail high-water is **4694899 bytes (4.477 MiB)**. Every observed completed
checkpoint reports **zero WAL afterward**; WAL is absent after close. Bounded
key pages and commits remain effective. These are sampled highs, not a continuous
proof that no transient byte exceeds them. No prolonged transaction or steady
memory growth is indicated by the receipts; application peak remains 5.390 GiB.

Whole-process Linux I/O counters: rchar 27280138159, wchar 9754791422,
read_bytes 33619968, write_bytes 9044987904. Scope includes setup and all passes;
kernel accounting/cache semantics do not establish physical PanFS traffic.

All **379** retrieved receipt hashes match the controlled inventory. Event groups:
4 overall/runtime/terminal, 3 preparation, 1 gate, 74 first-generation,
144 adoption and 143 partial-tail receipts; plus 10 root result/phase receipts.
Setup, generation start/end, every checkpoint, resume adoption progress,
validation start/end and terminal success are durable. Stdout has 212 parseable
fixed aggregate JSON records (210 checkpoint, one copy progress, one success);
stderr is empty. No protected query/source values occur in these portable records.
No candidate manifest, registration or `_COMMITTED` was created.

Review-only assumptions corrected during reconciliation: population setup is
persisted in the root receipt, not a separate progress directory; separately
taken preparation snapshots differ by 67805 ns of elapsed time while all their
counters/timers are identical. SQL wrapper/category timings have distinct scopes.
These are review-harness observations, not scientific or execution defects.

## Full DEVELOPMENT projection and proposed resources

**Extrapolation, not a measured full run.** Full N=69747; observed C=4424.
Generation including checkpoint/coalescing projects to **5.87 h** using
1339.761 × N/C. The unchanged publication path performs **three complete scientific
replays**: validation before registration, prepared-state validation, and committed
reopen validation. `CatalogArtifact.validate` calls `replay` each time. None is
skipped or weakened by this remediation. This confirmation did not publish a
candidate, so their full cost remains a forecast.

The per-replay proxy is (1233.138 s context construction + 2.224 s family
generation) × N/C = **5.41 h**. It excludes full-run output comparisons/summary
cost, covered by explicit planning allowances below. One-time setup uses the
measured 903.036 s across the already full input population; it is not multiplied
by N/C. Historical input/runtime validation and setup before attempt creation
was about 4149 s in 1772639, plus 128 s until shard creation; these are historical
timing envelopes, not isolated current measurements.

| Planning scenario | Formula / assumptions | Estimate |
|---|---|---:|
| Central | 5.87 h generation + 3 × 5.41 h replay + 903 s setup + historical 4149 s pre-attempt envelope + 128 s workspace allowance + 2700 s additional copy/hash/summary/finalization allowance | **24.3 h (87431 s)** |
| Conservative operational | Four complete traversals at the slowest measured portion, 2.949577 contexts/s; + 903 s setup + 7200 s input allowance + 128 s workspace allowance + 5400 s extra finalization allowance | **30.1 h (108217 s)** |

The extra allowances are explicit planning assumptions, not observed timings or
statistical confidence limits. The forecast assumes the hash-prefix shard is
representative of other witness/component mixtures and comparable filesystem
conditions. Publication's output comparisons and full input validation were not
timed end to end here; thus neither estimate is a guarantee or production claim.

Recommend the next owner-authorized full run request **4 CPUs / 32 GiB / 36h**,
with unchanged checkpointing and durable progress. `general1` permits up to
21 days. **24h is not a reliable limit** after pricing the three retained scientific
replays; the 36h proposal is based on measured repaired throughput plus validation
cost/headroom, not an attempt to hide the repaired algorithmic defects. No such
job has been submitted or is authorized by this confirmation result.

## Complete final P01–P12 disposition

| Item | Disposition | Evidence / remaining limit |
|---|---|---|
| P01 fine-grained SQL | VALIDATED | Zero reference point SQL; 10449 statements satisfy derived checkpoint bound; selector SQL inserts zero |
| P02 one-time preparation | VALIDATED | Registry/material encoded once; parser preparation once; 903.036 s separated; no repeat in generation/adoption/tail |
| P03 certificate dominance | MITIGATED | Repeated SQL/encoding defect fixed; 5323.204 → 1161.041 s; residual exact traversal still 86.7% but stable and operationally bounded |
| P04 checkpoint/resume | VALIDATED | 70 complete units adopted without scientific work; partial state adopts 69 and rebuilds only eight contexts; identical final relations |
| P05 durable observability | VALIDATED | All 379 receipts hash-verified, setup/checkpoint/adoption/validation and terminal success present |
| P06 Q5/Q6 | INFORMATIONAL | Negligible measured time, frozen logic/runtime unchanged; no speculative optimization |
| P07 resource planning | VALIDATED | Confirmation completes in 40m27s within 4h; full-run forecast prices validation and recommends 36h conditionally |
| P08 transaction/WAL | VALIDATED | Sampled maximum 4.477 MiB, zero after every observed checkpoint, absent after close; bounded unit transactions |
| P09 population/equivalence | VALIDATED | Exact 16/96/35 gate and all 4424 historical rows; B/C/D logical equality; prior 70/139 equality retained |
| P10 snapshots/termination | VALIDATED | Immutable durable snapshots; terminal success in this run; controlled SIGTERM/interruption behavior established by executable's synthetic tests |
| P11 publication/reopen cost | DEFERRED_WITH_JUSTIFICATION | Candidate publication outside this authorization; three unchanged full replays included in forecast, actual full-run validation still required |
| P12 boundaries/history | INFORMATIONAL | Original 24h cause remains unresolved; no need to reconstruct it; failed attempts/history preserved |

The implementation self-review R01–R09 remains resolved as recorded in the
[remediation record](STAGE10_FINAL_PERFORMANCE_REMEDIATION.md). No new major
performance or scientific defect was found. P03 is explicitly mitigation, not
a claim of optimal certificate computation. P11 remains a full-run evidence
boundary; no publication safeguard is removed to improve this confirmation.

Pre-submission validation evidence remains **276 focused Stage 10 tests**,
**1050 safe repository tests** including Stage 8/9, mypy, Ruff, exact runtime,
SQL/adoption/partition/termination tests, inventory/schema/spec, privacy, docs,
CLI and shell checks. This continuation changes reporting only; fresh receipt,
report/link/hash/runtime-inventory/privacy and diff checks accompany it.
This is the author's bounded reconciliation, not the future independent
DEVELOPMENT candidate review.

All thirteen owner confirmation requirements pass within their stated scopes:
complete population, exact equality, no loss, sealed checkpoints, bounded SQL,
immutable certificate reuse, zero-regeneration adoption, partial-tail isolation,
bounded WAL, sustained throughput, bounded memory, durable receipts and privacy.
Stage 0–9 and Stage 10 science are unchanged; operating budget **UNSELECTED**;
HOLDOUT sealed; production/Pelias untouched; Stage 11 NOT STARTED;
Stage 10 **NOT ACCEPTED**. No geocoding correctness or production readiness claim.

**NEXT: OWNER AUTHORIZATION FOR ONE CORRECTED STAGE 10 DEVELOPMENT RUN.**

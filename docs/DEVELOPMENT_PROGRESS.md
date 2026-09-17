# DEVELOPMENT progress

Current repository status. Execution checkpoints are dated records, not live
scheduler observations. Contracts and evidence are linked below.

| Stage | Name | Status | DEVELOPMENT evidence | Production status |
|---:|---|---|---|---|
| 0 | Source inventory | **`STAGE_0_ACCEPTED`** | Benchmark V1 bound to accepted 1,405-file population; [report](../reports/development/stage00.md) | **ACCEPTED** — `NEW_STAGE0_1411_ACCEPTED`, 1,411 files |
| 1 | Lossless ingestion | **`STAGE_1_ACCEPTED`** | Stable identity/provenance foundation; [report](../reports/development/stage01.md) | **ACCEPTED** — `NEW_STAGE1_1411_ACCEPTED`, 141,048,582 rows |
| 2 | Schema/provenance harmonization | **`STAGE_2_ACCEPTED`** | 35,000 → 35,000; all 22 incoming fields preserved; four structural fields added; [report](../reports/development/stage02.md) | **NOT STARTED** |
| 3 | Safe text cleaning | **`STAGE_3_ACCEPTED`** | Jobs `1759269`/`1759272`; exact v1/v2 scientific equality and bounded validation; [report](../reports/development/stage03.md) | **NOT STARTED** |
| 4 | Lowercase canonical forms | **`STAGE_4_ACCEPTED`** | Job `1759421`; independent job `1759473`; exact Python `str.lower()`; [report](../reports/development/stage04.md) | **NOT STARTED** |
| 5 | Address reconstruction | **`STAGE_5_ACCEPTED`** | Job `1759603`; independent job `1759692`; neutral U+0020 reconstruction; [report](../reports/development/stage05.md) | **NOT STARTED** |
| 6 | Early exact deduplication | **`STAGE_6_ACCEPTED`** | Job `1759819`; independent job `1760055`; 69,747 occurrences → 51,779 exact candidates; [report](../reports/development/stage06.md) | **NOT STARTED** |
| 7 | libpostal parsing/evidence | **`STAGE_7_ACCEPTED`** | Evidence-only job `1763516`; rereview job `1763656`; no semantic-trust claim; [report](../reports/development/stage07.md) | **NOT STARTED** |
| 8 | Lossless address-evidence projection | **`STAGE_8_ACCEPTED`** | Candidate `231cdbf9…`; executable `c04cb972…`; jobs `1764273`/`1764376`; zero candidate defects; [report](../reports/development/stage08.md) | **NOT STARTED** |
| 9 | Conservative offline reference evidence | **`STAGE_9_ACCEPTED`** | Executable `3e10ac7c…`; job `1771191`; independent review `a9ae443c…` / job `1772139`; zero candidate defects; [acceptance](../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14) | **NOT STARTED** |
| 10 | Bounded multi-hypothesis query generation | **IMPLEMENTED — NOT ACCEPTED** | Executable `f83480d6…`; public runtime job `1772341` completed; connection preflight blocked DEVELOPMENT submission on 2026-09-15; [record](stages/STAGE10_IMPLEMENTATION.md#executable-pushed-connection-preflight-blocked--2026-09-15) | **NOT STARTED** |
| 11–14 proposed | Query QA → Pelias top-N → scoring → granularity/abstain | **PROPOSED — NOT STARTED** | Remaining compact replacement architecture; [pipeline specification](PIPELINE.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

## Current checkpoint

D064–D066 record authorization for Stage 10 implementation and exactly one
bounded DEVELOPMENT catalog, followed by independent review. Executable
`f83480d60449bcc904c0c622e394e12df3c3f2d9` is pushed. The pinned Goethe ICU
runtime was verified by public-only job `1772341`; that job is not a DEVELOPMENT
execution. On 2026-09-15, DNS resolution failed while eduVPN was disconnected,
before remote checkout, publication reservation or scheduler submission.
The [implementation record](stages/STAGE10_IMPLEMENTATION.md#executable-pushed-connection-preflight-blocked--2026-09-15)
defines the outstanding preflight and single-run boundary. No DEVELOPMENT
artifact or Stage 10 acceptance is claimed.

Stage 7 acceptance guarantees reproducible parser evidence, not semantic truth
or trust from warning absence. Stage 8 acceptance preserves its lossless
projection and all rejected publication attempts. Stage 9 acceptance is scoped
reference evidence: Q04 conflict rates are not invalid-address rates, and its
country assessments remain unresolved under the frozen witness rule. Exact
limitations and histories remain in the linked reports.

Production Stage 2 onward, Stage 11 onward and geocoding remain unstarted.
HOLDOUT remains sealed. Documentation maintenance does not authorize execution.

# DEVELOPMENT progress

This page is the short current status index. Technical contracts and evidence
are in the linked stage records and sanitized reports.

| Stage | Name | Status | DEVELOPMENT evidence | Production status |
|---:|---|---|---|---|
| 0 | Source inventory | **ACCEPTED** | [Stage 0 record](stages/STAGE00_SOURCE_INVENTORY.md); Benchmark V1 bound to accepted 1,405-file population | **ACCEPTED** — `NEW_STAGE0_1411_ACCEPTED`, 1,411 files |
| 1 | Lossless ingestion | **ACCEPTED** | [Stage 1 record](stages/STAGE01_LOSSLESS_INGESTION.md); stable identity/provenance foundation | **ACCEPTED** — `NEW_STAGE1_1411_ACCEPTED`, 141,048,582 rows |
| 2 | Schema/provenance harmonization | **ACCEPTED** | 35,000 → 35,000; all 22 incoming fields preserved; four structural fields added; [report](../reports/development/stage02_summary.md) | **NOT STARTED** |
| 3 | Safe text cleaning | **`STAGE_3_ACCEPTED`** | Jobs `1759269`/`1759272`; exact v1/v2 scientific equality and bounded validation; [report](../reports/development/stage03_summary.md) | **NOT STARTED** |
| 4–19 | Remaining pre-geocoding stages | **PLANNED — NOT STARTED** | No implementation or DEVELOPMENT run | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

The exact next scientific action is **Stage 4 — Lowercase canonical forms —
NOT STARTED**. It requires a reviewed design and explicit approval. Production
Stage 2 also remains not started.

# DEVELOPMENT progress

This page is the short current status index. Technical contracts and evidence
are in the linked stage records and sanitized reports.

| Stage | Name | Status | DEVELOPMENT evidence | Production status |
|---:|---|---|---|---|
| 0 | Source inventory | **ACCEPTED** | [Stage 0 record](stages/STAGE00_SOURCE_INVENTORY.md); Benchmark V1 bound to accepted 1,405-file population | **ACCEPTED** — `NEW_STAGE0_1411_ACCEPTED`, 1,411 files |
| 1 | Lossless ingestion | **ACCEPTED** | [Stage 1 record](stages/STAGE01_LOSSLESS_INGESTION.md); stable identity/provenance foundation | **ACCEPTED** — `NEW_STAGE1_1411_ACCEPTED`, 141,048,582 rows |
| 2 | Schema/provenance harmonization | **ACCEPTED** | 35,000 → 35,000; all 22 incoming fields preserved; four structural fields added; [report](../reports/development/stage02_summary.md) | **NOT STARTED** |
| 3 | Safe text cleaning | **`STAGE_3_ACCEPTED`** | Jobs `1759269`/`1759272`; exact v1/v2 scientific equality and bounded validation; [report](../reports/development/stage03_summary.md) | **NOT STARTED** |
| 4 | Lowercase canonical forms | **`STAGE_4_ACCEPTED`** | Job `1759421`; independent job `1759473`; 35,000 → 35,000; exact Python `str.lower()`; [report](../reports/development/stage04_summary.md) | **NOT STARTED** |
| 5 | Address reconstruction | **`STAGE_5_ACCEPTED`** | Job `1759603`; independent job `1759692`; 35,000 → 35,000; exact reconstruction and six accepted non-damaging boundary limitations in a 179-row risk scope; [report](../reports/development/stage05_summary.md); [Stage 5 record](stages/STAGE05_ADDRESS_RECONSTRUCTION.md) | **NOT STARTED** |
| 6 | Early exact deduplication | **`STAGE_6_ACCEPTED`** | Job `1759819`; independent job `1760055`; 35,000 → 35,000; 69,747 occurrences → 51,779 unique exact candidates; zero collision/map-back/fixed-500 mismatches; [report](../reports/development/stage06_summary.md); [Stage 6 record](stages/STAGE06_EARLY_EXACT_DEDUPLICATION.md) | **NOT STARTED** |
| 7 | libpostal parsing | **`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`** | Authoritative job `1760221` and validation/fixed-500 jobs passed machine integrity; qualitative/root-cause evidence found material parser-quality errors, and context-aware libpostal is unavailable. Country-aware eligibility job `1762293` passed. Public-only job `1762661` published the pinned DeepParse bundle; compute smoke `1762663` failed pre-scientifically at a missing execution-site marker before bundle/model/synthetic execution. No protected inference was submitted. [candidate report](../reports/development/stage07_development_candidate_report.md); [root-cause report](../reports/development/stage07_quality_root_cause_summary.md); [context diagnostic](../reports/development/stage07_context_provenance_summary.md); [stabilization audit](../reports/development/stage07_stabilization_prelaunch_audit.md); [Stage 7 record](stages/STAGE07_LIBPOSTAL_PARSING.md) | **NOT STARTED** |
| 8–19 | Remaining pre-geocoding stages | **NOT STARTED** | No implementation or DEVELOPMENT run | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

DEVELOPMENT Stages 0–6 are accepted. Stage 7 v1 completed its DEVELOPMENT
machine run but remains not ready because targeted qualitative evidence found
genuine label and boundary failures that fixed Stage 8 mapping cannot safely
repair without guessing. Stages 8–19 are not started. Production
Stage 0 and Stage 1 are accepted; production Stages 2–7 are not started.
HOLDOUT is untouched and sealed.

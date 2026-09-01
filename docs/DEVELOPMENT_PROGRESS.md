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
| 7 | libpostal parsing/evidence | **`STAGE_7_DEVELOPMENT_CANDIDATE_NOT_READY`** | Authoritative v1 job `1760221` and validation/fixed-500 jobs passed machine integrity; qualitative/root-cause evidence found material parser-quality errors. Country-aware eligibility job `1762293` passed. DeepParse is closed. Fresh validation rejected the frozen readiness gate. D035 now freezes evidence-only `stage07_parser_evidence_contract_v2`: exact v1 outputs are retained, structural reasons are warnings only, and no semantic trust status is published. Full v2 DEVELOPMENT projection is pending. [evidence-only v2 design](../reports/development/stage07_parser_evidence_v2_design.md); [fresh v2 validation](../reports/development/stage07_v2_fresh_development_validation.md); [candidate report](../reports/development/stage07_development_candidate_report.md); [Stage 7 record](stages/STAGE07_LIBPOSTAL_PARSING.md) | **NOT STARTED** |
| 8–14 proposed | Evidence → hypotheses → Pelias top-N → scoring → granularity/abstention | **PROPOSED — NOT STARTED** | Compact replacement for the old unstarted 8–19 plan; [architecture redesign](../reports/development/post_stage07_geocoding_architecture_redesign.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

DEVELOPMENT Stages 0–6 are accepted. Stage 7 v1 completed its DEVELOPMENT
machine run but remains not ready. Its controlling evidence-only v2 preserves
v1 raw evidence and treats structural signals as warnings rather than semantic
truth. Machine-only job `1763433` applied the unchanged frozen rule to the 604
untouched fixed-frame candidates and froze a deterministic 240-case selection.
Owner-authorized Codex semantic review of exactly those 240 cases was completed
without changing predictions or thresholds and returned
`STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL`. That failed rule is immutable
history and is not a v2 trust gate. The full 51,779-row evidence projection is
pending. The
old Stages 8–19 and proposed replacement Stages 8–14 are not started. Production
Stage 0 and Stage 1 are accepted; production Stages 2–7 are not started.
HOLDOUT is untouched and sealed.

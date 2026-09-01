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
| 7 | libpostal parsing/evidence | **`STAGE_7_ACCEPTED`** | Exact candidate `656a16d3…`; evidence-only job `1763516`; independent rereview job `1763656` passed all 51,779 candidates and 69,747 occurrences with zero parser calls/trust claims. Components remain hypotheses/evidence; warning absence is not trust. Historical v1 semantic findings and the failed readiness experiment remain failures. [rereview](../reports/development/stage07_parser_evidence_v2_independent_rereview.md); [current evidence report](../reports/development/stage07_development_candidate_report.md); [Stage 7 record](stages/STAGE07_LIBPOSTAL_PARSING.md) | **NOT STARTED** |
| 8–14 proposed | Evidence → hypotheses → Pelias top-N → scoring → granularity/abstention | **PROPOSED — NOT STARTED** | Compact replacement for the old unstarted 8–19 plan; [architecture redesign](../reports/development/post_stage07_geocoding_architecture_redesign.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

DEVELOPMENT Stages 0–7 are accepted. Stage 7 is accepted only as reproducible
parser/applicability/technical/provenance/warning evidence with exact map-back;
it guarantees neither semantic component correctness nor geographic truth.
Machine-only job `1763433` and the owner-authorized 240-case review remain the
immutable failed `STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL` readiness
experiment, not a trust gate. The first independent review's documentation-
only failure and corrected rereview pass are both preserved. The exact next
task is Stage 8 design and explicit authorization only. The old Stages 8–19 and
proposed replacement Stages 8–14 are not started. Production Stage 0 and Stage
1 are accepted; production Stages 2–7 are not started. HOLDOUT is untouched
and sealed.

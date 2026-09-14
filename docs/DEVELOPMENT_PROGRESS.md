# DEVELOPMENT progress

This page is the short current status index. Technical contracts and evidence
are in the linked stage records and sanitized reports.

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
| 10–14 proposed | Hypotheses → Pelias top-N → scoring → granularity/abstain | **PROPOSED — NOT STARTED** | Remaining compact replacement architecture; [pipeline specification](PIPELINE.md) | **NOT STARTED** |

Benchmark V1 contains 35,000 DEVELOPMENT and 15,000 sealed HOLDOUT rows from
the permanent 1,405-file population. The fixed 500-row qualitative subset has
fingerprint
`014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52`.

DEVELOPMENT Stages 0–9 are accepted. Stage 7 is accepted only as reproducible
parser/applicability/technical/provenance/warning evidence with exact map-back;
it guarantees neither semantic component correctness nor geographic truth.
Machine-only job `1763433` and the owner-authorized 240-case review remain the
immutable failed `STAGE07_V2_FRESH_DEVELOPMENT_VALIDATION_FAIL` readiness
experiment, not a trust gate. The first independent review's documentation-
only failure and corrected rereview pass are both preserved. Stage 8 job
`1763747` completed the one authorized DEVELOPMENT materialization at exact
executable `a2544401b4b699f6c020970f3507a2ae432746c5`; its immutable manifest is
`bdf86738…` and logical dataset is `9c9d431c…`. Exact counts, reversibility,
frozen validators, privacy, publication, and permissions passed for that old
executable. Independent review nevertheless rejected reporting candidate
`adde81d…` because a synthetic prepublication failure could leave a success
marker and because current Stage 8/Stage 9 tool wording was stale. The repair
at executable `bd89a03…` completed job `1763984` with manifest `d521240b…` and
the same frozen logical dataset `9c9d431c…`; exact scientific reconciliation
passed. Independent rereview nevertheless failed reporting candidate
`fdf2f8c…`: a real rename followed by an exception could leave reader-visible
success while the invocation reported failure. Second repair executable
`bdea7232…` reconciles both paths using the captured attempt identity and
adopts only after parent fsync plus complete final reopen validation.
Authorized job `1764219` produced manifest `346ea27a…` and the same frozen
logical dataset `9c9d431c…`; all scientific and ordinary publication checks
pass. Independent rereview nevertheless failed candidate `70e3de95…` because
stdout failure after committed success produced a failure exit and FINAL
ownership was not re-established after parent fsync/final validation. Third
repair executable `c04cb972…` fixes only those terminal defects. Jobs
`1763747`, `1763984`, and `1764219` remain historical evidence, are not called
corrupt, and cannot validate it. Authorized job `1764273` produced manifest
`2a50bd8c…`, the unchanged logical dataset `9c9d431c…`, and exact scientific
and v3 publication-terminal reconciliation. Corrected independent rereview
commit `f8a456f5c939c4061d2be232fd5037010b7a88c8`, harness SHA-256
`4e728ca7…`, evidence SHA-256 `9fe94207…`, and job `1764376` then passed exact
candidate `231cdbf9…` with zero candidate defects and zero infrastructure-
incomplete checks. Review-only RH-001 remains preserved and is not a candidate
defect. Stage 8 is `STAGE_8_ACCEPTED`; its scientific contract remained
unchanged through every publication remediation.
The old Stages 8–19 were never started. Stage 9 is `STAGE_9_ACCEPTED` under
D060, tagged `stage09-offline-reference-evidence-v1`. Independent review passed
100 artifact checks, 836 candidate tests and 23 additional public/synthetic
checks, with zero candidate defects and no required scientific change or rerun.
Stage 9 remains reference evidence only. Its high Q04 conditional conflict rate
is not an invalid-address rate; all country assessments remain unresolved under
the frozen witness rule. Replacement Stages 10–14 remain proposed and not
started. Production Stage 0 and Stage 1 are accepted; production Stage 2 and
later are not started. HOLDOUT is untouched and sealed; production/Pelias
untouched. The pre-Stage-9 baseline and all historical failures remain frozen.
No job or Stage 10 design/implementation is authorized by this acceptance.

# Stage records

Stage contracts, designs and implementation records. DEVELOPMENT acceptance
requires independent review and explicit owner acceptance. Current execution
status is summarized in [progress](../DEVELOPMENT_PROGRESS.md).

| Stage | Record | DEVELOPMENT | Production |
|---:|---|---|---|
| 0 | [Source inventory](STAGE00_SOURCE_INVENTORY.md) | ACCEPTED | ACCEPTED (1,411 files) |
| 1 | [Lossless ingestion](STAGE01_LOSSLESS_INGESTION.md) | ACCEPTED | ACCEPTED (141,048,582 rows) |
| 2 | [Schema/provenance harmonization](STAGE02_SCHEMA_PROVENANCE.md) | ACCEPTED | NOT STARTED |
| 3 | [Safe text cleaning](STAGE03_SAFE_TEXT_CLEANING.md) | ACCEPTED | NOT STARTED |
| 4 | [Lowercase canonical forms](STAGE04_LOWERCASE_CANONICAL.md) | `STAGE_4_ACCEPTED` | NOT STARTED |
| 5 | [Address reconstruction](STAGE05_ADDRESS_RECONSTRUCTION.md) | `STAGE_5_ACCEPTED` | NOT STARTED |
| 6 | [Early exact deduplication](STAGE06_EARLY_EXACT_DEDUPLICATION.md) | `STAGE_6_ACCEPTED` | NOT STARTED |
| 7 | [libpostal parsing/evidence](STAGE07_LIBPOSTAL_PARSING.md) | `STAGE_7_ACCEPTED` | NOT STARTED |
| 8 | [Lossless address-evidence projection](STAGE08_ADDRESS_EVIDENCE_PROJECTION.md) | `STAGE_8_ACCEPTED`; candidate `231cdbf9…`, executable `c04cb972…`, job `1764273`, independent job `1764376` | NOT STARTED |
| 9 | [Conservative offline geographic reference evidence](STAGE09_OFFLINE_REFERENCE_EVIDENCE.md) | `STAGE_9_ACCEPTED`; executable `3e10ac7c…`, job `1771191`, independent job `1772139`; [owner acceptance](../../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14) | NOT STARTED |
| 10 | [Bounded multi-hypothesis query generation](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md) | **STAGE_10_ACCEPTED**; job `1785683`, independent rereview `1786959`, zero candidate defects; [owner acceptance](../../reports/development/stage10.md) | NOT STARTED |

## Reading frozen records

Design-time status and stop instructions describe the authorization at that
checkpoint. Stage 9's scientific design/reference freeze and Stage 10's five
normative design documents are preserved byte-for-byte; later implementation
and acceptance do not rewrite them. Use the separate
[Stage 9 implementation](STAGE09_IMPLEMENTATION.md),
[Stage 9 acceptance](../../reports/development/stage09.md#owner-acceptance-and-freeze--2026-09-14)
and [Stage 10 implementation](STAGE10_IMPLEMENTATION.md) and
[owner acceptance](../../reports/development/stage10.md) records for subsequent
authority and execution evidence.

Stage 0–8 records also retain historical later-stage stop statements. Their
accepted science and failed attempts remain unchanged. The
[reports index](../../reports/README.md) links exact execution/review identities;
[DECISIONS.md](../DECISIONS.md) preserves the decision sequence. Proposed Stages
11–14 and the superseded, unstarted Stage 8–19 plan are in
[PIPELINE.md](../PIPELINE.md).

# Stage records

These documents describe implemented library-first stages. They summarize
contracts and sanitized evidence without reproducing audit transcripts or
protected rows. A DEVELOPMENT candidate is not accepted until a fresh
independent review records acceptance.

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
| 8 | [Lossless address-evidence projection](STAGE08_ADDRESS_EVIDENCE_PROJECTION.md) | `STAGE08_ADDRESS_EVIDENCE_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW`; repaired job `1763984` materialized, not accepted | NOT STARTED |

Replacement Stages 9–14 remain proposed in
[the pipeline specification](../PIPELINE.md). Repaired Stage 8 job `1763984`
is frozen in the sanitized
[execution report](../../reports/development/stage08_address_evidence_development.md)
and [candidate report](../../reports/development/stage08_address_evidence_development_candidate_report.md).
They also retain job `1763747` and its rejected old executable as immutable
historical evidence. The [remediation report](../../reports/development/stage08_address_evidence_remediation.md)
records the publication fix. No second job is authorized; the next action is a
fresh independent rereview of the repaired candidate.

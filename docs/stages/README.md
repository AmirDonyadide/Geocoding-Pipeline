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
| 8 | [Lossless address-evidence projection](STAGE08_ADDRESS_EVIDENCE_PROJECTION.md) | `STAGE_8_ACCEPTED`; candidate `231cdbf9…`, executable `c04cb972…`, job `1764273`, independent job `1764376` | NOT STARTED |

Replacement Stages 9–14 remain proposed in
[the pipeline specification](../PIPELINE.md). Stage 8 jobs `1763747` and
`1763984` are frozen as historical evidence for their exact executables in the
sanitized
[execution report](../../reports/development/stage08_address_evidence_development.md)
and [candidate report](../../reports/development/stage08_address_evidence_development_candidate_report.md).
They also retain job `1763747` and its rejected old executable as immutable
historical evidence. The [remediation report](../../reports/development/stage08_address_evidence_remediation.md)
records the first publication fix. The
[second remediation report](../../reports/development/stage08_address_evidence_publication_remediation_v2.md)
records the second failed rereview and post-effect rename repair. Job `1764219`
and its [candidate report](../../reports/development/stage08_address_evidence_publication_remediation_v2_candidate_report.md)
remain historical after the third failed rereview. The
[third remediation report](../../reports/development/stage08_address_evidence_publication_remediation_v3.md)
records the post-commit CLI-status and final-ownership repair. Exact candidate
`231cdbf9…` passed corrected independent rereview job `1764376`; the
[sanitized rereview](../../reports/development/stage08_address_evidence_independent_rereview.md)
records zero candidate defects and preserves review-only RH-001 separately.
The next task is the full Stages 0–8 pipeline audit before Stage 9.

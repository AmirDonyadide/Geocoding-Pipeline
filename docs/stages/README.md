# Stage records

These documents describe accepted library-first stages and proposed designs.
They summarize
contracts and sanitized evidence without reproducing audit transcripts or
protected rows. A DEVELOPMENT candidate is not accepted until a fresh
independent review passes and the owner explicitly accepts it.

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
| 10 | [Bounded multi-hypothesis query generation](STAGE10_MULTI_HYPOTHESIS_QUERY_GENERATION.md) | DESIGN READY FOR OWNER REVIEW; not approved, implemented or executed | NOT STARTED |

Stage 9 is accepted with its design/reference bytes unchanged; historical
design-time status wording remains frozen, not a current status gate.
Stage 10 has a separately authorized documentation-only design candidate;
replacement Stages 11–14 remain proposed and not started in
[the pipeline specification](../PIPELINE.md). The authoritative
[Stage 8 report](../../reports/development/stage08.md) consolidates jobs
`1763747`, `1763984`, `1764219`, and accepted job `1764273`; all publication
remediations; corrected independent rereview job `1764376`; and review-only
RH-001 without relabeling any historical failure. Its
[machine summary](../../reports/generated/stage08.json) provides the exact
structured evidence. The required audit is complete and the pre-Stage-9
baseline is frozen. The separately authorized Stage 9 owner-revision session
completed the design and bounded public-reference freeze linked above.
The owner subsequently authorized implementation, synthetic/local tests and one
controlled DEVELOPMENT SLURM execution. Implementation and local validation are
complete; historical job `1770156` failed in the synthetic filesystem preflight
before protected input access. The approved PanFS repair then completed job
`1771191`; independent review job `1772139` passed with zero candidate defects,
and D060 records owner acceptance without scientific change or rerun. The linked
execution record preserves all failure/diagnostic history and the accepted
identity. Stage 10 stops for owner design review; implementation/execution are
not started. Stages 11–14 remain proposed and not started.

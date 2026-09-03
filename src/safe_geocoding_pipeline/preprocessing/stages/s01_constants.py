from __future__ import annotations

from ...raw_csv import SOURCE_COLUMNS

STAGING_VERSION = "phase02_v1"
SOURCE_SCHEMA_VERSION = "source_csv_15col_v1"
PARSER_VERSION = "phase01_csv_parser_v1"
SEMANTIC_DIGEST_VERSION = "raw_semantic_digest_v1"
STABLE_ROW_ID_VERSION = "stable_source_row_id_v1"

PROVENANCE_COLUMNS = (
    "source_file",
    "source_logical_record_number",
    "stable_source_row_id_v1",
    "source_file_sha256",
    "source_schema_version",
    "parser_version",
    "staging_version",
)

STAGING_COLUMNS = SOURCE_COLUMNS + PROVENANCE_COLUMNS

DICTIONARY_COLUMNS = (
    "country_iso_code",
    "batch_priority",
    "location_information",
    "source_file",
    "source_schema_version",
    "parser_version",
    "staging_version",
)

STATISTICS_COLUMNS = (
    "source_logical_record_number",
    "country_iso_code",
    "batch_priority",
    "location_information",
)

REPORT_NAMES = (
    "phase02_run.json",
    "phase02_file_validation.csv",
    "phase02_schema.json",
    "phase02_reconciliation.json",
    "phase02_failures.csv.gz",
    "phase02_summary.md",
)

# Frozen column order of the accepted Stage 1 validation artifact. The artifact
# filenames and serialized phase-prefixed keys below are immutable provenance
# compatibility identifiers; they do not expose a runnable Phase pipeline.
FILE_VALIDATION_COLUMNS = (
    "run_id",
    "relative_path",
    "status",
    "failure_code",
    "failure_detail",
    "source_size_bytes",
    "source_sha256",
    "source_rows",
    "staging_rows",
    "source_semantic_digest",
    "staging_semantic_digest",
    "semantic_digest_match",
    "output_path",
    "output_size_bytes",
    "output_sha256",
    "compression_ratio",
    "row_group_count",
    "row_group_rows_json",
    "isolated_record_count",
    "source_empty_counts_json",
    "staging_empty_counts_json",
    "source_non_ascii_counts_json",
    "staging_non_ascii_counts_json",
    "raw_null_count",
    "provenance_valid",
    "stable_ids_valid",
    "stable_ids_distinct",
    "known_extremes_valid",
    "extreme_observations_json",
    "page_checksums_verified",
    "conversion_seconds",
    "validation_seconds",
    "hashing_seconds",
    "promotion_seconds",
    "peak_temporary_bytes",
    "peak_rss_bytes",
)

FILE_STATUSES = ("PENDING", "WRITING", "VALIDATING", "COMPLETE", "FAILED")

AUTHORIZED_SMOKE_FILES = (
    "remaining_addresses_00103.csv",
    "remaining_addresses_00205.csv",
)

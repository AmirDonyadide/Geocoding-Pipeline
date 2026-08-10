from __future__ import annotations

from ..raw_csv import SOURCE_COLUMNS

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

FILE_STATUSES = ("PENDING", "WRITING", "VALIDATING", "COMPLETE", "FAILED")

AUTHORIZED_SMOKE_FILES = (
    "remaining_addresses_00103.csv",
    "remaining_addresses_00205.csv",
)

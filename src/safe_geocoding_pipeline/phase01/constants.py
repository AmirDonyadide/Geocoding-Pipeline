from __future__ import annotations

from ..raw_csv import SOURCE_COLUMNS

INVENTORY_VERSION = "phase01_v1"

EXPECTED_COLUMNS = SOURCE_COLUMNS

NATIVE_PAIRS = (
    ("street_address_line_1", "street_address_line_1_native"),
    ("street_address_line_2", "street_address_line_2_native"),
    ("street_address_line_3", "street_address_line_3_native"),
    ("street_address_line_4", "street_address_line_4_native"),
)

RAW_CATEGORICAL_FIELDS = (
    "country_iso_code",
    "batch_priority",
    "location_information",
)

DEFAULT_PLACEHOLDER_CANDIDATES = (".", "-", "Na", "Nan", "Null")

REPORT_NAMES = (
    "phase01_run.json",
    "phase01_file_manifest.csv",
    "phase01_schema_report.csv",
    "phase01_field_profile.csv",
    "phase01_value_profile.csv",
    "phase01_anomalies.csv.gz",
    "phase01_duplicate_ids.csv.gz",
    "phase01_summary.md",
)

ANOMALY_COLUMNS = (
    "run_id",
    "anomaly_id",
    "severity",
    "domain",
    "anomaly_type",
    "file_id",
    "relative_path",
    "logical_record_number",
    "physical_line_start",
    "physical_line_end",
    "column_name",
    "expected",
    "observed",
    "field_length_chars",
    "record_length_chars",
    "value_sha256",
    "message_code",
    "counts_complete",
)

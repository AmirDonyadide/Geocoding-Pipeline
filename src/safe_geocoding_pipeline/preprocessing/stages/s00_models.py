from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceFile:
    file_id: int
    path: Path
    relative_path: str
    file_name: str


@dataclass(slots=True)
class FileMetadata:
    size_bytes: int | None = None
    mtime_ns: int | None = None
    mtime_utc: str = ""


@dataclass(slots=True)
class SchemaRow:
    column_position: int
    observed_column_name: str
    expected_column_name: str
    name_matches_expected: bool
    position_matches_expected: bool
    schema_fingerprint: str


@dataclass(slots=True)
class FieldProfile:
    column_position: int
    column_name: str
    records_eligible_for_profile: int = 0
    nonempty_count: int = 0
    empty_count: int = 0
    whitespace_only_count: int = 0
    max_length_chars: int = 0
    max_length_logical_record_number: int | None = None
    contains_newline_count: int = 0
    oversized_field_count: int = 0
    exact_placeholder_candidate_count: int = 0
    profile_complete: bool = True


@dataclass(slots=True)
class ValueProfileRow:
    field_name: str
    profile_family: str
    category: str
    count: int
    denominator: int


@dataclass(slots=True)
class FileResult:
    file_id: int
    relative_path: str
    file_name: str
    before: FileMetadata = field(default_factory=FileMetadata)
    after_parse: FileMetadata = field(default_factory=FileMetadata)
    after_hash: FileMetadata = field(default_factory=FileMetadata)
    file_changed_during_scan: bool = False
    sha256: str = ""
    duplicate_file_group: str = ""
    duplicate_file_group_size: int = 0
    duplicate_verification_method: str = ""
    bom_type: str = "NONE"
    encoding_status: str = "UNKNOWN"
    delimiter: str = ","
    quote_character: str = '"'
    doublequote: bool = True
    escape_character: str = ""
    header_present: bool = False
    observed_column_count: int = 0
    schema_fingerprint: str = ""
    schema_matches_expected: bool = False
    logical_record_count: int = 0
    valid_schema_record_count: int = 0
    empty_record_count: int = 0
    all_fields_empty_record_count: int = 0
    wrong_column_count_record_count: int = 0
    parser_error_count: int = 0
    multiline_record_count: int = 0
    max_physical_lines_per_record: int = 0
    max_record_length_chars: int = 0
    max_field_length_chars: int = 0
    id_nonempty_count: int = 0
    id_empty_count: int = 0
    id_distinct_within_file: int = 0
    id_duplicate_group_count_within_file: int = 0
    id_duplicate_occurrence_count_within_file: int = 0
    id_lexical_min_sha256: str = ""
    id_lexical_min_length: int | None = None
    id_lexical_max_sha256: str = ""
    id_lexical_max_length: int | None = None
    counts_complete: bool = False
    scan_status: str = "PENDING"
    error_code: str = ""
    duration_ms: int = 0
    parse_duration_seconds: float = 0.0
    hash_duration_seconds: float = 0.0
    schema_rows: list[SchemaRow] = field(default_factory=list)
    field_profiles: list[FieldProfile] = field(default_factory=list)
    value_profiles: list[ValueProfileRow] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FileResult":
        payload = dict(value)
        for key in ("before", "after_parse", "after_hash"):
            payload[key] = FileMetadata(**payload[key])
        payload["schema_rows"] = [SchemaRow(**row) for row in payload["schema_rows"]]
        payload["field_profiles"] = [
            FieldProfile(**row) for row in payload["field_profiles"]
        ]
        payload["value_profiles"] = [
            ValueProfileRow(**row) for row in payload["value_profiles"]
        ]
        return cls(**payload)


@dataclass(frozen=True, slots=True)
class IdObservation:
    id_value: str
    file_id: int
    logical_record_number: int

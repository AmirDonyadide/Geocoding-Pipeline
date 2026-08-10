from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class Phase01FileEntry:
    file_id: int
    relative_path: str
    file_name: str
    size_bytes: int
    mtime_utc: str
    sha256: str
    logical_record_count: int
    schema_fingerprint: str
    bom_type: str


@dataclass(frozen=True, slots=True)
class KnownExtreme:
    relative_path: str
    logical_record_number: int
    column_name: str
    field_length_chars: int
    value_sha256: str
    physical_line_start: int | None = None
    physical_line_end: int | None = None


@dataclass(frozen=True, slots=True)
class Phase01Manifest:
    run_id: str
    input_manifest_sha256: str
    files: dict[str, Phase01FileEntry]
    extremes: dict[str, tuple[KnownExtreme, ...]]


@dataclass(slots=True)
class FileValidationResult:
    relative_path: str
    status: str = "FAILED"
    failure_code: str = ""
    failure_detail: str = ""
    source_size_bytes: int = 0
    source_sha256: str = ""
    source_rows: int = 0
    staging_rows: int = 0
    source_semantic_digest: str = ""
    staging_semantic_digest: str = ""
    semantic_digest_match: bool = False
    output_path: str = ""
    output_size_bytes: int = 0
    output_sha256: str = ""
    compression_ratio: float = 0.0
    row_group_count: int = 0
    row_group_rows: list[int] = field(default_factory=list)
    isolated_record_count: int = 0
    source_empty_counts: dict[str, int] = field(default_factory=dict)
    staging_empty_counts: dict[str, int] = field(default_factory=dict)
    source_non_ascii_counts: dict[str, int] = field(default_factory=dict)
    staging_non_ascii_counts: dict[str, int] = field(default_factory=dict)
    raw_null_count: int = 0
    provenance_valid: bool = False
    stable_ids_valid: bool = False
    stable_ids_distinct: int = 0
    known_extremes_valid: bool = False
    extreme_observations: list[dict[str, Any]] = field(default_factory=list)
    page_checksums_verified: bool = False
    conversion_seconds: float = 0.0
    validation_seconds: float = 0.0
    hashing_seconds: float = 0.0
    promotion_seconds: float = 0.0
    peak_temporary_bytes: int = 0
    peak_rss_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    status: str
    file_count: int
    total_rows: int
    distinct_ids: int
    distinct_stable_ids: int
    null_ids: int
    duplicate_stable_ids: int
    raw_null_count: int
    schema_count: int
    missing_files: tuple[str, ...]
    extra_files: tuple[str, ...]
    duckdb_seconds: float
    duckdb_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Phase02Outcome:
    run_id: str
    staging_run_dir: Path
    report_run_dir: Path
    status: str
    scope_gate: str
    phase02_completion_gate: str
    files: tuple[FileValidationResult, ...]
    reconciliation: ReconciliationResult
    metrics: dict[str, float | int]

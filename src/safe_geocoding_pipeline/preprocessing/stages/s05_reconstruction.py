from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import sqlite3
import stat
import struct
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable, Mapping, NoReturn, Protocol, Sequence, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s02_harmonization import NATIVE_ADDRESS_COLUMNS, STANDARD_ADDRESS_COLUMNS
from .s03_cleaning import EXPECTED_PYARROW_VERSION, EXPECTED_PYTHON_VERSION
from .s04_lowercase import (
    LOWER_OUTPUT_COLUMNS,
    STAGE04_CONTRACT_VERSION,
    STAGE04_MANIFEST_NAME,
    STAGE04_PROFILE_VERSION,
    Stage04ValidationError,
    stage04_schema,
    validate_stage04_bundle,
)

STAGE05_CONTRACT_VERSION = "stage05_address_reconstruction_contract_v1"
STAGE05_PROFILE_VERSION = "stage05_address_reconstruction_profile_v1"
STAGE05_INPUT_BINDING_VERSION = "stage05_input_binding_v1"
STAGE05_SCHEMA_VERSION = "stage05_address_reconstruction_schema_v1"
STAGE05_VALIDATION_VERSION = "stage05_bundle_validation_v1"
STAGE05_MANIFEST_VERSION = "stage05_manifest_v1"
STAGE05_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE05_LOGICAL_DATASET_V1"
STAGE05_SCHEMA_FINGERPRINT_DOMAIN = b"SAFE_STAGE05_ARROW_SCHEMA_V1"
STAGE05_ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
STAGE05_ORDERED_IDENTITY_VERSION = "stage03_ordered_stable_identity_sha256_v1"
STAGE05_SEPARATOR = ", "
STAGE05_LINE_ORDER = "SOURCE_LINE_1_TO_4_RELATIVE_ORDER"
STAGE05_EMPTY_LINE_RULE = "EXACT_EMPTY_STRING_FILTER"
STAGE05_GAP_RULE = "SKIP_EMPTY_WITHOUT_ARTIFICIAL_SEPARATOR"
STAGE05_DUPLICATE_LINE_RULE = "PRESERVE_EXACT_DUPLICATE_LINES"
STAGE05_GEOGRAPHIC_FIELD_RULE = "EXCLUDED_FROM_RECONSTRUCTION"
DEFAULT_TARGET_BATCH_BYTES = 256 * 1024 * 1024

STAGE05_MANIFEST_NAME = "stage05_manifest.json"
STAGE05_SUCCESS_MARKER = "_SUCCESS.json"
STAGE05_IN_PROGRESS_MARKER = "_IN_PROGRESS"

ACCEPTED_STAGE04_SCHEMA_FINGERPRINT = (
    "dafb4f78b8bfce3120b6f4f7ae8cb44883f4c3a9cfd94b3137871b83c0ed5cbc"
)
ACCEPTED_STAGE04_LOGICAL_FINGERPRINT = (
    "054c66701f854a0108938170e1cb9bcee8a772f7fed29b82cda53c71aa9747ec"
)
ACCEPTED_STAGE04_INPUT_BINDING_SHA256 = (
    "90e0e94d4359bd5927820dfc06b2cfc1dc37485c032d95726d1260ec88a534b0"
)
ACCEPTED_STAGE04_MANIFEST_SHA256 = (
    "17a4854cddd8929b65ea79402f1a4f12a1574b720c1921567b577f23e152d1f3"
)
ACCEPTED_STAGE04_ORDERED_IDENTITY_SHA256 = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_DEVELOPMENT_ROWS = 35_000

CASE_PRESERVED_OUTPUT_COLUMNS = (
    "stage05_standard_candidate_clean",
    "stage05_native_candidate_clean",
)
CANONICAL_OUTPUT_COLUMNS = (
    "stage05_standard_candidate_lower",
    "stage05_native_candidate_lower",
)
STAGE05_AUDIT_COLUMNS = (
    "stage05_standard_candidate_available",
    "stage05_native_candidate_available",
    "stage05_standard_contributing_line_count",
    "stage05_native_contributing_line_count",
    "stage05_standard_contributing_line_mask",
    "stage05_native_contributing_line_mask",
)
STAGE05_DERIVED_COLUMNS = (
    *CASE_PRESERVED_OUTPUT_COLUMNS,
    *CANONICAL_OUTPUT_COLUMNS,
    *STAGE05_AUDIT_COLUMNS,
)

_CLEAN_STANDARD_COLUMNS = tuple(
    f"stage03_clean_{name}" for name in STANDARD_ADDRESS_COLUMNS
)
_CLEAN_NATIVE_COLUMNS = tuple(
    f"stage03_clean_{name}" for name in NATIVE_ADDRESS_COLUMNS
)
_LOWER_STANDARD_COLUMNS = LOWER_OUTPUT_COLUMNS[:4]
_LOWER_NATIVE_COLUMNS = LOWER_OUTPUT_COLUMNS[4:8]
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"
_ALL_MASKS = tuple(f"{value:04b}" for value in range(16))
_LEFT_PACKED_MASKS = frozenset({"0000", "1000", "1100", "1110", "1111"})
_LENGTH_THRESHOLDS = (1_024, 65_536, 1_000_000)


class Stage05ValidationError(RuntimeError):
    """Privacy-safe, fail-closed Stage 5 validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage05InputBinding:
    upstream_contract_version: str
    upstream_profile_version: str
    upstream_logical_fingerprint: str
    upstream_schema_fingerprint: str
    upstream_input_binding_sha256: str
    upstream_manifest_sha256: str
    upstream_ordered_identity_sha256: str
    input_benchmark_fingerprint: str
    expected_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "stage05_input_binding_version": STAGE05_INPUT_BINDING_VERSION,
            "upstream_contract_version": self.upstream_contract_version,
            "upstream_profile_version": self.upstream_profile_version,
            "upstream_logical_fingerprint": self.upstream_logical_fingerprint,
            "upstream_schema_fingerprint": self.upstream_schema_fingerprint,
            "upstream_input_binding_sha256": self.upstream_input_binding_sha256,
            "upstream_manifest_sha256": self.upstream_manifest_sha256,
            "upstream_ordered_identity_sha256": self.upstream_ordered_identity_sha256,
            "input_benchmark_fingerprint": self.input_benchmark_fingerprint,
            "expected_row_count": self.expected_row_count,
        }


@dataclass(frozen=True, slots=True)
class Stage05RunConfig:
    stage04_output_directory: Path
    input_binding_file: Path
    expected_input_binding_sha256: str
    output_directory: Path
    execution_git_sha: str
    production: bool = True
    authoritative_development: bool = True
    batch_rows: int = 2_048
    target_batch_bytes: int = DEFAULT_TARGET_BATCH_BYTES
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        _digest_bytes(self.expected_input_binding_sha256)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git commit must be a full SHA")
        if isinstance(self.batch_rows, bool) or self.batch_rows < 1:
            _fail("INVALID_BATCH_SIZE", "Batch row count must be positive")
        if isinstance(self.target_batch_bytes, bool) or self.target_batch_bytes < 1:
            _fail("INVALID_BATCH_SIZE", "Target batch bytes must be positive")
        _reject_holdout_paths(
            self.stage04_output_directory,
            self.input_binding_file,
            self.output_directory,
        )
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(value, str)
                or not value
                or "\x00" in value
                or len(value) > 128
            ):
                _fail(
                    "INVALID_OPERATIONAL_METADATA",
                    "Operational metadata is outside the privacy-safe contract",
                )


@dataclass(frozen=True, slots=True)
class Stage05ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage05MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    schema_fingerprint: str
    input_binding_sha256: str
    manifest_sha256: str
    ordered_identity_sha256: str
    row_count: int
    output_shard_count: int
    metrics: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True, slots=True)
class ReconstructedCandidate:
    candidate: str
    available: bool
    contributing_line_count: int
    contributing_line_mask: str


@dataclass(slots=True)
class _RepresentationMetrics:
    available: int = 0
    unavailable: int = 0
    line_counts: Counter[str] = field(
        default_factory=lambda: Counter({str(value): 0 for value in range(5)})
    )
    masks: Counter[str] = field(
        default_factory=lambda: Counter({mask: 0 for mask in _ALL_MASKS})
    )
    gap_rows: int = 0
    duplicate_line_rows_clean: int = 0
    duplicate_line_rows_lower: int = 0
    duplicate_line_excess_clean: int = 0
    duplicate_line_excess_lower: int = 0
    internal_boundaries: int = 0
    predecessor_end: Counter[str] = field(
        default_factory=lambda: Counter(
            {
                "COMMA": 0,
                "SEMICOLON": 0,
                "SLASH": 0,
                "HYPHEN_OR_DASH": 0,
                "OTHER_PUNCTUATION": 0,
                "NO_PUNCTUATION": 0,
            }
        )
    )
    successor_starts_punctuation: int = 0
    separator_overhead: int = 0
    large: Counter[str] = field(
        default_factory=lambda: Counter(
            {f"AT_LEAST_{value}_CODEPOINTS": 0 for value in _LENGTH_THRESHOLDS}
        )
    )


@dataclass(slots=True)
class Stage05Metrics:
    input_rows: int = 0
    output_rows: int = 0
    standard: _RepresentationMetrics = field(default_factory=_RepresentationMetrics)
    native: _RepresentationMetrics = field(default_factory=_RepresentationMetrics)
    relationship: Counter[str] = field(
        default_factory=lambda: Counter(
            {
                "NO_REPRESENTATION": 0,
                "STANDARD_ONLY": 0,
                "NATIVE_ONLY": 0,
                "BOTH": 0,
            }
        )
    )
    both_candidate: Counter[str] = field(
        default_factory=lambda: Counter({"EXACT_EQUAL_CANONICAL": 0, "DIFFERENT": 0})
    )
    both_line_count: Counter[str] = field(
        default_factory=lambda: Counter(
            {"SAME_LINE_COUNT": 0, "DIFFERENT_LINE_COUNT": 0}
        )
    )
    reconstruction_mismatches: int = 0
    audit_mismatches: int = 0
    clean_lower_consistency_mismatches: int = 0
    idempotence_failures: int = 0

    def to_metric_groups(
        self,
        *,
        standard_lengths: Mapping[str, int],
        native_lengths: Mapping[str, int],
    ) -> dict[str, dict[str, int]]:
        return {
            "ROW_INTEGRITY": {
                "INPUT_ROWS": self.input_rows,
                "OUTPUT_ROWS": self.output_rows,
                "DROPPED_ROWS": 0,
                "ADDED_ROWS": 0,
                "DUPLICATE_IDENTITIES": 0,
            },
            "REPRESENTATION_AVAILABILITY": {
                "NO_REPRESENTATION": self.relationship["NO_REPRESENTATION"],
                "STANDARD_ONLY": self.relationship["STANDARD_ONLY"],
                "NATIVE_ONLY": self.relationship["NATIVE_ONLY"],
                "BOTH": self.relationship["BOTH"],
                "STANDARD_AVAILABLE": self.standard.available,
                "STANDARD_UNAVAILABLE": self.standard.unavailable,
                "NATIVE_AVAILABLE": self.native.available,
                "NATIVE_UNAVAILABLE": self.native.unavailable,
            },
            "BOTH_CANDIDATE_RELATIONSHIP": dict(self.both_candidate),
            "BOTH_LINE_COUNT_RELATIONSHIP": dict(self.both_line_count),
            "STANDARD_LINE_COUNT": dict(self.standard.line_counts),
            "NATIVE_LINE_COUNT": dict(self.native.line_counts),
            "STANDARD_OCCUPANCY_MASK": dict(self.standard.masks),
            "NATIVE_OCCUPANCY_MASK": dict(self.native.masks),
            "GAP_FINDINGS": {
                "STANDARD_GAP_ROWS": self.standard.gap_rows,
                "NATIVE_GAP_ROWS": self.native.gap_rows,
            },
            "DUPLICATE_LINE_FINDINGS": {
                "STANDARD_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": (
                    self.standard.duplicate_line_rows_clean
                ),
                "NATIVE_ROWS_WITH_EXACT_DUPLICATE_CLEAN_LINES": (
                    self.native.duplicate_line_rows_clean
                ),
                "STANDARD_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES": (
                    self.standard.duplicate_line_rows_lower
                ),
                "NATIVE_ROWS_WITH_EXACT_DUPLICATE_LOWER_LINES": (
                    self.native.duplicate_line_rows_lower
                ),
                "STANDARD_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": (
                    self.standard.duplicate_line_excess_clean
                ),
                "NATIVE_EXCESS_EXACT_DUPLICATE_CLEAN_VALUES": (
                    self.native.duplicate_line_excess_clean
                ),
                "STANDARD_EXCESS_EXACT_DUPLICATE_LOWER_VALUES": (
                    self.standard.duplicate_line_excess_lower
                ),
                "NATIVE_EXCESS_EXACT_DUPLICATE_LOWER_VALUES": (
                    self.native.duplicate_line_excess_lower
                ),
            },
            "SEPARATOR_BOUNDARIES": {
                "STANDARD_INTERNAL_BOUNDARIES": self.standard.internal_boundaries,
                "NATIVE_INTERNAL_BOUNDARIES": self.native.internal_boundaries,
                "STANDARD_PREDECESSOR_ENDS_COMMA": self.standard.predecessor_end[
                    "COMMA"
                ],
                "NATIVE_PREDECESSOR_ENDS_COMMA": self.native.predecessor_end["COMMA"],
                "STANDARD_SUCCESSOR_STARTS_PUNCTUATION": (
                    self.standard.successor_starts_punctuation
                ),
                "NATIVE_SUCCESSOR_STARTS_PUNCTUATION": (
                    self.native.successor_starts_punctuation
                ),
                "STANDARD_SEPARATOR_OVERHEAD_CODEPOINTS": (
                    self.standard.separator_overhead
                ),
                "NATIVE_SEPARATOR_OVERHEAD_CODEPOINTS": (
                    self.native.separator_overhead
                ),
            },
            "STANDARD_CANDIDATE_LENGTH_CODEPOINTS": dict(standard_lengths),
            "NATIVE_CANDIDATE_LENGTH_CODEPOINTS": dict(native_lengths),
            "VERY_LARGE_CANDIDATES": {
                **{
                    f"STANDARD_{name}": count
                    for name, count in self.standard.large.items()
                },
                **{
                    f"NATIVE_{name}": count for name, count in self.native.large.items()
                },
            },
            "RECONSTRUCTION_VALIDATION": {
                "RECONSTRUCTION_MISMATCHES": self.reconstruction_mismatches,
                "AUDIT_MISMATCHES": self.audit_mismatches,
                "CLEAN_LOWER_CONSISTENCY_MISMATCHES": (
                    self.clean_lower_consistency_mismatches
                ),
                "IDEMPOTENCE_FAILURES": self.idempotence_failures,
            },
        }


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...


class _CanonicalEncoder:
    def __init__(self, digest: _Digest) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
            _fail("INVALID_UNSIGNED_INTEGER", "Canonical integer is outside uint64")
        self._digest.update(_TYPE_UINT64 + struct.pack(">Q", value))

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            _fail("INVALID_CANONICAL_TEXT", "Canonical text is malformed")
        encoded = value.encode("utf-8", errors="strict")
        self._digest.update(_TYPE_TEXT + struct.pack(">Q", len(encoded)) + encoded)

    def digest(self, value: str) -> None:
        self._digest.update(_TYPE_DIGEST + _digest_bytes(value))


class _OrderedStableIdentityHasher:
    def __init__(self) -> None:
        self._digest = hashlib.sha256(STAGE05_ORDERED_IDENTITY_DOMAIN)
        self.row_count = 0

    def update(self, values: pa.Array) -> None:
        if (
            not pa.types.is_fixed_size_binary(values.type)
            or values.type.byte_width != 32
            or values.null_count
        ):
            _fail("INVALID_STABLE_IDENTITY", "Stable identity array is not exact")
        data = values.buffers()[1]
        if data is None:
            _fail("INVALID_STABLE_IDENTITY", "Stable identity storage is absent")
        self._digest.update(
            data.slice(values.offset * 32, len(values) * 32).to_pybytes()
        )
        self.row_count += len(values)

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return digest.hexdigest()


def _fail(code: str, message: str) -> NoReturn:
    raise Stage05ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be lowercase canonical SHA-256 text")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 5 path names HOLDOUT")


def validate_stage05_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not the pinned version")
    if pa.__version__ != EXPECTED_PYARROW_VERSION:
        _fail("PYARROW_VERSION_MISMATCH", "PyArrow runtime is not the pinned version")


def reconstruct_candidate(lines: Sequence[str]) -> ReconstructedCandidate:
    """Join exact nonempty lines in source order without interpreting content."""
    if len(lines) != 4 or any(not isinstance(value, str) for value in lines):
        _fail("INVALID_RECONSTRUCTION_INPUT", "Exactly four text lines are required")
    try:
        for value in lines:
            value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage05ValidationError(
            "INVALID_RECONSTRUCTION_INPUT", "A line is not valid Unicode text"
        ) from error
    nonempty = [value for value in lines if value != ""]
    candidate = STAGE05_SEPARATOR.join(nonempty)
    return ReconstructedCandidate(
        candidate=candidate,
        available=bool(nonempty),
        contributing_line_count=len(nonempty),
        contributing_line_mask="".join("1" if value != "" else "0" for value in lines),
    )


def stage05_schema() -> pa.Schema:
    fields = list(stage04_schema())
    fields.extend(
        pa.field(name, pa.string(), nullable=False)
        for name in (*CASE_PRESERVED_OUTPUT_COLUMNS, *CANONICAL_OUTPUT_COLUMNS)
    )
    fields.extend(
        (
            pa.field(STAGE05_AUDIT_COLUMNS[0], pa.bool_(), nullable=False),
            pa.field(STAGE05_AUDIT_COLUMNS[1], pa.bool_(), nullable=False),
            pa.field(STAGE05_AUDIT_COLUMNS[2], pa.uint8(), nullable=False),
            pa.field(STAGE05_AUDIT_COLUMNS[3], pa.uint8(), nullable=False),
            pa.field(STAGE05_AUDIT_COLUMNS[4], pa.string(), nullable=False),
            pa.field(STAGE05_AUDIT_COLUMNS[5], pa.string(), nullable=False),
        )
    )
    return pa.schema(fields)


def stage05_schema_fingerprint() -> str:
    digest = hashlib.sha256(STAGE05_SCHEMA_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE05_SCHEMA_VERSION)
    schema = stage05_schema().remove_metadata()
    encoder.uint64(len(schema))
    for schema_field in schema:
        encoder.text(schema_field.name)
        encoder.text(str(schema_field.type))
        encoder.text(str(schema_field.nullable).lower())
    return digest.hexdigest()


def validate_stage05_input_binding(
    binding: Stage05InputBinding, *, authoritative_development: bool = False
) -> None:
    if binding.upstream_contract_version != STAGE04_CONTRACT_VERSION:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "Stage 4 contract version is not exact")
    if binding.upstream_profile_version != STAGE04_PROFILE_VERSION:
        _fail("UPSTREAM_PROFILE_MISMATCH", "Stage 4 profile version is not exact")
    if binding.upstream_schema_fingerprint != ACCEPTED_STAGE04_SCHEMA_FINGERPRINT:
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 4 schema fingerprint is not exact")
    for digest in (
        binding.upstream_logical_fingerprint,
        binding.upstream_schema_fingerprint,
        binding.upstream_input_binding_sha256,
        binding.upstream_manifest_sha256,
        binding.upstream_ordered_identity_sha256,
        binding.input_benchmark_fingerprint,
    ):
        _digest_bytes(digest)
    if (
        isinstance(binding.expected_row_count, bool)
        or binding.expected_row_count < 1
        or binding.expected_row_count > 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail("INVALID_ROW_COUNT", "Stage 5 expected row count is invalid")
    if authoritative_development and (
        binding.upstream_logical_fingerprint != ACCEPTED_STAGE04_LOGICAL_FINGERPRINT
        or binding.upstream_schema_fingerprint != ACCEPTED_STAGE04_SCHEMA_FINGERPRINT
        or binding.upstream_input_binding_sha256
        != ACCEPTED_STAGE04_INPUT_BINDING_SHA256
        or binding.upstream_manifest_sha256 != ACCEPTED_STAGE04_MANIFEST_SHA256
        or binding.upstream_ordered_identity_sha256
        != ACCEPTED_STAGE04_ORDERED_IDENTITY_SHA256
        or binding.input_benchmark_fingerprint != ACCEPTED_BENCHMARK_FINGERPRINT
        or binding.expected_row_count != ACCEPTED_DEVELOPMENT_ROWS
    ):
        _fail(
            "AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH",
            "Stage 5 does not bind the accepted 35k Stage 4 DEVELOPMENT boundary",
        )


def stage05_logical_dataset_sha256_v1(binding: Stage05InputBinding) -> str:
    validate_stage05_input_binding(binding)
    digest = hashlib.sha256(STAGE05_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        STAGE05_CONTRACT_VERSION,
        STAGE05_PROFILE_VERSION,
        STAGE05_SCHEMA_VERSION,
        STAGE05_SEPARATOR,
        STAGE05_LINE_ORDER,
        STAGE05_EMPTY_LINE_RULE,
        STAGE05_GAP_RULE,
        STAGE05_DUPLICATE_LINE_RULE,
        STAGE05_GEOGRAPHIC_FIELD_RULE,
        "STANDARD_NATIVE_SEPARATE",
        "CASE_PRESERVED_AND_LOWER_CANDIDATES",
        "ZERO_LINES_EMPTY_CANDIDATE_UNAVAILABLE",
        binding.upstream_contract_version,
        binding.upstream_profile_version,
    ):
        encoder.text(value)
    for value in (
        *_CLEAN_STANDARD_COLUMNS,
        *_CLEAN_NATIVE_COLUMNS,
        *_LOWER_STANDARD_COLUMNS,
        *_LOWER_NATIVE_COLUMNS,
        *STAGE05_DERIVED_COLUMNS,
    ):
        encoder.text(value)
    for digest_value in (
        binding.upstream_logical_fingerprint,
        binding.upstream_schema_fingerprint,
        binding.upstream_ordered_identity_sha256,
        binding.input_benchmark_fingerprint,
        stage05_schema_fingerprint(),
    ):
        encoder.digest(digest_value)
    encoder.uint64(binding.expected_row_count)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage05ValidationError(
            "CONTROLLED_WRITE_FAILURE",
            "Controlled Stage 5 artifact could not be written",
        ) from error


def _write_json_exclusive(path: Path, value: object) -> None:
    _write_exclusive(
        path,
        (
            json.dumps(
                value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8"),
    )


def write_stage05_input_binding(path: Path, binding: Stage05InputBinding) -> str:
    validate_stage05_input_binding(binding)
    _reject_holdout_paths(path)
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 input binding already exists")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    _require_directory(path.parent, "INPUT_BINDING_INVALID")
    _require_mode(path.parent, 0o700, "PERMISSION_FAILURE")
    _write_json_exclusive(path, binding.to_dict())
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return _sha256_file(path)


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        _fail(code, "Required text metadata is malformed")
    return value


def _required_uint(value: object, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail(code, "Required integer metadata is invalid")
    return value


def load_stage05_input_binding(
    path: Path, *, expected_sha256: str, authoritative_development: bool = False
) -> Stage05InputBinding:
    _digest_bytes(expected_sha256)
    _reject_holdout_paths(path)
    _require_regular_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Input binding SHA-256 differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    expected_fields = {
        "stage05_input_binding_version",
        "upstream_contract_version",
        "upstream_profile_version",
        "upstream_logical_fingerprint",
        "upstream_schema_fingerprint",
        "upstream_input_binding_sha256",
        "upstream_manifest_sha256",
        "upstream_ordered_identity_sha256",
        "input_benchmark_fingerprint",
        "expected_row_count",
    }
    if (
        set(value) != expected_fields
        or value.get("stage05_input_binding_version") != STAGE05_INPUT_BINDING_VERSION
    ):
        _fail("INPUT_BINDING_INVALID", "Stage 5 input binding fields are not exact")
    binding = Stage05InputBinding(
        upstream_contract_version=_required_text(
            value.get("upstream_contract_version"), "INPUT_BINDING_INVALID"
        ),
        upstream_profile_version=_required_text(
            value.get("upstream_profile_version"), "INPUT_BINDING_INVALID"
        ),
        upstream_logical_fingerprint=_required_text(
            value.get("upstream_logical_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        upstream_schema_fingerprint=_required_text(
            value.get("upstream_schema_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        upstream_input_binding_sha256=_required_text(
            value.get("upstream_input_binding_sha256"), "INPUT_BINDING_INVALID"
        ),
        upstream_manifest_sha256=_required_text(
            value.get("upstream_manifest_sha256"), "INPUT_BINDING_INVALID"
        ),
        upstream_ordered_identity_sha256=_required_text(
            value.get("upstream_ordered_identity_sha256"), "INPUT_BINDING_INVALID"
        ),
        input_benchmark_fingerprint=_required_text(
            value.get("input_benchmark_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        expected_row_count=_required_uint(
            value.get("expected_row_count"), "INPUT_BINDING_INVALID"
        ),
    )
    validate_stage05_input_binding(
        binding, authoritative_development=authoritative_development
    )
    return binding


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage05ValidationError(code, "Controlled JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON is not an object")
    return cast(dict[str, Any], value)


def _require_regular_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage05ValidationError(
            code, "Required artifact is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Required artifact is not a regular non-symlink file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage05ValidationError(
            code, "Required directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Required directory is not a regular non-symlink directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage05ValidationError(
            code, "Protected path mode is unavailable"
        ) from error
    if observed != expected:
        _fail(code, "Protected path is not owner-only")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage05ValidationError(
            "ARTIFACT_READ_FAILURE", "Controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _output_metadata(
    binding: Stage05InputBinding, logical_fingerprint: str
) -> dict[bytes, bytes]:
    values = {
        "stage05_contract_version": STAGE05_CONTRACT_VERSION,
        "stage05_profile_version": STAGE05_PROFILE_VERSION,
        "stage05_schema_version": STAGE05_SCHEMA_VERSION,
        "stage05_schema_fingerprint": stage05_schema_fingerprint(),
        "stage05_logical_dataset_sha256_v1": logical_fingerprint,
        "separator_unicode_escape": "\\u002c\\u0020",
        "line_order": STAGE05_LINE_ORDER,
        "empty_line_rule": STAGE05_EMPTY_LINE_RULE,
        "gap_rule": STAGE05_GAP_RULE,
        "duplicate_line_rule": STAGE05_DUPLICATE_LINE_RULE,
        "geographic_field_rule": STAGE05_GEOGRAPHIC_FIELD_RULE,
        "upstream_stage04_contract_version": binding.upstream_contract_version,
        "upstream_stage04_profile_version": binding.upstream_profile_version,
        "upstream_stage04_logical_fingerprint": binding.upstream_logical_fingerprint,
        "upstream_stage04_schema_fingerprint": binding.upstream_schema_fingerprint,
        "upstream_stage04_input_binding_sha256": binding.upstream_input_binding_sha256,
        "upstream_stage04_manifest_sha256": binding.upstream_manifest_sha256,
        "upstream_ordered_identity_sha256": binding.upstream_ordered_identity_sha256,
        "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _columns_as_lines(
    batch: pa.RecordBatch, names: tuple[str, ...], row_index: int
) -> tuple[str, str, str, str]:
    values = tuple(
        batch.column(batch.schema.get_field_index(name))[row_index].as_py()
        for name in names
    )
    if len(values) != 4 or any(not isinstance(value, str) for value in values):
        _fail("UPSTREAM_TYPE_MISMATCH", "Stage 5 input line is not exact text")
    return cast(tuple[str, str, str, str], values)


def _project_batch(
    batch: pa.RecordBatch, *, metadata: Mapping[bytes, bytes]
) -> pa.RecordBatch:
    if not batch.schema.remove_metadata().equals(
        stage04_schema(), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 5 input batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("UPSTREAM_NULL", "Stage 5 input contains an unexpected null")
    standard_clean: list[str] = []
    native_clean: list[str] = []
    standard_lower: list[str] = []
    native_lower: list[str] = []
    standard_available: list[bool] = []
    native_available: list[bool] = []
    standard_count: list[int] = []
    native_count: list[int] = []
    standard_mask: list[str] = []
    native_mask: list[str] = []
    for row_index in range(batch.num_rows):
        standard_clean_result = reconstruct_candidate(
            _columns_as_lines(batch, _CLEAN_STANDARD_COLUMNS, row_index)
        )
        native_clean_result = reconstruct_candidate(
            _columns_as_lines(batch, _CLEAN_NATIVE_COLUMNS, row_index)
        )
        standard_lower_result = reconstruct_candidate(
            _columns_as_lines(batch, _LOWER_STANDARD_COLUMNS, row_index)
        )
        native_lower_result = reconstruct_candidate(
            _columns_as_lines(batch, _LOWER_NATIVE_COLUMNS, row_index)
        )
        for clean_result, lower_result in (
            (standard_clean_result, standard_lower_result),
            (native_clean_result, native_lower_result),
        ):
            if (
                clean_result.available != lower_result.available
                or clean_result.contributing_line_count
                != lower_result.contributing_line_count
                or clean_result.contributing_line_mask
                != lower_result.contributing_line_mask
                or clean_result.candidate.lower() != lower_result.candidate
            ):
                _fail(
                    "UPSTREAM_REPRESENTATION_MISMATCH",
                    "Stage 3 clean and Stage 4 lower reconstruction disagree",
                )
        standard_clean.append(standard_clean_result.candidate)
        native_clean.append(native_clean_result.candidate)
        standard_lower.append(standard_lower_result.candidate)
        native_lower.append(native_lower_result.candidate)
        standard_available.append(standard_clean_result.available)
        native_available.append(native_clean_result.available)
        standard_count.append(standard_clean_result.contributing_line_count)
        native_count.append(native_clean_result.contributing_line_count)
        standard_mask.append(standard_clean_result.contributing_line_mask)
        native_mask.append(native_clean_result.contributing_line_mask)
    arrays = [batch.column(index) for index in range(batch.num_columns)]
    arrays.extend(
        (
            pa.array(standard_clean, type=pa.string(), from_pandas=False, safe=True),
            pa.array(native_clean, type=pa.string(), from_pandas=False, safe=True),
            pa.array(standard_lower, type=pa.string(), from_pandas=False, safe=True),
            pa.array(native_lower, type=pa.string(), from_pandas=False, safe=True),
            pa.array(standard_available, type=pa.bool_(), from_pandas=False),
            pa.array(native_available, type=pa.bool_(), from_pandas=False),
            pa.array(standard_count, type=pa.uint8(), from_pandas=False),
            pa.array(native_count, type=pa.uint8(), from_pandas=False),
            pa.array(standard_mask, type=pa.string(), from_pandas=False),
            pa.array(native_mask, type=pa.string(), from_pandas=False),
        )
    )
    return pa.RecordBatch.from_arrays(
        arrays, schema=stage05_schema().with_metadata(dict(metadata))
    )


def _line_end_class(value: str) -> str:
    final = value[-1]
    if final == ",":
        return "COMMA"
    if final == ";":
        return "SEMICOLON"
    if final == "/":
        return "SLASH"
    if final == "-" or unicodedata.category(final) == "Pd":
        return "HYPHEN_OR_DASH"
    if unicodedata.category(final).startswith("P"):
        return "OTHER_PUNCTUATION"
    return "NO_PUNCTUATION"


def _observe_representation(
    metrics: _RepresentationMetrics,
    *,
    clean_lines: tuple[str, str, str, str],
    lower_lines: tuple[str, str, str, str],
    clean_result: ReconstructedCandidate,
    lower_result: ReconstructedCandidate,
    lengths: sqlite3.Connection,
    representation: str,
) -> None:
    if lower_result.available:
        metrics.available += 1
    else:
        metrics.unavailable += 1
    metrics.line_counts[str(lower_result.contributing_line_count)] += 1
    metrics.masks[lower_result.contributing_line_mask] += 1
    if lower_result.contributing_line_mask not in _LEFT_PACKED_MASKS:
        metrics.gap_rows += 1
    clean_nonempty = tuple(value for value in clean_lines if value != "")
    lower_nonempty = tuple(value for value in lower_lines if value != "")
    clean_excess = len(clean_nonempty) - len(set(clean_nonempty))
    lower_excess = len(lower_nonempty) - len(set(lower_nonempty))
    if clean_excess:
        metrics.duplicate_line_rows_clean += 1
        metrics.duplicate_line_excess_clean += clean_excess
    if lower_excess:
        metrics.duplicate_line_rows_lower += 1
        metrics.duplicate_line_excess_lower += lower_excess
    for predecessor, successor in zip(lower_nonempty, lower_nonempty[1:]):
        metrics.internal_boundaries += 1
        metrics.predecessor_end[_line_end_class(predecessor)] += 1
        if unicodedata.category(successor[0]).startswith("P"):
            metrics.successor_starts_punctuation += 1
    metrics.separator_overhead += len(STAGE05_SEPARATOR) * max(
        0, lower_result.contributing_line_count - 1
    )
    if lower_result.available:
        length = len(lower_result.candidate)
        lengths.execute(
            "INSERT INTO candidate_lengths (representation, codepoints) VALUES (?, ?)",
            (representation, length),
        )
        for threshold in _LENGTH_THRESHOLDS:
            if length >= threshold:
                metrics.large[f"AT_LEAST_{threshold}_CODEPOINTS"] += 1
    if clean_result.candidate.lower() != lower_result.candidate:
        _fail("CLEAN_LOWER_MISMATCH", "Clean/lower reconstructed candidates differ")


def _validate_output_batch(
    batch: pa.RecordBatch, *, metrics: Stage05Metrics, lengths: sqlite3.Connection
) -> None:
    if not batch.schema.remove_metadata().equals(
        stage05_schema(), check_metadata=False
    ):
        _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 5 output batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("OUTPUT_NULL", "Stage 5 output contains an unexpected null")
    for row_index in range(batch.num_rows):
        standard_clean_lines = _columns_as_lines(
            batch, _CLEAN_STANDARD_COLUMNS, row_index
        )
        native_clean_lines = _columns_as_lines(batch, _CLEAN_NATIVE_COLUMNS, row_index)
        standard_lower_lines = _columns_as_lines(
            batch, _LOWER_STANDARD_COLUMNS, row_index
        )
        native_lower_lines = _columns_as_lines(batch, _LOWER_NATIVE_COLUMNS, row_index)
        expected_standard_clean = reconstruct_candidate(standard_clean_lines)
        expected_native_clean = reconstruct_candidate(native_clean_lines)
        expected_standard_lower = reconstruct_candidate(standard_lower_lines)
        expected_native_lower = reconstruct_candidate(native_lower_lines)
        observed_values = {
            name: batch.column(batch.schema.get_field_index(name))[row_index].as_py()
            for name in STAGE05_DERIVED_COLUMNS
        }
        expected_values: dict[str, object] = {
            CASE_PRESERVED_OUTPUT_COLUMNS[0]: expected_standard_clean.candidate,
            CASE_PRESERVED_OUTPUT_COLUMNS[1]: expected_native_clean.candidate,
            CANONICAL_OUTPUT_COLUMNS[0]: expected_standard_lower.candidate,
            CANONICAL_OUTPUT_COLUMNS[1]: expected_native_lower.candidate,
            STAGE05_AUDIT_COLUMNS[0]: expected_standard_lower.available,
            STAGE05_AUDIT_COLUMNS[1]: expected_native_lower.available,
            STAGE05_AUDIT_COLUMNS[2]: expected_standard_lower.contributing_line_count,
            STAGE05_AUDIT_COLUMNS[3]: expected_native_lower.contributing_line_count,
            STAGE05_AUDIT_COLUMNS[4]: expected_standard_lower.contributing_line_mask,
            STAGE05_AUDIT_COLUMNS[5]: expected_native_lower.contributing_line_mask,
        }
        if observed_values != expected_values:
            _fail(
                "RECONSTRUCTION_SEMANTIC_MISMATCH",
                "Stage 5 candidate or audit value differs from its contract",
            )
        if (
            reconstruct_candidate(
                (expected_standard_lower.candidate, "", "", "")
            ).candidate
            != expected_standard_lower.candidate
            or reconstruct_candidate(
                (expected_native_lower.candidate, "", "", "")
            ).candidate
            != expected_native_lower.candidate
        ):
            _fail("IDEMPOTENCE_FAILURE", "Stage 5 reconstruction is not idempotent")
        _observe_representation(
            metrics.standard,
            clean_lines=standard_clean_lines,
            lower_lines=standard_lower_lines,
            clean_result=expected_standard_clean,
            lower_result=expected_standard_lower,
            lengths=lengths,
            representation="STANDARD",
        )
        _observe_representation(
            metrics.native,
            clean_lines=native_clean_lines,
            lower_lines=native_lower_lines,
            clean_result=expected_native_clean,
            lower_result=expected_native_lower,
            lengths=lengths,
            representation="NATIVE",
        )
        standard_available = expected_standard_lower.available
        native_available = expected_native_lower.available
        if standard_available and native_available:
            metrics.relationship["BOTH"] += 1
            if expected_standard_lower.candidate == expected_native_lower.candidate:
                metrics.both_candidate["EXACT_EQUAL_CANONICAL"] += 1
            else:
                metrics.both_candidate["DIFFERENT"] += 1
            if (
                expected_standard_lower.contributing_line_count
                == expected_native_lower.contributing_line_count
            ):
                metrics.both_line_count["SAME_LINE_COUNT"] += 1
            else:
                metrics.both_line_count["DIFFERENT_LINE_COUNT"] += 1
        elif standard_available:
            metrics.relationship["STANDARD_ONLY"] += 1
        elif native_available:
            metrics.relationship["NATIVE_ONLY"] += 1
        else:
            metrics.relationship["NO_REPRESENTATION"] += 1
    metrics.input_rows += batch.num_rows
    metrics.output_rows += batch.num_rows


def _new_writer(path: Path, schema: pa.Schema) -> pq.ParquetWriter:
    try:
        writer = pq.ParquetWriter(
            path,
            schema,
            version="2.6",
            data_page_version="1.0",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=[
                "source_logical_record_number",
                "stage05_standard_candidate_available",
                "stage05_native_candidate_available",
            ],
            write_page_checksum=True,
            store_schema=True,
            use_compliant_nested_type=True,
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage05ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 5 Parquet writer could not start"
        ) from error
    path.chmod(0o600)
    return writer


def _iter_bounded_batches(
    parquet: pq.ParquetFile, *, batch_rows: int, target_batch_bytes: int
) -> Iterable[pa.RecordBatch]:
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        if row_group.num_rows < 1:
            _fail("PARQUET_READ_FAILURE", "Stage 5 encountered an empty row group")
        average_row_bytes = max(
            1,
            (row_group.total_byte_size + row_group.num_rows - 1) // row_group.num_rows,
        )
        adaptive_rows = max(1, min(batch_rows, target_batch_bytes // average_row_bytes))
        yield from parquet.iter_batches(
            batch_size=adaptive_rows,
            row_groups=[row_group_index],
            use_threads=False,
        )


def _iter_output_batches(
    parquet: pq.ParquetFile, *, maximum_batch_rows: int
) -> Iterable[pa.RecordBatch]:
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        if row_group.num_rows < 1 or row_group.num_rows > maximum_batch_rows:
            _fail("OUTPUT_ROW_MISMATCH", "Stage 5 output row group is not bounded")
        yield from parquet.iter_batches(
            batch_size=maximum_batch_rows,
            row_groups=[row_group_index],
            use_threads=False,
        )


def _stage04_artifacts(
    root: Path, binding: Stage05InputBinding
) -> tuple[Stage05ArtifactIdentity, ...]:
    try:
        outcome = validate_stage04_bundle(
            root,
            expected_manifest_sha256=binding.upstream_manifest_sha256,
            authoritative_development=True,
        )
    except Stage04ValidationError as error:
        raise Stage05ValidationError(
            "STAGE04_BUNDLE_INVALID", "Accepted Stage 4 bundle validation failed"
        ) from error
    if (
        outcome.logical_dataset_sha256_v1 != binding.upstream_logical_fingerprint
        or outcome.schema_fingerprint != binding.upstream_schema_fingerprint
        or outcome.input_binding_sha256 != binding.upstream_input_binding_sha256
        or outcome.ordered_identity_sha256 != binding.upstream_ordered_identity_sha256
        or outcome.row_count != binding.expected_row_count
    ):
        _fail("STAGE04_IDENTITY_MISMATCH", "Stage 4 scientific binding differs")
    manifest = _load_json(root / STAGE04_MANIFEST_NAME, "STAGE04_MANIFEST_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 identity is malformed")
    if (
        scientific.get("stage04_contract_version") != binding.upstream_contract_version
        or scientific.get("stage04_profile_version") != binding.upstream_profile_version
        or scientific.get("input_benchmark_fingerprint")
        != binding.input_benchmark_fingerprint
    ):
        _fail("STAGE04_IDENTITY_MISMATCH", "Stage 4 contract binding differs")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifacts are absent")
    artifacts: list[Stage05ArtifactIdentity] = []
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE04_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifact order is not exact")
        artifact = Stage05ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE04_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE04_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE04_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        artifacts.append(artifact)
    return tuple(artifacts)


def _input_artifact_snapshot(
    root: Path, artifact: Stage05ArtifactIdentity
) -> tuple[Path, tuple[int, int, int, int, str]]:
    path = root / artifact.relative_path
    _require_regular_file(path, "STAGE04_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    observed = path.stat(follow_symlinks=False)
    sha256 = _sha256_file(path)
    if observed.st_size != artifact.size_bytes or sha256 != artifact.sha256:
        _fail("STAGE04_ARTIFACT_MISMATCH", "Stage 4 artifact identity differs")
    return path, (
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
        sha256,
    )


def _assert_input_unchanged(
    path: Path, before: tuple[int, int, int, int, str], expected_sha256: str
) -> None:
    observed = path.stat(follow_symlinks=False)
    after = (
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
        _sha256_file(path),
    )
    if before != after or after[-1] != expected_sha256:
        _fail("INPUT_CHANGED", "Stage 4 input changed during Stage 5")


def _write_output_shard(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    target_batch_bytes: int,
    metadata: Mapping[bytes, bytes],
    input_identities: _OrderedStableIdentityHasher,
) -> tuple[int, str]:
    try:
        parquet = pq.ParquetFile(input_path, page_checksum_verification=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            stage04_schema(), check_metadata=False
        ):
            _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 4 Parquet schema is not exact")
        batches = _iter_bounded_batches(
            parquet, batch_rows=batch_rows, target_batch_bytes=target_batch_bytes
        )
    except Stage05ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage05ValidationError(
            "PARQUET_READ_FAILURE", "Stage 4 input could not be opened safely"
        ) from error
    writer = _new_writer(output_path, stage05_schema().with_metadata(dict(metadata)))
    rows = 0
    shard_identities = _OrderedStableIdentityHasher()
    try:
        for batch in batches:
            stable_ids = batch.column(
                batch.schema.get_field_index("stable_source_row_id_v1")
            )
            input_identities.update(stable_ids)
            shard_identities.update(stable_ids)
            projected = _project_batch(batch, metadata=metadata)
            writer.write_batch(projected, row_group_size=projected.num_rows)
            rows += projected.num_rows
        writer.close()
    except Stage05ValidationError:
        try:
            writer.close()
        except Exception:
            pass
        raise
    except (OSError, pa.ArrowException) as error:
        try:
            writer.close()
        except Exception:
            pass
        raise Stage05ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 5 Parquet output could not be written"
        ) from error
    output_path.chmod(0o600)
    return rows, shard_identities.hexdigest()


def _assert_input_output_equal(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    target_batch_bytes: int,
    metadata: Mapping[bytes, bytes],
    metrics: Stage05Metrics,
    lengths: sqlite3.Connection,
    output_identities: _OrderedStableIdentityHasher,
) -> str:
    try:
        input_file = pq.ParquetFile(input_path, page_checksum_verification=True)
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        if not output_file.schema_arrow.equals(
            stage05_schema().with_metadata(dict(metadata)), check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 5 output schema is not exact")
        input_batches = _iter_bounded_batches(
            input_file, batch_rows=batch_rows, target_batch_bytes=target_batch_bytes
        )
        output_batches = _iter_output_batches(
            output_file, maximum_batch_rows=batch_rows
        )
        shard_identities = _OrderedStableIdentityHasher()
        sentinel = object()
        for input_batch, output_batch in zip_longest(
            input_batches, output_batches, fillvalue=sentinel
        ):
            if input_batch is sentinel or output_batch is sentinel:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 5 batch topology differs")
            assert isinstance(input_batch, pa.RecordBatch)
            assert isinstance(output_batch, pa.RecordBatch)
            if input_batch.num_rows != output_batch.num_rows:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 5 batch row count differs")
            for index in range(len(stage04_schema())):
                if not input_batch.column(index).equals(output_batch.column(index)):
                    _fail(
                        "UPSTREAM_VALUE_MISMATCH",
                        "Stage 5 changed an incoming Stage 4 value or row order",
                    )
            _validate_output_batch(output_batch, metrics=metrics, lengths=lengths)
            stable_ids = output_batch.column(
                output_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            output_identities.update(stable_ids)
            shard_identities.update(stable_ids)
        return shard_identities.hexdigest()
    except Stage05ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage05ValidationError(
            "PARQUET_READBACK_FAILURE", "Stage 5 independent read-back failed"
        ) from error


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage05ArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "STAGE05_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage05ArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _length_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    path.chmod(0o600)
    connection.execute(
        "CREATE TABLE candidate_lengths (representation TEXT NOT NULL, "
        "codepoints INTEGER NOT NULL)"
    )
    return connection


def _length_statistics(
    connection: sqlite3.Connection, representation: str
) -> dict[str, int]:
    row = connection.execute(
        "SELECT COUNT(*), MIN(codepoints), SUM(codepoints), MAX(codepoints) "
        "FROM candidate_lengths WHERE representation = ?",
        (representation,),
    ).fetchone()
    assert row is not None
    count, minimum, total, maximum = (int(value or 0) for value in row)
    if count == 0:
        return {
            "COUNT": 0,
            "MIN": 0,
            "MEDIAN": 0,
            "MEAN_MILLI": 0,
            "P95_NEAREST_RANK": 0,
            "P99_NEAREST_RANK": 0,
            "MAX": 0,
        }

    def ordered(offset: int) -> int:
        value = connection.execute(
            "SELECT codepoints FROM candidate_lengths WHERE representation = ? "
            "ORDER BY codepoints LIMIT 1 OFFSET ?",
            (representation, offset),
        ).fetchone()
        assert value is not None
        return int(value[0])

    if count % 2:
        median = ordered(count // 2)
    else:
        median = (ordered(count // 2 - 1) + ordered(count // 2) + 1) // 2
    return {
        "COUNT": count,
        "MIN": minimum,
        "MEDIAN": median,
        "MEAN_MILLI": (total * 1_000 + count // 2) // count,
        "P95_NEAREST_RANK": ordered(math.ceil(0.95 * count) - 1),
        "P99_NEAREST_RANK": ordered(math.ceil(0.99 * count) - 1),
        "MAX": maximum,
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize_stage05(config: Stage05RunConfig) -> Stage05MaterializationOutcome:
    """Materialize conservative line-only candidates from accepted Stage 4."""
    config.validate()
    validate_stage05_runtime()
    if config.production:
        require_goethe_nhr_slurm("stage05-address-reconstruction")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 output directory already exists")
    binding = load_stage05_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
        authoritative_development=config.authoritative_development,
    )
    artifacts = _stage04_artifacts(config.stage04_output_directory, binding)
    logical_fingerprint = stage05_logical_dataset_sha256_v1(binding)
    metadata = _output_metadata(binding, logical_fingerprint)
    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE05_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 temporary output already exists")
    temporary.mkdir(mode=0o700)
    data_directory = temporary / "data"
    data_directory.mkdir(mode=0o700)
    _write_json_exclusive(
        temporary / STAGE05_IN_PROGRESS_MARKER, {"status": "STAGE05_INCOMPLETE"}
    )
    lengths_path = temporary / ".candidate_lengths.sqlite3"
    lengths = _length_database(lengths_path)
    metrics = Stage05Metrics()
    input_identities = _OrderedStableIdentityHasher()
    output_identities = _OrderedStableIdentityHasher()
    shard_identity_evidence: list[dict[str, str | int]] = []
    output_artifacts: list[Stage05ArtifactIdentity] = []
    try:
        for sequence, artifact in enumerate(artifacts, start=1):
            input_path, snapshot = _input_artifact_snapshot(
                config.stage04_output_directory, artifact
            )
            relative_output = f"data/part-{sequence:06d}.parquet"
            output_path = temporary / relative_output
            rows, input_digest = _write_output_shard(
                input_path,
                output_path,
                batch_rows=config.batch_rows,
                target_batch_bytes=config.target_batch_bytes,
                metadata=metadata,
                input_identities=input_identities,
            )
            output_digest = _assert_input_output_equal(
                input_path,
                output_path,
                batch_rows=config.batch_rows,
                target_batch_bytes=config.target_batch_bytes,
                metadata=metadata,
                metrics=metrics,
                lengths=lengths,
                output_identities=output_identities,
            )
            if input_digest != output_digest:
                _fail("STABLE_IDENTITY_MISMATCH", "Shard identity ordering differs")
            _assert_input_unchanged(input_path, snapshot, artifact.sha256)
            if rows != artifact.row_count:
                _fail("ROW_COUNT_MISMATCH", "Stage 5 shard row count differs")
            shard_identity_evidence.append(
                {
                    "relative_path": relative_output,
                    "row_count": rows,
                    "input_ordered_stable_identity_sha256_v1": input_digest,
                    "output_ordered_stable_identity_sha256_v1": output_digest,
                }
            )
            output_artifacts.append(
                _artifact_identity(temporary, relative_output, row_count=rows)
            )
        lengths.commit()
        standard_lengths = _length_statistics(lengths, "STANDARD")
        native_lengths = _length_statistics(lengths, "NATIVE")
    finally:
        lengths.close()
    lengths_path.unlink()
    ordered_digest = output_identities.hexdigest()
    if (
        metrics.output_rows != binding.expected_row_count
        or input_identities.row_count != binding.expected_row_count
        or output_identities.row_count != binding.expected_row_count
    ):
        _fail("ROW_COUNT_MISMATCH", "Stage 5 total row count differs")
    if (
        input_identities.hexdigest() != ordered_digest
        or ordered_digest != binding.upstream_ordered_identity_sha256
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Stable identity stream is not exact")
    metric_groups = metrics.to_metric_groups(
        standard_lengths=standard_lengths, native_lengths=native_lengths
    )
    manifest = {
        "stage05_manifest_version": STAGE05_MANIFEST_VERSION,
        "status": "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED",
        "scientific_identity": {
            "stage05_contract_version": STAGE05_CONTRACT_VERSION,
            "stage05_profile_version": STAGE05_PROFILE_VERSION,
            "stage05_schema_version": STAGE05_SCHEMA_VERSION,
            "stage05_schema_fingerprint": stage05_schema_fingerprint(),
            "stage05_logical_dataset_sha256_v1": logical_fingerprint,
            "case_preserved_input_columns": [
                *_CLEAN_STANDARD_COLUMNS,
                *_CLEAN_NATIVE_COLUMNS,
            ],
            "lower_input_columns": [*_LOWER_STANDARD_COLUMNS, *_LOWER_NATIVE_COLUMNS],
            "derived_columns": list(STAGE05_DERIVED_COLUMNS),
            "separator_unicode_escape": "\\u002c\\u0020",
            "line_order": STAGE05_LINE_ORDER,
            "empty_line_rule": STAGE05_EMPTY_LINE_RULE,
            "gap_rule": STAGE05_GAP_RULE,
            "duplicate_line_rule": STAGE05_DUPLICATE_LINE_RULE,
            "geographic_field_rule": STAGE05_GEOGRAPHIC_FIELD_RULE,
            "standard_native_separate": True,
            "upstream_stage04_contract_version": binding.upstream_contract_version,
            "upstream_stage04_profile_version": binding.upstream_profile_version,
            "upstream_stage04_logical_fingerprint": (
                binding.upstream_logical_fingerprint
            ),
            "upstream_stage04_schema_fingerprint": binding.upstream_schema_fingerprint,
            "upstream_stage04_input_binding_sha256": (
                binding.upstream_input_binding_sha256
            ),
            "upstream_ordered_identity_sha256": (
                binding.upstream_ordered_identity_sha256
            ),
            "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
            "row_count": metrics.output_rows,
        },
        "development_metrics": metric_groups,
        "physical_identity": {
            "stage05_input_binding_sha256": config.expected_input_binding_sha256,
            "upstream_stage04_manifest_sha256": binding.upstream_manifest_sha256,
            "input_artifacts": [item.to_dict() for item in artifacts],
            "output_artifacts": [item.to_dict() for item in output_artifacts],
            "owner_only_permissions": True,
            "bounded_memory_architecture": {
                "maximum_configured_batch_rows": config.batch_rows,
                "target_uncompressed_batch_bytes": config.target_batch_bytes,
                "memory_scales_with_total_row_count": False,
                "total_row_python_identity_set_used": False,
                "length_quantiles_disk_backed": True,
                "review_selection_maximum_rows": 500,
            },
            "ordered_identity_validation": {
                "ordered_identity_contract_version": STAGE05_ORDERED_IDENTITY_VERSION,
                "upstream_duplicate_free_invariant_bound": True,
                "input_ordered_stable_identity_sha256_v1": input_identities.hexdigest(),
                "output_ordered_stable_identity_sha256_v1": ordered_digest,
                "row_count": metrics.output_rows,
                "shards": shard_identity_evidence,
            },
        },
        "validation": {
            "validation_contract_version": STAGE05_VALIDATION_VERSION,
            "stage04_bundle_validated": "PASS",
            "all_stage04_columns_preserved": "PASS",
            "standard_native_separate": "PASS",
            "line_only_reconstruction": "PASS",
            "candidate_semantics": "PASS",
            "audit_semantics": "PASS",
            "idempotence": "PASS",
            "ordered_identity": "PASS",
            "bounded_memory": "PASS",
            "page_checksum_readback": "PASS",
            "owner_only_permissions": "PASS",
            "atomic_publication": "PASS",
            "holdout_exclusion": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "pyarrow_version": pa.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json_exclusive(temporary / STAGE05_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(
        temporary, STAGE05_MANIFEST_NAME, row_count=0
    )
    _write_json_exclusive(
        temporary / STAGE05_SUCCESS_MARKER,
        {
            "status": "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "stage05_manifest_sha256": manifest_identity.sha256,
            "stage05_manifest_size_bytes": manifest_identity.size_bytes,
            "stage05_logical_dataset_sha256_v1": logical_fingerprint,
            "stage05_schema_fingerprint": stage05_schema_fingerprint(),
            "stage05_input_binding_sha256": config.expected_input_binding_sha256,
            "ordered_stable_identity_sha256_v1": ordered_digest,
            "row_count": metrics.output_rows,
            "output_shard_count": len(output_artifacts),
        },
    )
    (temporary / STAGE05_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(data_directory)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage05_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_identity.sha256,
        authoritative_development=config.authoritative_development,
    )


def _binding_from_manifest(manifest: Mapping[str, Any]) -> Stage05InputBinding:
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 identity is malformed")
    return Stage05InputBinding(
        upstream_contract_version=_required_text(
            scientific.get("upstream_stage04_contract_version"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_profile_version=_required_text(
            scientific.get("upstream_stage04_profile_version"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_logical_fingerprint=_required_text(
            scientific.get("upstream_stage04_logical_fingerprint"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_schema_fingerprint=_required_text(
            scientific.get("upstream_stage04_schema_fingerprint"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_input_binding_sha256=_required_text(
            scientific.get("upstream_stage04_input_binding_sha256"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_manifest_sha256=_required_text(
            physical.get("upstream_stage04_manifest_sha256"),
            "STAGE05_MANIFEST_INVALID",
        ),
        upstream_ordered_identity_sha256=_required_text(
            scientific.get("upstream_ordered_identity_sha256"),
            "STAGE05_MANIFEST_INVALID",
        ),
        input_benchmark_fingerprint=_required_text(
            scientific.get("input_benchmark_fingerprint"), "STAGE05_MANIFEST_INVALID"
        ),
        expected_row_count=_required_uint(
            scientific.get("row_count"), "STAGE05_MANIFEST_INVALID"
        ),
    )


def _validated_metrics(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 metrics are malformed")
    result: dict[str, dict[str, int]] = {}
    for group, raw_metrics in value.items():
        if not isinstance(group, str) or not isinstance(raw_metrics, dict):
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 metrics are malformed")
        metrics: dict[str, int] = {}
        for name, raw_count in raw_metrics.items():
            if (
                not isinstance(name, str)
                or not isinstance(raw_count, int)
                or isinstance(raw_count, bool)
                or raw_count < 0
            ):
                _fail("STAGE05_MANIFEST_INVALID", "Stage 5 metric value is invalid")
            metrics[name] = raw_count
        result[group] = metrics
    empty_lengths = {
        "COUNT": 0,
        "MIN": 0,
        "MEDIAN": 0,
        "MEAN_MILLI": 0,
        "P95_NEAREST_RANK": 0,
        "P99_NEAREST_RANK": 0,
        "MAX": 0,
    }
    expected = Stage05Metrics().to_metric_groups(
        standard_lengths=empty_lengths,
        native_lengths=empty_lengths,
    )
    if set(result) != set(expected) or any(
        set(result[group]) != set(expected[group]) for group in expected
    ):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 metric fields are not exact")
    return result


def _observed_topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            path = current / name
            if path.is_symlink():
                _fail("UNSAFE_OUTPUT", "Stage 5 output contains a symlink")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "UNSAFE_OUTPUT")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def validate_stage05_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    authoritative_development: bool = True,
    stage04_output_directory: Path | None = None,
) -> Stage05MaterializationOutcome:
    """Independently recompute and validate a published Stage 5 bundle."""
    validate_stage05_runtime()
    _digest_bytes(expected_manifest_sha256)
    _reject_holdout_paths(output_directory)
    if stage04_output_directory is not None:
        _reject_holdout_paths(stage04_output_directory)
    _require_directory(output_directory, "STAGE05_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    data_directory = output_directory / "data"
    _require_directory(data_directory, "STAGE05_OUTPUT_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    directories, files = _observed_topology(output_directory)
    if directories != {"data"}:
        _fail("STAGE05_ARTIFACT_MISMATCH", "Stage 5 directory topology is invalid")
    manifest_path = output_directory / STAGE05_MANIFEST_NAME
    success_path = output_directory / STAGE05_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE05_TERMINAL_MISSING")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE05_MANIFEST_SHA256_MISMATCH", "Stage 5 manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE05_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE05_SUCCESS_INVALID")
    if (
        manifest.get("stage05_manifest_version") != STAGE05_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_5_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage05_manifest_sha256") != manifest_sha
        or success.get("stage05_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
    ):
        _fail("STAGE05_TERMINAL_MISMATCH", "Stage 5 terminal state differs")
    binding = _binding_from_manifest(manifest)
    validate_stage05_input_binding(
        binding, authoritative_development=authoritative_development
    )
    logical = stage05_logical_dataset_sha256_v1(binding)
    scientific = cast(dict[str, Any], manifest["scientific_identity"])
    physical = cast(dict[str, Any], manifest["physical_identity"])
    validation = manifest.get("validation")
    if (
        scientific.get("stage05_contract_version") != STAGE05_CONTRACT_VERSION
        or scientific.get("stage05_profile_version") != STAGE05_PROFILE_VERSION
        or scientific.get("stage05_schema_version") != STAGE05_SCHEMA_VERSION
        or scientific.get("stage05_schema_fingerprint") != stage05_schema_fingerprint()
        or scientific.get("stage05_logical_dataset_sha256_v1") != logical
        or scientific.get("derived_columns") != list(STAGE05_DERIVED_COLUMNS)
        or scientific.get("separator_unicode_escape") != "\\u002c\\u0020"
        or scientific.get("line_order") != STAGE05_LINE_ORDER
        or scientific.get("empty_line_rule") != STAGE05_EMPTY_LINE_RULE
        or scientific.get("gap_rule") != STAGE05_GAP_RULE
        or scientific.get("duplicate_line_rule") != STAGE05_DUPLICATE_LINE_RULE
        or scientific.get("geographic_field_rule") != STAGE05_GEOGRAPHIC_FIELD_RULE
        or scientific.get("standard_native_separate") is not True
        or success.get("stage05_logical_dataset_sha256_v1") != logical
        or success.get("stage05_schema_fingerprint") != stage05_schema_fingerprint()
    ):
        _fail("STAGE05_FINGERPRINT_MISMATCH", "Stage 5 scientific identity differs")
    input_binding_sha = _required_text(
        physical.get("stage05_input_binding_sha256"), "STAGE05_MANIFEST_INVALID"
    )
    _digest_bytes(input_binding_sha)
    if success.get("stage05_input_binding_sha256") != input_binding_sha:
        _fail("STAGE05_TERMINAL_MISMATCH", "Stage 5 input binding differs")
    bounded = physical.get("bounded_memory_architecture")
    if not isinstance(bounded, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Bounded-memory evidence is malformed")
    maximum_batch_rows = _required_uint(
        bounded.get("maximum_configured_batch_rows"), "STAGE05_MANIFEST_INVALID"
    )
    target_batch_bytes = _required_uint(
        bounded.get("target_uncompressed_batch_bytes"), "STAGE05_MANIFEST_INVALID"
    )
    if (
        maximum_batch_rows < 1
        or target_batch_bytes < 1
        or bounded.get("memory_scales_with_total_row_count") is not False
        or bounded.get("total_row_python_identity_set_used") is not False
        or bounded.get("length_quantiles_disk_backed") is not True
        or bounded.get("review_selection_maximum_rows") != 500
        or physical.get("owner_only_permissions") is not True
    ):
        _fail("STAGE05_MANIFEST_INVALID", "Bounded-memory evidence differs")
    if (
        not isinstance(validation, dict)
        or validation.get("validation_contract_version") != STAGE05_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE05_VALIDATION_INCOMPLETE", "Stage 5 validation is incomplete")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifacts are absent")
    output_artifacts: list[Stage05ArtifactIdentity] = []
    expected_files = {STAGE05_MANIFEST_NAME, STAGE05_SUCCESS_MARKER}
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact is malformed")
        relative = _required_text(raw.get("relative_path"), "STAGE05_MANIFEST_INVALID")
        if relative != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact order differs")
        artifact = Stage05ArtifactIdentity(
            relative_path=relative,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE05_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE05_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE05_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        output_artifacts.append(artifact)
        expected_files.add(relative)
    if files != expected_files:
        _fail("STAGE05_ARTIFACT_MISMATCH", "Stage 5 artifact topology is incomplete")
    upstream_artifacts: tuple[Stage05ArtifactIdentity, ...] | None = None
    if stage04_output_directory is not None:
        upstream_artifacts = _stage04_artifacts(stage04_output_directory, binding)
        if len(upstream_artifacts) != len(output_artifacts):
            _fail("OUTPUT_ROW_MISMATCH", "Published Stage 5 shard count differs")
    ordered = physical.get("ordered_identity_validation")
    if not isinstance(ordered, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Ordered identity evidence is malformed")
    output_identity_digest = _required_text(
        ordered.get("output_ordered_stable_identity_sha256_v1"),
        "STAGE05_MANIFEST_INVALID",
    )
    input_identity_digest = _required_text(
        ordered.get("input_ordered_stable_identity_sha256_v1"),
        "STAGE05_MANIFEST_INVALID",
    )
    raw_shards = ordered.get("shards")
    if (
        ordered.get("ordered_identity_contract_version")
        != STAGE05_ORDERED_IDENTITY_VERSION
        or ordered.get("upstream_duplicate_free_invariant_bound") is not True
        or ordered.get("row_count") != binding.expected_row_count
        or input_identity_digest != output_identity_digest
        or output_identity_digest != binding.upstream_ordered_identity_sha256
        or not isinstance(raw_shards, list)
        or len(raw_shards) != len(output_artifacts)
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Ordered identity evidence differs")
    expected_metadata = _output_metadata(binding, logical)
    metrics = Stage05Metrics()
    identities = _OrderedStableIdentityHasher()
    validation_temp = output_directory.parent / (
        f".{output_directory.name}.{os.getpid()}.validation_lengths.sqlite3"
    )
    if validation_temp.exists() or validation_temp.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 5 validation temporary state exists")
    lengths = _length_database(validation_temp)
    try:
        for index, (artifact, shard) in enumerate(
            zip(output_artifacts, raw_shards, strict=True)
        ):
            if not isinstance(shard, dict):
                _fail(
                    "STAGE05_MANIFEST_INVALID", "Shard identity evidence is malformed"
                )
            path = output_directory / artifact.relative_path
            _require_mode(path, 0o600, "PERMISSION_FAILURE")
            if (
                path.stat(follow_symlinks=False).st_size != artifact.size_bytes
                or _sha256_file(path) != artifact.sha256
            ):
                _fail("STAGE05_ARTIFACT_MISMATCH", "Stage 5 artifact identity differs")
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            if not parquet.schema_arrow.equals(
                stage05_schema().with_metadata(expected_metadata), check_metadata=True
            ):
                _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 5 output schema is not exact")
            shard_hasher = _OrderedStableIdentityHasher()
            shard_rows = 0
            output_batches = _iter_output_batches(
                parquet, maximum_batch_rows=maximum_batch_rows
            )
            if upstream_artifacts is not None and stage04_output_directory is not None:
                upstream_artifact = upstream_artifacts[index]
                upstream_path, snapshot = _input_artifact_snapshot(
                    stage04_output_directory, upstream_artifact
                )
                upstream_file = pq.ParquetFile(
                    upstream_path, page_checksum_verification=True
                )
                upstream_batches: Iterable[pa.RecordBatch] = _iter_bounded_batches(
                    upstream_file,
                    batch_rows=maximum_batch_rows,
                    target_batch_bytes=target_batch_bytes,
                )
            else:
                upstream_artifact = None
                upstream_path = None
                snapshot = None
                upstream_batches = ()
            sentinel = object()
            paired = (
                zip_longest(upstream_batches, output_batches, fillvalue=sentinel)
                if upstream_artifact is not None
                else ((None, batch) for batch in output_batches)
            )
            for upstream_batch, batch in paired:
                if batch is sentinel or upstream_batch is sentinel:
                    _fail("OUTPUT_ROW_MISMATCH", "Published Stage 5 topology differs")
                assert isinstance(batch, pa.RecordBatch)
                if upstream_batch is not None:
                    assert isinstance(upstream_batch, pa.RecordBatch)
                    if upstream_batch.num_rows != batch.num_rows:
                        _fail("OUTPUT_ROW_MISMATCH", "Published Stage 5 rows differ")
                    for column_index in range(len(stage04_schema())):
                        if not upstream_batch.column(column_index).equals(
                            batch.column(column_index)
                        ):
                            _fail(
                                "UPSTREAM_VALUE_MISMATCH",
                                "Published Stage 5 changed an incoming Stage 4 value",
                            )
                _validate_output_batch(batch, metrics=metrics, lengths=lengths)
                stable_ids = batch.column(
                    batch.schema.get_field_index("stable_source_row_id_v1")
                )
                identities.update(stable_ids)
                shard_hasher.update(stable_ids)
                shard_rows += batch.num_rows
            shard_digest = shard_hasher.hexdigest()
            if (
                shard_rows != artifact.row_count
                or shard.get("relative_path") != artifact.relative_path
                or shard.get("row_count") != artifact.row_count
                or shard.get("input_ordered_stable_identity_sha256_v1") != shard_digest
                or shard.get("output_ordered_stable_identity_sha256_v1") != shard_digest
            ):
                _fail("STABLE_IDENTITY_MISMATCH", "Shard identity evidence differs")
            if (
                upstream_path is not None
                and snapshot is not None
                and upstream_artifact is not None
            ):
                _assert_input_unchanged(
                    upstream_path, snapshot, upstream_artifact.sha256
                )
        lengths.commit()
        standard_lengths = _length_statistics(lengths, "STANDARD")
        native_lengths = _length_statistics(lengths, "NATIVE")
    except Stage05ValidationError:
        raise
    except (OSError, pa.ArrowException, sqlite3.Error) as error:
        raise Stage05ValidationError(
            "STAGE05_READBACK_FAILURE", "Stage 5 independent read-back failed"
        ) from error
    finally:
        lengths.close()
        if validation_temp.exists() and not validation_temp.is_symlink():
            validation_temp.unlink()
    if (
        metrics.output_rows != binding.expected_row_count
        or identities.row_count != binding.expected_row_count
        or identities.hexdigest() != output_identity_digest
    ):
        _fail("ROW_COUNT_MISMATCH", "Stage 5 total identity stream differs")
    observed_metrics = metrics.to_metric_groups(
        standard_lengths=standard_lengths, native_lengths=native_lengths
    )
    recorded_metrics = _validated_metrics(manifest.get("development_metrics"))
    if observed_metrics != recorded_metrics:
        _fail("STAGE05_METRIC_MISMATCH", "Stage 5 aggregate metrics differ")
    if any(recorded_metrics["RECONSTRUCTION_VALIDATION"].values()):
        _fail("STAGE05_SCIENTIFIC_GATE_FAILURE", "Stage 5 terminal gates failed")
    if (
        success.get("row_count") != metrics.output_rows
        or success.get("output_shard_count") != len(output_artifacts)
        or success.get("ordered_stable_identity_sha256_v1") != output_identity_digest
    ):
        _fail("STAGE05_TERMINAL_MISMATCH", "Stage 5 terminal counts differ")
    return Stage05MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=logical,
        schema_fingerprint=stage05_schema_fingerprint(),
        input_binding_sha256=input_binding_sha,
        manifest_sha256=manifest_sha,
        ordered_identity_sha256=output_identity_digest,
        row_count=metrics.output_rows,
        output_shard_count=len(output_artifacts),
        metrics=recorded_metrics,
    )


__all__ = [
    "ACCEPTED_BENCHMARK_FINGERPRINT",
    "ACCEPTED_DEVELOPMENT_ROWS",
    "ACCEPTED_STAGE04_INPUT_BINDING_SHA256",
    "ACCEPTED_STAGE04_LOGICAL_FINGERPRINT",
    "ACCEPTED_STAGE04_MANIFEST_SHA256",
    "ACCEPTED_STAGE04_ORDERED_IDENTITY_SHA256",
    "ACCEPTED_STAGE04_SCHEMA_FINGERPRINT",
    "CANONICAL_OUTPUT_COLUMNS",
    "CASE_PRESERVED_OUTPUT_COLUMNS",
    "STAGE05_AUDIT_COLUMNS",
    "STAGE05_CONTRACT_VERSION",
    "STAGE05_DERIVED_COLUMNS",
    "STAGE05_INPUT_BINDING_VERSION",
    "STAGE05_MANIFEST_NAME",
    "STAGE05_PROFILE_VERSION",
    "STAGE05_SCHEMA_VERSION",
    "STAGE05_SEPARATOR",
    "ReconstructedCandidate",
    "Stage05InputBinding",
    "Stage05MaterializationOutcome",
    "Stage05RunConfig",
    "Stage05ValidationError",
    "load_stage05_input_binding",
    "materialize_stage05",
    "reconstruct_candidate",
    "stage05_logical_dataset_sha256_v1",
    "stage05_schema",
    "stage05_schema_fingerprint",
    "validate_stage05_bundle",
    "validate_stage05_input_binding",
    "validate_stage05_runtime",
    "write_stage05_input_binding",
]

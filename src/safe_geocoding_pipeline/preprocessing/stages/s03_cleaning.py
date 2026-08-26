from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import struct
import sys
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from typing import Any, Mapping, NoReturn, Protocol, Sequence, cast

import ftfy
import pyarrow as pa
import pyarrow.parquet as pq
from ftfy import TextFixerConfig, fix_encoding_and_explain
from ftfy.fixes import remove_terminal_escapes

from ...execution_policy import require_goethe_nhr_slurm
from .s02_harmonization import (
    NATIVE_ADDRESS_COLUMNS,
    STANDARD_ADDRESS_COLUMNS,
    STAGE02_CONTRACT_VERSION,
    STAGE02_MANIFEST_NAME,
    Stage02ValidationError,
    stage02_schema,
    stage02_schema_fingerprint,
    validate_stage02_bundle,
)

STAGE03_CONTRACT_VERSION = "stage03_safe_text_cleaning_contract_v1"
STAGE03_PROFILE_VERSION = "stage03_safe_text_cleaning_profile_v1"
STAGE03_INPUT_BINDING_VERSION = "stage03_input_binding_v1"
STAGE03_SCHEMA_VERSION = "stage03_canonical_clean_text_schema_v1"
STAGE03_VALIDATION_VERSION = "stage03_bundle_validation_v1"
STAGE03_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE03_LOGICAL_DATASET_V1"
STAGE03_SCHEMA_FINGERPRINT_DOMAIN = b"SAFE_STAGE03_ARROW_SCHEMA_V1"
STAGE03_MANIFEST_VERSION = "stage03_manifest_v1"

STAGE03_MANIFEST_NAME = "stage03_manifest.json"
STAGE03_SUCCESS_MARKER = "_SUCCESS.json"
STAGE03_IN_PROGRESS_MARKER = "_IN_PROGRESS"

EXPECTED_PYTHON_VERSION = (3, 14, 3)
EXPECTED_UNICODE_VERSION = "16.0.0"
EXPECTED_FTFY_VERSION = "6.3.1"
EXPECTED_PYARROW_VERSION = "25.0.0"

CLEAN_SOURCE_COLUMNS = (
    *STANDARD_ADDRESS_COLUMNS,
    *NATIVE_ADDRESS_COLUMNS,
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
)
CLEAN_DERIVED_COLUMNS = tuple(f"stage03_clean_{name}" for name in CLEAN_SOURCE_COLUMNS)
STAGE03_AUDIT_COLUMNS = ("stage03_change_details", "stage03_row_changed")

REASON_CODES = (
    "ENCODING_REPAIRED",
    "TERMINAL_ESCAPE_REMOVED",
    "CONTROL_CHARACTER_REMOVED",
    "TAB_NORMALIZED",
    "LINEBREAK_NORMALIZED",
    "UNICODE_WHITESPACE_NORMALIZED",
    "WHITESPACE_COLLAPSED",
    "WHITESPACE_TRIMMED",
    "WHITESPACE_ONLY_TO_EMPTY",
    "BOM_REMOVED",
    "UNICODE_NFC_NORMALIZED",
)

FIELD_GROUP_BY_COLUMN: Mapping[str, str] = {
    **{name: "STANDARD_ADDRESS_LINES" for name in STANDARD_ADDRESS_COLUMNS},
    **{name: "NATIVE_ADDRESS_LINES" for name in NATIVE_ADDRESS_COLUMNS},
    "postcode": "POSTCODE",
    "city": "CITY_LOCALITY",
    "region_in_country": "REGION",
    "country_iso_code": "COUNTRY_SOURCE_GEOGRAPHY",
}
FIELD_GROUPS = (
    "STANDARD_ADDRESS_LINES",
    "NATIVE_ADDRESS_LINES",
    "POSTCODE",
    "CITY_LOCALITY",
    "REGION",
    "COUNTRY_SOURCE_GEOGRAPHY",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MULTIPLE_SPACES_RE = re.compile(r" {2,}")
_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"

_UNICODE_WHITE_SPACE = frozenset(
    {
        *range(0x0009, 0x000E),
        0x0020,
        0x0085,
        0x00A0,
        0x1680,
        *range(0x2000, 0x200B),
        0x2028,
        0x2029,
        0x202F,
        0x205F,
        0x3000,
    }
)
_LINEBREAKS = frozenset({0x000A, 0x000B, 0x000C, 0x000D, 0x0085, 0x2028, 0x2029})
_OTHER_UNICODE_WHITE_SPACE = _UNICODE_WHITE_SPACE - {0x0009, 0x0020} - _LINEBREAKS
_REMOVABLE_CONTROLS = frozenset(
    {
        *range(0x0000, 0x0009),
        *range(0x000E, 0x0020),
        *range(0x007F, 0x0085),
        *range(0x0086, 0x00A0),
    }
)

FTFY_CONFIG = TextFixerConfig(
    unescape_html=False,
    remove_terminal_escapes=False,
    fix_encoding=True,
    restore_byte_a0=False,
    replace_lossy_sequences=False,
    decode_inconsistent_utf8=False,
    fix_c1_controls=True,
    fix_latin_ligatures=False,
    fix_character_width=False,
    uncurl_quotes=False,
    fix_line_breaks=False,
    fix_surrogates=False,
    remove_control_chars=False,
    normalization=None,
    max_decode_length=1_000_000,
    explain=True,
)

_CHANGE_REASON_LIST_TYPE = pa.list_(pa.field("element", pa.string(), nullable=False))
_CHANGE_DETAIL_STRUCT_TYPE = pa.struct(
    (
        pa.field("field_name", pa.string(), nullable=False),
        pa.field("reason_codes", _CHANGE_REASON_LIST_TYPE, nullable=False),
    )
)
CHANGE_DETAILS_TYPE = pa.list_(
    pa.field("element", _CHANGE_DETAIL_STRUCT_TYPE, nullable=False)
)


class Stage03ValidationError(RuntimeError):
    """Privacy-safe, fail-closed Stage 3 validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CleanTextResult:
    value: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stage03InputBinding:
    upstream_contract_version: str
    upstream_logical_identity_sha256: str
    upstream_schema_fingerprint: str
    upstream_manifest_sha256: str
    input_benchmark_fingerprint: str
    expected_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "stage03_input_binding_version": STAGE03_INPUT_BINDING_VERSION,
            "upstream_contract_version": self.upstream_contract_version,
            "upstream_logical_identity_sha256": self.upstream_logical_identity_sha256,
            "upstream_schema_fingerprint": self.upstream_schema_fingerprint,
            "upstream_manifest_sha256": self.upstream_manifest_sha256,
            "input_benchmark_fingerprint": self.input_benchmark_fingerprint,
            "expected_row_count": self.expected_row_count,
        }


@dataclass(frozen=True, slots=True)
class Stage03RunConfig:
    stage02_output_directory: Path
    input_binding_file: Path
    expected_input_binding_sha256: str
    output_directory: Path
    execution_git_sha: str
    production: bool = True
    batch_rows: int = 2_048
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        _digest_bytes(self.expected_input_binding_sha256)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git commit must be a full SHA")
        if isinstance(self.batch_rows, bool) or self.batch_rows < 1:
            _fail("INVALID_BATCH_SIZE", "Batch row count must be positive")
        _reject_holdout_paths(
            self.stage02_output_directory,
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
class Stage03ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage03MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    schema_fingerprint: str
    input_binding_sha256: str
    manifest_sha256: str
    row_count: int
    output_shard_count: int
    metrics: Mapping[str, Mapping[str, int]]


@dataclass(slots=True)
class Stage03Metrics:
    input_rows: int = 0
    output_rows: int = 0
    rows_changed: int = 0
    total_cleaned_fields: int = 0
    changed_fields: int = 0
    clean_values_became_empty: int = 0
    idempotence_failures: int = 0
    max_length_increase: int = 0
    max_length_decrease: int = 0
    reason_fields: Counter[str] = field(
        default_factory=lambda: Counter({reason: 0 for reason in REASON_CODES})
    )
    reason_rows: Counter[str] = field(
        default_factory=lambda: Counter({reason: 0 for reason in REASON_CODES})
    )
    field_group_changed_fields: Counter[str] = field(
        default_factory=lambda: Counter({group: 0 for group in FIELD_GROUPS})
    )
    field_group_affected_rows: Counter[str] = field(
        default_factory=lambda: Counter({group: 0 for group in FIELD_GROUPS})
    )

    def observe_row(
        self,
        *,
        raw_values: Sequence[str],
        results: Sequence[CleanTextResult],
    ) -> None:
        if len(raw_values) != len(CLEAN_SOURCE_COLUMNS) or len(results) != len(
            CLEAN_SOURCE_COLUMNS
        ):
            _fail("INTERNAL_METRIC_ERROR", "Cleaning metric arity is invalid")
        self.input_rows += 1
        self.output_rows += 1
        self.total_cleaned_fields += len(CLEAN_SOURCE_COLUMNS)
        row_reasons: set[str] = set()
        row_groups: set[str] = set()
        row_changed = False
        for column, raw, result in zip(
            CLEAN_SOURCE_COLUMNS, raw_values, results, strict=True
        ):
            if result.value == raw:
                if result.reason_codes:
                    _fail("CHANGE_AUDIT_MISMATCH", "Unchanged value has reason codes")
                continue
            if not result.reason_codes:
                _fail("CHANGE_AUDIT_MISMATCH", "Changed value has no reason code")
            row_changed = True
            self.changed_fields += 1
            group = FIELD_GROUP_BY_COLUMN[column]
            self.field_group_changed_fields[group] += 1
            row_groups.add(group)
            for reason in result.reason_codes:
                self.reason_fields[reason] += 1
                row_reasons.add(reason)
            if raw != "" and result.value == "":
                self.clean_values_became_empty += 1
            delta = len(result.value) - len(raw)
            if delta > self.max_length_increase:
                self.max_length_increase = delta
            if -delta > self.max_length_decrease:
                self.max_length_decrease = -delta
        if row_changed:
            self.rows_changed += 1
        self.reason_rows.update(row_reasons)
        self.field_group_affected_rows.update(row_groups)

    def to_metric_groups(self) -> dict[str, dict[str, int]]:
        rows_unchanged = self.output_rows - self.rows_changed
        unchanged_fields = self.total_cleaned_fields - self.changed_fields
        basis_points = (
            (self.rows_changed * 10_000 + self.output_rows // 2) // self.output_rows
            if self.output_rows
            else 0
        )
        group_totals = {
            group: self.output_rows
            * sum(FIELD_GROUP_BY_COLUMN[name] == group for name in CLEAN_SOURCE_COLUMNS)
            for group in FIELD_GROUPS
        }
        return {
            "ROW_INTEGRITY": {
                "INPUT_ROWS": self.input_rows,
                "OUTPUT_ROWS": self.output_rows,
                "DROPPED_ROWS": 0,
                "ADDED_ROWS": 0,
                "DUPLICATE_IDENTITIES": 0,
            },
            "CHANGE_RATE": {
                "ROWS_CHANGED": self.rows_changed,
                "ROWS_UNCHANGED": rows_unchanged,
                "ROWS_CHANGED_PERCENT_BASIS_POINTS": basis_points,
            },
            "FIELD_CHANGES": {
                "TOTAL_CLEANED_FIELDS": self.total_cleaned_fields,
                "CHANGED_FIELDS": self.changed_fields,
                "UNCHANGED_FIELDS": unchanged_fields,
            },
            "REASON_AFFECTED_ROWS": dict(self.reason_rows),
            "REASON_AFFECTED_FIELDS": dict(self.reason_fields),
            "FIELD_GROUP_AFFECTED_ROWS": dict(self.field_group_affected_rows),
            "FIELD_GROUP_CHANGED_FIELDS": dict(self.field_group_changed_fields),
            "FIELD_GROUP_TOTAL_FIELDS": group_totals,
            "WHITESPACE": {
                "TAB_NORMALIZED_FIELDS": self.reason_fields["TAB_NORMALIZED"],
                "LINEBREAK_NORMALIZED_FIELDS": self.reason_fields[
                    "LINEBREAK_NORMALIZED"
                ],
                "UNICODE_WHITESPACE_NORMALIZED_FIELDS": self.reason_fields[
                    "UNICODE_WHITESPACE_NORMALIZED"
                ],
                "WHITESPACE_COLLAPSED_FIELDS": self.reason_fields[
                    "WHITESPACE_COLLAPSED"
                ],
                "WHITESPACE_TRIMMED_FIELDS": self.reason_fields["WHITESPACE_TRIMMED"],
                "WHITESPACE_ONLY_TO_EMPTY_FIELDS": self.reason_fields[
                    "WHITESPACE_ONLY_TO_EMPTY"
                ],
            },
            "UNICODE_ENCODING": {
                "UNICODE_NFC_NORMALIZED_FIELDS": self.reason_fields[
                    "UNICODE_NFC_NORMALIZED"
                ],
                "ENCODING_REPAIRED_FIELDS": self.reason_fields["ENCODING_REPAIRED"],
                "TERMINAL_ESCAPE_REMOVED_FIELDS": self.reason_fields[
                    "TERMINAL_ESCAPE_REMOVED"
                ],
                "BOM_REMOVED_FIELDS": self.reason_fields["BOM_REMOVED"],
                "CONTROL_CHARACTER_REMOVED_FIELDS": self.reason_fields[
                    "CONTROL_CHARACTER_REMOVED"
                ],
            },
            "PUNCTUATION": {"PUNCTUATION_CHANGED_FIELDS": 0},
            "OUTPUT_EFFECTS": {
                "CLEAN_VALUES_BECAME_EMPTY": self.clean_values_became_empty,
                "MAX_LENGTH_INCREASE_CODEPOINTS": self.max_length_increase,
                "MAX_LENGTH_DECREASE_CODEPOINTS": self.max_length_decrease,
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


def _fail(code: str, message: str) -> NoReturn:
    raise Stage03ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be lowercase canonical SHA-256 text")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 3 path names HOLDOUT")


def validate_stage03_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not the pinned version")
    if unicodedata.unidata_version != EXPECTED_UNICODE_VERSION:
        _fail("UNICODE_VERSION_MISMATCH", "Unicode runtime is not the pinned version")
    if ftfy.__version__ != EXPECTED_FTFY_VERSION:
        _fail("FTFY_VERSION_MISMATCH", "ftfy runtime is not the pinned version")
    if pa.__version__ != EXPECTED_PYARROW_VERSION:
        _fail("PYARROW_VERSION_MISMATCH", "PyArrow runtime is not the pinned version")
    if FTFY_CONFIG != TextFixerConfig(
        unescape_html=False,
        remove_terminal_escapes=False,
        fix_encoding=True,
        restore_byte_a0=False,
        replace_lossy_sequences=False,
        decode_inconsistent_utf8=False,
        fix_c1_controls=True,
        fix_latin_ligatures=False,
        fix_character_width=False,
        uncurl_quotes=False,
        fix_line_breaks=False,
        fix_surrogates=False,
        remove_control_chars=False,
        normalization=None,
        max_decode_length=1_000_000,
        explain=True,
    ):
        _fail("FTFY_PROFILE_MISMATCH", "ftfy configuration is not exact")


def clean_stage03_text(value: str) -> CleanTextResult:
    """Apply the complete conservative Stage 3 profile to one source string."""
    if not isinstance(value, str):
        _fail("INVALID_CLEANING_INPUT", "Stage 3 cleaning input must be a string")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage03ValidationError(
            "INVALID_CLEANING_INPUT", "Stage 3 input is not valid Unicode text"
        ) from error

    reasons: list[str] = []
    try:
        encoding_result = fix_encoding_and_explain(value, config=FTFY_CONFIG)
    except (UnicodeError, ValueError) as error:
        raise Stage03ValidationError(
            "ENCODING_REPAIR_FAILURE", "Conservative encoding repair failed"
        ) from error
    current = encoding_result.text
    if current != value:
        if not encoding_result.explanation:
            _fail("FTFY_AUDIT_FAILURE", "ftfy changed text without an explanation")
        reasons.append("ENCODING_REPAIRED")

    updated = remove_terminal_escapes(current)
    if updated != current:
        reasons.append("TERMINAL_ESCAPE_REMOVED")
        current = updated

    updated = "".join(
        character for character in current if ord(character) not in _REMOVABLE_CONTROLS
    )
    if updated != current:
        reasons.append("CONTROL_CHARACTER_REMOVED")
        current = updated

    whitespace_only = bool(current) and all(
        ord(character) in _UNICODE_WHITE_SPACE for character in current
    )
    if "\t" in current:
        reasons.append("TAB_NORMALIZED")
    if any(ord(character) in _LINEBREAKS for character in current):
        reasons.append("LINEBREAK_NORMALIZED")
    if any(ord(character) in _OTHER_UNICODE_WHITE_SPACE for character in current):
        reasons.append("UNICODE_WHITESPACE_NORMALIZED")
    current = "".join(
        " " if ord(character) in _UNICODE_WHITE_SPACE else character
        for character in current
    )

    updated = _MULTIPLE_SPACES_RE.sub(" ", current)
    if updated != current:
        reasons.append("WHITESPACE_COLLAPSED")
        current = updated

    whitespace_trimmed = False
    bom_removed = False
    while True:
        previous = current
        updated = current.strip(" ")
        if updated != current:
            whitespace_trimmed = True
            current = updated
        updated = current.lstrip("\ufeff").rstrip("\ufeff")
        if updated != current:
            bom_removed = True
            current = updated
        if current == previous:
            break
    if whitespace_trimmed:
        reasons.append("WHITESPACE_TRIMMED")
    if whitespace_only and current == "":
        reasons.append("WHITESPACE_ONLY_TO_EMPTY")
    if bom_removed:
        reasons.append("BOM_REMOVED")

    updated = unicodedata.normalize("NFC", current)
    if updated != current:
        reasons.append("UNICODE_NFC_NORMALIZED")
        current = updated

    try:
        current.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage03ValidationError(
            "INVALID_CLEANING_OUTPUT", "Stage 3 output is not valid Unicode text"
        ) from error
    if tuple(sorted(set(reasons), key=REASON_CODES.index)) != tuple(reasons):
        _fail("CHANGE_REASON_ORDER_MISMATCH", "Change reasons are not canonical")
    if (current == value) != (not reasons):
        _fail("CHANGE_AUDIT_MISMATCH", "Change reasons do not match the clean value")
    return CleanTextResult(current, tuple(reasons))


def stage03_schema() -> pa.Schema:
    fields = list(stage02_schema())
    fields.extend(
        pa.field(name, pa.string(), nullable=False) for name in CLEAN_DERIVED_COLUMNS
    )
    fields.extend(
        (
            pa.field("stage03_change_details", CHANGE_DETAILS_TYPE, nullable=False),
            pa.field("stage03_row_changed", pa.bool_(), nullable=False),
        )
    )
    return pa.schema(fields)


def _fingerprint_schema(schema: pa.Schema) -> str:
    digest = hashlib.sha256(STAGE03_SCHEMA_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE03_SCHEMA_VERSION)
    encoder.uint64(len(schema))
    for schema_field in schema.remove_metadata():
        encoder.text(schema_field.name)
        encoder.text(str(schema_field.type))
        encoder.text(str(schema_field.nullable).lower())
    return digest.hexdigest()


def stage03_schema_fingerprint() -> str:
    return _fingerprint_schema(stage03_schema())


def validate_stage03_input_binding(binding: Stage03InputBinding) -> None:
    if binding.upstream_contract_version != STAGE02_CONTRACT_VERSION:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "Stage 2 contract version is not exact")
    if binding.upstream_schema_fingerprint != stage02_schema_fingerprint():
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 2 schema fingerprint is not exact")
    for digest in (
        binding.upstream_logical_identity_sha256,
        binding.upstream_schema_fingerprint,
        binding.upstream_manifest_sha256,
        binding.input_benchmark_fingerprint,
    ):
        _digest_bytes(digest)
    if (
        isinstance(binding.expected_row_count, bool)
        or binding.expected_row_count < 1
        or binding.expected_row_count > 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail("INVALID_ROW_COUNT", "Stage 3 expected row count is invalid")


def stage03_logical_dataset_sha256_v1(binding: Stage03InputBinding) -> str:
    validate_stage03_input_binding(binding)
    digest = hashlib.sha256(STAGE03_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        STAGE03_CONTRACT_VERSION,
        STAGE03_PROFILE_VERSION,
        STAGE03_SCHEMA_VERSION,
        EXPECTED_UNICODE_VERSION,
        EXPECTED_FTFY_VERSION,
        binding.upstream_contract_version,
    ):
        encoder.text(value)
    for value in CLEAN_SOURCE_COLUMNS:
        encoder.text(value)
    for value in CLEAN_DERIVED_COLUMNS:
        encoder.text(value)
    for value in REASON_CODES:
        encoder.text(value)
    for value in (
        "NFC",
        "NO_PUNCTUATION_TRANSFORM",
        repr(FTFY_CONFIG),
    ):
        encoder.text(value)
    encoder.digest(binding.upstream_logical_identity_sha256)
    encoder.digest(binding.upstream_schema_fingerprint)
    encoder.digest(binding.input_benchmark_fingerprint)
    encoder.digest(stage03_schema_fingerprint())
    encoder.uint64(binding.expected_row_count)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage03ValidationError(
            "CONTROLLED_WRITE_FAILURE",
            "Controlled Stage 3 artifact could not be written",
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


def write_stage03_input_binding(path: Path, binding: Stage03InputBinding) -> str:
    validate_stage03_input_binding(binding)
    _reject_holdout_paths(path)
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 3 input binding already exists")
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


def load_stage03_input_binding(
    path: Path, *, expected_sha256: str
) -> Stage03InputBinding:
    _digest_bytes(expected_sha256)
    _reject_holdout_paths(path)
    _require_regular_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Input binding SHA-256 differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    if (
        set(value)
        != {
            "stage03_input_binding_version",
            "upstream_contract_version",
            "upstream_logical_identity_sha256",
            "upstream_schema_fingerprint",
            "upstream_manifest_sha256",
            "input_benchmark_fingerprint",
            "expected_row_count",
        }
        or value.get("stage03_input_binding_version") != STAGE03_INPUT_BINDING_VERSION
    ):
        _fail("INPUT_BINDING_INVALID", "Stage 3 input binding fields are not exact")
    binding = Stage03InputBinding(
        upstream_contract_version=_required_text(
            value.get("upstream_contract_version"), "INPUT_BINDING_INVALID"
        ),
        upstream_logical_identity_sha256=_required_text(
            value.get("upstream_logical_identity_sha256"), "INPUT_BINDING_INVALID"
        ),
        upstream_schema_fingerprint=_required_text(
            value.get("upstream_schema_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        upstream_manifest_sha256=_required_text(
            value.get("upstream_manifest_sha256"), "INPUT_BINDING_INVALID"
        ),
        input_benchmark_fingerprint=_required_text(
            value.get("input_benchmark_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        expected_row_count=_required_uint(
            value.get("expected_row_count"), "INPUT_BINDING_INVALID"
        ),
    )
    validate_stage03_input_binding(binding)
    return binding


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage03ValidationError(code, "Controlled JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON is not an object")
    return cast(dict[str, Any], value)


def _require_regular_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage03ValidationError(
            code, "Required artifact is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Required artifact is not a regular non-symlink file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage03ValidationError(
            code, "Required directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Required directory is not a regular non-symlink directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage03ValidationError(
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
        raise Stage03ValidationError(
            "ARTIFACT_READ_FAILURE", "Controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _output_metadata(
    binding: Stage03InputBinding, logical_fingerprint: str
) -> dict[bytes, bytes]:
    values = {
        "stage03_contract_version": STAGE03_CONTRACT_VERSION,
        "stage03_profile_version": STAGE03_PROFILE_VERSION,
        "stage03_schema_version": STAGE03_SCHEMA_VERSION,
        "stage03_schema_fingerprint": stage03_schema_fingerprint(),
        "stage03_logical_dataset_sha256_v1": logical_fingerprint,
        "upstream_stage02_contract_version": binding.upstream_contract_version,
        "upstream_stage02_logical_identity_sha256": (
            binding.upstream_logical_identity_sha256
        ),
        "upstream_stage02_schema_fingerprint": binding.upstream_schema_fingerprint,
        "upstream_stage02_manifest_sha256": binding.upstream_manifest_sha256,
        "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
        "unicode_normalization": "NFC",
        "unicode_version": EXPECTED_UNICODE_VERSION,
        "ftfy_version": EXPECTED_FTFY_VERSION,
        "punctuation_policy": "NO_PUNCTUATION_TRANSFORM",
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _project_batch(
    batch: pa.RecordBatch,
    *,
    metadata: Mapping[bytes, bytes],
    metrics: Stage03Metrics | None,
) -> pa.RecordBatch:
    if not batch.schema.remove_metadata().equals(
        stage02_schema(), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 3 input batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("UPSTREAM_NULL", "Stage 3 input contains an unexpected null")

    source_values = {
        name: batch.column(batch.schema.get_field_index(name)).to_pylist()
        for name in CLEAN_SOURCE_COLUMNS
    }
    clean_values: dict[str, list[str]] = {name: [] for name in CLEAN_SOURCE_COLUMNS}
    change_details: list[list[dict[str, object]]] = []
    row_changed_flags: list[bool] = []
    for row_index in range(batch.num_rows):
        raw_row: list[str] = []
        result_row: list[CleanTextResult] = []
        details_row: list[dict[str, object]] = []
        for source_name in CLEAN_SOURCE_COLUMNS:
            raw = source_values[source_name][row_index]
            if not isinstance(raw, str):
                _fail("UPSTREAM_TYPE_MISMATCH", "Stage 3 source value is not text")
            result = clean_stage03_text(raw)
            second = clean_stage03_text(result.value)
            if second.value != result.value or second.reason_codes:
                if metrics is not None:
                    metrics.idempotence_failures += 1
                _fail("IDEMPOTENCE_FAILURE", "Stage 3 cleaning is not idempotent")
            raw_row.append(raw)
            result_row.append(result)
            clean_values[source_name].append(result.value)
            if result.reason_codes:
                details_row.append(
                    {
                        "field_name": source_name,
                        "reason_codes": list(result.reason_codes),
                    }
                )
        if metrics is not None:
            metrics.observe_row(raw_values=raw_row, results=result_row)
        change_details.append(details_row)
        row_changed_flags.append(bool(details_row))

    arrays: list[pa.Array] = [batch.column(index) for index in range(batch.num_columns)]
    arrays.extend(
        pa.array(clean_values[name], type=pa.string(), from_pandas=False, safe=True)
        for name in CLEAN_SOURCE_COLUMNS
    )
    arrays.extend(
        (
            pa.array(
                change_details,
                type=CHANGE_DETAILS_TYPE,
                from_pandas=False,
                safe=True,
            ),
            pa.array(row_changed_flags, type=pa.bool_(), from_pandas=False, safe=True),
        )
    )
    return pa.RecordBatch.from_arrays(
        arrays, schema=stage03_schema().with_metadata(dict(metadata))
    )


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
                "standard_has_nonempty_source_line",
                "native_has_nonempty_source_line",
                "standard_nonempty_source_line_count",
                "native_nonempty_source_line_count",
                "stage03_row_changed",
            ],
            write_page_checksum=True,
            store_schema=True,
            use_compliant_nested_type=True,
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage03ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 3 Parquet writer could not start"
        ) from error
    path.chmod(0o600)
    return writer


def _stage02_artifacts(
    root: Path, binding: Stage03InputBinding
) -> tuple[Stage03ArtifactIdentity, ...]:
    _reject_holdout_paths(root)
    try:
        outcome = validate_stage02_bundle(
            root, expected_manifest_sha256=binding.upstream_manifest_sha256
        )
    except Stage02ValidationError as error:
        raise Stage03ValidationError(
            "STAGE02_BUNDLE_INVALID", "Accepted Stage 2 bundle validation failed"
        ) from error
    if outcome.logical_dataset_sha256_v1 != binding.upstream_logical_identity_sha256:
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 logical identity differs")
    manifest = _load_json(root / STAGE02_MANIFEST_NAME, "STAGE02_MANIFEST_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 manifest identity is malformed")
    if (
        scientific.get("stage02_contract_version") != binding.upstream_contract_version
        or scientific.get("stage02_schema_fingerprint")
        != binding.upstream_schema_fingerprint
        or scientific.get("stage02_logical_dataset_sha256_v1")
        != binding.upstream_logical_identity_sha256
        or scientific.get("upstream_logical_identity_sha256")
        != binding.input_benchmark_fingerprint
        or scientific.get("row_count") != binding.expected_row_count
    ):
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 scientific binding differs")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 artifacts are absent")
    artifacts: list[Stage03ArtifactIdentity] = []
    for expected_sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE02_MANIFEST_INVALID", "Stage 2 artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE02_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{expected_sequence:06d}.parquet":
            _fail("STAGE02_MANIFEST_INVALID", "Stage 2 artifact order is not exact")
        artifact = Stage03ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE02_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE02_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE02_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        artifacts.append(artifact)
    return tuple(artifacts)


def _input_artifact_snapshot(
    root: Path, artifact: Stage03ArtifactIdentity
) -> tuple[Path, tuple[int, int, int, int, str]]:
    path = root / artifact.relative_path
    _require_regular_file(path, "STAGE02_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    observed = path.stat(follow_symlinks=False)
    sha256 = _sha256_file(path)
    if observed.st_size != artifact.size_bytes or sha256 != artifact.sha256:
        _fail("STAGE02_ARTIFACT_MISMATCH", "Stage 2 artifact identity differs")
    return path, (
        observed.st_dev,
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
        sha256,
    )


def _assert_input_unchanged(
    path: Path,
    before: tuple[int, int, int, int, str],
    expected_sha256: str,
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
        _fail("INPUT_CHANGED", "Stage 2 input changed during Stage 3")


def _write_output_shard(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    metadata: Mapping[bytes, bytes],
    metrics: Stage03Metrics,
    seen_stable_ids: set[bytes],
) -> int:
    try:
        parquet = pq.ParquetFile(input_path, page_checksum_verification=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            stage02_schema(), check_metadata=False
        ):
            _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 2 Parquet schema is not exact")
        batches = parquet.iter_batches(batch_size=batch_rows, use_threads=False)
    except Stage03ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage03ValidationError(
            "PARQUET_READ_FAILURE", "Stage 2 input could not be opened safely"
        ) from error
    writer = _new_writer(output_path, stage03_schema().with_metadata(dict(metadata)))
    rows = 0
    try:
        for batch in batches:
            stable_ids = batch.column(
                batch.schema.get_field_index("stable_source_row_id_v1")
            ).to_pylist()
            for identity in stable_ids:
                if not isinstance(identity, bytes) or len(identity) != 32:
                    _fail("INVALID_STABLE_IDENTITY", "Stable identity is malformed")
                if identity in seen_stable_ids:
                    _fail("DUPLICATE_STABLE_IDENTITY", "Stable identity is duplicated")
                seen_stable_ids.add(identity)
            projected = _project_batch(batch, metadata=metadata, metrics=metrics)
            writer.write_batch(projected, row_group_size=projected.num_rows)
            rows += projected.num_rows
        writer.close()
    except Stage03ValidationError:
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
        raise Stage03ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 3 Parquet output could not be written"
        ) from error
    output_path.chmod(0o600)
    return rows


def _assert_input_output_equal(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    metadata: Mapping[bytes, bytes],
) -> None:
    try:
        input_file = pq.ParquetFile(input_path, page_checksum_verification=True)
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        expected_schema = stage03_schema().with_metadata(dict(metadata))
        if not output_file.schema_arrow.equals(expected_schema, check_metadata=True):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 3 output schema is not exact")
        input_batches = input_file.iter_batches(
            batch_size=batch_rows, use_threads=False
        )
        output_batches = output_file.iter_batches(
            batch_size=batch_rows, use_threads=False
        )
        sentinel = object()
        for raw_batch, output_batch in zip_longest(
            input_batches, output_batches, fillvalue=sentinel
        ):
            if raw_batch is sentinel or output_batch is sentinel:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 3 batch topology differs")
            assert isinstance(raw_batch, pa.RecordBatch)
            assert isinstance(output_batch, pa.RecordBatch)
            expected = _project_batch(raw_batch, metadata=metadata, metrics=None)
            if not expected.equals(output_batch, check_metadata=True):
                _fail(
                    "OUTPUT_VALUE_MISMATCH",
                    "Stage 3 output differs from deterministic input projection",
                )
    except Stage03ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage03ValidationError(
            "PARQUET_READBACK_FAILURE", "Stage 3 independent read-back failed"
        ) from error


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage03ArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "STAGE03_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage03ArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize_stage03(config: Stage03RunConfig) -> Stage03MaterializationOutcome:
    """Materialize conservative clean derived values for an exact Stage 2 bundle."""
    config.validate()
    validate_stage03_runtime()
    if config.production:
        require_goethe_nhr_slurm("stage03-safe-text-cleaning")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 3 output directory already exists")
    binding = load_stage03_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
    )
    artifacts = _stage02_artifacts(config.stage02_output_directory, binding)
    logical_fingerprint = stage03_logical_dataset_sha256_v1(binding)
    metadata = _output_metadata(binding, logical_fingerprint)

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE03_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 3 temporary output already exists")
    temporary.mkdir(mode=0o700)
    data_directory = temporary / "data"
    data_directory.mkdir(mode=0o700)
    _write_json_exclusive(
        temporary / STAGE03_IN_PROGRESS_MARKER,
        {"status": "STAGE03_INCOMPLETE"},
    )

    metrics = Stage03Metrics()
    seen_stable_ids: set[bytes] = set()
    output_artifacts: list[Stage03ArtifactIdentity] = []
    for sequence_number, artifact in enumerate(artifacts, start=1):
        input_path, before = _input_artifact_snapshot(
            config.stage02_output_directory, artifact
        )
        relative_output = f"data/part-{sequence_number:06d}.parquet"
        output_path = temporary / relative_output
        rows = _write_output_shard(
            input_path,
            output_path,
            batch_rows=config.batch_rows,
            metadata=metadata,
            metrics=metrics,
            seen_stable_ids=seen_stable_ids,
        )
        _assert_input_output_equal(
            input_path,
            output_path,
            batch_rows=config.batch_rows,
            metadata=metadata,
        )
        _assert_input_unchanged(input_path, before, artifact.sha256)
        if rows != artifact.row_count:
            _fail("ROW_COUNT_MISMATCH", "Stage 3 shard row count differs")
        output_artifacts.append(
            _artifact_identity(temporary, relative_output, row_count=rows)
        )

    if metrics.output_rows != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 3 total row count differs")
    if len(seen_stable_ids) != binding.expected_row_count:
        _fail("DUPLICATE_STABLE_IDENTITY", "Stable identity count is not exact")
    if metrics.idempotence_failures:
        _fail("IDEMPOTENCE_FAILURE", "Stage 3 idempotence validation failed")
    metric_groups = metrics.to_metric_groups()
    manifest = {
        "stage03_manifest_version": STAGE03_MANIFEST_VERSION,
        "status": "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED",
        "scientific_identity": {
            "stage03_contract_version": STAGE03_CONTRACT_VERSION,
            "stage03_profile_version": STAGE03_PROFILE_VERSION,
            "stage03_schema_version": STAGE03_SCHEMA_VERSION,
            "stage03_schema_fingerprint": stage03_schema_fingerprint(),
            "stage03_logical_dataset_sha256_v1": logical_fingerprint,
            "clean_source_columns": list(CLEAN_SOURCE_COLUMNS),
            "clean_derived_columns": list(CLEAN_DERIVED_COLUMNS),
            "reason_codes": list(REASON_CODES),
            "unicode_normalization": "NFC",
            "unicode_version": EXPECTED_UNICODE_VERSION,
            "ftfy_version": EXPECTED_FTFY_VERSION,
            "punctuation_policy": "NO_PUNCTUATION_TRANSFORM",
            "upstream_stage02_contract_version": binding.upstream_contract_version,
            "upstream_stage02_logical_identity_sha256": (
                binding.upstream_logical_identity_sha256
            ),
            "upstream_stage02_schema_fingerprint": (
                binding.upstream_schema_fingerprint
            ),
            "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
            "row_count": metrics.output_rows,
        },
        "development_metrics": metric_groups,
        "physical_identity": {
            "stage03_input_binding_sha256": config.expected_input_binding_sha256,
            "upstream_stage02_manifest_sha256": binding.upstream_manifest_sha256,
            "input_artifacts": [item.to_dict() for item in artifacts],
            "output_artifacts": [item.to_dict() for item in output_artifacts],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": STAGE03_VALIDATION_VERSION,
            "upstream_identity_schema_and_manifest": "PASS",
            "input_artifact_integrity": "PASS",
            "row_count_preserved": "PASS",
            "stable_source_row_id_preserved": "PASS",
            "all_stage02_fields_preserved": "PASS",
            "source_provenance_preserved": "PASS",
            "standard_native_independence": "PASS",
            "change_audit_consistency": "PASS",
            "idempotence_all_clean_values": "PASS",
            "parquet_page_checksum_readback": "PASS",
            "holdout_exclusion": "PASS",
            "atomic_publication": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "unicode_version": unicodedata.unidata_version,
            "pyarrow_version": pa.__version__,
            "ftfy_version": ftfy.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json_exclusive(temporary / STAGE03_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(
        temporary, STAGE03_MANIFEST_NAME, row_count=0
    )
    _write_json_exclusive(
        temporary / STAGE03_SUCCESS_MARKER,
        {
            "status": "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "stage03_manifest_sha256": manifest_identity.sha256,
            "stage03_manifest_size_bytes": manifest_identity.size_bytes,
            "stage03_input_binding_sha256": config.expected_input_binding_sha256,
            "stage03_logical_dataset_sha256_v1": logical_fingerprint,
            "stage03_schema_fingerprint": stage03_schema_fingerprint(),
            "row_count": metrics.output_rows,
            "output_shard_count": len(output_artifacts),
        },
    )
    (temporary / STAGE03_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(data_directory)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage03_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_identity.sha256,
    )


def _observed_topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            path = current / name
            if path.is_symlink():
                _fail("UNSAFE_OUTPUT", "Stage 3 output contains a symlink")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "UNSAFE_OUTPUT")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def _binding_from_manifest(manifest: Mapping[str, Any]) -> Stage03InputBinding:
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 identity is malformed")
    return Stage03InputBinding(
        upstream_contract_version=_required_text(
            scientific.get("upstream_stage02_contract_version"),
            "STAGE03_MANIFEST_INVALID",
        ),
        upstream_logical_identity_sha256=_required_text(
            scientific.get("upstream_stage02_logical_identity_sha256"),
            "STAGE03_MANIFEST_INVALID",
        ),
        upstream_schema_fingerprint=_required_text(
            scientific.get("upstream_stage02_schema_fingerprint"),
            "STAGE03_MANIFEST_INVALID",
        ),
        upstream_manifest_sha256=_required_text(
            physical.get("upstream_stage02_manifest_sha256"),
            "STAGE03_MANIFEST_INVALID",
        ),
        input_benchmark_fingerprint=_required_text(
            scientific.get("input_benchmark_fingerprint"),
            "STAGE03_MANIFEST_INVALID",
        ),
        expected_row_count=_required_uint(
            scientific.get("row_count"), "STAGE03_MANIFEST_INVALID"
        ),
    )


def _validated_metrics(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 metrics are malformed")
    expected_groups = set(Stage03Metrics().to_metric_groups())
    if set(value) != expected_groups:
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 metric groups are not exact")
    result: dict[str, dict[str, int]] = {}
    for group, raw_metrics in value.items():
        if not isinstance(group, str) or not isinstance(raw_metrics, dict):
            _fail("STAGE03_MANIFEST_INVALID", "Stage 3 metrics are malformed")
        metrics: dict[str, int] = {}
        for name, raw_count in raw_metrics.items():
            if (
                not isinstance(name, str)
                or not isinstance(raw_count, int)
                or isinstance(raw_count, bool)
                or raw_count < 0
            ):
                _fail("STAGE03_MANIFEST_INVALID", "Stage 3 metric value is invalid")
            metrics[name] = raw_count
        result[group] = metrics
    return result


def validate_stage03_bundle(
    output_directory: Path, *, expected_manifest_sha256: str
) -> Stage03MaterializationOutcome:
    """Independently validate an atomically published Stage 3 bundle."""
    validate_stage03_runtime()
    _digest_bytes(expected_manifest_sha256)
    _reject_holdout_paths(output_directory)
    _require_directory(output_directory, "STAGE03_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    if (output_directory / STAGE03_IN_PROGRESS_MARKER).exists():
        _fail("STAGE03_INCOMPLETE", "Stage 3 retains an in-progress marker")
    data_directory = output_directory / "data"
    _require_directory(data_directory, "STAGE03_OUTPUT_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    directories, files = _observed_topology(output_directory)
    if directories != {"data"}:
        _fail("STAGE03_ARTIFACT_MISMATCH", "Stage 3 directory topology is invalid")
    manifest_path = output_directory / STAGE03_MANIFEST_NAME
    success_path = output_directory / STAGE03_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE03_TERMINAL_MISSING")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE03_MANIFEST_SHA256_MISMATCH", "Stage 3 manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE03_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE03_SUCCESS_INVALID")
    if (
        manifest.get("stage03_manifest_version") != STAGE03_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage03_manifest_sha256") != manifest_sha
        or success.get("stage03_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
    ):
        _fail("STAGE03_TERMINAL_MISMATCH", "Stage 3 terminal state differs")
    binding = _binding_from_manifest(manifest)
    logical_fingerprint = stage03_logical_dataset_sha256_v1(binding)
    scientific = cast(dict[str, Any], manifest["scientific_identity"])
    physical = cast(dict[str, Any], manifest["physical_identity"])
    validation = manifest.get("validation")
    if (
        scientific.get("stage03_contract_version") != STAGE03_CONTRACT_VERSION
        or scientific.get("stage03_profile_version") != STAGE03_PROFILE_VERSION
        or scientific.get("stage03_schema_version") != STAGE03_SCHEMA_VERSION
        or scientific.get("stage03_schema_fingerprint") != stage03_schema_fingerprint()
        or scientific.get("stage03_logical_dataset_sha256_v1") != logical_fingerprint
        or scientific.get("clean_source_columns") != list(CLEAN_SOURCE_COLUMNS)
        or scientific.get("clean_derived_columns") != list(CLEAN_DERIVED_COLUMNS)
        or scientific.get("reason_codes") != list(REASON_CODES)
        or scientific.get("unicode_normalization") != "NFC"
        or scientific.get("unicode_version") != EXPECTED_UNICODE_VERSION
        or scientific.get("ftfy_version") != EXPECTED_FTFY_VERSION
        or scientific.get("punctuation_policy") != "NO_PUNCTUATION_TRANSFORM"
        or success.get("stage03_logical_dataset_sha256_v1") != logical_fingerprint
        or success.get("stage03_schema_fingerprint") != stage03_schema_fingerprint()
    ):
        _fail("STAGE03_FINGERPRINT_MISMATCH", "Stage 3 scientific identity differs")
    input_binding_sha = _required_text(
        physical.get("stage03_input_binding_sha256"), "STAGE03_MANIFEST_INVALID"
    )
    _digest_bytes(input_binding_sha)
    if success.get("stage03_input_binding_sha256") != input_binding_sha:
        _fail("STAGE03_TERMINAL_MISMATCH", "Stage 3 input binding differs")
    if physical.get("owner_only_permissions") is not True:
        _fail("STAGE03_MANIFEST_INVALID", "Owner-only evidence is missing")
    if not isinstance(validation, dict) or any(
        value != "PASS"
        for key, value in validation.items()
        if key != "validation_contract_version"
    ):
        _fail("STAGE03_VALIDATION_INCOMPLETE", "Stage 3 validation is incomplete")
    if validation.get("validation_contract_version") != STAGE03_VALIDATION_VERSION:
        _fail("STAGE03_VALIDATION_INCOMPLETE", "Stage 3 validation version differs")

    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifacts are absent")
    output_artifacts: list[Stage03ArtifactIdentity] = []
    expected_files = {STAGE03_MANIFEST_NAME, STAGE03_SUCCESS_MARKER}
    for expected_sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE03_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{expected_sequence:06d}.parquet":
            _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifact order differs")
        artifact = Stage03ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE03_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE03_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE03_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        output_artifacts.append(artifact)
        expected_files.add(relative_path)
    if files != expected_files:
        _fail("STAGE03_ARTIFACT_MISMATCH", "Stage 3 artifact topology is incomplete")

    expected_metadata = _output_metadata(binding, logical_fingerprint)
    observed_metrics = Stage03Metrics()
    seen_stable_ids: set[bytes] = set()
    for artifact in output_artifacts:
        path = output_directory / artifact.relative_path
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("STAGE03_ARTIFACT_MISMATCH", "Stage 3 artifact identity differs")
        try:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            expected_schema = stage03_schema().with_metadata(expected_metadata)
            if not parquet.schema_arrow.equals(expected_schema, check_metadata=True):
                _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 3 output schema is not exact")
            shard_rows = 0
            for output_batch in parquet.iter_batches(
                batch_size=2_048, use_threads=False
            ):
                raw_batch = pa.RecordBatch.from_arrays(
                    [
                        output_batch.column(index)
                        for index in range(len(stage02_schema()))
                    ],
                    schema=stage02_schema(),
                )
                expected = _project_batch(
                    raw_batch, metadata=expected_metadata, metrics=observed_metrics
                )
                if not expected.equals(output_batch, check_metadata=True):
                    _fail(
                        "OUTPUT_VALUE_MISMATCH",
                        "Stage 3 values or change evidence are inconsistent",
                    )
                stable_values = raw_batch.column(
                    raw_batch.schema.get_field_index("stable_source_row_id_v1")
                ).to_pylist()
                for identity in stable_values:
                    if not isinstance(identity, bytes) or len(identity) != 32:
                        _fail("INVALID_STABLE_IDENTITY", "Stable identity is malformed")
                    if identity in seen_stable_ids:
                        _fail(
                            "DUPLICATE_STABLE_IDENTITY", "Stable identity is duplicated"
                        )
                    seen_stable_ids.add(identity)
                shard_rows += output_batch.num_rows
            if shard_rows != artifact.row_count:
                _fail("ROW_COUNT_MISMATCH", "Stage 3 shard row count differs")
        except Stage03ValidationError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise Stage03ValidationError(
                "PARQUET_READBACK_FAILURE", "Stage 3 page-checksum read-back failed"
            ) from error
    if observed_metrics.output_rows != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 3 total row count differs")
    if len(seen_stable_ids) != binding.expected_row_count:
        _fail("DUPLICATE_STABLE_IDENTITY", "Stage 3 stable identity count differs")
    recorded_metrics = _validated_metrics(manifest.get("development_metrics"))
    if observed_metrics.to_metric_groups() != recorded_metrics:
        _fail("STAGE03_METRIC_MISMATCH", "Stage 3 aggregate metrics differ")
    if success.get("row_count") != observed_metrics.output_rows or success.get(
        "output_shard_count"
    ) != len(output_artifacts):
        _fail("STAGE03_TERMINAL_MISMATCH", "Stage 3 terminal counts differ")
    return Stage03MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=logical_fingerprint,
        schema_fingerprint=stage03_schema_fingerprint(),
        input_binding_sha256=input_binding_sha,
        manifest_sha256=manifest_sha,
        row_count=observed_metrics.output_rows,
        output_shard_count=len(output_artifacts),
        metrics=recorded_metrics,
    )


__all__ = [
    "CHANGE_DETAILS_TYPE",
    "CLEAN_DERIVED_COLUMNS",
    "CLEAN_SOURCE_COLUMNS",
    "EXPECTED_FTFY_VERSION",
    "EXPECTED_PYARROW_VERSION",
    "EXPECTED_PYTHON_VERSION",
    "EXPECTED_UNICODE_VERSION",
    "FIELD_GROUPS",
    "FIELD_GROUP_BY_COLUMN",
    "FTFY_CONFIG",
    "REASON_CODES",
    "STAGE03_CONTRACT_VERSION",
    "STAGE03_INPUT_BINDING_VERSION",
    "STAGE03_MANIFEST_NAME",
    "STAGE03_PROFILE_VERSION",
    "STAGE03_SCHEMA_VERSION",
    "CleanTextResult",
    "Stage03InputBinding",
    "Stage03MaterializationOutcome",
    "Stage03RunConfig",
    "Stage03ValidationError",
    "clean_stage03_text",
    "load_stage03_input_binding",
    "materialize_stage03",
    "stage03_logical_dataset_sha256_v1",
    "stage03_schema",
    "stage03_schema_fingerprint",
    "validate_stage03_bundle",
    "validate_stage03_input_binding",
    "validate_stage03_runtime",
    "write_stage03_input_binding",
]

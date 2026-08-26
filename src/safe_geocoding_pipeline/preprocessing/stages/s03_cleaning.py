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
from typing import Any, Iterable, Mapping, NoReturn, Protocol, Sequence, cast

import ftfy
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from ftfy import TextFixerConfig, chardata, fix_encoding_and_explain
from ftfy.fixes import remove_terminal_escapes

from ...execution_policy import require_goethe_nhr_slurm
from .s02_harmonization import (
    NATIVE_ADDRESS_COLUMNS,
    STANDARD_ADDRESS_COLUMNS,
    STAGE02_CONTRACT_VERSION,
    STAGE02_IN_PROGRESS_MARKER,
    STAGE02_MANIFEST_NAME,
    STAGE02_SCHEMA_VERSION,
    STAGE02_SUCCESS_MARKER,
    STAGE02_VALIDATION_VERSION,
    stage02_schema,
    stage02_schema_fingerprint,
)

STAGE03_CONTRACT_VERSION = "stage03_safe_text_cleaning_contract_v1"
STAGE03_PROFILE_VERSION = "stage03_safe_text_cleaning_profile_v1"
STAGE03_INPUT_BINDING_VERSION = "stage03_input_binding_v1"
STAGE03_SCHEMA_VERSION = "stage03_canonical_clean_text_schema_v1"
STAGE03_VALIDATION_VERSION = "stage03_bundle_validation_v2"
STAGE03_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE03_LOGICAL_DATASET_V1"
STAGE03_SCHEMA_FINGERPRINT_DOMAIN = b"SAFE_STAGE03_ARROW_SCHEMA_V1"
STAGE03_MANIFEST_VERSION = "stage03_manifest_v2"
STAGE03_ORDERED_IDENTITY_VERSION = "stage03_ordered_stable_identity_sha256_v1"
STAGE03_ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
STAGE03_PUNCTUATION_POLICY = "NO_SEMANTIC_PUNCTUATION_NORMALIZATION"
DEFAULT_TARGET_BATCH_BYTES = 256 * 1024 * 1024

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
_ASCII_DIRTY_RE = re.compile(r"[\x00-\x1f\x7f]|^ | $| {2}")
_ASCII_DIRTY_ARROW_PATTERN = r"[\x00-\x1f\x7f]|^ | $| {2}"
_REMOVABLE_CONTROLS_RE = re.compile(r"[\x00-\x08\x0e-\x1f\x7f-\x84\x86-\x9f]")
_LINEBREAK_RE = re.compile(r"[\x0a-\x0d\x85\u2028\u2029]")
_OTHER_UNICODE_WHITESPACE_RE = re.compile(
    r"[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]"
)
_UNICODE_WHITESPACE_ONLY_RE = re.compile(
    r"[\x09-\x0d\x20\x85\u00a0\u1680\u2000-\u200a\u2028"
    r"\u2029\u202f\u205f\u3000]+"
)
_UNICODE_16_PUNCTUATION_ABSENT_FROM_ARROW_25 = (
    0x1B4E,
    0x1B4F,
    0x1B7F,
    0x10D6E,
    0x113D4,
    0x113D5,
    0x113D7,
    0x113D8,
    0x11BE1,
    0x16D6D,
    0x16D6E,
    0x16D6F,
    0x1E5FF,
)
_NON_PUNCTUATION_ARROW_PATTERN = (
    r"[^\p{P}"
    + "".join(
        rf"\x{{{codepoint:x}}}"
        for codepoint in _UNICODE_16_PUNCTUATION_ABSENT_FROM_ARROW_25
    )
    + r"]+"
)
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
_CLEAN_TRANSLATION = str.maketrans(
    {
        **{codepoint: None for codepoint in _REMOVABLE_CONTROLS},
        **{codepoint: " " for codepoint in _UNICODE_WHITE_SPACE if codepoint != 0x0020},
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


@dataclass(frozen=True, slots=True)
class Stage03ScientificEquivalenceOutcome:
    row_count: int
    cleaned_field_count: int
    row_identity_equal: bool
    incoming_stage02_equal: bool
    clean_values_equal: bool
    row_changed_equal: bool
    reason_codes_equal: bool


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
    punctuation_codepoint_changed_fields: int = 0
    punctuation_codepoint_changed_in_encoding_repaired_fields: int = 0
    punctuation_codepoint_changed_without_encoding_repair_fields: int = 0
    ascii_fast_path_values: int = 0
    full_profile_invocations: int = 0
    idempotence_recheck_invocations: int = 0
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

    def observe_batch_shape(
        self, *, row_count: int, ascii_fast_path_values: int
    ) -> None:
        if row_count < 0 or not 0 <= ascii_fast_path_values <= (
            row_count * len(CLEAN_SOURCE_COLUMNS)
        ):
            _fail("INTERNAL_METRIC_ERROR", "Cleaning batch metrics are invalid")
        field_count = row_count * len(CLEAN_SOURCE_COLUMNS)
        self.input_rows += row_count
        self.output_rows += row_count
        self.total_cleaned_fields += field_count
        self.ascii_fast_path_values += ascii_fast_path_values
        self.full_profile_invocations += field_count - ascii_fast_path_values

    def observe_changed_field(
        self,
        *,
        column: str,
        raw: str,
        clean: str,
        reasons: Sequence[str],
        punctuation_codepoints_changed: bool,
    ) -> None:
        if column not in CLEAN_SOURCE_COLUMNS or raw == clean or not reasons:
            _fail("INTERNAL_METRIC_ERROR", "Changed-field metrics are invalid")
        self.changed_fields += 1
        self.idempotence_recheck_invocations += 1
        self.field_group_changed_fields[FIELD_GROUP_BY_COLUMN[column]] += 1
        self.reason_fields.update(reasons)
        if raw != "" and clean == "":
            self.clean_values_became_empty += 1
        delta = len(clean) - len(raw)
        self.max_length_increase = max(self.max_length_increase, delta)
        self.max_length_decrease = max(self.max_length_decrease, -delta)
        if punctuation_codepoints_changed:
            self.punctuation_codepoint_changed_fields += 1
            if "ENCODING_REPAIRED" in reasons:
                self.punctuation_codepoint_changed_in_encoding_repaired_fields += 1
            else:
                self.punctuation_codepoint_changed_without_encoding_repair_fields += 1

    def observe_changed_row(self, *, reasons: set[str], groups: set[str]) -> None:
        self.rows_changed += 1
        self.reason_rows.update(reasons)
        self.field_group_affected_rows.update(groups)

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
            "PUNCTUATION": {
                "SEMANTIC_PUNCTUATION_NORMALIZATION_FIELDS": 0,
                "PUNCTUATION_CODEPOINT_CHANGED_FIELDS": (
                    self.punctuation_codepoint_changed_fields
                ),
                "PUNCTUATION_CODEPOINT_CHANGED_IN_ENCODING_REPAIRED_FIELDS": (
                    self.punctuation_codepoint_changed_in_encoding_repaired_fields
                ),
                "PUNCTUATION_CODEPOINT_CHANGED_WITHOUT_ENCODING_REPAIR_FIELDS": (
                    self.punctuation_codepoint_changed_without_encoding_repair_fields
                ),
            },
            "CLEANER_EFFICIENCY": {
                "TOTAL_FIELD_VALUES": self.total_cleaned_fields,
                "ASCII_FAST_PATH_VALUES": self.ascii_fast_path_values,
                "FULL_PROFILE_INVOCATIONS": self.full_profile_invocations,
                "IDEMPOTENCE_RECHECK_INVOCATIONS": (
                    self.idempotence_recheck_invocations
                ),
                "READBACK_CLEANER_INVOCATIONS": 0,
                "TERMINAL_VALIDATION_CLEANER_INVOCATIONS": 0,
                "REPORTING_CLEANER_INVOCATIONS": 0,
            },
            "OUTPUT_EFFECTS": {
                "CLEAN_VALUES_BECAME_EMPTY": self.clean_values_became_empty,
                "MAX_LENGTH_INCREASE_CODEPOINTS": self.max_length_increase,
                "MAX_LENGTH_DECREASE_CODEPOINTS": self.max_length_decrease,
                "IDEMPOTENCE_FAILURES": self.idempotence_failures,
            },
        }


@dataclass(slots=True)
class _ProjectionStats:
    total_field_values: int = 0
    ascii_fast_path_values: int = 0
    full_profile_invocations: int = 0
    idempotence_recheck_invocations: int = 0

    def validate_against(self, metrics: Stage03Metrics) -> None:
        if (
            self.total_field_values != metrics.total_cleaned_fields
            or self.ascii_fast_path_values != metrics.ascii_fast_path_values
            or self.full_profile_invocations != metrics.full_profile_invocations
            or self.idempotence_recheck_invocations
            != metrics.idempotence_recheck_invocations
        ):
            _fail(
                "CLEANER_INVOCATION_MISMATCH",
                "Recorded cleaner invocations differ from independent output evidence",
            )


class _OrderedStableIdentityHasher:
    """Bound an ordered identity stream without retaining individual identities."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256(STAGE03_ORDERED_IDENTITY_DOMAIN)
        self.row_count = 0

    def update(self, values: pa.Array) -> None:
        if (
            not pa.types.is_fixed_size_binary(values.type)
            or values.type.byte_width != 32
        ):
            _fail("INVALID_STABLE_IDENTITY", "Stable identity type is not exact")
        if values.null_count:
            _fail("INVALID_STABLE_IDENTITY", "Stable identity contains a null")
        data_buffer = values.buffers()[1]
        if data_buffer is None:
            _fail("INVALID_STABLE_IDENTITY", "Stable identity storage is absent")
        offset = values.offset * 32
        length = len(values) * 32
        self._digest.update(data_buffer.slice(offset, length).to_pybytes())
        self.row_count += len(values)

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return digest.hexdigest()


def ordered_stable_identity_sha256_v1(chunks: Iterable[pa.Array]) -> str:
    """Return the deterministic digest of ordered fixed-size stable IDs."""
    hasher = _OrderedStableIdentityHasher()
    for chunk in chunks:
        hasher.update(chunk)
    return hasher.hexdigest()


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


def _is_clean_ascii_fast_path(value: str) -> bool:
    """Recognize values for which every v1 profile operation is provably a no-op."""
    return value.isascii() and _ASCII_DIRTY_RE.search(value) is None


def _clean_ascii_fast_path_mask(values: pa.Array) -> pa.Array:
    ascii_values = pc.string_is_ascii(values)
    dirty_values = pc.match_substring_regex(values, pattern=_ASCII_DIRTY_ARROW_PATTERN)
    return cast(pa.Array, pc.and_(ascii_values, pc.invert(dirty_values)))


def _ftfy_encoding_is_proven_noop(value: str) -> bool:
    """Skip ftfy only where its pinned encoding decision graph cannot change text."""
    if value.isascii():
        return True
    if len(value) <= FTFY_CONFIG.max_decode_length:
        return False
    if chardata.C1_CONTROL_RE.search(value) is not None:
        return False
    return not any(
        chardata.possible_encoding(value, encoding)
        for encoding in chardata.CHARMAP_ENCODINGS
    )


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

    if _is_clean_ascii_fast_path(value):
        return CleanTextResult(value, ())

    reasons: list[str] = []
    if _ftfy_encoding_is_proven_noop(value):
        current = value
    else:
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

    control_removed = _REMOVABLE_CONTROLS_RE.search(current) is not None
    without_controls = (
        _REMOVABLE_CONTROLS_RE.sub("", current) if control_removed else current
    )
    whitespace_only = (
        _UNICODE_WHITESPACE_ONLY_RE.fullmatch(without_controls) is not None
    )
    tab_normalized = "\t" in without_controls
    linebreak_normalized = _LINEBREAK_RE.search(without_controls) is not None
    unicode_whitespace_normalized = (
        _OTHER_UNICODE_WHITESPACE_RE.search(without_controls) is not None
    )
    if control_removed:
        reasons.append("CONTROL_CHARACTER_REMOVED")
    if tab_normalized:
        reasons.append("TAB_NORMALIZED")
    if linebreak_normalized:
        reasons.append("LINEBREAK_NORMALIZED")
    if unicode_whitespace_normalized:
        reasons.append("UNICODE_WHITESPACE_NORMALIZED")
    if tab_normalized or linebreak_normalized or unicode_whitespace_normalized:
        current = without_controls.translate(_CLEAN_TRANSLATION)
    elif control_removed:
        current = without_controls

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
        "punctuation_policy": STAGE03_PUNCTUATION_POLICY,
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _project_batch(
    batch: pa.RecordBatch,
    *,
    metadata: Mapping[bytes, bytes],
    stats: _ProjectionStats,
) -> pa.RecordBatch:
    if not batch.schema.remove_metadata().equals(
        stage02_schema(), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 3 input batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("UPSTREAM_NULL", "Stage 3 input contains an unexpected null")

    change_details: list[list[dict[str, object]]] = []
    change_details.extend([] for _ in range(batch.num_rows))
    clean_arrays: list[pa.Array] = []
    stats.total_field_values += batch.num_rows * len(CLEAN_SOURCE_COLUMNS)
    for source_name in CLEAN_SOURCE_COLUMNS:
        raw_values = batch.column(batch.schema.get_field_index(source_name))
        safe_mask = _clean_ascii_fast_path_mask(raw_values)
        safe_count_scalar = pc.sum(pc.cast(safe_mask, pa.int64()))
        safe_count = cast(int, safe_count_scalar.as_py() or 0)
        stats.ascii_fast_path_values += safe_count
        stats.full_profile_invocations += batch.num_rows - safe_count

        projected_values: list[str | None] = [None] * batch.num_rows
        unsafe_indices = pc.indices_nonzero(pc.invert(safe_mask))
        for index_scalar in unsafe_indices:
            row_index = cast(int, index_scalar.as_py())
            raw = raw_values[row_index].as_py()
            if not isinstance(raw, str):
                _fail("UPSTREAM_TYPE_MISMATCH", "Stage 3 source value is not text")
            result = clean_stage03_text(raw)
            projected_values[row_index] = result.value
            if result.reason_codes:
                stats.idempotence_recheck_invocations += 1
                second = clean_stage03_text(result.value)
                if second.value != result.value or second.reason_codes:
                    _fail("IDEMPOTENCE_FAILURE", "Stage 3 cleaning is not idempotent")
                change_details[row_index].append(
                    {
                        "field_name": source_name,
                        "reason_codes": list(result.reason_codes),
                    }
                )
        projected_array = pa.array(
            projected_values, type=pa.string(), from_pandas=False, safe=True
        )
        clean_arrays.append(
            cast(pa.Array, pc.if_else(safe_mask, raw_values, projected_array))
        )

    row_changed_flags = [bool(details) for details in change_details]

    arrays: list[pa.Array] = [batch.column(index) for index in range(batch.num_columns)]
    arrays.extend(clean_arrays)
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


def _validate_output_batch(batch: pa.RecordBatch, *, metrics: Stage03Metrics) -> None:
    """Validate audit/value consistency without re-running the text cleaner."""
    if not batch.schema.remove_metadata().equals(
        stage03_schema(), check_metadata=False
    ):
        _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 3 output batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("OUTPUT_NULL", "Stage 3 output contains an unexpected null")

    changed_fields_by_row: list[list[str]] = [[] for _ in range(batch.num_rows)]
    ascii_fast_path_values = 0
    raw_arrays: dict[str, pa.Array] = {}
    clean_arrays: dict[str, pa.Array] = {}
    punctuation_changed_rows: dict[str, set[int]] = {}
    for source_name, derived_name in zip(
        CLEAN_SOURCE_COLUMNS, CLEAN_DERIVED_COLUMNS, strict=True
    ):
        raw_values = batch.column(batch.schema.get_field_index(source_name))
        clean_values = batch.column(batch.schema.get_field_index(derived_name))
        raw_arrays[source_name] = raw_values
        clean_arrays[source_name] = clean_values
        safe_count_scalar = pc.sum(
            pc.cast(_clean_ascii_fast_path_mask(raw_values), pa.int64())
        )
        ascii_fast_path_values += cast(int, safe_count_scalar.as_py() or 0)
        changed_indices = pc.indices_nonzero(pc.not_equal(raw_values, clean_values))
        punctuation_changed_rows[source_name] = set()
        if len(changed_indices):
            changed_raw = pc.take(raw_values, changed_indices)
            changed_clean = pc.take(clean_values, changed_indices)
            raw_punctuation = pc.replace_substring_regex(
                changed_raw,
                pattern=_NON_PUNCTUATION_ARROW_PATTERN,
                replacement="",
            )
            clean_punctuation = pc.replace_substring_regex(
                changed_clean,
                pattern=_NON_PUNCTUATION_ARROW_PATTERN,
                replacement="",
            )
            punctuation_changed_positions = pc.indices_nonzero(
                pc.not_equal(raw_punctuation, clean_punctuation)
            )
            punctuation_changed_rows[source_name] = {
                cast(int, changed_indices[cast(int, position.as_py())].as_py())
                for position in punctuation_changed_positions
            }
        for index_scalar in changed_indices:
            row_index = cast(int, index_scalar.as_py())
            changed_fields_by_row[row_index].append(source_name)

    metrics.observe_batch_shape(
        row_count=batch.num_rows,
        ascii_fast_path_values=ascii_fast_path_values,
    )
    details_values = batch.column(
        batch.schema.get_field_index("stage03_change_details")
    )
    changed_flags = batch.column(batch.schema.get_field_index("stage03_row_changed"))
    for row_index, expected_fields in enumerate(changed_fields_by_row):
        raw_details = details_values[row_index].as_py()
        if not isinstance(raw_details, list):
            _fail("CHANGE_AUDIT_MISMATCH", "Change details are malformed")
        observed_fields: list[str] = []
        row_reasons: set[str] = set()
        row_groups: set[str] = set()
        for detail in raw_details:
            if not isinstance(detail, dict) or set(detail) != {
                "field_name",
                "reason_codes",
            }:
                _fail("CHANGE_AUDIT_MISMATCH", "Change detail fields are malformed")
            field_name = detail.get("field_name")
            raw_reasons = detail.get("reason_codes")
            if (
                not isinstance(field_name, str)
                or field_name not in CLEAN_SOURCE_COLUMNS
            ):
                _fail("CHANGE_AUDIT_MISMATCH", "Change field name is invalid")
            if (
                not isinstance(raw_reasons, list)
                or not raw_reasons
                or any(
                    not isinstance(reason, str) or reason not in REASON_CODES
                    for reason in raw_reasons
                )
            ):
                _fail("CHANGE_AUDIT_MISMATCH", "Change reasons are invalid")
            reasons = tuple(cast(list[str], raw_reasons))
            if tuple(sorted(set(reasons), key=REASON_CODES.index)) != reasons:
                _fail(
                    "CHANGE_REASON_ORDER_MISMATCH", "Change reasons are not canonical"
                )
            observed_fields.append(field_name)
            raw = raw_arrays[field_name][row_index].as_py()
            clean = clean_arrays[field_name][row_index].as_py()
            if not isinstance(raw, str) or not isinstance(clean, str) or raw == clean:
                _fail("CHANGE_AUDIT_MISMATCH", "Change detail value is inconsistent")
            metrics.observe_changed_field(
                column=field_name,
                raw=raw,
                clean=clean,
                reasons=reasons,
                punctuation_codepoints_changed=(
                    row_index in punctuation_changed_rows[field_name]
                ),
            )
            row_reasons.update(reasons)
            row_groups.add(FIELD_GROUP_BY_COLUMN[field_name])
        if observed_fields != expected_fields:
            _fail("CHANGE_AUDIT_MISMATCH", "Changed fields are absent or out of order")
        changed_flag = changed_flags[row_index].as_py()
        if not isinstance(changed_flag, bool) or changed_flag != bool(expected_fields):
            _fail("CHANGE_AUDIT_MISMATCH", "Row change flag is inconsistent")
        if expected_fields:
            metrics.observe_changed_row(reasons=row_reasons, groups=row_groups)


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


def _iter_bounded_batches(
    parquet: pq.ParquetFile,
    *,
    batch_rows: int,
    target_batch_bytes: int,
) -> Iterable[pa.RecordBatch]:
    """Size batches from row-group bytes, never from total-dataset cardinality."""
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        if row_group.num_rows < 1:
            _fail("PARQUET_READ_FAILURE", "Stage 3 encountered an empty row group")
        average_row_bytes = max(
            1,
            (row_group.total_byte_size + row_group.num_rows - 1) // row_group.num_rows,
        )
        adaptive_rows = max(
            1,
            min(batch_rows, target_batch_bytes // average_row_bytes),
        )
        yield from parquet.iter_batches(
            batch_size=adaptive_rows,
            row_groups=[row_group_index],
            use_threads=False,
        )


def _iter_output_row_group_batches(
    parquet: pq.ParquetFile, *, batch_rows: int
) -> Iterable[pa.RecordBatch]:
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        if row_group.num_rows < 1 or row_group.num_rows > batch_rows:
            _fail("OUTPUT_ROW_MISMATCH", "Stage 3 output row group is not bounded")
        yield from parquet.iter_batches(
            batch_size=batch_rows,
            row_groups=[row_group_index],
            use_threads=False,
        )


def _stage02_artifacts(
    root: Path, binding: Stage03InputBinding
) -> tuple[Stage03ArtifactIdentity, ...]:
    """Bind exact accepted Stage 2 bytes without re-proving its row invariants."""
    _reject_holdout_paths(root)
    _require_directory(root, "STAGE02_BUNDLE_INVALID")
    _require_mode(root, 0o700, "PERMISSION_FAILURE")
    if (root / STAGE02_IN_PROGRESS_MARKER).exists():
        _fail("STAGE02_BUNDLE_INVALID", "Stage 2 retains an in-progress marker")
    data_directory = root / "data"
    _require_directory(data_directory, "STAGE02_BUNDLE_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    manifest_path = root / STAGE02_MANIFEST_NAME
    success_path = root / STAGE02_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE02_BUNDLE_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(manifest_path) != binding.upstream_manifest_sha256:
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 manifest SHA-256 differs")
    manifest = _load_json(manifest_path, "STAGE02_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE02_BUNDLE_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if (
        not isinstance(scientific, dict)
        or not isinstance(physical, dict)
        or not isinstance(validation, dict)
    ):
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 manifest identity is malformed")
    if (
        manifest.get("stage02_manifest_version") != "stage02_manifest_v1"
        or manifest.get("status")
        != "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION"
        or success.get("status")
        != "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION"
        or success.get("stage02_manifest_sha256") != binding.upstream_manifest_sha256
        or success.get("stage02_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
        or scientific.get("stage02_contract_version")
        != binding.upstream_contract_version
        or scientific.get("stage02_schema_version") != STAGE02_SCHEMA_VERSION
        or scientific.get("stage02_schema_fingerprint")
        != binding.upstream_schema_fingerprint
        or scientific.get("stage02_logical_dataset_sha256_v1")
        != binding.upstream_logical_identity_sha256
        or scientific.get("upstream_logical_identity_sha256")
        != binding.input_benchmark_fingerprint
        or scientific.get("row_count") != binding.expected_row_count
    ):
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 scientific binding differs")
    if (
        physical.get("owner_only_permissions") is not True
        or validation.get("validation_contract_version") != STAGE02_VALIDATION_VERSION
        or any(
            result != "PASS"
            for name, result in validation.items()
            if name != "validation_contract_version"
        )
    ):
        _fail("STAGE02_BUNDLE_INVALID", "Accepted Stage 2 validation is incomplete")
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
    directories, files = _observed_topology(root)
    expected_files = {
        STAGE02_MANIFEST_NAME,
        STAGE02_SUCCESS_MARKER,
        *(artifact.relative_path for artifact in artifacts),
    }
    if directories != {"data"} or files != expected_files:
        _fail("STAGE02_BUNDLE_INVALID", "Stage 2 artifact topology is not exact")
    if (
        sum(artifact.row_count for artifact in artifacts) != binding.expected_row_count
        or success.get("row_count") != binding.expected_row_count
        or success.get("output_shard_count") != len(artifacts)
        or success.get("stage02_logical_dataset_sha256_v1")
        != binding.upstream_logical_identity_sha256
    ):
        _fail("STAGE02_IDENTITY_MISMATCH", "Stage 2 terminal counts differ")
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
    target_batch_bytes: int,
    metadata: Mapping[bytes, bytes],
    stats: _ProjectionStats,
    ordered_input_identities: _OrderedStableIdentityHasher,
) -> tuple[int, str]:
    try:
        parquet = pq.ParquetFile(input_path, page_checksum_verification=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            stage02_schema(), check_metadata=False
        ):
            _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 2 Parquet schema is not exact")
        batches = _iter_bounded_batches(
            parquet,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        )
    except Stage03ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage03ValidationError(
            "PARQUET_READ_FAILURE", "Stage 2 input could not be opened safely"
        ) from error
    writer = _new_writer(output_path, stage03_schema().with_metadata(dict(metadata)))
    rows = 0
    shard_identities = _OrderedStableIdentityHasher()
    try:
        for batch in batches:
            stable_ids = batch.column(
                batch.schema.get_field_index("stable_source_row_id_v1")
            )
            ordered_input_identities.update(stable_ids)
            shard_identities.update(stable_ids)
            projected = _project_batch(batch, metadata=metadata, stats=stats)
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
    return rows, shard_identities.hexdigest()


def _assert_input_output_equal(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    target_batch_bytes: int,
    metadata: Mapping[bytes, bytes],
    metrics: Stage03Metrics,
    ordered_output_identities: _OrderedStableIdentityHasher,
) -> str:
    try:
        input_file = pq.ParquetFile(input_path, page_checksum_verification=True)
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        expected_schema = stage03_schema().with_metadata(dict(metadata))
        if not output_file.schema_arrow.equals(expected_schema, check_metadata=True):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 3 output schema is not exact")
        input_batches = _iter_bounded_batches(
            input_file,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        )
        output_batches = _iter_output_row_group_batches(
            output_file,
            batch_rows=batch_rows,
        )
        shard_identities = _OrderedStableIdentityHasher()
        sentinel = object()
        for raw_batch, output_batch in zip_longest(
            input_batches, output_batches, fillvalue=sentinel
        ):
            if raw_batch is sentinel or output_batch is sentinel:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 3 batch topology differs")
            assert isinstance(raw_batch, pa.RecordBatch)
            assert isinstance(output_batch, pa.RecordBatch)
            if raw_batch.num_rows != output_batch.num_rows:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 3 batch row count differs")
            for index in range(len(stage02_schema())):
                if not raw_batch.column(index).equals(output_batch.column(index)):
                    _fail(
                        "UPSTREAM_VALUE_MISMATCH",
                        "Stage 3 changed an incoming Stage 2 value or row order",
                    )
            _validate_output_batch(output_batch, metrics=metrics)
            stable_ids = output_batch.column(
                output_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            ordered_output_identities.update(stable_ids)
            shard_identities.update(stable_ids)
        return shard_identities.hexdigest()
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
    stats = _ProjectionStats()
    ordered_input_identities = _OrderedStableIdentityHasher()
    ordered_output_identities = _OrderedStableIdentityHasher()
    shard_identity_evidence: list[dict[str, str | int]] = []
    output_artifacts: list[Stage03ArtifactIdentity] = []
    for sequence_number, artifact in enumerate(artifacts, start=1):
        input_path, before = _input_artifact_snapshot(
            config.stage02_output_directory, artifact
        )
        relative_output = f"data/part-{sequence_number:06d}.parquet"
        output_path = temporary / relative_output
        rows, input_identity_digest = _write_output_shard(
            input_path,
            output_path,
            batch_rows=config.batch_rows,
            target_batch_bytes=config.target_batch_bytes,
            metadata=metadata,
            stats=stats,
            ordered_input_identities=ordered_input_identities,
        )
        output_identity_digest = _assert_input_output_equal(
            input_path,
            output_path,
            batch_rows=config.batch_rows,
            target_batch_bytes=config.target_batch_bytes,
            metadata=metadata,
            metrics=metrics,
            ordered_output_identities=ordered_output_identities,
        )
        if input_identity_digest != output_identity_digest:
            _fail(
                "STABLE_IDENTITY_MISMATCH",
                "Stage 3 ordered stable identities differ within a shard",
            )
        _assert_input_unchanged(input_path, before, artifact.sha256)
        if rows != artifact.row_count:
            _fail("ROW_COUNT_MISMATCH", "Stage 3 shard row count differs")
        shard_identity_evidence.append(
            {
                "relative_path": relative_output,
                "row_count": rows,
                "input_ordered_stable_identity_sha256_v1": input_identity_digest,
                "output_ordered_stable_identity_sha256_v1": output_identity_digest,
            }
        )
        output_artifacts.append(
            _artifact_identity(temporary, relative_output, row_count=rows)
        )

    if metrics.output_rows != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 3 total row count differs")
    if (
        ordered_input_identities.row_count != binding.expected_row_count
        or ordered_output_identities.row_count != binding.expected_row_count
        or ordered_input_identities.hexdigest() != ordered_output_identities.hexdigest()
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Stable identity stream is not exact")
    stats.validate_against(metrics)
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
            "punctuation_policy": STAGE03_PUNCTUATION_POLICY,
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
            "bounded_memory_architecture": {
                "maximum_configured_batch_rows": config.batch_rows,
                "target_uncompressed_batch_bytes": config.target_batch_bytes,
                "memory_scales_with_total_row_count": False,
                "review_selection_maximum_rows": 500,
            },
            "ordered_identity_validation": {
                "ordered_identity_contract_version": (STAGE03_ORDERED_IDENTITY_VERSION),
                "upstream_duplicate_free_invariant_bound": True,
                "total_row_python_identity_set_used": False,
                "input_ordered_stable_identity_sha256_v1": (
                    ordered_input_identities.hexdigest()
                ),
                "output_ordered_stable_identity_sha256_v1": (
                    ordered_output_identities.hexdigest()
                ),
                "row_count": ordered_output_identities.row_count,
                "shards": shard_identity_evidence,
            },
        },
        "validation": {
            "validation_contract_version": STAGE03_VALIDATION_VERSION,
            "upstream_identity_schema_and_manifest": "PASS",
            "input_artifact_integrity": "PASS",
            "row_count_preserved": "PASS",
            "stable_source_row_id_preserved": "PASS",
            "ordered_stable_identity_fingerprint_equal": "PASS",
            "shard_batch_incoming_array_equality": "PASS",
            "bounded_memory_identity_validation": "PASS",
            "upstream_duplicate_free_invariant_bound": "PASS",
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
        or scientific.get("punctuation_policy") != STAGE03_PUNCTUATION_POLICY
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
    bounded_memory = physical.get("bounded_memory_architecture")
    if not isinstance(bounded_memory, dict) or set(bounded_memory) != {
        "maximum_configured_batch_rows",
        "target_uncompressed_batch_bytes",
        "memory_scales_with_total_row_count",
        "review_selection_maximum_rows",
    }:
        _fail("STAGE03_MANIFEST_INVALID", "Bounded-memory evidence is malformed")
    maximum_batch_rows = _required_uint(
        bounded_memory.get("maximum_configured_batch_rows"),
        "STAGE03_MANIFEST_INVALID",
    )
    target_batch_bytes = _required_uint(
        bounded_memory.get("target_uncompressed_batch_bytes"),
        "STAGE03_MANIFEST_INVALID",
    )
    if (
        maximum_batch_rows < 1
        or target_batch_bytes < 1
        or bounded_memory.get("memory_scales_with_total_row_count") is not False
        or bounded_memory.get("review_selection_maximum_rows") != 500
    ):
        _fail("STAGE03_MANIFEST_INVALID", "Bounded-memory evidence differs")
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

    ordered_evidence = physical.get("ordered_identity_validation")
    if not isinstance(ordered_evidence, dict) or set(ordered_evidence) != {
        "ordered_identity_contract_version",
        "upstream_duplicate_free_invariant_bound",
        "total_row_python_identity_set_used",
        "input_ordered_stable_identity_sha256_v1",
        "output_ordered_stable_identity_sha256_v1",
        "row_count",
        "shards",
    }:
        _fail("STAGE03_MANIFEST_INVALID", "Ordered identity evidence is malformed")
    input_identity_digest = _required_text(
        ordered_evidence.get("input_ordered_stable_identity_sha256_v1"),
        "STAGE03_MANIFEST_INVALID",
    )
    output_identity_digest = _required_text(
        ordered_evidence.get("output_ordered_stable_identity_sha256_v1"),
        "STAGE03_MANIFEST_INVALID",
    )
    _digest_bytes(input_identity_digest)
    _digest_bytes(output_identity_digest)
    raw_shard_evidence = ordered_evidence.get("shards")
    if (
        ordered_evidence.get("ordered_identity_contract_version")
        != STAGE03_ORDERED_IDENTITY_VERSION
        or ordered_evidence.get("upstream_duplicate_free_invariant_bound") is not True
        or ordered_evidence.get("total_row_python_identity_set_used") is not False
        or ordered_evidence.get("row_count") != binding.expected_row_count
        or input_identity_digest != output_identity_digest
        or not isinstance(raw_shard_evidence, list)
        or len(raw_shard_evidence) != len(output_artifacts)
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Ordered identity evidence differs")

    expected_metadata = _output_metadata(binding, logical_fingerprint)
    observed_metrics = Stage03Metrics()
    observed_identities = _OrderedStableIdentityHasher()
    for artifact, raw_shard_identity in zip(
        output_artifacts, raw_shard_evidence, strict=True
    ):
        if not isinstance(raw_shard_identity, dict) or set(raw_shard_identity) != {
            "relative_path",
            "row_count",
            "input_ordered_stable_identity_sha256_v1",
            "output_ordered_stable_identity_sha256_v1",
        }:
            _fail("STAGE03_MANIFEST_INVALID", "Shard identity evidence is malformed")
        shard_input_digest = _required_text(
            raw_shard_identity.get("input_ordered_stable_identity_sha256_v1"),
            "STAGE03_MANIFEST_INVALID",
        )
        shard_output_digest = _required_text(
            raw_shard_identity.get("output_ordered_stable_identity_sha256_v1"),
            "STAGE03_MANIFEST_INVALID",
        )
        _digest_bytes(shard_input_digest)
        _digest_bytes(shard_output_digest)
        if (
            raw_shard_identity.get("relative_path") != artifact.relative_path
            or raw_shard_identity.get("row_count") != artifact.row_count
            or shard_input_digest != shard_output_digest
        ):
            _fail("STABLE_IDENTITY_MISMATCH", "Shard identity evidence differs")
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
            shard_identities = _OrderedStableIdentityHasher()
            for output_batch in _iter_bounded_batches(
                parquet,
                batch_rows=maximum_batch_rows,
                target_batch_bytes=target_batch_bytes,
            ):
                _validate_output_batch(output_batch, metrics=observed_metrics)
                stable_values = output_batch.column(
                    output_batch.schema.get_field_index("stable_source_row_id_v1")
                )
                observed_identities.update(stable_values)
                shard_identities.update(stable_values)
                shard_rows += output_batch.num_rows
            if shard_rows != artifact.row_count:
                _fail("ROW_COUNT_MISMATCH", "Stage 3 shard row count differs")
            if shard_identities.hexdigest() != shard_output_digest:
                _fail("STABLE_IDENTITY_MISMATCH", "Shard identity digest differs")
        except Stage03ValidationError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise Stage03ValidationError(
                "PARQUET_READBACK_FAILURE", "Stage 3 page-checksum read-back failed"
            ) from error
    if observed_metrics.output_rows != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 3 total row count differs")
    if (
        observed_identities.row_count != binding.expected_row_count
        or observed_identities.hexdigest() != output_identity_digest
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Stage 3 identity stream differs")
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


def _comparison_artifacts(
    root: Path, *, expected_manifest_sha256: str
) -> tuple[tuple[Stage03ArtifactIdentity, ...], int]:
    """Validate exact immutable bytes for a v1 or v2 scientific comparison."""
    _digest_bytes(expected_manifest_sha256)
    _reject_holdout_paths(root)
    _require_directory(root, "STAGE03_COMPARISON_INPUT_INVALID")
    _require_mode(root, 0o700, "PERMISSION_FAILURE")
    data_directory = root / "data"
    _require_directory(data_directory, "STAGE03_COMPARISON_INPUT_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    manifest_path = root / STAGE03_MANIFEST_NAME
    success_path = root / STAGE03_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE03_COMPARISON_INPUT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        _fail("STAGE03_MANIFEST_SHA256_MISMATCH", "Comparison manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE03_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE03_SUCCESS_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Comparison identity is malformed")
    if (
        manifest.get("stage03_manifest_version")
        not in {"stage03_manifest_v1", STAGE03_MANIFEST_VERSION}
        or manifest.get("status") != "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_3_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage03_manifest_sha256") != expected_manifest_sha256
        or scientific.get("stage03_contract_version") != STAGE03_CONTRACT_VERSION
        or scientific.get("stage03_profile_version") != STAGE03_PROFILE_VERSION
        or scientific.get("stage03_schema_fingerprint") != stage03_schema_fingerprint()
        or scientific.get("clean_source_columns") != list(CLEAN_SOURCE_COLUMNS)
        or scientific.get("clean_derived_columns") != list(CLEAN_DERIVED_COLUMNS)
        or scientific.get("reason_codes") != list(REASON_CODES)
    ):
        _fail("STAGE03_COMPARISON_INPUT_INVALID", "Comparison identity differs")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE03_MANIFEST_INVALID", "Comparison artifacts are absent")
    artifacts: list[Stage03ArtifactIdentity] = []
    expected_files = {STAGE03_MANIFEST_NAME, STAGE03_SUCCESS_MARKER}
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE03_MANIFEST_INVALID", "Comparison artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE03_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE03_MANIFEST_INVALID", "Comparison shard order differs")
        artifact = Stage03ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE03_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE03_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE03_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        path = root / relative_path
        _require_regular_file(path, "STAGE03_COMPARISON_INPUT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("STAGE03_ARTIFACT_MISMATCH", "Comparison artifact SHA differs")
        artifacts.append(artifact)
        expected_files.add(relative_path)
    directories, files = _observed_topology(root)
    row_count = sum(artifact.row_count for artifact in artifacts)
    if (
        directories != {"data"}
        or files != expected_files
        or scientific.get("row_count") != row_count
        or success.get("row_count") != row_count
        or success.get("output_shard_count") != len(artifacts)
    ):
        _fail("STAGE03_COMPARISON_INPUT_INVALID", "Comparison topology differs")
    return tuple(artifacts), row_count


def _iter_aligned_batch_slices(
    left_batches: Iterable[pa.RecordBatch],
    right_batches: Iterable[pa.RecordBatch],
) -> Iterable[tuple[pa.RecordBatch, pa.RecordBatch]]:
    """Align two bounded streams without requiring identical row-group boundaries."""
    left_iterator = iter(left_batches)
    right_iterator = iter(right_batches)
    left = next(left_iterator, None)
    right = next(right_iterator, None)
    left_offset = 0
    right_offset = 0
    while left is not None or right is not None:
        if left is None or right is None:
            _fail("STAGE03_V1_V2_ROW_MISMATCH", "v1/v2 row streams differ")
        assert isinstance(left, pa.RecordBatch)
        assert isinstance(right, pa.RecordBatch)
        if left.num_rows < 1 or right.num_rows < 1:
            _fail("STAGE03_V1_V2_ROW_MISMATCH", "v1/v2 contains an empty batch")
        row_count = min(
            left.num_rows - left_offset,
            right.num_rows - right_offset,
        )
        yield left.slice(left_offset, row_count), right.slice(right_offset, row_count)
        left_offset += row_count
        right_offset += row_count
        if left_offset == left.num_rows:
            left = next(left_iterator, None)
            left_offset = 0
        if right_offset == right.num_rows:
            right = next(right_iterator, None)
            right_offset = 0


def compare_stage03_scientific_outputs(
    v1_output_directory: Path,
    *,
    expected_v1_manifest_sha256: str,
    v2_output_directory: Path,
    expected_v2_manifest_sha256: str,
    batch_rows: int = 2_048,
) -> Stage03ScientificEquivalenceOutcome:
    """Stream an exact v1/v2 scientific-output comparison with bounded memory."""
    if isinstance(batch_rows, bool) or batch_rows < 1:
        _fail("INVALID_BATCH_SIZE", "Comparison batch size must be positive")
    v1_artifacts, v1_rows = _comparison_artifacts(
        v1_output_directory,
        expected_manifest_sha256=expected_v1_manifest_sha256,
    )
    v2_artifacts, v2_rows = _comparison_artifacts(
        v2_output_directory,
        expected_manifest_sha256=expected_v2_manifest_sha256,
    )
    if v1_rows != v2_rows or len(v1_artifacts) != len(v2_artifacts):
        _fail("STAGE03_V1_V2_ROW_MISMATCH", "v1/v2 row topology differs")

    compared_rows = 0
    for v1_artifact, v2_artifact in zip(v1_artifacts, v2_artifacts, strict=True):
        if v1_artifact.row_count != v2_artifact.row_count:
            _fail("STAGE03_V1_V2_ROW_MISMATCH", "v1/v2 shard rows differ")
        try:
            v1_file = pq.ParquetFile(
                v1_output_directory / v1_artifact.relative_path,
                page_checksum_verification=True,
            )
            v2_file = pq.ParquetFile(
                v2_output_directory / v2_artifact.relative_path,
                page_checksum_verification=True,
            )
            if not v1_file.schema_arrow.remove_metadata().equals(
                stage03_schema(), check_metadata=False
            ) or not v2_file.schema_arrow.remove_metadata().equals(
                stage03_schema(), check_metadata=False
            ):
                _fail("OUTPUT_SCHEMA_MISMATCH", "v1/v2 output schema differs")
            for v1_batch, v2_batch in _iter_aligned_batch_slices(
                v1_file.iter_batches(batch_size=batch_rows, use_threads=False),
                v2_file.iter_batches(batch_size=batch_rows, use_threads=False),
            ):
                for index in range(len(stage02_schema())):
                    if not v1_batch.column(index).equals(v2_batch.column(index)):
                        _fail(
                            "STAGE03_V1_V2_INCOMING_MISMATCH",
                            "v1/v2 incoming Stage 2 values differ",
                        )
                for name in CLEAN_DERIVED_COLUMNS:
                    index = v1_batch.schema.get_field_index(name)
                    if not v1_batch.column(index).equals(v2_batch.column(index)):
                        _fail(
                            "STAGE03_V1_V2_CLEAN_VALUE_MISMATCH",
                            "v1/v2 clean values differ",
                        )
                changed_index = v1_batch.schema.get_field_index("stage03_row_changed")
                if not v1_batch.column(changed_index).equals(
                    v2_batch.column(changed_index)
                ):
                    _fail(
                        "STAGE03_V1_V2_ROW_CHANGED_MISMATCH",
                        "v1/v2 row-changed flags differ",
                    )
                reason_index = v1_batch.schema.get_field_index("stage03_change_details")
                if not v1_batch.column(reason_index).equals(
                    v2_batch.column(reason_index)
                ):
                    _fail(
                        "STAGE03_V1_V2_REASON_MISMATCH",
                        "v1/v2 reason evidence differs",
                    )
                compared_rows += v1_batch.num_rows
        except Stage03ValidationError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise Stage03ValidationError(
                "STAGE03_V1_V2_READ_FAILURE",
                "v1/v2 Parquet comparison failed",
            ) from error
    if compared_rows != v1_rows:
        _fail("STAGE03_V1_V2_ROW_MISMATCH", "v1/v2 compared row count differs")
    return Stage03ScientificEquivalenceOutcome(
        row_count=compared_rows,
        cleaned_field_count=compared_rows * len(CLEAN_SOURCE_COLUMNS),
        row_identity_equal=True,
        incoming_stage02_equal=True,
        clean_values_equal=True,
        row_changed_equal=True,
        reason_codes_equal=True,
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
    "Stage03ScientificEquivalenceOutcome",
    "Stage03ValidationError",
    "clean_stage03_text",
    "compare_stage03_scientific_outputs",
    "load_stage03_input_binding",
    "materialize_stage03",
    "ordered_stable_identity_sha256_v1",
    "stage03_logical_dataset_sha256_v1",
    "stage03_schema",
    "stage03_schema_fingerprint",
    "validate_stage03_bundle",
    "validate_stage03_input_binding",
    "validate_stage03_runtime",
    "write_stage03_input_binding",
]

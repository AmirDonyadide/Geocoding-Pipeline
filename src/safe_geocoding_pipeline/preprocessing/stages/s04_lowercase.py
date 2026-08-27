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
from functools import lru_cache
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable, Mapping, NoReturn, Protocol, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..script_reference import ScriptReference, unicode_script_reference_paths
from .s03_cleaning import (
    CLEAN_DERIVED_COLUMNS,
    CLEAN_SOURCE_COLUMNS,
    EXPECTED_PYARROW_VERSION,
    EXPECTED_PYTHON_VERSION,
    EXPECTED_UNICODE_VERSION,
    FIELD_GROUPS,
    FIELD_GROUP_BY_COLUMN,
    STAGE03_CONTRACT_VERSION,
    STAGE03_MANIFEST_NAME,
    STAGE03_PROFILE_VERSION,
    STAGE03_SCHEMA_VERSION,
    STAGE03_SUCCESS_MARKER,
    Stage03ValidationError,
    stage03_schema,
    stage03_schema_fingerprint,
    validate_stage03_bundle,
)

STAGE04_CONTRACT_VERSION = "stage04_lowercase_canonical_contract_v1"
STAGE04_PROFILE_VERSION = "stage04_lowercase_canonical_profile_v1"
STAGE04_INPUT_BINDING_VERSION = "stage04_input_binding_v1"
STAGE04_SCHEMA_VERSION = "stage04_lowercase_canonical_schema_v1"
STAGE04_VALIDATION_VERSION = "stage04_bundle_validation_v1"
STAGE04_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE04_LOGICAL_DATASET_V1"
STAGE04_SCHEMA_FINGERPRINT_DOMAIN = b"SAFE_STAGE04_ARROW_SCHEMA_V1"
STAGE04_MANIFEST_VERSION = "stage04_manifest_v1"
STAGE04_ORDERED_IDENTITY_VERSION = "stage03_ordered_stable_identity_sha256_v1"
STAGE04_ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
STAGE04_TRANSFORMATION = "PYTHON_STR_LOWER"
STAGE04_NORMALIZATION_AFTER_LOWER = "NONE"
STAGE04_CASEFOLD_USED = False
STAGE04_LOCALE_SPECIFIC_CASING_USED = False
DEFAULT_TARGET_BATCH_BYTES = 256 * 1024 * 1024

STAGE04_MANIFEST_NAME = "stage04_manifest.json"
STAGE04_SUCCESS_MARKER = "_SUCCESS.json"
STAGE04_IN_PROGRESS_MARKER = "_IN_PROGRESS"

# The authoritative DEVELOPMENT boundary is explicit in code and the launcher.
ACCEPTED_STAGE03_LOGICAL_FINGERPRINT = (
    "38df499bfaf61883832a9c718adf4cf92cfcea753337df68fa2e89afb6051bdb"
)
ACCEPTED_STAGE03_SCHEMA_FINGERPRINT = (
    "fc991ef63bd80a754114ecae6a9d3c4cf1f33a35a28581fea997edd2e4565c9b"
)
ACCEPTED_STAGE03_INPUT_BINDING_SHA256 = (
    "6a2a28d276884511f5b8f63f40d14d6b7f4bf4397aa09289c53acdb92a661e6f"
)
ACCEPTED_STAGE03_MANIFEST_SHA256 = (
    "8f70745e31185abce52fdc1685c2b767f90874c21596152ea0463ec6677478d4"
)
ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256 = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_DEVELOPMENT_ROWS = 35_000

LOWER_INPUT_COLUMNS = CLEAN_DERIVED_COLUMNS
LOWER_OUTPUT_COLUMNS = tuple(f"stage04_lower_{name}" for name in CLEAN_SOURCE_COLUMNS)
STAGE04_AUDIT_COLUMNS = ("stage04_changed_fields", "stage04_row_changed")
CHANGED_FIELDS_TYPE = pa.list_(pa.field("element", pa.string(), nullable=False))

SCRIPT_CLASSES = (
    "EMPTY",
    "ASCII_ONLY",
    "LATIN_NON_ASCII",
    "CYRILLIC",
    "GREEK",
    "ARABIC_PERSIAN",
    "CJK_HANGUL",
    "MIXED",
    "OTHER",
)
_CJK_HANGUL_SCRIPTS = frozenset({"Han", "Hiragana", "Katakana", "Hangul", "Bopomofo"})
_NON_DISTINCTIVE_SCRIPTS = frozenset({"Common", "Inherited", "Unknown"})
CASE_CHANGE_CLASSES = (
    "UNCHANGED",
    "ASCII_CASE_CHANGED",
    "UNICODE_CASE_CHANGED",
    "UNICODE_LENGTH_CHANGED",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"


class Stage04ValidationError(RuntimeError):
    """Privacy-safe, fail-closed Stage 4 validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage04InputBinding:
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
            "stage04_input_binding_version": STAGE04_INPUT_BINDING_VERSION,
            "upstream_contract_version": self.upstream_contract_version,
            "upstream_profile_version": self.upstream_profile_version,
            "upstream_logical_fingerprint": self.upstream_logical_fingerprint,
            "upstream_schema_fingerprint": self.upstream_schema_fingerprint,
            "upstream_input_binding_sha256": self.upstream_input_binding_sha256,
            "upstream_manifest_sha256": self.upstream_manifest_sha256,
            "upstream_ordered_identity_sha256": (self.upstream_ordered_identity_sha256),
            "input_benchmark_fingerprint": self.input_benchmark_fingerprint,
            "expected_row_count": self.expected_row_count,
        }


@dataclass(frozen=True, slots=True)
class Stage04RunConfig:
    stage03_output_directory: Path
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
            self.stage03_output_directory,
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
class Stage04ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage04MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    schema_fingerprint: str
    input_binding_sha256: str
    manifest_sha256: str
    ordered_identity_sha256: str
    row_count: int
    output_shard_count: int
    metrics: Mapping[str, Mapping[str, int]]


@dataclass(slots=True)
class Stage04Metrics:
    input_rows: int = 0
    output_rows: int = 0
    rows_changed: int = 0
    total_lowercase_fields: int = 0
    changed_fields: int = 0
    character_count_increase_fields: int = 0
    character_count_decrease_fields: int = 0
    total_character_count_increase: int = 0
    total_character_count_decrease: int = 0
    max_length_increase: int = 0
    max_length_decrease: int = 0
    empty_to_nonempty: int = 0
    nonempty_to_empty: int = 0
    idempotence_failures: int = 0
    ascii_fast_path_values: int = 0
    python_lower_values: int = 0
    uncased_script_unchanged_values: int = 0
    field_changed_fields: Counter[str] = field(
        default_factory=lambda: Counter(
            {name.upper(): 0 for name in CLEAN_SOURCE_COLUMNS}
        )
    )
    field_group_changed_fields: Counter[str] = field(
        default_factory=lambda: Counter({group: 0 for group in FIELD_GROUPS})
    )
    field_group_affected_rows: Counter[str] = field(
        default_factory=lambda: Counter({group: 0 for group in FIELD_GROUPS})
    )
    case_change_classes: Counter[str] = field(
        default_factory=lambda: Counter({name: 0 for name in CASE_CHANGE_CLASSES})
    )
    script_total_values: Counter[str] = field(
        default_factory=lambda: Counter({name: 0 for name in SCRIPT_CLASSES})
    )
    script_changed_values: Counter[str] = field(
        default_factory=lambda: Counter({name: 0 for name in SCRIPT_CLASSES})
    )
    script_unchanged_values: Counter[str] = field(
        default_factory=lambda: Counter({name: 0 for name in SCRIPT_CLASSES})
    )

    def observe_row(self, *, changed_groups: set[str]) -> None:
        if changed_groups:
            self.rows_changed += 1
            self.field_group_affected_rows.update(changed_groups)

    def observe_value(self, *, source_name: str, before: str, after: str) -> None:
        self.total_lowercase_fields += 1
        script_class = classify_script_value(before)
        self.script_total_values[script_class] += 1
        changed = before != after
        if changed:
            self.changed_fields += 1
            self.field_changed_fields[source_name.upper()] += 1
            self.field_group_changed_fields[FIELD_GROUP_BY_COLUMN[source_name]] += 1
            self.script_changed_values[script_class] += 1
            if before.isascii():
                self.case_change_classes["ASCII_CASE_CHANGED"] += 1
            elif len(before) != len(after):
                self.case_change_classes["UNICODE_LENGTH_CHANGED"] += 1
            else:
                self.case_change_classes["UNICODE_CASE_CHANGED"] += 1
        else:
            self.case_change_classes["UNCHANGED"] += 1
            self.script_unchanged_values[script_class] += 1
            if before and not any(
                _codepoint_has_case(ord(character)) for character in before
            ):
                self.uncased_script_unchanged_values += 1
        if before.isascii():
            self.ascii_fast_path_values += 1
        else:
            self.python_lower_values += 1
        delta = len(after) - len(before)
        if delta > 0:
            self.character_count_increase_fields += 1
            self.total_character_count_increase += delta
            self.max_length_increase = max(self.max_length_increase, delta)
        elif delta < 0:
            self.character_count_decrease_fields += 1
            self.total_character_count_decrease += -delta
            self.max_length_decrease = max(self.max_length_decrease, -delta)
        if before == "" and after != "":
            self.empty_to_nonempty += 1
        if before != "" and after == "":
            self.nonempty_to_empty += 1
        if after.lower() != after:
            self.idempotence_failures += 1

    def finish_batch(self, row_count: int) -> None:
        self.input_rows += row_count
        self.output_rows += row_count

    def to_metric_groups(self) -> dict[str, dict[str, int]]:
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
                "ROWS_UNCHANGED": self.output_rows - self.rows_changed,
                "ROWS_CHANGED_PERCENT_BASIS_POINTS": (
                    (self.rows_changed * 10_000 + self.output_rows // 2)
                    // self.output_rows
                    if self.output_rows
                    else 0
                ),
            },
            "FIELD_CHANGES": {
                "TOTAL_LOWERCASE_FIELDS": self.total_lowercase_fields,
                "CHANGED_FIELDS": self.changed_fields,
                "UNCHANGED_FIELDS": self.total_lowercase_fields - self.changed_fields,
            },
            "FIELD_CHANGED_FIELDS": dict(self.field_changed_fields),
            "FIELD_GROUP_AFFECTED_ROWS": dict(self.field_group_affected_rows),
            "FIELD_GROUP_CHANGED_FIELDS": dict(self.field_group_changed_fields),
            "FIELD_GROUP_TOTAL_FIELDS": group_totals,
            "CASE_CHANGE_CLASSIFICATION": dict(self.case_change_classes),
            "SCRIPT_CLASS_TOTAL_VALUES": dict(self.script_total_values),
            "SCRIPT_CLASS_CHANGED_VALUES": dict(self.script_changed_values),
            "SCRIPT_CLASS_UNCHANGED_VALUES": dict(self.script_unchanged_values),
            "LOWERCASE_ENGINE": {
                "ASCII_FAST_PATH_VALUES": self.ascii_fast_path_values,
                "PYTHON_LOWER_VALUES": self.python_lower_values,
                "ARROW_UTF8_LOWER_VALUES": 0,
            },
            "OUTPUT_EFFECTS": {
                "CHARACTER_COUNT_INCREASE_FIELDS": (
                    self.character_count_increase_fields
                ),
                "CHARACTER_COUNT_DECREASE_FIELDS": (
                    self.character_count_decrease_fields
                ),
                "TOTAL_CHARACTER_COUNT_INCREASE_CODEPOINTS": (
                    self.total_character_count_increase
                ),
                "TOTAL_CHARACTER_COUNT_DECREASE_CODEPOINTS": (
                    self.total_character_count_decrease
                ),
                "MAX_LENGTH_INCREASE_CODEPOINTS": self.max_length_increase,
                "MAX_LENGTH_DECREASE_CODEPOINTS": self.max_length_decrease,
                "EMPTY_TO_NONEMPTY_FIELDS": self.empty_to_nonempty,
                "NONEMPTY_TO_EMPTY_FIELDS": self.nonempty_to_empty,
                "UNICODE_LENGTH_CHANGED_FIELDS": self.case_change_classes[
                    "UNICODE_LENGTH_CHANGED"
                ],
                "UNCASED_SCRIPT_UNCHANGED_VALUES": (
                    self.uncased_script_unchanged_values
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
    """Bind the ordered stable-ID stream without retaining individual IDs."""

    def __init__(self) -> None:
        self._digest = hashlib.sha256(STAGE04_ORDERED_IDENTITY_DOMAIN)
        self.row_count = 0

    def update(self, values: pa.Array) -> None:
        if (
            not pa.types.is_fixed_size_binary(values.type)
            or values.type.byte_width != 32
            or values.null_count
        ):
            _fail("INVALID_STABLE_IDENTITY", "Stable identity array is not exact")
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


def _fail(code: str, message: str) -> NoReturn:
    raise Stage04ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be lowercase canonical SHA-256 text")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 4 path names HOLDOUT")


def validate_stage04_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not the pinned version")
    if unicodedata.unidata_version != EXPECTED_UNICODE_VERSION:
        _fail("UNICODE_VERSION_MISMATCH", "Unicode runtime is not the pinned version")
    if pa.__version__ != EXPECTED_PYARROW_VERSION:
        _fail("PYARROW_VERSION_MISMATCH", "PyArrow runtime is not the pinned version")


def lower_stage04_text(value: str) -> str:
    """Return exact locale-independent Python Unicode ``str.lower()`` output."""
    if not isinstance(value, str):
        _fail("INVALID_LOWERCASE_INPUT", "Stage 4 lowercase input must be a string")
    try:
        value.encode("utf-8", errors="strict")
        lowered = value.lower()
        lowered.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage04ValidationError(
            "INVALID_LOWERCASE_INPUT", "Stage 4 input is not valid Unicode text"
        ) from error
    return lowered


@lru_cache(maxsize=1)
def _script_reference() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


@lru_cache(maxsize=4_096)
def _script_for_codepoint(codepoint: int) -> str:
    return _script_reference().script_for(chr(codepoint))


@lru_cache(maxsize=4_096)
def _codepoint_has_case(codepoint: int) -> bool:
    character = chr(codepoint)
    return character.lower() != character or character.upper() != character


def classify_script_value(value: str) -> str:
    """Return a coarse Unicode Script diagnostic, never a language inference."""
    if value == "":
        return "EMPTY"
    if value.isascii():
        return "ASCII_ONLY"
    observed_bucket: str | None = None
    for character in value:
        codepoint = ord(character)
        if codepoint < 0x80:
            if not (0x41 <= codepoint <= 0x5A or 0x61 <= codepoint <= 0x7A):
                continue
            script = "Latin"
        else:
            script = _script_for_codepoint(codepoint)
            if script in _NON_DISTINCTIVE_SCRIPTS:
                continue
        bucket = "CJK_HANGUL" if script in _CJK_HANGUL_SCRIPTS else script
        if observed_bucket is None:
            observed_bucket = bucket
        elif observed_bucket != bucket:
            return "MIXED"
    if observed_bucket in {None, "Latin"}:
        return "LATIN_NON_ASCII"
    if observed_bucket == "Cyrillic":
        return "CYRILLIC"
    if observed_bucket == "Greek":
        return "GREEK"
    if observed_bucket == "Arabic":
        return "ARABIC_PERSIAN"
    if observed_bucket == "CJK_HANGUL":
        return "CJK_HANGUL"
    return "OTHER"


def stage04_schema() -> pa.Schema:
    fields = list(stage03_schema())
    fields.extend(
        pa.field(name, pa.string(), nullable=False) for name in LOWER_OUTPUT_COLUMNS
    )
    fields.extend(
        (
            pa.field("stage04_changed_fields", CHANGED_FIELDS_TYPE, nullable=False),
            pa.field("stage04_row_changed", pa.bool_(), nullable=False),
        )
    )
    return pa.schema(fields)


def stage04_schema_fingerprint() -> str:
    digest = hashlib.sha256(STAGE04_SCHEMA_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE04_SCHEMA_VERSION)
    schema = stage04_schema().remove_metadata()
    encoder.uint64(len(schema))
    for schema_field in schema:
        encoder.text(schema_field.name)
        encoder.text(str(schema_field.type))
        encoder.text(str(schema_field.nullable).lower())
    return digest.hexdigest()


def validate_stage04_input_binding(
    binding: Stage04InputBinding, *, authoritative_development: bool = False
) -> None:
    if binding.upstream_contract_version != STAGE03_CONTRACT_VERSION:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "Stage 3 contract version is not exact")
    if binding.upstream_profile_version != STAGE03_PROFILE_VERSION:
        _fail("UPSTREAM_PROFILE_MISMATCH", "Stage 3 profile version is not exact")
    if binding.upstream_schema_fingerprint != stage03_schema_fingerprint():
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 3 schema fingerprint is not exact")
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
        _fail("INVALID_ROW_COUNT", "Stage 4 expected row count is invalid")
    if authoritative_development and (
        binding.upstream_logical_fingerprint != ACCEPTED_STAGE03_LOGICAL_FINGERPRINT
        or binding.upstream_schema_fingerprint != ACCEPTED_STAGE03_SCHEMA_FINGERPRINT
        or binding.upstream_input_binding_sha256
        != ACCEPTED_STAGE03_INPUT_BINDING_SHA256
        or binding.upstream_manifest_sha256 != ACCEPTED_STAGE03_MANIFEST_SHA256
        or binding.upstream_ordered_identity_sha256
        != ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256
        or binding.input_benchmark_fingerprint != ACCEPTED_BENCHMARK_FINGERPRINT
        or binding.expected_row_count != ACCEPTED_DEVELOPMENT_ROWS
    ):
        _fail(
            "AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH",
            "Stage 4 does not bind the accepted 35k Stage 3 DEVELOPMENT boundary",
        )


def stage04_logical_dataset_sha256_v1(binding: Stage04InputBinding) -> str:
    validate_stage04_input_binding(binding)
    digest = hashlib.sha256(STAGE04_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        STAGE04_CONTRACT_VERSION,
        STAGE04_PROFILE_VERSION,
        STAGE04_SCHEMA_VERSION,
        STAGE04_TRANSFORMATION,
        EXPECTED_PYTHON_VERSION.__repr__(),
        EXPECTED_UNICODE_VERSION,
        "CASEFOLD_FALSE",
        "LOCALE_SPECIFIC_CASING_FALSE",
        "NORMALIZATION_AFTER_LOWER_NONE",
        "ASCII_FAST_PATH_EQUIVALENT_TO_PYTHON_LOWER",
        "ARROW_UTF8_LOWER_FORBIDDEN",
        binding.upstream_contract_version,
        binding.upstream_profile_version,
    ):
        encoder.text(value)
    for input_name, output_name in zip(
        LOWER_INPUT_COLUMNS, LOWER_OUTPUT_COLUMNS, strict=True
    ):
        encoder.text(input_name)
        encoder.text(output_name)
    for value in STAGE04_AUDIT_COLUMNS:
        encoder.text(value)
    encoder.digest(binding.upstream_logical_fingerprint)
    encoder.digest(binding.upstream_schema_fingerprint)
    encoder.digest(binding.upstream_ordered_identity_sha256)
    encoder.digest(binding.input_benchmark_fingerprint)
    encoder.digest(stage04_schema_fingerprint())
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
        raise Stage04ValidationError(
            "CONTROLLED_WRITE_FAILURE",
            "Controlled Stage 4 artifact could not be written",
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


def write_stage04_input_binding(path: Path, binding: Stage04InputBinding) -> str:
    validate_stage04_input_binding(binding)
    _reject_holdout_paths(path)
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 4 input binding already exists")
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


def load_stage04_input_binding(
    path: Path, *, expected_sha256: str, authoritative_development: bool = False
) -> Stage04InputBinding:
    _digest_bytes(expected_sha256)
    _reject_holdout_paths(path)
    _require_regular_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Input binding SHA-256 differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    expected_fields = {
        "stage04_input_binding_version",
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
        or value.get("stage04_input_binding_version") != STAGE04_INPUT_BINDING_VERSION
    ):
        _fail("INPUT_BINDING_INVALID", "Stage 4 input binding fields are not exact")
    binding = Stage04InputBinding(
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
    validate_stage04_input_binding(
        binding, authoritative_development=authoritative_development
    )
    return binding


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage04ValidationError(code, "Controlled JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON is not an object")
    return cast(dict[str, Any], value)


def _require_regular_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage04ValidationError(
            code, "Required artifact is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Required artifact is not a regular non-symlink file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage04ValidationError(
            code, "Required directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Required directory is not a regular non-symlink directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage04ValidationError(
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
        raise Stage04ValidationError(
            "ARTIFACT_READ_FAILURE", "Controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _output_metadata(
    binding: Stage04InputBinding, logical_fingerprint: str
) -> dict[bytes, bytes]:
    values = {
        "stage04_contract_version": STAGE04_CONTRACT_VERSION,
        "stage04_profile_version": STAGE04_PROFILE_VERSION,
        "stage04_schema_version": STAGE04_SCHEMA_VERSION,
        "stage04_schema_fingerprint": stage04_schema_fingerprint(),
        "stage04_logical_dataset_sha256_v1": logical_fingerprint,
        "transformation": STAGE04_TRANSFORMATION,
        "python_version": ".".join(str(value) for value in EXPECTED_PYTHON_VERSION),
        "unicode_version": EXPECTED_UNICODE_VERSION,
        "casefold_used": "false",
        "locale_specific_casing_used": "false",
        "normalization_after_lower": STAGE04_NORMALIZATION_AFTER_LOWER,
        "upstream_stage03_contract_version": binding.upstream_contract_version,
        "upstream_stage03_profile_version": binding.upstream_profile_version,
        "upstream_stage03_logical_fingerprint": binding.upstream_logical_fingerprint,
        "upstream_stage03_schema_fingerprint": binding.upstream_schema_fingerprint,
        "upstream_stage03_input_binding_sha256": (
            binding.upstream_input_binding_sha256
        ),
        "upstream_stage03_manifest_sha256": binding.upstream_manifest_sha256,
        "upstream_ordered_identity_sha256": binding.upstream_ordered_identity_sha256,
        "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _project_batch(
    batch: pa.RecordBatch, *, metadata: Mapping[bytes, bytes]
) -> pa.RecordBatch:
    if not batch.schema.remove_metadata().equals(
        stage03_schema(), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 4 input batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("UPSTREAM_NULL", "Stage 4 input contains an unexpected null")
    changed_fields: list[list[str]] = [[] for _ in range(batch.num_rows)]
    lower_arrays: list[pa.Array] = []
    for source_name, input_name in zip(
        CLEAN_SOURCE_COLUMNS, LOWER_INPUT_COLUMNS, strict=True
    ):
        values = batch.column(batch.schema.get_field_index(input_name))
        lowered = _lower_array(values)
        lower_arrays.append(lowered)
        for index_scalar in pc.indices_nonzero(pc.not_equal(values, lowered)):
            changed_fields[cast(int, index_scalar.as_py())].append(source_name)
    arrays = [batch.column(index) for index in range(batch.num_columns)]
    arrays.extend(lower_arrays)
    arrays.extend(
        (
            pa.array(changed_fields, type=CHANGED_FIELDS_TYPE, from_pandas=False),
            pa.array(
                [bool(names) for names in changed_fields],
                type=pa.bool_(),
                from_pandas=False,
            ),
        )
    )
    return pa.RecordBatch.from_arrays(
        arrays, schema=stage04_schema().with_metadata(dict(metadata))
    )


def _lower_array(values: pa.Array) -> pa.Array:
    """Use the ASCII-equivalent fast path and Python for every Unicode value."""
    if not pa.types.is_string(values.type) or values.null_count:
        _fail("UPSTREAM_TYPE_MISMATCH", "Stage 4 clean array is not exact text")
    ascii_mask = cast(pa.Array, pc.string_is_ascii(values))
    ascii_lowered = cast(pa.Array, pc.ascii_lower(values))
    projected_values: list[str | None] = [None] * len(values)
    for index_scalar in pc.indices_nonzero(pc.invert(ascii_mask)):
        row_index = cast(int, index_scalar.as_py())
        raw = values[row_index].as_py()
        if not isinstance(raw, str):
            _fail("UPSTREAM_TYPE_MISMATCH", "Stage 4 clean value is not text")
        projected_values[row_index] = lower_stage04_text(raw)
    python_lowered = pa.array(
        projected_values, type=pa.string(), from_pandas=False, safe=True
    )
    return cast(pa.Array, pc.if_else(ascii_mask, ascii_lowered, python_lowered))


def _validate_output_batch(batch: pa.RecordBatch, *, metrics: Stage04Metrics) -> None:
    if not batch.schema.remove_metadata().equals(
        stage04_schema(), check_metadata=False
    ):
        _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 4 output batch schema is not exact")
    if any(batch.column(index).null_count for index in range(batch.num_columns)):
        _fail("OUTPUT_NULL", "Stage 4 output contains an unexpected null")
    details = batch.column(batch.schema.get_field_index("stage04_changed_fields"))
    flags = batch.column(batch.schema.get_field_index("stage04_row_changed"))
    expected_by_row: list[list[str]] = [[] for _ in range(batch.num_rows)]
    changed_groups_by_row: list[set[str]] = [set() for _ in range(batch.num_rows)]
    for source_name, input_name, output_name in zip(
        CLEAN_SOURCE_COLUMNS, LOWER_INPUT_COLUMNS, LOWER_OUTPUT_COLUMNS, strict=True
    ):
        inputs = batch.column(batch.schema.get_field_index(input_name))
        outputs = batch.column(batch.schema.get_field_index(output_name))
        for row_index in range(batch.num_rows):
            before = inputs[row_index].as_py()
            after = outputs[row_index].as_py()
            if not isinstance(before, str) or not isinstance(after, str):
                _fail("OUTPUT_TYPE_MISMATCH", "Stage 4 lowercase value is not text")
            expected = before.lower()
            if after != expected:
                _fail(
                    "LOWERCASE_SEMANTIC_MISMATCH",
                    "Stage 4 output differs from exact Python str.lower()",
                )
            metrics.observe_value(source_name=source_name, before=before, after=after)
            if before != after:
                expected_by_row[row_index].append(source_name)
                changed_groups_by_row[row_index].add(FIELD_GROUP_BY_COLUMN[source_name])
    for row_index, expected_fields in enumerate(expected_by_row):
        observed_fields = details[row_index].as_py()
        changed_flag = flags[row_index].as_py()
        if observed_fields != expected_fields:
            _fail("CHANGE_AUDIT_MISMATCH", "Changed fields are absent or out of order")
        if not isinstance(changed_flag, bool) or changed_flag != bool(expected_fields):
            _fail("CHANGE_AUDIT_MISMATCH", "Row change flag is inconsistent")
        metrics.observe_row(changed_groups=changed_groups_by_row[row_index])
    metrics.finish_batch(batch.num_rows)


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
                "stage03_row_changed",
                "stage04_row_changed",
            ],
            write_page_checksum=True,
            store_schema=True,
            use_compliant_nested_type=True,
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage04ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 4 Parquet writer could not start"
        ) from error
    path.chmod(0o600)
    return writer


def _iter_bounded_batches(
    parquet: pq.ParquetFile, *, batch_rows: int, target_batch_bytes: int
) -> Iterable[pa.RecordBatch]:
    for row_group_index in range(parquet.metadata.num_row_groups):
        row_group = parquet.metadata.row_group(row_group_index)
        if row_group.num_rows < 1:
            _fail("PARQUET_READ_FAILURE", "Stage 4 encountered an empty row group")
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
            _fail("OUTPUT_ROW_MISMATCH", "Stage 4 output row group is not bounded")
        yield from parquet.iter_batches(
            batch_size=maximum_batch_rows,
            row_groups=[row_group_index],
            use_threads=False,
        )


def _stage03_artifacts(
    root: Path, binding: Stage04InputBinding
) -> tuple[Stage04ArtifactIdentity, ...]:
    try:
        validate_stage03_bundle(
            root, expected_manifest_sha256=binding.upstream_manifest_sha256
        )
    except Stage03ValidationError as error:
        raise Stage04ValidationError(
            "STAGE03_BUNDLE_INVALID", "Accepted Stage 3 bundle validation failed"
        ) from error
    manifest = _load_json(root / STAGE03_MANIFEST_NAME, "STAGE03_MANIFEST_INVALID")
    success = _load_json(root / STAGE03_SUCCESS_MARKER, "STAGE03_BUNDLE_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 identity is malformed")
    ordered = physical.get("ordered_identity_validation")
    if not isinstance(ordered, dict):
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 ordered identity is malformed")
    if (
        scientific.get("stage03_contract_version") != binding.upstream_contract_version
        or scientific.get("stage03_profile_version") != binding.upstream_profile_version
        or scientific.get("stage03_schema_version") != STAGE03_SCHEMA_VERSION
        or scientific.get("stage03_schema_fingerprint")
        != binding.upstream_schema_fingerprint
        or scientific.get("stage03_logical_dataset_sha256_v1")
        != binding.upstream_logical_fingerprint
        or scientific.get("input_benchmark_fingerprint")
        != binding.input_benchmark_fingerprint
        or scientific.get("row_count") != binding.expected_row_count
        or physical.get("stage03_input_binding_sha256")
        != binding.upstream_input_binding_sha256
        or physical.get("upstream_stage02_manifest_sha256") is None
        or ordered.get("output_ordered_stable_identity_sha256_v1")
        != binding.upstream_ordered_identity_sha256
        or success.get("row_count") != binding.expected_row_count
    ):
        _fail("STAGE03_IDENTITY_MISMATCH", "Stage 3 scientific binding differs")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifacts are absent")
    artifacts: list[Stage04ArtifactIdentity] = []
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE03_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE03_MANIFEST_INVALID", "Stage 3 artifact order is not exact")
        artifact = Stage04ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE03_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE03_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE03_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        artifacts.append(artifact)
    return tuple(artifacts)


def _input_artifact_snapshot(
    root: Path, artifact: Stage04ArtifactIdentity
) -> tuple[Path, tuple[int, int, int, int, str]]:
    path = root / artifact.relative_path
    _require_regular_file(path, "STAGE03_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    observed = path.stat(follow_symlinks=False)
    sha256 = _sha256_file(path)
    if observed.st_size != artifact.size_bytes or sha256 != artifact.sha256:
        _fail("STAGE03_ARTIFACT_MISMATCH", "Stage 3 artifact identity differs")
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
        _fail("INPUT_CHANGED", "Stage 3 input changed during Stage 4")


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
            stage03_schema(), check_metadata=False
        ):
            _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 3 Parquet schema is not exact")
        batches = _iter_bounded_batches(
            parquet, batch_rows=batch_rows, target_batch_bytes=target_batch_bytes
        )
    except Stage04ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage04ValidationError(
            "PARQUET_READ_FAILURE", "Stage 3 input could not be opened safely"
        ) from error
    writer = _new_writer(output_path, stage04_schema().with_metadata(dict(metadata)))
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
    except Stage04ValidationError:
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
        raise Stage04ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 4 Parquet output could not be written"
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
    metrics: Stage04Metrics,
    output_identities: _OrderedStableIdentityHasher,
) -> str:
    try:
        input_file = pq.ParquetFile(input_path, page_checksum_verification=True)
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        if not output_file.schema_arrow.equals(
            stage04_schema().with_metadata(dict(metadata)), check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 4 output schema is not exact")
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
                _fail("OUTPUT_ROW_MISMATCH", "Stage 4 batch topology differs")
            assert isinstance(input_batch, pa.RecordBatch)
            assert isinstance(output_batch, pa.RecordBatch)
            if input_batch.num_rows != output_batch.num_rows:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 4 batch row count differs")
            for index in range(len(stage03_schema())):
                if not input_batch.column(index).equals(output_batch.column(index)):
                    _fail(
                        "UPSTREAM_VALUE_MISMATCH",
                        "Stage 4 changed an incoming Stage 3 value or row order",
                    )
            _validate_output_batch(output_batch, metrics=metrics)
            stable_ids = output_batch.column(
                output_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            output_identities.update(stable_ids)
            shard_identities.update(stable_ids)
        return shard_identities.hexdigest()
    except Stage04ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage04ValidationError(
            "PARQUET_READBACK_FAILURE", "Stage 4 independent read-back failed"
        ) from error


def _assert_published_upstream_equal(
    input_path: Path,
    output_path: Path,
    *,
    batch_rows: int,
    target_batch_bytes: int,
) -> int:
    """Reopen published output and independently compare every Stage 3 column."""
    try:
        input_file = pq.ParquetFile(input_path, page_checksum_verification=True)
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        input_batches = _iter_bounded_batches(
            input_file, batch_rows=batch_rows, target_batch_bytes=target_batch_bytes
        )
        output_batches = _iter_output_batches(
            output_file, maximum_batch_rows=batch_rows
        )
        rows = 0
        sentinel = object()
        for input_batch, output_batch in zip_longest(
            input_batches, output_batches, fillvalue=sentinel
        ):
            if input_batch is sentinel or output_batch is sentinel:
                _fail("OUTPUT_ROW_MISMATCH", "Published Stage 4 topology differs")
            assert isinstance(input_batch, pa.RecordBatch)
            assert isinstance(output_batch, pa.RecordBatch)
            if input_batch.num_rows != output_batch.num_rows:
                _fail("OUTPUT_ROW_MISMATCH", "Published Stage 4 rows differ")
            for index in range(len(stage03_schema())):
                if not input_batch.column(index).equals(output_batch.column(index)):
                    _fail(
                        "UPSTREAM_VALUE_MISMATCH",
                        "Published Stage 4 changed an incoming Stage 3 value",
                    )
            rows += output_batch.num_rows
        return rows
    except Stage04ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage04ValidationError(
            "PARQUET_READBACK_FAILURE",
            "Published Stage 3/Stage 4 comparison failed",
        ) from error


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage04ArtifactIdentity:
    path = root / relative_path
    _require_regular_file(path, "STAGE04_ARTIFACT_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage04ArtifactIdentity(
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


def materialize_stage04(config: Stage04RunConfig) -> Stage04MaterializationOutcome:
    """Materialize exact lowercase derivatives for an accepted Stage 3 bundle."""
    config.validate()
    validate_stage04_runtime()
    if config.production:
        require_goethe_nhr_slurm("stage04-lowercase-canonical")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 4 output directory already exists")
    binding = load_stage04_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
        authoritative_development=config.authoritative_development,
    )
    artifacts = _stage03_artifacts(config.stage03_output_directory, binding)
    logical_fingerprint = stage04_logical_dataset_sha256_v1(binding)
    metadata = _output_metadata(binding, logical_fingerprint)

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE04_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 4 temporary output already exists")
    temporary.mkdir(mode=0o700)
    data_directory = temporary / "data"
    data_directory.mkdir(mode=0o700)
    _write_json_exclusive(
        temporary / STAGE04_IN_PROGRESS_MARKER, {"status": "STAGE04_INCOMPLETE"}
    )

    metrics = Stage04Metrics()
    input_identities = _OrderedStableIdentityHasher()
    output_identities = _OrderedStableIdentityHasher()
    shard_identity_evidence: list[dict[str, str | int]] = []
    output_artifacts: list[Stage04ArtifactIdentity] = []
    for sequence, artifact in enumerate(artifacts, start=1):
        input_path, snapshot = _input_artifact_snapshot(
            config.stage03_output_directory, artifact
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
            output_identities=output_identities,
        )
        if input_digest != output_digest:
            _fail("STABLE_IDENTITY_MISMATCH", "Shard identity ordering differs")
        _assert_input_unchanged(input_path, snapshot, artifact.sha256)
        if rows != artifact.row_count:
            _fail("ROW_COUNT_MISMATCH", "Stage 4 shard row count differs")
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
    ordered_digest = output_identities.hexdigest()
    if (
        metrics.output_rows != binding.expected_row_count
        or input_identities.row_count != binding.expected_row_count
        or output_identities.row_count != binding.expected_row_count
    ):
        _fail("ROW_COUNT_MISMATCH", "Stage 4 total row count differs")
    if (
        input_identities.hexdigest() != ordered_digest
        or ordered_digest != binding.upstream_ordered_identity_sha256
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Stable identity stream is not exact")
    if metrics.nonempty_to_empty or metrics.empty_to_nonempty:
        _fail("UNEXPECTED_EMPTY_TRANSITION", "Lowercase changed string emptiness")
    if metrics.idempotence_failures:
        _fail("IDEMPOTENCE_FAILURE", "Stage 4 lowercase is not idempotent")
    metric_groups = metrics.to_metric_groups()
    manifest = {
        "stage04_manifest_version": STAGE04_MANIFEST_VERSION,
        "status": "STAGE_4_DEVELOPMENT_CANDIDATE_MATERIALIZED",
        "scientific_identity": {
            "stage04_contract_version": STAGE04_CONTRACT_VERSION,
            "stage04_profile_version": STAGE04_PROFILE_VERSION,
            "stage04_schema_version": STAGE04_SCHEMA_VERSION,
            "stage04_schema_fingerprint": stage04_schema_fingerprint(),
            "stage04_logical_dataset_sha256_v1": logical_fingerprint,
            "lower_input_columns": list(LOWER_INPUT_COLUMNS),
            "lower_output_columns": list(LOWER_OUTPUT_COLUMNS),
            "transformation": STAGE04_TRANSFORMATION,
            "casefold_used": STAGE04_CASEFOLD_USED,
            "locale_specific_casing_used": STAGE04_LOCALE_SPECIFIC_CASING_USED,
            "normalization_after_lower": STAGE04_NORMALIZATION_AFTER_LOWER,
            "python_version": ".".join(str(value) for value in EXPECTED_PYTHON_VERSION),
            "unicode_version": EXPECTED_UNICODE_VERSION,
            "upstream_stage03_contract_version": binding.upstream_contract_version,
            "upstream_stage03_profile_version": binding.upstream_profile_version,
            "upstream_stage03_logical_fingerprint": (
                binding.upstream_logical_fingerprint
            ),
            "upstream_stage03_schema_fingerprint": binding.upstream_schema_fingerprint,
            "upstream_stage03_input_binding_sha256": (
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
            "stage04_input_binding_sha256": config.expected_input_binding_sha256,
            "upstream_stage03_manifest_sha256": binding.upstream_manifest_sha256,
            "input_artifacts": [item.to_dict() for item in artifacts],
            "output_artifacts": [item.to_dict() for item in output_artifacts],
            "owner_only_permissions": True,
            "bounded_memory_architecture": {
                "maximum_configured_batch_rows": config.batch_rows,
                "target_uncompressed_batch_bytes": config.target_batch_bytes,
                "memory_scales_with_total_row_count": False,
                "total_row_python_identity_set_used": False,
                "review_selection_maximum_rows": 500,
            },
            "ordered_identity_validation": {
                "ordered_identity_contract_version": STAGE04_ORDERED_IDENTITY_VERSION,
                "upstream_duplicate_free_invariant_bound": True,
                "input_ordered_stable_identity_sha256_v1": (
                    input_identities.hexdigest()
                ),
                "output_ordered_stable_identity_sha256_v1": ordered_digest,
                "row_count": output_identities.row_count,
                "shards": shard_identity_evidence,
            },
        },
        "validation": {
            "validation_contract_version": STAGE04_VALIDATION_VERSION,
            "upstream_stage03_bundle_validated": "PASS",
            "accepted_stage03_boundary_bound": "PASS",
            "row_count_preserved": "PASS",
            "stable_source_row_id_preserved": "PASS",
            "ordered_stable_identity_fingerprint_equal": "PASS",
            "all_stage03_fields_preserved": "PASS",
            "exact_python_lower_semantics": "PASS",
            "ascii_fast_path_equivalence": "PASS",
            "arrow_utf8_lower_not_used": "PASS",
            "casefold_not_used": "PASS",
            "locale_specific_casing_not_used": "PASS",
            "normalization_after_lower_not_used": "PASS",
            "change_audit_consistency": "PASS",
            "idempotence_all_lowercase_values": "PASS",
            "no_empty_transitions": "PASS",
            "parquet_page_checksum_readback": "PASS",
            "bounded_memory_validation": "PASS",
            "holdout_exclusion": "PASS",
            "owner_only_permissions": "PASS",
            "atomic_publication": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "unicode_version": unicodedata.unidata_version,
            "pyarrow_version": pa.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json_exclusive(temporary / STAGE04_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(
        temporary, STAGE04_MANIFEST_NAME, row_count=0
    )
    _write_json_exclusive(
        temporary / STAGE04_SUCCESS_MARKER,
        {
            "status": "STAGE_4_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "stage04_manifest_sha256": manifest_identity.sha256,
            "stage04_manifest_size_bytes": manifest_identity.size_bytes,
            "stage04_input_binding_sha256": config.expected_input_binding_sha256,
            "stage04_logical_dataset_sha256_v1": logical_fingerprint,
            "stage04_schema_fingerprint": stage04_schema_fingerprint(),
            "ordered_stable_identity_sha256_v1": ordered_digest,
            "row_count": metrics.output_rows,
            "output_shard_count": len(output_artifacts),
        },
    )
    (temporary / STAGE04_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(data_directory)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return validate_stage04_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_identity.sha256,
        authoritative_development=config.authoritative_development,
    )


def _observed_topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            path = current / name
            if path.is_symlink():
                _fail("UNSAFE_OUTPUT", "Stage 4 output contains a symlink")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "UNSAFE_OUTPUT")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def _binding_from_manifest(manifest: Mapping[str, Any]) -> Stage04InputBinding:
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 identity is malformed")
    return Stage04InputBinding(
        upstream_contract_version=_required_text(
            scientific.get("upstream_stage03_contract_version"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_profile_version=_required_text(
            scientific.get("upstream_stage03_profile_version"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_logical_fingerprint=_required_text(
            scientific.get("upstream_stage03_logical_fingerprint"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_schema_fingerprint=_required_text(
            scientific.get("upstream_stage03_schema_fingerprint"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_input_binding_sha256=_required_text(
            scientific.get("upstream_stage03_input_binding_sha256"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_manifest_sha256=_required_text(
            physical.get("upstream_stage03_manifest_sha256"),
            "STAGE04_MANIFEST_INVALID",
        ),
        upstream_ordered_identity_sha256=_required_text(
            scientific.get("upstream_ordered_identity_sha256"),
            "STAGE04_MANIFEST_INVALID",
        ),
        input_benchmark_fingerprint=_required_text(
            scientific.get("input_benchmark_fingerprint"), "STAGE04_MANIFEST_INVALID"
        ),
        expected_row_count=_required_uint(
            scientific.get("row_count"), "STAGE04_MANIFEST_INVALID"
        ),
    )


def _validated_metrics(value: object) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 metrics are malformed")
    expected_groups = set(Stage04Metrics().to_metric_groups())
    if set(value) != expected_groups:
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 metric groups are not exact")
    result: dict[str, dict[str, int]] = {}
    for group, raw_metrics in value.items():
        if not isinstance(group, str) or not isinstance(raw_metrics, dict):
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 metrics are malformed")
        metrics: dict[str, int] = {}
        for name, raw_count in raw_metrics.items():
            if (
                not isinstance(name, str)
                or not isinstance(raw_count, int)
                or isinstance(raw_count, bool)
                or raw_count < 0
            ):
                _fail("STAGE04_MANIFEST_INVALID", "Stage 4 metric value is invalid")
            metrics[name] = raw_count
        result[group] = metrics
    return result


def validate_stage04_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    authoritative_development: bool = True,
    stage03_output_directory: Path | None = None,
) -> Stage04MaterializationOutcome:
    """Independently recompute and validate a published Stage 4 bundle."""
    validate_stage04_runtime()
    _digest_bytes(expected_manifest_sha256)
    _reject_holdout_paths(output_directory)
    if stage03_output_directory is not None:
        _reject_holdout_paths(stage03_output_directory)
    _require_directory(output_directory, "STAGE04_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    if (output_directory / STAGE04_IN_PROGRESS_MARKER).exists():
        _fail("STAGE04_INCOMPLETE", "Stage 4 retains an in-progress marker")
    data_directory = output_directory / "data"
    _require_directory(data_directory, "STAGE04_OUTPUT_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    directories, files = _observed_topology(output_directory)
    if directories != {"data"}:
        _fail("STAGE04_ARTIFACT_MISMATCH", "Stage 4 directory topology is invalid")
    manifest_path = output_directory / STAGE04_MANIFEST_NAME
    success_path = output_directory / STAGE04_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE04_TERMINAL_MISSING")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE04_MANIFEST_SHA256_MISMATCH", "Stage 4 manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE04_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE04_SUCCESS_INVALID")
    if (
        manifest.get("stage04_manifest_version") != STAGE04_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_4_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_4_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage04_manifest_sha256") != manifest_sha
        or success.get("stage04_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
    ):
        _fail("STAGE04_TERMINAL_MISMATCH", "Stage 4 terminal state differs")
    binding = _binding_from_manifest(manifest)
    validate_stage04_input_binding(
        binding, authoritative_development=authoritative_development
    )
    logical_fingerprint = stage04_logical_dataset_sha256_v1(binding)
    scientific = cast(dict[str, Any], manifest["scientific_identity"])
    physical = cast(dict[str, Any], manifest["physical_identity"])
    validation = manifest.get("validation")
    if (
        scientific.get("stage04_contract_version") != STAGE04_CONTRACT_VERSION
        or scientific.get("stage04_profile_version") != STAGE04_PROFILE_VERSION
        or scientific.get("stage04_schema_version") != STAGE04_SCHEMA_VERSION
        or scientific.get("stage04_schema_fingerprint") != stage04_schema_fingerprint()
        or scientific.get("stage04_logical_dataset_sha256_v1") != logical_fingerprint
        or scientific.get("lower_input_columns") != list(LOWER_INPUT_COLUMNS)
        or scientific.get("lower_output_columns") != list(LOWER_OUTPUT_COLUMNS)
        or scientific.get("transformation") != STAGE04_TRANSFORMATION
        or scientific.get("casefold_used") is not False
        or scientific.get("locale_specific_casing_used") is not False
        or scientific.get("normalization_after_lower")
        != STAGE04_NORMALIZATION_AFTER_LOWER
        or scientific.get("python_version")
        != ".".join(str(value) for value in EXPECTED_PYTHON_VERSION)
        or scientific.get("unicode_version") != EXPECTED_UNICODE_VERSION
        or success.get("stage04_logical_dataset_sha256_v1") != logical_fingerprint
        or success.get("stage04_schema_fingerprint") != stage04_schema_fingerprint()
    ):
        _fail("STAGE04_FINGERPRINT_MISMATCH", "Stage 4 scientific identity differs")
    input_binding_sha = _required_text(
        physical.get("stage04_input_binding_sha256"), "STAGE04_MANIFEST_INVALID"
    )
    _digest_bytes(input_binding_sha)
    if success.get("stage04_input_binding_sha256") != input_binding_sha:
        _fail("STAGE04_TERMINAL_MISMATCH", "Stage 4 input binding differs")
    bounded = physical.get("bounded_memory_architecture")
    if not isinstance(bounded, dict) or set(bounded) != {
        "maximum_configured_batch_rows",
        "target_uncompressed_batch_bytes",
        "memory_scales_with_total_row_count",
        "total_row_python_identity_set_used",
        "review_selection_maximum_rows",
    }:
        _fail("STAGE04_MANIFEST_INVALID", "Bounded-memory evidence is malformed")
    maximum_batch_rows = _required_uint(
        bounded.get("maximum_configured_batch_rows"), "STAGE04_MANIFEST_INVALID"
    )
    target_batch_bytes = _required_uint(
        bounded.get("target_uncompressed_batch_bytes"), "STAGE04_MANIFEST_INVALID"
    )
    if (
        maximum_batch_rows < 1
        or target_batch_bytes < 1
        or bounded.get("memory_scales_with_total_row_count") is not False
        or bounded.get("total_row_python_identity_set_used") is not False
        or bounded.get("review_selection_maximum_rows") != 500
        or physical.get("owner_only_permissions") is not True
    ):
        _fail("STAGE04_MANIFEST_INVALID", "Bounded-memory evidence differs")
    if (
        not isinstance(validation, dict)
        or validation.get("validation_contract_version") != STAGE04_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE04_VALIDATION_INCOMPLETE", "Stage 4 validation is incomplete")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifacts are absent")
    output_artifacts: list[Stage04ArtifactIdentity] = []
    expected_files = {STAGE04_MANIFEST_NAME, STAGE04_SUCCESS_MARKER}
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifact is malformed")
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE04_MANIFEST_INVALID"
        )
        if relative_path != f"data/part-{sequence:06d}.parquet":
            _fail("STAGE04_MANIFEST_INVALID", "Stage 4 artifact order differs")
        artifact = Stage04ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE04_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE04_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE04_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        output_artifacts.append(artifact)
        expected_files.add(relative_path)
    if files != expected_files:
        _fail("STAGE04_ARTIFACT_MISMATCH", "Stage 4 artifact topology is incomplete")
    if stage03_output_directory is not None:
        upstream_artifacts = _stage03_artifacts(stage03_output_directory, binding)
        if len(upstream_artifacts) != len(output_artifacts):
            _fail("OUTPUT_ROW_MISMATCH", "Published Stage 4 shard count differs")
        compared_rows = 0
        for upstream_artifact, output_artifact in zip(
            upstream_artifacts, output_artifacts, strict=True
        ):
            if (
                upstream_artifact.relative_path != output_artifact.relative_path
                or upstream_artifact.row_count != output_artifact.row_count
            ):
                _fail("OUTPUT_ROW_MISMATCH", "Published Stage 4 shards differ")
            input_path, snapshot = _input_artifact_snapshot(
                stage03_output_directory, upstream_artifact
            )
            output_path = output_directory / output_artifact.relative_path
            _require_regular_file(output_path, "STAGE04_ARTIFACT_INVALID")
            _require_mode(output_path, 0o600, "PERMISSION_FAILURE")
            if (
                output_path.stat(follow_symlinks=False).st_size
                != output_artifact.size_bytes
                or _sha256_file(output_path) != output_artifact.sha256
            ):
                _fail("STAGE04_ARTIFACT_MISMATCH", "Stage 4 artifact identity differs")
            compared_rows += _assert_published_upstream_equal(
                input_path,
                output_path,
                batch_rows=maximum_batch_rows,
                target_batch_bytes=target_batch_bytes,
            )
            _assert_input_unchanged(input_path, snapshot, upstream_artifact.sha256)
        if compared_rows != binding.expected_row_count:
            _fail("ROW_COUNT_MISMATCH", "Published upstream comparison is incomplete")
    ordered = physical.get("ordered_identity_validation")
    if not isinstance(ordered, dict):
        _fail("STAGE04_MANIFEST_INVALID", "Ordered identity evidence is malformed")
    output_identity_digest = _required_text(
        ordered.get("output_ordered_stable_identity_sha256_v1"),
        "STAGE04_MANIFEST_INVALID",
    )
    input_identity_digest = _required_text(
        ordered.get("input_ordered_stable_identity_sha256_v1"),
        "STAGE04_MANIFEST_INVALID",
    )
    _digest_bytes(input_identity_digest)
    _digest_bytes(output_identity_digest)
    raw_shards = ordered.get("shards")
    if (
        ordered.get("ordered_identity_contract_version")
        != STAGE04_ORDERED_IDENTITY_VERSION
        or ordered.get("upstream_duplicate_free_invariant_bound") is not True
        or ordered.get("row_count") != binding.expected_row_count
        or input_identity_digest != output_identity_digest
        or output_identity_digest != binding.upstream_ordered_identity_sha256
        or not isinstance(raw_shards, list)
        or len(raw_shards) != len(output_artifacts)
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Ordered identity evidence differs")
    expected_metadata = _output_metadata(binding, logical_fingerprint)
    observed_metrics = Stage04Metrics()
    observed_identities = _OrderedStableIdentityHasher()
    for artifact, shard_evidence in zip(output_artifacts, raw_shards, strict=True):
        if not isinstance(shard_evidence, dict):
            _fail("STAGE04_MANIFEST_INVALID", "Shard identity evidence is malformed")
        shard_digest = _required_text(
            shard_evidence.get("output_ordered_stable_identity_sha256_v1"),
            "STAGE04_MANIFEST_INVALID",
        )
        shard_input = _required_text(
            shard_evidence.get("input_ordered_stable_identity_sha256_v1"),
            "STAGE04_MANIFEST_INVALID",
        )
        _digest_bytes(shard_digest)
        _digest_bytes(shard_input)
        if (
            shard_evidence.get("relative_path") != artifact.relative_path
            or shard_evidence.get("row_count") != artifact.row_count
            or shard_input != shard_digest
        ):
            _fail("STABLE_IDENTITY_MISMATCH", "Shard identity evidence differs")
        path = output_directory / artifact.relative_path
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("STAGE04_ARTIFACT_MISMATCH", "Stage 4 artifact identity differs")
        try:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            if not parquet.schema_arrow.equals(
                stage04_schema().with_metadata(expected_metadata), check_metadata=True
            ):
                _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 4 output schema is not exact")
            shard_rows = 0
            shard_hasher = _OrderedStableIdentityHasher()
            for batch in _iter_bounded_batches(
                parquet,
                batch_rows=maximum_batch_rows,
                target_batch_bytes=target_batch_bytes,
            ):
                _validate_output_batch(batch, metrics=observed_metrics)
                stable_ids = batch.column(
                    batch.schema.get_field_index("stable_source_row_id_v1")
                )
                observed_identities.update(stable_ids)
                shard_hasher.update(stable_ids)
                shard_rows += batch.num_rows
            if (
                shard_rows != artifact.row_count
                or shard_hasher.hexdigest() != shard_digest
            ):
                _fail("ROW_COUNT_MISMATCH", "Stage 4 shard evidence differs")
        except Stage04ValidationError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise Stage04ValidationError(
                "PARQUET_READBACK_FAILURE", "Stage 4 page-checksum read-back failed"
            ) from error
    if (
        observed_metrics.output_rows != binding.expected_row_count
        or observed_identities.row_count != binding.expected_row_count
        or observed_identities.hexdigest() != output_identity_digest
    ):
        _fail("ROW_COUNT_MISMATCH", "Stage 4 total identity stream differs")
    recorded_metrics = _validated_metrics(manifest.get("development_metrics"))
    if observed_metrics.to_metric_groups() != recorded_metrics:
        _fail("STAGE04_METRIC_MISMATCH", "Stage 4 aggregate metrics differ")
    if (
        recorded_metrics["OUTPUT_EFFECTS"]["NONEMPTY_TO_EMPTY_FIELDS"] != 0
        or recorded_metrics["OUTPUT_EFFECTS"]["EMPTY_TO_NONEMPTY_FIELDS"] != 0
        or recorded_metrics["OUTPUT_EFFECTS"]["IDEMPOTENCE_FAILURES"] != 0
    ):
        _fail("STAGE04_SCIENTIFIC_GATE_FAILURE", "Stage 4 terminal gates failed")
    if (
        success.get("row_count") != observed_metrics.output_rows
        or success.get("output_shard_count") != len(output_artifacts)
        or success.get("ordered_stable_identity_sha256_v1") != output_identity_digest
    ):
        _fail("STAGE04_TERMINAL_MISMATCH", "Stage 4 terminal counts differ")
    return Stage04MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=logical_fingerprint,
        schema_fingerprint=stage04_schema_fingerprint(),
        input_binding_sha256=input_binding_sha,
        manifest_sha256=manifest_sha,
        ordered_identity_sha256=output_identity_digest,
        row_count=observed_metrics.output_rows,
        output_shard_count=len(output_artifacts),
        metrics=recorded_metrics,
    )


__all__ = [
    "ACCEPTED_BENCHMARK_FINGERPRINT",
    "ACCEPTED_DEVELOPMENT_ROWS",
    "ACCEPTED_STAGE03_INPUT_BINDING_SHA256",
    "ACCEPTED_STAGE03_LOGICAL_FINGERPRINT",
    "ACCEPTED_STAGE03_MANIFEST_SHA256",
    "ACCEPTED_STAGE03_ORDERED_IDENTITY_SHA256",
    "ACCEPTED_STAGE03_SCHEMA_FINGERPRINT",
    "CASE_CHANGE_CLASSES",
    "CHANGED_FIELDS_TYPE",
    "LOWER_INPUT_COLUMNS",
    "LOWER_OUTPUT_COLUMNS",
    "SCRIPT_CLASSES",
    "STAGE04_AUDIT_COLUMNS",
    "STAGE04_CONTRACT_VERSION",
    "STAGE04_INPUT_BINDING_VERSION",
    "STAGE04_MANIFEST_NAME",
    "STAGE04_PROFILE_VERSION",
    "STAGE04_SCHEMA_VERSION",
    "Stage04InputBinding",
    "Stage04MaterializationOutcome",
    "Stage04RunConfig",
    "Stage04ValidationError",
    "classify_script_value",
    "load_stage04_input_binding",
    "lower_stage04_text",
    "materialize_stage04",
    "stage04_logical_dataset_sha256_v1",
    "stage04_schema",
    "stage04_schema_fingerprint",
    "validate_stage04_bundle",
    "validate_stage04_input_binding",
    "validate_stage04_runtime",
    "write_stage04_input_binding",
]

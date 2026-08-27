from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import resource
import shutil
import stat
import struct
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, NoReturn, Protocol, Sequence, cast

import duckdb
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s03_cleaning import EXPECTED_PYARROW_VERSION, EXPECTED_PYTHON_VERSION
from .s05_reconstruction import (
    STAGE05_CONTRACT_VERSION,
    STAGE05_MANIFEST_NAME,
    STAGE05_PROFILE_VERSION,
    Stage05MaterializationOutcome,
    stage05_schema,
    validate_stage05_bundle,
)
from .s06_design_diagnostic import _collect_metrics

STAGE06_CONTRACT_VERSION = "stage06_early_exact_deduplication_contract_v1"
STAGE06_PROFILE_VERSION = "stage06_early_exact_deduplication_profile_v1"
STAGE06_INPUT_BINDING_VERSION = "stage06_input_binding_v1"
STAGE06_ROW_MAP_SCHEMA_VERSION = "stage06_row_map_schema_v1"
STAGE06_REGISTRY_SCHEMA_VERSION = "stage06_unique_candidate_registry_schema_v1"
STAGE06_SCHEMA_VERSION = "stage06_early_exact_deduplication_schema_v1"
STAGE06_VALIDATION_VERSION = "stage06_bundle_validation_v1"
STAGE06_MANIFEST_VERSION = "stage06_manifest_v1"
STAGE06_CANDIDATE_ID_VERSION = "stage06_exact_candidate_id_v1"
STAGE06_CANDIDATE_ID_DOMAIN = b"safe_geocoding_pipeline:stage06_exact_candidate_id_v1\0"
STAGE06_CONTRACT_FINGERPRINT_DOMAIN = b"SAFE_STAGE06_SCIENTIFIC_CONTRACT_V1"
STAGE06_SCHEMA_FINGERPRINT_DOMAIN = b"SAFE_STAGE06_COMBINED_ARROW_SCHEMA_V1"
STAGE06_ROW_MAP_LOGICAL_DOMAIN = b"SAFE_STAGE06_ROW_MAP_LOGICAL_V1"
STAGE06_REGISTRY_LOGICAL_DOMAIN = b"SAFE_STAGE06_REGISTRY_LOGICAL_V1"
STAGE06_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE06_LOGICAL_DATASET_V1"
STAGE06_ORDERED_IDENTITY_DOMAIN = b"SAFE_STAGE03_ORDERED_STABLE_IDENTITIES_V1"
STAGE06_ORDERED_IDENTITY_VERSION = "stage03_ordered_stable_identity_sha256_v1"
STAGE06_EXACT_COMPARISON = "EXACT_UTF8_BYTES"
STAGE06_SCOPE = "GLOBAL_STANDARD_NATIVE_ALL_SOURCE_ROWS"
STAGE06_UNAVAILABLE_RULE = "NULL_ID_NO_OCCURRENCE_NO_REGISTRY_ROW"
STAGE06_REGISTRY_ORDER = "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES"
STAGE06_SAME_ROW_EQUAL_RULE = "ONE_UNIQUE_TWO_OCCURRENCES_TWO_MAPPINGS"
STAGE06_CLEAN_SURFACE_RULE = "PRESERVE_UPSTREAM_EXCLUDE_FROM_KEY"
EXPECTED_DUCKDB_VERSION = "1.5.5"
DEFAULT_TARGET_BATCH_BYTES = 256 * 1024 * 1024
DEFAULT_HASH_CHUNK_CODEPOINTS = 1_048_576

STAGE06_MANIFEST_NAME = "stage06_manifest.json"
STAGE06_SUCCESS_MARKER = "_SUCCESS.json"
STAGE06_IN_PROGRESS_MARKER = "_IN_PROGRESS"
ROW_MAP_DIRECTORY = "row_map/data"
REGISTRY_DIRECTORY = "registry/data"

ACCEPTED_STAGE05_SCHEMA_FINGERPRINT = (
    "63d4cdb3707eda65c67cc5196891fa5005adce2b12eb7109554793c48c5303c3"
)
ACCEPTED_STAGE05_LOGICAL_FINGERPRINT = (
    "ba5829621fc15347d7cd4e168a48587bab896cd0be98924627876ae853dfaff2"
)
ACCEPTED_STAGE05_INPUT_BINDING_SHA256 = (
    "7e68c33f7daa482b442eca82c00c6904ec5e38bec1b3fc598d5be4d52a6bcb9f"
)
ACCEPTED_STAGE05_MANIFEST_SHA256 = (
    "fd945163e3be0242c43b98972350904631279cb99f366baadb0a3094ab6a1fc5"
)
ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256 = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_FIXED_500_FINGERPRINT = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
ACCEPTED_DEVELOPMENT_ROWS = 35_000

ROW_MAP_ID_COLUMNS = (
    "stage06_standard_exact_candidate_id",
    "stage06_native_exact_candidate_id",
)
REGISTRY_COLUMNS = (
    "stage06_exact_candidate_id",
    "stage06_candidate_lower",
    "stage06_occurrence_count",
    "stage06_standard_occurrence_count",
    "stage06_native_occurrence_count",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MEMORY_LIMIT_RE = re.compile(r"^[1-9][0-9]*(?:MB|GB)$")
_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"
_TYPE_BYTES = b"\x04"
_NULL_ID = b"\x00"
_PRESENT_ID = b"\x01"


class Stage06ValidationError(RuntimeError):
    """Privacy-safe, fail-closed Stage 6 validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class _Digest(Protocol):
    def update(self, value: bytes) -> None: ...

    def digest(self) -> bytes: ...

    def hexdigest(self) -> str: ...


DigestFactory = Callable[[], _Digest]


@dataclass(frozen=True, slots=True)
class Stage06InputBinding:
    upstream_contract_version: str
    upstream_profile_version: str
    upstream_logical_fingerprint: str
    upstream_schema_fingerprint: str
    upstream_input_binding_sha256: str
    upstream_manifest_sha256: str
    upstream_ordered_identity_sha256: str
    input_benchmark_fingerprint: str
    fixed_500_fingerprint: str
    expected_row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "stage06_input_binding_version": STAGE06_INPUT_BINDING_VERSION,
            "upstream_contract_version": self.upstream_contract_version,
            "upstream_profile_version": self.upstream_profile_version,
            "upstream_logical_fingerprint": self.upstream_logical_fingerprint,
            "upstream_schema_fingerprint": self.upstream_schema_fingerprint,
            "upstream_input_binding_sha256": self.upstream_input_binding_sha256,
            "upstream_manifest_sha256": self.upstream_manifest_sha256,
            "upstream_ordered_identity_sha256": self.upstream_ordered_identity_sha256,
            "input_benchmark_fingerprint": self.input_benchmark_fingerprint,
            "fixed_500_fingerprint": self.fixed_500_fingerprint,
            "expected_row_count": self.expected_row_count,
        }


@dataclass(frozen=True, slots=True)
class Stage06RunConfig:
    stage05_output_directory: Path
    input_binding_file: Path
    expected_input_binding_sha256: str
    output_directory: Path
    execution_git_sha: str
    production: bool = True
    authoritative_development: bool = True
    batch_rows: int = 2_048
    target_batch_bytes: int = DEFAULT_TARGET_BATCH_BYTES
    registry_batch_rows: int = 2_048
    registry_shard_rows: int = 1_000_000
    hash_chunk_codepoints: int = DEFAULT_HASH_CHUNK_CODEPOINTS
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        _digest_bytes(self.expected_input_binding_sha256)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git commit must be a full SHA")
        for bounded_value in (
            self.batch_rows,
            self.target_batch_bytes,
            self.registry_batch_rows,
            self.registry_shard_rows,
            self.hash_chunk_codepoints,
        ):
            if isinstance(bounded_value, bool) or bounded_value < 1:
                _fail("INVALID_BATCH_SIZE", "Stage 6 bounded size is invalid")
        if _MEMORY_LIMIT_RE.fullmatch(self.duckdb_memory_limit) is None:
            _fail("INVALID_MEMORY_LIMIT", "DuckDB memory limit is malformed")
        if (
            isinstance(self.duckdb_threads, bool)
            or self.duckdb_threads < 1
            or self.duckdb_threads > 64
        ):
            _fail("INVALID_THREAD_COUNT", "DuckDB thread count is invalid")
        _reject_holdout_paths(
            self.stage05_output_directory,
            self.input_binding_file,
            self.output_directory,
        )
        for key, metadata_value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(metadata_value, str)
                or not metadata_value
                or "\x00" in metadata_value
                or len(metadata_value) > 128
            ):
                _fail(
                    "INVALID_OPERATIONAL_METADATA",
                    "Operational metadata is outside the privacy-safe contract",
                )


@dataclass(frozen=True, slots=True)
class Stage06ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage06MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    row_map_logical_sha256_v1: str
    registry_logical_sha256_v1: str
    schema_fingerprint: str
    input_binding_sha256: str
    manifest_sha256: str
    ordered_identity_sha256: str
    row_count: int
    unique_candidate_count: int
    row_map_shard_count: int
    registry_shard_count: int
    metrics: Mapping[str, object]
    performance: Mapping[str, int | str]
    publication_validation_milliseconds: int = 0


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

    def bytes(self, value: bytes) -> None:
        self._digest.update(_TYPE_BYTES + struct.pack(">Q", len(value)) + value)


class _OrderedStableIdentityHasher:
    def __init__(self) -> None:
        self._digest = hashlib.sha256(STAGE06_ORDERED_IDENTITY_DOMAIN)
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


class _RowMapLogicalHasher:
    def __init__(self, contract_fingerprint: str) -> None:
        self._digest = hashlib.sha256(STAGE06_ROW_MAP_LOGICAL_DOMAIN)
        self._digest.update(_digest_bytes(contract_fingerprint))
        self.row_count = 0

    def update(
        self, stable_ids: pa.Array, standard_ids: pa.Array, native_ids: pa.Array
    ) -> None:
        if not (
            len(stable_ids) == len(standard_ids) == len(native_ids)
            and pa.types.is_fixed_size_binary(stable_ids.type)
            and stable_ids.type.byte_width == 32
            and not stable_ids.null_count
        ):
            _fail("ROW_MAP_LOGICAL_FAILURE", "Row-map logical arrays are invalid")
        for row_index in range(len(stable_ids)):
            stable = stable_ids[row_index].as_py()
            if not isinstance(stable, bytes) or len(stable) != 32:
                _fail("INVALID_STABLE_IDENTITY", "Stable identity is malformed")
            self._digest.update(stable)
            for values in (standard_ids, native_ids):
                value = values[row_index].as_py()
                if value is None:
                    self._digest.update(_NULL_ID)
                elif isinstance(value, bytes) and len(value) == 32:
                    self._digest.update(_PRESENT_ID + value)
                else:
                    _fail("ROW_MAP_LOGICAL_FAILURE", "Candidate ID is malformed")
            self.row_count += 1

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return digest.hexdigest()


class _RegistryLogicalHasher:
    def __init__(self, contract_fingerprint: str, *, chunk_codepoints: int) -> None:
        self._digest = hashlib.sha256(STAGE06_REGISTRY_LOGICAL_DOMAIN)
        self._digest.update(_digest_bytes(contract_fingerprint))
        self._chunk_codepoints = chunk_codepoints
        self.row_count = 0

    def update_row(
        self,
        candidate_id: bytes,
        candidate_lower: str,
        occurrence_count: int,
        standard_count: int,
        native_count: int,
    ) -> None:
        if len(candidate_id) != 32 or not candidate_lower:
            _fail("REGISTRY_LOGICAL_FAILURE", "Registry identity is malformed")
        self._digest.update(candidate_id)
        byte_length = _utf8_byte_length(candidate_lower, self._chunk_codepoints)
        self._digest.update(struct.pack(">Q", byte_length))
        _update_utf8(self._digest, candidate_lower, self._chunk_codepoints)
        if (
            isinstance(occurrence_count, bool)
            or not 0 < occurrence_count <= 0xFFFF_FFFF_FFFF_FFFF
            or occurrence_count != standard_count + native_count
        ):
            _fail("REGISTRY_LOGICAL_FAILURE", "Registry counts do not reconcile")
        for value in (standard_count, native_count):
            if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
                _fail("REGISTRY_LOGICAL_FAILURE", "Registry count is invalid")
        for value in (occurrence_count, standard_count, native_count):
            self._digest.update(struct.pack(">Q", value))
        self.row_count += 1

    def hexdigest(self) -> str:
        digest = self._digest.copy()
        digest.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return digest.hexdigest()


def _fail(code: str, message: str) -> NoReturn:
    raise Stage06ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be lowercase canonical SHA-256 text")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any("holdout" in part.casefold() for path in paths for part in path.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "A Stage 6 path names HOLDOUT")


def validate_stage06_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not pinned")
    if pa.__version__ != EXPECTED_PYARROW_VERSION:
        _fail("PYARROW_VERSION_MISMATCH", "PyArrow runtime is not pinned")
    if duckdb.__version__ != EXPECTED_DUCKDB_VERSION:
        _fail("DUCKDB_VERSION_MISMATCH", "DuckDB runtime is not pinned")


def _update_utf8(digest: _Digest, value: str, chunk_codepoints: int) -> None:
    try:
        for start in range(0, len(value), chunk_codepoints):
            digest.update(
                value[start : start + chunk_codepoints].encode("utf-8", errors="strict")
            )
    except UnicodeError as error:
        raise Stage06ValidationError(
            "INVALID_CANDIDATE_TEXT", "Candidate is not valid Unicode"
        ) from error


def _utf8_byte_length(value: str, chunk_codepoints: int) -> int:
    total = 0
    try:
        for start in range(0, len(value), chunk_codepoints):
            total += len(
                value[start : start + chunk_codepoints].encode("utf-8", errors="strict")
            )
    except UnicodeError as error:
        raise Stage06ValidationError(
            "INVALID_CANDIDATE_TEXT", "Candidate is not valid Unicode"
        ) from error
    return total


def exact_candidate_id_v1(
    candidate_lower: str,
    *,
    digest_factory: DigestFactory = hashlib.sha256,
    chunk_codepoints: int = DEFAULT_HASH_CHUNK_CODEPOINTS,
) -> bytes:
    """Return the fixed 32-byte ID for one exact nonempty lowercase candidate."""
    if not isinstance(candidate_lower, str) or not candidate_lower:
        _fail("INVALID_CANDIDATE_TEXT", "Available candidate must be nonempty text")
    if isinstance(chunk_codepoints, bool) or chunk_codepoints < 1:
        _fail("INVALID_BATCH_SIZE", "Hash chunk size must be positive")
    digest = digest_factory()
    digest.update(STAGE06_CANDIDATE_ID_DOMAIN)
    _update_utf8(digest, candidate_lower, chunk_codepoints)
    result = digest.digest()
    if not isinstance(result, bytes) or len(result) != 32:
        _fail("INVALID_DIGEST_IMPLEMENTATION", "Candidate digest is not 32 bytes")
    return result


def row_map_schema() -> pa.Schema:
    fields = list(stage05_schema())
    fields.extend(
        pa.field(name, pa.binary(32), nullable=True) for name in ROW_MAP_ID_COLUMNS
    )
    return pa.schema(fields)


def registry_schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field(REGISTRY_COLUMNS[0], pa.binary(32), nullable=False),
            pa.field(REGISTRY_COLUMNS[1], pa.string(), nullable=False),
            pa.field(REGISTRY_COLUMNS[2], pa.uint64(), nullable=False),
            pa.field(REGISTRY_COLUMNS[3], pa.uint64(), nullable=False),
            pa.field(REGISTRY_COLUMNS[4], pa.uint64(), nullable=False),
        )
    )


def stage06_schema_fingerprint() -> str:
    digest = hashlib.sha256(STAGE06_SCHEMA_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE06_SCHEMA_VERSION)
    for name, schema in (
        (STAGE06_ROW_MAP_SCHEMA_VERSION, row_map_schema()),
        (STAGE06_REGISTRY_SCHEMA_VERSION, registry_schema()),
    ):
        encoder.text(name)
        encoder.uint64(len(schema))
        for field in schema.remove_metadata():
            encoder.text(field.name)
            encoder.text(str(field.type))
            encoder.text(str(field.nullable).lower())
    return digest.hexdigest()


def validate_stage06_input_binding(
    binding: Stage06InputBinding, *, authoritative_development: bool = False
) -> None:
    if binding.upstream_contract_version != STAGE05_CONTRACT_VERSION:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "Stage 5 contract version is not exact")
    if binding.upstream_profile_version != STAGE05_PROFILE_VERSION:
        _fail("UPSTREAM_PROFILE_MISMATCH", "Stage 5 profile version is not exact")
    for digest in (
        binding.upstream_logical_fingerprint,
        binding.upstream_schema_fingerprint,
        binding.upstream_input_binding_sha256,
        binding.upstream_manifest_sha256,
        binding.upstream_ordered_identity_sha256,
        binding.input_benchmark_fingerprint,
        binding.fixed_500_fingerprint,
    ):
        _digest_bytes(digest)
    if (
        isinstance(binding.expected_row_count, bool)
        or binding.expected_row_count < 1
        or binding.expected_row_count > 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail("INVALID_ROW_COUNT", "Stage 6 expected row count is invalid")
    if authoritative_development and (
        binding.upstream_logical_fingerprint != ACCEPTED_STAGE05_LOGICAL_FINGERPRINT
        or binding.upstream_schema_fingerprint != ACCEPTED_STAGE05_SCHEMA_FINGERPRINT
        or binding.upstream_input_binding_sha256
        != ACCEPTED_STAGE05_INPUT_BINDING_SHA256
        or binding.upstream_manifest_sha256 != ACCEPTED_STAGE05_MANIFEST_SHA256
        or binding.upstream_ordered_identity_sha256
        != ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256
        or binding.input_benchmark_fingerprint != ACCEPTED_BENCHMARK_FINGERPRINT
        or binding.fixed_500_fingerprint != ACCEPTED_FIXED_500_FINGERPRINT
        or binding.expected_row_count != ACCEPTED_DEVELOPMENT_ROWS
    ):
        _fail(
            "AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH",
            "Stage 6 does not bind the accepted 35k Stage 5 DEVELOPMENT boundary",
        )


def stage06_contract_fingerprint_v1(binding: Stage06InputBinding) -> str:
    validate_stage06_input_binding(binding)
    digest = hashlib.sha256(STAGE06_CONTRACT_FINGERPRINT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    for value in (
        STAGE06_CONTRACT_VERSION,
        STAGE06_PROFILE_VERSION,
        STAGE06_SCHEMA_VERSION,
        STAGE06_CANDIDATE_ID_VERSION,
        STAGE06_EXACT_COMPARISON,
        STAGE06_SCOPE,
        STAGE06_UNAVAILABLE_RULE,
        STAGE06_REGISTRY_ORDER,
        STAGE06_SAME_ROW_EQUAL_RULE,
        STAGE06_CLEAN_SURFACE_RULE,
        "NO_TRIM_WHITESPACE_PUNCTUATION_OR_UNICODE_NORMALIZATION",
        "NO_PARSING_FUZZY_MATCHING_GEOGRAPHIC_LOGIC_OR_GEOCODING",
        binding.upstream_contract_version,
        binding.upstream_profile_version,
    ):
        encoder.text(value)
    encoder.bytes(STAGE06_CANDIDATE_ID_DOMAIN)
    for value in (*ROW_MAP_ID_COLUMNS, *REGISTRY_COLUMNS):
        encoder.text(value)
    for digest_value in (
        binding.upstream_logical_fingerprint,
        binding.upstream_schema_fingerprint,
        binding.upstream_input_binding_sha256,
        binding.upstream_manifest_sha256,
        binding.upstream_ordered_identity_sha256,
        binding.input_benchmark_fingerprint,
        binding.fixed_500_fingerprint,
        stage06_schema_fingerprint(),
    ):
        encoder.digest(digest_value)
    encoder.uint64(binding.expected_row_count)
    return digest.hexdigest()


def stage06_logical_dataset_sha256_v1(
    contract_fingerprint: str,
    row_map_logical_sha256: str,
    registry_logical_sha256: str,
    *,
    source_rows: int,
    unique_candidates: int,
) -> str:
    digest = hashlib.sha256(STAGE06_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.digest(contract_fingerprint)
    encoder.digest(row_map_logical_sha256)
    encoder.digest(registry_logical_sha256)
    encoder.uint64(source_rows)
    encoder.uint64(unique_candidates)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage06ValidationError(
            "CONTROLLED_WRITE_FAILURE", "Controlled Stage 6 artifact could not write"
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


def write_stage06_input_binding(path: Path, binding: Stage06InputBinding) -> str:
    validate_stage06_input_binding(binding)
    _reject_holdout_paths(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 6 input binding already exists")
    _write_json_exclusive(path, binding.to_dict())
    return _sha256_file(path)


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code, "Required text is absent")
    return value


def _required_uint(value: object, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail(code, "Required integer is invalid")
    return value


def load_stage06_input_binding(
    path: Path,
    *,
    expected_sha256: str,
    authoritative_development: bool = False,
) -> Stage06InputBinding:
    _digest_bytes(expected_sha256)
    _reject_holdout_paths(path)
    _require_regular_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Input binding SHA-256 differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    expected_keys = set(Stage06InputBinding.__dataclass_fields__) | {
        "stage06_input_binding_version"
    }
    if (
        set(value) != expected_keys
        or value.get("stage06_input_binding_version") != STAGE06_INPUT_BINDING_VERSION
    ):
        _fail("INPUT_BINDING_INVALID", "Stage 6 input binding fields differ")
    binding = Stage06InputBinding(
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
        fixed_500_fingerprint=_required_text(
            value.get("fixed_500_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        expected_row_count=_required_uint(
            value.get("expected_row_count"), "INPUT_BINDING_INVALID"
        ),
    )
    validate_stage06_input_binding(
        binding, authoritative_development=authoritative_development
    )
    return binding


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage06ValidationError(code, "Protected JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Protected JSON is not an object")
    return cast(dict[str, Any], value)


def _require_regular_file(path: Path, code: str) -> None:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage06ValidationError(code, "Protected file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(status.st_mode):
        _fail(code, "Protected path is not a regular file")


def _require_directory(path: Path, code: str) -> None:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage06ValidationError(
            code, "Protected directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(status.st_mode):
        _fail(code, "Protected path is not a directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage06ValidationError(
            code, "Protected path mode is unavailable"
        ) from error
    if path.is_symlink() or mode != expected:
        _fail(code, "Protected path is not owner-only")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_map_metadata(
    binding: Stage06InputBinding, contract_fingerprint: str
) -> Mapping[bytes, bytes]:
    values = {
        "stage06_contract_version": STAGE06_CONTRACT_VERSION,
        "stage06_profile_version": STAGE06_PROFILE_VERSION,
        "stage06_row_map_schema_version": STAGE06_ROW_MAP_SCHEMA_VERSION,
        "stage06_schema_fingerprint": stage06_schema_fingerprint(),
        "stage06_contract_fingerprint": contract_fingerprint,
        "stage06_candidate_id_version": STAGE06_CANDIDATE_ID_VERSION,
        "upstream_stage05_manifest_sha256": binding.upstream_manifest_sha256,
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _registry_metadata(
    binding: Stage06InputBinding, contract_fingerprint: str
) -> Mapping[bytes, bytes]:
    values = {
        "stage06_contract_version": STAGE06_CONTRACT_VERSION,
        "stage06_profile_version": STAGE06_PROFILE_VERSION,
        "stage06_registry_schema_version": STAGE06_REGISTRY_SCHEMA_VERSION,
        "stage06_schema_fingerprint": stage06_schema_fingerprint(),
        "stage06_contract_fingerprint": contract_fingerprint,
        "stage06_candidate_id_version": STAGE06_CANDIDATE_ID_VERSION,
        "stage06_registry_order": STAGE06_REGISTRY_ORDER,
        "upstream_stage05_manifest_sha256": binding.upstream_manifest_sha256,
    }
    return {key.encode(): value.encode() for key, value in values.items()}


def _artifact_identity(
    root: Path, relative_path: str, *, row_count: int
) -> Stage06ArtifactIdentity:
    path = root / relative_path
    return Stage06ArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _stage05_artifacts(
    root: Path, binding: Stage06InputBinding
) -> tuple[Stage06ArtifactIdentity, ...]:
    outcome: Stage05MaterializationOutcome = validate_stage05_bundle(
        root,
        expected_manifest_sha256=binding.upstream_manifest_sha256,
        authoritative_development=False,
    )
    if (
        outcome.logical_dataset_sha256_v1 != binding.upstream_logical_fingerprint
        or outcome.schema_fingerprint != binding.upstream_schema_fingerprint
        or outcome.input_binding_sha256 != binding.upstream_input_binding_sha256
        or outcome.ordered_identity_sha256 != binding.upstream_ordered_identity_sha256
        or outcome.row_count != binding.expected_row_count
    ):
        _fail("STAGE05_IDENTITY_MISMATCH", "Stage 5 scientific binding differs")
    manifest = _load_json(root / STAGE05_MANIFEST_NAME, "STAGE05_MANIFEST_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 identity is malformed")
    if (
        scientific.get("stage05_contract_version") != binding.upstream_contract_version
        or scientific.get("stage05_profile_version") != binding.upstream_profile_version
        or scientific.get("input_benchmark_fingerprint")
        != binding.input_benchmark_fingerprint
    ):
        _fail("STAGE05_IDENTITY_MISMATCH", "Stage 5 contract binding differs")
    raw_artifacts = physical.get("output_artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifacts are absent")
    artifacts: list[Stage06ArtifactIdentity] = []
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact is malformed")
        expected_relative = f"data/part-{sequence:06d}.parquet"
        artifact = Stage06ArtifactIdentity(
            relative_path=_required_text(
                raw.get("relative_path"), "STAGE05_MANIFEST_INVALID"
            ),
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE05_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE05_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE05_MANIFEST_INVALID"),
        )
        if artifact.relative_path != expected_relative:
            _fail("STAGE05_MANIFEST_INVALID", "Stage 5 artifact order differs")
        _digest_bytes(artifact.sha256)
        path = root / artifact.relative_path
        _require_regular_file(path, "STAGE05_ARTIFACT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("STAGE05_ARTIFACT_MISMATCH", "Stage 5 artifact identity differs")
        artifacts.append(artifact)
    return tuple(artifacts)


def _iter_bounded_batches(
    parquet: pq.ParquetFile, *, batch_rows: int, target_batch_bytes: int
) -> Iterable[pa.RecordBatch]:
    for row_group in range(parquet.metadata.num_row_groups):
        metadata = parquet.metadata.row_group(row_group)
        if metadata.num_rows < 1:
            _fail("PARQUET_READ_FAILURE", "Stage 6 encountered an empty row group")
        estimated = max(1, metadata.total_byte_size // metadata.num_rows)
        adaptive_rows = max(1, min(batch_rows, target_batch_bytes // estimated))
        yield from parquet.iter_batches(
            batch_size=adaptive_rows, row_groups=[row_group], use_threads=False
        )


def _iter_aligned_batches(
    left: Iterable[pa.RecordBatch], right: Iterable[pa.RecordBatch]
) -> Iterable[tuple[pa.RecordBatch, pa.RecordBatch]]:
    left_iterator = iter(left)
    right_iterator = iter(right)
    left_batch: pa.RecordBatch | None = None
    right_batch: pa.RecordBatch | None = None
    left_offset = 0
    right_offset = 0
    left_done = False
    right_done = False
    while True:
        if left_batch is None and not left_done:
            left_batch = next(left_iterator, None)
            left_offset = 0
            left_done = left_batch is None
        if right_batch is None and not right_done:
            right_batch = next(right_iterator, None)
            right_offset = 0
            right_done = right_batch is None
        if left_done or right_done:
            if left_done and right_done:
                return
            _fail("OUTPUT_ROW_MISMATCH", "Stage 6 row-map stream lengths differ")
        assert left_batch is not None and right_batch is not None
        row_count = min(
            left_batch.num_rows - left_offset,
            right_batch.num_rows - right_offset,
        )
        if row_count < 1:
            _fail("OUTPUT_ROW_MISMATCH", "Stage 6 row-map batch is empty")
        yield (
            left_batch.slice(left_offset, row_count),
            right_batch.slice(right_offset, row_count),
        )
        left_offset += row_count
        right_offset += row_count
        if left_offset == left_batch.num_rows:
            left_batch = None
        if right_offset == right_batch.num_rows:
            right_batch = None


def _new_writer(path: Path, schema: pa.Schema) -> pq.ParquetWriter:
    try:
        writer = pq.ParquetWriter(
            path,
            schema,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
            write_page_checksum=True,
            version="2.6",
            data_page_version="2.0",
            store_schema=True,
        )
        path.chmod(0o600)
        return writer
    except (OSError, pa.ArrowException) as error:
        raise Stage06ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 6 Parquet writer could not start"
        ) from error


def _project_row_map_batch(
    batch: pa.RecordBatch,
    *,
    metadata: Mapping[bytes, bytes],
    digest_factory: DigestFactory,
    hash_chunk_codepoints: int,
) -> tuple[pa.RecordBatch, int]:
    if not batch.schema.remove_metadata().equals(
        stage05_schema(), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 5 input batch schema is not exact")
    names = batch.schema.names
    standard_available = batch.column(
        names.index("stage05_standard_candidate_available")
    )
    native_available = batch.column(names.index("stage05_native_candidate_available"))
    standard_lower = batch.column(names.index("stage05_standard_candidate_lower"))
    native_lower = batch.column(names.index("stage05_native_candidate_lower"))
    standard_clean = batch.column(names.index("stage05_standard_candidate_clean"))
    native_clean = batch.column(names.index("stage05_native_candidate_clean"))
    standard_ids: list[bytes | None] = []
    native_ids: list[bytes | None] = []
    id_nanoseconds = 0
    for row_index in range(batch.num_rows):
        for available_array, lower_array, clean_array, destination in (
            (standard_available, standard_lower, standard_clean, standard_ids),
            (native_available, native_lower, native_clean, native_ids),
        ):
            available = available_array[row_index].as_py()
            lower = lower_array[row_index].as_py()
            clean = clean_array[row_index].as_py()
            if (
                not isinstance(available, bool)
                or not isinstance(lower, str)
                or not isinstance(clean, str)
            ):
                _fail("UPSTREAM_TYPE_MISMATCH", "Stage 5 candidate type differs")
            if available != bool(lower) or available != bool(clean):
                _fail("UPSTREAM_AVAILABILITY_MISMATCH", "Stage 5 availability differs")
            if clean.lower() != lower:
                _fail("UPSTREAM_CANDIDATE_MISMATCH", "Stage 5 clean/lower pair differs")
            if not available:
                destination.append(None)
                continue
            started = time.perf_counter_ns()
            destination.append(
                exact_candidate_id_v1(
                    lower,
                    digest_factory=digest_factory,
                    chunk_codepoints=hash_chunk_codepoints,
                )
            )
            id_nanoseconds += time.perf_counter_ns() - started
    arrays = [batch.column(index) for index in range(batch.num_columns)]
    arrays.extend(
        (
            pa.array(standard_ids, type=pa.binary(32)),
            pa.array(native_ids, type=pa.binary(32)),
        )
    )
    return (
        pa.RecordBatch.from_arrays(
            arrays, schema=row_map_schema().with_metadata(dict(metadata))
        ),
        id_nanoseconds,
    )


def _write_row_map_shard(
    *,
    input_path: Path,
    output_path: Path,
    batch_rows: int,
    target_batch_bytes: int,
    metadata: Mapping[bytes, bytes],
    digest_factory: DigestFactory,
    hash_chunk_codepoints: int,
    identities: _OrderedStableIdentityHasher,
    row_map_hasher: _RowMapLogicalHasher,
) -> tuple[int, int]:
    parquet = pq.ParquetFile(input_path, page_checksum_verification=True)
    expected_input_schema = stage05_schema()
    if not parquet.schema_arrow.remove_metadata().equals(
        expected_input_schema, check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Stage 5 Parquet schema is not exact")
    writer = _new_writer(output_path, row_map_schema().with_metadata(dict(metadata)))
    rows = 0
    id_nanoseconds = 0
    try:
        for batch in _iter_bounded_batches(
            parquet,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        ):
            projected, elapsed = _project_row_map_batch(
                batch,
                metadata=metadata,
                digest_factory=digest_factory,
                hash_chunk_codepoints=hash_chunk_codepoints,
            )
            writer.write_batch(projected)
            stable_ids = projected.column(
                projected.schema.get_field_index("stable_source_row_id_v1")
            )
            standard_ids = projected.column(
                projected.schema.get_field_index(ROW_MAP_ID_COLUMNS[0])
            )
            native_ids = projected.column(
                projected.schema.get_field_index(ROW_MAP_ID_COLUMNS[1])
            )
            identities.update(stable_ids)
            row_map_hasher.update(stable_ids, standard_ids, native_ids)
            rows += projected.num_rows
            id_nanoseconds += elapsed
    finally:
        writer.close()
    output_path.chmod(0o600)
    return rows, id_nanoseconds


def _configure_duckdb(
    connection: duckdb.DuckDBPyConnection,
    *,
    memory_limit: str,
    threads: int,
    spill_directory: Path,
) -> None:
    connection.execute("SET memory_limit=?", [memory_limit])
    connection.execute("SET threads=?", [threads])
    connection.execute("SET temp_directory=?", [str(spill_directory.resolve())])
    connection.execute("SET preserve_insertion_order=false")


def _query_uint(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None or len(row) != 1 or isinstance(row[0], bool):
        _fail("STAGE06_AGGREGATION_FAILURE", "Aggregate query shape is invalid")
    return int(row[0])


def _build_registry_tables(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    connection.execute(
        f"""
        CREATE OR REPLACE TABLE stage06_occurrences AS
        SELECT
            stable_source_row_id_v1 AS source_identity,
            'STANDARD'::VARCHAR AS representation,
            {ROW_MAP_ID_COLUMNS[0]} AS candidate_id,
            encode(stage05_standard_candidate_lower) AS candidate_bytes,
            encode(stage05_standard_candidate_clean) AS clean_surface_bytes,
            length(stage05_standard_candidate_lower)::UBIGINT AS candidate_codepoints
        FROM stage05_input
        WHERE stage05_standard_candidate_available
        UNION ALL
        SELECT
            stable_source_row_id_v1 AS source_identity,
            'NATIVE'::VARCHAR AS representation,
            {ROW_MAP_ID_COLUMNS[1]} AS candidate_id,
            encode(stage05_native_candidate_lower) AS candidate_bytes,
            encode(stage05_native_candidate_clean) AS clean_surface_bytes,
            length(stage05_native_candidate_lower)::UBIGINT AS candidate_codepoints
        FROM stage05_input
        WHERE stage05_native_candidate_available
        """
    )
    null_occurrences = _query_uint(
        connection,
        "SELECT count(*) FROM stage06_occurrences WHERE candidate_id IS NULL",
    )
    if null_occurrences:
        _fail("NULL_AVAILABLE_CANDIDATE_ID", "Available occurrence has null ID")
    connection.execute(
        """
        CREATE OR REPLACE TABLE candidate_text_groups AS
        SELECT
            candidate_id,
            candidate_bytes,
            count(*)::UBIGINT AS occurrence_count,
            count(*) FILTER (WHERE representation = 'STANDARD')::UBIGINT
                AS standard_occurrence_count,
            count(*) FILTER (WHERE representation = 'NATIVE')::UBIGINT
                AS native_occurrence_count,
            count(DISTINCT source_identity)::UBIGINT AS source_row_count,
            count(DISTINCT clean_surface_bytes)::UBIGINT AS clean_surface_count,
            min(candidate_codepoints)::UBIGINT AS candidate_codepoints,
            max(candidate_codepoints)::UBIGINT AS maximum_candidate_codepoints
        FROM stage06_occurrences
        GROUP BY candidate_id, candidate_bytes
        """
    )
    collision_row = connection.execute(
        """
        SELECT count(*), coalesce(sum(distinct_text_count - 1), 0)
        FROM (
            SELECT candidate_id, count(*)::UBIGINT AS distinct_text_count
            FROM candidate_text_groups
            GROUP BY candidate_id
            HAVING count(*) > 1
        )
        """
    ).fetchone()
    assert collision_row is not None
    collision_groups = int(collision_row[0])
    distinct_text_collisions = int(collision_row[1])
    if collision_groups or distinct_text_collisions:
        _fail(
            "CANDIDATE_ID_COLLISION",
            "One candidate ID represents more than one exact candidate text",
        )
    connection.execute(
        "CREATE OR REPLACE VIEW candidate_groups AS SELECT * FROM candidate_text_groups"
    )
    digest_reuse_groups = _query_uint(
        connection,
        "SELECT count(*) FROM candidate_groups WHERE occurrence_count > 1",
    )
    return {
        "DIGEST_GROUPS_WITH_MULTIPLE_OCCURRENCES": digest_reuse_groups,
        "CANDIDATE_ID_COLLISION_GROUPS": collision_groups,
        "DISTINCT_TEXT_DIGEST_COLLISION_GROUPS": distinct_text_collisions,
    }


def _cast_registry_batch(batch: pa.RecordBatch) -> pa.RecordBatch:
    schema = registry_schema()
    if batch.num_columns != len(schema):
        _fail("REGISTRY_SCHEMA_MISMATCH", "Registry query column count differs")
    arrays: list[pa.Array] = []
    for index, field in enumerate(schema):
        try:
            arrays.append(pc.cast(batch.column(index), field.type, safe=True))
        except pa.ArrowException as error:
            raise Stage06ValidationError(
                "REGISTRY_SCHEMA_MISMATCH", "Registry query type differs"
            ) from error
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def _write_registry(
    connection: duckdb.DuckDBPyConnection,
    *,
    output_root: Path,
    metadata: Mapping[bytes, bytes],
    registry_batch_rows: int,
    registry_shard_rows: int,
    registry_hasher: _RegistryLogicalHasher,
) -> tuple[tuple[Stage06ArtifactIdentity, ...], int]:
    reader = connection.execute(
        """
        SELECT
            candidate_id,
            decode(candidate_bytes),
            occurrence_count,
            standard_occurrence_count,
            native_occurrence_count
        FROM candidate_groups
        ORDER BY candidate_id
        """
    ).to_arrow_reader(batch_size=registry_batch_rows)
    artifacts: list[Stage06ArtifactIdentity] = []
    writer: pq.ParquetWriter | None = None
    writer_path: Path | None = None
    shard_rows = 0
    total_rows = 0
    shard_number = 0

    def close_writer() -> None:
        nonlocal writer, writer_path, shard_rows
        if writer is None or writer_path is None:
            return
        writer.close()
        writer_path.chmod(0o600)
        artifacts.append(
            _artifact_identity(
                output_root,
                writer_path.relative_to(output_root).as_posix(),
                row_count=shard_rows,
            )
        )
        writer = None
        writer_path = None
        shard_rows = 0

    for raw_batch in reader:
        batch = _cast_registry_batch(raw_batch)
        position = 0
        while position < batch.num_rows:
            if writer is None:
                shard_number += 1
                relative = f"{REGISTRY_DIRECTORY}/part-{shard_number:06d}.parquet"
                writer_path = output_root / relative
                writer = _new_writer(
                    writer_path, registry_schema().with_metadata(dict(metadata))
                )
            capacity = registry_shard_rows - shard_rows
            piece = batch.slice(position, min(capacity, batch.num_rows - position))
            writer.write_batch(
                pa.RecordBatch.from_arrays(
                    [piece.column(index) for index in range(piece.num_columns)],
                    schema=registry_schema().with_metadata(dict(metadata)),
                )
            )
            for row_index in range(piece.num_rows):
                values = [piece.column(index)[row_index].as_py() for index in range(5)]
                candidate_id, candidate_lower = values[:2]
                counts = values[2:]
                if not isinstance(candidate_id, bytes) or not isinstance(
                    candidate_lower, str
                ):
                    _fail("REGISTRY_SCHEMA_MISMATCH", "Registry scalar type differs")
                registry_hasher.update_row(
                    candidate_id,
                    candidate_lower,
                    int(counts[0]),
                    int(counts[1]),
                    int(counts[2]),
                )
            written = piece.num_rows
            position += written
            shard_rows += written
            total_rows += written
            if shard_rows == registry_shard_rows:
                close_writer()
    close_writer()
    if not artifacts:
        relative = f"{REGISTRY_DIRECTORY}/part-000001.parquet"
        empty_path = output_root / relative
        empty_writer = _new_writer(
            empty_path, registry_schema().with_metadata(dict(metadata))
        )
        empty_writer.close()
        empty_path.chmod(0o600)
        artifacts.append(_artifact_identity(output_root, relative, row_count=0))
    return tuple(artifacts), total_rows


def _directory_usage(path: Path) -> tuple[int, int]:
    total_bytes = 0
    files = 0
    if not path.exists():
        return total_bytes, files
    for candidate in path.rglob("*"):
        if candidate.is_file() and not candidate.is_symlink():
            files += 1
            total_bytes += candidate.stat(follow_symlinks=False).st_size
    return total_bytes, files


def _internal_map_back_metrics(
    connection: duckdb.DuckDBPyConnection, *, registry_paths: Sequence[Path]
) -> dict[str, int]:
    connection.read_parquet([str(path) for path in registry_paths]).create_view(
        "stage06_registry"
    )
    row = connection.execute(
        f"""
        SELECT
            count(*) FILTER (WHERE r.{REGISTRY_COLUMNS[0]} IS NULL),
            count(*) FILTER (
                WHERE r.{REGISTRY_COLUMNS[0]} IS NOT NULL
                  AND encode(r.{REGISTRY_COLUMNS[1]}) != o.candidate_bytes
            )
        FROM stage06_occurrences o
        LEFT JOIN stage06_registry r
          ON o.candidate_id = r.{REGISTRY_COLUMNS[0]}
        """
    ).fetchone()
    assert row is not None
    missing = int(row[0])
    text_mismatches = int(row[1])
    count_mismatches = _query_uint(
        connection,
        f"""
        SELECT count(*)
        FROM candidate_groups g
        JOIN stage06_registry r
          ON g.candidate_id = r.{REGISTRY_COLUMNS[0]}
        WHERE g.occurrence_count != r.{REGISTRY_COLUMNS[2]}
           OR g.standard_occurrence_count != r.{REGISTRY_COLUMNS[3]}
           OR g.native_occurrence_count != r.{REGISTRY_COLUMNS[4]}
        """,
    )
    duplicate_source_identities = _query_uint(
        connection,
        "SELECT count(*) - count(DISTINCT stable_source_row_id_v1) FROM stage05_input",
    )
    return {
        "SOURCE_TO_REGISTRY_MISSING": missing,
        "SOURCE_TO_REGISTRY_TEXT_MISMATCHES": text_mismatches,
        "REGISTRY_COUNT_MISMATCHES": count_mismatches,
        "DUPLICATE_SOURCE_IDENTITIES": duplicate_source_identities,
    }


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def materialize_stage06(
    config: Stage06RunConfig,
    *,
    digest_factory: DigestFactory = hashlib.sha256,
) -> Stage06MaterializationOutcome:
    """Materialize exact candidate mappings and a globally unique registry."""
    config.validate()
    validate_stage06_runtime()
    if config.production:
        require_goethe_nhr_slurm("stage06-early-exact-deduplication")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 6 output directory already exists")
    binding = load_stage06_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
        authoritative_development=config.authoritative_development,
    )
    stage05_artifacts = _stage05_artifacts(config.stage05_output_directory, binding)
    contract_fingerprint = stage06_contract_fingerprint_v1(binding)
    row_metadata = _row_map_metadata(binding, contract_fingerprint)
    registry_metadata = _registry_metadata(binding, contract_fingerprint)

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_directory(parent, "STAGE06_OUTPUT_INVALID")
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 6 temporary output already exists")
    row_data = temporary / ROW_MAP_DIRECTORY
    registry_data = temporary / REGISTRY_DIRECTORY
    work = temporary / "work"
    spill = work / "duckdb_spill"
    for directory in (
        temporary,
        temporary / "row_map",
        row_data,
        temporary / "registry",
        registry_data,
        work,
        spill,
    ):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    _write_exclusive(temporary / STAGE06_IN_PROGRESS_MARKER, b"IN_PROGRESS\n")

    total_started = time.perf_counter()
    row_started = time.perf_counter()
    identities = _OrderedStableIdentityHasher()
    row_map_hasher = _RowMapLogicalHasher(contract_fingerprint)
    row_artifacts: list[Stage06ArtifactIdentity] = []
    id_nanoseconds = 0
    for sequence, upstream in enumerate(stage05_artifacts, start=1):
        input_path = config.stage05_output_directory / upstream.relative_path
        relative = f"{ROW_MAP_DIRECTORY}/part-{sequence:06d}.parquet"
        output_path = temporary / relative
        rows, elapsed = _write_row_map_shard(
            input_path=input_path,
            output_path=output_path,
            batch_rows=config.batch_rows,
            target_batch_bytes=config.target_batch_bytes,
            metadata=row_metadata,
            digest_factory=digest_factory,
            hash_chunk_codepoints=config.hash_chunk_codepoints,
            identities=identities,
            row_map_hasher=row_map_hasher,
        )
        if rows != upstream.row_count:
            _fail("ROW_COUNT_MISMATCH", "Stage 6 row-map shard count differs")
        row_artifacts.append(_artifact_identity(temporary, relative, row_count=rows))
        id_nanoseconds += elapsed
    row_phase_milliseconds = round((time.perf_counter() - row_started) * 1_000)
    id_milliseconds = round(id_nanoseconds / 1_000_000)
    if (
        identities.row_count != binding.expected_row_count
        or identities.hexdigest() != binding.upstream_ordered_identity_sha256
        or row_map_hasher.row_count != binding.expected_row_count
    ):
        _fail("STABLE_IDENTITY_MISMATCH", "Stage 6 row identity/order differs")

    database_path = work / "stage06.duckdb"
    aggregation_started = time.perf_counter()
    connection = duckdb.connect(str(database_path))
    database_path.chmod(0o600)
    try:
        _configure_duckdb(
            connection,
            memory_limit=config.duckdb_memory_limit,
            threads=config.duckdb_threads,
            spill_directory=spill,
        )
        row_paths = [
            str((temporary / item.relative_path).resolve()) for item in row_artifacts
        ]
        connection.read_parquet(row_paths).create_view("stage05_input")
        collision_metrics = _build_registry_tables(connection)
        metrics = _collect_metrics(connection)
        metrics["COLLISION_EXACTNESS"] = collision_metrics
        registry_hasher = _RegistryLogicalHasher(
            contract_fingerprint, chunk_codepoints=config.hash_chunk_codepoints
        )
        registry_artifacts, unique_candidates = _write_registry(
            connection,
            output_root=temporary,
            metadata=registry_metadata,
            registry_batch_rows=config.registry_batch_rows,
            registry_shard_rows=config.registry_shard_rows,
            registry_hasher=registry_hasher,
        )
        registry_paths = [temporary / item.relative_path for item in registry_artifacts]
        map_back = _internal_map_back_metrics(connection, registry_paths=registry_paths)
        metrics["MAP_BACK_INTEGRITY"] = map_back
        spill_bytes, spill_files = _directory_usage(spill)
    except Stage06ValidationError:
        raise
    except (OSError, duckdb.Error, pa.ArrowException) as error:
        raise Stage06ValidationError(
            "STAGE06_AGGREGATION_FAILURE", "Stage 6 aggregation failed"
        ) from error
    finally:
        connection.close()
    aggregation_milliseconds = round(
        (time.perf_counter() - aggregation_started) * 1_000
    )
    row_map_logical = row_map_hasher.hexdigest()
    registry_logical = registry_hasher.hexdigest()
    logical = stage06_logical_dataset_sha256_v1(
        contract_fingerprint,
        row_map_logical,
        registry_logical,
        source_rows=binding.expected_row_count,
        unique_candidates=unique_candidates,
    )
    exact_metrics = cast(dict[str, Any], metrics["EXACT_DEDUPLICATION"])
    if int(exact_metrics["UNIQUE_EXACT_LOWER_CANDIDATES"]) != unique_candidates:
        _fail("REGISTRY_COUNT_MISMATCH", "Unique registry count differs")
    reconciliation = cast(dict[str, int], metrics["RECONCILIATION"])
    map_back = cast(dict[str, int], metrics["MAP_BACK_INTEGRITY"])
    collision_metrics = cast(dict[str, int], metrics["COLLISION_EXACTNESS"])
    if any(
        value for key, value in reconciliation.items() if key.endswith("MISMATCHES")
    ):
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Occurrence counts differ")
    if any(map_back.values()):
        _fail("MAP_BACK_INTEGRITY_FAILURE", "Source-to-registry map-back differs")
    if (
        collision_metrics["CANDIDATE_ID_COLLISION_GROUPS"]
        or collision_metrics["DISTINCT_TEXT_DIGEST_COLLISION_GROUPS"]
    ):
        _fail("CANDIDATE_ID_COLLISION", "Distinct candidate texts share an ID")

    database_path.unlink()
    for candidate in spill.iterdir():
        if candidate.is_file() and not candidate.is_symlink():
            candidate.unlink()
    spill.rmdir()
    work.rmdir()
    total_milliseconds = round((time.perf_counter() - total_started) * 1_000)
    performance: dict[str, int | str] = {
        "CANDIDATE_ID_DERIVATION_MILLISECONDS": id_milliseconds,
        "ROW_MAP_MATERIALIZATION_MILLISECONDS": row_phase_milliseconds,
        "ROW_MAP_NON_ID_MILLISECONDS": max(0, row_phase_milliseconds - id_milliseconds),
        "REGISTRY_DEDUP_AGGREGATION_MILLISECONDS": aggregation_milliseconds,
        "MATERIALIZATION_TOTAL_MILLISECONDS": total_milliseconds,
        "DUCKDB_MEMORY_LIMIT": config.duckdb_memory_limit,
        "DUCKDB_THREADS": config.duckdb_threads,
        "DUCKDB_SPILL_BYTES": spill_bytes,
        "DUCKDB_SPILL_FILES": spill_files,
        "PROCESS_MAX_RSS_KIB": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }
    physical = {
        "stage06_input_binding_sha256": config.expected_input_binding_sha256,
        "upstream_stage05_manifest_sha256": binding.upstream_manifest_sha256,
        "row_map_artifacts": [item.to_dict() for item in row_artifacts],
        "registry_artifacts": [item.to_dict() for item in registry_artifacts],
        "owner_only_permissions": True,
        "bounded_memory_architecture": {
            "maximum_configured_row_batch_rows": config.batch_rows,
            "target_uncompressed_batch_bytes": config.target_batch_bytes,
            "registry_batch_rows": config.registry_batch_rows,
            "registry_shard_rows": config.registry_shard_rows,
            "hash_chunk_codepoints": config.hash_chunk_codepoints,
            "duckdb_memory_limit": config.duckdb_memory_limit,
            "duckdb_threads": config.duckdb_threads,
            "memory_scales_with_population": False,
            "population_sized_python_candidate_map_used": False,
            "duckdb_disk_backed_grouping": True,
        },
    }
    manifest = {
        "stage06_manifest_version": STAGE06_MANIFEST_VERSION,
        "status": "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED",
        "scientific_identity": {
            "stage06_contract_version": STAGE06_CONTRACT_VERSION,
            "stage06_profile_version": STAGE06_PROFILE_VERSION,
            "stage06_schema_version": STAGE06_SCHEMA_VERSION,
            "stage06_schema_fingerprint": stage06_schema_fingerprint(),
            "stage06_contract_fingerprint": contract_fingerprint,
            "stage06_logical_dataset_sha256_v1": logical,
            "stage06_row_map_logical_sha256_v1": row_map_logical,
            "stage06_registry_logical_sha256_v1": registry_logical,
            "stage06_candidate_id_version": STAGE06_CANDIDATE_ID_VERSION,
            "stage06_candidate_id_domain_hex": STAGE06_CANDIDATE_ID_DOMAIN.hex(),
            "exact_comparison": STAGE06_EXACT_COMPARISON,
            "deduplication_scope": STAGE06_SCOPE,
            "unavailable_rule": STAGE06_UNAVAILABLE_RULE,
            "registry_order": STAGE06_REGISTRY_ORDER,
            "same_row_equal_rule": STAGE06_SAME_ROW_EQUAL_RULE,
            "clean_surface_rule": STAGE06_CLEAN_SURFACE_RULE,
            "row_map_id_columns": list(ROW_MAP_ID_COLUMNS),
            "registry_columns": list(REGISTRY_COLUMNS),
            "upstream_stage05_contract_version": binding.upstream_contract_version,
            "upstream_stage05_profile_version": binding.upstream_profile_version,
            "upstream_stage05_logical_fingerprint": binding.upstream_logical_fingerprint,
            "upstream_stage05_schema_fingerprint": binding.upstream_schema_fingerprint,
            "upstream_stage05_input_binding_sha256": (
                binding.upstream_input_binding_sha256
            ),
            "upstream_stage05_manifest_sha256": binding.upstream_manifest_sha256,
            "upstream_ordered_identity_sha256": (
                binding.upstream_ordered_identity_sha256
            ),
            "input_benchmark_fingerprint": binding.input_benchmark_fingerprint,
            "fixed_500_fingerprint": binding.fixed_500_fingerprint,
            "source_row_count": binding.expected_row_count,
            "unique_candidate_count": unique_candidates,
        },
        "physical_identity": physical,
        "development_metrics": metrics,
        "performance": performance,
        "validation": {
            "validation_contract_version": STAGE06_VALIDATION_VERSION,
            "stage05_bundle_validated": "PASS",
            "all_stage05_columns_preserved": "PASS",
            "source_rows_preserved": "PASS",
            "ordered_identity": "PASS",
            "candidate_id_derivation": "PASS",
            "unavailable_null_mapping": "PASS",
            "exact_collision_guard": "PASS",
            "occurrence_reconciliation": "PASS",
            "map_back_completeness": "PASS",
            "registry_order": "PASS",
            "bounded_memory": "PASS",
            "page_checksum_readback": "PASS",
            "owner_only_permissions": "PASS",
            "atomic_publication": "PASS",
            "holdout_exclusion": "PASS",
            "stage07_not_started": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "pyarrow_version": pa.__version__,
            "duckdb_version": duckdb.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json_exclusive(temporary / STAGE06_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(
        temporary, STAGE06_MANIFEST_NAME, row_count=0
    )
    _write_json_exclusive(
        temporary / STAGE06_SUCCESS_MARKER,
        {
            "status": "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "stage06_manifest_sha256": manifest_identity.sha256,
            "stage06_manifest_size_bytes": manifest_identity.size_bytes,
            "stage06_logical_dataset_sha256_v1": logical,
            "stage06_schema_fingerprint": stage06_schema_fingerprint(),
            "stage06_input_binding_sha256": config.expected_input_binding_sha256,
            "ordered_stable_identity_sha256_v1": identities.hexdigest(),
            "source_row_count": binding.expected_row_count,
            "unique_candidate_count": unique_candidates,
            "row_map_shard_count": len(row_artifacts),
            "registry_shard_count": len(registry_artifacts),
        },
    )
    (temporary / STAGE06_IN_PROGRESS_MARKER).unlink()
    for directory in (
        temporary / "row_map" / "data",
        temporary / "row_map",
        temporary / "registry" / "data",
        temporary / "registry",
        temporary,
    ):
        _fsync_directory(directory)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    validation_started = time.perf_counter()
    validated = validate_stage06_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_identity.sha256,
        stage05_output_directory=config.stage05_output_directory,
        authoritative_development=config.authoritative_development,
        batch_rows=config.batch_rows,
        target_batch_bytes=config.target_batch_bytes,
        duckdb_memory_limit=config.duckdb_memory_limit,
        duckdb_threads=config.duckdb_threads,
        hash_chunk_codepoints=config.hash_chunk_codepoints,
    )
    validation_ms = round((time.perf_counter() - validation_started) * 1_000)
    return replace(validated, publication_validation_milliseconds=validation_ms)


def _binding_from_manifest(manifest: Mapping[str, Any]) -> Stage06InputBinding:
    scientific = manifest.get("scientific_identity")
    if not isinstance(scientific, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 identity is malformed")
    return Stage06InputBinding(
        upstream_contract_version=_required_text(
            scientific.get("upstream_stage05_contract_version"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_profile_version=_required_text(
            scientific.get("upstream_stage05_profile_version"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_logical_fingerprint=_required_text(
            scientific.get("upstream_stage05_logical_fingerprint"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_schema_fingerprint=_required_text(
            scientific.get("upstream_stage05_schema_fingerprint"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_input_binding_sha256=_required_text(
            scientific.get("upstream_stage05_input_binding_sha256"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_manifest_sha256=_required_text(
            scientific.get("upstream_stage05_manifest_sha256"),
            "STAGE06_MANIFEST_INVALID",
        ),
        upstream_ordered_identity_sha256=_required_text(
            scientific.get("upstream_ordered_identity_sha256"),
            "STAGE06_MANIFEST_INVALID",
        ),
        input_benchmark_fingerprint=_required_text(
            scientific.get("input_benchmark_fingerprint"),
            "STAGE06_MANIFEST_INVALID",
        ),
        fixed_500_fingerprint=_required_text(
            scientific.get("fixed_500_fingerprint"), "STAGE06_MANIFEST_INVALID"
        ),
        expected_row_count=_required_uint(
            scientific.get("source_row_count"), "STAGE06_MANIFEST_INVALID"
        ),
    )


def _manifest_artifacts(
    output_directory: Path,
    physical: Mapping[str, Any],
    *,
    key: str,
    directory: str,
) -> tuple[Stage06ArtifactIdentity, ...]:
    raw_artifacts = physical.get(key)
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifacts are absent")
    artifacts: list[Stage06ArtifactIdentity] = []
    for sequence, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact is malformed")
        artifact = Stage06ArtifactIdentity(
            relative_path=_required_text(
                raw.get("relative_path"), "STAGE06_MANIFEST_INVALID"
            ),
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE06_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE06_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE06_MANIFEST_INVALID"),
        )
        if artifact.relative_path != f"{directory}/part-{sequence:06d}.parquet":
            _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact order differs")
        _digest_bytes(artifact.sha256)
        path = output_directory / artifact.relative_path
        _require_regular_file(path, "STAGE06_ARTIFACT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("STAGE06_ARTIFACT_MISMATCH", "Stage 6 artifact identity differs")
        artifacts.append(artifact)
    return tuple(artifacts)


def _validate_row_map_stream(
    *,
    stage05_root: Path,
    stage06_root: Path,
    upstream: Sequence[Stage06ArtifactIdentity],
    row_artifacts: Sequence[Stage06ArtifactIdentity],
    row_metadata: Mapping[bytes, bytes],
    contract_fingerprint: str,
    batch_rows: int,
    target_batch_bytes: int,
    hash_chunk_codepoints: int,
) -> tuple[str, str, int]:
    if len(upstream) != len(row_artifacts):
        _fail("OUTPUT_ROW_MISMATCH", "Stage 6 row-map shard count differs")
    identities = _OrderedStableIdentityHasher()
    logical = _RowMapLogicalHasher(contract_fingerprint)
    rows = 0
    for input_artifact, output_artifact in zip(upstream, row_artifacts, strict=True):
        input_file = pq.ParquetFile(
            stage05_root / input_artifact.relative_path,
            page_checksum_verification=True,
        )
        output_file = pq.ParquetFile(
            stage06_root / output_artifact.relative_path,
            page_checksum_verification=True,
        )
        if not output_file.schema_arrow.equals(
            row_map_schema().with_metadata(dict(row_metadata)), check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 6 row-map schema differs")
        input_batches = _iter_bounded_batches(
            input_file,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        )
        output_batches = _iter_bounded_batches(
            output_file,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        )
        shard_rows = 0
        for input_batch, output_batch in _iter_aligned_batches(
            input_batches, output_batches
        ):
            for column_index in range(len(stage05_schema())):
                if not input_batch.column(column_index).equals(
                    output_batch.column(column_index)
                ):
                    _fail(
                        "UPSTREAM_VALUE_MISMATCH",
                        "Stage 6 changed an incoming Stage 5 value or row order",
                    )
            expected, _ = _project_row_map_batch(
                input_batch,
                metadata=row_metadata,
                digest_factory=hashlib.sha256,
                hash_chunk_codepoints=hash_chunk_codepoints,
            )
            for column_index in range(len(stage05_schema()), len(row_map_schema())):
                if not expected.column(column_index).equals(
                    output_batch.column(column_index)
                ):
                    _fail("CANDIDATE_ID_MISMATCH", "Published candidate ID differs")
            stable_ids = output_batch.column(
                output_batch.schema.get_field_index("stable_source_row_id_v1")
            )
            standard_ids = output_batch.column(
                output_batch.schema.get_field_index(ROW_MAP_ID_COLUMNS[0])
            )
            native_ids = output_batch.column(
                output_batch.schema.get_field_index(ROW_MAP_ID_COLUMNS[1])
            )
            identities.update(stable_ids)
            logical.update(stable_ids, standard_ids, native_ids)
            rows += output_batch.num_rows
            shard_rows += output_batch.num_rows
        if shard_rows != output_artifact.row_count:
            _fail("OUTPUT_ROW_MISMATCH", "Stage 6 row-map shard rows differ")
    return identities.hexdigest(), logical.hexdigest(), rows


def _validate_registry_stream(
    *,
    stage06_root: Path,
    artifacts: Sequence[Stage06ArtifactIdentity],
    metadata: Mapping[bytes, bytes],
    contract_fingerprint: str,
    batch_rows: int,
    target_batch_bytes: int,
    hash_chunk_codepoints: int,
) -> tuple[str, int, dict[str, int]]:
    logical = _RegistryLogicalHasher(
        contract_fingerprint, chunk_codepoints=hash_chunk_codepoints
    )
    previous_id: bytes | None = None
    rows = 0
    total = 0
    standard_total = 0
    native_total = 0
    for artifact in artifacts:
        parquet = pq.ParquetFile(
            stage06_root / artifact.relative_path, page_checksum_verification=True
        )
        if not parquet.schema_arrow.equals(
            registry_schema().with_metadata(dict(metadata)), check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 6 registry schema differs")
        shard_rows = 0
        for batch in _iter_bounded_batches(
            parquet,
            batch_rows=batch_rows,
            target_batch_bytes=target_batch_bytes,
        ):
            if any(
                batch.column(index).null_count for index in range(batch.num_columns)
            ):
                _fail("OUTPUT_NULL", "Stage 6 registry contains null")
            for row_index in range(batch.num_rows):
                candidate_id = batch.column(0)[row_index].as_py()
                candidate_lower = batch.column(1)[row_index].as_py()
                counts = [
                    int(batch.column(index)[row_index].as_py()) for index in range(2, 5)
                ]
                if not isinstance(candidate_id, bytes) or not isinstance(
                    candidate_lower, str
                ):
                    _fail("REGISTRY_SCHEMA_MISMATCH", "Registry scalar type differs")
                if previous_id is not None and candidate_id <= previous_id:
                    _fail("REGISTRY_ORDER_MISMATCH", "Registry ID order is not strict")
                expected_id = exact_candidate_id_v1(
                    candidate_lower, chunk_codepoints=hash_chunk_codepoints
                )
                if candidate_id != expected_id:
                    _fail("CANDIDATE_ID_MISMATCH", "Registry candidate ID differs")
                if counts[0] != counts[1] + counts[2] or counts[0] < 1:
                    _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Registry counts differ")
                logical.update_row(candidate_id, candidate_lower, *counts)
                previous_id = candidate_id
                total += counts[0]
                standard_total += counts[1]
                native_total += counts[2]
                rows += 1
                shard_rows += 1
        if shard_rows != artifact.row_count:
            _fail("REGISTRY_COUNT_MISMATCH", "Registry shard rows differ")
    return (
        logical.hexdigest(),
        rows,
        {
            "REGISTRY_OCCURRENCE_SUM": total,
            "REGISTRY_STANDARD_OCCURRENCE_SUM": standard_total,
            "REGISTRY_NATIVE_OCCURRENCE_SUM": native_total,
        },
    )


def _expected_topology(
    row_artifacts: Sequence[Stage06ArtifactIdentity],
    registry_artifacts: Sequence[Stage06ArtifactIdentity],
) -> tuple[set[str], set[str]]:
    directories = {"row_map", "row_map/data", "registry", "registry/data"}
    files = {STAGE06_MANIFEST_NAME, STAGE06_SUCCESS_MARKER}
    files.update(item.relative_path for item in row_artifacts)
    files.update(item.relative_path for item in registry_artifacts)
    return directories, files


def _observed_topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        _require_mode(current, 0o700, "PERMISSION_FAILURE")
        for name in directory_names:
            path = current / name
            _require_directory(path, "STAGE06_OUTPUT_INVALID")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "STAGE06_OUTPUT_INVALID")
            _require_mode(path, 0o600, "PERMISSION_FAILURE")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def validate_stage06_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    stage05_output_directory: Path,
    authoritative_development: bool = True,
    batch_rows: int = 2_048,
    target_batch_bytes: int = DEFAULT_TARGET_BATCH_BYTES,
    duckdb_memory_limit: str = "8GB",
    duckdb_threads: int = 4,
    hash_chunk_codepoints: int = DEFAULT_HASH_CHUNK_CODEPOINTS,
) -> Stage06MaterializationOutcome:
    """Independently reopen Stage 5 and every published Stage 6 artifact."""
    validate_stage06_runtime()
    _digest_bytes(expected_manifest_sha256)
    _reject_holdout_paths(output_directory, stage05_output_directory)
    _require_directory(output_directory, "STAGE06_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    manifest_path = output_directory / STAGE06_MANIFEST_NAME
    success_path = output_directory / STAGE06_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE06_TERMINAL_MISSING")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE06_MANIFEST_SHA256_MISMATCH", "Stage 6 manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE06_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE06_SUCCESS_INVALID")
    if (
        manifest.get("stage06_manifest_version") != STAGE06_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage06_manifest_sha256") != manifest_sha
        or success.get("stage06_manifest_size_bytes")
        != manifest_path.stat(follow_symlinks=False).st_size
    ):
        _fail("STAGE06_TERMINAL_MISMATCH", "Stage 6 terminal state differs")
    binding = _binding_from_manifest(manifest)
    validate_stage06_input_binding(
        binding, authoritative_development=authoritative_development
    )
    contract_fingerprint = stage06_contract_fingerprint_v1(binding)
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 identity is malformed")
    if (
        scientific.get("stage06_contract_version") != STAGE06_CONTRACT_VERSION
        or scientific.get("stage06_profile_version") != STAGE06_PROFILE_VERSION
        or scientific.get("stage06_schema_version") != STAGE06_SCHEMA_VERSION
        or scientific.get("stage06_schema_fingerprint") != stage06_schema_fingerprint()
        or scientific.get("stage06_contract_fingerprint") != contract_fingerprint
        or scientific.get("stage06_candidate_id_version")
        != STAGE06_CANDIDATE_ID_VERSION
        or scientific.get("stage06_candidate_id_domain_hex")
        != STAGE06_CANDIDATE_ID_DOMAIN.hex()
        or scientific.get("exact_comparison") != STAGE06_EXACT_COMPARISON
        or scientific.get("deduplication_scope") != STAGE06_SCOPE
        or scientific.get("unavailable_rule") != STAGE06_UNAVAILABLE_RULE
        or scientific.get("registry_order") != STAGE06_REGISTRY_ORDER
        or scientific.get("same_row_equal_rule") != STAGE06_SAME_ROW_EQUAL_RULE
        or scientific.get("clean_surface_rule") != STAGE06_CLEAN_SURFACE_RULE
        or scientific.get("row_map_id_columns") != list(ROW_MAP_ID_COLUMNS)
        or scientific.get("registry_columns") != list(REGISTRY_COLUMNS)
    ):
        _fail("STAGE06_FINGERPRINT_MISMATCH", "Stage 6 scientific identity differs")
    if (
        not isinstance(validation, dict)
        or validation.get("validation_contract_version") != STAGE06_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE06_VALIDATION_INCOMPLETE", "Stage 6 validation is incomplete")
    bounded = physical.get("bounded_memory_architecture")
    if (
        not isinstance(bounded, dict)
        or bounded.get("memory_scales_with_population") is not False
        or bounded.get("population_sized_python_candidate_map_used") is not False
        or bounded.get("duckdb_disk_backed_grouping") is not True
        or physical.get("owner_only_permissions") is not True
    ):
        _fail("STAGE06_MANIFEST_INVALID", "Bounded-memory evidence differs")
    row_artifacts = _manifest_artifacts(
        output_directory,
        physical,
        key="row_map_artifacts",
        directory=ROW_MAP_DIRECTORY,
    )
    registry_artifacts = _manifest_artifacts(
        output_directory,
        physical,
        key="registry_artifacts",
        directory=REGISTRY_DIRECTORY,
    )
    expected_dirs, expected_files = _expected_topology(
        row_artifacts, registry_artifacts
    )
    observed_dirs, observed_files = _observed_topology(output_directory)
    if observed_dirs != expected_dirs or observed_files != expected_files:
        _fail("STAGE06_ARTIFACT_MISMATCH", "Stage 6 topology is incomplete")
    upstream = _stage05_artifacts(stage05_output_directory, binding)
    row_metadata = _row_map_metadata(binding, contract_fingerprint)
    registry_metadata = _registry_metadata(binding, contract_fingerprint)
    ordered, row_map_logical, rows = _validate_row_map_stream(
        stage05_root=stage05_output_directory,
        stage06_root=output_directory,
        upstream=upstream,
        row_artifacts=row_artifacts,
        row_metadata=row_metadata,
        contract_fingerprint=contract_fingerprint,
        batch_rows=batch_rows,
        target_batch_bytes=target_batch_bytes,
        hash_chunk_codepoints=hash_chunk_codepoints,
    )
    registry_logical, unique_candidates, registry_sums = _validate_registry_stream(
        stage06_root=output_directory,
        artifacts=registry_artifacts,
        metadata=registry_metadata,
        contract_fingerprint=contract_fingerprint,
        batch_rows=batch_rows,
        target_batch_bytes=target_batch_bytes,
        hash_chunk_codepoints=hash_chunk_codepoints,
    )
    logical = stage06_logical_dataset_sha256_v1(
        contract_fingerprint,
        row_map_logical,
        registry_logical,
        source_rows=rows,
        unique_candidates=unique_candidates,
    )
    if (
        rows != binding.expected_row_count
        or ordered != binding.upstream_ordered_identity_sha256
        or scientific.get("source_row_count") != rows
        or scientific.get("unique_candidate_count") != unique_candidates
        or scientific.get("stage06_row_map_logical_sha256_v1") != row_map_logical
        or scientific.get("stage06_registry_logical_sha256_v1") != registry_logical
        or scientific.get("stage06_logical_dataset_sha256_v1") != logical
        or success.get("stage06_logical_dataset_sha256_v1") != logical
        or success.get("stage06_schema_fingerprint") != stage06_schema_fingerprint()
        or success.get("ordered_stable_identity_sha256_v1") != ordered
        or success.get("source_row_count") != rows
        or success.get("unique_candidate_count") != unique_candidates
        or success.get("row_map_shard_count") != len(row_artifacts)
        or success.get("registry_shard_count") != len(registry_artifacts)
    ):
        _fail("STAGE06_FINGERPRINT_MISMATCH", "Stage 6 logical identity differs")

    validation_temp = output_directory.parent / (
        f".{output_directory.name}.{os.getpid()}.validation"
    )
    if validation_temp.exists() or validation_temp.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 6 validation state already exists")
    validation_temp.mkdir(mode=0o700)
    spill = validation_temp / "spill"
    spill.mkdir(mode=0o700)
    database = validation_temp / "validation.duckdb"
    connection = duckdb.connect(str(database))
    database.chmod(0o600)
    try:
        _configure_duckdb(
            connection,
            memory_limit=duckdb_memory_limit,
            threads=duckdb_threads,
            spill_directory=spill,
        )
        row_paths = [
            str(output_directory / item.relative_path) for item in row_artifacts
        ]
        registry_paths = [
            str(output_directory / item.relative_path) for item in registry_artifacts
        ]
        connection.read_parquet(row_paths).create_view("stage05_input")
        collision_metrics = _build_registry_tables(connection)
        observed_metrics = _collect_metrics(connection)
        observed_metrics["COLLISION_EXACTNESS"] = collision_metrics
        connection.read_parquet(registry_paths).create_view("stage06_registry")
        row = connection.execute(
            f"""
            SELECT
                count(*) FILTER (WHERE r.{REGISTRY_COLUMNS[0]} IS NULL),
                count(*) FILTER (
                    WHERE r.{REGISTRY_COLUMNS[0]} IS NOT NULL
                      AND encode(r.{REGISTRY_COLUMNS[1]}) != o.candidate_bytes
                )
            FROM stage06_occurrences o
            LEFT JOIN stage06_registry r
              ON o.candidate_id = r.{REGISTRY_COLUMNS[0]}
            """
        ).fetchone()
        assert row is not None
        count_mismatches = _query_uint(
            connection,
            f"""
            SELECT count(*)
            FROM candidate_groups g
            JOIN stage06_registry r
              ON g.candidate_id = r.{REGISTRY_COLUMNS[0]}
            WHERE g.occurrence_count != r.{REGISTRY_COLUMNS[2]}
               OR g.standard_occurrence_count != r.{REGISTRY_COLUMNS[3]}
               OR g.native_occurrence_count != r.{REGISTRY_COLUMNS[4]}
            """,
        )
        duplicate_ids = _query_uint(
            connection,
            "SELECT count(*) - count(DISTINCT stable_source_row_id_v1) "
            "FROM stage05_input",
        )
        observed_metrics["MAP_BACK_INTEGRITY"] = {
            "SOURCE_TO_REGISTRY_MISSING": int(row[0]),
            "SOURCE_TO_REGISTRY_TEXT_MISMATCHES": int(row[1]),
            "REGISTRY_COUNT_MISMATCHES": count_mismatches,
            "DUPLICATE_SOURCE_IDENTITIES": duplicate_ids,
        }
    except Stage06ValidationError:
        raise
    except (OSError, duckdb.Error) as error:
        raise Stage06ValidationError(
            "STAGE06_READBACK_FAILURE", "Stage 6 independent aggregation failed"
        ) from error
    finally:
        connection.close()
        shutil.rmtree(validation_temp)
    recorded_metrics = manifest.get("development_metrics")
    if recorded_metrics != observed_metrics:
        _fail("STAGE06_METRIC_MISMATCH", "Stage 6 aggregate metrics differ")
    if (
        registry_sums["REGISTRY_OCCURRENCE_SUM"]
        != cast(dict[str, int], observed_metrics["RECONCILIATION"])[
            "REGISTRY_OCCURRENCE_SUM"
        ]
        or registry_sums["REGISTRY_STANDARD_OCCURRENCE_SUM"]
        != cast(dict[str, int], observed_metrics["RECONCILIATION"])[
            "REGISTRY_STANDARD_OCCURRENCE_SUM"
        ]
        or registry_sums["REGISTRY_NATIVE_OCCURRENCE_SUM"]
        != cast(dict[str, int], observed_metrics["RECONCILIATION"])[
            "REGISTRY_NATIVE_OCCURRENCE_SUM"
        ]
    ):
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Registry sums differ")
    if any(cast(dict[str, int], observed_metrics["MAP_BACK_INTEGRITY"]).values()):
        _fail("MAP_BACK_INTEGRITY_FAILURE", "Published map-back differs")
    performance = manifest.get("performance")
    if not isinstance(performance, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 performance is malformed")
    input_binding_sha = _required_text(
        physical.get("stage06_input_binding_sha256"), "STAGE06_MANIFEST_INVALID"
    )
    _digest_bytes(input_binding_sha)
    if success.get("stage06_input_binding_sha256") != input_binding_sha:
        _fail("STAGE06_TERMINAL_MISMATCH", "Stage 6 input binding differs")
    return Stage06MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=logical,
        row_map_logical_sha256_v1=row_map_logical,
        registry_logical_sha256_v1=registry_logical,
        schema_fingerprint=stage06_schema_fingerprint(),
        input_binding_sha256=input_binding_sha,
        manifest_sha256=manifest_sha,
        ordered_identity_sha256=ordered,
        row_count=rows,
        unique_candidate_count=unique_candidates,
        row_map_shard_count=len(row_artifacts),
        registry_shard_count=len(registry_artifacts),
        metrics=cast(Mapping[str, object], recorded_metrics),
        performance=cast(Mapping[str, int | str], performance),
    )


__all__ = [
    "ACCEPTED_BENCHMARK_FINGERPRINT",
    "ACCEPTED_DEVELOPMENT_ROWS",
    "ACCEPTED_FIXED_500_FINGERPRINT",
    "ACCEPTED_STAGE05_INPUT_BINDING_SHA256",
    "ACCEPTED_STAGE05_LOGICAL_FINGERPRINT",
    "ACCEPTED_STAGE05_MANIFEST_SHA256",
    "ACCEPTED_STAGE05_ORDERED_IDENTITY_SHA256",
    "ACCEPTED_STAGE05_SCHEMA_FINGERPRINT",
    "REGISTRY_COLUMNS",
    "ROW_MAP_ID_COLUMNS",
    "STAGE06_CANDIDATE_ID_DOMAIN",
    "STAGE06_CANDIDATE_ID_VERSION",
    "STAGE06_CONTRACT_VERSION",
    "STAGE06_INPUT_BINDING_VERSION",
    "STAGE06_MANIFEST_NAME",
    "STAGE06_PROFILE_VERSION",
    "Stage06InputBinding",
    "Stage06MaterializationOutcome",
    "Stage06RunConfig",
    "Stage06ValidationError",
    "exact_candidate_id_v1",
    "load_stage06_input_binding",
    "materialize_stage06",
    "registry_schema",
    "row_map_schema",
    "stage06_contract_fingerprint_v1",
    "stage06_logical_dataset_sha256_v1",
    "stage06_schema_fingerprint",
    "validate_stage06_bundle",
    "validate_stage06_input_binding",
    "validate_stage06_runtime",
    "write_stage06_input_binding",
]

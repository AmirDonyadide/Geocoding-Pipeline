"""Frozen, fail-closed Stage 7 libpostal parsing materialization."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
import stat
import struct
import sys
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..script_reference import ScriptReference, unicode_script_reference_paths
from .s03_cleaning import EXPECTED_PYARROW_VERSION, EXPECTED_PYTHON_VERSION
from .s06_exact_deduplication import (
    ACCEPTED_BENCHMARK_FINGERPRINT,
    ACCEPTED_FIXED_500_FINGERPRINT,
    REGISTRY_COLUMNS,
    ROW_MAP_ID_COLUMNS,
    STAGE06_CONTRACT_VERSION,
    STAGE06_MANIFEST_NAME,
    STAGE06_PROFILE_VERSION,
    registry_schema,
    validate_stage06_bundle,
)
from .s07_design_diagnostic import _candidate_features
from .s07_libpostal_adapter import PARSED_EMPTY, PARSED_NONEMPTY, LibpostalComponent
from .s07_output_schema import (
    STAGE07_STATUS_FIELD,
    component_list_field,
    one_component_list_array,
)
from .s07_parser_bundle import (
    LIBPOSTAL_SOURCE_COMMIT,
    LIBPOSTAL_VERSION,
    PARSER_CALL,
    PARSER_CONTEXT_POLICY,
    PYPPOSTAL_SOURCE_COMMIT,
    PYPPOSTAL_VERSION,
    validate_parser_bundle,
)
from .s07_supervised_parser import Stage07SupervisorError, SupervisedParser


STAGE07_CONTRACT_VERSION = "stage07_libpostal_parsing_contract_v1"
STAGE07_PROFILE_VERSION = "stage07_libpostal_parsing_profile_v1"
STAGE07_INPUT_BINDING_VERSION = "stage07_input_binding_v1"
STAGE07_SCHEMA_VERSION = "stage07_libpostal_parsing_schema_v1"
STAGE07_MANIFEST_VERSION = "stage07_manifest_v1"
STAGE07_VALIDATION_VERSION = "stage07_bundle_validation_v1"
STAGE07_MANIFEST_NAME = "stage07_manifest.json"
STAGE07_SUCCESS_MARKER = "_SUCCESS.json"
STAGE07_IN_PROGRESS_MARKER = "_IN_PROGRESS"
STAGE07_REGISTRY_DIRECTORY = "registry/data"
STAGE07_STATUS_VOCABULARY = (PARSED_NONEMPTY, PARSED_EMPTY)
STAGE07_EXACT_INPUT_FIELD = REGISTRY_COLUMNS[1]
STAGE07_PARSE_POLICY = "EXACT_LOWERCASE_CANDIDATE_ONCE_NO_HINTS"
STAGE07_COMPONENT_POLICY = "ORDERED_EXACT_DUPLICATES_PRESERVED_NO_LABEL_MAPPING"
STAGE07_EMPTY_POLICY = "PARSED_EMPTY_NON_NULL_EXACT_EMPTY_LARGE_LIST"
STAGE07_CRASH_POLICY = "ONE_EXACT_FRESH_RETRY_THEN_ABORT_PUBLICATION"
STAGE07_TIMEOUT_POLICY = "NO_PER_CANDIDATE_TIMEOUT_GLOBAL_SLURM_LIMIT_ONLY"
STAGE07_RESOURCE_POLICY = "DEVELOPMENT_180_GIB_NO_INTERNAL_ADDRESS_SPACE_CAP"
STAGE07_CONCURRENCY_POLICY = "ONE_SYNCHRONOUS_LONG_LIVED_CHILD"
STAGE07_REGISTRY_ORDER = "EXACT_ACCEPTED_STAGE06_REGISTRY_ORDER"

ACCEPTED_STAGE06_SCHEMA_FINGERPRINT = (
    "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
)
ACCEPTED_STAGE06_LOGICAL_FINGERPRINT = (
    "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
)
ACCEPTED_STAGE06_INPUT_BINDING_SHA256 = (
    "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
)
ACCEPTED_STAGE06_MANIFEST_SHA256 = (
    "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
)
ACCEPTED_STAGE06_ORDERED_IDENTITY_SHA256 = (
    "fe2a4758582c1880d2b5c62dfc5c587d865e05d13033af9f5e8208b58e2a0487"
)
ACCEPTED_STAGE06_REGISTRY_ROWS = 51_779
ACCEPTED_STAGE06_OCCURRENCES = 69_747
ACCEPTED_STAGE06_STANDARD_OCCURRENCES = 34_822
ACCEPTED_STAGE06_NATIVE_OCCURRENCES = 34_925
ACCEPTED_PARSER_BUNDLE_FINGERPRINT = (
    "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
)
ACCEPTED_PARSER_MODEL_DATA_FINGERPRINT = (
    "0b067a2697e9f90cef92c806701c08648a1f5127c17f0f3168ecaed186dc3293"
)
ACCEPTED_PYPPOSTAL_RUNTIME_FINGERPRINT = (
    "ccc547bfdcaf391685cbb3285be9a02d84c28c7671dcafb4450d25c03920f7ff"
)
ACCEPTED_LIBPOSTAL_SHARED_LIBRARY_SHA256 = (
    "3e2aa3e23b62c22b77827b47d78692d49ae3d693c07ee7ad3763e9b97438cb5e"
)
ACCEPTED_PARSER_BUNDLE_MANIFEST_SHA256 = (
    "12a0080bff6b3ed2420847124eb918d91b7582214e3d4b037628bf5b9022340d"
)

_CONTRACT_DOMAIN = b"SAFE_STAGE07_SCIENTIFIC_CONTRACT_V1"
_SCHEMA_DOMAIN = b"SAFE_STAGE07_ARROW_SCHEMA_V1"
_LOGICAL_DOMAIN = b"SAFE_STAGE07_LOGICAL_REGISTRY_V1"
_DATASET_DOMAIN = b"SAFE_STAGE07_LOGICAL_DATASET_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Stage07ValidationError(RuntimeError):
    """Privacy-safe Stage 7 failure with a stable public code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ValidationError(code, detail)


@dataclass(frozen=True, slots=True)
class Stage07InputBinding:
    stage06_contract_version: str
    stage06_profile_version: str
    stage06_schema_fingerprint: str
    stage06_logical_fingerprint: str
    stage06_input_binding_sha256: str
    stage06_manifest_sha256: str
    stage06_ordered_identity_sha256: str
    stage06_registry_rows: int
    stage06_occurrences: int
    stage06_standard_occurrences: int
    stage06_native_occurrences: int
    benchmark_fingerprint: str
    fixed_500_fingerprint: str
    parser_bundle_fingerprint: str
    parser_model_data_fingerprint: str
    pypostal_runtime_fingerprint: str
    libpostal_shared_library_sha256: str
    parser_bundle_manifest_sha256: str
    parser_call: str
    parser_context_policy: str
    parser_initialization_policy: str
    parser_concurrency_policy: str
    parser_crash_policy: str
    parser_timeout_policy: str
    resource_policy: str

    def to_dict(self) -> dict[str, str | int]:
        return {"stage07_input_binding_version": STAGE07_INPUT_BINDING_VERSION, **asdict(self)}


@dataclass(frozen=True, slots=True)
class Stage07RunConfig:
    stage05_output_directory: Path
    stage06_output_directory: Path
    input_binding_file: Path
    expected_input_binding_sha256: str
    parser_bundle_directory: Path
    expected_parser_bundle_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    authoritative_development: bool = True
    production: bool = True
    input_batch_rows: int = 64
    output_batch_rows: int = 64
    target_batch_bytes: int = 128 * 1024 * 1024
    output_shard_rows: int = 4_096
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        _digest(self.expected_input_binding_sha256)
        _digest(self.expected_parser_bundle_fingerprint)
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA is malformed")
        for bounded_value in (
            self.input_batch_rows,
            self.output_batch_rows,
            self.target_batch_bytes,
            self.output_shard_rows,
        ):
            if isinstance(bounded_value, bool) or bounded_value < 1:
                _fail("INVALID_BATCH_SIZE", "A bounded Stage 7 size is invalid")
        _reject_holdout_paths(
            self.stage05_output_directory,
            self.stage06_output_directory,
            self.input_binding_file,
            self.parser_bundle_directory,
            self.output_directory,
        )
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(value, str)
                or not value
                or len(value) > 128
                or "\x00" in value
            ):
                _fail("INVALID_OPERATIONAL_METADATA", "Operational metadata differs")


@dataclass(frozen=True, slots=True)
class Stage07ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage07MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    registry_logical_sha256_v1: str
    schema_fingerprint: str
    contract_fingerprint: str
    input_binding_sha256: str
    manifest_sha256: str
    candidate_count: int
    shard_count: int
    metrics: Mapping[str, object]
    performance: Mapping[str, int | float | str]
    publication_validation_milliseconds: int = 0


def accepted_stage07_input_binding() -> Stage07InputBinding:
    return Stage07InputBinding(
        stage06_contract_version=STAGE06_CONTRACT_VERSION,
        stage06_profile_version=STAGE06_PROFILE_VERSION,
        stage06_schema_fingerprint=ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
        stage06_logical_fingerprint=ACCEPTED_STAGE06_LOGICAL_FINGERPRINT,
        stage06_input_binding_sha256=ACCEPTED_STAGE06_INPUT_BINDING_SHA256,
        stage06_manifest_sha256=ACCEPTED_STAGE06_MANIFEST_SHA256,
        stage06_ordered_identity_sha256=ACCEPTED_STAGE06_ORDERED_IDENTITY_SHA256,
        stage06_registry_rows=ACCEPTED_STAGE06_REGISTRY_ROWS,
        stage06_occurrences=ACCEPTED_STAGE06_OCCURRENCES,
        stage06_standard_occurrences=ACCEPTED_STAGE06_STANDARD_OCCURRENCES,
        stage06_native_occurrences=ACCEPTED_STAGE06_NATIVE_OCCURRENCES,
        benchmark_fingerprint=ACCEPTED_BENCHMARK_FINGERPRINT,
        fixed_500_fingerprint=ACCEPTED_FIXED_500_FINGERPRINT,
        parser_bundle_fingerprint=ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
        parser_model_data_fingerprint=ACCEPTED_PARSER_MODEL_DATA_FINGERPRINT,
        pypostal_runtime_fingerprint=ACCEPTED_PYPPOSTAL_RUNTIME_FINGERPRINT,
        libpostal_shared_library_sha256=ACCEPTED_LIBPOSTAL_SHARED_LIBRARY_SHA256,
        parser_bundle_manifest_sha256=ACCEPTED_PARSER_BUNDLE_MANIFEST_SHA256,
        parser_call=PARSER_CALL,
        parser_context_policy=PARSER_CONTEXT_POLICY,
        parser_initialization_policy="ONE_INITIALIZATION_PER_LONG_LIVED_CHILD_PROCESS",
        parser_concurrency_policy=STAGE07_CONCURRENCY_POLICY,
        parser_crash_policy=STAGE07_CRASH_POLICY,
        parser_timeout_policy=STAGE07_TIMEOUT_POLICY,
        resource_policy=STAGE07_RESOURCE_POLICY,
    )


def _digest(value: str) -> bytes:
    if _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_FINGERPRINT", "A SHA-256 fingerprint is malformed")
    return bytes.fromhex(value)


def _reject_holdout_paths(*paths: Path) -> None:
    if any(
        "holdout" in part.casefold()
        for path in paths
        for part in path.resolve(strict=False).parts
    ):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07ValidationError(
            "CONTROLLED_READ_FAILURE", "A controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage07ValidationError(
            "CONTROLLED_WRITE_FAILURE", "A controlled artifact could not be written"
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


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07ValidationError(code, "Controlled JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON is not an object")
    return cast(dict[str, Any], value)


def validate_stage07_input_binding(
    binding: Stage07InputBinding, *, authoritative_development: bool = False
) -> None:
    for value in (
        binding.stage06_schema_fingerprint,
        binding.stage06_logical_fingerprint,
        binding.stage06_input_binding_sha256,
        binding.stage06_manifest_sha256,
        binding.stage06_ordered_identity_sha256,
        binding.benchmark_fingerprint,
        binding.fixed_500_fingerprint,
        binding.parser_bundle_fingerprint,
        binding.parser_model_data_fingerprint,
        binding.pypostal_runtime_fingerprint,
        binding.libpostal_shared_library_sha256,
        binding.parser_bundle_manifest_sha256,
    ):
        _digest(value)
    for count in (
        binding.stage06_registry_rows,
        binding.stage06_occurrences,
        binding.stage06_standard_occurrences,
        binding.stage06_native_occurrences,
    ):
        if isinstance(count, bool) or not 0 < count <= 0xFFFF_FFFF_FFFF_FFFF:
            _fail("INVALID_ROW_COUNT", "Stage 7 binding count is invalid")
    if binding.stage06_occurrences != (
        binding.stage06_standard_occurrences + binding.stage06_native_occurrences
    ):
        _fail("OCCURRENCE_RECONCILIATION_FAILURE", "Binding occurrences differ")
    if binding.parser_call != PARSER_CALL or binding.parser_context_policy != PARSER_CONTEXT_POLICY:
        _fail("PARSER_OPTIONS_MISMATCH", "Stage 7 parser call or context differs")
    if binding.parser_initialization_policy != "ONE_INITIALIZATION_PER_LONG_LIVED_CHILD_PROCESS":
        _fail("PARSER_OPTIONS_MISMATCH", "Parser initialization policy differs")
    if binding.parser_concurrency_policy != STAGE07_CONCURRENCY_POLICY:
        _fail("PARSER_OPTIONS_MISMATCH", "Parser concurrency policy differs")
    if binding.parser_crash_policy != STAGE07_CRASH_POLICY:
        _fail("PARSER_OPTIONS_MISMATCH", "Parser crash policy differs")
    if binding.parser_timeout_policy != STAGE07_TIMEOUT_POLICY:
        _fail("PARSER_OPTIONS_MISMATCH", "Parser timeout policy differs")
    if binding.resource_policy != STAGE07_RESOURCE_POLICY:
        _fail("PARSER_RESOURCE_POLICY_MISMATCH", "Resource policy differs")
    if authoritative_development and binding != accepted_stage07_input_binding():
        _fail(
            "AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH",
            "Stage 7 input binding differs from accepted Stage 6/parser evidence",
        )


def write_stage07_input_binding(path: Path, binding: Stage07InputBinding) -> str:
    validate_stage07_input_binding(binding)
    _reject_holdout_paths(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    if path.exists() or path.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 input binding already exists")
    _write_json_exclusive(path, binding.to_dict())
    return _sha256_file(path)


def load_stage07_input_binding(
    path: Path,
    *,
    expected_sha256: str,
    authoritative_development: bool = False,
) -> Stage07InputBinding:
    _digest(expected_sha256)
    _reject_holdout_paths(path)
    _require_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Stage 7 input binding SHA differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    expected_keys = set(Stage07InputBinding.__dataclass_fields__) | {
        "stage07_input_binding_version"
    }
    if set(value) != expected_keys or value.get("stage07_input_binding_version") != STAGE07_INPUT_BINDING_VERSION:
        _fail("INPUT_BINDING_INVALID", "Stage 7 input binding fields differ")
    kwargs = {key: value[key] for key in Stage07InputBinding.__dataclass_fields__}
    try:
        binding = Stage07InputBinding(**kwargs)
    except TypeError as error:
        raise Stage07ValidationError(
            "INPUT_BINDING_INVALID", "Stage 7 input binding types differ"
        ) from error
    validate_stage07_input_binding(
        binding, authoritative_development=authoritative_development
    )
    return binding


def stage07_schema() -> pa.Schema:
    return pa.schema(
        (
            *registry_schema(),
            pa.field(STAGE07_STATUS_FIELD, pa.string(), nullable=False),
            component_list_field(),
        )
    )


def stage07_schema_fingerprint() -> str:
    digest = hashlib.sha256(_SCHEMA_DOMAIN)
    digest.update(STAGE07_SCHEMA_VERSION.encode("ascii"))
    for field in stage07_schema():
        for value in (field.name, str(field.type), str(field.nullable).lower()):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def stage07_contract_fingerprint(binding: Stage07InputBinding) -> str:
    validate_stage07_input_binding(binding)
    payload = {
        "contract": STAGE07_CONTRACT_VERSION,
        "profile": STAGE07_PROFILE_VERSION,
        "schema": STAGE07_SCHEMA_VERSION,
        "schema_fingerprint": stage07_schema_fingerprint(),
        "exact_input_field": STAGE07_EXACT_INPUT_FIELD,
        "parse_policy": STAGE07_PARSE_POLICY,
        "component_policy": STAGE07_COMPONENT_POLICY,
        "empty_policy": STAGE07_EMPTY_POLICY,
        "crash_policy": STAGE07_CRASH_POLICY,
        "timeout_policy": STAGE07_TIMEOUT_POLICY,
        "resource_policy": STAGE07_RESOURCE_POLICY,
        "status_vocabulary": list(STAGE07_STATUS_VOCABULARY),
        "registry_order": STAGE07_REGISTRY_ORDER,
        "stage8_label_mapping": False,
        "candidate_truncation": False,
        "candidate_skipping": False,
        "substring_parsing": False,
        "parser_process_crash_published_status": False,
        "binding": binding.to_dict(),
    }
    digest = hashlib.sha256(_CONTRACT_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    return digest.hexdigest()


def _metadata(binding: Stage07InputBinding, contract_fingerprint: str) -> dict[bytes, bytes]:
    return {
        b"stage07_contract_version": STAGE07_CONTRACT_VERSION.encode("ascii"),
        b"stage07_profile_version": STAGE07_PROFILE_VERSION.encode("ascii"),
        b"stage07_schema_version": STAGE07_SCHEMA_VERSION.encode("ascii"),
        b"stage07_schema_fingerprint": stage07_schema_fingerprint().encode("ascii"),
        b"stage07_contract_fingerprint": contract_fingerprint.encode("ascii"),
        b"stage07_input_field": STAGE07_EXACT_INPUT_FIELD.encode("ascii"),
        b"stage06_manifest_sha256": binding.stage06_manifest_sha256.encode("ascii"),
        b"parser_bundle_fingerprint": binding.parser_bundle_fingerprint.encode("ascii"),
    }


class _LogicalHasher:
    def __init__(self, contract_fingerprint: str) -> None:
        self._digest = hashlib.sha256(_LOGICAL_DOMAIN)
        self._digest.update(_digest(contract_fingerprint))

    def _bytes(self, value: bytes) -> None:
        self._digest.update(len(value).to_bytes(8, "big"))
        self._digest.update(value)

    def _text(self, value: str) -> None:
        encoded = value.encode("utf-8", errors="strict")
        if encoded.decode("utf-8", errors="strict") != value:
            _fail("UTF8_ROUND_TRIP_FAILURE", "Stage 7 text round-trip differs")
        self._bytes(encoded)

    def update(
        self,
        candidate_id: bytes,
        candidate: str,
        counts: Sequence[int],
        status: str,
        components: Sequence[LibpostalComponent],
    ) -> None:
        self._bytes(candidate_id)
        self._text(candidate)
        for count in counts:
            self._digest.update(struct.pack(">Q", count))
        self._text(status)
        self._digest.update(struct.pack(">Q", len(components)))
        for component in components:
            self._text(component.label)
            self._text(component.value)

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def stage07_logical_dataset_sha256(
    contract_fingerprint: str, registry_logical: str, candidate_count: int
) -> str:
    digest = hashlib.sha256(_DATASET_DOMAIN)
    digest.update(_digest(contract_fingerprint))
    digest.update(_digest(registry_logical))
    digest.update(struct.pack(">Q", candidate_count))
    return digest.hexdigest()


def _require_file(path: Path, code: str) -> None:
    if not path.is_file() or path.is_symlink():
        _fail(code, "Required regular file is absent")


def _require_directory(path: Path, code: str) -> None:
    if not path.is_dir() or path.is_symlink():
        _fail(code, "Required directory is absent")


def _require_mode(path: Path, mode: int, code: str) -> None:
    try:
        observed = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage07ValidationError(code, "Artifact permissions are unreadable") from error
    if observed != mode:
        _fail(code, "Owner-only artifact permissions differ")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stage06_artifact_paths(
    stage06_root: Path, *, kind: str
) -> tuple[Path, ...]:
    manifest = _load_json(stage06_root / STAGE06_MANIFEST_NAME, "STAGE06_MANIFEST_INVALID")
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 physical identity is absent")
    key = f"{kind}_artifacts"
    values = physical.get(key)
    if not isinstance(values, list) or not values:
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact list is absent")
    paths: list[Path] = []
    for value in values:
        if not isinstance(value, dict) or not isinstance(value.get("relative_path"), str):
            _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact entry is malformed")
        path = stage06_root / value["relative_path"]
        _require_file(path, "STAGE06_ARTIFACT_INVALID")
        paths.append(path)
    return tuple(paths)


def _iter_batches(
    paths: Sequence[Path], columns: Sequence[str], batch_rows: int
) -> Iterable[pa.RecordBatch]:
    try:
        for path in paths:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            yield from parquet.iter_batches(
                batch_size=batch_rows, columns=list(columns), use_threads=False
            )
    except (OSError, pa.ArrowException) as error:
        raise Stage07ValidationError(
            "PARQUET_READ_FAILURE", "A protected Parquet stream could not be read"
        ) from error


def _script_reference() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


class _MetricsAccumulator:
    """Disk-backed per-candidate metrics plus bounded categorical counters."""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        path.chmod(0o600)
        self._connection.execute("PRAGMA journal_mode=DELETE")
        self._connection.execute("PRAGMA temp_store=FILE")
        self._connection.execute(
            "CREATE TABLE row_metrics (component_count INTEGER NOT NULL, "
            "input_codepoints INTEGER NOT NULL, output_codepoints INTEGER NOT NULL, "
            "script_bucket TEXT NOT NULL, length_bucket TEXT NOT NULL, "
            "representation_bucket TEXT NOT NULL, repeated_labels INTEGER NOT NULL, "
            "maximum_label_repetition INTEGER NOT NULL, nested_arrow_bytes INTEGER NOT NULL)"
        )
        self.statuses: Counter[str] = Counter()
        self.labels: Counter[str] = Counter()
        self.rows = 0
        self.total_components = 0
        self.maximum_nested_arrow_bytes = 0

    def add(
        self,
        *,
        candidate: str,
        occurrence_count: int,
        standard_count: int,
        native_count: int,
        status: str,
        components: Sequence[LibpostalComponent],
        nested_arrow_bytes: int,
        scripts: ScriptReference,
    ) -> None:
        label_counts = Counter(component.label for component in components)
        self.labels.update(label_counts)
        features = _candidate_features(
            candidate,
            occurrence_count=occurrence_count,
            standard_count=standard_count,
            native_count=native_count,
            script_reference=scripts,
        )
        output_codepoints = sum(len(component.value) for component in components)
        maximum_repetition = max(label_counts.values(), default=0)
        self._connection.execute(
            "INSERT INTO row_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                len(components),
                len(candidate),
                output_codepoints,
                features.script_bucket,
                features.length_bucket,
                features.representation_bucket,
                int(maximum_repetition > 1),
                maximum_repetition,
                nested_arrow_bytes,
            ),
        )
        self.statuses[status] += 1
        self.rows += 1
        self.total_components += len(components)
        self.maximum_nested_arrow_bytes = max(
            self.maximum_nested_arrow_bytes, nested_arrow_bytes
        )

    def _scalar(self, query: str, parameters: Sequence[object] = ()) -> int | float:
        row = self._connection.execute(query, parameters).fetchone()
        if row is None or row[0] is None or not isinstance(row[0], (int, float)):
            _fail("METRIC_AGGREGATION_FAILURE", "A structural metric is absent")
        return cast(int | float, row[0])

    def _quantile(self, column: str, numerator: int, denominator: int) -> int:
        if self.rows == 0:
            return 0
        offset = max(0, (self.rows * numerator + denominator - 1) // denominator - 1)
        return int(
            self._scalar(
                f"SELECT {column} FROM row_metrics ORDER BY {column} LIMIT 1 OFFSET ?",
                (offset,),
            )
        )

    def _groups(self, column: str) -> dict[str, int]:
        result: dict[str, int] = {}
        cursor = self._connection.execute(
            f"SELECT {column}, count(*) FROM row_metrics GROUP BY {column} ORDER BY {column}"
        )
        for key, count in cursor:
            result[str(key)] = int(count)
        return result

    def finish(self) -> dict[str, object]:
        self._connection.commit()
        component_distribution = {
            "min": int(self._scalar("SELECT min(component_count) FROM row_metrics")),
            "median": self._quantile("component_count", 1, 2),
            "mean": float(self._scalar("SELECT avg(component_count) FROM row_metrics")),
            "p95": self._quantile("component_count", 95, 100),
            "p99": self._quantile("component_count", 99, 100),
            "max": int(self._scalar("SELECT max(component_count) FROM row_metrics")),
        }
        output_distribution = {
            "min": int(self._scalar("SELECT min(output_codepoints) FROM row_metrics")),
            "median": self._quantile("output_codepoints", 1, 2),
            "mean": float(self._scalar("SELECT avg(output_codepoints) FROM row_metrics")),
            "p95": self._quantile("output_codepoints", 95, 100),
            "p99": self._quantile("output_codepoints", 99, 100),
            "max": int(self._scalar("SELECT max(output_codepoints) FROM row_metrics")),
        }
        result: dict[str, object] = {
            "CANDIDATE_ROWS": self.rows,
            "STATUS_COUNTS": {key: self.statuses[key] for key in STAGE07_STATUS_VOCABULARY},
            "TOTAL_EMITTED_COMPONENTS": self.total_components,
            "COMPONENT_COUNT_DISTRIBUTION": component_distribution,
            "OUTPUT_VALUE_CODEPOINT_DISTRIBUTION": output_distribution,
            "LABEL_VOCABULARY": sorted(self.labels),
            "LABEL_FREQUENCIES": dict(sorted(self.labels.items())),
            "REPEATED_LABEL_CANDIDATES": int(
                self._scalar("SELECT coalesce(sum(repeated_labels), 0) FROM row_metrics")
            ),
            "MAXIMUM_SAME_LABEL_REPETITION": int(
                self._scalar("SELECT max(maximum_label_repetition) FROM row_metrics")
            ),
            "SINGLE_COMPONENT_PARSES": int(
                self._scalar("SELECT count(*) FROM row_metrics WHERE component_count = 1")
            ),
            "MULTI_COMPONENT_PARSES": int(
                self._scalar("SELECT count(*) FROM row_metrics WHERE component_count > 1")
            ),
            "SCRIPT_STRATIFIED_COUNTS": self._groups("script_bucket"),
            "LENGTH_STRATIFIED_COUNTS": self._groups("length_bucket"),
            "PROVENANCE_STRATIFIED_COUNTS": self._groups("representation_bucket"),
            "MAXIMUM_NESTED_ARROW_BYTES": self.maximum_nested_arrow_bytes,
        }
        return result

    def close(self) -> None:
        self._connection.close()


def _one_row_batch(
    candidate_id: bytes,
    candidate: str,
    counts: Sequence[int],
    status: str,
    components: tuple[LibpostalComponent, ...],
    schema: pa.Schema,
) -> pa.RecordBatch:
    if status not in STAGE07_STATUS_VOCABULARY:
        _fail("PUBLISHED_STATUS_INVALID", "Stage 7 v1 status is not publishable")
    if (status == PARSED_NONEMPTY) != bool(components):
        _fail("PARSER_STATUS_COMPONENT_MISMATCH", "Parser status/list semantics differ")
    arrays: list[pa.Array] = [
        pa.array((candidate_id,), type=pa.binary(32)),
        pa.array((candidate,), type=pa.string()),
        *(pa.array((value,), type=pa.uint64()) for value in counts),
        pa.array((status,), type=pa.string()),
        one_component_list_array(components),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def _artifact_identity(root: Path, path: Path, row_count: int) -> Stage07ArtifactIdentity:
    return Stage07ArtifactIdentity(
        relative_path=path.relative_to(root).as_posix(),
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=row_count,
    )


def _validate_runtime() -> None:
    if sys.version_info[:3] != EXPECTED_PYTHON_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime differs")
    if pa.__version__ != EXPECTED_PYARROW_VERSION:
        _fail("RUNTIME_VERSION_MISMATCH", "PyArrow runtime differs")
    if duckdb.__version__ != "1.5.5":
        _fail("RUNTIME_VERSION_MISMATCH", "DuckDB runtime differs")


def _validate_bundle_identity(binding: Stage07InputBinding, root: Path) -> None:
    outcome = validate_parser_bundle(
        root, expected_parser_bundle_fingerprint=binding.parser_bundle_fingerprint
    )
    if (
        outcome.parser_model_data_fingerprint != binding.parser_model_data_fingerprint
        or outcome.pypostal_runtime_fingerprint != binding.pypostal_runtime_fingerprint
        or outcome.libpostal_shared_library_sha256
        != binding.libpostal_shared_library_sha256
        or outcome.manifest_sha256 != binding.parser_bundle_manifest_sha256
    ):
        _fail("PARSER_BUNDLE_FINGERPRINT_MISMATCH", "Parser bundle identity differs")


def materialize_stage07(config: Stage07RunConfig) -> Stage07MaterializationOutcome:
    """Parse every accepted Stage 6 candidate once and publish atomically."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-libpostal-parsing")
    _validate_runtime()
    binding = load_stage07_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
        authoritative_development=config.authoritative_development,
    )
    if config.expected_parser_bundle_fingerprint != binding.parser_bundle_fingerprint:
        _fail("PARSER_BUNDLE_FINGERPRINT_MISMATCH", "Configured bundle differs")
    _validate_bundle_identity(binding, config.parser_bundle_directory)
    stage06 = validate_stage06_bundle(
        config.stage06_output_directory,
        expected_manifest_sha256=binding.stage06_manifest_sha256,
        stage05_output_directory=config.stage05_output_directory,
        authoritative_development=config.authoritative_development,
        batch_rows=config.input_batch_rows,
        target_batch_bytes=config.target_batch_bytes,
    )
    if (
        stage06.schema_fingerprint != binding.stage06_schema_fingerprint
        or stage06.logical_dataset_sha256_v1 != binding.stage06_logical_fingerprint
        or stage06.input_binding_sha256 != binding.stage06_input_binding_sha256
        or stage06.ordered_identity_sha256 != binding.stage06_ordered_identity_sha256
        or stage06.unique_candidate_count != binding.stage06_registry_rows
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Accepted Stage 6 identity differs")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 output path already exists")
    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 temporary publication path exists")
    old_umask = os.umask(0o077)
    try:
        temporary.mkdir(mode=0o700)
        registry_directory = temporary / STAGE07_REGISTRY_DIRECTORY
        registry_directory.mkdir(parents=True, mode=0o700)
        registry_directory.parent.chmod(0o700)
        _write_exclusive(temporary / STAGE07_IN_PROGRESS_MARKER, b"in_progress\n")
        metrics_path = temporary / ".stage07_metrics.sqlite"
        metrics = _MetricsAccumulator(metrics_path)
        scripts = _script_reference()
        contract_fingerprint = stage07_contract_fingerprint(binding)
        schema = stage07_schema().with_metadata(_metadata(binding, contract_fingerprint))
        logical = _LogicalHasher(contract_fingerprint)
        stage06_paths = _stage06_artifact_paths(
            config.stage06_output_directory, kind="registry"
        )
        candidates = 0
        input_occurrences = 0
        standard_occurrences = 0
        native_occurrences = 0
        serialization_seconds = 0.0
        publication_started = time.perf_counter()
        parse_seconds = 0.0
        pending: list[pa.RecordBatch] = []
        pending_bytes = 0
        shard_rows = 0
        shard_sequence = 0
        artifacts: list[Stage07ArtifactIdentity] = []
        writer: pq.ParquetWriter | None = None
        writer_path: Path | None = None

        def start_writer() -> None:
            nonlocal writer, writer_path, shard_sequence, shard_rows
            shard_sequence += 1
            shard_rows = 0
            writer_path = registry_directory / f"part-{shard_sequence:06d}.parquet"
            writer = pq.ParquetWriter(
                writer_path,
                schema,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                write_page_checksum=True,
                data_page_size=1024 * 1024,
                write_batch_size=256,
            )

        def flush_pending() -> None:
            nonlocal pending, pending_bytes, serialization_seconds
            if not pending:
                return
            if writer is None:
                start_writer()
            assert writer is not None
            started = time.perf_counter()
            table = pa.Table.from_batches(pending, schema=schema)
            writer.write_table(table, row_group_size=min(config.output_batch_rows, table.num_rows))
            serialization_seconds += time.perf_counter() - started
            pending = []
            pending_bytes = 0

        def close_writer() -> None:
            nonlocal writer, writer_path
            if writer is None or writer_path is None:
                return
            flush_pending()
            writer.close()
            writer_path.chmod(0o600)
            artifacts.append(_artifact_identity(temporary, writer_path, shard_rows))
            writer = None
            writer_path = None

        try:
            with SupervisedParser() as supervisor:
                for input_batch in _iter_batches(
                    stage06_paths, REGISTRY_COLUMNS, config.input_batch_rows
                ):
                    for row_index in range(input_batch.num_rows):
                        candidate_id = input_batch.column(0)[row_index].as_py()
                        candidate = input_batch.column(1)[row_index].as_py()
                        counts = tuple(
                            int(input_batch.column(index)[row_index].as_py())
                            for index in range(2, 5)
                        )
                        if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
                            _fail("STAGE06_REGISTRY_INVALID", "Stage 6 registry type differs")
                        parse_started = time.perf_counter()
                        outcome = supervisor.parse(candidate)
                        parse_seconds += time.perf_counter() - parse_started
                        if outcome.components is None or outcome.status not in STAGE07_STATUS_VOCABULARY:
                            _fail("PUBLISHED_STATUS_INVALID", "Supervisor returned a non-v1 result")
                        row_batch = _one_row_batch(
                            candidate_id,
                            candidate,
                            counts,
                            outcome.status,
                            outcome.components,
                            schema,
                        )
                        if writer is None:
                            start_writer()
                        if shard_rows == config.output_shard_rows:
                            close_writer()
                            start_writer()
                        pending.append(row_batch)
                        pending_bytes += row_batch.nbytes
                        shard_rows += 1
                        candidates += 1
                        input_occurrences += counts[0]
                        standard_occurrences += counts[1]
                        native_occurrences += counts[2]
                        logical.update(
                            candidate_id, candidate, counts, outcome.status, outcome.components
                        )
                        metrics.add(
                            candidate=candidate,
                            occurrence_count=counts[0],
                            standard_count=counts[1],
                            native_count=counts[2],
                            status=outcome.status,
                            components=outcome.components,
                            nested_arrow_bytes=row_batch.column(6).nbytes,
                            scripts=scripts,
                        )
                        if (
                            len(pending) >= config.output_batch_rows
                            or pending_bytes >= config.target_batch_bytes
                            or shard_rows == config.output_shard_rows
                        ):
                            flush_pending()
                close_writer()
                supervisor_metrics = {
                    "WORKERS_STARTED": supervisor.workers_started,
                    "WORKER_RESTARTS": supervisor.worker_restarts,
                    "FIRST_ATTEMPT_NATIVE_CRASHES": supervisor.first_attempt_crashes,
                    "RETRY_ATTEMPTS": supervisor.first_attempt_crashes,
                    "CONFIRMED_REPEATED_CRASHES": supervisor.confirmed_repeated_crashes,
                    "CRASH_SUCCESS_NONDETERMINISM": supervisor.crash_success_inconsistencies,
                    "CHANGED_FAILURE_INCONSISTENCIES": supervisor.changed_failure_inconsistencies,
                    "INITIALIZATION_SECONDS": sum(supervisor.worker_initialization_seconds),
                }
            metric_values = metrics.finish()
        finally:
            if writer is not None:
                writer.close()
            metrics.close()
        metrics_path.unlink()
        if (
            candidates != binding.stage06_registry_rows
            or input_occurrences != binding.stage06_occurrences
            or standard_occurrences != binding.stage06_standard_occurrences
            or native_occurrences != binding.stage06_native_occurrences
            or sum(cast(dict[str, int], metric_values["STATUS_COUNTS"]).values())
            != candidates
            or any(
                int(supervisor_metrics[key])
                for key in (
                    "FIRST_ATTEMPT_NATIVE_CRASHES",
                    "CONFIRMED_REPEATED_CRASHES",
                    "CRASH_SUCCESS_NONDETERMINISM",
                    "CHANGED_FAILURE_INCONSISTENCIES",
                )
            )
        ):
            _fail("TOTALITY_FAILURE", "Stage 7 authoritative totality differs")
        registry_logical = logical.hexdigest()
        dataset_logical = stage07_logical_dataset_sha256(
            contract_fingerprint, registry_logical, candidates
        )
        publication_seconds = time.perf_counter() - publication_started
        total_emitted_components = metric_values["TOTAL_EMITTED_COMPONENTS"]
        if not isinstance(total_emitted_components, int):
            _fail("METRIC_AGGREGATION_FAILURE", "Component total type differs")
        performance: dict[str, int | float | str] = {
            "PARSER_INITIALIZATION_SECONDS": float(supervisor_metrics["INITIALIZATION_SECONDS"]),
            "CANDIDATE_PARSING_SECONDS": parse_seconds,
            "SERIALIZATION_AND_PARQUET_SECONDS": serialization_seconds,
            "PREPUBLICATION_SECONDS": publication_seconds,
            "CANDIDATES_PER_SECOND": candidates / parse_seconds if parse_seconds else 0.0,
            "COMPONENTS_PER_SECOND": total_emitted_components / parse_seconds if parse_seconds else 0.0,
            "OUTPUT_BYTES": sum(item.size_bytes for item in artifacts),
            "TEMPORARY_SPILL_BYTES": 0,
        }
        manifest = {
            "stage07_manifest_version": STAGE07_MANIFEST_VERSION,
            "status": "STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "scientific_identity": {
                "stage07_contract_version": STAGE07_CONTRACT_VERSION,
                "stage07_profile_version": STAGE07_PROFILE_VERSION,
                "stage07_schema_version": STAGE07_SCHEMA_VERSION,
                "stage07_schema_fingerprint": stage07_schema_fingerprint(),
                "stage07_contract_fingerprint": contract_fingerprint,
                "stage07_registry_logical_sha256_v1": registry_logical,
                "stage07_logical_dataset_sha256_v1": dataset_logical,
                "stage07_input_binding_sha256": config.expected_input_binding_sha256,
                "stage06_binding": binding.to_dict(),
                "exact_parser_input_field": STAGE07_EXACT_INPUT_FIELD,
                "status_vocabulary": list(STAGE07_STATUS_VOCABULARY),
                "parser_process_crash_is_v1_status": False,
                "components_type": str(component_list_field().type),
                "candidate_count": candidates,
            },
            "physical_identity": {
                "registry_artifacts": [item.to_dict() for item in artifacts],
                "owner_only_permissions": True,
                "atomic_publication": True,
                "bounded_memory_architecture": {
                    "one_candidate_result_at_a_time": True,
                    "bounded_arrow_batches": True,
                    "disk_backed_row_metrics": True,
                    "population_sized_python_registry": False,
                    "population_sized_python_result_list": False,
                    "output_shard_rows": config.output_shard_rows,
                    "target_batch_bytes": config.target_batch_bytes,
                },
            },
            "development_metrics": {
                **metric_values,
                "INPUT_OCCURRENCES": input_occurrences,
                "STANDARD_OCCURRENCES": standard_occurrences,
                "NATIVE_OCCURRENCES": native_occurrences,
                "SUPERVISOR": supervisor_metrics,
            },
            "performance": performance,
            "validation": {
                "validation_contract_version": STAGE07_VALIDATION_VERSION,
                "stage06_bundle_validated": "PASS",
                "parser_bundle_validated": "PASS",
                "exact_stage06_registry_preservation": "PASS",
                "all_candidates_parsed_normally": "PASS",
                "large_list_large_string_serialization": "PASS",
                "ordered_duplicate_components_preserved": "PASS",
                "no_parser_hints": "PASS",
                "no_truncation_skip_or_substring": "PASS",
                "no_stage8_label_mapping": "PASS",
                "bounded_memory": "PASS",
                "holdout_exclusion": "PASS",
                "production_exclusion": "PASS",
                "stage08_not_started": "PASS",
            },
            "operational_provenance": {
                "execution_git_sha": config.execution_git_sha,
                "created_at_utc": _utc_now(),
                "python_version": platform.python_version(),
                "pyarrow_version": pa.__version__,
                "duckdb_version": duckdb.__version__,
                "libpostal_version": LIBPOSTAL_VERSION,
                "libpostal_source_commit": LIBPOSTAL_SOURCE_COMMIT,
                "pypostal_version": PYPPOSTAL_VERSION,
                "pypostal_source_commit": PYPPOSTAL_SOURCE_COMMIT,
                "slurm_requested_memory_gib": 180,
                "internal_address_space_limit": None,
                "per_candidate_timeout": None,
                **dict(config.operational_metadata or {}),
            },
        }
        _write_json_exclusive(temporary / STAGE07_MANIFEST_NAME, manifest)
        manifest_sha = _sha256_file(temporary / STAGE07_MANIFEST_NAME)
        _write_json_exclusive(
            temporary / STAGE07_SUCCESS_MARKER,
            {
                "status": "STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED",
                "stage07_manifest_sha256": manifest_sha,
                "stage07_logical_dataset_sha256_v1": dataset_logical,
                "stage07_schema_fingerprint": stage07_schema_fingerprint(),
                "stage07_input_binding_sha256": config.expected_input_binding_sha256,
                "candidate_count": candidates,
                "shard_count": len(artifacts),
            },
        )
        (temporary / STAGE07_IN_PROGRESS_MARKER).unlink()
        for directory in (registry_directory, registry_directory.parent, temporary):
            _fsync_directory(directory)
        os.replace(temporary, config.output_directory)
        _fsync_directory(parent)
    except (Stage07ValidationError, Stage07SupervisorError):
        raise
    except (OSError, pa.ArrowException, sqlite3.Error) as error:
        raise Stage07ValidationError(
            "STAGE07_MATERIALIZATION_FAILURE", "Stage 7 materialization failed"
        ) from error
    finally:
        os.umask(old_umask)
    validation_started = time.perf_counter()
    validated = validate_stage07_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_sha,
        stage05_output_directory=config.stage05_output_directory,
        stage06_output_directory=config.stage06_output_directory,
        parser_bundle_directory=config.parser_bundle_directory,
        authoritative_development=config.authoritative_development,
        batch_rows=config.input_batch_rows,
        target_batch_bytes=config.target_batch_bytes,
    )
    return replace(
        validated,
        publication_validation_milliseconds=round(
            (time.perf_counter() - validation_started) * 1_000
        ),
    )


def _manifest_artifacts(
    root: Path, physical: Mapping[str, Any]
) -> tuple[Stage07ArtifactIdentity, ...]:
    values = physical.get("registry_artifacts")
    if not isinstance(values, list) or not values:
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 artifacts are absent")
    result: list[Stage07ArtifactIdentity] = []
    for index, raw in enumerate(values, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE07_MANIFEST_INVALID", "Stage 7 artifact is malformed")
        try:
            artifact = Stage07ArtifactIdentity(
                relative_path=str(raw["relative_path"]),
                size_bytes=int(raw["size_bytes"]),
                sha256=str(raw["sha256"]),
                row_count=int(raw["row_count"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise Stage07ValidationError(
                "STAGE07_MANIFEST_INVALID", "Stage 7 artifact fields differ"
            ) from error
        if artifact.relative_path != f"{STAGE07_REGISTRY_DIRECTORY}/part-{index:06d}.parquet":
            _fail("STAGE07_MANIFEST_INVALID", "Stage 7 artifact order differs")
        _digest(artifact.sha256)
        path = root / artifact.relative_path
        _require_file(path, "STAGE07_ARTIFACT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if path.stat(follow_symlinks=False).st_size != artifact.size_bytes or _sha256_file(path) != artifact.sha256:
            _fail("STAGE07_ARTIFACT_MISMATCH", "Stage 7 artifact identity differs")
        result.append(artifact)
    return tuple(result)


def _topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        _require_mode(current_path, 0o700, "PERMISSION_FAILURE")
        for name in directory_names:
            path = current_path / name
            _require_directory(path, "STAGE07_OUTPUT_INVALID")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current_path / name
            _require_file(path, "STAGE07_OUTPUT_INVALID")
            _require_mode(path, 0o600, "PERMISSION_FAILURE")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def _mapback_metrics(stage06_root: Path, stage07_paths: Sequence[Path]) -> dict[str, int]:
    row_paths = _stage06_artifact_paths(stage06_root, kind="row_map")
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("SET threads=1")
        row = connection.execute(
            f"""
            WITH row_map AS (
              SELECT {ROW_MAP_ID_COLUMNS[0]} AS candidate_id, 'STANDARD' AS representation
              FROM read_parquet(?) WHERE {ROW_MAP_ID_COLUMNS[0]} IS NOT NULL
              UNION ALL
              SELECT {ROW_MAP_ID_COLUMNS[1]} AS candidate_id, 'NATIVE' AS representation
              FROM read_parquet(?) WHERE {ROW_MAP_ID_COLUMNS[1]} IS NOT NULL
            ), registry AS (
              SELECT {REGISTRY_COLUMNS[0]} AS candidate_id, count(*) AS copies
              FROM read_parquet(?) GROUP BY 1
            )
            SELECT count(*),
                   count(*) FILTER (WHERE representation = 'STANDARD'),
                   count(*) FILTER (WHERE representation = 'NATIVE'),
                   count(*) FILTER (WHERE registry.candidate_id IS NULL),
                   count(*) FILTER (WHERE copies != 1)
            FROM row_map LEFT JOIN registry USING (candidate_id)
            """,
            ([str(path) for path in row_paths], [str(path) for path in row_paths], [str(path) for path in stage07_paths]),
        ).fetchone()
    except duckdb.Error as error:
        raise Stage07ValidationError(
            "MAP_BACK_VALIDATION_FAILURE", "Occurrence map-back query failed"
        ) from error
    finally:
        connection.close()
    if row is None:
        _fail("MAP_BACK_VALIDATION_FAILURE", "Occurrence map-back result is absent")
    return {
        "TOTAL_OCCURRENCES": int(row[0]),
        "STANDARD_OCCURRENCES": int(row[1]),
        "NATIVE_OCCURRENCES": int(row[2]),
        "MISSING_STAGE07_ROWS": int(row[3]),
        "NON_UNIQUE_STAGE07_ROWS": int(row[4]),
    }


def validate_stage07_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    stage05_output_directory: Path,
    stage06_output_directory: Path,
    parser_bundle_directory: Path,
    authoritative_development: bool = True,
    batch_rows: int = 64,
    target_batch_bytes: int = 128 * 1024 * 1024,
) -> Stage07MaterializationOutcome:
    """Independently reopen accepted Stage 6 and every Stage 7 candidate row."""
    _validate_runtime()
    _digest(expected_manifest_sha256)
    _reject_holdout_paths(
        output_directory,
        stage05_output_directory,
        stage06_output_directory,
        parser_bundle_directory,
    )
    _require_directory(output_directory, "STAGE07_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    manifest_path = output_directory / STAGE07_MANIFEST_NAME
    success_path = output_directory / STAGE07_SUCCESS_MARKER
    _require_file(manifest_path, "STAGE07_TERMINAL_MISSING")
    _require_file(success_path, "STAGE07_TERMINAL_MISSING")
    manifest_sha = _sha256_file(manifest_path)
    if manifest_sha != expected_manifest_sha256:
        _fail("STAGE07_MANIFEST_SHA256_MISMATCH", "Stage 7 manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE07_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE07_SUCCESS_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 identity is malformed")
    binding_raw = scientific.get("stage06_binding")
    if not isinstance(binding_raw, dict):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 binding is absent")
    input_binding_sha = scientific.get("stage07_input_binding_sha256")
    if not isinstance(input_binding_sha, str):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 input binding SHA is absent")
    kwargs = {
        key: binding_raw[key] for key in Stage07InputBinding.__dataclass_fields__ if key in binding_raw
    }
    try:
        binding = Stage07InputBinding(**kwargs)
    except (TypeError, KeyError) as error:
        raise Stage07ValidationError(
            "STAGE07_MANIFEST_INVALID", "Stage 7 binding fields differ"
        ) from error
    validate_stage07_input_binding(
        binding, authoritative_development=authoritative_development
    )
    _validate_bundle_identity(binding, parser_bundle_directory)
    stage06 = validate_stage06_bundle(
        stage06_output_directory,
        expected_manifest_sha256=binding.stage06_manifest_sha256,
        stage05_output_directory=stage05_output_directory,
        authoritative_development=authoritative_development,
        batch_rows=batch_rows,
        target_batch_bytes=target_batch_bytes,
    )
    if (
        stage06.logical_dataset_sha256_v1 != binding.stage06_logical_fingerprint
        or stage06.schema_fingerprint != binding.stage06_schema_fingerprint
        or stage06.input_binding_sha256 != binding.stage06_input_binding_sha256
        or stage06.ordered_identity_sha256 != binding.stage06_ordered_identity_sha256
        or stage06.unique_candidate_count != binding.stage06_registry_rows
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Stage 6 independent identity differs")
    contract_fingerprint = stage07_contract_fingerprint(binding)
    if (
        manifest.get("stage07_manifest_version") != STAGE07_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status") != "STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("stage07_manifest_sha256") != manifest_sha
        or scientific.get("stage07_contract_version") != STAGE07_CONTRACT_VERSION
        or scientific.get("stage07_profile_version") != STAGE07_PROFILE_VERSION
        or scientific.get("stage07_schema_version") != STAGE07_SCHEMA_VERSION
        or scientific.get("stage07_schema_fingerprint") != stage07_schema_fingerprint()
        or scientific.get("stage07_contract_fingerprint") != contract_fingerprint
        or scientific.get("exact_parser_input_field") != STAGE07_EXACT_INPUT_FIELD
        or scientific.get("status_vocabulary") != list(STAGE07_STATUS_VOCABULARY)
        or scientific.get("parser_process_crash_is_v1_status") is not False
        or scientific.get("components_type") != str(component_list_field().type)
        or not isinstance(validation, dict)
        or validation.get("validation_contract_version") != STAGE07_VALIDATION_VERSION
        or any(value != "PASS" for key, value in validation.items() if key != "validation_contract_version")
    ):
        _fail("STAGE07_FINGERPRINT_MISMATCH", "Stage 7 scientific identity differs")
    artifacts = _manifest_artifacts(output_directory, physical)
    expected_directories = {"registry", STAGE07_REGISTRY_DIRECTORY}
    expected_files = {
        STAGE07_MANIFEST_NAME,
        STAGE07_SUCCESS_MARKER,
        *(artifact.relative_path for artifact in artifacts),
    }
    directories, files = _topology(output_directory)
    if directories != expected_directories or files != expected_files:
        _fail("STAGE07_ARTIFACT_MISMATCH", "Stage 7 topology differs")
    bounded = physical.get("bounded_memory_architecture")
    if (
        physical.get("owner_only_permissions") is not True
        or physical.get("atomic_publication") is not True
        or not isinstance(bounded, dict)
        or bounded.get("one_candidate_result_at_a_time") is not True
        or bounded.get("bounded_arrow_batches") is not True
        or bounded.get("disk_backed_row_metrics") is not True
        or bounded.get("population_sized_python_registry") is not False
        or bounded.get("population_sized_python_result_list") is not False
    ):
        _fail("BOUNDED_MEMORY_CONTRACT_MISMATCH", "Stage 7 memory contract differs")
    expected_schema = stage07_schema().with_metadata(_metadata(binding, contract_fingerprint))
    output_paths = tuple(output_directory / artifact.relative_path for artifact in artifacts)
    for path in output_paths:
        if not pq.ParquetFile(path, page_checksum_verification=True).schema_arrow.equals(
            expected_schema, check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 7 output schema differs")
    input_paths = _stage06_artifact_paths(stage06_output_directory, kind="registry")
    input_rows = (
        (batch, index)
        for batch in _iter_batches(input_paths, REGISTRY_COLUMNS, batch_rows)
        for index in range(batch.num_rows)
    )
    output_rows = (
        (batch, index)
        for batch in _iter_batches(output_paths, tuple(expected_schema.names), batch_rows)
        for index in range(batch.num_rows)
    )
    logical = _LogicalHasher(contract_fingerprint)
    temp_metrics = output_directory.parent / f".{output_directory.name}.{os.getpid()}.validation_metrics.sqlite"
    if temp_metrics.exists() or temp_metrics.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 validation metrics path exists")
    metrics = _MetricsAccumulator(temp_metrics)
    scripts = _script_reference()
    rows = 0
    previous_id: bytes | None = None
    try:
        while True:
            try:
                input_batch, input_index = next(input_rows)
            except StopIteration:
                try:
                    next(output_rows)
                except StopIteration:
                    break
                _fail("OUTPUT_ROW_MISMATCH", "Stage 7 contains added rows")
            try:
                output_batch, output_index = next(output_rows)
            except StopIteration:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 7 dropped rows")
            for column_index in range(len(REGISTRY_COLUMNS)):
                if input_batch.column(column_index)[input_index] != output_batch.column(column_index)[output_index]:
                    _fail("UPSTREAM_VALUE_MISMATCH", "Stage 7 changed a Stage 6 field")
            candidate_id = output_batch.column(0)[output_index].as_py()
            candidate = output_batch.column(1)[output_index].as_py()
            counts = tuple(
                int(output_batch.column(index)[output_index].as_py()) for index in range(2, 5)
            )
            status = output_batch.column(5)[output_index].as_py()
            raw_components = output_batch.column(6)[output_index].as_py()
            if (
                not isinstance(candidate_id, bytes)
                or not isinstance(candidate, str)
                or not isinstance(status, str)
                or not isinstance(raw_components, list)
                or status not in STAGE07_STATUS_VOCABULARY
            ):
                _fail("OUTPUT_STRUCTURE_INVALID", "Stage 7 row structure differs")
            components: list[LibpostalComponent] = []
            for item in raw_components:
                if not isinstance(item, dict) or set(item) != {"label", "value"} or not isinstance(item["label"], str) or not isinstance(item["value"], str):
                    _fail("OUTPUT_STRUCTURE_INVALID", "Stage 7 component differs")
                components.append(LibpostalComponent(label=item["label"], value=item["value"]))
            component_tuple = tuple(components)
            if (status == PARSED_NONEMPTY) != bool(component_tuple):
                _fail("PARSER_STATUS_COMPONENT_MISMATCH", "Stage 7 status/list differs")
            if previous_id is not None and candidate_id <= previous_id:
                _fail("REGISTRY_ORDER_MISMATCH", "Stage 7 candidate order differs")
            previous_id = candidate_id
            logical.update(candidate_id, candidate, counts, status, component_tuple)
            nested = one_component_list_array(component_tuple)
            metrics.add(
                candidate=candidate,
                occurrence_count=counts[0],
                standard_count=counts[1],
                native_count=counts[2],
                status=status,
                components=component_tuple,
                nested_arrow_bytes=nested.nbytes,
                scripts=scripts,
            )
            rows += 1
        observed_metrics = metrics.finish()
    finally:
        metrics.close()
        if temp_metrics.exists():
            temp_metrics.unlink()
    registry_logical = logical.hexdigest()
    dataset_logical = stage07_logical_dataset_sha256(contract_fingerprint, registry_logical, rows)
    recorded_metrics = manifest.get("development_metrics")
    if not isinstance(recorded_metrics, dict):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 metrics are absent")
    for key, value in observed_metrics.items():
        if recorded_metrics.get(key) != value:
            _fail("STAGE07_METRIC_MISMATCH", "Stage 7 structural metrics differ")
    mapback = _mapback_metrics(stage06_output_directory, output_paths)
    if mapback != {
        "TOTAL_OCCURRENCES": binding.stage06_occurrences,
        "STANDARD_OCCURRENCES": binding.stage06_standard_occurrences,
        "NATIVE_OCCURRENCES": binding.stage06_native_occurrences,
        "MISSING_STAGE07_ROWS": 0,
        "NON_UNIQUE_STAGE07_ROWS": 0,
    }:
        _fail("MAP_BACK_INTEGRITY_FAILURE", "Stage 7 occurrence map-back differs")
    if (
        rows != binding.stage06_registry_rows
        or scientific.get("candidate_count") != rows
        or scientific.get("stage07_registry_logical_sha256_v1") != registry_logical
        or scientific.get("stage07_logical_dataset_sha256_v1") != dataset_logical
        or success.get("stage07_logical_dataset_sha256_v1") != dataset_logical
        or success.get("stage07_schema_fingerprint") != stage07_schema_fingerprint()
        or success.get("stage07_input_binding_sha256") != input_binding_sha
        or success.get("candidate_count") != rows
        or success.get("shard_count") != len(artifacts)
        or sum(artifact.row_count for artifact in artifacts) != rows
        or recorded_metrics.get("INPUT_OCCURRENCES") != binding.stage06_occurrences
        or recorded_metrics.get("STANDARD_OCCURRENCES") != binding.stage06_standard_occurrences
        or recorded_metrics.get("NATIVE_OCCURRENCES") != binding.stage06_native_occurrences
    ):
        _fail("STAGE07_FINGERPRINT_MISMATCH", "Stage 7 reconciliation differs")
    performance = manifest.get("performance")
    if not isinstance(performance, dict):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 performance is absent")
    return Stage07MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=dataset_logical,
        registry_logical_sha256_v1=registry_logical,
        schema_fingerprint=stage07_schema_fingerprint(),
        contract_fingerprint=contract_fingerprint,
        input_binding_sha256=input_binding_sha,
        manifest_sha256=manifest_sha,
        candidate_count=rows,
        shard_count=len(artifacts),
        metrics={**recorded_metrics, "MAP_BACK": mapback},
        performance=cast(Mapping[str, int | float | str], performance),
    )


__all__ = [
    "ACCEPTED_PARSER_BUNDLE_FINGERPRINT",
    "ACCEPTED_STAGE06_LOGICAL_FINGERPRINT",
    "ACCEPTED_STAGE06_MANIFEST_SHA256",
    "ACCEPTED_STAGE06_REGISTRY_ROWS",
    "STAGE07_CONTRACT_VERSION",
    "STAGE07_MANIFEST_NAME",
    "STAGE07_PROFILE_VERSION",
    "STAGE07_STATUS_VOCABULARY",
    "Stage07InputBinding",
    "Stage07MaterializationOutcome",
    "Stage07RunConfig",
    "Stage07ValidationError",
    "accepted_stage07_input_binding",
    "load_stage07_input_binding",
    "materialize_stage07",
    "stage07_contract_fingerprint",
    "stage07_logical_dataset_sha256",
    "stage07_schema",
    "stage07_schema_fingerprint",
    "validate_stage07_bundle",
    "validate_stage07_input_binding",
    "write_stage07_input_binding",
]

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
import struct
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path, PurePosixPath
from typing import Any, Literal, NoReturn, cast

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s01_constants import (
    PARSER_VERSION,
    SOURCE_SCHEMA_VERSION,
    STAGING_VERSION,
)
from .s01_identity import stable_source_row_id_v1
from .s01_schema import base_staging_schema, schema_fingerprint
from ...raw_csv import SOURCE_COLUMNS
from ..benchmark_runner import (
    BENCHMARK_OUTPUT_SCHEMA_VERSION,
    benchmark_schema,
    benchmark_schema_fingerprint,
)
from ..benchmark_sample import BENCHMARK_CONTRACT_VERSION, FEATURE_CONTRACT_VERSION
from .s01_ingestion import STAGE01_CONTRACT_VERSION

STAGE02_CONTRACT_VERSION = "stage02_schema_provenance_harmonization_contract_v1"
STAGE02_INPUT_BINDING_VERSION = "stage02_input_binding_v1"
STAGE02_SCHEMA_VERSION = "stage02_canonical_source_row_schema_v1"
STAGE02_STRUCTURAL_METADATA_VERSION = "stage02_raw_representation_structure_v1"
STAGE02_VALIDATION_VERSION = "stage02_bundle_validation_v1"
STAGE02_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE02_LOGICAL_DATASET_V1"
STAGE02_REPRESENTATION_SOURCE_SYSTEM = "ORBIS"
STAGE02_REPRESENTATION_RELATIONSHIP = "ALTERNATIVE_SOURCE_REPRESENTATIONS"

STAGE02_MANIFEST_NAME = "stage02_manifest.json"
STAGE02_SUCCESS_MARKER = "_SUCCESS.json"
STAGE02_IN_PROGRESS_MARKER = "_IN_PROGRESS"

STANDARD_ADDRESS_COLUMNS = tuple(
    f"street_address_line_{index}" for index in range(1, 5)
)
NATIVE_ADDRESS_COLUMNS = tuple(
    f"street_address_line_{index}_native" for index in range(1, 5)
)
STAGE02_STRUCTURAL_COLUMNS = (
    "standard_has_nonempty_source_line",
    "native_has_nonempty_source_line",
    "standard_nonempty_source_line_count",
    "native_nonempty_source_line_count",
)

Stage02InputKind = Literal["STAGE01", "BENCHMARK_DEVELOPMENT"]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"
_OPERATIONAL_METADATA_KEYS = frozenset({"execution_site", "slurm_job_id"})


class Stage02ValidationError(RuntimeError):
    """Privacy-safe, fail-closed Stage 2 validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage02InputArtifact:
    sequence_number: int
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class Stage02InputBinding:
    input_kind: Stage02InputKind
    upstream_contract_version: str
    upstream_logical_identity_sha256: str
    source_population_identity_sha256: str
    input_schema_fingerprint: str
    expected_row_count: int
    artifacts: tuple[Stage02InputArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage02_input_binding_version": STAGE02_INPUT_BINDING_VERSION,
            "input_kind": self.input_kind,
            "upstream_contract_version": self.upstream_contract_version,
            "upstream_logical_identity_sha256": (self.upstream_logical_identity_sha256),
            "source_population_identity_sha256": (
                self.source_population_identity_sha256
            ),
            "input_schema_fingerprint": self.input_schema_fingerprint,
            "expected_row_count": self.expected_row_count,
            "artifacts": [asdict(item) for item in self.artifacts],
        }


@dataclass(frozen=True, slots=True)
class Stage02RunConfig:
    input_root: Path
    input_binding_file: Path
    expected_input_binding_sha256: str
    output_directory: Path
    adopting_git_commit: str
    production: bool = True
    batch_rows: int = 4_096
    operational_metadata: dict[str, str] | None = None

    def validate(self) -> None:
        _digest_bytes(self.expected_input_binding_sha256)
        if _GIT_SHA_RE.fullmatch(self.adopting_git_commit) is None:
            _fail("INVALID_GIT_COMMIT", "Adopting Git commit must be a full SHA")
        if isinstance(self.batch_rows, bool) or self.batch_rows < 1:
            _fail("INVALID_BATCH_SIZE", "Batch row count must be positive")
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in _OPERATIONAL_METADATA_KEYS
                or not isinstance(value, str)
                or "\x00" in value
                or len(value) > 128
            ):
                _fail(
                    "INVALID_OPERATIONAL_METADATA",
                    "Operational metadata is outside the privacy-safe contract",
                )


@dataclass(frozen=True, slots=True)
class Stage02ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Stage02MaterializationOutcome:
    output_directory: Path
    logical_dataset_sha256_v1: str
    manifest_sha256: str
    row_count: int
    source_file_count: int
    output_shard_count: int


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    mode: int


@dataclass(slots=True)
class _ProvenanceState:
    input_kind: Stage02InputKind
    previous_key: tuple[str, int] | None = None
    source_hash_by_path: dict[str, bytes] | None = None
    path_by_source_hash: dict[bytes, str] | None = None
    row_count: int = 0

    def __post_init__(self) -> None:
        self.source_hash_by_path = {}
        self.path_by_source_hash = {}


class _CanonicalEncoder:
    def __init__(self, digest: Any) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
            _fail("INVALID_UNSIGNED_INTEGER", "Value does not fit uint64")
        self._digest.update(_TYPE_UINT64)
        self._digest.update(struct.pack(">Q", value))

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            _fail("INVALID_TEXT", "Canonical text is malformed")
        encoded = value.encode("utf-8", errors="strict")
        self._digest.update(_TYPE_TEXT)
        self._digest.update(struct.pack(">Q", len(encoded)))
        self._digest.update(encoded)

    def digest(self, value: str) -> None:
        self._digest.update(_TYPE_DIGEST)
        self._digest.update(_digest_bytes(value))


def _fail(code: str, message: str) -> NoReturn:
    raise Stage02ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be lowercase canonical SHA-256 text")
    return bytes.fromhex(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stage02_schema() -> pa.Schema:
    fields = list(base_staging_schema())
    fields.extend(
        (
            pa.field(STAGE02_STRUCTURAL_COLUMNS[0], pa.bool_(), nullable=False),
            pa.field(STAGE02_STRUCTURAL_COLUMNS[1], pa.bool_(), nullable=False),
            pa.field(STAGE02_STRUCTURAL_COLUMNS[2], pa.uint8(), nullable=False),
            pa.field(STAGE02_STRUCTURAL_COLUMNS[3], pa.uint8(), nullable=False),
        )
    )
    return pa.schema(fields)


def _fingerprint_schema(schema: pa.Schema) -> str:
    digest = hashlib.sha256(b"SAFE_STAGE02_ARROW_SCHEMA_V1")
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE02_SCHEMA_VERSION)
    encoder.uint64(len(schema))
    for field in schema:
        encoder.text(field.name)
        encoder.text(str(field.type))
        encoder.text(str(field.nullable).lower())
    return digest.hexdigest()


def stage02_schema_fingerprint() -> str:
    return _fingerprint_schema(stage02_schema())


def _expected_input_contract(input_kind: Stage02InputKind) -> tuple[str, str]:
    if input_kind == "STAGE01":
        return STAGE01_CONTRACT_VERSION, schema_fingerprint()
    if input_kind == "BENCHMARK_DEVELOPMENT":
        return BENCHMARK_CONTRACT_VERSION, benchmark_schema_fingerprint()
    _fail("INVALID_INPUT_KIND", "Stage 2 input kind is unsupported")


def _canonical_relative_parquet_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or value == "" or "\x00" in value:
        _fail("INVALID_ARTIFACT_PATH", "Input artifact path is malformed")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() != ".parquet"
        or path.as_posix() != value
    ):
        _fail("INVALID_ARTIFACT_PATH", "Input artifact path is not canonical")
    return path


def validate_stage02_input_binding(binding: Stage02InputBinding) -> None:
    expected_contract, expected_schema = _expected_input_contract(binding.input_kind)
    if binding.upstream_contract_version != expected_contract:
        _fail("UPSTREAM_CONTRACT_MISMATCH", "Upstream contract version is not accepted")
    if binding.input_schema_fingerprint != expected_schema:
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Upstream schema fingerprint is not accepted")
    _digest_bytes(binding.upstream_logical_identity_sha256)
    _digest_bytes(binding.source_population_identity_sha256)
    _digest_bytes(binding.input_schema_fingerprint)
    if (
        isinstance(binding.expected_row_count, bool)
        or binding.expected_row_count < 1
        or binding.expected_row_count > 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail("INVALID_ROW_COUNT", "Expected Stage 2 row count is invalid")
    if not binding.artifacts:
        _fail("EMPTY_INPUT_BUNDLE", "Stage 2 requires at least one input artifact")
    seen: set[str] = set()
    for expected_sequence, artifact in enumerate(binding.artifacts, start=1):
        if artifact.sequence_number != expected_sequence:
            _fail("NONCANONICAL_ARTIFACT_ORDER", "Input artifact order is malformed")
        path = _canonical_relative_parquet_path(artifact.relative_path)
        if artifact.relative_path in seen:
            _fail("DUPLICATE_ARTIFACT_PATH", "Input artifact path is duplicated")
        seen.add(artifact.relative_path)
        if (
            isinstance(artifact.size_bytes, bool)
            or artifact.size_bytes < 1
            or artifact.size_bytes > 0xFFFF_FFFF_FFFF_FFFF
        ):
            _fail("INVALID_ARTIFACT_SIZE", "Input artifact size is invalid")
        _digest_bytes(artifact.sha256)
        if binding.input_kind == "BENCHMARK_DEVELOPMENT" and any(
            part.casefold() == "holdout" for part in path.parts
        ):
            _fail(
                "HOLDOUT_ACCESS_PROHIBITED", "Stage 2 DEVELOPMENT input names HOLDOUT"
            )


def stage02_logical_dataset_sha256_v1(binding: Stage02InputBinding) -> str:
    """Identify Stage 2 science independently of physical input/output layout."""
    validate_stage02_input_binding(binding)
    digest = hashlib.sha256(STAGE02_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE02_CONTRACT_VERSION)
    encoder.text(STAGE02_SCHEMA_VERSION)
    encoder.text(STAGE02_STRUCTURAL_METADATA_VERSION)
    encoder.text(STAGE02_REPRESENTATION_SOURCE_SYSTEM)
    encoder.text(STAGE02_REPRESENTATION_RELATIONSHIP)
    encoder.text(binding.input_kind)
    encoder.text(binding.upstream_contract_version)
    encoder.digest(binding.upstream_logical_identity_sha256)
    encoder.digest(binding.source_population_identity_sha256)
    encoder.digest(binding.input_schema_fingerprint)
    encoder.digest(stage02_schema_fingerprint())
    encoder.uint64(binding.expected_row_count)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise Stage02ValidationError(
            "CONTROLLED_WRITE_FAILURE", "Controlled JSON could not be written"
        ) from error


def write_stage02_input_binding(path: Path, binding: Stage02InputBinding) -> str:
    validate_stage02_input_binding(binding)
    if path.is_symlink() or path.exists():
        _fail("OUTPUT_COLLISION", "Stage 2 input-binding path already exists")
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as error:
        raise Stage02ValidationError(
            "PERMISSION_FAILURE", "Input-binding directory could not be protected"
        ) from error
    _require_directory(path.parent, "INPUT_BINDING_INVALID")
    try:
        path.parent.chmod(0o700)
    except OSError as error:
        raise Stage02ValidationError(
            "PERMISSION_FAILURE", "Input-binding directory could not be protected"
        ) from error
    _require_mode(path.parent, 0o700, "PERMISSION_FAILURE")
    _write_json_exclusive(path, binding.to_dict())
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return _sha256_file(path)


def _load_json(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage02ValidationError(code, "Controlled JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON is not an object")
    return cast(dict[str, Any], value)


def _required_text(value: object, code: str) -> str:
    if not isinstance(value, str) or value == "" or "\x00" in value:
        _fail(code, "Required text is malformed")
    return value


def _required_uint(value: object, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail(code, "Required integer is outside uint64")
    return value


def load_stage02_input_binding(
    path: Path, *, expected_sha256: str
) -> Stage02InputBinding:
    _digest_bytes(expected_sha256)
    _require_directory(path.parent, "INPUT_BINDING_INVALID")
    _require_mode(path.parent, 0o700, "PERMISSION_FAILURE")
    _require_regular_file(path, "INPUT_BINDING_INVALID")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(path) != expected_sha256:
        _fail("INPUT_BINDING_SHA256_MISMATCH", "Input-binding SHA-256 differs")
    value = _load_json(path, "INPUT_BINDING_INVALID")
    if value.get("stage02_input_binding_version") != STAGE02_INPUT_BINDING_VERSION:
        _fail("INPUT_BINDING_VERSION_MISMATCH", "Input-binding version is unknown")
    raw_kind = _required_text(value.get("input_kind"), "INPUT_BINDING_INVALID")
    if raw_kind not in {"STAGE01", "BENCHMARK_DEVELOPMENT"}:
        _fail("INVALID_INPUT_KIND", "Stage 2 input kind is unsupported")
    artifacts_value = value.get("artifacts")
    if not isinstance(artifacts_value, list):
        _fail("INPUT_BINDING_INVALID", "Input artifact inventory is malformed")
    artifacts: list[Stage02InputArtifact] = []
    for raw in artifacts_value:
        if not isinstance(raw, dict):
            _fail("INPUT_BINDING_INVALID", "Input artifact identity is malformed")
        artifacts.append(
            Stage02InputArtifact(
                sequence_number=_required_uint(
                    raw.get("sequence_number"), "INPUT_BINDING_INVALID"
                ),
                relative_path=_required_text(
                    raw.get("relative_path"), "INPUT_BINDING_INVALID"
                ),
                size_bytes=_required_uint(
                    raw.get("size_bytes"), "INPUT_BINDING_INVALID"
                ),
                sha256=_required_text(raw.get("sha256"), "INPUT_BINDING_INVALID"),
            )
        )
    binding = Stage02InputBinding(
        input_kind=cast(Stage02InputKind, raw_kind),
        upstream_contract_version=_required_text(
            value.get("upstream_contract_version"), "INPUT_BINDING_INVALID"
        ),
        upstream_logical_identity_sha256=_required_text(
            value.get("upstream_logical_identity_sha256"), "INPUT_BINDING_INVALID"
        ),
        source_population_identity_sha256=_required_text(
            value.get("source_population_identity_sha256"), "INPUT_BINDING_INVALID"
        ),
        input_schema_fingerprint=_required_text(
            value.get("input_schema_fingerprint"), "INPUT_BINDING_INVALID"
        ),
        expected_row_count=_required_uint(
            value.get("expected_row_count"), "INPUT_BINDING_INVALID"
        ),
        artifacts=tuple(artifacts),
    )
    validate_stage02_input_binding(binding)
    return binding


def _require_regular_file(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage02ValidationError(
            code, "Required artifact is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISREG(observed.st_mode):
        _fail(code, "Required artifact is not a regular non-symlink file")


def _require_directory(path: Path, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage02ValidationError(
            code, "Required directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(observed.st_mode):
        _fail(code, "Required directory is not a regular non-symlink directory")


def _require_mode(path: Path, expected: int, code: str) -> None:
    try:
        observed = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage02ValidationError(
            code, "Protected path mode could not be read"
        ) from error
    if stat.S_IMODE(observed.st_mode) != expected:
        _fail(code, "Protected path is not owner-only")


def _snapshot(path: Path) -> _FileSnapshot:
    _require_regular_file(path, "UNSAFE_INPUT_ARTIFACT")
    observed = path.stat(follow_symlinks=False)
    return _FileSnapshot(
        device=observed.st_dev,
        inode=observed.st_ino,
        size_bytes=observed.st_size,
        mtime_ns=observed.st_mtime_ns,
        mode=stat.S_IMODE(observed.st_mode),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage02ValidationError(
            "ARTIFACT_READ_FAILURE", "Controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _safe_artifact_path(root: Path, relative_path: str) -> Path:
    relative = _canonical_relative_parquet_path(relative_path)
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        if index < len(relative.parts) - 1:
            _require_directory(current, "UNSAFE_INPUT_ARTIFACT")
            _require_mode(current, 0o700, "PERMISSION_FAILURE")
        else:
            _require_regular_file(current, "UNSAFE_INPUT_ARTIFACT")
            _require_mode(current, 0o600, "PERMISSION_FAILURE")
    return current


def _validate_input_artifact(
    root: Path, artifact: Stage02InputArtifact
) -> tuple[Path, _FileSnapshot]:
    path = _safe_artifact_path(root, artifact.relative_path)
    before = _snapshot(path)
    if before.size_bytes != artifact.size_bytes:
        _fail("INPUT_ARTIFACT_SIZE_MISMATCH", "Input artifact byte size differs")
    if _sha256_file(path) != artifact.sha256:
        _fail("INPUT_ARTIFACT_SHA256_MISMATCH", "Input artifact SHA-256 differs")
    after = _snapshot(path)
    if before != after:
        _fail("INPUT_CHANGED", "Input artifact changed during validation")
    return path, after


def _input_schema(input_kind: Stage02InputKind) -> pa.Schema:
    if input_kind == "STAGE01":
        return base_staging_schema()
    return benchmark_schema()


def _metadata_text(metadata: dict[bytes, bytes], name: str) -> str | None:
    raw = metadata.get(name.encode("utf-8"))
    if raw is None:
        return None
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise Stage02ValidationError(
            "UPSTREAM_METADATA_INVALID", "Upstream metadata is not UTF-8"
        ) from error


def _validate_parquet_schema_and_metadata(
    parquet_file: pq.ParquetFile,
    *,
    binding: Stage02InputBinding,
) -> None:
    observed = parquet_file.schema_arrow
    if not observed.remove_metadata().equals(
        _input_schema(binding.input_kind), check_metadata=False
    ):
        _fail("UPSTREAM_SCHEMA_MISMATCH", "Input Parquet schema is not exact")
    metadata = observed.metadata or {}
    if binding.input_kind == "STAGE01":
        required = {
            "source_schema_version": SOURCE_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "staging_version": STAGING_VERSION,
        }
    else:
        required = {
            "benchmark_contract_version": BENCHMARK_CONTRACT_VERSION,
            "benchmark_fingerprint": binding.upstream_logical_identity_sha256,
            "benchmark_schema_version": BENCHMARK_OUTPUT_SCHEMA_VERSION,
            "benchmark_feature_contract_version": FEATURE_CONTRACT_VERSION,
        }
    for name, expected in required.items():
        if _metadata_text(metadata, name) != expected:
            _fail("UPSTREAM_METADATA_MISMATCH", "Upstream metadata is inconsistent")


def _constant_string_array(value: str, length: int) -> pa.Array:
    return pa.array([value] * length, type=pa.string(), from_pandas=False, safe=True)


def _expected_stage02_row_versions(
    input_kind: Stage02InputKind,
) -> tuple[str, str, str]:
    return (
        SOURCE_SCHEMA_VERSION,
        PARSER_VERSION,
        STAGING_VERSION if input_kind == "STAGE01" else BENCHMARK_OUTPUT_SCHEMA_VERSION,
    )


def _representation_arrays(
    arrays_by_name: dict[str, pa.Array], columns: tuple[str, ...]
) -> tuple[pa.Array, pa.Array]:
    count = pa.array([0] * len(next(iter(arrays_by_name.values()))), type=pa.uint8())
    for column in columns:
        nonempty = pc.not_equal(arrays_by_name[column], pa.scalar("", pa.string()))
        count = cast(pa.Array, pc.add(count, pc.cast(nonempty, pa.uint8())))
    present = cast(pa.Array, pc.greater(count, pa.scalar(0, pa.uint8())))
    return present, count


def _project_batch(
    batch: pa.RecordBatch, *, input_kind: Stage02InputKind, metadata: dict[bytes, bytes]
) -> pa.RecordBatch:
    arrays_by_name = {
        name: batch.column(index) for index, name in enumerate(batch.schema.names)
    }
    required_input_columns = SOURCE_COLUMNS + (
        "source_file",
        "source_logical_record_number",
        "stable_source_row_id_v1",
        "source_file_sha256",
    )
    for name in required_input_columns:
        if arrays_by_name[name].null_count:
            _fail("UPSTREAM_NULL", "Stage 2 required input contains null values")
    arrays = [arrays_by_name[name] for name in required_input_columns]
    if input_kind == "STAGE01":
        for name, expected in (
            ("source_schema_version", SOURCE_SCHEMA_VERSION),
            ("parser_version", PARSER_VERSION),
            ("staging_version", STAGING_VERSION),
        ):
            values = arrays_by_name[name]
            if values.null_count or any(
                value != expected for value in values.to_pylist()
            ):
                _fail(
                    "UPSTREAM_VERSION_MISMATCH", "Stage 1 row version is inconsistent"
                )
            arrays.append(values)
    else:
        splits = arrays_by_name["benchmark_split"]
        if splits.null_count or any(
            value != "DEVELOPMENT" for value in splits.to_pylist()
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "Stage 2 input is not DEVELOPMENT-only")
        arrays.extend(
            _constant_string_array(value, batch.num_rows)
            for value in _expected_stage02_row_versions(input_kind)
        )
    standard_present, standard_count = _representation_arrays(
        arrays_by_name, STANDARD_ADDRESS_COLUMNS
    )
    native_present, native_count = _representation_arrays(
        arrays_by_name, NATIVE_ADDRESS_COLUMNS
    )
    arrays.extend((standard_present, native_present, standard_count, native_count))
    schema = stage02_schema().with_metadata(metadata)
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def _validate_provenance_batch(batch: pa.RecordBatch, state: _ProvenanceState) -> None:
    for name, expected in zip(
        ("source_schema_version", "parser_version", "staging_version"),
        _expected_stage02_row_versions(state.input_kind),
        strict=True,
    ):
        values = batch.column(batch.schema.get_field_index(name))
        if values.null_count or any(value != expected for value in values.to_pylist()):
            _fail("UPSTREAM_VERSION_MISMATCH", "Stage 2 row version is inconsistent")
    source_files = batch.column(batch.schema.get_field_index("source_file")).to_pylist()
    ordinals = batch.column(
        batch.schema.get_field_index("source_logical_record_number")
    ).to_pylist()
    stable_ids = batch.column(
        batch.schema.get_field_index("stable_source_row_id_v1")
    ).to_pylist()
    source_hashes = batch.column(
        batch.schema.get_field_index("source_file_sha256")
    ).to_pylist()
    assert state.source_hash_by_path is not None
    assert state.path_by_source_hash is not None
    for source_file, ordinal, stable_id, source_hash in zip(
        source_files, ordinals, stable_ids, source_hashes, strict=True
    ):
        if (
            not isinstance(source_file, str)
            or source_file == ""
            or not isinstance(ordinal, int)
            or not isinstance(stable_id, bytes)
            or not isinstance(source_hash, bytes)
            or len(source_hash) != 32
            or len(stable_id) != 32
        ):
            _fail("INVALID_PROVENANCE", "Stage 2 provenance value is malformed")
        key = (source_file, ordinal)
        if state.previous_key is not None and key <= state.previous_key:
            _fail("NONCANONICAL_ROW_ORDER", "Input provenance order is not canonical")
        if state.input_kind == "STAGE01":
            if state.previous_key is None or source_file != state.previous_key[0]:
                if ordinal != 1:
                    _fail(
                        "NONCONTIGUOUS_STAGE01_PROVENANCE",
                        "Stage 1 source ordinals must start at one",
                    )
            elif ordinal != state.previous_key[1] + 1:
                _fail(
                    "NONCONTIGUOUS_STAGE01_PROVENANCE",
                    "Stage 1 source ordinals must be contiguous",
                )
        state.previous_key = key
        known_hash = state.source_hash_by_path.get(source_file)
        if known_hash is not None and known_hash != source_hash:
            _fail("SOURCE_IDENTITY_MISMATCH", "Source path has inconsistent SHA-256")
        other_path = state.path_by_source_hash.get(source_hash)
        if other_path is not None and other_path != source_file:
            _fail("DUPLICATE_SOURCE_CONTENT", "Source SHA-256 maps to multiple paths")
        state.source_hash_by_path[source_file] = source_hash
        state.path_by_source_hash[source_hash] = source_file
        try:
            expected_stable_id = stable_source_row_id_v1(source_hash, ordinal)
        except ValueError as error:
            raise Stage02ValidationError(
                "INVALID_PROVENANCE", "Source logical record number is invalid"
            ) from error
        if stable_id != expected_stable_id:
            _fail("STABLE_SOURCE_ROW_ID_MISMATCH", "Stable source-row ID changed")
        state.row_count += 1


def _output_metadata(
    binding: Stage02InputBinding, logical_fingerprint: str
) -> dict[bytes, bytes]:
    return {
        key.encode("utf-8"): value.encode("utf-8")
        for key, value in {
            "stage02_contract_version": STAGE02_CONTRACT_VERSION,
            "stage02_schema_version": STAGE02_SCHEMA_VERSION,
            "stage02_schema_fingerprint": stage02_schema_fingerprint(),
            "stage02_structural_metadata_version": (
                STAGE02_STRUCTURAL_METADATA_VERSION
            ),
            "stage02_representation_source_system": (
                STAGE02_REPRESENTATION_SOURCE_SYSTEM
            ),
            "stage02_representation_relationship": (
                STAGE02_REPRESENTATION_RELATIONSHIP
            ),
            "stage02_logical_dataset_sha256_v1": logical_fingerprint,
            "upstream_input_kind": binding.input_kind,
            "upstream_contract_version": binding.upstream_contract_version,
            "upstream_logical_identity_sha256": (
                binding.upstream_logical_identity_sha256
            ),
            "source_population_identity_sha256": (
                binding.source_population_identity_sha256
            ),
        }.items()
    }


def _new_writer(path: Path, schema: pa.Schema) -> pq.ParquetWriter:
    try:
        writer = pq.ParquetWriter(
            path,
            schema,
            version="1.0",
            data_page_version="1.0",
            compression="zstd",
            compression_level=3,
            use_dictionary=[
                "source_schema_version",
                "parser_version",
                "staging_version",
            ],
            write_statistics=[
                "source_logical_record_number",
                *STAGE02_STRUCTURAL_COLUMNS,
            ],
            write_page_checksum=True,
            store_schema=True,
            use_compliant_nested_type=True,
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage02ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 2 Parquet writer could not start"
        ) from error
    path.chmod(0o600)
    return writer


def _iter_projected_batches(
    path: Path,
    *,
    binding: Stage02InputBinding,
    batch_rows: int,
    metadata: dict[bytes, bytes],
) -> tuple[pq.ParquetFile, Any]:
    try:
        parquet_file = pq.ParquetFile(path, page_checksum_verification=True)
    except (OSError, pa.ArrowException) as error:
        raise Stage02ValidationError(
            "PARQUET_READ_FAILURE", "Input Parquet could not be opened safely"
        ) from error
    _validate_parquet_schema_and_metadata(parquet_file, binding=binding)
    if binding.input_kind == "STAGE01":
        columns = list(base_staging_schema().names)
    else:
        columns = list(
            SOURCE_COLUMNS
            + (
                "source_file",
                "source_logical_record_number",
                "stable_source_row_id_v1",
                "source_file_sha256",
                "benchmark_split",
            )
        )
    try:
        batches = parquet_file.iter_batches(
            batch_size=batch_rows, columns=columns, use_threads=False
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage02ValidationError(
            "PARQUET_READ_FAILURE", "Input Parquet batch reader could not start"
        ) from error
    return parquet_file, (
        _project_batch(batch, input_kind=binding.input_kind, metadata=metadata)
        for batch in batches
    )


def _write_output_shard(
    input_path: Path,
    output_path: Path,
    *,
    binding: Stage02InputBinding,
    batch_rows: int,
    metadata: dict[bytes, bytes],
    provenance_state: _ProvenanceState,
) -> int:
    _parquet_file, batches = _iter_projected_batches(
        input_path, binding=binding, batch_rows=batch_rows, metadata=metadata
    )
    writer = _new_writer(output_path, stage02_schema().with_metadata(metadata))
    rows = 0
    try:
        for batch in batches:
            _validate_provenance_batch(batch, provenance_state)
            writer.write_batch(batch, row_group_size=batch.num_rows)
            rows += batch.num_rows
        writer.close()
    except Stage02ValidationError:
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
        raise Stage02ValidationError(
            "PARQUET_WRITE_FAILURE", "Stage 2 Parquet output could not be written"
        ) from error
    output_path.chmod(0o600)
    return rows


def _assert_input_output_equal(
    input_path: Path,
    output_path: Path,
    *,
    binding: Stage02InputBinding,
    batch_rows: int,
    metadata: dict[bytes, bytes],
) -> None:
    _input_file, expected_batches = _iter_projected_batches(
        input_path, binding=binding, batch_rows=batch_rows, metadata=metadata
    )
    try:
        output_file = pq.ParquetFile(output_path, page_checksum_verification=True)
        if not output_file.schema_arrow.equals(
            stage02_schema().with_metadata(metadata), check_metadata=True
        ):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 2 output schema is not exact")
        observed_batches = output_file.iter_batches(
            batch_size=batch_rows, use_threads=False
        )
        sentinel = object()
        for expected, observed in zip_longest(
            expected_batches, observed_batches, fillvalue=sentinel
        ):
            if expected is sentinel or observed is sentinel:
                _fail("OUTPUT_ROW_MISMATCH", "Stage 2 output batch count differs")
            assert isinstance(expected, pa.RecordBatch)
            assert isinstance(observed, pa.RecordBatch)
            if not expected.equals(observed, check_metadata=True):
                _fail(
                    "OUTPUT_VALUE_MISMATCH", "Stage 2 output values differ from input"
                )
    except Stage02ValidationError:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Stage02ValidationError(
            "PARQUET_READBACK_FAILURE", "Stage 2 read-back failed"
        ) from error


def _artifact_identity(
    path: Path, relative_path: str, row_count: int
) -> Stage02ArtifactIdentity:
    _require_regular_file(path, "MISSING_OUTPUT_ARTIFACT")
    _require_mode(path, 0o600, "PERMISSION_FAILURE")
    return Stage02ArtifactIdentity(
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


def materialize_stage02(config: Stage02RunConfig) -> Stage02MaterializationOutcome:
    """Harmonize an exact Stage 1 or benchmark DEVELOPMENT input bundle."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage02-schema-provenance-harmonization")
    if config.output_directory.is_symlink() or config.output_directory.exists():
        _fail("OUTPUT_COLLISION", "Stage 2 output directory already exists")
    _require_directory(config.input_root, "INPUT_ROOT_INVALID")
    _require_mode(config.input_root, 0o700, "PERMISSION_FAILURE")
    if any(part.casefold() == "holdout" for part in config.input_root.parts):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "Stage 2 input root names HOLDOUT")
    binding = load_stage02_input_binding(
        config.input_binding_file,
        expected_sha256=config.expected_input_binding_sha256,
    )
    logical_fingerprint = stage02_logical_dataset_sha256_v1(binding)
    input_artifacts: list[tuple[Stage02InputArtifact, Path, _FileSnapshot]] = []
    for artifact in binding.artifacts:
        input_path, snapshot = _validate_input_artifact(config.input_root, artifact)
        input_artifacts.append((artifact, input_path, snapshot))

    parent = config.output_directory.parent
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as error:
        raise Stage02ValidationError(
            "PERMISSION_FAILURE", "Stage 2 output parent could not be protected"
        ) from error
    _require_directory(parent, "STAGE02_OUTPUT_INVALID")
    try:
        parent.chmod(0o700)
    except OSError as error:
        raise Stage02ValidationError(
            "PERMISSION_FAILURE", "Stage 2 output parent could not be protected"
        ) from error
    _require_mode(parent, 0o700, "PERMISSION_FAILURE")
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.is_symlink() or temporary.exists():
        _fail("OUTPUT_COLLISION", "Stage 2 temporary output already exists")
    temporary.mkdir(mode=0o700)
    data_directory = temporary / "data"
    data_directory.mkdir(mode=0o700)
    _write_json_exclusive(
        temporary / STAGE02_IN_PROGRESS_MARKER,
        {"status": "STAGE02_INCOMPLETE"},
    )

    metadata = _output_metadata(binding, logical_fingerprint)
    provenance_state = _ProvenanceState(input_kind=binding.input_kind)
    output_artifacts: list[Stage02ArtifactIdentity] = []
    for artifact, input_path, before in input_artifacts:
        relative_output = f"data/part-{artifact.sequence_number:06d}.parquet"
        output_path = temporary / relative_output
        rows = _write_output_shard(
            input_path,
            output_path,
            binding=binding,
            batch_rows=config.batch_rows,
            metadata=metadata,
            provenance_state=provenance_state,
        )
        _assert_input_output_equal(
            input_path,
            output_path,
            binding=binding,
            batch_rows=config.batch_rows,
            metadata=metadata,
        )
        after = _snapshot(input_path)
        if before != after or _sha256_file(input_path) != artifact.sha256:
            _fail("INPUT_CHANGED", "Input artifact changed during Stage 2")
        output_artifacts.append(_artifact_identity(output_path, relative_output, rows))

    if provenance_state.row_count != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 2 row count differs from its input contract")
    source_file_count = len(provenance_state.source_hash_by_path or {})
    manifest = {
        "stage02_manifest_version": "stage02_manifest_v1",
        "status": "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION",
        "scientific_identity": {
            "stage02_contract_version": STAGE02_CONTRACT_VERSION,
            "stage02_schema_version": STAGE02_SCHEMA_VERSION,
            "stage02_schema_fingerprint": stage02_schema_fingerprint(),
            "stage02_structural_metadata_version": (
                STAGE02_STRUCTURAL_METADATA_VERSION
            ),
            "representation_source_system": STAGE02_REPRESENTATION_SOURCE_SYSTEM,
            "representation_relationship": STAGE02_REPRESENTATION_RELATIONSHIP,
            "stage02_logical_dataset_sha256_v1": logical_fingerprint,
            "input_kind": binding.input_kind,
            "upstream_contract_version": binding.upstream_contract_version,
            "upstream_logical_identity_sha256": (
                binding.upstream_logical_identity_sha256
            ),
            "source_population_identity_sha256": (
                binding.source_population_identity_sha256
            ),
            "input_schema_fingerprint": binding.input_schema_fingerprint,
            "row_count": provenance_state.row_count,
            "source_file_count": source_file_count,
        },
        "physical_identity": {
            "input_binding_sha256": config.expected_input_binding_sha256,
            "input_artifacts": [asdict(item) for item in binding.artifacts],
            "output_artifacts": [item.to_dict() for item in output_artifacts],
            "owner_only_permissions": True,
        },
        "validation": {
            "validation_contract_version": STAGE02_VALIDATION_VERSION,
            "upstream_identity_and_schema": "PASS",
            "input_artifact_integrity": "PASS",
            "row_count_preserved": "PASS",
            "stable_source_row_id_preserved": "PASS",
            "raw_source_values_preserved": "PASS",
            "standard_native_separation": "PASS",
            "structural_metadata_recomputed": "PASS",
            "parquet_page_checksum_readback": "PASS",
            "atomic_publication": "PASS",
        },
        "operational_provenance": {
            "adopting_git_commit": config.adopting_git_commit,
            "created_at_utc": _utc_now(),
            "python_version": platform.python_version(),
            "pyarrow_version": pa.__version__,
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json_exclusive(temporary / STAGE02_MANIFEST_NAME, manifest)
    manifest_identity = _artifact_identity(
        temporary / STAGE02_MANIFEST_NAME, STAGE02_MANIFEST_NAME, 0
    )
    success = {
        "status": "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION",
        "stage02_manifest_sha256": manifest_identity.sha256,
        "stage02_manifest_size_bytes": manifest_identity.size_bytes,
        "stage02_logical_dataset_sha256_v1": logical_fingerprint,
        "row_count": provenance_state.row_count,
        "output_shard_count": len(output_artifacts),
    }
    _write_json_exclusive(temporary / STAGE02_SUCCESS_MARKER, success)
    (temporary / STAGE02_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(data_directory)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    validate_stage02_bundle(
        config.output_directory, expected_manifest_sha256=manifest_identity.sha256
    )
    return Stage02MaterializationOutcome(
        output_directory=config.output_directory,
        logical_dataset_sha256_v1=logical_fingerprint,
        manifest_sha256=manifest_identity.sha256,
        row_count=provenance_state.row_count,
        source_file_count=source_file_count,
        output_shard_count=len(output_artifacts),
    )


def _observed_output_topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        for name in directory_names:
            path = current / name
            if path.is_symlink():
                _fail("UNSAFE_OUTPUT", "Stage 2 output contains a symlinked directory")
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current / name
            _require_regular_file(path, "UNSAFE_OUTPUT")
            files.add(path.relative_to(root).as_posix())
    return directories, files


def _binding_from_manifest(
    scientific: dict[str, Any], physical: dict[str, Any]
) -> Stage02InputBinding:
    raw_artifacts = physical.get("input_artifacts")
    if not isinstance(raw_artifacts, list):
        _fail("STAGE02_MANIFEST_INVALID", "Input artifact identity is missing")
    artifacts: list[Stage02InputArtifact] = []
    for raw in raw_artifacts:
        if not isinstance(raw, dict):
            _fail("STAGE02_MANIFEST_INVALID", "Input artifact identity is malformed")
        artifacts.append(
            Stage02InputArtifact(
                sequence_number=_required_uint(
                    raw.get("sequence_number"), "STAGE02_MANIFEST_INVALID"
                ),
                relative_path=_required_text(
                    raw.get("relative_path"), "STAGE02_MANIFEST_INVALID"
                ),
                size_bytes=_required_uint(
                    raw.get("size_bytes"), "STAGE02_MANIFEST_INVALID"
                ),
                sha256=_required_text(raw.get("sha256"), "STAGE02_MANIFEST_INVALID"),
            )
        )
    raw_kind = _required_text(scientific.get("input_kind"), "STAGE02_MANIFEST_INVALID")
    if raw_kind not in {"STAGE01", "BENCHMARK_DEVELOPMENT"}:
        _fail("STAGE02_MANIFEST_INVALID", "Input kind is invalid")
    return Stage02InputBinding(
        input_kind=cast(Stage02InputKind, raw_kind),
        upstream_contract_version=_required_text(
            scientific.get("upstream_contract_version"), "STAGE02_MANIFEST_INVALID"
        ),
        upstream_logical_identity_sha256=_required_text(
            scientific.get("upstream_logical_identity_sha256"),
            "STAGE02_MANIFEST_INVALID",
        ),
        source_population_identity_sha256=_required_text(
            scientific.get("source_population_identity_sha256"),
            "STAGE02_MANIFEST_INVALID",
        ),
        input_schema_fingerprint=_required_text(
            scientific.get("input_schema_fingerprint"), "STAGE02_MANIFEST_INVALID"
        ),
        expected_row_count=_required_uint(
            scientific.get("row_count"), "STAGE02_MANIFEST_INVALID"
        ),
        artifacts=tuple(artifacts),
    )


def validate_stage02_bundle(
    output_directory: Path, *, expected_manifest_sha256: str | None = None
) -> Stage02MaterializationOutcome:
    _require_directory(output_directory, "STAGE02_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    if (output_directory / STAGE02_IN_PROGRESS_MARKER).exists():
        _fail("STAGE02_INCOMPLETE", "Stage 2 output retains an in-progress marker")
    data_directory = output_directory / "data"
    _require_directory(data_directory, "STAGE02_OUTPUT_INVALID")
    _require_mode(data_directory, 0o700, "PERMISSION_FAILURE")
    directories, files = _observed_output_topology(output_directory)
    if directories != {"data"}:
        _fail("STAGE02_ARTIFACT_MISMATCH", "Stage 2 output directory set is invalid")
    manifest_path = output_directory / STAGE02_MANIFEST_NAME
    success_path = output_directory / STAGE02_SUCCESS_MARKER
    for path in (manifest_path, success_path):
        _require_regular_file(path, "STAGE02_TERMINAL_MISSING")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
    manifest = _load_json(manifest_path, "STAGE02_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE02_SUCCESS_INVALID")
    manifest_sha = _sha256_file(manifest_path)
    if expected_manifest_sha256 is not None:
        _digest_bytes(expected_manifest_sha256)
        if manifest_sha != expected_manifest_sha256:
            _fail("STAGE02_MANIFEST_SHA256_MISMATCH", "Stage 2 manifest SHA differs")
    if (
        manifest.get("stage02_manifest_version") != "stage02_manifest_v1"
        or manifest.get("status")
        != "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION"
        or success.get("status")
        != "STAGE_2_IMPLEMENTED_AWAITING_DEVELOPMENT_VALIDATION"
        or success.get("stage02_manifest_sha256") != manifest_sha
        or success.get("stage02_manifest_size_bytes") != manifest_path.stat().st_size
    ):
        _fail("STAGE02_TERMINAL_MISMATCH", "Stage 2 terminal state is inconsistent")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    if not isinstance(scientific, dict) or not isinstance(physical, dict):
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 identity is malformed")
    if physical.get("owner_only_permissions") is not True:
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 permission evidence is missing")
    _digest_bytes(
        _required_text(physical.get("input_binding_sha256"), "STAGE02_MANIFEST_INVALID")
    )
    if not isinstance(validation, dict) or any(
        value != "PASS"
        for key, value in validation.items()
        if key != "validation_contract_version"
    ):
        _fail(
            "STAGE02_VALIDATION_INCOMPLETE", "Stage 2 validation gates are incomplete"
        )
    if validation.get("validation_contract_version") != STAGE02_VALIDATION_VERSION:
        _fail("STAGE02_VALIDATION_INCOMPLETE", "Stage 2 validation version is unknown")
    binding = _binding_from_manifest(scientific, physical)
    logical_fingerprint = stage02_logical_dataset_sha256_v1(binding)
    if (
        scientific.get("stage02_contract_version") != STAGE02_CONTRACT_VERSION
        or scientific.get("stage02_schema_version") != STAGE02_SCHEMA_VERSION
        or scientific.get("stage02_schema_fingerprint") != stage02_schema_fingerprint()
        or scientific.get("stage02_structural_metadata_version")
        != STAGE02_STRUCTURAL_METADATA_VERSION
        or scientific.get("representation_source_system")
        != STAGE02_REPRESENTATION_SOURCE_SYSTEM
        or scientific.get("representation_relationship")
        != STAGE02_REPRESENTATION_RELATIONSHIP
        or scientific.get("stage02_logical_dataset_sha256_v1") != logical_fingerprint
        or success.get("stage02_logical_dataset_sha256_v1") != logical_fingerprint
    ):
        _fail("STAGE02_FINGERPRINT_MISMATCH", "Stage 2 scientific identity differs")
    output_values = physical.get("output_artifacts")
    if not isinstance(output_values, list) or not output_values:
        _fail("STAGE02_MANIFEST_INVALID", "Stage 2 output artifacts are missing")
    output_artifacts: list[Stage02ArtifactIdentity] = []
    expected_files = {STAGE02_MANIFEST_NAME, STAGE02_SUCCESS_MARKER}
    for expected_sequence, raw in enumerate(output_values, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE02_MANIFEST_INVALID", "Output artifact identity is malformed")
        expected_relative = f"data/part-{expected_sequence:06d}.parquet"
        relative_path = _required_text(
            raw.get("relative_path"), "STAGE02_MANIFEST_INVALID"
        )
        if relative_path != expected_relative:
            _fail("STAGE02_MANIFEST_INVALID", "Output artifact order is malformed")
        artifact = Stage02ArtifactIdentity(
            relative_path=relative_path,
            size_bytes=_required_uint(
                raw.get("size_bytes"), "STAGE02_MANIFEST_INVALID"
            ),
            sha256=_required_text(raw.get("sha256"), "STAGE02_MANIFEST_INVALID"),
            row_count=_required_uint(raw.get("row_count"), "STAGE02_MANIFEST_INVALID"),
        )
        _digest_bytes(artifact.sha256)
        output_artifacts.append(artifact)
        expected_files.add(relative_path)
    if files != expected_files:
        _fail("STAGE02_ARTIFACT_MISMATCH", "Stage 2 artifact set is incomplete")

    metadata = _output_metadata(binding, logical_fingerprint)
    provenance_state = _ProvenanceState(input_kind=binding.input_kind)
    for artifact in output_artifacts:
        path = output_directory / artifact.relative_path
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if path.stat(follow_symlinks=False).st_size != artifact.size_bytes:
            _fail("STAGE02_ARTIFACT_MISMATCH", "Stage 2 artifact size differs")
        if _sha256_file(path) != artifact.sha256:
            _fail("STAGE02_ARTIFACT_MISMATCH", "Stage 2 artifact SHA-256 differs")
        try:
            parquet_file = pq.ParquetFile(path, page_checksum_verification=True)
            if not parquet_file.schema_arrow.equals(
                stage02_schema().with_metadata(metadata), check_metadata=True
            ):
                _fail("OUTPUT_SCHEMA_MISMATCH", "Stage 2 output schema is not exact")
            observed_rows = 0
            for batch in parquet_file.iter_batches(batch_size=4_096, use_threads=False):
                _validate_provenance_batch(batch, provenance_state)
                arrays = {
                    name: batch.column(index)
                    for index, name in enumerate(batch.schema.names)
                }
                standard_present, standard_count = _representation_arrays(
                    arrays, STANDARD_ADDRESS_COLUMNS
                )
                native_present, native_count = _representation_arrays(
                    arrays, NATIVE_ADDRESS_COLUMNS
                )
                expected_structural = (
                    standard_present,
                    native_present,
                    standard_count,
                    native_count,
                )
                for name, expected in zip(
                    STAGE02_STRUCTURAL_COLUMNS, expected_structural, strict=True
                ):
                    if not arrays[name].equals(expected):
                        _fail(
                            "STRUCTURAL_METADATA_MISMATCH",
                            "Stage 2 structural metadata is inconsistent",
                        )
                observed_rows += batch.num_rows
            if observed_rows != artifact.row_count:
                _fail("ROW_COUNT_MISMATCH", "Stage 2 shard row count differs")
        except Stage02ValidationError:
            raise
        except (OSError, pa.ArrowException) as error:
            raise Stage02ValidationError(
                "PARQUET_READBACK_FAILURE", "Stage 2 page-checksum read-back failed"
            ) from error
    if provenance_state.row_count != binding.expected_row_count:
        _fail("ROW_COUNT_MISMATCH", "Stage 2 total row count differs")
    source_file_count = len(provenance_state.source_hash_by_path or {})
    if scientific.get("source_file_count") != source_file_count:
        _fail("SOURCE_COUNT_MISMATCH", "Stage 2 source-file count differs")
    if success.get("row_count") != provenance_state.row_count:
        _fail("STAGE02_TERMINAL_MISMATCH", "Stage 2 success row count differs")
    if success.get("output_shard_count") != len(output_artifacts):
        _fail("STAGE02_TERMINAL_MISMATCH", "Stage 2 success shard count differs")
    return Stage02MaterializationOutcome(
        output_directory=output_directory,
        logical_dataset_sha256_v1=logical_fingerprint,
        manifest_sha256=manifest_sha,
        row_count=provenance_state.row_count,
        source_file_count=source_file_count,
        output_shard_count=len(output_artifacts),
    )


__all__ = [
    "NATIVE_ADDRESS_COLUMNS",
    "STANDARD_ADDRESS_COLUMNS",
    "STAGE02_CONTRACT_VERSION",
    "STAGE02_INPUT_BINDING_VERSION",
    "STAGE02_LOGICAL_DATASET_DOMAIN",
    "STAGE02_MANIFEST_NAME",
    "STAGE02_REPRESENTATION_RELATIONSHIP",
    "STAGE02_REPRESENTATION_SOURCE_SYSTEM",
    "STAGE02_SCHEMA_VERSION",
    "STAGE02_STRUCTURAL_COLUMNS",
    "STAGE02_STRUCTURAL_METADATA_VERSION",
    "STAGE02_SUCCESS_MARKER",
    "Stage02InputArtifact",
    "Stage02InputBinding",
    "Stage02InputKind",
    "Stage02MaterializationOutcome",
    "Stage02RunConfig",
    "Stage02ValidationError",
    "load_stage02_input_binding",
    "materialize_stage02",
    "stage02_logical_dataset_sha256_v1",
    "stage02_schema",
    "stage02_schema_fingerprint",
    "validate_stage02_bundle",
    "validate_stage02_input_binding",
    "write_stage02_input_binding",
]

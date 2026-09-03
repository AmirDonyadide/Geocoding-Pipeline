from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import struct
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

import duckdb
import pyarrow
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s00_constants import INVENTORY_VERSION
from .s01_constants import (
    FILE_VALIDATION_COLUMNS,
    PARSER_VERSION,
    REPORT_NAMES,
    SEMANTIC_DIGEST_VERSION,
    SOURCE_SCHEMA_VERSION,
    STABLE_ROW_ID_VERSION,
    STAGING_VERSION,
)
from .s01_schema import (
    base_staging_schema,
    exact_schema_matches,
    schema_fingerprint,
)
from .s00_inventory import (
    STAGE00_CONTRACT_VERSION,
    ArtifactIdentity,
    ValidatedSourceInventoryBundle,
    validate_stage00_inventory,
)

STAGE01_CONTRACT_VERSION = "stage01_lossless_ingestion_contract_v1"
# Phase-prefixed values below are frozen identifiers at the accepted artifact
# boundary. All executable APIs and implementation names in this module use the
# authoritative Stage architecture.
STAGE01_VALIDATION_CONTRACT_VERSION = "stage01_phase02_bundle_validation_v1"
STAGE01_IMPLEMENTATION_STATUS = "STAGE_1_ACCEPTED"
STAGE01_LOGICAL_DATASET_DOMAIN = b"SAFE_STAGE01_LOGICAL_DATASET_V1"
STAGE01_ADOPTION_RECORD_NAME = "stage01_adoption.json"

INGESTION_MANIFEST_NAME = "dataset_manifest.json"
INGESTION_SUCCESS_MARKER = "_SUCCESS.json"
INGESTION_STATE_NAME = "_work/phase02_state.sqlite3"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FULL_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HISTORICAL_GIT_SHA_RE = re.compile(r"^[0-9a-f]{8,40}$")
_RUN_ID_RE = re.compile(r"^phase02_[0-9]{8}T[0-9]{6}Z_[A-Za-z0-9._-]+$")

_TYPE_UINT64 = b"\x01"
_TYPE_TEXT = b"\x02"
_TYPE_DIGEST = b"\x03"


class Stage01ValidationError(RuntimeError):
    """Fail-closed Stage 1 error that never includes protected row values."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage01SourceRecord:
    relative_path: str
    source_file_sha256: str
    logical_record_count: int
    raw_semantic_digest_v1: str


@dataclass(frozen=True, slots=True)
class Stage00Binding:
    adoption_record: ArtifactIdentity
    source_inventory_bundle: ValidatedSourceInventoryBundle
    source_inventory_manifest_sha256: str
    source_population_sha256_v1: str
    scientific_inventory_sha256_v1: str
    parser_contract_fingerprint: str


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    path: Path
    device: int
    inode: int
    size_bytes: int
    mtime_ns: int
    mode: int


@dataclass(frozen=True, slots=True)
class ValidatedStage01Bundle:
    run_directory: Path
    reports_directory: Path
    run_id: str
    producing_git_commit: str
    stage00: Stage00Binding
    sources: tuple[Stage01SourceRecord, ...]
    schema_fingerprint: str
    configuration_fingerprint: str
    implementation_fingerprint: str
    logical_dataset_sha256_v1: str
    source_file_count: int
    total_row_count: int
    total_parquet_bytes: int
    manifest: ArtifactIdentity
    success_marker: ArtifactIdentity
    state_store: ArtifactIdentity
    reports: tuple[ArtifactIdentity, ...]
    shards: tuple[ArtifactIdentity, ...]
    snapshots: tuple[_FileSnapshot, ...]
    run_topology: tuple[tuple[str, str], ...]
    data_topology: tuple[tuple[str, str], ...]
    work_topology: tuple[tuple[str, str], ...]
    in_progress_topology: tuple[tuple[str, str], ...]
    reports_topology: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Stage01AdoptionOutcome:
    output_directory: Path
    adoption_record_path: Path
    adoption_record_sha256: str
    bundle: ValidatedStage01Bundle


class _CanonicalEncoder:
    """Typed canonical binary encoder for the Stage 1 logical digest."""

    def __init__(self, digest: Any) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF:
            _fail("INVALID_UNSIGNED_INTEGER", "Integer does not fit canonical uint64")
        self._digest.update(_TYPE_UINT64)
        self._digest.update(struct.pack(">Q", value))

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            _fail("INVALID_TEXT", "Canonical text is invalid")
        encoded = value.encode("utf-8", errors="strict")
        self._digest.update(_TYPE_TEXT)
        self._digest.update(struct.pack(">Q", len(encoded)))
        self._digest.update(encoded)

    def digest(self, value: str) -> None:
        self._digest.update(_TYPE_DIGEST)
        self._digest.update(_digest_bytes(value))


def _fail(code: str, message: str) -> NoReturn:
    raise Stage01ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be 64 lowercase hexadecimal characters")
    return bytes.fromhex(value)


def _canonical_source_path(value: str) -> None:
    if not isinstance(value, str) or "\x00" in value:
        _fail("INVALID_SOURCE_PATH", "Source path is not canonical text")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.name != value
        or candidate.suffix.lower() != ".csv"
        or value in {".", ".."}
    ):
        _fail("INVALID_SOURCE_PATH", "Source path violates the Stage 0 v1 contract")


def _canonical_sources(
    records: Sequence[Stage01SourceRecord],
) -> tuple[Stage01SourceRecord, ...]:
    ordered = tuple(sorted(records, key=lambda item: item.relative_path))
    seen_paths: set[str] = set()
    seen_source_hashes: set[str] = set()
    for record in ordered:
        _canonical_source_path(record.relative_path)
        if record.relative_path in seen_paths:
            _fail(
                "DUPLICATE_SOURCE_PATH",
                "Logical dataset contains a duplicate source path",
            )
        seen_paths.add(record.relative_path)
        _digest_bytes(record.source_file_sha256)
        _digest_bytes(record.raw_semantic_digest_v1)
        if record.source_file_sha256 in seen_source_hashes:
            _fail(
                "DUPLICATE_SOURCE_CONTENT",
                "Duplicate source content would violate stable source-row identity",
            )
        seen_source_hashes.add(record.source_file_sha256)
        if (
            isinstance(record.logical_record_count, bool)
            or record.logical_record_count < 0
            or record.logical_record_count > 0xFFFF_FFFF_FFFF_FFFF
        ):
            _fail("INVALID_SOURCE_ROW_COUNT", "Source row count is outside uint64")
    return ordered


def stage01_logical_dataset_sha256_v1(
    records: Sequence[Stage01SourceRecord],
    *,
    stage00_source_population_sha256_v1: str,
    stage00_scientific_inventory_sha256_v1: str,
    stage00_parser_contract_fingerprint: str,
    arrow_schema_fingerprint: str | None = None,
) -> str:
    """Hash logical Stage 1 content independently of Parquet layout."""
    ordered = _canonical_sources(records)
    total_rows = sum(record.logical_record_count for record in ordered)
    if total_rows > 0xFFFF_FFFF_FFFF_FFFF:
        _fail("INVALID_TOTAL_ROW_COUNT", "Logical dataset row count exceeds uint64")

    digest = hashlib.sha256()
    digest.update(STAGE01_LOGICAL_DATASET_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE01_CONTRACT_VERSION)
    encoder.text(STAGE00_CONTRACT_VERSION)
    encoder.text(INVENTORY_VERSION)
    encoder.digest(stage00_source_population_sha256_v1)
    encoder.digest(stage00_scientific_inventory_sha256_v1)
    encoder.digest(stage00_parser_contract_fingerprint)
    encoder.text(PARSER_VERSION)
    encoder.text(SOURCE_SCHEMA_VERSION)
    encoder.text(STAGING_VERSION)
    encoder.digest(arrow_schema_fingerprint or schema_fingerprint())
    encoder.text(STABLE_ROW_ID_VERSION)
    encoder.text(SEMANTIC_DIGEST_VERSION)
    encoder.uint64(len(ordered))
    encoder.uint64(total_rows)
    for record in ordered:
        encoder.text(record.relative_path)
        encoder.digest(record.source_file_sha256)
        encoder.uint64(record.logical_record_count)
        encoder.digest(record.raw_semantic_digest_v1)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage01ValidationError(
            "ARTIFACT_READ_FAILURE", "Controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _require_regular_file(path: Path, code: str) -> None:
    if path.is_symlink() or not path.is_file():
        _fail(code, "Required controlled artifact is not a regular non-symlink file")


def _snapshot(path: Path) -> _FileSnapshot:
    _require_regular_file(path, "MISSING_OR_UNSAFE_ARTIFACT")
    try:
        stat = path.stat()
    except OSError as error:
        raise Stage01ValidationError(
            "ARTIFACT_STAT_FAILURE", "Controlled artifact identity could not be read"
        ) from error
    return _FileSnapshot(
        path=path.resolve(),
        device=stat.st_dev,
        inode=stat.st_ino,
        size_bytes=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        mode=stat.st_mode & 0o777,
    )


def _artifact_identity(
    path: Path,
    relative_path: str,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
) -> tuple[ArtifactIdentity, _FileSnapshot]:
    before = _snapshot(path)
    if expected_size is not None and before.size_bytes != expected_size:
        _fail("ARTIFACT_SIZE_MISMATCH", "Controlled artifact byte size differs")
    if expected_sha256 is not None:
        _digest_bytes(expected_sha256)
    observed_sha = _sha256_file(path)
    if expected_sha256 is not None and observed_sha != expected_sha256:
        _fail("ARTIFACT_SHA256_MISMATCH", "Controlled artifact SHA-256 differs")
    after = _snapshot(path)
    if before != after:
        _fail("BUNDLE_CHANGED_DURING_VALIDATION", "Artifact changed during validation")
    return ArtifactIdentity(relative_path, after.size_bytes, observed_sha), after


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    _require_regular_file(path, code)
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage01ValidationError(
            code, "Controlled JSON artifact is malformed"
        ) from error
    if not isinstance(value, dict):
        _fail(code, "Controlled JSON artifact is not an object")
    return cast(dict[str, Any], value)


def _mapping(value: object, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(code, "Required object is malformed")
    return cast(dict[str, Any], value)


def _sequence(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code, "Required array is malformed")
    return value


def _canonical_uint(value: object, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 0xFFFF_FFFF_FFFF_FFFF
    ):
        _fail(code, "Required integer is outside uint64")
    return value


def _canonical_text(value: object, code: str) -> str:
    if not isinstance(value, str) or value == "" or "\x00" in value:
        _fail(code, "Required text is malformed")
    return value


def _artifact_map(value: object, code: str) -> dict[str, ArtifactIdentity]:
    result: dict[str, ArtifactIdentity] = {}
    for raw in _sequence(value, code):
        item = _mapping(raw, code)
        relative = _canonical_text(item.get("relative_path"), code)
        if relative in result:
            _fail(code, "Artifact identity is duplicated")
        result[relative] = ArtifactIdentity(
            relative_path=relative,
            size_bytes=_canonical_uint(item.get("size_bytes"), code),
            sha256=_canonical_text(item.get("sha256"), code),
        )
        _digest_bytes(result[relative].sha256)
    return result


def validate_stage00_binding(
    stage00_adoption_record_path: Path,
    source_inventory_run_directory: Path,
    *,
    expected_stage00_adoption_sha256: str,
    expected_source_population_sha256: str,
    expected_scientific_inventory_sha256: str,
    expected_parser_contract_fingerprint: str,
) -> tuple[Stage00Binding, _FileSnapshot]:
    """Validate Stage 0 and its legacy Stage 0 source-inventory bundle without opening source CSV files."""
    _digest_bytes(expected_stage00_adoption_sha256)
    _digest_bytes(expected_source_population_sha256)
    _digest_bytes(expected_scientific_inventory_sha256)
    _digest_bytes(expected_parser_contract_fingerprint)
    adoption_artifact, adoption_snapshot = _artifact_identity(
        stage00_adoption_record_path,
        stage00_adoption_record_path.name,
        expected_sha256=expected_stage00_adoption_sha256,
    )
    if adoption_snapshot.mode != 0o600:
        _fail("PERMISSION_FAILURE", "Stage 0 adoption record is not owner-only")
    record = _load_json_object(stage00_adoption_record_path, "MALFORMED_STAGE00_RECORD")
    identity = _mapping(record.get("identity"), "MALFORMED_STAGE00_RECORD")
    validation = _mapping(record.get("validation"), "MALFORMED_STAGE00_RECORD")
    if (
        record.get("stage00_contract_version") != STAGE00_CONTRACT_VERSION
        or record.get("status") != "STAGE_0_ACCEPTED"
        or validation.get("acceptance_status") != "STAGE_0_ACCEPTED"
        or any(
            validation.get(key) != "PASS"
            for key in (
                "artifact_integrity",
                "manifest_schema",
                "parser_contract",
                "per_file_completeness",
                "population_contract",
                "terminal_state",
            )
        )
    ):
        _fail("STAGE00_NOT_ACCEPTED", "Stage 0 adoption gates are not accepted")
    expected_identity = {
        "source_population_sha256_v1": expected_source_population_sha256,
        "stage00_scientific_inventory_sha256_v1": expected_scientific_inventory_sha256,
        "parser_contract_fingerprint": expected_parser_contract_fingerprint,
    }
    if any(identity.get(key) != value for key, value in expected_identity.items()):
        _fail("STAGE00_IDENTITY_MISMATCH", "Stage 0 scientific identity differs")
    source_file_count = _canonical_uint(
        validation.get("source_file_count"), "MALFORMED_STAGE00_RECORD"
    )
    producing_commit = _canonical_text(
        identity.get("producing_git_commit"), "MALFORMED_STAGE00_RECORD"
    )
    if _FULL_GIT_SHA_RE.fullmatch(producing_commit) is None:
        _fail(
            "MALFORMED_STAGE00_RECORD",
            "legacy Stage 0 source-inventory producing commit is not a full SHA",
        )

    source_inventory = validate_stage00_inventory(
        source_inventory_run_directory,
        expected_file_count=source_file_count,
        expected_producing_git_commit=producing_commit,
    )
    if (
        identity.get("adopted_phase01_run_id") != source_inventory.run_id
        or identity.get("phase01_inventory_version")
        != source_inventory.inventory_version
        or source_inventory.source_population_sha256_v1
        != expected_source_population_sha256
        or source_inventory.stage00_scientific_inventory_sha256_v1
        != expected_scientific_inventory_sha256
        or source_inventory.parser_contract_fingerprint
        != expected_parser_contract_fingerprint
    ):
        _fail(
            "STAGE00_PHASE01_BINDING_MISMATCH",
            "Stage 0 and legacy Stage 0 source-inventory differ",
        )
    if len({record.file_sha256 for record in source_inventory.records}) != len(
        source_inventory.records
    ):
        _fail(
            "DUPLICATE_SOURCE_CONTENT",
            "Duplicate source content would violate stable source-row identity",
        )

    bundle_integrity = _mapping(
        record.get("bundle_integrity"), "MALFORMED_STAGE00_RECORD"
    )
    recorded_artifacts = _artifact_map(
        bundle_integrity.get("artifacts"), "MALFORMED_STAGE00_RECORD"
    )
    actual_artifacts = {item.relative_path: item for item in source_inventory.artifacts}
    if recorded_artifacts != actual_artifacts:
        _fail("STAGE00_ARTIFACT_MISMATCH", "Stage 0 artifact identities differ")
    terminal = _mapping(
        bundle_integrity.get("terminal_state"), "MALFORMED_STAGE00_RECORD"
    )
    success = _mapping(terminal.get("success_marker"), "MALFORMED_STAGE00_RECORD")
    if (
        success != source_inventory.success_marker.to_dict()
        or terminal.get("failure_marker_present") is not False
        or terminal.get("in_progress_marker_present") is not False
    ):
        _fail("STAGE00_TERMINAL_MISMATCH", "Stage 0 terminal evidence differs")

    source_inventory_run = _load_json_object(
        source_inventory.run_dir / "phase01_run.json", "MALFORMED_PHASE01_RUN"
    )
    input_manifest_sha = _canonical_text(
        source_inventory_run.get("input_manifest_sha256"), "MALFORMED_PHASE01_RUN"
    )
    _digest_bytes(input_manifest_sha)
    return (
        Stage00Binding(
            adoption_record=adoption_artifact,
            source_inventory_bundle=source_inventory,
            source_inventory_manifest_sha256=input_manifest_sha,
            source_population_sha256_v1=expected_source_population_sha256,
            scientific_inventory_sha256_v1=expected_scientific_inventory_sha256,
            parser_contract_fingerprint=expected_parser_contract_fingerprint,
        ),
        adoption_snapshot,
    )


def resolve_stage00_binding(
    stage00_adoption_record_path: Path,
    source_inventory_run_directory: Path,
    *,
    expected_stage00_adoption_sha256: str,
) -> Stage00Binding:
    """Resolve a hash-pinned accepted Stage 0 record into its exact population."""
    _digest_bytes(expected_stage00_adoption_sha256)
    _, snapshot = _artifact_identity(
        stage00_adoption_record_path,
        stage00_adoption_record_path.name,
        expected_sha256=expected_stage00_adoption_sha256,
    )
    if snapshot.mode != 0o600:
        _fail("PERMISSION_FAILURE", "Stage 0 adoption record is not owner-only")
    record = _load_json_object(stage00_adoption_record_path, "MALFORMED_STAGE00_RECORD")
    identity = _mapping(record.get("identity"), "MALFORMED_STAGE00_RECORD")
    binding, _ = validate_stage00_binding(
        stage00_adoption_record_path,
        source_inventory_run_directory,
        expected_stage00_adoption_sha256=expected_stage00_adoption_sha256,
        expected_source_population_sha256=_canonical_text(
            identity.get("source_population_sha256_v1"),
            "MALFORMED_STAGE00_RECORD",
        ),
        expected_scientific_inventory_sha256=_canonical_text(
            identity.get("stage00_scientific_inventory_sha256_v1"),
            "MALFORMED_STAGE00_RECORD",
        ),
        expected_parser_contract_fingerprint=_canonical_text(
            identity.get("parser_contract_fingerprint"),
            "MALFORMED_STAGE00_RECORD",
        ),
    )
    return binding


def _verify_directory_mode(path: Path, mode: int, code: str) -> None:
    if path.is_symlink() or not path.is_dir():
        _fail(code, "Protected directory is missing or unsafe")
    if path.stat().st_mode & 0o777 != mode:
        _fail(code, "Protected directory permissions are not owner-only")


def _protected_tree_snapshots(path: Path) -> tuple[_FileSnapshot, ...]:
    _verify_directory_mode(path, 0o700, "PERMISSION_FAILURE")
    pending = [path]
    snapshots: list[_FileSnapshot] = []
    while pending:
        directory = pending.pop()
        _verify_directory_mode(directory, 0o700, "PERMISSION_FAILURE")
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    if entry.is_symlink():
                        _fail(
                            "UNSAFE_PROTECTED_TREE", "Protected tree contains a symlink"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(child)
                    elif entry.is_file(follow_symlinks=False):
                        snapshot = _snapshot(child)
                        if snapshot.mode != 0o600:
                            _fail(
                                "PERMISSION_FAILURE", "Protected file is not owner-only"
                            )
                        snapshots.append(snapshot)
                    else:
                        _fail(
                            "UNSAFE_PROTECTED_TREE",
                            "Protected tree contains a special file",
                        )
        except OSError as error:
            raise Stage01ValidationError(
                "PERMISSION_FAILURE", "Protected tree could not be inspected"
            ) from error
    return tuple(sorted(snapshots, key=lambda item: item.path.as_posix()))


def _directory_topology(
    path: Path, *, recursive: bool = False, protected: bool = False
) -> tuple[tuple[str, str], ...]:
    if path.is_symlink() or not path.is_dir():
        _fail("UNSAFE_DIRECTORY_TOPOLOGY", "Controlled directory is missing or unsafe")
    pending = [path]
    topology: list[tuple[str, str]] = []
    try:
        while pending:
            directory = pending.pop()
            if protected:
                _verify_directory_mode(directory, 0o700, "PERMISSION_FAILURE")
            with os.scandir(directory) as entries:
                for entry in entries:
                    child = Path(entry.path)
                    relative = child.relative_to(path).as_posix()
                    if entry.is_symlink():
                        _fail(
                            "UNSAFE_DIRECTORY_TOPOLOGY",
                            "Controlled directory contains a symlink",
                        )
                    if entry.is_dir(follow_symlinks=False):
                        topology.append((relative, "directory"))
                        if recursive:
                            pending.append(child)
                    elif entry.is_file(follow_symlinks=False):
                        if protected and child.stat().st_mode & 0o777 != 0o600:
                            _fail(
                                "PERMISSION_FAILURE",
                                "Protected file is not owner-only",
                            )
                        topology.append((relative, "file"))
                    else:
                        _fail(
                            "UNSAFE_DIRECTORY_TOPOLOGY",
                            "Controlled directory contains a special file",
                        )
    except Stage01ValidationError:
        raise
    except OSError as error:
        raise Stage01ValidationError(
            "DIRECTORY_TOPOLOGY_FAILURE",
            "Controlled directory topology could not be inspected",
        ) from error
    return tuple(sorted(topology))


def _validate_stage01_state(
    state_path: Path,
    records: Sequence[Stage01SourceRecord],
    *,
    run_id: str,
    source_inventory_manifest_sha256: str,
    configuration_fingerprint: str,
    implementation_fingerprint: str,
    manifest_files: Mapping[str, Mapping[str, Any]],
) -> None:
    expected = {record.relative_path: record for record in records}
    wal_path = state_path.with_name(f"{state_path.name}-wal")
    if wal_path.exists():
        _require_regular_file(wal_path, "STATE_INTEGRITY_FAILURE")
        if wal_path.stat().st_size != 0:
            _fail(
                "STATE_NOT_CHECKPOINTED",
                "Completed accepted Stage 1 ingestion state has an uncheckpointed WAL",
            )
    try:
        with tempfile.TemporaryDirectory(prefix="safe-stage01-state-") as temporary:
            temporary_path = Path(temporary)
            temporary_path.chmod(0o700)
            isolated_state = temporary_path / state_path.name
            shutil.copyfile(state_path, isolated_state)
            isolated_state.chmod(0o600)
            connection = sqlite3.connect(isolated_state)
            connection.row_factory = sqlite3.Row
            try:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    _fail(
                        "STATE_INTEGRITY_FAILURE",
                        "accepted Stage 1 ingestion state store is not valid",
                    )
                rows = connection.execute(
                    """
                    SELECT relative_path, source_sha256, expected_rows, status, attempt,
                           config_fingerprint, implementation_fingerprint, final_path,
                           source_semantic_digest, staging_semantic_digest,
                           output_sha256, output_size_bytes, source_rows, staging_rows,
                           failure_code, failure_detail
                    FROM file_state ORDER BY relative_path COLLATE BINARY
                    """
                ).fetchall()
                attempts = connection.execute(
                    "SELECT relative_path, attempt, completed_at_utc, terminal_status, "
                    "failure_code, output_sha256 FROM attempt_history "
                    "ORDER BY relative_path COLLATE BINARY, attempt"
                ).fetchall()
                run_meta = dict(connection.execute("SELECT key, value FROM run_meta"))
            finally:
                connection.close()
    except Stage01ValidationError:
        raise
    except (OSError, sqlite3.Error) as error:
        raise Stage01ValidationError(
            "STATE_INTEGRITY_FAILURE",
            "accepted Stage 1 ingestion state store cannot be validated",
        ) from error
    if len(rows) != len(expected) or {row["relative_path"] for row in rows} != set(
        expected
    ):
        _fail(
            "STATE_SCOPE_MISMATCH",
            "accepted Stage 1 ingestion state source scope differs",
        )
    for row in rows:
        record = expected[str(row["relative_path"])]
        manifest_file = manifest_files[record.relative_path]
        if (
            row["status"] != "COMPLETE"
            or row["source_sha256"] != record.source_file_sha256
            or row["expected_rows"] != record.logical_record_count
            or row["config_fingerprint"] != configuration_fingerprint
            or row["implementation_fingerprint"] != implementation_fingerprint
            or row["final_path"] != manifest_file["output_file"]
            or row["source_rows"] != record.logical_record_count
            or row["staging_rows"] != record.logical_record_count
            or row["source_semantic_digest"] != record.raw_semantic_digest_v1
            or row["staging_semantic_digest"] != record.raw_semantic_digest_v1
            or row["output_sha256"] != manifest_file["output_sha256"]
            or row["output_size_bytes"] != manifest_file["output_size_bytes"]
            or not isinstance(row["attempt"], int)
            or row["attempt"] < 1
            or row["failure_code"] != ""
            or row["failure_detail"] != ""
        ):
            _fail(
                "STATE_FILE_MISMATCH",
                "accepted Stage 1 ingestion state file evidence differs",
            )
    expected_meta = {
        "run_id": run_id,
        "run_scope": "FULL_CONVERSION",
        "phase01_input_manifest_sha256": source_inventory_manifest_sha256,
        "configuration_fingerprint": configuration_fingerprint,
        "implementation_fingerprint": implementation_fingerprint,
    }
    if any(run_meta.get(key) != value for key, value in expected_meta.items()):
        _fail(
            "STATE_META_MISMATCH",
            "accepted Stage 1 ingestion state run metadata differs",
        )
    attempts_by_path: dict[str, list[sqlite3.Row]] = {}
    for attempt_row in attempts:
        relative_path = attempt_row["relative_path"]
        if relative_path not in expected:
            _fail(
                "STATE_TERMINAL_MISMATCH",
                "accepted Stage 1 ingestion attempt scope differs",
            )
        attempts_by_path.setdefault(relative_path, []).append(attempt_row)
    state_by_path = {str(row["relative_path"]): row for row in rows}
    for relative_path, record in expected.items():
        history = attempts_by_path.get(relative_path, [])
        final_attempt = state_by_path[relative_path]["attempt"]
        if (
            [row["attempt"] for row in history] != list(range(1, final_attempt + 1))
            or any(row["completed_at_utc"] == "" for row in history)
            or any(row["terminal_status"] != "FAILED" for row in history[:-1])
            or any(row["failure_code"] == "" for row in history[:-1])
            or not history
            or history[-1]["terminal_status"] != "COMPLETE"
            or history[-1]["failure_code"] != ""
            or history[-1]["output_sha256"]
            != manifest_files[record.relative_path]["output_sha256"]
        ):
            _fail(
                "STATE_TERMINAL_MISMATCH",
                "accepted Stage 1 ingestion attempt history is not complete",
            )


def _validate_file_report(
    path: Path,
    *,
    run_id: str,
    manifest_files: Mapping[str, Mapping[str, Any]],
) -> None:
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != FILE_VALIDATION_COLUMNS:
                _fail(
                    "FILE_REPORT_SCHEMA_MISMATCH",
                    "accepted Stage 1 ingestion file report schema differs",
                )
            seen: set[str] = set()
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    _fail(
                        "MALFORMED_FILE_REPORT",
                        "accepted Stage 1 ingestion file report row is malformed",
                    )
                source_path = row["relative_path"]
                if source_path in seen or source_path not in manifest_files:
                    _fail(
                        "FILE_REPORT_SCOPE_MISMATCH",
                        "accepted Stage 1 ingestion file report scope differs",
                    )
                seen.add(source_path)
                expected = manifest_files[source_path]
                if (
                    row["run_id"] != run_id
                    or row["status"] != "PASS"
                    or row["failure_code"] != ""
                    or row["failure_detail"] != ""
                    or int(row["source_rows"]) != expected["source_rows"]
                    or int(row["staging_rows"]) != expected["staging_rows"]
                    or row["source_sha256"] != expected["source_sha256"]
                    or row["source_semantic_digest"]
                    != expected["source_semantic_digest"]
                    or row["staging_semantic_digest"]
                    != expected["staging_semantic_digest"]
                    or row["output_path"] != expected["output_file"]
                    or int(row["output_size_bytes"]) != expected["output_size_bytes"]
                    or row["output_sha256"] != expected["output_sha256"]
                    or row["semantic_digest_match"] != "True"
                    or row["page_checksums_verified"] != "True"
                    or row["provenance_valid"] != "True"
                    or row["stable_ids_valid"] != "True"
                    or int(row["stable_ids_distinct"]) != expected["source_rows"]
                    or int(row["raw_null_count"]) != 0
                ):
                    _fail(
                        "FILE_REPORT_VALIDATION_MISMATCH",
                        "accepted Stage 1 ingestion file evidence differs",
                    )
    except Stage01ValidationError:
        raise
    except (OSError, UnicodeError, csv.Error, KeyError, TypeError, ValueError) as error:
        raise Stage01ValidationError(
            "MALFORMED_FILE_REPORT",
            "accepted Stage 1 ingestion file report cannot be interpreted",
        ) from error
    if seen != set(manifest_files):
        _fail(
            "FILE_REPORT_SCOPE_MISMATCH",
            "accepted Stage 1 ingestion file report is incomplete",
        )


def _validate_failures_report(path: Path) -> None:
    try:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if (
                tuple(reader.fieldnames or ())
                != (
                    "run_id",
                    "relative_path",
                    "failure_code",
                    "failure_detail",
                )
                or next(reader, None) is not None
            ):
                _fail(
                    "PHASE02_FAILURES_PRESENT",
                    "accepted Stage 1 ingestion failure report is not empty",
                )
    except Stage01ValidationError:
        raise
    except (OSError, UnicodeError, csv.Error) as error:
        raise Stage01ValidationError(
            "MALFORMED_FAILURE_REPORT",
            "accepted Stage 1 ingestion failure report cannot be interpreted",
        ) from error


def _validate_stage01_reports(
    reports_directory: Path,
    *,
    run_id: str,
    producing_git_commit: str,
    stage00: Stage00Binding,
    manifest: Mapping[str, Any],
    manifest_files: Mapping[str, Mapping[str, Any]],
    total_parquet_bytes: int,
) -> tuple[tuple[ArtifactIdentity, ...], tuple[_FileSnapshot, ...], dict[str, Any]]:
    if reports_directory.is_symlink() or not reports_directory.is_dir():
        _fail(
            "INVALID_REPORT_DIRECTORY",
            "accepted Stage 1 ingestion report directory is missing or unsafe",
        )
    report_identities: list[ArtifactIdentity] = []
    snapshots: list[_FileSnapshot] = []
    for name in REPORT_NAMES:
        identity, snapshot = _artifact_identity(reports_directory / name, name)
        report_identities.append(identity)
        snapshots.append(snapshot)

    run = _load_json_object(
        reports_directory / "phase02_run.json", "MALFORMED_PHASE02_RUN"
    )
    run_commit = run.get("git_commit")
    if (
        run.get("run_id") != run_id
        or run.get("run_scope") != "FULL_CONVERSION"
        or run.get("status") != "COMPLETED_SCOPE_PASS"
        or run.get("scope_gate") != "PASS"
        or run.get("phase02_completion_gate") != "PASS"
        or run.get("git_dirty") is not False
        or not isinstance(run_commit, str)
        or _HISTORICAL_GIT_SHA_RE.fullmatch(run_commit) is None
        or not producing_git_commit.startswith(run_commit)
        or run.get("phase01_run_id") != stage00.source_inventory_bundle.run_id
        or run.get("phase01_input_manifest_sha256")
        != stage00.source_inventory_manifest_sha256
        or run.get("configuration_fingerprint")
        != manifest.get("configuration_fingerprint")
        or run.get("implementation_fingerprint")
        != manifest.get("implementation_fingerprint")
    ):
        _fail(
            "PHASE02_RUN_MISMATCH",
            "accepted Stage 1 ingestion run provenance or gates differ",
        )
    configuration = _mapping(run.get("configuration"), "MALFORMED_PHASE02_RUN")
    if (
        configuration.get("source_schema_version") != SOURCE_SCHEMA_VERSION
        or configuration.get("parser_version") != PARSER_VERSION
        or configuration.get("staging_version") != STAGING_VERSION
        or configuration.get("semantic_digest_version") != SEMANTIC_DIGEST_VERSION
        or configuration.get("stable_row_id_version") != STABLE_ROW_ID_VERSION
        or configuration.get("schema_fingerprint") != schema_fingerprint()
    ):
        _fail(
            "PHASE02_SCIENTIFIC_CONTRACT_MISMATCH",
            "accepted Stage 1 ingestion contracts differ",
        )
    accepted_population = configuration.get("accepted_stage00_population")
    if accepted_population is not None:
        expected_population = {
            "stage00_contract_version": STAGE00_CONTRACT_VERSION,
            "stage00_adoption_record_sha256": stage00.adoption_record.sha256,
            "source_population_sha256_v1": stage00.source_population_sha256_v1,
            "stage00_scientific_inventory_sha256_v1": (
                stage00.scientific_inventory_sha256_v1
            ),
            "parser_contract_fingerprint": stage00.parser_contract_fingerprint,
            "phase01_run_id": stage00.source_inventory_bundle.run_id,
            "phase01_input_manifest_sha256": stage00.source_inventory_manifest_sha256,
            "source_file_count": len(stage00.source_inventory_bundle.records),
        }
        if accepted_population != expected_population:
            _fail(
                "PHASE02_POPULATION_CONTRACT_MISMATCH",
                "accepted Stage 1 ingestion accepted Stage 0 population identity differs",
            )
    metrics = _mapping(run.get("metrics"), "MALFORMED_PHASE02_RUN")
    if metrics.get("parquet_bytes") != total_parquet_bytes or metrics.get(
        "source_bytes"
    ) != sum(
        record.file_size_bytes for record in stage00.source_inventory_bundle.records
    ):
        _fail(
            "PHASE02_METRIC_MISMATCH",
            "accepted Stage 1 ingestion aggregate byte evidence differs",
        )

    schema_report = _load_json_object(
        reports_directory / "phase02_schema.json", "MALFORMED_SCHEMA_REPORT"
    )
    expected_fields = [
        {
            "position": index,
            "name": field.name,
            "type": str(field.type),
            "nullable": field.nullable,
        }
        for index, field in enumerate(base_staging_schema(), start=1)
    ]
    if (
        schema_report.get("schema_version") != "phase02_arrow_schema_v1"
        or schema_report.get("schema_fingerprint") != schema_fingerprint()
        or schema_report.get("fields") != expected_fields
    ):
        _fail(
            "SCHEMA_REPORT_MISMATCH", "accepted Stage 1 ingestion schema report differs"
        )

    reconciliation_report = _load_json_object(
        reports_directory / "phase02_reconciliation.json",
        "MALFORMED_RECONCILIATION_REPORT",
    )
    reconciliation = _mapping(
        manifest.get("reconciliation"), "MALFORMED_PHASE02_MANIFEST"
    )
    for key in (
        "status",
        "file_count",
        "total_rows",
        "distinct_ids",
        "distinct_stable_ids",
        "null_ids",
        "duplicate_stable_ids",
        "raw_null_count",
        "schema_count",
        "missing_files",
        "extra_files",
    ):
        if reconciliation_report.get(key) != reconciliation.get(key):
            _fail(
                "RECONCILIATION_REPORT_MISMATCH",
                "accepted Stage 1 ingestion reconciliation differs",
            )
    _validate_file_report(
        reports_directory / "phase02_file_validation.csv",
        run_id=run_id,
        manifest_files=manifest_files,
    )
    _validate_failures_report(reports_directory / "phase02_failures.csv.gz")
    return tuple(report_identities), tuple(snapshots), run


def _output_path(value: object) -> str:
    text = _canonical_text(value, "MALFORMED_PHASE02_MANIFEST")
    candidate = PurePosixPath(text)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 2
        or candidate.parts[0] != "data"
        or candidate.suffix.lower() != ".parquet"
        or candidate.name in {".", ".."}
    ):
        _fail(
            "UNSAFE_SHARD_PATH",
            "accepted Stage 1 ingestion output path is outside the data directory",
        )
    return text


def _parquet_metadata(path: Path) -> tuple[pq.FileMetaData, dict[str, str]]:
    try:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        if not exact_schema_matches(parquet.schema_arrow):
            _fail("PARQUET_SCHEMA_MISMATCH", "Parquet Arrow schema differs")
        metadata = {
            key.decode("utf-8"): value.decode("utf-8")
            for key, value in (parquet.schema_arrow.metadata or {}).items()
        }
        return parquet.metadata, metadata
    except Stage01ValidationError:
        raise
    except (OSError, UnicodeError, pyarrow.ArrowException) as error:
        raise Stage01ValidationError(
            "PARQUET_METADATA_FAILURE", "Parquet metadata cannot be validated"
        ) from error


def _validate_manifest_shape(manifest: Mapping[str, Any]) -> None:
    expected_keys = {
        "run_id",
        "run_scope",
        "phase02_completion_gate",
        "phase01_input_manifest_sha256",
        "configuration_fingerprint",
        "implementation_fingerprint",
        "schema_fingerprint",
        "files",
        "reconciliation",
    }
    if set(manifest) != expected_keys:
        _fail(
            "PHASE02_MANIFEST_SCHEMA_MISMATCH",
            "accepted Stage 1 ingestion manifest fields are not exact",
        )


def validate_stage01_bundle(
    ingestion_run_directory: Path,
    ingestion_reports_directory: Path,
    source_inventory_run_directory: Path,
    stage00_adoption_record_path: Path,
    *,
    expected_stage00_adoption_sha256: str,
    expected_source_population_sha256: str,
    expected_scientific_inventory_sha256: str,
    expected_parser_contract_fingerprint: str,
    expected_ingestion_run_id: str,
    expected_ingestion_producing_git_commit: str,
    production: bool,
) -> ValidatedStage01Bundle:
    """Validate a completed accepted Stage 1 ingestion bundle without opening source CSV files."""
    if production:
        require_goethe_nhr_slurm("stage01.bundle-validation")
    if _RUN_ID_RE.fullmatch(expected_ingestion_run_id) is None:
        _fail(
            "INVALID_PHASE02_RUN_ID",
            "Expected accepted Stage 1 ingestion run ID is malformed",
        )
    if _FULL_GIT_SHA_RE.fullmatch(expected_ingestion_producing_git_commit) is None:
        _fail(
            "INVALID_GIT_COMMIT",
            "accepted Stage 1 ingestion producing commit is not a full SHA",
        )

    stage00, stage00_snapshot = validate_stage00_binding(
        stage00_adoption_record_path,
        source_inventory_run_directory,
        expected_stage00_adoption_sha256=expected_stage00_adoption_sha256,
        expected_source_population_sha256=expected_source_population_sha256,
        expected_scientific_inventory_sha256=expected_scientific_inventory_sha256,
        expected_parser_contract_fingerprint=expected_parser_contract_fingerprint,
    )
    if ingestion_run_directory.is_symlink():
        _fail(
            "INVALID_RUN_DIRECTORY",
            "accepted Stage 1 ingestion run directory is a symlink",
        )
    run_dir = ingestion_run_directory.resolve()
    _verify_directory_mode(run_dir, 0o700, "PERMISSION_FAILURE")
    data_dir = run_dir / "data"
    work_dir = run_dir / "_work"
    in_progress_dir = run_dir / ".in_progress"
    _verify_directory_mode(data_dir, 0o700, "PERMISSION_FAILURE")
    work_snapshots = _protected_tree_snapshots(work_dir)
    in_progress_snapshots = _protected_tree_snapshots(in_progress_dir)
    run_topology = _directory_topology(run_dir)
    expected_run_topology = tuple(
        sorted(
            (
                (".in_progress", "directory"),
                ("_SUCCESS.json", "file"),
                ("_work", "directory"),
                ("data", "directory"),
                ("dataset_manifest.json", "file"),
            )
        )
    )
    work_topology = _directory_topology(work_dir, recursive=True, protected=True)
    in_progress_topology = _directory_topology(
        in_progress_dir, recursive=True, protected=True
    )
    if in_progress_snapshots:
        _fail(
            "BUNDLE_IN_PROGRESS",
            "accepted Stage 1 ingestion in-progress directory is not empty",
        )
    for marker in (
        "_IN_PROGRESS",
        "_FAILURE.json",
        "_FAIL.json",
        "_SCOPE_FAIL",
        "_SCOPE_SUCCESS.json",
    ):
        candidate = run_dir / marker
        if candidate.exists() or candidate.is_symlink():
            _fail(
                "CONTRADICTORY_TERMINAL_STATE",
                "accepted Stage 1 ingestion terminal state is contradictory",
            )

    manifest_path = run_dir / INGESTION_MANIFEST_NAME
    success_path = run_dir / INGESTION_SUCCESS_MARKER
    manifest_identity, manifest_snapshot = _artifact_identity(
        manifest_path, INGESTION_MANIFEST_NAME
    )
    success_identity, success_snapshot = _artifact_identity(
        success_path, INGESTION_SUCCESS_MARKER
    )
    if run_topology != expected_run_topology:
        _fail(
            "PHASE02_RUN_TOPOLOGY_MISMATCH",
            "accepted Stage 1 ingestion run artifact set differs",
        )
    if manifest_snapshot.mode != 0o600 or success_snapshot.mode != 0o600:
        _fail(
            "PERMISSION_FAILURE",
            "accepted Stage 1 ingestion terminal artifacts are not owner-only",
        )
    manifest = _load_json_object(manifest_path, "MALFORMED_PHASE02_MANIFEST")
    _validate_manifest_shape(manifest)
    success = _load_json_object(success_path, "MALFORMED_PHASE02_SUCCESS")
    historical_success_keys = {
        "run_id",
        "run_scope",
        "scope_gate",
        "phase02_completion_gate",
        "dataset_manifest_sha256",
        "files",
        "rows",
        "completed_at_utc",
    }
    extended_success_keys = historical_success_keys | {
        "git_commit",
        "source_bytes",
        "staging_bytes",
    }
    if set(success) not in (historical_success_keys, extended_success_keys):
        _fail(
            "PHASE02_SUCCESS_SCHEMA_MISMATCH",
            "accepted Stage 1 ingestion success fields differ",
        )
    if (
        manifest.get("run_id") != expected_ingestion_run_id
        or run_dir.name != expected_ingestion_run_id
        or manifest.get("run_scope") != "FULL_CONVERSION"
        or manifest.get("phase02_completion_gate") != "PASS"
        or manifest.get("phase01_input_manifest_sha256")
        != stage00.source_inventory_manifest_sha256
        or manifest.get("schema_fingerprint") != schema_fingerprint()
    ):
        _fail(
            "PHASE02_MANIFEST_IDENTITY_MISMATCH",
            "accepted Stage 1 ingestion manifest identity differs",
        )
    for key in ("configuration_fingerprint", "implementation_fingerprint"):
        _digest_bytes(_canonical_text(manifest.get(key), "MALFORMED_PHASE02_MANIFEST"))
    if (
        success.get("run_id") != expected_ingestion_run_id
        or success.get("run_scope") != "FULL_CONVERSION"
        or success.get("scope_gate") != "PASS"
        or success.get("phase02_completion_gate") != "PASS"
        or success.get("dataset_manifest_sha256") != manifest_identity.sha256
    ):
        _fail(
            "PHASE02_SUCCESS_MISMATCH",
            "accepted Stage 1 ingestion success marker differs",
        )

    stage00_by_path = {
        record.relative_path: record
        for record in stage00.source_inventory_bundle.records
    }
    manifest_file_values = _sequence(
        manifest.get("files"), "MALFORMED_PHASE02_MANIFEST"
    )
    manifest_files: dict[str, Mapping[str, Any]] = {}
    output_paths: set[str] = set()
    sources: list[Stage01SourceRecord] = []
    expected_shards: dict[str, Mapping[str, Any]] = {}
    expected_file_keys = {
        "source_file",
        "source_sha256",
        "source_rows",
        "output_file",
        "output_sha256",
        "output_size_bytes",
        "staging_rows",
        "source_semantic_digest",
        "staging_semantic_digest",
        "status",
    }
    for raw in manifest_file_values:
        item = _mapping(raw, "MALFORMED_PHASE02_MANIFEST")
        if set(item) != expected_file_keys:
            _fail(
                "PHASE02_MANIFEST_SCHEMA_MISMATCH",
                "accepted Stage 1 ingestion file fields are not exact",
            )
        source_path = _canonical_text(
            item.get("source_file"), "MALFORMED_PHASE02_MANIFEST"
        )
        _canonical_source_path(source_path)
        if source_path in manifest_files or source_path not in stage00_by_path:
            _fail(
                "PHASE02_SOURCE_SCOPE_MISMATCH",
                "accepted Stage 1 ingestion source scope differs",
            )
        source_sha = _canonical_text(
            item.get("source_sha256"), "MALFORMED_PHASE02_MANIFEST"
        )
        source_rows = _canonical_uint(
            item.get("source_rows"), "MALFORMED_PHASE02_MANIFEST"
        )
        staging_rows = _canonical_uint(
            item.get("staging_rows"), "MALFORMED_PHASE02_MANIFEST"
        )
        source_digest = _canonical_text(
            item.get("source_semantic_digest"), "MALFORMED_PHASE02_MANIFEST"
        )
        staging_digest = _canonical_text(
            item.get("staging_semantic_digest"), "MALFORMED_PHASE02_MANIFEST"
        )
        output_sha = _canonical_text(
            item.get("output_sha256"), "MALFORMED_PHASE02_MANIFEST"
        )
        _digest_bytes(source_sha)
        _digest_bytes(source_digest)
        _digest_bytes(staging_digest)
        _digest_bytes(output_sha)
        stage00_record = stage00_by_path[source_path]
        if (
            source_sha != stage00_record.file_sha256
            or source_rows != stage00_record.logical_record_count
            or staging_rows != source_rows
            or source_digest != staging_digest
            or item.get("status") != "PASS"
        ):
            _fail(
                "PHASE02_SOURCE_PROJECTION_MISMATCH",
                "accepted Stage 1 ingestion source projection differs",
            )
        output_path = _output_path(item.get("output_file"))
        if output_path in output_paths:
            _fail(
                "DUPLICATE_SHARD_PATH",
                "accepted Stage 1 ingestion shard path is duplicated",
            )
        output_paths.add(output_path)
        output_size = _canonical_uint(
            item.get("output_size_bytes"), "MALFORMED_PHASE02_MANIFEST"
        )
        if output_size == 0:
            _fail("INVALID_SHARD_SIZE", "accepted Stage 1 ingestion shard size is zero")
        manifest_files[source_path] = item
        expected_shards[output_path] = item
        sources.append(
            Stage01SourceRecord(source_path, source_sha, source_rows, source_digest)
        )
    if set(manifest_files) != set(stage00_by_path):
        _fail(
            "PHASE02_SOURCE_SCOPE_MISMATCH",
            "accepted Stage 1 ingestion source population is incomplete",
        )
    if [record.relative_path for record in sources] != sorted(stage00_by_path):
        _fail(
            "PHASE02_SOURCE_ORDER_MISMATCH",
            "accepted Stage 1 ingestion source order is not canonical",
        )
    ordered_sources = _canonical_sources(sources)

    observed_entries = list(data_dir.iterdir())
    if any(path.is_symlink() or not path.is_file() for path in observed_entries):
        _fail(
            "UNSAFE_SHARD",
            "accepted Stage 1 ingestion data directory contains an unsafe entry",
        )
    observed_relative = {
        path.relative_to(run_dir).as_posix() for path in observed_entries
    }
    if observed_relative != set(expected_shards):
        _fail(
            "PHASE02_SHARD_SET_MISMATCH",
            "accepted Stage 1 ingestion shard set differs from manifest",
        )
    data_topology = _directory_topology(data_dir, protected=True)

    shard_identities: list[ArtifactIdentity] = []
    shard_snapshots: list[_FileSnapshot] = []
    total_parquet_bytes = 0
    for relative_path in sorted(expected_shards):
        shard_item = expected_shards[relative_path]
        path = run_dir / relative_path
        identity, snapshot = _artifact_identity(
            path,
            relative_path,
            expected_size=cast(int, shard_item["output_size_bytes"]),
            expected_sha256=cast(str, shard_item["output_sha256"]),
        )
        if snapshot.mode != 0o600:
            _fail(
                "PERMISSION_FAILURE",
                "accepted Stage 1 ingestion shard is not owner-only",
            )
        metadata, parquet_metadata = _parquet_metadata(path)
        source_path = cast(str, shard_item["source_file"])
        required_metadata = {
            "phase02_run_id": expected_ingestion_run_id,
            "phase01_run_id": stage00.source_inventory_bundle.run_id,
            "phase01_input_manifest_sha256": stage00.source_inventory_manifest_sha256,
            "pipeline_git_commit": expected_ingestion_producing_git_commit[:8],
            "source_file": source_path,
            "source_file_sha256": cast(str, shard_item["source_sha256"]),
            "source_schema_version": SOURCE_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "staging_version": STAGING_VERSION,
            "semantic_digest_version": SEMANTIC_DIGEST_VERSION,
            "stable_source_row_id_version": STABLE_ROW_ID_VERSION,
            "configuration_fingerprint": cast(
                str, manifest["configuration_fingerprint"]
            ),
            "implementation_fingerprint": cast(
                str, manifest["implementation_fingerprint"]
            ),
        }
        if any(
            parquet_metadata.get(key) != value
            for key, value in required_metadata.items()
        ):
            _fail(
                "PARQUET_METADATA_MISMATCH",
                "accepted Stage 1 ingestion Parquet metadata differs",
            )
        if metadata.num_rows != shard_item["staging_rows"]:
            _fail(
                "PARQUET_ROW_COUNT_MISMATCH",
                "accepted Stage 1 ingestion Parquet row count differs",
            )
        shard_identities.append(identity)
        shard_snapshots.append(snapshot)
        total_parquet_bytes += identity.size_bytes

    reconciliation = _mapping(
        manifest.get("reconciliation"), "MALFORMED_PHASE02_MANIFEST"
    )
    total_rows = sum(record.logical_record_count for record in ordered_sources)
    if (
        reconciliation.get("status") != "PASS"
        or reconciliation.get("file_count") != len(shard_identities)
        or reconciliation.get("total_rows") != total_rows
        or reconciliation.get("distinct_stable_ids") != total_rows
        or reconciliation.get("duplicate_stable_ids") != 0
        or reconciliation.get("raw_null_count") != 0
        or reconciliation.get("schema_count") != 1
        or reconciliation.get("missing_files") != []
        or reconciliation.get("extra_files") != []
    ):
        _fail(
            "PHASE02_RECONCILIATION_FAILURE",
            "accepted Stage 1 ingestion reconciliation did not pass",
        )
    if (
        success.get("files") != len(shard_identities)
        or success.get("rows") != total_rows
    ):
        _fail(
            "PHASE02_SUCCESS_MISMATCH",
            "accepted Stage 1 ingestion success counts differ",
        )
    if set(success) == extended_success_keys:
        marker_commit = success.get("git_commit")
        if (
            not isinstance(marker_commit, str)
            or _HISTORICAL_GIT_SHA_RE.fullmatch(marker_commit) is None
            or not expected_ingestion_producing_git_commit.startswith(marker_commit)
            or success.get("source_bytes")
            != sum(
                record.file_size_bytes
                for record in stage00.source_inventory_bundle.records
            )
            or success.get("staging_bytes") != total_parquet_bytes
        ):
            _fail(
                "PHASE02_SUCCESS_MISMATCH",
                "accepted Stage 1 ingestion success evidence differs",
            )

    state_path = run_dir / INGESTION_STATE_NAME
    state_identity, state_snapshot = _artifact_identity(
        state_path, INGESTION_STATE_NAME
    )
    if state_snapshot.mode != 0o600:
        _fail(
            "PERMISSION_FAILURE",
            "accepted Stage 1 ingestion state store is not owner-only",
        )
    _validate_stage01_state(
        state_path,
        ordered_sources,
        run_id=expected_ingestion_run_id,
        source_inventory_manifest_sha256=stage00.source_inventory_manifest_sha256,
        configuration_fingerprint=cast(str, manifest["configuration_fingerprint"]),
        implementation_fingerprint=cast(str, manifest["implementation_fingerprint"]),
        manifest_files=manifest_files,
    )

    reports, report_snapshots, run = _validate_stage01_reports(
        ingestion_reports_directory,
        run_id=expected_ingestion_run_id,
        producing_git_commit=expected_ingestion_producing_git_commit,
        stage00=stage00,
        manifest=manifest,
        manifest_files=manifest_files,
        total_parquet_bytes=total_parquet_bytes,
    )
    reports_topology = _directory_topology(ingestion_reports_directory)
    expected_reports_topology = tuple(sorted((name, "file") for name in REPORT_NAMES))
    if reports_topology != expected_reports_topology:
        _fail(
            "PHASE02_REPORT_TOPOLOGY_MISMATCH",
            "accepted Stage 1 ingestion report artifact set differs",
        )
    logical_digest = stage01_logical_dataset_sha256_v1(
        ordered_sources,
        stage00_source_population_sha256_v1=stage00.source_population_sha256_v1,
        stage00_scientific_inventory_sha256_v1=stage00.scientific_inventory_sha256_v1,
        stage00_parser_contract_fingerprint=stage00.parser_contract_fingerprint,
        arrow_schema_fingerprint=cast(str, manifest["schema_fingerprint"]),
    )
    snapshots = (
        (stage00_snapshot, manifest_snapshot, success_snapshot, state_snapshot)
        + work_snapshots
        + tuple(shard_snapshots)
        + report_snapshots
    )
    return ValidatedStage01Bundle(
        run_directory=run_dir,
        reports_directory=ingestion_reports_directory.resolve(),
        run_id=expected_ingestion_run_id,
        producing_git_commit=expected_ingestion_producing_git_commit,
        stage00=stage00,
        sources=ordered_sources,
        schema_fingerprint=cast(str, manifest["schema_fingerprint"]),
        configuration_fingerprint=cast(str, manifest["configuration_fingerprint"]),
        implementation_fingerprint=cast(str, manifest["implementation_fingerprint"]),
        logical_dataset_sha256_v1=logical_digest,
        source_file_count=len(ordered_sources),
        total_row_count=total_rows,
        total_parquet_bytes=total_parquet_bytes,
        manifest=manifest_identity,
        success_marker=success_identity,
        state_store=state_identity,
        reports=reports,
        shards=tuple(shard_identities),
        snapshots=snapshots,
        run_topology=run_topology,
        data_topology=data_topology,
        work_topology=work_topology,
        in_progress_topology=in_progress_topology,
        reports_topology=reports_topology,
    )


def _verify_snapshots_unchanged(snapshots: Sequence[_FileSnapshot]) -> None:
    for expected in snapshots:
        if _snapshot(expected.path) != expected:
            _fail(
                "BUNDLE_CHANGED_DURING_ADOPTION",
                "accepted Stage 1 ingestion bundle changed before adoption",
            )


def _verify_bundle_topology_unchanged(bundle: ValidatedStage01Bundle) -> None:
    run_dir = bundle.run_directory
    _verify_directory_mode(run_dir, 0o700, "PERMISSION_FAILURE")
    _verify_directory_mode(run_dir / "data", 0o700, "PERMISSION_FAILURE")
    if _directory_topology(run_dir) != bundle.run_topology:
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "accepted Stage 1 ingestion run topology changed",
        )
    if _directory_topology(run_dir / "data", protected=True) != bundle.data_topology:
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "accepted Stage 1 ingestion data topology changed",
        )
    if (
        _directory_topology(run_dir / "_work", recursive=True, protected=True)
        != bundle.work_topology
    ):
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "accepted Stage 1 ingestion work topology changed",
        )
    if (
        _directory_topology(run_dir / ".in_progress", recursive=True, protected=True)
        != bundle.in_progress_topology
    ):
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "accepted Stage 1 ingestion progress topology changed",
        )
    if _directory_topology(bundle.reports_directory) != bundle.reports_topology:
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "accepted Stage 1 ingestion report topology changed",
        )


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_adoption_record(
    bundle: ValidatedStage01Bundle,
    *,
    adopting_git_commit: str,
    adopting_git_dirty: bool,
    adoption_timestamp_utc: str,
    operational_metadata: Mapping[str, str] | None,
) -> dict[str, Any]:
    if _FULL_GIT_SHA_RE.fullmatch(adopting_git_commit) is None:
        _fail("INVALID_GIT_COMMIT", "Adopting Git commit is not a full SHA")
    provenance: dict[str, Any] = {
        "phase02_producing_git_commit": bundle.producing_git_commit,
        "adopting_git_commit": adopting_git_commit,
        "adopting_git_dirty": adopting_git_dirty,
        "adoption_timestamp_utc": adoption_timestamp_utc,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "pyarrow_version": pyarrow.__version__,
        "duckdb_version": duckdb.__version__,
        "sqlite_version": sqlite3.sqlite_version,
        "platform": sys.platform,
    }
    if operational_metadata:
        provenance["additional"] = dict(operational_metadata)
    return {
        "stage01_contract_version": STAGE01_CONTRACT_VERSION,
        "validation_contract_version": STAGE01_VALIDATION_CONTRACT_VERSION,
        "status": STAGE01_IMPLEMENTATION_STATUS,
        "scientific_identity": {
            "stage00_contract_version": STAGE00_CONTRACT_VERSION,
            "stage00_adoption_record_sha256": bundle.stage00.adoption_record.sha256,
            "stage00_source_population_sha256_v1": (
                bundle.stage00.source_population_sha256_v1
            ),
            "stage00_scientific_inventory_sha256_v1": (
                bundle.stage00.scientific_inventory_sha256_v1
            ),
            "stage00_parser_contract_fingerprint": (
                bundle.stage00.parser_contract_fingerprint
            ),
            "phase01_run_id": bundle.stage00.source_inventory_bundle.run_id,
            "phase01_inventory_version": bundle.stage00.source_inventory_bundle.inventory_version,
            "phase01_input_manifest_sha256": (
                bundle.stage00.source_inventory_manifest_sha256
            ),
            "phase02_staging_version": STAGING_VERSION,
            "source_schema_version": SOURCE_SCHEMA_VERSION,
            "parser_version": PARSER_VERSION,
            "arrow_schema_fingerprint": bundle.schema_fingerprint,
            "stable_source_row_id_version": STABLE_ROW_ID_VERSION,
            "raw_semantic_digest_version": SEMANTIC_DIGEST_VERSION,
            "source_file_count": bundle.source_file_count,
            "total_row_count": bundle.total_row_count,
            "stage01_logical_dataset_sha256_v1": bundle.logical_dataset_sha256_v1,
        },
        "physical_bundle_identity": {
            "phase02_run_id": bundle.run_id,
            "dataset_manifest": bundle.manifest.to_dict(),
            "success_marker": bundle.success_marker.to_dict(),
            "state_store": bundle.state_store.to_dict(),
            "reports": [item.to_dict() for item in bundle.reports],
            "physical_shard_count": len(bundle.shards),
            "total_parquet_bytes": bundle.total_parquet_bytes,
            "shard_identities_reference": (
                "dataset_manifest.json files[].output_file/output_size_bytes/output_sha256"
            ),
            "configuration_fingerprint": bundle.configuration_fingerprint,
            "implementation_fingerprint": bundle.implementation_fingerprint,
        },
        "provenance": provenance,
        "validation": {
            "acceptance_state": STAGE01_IMPLEMENTATION_STATUS,
            "stage00_binding": "PASS",
            "phase01_source_projection": "PASS",
            "phase02_terminal_state": "PASS",
            "artifact_integrity": "PASS",
            "shard_set": "PASS",
            "shard_sha256": "PASS",
            "parquet_schema_and_metadata": "PASS",
            "source_staging_semantic_digests": "PASS",
            "stable_source_row_id_contract": "PASS",
            "global_stable_source_row_id_uniqueness": "PASS",
            "page_checksum_evidence": "PASS",
            "reconciliation": "PASS",
            "state_integrity": "PASS",
            "state_manifest_reconciliation": "PASS",
            "wal_checkpoint_state": "PASS",
            "directory_topology": "PASS",
            "permissions": "PASS",
            "bundle_stability": "PASS",
            "source_csv_access": "NOT_PERFORMED",
            "parquet_rewrite": "NOT_PERFORMED",
        },
    }


def _write_owner_only_adoption_directory(
    output_directory: Path, record: Mapping[str, Any]
) -> Path:
    if output_directory.exists() or output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 1 adoption output already exists")
    parent = output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        _fail("UNSAFE_OUTPUT_PATH", "Stage 1 output parent is unsafe")
    parent.chmod(0o700)
    temporary = parent / f".{output_directory.name}.tmp"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 1 temporary output already exists")
    temporary.mkdir(mode=0o700)
    temporary.chmod(0o700)
    record_path = temporary / STAGE01_ADOPTION_RECORD_NAME
    try:
        descriptor = os.open(record_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        record_path.chmod(0o600)
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
    except BaseException:
        if temporary.exists() and not temporary.is_symlink():
            shutil.rmtree(temporary)
        raise
    return output_directory / STAGE01_ADOPTION_RECORD_NAME


def adopt_stage01_bundle(
    ingestion_run_directory: Path,
    ingestion_reports_directory: Path,
    source_inventory_run_directory: Path,
    stage00_adoption_record_path: Path,
    output_directory: Path,
    *,
    expected_stage00_adoption_sha256: str,
    expected_source_population_sha256: str,
    expected_scientific_inventory_sha256: str,
    expected_parser_contract_fingerprint: str,
    expected_ingestion_run_id: str,
    expected_ingestion_producing_git_commit: str,
    adopting_git_commit: str,
    adopting_git_dirty: bool,
    production: bool,
    adoption_timestamp_utc: str | None = None,
    operational_metadata: Mapping[str, str] | None = None,
) -> Stage01AdoptionOutcome:
    """Validate and adopt accepted Stage 1 ingestion without reading source CSV or rewriting Parquet."""
    bundle = validate_stage01_bundle(
        ingestion_run_directory,
        ingestion_reports_directory,
        source_inventory_run_directory,
        stage00_adoption_record_path,
        expected_stage00_adoption_sha256=expected_stage00_adoption_sha256,
        expected_source_population_sha256=expected_source_population_sha256,
        expected_scientific_inventory_sha256=expected_scientific_inventory_sha256,
        expected_parser_contract_fingerprint=expected_parser_contract_fingerprint,
        expected_ingestion_run_id=expected_ingestion_run_id,
        expected_ingestion_producing_git_commit=expected_ingestion_producing_git_commit,
        production=production,
    )
    record = _build_adoption_record(
        bundle,
        adopting_git_commit=adopting_git_commit,
        adopting_git_dirty=adopting_git_dirty,
        adoption_timestamp_utc=adoption_timestamp_utc or _utc_now_text(),
        operational_metadata=operational_metadata,
    )
    _verify_snapshots_unchanged(bundle.snapshots)
    _verify_bundle_topology_unchanged(bundle)
    record_path = _write_owner_only_adoption_directory(output_directory, record)
    return Stage01AdoptionOutcome(
        output_directory=output_directory.resolve(),
        adoption_record_path=record_path.resolve(),
        adoption_record_sha256=_sha256_file(record_path),
        bundle=bundle,
    )


__all__ = [
    "STAGE01_ADOPTION_RECORD_NAME",
    "STAGE01_CONTRACT_VERSION",
    "STAGE01_IMPLEMENTATION_STATUS",
    "STAGE01_LOGICAL_DATASET_DOMAIN",
    "STAGE01_VALIDATION_CONTRACT_VERSION",
    "Stage00Binding",
    "Stage01AdoptionOutcome",
    "Stage01SourceRecord",
    "Stage01ValidationError",
    "ValidatedStage01Bundle",
    "adopt_stage01_bundle",
    "stage01_logical_dataset_sha256_v1",
    "validate_stage01_bundle",
    "validate_stage00_binding",
    "resolve_stage00_binding",
]

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import struct
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from ...phase01.config import DEFAULT_PARSER_FIELD_LIMIT_CHARS, InventoryConfig
from ...phase01.constants import INVENTORY_VERSION, REPORT_NAMES
from ...phase01.reports import MANIFEST_COLUMNS
from ...phase01.runner import TERMINAL_MARKER_TEXT, InventoryOutcome, run_inventory
from ...raw_csv import (
    CSV_DELIMITER,
    CSV_DOUBLEQUOTE,
    CSV_ESCAPE_CHARACTER,
    CSV_NEWLINE,
    CSV_QUOTE_CHARACTER,
    CSV_SKIP_INITIAL_SPACE,
    CSV_STRICT,
    SOURCE_COLUMNS,
    SOURCE_ENCODING_POLICY,
    SOURCE_SCHEMA_FINGERPRINT_SEPARATOR,
    SOURCE_SCHEMA_FINGERPRINT_VERSION,
    SOURCE_TEXT_ENCODING,
    SOURCE_TEXT_ENCODING_WITH_BOM,
    SOURCE_TEXT_ERRORS,
    UTF8_BOM_BYTES,
    source_schema_fingerprint,
)

STAGE00_CONTRACT_VERSION = "stage00_inventory_contract_v1"
STAGE00_VALIDATION_CONTRACT_VERSION = "stage00_bundle_validation_v1"
STAGE00_IMPLEMENTATION_STATUS = "STAGE_0_ACCEPTED"
SOURCE_POPULATION_DOMAIN = b"SAFE_STAGE00_SOURCE_POPULATION_V1"
SCIENTIFIC_INVENTORY_DOMAIN = b"SAFE_STAGE00_SCIENTIFIC_INVENTORY_V1"
PARSER_CONTRACT_DOMAIN = b"SAFE_STAGE00_PARSER_CONTRACT_V1"
ADOPTION_RECORD_NAME = "stage00_adoption.json"
PHASE01_SUCCESS_MARKER = "_SCOPE_PASS"
PHASE01_FAILURE_MARKER = "_SCOPE_FAIL"
PHASE01_IN_PROGRESS_MARKER = "_IN_PROGRESS"
PHASE01_DISCOVERY_MODE = "DIRECT_CSV_CHILDREN_NON_RECURSIVE_NO_SYMLINKS"

_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNSIGNED_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)$")
_FULL_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_HISTORICAL_GIT_SHA_RE = re.compile(r"^[0-9a-f]{8,40}$")


class Stage00ValidationError(RuntimeError):
    """Fail-closed Stage 0 validation error without protected row values."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class Stage00InventoryRecord:
    file_id: int
    relative_path: str
    file_size_bytes: int
    file_sha256: str
    source_stable_during_scan: bool
    encoding_status: str
    bom_type: str
    header_present: bool
    observed_column_count: int
    schema_fingerprint: str
    schema_matches_contract: bool
    logical_record_count: int
    valid_schema_record_count: int
    wrong_column_count_record_count: int
    parser_error_count: int
    multiline_record_count: int
    counts_complete: bool
    scan_status: str
    duplicate_file_group: str | None
    duplicate_file_group_size: int
    max_record_length_chars: int
    max_field_length_chars: int


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ValidatedPhase01Bundle:
    run_dir: Path
    run_id: str
    inventory_version: str
    producing_git_commit: str
    records: tuple[Stage00InventoryRecord, ...]
    artifacts: tuple[ArtifactIdentity, ...]
    success_marker: ArtifactIdentity
    parser_contract_fingerprint: str
    source_population_sha256_v1: str
    stage00_scientific_inventory_sha256_v1: str


@dataclass(frozen=True, slots=True)
class PermissionHardeningResult:
    work_state_present: bool
    directories_hardened: int
    files_hardened: int


@dataclass(frozen=True, slots=True)
class Stage00AdoptionOutcome:
    output_directory: Path
    adoption_record_path: Path
    adoption_record_sha256: str
    bundle: ValidatedPhase01Bundle
    permissions: PermissionHardeningResult


class _CanonicalEncoder:
    def __init__(self, digest: Any) -> None:
        self._digest = digest

    def uint64(self, value: int) -> None:
        if isinstance(value, bool) or not 0 <= value <= 0xFFFFFFFFFFFFFFFF:
            raise Stage00ValidationError(
                "INVALID_UNSIGNED_INTEGER", "Canonical integer is outside uint64"
            )
        self._digest.update(struct.pack(">Q", value))

    def boolean(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise Stage00ValidationError(
                "INVALID_BOOLEAN", "Canonical Boolean has an invalid type"
            )
        self._digest.update(b"\x01" if value else b"\x00")

    def text(self, value: str) -> None:
        if not isinstance(value, str) or "\x00" in value:
            raise Stage00ValidationError(
                "INVALID_TEXT", "Canonical text is invalid or contains NUL"
            )
        encoded = value.encode("utf-8", errors="strict")
        self.uint64(len(encoded))
        self._digest.update(encoded)

    def nullable_text(self, value: str | None) -> None:
        if value is None:
            self._digest.update(b"\x00")
            return
        self._digest.update(b"\x01")
        self.text(value)

    def digest(self, value: str) -> None:
        self._digest.update(_digest_bytes(value))

    def byte_string(self, value: bytes) -> None:
        if not isinstance(value, bytes):
            raise Stage00ValidationError(
                "INVALID_BYTES", "Canonical byte string has an invalid type"
            )
        self.uint64(len(value))
        self._digest.update(value)


def _fail(code: str, message: str) -> NoReturn:
    raise Stage00ValidationError(code, message)


def _digest_bytes(value: str) -> bytes:
    if not isinstance(value, str) or _LOWER_SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_SHA256", "Digest must be 64 lowercase hexadecimal characters")
    return bytes.fromhex(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path: Path, code: str) -> None:
    if path.is_symlink() or not path.is_file():
        _fail(code, "Required bundle member is not a regular non-symlink file")


def _direct_relative_csv(value: str) -> None:
    if not isinstance(value, str) or "\x00" in value:
        _fail("INVALID_RELATIVE_PATH", "Inventory path is not canonical text")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) != 1
        or candidate.name != value
        or candidate.suffix.lower() != ".csv"
        or value in {".", ".."}
    ):
        _fail(
            "INVALID_RELATIVE_PATH", "Inventory path violates the direct CSV contract"
        )


def _canonical_records(
    records: Sequence[Stage00InventoryRecord],
) -> tuple[Stage00InventoryRecord, ...]:
    ordered = tuple(sorted(records, key=lambda item: item.relative_path))
    seen: set[str] = set()
    duplicate_groups: dict[str, list[Stage00InventoryRecord]] = {}
    for expected_file_id, record in enumerate(ordered, start=1):
        _direct_relative_csv(record.relative_path)
        if record.relative_path in seen:
            _fail(
                "DUPLICATE_RELATIVE_PATH",
                "Inventory contains a duplicate relative path",
            )
        seen.add(record.relative_path)
        if isinstance(record.file_id, bool) or record.file_id != expected_file_id:
            _fail(
                "INVALID_FILE_ID",
                "Inventory file ID does not follow sorted path order",
            )
        for value in (
            record.file_size_bytes,
            record.observed_column_count,
            record.logical_record_count,
            record.valid_schema_record_count,
            record.wrong_column_count_record_count,
            record.parser_error_count,
            record.multiline_record_count,
            record.duplicate_file_group_size,
            record.max_record_length_chars,
            record.max_field_length_chars,
        ):
            if isinstance(value, bool) or value < 0 or value > 0xFFFFFFFFFFFFFFFF:
                _fail(
                    "INVALID_INVENTORY_INTEGER", "Inventory integer is outside uint64"
                )
        _digest_bytes(record.file_sha256)
        _digest_bytes(record.schema_fingerprint)
        if record.encoding_status not in {"UTF8_VALID", "UTF8_INVALID", "UNKNOWN"}:
            _fail("INVALID_ENCODING_STATUS", "Inventory encoding status is unknown")
        if record.bom_type not in {"NONE", "UTF8"}:
            _fail("INVALID_BOM_TYPE", "Inventory BOM type is unknown")
        if record.scan_status not in {"COMPLETE", "FAILED", "PENDING", "SCANNING"}:
            _fail("INVALID_SCAN_STATUS", "Inventory scan status is unknown")
        if record.duplicate_file_group is None:
            if record.duplicate_file_group_size != 0:
                _fail(
                    "INVALID_DUPLICATE_GROUP",
                    "Empty duplicate group has a nonzero size",
                )
        elif record.duplicate_file_group == "" or record.duplicate_file_group_size < 2:
            _fail("INVALID_DUPLICATE_GROUP", "Duplicate group identity is inconsistent")
        else:
            duplicate_groups.setdefault(record.duplicate_file_group, []).append(record)
    for group in duplicate_groups.values():
        if (
            len(group) != group[0].duplicate_file_group_size
            or len({(item.file_size_bytes, item.file_sha256) for item in group}) != 1
            or any(item.duplicate_file_group_size != len(group) for item in group)
        ):
            _fail("INVALID_DUPLICATE_GROUP", "Duplicate file group is inconsistent")
    return ordered


def source_population_sha256_v1(records: Sequence[Stage00InventoryRecord]) -> str:
    """Hash exact source identities using the Stage 0 v1 binary contract."""
    ordered = _canonical_records(records)
    digest = hashlib.sha256()
    digest.update(SOURCE_POPULATION_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.uint64(len(ordered))
    for record in ordered:
        encoder.text(record.relative_path)
        encoder.uint64(record.file_size_bytes)
        encoder.digest(record.file_sha256)
    return digest.hexdigest()


def parser_contract_fingerprint_v1(
    *, parser_field_limit_chars: int = DEFAULT_PARSER_FIELD_LIMIT_CHARS
) -> str:
    """Hash the exact Stage 0 parser interpretation contract."""
    digest = hashlib.sha256()
    digest.update(PARSER_CONTRACT_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(INVENTORY_VERSION)
    encoder.uint64(len(SOURCE_COLUMNS))
    for column in SOURCE_COLUMNS:
        encoder.text(column)
    encoder.text(SOURCE_ENCODING_POLICY)
    encoder.text(SOURCE_TEXT_ENCODING)
    encoder.text(SOURCE_TEXT_ENCODING_WITH_BOM)
    encoder.text(SOURCE_TEXT_ERRORS)
    encoder.byte_string(UTF8_BOM_BYTES)
    encoder.text(SOURCE_SCHEMA_FINGERPRINT_VERSION)
    encoder.text(SOURCE_SCHEMA_FINGERPRINT_SEPARATOR)
    encoder.text(CSV_NEWLINE)
    encoder.text(CSV_DELIMITER)
    encoder.text(CSV_QUOTE_CHARACTER)
    encoder.boolean(CSV_DOUBLEQUOTE)
    encoder.nullable_text(CSV_ESCAPE_CHARACTER)
    encoder.boolean(CSV_SKIP_INITIAL_SPACE)
    encoder.boolean(CSV_STRICT)
    encoder.uint64(parser_field_limit_chars)
    return digest.hexdigest()


def stage00_scientific_inventory_sha256_v1(
    records: Sequence[Stage00InventoryRecord],
    *,
    parser_contract_fingerprint: str | None = None,
    source_population_fingerprint: str | None = None,
) -> str:
    """Hash the deterministic Stage 0 inventory projection."""
    ordered = _canonical_records(records)
    parser_digest = (
        parser_contract_fingerprint_v1()
        if parser_contract_fingerprint is None
        else parser_contract_fingerprint
    )
    source_digest = (
        source_population_sha256_v1(ordered)
        if source_population_fingerprint is None
        else source_population_fingerprint
    )
    digest = hashlib.sha256()
    digest.update(SCIENTIFIC_INVENTORY_DOMAIN)
    encoder = _CanonicalEncoder(digest)
    encoder.text(STAGE00_CONTRACT_VERSION)
    encoder.text(INVENTORY_VERSION)
    encoder.digest(parser_digest)
    encoder.digest(source_digest)
    encoder.uint64(len(ordered))
    for record in ordered:
        encoder.uint64(record.file_id)
        encoder.text(record.relative_path)
        encoder.uint64(record.file_size_bytes)
        encoder.digest(record.file_sha256)
        encoder.boolean(record.source_stable_during_scan)
        encoder.text(record.encoding_status)
        encoder.text(record.bom_type)
        encoder.boolean(record.header_present)
        encoder.uint64(record.observed_column_count)
        encoder.digest(record.schema_fingerprint)
        encoder.boolean(record.schema_matches_contract)
        encoder.uint64(record.logical_record_count)
        encoder.uint64(record.valid_schema_record_count)
        encoder.uint64(record.wrong_column_count_record_count)
        encoder.uint64(record.parser_error_count)
        encoder.uint64(record.multiline_record_count)
        encoder.boolean(record.counts_complete)
        encoder.text(record.scan_status)
        encoder.nullable_text(record.duplicate_file_group)
        encoder.uint64(record.duplicate_file_group_size)
        encoder.uint64(record.max_record_length_chars)
        encoder.uint64(record.max_field_length_chars)
    return digest.hexdigest()


def _required_text(row: Mapping[str, str], key: str) -> str:
    value = row.get(key, "")
    if value == "":
        _fail("MALFORMED_MANIFEST", "Manifest is missing a required value")
    return value


def _uint_from_text(value: str) -> int:
    if _UNSIGNED_DECIMAL_RE.fullmatch(value) is None:
        _fail(
            "MALFORMED_MANIFEST", "Manifest integer is not canonical unsigned decimal"
        )
    result = int(value)
    if result > 0xFFFFFFFFFFFFFFFF:
        _fail("MALFORMED_MANIFEST", "Manifest integer exceeds uint64")
    return result


def _bool_from_text(value: str) -> bool:
    if value == "True":
        return True
    if value == "False":
        return False
    _fail("MALFORMED_MANIFEST", "Manifest Boolean is not canonical")


def _load_manifest_unchecked(
    path: Path, run_id: str
) -> tuple[Stage00InventoryRecord, ...]:
    records: list[Stage00InventoryRecord] = []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != MANIFEST_COLUMNS:
            _fail("MANIFEST_SCHEMA_MISMATCH", "Phase 1 manifest columns are not exact")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                _fail(
                    "MALFORMED_MANIFEST",
                    "Manifest row width does not match its declared schema",
                )
            if row.get("run_id") != run_id:
                _fail("MANIFEST_RUN_ID_MISMATCH", "Manifest row has a different run ID")
            relative_path = _required_text(row, "relative_path")
            if _required_text(row, "file_name") != relative_path:
                _fail("SOURCE_POPULATION_MISMATCH", "Manifest filename is inconsistent")
            if (
                row.get("delimiter") != CSV_DELIMITER
                or row.get("quote_character") != CSV_QUOTE_CHARACTER
                or _bool_from_text(_required_text(row, "doublequote"))
                != CSV_DOUBLEQUOTE
                or row.get("escape_character", "") != (CSV_ESCAPE_CHARACTER or "")
            ):
                _fail(
                    "PARSER_CONTRACT_MISMATCH",
                    "Manifest parser contract is inconsistent",
                )
            before_size = _uint_from_text(_required_text(row, "size_bytes_before"))
            after_parse_size = _uint_from_text(
                _required_text(row, "size_bytes_after_parse")
            )
            after_hash_size = _uint_from_text(
                _required_text(row, "size_bytes_after_hash")
            )
            if len({before_size, after_parse_size, after_hash_size}) != 1:
                _fail(
                    "SOURCE_STABILITY_MISMATCH",
                    "Recorded source sizes are inconsistent",
                )
            duplicate_group = row.get("duplicate_file_group", "") or None
            duplicate_method = row.get("duplicate_verification_method", "")
            if (duplicate_group is None and duplicate_method != "") or (
                duplicate_group is not None and duplicate_method != "SIZE_AND_SHA256"
            ):
                _fail(
                    "INVALID_DUPLICATE_GROUP",
                    "Duplicate verification method is inconsistent",
                )
            records.append(
                Stage00InventoryRecord(
                    file_id=_uint_from_text(_required_text(row, "file_id")),
                    relative_path=relative_path,
                    file_size_bytes=after_hash_size,
                    file_sha256=_required_text(row, "sha256"),
                    source_stable_during_scan=not _bool_from_text(
                        _required_text(row, "file_changed_during_scan")
                    ),
                    encoding_status=_required_text(row, "encoding_status"),
                    bom_type=_required_text(row, "bom_type"),
                    header_present=_bool_from_text(
                        _required_text(row, "header_present")
                    ),
                    observed_column_count=_uint_from_text(
                        _required_text(row, "observed_column_count")
                    ),
                    schema_fingerprint=_required_text(row, "schema_fingerprint"),
                    schema_matches_contract=_bool_from_text(
                        _required_text(row, "schema_matches_expected")
                    ),
                    logical_record_count=_uint_from_text(
                        _required_text(row, "logical_record_count")
                    ),
                    valid_schema_record_count=_uint_from_text(
                        _required_text(row, "valid_schema_record_count")
                    ),
                    wrong_column_count_record_count=_uint_from_text(
                        _required_text(row, "wrong_column_count_record_count")
                    ),
                    parser_error_count=_uint_from_text(
                        _required_text(row, "parser_error_count")
                    ),
                    multiline_record_count=_uint_from_text(
                        _required_text(row, "multiline_record_count")
                    ),
                    counts_complete=_bool_from_text(
                        _required_text(row, "counts_complete")
                    ),
                    scan_status=_required_text(row, "scan_status"),
                    duplicate_file_group=duplicate_group,
                    duplicate_file_group_size=_uint_from_text(
                        row.get("duplicate_file_group_size", "") or "0"
                    ),
                    max_record_length_chars=_uint_from_text(
                        _required_text(row, "max_record_length_chars")
                    ),
                    max_field_length_chars=_uint_from_text(
                        _required_text(row, "max_field_length_chars")
                    ),
                )
            )
    path_ordered = tuple(sorted(records, key=lambda item: item.relative_path))
    if tuple(records) != path_ordered:
        _fail(
            "MANIFEST_ORDER_MISMATCH",
            "Manifest rows are not in deterministic path order",
        )
    ordered = _canonical_records(records)
    if [record.file_id for record in records] != list(range(1, len(records) + 1)):
        _fail("FILE_ID_CONTRACT_MISMATCH", "Manifest file IDs are not sequential")
    return ordered


def _load_manifest(path: Path, run_id: str) -> tuple[Stage00InventoryRecord, ...]:
    try:
        return _load_manifest_unchecked(path, run_id)
    except Stage00ValidationError:
        raise
    except (OSError, UnicodeError, csv.Error, TypeError, ValueError) as error:
        raise Stage00ValidationError(
            "MALFORMED_MANIFEST", "Phase 1 manifest cannot be interpreted safely"
        ) from error


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage00ValidationError(
            "MALFORMED_RUN_METADATA", "Phase 1 run metadata cannot be read"
        ) from error
    if not isinstance(value, dict):
        _fail("MALFORMED_RUN_METADATA", "Phase 1 run metadata is not an object")
    return cast(dict[str, Any], value)


def _expected_parser_configuration() -> dict[str, Any]:
    return {
        "encoding": SOURCE_ENCODING_POLICY,
        "newline": CSV_NEWLINE,
        "delimiter": CSV_DELIMITER,
        "quotechar": CSV_QUOTE_CHARACTER,
        "doublequote": CSV_DOUBLEQUOTE,
        "escapechar": CSV_ESCAPE_CHARACTER,
        "skipinitialspace": CSV_SKIP_INITIAL_SPACE,
        "strict": CSV_STRICT,
    }


def _artifact_identity(path: Path, relative_path: str) -> ArtifactIdentity:
    _require_regular_file(path, "MISSING_OR_UNSAFE_ARTIFACT")
    before = path.stat()
    sha256 = _sha256_file(path)
    after = path.stat()
    stable_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    if stable_identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        _fail(
            "BUNDLE_CHANGED_DURING_VALIDATION",
            "Phase 1 artifact changed while Stage 0 validation was in progress",
        )
    return ArtifactIdentity(relative_path, after.st_size, sha256)


def validate_phase01_bundle(
    run_dir: Path,
    *,
    expected_file_count: int,
    expected_producing_git_commit: str,
) -> ValidatedPhase01Bundle:
    """Validate and project a completed Phase 1 bundle without source access."""
    if run_dir.is_symlink() or not run_dir.is_dir():
        _fail("INVALID_BUNDLE_DIRECTORY", "Phase 1 bundle is not a regular directory")
    if _FULL_GIT_SHA_RE.fullmatch(expected_producing_git_commit) is None:
        _fail("INVALID_GIT_COMMIT", "Expected producing Git commit is not a full SHA")
    if isinstance(expected_file_count, bool) or expected_file_count < 1:
        _fail("INVALID_POPULATION_CONTRACT", "Expected file count must be positive")

    in_progress = run_dir / PHASE01_IN_PROGRESS_MARKER
    failure_marker = run_dir / PHASE01_FAILURE_MARKER
    success_marker_path = run_dir / PHASE01_SUCCESS_MARKER
    if in_progress.exists() or in_progress.is_symlink():
        _fail("BUNDLE_IN_PROGRESS", "Phase 1 bundle still has an in-progress marker")
    if failure_marker.exists() or failure_marker.is_symlink():
        _fail("INCONSISTENT_TERMINAL_STATE", "Phase 1 bundle has a failure marker")
    _require_regular_file(success_marker_path, "MISSING_SUCCESS_MARKER")
    if success_marker_path.read_bytes() != TERMINAL_MARKER_TEXT.encode("utf-8"):
        _fail(
            "INCONSISTENT_TERMINAL_STATE",
            "Phase 1 success marker content is not canonical",
        )

    artifact_paths = {name: run_dir / name for name in REPORT_NAMES}
    for path in artifact_paths.values():
        _require_regular_file(path, "MISSING_OR_UNSAFE_ARTIFACT")
    run_path = artifact_paths["phase01_run.json"]
    run = _load_json_object(run_path)
    required_run_values = {
        "inventory_version": INVENTORY_VERSION,
        "status": "COMPLETED_SCOPE_PASS",
        "scope_gate": "PASS",
        "phase01_completion_gate": "PASS",
        "run_scope": "FULL_INVENTORY",
        "discovery_mode": PHASE01_DISCOVERY_MODE,
        "files_discovered": expected_file_count,
        "git_dirty": False,
    }
    for key, expected in required_run_values.items():
        if run.get(key) != expected:
            _fail(
                "PHASE01_GATE_MISMATCH",
                "Phase 1 run metadata does not satisfy adoption",
            )
    run_id_value = run.get("run_id")
    if not isinstance(run_id_value, str) or run_id_value != run_dir.name:
        _fail("PHASE01_RUN_ID_MISMATCH", "Phase 1 run identity is inconsistent")
    run_id = run_id_value
    producing_commit = run.get("git_commit")
    if (
        not isinstance(producing_commit, str)
        or _HISTORICAL_GIT_SHA_RE.fullmatch(producing_commit) is None
        or not expected_producing_git_commit.startswith(producing_commit)
    ):
        _fail("PRODUCING_COMMIT_MISMATCH", "Phase 1 producing commit is inconsistent")
    if run.get("parser_configuration") != _expected_parser_configuration():
        _fail(
            "PARSER_CONTRACT_MISMATCH", "Phase 1 parser configuration is not approved"
        )
    if run.get("parser_limits") != {
        "field_limit_chars": DEFAULT_PARSER_FIELD_LIMIT_CHARS
    }:
        _fail("PARSER_CONTRACT_MISMATCH", "Phase 1 parser limits are not approved")

    output_files_value = run.get("output_files")
    expected_output_names = set(REPORT_NAMES) - {"phase01_run.json"}
    if (
        not isinstance(output_files_value, dict)
        or set(output_files_value) != expected_output_names
    ):
        _fail("ARTIFACT_SET_MISMATCH", "Phase 1 artifact set is not exact")
    output_files = cast(dict[str, Any], output_files_value)
    artifacts: list[ArtifactIdentity] = []
    for name in REPORT_NAMES:
        identity = _artifact_identity(artifact_paths[name], name)
        artifacts.append(identity)
        if name == "phase01_run.json":
            continue
        expected_identity = output_files.get(name)
        if not isinstance(expected_identity, dict):
            _fail("ARTIFACT_SET_MISMATCH", "Phase 1 artifact metadata is malformed")
        if (
            expected_identity.get("size_bytes") != identity.size_bytes
            or expected_identity.get("sha256") != identity.sha256
        ):
            _fail(
                "ARTIFACT_INTEGRITY_MISMATCH",
                "Phase 1 artifact identity does not match",
            )

    records = _load_manifest(artifact_paths["phase01_file_manifest.csv"], run_id)
    if len(records) != expected_file_count:
        _fail("SOURCE_POPULATION_MISMATCH", "Inventory file count is not approved")
    ordered_paths = [record.relative_path for record in records]
    if [record.file_id for record in records] != list(range(1, len(records) + 1)):
        _fail("FILE_ID_CONTRACT_MISMATCH", "File IDs do not follow sorted source order")
    if run.get("approved_input_files") != ordered_paths:
        _fail(
            "SOURCE_POPULATION_MISMATCH", "Approved input paths differ from inventory"
        )
    if run.get("total_size_bytes") != sum(record.file_size_bytes for record in records):
        _fail("SOURCE_POPULATION_MISMATCH", "Source byte total differs from inventory")

    expected_schema_fingerprint = source_schema_fingerprint(SOURCE_COLUMNS)
    for record in records:
        if (
            not record.source_stable_during_scan
            or record.encoding_status != "UTF8_VALID"
            or not record.header_present
            or record.observed_column_count != len(SOURCE_COLUMNS)
            or record.schema_fingerprint != expected_schema_fingerprint
            or not record.schema_matches_contract
            or record.valid_schema_record_count != record.logical_record_count
            or record.wrong_column_count_record_count != 0
            or record.parser_error_count != 0
            or not record.counts_complete
            or record.scan_status != "COMPLETE"
        ):
            _fail(
                "UNSUCCESSFUL_INVENTORY_ROW", "A Phase 1 inventory row is not complete"
            )

    parser_fingerprint = parser_contract_fingerprint_v1()
    source_fingerprint = source_population_sha256_v1(records)
    scientific_fingerprint = stage00_scientific_inventory_sha256_v1(
        records,
        parser_contract_fingerprint=parser_fingerprint,
        source_population_fingerprint=source_fingerprint,
    )
    return ValidatedPhase01Bundle(
        run_dir=run_dir.resolve(),
        run_id=run_id,
        inventory_version=INVENTORY_VERSION,
        producing_git_commit=expected_producing_git_commit,
        records=records,
        artifacts=tuple(artifacts),
        success_marker=_artifact_identity(success_marker_path, PHASE01_SUCCESS_MARKER),
        parser_contract_fingerprint=parser_fingerprint,
        source_population_sha256_v1=source_fingerprint,
        stage00_scientific_inventory_sha256_v1=scientific_fingerprint,
    )


def harden_phase01_work_state(run_dir: Path) -> PermissionHardeningResult:
    """Make retained protected Phase 1 working state owner-only."""
    if run_dir.is_symlink() or not run_dir.is_dir():
        _fail("INVALID_BUNDLE_DIRECTORY", "Phase 1 bundle is not a regular directory")
    work_dir = run_dir / "_work"
    if work_dir.is_symlink():
        _fail("UNSAFE_WORK_STATE", "Phase 1 working state is a symlink")
    if not work_dir.exists():
        return PermissionHardeningResult(False, 0, 0)
    if not work_dir.is_dir():
        _fail("UNSAFE_WORK_STATE", "Phase 1 working state is not a regular directory")

    directories: list[Path] = []
    files: list[Path] = []
    pending = [work_dir]
    try:
        while pending:
            directory = pending.pop()
            if directory.is_symlink() or not directory.is_dir():
                _fail(
                    "UNSAFE_WORK_STATE", "Protected working-state directory is unsafe"
                )
            directories.append(directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if entry.is_symlink():
                        _fail(
                            "UNSAFE_WORK_STATE_SYMLINK",
                            "Protected working state contains a symlink",
                        )
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(path)
                    else:
                        _fail(
                            "UNSAFE_WORK_STATE",
                            "Protected working state contains a special file",
                        )
        for directory in directories:
            if directory.is_symlink() or not directory.is_dir():
                _fail("UNSAFE_WORK_STATE", "Protected working-state directory changed")
            directory.chmod(0o700)
        for path in files:
            if path.is_symlink() or not path.is_file():
                _fail("UNSAFE_WORK_STATE", "Protected working-state file changed")
            path.chmod(0o600)
        verify_phase01_work_state_permissions(run_dir)
    except OSError as error:
        raise Stage00ValidationError(
            "WORK_STATE_PERMISSION_FAILURE",
            "Protected working-state permissions could not be established",
        ) from error
    return PermissionHardeningResult(True, len(directories), len(files))


def verify_phase01_work_state_permissions(run_dir: Path) -> None:
    work_dir = run_dir / "_work"
    if work_dir.is_symlink():
        _fail("UNSAFE_WORK_STATE", "Phase 1 working state is a symlink")
    if not work_dir.exists():
        return
    pending = [work_dir]
    while pending:
        directory = pending.pop()
        if directory.is_symlink() or not directory.is_dir():
            _fail("UNSAFE_WORK_STATE", "Protected working-state directory is unsafe")
        if directory.stat().st_mode & 0o777 != 0o700:
            _fail(
                "WORK_STATE_PERMISSION_FAILURE", "Protected directory is not mode 0700"
            )
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                if entry.is_symlink():
                    _fail(
                        "UNSAFE_WORK_STATE_SYMLINK",
                        "Protected working state contains a symlink",
                    )
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    if path.stat().st_mode & 0o777 != 0o600:
                        _fail(
                            "WORK_STATE_PERMISSION_FAILURE",
                            "Protected file is not mode 0600",
                        )
                else:
                    _fail(
                        "UNSAFE_WORK_STATE",
                        "Protected working state contains a special file",
                    )


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_adoption_record(
    bundle: ValidatedPhase01Bundle,
    permissions: PermissionHardeningResult,
    *,
    adopting_git_commit: str,
    adopting_git_dirty: bool,
    adoption_timestamp_utc: str,
    operational_metadata: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if _FULL_GIT_SHA_RE.fullmatch(adopting_git_commit) is None:
        _fail("INVALID_GIT_COMMIT", "Adopting Git commit is not a full SHA")
    provenance = {
        "adopting_git_commit": adopting_git_commit,
        "adopting_git_dirty": adopting_git_dirty,
        "adoption_timestamp_utc": adoption_timestamp_utc,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "platform": sys.platform,
    }
    if operational_metadata:
        provenance["additional"] = dict(operational_metadata)
    return {
        "stage00_contract_version": STAGE00_CONTRACT_VERSION,
        "validation_contract_version": STAGE00_VALIDATION_CONTRACT_VERSION,
        "status": STAGE00_IMPLEMENTATION_STATUS,
        "identity": {
            "adopted_phase01_run_id": bundle.run_id,
            "phase01_inventory_version": bundle.inventory_version,
            "producing_git_commit": bundle.producing_git_commit,
            "parser_contract_fingerprint": bundle.parser_contract_fingerprint,
            "source_population_sha256_v1": bundle.source_population_sha256_v1,
            "stage00_scientific_inventory_sha256_v1": (
                bundle.stage00_scientific_inventory_sha256_v1
            ),
        },
        "bundle_integrity": {
            "artifacts": [artifact.to_dict() for artifact in bundle.artifacts],
            "terminal_state": {
                "success_marker": bundle.success_marker.to_dict(),
                "failure_marker_present": False,
                "in_progress_marker_present": False,
            },
        },
        "provenance": provenance,
        "permission_hardening": {
            "status": "PASS",
            "work_state_present": permissions.work_state_present,
            "directories_hardened": permissions.directories_hardened,
            "files_hardened": permissions.files_hardened,
            "directory_mode": "0700",
            "file_mode": "0600",
        },
        "validation": {
            "acceptance_status": STAGE00_IMPLEMENTATION_STATUS,
            "artifact_integrity": "PASS",
            "manifest_schema": "PASS",
            "parser_contract": "PASS",
            "per_file_completeness": "PASS",
            "population_contract": "PASS",
            "terminal_state": "PASS",
            "source_file_count": len(bundle.records),
        },
    }


def _write_owner_only_adoption_directory(
    output_directory: Path, record: Mapping[str, Any]
) -> Path:
    if output_directory.exists() or output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 0 adoption output already exists")
    parent = output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if parent.is_symlink() or not parent.is_dir():
        _fail("UNSAFE_OUTPUT_PATH", "Stage 0 output parent is unsafe")
    temporary = parent / f".{output_directory.name}.tmp"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 0 temporary output already exists")
    temporary.mkdir(mode=0o700)
    temporary.chmod(0o700)
    record_path = temporary / ADOPTION_RECORD_NAME
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
    return output_directory / ADOPTION_RECORD_NAME


def adopt_phase01_bundle(
    run_dir: Path,
    output_directory: Path,
    *,
    expected_file_count: int,
    expected_producing_git_commit: str,
    adopting_git_commit: str,
    adopting_git_dirty: bool,
    adoption_timestamp_utc: str | None = None,
    operational_metadata: Mapping[str, str] | None = None,
) -> Stage00AdoptionOutcome:
    """Validate and adopt a Phase 1 bundle without opening source CSV files."""
    bundle = validate_phase01_bundle(
        run_dir,
        expected_file_count=expected_file_count,
        expected_producing_git_commit=expected_producing_git_commit,
    )
    permissions = harden_phase01_work_state(run_dir)
    verified_bundle = validate_phase01_bundle(
        run_dir,
        expected_file_count=expected_file_count,
        expected_producing_git_commit=expected_producing_git_commit,
    )
    if verified_bundle != bundle:
        _fail(
            "BUNDLE_CHANGED_DURING_ADOPTION",
            "Phase 1 bundle changed while Stage 0 adoption was in progress",
        )
    record = _build_adoption_record(
        verified_bundle,
        permissions,
        adopting_git_commit=adopting_git_commit,
        adopting_git_dirty=adopting_git_dirty,
        adoption_timestamp_utc=adoption_timestamp_utc or _utc_now_text(),
        operational_metadata=operational_metadata,
    )
    record_path = _write_owner_only_adoption_directory(output_directory, record)
    return Stage00AdoptionOutcome(
        output_directory=output_directory.resolve(),
        adoption_record_path=record_path.resolve(),
        adoption_record_sha256=_sha256_file(record_path),
        bundle=verified_bundle,
        permissions=permissions,
    )


def run_authoritative_phase01_scan(config: InventoryConfig) -> InventoryOutcome:
    """Delegate any future Stage 0 source scan to the authoritative Phase 1 scanner."""
    return run_inventory(config)


__all__ = [
    "ADOPTION_RECORD_NAME",
    "STAGE00_CONTRACT_VERSION",
    "STAGE00_IMPLEMENTATION_STATUS",
    "STAGE00_VALIDATION_CONTRACT_VERSION",
    "Stage00AdoptionOutcome",
    "Stage00InventoryRecord",
    "Stage00ValidationError",
    "ValidatedPhase01Bundle",
    "adopt_phase01_bundle",
    "harden_phase01_work_state",
    "parser_contract_fingerprint_v1",
    "run_authoritative_phase01_scan",
    "source_population_sha256_v1",
    "stage00_scientific_inventory_sha256_v1",
    "validate_phase01_bundle",
    "verify_phase01_work_state_permissions",
]

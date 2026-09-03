from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ...raw_csv import SOURCE_COLUMNS, source_schema_fingerprint
from .s00_constants import INVENTORY_VERSION

POPULATION_SCOPE_VERSION = "stage00_population_scope_v1"

_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_POPULATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SCOPE_KEYS = {
    "population_scope_version",
    "population_id",
    "phase01_inventory_version",
    "source_schema_fingerprint",
    "parser_field_limit_chars",
    "expected_source_count",
    "relative_paths",
}


@dataclass(frozen=True, slots=True)
class PopulationScope:
    artifact_path: Path
    artifact_size_bytes: int
    artifact_sha256: str
    population_scope_version: str
    population_id: str
    inventory_version: str
    source_schema_fingerprint: str
    parser_field_limit_chars: int
    expected_source_count: int
    relative_paths: tuple[str, ...]

    def provenance(self) -> dict[str, str | int]:
        return {
            "population_scope_version": self.population_scope_version,
            "population_id": self.population_id,
            "population_scope_artifact_sha256": self.artifact_sha256,
            "population_scope_artifact_size_bytes": self.artifact_size_bytes,
            "phase01_inventory_version": self.inventory_version,
            "source_schema_fingerprint": self.source_schema_fingerprint,
            "parser_field_limit_chars": self.parser_field_limit_chars,
            "expected_source_count": self.expected_source_count,
        }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Population scope contains a duplicate JSON key")
        result[key] = value
    return result


def _validate_relative_paths(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Population scope relative_paths must be a nonempty list")
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str) or "\x00" in item:
            raise ValueError("Population scope contains an invalid source path")
        candidate = PurePosixPath(item)
        if (
            candidate.is_absolute()
            or len(candidate.parts) != 1
            or candidate.name != item
            or candidate.suffix.lower() != ".csv"
        ):
            raise ValueError("Population scope paths must be direct CSV filenames")
        paths.append(item)
    if len(paths) != len(set(paths)):
        raise ValueError("Population scope contains a duplicate source path")
    if paths != sorted(paths):
        raise ValueError("Population scope paths are not in canonical sorted order")
    return tuple(paths)


def load_population_scope(
    artifact_path: Path,
    *,
    expected_sha256: str,
    expected_parser_field_limit_chars: int,
) -> PopulationScope:
    """Load an exact hash-pinned source scope without inspecting source files."""
    if _LOWER_SHA256_RE.fullmatch(expected_sha256) is None:
        raise ValueError("Expected population-scope SHA-256 is not canonical")
    if artifact_path.is_symlink() or not artifact_path.is_file():
        raise OSError("Population scope is not a regular file")
    before = artifact_path.stat(follow_symlinks=False)
    if stat.S_IMODE(before.st_mode) != 0o600:
        raise OSError("Population scope must be owner-only mode 0600")
    content = artifact_path.read_bytes()
    after = artifact_path.stat(follow_symlinks=False)
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeError("Population scope changed while it was being read")
    observed_sha256 = hashlib.sha256(content).hexdigest()
    if observed_sha256 != expected_sha256:
        raise ValueError("Population scope SHA-256 differs from the authorized value")
    try:
        value = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Population scope is not valid UTF-8 JSON") from error
    if not isinstance(value, dict) or set(value) != _SCOPE_KEYS:
        raise ValueError("Population scope schema is not exact")

    population_id = value["population_id"]
    if (
        not isinstance(population_id, str)
        or _POPULATION_ID_RE.fullmatch(population_id) is None
    ):
        raise ValueError("Population scope population_id is invalid")
    expected_source_count = value["expected_source_count"]
    if (
        isinstance(expected_source_count, bool)
        or not isinstance(expected_source_count, int)
        or expected_source_count < 1
    ):
        raise ValueError("Population scope expected_source_count must be positive")
    parser_field_limit_chars = value["parser_field_limit_chars"]
    if (
        isinstance(parser_field_limit_chars, bool)
        or not isinstance(parser_field_limit_chars, int)
        or parser_field_limit_chars != expected_parser_field_limit_chars
    ):
        raise ValueError("Population scope parser ceiling differs from the run")
    relative_paths = _validate_relative_paths(value["relative_paths"])
    if expected_source_count != len(relative_paths):
        raise ValueError("Population scope count differs from its exact path set")

    expected_schema_fingerprint = source_schema_fingerprint(SOURCE_COLUMNS)
    if (
        value["population_scope_version"] != POPULATION_SCOPE_VERSION
        or value["phase01_inventory_version"] != INVENTORY_VERSION
        or value["source_schema_fingerprint"] != expected_schema_fingerprint
    ):
        raise ValueError("Population scope scientific contract is incompatible")
    return PopulationScope(
        artifact_path=artifact_path.resolve(),
        artifact_size_bytes=before.st_size,
        artifact_sha256=observed_sha256,
        population_scope_version=POPULATION_SCOPE_VERSION,
        population_id=population_id,
        inventory_version=INVENTORY_VERSION,
        source_schema_fingerprint=expected_schema_fingerprint,
        parser_field_limit_chars=parser_field_limit_chars,
        expected_source_count=expected_source_count,
        relative_paths=relative_paths,
    )


__all__ = ["POPULATION_SCOPE_VERSION", "PopulationScope", "load_population_scope"]

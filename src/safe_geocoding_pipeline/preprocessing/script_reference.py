"""Pinned Unicode Script reference used by the accepted Benchmark V1 sampler."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal


AuthorityRole = Literal["UNICODE_SCRIPT_PROPERTY"]
RedistributionPolicy = Literal["VENDORED", "CONTROLLED_LOCAL_ONLY", "EXTERNAL_APPROVED"]
UNICODE_REFERENCE_DIRECTORY = "unicode_ucd_16_0_0"


class ScriptReferenceError(RuntimeError):
    """Privacy-safe pinned-reference failure with a stable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail[:500]


@dataclass(frozen=True, slots=True)
class ReferenceManifest:
    reference_id: str
    authority_role: AuthorityRole
    source: str
    vintage: str
    retrieved_at_utc: str
    artifact_file_name: str
    artifact_sha256: str
    artifact_size_bytes: int
    loader_schema_version: str
    license_name: str
    license_identifier: str
    license_note: str
    redistribution_policy: RedistributionPolicy
    validation_status: str
    unicode_version: str | None = None
    row_count: int | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ReferenceManifest":
        required = {
            "reference_id",
            "authority_role",
            "source",
            "vintage",
            "retrieved_at_utc",
            "artifact_file_name",
            "artifact_sha256",
            "artifact_size_bytes",
            "loader_schema_version",
            "license_name",
            "license_identifier",
            "license_note",
            "redistribution_policy",
            "validation_status",
        }
        missing = required - value.keys()
        if missing:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", f"missing fields: {sorted(missing)}"
            )
        string_fields = required - {"artifact_size_bytes"}
        if (
            any(not isinstance(value[key], str) for key in string_fields)
            or (
                type(value["artifact_size_bytes"]) is not int
                or value["artifact_size_bytes"] < 0
            )
            or (
                value.get("unicode_version") is not None
                and not isinstance(value["unicode_version"], str)
            )
            or (
                value.get("row_count") is not None
                and (type(value["row_count"]) is not int or value["row_count"] < 0)
            )
        ):
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "manifest fields have invalid types"
            )
        manifest = cls(
            reference_id=value["reference_id"],
            authority_role=value["authority_role"],
            source=value["source"],
            vintage=value["vintage"],
            retrieved_at_utc=value["retrieved_at_utc"],
            artifact_file_name=value["artifact_file_name"],
            artifact_sha256=value["artifact_sha256"],
            artifact_size_bytes=value["artifact_size_bytes"],
            loader_schema_version=value["loader_schema_version"],
            license_name=value["license_name"],
            license_identifier=value["license_identifier"],
            license_note=value["license_note"],
            redistribution_policy=value["redistribution_policy"],
            validation_status=value["validation_status"],
            unicode_version=value.get("unicode_version"),
            row_count=value.get("row_count"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.authority_role != "UNICODE_SCRIPT_PROPERTY":
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "unsupported authority role"
            )
        if self.redistribution_policy not in {
            "VENDORED",
            "CONTROLLED_LOCAL_ONLY",
            "EXTERNAL_APPROVED",
        }:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "unsupported redistribution policy"
            )
        if (
            len(self.artifact_sha256) != 64
            or self.artifact_sha256 != self.artifact_sha256.lower()
        ):
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "artifact SHA-256 must be lowercase hex"
            )
        try:
            bytes.fromhex(self.artifact_sha256)
        except ValueError as error:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "artifact SHA-256 is not hex"
            ) from error
        if not all(
            (
                self.reference_id,
                self.source,
                self.vintage,
                self.artifact_file_name,
                self.loader_schema_version,
                self.license_name,
                self.license_identifier,
                self.license_note,
            )
        ):
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "reference metadata cannot be empty"
            )
        try:
            retrieved = datetime.fromisoformat(
                self.retrieved_at_utc.removesuffix("Z") + "+00:00"
            )
        except ValueError as error:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "invalid UTC retrieval timestamp"
            ) from error
        if not self.retrieved_at_utc.endswith("Z") or retrieved.utcoffset() is None:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "retrieval timestamp must be UTC"
            )
        if Path(self.artifact_file_name).name != self.artifact_file_name:
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "artifact filename must be portable"
            )
        if self.validation_status != "PASS":
            raise ScriptReferenceError(
                "REFERENCE_MANIFEST_INVALID", "production reference is not validated"
            )


def load_manifest(path: Path) -> ReferenceManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ScriptReferenceError(
            "REFERENCE_MANIFEST_READ_FAILURE", type(error).__name__
        ) from error
    if not isinstance(value, dict):
        raise ScriptReferenceError(
            "REFERENCE_MANIFEST_INVALID", "manifest root must be an object"
        )
    return ReferenceManifest.from_mapping(value)


def verify_artifact(manifest: ReferenceManifest, path: Path) -> bytes:
    if path.name != manifest.artifact_file_name:
        raise ScriptReferenceError(
            "REFERENCE_ARTIFACT_FILENAME_MISMATCH",
            "artifact filename differs from manifest",
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ScriptReferenceError(
            "REFERENCE_ARTIFACT_READ_FAILURE", type(error).__name__
        ) from error
    if hashlib.sha256(data).hexdigest() != manifest.artifact_sha256:
        raise ScriptReferenceError(
            "REFERENCE_ARTIFACT_HASH_MISMATCH",
            "artifact identity differs from manifest",
        )
    if len(data) != manifest.artifact_size_bytes:
        raise ScriptReferenceError(
            "REFERENCE_ARTIFACT_SIZE_MISMATCH",
            "artifact byte size differs from manifest",
        )
    return data


@dataclass(frozen=True, slots=True)
class ScriptRange:
    start: int
    end: int
    script: str


class ScriptReference:
    """Validated lookup over the pinned Unicode Script property ranges."""

    def __init__(
        self, manifest: ReferenceManifest, ranges: tuple[ScriptRange, ...]
    ) -> None:
        if (
            manifest.authority_role != "UNICODE_SCRIPT_PROPERTY"
            or manifest.unicode_version != "16.0.0"
        ):
            raise ScriptReferenceError("SCRIPT_REFERENCE_VERSION_OR_ROLE_MISMATCH")
        self.manifest = manifest
        self.ranges = tuple(sorted(ranges, key=lambda item: (item.start, item.end)))
        previous_end = -1
        for item in self.ranges:
            if item.start <= previous_end or item.start > item.end:
                raise ScriptReferenceError("SCRIPT_REFERENCE_OVERLAP")
            previous_end = item.end

    @property
    def version(self) -> str:
        return self.manifest.reference_id

    def script_for(self, character: str) -> str:
        codepoint = ord(character)
        left, right = 0, len(self.ranges)
        while left < right:
            middle = (left + right) // 2
            item = self.ranges[middle]
            if codepoint < item.start:
                right = middle
            elif codepoint > item.end:
                left = middle + 1
            else:
                return item.script
        return "Unknown"

    def distinctive_scripts(self, value: str) -> frozenset[str]:
        return frozenset(
            script
            for character in value
            if (script := self.script_for(character))
            not in {"Common", "Inherited", "Unknown"}
        )

    @classmethod
    def from_artifact(
        cls, manifest_path: Path, artifact_path: Path
    ) -> "ScriptReference":
        manifest = load_manifest(manifest_path)
        data = verify_artifact(manifest, artifact_path)
        if manifest.loader_schema_version != "unicode_scripts_txt_v1":
            raise ScriptReferenceError("SCRIPT_REFERENCE_SCHEMA_UNSUPPORTED")
        ranges: list[ScriptRange] = []
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise ScriptReferenceError(
                "SCRIPT_REFERENCE_PARSE_FAILURE", "invalid UTF-8"
            ) from error
        for physical_line, line in enumerate(text.splitlines(), start=1):
            content = line.split("#", 1)[0].strip()
            if not content:
                continue
            pieces = [piece.strip() for piece in content.split(";")]
            if len(pieces) != 2 or not pieces[1].replace("_", "").isalnum():
                raise ScriptReferenceError(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                )
            bounds = pieces[0].split("..")
            try:
                start = int(bounds[0], 16)
                end = int(bounds[-1], 16)
            except ValueError as error:
                raise ScriptReferenceError(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                ) from error
            if not (0 <= start <= end <= 0x10FFFF):
                raise ScriptReferenceError(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                )
            ranges.append(ScriptRange(start, end, pieces[1]))
        return cls(manifest, tuple(ranges))


def unicode_script_reference_paths() -> dict[str, Path]:
    """Return paths for the benchmark-pinned, vendored Unicode reference."""

    resource_root = files("safe_geocoding_pipeline.preprocessing").joinpath(
        "resources", "references", UNICODE_REFERENCE_DIRECTORY
    )
    return {
        "unicode_manifest": Path(str(resource_root.joinpath("manifest.json"))),
        "unicode_artifact": Path(str(resource_root.joinpath("Scripts.txt"))),
        "unicode_license": Path(str(resource_root.joinpath("LICENSE.txt"))),
    }

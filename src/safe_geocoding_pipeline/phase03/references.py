from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .errors import Phase03Error, ReferenceNotReadyError

AuthorityRole = Literal[
    "NORMATIVE_CODE_VALIDATION", "NAME_MAPPING", "UNICODE_SCRIPT_PROPERTY"
]
RedistributionPolicy = Literal["VENDORED", "CONTROLLED_LOCAL_ONLY", "EXTERNAL_APPROVED"]


@dataclass(frozen=True, slots=True)
class ReferenceManifest:
    reference_id: str
    authority_role: AuthorityRole
    source: str
    vintage: str
    artifact_sha256: str
    loader_schema_version: str
    license_note: str
    redistribution_policy: RedistributionPolicy
    unicode_version: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ReferenceManifest":
        required = {
            "reference_id",
            "authority_role",
            "source",
            "vintage",
            "artifact_sha256",
            "loader_schema_version",
            "license_note",
            "redistribution_policy",
        }
        missing = required - value.keys()
        if missing:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", f"missing fields: {sorted(missing)}"
            )
        if any(not isinstance(value[key], str) for key in required) or (
            value.get("unicode_version") is not None
            and not isinstance(value["unicode_version"], str)
        ):
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "manifest fields have invalid types"
            )
        manifest = cls(
            reference_id=value["reference_id"],
            authority_role=value["authority_role"],
            source=value["source"],
            vintage=value["vintage"],
            artifact_sha256=value["artifact_sha256"],
            loader_schema_version=value["loader_schema_version"],
            license_note=value["license_note"],
            redistribution_policy=value["redistribution_policy"],
            unicode_version=value.get("unicode_version"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        if self.authority_role not in {
            "NORMATIVE_CODE_VALIDATION",
            "NAME_MAPPING",
            "UNICODE_SCRIPT_PROPERTY",
        }:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "unsupported authority role"
            )
        if self.redistribution_policy not in {
            "VENDORED",
            "CONTROLLED_LOCAL_ONLY",
            "EXTERNAL_APPROVED",
        }:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "unsupported redistribution policy"
            )
        if (
            len(self.artifact_sha256) != 64
            or self.artifact_sha256 != self.artifact_sha256.lower()
        ):
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "artifact SHA-256 must be lowercase hex"
            )
        try:
            bytes.fromhex(self.artifact_sha256)
        except ValueError as error:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "artifact SHA-256 is not hex"
            ) from error
        if not all(
            (
                self.reference_id,
                self.source,
                self.vintage,
                self.loader_schema_version,
                self.license_note,
            )
        ):
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "reference metadata cannot be empty"
            )


def load_manifest(path: Path) -> ReferenceManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error(
            "REFERENCE_MANIFEST_READ_FAILURE", type(error).__name__
        ) from error
    if not isinstance(value, dict):
        raise Phase03Error(
            "REFERENCE_MANIFEST_INVALID", "manifest root must be an object"
        )
    return ReferenceManifest.from_mapping(value)


def verify_artifact(manifest: ReferenceManifest, path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise Phase03Error(
            "REFERENCE_ARTIFACT_READ_FAILURE", type(error).__name__
        ) from error
    if hashlib.sha256(data).hexdigest() != manifest.artifact_sha256:
        raise Phase03Error(
            "REFERENCE_ARTIFACT_HASH_MISMATCH",
            "artifact identity differs from manifest",
        )
    return data


@dataclass(frozen=True, slots=True)
class CountryRecord:
    alpha2: str
    alpha3: str
    names: tuple[str, ...]


class CountryReference:
    def __init__(
        self,
        *,
        assignment_manifest: ReferenceManifest,
        name_manifest: ReferenceManifest,
        records: tuple[CountryRecord, ...],
    ) -> None:
        if assignment_manifest.authority_role != "NORMATIVE_CODE_VALIDATION":
            raise Phase03Error("COUNTRY_REFERENCE_ROLE_MISMATCH")
        if name_manifest.authority_role != "NAME_MAPPING":
            raise Phase03Error("COUNTRY_REFERENCE_ROLE_MISMATCH")
        self.assignment_manifest = assignment_manifest
        self.name_manifest = name_manifest
        self.records = records
        self._alpha2 = {record.alpha2: record for record in records}
        self._alpha3 = {record.alpha3: record for record in records}
        self._names = {name: record for record in records for name in record.names}
        if len(self._alpha2) != len(records) or len(self._alpha3) != len(records):
            raise Phase03Error("COUNTRY_REFERENCE_DUPLICATE_CODE")

    @property
    def version(self) -> str:
        return (
            f"{self.assignment_manifest.reference_id}+{self.name_manifest.reference_id}"
        )

    def exact_lookup(self, raw_value: str) -> tuple[CountryRecord | None, str]:
        if raw_value in self._alpha2:
            return self._alpha2[raw_value], "ALPHA2"
        if raw_value in self._alpha3:
            return self._alpha3[raw_value], "ALPHA3"
        if raw_value in self._names:
            return self._names[raw_value], "NAME"
        return None, "NONE"

    @classmethod
    def from_artifacts(
        cls,
        assignment_manifest_path: Path,
        assignment_artifact_path: Path,
        name_manifest_path: Path,
        name_artifact_path: Path,
    ) -> "CountryReference":
        assignment = load_manifest(assignment_manifest_path)
        names = load_manifest(name_manifest_path)
        assignment_data = verify_artifact(assignment, assignment_artifact_path)
        name_data = verify_artifact(names, name_artifact_path)
        if assignment.loader_schema_version != "country_assignments_json_v1":
            raise Phase03Error("COUNTRY_REFERENCE_SCHEMA_UNSUPPORTED")
        if names.loader_schema_version != "country_names_json_v1":
            raise Phase03Error("COUNTRY_REFERENCE_SCHEMA_UNSUPPORTED")
        try:
            assignments_value = json.loads(assignment_data)
            names_value = json.loads(name_data)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise Phase03Error(
                "COUNTRY_REFERENCE_PARSE_FAILURE", type(error).__name__
            ) from error
        if not isinstance(assignments_value, list) or not isinstance(names_value, list):
            raise Phase03Error(
                "COUNTRY_REFERENCE_PARSE_FAILURE", "artifacts must contain lists"
            )
        name_map: dict[str, list[str]] = {}
        seen_names: set[str] = set()
        for item in names_value:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("alpha2"), str)
                or not isinstance(item.get("names"), list)
            ):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid name record"
                )
            if not all(isinstance(value, str) and value for value in item["names"]):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid country name"
                )
            alpha2 = item["alpha2"]
            country_names = list(item["names"])
            if (
                alpha2 in name_map
                or len(set(country_names)) != len(country_names)
                or seen_names.intersection(country_names)
            ):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "duplicate country mapping"
                )
            name_map[alpha2] = country_names
            seen_names.update(country_names)
        records: list[CountryRecord] = []
        for item in assignments_value:
            if not isinstance(item, dict):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid assignment record"
                )
            alpha2, alpha3 = item.get("alpha2"), item.get("alpha3")
            if not isinstance(alpha2, str) or not isinstance(alpha3, str):
                raise Phase03Error("COUNTRY_REFERENCE_PARSE_FAILURE", "invalid code")
            if not (len(alpha2) == 2 and alpha2.isascii() and alpha2.isupper()):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid alpha-2 syntax"
                )
            if not (len(alpha3) == 3 and alpha3.isascii() and alpha3.isupper()):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid alpha-3 syntax"
                )
            records.append(
                CountryRecord(alpha2, alpha3, tuple(name_map.get(alpha2, ())))
            )
        assignment_codes = {record.alpha2 for record in records}
        if set(name_map) != assignment_codes:
            raise Phase03Error(
                "COUNTRY_REFERENCE_PARSE_FAILURE",
                "name and assignment country sets differ",
            )
        return cls(
            assignment_manifest=assignment, name_manifest=names, records=tuple(records)
        )


def require_production_country_reference(
    reference: CountryReference | None,
) -> CountryReference:
    if reference is None:
        raise ReferenceNotReadyError("COUNTRY_REFERENCE_NOT_READY")
    return reference


@dataclass(frozen=True, slots=True)
class ScriptRange:
    start: int
    end: int
    script: str


class ScriptReference:
    def __init__(
        self, manifest: ReferenceManifest, ranges: tuple[ScriptRange, ...]
    ) -> None:
        if (
            manifest.authority_role != "UNICODE_SCRIPT_PROPERTY"
            or manifest.unicode_version != "16.0.0"
        ):
            raise Phase03Error("SCRIPT_REFERENCE_VERSION_OR_ROLE_MISMATCH")
        self.manifest = manifest
        self.ranges = tuple(sorted(ranges, key=lambda item: (item.start, item.end)))
        previous_end = -1
        for item in self.ranges:
            if item.start <= previous_end or item.start > item.end:
                raise Phase03Error("SCRIPT_REFERENCE_OVERLAP")
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
            raise Phase03Error("SCRIPT_REFERENCE_SCHEMA_UNSUPPORTED")
        ranges: list[ScriptRange] = []
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise Phase03Error(
                "SCRIPT_REFERENCE_PARSE_FAILURE", "invalid UTF-8"
            ) from error
        for physical_line, line in enumerate(text.splitlines(), start=1):
            content = line.split("#", 1)[0].strip()
            if not content:
                continue
            pieces = [piece.strip() for piece in content.split(";")]
            if len(pieces) != 2 or not pieces[1].replace("_", "").isalnum():
                raise Phase03Error(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                )
            bounds = pieces[0].split("..")
            try:
                start = int(bounds[0], 16)
                end = int(bounds[-1], 16)
            except ValueError as error:
                raise Phase03Error(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                ) from error
            if not (0 <= start <= end <= 0x10FFFF):
                raise Phase03Error(
                    "SCRIPT_REFERENCE_PARSE_FAILURE", f"invalid line {physical_line}"
                )
            ranges.append(ScriptRange(start, end, pieces[1]))
        return cls(manifest, tuple(ranges))

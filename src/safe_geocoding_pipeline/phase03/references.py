from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from .errors import Phase03Error, ReferenceNotReadyError
from .reference_pinning import (
    CLDR_COUNTRY_EXTRACTOR_VERSION,
    CLDR_COUNTRY_REFERENCE_ID,
    CLDR_COUNTRY_SCHEMA_VERSION,
    CLDR_RELEASE,
    CLDR_SELECTABLE_POLICY_VERSION,
    cldr_extractor_configuration_fingerprint,
    extract_cldr_country_reference,
    load_canonical_cldr_value,
)

AuthorityRole = Literal[
    "NORMATIVE_CODE_VALIDATION",
    "NAME_MAPPING",
    "OPERATIONAL_COUNTRY_MAPPING",
    "UNICODE_SCRIPT_PROPERTY",
]
RedistributionPolicy = Literal["VENDORED", "CONTROLLED_LOCAL_ONLY", "EXTERNAL_APPROVED"]

UNICODE_REFERENCE_DIRECTORY = "unicode_ucd_16_0_0"
COUNTRY_REFERENCE_DIRECTORY = "cldr_46_1"
COUNTRY_AUTHORITY_MANIFEST = "country_reference_v2.json"


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
            raise Phase03Error(
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
            raise Phase03Error(
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
        if self.authority_role not in {
            "NORMATIVE_CODE_VALIDATION",
            "NAME_MAPPING",
            "OPERATIONAL_COUNTRY_MAPPING",
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
                self.artifact_file_name,
                self.loader_schema_version,
                self.license_name,
                self.license_identifier,
                self.license_note,
            )
        ):
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "reference metadata cannot be empty"
            )
        try:
            retrieved = datetime.fromisoformat(
                self.retrieved_at_utc.removesuffix("Z") + "+00:00"
            )
        except ValueError as error:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "invalid UTC retrieval timestamp"
            ) from error
        if not self.retrieved_at_utc.endswith("Z") or retrieved.utcoffset() is None:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "retrieval timestamp must be UTC"
            )
        if Path(self.artifact_file_name).name != self.artifact_file_name:
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "artifact filename must be portable"
            )
        if self.validation_status != "PASS":
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "production reference is not validated"
            )
        if (
            self.authority_role == "OPERATIONAL_COUNTRY_MAPPING"
            and self.row_count is None
        ):
            raise Phase03Error(
                "REFERENCE_MANIFEST_INVALID", "country reference row count is required"
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
    if path.name != manifest.artifact_file_name:
        raise Phase03Error(
            "REFERENCE_ARTIFACT_FILENAME_MISMATCH",
            "artifact filename differs from manifest",
        )
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
    if len(data) != manifest.artifact_size_bytes:
        raise Phase03Error(
            "REFERENCE_ARTIFACT_SIZE_MISMATCH",
            "artifact byte size differs from manifest",
        )
    return data


@dataclass(frozen=True, slots=True)
class CountryRecord:
    alpha2: str
    alpha3: str
    names: tuple[str, ...]
    numeric_code: str | None = None


class CountryReference:
    def __init__(
        self,
        *,
        assignment_manifest: ReferenceManifest,
        name_manifest: ReferenceManifest,
        records: tuple[CountryRecord, ...],
    ) -> None:
        legacy_roles = (
            assignment_manifest.authority_role == "NORMATIVE_CODE_VALIDATION"
            and name_manifest.authority_role == "NAME_MAPPING"
        )
        operational_roles = (
            assignment_manifest.authority_role == "OPERATIONAL_COUNTRY_MAPPING"
            and name_manifest.authority_role == "OPERATIONAL_COUNTRY_MAPPING"
            and assignment_manifest == name_manifest
        )
        if not (legacy_roles or operational_roles):
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
        if self.assignment_manifest == self.name_manifest:
            return self.assignment_manifest.reference_id
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

    @classmethod
    def from_cldr_artifact(
        cls, manifest_path: Path, artifact_path: Path
    ) -> "CountryReference":
        manifest = load_manifest(manifest_path)
        if manifest.authority_role != "OPERATIONAL_COUNTRY_MAPPING":
            raise Phase03Error("COUNTRY_REFERENCE_ROLE_MISMATCH")
        if manifest.loader_schema_version != CLDR_COUNTRY_SCHEMA_VERSION:
            raise Phase03Error("COUNTRY_REFERENCE_SCHEMA_UNSUPPORTED")
        data = verify_artifact(manifest, artifact_path)
        value = load_canonical_cldr_value(data)
        if set(value) != {
            "country_reference_version",
            "extractor_configuration_fingerprint",
            "extractor_version",
            "records",
            "schema_version",
            "selectable_territory_policy_version",
        }:
            raise Phase03Error("COUNTRY_REFERENCE_PARSE_FAILURE")
        if (
            value["country_reference_version"] != manifest.reference_id
            or value["extractor_configuration_fingerprint"]
            != cldr_extractor_configuration_fingerprint()
            or value["extractor_version"] != CLDR_COUNTRY_EXTRACTOR_VERSION
            or value["schema_version"] != CLDR_COUNTRY_SCHEMA_VERSION
            or value["selectable_territory_policy_version"]
            != CLDR_SELECTABLE_POLICY_VERSION
        ):
            raise Phase03Error("COUNTRY_REFERENCE_VERSION_MISMATCH")
        records_value = value["records"]
        if not isinstance(records_value, list) or len(records_value) != manifest.row_count:
            raise Phase03Error(
                "COUNTRY_REFERENCE_PARSE_FAILURE", "row count differs from manifest"
            )
        records: list[CountryRecord] = []
        rows_seen: set[tuple[str, str, str, str]] = set()
        names_seen: set[str] = set()
        numeric_seen: set[str] = set()
        for item in records_value:
            if not isinstance(item, dict) or set(item) != {
                "territory_code",
                "alpha3_code",
                "numeric_code",
                "english_name",
            }:
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid operational row"
                )
            name = item["english_name"]
            numeric = item["numeric_code"]
            alpha2 = item["territory_code"]
            alpha3 = item["alpha3_code"]
            if not all(isinstance(part, str) and part for part in item.values()):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "missing operational value"
                )
            if not (
                len(numeric) == 3 and numeric.isascii() and numeric.isdigit()
            ):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid numeric code"
                )
            if not (len(alpha2) == 2 and alpha2.isascii() and alpha2.isupper()):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid alpha-2 syntax"
                )
            if not (len(alpha3) == 3 and alpha3.isascii() and alpha3.isupper()):
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "invalid alpha-3 syntax"
                )
            row = (name, numeric, alpha2, alpha3)
            if row in rows_seen or name in names_seen or numeric in numeric_seen:
                raise Phase03Error(
                    "COUNTRY_REFERENCE_PARSE_FAILURE", "duplicate operational mapping"
                )
            rows_seen.add(row)
            names_seen.add(name)
            numeric_seen.add(numeric)
            records.append(CountryRecord(alpha2, alpha3, (name,), numeric))
        return cls(
            assignment_manifest=manifest,
            name_manifest=manifest,
            records=tuple(records),
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


def production_reference_paths() -> dict[str, Path]:
    resource_root = files("safe_geocoding_pipeline.phase03").joinpath(
        "resources", "references"
    )
    country_root = resource_root.joinpath(COUNTRY_REFERENCE_DIRECTORY)
    return {
        "unicode_manifest": Path(
            str(resource_root.joinpath(UNICODE_REFERENCE_DIRECTORY, "manifest.json"))
        ),
        "unicode_artifact": Path(
            str(resource_root.joinpath(UNICODE_REFERENCE_DIRECTORY, "Scripts.txt"))
        ),
        "unicode_license": Path(
            str(resource_root.joinpath(UNICODE_REFERENCE_DIRECTORY, "LICENSE.txt"))
        ),
        "country_manifest": Path(
            str(country_root.joinpath("manifest.json"))
        ),
        "country_artifact": Path(
            str(country_root.joinpath("country_reference_cldr_46_1_v1.json"))
        ),
        "country_supplemental_data": Path(
            str(country_root.joinpath("supplementalData.xml"))
        ),
        "country_english_names": Path(str(country_root.joinpath("en.xml"))),
        "country_region_validity": Path(str(country_root.joinpath("region.xml"))),
        "country_license": Path(str(country_root.joinpath("LICENSE"))),
        "country_directory": Path(str(country_root)),
        "country_authority_manifest": Path(
            str(resource_root.joinpath(COUNTRY_AUTHORITY_MANIFEST))
        ),
    }


def _read_json_object(path: Path, error_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error(error_code, type(error).__name__) from error
    if not isinstance(value, dict):
        raise Phase03Error(error_code)
    return value


def _read_reference_bytes(path: Path, error_code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise Phase03Error(error_code, type(error).__name__) from error


def verify_cldr_reference_bundle(
    manifest_path: Path, reference_directory: Path
) -> ReferenceManifest:
    manifest = load_manifest(manifest_path)
    value = _read_json_object(manifest_path, "CLDR_MANIFEST_INVALID")
    if (
        manifest.reference_id != CLDR_COUNTRY_REFERENCE_ID
        or manifest.authority_role != "OPERATIONAL_COUNTRY_MAPPING"
        or manifest.loader_schema_version != CLDR_COUNTRY_SCHEMA_VERSION
        or manifest.license_identifier != "Unicode-3.0"
        or manifest.redistribution_policy != "VENDORED"
        or manifest.row_count != 249
        or value.get("schema_version") != "cldr_country_reference_manifest_v1"
        or value.get("cldr_release") != CLDR_RELEASE
    ):
        raise Phase03Error("CLDR_MANIFEST_INVALID")

    release = value.get("release_artifact")
    if not isinstance(release, dict) or release != {
        "artifact_file_name": "cldr-common-46.1.zip",
        "artifact_sha256": "c3828c9280c6b3bb921bc96baf53be2174b5416d72e740ec3915c1ff91a50a80",
        "artifact_sha512": "6f5bece848d8187da35cc4c4022bea6a673e40a6032864b09ef24744f35bbf5e89e32e9852bbfd91d7466332db87c8f4f514ff70221729275701b7d95bac2925",
        "artifact_size_bytes": 34_308_024,
        "official_upstream_integrity": "No release checksum was available at the documented versioned hashes/SHASUM512.txt location when retrieved; SHA-256 and SHA-512 were calculated locally from the official HTTPS artifact.",
        "source": "https://www.unicode.org/Public/cldr/46.1/cldr-common-46.1.zip",
    }:
        raise Phase03Error("CLDR_RELEASE_IDENTITY_INVALID")

    expected_sources = {
        "supplementalData.xml": (
            "common/supplemental/supplementalData.xml",
            "277105238ecaab5b0e476f3bc7d25a26358227c5c77d02b0921d311c3f940dbf",
            396_715,
        ),
        "en.xml": (
            "common/main/en.xml",
            "5ac57cec48ab8d9a87cbd920444024ccdcc914ae6ffa4353f6e17bc0a9f8d6e7",
            431_277,
        ),
        "region.xml": (
            "common/validity/region.xml",
            "e751e0eedd46b52c38f3cdb72b0fab61ac8b48e052e8b28ba74b6ac26c4c8cb1",
            1_905,
        ),
    }
    source_artifacts = value.get("source_artifacts")
    if not isinstance(source_artifacts, list) or len(source_artifacts) != 3:
        raise Phase03Error("CLDR_SOURCE_IDENTITY_INVALID")
    source_data: dict[str, bytes] = {}
    for item in source_artifacts:
        if not isinstance(item, dict):
            raise Phase03Error("CLDR_SOURCE_IDENTITY_INVALID")
        local_name = item.get("artifact_file_name")
        if not isinstance(local_name, str) or local_name not in expected_sources:
            raise Phase03Error("CLDR_SOURCE_IDENTITY_INVALID")
        archive_path, expected_hash, expected_size = expected_sources.pop(local_name)
        if item != {
            "archive_path": archive_path,
            "artifact_file_name": local_name,
            "artifact_sha256": expected_hash,
            "artifact_size_bytes": expected_size,
        }:
            raise Phase03Error("CLDR_SOURCE_IDENTITY_INVALID")
        data = _read_reference_bytes(
            reference_directory / local_name, "CLDR_SOURCE_ARTIFACT_READ_FAILURE"
        )
        if hashlib.sha256(data).hexdigest() != expected_hash or len(data) != expected_size:
            raise Phase03Error("CLDR_SOURCE_ARTIFACT_MISMATCH", local_name)
        source_data[local_name] = data
    if expected_sources:
        raise Phase03Error("CLDR_SOURCE_IDENTITY_INVALID")

    license_value = value.get("license_artifact")
    if not isinstance(license_value, dict) or license_value != {
        "archive_path": "LICENSE",
        "artifact_file_name": "LICENSE",
        "artifact_sha256": "4e6e762822c88cf41c072b93568f3e1a6784b5b013e82bf42a61bb7a018d9239",
        "artifact_size_bytes": 2_036,
        "license_identifier": "Unicode-3.0",
    }:
        raise Phase03Error("CLDR_LICENSE_IDENTITY_INVALID")
    license_data = _read_reference_bytes(
        reference_directory / "LICENSE", "CLDR_LICENSE_READ_FAILURE"
    )
    if (
        hashlib.sha256(license_data).hexdigest()
        != license_value["artifact_sha256"]
        or len(license_data) != license_value["artifact_size_bytes"]
        or b"SPDX-License-Identifier: Unicode-3.0" not in license_data
    ):
        raise Phase03Error("CLDR_LICENSE_IDENTITY_INVALID")

    extractor = value.get("extractor")
    if not isinstance(extractor, dict) or extractor != {
        "configuration_fingerprint": cldr_extractor_configuration_fingerprint(),
        "version": CLDR_COUNTRY_EXTRACTOR_VERSION,
    }:
        raise Phase03Error("CLDR_EXTRACTOR_IDENTITY_INVALID")
    first = extract_cldr_country_reference(
        supplemental_data_xml=source_data["supplementalData.xml"],
        english_territories_xml=source_data["en.xml"],
        region_validity_xml=source_data["region.xml"],
    )
    second = extract_cldr_country_reference(
        supplemental_data_xml=source_data["supplementalData.xml"],
        english_territories_xml=source_data["en.xml"],
        region_validity_xml=source_data["region.xml"],
    )
    if first != second:
        raise Phase03Error("CLDR_EXTRACTION_NONDETERMINISTIC")
    if first.row_count != manifest.row_count:
        raise Phase03Error("CLDR_EXTRACTION_ROW_COUNT_MISMATCH")
    canonical = verify_artifact(manifest, reference_directory / manifest.artifact_file_name)
    if first.canonical_artifact != canonical:
        raise Phase03Error("CLDR_CANONICAL_REPRODUCTION_MISMATCH")
    expected_validation = {
        "alpha3_duplicate_count": 0,
        "canonical_name_duplicate_count": 0,
        "numeric_duplicate_count": 0,
        "selectable_row_count": first.row_count,
        "status_counts": first.status_counts,
        "excluded_identifiers": {
            key: list(identifiers)
            for key, identifiers in first.excluded_identifiers.items()
        },
    }
    if value.get("validation_results") != expected_validation:
        raise Phase03Error("CLDR_VALIDATION_RESULTS_MISMATCH")
    return manifest


def validate_country_authority_manifest(
    path: Path,
    operational_manifest: ReferenceManifest,
    *,
    operational_manifest_path: Path | None = None,
    expected_country_reference_id: str | None = None,
) -> dict[str, Any]:
    value = _read_json_object(path, "COUNTRY_AUTHORITY_MANIFEST_READ_FAILURE")
    if set(value) != {
        "country_reference_id",
        "normative_authority",
        "operational_reference",
        "schema_version",
    }:
        raise Phase03Error("COUNTRY_AUTHORITY_MANIFEST_INVALID")
    normative = value["normative_authority"]
    operational = value["operational_reference"]
    if (
        value["schema_version"] != "country_reference_manifest_v2"
        or not isinstance(normative, dict)
        or not isinstance(operational, dict)
        or normative.get("organization")
        != "International Organization for Standardization (ISO), ISO 3166 Maintenance Agency"
        or normative.get("standard") != "ISO 3166"
        or normative.get("source") != "https://www.iso.org/iso-3166-country-codes.html"
        or (
            expected_country_reference_id is not None
            and value["country_reference_id"] != expected_country_reference_id
        )
        or normative.get("role") != "normative_code_system"
        or operational.get("organization") != "Unicode Consortium"
        or operational.get("dataset") != "Common Locale Data Repository (CLDR)"
        or operational.get("release") != CLDR_RELEASE
        or operational.get("role") != "operational_machine_readable_mapping"
        or operational.get("reference_id") != operational_manifest.reference_id
        or operational.get("source") != operational_manifest.source
        or operational.get("artifact_sha256") != operational_manifest.artifact_sha256
        or operational.get("artifact_size_bytes")
        != operational_manifest.artifact_size_bytes
        or operational.get("row_count") != operational_manifest.row_count
        or operational.get("schema_version")
        != operational_manifest.loader_schema_version
        or operational.get("license_identifier") != "Unicode-3.0"
        or operational.get("selectable_territory_policy_version")
        != CLDR_SELECTABLE_POLICY_VERSION
        or operational.get("validation_status") != "PASS"
    ):
        raise Phase03Error("COUNTRY_AUTHORITY_MANIFEST_INVALID")
    if operational_manifest_path is not None:
        expected_manifest_hash = operational.get("manifest_sha256")
        if (
            not isinstance(expected_manifest_hash, str)
            or hashlib.sha256(operational_manifest_path.read_bytes()).hexdigest()
            != expected_manifest_hash
        ):
            raise Phase03Error("COUNTRY_AUTHORITY_MANIFEST_INVALID")
    return value


def load_production_references(
    *,
    expected_country_reference_id: str,
    expected_unicode_reference_id: str,
) -> tuple[CountryReference, ScriptReference]:
    paths = production_reference_paths()
    country_manifest = verify_cldr_reference_bundle(
        paths["country_manifest"], paths["country_directory"]
    )
    validate_country_authority_manifest(
        paths["country_authority_manifest"],
        country_manifest,
        operational_manifest_path=paths["country_manifest"],
        expected_country_reference_id=expected_country_reference_id,
    )
    country = CountryReference.from_cldr_artifact(
        paths["country_manifest"], paths["country_artifact"]
    )
    scripts = ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )
    if scripts.version != expected_unicode_reference_id:
        raise Phase03Error("PRODUCTION_UNICODE_REFERENCE_ID_MISMATCH")
    return country, scripts

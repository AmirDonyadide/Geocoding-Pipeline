from __future__ import annotations

import json
import string
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Final

from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from .errors import Phase03Error

CLDR_RELEASE: Final = "46.1"
CLDR_COUNTRY_REFERENCE_ID: Final = (
    "country_reference_v2_iso_normative_cldr_46_1_operational"
)
CLDR_COUNTRY_SCHEMA_VERSION: Final = "cldr_country_reference_json_v1"
CLDR_COUNTRY_EXTRACTOR_VERSION: Final = "cldr_country_reference_extractor_v1"
CLDR_SELECTABLE_POLICY_VERSION: Final = "cldr_country_selectability_v1"
_NONSELECTABLE_STATUSES: Final = (
    "deprecated",
    "macroregion",
    "private_use",
    "reserved",
    "special",
    "unknown",
)
_USER_ASSIGNED_ALPHA2: Final = frozenset(
    {"AA", "ZZ"}
    | {f"Q{letter}" for letter in string.ascii_uppercase[12:]}
    | {f"X{letter}" for letter in string.ascii_uppercase}
)


@dataclass(frozen=True, slots=True)
class CldrCountryExtraction:
    canonical_artifact: bytes
    row_count: int
    status_counts: dict[str, int]
    excluded_identifiers: dict[str, tuple[str, ...]]


def cldr_extractor_configuration_fingerprint() -> str:
    return fingerprint(
        {
            "version": CLDR_COUNTRY_EXTRACTOR_VERSION,
            "cldr_release": CLDR_RELEASE,
            "source_paths": [
                "common/supplemental/supplementalData.xml",
                "common/main/en.xml",
                "common/validity/region.xml",
            ],
            "schema_version": CLDR_COUNTRY_SCHEMA_VERSION,
            "selectable_policy": {
                "version": CLDR_SELECTABLE_POLICY_VERSION,
                "required_id_status": "regular",
                "required_fields": [
                    "territory_code",
                    "alpha3_code",
                    "numeric_code",
                    "english_name",
                ],
                "english_name_alt": None,
                "exclude_iso_user_assigned_alpha2": True,
                "exclude_numeric_range": [900, 999],
            },
        }
    )


def _parse_xml(data: bytes, source_name: str) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise Phase03Error("CLDR_SOURCE_XML_INVALID", source_name) from error


def _base26(value: str) -> int:
    result = 0
    for character in value:
        result = result * 26 + (ord(character) - ord("A"))
    return result


def _from_base26(value: int, width: int) -> str:
    characters = ["A"] * width
    for index in range(width - 1, -1, -1):
        value, remainder = divmod(value, 26)
        characters[index] = chr(ord("A") + remainder)
    if value:
        raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")
    return "".join(characters)


def _expand_validity_token(token: str) -> tuple[str, ...]:
    if "~" not in token:
        return (token,)
    if token.count("~") != 1:
        raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")
    start, abbreviated_end = token.split("~")
    end = start[: len(start) - len(abbreviated_end)] + abbreviated_end
    if len(start) != len(end):
        raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")
    if start.isdigit() and end.isdigit():
        lower, upper = int(start), int(end)
        if lower > upper:
            raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")
        return tuple(f"{value:0{len(start)}d}" for value in range(lower, upper + 1))
    if start.isalpha() and end.isalpha() and start.isupper() and end.isupper():
        lower, upper = _base26(start), _base26(end)
        if lower > upper:
            raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")
        return tuple(_from_base26(value, len(start)) for value in range(lower, upper + 1))
    raise Phase03Error("CLDR_VALIDITY_RANGE_INVALID")


def _validity_statuses(data: bytes) -> dict[str, frozenset[str]]:
    root = _parse_xml(data, "region.xml")
    statuses: dict[str, frozenset[str]] = {}
    identifiers_seen: set[str] = set()
    elements = root.findall("./idValidity/id[@type='region']")
    if not elements:
        raise Phase03Error("CLDR_REGION_VALIDITY_MISSING")
    for element in elements:
        status = element.get("idStatus")
        if not status or status in statuses:
            raise Phase03Error("CLDR_REGION_STATUS_INVALID")
        identifiers: list[str] = []
        for token in " ".join(element.itertext()).split():
            identifiers.extend(_expand_validity_token(token))
        if not identifiers or identifiers_seen.intersection(identifiers):
            raise Phase03Error("CLDR_REGION_STATUS_INVALID")
        identifiers_seen.update(identifiers)
        statuses[status] = frozenset(identifiers)
    if set(statuses) != {"regular", *_NONSELECTABLE_STATUSES}:
        raise Phase03Error("CLDR_REGION_STATUS_INVALID")
    return statuses


def _code_mappings(data: bytes) -> dict[str, tuple[str | None, str | None]]:
    root = _parse_xml(data, "supplementalData.xml")
    mappings: dict[str, tuple[str | None, str | None]] = {}
    elements = root.findall("./codeMappings/territoryCodes")
    if not elements:
        raise Phase03Error("CLDR_CODE_MAPPINGS_MISSING")
    for element in elements:
        territory = element.get("type")
        if not territory or territory in mappings:
            raise Phase03Error("CLDR_CODE_MAPPING_DUPLICATE")
        mappings[territory] = (element.get("alpha3"), element.get("numeric"))
    return mappings


def _canonical_english_names(data: bytes) -> dict[str, str]:
    root = _parse_xml(data, "en.xml")
    names: dict[str, str] = {}
    elements = root.findall("./localeDisplayNames/territories/territory")
    if not elements:
        raise Phase03Error("CLDR_ENGLISH_TERRITORIES_MISSING")
    for element in elements:
        if element.get("alt") is not None:
            continue
        territory = element.get("type")
        name = element.text
        if not territory or not name or territory in names:
            raise Phase03Error("CLDR_CANONICAL_NAME_INVALID")
        names[territory] = name
    return names


def extract_cldr_country_reference(
    *,
    supplemental_data_xml: bytes,
    english_territories_xml: bytes,
    region_validity_xml: bytes,
) -> CldrCountryExtraction:
    statuses = _validity_statuses(region_validity_xml)
    mappings = _code_mappings(supplemental_data_xml)
    names = _canonical_english_names(english_territories_xml)
    regular = statuses["regular"]
    excluded: dict[str, list[str]] = {
        f"cldr_status_{status}": sorted(statuses[status])
        for status in _NONSELECTABLE_STATUSES
    }
    excluded["regular_missing_required_mapping"] = []
    excluded["iso_user_assigned"] = []
    records: list[dict[str, str]] = []
    for territory in sorted(regular):
        alpha3, numeric = mappings.get(territory, (None, None))
        name = names.get(territory)
        if alpha3 is None or numeric is None or name is None:
            excluded["regular_missing_required_mapping"].append(territory)
            continue
        if not (
            len(territory) == 2
            and territory.isascii()
            and territory.isalpha()
            and territory.isupper()
            and len(alpha3) == 3
            and alpha3.isascii()
            and alpha3.isalpha()
            and alpha3.isupper()
            and len(numeric) == 3
            and numeric.isascii()
            and numeric.isdigit()
            and name
        ):
            raise Phase03Error("CLDR_SELECTABLE_RECORD_INVALID", territory)
        if territory in _USER_ASSIGNED_ALPHA2 or 900 <= int(numeric) <= 999:
            excluded["iso_user_assigned"].append(territory)
            continue
        records.append(
            {
                "territory_code": territory,
                "alpha3_code": alpha3,
                "numeric_code": numeric,
                "english_name": name,
            }
        )
    for key in ("territory_code", "alpha3_code", "numeric_code", "english_name"):
        if len({record[key] for record in records}) != len(records):
            raise Phase03Error("CLDR_CANONICAL_MAPPING_DUPLICATE", key)
    records_json: list[JsonValue] = [dict(record) for record in records]
    artifact_value: JsonValue = {
        "country_reference_version": CLDR_COUNTRY_REFERENCE_ID,
        "extractor_configuration_fingerprint": (
            cldr_extractor_configuration_fingerprint()
        ),
        "extractor_version": CLDR_COUNTRY_EXTRACTOR_VERSION,
        "records": records_json,
        "schema_version": CLDR_COUNTRY_SCHEMA_VERSION,
        "selectable_territory_policy_version": CLDR_SELECTABLE_POLICY_VERSION,
    }
    return CldrCountryExtraction(
        canonical_artifact=canonical_json_bytes(artifact_value) + b"\n",
        row_count=len(records),
        status_counts={key: len(value) for key, value in sorted(statuses.items())},
        excluded_identifiers={
            key: tuple(value) for key, value in sorted(excluded.items())
        },
    )


def load_canonical_cldr_value(data: bytes) -> dict[str, object]:
    try:
        value = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error("CLDR_CANONICAL_REFERENCE_INVALID") from error
    if not isinstance(value, dict):
        raise Phase03Error("CLDR_CANONICAL_REFERENCE_INVALID")
    return value

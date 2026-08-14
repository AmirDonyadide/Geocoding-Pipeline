from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files
from typing import Any

from .errors import Phase03Error

STREET_DESIGNATOR_RESOURCE_ID = "street_designators_v2"
STREET_DESIGNATOR_RESOURCE_FILE = "street_designators_v2.json"


@dataclass(frozen=True, slots=True)
class StreetDesignator:
    language: str
    position: str
    match_kind: str
    tokens: tuple[str, ...] = ()
    value: str | None = None


@dataclass(frozen=True, slots=True)
class StreetDesignatorResource:
    resource_id: str
    resource_version: str
    artifact_sha256: str
    designators: tuple[StreetDesignator, ...]


def _as_designator(value: Any) -> StreetDesignator:
    if not isinstance(value, dict):
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    shared = {"language", "position", "match_kind"}
    kind = value.get("match_kind")
    expected = shared | ({"tokens"} if kind == "TOKEN_SEQUENCE" else {"value"})
    if set(value) != expected:
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    if value.get("position") not in {"PREFIX", "SUFFIX"}:
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    if not isinstance(value.get("language"), str) or not value["language"]:
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    if kind == "TOKEN_SEQUENCE":
        tokens = value.get("tokens")
        if (
            not isinstance(tokens, list)
            or not tokens
            or any(not isinstance(token, str) or not token for token in tokens)
        ):
            raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
        return StreetDesignator(
            value["language"], value["position"], kind, tuple(tokens)
        )
    if kind == "WORD_SUFFIX" and isinstance(value.get("value"), str) and value["value"]:
        return StreetDesignator(
            value["language"], value["position"], kind, value=value["value"]
        )
    raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")


@lru_cache(maxsize=1)
def load_street_designators() -> StreetDesignatorResource:
    data = (
        files(__package__)
        .joinpath(f"resources/{STREET_DESIGNATOR_RESOURCE_FILE}")
        .read_bytes()
    )
    try:
        value = json.loads(data.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID") from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "resource_id",
        "resource_version",
        "comparison_contract",
        "designators",
    }:
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    if (
        value["schema_version"] != "phase03_street_designators_schema_v1"
        or value["resource_id"] != STREET_DESIGNATOR_RESOURCE_ID
        or not isinstance(value["resource_version"], str)
        or not value["resource_version"]
        or value["comparison_contract"]
        != "NFC tokens; ASCII lower-case only; non-ASCII exact case"
        or not isinstance(value["designators"], list)
    ):
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    designators = tuple(_as_designator(item) for item in value["designators"])
    if len(set(designators)) != len(designators):
        raise Phase03Error("STREET_DESIGNATOR_REFERENCE_INVALID")
    return StreetDesignatorResource(
        resource_id=value["resource_id"],
        resource_version=value["resource_version"],
        artifact_sha256=hashlib.sha256(data).hexdigest(),
        designators=designators,
    )

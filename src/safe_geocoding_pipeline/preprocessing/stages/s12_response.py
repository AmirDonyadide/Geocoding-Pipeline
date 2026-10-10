"""Strict bounded offline response validation, exact feature slices and projection."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

import pyarrow as pa

from . import s12_retrieval_contract as c

VALIDATION = "stage12_response_validation_v1"
EXTRACTION = "stage12_response_extraction_v1"
MAX_BODY = 16 * 1024 * 1024
MAX_DEPTH = 64
NUMBER = re.compile(rb"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
STRINGS = tuple(
    k
    for k in c.CANDIDATE_STRINGS
    if k not in ("feature_id", "geometry_type", "confidence")
)
MEDIA = (
    "application/json",
    "application/geo+json",
    "application/json;charset=utf-8",
    "application/geo+json;charset=utf-8",
)


@dataclass(frozen=True)
class Number:
    """Keep original numeric token spelling for the frozen prefix comparison."""

    token: str

    def binary64(self) -> float:
        value = float(self.token)
        c.require(math.isfinite(value), "RESPONSE_CONTRACT_INVALID")
        return value


@dataclass(frozen=True)
class Parsed:
    value: dict[str, Any]
    feature_slices: tuple[tuple[int, int], ...]


class Parser:
    """Single bounded body; byte positions are authoritative, never reserialization."""

    def __init__(
        self, raw: bytes, *, max_body: int = MAX_BODY, max_depth: int = MAX_DEPTH
    ):
        c.require(len(raw) <= max_body, "RESPONSE_RESOURCE_LIMIT")
        try:
            raw.decode("utf-8", "strict")
        except UnicodeError:
            raise c.Stage12Error("RESPONSE_CONTRACT_INVALID") from None
        self.raw = raw
        self.pos = 0
        self.depth = max_depth
        self.slices: list[tuple[int, int]] = []

    def space(self) -> None:
        while self.pos < len(self.raw) and self.raw[self.pos] in b" \t\r\n":
            self.pos += 1

    def take(self, char: int) -> None:
        c.require(
            self.pos < len(self.raw) and self.raw[self.pos] == char,
            "RESPONSE_CONTRACT_INVALID",
        )
        self.pos += 1

    def string(self) -> str:
        start = self.pos
        self.take(34)
        while self.pos < len(self.raw):
            ch = self.raw[self.pos]
            self.pos += 1
            if ch == 34:
                try:
                    value = json.loads(self.raw[start : self.pos])
                    value.encode("utf-8", "strict")
                    return str(value)
                except (ValueError, UnicodeError):
                    raise c.Stage12Error("RESPONSE_CONTRACT_INVALID") from None
            if ch == 92:
                self.pos += 1
        raise c.Stage12Error("RESPONSE_CONTRACT_INVALID")

    def value(self, depth: int, *, features: bool = False) -> Any:
        self.space()
        c.require(depth <= self.depth, "RESPONSE_RESOURCE_LIMIT")
        c.require(self.pos < len(self.raw), "RESPONSE_CONTRACT_INVALID")
        ch = self.raw[self.pos]
        if ch == 34:
            return self.string()
        if ch == 123:
            result: dict[str, Any] = {}
            self.pos += 1
            self.space()
            if self.pos < len(self.raw) and self.raw[self.pos] == 125:
                self.pos += 1
                return result
            while True:
                self.space()
                key = self.string()
                c.require(key not in result, "RESPONSE_CONTRACT_INVALID")
                self.space()
                self.take(58)
                result[key] = self.value(
                    depth + 1, features=depth == 0 and key == "features"
                )
                self.space()
                c.require(self.pos < len(self.raw), "RESPONSE_CONTRACT_INVALID")
                if self.raw[self.pos] == 125:
                    self.pos += 1
                    return result
                self.take(44)
        if ch == 91:
            items: list[Any] = []
            self.pos += 1
            self.space()
            if self.pos < len(self.raw) and self.raw[self.pos] == 93:
                self.pos += 1
                return items
            while True:
                self.space()
                start = self.pos
                items.append(self.value(depth + 1))
                if features:
                    self.slices.append((start, self.pos - start))
                self.space()
                c.require(self.pos < len(self.raw), "RESPONSE_CONTRACT_INVALID")
                if self.raw[self.pos] == 93:
                    self.pos += 1
                    return items
                self.take(44)
        for token, value in ((b"null", None), (b"true", True), (b"false", False)):
            if self.raw.startswith(token, self.pos):
                self.pos += len(token)
                return value
        match = NUMBER.match(self.raw, self.pos)
        c.require(match is not None, "RESPONSE_CONTRACT_INVALID")
        assert match is not None
        self.pos = match.end()
        number = Number(match.group().decode("ascii"))
        number.binary64()  # Reject nonfinite numeric tokens even in unknown fields.
        return number

    def parse(self) -> Parsed:
        value = self.value(0)
        self.space()
        c.require(
            self.pos == len(self.raw) and type(value) is dict,
            "RESPONSE_CONTRACT_INVALID",
        )
        return Parsed(value, tuple(self.slices))


def media_type(value: str | None) -> str:
    if value is None:
        return "ABSENT"
    # MIME syntax permits case and optional whitespace; only this closed enum persists.
    parts = value.lower().split(";")
    normalized = ";".join(p.strip() for p in parts)
    return normalized if normalized in MEDIA else "OTHER"


def content_encoding(value: str | None) -> str:
    if value is None:
        return "absent"
    return "identity" if value.strip().lower() == "identity" else "OTHER"


def secret_guard(raw: bytes, runtime_key: bytes) -> None:
    c.require(bool(runtime_key), "ENVIRONMENT_AUTH_MISSING")
    c.require(runtime_key not in raw, "SECRET_ECHO_DETECTED")


def optional_string(value: Any) -> str | None:
    c.require(value is None or type(value) is str, "RESPONSE_CONTRACT_INVALID")
    return value if isinstance(value, str) else None


def numeric(value: Any, low: float, high: float) -> float:
    c.require(type(value) is Number, "RESPONSE_CONTRACT_INVALID")
    result = value.binary64()
    c.require(low <= result <= high, "RESPONSE_CONTRACT_INVALID")
    return float(result)


def envelope(obj: dict[str, Any], *, messages: bool = True, bbox: bool = True) -> None:
    for key in ("errors", "warnings"):
        if messages and key in obj:
            c.require(
                type(obj[key]) is list and obj[key] == [], "RESPONSE_CONTRACT_INVALID"
            )
    c.require("crs" not in obj, "RESPONSE_CONTRACT_INVALID")
    if bbox and "bbox" in obj:
        box = obj["bbox"]
        c.require(type(box) is list and len(box) == 4, "RESPONSE_CONTRACT_INVALID")
        numeric(box[0], -180, 180)
        south = numeric(box[1], -90, 90)
        numeric(box[2], -180, 180)
        north = numeric(box[3], -90, 90)
        c.require(south <= north, "RESPONSE_CONTRACT_INVALID")


def compare_echo(query: dict[str, Any], expected: dict[str, Any]) -> None:
    """Exact deployment-pinned paths/values only; no guessed text normalization."""
    for path, value in expected.items():
        current: Any = query
        for component in path.split("."):
            c.require(
                type(current) is dict and component in current,
                "RESPONSE_CONTRACT_INVALID",
            )
            current = current[component]
        c.require(current == value, "RESPONSE_CONTRACT_INVALID")


@dataclass(frozen=True)
class Projection:
    outcome: str
    candidates: tuple[dict[str, Any], ...]
    feature_structures: tuple[Any, ...]
    response_sha256: bytes
    unknown_fields: int


def structural(value: Any) -> Any:
    """Ignore object order/whitespace only; numbers retain exact token spelling."""
    if type(value) is dict:
        return ("object", tuple((k, structural(v)) for k, v in sorted(value.items())))
    if type(value) is list:
        return ("array", tuple(structural(v) for v in value))
    if isinstance(value, Number):
        return ("number", value.token)
    return (type(value).__name__, value)


def extract(
    raw: bytes,
    execution: bytes,
    *,
    size: int,
    http_status: int,
    content_type: str,
    encoding: str,
    layers: frozenset[str],
    sources: frozenset[str],
    expected_echo: dict[str, Any],
    expected_hash: bytes | None = None,
) -> Projection:
    """No partial result escapes. Caller retains safe raw audit on any failure."""
    c.digest(execution)
    c.require(type(size) is int and size > 0, "S12_POLICY_INVALID")
    body_hash = c.sha(raw)
    c.require(
        expected_hash is None or c.digest(expected_hash) == body_hash,
        "S12_RAW_HASH_MISMATCH",
    )
    c.require(
        http_status == 200
        and content_type in MEDIA
        and encoding in ("identity", "absent"),
        "RESPONSE_CONTRACT_INVALID",
    )
    parsed = Parser(raw).parse()
    obj = parsed.value
    envelope(obj)
    c.require(obj.get("type") == "FeatureCollection", "RESPONSE_CONTRACT_INVALID")
    features = obj.get("features")
    c.require(
        type(features) is list and len(features) <= size, "RESPONSE_CONTRACT_INVALID"
    )
    assert isinstance(features, list)
    c.require(len(parsed.feature_slices) == len(features), "RESPONSE_CONTRACT_INVALID")
    if "geocoding" in obj:
        geo = obj["geocoding"]
        c.require(type(geo) is dict, "RESPONSE_CONTRACT_INVALID")
        envelope(geo, bbox=False)
        for field in ("version", "attribution"):
            if field in geo:
                c.require(type(geo[field]) is str, "RESPONSE_CONTRACT_INVALID")
        if "timestamp" in geo:
            timestamp = geo["timestamp"]
            c.require(
                type(timestamp) is Number
                and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", timestamp.token) is not None,
                "RESPONSE_CONTRACT_INVALID",
            )
        if "query" in geo:
            c.require(type(geo["query"]) is dict, "RESPONSE_CONTRACT_INVALID")
            compare_echo(geo["query"], expected_echo)
    candidates = []
    unknown = len(
        set(obj) - {"type", "features", "geocoding", "bbox", "errors", "warnings"}
    )
    for rank, (feature, (offset, length)) in enumerate(
        zip(features, parsed.feature_slices, strict=True), 1
    ):
        c.require(
            type(feature) is dict and feature.get("type") == "Feature",
            "RESPONSE_CONTRACT_INVALID",
        )
        envelope(feature, messages=False)
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        c.require(
            type(properties) is dict and type(geometry) is dict,
            "RESPONSE_CONTRACT_INVALID",
        )
        assert isinstance(properties, dict) and isinstance(geometry, dict)
        c.require(
            geometry.get("type") == "Point" and "crs" not in geometry,
            "RESPONSE_CONTRACT_INVALID",
        )
        coords = geometry.get("coordinates")
        c.require(
            type(coords) is list and len(coords) == 2, "RESPONSE_CONTRACT_INVALID"
        )
        assert isinstance(coords, list)
        longitude, latitude = numeric(coords[0], -180, 180), numeric(coords[1], -90, 90)
        strings = {k: optional_string(properties.get(k)) for k in STRINGS}
        c.require(
            bool(strings["layer"])
            and strings["layer"] in layers
            and bool(strings["source"])
            and strings["source"] in sources,
            "RESPONSE_CONTRACT_INVALID",
        )
        confidence = properties.get("confidence")
        row = {
            "request_execution_id": execution,
            "rank": rank,
            "response_sha256": body_hash,
            "raw_feature_sha256": c.sha(raw[offset : offset + length]),
            "feature_byte_offset": offset,
            "feature_byte_length": length,
            **strings,
            "feature_id": optional_string(feature.get("id")),
            "geometry_type": "Point",
            "longitude": longitude,
            "latitude": latitude,
            "confidence": None if confidence is None else numeric(confidence, 0, 1),
        }
        c.row_bytes("request_candidate", row)
        candidates.append(row)
        unknown += len(set(properties) - set(STRINGS) - {"confidence"})
        unknown += len(
            set(feature)
            - {"type", "id", "properties", "geometry", "bbox", "errors", "warnings"}
        )
        unknown += len(set(geometry) - {"type", "coordinates"})
    return Projection(
        c.SUCCESS[0] if candidates else c.SUCCESS[1],
        tuple(candidates),
        tuple(structural(f) for f in features),
        body_hash,
        unknown,
    )


def compress(raw: bytes, *, level: int = 3) -> bytes:
    """One independent zstd frame. Compression never participates in response ID."""
    c.require(len(raw) <= MAX_BODY, "RESPONSE_RESOURCE_LIMIT")
    return bytes(pa.Codec("zstd", compression_level=level).compress(raw))


def decompress(frame: bytes, *, length: int, expected_hash: bytes) -> bytes:
    c.require(
        type(length) is int and 0 <= length <= MAX_BODY, "RESPONSE_RESOURCE_LIMIT"
    )
    try:
        raw = bytes(pa.Codec("zstd").decompress(frame, length))
    except Exception:
        raise c.Stage12Error("S12_RAW_FRAME_INVALID") from None
    c.require(
        len(raw) == length and c.sha(raw) == c.digest(expected_hash),
        "S12_RAW_HASH_MISMATCH",
    )
    return raw

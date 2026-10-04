"""Frozen Stage 11 semantic core. No protected I/O, transport or normalization."""

from __future__ import annotations

import hashlib
import json
import re
import struct
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import pyarrow as pa

CONTRACT = "stage11_semantic_request_contract_v1"
PROFILE = "stage11_semantic_request_profile_v1"
SCHEMA = "stage11_semantic_request_schema_v1"
ENCODING = "stage11_semantic_request_encoding_v1"
SUMMARY = "stage11_semantic_request_summary_v1"
MANIFEST = "stage11_semantic_request_manifest_v1"
DESIGN_SHA = "ac96b033e2ba7201fbb99ea38cd363d13410c7c4"
BASELINE_SHA = "125b3684a000ea79523f77049ae1a290b0da8109"
DESIGN_TAG = "stage11-semantic-request-deduplication-design-v1"
DOMAIN = b"SAFE:stage11-query-semantic:v1\0"
RELATIONS = ("semantic_request", "hypothesis_request_map")
FIELDS = (
    "contract_version",
    "schema_version",
    "encoding_version",
    "semantic_policy_version",
    "endpoint",
    "search_mode",
    "text",
    "address",
    "postalcode",
    "locality",
    "region",
    "country",
    "boundary_country_namespace",
    "boundary_country",
    "language_policy",
    "layers_policy",
    "sources_policy",
    "spatial_policy",
    "additional_parameter_policy",
)
NULLABLE = ("text", "address", "postalcode", "locality", "region", "country")
CONSTANTS = {
    "contract_version": CONTRACT,
    "schema_version": SCHEMA,
    "encoding_version": ENCODING,
    "semantic_policy_version": PROFILE,
    "region": None,
    "country": None,
    "boundary_country_namespace": "STAGE10_RECOGNIZED_ISO_ALPHA2_V1",
    "language_policy": "NO_REQUEST_LANGUAGE_OVERRIDE",
    "layers_policy": "OMITTED_API_SELECTION",
    "sources_policy": "OMITTED_API_SELECTION",
    "spatial_policy": "NONE",
    "additional_parameter_policy": "REJECT_UNLISTED",
}
PAIRS = (("/v1/search", "FULL_TEXT"), ("/v1/search/structured", "STRUCTURED"))
INTENT_FIELDS = (
    "intent_version",
    "endpoint",
    "search_mode",
    *NULLABLE,
    "boundary_country",
    "retrieval_policy_slot",
)
DESIGN_DOCUMENTS = tuple(
    sorted(
        "docs/stages/" + n
        for n in (
            "STAGE11_SEMANTIC_REQUEST_DEDUPLICATION.md",
            "STAGE11_DATA_CONTRACT.md",
            "STAGE11_DEVELOPMENT_EVALUATION.md",
            "STAGE11_DESIGN_REVIEW.md",
        )
    )
)
ERRORS = frozenset(
    """
S11_INPUT_BINDING_INVALID S11_UPSTREAM_ID_INVALID S11_INTENT_CONTRACT_INVALID
S11_COUNTRY_BOUNDARY_INVALID S11_PARAMETER_POLICY_INVALID S11_ENCODING_INVALID
S11_ID_COLLISION S11_ID_RECOMPUTE_MISMATCH S11_MAP_TOTALITY_INVALID
S11_MAP_PROJECTION_MISMATCH S11_RESOURCE_FAILURE S11_CHECKPOINT_INVALID
S11_PUBLICATION_INVALID S11_PRIVACY_GUARD_FAILURE
""".split()
)


class Stage11Error(ValueError):
    """Static codes only; arbitrary engine exceptions must never be rendered."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Stage11Error(code)


def canonical(value: Any) -> bytes:
    """Metadata JSON only. Scientific core identity uses framed binary below."""

    def check(v: Any) -> None:
        if isinstance(v, dict):
            require(all(type(k) is str for k in v), "S11_ENCODING_INVALID")
            for child in v.values():
                check(child)
        elif isinstance(v, (tuple, list)):
            for child in v:
                check(child)
        else:
            require(v is None or type(v) in (str, int, bool), "S11_ENCODING_INVALID")

    check(value)
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        require(key not in result, "S11_ENCODING_INVALID")
        result[key] = value
    return result


def _not_integer(_: str) -> Any:
    raise Stage11Error("S11_ENCODING_INVALID")


def decode_json(raw: bytes) -> dict[str, Any]:
    try:
        result = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_not_integer,
            parse_constant=_not_integer,
        )
        require(type(result) is dict, "S11_ENCODING_INVALID")
        require(canonical(result) == raw, "S11_ENCODING_INVALID")
        return dict(result)
    except (UnicodeError, json.JSONDecodeError):
        raise Stage11Error("S11_ENCODING_INVALID") from None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def u64(value: int) -> bytes:
    require(type(value) is int and 0 <= value < 2**64, "S11_ENCODING_INVALID")
    return struct.pack(">Q", value)


def encoded(value: Any) -> bytes:
    if value is None:
        return b"\0"
    if type(value) is bool:
        return b"\x04" + bytes((int(value),))
    if type(value) is int:
        return b"\x03" + u64(value)
    if type(value) is bytes:
        return b"\x02" + u64(len(value)) + value
    if type(value) is str:
        try:
            raw = value.encode("utf-8", errors="strict")
        except UnicodeError:
            raise Stage11Error("S11_ENCODING_INVALID") from None
        return b"\x01" + u64(len(raw)) + raw
    if type(value) in (tuple, list):
        return b"\x05" + framed(value)
    raise Stage11Error("S11_ENCODING_INVALID")


def framed(values: Sequence[Any]) -> bytes:
    return u64(len(values)) + b"".join(encoded(v) for v in values)


def identity(domain: str, *values: Any) -> bytes:
    return hashlib.sha256(
        b"SAFE:" + domain.encode("ascii") + b"\0" + framed(values)
    ).digest()


def validate_core(core: Mapping[str, Any]) -> None:
    require(
        isinstance(core, Mapping) and set(core) == set(FIELDS),
        "S11_PARAMETER_POLICY_INVALID",
    )
    for key in FIELDS:
        value = core[key]
        require(
            (value is None and key in NULLABLE) or type(value) is str,
            "S11_INTENT_CONTRACT_INVALID",
        )
        if isinstance(value, str):
            require(len(value) > 0, "S11_INTENT_CONTRACT_INVALID")
            try:
                value.encode("utf-8", errors="strict")
            except UnicodeError:
                raise Stage11Error("S11_ENCODING_INVALID") from None
    require(
        all(core[k] == v for k, v in CONSTANTS.items()), "S11_PARAMETER_POLICY_INVALID"
    )
    require(
        (core["endpoint"], core["search_mode"]) in PAIRS, "S11_INTENT_CONTRACT_INVALID"
    )
    require(
        re.fullmatch(r"[A-Z]{2}", core["boundary_country"]) is not None,
        "S11_COUNTRY_BOUNDARY_INVALID",
    )
    if core["search_mode"] == "FULL_TEXT":
        require(
            core["text"] is not None and all(core[k] is None for k in NULLABLE[1:]),
            "S11_INTENT_CONTRACT_INVALID",
        )
    else:
        require(
            core["text"] is None
            and core["address"] is not None
            and (core["postalcode"] is not None or core["locality"] is not None)
            and core["region"] is None
            and core["country"] is None,
            "S11_INTENT_CONTRACT_INVALID",
        )


def project(intent: Mapping[str, Any], selection_status: str) -> dict[str, Any]:
    require(
        isinstance(intent, Mapping) and set(intent) == set(INTENT_FIELDS),
        "S11_PARAMETER_POLICY_INVALID",
    )
    require(
        intent["intent_version"] == "stage10_query_intent_v1"
        and intent["retrieval_policy_slot"] == "SAFE_PELIAS_COMMON_RETRIEVAL_V1"
        and selection_status == "ALL_ELIGIBLE_CATALOG",
        "S11_INTENT_CONTRACT_INVALID",
    )
    core = {k: intent[k] if k in intent else CONSTANTS[k] for k in FIELDS}
    validate_core(core)
    return core


def core_bytes(core: Mapping[str, Any]) -> bytes:
    validate_core(core)
    return DOMAIN + framed(tuple((k, core[k]) for k in FIELDS))


def semantic_id(payload: bytes) -> bytes:
    """Internal seam for synthetic collision injection; production uses full SHA-256."""
    return hashlib.sha256(payload).digest()


def decode_core(raw: bytes) -> dict[str, Any]:
    """Strict inverse for validation/checkpoint evidence; rejects extra framing."""
    require(raw.startswith(DOMAIN), "S11_ENCODING_INVALID")
    position = len(DOMAIN)

    def take(length: int) -> bytes:
        nonlocal position
        require(0 <= length <= len(raw) - position, "S11_ENCODING_INVALID")
        result = raw[position : position + length]
        position += length
        return result

    def count() -> int:
        return int.from_bytes(take(8), "big")

    def string() -> str:
        require(take(1) == b"\x01", "S11_ENCODING_INVALID")
        try:
            return take(count()).decode("utf-8", errors="strict")
        except UnicodeError:
            raise Stage11Error("S11_ENCODING_INVALID") from None

    require(count() == len(FIELDS), "S11_ENCODING_INVALID")
    core: dict[str, Any] = {}
    for field in FIELDS:
        require(take(1) == b"\x05" and count() == 2, "S11_ENCODING_INVALID")
        require(string() == field, "S11_ENCODING_INVALID")
        require(position < len(raw), "S11_ENCODING_INVALID")
        if raw[position] == 0:
            take(1)
            core[field] = None
        else:
            core[field] = string()
    require(position == len(raw), "S11_ENCODING_INVALID")
    validate_core(core)
    require(core_bytes(core) == raw, "S11_ENCODING_INVALID")
    return core


def contract_asset(root: Path) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT,
        "design_documents": [
            {"path": p, "sha256": sha256_file(root / p)} for p in DESIGN_DOCUMENTS
        ],
    }


def profile_asset(contract_sha: str) -> dict[str, Any]:
    return {
        "profile_version": PROFILE,
        "contract_sha256": contract_sha,
        "input_policy": "ALL_ACCEPTED_HYPOTHESES",
        "stage10_policy_slot": "SAFE_PELIAS_COMMON_RETRIEVAL_V1",
        "core_constants": CONSTANTS,
    }


def descriptor(name: str) -> dict[str, Any]:
    require(name in RELATIONS, "S11_ENCODING_INVALID")
    fields: list[dict[str, Any]] = [
        {
            "name": "query_semantic_id",
            "type": "fixed_size_binary[32]",
            "nullable": False,
        }
    ]
    if name == "semantic_request":
        fields.append(
            {
                "name": "core",
                "type": "struct",
                "nullable": False,
                "fields": [
                    {"name": k, "type": "large_string", "nullable": k in NULLABLE}
                    for k in FIELDS
                ],
            }
        )
    else:
        fields.insert(
            0,
            {
                "name": "hypothesis_id",
                "type": "fixed_size_binary[32]",
                "nullable": False,
            },
        )
    return {
        "schema_version": SCHEMA,
        "encoding_version": ENCODING,
        "relation": name,
        "fields": fields,
        "primary_key": fields[0]["name"],
        "order": "UNSIGNED_PRIMARY_KEY_ASCENDING",
        "constants": CONSTANTS,
        "endpoint_mode_pairs": PAIRS,
        "constraints": {
            "all_fields_required": True,
            "unknown_fields_rejected": True,
            "empty_strings_rejected": True,
            "strict_utf8": True,
            "full_text": {"required": ["text"], "null": list(NULLABLE[1:])},
            "structured": {
                "required": ["address"],
                "at_least_one": ["postalcode", "locality"],
                "null": ["text", "region", "country"],
            },
            "boundary_country_pattern": "^[A-Z]{2}$",
            "normalization": "NONE",
            "foreign_keys": {}
            if name == "semantic_request"
            else {
                "hypothesis_id": "accepted_stage10.query_hypothesis.hypothesis_id",
                "query_semantic_id": "semantic_request.query_semantic_id",
            },
            "orphans": "REJECT",
            "map_projection": "EXACT_CANONICAL_BYTES",
        },
    }


@cache
def schema(name: str) -> Any:
    desc = descriptor(name)
    fields = [pa.field("query_semantic_id", pa.binary(32), nullable=False)]
    if name == "semantic_request":
        fields.append(
            pa.field(
                "core",
                pa.struct(
                    [
                        pa.field(k, pa.large_string(), nullable=k in NULLABLE)
                        for k in FIELDS
                    ]
                ),
                nullable=False,
            )
        )
    else:
        fields.insert(0, pa.field("hypothesis_id", pa.binary(32), nullable=False))
    return pa.schema(
        fields, metadata={b"stage11_descriptor": canonical(desc), b"protected": b"true"}
    )


def descriptor_sha(name: str) -> bytes:
    return hashlib.sha256(canonical(descriptor(name))).digest()


def relation_digest(name: str, count: int, rows: Any) -> bytes:
    digest = hashlib.sha256(
        b"SAFE:stage11-relation:v1\0" + framed((name, descriptor_sha(name), count))
    )
    previous = None
    seen = 0
    for row in rows:
        require(set(row) == set(schema(name).names), "S11_MAP_TOTALITY_INVALID")
        key = row[schema(name).names[0]]
        require(
            type(key) is bytes
            and len(key) == 32
            and (previous is None or previous < key),
            "S11_MAP_TOTALITY_INVALID",
        )
        value = row["query_semantic_id"]
        require(type(value) is bytes and len(value) == 32, "S11_MAP_TOTALITY_INVALID")
        if name == "semantic_request":
            value = core_bytes(row["core"])
            require(semantic_id(value) == key, "S11_ID_RECOMPUTE_MISMATCH")
        digest.update(framed((key, value)))
        previous = key
        seen += 1
    require(seen == count, "S11_MAP_TOTALITY_INVALID")
    return digest.digest()

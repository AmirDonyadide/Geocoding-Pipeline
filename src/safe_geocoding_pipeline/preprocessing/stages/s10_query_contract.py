"""Owner-frozen Stage 10 types, identities and privacy-safe invariants.

This module performs no input discovery or protected I/O. Stage 10 intent
identity is deliberately separate from future complete-request identity.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

CONTRACT = "stage10_multi_hypothesis_query_contract_v1"
PROFILE = "stage10_multi_hypothesis_query_profile_v1"
SCHEMA = "stage10_multi_hypothesis_query_schema_v1"
INTENT = "stage10_query_intent_v1"
ENCODING = "stage10_query_logical_encoding_v1"
MANIFEST = "stage10_query_manifest_v1"
SUMMARY = "stage10_query_generation_summary_v1"
MODE = "ALL_ELIGIBLE_CATALOG"
POLICY = "SAFE_PELIAS_COMMON_RETRIEVAL_V1"
DESIGN_COMMIT = "ca0bac7acd8bae709e171c481ddea52df3e5304d"
DESIGN_MERGE = "1443bb3b3c1bb50220bf38231e01552c66c4eaee"
DESIGN_PACKAGE_SHA256 = (
    "d76d2e3d865b3b2cf6c08b080fec34135b7b6fa4736ded1d50c48c1c92645fc2"
)
FAMILIES = tuple(f"Q{i}" for i in range(1, 7))
ROLES = ("STANDARD", "NATIVE")
CONTEXT_CEILING = 5
ROW_CEILING = 10
ROLE_CEILINGS = {"STANDARD": 4, "NATIVE": 5}
RUNTIME = ("3.14.3", "16.0.0", "25.0.0", "1.5.5")
REASONS = tuple(
    """
REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE COUNTRY_CONTEXT_UNAVAILABLE
SOURCE_BOUNDARY_UNAVAILABLE SOURCE_FIELD_UNAVAILABLE MALFORMED_UPSTREAM_EVIDENCE
PARSER_EVIDENCE_UNUSABLE UNSUPPORTED_SCRIPT_TRANSLITERATION
TRANSLITERATION_UNSUPPORTED_OUTPUT UNIT_ALIGNMENT_AMBIGUOUS UNIT_SOURCE_FIELD_CONFLICT
CONTRADICTION_GATE INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE ADMIN_LEVEL_NOT_ESTABLISHED
PARSER_ONLY_FIELD_EXCLUDED FAMILY_INELIGIBLE EMPTY_RESULT_AFTER_TRANSFORMATION
EXACT_SEMANTIC_DUPLICATE QUERY_BUDGET_SUPPRESSION
""".split()
)
SELECTORS = (
    "CANDIDATE_V1",
    "OCCURRENCE_V1",
    "SOURCE_CONTEXT_V1",
    "SOURCE_LINES_V1",
    "PARSER_COMPONENTS_V1",
    "SOURCE_REFERENCE_V1",
    "REFERENCE_WITNESSES_V1",
)
STRUCTS = {
    "QueryIntent": "intent_version:T endpoint:T search_mode:T text:T? address:T? postalcode:T? locality:T? region:T? country:T? boundary_country:T retrieval_policy_slot:T",
    "SelectorCertificate": "selector_id:T selected_count:U selected_stream_sha256:D",
    "TransformStep": "ordinal:U8 transform_id:T transform_asset_binding:D? input_value_sha256:D output_value_sha256:D",
    "FieldDecision": "field:T disposition:T reason_codes:[T]",
    "RemovedLine": "source_slot:U8 start_codepoint:U end_codepoint_exclusive:U category:T grammar_id:T stage08_component_ordinal:U",
}
RELATIONS = {
    "query_hypothesis": "hypothesis_id:D query_context_id:D stable_source_row_id_v1:D stage08_representation:T stage06_exact_candidate_id:D representation_fingerprint:D intent:QueryIntent generation_rank:U8 selection_status:T",
    "query_family_decision": "family_decision_id:D query_context_id:D stable_source_row_id_v1:D stage08_representation:T stage06_exact_candidate_id:D family:T eligibility_state:T membership_state:T hypothesis_id:D? primary_reason:T? reason_codes:[T] eligibility_rule_id:T lineage:[SelectorCertificate] transformations:[TransformStep] field_decisions:[FieldDecision] removed_lines:[RemovedLine]",
}
PRIMARY_KEYS = {
    "query_hypothesis": ("hypothesis_id",),
    "query_family_decision": ("family_decision_id",),
}
ORDER_KEYS = {
    "query_hypothesis": ("query_context_id", "representation_fingerprint"),
    "query_family_decision": ("query_context_id", "family"),
}
INTENT_FIELDS = tuple(t.split(":")[0] for t in STRUCTS["QueryIntent"].split())


class Stage10Error(ValueError):
    """Static diagnostic codes only. Never insert query/source values."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Stage10Error(code)


def require_runtime() -> None:
    actual = (
        ".".join(map(str, sys.version_info[:3])),
        unicodedata.unidata_version,
        pa.__version__,
        duckdb.__version__,
    )
    require(actual == RUNTIME, "STAGE10_EXACT_RUNTIME_REQUIRED")


def canonical(value: Any) -> bytes:
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


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "STAGE10_DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _not_integer(_: str) -> Any:
    raise Stage10Error("STAGE10_NON_INTEGER_JSON_NUMBER")


def read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(
            path.read_bytes(),
            object_pairs_hook=_pairs,
            parse_float=_not_integer,
            parse_constant=_not_integer,
        )
    except (UnicodeError, json.JSONDecodeError):
        raise Stage10Error("STAGE10_INVALID_JSON") from None
    require(isinstance(result, dict), "STAGE10_JSON_OBJECT_REQUIRED")
    return dict(result)


def value_chunks(value: Any) -> Iterator[bytes]:
    """Exact typed E; string payloads stream in fixed code-point chunks."""
    if value is None:
        yield b"\x00"
    elif isinstance(value, bool):
        yield b"\x04" + bytes((int(value),))
    elif isinstance(value, str):
        # A giant string is already an accepted scalar; do not create another
        # whole-string UTF-8 allocation merely to hash it.
        size = sum(
            len(value[i : i + 65536].encode("utf-8"))
            for i in range(0, len(value), 65536)
        )
        yield b"\x01" + struct.pack(">Q", size)
        for i in range(0, len(value), 65536):
            yield value[i : i + 65536].encode("utf-8")
    elif isinstance(value, bytes):
        yield b"\x02" + struct.pack(">Q", len(value))
        yield value
    elif isinstance(value, int):
        require(0 <= value < 2**64, "STAGE10_UINT64_INVALID")
        yield b"\x03" + struct.pack(">Q", value)
    elif isinstance(value, (tuple, list)):
        yield b"\x05" + struct.pack(">Q", len(value))
        for item in value:
            yield from value_chunks(item)
    else:
        raise Stage10Error("STAGE10_UNTYPED_IDENTITY_VALUE")


def framed(values: Sequence[Any]) -> Iterator[bytes]:
    yield struct.pack(">Q", len(values))
    for value in values:
        yield from value_chunks(value)


def identity(domain: str, *values: Any) -> bytes:
    digest = hashlib.sha256(b"SAFE:" + domain.encode("ascii") + b"\0")
    for chunk in framed(values):
        digest.update(chunk)
    return digest.digest()


def _semantic(parent: str, name: str) -> str:
    if parent == "QueryIntent":
        return "QUERY_HYPOTHESIS"
    if parent == "RemovedLine" or name in (
        "stable_source_row_id_v1",
        "stage08_representation",
        "stage06_exact_candidate_id",
    ):
        return "SOURCE_LINEAGE"
    if parent == "SelectorCertificate" or name == "lineage":
        return "EVIDENCE_LINEAGE"
    if (
        name.endswith("_id")
        or name.endswith("_fingerprint")
        or name == "generation_rank"
    ):
        return "MECHANICAL_INDEX"
    return "QUERY_HYPOTHESIS_PROVENANCE"


def data_type(spec: str) -> Any:
    scalars = {
        "D": pa.binary(32),
        "T": pa.large_string(),
        "U": pa.uint64(),
        "U8": pa.uint8(),
    }
    if spec in scalars:
        return scalars[spec]
    if spec.startswith("["):
        return pa.list_(pa.field("element", data_type(spec[1:-1]), nullable=False))
    return pa.struct(_fields(spec, STRUCTS[spec]))


def _fields(parent: str, specification: str) -> list[Any]:
    result = []
    for token in specification.split():
        name, kind = token.split(":")
        result.append(
            pa.field(
                name,
                data_type(kind.rstrip("?")),
                nullable=kind.endswith("?"),
                metadata={b"semantic_class": _semantic(parent, name).encode("ascii")},
            )
        )
    return result


@cache
def schema(name: str) -> Any:
    require(name in RELATIONS, "STAGE10_UNKNOWN_RELATION")
    return pa.schema(
        _fields(name, RELATIONS[name]),
        metadata={
            b"stage10_schema_version": SCHEMA.encode(),
            b"scientific_boundary": b"QUERY_HYPOTHESIS_ONLY",
            b"protected": b"true",
        },
    )


def ordered_values(row: Mapping[str, Any], arrow_schema: Any) -> tuple[Any, ...]:
    def convert(value: Any, kind: Any) -> Any:
        if value is None:
            return None
        if pa.types.is_struct(kind):
            return tuple(convert(value[f.name], f.type) for f in kind)
        if pa.types.is_list(kind) or pa.types.is_large_list(kind):
            return tuple(convert(v, kind.value_type) for v in value)
        return value

    return tuple(convert(row[f.name], f.type) for f in arrow_schema)


@cache
def schema_fingerprint(name: str) -> bytes:
    # Source descriptor binds types, nullability, order, metadata and all PK/FK
    # and enum/bound requirements in the immutable owner-reviewed package.
    specification = RELATIONS.get(name, SUMMARY)
    return identity(
        "stage10-schema:v1",
        SCHEMA,
        name,
        specification,
        tuple(sorted(STRUCTS.items())),
        PRIMARY_KEYS.get(name, ()),
        ORDER_KEYS.get(name, ()),
        REASONS,
        SELECTORS,
        bytes.fromhex(DESIGN_PACKAGE_SHA256),
    )


@cache
def schema_bundle_fingerprint() -> bytes:
    return identity(
        "stage10-schema-bundle:v1",
        SCHEMA,
        tuple(
            (n, schema_fingerprint(n)) for n in (*RELATIONS, "query_generation_summary")
        ),
    )


@cache
def contract_fingerprint() -> bytes:
    return identity(
        "stage10-contract:v1",
        CONTRACT,
        bytes.fromhex(DESIGN_PACKAGE_SHA256),
        schema_bundle_fingerprint(),
        FAMILIES,
        ROLES,
        REASONS,
        SELECTORS,
        CONTEXT_CEILING,
        ROW_CEILING,
        tuple(ROLE_CEILINGS.items()),
        ENCODING,
    )


def budget_fingerprint() -> bytes:
    return identity(
        "stage10-budget:v1", MODE, None, FAMILIES, CONTEXT_CEILING, ROW_CEILING
    )


def science_fingerprint(asset_binding: bytes) -> bytes:
    versions = tuple(f"stage10_q{i}_eligibility_v1" for i in range(1, 7)) + (
        "stage10_exact_query_format_v1",
        "stage10_selector_v1",
    )
    return identity(
        "stage10-science:v1",
        contract_fingerprint(),
        schema_bundle_fingerprint(),
        versions,
        asset_binding,
    )


def intent_values(intent: Mapping[str, Any]) -> tuple[Any, ...]:
    require(set(intent) == set(INTENT_FIELDS), "STAGE10_INTENT_FIELDS_INVALID")
    return tuple(intent[n] for n in INTENT_FIELDS)


def validate_intent(intent: Mapping[str, Any]) -> None:
    intent_values(intent)
    require(
        intent["intent_version"] == INTENT
        and intent["retrieval_policy_slot"] == POLICY,
        "STAGE10_INTENT_VERSION_INVALID",
    )
    require(
        isinstance(intent["boundary_country"], str)
        and re.fullmatch(r"[A-Z]{2}", intent["boundary_country"]) is not None,
        "STAGE10_COUNTRY_BOUNDARY_INVALID",
    )
    structured = ("address", "postalcode", "locality", "region", "country")
    if intent["search_mode"] == "FULL_TEXT":
        require(
            intent["endpoint"] == "/v1/search"
            and isinstance(intent["text"], str)
            and bool(intent["text"])
            and all(intent[n] is None for n in structured),
            "STAGE10_FULL_INTENT_INVALID",
        )
    elif intent["search_mode"] == "STRUCTURED":
        require(
            intent["endpoint"] == "/v1/search/structured"
            and intent["text"] is None
            and isinstance(intent["address"], str)
            and bool(intent["address"])
            and any(intent[n] is not None for n in ("postalcode", "locality"))
            and all(
                intent[n] is None or isinstance(intent[n], str) and bool(intent[n])
                for n in structured
            )
            and intent["region"] is None
            and intent["country"] is None,
            "STAGE10_STRUCTURED_INTENT_INVALID",
        )
    else:
        raise Stage10Error("STAGE10_SEARCH_MODE_INVALID")


def intent_fingerprint(intent: Mapping[str, Any]) -> bytes:
    validate_intent(intent)
    return identity("stage10-intent:v1", intent_values(intent))


def full_intent(text: str, country: str) -> dict[str, Any]:
    return dict(
        zip(
            INTENT_FIELDS,
            (
                INTENT,
                "/v1/search",
                "FULL_TEXT",
                text,
                None,
                None,
                None,
                None,
                None,
                country,
                POLICY,
            ),
            strict=True,
        )
    )


def context_id(upstream_binding: bytes, source_id: bytes, role: str) -> bytes:
    require(
        len(upstream_binding) == len(source_id) == 32 and role in ROLES,
        "STAGE10_CONTEXT_ID_INPUT_INVALID",
    )
    return identity("stage10-context:v1", upstream_binding, source_id, role)

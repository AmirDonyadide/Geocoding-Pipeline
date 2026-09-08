"""Frozen Stage 9 types and identities; no input access or reference lookups.

The only scientific relations are the six in the owner-approved design. Public
reference text and protected argument *pointers* have deliberately different
types. No source value, parser value, coordinate or corrected value is added to
the evidence schema. Diagnostics contain closed codes, never queried values.
"""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import unicodedata
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa


CONTRACT_VERSION = "stage09_offline_reference_evidence_contract_v1"
PROFILE_VERSION = "stage09_offline_reference_evidence_profile_v1"
SCHEMA_VERSION = "stage09_offline_reference_evidence_schema_v1"
NORMALIZATION_VERSION = "stage09_lookup_normalization_v1"
MANIFEST_VERSION = "stage09_reference_manifest_v1"
DESIGN_SHA256 = "401945f7866211cb393f9b4e6f93c11c2d03fcaed694b7e79e1c53e1f5d8c200"
LOCK_SHA256 = "61cc5850372886eb4ba6477a178ebd74f6ca878815036874ad47069ca32a1c63"
DESIGN_COMMIT = "f85510f938a8506bf3d4a4f8d2b908d801957414"
ISO = "ISO_CODES"
LIA = "LIBADDRESSINPUT_METADATA"
GN = "GEONAMES_POSTAL"
FAMILIES = (ISO, LIA, GN)
STATES = ("SUPPORTED", "CONTRADICTED", "NOT_FOUND", "NOT_EVALUABLE")
COUNTRY_STATES = ("COUNTRY_SUPPORTED", "COUNTRY_CONTRADICTED", "COUNTRY_UNRESOLVED")
REASONS = tuple(
    """
EXACT_REFERENCE_SUPPORT EXPLICIT_RULE_SUPPORT EXPLICIT_RULE_CONFLICT
EXPLICIT_CODE_COUNTRY_SUPPORT EXPLICIT_CODE_COUNTRY_CONFLICT
VALUE_ABSENT_FROM_REFERENCE RELATION_ABSENT_FROM_REFERENCE
REFERENCE_ASSOCIATION_MISMATCH MISSING_COMPONENT AMBIGUOUS_COMPONENT_SET
COUNTRY_CONTEXT_UNRESOLVED COUNTRY_NOT_COVERED COMPONENT_CAPABILITY_MISSING
CAPABILITY_NOT_CONFIGURED REFERENCE_GRANULARITY_INSUFFICIENT
PATTERN_DIALECT_UNSUPPORTED ALTERNATE_RULE_SEMANTICS_UNSUPPORTED
NO_COUNTRY_PATTERN NO_PREFIX_RULE ADMIN_IDENTITY_UNRESOLVED
COUNTRY_FORMAT_PREREQUISITE_FAILED REFERENCE_INTERNAL_CONFLICT
SOURCE_ONLY_QUESTION EXPLICIT_CODE_NOT_IDENTIFIED TEMPORAL_SCOPE_UNSUPPORTED
METADATA_TREE_CAPABILITY_DISABLED
""".split()
)
CONTRADICTIONS = (
    "FORMAT_RULE_CONFLICT",
    "PREFIX_RULE_CONFLICT",
    "EXPLICIT_CODE_COUNTRY_CONFLICT",
)
SCOPES = ("SOURCE_ROW", "PARSER_CANDIDATE")
ISO_NORM = "ISO_CODE_ASCII_UPPER_V1"
NAME_NORM = "NAME_NFC_LOWER_U16_V1"
FORM_NORM = "POSTCODE_FORM_ASCII_UPPER_V1"
EXACT_NORM = "POSTCODE_EXACT_V1"
SEPARATOR_NORM = "POSTCODE_SEPARATORS_V1"
NO_NORM = "NOT_APPLIED_V1"
NORMALIZATIONS = (ISO_NORM, NAME_NORM, FORM_NORM, EXACT_NORM, SEPARATOR_NORM, NO_NORM)
SEMANTIC_RUNTIME = ("3.14.3", "16.0.0", "25.0.0", "1.5.5")
POSTCODE_SEPARATORS = {
    "JP": (3, "-", 4),
    "PL": (2, "-", 3),
    "PT": (4, "-", 3),
    "BR": (5, "-", 3),
    "SE": (3, " ", 2),
    "CZ": (3, " ", 2),
    "SK": (3, " ", 2),
}
SOURCE_FIELDS = {
    "COUNTRY_CODE": "stage03_clean_country_iso_code",
    "POSTCODE": "stage03_clean_postcode",
    "LOCALITY": "stage03_clean_city",
    "ADMIN": "stage03_clean_region_in_country",
}
PARSER_LABELS = {
    "POSTCODE": "PARSER_POSTCODE",
    "LOCALITY": "PARSER_CITY",
    "ADMIN": "PARSER_STATE",
    "STREET": "PARSER_ROAD",
    "HOUSE_NUMBER": "PARSER_HOUSE_NUMBER",
    "PARSER_COUNTRY_CODE": "PARSER_COUNTRY",
}


class Stage09Error(ValueError):
    """A fail-closed, privacy-safe error containing a static diagnostic code."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Stage09Error(code)


def require_runtime() -> None:
    actual = (
        ".".join(map(str, sys.version_info[:3])),
        unicodedata.unidata_version,
        pa.__version__,
        duckdb.__version__,
    )
    require(actual == SEMANTIC_RUNTIME, "STAGE09_EXACT_RUNTIME_REQUIRED")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _no_float(value: str) -> Any:
    raise Stage09Error("NON_INTEGER_JSON_NUMBER")


def read_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(
            path.read_bytes(),
            object_pairs_hook=_unique_pairs,
            parse_float=_no_float,
            parse_constant=_no_float,
        )
    except (UnicodeError, json.JSONDecodeError):
        raise Stage09Error("INVALID_JSON") from None
    require(isinstance(result, dict), "JSON_OBJECT_REQUIRED")
    return dict(result)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def typed_chunks(value: Any) -> Iterator[bytes]:
    """E's typed values. Iterable lists permit constant-memory relation hashing."""
    if value is None:
        yield b"\x00"
    elif isinstance(value, bool):
        yield b"\x04" + bytes((int(value),))
    elif isinstance(value, bytes):
        require(len(value) == 32, "DIGEST_WIDTH_INVALID")
        yield b"\x01" + value
    elif isinstance(value, str):
        raw = value.encode("utf-8", errors="strict")
        yield b"\x02" + struct.pack(">Q", len(raw))
        yield raw
    elif isinstance(value, int):
        require(0 <= value < 2**64, "UINT64_INVALID")
        yield b"\x03" + struct.pack(">Q", value)
    elif isinstance(value, (tuple, list)):
        yield b"\x05" + struct.pack(">Q", len(value))
        for item in value:
            yield from typed_chunks(item)
    else:
        raise Stage09Error("UNTYPED_IDENTITY_VALUE")


def framed(value: Any) -> bytes:
    return b"".join(typed_chunks(value))


def identity(domain: str, values: Sequence[Any]) -> bytes:
    digest = hashlib.sha256(struct.pack(">Q", 4))
    for item in ("SAFE_STAGE09", "V1", domain, tuple(values)):
        for chunk in typed_chunks(item):
            digest.update(chunk)
    return digest.digest()


def ascii_upper(value: str) -> str:
    return value.translate(
        str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    )


def normalize(method: str, value: str, country: str = "UNRESOLVED") -> str:
    require(method in NORMALIZATIONS and method != NO_NORM, "NORMALIZATION_NOT_ENABLED")
    if method == NAME_NORM:
        require(unicodedata.unidata_version == "16.0.0", "UNICODE_RUNTIME_REQUIRED")
        return unicodedata.normalize("NFC", value).lower()
    result = ascii_upper(value)
    if method == SEPARATOR_NORM:
        require(country in POSTCODE_SEPARATORS, "POSTCODE_SEPARATOR_COUNTRY_INVALID")
        left, separator, right = POSTCODE_SEPARATORS[country]
        pattern = rf"[0-9]{{{left}}}{re.escape(separator)}[0-9]{{{right}}}"
        if re.fullmatch(pattern, result):
            result = result[:left] + result[left + 1 :]
    return result


@dataclass(frozen=True)
class Question:
    question_id: str
    roles: tuple[str, ...]
    capability: str
    references: tuple[str, ...]
    claim_scope: str
    granularity: str

    def as_tuple(self) -> tuple[Any, ...]:
        return (
            self.question_id,
            self.roles,
            self.capability,
            self.references,
            self.claim_scope,
            self.granularity,
        )


def _question(
    number: int,
    roles: str,
    capability: str,
    references: tuple[str, ...],
    granularity: str,
) -> Question:
    claim = (
        "CODE_COUNTRY_RELATION"
        if number in (1, 2, 14)
        else "FROZEN_METADATA_RULE"
        if number in (3, 4, 8, 15)
        else "REFERENCE_SNAPSHOT"
    )
    return Question(
        f"Q{number:02}",
        tuple(roles.split()),
        capability,
        references,
        claim,
        granularity,
    )


CATALOG = (
    _question(1, "COUNTRY_CODE", "COUNTRY_CONTEXT", (ISO,), "COUNTRY_CODE"),
    _question(2, "TRUSTED_COUNTRY ADMIN", "COUNTRY_CONTEXT", (ISO,), "FULL_ADMIN_CODE"),
    _question(3, "TRUSTED_COUNTRY", "FORMAT", (LIA,), "METADATA"),
    _question(
        4, "TRUSTED_COUNTRY POSTCODE", "POSTCODE_PATTERN", (LIA,), "FULL_POSTCODE"
    ),
    _question(
        5, "TRUSTED_COUNTRY POSTCODE", "POSTCODE_EXISTENCE", (GN,), "FULL_POSTCODE"
    ),
    _question(
        6,
        "TRUSTED_COUNTRY POSTCODE LOCALITY",
        "POSTCODE_LOCALITY",
        (GN,),
        "FULL_POSTCODE",
    ),
    _question(
        7, "TRUSTED_COUNTRY POSTCODE ADMIN", "POSTCODE_ADMIN", (GN,), "FULL_POSTCODE"
    ),
    _question(
        8,
        "TRUSTED_COUNTRY POSTCODE ADMIN",
        "POSTCODE_PREFIX_BY_ADMIN",
        (LIA,),
        "POSTCODE_PREFIX_RULE",
    ),
    _question(9, "TRUSTED_COUNTRY LOCALITY", "LOCALITY", (LIA, GN), "REFERENCE_NAME"),
    _question(10, "TRUSTED_COUNTRY ADMIN", "ADMIN", (ISO, LIA, GN), "REFERENCE_NAME"),
    _question(
        11,
        "TRUSTED_COUNTRY LOCALITY ADMIN",
        "LOCALITY_ADMIN",
        (LIA, GN),
        "REFERENCE_NAME",
    ),
    _question(12, "TRUSTED_COUNTRY STREET", "STREET", ("NONE",), "UNSUPPORTED"),
    _question(
        13,
        "TRUSTED_COUNTRY STREET HOUSE_NUMBER",
        "HOUSE_NUMBER",
        ("NONE",),
        "UNSUPPORTED",
    ),
    _question(14, "PARSER_COUNTRY_CODE", "COUNTRY_CONTEXT", (ISO,), "COUNTRY_CODE"),
    _question(15, "TRUSTED_COUNTRY", "REQUIRED_FIELDS", (LIA,), "METADATA"),
)
QUESTIONS = {q.question_id: q for q in CATALOG}


def capability_name(question: Question, reference: str) -> str:
    return (
        "ADMIN_ENUMERATION"
        if question.question_id == "Q10" and reference == LIA
        else question.capability
    )


def normalization_method(
    question: str, role: str, reference: str, country: str, value: str
) -> str:
    if role in ("COUNTRY_CODE", "PARSER_COUNTRY_CODE", "TRUSTED_COUNTRY"):
        return ISO_NORM
    if role in ("STREET", "HOUSE_NUMBER"):
        return NO_NORM
    if role == "ADMIN" and (
        question == "Q02"
        or (
            question == "Q10"
            and reference == ISO
            and re.fullmatch(r"[A-Z]{2}-[A-Z0-9]+", ascii_upper(value))
        )
    ):
        return ISO_NORM
    if role == "POSTCODE":
        if question in ("Q04", "Q08"):
            return FORM_NORM
        return SEPARATOR_NORM if country in POSTCODE_SEPARATORS else EXACT_NORM
    return NAME_NORM


# Order, requiredness and nesting are a direct transcription of the frozen schema.
_STRUCTS = {
    "Asset": "asset_id:D role:T relative_path:T source_url:T member_path:T? retrieval_utc:T publisher_release:T? last_modified:T? etag:T? bytes:U sha256:D media_type:T provenance:T",
    "Lineage": "token:T parent_token:T relation:T pelias_overlap:T provenance:T",
    "ReferenceField": "field_name:T ordinal:U original_value:T source_field_locator:T alias_role:T language_tag:T? geographic_level:T?",
    "Argument": "role:T origin_relation:T origin_field:T? component_ordinal:U? observed_role_count:U origin_semantic_class:T normalization_id:T normalized_value_sha256:D? value_granularity:T",
    "FieldPointer": "reference_object_id:D field_name:T ordinal:U",
    "Witness": "reference_object_id:D witness_role:T fields:[FieldPointer]",
}
_RELATIONS = {
    "reference_registry": "reference_version_id:D reference_id:T dataset_name:T dataset_release:T edition:T evidence_family:T retrieval_utc:T effective_date:T? license_expression:T license_note:T normalization_contract:T countries:[T] limitations:[T] assets:[Asset] lineage:[Lineage] raw_dataset_sha256:D",
    "reference_capability": "capability_id:D reference_version_id:D country_scope:T question_catalog_id:T capability:T scope_locator:T enabled:B positive_authority:B positive_authority_basis:T negative_authority:B negative_authority_basis:T claim_scope:T coverage_kind:T granularity:T required_roles:[T] normalization_id:T limitations:[T]",
    "reference_object": "reference_object_id:D reference_version_id:D asset_id:D source_locator:T object_kind:T country_code:T? explicit_parent_id:D? fields:[ReferenceField]",
    "candidate_reference_evidence": "evidence_id:D stage06_exact_candidate_id:D evidence_scope:T stable_source_row_id_v1:D? question_catalog_id:T reference_slot:T reference_version_id:D? reference_asset_id:D? capability_id:D? rule_capability_id:D? evidence_family:T? interpretation:T claim_scope:T arguments:[Argument] result_state:T reason_code:T contradiction_type:T? country_assessment:T country_assessment_basis:T lookup_identity:D? witness_count:U single_witness:Witness? match_set_id:D? evidence_class:T",
    "reference_match_member": "match_set_id:D member_ordinal:U witness:Witness",
    "coverage_summary": "summary_kind:T country_scope:T evidence_scope:T representation:T question_catalog_id:T reference_slot:T capability:T result_state:T reason_code:T contradiction_type:T count:U denominator:U",
}
PRIMARY_KEYS = {
    "reference_registry": ("reference_version_id",),
    "reference_capability": ("capability_id",),
    "reference_object": ("reference_object_id",),
    "candidate_reference_evidence": ("evidence_id",),
    "reference_match_member": ("match_set_id", "member_ordinal"),
    "coverage_summary": tuple(
        item.split(":")[0] for item in _RELATIONS["coverage_summary"].split()[:10]
    ),
}
RELATIONS = tuple(_RELATIONS)
BOUNDS = {
    "arguments": 3,
    "assets": 512,
    "lineage": 32,
    "countries": 512,
    "limitations": 64,
    "required_roles": 3,
    "Witness.fields": 16,
    "reference_object.fields": 512,
}


def _semantic(parent: str, name: str) -> str:
    if name == "normalized_value_sha256":
        return "REFERENCE_LOOKUP_REPRESENTATION"
    if parent == "Argument":
        return "MECHANICAL_INDEX"
    if (
        name.endswith("_id")
        or name.endswith("_sha256")
        or name.endswith("_ordinal")
        or name in ("count", "denominator", "bytes", "witness_count")
    ):
        return "MECHANICAL_INDEX"
    return (
        "REFERENCE_PROVENANCE"
        if parent.startswith("reference_")
        or parent in ("Asset", "Lineage", "ReferenceField", "FieldPointer")
        else "REFERENCE_EVIDENCE"
    )


def _data_type(spec: str) -> Any:
    scalar = {
        "D": pa.binary(32),
        "T": pa.large_string(),
        "U": pa.uint64(),
        "B": pa.bool_(),
    }
    if spec in scalar:
        return scalar[spec]
    if spec.startswith("["):
        return pa.list_(pa.field("element", _data_type(spec[1:-1]), nullable=False))
    return pa.struct(_fields(spec, _STRUCTS[spec]))


def _fields(parent: str, specification: str) -> list[Any]:
    fields = []
    for token in specification.split():
        name, kind = token.split(":")
        fields.append(
            pa.field(
                name,
                _data_type(kind.rstrip("?")),
                nullable=kind.endswith("?"),
                metadata={b"semantic_class": _semantic(parent, name).encode()},
            )
        )
    return fields


@cache
def relation_schema(name: str) -> Any:
    require(name in _RELATIONS, "UNKNOWN_RELATION")
    return pa.schema(
        _fields(name, _RELATIONS[name]),
        metadata={
            b"stage09_schema_version": SCHEMA_VERSION.encode(),
            b"scientific_boundary": b"REFERENCE_EVIDENCE_ONLY",
        },
    )


@cache
def schema_fingerprint(name: str) -> bytes:
    def descriptor(field: Any) -> tuple[Any, ...]:
        kind = field.type
        children = (
            tuple(descriptor(f) for f in kind)
            if pa.types.is_struct(kind)
            else (descriptor(kind.value_field),)
            if pa.types.is_list(kind)
            else ()
        )
        return (
            field.name,
            str(kind),
            field.nullable,
            tuple(
                (k.decode(), v.decode())
                for k, v in sorted((field.metadata or {}).items())
            ),
            children,
        )

    return identity(
        "SCHEMA",
        (
            SCHEMA_VERSION,
            name,
            _RELATIONS[name],
            tuple(sorted(_STRUCTS.items())),
            PRIMARY_KEYS[name],
            tuple(sorted(BOUNDS.items())),
            DESIGN_SHA256,
            tuple(descriptor(f) for f in relation_schema(name)),
            "UNSIGNED_BYTES_UTF8_NUMERIC_NULL_FIRST",
        ),
    )


@cache
def schema_bundle_fingerprint() -> bytes:
    return identity(
        "SCHEMA_BUNDLE",
        (SCHEMA_VERSION, tuple((n, schema_fingerprint(n)) for n in sorted(RELATIONS))),
    )


@cache
def catalog_fingerprint() -> bytes:
    return identity(
        "CATALOG",
        (
            "stage09_reference_question_catalog_v1",
            tuple(q.as_tuple() for q in CATALOG),
            DESIGN_SHA256,
        ),
    )


@cache
def contract_fingerprint() -> bytes:
    return identity(
        "CONTRACT",
        (
            CONTRACT_VERSION,
            DESIGN_SHA256,
            schema_bundle_fingerprint(),
            catalog_fingerprint(),
            STATES,
            REASONS,
            COUNTRY_STATES,
            FAMILIES,
            CONTRADICTIONS,
            NORMALIZATIONS,
            tuple((c, v) for c, v in sorted(POSTCODE_SEPARATORS.items())),
        ),
    )


@cache
def normalization_fingerprint() -> bytes:
    return identity(
        "NORMALIZATION_CONTRACT",
        (
            NORMALIZATION_VERSION,
            DESIGN_SHA256,
            NORMALIZATIONS,
            tuple(sorted(POSTCODE_SEPARATORS.items())),
            SEMANTIC_RUNTIME[:2],
        ),
    )


@cache
def semantics_fingerprint() -> bytes:
    return identity(
        "EVIDENCE_SEMANTICS",
        (
            "stage09_evidence_semantics_v1",
            DESIGN_SHA256,
            STATES,
            COUNTRY_STATES,
            REASONS,
            CONTRADICTIONS,
            FAMILIES,
        ),
    )


def ordered_values(row: Mapping[str, Any], schema: Any) -> tuple[Any, ...]:
    def convert(value: Any, data_type: Any) -> Any:
        if value is None:
            return None
        if pa.types.is_struct(data_type):
            return tuple(convert(value[f.name], f.type) for f in data_type)
        if pa.types.is_list(data_type):
            return tuple(convert(v, data_type.value_type) for v in value)
        return value

    return tuple(convert(row[f.name], f.type) for f in schema)


def witness_tuple(witness: Mapping[str, Any]) -> tuple[Any, ...]:
    return ordered_values(witness, _data_type("Witness"))


def relation_fingerprint(
    name: str, count: int, rows: Iterable[Mapping[str, Any]]
) -> bytes:
    """H(RELATION, (..., ordered rows)), without allocating the row collection."""
    digest = hashlib.sha256(struct.pack(">Q", 4))
    for item in ("SAFE_STAGE09", "V1", "RELATION"):
        digest.update(framed(item))
    digest.update(b"\x05" + struct.pack(">Q", 4))
    for header_value in (name, schema_fingerprint(name), count):
        digest.update(framed(header_value))
    digest.update(b"\x05" + struct.pack(">Q", count))
    seen = 0
    previous: tuple[Any, ...] | None = None
    schema = relation_schema(name)
    for row in rows:
        key = tuple(row[k] for k in PRIMARY_KEYS[name])
        require(previous is None or previous < key, "RELATION_KEY_ORDER_OR_COLLISION")
        previous = key
        for chunk in typed_chunks(ordered_values(row, schema)):
            digest.update(chunk)
        seen += 1
    require(seen == count, "RELATION_COUNT_MISMATCH")
    return digest.digest()


def validate_evidence_semantics(
    row: Mapping[str, Any], capability: Mapping[str, Any] | None
) -> None:
    """Independent state/authority checks, also used by publication reopening."""
    state, reason = row["result_state"], row["reason_code"]
    require(state in STATES and reason in REASONS, "EVIDENCE_ENUM_INVALID")
    require(row["evidence_class"] == "REFERENCE_EVIDENCE", "EVIDENCE_CLASS_INVALID")
    require(row["evidence_scope"] in SCOPES, "EVIDENCE_SCOPE_INVALID")
    require(
        (row["stable_source_row_id_v1"] is not None)
        == (row["evidence_scope"] == "SOURCE_ROW"),
        "SOURCE_SCOPE_INVALID",
    )
    require(row["country_assessment"] in COUNTRY_STATES, "COUNTRY_ASSESSMENT_INVALID")
    require(
        row["contradiction_type"] is None
        or row["contradiction_type"] in CONTRADICTIONS,
        "CONTRADICTION_TYPE_INVALID",
    )
    count = row["witness_count"]
    require(
        isinstance(count, int) and not isinstance(count, bool) and count >= 0,
        "WITNESS_COUNT_INVALID",
    )
    require(
        (row["single_witness"] is not None) == (count == 1), "SINGLE_WITNESS_INVALID"
    )
    require((row["match_set_id"] is not None) == (count > 1), "MATCH_SET_INVALID")
    require(len(row["arguments"]) <= 3, "ARGUMENT_BOUND_EXCEEDED")
    if row["reference_slot"] == "NONE":
        require(
            capability is None
            and state == "NOT_EVALUABLE"
            and reason == "CAPABILITY_NOT_CONFIGURED",
            "NONE_REFERENCE_INVALID",
        )
        require(
            all(
                row[k] is None
                for k in (
                    "reference_version_id",
                    "reference_asset_id",
                    "capability_id",
                    "rule_capability_id",
                    "evidence_family",
                    "lookup_identity",
                )
            ),
            "NONE_REFERENCE_BINDING_INVALID",
        )
    else:
        require(capability is not None, "CAPABILITY_MISSING")
        assert capability is not None
        require(
            row["evidence_family"] == row["reference_slot"] in FAMILIES,
            "REFERENCE_FAMILY_INVALID",
        )
        require(
            row["capability_id"] == capability["capability_id"]
            and row["reference_version_id"] == capability["reference_version_id"],
            "CAPABILITY_BINDING_INVALID",
        )
        require(row["reference_asset_id"] is not None, "REFERENCE_ASSET_MISSING")
        if state in ("SUPPORTED", "CONTRADICTED", "NOT_FOUND"):
            require(
                capability["enabled"] and capability["positive_authority"],
                "CAPABILITY_NOT_ENABLED",
            )
    if state == "CONTRADICTED":
        require(
            capability is not None
            and capability["negative_authority"]
            and row["evidence_family"] != GN,
            "NEGATIVE_AUTHORITY_REQUIRED",
        )
        require(
            row["contradiction_type"] in CONTRADICTIONS and count > 0,
            "CONTRADICTION_CERTIFICATE_REQUIRED",
        )
        require(
            reason in ("EXPLICIT_RULE_CONFLICT", "EXPLICIT_CODE_COUNTRY_CONFLICT"),
            "CONTRADICTION_REASON_INVALID",
        )
    else:
        require(row["contradiction_type"] is None, "NON_CONTRADICTION_TYPE")
    if state == "SUPPORTED":
        require(count > 0, "SUPPORT_CERTIFICATE_REQUIRED")
    if state == "NOT_FOUND":
        require(
            count == 0
            and reason
            in (
                "VALUE_ABSENT_FROM_REFERENCE",
                "RELATION_ABSENT_FROM_REFERENCE",
                "REFERENCE_ASSOCIATION_MISMATCH",
            ),
            "MISS_CANNOT_CERTIFY_INVALIDITY",
        )
    if state == "NOT_EVALUABLE" and count:
        require(reason == "REFERENCE_INTERNAL_CONFLICT", "ABSTENTION_WITNESS_INVALID")
    if row["country_assessment"] != "COUNTRY_UNRESOLVED":
        require(
            row["evidence_scope"] == "SOURCE_ROW"
            and row["question_catalog_id"] == "Q02"
            and state in ("SUPPORTED", "CONTRADICTED"),
            "COUNTRY_INFERENCE_PROHIBITED",
        )
        require(
            row["country_assessment"] == "COUNTRY_" + state
            and row["country_assessment_basis"] == "EXPLICIT_SOURCE_SUBDIVISION_CODE",
            "COUNTRY_BASIS_INVALID",
        )
    if row["single_witness"] is not None:
        expected = {
            "SUPPORTED": "SUPPORT",
            "CONTRADICTED": "CONTRADICTION",
            "NOT_EVALUABLE": "CONFLICTING_REFERENCE",
        }
        require(
            row["single_witness"]["witness_role"] == expected.get(state),
            "WITNESS_ROLE_INVALID",
        )

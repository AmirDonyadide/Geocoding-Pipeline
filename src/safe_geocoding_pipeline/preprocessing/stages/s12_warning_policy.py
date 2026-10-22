"""Inactive, offline-only successor validation and limitation audit.

No runtime/probe caller imports this module. No real deployment approvals exist.
Synthetic review bindings exercise the conditional rule on explicitly marked
invented responses only. Assessments are not candidate projections, attempt
receipts, deployment attestations, or publication/checkpoint authority.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from . import s12_response as v1
from . import s12_retrieval_contract as c

VERSION = "stage12_response_validation_v2"
AUDIT_VERSION = "stage12_warning_limitation_audit_v1"
EXCEPTION_VERSION = "stage12_public_berlin_warning_exception_v1"
BASE_SHA256 = "3acfb6cb6888a6b16903f0b132b071f6bac82277263b9d17fd368bbe9449994e"
MATERIALIZATION_SHA256 = (
    "b29d69445aeaf99b77c7f3dd0265520dd1569a280b4bf6ec6718f09891ee603e"
)
WARNING = "performance optimization: excluding 'address' layer"
TARGET = b"/v1/search?boundary.country=DE&size=1&text=Berlin"
TEST_SCOPE = "SYNTHETIC_UNIT_TEST_ONLY"
TEST_MARKER = "STAGE12_WARNING_POLICY_INVENTED_RESPONSE"
HEADER_NAMES = ("Host", "Accept", "Accept-Encoding", "User-Agent", "X-API-Key")
REVIEW_KEYS = frozenset(
    {
        "scope",
        "deployment_content_sha256",
        "index_data_identity",
        "effective_behavior_id",
        "echo_adapter",
        "effective_layers",
        "sources",
        "review_approved",
        "authenticity_verified",
        "immutable_content_verified",
        "drift_verified",
    }
)


def audit_descriptor() -> dict[str, Any]:
    return {
        "audit_version": AUDIT_VERSION,
        "scope": "OFFLINE_VALIDATION_ASSESSMENT_NOT_NETWORK_RECEIPT",
        "fields": {
            "audit_version": "VERSION_STRING",
            "assessment_scope": "OFFLINE_ONLY",
            "scientific_publication_authorized": "FALSE",
            "validation_contract_sha256": "FULL_SHA256_HEX",
            "raw_response_sha256": "FULL_SHA256_HEX",
            "raw_response_bytes": "NONNEGATIVE_INTEGER",
            "hash_provenance": "OFFLINE_COMPUTATION_NOT_CAPTURE_TIME_ATTESTATION",
            "request_target_sha256": "NULL_OR_FULL_SHA256_HEX",
            "http_status": "200",
            "content_type": "V1_ALLOWED_ENUM",
            "content_encoding": "ABSENT_OR_IDENTITY",
            "feature_count": "NONNEGATIVE_INTEGER_WITHIN_REQUEST_SIZE",
            "validation_outcome": "V1_SUCCESS_ENUM_ASSESSMENT_ONLY",
            "exception_applied": "BOOLEAN",
            "exception_version": "NULL_OR_EXCEPTION_VERSION",
            "exception_evidence_scope": "NULL_OR_SYNTHETIC_UNIT_TEST_ONLY",
            "geocoding_warnings": "NULL_OR_EXACT_ORIGINAL_ARRAY",
            "effective_layers": "NULL_OR_EXACT_REVIEWED_ORDERED_ARRAY",
            "retrieval_limitation": "NULL_OR_ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED",
            "harmlessness_established": "FALSE",
            "live_determinism_established": "FALSE",
        },
        "emit": "ONLY_AFTER_ALL_VALIDATION_CHECKS_PASS",
        "rejected_response": "NO_ASSESSMENT_OR_CANDIDATE_ROWS",
        "scientific_ids": "NO_EXECUTION_OR_PROJECTION_ID",
        "original_raw_and_receipts": "READ_ONLY_NEVER_REWRITE",
    }


def descriptor(synthetic_review: bytes | None = None) -> dict[str, Any]:
    """All rule-bearing content, including test bindings, enters validation SHA.

    The shipped descriptor has no bindings. Supplying test evidence never registers
    an approved real deployment. There is deliberately no real-activation API.
    """
    review = None
    if synthetic_review is not None:
        try:
            review = json.loads(synthetic_review)
            c.require(c.canonical(review) == synthetic_review, "IDENTITY_UNVERIFIABLE")
        except (ValueError, UnicodeError):
            raise c.Stage12Error("IDENTITY_UNVERIFIABLE") from None
    return {
        "validation_version": VERSION,
        "base_validation_contract_sha256": BASE_SHA256,
        "ordinary_validation": "ALL_V1_CHECKS_UNCHANGED",
        "exception": {
            "exception_version": EXCEPTION_VERSION,
            "request": {
                "scope": "PUBLIC_SYNTHETIC_ONLY",
                "method": "GET",
                "mode": "FULL_TEXT",
                "target_ascii": TARGET.decode("ascii"),
                "header_names_in_order": list(HEADER_NAMES),
                "core": "EXACT_STAGE11_CORE_AND_POLICY_MATERIALIZATION",
                "materialization_contract_sha256": MATERIALIZATION_SHA256,
                "result_limit": 1,
                "omissions": "UNCHANGED_STAGE11_AND_MATERIALIZATION_V1",
            },
            "geocoding_warnings": [WARNING],
            "top_warnings_and_all_errors": "ABSENT_OR_EMPTY_ARRAY",
            "matching": "EXACT_STRING_AND_SINGLETON_ARRAY_NO_NORMALIZATION",
            "metadata": {
                "echo": "EXACT_REVIEWED_LITERAL_QUERY_KEYS_AND_TYPED_VALUES",
                "required_echo_keys": ["text", "size", "boundary.country", "lang"],
                "layers": "EXACT_ORDERED_REVIEWED_UNIQUE_NONEMPTY_LIST_NO_ADDRESS",
                "returned_layers": "MEMBERS_OF_EFFECTIVE_LIST_AND_DECLARED_VOCABULARY",
                "sources": "EXACT_REVIEWED_VOCABULARY",
                "parsed_text": "NOT_ELIGIBILITY_OR_PROOF_OF_NO_ADDRESS_EVIDENCE",
            },
            "required_binding_fields": sorted(REVIEW_KEYS),
            "binding_rules": {
                "keys": "EXACT_CLOSED_REVIEW_KEYS",
                "identity_values": "LOWERCASE_FULL_SHA256_HEX_SYNTHETIC_ONLY",
                "review_authenticity_immutability_drift": "ALL_EXACT_BOOLEAN_TRUE",
                "echo_text_size": {"text": "Berlin", "size": 1},
                "echo_country": "REVIEWED_NONEMPTY_STRING_ARRAY_NO_INFERRED_MAPPING",
                "echo_language": "REVIEWED_NONEMPTY_OBJECT_NO_ASSUMED_DEFAULT",
                "echo_values": "STRICT_PARSER_TYPED_EQUALITY_INCLUDING_NUMERIC_TOKENS",
            },
            "missing_or_unapproved_binding": "FAIL_CLOSED",
            "real_approved_bindings": [],
            "synthetic_only": {
                "scope": TEST_SCOPE,
                "required_top_level_marker": TEST_MARKER,
                "required_engine_name": TEST_MARKER,
                "source_vocabulary": ["synthetic"],
                "authority_over_real_evidence": False,
            },
            "scientific_interpretation": "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED",
            "harmlessness_or_live_determinism_established": False,
        },
        "synthetic_review": review,
        "audit_version": AUDIT_VERSION,
        "limitation_audit_contract_sha256": c.sha(
            c.canonical(audit_descriptor())
        ).hex(),
        "activation": "OFFLINE_ASSESSMENT_ONLY_NO_RUNTIME_INTEGRATION",
    }


def validation_sha256(synthetic_review: bytes | None = None) -> bytes:
    return c.sha(c.canonical(descriptor(synthetic_review)))


@dataclass(frozen=True)
class RequestFacts:
    """Secret-free request facts; no transport or credential access."""

    core_json: bytes
    query_semantic_id: bytes
    result_limit: int
    method: str
    target: bytes
    header_names: tuple[str, ...]

    def verify_exception_scope(self) -> bytes:
        try:
            core = json.loads(self.core_json)
        except (ValueError, UnicodeError):
            raise c.Stage12Error("RESPONSE_CONTRACT_INVALID") from None
        c.require(
            type(core) is dict
            and core.get("search_mode") == "FULL_TEXT"
            and self.method == "GET"
            and type(self.result_limit) is int
            and self.result_limit == 1
            and self.target == TARGET
            and self.header_names == HEADER_NAMES,
            "RESPONSE_CONTRACT_INVALID",
        )
        try:
            target, fingerprint = c.materialize(
                core, self.query_semantic_id, c.policy(1), target_limit=len(TARGET)
            )
        except c.Stage12Error:
            raise c.Stage12Error("RESPONSE_CONTRACT_INVALID") from None
        c.require(target == self.target, "RESPONSE_CONTRACT_INVALID")
        return fingerprint


@dataclass(frozen=True)
class Assessment:
    """No scientific IDs or candidate rows: only an offline validation result."""

    validation_sha256: bytes
    validation_descriptor_json: bytes
    response_sha256: bytes
    feature_structures: tuple[Any, ...]
    feature_slices: tuple[tuple[int, int], ...]
    audit_json: bytes


def _synthetic_guards(
    obj: dict[str, Any],
    query: dict[str, Any],
    review: Any,
    layers: frozenset[str],
    sources: frozenset[str],
) -> tuple[str, ...]:
    # An unmarked retained SAFE response cannot gain authority from test bindings.
    geo = obj["geocoding"]
    c.require(
        obj.get("stage12_test_evidence") == TEST_MARKER
        and type(geo.get("engine")) is dict
        and geo["engine"].get("name") == TEST_MARKER,
        "IDENTITY_UNVERIFIABLE",
    )
    c.require(
        type(review) is dict and set(review) == REVIEW_KEYS, "IDENTITY_UNVERIFIABLE"
    )
    c.require(review["scope"] == TEST_SCOPE, "IDENTITY_UNVERIFIABLE")
    for field in (
        "review_approved",
        "authenticity_verified",
        "immutable_content_verified",
        "drift_verified",
    ):
        c.require(review[field] is True, "IDENTITY_UNVERIFIABLE")
    for field in (
        "deployment_content_sha256",
        "index_data_identity",
        "effective_behavior_id",
    ):
        value = review[field]
        c.require(
            type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "IDENTITY_UNVERIFIABLE",
        )
    effective = review["effective_layers"]
    c.require(
        type(effective) is list
        and bool(effective)
        and all(type(item) is str and bool(item) for item in effective),
        "IDENTITY_UNVERIFIABLE",
    )
    c.require(
        len(set(effective)) == len(effective)
        and "address" not in effective
        and set(effective) <= layers
        and review["sources"] == ["synthetic"]
        and sources == frozenset({"synthetic"}),
        "IDENTITY_UNVERIFIABLE",
    )
    echo = review["echo_adapter"]
    c.require(
        type(echo) is dict
        and {"text", "size", "boundary.country", "lang"} <= set(echo)
        and echo.get("text") == "Berlin"
        and type(echo.get("size")) is int
        and echo["size"] == 1
        and "layers" not in echo,
        "IDENTITY_UNVERIFIABLE",
    )
    c.require(
        type(echo["boundary.country"]) is list
        and bool(echo["boundary.country"])
        and all(type(item) is str and bool(item) for item in echo["boundary.country"])
        and type(echo["lang"]) is dict
        and bool(echo["lang"]),
        "IDENTITY_UNVERIFIABLE",
    )
    # Literal JSON keys, including 'boundary.country'; no guessed dotted-path adapter.
    expected = v1.Parser(c.canonical(echo)).parse().value
    for key, value in expected.items():
        c.require(key in query and query[key] == value, "RESPONSE_CONTRACT_INVALID")
    c.require(query.get("layers") == effective, "RESPONSE_CONTRACT_INVALID")
    return tuple(effective)


def _features(
    parsed: v1.Parsed,
    layers: frozenset[str],
    sources: frozenset[str],
    effective: tuple[str, ...] | None,
) -> None:
    """V1 candidate checks without constructing a scientific execution/projection.

    This small duplication keeps the frozen v1 module byte-for-byte unchanged.
    Differential tests compare these checks with the unchanged v1 extractor.
    """
    for feature in parsed.value["features"]:
        c.require(
            type(feature) is dict and feature.get("type") == "Feature",
            "RESPONSE_CONTRACT_INVALID",
        )
        v1.envelope(feature, messages=False)
        properties, geometry = feature.get("properties"), feature.get("geometry")
        c.require(
            type(properties) is dict and type(geometry) is dict,
            "RESPONSE_CONTRACT_INVALID",
        )
        assert isinstance(properties, dict) and isinstance(geometry, dict)
        coordinates = geometry.get("coordinates")
        c.require(
            geometry.get("type") == "Point"
            and "crs" not in geometry
            and type(coordinates) is list
            and len(coordinates) == 2,
            "RESPONSE_CONTRACT_INVALID",
        )
        assert isinstance(coordinates, list)
        v1.numeric(coordinates[0], -180, 180)
        v1.numeric(coordinates[1], -90, 90)
        for name in v1.STRINGS:
            v1.optional_string(properties.get(name))
        v1.optional_string(feature.get("id"))
        c.require(
            bool(properties.get("layer"))
            and properties["layer"] in layers
            and bool(properties.get("source"))
            and properties["source"] in sources,
            "RESPONSE_CONTRACT_INVALID",
        )
        if effective is not None:
            c.require(properties["layer"] in effective, "RESPONSE_CONTRACT_INVALID")
        if properties.get("confidence") is not None:
            v1.numeric(properties["confidence"], 0, 1)


def validate_offline(
    raw: bytes,
    *,
    size: int,
    http_status: int,
    content_type: str,
    encoding: str,
    layers: frozenset[str],
    sources: frozenset[str],
    expected_echo: dict[str, Any],
    expected_hash: bytes | None = None,
    request: RequestFacts | None = None,
    synthetic_review: bytes | None = None,
) -> Assessment:
    """All-or-nothing offline assessment. Exceptions return no result/audit rows.

    Warning-free responses require no exception bindings. Any nonempty warning
    on real evidence is blocked: the real deployment approval set is empty.
    """
    policy = descriptor(synthetic_review)
    validation_bytes = c.canonical(policy)
    validation_hash = c.sha(validation_bytes)
    body_hash = c.sha(raw)
    c.require(type(size) is int and size > 0, "S12_POLICY_INVALID")
    c.require(
        expected_hash is None or c.digest(expected_hash) == body_hash,
        "S12_RAW_HASH_MISMATCH",
    )
    c.require(
        http_status == 200
        and content_type in v1.MEDIA
        and encoding in ("identity", "absent"),
        "RESPONSE_CONTRACT_INVALID",
    )
    parsed = v1.Parser(raw).parse()
    obj = parsed.value
    v1.envelope(obj)
    features = obj.get("features")
    c.require(
        obj.get("type") == "FeatureCollection"
        and type(features) is list
        and len(features) <= size
        and len(parsed.feature_slices) == len(features),
        "RESPONSE_CONTRACT_INVALID",
    )
    assert isinstance(features, list)
    effective = None
    target_hash = None
    warning = None
    if "geocoding" in obj:
        geo = obj["geocoding"]
        c.require(type(geo) is dict, "RESPONSE_CONTRACT_INVALID")
        # Check errors and CRS separately; warnings are handled by the new gate.
        v1.envelope(geo, messages=False, bbox=False)
        if "errors" in geo:
            c.require(
                type(geo["errors"]) is list and geo["errors"] == [],
                "RESPONSE_CONTRACT_INVALID",
            )
        if "warnings" in geo:
            warning = geo["warnings"]
            c.require(type(warning) is list, "RESPONSE_CONTRACT_INVALID")
        for field in ("version", "attribution"):
            if field in geo:
                c.require(type(geo[field]) is str, "RESPONSE_CONTRACT_INVALID")
        if "timestamp" in geo:
            timestamp = geo["timestamp"]
            c.require(
                type(timestamp) is v1.Number
                and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", timestamp.token) is not None,
                "RESPONSE_CONTRACT_INVALID",
            )
        if "query" in geo:
            c.require(type(geo["query"]) is dict, "RESPONSE_CONTRACT_INVALID")
            v1.compare_echo(geo["query"], expected_echo)
        if warning:
            c.require(warning == [WARNING] and size == 1, "RESPONSE_CONTRACT_INVALID")
            c.require(request is not None, "IDENTITY_UNVERIFIABLE")
            assert request is not None
            target_hash = request.verify_exception_scope()
            c.require(type(geo.get("query")) is dict, "RESPONSE_CONTRACT_INVALID")
            effective = _synthetic_guards(
                obj, geo["query"], policy["synthetic_review"], layers, sources
            )
    _features(parsed, layers, sources, effective)
    # Only now can an assessment/audit escape: no partial success for bad features.
    audit = {
        "audit_version": AUDIT_VERSION,
        "assessment_scope": "OFFLINE_ONLY",
        "scientific_publication_authorized": False,
        "validation_contract_sha256": validation_hash.hex(),
        "raw_response_sha256": body_hash.hex(),
        "raw_response_bytes": len(raw),
        "hash_provenance": "OFFLINE_COMPUTATION_NOT_CAPTURE_TIME_ATTESTATION",
        "request_target_sha256": target_hash.hex() if target_hash is not None else None,
        "http_status": http_status,
        "content_type": content_type,
        "content_encoding": encoding,
        "feature_count": len(features),
        "validation_outcome": c.SUCCESS[0] if features else c.SUCCESS[1],
        "exception_applied": effective is not None,
        "exception_version": EXCEPTION_VERSION if effective is not None else None,
        "exception_evidence_scope": TEST_SCOPE if effective is not None else None,
        "geocoding_warnings": warning,
        "effective_layers": list(effective) if effective is not None else None,
        "retrieval_limitation": "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED"
        if effective is not None
        else None,
        "harmlessness_established": False,
        "live_determinism_established": False,
    }
    return Assessment(
        validation_hash,
        validation_bytes,
        body_hash,
        tuple(v1.structural(f) for f in features),
        parsed.feature_slices,
        c.canonical(audit),
    )

"""SP-B-r2 identities and closed DEVELOPMENT records; no live defaults.

Descriptors are successor assets. Their checked bytes never replace v1 assets.
A valid hash/shape identifies retained bytes; it is not authority or provenance.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow as pa

from . import s12_retrieval_contract as v1

SCHEMA_BUNDLE = "stage12_development_observational_schemas_b2_v1"
BUNDLE_SHA256 = "b36959a950559994f0959b6fd52d1d5e37e6d8adb7afc79845cbbc8aeb590f58"
DESIGN_SHA256 = "c4e44994e5e2a0333269b2cb6537dbb8f3be5234a5c9cd00479551c9819107b5"
AMENDMENT_SHA256 = "cb3d446545d9f1de6a8baa042eaa83a054a6f4660186a1de93e6a6c604937dba"
SPEC_SHA256 = "cb24baf2e9320498d693b28a1a7f9fefc01893fdf563141ae6e6e3eeb79e4f62"
SCHEMA = "stage12_pelias_retrieval_schema_b2_v1"
IDENTITY = "stage12_observation_identity_b2_v1"
ATTEMPT = "stage12_attempt_receipt_b2_v1"
EXTRACTION = "stage12_response_extraction_b2_v1"
SYNTHETIC = "SYNTHETIC_TEST_ONLY"
DEVELOPMENT = "ACCEPTED_DEVELOPMENT"
MAX_METADATA = 4 * 1024 * 1024
require, canonical, sha, framed, named, identity = (
    v1.require,
    v1.canonical,
    v1.sha,
    v1.framed,
    v1.named,
    v1.identity,
)
SUCCESS, RELATIONS, KEYS = v1.SUCCESS, v1.RELATIONS, v1.KEYS
EXECUTION_FIELDS = (
    "identity_version",
    "query_semantic_id",
    "retrieval_policy_id",
    "materialization_contract_sha256",
    "observation_binding_id",
    "campaign_id",
)


def registry() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[4]
        / "docs/scientific_assets"
        / (SCHEMA_BUNDLE + ".json")
    )
    raw = path.read_bytes()
    require(sha(raw).hex() == BUNDLE_SHA256, "B2_DESCRIPTOR_MISMATCH")
    return json.loads(raw)


# The registry is a verified immutable module-level type definition, not evidence.
REGISTRY = registry()
TYPES, SCHEMAS = REGISTRY["named_types"], dict(REGISTRY["schemas"])
ACQUISITION_DESCRIPTOR = "stage12_bounded_acquisition_contract_descriptor_b2_v1"
ACQUISITION_SHA256 = "430939a59f07cf41fb7fbd8f122772056b44ea876b577c7bf5801cfd3ac4b15c"
_acq_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (ACQUISITION_DESCRIPTOR + ".json")
).read_bytes()
require(sha(_acq_raw).hex() == ACQUISITION_SHA256, "B2_DESCRIPTOR_MISMATCH")
ACQUISITION_ASSET = json.loads(_acq_raw)
SCHEMAS["stage12_bounded_acquisition_contract_b2_v1"] = ACQUISITION_ASSET[
    "record_schema"
]


def uint(value: Any, positive: bool = False) -> int:
    require(type(value) is int and int(positive) <= value < 2**64, "B2_UINT_INVALID")
    return value


def digest(value: Any) -> str:
    return sha(canonical(value)).hex()


def validate_type(value: Any, spec: Any) -> None:
    if isinstance(spec, str):
        if spec.endswith("?"):
            if value is not None:
                validate_type(value, spec[:-1])
        elif spec.endswith("[]"):
            require(type(value) is list, "B2_TYPE_INVALID")
            for item in value:
                validate_type(item, spec[:-2])
        elif spec.startswith("="):
            require(type(value) is str and value == spec[1:], "B2_LITERAL_INVALID")
        elif spec in ("U", "P", "ID"):
            uint(value, spec != "U")
        elif spec == "B":
            require(type(value) is bool, "B2_TYPE_INVALID")
        elif spec in ("D", "G", "N32"):
            n = 40 if spec == "G" else 64
            require(
                type(value) is str
                and re.fullmatch(r"[0-9a-f]{" + str(n) + "}", value) is not None
                and value != "0" * n,
                "B2_DIGEST_INVALID",
            )
        elif spec == "Z":
            require(
                type(value) is str
                and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value)
                is not None,
                "B2_TIME_INVALID",
            )
            try:
                datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                require(False, "B2_TIME_INVALID")
        else:
            require(spec in TYPES or spec in SCHEMAS, "B2_TYPE_INVALID")
            validate_type(value, TYPES.get(spec, SCHEMAS.get(spec)))
            if spec in ("Rate", "Fraction"):
                require(
                    math.gcd(value["num"], value["den"]) == 1
                    and value["num"] <= (60 if spec == "Rate" else 1) * value["den"],
                    "B2_RATE_INVALID",
                )
            if spec == "Count":
                require(
                    value["value"] is None or value["value"] == value["confirmed_min"],
                    "B2_COUNT_INVALID",
                )
    elif "enum" in spec:
        require(type(value) is str and value in spec["enum"], "B2_ENUM_INVALID")
    elif "const" in spec:
        require(
            type(value) is type(spec["const"]) and value == spec["const"],
            "B2_LITERAL_INVALID",
        )
    elif "primitive" in spec:
        require(type(value) is str and bool(value), "B2_TEXT_INVALID")
        try:
            value.encode("utf-8", "strict")
        except UnicodeError:
            require(False, "B2_TEXT_INVALID")
    elif "tag" in spec:
        require(
            type(value) is dict
            and type(value.get(spec["tag"])) is str
            and value[spec["tag"]] in spec["variants"],
            "B2_TAG_INVALID",
        )
        validate_type(value, spec["variants"][value[spec["tag"]]])
    else:
        require(type(value) is dict and set(value) == set(spec), "B2_FIELDS_INVALID")
        for key, child in spec.items():
            validate_type(value[key], child)


def validate(obj: dict[str, Any], version: str | None = None) -> None:
    version = version or obj.get("schema_version")
    require(version in SCHEMAS, "B2_VERSION_INVALID")
    validate_type(obj, SCHEMAS[version])


def parse(raw: bytes, version: str | None = None) -> dict[str, Any]:
    require(type(raw) is bytes and len(raw) <= MAX_METADATA, "B2_METADATA_LIMIT")

    def pairs(items):
        require(len({k for k, _ in items}) == len(items), "B2_DUPLICATE_KEY")
        return dict(items)

    try:
        obj = json.loads(raw, object_pairs_hook=pairs)
        require(type(obj) is dict and canonical(obj) == raw, "B2_ENCODING_INVALID")
        validate(obj, version)
        return obj
    except (ValueError, UnicodeError, TypeError, KeyError):
        raise v1.Stage12Error("B2_RECORD_INVALID") from None


def stamp(value: str) -> datetime:
    validate_type(value, "Z")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )


def binding_id(binding: dict[str, Any]) -> bytes:
    validate(binding, "stage12_observation_binding_b2_v1")
    return identity(
        "SAFE:stage12-observation-binding:b2:v1",
        [
            ("binding_version", "stage12_observation_binding_b2_v1"),
            ("binding_core", canonical(binding)),
        ],
    )


def execution_id(
    semantic: bytes,
    policy: bytes,
    materialization: bytes,
    binding: bytes,
    campaign: bytes,
) -> bytes:
    values = [
        IDENTITY,
        *(v1.digest(x) for x in (semantic, policy, materialization, binding, campaign)),
    ]
    return identity(
        "SAFE:stage12-request-observation:b2:v1",
        list(zip(EXECUTION_FIELDS, values, strict=True)),
    )


def attempt_id(execution: bytes, campaign: bytes, ordinal: int) -> bytes:
    uint(ordinal, True)
    require(ordinal <= 5, "B2_ATTEMPT_LIMIT")
    return identity(
        "SAFE:stage12-request-attempt:b2:v1",
        [
            ("receipt_version", ATTEMPT),
            ("request_execution_id", v1.digest(execution)),
            ("campaign_id", v1.digest(campaign)),
            ("attempt_number", ordinal),
        ],
    )


def descriptor(relation: str, *, scientific: bool = False) -> dict[str, Any]:
    result = copy.deepcopy(v1.descriptor(relation, scientific=scientific))
    result["schema_version"] = SCHEMA
    output = []
    for field in result["fields"]:
        name = field["name"]
        if relation == "request_execution" and name == "pelias_deployment_fingerprint":
            output.extend(
                {"name": n, "type": "D", "nullable": False}
                for n in ("observation_binding_id", "campaign_id")
            )
        elif relation == "request_execution" and name in (
            "index_data_identity",
            "effective_behavior_id",
        ):
            continue
        elif relation == "request_attempt" and name in (
            "observed_deployment_fingerprint",
            "identity_verification_receipt_sha256",
        ):
            output.append(
                {
                    "name": "segment_nonce"
                    if name == "observed_deployment_fingerprint"
                    else "preflight_observation_sha256",
                    "type": "D",
                    "nullable": False,
                }
            )
        else:
            output.append(field)
    result["fields"] = output
    return result


def columns(relation: str) -> tuple[str, ...]:
    return tuple(x["name"] for x in descriptor(relation)["fields"])


def schema(relation: str):
    types = {
        "D": pa.binary(32),
        "T": pa.large_string(),
        "U": pa.uint64(),
        "F": pa.float64(),
        "Z": pa.timestamp("us", tz="UTC"),
        "B": pa.bool_(),
        "L": pa.list_(pa.struct([])),
    }
    return pa.schema(
        [
            pa.field(f["name"], types[f["type"]], nullable=f["nullable"])
            for f in descriptor(relation)["fields"]
        ],
        metadata={b"stage12_b2_descriptor": canonical(descriptor(relation))},
    )


def row_bytes(
    relation: str, row: Mapping[str, Any], *, scientific: bool = False
) -> bytes:
    require(set(row) == set(columns(relation)), "B2_ROW_INVALID")
    values = []
    for field in descriptor(relation, scientific=scientific)["fields"]:
        value, kind = row[field["name"]], field["type"]
        if value is None:
            require(field["nullable"], "B2_ROW_INVALID")
        elif kind == "D":
            v1.digest(value)
        elif kind == "U":
            uint(value)
        elif kind == "T":
            require(type(value) is str, "B2_ROW_INVALID")
        elif kind == "F":
            require(type(value) is float and math.isfinite(value), "B2_ROW_INVALID")
        elif kind == "L":
            require(type(value) is list and value == [], "B2_ROW_INVALID")
        elif kind == "Z":
            if isinstance(value, datetime):
                require(
                    value.utcoffset() == timezone.utc.utcoffset(value),
                    "B2_TIME_INVALID",
                )
                value = value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            validate_type(value, "Z")
        values.append(value)
    return framed(values)


def relation_hash(
    relation: str,
    count: int,
    rows: Iterable[Mapping[str, Any]],
    *,
    scientific: bool = False,
) -> bytes:
    h = hashlib.sha256(
        b"SAFE:stage12-relation:b2:v1\0"
        + framed(
            [
                relation,
                sha(canonical(descriptor(relation, scientific=scientific))),
                count,
            ]
        )
    )
    last, observed = None, 0
    for row in rows:
        key = tuple(row[k] for k in KEYS[relation])
        require(last is None or last < key, "B2_RELATION_ORDER")
        h.update(row_bytes(relation, row, scientific=scientific))
        last, observed = key, observed + 1
    require(observed == count, "B2_RELATION_COUNT")
    return h.digest()


def projection_id(
    raw_set: bytes,
    capture_context: bytes,
    validation: bytes,
    extraction: bytes,
    candidate_schema: bytes,
) -> bytes:
    return identity(
        "SAFE:stage12-response-projection:b2:v1",
        [
            ("projection_version", "stage12_response_projection_b2_v1"),
            ("raw_response_set_sha256", v1.digest(raw_set)),
            ("capture_context_sha256", v1.digest(capture_context)),
            ("response_validation_contract_sha256", v1.digest(validation)),
            ("response_extraction_contract_sha256", v1.digest(extraction)),
            ("candidate_schema_sha256", v1.digest(candidate_schema)),
        ],
    )


def assets() -> dict[str, dict[str, Any]]:
    """New versioned descriptors; all original frozen assets remain unchanged."""
    from . import s12_assets as old
    from . import s12_response as response
    from . import s12_b2_publication as publication

    originals = old.objects()
    result = {}
    schema_asset = copy.deepcopy(originals[v1.SCHEMA])
    schema_asset["schema_version"] = SCHEMA
    schema_asset["relations"] = [descriptor(n) for n in RELATIONS]
    schema_asset["scientific_projections"] = [
        descriptor(n, scientific=True) for n in RELATIONS if n != "request_attempt"
    ]
    for key in ("terminal_states", "attempt_outcomes"):
        schema_asset[key] = [
            x.replace("DEPLOYMENT_IDENTITY_FAILURE", "OBSERVATION_CONTRACT_FAILURE")
            for x in schema_asset[key]
        ] + ["PERMISSION_FAILURE"]
    schema_asset["foreign_keys"]["request_execution"][-1] = (
        "observation_binding_id,campaign_id->campaign/window/evidence"
    )
    schema_asset["foreign_keys"]["request_attempt"][-1] = (
        "segment_nonce,preflight_observation_sha256->segment_admission"
    )
    result[SCHEMA] = schema_asset
    extraction = copy.deepcopy(originals[response.EXTRACTION])
    extraction["extraction_version"] = EXTRACTION
    if "candidate_schema" in extraction:
        extraction["candidate_schema"] = descriptor("request_candidate")
    result[EXTRACTION] = extraction
    for name, spec in REGISTRY["schemas"].items():
        result[name] = {
            "descriptor_version": name,
            "scope": "DEVELOPMENT_ONLY",
            "design_sha256": DESIGN_SHA256,
            "schema_bundle_sha256": BUNDLE_SHA256,
            "closed": True,
            "schema": spec,
            "named_types": TYPES,
            "live_instance": False,
        }
    result[IDENTITY] = {
        "identity_version": IDENTITY,
        "domain": "SAFE:stage12-request-observation:b2:v1",
        "ordered_fields": list(EXECUTION_FIELDS),
        "framing": "E/Named/H/J_UNCHANGED",
        "campaign_in_scientific_identity": True,
    }
    result[ATTEMPT] = {
        "receipt_version": ATTEMPT,
        "domain": "SAFE:stage12-request-attempt:b2:v1",
        "ordered_fields": [
            "receipt_version",
            "request_execution_id",
            "campaign_id",
            "attempt_number",
        ],
        "relation": descriptor("request_attempt"),
        "secret_persistence": "FORBIDDEN",
    }
    result["stage12_response_projection_b2_v1"] = {
        "projection_version": "stage12_response_projection_b2_v1",
        "domain": "SAFE:stage12-response-projection:b2:v1",
        "ordered_fields": [
            "projection_version",
            "raw_response_set_sha256",
            "capture_context_sha256",
            "response_validation_contract_sha256",
            "response_extraction_contract_sha256",
            "candidate_schema_sha256",
        ],
    }
    result["stage12_pelias_retrieval_contract_b2_v1"] = {
        "contract_version": "stage12_pelias_retrieval_contract_b2_v1",
        "design_documents": {
            **v1.DESIGN_HASHES,
            "SP_B_r2_amendment": AMENDMENT_SHA256,
            "SP_B_r2_schema": SPEC_SHA256,
            "B2_O1_design": DESIGN_SHA256,
        },
        "scientific_decision_required": True,
        "scope": "DEVELOPMENT_ONLY",
        "four_relations": list(RELATIONS),
    }
    result["stage12_pelias_retrieval_profile_b2_v1"] = {
        "profile_version": "stage12_pelias_retrieval_profile_b2_v1",
        "provenance_model": "MAINTAINED_SERVICE_OBSERVATIONS",
        "data_generation_status": "UNVERIFIED",
        "continuous_service_state": "NOT_VERIFIED",
        "required_binding_fields": [
            "window_plan_sha256",
            "observation_binding_id",
            "privacy_permission_sha256",
            "scientific_decision_sha256",
        ],
        "publication_roles": [publication.CALIBRATION, publication.FINAL],
        "C": None,
        "T": None,
        "N": None,
        "live_instance": False,
    }
    calibration = copy.deepcopy(originals["stage12_calibration_protocol_v1"])
    calibration.update(
        calibration_version="stage12_calibration_protocol_b2_v1",
        applicability="SAME_DECLARED_WINDOW_ONLY",
        cross_window_transfer="FORBIDDEN",
        scientific_amendment_sha256=AMENDMENT_SHA256,
        full_population_required=True,
    )
    result["stage12_calibration_protocol_b2_v1"] = calibration
    result["stage12_pelias_retrieval_manifest_b2_v1"] = {
        "manifest_version": "stage12_pelias_retrieval_manifest_b2_v1",
        "dataset_scientific_domain": "SAFE:stage12-dataset:b2:v1",
        "dataset_ordered_binding_fields": list(publication.DATASET_BINDINGS),
        "publication_binding_keys": list(publication.BINDINGS),
        "terminal_failures_allowed": 0,
        "full_reopen_required": True,
        "raw_packing": "INDEPENDENT_FRAMES_MAX_256_OR_64_MIB",
        "scientific_relations": [
            "retrieval_policy",
            "request_execution",
            "request_candidate",
        ],
        "audit_relation": "request_attempt",
        "nullable_for_calibration": [
            "window_closure_sha256",
            "calibration_evidence_inventory_sha256",
            "owner_freeze_sha256",
        ],
    }
    result[publication.VERSION] = {
        "record_version": publication.VERSION,
        "domain": "SAFE:stage12-publication-record:b2:v1",
        "body_keys": ["record_version", "namespace", "publication_key", "bindings"],
        "binding_keys": list(publication.BINDINGS),
        "namespaces": [publication.CALIBRATION, publication.FINAL],
        "synthetic_prefix": SYNTHETIC + "_",
        "registration": "H(domain,[record_version,record_body=J(body)])",
    }
    result["stage12_pelias_retrieval_summary_b2_v1"] = {
        "summary_version": "stage12_pelias_retrieval_summary_b2_v1",
        "minimum_distinct_source_rows": 20,
        "complementary_suppression": True,
        "protected_text_and_row_ids": "FORBIDDEN",
        "required_sections": [
            "observation_evidence",
            "permission_status",
            "window_applicability",
            "interruptions",
            "counts",
        ],
        "continuous_service_state": "NOT_VERIFIED",
        "data_generation_status": "UNVERIFIED",
    }
    return result


def verify_executable_science(start: Mapping[str, Any]) -> None:
    """No authority record may relabel the actual executable projection rules."""
    from . import s12_assets as inherited_assets
    from . import s12_response

    expected = {
        "materialization_contract_sha256": inherited_assets.hashes()[
            v1.MATERIALIZATION
        ].hex(),
        "response_validation_contract_sha256": inherited_assets.hashes()[
            s12_response.VALIDATION
        ].hex(),
        "response_extraction_contract_sha256": digest(assets()[EXTRACTION]),
        "candidate_schema_sha256": digest(descriptor("request_candidate")),
    }
    require(
        all(start.get(k) == value for k, value in expected.items()),
        "B2_EXECUTABLE_CONTRACT_MISMATCH",
    )

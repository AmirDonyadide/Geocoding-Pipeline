"""Frozen Stage 12 identities and four-relation schemas; no network or data I/O."""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, unquote_to_bytes

import pyarrow as pa

from . import s11_semantic_contract as upstream

CONTRACT = "stage12_pelias_retrieval_contract_v1"
PROFILE = "stage12_pelias_retrieval_profile_v1"
SCHEMA = "stage12_pelias_retrieval_schema_v1"
POLICY = "stage12_retrieval_policy_v1"
IDENTITY = "stage12_execution_identity_v1"
MATERIALIZATION = "stage12_request_materialization_v1"
PROJECTION = "stage12_response_projection_v1"
ATTEMPT = "stage12_attempt_receipt_v1"
RELATIONS = (
    "retrieval_policy",
    "request_execution",
    "request_attempt",
    "request_candidate",
)
SUCCESS = ("SUCCESS_WITH_CANDIDATES", "SUCCESS_ZERO_CANDIDATES")
TERMINAL = (
    *SUCCESS,
    "TECHNICAL_FAILURE_FINAL",
    "CONTRACT_FAILURE",
    "DEPLOYMENT_IDENTITY_FAILURE",
)
OUTCOMES = (*TERMINAL, "TECHNICAL_FAILURE_RETRYABLE", "UNKNOWN_DELIVERY")
BASELINE_SHA = "7543b8bac4f2953aab311fb58f73dbcb62ba401b"
DESIGN_SHA = "538f32023d2f78394e3acc5e8552f670fe0a6add"
DESIGN_HASHES = {
    "STAGE12_PELIAS_TOPN_RETRIEVAL.md": "18c62b499d0edd4e55f2a560cb7daeffb30e34bd20fa68b6df5a12ab9513c78c",
    "STAGE12_DATA_CONTRACT.md": "99b399cb77686a073feb22de736aedcc054ec35f241df84515f57ccba12cda41",
    "STAGE12_EXECUTION_CONTRACT.md": "3e00babb3da80ad6d9db43d8dfb1af47d619b95fce656572a404731d8db936ca",
    "STAGE12_DEVELOPMENT_CALIBRATION.md": "56f315ba462829f815a41514bb6499abb8694f5a8323ba51397f1fe289eeb4ad",
    "STAGE12_DESIGN_REVIEW.md": "253005e049cd5084cb3b65ca3ef1b7942c00ee7c96b7a8f68e9a132b35c14cfe",
}
EXECUTION_FIELDS = (
    "identity_version",
    "query_semantic_id",
    "retrieval_policy_id",
    "materialization_contract_sha256",
    "pelias_deployment_fingerprint",
    "index_data_identity",
    "effective_behavior_id",
)
CANDIDATE_STRINGS = tuple(
    """
gid feature_id layer source source_id geometry_type confidence match_type accuracy
label name housenumber street postalcode neighbourhood borough locality locality_gid
localadmin localadmin_gid county county_gid macrocounty macrocounty_gid region
region_gid region_a macroregion macroregion_gid macroregion_a country country_gid
country_a continent continent_gid
""".split()
)
# The compact declarations below are ordered exactly as the frozen data contract.
DECLARATIONS = {
    "retrieval_policy": "retrieval_policy_id:D policy_version:T result_limit:U retention:T result_options:L",
    "request_execution": """
request_execution_id:D query_semantic_id:D retrieval_policy_id:D
materialization_contract_sha256:D pelias_deployment_fingerprint:D index_data_identity:D
effective_behavior_id:D request_target_sha256:D? terminal_state:T reason_code:T
terminal_attempt_id:D? candidate_count:U? response_sha256:D? response_bytes:U?
raw_pack_key:T? raw_frame_offset:U? raw_frame_length:U? response_completed_utc:Z?
""",
    "request_attempt": """
attempt_id:D request_execution_id:D campaign_id:D attempt_number:U
campaign_start_sha256:D operations_policy_sha256:D started_utc:Z finished_utc:Z?
elapsed_ms:U? http_status:U? outcome:T reason_code:T received_body_bytes:U
application_payload_bytes:U? content_type:T? content_encoding:T? retry_delay_ms:U?
retry_after_seconds:U? observed_deployment_fingerprint:D?
identity_verification_receipt_sha256:D response_validation_contract_sha256:D response_sha256:D?
""",
    "request_candidate": """
request_execution_id:D rank:U response_sha256:D raw_feature_sha256:D
feature_byte_offset:U feature_byte_length:U gid:T? feature_id:T? layer:T source:T
source_id:T? geometry_type:T longitude:F latitude:F confidence:F? match_type:T?
accuracy:T? label:T? name:T? housenumber:T? street:T? postalcode:T? neighbourhood:T?
borough:T? locality:T? locality_gid:T? localadmin:T? localadmin_gid:T? county:T?
county_gid:T? macrocounty:T? macrocounty_gid:T? region:T? region_gid:T? region_a:T?
macroregion:T? macroregion_gid:T? macroregion_a:T? country:T? country_gid:T?
country_a:T? continent:T? continent_gid:T?
""",
}
KEYS = {
    "retrieval_policy": ("retrieval_policy_id",),
    "request_execution": ("request_execution_id",),
    "request_attempt": ("attempt_id",),
    "request_candidate": ("request_execution_id", "rank"),
}
AUDIT_COLUMNS = {
    "retrieval_policy": (),
    "request_execution": (
        "raw_pack_key",
        "raw_frame_offset",
        "raw_frame_length",
        "terminal_attempt_id",
        "response_completed_utc",
    ),
    "request_candidate": ("feature_byte_offset", "feature_byte_length"),
}


class Stage12Error(ValueError):
    """Only caller-selected static codes, never exception text or server values."""


def require(condition: bool, code: str = "S12_CONTRACT_INVALID") -> None:
    if not condition:
        raise Stage12Error(code)


def sha(raw: bytes) -> bytes:
    return hashlib.sha256(raw).digest()


def digest(value: Any) -> bytes:
    require(type(value) is bytes and len(value) == 32, "S12_DIGEST_INVALID")
    return bytes(value)


def canonical(value: Any) -> bytes:
    def validate(item: Any) -> None:
        if type(item) is dict:
            require(all(type(k) is str for k in item), "S12_ENCODING_INVALID")
            for k, v in item.items():
                validate(k)
                validate(v)
        elif type(item) in (tuple, list):
            for v in item:
                validate(v)
        elif type(item) is str:
            try:
                item.encode("utf-8", "strict")
            except UnicodeError:
                raise Stage12Error("S12_ENCODING_INVALID") from None
        else:
            require(item is None or type(item) in (int, bool), "S12_ENCODING_INVALID")

    validate(value)
    return upstream.canonical(value)


def framed(values: Sequence[Any]) -> bytes:
    """E framing; tag 06 is permitted only for finite logical-row binary64."""

    def encode(value: Any) -> bytes:
        if type(value) is float:
            require(math.isfinite(value), "S12_ENCODING_INVALID")
            return b"\x06" + struct.pack(">d", value)
        if type(value) in (tuple, list):
            return b"\x05" + framed(value)
        try:
            return upstream.encoded(value)
        except upstream.Stage11Error:
            raise Stage12Error("S12_ENCODING_INVALID") from None

    return len(values).to_bytes(8, "big") + b"".join(encode(v) for v in values)


def named(domain: str, fields: Sequence[tuple[str, Any]]) -> bytes:
    names = [k for k, _ in fields]
    require(len(set(names)) == len(names), "S12_ENCODING_INVALID")
    require(
        all(type(k) is str and re.fullmatch("[a-z][a-z0-9_]*", k) for k in names),
        "S12_ENCODING_INVALID",
    )
    try:
        prefix = domain.encode("ascii", "strict")
    except UnicodeError:
        raise Stage12Error("S12_ENCODING_INVALID") from None
    require(
        prefix.startswith(b"SAFE:stage12-") and b"\0" not in prefix,
        "S12_ENCODING_INVALID",
    )
    # Identity preimages never introduce the row-only floating-point extension.
    try:
        body = upstream.framed(fields)
    except upstream.Stage11Error:
        raise Stage12Error("S12_ENCODING_INVALID") from None
    return prefix + b"\0" + body


def identity(domain: str, fields: Sequence[tuple[str, Any]]) -> bytes:
    return sha(named(domain, fields))


def policy(limit: int) -> dict[str, Any]:
    require(type(limit) is int and 0 < limit < 2**64, "S12_POLICY_INVALID")
    fields = [
        ("policy_version", POLICY),
        ("result_limit", limit),
        ("retention", "ALL_RETURNED_IN_ORDER"),
        ("result_options", []),
    ]
    return {
        "retrieval_policy_id": identity("SAFE:stage12-retrieval-policy:v1", fields),
        **dict(fields),
    }


def validate_policy(row: Mapping[str, Any]) -> None:
    require(set(row) == set(columns("retrieval_policy")), "S12_POLICY_INVALID")
    require(dict(row) == policy(row["result_limit"]), "S12_POLICY_INVALID")


def execution_id(binding: Mapping[str, Any]) -> bytes:
    require(set(binding) == set(EXECUTION_FIELDS), "S12_EXECUTION_BINDING_INVALID")
    require(binding["identity_version"] == IDENTITY, "S12_EXECUTION_BINDING_INVALID")
    for k in EXECUTION_FIELDS[1:]:
        digest(binding[k])
    return identity(
        "SAFE:stage12-request-execution:v1", [(k, binding[k]) for k in EXECUTION_FIELDS]
    )


def attempt_id(execution: bytes, campaign: bytes, number: int) -> bytes:
    require(type(number) is int and 1 <= number <= 5, "S12_ATTEMPT_BUDGET_INVALID")
    return identity(
        "SAFE:stage12-request-attempt:v1",
        [
            ("receipt_version", ATTEMPT),
            ("request_execution_id", digest(execution)),
            ("campaign_id", digest(campaign)),
            ("attempt_number", number),
        ],
    )


def projection_id(
    raw_set: bytes,
    capture: bytes,
    validation: bytes,
    extraction: bytes,
    schema_hash: bytes,
) -> bytes:
    return identity(
        "SAFE:stage12-response-projection:v1",
        [
            ("projection_version", PROJECTION),
            ("raw_response_set_sha256", digest(raw_set)),
            ("capture_context_sha256", digest(capture)),
            ("response_validation_contract_sha256", digest(validation)),
            ("response_extraction_contract_sha256", digest(extraction)),
            ("candidate_schema_sha256", digest(schema_hash)),
        ],
    )


def materialize(
    core: Mapping[str, Any],
    semantic_id: bytes,
    retrieval: Mapping[str, Any],
    *,
    target_limit: int,
) -> tuple[bytes, bytes]:
    try:
        preimage = upstream.core_bytes(core)
    except upstream.Stage11Error:
        raise Stage12Error("S12_SEMANTIC_REQUEST_INVALID") from None
    require(sha(preimage) == digest(semantic_id), "S12_SEMANTIC_ID_MISMATCH")
    validate_policy(retrieval)
    params = {k: core[k] for k in upstream.NULLABLE if core[k] is not None}
    params.update(
        {
            "boundary.country": core["boundary_country"],
            "size": str(retrieval["result_limit"]),
        }
    )
    encoded = []
    for key, value in sorted(params.items()):
        raw = value.encode("utf-8", "strict")
        escaped = quote(raw, safe="-._~")
        require(unquote_to_bytes(escaped) == raw, "S12_ENCODING_INVALID")
        encoded.append(key + "=" + escaped)
    target = (core["endpoint"] + "?" + "&".join(encoded)).encode("ascii")
    require(
        type(target_limit) is int and 0 < len(target) <= target_limit,
        "REQUEST_TARGET_TOO_LARGE",
    )
    return target, sha(b"GET\0" + target)


def columns(relation: str) -> tuple[str, ...]:
    return tuple(f.split(":")[0] for f in DECLARATIONS[relation].split())


def descriptor(relation: str, *, scientific: bool = False) -> dict[str, Any]:
    require(relation in RELATIONS, "S12_SCHEMA_INVALID")
    require(not scientific or relation != "request_attempt", "S12_AUDIT_ONLY_RELATION")
    fields = []
    for f in DECLARATIONS[relation].split():
        name, kind = f.split(":")
        if scientific and name in AUDIT_COLUMNS.get(relation, ()):
            continue
        fields.append(
            {"name": name, "type": kind.rstrip("?"), "nullable": kind.endswith("?")}
        )
    return {
        "schema_version": SCHEMA,
        "relation": relation,
        "scope": "scientific" if scientific else "full",
        "fields": fields,
        "primary_key": list(KEYS[relation]),
        "projection_scope_required": relation == "request_candidate",
    }


def schema(relation: str) -> Any:
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
        ]
    )


def row_bytes(
    relation: str, row: Mapping[str, Any], *, scientific: bool = False
) -> bytes:
    require(set(row) == set(columns(relation)), "S12_ROW_INVALID")
    values = []
    for f in descriptor(relation, scientific=scientific)["fields"]:
        value = row[f["name"]]
        kind = f["type"]
        if value is None:
            require(f["nullable"], "S12_ROW_INVALID")
        elif kind == "D":
            digest(value)
        elif kind == "U":
            require(type(value) is int and 0 <= value < 2**64, "S12_ROW_INVALID")
        elif kind == "T":
            require(type(value) is str, "S12_ROW_INVALID")
        elif kind == "F":
            require(type(value) is float and math.isfinite(value), "S12_ROW_INVALID")
        elif kind == "L":
            require(type(value) is list and value == [], "S12_ROW_INVALID")
        elif kind == "Z":
            if type(value) is datetime:
                require(
                    value.tzinfo is not None
                    and value.utcoffset() == timezone.utc.utcoffset(value),
                    "S12_ROW_INVALID",
                )
                value = value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            require(
                type(value) is str
                and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value)
                is not None,
                "S12_ROW_INVALID",
            )
        values.append(value)
    return framed(values)


def relation_hash(
    relation: str,
    count: int,
    rows: Iterable[Mapping[str, Any]],
    *,
    scientific: bool = False,
) -> bytes:
    desc = descriptor(relation, scientific=scientific)
    h = hashlib.sha256(
        b"SAFE:stage12-relation:v1\0" + framed([relation, sha(canonical(desc)), count])
    )
    previous: tuple[Any, ...] | None = None
    observed = 0
    for row in rows:
        key = tuple(row[k] for k in KEYS[relation])
        require(previous is None or previous < key, "S12_RELATION_ORDER_INVALID")
        h.update(row_bytes(relation, row, scientific=scientific))
        previous = key
        observed += 1
    require(observed == count, "S12_RELATION_COUNT_INVALID")
    return h.digest()


def capture_hashes(
    count: int, captures: Iterable[Mapping[str, Any]]
) -> tuple[bytes, bytes]:
    raw = hashlib.sha256(b"SAFE:stage12-response-set:v1\0" + framed([count]))
    context = hashlib.sha256(b"SAFE:stage12-capture-context:v1\0" + framed([count]))
    previous: bytes | None = None
    observed = 0
    for row in captures:
        execution = digest(row["request_execution_id"])
        require(previous is None or previous < execution, "S12_CAPTURE_ORDER_INVALID")
        require(row["payload_complete"] is True, "S12_CAPTURE_INCOMPLETE")
        raw.update(
            framed([execution, digest(row["response_sha256"]), row["response_bytes"]])
        )
        context.update(
            framed(
                [
                    execution,
                    digest(row["request_target_sha256"]),
                    row["http_status"],
                    row["content_type"],
                    row["content_encoding"],
                    True,
                ]
            )
        )
        previous = execution
        observed += 1
    require(observed == count, "S12_CAPTURE_COUNT_INVALID")
    return raw.digest(), context.digest()


DATASET_BINDINGS = (
    "stage12_input_binding_sha256",
    "contract_sha256",
    "profile_sha256",
    "schema_sha256",
    "response_projection_id",
    "retrieval_policy_id",
    "pelias_deployment_fingerprint",
    "index_data_identity",
    "effective_behavior_id",
)


def dataset_fingerprint(
    bindings: Mapping[str, bytes],
    relation_digests: Sequence[tuple[str, bytes, int]],
    raw_response_set_sha256: bytes,
    scientific_summary_sha256: bytes,
) -> bytes:
    """Frozen scientific projection; executable/timing/packing live only in audit."""
    require(set(bindings) == set(DATASET_BINDINGS), "S12_DATASET_BINDING_INVALID")
    require(
        [row[0] for row in relation_digests]
        == ["retrieval_policy", "request_execution", "request_candidate"],
        "S12_DATASET_BINDING_INVALID",
    )
    for _, fingerprint, count in relation_digests:
        digest(fingerprint)
        require(type(count) is int and count >= 0, "S12_DATASET_BINDING_INVALID")
    fields: list[tuple[str, Any]] = [
        (key, digest(bindings[key])) for key in DATASET_BINDINGS
    ]
    fields.extend(
        [
            ("scientific_relations", list(relation_digests)),
            ("raw_response_set_sha256", digest(raw_response_set_sha256)),
            ("scientific_summary_sha256", digest(scientific_summary_sha256)),
        ]
    )
    return identity("SAFE:stage12-dataset:v1", fields)

"""Fresh specification-derived Stage 11 oracle. No candidate imports or I/O."""

import hashlib
import json
import re


FIELDS = tuple(
    """contract_version schema_version encoding_version semantic_policy_version
endpoint search_mode text address postalcode locality region country
boundary_country_namespace boundary_country language_policy layers_policy
sources_policy spatial_policy additional_parameter_policy""".split()
)
PAYLOAD = tuple("text address postalcode locality region country".split())
CONSTANTS = {
    "contract_version": "stage11_semantic_request_contract_v1",
    "schema_version": "stage11_semantic_request_schema_v1",
    "encoding_version": "stage11_semantic_request_encoding_v1",
    "semantic_policy_version": "stage11_semantic_request_profile_v1",
    "region": None,
    "country": None,
    "boundary_country_namespace": "STAGE10_RECOGNIZED_ISO_ALPHA2_V1",
    "language_policy": "NO_REQUEST_LANGUAGE_OVERRIDE",
    "layers_policy": "OMITTED_API_SELECTION",
    "sources_policy": "OMITTED_API_SELECTION",
    "spatial_policy": "NONE",
    "additional_parameter_policy": "REJECT_UNLISTED",
}
DOMAIN = b"SAFE:stage11-query-semantic:v1\0"


def canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def u64(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError("ORACLE_U64")
    return value.to_bytes(8, "big")


def atom(value):
    if value is None:
        return b"\x00"
    if type(value) is str:
        data = value.encode("utf-8", "strict")
        return b"\x01" + u64(len(data)) + data
    if type(value) is bytes:
        return b"\x02" + u64(len(value)) + value
    if type(value) is int:
        return b"\x03" + u64(value)
    if type(value) is bool:
        return b"\x04" + (b"\x01" if value else b"\x00")
    if type(value) in (tuple, list):
        return b"\x05" + sequence(value)
    raise ValueError("ORACLE_TYPE")


def sequence(values):
    return u64(len(values)) + b"".join(atom(v) for v in values)


def identity(domain, *values):
    return hashlib.sha256(
        b"SAFE:" + domain.encode("ascii") + b"\0" + sequence(values)
    ).digest()


def valid(core):
    if type(core) is not dict or set(core) != set(FIELDS):
        return False
    for field in FIELDS:
        value = core[field]
        if value is None and field in PAYLOAD:
            continue
        if type(value) is not str or not value:
            return False
        try:
            value.encode("utf-8", "strict")
        except UnicodeError:
            return False
    if any(core[k] != v for k, v in CONSTANTS.items()):
        return False
    if re.fullmatch("[A-Z]{2}", core["boundary_country"]) is None:
        return False
    if (core["endpoint"], core["search_mode"]) == ("/v1/search", "FULL_TEXT"):
        return core["text"] is not None and all(core[k] is None for k in PAYLOAD[1:])
    if (core["endpoint"], core["search_mode"]) == (
        "/v1/search/structured",
        "STRUCTURED",
    ):
        return (
            core["text"] is None
            and core["address"] is not None
            and (core["postalcode"] is not None or core["locality"] is not None)
            and core["region"] is None
            and core["country"] is None
        )
    return False


def core_bytes(core, *, validate=True):
    if validate and not valid(core):
        raise ValueError("ORACLE_INVALID_CORE")
    return DOMAIN + sequence([(field, core[field]) for field in FIELDS])


def project(intent, selection):
    expected = {
        "intent_version",
        "endpoint",
        "search_mode",
        *PAYLOAD,
        "boundary_country",
        "retrieval_policy_slot",
    }
    if (
        set(intent) != expected
        or intent["intent_version"] != "stage10_query_intent_v1"
        or intent["retrieval_policy_slot"] != "SAFE_PELIAS_COMMON_RETRIEVAL_V1"
        or selection != "ALL_ELIGIBLE_CATALOG"
    ):
        raise ValueError("ORACLE_INVALID_INTENT")
    result = {
        **CONSTANTS,
        **{
            k: intent[k]
            for k in ("endpoint", "search_mode", *PAYLOAD, "boundary_country")
        },
    }
    if not valid(result):
        raise ValueError("ORACLE_INVALID_PROJECTION")
    return result


def invented(text="x", country="DE", structured=False):
    core = {
        **CONSTANTS,
        **dict.fromkeys(PAYLOAD),
        "boundary_country": country,
        "endpoint": "/v1/search",
        "search_mode": "FULL_TEXT",
        "text": text,
    }
    if structured:
        core.update(
            endpoint="/v1/search/structured",
            search_mode="STRUCTURED",
            text=None,
            address=text,
            postalcode="0",
        )
    return core


def schema(name):
    import pyarrow as pa

    digest = pa.binary(32)
    if name == "semantic_request":
        return pa.schema(
            [
                pa.field("query_semantic_id", digest, nullable=False),
                pa.field(
                    "core",
                    pa.struct(
                        [
                            pa.field(k, pa.large_string(), nullable=k in PAYLOAD)
                            for k in FIELDS
                        ]
                    ),
                    nullable=False,
                ),
            ]
        )
    if name == "hypothesis_request_map":
        return pa.schema(
            [
                pa.field(k, digest, nullable=False)
                for k in ("hypothesis_id", "query_semantic_id")
            ]
        )
    raise ValueError("ORACLE_RELATION")


def relation_hash(name, descriptor_sha, count, rows, *, validate=True):
    digest = hashlib.sha256(
        b"SAFE:stage11-relation:v1\0"
        + sequence([name, bytes.fromhex(descriptor_sha), count])
    )
    seen, previous = 0, None
    for row in rows:
        if name == "semantic_request":
            key, payload = (
                row["query_semantic_id"],
                core_bytes(row["core"], validate=validate),
            )
            if validate and hashlib.sha256(payload).digest() != key:
                raise ValueError("ORACLE_ID")
        else:
            key, payload = row["hypothesis_id"], row["query_semantic_id"]
        if validate and (len(key) != 32 or (previous is not None and key <= previous)):
            raise ValueError("ORACLE_PK")
        digest.update(sequence([key, payload]))
        previous, seen = key, seen + 1
    if validate and seen != count:
        raise ValueError("ORACLE_COUNT")
    return digest.hexdigest()

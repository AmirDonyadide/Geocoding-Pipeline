"""Independent synthetic byte oracle and frozen validity-matrix challenges."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as s10
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c

ORDER = (
    "contract_version schema_version encoding_version semantic_policy_version endpoint search_mode "
    "text address postalcode locality region country boundary_country_namespace boundary_country "
    "language_policy layers_policy sources_policy spatial_policy additional_parameter_policy"
).split()


def independent_bytes(core: dict[str, Any]) -> bytes:
    result = bytearray(b"SAFE:stage11-query-semantic:v1\x00")
    result += struct.pack("!Q", 19)
    for key in ORDER:
        result += b"\x05" + struct.pack("!Q", 2)
        for value in (key, core[key]):
            if value is None:
                result += b"\x00"
            else:
                content = value.encode("utf-8", "strict")
                result += b"\x01" + struct.pack("!Q", len(content)) + content
    return bytes(result)


def full(
    text: str = " Fictional café\nΑθήνα\t𐐀 ", country: str = "DE"
) -> dict[str, Any]:
    return c.project(s10.full_intent(text, country), s10.MODE)


def structured() -> dict[str, Any]:
    intent = s10.full_intent("placeholder", "DE")
    intent.update(
        endpoint="/v1/search/structured",
        search_mode="STRUCTURED",
        text=None,
        address="Invented road 1",
        postalcode="00123",
        locality="Fictional city",
    )
    return c.project(intent, s10.MODE)


@pytest.mark.parametrize("core", [full(), structured()])
def test_independent_named_binary_oracle(core: dict[str, Any]) -> None:
    expected = independent_bytes(core)
    assert c.core_bytes(core) == expected
    assert c.semantic_id(expected) == hashlib.sha256(expected).digest()
    assert len(c.semantic_id(expected)) == 32
    assert c.decode_core(expected) == core
    assert c.core_bytes(dict(reversed(list(core.items())))) == expected


@pytest.mark.parametrize(
    "value",
    [
        "X",
        "x",
        " x",
        "x ",
        "x  x",
        "x x",
        "x\nx",
        r"x\nx",
        "é",
        "e\u0301",
        "\ufeffx",
        "x\rx",
        "x\tx",
        "𐐀",
        "اختبار",
        "null",
        "+&=%",
    ],
)
def test_exact_utf8_no_normalization(value: str) -> None:
    raw = c.core_bytes(full(value))
    assert raw == independent_bytes(full(value))
    assert c.decode_core(raw)["text"] == value
    assert b"\x01" + struct.pack("!Q", len(value.encode())) + value.encode() in raw


def test_near_strings_never_merge() -> None:
    values = ["x", "X", "x ", " x", "x\nx", r"x\nx", "é", "e\u0301"]
    assert len({c.semantic_id(c.core_bytes(full(v))) for v in values}) == len(values)


@pytest.mark.parametrize("field", ORDER)
def test_every_field_is_bound_or_rejected(field: str) -> None:
    original = (
        structured() if field in ("address", "postalcode", "locality") else full()
    )
    changed = dict(original)
    changed[field] = "FR" if field == "boundary_country" else "different"
    if field in ("text", "address", "postalcode", "locality", "boundary_country"):
        assert c.core_bytes(changed) != c.core_bytes(original)
        assert c.semantic_id(c.core_bytes(changed)) != c.semantic_id(
            c.core_bytes(original)
        )
    else:
        with pytest.raises(c.Stage11Error):
            c.core_bytes(changed)


@pytest.mark.parametrize("field", ORDER)
def test_every_canonical_field_required(field: str) -> None:
    core = full()
    del core[field]
    with pytest.raises(c.Stage11Error):
        c.core_bytes(core)


@pytest.mark.parametrize("value", ["", 123, True, [], {}, 1.5, b"x", "\ud800"])
@pytest.mark.parametrize("field", ["text", "postalcode", "boundary_country"])
def test_invalid_scalar_types_and_empty(field: str, value: Any) -> None:
    core = structured() if field == "postalcode" else full()
    core[field] = value
    with pytest.raises(c.Stage11Error):
        c.core_bytes(core)


@pytest.mark.parametrize(
    "extra",
    [
        "size",
        "top_n",
        "hostname",
        "host",
        "headers",
        "Accept-Language",
        "lang",
        "layers",
        "sources",
        "focus.point.lat",
        "spatial",
        "retrieval_policy_binding",
        "header_policy",
        "retrieval_policy",
        "path",
        "shard",
        "thread",
        "job_id",
        "source_row",
        "family",
    ],
)
def test_unknown_execution_and_result_affecting_parameters_rejected(extra: str) -> None:
    with pytest.raises(c.Stage11Error, match="S11_PARAMETER_POLICY_INVALID"):
        c.core_bytes({**full(), extra: "unlisted"})


def test_null_optional_and_modes_and_country_roles() -> None:
    original = structured()
    changed = {**original, "postalcode": None}
    assert c.core_bytes(original) != c.core_bytes(changed)
    assert c.core_bytes(full(original["address"])) != c.core_bytes(original)
    for mutations in (
        {"locality": None, "postalcode": None},
        {"country": "DE"},
        {"region": "X"},
        {"boundary_country": None},
        {"boundary_country": "de"},
        {"boundary_country": "DEU"},
        {"boundary_country": " DE"},
        {"endpoint": "/v1/search"},
        {"text": "x"},
    ):
        with pytest.raises(c.Stage11Error):
            c.core_bytes({**original, **mutations})


def test_projection_cannot_repair_upstream_and_policies_stable() -> None:
    intent = s10.full_intent("invented", "DE")
    for change in (
        {"country": "DE"},
        {"region": "R"},
        {"intent_version": "unknown"},
        {"retrieval_policy_slot": "Q7"},
        {"size": 1},
    ):
        with pytest.raises(c.Stage11Error):
            c.project({**intent, **change}, s10.MODE)
    for status in ("TOP_N", "BUDGETED", "", None):
        with pytest.raises(c.Stage11Error):
            c.project(intent, status)
    core = full()
    assert core["language_policy"] == "NO_REQUEST_LANGUAGE_OVERRIDE"
    assert core["layers_policy"] == core["sources_policy"] == "OMITTED_API_SELECTION"
    assert core["spatial_policy"] == "NONE"
    assert core["additional_parameter_policy"] == "REJECT_UNLISTED"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b + b"x",
        lambda b: b[:-1],
        lambda b: b.replace(b"\x01", b"\xff", 1),
        lambda b: b.replace(b"contract_version", b"schema_version__", 1),
        lambda b: b[: len(c.DOMAIN)] + b"\xff" * 8 + b[len(c.DOMAIN) + 8 :],
    ],
)
def test_malformed_framing_rejected(mutation: Any) -> None:
    with pytest.raises(c.Stage11Error):
        c.decode_core(mutation(c.core_bytes(full())))


def test_encoder_type_tags_overflow_and_json_duplicates() -> None:
    assert c.encoded(True) == b"\x04\x01"
    assert c.encoded(1) == b"\x03" + b"\0" * 7 + b"\x01"
    assert c.encoded(None) != c.encoded("") != c.encoded(b"")
    for invalid in (-1, 2**64):
        with pytest.raises(c.Stage11Error):
            c.encoded(invalid)
    for raw in (b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"x":1.0}\n', b'{"x":1}garbage'):
        with pytest.raises(c.Stage11Error):
            c.decode_json(raw)


def test_machine_assets_and_fixed_byte_vectors() -> None:
    root = Path(__file__).resolve().parents[1]
    assert assets.verify(root) == assets.identifiers(root)
    vectors = json.loads(
        (root / "tests/fixtures/stage11_canonical_vectors.json").read_bytes()
    )
    for vector in vectors:
        assert c.core_bytes(vector["core"]).hex() == vector["hex"]
        assert c.semantic_id(bytes.fromhex(vector["hex"])).hex() == vector["sha256"]


def test_core_has_no_execution_identity() -> None:
    raw = c.core_bytes(full())
    for token in (
        b"size",
        b"top_n",
        b"hostname",
        b"headers",
        b"/local",
        b"/panfs",
        b"job_id",
        b"shard",
        b"thread",
    ):
        assert token not in raw
    assert tuple(c.schema("semantic_request").names) == ("query_semantic_id", "core")
    assert tuple(c.schema("hypothesis_request_map").names) == (
        "hypothesis_id",
        "query_semantic_id",
    )

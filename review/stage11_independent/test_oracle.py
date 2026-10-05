"""Independent synthetic challenges, using only invented strings."""

import hashlib
import itertools

import pytest

import oracle as o
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c


@pytest.mark.parametrize(
    "text",
    [
        "x",
        " ",
        "\0",
        "é",
        "e\u0301",
        "𐐀",
        "اختبار",
        "\ufeff",
        "\n",
        "\\n",
        " x ",
        "X",
        "x  x",
        "null",
        "0",
    ],
)
@pytest.mark.parametrize(
    "structured,country", itertools.product([False, True], ["DE", "FR"])
)
def test_independent_bytes(text, structured, country):
    core = o.invented(text, country, structured)
    expected = o.core_bytes(core)
    assert c.core_bytes(dict(reversed(list(core.items())))) == expected
    assert c.decode_core(expected) == core
    assert c.semantic_id(expected) == hashlib.sha256(expected).digest()


def test_hand_calculated_frames():
    assert o.sequence([None, "é", b"x", 1, True, []]).hex() == (
        "0000000000000006"
        "00"
        "010000000000000002c3a9"
        "02000000000000000178"
        "030000000000000001"
        "0401"
        "050000000000000000"
    )
    assert c.framed([None, "é", b"x", 1, True, []]) == o.sequence(
        [None, "é", b"x", 1, True, []]
    )
    assert c.encoded(2**64 - 1) == bytes.fromhex("03ffffffffffffffff")
    for value in (-1, 2**64, 1.0, {}, b"\xff".decode("latin1") + "\ud800"):
        with pytest.raises((ValueError, UnicodeError)):
            o.atom(value)
        with pytest.raises(c.Stage11Error):
            c.encoded(value)


@pytest.mark.parametrize("field", o.FIELDS)
@pytest.mark.parametrize(
    "value", [None, "", True, 0, 1.5, [], {}, b"x", "\udfff", "default"]
)
@pytest.mark.parametrize("structured", [False, True])
def test_validity_matrix(field, value, structured):
    core = o.invented(structured=structured)
    core[field] = value
    if o.valid(core):
        assert c.core_bytes(core) == o.core_bytes(core)
    else:
        with pytest.raises(c.Stage11Error):
            c.core_bytes(core)


@pytest.mark.parametrize("field", o.FIELDS)
def test_missing_column(field):
    core = o.invented()
    del core[field]
    with pytest.raises(c.Stage11Error):
        c.core_bytes(core)


@pytest.mark.parametrize(
    "extra",
    "size top_n retrieval_depth retrieval_policy retrieval_policy_binding header_policy headers Accept-Language lang layers sources focus hostname deployment index authentication SLURM_JOB_ID path parameters".split(),
)
def test_forbidden_identity_fields(extra):
    for value in (None, 1, 3, 5, 10, "default"):
        with pytest.raises(c.Stage11Error):
            c.core_bytes({**o.invented(), extra: value})


def test_field_roles_and_false_equivalence():
    cores = [
        o.invented(v, country, mode)
        for v, country, mode in itertools.product(
            ["x", "X", " x", "x ", "é", "e\u0301"], ["DE", "FR"], [False, True]
        )
    ]
    a = o.invented("field-role", structured=True)
    b = {**a, "postalcode": None, "locality": "0"}
    cores += [a, b]
    assert len({o.core_bytes(v) for v in cores}) == len(cores)
    assert len({c.semantic_id(c.core_bytes(v)) for v in cores}) == len(cores)
    for change in (
        {"endpoint": "/v1/search"},
        {"country": "DE"},
        {"postalcode": None},
        {"text": "x"},
    ):
        with pytest.raises(c.Stage11Error):
            c.core_bytes({**a, **change})


def test_malformed_vectors():
    raw = o.core_bytes(o.invented("é"))
    cases = [
        raw[:-1],
        raw + b"\0",
        raw.replace(b"contract_version", b"contract_versioN", 1),
        raw.replace(b"\xc3\xa9", b"\xff\xff"),
        raw[: len(o.DOMAIN)] + b"\xff" * 8 + raw[len(o.DOMAIN) + 8 :],
    ]
    for invalid in cases:
        with pytest.raises(c.Stage11Error):
            c.decode_core(invalid)


def test_schema_and_relation_oracle():
    for name in ("semantic_request", "hypothesis_request_map"):
        assert c.schema(name).equals(o.schema(name), check_metadata=False)
    cores = [o.invented("x"), o.invented("x", "FR"), o.invented("é", structured=True)]
    rows = sorted(
        [
            {
                "core": core,
                "query_semantic_id": hashlib.sha256(o.core_bytes(core)).digest(),
            }
            for core in cores
        ],
        key=lambda r: r["query_semantic_id"],
    )
    expected = o.relation_hash(
        "semantic_request", c.descriptor_sha("semantic_request").hex(), len(rows), rows
    )
    assert c.relation_digest("semantic_request", len(rows), rows).hex() == expected

from __future__ import annotations

import copy
import hashlib
import json
import math

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_response as r
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from stage12_synthetic import HASH, body, feature


def project(raw, size=3, **overrides):
    args = {
        "size": size,
        "http_status": 200,
        "content_type": "application/json",
        "encoding": "identity",
        "layers": frozenset({"address", "street", "locality"}),
        "sources": frozenset({"synthetic"}),
        "expected_echo": {},
    }
    args.update(overrides)
    return r.extract(raw, HASH, **args)


def test_rank_duplicates_slices_and_descriptive_metadata():
    raw = body()
    result = project(raw)
    assert result.outcome == "SUCCESS_WITH_CANDIDATES"
    assert [v["rank"] for v in result.candidates] == [1, 2]
    assert (
        result.candidates[0]["raw_feature_sha256"]
        == result.candidates[1]["raw_feature_sha256"]
    )
    assert (
        result.candidates[0]["feature_byte_offset"]
        != result.candidates[1]["feature_byte_offset"]
    )
    for v in result.candidates:
        assert v["source_id"] == "0001"
        assert v["confidence"] == 0.1
        assert v["match_type"] == "exact"
        assert v["accuracy"] == "point"
        assert v["geometry_type"] == "Point"
        assert math.copysign(1, v["longitude"]) == -1
        part = raw[
            v["feature_byte_offset"] : v["feature_byte_offset"]
            + v["feature_byte_length"]
        ]
        assert json.loads(part) == feature()
        assert v["raw_feature_sha256"] == hashlib.sha256(part).digest()
        assert v["response_sha256"] == hashlib.sha256(raw).digest()
        assert not {"score", "correct", "rooftop", "usable"} & set(v)


@pytest.mark.parametrize("level", [-1, 1, 3, 9])
def test_compression_exact_bytes_offline_reextraction(level):
    raw = body()
    frame = r.compress(raw, level=level)
    restored = r.decompress(frame, length=len(raw), expected_hash=c.sha(raw))
    assert restored == raw
    assert c.sha(frame) != c.sha(raw)
    assert project(restored) == project(raw)


def test_raw_whitespace_and_key_order_are_distinct_but_structures_equal():
    raw = body()
    altered = json.dumps(json.loads(raw), sort_keys=True, indent=2).encode()
    a, b = project(raw), project(altered)
    assert a.response_sha256 != b.response_sha256
    assert a.feature_structures == b.feature_structures
    token_change = raw.replace(b"0.1", b"0.10")
    assert project(token_change).feature_structures != a.feature_structures


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"{}",
        b"[]",
        b"null",
        b"\xef\xbb\xbf{}",
        b'{"type":"FeatureCollection","features":null}',
        b'{"type":"FeatureCollection","features":[] ,"features":[]}',
        b'{"type":"FeatureCollection","features":[],"x":NaN}',
        b'{"type":"FeatureCollection","features":[],"x":1e9999}',
        b'{"type":"FeatureCollection","features":[],"x":"\\ud800"}',
        b'{"type":"FeatureCollection","features":[],"x":"\\q"}',
        b'{"type":"FeatureCollection","features":[],"x":01}',
        b'{"type":"FeatureCollection","features":[],}',
        b'{"type":"FeatureCollection","features":[]} trailing',
    ],
)
def test_strict_json(raw):
    with pytest.raises(c.Stage12Error):
        project(raw)


@pytest.mark.parametrize(
    "path,value",
    [
        ("type", "Other"),
        ("geometry", None),
        ("geometry.type", "Polygon"),
        ("geometry.coordinates", [1, 2, 3]),
        ("geometry.coordinates", [True, 2]),
        ("geometry.coordinates", [181, 0]),
        ("geometry.coordinates", [0, -91]),
        ("geometry.coordinates", [float("nan"), 0]),
        ("properties", []),
        ("properties.source", "unknown"),
        ("properties.layer", ""),
        ("properties.source_id", 123),
        ("properties.confidence", 1.1),
        ("properties.confidence", "0.5"),
        ("properties.match_type", False),
        ("properties.accuracy", 1),
        ("id", 123),
        ("crs", None),
    ],
)
def test_one_malformed_feature_fails_complete_response(path, value):
    bad = copy.deepcopy(feature())
    parts = path.split(".")
    target = bad
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    with pytest.raises(c.Stage12Error):
        project(body([feature(), bad, feature()]))


def test_optional_null_empty_and_unknown_preserved():
    f = feature()
    f["properties"].update(
        gid=None, name="", match_type=None, confidence=None, new_detail={"invented": 17}
    )
    projected = project(body([f]))
    row = projected.candidates[0]
    assert row["gid"] is None and row["name"] == "" and row["label"] == "Invented Café"
    assert row["confidence"] is None and row["match_type"] is None
    assert projected.unknown_fields == 1


@pytest.mark.parametrize(
    "patch",
    [
        {"errors": ["invented"]},
        {"warnings": ["invented"]},
        {"errors": None},
        {"warnings": ""},
        {"geocoding": None},
        {"geocoding": {"query": None}},
        {"geocoding": {"warnings": ["invented"]}},
        {"geocoding": {"timestamp": 1.5}},
        {"geocoding": {"version": None}},
        {"bbox": [0, 50, 1, 49]},
        {"crs": {}},
    ],
)
def test_envelope_failures(patch):
    obj = json.loads(body([]))
    obj.update(patch)
    with pytest.raises(c.Stage12Error):
        project(json.dumps(obj).encode())


def test_zero_and_antimeridian():
    obj = json.loads(body([]))
    obj["bbox"] = [170, -30, -170, 30]
    result = project(json.dumps(obj).encode())
    assert result.outcome == "SUCCESS_ZERO_CANDIDATES" and result.candidates == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"http_status": 204},
        {"http_status": 206},
        {"http_status": 500},
        {"content_type": "text/html"},
        {"content_type": "OTHER"},
        {"encoding": "gzip"},
        {"size": 1},
    ],
)
def test_http_contract(overrides):
    with pytest.raises(c.Stage12Error):
        project(body(), **overrides)


def test_bound_depth_body_and_expected_hash():
    with pytest.raises(c.Stage12Error, match="RESOURCE"):
        r.Parser(b"[]", max_body=1)
    with pytest.raises(c.Stage12Error, match="RESOURCE"):
        r.Parser(b'{"a":' + b"[" * 65 + b"0" + b"]" * 65 + b"}").parse()
    with pytest.raises(c.Stage12Error, match="HASH"):
        project(body(), expected_hash=c.sha(b"different"))


def test_secret_canary_not_in_exception():
    secret = b"invented-test-secret-never-real"
    with pytest.raises(c.Stage12Error) as caught:
        r.secret_guard(b"response " + secret, secret)
    assert str(caught.value) == "SECRET_ECHO_DETECTED"
    assert secret.decode() not in str(caught.value)


def test_exact_echo_adapter():
    raw = b'{"type":"FeatureCollection","features":[],"geocoding":{"query":{"size":3,"boundary":{"country":"DE"}}}}'
    expected = {"size": r.Number("3"), "boundary.country": "DE"}
    assert project(raw, expected_echo=expected).outcome == "SUCCESS_ZERO_CANDIDATES"
    with pytest.raises(c.Stage12Error):
        project(raw, expected_echo={"size": r.Number("5")})


def test_extractor_change_uses_same_raw_without_network(monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_a, **_kw: pytest.fail("offline projection used network"),
    )
    raw = body()
    old = c.projection_id(c.sha(raw), HASH, HASH, HASH, HASH)
    new = c.projection_id(
        c.sha(raw), HASH, HASH, c.sha(b"new extraction contract"), HASH
    )
    assert new != old
    assert project(raw) == project(raw)

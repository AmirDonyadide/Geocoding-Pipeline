"""Invented offline successor-policy tests; never read retained SAFE payloads."""

from __future__ import annotations

import copy
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing.stages import s12_response as v1
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_warning_policy as v2
from stage12_synthetic import HASH, body, core, feature

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline warning validation attempted network access")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def request(**changes):
    value = core(text="Berlin")
    value.update(changes)
    semantic = s11.semantic_id(s11.core_bytes(value))
    target, _ = c.materialize(value, semantic, c.policy(1), target_limit=4096)
    return v2.RequestFacts(
        c.canonical(value), semantic, 1, "GET", target, v2.HEADER_NAMES
    )


def review():
    return {
        "scope": v2.TEST_SCOPE,
        "deployment_content_sha256": c.sha(b"invented deployment test binding").hex(),
        "index_data_identity": c.sha(b"invented index test binding").hex(),
        "effective_behavior_id": c.sha(b"invented behavior test binding").hex(),
        "echo_adapter": {
            "text": "Berlin",
            "size": 1,
            "boundary.country": ["DEU"],
            "lang": {"name": "Invented test language", "via": "synthetic default"},
        },
        "effective_layers": ["locality", "street"],
        "sources": ["synthetic"],
        "review_approved": True,
        "authenticity_verified": True,
        "immutable_content_verified": True,
        "drift_verified": True,
    }


def warning_object():
    f = feature()
    f["properties"].update(layer="locality", gid="synthetic:locality:0001")
    return {
        "type": "FeatureCollection",
        "features": [f],
        "stage12_test_evidence": v2.TEST_MARKER,
        "geocoding": {
            "warnings": [v2.WARNING],
            "engine": {"name": v2.TEST_MARKER},
            "query": {
                **review()["echo_adapter"],
                "layers": review()["effective_layers"],
            },
        },
    }


def raw(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


def arguments(size=1):
    return {
        "size": size,
        "http_status": 200,
        "content_type": "application/json",
        "encoding": "identity",
        "layers": frozenset({"address", "street", "locality"}),
        "sources": frozenset({"synthetic"}),
        "expected_echo": {},
    }


def assess(obj=None, *, binding=None, facts=None, **overrides):
    args = arguments()
    args.update(overrides)
    return v2.validate_offline(
        raw(warning_object() if obj is None else obj),
        request=request() if facts is None else facts,
        synthetic_review=c.canonical(review() if binding is None else binding),
        **args,
    )


def test_v1_unchanged_rejection_v2_synthetic_conditional_assessment():
    payload = raw(warning_object())
    with pytest.raises(c.Stage12Error, match="^RESPONSE_CONTRACT_INVALID$"):
        v1.extract(payload, HASH, **arguments())
    a = assess()
    audit = json.loads(a.audit_json)
    assert audit["exception_applied"] is True
    assert audit["scientific_publication_authorized"] is False
    assert audit["exception_evidence_scope"] == v2.TEST_SCOPE
    assert audit["geocoding_warnings"] == [v2.WARNING]
    assert audit["effective_layers"] == ["locality", "street"]
    assert (
        audit["retrieval_limitation"]
        == "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED"
    )
    assert (
        not audit["harmlessness_established"]
        and not audit["live_determinism_established"]
    )
    assert (
        audit["hash_provenance"] == "OFFLINE_COMPUTATION_NOT_CAPTURE_TIME_ATTESTATION"
    )
    assert set(audit) == set(v2.audit_descriptor()["fields"])
    assert not hasattr(a, "candidates")
    assert not {"request_execution_id", "response_projection_id"} & set(audit)
    assert a.response_sha256 == c.sha(payload)
    assert a.validation_sha256 == v2.validation_sha256(c.canonical(review()))
    assert c.sha(a.validation_descriptor_json) == a.validation_sha256
    assert json.loads(a.validation_descriptor_json)["synthetic_review"] == review()
    assert audit["request_target_sha256"] == c.sha(b"GET\0" + v2.TARGET).hex()
    assert len(a.feature_slices) == 1


@pytest.mark.parametrize("with_empty_warnings", [False, True])
@pytest.mark.parametrize("count", [0, 1, 2])
def test_warning_free_retains_v1_validation_without_exception_bindings(
    count, with_empty_warnings
):
    obj = json.loads(body([feature()] * count))
    if with_empty_warnings:
        obj.update(warnings=[], errors=[], geocoding={"warnings": [], "errors": []})
    payload = raw(obj)
    ordinary = v1.extract(payload, HASH, **arguments(3))
    a = v2.validate_offline(payload, **arguments(3))
    # Ineligible request and unapproved exception bindings also do not gate ordinary responses.
    unapproved = review()
    unapproved["review_approved"] = False
    other = v2.validate_offline(
        payload,
        **arguments(3),
        request=request(text="Paris"),
        synthetic_review=c.canonical(unapproved),
    )
    assert (
        ordinary.feature_structures == a.feature_structures == other.feature_structures
    )
    assert json.loads(a.audit_json)["validation_outcome"] == ordinary.outcome
    assert json.loads(other.audit_json)["exception_applied"] is False
    assert a.feature_slices == tuple(
        (r["feature_byte_offset"], r["feature_byte_length"])
        for r in ordinary.candidates
    )


def test_order_and_duplicate_preservation_ordinary_path():
    first, second = feature(), feature()
    second["properties"]["source_id"] = "0002"
    payload = body([first, second, first])
    a = v2.validate_offline(payload, **arguments(3))
    original = v1.extract(payload, HASH, **arguments(3))
    assert a.feature_structures == original.feature_structures
    assert a.feature_structures[0] == a.feature_structures[2] != a.feature_structures[1]
    assert [r["rank"] for r in original.candidates] == [1, 2, 3]
    assert a.feature_slices[0] != a.feature_slices[2]


@pytest.mark.parametrize(
    "warning",
    [
        ["other"],
        [v2.WARNING, "other"],
        [v2.WARNING, v2.WARNING],
        [v2.WARNING.upper()],
        [v2.WARNING + " "],
        [v2.WARNING + " suffix"],
        [None],
        [False],
        [{}],
        None,
        "",
        v2.WARNING,
        {},
        1,
    ],
)
def test_unknown_additional_or_malformed_warnings_rejected(warning):
    obj = warning_object()
    obj["geocoding"]["warnings"] = warning
    with pytest.raises(c.Stage12Error, match="RESPONSE_CONTRACT_INVALID"):
        assess(obj)


@pytest.mark.parametrize("location", ["top_warning", "top_error", "geo_error"])
@pytest.mark.parametrize("value", [[v2.WARNING], None, "", {}, ["other"]])
def test_no_exception_for_errors_or_top_level_warnings(location, value):
    obj = warning_object()
    if location == "geo_error":
        obj["geocoding"]["errors"] = value
    else:
        obj["warnings" if location == "top_warning" else "errors"] = value
    with pytest.raises(c.Stage12Error):
        assess(obj)


@pytest.mark.parametrize(
    "change",
    [
        {"method": "POST"},
        {"result_limit": 3},
        {"result_limit": True},
        {"target": b"/v1/search?boundary.country=DE&size=3&text=Berlin"},
        {"target": b"/v1/search?size=1&boundary.country=DE&text=Berlin"},
        {"target": v2.TARGET + b"&layers=locality"},
        {"header_names": (*v2.HEADER_NAMES, "Accept-Language")},
        {"header_names": (*v2.HEADER_NAMES, "Cookie")},
        {"query_semantic_id": HASH},
        {"core_json": b"invalid"},
    ],
)
def test_request_guard_rejection(change):
    with pytest.raises(c.Stage12Error):
        assess(facts=replace(request(), **change))


@pytest.mark.parametrize(
    "text,country",
    [("Paris", "DE"), ("Berlin ", "DE"), ("berlin", "DE"), ("Berlin", "FR")],
)
def test_no_broader_query_or_country_eligibility(text, country):
    with pytest.raises(c.Stage12Error):
        assess(facts=request(text=text, boundary_country=country))


def test_structured_and_other_size_rejected():
    value = core(structured=True, text="Berlin")
    semantic = s11.semantic_id(s11.core_bytes(value))
    target, _ = c.materialize(value, semantic, c.policy(1), target_limit=4096)
    facts = v2.RequestFacts(
        c.canonical(value), semantic, 1, "GET", target, v2.HEADER_NAMES
    )
    with pytest.raises(c.Stage12Error):
        assess(facts=facts)
    for size in (3, 5, 10):
        with pytest.raises(c.Stage12Error):
            assess(size=size)


@pytest.mark.parametrize("field", sorted(v2.REVIEW_KEYS))
def test_each_missing_binding_fails_closed(field):
    binding = review()
    del binding[field]
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(binding=binding)


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope", "REAL_APPROVED"),
        ("review_approved", False),
        ("review_approved", 1),
        ("authenticity_verified", False),
        ("immutable_content_verified", False),
        ("drift_verified", False),
        ("deployment_content_sha256", "hostname"),
        ("index_data_identity", None),
        ("effective_behavior_id", "0" * 63),
        ("effective_layers", []),
        ("effective_layers", ["address"]),
        ("effective_layers", ["locality", "locality"]),
        ("effective_layers", [None]),
        ("effective_layers", ["new-layer"]),
        ("sources", ["whosonfirst"]),
        ("echo_adapter", {}),
    ],
)
def test_invalid_or_unapproved_binding_fails_closed(field, value):
    binding = review()
    binding[field] = value
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(binding=binding)


def test_no_real_activation_and_no_synthetic_authority_over_unmarked_response():
    obj = warning_object()
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        v2.validate_offline(raw(obj), **arguments(), request=request())
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        v2.validate_offline(
            raw(obj), **arguments(), synthetic_review=c.canonical(review())
        )
    # Both are invented negatives, not copies or modifications of retained SAFE evidence.
    del obj["stage12_test_evidence"]
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(obj)
    obj = warning_object()
    obj["geocoding"]["engine"] = {"name": "Pelias", "version": "1.0"}
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(obj)
    assert v2.descriptor()["exception"]["real_approved_bindings"] == []


def test_unknown_review_fields_and_invalid_review_encoding_fail_closed():
    binding = review()
    binding["invented_extra_authority"] = True
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(binding=binding)
    for invalid in (b"not json", b'{"scope":1,"scope":2}', b"{}", b"\xff"):
        with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
            v2.validate_offline(
                raw(warning_object()),
                **arguments(),
                request=request(),
                synthetic_review=invalid,
            )


@pytest.mark.parametrize(
    "key,value",
    [
        ("text", "Paris"),
        ("size", True),
        ("size", 3),
        ("boundary.country", []),
        ("boundary.country", "DEU"),
        ("boundary.country", [None]),
        ("lang", {}),
        ("lang", None),
        ("layers", ["locality"]),
    ],
)
def test_invalid_echo_adapter_never_grants_exception(key, value):
    binding = review()
    binding["echo_adapter"][key] = value
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(binding=binding)


@pytest.mark.parametrize("key", ["text", "size", "boundary.country", "lang"])
def test_missing_echo_adapter_requirement_fails_closed(key):
    binding = review()
    del binding["echo_adapter"][key]
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        assess(binding=binding)


@pytest.mark.parametrize("key", ["text", "size", "boundary.country", "lang", "layers"])
@pytest.mark.parametrize("operation", ["missing", "inconsistent"])
def test_metadata_required_and_consistent(key, operation):
    obj = warning_object()
    if operation == "missing":
        del obj["geocoding"]["query"][key]
    else:
        obj["geocoding"]["query"][key] = "inconsistent"
    with pytest.raises(c.Stage12Error, match="RESPONSE_CONTRACT_INVALID"):
        assess(obj)


def test_parsed_city_never_substitutes_for_bindings_or_claims_no_address_evidence():
    obj = warning_object()
    obj["geocoding"]["query"]["parsed_text"] = {"city": "berlin", "house_number": "123"}
    a = assess(obj)
    assert json.loads(a.audit_json)["retrieval_limitation"] is not None
    with pytest.raises(c.Stage12Error, match="IDENTITY_UNVERIFIABLE"):
        v2.validate_offline(raw(obj), **arguments(), request=request())


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
        ("geometry.coordinates", [float("inf"), 0]),
        ("properties", []),
        ("properties.source", "other"),
        ("properties.layer", "address"),
        ("properties.layer", ""),
        ("properties.source_id", 123),
        ("properties.confidence", 1.1),
        ("properties.confidence", "0.1"),
        ("properties.match_type", False),
        ("properties.accuracy", 1),
        ("id", 123),
        ("crs", None),
        ("geometry.crs", None),
        ("bbox", [0, 20, 1, 10]),
    ],
)
def test_downstream_candidate_checks_still_fail_whole_response(path, value):
    obj = warning_object()
    target = obj["features"][0]
    parts = path.split(".")
    for component in parts[:-1]:
        target = target[component]
    target[parts[-1]] = value
    with pytest.raises(c.Stage12Error):
        assess(obj)


@pytest.mark.parametrize(
    "overrides",
    [
        {"http_status": 204},
        {"http_status": 500},
        {"content_type": "text/html"},
        {"encoding": "gzip"},
        {"expected_hash": HASH},
    ],
)
def test_http_and_raw_hash_checks(overrides):
    with pytest.raises(c.Stage12Error):
        assess(**overrides)


def test_count_zero_overflow_and_invalid_later_feature_never_filtered():
    obj = warning_object()
    obj["features"] = []
    assert (
        json.loads(assess(obj).audit_json)["validation_outcome"]
        == "SUCCESS_ZERO_CANDIDATES"
    )
    obj = warning_object()
    obj["features"] *= 2
    with pytest.raises(c.Stage12Error):
        assess(obj)
    bad = feature()
    bad["geometry"] = None
    with pytest.raises(c.Stage12Error):
        v2.validate_offline(body([feature(), bad, feature()]), **arguments(3))


def test_rejected_response_emits_no_limitation_audit(monkeypatch):
    emitted = []
    canonical = c.canonical

    def observe(value):
        if isinstance(value, dict) and value.get("assessment_scope") == "OFFLINE_ONLY":
            emitted.append(value)
        return canonical(value)

    monkeypatch.setattr(c, "canonical", observe)
    obj = warning_object()
    obj["features"][0]["geometry"] = None
    with pytest.raises(c.Stage12Error):
        assess(obj)
    assert emitted == []


@pytest.mark.parametrize(
    "patch",
    [
        {"type": "Other"},
        {"features": None},
        {"features": {}},
        {"geocoding": None},
        {"geocoding": {"query": None}},
        {"geocoding": {"timestamp": 1.5}},
        {"geocoding": {"version": None}},
        {"geocoding": {"attribution": 123}},
        {"geocoding": {"crs": None}},
        {"bbox": [0, 50, 1, 49]},
        {"crs": {}},
        {"warnings": None},
        {"errors": ""},
    ],
)
def test_ordinary_envelope_failures_match_v1(patch):
    obj = json.loads(body([]))
    obj.update(patch)
    payload = raw(obj)
    with pytest.raises(c.Stage12Error):
        v1.extract(payload, HASH, **arguments(3))
    with pytest.raises(c.Stage12Error):
        v2.validate_offline(payload, **arguments(3))


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"[]",
        b"null",
        b"\xef\xbb\xbf{}",
        b'{"features":[],"features":[]}',
        b'{"x":NaN}',
        b'{"x":1e9999}',
        b'{"x":"\\ud800"}',
        b'{"x":"\\q"}',
        b'{"x":01}',
        b'{"type":"FeatureCollection","features":[]} trailing',
    ],
)
def test_strict_json_validation_matches_v1(payload):
    with pytest.raises(c.Stage12Error):
        v1.extract(payload, HASH, **arguments(3))
    with pytest.raises(c.Stage12Error):
        v2.validate_offline(payload, **arguments(3))


def test_ordinary_echo_and_optional_fields_match_v1():
    f = feature()
    f["properties"].update(
        name="",
        gid=None,
        confidence=None,
        match_type=None,
        unknown_detail={"invented": 1},
    )
    obj = json.loads(body([f]))
    obj["geocoding"] = {"query": {"size": 3}}
    args = arguments(3)
    args["expected_echo"] = {"size": v1.Number("3")}
    a = v2.validate_offline(raw(obj), **args)
    assert a.feature_structures == v1.extract(raw(obj), HASH, **args).feature_structures
    args["expected_echo"] = {"size": v1.Number("1")}
    with pytest.raises(c.Stage12Error):
        v2.validate_offline(raw(obj), **args)


def test_exception_candidate_metadata_remains_descriptive():
    obj = warning_object()
    a = assess(obj)
    fragment = raw(obj)[a.feature_slices[0][0] : sum(a.feature_slices[0])]
    properties = json.loads(fragment)["properties"]
    assert properties["confidence"] == 0.1
    assert properties["match_type"] == "exact" and properties["accuracy"] == "point"
    assert json.loads(a.audit_json)["harmlessness_established"] is False


def test_exact_raw_bytes_round_trip_and_no_side_effects():
    obj = warning_object()
    before = copy.deepcopy(obj)
    payload = raw(obj)
    first = assess(obj)
    for level in (1, 9):
        restored = v1.decompress(
            v1.compress(payload, level=level),
            length=len(payload),
            expected_hash=c.sha(payload),
        )
        replay = v2.validate_offline(
            restored,
            **arguments(),
            request=request(),
            synthetic_review=c.canonical(review()),
        )
        assert replay == first
    assert obj == before
    altered = json.dumps(obj, indent=2, sort_keys=True).encode()
    second = v2.validate_offline(
        altered,
        **arguments(),
        request=request(),
        synthetic_review=c.canonical(review()),
    )
    assert first.feature_structures == second.feature_structures
    assert first.response_sha256 != second.response_sha256
    assert json.loads(second.audit_json)["geocoding_warnings"] == [v2.WARNING]


def test_descriptor_rule_and_binding_changes_participate_in_identity():
    base = v2.descriptor()
    for field in (
        "geocoding_warnings",
        "request",
        "metadata",
        "required_binding_fields",
    ):
        changed = copy.deepcopy(base)
        changed["exception"][field] = "hypothetical reviewed change"
        assert c.sha(c.canonical(changed)) != v2.validation_sha256()
    binding = review()
    changed = copy.deepcopy(binding)
    changed["effective_layers"].reverse()
    assert v2.validation_sha256(c.canonical(binding)) != v2.validation_sha256(
        c.canonical(changed)
    )
    obj = warning_object()
    obj["geocoding"]["query"]["layers"].reverse()
    assert assess(obj, binding=changed).validation_sha256 == v2.validation_sha256(
        c.canonical(changed)
    )
    assert v2.validation_sha256() != bytes.fromhex(v2.BASE_SHA256)
    # Synthetic framing demonstration only; no real execution/projection is constructed.
    old = c.projection_id(HASH, HASH, bytes.fromhex(v2.BASE_SHA256), HASH, HASH)
    new = c.projection_id(HASH, HASH, v2.validation_sha256(), HASH, HASH)
    assert old != new
    facts = request()
    assess()
    assert facts == request()
    assert (
        c.policy(1)["retrieval_policy_id"].hex()
        == "8df725a6e6baf50d5e1eeb1f4979b5a33eb4b4b6217c8c6a6d488e4e3ef1586c"
    )


def test_versioned_assets_and_v1_binding():
    assets = ROOT / "docs/scientific_assets"
    assert (
        c.sha((assets / "stage12_response_validation_v1.json").read_bytes()).hex()
        == v2.BASE_SHA256
    )
    assert (
        c.sha((assets / "stage12_request_materialization_v1.json").read_bytes()).hex()
        == v2.MATERIALIZATION_SHA256
    )
    assert (assets / f"{v2.VERSION}.json").read_bytes() == c.canonical(v2.descriptor())
    assert (assets / f"{v2.AUDIT_VERSION}.json").read_bytes() == c.canonical(
        v2.audit_descriptor()
    )
    assert (
        v2.descriptor()["limitation_audit_contract_sha256"]
        == c.sha(c.canonical(v2.audit_descriptor())).hex()
    )


def test_existing_runtime_has_no_successor_import():
    source = ROOT / "src/safe_geocoding_pipeline/preprocessing"
    for file in source.rglob("*.py"):
        if file.name != "s12_warning_policy.py":
            assert "s12_warning_policy" not in file.read_text()

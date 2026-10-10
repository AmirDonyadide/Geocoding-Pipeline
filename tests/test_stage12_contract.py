from __future__ import annotations

import copy
import hashlib
import struct
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing.stages import s12_deployment as deployment
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from stage12_synthetic import HASH, core, cores


def independent_e(values):
    output = struct.pack(">Q", len(values))
    for v in values:
        if v is None:
            output += b"\0"
        elif type(v) is str:
            raw = v.encode("utf-8")
            output += b"\1" + struct.pack(">Q", len(raw)) + raw
        elif type(v) is bytes:
            output += b"\2" + struct.pack(">Q", len(v)) + v
        elif type(v) is int:
            output += b"\3" + struct.pack(">Q", v)
        else:
            output += b"\5" + independent_e(v)
    return output


@pytest.mark.parametrize("size", [1, 3, 5, 10, 11, 20, 2**64 - 1])
def test_policy_independent_byte_oracle(size):
    fields = [
        ("policy_version", "stage12_retrieval_policy_v1"),
        ("result_limit", size),
        ("retention", "ALL_RETURNED_IN_ORDER"),
        ("result_options", []),
    ]
    expected = hashlib.sha256(
        b"SAFE:stage12-retrieval-policy:v1\0" + independent_e(fields)
    ).digest()
    assert c.policy(size)["retrieval_policy_id"] == expected
    assert c.policy(size)["retrieval_policy_id"] != c.policy(2)["retrieval_policy_id"]


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, "3", None, 2**64])
def test_invalid_policy(value):
    with pytest.raises(c.Stage12Error):
        c.policy(value)


@pytest.mark.parametrize("key", c.EXECUTION_FIELDS[1:])
def test_each_scientific_binding_changes_execution(key):
    binding = {
        k: c.IDENTITY if k == "identity_version" else HASH for k in c.EXECUTION_FIELDS
    }
    original = c.execution_id(binding)
    binding[key] = c.sha(b"different")
    assert original != c.execution_id(binding)


@pytest.mark.parametrize(
    "key",
    [
        "git_sha",
        "reporting_sha",
        "extraction_schema",
        "attempt",
        "concurrency",
        "job_id",
        "path",
        "timestamp",
        "secret",
        "campaign_id",
    ],
)
def test_operational_fields_cannot_enter_network_preimage(key):
    binding = {
        k: c.IDENTITY if k == "identity_version" else HASH for k in c.EXECUTION_FIELDS
    }
    expected = c.execution_id(binding)
    metadata = {key: "changed"}
    assert c.execution_id(binding) == expected
    with pytest.raises(c.Stage12Error):
        c.execution_id({**binding, **metadata})


@pytest.mark.parametrize("index", [0, 1, 2])
def test_deployment_content_changes_execution(index):
    values = list(cores())
    original = deployment.content_identity(*values)
    values[index] = copy.deepcopy(values[index])
    key = next(k for k in values[index] if k != "schema_version")
    values[index][key] = {"different": "content"}
    changed = deployment.content_identity(*values)
    assert (
        original.pelias_deployment_fingerprint != changed.pelias_deployment_fingerprint
    )
    assert c.execution_id(
        original.execution_binding(HASH, HASH, HASH)
    ) != c.execution_id(changed.execution_binding(HASH, HASH, HASH))


def test_authenticity_is_separate_and_failure_blocks():
    values = cores()
    first = deployment.content_identity(*values)
    a = deployment.verify_authenticity(
        first.deployment_core, b"signature-a", verifier=lambda *_: True
    )
    b = deployment.verify_authenticity(
        first.deployment_core, b"signature-b", verifier=lambda *_: True
    )
    assert a != b
    assert deployment.content_identity(*values) == first
    with pytest.raises(c.Stage12Error, match="AUTHENTICITY"):
        deployment.verify_authenticity(
            first.deployment_core, b"wrong", verifier=lambda *_: False
        )


@pytest.mark.parametrize("structured", [False, True])
def test_exact_serialization(structured):
    value = core(structured=structured)
    semantic = s11.semantic_id(s11.core_bytes(value))
    target, h = c.materialize(value, semantic, c.policy(3), target_limit=10000)
    expected = (
        b"Invented%20Caf%C3%A9%20%2B%207%25%0A%D8%AE%DB%8C%D8%A7%D8%A8%D8%A7%D9%86"
    )
    assert target == (
        b"/v1/search/structured?address="
        + expected
        + b"&boundary.country=DE&postalcode=00123&size=3"
        if structured
        else b"/v1/search?boundary.country=DE&size=3&text=" + expected
    )
    assert h == hashlib.sha256(b"GET\0" + target).digest()
    assert s11.semantic_id(s11.core_bytes(value)) == semantic
    for forbidden in (b"layers=", b"sources=", b"lang=", b"region=", b"&country="):
        assert forbidden not in target
    with pytest.raises(c.Stage12Error, match="TOO_LARGE"):
        c.materialize(value, semantic, c.policy(3), target_limit=2)


@pytest.mark.parametrize(
    "field", ["region", "country", "language_policy", "layers_policy", "sources_policy"]
)
def test_no_new_semantics(field):
    value = core(structured=True)
    value[field] = "invented"
    with pytest.raises(c.Stage12Error):
        c.materialize(value, HASH, c.policy(3), target_limit=10000)


def test_projection_contract_change_separate():
    original = c.projection_id(HASH, HASH, HASH, HASH, HASH)
    assert c.projection_id(HASH, HASH, HASH, c.sha(b"extractor-v2"), HASH) != original
    assert c.projection_id(HASH, HASH, HASH, HASH, c.sha(b"schema-v2")) != original


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_float_framing_rejects_nonfinite(value):
    with pytest.raises(c.Stage12Error):
        c.framed([value])


def test_named_rejects_duplicate_and_identity_float():
    with pytest.raises(c.Stage12Error):
        c.named("SAFE:stage12-test:v1", [("a", 1), ("a", 2)])
    with pytest.raises(c.Stage12Error):
        c.named("SAFE:stage12-test:v1", [("a", 1.2)])
    assert c.framed([-0.0]) != c.framed([0.0])


def test_frozen_design_hashes():
    root = Path(__file__).resolve().parents[1]
    for name, expected in c.DESIGN_HASHES.items():
        assert (
            hashlib.sha256((root / "docs/stages" / name).read_bytes()).hexdigest()
            == expected
        )

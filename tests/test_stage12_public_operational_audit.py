"""Real temporary-file capture transactions with invented payloads only."""

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as old
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from stage12_synthetic import body, feature
from test_stage12_public_operations_v2 import H, KEY, FakeClock, inputs, offline  # noqa: F401


def capture(raw=None, status=200):
    from safe_geocoding_pipeline.preprocessing.stages import s12_operations as v1

    outcome, reason = v1.classify(status)
    return t.Capture(
        outcome,
        reason,
        status,
        "application/json",
        "identity",
        None,
        raw,
        len(raw) if raw is not None else 0,
        2,
    )


class Control:
    def target(self, recipe):
        return b"/synthetic-control-only"

    def validate(self, recipe, raw):
        obj = io.metadata(raw)
        c.require(obj == {"synthetic_index": "test"}, "RESPONSE_CONTRACT_INVALID")
        return c.canonical(
            {"scope": "SYNTHETIC_TEST_ONLY", "observed": c.sha(raw).hex()}
        )


def recipe(purpose="HEALTH_CHECK"):
    return {
        "recipe_id": 1,
        "recipe_sha256": H,
        "implementation_contract_sha256": H,
        "transport_profile_sha256": H,
        "purpose": purpose,
        "max_http_attempts_per_invocation": 5,
        "max_duration_ms": 10000,
    }


def control_begin():
    return {
        "schema_version": o.CONTROL_BEGIN,
        "campaign_start_sha256": H,
        "profile_sha256": H,
        "plan_sha256": H,
        "segment_id": 1,
        "work_id": 1,
        "attempt": 1,
        "recipe_sha256": H,
        "request_target_sha256": H,
        "started_utc": FakeClock().utc(),
    }


@pytest.mark.parametrize(
    "raw,expected",
    [
        (body([]), c.SUCCESS[1]),
        (body([feature(), feature()]), "CONTRACT_FAILURE"),
        (b'{"broken":', "CONTRACT_FAILURE"),
    ],
)
def test_T05_T07_DATA_retains_safe_bytes_and_v1_validation(tmp_path, raw, expected):
    profile, plan, start, rows, runtime = inputs()
    root = tmp_path / "data"
    a.begin_data(root, profile, plan, start, rows[0], 1, runtime)
    record = a.transport_record(rows[0], 1, capture(raw), FakeClock().utc())
    terminal, receipt = a.finish_data(
        root, rows[0], record, raw, key=KEY, validator=cli.public_shapes
    )
    name = old.name_for(1, 1)
    assert terminal["outcome"] == expected
    assert terminal["response_sha256"] == c.sha(raw).hex()
    assert io.read(root / (name + "_SEALED")) == b""
    assert receipt == c.sha(io.read(root / (name + "_receipt.json"))).hex()
    assert (
        old.reopen(root, name, validator=cli.public_shapes, context=a.DataContext())
        == terminal
    )
    with pytest.raises((c.Stage12Error, KeyError)):
        old.reopen(root, name, validator=cli.public_shapes)


def test_T07_secret_canary_neither_payload_nor_hash_persists(tmp_path):
    profile, plan, start, rows, runtime = inputs()
    root = tmp_path / "secret"
    a.begin_data(root, profile, plan, start, rows[0], 1, runtime)
    raw = b'{"secret":"' + KEY + b'"}'
    record = a.transport_record(rows[0], 1, capture(raw), FakeClock().utc())
    terminal, _ = a.finish_data(
        root, rows[0], record, raw, key=KEY, validator=cli.public_shapes
    )
    assert terminal["reason_code"] == "SECRET_ECHO_DETECTED"
    assert terminal["response_sha256"] is None
    assert not list(root.glob("*.zst"))
    for path in root.iterdir():
        assert KEY not in io.read(path)
        assert c.sha(raw).hex().encode() not in io.read(path)


@pytest.mark.parametrize(
    "purpose,raw,outcome",
    [
        ("HEALTH_CHECK", c.canonical({"synthetic_index": "test"}), "CONTROL_SUCCESS"),
        ("HEALTH_CHECK", b"{}\n", "CONTRACT_FAILURE"),
        ("IDENTITY_REFRESH", b"{}\n", "DEPLOYMENT_IDENTITY_FAILURE"),
    ],
)
def test_T16_distinct_control_outcomes_and_raw_transport(
    tmp_path, purpose, raw, outcome
):
    root = tmp_path / "control"
    a.begin_control(root, control_begin())
    record = a.transport_record({"work_id": 1}, 1, capture(raw), FakeClock().utc())
    finish, fingerprint = a.finish_control(
        root, record, raw, recipe(purpose), Control(), key=KEY
    )
    assert finish["outcome"] == outcome
    assert "candidate_count" not in finish
    assert (
        io.metadata(io.read(root / "transport.json"))["outcome"]
        == "VALIDATION_REQUIRED"
    )
    assert a.reopen_control(root, Control(), key=KEY) == finish
    assert fingerprint == c.sha(io.read(root / "inventory.json")).hex()
    with pytest.raises(c.Stage12Error):
        o.validate_type({"kind": "DATA", "value": "CONTROL_SUCCESS"}, "FinalOutcome")
    with pytest.raises(c.Stage12Error):
        o.validate_type(
            {"kind": "SERVICE_CONTROL", "value": c.SUCCESS[1]}, "FinalOutcome"
        )


def test_T16_control_identity_failure_overrides_retry_but_keeps_raw_classification(
    tmp_path,
):
    root = tmp_path / "identity"
    a.begin_control(root, control_begin())
    record = a.transport_record(
        {"work_id": 1}, 1, capture(None, 503), FakeClock().utc()
    )
    finish, _ = a.finish_control(
        root, record, None, recipe("IDENTITY_REFRESH"), Control(), key=KEY
    )
    assert finish["outcome"] == "DEPLOYMENT_IDENTITY_FAILURE"
    assert (
        io.metadata(io.read(root / "transport.json"))["outcome"]
        == "TECHNICAL_FAILURE_RETRYABLE"
    )


def test_T07_primary_failure_survives_control_audit_failure(monkeypatch, tmp_path):
    root = tmp_path / "failed"
    a.begin_control(root, control_begin())
    record = a.transport_record(
        {"work_id": 1}, 1, capture(None, 503), FakeClock().utc()
    )
    original = io.write

    def fail(path, raw):
        if path.name == "finish.json":
            raise OSError("synthetic disk fault")
        original(path, raw)

    monkeypatch.setattr(io, "write", fail)
    with pytest.raises(old.AuditWriteError, match="SERVER_TRANSIENT"):
        a.finish_control(root, record, None, recipe(), Control(), key=KEY)
    assert not (root / "_CONTROL_SEALED").exists()

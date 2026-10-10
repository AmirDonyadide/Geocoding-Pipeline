from __future__ import annotations

from dataclasses import replace

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_deployment as d
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from stage12_synthetic import HASH, NOW, cores


@pytest.mark.parametrize(
    "status,state,reason",
    [
        (408, "TECHNICAL_FAILURE_RETRYABLE", "TIMEOUT"),
        (429, "TECHNICAL_FAILURE_RETRYABLE", "RATE_LIMITED"),
        (500, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT"),
        (502, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT"),
        (503, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT"),
        (504, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT"),
        (501, "CONTRACT_FAILURE", "UNSUPPORTED_PROTOCOL"),
        (505, "CONTRACT_FAILURE", "UNSUPPORTED_PROTOCOL"),
        (401, "TECHNICAL_FAILURE_FINAL", "AUTHENTICATION_FAILED"),
        (403, "TECHNICAL_FAILURE_FINAL", "AUTHORIZATION_FAILED"),
        (404, "CONTRACT_FAILURE", "HTTP_REQUEST_REJECTED"),
        (302, "CONTRACT_FAILURE", "REDIRECT_FORBIDDEN"),
        (204, "CONTRACT_FAILURE", "RESPONSE_CONTRACT_INVALID"),
    ],
)
def test_status_taxonomy(status, state, reason):
    assert o.classify(status) == (state, reason)


@pytest.mark.parametrize("ordinal,base", [(2, 2000), (3, 4000), (4, 8000), (5, 16000)])
def test_retry_bounded_deterministic(ordinal, base):
    delay = o.retry_delay(HASH, ordinal, None, o.Operations())
    assert base <= delay <= base + 999
    assert delay == o.retry_delay(HASH, ordinal, None, o.Operations())
    assert o.retry_delay(HASH, ordinal, 300, o.Operations()) == 300000
    with pytest.raises(c.Stage12Error, match="OWNER_RECOVERY"):
        o.retry_delay(HASH, ordinal, 301, o.Operations())


@pytest.mark.parametrize(
    "value,expected",
    [(None, None), ("malformed", None), ("-1", None), ("0", 0), ("30", 30)],
)
def test_retry_after(value, expected):
    assert o.retry_after(value, None, NOW) == expected


def test_retry_http_date_uses_server_date():
    assert (
        o.retry_after(
            "Thu, 01 Jan 2026 00:01:00 GMT", "Thu, 01 Jan 2026 00:00:00 GMT", NOW
        )
        == 60
    )
    assert o.retry_after("Thu, 01 Jan 2026 00:00:00 GMT", None, NOW) == 0


def test_global_no_burst_connection_and_retry_budget():
    a = o.Admission(o.Operations())
    a.admit(0)
    with pytest.raises(c.Stage12Error):
        a.admit(999)
    a.admit(1000)
    with pytest.raises(c.Stage12Error):
        a.admit(2000)
    a.finish(2000, c.SUCCESS[1], 2000)
    a.admit(2000)
    assert a.active == 2
    assert o.remaining_attempts([1, 2, 3, 4, 5], o.Operations()) == 0
    for bad in ([2], [1, 3], [1, 1], [1, 2, 3, 4, 5, 6]):
        with pytest.raises(c.Stage12Error):
            o.remaining_attempts(bad, o.Operations())


def test_breaker_stops_without_half_open():
    a = o.Admission(o.Operations())
    for t in (0, 1000, 2000):
        a.admit(t)
        a.finish(t + 1, "TECHNICAL_FAILURE_RETRYABLE", 1)
    assert a.open_reason == "TECHNICAL_ERROR_PRESSURE"
    with pytest.raises(c.Stage12Error):
        a.admit(1000000)


def test_overload_cooldown_and_breaker():
    a = o.Admission(o.Operations())
    for t in (0, 30000):
        a.admit(t)
        a.finish(t, "TECHNICAL_FAILURE_RETRYABLE", 0, status=503)
    assert a.open_reason == "OVERLOAD_PRESSURE" and a.next_admission_ms == 60000


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_attempts", 6),
        ("connections", 5),
        ("requests_per_second", 3),
        ("connections", True),
    ],
)
def test_hard_limits(field, value):
    with pytest.raises(c.Stage12Error):
        replace(o.Operations(), **{field: value}).validate()


def evidence(deploy, **changes):
    values = dict(
        deployment_fingerprint=deploy.pelias_deployment_fingerprint,
        receipt_sha256=HASH,
        authenticated=True,
        immutable_content_verified=True,
        maintenance_controls_verified=True,
        route_uniformity_verified=True,
        no_secret_echo_verified=True,
        logging_controls_verified=True,
        continuity_verified=True,
        acquired_monotonic_ms=0,
        valid_until_monotonic_ms=1000000,
        completed_responses=0,
        interval_closed=False,
        generation_identity=HASH,
    )
    values.update(changes)
    return d.Evidence(**values)


@pytest.mark.parametrize(
    "field",
    [
        "authenticated",
        "immutable_content_verified",
        "maintenance_controls_verified",
        "route_uniformity_verified",
        "no_secret_echo_verified",
        "logging_controls_verified",
        "continuity_verified",
    ],
)
def test_missing_required_evidence_blocks(field):
    deploy = d.content_identity(*cores())
    guard = d.DriftGuard(deploy, "CONTROLLED_CAMPAIGN")
    with pytest.raises(c.Stage12Error):
        guard.accept(evidence(deploy, **{field: False}), 0)
    assert guard.quarantined


def test_stale_verification_and_drift_no_salvage():
    deploy = d.content_identity(*cores())
    guard = d.DriftGuard(deploy, "CONTROLLED_CAMPAIGN")
    guard.accept(evidence(deploy), 0)
    assert guard.before_dispatch(59999) == HASH
    with pytest.raises(c.Stage12Error, match="STALE"):
        guard.before_dispatch(60000)
    with pytest.raises(c.Stage12Error):
        guard.accept(evidence(deploy, deployment_fingerprint=c.sha(b"drift")), 0)
    with pytest.raises(c.Stage12Error):
        guard.accept(evidence(deploy), 0)


def test_per_response_generation_and_periodic_count():
    deploy = d.content_identity(*cores())
    guard = d.DriftGuard(deploy, "PER_RESPONSE_GENERATION")
    guard.accept(evidence(deploy), 0)
    for _ in range(100):
        guard.response(1, HASH)
    with pytest.raises(c.Stage12Error, match="STALE"):
        guard.before_dispatch(1)
    guard.accept(evidence(deploy, completed_responses=100), 1)
    with pytest.raises(c.Stage12Error):
        guard.response(2, c.sha(b"wrong generation"))


@pytest.mark.parametrize(
    "date,date_state,clock,seconds",
    [
        ("Thu, 01 Jan 2026 00:00:00 GMT", "VALID", "RESPONSE_DATE", 60),
        (None, "MISSING", "CLIENT_RECEIPT_UTC", 50),
        ("invalid-date", "UNUSABLE", "CLIENT_RECEIPT_UTC", 50),
        (
            "Thu, 01 Jan 2026 00:00:00 GMT, garbage",
            "UNUSABLE",
            "CLIENT_RECEIPT_UTC",
            50,
        ),
        ("Thu, 01 Jan 2026 00:00:00", "UNUSABLE", "CLIENT_RECEIPT_UTC", 50),
    ],
)
def test_owner_http_date_clock_clarification(date, date_state, clock, seconds):
    from datetime import datetime, timezone

    receipt = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc)
    decision = o.retry_after_decision("Thu, 01 Jan 2026 00:01:00 GMT", date, receipt)
    assert decision.seconds == seconds
    assert decision.reference_clock == clock
    assert decision.response_date == date_state
    assert decision.receipt_utc == "2026-01-01T00:00:10.000000+00:00"
    assert date is None or date not in str(decision.audit())
    assert o.retry_delay(HASH, 2, decision.seconds, o.Operations()) == seconds * 1000


@pytest.mark.parametrize(
    "header,seconds,kind",
    [
        ("30", 30, "DELTA_SECONDS"),
        ("0", 0, "DELTA_SECONDS"),
        ("Thu, 01 Jan 2026 00:00:00 GMT", 0, "HTTP_DATE"),
        ("wrong-date", None, "MALFORMED"),
        ("Thu, 01 Jan 2026 00:00:00 GMT junk", None, "MALFORMED"),
        (str(2**64), None, "MALFORMED"),
    ],
)
def test_retry_delay_and_audit_edges(header, seconds, kind):
    decision = o.retry_after_decision(header, "unusable", NOW)
    assert (decision.seconds, decision.kind) == (seconds, kind)
    delay = o.retry_delay(HASH, 2, decision.seconds, o.Operations())
    base = o.retry_delay(HASH, 2, None, o.Operations())
    assert delay == max(base, (seconds or 0) * 1000)


def test_retry_timestamps_are_outside_scientific_identity(tmp_path):
    from datetime import timedelta
    from stage12_synthetic import setup

    binding, _target = setup(tmp_path)
    scientific = {
        k: c.IDENTITY if k == "identity_version" else bytes.fromhex(binding[k])
        for k in c.EXECUTION_FIELDS
    }
    identity = c.execution_id(scientific)
    a = o.retry_after_decision("Thu, 01 Jan 2026 00:01:00 GMT", None, NOW)
    b = o.retry_after_decision(
        "Thu, 01 Jan 2026 00:01:00 GMT", "bad", NOW + timedelta(seconds=5)
    )
    assert a.audit() != b.audit()
    assert c.execution_id(scientific) == identity
    with pytest.raises(c.Stage12Error):
        c.execution_id({**scientific, "receipt_utc": a.receipt_utc})

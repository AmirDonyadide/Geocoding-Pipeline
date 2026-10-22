"""Prospective public audit only: injected transport, invented bytes, no sockets."""

from __future__ import annotations

import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from stage12_synthetic import body, feature
from test_stage12_probe import harness, successful

NAME = "call_0001_attempt_1"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("public audit tests must not use sockets")

    for name in ("create_connection", "getaddrinfo"):
        monkeypatch.setattr(socket, name, forbidden)
    for name in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, forbidden)
    monkeypatch.delenv("SAFE_PELIAS_API_KEY", raising=False)
    monkeypatch.delenv("SAFE_PELIAS_API_KEY_FILE", raising=False)


def setup(monkeypatch, tmp_path, dispatch, calls=1):
    config = harness(monkeypatch, tmp_path, dispatch)
    original = cli.probe.planned_calls
    monkeypatch.setattr(cli.probe, "planned_calls", lambda plan: original(plan)[:calls])
    return config, Path(config["output_directory"])


def run(config):
    return cli.run(config, "1" * 40, Path("."))


def capture(raw):
    return replace(successful(), payload=raw, received_body_bytes=len(raw))


def stored(root, suffix):
    return io.metadata(io.read(root / (NAME + suffix)))


@pytest.mark.parametrize("count", [0, 1])
def test_complete_public_capture_has_linked_exact_hash_and_v1_binding(
    monkeypatch, tmp_path, count
):
    raw = body([feature()] * count)
    cfg, root = setup(monkeypatch, tmp_path, lambda *_: capture(raw))
    report = run(cfg)
    assert report["status"] == "COMPLETED"
    assert report["public_audit_attempts_completed"] == 1
    assert report["public_audit_attempts_incomplete"] == 0
    terminal = audit.reopen(root, NAME, validator=cli.public_shapes)
    assert terminal["outcome"] == c.SUCCESS[0 if count else 1]
    assert terminal["candidate_count"] == count
    assert terminal["validation_performed"] is True
    assert terminal["response_sha256"] == c.sha(raw).hex()
    descriptor = c.canonical(assets.objects()[response.VALIDATION])
    assert io.read(root / "response_validation.json") == descriptor
    assert terminal["response_validation_contract_sha256"] == c.sha(descriptor).hex()
    assert terminal["validation_version"] == "stage12_response_validation_v1"
    assert terminal["validation_scope"] == audit.VALIDATION_SCOPE
    assert (
        terminal["begin_sha256"] == c.sha(io.read(root / (NAME + "_begin.json"))).hex()
    )
    assert (
        terminal["transport_receipt_sha256"]
        == c.sha(io.read(root / (NAME + "_finish.json"))).hex()
    )
    assert stored(root, "_finish.json")["outcome"] == "VALIDATION_REQUIRED"
    retained = stored(root, "_capture.json")["capture"]
    assert retained["payload_complete"] and retained["raw_path"] == NAME + ".zst"
    frame = io.read(root / retained["raw_path"])
    assert response.decompress(frame, length=len(raw), expected_hash=c.sha(raw)) == raw
    inventory = stored(root, "_receipt.json")["inventory"]
    assert (
        next(row for row in inventory if row["path"] == NAME + ".zst")["sha256"]
        == c.sha(frame).hex()
    )
    assert c.sha(frame) != c.sha(raw)
    assert {
        "request_execution_id",
        "attempt_id",
        "response_projection_id",
        "campaign_id",
    }.isdisjoint(terminal)


def warning():
    obj = json.loads(body([feature()]))
    obj["geocoding"] = {
        "warnings": ["performance optimization: excluding 'address' layer"]
    }
    return json.dumps(obj).encode()


@pytest.mark.parametrize(
    "raw",
    [warning(), b'{"type":', body([{"type": "Feature"}]), body([feature(), feature()])],
)
def test_v1_response_failures_keep_raw_hash_and_failure_inventory(
    monkeypatch, tmp_path, raw
):
    calls = []
    cfg, root = setup(
        monkeypatch, tmp_path, lambda *_: calls.append(1) or capture(raw), calls=2
    )
    report = run(cfg)
    assert report["status"] == "FAILED"
    assert report["failure_code"] == "RESPONSE_CONTRACT_INVALID"
    assert len(calls) == 1
    terminal = audit.reopen(root, NAME, validator=cli.public_shapes)
    assert terminal["outcome"] == terminal["validation_outcome"] == "CONTRACT_FAILURE"
    assert terminal["reason_code"] == "RESPONSE_CONTRACT_INVALID"
    assert terminal["candidate_count"] is None
    assert terminal["response_sha256"] == c.sha(raw).hex()
    assert terminal["validation_performed"] is True
    assert report["public_audit_attempts_completed"] == 1
    assert report["public_audit_attempts_incomplete"] == 0
    assert not list(root.glob("call_0002*"))


@pytest.mark.parametrize(
    "status,reason,outcome",
    [
        (401, "AUTHENTICATION_FAILED", "TECHNICAL_FAILURE_FINAL"),
        (403, "AUTHORIZATION_FAILED", "TECHNICAL_FAILURE_FINAL"),
        (400, "HTTP_REQUEST_REJECTED", "CONTRACT_FAILURE"),
        (302, "REDIRECT_FORBIDDEN", "CONTRACT_FAILURE"),
    ],
)
def test_no_payload_transport_failure_never_invents_hash_or_validation(
    monkeypatch, tmp_path, status, reason, outcome
):
    cfg, root = setup(
        monkeypatch,
        tmp_path,
        lambda *_: t.Capture(
            outcome, reason, status, "OTHER", "absent", None, None, 12, 2
        ),
    )
    report = run(cfg)
    assert report["status"] == "FAILED" and report["failure_code"] == reason
    terminal = audit.reopen(root, NAME, validator=cli.public_shapes)
    assert terminal["outcome"] == outcome
    assert (
        terminal["validation_performed"] is False
        and terminal["validation_outcome"] is None
    )
    assert (
        terminal["response_sha256"] is None
        and terminal["application_payload_bytes"] is None
    )
    assert not list(root.glob("*.zst"))
    assert not list(root.glob("*_validation_begin.json"))
    assert stored(root, "_finish.json")["received_body_bytes"] == 12


def test_retryable_attempt_sealed_before_existing_retry_then_correct_association(
    monkeypatch, tmp_path
):
    calls = []

    def dispatch(*_):
        calls.append(1)
        if len(calls) == 1:
            return t.Capture(
                "TECHNICAL_FAILURE_RETRYABLE",
                "TIMEOUT",
                None,
                "ABSENT",
                "absent",
                None,
                None,
                0,
                2,
            )
        assert (
            audit.reopen(root, NAME, validator=cli.public_shapes)["outcome"]
            == "TECHNICAL_FAILURE_RETRYABLE"
        )
        return successful()

    cfg, root = setup(monkeypatch, tmp_path, dispatch)
    report = run(cfg)
    assert report["status"] == "COMPLETED" and report["retry_count"] == 1
    a = audit.reopen(root, NAME, validator=cli.public_shapes)
    b = audit.reopen(root, "call_0001_attempt_2", validator=cli.public_shapes)
    assert a["response_sha256"] is None and not a["validation_performed"]
    assert (a["call"], a["attempt"], b["call"], b["attempt"]) == (1, 1, 1, 2)
    assert a["begin_sha256"] != b["begin_sha256"]
    assert a["run_provenance_sha256"] == b["run_provenance_sha256"]


@pytest.mark.parametrize("status", [204, 206])
def test_complete_non200_2xx_retained_as_contract_failure(
    monkeypatch, tmp_path, status
):
    raw = body([])
    cfg, root = setup(
        monkeypatch,
        tmp_path,
        lambda *_: replace(
            capture(raw),
            status=status,
            outcome="CONTRACT_FAILURE",
            reason="RESPONSE_CONTRACT_INVALID",
        ),
    )
    assert run(cfg)["failure_code"] == "RESPONSE_CONTRACT_INVALID"
    terminal = audit.reopen(root, NAME, validator=cli.public_shapes)
    assert terminal["response_sha256"] == c.sha(raw).hex()
    assert terminal["outcome"] == "CONTRACT_FAILURE"


@pytest.mark.parametrize(
    "suffix",
    [
        "_begin.json",
        "_finish.json",
        ".zst",
        "_capture.json",
        "_validation_begin.json",
        "_validation.json",
        "_receipt.json",
        "_SEALED",
    ],
)
def test_partial_writes_never_complete_or_continue(monkeypatch, tmp_path, suffix):
    calls = []
    cfg, root = setup(
        monkeypatch, tmp_path, lambda *_: calls.append(1) or successful(), calls=2
    )
    write = io.write

    def fault(path, raw):
        if path.name == NAME + suffix:
            # Preserve actual partial file; do not clean up failed evidence.
            write(path, raw[: max(1, len(raw) // 2)] if raw else b"partial")
            raise OSError("invented storage failure")
        write(path, raw)

    monkeypatch.setattr(io, "write", fault)
    report = run(cfg)
    assert report["status"] == "FAILED"
    assert report["public_audit_attempts_completed"] == 0
    assert len(calls) == (0 if suffix == "_begin.json" else 1)
    assert not list(root.glob("call_0002*"))
    assert (root / (NAME + suffix)).is_file()
    with pytest.raises((c.Stage12Error, KeyError)):
        audit.reopen(root, NAME, validator=cli.public_shapes)


@pytest.mark.parametrize("stage", ["compress", "decompress", "validation", "reopen"])
def test_capture_validation_and_reopen_faults_remain_incomplete(
    monkeypatch, tmp_path, stage
):
    calls = []
    cfg, root = setup(
        monkeypatch, tmp_path, lambda *_: calls.append(1) or successful(), calls=2
    )

    def fail(*_a, **_kw):
        raise OSError("invented failure")

    if stage in ("compress", "decompress"):
        monkeypatch.setattr(response, stage, fail)
    elif stage == "validation":
        monkeypatch.setattr(cli, "public_shapes", fail)
    else:
        monkeypatch.setattr(audit, "reopen", fail)
    report = run(cfg)
    assert (
        report["status"] == "FAILED" and report["public_audit_attempts_incomplete"] == 1
    )
    assert len(calls) == 1 and not (root / (NAME + "_SEALED")).exists()
    if stage in ("validation", "reopen"):
        assert (
            stored(root, "_capture.json")["capture"]["response_sha256"]
            == c.sha(body([])).hex()
        )


class Interrupted(BaseException):
    pass


@pytest.mark.parametrize(
    "suffix",
    [
        ".zst",
        "_capture.json",
        "_validation_begin.json",
        "_validation.json",
        "_receipt.json",
    ],
)
def test_interruption_after_durable_fragment_has_no_completion_or_resume(
    monkeypatch, tmp_path, suffix
):
    calls = []
    cfg, root = setup(
        monkeypatch, tmp_path, lambda *_: calls.append(1) or successful(), calls=2
    )
    write = io.write

    def interrupt(path, raw):
        write(path, raw)
        if path.name == NAME + suffix:
            raise Interrupted()

    monkeypatch.setattr(io, "write", interrupt)
    with pytest.raises(Interrupted):
        run(cfg)
    assert len(calls) == 1 and not (root / (NAME + "_SEALED")).exists()
    assert (root / (NAME + suffix)).is_file()
    with pytest.raises(c.Stage12Error):
        audit.reopen(root, NAME, validator=cli.public_shapes)
    with pytest.raises(FileExistsError):
        run(cfg)
    assert len(calls) == 1  # No resume policy, overwrite or automatic redispatch.


def test_original_failure_survives_terminal_audit_failure(monkeypatch, tmp_path):
    cfg, root = setup(monkeypatch, tmp_path, lambda *_: capture(warning()))
    write = io.write

    def fail(path, raw):
        if path.name == NAME + "_receipt.json":
            raise OSError("invented second error")
        write(path, raw)

    monkeypatch.setattr(io, "write", fail)
    report = run(cfg)
    assert report["failure_code"] == "RESPONSE_CONTRACT_INVALID"
    assert report["evidence_write_status"] == "FAILED"
    assert report["public_audit_attempts_completed"] == 0
    assert (
        stored(root, "_validation.json")["reason_code"] == "RESPONSE_CONTRACT_INVALID"
    )
    assert not (root / (NAME + "_SEALED")).exists()


def test_secret_canary_retains_only_static_incident_no_payload_hash(
    monkeypatch, tmp_path
):
    cfg, root = setup(monkeypatch, tmp_path, lambda *_: capture(b"synthetic-canary"))
    report = run(cfg)
    assert report["failure_code"] == "SECRET_ECHO_DETECTED"
    terminal = audit.reopen(root, NAME, validator=cli.public_shapes)
    assert (
        terminal["response_sha256"] is None
        and terminal["validation_performed"] is False
    )
    assert terminal["privacy_rejected"] is True
    assert not list(root.glob("*.zst"))
    assert all(b"synthetic-canary" not in p.read_bytes() for p in root.iterdir())


@pytest.mark.parametrize(
    "suffix",
    [
        "_begin.json",
        "_finish.json",
        "_capture.json",
        "_validation.json",
        "_receipt.json",
        ".zst",
    ],
)
def test_corruption_and_overwrite_rejected(monkeypatch, tmp_path, suffix):
    cfg, root = setup(monkeypatch, tmp_path, lambda *_: successful())
    assert run(cfg)["status"] == "COMPLETED"
    path = root / (NAME + suffix)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        io.write(path, b"replacement")
    assert path.read_bytes() == original
    path.write_bytes(b"invented corrupted synthetic artifact")
    with pytest.raises(c.Stage12Error):
        audit.reopen(root, NAME, validator=cli.public_shapes)


def test_dispatch_exception_has_only_unknown_delivery_and_no_fake_finish(
    monkeypatch, tmp_path
):
    def dispatch(*_):
        raise RuntimeError("invented unexpected exception")

    cfg, root = setup(monkeypatch, tmp_path, dispatch)
    report = run(cfg)
    assert report["failure_code"] == "PUBLIC_PROBE_HARNESS_FAILURE"
    assert stored(root, "_begin.json")["outcome"] == "UNKNOWN_DELIVERY"
    assert not (root / (NAME + "_finish.json")).exists()
    assert report["public_audit_attempts_incomplete"] == 1
    assert report["public_synthetic_requests_sent"] is None


@pytest.mark.parametrize(
    "outcome,reason,status",
    [
        ("TECHNICAL_FAILURE_FINAL", "AUTHENTICATION_FAILED", 401),
        ("TECHNICAL_FAILURE_RETRYABLE", "TIMEOUT", None),
    ],
)
@pytest.mark.parametrize("suffix", ["_finish.json", "_receipt.json"])
def test_transport_failure_remains_primary_when_receipt_cannot_be_written(
    monkeypatch, tmp_path, outcome, reason, status, suffix
):
    calls = []

    def dispatch(*_):
        calls.append(1)
        return t.Capture(outcome, reason, status, "ABSENT", "absent", None, None, 0, 2)

    cfg, root = setup(monkeypatch, tmp_path, dispatch)
    write = io.write

    def fault(path, raw):
        if path.name == NAME + suffix:
            raise OSError("invented receipt failure")
        write(path, raw)

    monkeypatch.setattr(io, "write", fault)
    report = run(cfg)
    assert len(calls) == 1
    assert (
        report["failure_code"] == reason and report["evidence_write_status"] == "FAILED"
    )
    assert report["public_audit_attempts_completed"] == 0
    assert not (root / (NAME + "_SEALED")).exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("call", 2),
        ("attempt", 2),
        ("validation_performed", False),
        ("response_validation_contract_sha256", "0" * 64),
        ("candidate_count", 1),
        ("outcome", "SUCCESS_WITH_CANDIDATES"),
        ("call", True),
        ("candidate_count", False),
        ("validation_performed", 1),
        ("privacy_rejected", 0),
    ],
)
def test_reopen_checks_logical_binding_even_if_physical_inventory_is_recomputed(
    monkeypatch, tmp_path, field, value
):
    cfg, root = setup(monkeypatch, tmp_path, lambda *_: successful())
    assert run(cfg)["status"] == "COMPLETED"
    terminal = stored(root, "_validation.json")
    terminal[field] = value
    (root / (NAME + "_validation.json")).write_bytes(c.canonical(terminal))
    receipt = stored(root, "_receipt.json")
    receipt["inventory"] = io.file_inventory(
        root, tuple(row["path"] for row in receipt["inventory"])
    )
    (root / (NAME + "_receipt.json")).write_bytes(c.canonical(receipt))
    with pytest.raises(c.Stage12Error):
        audit.reopen(root, NAME, validator=cli.public_shapes)


def test_existing_circuit_breaker_stops_after_three_durable_timeout_attempts(
    monkeypatch, tmp_path
):
    calls = []

    def dispatch(*_):
        calls.append(1)
        return t.Capture(
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT",
            None,
            "ABSENT",
            "absent",
            None,
            None,
            0,
            2,
        )

    cfg, root = setup(monkeypatch, tmp_path, dispatch)
    report = run(cfg)
    assert len(calls) == 3 and report["failure_code"] == "CIRCUIT_BREAKER_OPEN"
    assert report["public_audit_attempts_completed"] == 3
    assert report["public_audit_attempts_incomplete"] == 0
    for number in range(1, 4):
        terminal = audit.reopen(
            root, f"call_0001_attempt_{number}", validator=cli.public_shapes
        )
        assert terminal["outcome"] == "TECHNICAL_FAILURE_RETRYABLE"
        assert terminal["response_sha256"] is None


def test_directory_fsync_failure_stops_before_completion(monkeypatch, tmp_path):
    calls = []
    cfg, root = setup(
        monkeypatch, tmp_path, lambda *_: calls.append(1) or successful(), calls=2
    )
    write = io.write
    sync = io.fsync_directory
    armed = [False]

    def write_with_fault(path, raw):
        armed[0] = path.name == NAME + "_receipt.json"
        try:
            write(path, raw)
        finally:
            armed[0] = False

    def fail_directory(path):
        if armed[0]:
            raise OSError("invented directory fsync failure")
        sync(path)

    monkeypatch.setattr(io, "write", write_with_fault)
    monkeypatch.setattr(io, "fsync_directory", fail_directory)
    report = run(cfg)
    assert len(calls) == 1 and report["status"] == "FAILED"
    assert report["public_audit_attempts_completed"] == 0
    assert (root / (NAME + "_receipt.json")).is_file()
    assert not (root / (NAME + "_SEALED")).exists()


@pytest.mark.parametrize(
    "outcome,reason,status",
    [
        ("TECHNICAL_FAILURE_FINAL", "AUTHENTICATION_FAILED", 401),
        ("TECHNICAL_FAILURE_RETRYABLE", "TIMEOUT", None),
        ("VALIDATION_REQUIRED", "OK", 200),
    ],
)
@pytest.mark.parametrize("failure_kind", ["static_context_error", "io_error"])
def test_initial_context_read_preserves_only_known_primary_failure(
    monkeypatch, tmp_path, outcome, reason, status, failure_kind
):
    calls = []
    capture_result = (
        successful()
        if outcome == "VALIDATION_REQUIRED"
        else t.Capture(outcome, reason, status, "ABSENT", "absent", None, None, 0, 2)
    )
    cfg, root = setup(
        monkeypatch,
        tmp_path,
        lambda *_: calls.append(1) or capture_result,
        calls=2,
    )
    read, write = io.read, io.write
    initial_reads, saved_finish = [], []

    def fail_initial_read(path, **kwargs):
        if path.name == NAME + "_begin.json":
            initial_reads.append(path)
            if failure_kind == "static_context_error":
                raise c.Stage12Error("S12_PRIVATE_FILE_INVALID")
            raise OSError("synthetic-canary")
        return read(path, **kwargs)

    def record_finish(path, raw):
        write(path, raw)
        if path.name == NAME + "_finish.json":
            saved_finish.append(raw)

    monkeypatch.setattr(io, "read", fail_initial_read)
    monkeypatch.setattr(io, "write", record_finish)
    monkeypatch.setattr(
        cli,
        "public_shapes",
        lambda _: pytest.fail("validation must not run after context failure"),
    )
    report = run(cfg)
    known_failure = outcome != "VALIDATION_REQUIRED"
    context_code = (
        "S12_PRIVATE_FILE_INVALID"
        if failure_kind == "static_context_error"
        else "PUBLIC_PROBE_HARNESS_FAILURE"
    )
    assert report["status"] == "FAILED"
    assert report["failure_code"] == (reason if known_failure else context_code)
    if known_failure:
        assert report["evidence_write_status"] == "FAILED"
    else:
        # Retain the existing context-failure path; do not invent a primary reason.
        assert "evidence_write_status" not in report
    assert len(initial_reads) == len(calls) == 1
    assert report["public_audit_attempts_started"] == 1
    assert report["public_audit_attempts_incomplete"] == 1
    assert report["public_audit_attempts_completed"] == 0
    assert report["retry_count"] == 0
    assert saved_finish == [(root / (NAME + "_finish.json")).read_bytes()]
    assert stored(root, "_finish.json")["reason"] == reason
    begin = io.metadata((root / (NAME + "_begin.json")).read_bytes())
    assert begin["outcome"] == "UNKNOWN_DELIVERY"
    assert {path.name for path in root.iterdir()} == {
        *audit.CONTEXT,
        NAME + "_begin.json",
        NAME + "_finish.json",
        "sanitized_report.json",
    }
    # No raw/capture/hash, validation fragments, terminal inventory or seal exist.
    assert all(b"synthetic-canary" not in p.read_bytes() for p in root.iterdir())

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as ops
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from stage12_synthetic import HASH, NOW, body, feature


def config(tmp_path, deeper=None):
    return dict(
        scope="PUBLIC_SYNTHETIC_ONLY",
        origin="https://synthetic.invalid",
        approved_ip="127.0.0.1",
        configuration_evidence_sha256=HASH.hex(),
        target_limit=8192,
        header_limit=16384,
        operator_max_size=20 if deeper else 10,
        deeper_sizes=deeper or [],
        operator_size_evidence_sha256=HASH.hex() if deeper else None,
        workload_authorization_sha256=HASH.hex(),
        secret_source_category="APPROVED_RUNTIME_ENVIRONMENT",
        authentication_mechanism="X-API-Key",
        walltime_seconds=1700,
        output_directory=str(tmp_path / "probe"),
    )


def harness(monkeypatch, tmp_path, dispatch):
    # All external boundaries are replaced; production offers no test bypass.
    import socket

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_a, **_k: pytest.fail("external network forbidden"),
    )
    monkeypatch.setattr(cli, "IMPLEMENTATION_CLEARED_FOR_PROBE", True)
    monkeypatch.setattr(cli, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(cli.resource, "setrlimit", lambda *_: None)
    monkeypatch.setattr(cli.assets, "verify", lambda _: {})
    monkeypatch.setattr(
        cli.subprocess,
        "check_output",
        lambda args, **_: "1" * 40 if args[1] == "rev-parse" else "",
    )
    monkeypatch.setattr(cli, "validate_output_scope", lambda _: None)
    monkeypatch.setattr(
        cli.transport.Secret, "runtime", lambda: t.Secret.checked(b"synthetic-canary")
    )
    monkeypatch.setenv("SLURM_JOB_ID", "1")
    monkeypatch.setattr(cli.transport, "send", dispatch)
    clock = [0]
    monkeypatch.setattr(cli.time, "monotonic_ns", lambda: clock[0])
    monkeypatch.setattr(
        cli.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + int(seconds * 1_000_000_000)),
    )
    return config(tmp_path)


def successful(*_):
    return t.Capture(
        "VALIDATION_REQUIRED",
        "OK",
        200,
        "application/json",
        "identity",
        None,
        body([]),
        len(body([])),
        2,
    )


def test_frozen_public_workload_and_owner_base_only_clarification(tmp_path):
    _, plan = cli.validate_config(config(tmp_path))
    calls = probe.planned_calls(plan)
    assert len(calls) == 512 and plan["maximum_attempts"] == 2560
    assert plan["above10_capability"] == "ABOVE10_SAFE_SIZE_NOT_YET_OPERATOR_VERIFIED"
    assert len(probe.fixtures()) == 64
    assert {case["core"]["search_mode"] for _, _, case in calls} == {
        "FULL_TEXT",
        "STRUCTURED",
    }
    assert {size for size, _, _ in calls} == {1, 3, 5, 10}
    assert all(plan[key] == "UNSELECTED" for key in ("C", "T", "N"))
    _, deep = cli.validate_config(config(tmp_path, [20]))
    assert len(probe.planned_calls(deep)) == 544
    bad = config(tmp_path, [20])
    bad["operator_size_evidence_sha256"] = None
    with pytest.raises(c.Stage12Error):
        cli.validate_config(bad)
    bad = config(tmp_path, [30])
    with pytest.raises(c.Stage12Error):
        cli.validate_config(bad)


def test_full_mock_probe_replay_prefix_summary_and_no_secret(monkeypatch, tmp_path):
    cfg = harness(monkeypatch, tmp_path, successful)
    report = cli.run(cfg, "1" * 40, Path("."))
    assert report["status"] == "COMPLETED", report
    assert report["public_synthetic_requests_sent"] == 512
    assert report["retry_count"] == 0 and report["same_size_agreement"] == 256
    assert report["prefix_agreement"] == 768 and report["prefix_disagreement"] == 0
    assert report["endpoint_valid_responses"] == {"FULL_TEXT": 256, "STRUCTURED": 256}
    assert report["sizes"]["10"]["latency_ms"]["count"] == 128
    raw = io.read(Path(cfg["output_directory"]) / "sanitized_report.json")
    assert b"synthetic-canary" not in raw
    assert all(value == 0 for value in report["privacy"].values())


def test_retry_clock_durable_and_client_retry_bounded(monkeypatch, tmp_path):
    count = [0]
    decision = ops.retry_after_decision(
        "Thu, 01 Jan 2026 00:00:00 GMT", "bad Date", NOW
    )

    def dispatch(*args):
        count[0] += 1
        if count[0] == 1:
            return t.Capture(
                "TECHNICAL_FAILURE_RETRYABLE",
                "TIMEOUT",
                408,
                "ABSENT",
                "absent",
                0,
                None,
                0,
                1,
                decision,
            )
        return successful()

    cfg = harness(monkeypatch, tmp_path, dispatch)
    report = cli.run(cfg, "1" * 40, Path("."))
    assert report["status"] == "COMPLETED" and report["retry_count"] == 1
    finish = io.metadata(
        io.read(Path(cfg["output_directory"]) / "call_0001_attempt_1_finish.json")
    )
    assert finish["retry_clock"]["reference_clock"] == "CLIENT_RECEIPT_UTC"
    assert finish["retry_clock"]["response_date"] == "UNUSABLE"


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("auth", "AUTHENTICATION_FAILED"),
        ("contract", "RESPONSE_CONTRACT_INVALID"),
        ("secret", "SECRET_ECHO_DETECTED"),
        ("harness", "PUBLIC_PROBE_HARNESS_FAILURE"),
    ],
)
def test_failure_never_continues_or_leaks(monkeypatch, tmp_path, kind, expected):
    calls = []

    def dispatch(*_):
        calls.append(1)
        if kind == "auth":
            return t.Capture(
                "TECHNICAL_FAILURE_FINAL",
                expected,
                401,
                "OTHER",
                "absent",
                None,
                None,
                0,
                1,
            )
        if kind == "harness":
            raise RuntimeError("synthetic-canary")
        raw = b"synthetic-canary" if kind == "secret" else body([{"type": "Feature"}])
        return replace(successful(), payload=raw, received_body_bytes=len(raw))

    cfg = harness(monkeypatch, tmp_path, dispatch)
    report = cli.run(cfg, "1" * 40, Path("."))
    assert report["status"] == "FAILED" and report["failure_code"] == expected
    assert len(calls) == 1 and b"synthetic-canary" not in c.canonical(report)
    assert not list(Path(cfg["output_directory"]).glob("call_0002*"))


def test_primary_failure_survives_report_write_fault(monkeypatch, tmp_path):
    cfg = harness(
        monkeypatch,
        tmp_path,
        lambda *_: t.Capture(
            "TECHNICAL_FAILURE_FINAL",
            "AUTHENTICATION_FAILED",
            401,
            "OTHER",
            "absent",
            None,
            None,
            0,
            1,
        ),
    )
    write = io.write

    def fail_report(path, raw):
        if path.name == "sanitized_report.json":
            raise OSError("invented reporting error")
        write(path, raw)

    monkeypatch.setattr(io, "write", fail_report)
    report = cli.run(cfg, "1" * 40, Path("."))
    assert report["failure_code"] == "AUTHENTICATION_FAILED"
    assert report["evidence_write_status"] == "FAILED"


def test_duplicate_looking_features_preserved_in_probe():
    assert len(cli.public_shapes(body([feature(), feature()]))) == 2


def test_unapproved_auth_mechanism_stops_before_secret_or_dispatch(tmp_path):
    cfg = config(tmp_path)
    cfg["authentication_mechanism"] = "guessed-header"
    with pytest.raises(c.Stage12Error, match="AUTH_SOURCE_UNVERIFIED"):
        cli.validate_config(cfg)


def test_public_harness_records_file_provider_without_value(monkeypatch, tmp_path):
    cfg = harness(monkeypatch, tmp_path, successful)
    cfg["secret_source_category"] = "APPROVED_PRIVATE_FILE"
    monkeypatch.setenv(
        "SAFE_PELIAS_API_KEY_FILE", str(tmp_path / "invented-provider-path")
    )
    report = cli.run(cfg, "1" * 40, Path("."))
    assert report["status"] == "COMPLETED"
    assert report["authentication"]["source_category"] == "APPROVED_PRIVATE_FILE"
    assert report["authentication"]["provider_preflight"] == "PASS"
    assert b"synthetic-canary" not in c.canonical(report)
    assert b"invented-provider-path" not in c.canonical(report)


def test_startup_provider_failure_has_sanitized_specific_code(
    monkeypatch, capsys, tmp_path
):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--configuration",
            str(tmp_path / "config.json"),
            "--implementation-sha",
            "1" * 40,
        ],
    )
    monkeypatch.setattr(cli, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(cli.io, "read", lambda _: b"{}\n")

    def fail(*_):
        raise c.Stage12Error("ENVIRONMENT_AUTH_FILE_INVALID")

    monkeypatch.setattr(cli, "run", fail)
    assert cli.main() == 1
    captured = capsys.readouterr()
    assert (
        io.metadata(captured.out.encode())["failure_code"]
        == "ENVIRONMENT_AUTH_FILE_INVALID"
    )
    assert not captured.err

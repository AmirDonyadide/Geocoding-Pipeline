from __future__ import annotations

import http.client
import socket
import threading
from dataclasses import replace

import pytest

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as ops
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from stage12_synthetic import HASH, body


@pytest.mark.parametrize("secret", [b"", b"a\r\nb", b"a\x00b", b"a b", b"a\xffb"])
def test_invalid_secret_never_rendered(secret):
    with pytest.raises(c.Stage12Error) as caught:
        t.Secret.checked(secret)
    assert str(caught.value) == "ENVIRONMENT_AUTH_INVALID"


def test_secret_repr_and_missing_guard(monkeypatch):
    value = t.Secret.checked(b"synthetic-secret")
    assert "synthetic-secret" not in repr(value)
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError):
        t.Secret.runtime()


def exchange(monkeypatch, reply):
    # Explicit loopback-only synthetic capture. No real key, TLS route or
    # invented SLURM markers; the production path has no bypass switch.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    captured = []

    def serve():
        conn, _ = listener.accept()
        with conn:
            received = b""
            while b"\r\n\r\n" not in received:
                received += conn.recv(65536)
            captured.append(received)
            conn.sendall(reply)
        listener.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _operation: None)
    monkeypatch.setattr(
        t,
        "_Connection",
        lambda _host, _port, ip, timeout: http.client.HTTPConnection(
            ip, port, timeout=timeout
        ),
    )
    profile = t.TransportProfile(
        "https://synthetic.invalid", "127.0.0.1", HASH, 4096, 8192
    )
    result = t.send(
        b"/v1/search?boundary.country=DE&size=3&text=Caf%C3%A9%20%2B",
        profile,
        t.Secret.checked(b"synthetic-canary"),
        ops.Operations(),
    )
    worker.join(timeout=2)
    assert not worker.is_alive()
    return result, captured


def test_exact_method_target_header_order_utf8_and_payload(monkeypatch):
    raw = body()
    reply = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: "
        + str(len(raw)).encode()
        + b"\r\nConnection: close\r\n\r\n"
        + raw
    )
    result, captured = exchange(monkeypatch, reply)
    assert (
        result.payload == raw
        and result.status == 200
        and result.outcome == "VALIDATION_REQUIRED"
    )
    assert captured == [
        b"GET /v1/search?boundary.country=DE&size=3&text=Caf%C3%A9%20%2B HTTP/1.1\r\nHost: synthetic.invalid\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nUser-Agent: SAFE-stage12-retrieval/1\r\nX-API-Key: synthetic-canary\r\n\r\n"
    ]


def test_chunked_transport_decoded_application_bytes(monkeypatch):
    raw = body([])
    reply = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        + hex(len(raw))[2:].encode()
        + b"\r\n"
        + raw
        + b"\r\n0\r\n\r\n"
    )
    result, _ = exchange(monkeypatch, reply)
    assert result.payload == raw and c.sha(result.payload) == c.sha(raw)


def test_transport_truncation_never_zero(monkeypatch):
    result, _ = exchange(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\nConnection: close\r\n\r\n{}",
    )
    assert (
        result.outcome == "TECHNICAL_FAILURE_RETRYABLE"
        and result.reason == "RESPONSE_TRUNCATED"
        and result.payload is None
    )


def test_secret_echo_never_retained(monkeypatch):
    raw = b"synthetic-canary"
    reply = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 16\r\nConnection: close\r\n\r\n"
        + raw
    )
    # Exact length here is essential to exercise the secret guard, not EOF.
    reply = reply.replace(
        b"Content-Length: 16", b"Content-Length: " + str(len(raw)).encode()
    )
    result, _ = exchange(monkeypatch, reply)
    assert result.payload is None and result.reason == "SECRET_ECHO_DETECTED"
    assert "synthetic-canary" not in repr(result)


def test_redirect_no_follow(monkeypatch):
    result, captured = exchange(
        monkeypatch,
        b"HTTP/1.1 302 Found\r\nLocation: https://unapproved.invalid/\r\nContent-Length: 0\r\n\r\n",
    )
    assert result.reason == "REDIRECT_FORBIDDEN" and len(captured) == 1


@pytest.mark.parametrize(
    "origin",
    [
        "http://synthetic.invalid",
        "https://user:password@synthetic.invalid",
        "https://synthetic.invalid/path",
        "https://synthetic.invalid/?query=1",
        "https://synthetic.invalid/#fragment",
    ],
)
def test_unapproved_route_shape(origin):
    with pytest.raises(c.Stage12Error):
        t.TransportProfile(origin, "127.0.0.1", HASH, 4096, 8192).validate()


def test_initial_probe_cannot_silently_raise_concurrency():
    with pytest.raises(c.Stage12Error):
        replace(ops.Operations(), connections=4).validate(initial_probe=True)


def test_whole_deadline_interrupts_slow_connection_close_body(monkeypatch):
    import time

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        conn, _ = listener.accept()
        try:
            with conn:
                conn.recv(8192)
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n"
                )
                for _ in range(30):
                    conn.sendall(b" ")
                    time.sleep(0.03)
        except OSError:
            pass
        finally:
            listener.close()

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(
        t,
        "_Connection",
        lambda _h, _p, ip, timeout: http.client.HTTPConnection(
            ip, port, timeout=timeout
        ),
    )
    op = replace(
        ops.Operations(),
        connect_timeout_ms=100,
        read_idle_timeout_ms=100,
        attempt_timeout_ms=220,
    )
    result = t.send(
        b"/v1/search?size=1&text=Invented",
        t.TransportProfile("https://synthetic.invalid", "127.0.0.1", HASH, 8192, 8192),
        t.Secret.checked(b"invented-key"),
        op,
    )
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert result.reason == "TIMEOUT" and result.payload is None
    assert result.outcome == "TECHNICAL_FAILURE_RETRYABLE"
    assert result.elapsed_ms < 1500


def test_transport_retains_only_sanitized_retry_clock(monkeypatch):
    result, _ = exchange(
        monkeypatch,
        b"HTTP/1.1 429 Too Many Requests\r\nDate: broken\r\nRetry-After: Thu, 01 Jan 2026 00:00:00 GMT\r\nContent-Length: 0\r\n\r\n",
    )
    assert result.retry_after_audit.reference_clock == "CLIENT_RECEIPT_UTC"
    assert result.retry_after_audit.response_date == "UNUSABLE"
    assert result.retry_after_seconds == 0
    assert "broken" not in repr(result)


@pytest.mark.parametrize(
    "length", [b"-1", b"garbage", b"1, 1", b"999999999999999999999999999999"]
)
def test_malformed_content_length_fails_whole_response(monkeypatch, length):
    result, _ = exchange(
        monkeypatch,
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
        + length
        + b"\r\nConnection: close\r\n\r\n{}",
    )
    assert result.outcome == "CONTRACT_FAILURE" and result.payload is None

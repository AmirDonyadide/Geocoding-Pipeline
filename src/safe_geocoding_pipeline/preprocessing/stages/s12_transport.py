"""HTTP/1.1 SAFE-only transport with explicit routing and no library retries."""

from __future__ import annotations

import http.client
import ipaddress
import os
import re
import socket
import ssl
import stat
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

from . import s12_operations as ops
from . import s12_response as response
from . import s12_retrieval_contract as c


@dataclass(frozen=True)
class Secret:
    value: bytes = field(repr=False)

    @classmethod
    def runtime(cls) -> Secret:
        require_goethe_nhr_slurm("stage12 runtime authentication")
        filename = os.environ.get("SAFE_PELIAS_API_KEY_FILE")
        if filename is not None:
            c.require(
                not os.environ.get("SAFE_PELIAS_API_KEY"), "ENVIRONMENT_AUTH_AMBIGUOUS"
            )
            return cls.private_file(filename)
        value = os.environ.get("SAFE_PELIAS_API_KEY")
        c.require(bool(value), "ENVIRONMENT_AUTH_MISSING")
        assert value is not None
        try:
            encoded = value.encode("ascii", "strict")
        except UnicodeError:
            raise c.Stage12Error("ENVIRONMENT_AUTH_INVALID") from None
        return cls.checked(encoded)

    @classmethod
    def private_file(cls, filename: str) -> Secret:
        """Read an owner-only regular file into memory, without copying or hashing.

        No fallback on a bad configured file. One final LF/CRLF is permitted for
        a text-file provider; all other whitespace/header injection is rejected.
        """
        c.require(
            bool(filename) and Path(filename).is_absolute(),
            "ENVIRONMENT_AUTH_FILE_INVALID",
        )
        fd = None
        parent_fd = None
        try:
            path = Path(filename)
            parent_fd = os.open(
                path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            parent = os.fstat(parent_fd)
            c.require(
                parent.st_uid == os.geteuid() and not parent.st_mode & 0o022,
                "ENVIRONMENT_AUTH_FILE_INVALID",
            )
            fd = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
            )
            before = os.fstat(fd)
            c.require(
                stat.S_ISREG(before.st_mode)
                and before.st_uid == os.geteuid()
                and stat.S_IMODE(before.st_mode) in (0o400, 0o600)
                and before.st_nlink == 1
                and 0 < before.st_size <= 8194,
                "ENVIRONMENT_AUTH_FILE_INVALID",
            )
            value = os.read(fd, 8195)
            after = os.fstat(fd)
            c.require(
                len(value) == before.st_size
                and (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                == (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ),
                "ENVIRONMENT_AUTH_FILE_CHANGED",
            )
        except c.Stage12Error:
            raise
        except (OSError, ValueError):
            raise c.Stage12Error("ENVIRONMENT_AUTH_FILE_INVALID") from None
        finally:
            if fd is not None:
                os.close(fd)
            if parent_fd is not None:
                os.close(parent_fd)
        if value.endswith(b"\r\n"):
            value = value[:-2]
        elif value.endswith(b"\n"):
            value = value[:-1]
        return cls.checked(value)

    @classmethod
    def checked(cls, value: bytes) -> Secret:
        c.require(
            type(value) is bytes
            and 0 < len(value) <= 8192
            and all(33 <= b <= 126 for b in value),
            "ENVIRONMENT_AUTH_INVALID",
        )
        return cls(value)


@dataclass(frozen=True)
class TransportProfile:
    origin: str
    approved_ip: str
    configuration_evidence_sha256: bytes
    target_limit: int
    header_limit: int

    def validate(self) -> tuple[str, int, str]:
        parsed = urlsplit(self.origin)
        c.require(
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment,
            "ENVIRONMENT_NETWORK_INVALID",
        )
        assert parsed.hostname is not None
        c.digest(self.configuration_evidence_sha256)
        try:
            ipaddress.ip_address(self.approved_ip)
            port = parsed.port or 443
            host = parsed.hostname.encode("idna").decode("ascii")
        except (ValueError, UnicodeError):
            raise c.Stage12Error("ENVIRONMENT_NETWORK_INVALID") from None
        c.require(
            type(self.target_limit) is int
            and self.target_limit > 0
            and type(self.header_limit) is int
            and self.header_limit > 0,
            "S12_TRANSPORT_PROFILE_INVALID",
        )
        authority = ("[" + host + "]" if ":" in host else host) + (
            "" if port == 443 else ":" + str(port)
        )
        return host, port, authority


def headers(authority: str, key: Secret) -> tuple[tuple[str, bytes], ...]:
    Secret.checked(key.value)
    return (
        ("Host", authority.encode("ascii")),
        ("Accept", b"application/json"),
        ("Accept-Encoding", b"identity"),
        ("User-Agent", b"SAFE-stage12-retrieval/1"),
        ("X-API-Key", key.value),
    )


@dataclass(frozen=True)
class Capture:
    outcome: str
    reason: str
    status: int | None
    content_type: str
    content_encoding: str
    retry_after_seconds: int | None
    payload: bytes | None = field(repr=False)
    received_body_bytes: int
    elapsed_ms: int
    retry_after_audit: ops.RetryAfter | None = None


class _Connection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, port: int, approved_ip: str, timeout: float):
        self.tls_context = ssl.create_default_context()
        super().__init__(hostname, port, timeout=timeout, context=self.tls_context)
        self.approved_ip = approved_ip

    def connect(self) -> None:
        # No proxy, environment routing or unbounded DNS lookup at dispatch.
        sock = socket.create_connection((self.approved_ip, self.port), self.timeout)
        self.sock = sock
        self.sock = self.tls_context.wrap_socket(sock, server_hostname=self.host)


def send(
    target: bytes, profile: TransportProfile, key: Secret, operations: ops.Operations
) -> Capture:
    """Caller owns rate admission, durable begin, workload and deployment gates."""
    require_goethe_nhr_slurm("stage12 SAFE Pelias transport")
    operations.validate()
    host, port, authority = profile.validate()
    c.require(
        target.startswith((b"/v1/search?", b"/v1/search/structured?"))
        and len(target) <= profile.target_limit
        and all(33 <= b <= 126 for b in target)
        and b"#" not in target,
        "REQUEST_TARGET_TOO_LARGE",
    )
    request_headers = headers(authority, key)
    header_bytes = sum(len(k) + len(v) + 4 for k, v in request_headers)
    c.require(header_bytes <= profile.header_limit, "REQUEST_HEADERS_TOO_LARGE")
    connection = _Connection(
        host, port, profile.approved_ip, operations.connect_timeout_ms / 1000
    )
    connection.debuglevel = 0
    started = time.monotonic_ns()
    expired = threading.Event()
    active_socket: socket.socket | None = None

    def deadline() -> None:
        expired.set()
        active = active_socket or connection.sock
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()

    timer = threading.Timer(operations.attempt_timeout_ms / 1000, deadline)
    timer.daemon = True
    status: int | None = None
    media, coding = "ABSENT", "absent"
    retry = None
    retry_audit = None
    received = 0
    body: bytes | None = None
    outcome, reason = "TECHNICAL_FAILURE_RETRYABLE", "NETWORK_TRANSIENT"
    timer.start()
    try:
        connection.connect()
        c.require(not expired.is_set(), "TIMEOUT")
        assert connection.sock is not None
        active_socket = connection.sock
        connection.sock.settimeout(operations.read_idle_timeout_ms / 1000)
        connection.putrequest(
            "GET", target.decode("ascii"), skip_host=True, skip_accept_encoding=True
        )
        for name, value in request_headers:
            connection.putheader(name, value)
        connection.endheaders()
        incoming = connection.getresponse()
        status = incoming.status
        media = response.media_type(incoming.getheader("Content-Type"))
        coding = response.content_encoding(incoming.getheader("Content-Encoding"))
        retry_audit = ops.retry_after_decision(
            incoming.getheader("Retry-After"),
            incoming.getheader("Date"),
            datetime.now(timezone.utc),
        )
        retry = retry_audit.seconds
        outcome, reason = ops.classify(status)
        # Authentication/error pages never enter ordinary raw storage.
        if 200 <= status < 300:
            c.require(coding in ("absent", "identity"), "RESPONSE_CONTRACT_INVALID")
            c.require(
                len(incoming.headers.get_all("Content-Length", [])) <= 1
                and len(incoming.headers.get_all("Transfer-Encoding", [])) <= 1,
                "RESPONSE_CONTRACT_INVALID",
            )
            c.require(
                not (
                    incoming.getheader("Content-Length") is not None
                    and incoming.getheader("Transfer-Encoding") is not None
                ),
                "RESPONSE_CONTRACT_INVALID",
            )
            length_header = incoming.getheader("Content-Length")
            if length_header is not None:
                c.require(
                    re.fullmatch(r"[0-9]+", length_header) is not None
                    and len(length_header) <= 20,
                    "RESPONSE_CONTRACT_INVALID",
                )
                c.require(
                    int(length_header) <= operations.response_ceiling_bytes,
                    "RESPONSE_RESOURCE_LIMIT",
                )
            transfer = incoming.getheader("Transfer-Encoding")
            c.require(
                transfer is None or transfer.lower().strip() == "chunked",
                "RESPONSE_CONTRACT_INVALID",
            )
            collected = bytearray()
            while True:
                c.require(not expired.is_set(), "TIMEOUT")
                part = incoming.read1(
                    min(65536, operations.response_ceiling_bytes + 1 - len(collected))
                )
                if not part:
                    break
                received += len(part)
                collected.extend(part)
                c.require(
                    len(collected) <= operations.response_ceiling_bytes,
                    "RESPONSE_RESOURCE_LIMIT",
                )
            c.require(not expired.is_set(), "TIMEOUT")
            if incoming.length not in (None, 0):
                outcome, reason = "TECHNICAL_FAILURE_RETRYABLE", "RESPONSE_TRUNCATED"
            else:
                body = bytes(collected)
                response.secret_guard(body, key.value)
    except c.Stage12Error as error:
        reason = str(error)
        body = None
        outcome = (
            "TECHNICAL_FAILURE_RETRYABLE" if reason == "TIMEOUT" else "CONTRACT_FAILURE"
        )
    except (TimeoutError, socket.timeout):
        outcome, reason, body = "TECHNICAL_FAILURE_RETRYABLE", "TIMEOUT", None
    except ssl.SSLError:
        outcome, reason, body = (
            "TECHNICAL_FAILURE_FINAL",
            "ENVIRONMENT_NETWORK_INVALID",
            None,
        )
    except http.client.IncompleteRead:
        outcome, reason, body = (
            "TECHNICAL_FAILURE_RETRYABLE",
            "RESPONSE_TRUNCATED",
            None,
        )
    except (OSError, http.client.HTTPException):
        outcome, reason, body = (
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT" if expired.is_set() else "NETWORK_TRANSIENT",
            None,
        )
    finally:
        timer.cancel()
        connection.close()
    return Capture(
        outcome,
        reason,
        status,
        media,
        coding,
        retry,
        body,
        received,
        (time.monotonic_ns() - started) // 1_000_000,
        retry_audit,
    )

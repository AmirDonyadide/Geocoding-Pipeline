"""Frozen bounded attempt/rate/breaker rules. No scheduling or silent recovery."""

from __future__ import annotations

import hashlib
import math
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from . import s12_retrieval_contract as c

VERSION = "stage12_transport_operations_v1"


@dataclass(frozen=True)
class Operations:
    version: str = VERSION
    max_attempts: int = 5
    connect_timeout_ms: int = 10_000
    read_idle_timeout_ms: int = 30_000
    attempt_timeout_ms: int = 60_000
    identity_timeout_ms: int = 10_000
    requests_per_second: int = 1
    connections: int = 2
    retry_after_ceiling_ms: int = 300_000
    response_ceiling_bytes: int = 16 * 1024 * 1024
    json_depth: int = 64
    queue_multiplier: int = 2

    def validate(self, *, initial_probe: bool = False) -> None:
        c.require(self.version == VERSION, "S12_OPERATIONS_INVALID")
        c.require(
            all(
                type(v) is int and v > 0
                for k, v in asdict(self).items()
                if k != "version"
            ),
            "S12_OPERATIONS_INVALID",
        )
        c.require(
            self.max_attempts <= 5
            and self.connections <= 4
            and self.requests_per_second <= 2,
            "S12_OPERATIONS_INVALID",
        )
        c.require(
            self.connect_timeout_ms <= self.attempt_timeout_ms
            and self.read_idle_timeout_ms <= self.attempt_timeout_ms,
            "S12_OPERATIONS_INVALID",
        )
        c.require(
            self.retry_after_ceiling_ms <= 300_000
            and self.response_ceiling_bytes <= 16 * 1024 * 1024
            and self.json_depth <= 64
            and self.queue_multiplier == 2,
            "S12_OPERATIONS_INVALID",
        )
        if initial_probe:
            c.require(self == Operations(), "S12_PROBE_OPERATIONS_NOT_INITIAL")

    def fingerprint(self) -> bytes:
        self.validate()
        return c.sha(c.canonical(asdict(self)))


def classify(status: int) -> tuple[str, str]:
    c.require(type(status) is int and 100 <= status <= 599, "RESPONSE_CONTRACT_INVALID")
    if status == 200:
        return "VALIDATION_REQUIRED", "OK"
    if status in (401, 403):
        return (
            "TECHNICAL_FAILURE_FINAL",
            "AUTHENTICATION_FAILED" if status == 401 else "AUTHORIZATION_FAILED",
        )
    if status == 408:
        return "TECHNICAL_FAILURE_RETRYABLE", "TIMEOUT"
    if status == 429:
        return "TECHNICAL_FAILURE_RETRYABLE", "RATE_LIMITED"
    if status in (501, 505):
        return "CONTRACT_FAILURE", "UNSUPPORTED_PROTOCOL"
    if status >= 500:
        return "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT"
    if status >= 400:
        return "CONTRACT_FAILURE", "HTTP_REQUEST_REJECTED"
    if status >= 300:
        return "CONTRACT_FAILURE", "REDIRECT_FORBIDDEN"
    return "CONTRACT_FAILURE", "RESPONSE_CONTRACT_INVALID"


@dataclass(frozen=True)
class RetryAfter:
    seconds: int | None
    kind: str
    reference_clock: str
    response_date: str
    receipt_utc: str

    def audit(self) -> dict[str, str | int | None]:
        return asdict(self)


def http_date(value: str | None) -> datetime | None:
    """Only HTTP's three date grammars, never a permissively parsed prefix."""
    if value is None or len(value) > 128:
        return None
    day = r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
    month = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    patterns = (
        day + r", [0-9]{2} " + month + r" [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT",
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), [0-9]{2}-"
        + month
        + r"-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT",
        day + " " + month + r" (?:[0-9]{2}| [0-9]) [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}",
    )
    if not any(re.fullmatch(pattern, value) for pattern in patterns):
        return None
    try:
        result = parsedate_to_datetime(value)
        return (
            result.replace(tzinfo=timezone.utc)
            if result.tzinfo is None
            else result.astimezone(timezone.utc)
        )
    except (ValueError, TypeError, OverflowError):
        return None


def retry_after_decision(
    value: str | None, date: str | None, receipt_utc: datetime
) -> RetryAfter:
    """Owner clarification: unusable Date uses client receipt UTC, never base only.

    Raw headers are discarded. This is operational audit, outside scientific IDs.
    """
    c.require(receipt_utc.tzinfo is not None, "S12_RECEIPT_CLOCK_INVALID")
    receipt = receipt_utc.astimezone(timezone.utc)
    stamp = receipt.isoformat(timespec="microseconds")
    server = http_date(date)
    date_state = (
        "MISSING" if date is None else "VALID" if server is not None else "UNUSABLE"
    )
    if value is None:
        return RetryAfter(None, "ABSENT", "NONE", date_state, stamp)
    if len(value) <= 128 and re.fullmatch(r"[0-9]+", value):
        seconds = int(value)
        if seconds < 2**64:
            return RetryAfter(seconds, "DELTA_SECONDS", "NONE", date_state, stamp)
    target = http_date(value)
    if target is None:
        return RetryAfter(None, "MALFORMED", "NONE", date_state, stamp)
    reference = server if server is not None else receipt
    delay = max(0, math.ceil((target - reference).total_seconds()))
    return RetryAfter(
        delay,
        "HTTP_DATE",
        "RESPONSE_DATE" if server is not None else "CLIENT_RECEIPT_UTC",
        date_state,
        stamp,
    )


def retry_after(
    value: str | None, date: str | None, receipt_utc: datetime
) -> int | None:
    return retry_after_decision(value, date, receipt_utc).seconds


def retry_delay(
    execution: bytes,
    next_attempt: int,
    parsed_after: int | None,
    operations: Operations,
) -> int:
    c.require(
        type(next_attempt) is int and 2 <= next_attempt <= operations.max_attempts,
        "RETRY_BUDGET_EXHAUSTED",
    )
    spacing = (
        int.from_bytes(
            hashlib.sha256(
                b"SAFE:stage12-retry-spacing:v1\0"
                + c.framed([c.digest(execution), next_attempt])
            ).digest()[:2],
            "big",
        )
        % 1000
    )
    delay = (2 ** (next_attempt - 1)) * 1000 + spacing
    if parsed_after is not None:
        c.require(
            type(parsed_after) is int and parsed_after >= 0, "S12_OPERATIONS_INVALID"
        )
        delay = max(delay, parsed_after * 1000)
    c.require(
        delay <= operations.retry_after_ceiling_ms,
        "RETRY_AFTER_REQUIRES_OWNER_RECOVERY",
    )
    return int(delay)


class Admission:
    """Sole-coordinator global admission, including control traffic and retries.

    The caller supplies a monotonic clock and waits until next_admission_ms.
    No token accumulation/burst and no automatic breaker reset.
    """

    def __init__(self, operations: Operations):
        operations.validate()
        self.operations = operations
        self.next_admission_ms = 0
        self.active = 0
        # Measured synthetic parser/replay expansion with conservative headroom.
        # A global reservation is acquired before dispatch, retained through
        # capture, parsing and checkpoint reopen, then released on finish.
        self.memory_capacity_bytes = 4 * 1024**3
        self.reservation_bytes = operations.response_ceiling_bytes * 128
        self.reserved_bytes = 0
        self.open_reason: str | None = None
        self.consecutive = 0
        self.recent: deque[tuple[bool, int]] = deque(maxlen=20)
        self.overloads: deque[int] = deque()

    def admit(self, now_ms: int) -> None:
        c.require(self.open_reason is None, "CIRCUIT_BREAKER_OPEN")
        c.require(
            self.active < self.operations.connections
            and self.reserved_bytes + self.reservation_bytes
            <= self.memory_capacity_bytes
            and now_ms >= self.next_admission_ms,
            "S12_ADMISSION_NOT_READY",
        )
        self.active += 1
        self.reserved_bytes += self.reservation_bytes
        self.next_admission_ms = now_ms + 1000 // self.operations.requests_per_second

    def finish(
        self,
        now_ms: int,
        outcome: str,
        elapsed_ms: int,
        *,
        status: int | None = None,
        parsed_after: int | None = None,
    ) -> None:
        c.require(self.active > 0, "S12_ADMISSION_ACCOUNTING_INVALID")
        self.active -= 1
        self.reserved_bytes -= self.reservation_bytes
        retryable = outcome == "TECHNICAL_FAILURE_RETRYABLE"
        self.consecutive = self.consecutive + 1 if retryable else 0
        self.recent.append((retryable, elapsed_ms))
        if status in (429, 503):
            self.overloads.append(now_ms)
        while self.overloads and self.overloads[0] < now_ms - 60_000:
            self.overloads.popleft()
        if retryable and status is not None and (status == 429 or status >= 500):
            self.next_admission_ms = max(
                self.next_admission_ms, now_ms + max(30_000, (parsed_after or 0) * 1000)
            )
        if outcome in (
            "CONTRACT_FAILURE",
            "DEPLOYMENT_IDENTITY_FAILURE",
            "TECHNICAL_FAILURE_FINAL",
        ):
            self.open_reason = "TERMINAL_FAILURE"
        elif self.consecutive >= 3 or sum(v[0] for v in self.recent) >= 5:
            self.open_reason = "TECHNICAL_ERROR_PRESSURE"
        elif len(self.overloads) >= 2:
            self.open_reason = "OVERLOAD_PRESSURE"
        elif len(self.recent) == 20 and sum(v[1] > 30_000 for v in self.recent) >= 10:
            self.open_reason = "LATENCY_PRESSURE"
        elif (
            parsed_after is not None
            and parsed_after * 1000 > self.operations.retry_after_ceiling_ms
        ):
            self.open_reason = "RETRY_AFTER_REQUIRES_OWNER_RECOVERY"


def remaining_attempts(ordinals: list[int], operations: Operations) -> int:
    """Begin receipts consume budget even when delivery/finish is unknown."""
    c.require(
        ordinals == list(range(1, len(ordinals) + 1))
        and len(ordinals) <= operations.max_attempts,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    return operations.max_attempts - len(ordinals)

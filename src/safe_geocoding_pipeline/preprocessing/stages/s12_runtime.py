"""Bounded execution primitive shared by synthetic orchestration and future jobs.

No protected input reader or DEVELOPMENT launch command is exposed here.
Deployment verification, authorization and campaign closure remain mandatory
caller gates; a successful HTTP call alone cannot publish a dataset.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import s12_operations as ops
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_transport as transport


@dataclass(frozen=True)
class Result:
    outcome: str
    reason: str
    checkpoint: Path | None
    attempts: int
    candidates: int | None


def begin_row(
    binding: Mapping[str, str], ordinal: int, identity_receipt: bytes, now: datetime
) -> dict[str, Any]:
    execution = bytes.fromhex(binding["request_execution_id"])
    campaign = bytes.fromhex(binding["campaign_id"])
    row: dict[str, Any] = {name: None for name in c.columns("request_attempt")}
    row.update(
        {
            "attempt_id": c.attempt_id(execution, campaign, ordinal),
            "request_execution_id": execution,
            "campaign_id": campaign,
            "attempt_number": ordinal,
            "campaign_start_sha256": bytes.fromhex(binding["campaign_start_sha256"]),
            "operations_policy_sha256": bytes.fromhex(
                binding["operations_policy_sha256"]
            ),
            "started_utc": now,
            "outcome": "UNKNOWN_DELIVERY",
            "reason_code": "UNKNOWN_DELIVERY",
            "received_body_bytes": 0,
            "identity_verification_receipt_sha256": c.digest(identity_receipt),
            "response_validation_contract_sha256": bytes.fromhex(
                binding["response_validation_contract_sha256"]
            ),
        }
    )
    c.row_bytes("request_attempt", row)
    return row


def execute_one(
    root: Path,
    binding: Mapping[str, str],
    target: bytes,
    *,
    size: int,
    operations: ops.Operations,
    admission: ops.Admission,
    dispatch: Callable[[bytes], transport.Capture],
    verify_identity: Callable[[], bytes],
    extract: Callable[[bytes, dict[str, Any]], response.Projection],
    clock_ms: Callable[[], int],
    wait_ms: Callable[[int], None],
    now_utc: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    previous_attempts: int = 0,
) -> Result:
    """Each dispatch has durable begin evidence; retry ceilings never reset.

    `previous_attempts` is derived from verified immutable begin/finish history
    by campaign reconciliation. A new segment cannot infer it from cache hits.
    No automatic resubmission, breaker recovery or attempt after durable success.
    """
    io.validate_binding(binding)
    operations.validate()
    c.require(
        binding["operations_policy_sha256"] == operations.fingerprint().hex(),
        "S12_OPERATIONS_INVALID",
    )
    c.require(
        type(previous_attempts) is int
        and 0 <= previous_attempts <= operations.max_attempts,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    c.require(
        c.policy(size)["retrieval_policy_id"].hex() == binding["retrieval_policy_id"],
        "S12_POLICY_INVALID",
    )
    if previous_attempts == operations.max_attempts:
        return Result(
            "TECHNICAL_FAILURE_FINAL",
            "RETRY_BUDGET_EXHAUSTED",
            None,
            previous_attempts,
            None,
        )
    execution = bytes.fromhex(binding["request_execution_id"])
    for ordinal in range(previous_attempts + 1, operations.max_attempts + 1):
        c.require(admission.open_reason is None, "CIRCUIT_BREAKER_OPEN")
        wait_ms(max(0, admission.next_admission_ms - clock_ms()))
        receipt = verify_identity()
        attempt = begin_row(binding, ordinal, receipt, now_utc())
        unit = root / (execution.hex() + f"_{ordinal:02d}")
        io.begin(unit, binding, attempt)
        admission.admit(clock_ms())
        try:
            captured = dispatch(target)
            raw = captured.payload
            outcome, reason = captured.outcome, captured.reason
            candidates: list[dict[str, Any]] = []
            capture = None
            if raw is not None:
                capture = {
                    "request_execution_id": execution.hex(),
                    "request_target_sha256": c.sha(b"GET\0" + target).hex(),
                    "http_status": captured.status,
                    "content_type": captured.content_type,
                    "content_encoding": captured.content_encoding,
                    "payload_complete": True,
                    "response_bytes": len(raw),
                    "response_sha256": c.sha(raw).hex(),
                }
                try:
                    # A second check covers the response interval; identity failure
                    # remains a campaign quarantine, never a contract/zero response.
                    verify_identity()
                except c.Stage12Error:
                    outcome, reason = (
                        "DEPLOYMENT_IDENTITY_FAILURE",
                        "IDENTITY_UNVERIFIABLE",
                    )
                else:
                    try:
                        projected = extract(raw, capture)
                        outcome, reason = projected.outcome, "OK"
                        candidates = list(projected.candidates)
                    except c.Stage12Error:
                        outcome, reason = (
                            "CONTRACT_FAILURE",
                            "RESPONSE_CONTRACT_INVALID",
                        )
            delay = None
            if outcome == "TECHNICAL_FAILURE_RETRYABLE":
                if ordinal == operations.max_attempts:
                    # The attempt remains retryable in audit; final exhaustion is
                    # the execution result, not a forged non-retryable HTTP event.
                    pass
                else:
                    try:
                        delay = ops.retry_delay(
                            execution,
                            ordinal + 1,
                            captured.retry_after_seconds,
                            operations,
                        )
                    except c.Stage12Error:
                        admission.open_reason = "RETRY_AFTER_REQUIRES_OWNER_RECOVERY"
            attempt.update(
                {
                    "finished_utc": now_utc(),
                    "elapsed_ms": captured.elapsed_ms,
                    "http_status": captured.status,
                    "outcome": outcome,
                    "reason_code": reason,
                    "received_body_bytes": captured.received_body_bytes,
                    "application_payload_bytes": len(raw) if raw is not None else None,
                    "content_type": captured.content_type,
                    "content_encoding": captured.content_encoding,
                    "retry_delay_ms": delay,
                    "retry_after_seconds": captured.retry_after_seconds,
                    "response_sha256": c.sha(raw) if raw is not None else None,
                }
            )
            # Identity failures retain prior raw audit but cannot become adoptable
            # success checkpoints. Their failure receipt remains unsealed here.
            if outcome == "DEPLOYMENT_IDENTITY_FAILURE":
                if raw is not None:
                    io.write(unit / "quarantined_raw.zst", response.compress(raw))
                io.write(
                    unit / "failure.parquet",
                    io.parquet_bytes("request_attempt", [attempt]),
                )
            else:
                io.finish(
                    unit,
                    attempt,
                    capture,
                    raw,
                    candidates,
                    reopen=extract,
                    retry_after_audit=captured.retry_after_audit.audit()
                    if captured.retry_after_audit
                    else None,
                )
        except BaseException:
            # Release the global reservation without masking the primary fault.
            try:
                admission.finish(clock_ms(), "TECHNICAL_FAILURE_FINAL", 0)
            except BaseException:
                pass
            raise
        admission.finish(
            clock_ms(),
            outcome,
            captured.elapsed_ms,
            status=captured.status,
            parsed_after=captured.retry_after_seconds,
        )
        if outcome in c.SUCCESS:
            return Result(outcome, "OK", unit, ordinal, len(candidates))
        if (
            outcome != "TECHNICAL_FAILURE_RETRYABLE"
            or admission.open_reason is not None
        ):
            return Result(outcome, admission.open_reason or reason, None, ordinal, None)
        if delay is not None:
            wait_ms(delay)
    return Result(
        "TECHNICAL_FAILURE_FINAL",
        "RETRY_BUDGET_EXHAUSTED",
        None,
        operations.max_attempts,
        None,
    )

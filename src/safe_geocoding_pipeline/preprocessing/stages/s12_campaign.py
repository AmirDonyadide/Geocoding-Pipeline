"""Immutable campaign start and explicitly authorized sequential job segments."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from . import s12_retrieval_contract as c
from . import s12_storage as io

VERSION = "stage12_campaign_provenance_v1"
START_KEYS = tuple(
    """
campaign_version campaign_id executable_sha runtime_inventory_sha256 operations_policy_sha256
authorization_sha256 workload_sha256 stage11_input_binding_sha256 materialization_contract_sha256
retrieval_policy_id pelias_deployment_fingerprint index_data_identity effective_behavior_id
response_validation_contract_sha256 response_extraction_contract_sha256 candidate_schema_sha256
""".split()
)


def validate_start(start: Mapping[str, Any]) -> None:
    c.require(
        set(start) == set(START_KEYS) and start["campaign_version"] == VERSION,
        "S12_CAMPAIGN_INVALID",
    )
    for key, value in start.items():
        if key == "campaign_version":
            continue
        c.require(
            type(value) is str
            and re.fullmatch(
                "[0-9a-f]{40}" if key == "executable_sha" else "[0-9a-f]{64}", value
            )
            is not None,
            "S12_CAMPAIGN_INVALID",
        )


def create(root: Path, provenance: Mapping[str, Any]) -> dict[str, Any]:
    c.require(
        set(provenance) == set(START_KEYS) - {"campaign_id", "campaign_version"},
        "S12_CAMPAIGN_INVALID",
    )
    start = {
        "campaign_version": VERSION,
        "campaign_id": os.urandom(32).hex(),
        **provenance,
    }
    validate_start(start)
    io.reserve(root)
    io.write(root / "start.json", c.canonical(start))
    io.write(root / "_START_SEALED", b"")
    reopen(root, start)
    return start


def reopen(root: Path, expected: Mapping[str, Any]) -> bytes:
    validate_start(expected)
    c.require(io.read(root / "_START_SEALED", limit=0) == b"", "S12_CAMPAIGN_INVALID")
    raw = io.read(root / "start.json")
    c.require(raw == c.canonical(dict(expected)), "S12_CAMPAIGN_BINDING_MISMATCH")
    return c.sha(raw)


def open_segment(
    root: Path,
    expected_start: Mapping[str, Any],
    *,
    ordinal: int,
    job_id: str,
    authorization: bytes,
    predecessor_sha256: bytes | None,
    preverification_sha256: bytes,
) -> Path:
    start_hash = reopen(root, expected_start)
    c.require(
        type(ordinal) is int
        and 1 <= ordinal <= 999999
        and type(job_id) is str
        and re.fullmatch(r"[0-9]+", job_id) is not None,
        "S12_SEGMENT_INVALID",
    )
    # A prior open/crashed segment requires separate recovery/closure evidence;
    # its mere absence from the scheduler never grants takeover.
    if ordinal > 1:
        previous = root / f"segment_{ordinal - 1:06d}"
        c.require(
            io.read(previous / "_CLOSED", limit=0) == b"", "S12_PREDECESSOR_NOT_CLOSED"
        )
        c.require(
            c.sha(io.read(previous / "closure.json")) == c.digest(predecessor_sha256),
            "S12_SEGMENT_CHAIN_INVALID",
        )
    else:
        c.require(predecessor_sha256 is None, "S12_SEGMENT_CHAIN_INVALID")
    segment = root / f"segment_{ordinal:06d}"
    io.reserve(segment)
    io.write(
        segment / "admission.json",
        c.canonical(
            {
                "campaign_start_sha256": start_hash.hex(),
                "ordinal": ordinal,
                "job_id": job_id,
                "authorization_sha256": c.digest(authorization).hex(),
                "predecessor_sha256": predecessor_sha256.hex()
                if predecessor_sha256
                else None,
                "preverification_sha256": c.digest(preverification_sha256).hex(),
            }
        ),
    )
    io.reserve(segment / "attempts")
    return segment


def close_segment(
    segment: Path,
    *,
    postverification_sha256: bytes,
    attempt_inventory_sha256: bytes,
    planned: int,
    completed: int,
    failed: int,
    unprocessed: int,
) -> bytes:
    c.require(
        all(
            type(v) is int and v >= 0 for v in (planned, completed, failed, unprocessed)
        )
        and planned == completed + failed + unprocessed,
        "S12_TOTALITY_INVALID",
    )
    raw = c.canonical(
        {
            "admission_sha256": c.sha(io.read(segment / "admission.json")).hex(),
            "postverification_sha256": c.digest(postverification_sha256).hex(),
            "attempt_inventory_sha256": c.digest(attempt_inventory_sha256).hex(),
            "planned": planned,
            "completed": completed,
            "failed": failed,
            "unprocessed": unprocessed,
        }
    )
    io.write(segment / "closure.json", raw)
    c.require(io.read(segment / "closure.json") == raw, "S12_SEGMENT_CHAIN_INVALID")
    io.write(segment / "_CLOSED", b"")
    return c.sha(raw)


def checkpoint_binding(
    start: Mapping[str, Any], execution: Mapping[str, Any]
) -> dict[str, str]:
    validate_start(start)
    result: dict[str, str] = {
        key: str(start[key]) for key in io.BINDING_KEYS if key in start
    }
    result["campaign_start_sha256"] = c.sha(c.canonical(dict(start))).hex()
    result.update(
        {key: c.digest(execution[key]).hex() for key in c.EXECUTION_FIELDS[1:]}
    )
    result["request_execution_id"] = c.execution_id(execution).hex()
    # Scientific execution must match every corresponding campaign binding.
    for key in c.EXECUTION_FIELDS[2:]:
        c.require(result[key] == start[key], "S12_CAMPAIGN_BINDING_MISMATCH")
    io.validate_binding(result)
    return result


def reconcile_attempts(
    attempt_rows: Iterable[Mapping[str, Any]],
    campaign: bytes,
    execution: bytes,
    *,
    ceiling: int = 5,
) -> tuple[int, bytes | None]:
    """Consume uncertain delivery, reject gaps/duplicates and conflicting successes."""
    c.require(type(ceiling) is int and 1 <= ceiling <= 5, "S12_ATTEMPT_BUDGET_INVALID")
    ordinal = 0
    selected: bytes | None = None
    stopped = False
    for row in attempt_rows:
        ordinal += 1
        c.require(
            ordinal <= ceiling
            and row["attempt_number"] == ordinal
            and row["campaign_id"] == campaign
            and row["request_execution_id"] == execution,
            "S12_ATTEMPT_HISTORY_INVALID",
        )
        c.require(
            row["attempt_id"] == c.attempt_id(execution, campaign, ordinal),
            "S12_ATTEMPT_HISTORY_INVALID",
        )
        c.require(selected is None, "S12_DISPATCH_AFTER_SUCCESS")
        c.require(not stopped, "S12_DISPATCH_AFTER_TERMINAL_FAILURE")
        c.require(row["outcome"] in c.OUTCOMES, "S12_ATTEMPT_HISTORY_INVALID")
        stopped = row["outcome"] in (
            "CONTRACT_FAILURE",
            "DEPLOYMENT_IDENTITY_FAILURE",
            "TECHNICAL_FAILURE_FINAL",
        )
        if row["outcome"] in c.SUCCESS:
            selected = c.digest(row["response_sha256"])
    return ceiling - ordinal, selected

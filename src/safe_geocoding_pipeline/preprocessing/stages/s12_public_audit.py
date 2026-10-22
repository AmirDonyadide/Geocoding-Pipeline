"""Prospective public-attempt audit; not a scientific checkpoint or projection.

Reuse the frozen exclusive-write/inventory/reopen/seal protocol without inventing
the deployment identities required by the scientific request_attempt relation.
No adoption, retry, network, secret provider or successor-validator interface.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import s12_assets as assets
from . import s12_probe as probe
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io

SCOPE = "PUBLIC_CAPABILITY_AUDIT_NOT_SCIENTIFIC_CHECKPOINT"
VALIDATION_SCOPE = "PUBLIC_SHAPE_ONLY_DEPLOYMENT_VOCABULARY_AND_ECHO_UNVERIFIED"
CONTEXT = (
    "runtime_inventory.json",
    "workload.json",
    "provenance.json",
    "public_fixtures.json",
    "response_validation.json",
    "request_materialization.json",
)
Validator = Callable[[bytes], tuple[Any, ...]]


class AuditWriteError(c.Stage12Error):
    """Static primary code survives a secondary durability failure."""


def initialize(root: Path) -> None:
    objects = assets.objects()
    io.write(root / "public_fixtures.json", c.canonical(probe.fixtures()))
    io.write(
        root / "response_validation.json", c.canonical(objects[response.VALIDATION])
    )
    io.write(
        root / "request_materialization.json", c.canonical(objects[c.MATERIALIZATION])
    )


def name_for(call: int, attempt: int) -> str:
    c.require(
        type(call) is int and call > 0 and type(attempt) is int and 1 <= attempt <= 5,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    return f"call_{call:04d}_attempt_{attempt}"


def begin(root: Path, request: dict[str, Any]) -> None:
    record = {
        **request,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "run_provenance_sha256": c.sha(io.read(root / "provenance.json")).hex(),
        "workload_sha256": c.sha(io.read(root / "workload.json")).hex(),
        "validation_version": response.VALIDATION,
        "response_validation_contract_sha256": c.sha(
            io.read(root / "response_validation.json")
        ).hex(),
        "materialization_contract_sha256": c.sha(
            io.read(root / "request_materialization.json")
        ).hex(),
        "validation_scope": VALIDATION_SCOPE,
    }
    io.write(
        root / (name_for(record["call"], record["attempt"]) + "_begin.json"),
        c.canonical(record),
    )


def _validate(
    raw: bytes, transport: dict[str, Any], size: int, validator: Validator
) -> tuple[str, str, tuple[Any, ...] | None]:
    try:
        # Same public v1 checks as the original harness. This does not attest
        # deployment vocabulary/echo checks or produce scientific candidates.
        c.require(transport["status"] == 200, "RESPONSE_CONTRACT_INVALID")
        features = validator(raw)
        c.require(
            len(features) <= size
            and transport["content_type"] in response.MEDIA
            and transport["content_encoding"] in ("absent", "identity"),
            "RESPONSE_CONTRACT_INVALID",
        )
        return c.SUCCESS[0] if features else c.SUCCESS[1], "OK", features
    except c.Stage12Error as error:
        return "CONTRACT_FAILURE", str(error), None


def _context(root: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(
        re.fullmatch(r"call_[0-9]{4,}_attempt_[1-5]", name) is not None,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    begin = io.metadata(io.read(root / (name + "_begin.json")))
    transport = io.metadata(io.read(root / (name + "_finish.json")))
    c.require(
        name == name_for(begin["call"], begin["attempt"])
        and (transport["call"], transport["attempt"])
        == (begin["call"], begin["attempt"])
        and begin["outcome"] == "UNKNOWN_DELIVERY",
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    for key, path in (
        ("run_provenance_sha256", "provenance.json"),
        ("workload_sha256", "workload.json"),
        ("response_validation_contract_sha256", "response_validation.json"),
        ("materialization_contract_sha256", "request_materialization.json"),
    ):
        c.require(
            begin[key] == c.sha(io.read(root / path)).hex(),
            "S12_CAPTURE_BINDING_INVALID",
        )
    objects = assets.objects()
    provenance = io.metadata(io.read(root / "provenance.json"))
    c.require(
        begin["validation_version"] == response.VALIDATION
        and begin["validation_scope"] == VALIDATION_SCOPE
        and io.read(root / "response_validation.json")
        == c.canonical(objects[response.VALIDATION])
        and io.read(root / "request_materialization.json")
        == c.canonical(objects[c.MATERIALIZATION])
        and io.read(root / "public_fixtures.json") == c.canonical(probe.fixtures()),
        "S12_CAPTURE_BINDING_INVALID",
    )
    c.require(
        provenance["submission_scope"] == "PUBLIC_SYNTHETIC_ONLY"
        and provenance["runtime_inventory_sha256"]
        == c.sha(io.read(root / "runtime_inventory.json")).hex(),
        "S12_CAPTURE_BINDING_INVALID",
    )
    plan = io.metadata(io.read(root / "workload.json"))
    calls = probe.planned_calls(plan)
    c.require(begin["call"] <= len(calls), "S12_CAPTURE_BINDING_INVALID")
    size, repetition, case = calls[begin["call"] - 1]
    _, target_hash = c.materialize(
        case["core"],
        bytes.fromhex(case["fixture_id"]),
        c.policy(size),
        target_limit=2**32,
    )
    c.require(
        (
            begin["size"],
            begin["repetition"],
            begin["fixture_id"],
            begin["request_target_sha256"],
        )
        == (size, repetition, case["fixture_id"], target_hash.hex()),
        "S12_CAPTURE_BINDING_INVALID",
    )
    return begin, transport


def complete(
    root: Path,
    name: str,
    raw: bytes | None,
    *,
    validator: Validator,
    privacy_rejected: bool = False,
    primary_failure_reason: str | None = None,
) -> tuple[dict[str, Any], tuple[Any, ...] | None]:
    """Return only after complete linked evidence is sealed and fully reopened.

    Unexpected exceptions/interruption leave an incomplete attempt. A known
    response/transport failure remains primary if its audit cannot be sealed.
    The caller supplies only an already-known sanitized transport failure;
    it cannot substitute for verified context or authorize completion.
    """
    try:
        begin, transport = _context(root, name)
    except Exception:
        if primary_failure_reason is not None:
            raise AuditWriteError(primary_failure_reason) from None
        raise
    outcome, reason = transport["outcome"], transport["reason"]
    features = None
    capture = None
    validation_performed = False
    if privacy_rejected:
        c.require(raw is None, "SECRET_ECHO_DETECTED")
        outcome, reason = "CONTRACT_FAILURE", "SECRET_ECHO_DETECTED"
    try:
        if raw is not None:
            c.require(
                transport["status"] is not None and 200 <= transport["status"] < 300,
                "S12_CAPTURE_BINDING_INVALID",
            )
            fingerprint = c.sha(raw)
            io.write(root / (name + ".zst"), response.compress(raw))
            decoded = response.decompress(
                io.read(root / (name + ".zst")),
                length=len(raw),
                expected_hash=fingerprint,
            )
            capture = {
                "raw_path": name + ".zst",
                "response_sha256": fingerprint.hex(),
                "application_payload_bytes": len(raw),
                "payload_complete": True,
                "http_status": transport["status"],
                "content_type": transport["content_type"],
                "content_encoding": transport["content_encoding"],
            }
        io.write(root / (name + "_capture.json"), c.canonical({"capture": capture}))
        if raw is not None:
            io.write(
                root / (name + "_validation_begin.json"),
                c.canonical(
                    {
                        "begin_sha256": c.sha(
                            io.read(root / (name + "_begin.json"))
                        ).hex(),
                        "response_validation_contract_sha256": begin[
                            "response_validation_contract_sha256"
                        ],
                        "response_sha256": c.sha(raw).hex(),
                    }
                ),
            )
            outcome, reason, features = _validate(
                decoded, transport, begin["size"], validator
            )
            validation_performed = True
        c.require(
            outcome in c.OUTCOMES and outcome != "UNKNOWN_DELIVERY",
            "S12_CAPTURE_INCOMPLETE",
        )
        terminal = {
            "scope": SCOPE,
            "call": begin["call"],
            "attempt": begin["attempt"],
            "run_provenance_sha256": begin["run_provenance_sha256"],
            "begin_sha256": c.sha(io.read(root / (name + "_begin.json"))).hex(),
            "transport_receipt_sha256": c.sha(
                io.read(root / (name + "_finish.json"))
            ).hex(),
            "response_validation_contract_sha256": begin[
                "response_validation_contract_sha256"
            ],
            "validation_version": response.VALIDATION,
            "validation_scope": VALIDATION_SCOPE,
            "validation_performed": validation_performed,
            "validation_outcome": outcome if validation_performed else None,
            "outcome": outcome,
            "reason_code": reason,
            "candidate_count": len(features) if features is not None else None,
            "response_sha256": capture["response_sha256"] if capture else None,
            "application_payload_bytes": capture["application_payload_bytes"]
            if capture
            else None,
            "privacy_rejected": privacy_rejected,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
        }
        io.write(root / (name + "_validation.json"), c.canonical(terminal))
        names = [
            *CONTEXT,
            *(
                name + suffix
                for suffix in (
                    "_begin.json",
                    "_finish.json",
                    "_capture.json",
                    "_validation.json",
                )
            ),
        ]
        if raw is not None:
            names.extend([name + ".zst", name + "_validation_begin.json"])
        io.write(
            root / (name + "_receipt.json"),
            c.canonical(
                {
                    "receipt_version": c.ATTEMPT,
                    "scope": SCOPE,
                    "inventory": io.file_inventory(root, tuple(names)),
                }
            ),
        )
        reopen(root, name, validator=validator, sealed=False)
        io.write(root / (name + "_SEALED"), b"")
        reopen(root, name, validator=validator)
        return terminal, features
    except Exception:
        if outcome in c.OUTCOMES and outcome not in (*c.SUCCESS, "UNKNOWN_DELIVERY"):
            raise AuditWriteError(reason) from None
        raise AuditWriteError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED") from None


def reopen(
    root: Path, name: str, *, validator: Validator, sealed: bool = True
) -> dict[str, Any]:
    """Validate a public audit only; never adopt a checkpoint or publish rows."""
    begin, transport = _context(root, name)
    if sealed:
        c.require(
            io.read(root / (name + "_SEALED"), limit=0) == b"",
            "S12_CHECKPOINT_INCOMPLETE",
        )
    receipt = io.metadata(io.read(root / (name + "_receipt.json")))
    terminal = io.metadata(io.read(root / (name + "_validation.json")))
    capture = io.metadata(io.read(root / (name + "_capture.json")))["capture"]
    names = [
        *CONTEXT,
        *(
            name + suffix
            for suffix in (
                "_begin.json",
                "_finish.json",
                "_capture.json",
                "_validation.json",
            )
        ),
    ]
    if capture is not None:
        names.extend([name + ".zst", name + "_validation_begin.json"])
    c.require(
        receipt
        == {
            "receipt_version": c.ATTEMPT,
            "scope": SCOPE,
            "inventory": io.file_inventory(root, tuple(names)),
        },
        "S12_INVENTORY_INVALID",
    )
    for field, expected in {
        "scope": SCOPE,
        "call": begin["call"],
        "attempt": begin["attempt"],
        "run_provenance_sha256": begin["run_provenance_sha256"],
        "begin_sha256": c.sha(io.read(root / (name + "_begin.json"))).hex(),
        "transport_receipt_sha256": c.sha(
            io.read(root / (name + "_finish.json"))
        ).hex(),
        "response_validation_contract_sha256": begin[
            "response_validation_contract_sha256"
        ],
        "validation_version": response.VALIDATION,
        "validation_scope": VALIDATION_SCOPE,
    }.items():
        c.require(
            c.canonical(terminal[field]) == c.canonical(expected),
            "S12_CAPTURE_BINDING_INVALID",
        )
    c.require(type(terminal["privacy_rejected"]) is bool, "S12_CAPTURE_BINDING_INVALID")
    if capture is not None:
        c.require(
            capture["raw_path"] == name + ".zst"
            and capture["payload_complete"] is True
            and not terminal["privacy_rejected"],
            "S12_CAPTURE_BINDING_INVALID",
        )
        c.require(
            (
                capture["http_status"],
                capture["content_type"],
                capture["content_encoding"],
                capture["application_payload_bytes"],
            )
            == (
                transport["status"],
                transport["content_type"],
                transport["content_encoding"],
                transport["payload_bytes"],
            ),
            "S12_CAPTURE_BINDING_INVALID",
        )
        raw = response.decompress(
            io.read(root / capture["raw_path"]),
            length=capture["application_payload_bytes"],
            expected_hash=bytes.fromhex(capture["response_sha256"]),
        )
        c.require(
            io.metadata(io.read(root / (name + "_validation_begin.json")))
            == {
                "begin_sha256": terminal["begin_sha256"],
                "response_validation_contract_sha256": begin[
                    "response_validation_contract_sha256"
                ],
                "response_sha256": capture["response_sha256"],
            },
            "S12_CAPTURE_BINDING_INVALID",
        )
        outcome, reason, features = _validate(raw, transport, begin["size"], validator)
        expected = (
            True,
            outcome,
            outcome,
            reason,
            len(features) if features is not None else None,
            capture["response_sha256"],
            len(raw),
        )
    else:
        outcome, reason = (
            ("CONTRACT_FAILURE", "SECRET_ECHO_DETECTED")
            if terminal["privacy_rejected"]
            else (transport["outcome"], transport["reason"])
        )
        c.require(
            outcome in c.OUTCOMES and outcome not in (*c.SUCCESS, "UNKNOWN_DELIVERY"),
            "S12_CAPTURE_INCOMPLETE",
        )
        expected = (False, None, outcome, reason, None, None, None)
    c.require(
        c.canonical(
            tuple(
                terminal[k]
                for k in (
                    "validation_performed",
                    "validation_outcome",
                    "outcome",
                    "reason_code",
                    "candidate_count",
                    "response_sha256",
                    "application_payload_bytes",
                )
            )
        )
        == c.canonical(expected),
        "S12_CHECKPOINT_PROJECTION_MISMATCH",
    )
    return terminal

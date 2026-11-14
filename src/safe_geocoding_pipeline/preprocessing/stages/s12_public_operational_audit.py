"""O-r2 DATA context and distinct control receipts. No real control adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import s12_assets as assets
from . import s12_probe as probe
from . import s12_public_audit as audit
from . import s12_public_operations as o
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_transport as transport


def transport_record(
    work: dict[str, Any], attempt: int, capture: transport.Capture, finished_utc: str
) -> dict[str, Any]:
    return {
        "call": work["work_id"],
        "attempt": attempt,
        "status": capture.status,
        "outcome": capture.outcome,
        "reason": capture.reason,
        "content_type": capture.content_type,
        "content_encoding": capture.content_encoding,
        "elapsed_ms": capture.elapsed_ms,
        "finished_utc": finished_utc,
        "received_body_bytes": capture.received_body_bytes,
        "payload_bytes": len(capture.payload) if capture.payload is not None else None,
        "retry_after_seconds": capture.retry_after_seconds,
        "retry_clock": capture.retry_after_audit.audit()
        if capture.retry_after_audit
        else None,
    }


def validate_transport(record: dict[str, Any]) -> None:
    o.require(
        set(record)
        == set(
            "call attempt status outcome reason content_type content_encoding elapsed_ms finished_utc received_body_bytes payload_bytes retry_after_seconds retry_clock".split()
        )
    )
    for k in ("call", "attempt"):
        o.uint(record[k], True)
    o.require(record["attempt"] <= 5)
    for k in ("elapsed_ms", "received_body_bytes"):
        o.uint(record[k])
    for k in ("status", "payload_bytes", "retry_after_seconds"):
        if record[k] is not None:
            o.uint(record[k])
    o.require(record["status"] is None or 100 <= record["status"] <= 599)
    o.require(record["outcome"] in (*o.FAILURES, "VALIDATION_REQUIRED"))
    o.validate_type(record["reason"], "Reason")
    o.require(record["content_type"] in (*response.MEDIA, "ABSENT", "OTHER"))
    o.require(record["content_encoding"] in ("absent", "identity", "OTHER"))
    # UTC encoding preserves the baseline receipt; no mutation of old bytes.
    from datetime import datetime, timedelta

    try:
        stamp = datetime.fromisoformat(record["finished_utc"])
        o.require(stamp.utcoffset() == timedelta(0))
    except (ValueError, TypeError):
        o.require(False)
    clock = record["retry_clock"]
    if clock is not None:
        o.require(
            type(clock) is dict
            and set(clock)
            == {"seconds", "kind", "reference_clock", "response_date", "receipt_utc"}
        )
        o.require(clock["seconds"] == record["retry_after_seconds"])
        o.require(
            clock["kind"] in ("ABSENT", "MALFORMED", "DELTA_SECONDS", "HTTP_DATE")
        )
        o.require(
            clock["reference_clock"] in ("NONE", "RESPONSE_DATE", "CLIENT_RECEIPT_UTC")
        )
        o.require(clock["response_date"] in ("MISSING", "VALID", "UNUSABLE"))
        o.require(
            (clock["seconds"] is None) == (clock["kind"] in ("ABSENT", "MALFORMED"))
        )
        o.require(
            (clock["reference_clock"] != "NONE") == (clock["kind"] == "HTTP_DATE")
        )
        if clock["kind"] == "HTTP_DATE":
            o.require(
                (clock["reference_clock"] == "RESPONSE_DATE")
                == (clock["response_date"] == "VALID")
            )
        try:
            o.require(
                datetime.fromisoformat(clock["receipt_utc"]).utcoffset() == timedelta(0)
            )
        except (ValueError, TypeError):
            o.require(False)
    else:
        o.require(record["retry_after_seconds"] is None)


class DataContext:
    def __init__(self, validation=None):
        self.validation = validation
        if validation is not None:
            self.files = (*type(self).files, "public_limitation.json")

    files = (
        *audit.CONTEXT,
        "operations_profile.json",
        "campaign_start.json",
        "work.json",
    )

    def load(self, root: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
        from . import s12_public_operations as o

        version = io.metadata(io.read(root / "operations_profile.json")).get("schema_version")
        if version == "stage12_transport_operations_v3":
            from . import s12_public_sampling_contract as o
        elif version == "stage12_transport_operations_v4":
            from . import s12_wf_ap2_contract as o
        elif version == "stage12_transport_operations_ra_g1_v1":
            from . import s12_ra_g1_contract as o
        elif version == "stage12_transport_operations_rep_coverage_ra_g1_v1":
            from . import s12_ra_g1_rep_coverage_contract as o
        elif version == "stage12_transport_operations_rep_fair_service_ra_g1_v1":
            from . import s12_ra_g1_rep_fair_contract as o
        elif version == "stage12_transport_operations_rep_ack_queue_ra_g1_v1":
            from . import s12_ra_g1_rep_ack_contract as o
        profile = o.parse(io.read(root / "operations_profile.json"), o.PROFILE)
        plan = o.parse(io.read(root / "workload.json"), o.PLAN)
        start = o.parse(io.read(root / "campaign_start.json"), o.START)
        work = io.metadata(io.read(root / "work.json"))
        o.validate_type(work, "Work")
        o.validate_plan(plan, profile)
        o.require(
            work["kind"] == "DATA"
            and work["fixture_id"] == work["retry_spacing_key"]
            and work["recipe_id"] is None
        )
        o.require(
            start["profile_sha256"] == o.digest(profile)
            and start["plan_sha256"] == o.digest(plan)
        )
        block = plan["blocks"][work["block_id"] - 1]
        o.require(work["work_id"] in block["observation_ids"])
        begin = io.metadata(io.read(root / (name + "_begin.json")))
        record = io.metadata(io.read(root / (name + "_finish.json")))
        validate_transport(record)
        o.require(
            name == audit.name_for(work["work_id"], begin["attempt"])
            and record["call"] == begin["call"] == work["work_id"]
            and record["attempt"] == begin["attempt"]
        )
        o.require(begin["outcome"] == "UNKNOWN_DELIVERY")
        for key, filename in (
            ("run_provenance_sha256", "provenance.json"),
            ("workload_sha256", "workload.json"),
            ("response_validation_contract_sha256", "response_validation.json"),
            ("materialization_contract_sha256", "request_materialization.json"),
        ):
            o.require(begin[key] == c.sha(io.read(root / filename)).hex())
        objects = assets.objects()
        for filename, value in (
            ("public_fixtures.json", probe.fixtures()),
            (
                "response_validation.json",
                objects[response.VALIDATION]
                if self.validation is None
                else self.validation.descriptor(),
            ),
            ("request_materialization.json", objects[c.MATERIALIZATION]),
        ):
            o.require(io.read(root / filename) == c.canonical(value))
        provenance = io.metadata(io.read(root / "provenance.json"))
        o.require(
            provenance["submission_scope"] == o.SCOPE
            and provenance["campaign_start_sha256"] == o.digest(start)
        )
        o.require(
            provenance["runtime_inventory_sha256"]
            == start["runtime_inventory_sha256"]
            == c.sha(io.read(root / "runtime_inventory.json")).hex()
        )
        o.require(
            begin["validation_version"]
            == (
                response.VALIDATION
                if self.validation is None
                else self.validation.VERSION
            )
            and begin["validation_scope"]
            == (
                audit.VALIDATION_SCOPE
                if self.validation is None
                else self.validation.SCOPE
            )
        )
        fixture = next(
            (x for x in probe.fixtures() if x["fixture_id"] == work["fixture_id"]), None
        )
        o.require(fixture is not None and 1 <= work["result_limit"] <= 40)
        _, target_hash = c.materialize(
            fixture["core"],
            bytes.fromhex(work["fixture_id"]),
            c.policy(work["result_limit"]),
            target_limit=2**32,
        )
        o.require(
            (
                begin["size"],
                begin["repetition"],
                begin["fixture_id"],
                begin["request_target_sha256"],
            )
            == (
                work["result_limit"],
                work["repetition"],
                work["fixture_id"],
                target_hash.hex(),
            )
        )
        if self.validation is not None:
            self.validation.verify_limitation(root, work, record)
        return begin, record


def begin_data(
    root: Path,
    profile: dict[str, Any],
    plan: dict[str, Any],
    start: dict[str, Any],
    work: dict[str, Any],
    attempt: int,
    runtime: dict[str, Any],
    *,
    validation=None,
) -> str:
    o.require(
        work["kind"] == "DATA"
        and o.digest(runtime) == start["runtime_inventory_sha256"]
    )
    io.reserve(root)
    for filename, obj in (
        ("operations_profile.json", profile),
        ("workload.json", plan),
        ("campaign_start.json", start),
        ("work.json", work),
        ("runtime_inventory.json", runtime),
        (
            "provenance.json",
            {
                "submission_scope": o.SCOPE,
                "campaign_start_sha256": o.digest(start),
                "runtime_inventory_sha256": o.digest(runtime),
            },
        ),
    ):
        io.write(root / filename, c.canonical(obj))
    if validation is None:
        audit.initialize(root)
    else:
        for filename, value in (
            ("public_fixtures.json", probe.fixtures()),
            ("response_validation.json", validation.descriptor()),
            ("request_materialization.json", assets.objects()[c.MATERIALIZATION]),
        ):
            io.write(root / filename, c.canonical(value))
    fixture = next(x for x in probe.fixtures() if x["fixture_id"] == work["fixture_id"])
    _, target_hash = c.materialize(
        fixture["core"],
        bytes.fromhex(work["fixture_id"]),
        c.policy(work["result_limit"]),
        target_limit=2**32,
    )
    audit.begin(
        root,
        {
            "call": work["work_id"],
            "attempt": attempt,
            "size": work["result_limit"],
            "repetition": work["repetition"],
            "fixture_id": work["fixture_id"],
            "request_target_sha256": target_hash.hex(),
            "outcome": "UNKNOWN_DELIVERY",
        },
        validation_version=response.VALIDATION
        if validation is None
        else validation.VERSION,
        validation_scope=audit.VALIDATION_SCOPE
        if validation is None
        else validation.SCOPE,
    )
    raw = io.read(root / (audit.name_for(work["work_id"], attempt) + "_begin.json"))
    return c.sha(raw).hex()


def finish_data(
    root: Path,
    work: dict[str, Any],
    record: dict[str, Any],
    payload: bytes | None,
    *,
    key: bytes,
    validator: audit.Validator,
    validation=None,
) -> tuple[dict[str, Any], str]:
    validate_transport(record)
    name = audit.name_for(work["work_id"], record["attempt"])
    privacy = False
    if payload is not None:
        try:
            response.secret_guard(payload, key)
        except c.Stage12Error:
            privacy, payload = True, None
    path = root / (name + "_finish.json")
    if path.exists():
        o.require(io.read(path) == c.canonical(record))
    else:
        io.write(path, c.canonical(record))
    if validation is not None:
        io.write(
            root / "public_limitation.json",
            c.canonical(validation.limitation(payload, work)),
        )
    terminal, _ = audit.complete(
        root,
        name,
        payload,
        validator=validator,
        privacy_rejected=privacy,
        primary_failure_reason=record["reason"]
        if record["outcome"] in o.FAILURES
        else None,
        context=DataContext(validation),
    )
    return terminal, c.sha(io.read(root / (name + "_receipt.json"))).hex()


def begin_control(root: Path, begin: dict[str, Any]) -> str:
    o.validate(begin, o.CONTROL_BEGIN)
    o.require(begin["attempt"] <= 5)
    io.reserve(root)
    raw = c.canonical(begin)
    io.write(root / "begin.json", raw)
    o.require(io.read(root / "begin.json") == raw)
    return c.sha(raw).hex()


def control_result(
    record: dict[str, Any],
    payload: bytes | None,
    recipe: dict[str, Any],
    adapter: o.ControlAdapter,
    key: bytes | None,
    *,
    reopening: bool = False,
) -> tuple[str, str, str, bytes | None, bytes | None]:
    validate_transport(record)
    o.require(bool(key) or (reopening and key is None), "ENVIRONMENT_AUTH_MISSING")
    privacy = False
    if payload is not None and key is not None:
        try:
            response.secret_guard(payload, key)
        except c.Stage12Error:
            privacy, payload = True, None
    if privacy:
        return "FAILED", "CONTRACT_FAILURE", "SECRET_ECHO_DETECTED", None, None
    identity = recipe["purpose"] in ("IDENTITY_REFRESH", "IDENTITY_CLOSURE")
    if record["outcome"] != "VALIDATION_REQUIRED":
        return (
            (
                "FAILED",
                "DEPLOYMENT_IDENTITY_FAILURE",
                "IDENTITY_UNVERIFIABLE",
                payload,
                None,
            )
            if identity
            else ("NOT_PERFORMED", record["outcome"], record["reason"], payload, None)
        )
    try:
        o.require(
            payload is not None
            and record["status"] == 200
            and record["content_type"] in response.MEDIA
            and record["content_encoding"] in ("absent", "identity"),
            "RESPONSE_CONTRACT_INVALID",
        )
        verification = adapter.validate(recipe, payload)
        if key is not None:
            response.secret_guard(verification, key)
        io.metadata(verification)
    except c.Stage12Error as error:
        if str(error) == "SECRET_ECHO_DETECTED":
            return "FAILED", "CONTRACT_FAILURE", "SECRET_ECHO_DETECTED", None, None
        return (
            "FAILED",
            "DEPLOYMENT_IDENTITY_FAILURE" if identity else "CONTRACT_FAILURE",
            "IDENTITY_UNVERIFIABLE" if identity else "RESPONSE_CONTRACT_INVALID",
            payload,
            None,
        )
    return "VERIFIED", "CONTROL_SUCCESS", "OK", payload, verification


def finish_control(
    root: Path,
    record: dict[str, Any],
    payload: bytes | None,
    recipe: dict[str, Any],
    adapter: o.ControlAdapter,
    *,
    key: bytes,
) -> tuple[dict[str, Any], str]:
    begin = o.parse(io.read(root / "begin.json"), o.CONTROL_BEGIN)
    o.require(
        (record["call"], record["attempt"]) == (begin["work_id"], begin["attempt"])
        and begin["recipe_sha256"] == recipe["recipe_sha256"]
    )
    result, outcome, reason, safe, verification = control_result(
        record, payload, recipe, adapter, key
    )
    try:
        if (root / "transport.json").exists():
            o.require(io.read(root / "transport.json") == c.canonical(record))
        else:
            io.write(root / "transport.json", c.canonical(record))
        io.write(root / "recipe.json", c.canonical(recipe))
        raw_inventory = None
        if safe is not None:
            o.require(
                record["status"] is not None
                and 200 <= record["status"] < 300
                and record["payload_bytes"] == len(safe)
            )
            io.write(root / "raw.zst", response.compress(safe))
            raw_inventory = [
                {"path": "raw.zst", "sha256": c.sha(io.read(root / "raw.zst")).hex()}
            ]
            io.write(root / "raw_inventory.json", c.canonical(raw_inventory))
        if verification is not None:
            io.write(root / "verification.json", verification)
        finish = {
            "schema_version": o.CONTROL_FINISH,
            "begin_sha256": c.sha(io.read(root / "begin.json")).hex(),
            "transport_record_sha256": o.digest(record),
            "validation_contract_sha256": recipe["implementation_contract_sha256"],
            "validation_result": result,
            "verification_receipt_sha256": c.sha(verification).hex()
            if verification
            else None,
            "response_sha256": c.sha(safe).hex() if safe is not None else None,
            "application_payload_bytes": len(safe) if safe is not None else None,
            "raw_inventory_sha256": o.digest(raw_inventory)
            if raw_inventory is not None
            else None,
            "outcome": outcome,
            "reason": reason,
        }
        o.validate(finish, o.CONTROL_FINISH)
        io.write(root / "finish.json", c.canonical(finish))
        names = tuple(p.name for p in root.iterdir())
        io.write(
            root / "inventory.json",
            c.canonical({"inventory": io.file_inventory(root, names)}),
        )
        reopen_control(root, adapter, key=key, sealed=False)
        io.write(root / "_CONTROL_SEALED", b"")
        reopen_control(root, adapter, key=key)
        return finish, c.sha(io.read(root / "inventory.json")).hex()
    except Exception:
        raise audit.AuditWriteError(
            reason if outcome in o.FAILURES else "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED"
        ) from None


def reopen_control(
    root: Path, adapter: o.ControlAdapter, *, key: bytes | None, sealed: bool = True
) -> dict[str, Any]:
    # Capture always requires the actual runtime key. A sealed retrospective
    # reopening checks original bytes/receipt/validator again without accessing
    # credentials, matching DATA replay. No unsealed keyless publication.
    o.require(key is not None or sealed, "ENVIRONMENT_AUTH_MISSING")
    begin = o.parse(io.read(root / "begin.json"), o.CONTROL_BEGIN)
    finish = o.parse(io.read(root / "finish.json"), o.CONTROL_FINISH)
    record, recipe = (
        io.metadata(io.read(root / "transport.json")),
        io.metadata(io.read(root / "recipe.json")),
    )
    o.require(
        (record["call"], record["attempt"]) == (begin["work_id"], begin["attempt"])
        and begin["recipe_sha256"] == recipe["recipe_sha256"]
    )
    o.require(
        finish["begin_sha256"] == o.digest(begin)
        and finish["transport_record_sha256"] == o.digest(record)
        and finish["validation_contract_sha256"]
        == recipe["implementation_contract_sha256"]
    )
    inventory = io.metadata(io.read(root / "inventory.json"))["inventory"]
    io.verify_inventory(
        root,
        inventory,
        extra={"inventory.json"} | ({"_CONTROL_SEALED"} if sealed else set()),
    )
    if sealed:
        o.require(io.read(root / "_CONTROL_SEALED", limit=0) == b"")
    raw = None
    if finish["response_sha256"] is not None:
        raw = response.decompress(
            io.read(root / "raw.zst"),
            length=finish["application_payload_bytes"],
            expected_hash=bytes.fromhex(finish["response_sha256"]),
        )
        expected = [
            {"path": "raw.zst", "sha256": c.sha(io.read(root / "raw.zst")).hex()}
        ]
        o.require(
            io.read(root / "raw_inventory.json") == c.canonical(expected)
            and finish["raw_inventory_sha256"] == o.digest(expected)
        )
        result, outcome, reason, _, verification = control_result(
            record, raw, recipe, adapter, key, reopening=True
        )
        o.require(
            (result, outcome, reason)
            == (finish["validation_result"], finish["outcome"], finish["reason"])
        )
        if verification is not None:
            o.require(
                io.read(root / "verification.json") == verification
                and finish["verification_receipt_sha256"] == c.sha(verification).hex()
            )
    else:
        o.require(
            finish["application_payload_bytes"]
            is finish["raw_inventory_sha256"]
            is finish["verification_receipt_sha256"]
            is None
            and finish["outcome"] != "CONTROL_SUCCESS"
        )
        if finish["reason"] != "SECRET_ECHO_DETECTED":
            result, outcome, reason, _, _ = control_result(
                record, None, recipe, adapter, key, reopening=True
            )
            o.require(
                (result, outcome, reason)
                == (finish["validation_result"], finish["outcome"], finish["reason"])
            )
    return finish

"""B2 DATA capture and distinct control evidence, with full receipt reopening."""

from __future__ import annotations

from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_public_operational_audit as oa
from . import s12_retrieval_contract as c
from . import s12_response as response
from . import s12_storage as io
from . import s12_assets as assets


def extract(raw, begin, record, work, *, layers, sources, expected_echo):
    return response.extract(
        raw,
        bytes.fromhex(begin["request_execution_id"]),
        size=work["result_limit"],
        http_status=record["status"],
        content_type=record["content_type"],
        encoding=record["content_encoding"],
        layers=layers,
        sources=sources,
        expected_echo=expected_echo(work),
        expected_hash=b.sha(raw),
    )


def begin(
    root: Path, work, ordinal, target, *, scientific_start, admission, epoch, now, core
):
    b.validate(scientific_start, "stage12_campaign_provenance_b2_v1")
    b.verify_executable_science(scientific_start)
    b.validate(admission, "stage12_segment_admission_b2_v1")
    o.validate_type(work, "Work")
    b.require(work["kind"] == "DATA", "B2_DATA_CONTROL_MIX")
    semantic = bytes.fromhex(work["query_semantic_id"])
    policy = c.policy(work["result_limit"])
    exact, _ = c.materialize(core, semantic, policy, target_limit=len(target))
    b.require(
        target == exact
        and admission["campaign_start_sha256"] == b.digest(scientific_start),
        "B2_REQUEST_BINDING",
    )
    execution = b.execution_id(
        semantic,
        policy["retrieval_policy_id"],
        bytes.fromhex(scientific_start["materialization_contract_sha256"]),
        bytes.fromhex(scientific_start["observation_binding_id"]),
        bytes.fromhex(scientific_start["campaign_id"]),
    )
    obj = {
        "schema_version": "stage12_data_begin_b2_v1",
        "campaign_start_sha256": b.digest(scientific_start),
        "work_sha256": b.digest(work),
        "request_execution_id": execution.hex(),
        "attempt_id": b.attempt_id(
            execution, bytes.fromhex(scientific_start["campaign_id"]), ordinal
        ).hex(),
        "attempt": ordinal,
        "request_target_sha256": b.sha(b"GET\0" + target).hex(),
        "segment_nonce": admission["segment_nonce"],
        "preflight_observation_sha256": admission["preflight_observation_sha256"],
        "epoch_id": epoch,
        "started_utc": now,
        "outcome": "UNKNOWN_DELIVERY",
    }
    b.validate(obj)
    io.reserve(root)
    for name, value in (
        ("begin.json", obj),
        ("work.json", work),
        ("core.json", core),
        ("scientific_start.json", scientific_start),
        ("segment_admission.json", admission),
    ):
        io.write(root / name, b.canonical(value))
    return b.digest(obj)


def context(root):
    begin = b.parse(io.read(root / "begin.json"), "stage12_data_begin_b2_v1")
    work = io.metadata(io.read(root / "work.json"))
    o.validate_type(work, "Work")
    start = b.parse(
        io.read(root / "scientific_start.json"), "stage12_campaign_provenance_b2_v1"
    )
    admission = b.parse(
        io.read(root / "segment_admission.json"), "stage12_segment_admission_b2_v1"
    )
    core = io.metadata(io.read(root / "core.json"))
    b.verify_executable_science(start)
    target, _ = c.materialize(
        core,
        bytes.fromhex(work["query_semantic_id"]),
        c.policy(work["result_limit"]),
        target_limit=2**32,
    )
    execution = b.execution_id(
        bytes.fromhex(work["query_semantic_id"]),
        c.policy(work["result_limit"])["retrieval_policy_id"],
        bytes.fromhex(start["materialization_contract_sha256"]),
        bytes.fromhex(start["observation_binding_id"]),
        bytes.fromhex(start["campaign_id"]),
    )
    b.require(
        work["kind"] == "DATA"
        and begin["work_sha256"] == b.digest(work)
        and begin["campaign_start_sha256"]
        == b.digest(start)
        == admission["campaign_start_sha256"]
        and begin["request_execution_id"] == execution.hex()
        and begin["attempt_id"]
        == b.attempt_id(
            execution, bytes.fromhex(start["campaign_id"]), begin["attempt"]
        ).hex()
        and begin["request_target_sha256"] == b.sha(b"GET\0" + target).hex(),
        "B2_REQUEST_BINDING",
    )
    for key in ("segment_nonce", "preflight_observation_sha256", "epoch_id"):
        b.require(begin[key] == admission[key], "B2_SEGMENT_BINDING")
    return begin, work, start, admission


def finish(root, record, raw, *, key: bytes, layers, sources, expected_echo, now):
    begin, work, start, _ = context(root)
    oa.validate_transport(record)
    b.require(
        record["call"] == work["work_id"] and record["attempt"] == begin["attempt"],
        "B2_TRANSPORT_ASSOCIATION",
    )
    b.require(
        io.read(root / "transport.json") == b.canonical(record),
        "B2_TRANSPORT_ASSOCIATION",
    )
    outcome, reason = record["outcome"], record["reason"]
    projection = None
    privacy = False
    if raw is not None:
        b.require(
            len(raw) == record["payload_bytes"] and len(raw) <= response.MAX_BODY,
            "B2_CAPTURE_LENGTH",
        )
        try:
            response.secret_guard(raw, key)
        except c.Stage12Error:
            raw = None
            outcome, reason, privacy = "CONTRACT_FAILURE", "SECRET_ECHO_DETECTED", True
    response_hash = response_bytes = None
    if raw is not None:
        b.require(
            record["status"] is not None and 200 <= record["status"] < 300,
            "B2_CAPTURE_STATUS",
        )
        response_hash, response_bytes = b.sha(raw).hex(), len(raw)
        io.write(root / "raw.zst", response.compress(raw))
        decoded = response.decompress(
            io.read(root / "raw.zst"),
            length=response_bytes,
            expected_hash=bytes.fromhex(response_hash),
        )
        try:
            projection = extract(
                decoded,
                begin,
                record,
                work,
                layers=layers,
                sources=sources,
                expected_echo=expected_echo,
            )
            outcome, reason = projection.outcome, "OK"
        except c.Stage12Error:
            outcome, reason = "CONTRACT_FAILURE", "RESPONSE_CONTRACT_INVALID"
    b.require(
        outcome in b.TYPES["Outcome"]["enum"] and outcome not in ("UNKNOWN_DELIVERY",),
        "B2_CAPTURE_INCOMPLETE",
    )
    if projection is not None:
        sink = pa.BufferOutputStream()
        pq.write_table(
            pa.Table.from_pylist(
                projection.candidates, schema=b.schema("request_candidate")
            ),
            sink,
            compression="zstd",
        )
        io.write(root / "candidates.parquet", sink.getvalue().to_pybytes())
    receipt = {
        "schema_version": "stage12_data_receipt_b2_v1",
        "begin_sha256": b.digest(begin),
        "transport_sha256": b.digest(record),
        "request_execution_id": begin["request_execution_id"],
        "attempt_id": begin["attempt_id"],
        "outcome": outcome,
        "reason": reason,
        "response_sha256": response_hash,
        "response_bytes": response_bytes,
        "candidate_count": len(projection.candidates) if projection else None,
        "validation_sha256": assets.hashes()[response.VALIDATION].hex(),
        "extraction_sha256": start["response_extraction_contract_sha256"],
        "privacy_rejected": privacy,
        "finished_utc": now,
    }
    b.validate(receipt)
    io.write(root / "validation.json", b.canonical(receipt))
    names = tuple(sorted(p.name for p in root.iterdir()))
    io.write(
        root / "receipt.json",
        b.canonical(
            {
                "schema_version": "stage12_capture_inventory_b2_v1",
                "files": io.file_inventory(root, names),
            }
        ),
    )
    reopen(
        root, layers=layers, sources=sources, expected_echo=expected_echo, sealed=False
    )
    io.write(root / "_SEALED", b"")
    reopen(root, layers=layers, sources=sources, expected_echo=expected_echo)
    return receipt, b.sha(io.read(root / "receipt.json")).hex()


def reopen(root, *, layers, sources, expected_echo, sealed=True):
    begin, work, start, admission = context(root)
    inventory = io.metadata(io.read(root / "receipt.json"))
    b.require(
        set(inventory) == {"schema_version", "files"}
        and inventory["schema_version"] == "stage12_capture_inventory_b2_v1",
        "B2_RECEIPT_INVALID",
    )
    io.verify_inventory(
        root,
        inventory["files"],
        extra={"receipt.json", "_SEALED"} if sealed else {"receipt.json"},
    )
    if sealed:
        b.require(io.read(root / "_SEALED", limit=0) == b"", "B2_RECEIPT_UNSEALED")
    receipt = b.parse(io.read(root / "validation.json"), "stage12_data_receipt_b2_v1")
    record = io.metadata(io.read(root / "transport.json"))
    oa.validate_transport(record)
    b.require(
        receipt["begin_sha256"] == b.digest(begin)
        and receipt["transport_sha256"] == b.digest(record)
        and receipt["request_execution_id"] == begin["request_execution_id"]
        and receipt["attempt_id"] == begin["attempt_id"]
        and record["call"] == work["work_id"]
        and record["attempt"] == begin["attempt"],
        "B2_RECEIPT_ASSOCIATION",
    )
    b.require(
        receipt["validation_sha256"] == assets.hashes()[response.VALIDATION].hex()
        and receipt["extraction_sha256"]
        == start["response_extraction_contract_sha256"],
        "B2_VALIDATOR_MISMATCH",
    )
    raw = None
    projection = None
    if receipt["response_sha256"] is not None:
        b.require(
            not receipt["privacy_rejected"]
            and receipt["response_bytes"] is not None
            and receipt["response_bytes"] == record["payload_bytes"],
            "B2_CAPTURE_LENGTH",
        )
        raw = response.decompress(
            io.read(root / "raw.zst"),
            length=receipt["response_bytes"],
            expected_hash=bytes.fromhex(receipt["response_sha256"]),
        )
        try:
            projection = extract(
                raw,
                begin,
                record,
                work,
                layers=layers,
                sources=sources,
                expected_echo=expected_echo,
            )
        except c.Stage12Error:
            b.require(
                receipt["outcome"] == "CONTRACT_FAILURE"
                and receipt["reason"] == "RESPONSE_CONTRACT_INVALID",
                "B2_REPLAY_MISMATCH",
            )
    else:
        b.require(
            receipt["response_bytes"] is receipt["candidate_count"] is None,
            "B2_CAPTURE_LENGTH",
        )
    if projection is not None:
        b.require(
            receipt["outcome"] == projection.outcome
            and receipt["candidate_count"] == len(projection.candidates),
            "B2_REPLAY_MISMATCH",
        )
        table = pq.read_table(pa.BufferReader(io.read(root / "candidates.parquet")))
        b.require(
            table.schema.equals(b.schema("request_candidate"), check_metadata=True),
            "B2_REPLAY_MISMATCH",
        )
        actual = table.to_pylist()
        b.require(
            len(actual) == len(projection.candidates)
            and all(
                b.row_bytes("request_candidate", x)
                == b.row_bytes("request_candidate", y)
                for x, y in zip(actual, projection.candidates, strict=True)
            ),
            "B2_REPLAY_MISMATCH",
        )
    elif receipt["privacy_rejected"]:
        b.require(
            receipt["outcome"] == "CONTRACT_FAILURE"
            and receipt["reason"] == "SECRET_ECHO_DETECTED"
            and not (root / "raw.zst").exists(),
            "B2_PRIVACY_FAILURE",
        )
    elif raw is None:
        b.require(
            receipt["outcome"] == record["outcome"]
            and receipt["reason"] == record["reason"],
            "B2_REPLAY_MISMATCH",
        )
    return receipt, projection, raw


def begin_control(root, value):
    b.validate(value, o.CONTROL_BEGIN)
    io.reserve(root)
    io.write(root / "begin.json", b.canonical(value))
    return b.digest(value)


def control_timing(root, begin, recipe, record):
    value = io.metadata(io.read(root / "control_timing.json"))
    b.require(
        set(value)
        == {
            "schema_version",
            "begin_sha256",
            "epoch_id",
            "started_mono_ns",
            "completed_mono_ns",
            "max_duration_ms",
        }
        and value["schema_version"] == "stage12_control_timing_b2_v1"
        and value["begin_sha256"] == b.digest(begin)
        and value["max_duration_ms"] == recipe["max_duration_ms"],
        "B2_CONTROL_TIMING",
    )
    b.validate_type(value["epoch_id"], "D")
    for k in ("started_mono_ns", "completed_mono_ns", "max_duration_ms"):
        b.uint(value[k], k == "max_duration_ms")
    b.require(
        value["completed_mono_ns"] >= value["started_mono_ns"], "B2_CONTROL_TIMING"
    )
    return (
        value["completed_mono_ns"] - value["started_mono_ns"]
        > value["max_duration_ms"] * 1_000_000
        or record["elapsed_ms"] > value["max_duration_ms"]
    )


def finish_control(root, record, raw, recipe, adapter, *, key):
    """Control validation cannot produce geocoding candidates or service closure."""
    begin = b.parse(io.read(root / "begin.json"), o.CONTROL_BEGIN)
    oa.validate_transport(record)
    b.require(
        record["call"] == begin["work_id"]
        and record["attempt"] == begin["attempt"]
        and io.read(root / "transport.json") == b.canonical(record),
        "B2_CONTROL_ASSOCIATION",
    )
    late = control_timing(root, begin, recipe, record)
    outcome, reason = (
        ("CONTRACT_FAILURE", "TIMEOUT")
        if late
        else (record["outcome"], record["reason"])
    )
    verification = None
    response_hash = None
    raw_inventory = None
    length = None
    if raw is not None:
        b.require(
            len(raw) == record["payload_bytes"] and len(raw) <= response.MAX_BODY,
            "B2_CAPTURE_LENGTH",
        )
        try:
            response.secret_guard(raw, key)
        except c.Stage12Error:
            raw = None
            outcome, reason = "CONTRACT_FAILURE", "SECRET_ECHO_DETECTED"
    if raw is not None:
        b.require(
            record["status"] is not None and 200 <= record["status"] < 300,
            "B2_CAPTURE_STATUS",
        )
        response_hash = b.sha(raw).hex()
        length = len(raw)
        io.write(root / "raw.zst", response.compress(raw))
        try:
            if late:
                raise c.Stage12Error("TIMEOUT")
            verified = adapter.validate(recipe, raw)
            b.require(type(verified) is bytes, "B2_CONTROL_INVALID")
            io.write(root / "verification.json", verified)
            verification = b.sha(verified).hex()
            outcome, reason = "CONTROL_SUCCESS", "OK"
        except c.Stage12Error:
            outcome, reason = (
                "CONTRACT_FAILURE",
                "TIMEOUT" if late else "RESPONSE_CONTRACT_INVALID",
            )
        raw_inventory = b.digest(io.file_inventory(root, ("raw.zst",)))
    finish = {
        "schema_version": o.CONTROL_FINISH,
        "begin_sha256": b.digest(begin),
        "transport_record_sha256": b.digest(record),
        "validation_contract_sha256": recipe["implementation_contract_sha256"],
        "validation_result": "NOT_PERFORMED"
        if late
        else "VERIFIED"
        if verification
        else "FAILED"
        if raw is not None
        else "NOT_PERFORMED",
        "verification_receipt_sha256": verification,
        "response_sha256": response_hash,
        "application_payload_bytes": length,
        "raw_inventory_sha256": raw_inventory,
        "outcome": outcome,
        "reason": reason,
    }
    b.validate(finish)
    io.write(root / "finish.json", b.canonical(finish))
    io.write(
        root / "receipt.json",
        b.canonical(
            {
                "files": io.file_inventory(
                    root, tuple(sorted(p.name for p in root.iterdir()))
                )
            }
        ),
    )
    io.write(root / "_SEALED", b"")
    reopen_control(root, recipe, adapter)
    return finish, b.sha(io.read(root / "receipt.json")).hex()


def reopen_control(root, recipe, adapter):
    begin = b.parse(io.read(root / "begin.json"), o.CONTROL_BEGIN)
    finish = b.parse(io.read(root / "finish.json"), o.CONTROL_FINISH)
    io.verify_inventory(
        root,
        io.metadata(io.read(root / "receipt.json"))["files"],
        extra={"receipt.json", "_SEALED"},
    )
    b.require(io.read(root / "_SEALED", limit=0) == b"", "B2_RECEIPT_UNSEALED")
    record = io.metadata(io.read(root / "transport.json"))
    oa.validate_transport(record)
    b.require(
        finish["begin_sha256"] == b.digest(begin)
        and finish["transport_record_sha256"] == b.digest(record)
        and begin["recipe_sha256"] == recipe["recipe_sha256"]
        and finish["validation_contract_sha256"]
        == recipe["implementation_contract_sha256"]
        and record["call"] == begin["work_id"]
        and record["attempt"] == begin["attempt"],
        "B2_CONTROL_ASSOCIATION",
    )
    late = control_timing(root, begin, recipe, record)
    if finish["response_sha256"] is not None:
        b.require(
            finish["application_payload_bytes"] == record["payload_bytes"]
            and finish["raw_inventory_sha256"]
            == b.digest(io.file_inventory(root, ("raw.zst",))),
            "B2_CAPTURE_LENGTH",
        )
        raw = response.decompress(
            io.read(root / "raw.zst"),
            length=finish["application_payload_bytes"],
            expected_hash=bytes.fromhex(finish["response_sha256"]),
        )
        if late:
            b.require(
                finish["outcome"] == "CONTRACT_FAILURE"
                and finish["reason"] == "TIMEOUT"
                and finish["validation_result"] == "NOT_PERFORMED"
                and finish["verification_receipt_sha256"] is None
                and not (root / "verification.json").exists(),
                "B2_CONTROL_REPLAY",
            )
            return finish
        try:
            verified = adapter.validate(recipe, raw)
        except c.Stage12Error:
            b.require(
                finish["outcome"] == "CONTRACT_FAILURE"
                and finish["reason"] == "RESPONSE_CONTRACT_INVALID"
                and finish["validation_result"] == "FAILED"
                and finish["verification_receipt_sha256"] is None,
                "B2_CONTROL_REPLAY",
            )
        else:
            b.require(
                type(verified) is bytes
                and finish["outcome"] == "CONTROL_SUCCESS"
                and finish["validation_result"] == "VERIFIED"
                and verified == io.read(root / "verification.json")
                and b.sha(verified).hex() == finish["verification_receipt_sha256"],
                "B2_CONTROL_REPLAY",
            )
    else:
        b.require(
            finish["application_payload_bytes"]
            is finish["raw_inventory_sha256"]
            is finish["verification_receipt_sha256"]
            is None
            and finish["validation_result"] == "NOT_PERFORMED"
            and not (root / "raw.zst").exists(),
            "B2_CONTROL_REPLAY",
        )
        b.require(
            (finish["outcome"], finish["reason"])
            in (
                (record["outcome"], record["reason"]),
                ("CONTRACT_FAILURE", "SECRET_ECHO_DETECTED"),
                *(([("CONTRACT_FAILURE", "TIMEOUT")]) if late else []),
            ),
            "B2_CONTROL_REPLAY",
        )
    return finish


def report_control(root, recipe, adapter):
    terminal = reopen_control(root, recipe, adapter)
    return {
        **terminal,
        "_control_timing": io.metadata(io.read(root / "control_timing.json")),
    }

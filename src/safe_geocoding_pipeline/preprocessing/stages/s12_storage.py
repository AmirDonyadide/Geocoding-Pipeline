"""Exclusive immutable attempt/checkpoint fragments with mandatory full reopen."""

from __future__ import annotations

import json
import os
import re
import stat
import threading
from contextlib import contextmanager
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_publication as accepted
from . import s12_response as response
from . import s12_retrieval_contract as c

CHECKPOINT_SEAL = "_SEALED"
_checkpoints = threading.local()


@contextmanager
def cooperative_io(callback: Callable[[], None]) -> Iterator[None]:
    """Opt-in sole-writer safe points; never interrupt a partially written file.

    The callback may persist a pending resource sample, not another audit or
    controller mutation. It is disabled recursively and absent in legacy paths.
    """
    previous = getattr(_checkpoints, "callback", None)
    _checkpoints.callback = callback
    try:
        yield
    finally:
        _checkpoints.callback = previous


@contextmanager
def charged_writes(callback: Callable[[Path, int], None]) -> Iterator[None]:
    """Opt-in conservative byte reservation BEFORE exclusive writes.

    Thread-local, sole-writer only. Failed/partial writes retain the full charge.
    Legacy/B2 callers without this context retain their exact existing behavior.
    """
    previous = getattr(_checkpoints, "charge", None)
    _checkpoints.charge = callback
    try:
        yield
    finally:
        _checkpoints.charge = previous


def charge_write(path: Path, size: int) -> None:
    callback = getattr(_checkpoints, "charge", None)
    if callback is not None:
        callback(path, size)


def _checkpoint() -> None:
    callback = getattr(_checkpoints, "callback", None)
    if callback is not None:
        _checkpoints.callback = None
        try:
            callback()
        finally:
            _checkpoints.callback = callback


BINDING_KEYS = tuple(
    """
request_execution_id query_semantic_id retrieval_policy_id materialization_contract_sha256
pelias_deployment_fingerprint index_data_identity effective_behavior_id
stage11_input_binding_sha256 executable_sha runtime_inventory_sha256 operations_policy_sha256
campaign_id campaign_start_sha256 authorization_sha256 response_validation_contract_sha256
response_extraction_contract_sha256 candidate_schema_sha256
""".split()
)


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path: Path) -> None:
    accepted.check_parent(path / "unit")


def reserve(path: Path) -> None:
    accepted.check_parent(path)
    path.mkdir(mode=0o700)
    fsync_directory(path.parent)
    _checkpoint()


def write(path: Path, raw: bytes) -> None:
    charge_write(path, len(raw))
    private_directory(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(path.parent)
    _checkpoint()


def has_read_view() -> bool:
    return getattr(_checkpoints, "read_view", None) is not None


@contextmanager
def read_view(view) -> Iterator[None]:
    """Default-off coordinator hook; original private reads remain the authority."""
    c.require(not has_read_view(), "S12_PUBLIC_SOURCE_CHANGED")
    _checkpoints.read_view = view
    try:
        yield
    finally:
        _checkpoints.read_view = None


def record_read_output(path: Path, digest: str) -> None:
    view = getattr(_checkpoints, "read_view", None)
    if view is not None:
        view.output(path, digest)


def read(path: Path, *, limit: int = 64 * 1024 * 1024) -> bytes:
    view = getattr(_checkpoints, "read_view", None)
    if view is not None:
        return view.read(path, limit=limit, original=original_read)
    return original_read(path, limit=limit)


@contextmanager
def public_originals(reader):
    """Explicit public validation scope; default shared reader unchanged."""
    c.require(
        getattr(_checkpoints, "original_view", None) is None,
        "S12_PUBLIC_SOURCE_CHANGED",
    )
    _checkpoints.original_view = reader
    try:
        yield
    finally:
        _checkpoints.original_view = None


def public_original_reader():
    return getattr(_checkpoints, "original_view", None)


def original_read(path: Path, *, limit: int = 64 * 1024 * 1024) -> bytes:
    reader = public_original_reader()
    if reader is not None and reader.contains(path):
        return reader.read(path, limit=limit)
    private_directory(path.parent)
    try:
        raw = accepted.read_private(path, limit=limit)
    except Exception:
        raise c.Stage12Error("S12_PRIVATE_FILE_INVALID") from None
    _checkpoint()
    return raw


def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for k, v in items:
        c.require(k not in result, "S12_METADATA_INVALID")
        result[k] = v
    return result


def metadata(raw: bytes) -> dict[str, Any]:
    try:
        obj = json.loads(raw, object_pairs_hook=pairs)
        c.require(type(obj) is dict and c.canonical(obj) == raw, "S12_METADATA_INVALID")
        return dict(obj)
    except (ValueError, UnicodeError):
        raise c.Stage12Error("S12_METADATA_INVALID") from None


def validate_binding(binding: Mapping[str, Any]) -> None:
    c.require(set(binding) == set(BINDING_KEYS), "S12_CHECKPOINT_BINDING_INVALID")
    for k, v in binding.items():
        c.require(
            type(v) is str
            and re.fullmatch(
                "[0-9a-f]{40}" if k == "executable_sha" else "[0-9a-f]{64}", v
            )
            is not None,
            "S12_CHECKPOINT_BINDING_INVALID",
        )
    scientific = {
        k: c.IDENTITY if k == "identity_version" else bytes.fromhex(binding[k])
        for k in c.EXECUTION_FIELDS
    }
    c.require(
        c.execution_id(scientific).hex() == binding["request_execution_id"],
        "S12_EXECUTION_BINDING_INVALID",
    )


def parquet_bytes(relation: str, rows: list[dict[str, Any]]) -> bytes:
    for row in rows:
        c.row_bytes(relation, row)
    output = pa.BufferOutputStream()
    pq.write_table(
        pa.Table.from_pylist(rows, schema=c.schema(relation)),
        output,
        compression="zstd",
        compression_level=3,
    )
    return bytes(output.getvalue())


def read_rows(raw: bytes, relation: str) -> list[dict[str, Any]]:
    try:
        table = pq.read_table(pa.BufferReader(raw))
        c.require(table.schema.equals(c.schema(relation)), "S12_SCHEMA_INVALID")
        rows = table.to_pylist()
        for row in rows:
            c.row_bytes(relation, row)
        return list(rows)
    except c.Stage12Error:
        raise
    except Exception:
        raise c.Stage12Error("S12_PARQUET_INVALID") from None


def file_inventory(root: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {"path": name, "bytes": len(raw), "sha256": c.sha(raw).hex()}
        for name in sorted(names)
        for raw in (read(root / name),)
    ]


def verify_inventory(
    root: Path, inventory: list[dict[str, Any]], *, extra: set[str]
) -> None:
    c.require(type(inventory) is list, "S12_INVENTORY_INVALID")
    names = []
    for item in inventory:
        c.require(
            type(item) is dict and set(item) == {"path", "bytes", "sha256"},
            "S12_INVENTORY_INVALID",
        )
        name = item["path"]
        c.require(
            type(name) is str
            and re.fullmatch(
                r"[a-zA-Z0-9_][a-zA-Z0-9_.-]*(?:/[a-zA-Z0-9_][a-zA-Z0-9_.-]*)*", name
            )
            is not None
            and name not in names,
            "S12_INVENTORY_INVALID",
        )
        raw = read(root / name)
        c.require(
            len(raw) == item["bytes"] and c.sha(raw).hex() == item["sha256"],
            "S12_INVENTORY_INVALID",
        )
        names.append(name)
    expected_files = set(names) | extra
    expected_dirs = {
        str(parent)
        for name in expected_files
        for parent in Path(name).parents
        if str(parent) != "."
    }
    actual_files, actual_dirs = set(), set()
    for path in root.rglob("*"):
        relative = str(path.relative_to(root))
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            private_directory(path)
            actual_dirs.add(relative)
        else:
            c.require(stat.S_ISREG(mode), "S12_PRIVATE_FILE_INVALID")
            actual_files.add(relative)
    c.require(
        actual_files == expected_files and actual_dirs == expected_dirs,
        "S12_INVENTORY_INVALID",
    )


IMMUTABLE_ATTEMPT_FIELDS = (
    "attempt_id",
    "request_execution_id",
    "campaign_id",
    "attempt_number",
    "campaign_start_sha256",
    "operations_policy_sha256",
    "started_utc",
    "identity_verification_receipt_sha256",
    "response_validation_contract_sha256",
)


def validate_begin(binding: Mapping[str, Any], attempt: Mapping[str, Any]) -> None:
    c.row_bytes("request_attempt", attempt)
    c.require(
        attempt["outcome"] == "UNKNOWN_DELIVERY" and attempt["finished_utc"] is None,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    for field in (
        "request_execution_id",
        "campaign_id",
        "campaign_start_sha256",
        "operations_policy_sha256",
        "response_validation_contract_sha256",
    ):
        c.require(attempt[field].hex() == binding[field], "S12_ATTEMPT_HISTORY_INVALID")
    c.require(
        1 <= attempt["attempt_number"] <= 5
        and attempt["attempt_id"]
        == c.attempt_id(
            attempt["request_execution_id"],
            attempt["campaign_id"],
            attempt["attempt_number"],
        ),
        "S12_ATTEMPT_HISTORY_INVALID",
    )


def begin(root: Path, binding: Mapping[str, Any], attempt: dict[str, Any]) -> bytes:
    """Persist before dispatch; failure leaves a permanently reserved failed unit."""
    validate_binding(binding)
    c.require(
        attempt["outcome"] == "UNKNOWN_DELIVERY" and attempt["finished_utc"] is None,
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    c.require(
        attempt["request_execution_id"].hex() == binding["request_execution_id"]
        and attempt["campaign_id"].hex() == binding["campaign_id"],
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    c.require(
        attempt["attempt_id"]
        == c.attempt_id(
            attempt["request_execution_id"],
            attempt["campaign_id"],
            attempt["attempt_number"],
        ),
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    validate_begin(binding, attempt)
    reserve(root)
    raw = c.canonical(dict(binding))
    write(root / "binding.json", raw)
    write(root / "begin.parquet", parquet_bytes("request_attempt", [attempt]))
    return c.sha(raw)


def finish(
    root: Path,
    attempt: dict[str, Any],
    capture: dict[str, Any] | None,
    raw: bytes | None,
    candidates: list[dict[str, Any]],
    *,
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
    fault: Callable[[str], None] = lambda _: None,
    retry_after_audit: dict[str, Any] | None = None,
) -> bytes:
    """Whole-response transaction. No seal until every byte and row reopens."""
    original = read_rows(read(root / "begin.parquet"), "request_attempt")[0]
    for field in IMMUTABLE_ATTEMPT_FIELDS:
        a, b = original[field], attempt[field]
        if field == "started_utc":
            c.require(
                c.framed([str(a)]) == c.framed([str(b)]), "S12_ATTEMPT_HISTORY_INVALID"
            )
        else:
            c.require(a == b, "S12_ATTEMPT_HISTORY_INVALID")
    c.require(
        attempt["finished_utc"] is not None
        and attempt["outcome"] in c.OUTCOMES
        and attempt["outcome"] != "UNKNOWN_DELIVERY",
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    names = [
        "binding.json",
        "begin.parquet",
        "finish.parquet",
        "candidates.parquet",
        "capture.json",
        "retry_clock.json",
    ]
    if raw is not None:
        c.require(
            capture is not None and c.sha(raw) == attempt["response_sha256"],
            "S12_RAW_HASH_MISMATCH",
        )
        write(root / "raw.zst", response.compress(raw))
        names.append("raw.zst")
        fault("raw_written")
    else:
        c.require(
            capture is None and not candidates and attempt["outcome"] not in c.SUCCESS,
            "S12_CAPTURE_INCOMPLETE",
        )
    write(root / "finish.parquet", parquet_bytes("request_attempt", [attempt]))
    write(root / "candidates.parquet", parquet_bytes("request_candidate", candidates))
    write(root / "capture.json", c.canonical({"capture": capture}))
    write(root / "retry_clock.json", c.canonical({"retry_after": retry_after_audit}))
    inventory = file_inventory(root, tuple(names))
    receipt = c.canonical({"receipt_version": c.ATTEMPT, "inventory": inventory})
    write(root / "receipt.json", receipt)
    validate(
        root,
        metadata(read(root / "binding.json")),
        reopen=reopen,
        sealed=False,
        require_success=False,
    )
    fault("before_seal")
    write(root / CHECKPOINT_SEAL, b"")
    fault("after_seal")
    validate(
        root,
        metadata(read(root / "binding.json")),
        reopen=reopen,
        sealed=True,
        require_success=False,
    )
    return c.sha(receipt)


def validate(
    root: Path,
    expected_binding: Mapping[str, Any],
    *,
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
    sealed: bool = True,
    require_success: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes | None]:
    validate_binding(expected_binding)
    c.require(
        read(root / "binding.json") == c.canonical(dict(expected_binding)),
        "S12_CHECKPOINT_BINDING_MISMATCH",
    )
    if sealed:
        c.require(
            read(root / CHECKPOINT_SEAL, limit=0) == b"", "S12_CHECKPOINT_INCOMPLETE"
        )
    receipt = metadata(read(root / "receipt.json"))
    c.require(
        set(receipt) == {"receipt_version", "inventory"}
        and receipt["receipt_version"] == c.ATTEMPT,
        "S12_CHECKPOINT_INVALID",
    )
    verify_inventory(
        root,
        receipt["inventory"],
        extra={"receipt.json"} | ({CHECKPOINT_SEAL} if sealed else set()),
    )
    attempts = read_rows(read(root / "finish.parquet"), "request_attempt")
    c.require(len(attempts) == 1, "S12_ATTEMPT_HISTORY_INVALID")
    attempt = attempts[0]
    begins = read_rows(read(root / "begin.parquet"), "request_attempt")
    c.require(len(begins) == 1, "S12_ATTEMPT_HISTORY_INVALID")
    validate_begin(expected_binding, begins[0])
    for field in IMMUTABLE_ATTEMPT_FIELDS:
        c.require(attempt[field] == begins[0][field], "S12_ATTEMPT_HISTORY_INVALID")
    c.require(
        attempt["outcome"] in c.OUTCOMES
        and attempt["outcome"] != "UNKNOWN_DELIVERY"
        and attempt["finished_utc"] is not None
        and attempt["finished_utc"] >= attempt["started_utc"],
        "S12_ATTEMPT_HISTORY_INVALID",
    )
    c.require(
        not require_success or attempt["outcome"] in c.SUCCESS,
        "S12_CHECKPOINT_NOT_SUCCESSFUL",
    )
    candidates = read_rows(read(root / "candidates.parquet"), "request_candidate")
    capture = metadata(read(root / "capture.json"))["capture"]
    raw = None
    if capture is not None:
        c.require(
            capture["request_execution_id"] == expected_binding["request_execution_id"]
            and capture["response_sha256"] == attempt["response_sha256"].hex()
            and capture["payload_complete"] is True,
            "S12_CAPTURE_BINDING_INVALID",
        )
        c.require(
            capture["http_status"] == attempt["http_status"]
            and capture["content_type"] == attempt["content_type"]
            and capture["content_encoding"] == attempt["content_encoding"]
            and capture["response_bytes"] == attempt["application_payload_bytes"],
            "S12_CAPTURE_BINDING_INVALID",
        )
        raw = response.decompress(
            read(root / "raw.zst"),
            length=capture["response_bytes"],
            expected_hash=attempt["response_sha256"],
        )
        try:
            projection = reopen(raw, capture)
        except c.Stage12Error:
            c.require(
                attempt["outcome"] == "CONTRACT_FAILURE" and not candidates,
                "S12_CHECKPOINT_PROJECTION_MISMATCH",
            )
        else:
            c.require(
                attempt["outcome"] == projection.outcome,
                "S12_CHECKPOINT_PROJECTION_MISMATCH",
            )
            c.require(
                [c.row_bytes("request_candidate", r) for r in candidates]
                == [c.row_bytes("request_candidate", r) for r in projection.candidates],
                "S12_CHECKPOINT_PROJECTION_MISMATCH",
            )
    else:
        c.require(
            attempt["outcome"] not in c.SUCCESS
            and not candidates
            and attempt["response_sha256"] is None,
            "S12_CAPTURE_INCOMPLETE",
        )
    return attempt, candidates, raw


def adopt(
    root: Path,
    expected_binding: Mapping[str, Any],
    *,
    expected_receipt_sha256: bytes,
    verified_interval_closure_sha256: bytes,
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
) -> tuple[dict[str, Any], list[dict[str, Any]], bytes | None]:
    """External campaign inventory/closed verification interval are required pins."""
    c.digest(verified_interval_closure_sha256)
    c.require(
        c.sha(read(root / "receipt.json")) == c.digest(expected_receipt_sha256),
        "S12_CHECKPOINT_RECEIPT_MISMATCH",
    )
    return validate(root, expected_binding, reopen=reopen)


def record_failure_preserving_primary(
    action: Callable[[], Any], receipt: Callable[[], None]
) -> Any:
    try:
        return action()
    except BaseException:
        try:
            receipt()
        except BaseException:
            pass
        raise

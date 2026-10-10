"""Bounded scientific artifact assembly from fully verified checkpoint histories.

The caller owns authorization, deployment continuity and final publication.
No network client or Stage 11 payload reader is used during assembly/replay.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from . import s12_integrity as integrity
from . import s12_raw_packs as packs
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io


@dataclass(frozen=True)
class ExecutionUnits:
    binding: Mapping[str, str]
    units: tuple[integrity.HistoryUnit, ...]


def parquet_stream(root: Path, name: str, rows: Iterable[dict[str, Any]]) -> None:
    """8 MiB target logical batches; one large row is never silently truncated."""
    fd = os.open(
        root / (name + ".parquet"),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "wb") as stream:
        with pq.ParquetWriter(
            stream, c.schema(name), compression="zstd", compression_level=3
        ) as writer:
            batch: list[dict[str, Any]] = []
            size = 0
            for row in rows:
                encoded_size = len(c.row_bytes(name, row))
                if batch and size + encoded_size > 8 * 1024**2:
                    writer.write_table(
                        pa.Table.from_pylist(batch, schema=c.schema(name))
                    )
                    batch, size = [], 0
                batch.append(row)
                size += encoded_size
            if batch:
                writer.write_table(pa.Table.from_pylist(batch, schema=c.schema(name)))
        stream.flush()
        os.fsync(stream.fileno())
    io.fsync_directory(root)


def read_relation(root: Path, name: str) -> Iterator[dict[str, Any]]:
    if name == "retrieval_policy":
        obj = io.metadata(io.read(root / "retrieval_policy.json"))
        obj["retrieval_policy_id"] = bytes.fromhex(obj["retrieval_policy_id"])
        c.validate_policy(obj)
        yield obj
        return
    # Validate file ownership, mode and non-link topology without loading it.
    from . import s09_reference_io as accepted_io

    accepted_io.topology(root)
    with pq.ParquetFile(root / (name + ".parquet")) as source:
        c.require(source.schema_arrow.equals(c.schema(name)), "S12_SCHEMA_INVALID")
        for batch in source.iter_batches(batch_size=256):
            for row in batch.to_pylist():
                c.row_bytes(name, row)
                yield row


def assemble(
    root: Path,
    groups: Iterable[ExecutionUnits],
    policy: dict[str, Any],
    *,
    expected_semantic_ids: frozenset[bytes],
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
) -> dict[str, Any]:
    """Sorted full IDs; metadata only accumulates, raw/candidates stay per-response.

    Policy has an empty list<struct<>> in the frozen logical Arrow schema, which
    Parquet cannot represent. Its sole row is canonical JSON with hex display
    ID; all logical row/schema digests use the unchanged frozen typed schema.
    """
    io.private_directory(root)
    c.validate_policy(policy)
    selected: dict[bytes, tuple[Path, Mapping[str, str], dict[str, Any]]] = {}
    attempts = []
    common: dict[str, str] | None = None
    for group in groups:
        binding = group.binding
        shared = {
            k: v
            for k, v in binding.items()
            if k not in ("request_execution_id", "query_semantic_id")
        }
        if common is None:
            common = shared
        c.require(common == shared, "S12_CAMPAIGN_BINDING_MISMATCH")
        c.require(
            binding["retrieval_policy_id"] == policy["retrieval_policy_id"].hex(),
            "S12_POLICY_INVALID",
        )
        rows, path = integrity.history(group.units, binding, reopen=reopen)
        c.require(path is not None, "S12_PUBLICATION_INCOMPLETE")
        assert path is not None
        execution = bytes.fromhex(binding["request_execution_id"])
        c.require(execution not in selected, "S12_DUPLICATE_EXECUTION")
        selected[execution] = (path, binding, rows[-1])
        attempts.extend(rows)
    c.require(
        common is not None
        and {bytes.fromhex(v[1]["query_semantic_id"]) for v in selected.values()}
        == expected_semantic_ids,
        "S12_WORKLOAD_TOTALITY_INVALID",
    )
    assert common is not None
    ordered = sorted(selected)
    frames = packs.pack(
        root / "raw",
        (
            (
                execution,
                selected[execution][0] / "raw.zst",
                selected[execution][2]["application_payload_bytes"],
                selected[execution][2]["response_sha256"],
            )
            for execution in ordered
        ),
    )
    locators = {bytes.fromhex(row["request_execution_id"]): row for row in frames}
    policy_json = {**policy, "retrieval_policy_id": policy["retrieval_policy_id"].hex()}
    io.write(root / "retrieval_policy.json", c.canonical(policy_json))
    attempts.sort(key=lambda row: row["attempt_id"])
    parquet_stream(root, "request_attempt", attempts)
    captures = []
    executions = []
    for execution in ordered:
        path, binding, attempt = selected[execution]
        capture = io.metadata(io.read(path / "capture.json"))["capture"]
        typed = {**capture}
        for key in ("request_execution_id", "request_target_sha256", "response_sha256"):
            typed[key] = bytes.fromhex(typed[key])
        captures.append(typed)
        candidates = io.read_rows(
            io.read(path / "candidates.parquet"), "request_candidate"
        )
        row: dict[str, Any] = {name: None for name in c.columns("request_execution")}
        row.update({key: bytes.fromhex(binding[key]) for key in c.EXECUTION_FIELDS[1:]})
        frame = locators[execution]
        row.update(
            request_execution_id=execution,
            request_target_sha256=typed["request_target_sha256"],
            terminal_state=attempt["outcome"],
            reason_code="OK",
            terminal_attempt_id=attempt["attempt_id"],
            candidate_count=len(candidates),
            response_sha256=typed["response_sha256"],
            response_bytes=typed["response_bytes"],
            raw_pack_key="raw/" + frame["raw_pack_key"],
            raw_frame_offset=frame["raw_frame_offset"],
            raw_frame_length=frame["raw_frame_length"],
            response_completed_utc=attempt["finished_utc"],
        )
        executions.append(row)
    parquet_stream(root, "request_execution", executions)

    def candidate_rows() -> Iterator[dict[str, Any]]:
        for execution in ordered:
            yield from io.read_rows(
                io.read(selected[execution][0] / "candidates.parquet"),
                "request_candidate",
            )

    parquet_stream(root, "request_candidate", candidate_rows())
    totals = integrity.relations(
        lambda name: read_relation(root, name),
        expected_semantic_ids,
        campaign_id=bytes.fromhex(common["campaign_id"]),
    )
    raw_set, context = c.capture_hashes(len(captures), captures)
    projection = c.projection_id(
        raw_set,
        context,
        bytes.fromhex(common["response_validation_contract_sha256"]),
        bytes.fromhex(common["response_extraction_contract_sha256"]),
        bytes.fromhex(common["candidate_schema_sha256"]),
    )
    result = {
        **totals,
        "raw_response_set_sha256": raw_set.hex(),
        "capture_context_sha256": context.hex(),
        "response_projection_id": projection.hex(),
    }
    io.write(root / "assembly.json", c.canonical(result))
    return result


def reopen_artifact(
    root: Path,
    *,
    expected_semantic_ids: frozenset[bytes],
    campaign_id: bytes,
    validation_sha256: bytes,
    extraction_sha256: bytes,
    candidate_schema_sha256: bytes,
    reopen: Callable[[bytes, dict[str, Any]], response.Projection],
) -> dict[str, Any]:
    """Full offline reopen: every raw frame reprojects to exactly its relation rows."""
    totals = integrity.relations(
        lambda name: read_relation(root, name),
        expected_semantic_ids,
        campaign_id=campaign_id,
    )
    attempt_metadata = {
        row["attempt_id"]: row for row in read_relation(root, "request_attempt")
    }
    candidates = iter(read_relation(root, "request_candidate"))
    next_row = next(candidates, None)
    captures = []
    for execution in read_relation(root, "request_execution"):
        relative = Path(execution["raw_pack_key"])
        c.require(
            not relative.is_absolute()
            and all(part not in (".", "..") for part in relative.parts)
            and len(relative.parts) == 3
            and relative.parts[0] == "raw",
            "S12_RAW_PACK_INVALID",
        )
        path = root / relative
        receipt = io.metadata(io.read(path.parent / "receipt.json"))
        c.require(
            io.read(path.parent / "_SEALED", limit=0) == b"", "S12_RAW_PACK_INVALID"
        )
        physical = io.read(path, limit=packs.MAX_COMPRESSED)
        c.require(
            receipt["physical_sha256"] == c.sha(physical).hex()
            and receipt["bytes"] == len(physical),
            "S12_RAW_PACK_INVALID",
        )
        start, length = execution["raw_frame_offset"], execution["raw_frame_length"]
        raw = response.decompress(
            physical[start : start + length],
            length=execution["response_bytes"],
            expected_hash=execution["response_sha256"],
        )
        attempt = attempt_metadata[execution["terminal_attempt_id"]]
        capture = dict(
            request_execution_id=execution["request_execution_id"].hex(),
            request_target_sha256=execution["request_target_sha256"].hex(),
            http_status=attempt["http_status"],
            content_type=attempt["content_type"],
            content_encoding=attempt["content_encoding"],
            payload_complete=True,
            response_bytes=len(raw),
            response_sha256=c.sha(raw).hex(),
        )
        projected = reopen(raw, capture)
        c.require(
            projected.outcome == execution["terminal_state"],
            "S12_CHECKPOINT_PROJECTION_MISMATCH",
        )
        for expected in projected.candidates:
            c.require(
                next_row is not None
                and c.row_bytes("request_candidate", next_row)
                == c.row_bytes("request_candidate", expected),
                "S12_CHECKPOINT_PROJECTION_MISMATCH",
            )
            next_row = next(candidates, None)
        for key in ("request_execution_id", "request_target_sha256", "response_sha256"):
            capture[key] = bytes.fromhex(capture[key])
        captures.append(capture)
    c.require(next_row is None, "S12_CANDIDATE_COUNT_INVALID")
    raw_set, context = c.capture_hashes(len(captures), captures)
    projection = c.projection_id(
        raw_set, context, validation_sha256, extraction_sha256, candidate_schema_sha256
    )
    result = {
        **totals,
        "raw_response_set_sha256": raw_set.hex(),
        "capture_context_sha256": context.hex(),
        "response_projection_id": projection.hex(),
    }
    c.require(
        io.read(root / "assembly.json") == c.canonical(result), "S12_ASSEMBLY_MISMATCH"
    )
    return result

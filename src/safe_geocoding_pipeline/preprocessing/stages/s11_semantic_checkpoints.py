"""Immutable exact-bound units; recovery never relies on job-local bytes."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from . import s09_reference_io as base
from . import s09_reference_publication as publication
from . import s11_semantic_contract as c
from . import s11_semantic_io as io

DESCRIPTOR = "unit.json"
SEAL = "_COMPLETE"


def fault(phase: str) -> None:
    """Synthetic-only interruption seam; no CLI or environment switch."""


def payload_digest(kind: str, paths: Sequence[Path]) -> tuple[int, str]:
    digest = hashlib.sha256(b"SAFE:stage11-checkpoint-payload:v1\0" + c.framed((kind,)))
    count = 0
    previous = None
    values: tuple[Any, ...]
    for row in io.parquet_rows(paths):
        if kind == "input":
            c.require(set(row) == set(io.SPOOL_SCHEMA.names), "S11_CHECKPOINT_INVALID")
            key, request, raw = (
                row["hypothesis_id"],
                row["query_semantic_id"],
                row["canonical_bytes"],
            )
            c.decode_core(raw)
            c.require(c.semantic_id(raw) == request, "S11_ID_RECOMPUTE_MISMATCH")
            values = (key, request, raw)
        else:
            c.require(
                kind == "reduction"
                and set(row) == set(c.schema("semantic_request").names),
                "S11_CHECKPOINT_INVALID",
            )
            key = row["query_semantic_id"]
            raw = c.core_bytes(row["core"])
            c.require(c.semantic_id(raw) == key, "S11_ID_RECOMPUTE_MISMATCH")
            values = (key, raw)
        c.require(
            type(key) is bytes
            and len(key) == 32
            and (previous is None or previous < key),
            "S11_CHECKPOINT_INVALID",
        )
        previous = key
        digest.update(c.framed(values))
        count += 1
    digest.update(c.framed((count,)))
    return count, digest.hexdigest()


def validate_unit(root: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    try:
        raw = publication.read_private(root / DESCRIPTOR)
        c.require(
            publication.read_private(root / SEAL)
            == hashlib.sha256(raw).hexdigest().encode("ascii") + b"\n",
            "S11_CHECKPOINT_INVALID",
        )
        record = c.decode_json(raw)
        c.require(
            set(record)
            == {
                "checkpoint_version",
                "binding",
                "kind",
                "coverage",
                "files",
                "rows",
                "payload_sha256",
            }
            and record["checkpoint_version"] == "stage11_checkpoint_v1"
            and all(record[k] == v for k, v in expected.items()),
            "S11_CHECKPOINT_INVALID",
        )
        base.topology(
            root, [DESCRIPTOR, SEAL, *(f["relative_path"] for f in record["files"])]
        )
        paths = [io.verify_file(root, item) for item in record["files"]]
        c.require(
            bool(paths) and len(set(paths)) == len(paths), "S11_CHECKPOINT_INVALID"
        )
        schema = (
            io.SPOOL_SCHEMA
            if record["kind"] == "input"
            else c.schema("semantic_request")
        )
        c.require(
            all(pq.read_schema(p).equals(schema, check_metadata=True) for p in paths),
            "S11_CHECKPOINT_INVALID",
        )
        c.require(
            payload_digest(record["kind"], paths)
            == (record["rows"], record["payload_sha256"]),
            "S11_CHECKPOINT_INVALID",
        )
        return record
    except Exception:
        raise c.Stage11Error("S11_CHECKPOINT_INVALID") from None


def save_unit(
    root: Path, local: Path, paths: Sequence[Path], expected: Mapping[str, Any]
) -> dict[str, Any]:
    root.mkdir(mode=0o700)
    (root / "payload").mkdir(mode=0o700)
    copied = []
    for path in paths:
        destination = root / "payload" / path.name
        io.copy_exclusive(path, destination)
        copied.append(destination)
    count, digest = payload_digest(expected["kind"], copied)
    record = {
        "checkpoint_version": "stage11_checkpoint_v1",
        **expected,
        "files": [io.file_record(root, p) for p in copied],
        "rows": count,
        "payload_sha256": digest,
    }
    io.write_json(root / DESCRIPTOR, record)
    base.fsync_tree(root)
    fault("before_unit_seal")
    io.write_exclusive(
        root / SEAL, c.sha256_file(root / DESCRIPTOR).encode("ascii") + b"\n"
    )
    io.fsync_directory(root)
    io.fsync_directory(root.parent)
    validate_unit(root, expected)
    fault("after_unit_seal")
    return record


def adopt_unit(
    source: Path, target: Path, expected: Mapping[str, Any]
) -> dict[str, Any]:
    record = validate_unit(source, expected)
    target.mkdir(mode=0o700)
    (target / "payload").mkdir(mode=0o700)
    for item in record["files"]:
        io.copy_exclusive(
            io.confined(source, item["relative_path"]), target / item["relative_path"]
        )
    io.copy_exclusive(source / DESCRIPTOR, target / DESCRIPTOR)
    base.fsync_tree(target)
    io.copy_exclusive(source / SEAL, target / SEAL)
    io.fsync_directory(target)
    io.fsync_directory(target.parent)
    return validate_unit(target, expected)


def paths(root: Path, record: Mapping[str, Any]) -> list[Path]:
    return [io.confined(root, f["relative_path"]) for f in record["files"]]

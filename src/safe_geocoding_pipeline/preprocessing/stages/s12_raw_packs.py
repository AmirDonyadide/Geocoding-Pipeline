"""Bounded independent-frame compaction; old fragments remain immutable."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io

MAX_COMPRESSED = 64 * 1024 * 1024
MAX_RESPONSES = 256


def pack(
    root: Path, fragments: Iterable[tuple[bytes, Path, int, bytes]]
) -> Iterator[dict[str, Any]]:
    """Caller supplies sealed-capture inventory; every source frame reopens.

    At most 256 small index entries and one decoded response are held here.
    Entries become visible only after the complete pack and its receipt seal
    reopen. No adoption of incomplete frames, link copying or fragment deletion.
    """
    io.reserve(root)
    number = 0
    entries: list[dict[str, Any]] = []
    size = 0
    stream = None
    directory: Path | None = None

    def seal() -> list[dict[str, Any]]:
        assert stream is not None and directory is not None
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
        physical = io.read(directory / "raw.zst", limit=MAX_COMPRESSED)
        c.require(len(physical) == size, "S12_RAW_PACK_INVALID")
        for entry in entries:
            start = entry["raw_frame_offset"]
            end = start + entry["raw_frame_length"]
            response.decompress(
                physical[start:end],
                length=entry["response_bytes"],
                expected_hash=bytes.fromhex(entry["response_sha256"]),
            )
        receipt = {
            "codec": "zstd",
            "compression_level": 3,
            "codec_provider": "pyarrow",
            "codec_provider_version": pa.__version__,
            "bytes": size,
            "physical_sha256": c.sha(physical).hex(),
            "frames": entries,
        }
        io.write(directory / "receipt.json", c.canonical(receipt))
        c.require(
            io.metadata(io.read(directory / "receipt.json")) == receipt,
            "S12_RAW_PACK_INVALID",
        )
        io.write(directory / "_SEALED", b"")
        return list(entries)

    try:
        for execution, path, length, fingerprint in fragments:
            c.digest(execution)
            source = io.read(path)
            raw = response.decompress(source, length=length, expected_hash=fingerprint)
            frame = response.compress(raw)
            c.require(len(frame) <= MAX_COMPRESSED, "S12_RAW_PACK_INVALID")
            if entries and (
                len(entries) == MAX_RESPONSES or size + len(frame) > MAX_COMPRESSED
            ):
                yield from seal()
                stream = None
                entries = []
                size = 0
            if stream is None:
                number += 1
                directory = root / f"pack_{number:06d}"
                io.reserve(directory)
                fd = os.open(
                    directory / "raw.zst",
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                stream = os.fdopen(fd, "wb")
            stream.write(frame)
            entries.append(
                {
                    "request_execution_id": execution.hex(),
                    "response_sha256": c.digest(fingerprint).hex(),
                    "response_bytes": length,
                    "raw_pack_key": f"pack_{number:06d}/raw.zst",
                    "raw_frame_offset": size,
                    "raw_frame_length": len(frame),
                }
            )
            size += len(frame)
        if entries:
            yield from seal()
        io.fsync_directory(root)
    finally:
        if stream is not None and not stream.closed:
            stream.close()

"""Stage 11 private I/O and bounded execution primitives."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_io as base
from . import s11_semantic_contract as c

MANIFEST_NAME = "stage11_semantic_request_manifest.json"
SUMMARY_NAME = "semantic_request_summary.json"
SUCCESS_NAME = "_SUCCESS.json"
write_exclusive = base.write_exclusive
fsync_directory = base.fsync_directory
parquet_sql = base.parquet_sql
sql_literal = base.sql_literal


class RelationWriter(base.RelationWriter):
    """Accepted writer mechanics with arbitrary canonical-byte payload support."""

    def append(self, row: Mapping[str, Any]) -> None:
        def size(value: Any) -> int:
            if isinstance(value, Mapping):
                return 128 + sum(size(v) for v in value.values())
            if isinstance(value, str):
                return 64 + sum(
                    len(value[i : i + 65536].encode("utf-8"))
                    for i in range(0, len(value), 65536)
                )
            if isinstance(value, bytes):
                return 64 + len(value)
            return 64

        c.require(set(row) == set(self.schema.names), "S11_ENCODING_INVALID")
        amount = size(row)
        if self.buffer and (
            len(self.buffer) >= self.batch_rows
            or self.buffer_bytes + amount > self.batch_bytes
        ):
            self.flush()
        self.buffer.append(row)
        self.buffer_bytes += amount
        self.rows += 1
        if self.buffer_bytes >= self.batch_bytes:
            self.flush()


def write_json(path: Path, value: Any) -> None:
    write_exclusive(path, c.canonical(value))


def private(path: Path, *, directory: bool = False) -> None:
    info = path.lstat()
    c.require(
        (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and info.st_uid == os.geteuid()
        and (directory or info.st_nlink == 1),
        "S11_PRIVACY_GUARD_FAILURE",
    )


def confined(root: Path, name: str) -> Path:
    c.require(
        type(name) is str
        and not Path(name).is_absolute()
        and all(p not in ("", ".", "..") for p in name.split("/"))
        and "\\" not in name,
        "S11_INPUT_BINDING_INVALID",
    )
    path = root / name
    c.require(path.resolve(strict=True) == path, "S11_PRIVACY_GUARD_FAILURE")
    private(path)
    return path


def rows(connection: duckdb.DuckDBPyConnection, sql: str) -> Iterator[dict[str, Any]]:
    # One Arrow row limits decoded memory to the largest accepted value. Writers
    # independently enforce estimated byte + row bounds. DuckDB sort state spills.
    reader = connection.execute(sql).to_arrow_reader(batch_size=1)
    for batch in reader:
        yield batch.to_pylist()[0]


def parquet_rows(paths: Sequence[Path]) -> Iterator[dict[str, Any]]:
    for path in paths:
        with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
            for batch in parquet.iter_batches(batch_size=1, use_threads=False):
                yield batch.to_pylist()[0]


def connect(
    workspace: Path, *, memory: str = "2GB", threads: int = 2
) -> duckdb.DuckDBPyConnection:
    private(workspace, directory=True)
    return base.bounded_connection(
        workspace / "spill",
        memory=memory,
        threads=threads,
        database=workspace / "working.duckdb",
    )


def record(name: str, root: Path, paths: Sequence[Path], count: int) -> dict[str, Any]:
    return {
        "name": name,
        "row_count": count,
        "schema_sha256": c.descriptor_sha(name).hex(),
        "logical_sha256": c.relation_digest(name, count, parquet_rows(paths)).hex(),
        "files": [file_record(root, p) for p in paths],
    }


def file_record(root: Path, path: Path) -> dict[str, Any]:
    private(path)
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": c.sha256_file(path),
    }


def verify_file(root: Path, item: Mapping[str, Any]) -> Path:
    c.require(
        set(item) == {"relative_path", "bytes", "sha256"}, "S11_INPUT_BINDING_INVALID"
    )
    path = confined(root, item["relative_path"])
    c.require(
        path.stat().st_size == item["bytes"] and c.sha256_file(path) == item["sha256"],
        "S11_INPUT_BINDING_INVALID",
    )
    return path


def copy_exclusive(source: Path, destination: Path) -> None:
    private(source)
    before = source.stat()
    digest = hashlib.sha256()
    fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with source.open("rb") as src, os.fdopen(fd, "wb") as dst:
        for block in iter(lambda: src.read(8 * 1024 * 1024), b""):
            dst.write(block)
            digest.update(block)
        dst.flush()
        os.fsync(dst.fileno())
    after = source.stat()
    c.require(
        (before.st_size, before.st_mtime_ns, before.st_ino)
        == (after.st_size, after.st_mtime_ns, after.st_ino)
        and destination.stat().st_size == before.st_size
        and c.sha256_file(destination) == digest.hexdigest(),
        "S11_CHECKPOINT_INVALID",
    )
    fsync_directory(destination.parent)


def verify_relation(
    root: Path, relation: Mapping[str, Any], connection: duckdb.DuckDBPyConnection
) -> list[Path]:
    name = relation["name"]
    c.require(
        set(relation)
        == {"name", "row_count", "schema_sha256", "logical_sha256", "files"}
        and name in c.RELATIONS
        and relation["schema_sha256"] == c.descriptor_sha(name).hex(),
        "S11_INPUT_BINDING_INVALID",
    )
    paths = [verify_file(root, f) for f in relation["files"]]
    c.require(
        bool(paths) and len(set(paths)) == len(paths), "S11_INPUT_BINDING_INVALID"
    )
    for path in paths:
        c.require(
            pq.read_schema(path).equals(c.schema(name), check_metadata=True),
            "S11_INPUT_BINDING_INVALID",
        )
    ordered = rows(
        connection,
        f"SELECT * FROM {parquet_sql(paths)} ORDER BY {c.schema(name).names[0]}",
    )
    c.require(
        c.relation_digest(name, relation["row_count"], ordered).hex()
        == relation["logical_sha256"],
        "S11_INPUT_BINDING_INVALID",
    )
    return paths


SPOOL_SCHEMA = pa.schema(
    [
        pa.field("hypothesis_id", pa.binary(32), nullable=False),
        pa.field("query_semantic_id", pa.binary(32), nullable=False),
        pa.field("canonical_bytes", pa.large_binary(), nullable=False),
    ],
    metadata={b"kind": b"STAGE11_OPERATIONAL_CHECKPOINT", b"protected": b"true"},
)

"""Bounded Arrow I/O and fail-closed immutable publication for Stage 9.

Inodes prove only ownership during this invocation. Reopening across jobs
verifies bytes and logical identity, never an
historical inode. Failed attempts are retained and are not silently adopted.
"""

from __future__ import annotations

import os
import stat
import ctypes
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_contract as c

MANIFEST_NAME = "stage09_reference_manifest.json"
SUCCESS_NAME = "_SUCCESS.json"


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: Path, value: Any) -> None:
    write_exclusive(path, c.canonical_json(value))


def fsync_tree(root: Path) -> None:
    for directory, children, files in os.walk(root, followlinks=False, topdown=False):
        parent = Path(directory)
        for name in children:
            c.require(
                not (parent / name).is_symlink(), "PUBLICATION_SYMLINK_PROHIBITED"
            )
        for name in files:
            path = parent / name
            info = path.lstat()
            c.require(stat.S_ISREG(info.st_mode), "PUBLICATION_FILE_TYPE_INVALID")
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                c.require(
                    stat.S_ISREG(os.fstat(descriptor).st_mode),
                    "PUBLICATION_FILE_TYPE_INVALID",
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        fsync_directory(parent)


def topology(root: Path, expected_files: Sequence[str] | None = None) -> None:
    c.require(
        root.is_dir()
        and not root.is_symlink()
        and stat.S_IMODE(root.stat().st_mode) == 0o700
        and root.stat().st_uid == os.geteuid(),
        "PUBLICATION_ROOT_INVALID",
    )
    found = []
    found_directories = set()
    for directory, children, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        if parent != root:
            found_directories.add(parent.relative_to(root).as_posix())
        c.require(
            stat.S_IMODE(parent.lstat().st_mode) == 0o700
            and parent.lstat().st_uid == os.geteuid(),
            "PUBLICATION_DIRECTORY_MODE_INVALID",
        )
        for name in children:
            c.require(
                not (parent / name).is_symlink(), "PUBLICATION_SYMLINK_PROHIBITED"
            )
        for name in files:
            path = parent / name
            info = path.lstat()
            c.require(
                stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_nlink == 1,
                "PUBLICATION_FILE_TOPOLOGY_INVALID",
            )
            c.require(info.st_uid == os.geteuid(), "PUBLICATION_FILE_OWNER_INVALID")
            found.append(path.relative_to(root).as_posix())
    if expected_files is not None:
        c.require(
            sorted(found) == sorted(expected_files), "PUBLICATION_INVENTORY_NOT_EXACT"
        )
        expected_directories = {
            parent.as_posix()
            for name in expected_files
            for parent in Path(name).parents
            if parent != Path(".")
        }
        c.require(
            found_directories == expected_directories,
            "PUBLICATION_DIRECTORY_INVENTORY_NOT_EXACT",
        )


class RelationWriter:
    """Fixed row and estimated-byte batches; a scalar is never truncated."""

    def __init__(
        self,
        directory: Path,
        schema: Any,
        *,
        batch_rows: int = 8192,
        batch_bytes: int = 64 * 1024 * 1024,
        target_file_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        c.require(
            batch_rows > 0 and batch_bytes > 0 and target_file_bytes > 0,
            "WRITER_BOUNDS_INVALID",
        )
        directory.mkdir(mode=0o700)
        self.directory, self.schema = directory, schema
        self.batch_rows, self.batch_bytes, self.target_file_bytes = (
            batch_rows,
            batch_bytes,
            target_file_bytes,
        )
        self.buffer: list[Mapping[str, Any]] = []
        self.buffer_bytes = 0
        self.file_bytes = 0
        self.rows = 0
        self.paths: list[Path] = []
        self.writer: Any = None

    def append(self, row: Mapping[str, Any]) -> None:
        c.require(
            set(row) == set(self.schema.names), "OUTPUT_COLUMN_ALLOWLIST_MISMATCH"
        )
        size = sum(
            len(chunk) for chunk in c.typed_chunks(c.ordered_values(row, self.schema))
        )
        if self.buffer and (
            len(self.buffer) >= self.batch_rows
            or self.buffer_bytes + size > self.batch_bytes
        ):
            self.flush()
        self.buffer.append(row)
        self.buffer_bytes += size
        self.rows += 1
        if self.buffer_bytes >= self.batch_bytes:
            self.flush()

    def _open(self) -> None:
        path = self.directory / f"part-{len(self.paths):06}.parquet"
        # Explicit owner-only mode; publication does not mutate process umask.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        self.paths.append(path)
        self.writer = pq.ParquetWriter(
            path, self.schema, compression="zstd", version="2.6"
        )

    def flush(self) -> None:
        if not self.buffer:
            return
        if self.writer is None:
            self._open()
        table = pa.Table.from_pylist(self.buffer, schema=self.schema)
        self.writer.write_table(table)
        self.file_bytes += table.nbytes
        self.buffer.clear()
        self.buffer_bytes = 0
        if self.file_bytes >= self.target_file_bytes:
            self._close_file()

    def _close_file(self) -> None:
        if self.writer is not None:
            self.writer.close()
            self.writer = None
            with self.paths[-1].open("rb") as stream:
                os.fsync(stream.fileno())
            self.file_bytes = 0

    def close(self) -> None:
        self.flush()
        if not self.paths:
            self._open()
        self._close_file()
        fsync_directory(self.directory)


def parquet_rows(
    paths: Sequence[Path],
    *,
    columns: Sequence[str] | None = None,
    batch_rows: int = 1024,
) -> Iterator[dict[str, Any]]:
    for path in paths:
        with pq.ParquetFile(path) as parquet:
            for batch in parquet.iter_batches(
                batch_size=batch_rows, columns=columns, use_threads=False
            ):
                # Batches that include accepted giant Stage 8 scalars use
                # batch_rows=1; no candidate-sized nested component list here.
                yield from batch.to_pylist()


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parquet_sql(paths: Sequence[Path]) -> str:
    c.require(bool(paths), "PARQUET_INVENTORY_EMPTY")
    return (
        "read_parquet(["
        + ",".join(sql_literal(str(p)) for p in paths)
        + "], union_by_name=false)"
    )


def bounded_connection(
    scratch: Path,
    *,
    memory: str = "8GB",
    threads: int = 4,
    database: Path | None = None,
) -> duckdb.DuckDBPyConnection:
    scratch.mkdir(mode=0o700, parents=False, exist_ok=False)
    if database is not None:
        c.require(not os.path.lexists(database), "WORK_DATABASE_ALREADY_EXISTS")
    connection = duckdb.connect(":memory:" if database is None else str(database))
    if database is not None:
        database.chmod(0o600)
    connection.execute("SET memory_limit=" + sql_literal(memory))
    connection.execute("SET threads=" + str(threads))
    connection.execute("SET temp_directory=" + sql_literal(str(scratch)))
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET autoinstall_known_extensions=false")
    connection.execute("SET autoload_known_extensions=false")
    connection.execute("SET disabled_filesystems='HTTPFileSystem'")
    return connection


def sorted_rows(
    connection: duckdb.DuckDBPyConnection, sql: str, *, batch_rows: int = 8192
) -> Iterator[dict[str, Any]]:
    reader = connection.execute(sql).to_arrow_reader(batch_size=batch_rows)
    for batch in reader:
        yield from batch.to_pylist()


def canonicalize(
    connection: duckdb.DuckDBPyConnection,
    name: str,
    input_paths: Sequence[Path],
    output: Path,
    *,
    collapse_exact_duplicates: bool = False,
) -> dict[str, Any]:
    order = ",".join(c.PRIMARY_KEYS[name])
    distinct = "DISTINCT " if collapse_exact_duplicates else ""
    query = f"SELECT {distinct}* FROM {parquet_sql(input_paths)} ORDER BY {order}"
    writer = RelationWriter(output, c.relation_schema(name))
    previous = None
    for row in sorted_rows(connection, query):
        key = tuple(row[k] for k in c.PRIMARY_KEYS[name])
        c.require(
            previous is None or previous < key,
            "RELATION_ID_COLLISION_OR_NONDETERMINISM",
        )
        previous = key
        writer.append(row)
    writer.close()
    digest = c.relation_fingerprint(name, writer.rows, parquet_rows(writer.paths))
    return relation_record(name, output.parent, writer.paths, writer.rows, digest)


def relation_record(
    name: str, root: Path, paths: Sequence[Path], count: int, logical: bytes
) -> dict[str, Any]:
    return {
        "name": name,
        "row_count": count,
        "schema_sha256": c.schema_fingerprint(name).hex(),
        "logical_sha256": logical.hex(),
        "files": [
            {
                "relative_path": p.relative_to(root).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": c.sha256_file(p),
            }
            for p in paths
        ],
    }


def validate_relation(root: Path, record: Mapping[str, Any]) -> list[Path]:
    from .s09_reference_pack import confined

    name = record["name"]
    c.require(
        record["schema_sha256"] == c.schema_fingerprint(name).hex(),
        "RELATION_SCHEMA_BINDING_MISMATCH",
    )
    paths = []
    for item in record["files"]:
        path = confined(root, item["relative_path"])
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "RELATION_PHYSICAL_HASH_MISMATCH",
        )
        c.require(
            pq.read_schema(path).equals(c.relation_schema(name), check_metadata=True),
            "RELATION_SCHEMA_MISMATCH",
        )
        paths.append(path)
    c.require(
        c.relation_fingerprint(name, record["row_count"], parquet_rows(paths)).hex()
        == record["logical_sha256"],
        "RELATION_LOGICAL_HASH_MISMATCH",
    )
    return paths


def directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    c.require(stat.S_ISDIR(info.st_mode), "PUBLICATION_PATH_TYPE_INVALID")
    return info.st_dev, info.st_ino


@dataclass(frozen=True)
class PublicationResult:
    path: Path
    manifest_sha256: str
    manifest: Mapping[str, Any]
    disposition: str = "PASS"
    commit_record_id: str = ""
    registration_sha256: str = ""


Build = Callable[[Path], Mapping[str, Any]]
PublicationState = bool | Literal["prepared"]
Validate = Callable[[Path, str, PublicationState], Mapping[str, Any]]


def _atomic_rename(source: Path, destination: Path) -> None:
    # HISTORICAL DIAGNOSTICS ONLY. Active Stage 9 publication never calls this.
    c.require(not os.path.lexists(destination), "PUBLICATION_TARGET_EXISTS")
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "linux":
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        function.restype = ctypes.c_int
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    elif sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        result = function(os.fsencode(source), os.fsencode(destination), 4)
    else:
        raise c.Stage09Error("ATOMIC_NO_REPLACE_UNSUPPORTED_PLATFORM")
    c.require(result == 0, "ATOMIC_NO_REPLACE_FAILED")


def publish(
    final: Path,
    build: Build,
    validate: Validate,
    *,
    expected_manifest: str | None = None,
) -> PublicationResult:
    """Approved reservation/seal protocol; no rename or destructive demotion."""
    from . import s09_reference_publication as publication

    return publication.publish(
        final, build, validate, expected_manifest=expected_manifest
    )


def validate_terminal(
    root: Path, expected_manifest: str, published: PublicationState
) -> dict[str, Any]:
    from . import s09_reference_publication as publication

    return publication.validate_terminal(root, expected_manifest, published)


def terminal_files(published: PublicationState) -> list[str]:
    from . import s09_reference_publication as publication

    return publication.terminal_files(published)

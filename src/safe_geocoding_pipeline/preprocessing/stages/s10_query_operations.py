"""Bounded operational helpers; none participates in scientific identities."""

from __future__ import annotations

import hashlib
import resource
import re
import signal
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pyarrow as pa

from . import s09_reference_io as base_io
from . import s10_query_contract as c
from . import s10_query_io as io

PAGE_CONTEXTS = 64
PAGE_BYTES = 8 * 1024 * 1024
SELECTOR_BYTES = 2 * 1024 * 1024


class Progress:
    """Integer, fixed-label aggregate telemetry, with exclusive durable receipts."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root
        self.started = time.monotonic_ns()
        self.phase = "initialization"
        self.counts = dict.fromkeys(
            (
                "contexts_loaded",
                "contexts_completed",
                "family_decisions_written",
                "hypotheses_written",
                "checkpoints_completed",
                "checkpoints_reused",
            ),
            0,
        )
        self.timings: dict[str, dict[str, int]] = {}
        self.wal_high_water_bytes = 0
        self.sequence = 0
        self.failed_phase: str | None = None

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        before, cpu = time.monotonic_ns(), time.process_time_ns()
        previous, self.phase = self.phase, name
        try:
            yield
        except BaseException:
            if self.failed_phase is None:
                self.failed_phase = name
            raise
        finally:
            entry = self.timings.setdefault(
                name, {"calls": 0, "wall_ns": 0, "cpu_ns": 0}
            )
            entry["calls"] += 1
            entry["wall_ns"] += time.monotonic_ns() - before
            entry["cpu_ns"] += time.process_time_ns() - cpu
            self.phase = previous

    def observe_wal(self, database: Path) -> int:
        path = Path(str(database) + ".wal")
        size = path.stat().st_size if path.exists() else 0
        self.wal_high_water_bytes = max(self.wal_high_water_bytes, size)
        return size

    def snapshot(self) -> dict[str, Any]:
        return {
            "operational_version": "stage10_progress_v2",
            "phase": self.phase,
            "failed_phase": self.failed_phase,
            "elapsed_ns": time.monotonic_ns() - self.started,
            "counts": dict(self.counts),
            "timings_inclusive": self.timings,
            "wal_observed_high_water_bytes": self.wal_high_water_bytes,
            "max_rss_native": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }

    def record(self, *, announce: bool = False) -> None:
        if self.root is None:
            return
        if not self.root.exists():
            self.root.mkdir(mode=0o700)
        report = self.snapshot()
        io.write_json(self.root / f"progress-{self.sequence:06}.json", report)
        self.sequence += 1
        if announce:
            print(c.canonical(report).decode("utf-8"), end="", flush=True)


INDEX_DEPENDENCIES = re.compile(
    r"\bstage10_(?:sources|lines|candidates|context_keys|candidate_certificates)\b",
    re.IGNORECASE,
)
MUTATION = re.compile(
    r"\b(?:CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|TRUNCATE|REPLACE)\b", re.IGNORECASE
)


class TimedConnection:
    """Transparent operational SQL timing; parameters and SQL never enter logs."""

    def __init__(
        self, raw: Any, progress: Progress, revision: list[int] | None = None
    ) -> None:
        self.raw, self.progress = raw, progress
        self.revision = [0] if revision is None else revision

    @property
    def source_revision(self) -> int:
        return self.revision[0]

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    def cursor(self) -> TimedConnection:
        with self.progress.measure("database_cursor"):
            return TimedConnection(self.raw.cursor(), self.progress, self.revision)

    def execute(self, query: str, parameters: Any = None) -> TimedConnection:
        with self.progress.measure("database_execute"):
            if parameters is None:
                self.raw.execute(query)
            else:
                self.raw.execute(query, parameters)
            # Invalidate a derivative join if its private inputs are explicitly
            # changed (fault injection/review setup). Normal generation writes
            # only diagnostics. Never use a stale index after such a mutation.
            if MUTATION.search(query) and INDEX_DEPENDENCIES.search(query):
                self.revision[0] += 1
        return self

    def fetchone(self) -> Any:
        with self.progress.measure("database_fetch"):
            return self.raw.fetchone()

    def to_arrow_reader(self, **kwargs: Any) -> Any:
        with self.progress.measure("arrow_reader_create"):
            return self.raw.to_arrow_reader(**kwargs)


@contextmanager
def termination_guard() -> Iterator[None]:
    """Let normal failure handling preserve aggregates on scheduler SIGTERM."""

    def terminated(signum: int, frame: Any) -> None:
        raise c.Stage10Error("STAGE10_TERMINATED")

    previous = signal.signal(signal.SIGTERM, terminated)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


class SelectorWriter(base_io.RelationWriter):
    """Private variable-width work bytes, not Stage 9 digest-valued columns."""

    def append(self, row: Mapping[str, Any]) -> None:
        c.require(set(row) == set(self.schema.names), "STAGE10_SELECTOR_COLUMNS")
        size = 1024 + 8 * (len(row["sort_key"]) + len(row["payload"]))
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


class SelectorAccumulator:
    """Exact (section,key,payload) set, bounded RAM then immutable spill runs.

    No mutable selector table or per-record database transaction. Unequal
    payloads at one key fail even if they occur in different spill runs.
    """

    def __init__(self, db: Any, root: Path | None, limit: int = SELECTOR_BYTES) -> None:
        c.require(limit > 0, "STAGE10_SELECTOR_BUFFER_INVALID")
        self.db, self.root, self.limit = db, root, limit
        self.items: dict[tuple[int, bytes], bytes] = {}
        self.size = 0
        self.temporary: Any = None
        self.writer: Any = None
        self.schema = pa.schema(
            [
                pa.field("section", pa.uint8(), nullable=False),
                pa.field("sort_key", pa.binary(), nullable=False),
                pa.field("payload", pa.large_binary(), nullable=False),
            ]
        )

    def add(self, section: int, key: bytes, payload: bytes) -> None:
        address = (section, key)
        old = self.items.get(address)
        c.require(old is None or old == payload, "STAGE10_SELECTOR_ID_COLLISION")
        if old is not None:
            return
        weight = 1024 + 8 * (len(key) + len(payload))
        if self.items and self.size + weight > self.limit:
            self.flush()
        self.items[address] = payload
        self.size += weight
        if self.size >= self.limit:
            self.flush()

    def flush(self) -> None:
        if not self.items:
            return
        if self.writer is None:
            self.temporary = tempfile.TemporaryDirectory(
                prefix="selector-", dir=self.root
            )
            Path(self.temporary.name).chmod(0o700)
            self.writer = SelectorWriter(
                Path(self.temporary.name) / "runs",
                self.schema,
                batch_bytes=self.limit,
            )
        for (section, key), payload in self.items.items():
            self.writer.append(
                {"section": section, "sort_key": key, "payload": payload}
            )
        # The writer has its own byte/row ceiling; flush now to release this run.
        self.writer.flush()
        self.items.clear()
        self.size = 0

    def rows(self) -> Iterator[tuple[int, bytes, bytes]]:
        if self.writer is None:
            for (section, key), payload in sorted(self.items.items()):
                yield section, key, payload
            return
        self.flush()
        self.writer.close()
        previous: tuple[int, bytes] | None = None
        last = b""
        query = (
            "SELECT DISTINCT section,sort_key,payload FROM "
            + io.parquet_sql(self.writer.paths)
            + " ORDER BY section,sort_key,payload"
        )
        for row in base_io.sorted_rows(self.db, query, batch_rows=1):
            address = row["section"], row["sort_key"]
            c.require(
                previous != address or row["payload"] == last,
                "STAGE10_SELECTOR_ID_COLLISION",
            )
            if previous != address:
                yield *address, row["payload"]
            previous, last = address, row["payload"]

    def certificate(self) -> Mapping[str, Any]:
        digest, count = hashlib.sha256(), 0
        for section, _, payload in self.rows():
            for chunk in c.framed((section,)):
                digest.update(chunk)
            digest.update(payload)
            count += 1
        return {
            "selector_id": "REFERENCE_WITNESSES_V1",
            "selected_count": count,
            "selected_stream_sha256": digest.digest(),
        }

    def close(self) -> None:
        self.items.clear()
        if self.temporary is not None:
            if self.writer is not None:
                self.writer.close()
            self.temporary.cleanup()


def io_counters() -> dict[str, int]:
    path = Path("/proc/self/io")
    if not path.exists():
        return {}
    return {
        key: int(value)
        for line in path.read_text().splitlines()
        for key, value in [line.split(":")]
        if key in ("rchar", "wchar", "read_bytes", "write_bytes", "syscr", "syscw")
    }

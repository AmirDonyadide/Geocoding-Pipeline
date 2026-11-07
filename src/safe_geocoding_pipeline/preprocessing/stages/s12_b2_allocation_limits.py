"""Selected, opt-in RS1 allocation controls; native aggregate bounds stay external.

These limits are not a storage entitlement or a complete physical model.  In
particular SQLite auxiliary files and DuckDB database/WAL writes still require
the model's separately verified native-allocation bound. No live values default.
"""

from __future__ import annotations

import io as buffers
import json
import os
from pathlib import Path
import threading

import pyarrow as pa
import pyarrow.parquet as pq

from . import s11_semantic_io as upstream
from . import s12_b2_contract as b
from . import s12_storage as storage

VERSION = "stage12_allocation_limits_b2_rs1_v1"
ROLES = (
    "SQLITE",
    "DUCKDB",
    "PARQUET_FILE",
    "RAW_PACK_FILE",
    "COMPRESSED_FRAME",
    "CANDIDATE_BUFFER",
    "EXCLUSIVE_FILE",
    "EVENT_FILE",
    "PREFIX_FILE",
    "COMPARISON_FILE",
    "ADMIN_FILE",
    "CONTROL_BEGIN",
    "CONTROL_FINISH",
)
FIELDS = {
    "schema_version",
    "model_sha256",
    "command_id",
    "review_sha256",
    "native_bound_evidence_sha256",
    "max_compressed_frame_bytes",
    "max_candidate_buffer_bytes",
    "max_arrow_batch_bytes",
    "max_parquet_file_bytes",
    "max_raw_pack_bytes",
    "max_python_write_bytes",
    "sqlite_main_bytes",
    "duckdb_spill_bytes",
    "invocations",
}
POSITIVE = FIELDS - {
    "schema_version",
    "model_sha256",
    "review_sha256",
    "native_bound_evidence_sha256",
    "invocations",
}
DESCRIPTOR = "stage12_allocation_limits_descriptor_b2_rs1_v1"
DESCRIPTOR_SHA256 = "6982929540f4e369d94512413cb3e9ed75f81e5c9c96a4d63b3cb4b1dbf9a5c4"
_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (DESCRIPTOR + ".json")
).read_bytes()
b.require(b.sha(_raw).hex() == DESCRIPTOR_SHA256, "B2_RS1_DESCRIPTOR_CHANGED")
ASSET = json.loads(_raw)
b.require(
    ASSET["record"] == VERSION
    and tuple(ASSET["invocation_roles"]) == ROLES
    and set(ASSET["required_positive_integer_fields"]) == POSITIVE,
    "B2_RS1_DESCRIPTOR_CHANGED",
)


def parse(raw):
    b.require(type(raw) is bytes and len(raw) <= b.MAX_METADATA, "B2_METADATA_LIMIT")
    value = storage.metadata(raw)
    b.require(
        set(value) == FIELDS and value["schema_version"] == VERSION,
        "B2_RS1_LIMIT_FIELDS",
    )
    for field in POSITIVE:
        b.uint(value[field], True)
    for field in ("model_sha256", "review_sha256", "native_bound_evidence_sha256"):
        b.validate_type(value[field], "D")
    b.require(
        type(value["invocations"]) is dict and set(value["invocations"]) == set(ROLES),
        "B2_RS1_LIMIT_FIELDS",
    )
    for maximum in value["invocations"].values():
        b.uint(maximum)
    b.require(
        value["sqlite_main_bytes"] >= 4096
        and value["max_raw_pack_bytes"] <= 64 * 2**20,
        "B2_RS1_LIMIT_VALUE",
    )
    return value


def active():
    return storage.current_allocation_controls()


def validate_binding(value, model, command):
    b.require(
        value["model_sha256"] == b.digest(model)
        and value["command_id"] == command["command_id"]
        and value["native_bound_evidence_sha256"] == command["bound_evidence_sha256"]
        and value["max_python_write_bytes"] <= command["max_generated_bytes"],
        "B2_RS1_LIMIT_BINDING",
    )
    components = {x["component_id"]: x for x in model["components"]}
    for role, component, amount in (
        ("SQLITE", "SQLITE_INDEX", "sqlite_main_bytes"),
        ("DUCKDB", "DUCKDB_SPILL", "duckdb_spill_bytes"),
    ):
        b.require(
            value["invocations"][role] <= command["allocations"][component]
            and (
                value["invocations"][role] == 0
                or value[amount] <= components[component]["per_instance_bytes_bound"]
            ),
            "B2_RS1_LIMIT_BINDING",
        )
    b.require(
        value["invocations"]["DUCKDB"] <= command["allocations"]["DUCKDB_DATABASE"],
        "B2_RS1_LIMIT_BINDING",
    )
    b.require(
        2 * value["max_candidate_buffer_bytes"]
        + value["max_arrow_batch_bytes"]
        + value["max_compressed_frame_bytes"]
        <= command["max_memory_bytes"],
        "B2_RS1_LIMIT_BINDING",
    )
    file_roles = (
        "PARQUET_FILE",
        "RAW_PACK_FILE",
        "EXCLUSIVE_FILE",
        "EVENT_FILE",
        "PREFIX_FILE",
        "COMPARISON_FILE",
        "ADMIN_FILE",
    )
    b.require(
        sum(value["invocations"][x] for x in file_roles)
        <= command["max_generated_inodes"],
        "B2_RS1_LIMIT_BINDING",
    )
    allocations = command["allocations"]
    for role, maximum in (
        ("EVENT_FILE", allocations["EVENTS"]),
        ("CONTROL_BEGIN", allocations["CONTROL_ATTEMPT_METADATA"]),
        ("CONTROL_FINISH", allocations["CONTROL_ATTEMPT_METADATA"]),
        ("CANDIDATE_BUFFER", allocations["CANDIDATE_ORIGINAL"]),
        (
            "COMPRESSED_FRAME",
            allocations["DATA_RAW"]
            + allocations["CONTROL_RAW"]
            + allocations["RAW_PACKS"],
        ),
    ):
        b.require(value["invocations"][role] <= maximum, "B2_RS1_LIMIT_BINDING")


class Controls:
    """Fixed-size counters shared with the sole writer; no per-path cache.

    A claim precedes the allocation and is never refunded, including failures.
    Unclean commands cannot restart: their existing RS1 command claim blocks
    reuse. A later command has its own explicitly cumulative model allocation.
    """

    def __init__(self, value, *, check=lambda: None):
        self.value = parse(b.canonical(value))
        self.check = check
        self.counts = dict.fromkeys(ROLES, 0)
        self.python_bytes = 0
        self.lock = threading.Lock()

    def claim(self, role, size=0):
        self.check()
        b.uint(size)
        with self.lock:
            b.require(
                role in self.counts
                and self.counts[role] < self.value["invocations"][role],
                "B2_RS1_INVOCATION_BUDGET",
            )
            b.require(
                self.python_bytes + size <= self.value["max_python_write_bytes"],
                "B2_RS1_WRITE_BUDGET",
            )
            self.counts[role] += 1
            self.python_bytes += size

    def bytes(self, size):
        self.check()
        b.uint(size)
        with self.lock:
            b.require(
                self.python_bytes + size <= self.value["max_python_write_bytes"],
                "B2_RS1_WRITE_BUDGET",
            )
            self.python_bytes += size

    def usage(self):
        with self.lock:
            return {
                "schema_version": "stage12_allocation_usage_b2_rs1_v1",
                "selection_sha256": b.digest(self.value),
                "invocations": dict(self.counts),
                "python_reserved_bytes": self.python_bytes,
                "native_aggregate_prewrite_bound": "EXTERNAL_EVIDENCE_REQUIRED",
            }

    def reserve_remaining(self, *, report_bytes=65536):
        """Precharge a finite finalization sub-budget before writing usage.

        The original counters retain the entire reservation. The returned
        counters only spend that already charged allowance; they do not issue
        a new selection or refund unused finalization capacity. Leave exactly
        one exclusive report allocation in the original scope.
        """
        self.check()
        b.uint(report_bytes, True)
        with self.lock:
            remaining = {
                role: self.value["invocations"][role] - self.counts[role]
                for role in ROLES
            }
            b.require(remaining["EXCLUSIVE_FILE"] >= 3, "B2_RS1_INVOCATION_BUDGET")
            remaining["EXCLUSIVE_FILE"] -= 1
            byte_allowance = (
                self.value["max_python_write_bytes"] - self.python_bytes - report_bytes
            )
            b.require(byte_allowance > 0, "B2_RS1_WRITE_BUDGET")
            for role, count in remaining.items():
                self.counts[role] += count
            self.python_bytes += byte_allowance
        subrange = dict(self.value)
        subrange["invocations"] = remaining
        subrange["max_python_write_bytes"] = byte_allowance
        return Controls(subrange, check=self.check)

    def persist_usage(self, path):
        # Fixed metadata reserve includes its own report, even on failure. The
        # thirteen fixed role counters and digests fit below this envelope.
        self.claim("EXCLUSIVE_FILE", 65536)
        raw = b.canonical(self.usage())
        b.require(len(raw) <= 65536, "B2_RS1_LIMIT_FIELDS")
        with storage.allocation_controls(None):
            storage.write(path, raw)


def claim(role, size=0):
    controls = active()
    if controls is not None:
        controls.claim(role, size)


def exclusive(path):
    """Classify only actual exclusive calls; streaming chunks use bytes()."""
    role = (
        "EVENT_FILE"
        if path.parent.name == "events"
        else "ADMIN_FILE"
        if path.name.startswith("admin_")
        else "EXCLUSIVE_FILE"
    )
    claim(role)


def compressed(raw, compressor):
    controls = active()
    if controls is not None:
        controls.claim("COMPRESSED_FRAME")
    frame = compressor(raw)
    if controls is not None:
        b.require(
            len(frame) <= controls.value["max_compressed_frame_bytes"],
            "B2_RS1_COMPRESSED_FRAME_LIMIT",
        )
    return frame


class CappedBuffer(buffers.RawIOBase):
    def __init__(self, maximum):
        super().__init__()
        b.uint(maximum, True)
        # Fixed capacity avoids BytesIO's implementation-dependent growth.
        # getvalue creates at most one additional selected-size payload copy.
        self.maximum, self.position = maximum, 0
        self._data = bytearray(maximum)

    def writable(self):
        return True

    def tell(self):
        return self.position

    def write(self, data):
        b.require(not self.closed, "B2_RS1_SINK_FAILED")
        view = memoryview(data)
        b.require(view.c_contiguous, "B2_RS1_NONCONTIGUOUS_BUFFER")
        view = view.cast("B")
        amount = view.nbytes
        b.require(
            self.tell() + amount <= self.maximum, "B2_RS1_MATERIALIZED_BUFFER_LIMIT"
        )
        stop = self.position + amount
        self._data[self.position : stop] = view
        self.position = stop
        return amount

    def getvalue(self):
        return bytes(memoryview(self._data)[: self.position])

    def close(self):
        try:
            super().close()
        finally:
            self._data = None


def candidate_bytes(table):
    controls = active()
    if controls is None:
        sink = pa.BufferOutputStream()
        pq.write_table(table, sink, compression="zstd")
        return sink.getvalue().to_pybytes()
    controls.claim("CANDIDATE_BUFFER")
    b.require(
        table.nbytes <= controls.value["max_arrow_batch_bytes"],
        "B2_RS1_ARROW_BATCH_LIMIT",
    )
    with CappedBuffer(controls.value["max_candidate_buffer_bytes"]) as sink:
        pq.write_table(table, sink, compression="zstd")
        return sink.getvalue()


class PhysicalSink(buffers.RawIOBase):
    """Exclusive sequential physical sink including footer and failed writes.

    The entire file envelope is charged before open. Native Parquet may issue
    arbitrary write sizes; crossing writes fail before touching the file. No
    close retry can append a footer after a prior failed write.
    """

    def __init__(self, path, maximum, role):
        super().__init__()
        self.fd = None
        controls = active()
        b.require(controls is not None, "B2_RS1_LIMIT_CONTEXT")
        controls.claim(role, maximum)
        storage.private_directory(path.parent)
        self.controls = controls
        self.maximum, self.position, self.failed = maximum, 0, False
        self.fd = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )

    def writable(self):
        return True

    def tell(self):
        return self.position

    def fileno(self):
        if self.fd is None:
            raise ValueError("closed RS1 sink")
        return self.fd

    def write(self, data):
        b.require(not self.closed and not self.failed, "B2_RS1_SINK_FAILED")
        try:
            view = memoryview(data)
            b.require(view.c_contiguous, "B2_RS1_NONCONTIGUOUS_BUFFER")
            view = view.cast("B")
            amount = view.nbytes
            b.require(
                self.position + amount <= self.maximum, "B2_RS1_PARQUET_PHYSICAL_LIMIT"
            )
            self.controls.check()
            while view:
                self.controls.check()
                n = os.write(self.fd, view)
                b.require(n > 0, "B2_RS1_SINK_FAILED")
                self.position += n
                view = view[n:]
            return amount
        except BaseException:
            self.failed = True
            raise

    def flush(self):
        if not self.closed and self.fd is not None:
            try:
                self.controls.check()
                os.fsync(self.fd)
            except BaseException:
                self.failed = True
                raise

    def close(self):
        if not self.closed:
            primary = None
            try:
                super().close()
            except BaseException as error:
                self.failed = True
                primary = error
            finally:
                if self.fd is not None:
                    try:
                        os.close(self.fd)
                    except BaseException as error:
                        self.failed = True
                        if primary is None:
                            primary = error
                    finally:
                        self.fd = None
            if primary is not None:
                raise primary


class BoundedRelationWriter(upstream.RelationWriter):
    def __init__(self, *args, **kwargs):
        self.failed = False
        super().__init__(*args, **kwargs)

    def append(self, row):
        b.require(not self.failed, "B2_RS1_SINK_FAILED")

        # Same upper estimate as the accepted writer, checked before holding an
        # oversized scalar. Rejection retains the original evidence unchanged.
        def estimate(value):
            if isinstance(value, dict):
                return 128 + sum(estimate(x) for x in value.values())
            if isinstance(value, str):
                return 64 + sum(
                    len(value[i : i + 65536].encode("utf8"))
                    for i in range(0, len(value), 65536)
                )
            if isinstance(value, bytes):
                return 64 + len(value)
            return 64

        b.require(
            sum(estimate(v) for v in row.values()) <= self.batch_bytes,
            "B2_RS1_ARROW_BATCH_LIMIT",
        )
        super().append(row)

    def _open(self):
        controls = active()
        b.require(controls is not None, "B2_RS1_LIMIT_CONTEXT")
        path = self.directory / f"part-{len(self.paths):06}.parquet"
        try:
            self._physical = PhysicalSink(
                path, controls.value["max_parquet_file_bytes"], "PARQUET_FILE"
            )
            self.paths.append(path)
            self.writer = pq.ParquetWriter(
                self._physical, self.schema, compression="zstd", version="2.6"
            )
        except BaseException:
            self.failed = True
            physical = getattr(self, "_physical", None)
            if physical is not None:
                physical.failed = True
                try:
                    physical.close()
                except BaseException:
                    pass  # Preserve the initiating allocation/header failure.
            raise

    def flush(self):
        b.require(not self.failed, "B2_RS1_SINK_FAILED")
        if not self.buffer:
            return
        try:
            controls = active()
            table = pa.Table.from_pylist(self.buffer, schema=self.schema)
            b.require(
                table.nbytes <= controls.value["max_arrow_batch_bytes"],
                "B2_RS1_ARROW_BATCH_LIMIT",
            )
            if self.writer is None:
                self._open()
            self.writer.write_table(table)
        except BaseException:
            self.failed = True
            physical = getattr(self, "_physical", None)
            if physical is not None:
                physical.failed = True
                try:
                    physical.close()
                except BaseException:
                    pass  # Closing cannot replace a failed encoding/write.
            native, self.writer = self.writer, None
            if native is not None:
                try:
                    native.close()
                except BaseException:
                    pass  # The poisoned closed sink cannot accept a footer.
            raise
        self.file_bytes += table.nbytes
        self.buffer.clear()
        self.buffer_bytes = 0
        if self.file_bytes >= self.target_file_bytes:
            self._close_file()

    def _close_file(self):
        if self.writer is not None:
            primary = None
            try:
                self.writer.close()
            except BaseException as error:
                primary = error
            finally:
                self.writer = None
                try:
                    self._physical.close()
                except BaseException as error:
                    if primary is None:
                        primary = error
            if primary is not None:
                self.failed = self._physical.failed = True
                raise primary
            self.file_bytes = 0


def relation_writer(*args, **kwargs):
    controls = active()
    if controls is None:
        return upstream.RelationWriter(*args, **kwargs)
    kwargs["batch_bytes"] = min(
        kwargs.get("batch_bytes", 64 * 2**20), controls.value["max_arrow_batch_bytes"]
    )
    return BoundedRelationWriter(*args, **kwargs)


def sqlite_before(path):
    controls = active()
    if controls is not None:
        controls.claim("SQLITE")
        if Path(path).exists():
            b.require(
                Path(path).stat().st_size <= controls.value["sqlite_main_bytes"],
                "B2_RS1_SQLITE_MAIN_LIMIT",
            )


def sqlite_cap(db, requested=None):
    controls = active()
    if controls is None:
        return requested
    page = db.execute("pragma page_size").fetchone()[0]
    maximum = controls.value["sqlite_main_bytes"]
    if requested is not None:
        maximum = min(maximum, requested)
    pages = maximum // page
    b.require(
        pages > 0 and db.execute("pragma page_count").fetchone()[0] <= pages,
        "B2_RS1_SQLITE_MAIN_LIMIT",
    )
    actual = db.execute("pragma max_page_count=" + str(pages)).fetchone()[0]
    b.require(actual <= pages, "B2_RS1_SQLITE_MAIN_LIMIT")
    return maximum


def duck_connect(connect, *args, **kwargs):
    controls = active()
    if controls is not None:
        controls.claim("DUCKDB")
    db = connect(*args, **kwargs)
    if controls is not None:
        try:
            db.execute(
                "SET max_temp_directory_size='"
                + str(controls.value["duckdb_spill_bytes"])
                + "B'"
            )
        except BaseException:
            db.close()
            raise
    return db

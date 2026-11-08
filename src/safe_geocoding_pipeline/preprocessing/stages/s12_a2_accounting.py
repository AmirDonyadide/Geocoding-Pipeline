"""Opt-in A-only finite read/check accounting. No capacity or M2 assertion."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import sys
import threading

VERSION = "stage12_a2_accounting_inventory_v1"
CHUNK = 4096
ORIGINAL_READ_BYTES = 2**20
MODULES = ("_hashlib", "_ssl", "_sqlite3", "_duckdb", "pyarrow.lib")
PHASES = ("PREFLIGHT", "KERNEL_PRE", "RUNTIME", "KERNEL_POST", "SOURCE", "CAPTURE_CLOSE", "CAPTURE_OPEN", "REVIEW", "FINAL_WRITE", "FINAL_RECHECK", "FINAL_CLOSE", "FINAL_OPEN", "FINISHED")
IDENTITY = ("device", "inode", "mode", "uid", "gid", "nlink", "bytes", "mtime_ns", "ctime_ns")


class AccountingError(RuntimeError):
    pass


def need(condition, code="A2_ACCOUNTING_INVALID"):
    if not condition:
        raise AccountingError(code)


def fields(row, names):
    need(type(row) is dict and set(row) == set(names))


def uint(value, positive=False):
    need(type(value) is int and (value > 0 if positive else value >= 0) and value < 2**63)


def identity(info):
    return dict(zip(IDENTITY, (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)))


def runtime_roots():
    return tuple(Path(p).resolve(strict=True) for p in (sys.prefix, sys.base_prefix))


def validate(inventory, source_rows):
    fields(inventory, ("version", "backends", "sources"))
    need(inventory["version"] == VERSION)
    backends, sources = inventory["backends"], inventory["sources"]
    need(type(backends) is list and len(backends) == len(MODULES))
    need(type(sources) is list and 1 <= len(sources) <= 128)
    paths = set()
    for ordinal, row in enumerate(backends, 1):
        fields(row, ("ordinal", "module", "path", "identity", "stat_scope", "sha256"))
        need(row["ordinal"] == ordinal and type(row["ordinal"]) is int and row["module"] == MODULES[ordinal - 1])
        need(row["stat_scope"] == "PREPARATION_HOST_SNAPSHOT")
        need(type(row["sha256"]) is str and len(row["sha256"]) == 64 and all(c in "0123456789abcdef" for c in row["sha256"]))
        need(type(row["path"]) is str)
        try:
            encoded = row["path"].encode("ascii")
        except UnicodeError:
            raise AccountingError("A2_BACKEND_PATH_UNSUPPORTED") from None
        path = Path(row["path"])
        need(len(encoded) <= 1024 and path.is_absolute() and ".." not in path.parts)
        need(not any(p in {".ssh", "credentials", ".git", ".config"} or p.startswith(".env") for p in path.parts))
        need(str(path) not in paths); paths.add(str(path))
        fields(row["identity"], IDENTITY)
        for key, value in row["identity"].items():
            # Native dev/ino identifiers are unsigned64 (PanFS uses bit63).
            need(type(value) is int and 0 <= value < 2**64)
            if key == "bytes":
                uint(value)
        need(stat.S_ISREG(row["identity"]["mode"]) and row["identity"]["nlink"] == 1 and row["identity"]["bytes"] > 0)
    need([r["path"] for r in sources] == [r["path"] for r in source_rows])
    for row in sources:
        fields(row, ("path", "bytes")); uint(row["bytes"])
        need(row["bytes"] <= 4 * 2**20)
    # No unknown-to-zero default or caller-selected permissive multiplier.
    bounds(inventory)
    return inventory


def bounds(inventory):
    """Closed invocation graph; pessimistic one-byte short reads/writes allowed.

    Each hash pass: <=bytes+1 read calls/file (short reads included), one
    guard before each read plus entry/pre-stat/post-stat guards. Metadata writes: <=charged bytes
    successful os.write calls plus14 guards/creation (includes writer/persist
    wrappers). Root creation/close, source passes, kernel readers and bounded
    verifier entry/exit calls are separately charged. No refund of A's tail.
    """
    b = sum(r["identity"]["bytes"] for r in inventory["backends"])
    s = sum(r["bytes"] for r in inventory["sources"])
    n = len(inventory["sources"])
    hash_a = b + 4 * len(MODULES)
    source_a = s + 4 * n
    # Kernel: two passes, <=256 read guards +32 ancestor guards/pass;
    # entry/exit and immutable startup/publication/opening points enumerated.
    kernel_a = 2 * (256 + 32)
    # Up to selected creations, partial writes consume >=one precharged byte.
    write_a = 32 * 2**20 + 14 * 256
    write_f = 64 * 2**20 + 14 * 256
    # Collection: verify_bootstrap5, writer.close2, terminal1.
    # Final: verify_review6 twice, writer.close2, open_completed8, terminal1.
    fixed_a, fixed_f = 8, 23
    a = hash_a + len(MODULES) + 1 + 2 * source_a + kernel_a + write_a + fixed_a
    f = 3 * hash_a + 3 * source_a + write_f + fixed_f
    # Failure grammar permits512 manifest entries before duplicate rejection.
    # Bootstrap verifier521 originals/call; final verifier516/call. Six/two
    # calls cover producer+independent checks.47 administrative originals
    # cover owner/proof/review, selection, ack, runtime and parent records.
    # Up to512 write-readbacks; each original is bounded by MAX_READ+1.
    metadata_reads = 6 * 521 + 2 * 516 + 47 + 512
    result = dict(collect_checks=a, final_checks=f, reserved_total_checks=a + f,
                  backend_bytes_per_pass=b, source_bytes_per_pass=s,
                  backend_passes=4, source_passes=5,
                  hash_read_calls=4 * (b + 5) + 5 * (s + n),
                  original_hash_bytes=4 * (b + 5) + 5 * (s + n),
                  metadata_original_read_calls=metadata_reads,
                  metadata_validation_bytes=metadata_reads * (ORIGINAL_READ_BYTES + 1),
                  kernel_original_read_bytes=2 * 2 * 2**20,
                  # Resource I/O precedes the count predicate. Include the
                  # first rejected check in each phase (no retry/refund).
                  guard_kernel_read_bytes=(a + f + 2) * (65 + 8193),
                  shell_review_poll_invocations=120)
    # Explicit preparation graph: <=four read-only backend hash sweeps,
    # two source sweeps and eight canonical selection/owner binding parses
    # (each <=five original reads). Not Git/import/native internal I/O.
    result["preparation_selected_read_bytes"] = 4 * b + 2 * s + 8 * 5 * (ORIGINAL_READ_BYTES + 1)
    for value in result.values():
        uint(value, True)
    return result


def validate_watermarks(row, inventory, stage=0):
    fields(row, ("version", "stage", "phase_ordinal", "operation_ordinal", "backend_ordinal", "backend_pass_ordinal", "source_ordinal", "checks", "backend_calls", "source_calls", "completed_bytes", "completed_chunks", "read_calls", "read_bytes", "active_bytes", "active_chunks", "collect_checks_reserved", "cumulative_checks_reserved"))
    need(row["version"] == "stage12_a2_accounting_watermarks_v1")
    for key, value in row.items():
        if key != "version": uint(value)
    b = bounds(inventory)
    need(row["stage"] == stage and row["phase_ordinal"] < len(PHASES)
         and row["operation_ordinal"] <= 9
         and row["backend_ordinal"] <= 5 and row["source_ordinal"] <= len(inventory["sources"])
         and row["backend_calls"] <= (5 if stage == 0 else 15)
         and row["backend_pass_ordinal"] == (row["backend_calls"] + 4) // 5
         and row["source_calls"] <= (2 if stage == 0 else 3)
         and row["checks"] <= b["collect_checks" if stage == 0 else "final_checks"]
         and row["collect_checks_reserved"] == b["collect_checks"]
         and row["cumulative_checks_reserved"] == b["collect_checks"] + (b["final_checks"] if stage else 0)
         and row["completed_chunks"] <= row["read_calls"] <= b["hash_read_calls"]
         and row["active_bytes"] <= row["completed_bytes"] <= row["read_bytes"] <= b["original_hash_bytes"]
         and row["active_chunks"] <= row["completed_chunks"]
         and row["completed_chunks"] <= row["completed_bytes"] <= CHUNK * row["completed_chunks"]
         and row["active_chunks"] <= row["active_bytes"] <= CHUNK * row["active_chunks"]
         and row["read_bytes"] <= CHUNK * row["read_calls"]
         and row["checks"] >= row["read_calls"])


def validate_prefix(row, inventory, context):
    need(context in ("capture", "final_write", "terminal"))
    stage = 0 if context == "capture" else 1
    validate_watermarks(row, inventory, stage)
    backend_passes, source_passes = {"capture": (1, 2), "final_write": (1, 1), "terminal": (3, 3)}[context]
    b = bounds(inventory); n = len(inventory["sources"])
    count = backend_passes * 5 + source_passes * n
    size = backend_passes * b["backend_bytes_per_pass"] + source_passes * b["source_bytes_per_pass"]
    minimum_chunks = backend_passes * sum((x["identity"]["bytes"] + CHUNK - 1) // CHUNK for x in inventory["backends"]) + source_passes * sum((x["bytes"] + CHUNK - 1) // CHUNK for x in inventory["sources"])
    phase = {"capture": "CAPTURE_CLOSE", "final_write": "FINAL_WRITE", "terminal": "FINISHED"}[context]
    active = inventory["sources"][-1]["bytes"] if context == "capture" else inventory["backends"][-1]["identity"]["bytes"]
    need(row["phase_ordinal"] == PHASES.index(phase)
         and row["backend_calls"] == backend_passes * 5
         and row["backend_pass_ordinal"] == backend_passes
         and row["source_calls"] == source_passes
         and row["source_ordinal"] == n and row["backend_ordinal"] == 5
         and row["completed_bytes"] == row["read_bytes"] == size
         and row["completed_chunks"] >= minimum_chunks
         and row["read_calls"] == row["completed_chunks"] + count
         and row["checks"] >= row["read_calls"] + 3 * count + (6 if context == "capture" else 0)
         and row["active_bytes"] == active,
         "A2_ACCOUNTING_PREFIX_INCOMPLETE")


class Ledger:
    def __init__(self, inventory, stage):
        need(stage in ("collect", "final")); self.inventory = inventory
        self.stage = stage; self.bound = bounds(inventory); self.lock = threading.RLock()
        self.runtime_roots = runtime_roots()
        self.phase = 0 if stage == "collect" else 7
        self.operation = 0
        self.checks = self.backend_ordinal = self.source_ordinal = 0
        self.completed_bytes = self.completed_chunks = self.read_calls = self.read_bytes = 0
        self.active_bytes = self.active_chunks = 0
        self.backend_calls = self.source_calls = 0

    def enter(self, name):
        ordinal = PHASES.index(name)
        with self.lock:
            need(ordinal >= self.phase, "A2_ACCOUNTING_PHASE_ORDER")
            self.phase = ordinal
            self.operation = 0

    def op(self, ordinal):
        with self.lock:
            need(type(ordinal) is int and 0 <= ordinal <= 9)
            self.operation = ordinal

    def tick(self):
        with self.lock:
            self.checks += 1
            need(self.checks <= self.bound[self.stage + "_checks"], "A2_DERIVED_CHECK_LIMIT")

    def snapshot(self):
        with self.lock:
            return dict(version="stage12_a2_accounting_watermarks_v1", stage=0 if self.stage == "collect" else 1,
                        phase_ordinal=self.phase, operation_ordinal=self.operation, backend_ordinal=self.backend_ordinal,
                        backend_pass_ordinal=(self.backend_calls + 4) // 5,
                        source_ordinal=self.source_ordinal, checks=self.checks,
                        backend_calls=self.backend_calls, source_calls=self.source_calls,
                        completed_bytes=self.completed_bytes, completed_chunks=self.completed_chunks,
                        read_calls=self.read_calls, read_bytes=self.read_bytes, active_bytes=self.active_bytes, active_chunks=self.active_chunks,
                        collect_checks_reserved=self.bound["collect_checks"],
                        cumulative_checks_reserved=self.bound["collect_checks"] + (self.bound["final_checks"] if self.stage == "final" else 0))

    def _hash(self, path, expected_size, check, expected_identity=None, *, reader=None, preparation_identity=False):
        from .s12_wf_ap2_scratch import lease
        with lease("HASH"):
            return self._hash_leased(path, expected_size, check, expected_identity,
                                     reader=reader, preparation_identity=preparation_identity)

    def _hash_leased(self, path, expected_size, check, expected_identity=None, *, reader=None, preparation_identity=False):
        self.active_bytes = self.active_chunks = 0
        self.op(1)
        path = Path(path); check()
        need(path.resolve(strict=True) == path, "A2_HASH_PATH_CHANGED")
        before = path.stat(follow_symlinks=False)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size == expected_size, "A2_HASH_INVENTORY_CHANGED")
        if expected_identity is not None:
            actual = identity(before)
            # st_dev/st_ino are namespace-local. A preparation-host snapshot
            # is not an immutable cross-host identifier. Full identity is
            # nevertheless checked before/after against this actual open fd.
            keys = set(IDENTITY) - {"device", "inode"} if preparation_identity else set(IDENTITY)
            need(all(actual[k] == expected_identity[k] for k in keys), "A2_HASH_INVENTORY_CHANGED")
        self.active_bytes = self.active_chunks = 0
        digest = hashlib.sha256(); buffer = bytearray(CHUNK); fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            need(identity(os.fstat(fd)) == identity(before), "A2_HASH_CHANGED")
            remaining = expected_size
            while True:
                self.op(2)
                check()
                want = min(CHUNK, remaining) if remaining else 1
                with self.lock:
                    self.read_calls += 1
                    need(self.read_calls <= self.bound["hash_read_calls"], "A2_HASH_READ_LIMIT")
                count = (reader or os.readv)(fd, [memoryview(buffer)[:want]])
                need(type(count) is int and 0 <= count <= want, "A2_HASH_READ_INVALID")
                with self.lock:
                    self.read_bytes += count
                    need(self.read_bytes <= self.bound["original_hash_bytes"], "A2_HASH_BYTE_LIMIT")
                if not remaining:
                    need(count == 0, "A2_HASH_GREW"); break
                need(count > 0, "A2_HASH_TRUNCATED")
                digest.update(memoryview(buffer)[:count]); remaining -= count
                with self.lock:
                    self.completed_bytes += count; self.active_bytes += count
                    self.completed_chunks += 1; self.active_chunks += 1
                    need(self.completed_bytes <= self.bound["original_hash_bytes"], "A2_HASH_BYTE_LIMIT")
            self.op(3); check()
            need(path.resolve(strict=True) == path, "A2_HASH_PATH_CHANGED")
            need(identity(os.fstat(fd)) == identity(before) == identity(path.stat(follow_symlinks=False)), "A2_HASH_CHANGED")
            check(); return digest.hexdigest()
        finally:
            primary = sys.exc_info()[0] is not None
            try:
                os.close(fd)
            except OSError:
                if not primary: raise

    def backend(self, name, path, check):
        need(name in MODULES, "A2_BACKEND_UNSUPPORTED")
        ordinal = MODULES.index(name) + 1
        with self.lock:
            need(ordinal == self.backend_calls % 5 + 1, "A2_BACKEND_ORDER")
            self.backend_calls += 1
            need(self.backend_calls <= (5 if self.stage == "collect" else 15), "A2_BACKEND_INVOCATION_LIMIT")
            self.backend_ordinal = ordinal
        row = self.inventory["backends"][ordinal - 1]
        need(str(path) == row["path"], "A2_BACKEND_PATH_CHANGED")
        need(any(Path(path).is_relative_to(root) for root in self.runtime_roots), "A2_BACKEND_RUNTIME_SCOPE")
        digest = self._hash(path, row["identity"]["bytes"], check, row["identity"], preparation_identity=True)
        need(digest == row["sha256"], "A2_BACKEND_HASH_CHANGED")
        return digest

    def sources(self, selection, check, root=None):
        with self.lock:
            self.source_calls += 1
            need(self.source_calls <= (2 if self.stage == "collect" else 3), "A2_SOURCE_INVOCATION_LIMIT")
        for ordinal, (source, size) in enumerate(zip(selection["source_files"], self.inventory["sources"]), 1):
            self.source_ordinal = ordinal
            need(source["path"] == size["path"], "A2_SOURCE_INVENTORY_CHANGED")
            need(self._hash(Path(root or selection["paths"]["source"]) / source["path"], size["bytes"], check) == source["sha256"], "A2_SOURCE_HASH_CHANGED")

    def verify_backends(self, runtime, check):
        rows = runtime["wf_ap2_runtime"]["backends"]
        need(type(rows) is list and len(rows) == 5, "A2_RUNTIME_INVENTORY_INCOMPLETE")
        for row, selected in zip(rows, self.inventory["backends"]):
            need(row["module"] == selected["module"] and row["binary_name"] == Path(selected["path"]).name, "A2_RUNTIME_INVENTORY_CHANGED")
            need(self.backend(row["module"], Path(selected["path"]), check) == row["binary_sha256"], "A2_RUNTIME_HASH_CHANGED")


# Closed safe diagnostics; arbitrary exception arguments are never output.
ERROR_CODES = frozenset(('A2_ACCOUNTING_INVALID', 'A2_ACCOUNTING_PHASE_ORDER', 'A2_ACCOUNTING_PREFIX_INCOMPLETE', 'A2_BACKEND_HASH_CHANGED', 'A2_BACKEND_INVOCATION_LIMIT', 'A2_BACKEND_ORDER', 'A2_BACKEND_PATH_CHANGED', 'A2_BACKEND_PATH_UNSUPPORTED', 'A2_BACKEND_RUNTIME_SCOPE', 'A2_BACKEND_UNSUPPORTED', 'A2_DERIVED_CHECK_LIMIT', 'A2_HASH_BYTE_LIMIT', 'A2_HASH_CHANGED', 'A2_HASH_GREW', 'A2_HASH_INVENTORY_CHANGED', 'A2_HASH_PATH_CHANGED', 'A2_HASH_READ_INVALID', 'A2_HASH_READ_LIMIT', 'A2_HASH_TRUNCATED', 'A2_RUNTIME_HASH_CHANGED', 'A2_RUNTIME_INVENTORY_CHANGED', 'A2_RUNTIME_INVENTORY_INCOMPLETE', 'A2_SOURCE_HASH_CHANGED', 'A2_SOURCE_INVENTORY_CHANGED', 'A2_SOURCE_INVOCATION_LIMIT'))

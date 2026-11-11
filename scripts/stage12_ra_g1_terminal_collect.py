#!/usr/bin/env python3
"""Task-scoped, fail-closed terminal-original streaming codec.

This tool neither connects to a host nor submits a job. Collection integrity is
not native/scientific acceptance. Native use requires separate placement and
pool approval; the existing shared execution guard is mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import time

VERSION = "stage12_terminal_stream_v1"
MAGIC = b"S12TC001\n"
SCOPE = "TASK_ONLY_COLLECTION_INTEGRITY_NOT_NATIVE_PASS"
LABEL = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")
FORBIDDEN = {".git", ".ssh", ".aws", ".config", "credentials", "secrets", "HOLDOUT"}
LIMIT_KEYS = {
    "members", "payload_bytes", "manifest_bytes", "record_bytes", "path_bytes",
    "name_bytes", "depth", "sort_records", "sort_buffer_bytes", "merge_fan_in",
    "chunk_bytes", "wire_bytes", "read_bytes", "write_bytes", "creations",
    "operations", "scanned_entries", "seconds",
}
IDENTITY_FIELDS = ("dev", "ino", "mode", "uid", "gid", "nlink", "size", "mtime_ns", "ctime_ns")
STOP_CODES = frozenset({
    "ANCESTOR",
    "ANCESTOR_CHANGED",
    "ARCHIVE_CHANGED",
    "BINDING",
    "CANONICAL",
    "CLOSE_UNCERTAIN",
    "CREATIONS",
    "DATA_MEMBERSHIP",
    "DEADLINE",
    "DEPTH",
    "DEVICE",
    "DUPLICATE",
    "DUPLICATE_KEY",
    "EMPTY_MANIFEST",
    "FRAME",
    "IDENTITY",
    "INTEGER",
    "JSON",
    "LIMITS",
    "LINK",
    "MAGIC",
    "MANIFEST",
    "MEMBER_PATH",
    "OFFLINE_LIMITS",
    "OFFLINE_ROOT",
    "OPERATIONS",
    "ORDER",
    "OUTPUT",
    "OUTPUT_CHANGED",
    "OUTPUT_MEMBERSHIP",
    "OUTPUT_OVERLAP",
    "PATH",
    "PAYLOAD",
    "PAYLOAD_HASH",
    "PRIVATE",
    "PROTOCOL",
    "READ_BYTES",
    "RECORD",
    "REQUIRED_LOG",
    "REQUIRED_LOGS",
    "ROOTS",
    "ROOT_OVERLAP",
    "ROW",
    "SCANNED_ENTRIES",
    "SCOPE",
    "SELECTION",
    "SELECTION_CHANGED",
    "SELECTION_HASH",
    "SELECTION_SHORT",
    "SELECTION_SIZE",
    "SORT_MEMORY",
    "SOURCE_CHANGED",
    "SOURCE_IDENTITY",
    "SOURCE_SHORT",
    "SPECIAL",
    "SPILL_CHANGED",
    "STATUS",
    "SUMMARY",
    "TRAILING",
    "TRUNCATED",
    "UNCLASSIFIED",
    "WIRE_BYTES",
    "WIRE_READ",
    "WIRE_WRITE",
    "WRITE",
    "WRITE_BYTES",
})


class Stop(RuntimeError):
    """Static, non-data-bearing failure."""


def need(value, code):
    if not value:
        raise Stop(code)


def close_owned(budget, descriptors):
    """Attempt every owned close; preserve an active failure and mark uncertainty."""
    primary = sys.exc_info()[1]
    uncertain = False
    for fd in descriptors:
        if fd is None:
            continue
        try:
            os.close(fd)
        except BaseException:
            uncertain = True
    if uncertain:
        if budget is not None:
            budget.cleanup_uncertain = True
        if type(primary) is Stop:
            primary.cleanup_uncertain = True
        if primary is None:
            raise Stop("CLOSE_UNCERTAIN")


def uint(value, positive=False):
    need(type(value) is int and (0 < value if positive else 0 <= value) and value < 2**64,
         "INTEGER")
    return value


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "DUPLICATE_KEY")
        result[key] = value
    return result


def parse(raw):
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(Stop("JSON")))
        need(canonical(value) == raw, "CANONICAL")
        return value
    except Stop:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise Stop("JSON") from None


def ident(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def path_text(value):
    need(type(value) is str and value and "\\" not in value
         and not any(ord(ch) < 32 or ord(ch) == 127 for ch in value), "PATH")
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise Stop("PATH") from None
    need(not any(p in FORBIDDEN or p.startswith(".env") for p in Path(value).parts), "PATH")
    return value


def absolute(value):
    value = path_text(value)
    result = Path(value)
    need(result.is_absolute() and str(result) == os.path.normpath(value)
         and ".." not in result.parts, "PATH")
    return result


def ancestors(path, links=True):
    """Bounded lexical ancestors; never follow a symlink."""
    need(len(path.parts) <= 81 and len(os.fsencode(path)) <= 8192, "ANCESTOR")
    chain = []
    for parent in reversed(path.parents):
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode), "ANCESTOR")
        chain.append((parent, ident(info)[:6 if links else 5]))
    need(len(chain) <= 80, "ANCESTOR")
    return chain


def check_ancestors(chain):
    for path, expected in chain:
        need(ident(path.lstat())[:len(expected)] == expected, "ANCESTOR_CHANGED")


def private(info, kind, uid, gid=None):
    wanted = stat.S_ISDIR if kind == "DIR" else stat.S_ISREG
    need(wanted(info.st_mode) and stat.S_IMODE(info.st_mode) == (0o700 if kind == "DIR" else 0o600)
         and info.st_uid == uid and (gid is None or info.st_gid == gid), "PRIVATE")
    if kind == "FILE":
        need(info.st_nlink == 1, "LINK")
    for value in ident(info):
        uint(value)


def contained(path, root):
    return path == root or path.is_relative_to(root)


def selection_read(path, expected, entered):
    need(type(expected) is str and HEX.fullmatch(expected), "SELECTION_HASH")
    chain = ancestors(path)
    before = path.lstat()
    private(before, "FILE", os.geteuid())
    need(before.st_size <= 65536, "SELECTION_SIZE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        need(ident(os.fstat(fd)) == ident(before), "SELECTION_CHANGED")
        parts, left = [], before.st_size
        while left:
            need(time.monotonic_ns() < entered + 5_000_000_000, "DEADLINE")
            raw = os.read(fd, min(4096, left))
            need(raw and len(raw) <= left, "SELECTION_SHORT")
            parts.append(raw)
            left -= len(raw)
        need(not os.read(fd, 1) and ident(os.fstat(fd)) == ident(path.lstat()) == ident(before),
             "SELECTION_CHANGED")
    finally:
        close_owned(None, (fd,))
    check_ancestors(chain)
    raw = b"".join(parts)  # hard 64KiB control record only, never artifact data
    need(hashlib.sha256(raw).hexdigest() == expected, "SELECTION_HASH")
    return parse(raw)


class Selection:
    def __init__(self, value, offline, test_root):
        need(type(value) is dict and set(value) == {
            "version", "scope", "state", "approval_sha256", "source_uid", "source_gid",
            "roots", "external_files", "required_logs", "limits", "valid_until_epoch_ns",
            "job_id", "source_git_sha",
        }, "SELECTION")
        need(value["version"] == VERSION, "SELECTION")
        if offline:
            need(value["scope"] == "TEST_ONLY_INVENTED" and value["state"] == "TEST_ONLY"
                 and value["approval_sha256"] is None and test_root is not None, "SCOPE")
        else:
            need(value["scope"] == "NATIVE_TERMINAL_ORIGINALS" and value["state"] == "ISSUED"
                 and type(value["approval_sha256"]) is str
                 and HEX.fullmatch(value["approval_sha256"])
                 and value["approval_sha256"] != "0" * 64, "UNISSUED")
        uint(value["job_id"], not offline)
        need(type(value["source_git_sha"]) is str
             and re.fullmatch(r"[0-9a-f]{40}", value["source_git_sha"])
             and (offline or value["source_git_sha"] != "0"*40), "SOURCE_IDENTITY")
        self.value = value
        self.sha = hashlib.sha256(canonical(value)).hexdigest()
        self.uid, self.gid = uint(value["source_uid"]), uint(value["source_gid"])
        self.end_epoch = uint(value["valid_until_epoch_ns"], True)
        limits = value["limits"]
        need(type(limits) is dict and set(limits) == LIMIT_KEYS, "LIMITS")
        for number in limits.values():
            uint(number, True)
        need(limits["members"] <= 262144 and 512 <= limits["record_bytes"] <= 16384
             and limits["path_bytes"] <= 4096 and limits["name_bytes"] <= 255
             and limits["depth"] <= 64 and 2 <= limits["sort_records"] <= 4096
             and 2 <= limits["merge_fan_in"] <= 32
             and 4096 <= limits["chunk_bytes"] <= 1048576
             and limits["sort_buffer_bytes"] >= limits["sort_records"]
             * (limits["record_bytes"] + limits["path_bytes"])
             and limits["seconds"] <= 8400 and limits["creations"] >= 4
             and limits["write_bytes"] >= 65536, "LIMITS")
        if offline:
            need(limits["members"] <= 4096 and limits["payload_bytes"] <= 4 * 2**20
                 and limits["wire_bytes"] <= 16 * 2**20
                 and limits["manifest_bytes"] <= 4 * 2**20, "OFFLINE_LIMITS")
        self.limits = limits
        self.roots, self.external = {}, {}
        for field, target in (("roots", self.roots), ("external_files", self.external)):
            rows = value[field]
            need(type(rows) is list and len(rows) <= 16, "ROOTS")
            for row in rows:
                need(type(row) is dict and set(row) == {"label", "path"}
                     and type(row["label"]) is str and LABEL.fullmatch(row["label"])
                     and row["label"] not in self.roots and row["label"] not in self.external,
                     "ROOTS")
                target[row["label"]] = absolute(row["path"])
        need(self.roots and len(self.roots) + len(self.external) <= 16, "ROOTS")
        physical = list(self.roots.values()) + list(self.external.values())
        for i, path in enumerate(physical):
            if offline:
                need(contained(path, test_root) and path != test_root, "OFFLINE_ROOT")
            for other in physical[:i]:
                need(not contained(path, other) and not contained(other, path), "ROOT_OVERLAP")
        logs = value["required_logs"]
        need(type(logs) is list and 1 <= len(logs) <= 16 and len(set(logs)) == len(logs),
             "REQUIRED_LOGS")
        self.logs = set()
        for path in logs:
            self.relative(path)
            head = path.split("/")[0]
            need(head in self.roots or (head in self.external and path == head), "REQUIRED_LOGS")
            self.logs.add(path)

    def relative(self, value):
        value = path_text(value)
        pieces = value.split("/")
        need(not value.startswith("/") and all(p not in ("", ".", "..") for p in pieces)
             and len(pieces) <= self.limits["depth"]
             and len(value.encode()) <= self.limits["path_bytes"]
             and all(len(p.encode()) <= self.limits["name_bytes"] for p in pieces), "MEMBER_PATH")
        return value

    def disjoint_output(self, output, test_root=None):
        for source in list(self.roots.values()) + list(self.external.values()):
            need(not contained(output, source) and not contained(source, output), "OUTPUT_OVERLAP")
        if test_root is not None:
            need(contained(output, test_root) and output != test_root, "OFFLINE_ROOT")


class Budget:
    def __init__(self, selected, entered):
        self.l = selected.limits
        self.end = entered + self.l["seconds"] * 10**9
        self.epoch_end = selected.end_epoch
        self.final = False
        self.cleanup_uncertain = False
        self.output_path = self.output_static = self.output_chain = None
        self.counts = dict(read_bytes=0, write_bytes=0, creations=0, operations=0,
                           scanned_entries=0, wire_bytes=0)
        self.check()

    def check(self):
        self.counts["operations"] += 1
        need(self.counts["operations"] <= self.l["operations"], "OPERATIONS")
        need(time.monotonic_ns() < self.end and time.time_ns() < self.epoch_end, "DEADLINE")

    def check_output(self):
        if self.output_path is not None:
            check_ancestors(self.output_chain)
            need(ident(self.output_path.lstat())[:5] == self.output_static, "OUTPUT_CHANGED")

    def claim(self, key, amount):
        self.check()
        uint(amount)
        reserve = 0 if self.final else (2 if key == "creations" else 32768 if key == "write_bytes" else 0)
        need(self.counts[key] + amount <= self.l[key] - reserve, key.upper())
        self.counts[key] += amount

    def read(self, fd, amount):
        self.check()
        need(amount > 0 and self.counts["read_bytes"] + amount <= self.l["read_bytes"], "READ_BYTES")
        raw = os.read(fd, amount)
        self.counts["read_bytes"] += len(raw)
        self.check()
        return raw

    def write(self, fd, raw):
        self.claim("write_bytes", len(raw))
        view = memoryview(raw)
        while view:
            self.check()
            n = os.write(fd, view)
            need(type(n) is int and 0 < n <= len(view), "WRITE")
            view = view[n:]
        self.check()

    def scan(self):
        self.claim("scanned_entries", 1)


def writable_parent(path, budget):
    budget.check_output()
    chain = ancestors(path, links=False)
    info = path.parent.lstat()
    private(info, "DIR", os.geteuid())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        need(ident(os.fstat(fd))[:5] == ident(info)[:5], "OUTPUT_CHANGED")
        check_ancestors(chain)
        return fd, chain
    except BaseException:
        close_owned(budget, (fd,))
        raise


def create_file(path, budget):
    budget.claim("creations", 1)
    parent, chain = writable_parent(path, budget)
    fd = None
    try:
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        private(os.fstat(fd), "FILE", os.geteuid())
        need(ident(path.lstat()) == ident(os.fstat(fd)), "OUTPUT_CHANGED")
        check_ancestors(chain)
        budget.check_output()
        closing, parent = parent, None
        close_owned(budget, (closing,))
        result, fd = fd, None
        return result
    finally:
        close_owned(budget, (fd, parent))


def mkdir(path, budget):
    budget.claim("creations", 1)
    parent, chain = writable_parent(path, budget)
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent)
        info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        private(info, "DIR", os.geteuid())
        need(ident(info) == ident(path.lstat()), "OUTPUT_CHANGED")
        os.fsync(parent)
        check_ancestors(chain)
        if budget.output_path is None:
            budget.output_path, budget.output_static = path, ident(info)[:5]
            budget.output_chain = chain
        budget.check_output()
    finally:
        close_owned(budget, (parent,))


def finish_file(fd, path, budget):
    os.fsync(fd)
    info = os.fstat(fd)
    private(info, "FILE", os.geteuid())
    need(ident(path.lstat()) == ident(info), "OUTPUT_CHANGED")
    parent, chain = writable_parent(path, budget)
    try:
        os.fsync(parent)
        check_ancestors(chain)
        budget.check_output()
    finally:
        close_owned(budget, (parent,))


class Lines:
    def __init__(self, path, budget, maximum):
        self.path, self.b, self.maximum = path, budget, maximum
        self.before = path.lstat()
        private(self.before, "FILE", os.geteuid())
        budget.check_output()
        chain = ancestors(path, links=False)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        try:
            need(ident(os.fstat(parent))[:5] == ident(path.parent.lstat())[:5], "SPILL_CHANGED")
            check_ancestors(chain)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            need(ident(os.fstat(fd)) == ident(self.before), "SPILL_CHANGED")
            closing, parent = parent, None
            close_owned(budget, (closing,))
            self.fd, fd = fd, None
        finally:
            close_owned(budget, (fd, parent))
        self.buf = bytearray()
        self.done = False

    def next(self):
        while True:
            at = self.buf.find(b"\n")
            if at >= 0:
                raw = bytes(self.buf[:at + 1])
                del self.buf[:at + 1]
                need(len(raw) <= self.maximum, "RECORD")
                return raw
            need(len(self.buf) <= self.maximum, "RECORD")
            raw = self.b.read(self.fd, self.b.l["chunk_bytes"])
            if not raw:
                need(not self.buf and ident(os.fstat(self.fd)) == ident(self.path.lstat())
                     == ident(self.before), "SPILL_CHANGED")
                self.b.check_output()
                self.done = True
                return None
            self.buf.extend(raw)

    def close(self):
        fd, self.fd = self.fd, None
        close_owned(self.b, (fd,))


class Sorter:
    """Bounded runs and fixed fan-in; every immutable generation is retained."""
    def __init__(self, root, phase, selected, budget):
        self.root, self.phase, self.s, self.b = root, phase, selected, budget
        self.rows, self.held, self.total, self.count, self.runs = [], 0, 0, 0, 0

    def name(self, generation, index):
        return self.root / f"{self.phase}.g{generation:02d}.r{index:08d}.jsonl"

    def add(self, row):
        raw = canonical(row)
        key = row["path"].encode()
        need(len(raw) <= self.s.limits["record_bytes"] - 128, "RECORD")
        self.total += len(raw)
        self.count += 1
        need(self.total <= self.s.limits["manifest_bytes"]
             and self.count <= self.s.limits["members"], "MANIFEST")
        self.held += len(raw) + len(key)
        need(self.held <= self.s.limits["sort_buffer_bytes"], "SORT_MEMORY")
        self.rows.append((key, raw))
        if len(self.rows) == self.s.limits["sort_records"]:
            self.flush()

    def flush(self):
        if not self.rows:
            return
        self.rows.sort(key=lambda item: item[0])
        path = self.name(0, self.runs)
        fd = create_file(path, self.b)
        try:
            previous = None
            for key, raw in self.rows:
                need(previous is None or previous < key, "DUPLICATE")
                self.b.write(fd, raw)
                previous = key
            finish_file(fd, path, self.b)
        finally:
            close_owned(self.b, (fd,))
        self.runs += 1
        self.rows.clear()
        self.held = 0

    def finish(self):
        self.flush()
        need(self.runs > 0, "EMPTY_MANIFEST")
        count, generation = self.runs, 0
        fan = self.s.limits["merge_fan_in"]
        while count > 1:
            outputs = 0
            for first in range(0, count, fan):
                readers, heap = [], []
                outpath = self.name(generation + 1, outputs)
                fd = create_file(outpath, self.b)
                try:
                    for index in range(first, min(count, first + fan)):
                        reader = Lines(self.name(generation, index), self.b,
                                       self.s.limits["record_bytes"])
                        readers.append(reader)
                        raw = reader.next()
                        if raw is not None:
                            heapq.heappush(heap, (parse(raw)["path"].encode(), len(readers)-1, raw))
                    previous = None
                    while heap:
                        key, index, raw = heapq.heappop(heap)
                        need(previous is None or previous < key, "DUPLICATE")
                        self.b.write(fd, raw)
                        previous = key
                        following = readers[index].next()
                        if following is not None:
                            heapq.heappush(heap, (parse(following)["path"].encode(), index, following))
                    finish_file(fd, outpath, self.b)
                finally:
                    close_owned(self.b, [fd] + [reader.fd for reader in readers])
                outputs += 1
            count, generation = outputs, generation + 1
        return self.name(generation, 0)


def row_for(path, kind, info, digest):
    return dict(path=path, kind=kind, size=info.st_size if kind == "FILE" else 0,
                sha256=digest, identity=list(ident(info)))


def validate_row(row, selected):
    need(type(row) is dict and set(row) == {"path", "kind", "size", "sha256", "identity"}, "ROW")
    selected.relative(row["path"])
    need(row["kind"] in ("DIR", "FILE"), "SPECIAL")
    uint(row["size"])
    need(type(row["identity"]) is list and len(row["identity"]) == 9, "IDENTITY")
    for number in row["identity"]:
        uint(number)
    mode = row["identity"][2]
    need(stat.S_IMODE(mode) == (0o700 if row["kind"] == "DIR" else 0o600)
         and (stat.S_ISDIR(mode) if row["kind"] == "DIR" else stat.S_ISREG(mode))
         and row["identity"][3:5] == [selected.uid, selected.gid], "PRIVATE")
    if row["kind"] == "FILE":
        need(row["identity"][5] == 1 and row["identity"][6] == row["size"]
             and type(row["sha256"]) is str and HEX.fullmatch(row["sha256"]), "ROW")
    else:
        need(row["size"] == 0 and row["sha256"] is None, "ROW")
    return row


def hash_fd(fd, parent_fd, name, expected, budget):
    digest, left = hashlib.sha256(), expected.st_size
    while left:
        raw = budget.read(fd, min(budget.l["chunk_bytes"], left))
        need(raw and len(raw) <= left, "SOURCE_SHORT")
        digest.update(raw)
        left -= len(raw)
    need(not budget.read(fd, 1)
         and ident(os.fstat(fd)) == ident(os.stat(name, dir_fd=parent_fd, follow_symlinks=False))
         == ident(expected), "SOURCE_CHANGED")
    return digest.hexdigest()


class Source:
    def __init__(self, selected, budget, roots=None, external=None, local=False):
        self.s, self.b = selected, budget
        self.roots = selected.roots if roots is None else roots
        self.external = selected.external if external is None else external
        self.uid, self.gid = (os.geteuid(), None) if local else (selected.uid, selected.gid)
        self.payload = 0

    def file(self, parent, name, logical, info):
        private(info, "FILE", self.uid, self.gid)
        self.payload += info.st_size
        need(self.payload <= self.s.limits["payload_bytes"], "PAYLOAD")
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            need(ident(os.fstat(fd)) == ident(info), "SOURCE_CHANGED")
            digest = hash_fd(fd, parent, name, info, self.b)
        finally:
            close_owned(self.b, (fd,))
        return row_for(logical, "FILE", info, digest)

    def directory(self, fd, parent, name, logical, expected, depth, device):
        self.b.check()
        need(depth <= self.s.limits["depth"], "DEPTH")
        private(expected, "DIR", self.uid, self.gid)
        need(expected.st_dev == device and ident(os.fstat(fd)) == ident(expected), "SOURCE_CHANGED")
        self.s.relative(logical)
        yield row_for(logical, "DIR", expected, None)
        with os.scandir(fd) as entries:
            for entry in entries:
                self.b.scan()
                self.s.relative(logical + "/" + entry.name)
                info = os.stat(entry.name, dir_fd=fd, follow_symlinks=False)
                need(info.st_dev == device, "DEVICE")
                target = logical + "/" + entry.name
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        yield from self.directory(child, fd, entry.name, target, info, depth+1, device)
                    finally:
                        close_owned(self.b, (child,))
                else:
                    need(stat.S_ISREG(info.st_mode), "SPECIAL")
                    yield self.file(fd, entry.name, target, info)
        need(ident(os.fstat(fd)) == ident(os.stat(name, dir_fd=parent, follow_symlinks=False))
             == ident(expected), "SOURCE_CHANGED")

    def rows(self):
        for label, path in sorted(self.roots.items()):
            chain = ancestors(path)
            info = path.lstat()
            private(info, "DIR", self.uid, self.gid)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            fd = None
            try:
                need(ident(os.fstat(parent))[:6] == chain[-1][1], "ANCESTOR_CHANGED")
                check_ancestors(chain)
                fd = os.open(path.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                yield from self.directory(fd, parent, path.name, label, info, 1, info.st_dev)
            finally:
                close_owned(self.b, (fd, parent))
            check_ancestors(chain)
        for label, path in sorted(self.external.items()):
            chain = ancestors(path)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                need(ident(os.fstat(parent))[:6] == chain[-1][1], "ANCESTOR_CHANGED")
                check_ancestors(chain)
                info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                yield self.file(parent, path.name, label, info)
            finally:
                close_owned(self.b, (parent,))
            check_ancestors(chain)

    def open_member(self, row):
        """Descriptor-relative lookup; return bounded chain held until payload EOF."""
        parts = row["path"].split("/")
        if parts[0] in self.external:
            need(len(parts) == 1, "MEMBER_PATH")
            path = self.external[parts[0]]
            base, tail = path.parent, [path.name]
        else:
            need(parts[0] in self.roots, "MEMBER_PATH")
            path = self.roots[parts[0]]
            base, tail = path.parent, [path.name] + parts[1:]
        chain = ancestors(path)
        parent = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        held = [(parent, base, None)]
        target_fd = None
        try:
            opened = ident(os.fstat(parent))
            held[0] = (parent, base, opened)
            need(opened[:6] == chain[-1][1], "ANCESTOR_CHANGED")
            check_ancestors(chain)
            for name in tail[:-1]:
                info = os.stat(name, dir_fd=parent, follow_symlinks=False)
                private(info, "DIR", self.uid, self.gid)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                held.append((child, (held[-1][1]/name), ident(info)))
                need(ident(os.fstat(child)) == ident(info), "SOURCE_CHANGED")
                parent = child
            info = os.stat(tail[-1], dir_fd=parent, follow_symlinks=False)
            private(info, row["kind"], self.uid, self.gid)
            need(list(ident(info)) == row["identity"], "SOURCE_CHANGED")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
            if row["kind"] == "DIR":
                flags |= os.O_DIRECTORY
            target_fd = os.open(tail[-1], flags, dir_fd=parent)
            need(ident(os.fstat(target_fd)) == ident(info), "SOURCE_CHANGED")
            return target_fd, parent, tail[-1], info, held, chain
        except BaseException:
            close_owned(self.b, [target_fd] + [fd for fd, _, _ in reversed(held)])
            raise


def close_member(fd, held, chain, budget):
    active_error = sys.exc_info()[0] is not None
    try:
        for opened, path, expected in ([] if active_error else held):
            need(ident(os.fstat(opened)) == ident(path.lstat()) == expected, "SOURCE_CHANGED")
        if not active_error:
            check_ancestors(chain)
    finally:
        close_owned(budget, [fd] + [opened for opened, _, _ in reversed(held)])


def summarize(path, selected, budget, validate=True):
    reader = Lines(path, budget, selected.limits["record_bytes"])
    digest = hashlib.sha256()
    count = payload = length = 0
    previous = None
    found = set()
    try:
        while (raw := reader.next()) is not None:
            row = parse(raw)
            if validate:
                validate_row(row, selected)
            key = row["path"].encode()
            need(previous is None or previous < key, "ORDER")
            previous = key
            digest.update(raw)
            length += len(raw)
            count += 1
            payload += row["size"] if row["kind"] == "FILE" else 0
            if row["path"] in selected.logs:
                need(row["kind"] == "FILE", "REQUIRED_LOG")
                found.add(row["path"])
        need(count <= selected.limits["members"] and payload <= selected.limits["payload_bytes"]
             and length <= selected.limits["manifest_bytes"], "MANIFEST")
        need(found == selected.logs, "REQUIRED_LOG")
        return dict(members=count, payload_bytes=payload, manifest_bytes=length,
                    manifest_sha256=digest.hexdigest())
    finally:
        reader.close()


class WireOut:
    def __init__(self, stream, selected, budget):
        self.stream, self.s, self.b = stream, selected, budget

    def raw(self, raw):
        self.b.claim("wire_bytes", len(raw))
        self.b.claim("write_bytes", len(raw))
        view = memoryview(raw)
        while view:
            self.b.check()
            n = self.stream.write(view)
            need(type(n) is int and 0 < n <= len(view), "WIRE_WRITE")
            view = view[n:]
        self.b.check()

    def frame(self, value):
        raw = canonical(value)
        need(len(raw) <= self.s.limits["record_bytes"], "FRAME")
        self.raw(struct.pack(">I", len(raw)))
        self.raw(raw)


class WireIn:
    def __init__(self, stream, archive_fd, selected, budget):
        self.stream, self.fd, self.s, self.b = stream, archive_fd, selected, budget
        self.sha = hashlib.sha256()

    def read(self, n):
        self.b.check()
        need(self.b.counts["read_bytes"] + n <= self.b.l["read_bytes"], "READ_BYTES")
        raw = self.stream.read(n)
        need(type(raw) is bytes and len(raw) <= n, "WIRE_READ")
        self.b.counts["read_bytes"] += len(raw)
        if raw:
            self.b.claim("wire_bytes", len(raw))
            self.b.write(self.fd, raw)
            self.sha.update(raw)
        return raw

    def exact(self, n):
        need(n <= self.s.limits["record_bytes"], "FRAME")
        result = bytearray()
        while len(result) < n:
            raw = self.read(n-len(result))
            need(raw, "TRUNCATED")
            result.extend(raw)
        return bytes(result)

    def frame(self):
        n = struct.unpack(">I", self.exact(4))[0]
        need(0 < n <= self.s.limits["record_bytes"], "FRAME")
        return parse(self.exact(n))


def frame_kind(value, kind, keys):
    need(type(value) is dict and set(value) == {"kind", *keys} and value["kind"] == kind, "PROTOCOL")


def make_manifest(root, phase, source, selected, budget, project=False):
    sorter = Sorter(root, phase, selected, budget)
    rows = source.rows()
    try:
        for row in rows:
            sorter.add(content(row) if project else row)
    finally:
        rows.close()
    return sorter.finish()


def content(row):
    return {key: row[key] for key in ("path", "kind", "size", "sha256")}


def export(selected, output, stream, budget):
    before = make_manifest(output, "before", Source(selected, budget), selected, budget)
    summary = summarize(before, selected, budget)
    wire = WireOut(stream, selected, budget)
    wire.raw(MAGIC)
    wire.frame(dict(kind="BEGIN", version=VERSION, scope=SCOPE, selection_sha256=selected.sha))
    wire.frame(dict(kind="BEFORE", summary=summary))
    reader = Lines(before, budget, selected.limits["record_bytes"])
    try:
        while (raw := reader.next()) is not None:
            wire.frame(dict(kind="MEMBER", entry=parse(raw)))
    finally:
        reader.close()
    wire.frame(dict(kind="DATA", summary=summary))
    source = Source(selected, budget)
    reader = Lines(before, budget, selected.limits["record_bytes"])
    try:
        while (raw := reader.next()) is not None:
            row = parse(raw)
            fd, parent, name, info, held, chain = source.open_member(row)
            try:
                wire.frame(dict(kind="ENTRY", entry=row))
                if row["kind"] == "FILE":
                    left, sha = row["size"], hashlib.sha256()
                    while left:
                        data = budget.read(fd, min(budget.l["chunk_bytes"], left))
                        need(data and len(data) <= left, "SOURCE_SHORT")
                        sha.update(data)
                        wire.raw(data)
                        left -= len(data)
                    need(not budget.read(fd, 1) and sha.hexdigest() == row["sha256"], "SOURCE_CHANGED")
                need(ident(os.fstat(fd)) == ident(os.stat(name, dir_fd=parent, follow_symlinks=False))
                     == ident(info), "SOURCE_CHANGED")
            finally:
                close_member(fd, held, chain, budget)
    finally:
        reader.close()
    after = make_manifest(output, "after", Source(selected, budget), selected, budget)
    need(summarize(after, selected, budget) == summary, "SOURCE_CHANGED")
    left = Lines(before, budget, selected.limits["record_bytes"])
    right = None
    try:
        right = Lines(after, budget, selected.limits["record_bytes"])
        wire.frame(dict(kind="AFTER", summary=summary))
        while (raw := left.next()) is not None:
            actual = right.next()
            need(actual == raw, "SOURCE_CHANGED")
            wire.frame(dict(kind="MEMBER", entry=parse(actual)))
        need(right.next() is None, "SOURCE_CHANGED")
    finally:
        close_owned(budget, (left.fd, right.fd if right is not None else None))
    wire.frame(dict(kind="END", summary=summary, scope=SCOPE))
    stream.flush()
    return dict(summary=summary, wire_bytes=budget.counts["wire_bytes"])


def receive_manifest(wire, path, summary, selected, budget, expected=None):
    need(type(summary) is dict and set(summary) == {
        "members", "payload_bytes", "manifest_bytes", "manifest_sha256"}, "SUMMARY")
    for key in ("members", "payload_bytes", "manifest_bytes"):
        uint(summary[key])
    need(summary["members"] <= selected.limits["members"]
         and summary["payload_bytes"] <= selected.limits["payload_bytes"]
         and summary["manifest_bytes"] <= selected.limits["manifest_bytes"]
         and type(summary["manifest_sha256"]) is str and HEX.fullmatch(summary["manifest_sha256"]), "SUMMARY")
    fd = create_file(path, budget)
    previous, digest, length, payload, found = None, hashlib.sha256(), 0, 0, set()
    try:
        for _ in range(summary["members"]):
            frame = wire.frame()
            frame_kind(frame, "MEMBER", {"entry"})
            row = validate_row(frame["entry"], selected)
            raw, key = canonical(row), row["path"].encode()
            need(len(raw) <= selected.limits["record_bytes"] - 128, "RECORD")
            need(previous is None or previous < key, "ORDER")
            previous = key
            if expected is not None:
                need(expected.next() == raw, "SOURCE_CHANGED")
            length += len(raw)
            payload += row["size"] if row["kind"] == "FILE" else 0
            need(length <= selected.limits["manifest_bytes"] and payload <= selected.limits["payload_bytes"],
                 "MANIFEST")
            if row["path"] in selected.logs:
                need(row["kind"] == "FILE", "REQUIRED_LOG")
                found.add(row["path"])
            digest.update(raw)
            budget.write(fd, raw)
        need(length == summary["manifest_bytes"] and payload == summary["payload_bytes"]
             and digest.hexdigest() == summary["manifest_sha256"] and found == selected.logs,
             "MANIFEST")
        if expected is not None:
            need(expected.next() is None, "SOURCE_CHANGED")
        finish_file(fd, path, budget)
    finally:
        close_owned(budget, (fd,))


def output_parent(root, relative, budget):
    parts = relative.split("/")
    budget.check_output()
    chain = ancestors(root/"__entry__", links=False)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    held = [(fd, root, None)]
    try:
        opened = ident(os.fstat(fd))[:5]
        held[0] = (fd, root, opened)
        need(opened == chain[-1][1], "OUTPUT_CHANGED")
        check_ancestors(chain)
        for name in parts[:-1]:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            private(info, "DIR", os.geteuid())
            nxt = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            held.append((nxt, held[-1][1]/name, ident(info)[:5]))
            need(ident(os.fstat(nxt)) == ident(info), "OUTPUT_CHANGED")
            fd = nxt
        budget.check()
        return fd, parts[-1], held
    except BaseException:
        close_owned(budget, [item for item, _, _ in reversed(held)])
        raise


def receive(selected, output, stream, budget):
    archive_path = output / "terminal.s12c"
    archive_fd = create_file(archive_path, budget)
    wire = WireIn(stream, archive_fd, selected, budget)
    try:
        need(wire.exact(len(MAGIC)) == MAGIC, "MAGIC")
        begin = wire.frame()
        frame_kind(begin, "BEGIN", {"version", "scope", "selection_sha256"})
        need(begin["version"] == VERSION and begin["scope"] == SCOPE
             and begin["selection_sha256"] == selected.sha, "BINDING")
        before_frame = wire.frame()
        frame_kind(before_frame, "BEFORE", {"summary"})
        summary = before_frame["summary"]
        before = output / "before.jsonl"
        receive_manifest(wire, before, summary, selected, budget)
        frame = wire.frame()
        frame_kind(frame, "DATA", {"summary"})
        need(frame["summary"] == summary, "PROTOCOL")
        originals = output / "originals"
        mkdir(originals, budget)
        expected = Lines(before, budget, selected.limits["record_bytes"])
        try:
            for _ in range(summary["members"]):
                raw = expected.next()
                need(raw is not None, "MANIFEST")
                row = parse(raw)
                frame = wire.frame()
                frame_kind(frame, "ENTRY", {"entry"})
                need(canonical(frame["entry"]) == raw, "DATA_MEMBERSHIP")
                parent, name, held = output_parent(originals, row["path"], budget)
                try:
                    budget.claim("creations", 1)
                    if row["kind"] == "DIR":
                        os.mkdir(name, 0o700, dir_fd=parent)
                    else:
                        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                     0o600, dir_fd=parent)
                        try:
                            left, digest = row["size"], hashlib.sha256()
                            while left:
                                data = wire.read(min(budget.l["chunk_bytes"], left))
                                need(data and len(data) <= left, "TRUNCATED")
                                budget.write(fd, data)
                                digest.update(data)
                                left -= len(data)
                            need(digest.hexdigest() == row["sha256"], "PAYLOAD_HASH")
                            os.fsync(fd)
                            info = os.fstat(fd)
                            private(info, "FILE", os.geteuid())
                            need(ident(os.stat(name, dir_fd=parent, follow_symlinks=False)) == ident(info),
                                 "OUTPUT_CHANGED")
                        finally:
                            close_owned(budget, (fd,))
                    os.fsync(parent)
                finally:
                    active_error = sys.exc_info()[0] is not None
                    try:
                        if not active_error:
                            budget.check_output()
                            for fd, path, identity in held:
                                need(ident(os.fstat(fd))[:5] == ident(path.lstat())[:5] == identity,
                                     "OUTPUT_CHANGED")
                    finally:
                        close_owned(budget, [fd for fd, _, _ in reversed(held)])
            need(expected.next() is None, "MANIFEST")
        finally:
            expected.close()
        after_frame = wire.frame()
        frame_kind(after_frame, "AFTER", {"summary"})
        need(after_frame["summary"] == summary, "SOURCE_CHANGED")
        expected = Lines(before, budget, selected.limits["record_bytes"])
        try:
            receive_manifest(wire, output/"after.jsonl", summary, selected, budget, expected)
        finally:
            expected.close()
        end = wire.frame()
        frame_kind(end, "END", {"summary", "scope"})
        need(end["summary"] == summary and end["scope"] == SCOPE, "PROTOCOL")
        need(wire.read(1) == b"", "TRAILING")
        expected_archive = wire.sha.hexdigest()
        finish_file(archive_fd, archive_path, budget)
        closing, archive_fd = archive_fd, None
        close_owned(budget, (closing,))
        root_labels = set(selected.roots) | set(selected.external)
        with os.scandir(originals) as entries:
            seen = set()
            for entry in entries:
                budget.scan()
                need(entry.name in root_labels and entry.name not in seen, "OUTPUT_MEMBERSHIP")
                seen.add(entry.name)
            need(seen == root_labels, "OUTPUT_MEMBERSHIP")
        local_roots = {name: originals/name for name in selected.roots}
        local_external = {name: originals/name for name in selected.external}
        # Create the spill sibling before snapshotting original-tree ancestors.
        # Run publication must not change an ancestor's immediate entries.
        verify_spills = output / "verify-spills"
        mkdir(verify_spills, budget)
        verified = make_manifest(verify_spills, "verify",
                                 Source(selected, budget, local_roots, local_external, local=True),
                                 selected, budget, project=True)
        actual = Lines(verified, budget, selected.limits["record_bytes"])
        expected = None
        try:
            expected = Lines(before, budget, selected.limits["record_bytes"])
            while (raw := expected.next()) is not None:
                need(actual.next() == canonical(content(parse(raw))), "OUTPUT_MEMBERSHIP")
            need(actual.next() is None, "OUTPUT_MEMBERSHIP")
        finally:
            close_owned(budget, (actual.fd, expected.fd if expected is not None else None))
        # Fresh archive hash/EOF, no whole-file materialization.
        parent = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        try:
            fd = os.open(archive_path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            info = os.fstat(fd)
            private(info, "FILE", os.geteuid())
            need(hash_fd(fd, parent, archive_path.name, info, budget) == expected_archive, "ARCHIVE_CHANGED")
        finally:
            close_owned(budget, (fd, parent))
        return dict(summary=summary, archive_sha256=expected_archive,
                    wire_bytes=budget.counts["wire_bytes"], independently_rehashed=True)
    finally:
        close_owned(budget, (archive_fd,))


def status_write(output, value, budget, success):
    budget.final = True
    raw = canonical(value)
    need(len(raw) <= 16384, "STATUS")
    path = output / ("COLLECTION_COMPLETE.record" if success else "COLLECTION_INCOMPLETE.record")
    fd = create_file(path, budget)
    try:
        budget.write(fd, raw)
        finish_file(fd, path, budget)
    finally:
        close_owned(budget, (fd,))


def plan(selected):
    limits = selected.limits
    runs, files, generations = (limits["members"] + limits["sort_records"]-1)//limits["sort_records"], 0, 0
    while True:
        files += runs
        generations += 1
        if runs <= 1:
            break
        runs = (runs + limits["merge_fan_in"]-1)//limits["merge_fan_in"]
    m, p, wire, n = limits["manifest_bytes"], limits["payload_bytes"], limits["wire_bytes"], limits["members"]
    return dict(version=VERSION, scope=SCOPE, per_manifest_run_files=files,
                retained_generations=generations,
                exporter_scratch_bytes=2*generations*m+32768,
                exporter_creation_bound=2*files+3,
                receiver_filedata_bound=wire+p+(2+generations)*m+32768,
                receiver_creation_bound=n+files+9,
                total_filedata_bound=wire+p+(2+3*generations)*m+65536,
                total_creation_bound=n+3*files+12,
                sender_payload_read_bytes=3*p,
                logical_sort_buffer_bytes=limits["sort_buffer_bytes"],
                merge_line_buffer_bytes=limits["merge_fan_in"]*(limits["chunk_bytes"]+2*limits["record_bytes"]+limits["path_bytes"]),
                control_selection_bytes_max=65536, control_selection_read_calls_max=65537,
                worker_processes_each=1, child_processes=0, worker_threads=0,
                spill_deletion_or_refund=False, placement_or_pool_approval=False)


def main(argv=None, *, stdin=None, stdout=None, stderr=None):
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "receive", "plan"))
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--offline-invented", action="store_true")
    parser.add_argument("--test-root", type=Path)
    args = parser.parse_args(argv)
    stdin = sys.stdin.buffer if stdin is None else stdin
    stdout = sys.stdout.buffer if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    output = budget = None
    owned_output = False
    try:
        os.umask(0o077)
        selection_path = absolute(str(args.selection))
        test_root = None
        if args.offline_invented:
            need(args.test_root is not None, "OFFLINE_ROOT")
            test_root = absolute(str(args.test_root))
            ancestors(test_root)
            private(test_root.lstat(), "DIR", os.geteuid())
            need(selection_path.is_relative_to(test_root), "OFFLINE_ROOT")
        else:
            from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
            require_goethe_nhr_slurm("stage12_terminal_original_collection")
        selected = Selection(selection_read(selection_path, args.selection_sha256, entered),
                             args.offline_invented, test_root)
        budget = Budget(selected, entered)
        if args.action == "plan":
            stdout.write(canonical(plan(selected)))
            stdout.flush()
            return 0
        need(args.output is not None, "OUTPUT")
        output = absolute(str(args.output))
        selected.disjoint_output(output, test_root)
        ancestors(output)
        private(output.parent.lstat(), "DIR", os.geteuid())
        mkdir(output, budget)
        owned_output = True
        result = (export if args.action == "export" else receive)(
            selected, output, stdout if args.action == "export" else stdin, budget)
        need(not budget.cleanup_uncertain, "CLOSE_UNCERTAIN")
        result.update(version=VERSION, status="COLLECTION_INTEGRITY_COMPLETE", scope=SCOPE,
                      selection_sha256=selected.sha, counters_before_terminal_record=dict(budget.counts),
                      final_creation_liability=2, final_write_liability=32768,
                      completion_requires_zero_sender_and_receiver_exits_and_parent_envelopes=True,
                      native_or_scientific_acceptance=False)
        budget.check()
        status_write(output, result, budget, True)
        budget.check()
        stderr.write(canonical(dict(status="COLLECTION_INTEGRITY_COMPLETE", scope=SCOPE)).decode())
        stderr.flush()
        return 0
    except BaseException as error:
        code = (error.args[0] if type(error) is Stop and len(error.args) == 1
                and type(error.args[0]) is str and error.args[0] in STOP_CODES else "UNCLASSIFIED")
        result = dict(version=VERSION, status="INCOMPLETE", scope=SCOPE, code=code,
                      native_or_scientific_acceptance=False,
                      counters=dict(budget.counts) if budget is not None else None,
                      cleanup_uncertain=(True if type(error) is Stop
                                         and getattr(error, "cleanup_uncertain", False) is True
                                         else budget.cleanup_uncertain if budget is not None else None))
        if owned_output and output is not None and budget is not None:
            try:
                status_write(output, result, budget, False)
            except BaseException:
                result["incomplete_record_uncertain"] = True
        stderr.write(canonical(result).decode())
        stderr.flush()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

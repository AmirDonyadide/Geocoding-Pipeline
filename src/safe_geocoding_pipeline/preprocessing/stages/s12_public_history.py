"""AP-only compact history bindings; no database, spill or durable cache.

Two count/build scans precede an in-place heapsort of packed entry indices.
Only bounded pathname/hash/identity backing survives, never Path/dict per file.
Every stage finishes with fresh membership, private paths and original hashes.
"""

from __future__ import annotations

from typing import Any, Callable

from array import array
import hashlib
import os
from pathlib import Path
import stat
import struct
import sys
import threading

from . import s12_storage as io
from . import s12_retrieval_contract as c
from .s12_public_reader import PublicReader

_reader_type: Callable[..., Any] = PublicReader

MAX_ENTRIES = 32768
MAX_PATH_BYTES = 4 * 2**20
MAX_NAME_BYTES = 1024
MAX_DEPTH = 8
CACHE_BYTES = 2**20
CACHE_ITEM_BYTES = 4096
ENTRY = struct.Struct("<IIQQ32sB7xII")
MAX_BACKING = 8 * 2**20
_backing_lock = threading.Lock()
_backing = 0


def walk(
    root: Any, *, check: Any = io._checkpoint, depth: Any = 0, strict: Any = True
) -> Any:
    """Unsorted discovery, at most MAX_DEPTH+1 open directory streams."""
    c.require(depth <= MAX_DEPTH, "S12_PUBLIC_HISTORY_LIMIT")
    check()
    info = root.stat(follow_symlinks=False)
    c.require(stat.S_ISDIR(info.st_mode), "S12_PUBLIC_SOURCE_CHANGED")
    io.private_directory(root)
    yield root, info, True
    with os.scandir(root) as entries:
        for entry in entries:
            check()
            info = entry.stat(follow_symlinks=False)
            path = Path(entry.path)
            if stat.S_ISDIR(info.st_mode):
                yield from walk(path, check=check, depth=depth + 1, strict=strict)
            else:
                c.require(
                    not strict
                    or (
                        stat.S_ISREG(info.st_mode)
                        and info.st_nlink == 1
                        and info.st_uid == os.geteuid()
                        and stat.S_IMODE(info.st_mode) == 0o600
                    ),
                    "S12_PRIVATE_FILE_INVALID",
                )
                yield path, info, False


def key(root: Any, path: Any) -> Any:
    raw = path.relative_to(root).as_posix().encode("utf8")
    c.require(len(raw) <= MAX_NAME_BYTES, "S12_PUBLIC_HISTORY_LIMIT")
    return raw


class Index:
    """Packed original identities and hashes with one fixed optional byte cache."""

    def __init__(
        self,
        root: Any,
        *,
        outputs: Any = (),
        check: Any = io._checkpoint,
        cache_bytes: Any = 0,
        strict: Any = True,
    ) -> None:
        global _backing

        self._reserved = 0
        self.entries: Any = None
        self.order: Any = None
        self.names: Any = None
        self.cache: Any = None
        self.root, self.check = Path(root).absolute(), check
        c.require(
            self.root == Path(os.path.abspath(self.root)), "S12_PRIVATE_FILE_INVALID"
        )
        self.count = self.names_used = self.cached_bytes = 0
        self.strict = strict
        count = names = 0
        for path, _, _ in walk(self.root, check=check, strict=strict):
            count += 1
            names += len(key(self.root, path))
            c.require(
                count <= MAX_ENTRIES and names <= MAX_PATH_BYTES,
                "S12_PUBLIC_HISTORY_LIMIT",
            )
        self.capacity = count + len(outputs)
        self.name_capacity = names + sum(len(x.encode("utf8")) for x in outputs)
        c.require(
            self.capacity <= MAX_ENTRIES and self.name_capacity <= MAX_PATH_BYTES,
            "S12_PUBLIC_HISTORY_LIMIT",
        )
        c.require(type(cache_bytes) is int and 0 <= cache_bytes <= CACHE_BYTES)
        c.require(array("I").itemsize == 4, "S12_PUBLIC_HISTORY_LIMIT")
        reservation = (
            self.capacity * (ENTRY.size + 4)
            + self.name_capacity
            + cache_bytes
            + (self.capacity + 7) // 8
        )
        with _backing_lock:
            c.require(reservation <= MAX_BACKING - _backing, "S12_PUBLIC_HISTORY_LIMIT")
            _backing += reservation
            self._reserved = reservation
        try:
            self.entries = bytearray(self.capacity * ENTRY.size)
            self.order = array("I", [0]) * self.capacity
            self.names = bytearray(self.name_capacity)
            self.cache = bytearray(cache_bytes)
            for path, info, directory in walk(self.root, check=check, strict=strict):
                self.add(key(self.root, path), info, directory)
            self.sort()
            for n in range(1, self.count):
                c.require(
                    self.name(self.order[n - 1]) != self.name(self.order[n]),
                    "S12_PUBLIC_SOURCE_CHANGED",
                )
        except BaseException:
            self.close()
            raise

    def add(self, name: Any, info: Any, directory: Any = False) -> Any:
        self.check()
        c.require(
            self.count < self.capacity
            and self.names_used + len(name) <= self.name_capacity,
            "S12_PUBLIC_HISTORY_LIMIT",
        )
        i = self.count
        offset = self.names_used
        self.names[offset : offset + len(name)] = name
        ENTRY.pack_into(
            self.entries,
            i * ENTRY.size,
            offset,
            len(name),
            info.st_dev,
            info.st_ino,
            b"\0" * 32,
            directory,
            0,
            0,
        )
        self.order[i] = i
        self.count += 1
        self.names_used += len(name)
        return i

    def row(self, i: Any) -> Any:
        return ENTRY.unpack_from(self.entries, i * ENTRY.size)

    def name(self, i: Any) -> Any:
        start, length = struct.unpack_from("<II", self.entries, i * ENTRY.size)
        return bytes(memoryview(self.names)[start : start + length])

    def _less(self, a: Any, b: Any) -> Any:
        # Path ordering compares components, not '/' against '.' in another name.
        return tuple(self.name(a).split(b"/")) < tuple(self.name(b).split(b"/"))

    def sort(self) -> Any:
        def sift(start: Any, end: Any) -> Any:
            while 2 * start + 1 <= end:
                child = 2 * start + 1
                if child + 1 <= end and self._less(
                    self.order[child], self.order[child + 1]
                ):
                    child += 1
                if not self._less(self.order[start], self.order[child]):
                    return
                self.order[start], self.order[child] = (
                    self.order[child],
                    self.order[start],
                )
                start = child

        for n in range(self.count // 2 - 1, -1, -1):
            self.check()
            sift(n, self.count - 1)
        for n in range(self.count - 1, 0, -1):
            self.check()
            self.order[0], self.order[n] = self.order[n], self.order[0]
            sift(0, n - 1)

    def find(self, name: Any) -> Any:
        target = tuple(name.split(b"/"))
        lo, hi = 0, self.count
        while lo < hi:
            mid = (lo + hi) // 2
            current = tuple(self.name(self.order[mid]).split(b"/"))
            if current < target:
                lo = mid + 1
            else:
                hi = mid
        return (
            self.order[lo]
            if lo < self.count and self.name(self.order[lo]) == name
            else None
        )

    def bind(self, i: Any, raw: Any) -> Any:
        self.bind_digest(i, hashlib.sha256(raw).digest(), raw=raw)

    def bind_digest(self, i: Any, observed: Any, *, raw: Any = None) -> Any:
        start, size, dev, ino, digest, directory, cache_at, cache_len = self.row(i)
        c.require(not directory & 2 or digest == observed, "S12_PUBLIC_SOURCE_CHANGED")
        if (
            not cache_len
            and raw
            and len(raw) <= min(CACHE_ITEM_BYTES, len(self.cache) - self.cached_bytes)
        ):
            cache_at, cache_len = self.cached_bytes, len(raw)
            self.cache[cache_at : cache_at + cache_len] = raw
            self.cached_bytes += cache_len
        ENTRY.pack_into(
            self.entries,
            i * ENTRY.size,
            start,
            size,
            dev,
            ino,
            observed,
            directory | 2,
            cache_at,
            cache_len,
        )

    def verify_membership(self, *, allowed_new: Any = ()) -> Any:
        seen, count = bytearray((self.capacity + 7) // 8), 0
        for path, info, directory in walk(
            self.root, check=self.check, strict=self.strict
        ):
            i = self.find(key(self.root, path))
            if i is None and path.relative_to(self.root).as_posix() in allowed_new:
                continue
            c.require(i is not None, "S12_PUBLIC_SOURCE_CHANGED")
            row = self.row(i)
            c.require(
                (info.st_dev, info.st_ino, directory)
                == (row[2], row[3], bool(row[5] & 1))
                and not seen[i // 8] & (1 << (i % 8)),
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            seen[i // 8] |= 1 << (i % 8)
            count += 1
        c.require(count == self.count, "S12_PUBLIC_SOURCE_CHANGED")

    def files(self) -> Any:
        for rank in range(self.count):
            self.check()
            i = self.order[rank]
            if not self.row(i)[5] & 1:
                yield i, self.root / self.name(i).decode("utf8")

    def close(self) -> Any:
        global _backing

        self.entries = self.names = self.cache = None
        self.order = None
        with _backing_lock:
            _backing -= self._reserved
            self._reserved = 0


class Fresh:
    """Explicit AP stage; independent instances never accept another's result."""

    def __init__(
        self,
        root: Any,
        *,
        check: Any = io._checkpoint,
        boundary: Any = None,
        outputs: Any = (),
        events: Any = (),
        reader_root: Any = None,
    ) -> None:
        self.root = Path(root).absolute()
        self.reader_root = (
            self.root if reader_root is None else Path(reader_root).absolute()
        )
        self.check, self.boundary = check, boundary or check
        self.outputs = frozenset(outputs) | frozenset(events)
        c.require(len(self.outputs) <= 32)
        self.owner, self.state = threading.get_ident(), "NEW"
        self.index: Any = None
        self.reader: Any = None
        self.hook: Any = None
        self.original_scope: Any = None
        self.parent_view: Any = None
        self.parent_original: Any = None

    def _owner(self) -> Any:
        c.require(threading.get_ident() == self.owner)
        self.check()

    def __enter__(self) -> Any:
        self._owner()
        c.require(self.state == "NEW")
        current = getattr(io._checkpoints, "read_view", None)
        c.require(
            current is None or isinstance(current, Fresh), "S12_PUBLIC_SOURCE_CHANGED"
        )
        # Nested original-history validation suspends, never accepts its parent.
        self.parent_view = current
        self.parent_original = getattr(io._checkpoints, "original_view", None)
        c.require(
            current is not None or self.parent_original is None,
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        if current is not None:
            io._checkpoints.read_view = io._checkpoints.original_view = None
        try:
            self.boundary()
            self.index = Index(
                self.root,
                outputs=self.outputs,
                check=self.check,
                cache_bytes=CACHE_BYTES,
            )
            self.reader = _reader_type(self.reader_root, check=self.check)
            scope = io.public_originals(self.reader)
            scope.__enter__()
            self.original_scope = scope
            for i, path in self.index.files():
                size = path.stat(follow_symlinks=False).st_size
                if size <= min(
                    CACHE_ITEM_BYTES, len(self.index.cache) - self.index.cached_bytes
                ):
                    self.index.bind(
                        i,
                        io.original_read(
                            path, limit=4096 if path.parent.name == "events" else 65536
                        ),
                    )
                else:
                    self.index.bind_digest(
                        i, bytes.fromhex(hash_file(path, reader=self.reader))
                    )
            self.index.verify_membership()
            self.boundary()
            hook = io.read_view(self)
            hook.__enter__()
            self.hook = hook
            self.state = "ACTIVE"
            return self
        except BaseException:
            self.abort(suppress_cleanup=True)
            raise

    def read(self, path: Any, *, limit: Any, original: Any) -> Any:
        self._owner()
        c.require(self.state == "ACTIVE")
        path = Path(path).absolute()
        if not path.is_relative_to(self.root):
            return original(path, limit=limit)
        i = self.index.find(key(self.root, path))
        c.require(i is not None, "S12_PUBLIC_SOURCE_CHANGED")
        row = self.index.row(i)
        if row[7]:
            c.require(row[7] <= limit, "S12_PRIVATE_FILE_INVALID")
            return bytes(memoryview(self.index.cache)[row[6] : row[6] + row[7]])
        raw = original(path, limit=limit)
        self.index.bind(i, raw)
        return raw

    def output(self, path: Any, digest: Any) -> Any:
        self._owner()
        path = Path(path).absolute()
        if not path.is_relative_to(self.root):
            return
        name = key(self.root, path)
        c.require(name.decode("utf8") in self.outputs and self.index.find(name) is None)
        observed = hash_file(path, reader=self.reader)
        c.require(observed == digest)
        i = self.index.add(name, path.stat(follow_symlinks=False))
        self.index.bind_digest(i, bytes.fromhex(observed))
        self.index.sort()

    def finish(self) -> Any:
        self._owner()
        c.require(self.state == "ACTIVE")
        self.hook.__exit__(None, None, None)
        self.hook = None
        self.state = "VERIFYING"
        try:
            self.boundary()
            self.index.verify_membership()
            for i, path in self.index.files():
                c.require(
                    bytes.fromhex(hash_file(path, reader=self.reader))
                    == self.index.row(i)[4],
                    "S12_PUBLIC_SOURCE_CHANGED",
                )
            self.index.verify_membership()
            self.boundary()
            self.state = "VERIFIED"
        except BaseException:
            self.state = "INVALID"
            raise
        finally:
            self._close(suppress=sys.exc_info()[0] is not None)

    def _close(self, *, suppress: Any = False) -> Any:
        try:
            if self.hook is not None:
                self.hook.__exit__(None, None, None)
                self.hook = None
            if self.original_scope is not None:
                self.original_scope.__exit__(None, None, None)
                self.original_scope = None
            if self.reader is not None:
                self.reader.close()
                self.reader = None
        except BaseException:
            self.state = "INVALID"
            if not suppress:
                raise
        finally:
            if self.index is not None:
                self.index.close()
                self.index = None
            if self.parent_view is not None:
                io._checkpoints.read_view = self.parent_view
                io._checkpoints.original_view = self.parent_original
                self.parent_view = self.parent_original = None

    def abort(self, *, suppress_cleanup: Any = False) -> Any:
        self.state = "INVALID"
        self._close(suppress=suppress_cleanup)

    def __exit__(self, kind: Any, error: Any, tb: Any) -> Any:
        if kind is not None:
            self.abort(suppress_cleanup=True)
        elif self.state == "ACTIVE":
            self.finish()
        else:
            c.require(self.state == "VERIFIED")


def inventory(root: Any, *, check: Any = io._checkpoint) -> Any:
    """Fresh deterministic original reads, constant per-file transient state."""
    active: Any = getattr(io._checkpoints, "read_view", None)
    shared = isinstance(active, Fresh) and root.absolute().is_relative_to(active.root)
    index = active.index if shared else Index(root, check=check)
    try:
        for _, path in index.files():
            if not path.is_relative_to(root):
                continue
            yield {"path": path.relative_to(root).as_posix(), "sha256": hash_file(path)}
        index.verify_membership(allowed_new=active.outputs if shared else ())
    finally:
        if not shared:
            index.close()


class Known:
    """Reusable incomplete-input projection, validated afresh on each traversal."""

    OUTPUTS = frozenset(
        {
            "available_event_inventory.json",
            "available_attempt_inventory.json",
            "incomplete_campaign_report.json",
        }
    )

    def __init__(self, root: Any, verify_known: Any = None) -> None:
        self.index = Index(root, strict=False)
        self.confirmed = self.verified = 0
        try:
            for i, path in self.index.files():
                try:
                    info = path.stat(follow_symlinks=False)
                    c.require(
                        stat.S_ISREG(info.st_mode)
                        and stat.S_IMODE(info.st_mode) == 0o600
                        and info.st_nlink == 1
                    )
                    self.index.bind_digest(i, bytes.fromhex(hash_file(path)))
                    if path.name == "begin.json" or (
                        path.name.endswith("_begin.json")
                        and not path.name.endswith("_validation_begin.json")
                    ):
                        raw = io.original_read(path, limit=65536)
                        obj = io.metadata(raw)
                        c.require(
                            type(obj.get("attempt")) is int and 1 <= obj["attempt"] <= 5
                        )
                        self.confirmed += 1
                        if verify_known is not None:
                            self.verified += bool(verify_known(path.parent, obj))
                except (c.Stage12Error, OSError):
                    continue
            self.index.verify_membership()
        except BaseException:
            self.close()
            raise

    def rows(self, prefix: Any = "") -> Any:
        self.index.verify_membership(allowed_new=self.OUTPUTS)
        for i, path in self.index.files():
            name = path.relative_to(self.index.root).as_posix()
            if not name.startswith(prefix) or not self.index.row(i)[5] & 2:
                continue
            c.require(
                bytes.fromhex(hash_file(path)) == self.index.row(i)[4],
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            yield {"path": name, "sha256": self.index.row(i)[4].hex()}
        self.index.verify_membership(allowed_new=self.OUTPUTS)

    def __iter__(self) -> Any:
        return self.rows()

    def close(self) -> Any:
        self.index.close()


def event_paths(root: Any) -> Any:
    """Canonical numeric event names need no sorting/Path list or packed index."""
    count, low, high = 0, None, 0
    io.private_directory(root)
    with os.scandir(root) as entries:
        for entry in entries:
            io._checkpoint()
            name = entry.name
            c.require(
                len(name) == 25
                and name.endswith(".json")
                and name[:20].isascii()
                and name[:20].isdigit()
            )
            n = int(name[:20])
            c.require(n > 0 and name == f"{n:020d}.json")
            count += 1
            c.require(count <= MAX_ENTRIES, "S12_PUBLIC_HISTORY_LIMIT")
            low, high = n if low is None else min(n, low), max(n, high)
    if count:
        assert low is not None
        c.require(high - low + 1 == count, "S12_PUBLIC_SOURCE_CHANGED")
    if low is not None:
        for n in range(low, high + 1):
            io._checkpoint()
            yield root / f"{n:020d}.json"


def hash_file(path: Any, *, reader: Any = None) -> Any:
    """Fresh private original hash with at most two4096-byte input buffers."""
    path = Path(path).absolute()
    active: Any = getattr(io._checkpoints, "read_view", None)
    original_reader: Callable[[], Any] = io.public_original_reader
    reader = reader or (
        active.reader if isinstance(active, Fresh) else original_reader()
    )
    own = reader is None or not reader.contains(str(path))
    if own:
        reader = _reader_type(path.parent)
    fd = None
    try:
        parent = str(path.parent)
        reader._directory(parent)
        reader._bound(parent)
        before = path.stat(follow_symlinks=False)
        limit = 4096 if path.parent.name == "events" else 64 * 2**20
        c.require(
            stat.S_ISREG(before.st_mode)
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and before.st_size <= limit,
            "S12_PRIVATE_FILE_INVALID",
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)

        def identity(info: Any) -> Any:
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_gid,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        c.require(
            identity(before) == identity(os.fstat(fd)), "S12_PUBLIC_SOURCE_CHANGED"
        )
        digest, size = hashlib.sha256(), 0
        while True:
            reader.check()
            raw = os.read(fd, min(4096, limit + 1 - size))
            if not raw:
                break
            size += len(raw)
            c.require(size <= limit, "S12_PRIVATE_FILE_INVALID")
            digest.update(raw)
        c.require(
            size == before.st_size
            and identity(before)
            == identity(os.fstat(fd))
            == identity(path.stat(follow_symlinks=False)),
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        reader._bound(parent)
        return digest.hexdigest()
    finally:
        if fd is not None:
            os.close(fd)
        if own:
            reader.close()

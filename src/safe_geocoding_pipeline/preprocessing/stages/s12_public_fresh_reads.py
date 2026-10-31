"""Bounded, disposable public validation-stage read set; never a durable cache."""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from pathlib import Path

from . import s12_public_operations as o
from . import s12_storage as io

MAX_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 32768
MAX_PATH_BYTES = 8 * 1024 * 1024


class FreshReads:
    """Every stage starts with originals and ends with originals.

    A single coordinator may reuse immutable bytes only during this stage.
    Original private-file reads, complete file/directory sets and byte hashes
    are checked again before any stage result is accepted. Nothing survives
    finish/abort. Byte overflow skips caching, never source verification.
    """

    def __init__(
        self,
        root,
        *,
        check=io._checkpoint,
        boundary=None,
        outputs=frozenset(),
        events=(),
    ):
        self.root = Path(root).absolute()
        self.check = check
        self.boundary = boundary or check
        self.outputs = frozenset(outputs) | frozenset(events)
        self.owner = threading.get_ident()
        self.cache = {}
        self.hashes = {}
        self.directories = {}
        self.inputs = set()
        self.cached_bytes = 0
        self.state = "NEW"
        self.hook = None

    def _owner(self):
        o.require(threading.get_ident() == self.owner)
        o.require(threading.current_thread().name != "stage12-public-writer")
        self.check()

    def _key(self, path):
        path = Path(path).absolute()
        o.require(".." not in path.parts and path.is_relative_to(self.root))
        return path.relative_to(self.root).as_posix()

    def _tree(self):
        self._owner()
        dirs, files = {}, set()
        count = names = 0

        def visit(path):
            nonlocal count, names
            self.check()
            info = path.stat(follow_symlinks=False)
            o.require(stat.S_ISDIR(info.st_mode))
            io.private_directory(path)
            key = path.relative_to(self.root).as_posix()
            dirs[key] = (info.st_dev, info.st_ino)
            count += 1
            names += len(key.encode("utf8"))
            o.require(count <= MAX_ENTRIES and names <= MAX_PATH_BYTES)
            with os.scandir(path) as entries:
                # Count bounded names before sorting; no unbounded rglob list.
                pending = []
                for entry in entries:
                    self.check()
                    count += 1
                    names += len(entry.path.encode("utf8"))
                    o.require(count <= MAX_ENTRIES and names <= MAX_PATH_BYTES)
                    pending.append(entry)
            for entry in sorted(pending, key=lambda x: x.name):
                kind = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(kind.st_mode):
                    visit(Path(entry.path))
                else:
                    o.require(stat.S_ISREG(kind.st_mode) and kind.st_nlink == 1)
                    files.add(self._key(entry.path))

        visit(self.root)
        return dirs, files

    def _remember(self, key, raw):
        digest = hashlib.sha256(raw).digest()
        prior = self.hashes.get(key)
        o.require(prior is None or prior == digest, "S12_PUBLIC_SOURCE_CHANGED")
        self.hashes[key] = digest
        if key not in self.cache and len(raw) <= MAX_BYTES - self.cached_bytes:
            self.cache[key] = raw
            self.cached_bytes += len(raw)

    def __enter__(self):
        self._owner()
        o.require(self.state == "NEW")
        o.require(not io.has_read_view())
        self.state = "LOADING"
        try:
            self.boundary()
            self.directories, self.inputs = self._tree()
            for key in sorted(self.inputs):
                self._remember(key, io.read(self.root / key))
            self._same_set()
            self.boundary()
            self.hook = io.read_view(self)
            self.hook.__enter__()
            self.state = "ACTIVE"
            return self
        except BaseException:
            self.abort()
            raise

    def _same_set(self):
        dirs, files = self._tree()
        o.require(dirs == self.directories, "S12_PUBLIC_SOURCE_CHANGED")
        o.require(files == set(self.hashes), "S12_PUBLIC_SOURCE_CHANGED")

    def read(self, path, *, limit, original):
        self._owner()
        o.require(self.state == "ACTIVE")
        if not Path(path).absolute().is_relative_to(self.root):
            # Authority/configuration inputs outside this campaign retain their
            # existing fresh reader and bindings; they never enter this view.
            return original(path, limit=limit)
        key = self._key(path)
        # Generated outputs must be registered by the actual writer-returned
        # identity; a read never implicitly blesses a new filename.
        o.require(key in self.hashes, "S12_PUBLIC_SOURCE_CHANGED")
        if key in self.cache:
            raw = self.cache[key]
            o.require(len(raw) <= limit, "S12_PRIVATE_FILE_INVALID")
            return raw
        raw = original(path, limit=limit)
        self._remember(key, raw)
        return raw

    def output(self, path, digest):
        self._owner()
        o.require(self.state == "ACTIVE")
        if not Path(path).absolute().is_relative_to(self.root):
            # A read-only attempts-stage view does not own the event journal or
            # derived comparison output. These retain their original writer
            # validation, and are checked by the later whole-campaign stage.
            return
        key = self._key(path)
        o.require(key in self.outputs and key not in self.hashes)
        raw = io.original_read(path)
        o.require(hashlib.sha256(raw).hexdigest() == digest)
        self._remember(key, raw)

    def finish(self):
        # Unhook before the first deadline/health check can fail.
        o.require(threading.get_ident() == self.owner)
        o.require(self.state == "ACTIVE")
        self.state = "VERIFYING"
        self.hook.__exit__(None, None, None)
        self.hook = None
        try:
            self._owner()
            self.boundary()
            self._same_set()
            for key, expected in sorted(self.hashes.items()):
                self.check()
                o.require(
                    hashlib.sha256(io.read(self.root / key)).digest() == expected,
                    "S12_PUBLIC_SOURCE_CHANGED",
                )
            self._same_set()
            self.boundary()
            self.check()
            self.state = "VERIFIED"
        except BaseException:
            self.state = "INVALID"
            raise
        finally:
            self.cache.clear()
            self.hashes.clear()
            self.directories.clear()
            self.inputs.clear()
            self.cached_bytes = 0

    def abort(self):
        if self.hook is not None:
            self.hook.__exit__(None, None, None)
            self.hook = None
        self.state = "INVALID"
        self.cache.clear()
        self.hashes.clear()
        self.directories.clear()
        self.inputs.clear()
        self.cached_bytes = 0

    def __exit__(self, kind, error, traceback):
        if kind is not None:
            self.abort()
        elif self.state == "ACTIVE":
            self.finish()
        else:
            o.require(self.state == "VERIFIED")


WORK_ROWS_BOUND = 4096


def _work_read(path):
    """Original file reader, within a separately checked private work anchor."""
    from . import s12_retrieval_contract as c

    try:
        raw = io.accepted.read_private(path)
    except Exception:
        raise c.Stage12Error("S12_PRIVATE_FILE_INVALID") from None
    io._checkpoint()
    return raw


def work_manifest_digest(root, count):
    """Fresh, bounded two-pass work validation; no state survives an attempt.

    Fuse repeated ancestor checks only. Both passes use the existing exact
    private-file reader, and pin/check the work-directory identity for every
    file. Canonical bytes generate the original manifest digest directly.
    Before returning, re-read every original and exact directory membership.
    The caller retains its streaming fallback above WORK_ROWS_BOUND.
    """
    root = Path(root)
    o.require(type(count) is int and 0 <= count <= WORK_ROWS_BOUND)
    io._checkpoint()
    io.private_directory(root)
    anchor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        identity = os.fstat(anchor)
        expected = {f"{key:020d}.json" for key in range(1, count + 1)}

        def bound():
            io._checkpoint()
            info = root.stat(follow_symlinks=False)
            o.require(
                stat.S_ISDIR(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.geteuid()
                and (info.st_dev, info.st_ino) == (identity.st_dev, identity.st_ino),
                "S12_PUBLIC_SOURCE_CHANGED",
            )

        def membership():
            bound()
            names = set()
            with os.scandir(root) as entries:
                for entry in entries:
                    io._checkpoint()
                    # Bound before retaining any attacker-supplied name.
                    o.require(entry.name in expected and entry.name not in names)
                    names.add(entry.name)
                    o.require(len(names) <= WORK_ROWS_BOUND)
            o.require(names == expected, "S12_PUBLIC_SOURCE_CHANGED")
            bound()

        membership()
        hashes = []
        digest = hashlib.sha256(b"[")
        for key in range(1, count + 1):
            bound()
            raw = _work_read(root / f"{key:020d}.json")
            # Parse and check canonical form once; the exact validated bytes
            # are also the manifest contribution, avoiding recanonicalization.
            io.metadata(raw)
            bound()
            hashes.append(hashlib.sha256(raw).digest())
            if key > 1:
                digest.update(b",")
            digest.update(raw[:-1])
        digest.update(b"]\n")
        membership()
        for key, expected_hash in enumerate(hashes, 1):
            bound()
            raw = _work_read(root / f"{key:020d}.json")
            o.require(
                hashlib.sha256(raw).digest() == expected_hash,
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            bound()
        membership()
        io.private_directory(root)
        bound()
        return digest.hexdigest()
    finally:
        os.close(anchor)

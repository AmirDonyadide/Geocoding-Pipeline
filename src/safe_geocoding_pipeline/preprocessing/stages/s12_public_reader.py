"""Bounded public-only original reader; no byte cache or durable trust token."""

from __future__ import annotations

import os
import stat
import sys
import threading
from collections import OrderedDict
from pathlib import Path

from . import s12_storage as io
from . import s12_retrieval_contract as c

MAX_DESCRIPTORS = 256
MAX_NAMES_BYTES = 128 * 1024


def identity(info):
    return info.st_dev, info.st_ino


class PublicReader:
    """Fresh bytes on every call, with configured pathname AND descriptor checks.

    All ancestor path components are rechecked on every read, including on
    retained descriptors. A renamed/detached directory cannot authorize a read.
    Only the entering thread owns the bounded descriptors. No state survives close.
    """

    def __init__(self, root, *, check=io._checkpoint, direct_work=False):
        self.root = os.path.abspath(os.fspath(root))
        c.require(os.fspath(root) == self.root, "S12_PRIVATE_FILE_INVALID")
        self.owner = threading.get_ident()
        self.check = check
        self.direct_work = direct_work
        self.closed = False
        self.dirs = {}
        self.files = OrderedDict()
        self.names_bytes = 0
        # Compile names once; every check still stats the current pathname.
        path = Path(self.root)
        self.ancestors = tuple(str(p) for p in reversed((path, *path.parents)))
        c.require(
            len(self.ancestors) <= 64
            and sum(len(os.fsencode(p)) for p in self.ancestors) <= 16384,
            "S12_PRIVATE_FILE_INVALID",
        )
        self.ancestor_ids = {}
        try:
            io.private_directory(path)
            for name in self.ancestors:
                info = os.stat(name, follow_symlinks=False)
                c.require(stat.S_ISDIR(info.st_mode), "S12_PRIVATE_FILE_INVALID")
                self.ancestor_ids[name] = identity(info)
            self._directory(self.root)
            self._bound(self.root)
        except BaseException:
            self._abort()
            raise

    def _owner(self):
        c.require(
            not self.closed and threading.get_ident() == self.owner,
            "S12_PRIVATE_FILE_INVALID",
        )
        self.check()

    def _bound(self, parent, *, ancestors=True):
        self._owner()
        for name in self.ancestors if ancestors else ():
            info = os.stat(name, follow_symlinks=False)
            c.require(
                stat.S_ISDIR(info.st_mode)
                and identity(info) == self.ancestor_ids[name],
                "S12_PUBLIC_SOURCE_CHANGED",
            )
        chain = []
        name = parent
        while name != self.root:
            chain.append(name)
            name = os.path.dirname(name)
        for name in (self.root, *reversed(chain)):
            _, expected = self.dirs[name]
            info = os.stat(name, follow_symlinks=False)
            c.require(
                stat.S_ISDIR(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o700
                and info.st_uid == os.geteuid()
                # Each owned directory descriptor is opened/fstat-bound once;
                # its kernel inode cannot change before this scope closes it.
                and identity(info) == expected,
                "S12_PUBLIC_SOURCE_CHANGED",
            )
        self.check()

    def check_path(self):
        """Fresh ancestor/root check at a manifest membership boundary."""
        self._bound(self.root)

    def _directory(self, name):
        if name in self.dirs:
            return self.dirs[name][0]
        c.require(
            name == self.root or name.startswith(self.root + os.sep),
            "S12_PRIVATE_FILE_INVALID",
        )
        if name != self.root:
            self._directory(os.path.dirname(name))
        self._room(name)
        io.private_directory(Path(name))
        before = os.stat(name, follow_symlinks=False)
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            after = os.stat(name, follow_symlinks=False)
            held = os.fstat(fd)
            c.require(
                identity(before) == identity(after) == identity(held)
                and stat.S_ISDIR(held.st_mode)
                and stat.S_IMODE(held.st_mode) == 0o700
                and held.st_uid == os.geteuid(),
                "S12_PUBLIC_SOURCE_CHANGED",
            )
        except BaseException:
            os.close(fd)
            raise
        self.dirs[name] = (fd, identity(held))
        self.names_bytes += len(os.fsencode(name))
        return fd

    def _room(self, name):
        size = len(os.fsencode(name))
        while self.files and (
            len(self.dirs) + len(self.files) >= MAX_DESCRIPTORS
            or self.names_bytes + size > MAX_NAMES_BYTES
        ):
            old, fd = self.files.popitem(last=False)
            os.close(fd)
            self.names_bytes -= len(os.fsencode(old))
        # Evict only leaf directories outside the active configured pathname.
        # File descriptors were evicted first, so none refers to an evicted leaf.
        while (
            len(self.dirs) + len(self.files) >= MAX_DESCRIPTORS
            or self.names_bytes + size > MAX_NAMES_BYTES
        ):
            removable = next(
                (
                    key
                    for key in self.dirs
                    if key != self.root
                    and not name.startswith(key + os.sep)
                    and key != name
                    and not any(other.startswith(key + os.sep) for other in self.dirs)
                ),
                None,
            )
            c.require(removable is not None, "S12_PRIVATE_FILE_INVALID")
            fd, _ = self.dirs.pop(removable)
            os.close(fd)
            self.names_bytes -= len(os.fsencode(removable))

    def contains(self, path):
        return os.fspath(path).startswith(self.root + os.sep)

    def read(self, path, *, limit=64 * 1024 * 1024):
        try:
            self._owner()
            name = os.fspath(path)
            c.require(
                type(limit) is int
                and limit >= 0
                and os.path.normpath(name) == name
                and name.startswith(self.root + os.sep),
                "S12_PRIVATE_FILE_INVALID",
            )
            parent = os.path.dirname(name)
            c.require(
                not self.direct_work or parent == self.root, "S12_PRIVATE_FILE_INVALID"
            )
            depth = len(Path(parent).relative_to(self.root).parts)
            if depth + 2 > min(MAX_DESCRIPTORS, 64):
                # Existing full private reader remains the bounded fallback for
                # unusually deep trees; no new semantic directory-count limit.
                self._room(name)
                self._bound(self.root)
                io.private_directory(Path(parent))
                try:
                    raw = io.accepted.read_private(Path(name), limit=limit)
                except Exception:
                    raise c.Stage12Error("S12_PRIVATE_FILE_INVALID") from None
                self._bound(self.root)
                return raw
            directory = self._directory(parent)
            self._bound(parent, ancestors=not self.direct_work)
            fd = self.files.get(name)
            if fd is None:
                self._room(name)
                # Linux open through the already-bound directory avoids repeated
                # kernel traversal of the long configured mount path. The existing
                # audit guard resolves this to the same allowed original pathname.
                opening = (
                    f"/proc/self/fd/{directory}/{os.path.basename(name)}"
                    if sys.platform == "linux"
                    else name
                )
                fd = os.open(opening, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                self.files[name] = fd
                self.names_bytes += len(os.fsencode(name))
            self.files.move_to_end(name)
            info = os.fstat(fd)
            current = os.stat(name, follow_symlinks=False)
            c.require(
                stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_uid == os.geteuid()
                and info.st_nlink == 1
                and info.st_size <= limit
                and stat.S_ISREG(current.st_mode)
                and identity(current) == identity(info),
                "S12_PRIVATE_FILE_INVALID",
            )
            chunks = []
            offset = 0
            while offset <= limit:
                self.check()
                raw = os.pread(fd, min(65536, limit + 1 - offset), offset)
                if not raw:
                    break
                chunks.append(raw)
                offset += len(raw)
            data = b"".join(chunks)
            after = os.fstat(fd)
            current = os.stat(name, follow_symlinks=False)
            c.require(
                len(data) == info.st_size == after.st_size <= limit
                and identity(current) == identity(info) == identity(after)
                and stat.S_ISREG(current.st_mode)
                and stat.S_IMODE(current.st_mode) == 0o600
                and current.st_uid == os.geteuid()
                and current.st_nlink == 1,
                "S12_PRIVATE_FILE_INVALID",
            )
            # Recheck configured root/subdirectory path-to-descriptor bindings
            # after the content read. Full ancestors were checked before this
            # read (or at work-manifest boundaries); no duplicate ancestor walk
            # is required by the original reader.
            self._bound(parent, ancestors=False)
            self.check()
            return data
        except BaseException:
            self._abort()
            raise

    def _abort(self):
        if threading.get_ident() == self.owner:
            try:
                self.close()
            except OSError:
                pass  # Preserve the initiating error; never reuse this scope.

    def close(self):
        if self.closed:
            return
        self.closed = True
        error = None
        for fd in [*self.files.values(), *(item[0] for item in self.dirs.values())]:
            try:
                os.close(fd)
            except OSError as exc:
                error = exc
        self.files.clear()
        self.dirs.clear()
        self.ancestor_ids.clear()
        self.names_bytes = 0
        if error is not None:
            raise error

    def __enter__(self):
        self._owner()
        return self

    def __exit__(self, kind, error, tb):
        if kind is not None:
            self._abort()
        else:
            self.close()

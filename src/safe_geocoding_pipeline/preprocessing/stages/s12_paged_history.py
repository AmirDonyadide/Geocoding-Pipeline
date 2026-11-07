"""Selected finite fresh-original history without a population index or spill.

Numeric event namespaces enumerate directly. Arbitrary filenames use bounded
successor-page selection scans in exact Path order. A page fill validates the
whole original content commitment afresh before exposing any page member. No
commitment is reusable by another validation stage. This is a logical backing
bound; WF-AP2 M2 supplies no native component-memory proof.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import stat
import threading

from . import s12_public_history as old
from . import s12_retrieval_contract as c
from . import s12_storage as io

BUCKETS = 4096
_selected = threading.local()


def validate_limits(limits):
    c.require(
        type(limits) is dict
        and set(limits)
        == {
            "maximum_entries",
            "maximum_name_bytes",
            "maximum_total_name_bytes",
            "page_entries",
            "maximum_depth",
            "maximum_file_bytes",
        },
        "S12_PUBLIC_HISTORY_LIMIT",
    )
    for value in limits.values():
        c.require(type(value) is int and 1 <= value < 2**64, "S12_PUBLIC_HISTORY_LIMIT")
    c.require(
        limits["maximum_name_bytes"] <= 1024
        and limits["maximum_depth"] <= 8
        and limits["page_entries"] <= 512
        and limits["maximum_file_bytes"] <= 2**63 - 1,
        "S12_PUBLIC_HISTORY_LIMIT",
    )
    c.require(
        limits["maximum_name_bytes"] <= limits["maximum_total_name_bytes"],
        "S12_PUBLIC_HISTORY_LIMIT",
    )
    c.require(reservation(limits) <= old.MAX_BACKING, "S12_PUBLIC_HISTORY_LIMIT")


def reservation(limits):
    # One selection page, one active digest page, bounded names/identity tuples,
    # fixed retained/build commitment tables, aggregate scratch, bounded
    # ancestor names, and the capped original-reader descriptor metadata.
    return 3 * limits["page_entries"] * (limits["maximum_name_bytes"] + 128) + 917504


@contextmanager
def selected(limits):
    validate_limits(limits)
    previous = getattr(_selected, "limits", None)
    _selected.limits = limits
    try:
        yield
    finally:
        _selected.limits = previous


def current():
    return getattr(_selected, "limits", None)


def _identity(info):
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


def _scan(root, limits, check):
    count = names = 0
    for path, info, directory in old.walk(root, check=check):
        name = path.relative_to(root).as_posix() if path != root else ""
        raw = name.encode("utf8")
        count += 1
        names += len(raw)
        c.require(
            count <= limits["maximum_entries"]
            and names <= limits["maximum_total_name_bytes"]
            and len(raw) <= limits["maximum_name_bytes"]
            and name.count("/") <= limits["maximum_depth"],
            "S12_PUBLIC_HISTORY_LIMIT",
        )
        if not directory:
            c.require(
                info.st_size <= limits["maximum_file_bytes"], "S12_PUBLIC_HISTORY_LIMIT"
            )
        yield name, info, directory


def ordered(root, limits, *, check=io._checkpoint, strict=True):
    """Exact all-family ordering with a fixed selected page and no disk scratch."""
    root = Path(root).absolute()
    validate_limits(limits)
    count = names = 0

    def charge(path, info, directory):
        nonlocal count, names
        name = path.relative_to(root).as_posix() if path != root else ""
        length = len(name.encode("utf8"))
        count += 1
        names += length
        c.require(
            count <= limits["maximum_entries"]
            and names <= limits["maximum_total_name_bytes"]
            and length <= limits["maximum_name_bytes"]
            and name.count("/") <= limits["maximum_depth"],
            "S12_PUBLIC_HISTORY_LIMIT",
        )
        c.require(
            directory or info.st_size <= limits["maximum_file_bytes"],
            "S12_PUBLIC_HISTORY_LIMIT",
        )
        return name, info, directory

    def visit(directory):
        check()
        io.private_directory(directory)
        yield charge(directory, directory.stat(follow_symlinks=False), True)
        if directory.name == "events" and strict:
            for path in event_paths(directory, limits, check=check):
                yield charge(path, path.stat(follow_symlinks=False), False)
            return
        after = None
        while True:
            page = []
            scanned = 0
            with os.scandir(directory) as entries:
                for entry in entries:
                    check()
                    scanned += 1
                    c.require(
                        scanned <= limits["maximum_entries"], "S12_PUBLIC_HISTORY_LIMIT"
                    )
                    name = entry.name
                    c.require(
                        len(name.encode("utf8")) <= limits["maximum_name_bytes"],
                        "S12_PUBLIC_HISTORY_LIMIT",
                    )
                    if after is not None and name <= after:
                        continue
                    if len(page) < limits["page_entries"]:
                        page.append(name)
                        page.sort()
                    elif name < page[-1]:
                        page[-1] = name
                        page.sort()
            if not page:
                return
            for name in page:
                path = directory / name
                info = path.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    yield from visit(path)
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
                    yield charge(path, info, False)
            after = page[-1]

    yield from visit(root)


def event_paths(root, limits, *, check=io._checkpoint):
    """Validate one canonical contiguous numeric namespace before original reads."""
    root = Path(root).absolute()
    io.private_directory(root)
    before = root.stat(follow_symlinks=False)
    count = high = 0
    low = None
    names = 0
    with os.scandir(root) as entries:
        for entry in entries:
            check()
            name, info = entry.name, entry.stat(follow_symlinks=False)
            c.require(
                len(name) == 25
                and name.endswith(".json")
                and name[:20].isascii()
                and name[:20].isdigit(),
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            n = int(name[:20])
            c.require(n > 0 and name == f"{n:020d}.json", "S12_PUBLIC_SOURCE_CHANGED")
            c.require(
                stat.S_ISREG(info.st_mode)
                and info.st_nlink == 1
                and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o600
                and info.st_size <= min(4096, limits["maximum_file_bytes"]),
                "S12_PRIVATE_FILE_INVALID",
            )
            count += 1
            names += len(name)
            c.require(
                count <= limits["maximum_entries"]
                and names <= limits["maximum_total_name_bytes"]
                and len(name) <= limits["maximum_name_bytes"],
                "S12_PUBLIC_HISTORY_LIMIT",
            )
            low, high = n if low is None else min(low, n), max(high, n)
    c.require(not count or high - low + 1 == count, "S12_PUBLIC_SOURCE_CHANGED")
    if low is not None:
        for n in range(low, high + 1):
            check()
            path = root / f"{n:020d}.json"
            # A new enumeration is still required at the closing fence; each
            # original reader separately binds this pathname/inode/content.
            yield path
    after = root.stat(follow_symlinks=False)
    c.require(_identity(before) == _identity(after), "S12_PUBLIC_SOURCE_CHANGED")


def ordered_files(root, limits, *, check=io._checkpoint):
    if Path(root).name == "events":
        yield from event_paths(root, limits, check=check)
        return
    for name, _, directory in ordered(root, limits, check=check):
        if not directory:
            yield Path(root) / name


def lineage(root, maximum, *, check=io._checkpoint):
    """Fresh oldest-first chain without retaining a root-path list or set.

    At most512 selected scientific segments; bounded repeated predecessor
    traversal is charged separately from source-file enumeration.
    """
    from . import s12_public_journal as journal

    c.require(type(maximum) is int and 1 <= maximum <= 512, "S12_PUBLIC_HISTORY_LIMIT")
    count = 0
    node = root
    while node is not None:
        check()
        count += 1
        c.require(count <= maximum, "S12_PUBLIC_SOURCE_CHANGED")
        node = journal.predecessor_root(node)
    for depth in range(count - 1, -1, -1):
        node = root
        for _ in range(depth):
            check()
            node = journal.predecessor_root(node)
            c.require(node is not None, "S12_PUBLIC_SOURCE_CHANGED")
        check()
        yield node


class Fresh(old.Fresh):
    """Independent fresh stage with one bounded identity/hash page and no cache."""

    def __init__(self, root, *, limits=None, **kwargs):
        super().__init__(root, **kwargs)
        self.limits = limits or current()
        validate_limits(self.limits)
        self.page = []
        self.additions = {}
        self.pending_outputs = set()
        self._reserved = 0
        self.baseline = None
        self.membership_digest = None
        self.bucket_digests = None
        self.numeric_digests = None
        self.numeric_epoch = None

    def _members(self):
        yield from ordered(self.root, self.limits, check=self.check)

    def _bucket(self, name):
        buckets = min(
            BUCKETS,
            max(1, self.limits["maximum_entries"] // self.limits["page_entries"]),
        )
        parent, _, filename = name.rpartition("/")
        if parent.rsplit("/", 1)[-1] == "events" or (
            self.root.name == "events" and not parent
        ):
            stem = filename[:-5] if filename.endswith(".json") else ""
            if len(stem) == 20 and stem.isascii() and stem.isdigit():
                n = int(stem)
                c.require(
                    1 <= n <= self.limits["maximum_entries"], "S12_PUBLIC_HISTORY_LIMIT"
                )
                return min(
                    buckets - 1, (n - 1) * buckets // self.limits["maximum_entries"]
                )
        return (
            int.from_bytes(hashlib.sha256(name.encode("utf8")).digest()[:2], "big")
            % buckets
        )

    def _numeric_dirs(self):
        if self.root.name == "events":
            yield self.root
        elif (self.root / "events").is_dir():
            yield self.root / "events"

    def _numeric_epoch(self):
        fingerprint = hashlib.sha256()
        for directory in self._numeric_dirs():
            self.check()
            io.private_directory(directory)
            self.reader._directory(str(directory))
            self.reader._bound(str(directory))
            fingerprint.update(
                c.canonical(
                    [
                        directory.relative_to(self.root).as_posix(),
                        _identity(directory.stat(follow_symlinks=False)),
                    ]
                )
            )
        return fingerprint.digest()

    def _numeric_name(self, name):
        parent, _, filename = name.rpartition("/")
        return (
            (
                parent.rsplit("/", 1)[-1] == "events"
                or self.root.name == "events"
                and not parent
            )
            and len(filename) == 25
            and filename.endswith(".json")
            and filename[:20].isascii()
            and filename[:20].isdigit()
        )

    def _numeric_page(self, target):
        # Initial and final stages still enumerate/hash the complete source.
        # Between them an exact directory epoch fences the canonical numeric
        # namespace, and original bucket commitments bind each returned page.
        before = self._numeric_epoch()
        c.require(before == self.numeric_epoch, "S12_PUBLIC_SOURCE_CHANGED")
        bucket = self._bucket(target)
        buckets = min(
            BUCKETS,
            max(1, self.limits["maximum_entries"] // self.limits["page_entries"]),
        )
        first = (bucket * self.limits["maximum_entries"] + buckets - 1) // buckets + 1
        last = ((bucket + 1) * self.limits["maximum_entries"] + buckets - 1) // buckets
        fingerprint = bytes(32)
        page = []
        taking = False
        for directory in self._numeric_dirs():
            for n in range(first, last + 1):
                self.check()
                path = directory / f"{n:020d}.json"
                name = path.relative_to(self.root).as_posix()
                if name in self.additions:
                    self._registered(path, name)
                    continue
                try:
                    info = path.stat(follow_symlinks=False)
                except FileNotFoundError:
                    continue
                identity = _identity(info)
                digest = old.hash_file(
                    path,
                    reader=self.reader,
                    maximum_bytes=self.limits["maximum_file_bytes"],
                )
                fingerprint = hashlib.sha256(
                    fingerprint + c.canonical([name, False, identity, digest])
                ).digest()
                if name == target:
                    taking = True
                if taking and len(page) < self.limits["page_entries"]:
                    page.append((name, identity, digest))
        offset = bucket * 32
        c.require(
            fingerprint == self.numeric_digests[offset : offset + 32]
            and self._numeric_epoch() == before,
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        return self.baseline, page

    def _snapshot(self, target=None):
        if (
            target is not None
            and self._numeric_name(target)
            and self.numeric_epoch is not None
        ):
            return self._numeric_page(target)
        membership = hashlib.sha256()
        table = bytearray(BUCKETS * 32) if target is None else None
        numeric_table = bytearray(BUCKETS * 32) if target is None else None
        target_bucket = None if target is None else self._bucket(target)
        selected_digest = bytes(32)
        captured = []
        taking = False
        additions_seen = 0
        for name, info, directory in self._members():
            if name in self.outputs and name not in self.additions:
                c.require(
                    self.baseline is not None and not directory,
                    "S12_PUBLIC_SOURCE_CHANGED",
                )
                self.pending_outputs.add(name)
                continue
            if name in self.additions:
                additions_seen += 1
                c.require(not directory, "S12_PUBLIC_SOURCE_CHANGED")
                self._registered(self.root / name, name)
                continue
            identity = (
                (info.st_dev, info.st_ino, info.st_mode, info.st_uid)
                if directory
                else _identity(info)
            )
            metadata = c.canonical([name, bool(directory), identity])
            membership.update(metadata)
            bucket = self._bucket(name)
            if target is not None and bucket != target_bucket:
                continue
            digest = (
                None
                if directory
                else old.hash_file(
                    self.root / name,
                    reader=self.reader,
                    maximum_bytes=self.limits["maximum_file_bytes"],
                )
            )
            framed = c.canonical([name, bool(directory), identity, digest])
            if table is not None:
                offset = bucket * 32
                table[offset : offset + 32] = hashlib.sha256(
                    table[offset : offset + 32] + framed
                ).digest()
                if not directory and self._numeric_name(name):
                    numeric_table[offset : offset + 32] = hashlib.sha256(
                        numeric_table[offset : offset + 32] + framed
                    ).digest()
            else:
                selected_digest = hashlib.sha256(selected_digest + framed).digest()
            if name == target:
                taking = True
            if taking and len(captured) < self.limits["page_entries"] and not directory:
                captured.append((name, identity, digest))
        c.require(additions_seen == len(self.additions), "S12_PUBLIC_SOURCE_CHANGED")
        metadata_digest = membership.digest()
        if table is not None:
            aggregate = hashlib.sha256(metadata_digest + table).digest()
            if self.baseline is None:
                self.bucket_digests[:] = table
                self.membership_digest = metadata_digest
                self.numeric_digests[:] = numeric_table
                self.numeric_epoch = self._numeric_epoch()
            return aggregate, captured
        offset = target_bucket * 32
        c.require(
            metadata_digest == self.membership_digest
            and selected_digest == self.bucket_digests[offset : offset + 32],
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        return self.baseline, captured

    def __enter__(self):
        self._owner()
        c.require(self.state == "NEW")
        self.parent_view = getattr(io._checkpoints, "read_view", None)
        self.parent_original = getattr(io._checkpoints, "original_view", None)
        c.require(
            self.parent_view is None or isinstance(self.parent_view, old.Fresh),
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        io._checkpoints.read_view = io._checkpoints.original_view = None
        try:
            self.boundary()
            with old._backing_lock:
                needed = reservation(self.limits)
                c.require(
                    needed <= old.MAX_BACKING - old._backing, "S12_PUBLIC_HISTORY_LIMIT"
                )
                old._backing += needed
                self._reserved = needed
            self.bucket_digests = bytearray(BUCKETS * 32)
            self.numeric_digests = bytearray(BUCKETS * 32)
            self.reader = old._reader_type(self.reader_root, check=self.check)
            self.original_scope = io.public_originals(self.reader)
            self.original_scope.__enter__()
            self.baseline, _ = self._snapshot()
            self.boundary()
            self.hook = io.read_view(self)
            self.hook.__enter__()
            self.state = "ACTIVE"
            return self
        except BaseException:
            self.abort(suppress_cleanup=True)
            raise

    def _registered(self, path, name):
        digest, expected = self.additions[name]
        c.require(
            _identity(path.stat(follow_symlinks=False)) == expected,
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        observed = old.hash_file(
            path, reader=self.reader, maximum_bytes=self.limits["maximum_file_bytes"]
        )
        c.require(
            observed == digest
            and _identity(path.stat(follow_symlinks=False)) == expected,
            "S12_PUBLIC_SOURCE_CHANGED",
        )

    def read(self, path, *, limit, original):
        self._owner()
        c.require(self.state == "ACTIVE")
        path = Path(path).absolute()
        if not path.is_relative_to(self.root):
            return original(path, limit=limit)
        name = path.relative_to(self.root).as_posix()
        if name in self.additions:
            digest, expected = self.additions[name]
            c.require(
                _identity(path.stat(follow_symlinks=False)) == expected,
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            raw = original(path, limit=limit)
            c.require(
                c.sha(raw).hex() == digest
                and _identity(path.stat(follow_symlinks=False)) == expected,
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            return raw
        row = next((row for row in self.page if row[0] == name), None)
        if row is None:
            observed, self.page = self._snapshot(target=name)
            c.require(observed == self.baseline, "S12_PUBLIC_SOURCE_CHANGED")
            row = next((row for row in self.page if row[0] == name), None)
        c.require(row is not None, "S12_PUBLIC_SOURCE_CHANGED")
        raw = original(path, limit=limit)
        c.require(
            _identity(path.stat(follow_symlinks=False)) == row[1]
            and c.sha(raw).hex() == row[2],
            "S12_PUBLIC_SOURCE_CHANGED",
        )
        return raw

    def output(self, path, digest):
        self._owner()
        path = Path(path).absolute()
        if not path.is_relative_to(self.root):
            return
        name = path.relative_to(self.root).as_posix()
        c.require(name in self.outputs and name not in self.additions)
        identity = _identity(path.stat(follow_symlinks=False))
        c.require(
            old.hash_file(
                path,
                reader=self.reader,
                maximum_bytes=self.limits["maximum_file_bytes"],
            )
            == digest
            and _identity(path.stat(follow_symlinks=False)) == identity
        )
        self.additions[name] = (digest, identity)
        self.pending_outputs.discard(name)
        if self._numeric_name(name):
            # A declared generated event is accepted only after all prior
            # original membership and bytes have been freshly revalidated.
            observed, _ = self._snapshot()
            c.require(observed == self.baseline, "S12_PUBLIC_SOURCE_CHANGED")
            self.numeric_epoch = self._numeric_epoch()

    def finish(self):
        self._owner()
        c.require(self.state == "ACTIVE")
        self.hook.__exit__(None, None, None)
        self.hook = None
        self.state = "VERIFYING"
        try:
            self.boundary()
            c.require(
                self._numeric_epoch() == self.numeric_epoch, "S12_PUBLIC_SOURCE_CHANGED"
            )
            observed, _ = self._snapshot()
            c.require(
                not self.pending_outputs
                and self._numeric_epoch() == self.numeric_epoch
                and observed == self.baseline,
                "S12_PUBLIC_SOURCE_CHANGED",
            )
            self.boundary()
            self.state = "VERIFIED"
        except BaseException:
            self.state = "INVALID"
            raise
        finally:
            self._close(suppress=self.state == "INVALID")

    def _close(self, *, suppress=False):
        try:
            super()._close(suppress=suppress)
        finally:
            self.page.clear()
            self.additions.clear()
            self.pending_outputs.clear()
            self.bucket_digests = self.numeric_digests = None
            with old._backing_lock:
                old._backing -= self._reserved
                self._reserved = 0


def inventory(root, *, check=io._checkpoint):
    limits = current()
    c.require(limits is not None, "S12_PUBLIC_HISTORY_LIMIT")
    for path in ordered_files(root, limits, check=check):
        yield {
            "path": path.relative_to(root).as_posix(),
            "sha256": old.hash_file(path, maximum_bytes=limits["maximum_file_bytes"]),
        }


class ChainFresh(Fresh):
    """One shared arena/page across every selected predecessor root."""

    def __init__(self, root, roots, *, limits, **kwargs):
        super().__init__(root, limits=limits, **kwargs)
        self.roots = roots

    def _members(self):
        previous = getattr(io._checkpoints, "read_view", None)
        io._checkpoints.read_view = None
        try:
            yield from self._chain_members()
        finally:
            io._checkpoints.read_view = previous

    def _numeric_dirs(self):
        previous = getattr(io._checkpoints, "read_view", None)
        io._checkpoints.read_view = None
        try:
            for root in self.roots():
                directory = root / "events"
                if directory.is_dir():
                    yield directory
        finally:
            io._checkpoints.read_view = previous

    def _chain_members(self):
        count = names = 0
        for root in self.roots():
            c.require(root.is_relative_to(self.root), "S12_PUBLIC_SOURCE_CHANGED")
            for name, info, directory in ordered(root, self.limits, check=self.check):
                relative = (root / name).relative_to(self.root).as_posix()
                count += 1
                names += len(relative.encode("utf8"))
                c.require(
                    count <= self.limits["maximum_entries"]
                    and names <= self.limits["maximum_total_name_bytes"]
                    and len(relative.encode("utf8"))
                    <= self.limits["maximum_name_bytes"],
                    "S12_PUBLIC_HISTORY_LIMIT",
                )
                yield relative, info, directory

    def read(self, path, *, limit, original):
        previous = getattr(io._checkpoints, "read_view", None)
        io._checkpoints.read_view = None
        try:
            contained = any(
                Path(path).absolute().is_relative_to(root) for root in self.roots()
            )
        finally:
            io._checkpoints.read_view = previous
        if not contained:
            self._owner()
            return original(path, limit=limit)
        return super().read(path, limit=limit, original=original)


class Known:
    """Bounded uncertain-input projection; unknown originals remain unknown.

    Each traversal recomputes the complete original commitment. No persisted
    inventory, previous reader token or per-file database grants trust.
    """

    OUTPUTS = old.Known.OUTPUTS

    def __init__(self, root, verify_known=None, *, limits=None):
        self.root = Path(root).absolute()
        self.limits = limits or current()
        validate_limits(self.limits)
        self.confirmed = self.verified = 0
        self.closed = False
        self.existing_outputs = frozenset(
            name for name in self.OUTPUTS if (self.root / name).exists()
        )
        self._reserved = 0
        with old._backing_lock:
            needed = reservation(self.limits)
            c.require(
                needed <= old.MAX_BACKING - old._backing, "S12_PUBLIC_HISTORY_LIMIT"
            )
            old._backing += needed
            self._reserved = needed
        try:
            self.baseline = self._commitment()
            for name, _, digest in self._rows():
                if digest is None or not (
                    name.endswith("/begin.json")
                    or name.endswith("_begin.json")
                    and not name.endswith("_validation_begin.json")
                ):
                    continue
                path = self.root / name
                try:
                    obj = io.metadata(io.original_read(path, limit=65536))
                    c.require(
                        type(obj.get("attempt")) is int and 1 <= obj["attempt"] <= 5
                    )
                    self.confirmed += 1
                    if verify_known is not None:
                        self.verified += bool(verify_known(path.parent, obj))
                except (c.Stage12Error, OSError, ValueError):
                    continue
            c.require(self._commitment() == self.baseline, "S12_PUBLIC_SOURCE_CHANGED")
        except BaseException:
            self.close()
            raise

    def _rows(self):
        c.require(not self.closed, "S12_PUBLIC_SOURCE_CHANGED")
        for name, info, directory in ordered(self.root, self.limits, strict=False):
            if name in self.OUTPUTS and name not in self.existing_outputs:
                continue
            if directory:
                yield name, (info.st_dev, info.st_ino, info.st_mode, info.st_uid), None
                continue
            digest = None
            try:
                digest = old.hash_file(
                    self.root / name, maximum_bytes=self.limits["maximum_file_bytes"]
                )
            except (c.Stage12Error, OSError):
                pass
            yield name, _identity(info), digest

    def _commitment(self):
        fingerprint = hashlib.sha256()
        for row in self._rows():
            fingerprint.update(c.canonical(row))
        return fingerprint.digest()

    def rows(self, prefix=""):
        c.require(self._commitment() == self.baseline, "S12_PUBLIC_SOURCE_CHANGED")
        for name, _, digest in self._rows():
            if digest is not None and name.startswith(prefix):
                yield {"path": name, "sha256": digest}
        c.require(self._commitment() == self.baseline, "S12_PUBLIC_SOURCE_CHANGED")

    def __iter__(self):
        return self.rows()

    def close(self):
        self.closed = True
        with old._backing_lock:
            old._backing -= self._reserved
            self._reserved = 0

"""B2-only bounded original metadata reads; no trusted cross-stage cache."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import shutil
import threading
from contextlib import contextmanager

from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_catalog as catalog
from . import s12_public_journal as journal
from . import s12_storage as io

ROW_BYTES = 65536


def binding(path):
    """Bind configured ancestors as well as the opened file, not just an fd."""
    path = Path(path).absolute()
    io.private_directory(path.parent)
    result = []
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        b.require(not stat.S_ISLNK(info.st_mode), "B2_METADATA_BINDING")
        result.append(
            (
                str(part),
                info.st_dev,
                info.st_ino,
                stat.S_IMODE(info.st_mode),
                info.st_uid,
            )
        )
    return tuple(result)


def _file_state(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_array(path, *, max_bytes, max_rows, check=io._checkpoint):
    """Canonical arrays may exceed 64MiB only under explicit B2 bounds.

    The original bytes are parsed and checked anew on every invocation. One
    <=64KiB row plus one 4KiB read chunk is held; no whole-file read occurs.
    """
    b.uint(max_bytes, True)
    b.uint(max_rows)
    before_path = binding(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    before = os.fstat(fd)
    try:
        b.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) in (0o400, 0o600)
            and before.st_size <= max_bytes
            and (before.st_dev, before.st_ino) == before_path[-1][1:3],
            "B2_METADATA_BOUND",
        )
        decoder = json.JSONDecoder(object_pairs_hook=io.pairs)
        buffer, eof = "", False
        count = 0

        def fill():
            nonlocal buffer, eof
            check()
            raw = os.read(fd, 4096)
            eof = not raw
            try:
                buffer += raw.decode("ascii")
            except UnicodeError:
                b.require(False, "B2_METADATA_CANONICAL")
            b.require(len(buffer) <= ROW_BYTES + 4096, "B2_METADATA_BOUND")

        fill()
        b.require(buffer.startswith("["), "B2_METADATA_CANONICAL")
        buffer = buffer[1:]
        first = True
        while True:
            while not buffer and not eof:
                fill()
            if buffer.startswith("]"):
                break
            if not first:
                b.require(buffer.startswith(","), "B2_METADATA_CANONICAL")
                buffer = buffer[1:]
            while True:
                try:
                    item, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    b.require(not eof, "B2_METADATA_CANONICAL")
                    fill()
            count += 1
            b.require(
                count <= max_rows
                and end <= ROW_BYTES
                and type(item) is dict
                and b.canonical(item)[:-1].decode("ascii") == buffer[:end],
                "B2_METADATA_CANONICAL",
            )
            buffer = buffer[end:]
            first = False
            yield item
        while not eof:
            fill()
        b.require(
            buffer == "]\n"
            and _file_state(before) == _file_state(os.fstat(fd))
            and binding(path) == before_path,
            "B2_METADATA_CHANGED",
        )
    finally:
        os.close(fd)


def array_bounds(plan, name):
    amounts = plan["budgets"]
    works = amounts["data_observations"] + amounts["required_control_observations"]
    if name in ("work.json", "work_ledger.json", "remaining_work_ledger.json"):
        rows = works
    elif name == "event_inventory.json":
        rows = amounts["event_count"]
    elif name == "attempt_inventory.json":
        # DATA has at most 11 fixed files; controls at most 8. Twelve is a
        # conservative per-attempt member bound, not a payload-size estimate.
        rows = 12 * (amounts["data_attempts"] + amounts["control_http_attempts"])
    else:
        b.require(False, "B2_METADATA_ROLE")
    return {
        "max_bytes": min(amounts["storage_bytes"], 3 + rows * (ROW_BYTES + 1)),
        "max_rows": rows,
    }


def read_role(root, name, plan, *, check=io._checkpoint):
    return read_array(root / name, check=check, **array_bounds(plan, name))


def stream_array(log, name, rows, plan):
    """Derive outside writer actions; one <=64KiB row plus delimiters per batch."""
    bound = array_bounds(plan, name)
    path = log.writer.root / name
    state = {"fd": None, "size": 0}
    fingerprint = hashlib.sha256()

    def put(raw):
        log.writer.assert_owner()
        b.require(state["size"] + len(raw) <= bound["max_bytes"], "B2_METADATA_BOUND")
        log.check_storage(len(raw))
        if state["fd"] is None:
            io.private_directory(path.parent)
            state["fd"] = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
        io.charge_write(path, len(raw))
        view = memoryview(raw)
        while view:
            written = os.write(state["fd"], view)
            b.require(written > 0, "B2_METADATA_WRITE")
            view = view[written:]
        fingerprint.update(raw)
        state["size"] += len(raw)

    def close():
        if state["fd"] is not None:
            try:
                os.fsync(state["fd"])
            finally:
                os.close(state["fd"])
                state["fd"] = None
            io.fsync_directory(path.parent)

    try:
        batch = bytearray(b"[")
        for count, row in enumerate(rows, 1):
            log.writer.check_deadline()
            raw = b.canonical(row)[:-1]
            b.require(
                count <= bound["max_rows"] and len(raw) <= ROW_BYTES,
                "B2_METADATA_BOUND",
            )
            raw = (b"," if count > 1 else b"") + raw
            if len(batch) + len(raw) > ROW_BYTES:
                log.writer.call(lambda raw=bytes(batch): put(raw))
                batch.clear()
            batch.extend(raw)
        batch.extend(b"]\n")
        log.writer.call(lambda: put(bytes(batch)))
        log.writer.call(close)
        b.require(
            o.manifest_digest(
                read_role(log.writer.root, name, plan, check=log.writer.check_deadline)
            )
            == fingerprint.hexdigest(),
            "B2_METADATA_CHANGED",
        )
        io.record_read_output(path, fingerprint.hexdigest())
        return fingerprint.hexdigest()
    except BaseException:
        # Never use an uncertain writer to finish or seal partial evidence.
        if not log.writer.failed.is_set():
            try:
                log.writer.call(close)
            except BaseException:
                pass
        raise


def lineage(root, max_segments):
    result, seen = [], set()
    while root is not None:
        io._checkpoint()
        b.require(
            str(root) not in seen and len(result) < max_segments, "B2_RECOVERY_CYCLE"
        )
        seen.add(str(root))
        result.append(root)
        root = journal.predecessor_root(root)
    yield from reversed(result)


_ordering_context = threading.local()


@contextmanager
def ordering_scope(root, observe):
    """Bind all current/predecessor spill to the runtime's accounted namespace."""
    io.private_directory(root)
    previous = getattr(_ordering_context, "scope", None)
    _ordering_context.scope = (root, observe)
    try:
        yield
    finally:
        _ordering_context.scope = previous


def ordered_files(root, *, max_files, max_scratch_bytes):
    """Exact lexical membership on a bounded, physically observed disk index.

    Only successful derived ordering scratch is removed. Failure/uncertainty
    preserves it in the same registered runtime temporary namespace. Original
    evidence is never deleted or replaced by this stage-local index.
    """
    b.uint(max_files)
    b.uint(max_scratch_bytes, True)
    b.require(max_scratch_bytes >= 4096, "B2_INVENTORY_BOUND")
    root_binding = binding(root)
    io.private_directory(root)
    scope = getattr(_ordering_context, "scope", None)
    temporary, observe = (
        scope if scope is not None else (root.parent.parent, lambda force=False: None)
    )
    io.private_directory(temporary)
    tmp = Path(tempfile.mkdtemp(prefix=".b2-order-", dir=temporary))
    db = None
    count = 0

    def check():
        io._checkpoint()
        # The real observer applies the existing selected interval. This is a
        # cheap clock check per entry, not a recursive scan per event.
        observe(False)

    def scan(directory, prefix=""):
        b.require(prefix.count("/") <= 2, "B2_INVENTORY_DEPTH")
        with os.scandir(directory) as entries:
            for entry in entries:
                check()
                info = entry.stat(follow_symlinks=False)
                relative = prefix + entry.name
                b.require(
                    len(relative.encode("utf8")) <= 4096
                    and not stat.S_ISLNK(info.st_mode),
                    "B2_INVENTORY_MEMBER",
                )
                if stat.S_ISDIR(info.st_mode):
                    io.private_directory(Path(entry.path))
                    yield from scan(Path(entry.path), relative + "/")
                else:
                    b.require(
                        stat.S_ISREG(info.st_mode)
                        and info.st_nlink == 1
                        and info.st_uid == os.geteuid()
                        and stat.S_IMODE(info.st_mode) in (0o400, 0o600),
                        "B2_INVENTORY_MEMBER",
                    )
                    yield relative, info

    try:
        observe(True)
        db = catalog.connect(tmp / "members.sqlite")
        db.execute("pragma max_page_count=" + str(max_scratch_bytes // 4096))
        db.execute(
            "create table member(path text primary key, dev integer, ino integer, size integer, mt integer, ct integer, mode integer) without rowid"
        )
        for name, info in scan(root):
            count += 1
            b.require(count <= max_files, "B2_INVENTORY_BOUND")
            db.execute(
                "insert into member values(?,?,?,?,?,?,?)",
                (name, *_file_state(info), stat.S_IMODE(info.st_mode)),
            )
        # Observe while the database and rollback journal are still linked;
        # neither may disappear at commit before the runtime counts them.
        observe(True)
        db.commit()
        observe(True)
        for (name,) in db.execute("select path from member order by path"):
            check()
            yield root / name
        after = 0
        for name, info in scan(root):
            after += 1
            row = db.execute(
                "select dev,ino,size,mt,ct,mode from member where path=?", (name,)
            ).fetchone()
            b.require(
                row == (*_file_state(info), stat.S_IMODE(info.st_mode)),
                "B2_INVENTORY_CHANGED",
            )
        b.require(
            after == count and binding(root) == root_binding, "B2_INVENTORY_CHANGED"
        )
        # Forced even if the selected observation interval has not elapsed.
        observe(True)
        db.close()
        db = None
        shutil.rmtree(tmp)
    except BaseException:
        if db is not None:
            try:
                db.close()
            except BaseException:
                pass  # Keep the initiating error and preserved scratch.
        raise

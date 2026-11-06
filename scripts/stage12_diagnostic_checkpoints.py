"""Bounded supplementary timing checkpoints; never campaign or sampling proof.

``record`` does no I/O. One independent daemon persists immutable chunks outside
the sampler/campaign-writer critical sections. Missing/truncated telemetry stays
explicit; the last flushed prefix survives a hard process exit. No query, body,
exception text, credentials or arbitrary paths belong in this format.
"""

from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import time


_TOKEN = re.compile(r"[A-Za-z0-9_]{1,80}\Z")
_NAME = re.compile(r"chunk([0-9]{6})\.json\Z")
_ZERO = "0" * 64
_CODES = frozenset(
    {
        "CHECKPOINT_LABEL_INVALID",
        "CHECKPOINT_ROW_INVALID",
        "CHECKPOINT_LIMIT_INVALID",
        "CHECKPOINT_ROOT_INVALID",
        "CHECKPOINT_CLOSED",
        "CHECKPOINT_WAIT_INVALID",
        "CHECKPOINT_WAIT_EXPIRED",
        "CHECKPOINT_ROOT_CHANGED",
        "CHECKPOINT_SHORT_WRITE",
        "CHECKPOINT_FILE_LIMIT",
        "CHECKPOINT_CLOCK_INVALID",
        "CHECKPOINT_BYTE_LIMIT",
        "CHECKPOINT_MEMBERSHIP_LIMIT",
        "CHECKPOINT_EXTRA_MEMBER",
        "CHECKPOINT_MEMBERSHIP_GAP",
        "CHECKPOINT_FILE_INVALID",
        "CHECKPOINT_FILE_CHANGED",
        "CHECKPOINT_CANONICAL_INVALID",
        "CHECKPOINT_BINDING_INVALID",
        "CHECKPOINT_RECORD_ORDER_INVALID",
        "CHECKPOINT_WATERMARK_INVALID",
    }
)
_FIELDS = (
    "phase",
    "stage_at_event_enter",
    "collector_enter_ns",
    "observed_ns",
    "event_enter_ns",
    "writer_start_ns",
    "writer_done_ns",
    "event_ack_ns",
    "collector_return_after_slot_release_ns",
)


class CheckpointError(RuntimeError):
    """A static diagnostic failure code, without unsafe exception contents."""


def _canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def _token(value):
    if value is not None and (
        not isinstance(value, str) or not _TOKEN.fullmatch(value)
    ):
        raise CheckpointError("CHECKPOINT_LABEL_INVALID")
    return value


def _integer(value):
    return type(value) is int and 0 <= value < 2**64


def _row(value):
    if not isinstance(value, (list, tuple)) or len(value) != 9:
        raise CheckpointError("CHECKPOINT_ROW_INVALID")
    _token(value[0])
    _token(value[1])
    if any(v is not None and not _integer(v) for v in value[2:]):
        raise CheckpointError("CHECKPOINT_ROW_INVALID")
    return tuple(value)


def _private(info, directory=False):
    return (
        stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    ) and (
        stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600)
        and info.st_uid == os.getuid()
        and (directory or info.st_nlink == 1)
    )


def _identity(info):
    # Reads can legitimately update atime, including under strict-atime mounts.
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


def _safe_failure(error, fallback):
    return (
        error.args[0]
        if (
            isinstance(error, CheckpointError)
            and len(error.args) == 1
            and isinstance(error.args[0], str)
            and error.args[0] in _CODES
        )
        else fallback
    )


def _names(root, maximum):
    names = []
    with os.scandir(root) as entries:
        for entry in entries:
            if len(names) >= maximum:
                raise CheckpointError("CHECKPOINT_MEMBERSHIP_LIMIT")
            if not _NAME.fullmatch(entry.name):
                raise CheckpointError("CHECKPOINT_EXTRA_MEMBER")
            names.append(entry.name)
    return sorted(names)


class Checkpoints:
    """One bounded ring and one diagnostic writer; budgets are charged first.

    Limits may be reduced, never exceed the reviewed 1,500 files / 32KiB each /
    4,096 rows / 128 rows per chunk. ``budget_charge`` must be thread-safe. An
    uncertain write is not refunded or retried. Flush waits use the real clock,
    independently of the observation clock, and do not hold the ring lock in I/O.
    """

    def __init__(
        self,
        root,
        clock_ns=time.monotonic_ns,
        budget_charge=lambda n: None,
        interval_seconds=5,
        max_files=1500,
        max_bytes=32768,
        ring_size=4096,
        chunk_records=128,
    ):
        for value, limit in (
            (max_files, 1500),
            (max_bytes, 32768),
            (ring_size, 4096),
            (chunk_records, 128),
        ):
            if type(value) is not int or not 0 < value <= limit:
                raise CheckpointError("CHECKPOINT_LIMIT_INVALID")
        if (
            max_bytes < 1024
            or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds)
            or interval_seconds <= 0
        ):
            raise CheckpointError("CHECKPOINT_LIMIT_INVALID")
        self.root = Path(root)
        self.root.mkdir(mode=0o700)
        info = self.root.lstat()
        if not _private(info, True):
            raise CheckpointError("CHECKPOINT_ROOT_INVALID")
        self._root_identity = (info.st_dev, info.st_ino)
        self._clock = clock_ns
        self._charge = budget_charge
        self._interval = interval_seconds
        self._max_files, self._max_bytes = max_files, max_bytes
        self._chunk_records = min(chunk_records, ring_size)
        self._rows = deque(maxlen=ring_size)
        self._condition = threading.Condition()
        self._observed = self._watermark = self._dropped = self._overflow = 0
        self._files = self._bytes = self._reserved_files = self._reserved_bytes = 0
        self._requested = self._serviced = 0
        self._phase = self._stage = None
        self._previous = _ZERO
        self._failure = None
        self._closing = self._closed = False
        self._thread = threading.Thread(
            target=self._run, name="stage12-diagnostic-checkpoints", daemon=True
        )
        self._thread.start()

    def record(self, row):
        """Copy an already observed safe row into memory; never persist here."""
        row = _row(row)
        with self._condition:
            self._check_locked()
            if self._closing or self._closed:
                raise CheckpointError("CHECKPOINT_CLOSED")
            self._observed += 1
            if len(self._rows) == self._rows.maxlen:
                self._overflow += 1
            self._rows.append((self._observed, row))

    def set_phase(self, phase, stage=None):
        phase, stage = _token(phase), _token(stage)
        with self._condition:
            self._check_locked()
            if self._closing or self._closed:
                raise CheckpointError("CHECKPOINT_CLOSED")
            self._phase, self._stage = phase, stage

    def _check_locked(self):
        if self._failure:
            raise CheckpointError(self._failure)

    def check(self):
        with self._condition:
            self._check_locked()

    def snapshot(self):
        with self._condition:
            return {
                "observed_rows": self._observed,
                "persisted_watermark": self._watermark,
                "dropped_unpersisted_rows": self._dropped,
                "ring_evictions": self._overflow,
                "persisted_files": self._files,
                "persisted_bytes": self._bytes,
                "reserved_files": self._reserved_files,
                "reserved_bytes": self._reserved_bytes,
                "buffered_rows": len(self._rows),
                "failure_code": self._failure,
                "closed": self._closed,
                "sampling_coverage_proof": False,
            }

    def _wait(self, ticket, timeout_seconds):
        if (
            not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise CheckpointError("CHECKPOINT_WAIT_INVALID")
        deadline = time.monotonic() + timeout_seconds
        while self._serviced < ticket:
            self._check_locked()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CheckpointError("CHECKPOINT_WAIT_EXPIRED")
            self._condition.wait(remaining)
        self._check_locked()

    def flush(self, timeout_seconds=5, *, timeout=None):
        """Boundary request and bounded wait; only call outside sampler/writer locks."""
        if timeout is not None:
            timeout_seconds = timeout
        with self._condition:
            self._check_locked()
            if self._closed:
                return self.snapshot()
            self._requested += 1
            ticket = self._requested
            self._condition.notify_all()
            self._wait(ticket, timeout_seconds)
        return self.snapshot()

    def close(self, timeout_seconds=5, *, timeout=None):
        if timeout is not None:
            timeout_seconds = timeout
        with self._condition:
            self._check_locked()
            if self._closed:
                return self.snapshot()
            self._closing = True
            self._requested += 1
            ticket = self._requested
            self._condition.notify_all()
            self._wait(ticket, timeout_seconds)
        return self.snapshot()

    def _root_check(self):
        info = self.root.lstat()
        if (
            not _private(info, True)
            or (info.st_dev, info.st_ino) != self._root_identity
        ):
            raise CheckpointError("CHECKPOINT_ROOT_CHANGED")

    def _persist(self, raw, index):
        self._root_check()
        self._charge(len(raw))  # No refund after this point, even if creation fails.
        filename = self.root / f"chunk{index:06d}.json"
        fd = os.open(
            filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(fd, raw[offset:])
                if written <= 0:
                    raise CheckpointError("CHECKPOINT_SHORT_WRITE")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)
        self._root_check()
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _run(self):
        next_due = time.monotonic() + self._interval
        try:
            while True:
                with self._condition:
                    while self._requested <= self._serviced and not self._closing:
                        remaining = next_due - time.monotonic()
                        if remaining <= 0:
                            break
                        self._condition.wait(remaining)
                    ticket, final = self._requested, self._closing
                    index, previous = self._files + 1, self._previous
                    if self._reserved_files >= self._max_files:
                        raise CheckpointError("CHECKPOINT_FILE_LIMIT")
                    total, watermark = self._observed, self._watermark
                    rows = [(n, row) for n, row in self._rows if n > watermark]
                    rows = rows[-self._chunk_records :]
                    payload = {
                        "schema": "stage12_supplementary_checkpoints_v1",
                        "units": "actual_monotonic_nanoseconds",
                        "fields": list(_FIELDS),
                        "sampling_coverage_proof": False,
                        "index": index,
                        "previous_sha256": previous,
                        "checkpoint_mono_ns": self._clock(),
                        "phase": self._phase,
                        "stage": self._stage,
                        "final": final,
                        "previous_watermark": watermark,
                        "watermark": total,
                        "ring_evictions": self._overflow,
                        "dropped_unpersisted_rows": self._dropped,
                        "records": [],
                    }
                    prior_dropped = self._dropped
                # Serialization and every disk operation are outside the short
                # ring lock. The immutable copied prefix is the source binding.
                if not _integer(payload["checkpoint_mono_ns"]):
                    raise CheckpointError("CHECKPOINT_CLOCK_INVALID")
                while True:
                    payload["records"] = [[n, list(row)] for n, row in rows]
                    payload["dropped_unpersisted_rows"] = (
                        prior_dropped + total - watermark - len(rows)
                    )
                    raw = _canonical(payload)
                    if len(raw) <= self._max_bytes:
                        break
                    if not rows:
                        raise CheckpointError("CHECKPOINT_BYTE_LIMIT")
                    rows = rows[1:]
                with self._condition:
                    self._reserved_files += 1
                    self._reserved_bytes += len(raw)
                self._persist(raw, index)
                with self._condition:
                    self._files, self._bytes = index, self._bytes + len(raw)
                    self._previous = hashlib.sha256(raw).hexdigest()
                    self._watermark = total
                    self._dropped = payload["dropped_unpersisted_rows"]
                    self._serviced = ticket
                    self._closed = final
                    self._condition.notify_all()
                    if final:
                        return
                next_due = time.monotonic() + self._interval
        except BaseException as error:
            with self._condition:
                self._failure = _safe_failure(error, "CHECKPOINT_PERSISTENCE_FAILED")
                self._condition.notify_all()


def read_prefix(root, *, max_files=1500, max_bytes=32768):
    """Validate the entire bounded membership and return only a verified prefix.

    A partial/invalid tail is never skipped: ``incomplete`` and a static reason
    identify it. Even a clean final marker is supplementary telemetry, never
    proof of required campaign sampling. Returned memory is at most one chunk.
    """
    root = Path(root)
    result = {
        "verified_files": 0,
        "verified_rows": 0,
        "last_watermark": 0,
        "dropped_unpersisted_rows": 0,
        "last_sha256": _ZERO,
        "incomplete": True,
        "reason": "NO_FINAL_CHECKPOINT",
        "sampling_coverage_proof": False,
        "last_payload": None,
    }
    try:
        if (
            type(max_files) is not int
            or not 0 < max_files <= 1500
            or type(max_bytes) is not int
            or not 0 < max_bytes <= 32768
        ):
            raise CheckpointError("CHECKPOINT_LIMIT_INVALID")
        info = root.lstat()
        if not _private(info, True):
            raise CheckpointError("CHECKPOINT_ROOT_INVALID")
        identity = (info.st_dev, info.st_ino)
        names = _names(root, max_files)
        previous, watermark, dropped, evictions, observed_clock = _ZERO, 0, 0, 0, 0
        bindings = []
        for index, name in enumerate(names, 1):
            if name != f"chunk{index:06d}.json":
                raise CheckpointError("CHECKPOINT_MEMBERSHIP_GAP")
            fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                before = os.fstat(fd)
                if not _private(before) or before.st_size > max_bytes:
                    raise CheckpointError("CHECKPOINT_FILE_INVALID")
                raw = bytearray()
                while len(raw) <= max_bytes:
                    part = os.read(fd, max_bytes + 1 - len(raw))
                    if not part:
                        break
                    raw.extend(part)
                after = os.fstat(fd)
                if _identity(before) != _identity(after) or len(raw) > max_bytes:
                    raise CheckpointError("CHECKPOINT_FILE_CHANGED")
                bindings.append((name, _identity(after)))
            finally:
                os.close(fd)
            payload = json.loads(raw)
            if _canonical(payload) != raw:
                raise CheckpointError("CHECKPOINT_CANONICAL_INVALID")
            expected = {
                "schema",
                "units",
                "fields",
                "sampling_coverage_proof",
                "index",
                "previous_sha256",
                "checkpoint_mono_ns",
                "phase",
                "stage",
                "final",
                "previous_watermark",
                "watermark",
                "ring_evictions",
                "dropped_unpersisted_rows",
                "records",
            }
            if (
                set(payload) != expected
                or payload["schema"] != "stage12_supplementary_checkpoints_v1"
                or payload["units"] != "actual_monotonic_nanoseconds"
                or payload["fields"] != list(_FIELDS)
                or payload["sampling_coverage_proof"] is not False
                or payload["index"] != index
                or payload["previous_sha256"] != previous
                or payload["previous_watermark"] != watermark
                or not all(
                    _integer(payload[key])
                    for key in (
                        "checkpoint_mono_ns",
                        "watermark",
                        "previous_watermark",
                        "ring_evictions",
                        "dropped_unpersisted_rows",
                        "index",
                    )
                )
                or payload["watermark"] < watermark
                or type(payload["final"]) is not bool
                or payload["ring_evictions"] < evictions
                or payload["checkpoint_mono_ns"] < observed_clock
                or not isinstance(payload["records"], list)
                or len(payload["records"]) > 128
                or (payload["final"] and index != len(names))
            ):
                raise CheckpointError("CHECKPOINT_BINDING_INVALID")
            _token(payload["phase"])
            _token(payload["stage"])
            ordinal = payload["watermark"] - len(payload["records"]) + 1
            for pair in payload["records"]:
                if (
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or not _integer(pair[0])
                    or pair[0] != ordinal
                    or pair[0] <= watermark
                ):
                    raise CheckpointError("CHECKPOINT_RECORD_ORDER_INVALID")
                _row(pair[1])
                ordinal += 1
            expected_dropped = (
                dropped + payload["watermark"] - watermark - len(payload["records"])
            )
            if payload["dropped_unpersisted_rows"] != expected_dropped:
                raise CheckpointError("CHECKPOINT_WATERMARK_INVALID")
            previous = hashlib.sha256(raw).hexdigest()
            watermark, dropped = (
                payload["watermark"],
                payload["dropped_unpersisted_rows"],
            )
            evictions, observed_clock = (
                payload["ring_evictions"],
                payload["checkpoint_mono_ns"],
            )
            result.update(
                verified_files=index,
                verified_rows=result["verified_rows"] + len(payload["records"]),
                last_watermark=watermark,
                dropped_unpersisted_rows=dropped,
                last_sha256=previous,
                last_payload=payload,
            )
        current = root.lstat()
        if (
            (current.st_dev, current.st_ino) != identity
            or not _private(current, True)
            or _names(root, max_files) != names
        ):
            raise CheckpointError("CHECKPOINT_ROOT_CHANGED")
        if any(
            _identity((root / name).lstat()) != binding for name, binding in bindings
        ):
            raise CheckpointError("CHECKPOINT_FILE_CHANGED")
        if result["last_payload"] and result["last_payload"]["final"]:
            result.update(
                incomplete=bool(dropped),
                reason="TELEMETRY_TRUNCATED" if dropped else None,
            )
    except BaseException as error:
        result.update(
            incomplete=True, reason=_safe_failure(error, "CHECKPOINT_PREFIX_INVALID")
        )
    return result

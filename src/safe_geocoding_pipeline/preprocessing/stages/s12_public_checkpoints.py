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


PUBLIC_FIELDS = (
    "phase_id",
    "cause",
    "outcome",
    "segment_id",
    "event_seq",
    "event_mono_ns",
    "collector_enter_ns",
    "sampler_slot_acquired_ns",
    "free_query_start_ns",
    "free_query_end_ns",
    "safety_wait_start_ns",
    "safety_acquired_ns",
    "observed_ns",
    "safety_snapshot_complete_ns",
    "journal_enter_ns",
    "enqueue_ns",
    "writer_entry_ns",
    "writer_action_enter_ns",
    "event_header_ns",
    "append_complete_ns",
    "writer_action_return_ns",
    "post_action_complete_ns",
    "future_completion_ns",
    "caller_ack_ns",
    "journal_ack_ns",
    "sampler_slot_released_ns",
    "collector_return_ns",
)
PUBLIC_SCHEMA = "stage12_public_path_timing_v1"
AP_SCHEMA = "stage12_public_path_timing_v2"
WF_SCHEMA = "stage12_public_path_timing_v3"
RA_SCHEMA = "stage12_public_path_timing_ra_g1_v1"


def _ap_row(value):
    from .s12_public_bounded import pack_timing, unpack_timing

    try:
        return unpack_timing(pack_timing(value))
    except BaseException:
        raise CheckpointError("CHECKPOINT_ROW_INVALID") from None


def _public_row(value):
    if not isinstance(value, (list, tuple)) or len(value) != len(PUBLIC_FIELDS):
        raise CheckpointError("CHECKPOINT_ROW_INVALID")
    if (
        not _integer(value[0])
        or value[0] == 0
        or value[1] not in ("PERIODIC", "START_RESERVE")
        or value[2] not in ("COMPLETE", "FAILED", "CANCELLED", "UNCERTAIN")
        or any(v is not None and not _integer(v) for v in value[3:])
        or (value[1] == "START_RESERVE" and value[25] is not None)
    ):
        raise CheckpointError("CHECKPOINT_ROW_INVALID")
    return tuple(value)


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
        row_schema=None,
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
        if row_schema not in (None, PUBLIC_SCHEMA, AP_SCHEMA):
            raise CheckpointError("CHECKPOINT_ROW_INVALID")
        self._ap = row_schema == AP_SCHEMA
        self._public = row_schema == PUBLIC_SCHEMA
        self._row = _ap_row if self._ap else _public_row if self._public else _row
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
        if self._ap:
            from .s12_public_bounded import TimingRing, pack_timing

            self._rows = TimingRing(ring_size)
            self._row = pack_timing
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
        try:
            row = self._row(row)
        except BaseException:
            if self._ap:
                raise CheckpointError("CHECKPOINT_ROW_INVALID") from None
            raise
        with self._condition:
            self._check_locked()
            if self._closing or self._closed:
                raise CheckpointError("CHECKPOINT_CLOSED")
            if self._ap and self._observed == 2**64 - 1:
                raise CheckpointError("CHECKPOINT_LIMIT_INVALID")
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
                "persistence_uncertain": self._reserved_files > self._files,
                "final_coverage_complete": self._closed and not self._dropped,
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
            # AP uses at most three immutable views over bounded arenas. No
            # concatenation or bytes slice duplicates the selected document.
            parts = raw.parts if self._ap else (raw,)
            for part in parts:
                view = memoryview(part)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise CheckpointError("CHECKPOINT_SHORT_WRITE")
                    view = view[written:]
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
        if self._ap:
            return self._run_ap()
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
                    rows = (
                        rows[: self._chunk_records]
                        if self._ap
                        else rows[-self._chunk_records :]
                    )
                    if self._ap:
                        total = rows[-1][0] if rows else watermark
                        final = final and total == self._observed
                    payload = {
                        "schema": (
                            AP_SCHEMA
                            if self._ap
                            else PUBLIC_SCHEMA
                            if self._public
                            else "stage12_supplementary_checkpoints_v1"
                        ),
                        "units": (
                            "actual_monotonic_nanoseconds_lossless_offsets"
                            if self._public
                            else "actual_monotonic_nanoseconds"
                        ),
                        "fields": []
                        if self._ap
                        else list(PUBLIC_FIELDS if self._public else _FIELDS),
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
                    if self._ap:
                        payload["records"] = [[n, row] for n, row in rows]
                    elif self._public:
                        base = min(
                            (v for _, row in rows for v in row[5:] if v is not None),
                            default=0,
                        )
                        payload["timestamp_base_ns"] = base
                        payload["records"] = [
                            [
                                n,
                                list(row[:5])
                                + [
                                    v - base if v is not None else None for v in row[5:]
                                ],
                            ]
                            for n, row in rows
                        ]
                    else:
                        payload["records"] = [[n, list(row)] for n, row in rows]
                    payload["dropped_unpersisted_rows"] = (
                        prior_dropped + total - watermark - len(rows)
                    )
                    raw = _canonical(payload)
                    if len(raw) <= self._max_bytes:
                        break
                    if not rows:
                        raise CheckpointError("CHECKPOINT_BYTE_LIMIT")
                    if self._ap:
                        rows = rows[:-1]
                        if not rows:
                            raise CheckpointError("CHECKPOINT_BYTE_LIMIT")
                        total = rows[-1][0] if rows else watermark
                        payload["watermark"] = total
                        payload["final"] = False
                        final = False
                    else:
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
                    self._serviced = (
                        ticket
                        if (not self._ap or total == self._observed)
                        else self._serviced
                    )
                    self._closed = final
                    self._condition.notify_all()
                    if final:
                        return
                next_due = time.monotonic() + self._interval
        except BaseException as error:
            with self._condition:
                self._failure = _safe_failure(error, "CHECKPOINT_PERSISTENCE_FAILED")
                self._condition.notify_all()

    def _run_ap(self):
        from .s12_public_bounded import Canonical, Document, envelope, unpack_timing

        next_due = time.monotonic() + self._interval
        try:
            while True:
                with self._condition:
                    while (
                        self._requested <= self._serviced
                        and not self._closing
                        and self._observed <= self._watermark
                    ):
                        remaining = next_due - time.monotonic()
                        if remaining <= 0:
                            break
                        self._condition.wait(remaining)
                    ticket, closing = self._requested, self._closing
                    index, previous = self._files + 1, self._previous
                    if self._reserved_files >= self._max_files:
                        raise CheckpointError("CHECKPOINT_FILE_LIMIT")
                    end, watermark = self._observed, self._watermark
                    first = max(watermark + 1, end - len(self._rows) + 1)
                    packed = self._rows.get(first) if first <= end else None
                    payload = dict(
                        schema=AP_SCHEMA,
                        units="actual_monotonic_nanoseconds",
                        fields=[],
                        sampling_coverage_proof=False,
                        index=index,
                        previous_sha256=previous,
                        checkpoint_mono_ns=self._clock(),
                        phase=self._phase,
                        stage=self._stage,
                        final=False,
                        previous_watermark=watermark,
                        watermark=watermark,
                        ring_evictions=self._overflow,
                        dropped_unpersisted_rows=self._dropped,
                        records=None,
                    )
                    prior_dropped = self._dropped
                if not _integer(payload["checkpoint_mono_ns"]):
                    raise CheckpointError("CHECKPOINT_CLOCK_INVALID")
                records = Canonical(self._max_bytes)
                records.put(b"[")
                count, total = 0, watermark
                for ordinal in range(first, min(end + 1, first + self._chunk_records)):
                    if ordinal != first:
                        with self._condition:
                            packed = self._rows.get(ordinal)
                    if packed is None:
                        break  # Concurrent eviction: preserve this exact prefix.
                    row = unpack_timing(packed)
                    pair = (ordinal, row)
                    size = Canonical(self._max_bytes, count_only=True)
                    size.value(pair)
                    proposed = dict(
                        payload,
                        watermark=ordinal,
                        final=closing and ordinal == end,
                        dropped_unpersisted_rows=prior_dropped
                        + ordinal
                        - watermark
                        - count
                        - 1,
                    )
                    header, _ = envelope(proposed, count_only=True)
                    # Count escaped canonical bytes BEFORE writing the pair.
                    if (
                        records.pos + bool(count) + size.pos + 1 + header.pos
                        > self._max_bytes
                    ):
                        if not count:
                            raise CheckpointError("CHECKPOINT_BYTE_LIMIT")
                        break
                    if count:
                        records.put(b",")
                    records.value(pair)
                    count, total, payload = count + 1, ordinal, proposed
                    del row, pair, packed
                records.put(b"]")
                payload["final"] = closing and total == end
                document = Document(payload, records)
                if len(document) > self._max_bytes:
                    raise CheckpointError("CHECKPOINT_BYTE_LIMIT")
                with self._condition:
                    self._reserved_files += 1
                    self._reserved_bytes += len(document)
                self._persist(document, index)
                with self._condition:
                    self._files, self._bytes = index, self._bytes + len(document)
                    self._previous = document.digest()
                    self._watermark = total
                    self._dropped = payload["dropped_unpersisted_rows"]
                    if total == self._observed:
                        self._serviced = ticket
                    self._closed = payload["final"]
                    self._condition.notify_all()
                    if self._closed:
                        return
                # Release previous arenas before allocating the next document.
                del document, records, payload
                next_due = time.monotonic() + self._interval
        except BaseException as error:
            with self._condition:
                self._failure = _safe_failure(error, "CHECKPOINT_PERSISTENCE_FAILED")
                self._condition.notify_all()


def read_prefix(
    root,
    *,
    max_files=1500,
    max_bytes=32768,
    record_consumer=None,
    expected_binding=None,
    expected_snapshot=None,
    timing_schema=None,
):
    """Validate the entire bounded membership and return only a verified prefix.

    A partial/invalid tail is never skipped: ``incomplete`` and a static reason
    identify it. Even a clean final marker is supplementary telemetry, never
    proof of required campaign sampling. Returned memory is at most one chunk.
    Public records use lossless per-chunk timestamp offsets on disk; an optional
    record_consumer(ordinal, row) receives exact absolute timestamps after each
    chunk validates. last_payload retains the on-disk wire representation.
    WF-AP2 fixed rows retain only their closed header in last_payload. Explicit
    expected bindings select that family, and its completion verdict also needs
    the matching successful original task checkpoint snapshot.
    """
    root = Path(root)
    # Dispatch by a new wire family only. Historical JSON parsers and verdicts
    # retain their original implementation; mixed membership fails closed.
    try:
        with os.scandir(root) as entries:
            use_compact = (
                expected_binding is not None
                or expected_snapshot is not None
                or any(entry.name.endswith(".bin") for entry in entries)
            )
    except OSError:
        use_compact = expected_binding is not None or expected_snapshot is not None
    if use_compact:
        from . import s12_wf_ap2_timing as compact

        return compact.read_prefix(
            root,
            max_files=max_files,
            max_bytes=max_bytes,
            record_consumer=record_consumer,
            expected_binding=expected_binding,
            expected_snapshot=expected_snapshot,
            timing_schema=(
                timing_schema
                or (
                    expected_snapshot.get("schema")
                    if type(expected_snapshot) is dict
                    else None
                )
                or WF_SCHEMA
            ),
        )
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
        chain_schema = None
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
            if payload.get("schema") == AP_SCHEMA:
                from .s12_public_bounded import EncodingLimit, canonical_match

                try:
                    canonical_match(payload, raw)
                except EncodingLimit:
                    raise CheckpointError("CHECKPOINT_CANONICAL_INVALID") from None
                canonical_bytes = raw
            else:
                canonical_bytes = _canonical(payload)
            if canonical_bytes != raw:
                raise CheckpointError("CHECKPOINT_CANONICAL_INVALID")
            del canonical_bytes
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
            public = payload.get("schema") == PUBLIC_SCHEMA
            ap = payload.get("schema") == AP_SCHEMA
            if public:
                expected.add("timestamp_base_ns")
            if (
                set(payload) != expected
                or payload["schema"]
                not in (
                    "stage12_supplementary_checkpoints_v1",
                    PUBLIC_SCHEMA,
                    AP_SCHEMA,
                )
                or (chain_schema is not None and payload["schema"] != chain_schema)
                or payload["units"]
                != (
                    "actual_monotonic_nanoseconds_lossless_offsets"
                    if public
                    else "actual_monotonic_nanoseconds"
                )
                or (public and not _integer(payload["timestamp_base_ns"]))
                or payload["fields"]
                != (
                    []
                    if ap
                    else list(
                        PUBLIC_FIELDS if payload["schema"] == PUBLIC_SCHEMA else _FIELDS
                    )
                )
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
            chain_schema = payload["schema"]
            _token(payload["phase"])
            _token(payload["stage"])
            decoded_records = []
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
                if ap:
                    decoded = _ap_row(pair[1])
                elif public:
                    wire = _public_row(pair[1])
                    decoded = _public_row(
                        list(wire[:5])
                        + [
                            v + payload["timestamp_base_ns"] if v is not None else None
                            for v in wire[5:]
                        ]
                    )
                else:
                    decoded = _row(pair[1])
                if not ap:
                    decoded_records.append((pair[0], decoded))
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
            if record_consumer is not None:
                if ap:
                    for number, wire in payload["records"]:
                        record_consumer(number, _ap_row(wire))
                else:
                    for number, row in decoded_records:
                        record_consumer(number, tuple(row))
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

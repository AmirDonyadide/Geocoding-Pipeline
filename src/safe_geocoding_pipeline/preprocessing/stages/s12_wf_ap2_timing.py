"""WF-AP2 T3 supplementary wire, finite cuts and fresh bounded reopening.

One logical 4096-row arena and one writer; this is no native allocation claim.
Timing bytes do not prove fsync acknowledgement. A successful opener additionally
requires the original task's successful checkpoint disposition, matched exactly
to the freshly read source set. All evidence remains supplementary.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import threading
import time

from . import s12_public_checkpoints as cp
from . import s12_public_bounded as bounded
from . import s12_wf_ap2_scratch as scratch


SCHEMA = "stage12_public_path_timing_v3"
POLICY_VERSION = "stage12_public_sampling_policy_v2"
POLICY_VERSIONS = (POLICY_VERSION, "stage12_development_sampling_policy_b2_ap_v1")
MAGIC = b"S12T3\x00\x01\n"
HEADER_BYTES, ROW_BYTES, CHUNK_ROWS = 4096, 512, 56
MAX_BYTES, MAX_FILES, TIMER_NS = 32768, 1500, 5_000_000_000
_NAME = re.compile(r"chunk([0-9]{6})\.bin\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_BINDING = frozenset(("policy_sha256", "source_sha256", "task_sha256"))
_HEADER = frozenset(
    "schema policy_version policy_sha256 source_sha256 task_sha256 index "
    "previous_sha256 checkpoint_mono_ns phase_id phase_selected_ms "
    "phase_open_mono_ns phase_end_mono_ns phase_deadline_ns cumulative_deadline_ns cut_id cut_kind cut_requested_mono_ns "
    "cut_high_watermark cut_complete previous_watermark watermark first_row_ordinal "
    "last_row_ordinal row_count ring_evictions dropped_unpersisted_rows "
    "uncertainty_count final terminal_status sampling_coverage_proof".split()
)
_KINDS = frozenset(("PHASE_OPEN", "TIMER", "PHASE_CLOSE", "TASK_CLOSE"))
_ERRORS = frozenset(
    "CHECKPOINT_CUT_INVALID CHECKPOINT_PHASE_INVALID CHECKPOINT_READBACK_FAILED "
    "CHECKPOINT_ACK_UNVERIFIED CHECKPOINT_PERSISTENCE_FAILED".split()
)


def _error(code):
    raise cp.CheckpointError(code)


def _require(condition, code="CHECKPOINT_BINDING_INVALID"):
    if not condition:
        _error(code)


def _failure(error):
    if (
        isinstance(error, cp.CheckpointError)
        and len(error.args) == 1
        and isinstance(error.args[0], str)
    ):
        if error.args[0] in cp._CODES | _ERRORS:
            return error.args[0]
    return "CHECKPOINT_PERSISTENCE_FAILED"


def validate_binding(value):
    _require(type(value) is dict and set(value) == _BINDING)
    _require(
        all(
            type(v) is str and _HASH.fullmatch(v) and v != cp._ZERO
            for v in value.values()
        )
    )
    return dict(value)


def validate_policy_version(value):
    _require(type(value) is str and value in POLICY_VERSIONS)
    return value


def _path_identity(root):
    """Finite ancestor topology; no symlink component can redirect originals."""
    current = Path(os.path.abspath(root))
    result = []
    while True:
        _require(len(result) < 64, "CHECKPOINT_ROOT_INVALID")
        info = current.lstat()
        _require(stat.S_ISDIR(info.st_mode), "CHECKPOINT_ROOT_INVALID")
        result.append((info.st_dev, info.st_ino))
        if current.parent == current:
            return tuple(result)
        current = current.parent


def encode_row(row):
    """Use the original closed tagged representation without value substitution."""
    try:
        return bounded.pack_timing(row)
    except BaseException:
        _error("CHECKPOINT_ROW_INVALID")


def decode_row(raw):
    """Repacking rejects unknown tags, masks, null bytes and reserved padding."""
    try:
        _require(len(raw) == ROW_BYTES, "CHECKPOINT_ROW_INVALID")
        row = bounded.unpack_timing(raw)
        _require(bounded.pack_timing(row) == raw, "CHECKPOINT_ROW_INVALID")
        return row
    except BaseException:
        _error("CHECKPOINT_ROW_INVALID")


def encode_header(header, block=None):
    encoded = bounded.canonical(header, HEADER_BYTES - 12)
    if block is None:
        block = bytearray(HEADER_BYTES)
    _require(len(block) == HEADER_BYTES, "CHECKPOINT_BYTE_LIMIT")
    block[:8] = MAGIC
    struct.pack_into("<I", block, 8, len(encoded))
    block[12 : 12 + len(encoded)] = encoded
    # Also canonical when a caller supplies a reused target. A byte loop avoids
    # allocating another header-sized zero/padding representation.
    for index in range(12 + len(encoded), HEADER_BYTES):
        block[index] = 0
    return block


def decode_header(block):
    try:
        _require(len(block) == HEADER_BYTES and block[:8] == MAGIC)
        length = struct.unpack_from("<I", block, 8)[0]
        _require(0 < length <= HEADER_BYTES - 12)
        raw = bytes(block[12 : 12 + length])
        header = json.loads(raw)
        _require(type(header) is dict and set(header) == _HEADER)
        bounded.canonical_match(header, raw)
        _require(not any(block[12 + length :]), "CHECKPOINT_CANONICAL_INVALID")
        _require(header["schema"] == SCHEMA)
        validate_policy_version(header["policy_version"])
        validate_binding({k: header[k] for k in _BINDING})
        integers = (
            _HEADER
            - _BINDING
            - {
                "schema",
                "policy_version",
                "previous_sha256",
                "phase_id",
                "phase_selected_ms",
                "phase_open_mono_ns",
                "phase_end_mono_ns",
                "phase_deadline_ns",
                "cut_kind",
                "cut_complete",
                "final",
                "terminal_status",
                "sampling_coverage_proof",
            }
        )
        _require(all(cp._integer(header[k]) for k in integers))
        _require(
            type(header["previous_sha256"]) is str
            and _HASH.fullmatch(header["previous_sha256"])
        )
        _require(header["cut_kind"] in _KINDS)
        _require(header["cut_requested_mono_ns"] <= header["checkpoint_mono_ns"])
        _require(type(header["cut_complete"]) is bool and type(header["final"]) is bool)
        _require(header["sampling_coverage_proof"] is False)
        _require(0 < header["index"] <= MAX_FILES and 0 < header["cut_id"])
        _require(header["row_count"] <= CHUNK_ROWS)
        if header["phase_id"] is None:
            _require(header["cut_kind"] == "TASK_CLOSE")
            _require(
                all(
                    header[k] is None
                    for k in (
                        "phase_selected_ms",
                        "phase_open_mono_ns",
                        "phase_end_mono_ns",
                        "phase_deadline_ns",
                    )
                )
            )
        else:
            _require(header["cut_kind"] != "TASK_CLOSE")
            _require(
                all(
                    cp._integer(header[k])
                    for k in (
                        "phase_id",
                        "phase_selected_ms",
                        "phase_open_mono_ns",
                        "phase_end_mono_ns",
                        "phase_deadline_ns",
                    )
                )
            )
            _require(1 <= header["phase_id"] <= 32 and header["phase_selected_ms"] > 0)
            _require(
                header["phase_open_mono_ns"]
                <= header["phase_end_mono_ns"]
                <= header["phase_deadline_ns"]
                <= header["cumulative_deadline_ns"]
            )
            _require(
                header["phase_end_mono_ns"]
                == min(
                    header["phase_open_mono_ns"]
                    + header["phase_selected_ms"] * 1_000_000,
                    header["phase_deadline_ns"],
                    header["cumulative_deadline_ns"],
                )
            )
        _require(
            header["previous_watermark"]
            <= header["watermark"]
            <= header["cut_high_watermark"]
        )
        _require(
            header["cut_complete"]
            == (header["watermark"] == header["cut_high_watermark"])
        )
        count = header["row_count"]
        if count:
            _require(header["previous_watermark"] < header["first_row_ordinal"])
            _require(
                header["first_row_ordinal"] + count - 1
                == header["last_row_ordinal"]
                == header["watermark"]
            )
        else:
            _require(header["first_row_ordinal"] == header["last_row_ordinal"] == 0)
            _require(header["cut_complete"])
        _require(count == CHUNK_ROWS or header["cut_complete"])
        _require(
            header["final"]
            == (header["cut_kind"] == "TASK_CLOSE" and header["cut_complete"])
        )
        expected_status = (
            (
                "FINAL_INCOMPLETE"
                if header["dropped_unpersisted_rows"]
                or header["uncertainty_count"]
                or header["ring_evictions"]
                else "FINAL_COMPLETE"
            )
            if header["final"]
            else "OPEN"
        )
        _require(header["terminal_status"] == expected_status)
        return header
    except BaseException:
        _error("CHECKPOINT_CANONICAL_INVALID")


class Checkpoints:
    """Exactly one ring, one writer and finite, nonextending high-water cuts.

    The selected cut budget is charged before the cut is queued. Each attempted
    exclusive file is fully charged before I/O; no refunds or persistence retry.
    Only explicit phase boundaries, eligible timers and task close create cuts.
    """

    def __init__(
        self,
        root,
        *,
        timing_binding,
        phase_windows,
        cumulative_deadline_ns,
        timing_policy_version=POLICY_VERSION,
        clock_ns=time.monotonic_ns,
        budget_charge=lambda n: None,
        max_files=MAX_FILES,
        max_bytes=MAX_BYTES,
        ring_size=4096,
        chunk_records=CHUNK_ROWS,
        interval_seconds=5,
    ):
        self.binding = validate_binding(timing_binding)
        self.policy_version = validate_policy_version(timing_policy_version)
        _require(cp._integer(cumulative_deadline_ns) and cumulative_deadline_ns > 0)
        _require(type(phase_windows) is list and 1 <= len(phase_windows) <= 32)
        self.windows = {}
        for index, item in enumerate(phase_windows, 1):
            _require(
                type(item) is dict and set(item) == {"phase_id", "selected_phase_ms"}
            )
            _require(type(item["phase_id"]) is int and item["phase_id"] == index)
            _require(
                cp._integer(item["selected_phase_ms"]) and item["selected_phase_ms"] > 0
            )
            self.windows[index] = item["selected_phase_ms"]
        _require(
            type(max_files) is int and 1 <= max_files <= MAX_FILES,
            "CHECKPOINT_LIMIT_INVALID",
        )
        _require(
            type(max_bytes) is int
            and max_bytes == MAX_BYTES
            and type(chunk_records) is int
            and chunk_records == CHUNK_ROWS
            and interval_seconds == 5,
            "CHECKPOINT_LIMIT_INVALID",
        )
        _require(
            type(ring_size) is int and 1 <= ring_size <= 4096,
            "CHECKPOINT_LIMIT_INVALID",
        )
        _require(
            callable(clock_ns) and callable(budget_charge), "CHECKPOINT_LIMIT_INVALID"
        )
        self.root = Path(root)
        self.root.mkdir(mode=0o700)
        info = self.root.lstat()
        _require(cp._private(info, True), "CHECKPOINT_ROOT_INVALID")
        self._root_identity = (info.st_dev, info.st_ino)
        self._path_identity = _path_identity(self.root)
        self._condition = threading.Condition()
        self._rows = bounded.TimingRing(ring_size)
        self._clock, self._charge = clock_ns, budget_charge
        self._deadline, self._max_files = cumulative_deadline_ns, max_files
        self._observed = self._watermark = self._dropped = self._overflow = 0
        self._files = self._bytes = self._reserved_files = self._reserved_bytes = 0
        self._requested = self._serviced = self._uncertainty = 0
        self._cut_limit = (
            2 * len(self.windows)
            + 1
            + sum((ms + 4999) // 5000 for ms in self.windows.values())
        )
        self._pending = self._active_phase = self._failure = None
        self._phase_open = self._phase_end = self._next_due = None
        self._phase_deadline = None
        self._timer_count = self._last_phase = 0
        self._closing = self._closed = False
        self._previous = cp._ZERO
        self._last_clock = 0
        self._thread = threading.Thread(
            target=self._run, name="stage12-wf-ap2-checkpoints", daemon=True
        )
        self._thread.start()

    def _now(self):
        value = self._clock()
        if not cp._integer(value) or value < self._last_clock:
            self._failure = "CHECKPOINT_CLOCK_INVALID"
            _error(self._failure)
        self._last_clock = value
        return value

    def _check_locked(self):
        if self._failure:
            _error(self._failure)

    def check(self):
        with self._condition:
            self._check_locked()

    def record(self, row):
        raw = encode_row(row)
        phase = (
            row["legacy_row"][0] if row["row_kind"] == "HARD_SYNC" else row["phase_id"]
        )
        with self._condition:
            self._check_locked()
            _require(not self._closing and not self._closed, "CHECKPOINT_CLOSED")
            _require(self._observed < bounded.UINT64, "CHECKPOINT_LIMIT_INVALID")
            # Preserve late rows, while making unresolved/off-window work fail
            # coverage. It cannot enable a timer or extend an earlier cut.
            if phase != self._active_phase or self._now() >= self._phase_end:
                self._uncertainty += 1
            self._observed += 1
            if self._observed - self._rows.maxlen > self._watermark:
                self._overflow += 1
            self._rows.append((self._observed, raw))

    def _request_locked(self, kind, phase, opened, end, selected):
        self._check_locked()
        _require(
            self._pending is None and self._requested < self._cut_limit,
            "CHECKPOINT_CUT_INVALID",
        )
        requested = opened if kind == "PHASE_OPEN" else self._now()
        if kind == "TIMER" and (requested >= end or requested >= self._deadline):
            return None
        if kind == "PHASE_CLOSE" and requested > end:
            self._uncertainty += 1
        self._requested += 1  # Selected cut precharge; never refunded.
        self._pending = dict(
            cut_id=self._requested,
            cut_kind=kind,
            cut_high_watermark=self._observed,
            cut_requested_mono_ns=requested,
            phase_id=phase,
            phase_selected_ms=selected,
            phase_open_mono_ns=opened,
            phase_end_mono_ns=end,
            phase_deadline_ns=self._phase_deadline if phase is not None else None,
        )
        self._condition.notify_all()
        return self._requested

    def _wait_locked(self, ticket, timeout_seconds):
        _require(
            type(timeout_seconds) in (int, float)
            and math.isfinite(timeout_seconds)
            and timeout_seconds > 0,
            "CHECKPOINT_WAIT_INVALID",
        )
        # A boundary drain spends the existing cumulative deadline; it cannot
        # manufacture a new five-second allowance at task expiry.
        available = max(0, self._deadline - self._now()) / 1e9
        deadline = time.monotonic() + min(timeout_seconds, available)
        while self._serviced < ticket:
            self._check_locked()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._uncertainty += 1
                self._failure = "CHECKPOINT_WAIT_EXPIRED"
                self._condition.notify_all()
                _error(self._failure)
            self._condition.wait(remaining)
        self._check_locked()

    def phase_open(self, phase_id, *, phase_deadline_ns=None, timeout_seconds=5):
        with self._condition:
            self._check_locked()
            _require(
                type(phase_id) is int
                and phase_id == self._last_phase + 1
                and phase_id in self.windows,
                "CHECKPOINT_PHASE_INVALID",
            )
            _require(
                self._active_phase is None and not self._closing,
                "CHECKPOINT_PHASE_INVALID",
            )
            now, ms = self._now(), self.windows[phase_id]
            _require(now < self._deadline, "CHECKPOINT_PHASE_INVALID")
            if phase_deadline_ns is None:
                phase_deadline_ns = self._deadline
            _require(
                cp._integer(phase_deadline_ns)
                and now < phase_deadline_ns <= self._deadline,
                "CHECKPOINT_PHASE_INVALID",
            )
            self._active_phase = self._last_phase = phase_id
            self._phase_open = now
            self._phase_deadline = phase_deadline_ns
            self._phase_end = min(
                self._deadline, now + ms * 1_000_000, phase_deadline_ns
            )
            self._next_due, self._timer_count = now + TIMER_NS, 0
            ticket = self._request_locked(
                "PHASE_OPEN", phase_id, now, self._phase_end, ms
            )
            self._wait_locked(ticket, timeout_seconds)
        return self.snapshot()

    def phase_close(self, phase_id, *, quiescent=True, timeout_seconds=5):
        with self._condition:
            self._check_locked()
            _require(
                type(phase_id) is int and phase_id == self._active_phase,
                "CHECKPOINT_PHASE_INVALID",
            )
            _require(type(quiescent) is bool, "CHECKPOINT_PHASE_INVALID")
            opened, end = self._phase_open, self._phase_end
            self._active_phase = self._next_due = None  # Timers off BEFORE drain.
            if not quiescent or self._now() > end:
                self._uncertainty += 1
            ticket = self._request_locked(
                "PHASE_CLOSE", phase_id, opened, end, self.windows[phase_id]
            )
            self._wait_locked(ticket, timeout_seconds)
        return self.snapshot()

    def flush(self, *args, **kwargs):
        _error("CHECKPOINT_CUT_INVALID")  # No extra, unselected cut API.

    def close(self, timeout_seconds=5, *, timeout=None):
        if timeout is not None:
            timeout_seconds = timeout
        with self._condition:
            self._check_locked()
            if self._closed:
                return self.snapshot()
            _require(not self._closing, "CHECKPOINT_CLOSED")
            if self._active_phase is not None:
                self._uncertainty += 1
            self._active_phase = self._next_due = None
            self._closing = True
            ticket = self._request_locked("TASK_CLOSE", None, None, None, None)
            self._wait_locked(ticket, timeout_seconds)
        return self.snapshot()

    def snapshot(self):
        with self._condition:
            return dict(
                observed_rows=self._observed,
                persisted_watermark=self._watermark,
                dropped_unpersisted_rows=self._dropped,
                ring_evictions=self._overflow,
                persisted_files=self._files,
                persisted_bytes=self._bytes,
                reserved_files=self._reserved_files,
                reserved_bytes=self._reserved_bytes,
                buffered_rows=max(
                    0, min(len(self._rows), self._observed - self._watermark)
                ),
                failure_code=self._failure,
                closed=self._closed,
                persistence_uncertain=self._reserved_files > self._files
                or bool(self._uncertainty),
                final_coverage_complete=bool(
                    self._closed
                    and not self._failure
                    and not self._uncertainty
                    and not self._dropped
                    and not self._overflow
                    and self._watermark == self._observed
                ),
                sampling_coverage_proof=False,
                schema=SCHEMA,
                uncertainty_count=self._uncertainty,
                reserved_cuts=self._requested,
                maximum_selected_cuts=self._cut_limit,
                last_sha256=self._previous,
                timing_binding=dict(self.binding),
                timing_policy_version=self.policy_version,
                active_phase_id=self._active_phase,
            )

    def _root_check(self):
        info = self.root.lstat()
        _require(
            cp._private(info, True)
            and (info.st_dev, info.st_ino) == self._root_identity,
            "CHECKPOINT_ROOT_CHANGED",
        )
        _require(
            _path_identity(self.root) == self._path_identity, "CHECKPOINT_ROOT_CHANGED"
        )

    def _persist(self, raw, index):
        self._root_check()
        # Reservation precedes the first exclusive creation, including failures.
        self._charge(len(raw))
        path = self.root / f"chunk{index:06d}.bin"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            remaining = memoryview(raw)
            while remaining:
                size = os.write(fd, remaining)
                _require(size > 0, "CHECKPOINT_SHORT_WRITE")
                remaining = remaining[size:]
            os.fsync(fd)
        finally:
            os.close(fd)
        self._root_check()
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self._readback(path, raw)

    def _readback(self, path, raw):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            _require(
                cp._private(before) and before.st_size == len(raw),
                "CHECKPOINT_READBACK_FAILED",
            )
            offset = 0
            while offset < len(raw):
                part = os.read(fd, min(ROW_BYTES, len(raw) - offset))
                _require(
                    part and part == memoryview(raw)[offset : offset + len(part)],
                    "CHECKPOINT_READBACK_FAILED",
                )
                offset += len(part)
            _require(
                not os.read(fd, 1)
                and cp._identity(before) == cp._identity(os.fstat(fd)),
                "CHECKPOINT_READBACK_FAILED",
            )
            _require(
                cp._identity(before) == cp._identity(path.lstat()),
                "CHECKPOINT_READBACK_FAILED",
            )
        finally:
            os.close(fd)
        self._root_check()

    def _timer_locked(self):
        if self._active_phase is None or self._pending is not None:
            return None
        now = self._now()
        if now >= self._phase_end or now >= self._deadline:
            self._next_due = None
            return None
        if self._next_due is not None and now >= self._next_due:
            phase = self._active_phase
            _require(
                self._timer_count < (self.windows[phase] + 4999) // 5000,
                "CHECKPOINT_CUT_INVALID",
            )
            self._timer_count += 1
            # No catch-up burst: one cut per actual 5000ms, from this request.
            self._next_due = now + TIMER_NS
            self._request_locked(
                "TIMER", phase, self._phase_open, self._phase_end, self.windows[phase]
            )
        return self._next_due

    def _write_chunk(self, cut):
        # The global TIMING lease is held for this complete arena lifetime.
        arena = bytearray(MAX_BYTES)
        with self._condition:
            self._check_locked()
            _require(self._reserved_files < self._max_files, "CHECKPOINT_FILE_LIMIT")
            old, high = self._watermark, cut["cut_high_watermark"]
            first = max(old + 1, self._observed - len(self._rows) + 1)
            count = min(CHUNK_ROWS, max(0, high - first + 1))
            for offset in range(count):
                packed = self._rows.get(first + offset)
                _require(packed is not None, "CHECKPOINT_RECORD_ORDER_INVALID")
                pos = HEADER_BYTES + offset * ROW_BYTES
                arena[pos : pos + ROW_BYTES] = packed
            total = first + count - 1 if count else high
            final = cut["cut_kind"] == "TASK_CLOSE" and total == high
            dropped = self._dropped + total - old - count
            header = dict(
                schema=SCHEMA,
                policy_version=self.policy_version,
                **self.binding,
                index=self._files + 1,
                previous_sha256=self._previous,
                checkpoint_mono_ns=self._now(),
                **cut,
                cumulative_deadline_ns=self._deadline,
                cut_complete=total == high,
                previous_watermark=old,
                watermark=total,
                first_row_ordinal=first if count else 0,
                last_row_ordinal=total if count else 0,
                row_count=count,
                ring_evictions=self._overflow,
                dropped_unpersisted_rows=dropped,
                uncertainty_count=self._uncertainty,
                final=final,
                terminal_status=(
                    "FINAL_INCOMPLETE"
                    if dropped or self._overflow or self._uncertainty
                    else "FINAL_COMPLETE"
                )
                if final
                else "OPEN",
                sampling_coverage_proof=False,
            )
            _require(
                header["checkpoint_mono_ns"] < self._deadline, "CHECKPOINT_WAIT_EXPIRED"
            )
        # Encode straight into the frame's header area: no second4096 block.
        encode_header(header, memoryview(arena)[:HEADER_BYTES])
        raw = memoryview(arena)[: HEADER_BYTES + ROW_BYTES * count].toreadonly()
        with self._condition:
            self._reserved_files += 1
            self._reserved_bytes += len(raw)
        self._persist(raw, header["index"])
        digest = hashlib.sha256(raw).hexdigest()
        with self._condition:
            self._check_locked()  # Timed-out/poisoned writes cannot recover.
            _require(self._now() <= self._deadline, "CHECKPOINT_WAIT_EXPIRED")
            self._files, self._bytes = header["index"], self._bytes + len(raw)
            self._previous, self._watermark, self._dropped = digest, total, dropped
            if header["cut_complete"]:
                self._serviced = cut["cut_id"]
                self._closed = final
                self._condition.notify_all()
        return final, total, high

    def _run(self):
        try:
            while True:
                with self._condition:
                    self._check_locked()
                    while self._pending is None:
                        due = self._timer_locked()
                        if self._pending is not None:
                            break
                        self._condition.wait(
                            None
                            if due is None
                            else max(0.001, (due - self._now()) / 1e9)
                        )
                        self._check_locked()
                    cut, self._pending = self._pending, None
                while True:
                    with scratch.lease("TIMING"):
                        final, total, high = self._write_chunk(cut)
                    if final:
                        return
                    if total == high:
                        break
        except BaseException as error:
            with self._condition:
                if self._failure is None:
                    self._failure = _failure(error)
                self._condition.notify_all()


def is_compact(root):
    """Detection only; the compact opener subsequently validates every entry."""
    with os.scandir(root) as entries:
        return any(entry.name.endswith(".bin") for entry in entries)


def descriptor():
    """Machine-readable successor identity; historical descriptors stay frozen."""
    from . import s12_public_sampling_contract as ap

    return dict(
        descriptor_version=SCHEMA,
        scope="SUPPLEMENTARY_TIMING_ONLY",
        closed=True,
        live_instance=False,
        sampling_coverage_proof=False,
        framing=dict(
            magic_hex=MAGIC.hex(),
            header_block_bytes=HEADER_BYTES,
            header_length_offset=8,
            header_length_encoding="UINT32_LITTLE_ENDIAN",
            canonical_json_offset=12,
            canonical_json_maximum_bytes=HEADER_BYTES - 12,
            canonical_json="SORTED_ASCII_KEYS_COMPACT_JSON_LF",
            unused_header_bytes="ZERO",
            row_bytes=ROW_BYTES,
            maximum_rows=CHUNK_ROWS,
            maximum_total_bytes=MAX_BYTES,
            file_name_pattern="chunk[000001..001500].bin",
        ),
        header_fields=sorted(_HEADER),
        header_schema={
            **{key: "UINT64" for key in _HEADER},
            **{key: "NONZERO_LOWERCASE_SHA256" for key in _BINDING},
            "schema": "=" + SCHEMA,
            "policy_version": list(POLICY_VERSIONS),
            "previous_sha256": "LOWERCASE_SHA256",
            "phase_id": "POSITIVE_UINT64_MAX32_OR_NULL",
            "phase_selected_ms": "POSITIVE_UINT64_OR_NULL",
            "phase_open_mono_ns": "UINT64_OR_NULL",
            "phase_end_mono_ns": "UINT64_OR_NULL",
            "phase_deadline_ns": "UINT64_OR_NULL",
            "cut_kind": sorted(_KINDS),
            "cut_complete": "BOOL",
            "final": "BOOL",
            "terminal_status": ["OPEN", "FINAL_COMPLETE", "FINAL_INCOMPLETE"],
            "sampling_coverage_proof": "=false",
        },
        row_schema=ap.TIMING_SCHEMA,
        named_types=ap.TYPES,
        row_encoding=dict(
            kind_byte=0,
            kinds={"PERIODIC_ASYNC": 0, "HARD_SYNC": 1},
            outcome_byte=1,
            outcomes=list(bounded.OUTCOMES),
            role_byte=2,
            roles=["REGULAR", "FINAL"],
            future_used_byte=3,
            null_mask_offset=8,
            null_mask_encoding="UINT64_LITTLE_ENDIAN",
            number_offset=16,
            number_encoding="UINT64_LITTLE_ENDIAN",
            periodic_number_fields=list(bounded.NUMBERS),
            periodic_hash_fields=list(bounded.HASHES),
            hash_bytes=32,
            hash_null_mask_bit_offset=32,
            hard_number_fields=[cp.PUBLIC_FIELDS[0], *cp.PUBLIC_FIELDS[3:]],
            hard_fixed_cause="START_RESERVE",
            unused_bytes="ZERO",
            acceptance="DECODE_VALIDATE_REPACK_EXACT_EQUALITY",
        ),
        cuts=dict(
            timer_interval_ms=5000,
            timer_limit="CEIL_SELECTED_PHASE_MS_DIV_5000",
            boundary_cuts_per_selected_root=2,
            task_close_cuts=1,
            high_watermark="FROZEN_PER_CUT",
            drain_rows=56,
            partial_chunks_per_cut=1,
            pending_rows_create_cut=False,
            off_phase_timers=False,
            deadline_extension=False,
            boundary_requires_quiescent_producers=True,
        ),
        accounting=dict(
            maximum_files=MAX_FILES,
            summary_reserve_bytes=2**20,
            maximum_ring_rows=4096,
            precharge="CUT_AND_EVERY_ATTEMPTED_FILE",
            refunds=False,
            persistence_retry=False,
            native_component_bound_claim=False,
            shared_timing_scratch_partition_bytes=scratch.CAPS["TIMING"],
            maximum_concurrent_timing_frames=1,
            canonical_header_arena_bytes=HEADER_BYTES - 12,
            readback_piece_bytes=ROW_BYTES,
            logical_component_ceiling_bytes=16777216,
            logical_serialization_scratch_ceiling_bytes=65536,
        ),
        reopening=dict(
            history_lists=False,
            numeric_membership="EXACT_CANONICAL_SEQUENCE",
            original_source_set="FRESH_BYTES_TYPES_IDENTITY_PATHS_HASHES_TWO_PASSES",
            completed_persistence="MATCH_ORIGINAL_SUCCESSFUL_TASK_CHECKPOINT_SNAPSHOT",
            bytes_alone_prove_fsync_ack=False,
        ),
    )


def _membership(root, maximum, expected_count=None):
    count = 0
    with os.scandir(root) as entries:
        for entry in entries:
            match = _NAME.fullmatch(entry.name)
            _require(match is not None, "CHECKPOINT_EXTRA_MEMBER")
            number = int(match[1])
            count += 1
            _require(
                count <= maximum and 1 <= number <= maximum,
                "CHECKPOINT_MEMBERSHIP_LIMIT",
            )
            if expected_count is not None:
                _require(number <= expected_count, "CHECKPOINT_MEMBERSHIP_GAP")
    _require(
        expected_count is None or count == expected_count, "CHECKPOINT_MEMBERSHIP_GAP"
    )
    return count


def _read(root, index, maximum):
    path = root / f"chunk{index:06d}.bin"
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        _require(
            cp._private(before) and HEADER_BYTES <= before.st_size <= maximum,
            "CHECKPOINT_FILE_INVALID",
        )
        arena = bytearray(before.st_size)
        with os.fdopen(fd, "rb", buffering=0, closefd=False) as stream:
            size = stream.readinto(arena)
            _require(
                size == before.st_size and not stream.read(1), "CHECKPOINT_FILE_CHANGED"
            )
        _require(
            cp._identity(before) == cp._identity(os.fstat(fd)),
            "CHECKPOINT_FILE_CHANGED",
        )
        _require(
            cp._identity(before) == cp._identity(path.lstat()),
            "CHECKPOINT_FILE_CHANGED",
        )
        return arena, cp._identity(before)
    finally:
        os.close(fd)


def _source_part(digest, index, identity, raw):
    digest.update(
        cp._canonical([index, list(identity), hashlib.sha256(raw).hexdigest()])
    )


def read_prefix(root, **kwargs):
    # A consumer may use other logical partitions, but cannot materialize a
    # second timing frame recursively or race this arena with another reader.
    with scratch.lease("TIMING"):
        return _read_prefix(root, **kwargs)


def _read_prefix(
    root,
    *,
    max_files=MAX_FILES,
    max_bytes=MAX_BYTES,
    record_consumer=None,
    expected_binding=None,
    expected_snapshot=None,
):
    """Constant-history-memory numeric membership, rows and fresh source reopening.

    Each original is read again after callbacks. The aggregate includes original
    inode/type/owner/mode/size/mtime/ctime and exact bytes, with no history list.
    A byte-valid final file alone cannot establish the writer's fsync return.
    """
    root = Path(root)
    result = dict(
        verified_files=0,
        verified_rows=0,
        last_watermark=0,
        dropped_unpersisted_rows=0,
        last_sha256=cp._ZERO,
        incomplete=True,
        reason="NO_FINAL_CHECKPOINT",
        sampling_coverage_proof=False,
        last_payload=None,
    )
    try:
        _require(
            type(max_files) is int
            and 1 <= max_files <= MAX_FILES
            and type(max_bytes) is int
            and HEADER_BYTES <= max_bytes <= MAX_BYTES,
            "CHECKPOINT_LIMIT_INVALID",
        )
        if expected_binding is not None:
            expected_binding = validate_binding(expected_binding)
        info = root.lstat()
        _require(cp._private(info, True), "CHECKPOINT_ROOT_INVALID")
        identity = cp._identity(info)
        path_identity = _path_identity(root)
        count = _membership(root, max_files)
        _membership(root, max_files, count)
        previous, watermark, dropped, evictions, uncertainty, observed_clock = (
            cp._ZERO,
            0,
            0,
            0,
            0,
            0,
        )
        last, binding, total_bytes = None, None, 0
        active, last_phase, timer_count, timer_clock = None, 0, 0, 0
        source_digest = hashlib.sha256()
        for index in range(1, count + 1):
            raw, file_identity = _read(root, index, max_bytes)
            header = decode_header(memoryview(raw)[:HEADER_BYTES])
            current_binding = {k: header[k] for k in _BINDING}
            _require(binding is None or current_binding == binding)
            _require(expected_binding is None or current_binding == expected_binding)
            binding = current_binding
            _require(last is None or header["policy_version"] == last["policy_version"])
            _require(header["index"] == index and header["previous_sha256"] == previous)
            _require(header["previous_watermark"] == watermark)
            _require(header["checkpoint_mono_ns"] >= observed_clock)
            _require(
                header["ring_evictions"] >= evictions
                and header["uncertainty_count"] >= uncertainty
            )
            _require(
                header["dropped_unpersisted_rows"]
                == dropped + header["watermark"] - watermark - header["row_count"],
                "CHECKPOINT_WATERMARK_INVALID",
            )
            _require(
                len(raw) == HEADER_BYTES + ROW_BYTES * header["row_count"],
                "CHECKPOINT_BYTE_LIMIT",
            )
            _require(not header["final"] or index == count)
            if last is None:
                _require(header["cut_id"] == 1)
            elif header["cut_id"] == last["cut_id"]:
                _require(not last["cut_complete"])
                _require(
                    all(
                        header[k] == last[k]
                        for k in (
                            "cut_kind",
                            "cut_high_watermark",
                            "cut_requested_mono_ns",
                            "phase_id",
                            "phase_selected_ms",
                            "phase_open_mono_ns",
                            "phase_end_mono_ns",
                            "phase_deadline_ns",
                            "cumulative_deadline_ns",
                        )
                    )
                )
            else:
                _require(
                    last["cut_complete"] and header["cut_id"] == last["cut_id"] + 1
                )
                _require(
                    header["cumulative_deadline_ns"] == last["cumulative_deadline_ns"]
                )
            if last is None or header["cut_id"] != last["cut_id"]:
                kind, phase, requested = (
                    header["cut_kind"],
                    header["phase_id"],
                    header["cut_requested_mono_ns"],
                )
                window = tuple(
                    header[k]
                    for k in (
                        "phase_id",
                        "phase_selected_ms",
                        "phase_open_mono_ns",
                        "phase_end_mono_ns",
                        "phase_deadline_ns",
                    )
                )
                if kind == "PHASE_OPEN":
                    _require(
                        active is None and phase == last_phase + 1,
                        "CHECKPOINT_PHASE_INVALID",
                    )
                    _require(
                        requested
                        == header["phase_open_mono_ns"]
                        < header["phase_end_mono_ns"],
                        "CHECKPOINT_PHASE_INVALID",
                    )
                    active, last_phase, timer_count, timer_clock = (
                        window,
                        phase,
                        0,
                        requested,
                    )
                elif kind == "TIMER":
                    _require(
                        active == window and requested - timer_clock >= TIMER_NS,
                        "CHECKPOINT_PHASE_INVALID",
                    )
                    _require(
                        requested
                        < header["phase_end_mono_ns"]
                        <= header["cumulative_deadline_ns"],
                        "CHECKPOINT_PHASE_INVALID",
                    )
                    timer_count += 1
                    _require(
                        timer_count <= (header["phase_selected_ms"] + 4999) // 5000,
                        "CHECKPOINT_CUT_INVALID",
                    )
                    timer_clock = requested
                elif kind == "PHASE_CLOSE":
                    _require(active == window, "CHECKPOINT_PHASE_INVALID")
                    _require(
                        requested <= header["phase_end_mono_ns"]
                        or header["uncertainty_count"] > 0,
                        "CHECKPOINT_PHASE_INVALID",
                    )
                    active = None
                else:
                    _require(
                        active is None or header["uncertainty_count"] > 0,
                        "CHECKPOINT_PHASE_INVALID",
                    )
            # Validate every row before exposing any record from this chunk.
            for offset in range(header["row_count"]):
                start = HEADER_BYTES + ROW_BYTES * offset
                row = decode_row(memoryview(raw)[start : start + ROW_BYTES])
                phase = (
                    row["legacy_row"][0]
                    if row["row_kind"] == "HARD_SYNC"
                    else row["phase_id"]
                )
                _require(
                    phase == header["phase_id"] or header["uncertainty_count"] > 0,
                    "CHECKPOINT_PHASE_INVALID",
                )
            _source_part(source_digest, index, file_identity, raw)
            previous = hashlib.sha256(raw).hexdigest()
            watermark, dropped = header["watermark"], header["dropped_unpersisted_rows"]
            evictions, uncertainty, observed_clock = (
                header["ring_evictions"],
                header["uncertainty_count"],
                header["checkpoint_mono_ns"],
            )
            total_bytes += len(raw)
            if record_consumer is not None:
                for offset in range(header["row_count"]):
                    start = HEADER_BYTES + ROW_BYTES * offset
                    record_consumer(
                        header["first_row_ordinal"] + offset,
                        decode_row(memoryview(raw)[start : start + ROW_BYTES]),
                    )
            last = header
            result.update(
                verified_files=index,
                verified_rows=result["verified_rows"] + header["row_count"],
                last_watermark=watermark,
                dropped_unpersisted_rows=dropped,
                last_sha256=previous,
                last_payload=header,
            )
            del raw
        _require(cp._identity(root.lstat()) == identity, "CHECKPOINT_ROOT_CHANGED")
        _require(_path_identity(root) == path_identity, "CHECKPOINT_ROOT_CHANGED")
        _membership(root, max_files, count)
        reopened = hashlib.sha256()
        for index in range(1, count + 1):
            raw, file_identity = _read(root, index, max_bytes)
            _source_part(reopened, index, file_identity, raw)
            del raw
        _require(reopened.digest() == source_digest.digest(), "CHECKPOINT_FILE_CHANGED")
        _membership(root, max_files, count)
        _require(cp._identity(root.lstat()) == identity, "CHECKPOINT_ROOT_CHANGED")
        _require(_path_identity(root) == path_identity, "CHECKPOINT_ROOT_CHANGED")
        result["source_set_sha256"] = source_digest.hexdigest()
        if last and last["final"]:
            result["reason"] = (
                "TELEMETRY_TRUNCATED"
                if dropped or evictions
                else "CHECKPOINT_ACK_UNVERIFIED"
            )
            if (
                not dropped
                and not evictions
                and not uncertainty
                and type(expected_snapshot) is dict
            ):
                expected = dict(
                    closed=True,
                    failure_code=None,
                    persistence_uncertain=False,
                    final_coverage_complete=True,
                    observed_rows=watermark,
                    persisted_watermark=watermark,
                    persisted_files=count,
                    reserved_files=count,
                    persisted_bytes=total_bytes,
                    reserved_bytes=total_bytes,
                    last_sha256=previous,
                    timing_binding=binding,
                    timing_policy_version=last["policy_version"],
                    uncertainty_count=0,
                )
                _require(
                    all(
                        k in expected_snapshot
                        and type(expected_snapshot[k]) is type(v)
                        and expected_snapshot[k] == v
                        for k, v in expected.items()
                    ),
                    "CHECKPOINT_ACK_UNVERIFIED",
                )
                result.update(incomplete=False, reason=None)
    except BaseException as error:
        result.update(incomplete=True, reason=_failure(error))
    return result

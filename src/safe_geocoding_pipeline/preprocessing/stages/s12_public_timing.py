"""Supplementary public timing: bounded memory on hot paths, independent I/O.

No method in a trace writes files. Null milestones mean unobserved, including
late writer work after a caller timeout. This evidence never proves sampling
coverage or grants authority to change campaign acceptance.
"""

from __future__ import annotations

import threading

from . import s12_public_checkpoints as cp

MAX_FILES = 1500
MAX_BYTES = 32768
TASK_FILE_CAP = 300_000
SUMMARY_RESERVE = 2**20
_METRICS = frozenset(
    (
        "wake_lateness",
        "slot_busy",
        "resource_observation",
        "safety_wait",
        "persistence_ack",
        "writer_queue_wait",
        "writer_action",
        "overdue_after_ack",
    )
)
_FIELDS = frozenset(cp.PUBLIC_FIELDS)


def safe_call(observer, method, *args):
    """A supplementary failure must never replace an authoritative outcome."""
    if observer is None:
        return None
    try:
        return getattr(observer, method)(*args)
    except BaseException:
        try:
            observer.note_failure()
        except BaseException:
            pass
        return None


class Trace:
    """Exactly one fixed dictionary per outstanding resource call."""

    __slots__ = ("clock", "values", "lock", "finished", "owner")

    def __init__(self, phase_id, cause, clock, owner=None):
        self.owner = owner
        self.clock = clock
        self.values = dict.fromkeys(cp.PUBLIC_FIELDS)
        self.values.update(phase_id=phase_id, cause=cause, outcome="FAILED")
        self.lock = threading.Lock()
        self.finished = False
        self.mark("collector_enter_ns")

    def note_failure(self):
        safe_call(self.owner, "note_failure")

    def mark(self, name, value=None):
        if name not in _FIELDS or name in ("phase_id", "cause", "outcome"):
            raise cp.CheckpointError("CHECKPOINT_ROW_INVALID")
        value = self.clock.now_ns() if value is None else value
        if not cp._integer(value):
            raise cp.CheckpointError("CHECKPOINT_CLOCK_INVALID")
        with self.lock:
            # A late writer cannot revise an already emitted uncertain row.
            if not self.finished:
                self.values[name] = value

    def outcome(self, value):
        if value not in ("COMPLETE", "FAILED", "CANCELLED", "UNCERTAIN"):
            raise cp.CheckpointError("CHECKPOINT_ROW_INVALID")
        with self.lock:
            if not self.finished:
                self.values["outcome"] = value

    def take(self):
        with self.lock:
            if self.finished:
                return None
            self.finished = True
            if self.values["outcome"] == "COMPLETE" and any(
                self.values[name] is None
                for name in cp.PUBLIC_FIELDS[3:]
                if name != "sampler_slot_acquired_ns"
                and name != "sampler_slot_released_ns"
            ):
                self.values["outcome"] = "UNCERTAIN"
            return tuple(self.values[name] for name in cp.PUBLIC_FIELDS)


class PublicTiming:
    """One optional observer per task, outside all authoritative phase trees.

    ``budget_charge(bytes)`` reserves one creation (including the zero-byte
    directory) before I/O; uncertain attempts are never refunded. Reduced test
    caps are permitted by the shared Checkpoints implementation.
    """

    def __init__(self, root, *, phase_count, budget_charge=lambda size: None, **limits):
        if type(phase_count) is not int or not 1 <= phase_count <= 32:
            raise cp.CheckpointError("CHECKPOINT_LIMIT_INVALID")
        self.lock = threading.Lock()
        self.phase_count, self.phase_id = phase_count, 1
        self.failures = 0
        self.closed = False
        self.samples = {}
        self.charged_bytes = self.charged_creations = 0
        self.outstanding = self.completed_rows = self.partial_rows = 0
        self.checkpoints = None
        self.reservation = None

        def charge(size):
            # Reserve first; a failure retains its uncertain charge.
            with self.lock:
                self.charged_bytes += size
                self.charged_creations += 1
            budget_charge(size)

        try:
            charge(0)
            self.checkpoints = cp.Checkpoints(
                root, budget_charge=charge, row_schema=cp.PUBLIC_SCHEMA, **limits
            )
        except BaseException:
            self.note_failure()

    def note_failure(self):
        with self.lock:
            self.failures = min(2**64 - 1, self.failures + 1)

    def set_phase(self, phase_id):
        if type(phase_id) is not int or not 1 <= phase_id <= self.phase_count:
            raise cp.CheckpointError("CHECKPOINT_LABEL_INVALID")
        with self.lock:
            self.phase_id = phase_id
        if self.checkpoints:
            self.checkpoints.set_phase("PUBLIC_PHASE", "RESOURCE_PATH")

    def begin(self, cause, clock):
        if cause not in ("PERIODIC", "START_RESERVE"):
            return None
        with self.lock:
            phase_id = self.phase_id
            if self.outstanding >= 8 or self.closed:
                raise cp.CheckpointError("CHECKPOINT_LIMIT_INVALID")
            self.outstanding += 1
        return Trace(phase_id, cause, clock, self)

    def finish(self, trace):
        if trace is not None:
            row = trace.take()
            if row is not None:
                with self.lock:
                    self.outstanding -= 1
                    if row[2] == "COMPLETE":
                        self.completed_rows = min(2**64 - 1, self.completed_rows + 1)
                    else:
                        self.partial_rows = min(2**64 - 1, self.partial_rows + 1)
                if self.checkpoints is not None:
                    self.checkpoints.record(row)

    def sampling(self, metrics):
        if (
            not isinstance(metrics, dict)
            or set(metrics) != _METRICS
            or any(
                not isinstance(cell, list)
                or len(cell) != 3
                or any(not cp._integer(n) for n in cell)
                for cell in metrics.values()
            )
        ):
            raise cp.CheckpointError("CHECKPOINT_ROW_INVALID")
        with self.lock:
            self.samples[self.phase_id] = {
                name: list(cell) for name, cell in metrics.items()
            }

    def boundary(self):
        if self.checkpoints is not None:
            self.checkpoints.flush(timeout_seconds=5)

    def close(self):
        if self.checkpoints is not None:
            self.checkpoints.close(timeout_seconds=5)
        self.closed = True
        return self.snapshot()

    def snapshot(self):
        checkpoint = self.checkpoints.snapshot() if self.checkpoints else None
        with self.lock:
            return {
                "schema": "stage12_public_path_timing_summary_v1",
                "enabled": True,
                "observer_failure_count": self.failures,
                "persistence_complete": bool(
                    not self.failures
                    and not self.outstanding
                    and self.closed
                    and checkpoint
                    and checkpoint["final_coverage_complete"]
                    and not checkpoint["failure_code"]
                ),
                "outstanding_traces": self.outstanding,
                "complete_timing_rows": self.completed_rows,
                "partial_timing_rows": self.partial_rows,
                "final_timing_coverage_complete": bool(
                    self.closed
                    and not self.outstanding
                    and not self.partial_rows
                    and not self.failures
                    and checkpoint
                    and checkpoint["final_coverage_complete"]
                    and not checkpoint["failure_code"]
                ),
                "charged_bytes": self.charged_bytes,
                "charged_creations": self.charged_creations,
                "task_allocation_reservation": self.reservation,
                "sampler_aggregates_by_phase": {
                    str(k): v for k, v in self.samples.items()
                },
                "checkpoint": checkpoint,
                "sampling_coverage_proof": False,
            }


def for_task(config, output):
    """Pre-reserve supplementary maxima within the selected task envelope.

    The file bound reserves all selected events plus 24 creations per attempted
    exchange, 128 per phase for closure/metadata and 128 task metadata members.
    This is application accounting, never a physical allocation/inode guarantee.
    """
    phases = config["campaigns"]
    selected_bytes = sum(x["plan"]["budgets"]["storage_bytes"] for x in phases)
    selected_events = sum(x["plan"]["budgets"]["event_count"] for x in phases)
    attempts = sum(
        x["plan"]["budgets"]["data_attempts"]
        + x["plan"]["budgets"]["control_http_attempts"]
        for x in phases
    )
    reserved_bytes = MAX_FILES * MAX_BYTES + SUMMARY_RESERVE
    reserved_creations = MAX_FILES + 1
    if (
        selected_bytes + reserved_bytes > config["resources"]["allocated_disk_bytes"]
        or selected_events
        + 24 * attempts
        + 128 * len(phases)
        + 128
        + reserved_creations
        > TASK_FILE_CAP
    ):
        raise cp.CheckpointError("CHECKPOINT_LIMIT_INVALID")
    observer = PublicTiming(output / "public_path_timing", phase_count=len(phases))
    observer.reservation = {
        "bytes": reserved_bytes,
        "creations": reserved_creations,
        "task_byte_ceiling": config["resources"]["allocated_disk_bytes"],
        "task_file_ceiling": TASK_FILE_CAP,
        "physical_quota_verified": False,
    }
    return observer


def verify_association(row, event, *, phase_id):
    """Match one supplementary row to an exact freshly reopened original event.

    A mismatch is diagnostic only; this does not validate an event chain or turn
    supplementary telemetry into authoritative campaign evidence.
    """
    values = dict(zip(cp.PUBLIC_FIELDS, cp._public_row(row), strict=True))
    try:
        matches = (
            values["phase_id"] == phase_id
            and event["kind"] == "RESOURCE"
            and event["body"]["cause"] == values["cause"]
            and event["body"]["observed_mono_ns"] == values["observed_ns"]
            and event["segment_id"] == values["segment_id"]
            and event["seq"] == values["event_seq"]
            and event["mono_ns"] == values["event_mono_ns"] == values["event_header_ns"]
        )
    except (KeyError, TypeError):
        matches = False
    if not matches:
        raise cp.CheckpointError("CHECKPOINT_BINDING_INVALID")
    return values

"""AP-1 fixed outstanding arena and original-evidence reader. No HTTP authority."""

from __future__ import annotations
from array import array
from collections import deque
from contextlib import nullcontext
import threading
import time
from . import s12_public_sampling_contract as a
from . import s12_retrieval_contract as c


def count(value):
    return {"value": value, "confirmed_min": value or 0}


class SamplingFailure(RuntimeError):
    """Static, secret-free sampler disposition."""


class Sampler:
    def __init__(self, coordinator):
        self.contract = coordinator.contract
        self.co = coordinator
        self.writer = coordinator.writer
        self.log = coordinator.journal
        self.clock = coordinator.clock
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.arena = bytearray(65536)
        self.states = array("Q", [0] * 16)
        self.lengths = array("Q", [0] * 16)
        self.ordinals = array("Q", [0] * 16)
        self.entered = array("Q", [0] * 16)
        self.observed = array("Q", [0] * 16)
        self.reserved = self.acquired = self.appended = self.acknowledged = (
            self.witnessed
        ) = 0
        self.occupied = 0
        self.failure = None
        self.failure_stage = "ACQUIRE"
        self.fault_written = False
        self.anchor = None
        self.seed = None
        self.head = None
        self.association = None
        self.last_observed = None
        self.last_witness_reopened = None
        self.open_seq = None
        self.opened = False
        self.producer_closed = None
        self.close_requested = None
        self.cut = None
        self.cut_taken = False
        self.final_seq = None
        self.final_observed = None
        self.owner_busy = False
        self.stop = threading.Event()
        self.thread = None
        self.action_started = None
        self.closed = False
        self.close_body = None
        self.close_end = None
        self.close_failed = False
        self.maximum_gap = 0
        self.gaps = 0
        self.maximum_age = 0
        self.final_ack = None
        self.deadline_ns = self.clock.now_ns() + int(
            self.writer.remaining_seconds() * 1e9
        )
        self.traces = [None] * 16
        self.pending_release = None
        self.log.ap_inventory_limit = coordinator.plan["sampling_budget"][
            "maximum_inventory_versions_per_segment"
        ]
        self.owner_ident = None
        self.log.ap_pending_events = 4
        self.log.ap_pending_bytes = 32768
        self.maximum_observations = coordinator.plan["sampling_budget"][
            "maximum_observations"
        ]

    def fail(self, code, stage="ACQUIRE"):
        a = self.contract
        a.validate_type(code, "SamplingFailure")
        with self.lock:
            if self.failure is None:
                self.failure, self.failure_stage = code, stage
            self.condition.notify_all()
        # Never wait for disk to close the real admission boundary.
        with self.co.safety:
            self.co.measurement_failed = True
            if self.co.stop_reason is None:
                self.co.stop_reason = (
                    "AUDIT_IO"
                    if code in ("WRITE_UNCERTAIN", "READBACK_FAILED", "ACK_UNCERTAIN")
                    else "TIME"
                    if code == "DRAIN_EXPIRED"
                    else "RESOURCE"
                    if code
                    in (
                        "OBSERVATION_COUNT_LIMIT",
                        "OBSERVATION_BYTE_LIMIT",
                        "OBSERVATION_STORAGE_LIMIT",
                    )
                    else "BUDGET"
                    if code == "OBSERVATION_EVENT_LIMIT"
                    else "MEASUREMENT_FAILURE"
                )
                self.co.state = "STOPPED"
            self.co.wake.set()
        self.writer.wake.set()

    def anchor_open(self, event):
        a = self.contract
        a.require(self.anchor is None)
        self.anchor = event["mono_ns"]
        self.last_observed = self.anchor
        self.seed = a.digest(
            dict(
                schema_version=a.SEED,
                campaign_start_sha256=self.log.start_hash,
                profile_sha256=a.digest(self.co.profile),
                segment_id=self.log.segment,
                epoch_id=self.log.epoch,
            )
        )
        self.head = self.association = self.seed
        self.anchor_event_seq, self.anchor_event_sha = event["seq"], a.digest(event)
        self.thread = threading.Thread(
            target=self._owner, name="stage12-public-sampler", daemon=True
        )
        self.thread.start()

    def publish_open(self):
        a = self.contract
        self.log.event(
            "SAMPLING_OPEN",
            dict(
                policy_sha256=a.POLICY_SHA,
                seed_sha256=self.seed,
                anchor_event_seq=self.anchor_event_seq,
                anchor_event_sha256=self.anchor_event_sha,
                anchor_mono_ns=self.anchor,
                baseline=self.co.ap_baseline,
            ),
        )
        self.open_seq = self.log.seq
        self.opened = True
        self.writer.wake.set()

    def health(self):
        now = self.clock.now_ns()
        with self.lock:
            if self.anchor is None:
                return
            if now < self.last_observed:
                self.fail("CLOCK_INVALID")
            if self.co.ap_cut_fault:
                self.fail("ORDER_INVALID", "DRAIN")
            if self.writer.failed.is_set():
                self.fail("WRITE_UNCERTAIN", "APPEND")
            if (
                self.failure is None
                and self.producer_closed is None
                and now - self.last_observed > 100_000_000
            ):
                self.fail("ACQUISITION_GAP")
            for i, state in enumerate(self.states):
                if (
                    state in (1, 2, 3)
                    and now - (self.observed[i] or self.entered[i]) > 500_000_000
                ):
                    self.fail("ACK_AGE_LIMIT", "ACK")
            if (
                self.writer.ap_active_started is not None
                and now - self.writer.ap_active_started >= 5_000_000_000
            ):
                self.writer.failed.set()
                self.fail("WRITE_UNCERTAIN", "APPEND")
            if (
                self.close_requested is not None
                and not self.closed
                and now - self.close_requested >= 5_000_000_000
            ):
                self.fail("DRAIN_EXPIRED", "DRAIN")
        # Cumulative deadline is a clock comparison, never the I/O checkpoint.
        if now >= self.deadline_ns:
            self.fail("DRAIN_EXPIRED", "DRAIN")

    def _reserve(self, final=False):
        a = self.contract
        with self.lock:
            if self.co.ap_cut_fault:
                self.fail("ORDER_INVALID", "DRAIN")
            if self.writer.failed.is_set():
                self.fail("WRITE_UNCERTAIN", "APPEND")
            if self.failure:
                return None
            if self.cut is not None and not final:
                return None
            if final:
                a.require(
                    self.cut is not None
                    and not self.cut_taken
                    and self.occupied == 0
                    and not self.owner_busy
                )
                a.require(
                    self.cut["prefix_last_event_seq"] == self.log.seq
                    and self.cut["prefix_last_event_sha256"] == self.log.last_hash
                )
                self.cut_taken = True
            if self.occupied >= 16:
                self.fail("OBSERVATION_COUNT_LIMIT", "RESERVE")
                return None
            if self.reserved >= self.maximum_observations:
                self.fail("OBSERVATION_EVENT_LIMIT", "RESERVE")
                return None
            # No filesystem call: accounting was enabled before owner startup.
            with self.log.ap_budget_lock:
                if self.log.normal_event_headroom() < 2:
                    self.fail("OBSERVATION_EVENT_LIMIT", "RESERVE")
                    return None
                try:
                    self.log.check_storage(16384)
                except c.Stage12Error:
                    self.fail("OBSERVATION_STORAGE_LIMIT", "RESERVE")
                    return None
                self.log.ap_pending_events += 2
                self.log.ap_pending_bytes += 16384
            i = next(i for i, state in enumerate(self.states) if state == 0)
            self.reserved += 1
            self.occupied += 1
            self.ordinals[i] = self.reserved
            self.entered[i] = self.clock.now_ns()
            self.observed[i] = 0
            self.owner_busy = True
            if self.co.timing_observer is not None:
                row = {k: None for k in a.ASYNC_FIELDS}
                row.update(
                    row_kind="PERIODIC_ASYNC",
                    phase_id=self.co.timing_observer.phase_id,
                    segment_id=self.log.segment,
                    epoch_id=self.log.epoch,
                    acquisition_seq=self.ordinals[i],
                    role="FINAL" if final else "REGULAR",
                    future_used=False,
                    outcome="FAILED",
                    acquire_enter_ns=self.entered[i],
                    reserved_ns=self.entered[i],
                )
                self.traces[i] = row
            self.states[i] = 1
            return i, self.occupied

    def trace_mark(self, i, name, value=None):
        row = self.traces[i]
        if row is not None:
            row[name] = self.clock.now_ns() if value is None else value

    def event_milestone(self, kind, obj, stage):
        a = self.contract
        if kind not in ("RESOURCE_SAMPLE", "SAMPLE_ACK"):
            return
        i = next((i for i, s in enumerate(self.states) if s in (3, 4)), None)
        if i is None:
            return
        if stage == "HEADER":
            if kind == "RESOURCE_SAMPLE":
                for k, v in [
                    ("sample_event_seq", obj["seq"]),
                    ("sample_event_sha256", a.digest(obj)),
                    ("sample_header_ns", obj["mono_ns"]),
                ]:
                    self.trace_mark(i, k, v)
            else:
                for k, v in [
                    ("ack_event_seq", obj["seq"]),
                    ("ack_event_sha256", a.digest(obj)),
                    ("ack_witness_header_ns", obj["mono_ns"]),
                ]:
                    self.trace_mark(i, k, v)
        elif kind == "RESOURCE_SAMPLE":
            self.trace_mark(i, "append_complete_ns")

    def uncertain_traces(self):
        # Snapshot only; independent checkpoint worker owns all telemetry I/O.
        # Up to16 rows, no Future or growing list. Occupied credits stay held.
        from .s12_public_timing import safe_call

        safe_call(self.co.timing_observer, "note_failure")
        for i in range(16):
            with self.lock:
                row = self.traces[i]
                self.traces[i] = None
                if row is not None:
                    row = dict(row, outcome="UNCERTAIN")
            if row is not None:
                safe_call(self.co.timing_observer, "periodic", row)

    def pair_return(self):
        if self.pending_release is not None:
            self.trace_mark(self.pending_release, "pair_action_return_ns")

    def after_turn(self):
        a = self.contract
        i = self.pending_release
        a.require(i is not None)
        self.trace_mark(i, "pair_post_action_complete_ns")
        if self.writer.failed.is_set():
            return
        with self.lock:
            self.states[i] = 0
            self.lengths[i] = 0
            self.occupied -= 1
            self.trace_mark(i, "credit_released_ns")
            row = self.traces[i]
            self.traces[i] = None
            self.pending_release = None
            self.condition.notify_all()
            if row is not None:
                row["outcome"] = "COMPLETE"
        if row is not None:
            from .s12_public_timing import safe_call

            safe_call(self.co.timing_observer, "periodic", row)

    def acquire(self, final=False):
        a = self.contract
        a.require(threading.get_ident() == self.owner_ident)
        reservation = self._reserve(final)
        if reservation is None:
            return False
        i, n = reservation
        try:
            begin = self.clock.now_ns()
            self.trace_mark(i, "free_query_start_ns", begin)
            free = self.co.free_bytes()
            end = self.clock.now_ns()
            self.trace_mark(i, "free_query_end_ns", end)
            a.uint(free)
            self.trace_mark(i, "safety_wait_start_ns")
            with self.co.safety:
                self.trace_mark(i, "safety_acquired_ns")
                revision, state = self.co.ap_state()
                observed = self.clock.now_ns()
                self.co.last_sample_ns = observed
            exit_ns = self.clock.now_ns()
            from .s12_wf_ap2_scratch import lease

            with (
                (
                    lease("OBSERVATION")
                    if getattr(a, "AP_ENABLED", False)
                    else nullcontext()
                ),
                self.lock,
            ):
                cut = self.cut if final else None
                value = dict(
                    schema_version=a.OBSERVATION,
                    campaign_start_sha256=self.log.start_hash,
                    segment_id=self.log.segment,
                    epoch_id=self.log.epoch,
                    acquisition_seq=self.ordinals[i],
                    previous_observation_sha256=self.head,
                    role="FINAL" if final else "REGULAR",
                    acquire_enter_ns=self.entered[i],
                    occupied_count_after_reserve=n,
                    occupied_bytes_after_reserve=n * 4096,
                    free_query_start_ns=begin,
                    free_query_end_ns=end,
                    observed_mono_ns=observed,
                    acquire_exit_ns=exit_ns,
                    resource_revision=revision,
                    state=state,
                    free_allocated_disk_bytes=free,
                    cut=cut,
                )
                a.validate(value, a.OBSERVATION)
                raw = c.canonical(value)
                self.arena[i * 4096 : i * 4096 + len(raw)] = raw
                self.lengths[i] = len(raw)
                self.head = a.digest(value)
                self.observed[i] = observed
                self.acquired += 1
                self.states[i] = 2
                for key, val in [
                    ("observation_sha256", self.head),
                    ("resource_revision", revision),
                    ("observed_ns", observed),
                    ("acquire_exit_ns", exit_ns),
                    ("enqueued_ns", self.clock.now_ns()),
                ]:
                    self.trace_mark(i, key, val)
                gap = observed - self.last_observed
                self.maximum_gap = max(self.maximum_gap, gap)
                self.last_observed = observed
                if gap < 0 or gap > 100_000_000:
                    self.gaps += 1
                    self.fail("ACQUISITION_GAP")
                if final:
                    self.final_seq = self.ordinals[i]
                    self.final_observed = observed
                    self.producer_closed = self.clock.now_ns()
                self.writer.wake.set()
                return True
        except BaseException:
            self.fail("ACQUISITION_FAILED")
            from .s12_public_timing import safe_call

            if self.traces[i] is not None:
                safe_call(self.co.timing_observer, "periodic", self.traces[i])
                self.traces[i] = None
            return False
        finally:
            with self.lock:
                self.owner_busy = False
                self.condition.notify_all()

    def _owner(self):
        self.owner_ident = threading.get_ident()
        try:
            while not self.stop.is_set():
                self.health()
                if self.failure:
                    if self.writer.ap_active_started is None:
                        return
                    self.stop.wait(0.005)
                    continue
                with self.lock:
                    final = self.cut is not None and not self.cut_taken
                if final:
                    self.acquire(True)
                    return
                due = self.last_observed + 50_000_000
                if self.clock.now_ns() >= due:
                    self.acquire()
                else:
                    self.stop.wait(min(0.005, max(0, due - self.clock.now_ns()) / 1e9))
        except BaseException:
            self.fail("OWNER_FAILED")

    def transfer_event(self, kind):
        # Transfer prepaid liabilities, before I/O; uncertainty never refunds.
        a = self.contract
        if kind not in (
            "RESOURCE_SAMPLE",
            "SAMPLE_ACK",
            "SAMPLING_OPEN",
            "SAMPLING_FAULT",
            "SAMPLING_CLOSE",
        ):
            return
        with self.log.ap_budget_lock:
            a.require(
                self.log.ap_pending_events > 0 and self.log.ap_pending_bytes >= 8192
            )
            self.log.ap_pending_events -= 1
            self.log.ap_pending_bytes -= 8192

    def service(self):
        if getattr(self.contract, "M2_ENABLED", False) or getattr(self.contract, "RA_ENABLED", False):
            from .s12_wf_ap2_scratch import lease

            # The writer takes this before any sampler/safety lock. The sole
            # producer and writer share one serialization partition.
            with lease("OBSERVATION"):
                return self._service()
        return self._service()

    def _service(self):
        a = self.contract
        """Writer-only one atomic pair, including its witness; no recursive call."""
        self.writer.assert_owner()
        if not self.opened or self.writer.failed.is_set():
            return False
        with self.lock:
            queued = [i for i, s in enumerate(self.states) if s == 2]
            if not queued:
                return False
            i = min(queued, key=lambda k: self.ordinals[k])
            self.states[i] = 3
            raw = bytes(self.arena[i * 4096 : i * 4096 + self.lengths[i]])
            value = a.parse(raw, a.OBSERVATION)
            self.action_started = self.clock.now_ns()
            self.trace_mark(i, "writer_entry_ns", self.action_started)
        try:
            self.health()
            h = self.log.event(
                "RESOURCE_SAMPLE",
                {"observation": value, "observation_sha256": a.digest(value)},
                closure=bool(self.failure or self.close_requested),
                writer_inline=True,
            )
            sample_seq = self.log.seq
            self.writer.check_deadline()
            self.writer.storage_guard()
            acknowledged = self.clock.now_ns()
            with self.lock:
                self.states[i] = 4
                self.appended += 1
                self.acknowledged += 1
                self.trace_mark(i, "event_ack_publish_ns", acknowledged)
                age = acknowledged - value["observed_mono_ns"]
                self.maximum_age = max(self.maximum_age, age)
                if age > 500_000_000:
                    self.fail("ACK_AGE_LIMIT", "ACK")
            ah = self.log.event(
                "SAMPLE_ACK",
                dict(
                    acquisition_seq=value["acquisition_seq"],
                    observation_sha256=a.digest(value),
                    sample_event_seq=sample_seq,
                    sample_event_sha256=h,
                    event_ack_mono_ns=acknowledged,
                ),
                closure=bool(self.failure or self.close_requested),
                writer_inline=True,
            )
            self.writer.check_deadline()
            self.writer.storage_guard()
            reopened = self.clock.now_ns()
            with self.lock:
                self.association = a.digest(
                    dict(
                        previous_sha256=self.association,
                        acquisition_seq=value["acquisition_seq"],
                        observation_sha256=a.digest(value),
                        sample_event_seq=sample_seq,
                        sample_event_sha256=h,
                        ack_event_seq=self.log.seq,
                        ack_event_sha256=ah,
                    )
                )
                self.witnessed += 1
                self.last_witness_reopened = reopened
                self.trace_mark(i, "ack_witness_reopened_ns", reopened)
                self.pending_release = i
                self.condition.notify_all()
                if value["role"] == "FINAL":
                    self.final_ack = reopened
            return True
        except BaseException:
            self.writer.failed.set()
            self.fail("WRITE_UNCERTAIN", "APPEND")
            raise
        finally:
            if (
                self.action_started is not None
                and self.clock.now_ns() - self.action_started >= 5_000_000_000
            ):
                self.writer.failed.set()
                self.fail("WRITE_UNCERTAIN", "APPEND")
            self.action_started = None

    def probe_cut(self):
        a = self.contract
        self.writer.assert_owner()
        with self.lock:
            if (
                self.close_requested is None
                or self.failure
                or self.cut is not None
                or self.owner_busy
                or self.occupied
            ):
                return
            with self.co.safety:
                if (
                    self.co.slots
                    or self.co.safety_barriers
                    or self.co.begin_in_progress
                    or self.co.mutation.locked()
                    or self.co.ap_persisted != self.co.ap_revision
                    or self.co.last_ticket != self.co.finalized_ticket
                ):
                    return
                if not self.writer.mailbox.empty():
                    return
                self.co.ap_cut_granted = True
                self.cut = dict(
                    campaign_start_sha256=self.log.start_hash,
                    profile_sha256=a.digest(self.co.profile),
                    segment_id=self.log.segment,
                    epoch_id=self.log.epoch,
                    at_mono_ns=self.clock.now_ns(),
                    last_prior_acquisition_seq=self.reserved,
                    prior_acquisition_head_sha256=self.head,
                    prior_association_head_sha256=self.association,
                    prefix_last_event_seq=self.log.seq,
                    prefix_last_event_sha256=self.log.last_hash,
                    last_witness_reopened_mono_ns=self.last_witness_reopened,
                    resource_revision=self.co.ap_revision,
                )
            self.condition.notify_all()

    def close(self):
        a = self.contract
        if self.closed:
            return self.close_body
        if self.close_failed:
            raise SamplingFailure("DRAIN_EXPIRED")
        if self.close_requested is None:
            self.close_requested = self.clock.now_ns()
            self.close_end = time.monotonic() + min(5, self.writer.remaining_seconds())
        self.writer.wake.set()
        end = self.close_end
        while True:
            self.health()
            if self.writer.failed.is_set():
                raise SamplingFailure("WRITE_UNCERTAIN")
            with self.lock:
                ready = (
                    self.failure is not None and not self.occupied
                ) or self.final_ack is not None
            if ready:
                break
            if self.failure and any(x == 1 for x in self.states):
                break
            if time.monotonic() >= end:
                self.close_failed = True
                self.fail("DRAIN_EXPIRED", "DRAIN")
                raise SamplingFailure("DRAIN_EXPIRED")
            self.writer.wake.set()
            time.sleep(0.001)
        self.stop.set()
        if self.thread is not None:
            self.thread.join(max(0, end - time.monotonic()))
        if self.thread is not None and self.thread.is_alive():
            raise SamplingFailure("DRAIN_EXPIRED")
        if self.failure and not self.fault_written:
            self.log.event(
                "SAMPLING_FAULT",
                dict(
                    code=self.failure,
                    at_mono_ns=self.clock.now_ns(),
                    stage=self.failure_stage,
                    reserved_seq=self.reserved or None,
                    trigger_sample_event_seq=None,
                ),
                closure=True,
            )
            self.fault_written = True
        exact = count
        body = dict(
            policy_sha256=a.POLICY_SHA,
            seed_sha256=self.seed,
            close_requested_mono_ns=self.close_requested,
            producer_closed_mono_ns=self.producer_closed,
            cut_mono_ns=self.cut["at_mono_ns"] if self.cut else None,
            final_acquisition_seq=self.final_seq,
            final_observed_mono_ns=self.final_observed,
            last_reserved_seq=exact(self.reserved),
            acquired=exact(self.acquired),
            appended=exact(self.appended),
            acknowledged=exact(self.acknowledged),
            witnessed=exact(self.witnessed),
            acquisition_head_sha256=self.head,
            association_head_sha256=self.association,
            failure=self.failure,
            result="INCOMPLETE" if self.failure else "COMPLETE",
        )
        self.log.event("SAMPLING_CLOSE", body, closure=True)
        if time.monotonic() > end:
            self.fail("DRAIN_EXPIRED", "DRAIN")
            raise SamplingFailure("DRAIN_EXPIRED")
        self.closed = True
        self.close_body = body
        return body


def inspect(factory, profile, start, *, maximum_segments, contract=a):
    """Fresh streaming validation. Revision cache is disposable and capped512.

    A rare older/future revision uses a fresh original pass, never a campaign
    cache. Each invocation belongs to one mandatory validation stage.
    """
    a = contract
    results = []
    context = None
    previous = None
    seq = 0
    epoch = None
    mono = 0
    revision_key = None
    revision_rows = {}

    def revision(segment, r):
        # Disposable, source-fresh bounded join: at most512 revisions. One fresh
        # traversal per511-revision block, not per observation. Acquisition
        # revisions are checked monotone below; no cross-validation-stage cache.
        nonlocal revision_key, revision_rows
        key = (segment, r // 511)
        if key != revision_key:
            low = key[1] * 511
            rows = {}
            for e in factory():
                a.validate(e, a.EVENT)
                if e["segment_id"] != segment:
                    continue
                if e["kind"] == "SAMPLING_OPEN" and low == 0:
                    rows[0] = (e["body"]["anchor_mono_ns"], e["body"]["baseline"])
                if e["kind"] == "RESOURCE" and e["body"]["mutation"]:
                    b = e["body"]
                    v = b["state_revision"]
                    if low <= v <= low + 511:
                        rows[v] = (
                            b["mutation_mono_ns"],
                            {k: b[k] for k in a.TYPES["HardState"]},
                        )
            a.require(len(rows) <= 512)
            revision_key, revision_rows = key, rows
        a.require(r in revision_rows)
        return revision_rows[r], revision_rows.get(r + 1, (None, None))[0]

    def finish(s):
        close = s["close"]
        known = close is not None
        n = s["n"]
        fault = s["fault"]
        complete = (
            known
            and close["result"] == "COMPLETE"
            and fault is None
            and s["pending"] is None
            and s["final"] is not None
            and s["gaps"] == 0
            and s["lag"] <= 500_000_000
        )
        if close:
            a.require(
                close["policy_sha256"] == a.POLICY_SHA
                and close["seed_sha256"] == s["seed"]
            )
            values = [
                close[k]["value"]
                for k in (
                    "last_reserved_seq",
                    "acquired",
                    "appended",
                    "acknowledged",
                    "witnessed",
                )
            ]
            complete = complete and values == [n] * 5
            a.require(
                close["acquisition_head_sha256"] == s["head"]
                and close["association_head_sha256"] == s["assoc"]
            )
            if close["result"] == "COMPLETE":
                a.require(complete and close["failure"] is None)
                a.require(
                    close["close_requested_mono_ns"]
                    <= close["cut_mono_ns"]
                    <= close["final_observed_mono_ns"]
                    <= s["close_header"]
                    and s["close_header"] - close["close_requested_mono_ns"]
                    < 5_000_000_000
                )
                final = s["final"]
                cut = final["cut"]
                a.require(
                    close["final_acquisition_seq"] == n
                    and close["final_observed_mono_ns"] == final["observed_mono_ns"]
                    and close["cut_mono_ns"] == cut["at_mono_ns"]
                )
                a.require(
                    final["acquire_exit_ns"]
                    <= close["producer_closed_mono_ns"]
                    <= s["final_header"]
                )
            else:
                complete = False
        # Unknown volatile observations cannot be inferred as zero/exact total.
        exact = known and all(
            close[k]["value"] == n
            for k in (
                "last_reserved_seq",
                "acquired",
                "appended",
                "acknowledged",
                "witnessed",
            )
        )
        lower = count(n) if exact else {"value": None, "confirmed_min": n}
        summary = dict(
            policy_sha256=a.POLICY_SHA,
            seed_sha256=s["seed"],
            open_event_seq=s["open_seq"],
            close_event_seq=s["close_seq"],
            anchor_mono_ns=s["anchor"],
            end_observed_mono_ns=s["final"]["observed_mono_ns"] if s["final"] else None,
            last_reserved_seq=lower.copy(),
            acquired=lower.copy(),
            appended=lower.copy(),
            acknowledged=(
                lower.copy()
                if s["pending"] is None
                else {"value": None, "confirmed_min": n - 1}
            ),
            witnessed=(
                lower.copy()
                if s["pending"] is None
                else {"value": None, "confirmed_min": n - 1}
            ),
            reopened=(
                lower.copy()
                if s["pending"] is None
                else {"value": None, "confirmed_min": n - 1}
            ),
            maximum_gap_ns=s["maxgap"],
            gap_count=count(s["gaps"])
            if known
            else {"value": None, "confirmed_min": s["gaps"]},
            maximum_ack_age_ns=s["lag"],
            missing_observation_count=count(0)
            if exact
            else {"value": None, "confirmed_min": 0},
            missing_ack_count=count(0)
            if exact and s["pending"] is None
            else {"value": None, "confirmed_min": int(s["pending"] is not None)},
            maximum_outstanding_count=s["peak"] if exact else None,
            maximum_outstanding_bytes=s["peak"] * 4096 if exact else None,
            acquisition_head_sha256=s["head"],
            association_head_sha256=s["assoc"],
            failure=fault or (None if complete else "MISSING_TERMINAL"),
            complete=bool(complete),
        )
        a.validate_type(summary, "SamplingSummary")
        return summary

    for event in factory():
        a.validate(event, a.EVENT)
        a.require(
            event["campaign_start_sha256"] == a.digest(start)
            and event["seq"] == seq + 1
            and event["previous_event_sha256"] == previous
        )
        if event["epoch_id"] == epoch:
            a.require(event["mono_ns"] >= mono)
        else:
            a.require(event["kind"] == "SEGMENT_OPEN")
        kind, b = event["kind"], event["body"]
        header_previous = previous
        if kind == "SEGMENT_OPEN":
            if context is not None:
                results.append(finish(context))
            a.require(len(results) < maximum_segments)
            context = dict(
                segment=event["segment_id"],
                epoch=event["epoch_id"],
                anchor=event["mono_ns"],
                anchor_seq=event["seq"],
                anchor_sha=a.digest(event),
                seed=None,
                open_seq=None,
                head=None,
                assoc=None,
                n=0,
                pending=None,
                last_obs=event["mono_ns"],
                maxgap=0,
                gaps=0,
                lag=0,
                peak=0,
                close=None,
                close_seq=None,
                final=None,
                final_header=None,
                fault=None,
                revision=0,
                hard=None,
                cache=deque(maxlen=512),
                last_sample_revision=0,
                last_ack_header=None,
                ack_headers=deque(maxlen=16),
                close_header=None,
            )
        s = context
        a.require(s is not None and event["segment_id"] == s["segment"])
        if s["pending"] is not None:
            a.require(kind == "SAMPLE_ACK")
        if kind == "SAMPLING_OPEN":
            a.require(s["open_seq"] is None and s["close"] is None)
            seed = a.digest(
                dict(
                    schema_version=a.SEED,
                    campaign_start_sha256=a.digest(start),
                    profile_sha256=a.digest(profile),
                    segment_id=s["segment"],
                    epoch_id=s["epoch"],
                )
            )
            a.require(
                b["seed_sha256"] == seed
                and b["policy_sha256"] == a.POLICY_SHA
                and b["anchor_event_seq"] == s["anchor_seq"]
                and b["anchor_event_sha256"] == s["anchor_sha"]
                and b["anchor_mono_ns"] == s["anchor"]
            )
            s.update(
                seed=seed,
                head=seed,
                assoc=seed,
                open_seq=event["seq"],
                hard=b["baseline"],
            )
            s["cache"].append((0, s["anchor"], b["baseline"]))
        elif kind == "RESOURCE":
            a.require(s["open_seq"] is not None and s["close"] is None)
            state = {k: b[k] for k in a.TYPES["HardState"]}
            if b["mutation"]:
                a.require(
                    state != s["hard"]
                    and b["state_revision"] == s["revision"] + 1
                    and b["mutation_mono_ns"] is not None
                    and b["mutation_mono_ns"]
                    <= b["observed_mono_ns"]
                    <= event["mono_ns"]
                )
                s["revision"] += 1
                s["hard"] = state
                s["cache"].append((s["revision"], b["mutation_mono_ns"], state))
            else:
                a.require(
                    b["mutation_mono_ns"] is None
                    and b["state_revision"] == s["revision"]
                    and state == s["hard"]
                )
        elif kind == "RESOURCE_SAMPLE":
            a.require(
                s["open_seq"] is not None and s["close"] is None and s["final"] is None
            )
            v = b["observation"]
            a.validate(v, a.OBSERVATION)
            h = a.digest(v)
            a.require(
                v["occupied_count_after_reserve"]
                >= 1
                + sum(header >= v["acquire_enter_ns"] for header in s["ack_headers"])
            )
            a.require(
                b["observation_sha256"] == h
                and v["campaign_start_sha256"] == a.digest(start)
                and v["segment_id"] == s["segment"]
                and v["epoch_id"] == s["epoch"]
                and v["acquisition_seq"] == s["n"] + 1
                and v["previous_observation_sha256"] == s["head"]
                and v["acquire_exit_ns"] <= event["mono_ns"]
            )
            a.require(v["resource_revision"] >= s["last_sample_revision"])
            s["last_sample_revision"] = v["resource_revision"]
            found, later = revision(s["segment"], v["resource_revision"])
            a.require(
                v["state"] == found[1]
                and found[0] <= v["observed_mono_ns"]
                and (later is None or v["observed_mono_ns"] <= later)
            )
            gap = v["observed_mono_ns"] - s["last_obs"]
            s["maxgap"] = max(s["maxgap"], gap)
            s["gaps"] += int(not 0 <= gap <= 100_000_000)
            s["last_obs"] = v["observed_mono_ns"]
            s["peak"] = max(s["peak"], v["occupied_count_after_reserve"])
            if v["role"] == "FINAL":
                cut = v["cut"]
                a.require(
                    cut["campaign_start_sha256"] == a.digest(start)
                    and cut["profile_sha256"] == a.digest(profile)
                    and cut["segment_id"] == s["segment"]
                    and cut["epoch_id"] == s["epoch"]
                    and cut["prefix_last_event_seq"] == event["seq"] - 1
                    and cut["prefix_last_event_sha256"] == header_previous
                    and cut["last_prior_acquisition_seq"] == s["n"]
                    and cut["prior_acquisition_head_sha256"] == s["head"]
                    and cut["prior_association_head_sha256"] == s["assoc"]
                    and cut["resource_revision"] == v["resource_revision"]
                    and cut["at_mono_ns"] <= v["acquire_enter_ns"]
                )
                r = cut["last_witness_reopened_mono_ns"]
                a.require((r is None) == (s["n"] == 0))
                if r is not None:
                    a.require(s["last_ack_header"] <= r <= cut["at_mono_ns"])
                s["final"] = v
                s["final_header"] = event["mono_ns"]
            s["head"] = h
            s["pending"] = (event, v)
            s["n"] += 1
        elif kind == "SAMPLE_ACK":
            a.require(s["pending"] is not None)
            sample, v = s["pending"]
            a.require(
                b["acquisition_seq"] == v["acquisition_seq"]
                and b["observation_sha256"] == a.digest(v)
                and b["sample_event_seq"] == sample["seq"] == event["seq"] - 1
                and b["sample_event_sha256"] == a.digest(sample) == header_previous
                and sample["mono_ns"] <= b["event_ack_mono_ns"] <= event["mono_ns"]
            )
            s["lag"] = max(s["lag"], b["event_ack_mono_ns"] - v["observed_mono_ns"])
            s["assoc"] = a.digest(
                dict(
                    previous_sha256=s["assoc"],
                    acquisition_seq=v["acquisition_seq"],
                    observation_sha256=a.digest(v),
                    sample_event_seq=sample["seq"],
                    sample_event_sha256=a.digest(sample),
                    ack_event_seq=event["seq"],
                    ack_event_sha256=a.digest(event),
                )
            )
            s["pending"] = None
            s["last_ack_header"] = event["mono_ns"]
            s["ack_headers"].append(event["mono_ns"])
        elif kind == "SAMPLING_FAULT":
            a.require(s["open_seq"] is not None and s["fault"] is None)
            s["fault"] = b["code"]
            if s["close"] is not None:
                a.require(s["close"]["result"] != "COMPLETE")
        elif kind == "SAMPLING_CLOSE":
            a.require(s["open_seq"] is not None and s["close"] is None)
            s["close"] = b
            s["close_seq"] = event["seq"]
            s["close_header"] = event["mono_ns"]
        elif kind in (
            "BLOCK_CLOSED",
            "SEGMENT_CLOSE",
            *getattr(a, "POST_SAMPLING_EVENT_KINDS", ()),
        ):
            a.require(s["close"] is not None)
        elif s["final"] is not None:
            a.require(False)
        previous = a.digest(event)
        seq = event["seq"]
        mono = event["mono_ns"]
        epoch = event["epoch_id"]
    if context is not None:
        a.require(context["open_seq"] is not None)
        results.append(finish(context))
    return results

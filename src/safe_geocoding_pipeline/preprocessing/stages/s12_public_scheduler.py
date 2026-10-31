"""Bounded O-r2 coordinator. Transports, clocks and gates are explicit inputs.

There is no real-service adapter, credential reader or automatic authorization.
The writer owns filesystem transactions; the coordinator owns all admissions.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from . import s12_operations as v1
from . import s12_public_journal as journal
from . import s12_public_operations as o
from . import s12_retrieval_contract as c
from . import s12_transport as transport


class Clock(Protocol):
    def now_ns(self) -> int: ...
    def utc(self) -> str: ...
    def wait_until(self, ns: int) -> None: ...


class Monitor(Protocol):
    def before_dispatch(self) -> None: ...
    def before_response(
        self, work: dict[str, Any], capture: transport.Capture
    ) -> None: ...
    def accept(self, receipt_sha256: str, *, closure: bool) -> int:
        """Verify actual evidence; return acquired monotonic ns, never fake it."""


@dataclass
class Pending:
    work: dict[str, Any]
    target: bytes = field(repr=False)
    attempt: int
    due_ns: int
    monitor: bool = False


@dataclass
class Slot:
    pending: Pending
    begin_hash: str
    started_ns: int | None = None
    committed_ns: int | None = None
    emitted_ns: int | None = None
    ticket: int | None = None
    completed_ns: int | None = None
    writer_enqueued_ns: int | None = None
    capture: transport.Capture | None = field(default=None, repr=False)
    transport_hash: str | None = None
    connection: bool = True

    @property
    def key(self) -> tuple[int, int]:
        return self.pending.work["work_id"], self.pending.attempt

    def identity(self) -> dict[str, int]:
        return {"work_id": self.key[0], "attempt": self.key[1]}


class Coordinator:
    def __init__(
        self,
        profile: dict[str, Any],
        plan: dict[str, Any],
        start: dict[str, Any],
        *,
        authority: o.Authority,
        clock: Clock,
        root: Path,
        block_id: int,
        segment_authority: str,
        writer_exclusion_evidence: str,
        epoch: str,
        free_bytes: Callable[[], int],
        monitor: Monitor | None = None,
        predecessor: Path | None = None,
        rebase: dict[str, Any] | None = None,
        contract: Any = o,
        segment_body: dict[str, Any] | None = None,
        diagnostics: Any = None,
    ):
        self.failures = diagnostics
        self.contract = contract
        self.contract.verify_authorities(profile, plan, start, authority)
        self.contract.uint(block_id, True)
        self.contract.require(block_id <= len(plan["blocks"]))
        self.profile, self.plan, self.start = profile, plan, start
        self.block = plan["blocks"][block_id - 1]
        self.state_id = self.block["state_id"]
        self.clock, self.authority, self.free_bytes, self.monitor = (
            clock,
            authority,
            free_bytes,
            monitor,
        )
        self.monitored = profile["monitoring"]["mode"] == "FROZEN_V1"
        self.contract.require(self.monitored == (monitor is not None))
        self.safety = threading.RLock()
        self.emission = threading.Lock()
        self.mutation = threading.Lock()
        self.wake = threading.Event()
        self.state = "PREPARED"
        self.stop_reason: str | None = None
        self.primary_reason: str | None = None
        self.pending: list[Pending] = []
        self.slots: dict[tuple[int, int], Slot] = {}
        self.begin_in_progress = False
        self.safety_barriers = 0
        self.next_start_ns = self.next_emit_ns = clock.now_ns()
        self.last_start_ns = self.last_emit_end_ns = 0
        self.cooldown_until = 0
        self.cooldown_delay_ms = 0
        self.consecutive = 0
        self.recent: deque[tuple[int, bool, int]] = deque(maxlen=20)
        self.overloads: deque[tuple[int, tuple[int, int]]] = deque()
        self.signalled: set[tuple[int, int]] = set()
        # Safety latching never waits for this separate persistence turnstile.
        # At most one signal per resident slot can wait here.
        self.signal_order = threading.Condition()
        self.signal_issued = self.signal_persisted = 0
        self.last_ticket = self.finalized_ticket = 0
        self.c = self.a = 0
        self.verified_ns: int | None = None
        self.charged = {"DATA": 0, "SERVICE_CONTROL": 0}
        self.block_charged = {"DATA": 0, "SERVICE_CONTROL": 0}
        self.opened_ns = clock.now_ns()
        self.prior_active_ms = 0
        self.prior_block_ms = 0
        self.measurement_failed = False
        self.pause_pending = False
        self.last_sample_ns = self.opened_ns
        # One bounded periodic-sample slot, separate from result/mutation slots.
        # Its owner may wait for the sole writer, never with safety held.
        self.sample_slot = threading.Lock()
        self.sample_condition = threading.Condition()
        self.sample_busy = False
        self.coordinator_thread = threading.get_ident()
        self.sample_stop = threading.Event()
        self.sample_thread: threading.Thread | None = None
        self.sample_join_failed = False
        # Supplementary fixed-size diagnostics; never authority for sampling
        # completeness. Each cell is [count, total_ns, max_ns], saturated uint64.
        self.sample_metrics_lock = threading.Lock()
        self.sample_metrics = {
            name: [0, 0, 0]
            for name in (
                "wake_lateness",
                "slot_busy",
                "resource_observation",
                "safety_wait",
                "persistence_ack",
                "overdue_after_ack",
            )
        }
        self.resources = profile["resources"]
        # The public driver supplies the source-reconciled ascending-size gate.
        # A bare capability coordinator cannot silently omit that barrier.
        self.size_ready: Callable[[Pending], bool] = lambda _: (
            plan["experiment_kind"] != "CAPABILITY"
        )
        # Closure reserve is deterministic metadata accounting, not a live rate.
        closure_events = (
            12 * max(s["admitted_operations"] for s in profile["states"]) + 8
        )
        authority.require(
            "segment_open", segment_authority, {"start": start, "block": self.block}
        )
        self.contract.validate_type(writer_exclusion_evidence, "D")
        authority.require(
            "writer_exclusion",
            writer_exclusion_evidence,
            {"start": start, "block": self.block},
        )
        authority.require(
            "runtime_preflight",
            start["initial_workload_authority_sha256"],
            {"profile": profile, "plan": plan, "start": start},
        )
        self.writer = journal.Writer(
            root, self.capacity, self.resources["writer_guard_ms"], self.audit_failed
        )
        self.writer.failures = diagnostics
        self.contract.require((predecessor is None) == (rebase is None))
        self.journal = journal.Journal(
            self.writer,
            start,
            clock,
            event_budget=plan["budgets"]["event_count"],
            storage_budget=plan["budgets"]["storage_bytes"],
            closure_events=closure_events,
            predecessor=predecessor,
            contract=contract,
        )
        self.journal.block_start_seq = self.journal.seq
        self.journal.block_byte_budget = self.block["budget"]["storage_bytes"]
        self.journal.block_event_budget = self.block["budget"]["event_count"]
        if predecessor is not None:
            from . import s12_storage as io

            node = predecessor
            while node is not None:
                prior = self.contract.parse(
                    io.read(node / "snapshot.json"), self.contract.SNAPSHOT
                )
                if prior["controller"]["block_id"] == block_id:
                    self.journal.prior_block_bytes += journal.tree_bytes(node)
                node = journal.predecessor_root(node)
            current_block = None
            for event in journal.read_events(
                predecessor, self.contract.digest(start), contract=contract
            ):
                if event["kind"] == "SEGMENT_OPEN":
                    current_block = event["body"]["block_id"]
                if current_block == block_id:
                    self.journal.prior_block_events += 1
        if rebase is not None:
            previous = rebase["snapshot"]["controller"]
            self.charged = {
                "DATA": previous["charged_data_attempts"],
                "SERVICE_CONTROL": previous["charged_control_attempts"],
            }
            if block_id == previous["block_id"]:
                self.state_id = rebase["state_id"]
                self.block_charged = rebase["block_charged"].copy()
            self.cooldown_delay_ms = rebase["cooldown_delay_ms"]
            self.consecutive = rebase["consecutive_retryable"]
            self.recent = deque(
                (
                    (x["ticket"], x["retryable"], x["elapsed_ms"])
                    for x in rebase["recent"]
                ),
                maxlen=20,
            )
            self.last_ticket = self.finalized_ticket = previous["last_ticket"]
            self.prior_active_ms = previous["active_duration_ms"]
            self.prior_block_ms = rebase["block_durations_ms"].get(block_id, 0)
        self.journal.open_segment(
            self.journal.segment + 1,
            epoch,
            {
                **(segment_body or {}),
                "authority_sha256": segment_authority,
                "predecessor_snapshot_sha256": self.contract.digest(rebase["snapshot"])
                if rebase
                else None,
                "writer_exclusion_evidence_sha256": writer_exclusion_evidence,
                "block_id": block_id,
                "state_id": self.state_id,
            },
        )
        # The durable SEGMENT_OPEN timestamp follows all gates and any delayed
        # journal opening. It is also the epoch used by deterministic replay.
        self.opened_ns = self.last_sample_ns = self.journal.last_mono
        if rebase is not None:
            self.next_start_ns = self.next_emit_ns = self.contract.checked(
                self.opened_ns + self.spacing
            )
            self.cooldown_until = self.contract.checked(
                self.opened_ns + self.cooldown_delay_ms * 1_000_000
            )
            self.overloads = deque(
                (self.opened_ns, (entry["work_id"], entry["attempt"]))
                for entry in rebase["overload_carry"]
            )
        self.state = "VERIFYING" if self.monitored else "RUNNING"
        if rebase is not None and self.cooldown_until > clock.now_ns():
            self.state = "COOLDOWN"
            self.journal.event(
                "COOLDOWN",
                {"until_mono_ns": self.cooldown_until, **rebase["cooldown_trigger"]},
            )
        self.resource("STATE_CHANGE")

    @property
    def selected(self) -> dict[str, Any]:
        return self.profile["states"][self.state_id - 1]

    @property
    def capacity(self) -> int:
        return self.selected["admitted_operations"]

    @property
    def spacing(self) -> int:
        return self.contract.interval(self.selected["rate"])

    def audit_failed(self) -> None:
        with self.safety:
            self.state = "RECOVERY_BLOCKED"
            if self.stop_reason is None:
                self.stop_reason = "AUDIT_IO"
            self.wake.set()

    def terminal(self, why: str, primary: str | None = None) -> None:
        with self.safety:
            if self.stop_reason is None:
                self.stop_reason = why
                self.primary_reason = primary
                self.state = (
                    "QUARANTINED"
                    if why in ("DRIFT", "IDENTITY_STALE", "PRIVACY")
                    else "STOPPED"
                )
            self.safety_barriers += 1
            self.wake.set()
        try:
            self.journal.event(
                "STOP",
                {"why": why, "primary_reason": primary, "trigger_event_seq": None},
                closure=True,
            )
        finally:
            with self.safety:
                self.safety_barriers -= 1

    @property
    def sample_lead_ns(self) -> int:
        # Collection starts halfway through the selected maximum gap. This is
        # scheduling headroom, not a tolerance or a substituted observation time.
        return max(1, self.profile["resource_sample_period_ms"] * 1_000_000 // 2)

    def next_wakeup_ns(self, *deadlines: int) -> int:
        now = self.clock.now_ns()
        with self.safety:
            sample_due = self.last_sample_ns + self.sample_lead_ns
        # A busy sample slot cannot create a zero-delay spin loop. The sampler
        # continues independently while the coordinator is blocked on I/O.
        if sample_due <= now:
            sample_due = now + self.sample_lead_ns
        return min(
            sample_due,
            now + self.resources["scheduler_guard_ms"] * 1_000_000,
            *(due for due in deadlines if due > now),
        )

    def sample_metric(self, name: str, elapsed_ns: int = 0) -> None:
        # Static names only, no paths, exception text, request data or event list.
        with self.sample_metrics_lock:
            cell = self.sample_metrics[name]
            value = max(0, elapsed_ns)
            cell[:] = (
                min(2**64 - 1, cell[0] + 1),
                min(2**64 - 1, cell[1] + value),
                min(2**64 - 1, max(cell[2], value)),
            )

    def sampling_snapshot(self) -> dict:
        with self.sample_metrics_lock:
            return {name: list(cell) for name, cell in self.sample_metrics.items()}

    def sampler_wakeup_ns(self, collected: bool) -> int:
        # A successful collector released the sample slot. If acknowledgement
        # consumed the headroom, collect again immediately; do not add another
        # idle guard interval. Busy/unavailable slots retain bounded polling.
        if collected:
            now = self.clock.now_ns()
            with self.safety:
                due = self.last_sample_ns + self.sample_lead_ns
            if due < now:
                self.sample_metric("overdue_after_ack", now - due)
            return max(now, due)
        return self.next_wakeup_ns()

    def sample_if_due(self) -> bool:
        if self.sample_stop.is_set() or self.writer.failed.is_set():
            return False
        with self.sample_condition:
            if not self.sample_slot.acquire(blocking=False):
                self.sample_metric("slot_busy")
                return False
            self.sample_busy = True
        try:
            if (
                self.sample_stop.is_set()
                or self.writer.failed.is_set()
                or self.clock.now_ns() < self.last_sample_ns + self.sample_lead_ns
            ):
                return False
            # Periodic work cannot spend the reserved closure tail. Other
            # producers still face the writer's exact event/storage checks.
            if self.journal.normal_event_headroom() <= self.journal.closure_events:
                if not self.stop_reason:
                    self.terminal("BUDGET")
                return False
            self._resource("PERIODIC", cancel_periodic=True)
            return True
        finally:
            with self.sample_condition:
                self.sample_slot.release()
                self.sample_busy = False
                self.sample_condition.notify_all()

    def yield_to_sample(self, check: Callable[[], None]) -> None:
        """Coordinator-only comparison safe point, never another sample owner.

        Keep CPU-intensive derivation out of an outstanding sample's writer
        action. Wait time remains inside the original cumulative budget. The
        condition never transfers/releases the sample slot or cancels I/O.
        """
        self.contract.require(
            threading.get_ident() == self.coordinator_thread
            and not self.safety._is_owned()
            and not self.mutation.locked()
        )
        check()
        deadline = time.monotonic() + min(
            self.resources["writer_guard_ms"] / 1000,
            self.writer.remaining_seconds(),
        )
        with self.sample_condition:
            while self.sample_busy:
                check()
                if self.writer.failed.is_set():
                    raise OSError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.writer.failed.set()
                    self.audit_failed()
                    raise TimeoutError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
                self.sample_condition.wait(
                    min(remaining, self.resources["scheduler_guard_ms"] / 1000)
                )
        check()
        if self.writer.failed.is_set():
            raise OSError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")

    def start_sampling(self) -> None:
        self.contract.require(
            self.sample_thread is None and not self.sample_stop.is_set()
        )

        def sample() -> None:
            try:
                while not self.sample_stop.is_set() and not self.writer.failed.is_set():
                    collected = self.sample_if_due()
                    wake = self.sampler_wakeup_ns(collected)
                    if not self.sample_stop.wait(
                        max(0, wake - self.clock.now_ns()) / 1e9
                    ):
                        self.sample_metric("wake_lateness", self.clock.now_ns() - wake)
            except BaseException as error:
                if self.failures is not None:
                    self.failures.record("SAMPLER", error, writer=self.writer)
                # No abandoned sampler may leave admission open or create a
                # clean report. Do not attempt a second writer/recovery path.
                self.audit_failed()
                self.writer.failed.set()

        self.sample_thread = threading.Thread(
            target=sample, name="stage12-public-sampler", daemon=True
        )
        self.sample_thread.start()

    def stop_sampling(self) -> bool:
        """Join the one sample slot before final PERIODIC/report-prefix capture.

        A stuck observation/write cannot be cancelled into a clean seal. Once
        stop is set, a late free-space observation is discarded before enqueue;
        a submitted writer transaction remains uncertain on guard expiry.
        """
        self.sample_stop.set()
        if self.sample_join_failed:
            return False
        if self.sample_thread is not None:
            self.sample_thread.join(
                min(
                    self.resources["writer_guard_ms"] / 1000,
                    self.writer.remaining_seconds(),
                )
            )
            if self.sample_thread.is_alive():
                self.sample_join_failed = True
                self.audit_failed()
                self.writer.failed.set()
                return False
        return not self.writer.failed.is_set()

    def resource(self, cause: str) -> None:
        if cause == "PERIODIC":
            self.sample_slot.acquire()
            with self.sample_condition:
                self.sample_busy = True
            try:
                self._resource(cause)
            finally:
                with self.sample_condition:
                    self.sample_slot.release()
                    self.sample_busy = False
                    self.sample_condition.notify_all()
        else:
            self._resource(cause)

    def _resource(self, cause: str, *, cancel_periodic: bool = False) -> None:
        # Filesystem sampling cannot hold the immediate stop/emission lock.
        observation_started = self.clock.now_ns() if cause == "PERIODIC" else None
        available = (
            self.free_bytes() if cause in ("PERIODIC", "START_RESERVE") else None
        )
        observation_done = self.clock.now_ns() if cause == "PERIODIC" else None
        if cancel_periodic and (
            self.sample_stop.is_set() or self.writer.failed.is_set()
        ):
            return
        # A periodic observation changes no admission state. It owns its own
        # slot; only hard mutation records hold the admission barrier.
        safety_started = self.clock.now_ns() if cause == "PERIODIC" else None
        with self.safety:
            safety_acquired = self.clock.now_ns() if cause == "PERIODIC" else None
            body = {
                "observed_mono_ns": self.clock.now_ns(),
                "cause": cause,
                "connection_slots": sum(s.connection for s in self.slots.values()),
                "admitted_operations": len(self.slots),
                "pending_count": len(self.pending),
                "pending_bytes": sum(len(p.target) for p in self.pending),
                "reserved_bytes": len(self.slots) * self.contract.RESERVATION,
                "free_allocated_disk_bytes": available,
            }
            if cause != "PERIODIC":
                self.safety_barriers += 1
        if cause == "PERIODIC":
            self.sample_metric(
                "resource_observation", observation_done - observation_started
            )
            self.sample_metric("safety_wait", safety_acquired - safety_started)
        persistence_started = self.clock.now_ns() if cause == "PERIODIC" else None
        try:
            self.journal.event(
                "RESOURCE",
                body,
                # Background collection never spends the reserved closure tail.
                closure=self.stop_reason is not None and not cancel_periodic,
                periodic=cause == "PERIODIC",
            )
        finally:
            if cause == "PERIODIC":
                self.sample_metric(
                    "persistence_ack", self.clock.now_ns() - persistence_started
                )
            with self.safety:
                if cause != "PERIODIC":
                    self.safety_barriers -= 1
        if cause == "PERIODIC":
            with self.safety:
                self.last_sample_ns = body["observed_mono_ns"]

    def can_refill(self, target_bound: int, *, monitor_reserve: int = 0) -> bool:
        """Reserve count AND bytes before advancing/materializing the work stream.

        Resident slots can each return a retry. Their request bytes are already
        inside the slot reservation; leave space to transfer them to the queue.
        The optional priority-monitor reservation is not an allocated request.
        """
        self.contract.uint(target_bound, True)
        self.contract.uint(monitor_reserve)
        with self.safety:
            return (
                self.stop_reason is None
                and len(self.pending) + len(self.slots) + 1 + bool(monitor_reserve)
                <= 2 * self.capacity
                and sum(len(p.target) for p in self.pending)
                + sum(len(s.pending.target) for s in self.slots.values())
                + target_bound
                + monitor_reserve
                <= self.resources["pending_request_bytes"]
            )

    def prepare_closure(self) -> None:
        """After drain, release queued bytes before materializing closure work.

        These are only request caches, not the durable Work/attempt ledger.
        Unbegun work and due retries remain there for clean continuation, with
        no new charge or dispatch. Do not release a live attempt reservation.
        """
        with self.mutation:
            with self.safety:
                self.contract.require(
                    self.monitored
                    and self.stop_reason is None
                    and not self.slots
                    and not self.begin_in_progress
                    and not self.safety_barriers
                    and self.last_ticket == self.finalized_ticket
                )
                self.pending.clear()
                self.state = "DRAINING"
            self.resource("STATE_CHANGE")

    def queue(self, pending: Pending) -> None:
        self.contract.validate_type(pending.work, "Work")
        self.contract.require(
            pending.work["block_id"] == self.block["block_id"]
            and type(pending.target) is bytes
            and 1 <= pending.attempt <= 5
        )
        self.contract.require(
            len(pending.target) <= self.resources["pending_request_bytes"],
            "S12_PUBLIC_SINGLE_REQUEST_TOO_LARGE",
        )
        with self.mutation:
            with self.safety:
                self.contract.require(
                    self.stop_reason is None and len(self.pending) < 2 * self.capacity
                )
                self.contract.require(
                    sum(len(p.target) for p in self.pending) + len(pending.target)
                    <= self.resources["pending_request_bytes"]
                )
                self.contract.require(
                    all(
                        p.work["work_id"] != pending.work["work_id"]
                        for p in self.pending
                    )
                    and all(k[0] != pending.work["work_id"] for k in self.slots)
                )
                self.pending.append(pending)
            self.resource("QUEUE_ADD")

    def _time_gate(self) -> None:
        from datetime import datetime, timedelta

        now = self.clock.now_ns()
        elapsed_ms = (now - self.opened_ns) // 1_000_000
        self.contract.require(
            self.plan["window_start"] <= self.clock.utc() < self.plan["window_end"],
            "S12_PUBLIC_WINDOW_CLOSED",
        )
        self.contract.require(
            datetime.fromisoformat(self.clock.utc())
            + timedelta(milliseconds=self.plan["shutdown_reserve_ms"])
            < datetime.fromisoformat(self.plan["window_end"]),
            "S12_PUBLIC_WINDOW_CLOSED",
        )
        self.contract.require(
            elapsed_ms + self.prior_active_ms + self.plan["shutdown_reserve_ms"]
            < self.plan["budgets"]["active_duration_ms"]
            and elapsed_ms + self.prior_block_ms + self.plan["shutdown_reserve_ms"]
            < self.block["budget"]["active_duration_ms"],
            "S12_PUBLIC_WINDOW_CLOSED",
        )

    def monitoring_due(self) -> bool:
        if not self.monitored:
            return False
        lead = (
            10_000
            + self.resources["scheduler_guard_ms"]
            + self.resources["writer_guard_ms"]
        ) * 1_000_000
        return (
            self.verified_ns is None
            or self.clock.now_ns() >= self.verified_ns + 60_000_000_000 - lead
            or self.c + self.a + 1 > 99
        )

    def _state_allows(self, pending: Pending) -> bool:
        purpose = None
        if pending.work["kind"] == "SERVICE_CONTROL":
            purpose = next(
                r["purpose"]
                for r in self.plan["control_recipes"]
                if r["recipe_id"] == pending.work["recipe_id"]
            )
        return (
            self.state == "RUNNING"
            or (
                self.state == "VERIFYING"
                and pending.monitor
                and purpose == "IDENTITY_REFRESH"
            )
            or (self.state == "DRAINING" and purpose == "IDENTITY_CLOSURE")
        )

    def admit(self, begin: Callable[[Pending], str]) -> Slot | None:
        """One begin-to-start transaction; no permit is reserved in the future."""
        if (
            self.journal.normal_event_headroom() <= self.journal.closure_events
            and not self.stop_reason
        ):
            self.terminal("BUDGET")
            return None
        with self.mutation:
            with self.safety:
                now = self.clock.now_ns()
                if (
                    self.stop_reason
                    or self.begin_in_progress
                    or self.safety_barriers
                    or (self.pause_pending and self.state != "DRAINING")
                    or any(s.ticket is not None for s in self.slots.values())
                ):
                    return None
                if (
                    now < max(self.next_start_ns, self.cooldown_until)
                    or len(self.slots) >= self.capacity
                ):
                    return None
                eligible = [
                    p for p in self.pending if p.due_ns <= now and self._state_allows(p)
                ]
                eligible.sort(
                    key=lambda p: (
                        not p.monitor,
                        p.attempt == 1,
                        p.due_ns,
                        p.work["work_id"],
                    )
                )
                if not eligible:
                    return None
                pending = eligible[0]
                if self.monitored and not pending.monitor:
                    if (
                        self.monitoring_due()
                        or len(
                            [s for s in self.slots.values() if not s.pending.monitor]
                        )
                        >= self.capacity - 1
                    ):
                        return None
                selected = self.selected
            # Evidence and filesystem interfaces may wait: never hold the
            # independent safety latch while calling either one.
            try:
                ready = self.size_ready(pending)
            except BaseException as error:
                if self.failures is not None:
                    self.failures.record(
                        "READINESS",
                        error,
                        work_id=pending.work["work_id"],
                        attempt=pending.attempt,
                        writer=self.writer,
                    )
                raise
            if not ready:
                return None
            if self.monitored and not pending.monitor:
                self.monitor.before_dispatch()
            self._time_gate()
            self.authority.require(
                "dispatch",
                self.start["initial_workload_authority_sha256"],
                {"work": pending.work, "attempt": pending.attempt, "state": selected},
            )
            available = self.free_bytes()
            if self.journal.accounted_bytes is not None:
                self.writer.call(self.journal.verify_storage)
            self.journal.check_storage(
                self.resources["per_attempt_disk_bound_bytes"]
                + self.resources["fixed_campaign_disk_bound_bytes"]
            )
            with self.safety:
                if (
                    self.stop_reason
                    or self.safety_barriers
                    or selected != self.selected
                    or not self._state_allows(pending)
                    or self.clock.now_ns()
                    < max(self.cooldown_until, self.next_start_ns)
                    or any(s.ticket is not None for s in self.slots.values())
                ):
                    return None
                self._time_gate()
                kind = pending.work["kind"]
                budget_key = (
                    "data_attempts" if kind == "DATA" else "control_http_attempts"
                )
                self.contract.require(
                    self.charged[kind] < self.plan["budgets"][budget_key]
                    and self.block_charged[kind] < self.block["budget"][budget_key],
                    "RETRY_BUDGET_EXHAUSTED",
                )
                if kind == "SERVICE_CONTROL":
                    recipe = next(
                        r
                        for r in self.plan["control_recipes"]
                        if r["recipe_id"] == pending.work["recipe_id"]
                    )
                    self.contract.require(
                        pending.attempt <= recipe["max_http_attempts_per_invocation"],
                        "RETRY_BUDGET_EXHAUSTED",
                    )
                remaining = sum(
                    self.plan["budgets"][k]
                    for k in ("data_attempts", "control_http_attempts")
                ) - sum(self.charged.values())
                required_storage = (
                    remaining * self.resources["per_attempt_disk_bound_bytes"]
                    + self.resources["fixed_campaign_disk_bound_bytes"]
                )
                self.contract.require(
                    available >= required_storage, "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED"
                )
                self.begin_in_progress = True
                self.pending.remove(pending)
                slot = Slot(pending, "")
                self.slots[slot.key] = slot
            self.resource("QUEUE_REMOVE")
            self.resource("START_RESERVE")
            try:
                slot.begin_hash = self.writer.cooperative(lambda: begin(pending))
                self.contract.validate_type(slot.begin_hash, "D")
                with self.safety:
                    self.charged[kind] += 1
                    self.block_charged[kind] += 1
                self.journal.event(
                    "BEGIN_DURABLE",
                    {**slot.identity(), "begin_sha256": slot.begin_hash},
                )
            except BaseException:
                self.audit_failed()
                raise
            return slot

    def started(self, slot: Slot, mono_ns: int) -> None:
        with self.safety:
            if self.stop_reason or self.clock.now_ns() < self.cooldown_until:
                self._unknown(slot)
            self.contract.require(
                slot.started_ns is None
                and self.begin_in_progress
                and mono_ns >= self.next_start_ns
            )
            self._time_gate()
            slot.started_ns = mono_ns
            self.last_start_ns = mono_ns
            self.next_start_ns = self.contract.checked(mono_ns + self.spacing)
            self.begin_in_progress = False
            if not slot.pending.monitor:
                self.a += 1
            self.safety_barriers += 1
        try:
            self.journal.event(
                "ATTEMPT_STARTED", {**slot.identity(), "started_mono_ns": mono_ns}
            )
        finally:
            with self.safety:
                self.safety_barriers -= 1
        self.wake.set()

    def _unknown(self, slot: Slot) -> None:
        self.state, self.stop_reason = "RECOVERY_BLOCKED", "UNACCOUNTED_DELIVERY"
        self.wake.set()
        raise transport.DispatchBlocked("UNACCOUNTED_DELIVERY")

    def emit(
        self, slot: Slot, write: Callable[[], None], check_deadline: Callable[[], None]
    ) -> None:
        with self.emission:
            while True:
                if self.monitored and not slot.pending.monitor:
                    self.monitor.before_dispatch()
                with self.safety:
                    if self.stop_reason or self.clock.now_ns() < self.cooldown_until:
                        self._unknown(slot)
                    now = self.clock.now_ns()
                    due = self.next_emit_ns
                    blocked = self.safety_barriers or any(
                        s.ticket is not None for s in self.slots.values()
                    )
                    self.contract.require(
                        slot.started_ns is not None and slot.committed_ns is None
                    )
                    check_deadline()
                    if now - slot.started_ns >= 60_000_000_000:
                        raise c.Stage12Error("TIMEOUT")
                    if now >= due and not blocked:
                        self._time_gate()
                        slot.committed_ns = now
                        break
                if blocked:
                    self.wake.wait(
                        max(0, self.next_wakeup_ns(due) - self.clock.now_ns()) / 1e9
                    )
                    self.wake.clear()
                else:
                    self.clock.wait_until(min(due, self.next_wakeup_ns()))
            self.journal.event(
                "EMIT_COMMITTED",
                {**slot.identity(), "committed_mono_ns": slot.committed_ns},
            )
            entered, returned, result = None, None, "WRITE_FAILED"
            try:
                check_deadline()
                self._time_gate()
                entered = self.clock.now_ns()
                slot.emitted_ns = entered
                write()
                result = "WRITE_RETURNED"
            finally:
                returned = self.clock.now_ns()
                with self.safety:
                    self.last_emit_end_ns = returned
                    self.next_emit_ns = max(
                        self.next_emit_ns,
                        self.contract.checked(returned + self.spacing),
                    )
                if entered is not None:
                    self.journal.event(
                        "EMISSION",
                        {
                            **slot.identity(),
                            "entered_mono_ns": entered,
                            "returned_mono_ns": returned,
                            "result": result,
                        },
                        closure=self.stop_reason is not None,
                    )

    def signal(
        self,
        slot: Slot,
        status: int | None,
        outcome: str,
        reason: str,
        retry: int | None,
    ) -> None:
        signal = None
        breaker = None
        with self.safety:
            now = self.clock.now_ns()
            if slot.key in self.signalled:
                return
            if status in (429, 503):
                self.overloads.append((now, slot.key))
            while self.overloads and self.overloads[0][0] < now - 60_000_000_000:
                self.overloads.popleft()
            if (
                outcome == "TECHNICAL_FAILURE_RETRYABLE"
                and status is not None
                and (status == 429 or status >= 500)
            ):
                signal = "OVERLOAD" if status in (429, 503) else "RETRYABLE_5XX"
                self.cooldown_delay_ms = max(30_000, (retry or 0) * 1000)
                self.cooldown_until = max(
                    self.cooldown_until, now + self.cooldown_delay_ms * 1_000_000
                )
                self.state = "COOLDOWN" if self.stop_reason is None else self.state
                self.measurement_failed = True
            elif outcome in (
                "TECHNICAL_FAILURE_FINAL",
                "CONTRACT_FAILURE",
                "DEPLOYMENT_IDENTITY_FAILURE",
            ):
                signal = (
                    "PRIVACY"
                    if reason == "SECRET_ECHO_DETECTED"
                    else "IDENTITY"
                    if outcome == "DEPLOYMENT_IDENTITY_FAILURE"
                    else "TERMINAL"
                )
                self.state, self.stop_reason = (
                    ("QUARANTINED", "PRIVACY")
                    if signal == "PRIVACY"
                    else ("STOPPED", "TERMINAL")
                )
            if signal:
                self.signalled.add(slot.key)
                self.safety_barriers += 1
                signal_sequence = self.signal_issued
                self.signal_issued += 1
                # Capture this causal transaction before another worker changes
                # the live latch. Persist pairs in the same order as latching.
                cooldown_until = self.cooldown_until
                if len(self.overloads) >= 2:
                    breaker = "OVERLOAD_PRESSURE"
                elif retry is not None and retry > 300:
                    breaker = "RETRY_AFTER_REQUIRES_OWNER_RECOVERY"
                if breaker and self.stop_reason is None:
                    self.state, self.stop_reason = "STOPPED", "BREAKER"
                self.wake.set()
        if signal:
            try:
                with self.signal_order:
                    self.signal_order.wait_for(
                        lambda: self.signal_persisted == signal_sequence
                    )
                    try:
                        self.journal.event(
                            "EARLY_SIGNAL",
                            {
                                **slot.identity(),
                                "signal": signal,
                                "observed_mono_ns": now,
                                "status": status,
                                "retry_after_seconds": retry,
                            },
                            closure=self.stop_reason is not None,
                        )
                        if signal in ("OVERLOAD", "RETRYABLE_5XX"):
                            self.journal.event(
                                "COOLDOWN",
                                {
                                    "until_mono_ns": cooldown_until,
                                    "trigger_work_id": slot.key[0],
                                    "trigger_attempt": slot.key[1],
                                },
                                closure=self.stop_reason is not None,
                            )
                    finally:
                        self.signal_persisted += 1
                        self.signal_order.notify_all()
            finally:
                with self.safety:
                    self.safety_barriers -= 1
            if breaker:
                self.terminal("BREAKER", breaker)

    def completed(
        self,
        slot: Slot,
        capture: transport.Capture,
        transport_hash: str,
        persist_transport: Callable[[], None],
    ) -> None:
        self.signal(
            slot,
            capture.status,
            capture.outcome,
            capture.reason,
            capture.retry_after_seconds,
        )
        if self.monitored:
            try:
                self.monitor.before_response(slot.pending.work, capture)
            except c.Stage12Error:
                self.terminal("IDENTITY_STALE", "IDENTITY_VERIFICATION_STALE")
        with self.safety:
            self.contract.require(slot.ticket is None and slot.started_ns is not None)
            self.last_ticket += 1
            slot.ticket, slot.completed_ns = self.last_ticket, self.clock.now_ns()
            slot.writer_enqueued_ns = slot.completed_ns
            slot.capture, slot.transport_hash, slot.connection = (
                capture,
                transport_hash,
                False,
            )
            if not slot.pending.monitor:
                self.a -= 1
            self.c += 1
        self.writer.call(persist_transport)
        self.journal.event(
            "NETWORK_DONE",
            {
                **slot.identity(),
                "ticket": slot.ticket,
                "completed_mono_ns": slot.completed_ns,
                "elapsed_ms": capture.elapsed_ms,
                "transport_record_sha256": transport_hash,
            },
            closure=self.stop_reason is not None,
        )
        self.resource("CONNECTION_RELEASE")
        self.wake.set()

    def finalize(
        self, slot: Slot, transaction: Callable[[], tuple[dict[str, Any], str]]
    ) -> Pending | None:
        with self.safety:
            self.contract.require(
                slot.ticket == self.finalized_ticket + 1 and slot.capture is not None
            )
            self.safety_barriers += 1
        enqueued = slot.writer_enqueued_ns
        self.contract.require(enqueued is not None)
        times: dict[str, int] = {}

        def commit() -> tuple[dict[str, Any], str]:
            times["started"] = self.clock.now_ns()
            result = transaction()
            times["reopened"] = self.clock.now_ns()
            return result

        terminal, receipt = self.writer.cooperative(commit)
        kind = slot.pending.work["kind"]
        outcome, reason = (
            terminal["outcome"],
            terminal.get("reason_code", terminal.get("reason")),
        )
        final = {"kind": kind, "value": outcome}
        self.contract.validate_type(final, "FinalOutcome")
        self.contract.validate_type(reason, "Reason")
        self.contract.require(outcome != "UNKNOWN_DELIVERY")
        retryable = outcome == "TECHNICAL_FAILURE_RETRYABLE"
        capture = slot.capture
        with self.safety:
            self.consecutive = self.consecutive + 1 if retryable else 0
            self.recent.append((slot.ticket, retryable, capture.elapsed_ms))
            failure = (
                "TERMINAL_FAILURE"
                if outcome in self.contract.FAILURES and not retryable
                else "TECHNICAL_ERROR_PRESSURE"
                if self.consecutive >= 3 or sum(x[1] for x in self.recent) >= 5
                else "OVERLOAD_PRESSURE"
                if len(self.overloads) >= 2
                else "LATENCY_PRESSURE"
                if len(self.recent) == 20
                and sum(x[2] > 30_000 for x in self.recent) >= 10
                else None
            )
        delay = None
        if retryable:
            if slot.key[1] == 5:
                failure = "RETRY_BUDGET_EXHAUSTED"
            else:
                try:
                    delay = v1.retry_delay(
                        bytes.fromhex(slot.pending.work["retry_spacing_key"]),
                        slot.key[1] + 1,
                        capture.retry_after_seconds,
                        v1.Operations(),
                    )
                except c.Stage12Error as error:
                    failure = str(error)
        if failure:
            if self.failures is not None and not retryable:
                self.failures.rejected(reason)
            self.terminal(
                "PRIVACY"
                if reason == "SECRET_ECHO_DETECTED"
                else "BREAKER"
                if retryable
                else "TERMINAL",
                failure,
            )
        self.journal.event(
            "ATTEMPT_FINALIZED",
            {
                **slot.identity(),
                "ticket": slot.ticket,
                "outcome": final,
                "reason": reason,
                "receipt_inventory_sha256": receipt,
                "elapsed_ms": capture.elapsed_ms,
                "status": capture.status,
                "retry_after_seconds": capture.retry_after_seconds,
                "retry_delay_ms": delay,
            },
            closure=self.stop_reason is not None,
        )
        ack = self.clock.now_ns()
        # Drop the last internal payload reference before releasing its memory
        # reservation. Retain only transport metadata needed for retry scheduling.
        slot.capture = None
        capture = replace(capture, payload=None)
        with self.safety:
            self.finalized_ticket = slot.ticket
            del self.slots[slot.key]
            self.signalled.discard(slot.key)
            released = self.clock.now_ns()
        self.journal.event(
            "AUDIT_TIMING",
            {
                **slot.identity(),
                "ticket": slot.ticket,
                "writer_enqueued_ns": enqueued,
                "writer_started_ns": times["started"],
                "receipt_reopened_ns": times["reopened"],
                "finalized_event_ack_ns": ack,
                "reservation_released_ns": released,
            },
            closure=self.stop_reason is not None,
        )
        self.resource("RESERVATION_RELEASE")
        with self.safety:
            self.safety_barriers -= 1
        self.wake.set()
        if slot.pending.monitor and outcome == "CONTROL_SUCCESS":
            self.accept_monitor(
                slot,
                terminal["verification_receipt_sha256"],
                closure=self.state == "DRAINING",
            )
        if retryable and delay is not None and not self.stop_reason:
            return Pending(
                slot.pending.work,
                slot.pending.target,
                slot.key[1] + 1,
                self.clock.now_ns() + delay * 1_000_000,
                slot.pending.monitor,
            )
        return None

    def accept_monitor(self, slot: Slot, receipt: str, *, closure: bool) -> None:
        self.contract.require(self.monitored)
        try:
            recipe = next(
                r
                for r in self.plan["control_recipes"]
                if r["recipe_id"] == slot.pending.work["recipe_id"]
            )
            self.contract.require(
                slot.started_ns is not None
                and self.clock.now_ns() - slot.started_ns
                <= (
                    recipe["max_duration_ms"]
                    + self.resources["scheduler_guard_ms"]
                    + self.resources["writer_guard_ms"]
                )
                * 1_000_000
            )
            acquired = self.monitor.accept(receipt, closure=closure)
            self.contract.require(
                acquired <= self.clock.now_ns() < acquired + 60_000_000_000
            )
        except c.Stage12Error:
            self.terminal("IDENTITY_STALE", "IDENTITY_UNVERIFIABLE")
            return
        with self.safety:
            self.verified_ns = acquired
            self.c = 0
            self.safety_barriers += 1
        self.journal.event(
            "MONITOR_RESULT",
            {
                "work_id": slot.key[0],
                "receipt_sha256": receipt,
                "result": "VERIFIED",
                "acquired_mono_ns": acquired,
                "count_baseline": 0,
                "interval_closed": closure,
            },
        )
        if not self.stop_reason and not closure:
            self.state = "RUNNING"
        self.resource("STATE_CHANGE")
        with self.safety:
            self.safety_barriers -= 1

    def tick(self) -> None:
        now = self.clock.now_ns()
        if self.stop_reason:
            return
        # Stop while the bounded closure tail is still writable. Never spend it
        # on another begin or rely on a failed event write to notice exhaustion.
        if self.journal.normal_event_headroom() <= self.journal.closure_events:
            self.terminal("BUDGET")
            return
        if len(self.pending) > 2 * self.capacity:
            self.terminal("RESOURCE")
            return
        if self.monitored and self.verified_ns is not None:
            if (
                now >= self.verified_ns + 60_000_000_000
                or self.cooldown_until >= self.verified_ns + 60_000_000_000
            ):
                self.terminal("IDENTITY_STALE", "IDENTITY_VERIFICATION_STALE")
                return
        if self.state == "COOLDOWN" and now >= self.cooldown_until:
            self.state = "VERIFYING" if self.monitoring_due() else "RUNNING"
            self.resource("STATE_CHANGE")
        elif self.state == "RUNNING" and self.monitoring_due():
            self.state = "VERIFYING"
            self.resource("STATE_CHANGE")
        self.sample_if_due()
        try:
            self._time_gate()
        except c.Stage12Error:
            self.terminal("TIME")

    def downshift(self, state_id: int, why: str, basis_seq: int) -> None:
        self.contract.require(
            not self.stop_reason and 0 < basis_seq <= self.journal.seq
        )
        self.authority.require(
            "rate_reduction_basis",
            self.start["initial_workload_authority_sha256"],
            {"state_id": state_id, "why": why, "basis_event_seq": basis_seq},
        )
        with self.safety:
            self.contract.require(
                state_id in self.block["fallback_state_ids"]
                and state_id < self.state_id
            )
            old, spacing = self.state_id, self.spacing
            self.state_id = state_id
            self.next_start_ns = max(
                self.next_start_ns, self.last_start_ns + max(spacing, self.spacing)
            )
            self.next_emit_ns = max(
                self.next_emit_ns, self.last_emit_end_ns + max(spacing, self.spacing)
            )
            self.measurement_failed = True
        self.journal.event(
            "DOWNSHIFT",
            {
                "from_state": old,
                "to_state": state_id,
                "why": why,
                "basis_event_seq": basis_seq,
            },
        )
        self.resource("STATE_CHANGE")

    def hooks(
        self,
        slot: Slot,
        record_hash: Callable[[transport.Capture], str],
        persist_transport: Callable[[], None],
    ) -> transport.TimingHooks:
        coordinator = self

        class Hooks:
            def started(self, mono_ns: int) -> None:
                coordinator.started(slot, mono_ns)

            def emit(
                self, write: Callable[[], None], check_deadline: Callable[[], None]
            ) -> None:
                coordinator.emit(slot, write, check_deadline)

            def signal(
                self, status: int, outcome: str, reason: str, retry_after: int | None
            ) -> None:
                coordinator.signal(slot, status, outcome, reason, retry_after)

            def completed(self, capture: transport.Capture) -> None:
                coordinator.completed(
                    slot, capture, record_hash(capture), persist_transport
                )

        return Hooks()

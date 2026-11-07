"""Single durable writer for O-r2 operational evidence; no scientific seal."""

from __future__ import annotations

import queue
import threading
import hashlib
import json
import os
import stat
from collections.abc import Callable, Iterator
from concurrent.futures import Future
from pathlib import Path
from typing import Any, TypeVar

from . import s12_public_operations as o
from . import s12_retrieval_contract as c
from . import s12_storage as io
from .s12_public_timing import safe_call

T = TypeVar("T")


class Writer:
    """Bounded transaction mailbox, exclusive reservation, one writing thread.

    A failure permanently poisons the writer and invokes the independent stop
    latch. A timeout cannot cancel uncertain filesystem work or allow reuse.
    """

    def __init__(self, root: Path, slots: int, guard_ms: int, stop: Callable[[], None]):
        o.uint(slots, True)
        o.require(slots <= 4)
        o.uint(guard_ms, True)
        io.reserve(root)
        io.write(root / "_WRITER_RESERVED", b"")
        self.root, self.guard_ms, self.stop = root, guard_ms, stop
        # Same total bound: admitted-operation slots, mutation slot, sample slot.
        self.mailbox: queue.Queue[Any] = queue.Queue(maxsize=slots + 2)
        self.periodic: queue.Queue[Any] = queue.Queue(maxsize=1)
        self.mailbox_capacity = threading.BoundedSemaphore(slots + 2)
        self.wake = threading.Event()
        self.failed = threading.Event()
        self.closed = False
        self.submission_lock = threading.Lock()
        self.closure_fence = None
        self.sampling = None
        self.ap_credit = False
        self.ap_active_started = None
        self.failures = None
        self.charge_write: Callable[[Path, int], None] = lambda path, size: None
        self.storage_guard: Callable[[], None] = lambda: None
        self.check_deadline: Callable[[], None] = lambda: None
        self.remaining_seconds: Callable[[], float] = lambda: self.guard_ms / 1000
        # The owner explicitly installs RS1 controls before constructing its
        # writer. Thread-local scopes do not otherwise cross a thread boundary.
        self.allocation_controls = io.current_allocation_controls()
        self.thread = threading.Thread(
            target=self._work, name="stage12-public-writer", daemon=True
        )
        self.thread.start()

    def _work(self) -> None:
        while True:
            self.wake.clear()
            if self.sampling is not None:
                if self._ap_turn():
                    return
                continue
            try:
                self.service_periodic()
            except BaseException:
                # The failed sample Future and stop latch already carry failure.
                # Drain queued transactions as failures instead of abandoning them.
                pass
            try:
                item = self.mailbox.get_nowait()
            except queue.Empty:
                self.wake.wait()
                continue
            if item is None:
                return
            self.mailbox_capacity.release()
            self._execute(item)

    def _ap_turn(self):
        try:
            try:
                item = self.mailbox.get_nowait()
            except queue.Empty:
                item = False
            if item is None:
                if not self.failed.is_set():
                    self.contract_check_empty()
                return True
            if item is not False:
                self.mailbox_capacity.release()
                self.ap_credit = True
                self._execute(item)
                if self.ap_credit and not self.failed.is_set():
                    self.ap_credit = False
                    self._execute_periodic()
            elif not self.failed.is_set():
                self._execute_periodic()
            if not self.failed.is_set():
                self.sampling.probe_cut()
        except BaseException:
            self.failed.set()
            self.stop()
        self.wake.wait(0.001)
        return False

    def _execute_periodic(self):
        # Sole-writer inline turn: no per-observation/pair Future or callback.
        self.ap_active_started = self.sampling.clock.now_ns()
        try:
            self.assert_owner()
            self.check_deadline()
            self.sampling.health()
            with (
                io.cooperative_io(self.publication_checkpoint),
                io.charged_writes(self.charge_write),
                io.allocation_controls(self.allocation_controls),
            ):
                self.sampling_pair()
            self.check_deadline()
            self.storage_guard()
            self.assert_owner()
            self.sampling.health()
        except BaseException as error:
            if self.failures is not None:
                self.failures.record("WRITER_ACTION", error, writer=self)
            self.failed.set()
            self.stop()
            self.sampling.uncertain_traces()
        finally:
            self.ap_active_started = None

    def sampling_pair(self):
        result = self.sampling.service()
        if result:
            self.sampling.pair_return()
            self.check_deadline()
            self.storage_guard()
            self.sampling.after_turn()
        return result

    def contract_check_empty(self):
        o.require(
            self.sampling.closed
            and (
                not self.sampling.occupied
                or (
                    self.sampling.failure
                    and not self.sampling.owner_busy
                    and not any(x in (2, 3, 4) for x in self.sampling.states)
                )
            )
        )

    def _execute(self, item: Any) -> None:
        if self.sampling is not None:
            self.ap_active_started = self.sampling.clock.now_ns()
        action, future, *extra = item
        timing = extra[0] if extra else None
        safe_call(timing, "mark", "writer_entry_ns")
        try:
            o.require(not self.failed.is_set(), "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
            self.check_deadline()
            if self.sampling is not None:
                self.sampling.health()
            with (
                io.cooperative_io(self.publication_checkpoint),
                io.charged_writes(self.charge_write),
                io.allocation_controls(self.allocation_controls),
            ):
                safe_call(timing, "mark", "writer_action_enter_ns")
                result = action()
                safe_call(timing, "mark", "writer_action_return_ns")
            self.check_deadline()
            o.require(not self.failed.is_set(), "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
            self.storage_guard()
            if self.sampling is not None:
                self.sampling.health()
            safe_call(timing, "mark", "post_action_complete_ns")
        except BaseException as error:
            if self.failures is not None:
                self.failures.record("WRITER_ACTION", error, writer=self)
            self.failed.set()
            self.stop()
            if self.sampling is not None:
                self.sampling.uncertain_traces()
            future.set_exception(error)
        else:
            future.set_result(result)
        self.ap_active_started = None

    def service_periodic(self) -> None:
        """Only the writer can drain the one sample slot, at a safe boundary.

        No ordinary transaction is reentrant. An indivisible slow I/O remains
        observable as a late sample; this never fabricates an acquisition time.
        """
        o.require(threading.current_thread() is self.thread)
        if self.sampling is not None:
            self.sampling.health()
            if self.ap_credit:
                self.ap_credit = False
                self.sampling_pair()
            return
        if self.failed.is_set():
            raise OSError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
        try:
            item = self.periodic.get_nowait()
        except queue.Empty:
            return
        self.mailbox_capacity.release()
        self._execute(item)
        if self.failed.is_set():
            # Do not masquerade as a response-validation Stage12Error inside
            # a validator that intentionally classifies contract rejections.
            raise OSError("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")

    def cooperative(self, action: Callable[[], T]) -> T:
        def run() -> T:
            def checkpoint():
                self.check_deadline()
                self.service_periodic()

            with io.cooperative_io(checkpoint):
                return action()

        return self.call(run)

    def submit(
        self, action: Callable[[], T], *, periodic: bool = False, timing=None
    ) -> Future[T]:
        with self.submission_lock:
            if self.closure_fence is not None:
                o.require(
                    threading.get_ident() == self.closure_fence.owner and not periodic,
                    "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                )
            return self._submit(action, periodic=periodic, timing=timing)

    def _submit(
        self, action: Callable[[], T], *, periodic: bool = False, timing=None
    ) -> Future[T]:
        o.require(
            not self.closed and not self.failed.is_set(),
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        )
        future: Future[T] = Future()
        if timing is not None:
            # This observes FINISHED publication, rather than action return.
            # The caller may already be awake; an unobserved milestone stays null.
            future.add_done_callback(
                lambda _: safe_call(timing, "mark", "future_completion_ns")
            )
        acquired = self.mailbox_capacity.acquire(blocking=False)
        try:
            if not acquired:
                raise queue.Full
            safe_call(timing, "mark", "enqueue_ns")
            item = (action, future) if timing is None else (action, future, timing)
            (self.periodic if periodic else self.mailbox).put_nowait(item)
            self.wake.set()
        except queue.Full:
            if acquired:
                self.mailbox_capacity.release()
            self.failed.set()
            self.stop()
            raise c.Stage12Error("PUBLIC_PROBE_EVIDENCE_WRITE_FAILED") from None
        return future

    def publication_checkpoint(self) -> None:
        self.check_deadline()
        # Opt-in only: shared B2/legacy transactions retain their existing
        # cooperative semantics. A late closure action must stop before the
        # next I/O boundary after its caller has poisoned the writer.
        if self.closure_fence is not None:
            o.require(not self.failed.is_set(), "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")

    def freeze_closure(self):
        """Exclude producers, then drain their already submitted actions.

        Called only after operation drain and sampler join/final observation.
        The lock protects queue admission, never disk I/O or waiting.
        """
        fence = ClosureFence(self)
        with self.submission_lock:
            o.require(self.closure_fence is None)
            self.closure_fence = fence
        self.call(self.closure_fence.check)
        return self.closure_fence

    def call(
        self, action: Callable[[], T], *, periodic: bool = False, timing=None
    ) -> T:
        o.require(threading.current_thread() is not self.thread)
        future = None
        try:
            self.check_deadline()
            future = (
                self.submit(action, periodic=periodic)
                if timing is None
                else self.submit(action, periodic=periodic, timing=timing)
            )
            result = future.result(
                timeout=min(self.guard_ms / 1000, self.remaining_seconds())
            )
            safe_call(timing, "mark", "caller_ack_ns")
            self.check_deadline()
            return result
        except BaseException as error:
            safe_call(timing, "mark", "caller_ack_ns")
            safe_call(
                timing,
                "outcome",
                "FAILED" if future is not None and future.done() else "UNCERTAIN",
            )
            if self.failures is not None:
                self.failures.record("WRITER_WAIT", error, writer=self)
            self.failed.set()
            self.stop()
            raise

    def assert_owner(self) -> None:
        o.require(
            threading.current_thread() is self.thread and not self.failed.is_set()
        )

    def release(self, evidence: dict[str, Any], *, segment_seal: bool = False) -> str:
        def write() -> str:
            raw = c.canonical(evidence)
            io.write(self.root / "_WRITER_RELEASED.json", raw)
            o.require(io.read(self.root / "_WRITER_RELEASED.json") == raw)
            if segment_seal:
                io.write(self.root / "_SEGMENT_SEALED", b"")
                o.require(io.read(self.root / "_SEGMENT_SEALED", limit=0) == b"")
            return c.sha(raw).hex()

        result = self.call(write)
        self.closed = True
        self.mailbox.put_nowait(None)
        self.wake.set()
        self.thread.join(timeout=min(self.guard_ms / 1000, self.remaining_seconds()))
        o.require(not self.thread.is_alive(), "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
        return result

    def abort(self) -> None:
        """Stop accepting work without creating a clean release/seal claim."""
        if self.sampling is not None:
            self.failed.set()
            self.sampling.stop.set()
            if (
                self.sampling.thread is not None
                and threading.current_thread() is not self.sampling.thread
            ):
                self.sampling.thread.join(timeout=min(5, self.remaining_seconds()))
        self.closed = True
        try:
            self.mailbox.put_nowait(None)
            self.wake.set()
        except queue.Full:
            return
        self.thread.join(timeout=min(self.guard_ms / 1000, self.remaining_seconds()))


class ClosureFence:
    """Ephemeral ownership/root binding, never evidence-validation authority."""

    def __init__(self, writer):
        self.writer = writer
        self.owner = threading.get_ident()
        self.path = writer.root.resolve()
        info = writer.root.stat(follow_symlinks=False)
        self.identity = (info.st_dev, info.st_ino)

    def check_live(self):
        """Cheap live ownership/health/root checks inside a validation stage.

        Full ancestor/path checks still bracket the stage and existing snapshot
        validation/persist/seal bounds. This grants no content-validation authority.
        """
        writer = self.writer
        writer.check_deadline()
        o.require(
            writer.closure_fence is self
            and not writer.closed
            and not writer.failed.is_set()
            and threading.get_ident() in (self.owner, writer.thread.ident),
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        )
        info = writer.root.stat(follow_symlinks=False)
        o.require(
            stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o700
            and info.st_uid == os.geteuid()
            and (info.st_dev, info.st_ino) == self.identity,
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        )

    def check(self):
        self.check_live()
        io.private_directory(self.writer.root)
        o.require(
            self.writer.root.resolve() == self.path,
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        )
        self.check_live()


class Journal:
    def __init__(
        self,
        writer: Writer,
        start: dict[str, Any],
        clock: Any,
        *,
        event_budget: int,
        storage_budget: int,
        closure_events: int,
        predecessor: Path | None = None,
        contract: Any = o,
    ):
        self.contract = contract
        self.contract.validate(start, self.contract.START)
        for n in (event_budget, storage_budget, closure_events):
            self.contract.uint(n, True)
        self.contract.require(closure_events < event_budget)
        self.writer, self.clock, self.start = writer, clock, start
        self.event_budget, self.storage_budget, self.closure_events = (
            event_budget,
            storage_budget,
            closure_events,
        )
        self.seq = 0
        self.prior_bytes = 0
        self.prior_block_bytes = 0
        self.block_byte_budget = storage_budget
        self.block_event_budget = event_budget
        self.prior_block_events = 0
        self.block_start_seq = 0
        self.last_hash = None
        self.segment = 0
        self.epoch = None
        self.last_mono = 0
        self.segment_closed = True
        self.start_hash = self.contract.digest(start)
        self.ap_budget_lock = threading.RLock()
        self.ap_pending_events = self.ap_pending_bytes = 0
        self.ap_inflight_events = 0
        self.ap_inventory_calls = 0
        self.ap_inventory_limit = 8
        self.accounted_bytes: int | None = None
        self.external_write = None
        self.external_bytes = 0
        self.root_identity = None
        writer.call(lambda: self.write("campaign_start.json", start))
        writer.call(lambda: io.reserve(writer.root / "events"))
        if predecessor is not None:
            previous = self.contract.parse(
                io.read(predecessor / "snapshot.json"), self.contract.SNAPSHOT
            )
            self.contract.require(
                io.read(predecessor / "campaign_start.json") == c.canonical(start)
            )
            self.contract.require(
                io.read(predecessor / "_SEGMENT_SEALED", limit=0) == b""
                and previous["disposition"] == "PAUSED_CLEAN"
            )
            writer.call(
                lambda: self.write(
                    "predecessor.json",
                    {
                        "root": str(predecessor),
                        "snapshot_sha256": self.contract.digest(previous),
                    },
                )
            )
            self.seq, self.last_hash, self.segment = (
                previous["last_event_seq"],
                previous["last_event_sha256"],
                previous["segment_id"],
            )
            node = predecessor
            seen = set()
            while node is not None:
                self.contract.require(str(node) not in seen)
                seen.add(str(node))
                self.prior_bytes += tree_bytes(node, check=self.writer.check_deadline)
                node = predecessor_root(node)
        writer.storage_guard = lambda: self.check_storage(0)

    def enable_accounting(self) -> None:
        """Public-only monotone reservation counter, never a validation cache.

        Rebuilt from the new segment tree on every invocation. Exclusive writes
        are charged before I/O; uncertain writes are never refunded. No path or
        event list is retained. Full physical accounting is reconciled on each
        admission and finalization boundary by the sole writer. Contents still
        require the original event/receipt readers; this tracks bytes only.
        """

        def enable():
            self.writer.assert_owner()
            self.contract.require(self.accounted_bytes is None)
            info = self.writer.root.stat(follow_symlinks=False)
            self.root_identity = (info.st_dev, info.st_ino)
            self.accounted_bytes = tree_bytes(self.writer.root)
            self.writer.charge_write = self.reserve_bytes

        self.writer.call(enable)

    def reserve_bytes(self, path: Path, size: int) -> None:
        self.writer.assert_owner()
        self.contract.uint(size)
        if not path.is_relative_to(self.writer.root):
            self.contract.require(callable(self.external_write))
            self.external_write(path, size)
            with self.ap_budget_lock:
                self.check_storage(size)
                self.external_bytes = self.contract.checked(self.external_bytes + size)
            return
        with self.ap_budget_lock:
            self.check_storage(size)
            self.accounted_bytes = self.contract.checked(self.accounted_bytes + size)

    def verify_storage(self) -> int:
        self.writer.assert_owner()
        if self.accounted_bytes is None:
            # Shared legacy/B2 callers retain their original synchronous scan.
            return tree_bytes(self.writer.root, check=self.writer.check_deadline)
        # Only the existing periodic slot may run during this writer action.
        # Pin all old bytes; newly appended periodic files are outside that sum
        # and are verified freshly, exactly, before accepting any accounting.
        before_bytes, before_seq, before_head = (
            self.accounted_bytes,
            self.seq,
            self.last_hash,
        )
        before_mono = self.last_mono
        events_root = self.writer.root / "events"

        def checkpoint():
            self.writer.check_deadline()
            self.writer.service_periodic()
            self.writer.assert_owner()

        def appended_sample(path):
            if path.parent != events_root or not path.name.endswith(".json"):
                return False
            token = path.name[:-5]
            if len(token) != 20 or not token.isascii() or not token.isdigit():
                return False
            ordinal = int(token)
            if ordinal <= before_seq:
                return False
            self.contract.require(
                before_seq < ordinal <= self.seq,
                "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
            )
            return True

        actual_old = tree_bytes(
            self.writer.root, check=checkpoint, exclude_file=appended_sample
        )
        # No more periodic servicing while validating this now-pinned tail.
        # A pending observation remains bounded in its existing single slot.
        end, head, accounted = self.seq, self.last_hash, self.accounted_bytes
        tail_bytes, previous, mono = 0, before_head, before_mono
        for seq in range(before_seq + 1, end + 1):
            self.writer.check_deadline()
            raw = (
                io.read(events_root / f"{seq:020d}.json", limit=4096)
                if self.writer.sampling is not None
                else io.read(events_root / f"{seq:020d}.json")
            )
            obj = self.contract.parse(raw, self.contract.EVENT)
            self.contract.require(
                obj["seq"] == seq
                and obj["previous_event_sha256"] == previous
                and obj["campaign_start_sha256"] == self.start_hash
                and obj["segment_id"] == self.segment
                and obj["epoch_id"] == self.epoch
                and obj["mono_ns"] >= mono
                and (
                    (obj["kind"] == "RESOURCE" and obj["body"]["cause"] == "PERIODIC")
                    if self.writer.sampling is None
                    else obj["kind"] in ("RESOURCE_SAMPLE", "SAMPLE_ACK")
                ),
                "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
            )
            tail_bytes = self.contract.checked(tail_bytes + len(raw))
            previous, mono = self.contract.digest(obj), obj["mono_ns"]
        info = self.writer.root.stat(follow_symlinks=False)
        self.writer.assert_owner()
        self.contract.require(
            (info.st_dev, info.st_ino) == self.root_identity
            and actual_old == before_bytes
            and before_bytes + tail_bytes == accounted == self.accounted_bytes
            and (end, head) == (self.seq, self.last_hash)
            and previous == head,
            "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
        )
        return accounted

    def reconcile_storage(self) -> int:
        """Same physical scan, outside a guarded action ONLY when quiescent.

        A live writer without an exclusive closure fence uses the old path.
        No size/mtime observation substitutes for content validation.
        """
        fence = self.writer.closure_fence
        if fence is None:
            return self.writer.call(self.verify_storage)
        fence.check()
        before = self.writer.call(lambda: (self.root_identity, self.accounted_bytes))
        actual = tree_bytes(self.writer.root, check=self.writer.check_deadline)

        def bind():
            fence.check()
            self.contract.require(
                before == (self.root_identity, self.accounted_bytes)
                and (
                    self.accounted_bytes is None
                    or (
                        self.root_identity == fence.identity
                        and actual == self.accounted_bytes
                    )
                ),
                "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
            )
            return actual

        return self.writer.call(bind)

    @property
    def stored_bytes(self) -> int:
        return self.contract.checked(self.prior_bytes + tree_bytes(self.writer.root))

    def check_storage(self, additional: int) -> None:
        with self.ap_budget_lock:
            return self._check_storage(additional)

    def _check_storage(self, additional: int) -> None:
        current = (
            tree_bytes(self.writer.root)
            if self.accounted_bytes is None
            else self.accounted_bytes
        )
        self.contract.require(
            self.prior_bytes
            + current
            + self.external_bytes
            + additional
            + self.ap_pending_bytes
            <= self.storage_budget
            and self.prior_block_bytes
            + current
            + self.external_bytes
            + additional
            + self.ap_pending_bytes
            <= self.block_byte_budget,
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        )

    def normal_event_headroom(self) -> int:
        return (
            min(
                self.event_budget - self.seq,
                self.block_event_budget
                - self.prior_block_events
                - (self.seq - self.block_start_seq),
            )
            - self.closure_events
            - self.ap_pending_events
            - self.ap_inflight_events
        )

    def _readback(self, path: Path, raw: bytes) -> bytes:
        # Public metadata already has an exact expected length. A tighter read
        # bound rejects every extra/truncated byte as before, while avoiding a
        # 64MiB requested read for each small event. Shared B2 defaults unchanged.
        if (
            self.contract is o
            or getattr(self.contract, "AP_ENABLED", False)
            or getattr(self.contract, "PROFILE", None)
            == "stage12_transport_operations_v3"
        ):
            limit = min(len(raw), 64 * 1024 * 1024)
            if (
                getattr(self.contract, "AP_ENABLED", False)
                or getattr(self.contract, "PROFILE", None)
                == "stage12_transport_operations_v3"
            ) and path.parent.name == "events":
                self.contract.require(len(raw) <= 4096)
                limit = min(limit, 4096)
            return io.read(path, limit=limit)
        return io.read(path)

    def write(self, name: str, value: Any) -> str:
        self.writer.assert_owner()
        self.contract.require(Path(name).name == name and name not in (".", ".."))
        raw = c.canonical(value)
        self.check_storage(len(raw))
        io.write(self.writer.root / name, raw)
        self.contract.require(self._readback(self.writer.root / name, raw) == raw)
        return c.sha(raw).hex()

    def claim_inventory(self, name):
        # Cumulative validation inventory versions only, not DATA/control receipt
        # files or unchanged input runtime inventories. Charge before creation;
        # failed/partial attempts retain their invocation charge.
        if self.writer.sampling is not None and name in (
            "event_inventory.json",
            "attempt_inventory.json",
            "available_event_inventory.json",
            "available_attempt_inventory.json",
            "measurement_event_prefix.json",
        ):
            with self.ap_budget_lock:
                self.ap_inventory_calls += 1
                self.contract.require(
                    self.ap_inventory_calls <= self.ap_inventory_limit
                )

    def write_array(self, name: str, rows: Iterator[dict[str, Any]]) -> str:
        """Stream fixed-size metadata rows; exclusive write and full reopen."""
        self.writer.assert_owner()
        self.contract.require(Path(name).name == name and name not in (".", ".."))
        self.claim_inventory(name)
        path = self.writer.root / name
        io.private_directory(path.parent)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        fingerprint, size = hashlib.sha256(), 0
        before_bytes = tree_bytes(self.writer.root)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:

                def put(raw: bytes) -> None:
                    nonlocal size
                    self.contract.require(
                        self.prior_bytes + before_bytes + size + len(raw)
                        <= self.storage_budget
                        and self.prior_block_bytes + before_bytes + size + len(raw)
                        <= self.block_byte_budget,
                        "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                    )
                    io.charge_write(path, len(raw))
                    stream.write(raw)
                    fingerprint.update(raw)
                    size += len(raw)

                put(b"[")
                for i, row in enumerate(rows):
                    raw = c.canonical(row)[:-1]
                    self.contract.require(
                        len(raw)
                        <= (4095 if name == "measurement_event_prefix.json" else 511)
                        if self.writer.sampling is not None
                        and name
                        in (
                            "event_inventory.json",
                            "attempt_inventory.json",
                            "available_event_inventory.json",
                            "available_attempt_inventory.json",
                            "measurement_event_prefix.json",
                        )
                        else len(raw) <= 65536
                    )  # Fixed ledger/inventory rows, not payloads.
                    if i:
                        put(b",")
                    put(raw)
                put(b"]\n")
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        io.fsync_directory(path.parent)
        self.contract.require(
            self.contract.manifest_digest(read_array(path)) == fingerprint.hexdigest()
        )
        return fingerprint.hexdigest()

    def stream_array(self, name: str, rows: Iterator[dict[str, Any]]) -> str:
        """Derive one row on the caller, persist it on the sole writer.

        Expensive validation/joins never occupy one guarded writer transaction.
        There is one <=64 KiB row in flight. Partial files remain on failure;
        only a fully fsynced, reopened exact array returns an evidence identity.
        """
        self.contract.require(threading.current_thread() is not self.writer.thread)
        self.contract.require(Path(name).name == name and name not in (".", ".."))
        self.claim_inventory(name)
        path = self.writer.root / name
        state: dict[str, Any] = {"fd": None}
        fingerprint = hashlib.sha256()

        def put(raw: bytes) -> None:
            self.writer.assert_owner()
            self.check_storage(len(raw))
            if state["fd"] is None:
                io.private_directory(path.parent)
                state["fd"] = os.open(
                    path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                )
            io.charge_write(path, len(raw))
            view = memoryview(raw)
            while view:
                written = os.write(state["fd"], view)
                self.contract.require(written > 0, "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED")
                view = view[written:]
            fingerprint.update(raw)

        def close() -> None:
            if state["fd"] is not None:
                try:
                    os.fsync(state["fd"])
                finally:
                    os.close(state["fd"])
                    state["fd"] = None
                io.fsync_directory(path.parent)

        try:
            self.writer.call(lambda: put(b"["))
            for i, row in enumerate(rows):
                self.writer.check_deadline()
                raw = c.canonical(row)[:-1]
                self.contract.require(
                    len(raw)
                    <= (
                        (4095 if name == "measurement_event_prefix.json" else 511)
                        if self.writer.sampling is not None
                        and name
                        in (
                            "event_inventory.json",
                            "attempt_inventory.json",
                            "available_event_inventory.json",
                            "available_attempt_inventory.json",
                            "measurement_event_prefix.json",
                        )
                        else 65536
                    )
                )
                self.writer.call(lambda: put((b"," if i else b"") + raw))
            self.writer.call(lambda: put(b"]\n"))
            self.writer.call(close)
            self.contract.require(
                self.contract.manifest_digest(
                    read_array(path, check=self.writer.check_deadline)
                )
                == fingerprint.hexdigest()
            )
            io.record_read_output(path, fingerprint.hexdigest())
            return fingerprint.hexdigest()
        except BaseException as error:
            if self.writer.failures is not None:
                self.writer.failures.record("RECONCILIATION", error, writer=self.writer)
            if not self.writer.failed.is_set():
                try:
                    self.writer.call(close)
                except BaseException as error:
                    if self.writer.failures is not None:
                        self.writer.failures.record(
                            "CLEANUP", error, writer=self.writer
                        )
                    # Keep the original derivation/validation failure.
            raise

    def open_segment(self, segment: int, epoch: str, body: dict[str, Any]) -> str:
        self.contract.validate_type(epoch, "N32")
        self.contract.require(self.segment_closed and segment == self.segment + 1)
        self.segment, self.epoch = segment, epoch
        self.segment_closed, self.last_mono = False, 0
        return self.event("SEGMENT_OPEN", body)

    def event(
        self,
        kind: str,
        body: dict[str, Any],
        *,
        closure: bool = False,
        periodic: bool = False,
        periodic_timing: dict[str, int] | None = None,
        timing=None,
        writer_inline: bool = False,
    ) -> str:
        self.contract.require(
            not periodic or (kind == "RESOURCE" and body["cause"] == "PERIODIC")
        )
        self.contract.require(
            periodic_timing is None
            or (periodic and type(periodic_timing) is dict and not periodic_timing)
        )

        safe_call(timing, "mark", "journal_enter_ns")

        # Serializing this call through the writer is the seq allocation boundary.
        def append_unleased() -> str:
            if periodic_timing is not None:
                periodic_timing["writer_start_ns"] = self.clock.now_ns()
            self.writer.assert_owner()
            self.contract.require(not self.segment_closed)
            with self.ap_budget_lock:
                cap = (
                    self.event_budget
                    if closure
                    else self.event_budget - self.closure_events
                )
                if self.writer.sampling is not None:
                    self.writer.sampling.transfer_event(kind)
                self.contract.require(
                    self.seq + self.ap_pending_events + self.ap_inflight_events < cap,
                    "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                )
                block_cap = (
                    self.block_event_budget
                    if closure
                    else self.block_event_budget - self.closure_events
                )
                self.contract.require(
                    self.prior_block_events
                    + self.seq
                    - self.block_start_seq
                    + self.ap_pending_events
                    + self.ap_inflight_events
                    < block_cap,
                    "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
                )
                if self.writer.sampling is not None:
                    self.ap_inflight_events += 1
            mono = self.clock.now_ns()
            self.contract.require(mono >= self.last_mono)
            obj = {
                "schema_version": self.contract.EVENT,
                "campaign_start_sha256": self.start_hash,
                "segment_id": self.segment,
                "seq": self.seq + 1,
                "previous_event_sha256": self.last_hash,
                "epoch_id": self.epoch,
                "mono_ns": mono,
                "utc": self.clock.utc(),
                "kind": kind,
                "body": body,
            }
            safe_call(timing, "mark", "segment_id", self.segment)
            safe_call(timing, "mark", "event_seq", obj["seq"])
            safe_call(timing, "mark", "event_mono_ns", mono)
            safe_call(timing, "mark", "event_header_ns", mono)
            self.contract.validate(obj, self.contract.EVENT)
            if self.writer.sampling is not None:
                self.writer.sampling.event_milestone(kind, obj, "HEADER")
            if kind == "ATTEMPT_FINALIZED":
                self.contract.require(body["outcome"]["value"] != "UNKNOWN_DELIVERY")
            if "attempt" in body:
                self.contract.require(body["attempt"] <= 5)
            raw = c.canonical(obj)
            if kind == "SEGMENT_OPEN" and self.writer.sampling is not None:
                self.writer.sampling.anchor_open(obj)
            self.check_storage(len(raw))
            path = self.writer.root / "events" / f"{obj['seq']:020d}.json"
            io.write(path, raw)
            if self.writer.sampling is not None:
                self.writer.sampling.event_milestone(kind, obj, "APPENDED")
            self.contract.require(self._readback(path, raw) == raw)
            with self.ap_budget_lock:
                self.seq, self.last_hash, self.last_mono = (
                    obj["seq"],
                    c.sha(raw).hex(),
                    mono,
                )
                if self.writer.sampling is not None:
                    self.ap_inflight_events -= 1
            if kind == "SEGMENT_CLOSE":
                self.segment_closed = True
            safe_call(timing, "mark", "append_complete_ns")
            if periodic_timing is not None:
                periodic_timing["writer_done_ns"] = self.clock.now_ns()
            return self.last_hash

        def append():
            if getattr(self.contract, "AP_ENABLED", False):
                from .s12_wf_ap2_scratch import lease

                with lease("EVENT"):
                    return append_unleased()
            return append_unleased()

        if writer_inline:
            self.contract.require(
                self.writer.sampling is not None
                and threading.current_thread() is self.writer.thread
            )
            return append()
        result = (
            self.writer.call(append, periodic=periodic)
            if timing is None
            else self.writer.call(append, periodic=periodic, timing=timing)
        )
        io.record_read_output(
            self.writer.root / "events" / f"{self.seq:020d}.json", result
        )
        safe_call(timing, "mark", "journal_ack_ns")
        return result


def predecessor_root(root: Path) -> Path | None:
    if not (root / "predecessor.json").exists():
        return None
    ref = io.metadata(io.read(root / "predecessor.json"))
    o.require(set(ref) == {"root", "snapshot_sha256"} and type(ref["root"]) is str)
    parent = Path(ref["root"])
    o.require(parent.is_absolute() and ".." not in parent.parts and parent != root)
    o.require(c.sha(io.read(parent / "snapshot.json")).hex() == ref["snapshot_sha256"])
    o.require(io.read(parent / "_SEGMENT_SEALED", limit=0) == b"")
    return parent


def read_events(
    root: Path,
    start_hash: str,
    _seen: frozenset[str] = frozenset(),
    *,
    contract: Any = o,
) -> Iterator[dict[str, Any]]:
    """Validate the entire available chain; caller separately proves totality."""
    o = contract
    last, segment, epoch, mono, closed = None, 0, None, 0, True
    o.require(str(root) not in _seen)
    parent = predecessor_root(root)

    def sources():
        if parent is not None:
            yield from (
                (e["seq"], c.canonical(e))
                for e in read_events(
                    parent, start_hash, _seen | {str(root)}, contract=contract
                )
            )
        if (
            getattr(o, "AP_ENABLED", False)
            or o.PROFILE == "stage12_transport_operations_v3"
        ):
            from .s12_public_history import event_paths

            paths = event_paths(root / "events")
        else:
            paths = sorted((root / "events").iterdir())
        for path in paths:
            o.require(path.name.endswith(".json") and path.stem.isdigit())
            yield (
                int(path.stem),
                io.read(path, limit=4096)
                if (
                    getattr(o, "AP_ENABLED", False)
                    or o.PROFILE == "stage12_transport_operations_v3"
                )
                else io.read(path),
            )

    for seq, (file_seq, raw) in enumerate(sources(), 1):
        o.require(file_seq == seq)
        obj = o.parse(raw, o.EVENT)
        o.require(
            obj["seq"] == seq
            and obj["previous_event_sha256"] == last
            and obj["campaign_start_sha256"] == start_hash
        )
        if obj["kind"] == "SEGMENT_OPEN":
            o.require(
                closed and obj["segment_id"] == segment + 1 and obj["epoch_id"] != epoch
            )
            segment, epoch, mono, closed = obj["segment_id"], obj["epoch_id"], 0, False
        o.require(
            not closed
            and obj["segment_id"] == segment
            and obj["epoch_id"] == epoch
            and obj["mono_ns"] >= mono
        )
        if obj["kind"] == "SEGMENT_CLOSE":
            closed = True
        last, mono = c.sha(raw).hex(), obj["mono_ns"]
        yield obj


class MeasurementPrefix:
    """Bounded disk projection of a quiescent validated event prefix.

    No event cache survives in memory. Every projection traversal revalidates
    canonical bytes, types, exact seq/hash chain and the pinned head. Original
    files are fully compared before creation and before accepting derived
    outputs/closure. Subsequent tail events remain original-file reads. This
    object is never restored or used for admission/recovery; ordinary reopen
    still reads all original event/receipt files.
    """

    LIMIT = 64 * 1024 * 1024

    def __init__(self, journal):
        self.journal = journal
        self.contract = journal.contract
        self.root = journal.writer.root
        self.start_hash = journal.start_hash
        self.seq, self.head = journal.writer.call(
            lambda: (journal.seq, journal.last_hash)
        )
        self.path = self.root / "measurement_event_prefix.json"
        self.bytes = 0
        self.hash = None
        self.check = lambda: journal.writer.check_deadline()

    @classmethod
    def from_closed(cls, root, start_hash, seq, *, check, contract=o):
        """Freshly bind a retained projection to ORIGINAL source, never its label.

        The caller has validated sealed snapshot inventories. No authority or
        correctness follows from the projection existing. Missing projection is
        handled by the caller as the legacy full-reader path.
        """
        if (
            getattr(contract, "AP_ENABLED", False)
            or contract.PROFILE == "stage12_transport_operations_v3"
        ):
            contract.require(predecessor_root(root) is None)
        result = cls.__new__(cls)
        result.journal = None
        result.contract = contract
        result.root, result.start_hash = root, start_hash
        result.seq, result.head = seq, None
        result.path = root / "measurement_event_prefix.json"
        result.check = check
        fingerprint = hashlib.sha256(b"[")
        last = None
        for event in read_events(root, start_hash, contract=contract):
            check()
            last = event
            if event["seq"] <= seq:
                if event["seq"] > 1:
                    fingerprint.update(b",")
                fingerprint.update(c.canonical(event)[:-1])
            if event["seq"] == seq:
                result.head = o.digest(event)
        o.require(last is not None and result.head is not None)
        fingerprint.update(b"]\n")
        result.hash = fingerprint.hexdigest()
        result.closed_end = (last["seq"], o.digest(last))
        return result

    def endpoint(self):
        if self.journal is None:
            return self.closed_end
        return (
            (self.journal.seq, self.journal.last_hash)
            if threading.current_thread() is self.journal.writer.thread
            else self.journal.writer.call(
                lambda: (self.journal.seq, self.journal.last_hash)
            )
        )

    def verify_original(self):
        o = self.contract
        last = None
        for event in read_events(self.root, self.start_hash, contract=self.contract):
            last = event
            if event["seq"] == self.seq:
                o.require(o.digest(event) == self.head)
        o.require(last is not None and last["seq"] >= self.seq)
        o.require((last["seq"], o.digest(last)) == self.endpoint())

    def build(self, *, closure_reserve=0):
        o = self.contract
        o.uint(closure_reserve)
        if (
            getattr(o, "AP_ENABLED", False)
            or o.PROFILE == "stage12_transport_operations_v3"
        ) and predecessor_root(self.root) is not None:
            return False  # No third retained copy of predecessor raw events.
        # No sample/event producer remains during this construction. Count
        # bytes AND perform the first exact original-source verification in the
        # same traversal; do not replace it with a metadata/cache assertion.
        size, last = 3, None
        for event in read_events(self.root, self.start_hash, contract=self.contract):
            last = event
            if event["seq"] == self.seq:
                o.require(o.digest(event) == self.head)
            size += len(c.canonical(event))
            if size > self.LIMIT:
                return False  # Original validated factory remains the fallback.
        o.require(last is not None and last["seq"] >= self.seq)
        o.require((last["seq"], o.digest(last)) == self.endpoint())
        journal = self.journal
        current = journal.reconcile_storage()
        if (
            journal.prior_bytes + current + size + closure_reserve
            > journal.storage_budget
            or journal.prior_block_bytes + current + size + closure_reserve
            > journal.block_byte_budget
        ):
            return False  # Preserve the full selected finalization metadata reserve.
        self.hash = self.journal.stream_array(
            self.path.name,
            read_events(self.root, self.start_hash, contract=self.contract),
        )
        self.bytes = size
        self.verify_original()
        return True

    def events(self):
        o = self.contract
        last, segment, epoch, mono, closed = None, 0, None, 0, True
        fingerprint = hashlib.sha256(b"[")
        seq = 0
        for obj in read_array(
            self.path,
            check=self.check,
            maximum_row_bytes=4095
            if (
                getattr(o, "AP_ENABLED", False)
                or o.PROFILE == "stage12_transport_operations_v3"
            )
            else 65536,
        ):
            seq += 1
            if seq > 1:
                fingerprint.update(b",")
            raw = c.canonical(obj)
            fingerprint.update(raw[:-1])
            o.validate(obj, o.EVENT)
            o.require(
                obj["seq"] == seq
                and obj["previous_event_sha256"] == last
                and obj["campaign_start_sha256"] == self.start_hash
            )
            if obj["kind"] == "SEGMENT_OPEN":
                o.require(
                    closed
                    and obj["segment_id"] == segment + 1
                    and obj["epoch_id"] != epoch
                )
                segment, epoch, mono, closed = (
                    obj["segment_id"],
                    obj["epoch_id"],
                    0,
                    False,
                )
            o.require(
                not closed
                and obj["segment_id"] == segment
                and obj["epoch_id"] == epoch
                and obj["mono_ns"] >= mono
            )
            if obj["kind"] == "SEGMENT_CLOSE":
                closed = True
            last, mono = c.sha(raw).hex(), obj["mono_ns"]
            yield obj
        fingerprint.update(b"]\n")
        o.require(
            seq == self.seq
            and last == self.head
            and fingerprint.hexdigest() == self.hash
        )
        # Only the sole writer can append a tail. Pin its current head on entry.
        end, head = self.endpoint()
        for i in range(seq + 1, end + 1):
            path = self.root / "events" / f"{i:020d}.json"
            obj = o.parse(
                io.read(path, limit=4096)
                if (
                    getattr(o, "AP_ENABLED", False)
                    or o.PROFILE == "stage12_transport_operations_v3"
                )
                else io.read(path),
                o.EVENT,
            )
            o.require(
                not closed
                and obj["seq"] == i
                and obj["previous_event_sha256"] == last
                and obj["campaign_start_sha256"] == self.start_hash
                and obj["segment_id"] == segment
                and obj["epoch_id"] == epoch
                and obj["mono_ns"] >= mono
            )
            if obj["kind"] == "SEGMENT_CLOSE":
                closed = True
            last, mono = o.digest(obj), obj["mono_ns"]
            yield obj
        o.require(last == head)


def inventory(root: Path, *, contract: Any = o) -> Iterator[dict[str, str]]:
    """Available-file inventory; does not assert complete campaign provenance."""
    if (
        getattr(contract, "AP_ENABLED", False)
        or contract.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_history import inventory as ap_inventory

        yield from ap_inventory(root)
        return
    for p in sorted(root.rglob("*")):
        if not p.is_dir():
            yield {
                "path": str(p.relative_to(root)),
                "sha256": c.sha(
                    io.read(p, limit=4096)
                    if root.name == "events"
                    and getattr(contract, "PROFILE", None)
                    == "stage12_transport_operations_v3"
                    else io.read(p)
                ).hex(),
            }


def evidence_inventory(
    root: Path, area: str, *, contract: Any = o
) -> Iterator[dict[str, str]]:
    """Full campaign inventory with immutable predecessor locations disambiguated."""
    o = contract
    o.require(area in ("events", "attempts"))
    parent = predecessor_root(root)
    if parent is not None:
        yield from evidence_inventory(parent, area, contract=contract)
    first = min((root / "events").iterdir(), key=lambda p: p.name)
    segment = o.parse(
        io.read(first, limit=4096)
        if (
            getattr(o, "AP_ENABLED", False)
            or o.PROFILE == "stage12_transport_operations_v3"
        )
        else io.read(first),
        o.EVENT,
    )["segment_id"]
    for row in inventory(root / area, contract=contract):
        yield {
            "path": f"segments/{segment:020d}/{area}/{row['path']}",
            "sha256": row["sha256"],
        }


def tree_bytes(
    root: Path,
    exclude: frozenset[str] = frozenset(),
    *,
    check: Callable[[], None] = lambda: None,
    exclude_file: Callable[[Path], bool] = lambda path: False,
) -> int:
    """Actual logical file bytes, including failed writes, without reading bodies."""
    check()
    total = 0
    with os.scandir(root) as entries:
        for entry in entries:
            check()
            if entry.name in exclude:
                continue
            info = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                total = o.checked(
                    total
                    + tree_bytes(
                        Path(entry.path), check=check, exclude_file=exclude_file
                    )
                )
            else:
                o.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
                if not exclude_file(Path(entry.path)):
                    total = o.checked(total + info.st_size)
    return total


def read_array(
    path: Path,
    *,
    check: Callable[[], None] = lambda: None,
    maximum_row_bytes: int = 65536,
) -> Iterator[dict[str, Any]]:
    """Read canonical metadata arrays with a bounded single-row buffer.

    This is for fixed O-r2 work/ledger/inventory rows, never response payloads.
    Existing private regular-file/64 MiB metadata-file guards are retained.
    """
    o.require(type(maximum_row_bytes) is int and 1 <= maximum_row_bytes <= 65536)
    io.private_directory(path.parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    before = os.fstat(fd)
    try:
        o.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and before.st_nlink == 1
            and stat.S_IMODE(before.st_mode) in (0o400, 0o600)
            and before.st_size <= 64 * 1024 * 1024
        )
        decoder = json.JSONDecoder(object_pairs_hook=io.pairs)
        buffer, eof = "", False

        def fill() -> None:
            check()
            nonlocal buffer, eof
            raw = os.read(fd, 4096)
            eof = not raw
            try:
                buffer += raw.decode("ascii")
            except UnicodeError:
                o.require(False)
            o.require(len(buffer) <= 65536 + 4096)

        fill()
        o.require(buffer.startswith("["))
        buffer = buffer[1:]
        first = True
        while True:
            while not buffer and not eof:
                fill()
            if buffer.startswith("]"):
                break
            if not first:
                o.require(buffer.startswith(","))
                buffer = buffer[1:]
            while True:
                try:
                    item, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    o.require(not eof and len(buffer) <= maximum_row_bytes)
                    fill()
            o.require(
                type(item) is dict
                and end <= maximum_row_bytes
                and c.canonical(item)[:-1].decode("ascii") == buffer[:end]
            )
            buffer = buffer[end:]
            first = False
            yield item
        while not eof:
            fill()
        o.require(buffer == "]\n")
        after = os.fstat(fd)
        o.require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
        )
    finally:
        os.close(fd)

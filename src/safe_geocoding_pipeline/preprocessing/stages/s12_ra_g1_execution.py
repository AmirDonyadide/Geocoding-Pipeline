"""One monitored phase with real opening and a bounded growing first read.

The worker validates prefix H0 inside its real opening stage, then reads only
new rows after FINAL. The supervisor independently reads the entire immutable
stream after the genuine worker return. No boolean replaces either read pass.
"""

from __future__ import annotations

from typing import Any
import hashlib
import os
from pathlib import Path
import stat
import time

from . import s12_ra_g1_assurance as a
from . import s12_ra_g1_monitor as m
from . import s12_public_operations as o
from . import s12_public_bounded as bounded
from . import s12_retrieval_contract as c

WORKER_VALIDATION = "stage12_resource_monitor_worker_validation_ra_g1_v1"
WORKER_SCHEMA: dict[str, Any] = {
    "schema_version": "=" + WORKER_VALIDATION,
    **o.fields(
        "binding_sha256:D selection_sha256:D phase_id:ID preopening_closure_sha256:D opener_return_sha256:D monitor_terminal_sha256:D prefix_H0_sha256:D full_monitor_inventory_sha256:D monitor_source_identity_sha256:D first_pass_start_ns:U prefix_validated_ns:U actual_data_opener_enter_ns:U first_pass_end_ns:U verified_original_rows:U max_gap_ns:U"
    ),
    "disposition": "=FIRST_GROWING_PASS_COMPLETE",
    "coverage": "=COMPLETE_SELECTED_SCOPE",
    "source_execution": "=REVIEWED_PHASE_WORKER_REAL_OPENER",
}

# Explicit successor registration; no historical reader changes.
m.SCHEMAS[WORKER_VALIDATION] = WORKER_SCHEMA
m.register_bootstrap_protocol_schema(WORKER_VALIDATION, WORKER_SCHEMA)


def validate_worker_validation(record: Any, *, protocol: Any = None) -> Any:
    bootstrap_sha = record.get("bootstrap_evidence_sha256")
    a.shape(record, m.SCHEMAS[m.BOOTSTRAP_PROTOCOL_IDS[WORKER_VALIDATION]] if bootstrap_sha is not None else WORKER_SCHEMA)
    if protocol is not None:
        c.require(bootstrap_sha == protocol.bootstrap_evidence_sha256, "RA_G1_BOOTSTRAP_REQUIRED")
    c.require(
        record["first_pass_start_ns"]
        <= record["prefix_validated_ns"]
        <= record["actual_data_opener_enter_ns"]
        <= record["first_pass_end_ns"]
        and record["verified_original_rows"] >= 2
        and record["max_gap_ns"] <= m.MAX_GAP_NS,
        "RA_G1_PROTOCOL",
    )
    if protocol is not None:
        c.require(
            record["binding_sha256"] == protocol.binding
            and record["selection_sha256"] == protocol.selection
            and record["phase_id"] == protocol.phase
            and record["preopening_closure_sha256"] == o.digest(protocol.closure)
            and record["opener_return_sha256"] == o.digest(protocol.opener)
            and record["monitor_terminal_sha256"] == o.digest(protocol.terminal)
            and record["prefix_H0_sha256"]
            == protocol.closure["original_observation_prefix_sha256"]
            and record["full_monitor_inventory_sha256"]
            == protocol.terminal["full_monitor_inventory_sha256"]
            and record["verified_original_rows"] == protocol.terminal["last_seq"]
            and record["max_gap_ns"] == protocol.terminal["max_gap_ns"]
            and protocol.opener["actual_opener_start_ns"]
            <= record["first_pass_start_ns"]
            <= record["prefix_validated_ns"]
            <= record["actual_data_opener_enter_ns"]
            <= protocol.opener["actual_opener_return_ns"]
            <= record["first_pass_end_ns"]
            < protocol.deadline,
            "RA_G1_PROTOCOL",
        )
    return record


def _identity(info: Any) -> tuple[Any, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
    )


class GrowingPrefix:
    """Constant Coverage/fd state, one monotonic first read through prefix+tail."""

    def __init__(
        self,
        path: Any,
        *,
        binding_sha256: Any,
        selection: Any,
        phase_id: Any,
        seed_sha256: Any,
        scope_start_ns: Any,
        check: Any,
        original_reader: Any,
        charge_read: Any,
        clock_ns: Any = time.monotonic_ns,
        test_only: Any = False,
    ) -> None:
        (
            self.path,
            self.selection,
            self.check,
            self.original_reader,
            self.charge_read,
            self.clock,
            self.test_only,
        ) = (
            Path(path),
            selection,
            check,
            original_reader,
            charge_read,
            clock_ns,
            test_only,
        )
        self.ancestors = a.private_root_identity(self.path.parent)
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        self.initial = os.fstat(self.fd)
        c.require(
            stat.S_ISREG(self.initial.st_mode)
            and self.initial.st_uid == os.geteuid()
            and stat.S_IMODE(self.initial.st_mode) == 0o600
            and self.initial.st_nlink == 1,
            "RA_G1_ORIGINAL_CHANGED",
        )
        self.coverage = m.Coverage(
            binding_sha256=binding_sha256,
            selection_sha256=o.digest(selection),
            phase_id=phase_id,
            seed_sha256=seed_sha256,
            selected=selection,
            scope_start_ns=scope_start_ns,
        )
        self.digest, self.closed, self.started = hashlib.sha256(), False, self.clock()

    def consume(self, last_seq: Any) -> Any:
        a.shape(last_seq, "U")
        c.require(
            not self.closed
            and self.coverage.seq
            <= last_seq
            <= self.selection["limits"]["monitor_rows"],
            "RA_G1_READ_LIMIT",
        )
        while self.coverage.seq < last_seq:
            self.check()
            raw = m.charged_read(self.fd, m.CODEC_BYTES, self.charge_read)
            c.require(len(raw) == m.CODEC_BYTES, "RA_G1_ORIGINAL_CHANGED")
            row = m.unpack_observation(raw)
            original = self.original_reader(row["visible_identity_inventory_sha256"])
            m.validate_original_observation(
                original, observation=row, allow_synthetic=self.test_only
            )
            self.coverage.add(row)
            self.digest.update(raw)
        current, opened = self.path.stat(follow_symlinks=False), os.fstat(self.fd)
        c.require(
            _identity(self.initial) == _identity(current) == _identity(opened)
            and opened.st_size >= last_seq * m.CODEC_BYTES,
            "RA_G1_ORIGINAL_CHANGED",
        )
        self.check()
        return self.coverage.inventory_sha256()

    def finish(self, terminal: Any) -> Any:
        self.consume(terminal["last_seq"])
        self.coverage.require_complete(
            opener_return_ns=terminal["coverage_end_ns"]
            if self.coverage.final is None
            else self.coverage.final["enter_mono_ns"],
            last_ack_ns=terminal["last_ack_ns"],
        )
        self.check()
        c.require(
            not m.charged_read(self.fd, 1, self.charge_read), "RA_G1_ORIGINAL_CHANGED"
        )
        info, path_info = os.fstat(self.fd), self.path.stat(follow_symlinks=False)
        c.require(
            _identity(self.initial) == _identity(info) == _identity(path_info)
            and info.st_size == self.coverage.seq * m.CODEC_BYTES
            and self.ancestors == a.private_root_identity(self.path.parent)
            and self.coverage.inventory_sha256()
            == terminal["full_monitor_inventory_sha256"]
            and self.coverage.head == terminal["final_observation_sha256"],
            "RA_G1_ORIGINAL_CHANGED",
        )
        result = dict(
            device=info.st_dev,
            inode=info.st_ino,
            mode=info.st_mode,
            uid=info.st_uid,
            gid=info.st_gid,
            nlink=info.st_nlink,
            bytes=info.st_size,
            mtime_ns=info.st_mtime_ns,
            ctime_ns=info.st_ctime_ns,
            sha256=self.digest.hexdigest(),
        )
        self.close()
        self.check()
        return result

    def close(self) -> None:
        if not self.closed:
            os.close(self.fd)
            self.closed = True


def resource_cadence_mode(selection: Any, requested: bool = False) -> bool:
    """Current REP is closed by its schema; PUBLIC requires its admitted caller."""
    c.require(type(requested) is bool, "RA_G1_SELECTION_BINDING")
    representative = (
        selection["scope"] == "REPRESENTATIVE_NO_SERVICE"
        and selection["schema_version"] == a.REP_ADMIN_SELECTION
    )
    public = (
        selection["scope"] == "PUBLIC_SYNTHETIC_ONLY"
        and selection["schema_version"] == a.SELECTION
    )
    c.require(not requested or representative or public, "RA_G1_SELECTION_BINDING")
    return representative or requested


class PhaseSession:
    """Attach scoped monitoring to a public Authority or protected RuntimePort.

    All filesystem mutations are exclusive and precharged. Real observers use
    actual Linux originals; observer_factory is accepted only on a test-only
    authority. Root/genuine supervisor lifecycle remains outside this worker.
    """

    def __init__(
        self,
        *,
        authority: Any,
        binding: Any,
        selection: Any,
        resource_evidence_root: Any,
        pids: Any,
        counter_provider: Any,
        charge: Any,
        check: Any,
        deadline_ns: Any,
        phase_id: Any = 1,
        cgroup_path: Any = None,
        native_paths: Any = (),
        native_roots: Any = None,
        admitted_process_provider: Any = None,
        read_charge: Any = None,
        clock_ns: Any = time.monotonic_ns,
        observer_factory: Any = None,
        scope_start_ns: Any = None,
        directory_charge: Any = None,
        startup_trace: Any = None,
        bootstrap_prefix: Any = None,
        bootstrap_adoption_reader: Any = None,
        start_to_start: bool = False,
    ) -> None:
        if startup_trace is not None:
            m.emit_startup_trace(startup_trace, "SESSION_SETUP_ENTER")
        self.authority, self.binding, self.selection = (
            authority,
            binding,
            a.validate_selection(selection),
        )
        self.start_to_start = resource_cadence_mode(self.selection, start_to_start)
        self.validate_binding(binding)
        c.require(
            o.digest(selection) == binding["selection_sha256"]
            and selection["scope"] == binding["scope"]
            and callable(charge)
            and callable(check)
            and callable(counter_provider)
            and callable(admitted_process_provider)
            and callable(read_charge),
            "RA_G1_SELECTION_BINDING",
        )
        self.root, self.clock, self.deadline, self.phase = (
            Path(resource_evidence_root),
            clock_ns,
            deadline_ns,
            phase_id,
        )
        self.external_check, self.charge, self.read_charge = check, charge, read_charge
        self.bootstrap_record = None
        self.bootstrap_prefix = bootstrap_prefix
        self.bootstrap_adoption_reader = bootstrap_adoption_reader
        self.bootstrap_rechecks = 0
        required_role = a.bootstrap_role(selection, phase_id)
        c.require((required_role is not None) == (bootstrap_prefix is not None), "RA_G1_BOOTSTRAP_REQUIRED")
        monitor_scope_start = scope_start_ns
        if bootstrap_prefix is not None:
            a.shape(bootstrap_prefix, {"role": o.enum("COLLECTOR", "REVIEW", "PHASE_RUNNER"), "source_entry_ns":"U", "bootstrap_end_ns":"U"})
            c.require(bootstrap_prefix["role"] == required_role
                      and bootstrap_prefix["source_entry_ns"] == scope_start_ns
                      and scope_start_ns <= bootstrap_prefix["bootstrap_end_ns"] <= self.clock()
                      and bootstrap_prefix["bootstrap_end_ns"] - scope_start_ns <= a.BOOTSTRAP_LIMIT_NS
                      and callable(bootstrap_adoption_reader), "RA_G1_BOOTSTRAP_LIMIT")
            monitor_scope_start = bootstrap_prefix["bootstrap_end_ns"]
        self.directory_charge = directory_charge
        self.test_only = getattr(authority, "test_only", False) is True
        self.monitor: Any = None
        self.failed, self.completed, self.admin_operations = False, False, 0
        self._making_observation = False
        self._counter_provider = counter_provider
        self.check()
        self._mkdir(self.root)
        self.original_root = self.root / "originals"
        self._mkdir(self.original_root)
        self.writer = m.ObservationWriter(
            self.root / "observations.bin",
            maximum_rows=selection["limits"]["monitor_rows"],
            charge=charge,
            check=self.check,
            clock_ns=clock_ns,
            original_root=self.original_root,
            prewrite=self._prewrite,
            charge_read=self.read_charge,
            startup_trace=startup_trace,
        )
        try:
            if startup_trace is not None:
                m.emit_startup_trace(startup_trace, "WRITER_CREATED", writer=self.writer)
            self.seed = o.digest(
                dict(
                    schema_version="stage12_resource_monitor_seed_ra_g1_v1",
                    binding_sha256=o.digest(binding),
                    selection_sha256=o.digest(selection),
                    phase_id=phase_id,
                )
            )

            def retain(original: Any) -> str:
                raw = m.export_original_observation(
                    original, allow_synthetic=self.test_only
                )
                return self.writer.stage_original(raw)

            if observer_factory is None:
                c.require(cgroup_path is not None, "RA_G1_PROCESS_SCOPE")
                self.observer = m.LinuxObserver(
                    pids=pids,
                    cgroup_path=cgroup_path,
                    root=self.root,
                    native_paths=native_paths,
                    native_roots=native_roots,
                    counter_provider=counter_provider,
                    retain_originals=retain,
                    admitted_process_provider=admitted_process_provider,
                    read_charge=read_charge,
                    check=self.check,
                    clock_ns=clock_ns,
                )
            else:
                c.require(self.test_only, "RA_G1_SYNTHETIC_DENIED")
                self.observer = observer_factory(retain)
            self.monitor = m.ResourceMonitor(
                observer=self.observer,
                writer=self.writer,
                selected=selection,
                binding_sha256=o.digest(binding),
                phase_id=phase_id,
                seed_sha256=self.seed,
                deadline_ns=deadline_ns,
                check=self.check,
                clock_ns=clock_ns,
                scope_start_ns=monitor_scope_start,
                startup_trace=startup_trace,
                start_to_start=self.start_to_start,
            )
            self.protocol = m.PhaseProtocol(
                binding_sha256=o.digest(binding),
                selection_sha256=o.digest(selection),
                phase_id=phase_id,
                deadline_ns=deadline_ns,
                check=self.check,
                clock_ns=clock_ns,
            )
            self.cursor: Any = None
            self.records: dict[str, Any] = {}
            self.source_identities: dict[str, Any] = {}
            self.supervisor_context: Any = None
            self.supervisor_context_sha256: Any = None
        except BaseException as error:
            # The writer is owned here until construction returns to the caller.
            if startup_trace is not None:
                m.emit_startup_trace(startup_trace, "START_FAILED", error=error)
            if self.monitor is not None:
                self.monitor.stop_event.set()
            with self.writer.condition:
                self.writer.closing = True
                self.writer.condition.notify_all()
            try:
                self.writer.close(self.deadline)
            except BaseException as cleanup:
                with self.writer.condition:
                    self.writer.poisoned = True
                if startup_trace is not None:
                    m.emit_startup_trace(
                        startup_trace, "ABORT_FAILED", error=cleanup, cleanup=True
                    )
            finally:
                self.failed = True
            raise

    def validate_binding(self, binding: Any) -> None:
        a.shape(binding, a.SCHEMA)

    def check(self) -> None:
        self.external_check()
        c.require(not self.failed and self.clock() < self.deadline, "RA_G1_DEADLINE")

    def _mkdir(self, path: Any) -> None:
        self.check()
        a.private_root_identity(path.parent)
        (self.charge if self.directory_charge is None else self.directory_charge)(0, 1)
        self._prewrite(0, 1, root=path.parent)
        path.mkdir(mode=0o700, exist_ok=False)
        a.private_root_identity(path)
        self.check()

    def _prewrite(self, size: Any, creations: Any, *, root: Any = None) -> None:
        self.check()
        o.uint(size)
        o.uint(creations)
        selected_root = self.root if root is None else Path(root)
        info = selected_root.stat(follow_symlinks=False)
        c.require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700,
            "RA_G1_PATH",
        )
        observed = os.statvfs(selected_root)
        c.require(
            observed.f_frsize > 0
            and 0 <= observed.f_bavail <= observed.f_blocks
            and 0 <= observed.f_favail <= observed.f_files
            and o.checked(observed.f_bavail * observed.f_frsize)
            >= o.checked(size + 1342177280)
            and observed.f_favail >= o.checked(creations + 4096),
            "RA_G1_SHARED_MARGIN",
        )
        self.check()

    def _persist(self, name: Any, record: Any, *, validator: Any = m.validate) -> str:
        self.check()
        c.require(
            name
            in ("preopening", "opener_return", "monitor_terminal", "worker_validation", "bootstrap_prefix"),
            "RA_G1_FIELDS",
        )
        validator(record)
        counter = bounded.Canonical(m.MAX_RECORD_BYTES, count_only=True)
        counter.value(record)
        counter.put(b"\n")
        raw = bytes(bounded.canonical(record, m.MAX_RECORD_BYTES))
        self.charge(m.MAX_RECORD_BYTES, 1)
        self._prewrite(m.MAX_RECORD_BYTES, 1)
        self.admin_operations += 1
        c.require(self.admin_operations <= 64, "RA_G1_COUNTER_LIMIT")
        deadline = min(self.deadline, self.clock() + m.GUARD_NS)
        path = self.root / (name + ".record")
        self.check()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            offset = 0
            while offset < len(raw):
                self.check()
                c.require(self.clock() < deadline, "RA_G1_DEADLINE")
                size = os.write(fd, memoryview(raw)[offset:])
                c.require(size > 0, "RA_G1_WRITE_UNCERTAIN")
                offset += size
            os.fsync(fd)
        finally:
            os.close(fd)
        self.check()
        c.require(self.clock() < deadline, "RA_G1_DEADLINE")
        # A bounded independent readback, not the submitted in-memory object.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            actual = m.charged_read(fd, m.MAX_RECORD_BYTES, self.read_charge)
            c.require(
                not m.charged_read(fd, 1, self.read_charge)
                and actual == raw
                and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600,
                "RA_G1_WRITE_UNCERTAIN",
            )
            self.source_identities[name] = dict(
                device=info.st_dev, inode=info.st_ino, bytes=info.st_size
            )
        finally:
            os.close(fd)
        self.check()
        c.require(self.clock() < deadline, "RA_G1_DEADLINE")
        self.records[name] = record
        return hashlib.sha256(raw).hexdigest()

    def original_reader(self, digest: Any) -> Any:
        a.shape(digest, "D")
        return m.read_original_observation(
            self.original_root / (digest + ".record"),
            expected_sha256=digest,
            check=self.check,
            charge_read=self.read_charge,
            test_only=self.test_only,
        )

    def abort(self) -> None:
        """Bounded truthful stop; no terminal success or lost charge is repaired."""
        self.failed = True
        if self.monitor is not None:
            self.monitor.stop_event.set()
            if self.monitor.thread.is_alive():
                self.monitor.thread.join(
                    max(0, min(m.GUARD_NS, self.deadline - self.clock())) / 1e9
                )
        with self.writer.condition:
            self.writer.closing = True
            self.writer.condition.notify_all()
        self.writer.thread.join(
            max(0, min(m.GUARD_NS, self.deadline - self.clock())) / 1e9
        )
        if self.writer.thread.is_alive():
            with self.writer.condition:
                self.writer.poisoned = True
        self.protocol.state = "UNCERTAIN" if self.writer.poisoned else "INCOMPLETE"
        if self.cursor is not None:
            self.cursor.close()

    def start(self) -> Any:
        trace = getattr(self.monitor, "startup_trace", None)
        if trace is None:
            self.check()  # Preserve legacy/default ordering and cleanup behavior.
        try:
            if trace is not None:
                self.check()
            self._rep_admin_adoption()
            self.monitor.start()
            if self.bootstrap_prefix is not None:
                self._save_bootstrap_original()
                self.require_start_acknowledged()
        except BaseException as error:
            if trace is None:
                self.abort()
                raise
            m.emit_startup_trace(trace, "START_FAILED", error=error)
            try:
                self.abort()
            except BaseException as cleanup:
                m.emit_startup_trace(trace, "ABORT_FAILED", error=cleanup, cleanup=True)
            raise
        self.authority.resource_monitor = self.monitor
        self.authority.resource_session = self
        return self

    def _rep_admin_adoption(self) -> Any:
        if self.selection["schema_version"] != a.REP_ADMIN_SELECTION:
            return None
        c.require(callable(self.bootstrap_adoption_reader), "RA_G1_SELECTION_BINDING")
        value = self.bootstrap_adoption_reader(self.selection["rep_admin_budget_adoption_sha256"])
        if type(value) is bytes:
            import json
            c.require(len(value) <= 8192, "RA_G1_RECORD_LIMIT")
            raw = value
            value = json.loads(raw)
            c.require(c.canonical(value) == raw, "RA_G1_SELECTION_BINDING")
        c.require(len(c.canonical(value)) <= 8192, "RA_G1_RECORD_LIMIT")
        return a.validate_rep_admin_adoption(value, self.selection)

    def _bootstrap_adoption(self) -> Any:
        value = self.bootstrap_adoption_reader(self.selection["bootstrap_prefix_adoption_sha256"])
        if type(value) is bytes:
            import json
            c.require(len(value) <= 8192, "RA_G1_RECORD_LIMIT")
            raw = value
            value = json.loads(raw)
            c.require(c.canonical(value) == raw, "RA_G1_BOOTSTRAP_EVIDENCE")
        return a.validate_bootstrap_adoption(value, self.selection)

    def _save_bootstrap_original(self) -> None:
        receipt = self.monitor.first_start_receipt
        first, ack = receipt["row"], receipt["ack_ns"]
        prefix = self.bootstrap_prefix
        c.require(first["seq"] == 1 and ack - prefix["source_entry_ns"] <= a.BOOTSTRAP_LIMIT_NS
                  and ack < self.deadline, "RA_G1_BOOTSTRAP_LIMIT")
        record = dict(schema_version=a.BOOTSTRAP_EVIDENCE, scope="REPRESENTATIVE_NO_SERVICE",
            role=prefix["role"], binding_sha256=o.digest(self.binding), selection_sha256=o.digest(self.selection),
            bootstrap_policy_sha256=self.selection["bootstrap_prefix_policy_sha256"],
            bootstrap_adoption_sha256=self.selection["bootstrap_prefix_adoption_sha256"],
            root_identity_inventory_sha256=o.digest(a.private_root_identity(self.root)), phase_id=self.phase,
            source_entry_mono_ns=prefix["source_entry_ns"], bootstrap_end_mono_ns=prefix["bootstrap_end_ns"],
            phase_deadline_mono_ns=self.deadline, first_start_seq=1, first_start_record_sha256=o.digest(first),
            first_start_original_sha256=first["visible_identity_inventory_sha256"],
            first_start_enter_mono_ns=first["enter_mono_ns"], first_start_exit_mono_ns=first["exit_mono_ns"],
            first_start_ack_mono_ns=ack, adoption_original=self._bootstrap_adoption(),
            unmonitored_prefix="OWNER_ACCEPTED_PROSPECTIVE_ONLY", monitor_scope_start="ACTUAL_BOOTSTRAP_END")
        a.validate_bootstrap_evidence(record, self.selection, binding_sha256=o.digest(self.binding), root=self.root, first=first)
        self._persist("bootstrap_prefix", record)
        self.bootstrap_record = record
        self.protocol.bootstrap_evidence_sha256 = o.digest(record)
        self.monitor.bootstrap_evidence_sha256 = o.digest(record)

    def require_start_acknowledged(self) -> Any:
        self.check()
        receipt = getattr(self.monitor, "first_start_receipt", None)
        c.require(receipt is not None and receipt["row"]["seq"] == 1, "RA_G1_BOOTSTRAP_REQUIRED")
        if self.bootstrap_prefix is None:
            return receipt
        self.bootstrap_rechecks += 1
        c.require(self.bootstrap_rechecks <= 8 and self.bootstrap_record is not None, "RA_G1_BOOTSTRAP_REQUIRED")
        actual = m.read_record(self.root / "bootstrap_prefix.record", expected_sha256=o.digest(self.bootstrap_record),
            check=self.check, charge_read=self.read_charge)
        a.validate_bootstrap_evidence(actual, self.selection, binding_sha256=o.digest(self.binding), root=self.root, first=receipt["row"])
        c.require(actual["first_start_ack_mono_ns"] == receipt["ack_ns"]
                  and actual["phase_deadline_mono_ns"] == self.deadline
                  and actual["adoption_original"] == self._bootstrap_adoption(), "RA_G1_BOOTSTRAP_EVIDENCE")
        return actual

    def barrier(self, *, next_write_bytes: Any = 0, next_creations: Any = 0) -> Any:
        return self.monitor.barrier(
            next_write_bytes=next_write_bytes, next_creations=next_creations
        )

    def freeze_and_open(
        self,
        *,
        frozen_data_inventory_sha256: Any,
        actual_opener: Any,
        expected_negative_sha256: Any = None,
        is_expected_negative: Any = None,
    ) -> Any:
        try:
            return self._freeze_and_open(
                frozen_data_inventory_sha256=frozen_data_inventory_sha256,
                actual_opener=actual_opener,
                expected_negative_sha256=expected_negative_sha256,
                is_expected_negative=is_expected_negative,
            )
        except BaseException:
            self.abort()
            raise

    def _freeze_and_open(
        self,
        *,
        frozen_data_inventory_sha256: Any,
        actual_opener: Any,
        expected_negative_sha256: Any = None,
        is_expected_negative: Any = None,
    ) -> Any:
        """Run the existing real opener exactly once, under the same deadline."""
        self.check()
        c.require(
            not self.completed
            and self.protocol.state == "RUNNING"
            and callable(actual_opener),
            "RA_G1_PROTOCOL",
        )
        self.require_start_acknowledged()
        self.monitor.barrier()
        self.protocol.freeze(frozen_data_inventory_sha256)
        prefix = self.monitor.prefix()
        closure = dict(
            schema_version=m.CLOSURE,
            binding_sha256=o.digest(self.binding),
            selection_sha256=o.digest(self.selection),
            phase_id=self.phase,
            original_observation_prefix_sha256=prefix["inventory_sha256"],
            last_seq=prefix["last_seq"],
            monitor_coverage="COMPLETE_SELECTED_SCOPE",
            max_observed_gap_ns=prefix["max_gap_ns"],
            counter_totals_sha256=o.digest(prefix["counters"]),
            original_inventory_sha256=frozen_data_inventory_sha256,
            first_failure=None,
            cleanup_failure=None,
            outcome="PENDING_OPEN",
            native_maximum="NOT_PROVEN",
            physical_maximum="NOT_PROVEN",
            accepted_risk_inventory_sha256=self.binding["risk_inventory_sha256"],
            actual_opener_record_sha256=None,
        )
        closure = m.bootstrap_protocol_record(closure, self.protocol.bootstrap_evidence_sha256)
        self._persist("preopening", closure)
        self.protocol.preopen(closure)
        times: dict[str, int] = {}

        def opening_stage() -> Any:
            self.require_start_acknowledged()
            self._rep_admin_adoption()
            self.cursor = GrowingPrefix(
                self.writer.path,
                binding_sha256=o.digest(self.binding),
                selection=self.selection,
                phase_id=self.phase,
                seed_sha256=self.seed,
                scope_start_ns=self.monitor.scope_start,
                check=self.check,
                original_reader=self.original_reader,
                charge_read=self.read_charge,
                clock_ns=self.clock,
                test_only=self.test_only,
            )
            c.require(
                self.cursor.consume(prefix["last_seq"]) == prefix["inventory_sha256"]
                and self.cursor.coverage.max_gap == prefix["max_gap_ns"],
                "RA_G1_ORIGINAL_CHANGED",
            )
            times["prefix_validated_ns"] = self.clock()
            self.check()
            times["actual_data_opener_enter_ns"] = self.clock()
            return actual_opener()

        try:
            result, opener = self.protocol.open(
                opening_stage,
                expected_negative_sha256=expected_negative_sha256,
                is_expected_negative=is_expected_negative,
            )
            self._persist("opener_return", opener)
            self.monitor.finish(opener_return_ns=opener["actual_opener_return_ns"])
            terminal = m.monitor_terminal_record(
                self.monitor,
                opener_return=opener,
                prefix_H0_sha256=prefix["inventory_sha256"],
            )
            terminal = m.bootstrap_protocol_record(terminal, self.protocol.bootstrap_evidence_sha256)
            self.protocol.monitor_closed(terminal)
            self._persist("monitor_terminal", terminal)
            source_identity = self.cursor.finish(terminal)
            worker = dict(
                schema_version=WORKER_VALIDATION,
                binding_sha256=o.digest(self.binding),
                selection_sha256=o.digest(self.selection),
                phase_id=self.phase,
                preopening_closure_sha256=o.digest(closure),
                opener_return_sha256=o.digest(opener),
                monitor_terminal_sha256=o.digest(terminal),
                prefix_H0_sha256=prefix["inventory_sha256"],
                full_monitor_inventory_sha256=terminal["full_monitor_inventory_sha256"],
                monitor_source_identity_sha256=o.digest(source_identity),
                first_pass_start_ns=self.cursor.started,
                prefix_validated_ns=times["prefix_validated_ns"],
                actual_data_opener_enter_ns=times["actual_data_opener_enter_ns"],
                first_pass_end_ns=self.clock(),
                verified_original_rows=terminal["last_seq"],
                max_gap_ns=terminal["max_gap_ns"],
                disposition="FIRST_GROWING_PASS_COMPLETE",
                coverage="COMPLETE_SELECTED_SCOPE",
                source_execution="REVIEWED_PHASE_WORKER_REAL_OPENER",
            )
            worker = m.bootstrap_protocol_record(worker, self.protocol.bootstrap_evidence_sha256)
            validate_worker_validation(worker, protocol=self.protocol)
            self._persist(
                "worker_validation", worker, validator=validate_worker_validation
            )
            self.completed = True
            self.check()
            return result, dict(self.records)
        except BaseException:
            self.failed = True
            self.protocol.state = "UNCERTAIN" if self.writer.poisoned else "INCOMPLETE"
            if self.cursor is not None:
                self.cursor.close()
            raise


EXECUTION_REQUEST = "stage12_resource_execution_request_ra_g1_v1"
SUPERVISOR_CONTEXT = "stage12_resource_supervisor_context_ra_g1_v1"
ROLE_IDENTITY = o.fields("pid:P start_ticks:U uid:U")
SUPERVISOR_SCHEMA: dict[str, Any] = {
    "schema_version": "=" + SUPERVISOR_CONTEXT,
    "scope": o.enum(*a.SCOPES),
    **o.fields(
        "run_nonce:D source_git_sha:G selection_sha256:D adoption_sha256:D slurm_job_id:P boot_id:UUID created_mono_ns:U worker_uid:U cgroup_namespace_inode:P mount_namespace_inode:P"
    ),
    "visible_cgroup_path": "PATH",
    "supervisor": ROLE_IDENTITY,
    "timeout": {"nullable": ROLE_IDENTITY},
    "private_paths": {
        key: "PATH"
        for key in ("allocation_root", "resource_evidence_root", "scratch_root")
    },
    "protected_paths": {
        "nullable": {"bindings_path": "PATH", "registered_paths_record_sha256": "D"}
    },
}


def _path(value: Any) -> Path:
    c.require(
        type(value) is str
        and 0 < len(value.encode("utf-8")) <= 4096
        and "\x00" not in value
        and Path(value).is_absolute()
        and value == os.path.abspath(value),
        "RA_G1_PATH",
    )
    return Path(value)


def _context_shape(value: Any, spec: Any) -> None:
    if spec == "PATH":
        _path(value)
    elif type(spec) is dict and "nullable" in spec:
        if value is not None:
            _context_shape(value, spec["nullable"])
    elif type(spec) is dict and "enum" not in spec:
        c.require(type(value) is dict and set(value) == set(spec), "RA_G1_FIELDS")
        for key, child in spec.items():
            _context_shape(value[key], child)
    else:
        a.shape(value, spec)


def validate_execution_request(value: Any) -> Any:
    c.require(
        type(value) is dict
        and set(value)
        == {"schema_version", "supervisor_context_path", "supervisor_context_sha256"}
        and value["schema_version"] == EXECUTION_REQUEST,
        "RA_G1_EXECUTION_REQUEST",
    )
    _path(value["supervisor_context_path"])
    a.shape(value["supervisor_context_sha256"], "D")
    return value


def validate_supervisor_context(record: Any) -> Any:
    _context_shape(record, SUPERVISOR_SCHEMA)
    counter = bounded.Canonical(65536, count_only=True)
    counter.value(record)
    counter.put(b"\n")
    protected = record["scope"] in ("DEVELOPMENT_LOCAL_PREPARATION", "DEVELOPMENT_ONLY")
    c.require((record["protected_paths"] is not None) == protected, "RA_G1_SCOPE")
    a.shape(record["boot_id"], "UUID")
    c.require(
        record["supervisor"]["uid"] == record["worker_uid"]
        and (
            record["timeout"] is None
            or record["timeout"]["uid"] == record["worker_uid"]
            and record["timeout"]["pid"] != record["supervisor"]["pid"]
        ),
        "RA_G1_PROCESS_SCOPE",
    )
    return record


def execution_proc_paths(context: Any, *, worker_pid: Any = None) -> frozenset[Path]:
    """Exact read-only audit allowlist; no fd/environment/credential tree."""
    validate_supervisor_context(context)
    worker_pid = os.getpid() if worker_pid is None else worker_pid
    a.shape(worker_pid, "P")
    pids = [worker_pid, context["supervisor"]["pid"]]
    if context["timeout"] is not None:
        pids.append(context["timeout"]["pid"])
    result = {
        Path(f"/proc/{pid}/{name}")
        for pid in pids
        for name in ("status", "stat", "cgroup")
    }
    result.update(
        (
            Path("/proc/sys/kernel/random/boot_id"),
            Path(f"/proc/{worker_pid}/ns/cgroup"),
            Path(f"/proc/{worker_pid}/ns/mnt"),
        )
    )
    domain = _path(context["visible_cgroup_path"])
    result.update(
        domain / name
        for name in (
            "cgroup.procs",
            "memory.max",
            "memory.high",
            "memory.swap.max",
            "pids.max",
        )
    )
    return frozenset(result)


def _kernel_text(path: Any, *, check: Any, read_charge: Any) -> str:
    from . import s12_wf_ap2_scratch as scratch

    check()
    with scratch.lease("KERNEL"):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            c.require(
                stat.S_ISREG(before.st_mode) and not before.st_mode & 0o022,
                "RA_G1_KERNEL_SOURCE",
            )
            block, used = bytearray(8192), 0
            while used < 8192:
                check()
                read_charge(1, 0)
                size = os.readv(fd, [memoryview(block)[used:]])
                read_charge(0, size)
                if not size:
                    break
                used += size
            c.require(
                used < 8192
                and a.kernel_identity(before)
                == a.kernel_identity(os.fstat(fd))
                == a.kernel_identity(Path(path).stat(follow_symlinks=False)),
                "RA_G1_KERNEL_SOURCE",
            )
            return memoryview(block)[:used].tobytes().decode("ascii")
        finally:
            os.close(fd)


def _process_identity(pid: Any, *, check: Any, read_charge: Any) -> Any:
    a.shape(pid, "P")
    raw = _kernel_text(Path(f"/proc/{pid}/stat"), check=check, read_charge=read_charge)
    suffix = raw.rpartition(") ")[2].split()
    c.require(
        raw.partition(" (")[0] == str(pid)
        and len(suffix) >= 20
        and suffix[1].isdecimal()
        and suffix[19].isdecimal(),
        "RA_G1_PROCESS_SCOPE",
    )
    status = _kernel_text(
        Path(f"/proc/{pid}/status"), check=check, read_charge=read_charge
    )
    uid_rows = [
        line.partition(":")[2].split()
        for line in status.splitlines()
        if line.partition(":")[0] == "Uid"
    ]
    c.require(
        len(uid_rows) == 1
        and len(uid_rows[0]) == 4
        and len(set(uid_rows[0])) == 1
        and uid_rows[0][0].isdecimal(),
        "RA_G1_PROCESS_SCOPE",
    )
    uid = int(uid_rows[0][0])
    c.require(uid == os.geteuid(), "RA_G1_PROCESS_SCOPE")
    return dict(pid=pid, start_ticks=int(suffix[19]), uid=uid), int(suffix[1])


def _live_domain(*, check: Any, read_charge: Any) -> Any:
    pid = os.getpid()
    membership = _kernel_text(
        Path(f"/proc/{pid}/cgroup"), check=check, read_charge=read_charge
    ).strip()
    c.require(
        membership.startswith("0::/") and "\n" not in membership, "RA_G1_PROCESS_SCOPE"
    )
    domain = Path("/sys/fs/cgroup" + membership[3:].rstrip("/"))
    c.require(domain.resolve(strict=True) == domain, "RA_G1_PROCESS_SCOPE")
    boot = (
        _kernel_text(
            Path("/proc/sys/kernel/random/boot_id"),
            check=check,
            read_charge=read_charge,
        )
        .strip()
        .replace("-", "")
    )
    a.shape(boot, "UUID")
    return dict(
        domain=str(domain),
        membership=membership,
        boot_id=boot,
        cgroup_namespace_inode=Path(f"/proc/{pid}/ns/cgroup").stat().st_ino,
        mount_namespace_inode=Path(f"/proc/{pid}/ns/mnt").stat().st_ino,
    )


def capture_supervisor_context(
    *,
    scope: Any,
    source_git_sha: Any,
    selection: Any,
    private_paths: Any,
    supervisor_pid: Any = None,
    timeout_pid: Any = None,
    protected_paths: Any = None,
    run_nonce: Any = None,
    check: Any,
    read_charge: Any,
    clock_ns: Any = time.monotonic_ns,
) -> Any:
    """Source-owned collector records actual roles before config/binding exist."""
    import sys

    c.require(
        sys.platform == "linux"
        and os.environ.get("SAFE_EXECUTION_SITE") == "goethe-nhr",
        "RA_G1_EXECUTION_SITE",
    )
    job: Any = os.environ.get("SLURM_JOB_ID")
    c.require(
        type(job) is str and job.isdecimal() and str(int(job)) == job and int(job) > 0,
        "RA_G1_EXECUTION_SITE",
    )
    a.validate_selection(selection)
    supervisor_pid = os.getppid() if supervisor_pid is None else supervisor_pid
    supervisor, _ = _process_identity(
        supervisor_pid, check=check, read_charge=read_charge
    )
    timeout = None
    if timeout_pid is not None:
        timeout, parent = _process_identity(
            timeout_pid, check=check, read_charge=read_charge
        )
        c.require(parent == supervisor_pid, "RA_G1_PROCESS_SCOPE")
    environment = _live_domain(check=check, read_charge=read_charge)
    context = dict(
        schema_version=SUPERVISOR_CONTEXT,
        scope=scope,
        run_nonce=os.urandom(32).hex() if run_nonce is None else run_nonce,
        source_git_sha=source_git_sha,
        selection_sha256=o.digest(selection),
        adoption_sha256=selection["adoption_sha256"],
        slurm_job_id=int(job),
        boot_id=environment["boot_id"],
        created_mono_ns=clock_ns(),
        worker_uid=os.geteuid(),
        cgroup_namespace_inode=environment["cgroup_namespace_inode"],
        mount_namespace_inode=environment["mount_namespace_inode"],
        visible_cgroup_path=environment["domain"],
        supervisor=supervisor,
        timeout=timeout,
        private_paths=private_paths,
        protected_paths=protected_paths,
    )
    validate_supervisor_context(context)
    c.require(
        scope == selection["scope"] and source_git_sha == selection["source_git_sha"],
        "RA_G1_SELECTION_BINDING",
    )
    for key in ("allocation_root", "scratch_root"):
        a.private_root_identity(private_paths[key])
    a.private_root_identity(_path(private_paths["resource_evidence_root"]).parent)
    check()
    return context


def read_supervisor_context(request: Any, *, check: Any, read_charge: Any) -> Any:
    import json

    validate_execution_request(request)
    path = _path(request["supervisor_context_path"])
    ancestors = a.private_root_identity(path.parent)
    check()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        c.require(
            stat.S_ISREG(before.st_mode)
            and before.st_uid == os.geteuid()
            and stat.S_IMODE(before.st_mode) == 0o600
            and before.st_nlink == 1
            and 0 < before.st_size <= 65536,
            "RA_G1_ORIGINAL_CHANGED",
        )
        raw = m.charged_read(fd, 65536, read_charge)
        c.require(
            len(raw) == before.st_size
            and not m.charged_read(fd, 1, read_charge)
            and hashlib.sha256(raw).hexdigest() == request["supervisor_context_sha256"],
            "RA_G1_ORIGINAL_CHANGED",
        )

        def pairs(items: Any) -> Any:
            c.require(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
            return dict(items)

        context = json.loads(raw, object_pairs_hook=pairs)
        validate_supervisor_context(context)
        bounded.canonical_match(context, raw)
        after, current = os.fstat(fd), path.stat(follow_symlinks=False)
        c.require(
            _identity(before) == _identity(after) == _identity(current)
            and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            == (current.st_size, current.st_mtime_ns, current.st_ctime_ns)
            and ancestors == a.private_root_identity(path.parent),
            "RA_G1_ORIGINAL_CHANGED",
        )
        check()
        return context
    finally:
        os.close(fd)


def validate_current_supervisor(
    context: Any,
    *,
    binding: Any,
    selection: Any,
    evidence_root: Any,
    check: Any,
    read_charge: Any,
    clock_ns: Any = time.monotonic_ns,
) -> Any:
    """Current actual ancestry/UID/start ticks; no fabricated worker/wait status."""
    import sys

    validate_supervisor_context(context)
    c.require(
        sys.platform == "linux"
        and os.environ.get("SAFE_EXECUTION_SITE") == "goethe-nhr"
        and os.environ.get("SLURM_JOB_ID") == str(context["slurm_job_id"]),
        "RA_G1_EXECUTION_SITE",
    )
    c.require(
        context["scope"] == binding["scope"] == selection["scope"]
        and context["source_git_sha"]
        == binding["source_git_sha"]
        == selection["source_git_sha"]
        and context["selection_sha256"]
        == o.digest(selection)
        == binding["selection_sha256"]
        and context["adoption_sha256"]
        == binding["adoption_sha256"]
        == selection["adoption_sha256"]
        and _path(context["private_paths"]["resource_evidence_root"])
        == Path(evidence_root)
        and 0
        <= clock_ns() - context["created_mono_ns"]
        <= selection["limits"]["processing_ms"] * 1_000_000,
        "RA_G1_SUPERVISOR_CONTEXT",
    )
    environment = _live_domain(check=check, read_charge=read_charge)
    c.require(
        context["boot_id"] == environment["boot_id"]
        and context["visible_cgroup_path"] == environment["domain"]
        and context["cgroup_namespace_inode"] == environment["cgroup_namespace_inode"]
        and context["mount_namespace_inode"] == environment["mount_namespace_inode"],
        "RA_G1_VISIBLE_DOMAIN_CHANGED",
    )
    worker, parent = _process_identity(
        os.getpid(), check=check, read_charge=read_charge
    )
    supervisor, _ = _process_identity(
        context["supervisor"]["pid"], check=check, read_charge=read_charge
    )
    c.require(
        supervisor == context["supervisor"] and worker["uid"] == context["worker_uid"],
        "RA_G1_PROCESS_SCOPE",
    )
    roles = [worker, supervisor]
    if context["timeout"] is not None:
        timeout, timeout_parent = _process_identity(
            context["timeout"]["pid"], check=check, read_charge=read_charge
        )
        c.require(
            timeout == context["timeout"]
            and timeout_parent == supervisor["pid"]
            and parent == timeout["pid"],
            "RA_G1_PROCESS_SCOPE",
        )
        roles.append(timeout)
    else:
        c.require(parent == supervisor["pid"], "RA_G1_PROCESS_SCOPE")
    pids = tuple(role["pid"] for role in roles)
    c.require(len(set(pids)) == len(pids) <= 4, "RA_G1_PROCESS_SCOPE")
    for pid in pids:
        actual = _kernel_text(
            Path(f"/proc/{pid}/cgroup"), check=check, read_charge=read_charge
        ).strip()
        c.require(actual == environment["membership"], "RA_G1_PROCESS_SCOPE")
    for key in ("allocation_root", "scratch_root"):
        a.private_root_identity(context["private_paths"][key])
    a.private_root_identity(Path(evidence_root).parent)
    return dict(
        pids=pids,
        cgroup_path=Path(environment["domain"]),
        proc_paths=execution_proc_paths(context),
    )


def start_session(
    authority: Any,
    config: Any,
    binding: Any,
    selection: Any,
    evidence_root: Any,
    deadline_ns: Any,
    phase_id: Any,
    check: Any,
    counters: Any,
    charge: Any,
    read_charge: Any,
    *,
    clock_ns: Any = time.monotonic_ns,
    native_roots: Any = None,
    native_paths: Any = (),
    scope_start_ns: Any = None,
    bootstrap_prefix: Any = None,
    bootstrap_adoption_reader: Any = None,
    startup_trace: Any = None,
    start_to_start: bool = False,
) -> PhaseSession:
    """Actual CLI entry: exact original context, genuine Linux roles, real monitor."""
    request = validate_execution_request(config.get("resource_execution"))
    context = read_supervisor_context(request, check=check, read_charge=read_charge)
    scope_root = Path(evidence_root)
    if selection["scope"] in ("PUBLIC_SYNTHETIC_ONLY", "REPRESENTATIVE_NO_SERVICE"):
        declared = config.get(
            "output_directory", config.get("command_paths", {}).get("output")
        )
        scope_root = _path(declared)
        campaigns = config.get("campaigns")
        c.require(
            type(campaigns) is list
            and type(phase_id) is int
            and 1 <= phase_id <= len(campaigns) + 1,
            "RA_G1_EVIDENCE_NAMESPACE",
        )
        label = (
            campaigns[phase_id - 1]["label"]
            if phase_id <= len(campaigns)
            else "whole_task"
        )
        c.require(
            type(label) is str
            and "/" not in label
            and ".." not in label
            and Path(evidence_root) == scope_root / (label + "_resources"),
            "RA_G1_EVIDENCE_NAMESPACE",
        )
    actual = validate_current_supervisor(
        context,
        binding=binding,
        selection=selection,
        evidence_root=scope_root,
        check=check,
        read_charge=read_charge,
        clock_ns=clock_ns,
    )
    if context["protected_paths"] is not None:
        paths = config.get("resource_paths")
        c.require(
            type(paths) is dict
            and paths.get("bindings_path")
            == context["protected_paths"]["bindings_path"]
            and paths.get("registered_paths_record_sha256")
            == context["protected_paths"]["registered_paths_record_sha256"]
            and paths.get("resource_evidence_root") == str(evidence_root),
            "RA_G1_SUPERVISOR_CONTEXT",
        )
    owner = getattr(authority, "port", None)
    register = getattr(
        owner if owner is not None else authority, "registered_application_pids", None
    )
    if register is None:
        # This roster is immutable source-owned context plus the actual worker.
        # Additional application creation requires the existing invocation guard.
        roster = actual["pids"]

        def register() -> Any:
            return roster

    c.require(callable(register), "RA_G1_PROCESS_SCOPE")
    value = PhaseSession(
        authority=authority,
        binding=binding,
        selection=selection,
        resource_evidence_root=evidence_root,
        pids=actual["pids"],
        counter_provider=counters,
        charge=charge,
        check=check,
        deadline_ns=deadline_ns,
        phase_id=phase_id,
        cgroup_path=actual["cgroup_path"],
        native_paths=native_paths,
        native_roots=native_roots,
        admitted_process_provider=register,
        read_charge=read_charge,
        clock_ns=clock_ns,
        scope_start_ns=scope_start_ns,
        startup_trace=startup_trace,
        bootstrap_prefix=bootstrap_prefix,
        bootstrap_adoption_reader=bootstrap_adoption_reader if bootstrap_adoption_reader is not None else
            (lambda identity: authority._resource_evidence(identity, "adoptions")),
        start_to_start=start_to_start,
    )
    value.supervisor_context = context
    value.supervisor_context_sha256 = request["supervisor_context_sha256"]
    value.start()
    return value


ADMIN_BINDING = "stage12_resource_admin_role_binding_ra_g1_v1"
ADMIN_ROLES = {"COLLECTOR": 6, "REVIEW": 7, "BINDER": 8}
ADMIN_PHASES = {
    "REPRESENTATIVE_NO_SERVICE": ADMIN_ROLES,
    "PUBLIC_SYNTHETIC_ONLY": {
        "COLLECTOR": 13,
        "REVIEW": 13,
        "BINDER": 13,
        "PUBLIC_SETUP": 13,
    },
    "DEVELOPMENT_ONLY": {"PROTECTED_SETUP": 1},
    "DEVELOPMENT_LOCAL_PREPARATION": {"PROTECTED_SETUP": 1},
}
ADMIN_BINDING_SCHEMA: dict[str, Any] = {
    "schema_version": "=" + ADMIN_BINDING,
    "scope": o.enum(*a.SCOPES),
    "method": "=" + a.METHOD,
    "role": o.enum("COLLECTOR", "REVIEW", "BINDER", "PUBLIC_SETUP", "PROTECTED_SETUP"),
    **o.fields(
        "phase_id:P source_git_sha:G selection_sha256:D adoption_sha256:D supervisor_context_sha256:D risk_inventory_sha256:D process_pid:P process_start_ticks:U process_uid:U scope_start_mono_ns:U deadline_mono_ns:U"
    ),
    "service_authority": "=DENIED",
    "protected_input_authority": "=DENIED",
    "ap_dispatch_authority": "=DENIED",
}


class AdministrativeAuthority:
    """Resource-only source-owned metadata role; no scientific grants exist."""

    test_only = False
    service_authority = False
    diagnostic_scope = "ADMINISTRATIVE_RESOURCE_ONLY"

    def require(self, *args: Any, **kwargs: Any) -> Any:
        raise c.Stage12Error("RA_G1_ADMIN_AUTHORITY_DENIED")


class AdministrativePhaseSession(PhaseSession):
    """Same real monitor/opener DAG, with its separate non-AP binding family."""

    def validate_binding(self, binding: Any) -> None:
        a.shape(binding, ADMIN_BINDING_SCHEMA)
        c.require(
            binding["role"] in ADMIN_PHASES[binding["scope"]]
            and binding["phase_id"] == ADMIN_PHASES[binding["scope"]][binding["role"]],
            "RA_G1_ADMIN_SCOPE",
        )


def start_administrative_session(
    *,
    binding: Any,
    selection: Any,
    evidence_root: Any,
    pids: Any,
    cgroup_path: Any,
    counters: Any,
    charge: Any,
    check: Any,
    read_charge: Any,
    scope_start_ns: Any,
    deadline_ns: Any,
    observer_factory: Any = None,
    test_only: Any = False,
    directory_charge: Any = None,
    startup_trace: Any = None,
    bootstrap_prefix: Any = None,
    bootstrap_adoption_reader: Any = None,
    start_to_start: bool = False,
) -> AdministrativePhaseSession:
    """Metadata-only monitor entry, never a fabricated full AP binding."""
    authority = AdministrativeAuthority()
    authority.test_only = test_only is True
    c.require(
        binding["scope_start_mono_ns"] == scope_start_ns
        and binding["deadline_mono_ns"] == deadline_ns,
        "RA_G1_ADMIN_SCOPE",
    )
    value = AdministrativePhaseSession(
        authority=authority,
        binding=binding,
        selection=selection,
        resource_evidence_root=evidence_root,
        pids=pids,
        counter_provider=counters,
        charge=charge,
        check=check,
        read_charge=read_charge,
        deadline_ns=deadline_ns,
        phase_id=binding["phase_id"],
        cgroup_path=cgroup_path,
        native_paths=(),
        admitted_process_provider=lambda: pids,
        scope_start_ns=scope_start_ns,
        observer_factory=observer_factory,
        directory_charge=directory_charge,
        startup_trace=startup_trace,
        bootstrap_prefix=bootstrap_prefix,
        bootstrap_adoption_reader=bootstrap_adoption_reader,
        start_to_start=start_to_start,
    )
    value.start()
    return value

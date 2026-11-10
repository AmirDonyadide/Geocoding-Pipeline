"""Bounded actual shared-lease and independent monitor-failure regressions."""

from copy import deepcopy
import hashlib
import importlib
from pathlib import Path
import threading
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as monitor
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_scratch as scratch
from test_s12_ra_g1_accounting import inputs
from test_s12_ra_g1_core import H, observation, original_observation, selection


def cleanup(writer, resource=None):
    if resource is not None:
        resource.stop_event.set()
        if resource.thread.is_alive():
            resource.thread.join(2)
    with writer.condition:
        writer.closing = True
        writer.condition.notify_all()
    writer.thread.join(2)
    assert not writer.thread.is_alive()
    assert resource is None or not resource.thread.is_alive()


def make_writer(root, reads=None):
    root.mkdir(mode=0o700)
    originals = root / "originals"
    originals.mkdir(mode=0o700)
    return monitor.ObservationWriter(
        root / "observations.bin", maximum_rows=20,
        charge=lambda size, count: None, check=lambda: None,
        original_root=originals,
        charge_read=lambda calls, size: reads.append((calls, size)) if reads is not None else None,
    )


def test_independent_partition_and_nonreentrant_lifetime():
    assert sum(scratch.CAPS.values()) == 63616
    assert sum(scratch.RA_G1_CAPS.values()) == 65152
    assert scratch._locks["HASH"] is not scratch._locks["MONITOR_READBACK"]
    with scratch.lease("HASH"), scratch.ra_g1_lease("MONITOR_READBACK") as size:
        assert size == 512
        with pytest.raises(contract.Stage12Error, match="SCRATCH_REENTRANT"):
            with scratch.ra_g1_lease("MONITOR_READBACK"):
                pass
    with pytest.raises(contract.Stage12Error, match="SCRATCH_LIMIT"):
        with scratch.lease("MONITOR_READBACK"):
            pass
    with pytest.raises(contract.Stage12Error, match="SCRATCH_LIMIT"):
        with scratch.ra_g1_lease("MONITOR_READBACK", requested=513):
            pass


def test_real_backend_hash_hold_allows_actual_writer_ack(tmp_path, monkeypatch):
    held, release = threading.Event(), threading.Event()
    result, reads = {}, []
    real_readv = monitor.os.readv
    backend = Path(importlib.import_module("_hashlib").__file__).resolve(strict=True)

    def readv(fd, buffers):
        size = real_readv(fd, buffers)
        if threading.current_thread().name == "shared-lease-backend" and not held.is_set():
            result["owned"] = scratch._locks["HASH"]._is_owned()
            held.set()
            if not release.wait(3):
                raise RuntimeError("SYNTHETIC_HOLD_EXPIRED")
        return size

    def backend_reader():
        try:
            result["digest"] = assurance.bounded_backend_reader(lambda calls, size: None)(
                "_hashlib", backend, lambda: None)
        except BaseException as error:
            result["error_type"] = type(error).__name__

    monkeypatch.setattr(monitor.os, "readv", readv)
    thread = threading.Thread(target=backend_reader, name="shared-lease-backend")
    writer = make_writer(tmp_path / "actual", reads)
    try:
        thread.start()
        assert held.wait(2)
        raw = b"x" * monitor.MAX_ORIGINAL_BYTES
        writer.stage_original(raw)
        row = observation(selection(), enter=time.monotonic_ns())
        deadline = time.monotonic_ns() + 1_000_000_000
        writer.append(monitor.pack_observation(row), 1, deadline)
        writer.wait(1, deadline)
        assert result["owned"] and thread.is_alive() and not release.is_set()
        assert writer.acked == 1 and not writer.poisoned
        assert sum(calls for calls, _ in reads) == 31
        assert sum(size for _, size in reads) == 16384
        release.set()
        thread.join(2)
        assert result.get("digest") == hashlib.sha256(backend.read_bytes()).hexdigest()
        writer.close(time.monotonic_ns() + 1_000_000_000)
    finally:
        release.set()
        if thread.is_alive():
            thread.join(2)
        cleanup(writer)
    assert not thread.is_alive()


@pytest.mark.parametrize("mode,code", [
    ("short", "RA_G1_WRITE_UNCERTAIN"),
    ("changed", "RA_G1_ORIGINAL_CHANGED"),
])
def test_actual_readback_failure_never_acknowledges(tmp_path, monkeypatch, mode, code):
    writer = make_writer(tmp_path / mode)
    real_pread = monitor.os.pread

    def pread(fd, size, offset):
        raw = real_pread(fd, size, offset)
        if fd != writer.fd and offset == 0:
            return raw[:-1] if mode == "short" else b"!" + raw[1:]
        return raw

    monkeypatch.setattr(monitor.os, "pread", pread)
    try:
        writer.stage_original(b"x" * monitor.MAX_ORIGINAL_BYTES)
        writer.append(monitor.pack_observation(observation(selection())), 1,
                      time.monotonic_ns() + 2_000_000_000)
        with pytest.raises(contract.Stage12Error, match="WRITE_UNCERTAIN"):
            writer.wait(1, time.monotonic_ns() + 2_000_000_000)
        state = writer.diagnostic_snapshot()
        assert state["poisoned"] and state["acked"] == 0
        assert state["first_failure"]["code"] == code
        with pytest.raises(contract.Stage12Error, match="WRITE_UNCERTAIN"):
            writer.append(b"x" * monitor.CODEC_BYTES, 2,
                          time.monotonic_ns() + 2_000_000_000)
    finally:
        cleanup(writer)


class Trace:
    def __init__(self):
        self.snapshots = []
        self.failed = threading.Event()

    def __call__(self, *args, **kwargs):
        pass

    def monitor_failure(self, snapshot):
        self.snapshots.append(snapshot)
        self.failed.set()


@pytest.mark.parametrize("mode,code,number,source", [
    ("observer", "RA_G1_MONITOR_INCOMPLETE", 5, "MONITOR"),
    ("writer", "RA_G1_WRITE_UNCERTAIN", 28, "WRITER"),
])
def test_periodic_actual_primary_survives_barrier(tmp_path, monkeypatch, mode, code, number, source):
    selected = selection()
    writer = make_writer(tmp_path / mode)
    trace = Trace()
    fail = threading.Event()
    real_fsync = monitor.os.fsync

    def fsync(fd):
        if mode == "writer" and fail.is_set() and fd == writer.fd:
            raise OSError(28, "UNSAFE_SYNTHETIC_DETAIL")
        return real_fsync(fd)

    def observer(kind):
        if mode == "observer" and kind == "PERIODIC":
            raise OSError(5, "UNSAFE_SYNTHETIC_DETAIL")
        row = observation(selected, enter=time.monotonic_ns(), kind=kind)
        row["visible_identity_inventory_sha256"] = writer.stage_original(
            contract.canonical(original_observation(row)))
        return {key: row[key] for key in (
            "readings", "counters", "native_visibility", "visible_identity_inventory_sha256")}

    monkeypatch.setattr(monitor.os, "fsync", fsync)
    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        check=lambda: None, startup_trace=trace)
    try:
        resource.start()
        fail.set()
        assert trace.failed.wait(2)
        with pytest.raises(contract.Stage12Error, match=code):
            resource.barrier()
        state = resource.diagnostic_snapshot()
        fault = state["first_primary"]
        assert fault["family"] == "OS_ERROR" and fault["errno"] == number
        assert fault["source"] == source
        assert "UNSAFE_SYNTHETIC_DETAIL" not in repr(state)
        assert len(trace.snapshots) == 1
        if mode == "writer":
            assert state["writer"]["poisoned"] and state["writer"]["acked"] == 1
            assert fault["stage"] == "CODEC_FSYNC"
        else:
            assert not state["writer"]["poisoned"]
            assert fault["stage"] == "OBSERVER"
    finally:
        cleanup(writer, resource)


@pytest.mark.parametrize("scope,bootstrap", [
    ("REPRESENTATIVE_NO_SERVICE", True),
    ("PUBLIC_SYNTHETIC_ONLY", False),
])
def test_new_compiler_primitive_exact_deltas_and_old_grammar(scope, bootstrap):
    sources, backends = inputs()
    previous, old_caps = accounting.compile_inventory(
        sources, backends, scope, bootstrap_successor=bootstrap)
    current, caps = accounting.compile_inventory(
        sources, backends, scope, bootstrap_successor=bootstrap,
        shared_lease_successor=True)
    assert current["schema_version"] == accounting.SHARED_LEASE_VERSION
    assert current["bootstrap_proof_record_count"] == (3 if bootstrap else 0)
    assert accounting.validate_inventory(previous) == previous
    assert accounting.validate_inventory(current) == current
    assert set(current) == set(accounting.descriptor(shared_lease_successor=True)["outer_fields"])
    rows = sum(row["maximum_rows"] for row in current["monitor_streams"])
    assert caps["original_read_calls"] - old_caps["original_read_calls"] == 26 * rows
    assert caps["check_calls"] - old_caps["check_calls"] == 26 * rows
    assert caps["identity_calls"] - old_caps["identity_calls"] == 26 * rows
    assert caps["original_read_bytes"] == old_caps["original_read_bytes"]
    changed = deepcopy(current)
    row = next(row for row in changed["cost_rows"]
               if row["component"] == "MONITOR_WRITER_ORIGINAL_AND_CODEC_READBACK")
    row["per_invocation_read_calls"] = 5
    with pytest.raises(accounting.AccountingError, match="CHANGED"):
        accounting.validate_inventory(changed)


@pytest.mark.parametrize("fail_read", [False, True])
def test_backend_backing_and_traceback_views_end_inside_hash_lease(monkeypatch, fail_read):
    destroyed, retained_views = [], []
    real_readv = monitor.os.readv

    class Tracked(bytearray):
        def __del__(self):
            destroyed.append(scratch._locks["HASH"]._is_owned())

    def readv(fd, buffers):
        if fail_read:
            retained_views.extend(buffers)
            raise OSError(5, "UNSAFE_SYNTHETIC_DETAIL")
        return real_readv(fd, buffers)

    monkeypatch.setattr(assurance, "bytearray", Tracked, raising=False)
    monkeypatch.setattr(monitor.os, "readv", readv)
    backend = Path(importlib.import_module("_hashlib").__file__).resolve(strict=True)
    reader = assurance.bounded_backend_reader(lambda calls, size: None)
    if fail_read:
        with pytest.raises(OSError) as captured:
            reader("_hashlib", backend, lambda: None)
        assert captured.value.__traceback__ is not None
        assert destroyed == [True]
        for view in retained_views:
            with pytest.raises(ValueError):
                len(view)
    else:
        assert reader("_hashlib", backend, lambda: None) == hashlib.sha256(
            backend.read_bytes()).hexdigest()
        assert destroyed == [True]


@pytest.mark.parametrize("offset", [None, 0])
def test_failed_byte_charge_traceback_releases_readback_bytes(tmp_path, offset):
    path = tmp_path / "bounded-original"
    path.write_bytes(b"x" * 512)
    path.chmod(0o600)
    calls = []

    def charge(calls_delta, bytes_delta):
        calls.append((calls_delta, bytes_delta))
        if bytes_delta:
            raise contract.Stage12Error("RA_G1_COUNTER_LIMIT")

    fd = monitor.os.open(path, monitor.os.O_RDONLY | monitor.os.O_NOFOLLOW)
    try:
        with pytest.raises(contract.Stage12Error, match="COUNTER_LIMIT") as captured:
            with scratch.ra_g1_lease("MONITOR_READBACK"):
                monitor.charged_read(fd, 512, charge, offset=offset)
        retained = captured.value.__traceback__
        frames = []
        while retained is not None:
            frame = retained.tb_frame
            if frame.f_code is monitor.charged_read.__code__:
                frames.append(frame)
            retained = retained.tb_next
        assert frames
        assert all("raw" not in frame.f_locals for frame in frames)
        assert all(
            not any(type(value) is bytes and len(value) == 512
                    for value in frame.f_locals.values())
            for frame in frames)
        assert calls == [(1, 0), (0, 512)]
    finally:
        monitor.os.close(fd)


def test_writer_classifier_failure_cannot_suppress_poison(tmp_path, monkeypatch):
    writer = make_writer(tmp_path / "classifier")
    classified_after_poison, thread_errors = [], []

    def check():
        if threading.current_thread() is writer.thread:
            raise OSError(5, "UNSAFE_SYNTHETIC_DETAIL")

    def classify(*args, **kwargs):
        classified_after_poison.append(writer.poisoned)
        raise MemoryError

    monkeypatch.setattr(writer, "check", check)
    monkeypatch.setattr(monitor, "_diagnostic_fault", classify)
    monkeypatch.setattr(threading, "excepthook",
                        lambda event: thread_errors.append(event.exc_type.__name__))
    try:
        writer.stage_original(b"synthetic")
        writer.append(monitor.pack_observation(observation(selection())), 1,
                      time.monotonic_ns() + 2_000_000_000)
        with pytest.raises(contract.Stage12Error, match="WRITE_UNCERTAIN"):
            writer.wait(1, time.monotonic_ns() + 2_000_000_000)
        writer.thread.join(1)
        state = writer.diagnostic_snapshot()
        assert state["poisoned"] and not state["released"]
        assert state["rows"] == 1 and state["acked"] == 0
        assert state["first_failure"] is None
        assert classified_after_poison == [True] and thread_errors == []
    finally:
        cleanup(writer)


def test_timeout_classifier_failure_cannot_suppress_poison(tmp_path, monkeypatch):
    writer = make_writer(tmp_path / "timeout")
    entered, release = threading.Event(), threading.Event()
    classified_after_poison = []

    def check():
        if threading.current_thread() is writer.thread:
            entered.set()
            assert release.wait(2)

    def classify(*args, **kwargs):
        classified_after_poison.append(writer.poisoned)
        raise MemoryError

    monkeypatch.setattr(writer, "check", check)
    monkeypatch.setattr(monitor, "_diagnostic_fault", classify)
    try:
        writer.stage_original(b"synthetic")
        writer.append(monitor.pack_observation(observation(selection())), 1,
                      time.monotonic_ns() + 2_000_000_000)
        assert entered.wait(1)
        with pytest.raises(contract.Stage12Error, match="WRITE_UNCERTAIN"):
            writer.wait(1, time.monotonic_ns() + 20_000_000)
        assert writer.poisoned and classified_after_poison == [True]
    finally:
        release.set()
        cleanup(writer)
    assert writer.poisoned and not writer.released


@pytest.mark.parametrize("broken", ["classifier", "snapshot", "callback"])
def test_monitor_diagnostic_fault_cannot_suppress_failure_or_stop(
    tmp_path, monkeypatch, broken
):
    writer = make_writer(tmp_path / broken)
    selected, trace = selection(), Trace()
    mandatory_observed, thread_errors = [], []

    def observer(kind):
        if kind == "PERIODIC":
            raise OSError(5, "UNSAFE_SYNTHETIC_DETAIL")
        row = observation(selected, enter=time.monotonic_ns(), kind=kind)
        row["visible_identity_inventory_sha256"] = writer.stage_original(
            contract.canonical(original_observation(row)))
        return {key: row[key] for key in (
            "readings", "counters", "native_visibility", "visible_identity_inventory_sha256")}

    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        check=lambda: None, startup_trace=trace)

    def diagnostic_failure(*args, **kwargs):
        mandatory_observed.append(
            resource.failure is not None and resource.stop_event.is_set())
        raise MemoryError

    monkeypatch.setattr(threading, "excepthook",
                        lambda event: thread_errors.append(event.exc_type.__name__))
    try:
        resource.start()
        if broken == "classifier":
            monkeypatch.setattr(monitor, "_diagnostic_fault", diagnostic_failure)
        elif broken == "snapshot":
            monkeypatch.setattr(writer, "diagnostic_snapshot", diagnostic_failure)
        else:
            monkeypatch.setattr(trace, "monitor_failure", diagnostic_failure)
        resource.thread.join(2)
        assert not resource.thread.is_alive()
        assert resource.failure == "RA_G1_MONITOR_INCOMPLETE"
        assert resource.stop_event.is_set()
        with pytest.raises(contract.Stage12Error, match="MONITOR_INCOMPLETE"):
            resource.barrier()
        assert mandatory_observed and all(mandatory_observed)
        assert thread_errors == [] and not writer.poisoned
        if broken == "callback":
            assert resource.first_primary["errno"] == 5
    finally:
        cleanup(writer, resource)


@pytest.mark.parametrize("writer_first", [False, True])
def test_actual_composed_primary_uses_observed_chronology(
    tmp_path, monkeypatch, writer_first
):
    writer = make_writer(tmp_path / ("writer-first" if writer_first else "observer-first"))
    selected, events = selection(), []
    fired = False
    original_snapshot = writer.diagnostic_snapshot

    def check():
        if threading.current_thread() is writer.thread:
            events.append(("writer", time.monotonic_ns()))
            raise OSError(28, "UNSAFE_LATER_DETAIL")

    def trigger_writer():
        writer.stage_original(b"synthetic-composed")
        writer.append(monitor.pack_observation(observation(selected)), 1,
                      time.monotonic_ns() + 2_000_000_000)
        writer.thread.join(1)
        assert not writer.thread.is_alive() and writer.poisoned

    def observer(kind):
        events.append(("observer", time.monotonic_ns()))
        raise OSError(5, "UNSAFE_FIRST_DETAIL")

    def snapshot():
        nonlocal fired
        if not fired:
            fired = True
            trigger_writer()
        return original_snapshot()

    monkeypatch.setattr(writer, "check", check)
    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000, check=lambda: None)
    try:
        if writer_first:
            trigger_writer()
        else:
            monkeypatch.setattr(writer, "diagnostic_snapshot", snapshot)
        with pytest.raises(OSError) as actual:
            resource.start()
        assert actual.value.errno == 5
        state = resource.diagnostic_snapshot()
        assert state["first_primary"]["errno"] == (28 if writer_first else 5)
        assert state["first_primary"]["source"] == ("WRITER" if writer_first else "MONITOR")
        assert [name for name, _ in events] == (
            ["writer", "observer"] if writer_first else ["observer", "writer"])
        assert events[0][1] < events[1][1]
        if not writer_first:
            assert state["first_primary"]["mono_ns"] < state["writer"]["first_failure"]["mono_ns"]
        assert resource.failure == "RA_G1_MONITOR_INCOMPLETE"
        assert resource.stop_event.is_set()
    finally:
        cleanup(writer, resource)


@pytest.mark.parametrize("classifier_broken", [False, True])
def test_actual_barrier_cannot_steal_first_latch_primary(
    tmp_path, monkeypatch, classifier_broken
):
    writer = make_writer(tmp_path / ("unknown-owner" if classifier_broken else "known-owner"))
    selected, trace = selection(), Trace()
    paused, release = threading.Event(), threading.Event()

    def observer(kind):
        if kind == "PERIODIC":
            raise OSError(5, "UNSAFE_INITIATING_DETAIL")
        row = observation(selected, enter=time.monotonic_ns(), kind=kind)
        row["visible_identity_inventory_sha256"] = writer.stage_original(
            contract.canonical(original_observation(row)))
        return {key: row[key] for key in (
            "readings", "counters", "native_visibility", "visible_identity_inventory_sha256")}

    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        check=lambda: None, startup_trace=trace)
    real_stop = resource.stop_event.set
    real_classify = monitor._diagnostic_fault

    def stop():
        real_stop()
        if threading.current_thread() is resource.thread and not paused.is_set():
            paused.set()
            assert release.wait(2)

    def classify(error, **kwargs):
        if kwargs["source"] == "MONITOR":
            raise MemoryError
        return real_classify(error, **kwargs)

    def later_writer_check():
        if threading.current_thread() is writer.thread:
            raise OSError(28, "UNSAFE_LATER_DETAIL")

    try:
        resource.start()
        monkeypatch.setattr(resource.stop_event, "set", stop)
        if classifier_broken:
            monkeypatch.setattr(monitor, "_diagnostic_fault", classify)
        assert paused.wait(2)
        assert resource.failure == "RA_G1_MONITOR_INCOMPLETE"
        assert resource.stop_event.is_set() and resource.first_primary is None
        with pytest.raises(contract.Stage12Error, match="MONITOR_INCOMPLETE"):
            resource.barrier()
        assert resource.first_primary is None and trace.snapshots == []
        release.set()
        resource.thread.join(2)
        assert not resource.thread.is_alive()
        initial = resource.diagnostic_snapshot()
        if classifier_broken:
            assert initial["first_primary"] is None
        else:
            assert initial["first_primary"]["errno"] == 5
        with pytest.raises(contract.Stage12Error, match="MONITOR_INCOMPLETE"):
            resource.barrier()
        assert len(trace.snapshots) == 1

        monkeypatch.setattr(writer, "check", later_writer_check)
        row = observation(selected, enter=time.monotonic_ns(), kind="PERIODIC")
        row.update(seq=2, previous_sha256=resource.head)
        row["visible_identity_inventory_sha256"] = writer.stage_original(b"synthetic-later")
        writer.append(monitor.pack_observation(row), 2,
                      time.monotonic_ns() + 1_000_000_000)
        writer.thread.join(1)
        assert not writer.thread.is_alive() and writer.poisoned
        final = resource.diagnostic_snapshot()
        assert final["writer"]["first_failure"]["errno"] == 28
        if classifier_broken:
            assert final["first_primary"] is None
            assert trace.snapshots[0]["first_primary"] is None
        else:
            assert final["first_primary"]["errno"] == 5
            assert trace.snapshots[0]["first_primary"]["errno"] == 5
        assert len(trace.snapshots) == 1
    finally:
        release.set()
        cleanup(writer, resource)


def test_unlatched_monitor_snapshot_preserves_writer_only_fault(tmp_path, monkeypatch):
    writer = make_writer(tmp_path / "writer-only")
    resource = monitor.ResourceMonitor(
        observer=lambda kind: None, writer=writer, selected=selection(),
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000, check=lambda: None)

    def check():
        if threading.current_thread() is writer.thread:
            raise OSError(28, "UNSAFE_SYNTHETIC_DETAIL")

    monkeypatch.setattr(writer, "check", check)
    try:
        writer.stage_original(b"synthetic-writer-only")
        writer.append(monitor.pack_observation(observation(selection())), 1,
                      time.monotonic_ns() + 1_000_000_000)
        writer.thread.join(1)
        assert not writer.thread.is_alive()
        state = resource.diagnostic_snapshot()
        assert state["monitor_failure"] is None
        assert state["first_primary"]["source"] == "WRITER"
        assert state["first_primary"]["errno"] == 28
    finally:
        cleanup(writer, resource)


def test_lost_local_classification_cannot_become_writer_snapshot_cause(
    tmp_path, monkeypatch
):
    writer = make_writer(tmp_path / "unknown-local-snapshot")
    selected = selection()
    real_classify, real_snapshot = monitor._diagnostic_fault, writer.diagnostic_snapshot
    triggered = False

    def check():
        if threading.current_thread() is writer.thread:
            raise OSError(28, "UNSAFE_LATER_DETAIL")

    def observer(kind):
        raise OSError(5, "UNSAFE_INITIATING_DETAIL")

    def classify(error, **kwargs):
        if kwargs["source"] == "MONITOR":
            raise MemoryError
        return real_classify(error, **kwargs)

    def snapshot():
        nonlocal triggered
        if not triggered:
            triggered = True
            writer.stage_original(b"synthetic-later-snapshot")
            writer.append(monitor.pack_observation(observation(selected)), 1,
                          time.monotonic_ns() + 1_000_000_000)
            writer.thread.join(1)
            assert not writer.thread.is_alive()
        return real_snapshot()

    monkeypatch.setattr(writer, "check", check)
    monkeypatch.setattr(writer, "diagnostic_snapshot", snapshot)
    monkeypatch.setattr(monitor, "_diagnostic_fault", classify)
    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000, check=lambda: None)
    try:
        with pytest.raises(OSError) as original:
            resource.start()
        assert original.value.errno == 5
        state = resource.diagnostic_snapshot()
        assert resource.failure == "RA_G1_MONITOR_INCOMPLETE"
        assert resource.stop_event.is_set() and state["first_primary"] is None
        assert state["writer"]["first_failure"]["errno"] == 28
        with pytest.raises(contract.Stage12Error, match="MONITOR_INCOMPLETE"):
            resource.barrier()
        assert resource.diagnostic_snapshot()["first_primary"] is None
    finally:
        cleanup(writer, resource)


@pytest.mark.parametrize("claim_clock_broken", [False, True])
def test_claim_time_precedes_stop_interleaved_writer_and_clock_fault_still_stops(
    tmp_path, monkeypatch, claim_clock_broken
):
    writer = make_writer(tmp_path / ("broken-claim-clock" if claim_clock_broken else "claim-clock"))
    selected, events = selection(), []
    triggered = False

    def check():
        if threading.current_thread() is writer.thread:
            events.append(("writer", time.monotonic_ns()))
            raise OSError(28, "UNSAFE_LATER_DETAIL")

    def observer(kind):
        events.append(("observer", time.monotonic_ns()))
        raise OSError(5, "UNSAFE_INITIATING_DETAIL")

    resource = monitor.ResourceMonitor(
        observer=observer, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000, check=lambda: None)
    real_stop = resource.stop_event.set

    def clock():
        if claim_clock_broken and resource.failure is not None:
            raise MemoryError
        return time.monotonic_ns()

    def stop():
        nonlocal triggered
        real_stop()
        if not triggered:
            triggered = True
            writer.stage_original(b"synthetic-during-stop")
            writer.append(monitor.pack_observation(observation(selected)), 1,
                          time.monotonic_ns() + 1_000_000_000)
            writer.thread.join(1)
            assert not writer.thread.is_alive()

    monkeypatch.setattr(writer, "check", check)
    monkeypatch.setattr(resource, "clock", clock)
    monkeypatch.setattr(resource.stop_event, "set", stop)
    try:
        with pytest.raises(OSError) as original:
            resource.start()
        assert original.value.errno == 5
        state = resource.diagnostic_snapshot()
        assert resource.stop_event.is_set()
        assert resource.failure == "RA_G1_MONITOR_INCOMPLETE"
        assert state["first_primary"]["errno"] == 5
        assert state["writer"]["first_failure"]["errno"] == 28
        assert [name for name, _ in events] == ["observer", "writer"]
        if claim_clock_broken:
            assert state["first_primary"]["mono_ns"] is None
        else:
            assert events[0][1] <= state["first_primary"]["mono_ns"] < events[1][1]
        with pytest.raises(contract.Stage12Error, match="MONITOR_INCOMPLETE"):
            resource.barrier()
        assert resource.diagnostic_snapshot()["first_primary"]["errno"] == 5
    finally:
        cleanup(writer, resource)

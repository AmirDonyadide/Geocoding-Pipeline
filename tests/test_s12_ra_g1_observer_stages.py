"""Opt-in coarse observer timing; Linux paths below are private Mac/unit fixtures.

No fixture grants kernel, service or protected-data authority. Original LinuxObserver
checks, reads, parser, digest and KERNEL lease remain the actual implementations.
"""

import ast
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from types import MethodType, SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_s12_ra_g1_core import H, selection
from test_stage12_ra_g1_native_root_sessions import KernelSession
from test_s12_ra_g1_monitor_shared_scratch import cleanup, make_writer


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    value = KernelSession(tmp_path, monkeypatch)
    # Freeze one actual filesystem metadata sample as a controlled fixture input;
    # shared free space can otherwise change between the two matched runs.
    filesystem = os.statvfs(value.output)
    monkeypatch.setattr(os, "statvfs", lambda path: filesystem)
    yield value
    value.cleanup()


def owner():
    return d.Failures(SimpleNamespace(now_ns=time.monotonic_ns), observer=True)


def observer(kernel, *, failures=None, transcript=None, counter=None, clock=None):
    transcript = [] if transcript is None else transcript

    def checked():
        transcript.append(("CHECK",))

    def charged(calls, size):
        transcript.append(("READ_CHARGE", calls, size))

    def admitted():
        transcript.append(("ADMITTED",))
        return (os.getpid(),)

    def counters():
        transcript.append(("COUNTERS",))
        return {key: 0 for key in m.COUNTERS} if counter is None else counter()

    def retain(original):
        assert m.scratch._locks["KERNEL"]._is_owned()
        raw = c.canonical(original)
        transcript.append(("RETAIN", len(raw), hashlib.sha256(raw).hexdigest()))
        return m.old.digest(original)

    return m.LinuxObserver(
        pids=(os.getpid(),), cgroup_path=kernel.domain, root=kernel.output,
        native_paths=(kernel.native,), native_roots=(kernel.output,),
        counter_provider=counters, retain_originals=retain,
        admitted_process_provider=admitted, read_charge=charged, check=checked,
        clock_ns=(lambda: 123) if clock is None else clock,
        observer_stages=failures, observer_phase_id=1,
    )


def instrument_original_io(monkeypatch, transcript):
    # These are test observers of the actual I/O, not fake reader successes.
    opened, readv, stated, statvfs = os.open, os.readv, Path.stat, os.statvfs

    def open_(path, flags, *args, **kwargs):
        transcript.append(("OPEN", os.fspath(path), flags))
        return opened(path, flags, *args, **kwargs)

    def read_(fd, buffers):
        returned = readv(fd, buffers)
        raw = b"".join(bytes(part) for part in buffers)[:returned]
        transcript.append(("READV", returned, hashlib.sha256(raw).hexdigest()))
        return returned

    def stat_(path, *args, **kwargs):
        transcript.append(("STAT", os.fspath(path)))
        return stated(path, *args, **kwargs)

    def filesystem_(path):
        transcript.append(("STATVFS", os.fspath(path)))
        return statvfs(path)

    monkeypatch.setattr(os, "open", open_)
    monkeypatch.setattr(os, "readv", read_)
    monkeypatch.setattr(Path, "stat", stat_)
    monkeypatch.setattr(os, "statvfs", filesystem_)


def test_actual_original_transcript_results_and_clock_calls_match(kernel, monkeypatch, record_property):
    calls = []
    failures = owner()
    plain = observer(kernel, transcript=calls)
    baseline_call = MethodType(original_observer_body(), plain)
    disabled = observer(kernel, transcript=calls)
    observed = observer(kernel, failures=failures, transcript=calls)
    instrument_original_io(monkeypatch, calls)
    elapsed, cpu, results, transcripts = [], [], [], []
    for current in (baseline_call, disabled, observed):
        calls.clear()
        started, thread_started = time.monotonic_ns(), time.thread_time_ns()
        result = [current("START" if index == 0 else "PERIODIC") for index in range(8)]
        cpu.append(time.thread_time_ns() - thread_started)
        elapsed.append(time.monotonic_ns() - started)
        results.append(result)
        transcripts.append(deepcopy(calls))
    assert results[0] == results[1] == results[2]
    assert transcripts[0] == transcripts[1] == transcripts[2]
    assert plain.read_calls == disabled.read_calls == observed.read_calls
    assert plain.read_bytes == disabled.read_bytes == observed.read_bytes
    assert plain.stat_calls == disabled.stat_calls == observed.stat_calls
    snapshot = failures.snapshot()["observer_stages"]
    assert snapshot["calls"] == 8 and not snapshot["retention_uncertain"]
    assert snapshot["last_acquisition"]["returned"] is True
    assert set(snapshot["totals"]) == set(d.OBSERVER_ROWS)
    assert all(row["count"] == 8 for row in snapshot["totals"].values())
    record_property("matched_original_io", json.dumps({
        "operations": len(transcripts[0]), "original_read_calls": plain.read_calls,
        "returned_original_bytes": plain.read_bytes, "native_stat_calls": plain.stat_calls,
        "baseline_wall_ns": elapsed[0], "disabled_wall_ns": elapsed[1], "observed_wall_ns": elapsed[2],
        "baseline_thread_cpu_ns": cpu[0], "disabled_thread_cpu_ns": cpu[1], "observed_thread_cpu_ns": cpu[2],
        "baseline_source": "EXACT_HASH_VERIFIED_PREDELTA_CALL_AST_IN_ACTUAL_MONITOR_NAMESPACE",
        "scope": "8_CALL_LOCAL_REHEARSAL_NO_WHOLE_WORKFLOW_OR_GOETHE_OVERHEAD_BOUND",
    }, sort_keys=True))


def test_default_off_does_not_read_any_instrumentation_clock(kernel, monkeypatch):
    current = observer(kernel, failures=d.Failures(SimpleNamespace(now_ns=lambda: 999)))

    def forbidden(_owner):
        raise AssertionError("instrumentation clock invoked while disabled")

    monkeypatch.setattr(d, "_observer_sample", forbidden)
    assert current("START")["visible_identity_inventory_sha256"]
    assert "observer_stages" not in d.Failures(SimpleNamespace(now_ns=lambda: 999)).snapshot()


def test_original_enforcing_clock_callback_count_is_unchanged(kernel):
    counts = [0]

    def clock():
        counts[0] += 1
        return 123

    for failure in (None, owner()):
        counts[0] = 0
        current = observer(kernel, failures=failure, clock=clock)
        current("START")
        if failure is None:
            baseline = counts[0]
        else:
            assert counts[0] == baseline > 0


def test_actual_lease_and_stage_latency_are_separate(kernel, monkeypatch):
    failures = owner()
    lease = m.scratch.lease

    @contextmanager
    def delayed(key):
        time.sleep(0.012)  # Controlled entry latency; genuine lease still acquired.
        with lease(key) as size:
            yield size

    monkeypatch.setattr(m.scratch, "lease", delayed)

    def counters():
        assert m.scratch._locks["KERNEL"]._is_owned()
        time.sleep(0.008)
        return {key: 0 for key in m.COUNTERS}

    observer(kernel, failures=failures, counter=counters)("START")
    episode = failures.snapshot()["observer_stages"]["last_acquisition"]
    assert episode["stages"]["KERNEL_LEASE_WAIT"]["wall_ns"] >= 10_000_000
    assert episode["stages"]["COUNTERS"]["wall_ns"] >= 6_000_000
    assert episode["returned"] and episode["phase_id"] == 1
    assert sum(row["wall_ns"] for row in episode["stages"].values()) == episode["wall_ns"]
    assert sum(row["thread_cpu_ns"] for row in episode["stages"].values()) == episode["thread_cpu_ns"]
    # The wall/CPU difference is measured, with no descheduling/I/O-cause inference.


def test_real_lease_reentrancy_failure_is_retained_before_cleanup(kernel):
    failures = owner()
    current = observer(kernel, failures=failures)
    with m.scratch.lease("KERNEL"):
        with pytest.raises(c.Stage12Error, match="WF_AP2_SCRATCH_REENTRANT"):
            current("START")
        first = failures.snapshot()["observer_stages"]["first_failed_acquisition"]
        assert first["failure"]["stage"] == "KERNEL_LEASE_WAIT"
        assert first["failure"]["code"] == "WF_AP2_SCRATCH_REENTRANT"
        assert first["snapshot_point"] == "FIRST_STAGE_FAILURE_BEFORE_CLEANUP"
        assert first["observed_end_wall_ns"] >= first["start_wall_ns"]


def test_primary_stage_failure_is_not_replaced_by_lease_cleanup(kernel, monkeypatch):
    failures = owner()
    primary = OSError(28, "PRIVATE_PAYLOAD_NEVER_RETAIN")
    cleanup_error = RuntimeError("PRIVATE_CLEANUP_NEVER_RETAIN")
    real_lease = m.scratch.lease

    @contextmanager
    def lease(key):
        with real_lease(key):
            try:
                yield
            finally:
                raise cleanup_error

    def counters():
        raise primary

    monkeypatch.setattr(m.scratch, "lease", lease)
    with pytest.raises(RuntimeError) as caught:
        observer(kernel, failures=failures, counter=counters)("START")
    assert caught.value is cleanup_error  # Preserve actual context-manager semantics.
    snapshot = failures.snapshot()["observer_stages"]
    first = snapshot["first_failed_acquisition"]
    assert first["failure"]["stage"] == "COUNTERS"
    assert first["failure"]["family"] == "OS_ERROR" and first["failure"]["errno"] == 28
    assert first["end_wall_ns"] is None  # Recorded before cleanup, not backdated.
    assert "PRIVATE" not in json.dumps(snapshot)


def test_observer_recording_fault_cannot_change_original_return(kernel, monkeypatch):
    failures = owner()
    plain = observer(kernel)("START")

    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE_INSTRUMENTATION_PAYLOAD")

    monkeypatch.setattr(d._ObserverCall, "stage_complete", broken)
    assert observer(kernel, failures=failures)("START") == plain
    snapshot = failures.snapshot()["observer_stages"]
    assert snapshot["retention_uncertain"] and snapshot["observation_faults"] > 0
    assert "PRIVATE" not in json.dumps(snapshot)


def test_slow_observer_return_is_retained_before_real_coverage_failure(kernel, tmp_path):
    failures = owner()

    def counters():
        time.sleep(1.025)
        return {key: 0 for key in m.COUNTERS}

    current = observer(kernel, failures=failures, counter=counters, clock=time.monotonic_ns)
    writer = make_writer(tmp_path / "resource-writer")
    selected = selection()
    resource = m.ResourceMonitor(
        observer=current, writer=writer, selected=selected,
        binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 4_000_000_000, check=lambda: None,
    )
    try:
        with pytest.raises(c.Stage12Error, match="RA_G1_MONITOR_GAP"):
            resource._acquire("START")
        first = failures.snapshot()["observer_stages"]["first_slow_acquisition"]
        assert first["returned"] and first["wall_ns"] > 1_000_000_000
        assert first["stages"]["COUNTERS"]["wall_ns"] >= 1_000_000_000
        assert resource.first_primary["stage"] == "COVERAGE"
        assert resource.failure == "RA_G1_MONITOR_GAP"
        # A later actual error does not replace the first slow return.
        def rejected():
            raise OSError(5, "UNSAFE_SECONDARY")
        with pytest.raises(OSError):
            observer(kernel, failures=failures, counter=rejected)("PERIODIC")
        assert failures.snapshot()["observer_stages"]["first_slow_acquisition"] == first
    finally:
        cleanup(writer, resource)


def test_thread_cpu_unavailable_is_unknown_and_does_not_change_original(kernel, monkeypatch):
    failures = owner()
    plain = observer(kernel)("START")
    monkeypatch.delattr(d.time, "thread_time_ns")
    assert observer(kernel, failures=failures)("START") == plain
    snapshot = failures.snapshot()["observer_stages"]
    assert not snapshot["thread_cpu_clock_complete"]
    assert snapshot["retention_uncertain"]


def test_maximum_fixed_snapshot_fits_declared_16384_and_has_no_history(kernel):
    failures = owner()
    observer(kernel, failures=failures)("START")
    episode = deepcopy(failures.observer_last)
    episode["failure"] = dict(family="STAGE12", code=max(d.RESOURCE_CODES, key=len),
                              errno=4095, stage="KERNEL_READ_PARSE", wall_ns=1, thread_cpu_ns=1)
    episode["snapshot_point"] = "FIRST_STAGE_FAILURE_BEFORE_CLEANUP"
    episode["observed_end_wall_ns"] = episode["observed_end_thread_cpu_ns"] = 1
    episode["returned"] = False
    failures.observer_last["failure"] = deepcopy(episode["failure"])
    failures.observer_last["returned"] = False
    failures.observer_first_failed = deepcopy(episode)
    failures.observer_first_slow = deepcopy(episode)

    def largest(value):
        if type(value) is dict:
            return {key: largest(item) for key, item in value.items()}
        return 2**64 - 1 if type(value) is int else value

    snapshot = largest(failures.snapshot()["observer_stages"])
    raw = c.canonical(snapshot)
    assert len(raw) <= 16384
    assert sum(len(row["stages"]) for row in (episode, episode, episode)) + len(snapshot["totals"]) == 36
    assert snapshot["scope"] == "SUPPLEMENTARY_COARSE_TIMING_NOT_COVERAGE_OR_CAUSE_PROOF"


def original_observer_body():
    baseline = Path(__file__).resolve().parents[1] / "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_monitor.py"
    current = ast.parse(baseline.read_text())
    # Freeze the accepted source-owned body before this delta, not a lookalike observer.
    expected = '25c011387d580859ce75a19b1c6565578a281ebcf942542208d0f1da2277f565'
    target = next(node for node in ast.walk(current) if isinstance(node, ast.ClassDef) and node.name == "LinuxObserver")
    method = next(node for node in target.body if isinstance(node, ast.FunctionDef) and node.name == "__call__")

    class Strip(ast.NodeTransformer):
        def visit_With(self, node):
            node = self.generic_visit(node)
            call = node.items[0].context_expr
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and (
                (isinstance(call.func.value, ast.Name) and call.func.value.id == "observed" and call.func.attr == "stage")
                or (isinstance(call.func.value, ast.Name) and call.func.value.id == "diagnostics" and call.func.attr == "observer_acquisition")
            ):
                return node.body
            return node

        def visit_Expr(self, node):
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and isinstance(value.func.value, ast.Name) and value.func.value.id == "lease_wait" and value.func.attr == "complete":
                return None
            return self.generic_visit(node)

    stripped = Strip().visit(method)
    observed_ast = ast.dump(stripped, include_attributes=False)
    assert hashlib.sha256(observed_ast.encode()).hexdigest() == expected
    namespace = dict(vars(m))
    module = ast.fix_missing_locations(ast.Module(body=[stripped], type_ignores=[]))
    exec(compile(module, "SOURCE_OWNED_EXACT_PREDELTA_OBSERVER_BODY", "exec"), namespace)
    return namespace["__call__"]


def test_strip_supplementary_contexts_preserves_exact_original_operation_ast():
    assert original_observer_body().__name__ == "__call__"


def test_actual_session_entrypoint_records_start_before_durable_ack_original_read(kernel):
    failures = owner()
    arguments = kernel.arguments("REPRESENTATIVE_NO_SERVICE", phase=1,
                                 native_roots=(kernel.output,))
    arguments["observer_stages"] = failures
    session = e.start_session(**arguments)
    kernel.sessions.append(session)
    assert type(session.observer) is m.LinuxObserver
    assert session.observer.observer_stages is failures
    receipt = session.require_start_acknowledged()
    assert receipt["row"]["seq"] == 1 and session.writer.acked >= 1
    original = session.original_reader(receipt["row"]["visible_identity_inventory_sha256"])
    m.validate_original_observation(original)
    assert m.old.digest(original) == receipt["row"]["visible_identity_inventory_sha256"]
    episode = failures.snapshot()["observer_stages"]["last_acquisition"]
    assert episode["kind"] == "START" and episode["phase_id"] == 1
    assert episode["observer_call_ordinal"] == 1 and episode["returned"]
    assert episode["stages"]["RETAIN_DIGEST"]["count"] == 1
    # Test abort in KernelSession teardown is not monitor FINAL or qualification.


def test_representative_command_opt_in_is_explicit_and_default_off():
    path = Path(__file__).resolve().parents[1] / "scripts/stage12_ra_g1_diagnostic.py"
    tree = ast.parse(path.read_text())
    options = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument"
               and any(isinstance(arg, ast.Constant) and arg.value == "--observer-stages" for arg in node.args)]
    assert len(options) == 1
    values = {keyword.arg: ast.literal_eval(keyword.value) for keyword in options[0].keywords
              if keyword.arg in ("action", "default")}
    assert values.get("action") == "store_true" and values.get("default", False) is False
    constructors = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name) and node.func.id == "Failures"]
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "observer_stage_enabled"
                           for target in node.targets)]
    assert len(assignments) == 1
    expression = compile(ast.Expression(assignments[0].value), str(path), "eval")
    for arguments, expected in ((SimpleNamespace(), False),
                                (SimpleNamespace(observer_stages=False), False),
                                (SimpleNamespace(observer_stages=True), True),
                                (SimpleNamespace(observer_stages=1), False),
                                (SimpleNamespace(observer_stages="True"), False)):
        assert eval(expression, {"getattr": getattr, "args": arguments}) is expected
    assert any(any(keyword.arg == "observer" and isinstance(keyword.value, ast.Name)
                   and keyword.value.id == "observer_stage_enabled"
                   for keyword in node.keywords) for node in constructors)

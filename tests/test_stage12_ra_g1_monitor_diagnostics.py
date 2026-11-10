"""Actual monitor/writer diagnostics; synthetic observations confer no authority."""

from copy import deepcopy
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import time

import pytest
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_core import H, selection, observation, original_observation
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_stage12_ra_g1_allocation_controller import world  # noqa: F401
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as capture_diagnostics

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        "synthetic_monitor_diagnostics_" + name, ROOT / "scripts" / (name + ".py")
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def controller():
    return load("stage12_ra_g1_allocation")


@pytest.fixture
def actual_failure(tmp_path, controller, monkeypatch):
    """Real daemon monitor and writer, original retention and fsync/ACK path."""
    active = []

    def run(mode):
        root = tmp_path / mode
        root.mkdir(mode=0o700)
        originals = root / "originals"
        originals.mkdir(mode=0o700)
        selected = selection("REPRESENTATIVE_NO_SERVICE")
        selected["limits"]["stages"][0].update(id=6, phase=6)
        trace = controller.StartupTrace(clock_ns=time.monotonic_ns)
        trace.enable_monitor_diagnostics()
        trace.first_start("COLLECTOR")
        writer = m.ObservationWriter(
            root / "observations.bin", maximum_rows=100,
            charge=lambda size, creates: None, check=lambda: None,
            original_root=originals, startup_trace=trace,
        )
        injected = []
        actual_fsync = m.os.fsync
        armed = [False]

        def fsync(fd):
            if armed[0] and fd == writer.fd:
                if mode == "writer_failure":
                    injected.append(("WRITER", 28, time.monotonic_ns()))
                    raise OSError(28, "PRIVATE_ADDRESS_SECRET_MUST_NOT_ECHO")
                if mode == "delayed_ack":
                    time.sleep(1.10)
            return actual_fsync(fd)

        def observe(kind):
            if kind == "PERIODIC" and mode == "acquisition_failure":
                injected.append(("MONITOR", 5, time.monotonic_ns()))
                raise OSError(5, "PRIVATE_ADDRESS_SECRET_MUST_NOT_ECHO")
            if kind == "PERIODIC" and mode == "acquisition_gap":
                time.sleep(1.10)
            row = observation(selected, enter=time.monotonic_ns(), kind=kind)
            row["visible_identity_inventory_sha256"] = writer.stage_original(
                m.export_original_observation(original_observation(row), allow_synthetic=True)
            )
            return {key: row[key] for key in (
                "readings", "counters", "native_visibility", "visible_identity_inventory_sha256"
            )}

        resource = m.ResourceMonitor(
            observer=observe, writer=writer, selected=selected,
            binding_sha256=H, phase_id=6, seed_sha256=H,
            deadline_ns=time.monotonic_ns() + 10 * 10**9,
            check=lambda: None, startup_trace=trace,
        )
        active.append((resource, writer))
        trace.bind_monitor(resource)
        resource.start()
        armed[0] = True
        monkeypatch.setattr(m.os, "fsync", fsync)
        until = time.monotonic() + 4
        while time.monotonic() < until:
            if resource.failure is not None or mode == "delayed_ack" and resource.seq >= 2:
                break
            time.sleep(0.005)
        error = None
        try:
            resource.barrier()
        except c.Stage12Error as caught:
            error = caught
        assert error is not None
        # Retain state before any cleanup action can alter thread/close flags.
        before_cleanup = deepcopy(trace.snapshot())
        return SimpleNamespace(
            resource=resource, writer=writer, trace=trace, error=error,
            before_cleanup=before_cleanup, injected=injected, selected=selected,
        )

    yield run
    for resource, writer in active:
        resource.stop_event.set()
        if resource.thread.is_alive():
            resource.thread.join(2)
        with writer.condition:
            writer.closing = True
            writer.condition.notify_all()
        writer.thread.join(2)
        assert not resource.thread.is_alive() and not writer.thread.is_alive()


@pytest.mark.parametrize("mode,errno,source", [
    ("acquisition_failure", 5, "MONITOR"), ("writer_failure", 28, "WRITER"),
])
def test_actual_primary_is_retained_before_cleanup_and_safe_stdout(
    actual_failure, controller, mode, errno, source, monkeypatch
):
    actual = actual_failure(mode)
    state = actual.before_cleanup
    fault = state["runtime_monitor"]["first_primary"]
    assert state["schema_version"] == controller.DIAGNOSTIC_VERSION
    assert fault["family"] == "OS_ERROR" and fault["errno"] == errno
    assert fault["source"] == source and fault["code"] == "UNKNOWN"
    assert state["primary_failure"]["errno"] == errno
    assert state["runtime_monitor"]["phase_id"] == 6
    assert actual.injected[0][:2] == (source, errno)
    if mode == "writer_failure":
        assert actual.writer.poisoned and actual.writer.acked == 1
        assert state["runtime_monitor"]["writer"]["first_failure"]["errno"] == errno
    else:
        assert not actual.writer.poisoned

    run = SimpleNamespace(
        startup_trace=actual.trace, poisoned=False, first_failure=None,
        counter_prefix=lambda: {"SYNTHETIC_COUNTER_PREFIX_ONLY": 0},
    )
    returned = controller.safe_failure(actual.error, run)
    assert returned["family"] == "OS_ERROR" and returned["errno"] == errno
    # Cleanup failure never replaces the initiating fault.
    actual.trace("ABORT_FAILED", error=c.Stage12Error("RA_G1_DEADLINE"), cleanup=True)
    assert actual.trace.snapshot()["primary_failure"]["errno"] == errno
    assert actual.trace.snapshot()["cleanup_failure"]["code"] == "RA_G1_DEADLINE"

    def denied_failed_writer(*args, **kwargs):
        raise AssertionError("diagnostic must never use failed monitor writer")

    monkeypatch.setattr(actual.writer, "append", denied_failed_writer)
    output = io.StringIO()
    actual.trace.emit(output)
    raw = output.getvalue()
    assert "PRIVATE_ADDRESS_SECRET" not in raw and "Traceback" not in raw
    assert len(raw.encode("ascii")) <= 8192
    assert '"schema_version":"' + controller.DIAGNOSTIC_VERSION + '"' in raw
    assert '"runtime_monitor"' in raw
    assert "BOUNDED_DIAGNOSTIC_NOT_CLOSURE" in raw


@pytest.mark.parametrize("mode", ["acquisition_gap", "delayed_ack"])
def test_genuine_acquisition_gap_and_delayed_ack_remain_gap_with_distinct_states(
    actual_failure, mode
):
    actual = actual_failure(mode)
    assert actual.error.args == ("RA_G1_MONITOR_GAP",)
    state = actual.before_cleanup["runtime_monitor"]
    assert not state["writer"]["poisoned"]
    assert state["first_primary"]["source"] == "MONITOR"
    assert state["first_primary"]["code"] == "RA_G1_MONITOR_GAP"
    if mode == "acquisition_gap":
        assert state["acquisition"]["exit_mono_ns"] - state["acquisition"]["enter_mono_ns"] > m.MAX_GAP_NS
        assert state["writer"]["acked"] == 1
    else:
        assert state["published"]["seq"] >= 2
        assert state["published"]["ack_mono_ns"] - state["published"]["exit_mono_ns"] > m.MAX_GAP_NS
        assert state["acquisition"]["exit_mono_ns"] - state["acquisition"]["enter_mono_ns"] < m.MAX_GAP_NS


def worst_snapshot(controller):
    maximum = 2**64 - 1
    code = max(m.DIAGNOSTIC_CODES, key=len)
    stage = max(controller.StartupTrace.DIAGNOSTIC_STAGES, key=len)
    fault = dict(family="STAGE12_ERROR", code=code, errno=4095, mono_ns=maximum,
                 source="MONITOR", stage=stage)
    return dict(
        phase_id=maximum, monitor_failure=code, first_primary=fault,
        acquisition=dict(kind="PERIODIC", stage=stage, enter_mono_ns=maximum, exit_mono_ns=maximum),
        published=dict(seq=maximum, enter_mono_ns=maximum, exit_mono_ns=maximum, ack_mono_ns=maximum),
        writer=dict(rows=maximum, acked=maximum, ack_ns=maximum, poisoned=False,
                    closing=False, released=False, thread_alive=False, current_seq=maximum,
                    stage=stage, first_failure={**fault, "source": "WRITER"}),
    )


def test_full48_entry_and_uint64_diagnostic_remains_within_original8192(controller):
    maximum = 2**64 - 1
    trace = controller.StartupTrace(maximum, clock_ns=lambda: maximum)
    trace.enable_monitor_diagnostics()
    for _ in range(47):
        trace(max(trace.EVENTS, key=len), maximum)
    trace.monitor_failure(worst_snapshot(controller))
    trace("ABORT_FAILED", error=c.Stage12Error(max(controller.SAFE_CODES, key=len)), cleanup=True)
    trace.cleanup["at_mono_ns"] = maximum
    trace.dropped = trace.unknown = trace.instrumentation_faults = maximum
    trace.controller_command = "phase_runner"
    raw = trace.encoded_snapshot()
    assert len(trace.snapshot()["entries"]) == 48
    assert trace.MAX_BYTES == 8192 and len(raw) <= 8192
    assert trace.snapshot()["runtime_logical_scalar_bytes"] == 248
    assert 248 + 10 * 8 <= trace.snapshot()["failure_state_allowance_bytes"]


@pytest.mark.parametrize("tamper", ["unsafe_stage", "unsafe_code", "unknown_field", "oversized_integer"])
def test_invalid_diagnostic_scalar_is_never_retained_or_echoed(controller, tamper):
    trace = controller.StartupTrace()
    trace.enable_monitor_diagnostics()
    state = worst_snapshot(controller)
    if tamper == "unsafe_stage":
        state["acquisition"]["stage"] = "PRIVATE_ADDRESS_SECRET_MUST_NOT_ECHO"
    elif tamper == "unsafe_code":
        state["first_primary"]["code"] = "PRIVATE_ADDRESS_SECRET_MUST_NOT_ECHO"
    elif tamper == "unknown_field":
        state["unsafe_path"] = "PRIVATE_ADDRESS_SECRET_MUST_NOT_ECHO"
    else:
        state["writer"]["acked"] = 2**64
    trace.monitor_failure(state)
    assert trace.snapshot()["runtime_monitor"] is None
    assert trace.snapshot()["instrumentation_faults"] == 1
    assert b"PRIVATE_ADDRESS_SECRET" not in trace.encoded_snapshot()


def test_old_trace_v1_retains_original_shape_and_does_not_opt_in(controller):
    trace = controller.StartupTrace(10, clock_ns=lambda: 10)
    before = deepcopy(trace.snapshot())
    trace.monitor_failure(worst_snapshot(controller))
    assert trace.snapshot() == before
    assert before["schema_version"] == "stage12_ra_g1_startup_trace_v1"
    assert before["first_start_only"] is True and "runtime_monitor" not in before
    assert trace.MAX_ENTRIES == 48
    assert trace.encoded_snapshot().endswith(b"\n")


# Request the imported fixture by its registered pytest name.
def test_new_outer_requires_new_compiler_and_all_three_bootstrap_proofs(world):  # noqa: F811
    controller = world.m
    old = deepcopy(world.s)
    _, adoption, _ = bootstrap_inputs()
    selected = deepcopy(old)
    selected.update(
        version=controller.SHARED_LEASE_VERSION,
        bootstrap_prefix_adoption=adoption,
        bootstrap_prefix_adoption_sha256=controller.digest(adoption),
    )
    inv, totals = accounting.compile_inventory(
        selected["source_files"], selected["accounting_inventory"]["backends"],
        selected["scope"], bootstrap_successor=True, shared_lease_successor=True,
    )
    selected.update(accounting_inventory=inv, accounting=totals)
    assert controller.validate_selection(selected) == selected
    assert controller.validate_selection(old) == old
    changed = deepcopy(selected)
    changed["accounting_inventory"]["bootstrap_proof_record_count"] = 2
    with pytest.raises((RuntimeError, c.Stage12Error)):
        controller.validate_selection(changed)
    changed = deepcopy(selected)
    changed["accounting_inventory"], changed["accounting"] = accounting.compile_inventory(
        selected["source_files"], selected["accounting_inventory"]["backends"],
        selected["scope"], bootstrap_successor=True,
    )
    with pytest.raises(RuntimeError):
        controller.validate_selection(changed)


def test_phase_runner_stdout_bridge_runs_on_real_failure_snapshot(
    actual_failure, monkeypatch, capsys
):
    actual = actual_failure("writer_failure")
    runner = load("stage12_ra_g1_diagnostic")
    runner.ACTIVE_DIAGNOSTIC_TRACE = actual.trace
    runner.ACTIVE_DIAGNOSTIC_CHECK = lambda: None

    def fail_main():
        raise actual.error

    monkeypatch.setattr(runner, "main", fail_main)
    assert runner.cli_entry() == 1
    output = capsys.readouterr().out
    assert actual.writer.poisoned
    assert '"runtime_monitor"' in output and '"errno":28' in output
    assert "PRIVATE_ADDRESS_SECRET" not in output


def test_phase_runner_stdout_is_charged_once_and_cannot_create_late_success(
    controller, monkeypatch, capsys
):
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import ApplicationControls

    trace = controller.StartupTrace()
    trace.enable_monitor_diagnostics()
    trace.set_controller_command("phase_runner")
    controls = ApplicationControls(selection("REPRESENTATIVE_NO_SERVICE"), check=lambda: None)
    before = controls.snapshot()
    trace.reserve_phase_stdout(controls)
    assert controls.snapshot()["bytes"] == before["bytes"] + 8192
    assert controls.snapshot()["creations"] == before["creations"]
    runner = load("stage12_ra_g1_diagnostic")
    runner.ACTIVE_DIAGNOSTIC_TRACE = trace

    def expired():
        raise RuntimeError("RA_G1_DEADLINE")

    runner.ACTIVE_DIAGNOSTIC_CHECK = expired
    monkeypatch.setattr(runner, "main", lambda: 0)
    assert runner.cli_entry() == 1
    output = capsys.readouterr().out
    assert '"runtime_monitor"' in output


def test_shared_input_is_distinct_without_changing_old_descriptor_bytes(controller):
    runner = load("stage12_ra_g1_diagnostic")
    assert runner.SHARED_LEASE_VERSION == "stage12_ra_g1_shared_lease_representative_input_v1"
    assert controller.SHARED_LEASE_VERSION == "stage12_ra_g1_shared_lease_allocation_selection_v1"
    for version in (runner.VERSION, runner.BOOTSTRAP_VERSION):
        descriptor = runner.descriptor(version)
        assert "runtime_diagnostic_version" not in descriptor
    assert runner.descriptor(runner.SHARED_LEASE_VERSION)["diagnostic_stdout_bytes"] == 8192
    selected = dict(scope=runner.SCOPE, schema_version=runner.BOOTSTRAP_SELECTION)
    runner.validate_resource_family(runner.SHARED_LEASE_VERSION, selected)


@pytest.mark.parametrize("code", ["WF_AP2_SCRATCH_LIMIT", "WF_AP2_SCRATCH_REENTRANT"])
def test_exact_typed_core_scratch_code_is_retained_without_widening_outer_v1(controller, code):
    trace = controller.StartupTrace()
    trace.enable_monitor_diagnostics()
    state = worst_snapshot(controller)
    state["first_primary"]["code"] = code
    state["writer"]["first_failure"]["code"] = code
    trace.monitor_failure(state)
    actual = trace.snapshot()
    assert actual["instrumentation_faults"] == 0
    assert actual["runtime_monitor"]["first_primary"]["code"] == code
    assert actual["primary_failure"]["code"] == code
    assert trace.monitor_primary()["code"] == "UNKNOWN"
    assert code.encode("ascii") in trace.encoded_snapshot()


@pytest.mark.parametrize("code", m.DIAGNOSTIC_CODES)
def test_every_exact_core_code_survives_closed_v2_bridge_and_encoding(controller, code):
    assert controller.StartupTrace.DIAGNOSTIC_CODES == frozenset(m.DIAGNOSTIC_CODES)
    trace = controller.StartupTrace()
    trace.enable_monitor_diagnostics()
    state = worst_snapshot(controller)
    state["monitor_failure"] = code
    state["first_primary"]["code"] = code
    state["writer"]["first_failure"]["code"] = code
    trace.monitor_failure(state)
    actual = trace.snapshot()
    assert actual["instrumentation_faults"] == 0
    assert actual["runtime_monitor"]["monitor_failure"] == code
    assert actual["runtime_monitor"]["first_primary"]["code"] == code
    assert actual["runtime_monitor"]["writer"]["first_failure"]["code"] == code
    assert code.encode("ascii") in trace.encoded_snapshot()
    if code not in controller.SAFE_CODES:
        assert trace.monitor_primary()["code"] == "UNKNOWN"


@pytest.mark.parametrize("family", ["BOOTSTRAP_VERSION", "SHARED_LEASE_VERSION"])
# Request the imported fixture by its registered pytest name.
def test_exact_bootstrap_adoption_reader_under_actual_installed_callback(world, monkeypatch, family):  # noqa: F811
    """Native install is synthetic; the policy closure and Run.original are real."""
    import os
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport

    m = world.m
    _, adoption, _ = bootstrap_inputs()
    adoption_sha = m.digest(adoption)
    selected = deepcopy(world.s)
    selected.update(
        version=getattr(m, family), bootstrap_prefix_adoption=adoption,
        bootstrap_prefix_adoption_sha256=adoption_sha,
    )
    inventory, totals = accounting.compile_inventory(
        selected["source_files"], selected["accounting_inventory"]["backends"], selected["scope"],
        bootstrap_successor=True, shared_lease_successor=family == "SHARED_LEASE_VERSION",
    )
    selected.update(accounting_inventory=inventory, accounting=totals)
    assert m.validate_selection(selected) == selected
    assert adoption_sha not in selected["records"].values()
    world.s.clear()
    world.s.update(selected)
    adoption_path = world.records / (adoption_sha + ".record")
    original_raw = m.canonical(adoption)
    adoption_path.write_bytes(original_raw)
    adoption_path.chmod(0o600)
    wrong_sha = "f" * 64
    assert wrong_sha != adoption_sha and wrong_sha not in selected["records"].values()
    wrong_path = world.records / (wrong_sha + ".record")
    wrong_path.write_bytes(original_raw)
    wrong_path.chmod(0o600)
    foreign_path = world.source / (adoption_sha + ".record")
    foreign_path.write_bytes(original_raw)
    foreign_path.chmod(0o600)
    membership = world.records / "synthetic-cgroup-for-adoption-policy"
    membership.write_bytes(b"0::/SYNTHETIC\n")
    membership.chmod(0o600)
    actual_open = os.open

    def substitute_membership(path, flags, *args, **kwargs):
        if str(path) == f"/proc/{os.getpid()}/cgroup":
            return actual_open(membership, flags, *args, **kwargs)
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(m.os, "open", substitute_membership)
    guard = SimpleNamespace()

    def denied(*args, **kwargs):
        raise PermissionError("SYNTHETIC_INSTALLED_POLICY_DENIED")

    def simulated_native_install(*args):
        assert callable(guard.open_allowed)
        return (
            SimpleNamespace(origin="SYNTHETIC_ONLY_NO_NATIVE_OR_SECCOMP_QUALIFICATION"),
            "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT",
            [0], [None], lambda count: None, denied,
        )

    guard.install_denials = simulated_native_install
    monkeypatch.setattr(m, "module", lambda *args: guard)
    for name in ("runtime", "private_file"):
        monkeypatch.setattr(s12_transport.Secret, name, s12_transport.Secret.__dict__[name])
    with world.run("collect") as run:
        m.install_denials(world.s, check=run.check, read_charge=run.read_charge)

        def allowed(path, write=False):
            return guard.open_allowed(
                path, write=write, source=world.source, output=world.root,
                input_path=world.root / "input.record", evidence=world.records,
                self_proc=None,
            )

        touched = []

        def guarded_open(path, flags, *args, **kwargs):
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            touched.append((str(path), write))
            if not allowed(path, write):
                raise PermissionError("SYNTHETIC_INSTALLED_POLICY_DENIED")
            return actual_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(m.os, "open", guarded_open)
        before = run.counter_prefix()
        assert run.original(adoption_path, limit=8192) == original_raw
        assert run.read_bytes == before["source_read_bytes"] + len(original_raw)
        assert run.read_calls > before["source_read_calls"]

        # This is the actual production start_admin adoption-reader expression.
        def adoption_reader(identity):
            return run.original(world.records / (identity + ".record"), limit=8192)

        returned = m.parse(adoption_reader(adoption_sha))
        assert returned == adoption
        assurance.validate_bootstrap_adoption(
            returned, {"bootstrap_prefix_adoption_sha256": adoption_sha}
        )
        assert (str(adoption_path), False) in touched
        for path in (wrong_path, foreign_path):
            with pytest.raises(PermissionError, match="SYNTHETIC_INSTALLED_POLICY_DENIED"):
                run.original(path, limit=8192)
        with pytest.raises(PermissionError, match="SYNTHETIC_INSTALLED_POLICY_DENIED"):
            adoption_reader(wrong_sha)
        with pytest.raises(PermissionError, match="SYNTHETIC_INSTALLED_POLICY_DENIED"):
            m.os.open(adoption_path, os.O_WRONLY | os.O_TRUNC)
        assert not allowed(adoption_path, True)
        assert not allowed("/proc/999999/status")
        assert not allowed("/sys/fs/cgroup/FOREIGN/memory.max")
        assert not allowed("/sys/fs/cgroup/SYNTHETIC/memory.max", True)

        # A simulated external writer can alter a declared original; a fresh
        # reader plus the real adoption validator must reject the hash mismatch.
        changed = deepcopy(adoption)
        key = next(key for key, value in changed.items() if type(value) is str and len(value) == 64)
        changed[key] = "0" * 64 if changed[key] != "0" * 64 else "1" * 64
        fd = actual_open(adoption_path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
        try:
            raw = m.canonical(changed)
            assert os.write(fd, raw) == len(raw)
            os.fsync(fd)
        finally:
            os.close(fd)
        fresh = m.parse(adoption_reader(adoption_sha))
        with pytest.raises(c.Stage12Error):
            assurance.validate_bootstrap_adoption(
                fresh, {"bootstrap_prefix_adoption_sha256": adoption_sha}
            )


@pytest.mark.parametrize("output_case", ["success", "phase_late", "global_late", "window_end"])
def test_real_completed_session_actual_execute_tail_postemit_limits(
    tmp_path, controller, output_case
):
    """Execute the source's real completion tail; no full workload or authority."""
    import ast
    from copy import deepcopy as clone
    from test_s12_ra_g1_core import Authority, binding
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as ap
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage

    runner = load("stage12_ra_g1_diagnostic")
    tree = ast.parse(Path(runner.__file__).read_text())
    source_execute = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute")
    source_check = next(node for node in source_execute.body if isinstance(node, ast.FunctionDef) and node.name == "check")
    completion = next(
        node for node in ast.walk(source_execute)
        if isinstance(node, ast.If)
        and any(
            isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute)
            and isinstance(item.func.value, ast.Name) and item.func.value.id == "final_resource"
            and item.func.attr == "freeze_and_open" for item in ast.walk(node)
        )
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name) and node.test.left.id == "final_resource"
    )
    precharge_index = next(
        index for index, node in enumerate(source_execute.body)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "claim"
    )
    # Exact source statements include freeze/open, record publication, deadline
    # capture, resource clear, summary write, callback construction and return.
    arguments = ast.arguments(posonlyargs=[], args=[ast.arg(arg="final_resource")],
        vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None, defaults=[])
    tail = ast.FunctionDef(
        name="actual_completed_tail", args=arguments,
        body=[ast.Global(names=["ACTIVE_DIAGNOSTIC_CHECK"]), clone(source_check),
              *clone(completion.body), *clone(source_execute.body[precharge_index:])],
        decorator_list=[], returns=None, type_comment=None,
    )

    class Clock:
        def __init__(self):
            self.value = 10**9
            self.utc_value = None
            self.step = 1000

        def now_ns(self):
            self.value += self.step
            return self.value

        def utc(self):
            return self.utc_value

    clock = Clock()
    started_ns = clock.now_ns()
    selected, _adoption, adoption_reader = bootstrap_inputs()
    selected["limits"].update(processing_ms=8160000, scheduler_s=8400)
    final_stage = deepcopy(selected["limits"]["stages"][0])
    final_stage.update(id=5, phase=5, deadline_ms=120000, attempts=0, events=0)
    prior_stages = []
    for phase_id in range(1, 5):
        row = dict.fromkeys(final_stage, 1)
        row.update(id=phase_id, phase=phase_id, deadline_ms=2, reserve_ms=1, attempts=0, events=0)
        prior_stages.append(row)
    final_stage["logical_write_bytes"] -= len(prior_stages)
    selected["limits"]["stages"] = prior_stages + [final_stage]
    bound = binding(selected)
    clock.utc_value = bound["valid_from"]
    output = tmp_path / "SYNTHETIC_COMPLETION_TAIL_ONLY"
    storage.reserve(output)
    marker = output / "synthetic_opener_original.json"
    storage.write(marker, runner.canonical({"scope": "SYNTHETIC_COMPLETION_TAIL_ONLY"}))
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import ApplicationControls

    controls = ApplicationControls(selected, check=lambda: None)
    trace = controller.StartupTrace(started_ns, clock_ns=clock.now_ns)
    trace.enable_monitor_diagnostics()
    trace.set_controller_command("phase_runner")
    trace.reserve_phase_stdout(controls)
    reads = []

    def factory(retain):
        def observe(kind):
            row = observation(selected, enter=clock.now_ns(), kind=kind)
            row["visible_identity_inventory_sha256"] = retain(original_observation(row))
            return {key: row[key] for key in (
                "readings", "counters", "native_visibility", "visible_identity_inventory_sha256"
            )}
        return observe

    phase_start = clock.now_ns()
    phase_deadline = phase_start + 120 * 10**9
    global_deadline = started_ns + 7200 * 10**9
    value = execution.PhaseSession(
        authority=Authority(selected), binding=bound, selection=selected,
        resource_evidence_root=output / "whole_task_resources", pids=(123,),
        counter_provider=lambda: dict.fromkeys(m.COUNTERS, 0),
        charge=controls.monitor_charge, check=lambda: None,
        deadline_ns=phase_deadline, phase_id=5,
        admitted_process_provider=lambda: (123,),
        read_charge=lambda calls, size: reads.append((calls, size)),
        observer_factory=factory, clock_ns=clock.now_ns, scope_start_ns=phase_start,
        startup_trace=trace, bootstrap_adoption_reader=adoption_reader,
    )
    trace.bind_monitor(value.monitor)
    value.start()
    opened = []

    def actual_opener():
        opened.append(storage.metadata(storage.read(marker)))
        return opened[-1]

    namespace = dict(runner.__dict__)
    namespace.update(
        clock=clock, deadline=global_deadline,
        limits={"rss_bytes": 768 * 2**20, "summary_reserve_bytes": 2**20},
        budget=SimpleNamespace(snapshot=lambda: {"exceeded": False, "scope": "SYNTHETIC_TAIL_ONLY"}),
        original=SimpleNamespace(allocation_controls=controls, counters=lambda: {"SYNTHETIC_TAIL_ONLY": 0}),
        resource_sessions=[], phases=[{"scope": "SYNTHETIC_PRIOR_PHASE_ONLY", "id": i} for i in range(4)],
        summary={"scope": "SYNTHETIC_COMPLETION_TAIL_ONLY"}, ap=ap, selected=selected, bound=bound,
        final_start_ns=phase_start, actual_whole_open=actual_opener,
        data={"version": runner.SHARED_LEASE_VERSION},
        args=SimpleNamespace(source_sha=bound["source_git_sha"], input_sha256=H),
        failure=None, first_failure=None, cleanup_failure=None, cleanup_failure_count=0,
        capture_failures=capture_diagnostics.Failures(clock),
        runtime_trace=trace,
        boundaries=[], attempts=106, resource_observation={"scope": "SYNTHETIC_TAIL_ONLY"},
        network_guard="SYNTHETIC_NO_NATIVE_QUALIFICATION", creations=[0],
        started_ns=started_ns, cpu_started_ns=time.process_time_ns(), storage=storage, output=output,
    )
    try:
        module = ast.fix_missing_locations(ast.Module(body=[tail], type_ignores=[]))
        exec(compile(module, runner.__file__, "exec"), namespace)
        assert namespace["actual_completed_tail"](value) == 0
        assert value.completed and value.writer.released
        assert opened == [{"scope": "SYNTHETIC_COMPLETION_TAIL_ONLY"}]
        assert reads and storage.metadata(storage.read(output / "summary.json"))["complete"] is True
        postcheck = namespace["ACTIVE_DIAGNOSTIC_CHECK"]
        assert postcheck.__defaults__ == (phase_deadline, bound["valid_from"], bound["valid_until"])
        assert "final_resource" not in postcheck.__code__.co_freevars

        class Output(io.StringIO):
            def write(self, raw):
                result = super().write(raw)
                if output_case == "phase_late":
                    clock.value = phase_deadline
                    clock.step = 0
                elif output_case == "global_late":
                    clock.value = global_deadline
                    clock.step = 0
                elif output_case == "window_end":
                    clock.utc_value = bound["valid_until"]
                return result

        emitted = Output()
        trace.emit(emitted)
        assert '"runtime_monitor"' in emitted.getvalue()
        if output_case == "success":
            postcheck()
        else:
            expected = {
                "phase_late": "RA_G1_DIAGNOSTIC_PHASE_DEADLINE",
                "global_late": "RA_G1_DIAGNOSTIC_DEADLINE",
                "window_end": "RA_G1_EXPIRED",
            }[output_case]
            with pytest.raises(RuntimeError, match=expected):
                postcheck()
    finally:
        value.monitor.stop_event.set()
        if value.monitor.thread.is_alive():
            value.monitor.thread.join(1)
        with value.writer.condition:
            value.writer.closing = True
            value.writer.condition.notify_all()
        value.writer.thread.join(1)
        assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()

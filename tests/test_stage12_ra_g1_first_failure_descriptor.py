"""Bounded first-failure diagnostics: synthetic pins, no execution authority."""

from contextlib import redirect_stdout
from copy import deepcopy
import gc
import io
import json
from types import SimpleNamespace
import weakref

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from test_s12_ra_g1_accounting import inputs
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_ra_g1_allocation_controller import (
    collect_and_release,
    orchestration,  # noqa: F401
    world,  # noqa: F401
)


@pytest.fixture
def context(world):  # noqa: F811
    m = world.m
    selected = deepcopy(world.s)
    selected["source_files"] = [
        dict(path=relative, bytes=100000, sha256="1" * 64)
        for relative, _ in sorted(m._FIRST_FAILURE_MODULES)
    ]
    _, backends = inputs()
    selected["accounting_inventory"], selected["accounting"] = accounting.compile_inventory(
        selected["source_files"], backends, m.SCOPE)
    m.validate_selection(selected)
    trace = m.StartupTrace()
    trace.first_descriptor.configure(selected)
    trace.first_descriptor.set_operation("BUILD_INPUT")
    return SimpleNamespace(m=m, selected=selected, trace=trace,
                           state=trace.first_descriptor, root=world.source)


def raise_four(context, payload="UNSAFE_QUERY_SECRET"):
    root = str(context.root)
    builder = {"payload": payload}
    exec(compile(
        "def build(): return build_campaigns()\n"
        "def build_campaigns(): return {}[payload]\n",
        root + "/scripts/stage12_prepare_ra_g1.py", "exec"), builder)
    caller = {"builder": builder["build"]}
    exec(compile("def main(): return bind()\ndef bind(): return builder()\n",
                 root + "/scripts/stage12_ra_g1_allocation.py", "exec"), caller)
    caller["main"]()


def fake_run(trace):
    maximum = 2**64 - 1
    prefix = dict(
        source_read_calls=maximum, source_read_bytes=maximum, checks=maximum,
        monitor_usage=dict(bytes=maximum, creations=maximum, rows=maximum, directories=maximum),
        metadata={stage: dict(write_bytes=maximum, creations=maximum, file_attempts=maximum)
                  for stage in ("ready", "collect", "bind", "verify")})
    return SimpleNamespace(startup_trace=trace, first_failure=None, poisoned=False,
                           counter_prefix=lambda: deepcopy(prefix))


def test_exact_keyerror_four_pinned_frames_without_secret_text(context):
    m, state = context.m, context.state
    try:
        raise_four(context)
    except KeyError as error:
        value = m.described_failure(error, fake_run(context.trace))
    descriptor = value["first_failure_descriptor"]
    assert value["schema_version"] == m.FAILURE_ENVELOPE_VERSION
    assert descriptor["exception_kind"] == "KEY_ERROR"
    assert descriptor["guard_code"] == "UNKNOWN"
    assert descriptor["binder_operation"] == "BUILD_INPUT"
    assert [row["module_id"] for row in descriptor["frames"]] == [
        "ALLOCATION_CONTROLLER", "ALLOCATION_CONTROLLER",
        "REPRESENTATIVE_PREPARER", "REPRESENTATIVE_PREPARER"]
    assert all(type(row["line"]) is int and 1 <= row["line"] <= 100001
               for row in descriptor["frames"])
    assert len(m.canonical(descriptor)) <= 1024
    raw = m.canonical(value)
    assert b"UNSAFE_QUERY_SECRET" not in raw and str(context.root).encode() not in raw
    assert state.snapshot() == descriptor


def test_traceback_walk_and_frame_limits_are_explicit(context):
    namespace = {}
    exec(compile(
        "def recurse(n):\n"
        "    if n: return recurse(n-1)\n"
        "    raise KeyError('UNSAFE_QUERY_SECRET')\n",
        str(context.root) + "/scripts/stage12_prepare_ra_g1.py", "exec"), namespace)
    try:
        namespace["recurse"](80)
    except KeyError as error:
        context.state.capture(error)
    value = context.state.snapshot()
    assert value["traceback_walked"] == 32
    assert value["traceback_truncated"] is True and value["frames_truncated"] is True
    assert len(value["frames"]) == 4
    assert all(row["module_id"] == "REPRESENTATIVE_PREPARER" for row in value["frames"])


def test_unsupported_and_secret_argument_getters_are_not_invoked(context):
    calls = []

    class SecretError(RuntimeError):
        def __getattribute__(self, name):
            if name in ("args", "__traceback__"):
                calls.append(name)
                raise AssertionError("UNSAFE_QUERY_SECRET")
            return super().__getattribute__(name)

    class SecretArgument:
        def __str__(self):
            raise AssertionError("UNSAFE_QUERY_SECRET")

    value = context.m.described_failure(SecretError(SecretArgument()), fake_run(context.trace))
    assert calls == []
    assert value["first_failure_descriptor"]["exception_kind"] == "UNKNOWN"
    assert value["first_failure_descriptor"]["guard_code"] == "UNKNOWN"
    assert "UNSAFE_QUERY_SECRET" not in json.dumps(value)


def test_exact_reviewed_guard_only_and_snapshot_is_independent(context):
    state, m = context.state, context.m
    state.capture(RuntimeError("RA_G1_CANONICAL_REQUIRED"))
    first = state.snapshot()
    assert first["exception_kind"] == "RUNTIME_ERROR"
    assert first["guard_code"] == "RA_G1_CANONICAL_REQUIRED"
    first["guard_code"] = "UNSAFE_QUERY_SECRET"
    assert state.snapshot()["guard_code"] == "RA_G1_CANONICAL_REQUIRED"
    assert m.safe_failure(RuntimeError("RA_G1_PATH"))["schema_version"] == "stage12_ra_g1_allocation_failure_v1"


def test_descriptor_does_not_retain_error_traceback_or_locals(context):
    class Payload:
        pass

    def produce():
        payload = Payload()
        reference = weakref.ref(payload)
        try:
            raise ValueError(payload)
        except ValueError as error:
            context.state.capture(error)
        return reference

    reference = produce()
    gc.collect()
    assert reference() is None
    value = context.state.snapshot()
    assert value["exception_kind"] == "VALUE_ERROR" and value["guard_code"] == "UNKNOWN"


def test_saturation_and_cleanup_cannot_replace_first_descriptor(context):
    trace, m = context.trace, context.m
    for _ in range(trace.MAX_ENTRIES + 30):
        trace("MAIN_ENTER")
    run = fake_run(trace)
    first = m.described_failure(KeyError("UNSAFE_QUERY_SECRET"), run)
    trace("START_FAILED", error=KeyError("UNSAFE_SECONDARY"))
    context.state.set_operation("COMPLETE")
    trace("ABORT_FAILED", error=RuntimeError("RA_G1_WRITE_UNCERTAIN"), cleanup=True)
    run.poisoned = True
    later = m.described_failure(RuntimeError("RA_G1_WRITE_UNCERTAIN"), run)
    assert later["first_failure_descriptor"] == first["first_failure_descriptor"]
    assert later["first_failure_descriptor"]["exception_kind"] == "KEY_ERROR"
    assert later["first_failure_descriptor"]["binder_operation"] == "BUILD_INPUT"
    assert later["writer"] == "POISONED" and trace.snapshot()["truncated"] is True


def test_shared_output_budget_trims_events_with_exact_dropped_count(context):
    m, trace = context.m, context.trace
    trace.enable_monitor_diagnostics()
    for _ in range(48):
        trace("FIRST_ACQUIRE_ENTER")
    trace("START_FAILED", error=RuntimeError("RA_G1_PATH"))
    before = trace.snapshot()
    trace.failure_output_bytes = 4096  # Source maximum-envelope budget stress.
    raw = trace.encoded_snapshot()
    value = json.loads(raw)
    assert len(raw) <= 4096 and value["truncated"] is True
    assert value["dropped_entries"] == before["dropped_entries"] + len(before["entries"]) - len(value["entries"])
    assert value["primary_failure"] == before["primary_failure"]
    assert value["schema_version"] == m.DIAGNOSTIC_VERSION
    assert "first_failure_descriptor" not in value


def test_actual_failure_then_trace_fit_original8192_and_duplicate_is_not_printed(context):
    m, trace = context.m, context.trace
    trace.enable_monitor_diagnostics()
    for _ in range(80):
        trace("FIRST_ACQUIRE_ENTER")
    run = fake_run(trace)
    first = m.described_failure(RuntimeError("RA_G1_PATH"), run)
    output = io.StringIO()
    with redirect_stdout(output):
        m.print_failure(first, run)
        m.print_failure(first, run)
    failure_raw = output.getvalue().encode()
    trace_raw = trace.encoded_snapshot()
    assert len(failure_raw.splitlines()) == 1
    assert len(failure_raw) + len(trace_raw) <= 8192
    assert len(m.canonical(first["first_failure_descriptor"])) <= 1024
    assert trace.failure_output_bytes == len(failure_raw)


def test_monitor_primary_and_unknown_basis_precede_later_controller_error(context):
    trace, m = context.trace, context.m
    trace.enable_monitor_diagnostics()
    fault = dict(family="OS_ERROR", code="UNKNOWN", errno=5,
                 mono_ns=1, source="WRITER", stage="CODEC_FSYNC")
    snapshot = dict(
        phase_id=7, monitor_failure="RA_G1_WRITE_UNCERTAIN", first_primary=fault,
        acquisition=dict(kind="PERIODIC", stage="WAIT_ACK", enter_mono_ns=1, exit_mono_ns=2),
        published=dict(seq=1, enter_mono_ns=1, exit_mono_ns=1, ack_mono_ns=1),
        writer=dict(rows=2, acked=1, ack_ns=1, poisoned=True, closing=True,
                    released=False, thread_alive=False, current_seq=2,
                    stage="CLOSED", first_failure=fault))
    trace.monitor_failure(snapshot)
    run = fake_run(trace)
    run.poisoned = True
    value = m.described_failure(RuntimeError("RA_G1_WRITE_UNCERTAIN"), run)
    assert value["family"] == "OS_ERROR" and value["errno"] == 5
    assert value["writer"] == "POISONED"
    assert value["first_failure_descriptor"]["exception_kind"] == "UNKNOWN"
    assert value["first_failure_descriptor"]["capture_status"] == "MONITOR_PRIMARY_NO_TRACEBACK"


def test_actual_bind_marks_build_input_before_raising_builder(orchestration, monkeypatch):  # noqa: F811
    environment = orchestration
    collect_and_release(environment)
    builder = environment.m.module(environment.s["paths"]["source"], "stage12_prepare_ra_g1")
    observed = []

    def fail(*args, **kwargs):
        observed.append(environment.m.PROCESS_TRACE.first_descriptor.operation)
        raise KeyError("UNSAFE_QUERY_SECRET")

    monkeypatch.setattr(builder, "build", fail)
    with environment.run("bind") as run:
        with pytest.raises(KeyError) as caught:
            environment.m.bind(run)
        value = environment.m.described_failure(caught.value, run)
        assert value["first_failure_descriptor"]["binder_operation"] == "BUILD_INPUT"
        assert value["first_failure_descriptor"]["exception_kind"] == "KEY_ERROR"
    assert observed == ["BUILD_INPUT"]


def test_trace_and_envelope_never_invoke_unsupported_oserror_getters(context):
    calls = []

    class Unsupported(OSError):
        def __getattribute__(self, name):
            if name in ("args", "errno", "__traceback__"):
                calls.append(name)
                raise AssertionError("UNSAFE_QUERY_SECRET")
            return super().__getattribute__(name)

        def __str__(self):
            raise AssertionError("UNSAFE_QUERY_SECRET")

    error = Unsupported()
    run = fake_run(context.trace)
    value = context.m.described_failure(error, run)
    context.trace("START_FAILED", error=error)
    assert calls == []
    assert value["first_failure_descriptor"]["exception_kind"] == "UNKNOWN"
    assert context.trace.snapshot()["primary_failure"]["code"] == "UNKNOWN"
    assert "UNSAFE_QUERY_SECRET" not in json.dumps(value)


def test_maximum_descriptor_and_packet_sizes_fit_shared_reservation(context):
    m, state = context.m, context.state
    state.capture(KeyError("UNSAFE_QUERY_SECRET"))
    with state.lock:
        state._value.update(
            exception_kind="NOT_A_DIRECTORY_ERROR",
            guard_code=max(m.SAFE_CODES, key=len),
            binder_operation=max(m.BINDER_OPERATIONS, key=len),
            source_inventory_sha256="f" * 64,
            frames=[dict(module_id="REPRESENTATIVE_PREPARER", line=4 * 2**20 + 1)
                    for _ in range(4)],
            traceback_walked=32, unmapped_frames=32,
            traceback_truncated=True, frames_truncated=True,
            capture_status="MONITOR_PRIMARY_NO_TRACEBACK")
    descriptor = state.snapshot()
    assert len(m.canonical(descriptor)) <= 1024
    run = fake_run(context.trace)
    value = m.described_failure(RuntimeError("RA_G1_PATH"), run)
    assert len(m.canonical(value)) <= 4096
    output = io.StringIO()
    with redirect_stdout(output):
        m.print_failure(value, run)
    assert len(output.getvalue().encode()) + len(context.trace.encoded_snapshot()) <= 8192


def test_late_first_failure_retains_headroom_after_actual_trace_emit(context):
    m, trace = context.m, context.trace
    trace.enable_monitor_diagnostics()
    trace.first_descriptor.active = True
    for _ in range(80):
        trace("FIRST_ACQUIRE_ENTER")
    output = io.StringIO()
    trace.emit(output)
    trace_bytes = len(output.getvalue().encode())
    assert trace_bytes <= 4096
    run = fake_run(trace)
    value = m.described_failure(RuntimeError("RA_G1_DEADLINE"), run)
    with redirect_stdout(output):
        m.print_failure(value, run)
    assert len(output.getvalue().encode()) <= 8192
    assert len(output.getvalue().splitlines()) == 2
    assert trace.trace_output_bytes == trace_bytes


def test_cli_unsupported_secret_exception_is_safe_end_to_end(context, monkeypatch):
    m, trace = context.m, context.trace
    calls = []

    class Unsupported(OSError):
        def __getattribute__(self, name):
            if name in ("args", "errno", "__traceback__"):
                calls.append(name)
                raise AssertionError("UNSAFE_QUERY_SECRET")
            return super().__getattribute__(name)

        def __str__(self):
            raise AssertionError("UNSAFE_QUERY_SECRET")

    def failing_main():
        raise Unsupported()

    monkeypatch.setattr(m, "PROCESS_TRACE", trace)
    monkeypatch.setattr(m, "main", failing_main)
    output = io.StringIO()
    with redirect_stdout(output):
        assert m.cli_entry() == 1
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert records[0]["schema_version"] == m.FAILURE_ENVELOPE_VERSION
    assert records[0]["first_failure_descriptor"]["exception_kind"] == "UNKNOWN"
    assert calls == [] and "UNSAFE_QUERY_SECRET" not in output.getvalue()
    assert len(output.getvalue().encode()) <= 8192


def test_builtin_storage_bypasses_real_subclass_properties_full_cli(context, monkeypatch):
    m, trace = context.m, context.trace
    calls = []

    class PropertyError(OSError):
        @property
        def args(self):
            calls.append("args")
            raise AssertionError("UNSAFE_QUERY_SECRET")

        @property
        def errno(self):
            calls.append("errno")
            raise AssertionError("UNSAFE_QUERY_SECRET")

        @property
        def __traceback__(self):
            calls.append("traceback")
            raise AssertionError("UNSAFE_QUERY_SECRET")

        def __str__(self):
            calls.append("str")
            raise AssertionError("UNSAFE_QUERY_SECRET")

    original = PropertyError()
    namespace = {"original": original}
    exec(compile(
        "def main(): raise original\n",
        str(context.root) + "/scripts/stage12_ra_g1_allocation.py", "exec"), namespace)
    monkeypatch.setattr(m, "PROCESS_TRACE", trace)
    monkeypatch.setattr(m, "main", namespace["main"])
    output = io.StringIO()
    with redirect_stdout(output):
        assert m.cli_entry() == 1
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    descriptor = records[0]["first_failure_descriptor"]
    assert calls == []
    assert descriptor["exception_kind"] == "UNKNOWN"
    assert descriptor["guard_code"] == "UNKNOWN"
    assert descriptor["capture_status"] == "UNSUPPORTED_EXCEPTION"
    assert descriptor["frames"][-1]["module_id"] == "ALLOCATION_CONTROLLER"
    assert records[1]["primary_failure"]["code"] == "UNKNOWN"
    assert "UNSAFE_QUERY_SECRET" not in output.getvalue()
    assert len(output.getvalue().encode()) <= 8192

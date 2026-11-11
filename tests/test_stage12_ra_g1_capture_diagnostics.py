"""Supplementary capture ownership only; connected readiness is tested separately."""

import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage


class Clock:
    def __init__(self, value=100):
        self.value = value

    def now_ns(self):
        return self.value


def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/stage12_ra_g1_diagnostic.py"
    spec = importlib.util.spec_from_file_location("capture_diagnostics_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result_from_actual_source(owner, *, failed=True, monitor=None, cleanup=None):
    """Execute the actual supplementary result expression, not campaign validators."""
    module = runner()
    tree = ast.parse(Path(module.__file__).read_text())
    node = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "result" for target in node.targets)
        and isinstance(node.value, ast.Call)
        and any(keyword.arg == "initiating_failure" for keyword in node.value.keywords)
    )
    foreground = dict(at_mono_ns=300, family="UNCLASSIFIED", code=None, errno=None, phase_id=1)
    namespace = dict(module.__dict__)
    namespace.update(
        data={"version": module.REP_ADMIN_VERSION},
        args=SimpleNamespace(source_sha="a" * 40, input_sha256="b" * 64),
        failure="RA_G1_DIAGNOSTIC_INCOMPLETE" if failed else None,
        first_failure=foreground if failed else None,
        capture_failures=owner,
        runtime_trace=SimpleNamespace(monitor_primary=lambda: monitor),
        cleanup_failure=cleanup,
        cleanup_failure_count=int(cleanup is not None),
        boundaries=[], attempts=0,
        phases=[] if failed else [{"test_only": True}] * 4,
        summary={"sampling_coverage_proof": False},
        resource_observation={"native_maximum": "NOT_PROVEN"}, resource_sessions=[],
        original=SimpleNamespace(counters=lambda: {"root_attempts": 0}),
        network_guard="TEST_ONLY_NO_SERVICE", budget=SimpleNamespace(snapshot=lambda: {}),
        creations=[0], clock=Clock(500), started_ns=0, cpu_started_ns=time.process_time_ns(),
    )
    return eval(compile(ast.Expression(node.value), module.__file__, "eval"), namespace)


def test_actual_capture_call_owns_existing_failures():
    """A wiring assertion, not a replacement for real Authority/admission tests."""
    module = runner()
    tree = ast.parse(Path(module.__file__).read_text())
    call = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and node.args
        and isinstance(node.args[0], ast.Constant) and node.args[0].value == "CAPTURE"
    )
    keyword = next(keyword for keyword in call.keywords if keyword.arg == "diagnostics")
    assert isinstance(keyword.value, ast.Name) and keyword.value.id == "capture_failures"
    owners = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "capture_failures" for target in node.targets)
    ]
    assert len(owners) == 1
    assert isinstance(owners[0].value, ast.Call) and owners[0].value.func.id == "Failures"


def test_earlier_capture_survives_later_monitor_and_cleanup():
    clock = Clock(100)
    owner = diagnostics.Failures(clock)
    owner.record("SAMPLER", TimeoutError("invented secret response text"))
    clock.value = 200
    owner.record("CLEANUP", RuntimeError("invented private path"))
    monitor = dict(at_mono_ns=250, family="CONTRACT_OR_GUARD", code="RA_G1_MONITOR_GAP", errno=None)
    cleanup = dict(at_mono_ns=400, family="UNCLASSIFIED", code=None, errno=None)
    result = result_from_actual_source(owner, monitor=monitor, cleanup=cleanup)
    capture = result["capture_failure_diagnostics"]
    assert capture["first_initiating_failure"]["mono_ns"] == 100
    assert capture["first_secondary_failure"]["mono_ns"] == 200
    assert result["initiating_failure"]["at_mono_ns"] == 300
    assert result["initiating_failure_scope"] == "CAUGHT_FOREGROUND_EXCEPTION_ONLY_SEE_CAPTURE_AND_MONITOR"
    assert result["resource_monitor_failure"] == monitor
    assert result["cleanup_failure"] == cleanup
    assert b"invented" not in contract.canonical(result)


@pytest.mark.parametrize("kind", ["ordinary", "stage12", "subclass"])
def test_unknown_and_secret_bearing_exceptions_stay_redacted(kind):
    class Hostile(contract.Stage12Error):
        def __str__(self):
            raise AssertionError("must never format this exception")

    error = {
        "ordinary": RuntimeError("invented secret body/header/path"),
        "stage12": contract.Stage12Error("invented secret body/header/path"),
        "subclass": Hostile("invented secret body/header/path"),
    }[kind]
    owner = diagnostics.Failures(Clock())
    owner.record("CAPTURE_FINALIZE", error)
    raw = contract.canonical(result_from_actual_source(owner))
    assert b"invented" not in raw and b"Hostile" not in raw
    assert owner.snapshot()["first_initiating_failure"]["code"] is None


def test_expected_negative_diagnostics_are_not_a_new_acceptance_gate():
    owner = diagnostics.Failures(Clock())
    owner.rejected("RESPONSE_CONTRACT_INVALID")
    owner.record("CAPTURE_FINALIZE", contract.Stage12Error("RESPONSE_CONTRACT_INVALID"))
    result = result_from_actual_source(owner, failed=False)
    assert result["complete"] is True and result["initiating_failure"] is None
    assert result["capture_failure_diagnostics"]["earlier_response_rejection"] == "RESPONSE_CONTRACT_INVALID"


def test_snapshot_survives_uncertain_writer_without_writer_reuse(tmp_path):
    owner = diagnostics.Failures(Clock())
    writer = journal.Writer(tmp_path / "campaign", 1, 30, lambda: None)
    writer.failures = owner
    release = threading.Event()
    entered = threading.Event()

    def blocked_action():
        entered.set()
        release.wait(1)

    try:
        with pytest.raises(TimeoutError):
            writer.call(blocked_action)
        assert entered.is_set() and writer.failed.is_set()
        snapshot = owner.snapshot()
        raw = contract.canonical(snapshot)
        assert len(raw) < 4096
        storage.write(tmp_path / "outside_campaign_failure.json", raw)
        assert storage.read(tmp_path / "outside_campaign_failure.json") == raw
        assert snapshot["first_initiating_failure"]["operation"] == "WRITER_WAIT"
        assert not (tmp_path / "campaign/_WRITER_RELEASED.json").exists()
    finally:
        release.set()
        writer.abort()
        assert not writer.thread.is_alive()


def test_first_owner_is_independent_of_saturated_startup_trace():
    module = runner()
    allocation = module.importlib.util.spec_from_file_location(
        "capture_trace_controller", Path(module.__file__).with_name("stage12_ra_g1_allocation.py")
    )
    controller = module.importlib.util.module_from_spec(allocation)
    allocation.loader.exec_module(controller)
    trace = controller.StartupTrace(1, clock_ns=lambda: 2)
    for _ in range(100):
        trace("MAIN_ENTER")
    owner = diagnostics.Failures(Clock(10))
    owner.record("SAMPLER", TimeoutError())
    assert owner.snapshot()["first_initiating_failure"]["mono_ns"] == 10
    assert trace.snapshot()["truncated"] is True


def test_legacy_supplementary_summary_remains_readable():
    old = {"version": "stage12_ra_g1_rep_admin_budget_representative_input_v1",
           "complete": False, "initiating_failure": None, "attempts": 0}
    assert storage.metadata(contract.canonical(old)) == old


def test_closure_successor_is_opt_in_and_preserves_historical_snapshot():
    owner = diagnostics.Failures(Clock())
    before = owner.snapshot()
    owner.closure_boundary("SNAPSHOT_PERSIST")
    assert owner.snapshot() == before
    assert set(before) == {"version", "scope", "first_initiating_failure",
                           "first_secondary_failure", "secondary_observations",
                           "earlier_response_rejection"}
    assert storage.metadata(contract.canonical(before)) == before


def test_closure_fixed_boundaries_preserve_primary_and_prepoison_state():
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_recovery import Deadline

    clock = Clock(100)
    owner = diagnostics.Failures(clock, closure=True)
    failed = threading.Event()
    writer = SimpleNamespace(failed=failed)
    deadline = Deadline(clock, 1000)
    owner.closure_boundary("PREPARE_ORIGINAL_VERIFY", writer=writer, deadline=deadline)
    clock.value = 200
    owner.closure_boundary("ORIGINAL_REPLAY", completed=True, writer=writer, deadline=deadline)
    owner.record("CLOSURE", TimeoutError("secret-bearing content"), writer=writer, deadline=deadline)
    first = owner.snapshot()
    failed.set()
    clock.value = 300
    owner.closure_boundary("SNAPSHOT_SEAL", writer=writer, deadline=deadline)
    owner.record("CLEANUP", RuntimeError("private content"), writer=writer)
    actual = owner.snapshot()
    assert actual["first_initiating_failure"] == first["first_initiating_failure"]
    assert actual["closure_boundary"]["first_failure"] == first["closure_boundary"]["first_failure"]
    retained = actual["closure_boundary"]["first_failure"]
    assert retained["failure"]["writer_failed"] is False
    assert retained["last_entered"]["stage"] == "PREPARE_ORIGINAL_VERIFY"
    assert retained["last_completed"]["stage"] == "ORIGINAL_REPLAY"
    assert retained["last_entered"]["deadline_ns"] == 1000
    assert retained["last_entered"]["deadline_identity"] == 1
    assert actual["first_secondary_failure"]["writer_failed"] is True
    assert len(contract.canonical(actual)) < 4096
    assert b"secret" not in contract.canonical(actual)


def test_closure_boundary_invalid_values_are_uncertain_and_never_formatted():
    owner = diagnostics.Failures(Clock(), closure=True)
    owner.closure_boundary("private arbitrary path text")
    owner.closure_boundary(object())
    assert owner.snapshot()["closure_boundary"]["retention_uncertain"]
    assert owner.snapshot()["closure_boundary"]["observation_faults"] == 2
    assert b"private" not in contract.canonical(owner.snapshot())


def test_closure_deadline_identity_detects_in_place_change_without_reset():
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_recovery import Deadline

    clock = Clock(100)
    deadline = Deadline(clock, 1000)
    owner = diagnostics.Failures(clock, closure=True)
    owner.closure_boundary("SNAPSHOT_PRECHECK", deadline=deadline)
    deadline.end_ns = 2000
    owner.closure_boundary("SNAPSHOT_PERSIST", deadline=deadline)
    state = owner.snapshot()["closure_boundary"]
    assert state["last_entered"]["deadline_ns"] == 2000
    assert state["last_entered"]["deadline_identity_unchanged"] is False
    assert state["retention_uncertain"] is True
    assert deadline.end_ns == 2000  # telemetry did not mutate the actual deadline


def test_closure_cleanup_only_does_not_claim_an_initiating_closure_failure():
    owner = diagnostics.Failures(Clock(), closure=True)
    owner.closure_boundary("T3_CLOSE")
    owner.record("CLEANUP", OSError(5, "private content"))
    assert owner.snapshot()["closure_boundary"]["first_failure"] is None


def test_closure_boundary_recorder_fault_does_not_retain_arbitrary_objects():
    class BrokenClock:
        def now_ns(self):
            raise RuntimeError("private content")

    owner = diagnostics.Failures(BrokenClock(), closure=True)
    owner.closure_boundary("SNAPSHOT_PERSIST")
    state = owner.snapshot()["closure_boundary"]
    assert state["last_entered"] is None and state["retention_uncertain"]
    assert b"private" not in contract.canonical(state)


def test_actual_earlier_writer_failure_is_not_relabelled_as_closure_cause(tmp_path):
    owner = diagnostics.Failures(Clock(), closure=True)
    writer = journal.Writer(tmp_path / "writer", 1, 5000, lambda: None)
    writer.failures = owner

    def failing_action():
        raise OSError(5, "INVENTED_PRIVATE_DETAILS")

    try:
        with pytest.raises(OSError):
            writer.call(failing_action)
        earlier = owner.snapshot()["first_initiating_failure"]
        assert earlier["operation"] == "WRITER_ACTION"
        assert earlier["writer_failed"] is False
        owner.closure_boundary("SNAPSHOT_PRECHECK", writer=writer)
        owner.record("CLOSURE", TimeoutError(), writer=writer)
        state = owner.snapshot()
        assert state["first_initiating_failure"] == earlier
        assert state["closure_boundary"]["first_failure"]["failure"]["writer_failed"] is True
        assert b"INVENTED_PRIVATE_DETAILS" not in contract.canonical(state)
    finally:
        writer.abort()
        assert not writer.thread.is_alive()


def test_closure_actual_original_scalar_guard_and_invalid_kind_redaction():
    owner = diagnostics.Failures(Clock(), closure=True)
    original = 123456789012345
    owner.closure_boundary("T3_REREAD", deadline_ns=original, guard="GLOBAL_TASK")
    row = owner.snapshot()["closure_boundary"]["last_entered"]
    assert row["deadline_ns"] == original and row["deadline_unit"] == "MONOTONIC_NS"
    assert row["guard_kind"] == "GLOBAL_TASK"
    assert row["deadline_identity_source"] == "ACTUAL_ORIGINAL_SCALAR"
    assert row["deadline_identity"] is None  # no invented object identity
    owner.closure_boundary("T3_REREAD", deadline_ns=original, guard="PRIVATE_UNKNOWN_GUARD")
    state = owner.snapshot()
    assert state["closure_boundary"]["last_entered"]["guard_kind"] is None
    assert state["closure_boundary"]["retention_uncertain"]
    assert b"PRIVATE_UNKNOWN_GUARD" not in contract.canonical(state)

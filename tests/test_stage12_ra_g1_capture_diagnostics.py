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

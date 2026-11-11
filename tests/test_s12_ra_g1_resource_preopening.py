"""Real session/writer/readback boundaries; injected faults are explicitly synthetic."""
import ast
from pathlib import Path
from types import SimpleNamespace
import threading
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_s12_ra_g1_execution import H, session


def owner():
    return d.Failures(SimpleNamespace(now_ns=time.monotonic_ns), closure=True)


def test_success_uses_actual_ack_original_reads_and_opener(tmp_path):
    value, _, reads = session(tmp_path)
    failures = owner()
    value.start()
    called = []
    result, records = value.freeze_and_open(
        frozen_data_inventory_sha256=H,
        actual_opener=lambda: called.append(True) or "actual-test-return",
        diagnostics=failures,
    )
    snap = failures.snapshot()["resource_preopening"]
    assert result == "actual-test-return" and called == [True] and reads
    assert value.completed and value.writer.released and "worker_validation" in records
    assert snap["first_failure"] is None
    assert snap["last_completed"]["stage"] == "COMPLETE_CHECK"


@pytest.mark.parametrize("stage", ["CHECK", "STATE", "START_ACK", "BARRIER", "FREEZE", "PREFIX", "PREOPEN_PERSIST", "PREOPEN_BIND"])
def test_exact_boundary_is_retained_before_real_abort(tmp_path, monkeypatch, stage):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    primary = c.Stage12Error("RA_G1_PROTOCOL")

    def reject(*args, **kwargs):
        raise primary

    expected_code = "RA_G1_PROTOCOL"
    if stage == "CHECK":
        original = value.external_check
        main_thread = threading.current_thread()
        def external():
            if threading.current_thread() is main_thread:
                raise primary
            original()
        monkeypatch.setattr(value, "external_check", external)
    elif stage == "STATE":
        value.protocol.state = "INCOMPLETE"
    elif stage == "START_ACK":
        value.monitor.first_start_receipt = None
        expected_code = "RA_G1_BOOTSTRAP_REQUIRED"
    elif stage == "BARRIER":
        value.monitor._latch_failure(primary)
    elif stage == "FREEZE":
        monkeypatch.setattr(value.protocol, "freeze", reject)
    elif stage == "PREFIX":
        monkeypatch.setattr(value.monitor, "prefix", reject)
    elif stage == "PREOPEN_PERSIST":
        monkeypatch.setattr(value, "_persist", reject)
    else:
        monkeypatch.setattr(value.protocol, "preopen", reject)
    opened = []
    with pytest.raises(c.Stage12Error) as caught:
        value.freeze_and_open(frozen_data_inventory_sha256=H,
            actual_opener=lambda: opened.append(True), diagnostics=failures)
    saved = failures.snapshot()["resource_preopening"]["first_failure"]
    assert caught.value.args == (expected_code,)
    assert saved["last_entered"]["stage"] == stage
    assert saved["failure"]["code"] == expected_code
    assert saved["failure"]["session_failed"] is False
    assert saved["failure"]["deadline_ns"] == value.deadline
    assert saved["failure"]["mono_ns"] <= saved["failure"]["snapshot_completed_mono_ns"]
    assert not opened and not value.completed and value.failed
    assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()
    if stage == "BARRIER":
        assert saved["failure"]["monitor"]["first_primary"]["code"] == expected_code
    if stage == "PREOPEN_BIND":
        assert "preopening" in value.records and not value.completed


def test_primary_precedes_cleanup_and_earlier_failure_is_unchanged(tmp_path, monkeypatch):
    value, _, _ = session(tmp_path)
    failures = owner()
    earlier = TimeoutError("INVENTED_SECRET")
    failures.record("SAMPLER", earlier)
    value.start()
    primary = c.Stage12Error("RA_G1_BOOTSTRAP_REQUIRED")
    cleanup = OSError(28, "INVENTED_SECRET_PATH")
    monkeypatch.setattr(value, "require_start_acknowledged", lambda: (_ for _ in ()).throw(primary))
    actual_abort = value.abort
    def abort():
        actual_abort()
        raise cleanup
    monkeypatch.setattr(value, "abort", abort)
    with pytest.raises(c.Stage12Error) as caught:
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda:None, diagnostics=failures)
    assert caught.value is primary
    snap = failures.snapshot()
    assert snap["first_initiating_failure"]["operation"] == "SAMPLER"
    first = snap["resource_preopening"]["first_failure"]
    second = snap["resource_preopening"]["first_cleanup_failure"]
    assert first["failure"]["code"] == "RA_G1_BOOTSTRAP_REQUIRED"
    assert second["failure"]["family"] == "OS_ERROR" and second["failure"]["errno"] == 28
    assert "INVENTED_SECRET" not in repr(snap)
    first["failure"]["code"] = "ALTERED_COPY"
    assert failures.snapshot()["resource_preopening"]["first_failure"]["failure"]["code"] == "RA_G1_BOOTSTRAP_REQUIRED"


def test_poison_and_real_monitor_primary_are_kept_separate(tmp_path):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    value.writer.poisoned = True
    with pytest.raises(c.Stage12Error):
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda:None, diagnostics=failures)
    saved = failures.snapshot()["resource_preopening"]["first_failure"]
    assert saved["failure"]["monitor"]["writer"]["poisoned"] is True
    assert saved["failure"]["code"] == "RA_G1_WRITE_UNCERTAIN"
    assert not value.completed


def test_diagnostic_fault_cannot_replace_real_boundary_failure(tmp_path, monkeypatch):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    primary = c.Stage12Error("RA_G1_BOOTSTRAP_REQUIRED")
    monkeypatch.setattr(value, "require_start_acknowledged", lambda: (_ for _ in ()).throw(primary))
    monkeypatch.setattr(failures, "resource_failure", lambda *a,**k: (_ for _ in ()).throw(RuntimeError("SECRET")))
    with pytest.raises(c.Stage12Error) as caught:
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda:None, diagnostics=failures)
    assert caught.value is primary and failures.snapshot()["closure_boundary"]["retention_uncertain"]


def test_unknown_exception_and_unsafe_snapshot_values_are_not_retained(tmp_path, monkeypatch):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    primary = RuntimeError("INVENTED_SECRET_PATH")
    original_snapshot = value.monitor.diagnostic_snapshot
    def unsafe():
        snap = original_snapshot()
        snap["first_primary"] = dict(family="INVENTED_SECRET", code="INVENTED_SECRET", errno=2**50,
            mono_ns=123, source="INVENTED_SECRET", stage="INVENTED_SECRET", unsafe="INVENTED_SECRET")
        return snap
    monkeypatch.setattr(value.monitor, "diagnostic_snapshot", unsafe)
    monkeypatch.setattr(value, "require_start_acknowledged", lambda: (_ for _ in ()).throw(primary))
    with pytest.raises(RuntimeError) as caught:
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda:None, diagnostics=failures)
    assert caught.value is primary
    snap = failures.snapshot()
    assert "INVENTED_SECRET" not in repr(snap)
    assert snap["resource_preopening"]["first_failure"]["failure"]["family"] == "UNCLASSIFIED"


def test_actual_deadline_error_remains_the_original_phase_error(tmp_path):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    value.deadline = time.monotonic_ns() - 1
    with pytest.raises(c.Stage12Error, match="RA_G1_DEADLINE"):
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda:None, diagnostics=failures)
    saved = failures.snapshot()["resource_preopening"]["first_failure"]
    assert saved["last_entered"]["stage"] == "CHECK"
    assert saved["failure"]["deadline_ns"] == value.deadline
    # Expired cleanup may not join in zero remaining time; this test owns the
    # already-stopped synthetic threads and observes their later bounded join.
    value.monitor.thread.join(1)
    value.writer.thread.join(1)
    assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()


def test_legacy_snapshot_and_real_production_wiring():
    historical = d.Failures(SimpleNamespace(now_ns=time.monotonic_ns))
    assert "resource_preopening" not in historical.snapshot()
    source = Path(__file__).resolve().parents[1]/"scripts/stage12_ra_g1_diagnostic.py"
    tree = ast.parse(source.read_text())
    calls = [n for n in ast.walk(tree) if isinstance(n,ast.Call) and any(
        isinstance(x,ast.Attribute) and x.attr=="freeze_and_open" for x in n.args)]
    assert any(any(k.arg=="diagnostics" and isinstance(k.value,ast.Name) and k.value.id=="capture_failures" for k in n.keywords) for n in calls)


def test_actual_cursor_cleanup_cannot_replace_actual_opener_failure(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    primary = c.Stage12Error("RA_G1_PROTOCOL")
    cleanup = OSError(5, "INVENTED_SECRET_CLOSE")
    actual_close = e.GrowingPrefix.close
    def close(cursor):
        actual_close(cursor)
        raise cleanup
    monkeypatch.setattr(e.GrowingPrefix, "close", close)
    def opener():
        assert value.cursor is not None
        raise primary
    with pytest.raises(c.Stage12Error) as caught:
        value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=opener, diagnostics=failures)
    assert caught.value is primary
    saved = failures.snapshot()["resource_preopening"]
    assert saved["first_failure"]["last_entered"]["stage"] == "DATA_OPENER"
    assert saved["first_cleanup_failure"]["failure"]["errno"] == 5
    assert saved["cleanup_observations"] == 2
    assert value.cursor.closed and not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()


def test_caller_precheck_is_captured_before_any_session_abort(tmp_path):
    value, _, _ = session(tmp_path)
    failures = owner()
    value.start()
    error = TimeoutError("INVENTED_SECRET_CALLER")
    failures.resource_boundary("CALLER_CHECK", deadline_ns=value.deadline)
    # Same existing failure owner used by the actual caller's outer handler.
    failures.resource_failure(error, session=value)
    saved = failures.snapshot()["resource_preopening"]["first_failure"]
    assert saved["last_entered"]["stage"] == "CALLER_CHECK"
    assert saved["failure"]["session_failed"] is False
    value.abort()
    assert saved == failures.snapshot()["resource_preopening"]["first_failure"]

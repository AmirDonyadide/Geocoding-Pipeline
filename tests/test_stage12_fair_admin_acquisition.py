"""One bounded actual acquisition path; private kernel facts are TEST_ONLY."""

import json
import os
import time
from types import SimpleNamespace

from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from test_stage12_ra_g1_native_root_sessions import KernelSession


def test_actual_acquisition_and_durable_original_path_is_measured_once(tmp_path, monkeypatch):
    """Real observer/parser/retention/fsync/ACK, no historical cost attribution.

    Existing finite syscall fixtures supply Linux proc/cgroup records on this
    host; all recorded timings are actual current local monotonic/thread clocks.
    The monitor's original 1000ms rule and selected one-second scope stay intact.
    """
    kernel = KernelSession(tmp_path, monkeypatch)
    failures = d.Failures(SimpleNamespace(now_ns=time.monotonic_ns), observer=True)
    args = kernel.arguments("REPRESENTATIVE_NO_SERVICE", phase=1,
                            native_roots=(kernel.output,))
    args["observer_stages"] = failures
    started = time.monotonic_ns()
    session = None
    try:
        session = e.start_session(**args)
        kernel.sessions.append(session)
        assert type(session.observer) is m.LinuxObserver
        receipt = session.require_start_acknowledged()
        assert receipt["row"]["seq"] == 1
        with session.writer.condition:
            remaining = max(0, args["deadline_ns"] - time.monotonic_ns()) / 1e9
            assert session.writer.condition.wait_for(
                lambda: session.writer.acked >= 2 or session.monitor.failure is not None,
                timeout=remaining,
            )
        assert session.monitor.failure is None
        snapshot = failures.snapshot()["observer_stages"]
        assert snapshot["calls"] == 2
        assert snapshot["last_acquisition"]["kind"] == "PERIODIC"
        assert snapshot["last_acquisition"]["returned"] is True
        assert not snapshot["retention_uncertain"]
        original = session.original_reader(session.monitor.last["visible_identity_inventory_sha256"])
        m.validate_original_observation(original, observation=session.monitor.last)
        assert set(snapshot["last_acquisition"]["stages"]) == set(d.OBSERVER_ROWS)
        assert snapshot["last_acquisition"]["stages"]["RETAIN_DIGEST"]["count"] == 1
        result = dict(
            scope="ONE_CURRENT_LOCAL_ACTUAL_ACQUISITION_NOT_NATIVE_CAUSE_OR_WHOLE_WORKFLOW_TIMING",
            kernel_and_scheduler="EXPLICIT_TEST_ONLY_EXISTING_KERNEL_SESSION_SYSCALL_FIXTURES",
            historical_duration_ns=1457202932,
            historical_lower_component_cause="UNKNOWN_NO_COMPONENT_TIMINGS_RETAINED",
            native_observer_gap_limit_ns=m.MAX_GAP_NS,
            elapsed_ns=time.monotonic_ns() - started,
            observer=snapshot, read_calls=session.observer.read_calls,
            read_bytes=session.observer.read_bytes, stat_calls=session.observer.stat_calls,
            durable_acked_rows=session.writer.acked,
            no_production_optimization=True,
        )
    finally:
        kernel.cleanup()
    result["all_owned_threads_joined"] = (
        not session.monitor.thread.is_alive() and not session.writer.thread.is_alive()
    )
    raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert len(raw) <= 16384
    fd = os.open(tmp_path / "ADMIN_ACQUISITION_RESULT.record", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        assert os.write(fd, raw) == len(raw)
    finally:
        os.close(fd)

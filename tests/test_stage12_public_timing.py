"""Offline synthetic timing boundaries; no protected bytes, keys or services."""

import threading

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from test_stage12_public_operations_v2 import (
    H,
    FakeClock,
    inputs,
    offline,  # noqa: F401 -- inherited denial fixture
)
from test_stage12_public_scheduler import (
    repair_common,
    sampling_controller,
    synthetic_dispatch,
)


def rows(observer):
    records = []
    result = cp.read_prefix(
        observer.checkpoints.root, record_consumer=lambda n, row: records.append(row)
    )
    assert not result["incomplete"]
    return [dict(zip(cp.PUBLIC_FIELDS, row, strict=True)) for row in records]


@pytest.mark.parametrize("cause", ["PERIODIC", "START_RESERVE"])
def test_real_resource_boundaries_and_exact_original_association(
    tmp_path, cause, monkeypatch
):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=2, interval_seconds=60
    )
    observer.set_phase(2)
    ctl.timing_observer = observer
    original = observer.checkpoints.record

    def record(row):
        assert not ctl.safety._is_owned()
        if cause == "PERIODIC":
            assert not ctl.sample_slot.locked()
        assert threading.current_thread() is not ctl.writer.thread
        original(row)

    monkeypatch.setattr(observer.checkpoints, "record", record)
    try:
        clock.advance(50_000_000)
        ctl.resource(cause)
        observer.sampling(ctl.sampling_snapshot())
        observer.close()
        record = rows(observer)[0]
        events = list(journal.read_events(ctl.writer.root, o.digest(start)))
        event = next(e for e in events if e["seq"] == record["event_seq"])
        timing.verify_association(tuple(record.values()), event, phase_id=2)
        assert record["outcome"] == "COMPLETE"
        assert record["observed_ns"] == 50_000_000
        timestamps = [
            record[name] for name in cp.PUBLIC_FIELDS[6:] if record[name] is not None
        ]
        assert timestamps == sorted(timestamps)
        assert (record["sampler_slot_released_ns"] is None) == (
            cause == "START_RESERVE"
        )
        for changed in ("seq", "mono_ns", "segment_id"):
            wrong = dict(event)
            wrong[changed] += 1
            with pytest.raises(cp.CheckpointError, match="CHECKPOINT_BINDING_INVALID"):
                timing.verify_association(tuple(record.values()), wrong, phase_id=2)
        with pytest.raises(cp.CheckpointError):
            timing.verify_association(tuple(record.values()), event, phase_id=1)
        assert observer.snapshot()["persistence_complete"]
        assert (
            observer.snapshot()["sampler_aggregates_by_phase"]["2"]
            == ctl.sampling_snapshot()
        )
    finally:
        ctl.writer.abort()


def test_append_action_return_and_future_postaction_are_separate(tmp_path):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=60
    )
    ctl.timing_observer = observer
    entered, release = threading.Event(), threading.Event()
    old_guard = ctl.writer.storage_guard
    traces = []
    begin = observer.begin
    observer.begin = lambda *a: traces.append(begin(*a)) or traces[-1]

    def guard():
        entered.set()
        assert release.wait(2)
        clock.advance(7)
        old_guard()

    ctl.writer.storage_guard = guard
    errors = []

    def collect():
        try:
            ctl.resource("PERIODIC")
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=collect)
    try:
        worker.start()
        assert entered.wait(2)
        trace = traces[0]
        assert trace.values["append_complete_ns"] is not None
        assert trace.values["writer_action_return_ns"] is not None
        assert trace.values["post_action_complete_ns"] is None
        assert trace.values["future_completion_ns"] is None
        assert trace.values["caller_ack_ns"] is None
        release.set()
        worker.join(2)
        assert not worker.is_alive() and not errors
        observer.close()
        record = rows(observer)[0]
        assert (
            record["post_action_complete_ns"] >= record["writer_action_return_ns"] + 7
        )
        assert record["future_completion_ns"] >= record["post_action_complete_ns"]
        assert record["journal_ack_ns"] >= record["caller_ack_ns"]
    finally:
        release.set()
        worker.join(2)
        ctl.writer.abort()


@pytest.mark.parametrize("failure", ["action", "postaction", "timeout", "free"])
def test_failure_partial_rows_do_not_invent_later_completion(
    tmp_path, failure, monkeypatch
):
    ctl, clock, start = sampling_controller(
        tmp_path, lambda: 2**42, writer_guard_ms=100
    )
    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=60
    )
    ctl.timing_observer = observer
    release = threading.Event()
    primary = OSError("UNSAFE_SYNTHETIC_MESSAGE_MUST_NOT_PERSIST")
    if failure == "action":
        monkeypatch.setattr(
            ctl.journal, "_readback", lambda *_: (_ for _ in ()).throw(primary)
        )
    elif failure == "postaction":
        ctl.writer.storage_guard = lambda: (_ for _ in ()).throw(primary)
    elif failure == "timeout":
        ctl.writer.storage_guard = lambda: release.wait(2)
    else:
        ctl.free_bytes = lambda: (_ for _ in ()).throw(primary)
    try:
        with pytest.raises((OSError, TimeoutError)) as caught:
            ctl.resource("PERIODIC")
        if failure != "timeout":
            assert caught.value is primary
        assert not ctl.sample_slot.locked()
        observer.close()
        record = rows(observer)[0]
        assert record["outcome"] == ("UNCERTAIN" if failure == "timeout" else "FAILED")
        assert record["post_action_complete_ns"] is None
        if failure in ("action", "free"):
            assert record["writer_action_return_ns"] is None
        if failure in ("timeout", "free"):
            assert record["future_completion_ns"] is None
        raw = b"".join(p.read_bytes() for p in observer.checkpoints.root.iterdir())
        assert b"UNSAFE_SYNTHETIC" not in raw
        # A late writer's completion cannot revise the frozen uncertain row.
        before = record.copy()
        release.set()
        ctl.writer.thread.join(0.02)
        assert rows(observer)[0] == before
    finally:
        release.set()
        ctl.writer.abort()


def test_supplementary_failure_never_poisons_authoritative_writer(
    tmp_path, monkeypatch
):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=60
    )
    ctl.timing_observer = observer
    monkeypatch.setattr(
        observer.checkpoints,
        "record",
        lambda *_: (_ for _ in ()).throw(OSError("private")),
    )
    try:
        ctl.resource("PERIODIC")
        assert not ctl.writer.failed.is_set()
        assert ctl.last_sample_ns == clock.now_ns()
        assert observer.snapshot()["observer_failure_count"] == 1
        observer.close()
        assert not observer.snapshot()["persistence_complete"]
    finally:
        ctl.writer.abort()


def test_charged_caps_uncertainty_and_truncation_remain_explicit(tmp_path, monkeypatch):
    observer = timing.PublicTiming(
        tmp_path / "telemetry",
        phase_count=1,
        max_files=1,
        ring_size=2,
        chunk_records=1,
        interval_seconds=60,
    )
    for n in range(4):
        trace = observer.begin("START_RESERVE", FakeClock())
        observer.finish(trace)
    observer.boundary()
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_FILE_LIMIT"):
        observer.close()
    snapshot = observer.snapshot()
    assert snapshot["charged_creations"] == 2  # root plus first chunk
    assert snapshot["checkpoint"]["dropped_unpersisted_rows"] == 3
    assert not snapshot["persistence_complete"]

    broken = timing.PublicTiming(
        tmp_path / "broken", phase_count=1, interval_seconds=60
    )
    monkeypatch.setattr(
        cp.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("private"))
    )
    with pytest.raises(cp.CheckpointError):
        broken.close()
    state = broken.snapshot()
    assert state["charged_bytes"] > 0 and state["charged_creations"] == 2
    assert state["checkpoint"]["persistence_uncertain"]
    assert state["checkpoint"]["reserved_files"] == 1


def test_enabled_and_disabled_full_synthetic_path_keep_authoritative_behavior(tmp_path):
    reports = []
    for enabled in (False, True):
        root = tmp_path / str(enabled)
        root.mkdir(mode=0o700)
        p, plan, start, work, inventory = inputs(2)
        clock = FakeClock()
        observer = (
            timing.PublicTiming(root / "telemetry", phase_count=1, interval_seconds=60)
            if enabled
            else None
        )
        report = cli.run_operations_block(
            p,
            plan,
            start,
            output=root / "campaign",
            clock=clock,
            dispatch=synthetic_dispatch(clock),
            epoch=H,
            timing_observer=observer,
            **repair_common(work, inventory),
        )
        reports.append(report)
        if observer:
            observer.close()
            assert observer.snapshot()["sampler_aggregates_by_phase"]
            assert rows(observer)
    for key in (
        "campaign_counts",
        "disposition",
        "report_complete",
        "scientific_identity_verified",
        "protected_readiness",
        "approval_status",
    ):
        assert reports[0][key] == reports[1][key]
    for key in ("cells", "counts", "status", "reasons", "resource_sampling_complete"):
        assert reports[0]["blocks"][0][key] == reports[1]["blocks"][0][key]


def test_reservation_fits_selected_task_budget_and_real_adapter(tmp_path):
    config = {
        "resources": {"allocated_disk_bytes": 512 * 2**30},
        "campaigns": [
            {
                "plan": {
                    "budgets": {
                        "storage_bytes": 480 * 2**30,
                        "event_count": 206000,
                        "data_attempts": 2880,
                        "control_http_attempts": 40,
                    }
                }
            }
        ],
    }
    observer = timing.for_task(config, tmp_path)
    try:
        reserve = observer.snapshot()["task_allocation_reservation"]
        assert reserve["bytes"] == 1500 * 32768 + 2**20
        assert reserve["creations"] == 1501
        assert reserve["task_file_ceiling"] == 300000
        assert runtime.filesystem_free_bytes(tmp_path) > 0
    finally:
        observer.close()
    config["resources"]["allocated_disk_bytes"] = 480 * 2**30
    with pytest.raises(cp.CheckpointError, match="CHECKPOINT_LIMIT_INVALID"):
        timing.for_task(config, tmp_path / "never-created")
    assert not (tmp_path / "never-created").exists()


def test_100_fully_populated_20hz_rows_fit_default_chunk_losslessly(tmp_path):
    writer = cp.Checkpoints(
        tmp_path / "compact", row_schema=cp.PUBLIC_SCHEMA, interval_seconds=60
    )
    absolute = 9_876_543_210_000_000
    originals = []
    for n in range(100):
        times = [absolute + n * 50_000_000 + i * 1000 for i in range(22)]
        row = [1, "PERIODIC", "COMPLETE", 1, n + 1] + times
        originals.append(tuple(row))
        writer.record(row)
    writer.close(timeout=2)
    actual = []
    prefix = cp.read_prefix(
        writer.root, record_consumer=lambda n, row: actual.append(row)
    )
    assert not prefix["incomplete"]
    assert actual == originals
    assert prefix["dropped_unpersisted_rows"] == 0
    assert prefix["verified_files"] == 1
    assert writer.snapshot()["persisted_bytes"] <= 32768


def test_outstanding_shutdown_is_explicit_without_waiting_for_blocked_sampler(tmp_path):
    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=1, interval_seconds=60
    )
    trace = observer.begin("PERIODIC", FakeClock())
    observer.close()
    state = observer.snapshot()
    assert state["outstanding_traces"] == 1
    assert not state["persistence_complete"]
    assert not state["final_timing_coverage_complete"]
    timing.safe_call(observer, "finish", trace)
    assert observer.snapshot()["observer_failure_count"] == 1


@pytest.mark.parametrize("observer_fails", [False, True])
def test_runtime_failure_retains_sampler_aggregates_and_primary_reason(
    tmp_path, monkeypatch, observer_fails
):
    from test_stage12_public_runtime import (
        test_actual_coordinator_capture_report_reopen_and_failure_honesty as exercise,
    )

    observer = timing.PublicTiming(
        tmp_path / "telemetry", phase_count=3, interval_seconds=60
    )
    execute = runtime.execute
    summaries = []

    if observer_fails:
        monkeypatch.setattr(
            observer, "close", lambda: (_ for _ in ()).throw(OSError("private"))
        )

    def injected(*a, **kw):
        summary = execute(*a, **kw, timing_observer=observer)
        summaries.append(summary)
        return summary

    monkeypatch.setattr(runtime, "execute", injected)
    exercise(monkeypatch, tmp_path, broken_reopen=True)
    summary = summaries[0]
    assert summary["public_path_timing"]["sampler_aggregates_by_phase"]["1"]
    assert summary["diagnostic_persistence_complete"] == (not observer_fails)
    import json

    stop = json.loads((tmp_path / ("or2_" + H) / "diagnostic_stop.json").read_bytes())
    assert stop["reason"] == "PUBLIC_PROBE_DIAGNOSTIC_STOPPED"
    failure = summary["failure_diagnostics"]["first_initiating_failure"]
    assert failure["operation"] == "RUNTIME_REOPEN" and failure["family"] == "STAGE12"
    assert summary["failure_diagnostics"]["first_secondary_failure"] is None
    if observer_fails:
        monkeypatch.undo()
        observer.close()


@pytest.mark.parametrize("disabled", [False, True])
def test_actual_matrix_execute_default_enable_and_explicit_false_optout(
    tmp_path, monkeypatch, disabled
):
    from test_stage12_public_matrix import (
        test_matrix_runtime_gates_reconciliation_and_shared_budget as exercise,
    )

    execute = runtime.execute
    summaries = []

    def observed(*a, **kw):
        if disabled:
            kw["timing_observer"] = False
        result = execute(*a, **kw)
        summaries.append(result)
        return result

    monkeypatch.setattr(runtime, "execute", observed)
    exercise(monkeypatch, tmp_path, stop_at=0)
    state = summaries[0]["public_path_timing"]
    assert state["enabled"] == (not disabled)
    assert state["persistence_complete"]
    root = tmp_path / ("or2_" + H) / "public_path_timing"
    assert root.exists() == (not disabled)
    if not disabled:
        prefix = cp.read_prefix(root)
        assert not prefix["incomplete"]
        assert state["task_allocation_reservation"]["task_file_ceiling"] == 300000

"""Bounded overhead, exact evidence and secret-safe failure regressions."""

import json
import threading
import importlib.util
from pathlib import Path
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_journal import setup
from test_stage12_public_operations_v2 import H, FakeClock, offline  # noqa: F401
from test_stage12_public_runtime import failed_public_pair


def diagnostic_asset():
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts/stage12_client_overhead_diagnostic.py"
    )
    spec = importlib.util.spec_from_file_location(
        "stage12_bounded_diagnostic_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("limit", [-1, True, 1.5])
def test_diagnostic_artifact_budget_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        diagnostic_asset().ArtifactBudget(limit)


def test_diagnostic_artifact_budget_is_bounded_concurrent_and_sticky():
    budget = diagnostic_asset().ArtifactBudget(200)
    threads = [
        threading.Thread(target=lambda: [budget.charge(1) for _ in range(50)])
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert budget.snapshot() == {
        "charged_upper_bytes": 200,
        "limit_bytes": 200,
        "exceeded": False,
    }
    with pytest.raises(RuntimeError, match="SYNTHETIC_ARTIFACT_LIMIT"):
        budget.charge(1)
    budget.charge(0)
    assert budget.snapshot() == {
        "charged_upper_bytes": 200,
        "limit_bytes": 200,
        "exceeded": True,
    }
    for bad in (-1, True, 1.5):
        with pytest.raises(ValueError):
            budget.charge(bad)


@pytest.mark.parametrize("kind", ["write", "array", "stream", "empty_array"])
def test_diagnostic_accounting_covers_artifact_write_paths(tmp_path, kind):
    module = diagnostic_asset()
    writer, log, _ = setup(tmp_path)
    budget = module.ArtifactBudget(4096)
    before = j.tree_bytes(writer.root)
    originals = module.install_artifact_accounting(io, j, budget)
    try:
        rows = [{"ordinal": 1}, {"ordinal": 2}]
        if kind == "write":
            writer.call(lambda: io.write(writer.root / "synthetic", b"synthetic"))
        elif kind == "stream":
            log.stream_array("rows.json", iter(rows))
        else:
            writer.call(
                lambda: log.write_array(
                    "rows.json", iter([] if kind == "empty_array" else rows)
                )
            )
        delta = j.tree_bytes(writer.root) - before
        # Buffered array accounting reserves one extra separator at most.
        assert delta <= budget.snapshot()["charged_upper_bytes"] <= delta + 1
        assert not budget.snapshot()["exceeded"]
    finally:
        io.write, module.os.write, j.Journal.write_array = originals
        writer.abort()


def test_diagnostic_reserves_before_failure_and_rejects_before_write(
    monkeypatch, tmp_path
):
    module = diagnostic_asset()
    budget = module.ArtifactBudget(5)
    calls = []

    def partial(path, raw):
        calls.append(len(raw))
        path.write_bytes(raw[:1])
        raise OSError(5, "invented failure")

    monkeypatch.setattr(io, "write", partial)
    originals = module.install_artifact_accounting(io, j, budget)
    try:
        with pytest.raises(OSError):
            io.write(tmp_path / "partial", b"abc")
        assert budget.snapshot()["charged_upper_bytes"] == 3
        with pytest.raises(RuntimeError, match="SYNTHETIC_ARTIFACT_LIMIT"):
            io.write(tmp_path / "denied", b"abc")
        assert calls == [3] and not (tmp_path / "denied").exists()
        assert budget.snapshot()["exceeded"]
    finally:
        io.write, module.os.write, j.Journal.write_array = originals


def test_diagnostic_partial_os_writes_keep_conservative_reservations(
    monkeypatch, tmp_path
):
    module = diagnostic_asset()
    writer, log, _ = setup(tmp_path)
    budget = module.ArtifactBudget(4096)
    before = j.tree_bytes(writer.root)
    original = module.os.write
    monkeypatch.setattr(module.os, "write", lambda fd, raw: original(fd, raw[:1]))
    originals = module.install_artifact_accounting(io, j, budget)
    try:
        log.stream_array("rows.json", iter([{"ordinal": 1}]))
        assert (
            budget.snapshot()["charged_upper_bytes"]
            > j.tree_bytes(writer.root) - before
        )
        assert list(j.read_array(writer.root / "rows.json")) == [{"ordinal": 1}]
    finally:
        io.write, module.os.write, j.Journal.write_array = originals
        writer.abort()


def test_diagnostic_watchdog_has_no_history_traversal():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(diagnostic_asset()))
    watchdog = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "watchdog"
    )
    calls = {
        n.func.attr
        for n in ast.walk(watchdog)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert not calls & {
        "rglob",
        "glob",
        "walk",
        "stat",
        "scandir",
        "read_events",
        "realpath",
    }
    assert "snapshot" in calls and "getrusage" in calls
    # Exactly one final inventory, outside the recurring watchdog.
    assert (
        sum(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "rglob"
            for n in ast.walk(tree)
        )
        == 1
    )


def periodic(log, n):
    log.event(
        "RESOURCE",
        {
            "observed_mono_ns": n,
            "cause": "PERIODIC",
            "connection_slots": 0,
            "admitted_operations": 0,
            "pending_count": 0,
            "pending_bytes": 0,
            "reserved_bytes": 0,
            "free_allocated_disk_bytes": 2**40,
        },
        periodic=True,
    )


@pytest.mark.parametrize("count", [1, 20, 60])
def test_samples_do_not_recursively_scan_history(monkeypatch, tmp_path, count):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    original = j.tree_bytes
    scans = 0

    def scan(*a, **kw):
        nonlocal scans
        scans += 1
        return original(*a, **kw)

    monkeypatch.setattr(j, "tree_bytes", scan)
    for i in range(count):
        periodic(log, i)
    assert scans == 0  # Every append still fsyncs and reads back exact bytes.
    assert writer.call(log.verify_storage) == log.accounted_bytes
    assert scans > 0
    writer.abort()


@pytest.mark.parametrize("change", ["new", "extend", "remove", "symlink"])
def test_accounting_tamper_detected_at_boundary(tmp_path, change):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    p = writer.root / "events/00000000000000000001.json"
    if change == "new":
        (writer.root / "untracked").write_bytes(b"x")
    elif change == "extend":
        p.write_bytes(p.read_bytes() + b"x")
    elif change == "remove":
        p.unlink()
    else:
        (writer.root / "untracked").symlink_to(p)
    with pytest.raises(c.Stage12Error):
        writer.call(log.verify_storage)
    assert writer.failed.is_set()
    writer.abort()


def test_uncertain_write_keeps_full_charge_and_first_error(monkeypatch, tmp_path):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    failures = d.Failures(FakeClock())
    writer.failures = failures
    before = log.accounted_bytes

    def fail(*a):
        raise OSError(5, "DO_NOT_RETAIN_secret_or_query")

    monkeypatch.setattr(io, "fsync_directory", fail)
    with pytest.raises(OSError):
        writer.call(lambda: io.write(writer.root / "partial", b"synthetic"))
    assert log.accounted_bytes == before + len(b"synthetic")
    with pytest.raises(c.Stage12Error):
        writer.call(lambda: None)
    assert failures.snapshot()["first_initiating_failure"]["errno"] == 5
    assert "secret_or_query" not in json.dumps(failures.snapshot())
    assert not (writer.root / "_SEGMENT_SEALED").exists()
    writer.abort()


@pytest.mark.parametrize("target", ["projection", "original", "extra", "tail"])
def test_prefix_exact_binding_and_invalidations(tmp_path, target):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    periodic(log, 0)
    prefix = j.MeasurementPrefix(log)
    assert prefix.build()
    assert list(prefix.events()) == list(j.read_events(writer.root, log.start_hash))
    if target == "projection":
        raw = prefix.path.read_bytes()
        prefix.path.write_bytes(
            raw.replace(
                b'"free_allocated_disk_bytes":1099511627776',
                b'"free_allocated_disk_bytes":1099511627775',
            )
        )
        with pytest.raises(c.Stage12Error):
            list(prefix.events())
    elif target == "original":
        path = writer.root / "events/00000000000000000002.json"
        path.write_bytes(path.read_bytes().replace(b"1099511627776", b"1099511627775"))
        with pytest.raises(c.Stage12Error):
            prefix.verify_original()
    elif target == "extra":
        (writer.root / "events/invalid.json").write_bytes(b"{}\n")
        with pytest.raises(c.Stage12Error):
            prefix.verify_original()
    else:
        periodic(log, 1)
        assert list(prefix.events()) == list(j.read_events(writer.root, log.start_hash))
        path = writer.root / "events/00000000000000000003.json"
        path.write_bytes(path.read_bytes().replace(b"1099511627776", b"1099511627775"))
        with pytest.raises(c.Stage12Error):
            list(prefix.events())
    writer.abort()


def test_prefix_bound_fallback_and_deadline(monkeypatch, tmp_path):
    writer, log, _ = setup(tmp_path)
    prefix = j.MeasurementPrefix(log)
    monkeypatch.setattr(prefix, "LIMIT", 1)
    assert not prefix.build() and not prefix.path.exists()
    monkeypatch.setattr(prefix, "LIMIT", 64 * 2**20)
    assert prefix.build()
    clock = FakeClock()
    deadline = recovery.Deadline(clock, 1)
    writer.check_deadline = deadline.check
    clock.advance(1)
    with pytest.raises(recovery.FinalizationExpired):
        list(prefix.events())
    writer.abort()


def test_readonly_projection_rebinds_original_and_preserves_tail(tmp_path, monkeypatch):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    for i in range(20):
        periodic(log, i)
    prefix = j.MeasurementPrefix(log)
    assert prefix.build()
    log.event(
        "SEGMENT_CLOSE",
        {"disposition": "PAUSED_CLEAN", "closure_evidence_sha256": H, "last_ticket": 0},
        closure=True,
    )
    expected = list(j.read_events(writer.root, log.start_hash))
    reopened = j.MeasurementPrefix.from_closed(
        writer.root, log.start_hash, prefix.seq, check=lambda: None
    )
    reopened.verify_original()
    reads = 0
    read = io.read

    def counted(path, **kw):
        nonlocal reads
        reads += path.parent.name == "events"
        return read(path, **kw)

    monkeypatch.setattr(io, "read", counted)
    assert list(reopened.events()) == expected
    assert reads == 1  # Tail only; every projected row is still chain-validated.
    path = writer.root / "events/00000000000000000002.json"
    path.write_bytes(path.read_bytes().replace(b"1099511627776", b"1099511627775"))
    with pytest.raises(c.Stage12Error):
        reopened.verify_original()
    with pytest.raises(c.Stage12Error):
        j.MeasurementPrefix.from_closed(
            writer.root, log.start_hash, prefix.seq, check=lambda: None
        )
    writer.abort()


def test_prefix_keeps_full_metadata_reserve(tmp_path):
    writer, log, _ = setup(tmp_path)
    log.enable_accounting()
    prefix = j.MeasurementPrefix(log)
    assert not prefix.build(closure_reserve=log.storage_budget)
    assert not prefix.path.exists() and not writer.failed.is_set()
    writer.abort()


@pytest.mark.parametrize(
    "error,expected",
    [
        (c.Stage12Error("S12_PUBLIC_WINDOW_CLOSED"), "STAGE12"),
        (c.Stage12Error("S12_SECRET_PAYLOAD_CANARY"), "STAGE12"),
        (OSError(5, "SECRET_PAYLOAD_CANARY", "/unsafe/secret"), "OS_ERROR"),
        (TimeoutError("SECRET_PAYLOAD_CANARY"), "TIMEOUT"),
        (ValueError("SECRET_PAYLOAD_CANARY"), "UNCLASSIFIED"),
        (recovery.FinalizationExpired(), "CUMULATIVE_DEADLINE"),
    ],
)
def test_safe_first_failure_secondary_and_rejection_separate(error, expected):
    clock = FakeClock()
    failures = d.Failures(clock)
    failures.rejected("RESPONSE_CONTRACT_INVALID")
    failures.record("ADMISSION", error, work_id=7, attempt=1)
    clock.advance(9)
    failures.record("CLEANUP", OSError(28, "SECRET_PAYLOAD_CANARY"))
    for _ in range(100):
        failures.record("SECRET_PAYLOAD_CANARY", error)
    record = failures.snapshot()
    assert record["first_initiating_failure"]["family"] == expected
    assert record["first_initiating_failure"]["mono_ns"] == 0
    assert record["first_secondary_failure"]["mono_ns"] == 9
    assert record["secondary_observations"] == 101
    assert record["earlier_response_rejection"] == "RESPONSE_CONTRACT_INVALID"
    assert "SECRET_PAYLOAD_CANARY" not in json.dumps(record)


def test_failure_records_bound_under_concurrency():
    failures = d.Failures(FakeClock())
    threads = [
        threading.Thread(target=lambda: failures.record("SAMPLER", RuntimeError()))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert failures.snapshot()["secondary_observations"] == 3


def test_one_validated_prefix_per_size_gate(monkeypatch, tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as scheduler,
    )
    from test_stage12_public_followup import (
        test_successor_full_six_size_pairs_complete_without_feature_pin,
    )

    original_admit, original_events = scheduler.Coordinator.admit, j.read_events
    counts = []
    count = 0

    def events(*a, **kw):
        nonlocal count
        count += 1
        yield from original_events(*a, **kw)

    monkeypatch.setattr(j, "read_events", events)

    def admit(self, *a, **kw):
        ready = self.size_ready

        def gate(pending):
            before = count
            value = ready(pending)
            counts.append(count - before)
            return value

        self.size_ready = gate
        try:
            return original_admit(self, *a, **kw)
        finally:
            self.size_ready = ready

    monkeypatch.setattr(scheduler.Coordinator, "admit", admit)
    test_successor_full_six_size_pairs_complete_without_feature_pin(
        monkeypatch, tmp_path
    )
    assert len(counts) == 12 and max(counts) == 1


def test_stream_derivation_records_failure_before_cleanup(monkeypatch, tmp_path):
    writer, log, _ = setup(tmp_path)
    failures = d.Failures(FakeClock())
    writer.failures = failures

    def rows():
        yield {"synthetic": 1}

        def fsync(*_):
            raise OSError(5, "unsafe_cleanup")

        monkeypatch.setattr(j.os, "fsync", fsync)
        raise ValueError("unsafe_original")

    with pytest.raises(ValueError):
        log.stream_array("derived.json", rows())
    record = failures.snapshot()
    assert record["first_initiating_failure"]["family"] == "UNCLASSIFIED"
    assert record["first_secondary_failure"]["family"] == "OS_ERROR"
    assert "unsafe" not in json.dumps(record)
    writer.abort()


def test_report_error_then_reconciliation_error_keeps_first(monkeypatch, tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_reporting as reporting,
    )
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli

    failures = d.Failures(FakeClock())
    original = cli.run_operations_block

    def run(*a, **kw):
        return original(*a, **kw, diagnostics=failures)

    monkeypatch.setattr(cli, "run_operations_block", run)

    def bad_report(*a, **kw):
        raise c.Stage12Error("S12_PUBLIC_WINDOW_CLOSED")

    def bad_reconcile(*a, **kw):
        raise OSError(5, "unsafe_canary")

    monkeypatch.setattr(reporting, "block_report", bad_report)
    monkeypatch.setattr(recovery, "unclean_reconciliation", bad_reconcile)
    root, result, _, _ = failed_public_pair(tmp_path, monkeypatch)
    record = failures.snapshot()
    assert record["first_initiating_failure"]["operation"] == "REPORT"
    assert record["first_initiating_failure"]["code"] == "S12_PUBLIC_WINDOW_CLOSED"
    assert record["first_secondary_failure"]["operation"] == "RECONCILIATION"
    assert record["earlier_response_rejection"] == "RESPONSE_CONTRACT_INVALID"
    assert not result["report_complete"] and not (root / "_SEGMENT_SEALED").exists()


@pytest.mark.parametrize(
    "file",
    ["diagnostic_stop.json", "failure_diagnostics.json", "diagnostic_summary.json"],
)
def test_runtime_original_survives_supplementary_persistence_failure(
    monkeypatch, tmp_path, file
):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from test_stage12_public_runtime import (
        test_actual_coordinator_capture_report_reopen_and_failure_honesty,
    )

    error = OSError(5, "do_not_record_primary_canary")

    def reopen(*a, **kw):
        raise error

    monkeypatch.setattr(runtime, "reopen_completed", reopen)
    original = io.write

    def write(path, raw):
        if path.name == file:
            raise OSError(28, "do_not_record_cleanup_canary")
        return original(path, raw)

    monkeypatch.setattr(io, "write", write)
    with pytest.raises(OSError) as caught:
        test_actual_coordinator_capture_report_reopen_and_failure_honesty(
            monkeypatch, tmp_path, False
        )
    assert caught.value is error
    root = tmp_path / ("or2_" + H)
    path = root / (
        "failure_diagnostics.json"
        if file == "diagnostic_summary.json"
        else "diagnostic_summary.json"
    )
    obj = json.loads(path.read_bytes())
    evidence = obj.get("failure_diagnostics", obj)
    assert evidence["first_initiating_failure"]["operation"] == "RUNTIME_REOPEN"
    assert evidence["first_initiating_failure"]["errno"] == 5
    assert "canary" not in json.dumps(obj)
    if file != "diagnostic_summary.json":
        assert not obj["diagnostic_persistence_complete"]
        assert obj["qualified_public_rates"] == []

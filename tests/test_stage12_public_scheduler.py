"""Controller races/resources/retries and the complete injected public path."""

from dataclasses import replace

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as v1
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as s
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t
from test_stage12_public_operations_v2 import (
    H,
    KEY,
    FakeAuthority,
    FakeClock,
    inputs,
    rebind,
    offline,  # noqa: F401 -- imported autouse network/credential denial fixture
)
from test_stage12_public_operational_audit import capture
from stage12_synthetic import body


def repair_common(rows, runtime, authority=None):
    """Explicit offline inputs shared by F01–F06 corrected-behavior tests."""
    return dict(
        work_factory=lambda: iter(rows),
        block_id=1,
        authority=authority or FakeAuthority(),
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        writer_release_evidence=H,
    )


class FakeMonitor:
    def __init__(self, clock):
        self.clock = clock
        self.fail = False

    def before_dispatch(self):
        c.require(not self.fail, "IDENTITY_VERIFICATION_STALE")

    def before_response(self, work, result):
        self.before_dispatch()

    def accept(self, receipt_sha256, *, closure):
        self.before_dispatch()
        return self.clock.now_ns()


def controller(tmp_path, count=4, rate=20, monitored=False):
    profile, plan, start, rows, runtime = inputs(count, rate, monitored=monitored)
    clock = FakeClock()
    monitor = FakeMonitor(clock) if monitored else None
    ctl = s.Coordinator(
        profile,
        plan,
        start,
        authority=FakeAuthority(),
        clock=clock,
        root=tmp_path / "campaign",
        block_id=1,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        free_bytes=lambda: 2**42,
        monitor=monitor,
    )
    if monitored:
        ctl.verified_ns = 0
        ctl.state = "RUNNING"
    return ctl, rows


def start_slot(ctl, row, attempt=1):
    ctl.clock.wait_until(ctl.next_start_ns)
    ctl.queue(s.Pending(row, b"/synthetic-only", attempt, ctl.clock.now_ns()))

    def begin(pending):
        raw = c.canonical(
            {
                "work_id": row["work_id"],
                "attempt": attempt,
                "scope": "SYNTHETIC_TEST_ONLY",
            }
        )
        io.write(ctl.writer.root / f"begin_{row['work_id']}_{attempt}.json", raw)
        return c.sha(raw).hex()

    slot = ctl.admit(begin)
    assert slot is not None
    ctl.started(slot, ctl.clock.now_ns())
    return slot


def complete_slot(ctl, slot, result=None):
    result = result or capture(body([]))
    ctl.completed(
        slot,
        result,
        H,
        lambda: io.write(
            ctl.writer.root / f"transport_{slot.key[0]}_{slot.key[1]}.json",
            c.canonical({"scope": "SYNTHETIC_TEST_ONLY"}),
        ),
    )


def finalize_slot(ctl, slot, outcome=c.SUCCESS[1]):
    return ctl.finalize(
        slot, lambda: ({"outcome": outcome, "reason_code": slot.capture.reason}, H)
    )


@pytest.mark.parametrize("rate", [20, 40, 60])
def test_T02_actual_writes_paced_after_reverse_TLS_completion(tmp_path, rate):
    ctl, rows = controller(tmp_path, rate=rate)
    first, second = start_slot(ctl, rows[0]), start_slot(ctl, rows[1])
    writes = []
    ctl.emit(second, lambda: writes.append(ctl.clock.now_ns()), lambda: None)
    ctl.emit(first, lambda: writes.append(ctl.clock.now_ns()), lambda: None)
    assert writes[1] - writes[0] >= o.interval({"num": rate, "den": 1})
    assert ctl.charged["DATA"] == 2
    assert first.started_ns < second.started_ns
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T03_stop_wins_and_committed_write_remains_inflight(tmp_path):
    ctl, rows = controller(tmp_path)
    slot = start_slot(ctl, rows[0])
    ctl.terminal("OPERATOR")
    writes = []
    with pytest.raises(t.DispatchBlocked):
        ctl.emit(slot, lambda: writes.append(1), lambda: None)
    assert not writes and slot.committed_ns is None and ctl.state == "RECOVERY_BLOCKED"
    assert ctl.charged["DATA"] == 1
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T03_commit_wins_then_stop_can_precede_socket_write(tmp_path):
    ctl, rows = controller(tmp_path)
    slot = start_slot(ctl, rows[0])
    writes = []
    original = ctl.journal.event

    def record(kind, value, **kwargs):
        result = original(kind, value, **kwargs)
        if kind == "EMIT_COMMITTED":
            ctl.terminal("OPERATOR")
        return result

    ctl.journal.event = record
    ctl.emit(slot, lambda: writes.append(1), lambda: None)
    assert writes == [1] and slot.committed_ns is not None
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T04_T05_closed_socket_does_not_release_memory_and_ticket_order(tmp_path):
    ctl, rows = controller(tmp_path)
    first, second = start_slot(ctl, rows[0]), start_slot(ctl, rows[1])
    ctl.emit(second, lambda: None, lambda: None)
    ctl.emit(first, lambda: None, lambda: None)
    complete_slot(ctl, second)
    complete_slot(ctl, first)
    assert not first.connection and not second.connection
    assert len(ctl.slots) * o.RESERVATION == o.MEMORY
    ctl.queue(s.Pending(rows[2], b"/synthetic", 1, ctl.clock.now_ns()))
    assert ctl.admit(lambda _: H) is None
    with pytest.raises(c.Stage12Error):
        finalize_slot(ctl, first)
    finalize_slot(ctl, second)
    finalize_slot(ctl, first)
    assert len(ctl.slots) == 0 and ctl.finalized_ticket == 2
    events = list(j.read_events(ctl.writer.root, ctl.journal.start_hash))
    assert [
        e["body"]["work_id"] for e in events if e["kind"] == "ATTEMPT_FINALIZED"
    ] == [2, 1]
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T06_retry_delay_preserves_fixture_key_and_429_cooldown(tmp_path):
    ctl, rows = controller(tmp_path)
    slot = start_slot(ctl, rows[0])
    ctl.emit(slot, lambda: None, lambda: None)
    complete_slot(ctl, slot, capture(None, 429))
    retry = finalize_slot(ctl, slot, "TECHNICAL_FAILURE_RETRYABLE")
    assert retry.attempt == 2
    expected = v1.retry_delay(
        bytes.fromhex(rows[0]["fixture_id"]), 2, None, v1.Operations()
    )
    assert retry.due_ns - ctl.clock.now_ns() == expected * 1_000_000
    assert ctl.cooldown_until >= 30_000_000_000
    ctl.queue(retry)
    assert ctl.admit(lambda _: H) is None
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T08_consecutive_errors_break_before_fourth_and_no_reset(tmp_path):
    ctl, rows = controller(tmp_path)
    for row in rows[:3]:
        slot = start_slot(ctl, row)
        ctl.emit(slot, lambda: None, lambda: None)
        result = t.Capture(
            "TECHNICAL_FAILURE_RETRYABLE",
            "TIMEOUT",
            None,
            "ABSENT",
            "absent",
            None,
            None,
            0,
            1,
        )
        complete_slot(ctl, slot, result)
        finalize_slot(ctl, slot, "TECHNICAL_FAILURE_RETRYABLE")
    assert ctl.stop_reason == "BREAKER" and ctl.consecutive == 3
    ctl.clock.advance(10**12)
    ctl.tick()
    assert ctl.admit(lambda _: H) is None
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T09_monitor_slot_and_disjoint_completion_headroom(tmp_path):
    ctl, rows = controller(tmp_path, monitored=True)
    first = start_slot(ctl, rows[0])
    ctl.clock.wait_until(ctl.next_start_ns)
    ctl.queue(s.Pending(rows[1], b"/synthetic", 1, ctl.clock.now_ns()))
    assert ctl.admit(lambda _: H) is None
    ctl.c = 98
    assert ctl.monitoring_due()
    complete_slot(ctl, first)
    assert (ctl.c, ctl.a) == (99, 0) and len(ctl.slots) == 1
    ctl.clock.wait_until(60_000_000_000)
    ctl.tick()
    assert ctl.state == "QUARANTINED"
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def test_T15_walltime_and_pending_bytes_stop_admission(tmp_path):
    ctl, rows = controller(tmp_path)
    with pytest.raises(c.Stage12Error):
        ctl.queue(
            s.Pending(
                rows[0], b"x" * (ctl.resources["pending_request_bytes"] + 1), 1, 0
            )
        )
    ctl.clock.wait_until(600_000_000_000)
    ctl.tick()
    assert ctl.stop_reason == "TIME"
    assert ctl.admit(lambda _: H) is None
    ctl.writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


def synthetic_dispatch(clock, result=None):
    def dispatch(work, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: clock.advance(1_000_000), lambda: None)
        value = result or capture(body([]))
        hooks.signal(
            value.status, value.outcome, value.reason, value.retry_after_seconds
        )
        clock.advance(1_000_000)
        hooks.completed(value)
        return value

    return dispatch


def run_offline(tmp_path, *, count=2, result=None):
    profile, plan, start, rows, runtime = inputs(count)
    clock = FakeClock()
    output = tmp_path / "full"
    result = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=output,
        block_id=1,
        authority=FakeAuthority(),
        clock=clock,
        dispatch=synthetic_dispatch(clock, result),
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
    )
    return result, output, (profile, plan, start, rows, runtime)


def test_T05_T10_T14_full_offline_path_keeps_science_blocked(tmp_path):
    report, output, data = run_offline(tmp_path)
    assert report["schema_version"] == o.REPORT
    assert report["disposition"] == "COMPLETED"
    assert report["scientific_identity_verified"] is False
    assert report["protected_readiness"] == "BLOCKED"
    assert report["blocks"][0]["status"] == "EXPLORATORY_ONLY"
    assert report["campaign_counts"]["durable_valid_data"]["value"] == 2
    assert (output / "_SEGMENT_SEALED").is_file()
    assert not (output / "_COMMITTED").exists()
    assert io.metadata(io.read(output / "campaign_report.json")) == report


def test_T09_T16_monitored_refresh_data_closure_share_limits(tmp_path):
    from test_stage12_public_operational_audit import Control

    profile, plan, start, rows, runtime = inputs(2, monitored=True)
    clock = FakeClock()
    order = []

    def dispatch(work, target, hooks):
        order.append(work["kind"])
        result = (
            capture(c.canonical({"synthetic_index": "test"}))
            if work["kind"] == "SERVICE_CONTROL"
            else capture(body([]))
        )
        return synthetic_dispatch(clock, result)(work, target, hooks)

    output = tmp_path / "monitored"
    report = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=output,
        block_id=1,
        authority=FakeAuthority(),
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={1: Control(), 2: Control()},
        monitor=FakeMonitor(clock),
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
    )
    assert report["disposition"] == "COMPLETED"
    assert order == ["SERVICE_CONTROL", "DATA", "DATA", "SERVICE_CONTROL"]
    counts = report["campaign_counts"]
    assert counts["attempt_starts"]["value"] == 4
    assert counts["durable_valid_data"]["value"] == 2
    assert counts["control_attempt_starts"]["value"] == 2
    events = list(j.read_events(output, o.digest(start)))
    starts = [
        e["body"]["started_mono_ns"] for e in events if e["kind"] == "ATTEMPT_STARTED"
    ]
    assert all(b - a >= 50_000_000 for a, b in zip(starts, starts[1:]))
    assert [
        e["body"]["interval_closed"] for e in events if e["kind"] == "MONITOR_RESULT"
    ] == [False, True]
    assert (
        report["scientific_identity_verified"]
        and report["protected_readiness"] == "BLOCKED"
    )


def test_T07_T12_unknown_dispatch_returns_exact_incomplete_schema(tmp_path):
    profile, plan, start, rows, runtime = inputs(1)
    output = tmp_path / "unknown"

    def broken(*_):
        raise OSError("synthetic uncertain dispatch")

    result = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=output,
        block_id=1,
        authority=FakeAuthority(),
        clock=FakeClock(),
        dispatch=broken,
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
    )
    o.validate(result, o.REPORT)
    assert result["disposition"] == "RECOVERY_BLOCKED" and not result["report_complete"]
    assert result["campaign_counts"]["begins_charged"] == {
        "value": None,
        "confirmed_min": 1,
    }
    assert (
        not (output / "snapshot.json").exists()
        and not (output / "_SEGMENT_SEALED").exists()
    )
    assert not list((output / "attempts").rglob("*_finish.json"))
    assert io.metadata(io.read(output / "incomplete_campaign_report.json")) == result


def test_T08_inclusive_overload_boundary_latches_before_finalization(tmp_path):
    ctl, rows = controller(tmp_path)
    first = start_slot(ctl, rows[0])
    ctl.signal(first, 429, "TECHNICAL_FAILURE_RETRYABLE", "RATE_LIMITED", None)
    # Already committed second attempt can return at the inclusive boundary.
    ctl.clock.advance(60_000_000_000)
    second = s.Slot(s.Pending(rows[1], b"/synthetic", 1, 0), H)
    ctl.signal(second, 503, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT", None)
    assert ctl.stop_reason == "BREAKER" and ctl.finalized_ticket == 0
    ctl.signal(second, 503, "TECHNICAL_FAILURE_RETRYABLE", "SERVER_TRANSIENT", None)
    assert len(ctl.overloads) == 2
    ctl.writer.abort()


def test_T06_fifth_retryable_stops_without_ordinal_six(tmp_path):
    ctl, rows = controller(tmp_path, count=5)
    for ordinal in range(1, 6):
        slot = start_slot(ctl, rows[0], attempt=ordinal)
        ctl.emit(slot, lambda: None, lambda: None)
        complete_slot(
            ctl,
            slot,
            t.Capture(
                "TECHNICAL_FAILURE_RETRYABLE",
                "TIMEOUT",
                None,
                "ABSENT",
                "absent",
                None,
                None,
                0,
                1,
            ),
        )
        retry = finalize_slot(ctl, slot, "TECHNICAL_FAILURE_RETRYABLE")
        if ordinal < 5:
            assert retry.attempt == ordinal + 1
            other = start_slot(ctl, rows[ordinal])
            ctl.emit(other, lambda: None, lambda: None)
            complete_slot(ctl, other)
            finalize_slot(ctl, other)
            ctl.clock.wait_until(retry.due_ns)
        else:
            assert retry is None
    assert ctl.stop_reason == "BREAKER"
    finals = [
        e
        for e in j.read_events(ctl.writer.root, ctl.journal.start_hash)
        if e["kind"] == "ATTEMPT_FINALIZED" and e["body"]["work_id"] == 1
    ]
    assert [e["body"]["attempt"] for e in finals] == [1, 2, 3, 4, 5]
    final = finals[-1]
    assert final["body"]["attempt"] == 5 and final["body"]["retry_delay_ms"] is None
    assert final["body"]["outcome"]["value"] == "TECHNICAL_FAILURE_RETRYABLE"
    ctl.writer.abort()


def test_T13_downshift_persists_frontiers_and_rejects_rebound(tmp_path):
    profile, plan, start, rows, _ = inputs(2)
    profile["states"].append(
        {**profile["states"][0], "state_id": 2, "rate": {"num": 40, "den": 1}}
    )
    plan["blocks"][0].update(state_id=2, fallback_state_ids=[1])
    rebind(profile, plan, start)
    ctl = s.Coordinator(
        profile,
        plan,
        start,
        authority=FakeAuthority(),
        clock=FakeClock(),
        root=tmp_path / "down",
        block_id=1,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        free_bytes=lambda: 2**42,
    )
    slot = start_slot(ctl, rows[0])
    ctl.emit(slot, lambda: None, lambda: None)
    ctl.downshift(1, "RESOURCE_PRESSURE", ctl.journal.seq)
    assert (
        ctl.spacing == 50_000_000 and ctl.next_start_ns >= slot.started_ns + 50_000_000
    )
    assert ctl.next_emit_ns >= ctl.last_emit_end_ns + 50_000_000
    with pytest.raises(c.Stage12Error):
        ctl.downshift(2, "RESOURCE_PRESSURE", ctl.journal.seq)
    assert ctl.state_id == 1
    ctl.writer.abort()


@pytest.mark.parametrize("slow_ms,stops", [(30_000, False), (30_001, True)])
def test_T08_latency_window_uses_strict_predicate_and_all_twenty(
    tmp_path, slow_ms, stops
):
    ctl, rows = controller(tmp_path, count=20)
    for index, row in enumerate(rows):
        slot = start_slot(ctl, row)
        ctl.emit(slot, lambda: None, lambda: None)
        complete_slot(
            ctl,
            slot,
            replace(capture(body([])), elapsed_ms=slow_ms if index < 10 else 1),
        )
        finalize_slot(ctl, slot)
        if index < 19:
            assert ctl.stop_reason is None
    assert (ctl.stop_reason is not None) is stops
    ctl.writer.abort()


def test_T15_disk_and_event_reserve_stop_before_begin(tmp_path):
    ctl, rows = controller(tmp_path)
    ctl.free_bytes = lambda: 0
    ctl.queue(s.Pending(rows[0], b"/synthetic", 1, 0))
    called = []
    with pytest.raises(c.Stage12Error):
        ctl.admit(lambda _: called.append(1))
    assert not called and ctl.charged["DATA"] == 0
    ctl.writer.abort()


@pytest.mark.parametrize(
    "suffix",
    [
        "_begin.json",
        "_finish.json",
        ".zst",
        "_validation_begin.json",
        "_validation.json",
        "_receipt.json",
        "_SEALED",
    ],
)
def test_T07_each_new_DATA_transaction_fault_blocks_clean_recovery(
    monkeypatch, tmp_path, suffix
):
    original = io.write

    def fail(path, raw):
        if path.name == "call_0001_attempt_1" + suffix:
            raise OSError("synthetic transaction boundary failure")
        original(path, raw)

    monkeypatch.setattr(io, "write", fail)
    report, root, _ = run_offline(tmp_path, count=1)
    assert report["disposition"] == "RECOVERY_BLOCKED"
    assert not report["report_complete"] and not report["segment_snapshot_hashes"]
    assert not (root / "snapshot.json").exists()
    assert not (root / "_SEGMENT_SEALED").exists()


@pytest.mark.parametrize("status", [200, 429, 403])
def test_T03_T06_real_transport_hooks_with_fake_socket_only(monkeypatch, status):
    from email.message import Message

    clock = FakeClock()
    calls = []
    raw = body([])

    class Socket:
        def settimeout(self, timeout):
            calls.append(("timeout", timeout))

        def shutdown(self, *_):
            calls.append(("shutdown",))

    class Reply:
        length = 0

        def __init__(self):
            self.status = status
            self.headers = Message()
            self.headers["Content-Type"] = "application/json"
            self.headers["Content-Length"] = str(len(raw))
            self.headers["Retry-After"] = "31"
            self.done = False

        def getheader(self, key):
            return self.headers.get(key)

        def read1(self, maximum):
            assert status == 200
            if self.done:
                return b""
            self.done = True
            return raw

    class Connection:
        sock = Socket()

        def __init__(self, *_a):
            pass

        def connect(self):
            calls.append(("connect",))

        def putrequest(self, method, target, **kwargs):
            calls.append((method, target, kwargs))

        def putheader(self, name, value):
            calls.append((name, value))

        def endheaders(self):
            calls.append(("write",))

        def getresponse(self):
            return Reply()

        def close(self):
            calls.append(("close",))

    class Timer:
        def __init__(self, timeout, callback):
            assert timeout == 60

        def start(self):
            pass

        def cancel(self):
            pass

    class Hooks:
        def started(self, ns):
            calls.append(("started", ns))

        def emit(self, write, check):
            calls.append(("commit",))
            check()
            write()

        def signal(self, status, outcome, reason, retry):
            calls.append(("signal", status, retry))

        def completed(self, result):
            calls.append(("completed", result.status))

    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(t, "_Connection", Connection)
    monkeypatch.setattr(t.threading, "Timer", Timer)
    monkeypatch.setattr(t.time, "monotonic_ns", clock.now_ns)
    profile = t.TransportProfile(
        "https://synthetic.invalid", "127.0.0.1", bytes.fromhex(H), 8192, 16384
    )
    result = t.send(
        b"/v1/search?size=1&text=Berlin",
        profile,
        t.Secret.checked(KEY),
        v1.Operations(),
        hooks=Hooks(),
    )
    assert result.status == status
    assert (
        calls.index(("started", 0))
        < calls.index(("connect",))
        < calls.index(("commit",))
        < calls.index(("write",))
    )
    assert (
        calls.index(("signal", status, 31))
        < calls.index(("close",))
        < calls.index(("completed", status))
    )
    assert ("Accept-Encoding", b"identity") in calls
    assert result.payload == (raw if status == 200 else None)


def test_T03_expiry_after_commit_does_not_invent_write_entry(tmp_path):
    ctl, rows = controller(tmp_path)
    slot = start_slot(ctl, rows[0])
    checks, writes = [], []

    def deadline():
        checks.append(1)
        if len(checks) == 2:
            raise c.Stage12Error("TIMEOUT")

    with pytest.raises(c.Stage12Error, match="TIMEOUT"):
        ctl.emit(slot, lambda: writes.append(1), deadline)
    events = list(j.read_events(ctl.writer.root, ctl.journal.start_hash))
    assert not writes and slot.emitted_ns is None
    assert sum(e["kind"] == "EMIT_COMMITTED" for e in events) == 1
    assert not any(e["kind"] == "EMISSION" for e in events)
    assert ctl.charged["DATA"] == 1
    ctl.writer.abort()


def test_T15_event_tail_remains_writable_when_admission_stops(tmp_path):
    ctl, rows = controller(tmp_path)
    ctl.journal.event_budget = ctl.journal.seq + ctl.journal.closure_events
    ctl.tick()
    assert ctl.stop_reason == "BUDGET"
    assert not ctl.writer.failed.is_set()
    assert (
        list(j.read_events(ctl.writer.root, ctl.journal.start_hash))[-1]["kind"]
        == "STOP"
    )
    assert ctl.admit(lambda _: H) is None
    ctl.writer.abort()


@pytest.mark.parametrize("retry_first", [False, True])
def test_F06_T04_queue_one_target_backpressures_without_loss(tmp_path, retry_first):
    from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe

    p, plan, start, rows, runtime = inputs(3)
    f = probe.fixtures()[0]
    target = c.materialize(
        f["core"], bytes.fromhex(f["fixture_id"]), c.policy(1), target_limit=2**32
    )[0]
    p["resources"]["pending_request_bytes"] = len(target)
    rebind(p, plan, start)
    clock, calls = FakeClock(), []

    def dispatch(work, target, hooks):
        calls.append(work["work_id"])
        result = (
            replace(
                capture(),
                outcome="TECHNICAL_FAILURE_RETRYABLE",
                reason="TIMEOUT",
                status=None,
            )
            if retry_first and len(calls) == 1
            else None
        )
        return synthetic_dispatch(clock, result)(work, target, hooks)

    root = tmp_path / "one-target"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=dispatch,
        epoch=H,
        **repair_common(rows, runtime),
    )
    assert result["disposition"] == "COMPLETED"
    assert sorted(calls) == ([1, 1, 2, 3] if retry_first else [1, 2, 3])
    events = list(j.read_events(root, o.digest(start)))
    assert all(
        e["body"]["pending_bytes"] <= len(target) and e["body"]["pending_count"] <= 1
        for e in events
        if e["kind"] == "RESOURCE"
    )
    assert [
        (e["body"]["work_id"], e["body"]["attempt"])
        for e in events
        if e["kind"] == "BEGIN_DURABLE"
    ] == ([(1, 1), (1, 2), (2, 1), (3, 1)] if retry_first else [(1, 1), (2, 1), (3, 1)])


def test_F06_T04_single_oversize_is_distinct_and_pre_dispatch(tmp_path):
    p, plan, start, rows, runtime = inputs(1)
    p["resources"]["pending_request_bytes"] = 1
    rebind(p, plan, start)
    root = tmp_path / "oversize"
    with pytest.raises(c.Stage12Error, match="SINGLE_REQUEST_TOO_LARGE"):
        cli.run_operations_block(
            p,
            plan,
            start,
            output=root,
            clock=FakeClock(),
            dispatch=lambda *_: pytest.fail("dispatch forbidden"),
            epoch=H,
            **repair_common(rows, runtime),
        )
    assert not root.exists()


def test_F06_T04_refill_reserves_lookahead_retry_and_monitor_bytes(tmp_path):
    ctl, rows = controller(tmp_path, count=3)
    try:
        ctl.resources["pending_request_bytes"] = 40
        assert ctl.can_refill(20, monitor_reserve=20)
        ctl.queue(s.Pending(rows[0], b"x" * 20, 1, 0))
        assert not ctl.can_refill(20, monitor_reserve=20)
        first = ctl.admit(lambda _: H)
        assert first is not None
        ctl.started(first, ctl.clock.now_ns())
        assert ctl.can_refill(20)  # monitor fits; ordinary needs its reserve too
        assert not ctl.can_refill(20, monitor_reserve=20)
        ctl.queue(s.Pending(rows[1], b"x" * 20, 1, 0))
        ctl.clock.wait_until(ctl.next_start_ns)
        second = ctl.admit(lambda _: H)
        assert second is not None  # two operations remain admissible with room
        assert not ctl.can_refill(1)
    finally:
        ctl.writer.abort()


@pytest.mark.parametrize("statuses", [(500, 502), (429, 503)])
@pytest.mark.parametrize("blocked_kind", ["EARLY_SIGNAL", "COOLDOWN"])
def test_F03_T05_T08_T11_concurrent_signals_replay_in_latch_order(
    tmp_path, blocked_kind, statuses
):
    import threading
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )

    ctl, rows = controller(tmp_path, count=2)
    release, blocked, second_latched = (threading.Event() for _ in range(3))
    errors = []
    threads = []
    try:
        first, second = start_slot(ctl, rows[0]), start_slot(ctl, rows[1])
        ctl.emit(first, lambda: None, lambda: None)
        ctl.emit(second, lambda: None, lambda: None)
        original, wake = ctl.journal.event, ctl.wake.set

        def capture_latch():
            if second.key in ctl.signalled:
                second_latched.set()
            wake()

        ctl.wake.set = capture_latch

        def delayed(kind, value, **kw):
            identity = value.get("work_id", value.get("trigger_work_id"))
            if kind == blocked_kind and identity == 1:
                blocked.set()
                assert release.wait(3)
            return original(kind, value, **kw)

        ctl.journal.event = delayed

        def signal(slot, status):
            try:
                ctl.signal(
                    slot,
                    status,
                    "TECHNICAL_FAILURE_RETRYABLE",
                    "SERVER_TRANSIENT",
                    None,
                )
            except BaseException as exc:
                errors.append(exc)

        threads.append(threading.Thread(target=signal, args=(first, statuses[0])))
        threads[0].start()
        assert blocked.wait(2)
        old_until = ctl.cooldown_until
        ctl.clock.advance(1_000_000_000)
        threads.append(threading.Thread(target=signal, args=(second, statuses[1])))
        threads[1].start()
        assert second_latched.wait(2)  # disk is blocked, safety update is immediate
        assert ctl.safety.acquire(timeout=1)
        try:
            assert ctl.cooldown_until == old_until + 1_000_000_000
            assert ctl.safety_barriers == 2
            assert ctl.stop_reason == ("BREAKER" if statuses[0] == 429 else None)
        finally:
            ctl.safety.release()
        release.set()
        for thread in threads:
            thread.join(3)
            assert not thread.is_alive()
        assert not errors
        events = list(j.read_events(ctl.writer.root, ctl.journal.start_hash))
        pairs = [e for e in events if e["kind"] in ("EARLY_SIGNAL", "COOLDOWN")]
        assert [e["kind"] for e in pairs] == ["EARLY_SIGNAL", "COOLDOWN"] * 2
        assert [
            e["body"]["until_mono_ns"] for e in pairs if e["kind"] == "COOLDOWN"
        ] == [old_until, old_until + 1_000_000_000]
        replayed = recovery.replay(events)
        assert replayed["cooldown_delay_ms"] == 30_000
        assert ctl.stop_reason == ("BREAKER" if statuses[0] == 429 else None)
        assert ctl.safety_barriers == 0
    finally:
        release.set()
        for thread in threads:
            thread.join(3)
        ctl.writer.abort()


def test_F06_T04_T09_byte_backpressure_preserves_monitor_headroom(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
    from test_stage12_public_operational_audit import Control

    p, plan, start, rows, runtime = inputs(2, monitored=True)
    f = probe.fixtures()[0]
    data_size = len(
        c.materialize(
            f["core"], bytes.fromhex(f["fixture_id"]), c.policy(1), target_limit=2**32
        )[0]
    )
    p["resources"]["pending_request_bytes"] = data_size + len(Control().target(None))
    rebind(p, plan, start)
    clock, calls = FakeClock(), []

    def dispatch(work, target, hooks):
        calls.append(work["work_id"])
        raw = (
            c.canonical({"synthetic_index": "test"})
            if work["kind"] == "SERVICE_CONTROL"
            else body([])
        )
        return synthetic_dispatch(clock, capture(raw))(work, target, hooks)

    common = repair_common(rows, runtime)
    common.update(
        control_adapters={1: Control(), 2: Control()}, monitor=FakeMonitor(clock)
    )
    root = tmp_path / "monitor-bytes"
    report = cli.run_operations_block(
        p, plan, start, output=root, clock=clock, dispatch=dispatch, epoch=H, **common
    )
    assert report["disposition"] == "COMPLETED"
    assert len(calls) == len(set(calls)) == 4
    events = list(j.read_events(root, o.digest(start)))
    assert [
        e["body"]["interval_closed"] for e in events if e["kind"] == "MONITOR_RESULT"
    ] == [False, True]
    assert all(
        e["body"]["pending_bytes"] <= p["resources"]["pending_request_bytes"]
        for e in events
        if e["kind"] == "RESOURCE"
    )


def f06_role_case(count=1, refresh_bytes=512, closure_bytes=23, capacity=None):
    """Invented finite work; lengths are regression oracles, never live values."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
    from test_stage12_public_operational_audit import Control

    p, plan, start, rows, runtime = inputs(count, monitored=True)
    fixture = probe.fixtures()[0]
    data_bytes = len(
        c.materialize(
            fixture["core"],
            bytes.fromhex(fixture["fixture_id"]),
            c.policy(1),
            target_limit=2**32,
        )[0]
    )

    class SizedControl(Control):
        def __init__(self, size):
            self.size = size

        def target(self, recipe):
            return b"/" + b"m" * (self.size - 1)

    cap = (
        max((data_bytes if count else 0) + refresh_bytes, closure_bytes)
        if capacity is None
        else capacity
    )
    p["resources"]["pending_request_bytes"] = cap
    rebind(p, plan, start, rows)
    clock = FakeClock()
    common = repair_common(rows, runtime)
    common.update(
        control_adapters={
            1: SizedControl(refresh_bytes),
            2: SizedControl(closure_bytes),
        },
        monitor=FakeMonitor(clock),
    )
    return p, plan, start, rows, runtime, clock, common, data_bytes


def f06_role_dispatch(clock, calls, retry_first_data=False):
    def dispatch(work, target, hooks):
        previous = [w for w, _ in calls]
        calls.append((work["work_id"], len(target)))
        if work["kind"] == "SERVICE_CONTROL":
            result = capture(c.canonical({"synthetic_index": "test"}))
        elif retry_first_data and work["work_id"] == 1 and 1 not in previous:
            result = replace(
                capture(),
                outcome="TECHNICAL_FAILURE_RETRYABLE",
                reason="TIMEOUT",
                status=None,
            )
        else:
            result = capture(body([]))
        return synthetic_dispatch(clock, result)(work, target, hooks)

    return dispatch


@pytest.mark.parametrize("refresh_bytes", [512, 206, 23])
@pytest.mark.parametrize("closure_bytes", [23, 718, 1024])
def test_F06_final_role_bounds_fit_exact_coexistence(
    tmp_path, refresh_bytes, closure_bytes
):
    p, plan, start, rows, _, clock, common, data_bytes = f06_role_case(
        refresh_bytes=refresh_bytes, closure_bytes=closure_bytes
    )
    assert data_bytes == 206
    if refresh_bytes == 512 and closure_bytes == 23:
        assert p["resources"]["pending_request_bytes"] == 718
    calls, root = [], tmp_path / "roles"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=f06_role_dispatch(clock, calls),
        epoch=H,
        **common,
    )
    assert report["disposition"] == "COMPLETED"
    assert calls == [(2, refresh_bytes), (1, data_bytes), (3, closure_bytes)]
    events = list(j.read_events(root, o.digest(start)))
    resources = [e["body"] for e in events if e["kind"] == "RESOURCE"]
    assert all(
        e["pending_bytes"] <= p["resources"]["pending_request_bytes"]
        and e["pending_count"] <= 4
        for e in resources
    )
    assert all(
        row["state"] == "DURABLE_SUCCESS"
        for row in j.read_array(root / "work_ledger.json")
    )
    assert report["campaign_counts"]["begins_charged"]["value"] == 3


def test_F06_final_tight_monitored_retry_preserves_every_ordinal(tmp_path):
    p, plan, start, rows, _, clock, common, _ = f06_role_case(count=2)
    calls, root = [], tmp_path / "retry"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=f06_role_dispatch(clock, calls, True),
        epoch=H,
        **common,
    )
    assert p["resources"]["pending_request_bytes"] == 718
    assert report["disposition"] == "COMPLETED"
    assert calls == [(3, 512), (1, 206), (1, 206), (2, 206), (4, 23)]
    begins = [
        (e["body"]["work_id"], e["body"]["attempt"])
        for e in j.read_events(root, o.digest(start))
        if e["kind"] == "BEGIN_DURABLE"
    ]
    assert begins == [(3, 1), (1, 1), (1, 2), (2, 1), (4, 1)]


@pytest.mark.parametrize(
    "refresh_bytes,closure_bytes,capacity,error",
    [
        (512, 23, 717, "MONITOR_QUEUE_HEADROOM_REQUIRED"),
        (512, 23, 511, "SINGLE_REQUEST_TOO_LARGE"),
        (23, 800, 799, "SINGLE_REQUEST_TOO_LARGE"),
        (23, 23, 205, "SINGLE_REQUEST_TOO_LARGE"),
    ],
)
def test_F06_final_impossible_capacity_rejects_without_dispatch(
    tmp_path, refresh_bytes, closure_bytes, capacity, error
):
    p, plan, start, _, _, clock, common, _ = f06_role_case(
        refresh_bytes=refresh_bytes, closure_bytes=closure_bytes, capacity=capacity
    )
    root = tmp_path / "rejected"
    with pytest.raises(c.Stage12Error, match=error):
        cli.run_operations_block(
            p,
            plan,
            start,
            output=root,
            clock=clock,
            dispatch=lambda *_: pytest.fail("dispatch forbidden"),
            epoch=H,
            **common,
        )
    assert not root.exists()


def test_F06_final_monitor_only_has_no_ordinary_byte_reservation(tmp_path):
    p, plan, start, _, _, clock, common, _ = f06_role_case(count=0)
    assert p["resources"]["pending_request_bytes"] == 512
    calls = []
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=tmp_path / "monitor-only",
        clock=clock,
        dispatch=f06_role_dispatch(clock, calls),
        epoch=H,
        **common,
    )
    assert report["disposition"] == "COMPLETED"
    assert calls == [(1, 512), (2, 23)]


@pytest.mark.parametrize("retry_first", [False, True])
def test_F06_final_large_closure_releases_only_request_caches_and_resumes(
    tmp_path, retry_first
):
    p, plan, start, rows, runtime, clock, common, _ = f06_role_case(
        count=3, refresh_bytes=23, closure_bytes=1024, capacity=1024
    )
    # Declare a fresh refresh and closure for the second segment in advance.
    for old_id, new_id in ((4, 6), (5, 7)):
        rows.append({**rows[old_id - 1], "work_id": new_id})
    plan["blocks"][0]["reserved_control_ids"].append(6)
    plan["blocks"][0]["observation_ids"].append(7)
    for budget in (plan["budgets"], plan["blocks"][0]["budget"]):
        budget.update(
            required_control_observations=2,
            reserved_control_observations=2,
            control_http_attempts=4,
        )
    rebind(p, plan, start, rows)
    calls, first = [], tmp_path / "paused"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=first,
        clock=clock,
        dispatch=f06_role_dispatch(clock, calls, retry_first),
        epoch=H,
        pause_requested=lambda: any(w == 1 for w, _ in calls),
        **common,
    )
    assert report["disposition"] == "PAUSED_CLEAN"
    assert calls == [(4, 23), (1, 206), (5, 1024)]
    ledger = list(j.read_array(first / "work_ledger.json"))
    assert ledger[0]["state"] == ("RETRY_DUE" if retry_first else "DURABLE_SUCCESS")
    assert ledger[1]["state"] == ledger[2]["state"] == "UNBEGUN"
    assert ledger[1]["charged_ordinals"] == ledger[2]["charged_ordinals"] == []
    resources = [
        e["body"]
        for e in j.read_events(first, o.digest(start))
        if e["kind"] == "RESOURCE"
    ]
    assert any(e["pending_count"] >= 2 for e in resources)
    assert all(e["pending_bytes"] <= 1024 for e in resources)
    assert any(
        e["cause"] == "STATE_CHANGE" and e["pending_bytes"] == 0 for e in resources
    )
    before = {
        str(path.relative_to(first)): c.sha(io.read(path)).hex()
        for path in first.rglob("*")
        if path.is_file()
    }
    clock2, second_calls = FakeClock(wall_offset_ns=1_000_000_000), []
    common["monitor"] = FakeMonitor(clock2)
    final = cli.run_operations_block(
        p,
        plan,
        start,
        output=tmp_path / "resumed",
        clock=clock2,
        dispatch=f06_role_dispatch(clock2, second_calls),
        epoch="2" * 64,
        predecessor=first,
        continuation_authority=H,
        **common,
    )
    assert final["disposition"] == "COMPLETED"
    assert [w for w, _ in second_calls] == (
        [6, 2, 3, 1, 7] if retry_first else [6, 2, 3, 7]
    )
    assert final["campaign_counts"]["durable_valid_data"]["value"] == 3
    assert final["campaign_counts"]["begins_charged"]["value"] == (
        8 if retry_first else 7
    )
    assert before == {
        str(path.relative_to(first)): c.sha(io.read(path)).hex()
        for path in first.rglob("*")
        if path.is_file()
    }


def test_F06_final_closure_releases_actual_pending_and_slot_targets(
    tmp_path, monkeypatch
):
    import gc
    import weakref
    from test_stage12_public_operational_audit import Control

    p, plan, start, rows, runtime, clock, common, _ = f06_role_case(
        count=3, refresh_bytes=23, closure_bytes=1024, capacity=1024
    )
    refs, observations, calls = [], [], []
    original_queue, original_admit = s.Coordinator.queue, s.Coordinator.admit

    def queue(self, pending):
        if pending.work["kind"] == "DATA":
            refs.append(weakref.ref(pending))
        return original_queue(self, pending)

    def admit(self, begin):
        slot = original_admit(self, begin)
        if slot is not None and slot.pending.work["kind"] == "DATA":
            refs.append(weakref.ref(slot))
        return slot

    class Closure(Control):
        def target(self, recipe):
            raw = b"/" + b"c" * 1023
            if refs:
                gc.collect()
                # Only weak references are retained by this observer. A count
                # reset alone cannot make a still-owned request cache disappear.
                live = [type(ref()).__name__ for ref in refs if ref() is not None]
                observations.append((live, len(raw)))
            return raw

    monkeypatch.setattr(s.Coordinator, "queue", queue)
    monkeypatch.setattr(s.Coordinator, "admit", admit)
    common["control_adapters"][2] = Closure()
    root = tmp_path / "actual-cache-lifetime"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=f06_role_dispatch(clock, calls, True),
        epoch=H,
        pause_requested=lambda: any(w == 1 for w, _ in calls),
        **common,
    )
    assert result["disposition"] == "PAUSED_CLEAN"
    assert observations == [([], 1024)]
    ledger = list(j.read_array(root / "work_ledger.json"))
    assert ledger[0]["state"] == "RETRY_DUE" and ledger[0]["charged_ordinals"] == [1]
    assert ledger[1]["state"] == ledger[2]["state"] == "UNBEGUN"


def sampling_controller(tmp_path, free_bytes, *, writer_guard_ms=1000):
    p, plan, start, _, _ = inputs(1)
    p["resources"]["writer_guard_ms"] = writer_guard_ms
    rebind(p, plan, start)
    clock = FakeClock()
    ctl = s.Coordinator(
        p,
        plan,
        start,
        authority=FakeAuthority(),
        clock=clock,
        root=tmp_path / "sample",
        block_id=1,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        free_bytes=free_bytes,
    )
    return ctl, clock, start


@pytest.mark.parametrize("wait_kind", ["retry", "cooldown"])
def test_T14_sampling_deadline_precedes_retry_and_cooldown_waits(tmp_path, wait_kind):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    if wait_kind == "cooldown":
        ctl.state, ctl.cooldown_until = "COOLDOWN", 30_000_000_000
    try:
        for _ in range(3):
            deadline = ctl.next_wakeup_ns(30_000_000_000)
            assert deadline - clock.now_ns() == 50_000_000
            clock.wait_until(deadline)
            ctl.tick()
            assert ctl.last_sample_ns == clock.now_ns()
        periodic = [
            e
            for e in j.read_events(ctl.writer.root, o.digest(start))
            if e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
        ]
        assert [e["body"]["observed_mono_ns"] for e in periodic] == [
            50_000_000,
            100_000_000,
            150_000_000,
        ]
        assert ctl.stop_reason is None
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()


@pytest.mark.parametrize("writer_delay_ns", [80_000_000, 200_000_000])
def test_T05_T14_sampler_one_slot_observes_during_writer_transaction(
    monkeypatch, tmp_path, writer_delay_ns
):
    import threading

    observed, occupied, release = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    calls = []

    def free():
        calls.append(1)
        return 2**42

    ctl, clock, start = sampling_controller(tmp_path, free)
    original_event = ctl.journal.event

    def record(kind, body, **kwargs):
        if kind == "RESOURCE" and body["cause"] == "PERIODIC":
            observed.set()  # The actual counter/time snapshot already exists.
        return original_event(kind, body, **kwargs)

    monkeypatch.setattr(ctl.journal, "event", record)

    def slow():
        occupied.set()
        assert release.wait(2)

    future = ctl.writer.submit(slow)
    assert occupied.wait(1)
    ctl.start_sampling()
    try:
        clock.advance(50_000_000)
        assert observed.wait(1)
        # One sample is retained while the sole writer remains busy. A second
        # collection neither overwrites it nor allocates an unbounded queue.
        assert ctl.sample_slot.locked()
        with ctl.safety:
            assert ctl.safety_barriers == 0  # observation is not a hard mutation
        clock.advance(writer_delay_ns)
        ctl.sample_if_due()
        assert len(calls) == 1
        release.set()
        future.result(timeout=1)
        assert ctl.stop_sampling()
        ctl.resource("PERIODIC")
        periodic = [
            e
            for e in j.read_events(ctl.writer.root, o.digest(start))
            if e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
        ]
        times = [e["body"]["observed_mono_ns"] for e in periodic]
        assert times[0] == 50_000_000
        assert times[-1] == 50_000_000 + writer_delay_ns
        assert any(b - a > 100_000_000 for a, b in zip(times, times[1:])) is (
            writer_delay_ns > 100_000_000
        )
        assert periodic[0]["mono_ns"] >= times[0] + writer_delay_ns
        assert not ctl.sample_thread.is_alive()
    finally:
        release.set()
        ctl.stop_sampling()
        ctl.writer.abort()


def test_T14_slow_storage_observation_cancels_before_enqueue_on_shutdown(tmp_path):
    import threading

    entered, release = threading.Event(), threading.Event()

    def free():
        entered.set()
        assert release.wait(2)
        return 2**42

    ctl, clock, start = sampling_controller(tmp_path, free, writer_guard_ms=20)
    ctl.start_sampling()
    try:
        clock.advance(50_000_000)
        assert entered.wait(1)
        # The safety latch is free even while filesystem observation is stuck.
        assert ctl.safety.acquire(timeout=0.05)
        ctl.safety.release()
        clock.advance(200_000_000)
        assert not ctl.stop_sampling()
        assert ctl.state == "RECOVERY_BLOCKED" and ctl.writer.failed.is_set()
        release.set()
        ctl.sample_thread.join(1)
        assert not ctl.sample_thread.is_alive()
        assert not any(
            e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
            for e in j.read_events(ctl.writer.root, o.digest(start))
        )
        assert not (ctl.writer.root / "_SEGMENT_SEALED").exists()
    finally:
        release.set()
        ctl.stop_sampling()
        ctl.writer.abort()


def test_T14_sampler_event_budget_preserves_closure_tail(tmp_path):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    try:
        # Fault/boundary injection at the exact remaining-event frontier.
        ctl.journal.event_budget = ctl.journal.seq + 2 * ctl.journal.closure_events
        before = ctl.journal.seq
        clock.advance(50_000_000)
        ctl.sample_if_due()
        assert ctl.stop_reason == "BUDGET"
        assert ctl.journal.seq == before + 1  # STOP, no unbudgeted periodic event
        assert ctl.journal.normal_event_headroom() >= ctl.journal.closure_events - 1
        assert ctl.stop_sampling()
        ctl.resource("PERIODIC")
        assert ctl.journal.seq < ctl.journal.event_budget
        assert not ctl.writer.failed.is_set()
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()


def test_T07_T14_sampler_write_failure_closes_admission(monkeypatch, tmp_path):
    import threading

    failed = threading.Event()
    ctl, clock, _ = sampling_controller(tmp_path, lambda: 2**42)
    original = ctl.journal.event

    def event(kind, body, **kwargs):
        if kind == "RESOURCE" and body["cause"] == "PERIODIC":
            failed.set()
            raise OSError("SYNTHETIC_SAMPLE_WRITE_FAILURE")
        return original(kind, body, **kwargs)

    monkeypatch.setattr(ctl.journal, "event", event)
    ctl.start_sampling()
    try:
        clock.advance(50_000_000)
        assert failed.wait(1)
        ctl.sample_thread.join(1)
        assert not ctl.stop_sampling()
        assert ctl.state == "RECOVERY_BLOCKED" and ctl.writer.failed.is_set()
        assert not ctl.sample_thread.is_alive()
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()


def test_T14_sampler_is_joined_before_final_prefix_and_writer_release(
    monkeypatch, tmp_path
):
    instances = []
    original = s.Coordinator.start_sampling

    def start(ctl):
        instances.append(ctl)
        return original(ctl)

    monkeypatch.setattr(s.Coordinator, "start_sampling", start)
    campaign, root, (_, _, begin, _, _) = run_offline(tmp_path)
    assert len(instances) == 1
    assert (
        instances[0].sample_stop.is_set() and not instances[0].sample_thread.is_alive()
    )
    events = list(j.read_events(root, o.digest(begin)))
    end = campaign["blocks"][0]["input_last_event_seq"]
    assert events[end - 1]["body"]["cause"] == "PERIODIC"
    assert events[end]["kind"] == "BLOCK_CLOSED"
    assert not any(e["kind"] == "RESOURCE" for e in events[end:])
    assert (
        max(e["mono_ns"] for e in events[:end] if e["kind"] == "AUDIT_TIMING")
        <= events[end - 1]["body"]["observed_mono_ns"]
    )


def test_1804093_audit_safe_points_drain_only_one_periodic_slot(monkeypatch, tmp_path):
    import threading

    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    io.write(ctl.writer.root / "synthetic", b"synthetic")
    entered, release, queued, checkpoint, done = [threading.Event() for _ in range(5)]
    original_submit = ctl.writer.submit

    def submit(action, *, periodic=False):
        future = original_submit(action, periodic=periodic)
        if periodic:
            queued.set()
        return future

    monkeypatch.setattr(ctl.writer, "submit", submit)
    ordinary = []

    def audit_transaction():
        entered.set()
        for _ in range(3):
            assert checkpoint.wait(1)
            checkpoint.clear()
            # A completed read is a safe point; the caller holds no safety mutex.
            assert ctl.safety.acquire(blocking=False)
            ctl.safety.release()
            io.read(ctl.writer.root / "synthetic")
            done.set()
        assert release.wait(1)

    result = []
    thread = threading.Thread(
        target=lambda: result.append(ctl.writer.cooperative(audit_transaction))
    )
    thread.start()
    assert entered.wait(1)
    ordinary_future = ctl.writer.submit(lambda: ordinary.append(threading.get_ident()))
    try:
        for n in range(1, 4):
            clock.advance(50_000_000)
            queued.clear()
            sample = threading.Thread(target=ctl.sample_if_due)
            sample.start()
            assert queued.wait(1)
            assert ctl.sample_slot.locked()
            done.clear()
            checkpoint.set()
            assert done.wait(1)
            sample.join(1)
            assert not sample.is_alive()
            assert ctl.last_sample_ns == n * 50_000_000
            assert ordinary == []  # Never reenter another audit/mutation.
        release.set()
        thread.join(1)
        ordinary_future.result(1)
        assert result == [None] and ordinary == [ctl.writer.thread.ident]
        assert ctl.stop_sampling()
        ctl.resource("PERIODIC")
        events = list(j.read_events(ctl.writer.root, o.digest(start)))
        times = [
            e["body"]["observed_mono_ns"]
            for e in events
            if e["kind"] == "RESOURCE" and e["body"]["cause"] == "PERIODIC"
        ]
        assert times == [50_000_000, 100_000_000, 150_000_000, 150_000_000]
        assert not ctl.writer.failed.is_set()
    finally:
        release.set()
        checkpoint.set()
        thread.join(2)
        ctl.stop_sampling()
        ctl.writer.abort()


def test_1804093_terminal_drain_still_samples_and_preserves_primary(tmp_path):
    ctl, clock, start = sampling_controller(tmp_path, lambda: 2**42)
    try:
        ctl.terminal("TERMINAL", "TERMINAL_FAILURE")
        clock.advance(50_000_000)
        ctl.sample_if_due()
        assert ctl.last_sample_ns == clock.now_ns()
        ctl.audit_failed()
        assert ctl.state == "RECOVERY_BLOCKED"
        assert ctl.stop_reason == "TERMINAL"
        assert ctl.primary_reason == "TERMINAL_FAILURE"
        events = list(j.read_events(ctl.writer.root, o.digest(start)))
        assert events[-1]["kind"] == "RESOURCE"
        assert (
            next(e["body"] for e in events if e["kind"] == "STOP")["primary_reason"]
            == "TERMINAL_FAILURE"
        )
    finally:
        ctl.stop_sampling()
        ctl.writer.abort()

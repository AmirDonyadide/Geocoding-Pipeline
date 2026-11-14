"""Selected AP coverage is separate from complete workload evidence.

All clocks, authorities, resource/kernel facts and transport responses here are
explicit TEST_ONLY fixtures. No provider request or native qualification runs.
"""
from copy import deepcopy
import threading
from types import SimpleNamespace

import pytest
from test_stage12_public_operations_v2 import FakeClock, H, KEY, offline  # noqa:F401
from test_stage12_public_sampling import component
from test_stage12_public_sampling_integration import RealClock
from test_stage12_rep_fair_service import selected_inputs as fair_inputs
from test_stage12_ra_g1_integration import SyntheticAuthority, ra_inputs
from test_s12_ra_g1_core import capacity
from stage12_synthetic import body, feature
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_coverage_contract as wire
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract as strict
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as checkpoints
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as compact
from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation


def selected_inputs(clock):
    p, plan, start, previous = fair_inputs(clock)
    selected, record = deepcopy(previous.selected), deepcopy(previous.record)
    selected.update(schema_version=assurance.REP_COVERAGE_SELECTION,
                    rep_coverage_policy_sha256=wire.POLICY_SHA,
                    rep_coverage_policy_adoption_sha256=H)
    selected.pop("rep_fair_policy_sha256")
    selected.pop("rep_fair_policy_adoption_sha256")
    assurance.validate_selection(selected)
    record["selection_sha256"] = wire.digest(selected)
    p["resources"].update(resource_selection_sha256=wire.digest(selected),
        initial_capacity_observation_sha256=wire.digest(capacity(selected)))
    p.update(schema_version=wire.PROFILE, rule_bundle_sha256=wire.RULE_BUNDLE,
        sampling_policy_sha256=wire.POLICY_SHA, sampling_runtime_bound_sha256=wire.digest(record))
    plan.update(schema_version=wire.PLAN, operations_profile_sha256=wire.digest(p))
    start.update(schema_version=wire.START, profile_sha256=wire.digest(p),
        plan_sha256=wire.digest(plan), rule_bundle_sha256=wire.RULE_BUNDLE,
        sampling_policy_sha256=wire.POLICY_SHA)
    authority = SyntheticAuthority(p, plan, start, record, selected, previous.rows, clock)
    authority.diagnostic_scope = "REPRESENTATIVE_NO_SERVICE"
    authority.service_authority = False
    # TEST_ONLY current-resource ACK endpoint for the small programmatic
    # campaign; the actual production adapter/monitor are tested separately.
    def resource_current(**kwargs):
        c.require(authority.reject != "resource_current", "SYNTHETIC_RESOURCE_DENIED")
        c.require(kwargs["next_write_bytes"] > 0 and kwargs["next_creations"] == 1)
    authority.resource_current = resource_current
    return p, plan, start, authority


def coverage_component():
    _, co, log, clock = component()
    co.contract = wire
    ap = sampling.Sampler(co)
    ap.anchor = ap.last_observed = 0
    ap.owner_ident = threading.get_ident()
    ap.head = ap.association = H
    return ap, co, log, clock


@pytest.mark.parametrize("gap", [100_000_000, 100_000_001, 200_000_000])
def test_positive_health_gap_retains_operands_and_continues_actual_acquisition(gap):
    ap, co, _, clock = coverage_component()
    clock.value = gap
    ap.health(caller_context="OWNER")
    ap.health(caller_context="SERVICE")
    assert ap.failure is None and co.stop_reason is None
    assert ap.health_gap_count == int(gap > 100_000_000)
    assert ap.maximum_health_age == gap
    if gap > 100_000_000:
        assert ap.first_fault["predicate_origin"] == "HEALTH_FRESHNESS"
        assert ap.first_fault["health_time_mono_ns"] == gap
        assert ap.first_fault["previous_observed_mono_ns"] == 0
    assert ap.acquire() is True
    assert ap.acquired == 1 and ap.last_observed == gap
    assert ap.gaps == int(gap > 100_000_000) and ap.failure is None
    clock.value += 50_000_000
    ap.health(caller_context="OWNER")
    assert ap.acquire() is True and ap.acquired == 2
    assert ap.health_gap_count == int(gap > 100_000_000)


@pytest.mark.parametrize("fault,expected", [
    ("reverse_health", "CLOCK_INVALID"), ("reverse_acquire", "ACQUISITION_GAP"),
    ("uncertain", "WRITE_UNCERTAIN"), ("exhausted", "OBSERVATION_COUNT_LIMIT"),
    ("action", "WRITE_UNCERTAIN"), ("close", "DRAIN_EXPIRED"),
])
def test_positive_coverage_policy_keeps_real_fatal_guards(fault, expected):
    ap, co, _, clock = coverage_component()
    if fault == "reverse_health":
        ap.last_observed = 1
        ap.health(caller_context="OWNER")
    elif fault == "reverse_acquire":
        ap.last_observed = 1
        ap.acquire()
    elif fault == "uncertain":
        co.writer.failed.set()
        ap.health()
    elif fault == "exhausted":
        for i in range(16):
            assert ap._reserve() == (i, i + 1)
            ap.owner_busy = False
            ap.states[i] = 2
        assert ap._reserve() is None
        assert ap.occupied == 16
    else:
        clock.value = 5_000_000_000
        ap.last_observed = clock.value
        if fault == "action":
            co.writer.ap_active_started = 0
        else:
            ap.close_requested = 0
        ap.health()
    assert ap.failure == expected and co.stop_reason is not None


def test_legacy_positive_gap_stays_fail_closed_and_flag_cannot_select_successor():
    ap, co, _, clock = component()
    clock.value = 100_000_001
    ap.health()
    assert ap.failure == "ACQUISITION_GAP" and co.stop_reason is not None
    assert sampling.positive_coverage_only(wire) is True
    assert sampling.positive_coverage_only(strict) is False
    forged = SimpleNamespace(AP_COVERAGE_ONLY=True, POLICY=wire.POLICY)
    assert sampling.positive_coverage_only(forged) is False


def test_concurrent_health_retains_one_episode_and_later_poison_stops():
    ap, co, _, clock = coverage_component()
    clock.value = 200_000_000
    gate = threading.Barrier(3)
    def check():
        gate.wait()
        ap.health(caller_context="SERVICE")
    threads = [threading.Thread(target=check) for _ in range(2)]
    for thread in threads:
        thread.start()
    gate.wait()
    for thread in threads:
        thread.join(1)
        assert not thread.is_alive()
    first = dict(ap.first_fault)
    assert ap.health_gap_count == 1 and ap.failure is None
    co.writer.failed.set()
    ap.health(caller_context="SERVICE")
    assert ap.failure == "WRITE_UNCERTAIN" and ap.first_fault == first
    assert co.stop_reason == "AUDIT_IO"


class OffsetClock(RealClock):
    """One explicit monotone TEST_ONLY positive gap, no timestamp reset."""
    def __init__(self):
        super().__init__()
        self.offset = 0
        self.lock = threading.RLock()

    def now_ns(self):
        with self.lock:
            return super().now_ns() + self.offset

    def add_gap(self):
        with self.lock:
            self.offset += 200_000_000


@pytest.mark.parametrize("positive_gap", [False, True], ids=["gap_free", "coverage_failure"])
def test_actual_cli_workload_report_snapshot_release_and_reopening(offline, tmp_path, monkeypatch, request, positive_gap):
    clock = OffsetClock()
    p, plan, start, authority = selected_inputs(clock)
    calls, direct = [], []
    original_require = authority.require
    original_barrier = authority.resource_prewrite
    def require(purpose, digest, context):
        if purpose == "dispatch":
            direct.append(("AUTHORITY", context["work"]["work_id"]))
        return original_require(purpose, digest, context)
    def barrier(**kwargs):
        direct.append(("RESOURCE_ACK", kwargs["next_creations"]))
        return original_barrier(**kwargs)
    authority.require = require
    authority.resource_prewrite = barrier
    owner = sampling.Sampler._owner
    def selected_owner(ap):
        if positive_gap:
            clock.add_gap()
        return owner(ap)
    monkeypatch.setattr(sampling.Sampler, "_owner", selected_owner)
    def invented_dispatch(work, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        calls.append(work["work_id"])
        raw = body([feature()])
        capture = transport.Capture("VALIDATION_REQUIRED", "OK", 200,
            "application/json", "identity", None, raw, len(raw), 1)
        hooks.completed(capture)
        return capture
    output = tmp_path / "phase"
    timing_binding = dict(policy_sha256=wire.POLICY_SHA, source_sha256=H, task_sha256=H)
    observer = timing.SamplingTiming(tmp_path / "timing", phase_count=1,
        timing_schema=checkpoints.RA_SCHEMA, timing_policy_version=wire.POLICY_VERSION,
        timing_binding=timing_binding, max_files=2980,
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=clock.now_ns()+180*10**9, clock_ns=clock.now_ns)
    def cleanup_observer():
        if not observer.closed:
            observer.close(timeout_seconds=2)
    request.addfinalizer(cleanup_observer)
    observer.phase_open(1, phase_deadline_ns=clock.now_ns()+20*10**9, timeout_seconds=2)
    report = cli.run_operations_block(p, plan, start,
        work_factory=lambda: iter(authority.rows), output=output, block_id=1,
        authority=authority, clock=clock, dispatch=invented_dispatch,
        runtime_inventory=ra_inputs()[-1], runtime_key=KEY, control_adapters={},
        monitor=None, free_bytes=lambda: 2**40, segment_authority=H,
        writer_exclusion_evidence=H, epoch="1"*64, writer_release_evidence=H,
        public_validation=Validation(), timing_observer=observer,
        task_deadline_ns=clock.now_ns()+180*10**9)
    assert calls == [1, 2]
    assert report["report_complete"] and report["workload_evidence_complete"]
    assert report["ap_coverage_complete"] is (not positive_gap)
    summaries = report["sampling_segments"]
    assert all(row["workload_complete"] for row in summaries)
    assert all(row["ap_coverage_complete"] for row in summaries) is (not positive_gap)
    assert all(row["complete"] for row in summaries) is (not positive_gap)
    if positive_gap:
        assert summaries[0]["gap_count"]["value"] >= 1
        assert summaries[0]["health_gap_count"]["value"] >= 1
        assert summaries[0]["maximum_gap_ns"] > 100_000_000
        assert summaries[0]["failure"] is None
    assert sum(kind == "AUTHORITY" for kind, _ in direct) == 6
    assert sum(kind == "RESOURCE_ACK" for kind, _ in direct) == 6
    assert (output / "_WRITER_RELEASED.json").is_file()
    assert runtime.reopen_completed(output, p, plan, start,
        validation_sha256=wire.digest(Validation().descriptor())) == report["blocks"][0]
    events = list(journal.read_events(output, wire.digest(start), contract=wire))
    fresh = sampling.inspect(lambda: iter(events), p, start, maximum_segments=1, contract=wire)
    assert fresh == summaries
    observer.phase_close(1, quiescent=True, timeout_seconds=2)
    timing_result = observer.close(timeout_seconds=2)
    assert timing_result["persistence_complete"] and timing_result["final_timing_coverage_complete"]
    by_seq = {event["seq"]: event for event in events}
    counts = {"HARD_SYNC": 0, "PERIODIC_ASYNC": 0}
    def association(_ordinal, row):
        hard = row["row_kind"] == "HARD_SYNC"
        seq = row["legacy_row"][4] if hard else row["sample_event_seq"]
        event = by_seq[seq]
        ack = None if hard else by_seq[row["ack_event_seq"]]
        timing.verify_sampling_association(row, event, phase_id=1, ack_event=ack, contract=wire)
        counts[row["row_kind"]] += 1
    prefix = compact.read_prefix(tmp_path / "timing", max_files=2980,
        timing_schema=checkpoints.RA_SCHEMA, expected_binding=timing_binding,
        expected_snapshot=timing_result["checkpoint"], record_consumer=association)
    assert not prefix["incomplete"] and prefix["last_payload"]["terminal_status"] == "FINAL_COMPLETE"
    assert counts["HARD_SYNC"] == 2
    assert counts["PERIODIC_ASYNC"] == summaries[0]["acquired"]["value"]
    assert prefix["sampling_coverage_proof"] is False
    if positive_gap:
        inconsistent = deepcopy(events)
        close = next(e for e in inconsistent if e["kind"] == "SAMPLING_CLOSE")
        close["body"]["health_gap_count"] = summaries[0]["acquired"]["value"] + 2
        # Preserve exact event-chain syntax to reach the substantive new
        # episode bound, rather than fail merely on a stale digest fixture.
        previous = None
        for event in inconsistent:
            event["previous_event_sha256"] = previous
            previous = wire.digest(event)
        with pytest.raises(c.Stage12Error):
            sampling.inspect(lambda: iter(inconsistent), p, start, maximum_segments=1, contract=wire)
    with pytest.raises(c.Stage12Error):
        sampling.inspect(lambda: iter(events), p, start, maximum_segments=1, contract=strict)
    # A broken original association is still rejected; policy is not evidence.
    broken = deepcopy(events)
    ack = next(e for e in broken if e["kind"] == "SAMPLE_ACK")
    ack["body"]["observation_sha256"] = H
    with pytest.raises(c.Stage12Error):
        sampling.inspect(lambda: iter(broken), p, start, maximum_segments=1, contract=wire)
    (tmp_path / "OBSERVED.record").write_bytes(c.canonical(dict(
        scope="TEST_ONLY_ACTUAL_CLI_REPORT_RELEASE_AND_REOPEN_NOT_NATIVE_QUALIFICATION",
        positive_gap_injected=positive_gap, workload_complete=True,
        ap_coverage_complete=report["ap_coverage_complete"], scenarios=0,
        selected_full_512_or_held_ACK_fixture=False, direct_gate_calls=direct,
        T3_complete=timing_result["persistence_complete"], T3_original_prefix=prefix,
        T3_actual_original_associations=counts,
        summaries=summaries)))
    (tmp_path / "OBSERVED.record").chmod(0o600)


@pytest.mark.parametrize("stage", ["START", "EMISSION"])
@pytest.mark.parametrize("reject", ["authority", "resource", "storage", "state"])
def test_actual_start_emission_direct_checks_do_not_use_stale_AP(offline, tmp_path, stage, reject):
    clock = FakeClock()
    p, plan, start, authority = selected_inputs(clock)
    co = scheduler.Coordinator(p, plan, start, authority=authority, clock=clock,
        root=tmp_path / "phase", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42, contract=wire)
    try:
        pending = scheduler.Pending(authority.rows[0], b"/TEST_ONLY", 1, clock.now_ns())
        co.queue(pending)
        slot = co.admit(lambda _: H)
        assert slot is not None
        if stage == "EMISSION":
            co.started(slot, clock.now_ns())
        # The last AP snapshot is healthy. Each changed direct fact must still
        # reject before a started/emission outcome; no callback writes occur.
        assert co.ap_sampler.failure is None
        if reject == "authority":
            authority.reject = "dispatch"
        elif reject == "resource":
            authority.reject = "resource_prewrite"
        elif reject == "storage":
            co.free_bytes = lambda: 0
        else:
            co.slots[(99, 1)] = slot
            co.slots[(100, 1)] = slot
        writes = []
        with pytest.raises(c.Stage12Error):
            if stage == "START":
                co.started(slot, clock.now_ns())
            else:
                co.emit(slot, lambda: writes.append(True), lambda: None)
        assert not writes
    finally:
        co.writer.abort()
    assert not co.writer.thread.is_alive() and not co.ap_sampler.thread.is_alive()


@pytest.mark.parametrize("reject", ["stop", "writer", "authority", "resource", "resource_current", "storage", "state", "deadline", "deadline_callback"])
def test_actual_postcommit_failures_prevent_the_write_callback(offline, tmp_path, reject):
    clock = FakeClock()
    p, plan, start, authority = selected_inputs(clock)
    co = scheduler.Coordinator(p, plan, start, authority=authority, clock=clock,
        root=tmp_path / "phase", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42, contract=wire)
    original = co.journal.event
    committed = False
    writes = []
    try:
        co.queue(scheduler.Pending(authority.rows[0], b"/TEST_ONLY", 1, clock.now_ns()))
        slot = co.admit(lambda _: H)
        co.started(slot, clock.now_ns())
        def event(kind, value, **kwargs):
            nonlocal committed
            result = original(kind, value, **kwargs)
            if kind == "EMIT_COMMITTED":
                committed = True
                if reject == "stop":
                    co.terminal("RESOURCE")
                elif reject == "writer":
                    co.writer.failed.set()
                elif reject == "authority":
                    authority.reject = "dispatch"
                elif reject == "resource":
                    authority.reject = "resource_prewrite"
                elif reject == "resource_current":
                    authority.reject = "resource_current"
                elif reject == "storage":
                    co.free_bytes = lambda: 0
                elif reject == "state":
                    co.slots[(99, 1)] = slot
                    co.slots[(100, 1)] = slot
                elif reject == "deadline":
                    clock.advance(60_000_000_000)
            return result
        co.journal.event = event
        def check():
            if committed and reject == "deadline_callback":
                co.terminal("RESOURCE")
        with pytest.raises((c.Stage12Error, transport.DispatchBlocked)):
            co.emit(slot, lambda: writes.append(True), check)
        assert committed and slot.committed_ns is not None
        assert not writes and slot.emitted_ns is None
    finally:
        co.writer.abort()
    assert not co.writer.thread.is_alive() and not co.ap_sampler.thread.is_alive()


@pytest.mark.parametrize("selected", [wire, strict], ids=["coverage_final_barrier", "legacy_early_barrier"])
def test_actual_authority_resource_barrier_order_after_capacity_IO(offline, tmp_path, monkeypatch, selected):
    """Real Authority method/capacity validator; TEST_ONLY bound/kernel facts.

    The ACK endpoint is an explicit test callback, not a fabricated native ACK.
    Actual private-root/statvfs identity/capacity reads still run in the method.
    """
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import Authority
    clock = FakeClock()
    p, plan, start, authority = selected_inputs(clock) if selected is wire else fair_inputs(clock)
    order = []
    authority._source_verified = True
    authority._deadline_check = lambda: None
    authority.active = ({"profile": p}, plan)
    authority.start = start
    authority.config = {"output_directory": str(tmp_path)}
    authority.allocation_controls = authority.controls
    bound = authority.sampling_bound
    capacity_original = authority.capacity_observation
    def read_bound(profile, campaign):
        order.append("BOUND_ORIGINAL")
        return bound(profile, campaign)
    def read_capacity(record):
        order.append("CAPACITY_ORIGINAL")
        return capacity_original(record)
    authority.sampling_bound = read_bound
    authority.capacity_observation = read_capacity
    observe = assurance.observe_capacity
    def actual_observe(*args, **kwargs):
        result = observe(*args, **kwargs)
        order.append("ACTUAL_CAPACITY_OBSERVATION")
        return result
    monkeypatch.setattr(assurance, "observe_capacity", actual_observe)
    authority.resource_monitor = SimpleNamespace(barrier=lambda **_: order.append("BARRIER_ACK_CALLBACK_TEST_ONLY"))
    Authority.resource_prewrite(authority, next_write_bytes=1, next_creations=1)
    expected = ["BOUND_ORIGINAL", "CAPACITY_ORIGINAL", "ACTUAL_CAPACITY_OBSERVATION"]
    if selected is wire:
        expected.append("BARRIER_ACK_CALLBACK_TEST_ONLY")
    else:
        expected.insert(0, "BARRIER_ACK_CALLBACK_TEST_ONLY")
    assert order == expected


def test_original_attempt_deadline_after_emission_resource_barrier(offline, tmp_path):
    clock = FakeClock()
    p, plan, start, authority = selected_inputs(clock)
    co = scheduler.Coordinator(p, plan, start, authority=authority, clock=clock,
        root=tmp_path / "phase", block_id=1, segment_authority=H,
        writer_exclusion_evidence=H, epoch=H, free_bytes=lambda: 2**42, contract=wire)
    original_event, original_barrier = co.journal.event, authority.resource_prewrite
    writes = []
    original_error = TimeoutError("TEST_ONLY_ORIGINAL_ATTEMPT_DEADLINE")
    try:
        co.queue(scheduler.Pending(authority.rows[0], b"/TEST_ONLY", 1, clock.now_ns()))
        slot = co.admit(lambda _: H)
        co.started(slot, clock.now_ns())
        original_deadline = clock.now_ns() + 500_000
        def barrier(**kwargs):
            result = original_barrier(**kwargs)
            clock.advance(1_000_000)
            return result
        def event(kind, value, **kwargs):
            result = original_event(kind, value, **kwargs)
            if kind == "EMIT_COMMITTED":
                authority.resource_prewrite = barrier
            return result
        co.journal.event = event
        def check():
            if clock.now_ns() >= original_deadline:
                raise original_error
        with pytest.raises(TimeoutError) as caught:
            co.emit(slot, lambda: writes.append(True), check)
        assert caught.value is original_error
        assert not writes and slot.emitted_ns is None
        assert clock.now_ns() - slot.started_ns < 60_000_000_000
    finally:
        co.writer.abort()


@pytest.mark.parametrize("condition,expected", [
    ("exact", None), ("late", "RA_G1_MONITOR_GAP"),
    ("negative", "RA_G1_MONITOR_GAP"), ("deadline", "RA_G1_DEADLINE"),
    ("poison", "RA_G1_WRITE_UNCERTAIN"), ("unacked", "RA_G1_WRITE_UNCERTAIN"),
    ("threshold", "RA_G1_MONITOR_THRESHOLD"), ("latched", "RA_G1_MONITOR_THRESHOLD"),
])
def test_actual_final_monitor_current_guard_is_strict_and_zero_IO(condition, expected):
    """Actual consumer; the retained START/ACK state is explicitly TEST_ONLY."""
    from test_s12_ra_g1_core import selection, observation
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as monitor
    selected = selection()
    row = observation(selected, enter=100)
    now = [100 + 1_000_000_000]
    calls = []
    writer = SimpleNamespace(poisoned=False, acked=1)
    resource = monitor.ResourceMonitor(observer=lambda _: calls.append("ACQUIRE"),
        writer=writer, selected=selected, binding_sha256=H, phase_id=1,
        seed_sha256=H, deadline_ns=now[0]+1_000_000_000,
        check=lambda: calls.append("EXTERNAL_CHECK"), clock_ns=lambda: now[0],
        scope_start_ns=100)
    resource.last = row
    if condition == "late":
        now[0] += 1
    elif condition == "negative":
        now[0] = 99
    elif condition == "deadline":
        resource.deadline = now[0]
    elif condition == "poison":
        writer.poisoned = True
    elif condition == "unacked":
        writer.acked = 0
    elif condition == "threshold":
        row["readings"]["self_rss_peak_bytes"]["value"] = selected["monitor"]["self_rss_stop_bytes"] + 1
    elif condition == "latched":
        resource.failure = "RA_G1_MONITOR_THRESHOLD"
    if expected is None:
        assert resource.require_current() is None
    else:
        with pytest.raises(c.Stage12Error) as caught:
            resource.require_current()
        assert caught.value.args == (expected,)
        assert resource.failure == expected
    assert calls == []

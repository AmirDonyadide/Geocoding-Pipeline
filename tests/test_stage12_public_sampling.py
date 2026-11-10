"""AP-1 bounded synthetic fault/credit/reader tests. No live resource proof."""

from copy import deepcopy
from types import SimpleNamespace as NS
import threading
import pytest
from test_stage12_public_operations_v2 import offline, FakeClock, H  # noqa:F401
from test_stage12_public_sampling_contract import ap_inputs
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sm
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


class BudgetLog:
    start_hash = H
    segment = 1
    epoch = H
    seq = 2
    last_hash = H

    def __init__(self):
        self.ap_budget_lock = threading.RLock()
        self.events = 10000
        self.bytes = 2**40
        self.ap_pending_events = self.ap_pending_bytes = 0

    def normal_event_headroom(self):
        return self.events - self.ap_pending_events

    def check_storage(self, n):
        a.require(n + self.ap_pending_bytes <= self.bytes)


def component():
    p, pl, start, *_ = ap_inputs()
    clock = FakeClock()
    log = BudgetLog()
    w = NS(
        wake=threading.Event(),
        failed=threading.Event(),
        ap_active_started=None,
        remaining_seconds=lambda: 180,
    )
    w.assert_owner = lambda: None
    co = NS(
        contract=a,
        writer=w,
        journal=log,
        clock=clock,
        plan=pl,
        profile=p,
        safety=threading.RLock(),
        wake=threading.Event(),
        measurement_failed=False,
        stop_reason=None,
        state="RUNNING",
        free_bytes=lambda: 2**40,
        ap_state=lambda: (
            0,
            dict(
                connection_slots=0,
                admitted_operations=0,
                pending_count=0,
                pending_bytes=0,
                reserved_bytes=0,
                selected_state_id=1,
            ),
        ),
        timing_observer=None,
        last_sample_ns=0,
        ap_cut_fault=False,
    )
    sampler = sm.Sampler(co)
    sampler.owner_ident = threading.get_ident()
    sampler.anchor = 0
    sampler.last_observed = 0
    sampler.head = sampler.association = H
    return sampler, co, log, clock


def test_AP03_AP14_all_states_count_no_overwrite():
    s, co, log, clock = component()
    for i in range(16):
        assert s._reserve() == (i, i + 1)
        s.owner_busy = False
        s.states[i] = (1, 2, 3, 4)[i % 4]
    assert len(s.arena) == 65536 and s.occupied == 16
    before = bytes(s.arena), list(s.ordinals)
    assert s._reserve() is None
    assert s.failure == "OBSERVATION_COUNT_LIMIT" and co.stop_reason == "RESOURCE"
    assert before == (bytes(s.arena), list(s.ordinals))


@pytest.mark.parametrize(
    "age,failed", [(499999999, False), (500000000, False), (500000001, True)]
)
@pytest.mark.parametrize("state", [1, 2, 3, 4])
def test_AP05_age_boundary_and_ACK_READY_credits(age, failed, state):
    s, co, log, clock = component()
    s._reserve()
    s.owner_busy = False
    s.states[0] = state
    s.entered[0] = 1
    s.observed[0] = 1
    s.last_observed = age + 1
    clock.value = age + 1
    s.health()
    assert (s.failure == "ACK_AGE_LIMIT") == (failed and state != 4)
    assert s.occupied == 1


@pytest.mark.parametrize(
    "gap,expected",
    [(-1, "CLOCK_INVALID"), (100000000, None), (100000001, "ACQUISITION_GAP")],
)
def test_AP06_true_acquisition_gap_is_inclusive(gap, expected):
    s, co, log, clock = component()
    clock.value = gap
    s.health()
    assert s.failure == expected


def test_AP06_query_failure_retains_hole_and_closes_admission():
    s, co, log, clock = component()

    def fail():
        raise OSError(5)

    co.free_bytes = fail
    assert not s.acquire()
    assert s.reserved == 1 and s.acquired == 0 and s.states[0] == 1
    assert s.failure == "ACQUISITION_FAILED" and co.stop_reason is not None
    assert s._reserve() is None


def test_AP10_AP14_pre_query_event_and_byte_reservations():
    for cause in ("events", "bytes"):
        s, co, log, clock = component()
        if cause == "events":
            log.events = 5
        else:
            log.bytes = 32768 + 16383
        assert s._reserve() is None
        assert s.reserved == 0 and co.stop_reason in ("BUDGET", "RESOURCE")
    s, co, log, clock = component()
    for _ in range(16):
        s._reserve()
        s.owner_busy = False
    assert log.ap_pending_events == 36
    assert log.ap_pending_bytes == 32768 + 16 * 16384
    s.transfer_event("RESOURCE_SAMPLE")
    s.transfer_event("SAMPLE_ACK")
    assert log.ap_pending_events == 34
    assert s.occupied == 16  # Writing/ACK never refunds physical slot.


def test_AP11_AP12_poison_stops_acquisition_and_no_credit_refund():
    s, co, log, clock = component()
    s._reserve()
    s.owner_busy = False
    s.writer.failed.set()
    s.health()
    assert s.failure == "WRITE_UNCERTAIN" and co.stop_reason == "AUDIT_IO"
    assert s._reserve() is None and s.occupied == 1
    s.pending_release = 0
    s.states[0] = 4
    s.after_turn()
    assert s.states[0] == 4 and s.occupied == 1


def test_AP15_AP16_cut_is_one_use_and_regular_cannot_race_grant():
    s, co, log, clock = component()
    s.cut = {
        "prefix_last_event_seq": log.seq,
        "prefix_last_event_sha256": log.last_hash,
    }
    assert s._reserve(False) is None and s.reserved == 0 and s.failure is None
    assert s._reserve(True) == (0, 1)
    s.owner_busy = False
    with pytest.raises(c.Stage12Error):
        s._reserve(True)


def test_AP16_stale_cut_and_second_acquisition_owner_rejected():
    s, co, log, clock = component()
    s.cut = {"prefix_last_event_seq": log.seq - 1, "prefix_last_event_sha256": H}
    with pytest.raises(c.Stage12Error):
        s._reserve(True)
    s.owner_ident = -1
    with pytest.raises(c.Stage12Error):
        s.acquire()


def test_AP17_close_deadline_does_not_reset_and_is_not_phase_extension():
    s, co, log, clock = component()
    s.close_requested = 1
    clock.value = 5_000_000_001
    s.last_observed = clock.value
    s.health()
    assert s.failure == "DRAIN_EXPIRED"
    assert co.stop_reason == "TIME"


def test_AP04_AP22_policy_bytes_and_canonical_bounded_probe():
    p, pl, start, *_ = ap_inputs()
    for value in (65535, 65537):
        policy = deepcopy(a.POLICY)
        policy["maximum_outstanding_bytes"] = value
        with pytest.raises(c.Stage12Error):
            a.validate(policy, a.POLICY_VERSION)
    # Oversize framing is rejected before any writer or storage access.
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_journal import Journal

    log = object.__new__(Journal)
    log.contract = a
    with pytest.raises(c.Stage12Error):
        log._readback(__import__("pathlib").Path("events/1.json"), b" " * 4097)


def test_AP23_slot_backing_is_fixed_not_a_native_bound_claim():
    s, *_ = component()
    assert len(s.states) == len(s.ordinals) == 16
    assert len(s.traces) == 16 and len(s.arena) == 65536
    # Test inventory is explicitly synthetic; runtime admission separately needs
    # actual ABI, method and competent review record, not this length check.


def test_AP08_AP09_hard_FIFO_wins_and_periodic_credit_once():
    import queue
    from concurrent.futures import Future
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_journal import Writer

    w = object.__new__(Writer)
    w.mailbox = queue.Queue(4)
    w.mailbox_capacity = threading.BoundedSemaphore(4)
    w.wake = threading.Event()
    w.failed = threading.Event()
    w.thread = threading.current_thread()
    w.ap_credit = False
    order = []
    w.check_deadline = lambda: None
    w.storage_guard = lambda: None
    w.stop = lambda: None
    sample = NS(
        service=lambda: order.append("pair") or True,
        probe_cut=lambda: None,
        health=lambda: None,
        pair_return=lambda: None,
        after_turn=lambda: None,
    )
    w.sampling = sample

    def execute(item):
        action, future = item
        future.set_result(action())

    w._execute = execute
    w._execute_periodic = lambda: w.sampling_pair()
    for n in range(3):
        w.mailbox_capacity.acquire()

        def hard(n=n):
            order.append(n)
            for _ in range(8):
                w.service_periodic()

        w.mailbox.put_nowait((hard, Future()))
    for _ in range(3):
        assert not w._ap_turn()
    assert order == [0, "pair", 1, "pair", 2, "pair"]

    # A hard action arriving inside an already-running idle pair wins next turn.
    def arrive():
        order.append("arrival-pair")
        w.mailbox_capacity.acquire()
        w.mailbox.put_nowait((lambda: order.append("arrived-hard"), Future()))
        return True

    sample.service = arrive
    w._ap_turn()
    sample.service = lambda: False
    w._ap_turn()
    assert order[-2:] == ["arrival-pair", "arrived-hard"]


@pytest.mark.parametrize("failure_at", ["sample", "witness"])
def test_AP11_AP12_pair_write_uncertainty_holds_credit(failure_at):
    s, co, log, clock = component()
    assert s.acquire()
    s.opened = True
    log.event = lambda kind, *args, **kwargs: (
        (_ for _ in ()).throw(OSError(5))
        if (
            kind == "RESOURCE_SAMPLE"
            if failure_at == "sample"
            else kind == "SAMPLE_ACK"
        )
        else H
    )
    s.writer.check_deadline = lambda: None
    s.writer.storage_guard = lambda: None
    with pytest.raises(OSError):
        s.service()
    assert s.writer.failed.is_set() and s.failure == "WRITE_UNCERTAIN"
    assert s.occupied == 1 and s.states[0] in (3, 4)
    assert s._reserve() is None


def test_AP15_empty_and_occupied_slots_cannot_close_without_cut():
    s, co, log, clock = component()
    s.close_requested = 1
    w = s.writer
    w.mailbox = __import__("queue").Queue()
    co.slots = {}
    co.safety_barriers = 0
    co.begin_in_progress = False
    co.mutation = threading.Lock()
    co.ap_persisted = co.ap_revision = 0
    co.last_ticket = co.finalized_ticket = 0
    s.acquire()
    s.probe_cut()
    assert s.cut is None
    s.states[0] = 0
    s.occupied = 0
    s.owner_busy = False
    s.probe_cut()
    assert s.cut is not None and co.ap_cut_granted
    token = deepcopy(s.cut)
    s.probe_cut()
    assert s.cut == token


def test_AP24_closed_rows_order_and_missing_milestones():
    row = {k: None for k in a.ASYNC_FIELDS}
    row.update(
        row_kind="PERIODIC_ASYNC",
        phase_id=1,
        segment_id=1,
        epoch_id=H,
        acquisition_seq=1,
        role="REGULAR",
        future_used=False,
        outcome="FAILED",
        acquire_enter_ns=0,
        reserved_ns=0,
    )
    a.validate_timing(row)
    bad = deepcopy(row)
    bad["outcome"] = "COMPLETE"
    with pytest.raises(c.Stage12Error):
        a.validate_timing(bad)
    bad = deepcopy(row)
    bad.update(free_query_start_ns=2, free_query_end_ns=1)
    with pytest.raises(c.Stage12Error):
        a.validate_timing(bad)
    bad = deepcopy(row)
    bad["future_finished_observed_ns"] = 1
    with pytest.raises(c.Stage12Error):
        a.validate_timing(bad)


def test_AP26_new_scope_never_admits_scientific_monitoring():
    p, pl, s, *_ = ap_inputs()
    p["monitoring"]["mode"] = "FROZEN_V1"
    with pytest.raises(c.Stage12Error):
        a.validate_profile(p)
    p, pl, s, *_ = ap_inputs()
    p["scope"] = "DEVELOPMENT"
    with pytest.raises(c.Stage12Error):
        a.validate_profile(p)


def observed_history():
    """Invented, independently encoded late-append history; never authority."""
    p, plan, start, *_ = ap_inputs()
    events = []
    assoc = None

    def emit(kind, body, ns):
        event = dict(
            schema_version=a.EVENT,
            campaign_start_sha256=a.digest(start),
            segment_id=1,
            seq=len(events) + 1,
            previous_event_sha256=a.digest(events[-1]) if events else None,
            epoch_id=H,
            mono_ns=ns,
            utc="2026-01-01T00:00:00.000000Z",
            kind=kind,
            body=body,
        )
        a.validate(event, a.EVENT)
        events.append(event)
        return event

    anchor = emit(
        "SEGMENT_OPEN",
        dict(
            authority_sha256=H,
            predecessor_snapshot_sha256=None,
            writer_exclusion_evidence_sha256=H,
            block_id=1,
            state_id=1,
        ),
        0,
    )
    baseline = dict(
        connection_slots=0,
        admitted_operations=0,
        pending_count=0,
        pending_bytes=0,
        reserved_bytes=0,
        selected_state_id=1,
    )
    seed = a.digest(
        dict(
            schema_version=a.SEED,
            campaign_start_sha256=a.digest(start),
            profile_sha256=a.digest(p),
            segment_id=1,
            epoch_id=H,
        )
    )
    assoc = seed
    emit(
        "SAMPLING_OPEN",
        dict(
            policy_sha256=a.POLICY_SHA,
            seed_sha256=seed,
            anchor_event_seq=1,
            anchor_event_sha256=a.digest(anchor),
            anchor_mono_ns=0,
            baseline=baseline,
        ),
        1,
    )
    changed = dict(baseline, pending_count=1, pending_bytes=23)
    emit(
        "RESOURCE",
        dict(
            cause="QUEUE_ADD",
            observed_mono_ns=70_000_000,
            free_allocated_disk_bytes=None,
            state_revision=1,
            mutation=True,
            mutation_mono_ns=70_000_000,
            **changed,
        ),
        70_000_000,
    )
    obs = dict(
        schema_version=a.OBSERVATION,
        campaign_start_sha256=a.digest(start),
        segment_id=1,
        epoch_id=H,
        acquisition_seq=1,
        previous_observation_sha256=seed,
        role="REGULAR",
        acquire_enter_ns=49_000_000,
        occupied_count_after_reserve=1,
        occupied_bytes_after_reserve=4096,
        free_query_start_ns=49_000_001,
        free_query_end_ns=49_999_999,
        observed_mono_ns=50_000_000,
        acquire_exit_ns=50_000_001,
        resource_revision=0,
        state=baseline,
        free_allocated_disk_bytes=2**40,
        cut=None,
    )

    def pair(value, ns):
        nonlocal assoc
        sample = emit(
            "RESOURCE_SAMPLE",
            dict(observation=value, observation_sha256=a.digest(value)),
            ns,
        )
        ack = emit(
            "SAMPLE_ACK",
            dict(
                acquisition_seq=value["acquisition_seq"],
                observation_sha256=a.digest(value),
                sample_event_seq=sample["seq"],
                sample_event_sha256=a.digest(sample),
                event_ack_mono_ns=ns + 1,
            ),
            ns + 2,
        )
        assoc = a.digest(
            dict(
                previous_sha256=assoc,
                acquisition_seq=value["acquisition_seq"],
                observation_sha256=a.digest(value),
                sample_event_seq=sample["seq"],
                sample_event_sha256=a.digest(sample),
                ack_event_seq=ack["seq"],
                ack_event_sha256=a.digest(ack),
            )
        )

    pair(obs, 80_000_000)
    emit(
        "RESOURCE",
        dict(
            cause="QUEUE_REMOVE",
            observed_mono_ns=92_000_000,
            free_allocated_disk_bytes=None,
            state_revision=2,
            mutation=True,
            mutation_mono_ns=92_000_000,
            **baseline,
        ),
        92_000_000,
    )
    cut = dict(
        campaign_start_sha256=a.digest(start),
        profile_sha256=a.digest(p),
        segment_id=1,
        epoch_id=H,
        at_mono_ns=95_000_000,
        last_prior_acquisition_seq=1,
        prior_acquisition_head_sha256=a.digest(obs),
        prior_association_head_sha256=assoc,
        prefix_last_event_seq=len(events),
        prefix_last_event_sha256=a.digest(events[-1]),
        last_witness_reopened_mono_ns=90_000_000,
        resource_revision=2,
    )
    final = dict(
        obs,
        acquisition_seq=2,
        previous_observation_sha256=a.digest(obs),
        role="FINAL",
        acquire_enter_ns=95_000_000,
        free_query_start_ns=95_000_001,
        free_query_end_ns=95_999_999,
        observed_mono_ns=96_000_000,
        acquire_exit_ns=96_000_001,
        resource_revision=2,
        cut=cut,
    )
    pair(final, 97_000_000)
    emit(
        "SAMPLING_CLOSE",
        dict(
            policy_sha256=a.POLICY_SHA,
            seed_sha256=seed,
            close_requested_mono_ns=94_000_000,
            producer_closed_mono_ns=96_000_002,
            cut_mono_ns=95_000_000,
            final_acquisition_seq=2,
            final_observed_mono_ns=96_000_000,
            last_reserved_seq=sm.count(2),
            acquired=sm.count(2),
            appended=sm.count(2),
            acknowledged=sm.count(2),
            witnessed=sm.count(2),
            acquisition_head_sha256=a.digest(final),
            association_head_sha256=assoc,
            failure=None,
            result="COMPLETE",
        ),
        99_000_000,
    )
    return p, start, events


def test_AP07_historical_sample_revision_never_rolls_hard_state_back():
    p, start, events = observed_history()
    passes = [0]

    def factory():
        passes[0] += 1
        return iter(events)

    summary = sm.inspect(factory, p, start, maximum_segments=1)[0]
    assert summary["complete"] and summary["reopened"] == sm.count(2)
    assert events[2]["body"]["state_revision"] == 1
    assert events[3]["body"]["observation"]["resource_revision"] == 0
    assert passes[0] == 2  # bounded fresh revision join, not one replay per sample
    bad = deepcopy(events)
    bad[3]["body"]["observation"]["state"]["pending_count"] = 1
    with pytest.raises(c.Stage12Error):
        sm.inspect(lambda: iter(bad), p, start, maximum_segments=1)


def test_AP20_missing_close_and_unacknowledged_final_are_unknown():
    p, start, events = observed_history()
    without_close = sm.inspect(lambda: iter(events[:-1]), p, start, maximum_segments=1)[
        0
    ]
    assert not without_close["complete"] and without_close["acquired"]["value"] is None
    half_final = sm.inspect(lambda: iter(events[:-2]), p, start, maximum_segments=1)[0]
    assert half_final["acknowledged"] == {"value": None, "confirmed_min": 1}
    assert half_final["appended"]["confirmed_min"] == 2


def test_AP24_byte_split_retains_full_v2_prefix_and_partial_status(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )

    observer = timing.SamplingTiming(
        tmp_path / "rows", phase_count=1, interval_seconds=60
    )
    row = {key: None for key in a.ASYNC_FIELDS}
    row.update(
        row_kind="PERIODIC_ASYNC",
        phase_id=1,
        segment_id=1,
        epoch_id=H,
        acquisition_seq=1,
        role="REGULAR",
        future_used=False,
        outcome="FAILED",
        acquire_enter_ns=0,
        reserved_ns=0,
    )
    for n in range(128):
        observer.periodic(dict(row, acquisition_seq=n + 1))
    summary = observer.close()
    rows = []
    reopened = cp.read_prefix(
        tmp_path / "rows", record_consumer=lambda n, v: rows.append(v)
    )
    assert not reopened["incomplete"] and len(rows) == 128
    assert reopened["verified_files"] > 1
    assert (
        summary["partial_timing_rows"] == 128
        and not summary["final_timing_coverage_complete"]
    )
    assert all(p.stat().st_size <= 32768 for p in (tmp_path / "rows").iterdir())


def test_AP22_event_tail_and_projected_row_caps(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    root = tmp_path / "root"
    io.reserve(root)
    io.reserve(root / "events")
    io.write(root / "events" / "00000000000000000001.json", b" " * 4097)
    seen = []
    original = io.read

    def read(path, **kwargs):
        seen.append(kwargs.get("limit"))
        return original(path, **kwargs)

    monkeypatch.setattr(io, "read", read)
    with pytest.raises(c.Stage12Error):
        list(j.read_events(root, H, contract=a))
    assert seen == [4096]
    io.write(root / "projected.json", c.canonical([{"extra": "x" * 4096}]))
    with pytest.raises(c.Stage12Error):
        list(j.read_array(root / "projected.json", maximum_row_bytes=4095))


def test_AP03_credit_released_only_once_after_witness_and_guards():
    s, co, log, clock = component()
    s._reserve()
    s.owner_busy = False
    s.states[0] = 4
    s.pending_release = 0
    s.after_turn()
    assert s.occupied == 0 and s.states[0] == 0
    with pytest.raises(c.Stage12Error):
        s.after_turn()


@pytest.mark.parametrize("size", [2047, 2048, 2049, 4095, 4096, 4097])
def test_AP04_wire_bound_does_not_admit_malformed_records(tmp_path, size):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_journal import Journal
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    root = tmp_path / "events"
    io.reserve(root)
    path = root / "1.json"
    raw = b" " * size
    io.write(path, raw)
    log = object.__new__(Journal)
    log.contract = a
    if size <= 4096:
        assert log._readback(path, raw) == raw
    else:
        with pytest.raises(c.Stage12Error):
            log._readback(path, raw)
    with pytest.raises(c.Stage12Error):
        a.parse(raw, a.EVENT)
    with pytest.raises(c.Stage12Error):
        a.parse(raw, a.OBSERVATION)


def test_AP17_cumulative_and_writer_guards_remain_nonresetting():
    s, co, log, clock = component()
    clock.value = s.deadline_ns
    s.last_observed = clock.value
    s.health()
    assert s.failure == "DRAIN_EXPIRED"
    s, co, log, clock = component()
    s.writer.ap_active_started = 0
    clock.value = 5_000_000_000
    s.last_observed = clock.value
    s.health()
    assert s.failure == "WRITE_UNCERTAIN" and s.writer.failed.is_set()


def test_AP09_gate_closes_on_age_even_without_owner_progress():
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_scheduler import (
        Coordinator,
    )

    s, co, log, clock = component()
    s._reserve()
    s.owner_busy = False
    s.states[0] = 3
    s.entered[0] = s.observed[0] = 1
    co.ap_enabled = True
    co.ap_sampler = s
    clock.value = 500_000_002
    co.last_sample_ns = clock.value
    with co.safety:
        assert not Coordinator._sampling_gate(co)
    assert co.measurement_failed and co.stop_reason is not None


def test_AP24_registration_is_atomic_with_reservation_before_query():
    s, co, log, clock = component()
    rows = []
    failures = []
    co.timing_observer = NS(
        phase_id=1,
        periodic=lambda row: rows.append(row),
        note_failure=lambda: failures.append(True),
    )
    index, _ = s._reserve()
    assert s.states[index] == 1 and s.traces[index] is not None
    s.writer.failed.set()
    s.uncertain_traces()
    assert len(rows) == 1 and rows[0]["outcome"] == "UNCERTAIN"
    assert rows[0]["observation_sha256"] is None and rows[0]["observed_ns"] is None
    assert failures and s.occupied == 1 and s.states[index] == 1


def test_AP26_matrix_context_dispatch_preserves_old_reader_interface(
    monkeypatch, tmp_path
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
    from test_stage12_public_operations_v2 import inputs

    calls = []
    monkeypatch.setattr(
        matrix.journal,
        "read_events",
        lambda *args, **kwargs: calls.append((args, kwargs)) or iter(()),
    )
    old_start = inputs()[2]
    new_start = ap_inputs()[2]
    list(matrix._events(tmp_path, old_start))
    list(matrix._events(tmp_path, new_start))
    assert calls[0] == ((tmp_path, a.digest(old_start)), {})
    assert calls[1] == ((tmp_path, a.digest(new_start)), {"contract": a})


def test_AP22_selected_inventory_invocations_include_failure_writers(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_journal import Journal

    log = object.__new__(Journal)
    log.contract = a
    log.writer = NS(
        sampling=True, root=tmp_path, assert_owner=lambda: None, thread=object()
    )
    log.ap_budget_lock = threading.RLock()
    log.ap_inventory_limit = 1
    log.ap_inventory_calls = 0
    log.claim_inventory("measurement_event_prefix.json")
    assert log.ap_inventory_calls == 1
    # Both actual entrypoints reject their second invocation before I/O, using
    # the same selected cap; no automatic refund/retry after refusal.
    with pytest.raises(c.Stage12Error):
        log.write_array("available_event_inventory.json", iter(()))
    assert log.ap_inventory_calls == 2 and not list(tmp_path.iterdir())
    with pytest.raises(c.Stage12Error):
        log.stream_array("attempt_inventory.json", iter(()))
    assert log.ap_inventory_calls == 3 and not list(tmp_path.iterdir())
    log.claim_inventory("runtime_inventory.json")
    assert log.ap_inventory_calls == 3


def test_AP22_predecessor_projection_cannot_add_third_raw_copy(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j

    monkeypatch.setattr(
        j, "predecessor_root", lambda root: tmp_path / "invented_parent"
    )
    prefix = object.__new__(j.MeasurementPrefix)
    prefix.contract = a
    prefix.root = tmp_path
    assert prefix.build() is False
    with pytest.raises(c.Stage12Error):
        j.MeasurementPrefix.from_closed(tmp_path, H, 1, check=lambda: None, contract=a)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("method", ["stream_array", "write_array"])
@pytest.mark.parametrize("size", [512, 513])
def test_AP22_inventory_entry_wire_cap_precedes_row_write(tmp_path, method, size):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_journal import Journal

    log = object.__new__(Journal)
    log.contract = a
    log.writer = NS(
        sampling=True,
        root=tmp_path,
        assert_owner=lambda: None,
        thread=object(),
        call=lambda action: action(),
        check_deadline=lambda: None,
        failures=None,
        failed=threading.Event(),
    )
    log.ap_budget_lock = threading.RLock()
    log.ap_inventory_limit = 8
    log.ap_inventory_calls = 0
    log.prior_bytes = log.prior_block_bytes = 0
    log.storage_budget = log.block_byte_budget = 2**20
    log.check_storage = lambda n: None
    fixed = {"path": "", "sha256": H}
    row = dict(fixed, path="x" * (size - len(c.canonical(fixed))))
    assert len(c.canonical(row)) == size
    path = tmp_path / "event_inventory.json"
    if size == 512:
        getattr(log, method)(path.name, iter([row]))
        assert path.read_bytes() == c.canonical([row])
    else:
        with pytest.raises(c.Stage12Error):
            getattr(log, method)(path.name, iter([row]))
        assert (
            path.read_bytes() == b"["
        )  # charged partial delimiter only, no row/truncation
    assert log.ap_inventory_calls == 1

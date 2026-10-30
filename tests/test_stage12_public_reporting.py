"""Exact numeric oracles and immutable block/report dependency checks."""

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_reporting as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_stage12_public_operations_v2 import H, offline  # noqa: F401
from test_stage12_public_scheduler import run_offline


@pytest.mark.parametrize(
    "case", ["ordinary", "missing_timing", "duplicate_timing", "duplicate_network"]
)
def test_1804272_bounded_join_matches_single_work_and_preserves_failures(
    tmp_path, monkeypatch, case
):
    import copy

    campaign, root, (profile, plan, start, rows, _) = run_offline(tmp_path, count=9)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]
    if case == "missing_timing":
        events = [
            e
            for e in events
            if not (e["kind"] == "AUDIT_TIMING" and e["body"]["work_id"] == 1)
        ]
    elif case.startswith("duplicate_"):
        kind = "AUDIT_TIMING" if case == "duplicate_timing" else "NETWORK_DONE"
        example = next(
            e for e in events if e["kind"] == kind and e["body"]["work_id"] == 1
        )
        events[-1:-1] = [copy.deepcopy(example) for _ in range(7)]
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from events

    def report():
        return r.block_report(
            plan,
            profile,
            1,
            events=source,
            works=lambda: iter(rows),
            verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
            repeat_evidence=lambda: (
                campaign["blocks"][0]["repeat_comparison_sha256"],
                True,
            ),
            monitoring_closed=lambda: True,
        )

    monkeypatch.setattr(r, "_TIMING_JOIN_WORKS", 1)
    one = report()
    one_calls = calls
    calls = 0
    monkeypatch.setattr(r, "_TIMING_JOIN_WORKS", 8)
    grouped = report()
    assert grouped == one
    assert calls < one_calls
    if case == "ordinary":
        assert grouped == campaign["blocks"][0]
        assert grouped["status"] == "EXPLORATORY_ONLY"
    else:
        assert grouped["status"] == "INCOMPLETE"
        assert not grouped["resource_sampling_complete"]
    if case == "duplicate_timing":
        assert grouped["latencies"]["writer_wait"]["n"] == 16
    if case == "duplicate_network":
        assert grouped["latencies"]["transport_all"]["n"] == 16


@pytest.mark.parametrize("count", [8, 9, 17])
def test_1804272_join_scan_count_and_fixed_memory_bound(tmp_path, monkeypatch, count):
    import sys

    # Preserve the original eight-work implementation-bound regression.
    monkeypatch.setattr(r, "_TIMING_JOIN_WORKS", 8)
    monkeypatch.setattr(r, "_COUNT_JOIN_WORKS", 1)
    campaign, root, (profile, plan, start, rows, _) = run_offline(tmp_path, count=count)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]
    calls = rounds = 0
    retained_peak = 0
    stats = r.exact_stats

    def source():
        nonlocal calls
        calls += 1
        yield from events

    def counted(values, names):
        def stream():
            nonlocal rounds
            rounds += 1
            yield from values()

        return stats(stream, names)

    def bounded_frames(frame, event, arg):
        nonlocal retained_peak
        if frame.f_code.co_filename != r.__file__:
            return
        if frame.f_code.co_name == "values":
            state = frame.f_locals
            for field in ("starts", "timings", "transports"):
                mapping = state.get(field, {})
                assert len(mapping) <= 8
                assert all(len(items) <= 5 for items in mapping.values())
            retained_peak = max(retained_peak, len(state.get("starts", {})))
        elif frame.f_code.co_name == "single_values":
            assert len(frame.f_locals.get("started", {})) <= 5
            assert len(frame.f_locals.get("timings", [])) <= 5

    monkeypatch.setattr(r, "exact_stats", counted)
    previous_profile = sys.getprofile()
    sys.setprofile(bounded_frames)
    try:
        result = r.block_report(
            plan,
            profile,
            1,
            events=source,
            works=lambda: iter(rows),
            verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
            repeat_evidence=lambda: (
                campaign["blocks"][0]["repeat_comparison_sha256"],
                True,
            ),
            monitoring_closed=lambda: True,
        )
    finally:
        sys.setprofile(previous_profile)
    assert result == campaign["blocks"][0]
    assert calls == 1 + count + rounds * ((count + 7) // 8)
    assert retained_peak == min(count, 8)


@pytest.mark.parametrize(
    "values,expected",
    [
        ([], (None, None, None)),
        ([7], (7, 7, 7)),
        ([1, 9], (1, 9, 9)),
        (list(range(1, 21)), (10, 19, 20)),
    ],
)
def test_T14_nearest_rank_numeric_oracle(values, expected):
    result = r.stat(lambda: iter(values))
    assert tuple(result[k] for k in ("p50_ms", "p95_ms", "p99_ms")) == expected
    assert result["n"] == len(values)
    assert r.ratio(4, 2_000_000_000, per_second=True) == {
        "num": 4_000_000_000,
        "den": 2_000_000_000,
    }
    assert r.ratio(0, 0) is None and r.ratio(4, None) is None


def test_T14_unknown_counts_never_become_zero_or_permit_completion():
    assert r.count(None, 3) == {"value": None, "confirmed_min": 3}
    with pytest.raises(c.Stage12Error):
        o.validate_type({"value": 4, "confirmed_min": 3}, "Count")


def test_T14_report_hash_graph_is_acyclic_and_measurement_whole(tmp_path):
    campaign, root, (_, _, start, _, _) = run_offline(tmp_path)
    block = campaign["blocks"][0]
    events = list(j.read_events(root, o.digest(start)))
    closed = next(e for e in events if e["kind"] == "BLOCK_CLOSED")
    assert (
        closed["body"]["report_sha256"]
        == c.sha(io.read(root / "block_report.json")).hex()
    )
    assert block["input_last_event_seq"] == closed["seq"] - 1
    assert events[block["input_last_event_seq"] - 1]["kind"] == "RESOURCE"
    beginning = min(
        e["body"]["started_mono_ns"] for e in events if e["kind"] == "ATTEMPT_STARTED"
    )
    end = events[block["input_last_event_seq"] - 1]["body"]["observed_mono_ns"]
    assert block["duration_ns"] == end - beginning
    assert block["status"] == "EXPLORATORY_ONLY"
    snapshot = io.metadata(io.read(root / "snapshot.json"))
    assert snapshot["last_event_sha256"] == o.digest(events[-1])
    assert campaign["segment_snapshot_hashes"] == [o.digest(snapshot)]
    assert campaign["approval_status"] == "UNISSUED"


@pytest.mark.parametrize(
    "omitted", ["AUDIT_TIMING", "START_RESERVE", "RESERVATION_RELEASE"]
)
def test_T14_missing_required_evidence_is_incomplete_and_metrics_unknown(
    tmp_path, omitted
):
    campaign, root, (profile, plan, start, rows, _) = run_offline(tmp_path)
    end = campaign["blocks"][0]["input_last_event_seq"]
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= end
        and e["kind"] != omitted
        and not (e["kind"] == "RESOURCE" and e["body"]["cause"] == omitted)
    ]
    result = r.block_report(
        plan,
        profile,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=lambda _w, _e: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert result["status"] == "INCOMPLETE" and not result["resource_sampling_complete"]
    if omitted == "AUDIT_TIMING":
        assert result["peaks"]["writer_wait_ms"] is None
        assert result["latencies"]["full_slot_data"]["p95_ms"] is None
    else:
        assert result["peaks"]["admitted"] is None


def test_T13_T14_preselected_confirmation_predicates(tmp_path):
    # All numbers below are invented test criteria, never a service measurement.
    from test_stage12_public_operations_v2 import (
        inputs,
        rebind,
        FakeAuthority,
        FakeClock,
        KEY,
    )
    from test_stage12_public_scheduler import synthetic_dispatch
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe

    profile, plan, start, rows, runtime = inputs(2)
    plan["capability_parent_sha256"] = H
    plan["blocks"][0].update(
        evaluation="CONFIRMATORY",
        criteria={
            "min_valid_data": 2,
            "min_duration_ms": 1,
            "max_duration_ms": 1000,
            "min_attempt_rate": {"num": 1, "den": 1},
            "min_durable_data_rate": {"num": 1, "den": 1},
            "max_http_p95_ms": 5,
            "max_http_p99_ms": 5,
            "max_slot_p95_ms": 1000,
            "max_slot_p99_ms": 1000,
            "max_retry_fraction": {"num": 0, "den": 1},
            "max_pending_count": 4,
            "max_pending_bytes": 2**20,
            "max_reserved_bytes": o.MEMORY,
            "max_writer_wait_ms": 1000,
            "required_cells": [
                {"mode": probe.fixtures()[0]["core"]["search_mode"], "size": 1}
            ],
            "min_per_cell": 2,
        },
    )
    rebind(profile, plan, start)
    clock = FakeClock()
    output = tmp_path / "confirmation"
    report = cli.run_operations_block(
        profile,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=output,
        block_id=1,
        authority=FakeAuthority(),
        clock=clock,
        dispatch=synthetic_dispatch(clock),
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
    assert report["blocks"][0]["status"] == "PASS"
    assert report["blocks"][0]["reasons"] == []
    assert not report["scientific_identity_verified"]
    assert report["approval_status"] == "UNISSUED"


@pytest.mark.parametrize(
    "stretch_ns,complete",
    [(100_000_000, True), (100_000_001, False), (10_000_000_000, False)],
)
def test_F04_T14_periodic_schedule_coverage_is_checked(tmp_path, stretch_ns, complete):
    report, root, (p, plan, start, rows, _) = run_offline(tmp_path, count=1)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= report["blocks"][0]["input_last_event_seq"]
    ]
    opened = events[0]["mono_ns"]
    assert events[-1]["body"]["cause"] == "PERIODIC"
    events[-1]["body"]["observed_mono_ns"] = opened + stretch_ns
    events[-1]["mono_ns"] = opened + stretch_ns
    result = r.block_report(
        plan,
        p,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert result["resource_sampling_complete"] is complete
    assert (result["status"] == "INCOMPLETE") is not complete
    # Hard resource mutation peaks remain independently known despite a gap.
    assert result["peaks"]["admitted"] == 1


def test_F04_T14_writer_delay_below_guard_leaves_incomplete_sampling(
    monkeypatch, tmp_path
):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_operations_v2 import inputs, FakeClock
    from test_stage12_public_scheduler import repair_common, synthetic_dispatch

    p, plan, start, rows, runtime = inputs(1)
    clock, original = FakeClock(), io.write

    def delayed(path, raw):
        if path.name == "call_0001_attempt_1_validation.json":
            clock.advance(500_000_000)
        return original(path, raw)

    monkeypatch.setattr(io, "write", delayed)
    root = tmp_path / "writer-delay"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=root,
        clock=clock,
        dispatch=synthetic_dispatch(clock),
        epoch=H,
        **repair_common(rows, runtime),
    )
    assert p["resource_sample_period_ms"] < 500 < p["resources"]["writer_guard_ms"]
    block = report["blocks"][0]
    assert block["status"] == "INCOMPLETE"
    assert not block["resource_sampling_complete"] and not report["report_complete"]
    assert (
        block["peaks"]["admitted"] == 1
        and block["peaks"]["reserved_bytes"] == o.RESERVATION
    )
    assert block["peaks"]["writer_wait_ms"] <= p["resources"]["writer_guard_ms"]
    assert block["counts"]["durable_valid_data"] == r.count(1)


@pytest.mark.parametrize("missing_cause", ["START_RESERVE", "PERIODIC"])
def test_F04_T14_required_disk_sample_cannot_be_null(tmp_path, missing_cause):
    report, root, (p, plan, start, rows, _) = run_offline(tmp_path, count=1)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= report["blocks"][0]["input_last_event_seq"]
    ]
    for event in events:
        if event["kind"] == "RESOURCE" and event["body"]["cause"] == missing_cause:
            event["body"]["free_allocated_disk_bytes"] = None
    result = r.block_report(
        plan,
        p,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert result["status"] == "INCOMPLETE" and not result["resource_sampling_complete"]


@pytest.mark.parametrize("unavailable_ids", [{1}, {1, 2}, {1, 2, 3}])
def test_F05_T14_unavailable_receipts_keep_lower_bounds_and_null_rates(
    tmp_path, unavailable_ids
):
    report, root, (p, plan, start, rows, _) = run_offline(tmp_path, count=3)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= report["blocks"][0]["input_last_event_seq"]
    ]
    verified = []

    def receipt(work, event):
        verified.append((work["work_id"], event["attempt"]))
        if work["work_id"] in unavailable_ids:
            raise OSError("SYNTHETIC_UNAVAILABLE_RECEIPT")
        return {"outcome": c.SUCCESS[1]}

    result = r.block_report(
        plan,
        p,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=receipt,
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    lower = 3 - len(unavailable_ids)
    assert verified == [(1, 1), (2, 1), (3, 1)]  # one validated evidence view
    for key in (
        "http_completions",
        "http_200",
        "durable_valid_data",
        "durable_valid_zero",
    ):
        assert result["counts"][key] == r.count(None, lower)
    for key in (
        "unknown_delivery",
        "unprocessed_data",
        "durable_retryable",
        "durable_terminal_failure",
    ):
        assert result["counts"][key] == r.count(None, 0)
    assert result["rates"]["http_completions_per_s"] is None
    assert result["rates"]["durable_data_per_s"] is None
    assert result["counts"]["attempt_starts"] == r.count(3)
    assert result["cells"][0]["durable_valid"] == r.count(None, lower)
    assert not result["receipts_complete"] and result["status"] == "INCOMPLETE"
    campaign = r.campaign_report(
        start,
        event_inventory_sha256=H,
        attempt_inventory_sha256=H,
        snapshots=[],
        blocks=[result],
        disposition="STOPPED",
        scientific_identity_verified=False,
        reconciliation_reasons=[],
        plan=plan,
    )
    assert campaign["campaign_counts"]["durable_valid_data"] == r.count(None, lower)
    assert campaign["campaign_counts"]["unprocessed_data"] == r.count(None, 0)
    assert not campaign["report_complete"]


def test_F05_T14_mixed_known_unprocessed_and_unavailable_receipt_lower_bound(tmp_path):
    report, root, (p, plan, start, rows, _) = run_offline(tmp_path, count=3)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= report["blocks"][0]["input_last_event_seq"]
    ]
    # A separate synthetic reader input has no attempt evidence for work 3.
    events = [e for e in events if e["body"].get("work_id") != 3]

    def receipt(work, event):
        if work["work_id"] == 2:
            raise OSError("SYNTHETIC_UNAVAILABLE_RECEIPT")
        return {"outcome": c.SUCCESS[1]}

    result = r.block_report(
        plan,
        p,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=receipt,
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert result["counts"]["durable_valid_data"] == r.count(None, 1)
    assert result["counts"]["unprocessed_data"] == r.count(None, 1)
    campaign = r.campaign_report(
        start,
        event_inventory_sha256=H,
        attempt_inventory_sha256=H,
        snapshots=[],
        blocks=[result],
        disposition="STOPPED",
        scientific_identity_verified=False,
        reconciliation_reasons=[],
        plan=plan,
    )
    assert campaign["campaign_counts"]["unprocessed_data"] == r.count(None, 1)


def test_F05_T14_T16_unavailable_control_does_not_inflate_or_null_data(tmp_path):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_operations_v2 import inputs, FakeClock
    from test_stage12_public_scheduler import (
        repair_common,
        synthetic_dispatch,
        FakeMonitor,
    )
    from test_stage12_public_operational_audit import Control, capture
    from stage12_synthetic import body

    p, plan, start, rows, runtime = inputs(1, monitored=True)
    clock = FakeClock()
    common = repair_common(rows, runtime)
    common.update(
        control_adapters={1: Control(), 2: Control()}, monitor=FakeMonitor(clock)
    )

    def dispatch(work, target, hooks):
        raw = (
            c.canonical({"synthetic_index": "test"})
            if work["kind"] == "SERVICE_CONTROL"
            else body([])
        )
        return synthetic_dispatch(clock, capture(raw))(work, target, hooks)

    root = tmp_path / "control"
    campaign = cli.run_operations_block(
        p, plan, start, output=root, clock=clock, dispatch=dispatch, epoch=H, **common
    )
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]

    def receipt(work, event):
        if work["kind"] == "SERVICE_CONTROL":
            raise OSError("SYNTHETIC_UNAVAILABLE_CONTROL")
        return {"outcome": c.SUCCESS[1]}

    report = r.block_report(
        plan,
        p,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=receipt,
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert report["counts"]["durable_valid_data"] == r.count(1)
    assert report["counts"]["unprocessed_data"] == r.count(0)
    assert report["counts"]["http_completions"] == r.count(None, 1)
    assert report["counts"]["unknown_delivery"] == r.count(None)
    assert report["rates"]["http_completions_per_s"] is None
    assert report["rates"]["durable_data_per_s"] is not None
    assert report["status"] == "INCOMPLETE" and not report["receipts_complete"]


@pytest.mark.parametrize(
    "values",
    [
        [],
        [0],
        [7],
        [1, 9],
        list(range(1, 21)),
        [4] * 21,
        [0, 2**64 - 1],
        [0, 1, 1, 2, 2, 2, 10**12],
    ],
)
def test_T14_shared_search_exact_edges_and_scan_bound(values):
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from values

    result = r.stat(source)
    ordered = sorted(values)
    assert result == {
        "n": len(values),
        **{
            f"p{q}_ms": ordered[(q * len(values) + 99) // 100 - 1] if values else None
            for q in (50, 95, 99)
        },
        "max_ms": max(values) if values else None,
    }
    assert calls <= 1 + max(values, default=0).bit_length()


def test_T14_shared_metrics_stream_without_campaign_sized_cache():
    import tracemalloc

    names = tuple(o.TYPES["Latencies"])
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        # A small generated stream, not resident response bodies or a campaign cache.
        for value in range(4096):
            for name in names:
                yield name, value

    tracemalloc.start()
    try:
        measured = r.exact_stats(source, names)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 256 * 1024
    assert calls <= 13  # Shared by all four metrics and all three percentiles.
    for result in measured.values():
        assert result == dict(
            n=4096, p50_ms=2047, p95_ms=3891, p99_ms=4055, max_ms=4095
        )


def test_T14_changed_values_with_same_count_and_maximum_are_rejected():
    calls = 0

    def values():
        nonlocal calls
        calls += 1
        return iter([0, 10] if calls == 1 else [9, 10])

    with pytest.raises(c.Stage12Error):
        r.stat(values)


@pytest.mark.parametrize("bad", [-1, True, 2**64, 1.0])
def test_T14_shared_search_rejects_non_uint_samples(bad):
    with pytest.raises(c.Stage12Error):
        r.stat(lambda: iter([bad]))


def test_T14_consolidated_report_bounds_traversals_and_rejects_changed_prefix(tmp_path):
    import copy

    campaign, root, (p, plan, start, rows, _) = run_offline(tmp_path)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from events

    kwargs = dict(
        works=lambda: iter(rows),
        verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (
            campaign["blocks"][0]["repeat_comparison_sha256"],
            True,
        ),
        monitoring_closed=lambda: True,
    )
    result = r.block_report(plan, p, 1, events=source, **kwargs)
    assert result == campaign["blocks"][0]
    maximum = max(v["max_ms"] or 0 for v in result["latencies"].values())
    assert calls <= 1 + len(rows) * (2 + maximum.bit_length())
    assert calls < 20
    # Prefix changes that do not affect latency values must also be detected.
    calls = 0

    def changed():
        nonlocal calls
        calls += 1
        for event in events:
            value = copy.deepcopy(event)
            if calls > 1 and value["kind"] == "RESOURCE":
                value["body"]["pending_bytes"] += 1
            yield value

    with pytest.raises(c.Stage12Error):
        r.block_report(plan, p, 1, events=changed, **kwargs)


def test_T14_unknown_timing_work_is_rejected_and_duplicate_tail_stays_bounded(tmp_path):
    import copy

    campaign, root, (p, plan, start, rows, _) = run_offline(tmp_path, count=1)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]
    kwargs = dict(
        works=lambda: iter(rows),
        verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    unknown = copy.deepcopy(events)
    next(e for e in unknown if e["kind"] == "AUDIT_TIMING")["body"]["work_id"] = 9999
    with pytest.raises(c.Stage12Error):
        r.block_report(plan, p, 1, events=lambda: iter(unknown), **kwargs)
    duplicate = copy.deepcopy(events)
    timing = next(e for e in duplicate if e["kind"] == "AUDIT_TIMING")
    duplicate[-1:-1] = [copy.deepcopy(timing) for _ in range(6)]
    for i, event in enumerate(duplicate, 1):
        event["seq"] = i
    result = r.block_report(plan, p, 1, events=lambda: iter(duplicate), **kwargs)
    assert result["status"] == "INCOMPLETE"
    for name in ("full_slot_data", "writer_wait"):
        assert result["latencies"][name] == dict(
            n=7, p50_ms=None, p95_ms=None, p99_ms=None, max_ms=None
        )


@pytest.mark.parametrize(
    "damage", ["missing_final", "backward_observation", "startup_gap"]
)
def test_1804093_sampling_lifecycle_missing_and_out_of_order_stays_incomplete(
    tmp_path, damage
):
    report, root, (profile, plan, start, rows, _) = run_offline(tmp_path, count=1)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= report["blocks"][0]["input_last_event_seq"]
    ]
    assert events[-1]["body"]["cause"] == "PERIODIC"
    if damage == "missing_final":
        events.pop()
    elif damage == "startup_gap":
        events[-1]["body"]["observed_mono_ns"] += 100_000_001
        events[-1]["mono_ns"] = events[-1]["body"]["observed_mono_ns"]
    else:
        # Two explicit sample observations in one epoch; no scheduled timestamps.
        import copy

        previous = copy.deepcopy(events[-1])
        previous["body"]["observed_mono_ns"] = 10
        previous["mono_ns"] = 10
        events.insert(-1, previous)
        events[-1]["body"]["observed_mono_ns"] = 9
        events[-1]["mono_ns"] = 10
    block = r.block_report(
        plan,
        profile,
        1,
        events=lambda: iter(events),
        works=lambda: iter(rows),
        verified_receipt=lambda *_: {"outcome": c.SUCCESS[1]},
        repeat_evidence=lambda: (H, True),
        monitoring_closed=lambda: True,
    )
    assert not block["resource_sampling_complete"]
    assert block["status"] == "INCOMPLETE"
    assert "INSUFFICIENT_MEASUREMENT" in block["reasons"]


@pytest.mark.parametrize(
    "case", ["ordinary", "missing_receipt", "missing_timing", "resumed_epoch"]
)
def test_scale120_batched_counts_exact_equivalence_and_bounds(
    tmp_path, monkeypatch, case
):
    import copy

    campaign, root, (profile, plan, start, rows, _) = run_offline(tmp_path, count=65)
    events = [
        e
        for e in j.read_events(root, o.digest(start))
        if e["seq"] <= campaign["blocks"][0]["input_last_event_seq"]
    ]
    if case == "missing_timing":
        events = [
            e
            for e in events
            if not (e["kind"] == "AUDIT_TIMING" and e["body"]["work_id"] == 64)
        ]
    if case == "resumed_epoch":
        opening = copy.deepcopy(events[0])
        opening["seq"] = events[-1]["seq"]
        events.insert(-1, opening)
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from events

    def receipt(row, _):
        if case == "missing_receipt" and row["work_id"] == 64:
            raise c.Stage12Error("S12_CAPTURE_INCOMPLETE")
        return {"outcome": c.SUCCESS[1]}

    def report():
        return r.block_report(
            plan,
            profile,
            1,
            events=source,
            works=lambda: iter(rows),
            verified_receipt=receipt,
            repeat_evidence=lambda: (H, True),
            monitoring_closed=lambda: True,
        )

    monkeypatch.setattr(r, "_COUNT_JOIN_WORKS", 1)
    monkeypatch.setattr(r, "_TIMING_JOIN_WORKS", 8)
    before = report()
    old_calls = calls
    calls = 0
    monkeypatch.setattr(r, "_COUNT_JOIN_WORKS", 64)
    monkeypatch.setattr(r, "_TIMING_JOIN_WORKS", 64)
    after = report()
    assert after == before
    assert calls < old_calls // 4
    if case == "missing_receipt":
        assert after["counts"]["durable_valid_data"] == {
            "value": None,
            "confirmed_min": 64,
        }
        assert after["rates"]["durable_data_per_s"] is None
    if case == "resumed_epoch":
        assert after["duration_ns"] is None
        assert after["status"] == "INCOMPLETE"


@pytest.mark.parametrize("length", [0, 1, 1024, 1025])
def test_scale120_exact_numeric_buffer_boundary_matches_search(monkeypatch, length):
    names = tuple(o.TYPES["Latencies"])
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        for i in range(length):
            yield names[0], (i * 37) % 4096
            yield names[2], 2**64 - 1 if i % 7 else 0
        # Other metrics deliberately remain empty.

    monkeypatch.setattr(r, "_EXACT_VALUE_BOUND", 0)
    expected = r.exact_stats(source, names)
    calls = 0
    monkeypatch.setattr(r, "_EXACT_VALUE_BOUND", 1024)
    actual = r.exact_stats(source, names)
    assert actual == expected
    if length == 1:
        assert calls == 1  # Both generated values are zero; no search required.
    elif 1 < length <= 1024:
        assert calls == 2
    elif length > 1024:
        assert calls > 2


def test_scale120_exact_numeric_buffer_rejects_reordered_second_pass():
    calls = 0

    def values():
        nonlocal calls
        calls += 1
        return iter([3, 9, 4] if calls == 1 else [4, 9, 3])

    with pytest.raises(c.Stage12Error):
        r.stat(values)


def test_scale120_fast_numeric_heap_is_fixed_and_small():
    import tracemalloc

    names = tuple(o.TYPES["Latencies"])

    def values():
        for n in range(1024):
            for name in names:
                yield name, 2**64 - n - 1

    tracemalloc.start()
    try:
        result = r.exact_stats(values, names)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 256 * 1024  # Includes arrays, Python sort temporaries and results.
    assert all(value["n"] == 1024 for value in result.values())

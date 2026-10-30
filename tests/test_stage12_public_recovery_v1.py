"""Only clean closures can be candidates for separately authorized continuation."""

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_operations_v2 import H, FakeAuthority, offline  # noqa: F401
from test_stage12_public_scheduler import run_offline


def test_T12_begin_only_is_unknown_and_reconciliation_never_resumes(tmp_path):
    root = tmp_path / "unclean"
    io.reserve(root)
    io.reserve(root / "events")
    io.write(
        root / "call_0001_attempt_1_begin.json",
        c.canonical({"call": 1, "attempt": 1, "outcome": "UNKNOWN_DELIVERY"}),
    )
    result = r.unclean_reconciliation(root, H)
    assert result["disposition"] == "RECOVERY_BLOCKED"
    assert result["snapshot"] is None
    assert result["begins_charged"] == {"value": None, "confirmed_min": 1}
    assert not result["report_complete"]
    assert set(p.name for p in root.iterdir()) == {
        "events",
        "call_0001_attempt_1_begin.json",
    }


def test_T12_corrupt_begin_does_not_fabricate_exact_count(tmp_path):
    root = tmp_path / "corrupt"
    io.reserve(root)
    io.reserve(root / "events")
    io.write(root / "call_0001_attempt_1_begin.json", b"{incomplete")
    result = r.unclean_reconciliation(root, H)
    assert result["begins_charged"] == {"value": None, "confirmed_min": 0}
    assert result["snapshot"] is None


def test_T11_completed_is_not_automatically_resumable(tmp_path):
    report, root, (profile, plan, start, rows, _) = run_offline(tmp_path)
    snapshot = io.metadata(io.read(root / "snapshot.json"))
    assert (
        snapshot["disposition"] == "COMPLETED"
        and not snapshot["controller"]["resume_eligible"]
    )
    with pytest.raises(c.Stage12Error):
        r.clean_continuation(
            root,
            start,
            profile,
            plan,
            authority=FakeAuthority(),
            new_segment_authority=H,
            now_ns=0,
            work_factory=lambda: iter(rows),
            verify_receipt=lambda *_: None,
        )
    state = r.replay(j.read_events(root, o.digest(start)))
    assert state["closed"] and not state["unfinished"] and state["begins_charged"] == 2


def test_T12_finalized_without_begin_and_duplicate_ordinal_rejected():
    start = {
        "schema_version": o.EVENT,
        "campaign_start_sha256": H,
        "segment_id": 1,
        "seq": 1,
        "previous_event_sha256": None,
        "epoch_id": H,
        "mono_ns": 0,
        "utc": "2026-01-01T00:00:00.000000Z",
        "kind": "SEGMENT_OPEN",
        "body": {
            "authority_sha256": H,
            "predecessor_snapshot_sha256": None,
            "writer_exclusion_evidence_sha256": H,
            "block_id": 1,
            "state_id": 1,
        },
    }
    finalized = {
        **start,
        "seq": 2,
        "kind": "ATTEMPT_FINALIZED",
        "body": {
            "work_id": 1,
            "attempt": 1,
            "ticket": 1,
            "outcome": {"kind": "DATA", "value": c.SUCCESS[1]},
            "reason": "OK",
            "receipt_inventory_sha256": H,
            "elapsed_ms": 1,
            "status": 200,
            "retry_after_seconds": None,
            "retry_delay_ms": None,
        },
    }
    with pytest.raises(c.Stage12Error):
        r.replay([start, finalized])


def test_T11_clean_retry_continuation_rewaits_full_delays_and_keeps_ordinals(tmp_path):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_operations_v2 import inputs, FakeClock, KEY
    from test_stage12_public_scheduler import synthetic_dispatch
    from test_stage12_public_operational_audit import capture

    profile, plan, start, rows, runtime = inputs(1)
    first_clock = FakeClock()
    first = tmp_path / "first"
    common = dict(
        work_factory=lambda: iter(rows),
        block_id=1,
        authority=FakeAuthority(),
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        writer_release_evidence=H,
    )
    paused = cli.run_operations_block(
        profile,
        plan,
        start,
        output=first,
        clock=first_clock,
        dispatch=synthetic_dispatch(first_clock, capture(None, 429)),
        epoch=H,
        pause_requested=lambda: first_clock.now_ns() >= 2_000_000,
        **common,
    )
    assert paused["disposition"] == "PAUSED_CLEAN"
    snapshot = io.metadata(io.read(first / "snapshot.json"))
    assert snapshot["controller"]["resume_eligible"]
    assert snapshot["controller"]["cooldown_delay_ms"] == 30_000
    assert snapshot["controller"]["charged_data_attempts"] == 1
    before = {
        str(p.relative_to(first)): c.sha(io.read(p)).hex()
        for p in first.rglob("*")
        if p.is_file()
    }
    second_clock = FakeClock(wall_offset_ns=1_000_000_000)
    second = tmp_path / "second"
    resumed = cli.run_operations_block(
        profile,
        plan,
        start,
        output=second,
        clock=second_clock,
        dispatch=synthetic_dispatch(second_clock),
        epoch="2" * 64,
        predecessor=first,
        continuation_authority=H,
        **common,
    )
    assert resumed["disposition"] == "COMPLETED"
    assert resumed["blocks"][0]["status"] == "INCOMPLETE"  # split sample cannot qualify
    assert resumed["blocks"][0]["duration_ns"] is None
    assert resumed["blocks"][0]["rates"]["all_attempts_per_s"] is None
    events = list(j.read_events(second, o.digest(start)))
    starts = [e for e in events if e["kind"] == "ATTEMPT_STARTED"]
    assert [e["body"]["attempt"] for e in starts] == [1, 2]
    assert starts[-1]["body"]["started_mono_ns"] >= 30_000_000_000
    final = io.metadata(io.read(second / "snapshot.json"))
    assert final["controller"]["charged_data_attempts"] == 2
    assert [p["retryable"] for p in final["controller"]["recent"]] == [True, False]
    assert before == {
        str(p.relative_to(first)): c.sha(io.read(p)).hex()
        for p in first.rglob("*")
        if p.is_file()
    }

    # Both mismatch and a still-active predecessor are rejection paths; no file
    # may be adopted on the strength of digest-shaped strings alone.
    with pytest.raises(c.Stage12Error):
        r.clean_continuation(
            first,
            {**start, "client_git_sha": "2" * 40},
            profile,
            plan,
            authority=FakeAuthority(),
            new_segment_authority=H,
            now_ns=0,
            work_factory=lambda: iter(rows),
            verify_receipt=lambda *_: None,
        )
    with pytest.raises(c.Stage12Error, match="AUTHORITY"):
        r.clean_continuation(
            first,
            start,
            profile,
            plan,
            authority=FakeAuthority("predecessor_termination"),
            new_segment_authority=H,
            now_ns=0,
            work_factory=lambda: iter(rows),
            verify_receipt=lambda *_: None,
        )
    assert before == {
        str(p.relative_to(first)): c.sha(io.read(p)).hex()
        for p in first.rglob("*")
        if p.is_file()
    }


def test_T11_T14_multiple_closed_blocks_keep_campaign_totals_and_prefixes(tmp_path):
    import copy
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_operations_v2 import inputs, rebind, FakeClock, KEY
    from test_stage12_public_scheduler import synthetic_dispatch

    profile, plan, start, rows, runtime = inputs(2)
    first_block = plan["blocks"][0]
    first_block["observation_ids"] = [1]
    for key in (
        "data_observations",
        "data_attempts",
        "active_duration_ms",
        "storage_bytes",
        "event_count",
    ):
        first_block["budget"][key] //= 2
    next_block = copy.deepcopy(first_block)
    next_block.update(block_id=2, observation_ids=[2], transition_from=1)
    plan["blocks"].append(next_block)
    rows[1]["block_id"] = 2
    rebind(profile, plan, start, rows)
    common = dict(
        work_factory=lambda: iter(rows),
        authority=FakeAuthority(),
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters={},
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        writer_release_evidence=H,
    )
    first_clock = FakeClock()
    first = tmp_path / "block_one"
    paused = cli.run_operations_block(
        profile,
        plan,
        start,
        output=first,
        block_id=1,
        clock=first_clock,
        dispatch=synthetic_dispatch(first_clock),
        epoch=H,
        **common,
    )
    assert paused["disposition"] == "PAUSED_CLEAN"
    assert paused["campaign_counts"]["planned_data"]["value"] == 2
    assert paused["campaign_counts"]["unprocessed_data"]["value"] == 1
    second_clock = FakeClock(wall_offset_ns=1_000_000_000)
    second = tmp_path / "block_two"
    completed = cli.run_operations_block(
        profile,
        plan,
        start,
        output=second,
        block_id=2,
        clock=second_clock,
        dispatch=synthetic_dispatch(second_clock),
        epoch="2" * 64,
        predecessor=first,
        continuation_authority=H,
        **common,
    )
    assert completed["disposition"] == "COMPLETED"
    assert len(completed["blocks"]) == len(completed["segment_snapshot_hashes"]) == 2
    assert completed["campaign_counts"]["durable_valid_data"]["value"] == 2
    inventory = list(j.read_array(second / "attempt_inventory.json"))
    assert {row["path"].split("/")[1] for row in inventory} == {
        f"{i:020d}" for i in (1, 2)
    }


def test_T12_known_sealed_receipts_are_checked_without_promoting_history(tmp_path):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operational_audit as oa,
    )

    _, root, (_, _, start, _, _) = run_offline(tmp_path)
    verified = []

    def check(directory, begin):
        name = audit.name_for(begin["call"], begin["attempt"])
        audit.reopen(
            directory, name, validator=cli.public_shapes, context=oa.DataContext()
        )
        verified.append(begin["call"])
        return True

    result = r.unclean_reconciliation(root, o.digest(start), verify_known=check)
    assert sorted(verified) == [1, 2]
    assert result["known_sealed_receipts_verified"] == 2
    assert result["disposition"] == "RECOVERY_BLOCKED" and result["snapshot"] is None
    assert result["begins_charged"]["value"] is None


@pytest.mark.parametrize("status", [None, 429])
@pytest.mark.parametrize(
    "delay_at", ["fresh_runtime_and_monitoring", "runtime_preflight", "journal_open"]
)
def test_F01_T02_T11_rebase_after_delayed_gates_and_open(
    tmp_path, monkeypatch, status, delay_at
):
    from dataclasses import replace
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as scheduler,
    )
    from test_stage12_public_operations_v2 import inputs, FakeClock
    from test_stage12_public_scheduler import synthetic_dispatch, repair_common
    from test_stage12_public_operational_audit import capture

    p, plan, start, rows, runtime = inputs(1)
    clock1, first = FakeClock(), tmp_path / "first"
    failure = (
        capture(None, 429)
        if status
        else replace(
            capture(),
            outcome="TECHNICAL_FAILURE_RETRYABLE",
            reason="TIMEOUT",
            status=None,
        )
    )
    paused = cli.run_operations_block(
        p,
        plan,
        start,
        output=first,
        clock=clock1,
        dispatch=synthetic_dispatch(clock1, failure),
        epoch=H,
        pause_requested=lambda: clock1.now_ns() >= 2_000_000,
        **repair_common(rows, runtime),
    )
    assert paused["disposition"] == "PAUSED_CLEAN"
    old_hashes = {
        str(path.relative_to(first)): c.sha(io.read(path)).hex()
        for path in first.rglob("*")
        if path.is_file()
    }
    ledger = list(j.read_array(first / "work_ledger.json"))
    delay = ledger[0]["retry_delay_ms"] * 1_000_000
    clock, seen = FakeClock(wall_offset_ns=1_000_000_000), {}

    class SlowGate(FakeAuthority):
        def require(self, purpose, evidence_sha256, context):
            super().require(purpose, evidence_sha256, context)
            if purpose == delay_at:
                clock.advance(40_000_000_000)

    original_open = j.Journal.open_segment

    def delayed_open(self, *args, **kw):
        if delay_at == "journal_open":
            clock.advance(40_000_000_000)
        return original_open(self, *args, **kw)

    monkeypatch.setattr(j.Journal, "open_segment", delayed_open)
    original_coordinator = scheduler.Coordinator

    class ObservedCoordinator(original_coordinator):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            seen.update(
                opened=self.opened_ns,
                start=self.next_start_ns,
                emit=self.next_emit_ns,
                overloads=list(self.overloads),
            )

    monkeypatch.setattr(scheduler, "Coordinator", ObservedCoordinator)
    second = tmp_path / "second"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        output=second,
        clock=clock,
        dispatch=synthetic_dispatch(clock),
        epoch="2" * 64,
        predecessor=first,
        continuation_authority=H,
        **repair_common(rows, runtime, SlowGate()),
    )
    events = [e for e in j.read_events(second, o.digest(start)) if e["segment_id"] == 2]
    opened = next(e["mono_ns"] for e in events if e["kind"] == "SEGMENT_OPEN")
    started = next(
        e["body"]["started_mono_ns"] for e in events if e["kind"] == "ATTEMPT_STARTED"
    )
    emitted = next(
        e["body"]["entered_mono_ns"] for e in events if e["kind"] == "EMISSION"
    )
    assert opened >= 40_000_000_000 and seen["opened"] == opened
    assert seen["start"] == seen["emit"] == opened + o.interval(p["states"][0]["rate"])
    assert started - opened >= max(delay, 30_000_000_000 if status else 0)
    assert emitted >= seen["emit"]
    assert seen["overloads"] == ([(opened, (1, 1))] if status else [])
    assert report["disposition"] == "COMPLETED"
    assert old_hashes == {
        str(path.relative_to(first)): c.sha(io.read(path)).hex()
        for path in first.rglob("*")
        if path.is_file()
    }
    assert r.replay(j.read_events(second, o.digest(start)))["closed"]


def test_F02_T11_required_control_blocks_advance_but_same_block_retry_resumes(tmp_path):
    import copy
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from test_stage12_public_operations_v2 import inputs, rebind, FakeClock
    from test_stage12_public_scheduler import synthetic_dispatch, repair_common
    from test_stage12_public_operational_audit import Control, recipe, capture

    p, plan, start, rows, runtime = inputs(2)
    rows[1].update(work_id=3, block_id=2)
    rows.insert(
        1,
        dict(
            work_id=2,
            block_id=1,
            kind="SERVICE_CONTROL",
            fixture_id=None,
            result_limit=None,
            repetition=None,
            recipe_id=1,
            retry_spacing_key=H,
        ),
    )
    plan["control_recipes"] = [recipe()]
    b1 = plan["blocks"][0]
    b1["observation_ids"] = [1, 2]
    for key in (
        "data_observations",
        "data_attempts",
        "active_duration_ms",
        "storage_bytes",
        "event_count",
    ):
        b1["budget"][key] //= 2
    b2 = copy.deepcopy(b1)
    b2.update(block_id=2, observation_ids=[3], transition_from=1)
    b1["budget"].update(required_control_observations=1, control_http_attempts=5)
    plan["blocks"].append(b2)
    plan["budgets"].update(required_control_observations=1, control_http_attempts=5)
    rebind(p, plan, start, rows)
    clock1, control_done = FakeClock(), []

    def first_dispatch(work, target, hooks):
        result = synthetic_dispatch(
            clock1, capture(None, 500) if work["kind"] == "SERVICE_CONTROL" else None
        )(work, target, hooks)
        if work["kind"] == "SERVICE_CONTROL":
            control_done.append(True)
        return result

    common = repair_common(rows, runtime)
    common["control_adapters"] = {1: Control()}
    first = tmp_path / "first"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=first,
        clock=clock1,
        dispatch=first_dispatch,
        epoch=H,
        pause_requested=lambda: bool(control_done),
        **common,
    )
    assert result["disposition"] == "PAUSED_CLEAN"
    assert list(j.read_array(first / "work_ledger.json"))[1]["state"] == "RETRY_DUE"
    common["block_id"] = 2
    clock = FakeClock(wall_offset_ns=1_000_000_000)
    rejected = tmp_path / "rejected"
    with pytest.raises(c.Stage12Error):
        cli.run_operations_block(
            p,
            plan,
            start,
            output=rejected,
            clock=clock,
            dispatch=lambda *_: pytest.fail("advance forbidden"),
            epoch="2" * 64,
            predecessor=first,
            continuation_authority=H,
            **common,
        )
    assert not rejected.exists()
    common["block_id"] = 1
    resumed = tmp_path / "resumed"
    seen = []

    def success(work, target, hooks):
        seen.append(work["work_id"])
        return synthetic_dispatch(
            clock, capture(c.canonical({"synthetic_index": "test"}))
        )(work, target, hooks)

    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=resumed,
        clock=clock,
        dispatch=success,
        epoch="2" * 64,
        predecessor=first,
        continuation_authority=H,
        **common,
    )
    assert result["disposition"] == "PAUSED_CLEAN" and seen == [2]
    assert (
        list(j.read_array(resumed / "work_ledger.json"))[1]["state"]
        == "DURABLE_SUCCESS"
    )
    common["block_id"] = 2
    final_clock = FakeClock(wall_offset_ns=40_000_000_000)
    final = tmp_path / "final"
    result = cli.run_operations_block(
        p,
        plan,
        start,
        output=final,
        clock=final_clock,
        dispatch=synthetic_dispatch(final_clock),
        epoch="3" * 64,
        predecessor=resumed,
        continuation_authority=H,
        **common,
    )
    assert result["disposition"] == "COMPLETED"
    assert all(
        row["state"] == "DURABLE_SUCCESS"
        for row in j.read_array(final / "work_ledger.json")
    )


def test_F02_T11_ledger_totality_allows_only_truly_unused_reserves():
    from test_stage12_public_operations_v2 import inputs

    _, plan, _, rows, _ = inputs(1, monitored=True)
    reserved = plan["blocks"][0]["reserved_control_ids"]
    ledger = [
        dict(work_id=w["work_id"], state="DURABLE_SUCCESS", charged_ordinals=[1])
        for w in rows
    ]
    item = next(x for x in ledger if x["work_id"] in reserved)
    for state in ("UNBEGUN", "UNUSED_RESERVED_CONTROL"):
        item.update(state=state, charged_ordinals=[])
        assert r.required_work_complete(plan, lambda: iter(rows), lambda: iter(ledger))
    item.update(state="RETRY_DUE", charged_ordinals=[1])
    assert not r.required_work_complete(plan, lambda: iter(rows), lambda: iter(ledger))
    item.update(state="DURABLE_SUCCESS")
    ledger[-1].update(state="UNBEGUN", charged_ordinals=[])
    assert not r.required_work_complete(plan, lambda: iter(rows), lambda: iter(ledger))

"""Invented bounded population mechanisms; never a protected population run."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path

import pytest
from stage12_b2_synthetic import World, H, KEY, offline as offline
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_inventory as m,
    s12_b2_contract as b,
    s12_b2_operations as o,
    s12_b2_planning as planning,
    s12_b2_pipeline as pipe,
    s12_b2_reporting as reporting,
    s12_public_journal as old,
    s12_retrieval_contract as c,
    s12_storage as io,
    s12_response as response,
)


def test_streamed_105805_rows_cross_64mib_exact_hash(tmp_path):
    # One 69MiB file, not 105805 attempts or files. Fixed <=1KiB row memory.
    path = tmp_path / "population.json"
    h = hashlib.sha256()
    with path.open("xb") as f:
        os.chmod(path, 0o600)
        for raw in (b"[",):
            f.write(raw)
            h.update(raw)
        for i in range(105805):
            raw = (b"," if i else b"") + b.canonical({"id": i, "invented": "x" * 664})[
                :-1
            ]
            f.write(raw)
            h.update(raw)
        f.write(b"]\n")
        h.update(b"]\n")
    size = path.stat().st_size
    assert 64 * 2**20 < size < 80 * 2**20
    with pytest.raises(c.Stage12Error):
        list(old.read_array(path))
    assert (
        o.manifest_digest(m.read_array(path, max_bytes=size, max_rows=105805))
        == h.hexdigest()
    )
    with pytest.raises(c.Stage12Error):
        for _ in m.read_array(path, max_bytes=size, max_rows=105804):
            pass
    with pytest.raises(c.Stage12Error):
        next(m.read_array(path, max_bytes=size - 1, max_rows=105805))


@pytest.mark.parametrize(
    "mutation", ["contents", "permissions", "directory", "ancestor", "symlink"]
)
def test_reader_detects_configured_path_and_original_change(tmp_path, mutation):
    ancestor = tmp_path / "a"
    root = ancestor / "b"
    ancestor.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    path = root / "rows.json"
    io.write(path, b.canonical([{"i": 1}, {"i": 2}]))
    rows = m.read_array(path, max_bytes=1024, max_rows=2)
    assert next(rows) == {"i": 1}
    if mutation == "contents":
        path.write_bytes(b.canonical([{"i": 1}, {"i": 3}]))
    elif mutation == "permissions":
        path.chmod(0o644)
    elif mutation == "directory":
        root.rename(ancestor / "old")
        root.mkdir(mode=0o700)
        io.write(path, b.canonical([{"i": 1}, {"i": 2}]))
    elif mutation == "ancestor":
        ancestor.rename(tmp_path / "old")
        ancestor.mkdir(mode=0o700)
        root.mkdir(mode=0o700)
        io.write(path, b.canonical([{"i": 1}, {"i": 2}]))
    else:
        path.rename(root / "original")
        path.symlink_to(root / "original")
    with pytest.raises((c.Stage12Error, OSError)):
        list(rows)


@pytest.mark.parametrize("mutation", ["added", "missing", "contents", "symlink"])
def test_bounded_order_rechecks_exact_membership(tmp_path, mutation):
    root = tmp_path / "segment" / "events"
    root.parent.mkdir(mode=0o700)
    root.mkdir(mode=0o700)
    io.write(root / "b", b"old")
    io.write(root / "a", b"old")
    rows = m.ordered_files(root, max_files=2, max_scratch_bytes=2**20)
    assert next(rows).name == "a"
    if mutation == "added":
        io.write(root / "c", b"new")
    elif mutation == "missing":
        (root / "b").unlink()
    elif mutation == "contents":
        (root / "b").write_bytes(b"NEW")
    else:
        (root / "b").unlink()
        (root / "b").symlink_to(root / "a")
    with pytest.raises((c.Stage12Error, OSError)):
        list(rows)


def narrow_slots(w, maximum):
    window = deepcopy(w.records.get(w.window_hash, "window_plan"))
    schedule = deepcopy(
        w.records.get(window["planned_segment_plan_sha256"], "window_segment_plan")
    )
    for campaign in schedule["planned_campaigns"]:
        if campaign["workload_kind"] == "FULL_C":
            for slot in campaign["segment_slots"]:
                slot["max_attempts"] = maximum
    window["planned_segment_plan_sha256"] = w.put(schedule)
    w.window_hash = w.put(window)
    w.selection_hash = planning.bind_window(
        w.records,
        window["calibration_plan_sha256"],
        w.window_hash,
        owner=lambda: None,
        secret_guard=lambda _: None,
    )


def continue_inputs(w, values, first):
    profile, plan, start, science, admission, rows = values
    snap = b.parse(io.read(first / "snapshot.json"), o.SNAPSHOT)
    admission = deepcopy(admission)
    admission.update(
        segment_nonce=w.nonce(),
        epoch_id=w.nonce(),
        segment_id=2,
        predecessor_closure_sha256=snap["segment_closure_sha256"],
    )
    release = w.put(
        {
            "schema_version": "stage12_writer_release_authority_b2_v1",
            "campaign_id": start["campaign_id"],
            "segment_nonce": admission["segment_nonce"],
            "issuer_delegation_sha256": H,
            "valid_from": "2025-01-01T00:00:00.000000Z",
            "valid_until": "2027-01-01T00:00:00.000000Z",
            "purpose": "WRITER_TERMINATION_AND_HANDOFF",
        }
    )
    admission["bootstrap_acquisition_sha256"] = pipe.prepare_bootstrap(
        w.root / "bootstrap_second",
        records=w.records,
        raw_factory=lambda: (lambda: w.records.raw(H),),
        clock=w.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=admission["segment_nonce"],
        epoch_id=admission["epoch_id"],
        authority=w.gate,
        authority_hash=H,
        writer_release_evidence=release,
        secret_guard=lambda raw: response.secret_guard(raw, KEY),
        previous_hash=snap["bootstrap_acquisition_sha256"],
    )
    w.releases[admission["segment_nonce"]] = release
    return profile, plan, start, science, admission, rows


def test_segment_cap_drains_one_then_resumes_same_intent_and_completes(tmp_path):
    w = World(tmp_path)
    narrow_slots(w, 1)
    report, values = w.run("first")
    assert report["disposition"] == "PAUSED_CLEAN"
    assert report["counts"]["begins_charged"]["value"] == 1
    assert report["counts"]["durable_valid_data"]["value"] == 1
    next_values = continue_inputs(w, values, tmp_path / "first")
    report, _ = w.run("second", inputs=next_values, predecessor=tmp_path / "first")
    assert report["disposition"] == "COMPLETED"
    assert report["counts"]["begins_charged"]["value"] == 2
    assert report["counts"]["durable_valid_data"]["value"] == 2
    assert (tmp_path / "second/_SEGMENT_SEALED").exists()


def test_prefix_receipts_cannot_repair_earlier_unknown(tmp_path):
    # An exact projected index must leave a prefix begin with no final unknown,
    # even though a later original receipt is valid in the same-stage index.
    w = World(tmp_path)
    _, values = w.run()
    profile, plan, start, science, admission, rows = values
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_audit as audit

    def verify(work, final):
        unit = (
            tmp_path
            / "segment/attempts"
            / f"{work['work_id']:020d}_{final['attempt']:02d}"
        )
        receipt, _, _ = audit.reopen(unit, **w.rules.kwargs())
        assert (
            b.sha(io.read(unit / "receipt.json")).hex()
            == final["receipt_inventory_sha256"]
        )
        return receipt

    index = reporting.Index(
        tmp_path / "prefix.sqlite",
        lambda: recovery.events(tmp_path / "segment", start, plan),
        lambda: iter(rows),
        verify,
        max_bytes=profile["resources"]["fixed_campaign_disk_bound_bytes"],
    )
    try:
        begin = next(e for e in index.all() if e["kind"] == "BEGIN_DURABLE")
        prefix = index.prefix(begin["seq"])
        assert prefix.verified(begin["body"]["work_id"], 1) is None
        first = next(
            r for r in prefix.ledger() if r["work_id"] == begin["body"]["work_id"]
        )
        assert first["state"] == "UNKNOWN_DELIVERY"
        assert all(r["state"] == "DURABLE_SUCCESS" for r in index.ledger())
    finally:
        index.close()


@pytest.mark.parametrize("n", [0, 1, 3, 101, 1025])
def test_exact_spill_statistics_match_shared_uint64_nearest_ranks(tmp_path, n):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_reporting as old_stats,
    )

    names = tuple(o.TYPES["Latencies"])
    values = [
        (names[i % len(names)], [0, 1, 2**63, 2**64 - 1, 7][i % 5]) for i in range(n)
    ]
    works = [{"work_id": i + 1} for i in range(max(1, (n + 19) // 20))]
    index = reporting.Index(
        tmp_path / "stats.sqlite",
        lambda: iter(()),
        lambda: iter(works),
        lambda *_: None,
        max_bytes=4 * 2**20,
    )
    calls = []

    def source():
        calls.append(True)
        yield from values

    try:
        got = index.exact_statistics(source, names)
        assert len(calls) == 1
        assert got == old_stats.exact_stats(lambda: iter(values), names)
        assert index.exact_statistics(lambda: iter(()), names) == old_stats.exact_stats(
            lambda: iter(()), names
        )
    finally:
        index.close()


@pytest.mark.parametrize("kind", ["memory", "storage"])
def test_outer_runtime_allocation_rejects_campaign_before_work_access(tmp_path, kind):
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    w = World(tmp_path)
    profile, plan, start, science, admission, rows = w.inputs()
    spec = {
        "profile_sha256": w.put(profile),
        "plan_sha256": w.put(plan),
        "start_sha256": w.put(start),
        "scientific_start_sha256": w.put(science),
        "admission_sha256": w.put(admission),
        "work_path": "MUST_NOT_BE_READ",
        "work_file_sha256": H,
        "segment_path": None,
        "predecessor_path": None,
        "runtime_inventory_sha256": H,
        "pause_after_ms": 0,
        "control_adapters": {},
    }
    settings = {
        "campaign": spec,
        "phase_memory_bytes": profile["resources"]["job_memory_bytes"],
        "phase_disk_capacity_bytes": plan["budgets"]["storage_bytes"],
    }
    settings[
        "phase_memory_bytes" if kind == "memory" else "phase_disk_capacity_bytes"
    ] -= 1
    fake = SimpleNamespace(
        settings=settings, records=w.records, check_deadline=lambda: None
    )
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_CAMPAIGN_CAPACITY"):
        runtime.RuntimePort.campaign_inputs(fake)


def test_retry_charge_uses_slot_without_resetting_ordinal_or_delay(tmp_path):
    w = World(tmp_path, count=1)
    narrow_slots(w, 1)
    report, values = w.run(
        "first",
        dispatch=lambda work, target, hooks: w.dispatch(
            work, target, hooks, status=500
        ),
    )
    assert report["disposition"] == "PAUSED_CLEAN"
    ledger = list(m.read_role(tmp_path / "first", "work_ledger.json", values[1]))
    assert ledger[0]["state"] == "RETRY_DUE" and ledger[0]["charged_ordinals"] == [1]
    next_values = continue_inputs(w, values, tmp_path / "first")
    report, _ = w.run("second", inputs=next_values, predecessor=tmp_path / "first")
    ledger = list(m.read_role(tmp_path / "second", "work_ledger.json", values[1]))
    assert report["disposition"] == "COMPLETED"
    assert ledger[0]["state"] == "DURABLE_SUCCESS" and ledger[0][
        "charged_ordinals"
    ] == [1, 2]
    assert report["counts"]["begins_charged"]["value"] == 2


def test_index_exit_revalidates_original_and_derived_work(tmp_path):
    rows = [{"work_id": 1}]
    index = reporting.Index(
        tmp_path / "changed.sqlite",
        lambda: iter(()),
        lambda: iter(rows),
        lambda *_: None,
        max_bytes=2**20,
    )
    index.db.execute(
        "update work set body=?", (b.canonical({"work_id": 1, "invented": True}),)
    )
    with pytest.raises(c.Stage12Error, match="B2_REPORT_SOURCE_CHANGED"):
        index.close()
    index = reporting.Index(
        tmp_path / "original.sqlite",
        lambda: iter(()),
        lambda: iter(rows),
        lambda *_: None,
        max_bytes=2**20,
    )
    rows[0]["changed"] = True
    with pytest.raises(c.Stage12Error, match="B2_REPORT_SOURCE_CHANGED"):
        index.close()


def test_array_deadline_and_row_bounds_reject_honestly(tmp_path):
    path = tmp_path / "rows.json"
    io.write(path, b.canonical([{"i": 1}, {"i": 2}]))

    def expired():
        raise c.Stage12Error("SYNTHETIC_DEADLINE")

    with pytest.raises(c.Stage12Error, match="SYNTHETIC_DEADLINE"):
        list(m.read_array(path, max_bytes=1024, max_rows=2, check=expired))
    io.write(tmp_path / "large.json", b.canonical([{"padding": "x" * 65536}]))
    with pytest.raises(c.Stage12Error):
        list(m.read_array(tmp_path / "large.json", max_bytes=70000, max_rows=1))


def test_missing_state_observation_keeps_report_incomplete(tmp_path):
    # Component-only invented event transcript: required STATE_CHANGE evidence
    # cannot be replaced by an unrelated resource observation.
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery

    w = World(tmp_path)
    _, values = w.run()
    profile, plan, start, _, _, rows = values
    source = list(recovery.events(tmp_path / "segment", start, plan))
    prefix = [
        e
        for e in source
        if e["seq"]
        <= b.parse(io.read(tmp_path / "segment/measurement_report.json"))[
            "input_last_event_seq"
        ]
    ]
    for event in prefix:
        if event["kind"] == "RESOURCE" and event["body"]["cause"] == "STATE_CHANGE":
            event["body"]["cause"] = "QUEUE_ADD"
    index = reporting.Index(
        tmp_path / "missing_state.sqlite",
        lambda: iter(prefix),
        lambda: iter(rows),
        lambda *_: None,
        max_bytes=2**20,
    )
    try:
        report = reporting.measurement(
            index,
            profile,
            plan,
            start,
            attempt_inventory=H,
            administrative_spent={"operations": 1, "bytes": 1, "duration_ms": 1},
            disposition="COMPLETED",
        )
        assert not report["resource_sampling_complete"]
        assert not report["report_complete"]
    finally:
        index.close()


def test_real_selection_verifier_accepts_finite_slot_below_whole_plan(tmp_path):
    w = World(tmp_path)
    narrow_slots(w, 1)
    profile, plan, start, science, admission, rows = w.inputs()
    selection, _ = planning.load_selection(
        w.records,
        w.selection_hash,
        w.catalog,
        authority=w.gate.authority,
        scratch=tmp_path / "selection_check.sqlite",
    )
    slot = planning.verify_workload(
        w.records,
        w.selection_hash,
        selection,
        w.catalog,
        plan,
        lambda: iter(rows),
        admission,
        authority=w.gate,
    )
    assert slot["max_attempts"] == 1 < plan["budgets"]["data_attempts"]


def test_slot_utc_boundary_is_exclusive_before_every_dispatch(tmp_path):
    from test_stage12_b2_evidence import gate_fixture

    w = World(tmp_path)
    gate, preflight, nonce, state = gate_fixture(w)
    gate.admit(preflight, nonce)
    gate.slot = {"dispatch_from": w.clock.utc(), "dispatch_until": w.clock.utc()}
    with pytest.raises(c.Stage12Error, match="B2_SEGMENT_EXPIRED"):
        gate.before_dispatch()


def test_changed_segment_admission_cannot_choose_another_slot(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery

    w = World(tmp_path)
    _, values = w.run(pause_requested=lambda: True)
    profile, plan, start, science, admission, rows = values
    changed = dict(admission, segment_id=2)
    (tmp_path / "segment/segment_admission.json").write_bytes(b.canonical(changed))
    with pytest.raises(c.Stage12Error):
        recovery.reopen(
            tmp_path / "segment",
            start,
            profile,
            plan,
            works=lambda: iter(rows),
            verify_receipt=lambda *_: None,
            scratch=tmp_path / "changed_admission.sqlite",
            authority=w.gate,
        )


def test_runtime_deadline_callback_reaches_sole_writer(tmp_path):
    import threading

    w = World(tmp_path)
    observed_threads = set()
    report, _ = w.run(
        phase_check=lambda: observed_threads.add(threading.current_thread().name),
        phase_remaining_seconds=lambda: 10.0,
    )
    assert report["disposition"] == "COMPLETED"
    assert (
        "stage12-public-writer" in observed_threads and "MainThread" in observed_threads
    )


@pytest.mark.parametrize("stage", ["statistics", "snapshot", "opener"])
def test_cumulative_expiry_during_closure_never_returns_success(
    tmp_path, monkeypatch, stage
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery

    w = World(tmp_path)
    values = w.inputs()

    def expire():
        w.clock.advance(values[1]["budgets"]["active_duration_ms"] * 1000000)

    if stage == "statistics":
        original = reporting.Index.exact_statistics

        def statistics(self, *args):
            expire()
            return original(self, *args)

        monkeypatch.setattr(reporting.Index, "exact_statistics", statistics)
    elif stage == "snapshot":
        original = io.write

        def write(path, raw):
            if path.name == "snapshot.json":
                expire()
            return original(path, raw)

        monkeypatch.setattr(io, "write", write)
    else:
        original = recovery.reopen

        def opener(*args, **kwargs):
            expire()
            return original(*args, **kwargs)

        monkeypatch.setattr(recovery, "reopen", opener)
    with pytest.raises((c.Stage12Error, OSError)):
        w.run(inputs=values)
    if stage != "opener":
        assert not (tmp_path / "segment/_SEGMENT_SEALED").exists()
        assert not (tmp_path / "segment/_WRITER_RELEASED.json").exists()
    # An already persisted seal in the opener case is not a timed successful
    # execution. The real opener failed and the runner returned no success.


@pytest.mark.parametrize("preparation", ["storage", "original_events"])
def test_delayed_predecessor_preparation_expires_and_aborts_writer(
    tmp_path, monkeypatch, preparation
):
    import time

    w = World(tmp_path)
    _, values = w.run("first", pause_requested=lambda: True)
    next_values = continue_inputs(w, values, tmp_path / "first")
    created = []
    original_init = old.Writer.__init__

    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created.append(self)

    monkeypatch.setattr(old.Writer, "__init__", initialize)
    injected = []

    def expire_once():
        if created and not injected:
            injected.append(True)
            w.clock.advance(values[1]["budgets"]["active_duration_ms"] * 1000000)

    if preparation == "storage":
        original = old.tree_bytes

        def storage(path, *args, **kwargs):
            if path == tmp_path / "first":
                expire_once()
            return original(path, *args, **kwargs)

        monkeypatch.setattr(old, "tree_bytes", storage)
    else:
        original = m.ordered_files

        def ordered(path, *args, **kwargs):
            if path == tmp_path / "first/events":
                expire_once()
            yield from original(path, *args, **kwargs)

        monkeypatch.setattr(m, "ordered_files", ordered)
    with pytest.raises(c.Stage12Error, match="B2_PHASE_DEADLINE"):
        w.run("second", inputs=next_values, predecessor=tmp_path / "first")
    assert injected and len(created) == 1
    writer = created[0]
    for _ in range(20):
        if not writer.thread.is_alive():
            break
        time.sleep(0.005)
    assert writer.closed and not writer.thread.is_alive()
    assert not (tmp_path / "second/_SEGMENT_SEALED").exists()
    assert not (tmp_path / "second/_WRITER_RELEASED.json").exists()


@pytest.mark.parametrize("secondary", ["close", "deadline"])
def test_initiating_report_failure_survives_cleanup(tmp_path, monkeypatch, secondary):
    w = World(tmp_path)
    values = w.inputs()

    def fail_report(*args, **kwargs):
        raise c.Stage12Error("SYNTHETIC_REPORT_PRIMARY")

    monkeypatch.setattr(reporting, "measurement", fail_report)
    original = reporting.Index.close

    def close(index):
        if secondary == "deadline":
            w.clock.advance(values[1]["budgets"]["active_duration_ms"] * 1000000)
        try:
            original(index)
        finally:
            if secondary == "close":
                raise c.Stage12Error("SYNTHETIC_CLOSE_SECONDARY")

    monkeypatch.setattr(reporting.Index, "close", close)
    with pytest.raises(c.Stage12Error, match="SYNTHETIC_REPORT_PRIMARY"):
        w.run(inputs=values)
    assert not (tmp_path / "segment/_SEGMENT_SEALED").exists()
    assert not (tmp_path / "segment/_WRITER_RELEASED.json").exists()


def ordering_runtime(w, monkeypatch):
    """Real non-preparation RuntimePort, with only invented existing adapters."""
    from test_stage12_b2_runtime import configuration, campaign_port
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    config, _, _ = configuration(
        w, phase="run-campaign", mode="EXACT_AUTHORIZED_DISPATCH"
    )
    w.runtime = {
        "version": "stage12_development_runtime_inventory_v1",
        "population_scope": b.SYNTHETIC,
        "python_version": runtime.platform.python_version(),
        "platform": runtime.platform.system(),
        "source_inventory_sha256": b.digest(config["runtime"]["source_files"]),
        "continuous_service_state": "NOT_VERIFIED",
        "resource_sampling_is_service_monitoring": False,
        "scientific_identity_verified": False,
    }
    port, config = campaign_port(
        w, "run-campaign", w.inputs(), output=w.root / "runtime_segment"
    )
    port.bind_session(
        "run-campaign",
        config,
        w.root / "runtime_segment",
        w.root / "runtime_scratch",
        H,
    )
    seen = {"calls": 0, "journal": False, "peak_bytes": 0}
    original = port.reconcile_generation

    def observe():
        seen["calls"] += 1
        temporary = Path(config["runtime"]["temporary_root"])
        seen["journal"] |= any(temporary.glob(".b2-order-*/members.sqlite-journal"))
        result = original()
        seen["peak_bytes"] = max(seen["peak_bytes"], result["bytes"])
        return result

    monkeypatch.setattr(port, "reconcile_generation", observe)
    return port, config, seen


def test_linked_ordering_database_and_journal_use_observed_runtime_namespace(
    tmp_path, monkeypatch
):
    w = World(tmp_path)
    earlier = tmp_path / "earlier_segment"
    io.reserve(earlier)
    io.reserve(earlier / "events")
    io.write(earlier / "events/a", b"invented predecessor evidence")
    port, config, seen = ordering_runtime(w, monkeypatch)
    try:
        temporary = Path(config["runtime"]["temporary_root"])
        before = port.reconcile_generation()["bytes"]
        rows = m.ordered_files(earlier / "events", max_files=1, max_scratch_bytes=2**20)
        assert next(rows).name == "a"
        scratch = list(temporary.glob(".b2-order-*"))
        assert len(scratch) == 1 and not list(tmp_path.glob(".b2-order-*"))
        assert seen["journal"] and seen["peak_bytes"] > before
        calls = seen["calls"]
        port.observe_ordering(False)
        assert seen["calls"] == calls  # No recursive scan per row/check.
        w.clock.advance(config["runtime"]["phase_generation_check_ms"] * 1000000)
        port.observe_ordering(False)
        assert seen["calls"] == calls + 1
        calls = seen["calls"]
        assert list(rows) == []
        assert seen["calls"] == calls + 1  # Forced before cleanup, same clock.
        assert not scratch[0].exists()
        assert port.reconcile_generation()["bytes"] == before
    finally:
        port.close()


def test_nonpreparation_linked_spill_pressure_is_checked_before_cleanup(
    tmp_path, monkeypatch
):
    w = World(tmp_path)
    earlier = tmp_path / "earlier_segment"
    io.reserve(earlier)
    io.reserve(earlier / "events")
    io.write(earlier / "events/a", b"invented")
    port, config, seen = ordering_runtime(w, monkeypatch)
    temporary = Path(config["runtime"]["temporary_root"])
    rows = m.ordered_files(earlier / "events", max_files=1, max_scratch_bytes=2**20)
    assert next(rows).name == "a"
    scratch = next(temporary.glob(".b2-order-*"))
    pressure = scratch / "invented-linked-pressure"
    with pressure.open("xb") as stream:
        pressure.chmod(0o600)
        for _ in range(config["runtime"]["phase_generation_bound_bytes"] // 65536):
            stream.write(b"x" * 65536)
    # No fake time advancement: forced in-lifetime observation must see it.
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
        list(rows)
    assert scratch.exists() and pressure.exists()  # failed scratch preserved
    with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_BOUND"):
        port.close()
    assert port._closed


def test_ordering_source_failure_preserves_scratch_and_primary(tmp_path, monkeypatch):
    w = World(tmp_path)
    earlier = tmp_path / "earlier_segment"
    io.reserve(earlier)
    io.reserve(earlier / "events")
    io.write(earlier / "events/a", b"invented")
    port, config, seen = ordering_runtime(w, monkeypatch)
    temporary = Path(config["runtime"]["temporary_root"])
    try:
        rows = m.ordered_files(earlier / "events", max_files=1, max_scratch_bytes=2**20)
        next(rows)
        (earlier / "events/a").write_bytes(b"changed")
        with pytest.raises(c.Stage12Error, match="B2_INVENTORY_CHANGED"):
            list(rows)
        scratch = list(temporary.glob(".b2-order-*"))
        assert len(scratch) == 1 and (scratch[0] / "members.sqlite").exists()
        assert port.reconcile_generation()["bytes"] > 0
    finally:
        port.close()


def test_runtime_scoped_umask_keeps_active_library_files_private_and_restores(
    tmp_path, monkeypatch
):
    import stat
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    prior = os.umask(0o022)
    try:
        w = World(tmp_path)
        port, config, seen = ordering_runtime(w, monkeypatch)
        temporary = Path(config["runtime"]["temporary_root"])
        db = duckdb.connect(str(temporary / "invented.duckdb"))
        db.execute("set memory_limit='32MB'")
        db.execute("set threads=1")
        db.execute("create table invented(value integer)")
        writer = pq.ParquetWriter(
            temporary / "invented.parquet", pa.schema([("value", pa.int32())])
        )
        writer.write_table(pa.table({"value": pa.array([1], type=pa.int32())}))
        try:
            assert not runtime._PHASE_LOCK.acquire(blocking=False)
            active = [path for path in temporary.iterdir() if path.is_file()]
            assert len(active) >= 3  # live DuckDB, WAL and Arrow output
            assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in active)
            assert port.reconcile_generation()["bytes"] > 0
        finally:
            writer.close()
            db.close()
            port.close()
        assert os.umask(0o022) == 0o022
        assert runtime._PHASE_LOCK.acquire(blocking=False)
        runtime._PHASE_LOCK.release()
    finally:
        os.umask(prior)


def test_runtime_bind_failure_restores_umask_and_releases_phase_lock(tmp_path):
    from test_stage12_b2_runtime import configuration, pin, port as make_port
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    prior = os.umask(0o022)
    try:
        w = World(tmp_path)
        config, _, grants = configuration(w)
        pin(w, config, grants)
        port = make_port(w, config)
        io.write(tmp_path / "already_exists", b"invented")
        with pytest.raises(c.Stage12Error, match="B2_RUNTIME_GENERATION_EXISTS"):
            port.bind_session(
                "plan-calibration",
                config,
                tmp_path / "already_exists",
                tmp_path / "scratch",
                H,
            )
        assert port._closed and os.umask(0o022) == 0o022
        assert runtime._PHASE_LOCK.acquire(blocking=False)
        runtime._PHASE_LOCK.release()
    finally:
        os.umask(prior)

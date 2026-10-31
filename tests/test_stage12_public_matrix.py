"""Invented public matrix tests; network/process/credential access is denied."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as m
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_response as v
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing import stage12_operations_cli as entry
from test_stage12_public_operations_v2 import (
    H,
    KEY,
    FakeClock,
    FakeAuthority,
    inputs,
    rebind,
    offline,  # noqa: F401 -- autouse network/process/credential denial fixture
)  # noqa:F401
from test_stage12_public_operational_audit import capture
from stage12_synthetic import body


def configuration():
    from test_stage12_public_runtime import config_test_only

    cfg = config_test_only()
    cfg.update(version=m.VERSION, maximum_attempts=2960, active_seconds=7200)
    cfg["sources"]["size_allowance"] = H
    cfg["capability"] = m.binding(H)
    p = cfg["campaigns"][0]["profile"]
    p["resources"]["allocated_disk_bytes"] = 512 * 2**30
    p["resources"]["writer_guard_ms"] = 5000
    p["states"][0]["connections"] = 2
    p["states"][0]["rate"] = {"num": 1, "den": 1}
    cfg["resources"] = deepcopy(p["resources"])
    cfg["campaigns"] = m.build_campaigns(
        p,
        window_start=cfg["window_start"],
        window_end=cfg["window_end"],
        selection_sha256=H,
    )
    cfg["public_validation_sha256"] = o.digest(v.descriptor(v.FAMILY_VERSION))
    return cfg


def test_matrix_exact_union_deep_ids_coverage_and_aggregate_bounds():
    cfg = configuration()
    r.validate_config(cfg)
    assert len(cfg["campaigns"]) == 11
    rows = [w for item in cfg["campaigns"] for w in item["work"]]
    data = [w for w in rows if w["kind"] == "DATA"]
    assert len(data) == 576 and len(rows) == 584
    deep = {f["fixture_id"] for f in probe.fixtures() if f["deep_case"]}
    assert len(deep) == 16
    assert {w["fixture_id"] for w in data if w["result_limit"] > 10} == deep
    assert all(
        sum(
            w["fixture_id"] == f["fixture_id"] and w["result_limit"] == size
            for w in data
        )
        == 2
        for f in probe.fixtures()
        for size in (1, 3, 5, 10)
    )
    totals = m.validate_matrix(cfg)
    assert totals == {
        "attempts": 2920,
        "events": 206000,
        "storage_bytes": 480 * 2**30,
        "phase_duration_ms": 5180000,
    }
    assert (
        o.digest(probe.fixtures())
        == cfg["campaigns"][0]["plan"]["fixture_inventory_sha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "drop_case",
        "replace_deep",
        "reorder_size",
        "repetition",
        "extra_recipe",
        "postal_target",
        "rate",
        "connections",
        "period",
        "writer",
        "unbounded_phase",
        "aggregate_storage",
        "size_record",
        "warning_version",
        "wrong_kind",
    ],
)
def test_matrix_rejects_exact_scope_and_budget_drift(mutation):
    cfg = configuration()
    item = cfg["campaigns"][0]
    if mutation == "drop_case":
        item["work"].pop()
    elif mutation == "replace_deep":
        cfg["campaigns"][8]["work"][0]["fixture_id"] = next(
            f["fixture_id"] for f in probe.fixtures() if not f["deep_case"]
        )
    elif mutation == "reorder_size":
        cfg["campaigns"][0], cfg["campaigns"][2] = (
            cfg["campaigns"][2],
            cfg["campaigns"][0],
        )
    elif mutation == "repetition":
        item["work"][0]["repetition"] = 1
    elif mutation == "extra_recipe":
        cfg["campaigns"][-1]["plan"]["control_recipes"][0]["purpose"] = "AUTH_CHECK"
    elif mutation == "postal_target":
        cfg["capability"]["additional_checks"][0]["core"]["postalcode"] = "2139"
    elif mutation == "rate":
        item["profile"]["states"][0]["rate"]["num"] = 2
    elif mutation == "connections":
        item["profile"]["states"][0]["connections"] = 3
    elif mutation == "period":
        item["profile"]["resource_sample_period_ms"] = 101
    elif mutation == "writer":
        cfg["resources"]["writer_guard_ms"] = 6000
        item["profile"]["resources"]["writer_guard_ms"] = 6000
    elif mutation == "unbounded_phase":
        item["plan"]["budgets"]["active_duration_ms"] = 7200000
    elif mutation == "aggregate_storage":
        cfg["resources"]["allocated_disk_bytes"] = 60 * 2**30
    elif mutation == "size_record":
        cfg["capability"]["operator_size_evidence_sha256"] = "0" * 64
    elif mutation == "warning_version":
        cfg["public_validation_sha256"] = o.digest(v.descriptor())
    elif mutation == "wrong_kind":
        item["plan"]["experiment_kind"] = "CAPABILITY"
    with pytest.raises((c.Stage12Error, KeyError)):
        r.validate_config(cfg)


def test_extra_checks_exact_targets_and_omitted_boundary_stays_ineligible():
    values = m.checks()
    assert "postalcode=02139" in values[0]["target_ascii"]
    assert "postalcode=SW1A%201AA" in values[1]["target_ascii"]
    assert (
        "%2B" in values[2]["target_ascii"]
        and "%25" in values[2]["target_ascii"]
        and "%0A" in values[2]["target_ascii"]
    )
    assert all("boundary.country=" in x["target_ascii"] for x in values)
    x = deepcopy(values[0]["core"])
    x["boundary_country"] = None
    with pytest.raises((c.Stage12Error, TypeError, ValueError)):
        s11.core_bytes(x)
    assert len(probe.fixtures()) == 64


def test_no_control_acquires_berlin_warning_exception():
    from test_stage12_public_runtime import warning_body

    adapter = m.CheckAdapter(m.recipes(H)[0])
    with pytest.raises(c.Stage12Error):
        adapter.validate(adapter.recipe, c.canonical(warning_body()))
    accepted = io.metadata(adapter.validate(adapter.recipe, body([])))
    assert (
        accepted["candidate_count"] == 0
        and accepted["request_target_sha256"] == m.checks()[0]["target_sha256"]
    )
    changed = deepcopy(adapter.recipe)
    changed["recipe_sha256"] = "0" * 64
    with pytest.raises(c.Stage12Error):
        adapter.target(changed)


def test_global_envelope_attempts_time_and_both_pacers_span_fragments():
    clock = FakeClock()
    e = r.Envelope(clock, 3, 5, matrix=True)

    class Hooks:
        def started(self, ns):
            pass

        def emit(self, write, check):
            check()
            write()

    a = e.wrap(Hooks())
    b = e.wrap(Hooks())
    writes = []
    e.charge()
    a.started(0)
    a.emit(lambda: writes.append(1), lambda: None)
    e.charge()
    with pytest.raises(c.Stage12Error):
        b.started(999999999)
    clock.wait_until(10**9)
    b.started(clock.now_ns())
    b.emit(lambda: writes.append(2), lambda: None)
    with pytest.raises(c.Stage12Error):
        a.emit(lambda: writes.append(3), lambda: None)
    assert writes == [1, 2] and e.attempts == 2
    e.charge()
    with pytest.raises(c.Stage12Error):
        e.charge()
    clock.wait_until(5 * 10**9)
    with pytest.raises(c.Stage12Error):
        e.check()
    with pytest.raises(c.Stage12Error):
        r.Envelope(FakeClock(), 2960, 7200)


def test_control_capture_reopen_keyless_only_after_seal_and_secret_guard(tmp_path):
    recipe = m.recipes(H)[0]
    adapter = m.CheckAdapter(recipe)
    root = tmp_path / "control"
    begin = {
        "schema_version": o.CONTROL_BEGIN,
        "campaign_start_sha256": H,
        "profile_sha256": H,
        "plan_sha256": H,
        "segment_id": 1,
        "work_id": 1,
        "attempt": 1,
        "recipe_sha256": recipe["recipe_sha256"],
        "request_target_sha256": c.sha(adapter.target(recipe)).hex(),
        "started_utc": "2026-01-01T00:00:00.000000Z",
    }
    a.begin_control(root, begin)
    record = a.transport_record(
        {"work_id": 1}, 1, capture(body([])), "2026-01-01T00:00:01+00:00"
    )
    finish, _ = a.finish_control(root, record, body([]), recipe, adapter, key=KEY)
    assert finish["outcome"] == "CONTROL_SUCCESS"
    assert a.reopen_control(root, adapter, key=None) == finish
    with pytest.raises(c.Stage12Error):
        a.reopen_control(root, adapter, key=None, sealed=False)
    with pytest.raises(c.Stage12Error):
        a.control_result(record, body([]), recipe, adapter, None)
    result = a.control_result(record, KEY, recipe, adapter, KEY)
    assert result[2] == "SECRET_ECHO_DETECTED" and result[3] is None
    (root / "raw.zst").write_bytes(b"corrupted")
    with pytest.raises(c.Stage12Error):
        a.reopen_control(root, adapter, key=None)


def test_matrix_exit_requires_complete_closure_not_rate_qualification():
    cfg = configuration()
    base = {
        "full_frozen_capability_matrix_completed": True,
        "completed_phases": [x["label"] for x in cfg["campaigns"]],
        "qualified_public_rates": [],
    }
    assert entry.result_exit_status(cfg, base) == 0
    for key, value in [
        ("full_frozen_capability_matrix_completed", False),
        ("completed_phases", base["completed_phases"][:-1]),
        ("qualified_public_rates", [1]),
    ]:
        changed = {**base, key: value}
        assert entry.result_exit_status(cfg, changed) == 1


def test_actual_control_phase_capture_report_seal_and_original_reopen(tmp_path):
    cfg = configuration()
    item = cfg["campaigns"][-1]
    p, plan, rows = item["profile"], item["plan"], item["work"]
    _, _, start, _, runtime = inputs(0, rate=1)
    clock = r.Clock()
    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    hi = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    p["operator_allowance"].update(valid_from=lo, valid_until=hi)
    plan.update(window_start=lo, window_end=hi)
    start["created_utc"] = clock.utc()
    rebind(p, plan, start, rows)

    class Authority(FakeAuthority):
        def require(self, purpose, evidence, context):
            if purpose == "control_recipe":
                assert (
                    evidence == o.digest(m.check_descriptor())
                    and context in plan["control_recipes"]
                )
            elif purpose == "transport_profile":
                assert evidence == p["transport_profile_sha256"] and context == p
            else:
                super().require(purpose, evidence, context)

    targets = []

    def dispatch(work, target, hooks):
        assert target == m.CheckAdapter(
            plan["control_recipes"][work["recipe_id"] - 1]
        ).target(plan["control_recipes"][work["recipe_id"] - 1])
        hooks.started(clock.now_ns())
        hooks.emit(lambda: targets.append(target), lambda: None)
        value = capture(body([]))
        hooks.signal(200, value.outcome, value.reason, None)
        hooks.completed(value)
        return value

    root = tmp_path / "actual_control_phase"
    report = cli.run_operations_block(
        p,
        plan,
        start,
        work_factory=lambda: iter(rows),
        output=root,
        block_id=1,
        authority=Authority(),
        clock=clock,
        dispatch=dispatch,
        runtime_inventory=runtime,
        runtime_key=KEY,
        control_adapters=m.adapters(plan),
        monitor=None,
        free_bytes=lambda: 2**42,
        segment_authority=H,
        writer_exclusion_evidence=H,
        epoch=H,
        writer_release_evidence=H,
        public_validation=v.Validation(v.FAMILY_VERSION),
    )
    assert len(targets) == 8
    assert report["disposition"] == "COMPLETED" and report["report_complete"]
    block = r.reopen_completed(
        root,
        p,
        plan,
        start,
        validation_sha256=o.digest(v.descriptor(v.FAMILY_VERSION)),
        control_adapters=m.adapters(plan),
    )
    assert (
        block["counts"]["control_attempt_starts"]["value"] == 8
        and block["counts"]["durable_valid_data"]["value"] == 0
    )
    assert len(m.verify_controls(root, plan)) == 4
    assert (root / "_WRITER_RELEASED.json").exists()
    original = io.read(root / "attempts/call_0001_attempt_1/begin.json")
    value = io.metadata(original)
    value["request_target_sha256"] = "0" * 64
    (root / "attempts/call_0001_attempt_1/begin.json").write_bytes(c.canonical(value))
    with pytest.raises(c.Stage12Error):
        r.reopen_completed(
            root,
            p,
            plan,
            start,
            validation_sha256=o.digest(v.descriptor(v.FAMILY_VERSION)),
            control_adapters=m.adapters(plan),
        )


@pytest.mark.parametrize("stop_at", [None, 0, 3, 10])
def test_matrix_runtime_gates_reconciliation_and_shared_budget(
    monkeypatch, tmp_path, stop_at
):
    cfg = configuration()
    clock = FakeClock()
    cfg["output_directory"] = str(tmp_path / ("or2_" + H))
    monkeypatch.setattr(r, "OUTPUT_PARENT", tmp_path)
    monkeypatch.setattr(r, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.setattr(r.assets, "verify", lambda _: None)
    monkeypatch.setattr(
        r.subprocess,
        "check_output",
        lambda args, **kw: "a" * 40 if "rev-parse" in args else b"",
    )
    monkeypatch.setattr(r.resource, "setrlimit", lambda *a: None)
    monkeypatch.setattr(
        r, "runtime_inventory", lambda *a: {"scope": "SYNTHETIC_TEST_ONLY"}
    )
    monkeypatch.setattr(
        r.os,
        "statvfs",
        lambda _: type("Stat", (), {"f_bavail": 2**50, "f_frsize": 1})(),
    )
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_ONLY")
    monkeypatch.setenv("SLURM_MEM_PER_NODE", "6144")
    monkeypatch.setenv(
        "SAFE_PELIAS_API_KEY_FILE",
        str(Path.home() / ".config/safe-geocoding/pelias_api_key"),
    )
    monkeypatch.delenv("SAFE_PELIAS_API_KEY", raising=False)
    bundle = tmp_path / "bundle"
    io.reserve(bundle)
    for role in cfg["sources"]:
        io.write(
            bundle / (role + ".record"),
            b"SYNTHETIC TEST ONLY - NOT AN AUTHORITY RECORD",
        )
    review_raw = b"SYNTHETIC TEST ONLY REVIEW"
    io.write(bundle / "integration_review.md", review_raw)
    review = {
        "version": "stage12_public_integration_review_binding_v1",
        "scope": o.SCOPE,
        "disposition": "PASS",
        "configuration_sha256": o.digest(cfg),
        "report_sha256": c.sha(review_raw).hex(),
        "source_files": [
            {"path": "bundle/integration_review.md", "sha256": c.sha(review_raw).hex()}
        ],
    }
    attempted = []
    reopened = []
    charged = []

    class Hooks:
        def started(self, ns):
            pass

        def signal(self, *a):
            pass

        def completed(self, *a):
            pass

        def emit(self, write, check):
            check()
            write()

    def send(target, profile, key, ops, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: charged.append(target), lambda: None)
        return capture(body([]))

    monkeypatch.setattr(r.transport, "send", send)

    def run(profile, plan, start, **kw):
        index = len(attempted)
        attempted.append(index)
        io.reserve(kw["output"])
        for w in kw["work_factory"]():
            clock.advance(10**9)
            kw["dispatch"](w, b"/SYNTHETIC_ONLY", Hooks())
        return {"disposition": "COMPLETED", "report_complete": True}

    monkeypatch.setattr(cli, "run_operations_block", run)

    def reopen(*args, **kw):
        index = len(reopened)
        reopened.append(index)
        return {"synthetic_block_index": index}

    monkeypatch.setattr(r, "reopen_completed", reopen)
    monkeypatch.setattr(
        m, "gate", lambda block, *args: block["synthetic_block_index"] != stop_at
    )
    monkeypatch.setattr(m, "verify_controls", lambda *a: [])
    reconciled = []

    def reconcile(*a):
        reconciled.append(True)
        return {"actual_attempts": 584}

    monkeypatch.setattr(m, "reconcile", reconcile)
    summary = r.execute(
        cfg,
        bundle=bundle,
        review=review,
        review_hash=H,
        repository=tmp_path,
        git_sha="a" * 40,
        key_provider=lambda: r.transport.Secret.checked(KEY),
        clock=clock,
    )
    expected_phases = 11 if stop_at is None else stop_at + 1
    assert len(attempted) == len(reopened) == expected_phases
    assert (
        summary["attempts_dispatched_or_uncertain"]
        == sum(len(x["work"]) for x in cfg["campaigns"][:expected_phases])
        == len(charged)
    )
    assert summary["qualified_public_rates"] == []
    assert summary["full_frozen_capability_matrix_completed"] == (stop_at is None)
    assert bool(reconciled) == (stop_at is None)


@pytest.mark.parametrize(
    "failure", [None, "receipt_change", "second_stage_mutation", "deadline"]
)
def test_global_reconciliation_fixed_pair_counts_and_fresh_boundaries(
    tmp_path, monkeypatch, failure
):
    """Unit of aggregate joins; phase opener is an explicit checked test double.

    Actual production opener/control durability is exercised separately above.
    Original payloads are real compressed temporary files on every pair read.
    """
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_audit as data_audit,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    cfg = configuration()
    root = tmp_path / "matrix"
    io.reserve(root)
    io.write(root / "configuration.json", c.canonical(cfg))
    raw = body([])
    compressed = response.compress(raw)
    rows_by_root = {}
    opens = []
    reads = []
    ticks = []
    for item in cfg["campaigns"]:
        phase = root / item["label"]
        io.reserve(phase)
        io.reserve(phase / "work")
        io.reserve(phase / "attempts")
        io.write(
            phase / "campaign_start.json",
            c.canonical({"explicit_synthetic_start": item["label"]}),
        )
        io.write(
            phase / "campaign_report.json",
            c.canonical({"explicit_synthetic_report": item["label"]}),
        )
        block = {"explicit_synthetic_block": item["label"]}
        io.write(
            root / (item["label"] + "_CAPABILITY_GATE.json"),
            c.canonical(
                {
                    "configuration_sha256": o.digest(cfg),
                    "block_report_sha256": o.digest(block),
                    "control_comparisons": [],
                    "disposition": "PASS_EXACT_PHASE_NOT_RATE_QUALIFICATION",
                }
            ),
        )
        events = []
        for w in item["work"]:
            io.write(phase / "work" / f"{w['work_id']:020d}.json", c.canonical(w))
            name = data_audit.name_for(w["work_id"], 1)
            a_root = phase / "attempts" / name
            io.reserve(a_root)
            io.write(a_root / (name + ".zst"), compressed)
            receipt = c.canonical({"test_only_work": w["work_id"]})
            io.write(a_root / (name + "_receipt.json"), receipt)
            events.append(
                {
                    "kind": "ATTEMPT_FINALIZED",
                    "body": {
                        "work_id": w["work_id"],
                        "attempt": 1,
                        "receipt_inventory_sha256": c.sha(receipt).hex(),
                    },
                }
            )
        rows_by_root[str(phase)] = events

    def reopen(phase, *a, **kw):
        opens.append(phase.name)
        if failure == "second_stage_mutation" and len(opens) > 11:
            raise c.Stage12Error("PUBLIC_PROBE_INPUT_IDENTITY_MISMATCH")
        return {
            "explicit_synthetic_block": phase.name,
            "counts": {"attempt_starts": {"value": len(rows_by_root[str(phase)])}},
        }

    # Gate hash binds the same exact test-double block, including counts.
    for item in cfg["campaigns"]:
        p = root / (item["label"] + "_CAPABILITY_GATE.json")
        gate = io.metadata(io.read(p))
        gate["block_report_sha256"] = o.digest(
            {
                "explicit_synthetic_block": item["label"],
                "counts": {"attempt_starts": {"value": len(item["work"])}},
            }
        )
        p.write_bytes(c.canonical(gate))
    monkeypatch.setattr(r, "reopen_completed", reopen)
    monkeypatch.setattr(m, "gate", lambda *a: True)
    monkeypatch.setattr(m, "verify_controls", lambda *a: [])
    monkeypatch.setattr(j, "read_events", lambda p, *a: iter(rows_by_root[str(p)]))

    def receipt(path, *a, **kw):
        reads.append(path)
        if failure == "receipt_change" and len(reads) == 1:
            name = path.name
            (path / (name + ".zst")).write_bytes(
                response.compress(body([{"invented": "bad"}]))
            )
        return {
            "application_payload_bytes": len(raw),
            "response_sha256": c.sha(raw).hex(),
        }

    monkeypatch.setattr(data_audit, "reopen", receipt)

    def check():
        ticks.append(1)
        if failure == "deadline" and len(ticks) > 20:
            raise c.Stage12Error("S12_PUBLIC_WINDOW_CLOSED")

    if failure:
        with pytest.raises(c.Stage12Error):
            m.reconcile(cfg, root, check)
    else:
        value = m.reconcile(cfg, root, check)
        assert value["actual_attempts"] == 584 and value["data_observations"] == 576
        assert (
            value["same_size_comparisons"] == 288
            and len(value["cross_size_comparisons"]) == 1024
        )
        assert all(x["equal"] for x in value["cross_size_comparisons"])
        assert len(reads) == 2048 and len(opens) == 22
        assert value["qualified_public_rates"] == []

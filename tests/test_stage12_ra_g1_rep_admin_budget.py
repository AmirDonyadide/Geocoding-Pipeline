"""REP-only budget successor; synthetic fixtures never issue live authority."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as monitor
from safe_geocoding_pipeline.preprocessing.stages import s12_storage
from test_s12_ra_g1_accounting import inputs
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_s12_ra_g1_core import H, G, binding, Authority, observation, original_observation
from test_stage12_ra_g1_production_binding import (  # noqa: F401
    private_source, production, installed_production_audit, materialize,
)

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location("rep_admin_" + name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


allocation = module("stage12_ra_g1_allocation")
preparer = module("stage12_prepare_ra_g1")
diagnostic = module("stage12_ra_g1_diagnostic")


def synthetic_adoption():
    # Deliberately invented hashes: this is not the retained authority original.
    return deepcopy(SYNTHETIC_ADOPTION)


SYNTHETIC_ADOPTION = {'additional_prospective_units': 128,
 'administrator_attestation': False,
 'adopted_representative_admin_seconds': {'binder_complete': 240,
                                          'collector': 120,
                                          'combined_binder_watchdog': 720,
                                          'factual_review': 480},
 'baseline': '2222222222222222222222222222222222222222',
 'binder_operational_publication_target_seconds': 180,
 'binder_remaining_suffix_target_seconds': 60,
 'cumulative_ceiling': 704,
 'direct_owner_detailed_statement_claimed': False,
 'existing_conditional_public_unconsumed': 2,
 'historical_job1811762': 'FAILED_INCOMPLETE_WAIT_RELEASE_CONTENT_PASS_LATE_PUBLICATION_NO_B_UNCHANGED',
 'independent_advisory_authentication': False,
 'input_manifest_sha256': '1111111111111111111111111111111111111111111111111111111111111111',
 'new_allocation_grant': {'consumed': 0,
                          'id': 'REPRESENTATIVE_ADMIN_BUDGET_SUCCESSOR_ONE',
                          'maximum': 1,
                          'only_after_focused_verification_and_all_current_gates': True,
                          'replacement_requeue_A_rerun': False},
 'no_new_public_or_protected_slots': True,
 'original_anchors_nonresetting': True,
 'original_recommendation_sha256': '1111111111111111111111111111111111111111111111111111111111111111',
 'previous_cumulative_ceiling': 576,
 'prior_charged_actual_or_possible': 512,
 'provenance': 'ACTUAL_USER_RELAY_OF_GPT6_ASTRA_ULTRA_RECOMMENDATION_UNDER_STANDING_HUMAN_DELEGATION',
 'public_operating_budgets_unchanged': True,
 'recorded_utc': '2026-11-10T06:16:57.603990+00:00',
 'remaining_assigned_prospectively': 192,
 'schema_version': 'stage12_advisory_delegated_rep_admin_budget_continuation_v1',
 'unchanged_seconds': {'B': 7200,
                       'processing': 8160,
                       'scheduler': 8400,
                       'terminal_verifier': 120},
 'unchanged_window_end': '2026-11-11T19:13:21.620987Z'}


def upgrade(value):
    result = deepcopy(value)
    result["version"] = allocation.REP_ADMIN_VERSION
    result["limits"] = deepcopy(allocation.REP_ADMIN_LIMITS)
    result["rep_admin_budget_adoption"] = synthetic_adoption()
    result["rep_admin_budget_adoption_sha256"] = allocation.digest(result["rep_admin_budget_adoption"])
    inv, totals = ac.compile_inventory(result["source_files"], result["accounting_inventory"]["backends"],
        allocation.SCOPE, bootstrap_successor=True, shared_lease_successor=True, rep_admin_successor=True)
    result["accounting_inventory"], result["accounting"] = inv, totals
    return result


def selected():
    sources, backends = inputs()
    _, prefix, _ = bootstrap_inputs()
    inv, totals = ac.compile_inventory(sources, backends, allocation.SCOPE,
        bootstrap_successor=True, shared_lease_successor=True, rep_admin_successor=True)
    value = dict(version=allocation.REP_ADMIN_VERSION, source_files=sources,
        accounting_inventory=inv, accounting=totals, source_sha=G,
        valid_from="2026-01-01T00:00:00.000000Z", valid_until="2026-01-02T00:00:00.000000Z",
        bootstrap_prefix_adoption=prefix, bootstrap_prefix_adoption_sha256=allocation.digest(prefix),
        rep_admin_budget_adoption=synthetic_adoption(), rep_admin_budget_adoption_sha256=allocation.digest(synthetic_adoption()))
    return preparer.resource_selection(value, policy_sha256=H, adoption_sha256=H,
        descriptor_inventory_sha256=H, graph_sha256=H, paths_sha256=H, implementation_review_sha256=H)


def test_new_selection_caps_and_conservation():
    new = selected()
    assert new["schema_version"] == a.REP_ADMIN_SELECTION
    stages = new["limits"]["stages"]
    assert [row["deadline_ms"] for row in stages[5:8]] == [120000, 480000, 240000]
    assert sum(row["creations"] for row in stages) == 184184
    assert stages[6]["creations"] == stages[7]["creations"] == 2008
    assert new["limits"]["monitor_rows"] == 16342
    assert new["limits"]["logical_write_bytes"] == 72 * 2**30
    assert new["limits"]["closure_reserve_bytes"] == 256 * 2**20
    assert allocation.LIMITS["review_seconds"] == 600 and allocation.LIMITS["binder_seconds"] == 120
    assert allocation.REP_ADMIN_LIMITS["review_seconds"] + allocation.REP_ADMIN_LIMITS["binder_seconds"] == 720


@pytest.mark.parametrize("phase,maximum", [(7,480000),(8,240000)])
def test_new_caps_inclusive_and_one_above_rejects(phase, maximum):
    value = selected()
    value["limits"]["stages"][phase - 1]["deadline_ms"] = maximum
    a.validate_selection(value)
    value["limits"]["stages"][phase - 1]["deadline_ms"] += 1
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(value)


def test_legacy_and_public_keep_original_caps():
    old, _, _ = bootstrap_inputs()
    old["limits"]["stages"][6]["deadline_ms"] = 600000
    a.validate_selection(old)
    assert "rep_admin_budget_policy_sha256" not in old
    for scope in ("REPRESENTATIVE_NO_SERVICE", "PUBLIC_SYNTHETIC_ONLY"):
        sources, backends = inputs()
        inv, _ = ac.compile_inventory(sources, backends, scope,
            bootstrap_successor=scope == "REPRESENTATIVE_NO_SERVICE", shared_lease_successor=True)
        assert inv["schema_version"] == ac.SHARED_LEASE_VERSION
        if scope == "REPRESENTATIVE_NO_SERVICE":
            assert [row["deadline_ms"] for row in inv["monitor_streams"] if row["phase_id"] in (7,8)] == [600000,120000]
        else:
            with pytest.raises(ac.AccountingError):
                ac.compile_inventory(sources, backends, scope, bootstrap_successor=True,
                    shared_lease_successor=True, rep_admin_successor=True)
    assert a.REP_ADMIN_POLICY not in contract.descriptors()
    for name, value in contract.descriptors().items():
        assert (ROOT / "docs/scientific_assets" / (name + ".json")).read_bytes() == a.c.canonical(value)


def test_accounting_monitor_transfer_and_both_poll_loops():
    sources, backends = inputs()
    old, old_totals = ac.compile_inventory(sources, backends, allocation.SCOPE,
        bootstrap_successor=True, shared_lease_successor=True)
    new, totals = ac.compile_inventory(sources, backends, allocation.SCOPE,
        bootstrap_successor=True, shared_lease_successor=True, rep_admin_successor=True)
    assert new["schema_version"] == ac.REP_ADMIN_VERSION
    assert sum(row["maximum_rows"] for row in old["monitor_streams"]) == sum(row["maximum_rows"] for row in new["monitor_streams"])
    assert [row["maximum_rows"] for row in new["monitor_streams"] if row["phase_id"] in (7,8)] == [962,482]
    waits = [row for row in new["cost_rows"] if row["component"] in ("REVIEW_WAIT_CHECKPOINTS","BINDER_RELEASE_WAIT_CHECKPOINTS")]
    assert [(r["stage_id"],r["check_calls"]) for r in waits] == [(7,1922),(8,962)]
    assert sum(r["invocations"] for r in new["cost_rows"] if r["component"] == "REP_ADMIN_ADOPTION_START_AND_ACTUAL_OPENER") == 16
    assert totals["original_read_calls"] > old_totals["original_read_calls"]
    assert ac.validate_inventory(new) == new
    bad = deepcopy(new)
    bad["schema_version"] = ac.SHARED_LEASE_VERSION
    with pytest.raises(ac.AccountingError):
        ac.validate_inventory(bad)


def test_new_input_rejects_mixed_resource_families():
    new = selected()
    diagnostic.validate_resource_family(diagnostic.REP_ADMIN_VERSION, new)
    with pytest.raises(RuntimeError):
        diagnostic.validate_resource_family(diagnostic.SHARED_LEASE_VERSION, new)
    old, _, _ = bootstrap_inputs()
    with pytest.raises(RuntimeError):
        diagnostic.validate_resource_family(diagnostic.REP_ADMIN_VERSION, old)


def test_real_wait_record_and_native_deadline_do_not_reset(tmp_path, monkeypatch):
    clock = [100]
    calls = []
    class Run:
        def check(self):
            calls.append(clock[0])
        def original(self, path):
            return allocation.canonical(dict(disposition="PASS"))
    path = tmp_path / "release.record"
    monkeypatch.setattr(allocation.time, "monotonic_ns", lambda: clock[0])
    def sleep(seconds):
        assert seconds == 0.25
        clock[0] += 250000000
    monkeypatch.setattr(allocation.time, "sleep", sleep)
    with pytest.raises(RuntimeError, match="RA_G1_REVIEW_TIMEOUT"):
        allocation.wait_record(Run(), path, deadline_ns=100 + 240 * 10**9)
    assert clock[0] == 100 + 240 * 10**9
    assert len(calls) == 961


def test_original_adoption_digest_provenance_and_fields_are_required():
    new = selected()
    value = synthetic_adoption()
    a.validate_rep_admin_adoption(value, new)
    for field in ("adopted_representative_admin_seconds", "original_anchors_nonresetting", "administrator_attestation"):
        bad = deepcopy(value)
        if field == "adopted_representative_admin_seconds":
            bad[field]["binder_complete"] += 1
        else:
            bad[field] = not bad[field]
        with pytest.raises(a.c.Stage12Error):
            a.validate_rep_admin_adoption(bad, new)


def test_actual_builder_writes_new_adoption_and_real_consumers_accept(request, monkeypatch):
    case = request.getfixturevalue("production")
    case.allocation = upgrade(case.allocation)
    data, objects = case.preparer.build(case.allocation, case.bootstrap, **case.kwargs)
    case.allocation["resource_selection_sha256"] = allocation.digest(objects["resource_selection"])
    case.controller.validate_selection(case.allocation)
    assert data["version"] == diagnostic.REP_ADMIN_VERSION
    assert objects["resource_selection"]["schema_version"] == a.REP_ADMIN_SELECTION
    assert case.allocation["rep_admin_budget_adoption_sha256"] in objects["resource_evidence"]["adoptions"]
    for outer, inv in [(allocation.SHARED_LEASE_VERSION, ac.REP_ADMIN_VERSION), (allocation.REP_ADMIN_VERSION, ac.SHARED_LEASE_VERSION)]:
        bad = deepcopy(case.allocation)
        bad["version"] = outer
        if inv == ac.SHARED_LEASE_VERSION:
            bad["accounting_inventory"], bad["accounting"] = ac.compile_inventory(bad["source_files"], bad["accounting_inventory"]["backends"], allocation.SCOPE, bootstrap_successor=True, shared_lease_successor=True)
        with pytest.raises((RuntimeError,a.c.Stage12Error)):
            case.controller.validate_selection(bad)
    run = case.controller.Run(case.allocation, stage="bind", stage_seconds=720)
    try:
        with installed_production_audit(case, run, monkeypatch):
            bundle = materialize(run, case, data, objects)
            actual = case.controller.parse(run.original(case.allocation["paths"]["input"]))
            case.diagnostic.validate_envelope(actual, G, for_execution=False)
            case.diagnostic.validate_workloads(actual)
            case.diagnostic.validate_resource_family(actual["version"], objects["resource_selection"])
            class Originals:
                def read(self, path, *, limit, original):
                    return run.original(path, limit=limit)
            with s12_storage.read_view(Originals()):
                case.diagnostic.validate_grants(actual, bundle)
            assert run.read_calls > 0 and run.write_bytes > 0 and run.creations > 0
    finally:
        run.close()


@pytest.mark.parametrize("mutate", [False, True])
def test_real_phase_session_requires_fresh_adoption_at_start_and_opener(tmp_path, mutate):
    chosen = selected()
    authority = Authority(chosen)
    original = synthetic_adoption()
    calls = []
    def reader(identity):
        calls.append(identity)
        return deepcopy(original)
    def factory(retain):
        def observed(kind):
            row = observation(chosen, enter=time.monotonic_ns(), kind=kind)
            row["phase_id"] = 8
            row["visible_identity_inventory_sha256"] = retain(original_observation(row))
            return {key: row[key] for key in ("readings", "counters", "native_visibility", "visible_identity_inventory_sha256")}
        return observed
    value = e.PhaseSession(authority=authority, binding=binding(chosen), selection=chosen,
        resource_evidence_root=tmp_path / "phase8", pids=(123,),
        counter_provider=lambda: {key: 0 for key in monitor.COUNTERS}, charge=lambda *args: None,
        check=lambda: None, deadline_ns=time.monotonic_ns() + 5 * 10**9, phase_id=8,
        admitted_process_provider=lambda: (123,), read_charge=lambda *args: None,
        observer_factory=factory, bootstrap_adoption_reader=reader)
    try:
        value.start()
        assert calls == [chosen["rep_admin_budget_adoption_sha256"]]
        value.require_start_acknowledged()
        if mutate:
            original["adopted_representative_admin_seconds"]["binder_complete"] -= 1
            with pytest.raises(a.c.Stage12Error):
                value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda: True)
            assert not value.completed and "worker_validation" not in value.records
        else:
            result, _ = value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda: True)
            assert result is True and value.completed
        assert len(calls) == 2
    finally:
        if not value.completed:
            value.abort()
        value.monitor.stop_event.set()
        value.monitor.thread.join(1)
        value.writer.thread.join(1)
        assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()


def test_actual_native_deadline_expires_at_original_240s_anchor(request, monkeypatch):
    case = request.getfixturevalue("production")
    chosen = upgrade(case.allocation)
    run = case.controller.Run(chosen, stage="bind", stage_seconds=720)
    try:
        anchor = case.controller.time.monotonic_ns()
        original_end = min(run.end, anchor + 240 * 10**9)
        run.active_scope_deadline = original_end
        clock = [anchor + 180 * 10**9]
        monkeypatch.setattr(case.controller.time, "monotonic_ns", lambda: clock[0])
        run.check()
        assert run.active_scope_deadline == original_end
        clock[0] = original_end - 1
        run.check()
        clock[0] = original_end
        with pytest.raises(RuntimeError, match="RA_G1_DEADLINE"):
            run.check()
        assert run.active_scope_deadline == original_end
    finally:
        run.close()


def test_bind_source_keeps_both_review_and_release_original_deadlines():
    import ast
    tree = ast.parse((ROOT / "scripts/stage12_ra_g1_allocation.py").read_text())
    bind_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "bind")
    ends = [node.value for node in bind_node.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "end" for target in node.targets)]
    assert len(ends) == 2
    assert "review_session.deadline" in ast.unparse(ends[0])
    assert "binding_session.deadline" in ast.unparse(ends[1])
    targets = [node for node in ast.walk(bind_node) if isinstance(node, ast.Call)
               and isinstance(node.func, ast.Name) and node.func.id == "wait_record"]
    assert len(targets) == 2
    assert all(any(kw.arg == "deadline_ns" and isinstance(kw.value, ast.Name)
                   and kw.value.id == "end" for kw in node.keywords) for node in targets)


@pytest.mark.parametrize("field", ["bytes", "creations"])
def test_new_family_keeps_non_b_failure_partitions(request, field):
    case = request.getfixturevalue("production")
    chosen = upgrade(case.allocation)
    run = case.controller.Run(chosen, stage="bind", stage_seconds=720)
    target = case.root / "must_not_exist.record"
    try:
        run.mkdir(case.root)
        assert run.byte_limit == 160 * 2**20 and run.creation_limit == 1024
        if field == "bytes":
            run.write_bytes = run.byte_limit
        else:
            run.creations = run.creation_limit
        with pytest.raises(RuntimeError):
            run.write(target, {"SYNTHETIC": True})
        assert not target.exists()
        assert chosen["limits"]["non_b_bytes"] == 240 * 2**20
        assert chosen["limits"]["non_b_creations"] == 1544
    finally:
        run.close()


def test_new_selection_and_all_six_nonlive_assets_remain_bounded():
    chosen = selected()
    assert len(a.c.canonical(chosen)) <= 8192
    exports = contract.descriptors(rep_admin_successor=True)
    for name in (a.REP_ADMIN_POLICY, a.REP_ADMIN_SELECTION, a.REP_ADMIN_ADOPTION, ac.REP_ADMIN_VERSION):
        value = exports[name]
        assert value["live_instance"] is False
        assert (ROOT / "docs/scientific_assets" / (name + ".json")).read_bytes() == a.c.canonical(value)
    for owner in (allocation, diagnostic):
        name = owner.REP_ADMIN_VERSION
        assert (ROOT / "docs/scientific_assets" / (name + ".json")).read_bytes() == owner.canonical(owner.descriptor(name))

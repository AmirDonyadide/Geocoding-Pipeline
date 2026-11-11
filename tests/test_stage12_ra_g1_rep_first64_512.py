"""Exact representative512 successor; every record here is synthetic, never live authority."""
from copy import deepcopy
from pathlib import Path
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution
from safe_geocoding_pipeline.preprocessing.stages import s12_storage
from test_s12_ra_g1_accounting import inputs
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_s12_ra_g1_core import H, G, Authority, binding, observation, original_observation
from test_stage12_ra_g1_rep_admin_budget import (
    allocation, preparer, diagnostic, upgrade as admin_upgrade,
    selected as historical_selected,
)
from test_stage12_ra_g1_production_binding import (  # noqa: F401
    private_source, production, installed_production_audit, materialize,
)

ROOT = Path(__file__).resolve().parents[1]


def synthetic_adoption():
    # Known baseline references identify the adopted design; recommendation hash is invented.
    return dict(schema_version=a.REP512_ADOPTION, scope="REPRESENTATIVE_NO_SERVICE",
        policy_sha256=allocation.digest(a.rep512_policy_descriptor()),
        original_recommendation_sha256=H, recorded_utc="2026-11-11T00:42:16.000000Z",
        baseline_source="982cc871169fcb8215c163b8ed141965c829cd20",
        baseline_manifest_sha256="d1d473f241a1192004349629701524f5872ba1130f50d1d467781b7de6645ceb",
        derivation_sha256="59fe61efaca6187ee954f0cc9126be44b1e1388badba87598a66e2bbf0299d83",
        provenance="ACTUAL_USER_RELAY_OF_GPT6_ASTRA_ULTRA_RECOMMENDATION_UNDER_STANDING_HUMAN_DELEGATION",
        administrator_attestation=False, direct_owner_numerical_statement_claimed=False,
        prospective_only=True, historical_346_unchanged=True, other_stage_caps_unchanged=True,
        public_protected_budgets_unchanged=True, workload_authority_issued=False)


def upgrade(value):
    result = admin_upgrade(value)
    result["version"] = allocation.REP512_VERSION
    result["rep_first64_512_adoption"] = synthetic_adoption()
    result["rep_first64_512_adoption_sha256"] = allocation.digest(synthetic_adoption())
    inv, caps = ac.compile_inventory(result["source_files"], result["accounting_inventory"]["backends"],
        allocation.SCOPE, bootstrap_successor=True, shared_lease_successor=True,
        rep_admin_successor=True, first64_512_successor=True)
    result["accounting_inventory"], result["accounting"] = inv, caps
    return result


def selected():
    sources, backends = inputs()
    _, prefix, _ = bootstrap_inputs()
    from test_stage12_ra_g1_rep_admin_budget import synthetic_adoption as old_adoption
    value = dict(version=allocation.REP512_VERSION, source_files=sources, source_sha=G,
        valid_from="2026-01-01T00:00:00.000000Z", valid_until="2026-01-02T00:00:00.000000Z",
        bootstrap_prefix_adoption=prefix, bootstrap_prefix_adoption_sha256=allocation.digest(prefix),
        rep_admin_budget_adoption=old_adoption(), rep_admin_budget_adoption_sha256=allocation.digest(old_adoption()),
        rep_first64_512_adoption=synthetic_adoption(),
        rep_first64_512_adoption_sha256=allocation.digest(synthetic_adoption()))
    value["accounting_inventory"], value["accounting"] = ac.compile_inventory(sources, backends,
        allocation.SCOPE, bootstrap_successor=True, shared_lease_successor=True,
        rep_admin_successor=True, first64_512_successor=True)
    return preparer.resource_selection(value, policy_sha256=H, adoption_sha256=H,
        descriptor_inventory_sha256=H, graph_sha256=H, paths_sha256=H, implementation_review_sha256=H)


def test_exact_coupled_bounds_and_unchanged_other_stages():
    old, new = historical_selected(), selected()
    assert new["schema_version"] == a.REP512_SELECTION
    first = new["limits"]["stages"][0]
    assert (first["deadline_ms"], first["events"], first["creations"]) == (512000, 26608, 77767)
    assert new["limits"]["application_counters"]["EVENT_FILE"] == 57237
    assert new["limits"]["application_counters"]["EXCLUSIVE_FILE"] == 204860
    assert sum(row["creations"] for row in new["limits"]["stages"]) == 204860
    assert sum(row["events"] for row in new["limits"]["stages"]) == 57237
    for left, right in zip(old["limits"]["stages"][1:], new["limits"]["stages"][1:], strict=True):
        for key in ("deadline_ms", "reserve_ms", "attempts", "events", "logical_write_bytes", "creations"):
            assert left[key] == right[key]
    assert new["limits"]["stages"][4]["creations"] == 30177
    for key in ("processing_ms", "scheduler_s", "attempts", "logical_write_bytes", "telemetry_chunks",
                "telemetry_bytes", "telemetry_creations", "monitor_rows", "monitor_bytes",
                "monitor_creations", "closure_reserve_bytes", "closure_reserve_creations"):
        assert old["limits"][key] == new["limits"][key]


def test_inclusive_512_and_legacy_boundary():
    new = selected()
    a.validate_selection(new)
    new["limits"]["stages"][0]["deadline_ms"] = 512001
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(new)
    old = historical_selected()
    old["limits"]["stages"][0]["deadline_ms"] = 346001
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(old)


@pytest.mark.parametrize("field", ["administrator_attestation", "direct_owner_numerical_statement_claimed",
    "prospective_only", "historical_346_unchanged", "other_stage_caps_unchanged",
    "public_protected_budgets_unchanged", "workload_authority_issued"])
def test_adoption_exact_boolean_scope_and_digest(field):
    chosen, value = selected(), synthetic_adoption()
    value[field] = not value[field]
    with pytest.raises(a.c.Stage12Error):
        a.validate_rep512_adoption(value, chosen)


@pytest.mark.parametrize("scope", ["PUBLIC_SYNTHETIC_ONLY", "DEVELOPMENT_ONLY", "DEVELOPMENT_LOCAL_PREPARATION"])
def test_no_public_or_protected_successor(scope):
    sources, backends = inputs()
    with pytest.raises(ac.AccountingError):
        ac.compile_inventory(sources, backends, scope, bootstrap_successor=True,
            shared_lease_successor=True, rep_admin_successor=True, first64_512_successor=True)
    value = selected()
    value["scope"] = scope
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(value)


def test_accounting_original_recompilation_and_mixed_family_rejection():
    sources, backends = inputs()
    inv, _ = ac.compile_inventory(sources, backends, allocation.SCOPE,
        bootstrap_successor=True, shared_lease_successor=True, rep_admin_successor=True,
        first64_512_successor=True)
    assert ac.validate_inventory(inv) == inv
    assert inv["monitor_streams"][0]["maximum_rows"] == 1026
    assert inv["rep_first64_512"]["phase1_events"] == 26608
    assert any(r["component"] == "REP512_ADOPTION_BINDER_DAG_REOPEN" for r in inv["cost_rows"])
    for key in ("schema_version", "sources", "rep_first64_512"):
        changed = deepcopy(inv)
        if key == "schema_version":
            changed[key] = ac.REP_ADMIN_VERSION
        elif key == "sources":
            changed[key][0]["bytes"] += 1
        else:
            changed[key]["first64_ms"] += 1
        with pytest.raises(ac.AccountingError):
            ac.validate_inventory(changed)


def test_family_and_phase_descriptor_compatibility():
    new, old = selected(), historical_selected()
    diagnostic.validate_resource_family(diagnostic.REP512_VERSION, new)
    diagnostic.validate_resource_family(diagnostic.REP_ADMIN_VERSION, old)
    for version, chosen in [(diagnostic.REP512_VERSION, old), (diagnostic.REP_ADMIN_VERSION, new)]:
        with pytest.raises(RuntimeError):
            diagnostic.validate_resource_family(version, chosen)
    assert diagnostic.descriptor(diagnostic.REP512_VERSION)["phases"][0]["proposed_phase_ms"] == 512000
    assert diagnostic.descriptor(diagnostic.REP_ADMIN_VERSION)["phases"][0]["proposed_phase_ms"] == 346000
    assert diagnostic.phases_for(diagnostic.REP512_VERSION)[0][2] == 1817
    for name, value in contract.descriptors(rep_admin_successor=True).items():
        assert (ROOT / "docs/scientific_assets" / (name + ".json")).read_bytes() == a.c.canonical(value)


def test_actual_builder_controller_audit_and_exact_validators(production, monkeypatch):  # noqa: F811 -- pytest fixture injection
    case = production
    case.allocation = upgrade(case.allocation)
    data, objects = case.preparer.build(case.allocation, case.bootstrap, **case.kwargs)
    case.allocation["resource_selection_sha256"] = allocation.digest(objects["resource_selection"])
    case.controller.validate_selection(case.allocation)
    assert data["version"] == diagnostic.REP512_VERSION
    assert data["configuration"]["campaigns"][0]["plan"]["sampling_budget"]["maximum_observations"] == 10242
    assert data["configuration"]["campaigns"][0]["plan"]["sampling_budget"]["additional_event_tokens"] == 20488
    assert data["limits"]["maximum_creations"] == 204860
    assert case.allocation["rep_first64_512_adoption_sha256"] in objects["resource_evidence"]["adoptions"]
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
            assert run.read_calls and run.write_bytes and run.creations
    finally:
        run.close()


@pytest.mark.parametrize("field", ["events", "creations", "deadline_ms", "logical_write_bytes"])
def test_new_family_rejects_underfunded_phase(field):
    value = selected()
    value["limits"]["stages"][0][field] -= 1
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(value)


@pytest.mark.parametrize("field", ["EVENT_FILE", "EXCLUSIVE_FILE"])
def test_new_family_rejects_underfunded_global_counter(field):
    value = selected()
    value["limits"]["application_counters"][field] -= 1
    with pytest.raises(a.c.Stage12Error):
        a.validate_selection(value)


@pytest.mark.parametrize("encoded", [False, True])
@pytest.mark.parametrize("mutate", [False, True])
def test_real_session_revalidates_original_512_adoption(tmp_path, encoded, mutate):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as monitor
    from test_stage12_ra_g1_rep_admin_budget import synthetic_adoption as admin_adoption
    chosen = selected()
    authority = Authority(chosen)
    original, admin = synthetic_adoption(), admin_adoption()
    calls = []
    def reader(identity):
        calls.append(identity)
        value = original if identity == chosen["rep_first64_512_adoption_sha256"] else admin
        return allocation.canonical(value) if encoded else deepcopy(value)
    def factory(retain):
        def observed(kind):
            row = observation(chosen, enter=time.monotonic_ns(), kind=kind)
            row["phase_id"] = 8
            row["visible_identity_inventory_sha256"] = retain(original_observation(row))
            return {key: row[key] for key in ("readings", "counters", "native_visibility", "visible_identity_inventory_sha256")}
        return observed
    value = execution.PhaseSession(authority=authority, binding=binding(chosen), selection=chosen,
        resource_evidence_root=tmp_path / "phase8", pids=(123,),
        counter_provider=lambda: {key: 0 for key in monitor.COUNTERS}, charge=lambda *args: None,
        check=lambda: None, deadline_ns=time.monotonic_ns() + 5 * 10**9, phase_id=8,
        admitted_process_provider=lambda: (123,), read_charge=lambda *args: None,
        observer_factory=factory, bootstrap_adoption_reader=reader)
    try:
        value.start()
        value.require_start_acknowledged()
        assert calls == [chosen["rep_first64_512_adoption_sha256"], chosen["rep_admin_budget_adoption_sha256"]]
        if mutate:
            original["prospective_only"] = False
            with pytest.raises(a.c.Stage12Error):
                value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda: True)
            assert not value.completed
        else:
            opened, _ = value.freeze_and_open(frozen_data_inventory_sha256=H, actual_opener=lambda: True)
            assert opened is True and value.completed
        assert calls.count(chosen["rep_first64_512_adoption_sha256"]) == 2
    finally:
        if not value.completed:
            value.abort()
        value.monitor.stop_event.set()
        value.monitor.thread.join(1)
        value.writer.thread.join(1)
        assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()

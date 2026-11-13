"""TEST_ONLY operating successor: real runtime guards and ownership remain."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_environment_launch as gate
import stage12_ra_g1_terminal_parent as parent
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows


def selected_window(scope=windows.SCOPES[0]):
    return dict(version=windows.SIMPLE_WINDOW_VERSION, scope=scope,
        valid_from=windows.SIMPLE_WINDOW_START, valid_until=windows.SIMPLE_WINDOW_END,
        policy_sha256=windows.digest(windows.simple_descriptor()),
        owner_authority_sha256="1"*64, grant_nonce="2"*64)


@pytest.mark.parametrize("scope,remaining", [(windows.SCOPES[0],10320),(windows.SCOPES[1],1920)])
def test_actual_window_runtime_reserves_and_no_preparation_clock(scope, remaining):
    value=selected_window(scope)
    exact=windows.epoch_ns(windows.SIMPLE_WINDOW_END)-remaining*10**9
    assert windows.validate_window(value,scope=scope,now_epoch_ns=exact,
                                   required_remaining_seconds=remaining) is value
    with pytest.raises(RuntimeError):
        windows.validate_window(value,scope=scope,now_epoch_ns=exact+1,
                                required_remaining_seconds=remaining)
    descriptor=windows.selected_descriptor(value)
    assert "collection_preparation_seconds" not in descriptor
    assert descriptor["collection_controller_seconds"]==1800
    assert descriptor["post_collection_review_seconds"]==120
    assert windows.discriminator_descriptor()["collection_preparation_seconds"]==600
    assert windows.discriminator_descriptor()["complete_admission_reserve_seconds"]==10920
    parent.validate_cli_window(dict(window=value),handoff_window_successor=False,
                               discriminator_window_successor=True)
    with pytest.raises(RuntimeError):
        parent.validate_cli_window(dict(window=value),handoff_window_successor=False)


@pytest.mark.parametrize("key,value",[("version",windows.DISCRIMINATOR_WINDOW_VERSION),
    ("policy_sha256",windows.digest(windows.discriminator_descriptor())),
    ("valid_from",windows.DISCRIMINATOR_WINDOW_START),
    ("valid_until","2026-11-15T19:13:21.620987Z"), ("grant_nonce","0"*64)])
def test_window_rejects_mixed_stale_or_extended_binding(key,value):
    selected=selected_window();selected[key]=value
    with pytest.raises(RuntimeError):
        windows.validate_window(selected,scope=windows.SCOPES[0],
            now_epoch_ns=windows.epoch_ns(windows.SIMPLE_WINDOW_START),required_remaining_seconds=10320)


def helper():
    path=ROOT/"scripts/stage12_ra_g1_task_assets/prearmed_handoff.py"
    spec=importlib.util.spec_from_file_location("test_simple_ownership",path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def ownership(module, simple):
    cfg=dict(schema_version=module.SIMPLE_CATALOG_SCHEMA if simple else module.CATALOG_SCHEMA,
             job_id="123")
    value=dict(schema_version=module.ROLE_OWNERSHIP if simple else "stage12_root_precharged_handoff_vouchers_v1",
        source_sha=module.SOURCE,job_id="123",selection_sha256="1"*64,
        resource_selection_sha256="2"*64,configuration_scope_sha256="3"*64,
        orchestrator_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        roles=sorted(module.ROLES) if simple else module.ROLES)
    value.update({"decision_delta_sha256":"4"*64} if simple else {"ledger_reservation_id":"HISTORICAL"})
    return cfg,value


@pytest.mark.parametrize("simple",[False,True])
def test_actual_ownership_validator_preserves_legacy_and_new_exact_identity(simple):
    module=helper();cfg,value=ownership(module,simple)
    module.validate_role_ownership(value,cfg,"1"*64,"2"*64,"3"*64,"4"*64)
    for key in ("source_sha","job_id","selection_sha256","resource_selection_sha256",
                "configuration_scope_sha256","orchestrator_sha256"):
        changed=deepcopy(value);changed[key]="9"*64
        with pytest.raises(RuntimeError):
            module.validate_role_ownership(changed,cfg,"1"*64,"2"*64,"3"*64,"4"*64)
    changed=deepcopy(value);changed["roles"]=[]
    with pytest.raises(RuntimeError):
        module.validate_role_ownership(changed,cfg,"1"*64,"2"*64,"3"*64,"4"*64)


def test_single_use_role_claim_is_still_exclusive(tmp_path):
    module=helper();tmp_path.chmod(0o700)
    claim=tmp_path/"CHECKER.SPENT.record"
    module.put(claim,b"exact immutable claim\n")
    with pytest.raises(FileExistsError):module.put(claim,b"second claim\n")
    assert claim.read_bytes()==b"exact immutable claim\n"


def test_new_budget_withdraws_only_administrative_preparation_reserve():
    value=gate.simple_collection_descriptor()
    assert value["budget"]==dict(gate.BUDGET,complete_admission_reserve_seconds=10320)
    assert gate.discriminator_collection_descriptor()["budget"]==dict(gate.BUDGET,
        collection_preparation_seconds=600,complete_admission_reserve_seconds=10920)
    assert value["new_source_qualification_claimed"] is False
    assert value["new_qualification_allocations"]==0
    assert value["unchanged_consumers"]==[dict(path=p,sha256=h) for p,h in gate.Q2_UNCHANGED_CONSUMERS[:-1]]


# Actual bound gate/production ready calls; TEST_ONLY selected source/authority and
# fixed absolute clock, genuine retained historical Q2. No native acceptance.
from test_stage12_ra_g1_allocation_controller import world  # noqa: E402,F401
from test_stage12_public_operations_v2 import offline  # noqa: E402,F401
from test_stage12_handoff_execution_window import genuine_q2  # noqa: E402,F401


def actual_case(world, bundle):
    from test_stage12_remote_directory_environment_gate import selected_case
    from test_stage12_ra_g1_rep_first64_512 import upgrade
    from test_stage12_ra_g1_environment_launch import original
    import stage12_ra_g1_allocation as allocation
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics
    module, selected, binding, value, _, _ = selected_case(world)
    prior_windowed_adoption=deepcopy(selected["rep_admin_budget_adoption"])
    selected = upgrade(selected)
    required = {name for _,name in diagnostics.FOREGROUND_MODULES}
    required.update(p for p,_ in (*module.Q2_UNCHANGED_CONSUMERS[:-1],module.SIMPLE_CHANGED_CONSUMER))
    for name in required:
        raw=(ROOT/name).read_bytes();path=world.source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_bytes(raw);path.chmod(0o644)
        selected["source_files"]=[r for r in selected["source_files"] if r["path"]!=name]
        selected["source_files"].append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    selected["source_files"].sort(key=lambda r:r["path"])
    selected.update(version=allocation.REP_FOREGROUND_VERSION,source_sha="c"*40,
        valid_from=windows.SIMPLE_WINDOW_START,valid_until=windows.SIMPLE_WINDOW_END)
    selected["accounting_inventory"],selected["accounting"]=accounting.compile_inventory(
        selected["source_files"],selected["accounting_inventory"]["backends"],allocation.SCOPE,
        bootstrap_successor=True,shared_lease_successor=True,rep_admin_successor=True,
        first64_512_successor=True,foreground_successor=True)
    adoption=prior_windowed_adoption
    adoption.update(schema_version=windows.SIMPLE_WINDOW_ADOPTION,window=selected_window(),
        qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW)
    selected["rep_admin_budget_adoption"]=adoption
    selected["rep_admin_budget_adoption_sha256"]=module.digest(adoption)
    binding=dict(binding,version=module.SIMPLE_COLLECTION_BINDING,
        policy_sha256=module.digest(module.simple_collection_descriptor()),
        window_policy_sha256=windows.digest(windows.simple_descriptor()),
        owner_authority_sha256=selected_window()["owner_authority_sha256"],
        grant_nonce=selected_window()["grant_nonce"],
        qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW)
    for name in ("software_review","resource_review"):
        review=world.m.parse((world.records/(selected["records"][name]+".record")).read_bytes())
        review["source_sha"]=selected["source_sha"]
        if name=="software_review":review["environment_gate_binding"]=binding
        identity=world.m.digest(review);original(world.m,world.records/(identity+".record"),review)
        selected["records"][name]=identity
    value=dict(value,version=module.SIMPLE_COLLECTION_VERSION,source_git_sha=selected["source_sha"],
        **{k:binding[k] for k in (*module.COLLECTION_BINDING_HASHES,*module.REMOTE_COLLECTION_FIELDS)},
        selection_sha256=module.digest(selected),software_review_sha256=selected["records"]["software_review"],
        resource_review_sha256=selected["records"]["resource_review"],
        source_inventory_sha256=selected["accounting_inventory"]["source_inventory_sha256"],
        valid_from=windows.SIMPLE_WINDOW_START,valid_until=windows.SIMPLE_WINDOW_END,
        outer_window_end=windows.SIMPLE_WINDOW_END,window=selected_window(),budget=dict(module.SIMPLE_BUDGET))
    original(world.m,module.qualification_path(selected,binding),bundle)
    identity=module.digest(value);original(world.m,module.gate_path(selected,identity),value)
    world.m.validate_selection(selected)
    return module,selected,binding,value,identity


def test_actual_ready_gate_uses_reviewed_delta_and_original_q2(world,genuine_q2,monkeypatch):
    import stage12_ra_g1_terminal_verify as verifier
    from test_stage12_ra_g1_environment_launch import attach
    module,selected,binding,value,identity=actual_case(world,genuine_q2)
    before=deepcopy(genuine_q2);now=windows.epoch_ns(windows.SIMPLE_WINDOW_START)+1000
    proof=module.validate_gate(value,selected,binding,now_epoch_ns=now,
        qualification=genuine_q2,qualification_validator=verifier.validate_qualification)
    assert proof["required_remaining_ns"]==10320*10**9
    assert genuine_q2==before and proof["native_timing_PASS"] is False
    monkeypatch.setattr(world.m,"now",lambda:windows.SIMPLE_WINDOW_START)
    monkeypatch.setattr(module.time,"time_ns",lambda:now)
    run=world.m.Run(selected,stage="ready",stage_seconds=120)
    try:
        attach(run,module,identity,world.m.parse)
        module.precheck(run)
        assert world.m.ready(run)
        assert module.after_ready(run)["gate_sha256"]==identity
    finally:run.close()


@pytest.mark.parametrize("changed",["legacy_gate","legacy_binding","legacy_window","legacy_budget","driver_pin"])
def test_actual_gate_rejects_mixed_or_stale_consumer(world,genuine_q2,changed):
    import stage12_ra_g1_terminal_verify as verifier
    module,selected,binding,value,_=actual_case(world,genuine_q2)
    if changed=="legacy_gate":value["version"]=module.DISCRIMINATOR_COLLECTION_VERSION
    elif changed=="legacy_binding":binding["version"]=module.DISCRIMINATOR_COLLECTION_BINDING
    elif changed=="legacy_window":value["window"]["version"]=windows.DISCRIMINATOR_WINDOW_VERSION
    elif changed=="legacy_budget":value["budget"]=dict(module.DISCRIMINATOR_BUDGET)
    else:
        next(r for r in selected["source_files"] if r["path"]==module.SIMPLE_CHANGED_CONSUMER[0])["sha256"]="e"*64
    with pytest.raises(RuntimeError):
        module.validate_gate(value,selected,binding,
            now_epoch_ns=windows.epoch_ns(windows.SIMPLE_WINDOW_START),
            qualification=genuine_q2,qualification_validator=verifier.validate_qualification)

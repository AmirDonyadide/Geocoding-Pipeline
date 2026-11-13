"""TEST_ONLY r3 window/family propagation; no current native facts or approval."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
REAL_PREFIX_POPEN=subprocess.Popen
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import stage12_ra_g1_allocation as allocation
import stage12_ra_g1_environment_launch as gate_module
import stage12_ra_g1_terminal_parent as parent
import stage12_ra_g1_terminal_verify as verifier
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics
from test_stage12_handoff_execution_window import world, offline, genuine_q2, handoff_case
from test_stage12_ra_g1_environment_launch import original, attach


def new_window(scope=windows.SCOPES[0]):
    return dict(version=windows.DISCRIMINATOR_WINDOW_VERSION,scope=scope,
        valid_from=windows.DISCRIMINATOR_WINDOW_START,valid_until=windows.DISCRIMINATOR_WINDOW_END,
        policy_sha256=windows.digest(windows.discriminator_descriptor()),
        owner_authority_sha256="1"*64,grant_nonce="2"*64)


def new_case(world,genuine_q2):
    gate,selected,binding,value,_=handoff_case(world,genuine_q2)
    for _,name in diagnostics.FOREGROUND_MODULES:
        raw=(ROOT/name).read_bytes();path=world.source/name
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        path.write_bytes(raw);path.chmod(0o644)
        selected["source_files"]=[r for r in selected["source_files"] if r["path"]!=name]
        selected["source_files"].append(dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    selected["source_files"].sort(key=lambda r:r["path"])
    selected["version"]=allocation.REP_FOREGROUND_VERSION
    selected["accounting_inventory"],selected["accounting"]=accounting.compile_inventory(
        selected["source_files"],selected["accounting_inventory"]["backends"],allocation.SCOPE,
        bootstrap_successor=True,shared_lease_successor=True,rep_admin_successor=True,
        first64_512_successor=True,foreground_successor=True)
    selected.update(valid_from=windows.DISCRIMINATOR_WINDOW_START,valid_until=windows.DISCRIMINATOR_WINDOW_END)
    adoption=selected["rep_admin_budget_adoption"]
    adoption.update(schema_version=windows.DISCRIMINATOR_WINDOW_ADOPTION,window=new_window())
    selected["rep_admin_budget_adoption_sha256"]=gate.digest(adoption)
    binding=dict(binding,version=gate.DISCRIMINATOR_COLLECTION_BINDING,
        policy_sha256=gate.digest(gate.discriminator_collection_descriptor()),
        window_policy_sha256=windows.digest(windows.discriminator_descriptor()))
    review=world.m.parse((world.records/(selected["records"]["software_review"]+".record")).read_bytes())
    review["environment_gate_binding"]=binding
    identity=world.m.digest(review);original(world.m,world.records/(identity+".record"),review)
    selected["records"]["software_review"]=identity
    value=dict(value,version=gate.DISCRIMINATOR_COLLECTION_VERSION,
        **{k:binding[k] for k in (*gate.COLLECTION_BINDING_HASHES,*gate.REMOTE_COLLECTION_FIELDS)},
        selection_sha256=gate.digest(selected),software_review_sha256=identity,
        source_inventory_sha256=selected["accounting_inventory"]["source_inventory_sha256"],
        valid_from=windows.DISCRIMINATOR_WINDOW_START,valid_until=windows.DISCRIMINATOR_WINDOW_END,
        outer_window_end=windows.DISCRIMINATOR_WINDOW_END,window=new_window(),budget=dict(gate.DISCRIMINATOR_BUDGET))
    identity=gate.digest(value);original(world.m,gate.gate_path(selected,identity),value)
    world.m.validate_selection(selected)
    return gate,selected,binding,value,identity


@pytest.mark.parametrize("scope,remaining",[(windows.SCOPES[0],10920),(windows.SCOPES[1],1920)])
def test_new_window_exact_reserve_and_unchanged_old_limits(scope,remaining):
    value=new_window(scope);end=windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_END)
    exact=end-remaining*10**9
    assert windows.validate_window(value,scope=scope,now_epoch_ns=exact,required_remaining_seconds=remaining) is value
    with pytest.raises(RuntimeError):windows.validate_window(value,scope=scope,now_epoch_ns=exact+1,required_remaining_seconds=remaining)
    with pytest.raises(RuntimeError):windows.validate_window(value,scope=scope,now_epoch_ns=exact,required_remaining_seconds=10320)
    assert windows.WINDOW_END=="2026-11-12T19:13:21.620987Z"
    assert windows.HANDOFF_WINDOW_END=="2026-11-13T19:13:21.620987Z"
    assert windows.PUBLIC_WINDOW_END=="2026-11-11T19:13:21.620987Z"


@pytest.mark.parametrize("change",["old_policy","old_start","old_end","old_version","invalid_authority"])
def test_new_window_cannot_reinterpret_old_or_unbound_controls(change):
    value=new_window()
    if change=="old_policy":value["policy_sha256"]=windows.digest(windows.handoff_descriptor())
    elif change=="old_start":value["valid_from"]=windows.HANDOFF_WINDOW_START
    elif change=="old_end":value["valid_until"]=windows.HANDOFF_WINDOW_END
    elif change=="old_version":value["version"]=windows.HANDOFF_WINDOW_VERSION
    else:value["owner_authority_sha256"]="0"*64
    with pytest.raises(RuntimeError):windows.validate_window(value,scope=windows.SCOPES[0],now_epoch_ns=windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_START),required_remaining_seconds=10920)


def test_parent_window_bootstrap_requires_exact_explicit_optin():
    assert parent.bootstrap_family_end(same_domain_successor=False)==parent.WINDOW_END_NS
    assert parent.bootstrap_family_end(same_domain_successor=True)==windows.epoch_ns(windows.WINDOW_END)
    assert parent.bootstrap_family_end(same_domain_successor=True,handoff_window_successor=True)==windows.epoch_ns(windows.HANDOFF_WINDOW_END)
    assert parent.bootstrap_family_end(same_domain_successor=True,discriminator_window_successor=True)==windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_END)
    for kwargs in [dict(same_domain_successor=False,discriminator_window_successor=True),dict(same_domain_successor=True,discriminator_window_successor=True,handoff_window_successor=True)]:
        with pytest.raises(RuntimeError):parent.bootstrap_family_end(**kwargs)
    control=dict(version=parent.SUCCESSOR_VERSION,window=new_window(windows.SCOPES[1]))
    parent.validate_cli_window(control,handoff_window_successor=False,discriminator_window_successor=True)
    assert parent.family_end(control)==windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_END)
    with pytest.raises(RuntimeError):parent.validate_cli_window(control,handoff_window_successor=False)
    with pytest.raises(RuntimeError):parent.validate_cli_window(control,handoff_window_successor=True)


def test_actual_new_gate_Q2_reuse_and_ready_boundary(world,genuine_q2,monkeypatch):
    gate,selected,binding,value,identity=new_case(world,genuine_q2)
    historical=deepcopy(genuine_q2)
    now=windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_START)+1000
    proof=gate.validate_gate(value,selected,binding,now_epoch_ns=now,
        qualification=genuine_q2,qualification_validator=verifier.validate_qualification)
    assert proof["required_remaining_ns"]==10920*10**9 and proof["native_timing_PASS"] is False
    assert genuine_q2==historical and genuine_q2["window"]["version"]==windows.WINDOW_VERSION
    monkeypatch.setattr(world.m,"now",lambda:windows.DISCRIMINATOR_WINDOW_START)
    monkeypatch.setattr(gate.time,"time_ns",lambda:now)
    run=world.m.Run(selected,stage="ready",stage_seconds=120)
    try:
        attach(run,gate,identity,world.m.parse)
        assert gate.precheck(run)["qualification_bundle_sha256"]==windows.Q2_BUNDLE
        assert world.m.ready(run)
        assert gate.after_ready(run)["gate_sha256"]==identity
    finally:run.close()


@pytest.mark.parametrize("change",["old_binding","old_allocation","old_window","old_budget","source_change"])
def test_new_gate_rejects_mixed_bindings(world,genuine_q2,change):
    gate,selected,binding,value,_=new_case(world,genuine_q2)
    if change=="old_binding":binding["version"]=gate.HANDOFF_COLLECTION_BINDING
    elif change=="old_allocation":selected["version"]=allocation.REP512_VERSION
    elif change=="old_window":value["window"]["version"]=windows.HANDOFF_WINDOW_VERSION
    elif change=="old_budget":value["budget"]=dict(gate.BUDGET)
    else:selected["source_files"][0]["sha256"]="d"*64
    with pytest.raises(RuntimeError):gate.validate_gate(value,selected,binding,
        now_epoch_ns=windows.epoch_ns(windows.DISCRIMINATOR_WINDOW_START),
        qualification=genuine_q2,qualification_validator=verifier.validate_qualification)


@pytest.mark.parametrize("flags,expected",[(dict(STAGE12_TC_SAME_DOMAIN_SUCCESSOR="1",STAGE12_TC_DISCRIMINATOR_WINDOW_SUCCESSOR="1"),0),(dict(STAGE12_TC_DISCRIMINATOR_WINDOW_SUCCESSOR="1"),2),(dict(STAGE12_TC_SAME_DOMAIN_SUCCESSOR="1",STAGE12_TC_DISCRIMINATOR_WINDOW_SUCCESSOR="1",STAGE12_TC_HANDOFF_WINDOW_SUCCESSOR="1"),2),(dict(STAGE12_TC_SAME_DOMAIN_SUCCESSOR="1",STAGE12_TC_DISCRIMINATOR_WINDOW_SUCCESSOR="bad"),2)])
def test_actual_launcher_flag_prefix(flags,expected):
    # Actual source-owned shell prefix and builtins only. No scheduler/source/
    # Python substitution is described as native guard acceptance.
    text=(ROOT/"cluster/goethe_nhr/stage12_ra_g1_terminal_collection.sbatch").read_text()
    prefix=text[:text.index("export SAFE_EXECUTION_SITE=")]
    env={"PATH":os.environ["PATH"],**{k:"TEST_ONLY" for k in ("STAGE12_TC_SOURCE","STAGE12_TC_SHA","STAGE12_TC_PYTHON","STAGE12_TC_BINDING","STAGE12_TC_BINDING_SHA","STAGE12_TC_AUTHORITY","STAGE12_TC_AUTHORITY_SHA")},**flags}
    # The module's existing offline fixture denies all general children. Only
    # these four explicitly precharged shell-prefix children use the saved
    # primitive; all production/network/credential calls remain denied.
    proc=REAL_PREFIX_POPEN(["/bin/bash","-c",prefix+"\nprintf '%s\\n' \"${successor_args[@]}\"\n"],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:out,err=proc.communicate(timeout=4.75)
    except BaseException:
        proc.kill();proc.communicate(timeout=0.25);raise
    assert proc.returncode==expected and len(out)+len(err)<=4096
    if expected==0:assert out==b"--same-domain-successor\n--discriminator-window-successor\n"



@pytest.mark.parametrize("new_family",[False,True])
def test_actual_original_namespace_supports_legacy_producer_api(world,genuine_q2,new_family):
    from types import SimpleNamespace
    if new_family:
        _,selected,_,_,_=new_case(world,genuine_q2)
        producer=allocation
    else:
        _,selected,_,_,_=handoff_case(world,genuine_q2)
        # Explicit old-API shape with the actual production validator. This is
        # not a claim that historical software was rerun or current facts proved.
        producer=SimpleNamespace(REP512_VERSION=allocation.REP512_VERSION,
            SCOPE=allocation.SCOPE,validate_selection=allocation.validate_selection)
    paths=selected["paths"]
    roots=[dict(label="allocation",path=paths["allocation_root"]),dict(label="records",path=paths["records"])]
    policy=dict(external_files=[],required_logs=["records/slurm.log"])
    binding=dict(version=parent.SUCCESSOR_VERSION,original_source_root=paths["source"],
        historical_collection=None,original_log_policy=policy)
    template=dict(roots=roots,**policy)
    parent.validate_original_namespace(selected,template,binding,producer,False)
    changed=deepcopy(selected);changed["accounting"]["check_calls"]-=1
    with pytest.raises((RuntimeError,ValueError)):
        parent.validate_original_namespace(changed,template,binding,producer,False)
    changed=deepcopy(selected);changed["version"]="UNKNOWN_SOURCE_FAMILY"
    with pytest.raises(RuntimeError):parent.validate_original_namespace(changed,template,binding,producer,False)

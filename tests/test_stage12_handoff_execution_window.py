"""Fresh handoff-window composition tests: synthetic authority, genuine retained Q2.

Retained originals supply historical facts only. These tests issue no live record,
allocate no job, and do not qualify the current source or release a workload.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from test_stage12_ra_g1_allocation_controller import world
from test_stage12_public_operations_v2 import offline
from test_stage12_remote_directory_environment_gate import selected_case
from test_stage12_ra_g1_environment_launch import original, attach
from test_stage12_ra_g1_rep_first64_512 import upgrade
import stage12_ra_g1_allocation as allocation
import stage12_prepare_ra_g1 as preparer
import stage12_ra_g1_terminal_verify as verifier
import stage12_ra_g1_terminal_parent as parent
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance


def retained_bytes(variable, expected_hash, maximum):
    path = os.environ.get(variable)
    if path is None:
        pytest.skip("requires the explicitly selected retained original; no invented replacement")
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    identity = lambda s: (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    try:
        import stat
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= maximum
        assert identity(before) == identity(path.lstat())
        raw = bytearray()
        while len(raw) < before.st_size:
            part = os.read(fd, min(65536,before.st_size-len(raw)))
            assert part
            raw.extend(part)
        assert not os.read(fd,1)
        assert identity(before) == identity(os.fstat(fd)) == identity(path.lstat())
    finally:
        os.close(fd)
    result = bytes(raw)
    assert hashlib.sha256(result).hexdigest() == expected_hash
    return result


@pytest.fixture(scope="module")
def genuine_q2():
    raw = retained_bytes("STAGE12_HANDOFF_RETAINED_Q2", windows.Q2_BUNDLE, 65536)
    value = allocation.parse(raw)
    assert value["review"]["collection_source_git_sha"] == windows.Q2_SOURCE
    assert verifier._q_digest(value["review"]) == windows.Q2_REVIEW
    return value


def r2_window(scope="REPRESENTATIVE_NO_SERVICE"):
    return dict(version=windows.HANDOFF_WINDOW_VERSION, scope=scope,
        valid_from=windows.HANDOFF_WINDOW_START,valid_until=windows.HANDOFF_WINDOW_END,
        policy_sha256=windows.digest(windows.handoff_descriptor()),
        owner_authority_sha256="1"*64,grant_nonce="2"*64)


def r2_adoption(prior):
    original = prior["original_adoption"] if windows.is_window_adoption(prior) else prior
    return dict(schema_version=windows.HANDOFF_WINDOW_ADOPTION,scope="REPRESENTATIVE_NO_SERVICE",
        window=r2_window(),original_adoption=original,original_adoption_sha256=windows.digest(original),
        grant_kind=windows.REP_GRANT,maximum_submissions=1,
        qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW,
        historical_grant_consumed=True,original_budget_terms_unchanged=True)


def handoff_case(world, genuine_q2):
    gate, selected, binding, value, _, _ = selected_case(world)
    # Actual source files and validators, with TEST_ONLY source/review/grant identities.
    for name, expected in gate.Q2_UNCHANGED_CONSUMERS:
        path = world.source/name
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        raw = (ROOT/name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected
        path.write_bytes(raw);path.chmod(0o644)
        selected["source_files"] = [r for r in selected["source_files"] if r["path"] != name]
        selected["source_files"].append(dict(path=name,bytes=len(raw),sha256=expected))
    selected["source_files"].sort(key=lambda row:row["path"])
    prior = selected["rep_admin_budget_adoption"]
    selected = upgrade(selected)
    selected.update(source_sha="c"*40,valid_from=windows.HANDOFF_WINDOW_START,
                    valid_until=windows.HANDOFF_WINDOW_END)
    selected["rep_admin_budget_adoption"] = r2_adoption(prior)
    selected["rep_admin_budget_adoption_sha256"] = gate.digest(selected["rep_admin_budget_adoption"])
    binding = dict(binding,version=gate.HANDOFF_COLLECTION_BINDING,
        policy_sha256=gate.digest(gate.handoff_collection_descriptor()),
        window_policy_sha256=windows.digest(windows.handoff_descriptor()),
        owner_authority_sha256=r2_window()["owner_authority_sha256"],grant_nonce=r2_window()["grant_nonce"],
        qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW)
    for name in ("resource_review","software_review"):
        review = world.m.parse((world.records/(selected["records"][name]+".record")).read_bytes())
        review["source_sha"] = selected["source_sha"]
        if name == "software_review": review["environment_gate_binding"] = binding
        identity = world.m.digest(review)
        original(world.m,world.records/(identity+".record"),review)
        selected["records"][name] = identity
    value = dict(value,version=gate.HANDOFF_COLLECTION_VERSION,source_git_sha=selected["source_sha"],
        **{key:binding[key] for key in (*gate.COLLECTION_BINDING_HASHES,*gate.REMOTE_COLLECTION_FIELDS)},
        selection_sha256=gate.digest(selected),software_review_sha256=selected["records"]["software_review"],
        resource_review_sha256=selected["records"]["resource_review"],
        source_inventory_sha256=selected["accounting_inventory"]["source_inventory_sha256"],
        valid_from=windows.HANDOFF_WINDOW_START,valid_until=windows.HANDOFF_WINDOW_END,
        outer_window_end=windows.HANDOFF_WINDOW_END,window=r2_window())
    original(world.m,gate.qualification_path(selected,binding),genuine_q2)
    identity=gate.digest(value)
    original(world.m,gate.gate_path(selected,identity),value)
    world.m.validate_selection(selected)
    return gate,selected,binding,value,identity


def test_r1_defaults_and_r2_inclusive_windows_are_separate():
    assert windows.WINDOW_END == "2026-11-12T19:13:21.620987Z"
    assert windows.PUBLIC_WINDOW_END == "2026-11-11T19:13:21.620987Z"
    assert windows.descriptor()["initial_collection_required"] is True
    assert windows.handoff_descriptor()["initial_collection_required"] is False
    for scope, remaining in ((windows.SCOPES[0],windows.REP_REMAINING),(windows.SCOPES[1],windows.FINAL_REMAINING)):
        value=r2_window(scope)
        exact=windows.epoch_ns(windows.HANDOFF_WINDOW_END)-remaining*10**9
        assert windows.validate_window(value,scope=scope,now_epoch_ns=exact,required_remaining_seconds=remaining) is value
        with pytest.raises(RuntimeError):windows.validate_window(value,scope=scope,now_epoch_ns=exact+1,required_remaining_seconds=remaining)
    with pytest.raises(RuntimeError):
        windows.validate_window(r2_window(windows.SCOPES[1]),scope=windows.SCOPES[1],
            now_epoch_ns=windows.epoch_ns(windows.HANDOFF_WINDOW_START),required_remaining_seconds=windows.INITIAL_REMAINING)
    assert parent.family_end(dict(version=parent.SUCCESSOR_VERSION,window=r2_window(windows.SCOPES[1]))) == windows.epoch_ns(windows.HANDOFF_WINDOW_END)
    old=dict(r2_window(),version=windows.WINDOW_VERSION,valid_from=windows.WINDOW_START,valid_until=windows.WINDOW_END,policy_sha256=windows.digest(windows.descriptor()))
    assert windows.validate_window(old,scope=windows.SCOPES[0],now_epoch_ns=windows.epoch_ns(windows.WINDOW_START),required_remaining_seconds=windows.REP_REMAINING) is old
    assert parent.family_end(dict(version=parent.SUCCESSOR_VERSION,window=old)) == windows.epoch_ns(windows.WINDOW_END)


def test_genuine_historical_q2_and_current_gate_are_distinct(world,genuine_q2):
    gate,selected,binding,value,_=handoff_case(world,genuine_q2)
    historical=deepcopy(genuine_q2)
    proof=gate.validate_gate(value,selected,binding,
        now_epoch_ns=windows.epoch_ns(windows.HANDOFF_WINDOW_START),
        qualification=genuine_q2,qualification_validator=verifier.validate_qualification)
    assert proof["qualification_bundle_sha256"] == windows.Q2_BUNDLE
    assert proof["native_timing_PASS"] is proof["service_or_protected_authority"] is False
    assert selected["source_sha"] != genuine_q2["ready"]["context"]["collection_source_git_sha"] == windows.Q2_SOURCE
    assert genuine_q2 == historical and genuine_q2["window"]["version"] == windows.WINDOW_VERSION


@pytest.mark.parametrize("change", ["gate_family","window","window_policy","adoption","qhash","qsource","consumer","collect_consumer","unknown","old_expiry"])
def test_current_gate_rejects_mixed_or_changed_bindings(world,genuine_q2,change):
    gate,selected,binding,value,_=handoff_case(world,genuine_q2)
    bundle=deepcopy(genuine_q2)
    if change == "gate_family":value["version"]=gate.REMOTE_COLLECTION_VERSION
    elif change == "window":value["window"]["version"]=windows.WINDOW_VERSION
    elif change == "window_policy":binding["window_policy_sha256"]=value["window_policy_sha256"]="a"*64
    elif change == "adoption":selected["rep_admin_budget_adoption"]["schema_version"]=windows.WINDOW_ADOPTION
    elif change == "qhash":binding["qualification_bundle_sha256"]=value["qualification_bundle_sha256"]="a"*64
    elif change == "qsource":bundle["ready"]["context"]["collection_source_git_sha"]="a"*40
    elif change == "consumer":
        next(row for row in selected["source_files"] if row["path"]==gate.Q2_UNCHANGED_CONSUMERS[0][0])["sha256"]="a"*64
    elif change == "collect_consumer":
        next(row for row in selected["source_files"] if row["path"]=="scripts/stage12_ra_g1_terminal_collect.py")["sha256"]="a"*64
    elif change == "unknown":value["assumed_permission"]=True
    elif change == "old_expiry":value["valid_until"]=windows.WINDOW_END
    with pytest.raises(RuntimeError):gate.validate_gate(value,selected,binding,
        now_epoch_ns=windows.epoch_ns(windows.HANDOFF_WINDOW_START),
        qualification=bundle,qualification_validator=verifier.validate_qualification)


def test_actual_current_precheck_and_fresh_verifier_mutation(world,genuine_q2,monkeypatch):
    gate,selected,_,_,identity=handoff_case(world,genuine_q2)
    monkeypatch.setattr(world.m,"now",lambda:windows.HANDOFF_WINDOW_START)
    monkeypatch.setattr(gate.time,"time_ns",lambda:windows.epoch_ns(windows.HANDOFF_WINDOW_START)+2000)
    run=world.m.Run(selected,stage="ready",stage_seconds=120)
    try:
        attach(run,gate,identity,world.m.parse)
        assert gate.precheck(run)["qualification_bundle_sha256"] == windows.Q2_BUNDLE
        assert world.m.ready(run)
        path=world.source/"scripts/stage12_ra_g1_terminal_verify.py"
        path.write_bytes(path.read_bytes()+b"# TEST_ONLY mutation\n")
        with pytest.raises(RuntimeError,match="RA_G1_SOURCE_CHANGED"):gate.after_ready(run)
    finally:run.close()


def test_genuine_allocation_resource_compiler_accepts_only_bound_r2(genuine_q2):
    raw=retained_bytes("STAGE12_HANDOFF_RETAINED_SELECTION","34b34846a2db9f4c16eaadeece96cce611cd2f6b22edc2a6e0d3eca549c4be92",2**20)
    old=allocation.parse(raw)
    assert allocation.validate_selection(old) is old
    selected=deepcopy(old)
    selected.update(source_sha="c"*40,valid_from=windows.HANDOFF_WINDOW_START,valid_until=windows.HANDOFF_WINDOW_END)
    selected["rep_admin_budget_adoption"]=r2_adoption(old["rep_admin_budget_adoption"])
    selected["rep_admin_budget_adoption_sha256"]=allocation.digest(selected["rep_admin_budget_adoption"])
    assert allocation.validate_selection(selected) is selected
    record=preparer.resource_selection(selected,policy_sha256="1"*64,adoption_sha256="2"*64,
        descriptor_inventory_sha256="3"*64,graph_sha256="4"*64,paths_sha256="5"*64,implementation_review_sha256="6"*64)
    assert assurance.validate_selection(record) is record
    assert record["valid_from"]==windows.HANDOFF_WINDOW_START and record["valid_until"]==windows.HANDOFF_WINDOW_END
    assert record["limits"]["stages"][0]["deadline_ms"]==512000
    assurance.validate_rep_admin_adoption(selected["rep_admin_budget_adoption"],record)
    for change in ("schema","window","q2"):
        bad=deepcopy(selected)
        if change=="schema":bad["rep_admin_budget_adoption"]["schema_version"]=windows.WINDOW_ADOPTION
        elif change=="window":bad["valid_until"]=windows.WINDOW_END
        else:bad["rep_admin_budget_adoption"]["qualification_bundle_sha256"]="a"*64
        bad["rep_admin_budget_adoption_sha256"]=allocation.digest(bad["rep_admin_budget_adoption"])
        with pytest.raises(RuntimeError):allocation.validate_selection(bad)


def test_parent_bootstrap_cli_requires_exact_window_opt_in():
    assert parent.bootstrap_family_end(same_domain_successor=False) == parent.WINDOW_END_NS
    assert parent.bootstrap_family_end(same_domain_successor=True) == windows.epoch_ns(windows.WINDOW_END)
    assert parent.bootstrap_family_end(same_domain_successor=True,handoff_window_successor=True) == windows.epoch_ns(windows.HANDOFF_WINDOW_END)
    with pytest.raises(RuntimeError):parent.bootstrap_family_end(same_domain_successor=False,handoff_window_successor=True)
    old=dict(version=windows.WINDOW_VERSION)
    new=r2_window(windows.SCOPES[1])
    parent.validate_cli_window(dict(window=old),handoff_window_successor=False)
    parent.validate_cli_window(dict(window=new),handoff_window_successor=True)
    parent.validate_cli_window(dict(context=dict(window=new)),handoff_window_successor=True)
    with pytest.raises(RuntimeError):parent.validate_cli_window(dict(window=old),handoff_window_successor=True)
    with pytest.raises(RuntimeError):parent.validate_cli_window(dict(window=new),handoff_window_successor=False)

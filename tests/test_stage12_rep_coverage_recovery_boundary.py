"""TEST_ONLY constructed verifier output through real export/transfer/open.

The substituted output tests a producer/consumer representation boundary. It is
not a four-scenario verifier,106-attempt result, native approval, or B PASS.
Actual CLI/T3/report/reopen semantics are tested separately without substitution.
"""
from copy import deepcopy
import ast
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import stage12_ra_g1_direct_recovery as direct
import stage12_ra_g1_terminal_collect as tc
from test_stage12_direct_recovery import ROOT, case, put, recover
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_coverage_contract as policy


def scoped_proof():
    return dict(schema=direct.verifier.COVERAGE_VERSION, complete=True,
        scope="REPRESENTATIVE_NO_SERVICE", source_sha="a"*40,
        allocation_selection_sha256="1"*64,
        status="FRESH_ORIGINAL_CONTENT_AND_TIMED_RECORDS_VERIFIED",
        original_timed_acceptance_repaired=False,
        current_environment_or_old_clock_equivalence_asserted=False,
        workload_evidence_complete=True, ap_coverage_complete=False,
        administrative_monitor_coverage_complete=True,
        qualification_outcome="WORKLOAD_COMPLETE_AP_COVERAGE_INCOMPLETE",
        sampling_policy_sha256=policy.POLICY_SHA, sampling_policy_version=policy.POLICY_VERSION,
        counts=dict(read_calls=0, returned_bytes=0, opens=0),
        summary_sha256="1"*64, input_sha256="1"*64,
        data_phases=[], resource_phases=[], timing_prefix_sha256="1"*64)


def test_constructed_shape_tracks_actual_source_owned_emitter_fields():
    tree=ast.parse((ROOT/"scripts/stage12_ra_g1_terminal_verify.py").read_bytes())
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef)
        and node.name=="verify_original_workload")
    emitted=set()
    for node in ast.walk(function):
        if isinstance(node,ast.Assign):
            if any(isinstance(t,ast.Name) and t.id=="result" for t in node.targets):
                assert isinstance(node.value,ast.Call)
                emitted.update(k.arg for k in node.value.keywords)
            for target in node.targets:
                if (isinstance(target,ast.Subscript) and isinstance(target.value,ast.Name)
                        and target.value.id=="result" and isinstance(target.slice,ast.Constant)):
                    emitted.add(target.slice.value)
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                and isinstance(node.func.value,ast.Name) and node.func.value.id=="result"
                and node.func.attr=="update"):
            emitted.update(k.arg for k in node.keywords)
    assert emitted==set(scoped_proof())
    direct._coverage_workload_shape(scoped_proof())


def test_new_scoped_output_through_actual_export_transfer_and_reopening(tmp_path, monkeypatch):
    root, plan = case(tmp_path)
    original = dict(source_sha="a"*40, scope="REPRESENTATIVE_NO_SERVICE", version=direct.COVERAGE_ALLOCATION)
    raw = tc.canonical(original)
    # Fresh fixture only: no retained or historical original is modified.
    selected = root/"records/FINAL_SELECTION.record"
    selected.write_bytes(raw)
    plan["originals"][0]["identity_sha256"] = direct.digest(raw)
    plan["original_workload"]["selection_sha256"] = direct.digest(raw)
    proof_path = root/"TEST_ONLY_CONSTRUCTED_SCOPE_PROOF.record"
    put(proof_path, tc.canonical(scoped_proof()))
    launcher = root/"TEST_ONLY_CONSTRUCTED_SCOPE_LAUNCHER.py"
    put(launcher, b'''import json,sys
from pathlib import Path
import stage12_ra_g1_direct_recovery as d
proof=json.loads(Path(sys.argv[1]).read_bytes())
def TEST_ONLY_scoped_output(original, **kwargs):
    result=dict(proof)
    result["source_sha"]=original["source_sha"]
    result["allocation_selection_sha256"]=d.digest(d.tc.canonical(original))
    return result
d.verifier.verify_original_workload=TEST_ONLY_scoped_output
raise SystemExit(d.main(sys.argv[2:]))
''')
    config=root/"plan.record";put(config,tc.canonical(plan))
    argv=[str(ROOT/".venv/bin/python"),"-B",str(launcher),str(proof_path),"export",
        "--plan",str(config),"--plan-sha256",direct.digest(tc.canonical(plan)),
        "--output",str(root/"export"),"--window-end-epoch-ns",str(plan["window_end_epoch_ns"]),
        "--export-end-epoch-ns",str(time.time_ns()+60*10**9),"--offline-invented","--test-root",str(root)]
    env=dict(os.environ,PYTHONPATH=str(ROOT/"src")+os.pathsep+str(ROOT/"scripts"),PYTHONDONTWRITEBYTECODE="1")
    proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    try: stdout,stderr=proc.communicate(timeout=15)
    except BaseException:
        proc.kill();proc.communicate(timeout=2);raise
    assert proc.returncode==0,stderr
    put(root/"export-client.stdout",stdout);put(root/"export-client.stderr",stderr)
    proof=recover(root,plan,monkeypatch)
    opened=direct.reopen_recovery(plan,proof,root/"local",root/"independent",offline=True,test_root=root)
    assert opened["status"]=="COMPLETE" and opened["complete_mirror_rehashed"]
    work=proof["workload_verification"]
    assert work["version"]==direct.WORKLOAD_COVERAGE_VERSION and work["complete"]
    assert work["proof"]["workload_evidence_complete"] is True
    assert work["proof"]["ap_coverage_complete"] is False
    assert work["proof"]["administrative_monitor_coverage_complete"] is True
    assert proof["native_or_scientific_acceptance"] is False
    for key in ("ap_coverage_complete","administrative_monitor_coverage_complete"):
        broken=deepcopy(proof);broken["workload_verification"]["proof"].pop(key)
        with pytest.raises(RuntimeError):direct._integrity(broken,allow_test_only=True)
    put(root/"TEST_ONLY_BOUNDARY_DISPOSITION.record",tc.canonical(dict(
        scope="CONSTRUCTED_VERIFIER_OUTPUT_ONLY_NOT_NATIVE_OR_FULL_REPRESENTATIVE_QUALIFICATION",
        substituted_interface="terminal_verifier_return_value",
        actual_export_child_exit=proc.returncode,actual_transfer_and_full_reopen=True,
        no_106_attempt_or_four_scenario_claim=True,workload_field=True,ap_coverage_field=False)))


@pytest.mark.parametrize("change",["old_schema","missing_ap","admin_gap","combined_assertion","wrong_policy","half_input_binding"])
def test_new_scoped_proof_rejects_mixed_or_ineligible_fields(change):
    value=scoped_proof()
    if change=="old_schema":value["schema"]=direct.verifier.FAIR_VERSION
    elif change=="missing_ap":value.pop("ap_coverage_complete")
    elif change=="admin_gap":value["administrative_monitor_coverage_complete"]=False
    elif change=="combined_assertion":value["sampling_and_monitor_coverage"]="COMPLETE_SELECTED_SCOPE"
    elif change=="half_input_binding":value.pop("input_sha256")
    else:value["sampling_policy_sha256"]="2"*64
    with pytest.raises(RuntimeError):direct._coverage_workload_shape(value)

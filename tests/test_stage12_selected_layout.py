"""Selected native layout regressions; every positive fixture is TEST_ONLY.

Mac filesystem backing never supplies a Goethe preparation or B PASS.  Native
command bytes and logical /panfs paths remain unchanged in retained artifacts.
"""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import stat
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = PurePosixPath("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
CONTROLLED = PROJECT / "derived/controlled/stage12/client_diagnostics"

def module(name, folder="scripts"):
    path = ROOT / folder / (name + ".py")
    spec = importlib.util.spec_from_file_location("selected_layout_" + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)+"\n").encode()

def put(path, raw):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return {"path":str(path), "sha256":hashlib.sha256(raw).hexdigest()}

def corrected_paths():
    root = CONTROLLED / ("ra_g1_" + "a"*32)
    records = CONTROLLED / ("selected_records_" + "b"*32) / "records"
    source = PROJECT / "integration_stage12/selected_fixture"
    result = {"source":str(source), "records":str(records), "allocation_root":str(root),
              "log":str(records/"slurm.log")}
    for key,name in (("input","input.json"),("binding","binding"),("output","diagnostic"),
                     ("context","context.record"),("bootstrap","bootstrap"),
                     ("review","bootstrap_review.record"),("release","exact_release.record"),
                     ("outcome","outcome.record"),("worker_return","worker_return.record"),
                     ("supervisor_state","supervisor_state.record"),("tail","tail.record")):
        result[key] = str(root/name)
    return result

@pytest.fixture
def commands():
    return module("b_nonwaiting_commands", "scripts/stage12_ra_g1_task_assets")

@pytest.fixture
def producer():
    return module("prepare_current_native", "scripts/stage12_ra_g1_task_assets")

def test_selected_producer_and_actual_command_helpers_agree(commands,producer):
    paths=corrected_paths()
    a=producer.selected_native_layout(paths["allocation_root"],paths["records"],paths["source"])
    b=commands.selected_native_layout(paths)
    assert a==b
    assert a["allocation_creation_owner"]=="NATIVE_COLLECTOR_EXCLUSIVE"
    assert a["controlled_parent"]==str(CONTROLLED)

@pytest.mark.parametrize("case",["nested_old","shared_records","records_under_allocation",
    "source_under_allocation","input_sibling","binding_alias","output_wrong","log_wrong",
    "double_slash","relative","empty_nonce","public","dotdot"])
def test_selected_layout_rejects_unsafe_or_incompatible_paths(commands,producer,case):
    paths=corrected_paths()
    if case=="nested_old":
        old=CONTROLLED/"old_private"
        root=old/"allocation"
        original_root=PurePosixPath(paths["allocation_root"])
        for key,value in list(paths.items()):
            if key not in ("source","records","log"):
                paths[key]=str(root/PurePosixPath(value).relative_to(original_root)) if key!="allocation_root" else str(root)
        paths["records"]=str(old/"records")
        paths["log"]=str(old/"records/slurm.log")
    elif case=="shared_records":
        paths["records"]=str(CONTROLLED/"records");paths["log"]=str(CONTROLLED/"records/slurm.log")
    elif case=="records_under_allocation":
        paths["records"]=paths["allocation_root"]+"/records";paths["log"]=paths["records"]+"/slurm.log"
    elif case=="source_under_allocation":
        paths["source"]=paths["allocation_root"]+"/source"
    elif case=="input_sibling":
        paths["input"]=str(CONTROLLED/"other/input.json")
    elif case=="binding_alias":
        paths["binding"]=paths["allocation_root"]+"/evidence"
    elif case=="output_wrong":
        paths["output"]=paths["allocation_root"]+"/result"
    elif case=="log_wrong":
        paths["log"]=paths["records"]+"/wrong.log"
    elif case=="double_slash":
        paths["allocation_root"]=paths["allocation_root"].replace("/client_diagnostics/","/client_diagnostics//")
    elif case=="relative":
        paths["allocation_root"]="relative/ra_g1_bad"
    elif case=="empty_nonce":
        paths["allocation_root"]=str(CONTROLLED/"ra_g1_")
    elif case=="public":
        paths["source"]=str(PROJECT/"public/integration_stage12/source")
    elif case=="dotdot":
        paths["allocation_root"]=str(CONTROLLED)+"/../client_diagnostics/ra_g1_bad"
    with pytest.raises((RuntimeError,ValueError)):
        commands.selected_native_layout(paths)
    if case in {"nested_old","shared_records","records_under_allocation","source_under_allocation",
                "double_slash","relative","empty_nonce","public","dotdot"}:
        with pytest.raises((RuntimeError,ValueError)):
            producer.selected_native_layout(paths["allocation_root"],paths["records"],paths["source"])

def test_materialized_exact_setup_and_submission_do_not_create_allocation(commands,tmp_path):
    paths=corrected_paths()
    selection={"source_sha":"a"*40,"scope":"REPRESENTATIVE_NO_SERVICE","paths":paths,
               "accounting_inventory":{"backends":[{"path":"/runtime/lib"+str(n)}for n in range(5)]}}
    sr=put(tmp_path/"SELECTION.record",canonical(selection))
    ur=put(tmp_path/"UPLOADS.record",canonical([]))
    prepared={"status":"CANONICAL_BINDINGS_GENERATED_NOT_NATIVE_READY_OR_SUBMISSION",
              "source_sha":selection["source_sha"],"selection":sr,"record_uploads":ur}
    result=commands.materialize_preparation(prepared=prepared,allocation=selection,source_tree="b"*40,
        backend_inventory=selection["accounting_inventory"]["backends"],output=tmp_path/"staged",write=put)
    setup=shlex.split(result["setup_argv"][-1])[-1]
    verify=shlex.split(result["verify_argv"][-1])[-1]
    lines=setup.splitlines()
    mkdir=[shlex.split(x)for x in lines if x.startswith("mkdir ")]
    assert mkdir==[["mkdir","--",str(PurePosixPath(paths["records"]).parent),paths["records"]]]
    assert all("chmod" not in x for x in lines)
    assert not any(shlex.split(x)[-1]==str(CONTROLLED) for x in lines if x.startswith("mkdir "))
    for body in (setup,verify):
        assert "test ! -e "+shlex.quote(paths["allocation_root"]) in body
        assert "test ! -L "+shlex.quote(paths["allocation_root"]) in body
    shared=module("stage12_ra_g1_nonwaiting_submit")
    submit=commands.render_submission(allocation=selection,selection_sha256=sr["sha256"],
        gate_sha256="c"*64,helper_sha256="d"*64,nonce="e"*32,shared=shared,
        deadline_epoch_ns=commands.WINDOW_END_NS)
    assert submit["command_scoped_sbatch_argv"][:3]==["env","-u","SBATCH_WAIT"]
    assert "--wait" not in submit["raw_sbatch_argv"]
    assert "test ! -e "+shlex.quote(paths["allocation_root"]) in submit["prefix"]
    assert submit["native_layout"]==result["native_layout"]
    # Emitted production native command is retained verbatim.  No local shell
    # execution of rebased literals is counted as native command proof.
    target=os.environ.get("STAGE12_LAYOUT_EVIDENCE")
    if target:
        put(Path(target)/"ACTUAL_NATIVE_COMMANDS_TEST_ONLY.record",canonical(result|{"submission":submit}))

def test_pretrace_mapper_exact_type_secret_safe():
    d=module("stage12_ra_g1_diagnostic")
    class SecretEq:
        def __eq__(self,other):raise AssertionError("MUST_NOT_COMPARE")
    class Subclass(RuntimeError):pass
    assert d.safe_failure(RuntimeError("RA_G1_DIAGNOSTIC_PATH_SCOPE"))["code"]=="RA_G1_DIAGNOSTIC_PATH_SCOPE"
    for exc in (RuntimeError(SecretEq()),Subclass("RA_G1_DIAGNOSTIC_PATH_SCOPE"),
                RuntimeError("RA_G1_DIAGNOSTIC_PATH_SCOPE secret"),ValueError("secret")):
        assert "secret" not in json.dumps(d.safe_failure(exc)).lower()
        assert d.safe_failure(exc)["code"]!="RA_G1_DIAGNOSTIC_PATH_SCOPE"

def test_actual_execute_connected_selected_startup(tmp_path):
    """Real caller/Authority/audit/START, controlled stop before CAPTURE."""
    import subprocess,time
    evidence=os.environ.get("STAGE12_LAYOUT_EVIDENCE")
    if not evidence:
        pytest.skip("Explicit retained fixture asset selection required")
    evidence=Path(evidence)
    fixture=evidence/"selected_startup_fixture.py"
    old=Path(os.environ["STAGE12_LAYOUT_OLD_SELECTION"])
    root=tmp_path/"actual_connected";root.mkdir(mode=0o700)
    os.chmod(tmp_path,0o700)
    entry=time.monotonic_ns();deadline=entry+180_000_000_000
    results=[]
    for role in("admin","phase"):
        remaining=(deadline-time.monotonic_ns())/1e9
        assert remaining>5
        argv=[sys.executable,"-B",str(fixture),"--mode",role,"--fixture",str(root),
              "--repo",str(ROOT),"--selection",str(old)]
        started=time.monotonic_ns()
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1"))
        timed_out=False;cleanup_uncertain=False
        child_deadline=min(deadline,started+120_000_000_000)
        active=(child_deadline-time.monotonic_ns())/1e9-5
        assert active>0
        try:
            stdout,stderr=child.communicate(timeout=active)
        except subprocess.TimeoutExpired as expired:
            timed_out=True;child.terminate()
            stdout,stderr=expired.output or b"",expired.stderr or b""
            remaining=(child_deadline-time.monotonic_ns())/1e9-1
            if remaining>0:
                try:stdout,stderr=child.communicate(timeout=remaining)
                except subprocess.TimeoutExpired as pending:
                    stdout,stderr=pending.output or b"",pending.stderr or b""
            if child.poll() is None:
                child.kill()
                remaining=(child_deadline-time.monotonic_ns())/1e9
                if remaining>0:
                    try:stdout,stderr=child.communicate(timeout=remaining)
                    except subprocess.TimeoutExpired as pending:
                        stdout,stderr=pending.output or b"",pending.stderr or b""
            cleanup_uncertain=child.poll() is None
        completed=time.monotonic_ns()
        assert len(stdout)+len(stderr)<=2**20
        operation=dict(role=role,pid=child.pid,parent_pid=os.getpid(),argv=argv,
            entry_mono_ns=started,completed_mono_ns=completed,exit=child.returncode,
            timed_out=timed_out,cleanup_uncertain=cleanup_uncertain,joined=child.poll() is not None,stdout_bytes=len(stdout),stderr_bytes=len(stderr))
        put(evidence/(role.upper()+"_CHILD_OPERATION.record"),canonical(operation))
        put(evidence/(role.upper()+"_CHILD.stdout"),stdout)
        put(evidence/(role.upper()+"_CHILD.stderr"),stderr)
        assert completed<=child_deadline and not timed_out and child.returncode==0, (operation,stdout.decode(errors="replace"),stderr.decode(errors="replace"))
        actual=json.loads((root/(role.upper()+"_RESULT.record")).read_bytes())
        assert actual["complete"]is True
        results.append(actual)
        if role=="admin":
            s=json.loads((root/"SELECTION.record").read_bytes())
            assert actual["local_process_pid"]==child.pid and actual["parent_pid"]==os.getpid()
            record=dict(version="stage12_ra_g1_supervisor_wait_v1",source_sha=s["source_sha"],
                selection_sha256=hashlib.sha256(canonical(s)).hexdigest(),pid=child.pid,wait_status=0,
                exit_code=child.returncode,supervisor_pid=os.getpid(),acquired_mono_ns=completed)
            logical=PurePosixPath(actual["parent_wait_destination"])
            wait_path=root/"native-root/panfs"/logical.relative_to("/panfs")
            put(wait_path,canonical(record))
            put(evidence/"ACTUAL_PARENT_WAIT_PROVENANCE.record",canonical(dict(
                status="TEST_ONLY_GENUINE_POPEN_WAIT_ONLY",operation=operation,record=record,
                historical_or_native_success=False)))
    phase=results[-1]
    assert phase["first_phase_returned"]is True
    assert phase["summary"]["attempts"]==0 and phase["summary"]["complete"]is False
    assert phase["CAPTURE_entries"]==0
    assert phase["nonmain_live_threads"]==[]
    required={"ACTUAL_DIAGNOSTIC_AUDIT_BEFORE_INPUT","ACTUAL_FIRST_SCENARIO_RESOURCE_SESSION",
        "ACTUAL_COMPLETE_CURRENT_SOURCE_FENCE",
        "ACTUAL_PREPARE_FIRST_PHASE_RETURN_AFTER_START_ACK_INITIALIZATION_AND_BODIES"}
    assert required<=set(phase["sequence"])
    assert phase["audit_events"]>100
    assert results[0]["source_rows"]==947
    for package,origins in phase["project_package_origins"].items():
        assert origins==[str(PurePosixPath(s["paths"]["source"])/"src"/Path(*package.split(".")))]
    put(evidence/"CONNECTED_RESULT_TEST_ONLY.record",canonical(dict(
        disposition="TEST_ONLY_CONNECTED_STARTUP_PASS_TRUTHFUL_ABORT_NO_B_QUALIFICATION",
        entry_mono_ns=entry,completed_mono_ns=time.monotonic_ns(),admin=results[0],phase=phase,
        native_command_preparation="NOT_EXECUTED_ON_MAC_REQUIRES_ACTUAL_GOETHE_SETUP",
        original_selection_sha256=hashlib.sha256(old.read_bytes()).hexdigest())))

@pytest.mark.parametrize("case",["mode","symlink","file","owner"])
def test_actual_private_layout_guard_rejects_unsafe_directory(tmp_path,monkeypatch,case):
    d=module("stage12_ra_g1_diagnostic")
    controlled=tmp_path/"controlled";controlled.mkdir(mode=0o700)
    root=controlled/"ra_g1_fixture";root.mkdir(mode=0o700)
    bundle=root/"binding";bundle.mkdir(mode=0o700)
    assert d.public_input_layout(root/"input.json",bundle,controlled)
    if case=="mode":root.chmod(0o755)
    elif case=="symlink":
        bundle.rmdir();target=tmp_path/"target";target.mkdir(mode=0o700);bundle.symlink_to(target,target_is_directory=True)
    elif case=="file":
        bundle.rmdir();bundle.write_bytes(b"not a directory")
    elif case=="owner":monkeypatch.setattr(os,"geteuid",lambda:root.stat().st_uid+1)
    assert not d.public_input_layout(root/"input.json",bundle,controlled)

def test_materializer_rejects_changed_bound_original_before_native_command(commands,tmp_path):
    paths=corrected_paths()
    allocation={"source_sha":"a"*40,"scope":"REPRESENTATIVE_NO_SERVICE","paths":paths,
      "accounting_inventory":{"backends":[{"path":"/runtime/lib"+str(n)}for n in range(5)]}}
    sr=put(tmp_path/"SELECTION.record",canonical(allocation))
    ur=put(tmp_path/"UPLOADS.record",canonical([]))
    Path(sr["path"]).write_bytes(canonical(allocation)+b" ")
    prepared={"status":"CANONICAL_BINDINGS_GENERATED_NOT_NATIVE_READY_OR_SUBMISSION",
      "source_sha":allocation["source_sha"],"selection":sr,"record_uploads":ur}
    with pytest.raises(RuntimeError):
        commands.materialize_preparation(prepared=prepared,allocation=allocation,source_tree="b"*40,
          backend_inventory=allocation["accounting_inventory"]["backends"],output=tmp_path/"staged",write=put)
    assert not(tmp_path/"staged").exists()

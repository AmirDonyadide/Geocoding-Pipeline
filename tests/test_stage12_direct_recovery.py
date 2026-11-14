"""Tiny actual direct exporter/transport/opener; all scheduler facts TEST_ONLY.

The endpoint fixture serves real producer bytes with genuine cat children. It
replaces only authenticated SSH's endpoint representation, never a validator.
"""
from __future__ import annotations
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import stage12_ra_g1_direct_recovery as direct
import stage12_ra_g1_terminal_collect as tc

spec=importlib.util.spec_from_file_location("direct_transport_fixture",ROOT/"tests/test_stage12_ra_g1_terminal_transport.py")
fixture_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture_module)


def put(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view);assert n>0;view=view[n:]
        os.fsync(fd)
    finally: os.close(fd)


def case(tmp_path):
    root=tmp_path/"case";root.mkdir(mode=0o700)
    for name in ("allocation","records","failed_pair","failed_bindings"):
        (root/name).mkdir(mode=0o700)
    put(root/"allocation/input.json",b'{"TEST_ONLY":"invented failed workload"}\n')
    put(root/"records/slurm.log",b"TEST_ONLY FAILED1:0\n")
    put(root/"records/slurm.err",b"TEST_ONLY retained stderr\n")
    original_selection=tc.canonical(dict(source_sha="a"*40,scope="REPRESENTATIVE_NO_SERVICE",version="TEST_ONLY_INVENTED_UNSUPPORTED_FULL_WORKLOAD"))
    put(root/"records/FINAL_SELECTION.record",original_selection)
    put(root/"failed_pair/PAIR_INCOMPLETE.record",b'{"TEST_ONLY":true,"status":"INCOMPLETE"}\n')
    put(root/"failed_pair/partial.original",b"TEST_ONLY partial data\0")
    put(root/"failed_bindings/binding.record",b"TEST_ONLY actual binding original\n")
    put(root/"collection.stdout",b"TEST_ONLY collection stdout\n")
    put(root/"collection.stderr",b"TEST_ONLY collection stderr\n")
    os.mkfifo(root/"allocation/supervisor_wait.fifo",0o600)
    limits=dict(members=64,payload_bytes=1048576,manifest_bytes=262144,
        record_bytes=4096,path_bytes=1024,name_bytes=255,depth=16,sort_records=16,
        sort_buffer_bytes=131072,merge_fan_in=2,chunk_bytes=4096,wire_bytes=2097152,
        read_bytes=33554432,write_bytes=33554432,creations=512,operations=1000000,
        scanned_entries=2048,seconds=30)
    end=time.time_ns()+120*10**9
    selection=dict(version=tc.FIFO_VERSION,scope="TEST_ONLY_INVENTED",state="TEMPLATE",
        approval_sha256=None,source_uid=os.geteuid(),source_gid=os.getegid(),job_id=11,
        source_git_sha="a"*40,roots=[dict(label=n,path=str(root/n)) for n in
        ("allocation","records","failed_pair","failed_bindings")],
        external_files=[dict(label=n,path=str(root/("collection."+n))) for n in ("stdout","stderr")],
        required_logs=["records/slurm.log","records/slurm.err","stdout","stderr"],
        limits=limits,valid_until_epoch_ns=end,inert_fifos=[])
    consumers=[]
    for name in sorted(direct.DIRECT_CONSUMER_PATHS):
        raw=(ROOT/name).read_bytes();consumers.append(dict(path=name,bytes=len(raw),sha256=direct.digest(raw)))
    original=lambda role,job,kind:dict(role=role,job_id=job,source_git_sha="a"*40,
        identity_kind=kind,identity_sha256="1"*64,terminal_sha256="2"*64)
    plan=dict(version=direct.PLAN_VERSION,scope=direct.SCOPE,nonce="1"*32,
        approval_sha256="3"*64,purpose="OLD_B_F_RECOVERY",
        originals=[original("B",11,"ALLOCATION_SELECTION"),original("F",12,"COLLECTION_BINDING")],
        software=dict(source_git_sha="d"*40,inventory_sha256=direct.consumer_digest(consumers),consumer_inventory=consumers),
        selection_template=selection,allowed_inert_fifos=["allocation/supervisor_wait.fifo"],
        required_inert_fifos=["allocation/supervisor_wait.fifo"],window_end_epoch_ns=end,test_only=True)
    plan["export_logs"]=[dict(label="export_stdout",path=str(root/"export-client.stdout")),
                         dict(label="export_stderr",path=str(root/"export-client.stderr"))]
    plan["originals"][0]["identity_sha256"]=direct.digest(original_selection)
    plan["original_workload"]=dict(selection_path=str(root/"records/FINAL_SELECTION.record"),
        selection_sha256=direct.digest(original_selection),verifier_sha256=next(row["sha256"] for row in consumers
            if row["path"]=="scripts/stage12_ra_g1_terminal_verify.py"),required_for_B_acceptance=False)
    return root,plan


def exported(root,plan):
    raw=tc.canonical(plan);config=root/"plan.record";put(config,raw)
    argv=[str(ROOT/".venv/bin/python"),"-B",str(ROOT/"scripts/stage12_ra_g1_direct_recovery.py"),"export",
        "--plan",str(config),"--plan-sha256",direct.digest(raw),"--output",str(root/"export"),
        "--window-end-epoch-ns",str(plan["window_end_epoch_ns"]),
        "--export-end-epoch-ns",str(time.time_ns()+60*10**9),"--offline-invented","--test-root",str(root)]
    env=dict(os.environ,PYTHONPATH=str(ROOT/"src"),PYTHONDONTWRITEBYTECODE="1")
    started=time.monotonic_ns();proc=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    try: stdout,stderr=proc.communicate(timeout=15)
    except BaseException:
        proc.kill();proc.communicate(timeout=2);raise
    assert len(stdout)+len(stderr)<65536
    put(root/"export-client.stdout",stdout);put(root/"export-client.stderr",stderr)
    put(root/"EXPORT_CLIENT.record",tc.canonical(dict(TEST_ONLY=True,argv=argv,pid=proc.pid,
        entered_mono_ns=started,completed_mono_ns=time.monotonic_ns(),exit_code=proc.returncode,
        stdout_eof=True,stderr_eof=True,observed_joined=True)))
    return proc.returncode,stdout,stderr


def endpoints(root,mutation=None):
    counter=[0]
    def batch(rows):
        counter[0]+=1;here=root/f"endpoint{counter[0]:02d}";here.mkdir(mode=0o700)
        return fixture_module.framed_fixture(here,rows,mutation=mutation if counter[0]==2 else None)
    return batch


def recover(root,plan,monkeypatch,mutation=None):
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT","1")
    return direct.recover_archive(plan,root/"export",root/"local",offline=True,test_root=root,
        export_terminal=dict(kind="TEST_ONLY_ACTUAL_LOCAL_CHILD",exit_code=0),
        testing_batch_factory=endpoints(root,mutation))


def complete_fixture(tmp_path,monkeypatch):
    """Portable TEST_ONLY real-child specimen for matched-gate regression."""
    root,plan=case(tmp_path);code,_,stderr=exported(root,plan);assert code==0,stderr
    proof=recover(root,plan,monkeypatch)
    reopened=direct.reopen_recovery(plan,proof,root/"local",root/"independent",offline=True,test_root=root)
    review=dict(version=direct.REVIEW_VERSION,status="PASS",independent_review=True,
        reviewer_role="INDEPENDENT_REVIEWER",actual_reopened=True,reopen=reopened,
        result_sha256=direct.digest(tc.canonical(proof)),**{key:proof[key] for key in
        ("plan_sha256","software_source_sha","software_inventory_sha256","recovery_consumer_inventory_sha256")})
    put(root/"TEST_ONLY_REVIEW.record",tc.canonical(review))
    return root,plan,proof,review


def test_actual_export_child_transport_decode_and_independent_reopening(tmp_path,monkeypatch):
    root,plan,proof,review=complete_fixture(tmp_path,monkeypatch)
    assert proof["archive_open"]["status"]=="COMPLETE"
    assert proof["originals"][0]["source_git_sha"]=="a"*40!=proof["software_source_sha"]
    assert not proof["native_or_scientific_acceptance"] and proof["original_outcomes_unchanged"]
    assert proof["workload_verification"]["complete"] is False
    assert proof["workload_verification"]["first_failure"]["code"]=="TERMINAL_ORIGINAL_INVALID"
    for fact in proof["transport"].values():
        assert fact["exit_code"]==0 and fact["observed_joined"]
        assert fact["domain_before"]==fact["domain_after"]
    for name in ("allocation/input.json","records/slurm.log","records/slurm.err",
                 "failed_pair/PAIR_INCOMPLETE.record","failed_pair/partial.original","failed_bindings/binding.record"):
        assert (root/"local/mirror/originals"/name).read_bytes()==(root/name).read_bytes()
    assert not (root/"local/mirror/originals/allocation/supervisor_wait.fifo").exists()
    inert=list((root/"local/mirror/inert-metadata").glob("*.record"));assert len(inert)==1
    assert json.loads(inert[0].read_bytes())["kind"]=="FIFO_INERT"
    reopened=review["reopen"]
    assert reopened["complete_mirror_rehashed"] and reopened["read_calls"]<=131072
    # This invented review tests the codec only; it is never live authority.
    kwargs=dict(review=review,expected_plan_sha256=proof["plan_sha256"],
        expected_software_source_sha=proof["software_source_sha"],expected_software_inventory_sha256=proof["software_inventory_sha256"],
        expected_review_sha256=direct.digest(tc.canonical(review)),expected_consumer_inventory_sha256=proof["recovery_consumer_inventory_sha256"])
    assert direct.validate_recovery_proof(proof,allow_test_only=True,**kwargs) is proof
    # Match the real native gate's read-only source-loader namespace. This is
    # the actual validator, with only the explicit TEST_ONLY unit opt-in.
    source=ROOT/"scripts/stage12_ra_g1_direct_recovery.py"
    namespace={"__file__":str(source),"__name__":"actual_collection_qualification"}
    exec(compile(source.read_bytes(),str(source),"exec"),namespace)
    assert namespace["validate_recovery_proof"](proof,allow_test_only=True,**kwargs) is proof
    with pytest.raises(RuntimeError,match="DIRECT_PROOF"):
        direct.validate_recovery_proof(proof,**kwargs)
    for name in ("originals","software_source_sha","software_inventory_sha256","recovery_consumer_inventory"):
        wrong=deepcopy(proof)
        if name=="originals": wrong[name][0]["identity_sha256"]="f"*64
        elif name=="recovery_consumer_inventory": wrong[name][0]["sha256"]="f"*64
        else: wrong[name]="f"*(40 if name=="software_source_sha" else 64)
        rejected=root/("must-not-create-"+name)
        with pytest.raises((RuntimeError,tc.Stop)):
            direct.reopen_recovery(plan,wrong,root/"local",rejected,offline=True,test_root=root)
        assert not rejected.exists()


@pytest.mark.parametrize("mutation",["metadata","domain","truncated","excess"])
def test_real_transport_rejects_changed_or_truncated_framing(tmp_path,monkeypatch,mutation):
    root,plan=case(tmp_path);assert exported(root,plan)[0]==0
    with pytest.raises((tc.Stop,RuntimeError)) as caught: recover(root,plan,monkeypatch,mutation)
    failure=caught.value.direct_recovery_failure
    assert failure["operation"]=="COMPLETE_TRANSFER" and failure["status"]=="INCOMPLETE"
    assert not (root/"local/DIRECT_RECOVERY_RESULT.record").exists()
    assert (root/"local/DIRECT_RECOVERY_INCOMPLETE.record").exists()
    assert failure["transport"] is not None


@pytest.mark.parametrize("kind",["missing-log","missing-fifo","unknown-fifo","symlink"])
def test_exporter_actual_entry_rejects_missing_or_unsafe_originals(tmp_path,kind):
    root,plan=case(tmp_path)
    if kind=="missing-log": (root/"records/slurm.err").unlink()
    elif kind=="missing-fifo": (root/"allocation/supervisor_wait.fifo").unlink()
    elif kind=="unknown-fifo": os.mkfifo(root/"failed_pair/undeclared.fifo",0o600)
    else: (root/"allocation/link").symlink_to(root/"records/slurm.log")
    code,_,stderr=exported(root,plan);assert code==2
    failure=json.loads(stderr)
    assert failure["operation"] in ("BIND_SOURCE","EXPORT")
    assert failure["first_failure"]["exception_class"] in ("RUNTIME_ERROR","COLLECTION_CORE_STOP")
    assert not (root/"export/DIRECT_EXPORT.record").exists()
    assert all("text" not in row and "locals" not in row for row in failure["first_failure"]["frames"])


def test_full_mirror_reopen_rejects_changed_content(tmp_path,monkeypatch):
    root,plan=case(tmp_path);assert exported(root,plan)[0]==0;proof=recover(root,plan,monkeypatch)
    path=root/"local/mirror/originals/allocation/input.json"
    with path.open("ab") as stream: stream.write(b"MUTATED")
    with pytest.raises((tc.Stop,RuntimeError)):
        direct.reopen_recovery(plan,proof,root/"local",root/"independent",offline=True,test_root=root)
    assert (root/"independent/DIRECT_REOPEN_INCOMPLETE.record").exists()


@pytest.mark.parametrize("label",["selection","export","export_stdout","export_stderr","workload"])
def test_independent_reopen_rehashes_all_retained_controls_and_logs(tmp_path,monkeypatch,label):
    root,plan=case(tmp_path);assert exported(root,plan)[0]==0;proof=recover(root,plan,monkeypatch)
    with (root/"local/artifacts"/(label+".original")).open("ab") as stream: stream.write(b"MUTATED")
    with pytest.raises((tc.Stop,RuntimeError)):
        direct.reopen_recovery(plan,proof,root/"local",root/"independent",offline=True,test_root=root)
    assert (root/"independent/DIRECT_REOPEN_INCOMPLETE.record").exists()


def test_changed_archive_hash_is_rejected_by_actual_transfer(tmp_path,monkeypatch):
    root,plan=case(tmp_path);assert exported(root,plan)[0]==0
    path=root/"export/terminal.s12c"
    with path.open("r+b") as stream: stream.seek(16);stream.write(b"BAD")
    with pytest.raises(tc.Stop) as caught: recover(root,plan,monkeypatch)
    assert caught.value.direct_recovery_failure["operation"]=="COMPLETE_TRANSFER"


def test_optional_fifo_absence_retained_explicitly(tmp_path,monkeypatch):
    root,plan=case(tmp_path);plan["required_inert_fifos"]=[]
    (root/"allocation/supervisor_wait.fifo").unlink()
    assert exported(root,plan)[0]==0
    proof=recover(root,plan,monkeypatch)
    assert proof["export"]["fifo_status"]==[dict(path="allocation/supervisor_wait.fifo",status="ABSENT_ENOENT")]
    assert proof["selection"]["inert_fifos"]==[]


@pytest.mark.parametrize("field",["roots","approval_sha256","valid_until_epoch_ns","limits"])
def test_actual_issued_selection_replay_rejects_mixed_plan_before_data_open(tmp_path,field):
    root,plan=case(tmp_path);assert exported(root,plan)[0]==0
    issued=json.loads((root/"export/selection.record").read_bytes())
    assert direct._selected_cohort(plan,issued,offline=True,test_root=root).sha==direct.digest(tc.canonical(issued))
    wrong=deepcopy(plan)
    if field=="roots": wrong["selection_template"]["roots"]=wrong["selection_template"]["roots"][:2]
    elif field=="approval_sha256":
        # Offline's actual strict selection remains approvalNone; the native
        # issued representation must never enter this TEST_ONLY validator.
        issued["scope"]="NATIVE_TERMINAL_ORIGINALS";issued["state"]="ISSUED";issued["approval_sha256"]="f"*64
    elif field=="valid_until_epoch_ns":
        wrong["window_end_epoch_ns"]+=1;wrong["selection_template"][field]+=1
    else: wrong["selection_template"]["limits"]["payload_bytes"]-=1
    with pytest.raises((RuntimeError,tc.Stop)):
        direct._selected_cohort(wrong,issued,offline=True,test_root=root)


def test_shared_pre_read_stops_include_codec_and_direct_reads(tmp_path):
    root,plan=case(tmp_path);selected=direct.validate_plan(plan,offline=True,test_root=root)
    role=direct.Role(selected,time.monotonic_ns(),plan["window_end_epoch_ns"])
    fd=os.open(root/"records/slurm.log",os.O_RDONLY)
    try:
        role.budget.maximum_calls=2
        assert role.read(fd,1) and role.budget.read(fd,1) and role.read_calls==2
        with pytest.raises(RuntimeError,match="DIRECT_PROOF"): role.read(fd,1)
    finally: os.close(fd)


@pytest.mark.parametrize("kind",[KeyboardInterrupt,SystemExit])
def test_optional_scientific_negative_handler_never_absorbs_interruption(tmp_path,monkeypatch,kind):
    root,plan=case(tmp_path);selected=direct.validate_plan(plan,offline=True,test_root=root)
    role=direct.Role(selected,time.monotonic_ns(),plan["window_end_epoch_ns"],native_export=True)
    original=kind()
    def interrupted(*args,**kwargs): raise original
    monkeypatch.setattr(direct.verifier,"verify_original_workload",interrupted)
    with pytest.raises(kind) as caught:
        direct._workload(plan,role,direct.diagnostics.FirstFailureDescriptor())
    assert caught.value is original


def test_candidate_b_only_archive_cannot_cover_failed_collection(tmp_path):
    root,plan=case(tmp_path);old=deepcopy(plan["selection_template"])
    old["roots"]=old["roots"][:2];old["external_files"]=[]
    assert not direct.cohort_matches(plan,old)


def test_native_export_guard_precedes_plan_input(tmp_path):
    env=dict(os.environ,PYTHONPATH=str(ROOT/"src"));env.pop("SAFE_EXECUTION_SITE",None);env.pop("SLURM_JOB_ID",None)
    argv=[str(ROOT/".venv/bin/python"),"-B",str(ROOT/"scripts/stage12_ra_g1_direct_recovery.py"),"export",
        "--plan",str(tmp_path/"must-not-open"),"--plan-sha256","0"*64,"--output",str(tmp_path/"must-not-create"),
        "--window-end-epoch-ns",str(time.time_ns()+30*10**9),"--export-end-epoch-ns",str(time.time_ns()+30*10**9)]
    done=subprocess.run(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert done.returncode==2 and json.loads(done.stderr)["code"]!="UNCLASSIFIED_FILE_NOT_FOUND"
    assert not (tmp_path/"must-not-create").exists()

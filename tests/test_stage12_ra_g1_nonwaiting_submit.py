"""Focused operating-only tests; every job/accounting row below is invented."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import pytest

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/"scripts"
if str(SCRIPTS) not in sys.path:sys.path.insert(0,str(SCRIPTS))
import stage12_ra_g1_nonwaiting_submit as m
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_collect as tc
NONCE="a"*32
JOB=70000000009999
UID=60099
CHILDREN=[]

def rows(state="COMPLETED",code="0:0",uid=str(UID)):
 return "".join(str(JOB)+suffix+"|"+state+"|"+code+"|2026-11-12T07:52:19|2026-11-12T07:55:18|"+(uid if not suffix else "")+"|footprint|"+("general1" if not suffix else "")+"\n" for suffix in ("",".batch",".extern"))

def wire(body=None):
 return ("S12TERM1|BEGIN|"+NONCE+"|"+str(JOB)+"|1794470000.123456\n"+(rows() if body is None else body)).encode()

def parser(raw,rc=0):
 p=m.QueryParser(JOB,NONCE,UID);p.feed(raw);return p.finish(rc)

@pytest.mark.parametrize("flag",["--wait","--wait=1","-W","-Wv","-vW","--parsable=1","--wai","--requeue"])
def test_reject_wait_and_unsupported_option_aliases(flag):
 with pytest.raises(m.Stop):m.ordinary_sbatch_argv(["sbatch","--parsable",flag,"fixture"])

def test_submit_prefix_and_command_scoped_unset():
 script=m.submit_builder(": TEST_ONLY",["sbatch","--parsable","fixture"],NONCE,1794510801620987000,1800)
 assert script.endswith("exec env -u SBATCH_WAIT sbatch --parsable fixture\n")
 assert "unset SBATCH_WAIT" not in script and "selected_now_ns" in script
 assert "SECONDS=0" not in script and "--wait" not in script
 assert m.submission_argv(": TEST_ONLY",["sbatch","--parsable","fixture"],NONCE,1794510801620987000,1800)[-1].startswith("exec bash -c ")

def test_submit_distinct_contract_and_cluster_rejection():
 p=m.SubmitParser(NONCE,1794510801620987000,1800)
 p.feed(("S12SUB3|BEGIN|"+NONCE+"|1794510801620987000|1800|5.1.8(1)-release\n"+str(JOB)+"\n").encode())
 f=p.finish(0)
 assert f["submit_client_exit"]==0 and "wait_exit" not in f and f["job_success"] is False
 p=m.SubmitParser(NONCE,1794510801620987000,1800)
 p.feed(("S12SUB3|BEGIN|"+NONCE+"|1794510801620987000|1800|5.1.8(1)-release\n"+str(JOB)+";unbound_cluster\n").encode())
 assert p.submitted["parsable_id"].endswith(";unbound_cluster")
 with pytest.raises(m.Stop,match="SUBMIT_CLUSTER"):p.finish(0)

def test_submit_bad_exit_truncation_extra_and_legacy_frame():
 for raw,rc in [(b"",7),(b"S12SUB2|BEGIN|x\n",0),(b"S12SUB3|BEGIN|x",0)]:
  p=m.SubmitParser(NONCE,1794510801620987000,1800)
  with pytest.raises(m.Stop):p.feed(raw);p.finish(rc)
 p=m.SubmitParser(NONCE,1794510801620987000,1800)
 with pytest.raises(m.Stop):p.feed(("S12SUB3|BEGIN|"+NONCE+"|1794510801620987000|1800|5.1.8(1)-release\n123\n124\n").encode())

def test_query_complete_pending_missing_and_failed_states():
 f=parser(wire());assert f["status"]=="AUTHORITATIVE_TERMINAL" and f["all_completed_zero"]
 assert f["native_query_start_epoch_ns"]==1794470000123456000
 assert f["observation_clock_scope"]=="LOCAL_CONTROLLER_AFTER_GENUINE_QUERY_CLIENT_EXIT"
 assert parser(wire(""))["status"]=="ACCOUNTING_PENDING"
 assert parser(wire(rows().splitlines()[0]+"\n"))["status"]=="ACCOUNTING_PENDING"
 assert parser(wire(rows("RUNNING")))["status"]=="NONTERMINAL"
 f=parser(wire(rows("FAILED","1:0")));assert f["status"]=="AUTHORITATIVE_TERMINAL" and not f["all_completed_zero"]

def test_query_reject_mismatch_duplicates_foreign_truncated():
 bad=[wire(rows(uid="1")),wire(rows()+rows().splitlines()[0]+"\n"),wire(rows().replace(str(JOB)+".extern",str(JOB)+".unexpected")),wire()[:-1],wire().replace(b"1794470000.123456",b"not_a_clock")]
 for raw in bad:
  with pytest.raises(m.Stop):parser(raw)
 with pytest.raises(m.Stop,match="QUERY_EXIT"):parser(wire(),7)

def test_policy_closed_and_legacy_unchanged():
 assert pair.SELECTED_PAIR_ADMISSION_VERSION=="stage12_collection_selected_pair_admission_v2"
 assert dict(pair.SELECTED_PAIR_CONTROL_LIMITS)["maximum_process_units"]==228
 new=dict(pair.NONWAITING_TERMINAL_LIMITS,module_sha256="a"*64)
 assert pair.validate_nonwaiting_terminal_policy(new)==new
 for key,value in [("maximum_queries",17),("query_seconds",16),("minimum_start_spacing_seconds",119),("query_process_units",3)]:
  changed=dict(new);changed[key]=value
  with pytest.raises(tc.Stop):pair.validate_nonwaiting_terminal_policy(changed)

def real_query(tmp_path,raw=None,exit_code=0,sleep=0,owner_seconds=3,record_failure=False):
 tmp_path.mkdir(mode=0o700,parents=True,exist_ok=True);os.chmod(tmp_path,0o700)
 selected=wire() if raw is None else raw
 code="import os,time;time.sleep("+repr(sleep)+");os.write(1,"+repr(selected)+");raise SystemExit("+str(exit_code)+")"
 argv=[sys.executable,"-c",code]
 entered=time.monotonic_ns();owner=pair.Control(entered,time.time_ns()+int(owner_seconds*1000000000),owner_seconds)
 records=[];charges=[]
 def record(name,value):
  records.append(value)
  if record_failure:raise RuntimeError("INVENTED_SECRET_ARGUMENT_MUST_NOT_BE_RETAINED")
  return owner.record(tmp_path/name,value)
 def charge(label,units):charges.append((label,units))
 try:
  value=m.run_query(argv,m.QueryParser(JOB,NONCE,UID),owner,record,"TERMINAL_QUERY_01",charge)
  return value,records,charges,owner
 finally:
  CHILDREN.append(dict(argv_kind="CONTROLLED_LOCAL_PYTHON_SUBPROCESS",records=records,charges=charges,read_calls=owner.read_calls,read_bytes=owner.read_bytes,creations=owner.creations))

def test_real_child_success_and_durable_record(tmp_path):
 facts,records,charges,owner=real_query(tmp_path/"success")
 assert facts["all_completed_zero"] and charges==[("TERMINAL_QUERY_01",4)]
 assert owner.creations==2 and records[0]["actual_client_exit"]==0 and records[0]["joined"]
 assert records[0]["stdout_eof"] and records[0]["stderr_eof"] and not records[0]["cleanup_uncertain"]
 assert len(tc.canonical(records[0]))<=m.QUERY_RECORD_BYTES
 assert tc.parse((tmp_path/"success/TERMINAL_QUERY_01.record").read_bytes())["facts"]["all_completed_zero"]

def test_real_child_pending(tmp_path):
 facts,records,_,_=real_query(tmp_path/"pending",wire(""))
 assert facts["status"]=="ACCOUNTING_PENDING" and records[0]["actual_client_exit"]==0

def test_real_child_terminal_failure(tmp_path):
 facts,records,_,_=real_query(tmp_path/"failed_job",wire(rows("FAILED","1:0")))
 assert facts["status"]=="AUTHORITATIVE_TERMINAL" and not facts["all_completed_zero"]

def test_real_child_identity_mismatch(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_IDENTITY"):real_query(tmp_path/"mismatch",wire(rows(uid="1")))

def test_real_child_truncated(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_FRAME"):real_query(tmp_path/"truncated",wire()[:-1])

def test_real_child_exit_seven(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_EXIT"):real_query(tmp_path/"exit7",exit_code=7)
 assert CHILDREN[-1]["records"][0]["actual_client_exit"]==7 and CHILDREN[-1]["records"][0]["joined"]

def test_real_child_expiry_and_cleanup(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_DEADLINE"):real_query(tmp_path/"expiry",sleep=2,owner_seconds=1)
 row=CHILDREN[-1]["records"][0]
 assert row["joined"] and row["signals"] and row["actual_client_exit"] is not None
 assert row["completed_mono_ns"]<=row["cleanup_deadline_mono_ns"]

def test_real_child_uncertain_persistence_retains_lifecycle(tmp_path):
 with pytest.raises(RuntimeError) as found:real_query(tmp_path/"persist",record_failure=True)
 error=found.value
 assert error.query_persistence_uncertain and error.terminal_query_diagnostic["actual_client_exit"]==0
 assert "INVENTED_SECRET_ARGUMENT" not in json.dumps(error.terminal_query_diagnostic)

def test_real_child_primary_precedes_persistence(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_EXIT") as found:real_query(tmp_path/"primary",exit_code=7,record_failure=True)
 assert found.value.query_persistence_uncertain and found.value.terminal_query_diagnostic["actual_client_exit"]==7

def test_real_child_output_limit(tmp_path):
 with pytest.raises(m.Stop,match="QUERY_OUTPUT_LIMIT"):real_query(tmp_path/"overflow",raw=b"x"*5000)
 row=CHILDREN[-1]["records"][0]
 assert row["stdout_truncated"] and row["joined"]


def test_query_bank_closed_exhaustion_and_nonreset():
 bank=m.new_query_bank()
 assert bank["maximum"]==16 and bank["normal_slots"]==13 and bank["cancellation_slots"]==3
 owner=pair.Control(time.monotonic_ns(),time.time_ns()+1000000000,1)
 first=m.reserve_query_start(owner,bank)
 assert first["ordinal"]==1 and bank["used"]==1
 before=dict(bank)
 with pytest.raises(tc.Stop,match="DEADLINE"):m.reserve_query_start(owner,bank)
 assert bank==before  # No second admission occurred and no origin/counter was reset.
 full=m.new_query_bank();full.update(used=13,normal_used=13,last_started_mono_ns=time.monotonic_ns()-120000000000)
 owner2=pair.Control(time.monotonic_ns(),time.time_ns()+1000000000,1)
 with pytest.raises(m.Stop,match="QUERY_LIMIT"):m.reserve_query_start(owner2,full)
 with pytest.raises(m.Stop):m.new_query_bank(normal_slots=15,cancellation_slots=3)


@pytest.mark.skipif(os.environ.get("SAFE_STAGE12_REAL_QUERY_SPACING_TEST") != "1", reason="explicitly selected 120-second interface timing case")
def test_query_bank_genuine_120_second_starts(tmp_path):
 root=tmp_path/"spacing";root.mkdir(mode=0o700);os.chmod(root,0o700)
 owner=pair.Control(time.monotonic_ns(),time.time_ns()+150000000000,150)
 bank=m.new_query_bank();charges=[];records=[]
 def record(name,value):records.append(value);return owner.record(root/name,value)
 def charge(label,units):charges.append((label,units))
 code="import os;os.write(1,"+repr(wire())+")"
 facts=[]
 for n in (1,2):
  facts.append(m.run_query([sys.executable,"-c",code],m.QueryParser(JOB,NONCE,UID),owner,record,"TERMINAL_QUERY_"+str(n).zfill(2),charge,bank=bank))
  CHILDREN.append(dict(argv_kind="CONTROLLED_LOCAL_PYTHON_SPACING",records=[records[-1]],charges=[charges[-1]],read_calls=owner.read_calls,read_bytes=owner.read_bytes,creations=owner.creations))
 assert facts[1]["query_entered_mono_ns"]-facts[0]["query_entered_mono_ns"]>=120000000000
 assert bank["used"]==bank["normal_used"]==2 and owner.creations==4
 assert all(r["actual_client_exit"]==0 and r["joined"] and not r["cleanup_uncertain"] for r in records)


def test_query_persistence_time_boundary_fails_honestly(tmp_path):
 root=tmp_path/"persistence_deadline";root.mkdir(mode=0o700);os.chmod(root,0o700)
 owner=pair.Control(time.monotonic_ns(),time.time_ns()+1000000000,1)
 captured=[]
 def slow_record(name,value):
  captured.append(value);time.sleep(1.05)
  return owner.record(root/name,value)
 code="import os;os.write(1,"+repr(wire())+")"
 with pytest.raises(tc.Stop,match="DEADLINE") as found:
  m.run_query([sys.executable,"-c",code],m.QueryParser(JOB,NONCE,UID),owner,slow_record,"TERMINAL_QUERY_01",lambda label,units:None)
 assert found.value.query_persistence_uncertain
 assert found.value.terminal_query_diagnostic["actual_client_exit"]==0
 assert found.value.terminal_query_diagnostic["joined"]
 CHILDREN.append(dict(argv_kind="CONTROLLED_LOCAL_PYTHON_PERSISTENCE_EXPIRY",records=captured,charges=[],read_calls=owner.read_calls,read_bytes=owner.read_bytes,creations=owner.creations))


def test_expired_charge_never_dispatches_query(tmp_path,monkeypatch):
 from types import SimpleNamespace
 base_mono=time.monotonic_ns();base_epoch=time.time_ns();offset=[0]
 clock=SimpleNamespace(monotonic_ns=lambda:base_mono+offset[0],time_ns=lambda:base_epoch+offset[0],sleep=lambda seconds:offset.__setitem__(0,offset[0]+int(seconds*1000000000)))
 monkeypatch.setattr(m,"time",clock)
 owner=pair.Control(base_mono,base_epoch+100000000000,100)
 root=tmp_path/"postcharge";root.mkdir(mode=0o700);os.chmod(root,0o700)
 calls=[];records=[]
 def no_child(*args,**kwargs):calls.append(True);raise AssertionError("LATE_POPEN")
 monkeypatch.setattr(m.subprocess,"Popen",no_child)
 def charge(label,units):offset[0]+=16000000000
 def record(name,value):records.append(value);return owner.record(root/name,value)
 bank=m.new_query_bank()
 with pytest.raises(m.Stop,match="QUERY_DEADLINE"):
  m.run_query([sys.executable,"-c","raise SystemExit(0)"],m.QueryParser(JOB,NONCE,UID),owner,record,"TERMINAL_QUERY_01",charge,bank=bank)
 assert not calls and bank["used"]==1 and records[0]["local_pid"] is None


def test_bank_integer_types_and_submit_fresh_guard_ast():
 import ast
 owner=pair.Control(time.monotonic_ns(),time.time_ns()+1000000000,1)
 bank=m.new_query_bank();bank["maximum"]=16.0
 with pytest.raises(m.Stop,match="QUERY_CONFIG"):m.reserve_query_start(owner,bank)
 tree=ast.parse((SCRIPTS/"stage12_ra_g1_collection_driver.py").read_text())
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_execute")
 body=next(n for n in fn.body if isinstance(n,ast.Try)).body
 slot=next(i for i,n in enumerate(body) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=="mark_slot")
 assert ast.unparse(body[slot+1])=="if nonwaiting:\n    overall.check()"
 assert "subprocess.Popen" in ast.unparse(body[slot+2])

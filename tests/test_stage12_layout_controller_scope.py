"""TEST_ONLY closed ledger-scope/owned capture tests; no native workflow."""
import copy, hashlib, sys, types
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
 m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m
 exec(compile(path.read_bytes(),str(path),"exec"),m.__dict__);return m

def modules():
 w=load("layout_scope_test_wrapper",ROOT/"scripts/stage12_ra_g1_task_assets/one_fresh_controller_instance.py")
 p=load("layout_scope_test_private",ROOT/"scripts/stage12_ra_g1_task_assets/private_local_preflight.py")
 t=load("layout_scope_test_tc",ROOT/"scripts/stage12_ra_g1_terminal_collect.py")
 return w,p,t

def healthy(version,key):
 return dict(version=version,instance_grant_key=key,first_state=None,all_owned_capture_fds_closed=True,captures_poisoned=[False,False],stdout_bytes=0,stderr_bytes=0,rejected_writes=0,rejected_flushes=0,failures=dict(version="stage12_public_failure_diagnostics_v1",scope="SUPPLEMENTARY_NOT_CLOSURE_EVIDENCE",first_initiating_failure=None,first_secondary_failure=None,secondary_observations=0,earlier_response_rejection=None))

@pytest.mark.parametrize("key",["fresh_controller","new_B_collection_controller"])
def test_legacy_capture_family_retained(key):
 w,_,_=modules();assert w.capture_eligible(healthy(w.VERSION,key),instance_grant_key=key)
 assert not w.capture_eligible(healthy(w.LAYOUT_VERSION,key),instance_grant_key=key)

def test_layout_capture_is_exclusive_family():
 w,_,_=modules();key="layout_collection_controller"
 assert w.capture_eligible(healthy(w.LAYOUT_VERSION,key),instance_grant_key=key)
 assert not w.capture_eligible(healthy(w.VERSION,key),instance_grant_key=key)
 assert not w.capture_eligible(healthy(w.LAYOUT_VERSION,"fresh_controller"),instance_grant_key=key)

@pytest.mark.parametrize("bad",[None,0,"layout_slots","collection_controller","other"])
def test_arbitrary_scope_is_not_a_ledger_alias(bad):
 w,_,_=modules();assert w._selected_instance_scope(bad) is None
 assert not w.capture_eligible({},instance_grant_key=bad)

def test_nonstring_scope_never_evaluates_equality():
 w,_,_=modules()
 class Poison:
  def __eq__(self,other):raise AssertionError("not called")
 assert w._selected_instance_scope(Poison()) is None

@pytest.mark.parametrize("already_consumed",[False,True])
def test_real_private_capture_uses_only_fresh_layout_grant(tmp_path,already_consumed):
 w,p,t=modules();root=tmp_path/"owned";root.mkdir(mode=0o700);(root/"followon").mkdir(mode=0o700)
 executor=root/"TEST_ONLY_executor.py"
 executor.write_text("def execute_task(**kwargs):\n return {\"TEST_ONLY\":True}\n")
 executor.chmod(0o600)
 ledger=dict(layout_slots=dict(collection_controller=dict(maximum=1,consumed=int(already_consumed))),catalog_controller_task_slots=dict(fresh_controller=dict(maximum=1,consumed=1),new_B_collection_controller=dict(maximum=1,consumed=1)))
 legacy=copy.deepcopy(ledger["catalog_controller_task_slots"])
 def rec(path,value):
  import json,os
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
  with os.fdopen(fd,"w") as f:json.dump(value,f,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
 kwargs=dict(root=root,ledger=ledger,charge=lambda *a:None,saveledger=lambda:None,selected_executor=executor,expected_executor_sha=hashlib.sha256(executor.read_bytes()).hexdigest(),load_actual=load,preflight=p,tc=t,rec=rec,fsha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest(),executor_kwargs=dict(reviewed_source=str(ROOT),instance_nonce="TEST_ONLY_LAYOUT",plan_sha256="a"*64,command_sha256="b"*64,adoption_ref={},source_sha="c"*40,reviewed={}),instance_grant_key="layout_collection_controller")
 if already_consumed:
  with pytest.raises(RuntimeError):w.run(**kwargs)
 else:
  assert w.run(**kwargs)=={"TEST_ONLY":True}
 assert ledger["catalog_controller_task_slots"]==legacy
 assert ledger["layout_slots"]["collection_controller"]["consumed"]==1
 import json
 row=json.loads((root/"followon/FRESH_CONTROLLER_CAPTURE_LIFECYCLE.record").read_bytes())
 assert row["version"]==w.LAYOUT_VERSION
 assert w.capture_eligible(row,instance_grant_key="layout_collection_controller") is (not already_consumed)

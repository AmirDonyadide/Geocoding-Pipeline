import contextlib,io,os,sys,time
from pathlib import Path
VERSION="stage12_task_one_fresh_controller_instance_r9"
LAYOUT_VERSION="stage12_task_layout_collection_controller_r1"

def _selected_instance_scope(key):
 if type(key)is not str:return None
 if key in ("fresh_controller","new_B_collection_controller"):
  return ("catalog_controller_task_slots",key,VERSION)
 if key=="layout_collection_controller":
  return ("layout_slots","collection_controller",LAYOUT_VERSION)
 return None

OPS=frozenset(("LOCAL_SETUP","LOAD_SELECTED_EXECUTOR","EXECUTE_SELECTED_DRIVER","CAPTURE_CLOSE"))
def capture_eligible(row, *, instance_grant_key):
 scope=_selected_instance_scope(instance_grant_key)
 if scope is None or type(row)is not dict or row.get("version")!=scope[2] or row.get("instance_grant_key")!=instance_grant_key:return False
 if "first_state" not in row or row["first_state"]is not None:return False
 if row.get("all_owned_capture_fds_closed")is not True:return False
 poisoned=row.get("captures_poisoned")
 if type(poisoned)is not list or len(poisoned)!=2 or any(type(v)is not bool or v for v in poisoned):return False
 for key in ("stdout_bytes","stderr_bytes"):
  if type(row.get(key))is not int or not 0<=row[key]<=65536:return False
 if row.get("rejected_writes")!=0 or type(row.get("rejected_writes"))is not int:return False
 if row.get("rejected_flushes")!=0 or type(row.get("rejected_flushes"))is not int:return False
 failures=row.get("failures")
 required={"version","scope","first_initiating_failure","first_secondary_failure","secondary_observations","earlier_response_rejection"}
 if type(failures)is not dict or set(failures)!=required:return False
 return (failures["version"]=="stage12_public_failure_diagnostics_v1" and failures["scope"]=="SUPPLEMENTARY_NOT_CLOSURE_EVIDENCE" and failures["first_initiating_failure"]is None and failures["first_secondary_failure"]is None and type(failures["secondary_observations"])is int and failures["secondary_observations"]==0 and failures["earlier_response_rejection"]is None)

def run(*,root,ledger,charge,saveledger,selected_executor,expected_executor_sha,load_actual,preflight,tc,rec,fsha,executor_kwargs,failure_owner=None,instance_grant_key="fresh_controller"):
 root=Path(root);q=root/"followon"
 selected_scope=_selected_instance_scope(instance_grant_key)
 selected_version=VERSION if selected_scope is None else selected_scope[2]
 sys.path.insert(0,str(Path(executor_kwargs["reviewed_source"])/"src"))
 from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics
 class Clock:
  def now_ns(self):return time.monotonic_ns()
 owner=diagnostics.Failures(Clock()) if failure_owner is None else failure_owner;state={"operation":"LOCAL_SETUP","role":"ROOT"};handles=[];native_result=None;primary=None
 def safe_state():
  ops=("ROOT_IDENTITY","ROLE_PREPARE","FINAL_ROLE_VERIFY","FINAL_ROOT_VERIFY","FINAL_ROOT_OBSERVATION","PROTOCOL_OWNERSHIP")
  roles=("ROOT",)+preflight.ROLES
  return dict(operation=state.get("operation") if state.get("operation") in ops or state.get("operation") in OPS else "UNKNOWN",role=state.get("role") if state.get("role") in roles else "UNKNOWN")
 class CapturePoisoned(RuntimeError):pass
 class Capture(io.TextIOBase):
  def __init__(self,path,console):
   self.fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);self.n=0;self.console=console;self.failed=False;self.propagating_error=None;self.rejected_writes=0;self.rejected_flushes=0;handles.append(self)
  def fail(self,error,tag):
   if not self.failed:
    self.failed=True;self.propagating_error=error;owner.record(tag,error)
  def write(self,value):
   if self.failed:
    self.rejected_writes=min(2**32-1,self.rejected_writes+1);raise CapturePoisoned()
   try:
    if type(value)is not str:raise TypeError()
    if len(value)>65536-self.n:raise OverflowError()
    for start in range(0,len(value),512):
     raw=value[start:start+512].encode("utf-8")
     if self.n+len(raw)>65536:raise OverflowError()
     off=0
     while off<len(raw):
      n=os.write(self.fd,raw[off:])
      if n<=0:raise OSError()
      off+=n;self.n+=n
    if value.startswith("TASK_DURABLE_RECORD") or value=="\n":self.console.write(value);self.console.flush()
    return len(value)
   except BaseException as error:
    self.fail(error,"WRITER_ACTION");raise
  def flush(self):
   if self.fd is None:return
   if self.failed:
    self.rejected_flushes=min(2**32-1,self.rejected_flushes+1);raise CapturePoisoned()
   try:os.fsync(self.fd)
   except BaseException as error:self.fail(error,"WRITER_ACTION");raise
  def close_owned(self):
   if self.fd is None:return
   if not self.failed:
    try:os.fsync(self.fd)
    except BaseException as error:self.fail(error,"CLEANUP")
   try:os.close(self.fd);self.fd=None
   except BaseException as error:owner.record("CLEANUP",error)

 try:
  actual_setup=preflight.prepare(q,tc,state);rec(q/"ACTUAL_PRIVATE_PRECONDITIONS_AT_INSTANCE_ENTRY.record",actual_setup)
  if selected_scope is None:raise RuntimeError()
  grant=ledger[selected_scope[0]][selected_scope[1]]
  if grant["maximum"]!=1 or grant["consumed"]!=0:raise RuntimeError()
  grant.update(consumed=1,instance_nonce=executor_kwargs["instance_nonce"],prelude_entry_mono_ns=time.monotonic_ns(),prelude_entry_epoch_ns=time.time_ns(),actual_controller_origin="UNCHANGED_PRODUCTION_DRIVER_ENTRY_MUST_BE_OBSERVED")
  saveledger()
  stdout=Capture(q/"CONTROLLER_STDOUT.raw",sys.stdout);stderr=Capture(q/"CONTROLLER_STDERR.raw",sys.stderr)
  with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
   state.update(operation="LOAD_SELECTED_EXECUTOR",role="ROOT")
   if fsha(selected_executor)!=expected_executor_sha:raise RuntimeError()
   module=load_actual("actual_one_fresh_controller_executor",selected_executor)
   state.update(operation="EXECUTE_SELECTED_DRIVER",role="ROOT")
   native_result=module.execute_task(root=root,ledger=ledger,charge=charge,saveledger=saveledger,expected_plan_sha256=executor_kwargs["plan_sha256"],expected_command_sha256=executor_kwargs["command_sha256"],adoption_ref=executor_kwargs["adoption_ref"],source_sha=executor_kwargs["source_sha"],reviewed=executor_kwargs["reviewed"])
  return native_result
 except BaseException as error:
  duplicate=any(c.propagating_error is error for c in handles) or type(error)is CapturePoisoned and any(c.failed for c in handles)
  if not duplicate:owner.record("PREFLIGHT",error)
  primary=safe_state()
  code=None
  if type(error)is preflight.Rejected and len(error.args)==1 and error.args[0] in ("LOCAL_SETUP_PATH","LOCAL_SETUP_REPLACED","LOCAL_SETUP_UNEXPECTED_MEMBER","LOCAL_SETUP_PROTOCOL_OWNERSHIP"):code=error.args[0]
  elif type(error)is getattr(tc,"Stop",None) and len(error.args)==1 and type(error.args[0])is str:
   code={"PRIVATE":"LOCAL_SETUP_INVALID_IDENTITY","LINK":"LOCAL_SETUP_LINK","ANCESTOR":"LOCAL_SETUP_ANCESTOR","ANCESTOR_CHANGED":"LOCAL_SETUP_ANCESTOR_CHANGED","OUTPUT_CHANGED":"LOCAL_SETUP_REPLACED"}.get(error.args[0])
  elif type(error)is FileNotFoundError:code="LOCAL_SETUP_MISSING"
  elif type(error)is PermissionError:code="LOCAL_SETUP_ACCESS_DENIED"
  elif type(error)is CapturePoisoned:code="LOCAL_CAPTURE_POISONED"
  rec(q/"FRESH_CONTROLLER_FIRST_FAILURE.record",dict(version=selected_version,state=primary,safe_guard=code,failures=owner.snapshot(),no_arbitrary_exception_text=True,no_native_success=True))
  raise
 finally:
  for capture in reversed(handles):
   try:capture.close_owned()
   except BaseException as cleanup:
    owner.record("CLEANUP",cleanup)
  try:
   rec(q/"FRESH_CONTROLLER_CAPTURE_LIFECYCLE.record",dict(version=selected_version,instance_grant_key=instance_grant_key,first_state=primary,failures=owner.snapshot(),stdout_bytes=sum(c.n for c in handles[:1]),stderr_bytes=sum(c.n for c in handles[1:]),all_owned_capture_fds_closed=all(c.fd is None for c in handles),captures_poisoned=[c.failed for c in handles],rejected_writes=sum(c.rejected_writes for c in handles),rejected_flushes=sum(c.rejected_flushes for c in handles),native_or_scientific_acceptance=False))
  except BaseException as error:
   owner.record("CLEANUP",error)
   raise
  finally:
   for capture in handles:capture.propagating_error=None

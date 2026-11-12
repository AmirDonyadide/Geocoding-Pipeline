"""Exact task-scoped collection coordinator; no retries or automatic replacement."""
import hashlib,os,stat,subprocess,time,types,sys
if sys.flags.optimize!=0:raise RuntimeError("CONTROLLER_OPTIMIZATION_UNSUPPORTED")

def validate_prelude(raw,rows,ancestors,transport,uid,gid,*,remote_directory_scope=None):
 lines=raw.splitlines(keepends=True); n=len(rows)+len(ancestors)
 selected_remote=transport._remote_scope(remote_directory_scope)
 assert len(raw)<=32768 and len(lines)==(2*n+len(rows)+4 if selected_remote else n+len(rows)+2) and lines[0]==b"BEFORE\n"
 ids=[transport._stat_line(v) for v in lines[1:1+n]]
 for info,row in zip(ids[:len(rows)],rows,strict=True):
  assert stat.S_ISREG(info[2]) and stat.S_IMODE(info[2])==0o600 and info[3:6]==[uid,gid,1] and info[6]==row["bytes"]
 for info in ids[len(rows):]: assert stat.S_ISDIR(info[2])
 for row in rows:
  parent=ancestors.index(__import__("pathlib").Path(row["path"]).parent)+len(rows); info=ids[parent]
  assert stat.S_IMODE(info[2])==0o700 and info[3:5]==[uid,gid]
 assert lines[1+n:1+n+len(rows)]==[(r["path"]+": OK\n").encode() for r in rows]
 assert lines[-1]==b"S12_CANONICAL_BINDINGS_AND_SOURCE_VERIFIED\n"
 if selected_remote:
  after_at=1+n+len(rows)
  assert lines[after_at]==b"AFTER\n"
  after=[transport._stat_line(v) for v in lines[after_at+1:after_at+1+n]]
  assert lines[-2]==("REMOTE_DIRECTORY_POLICY|"+remote_directory_scope+"\n").encode()
  assert after[:len(rows)]==ids[:len(rows)]
  assert [v[:5] for v in after[len(rows):]]==[v[:5] for v in ids[len(rows):]]
 return ids

class SubmissionStreams:
 def __init__(self,proc,files,owner,wait_module,nonce,epoch,seconds,rows,ancestors,transport,uid,gid,record):
  self.proc=proc;self.files=files;self.owner=owner;self.wait=wait_module;self.nonce=nonce;self.epoch=epoch;self.seconds=seconds;self.rows=rows;self.ancestors=ancestors;self.transport=transport;self.uid=uid;self.gid=gid;self.record=record
  self.offset={k:0 for k in files};self.raw=bytearray();self.parser=None;self.prelude_ids=None;self.recorded=False;self.busy=False;self.next_pump=0
 def pump(self,force=False):
  if self.busy:return
  now=time.monotonic_ns()
  if not force and now<self.next_pump:return
  self.next_pump=now+50_000_000;self.busy=True
  try:
   for label,(fd,path) in self.files.items():
    info=os.fstat(fd);assert info.st_size<=(1048576 if label=="stdout" else 65536) and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.geteuid()
    raw=self.owner.read(fd,65536)
    if raw:
     self.offset[label]+=len(raw)
     if label=="stdout":
      self.raw.extend(raw);assert len(self.raw)<=1048576
      if self.parser is None:
       marker=b"S12SUB2|BEGIN|";p=self.raw.find(marker)
       if p>=0:
        assert p==0 or self.raw[p-1]==10
        prefix=bytes(self.raw[:p]);self.prelude_ids=validate_prelude(prefix,self.rows,self.ancestors,self.transport,self.uid,self.gid)
        self.parser=self.wait.Parser(self.nonce,self.epoch,self.seconds,expected_prelude=prefix);self.parser.feed(bytes(self.raw))
       else:assert len(self.raw)<=32768
      else:self.parser.feed(raw)
      if self.parser is not None and self.parser.submitted is not None and not self.recorded:
       self.record("SUBMITTED_ID_OBSERVED.record",dict(submission=self.parser.submitted,observed_mono_ns=time.monotonic_ns(),observed_epoch_ns=time.time_ns(),native_acceptance=False));self.recorded=True
  finally:self.busy=False
 def terminal(self):
  assert self.proc.poll() is not None
  self.proc.wait(timeout=0)
  while True:
   old=sum(self.offset.values());self.pump(True)
   if sum(self.offset.values())==old:break
  assert self.parser is not None
  return self.parser.finish(self.proc.returncode)


class OrdinarySubmissionStreams:
 def __init__(self,proc,files,owner,module,nonce,epoch,seconds,rows,ancestors,transport,uid,gid,record,*,remote_directory_scope=None):
  self.proc=proc;self.files=files;self.owner=owner;self.module=module;self.nonce=nonce;self.epoch=epoch;self.seconds=seconds;self.rows=rows;self.ancestors=ancestors;self.transport=transport;self.uid=uid;self.gid=gid;self.record=record
  self.remote_directory_scope=remote_directory_scope
  self.offset={k:0 for k in files};self.raw=bytearray();self.parser=None;self.prelude_ids=None;self.recorded=False;self.busy=False;self.next_pump=0;self.finished=False;self.facts=None
 def pump(self,force=False):
  if self.busy or self.finished:return
  now=time.monotonic_ns()
  if not force and now<self.next_pump:return
  self.next_pump=now+50_000_000;self.busy=True
  try:
   for label,(fd,path) in self.files.items():
    info=os.fstat(fd);assert info.st_size<=(65536 if label=="stdout" else 65536) and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.geteuid()
    raw=self.owner.read(fd,65536)
    if raw:
     self.offset[label]+=len(raw)
     if label=="stdout":
      self.raw.extend(raw);assert len(self.raw)<=65536
      if self.parser is None:
       p=self.raw.find(self.module.SUBMIT_MARKER)
       if p>=0:
        assert p==0 or self.raw[p-1]==10
        prefix=bytes(self.raw[:p]);self.prelude_ids=validate_prelude(prefix,self.rows,self.ancestors,self.transport,self.uid,self.gid,remote_directory_scope=self.remote_directory_scope)
        self.parser=self.module.SubmitParser(self.nonce,self.epoch,self.seconds,expected_prelude=prefix);self.parser.feed(bytes(self.raw))
       else:assert len(self.raw)<=32768
      else:self.parser.feed(raw)
      if self.parser is not None and self.parser.submitted is not None and not self.recorded:
       self.module.need(self.parser.submitted["cluster"] is None,"SUBMIT_CLUSTER")
       self.record("SUBMITTED_ID_OBSERVED.record",dict(version=self.module.SUBMIT_VERSION,submission=self.parser.submitted,observed_mono_ns=time.monotonic_ns(),observed_epoch_ns=time.time_ns(),native_acceptance=False));self.recorded=True
  finally:self.busy=False
 def submission_complete(self):
  assert self.proc.poll() is not None
  self.proc.wait(timeout=0)
  while True:
   old=sum(self.offset.values());self.pump(True)
   if sum(self.offset.values())==old:break
  assert self.parser is not None
  self.facts=self.parser.finish(self.proc.returncode);self.finished=True
  return self.facts


def phase_control(pair,overall,seconds,epoch):
 start=time.monotonic_ns();phase=pair.Control(start,min(epoch,overall.epoch_end),seconds);original=phase.check
 def check(self):
  overall.check();original()
 phase.check=types.MethodType(check,phase)
 original_read=phase.read
 def read(self,fd,amount):
  selected_read_precharge(overall,pair)
  return original_read(fd,amount)
 phase.read=types.MethodType(read,phase)
 return phase

SELECTED_OVERALL_READ_ATTEMPTS = 173646


def selected_read_precharge(overall,pair):
 pair.need(overall.selected_read_attempts<SELECTED_OVERALL_READ_ATTEMPTS,"READ_CALLS")
 overall.selected_read_attempts+=1  # One shared attempted-read owner; no refunds.


def install_selected_read_limit(overall, pair):
 """Precharge each attempted read before any reentrant stream servicing."""
 pair.need(not hasattr(overall,"selected_read_attempts"),"BINDING")
 original_read=overall.read
 overall.selected_read_attempts=0
 def selected_read(self,fd,amount):
  selected_read_precharge(self,pair)
  return original_read(fd,amount)
 overall.read=types.MethodType(selected_read,overall)


def load_verified_admission(plan, command, overall, pair, transport, observer, *, nonwaiting_module=None):
 """Read the actual canonical controls; a claimed scalar is never admission."""
 from pathlib import Path
 pair.need("actual_admission_process_cap" not in command, "AUTHORITY")
 local_paths=[pair.tc.absolute(command[key]) for key in
              ("local_binding_path","local_authority_path","local_admission_path")]
 pair.need(len({p.parent for p in local_paths})==1
           and [p.name for p in local_paths]==["binding.record","authority.record","collection_admission.record"], "PATH")
 binding=pair.load_control(local_paths[0],command["binding_sha256"],overall)
 authority=pair.load_control(local_paths[1],command["authority_sha256"],overall)
 admission=pair.load_control(local_paths[2],command["admission_sha256"],overall)
 pair.validate_binding(binding,False,None)
 pair.validate_authority(authority,binding,False)
 pair.need(binding["authority_sha256"]==command["authority_sha256"]
           and authority["collection_admission_sha256"]==command["admission_sha256"], "AUTHORITY")
 pair.validate_collection_admission(admission,binding,authority,False)
 selected_remote = plan.get("remote_directory_scope") is not None
 pair.need(not selected_remote or nonwaiting_module is not None
           and plan["remote_directory_scope"] == transport.REMOTE_DIRECTORY_SCOPE
           and plan.get("transport_evidence_version") == transport.REMOTE_TRANSPORT_VERSION, "BINDING")
 pair.need(selected_remote or "transport_evidence_version" not in plan, "BINDING")
 pair.need((command.get("version") == "stage12_selected_pair_remote_directory_exact_commands_v3") == selected_remote, "BINDING")
 pair.need(command.get("remote_directory_scope") == plan.get("remote_directory_scope")
           and command.get("transport_evidence_version") == plan.get("transport_evidence_version"), "BINDING")
 pair.need(admission["version"]==(pair.REMOTE_IDENTITY_ADMISSION_VERSION if selected_remote else pair.NONWAITING_ADMISSION_VERSION if nonwaiting_module is not None else pair.SELECTED_PAIR_ADMISSION_VERSION), "AUTHORITY")
 pair.need(plan["remote_pair"]==binding["output_path"], "BINDING")
 for key in ("source_git_sha","original_source_git_sha","original_source_root",
             "original_producer_path","allocation_producer_sha256"):
  pair.need(binding[key]==plan[key], "BINDING")
 pair.need(binding["original_selection_sha256"]==command["original_selection_sha256"], "BINDING")
 policy=admission["one_shot_control_policy"]
 if selected_remote:
  pair.need(policy["remote_directory_scope"] == plan["remote_directory_scope"]
            and policy["transport_evidence_version"] == plan["transport_evidence_version"], "BINDING")
 modules=((Path(observer.__file__).absolute(),"stage12_ra_g1_one_shot_controls.py","one_shot_controls_sha256"),
          (Path(__file__).absolute(),"stage12_ra_g1_collection_driver.py","collection_driver_sha256"),
          (Path(transport.__file__).absolute(),"stage12_ra_g1_terminal_transport.py","transport_sha256"))
 for path,filename,key in modules:
  pair.need(path.name==filename and path.parent==Path(__file__).absolute().parent, "BINDING")
  pair.source_hash(path,policy[key],overall)
 if nonwaiting_module is not None:
  terminal_policy=admission["submission_terminal_policy"]
  pair.need(nonwaiting_module.VERSION==terminal_policy["version"],"BINDING")
  module_path=Path(nonwaiting_module.__file__).absolute()
  pair.need(module_path==Path(__file__).absolute().with_name("stage12_ra_g1_nonwaiting_submit.py"),"BINDING")
  pair.source_hash(module_path,terminal_policy["module_sha256"],overall)
  pair.need(admission["collection_plan_sha256"]==command["plan_sha256"]==hashlib.sha256(pair.tc.canonical(plan)).hexdigest(),"BINDING")
  pair.need(admission["process_graph_sha256"]==command["graph_sha256"],"BINDING")
  pair.need(command["submission_protocol"]==nonwaiting_module.VERSION,"BINDING")
  expected_argv=nonwaiting_module.submission_argv(command["canonical_preflight_prefix"],command["submit_sbatch_argv"],command["nonce"],command["selected_original_submission_epoch_ceiling"],1800)
  pair.need(command["submit_argv"]==expected_argv,"BINDING")
 overall.check()
 return admission


def run_irreversible_failure_hook(callback, *, overall, streams, proc, plan, command, first_failure, pair, tc):
 """One task-owned hook; it cannot rewrite the retained initiating failure."""
 entered=time.monotonic_ns()
 disposition=dict(status="FAILED_OR_UNCERTAIN",invoked=False,entry_mono_ns=entered,
                  original_deadline_mono_ns=overall.end,original_window_end_epoch_ns=overall.epoch_end)
 try:
  pair.need(callable(callback),"BINDING")
  raw=tc.canonical(first_failure)
  pair.need(len(raw)<=65536,"LIMITS")
  primary_copy=tc.parse(raw)
  disposition["invoked"]=True
  callback(overall=overall,streams=streams,proc=proc,plan=plan,command=command,
           first_failure_copy=primary_copy)
  disposition["status"]="RETURNED_PENDING_INDEPENDENT_VERIFICATION"
 except BaseException as error:
  disposition["safe_error"]=pair.safe_code(error)
 finally:
  disposition["complete_mono_ns"]=time.monotonic_ns()
 return disposition


def _execute(plan,command,rows,ancestors,base,modules,observer,wait_module,handoff,charge,mark_slot,record,handles, *, on_irreversible_failure=None, nonwaiting=False, entry=None):
 tc,pair,transport,_=modules;started,epoch=(time.monotonic_ns(),time.time_ns()) if entry is None else entry;overall=pair.Control(started,plan["window_end_epoch_ns"],1800)
 install_selected_read_limit(overall,pair)
 handles["control"]=overall
 if nonwaiting:handles["terminal_query_bank"]=wait_module.new_query_bank()
 original_check=overall.check;streams=None;stage="SUBMIT";phase_owners=[];proc=None;fds={};readers={};failure=None;result=None;failure_hook=None
 def check(self):
  original_check()
  if streams is not None:streams.pump()
  original_check()
 overall.check=types.MethodType(check,overall)
 def action_control(name,seconds,end):
  c=phase_control(pair,overall,seconds,end);phase_owners.append((name,c));return c
 try:
  assert "observer_argv" not in command
  actual_admission=load_verified_admission(plan,command,overall,pair,transport,observer,nonwaiting_module=wait_module if nonwaiting else None)
  pair.need(plan.get("local_directory_scope") == transport.TASK_LOCAL_DIRECTORY_SCOPE, "BINDING")
  policy=actual_admission["one_shot_control_policy"]
  expected_task_selection={key:policy[key] for key in ("version","maximum_probes","probe_seconds","minimum_start_spacing_seconds","spacing_anchor","maximum_process_units","directory_readiness","selected_remote_pair")}
  assert command["task_control_selection"] == expected_task_selection
  assert (observer.REMOTE_VERSION if plan.get("remote_directory_scope") is not None else observer.VERSION)==(policy["readiness_reader_version"] if nonwaiting else policy["version"]) and policy["selected_remote_pair"]==plan["remote_pair"]
  for label in ("stdout","stderr"):
   path=base/("submission."+label+".raw");fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);fds[label]=(fd,path);readfd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);assert os.fstat(readfd).st_ino==os.fstat(fd).st_ino and os.fstat(readfd).st_dev==os.fstat(fd).st_dev;readers[label]=(readfd,path)
  record("EXECUTION_ENTRY.record",dict(entry_mono_ns=started,entry_epoch_ns=epoch,role_deadline_mono_ns=overall.end,window_end_epoch_ns=overall.epoch_end,source=plan["source_git_sha"],nonce=command["nonce"],actual_admission_sha256=command["admission_sha256"],actual_admission_version=actual_admission["version"],actual_admission_process_cap=actual_admission["maximum_preparation_and_native_processes"]))
  charge("QUALIFICATION_SOLE_ORDINARY_SUBMISSION_AND_POSSIBLE_NATIVE_ROLES" if nonwaiting else "QUALIFICATION_SOLE_SUBMIT_WAIT_TERMINAL_AND_POSSIBLE_NATIVE_ROLES",8 if nonwaiting else 11)
  mark_slot()
  if nonwaiting:overall.check()  # fresh original-controller/window gate after ledger fsync
  proc=subprocess.Popen(command["submit_argv"],stdin=subprocess.DEVNULL,stdout=fds["stdout"][0],stderr=fds["stderr"][0],start_new_session=True)
  record("SUBMISSION_CLIENT_IDENTITY.record",dict(pid=proc.pid,pgid=os.getpgid(proc.pid),entry_mono_ns=time.monotonic_ns(),one_submission_only=True))
  handles["submission"]=proc;handles["source_entry_mono_ns"]=started;handles["source_end_mono_ns"]=overall.end
  streams=(OrdinarySubmissionStreams if nonwaiting else SubmissionStreams)(proc,readers,overall,wait_module,command["nonce"],command["selected_original_submission_epoch_ceiling"],1800,rows,ancestors,transport,plan["source_uid"],plan["source_gid"],record,**({"remote_directory_scope":plan.get("remote_directory_scope")} if nonwaiting else {}))
  if nonwaiting:
   while proc.poll() is None:overall.check();time.sleep(.05)
   overall.check();submission_facts=streams.submission_complete()
   record("SUBMISSION_CLIENT_FACTS.record",submission_facts)
  stage="OBSERVE"
  controls_root=base/"one-shot-probes"
  overall.claim(0,True);controls_root.mkdir(mode=0o700)
  proof=observer.poll(plan,controls_root,overall,transport,pair,tc,charge,record,local_directory_scope=plan["local_directory_scope"],remote_directory_scope=plan.get("remote_directory_scope"))
  record("ONE_SHOT_DISPOSITION.record",proof)
  assert proof["status"]=="READY_ORIGINAL_AWAITING_CONTEXT_VALIDATION"
  overall.check();stage="READY";charge("QUALIFICATION_FRESH_READY_ORIGINAL_SAME_DOMAIN",7)
  c=action_control(stage,120,overall.epoch_end);ev,_=transport.fetch_batch([dict(label="ready",path=plan["remote_pair"]+"/TRANSPORT_READY.record",maximum=65536,local_name="transport-ready.original")],__import__("pathlib").Path(plan["local_final_logs"]),c,expected_uid=plan["source_uid"],expected_gid=plan["source_gid"],local_directory_scope=plan["local_directory_scope"],remote_directory_scope=plan.get("remote_directory_scope"))
  c.record(__import__("pathlib").Path(plan["local_final_logs"])/"READY_TRANSPORT_EVIDENCE.record",ev)
  ready_raw=pair.read_original(__import__("pathlib").Path(plan["local_final_logs"])/"transport-ready.original",c,65536);ready=tc.parse(ready_raw);pair.validate_ready(ready)
  pair.need((ready["version"] == pair.REMOTE_IDENTITY_READY_VERSION) == (plan.get("remote_directory_scope") is not None), "BINDING")
  if plan.get("remote_directory_scope") is not None:
   pair.need(ready["context"].get("remote_directory_scope") == plan["remote_directory_scope"]
             and ready["context"].get("transport_evidence_version") == plan["transport_evidence_version"], "BINDING")
  assert ready["context"]["collection_source_git_sha"]==plan["source_git_sha"] and ready["context"]["original_source_git_sha"]==plan["original_source_git_sha"] and ready["context"]["original_job_id"]==actual_admission["original_job_id"] and ready["context"]["binding_sha256"]==command["binding_sha256"] and ready["context"]["authority_sha256"]==command["authority_sha256"]
  assert hashlib.sha256(ready_raw).hexdigest()==proof["ready_sha256"]
  ctx=ready["context"]
  assert ctx["original_workload_selection_sha256"]==command["original_selection_sha256"] and ctx["collection_uid"]==plan["source_uid"] and ctx["window"]==plan["window"] and ctx["collection_purpose"]==actual_admission["collection_purpose"] and ctx["scope"]==pair.NATIVE
  assert ctx["original_source_root"]==plan["original_source_root"] and ctx["original_producer_path"]==plan["original_producer_path"] and ctx["original_producer_sha256"]==plan["allocation_producer_sha256"] and ctx["external_logs"]==plan["collection_logs"]
  required_artifacts={"archive":plan["remote_pair"]+"/receive/terminal.s12c","before":plan["remote_pair"]+"/receive/before.jsonl","after":plan["remote_pair"]+"/receive/after.jsonl","verification":plan["remote_pair"]+"/WORKLOAD_VERIFICATION.record"}
  assert len(ready["artifacts"])==4 and {r["label"]:r["path"] for r in ready["artifacts"]}==required_artifacts
  overall.check()
  if streams.parser is not None and streams.parser.submitted is not None:assert streams.parser.submitted["job_id"]==ready["context"]["collection_job_id"]
  elif nonwaiting:raise wait_module.Stop("SUBMIT_INCOMPLETE")
  else:record("EARLY_WAIT_ID_PENDING.record",dict(native_context_job_id=ready["context"]["collection_job_id"],reason="WAIT_CLIENT_ID_NOT_YET_OBSERVED",not_terminal_acceptance=True))
  overall.epoch_end=min(overall.epoch_end,ready["context"]["overall_deadline_epoch_ns"])
  stage="FETCH";charge("QUALIFICATION_FOUR_COMPLETE_READY_ARTIFACTS",10);c=action_control(stage,900,ready["context"]["parent_deadline_epoch_ns"])
  receipt,transport_result=transport.fetch_ready(ready,hashlib.sha256(ready_raw).hexdigest(),__import__("pathlib").Path(plan["local_retained"]),__import__("pathlib").Path(plan["local_transport"]),control=c,local_directory_scope=plan["local_directory_scope"],remote_directory_scope=plan.get("remote_directory_scope"))
  record("FETCH_DISPOSITION.record",dict(status=transport_result["status"],completed_mono_ns=time.monotonic_ns(),read_bytes=c.read_bytes,read_calls=c.read_calls))
  stage="RECEIPT";charge("QUALIFICATION_EXCLUSIVE_RECEIPT_PUBLICATION_AND_ORIGINAL_ECHO",15);c=action_control(stage,120,ready["context"]["parent_deadline_epoch_ns"]);publication=handoff.publish_receipt(plan,ready,receipt,c);record("RECEIPT_DISPOSITION.record",publication)
  stage="WAIT_TERMINAL"
  if nonwaiting:
   # Queries are deliberately AFTER receipt. This preserves handoff progress and
   # the original-1800s joint readiness/query creation-accounting bound.
   terminal_facts=None;query_bank=handles["terminal_query_bank"]
   for query_index in range(actual_admission["submission_terminal_policy"]["normal_query_slots"]):
    overall.check()
    parser=wait_module.QueryParser(streams.parser.submitted["job_id"],command["nonce"],plan["source_uid"])
    facts=wait_module.run_query(wait_module.query_argv(streams.parser.submitted["job_id"],command["nonce"]),parser,overall,record,"TERMINAL_QUERY_"+str(query_index+1).zfill(2),charge,bank=query_bank)
    if facts["status"]=="AUTHORITATIVE_TERMINAL":terminal_facts=facts;break
    wait_module.need(facts["status"] in ("ACCOUNTING_PENDING","NONTERMINAL"),"QUERY_FRAME")
   wait_module.need(terminal_facts is not None,"QUERY_LIMIT")
   wait_module.need(terminal_facts["all_completed_zero"],"JOB_FAILED")
   top=terminal_facts["terminal"]
   terminal=dict(version="stage12_terminal_collection_scheduler_v1",collection_job_id=terminal_facts["job_id"],source_git_sha=plan["source_git_sha"],binding_sha256=command["binding_sha256"],scope=pair.NATIVE,scheduler_state="COMPLETED",exit_code="0:0",start_epoch_ns=top["start_epoch_ns"],end_epoch_ns=top["end_epoch_ns"],observed_epoch_ns=terminal_facts["observed_epoch_ns"])
  else:
   while proc.poll() is None:overall.check();time.sleep(.05)
   overall.check();terminal_facts=streams.terminal();record("WAIT_AND_QUERY_FACTS.record",terminal_facts)
   assert terminal_facts["wait_exit"]==0 and terminal_facts["ssh_query_exit"]==0 and terminal_facts["terminal"]["state"]=="COMPLETED" and terminal_facts["terminal"]["exit_code"]=="0:0"
   assert terminal_facts["submission"]["job_id"]==ready["context"]["collection_job_id"]
   top=terminal_facts["terminal"];start_ns=__import__("datetime").datetime.strptime(top["start"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=__import__("datetime").timezone.utc).timestamp();end_ns=__import__("datetime").datetime.strptime(top["end"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=__import__("datetime").timezone.utc).timestamp()
   terminal=dict(version="stage12_terminal_collection_scheduler_v1",collection_job_id=terminal_facts["submission"]["job_id"],source_git_sha=plan["source_git_sha"],binding_sha256=command["binding_sha256"],scope=pair.NATIVE,scheduler_state="COMPLETED",exit_code="0:0",start_epoch_ns=int(start_ns)*10**9,end_epoch_ns=int(end_ns)*10**9,observed_epoch_ns=time.time_ns())
  record("COLLECTION_TERMINAL.record",terminal)
  stage="FINAL_OPEN";charge("QUALIFICATION_POSTTERMINAL_SIX_ORIGINALS_AND_ACTUAL_OPENER",12);c=action_control(stage,120,min(ready["context"]["overall_deadline_epoch_ns"],terminal["start_epoch_ns"]+1800*10**9));open_entry=time.monotonic_ns();result=handoff.finish_collected(plan,terminal,__import__("pathlib").Path(plan["local_final_logs"]),__import__("pathlib").Path(plan["local_retained"]),c)
  overall.check();record("ACTUAL_OPENER_COMPLETION.record",dict(invoked_mono_ns=open_entry,complete_mono_ns=time.monotonic_ns(),complete_epoch_ns=time.time_ns(),status=result["status"],result=result));stage="COMPLETE"
 except BaseException as error:
  failure=dict(stage=stage,code=(wait_module.safe_code(error) if nonwaiting and type(error) is wait_module.Stop else pair.safe_code(error)),kind=("TC_STOP" if type(error) is tc.Stop else "ASSERTION" if type(error) is AssertionError else "OS_ERROR" if isinstance(error,OSError) else "UNCLASSIFIED"),observed_mono_ns=time.monotonic_ns(),observed_epoch_ns=time.time_ns(),transport=getattr(error,"transport_diagnostic",None),historical_cause_not_inferred=True)
  if nonwaiting and getattr(error,"terminal_query_diagnostic",None) is not None:
   failure["terminal_query"]=error.terminal_query_diagnostic
   failure["query_persistence_uncertain"]=getattr(error,"query_persistence_uncertain",False)
  try:record("FIRST_FAILURE.record",failure)
  except BaseException:failure["diagnostic_retention"]="INCOMPLETE"
  if on_irreversible_failure is not None:
   failure_hook=run_irreversible_failure_hook(on_irreversible_failure,overall=overall,
       streams=streams,proc=proc,plan=plan,command=command,first_failure=failure,pair=pair,tc=tc)
 finally:
  if proc is not None and proc.poll() is None:
   while time.monotonic_ns()<overall.end and time.time_ns()<overall.epoch_end and proc.poll() is None:
    try:streams.pump(True)
    except BaseException:break
    time.sleep(.1)
  actual_exit=proc.poll() if proc is not None else None
  if actual_exit is not None:
   proc.wait(timeout=0)
   if streams is not None and not nonwaiting:
    try:record("FINAL_WAIT_AND_QUERY_FACTS.record",streams.terminal())
    except BaseException:pass
  # Final mandatory draining above is complete; no checks may service closed FDs.
  streams=None
  for readfd,path in readers.values():
   try:os.close(readfd)
   except BaseException:
    if failure is None:failure=dict(stage="LOCAL_LOG_READ_CLOSE",code="CLOSE_UNCERTAIN")
  for fd,path in fds.values():
   try:os.fsync(fd);os.close(fd)
   except BaseException:
    if failure is None:failure=dict(stage="LOCAL_LOG_CLOSE",code="CLOSE_UNCERTAIN")
  final_check_mono=time.monotonic_ns();final_check_epoch=time.time_ns()
  if final_check_mono>=overall.end or final_check_epoch>=overall.epoch_end:
   if failure is None:failure=dict(stage="LOCAL_FINALIZATION",code="DEADLINE",observed_mono_ns=final_check_mono,observed_epoch_ns=final_check_epoch)
  status="COMPLETE_PENDING_INDEPENDENT_REVIEW" if result is not None and failure is None and actual_exit==0 else "INCOMPLETE"
  output=dict(status=status,first_failure=failure,stage=stage,actual_client_exit=actual_exit,client_joined=actual_exit is not None,entry_mono_ns=started,entry_epoch_ns=epoch,role_deadline_mono_ns=overall.end,window_end_epoch_ns=overall.epoch_end,complete_mono_ns=time.monotonic_ns(),selected_read_attempts=overall.selected_read_attempts,selected_read_attempt_limit=SELECTED_OVERALL_READ_ATTEMPTS,phase_counters=[dict(role=n,entered=c.entered,end=c.end,read_calls=c.read_calls,read_bytes=c.read_bytes,write_bytes=c.write_bytes,creations=c.creations,cleanup_uncertain=c.cleanup_uncertain) for n,c in phase_owners],old_observer_termination="UNKNOWN",public_authorized=False,protected_authorized=False,scientific_acceptance=False)
  if failure_hook is not None:output["irreversible_failure_hook"]=failure_hook
  if nonwaiting:output["terminal_query_bank"]=dict(handles["terminal_query_bank"])
  output["persisted_timestamp_scope"]="BEFORE_OUTCOME_RECORD_FSYNC_NOT_FINAL_RETURN"
  try:record("COORDINATOR_OUTCOME.record",output)
  except BaseException:output["status"]="INCOMPLETE";output["diagnostic_retention"]="INCOMPLETE"
  output["actual_post_record_mono_ns"]=time.monotonic_ns();output["actual_post_record_epoch_ns"]=time.time_ns()
  if output["actual_post_record_mono_ns"]>=overall.end or output["actual_post_record_epoch_ns"]>=overall.epoch_end:output["status"]="INCOMPLETE";output["post_record_lateness"]=True
 return output


def execute(plan,command,rows,ancestors,base,modules,observer,wait_module,handoff,charge,mark_slot,record,handles, *, on_irreversible_failure=None):
 return _execute(plan,command,rows,ancestors,base,modules,observer,wait_module,handoff,charge,mark_slot,record,handles,on_irreversible_failure=on_irreversible_failure,nonwaiting=False)


def execute_nonwaiting(plan,command,rows,ancestors,base,modules,observer,terminal_module,handoff,charge,mark_slot,record,handles, *, on_irreversible_failure=None):
 """Versioned operating successor; submit-client exit is never a --wait result."""
 entry=(time.monotonic_ns(),time.time_ns())
 return _execute(plan,command,rows,ancestors,base,modules,observer,terminal_module,handoff,charge,mark_slot,record,handles,on_irreversible_failure=on_irreversible_failure,nonwaiting=True,entry=entry)

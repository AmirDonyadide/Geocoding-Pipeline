"""Exact task-scoped collection coordinator; no retries or automatic replacement."""
import hashlib,os,stat,subprocess,time,types,sys
if sys.flags.optimize!=0:raise RuntimeError("CONTROLLER_OPTIMIZATION_UNSUPPORTED")

def validate_prelude(raw,rows,ancestors,transport,uid,gid):
 lines=raw.splitlines(keepends=True); n=len(rows)+len(ancestors)
 assert len(raw)<=32768 and len(lines)==n+len(rows)+2 and lines[0]==b"BEFORE\n"
 ids=[transport._stat_line(v) for v in lines[1:1+n]]
 for info,row in zip(ids[:len(rows)],rows,strict=True):
  assert stat.S_ISREG(info[2]) and stat.S_IMODE(info[2])==0o600 and info[3:6]==[uid,gid,1] and info[6]==row["bytes"]
 for info in ids[len(rows):]: assert stat.S_ISDIR(info[2])
 for row in rows:
  parent=ancestors.index(__import__("pathlib").Path(row["path"]).parent)+len(rows); info=ids[parent]
  assert stat.S_IMODE(info[2])==0o700 and info[3:5]==[uid,gid]
 assert lines[1+n:1+n+len(rows)]==[(r["path"]+": OK\n").encode() for r in rows]
 assert lines[-1]==b"S12_CANONICAL_BINDINGS_AND_SOURCE_VERIFIED\n"
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

def phase_control(pair,overall,seconds,epoch):
 start=time.monotonic_ns();phase=pair.Control(start,min(epoch,overall.epoch_end),seconds);original=phase.check
 def check(self):
  overall.check();original()
 phase.check=types.MethodType(check,phase)
 return phase

SELECTED_OVERALL_READ_ATTEMPTS = 173646


def install_selected_read_limit(overall, pair):
 """Precharge each attempted read before any reentrant stream servicing."""
 pair.need(not hasattr(overall,"selected_read_attempts"),"BINDING")
 original_read=overall.read
 overall.selected_read_attempts=0
 def selected_read(self,fd,amount):
  pair.need(self.selected_read_attempts<SELECTED_OVERALL_READ_ATTEMPTS,"READ_CALLS")
  self.selected_read_attempts+=1  # Never refunded, including failed/uncertain reads.
  return original_read(fd,amount)
 overall.read=types.MethodType(selected_read,overall)


def load_verified_admission(plan, command, overall, pair, transport, observer):
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
 pair.need(admission["version"]==pair.ONESHOT_ADMISSION_VERSION, "AUTHORITY")
 for key in ("source_git_sha","original_source_git_sha","original_source_root",
             "original_producer_path","allocation_producer_sha256"):
  pair.need(binding[key]==plan[key], "BINDING")
 pair.need(binding["original_selection_sha256"]==command["original_selection_sha256"], "BINDING")
 policy=admission["one_shot_control_policy"]
 modules=((Path(observer.__file__).absolute(),"stage12_ra_g1_one_shot_controls.py","one_shot_controls_sha256"),
          (Path(__file__).absolute(),"stage12_ra_g1_collection_driver.py","collection_driver_sha256"),
          (Path(transport.__file__).absolute(),"stage12_ra_g1_terminal_transport.py","transport_sha256"))
 for path,filename,key in modules:
  pair.need(path.name==filename and path.parent==Path(__file__).absolute().parent, "BINDING")
  pair.source_hash(path,policy[key],overall)
 overall.check()
 return admission


def execute(plan,command,rows,ancestors,base,modules,observer,wait_module,handoff,charge,mark_slot,record,handles):
 tc,pair,transport,_=modules;started=time.monotonic_ns();epoch=time.time_ns();overall=pair.Control(started,plan["window_end_epoch_ns"],1800)
 install_selected_read_limit(overall,pair)
 original_check=overall.check;streams=None;stage="SUBMIT";phase_owners=[];proc=None;fds={};readers={};failure=None;result=None
 def check(self):
  original_check()
  if streams is not None:streams.pump()
  original_check()
 overall.check=types.MethodType(check,overall)
 def action_control(name,seconds,end):
  c=phase_control(pair,overall,seconds,end);phase_owners.append((name,c));return c
 try:
  assert command["task_control_selection"] == dict(version="stage12_task_oneshot_controls_v1",maximum_probes=16,probe_seconds=15,minimum_start_spacing_seconds=120,spacing_anchor="PREVIOUS_DURABLE_RECORD_ACK_PLUS_120_SECONDS",maximum_process_units=208)
  assert observer.VERSION=="stage12_task_oneshot_controls_v1" and "observer_argv" not in command
  actual_admission=load_verified_admission(plan,command,overall,pair,transport,observer)
  for label in ("stdout","stderr"):
   path=base/("submission."+label+".raw");fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);fds[label]=(fd,path);readfd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);assert os.fstat(readfd).st_ino==os.fstat(fd).st_ino and os.fstat(readfd).st_dev==os.fstat(fd).st_dev;readers[label]=(readfd,path)
  record("EXECUTION_ENTRY.record",dict(entry_mono_ns=started,entry_epoch_ns=epoch,role_deadline_mono_ns=overall.end,window_end_epoch_ns=overall.epoch_end,source=plan["source_git_sha"],nonce=command["nonce"],actual_admission_sha256=command["admission_sha256"],actual_admission_version=actual_admission["version"],actual_admission_process_cap=actual_admission["maximum_preparation_and_native_processes"]))
  charge("QUALIFICATION_SOLE_SUBMIT_WAIT_TERMINAL_AND_POSSIBLE_NATIVE_ROLES",11)
  mark_slot()
  proc=subprocess.Popen(command["submit_argv"],stdin=subprocess.DEVNULL,stdout=fds["stdout"][0],stderr=fds["stderr"][0],start_new_session=True)
  record("SUBMISSION_CLIENT_IDENTITY.record",dict(pid=proc.pid,pgid=os.getpgid(proc.pid),entry_mono_ns=time.monotonic_ns(),one_submission_only=True))
  handles["submission"]=proc;handles["source_entry_mono_ns"]=started;handles["source_end_mono_ns"]=overall.end
  streams=SubmissionStreams(proc,readers,overall,wait_module,command["nonce"],command["selected_original_submission_epoch_ceiling"],1800,rows,ancestors,transport,plan["source_uid"],plan["source_gid"],record)
  stage="OBSERVE"
  controls_root=base/"one-shot-probes"
  overall.claim(0,True);controls_root.mkdir(mode=0o700)
  proof=observer.poll(plan,controls_root,overall,transport,pair,tc,charge,record)
  record("ONE_SHOT_DISPOSITION.record",proof)
  assert proof["status"]=="READY_ORIGINAL_AWAITING_CONTEXT_VALIDATION"
  overall.check();stage="READY";charge("QUALIFICATION_FRESH_READY_ORIGINAL_SAME_DOMAIN",7)
  c=action_control(stage,120,overall.epoch_end);ev,_=transport.fetch_batch([dict(label="ready",path=plan["remote_pair"]+"/TRANSPORT_READY.record",maximum=65536,local_name="transport-ready.original")],__import__("pathlib").Path(plan["local_final_logs"]),c,expected_uid=plan["source_uid"],expected_gid=plan["source_gid"])
  c.record(__import__("pathlib").Path(plan["local_final_logs"])/"READY_TRANSPORT_EVIDENCE.record",ev)
  ready_raw=pair.read_original(__import__("pathlib").Path(plan["local_final_logs"])/"transport-ready.original",c,65536);ready=tc.parse(ready_raw);pair.validate_ready(ready)
  assert ready["context"]["collection_source_git_sha"]==plan["source_git_sha"] and ready["context"]["original_source_git_sha"]==plan["original_source_git_sha"] and ready["context"]["original_job_id"]==actual_admission["original_job_id"] and ready["context"]["binding_sha256"]==command["binding_sha256"] and ready["context"]["authority_sha256"]==command["authority_sha256"]
  assert hashlib.sha256(ready_raw).hexdigest()==proof["ready_sha256"]
  ctx=ready["context"]
  assert ctx["original_workload_selection_sha256"]==command["original_selection_sha256"] and ctx["collection_uid"]==plan["source_uid"] and ctx["window"]==plan["window"] and ctx["collection_purpose"]==actual_admission["collection_purpose"] and ctx["scope"]==pair.NATIVE
  assert ctx["original_source_root"]==plan["original_source_root"] and ctx["original_producer_path"]==plan["original_producer_path"] and ctx["original_producer_sha256"]==plan["allocation_producer_sha256"] and ctx["external_logs"]==plan["collection_logs"]
  required_artifacts={"archive":plan["remote_pair"]+"/receive/terminal.s12c","before":plan["remote_pair"]+"/receive/before.jsonl","after":plan["remote_pair"]+"/receive/after.jsonl","verification":plan["remote_pair"]+"/WORKLOAD_VERIFICATION.record"}
  assert len(ready["artifacts"])==4 and {r["label"]:r["path"] for r in ready["artifacts"]}==required_artifacts
  overall.check()
  if streams.parser is not None and streams.parser.submitted is not None:assert streams.parser.submitted["job_id"]==ready["context"]["collection_job_id"]
  else:record("EARLY_WAIT_ID_PENDING.record",dict(native_context_job_id=ready["context"]["collection_job_id"],reason="WAIT_CLIENT_ID_NOT_YET_OBSERVED",not_terminal_acceptance=True))
  overall.epoch_end=min(overall.epoch_end,ready["context"]["overall_deadline_epoch_ns"])
  stage="FETCH";charge("QUALIFICATION_FOUR_COMPLETE_READY_ARTIFACTS",10);c=action_control(stage,900,ready["context"]["parent_deadline_epoch_ns"])
  receipt,transport_result=transport.fetch_ready(ready,hashlib.sha256(ready_raw).hexdigest(),__import__("pathlib").Path(plan["local_retained"]),__import__("pathlib").Path(plan["local_transport"]),control=c)
  record("FETCH_DISPOSITION.record",dict(status=transport_result["status"],completed_mono_ns=time.monotonic_ns(),read_bytes=c.read_bytes,read_calls=c.read_calls))
  stage="RECEIPT";charge("QUALIFICATION_EXCLUSIVE_RECEIPT_PUBLICATION_AND_ORIGINAL_ECHO",15);c=action_control(stage,120,ready["context"]["parent_deadline_epoch_ns"]);publication=handoff.publish_receipt(plan,ready,receipt,c);record("RECEIPT_DISPOSITION.record",publication)
  stage="WAIT_TERMINAL"
  while proc.poll() is None:overall.check();time.sleep(.05)
  overall.check();terminal_facts=streams.terminal();record("WAIT_AND_QUERY_FACTS.record",terminal_facts)
  assert terminal_facts["wait_exit"]==0 and terminal_facts["ssh_query_exit"]==0 and terminal_facts["terminal"]["state"]=="COMPLETED" and terminal_facts["terminal"]["exit_code"]=="0:0"
  assert terminal_facts["submission"]["job_id"]==ready["context"]["collection_job_id"]
  top=terminal_facts["terminal"];start_ns=__import__("datetime").datetime.strptime(top["start"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=__import__("datetime").timezone.utc).timestamp();end_ns=__import__("datetime").datetime.strptime(top["end"],"%Y-%m-%dT%H:%M:%S").replace(tzinfo=__import__("datetime").timezone.utc).timestamp()
  terminal=dict(version="stage12_terminal_collection_scheduler_v1",collection_job_id=terminal_facts["submission"]["job_id"],source_git_sha=plan["source_git_sha"],binding_sha256=command["binding_sha256"],scope=pair.NATIVE,scheduler_state="COMPLETED",exit_code="0:0",start_epoch_ns=int(start_ns)*10**9,end_epoch_ns=int(end_ns)*10**9,observed_epoch_ns=time.time_ns());record("COLLECTION_TERMINAL.record",terminal)
  stage="FINAL_OPEN";charge("QUALIFICATION_POSTTERMINAL_SIX_ORIGINALS_AND_ACTUAL_OPENER",12);c=action_control(stage,120,min(ready["context"]["overall_deadline_epoch_ns"],terminal["start_epoch_ns"]+1800*10**9));open_entry=time.monotonic_ns();result=handoff.finish_collected(plan,terminal,__import__("pathlib").Path(plan["local_final_logs"]),__import__("pathlib").Path(plan["local_retained"]),c)
  overall.check();record("ACTUAL_OPENER_COMPLETION.record",dict(invoked_mono_ns=open_entry,complete_mono_ns=time.monotonic_ns(),complete_epoch_ns=time.time_ns(),status=result["status"],result=result));stage="COMPLETE"
 except BaseException as error:
  failure=dict(stage=stage,code=pair.safe_code(error),kind=("TC_STOP" if type(error) is tc.Stop else "ASSERTION" if type(error) is AssertionError else "OS_ERROR" if isinstance(error,OSError) else "UNCLASSIFIED"),observed_mono_ns=time.monotonic_ns(),observed_epoch_ns=time.time_ns(),transport=getattr(error,"transport_diagnostic",None),historical_cause_not_inferred=True)
  try:record("FIRST_FAILURE.record",failure)
  except BaseException:failure["diagnostic_retention"]="INCOMPLETE"
 finally:
  if proc is not None and proc.poll() is None:
   while time.monotonic_ns()<overall.end and time.time_ns()<overall.epoch_end and proc.poll() is None:
    try:streams.pump(True)
    except BaseException:break
    time.sleep(.1)
  actual_exit=proc.poll() if proc is not None else None
  if actual_exit is not None:
   proc.wait(timeout=0)
   if streams is not None:
    try:record("FINAL_WAIT_AND_QUERY_FACTS.record",streams.terminal())
    except BaseException:pass
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
  output["persisted_timestamp_scope"]="BEFORE_OUTCOME_RECORD_FSYNC_NOT_FINAL_RETURN"
  try:record("COORDINATOR_OUTCOME.record",output)
  except BaseException:output["status"]="INCOMPLETE";output["diagnostic_retention"]="INCOMPLETE"
  output["actual_post_record_mono_ns"]=time.monotonic_ns();output["actual_post_record_epoch_ns"]=time.time_ns()
  if output["actual_post_record_mono_ns"]>=overall.end or output["actual_post_record_epoch_ns"]>=overall.epoch_end:output["status"]="INCOMPLETE";output["post_record_lateness"]=True
 return output

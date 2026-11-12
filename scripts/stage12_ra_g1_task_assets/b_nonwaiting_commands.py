"""Task-only REP ordinary submission and fixed long-envelope observations.

Commands and parsed submission facts issue no execution, factual or input approval.
The existing online handoff driver/tail is separate and remains unchanged.
"""
from pathlib import Path, PurePosixPath
import hashlib, importlib.util, json, os, re, shlex, stat, time
VERSION="stage12_b_direct_layout_submit_and_observation_v4"
SUBMISSION_RECORD="stage12_b_catalog_observed_submit_client_v3"
SCHEDULE_VERSION="stage12_b_catalog_fixed_terminal_schedule_v3"
OFFSETS=tuple(range(0,7801,600))+(8260,8380)
FOLLOWON_AND_REVIEW_SECONDS=1920
NATIVE_PROCESSING_SECONDS=8160
NATIVE_SCHEDULER_SECONDS=8400
ORIGINAL_WATCH_SECONDS=8400
WINDOW_END_NS=1794597201620987000
NATIVE_PYTHON="/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/runtimes/stage06/stage06_development_20260828T223804Z_f39047cc825d/venv/bin/python"
PROJECT="/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/"
def need(value,code="B_NONWAITING_BINDING"):
    if not value:raise RuntimeError(code)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(value):return(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def ident(s):return(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def read_ref(value,maximum=4*2**20):
    need(type(value)is dict and set(value)=={"path","sha256"} and type(value["sha256"])is str and re.fullmatch("[0-9a-f]{64}",value["sha256"]))
    p=Path(value["path"]);need(not any(x in {".git",".ssh",".aws",".config","credentials","secrets","HOLDOUT"} or x.startswith(".env") for x in p.parts),"B_REFERENCE_SECRET_PATH");before=p.lstat()
    need(p.is_absolute() and p.resolve(strict=True)==p and stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<=before.st_size<=maximum)
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);out=bytearray()
    try:
        need(ident(os.fstat(fd))==ident(before))
        while len(out)<before.st_size:
            raw=os.read(fd,min(65536,before.st_size-len(out)));need(bool(raw));out.extend(raw)
        need(os.read(fd,1)==b"" and ident(os.fstat(fd))==ident(before)==ident(p.lstat()))
    finally:os.close(fd)
    raw=bytes(out);need(sha(raw)==value["sha256"]);return raw

def source_module(ref,source_dir,source_inventory):
    source_dir=Path(source_dir);p=source_dir/"scripts/stage12_ra_g1_nonwaiting_submit.py"
    need(Path(ref["path"])==p)
    rows=[r for r in source_inventory if r["path"]=="scripts/stage12_ra_g1_nonwaiting_submit.py"]
    need(len(rows)==1 and rows[0]["sha256"]==ref["sha256"])
    raw=read_ref(ref,256*1024);need(len(raw)==rows[0]["bytes"])
    spec=importlib.util.spec_from_file_location("selected_b_nonwaiting_source",p)
    result=importlib.util.module_from_spec(spec);exec(compile(raw,str(p),"exec"),result.__dict__)
    need(result.VERSION=="stage12_nonwaiting_submission_terminal_v1" and result.QUERY_PROCESS_UNITS==4 and result.MAX_QUERIES==16 and result.QUERY_SECONDS==15)
    return result

def project_path(value):
    need(type(value)is str);p=PurePosixPath(value)
    need(p.is_absolute() and str(p)==value and value.startswith(PROJECT) and ".." not in p.parts and not any(x in {"public","HOLDOUT",".git",".ssh",".aws",".config","credentials","secrets"} or x.startswith(".env") for x in p.parts))
    return p

NATIVE_LAYOUT_VERSION="stage12_rep_direct_allocation_separate_records_v1"


def selected_native_layout(paths):
    """Exact selected paths, with a direct allocation and disjoint records base."""
    need(type(paths) is dict,"B_NATIVE_LAYOUT")
    source,root,records=(project_path(paths[key]) for key in ("source","allocation_root","records"))
    controlled=PurePosixPath(PROJECT)/"derived/controlled/stage12/client_diagnostics"
    base=records.parent
    need(root.parent==controlled and root.name.startswith("ra_g1_") and root.name!="ra_g1_"
        and records.name=="records" and base.parent==controlled and base!=root
        and source.parent==PurePosixPath(PROJECT)/"integration_stage12"
        and all(left!=right and not left.is_relative_to(right) and not right.is_relative_to(left)
                for left,right in ((root,base),(root,source),(base,source))),"B_NATIVE_LAYOUT")
    for key,value in paths.items():
        path=project_path(value)
        need(not any(ord(ch)<32 or ord(ch)==127 for ch in value),"B_NATIVE_LAYOUT")
        if key not in ("source","allocation_root","records","log"):
            need(path!=root and path.is_relative_to(root),"B_NATIVE_LAYOUT")
    need(paths["input"]==str(root/"input.json") and paths["binding"]==str(root/"binding")
        and paths["output"]==str(root/"diagnostic") and paths["context"]==str(root/"context.record")
        and paths["log"]==str(records/"slurm.log"),"B_NATIVE_LAYOUT")
    return dict(version=NATIVE_LAYOUT_VERSION,allocation_root=str(root),records=str(records),
        records_base=str(base),controlled_parent=str(controlled),source=str(source),
        allocation_creation_owner="NATIVE_COLLECTOR_EXCLUSIVE")


def render_submission(*,allocation,selection_sha256,gate_sha256,helper_sha256,nonce,shared,deadline_epoch_ns):
    # The caller has already run current canonical producer/selection/resource/gate validators.
    need(type(allocation)is dict and allocation.get("scope")=="REPRESENTATIVE_NO_SERVICE")
    need(type(nonce)is str and re.fullmatch("[0-9a-f]{32}",nonce))
    need(all(type(x)is str and re.fullmatch("[0-9a-f]{64}",x) for x in (selection_sha256,gate_sha256,helper_sha256)))
    need(type(deadline_epoch_ns)is int and 0<deadline_epoch_ns<=WINDOW_END_NS)
    source=allocation["source_sha"];need(re.fullmatch("[0-9a-f]{40}",source))
    p=allocation["paths"];layout=selected_native_layout(p);ns=project_path(p["source"]);records=project_path(p["records"])
    for key in ("allocation_root","input","binding","output","supervisor_state","worker_return"):project_path(p[key])
    selected=str(records/"FINAL_SELECTION.record")
    env={"STAGE12_RA_SOURCE":str(ns),"STAGE12_RA_SHA":source,"STAGE12_RA_PYTHON":NATIVE_PYTHON,
         "STAGE12_RA_SELECTION":selected,"STAGE12_RA_SELECTION_SHA":selection_sha256,
         "STAGE12_RA_ROOT":p["allocation_root"],"STAGE12_RA_INPUT":p["input"],"STAGE12_RA_BINDING":p["binding"],
         "STAGE12_RA_OUTPUT":p["output"],"STAGE12_RA_STATE":p["supervisor_state"],"STAGE12_RA_RETURN":p["worker_return"],
         "STAGE12_RA_HELPER_SHA":helper_sha256,"STAGE12_RA_ENVIRONMENT_GATE_SHA":gate_sha256}
    prefix="\n".join(("test ! -e "+shlex.quote(p["allocation_root"]),"test ! -L "+shlex.quote(p["allocation_root"]),
        "test -d "+shlex.quote(str(records)),"test ! -L "+shlex.quote(str(records))))+"\n"
    prefix+="\n".join("export "+key+"="+shlex.quote(value) for key,value in sorted(env.items()))+"\ncd -- "+shlex.quote(str(ns))+"\n"
    tag="stage12-rep:"+nonce+":"+selection_sha256
    argv=["sbatch","--parsable","--nodes=1","--ntasks=1","--cpus-per-task=2","--mem=6G","--time=02:20:00","--partition=general1","--account=footprint","--no-requeue",
          "--chdir="+str(ns),"--comment="+tag,"--output="+str(records/"slurm.log"),"--error="+str(records/"slurm.err"),str(ns/"cluster/goethe_nhr/stage12_ra_g1_allocation.sbatch")]
    ordinary=shared.ordinary_sbatch_argv(argv)
    need(ordinary[:3]==["env","-u","SBATCH_WAIT"] and "--wait" not in ordinary and "-W" not in ordinary)
    command=shared.submission_argv(prefix,argv,nonce,deadline_epoch_ns,NATIVE_SCHEDULER_SECONDS)
    return dict(version=VERSION,state="MATERIALIZED_COMMAND_NOT_SUBMISSION_AUTHORITY",source_sha=source,native_layout=layout,
        nonce=nonce,selection_sha256=selection_sha256,gate_sha256=gate_sha256,helper_sha256=helper_sha256,
        raw_sbatch_argv=argv,command_scoped_sbatch_argv=ordinary,submit_argv=command,prefix=prefix,expected_prelude_b64="",
        submission_window_epoch_ns=deadline_epoch_ns,submission_remaining_seconds=NATIVE_SCHEDULER_SECONDS,
        submission_process_units=4,submission_invocations=["local SSH","remote Bash","env -u SBATCH_WAIT","sbatch --parsable"],
        job_identity_comment=tag,expected_uid=60099,account="footprint",partition="general1",native_processing_seconds=8160,native_scheduler_seconds=8400,
        online_handoff_watch_seconds=8400,online_handoff_watch_changed=False,no_resubmission_on_uncertain_submission=True,
        raw_stdout_is_not_wait_result=True,submit_exit_zero_is_not_job_success=True)

def terminal_schedule(*,entry_mono_ns,entry_epoch_ns,absolute_window_end_epoch_ns):
    need(type(entry_mono_ns)is int and entry_mono_ns>0 and type(entry_epoch_ns)is int and entry_epoch_ns>0)
    need(type(absolute_window_end_epoch_ns)is int and absolute_window_end_epoch_ns==WINDOW_END_NS)
    need(entry_epoch_ns+(NATIVE_SCHEDULER_SECONDS+FOLLOWON_AND_REVIEW_SECONDS)*10**9<absolute_window_end_epoch_ns,"B_WINDOW_INSUFFICIENT")
    return dict(version=SCHEDULE_VERSION,anchor="ORIGINAL_B_SUBMISSION_ENTRY_NOT_RESET",entry_mono_ns=entry_mono_ns,entry_epoch_ns=entry_epoch_ns,
        deadline_mono_ns=entry_mono_ns+8400*10**9,deadline_epoch_ns=entry_epoch_ns+8400*10**9,
        absolute_window_end_epoch_ns=absolute_window_end_epoch_ns,offset_seconds=list(OFFSETS),maximum_observations=16,
        final_authoritative_slots=[14,15],query_seconds=15,query_process_units=4,maximum_query_process_units=64,
        early_terminal_rule="STOP_REGULAR_SLOTS;FINAL_START_OFFSETS=FIRST_TERMINAL_ACTUAL_START_MINUS_ORIGINAL_ENTRY_PLUS_120_AND_240",
        last_selected_query_finish_offset_seconds=8395,finalization_reserve_seconds=5,
        followon_and_review_reserved_seconds=FOLLOWON_AND_REVIEW_SECONDS,
        queue_and_full_scheduler_risk="EARLIER_CONTROLLER_EXHAUSTION_CAN_REMAIN_INCOMPLETE;NO_NATIVE_DEADLINE_RESET_OR_EXTENSION",
        native_processing_seconds=8160,native_scheduler_seconds=8400,online_handoff_watch_seconds=8400)

def final_not_before(schedule,first_terminal_query_start=None):
    origin=schedule["entry_mono_ns"]
    if first_terminal_query_start is None:return origin+8260*10**9,origin+8380*10**9
    need(type(first_terminal_query_start)is int and origin<=first_terminal_query_start<origin+8260*10**9,"B_TERMINAL_ANCHOR")
    offsets=(first_terminal_query_start-origin+120*10**9,first_terminal_query_start-origin+240*10**9)
    need(origin+offsets[1]+15*10**9<schedule["deadline_mono_ns"],"B_FINAL_OBSERVATIONS_DO_NOT_FIT")
    return origin+offsets[0],origin+offsets[1]

def slot_bounds(schedule,index,*,first_terminal_query_start=None):
    need(type(schedule)is dict and schedule.get("version")==SCHEDULE_VERSION and schedule.get("offset_seconds")==list(OFFSETS) and schedule.get("maximum_observations")==16)
    need(type(index)is int and 0<=index<16)
    origin=schedule["entry_mono_ns"]
    if index>=14:
        finals=final_not_before(schedule,first_terminal_query_start)
        return finals[index-14],schedule["deadline_mono_ns"]-(135 if index==14 else 15)*10**9
    need(first_terminal_query_start is None,"B_REGULAR_OBSERVATION_AFTER_TERMINAL")
    earliest=origin+OFFSETS[index]*10**9
    next_offset=OFFSETS[index+1]
    return earliest,origin+(next_offset-15)*10**9

def run_observation(*,shared,schedule,index,job_id,nonce,owner,record,charge,service,bank,first_terminal_query_start=None,cleanup_only=False):
    need(type(owner)is ObservationOwner and bank is owner.bank,"B_OBSERVER_OWNER_BANK_IDENTITY")
    need(type(bank)is dict and bank.get("maximum")==16 and bank.get("normal_slots")==16 and bank.get("cancellation_slots")==0,"B_SHARED_QUERY_BANK_REQUIRED")
    need(type(cleanup_only)is bool)
    earliest,latest=slot_bounds(schedule,index,first_terminal_query_start=first_terminal_query_start)
    if bank.get("last_started_mono_ns")is not None:earliest=max(earliest,bank["last_started_mono_ns"]+120*10**9)
    need(owner.end==schedule["deadline_mono_ns"] and owner.epoch_end==schedule["deadline_epoch_ns"],"B_OBSERVER_ORIGIN")
    while time.monotonic_ns()<earliest:
        owner.check();service();time.sleep(min(.05,max(0,(earliest-time.monotonic_ns())/1e9)))
    owner.check();need(time.monotonic_ns()<latest,"B_OBSERVATION_SLOT_EXPIRED")
    parser=shared.QueryParser(job_id,nonce,60099,"footprint","general1")
    result=shared.run_query(shared.query_argv(job_id,nonce),parser,owner,record,"TERMINAL_QUERY_"+format(index+1,"02d"),charge,bank=bank,kind="NORMAL")
    owner.check();service();need(result["query_entered_mono_ns"]<latest,"B_OBSERVATION_ACTUAL_SLOT_EXPIRED")
    if cleanup_only:result=dict(result,purpose="CLEANUP_ONLY_AFTER_IRREVERSIBLE_FAILURE_NO_ACCEPTANCE_RECOVERY")
    need(result["status"] in ("ACCOUNTING_PENDING","NONTERMINAL","AUTHORITATIVE_TERMINAL"))
    return result

def final_terminal_disposition(first,second,*,job_id,nonce):
    for row in (first,second):
        need(type(row)is dict and row.get("version")=="stage12_authoritative_terminal_query_v1" and row.get("job_id")==job_id and row.get("nonce")==nonce)
    need(first["query_entered_mono_ns"]<second["query_entered_mono_ns"] and first["query_completed_mono_ns"]<=second["query_entered_mono_ns"])
    if any(row["status"]!="AUTHORITATIVE_TERMINAL" for row in (first,second)):return "INCOMPLETE"
    if all(row["all_completed_zero"] is True for row in (first,second)):return "TERMINAL_METADATA_SUCCESS_NOT_B_ACCEPTANCE"
    return "TERMINAL_METADATA_FAILURE_NOT_B_ACCEPTANCE"

def validate_submission(*,record,commands,stdout,stderr,shared):
    need(type(record)is dict and record.get("version")==SUBMISSION_RECORD and record.get("command_sha256")==sha(canonical(commands)))
    need(record.get("source_sha")==commands["source_sha"] and record.get("nonce")==commands["nonce"])
    need(record.get("actual_submit_client_exit")==0 and record.get("joined") is True and record.get("stdout_eof") is True and record.get("stderr_eof") is True and record.get("cleanup_uncertain") is False)
    need(type(stdout)is bytes and type(stderr)is bytes and len(stdout)<=65536 and len(stderr)<=65536 and record.get("stdout_sha256")==sha(stdout) and record.get("stderr_sha256")==sha(stderr))
    parser=shared.SubmitParser(commands["nonce"],commands["submission_window_epoch_ns"],commands["submission_remaining_seconds"],expected_prelude=b"")
    parser.feed(stdout);facts=parser.finish(record["actual_submit_client_exit"])
    need(facts["version"]==shared.SUBMIT_VERSION and facts["submit_client_exit"]==0 and facts["job_success"] is False)
    return facts

def graph_quote():
    rows=[dict(stage="PINNED_PRIVATE_GIT_CHECKOUT",units=6,invocations=["root-selected exact six-process Git checkout graph"]),dict(stage="METADATA_EXCLUSIVE_DESTINATION",units=8,invocations=["SSH","Bash","mkdir","stat before","stat after","filesystem stat","readlink before","readlink after"]),
          dict(stage="TRANSFER",units=4,invocations=["SCP","SSH transport","remote protocol shell/server","remote protocol worker"]),
          dict(stage="TRANSFER_VERIFY",units=11,invocations=["SSH","Bash","stat before","sha256sum","Git rev-parse substitution wrapper","git rev-parse","Git status substitution wrapper","git status","stat after","readlink before","readlink after"]),
          dict(stage="SUBMIT_ONCE",units=4,invocations=["SSH","Bash","env -u SBATCH_WAIT","sbatch --parsable"]),
          dict(stage="EXACT_OWNED_FAILURE_IDENTITY_AND_OPTIONAL_CANCEL",units=8,invocations=["SSH","Bash","timeout","scontrol","SSH","Bash","timeout","scancel"]),
          dict(stage="TERMINAL_OBSERVATIONS",units=64,invocations=["16 * (SSH+Bash+timeout+SACCT)"]),
          dict(stage="ONLINE_HANDOFF_HELPER_ROLES",units=42,invocations=["prepaid exact seven helper-role slots"]),
          dict(stage="ONLINE_HANDOFF_DRIVER",units=1,invocations=["verified repository Python driver"])]
    need(sum(r["units"] for r in rows)==148)
    return dict(version=VERSION,state="EXACT_WRAPPER_QUOTE_PENDING_ACTUAL_MATERIALIZED_BINDINGS",maximum_process_units=148,permitted_process_ceiling=192,remaining_margin=44,rows=rows,
        historical_baseline_75_preserved=True,three_units_per_query_not_assumed=True,role42_is_single_global_precharge=True,
        maximum_terminal_query_read_calls=1536,maximum_terminal_query_returned_bytes=131072,maximum_terminal_query_encoded_records=262144,
        maximum_terminal_query_creations=16,query_record_limit_each=16384,no_native_descendant_or_memory_guarantee=True,
        native_execution_counters_are_separate=dict(python_invocations=5,utility_invocations=256),no_new_job_or_authority=True)

def observe_submission(*,commands_ref,stdout_ref,stderr_ref,operation_ref,shared):
    commands_raw=read_ref(commands_ref,65536);commands=json.loads(commands_raw);need(canonical(commands)==commands_raw and commands.get("version")==VERSION)
    stdout=read_ref(stdout_ref,65536);stderr=read_ref(stderr_ref,65536)
    operation_raw=read_ref(operation_ref,65536);operation=json.loads(operation_raw)
    # This is explicitly the fixed root-runner's metadata schema, not a production canonical control.
    need(type(operation)is dict and operation.get("argv_sha256")==sha(json.dumps(commands["submit_argv"]).encode()))
    need(type(operation.get("actual_exit"))is int and operation["actual_exit"]==0 and operation.get("joined") is True and operation.get("eof")==["stderr","stdout"] and operation.get("cleanup_uncertain") is False and operation.get("within_deadline") is True and operation.get("first_safe_error") is None and operation.get("signals")==[])
    need(operation["entry_mono_ns"]<=operation["complete_mono_ns"]<=operation["deadline_mono_ns"] and time.monotonic_ns()<operation["deadline_mono_ns"],"B_SUBMISSION_OBSERVATION_LATE")
    need(operation.get("returned_bytes")==len(stdout)+len(stderr))
    result=dict(version=SUBMISSION_RECORD,source_sha=commands["source_sha"],nonce=commands["nonce"],command_sha256=sha(commands_raw),commands=commands_ref,original_stdout=stdout_ref,original_stderr=stderr_ref,original_operation=operation_ref,
        actual_submit_client_exit=operation["actual_exit"],joined=True,stdout_eof=True,stderr_eof=True,cleanup_uncertain=False,
        stdout_sha256=sha(stdout),stderr_sha256=sha(stderr),observed_mono_ns=time.monotonic_ns(),observed_epoch_ns=time.time_ns(),job_success=False,no_resubmission_if_lost_or_uncertain=True)
    result["parsed_submission"]=validate_submission(record=result,commands=commands,stdout=stdout,stderr=stderr,shared=shared)
    return result

def materialize_owned_controls(*,commands,job_id,epoch_end_ns,cancel_module):
    need(type(job_id)is int and 0<job_id<10**20 and type(epoch_end_ns)is int and 0<epoch_end_ns<=WINDOW_END_NS)
    need(commands.get("version")==VERSION and cancel_module.VERSION=="stage12_task_owned_cancel_nonwaiting_v3")
    args=commands["raw_sbatch_argv"]
    def option(prefix):
        rows=[s[len(prefix):] for s in args if s.startswith(prefix)];need(len(rows)==1);return rows[0]
    source=option("--chdir=");project_path(source)
    expected=dict(JobId=str(job_id),uid=60099,Account="footprint",Partition="general1",Command=args[-1],WorkDir=source,
        StdOut=option("--output="),StdErr=option("--error="),Comment=commands["job_identity_comment"])
    need(expected["Command"]==source+"/cluster/goethe_nhr/stage12_ra_g1_allocation.sbatch")
    need(expected["Comment"]=="stage12-rep:"+commands["nonce"]+":"+commands["selection_sha256"])
    return dict(version="stage12_b_materialized_owned_controls_v1",job_id=job_id,source_sha=commands["source_sha"],nonce=commands["nonce"],selection_sha256=commands["selection_sha256"],
        expected_scontrol_identity=expected,scontrol_argv=cancel_module.operation_argv("SCONTROL",job_id,epoch_end_ns),
        scancel_argv=cancel_module.operation_argv("SCANCEL",job_id,epoch_end_ns),epoch_end_ns=epoch_end_ns,operation_process_units=4,maximum_operations=2,maximum_process_units=8,
        maximum_reads=128,maximum_return_bytes=81922,maximum_records=2,maximum_record_bytes_each=65536,
        terminal_verification="ONLY_EXISTING_REMAINING_SHARED_B_QUERY_BANK;NO_LEGACY_SACCT_CALLS",sacct_argv=None,no_request_without_exact_current_owner=True)

def run_owned_cancel(*,controls,commands,cancel_module,owner,charge,persist,current_grant,mark_cancel_requested,first_failure_retained):
    need(first_failure_retained is True,"B_CANCEL_INITIATING_FAILURE_NOT_RETAINED")
    owner.check();scope=current_grant(controls["job_id"])
    need(scope.get("active")is True and scope.get("job_id")==controls["job_id"] and scope.get("nonce")==commands["nonce"] and scope.get("source_git_sha")==commands["source_sha"] and scope.get("selection_sha256")==commands["selection_sha256"]
        and scope.get("maximum_cancel_requests")==1 and type(scope.get("cancel_request_count"))is int and scope["cancel_request_count"]==0,"B_CANCEL_CURRENT_OWNER_REJECTED")
    need(type(controls.get("epoch_end_ns"))is int and controls["epoch_end_ns"]<=owner.epoch_end,"B_CANCEL_ORIGINAL_EPOCH_CHANGED")
    expected_controls=materialize_owned_controls(commands=commands,job_id=controls["job_id"],epoch_end_ns=controls["epoch_end_ns"],cancel_module=cancel_module)
    need(controls==expected_controls,"B_CANCEL_MATERIALIZED_CONTROLS_CHANGED")
    rows=[]
    raw,code,ownership_hash=cancel_module._run_bounded_child(argv=controls["scontrol_argv"],overall=owner,kind="SCONTROL",index=0,job_id=controls["job_id"],charge=charge,persist=persist,operation_rows=rows)
    need(code==0,"B_CANCEL_IDENTITY_QUERY_FAILED")
    state=cancel_module.parse_scontrol(raw,controls["expected_scontrol_identity"])
    if state["state"] in cancel_module.TERMINAL:
        return dict(status="ALREADY_TERMINAL_AWAIT_EXISTING_QUERY_BANK",operations=rows,cancel_request_consumed=False,terminal_verification=controls["terminal_verification"],native_role_closure="UNKNOWN")
    owner.check();scope2=current_grant(controls["job_id"]);need(scope2==scope,"B_CANCEL_CURRENT_OWNER_CHANGED")
    mark_cancel_requested(controls["job_id"],ownership_hash)
    raw,code,_=cancel_module._run_bounded_child(argv=controls["scancel_argv"],overall=owner,kind="SCANCEL",index=0,job_id=controls["job_id"],charge=charge,persist=persist,operation_rows=rows)
    need(code==0,"B_CANCEL_REQUEST_FAILED_OR_UNCERTAIN")
    return dict(status="ONE_CANCEL_REQUEST_REPORTED_NOT_TERMINATION_PROOF",operations=rows,cancel_request_consumed=True,terminal_verification=controls["terminal_verification"],native_role_closure="UNKNOWN")

def materialize_preparation(*,prepared,allocation,source_tree,backend_inventory,output,write):
    """Stage exact immutable control bytes and render bounded existing CLI interfaces."""
    need(prepared.get("status")=="CANONICAL_BINDINGS_GENERATED_NOT_NATIVE_READY_OR_SUBMISSION" and prepared["source_sha"]==allocation["source_sha"])
    need(re.fullmatch("[0-9a-f]{40}",source_tree) and type(backend_inventory)is list and len(backend_inventory)==5)
    p=allocation["paths"];layout=selected_native_layout(p);source=project_path(p["source"]);records=project_path(p["records"]);allocation_root=project_path(p["allocation_root"]);base=records.parent;parent=base.parent
    need(backend_inventory==allocation["accounting_inventory"]["backends"],"B_BACKEND_SELECTION_CHANGED")
    uploads=json.loads(read_ref(prepared["record_uploads"],2**20));need(type(uploads)is list and len(uploads)<=127)
    selection_raw=read_ref(prepared["selection"],4*2**20);need(canonical(allocation)==selection_raw)
    uploads=list(uploads)+[dict(local=prepared["selection"]["path"],remote=str(records/"FINAL_SELECTION.record"),bytes=len(selection_raw),sha256=sha(selection_raw))]
    staged=[];seen=set();total=0;output=Path(output);output.mkdir(mode=0o700)
    for row in uploads:
        need(type(row)is dict and set(row)=={"local","remote","bytes","sha256"})
        remote=project_path(row["remote"]);need(remote.parent==records and remote.name not in seen);seen.add(remote.name)
        before=Path(row["local"]).lstat();need(stat.S_IMODE(before.st_mode)==0o600 and before.st_uid==os.geteuid())
        body=read_ref(dict(path=row["local"],sha256=row["sha256"]),4*2**20);need(type(row["bytes"])is int and len(body)==row["bytes"])
        total+=len(body);need(total<=16*2**20)
        pin=write(output/remote.name,body)
        staged.append(dict(local=str(output/remote.name),remote=str(remote),bytes=len(body),sha256=sha(body)))
    backend_paths=[]
    for row in backend_inventory:
        need(type(row)is dict and type(row.get("path"))is str);path=PurePosixPath(row["path"])
        need(path.is_absolute() and str(path)==row["path"] and ".." not in path.parts and not any(ord(c)<32 or ord(c)==127 for c in row["path"]) and len(row["path"].encode())<=4096)
        backend_paths.append(str(path))
    need(len(set(backend_paths))==5)
    before_paths=[str(source),str(parent)]+backend_paths
    after_paths=[str(source),str(parent),str(base),str(records)]+backend_paths
    fmt="%n|%d|%i|%f|%u|%g|%h|%s|%y|%z|%F"
    q=shlex.quote
    def domain(tag):
        return "printf '%s\\n' "+q(tag)+"\nIFS= read -r selected_boot < /proc/sys/kernel/random/boot_id\nprintf '%s|%s|%s|%s\\n' \"$HOSTNAME\" \"$selected_boot\" \"$BASHPID\" \"$EPOCHREALTIME\"\nreadlink -- /proc/self/ns/mnt\n"
    def stats(paths):return "stat -c "+q(fmt)+" -- "+" ".join(map(q,paths))+"\n"
    script="set -euo pipefail\numask 077\nexport LC_ALL=C TZ=UTC\ntest -d "+q(str(parent))+"\ntest ! -L "+q(str(parent))+"\ntest ! -e "+q(str(base))+"\ntest ! -L "+q(str(base))+"\n"
    script+="test ! -e "+q(str(allocation_root))+"\ntest ! -L "+q(str(allocation_root))+"\n"
    script+=domain("B_SETUP_BEFORE_DOMAIN")+"printf '%s\\n' B_SETUP_BEFORE\n"+stats(before_paths)
    script+="mkdir -- "+q(str(base))+" "+q(str(records))+"\n"
    script+="printf '%s\\n' B_SETUP_AFTER\n"+stats(after_paths)+domain("B_SETUP_AFTER_DOMAIN")
    script+="printf '%s\\n' B_SETUP_FILESYSTEM\nstat -f -c '%a|%S|%d' -- "+q(str(records))+"\nprintf '%s\\n' B_SETUP_CLOSED\n"
    verify_paths=[r["remote"] for r in staged]
    checks="".join(r["sha256"]+"  "+r["remote"]+"\n" for r in staged)
    verify="set -euo pipefail\nexport LC_ALL=C TZ=UTC\ncd -- "+q(str(source))+"\n"
    verify+="test ! -e "+q(str(allocation_root))+"\ntest ! -L "+q(str(allocation_root))+"\n"
    verify+=domain("B_VERIFY_BEFORE_DOMAIN")+"printf '%s\\n' B_VERIFY_BEFORE\n"+stats(verify_paths)
    verify+="sha256sum --check --status <<'B_CURRENT_CANONICAL_ORIGINALS'\n"+checks+"B_CURRENT_CANONICAL_ORIGINALS\n"
    verify+="actual_source=$(git rev-parse HEAD HEAD^{tree})\n[[ \"$actual_source\" == "+q(allocation["source_sha"]+"\n"+source_tree)+" ]]\nactual_changes=$(git status --porcelain)\n[[ -z \"$actual_changes\" ]]\n"
    verify+="printf '%s\\n' B_VERIFY_AFTER\n"+stats(verify_paths)+domain("B_VERIFY_AFTER_DOMAIN")+"printf '%s\\n' B_VERIFY_CLOSED\n"
    # Include conservative textual integer/time/domain formatting overhead before any transport.
    setup_return=sum(len(x.encode())+256 for x in before_paths+after_paths)+8192
    verify_return=2*sum(len(x.encode())+256 for x in verify_paths)+8192
    need(max(setup_return,verify_return)<=65536,"B_METADATA_RETURN_BOUND")
    ssh=lambda body:["/usr/bin/ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=15","goethe","exec bash -c "+shlex.quote(body)]
    return dict(version="stage12_b_direct_layout_materialized_preparation_v2",native_layout=layout,state="EXACT_COMMANDS_NOT_EXECUTION_AUTHORITY",source_sha=allocation["source_sha"],source_tree=source_tree,
        setup_argv=ssh(script),scp_argv=["/usr/bin/scp","-p"]+[r["local"] for r in staged]+["goethe:"+str(records)+"/"],verify_argv=ssh(verify),
        setup_process_units=8,transfer_process_units=4,verify_process_units=11,setup_before_paths=before_paths,setup_after_paths=after_paths,
        setup_domain_comparison="BEFORE_AND_AFTER_WITHIN_THIS_ONE_SSH_SESSION_ONLY",verify_domain_comparison="BEFORE_AND_AFTER_WITHIN_THIS_ONE_SSH_SESSION_ONLY",compare_identity_across_separate_sessions=False,
        planned_setup_parent_child_count_change=True,immutable_backend_before_after_complete_identity_required=True,source_and_parent_stable_dev_inode_mode_uid_gid_required=True,
        transferred_regular_files_complete_identity_hash_and_EOF_required=True,staged_files=staged,staged_data_bytes=total,maximum_staged_bytes=16*2**20,maximum_staged_creations=128,
        maximum_setup_return_bytes=setup_return,maximum_verify_return_bytes=verify_return,unknown_native_protocol_workers="ACCEPTED_RA_G1_UNCERTAINTY_NOT_A_HARD_PROCESS_GUARANTEE")

class ObservationOwner:
    """One fixed B metadata observer; never constructs or mutates a collection Control.

    Read/write limits cover sixteen query captures, two owned cancellation captures
    and at most32 small durable records including readback. They do not assert
    native allocator, descendant, physical-storage or timing enforcement bounds.
    """
    MAX_RECORDS=32
    MAX_RECORD_BYTES=65536
    MAX_READ_CALLS=16*96+2*64+32*65
    MAX_READ_BYTES=16*(2*4097)+2*40961+32*(65536+1)
    MAX_WRITE_BYTES=32*65536
    def __init__(self,*,schedule,directory,shared,job_id,nonce,source_sha,selection_sha256,service):
        need(type(schedule)is dict and schedule==terminal_schedule(entry_mono_ns=schedule["entry_mono_ns"],entry_epoch_ns=schedule["entry_epoch_ns"],absolute_window_end_epoch_ns=schedule["absolute_window_end_epoch_ns"]),"B_OBSERVER_SCHEDULE_CHANGED")
        need(type(job_id)is int and 0<job_id<10**20 and type(nonce)is str and re.fullmatch("[0-9a-f]{32}",nonce) and re.fullmatch("[0-9a-f]{40}",source_sha) and re.fullmatch("[0-9a-f]{64}",selection_sha256) and callable(service))
        need(time.monotonic_ns()>=schedule["entry_mono_ns"] and time.time_ns()>=schedule["entry_epoch_ns"],"B_OBSERVER_FUTURE_ORIGIN")
        self._schedule=dict(schedule);self._end=schedule["deadline_mono_ns"];self._epoch_end=schedule["deadline_epoch_ns"]
        self._entry=schedule["entry_mono_ns"];self._service=service;self._busy=False
        self._read_calls=0;self._read_bytes=0;self._write_bytes=0;self._records=0;self._creations=0;self._record_failure=None
        self._bank=shared.new_query_bank(normal_slots=16,cancellation_slots=0)
        self._directory=Path(directory)
        need(self._directory.name=="terminal_observations" and self._directory.parent.name=="job_"+str(job_id) and self._directory.is_absolute() and self._directory.resolve(strict=False)==self._directory)
        parent=self._directory.parent.lstat();need(stat.S_ISDIR(parent.st_mode) and stat.S_IMODE(parent.st_mode)==0o700 and parent.st_uid==os.geteuid())
        self.check();self._creations+=1;self._directory.mkdir(mode=0o700);self._chain=self._ancestor_chain()
        self.record("OBSERVER_BINDING.record",dict(version="stage12_b_terminal_observer_owner_v1",job_id=job_id,source_sha=source_sha,nonce=nonce,selection_sha256=selection_sha256,schedule=schedule,
            invocation_scope="FIXED_ORIGINAL_B_SUBMISSION_ANCHOR_NO_RESET",query_bank=dict(self._bank),maximum_record_count=self.MAX_RECORDS,maximum_record_bytes=self.MAX_RECORD_BYTES,
            maximum_read_calls=self.MAX_READ_CALLS,maximum_read_bytes=self.MAX_READ_BYTES,maximum_write_bytes=self.MAX_WRITE_BYTES,
            logical_buffer_quote="64KiB serialized record plus encoder/string copies,1KiB returned read block,hash/I/O scratch; no native-inclusive guarantee",no_job_or_scientific_acceptance=True))
    @property
    def end(self):return self._end
    @property
    def epoch_end(self):return self._epoch_end
    @property
    def entered(self):return self._entry
    @property
    def bank(self):return self._bank
    def _ancestor_chain(self):
        parents=(self._directory,*self._directory.parents);need(len(parents)<=64 and sum(len(os.fsencode(p)) for p in parents)<=16384,"B_OBSERVER_ANCESTOR_BOUND")
        rows=[]
        for p in reversed(parents):
            s=p.lstat();need(stat.S_ISDIR(s.st_mode),"B_OBSERVER_ANCESTOR");rows.append((str(p),s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid))
        return tuple(rows)
    def check(self):
        need(self._record_failure is None,"B_OBSERVER_WRITER_UNCERTAIN")
        need(time.monotonic_ns()<self._end and time.time_ns()<self._epoch_end,"B_OBSERVER_DEADLINE")
        if not self._busy:
            self._busy=True
            try:self._service()
            finally:self._busy=False
        need(time.monotonic_ns()<self._end and time.time_ns()<self._epoch_end,"B_OBSERVER_DEADLINE")
    def read(self,fd,amount):
        self.check();need(type(fd)is int and fd>=0 and type(amount)is int and 0<amount<=1024)
        need(self._read_calls<self.MAX_READ_CALLS,"B_OBSERVER_READ_CALL_LIMIT");self._read_calls+=1
        need(self._read_bytes+amount<=self.MAX_READ_BYTES,"B_OBSERVER_READ_BYTE_LIMIT")
        raw=os.read(fd,amount);self._read_bytes+=len(raw);self.check();return raw
    def record(self,name,value):
        try:return self._record_original(name,value)
        except BaseException as error:
            if self._record_failure is None:self._record_failure=dict(operation="RECORD",safe_name=name if type(name)is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}\.record",name) else "UNKNOWN",error_kind="OS_ERROR" if isinstance(error,OSError) else "GUARD_OR_UNKNOWN",observed_mono_ns=time.monotonic_ns(),original_end_mono_ns=self.end)
            raise
    def _record_original(self,name,value):
        self.check();need(self._ancestor_chain()==self._chain,"B_OBSERVER_ANCESTOR_CHANGED");need(type(name)is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}\.record",name),"B_OBSERVER_RECORD_NAME")
        raw=canonical(value);need(len(raw)<=self.MAX_RECORD_BYTES and self._write_bytes+len(raw)<=self.MAX_WRITE_BYTES,"B_OBSERVER_WRITE_LIMIT")
        need(self._records<self.MAX_RECORDS,"B_OBSERVER_RECORD_LIMIT");self._records+=1;self._creations+=1;self._write_bytes+=len(raw)
        path=self._directory/name;before_parent=self._directory.lstat();need(stat.S_ISDIR(before_parent.st_mode) and stat.S_IMODE(before_parent.st_mode)==0o700 and before_parent.st_uid==os.geteuid())
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            view=memoryview(raw)
            while view:self.check();written=os.write(fd,view);need(written>0);view=view[written:]
            os.fsync(fd);written_identity=ident(os.fstat(fd))
        finally:os.close(fd)
        parent_fd=os.open(self._directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent_fd)
        finally:os.close(parent_fd)
        self.check();info=path.lstat();need(ident(info)==written_identity and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW);digest=hashlib.sha256();count=0
        try:
            need(ident(os.fstat(fd))==written_identity)
            while count<info.st_size:
                block=self.read(fd,min(1024,info.st_size-count));need(bool(block));count+=len(block);digest.update(block)
            need(self.read(fd,1)==b"" and count==len(raw) and digest.hexdigest()==sha(raw) and ident(os.fstat(fd))==written_identity==ident(path.lstat()))
        finally:os.close(fd)
        after_parent=self._directory.lstat();need((before_parent.st_dev,before_parent.st_ino,before_parent.st_mode,before_parent.st_uid,before_parent.st_gid)==(after_parent.st_dev,after_parent.st_ino,after_parent.st_mode,after_parent.st_uid,after_parent.st_gid))
        need(self._ancestor_chain()==self._chain,"B_OBSERVER_ANCESTOR_CHANGED");self.check();return sha(raw)
    def snapshot(self):
        return dict(version="stage12_b_terminal_observer_owner_v1",entered_mono_ns=self.entered,end_mono_ns=self.end,end_epoch_ns=self.epoch_end,
            read_calls=self._read_calls,read_bytes=self._read_bytes,write_bytes=self._write_bytes,records=self._records,creations=self._creations,query_bank=dict(self._bank),
            child_processes_launched_by_owner=0,collection_Control_constructed=False,first_record_failure=self._record_failure,native_or_scientific_acceptance=False)

def derive_three_column_scheduler(*,source_query_record_ref,observer_binding_ref,shared_module_ref,source_dir,source_inventory,
                                  expected_job_id,expected_nonce,expected_source_sha,expected_selection_sha256,output,write):
    """Closed compatibility projection; never a fresh scheduler query or raw-command claim."""
    import base64
    shared=source_module(shared_module_ref,source_dir,source_inventory)
    query_raw=read_ref(source_query_record_ref,16384);query=json.loads(query_raw);need(canonical(query)==query_raw and query.get("version")==shared.QUERY_VERSION)
    bound_raw=read_ref(observer_binding_ref,65536);bound=json.loads(bound_raw);need(canonical(bound)==bound_raw and bound.get("version")=="stage12_b_terminal_observer_owner_v1")
    need(Path(source_query_record_ref["path"]).parent==Path(observer_binding_ref["path"]).parent and Path(observer_binding_ref["path"]).name=="OBSERVER_BINDING.record")
    need(bound.get("job_id")==expected_job_id and bound.get("nonce")==expected_nonce and bound.get("source_sha")==expected_source_sha and bound.get("selection_sha256")==expected_selection_sha256)
    need(type(query.get("actual_client_exit"))is int and query["actual_client_exit"]==0 and query.get("joined")is True and query.get("stdout_eof")is True and query.get("stderr_eof")is True and query.get("cleanup_uncertain")is False and query.get("first_safe_error")is None and query.get("signals")==[])
    need(query["entered_mono_ns"]>=bound["schedule"]["entry_mono_ns"] and query["completed_mono_ns"]<bound["schedule"]["deadline_mono_ns"])
    reservation=query["reservation"];need(type(reservation)is dict and reservation.get("version")==shared.BANK_VERSION and type(reservation.get("ordinal"))is int and 1<=reservation["ordinal"]<=16)
    need(reservation["entered_mono_ns"]==query["entered_mono_ns"] and reservation["entered_epoch_ns"]==query["entered_epoch_ns"])
    native_raw=base64.b64decode(query["stdout_b64"],validate=True);stderr=base64.b64decode(query["stderr_b64"],validate=True)
    need(len(native_raw)==query["stdout_bytes"]<=4096 and len(stderr)==query["stderr_bytes"]<=4096)
    parser=shared.QueryParser(expected_job_id,expected_nonce,60099,"footprint","general1");parser.feed(native_raw);facts=parser.finish(query["actual_client_exit"])
    need(facts["status"]=="AUTHORITATIVE_TERMINAL" and query["facts"]["status"]=="AUTHORITATIVE_TERMINAL")
    for key in ("version","job_id","nonce","native_query_start_epoch_ns","query_client_exit","rows","terminal","all_completed_zero","raw_sha256","workload_or_scientific_acceptance"):
        need(query["facts"][key]==facts[key],"B_SCHEDULER_DERIVATION_CHANGED")
    rows={row["job_id_raw"]:row for row in facts["rows"]};ids=[str(expected_job_id),str(expected_job_id)+".batch",str(expected_job_id)+".extern"]
    need(set(rows)==set(ids))
    projected="".join(job+"|"+rows[job]["reported_state"]+"|"+rows[job]["exit_code"]+"\n" for job in ids).encode("ascii")
    need(len(projected)<=1024)
    output=Path(output);need(output.name.endswith(".derived-scheduler-3col.record"))
    projected_ref=write(output,projected)
    if projected_ref is None:projected_ref=dict(path=str(output),sha256=sha(projected))
    need(projected_ref==dict(path=str(output),sha256=sha(projected)))
    provenance=dict(version="stage12_b_scheduler_three_column_projection_v1",source_query_record=source_query_record_ref,observer_binding=observer_binding_ref,actual_native_stdout_sha256=sha(native_raw),actual_native_stderr_sha256=sha(stderr),
        native_format_columns=["JobIDRaw","State","ExitCode","Start","End","UID","Account","Partition"],derived_format_columns=["JobIDRaw","State","ExitCode"],row_order=ids,
        source_kind="DETERMINISTIC_CLOSED_COLUMN_PROJECTION_NOT_COMMAND_STDOUT",genuine_new_query_invocations=0,derived_scheduler=projected_ref,
        source_query_start_epoch_ns=facts["native_query_start_epoch_ns"],source_query_completed_epoch_ns=query["completed_epoch_ns"],original_job_id=expected_job_id,
        original_source_git_sha=expected_source_sha,selection_sha256=expected_selection_sha256,terminal=facts["terminal"],all_completed_zero=facts["all_completed_zero"],
        no_new_authority_or_B_scientific_acceptance=True,no_17th_terminal_query=True)
    provenance_path=output.with_name(output.name+".provenance.record");write(provenance_path,canonical(provenance))
    return dict(derived_scheduler=projected_ref,provenance=dict(path=str(provenance_path),sha256=sha(canonical(provenance))),observed_epoch_ns=query["completed_epoch_ns"],terminal=facts["terminal"],state="DERIVED_COMPATIBILITY_INPUT_NOT_B_PASS",extra_query_invocations=0)

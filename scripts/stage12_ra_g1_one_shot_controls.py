"""Prospective task-only single-flight control polling; no workload authority."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import time

VERSION = "stage12_task_oneshot_controls_v1"
MAX_PROBES = 16
PROBE_NS = 15_000_000_000
SPACING_NS = 120_000_000_000
MAX_READ_CALLS = 4096
MAX_READ_BYTES = 1_048_576
MAX_CHECKS = 65_536
PROCESS_UNITS_PER_PROBE = 9
LABELS = ("ready", "incomplete", "provisional")
NAMES = ("TRANSPORT_READY.record", "PAIR_INCOMPLETE.record", "PAIR_PROVISIONAL_COMPLETE.record")
BODY_PRECHARGE = 3 * 65536
RECORD_PRECHARGE = 65536

class Stop(RuntimeError):
    def __init__(self, code):
        self.one_shot_code = code
        super().__init__(code)

def need(value, code):
    if not value:
        raise Stop(code)

def rows_for(plan, transport):
    parent = Path(plan["remote_pair"])
    need(parent.is_absolute() and str(parent) == plan["remote_pair"]
         and ".." not in parent.parts, "POLL_PATH")
    rows = [dict(label=label, path=str(parent/name), maximum=65536,
                 local_name=label+".original")
            for label,name in zip(LABELS,NAMES,strict=True)]
    need(all(len(r["path"]) <= 1024
             and re.fullmatch(r"[A-Za-z0-9_./-]+",r["path"]) for r in rows), "POLL_PATH")
    paths,extras,ancestors=transport.batch_paths(rows)
    need(not extras and len(ancestors)<=24, "POLL_PATH")
    return rows, ancestors

def next_start(previous_start):
    need(type(previous_start) is int and previous_start > 0, "POLL_CONFIG")
    return previous_start + SPACING_NS

def _phase(pair, overall, start):
    class ProbeControl(pair.Control):
        def __init__(self):
            super().__init__(start, overall.epoch_end, 15)
            self.end=min(self.end,overall.end)
            self.check_calls=0
        def check(self):
            need(self.check_calls < MAX_CHECKS, "PROBE_CHECK_LIMIT")
            self.check_calls+=1
            overall.check()
            pair.Control.check(self)
        def read(self, fd, amount):
            self.check()
            need(self.read_calls < MAX_READ_CALLS
                 and self.read_bytes+amount <= MAX_READ_BYTES, "PROBE_READ_LIMIT")
            self.read_calls+=1
            raw=overall.read(fd,amount)
            self.read_bytes+=len(raw)
            self.check()
            return raw
        def claim(self, amount, creation=False):
            self.check()
            overall.claim(amount,creation)
            self.write_bytes+=amount
            if creation:self.creations+=1
    return ProbeControl()

def _missing_result(error, rows, ancestors, pair, tc):
    """Accept ENOENT only after the actual complete named reader validates it."""
    need(type(error) is tc.Stop and error.args == ("RETENTION",), "PROBE_FAILED")
    d=getattr(error,"transport_diagnostic",None)
    need(type(d) is dict and d.get("code")=="RETENTION"
         and d.get("first_phase")=="BEFORE"
         and d.get("cleanup_uncertain") is False
         and d.get("remote_cleanup_status")=="JOINED_NATIVE_EXIT_ZERO", "PROBE_FAILED")
    p=d.get("pending_check")
    need(type(p) is dict and p.get("version")=="stage12_task_named_control_absence_v1"
         and p.get("child_exit")==0 and type(p.get("child_exit")) is int
         and p.get("observed_joined") is True
         and p.get("stdout_eof") is True and p.get("stderr_eof") is True
         and p.get("keep_stdin_open") is True, "PROBE_FAILED")
    pair.validate_transport_domain(d["domain_before"])
    pair.validate_transport_domain(d["domain_after"])
    need(d["domain_before"]==d["domain_after"], "PROBE_DOMAIN")
    before,after=d.get("metadata_before"),d.get("metadata_after")
    need(type(before) is list and type(after) is list
         and len(before)==len(after)==len(rows)+len(ancestors), "PROBE_METADATA")
    presence=d.get("presence")
    need(type(presence) is dict
         and presence.get("before_stat_exit")==presence.get("after_stat_exit")==1,
         "PROBE_METADATA")
    entries=presence.get("entries")
    need(type(entries) is list and len(entries)==len(before), "PROBE_METADATA")
    missing=[]; states=[]
    for i,row in enumerate(rows):
        e=entries[i]
        need(e.get("index")==i and e.get("label")==row["label"]
             and e.get("kind")=="CONTROL", "PROBE_METADATA")
        if before[i] is None:
            need(after[i] is None and e.get("before")==e.get("after")=="UNAVAILABLE",
                 "PROBE_METADATA")
            missing.append(row["label"])
            states.append(dict(label=row["label"],before="ABSENT_ENOENT",after="ABSENT_ENOENT"))
        else:
            need(type(before[i]) is list and len(before[i])==9
                 and before[i]==after[i]
                 and e.get("before")==e.get("after")=="PRESENT", "PROBE_METADATA")
            states.append(dict(label=row["label"],before="PRESENT",after="PRESENT"))
    need(missing and p.get("verified_missing_errno_labels")==missing, "PROBE_ABSENCE_UNVERIFIED")
    for i,path in enumerate(ancestors,start=len(rows)):
        need(type(before[i]) is list and len(before[i])==9
             and type(after[i]) is list and len(after[i])==9
             and before[i][:6]==after[i][:6]
             and entries[i].get("kind")=="ANCESTOR"
             and entries[i].get("before")==entries[i].get("after")=="PRESENT",
             "PROBE_METADATA")
    files=d.get("retained_files")
    need(type(files) is list, "PROBE_METADATA")
    by_label={r["label"]:r for r in files}
    need(len(by_label)==len(files)
         and set(by_label)==set(LABELS)-set(missing), "PROBE_METADATA")
    if files:
        evidence=dict(version="stage12_same_session_transfer_v2",
                      domain_before=d["domain_before"],domain_after=d["domain_after"],
                      ancestors=[dict(path=str(path),before=before[len(rows)+i],
                                      after=after[len(rows)+i]) for i,path in enumerate(ancestors)],
                      files=files,exit_code=0,observed_joined=True)
        pair.validate_transport_evidence(evidence)
    else:
        evidence=None
    return states,by_label,evidence,d

def _classify(states, by_label):
    need(not ({"incomplete","provisional"} & set(by_label)), "PROBE_TERMINAL_CONTROL")
    if "ready" in by_label:
        return "READY_ORIGINAL_AWAITING_CONTEXT_VALIDATION"
    need(all(r["before"]==r["after"]=="ABSENT_ENOENT" for r in states), "PROBE_FAILED")
    return "PENDING"

def probe(plan, output_root, overall, transport, pair, tc, record, charge,
          *, index=1, previous_ack=None, testing_argv=None, nonce=None):
    """One complete/closed probe. READY is still subject to the caller's full gate."""
    start=time.monotonic_ns(); epoch=time.time_ns()
    need(type(index) is int and 1<=index<=MAX_PROBES, "POLL_CONFIG")
    c=_phase(pair,overall,start); c.check()
    need(getattr(overall,"cleanup_uncertain",True) is False,"PROBE_CLEANUP_UNCERTAIN")
    rows,ancestors=rows_for(plan,transport)
    output_root=tc.absolute(str(output_root))
    local_chain=tc.ancestors(output_root,links=False)
    tc.private(output_root.lstat(),"DIR",os.geteuid())
    root_identity=tc.ident(output_root.lstat())[:5]
    c.check()
    need(c.end-time.monotonic_ns()>2_000_000_000, "PROBE_DEADLINE")
    # Permanent maximum liabilities: no refund for absent bodies or a failed read.
    c.claim(BODY_PRECHARGE+RECORD_PRECHARGE,True)
    c.claim(0,True)
    c.claim(0,True)  # directory plus conservative two-name durable result liability
    target=output_root/("probe-%02d"%index)
    tc.check_ancestors(local_chain)
    need(tc.ident(output_root.lstat())[:5]==root_identity,"POLL_PATH_CHANGED")
    target.mkdir(mode=0o700)
    tc.private(target.lstat(),"DIR",os.geteuid())
    tc.check_ancestors(local_chain)
    need(tc.ident(output_root.lstat())[:5]==root_identity,"POLL_PATH_CHANGED")
    charge("ONE_SHOT_CONTROL_PROBE_%02d_MAXIMUM"%index,PROCESS_UNITS_PER_PROBE)
    result=dict(version=VERSION,index=index,entry_mono_ns=start,entry_epoch_ns=epoch,
                deadline_mono_ns=c.end,window_end_epoch_ns=c.epoch_end,
                previous_probe_record_ack_mono_ns=previous_ack,
                status="FAILED",present_absent=None,actual_process=None,
                read_calls=0,read_bytes=0,cleanup_uncertain=True,
                native_or_scientific_acceptance=False)
    try:
        try:
            ev,_=transport.fetch_batch(rows,target,c,expected_uid=plan["source_uid"],
                expected_gid=plan["source_gid"],pending_labels=LABELS,
                keep_stdin_open=True,testing_argv=testing_argv,nonce=nonce)
        except BaseException as error:
            # Any incomplete parse, nonzero child, uncertainty or non-ENOENT error
            # propagates unchanged; only this completed absence proof is pending.
            original_diagnostic=getattr(error,"transport_diagnostic",None)
            if type(original_diagnostic) is dict:
                result["transport_diagnostic"]=original_diagnostic
                result["actual_process"]=original_diagnostic.get("pending_check")
            try:
                states,by_label,ev,d=_missing_result(error,rows,ancestors,pair,tc)
            except BaseException as classification_error:
                error.one_shot_predicate=getattr(classification_error,"one_shot_code","PROBE_CLASSIFICATION_FAILED")
                raise error
            result["actual_process"]=d["pending_check"]
            result["transport_diagnostic"]=d
        else:
            pair.validate_transport_evidence(ev)
            by_label={r["label"]:r for r in ev["files"]}
            need(len(by_label)==3 and set(by_label)==set(LABELS), "PROBE_METADATA")
            states=[dict(label=k,before="PRESENT",after="PRESENT") for k in LABELS]
            result["actual_process"]=dict(child_exit=ev["exit_code"],
                observed_joined=ev["observed_joined"],stdout_eof=True,stderr_eof=True)
        result["present_absent"]=states
        result["status"]=_classify(states,by_label)
        result["cleanup_uncertain"]=False
        result["transport_evidence"]=ev
        if "ready" in by_label:
            path=target/"ready.original"
            raw=pair.read_original(path,c,65536)
            need(hashlib.sha256(raw).hexdigest()==by_label["ready"]["sha256"],
                 "PROBE_READY_ORIGINAL")
            result["ready_sha256"]=by_label["ready"]["sha256"]
            result["ready_path"]=str(path)
        c.check()
    except BaseException as error:
        result["status"]="FAILED"
        result["safe_error"]=getattr(error,"one_shot_code",pair.safe_code(error))
        result["transport_diagnostic"]=getattr(error,"transport_diagnostic",
                                              result.get("transport_diagnostic"))
        result["read_calls"]=c.read_calls;result["read_bytes"]=c.read_bytes
        result["cleanup_uncertain"]=c.cleanup_uncertain or result["cleanup_uncertain"]
        result["result_timestamp_scope"]="BEFORE_RESULT_DURABILITY"
        result["observed_mono_ns"]=time.monotonic_ns()
        try:record("ONE_SHOT_PROBE_%02d.record"%index,result)
        except BaseException: setattr(error,"one_shot_retention","INCOMPLETE")
        raise
    result["read_calls"]=c.read_calls;result["read_bytes"]=c.read_bytes
    result["result_timestamp_scope"]="BEFORE_RESULT_DURABILITY"
    result["observed_mono_ns"]=time.monotonic_ns()
    need(len(json.dumps(result,sort_keys=True,separators=(",",":")).encode())<=65536,
         "PROBE_RECORD_LIMIT")
    record("ONE_SHOT_PROBE_%02d.record"%index,result)
    try:
        c.check()
    except BaseException as error:
        error.one_shot_stage="RESULT_ACKNOWLEDGEMENT"
        error.one_shot_probe_index=index
        error.one_shot_probe_deadline_mono_ns=c.end
        error.one_shot_record_acknowledged=False
        raise
    result["durable_record_ack_mono_ns"]=time.monotonic_ns()
    need(result["durable_record_ack_mono_ns"]<c.end, "PROBE_DEADLINE")
    return result

def poll(plan, output_root, overall, transport, pair, tc, charge, record):
    """Native policy: never overlap, retry a failure, or reset the owner deadline."""
    results=[];last_start=last_ack=None
    for index in range(1,MAX_PROBES+1):
        if last_start is not None:
            target=next_start(last_ack)
            while time.monotonic_ns()<target:
                overall.check()  # existing owner services submission streams here
                time.sleep(min(.05,max(0,(target-time.monotonic_ns())/1e9)))
        overall.check()
        result=probe(plan,output_root,overall,transport,pair,tc,record,charge,
                     index=index,previous_ack=last_ack)
        if last_start is not None:
            need(result["entry_mono_ns"]-last_start>=SPACING_NS, "POLL_SPACING")
        last_start=result["entry_mono_ns"];last_ack=result["durable_record_ack_mono_ns"]
        results.append(dict(index=index,status=result["status"],entry_mono_ns=last_start,
                            durable_record_ack_mono_ns=last_ack,
                            present_absent=result["present_absent"],
                            read_calls=result["read_calls"],read_bytes=result["read_bytes"]))
        if result["status"]=="READY_ORIGINAL_AWAITING_CONTEXT_VALIDATION":
            return dict(version=VERSION,status=result["status"],probe_count=index,
                        minimum_spacing_anchor="PREVIOUS_DURABLE_RECORD_ACK_PLUS_120_SECONDS",
                        probes=results,ready_sha256=result["ready_sha256"],
                        ready_path=result["ready_path"],native_or_scientific_acceptance=False)
        need(result["status"]=="PENDING", "PROBE_FAILED")
    raise Stop("POLL_EXHAUSTED")

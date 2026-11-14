"""Versioned ordinary-submit facts and bounded authoritative terminal observation.

This operating-only successor issues no workload authority and never interprets
submission-client exit as job success. Historical --wait readers stay separate.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import re
import selectors
import shlex
import subprocess
import time

VERSION = "stage12_nonwaiting_submission_terminal_v1"
SUBMIT_VERSION = "stage12_ordinary_submission_client_v1"
QUERY_VERSION = "stage12_authoritative_terminal_query_v1"
SUBMIT_MARKER = b"S12SUB3|BEGIN|"
QUERY_PROCESS_UNITS = 4
MAX_QUERIES = 16
QUERY_SECONDS = 15
QUERY_READ_ATTEMPTS = 96
QUERY_STREAM_BYTES = 4096
QUERY_RECORD_BYTES = 16384
QUERY_CLEANUP_NS = 250000000
QUERY_SPACING_NS = 120000000000
# Prospective selected-B evidence contract. It changes neither the wire parser
# nor any historical two-confirmation helper/artifact.
FIRST_TERMINAL_POLICY = "stage12_first_complete_authoritative_terminal_v1"
FIRST_TERMINAL_SCHEDULE = "stage12_b_first_complete_terminal_schedule_v1"
QUALIFYING_TERMINAL_ROLE = "QUALIFYING_AUTHORITATIVE_TERMINAL_OBSERVATION"
TERMINAL = frozenset(("COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL",
    "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE", "PREEMPTED", "REVOKED"))
ACTIVE = frozenset(("PENDING", "RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED",
    "RESIZING", "REQUEUED", "REQUEUE_FED", "REQUEUE_HOLD", "SPECIAL_EXIT", "STAGE_OUT"))
SAFE = frozenset(("SUBMIT_FLAGS", "SUBMIT_FRAME", "SUBMIT_EXIT", "SUBMIT_INCOMPLETE", "SUBMIT_CLUSTER",
    "QUERY_FRAME", "QUERY_IDENTITY", "QUERY_MEMBERSHIP", "QUERY_TIME", "QUERY_STATE",
    "QUERY_EXIT", "QUERY_OUTPUT_LIMIT", "QUERY_READ_LIMIT", "QUERY_DEADLINE",
    "QUERY_CLEANUP_UNCERTAIN", "QUERY_IO", "QUERY_LIMIT", "QUERY_SPACING",
    "QUERY_CONFIG", "NONTERMINAL", "JOB_FAILED", "UNCLASSIFIED"))

class Stop(RuntimeError):
    pass

def need(value, code):
    if not value:
        raise Stop(code)

def safe_code(error):
    if type(error) is Stop and len(error.args) == 1 and error.args[0] in SAFE:
        return error.args[0]
    return "QUERY_IO" if isinstance(error, OSError) else "UNCLASSIFIED"

def _nonce(value):
    need(type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value), "QUERY_CONFIG")

def ordinary_sbatch_argv(argv):
    need(type(argv) is list and len(argv) >= 3 and argv[0] in ("sbatch", "/usr/bin/sbatch")
         and all(type(s) is str and 0 < len(s.encode()) <= 8192
                 and not any(c in s for c in ("\0", "\n", "\r")) for s in argv), "SUBMIT_FLAGS")
    need(argv.count("--parsable") == 1
         and not any(s == "--wait" or s.startswith("--wait=")
                     or (s.startswith("-") and not s.startswith("--"))
                     or s.startswith("--parsable=") for s in argv), "SUBMIT_FLAGS")
    valueless = frozenset(("--parsable", "--no-requeue"))
    valued = frozenset(("--chdir", "--comment", "--output", "--error", "--job-name",
        "--account", "--partition", "--nodes", "--ntasks", "--cpus-per-task", "--mem", "--time"))
    need(not argv[-1].startswith("-") and all(
        token in valueless or ("=" in token and token.split("=",1)[0] in valued
                                and bool(token.split("=",1)[1]))
        for token in argv[1:-1]), "SUBMIT_FLAGS")
    return ["env", "-u", "SBATCH_WAIT"] + list(argv)

def submit_builder(prefix, sbatch_argv, nonce, deadline_epoch_ns, remaining_seconds):
    _nonce(nonce)
    need(type(prefix) is str and "\0" not in prefix and len(prefix.encode()) <= 65536,
         "SUBMIT_FRAME")
    need(type(deadline_epoch_ns) is int and deadline_epoch_ns > 0
         and type(remaining_seconds) is int and 0 < remaining_seconds <= 86400, "QUERY_CONFIG")
    argv = ordinary_sbatch_argv(sbatch_argv)
    # The source entry/SECONDS origin is never reset after the canonical prelude.
    # exec preserves the actual short-lived submission client's exit through SSH.
    return ("set -euo pipefail\numask 077\nexport LC_ALL=C TZ=UTC\n" + prefix + "\n"
        + "(( SECONDS < " + str(remaining_seconds) + " )) || exit 2\n"
        + 'selected_now=${EPOCHREALTIME-}\n[[ "$selected_now" =~ ^([0-9]+)\\.([0-9]{6})$ ]] || exit 2\n'
        + 'selected_now_ns=$((10#${BASH_REMATCH[1]}*1000000000+10#${BASH_REMATCH[2]}*1000))\n'
        + "(( selected_now_ns < " + str(deadline_epoch_ns) + " )) || exit 2\n"
        + "printf 'S12SUB3|BEGIN|%s|%s|%s|%s\\n' " + shlex.quote(nonce)
        + " " + str(deadline_epoch_ns) + " " + str(remaining_seconds) + ' "$BASH_VERSION"\n'
        + "exec " + shlex.join(argv) + "\n")

def submission_argv(prefix, sbatch_argv, nonce, deadline_epoch_ns, remaining_seconds):
    body = submit_builder(prefix, sbatch_argv, nonce, deadline_epoch_ns, remaining_seconds)
    return ["/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", "goethe",
            "exec bash -c " + shlex.quote(body)]

class SubmitParser:
    def __init__(self, nonce, deadline_epoch_ns, remaining_seconds, *, expected_prelude=b"", maximum=65536):
        _nonce(nonce)
        need(type(expected_prelude) is bytes and len(expected_prelude) <= 32768
             and type(maximum) is int and 32768 < maximum <= 65536, "SUBMIT_FRAME")
        self.nonce = nonce; self.deadline = deadline_epoch_ns; self.seconds = remaining_seconds
        self.expected_prelude = expected_prelude; self.maximum = maximum
        self.raw = bytearray(); self.buffer = bytearray(); self.prelude = bytearray()
        self.begun = False; self.submitted = None; self.bash_version = None
    def feed(self, raw):
        need(type(raw) is bytes and len(self.raw) + len(raw) <= self.maximum, "SUBMIT_FRAME")
        self.raw.extend(raw); self.buffer.extend(raw)
        while b"\n" in self.buffer:
            index = self.buffer.index(10)
            need(index <= 32768, "SUBMIT_FRAME")
            line = bytes(self.buffer[:index]); del self.buffer[:index+1]
            if not self.begun:
                if not line.startswith(b"S12SUB3|"):
                    self.prelude.extend(line+b"\n")
                    need(len(self.prelude) <= 32768, "SUBMIT_FRAME"); continue
                try: fields = line.decode("ascii").split("|")
                except UnicodeError: raise Stop("SUBMIT_FRAME") from None
                need(len(fields) == 6 and fields[:3] == ["S12SUB3", "BEGIN", self.nonce]
                     and fields[3:5] == [str(self.deadline), str(self.seconds)]
                     and bytes(self.prelude) == self.expected_prelude, "SUBMIT_FRAME")
                match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.[0-9]+(?:\([0-9]+\))?[-A-Za-z0-9_.]*", fields[5])
                need(match is not None and (int(match[1]), int(match[2])) >= (4,1), "SUBMIT_FRAME")
                self.bash_version = fields[5]; self.begun = True
            else:
                need(self.submitted is None and len(line) <= 64, "SUBMIT_FRAME")
                try: value = line.decode("ascii")
                except UnicodeError: raise Stop("SUBMIT_FRAME") from None
                need(re.fullmatch(r"[1-9][0-9]{0,19}(;[A-Za-z0-9_.-]{1,32})?", value), "SUBMIT_FRAME")
                self.submitted = dict(job_id=int(value.split(";")[0]), parsable_id=value, cluster=value.split(";",1)[1] if ";" in value else None)
    def finish(self, submit_client_exit):
        need(type(submit_client_exit) is int and submit_client_exit == 0, "SUBMIT_EXIT")
        need(not self.buffer and self.begun and self.submitted is not None, "SUBMIT_INCOMPLETE")
        need(self.submitted["cluster"] is None, "SUBMIT_CLUSTER")
        return dict(version=SUBMIT_VERSION, status="GENUINE_SUBMIT_CLIENT_FACTS_NOT_JOB_SUCCESS",
            nonce=self.nonce, deadline_epoch_ns=self.deadline, remaining_seconds=self.seconds,
            bash_version=self.bash_version, submission=self.submitted,
            submit_client_exit=submit_client_exit, raw_sha256=hashlib.sha256(self.raw).hexdigest(),
            job_success=False, workload_or_scientific_acceptance=False)

def query_argv(job_id, nonce, *, host="goethe"):
    _nonce(nonce)
    need(host == "goethe" and type(job_id) is int and 0 < job_id < 10**20, "QUERY_CONFIG")
    body = ("set -euo pipefail\nexport LC_ALL=C TZ=UTC\n"
        + "printf 'S12TERM1|BEGIN|%s|%s|%s\\n' " + shlex.quote(nonce) + " " + str(job_id)
        + ' "$EPOCHREALTIME"\n'
        + "exec timeout --signal=TERM --kill-after=0.2s 10s sacct --parsable2 --noheader --jobs "
        + str(job_id) + " --format=JobIDRaw,State%40,ExitCode,Start,End,UID,Account,Partition\n")
    return ["/usr/bin/ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host,
            "exec bash -c " + shlex.quote(body)]

def _timestamp(value, *, optional):
    if optional and value in ("Unknown", "N/A", "None", ""):
        return None
    need(type(value) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}", value), "QUERY_TIME")
    try: parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError: raise Stop("QUERY_TIME") from None
    return int(parsed.timestamp()) * 1000000000

class QueryParser:
    def __init__(self, job_id, nonce, uid, account="footprint", partition="general1"):
        _nonce(nonce)
        need(type(job_id) is int and 0 < job_id < 10**20 and type(uid) is int and uid > 0
             and account == "footprint" and partition == "general1", "QUERY_CONFIG")
        self.job_id = job_id; self.nonce = nonce; self.uid = uid
        self.account = account; self.partition = partition; self.raw = bytearray()
    def feed(self, raw):
        need(type(raw) is bytes and len(self.raw)+len(raw) <= QUERY_STREAM_BYTES, "QUERY_OUTPUT_LIMIT")
        self.raw.extend(raw)
    def finish(self, query_client_exit):
        need(type(query_client_exit) is int and query_client_exit == 0, "QUERY_EXIT")
        raw = bytes(self.raw)
        need(raw.endswith(b"\n") and b"\0" not in raw and b"\r" not in raw, "QUERY_FRAME")
        try: lines = raw.decode("ascii").splitlines()
        except UnicodeError: raise Stop("QUERY_FRAME") from None
        need(1 <= len(lines) <= 4, "QUERY_FRAME")
        frame = lines[0].split("|")
        need(len(frame) == 5 and frame[:4] == ["S12TERM1", "BEGIN", self.nonce, str(self.job_id)]
             and re.fullmatch(r"[0-9]{10,20}\.[0-9]{6}", frame[4]), "QUERY_FRAME")
        seconds, micros = frame[4].split("."); observed = int(seconds)*1000000000+int(micros)*1000
        job = str(self.job_id); expected = {job, job+".batch", job+".extern"}; rows=[]
        for line in lines[1:]:
            p=line.split("|")
            need(len(p) == 8 and p[0] in expected and all(r["job_id_raw"] != p[0] for r in rows), "QUERY_MEMBERSHIP")
            state = p[1]; match = re.fullmatch(r"CANCELLED by ([0-9]{1,20})", state)
            canonical = "CANCELLED" if match else state
            need(canonical in ACTIVE|TERMINAL, "QUERY_STATE")
            need(re.fullmatch(r"[0-9]{1,3}:[0-9]{1,3}", p[2]), "QUERY_FRAME")
            if p[0] == job:
                need(p[5:] == [str(self.uid), self.account, self.partition], "QUERY_IDENTITY")
            else:
                need(p[5] in ("", str(self.uid)) and p[6] in ("", self.account)
                     and p[7] in ("", self.partition), "QUERY_IDENTITY")
            start = _timestamp(p[3], optional=canonical != "COMPLETED")
            end = _timestamp(p[4], optional=canonical != "COMPLETED")
            need(start is None or end is None or start <= end, "QUERY_TIME")
            rows.append(dict(job_id_raw=p[0], state=canonical, reported_state=state, exit_code=p[2],
                start=p[3], end=p[4], start_epoch_ns=start, end_epoch_ns=end,
                uid=p[5], account=p[6], partition=p[7]))
        top = [r for r in rows if r["job_id_raw"] == job]
        need(not rows or len(top) == 1, "QUERY_IDENTITY")
        if not top or {r["job_id_raw"] for r in rows} != expected:
            status = "ACCOUNTING_PENDING"
        elif any(r["state"] not in TERMINAL for r in rows):
            status = "NONTERMINAL"
        else:
            status = "AUTHORITATIVE_TERMINAL"
        return dict(version=QUERY_VERSION, status=status, job_id=self.job_id, nonce=self.nonce,
            native_query_start_epoch_ns=observed, observed_epoch_ns=time.time_ns(),
            observation_clock_scope="LOCAL_CONTROLLER_AFTER_GENUINE_QUERY_CLIENT_EXIT", query_client_exit=query_client_exit, rows=rows,
            terminal=top[0] if top and status=="AUTHORITATIVE_TERMINAL" else None,
            all_completed_zero=status=="AUTHORITATIVE_TERMINAL" and all(r["state"]=="COMPLETED" and r["exit_code"]=="0:0" for r in rows),
            raw_sha256=hashlib.sha256(raw).hexdigest(), workload_or_scientific_acceptance=False)


def validate_first_terminal_original(op, bound, *, job_id, nonce, source_sha,
                                     selection_sha256, uid):
    """Replay one complete selected query original, independently of its number.

    Callers retain/read the immutable operation bytes and bind their full hash.
    This validator establishes its semantic role only; driver closure and
    scientific acceptance are separate requirements.
    """
    operation_keys = frozenset(('actual_client_exit', 'cleanup_deadline_mono_ns',
        'cleanup_entry_mono_ns', 'cleanup_uncertain', 'completed_epoch_ns',
        'completed_mono_ns', 'deadline_mono_ns', 'entered_epoch_ns',
        'entered_mono_ns', 'facts', 'first_safe_error', 'joined', 'local_pid',
        'observed_join_mono_ns', 'operation', 'persisted_timestamp_scope',
        'read_calls', 'remote_endpoint_termination', 'reservation', 'signals',
        'spawn_entered_mono_ns', 'spawn_returned_mono_ns', 'stderr_b64',
        'stderr_bytes', 'stderr_eof', 'stderr_truncated', 'stdout_b64',
        'stdout_bytes', 'stdout_eof', 'stdout_truncated', 'version',
        'workload_or_scientific_acceptance'))
    owner_keys = frozenset(('invocation_scope', 'job_id', 'logical_buffer_quote',
        'maximum_read_bytes', 'maximum_read_calls', 'maximum_record_bytes',
        'maximum_record_count', 'maximum_write_bytes', 'no_job_or_scientific_acceptance',
        'nonce', 'query_bank', 'schedule', 'selection_sha256', 'source_sha',
        'version', 'terminal_observation_policy', 'qualifying_operation_role'))
    need(type(op) is dict and set(op) == operation_keys
         and type(bound) is dict and set(bound) == owner_keys, "QUERY_CONFIG")
    need(bound['version'] == 'stage12_b_terminal_observer_owner_v2'
         and bound['terminal_observation_policy'] == FIRST_TERMINAL_POLICY
         and bound['qualifying_operation_role'] == QUALIFYING_TERMINAL_ROLE
         and bound['job_id'] == job_id and bound['nonce'] == nonce
         and bound['source_sha'] == source_sha
         and bound['selection_sha256'] == selection_sha256
         and bound['invocation_scope'] == 'FIXED_ORIGINAL_B_SUBMISSION_ANCHOR_NO_RESET'
         and bound['no_job_or_scientific_acceptance'] is True
         and bound['query_bank'] == new_query_bank(normal_slots=16, cancellation_slots=0),
         "QUERY_IDENTITY")
    schedule = bound['schedule']
    schedule_keys = frozenset(('version', 'anchor', 'entry_mono_ns', 'entry_epoch_ns',
        'deadline_mono_ns', 'deadline_epoch_ns', 'absolute_window_end_epoch_ns',
        'offset_seconds', 'maximum_observations', 'query_seconds', 'query_process_units',
        'maximum_query_process_units', 'early_terminal_rule',
        'last_selected_query_finish_offset_seconds', 'finalization_reserve_seconds',
        'followon_and_review_reserved_seconds', 'queue_and_full_scheduler_risk',
        'required_remaining_seconds',
        'native_processing_seconds', 'native_scheduler_seconds',
        'online_handoff_watch_seconds', 'terminal_observation_policy',
        'qualifying_observation_role', 'fixed_confirmation_wait'))
    need(type(schedule) is dict and set(schedule) == schedule_keys
         and schedule.get('version') == FIRST_TERMINAL_SCHEDULE
         and schedule.get('terminal_observation_policy') == FIRST_TERMINAL_POLICY
         and schedule.get('qualifying_observation_role') == QUALIFYING_TERMINAL_ROLE
         and schedule.get('fixed_confirmation_wait') is False
         and 'final_authoritative_slots' not in schedule
         and schedule['anchor'] == 'ORIGINAL_B_SUBMISSION_ENTRY_NOT_RESET'
         and schedule['offset_seconds'] == list(range(0, 7801, 600)) + [8260, 8380]
         and schedule['native_scheduler_seconds'] == 8400
         and schedule['native_processing_seconds'] == 8160
         and schedule['online_handoff_watch_seconds'] == 8400
         and schedule['maximum_observations'] == 16 and schedule['query_seconds'] == 15
         and schedule['query_process_units'] == 4 and schedule['maximum_query_process_units'] == 64
         and schedule['followon_and_review_reserved_seconds'] == 2820
         and schedule['required_remaining_seconds'] == 11220
         and schedule['deadline_mono_ns'] - schedule['entry_mono_ns'] == 8400 * 10**9
         and schedule['deadline_epoch_ns'] - schedule['entry_epoch_ns'] == 8400 * 10**9,
         "QUERY_CONFIG")
    need(op['version'] == QUERY_VERSION
         and type(op['operation']) is str
         and re.fullmatch(r'TERMINAL_QUERY_(?:0[1-9]|1[0-6])', op['operation'])
         and type(op['actual_client_exit']) is int and op['actual_client_exit'] == 0
         and op['joined'] is True and op['stdout_eof'] is True and op['stderr_eof'] is True
         and op['stdout_truncated'] is False and op['stderr_truncated'] is False
         and op['cleanup_uncertain'] is False and op['first_safe_error'] is None
         and op['signals'] == [] and op['workload_or_scientific_acceptance'] is False
         and op['persisted_timestamp_scope'] == 'BEFORE_QUERY_RECORD_FSYNC'
         and op['remote_endpoint_termination'] == 'REPORTED_COMMAND_EXIT', "QUERY_EXIT")
    for key in ('entered_mono_ns', 'completed_mono_ns', 'deadline_mono_ns',
                'spawn_entered_mono_ns', 'spawn_returned_mono_ns', 'observed_join_mono_ns',
                'cleanup_entry_mono_ns', 'cleanup_deadline_mono_ns', 'entered_epoch_ns',
                'completed_epoch_ns', 'read_calls', 'stdout_bytes', 'stderr_bytes'):
        need(type(op[key]) is int and op[key] >= 0, 'QUERY_TIME')
    need(schedule['entry_mono_ns'] <= op['entered_mono_ns'] <= op['spawn_entered_mono_ns']
         <= op['spawn_returned_mono_ns'] <= op['cleanup_entry_mono_ns']
         <= op['observed_join_mono_ns'] <= op['completed_mono_ns']
         <= op['cleanup_deadline_mono_ns'] <= op['deadline_mono_ns']
         and op['completed_mono_ns'] < schedule['deadline_mono_ns']
         and 0 < op['deadline_mono_ns'] - op['entered_mono_ns'] <= 15 * 10**9
         and schedule['entry_epoch_ns'] <= op['entered_epoch_ns'] <= op['completed_epoch_ns']
         < schedule['deadline_epoch_ns']
         and op['read_calls'] <= QUERY_READ_ATTEMPTS, 'QUERY_TIME')
    reservation = op['reservation']
    need(type(reservation) is dict and set(reservation) == {
        'version', 'entered_mono_ns', 'entered_epoch_ns', 'kind', 'ordinal'}
        and reservation['version'] == BANK_VERSION and reservation['kind'] == 'NORMAL'
        and type(reservation['ordinal']) is int and 1 <= reservation['ordinal'] <= 16
        and reservation['entered_mono_ns'] == op['entered_mono_ns']
        and reservation['entered_epoch_ns'] == op['entered_epoch_ns'], 'QUERY_CONFIG')
    need(int(op['operation'][-2:]) == reservation['ordinal'], 'QUERY_CONFIG')
    try:
        raw = base64.b64decode(op['stdout_b64'], validate=True)
        stderr = base64.b64decode(op['stderr_b64'], validate=True)
    except (ValueError, TypeError):
        raise Stop('QUERY_FRAME') from None
    need(len(raw) == op['stdout_bytes'] <= QUERY_STREAM_BYTES
         and len(stderr) == op['stderr_bytes'] <= QUERY_STREAM_BYTES, 'QUERY_OUTPUT_LIMIT')
    parser = QueryParser(job_id, nonce, uid)
    parser.feed(raw)
    facts = parser.finish(op['actual_client_exit'])
    need(facts['status'] == 'AUTHORITATIVE_TERMINAL' and type(op['facts']) is dict,
         'NONTERMINAL')
    for key in ('version', 'status', 'job_id', 'nonce', 'native_query_start_epoch_ns',
                'observation_clock_scope', 'query_client_exit', 'rows', 'terminal',
                'all_completed_zero', 'raw_sha256', 'workload_or_scientific_acceptance'):
        need(op['facts'].get(key) == facts[key], 'QUERY_FRAME')
    need(op['facts']['query_entered_mono_ns'] == op['entered_mono_ns']
         and op['entered_mono_ns'] <= op['facts']['query_completed_mono_ns']
         <= op['cleanup_entry_mono_ns']
         and op['entered_epoch_ns'] <= op['facts']['observed_epoch_ns']
         <= op['completed_epoch_ns'], 'QUERY_TIME')
    return dict(semantic_role=QUALIFYING_TERMINAL_ROLE, policy=FIRST_TERMINAL_POLICY,
        operation=op['operation'], facts=op['facts'], driver_closure='SEPARATELY_REQUIRED',
        scientific_acceptance=False)

BANK_VERSION = "stage12_selected_terminal_query_bank_v1"
BANK_KEYS = frozenset(("version", "maximum", "normal_slots", "cancellation_slots",
    "used", "normal_used", "cancellation_used", "last_started_mono_ns"))

def new_query_bank(*, normal_slots=13, cancellation_slots=3):
    need(type(normal_slots) is int and type(cancellation_slots) is int
         and (normal_slots, cancellation_slots) in ((13,3),(16,0)), "QUERY_CONFIG")
    return dict(version=BANK_VERSION, maximum=16, normal_slots=normal_slots,
        cancellation_slots=cancellation_slots, used=0, normal_used=0,
        cancellation_used=0, last_started_mono_ns=None)

def reserve_query_start(owner, bank, *, kind="NORMAL"):
    need(type(bank) is dict and set(bank)==BANK_KEYS and type(bank["version"]) is str
         and bank["version"]==BANK_VERSION and type(bank["maximum"]) is int
         and bank["maximum"]==16 and kind in ("NORMAL","CANCEL"), "QUERY_CONFIG")
    for key in ("normal_slots","cancellation_slots","used","normal_used","cancellation_used"):
        need(type(bank[key]) is int and 0 <= bank[key] <= 16, "QUERY_CONFIG")
    need((bank["normal_slots"],bank["cancellation_slots"]) in ((13,3),(16,0))
         and bank["used"]==bank["normal_used"]+bank["cancellation_used"], "QUERY_CONFIG")
    need(bank["normal_used"]<=bank["normal_slots"] and bank["cancellation_used"]<=bank["cancellation_slots"],"QUERY_CONFIG")
    last=bank["last_started_mono_ns"]
    need((bank["used"]==0 and last is None) or (bank["used"]>0 and type(last) is int and last>0),"QUERY_CONFIG")
    key="normal_used" if kind=="NORMAL" else "cancellation_used"
    limit=bank["normal_slots"] if kind=="NORMAL" else bank["cancellation_slots"]
    owner.check();need(bank["used"]<16 and bank[key]<limit,"QUERY_LIMIT")
    if last is not None:
        due=last+QUERY_SPACING_NS
        while time.monotonic_ns()<due:
            owner.check();time.sleep(min(.05,max(0,(due-time.monotonic_ns())/1000000000)))
    owner.check();entered=time.monotonic_ns();epoch=time.time_ns()
    need(owner.end-entered>QUERY_CLEANUP_NS and owner.epoch_end-epoch>QUERY_CLEANUP_NS,"QUERY_DEADLINE")
    need(last is None or entered-last>=QUERY_SPACING_NS,"QUERY_SPACING")
    bank["used"]+=1;bank[key]+=1;bank["last_started_mono_ns"]=entered
    return dict(entered_mono_ns=entered,entered_epoch_ns=epoch,kind=kind,
                ordinal=bank["used"],version=BANK_VERSION)

def run_query(argv, parser, owner, record, label, charge, *, bank=None, kind="NORMAL"):
    """One bounded real child; record embeds private bounded raw framing/stderr."""
    need(type(label) is str and re.fullmatch(r"TERMINAL_QUERY_[0-9]{2}",label), "QUERY_CONFIG")
    reservation=reserve_query_start(owner,bank,kind=kind) if bank is not None else None
    entered=time.monotonic_ns() if reservation is None else reservation["entered_mono_ns"]
    entered_epoch=time.time_ns() if reservation is None else reservation["entered_epoch_ns"]
    owner.check()
    end=min(entered+QUERY_SECONDS*1000000000,owner.end,
            entered+max(0,owner.epoch_end-entered_epoch))
    need(end-entered>QUERY_CLEANUP_NS,"QUERY_DEADLINE")
    charge(label,QUERY_PROCESS_UNITS)
    child=None;selector=None;outs={"stdout":bytearray(),"stderr":bytearray()}
    eof=set();reads=0;primary=None;cleanup=False;joined=False;exit_code=None;signals=[];facts=None
    spawn_entered=spawn_returned=joined_mono=None
    try:
        owner.check()
        need(time.monotonic_ns()<end-QUERY_CLEANUP_NS
             and time.time_ns()<owner.epoch_end,"QUERY_DEADLINE")
        spawn_entered=time.monotonic_ns()
        child=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        spawn_returned=time.monotonic_ns()
        selector=selectors.DefaultSelector()
        for name,stream in (("stdout",child.stdout),("stderr",child.stderr)):
            os.set_blocking(stream.fileno(),False);selector.register(stream,selectors.EVENT_READ,name)
        while len(eof)<2 or child.poll() is None:
            owner.check();need(time.monotonic_ns()<end-QUERY_CLEANUP_NS,"QUERY_DEADLINE")
            for key,_ in selector.select(.05):
                need(time.monotonic_ns()<end-QUERY_CLEANUP_NS,"QUERY_DEADLINE")
                need(reads<QUERY_READ_ATTEMPTS,"QUERY_READ_LIMIT");reads+=1
                remaining=QUERY_STREAM_BYTES+1-len(outs[key.data]);need(remaining>0,"QUERY_OUTPUT_LIMIT")
                try: raw=owner.read(key.fileobj.fileno(),min(1024,remaining))
                except BlockingIOError: continue
                if not raw:selector.unregister(key.fileobj);eof.add(key.data)
                else:
                    outs[key.data].extend(raw)
                    need(len(outs[key.data])<=QUERY_STREAM_BYTES,"QUERY_OUTPUT_LIMIT")
        exit_code=child.wait(timeout=0);joined=True;joined_mono=time.monotonic_ns()
        parser.feed(bytes(outs["stdout"]));facts=parser.finish(exit_code)
        facts = dict(facts, query_entered_mono_ns=entered, query_completed_mono_ns=time.monotonic_ns())
        owner.check()
    except BaseException as error:primary=error
    finally:
        cleanup_entry=time.monotonic_ns();cleanup_end=min(end,cleanup_entry+QUERY_CLEANUP_NS)
        if child is not None and child.poll() is None:
            try:
                child.terminate();signals.append("TERM")
                half=min(cleanup_end,time.monotonic_ns()+QUERY_CLEANUP_NS//2)
                while child.poll() is None and time.monotonic_ns()<half:time.sleep(.005)
                if child.poll() is None:child.kill();signals.append("KILL")
                while child.poll() is None and time.monotonic_ns()<cleanup_end:time.sleep(.005)
            except BaseException:cleanup=True
        if child is not None and child.poll() is not None:
            try:exit_code=child.wait(timeout=0);joined=True;joined_mono=time.monotonic_ns()
            except BaseException:cleanup=True
        elif child is not None:cleanup=True
        if selector is not None:
            try:selector.close()
            except BaseException:cleanup=True
        if child is not None:
            for stream in (child.stdout,child.stderr):
                if stream is not None:
                    try:stream.close()
                    except BaseException:cleanup=True
        completed=time.monotonic_ns()
        if completed>cleanup_end or completed>=owner.end or time.time_ns()>=owner.epoch_end:cleanup=True
    value=dict(version=QUERY_VERSION,operation=label,entered_mono_ns=entered,entered_epoch_ns=entered_epoch,
        completed_mono_ns=completed,completed_epoch_ns=time.time_ns(),deadline_mono_ns=end,
        local_pid=None if child is None else child.pid,actual_client_exit=exit_code,joined=joined,
        reservation=reservation,spawn_entered_mono_ns=spawn_entered,spawn_returned_mono_ns=spawn_returned,
        observed_join_mono_ns=joined_mono,persisted_timestamp_scope="BEFORE_QUERY_RECORD_FSYNC",
        stdout_eof="stdout" in eof,stderr_eof="stderr" in eof,read_calls=reads,
        stdout_bytes=len(outs["stdout"]),stderr_bytes=len(outs["stderr"]),
        stdout_b64=base64.b64encode(outs["stdout"]).decode("ascii"),stderr_b64=base64.b64encode(outs["stderr"]).decode("ascii"),
        stdout_truncated=len(outs["stdout"])>QUERY_STREAM_BYTES,stderr_truncated=len(outs["stderr"])>QUERY_STREAM_BYTES,
        first_safe_error=None if primary is None else safe_code(primary),cleanup_entry_mono_ns=cleanup_entry,
        cleanup_deadline_mono_ns=cleanup_end,cleanup_uncertain=cleanup,signals=signals,
        remote_endpoint_termination="REPORTED_COMMAND_EXIT" if joined and len(eof)==2 and not cleanup and not signals else "UNKNOWN",
        facts=facts,workload_or_scientific_acceptance=False)
    # Fixed stream/row bounds establish this before the canonical copy is made.
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)+"\n").encode("utf-8")
    need(len(encoded) <= QUERY_RECORD_BYTES, "QUERY_OUTPUT_LIMIT")
    if primary is None and (not joined or len(eof)!=2 or cleanup):
        primary = Stop("QUERY_CLEANUP_UNCERTAIN")
    if primary is not None:
        try: primary.terminal_query_diagnostic = value
        except BaseException: pass
    try: record(label+".record",value)
    except BaseException as persistence_error:
        if primary is None:
            try:
                persistence_error.terminal_query_diagnostic = value
                persistence_error.query_persistence_uncertain = True
            except BaseException: pass
            raise
        try: primary.query_persistence_uncertain = True
        except BaseException: pass
    post_record=time.monotonic_ns()
    if primary is None and (post_record>=end or time.time_ns()>=owner.epoch_end):
        primary=Stop("QUERY_DEADLINE")
        value=dict(value,post_record_return_mono_ns=post_record,post_record_late=True)
        primary.terminal_query_diagnostic=value
    if primary is not None:raise primary
    return dict(facts,query_persistence_return_mono_ns=post_record)

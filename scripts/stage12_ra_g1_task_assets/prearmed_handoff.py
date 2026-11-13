"""Task-scoped prearmed REP handoffs. No authority is issued by this program.

Selected immutable role ownership binds the declared child roles. Historical
precharged records remain readable; current ownership does not assert funding.
Collector facts and independent review remain separate; expected B input is never
derived on the factual-publication path. Native allocation gates stay authoritative.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import select
import shlex
import stat
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone

SCHEMA = "stage12_task_prearmed_factual_handoff_single_driver_v2"
REVIEWER_ROLES = ("CHECKER", "EXACT_CHECKER")
DRIVER_EXECUTION = "SINGLE_ARMED_DRIVER_ONLY"
SOURCE = "9952818fdbdc7df55e73dd11536165af2dc46eb6"
READY = "stage12_local_factual_review_ready_v1"
ROLES = {"WATCH":4,"COLLECTOR_FETCH":7,"CHECKER":2,"FACTUAL_PUBLISH":11,
         "EXACT_FETCH":5,"EXACT_PUBLISH":11,"EXACT_CHECKER":2}
CONFIG_KEYS = {"schema_version","source_sha","source_dir","python_executable","source_inventory","selection",
    "resource_selection","resource_review","job_id","host","expected_uid","expected_gid",
    "state_dir","review_dir","checker_script","exact_checker_script","records_dir","vouchers","limits"}
LIMITS = {"watch_seconds":8400,"watch_line_bytes":4*2**20,"watch_total_bytes":32*2**20,
    "fetch_seconds":60,"publication_seconds":45,"checker_seconds":120,
    "collector_tar_bytes":16*2**20,"collector_data_bytes":16*2**20,"collector_files":512,
    "exact_tar_bytes":16*2**20,"exact_files":256,"poll_ms":50}
FACT_READY_KEYS = {"schema_version","job_id","source_sha","selection_sha256",
    "resource_selection_sha256","collector_ready_sha256","originals_tar_sha256",
    "originals_inventory_sha256","checker_report_sha256","factual_review_sha256",
    "factual_review_bytes","substantive_checks","sealed_utc","reviewer_decision_sha256"}
CODEC_HEADER = b"S12_FIRST_START_CODEC_1024\n"

def need(value, code="PREARMED_HANDOFF_BINDING"):
    if not value: raise RuntimeError(code)

def canonical(value):
    return (json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()

def sha(raw): return hashlib.sha256(raw).hexdigest()

def utc(value):
    need(type(value) is str,"PREARMED_CLOCK")
    return datetime.strptime(value,"%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)

def now_utc(): return datetime.now(timezone.utc)

def z(value): return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

def absolute(value):
    need(type(value) is str and value.startswith("/") and not any(c in value for c in "\n\r\\\0"),"PREARMED_PATH")
    path=Path(value)
    need(".." not in path.parts and str(path)==os.path.normpath(value),"PREARMED_PATH")
    return path

def identity(info):
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,
            info.st_size,info.st_mtime_ns,info.st_ctime_ns)

def ancestor_snapshot(path):
    result=[]
    parents=(path.parent,*path.parent.parents)
    need(len(parents)<=64 and sum(len(os.fsencode(p)) for p in parents)<=16384,"PREARMED_ANCESTOR_BOUND")
    for parent in reversed(parents):
        info=parent.lstat()
        need(stat.S_ISDIR(info.st_mode),"PREARMED_ANCESTOR")
        result.append((str(parent),info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid))
    return tuple(result)

def artifact_path(path):
    path=Path(path)
    need(path.is_absolute() and ".." not in path.parts
         and not any(part in {".git",".ssh",".aws",".config","credentials","secrets","HOLDOUT"}
                     or part.startswith(".env") for part in path.parts)
         and not any(ord(ch)<32 or ord(ch)==127 for ch in str(path)),"PREARMED_ARTIFACT_PATH")
    return path

def read_original(path, maximum, *, private=True):
    path=artifact_path(path)
    ancestors=ancestor_snapshot(path);before=path.lstat()
    need(path.resolve(strict=True)==path and stat.S_ISREG(before.st_mode) and before.st_nlink==1
         and before.st_size<=maximum,"PREARMED_ORIGINAL")
    if private:
        need(stat.S_IMODE(before.st_mode)==0o600 and before.st_uid==os.geteuid()
             and stat.S_IMODE(path.parent.stat().st_mode)==0o700,"PREARMED_PRIVATE")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        need(identity(before)==identity(os.fstat(fd)),"PREARMED_ORIGINAL")
        chunks=[]; remaining=before.st_size
        while remaining:
            raw=os.read(fd,min(8192,remaining));need(bool(raw),"PREARMED_SHORT_READ")
            chunks.append(raw);remaining-=len(raw)
        need(os.read(fd,1)==b"" and identity(before)==identity(os.fstat(fd))
             ==identity(path.lstat()) and ancestor_snapshot(path)==ancestors,"PREARMED_ORIGINAL")
        return b"".join(chunks)
    finally: os.close(fd)

def parse(raw):
    value=json.loads(raw);need(canonical(value)==raw,"PREARMED_CANONICAL")
    return value

def ref(value, maximum, *, private=True):
    need(type(value) is dict and set(value)=={"path","sha256"},"PREARMED_REFERENCE")
    raw=read_original(absolute(value["path"]),maximum,private=private)
    need(sha(raw)==value["sha256"],"PREARMED_REFERENCE_CHANGED")
    return raw

_SEAL_AUTHORIZATION = None


def check_seal_clock(auth):
    need(time.monotonic_ns() < auth["end_mono_ns"] and time.time_ns() < auth["end_epoch_ns"],"PREARMED_REVIEW_LATE")


def check_seal_write(path):
    name=Path(path).name
    role = "FACTUAL_SEAL" if name.startswith(("BOOTSTRAP_REVIEW.record", "FACTUAL_REVIEW.ready")) else "EXACT_SEAL" if name.startswith("EXACT_INPUT_RELEASE") else None
    if role is None:
        return
    auth=_SEAL_AUTHORIZATION
    need(type(auth) is dict and auth["role"]==role and auth["pid"]==os.getpid()
        and str(Path(path).parent)==auth["review_dir"],"PREARMED_DRIVER_OWNERSHIP")
    check_seal_clock(auth)
    need(sha(read_original(Path(auth["claim_path"]),8192))==auth["claim_sha256"],"PREARMED_DRIVER_OWNERSHIP")
    check_seal_clock(auth)


def put(path, raw):
    check_seal_write(path)
    path=artifact_path(path)
    ancestors=ancestor_snapshot(path);parent_before=path.parent.lstat()
    need(stat.S_ISDIR(parent_before.st_mode) and stat.S_IMODE(parent_before.st_mode)==0o700
         and parent_before.st_uid==os.geteuid(),"PREARMED_PRIVATE")
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        need(identity(parent_before)==identity(os.fstat(parent)) and ancestor_snapshot(path)==ancestors,
             "PREARMED_PARENT_CHANGED")
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
        try:
            view=memoryview(raw)
            while view:
                n=os.write(fd,view);need(n>0,"PREARMED_WRITE_UNCERTAIN");view=view[n:]
            os.fsync(fd);written=os.fstat(fd)
        finally:os.close(fd)
        os.fsync(parent)
        need(ancestor_snapshot(path)==ancestors and identity(path.lstat())==identity(written)
             and (path.parent.lstat().st_dev,path.parent.lstat().st_ino)==(parent_before.st_dev,parent_before.st_ino),
             "PREARMED_WRITE_UNCERTAIN")
    finally:os.close(parent)
    need(read_original(path,len(raw))==raw,"PREARMED_WRITE_UNCERTAIN")
    check_seal_write(path)

def load_script(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


CATALOG_SCHEMA = "stage12_task_prearmed_factual_handoff_local_catalog_v3"
SIMPLE_CATALOG_SCHEMA = "stage12_task_prearmed_handoff_role_ownership_v4"
ROLE_OWNERSHIP = "stage12_handoff_role_ownership_v2"
CATALOG_EXACT_SCHEMA = "stage12_task_exact_input_checker_local_catalog_v2"
LOCAL_CATALOG_VERSION = "stage12_task_local_record_catalog_v1"
LOCAL_CATALOG_ROLES = ("adoption", "project_approval", "resource_review", "software_review", "software_report")
LOCAL_CATALOG_CODES = frozenset({"PREARMED_LOCAL_CATALOG_REQUIRED", "PREARMED_LOCAL_CATALOG_FIELDS",
    "PREARMED_LOCAL_CATALOG_BINDING", "PREARMED_LOCAL_CATALOG_IDENTITY", "PREARMED_LOCAL_CATALOG_CONTENT",
    "PREARMED_LOCAL_CATALOG_MEMBERSHIP", "PREARMED_LOCAL_CATALOG_ROLE", "PREARMED_LOCAL_CATALOG_BOUND"})


def catalog_diagnostic(error):
    value=getattr(error,"local_catalog_failure",None)
    if not (type(value) is dict and set(value)=={"version","operation","role","mono_ns","kind","code","errno"}
        and value["version"]=="stage12_local_catalog_first_failure_v1"
        and value["operation"] in ("BIND","ROLE_READ","REPORT_READ","CREATE")
        and (value["role"] is None or value["role"] in LOCAL_CATALOG_ROLES)
        and type(value["mono_ns"]) is int and 0<=value["mono_ns"]<2**64
        and value["kind"] in ("OS_ERROR","RUNTIME","UNKNOWN")
        and type(value["code"]) is str and value["code"] in (LOCAL_CATALOG_CODES|{"UNCLASSIFIED"})
        and (value["errno"] is None or type(value["errno"]) is int and 0<=value["errno"]<=4096)):
        return None
    return dict(value)


def catalog_error(error, operation, role=None):
    """Supplement the original exception with finite static fields, never text."""
    if catalog_diagnostic(error) is None:
        try:
            need(operation in ("BIND", "ROLE_READ", "REPORT_READ", "CREATE"), "PREARMED_LOCAL_CATALOG_FIELDS")
            need(role is None or role in LOCAL_CATALOG_ROLES, "PREARMED_LOCAL_CATALOG_FIELDS")
            error.local_catalog_failure=dict(version="stage12_local_catalog_first_failure_v1",
                operation=operation,role=role,mono_ns=time.monotonic_ns(),
                kind="OS_ERROR" if isinstance(error,OSError) else "RUNTIME" if type(error) is RuntimeError else "UNKNOWN",
                code=error.args[0] if type(error) is RuntimeError and len(error.args)==1
                    and type(error.args[0]) is str and error.args[0] in LOCAL_CATALOG_CODES else "UNCLASSIFIED",
                errno=error.errno if isinstance(error,OSError) and type(error.errno) is int and 0<=error.errno<=4096 else None)
        except BaseException:
            pass
    return error


class LocalRecordCatalog:
    """One exact local original catalog, distinct from selected native paths."""
    def __init__(self, reference, selected, selection_sha256, controller):
        try:
            self.reference=reference;self.controller=controller
            raw=ref(reference,65536);value=parse(raw)
            need(set(value)=={"schema_version","source_sha","selection_sha256","native_records_dir",
                 "root","root_identity","entries"} and value["schema_version"]==LOCAL_CATALOG_VERSION,
                 "PREARMED_LOCAL_CATALOG_FIELDS")
            need(value["source_sha"]==SOURCE==selected["source_sha"]
                and value["selection_sha256"]==selection_sha256
                and value["native_records_dir"]==selected["paths"]["records"], "PREARMED_LOCAL_CATALOG_BINDING")
            self.root=absolute(value["root"]);self.root_identity=value["root_identity"]
            need(self.root!=absolute(value["native_records_dir"])
                and type(self.root_identity) is list and len(self.root_identity)==9
                and all(type(n) is int and n>=0 for n in self.root_identity), "PREARMED_LOCAL_CATALOG_IDENTITY")
            self.chain=ancestor_snapshot(self.root/"catalog.member")
            self.rows={};total=0
            need(type(value["entries"]) is list and len(value["entries"])==5, "PREARMED_LOCAL_CATALOG_MEMBERSHIP")
            for row in value["entries"]:
                need(type(row) is dict and set(row)=={"role","filename","bytes","sha256","identity"}
                    and row["role"] in LOCAL_CATALOG_ROLES and row["role"] not in self.rows,
                    "PREARMED_LOCAL_CATALOG_ROLE")
                role=row["role"];limit=4*2**20 if role=="software_report" else 65536
                need(type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",row["sha256"])
                    and type(row["bytes"]) is int and 0<=row["bytes"]<=limit,
                    "PREARMED_LOCAL_CATALOG_BOUND")
                need(row["filename"]==row["sha256"]+(".md" if role=="software_report" else ".record")
                    and type(row["identity"]) is list and len(row["identity"])==9
                    and all(type(n) is int and n>=0 for n in row["identity"]), "PREARMED_LOCAL_CATALOG_FIELDS")
                if role!="software_report":
                    need(row["sha256"]==selected["records"][role], "PREARMED_LOCAL_CATALOG_BINDING")
                total+=row["bytes"];self.rows[role]=row
            need(set(self.rows)==set(LOCAL_CATALOG_ROLES) and total<=4*65536+4*2**20,
                "PREARMED_LOCAL_CATALOG_BOUND")
            self.check_root()
            software=None
            for role in LOCAL_CATALOG_ROLES[:-1]:
                value=self.role(role)
                if role=="software_review":software=value
            self.report(software["report_sha256"])
        except BaseException as error:
            raise catalog_error(error,"BIND")

    def check_root(self):
        info=self.root.lstat()
        need(identity(info)==tuple(self.root_identity) and stat.S_ISDIR(info.st_mode)
            and stat.S_IMODE(info.st_mode)==0o700 and info.st_uid==os.geteuid()
            and self.root.resolve(strict=True)==self.root
            and ancestor_snapshot(self.root/"catalog.member")==self.chain, "PREARMED_LOCAL_CATALOG_IDENTITY")
        names=set()
        with os.scandir(self.root) as entries:
            for item in entries:
                need(len(names)<5 and item.name not in names, "PREARMED_LOCAL_CATALOG_MEMBERSHIP")
                names.add(item.name)
        need(names=={row["filename"] for row in self.rows.values()}, "PREARMED_LOCAL_CATALOG_MEMBERSHIP")

    def original(self,role):
        need(role in LOCAL_CATALOG_ROLES,"PREARMED_LOCAL_CATALOG_ROLE")
        operation="REPORT_READ" if role=="software_report" else "ROLE_READ"
        try:
            self.check_root();row=self.rows[role];path=self.root/row["filename"]
            before=path.lstat()
            need(identity(before)==tuple(row["identity"]) and before.st_size==row["bytes"]
                and before.st_gid==self.root_identity[4], "PREARMED_LOCAL_CATALOG_IDENTITY")
            raw=read_original(path,4*2**20 if role=="software_report" else 65536)
            need(len(raw)==row["bytes"] and sha(raw)==row["sha256"]
                and identity(path.lstat())==tuple(row["identity"]), "PREARMED_LOCAL_CATALOG_CONTENT")
            self.check_root()
            return raw
        except BaseException as error:
            raise catalog_error(error,operation,role)

    def role(self,name):
        try:
            need(name in LOCAL_CATALOG_ROLES[:-1],"PREARMED_LOCAL_CATALOG_ROLE")
            raw=self.original(name);value=self.controller.parse(raw)
            need(self.controller.canonical(value)==raw,"PREARMED_LOCAL_CATALOG_CONTENT")
            return value
        except BaseException as error:
            raise catalog_error(error,"ROLE_READ",name if name in LOCAL_CATALOG_ROLES else None)

    def report(self, expected_sha256):
        try:
            need(expected_sha256==self.rows["software_report"]["sha256"],"PREARMED_LOCAL_CATALOG_BINDING")
            return self.original("software_report")
        except BaseException as error:
            raise catalog_error(error,"REPORT_READ","software_report")


def create_local_catalog(selection_raw, local_records_dir, output_root, manifest_path, controller):
    """Create a new bounded copy catalog; no native path or original is changed."""
    role=None
    try:
        selected=controller.validate_selection(controller.parse(selection_raw))
        need(selected["source_sha"]==SOURCE,"PREARMED_LOCAL_CATALOG_BINDING")
        original_root=absolute(str(local_records_dir));root=absolute(str(output_root));manifest=absolute(str(manifest_path))
        need(root!=original_root and not root.is_relative_to(original_root)
            and not original_root.is_relative_to(root) and not manifest.is_relative_to(original_root)
            and manifest.parent!=root and not manifest.is_relative_to(root),"PREARMED_LOCAL_CATALOG_BINDING")
        parent=root.parent.lstat()
        need(stat.S_ISDIR(parent.st_mode) and stat.S_IMODE(parent.st_mode)==0o700
            and parent.st_uid==os.geteuid(),"PREARMED_PRIVATE")
        ancestor_snapshot(root);root.mkdir(mode=0o700)
        rows=[];software=None;written=set()
        for role in LOCAL_CATALOG_ROLES:
            expected=software["report_sha256"] if role=="software_report" else selected["records"][role]
            need(type(expected) is str and re.fullmatch(r"[0-9a-f]{64}",expected),"PREARMED_LOCAL_CATALOG_FIELDS")
            filename=expected+(".md" if role=="software_report" else ".record")
            raw=read_original(original_root/filename,4*2**20 if role=="software_report" else 65536)
            need(sha(raw)==expected,"PREARMED_LOCAL_CATALOG_CONTENT")
            if role!="software_report":
                value=controller.parse(raw)
                need(controller.canonical(value)==raw,"PREARMED_LOCAL_CATALOG_CONTENT")
                if role=="software_review":software=value
            if filename not in written:put(root/filename,raw);written.add(filename)
            else:need(read_original(root/filename,len(raw))==raw,"PREARMED_LOCAL_CATALOG_CONTENT")
            rows.append(dict(role=role,filename=filename,bytes=len(raw),sha256=expected,
                             identity=list(identity((root/filename).lstat()))))
        value=dict(schema_version=LOCAL_CATALOG_VERSION,source_sha=SOURCE,
            selection_sha256=sha(selection_raw),native_records_dir=selected["paths"]["records"],
            root=str(root),root_identity=list(identity(root.lstat())),entries=rows)
        raw=canonical(value);need(len(raw)<=65536,"PREARMED_LOCAL_CATALOG_BOUND")
        put(manifest,raw);reference=dict(path=str(manifest),sha256=sha(raw))
        LocalRecordCatalog(reference,selected,sha(selection_raw),controller)
        return reference
    except BaseException as error:
        raise catalog_error(error,"CREATE",role)


class Bound:
    def __init__(self, raw, *, unissued=False):
        need(type(unissued) is bool,"PREARMED_CONFIG")
        self.unissued=unissued
        self.raw=raw;self.cfg=parse(raw);c=self.cfg
        catalog_selected=c.get("schema_version") in (CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA)
        need(set(c)==(CONFIG_KEYS|{"local_record_catalog"} if catalog_selected else CONFIG_KEYS)
            and c["schema_version"] in (SCHEMA,CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA) and c["source_sha"]==SOURCE,"PREARMED_CONFIG")
        if unissued:
            need(all(c[field] is None for field in ("job_id","state_dir","review_dir","vouchers")),"PREARMED_UNISSUED_FIELDS")
        else:
            need(type(c["job_id"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}",c["job_id"]),"PREARMED_JOB")
        need(c["host"]=="goethe" and c["limits"]==LIMITS,"PREARMED_CONFIG")
        need(type(c["expected_uid"]) is int and c["expected_uid"]>0 and
             type(c["expected_gid"]) is int and c["expected_gid"]>=0,"PREARMED_CONFIG")
        self.source=absolute(c["source_dir"])
        inventory=parse(ref(c["source_inventory"],4*2**20))
        self.selection_raw=ref(c["selection"],4*2**20)
        self.resource_raw=ref(c["resource_selection"],65536)
        self.review_raw=ref(c["resource_review"],65536)
        self.resource=parse(self.resource_raw)
        need(type(inventory) is list and 1<=len(inventory)<=2048,"PREARMED_SOURCE_BOUND")
        source_names=[];source_total=0
        for row in inventory:
            need(type(row) is dict and set(row)=={"path","bytes","sha256"}
                 and type(row["path"]) is str and 0<len(row["path"].encode("utf8"))<=512
                 and not row["path"].startswith("/") and ".." not in Path(row["path"]).parts
                 and str(Path(row["path"]))==row["path"]
                 and not any(part in {".git",".ssh",".aws",".config","credentials","secrets","HOLDOUT"} or part.startswith(".env") for part in Path(row["path"]).parts)
                 and not any(ord(ch)<32 or ord(ch)==127 for ch in row["path"])
                 and type(row["bytes"]) is int and 0<=row["bytes"]<=4*2**20
                 and type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}",row["sha256"]),"PREARMED_SOURCE_BOUND")
            source_names.append(row["path"]);source_total+=row["bytes"]
        need(source_names==sorted(set(source_names)) and source_total<=64*2**20,"PREARMED_SOURCE_BOUND")
        need({"scripts/stage12_ra_g1_allocation.py","scripts/stage12_ra_g1_review_handoff.py","src/safe_geocoding_pipeline/__init__.py"}<=set(source_names),"PREARMED_SOURCE_BOUND")
        # Content reads follow the complete metadata preflight.
        for row in inventory:
            need(set(row)=={"path","bytes","sha256"} and type(row["path"]) is str
                 and not row["path"].startswith("/") and ".." not in Path(row["path"]).parts,"PREARMED_SOURCE")
            original=read_original(self.source/row["path"],row["bytes"],private=False)
            need(len(original)==row["bytes"] and sha(original)==row["sha256"],"PREARMED_SOURCE")
        sys.path.insert(0,str(self.source/"src"))
        import safe_geocoding_pipeline as package
        need(package.__version__=="0.2.0" and Path(package.__file__).resolve()==self.source/"src/safe_geocoding_pipeline/__init__.py"
             and list(map(lambda p:Path(p).resolve(),package.__path__))==[self.source/"src/safe_geocoding_pipeline"],"PREARMED_SOURCE")
        self.controller=load_script(self.source/"scripts/stage12_ra_g1_allocation.py","prearmed_controller")
        self.helper=load_script(self.source/"scripts/stage12_ra_g1_review_handoff.py","prearmed_review_handoff")
        self.selected=self.controller.validate_selection(self.controller.parse(self.selection_raw))
        s=self.selected
        need((c["schema_version"]==SIMPLE_CATALOG_SCHEMA)==
             (s.get("rep_admin_budget_adoption",{}).get("window",{}).get("version")==
              "SYNTHETIC_AND_COLLECTION_OPERATING_WINDOW_r4"),"PREARMED_CONFIG")
        need(s["version"]==self.controller.REP512_VERSION and s["source_sha"]==SOURCE
             and s["source_files"]==inventory and s["resource_selection_sha256"]==sha(self.resource_raw),"PREARMED_SOURCE")
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution
        self.assurance,self.execution=assurance,execution
        assurance.validate_selection(self.resource)
        need(self.resource["schema_version"]==assurance.REP512_SELECTION and self.resource["source_git_sha"]==SOURCE,"PREARMED_RESOURCE")
        # These are the factual checker's existing static RR associations.
        review=self.production_parse(self.review_raw)
        need(self.controller.digest(review)==s["records"]["resource_review"]
             and review["scope"]==self.resource["scope"]==s["scope"]=="REPRESENTATIVE_NO_SERVICE"
             and review["disposition"]=="PASS" and review["source_sha"]==SOURCE
             and review["source_files"]==len(s["source_files"])
             and review["source_bytes"]==sum(row["bytes"] for row in s["source_files"]),"PREARMED_RESOURCE_REVIEW")
        need(all(self.resource[key]==review[key] for key in ("descriptor_inventory_sha256","workload_graph_sha256","paths_sha256"))
             and review["accounting_inventory_sha256"]==self.controller.digest(s["accounting_inventory"]),"PREARMED_RESOURCE_REVIEW")
        self.root=absolute(s["paths"]["allocation_root"])
        if unissued:self.state=self.review_dir=None
        else:
            self.state=absolute(c["state_dir"]);self.review_dir=absolute(c["review_dir"])
            need(self.state!=self.review_dir and not self.state.is_relative_to(self.review_dir)
                 and not self.review_dir.is_relative_to(self.state),"PREARMED_PATH")
        self.sha=sha(self.selection_raw);self.resource_sha=sha(self.resource_raw)
        self.records={};self.terminal=False;self.factual_published=False
        self.closed_records={}
        p=s["paths"]
        self.names={"context":p["context"],"wait":str(self.root/"collector.wait.record"),
            "handoff":str(self.root/"collector.handoff.record"),
            "bootstrap":str(Path(p["bootstrap"])/"bootstrap.record"),
            "manifest":str(Path(p["bootstrap"])/"manifest.record"),
            "collector_terminal":str(self.root/"collector_resources/supervisor_terminal.record"),
            "phase7":str(self.root/"review_resources/admin_binding.record"),
            "phase7_prefix":str(self.root/"review_resources/bootstrap_prefix.record"),
            "phase8":str(self.root/"binder_resources/admin_binding.record"),
            "input":p["input"],"review_binding":str(Path(p["binding"])/"integration_review.binding.json")}
        self.terminal_paths=tuple(dict.fromkeys([p["supervisor_state"],p["worker_return"],p["outcome"],
            str(self.root/"binder.wait.record"),str(self.root/"binder.handoff.record")]))
        self.required=tuple(k for k in self.names if k not in ("phase8","input","review_binding"))
        self.review_closed=tuple(str(self.root/"review_resources"/(n+".record")) for n in ("preopening","opener_return","monitor_terminal","worker_validation","supervisor_terminal"))
        self.binder_closed=tuple(str(self.root/"binder_resources"/(n+".record")) for n in ("preopening","opener_return","monitor_terminal","worker_validation","supervisor_terminal"))
        self.config_scope=sha(canonical({k:v for k,v in c.items() if k!="vouchers"}))
        checker=ref(c["checker_script"],256*1024)
        self.checker_sha=sha(checker)
        self.exact_checker_sha=sha(ref(c["exact_checker_script"],256*1024))
        self.records_dir=absolute(c["records_dir"])
        self.local_catalog=None
        if catalog_selected:
            need(self.records_dir==absolute(s["paths"]["records"]),"PREARMED_LOCAL_CATALOG_BINDING")
            self.local_catalog=LocalRecordCatalog(c["local_record_catalog"],s,self.sha,self.controller)

    def production_parse(self,raw):
        value=self.controller.parse(raw)
        need(self.controller.canonical(value)==raw,"PREARMED_CANONICAL_PRODUCTION")
        return value

    def watch_plan(self):
        paths=list(self.names.values())+list(self.terminal_paths)+list(self.review_closed)+list(self.binder_closed)
        command="exec timeout --signal=TERM --kill-after=1s "+str(LIMITS["watch_seconds"])+"s tail -F -n+1 -- "+" ".join(map(shlex.quote,paths))
        return self.plan("WATCH",command,maximum_stdout=LIMITS["watch_total_bytes"],maximum_stderr=65536,timeout=LIMITS["watch_seconds"]+25)

    def plan(self, role, command, **extra):
        return dict(role=role,units=ROLES[role],execution=DRIVER_EXECUTION,source_sha=SOURCE,job_id=self.cfg["job_id"],
            selection_sha256=self.sha,resource_selection_sha256=self.resource_sha,
            argv=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=20",self.cfg["host"],command],
            command=command,**extra)

    def accept_line(self, path, raw):
        need(path in set(self.names.values())|set(self.terminal_paths)|set(self.review_closed)|set(self.binder_closed),"PREARMED_STREAM_PATH")
        need(0<len(raw)<=LIMITS["watch_line_bytes"],"PREARMED_STREAM_RECORD")
        self.production_parse(raw)
        if path in self.review_closed:
            need(self.factual_published,"PREARMED_REVIEW_CLOSED")
            self.closed_records[path]=raw;return
        if path in self.binder_closed:raise RuntimeError("PREARMED_BINDER_CLOSED")
        if path in self.terminal_paths:
            self.terminal=True;raise RuntimeError("PREARMED_NATIVE_TERMINAL")
        key=next(k for k,v in self.names.items() if v==path)
        if key in self.records: need(self.records[key]==raw,"PREARMED_CHANGED_CONTROL")
        self.records[key]=raw

    def readiness(self):
        if not all(k in self.records for k in self.required):return None
        need(not self.terminal,"PREARMED_NATIVE_TERMINAL")
        r={k:self.production_parse(self.records[k]) for k in self.required};s=self.selected;a=self.assurance;e=self.execution
        context=e.validate_supervisor_context(r["context"])
        need(context["source_git_sha"]==SOURCE and str(context["slurm_job_id"])==self.cfg["job_id"]
             and context["run_nonce"]==s["intent_id"] and context["selection_sha256"]==self.resource_sha
             and context["private_paths"]==dict(allocation_root=str(self.root),
                 resource_evidence_root=s["paths"]["output"],scratch_root=str(self.root)),"PREARMED_CONTEXT")
        h=r["handoff"];w=r["wait"]
        totals=self.controller.handoff_counters(h,len(self.records["handoff"]))
        need(h["stage"]=="collect" and h["source_sha"]==SOURCE and h["allocation_selection_sha256"]==self.sha
             and h["resource_selection_sha256"]==self.resource_sha and h["supervisor_context_sha256"]==sha(self.records["context"])
             and h["predecessor_handoff_sha256"] is None,"PREARMED_COLLECTOR")
        self.controller.validate_wait_record(w,source_sha=SOURCE,allocation_selection_sha256=self.sha,
            supervisor_pid=context["supervisor"]["pid"],process_pid=h["process_pid"])
        need(len(h["administrative_sessions"])==1,"PREARMED_COLLECTOR")
        row=h["administrative_sessions"][0];terminal=r["collector_terminal"]
        child_subset={key:w[key] for key in ("pid","wait_status","acquired_mono_ns")}
        need(row["role"]=="COLLECTOR" and row["phase_id"]==6 and row["root"]==str(self.root/"collector_resources")
             and terminal["phase_id"]==6 and terminal["binding_sha256"]==row["binding_sha256"]
             and terminal["selection_sha256"]==self.resource_sha and terminal["child_exit_code"]==0
             and terminal["child_signal"] is None and terminal["first_failure"] is None
             and terminal["cleanup_failure"] is None and terminal["disposition"]=="COMPLETE_SELECTED_SCOPE"
             and terminal["child_result_original_sha256"]==self.controller.digest(child_subset),"PREARMED_COLLECTOR_CLOSURE")
        a.shape(r["phase7"],e.ADMIN_BINDING_SCHEMA)
        p7,bp=r["phase7"],r["phase7_prefix"]
        need(p7["role"]=="REVIEW" and p7["phase_id"]==7 and p7["source_git_sha"]==SOURCE
             and p7["selection_sha256"]==self.resource_sha and p7["supervisor_context_sha256"]==sha(self.records["context"])
             and p7["scope_start_mono_ns"]<p7["deadline_mono_ns"]<=p7["scope_start_mono_ns"]+480_000_000_000
             and bp["binding_sha256"]==sha(self.records["phase7"]) and bp["phase_id"]==7 and bp["role"]=="REVIEW"
             and bp["selection_sha256"]==self.resource_sha and bp["source_entry_mono_ns"]==p7["scope_start_mono_ns"]
             and bp["phase_deadline_mono_ns"]==p7["deadline_mono_ns"]
             and bp["first_start_seq"]==1 and p7["scope_start_mono_ns"]<=bp["bootstrap_end_mono_ns"]
             <=bp["first_start_enter_mono_ns"]<=bp["first_start_exit_mono_ns"]<=bp["first_start_ack_mono_ns"]
             <=p7["scope_start_mono_ns"]+30_000_000_000,"PREARMED_REVIEW_START")
        b,m=r["bootstrap"],r["manifest"]
        need(b["source_sha"]==SOURCE and str(b["job_id"])==self.cfg["job_id"] and m["source_sha"]==SOURCE
             and m["bootstrap_sha256"]==sha(self.records["bootstrap"])
             and b["resource_execution"]["supervisor_context_sha256"]==sha(self.records["context"]),"PREARMED_BOOTSTRAP")
        started,ended=b["started_mono_ns"],b["ended_mono_ns"]
        need(type(started) is int and type(ended) is int and started<=ended<=p7["scope_start_mono_ns"],"PREARMED_CLOCK")
        base=utc(b["created_utc"])
        origin=base+timedelta(microseconds=(p7["scope_start_mono_ns"]-ended)//1000)
        deadline=base+timedelta(microseconds=(p7["deadline_mono_ns"]-ended)//1000)
        return dict(schema_version="stage12_task_collector_ready_v1",status="SAME_JOB_PARENT_WAIT_AND_CLOSED_COLLECTOR_READY_TO_FETCH",
            source_sha=SOURCE,job_id=self.cfg["job_id"],selection_sha256=self.sha,resource_selection_sha256=self.resource_sha,
            raw_sha256={k:sha(self.records[k]) for k in self.required},
            collector_released_counter_prefix=totals,first_start_original_sha256=bp["first_start_original_sha256"],
            review_origin_utc_earliest=z(origin),review_deadline_utc_earliest=z(deadline),
            review_target_utc_earliest=z(origin+timedelta(seconds=360)),
            clock_semantics="BOOTSTRAP_UTC_WITHIN_NATIVE_START_END_BRACKET_SAME_ALLOCATION_NOT_CROSS_HOST_MONO",
            required_independent_factual_checks="PENDING_FETCH_AND_FRESH_NONAUTHOR_CHECKER",
            native_acceptance="NOT_OBSERVED")

    def eligible_lines(self, cutoff, *, factual=True):
        q=shlex.quote
        result=["handoff_state=$(squeue -h -j "+q(self.cfg["job_id"])+" -o '%i|%T')",
            'test "$handoff_state" = '+q(self.cfg["job_id"]+"|RUNNING")]
        for path in self.terminal_paths+(self.review_closed if factual else self.binder_closed):
            result+=["test ! -e "+q(path),"test ! -L "+q(path)]
        result+=["printf -v handoff_now '%(%s)T' -1",'test "$handoff_now" -lt '+str(int(cutoff.timestamp()))]
        return result

    def fetch_plan(self, ready):
        cutoff=min(utc(ready["review_deadline_utc_earliest"]),utc(self.selected["valid_until"]))-timedelta(seconds=LIMITS["fetch_seconds"])
        q=shlex.quote
        roots=[str(Path(self.selected["paths"]["bootstrap"]).relative_to(self.root)),
            str(Path(self.names["context"]).relative_to(self.root)),"collector.wait.record","collector.handoff.record",
            "collector_resources","review_resources/admin_binding.record","review_resources/bootstrap_prefix.record",
            "review_resources/originals/"+ready["first_start_original_sha256"]+".record"]
        checks="".join(ready["raw_sha256"][k]+"  "+self.names[k]+"\n" for k in self.required)
        script=["set -e","umask 077",*self.eligible_lines(cutoff),
            "sha256sum --check --status <<'PREARMED_ORIGINALS'",checks.rstrip("\n"),"PREARMED_ORIGINALS",
            "tar -cf - -C "+q(str(self.root))+" "+" ".join(map(q,roots[:5]))+" --no-recursion review_resources review_resources/originals "+" ".join(map(q,roots[5:])),
            "printf '%s\\n' 'S12_FIRST_START_CODEC_1024' >&2",
            "head -c 1024 -- "+q(str(self.root/"review_resources/observations.bin"))+" >&2"]
        return self.plan("COLLECTOR_FETCH","\n".join(script)+"\n",expected_roots=roots,
            maximum_stdout=LIMITS["collector_tar_bytes"],maximum_stderr=len(CODEC_HEADER)+1024,
            timeout=LIMITS["fetch_seconds"])

    def factual_plan(self, ready, marker_raw, factual_raw, independent_report_raw):
        marker=parse(marker_raw);factual=self.production_parse(factual_raw);report=parse(independent_report_raw)
        need(set(marker)==FACT_READY_KEYS and marker["schema_version"]==READY
             and marker["substantive_checks"]=="PASS_ALL_REQUIRED","PREARMED_REVIEW_INCOMPLETE")
        expected={"job_id":self.cfg["job_id"],"source_sha":SOURCE,"selection_sha256":self.sha,
            "resource_selection_sha256":self.resource_sha,"collector_ready_sha256":sha(canonical(ready)),
            "originals_tar_sha256":self.archive_sha,"originals_inventory_sha256":self.inventory_sha,
            "checker_report_sha256":sha(independent_report_raw),"reviewer_decision_sha256":sha(read_original(self.review_dir/"FACTUAL_REVIEW_DECISION.record",8192)),"factual_review_sha256":sha(factual_raw),
            "factual_review_bytes":len(factual_raw)}
        need(all(marker[k]==v for k,v in expected.items()),"PREARMED_REVIEW_BINDING")
        need(report["required_checks"]=="ALL_COMPLETED" and report["authority"]=="NONE_FINDINGS_ONLY"
             and report["release_or_factual_authority_issued"] is False and report["b_input_derived"] is False and report["evidence_use"]=="FRESH_SAME_ALLOCATION_FINDINGS_ONLY","PREARMED_REVIEW_INCOMPLETE")
        for key,value in {"source_sha":SOURCE,"job_id":int(self.cfg["job_id"]),"selection_sha256":self.sha,
            "resource_selection_sha256":self.resource_sha,"originals_tar_sha256":self.archive_sha,
            "originals_inventory_sha256":self.inventory_sha,"checker_sha256":self.checker_sha}.items():
            need(report[key]==value,"PREARMED_REVIEW_BINDING")
        need(report["checker_input_sha256"]==sha(read_original(self.state/"CHECKER_INPUT.record",4*2**20)),"PREARMED_REVIEW_BINDING")
        completion=parse(read_original(self.state/"CHECKER.completed.record",8192))
        need(completion["returncode"]==0 and completion["report_sha256"]==sha(independent_report_raw)
             and completion["checker_input_sha256"]==report["checker_input_sha256"]
             and completion["spent_sha256"]==sha(read_original(self.state/"CHECKER.SPENT.record",8192)),"PREARMED_REVIEW_BINDING")
        essential={"schema_version":"stage12_ra_g1_independent_bootstrap_review_v1","disposition":"PASS",
            "source_sha":SOURCE,"selection_sha256":self.sha,"resource_selection_sha256":self.resource_sha,
            "bootstrap_sha256":ready["raw_sha256"]["bootstrap"],"bootstrap_manifest_sha256":ready["raw_sha256"]["manifest"],
            "collector_wait_sha256":ready["raw_sha256"]["wait"],"collector_handoff_sha256":ready["raw_sha256"]["handoff"],
            "originals_archive_sha256":self.archive_sha,"originals_inventory_sha256":self.inventory_sha,
            "independent_report_sha256":sha(independent_report_raw),"independent_decision_sha256":marker["reviewer_decision_sha256"],"exact_B_input_release":"NOT_ISSUED"}
        need(all(factual.get(k)==v for k,v in essential.items()) and str(factual.get("job_id"))==self.cfg["job_id"],"PREARMED_REVIEW_BINDING")
        cutoff=min(utc(ready["review_deadline_utc_earliest"]),utc(self.selected["valid_until"]))-timedelta(seconds=LIMITS["publication_seconds"])
        need(now_utc()<cutoff and utc(marker["sealed_utc"])<=now_utc(),"PREARMED_REVIEW_LATE")
        destination=self.selected["paths"]["review"]
        temporary=destination+".publication-"+sha(factual_raw)[:12]+".tmp"
        checks="".join(ready["raw_sha256"][k]+"  "+self.names[k]+"\n" for k in self.required)
        command=emit_factual_shell(destination=destination,factual_raw=factual_raw,job_id=self.cfg["job_id"],
            checksum_text=checks,terminal_paths=self.terminal_paths+self.review_closed,
            cutoff_epoch=int(cutoff.timestamp()))
        return self.plan("FACTUAL_PUBLISH",command,maximum_stdout=8192,maximum_stderr=8192,
            timeout=LIMITS["publication_seconds"],expected_stdout=(sha(factual_raw)+"  "+destination+"\n").encode().hex(),
            creation_attempts=3,logical_write_bytes=len(factual_raw)+len(checks.encode()),
            native_acceptance="PENDING_ACTUAL_REVIEW_CLOSE_AND_BINDER_START",
            target_status="UTC_CONSERVATIVE_WITHIN_360" if now_utc()<=utc(ready["review_target_utc_earliest"]) else "TARGET_MISSED_NATIVE_MARGIN_OBSERVED_ONLY")

def emit_factual_shell(*, destination, factual_raw, job_id, checksum_text, terminal_paths, cutoff_epoch):
    """Pure command renderer, not an authority or factual-evidence validator.

    Production calls this only after all factual_plan semantic gates. Offline
    tests may use a non-executable dummy body and simulated Slurm function.
    """
    need(type(factual_raw) is bytes and len(factual_raw)<=8192
         and type(job_id) is str and re.fullmatch(r"[1-9][0-9]{0,19}",job_id)
         and type(cutoff_epoch) is int and cutoff_epoch>0,"PREARMED_SHELL_ARGUMENTS")
    q=shlex.quote;parent=str(Path(destination).parent)
    temporary=destination+".publication-"+sha(factual_raw)[:12]+".tmp"
    script=["set -e","umask 077","test -d "+q(parent),"test ! -L "+q(parent)]
    for path in (destination,temporary):script+=["test ! -e "+q(path),"test ! -L "+q(path)]
    script+=["handoff_state=$(squeue -h -j "+q(job_id)+" -o '%i|%T')",
        'test "$handoff_state" = '+q(job_id+"|RUNNING")]
    for path in terminal_paths:script+=["test ! -e "+q(path),"test ! -L "+q(path)]
    script+=["printf -v handoff_now '%(%s)T' -1",'test "$handoff_now" -lt '+str(cutoff_epoch)]
    script+=["sha256sum --check --status <<'PREARMED_ORIGINALS'",checksum_text.rstrip("\n"),"PREARMED_ORIGINALS",
        "set -o noclobber","printf '%s\\n' "+q(factual_raw.decode().removesuffix("\n"))+" > "+q(temporary),
        "set +o noclobber","timeout --signal=TERM --kill-after=1s 5s sync -f "+q(temporary)]
    for path in terminal_paths:script+=["test ! -e "+q(path),"test ! -L "+q(path)]
    script+=["printf -v handoff_now '%(%s)T' -1",'test "$handoff_now" -lt '+str(cutoff_epoch),
        "mv --no-clobber --no-target-directory -- "+q(temporary)+" "+q(destination),
        "test ! -e "+q(temporary),"timeout --signal=TERM --kill-after=1s 5s sync -f "+q(parent),
        "sha256sum -- "+q(destination),""]
    return "\n".join(script)


def archive_relative(item, code):
    rel=Path(item.name);text=str(rel)
    need(not rel.is_absolute() and rel.parts and ".." not in rel.parts
         and len(item.name.encode("utf8"))<=2048
         and (item.name==text or item.isdir() and item.name==text+"/"),code)
    return rel


def archive_parents(files):
    return {parent for rel in files for parent in rel.parents if parent!=Path(".")}


def exact_archive_layout(bound, expected_relative_roots=None):
    paths=bound.selected["paths"]
    specs=tuple(Path(paths[key]).relative_to(bound.root) for key in ("input","binding","context","review"))
    specs+=(Path("review_resources/admin_binding.record"),Path("binder_resources/admin_binding.record"))
    if expected_relative_roots is not None:
        need(tuple(Path(p) for p in expected_relative_roots)==specs,"PREARMED_EXACT_ARCHIVE")
    binding=specs[1];fixed=set(specs)-{binding}
    directories={binding,binding/"resource_evidence"}|archive_parents(fixed)
    need(len(directories)==4 and all(0<len(p.parts)<=2 for p in directories),"PREARMED_EXACT_ARCHIVE")
    return fixed,binding,directories


def exact_copied_tree(root, files, directories):
    # Inspect only private, descriptor-bound selected directories.
    need(len(files)<=LIMITS["exact_files"] and len(directories)<=4,"PREARMED_EXACT_INVENTORY")
    pending=[Path(".")];seen_dirs=set();seen_files=set();entries=0
    def identity(info):
        return info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid
    while pending:
        current=pending.pop();cursor=root/current
        chain=ancestor_snapshot(cursor/"__copied_tree_entry__")
        original=cursor.lstat()
        need(stat.S_ISDIR(original.st_mode) and stat.S_IMODE(original.st_mode)==0o700
             and original.st_uid==os.getuid(),"PREARMED_EXACT_INVENTORY")
        fd=os.open(cursor,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            need(identity(os.fstat(fd))==identity(original),"PREARMED_EXACT_INVENTORY")
            with os.scandir(fd) as children:
                for child in children:
                    entries+=1;need(entries<=LIMITS["exact_files"]+len(directories),"PREARMED_EXACT_INVENTORY")
                    rel=current/child.name;info=child.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        need(rel in directories and rel not in seen_dirs
                             and stat.S_IMODE(info.st_mode)==0o700 and info.st_uid==os.getuid(),"PREARMED_EXACT_INVENTORY")
                        seen_dirs.add(rel);pending.append(rel)
                    else:
                        need(stat.S_ISREG(info.st_mode) and rel in files and rel not in seen_files,"PREARMED_EXACT_INVENTORY")
                        seen_files.add(rel)
            need(identity(os.fstat(fd))==identity(original)
                 and identity(cursor.lstat())==identity(original)
                 and ancestor_snapshot(cursor/"__copied_tree_entry__")==chain,"PREARMED_EXACT_INVENTORY")
        finally:os.close(fd)
    need(seen_dirs==directories and seen_files==files,"PREARMED_EXACT_INVENTORY")


def extract_collector(bound, raw, stderr, ready):
    need(0<len(raw)<=LIMITS["collector_tar_bytes"] and stderr.startswith(CODEC_HEADER)
         and len(stderr)==len(CODEC_HEADER)+1024,"PREARMED_FETCH_FRAMING")
    destination=bound.state/"collector-originals"
    roots=bound.fetch_plan(ready)["expected_roots"];specs=tuple(Path(p) for p in roots)
    directories={Path(p) for p in ("bootstrap","collector_resources","collector_resources/originals","review_resources","review_resources/originals")}
    inventory=[];seen=set();files=set();headers=set();items=[];total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
        for item in archive:
            rel=archive_relative(item,"PREARMED_ARCHIVE")
            need(rel not in seen and len(seen)<LIMITS["collector_files"]+len(directories),"PREARMED_ARCHIVE")
            seen.add(rel)
            if item.isdir():
                need(rel in directories and item.mode==0o700
                     and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"],"PREARMED_ARCHIVE")
                headers.add(rel);continue
            allowed=any(rel==p or p in rel.parents for p in specs)
            need(item.isfile() and rel not in directories and allowed
                 and archive_parents({rel})<=directories and item.mode==0o600
                 and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"]
                 and 0<=item.size<=collector_file_limit(bound,rel,ready)
                 and len(files)<LIMITS["collector_files"],"PREARMED_ARCHIVE")
            total+=item.size;need(total<=LIMITS["collector_data_bytes"],"PREARMED_ARCHIVE")
            files.add(rel);items.append((rel,item))
        effective=archive_parents(files)|{p for p in specs if p in directories}
        need(effective<=directories and headers<=effective
             and all(p in files or p in headers or p in archive_parents(files) for p in specs),"PREARMED_ARCHIVE")
        # All headers and implicit parents are closed before the first mkdir.
        destination.mkdir(mode=0o700)
        for rel in sorted(effective,key=lambda p:(len(p.parts),str(p))):
            (destination/rel).mkdir(mode=0o700)
        for rel,item in items:
            body=archive.extractfile(item).read(item.size+1)
            need(len(body)==item.size,"PREARMED_ARCHIVE")
            put(destination/rel,body)
            inventory.append(dict(path=str(rel),bytes=len(body),sha256=sha(body),original_mode=item.mode,
                original_uid=item.uid,original_gid=item.gid))
    for key in bound.required:
        rel=Path(bound.names[key]).relative_to(bound.root)
        need(read_original(destination/rel,65536)==bound.records[key],"PREARMED_FETCH_CHANGED")
    codec_path=bound.state/"review_first_start_codec.bin";codec=stderr[len(CODEC_HEADER):];put(codec_path,codec)
    inventory.sort(key=lambda row:row["path"])
    need(read_original(bound.state/"COLLECTOR_FETCH.stdout",LIMITS["collector_tar_bytes"])==raw,"PREARMED_FETCH_CHANGED")
    put(bound.state/"COLLECTOR_INVENTORY.record",canonical(inventory))
    bound.archive_sha=sha(raw);bound.inventory_sha=sha(canonical(inventory))
    return destination,inventory,dict(path=str(codec_path),sha256=sha(codec),offset=0,bytes=1024)

def validate_role_ownership(value, cfg, selection_sha, resource_sha, scope_sha, decision_sha=None):
    """The legacy `vouchers` config key remains a hash reference, not a payer."""
    simple=cfg["schema_version"]==SIMPLE_CATALOG_SCHEMA
    base={"schema_version","source_sha","job_id","selection_sha256","resource_selection_sha256",
          "configuration_scope_sha256","orchestrator_sha256","roles"}
    need(set(value)==(base|{"decision_delta_sha256"} if simple else base|{"ledger_reservation_id"}),"PREARMED_VOUCHER")
    need(value["schema_version"]==(ROLE_OWNERSHIP if simple else "stage12_root_precharged_handoff_vouchers_v1")
         and value["source_sha"]==SOURCE and value["job_id"]==cfg["job_id"]
         and value["selection_sha256"]==selection_sha and value["resource_selection_sha256"]==resource_sha
         and value["configuration_scope_sha256"]==scope_sha
         and value["roles"]==(sorted(ROLES) if simple else ROLES)
         and value["orchestrator_sha256"]==sha(read_original(Path(__file__).resolve(),256*1024,private=False)),"PREARMED_VOUCHER")
    if simple:
        need(type(decision_sha) is str and re.fullmatch(r"[0-9a-f]{64}",decision_sha)
             and value["decision_delta_sha256"]==decision_sha,"PREARMED_VOUCHER")


class Vouchers:
    """Exact single-use role ownership; legacy class/config names are codecs."""
    def __init__(self,bound):
        self.b=bound;self.raw=ref(bound.cfg["vouchers"],65536);self.v=parse(self.raw)
        validate_role_ownership(self.v,bound.cfg,bound.sha,bound.resource_sha,bound.config_scope,
            bound.selected["rep_admin_budget_adoption"]["window"]["owner_authority_sha256"]
            if bound.cfg["schema_version"]==SIMPLE_CATALOG_SCHEMA else None)
    def start(self,plan):
        role=plan["role"];need(role in ROLES and role not in REVIEWER_ROLES and plan["units"]==ROLES[role],"PREARMED_VOUCHER")
        need(_DRIVER.get("bound") is self.b and _DRIVER.get("armed_pid") == os.getpid(), "PREARMED_DRIVER_OWNERSHIP")
        need(plan.get("execution") == DRIVER_EXECUTION, "PREARMED_DRIVER_OWNERSHIP")
        need(ref(self.b.cfg["vouchers"],65536)==self.raw,"PREARMED_VOUCHER_CHANGED")
        spent=dict(schema_version="stage12_handoff_voucher_spent_v1",role=role,units=ROLES[role],
            voucher_sha256=sha(self.raw),configuration_sha256=sha(self.b.raw),
            plan_sha256=sha(canonical(plan)),launch_attempt_utc=z(now_utc()),no_refund=True,
            execution=DRIVER_EXECUTION,driver_pid=os.getpid())
        put(self.b.state/(role+".SPENT.record"),canonical(spent))
        return subprocess.Popen(plan["argv"],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)

    def finish(self,role,proc,timeout,stdout_max,stderr_max):
        end=time.monotonic()+timeout;buffers={proc.stdout.fileno():bytearray(),proc.stderr.fileno():bytearray()}
        streams={proc.stdout.fileno():proc.stdout,proc.stderr.fileno():proc.stderr}
        limits={proc.stdout.fileno():stdout_max,proc.stderr.fileno():stderr_max};failed=None
        try:
            while streams:
                need(time.monotonic()<end,"PREARMED_CHILD_TIMEOUT")
                readable,_,_=select.select(list(streams),[],[],min(.05,max(0,end-time.monotonic())))
                for fd in readable:
                    raw=os.read(fd,min(8192,limits[fd]-len(buffers[fd])+1))
                    if not raw:streams.pop(fd);continue
                    buffers[fd].extend(raw);need(len(buffers[fd])<=limits[fd],"PREARMED_CHILD_OUTPUT")
            code=proc.wait(timeout=max(.01,end-time.monotonic()))
        except BaseException:
            failed="TIMEOUT_OUTPUT_OR_IO_UNCERTAIN";proc.kill();code=proc.wait()
            raise
        finally:
            out=bytes(buffers[proc.stdout.fileno()]);err=bytes(buffers[proc.stderr.fileno()])
            put(self.b.state/(role+".stdout"),out[:stdout_max]);put(self.b.state/(role+".stderr"),err[:stderr_max])
            put(self.b.state/(role+".result.record"),canonical(dict(returncode=proc.returncode,
                stdout_sha256=sha(out[:stdout_max]),stderr_sha256=sha(err[:stderr_max]),uncertain=failed)))
        return code,out,err
    def run(self,plan):
        proc=self.start(plan)
        return self.finish(plan["role"],proc,plan["timeout"],plan["maximum_stdout"],plan["maximum_stderr"])

class Watch:
    def __init__(self,bound,vouchers):
        self.b=bound;self.plan=bound.watch_plan();self.proc=vouchers.start(self.plan)
        self.started=time.monotonic();self.buffer=bytearray();self.path=None;self.total=0;self.stderr=bytearray()
    def pump(self):
        need(time.monotonic()-self.started<LIMITS["watch_seconds"] and self.proc.poll() is None,"PREARMED_WATCH_ENDED")
        readable,_,_=select.select([self.proc.stdout,self.proc.stderr],[],[],LIMITS["poll_ms"]/1000)
        for stream in readable:
            block=os.read(stream.fileno(),8192);need(bool(block),"PREARMED_WATCH_ENDED")
            if stream is self.proc.stderr:
                self.stderr.extend(block);need(len(self.stderr)<=65536,"PREARMED_WATCH_OUTPUT");continue
            self.total+=len(block);need(self.total<=LIMITS["watch_total_bytes"],"PREARMED_WATCH_OUTPUT")
            self.buffer.extend(block);need(len(self.buffer)<=LIMITS["watch_line_bytes"]+8192,"PREARMED_WATCH_OUTPUT")
            while b"\n" in self.buffer:
                raw,_,rest=self.buffer.partition(b"\n");self.buffer=bytearray(rest)
                if not raw:continue
                if raw.startswith(b"==> ") and raw.endswith(b" <=="):
                    path=raw[4:-4].decode();need(path in set(self.b.names.values())|set(self.b.terminal_paths)|set(self.b.review_closed)|set(self.b.binder_closed),"PREARMED_STREAM_PATH")
                    self.path=path
                else:
                    need(self.path is not None,"PREARMED_STREAM_HEADER")
                    self.b.accept_line(self.path,raw+b"\n")
    def until(self,predicate,deadline):
        while True:
            need(now_utc()<deadline and now_utc()<utc(self.b.selected["valid_until"]),"PREARMED_CLIENT_DEADLINE")
            value=predicate()
            if value is not None:return value
            self.pump()
    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()
        put(self.b.state/"WATCH.result.record",canonical(dict(local_returncode=self.proc.returncode,
            observed_stream_bytes=self.total,remote_watch_end="NOT_INDEPENDENTLY_OBSERVED_NATIVE_TIMEOUT_BOUND_REMAINS",
            unused_capacity_refund=False)))

def checker_config(bound,destination,codec,*,evidence_use="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"):
    need(evidence_use in ("FRESH_SAME_ALLOCATION_FINDINGS_ONLY","HISTORICAL_REHEARSAL"),"PREARMED_CHECKER_INPUT")
    b=bound
    return dict(schema_version="stage12_task_factual_checker_input_v1",source_sha=SOURCE,
        source_dir=str(b.source),job_id=int(b.cfg["job_id"]),evidence_use=evidence_use,
        originals_dir=str(destination),first_start_codec=codec,selection=b.cfg["selection"],
        resource_selection=b.cfg["resource_selection"],resource_review=b.cfg["resource_review"],
        originals_tar=dict(path=str(b.state/"COLLECTOR_FETCH.stdout"),sha256=b.archive_sha),
        originals_inventory=dict(path=str(b.state/"COLLECTOR_INVENTORY.record"),sha256=b.inventory_sha))

def ready_marker(bound,name):
    path=bound.review_dir/name
    try:path.lstat()
    except FileNotFoundError:return None
    return read_original(path,8192)

def run(bound):
    need(bound.cfg["schema_version"] in (CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA) and bound.local_catalog is not None,"PREARMED_LOCAL_CATALOG_REQUIRED")
    b=bound
    driver_checkpoint("ARM",bound=b)
    _DRIVER["armed_pid"] = os.getpid()
    b.state.mkdir(mode=0o700);need(b.review_dir.is_dir() and stat.S_IMODE(b.review_dir.stat().st_mode)==0o700,"PREARMED_PRIVATE")
    v=Vouchers(b);watch=None
    put(b.state/"ORCHESTRATION_CONFIG.record",b.raw)
    put(b.state/"ARMED.record",canonical(dict(config_sha256=sha(b.raw),voucher_sha256=sha(v.raw),
        source_sha=SOURCE,job_id=b.cfg["job_id"],status="PREARMED_NOT_APPROVAL")))
    primary_failure=None
    try:
        driver_checkpoint("WATCH",bound=b)
        watch=Watch(b,v)
        ready=watch.until(b.readiness,min(now_utc()+timedelta(seconds=LIMITS["watch_seconds"]),utc(b.selected["valid_until"])))
        driver_checkpoint("COLLECTOR_READY",bound=b,status="OK")
        put(b.state/"COLLECTOR_READY.record",canonical(ready))
        plan=b.fetch_plan(ready);put(b.state/"COLLECTOR_FETCH.plan.record",canonical(plan))
        driver_checkpoint("COLLECTOR_FETCH",bound=b)
        code,raw,stderr=v.run(plan);need(code==0,"PREARMED_FETCH_UNCERTAIN")
        destination,request=prepare_checker_handoff(b,raw,stderr,ready)
        # Driver-owned seals are never offered as independent reviewer actions.
        driver_result(dict(status="FETCH_INVENTORY_READY_REQUEST_INDEPENDENT_CHECKER_AND_REVIEW",
            job_id=b.cfg["job_id"],checker_request=str(b.state/"CHECKER_REQUEST.record"),
            checker_config=str(b.state/"CHECKER_INPUT.record"),independent_report_destination=str(b.review_dir/"FACTUAL_CHECKER_FINDINGS.record")))
        cutoff=utc(ready["review_deadline_utc_earliest"])-timedelta(seconds=LIMITS["publication_seconds"])
        driver_checkpoint("WAIT_FACTUAL_DECISION",bound=b)
        watch.until(lambda:ready_marker(b,"FACTUAL_REVIEW_DECISION.record"),cutoff)
        seal_plan=mechanical_plan(b,"FACTUAL_SEAL");put(b.state/"FACTUAL_SEAL.plan.record",canonical(seal_plan))
        driver_checkpoint("FACTUAL_SEAL",bound=b)
        seal_factual(b.state/"ORCHESTRATION_CONFIG.record",cutoff_epoch_ns=int(cutoff.timestamp()*10**9))
        marker=ready_marker(b,"FACTUAL_REVIEW.ready.record");need(marker is not None,"PREARMED_FACTUAL_SEAL_UNCERTAIN")
        factual=read_original(b.review_dir/"BOOTSTRAP_REVIEW.record",8192)
        independent=read_original(b.review_dir/"FACTUAL_CHECKER_FINDINGS.record",2**20)
        plan=b.factual_plan(ready,marker,factual,independent);put(b.state/"FACTUAL_PUBLISH.plan.record",canonical(plan))
        local_factual_origin=time.monotonic_ns()
        factual_command_utc=now_utc()
        exact_client_end=factual_command_utc+timedelta(seconds=260)
        driver_checkpoint("FACTUAL_PUBLISH",bound=b)
        code,out,_=v.run(plan)
        need(code==0 and out==bytes.fromhex(plan["expected_stdout"]),"PREARMED_FACTUAL_PUBLICATION_UNCERTAIN")
        put(b.state/"FACTUAL_PUBLISHED.record",canonical(dict(source_sha=SOURCE,job_id=b.cfg["job_id"],
            factual_review_sha256=sha(factual),local_completed_utc=z(now_utc()),
            native_acceptance="NOT_OBSERVED_WAIT_REAL_REVIEW_CLOSE_AND_BINDER_START")))
        b.factual_published=True
        # Expected B construction belongs solely to independent exact-input review,
        # after the preceding factual publication has completed.
        driver_checkpoint("WAIT_BINDER",bound=b)
        watch.until(lambda:True if all(k in b.records for k in ("phase8","input","review_binding")) else None,
            min(utc(b.selected["valid_until"]),exact_client_end))
        driver_checkpoint("EXACT_PLAN",bound=b)
        exact_plan=b.helper.preparation_plan(b.selection_raw,selection_sha256=b.sha,source_sha=SOURCE,job_id=b.cfg["job_id"])
        driver_checkpoint("EXACT_PLAN",bound=b,status="OK")
        exact_plan.update(role="EXACT_FETCH",units=5,execution=DRIVER_EXECUTION,argv=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=20",b.cfg["host"],exact_plan["command"]],
            maximum_stdout=LIMITS["exact_tar_bytes"],maximum_stderr=8192,timeout=60)
        put(b.state/"EXACT_FETCH.plan.record",canonical(exact_plan))
        driver_checkpoint("EXACT_FETCH",bound=b)
        code,archive,_=v.run(exact_plan);need(code==0,"PREARMED_EXACT_FETCH_UNCERTAIN")
        driver_checkpoint("EXACT_EXTRACT",bound=b)
        exact_root,_exact_inventory=extract_exact(b,archive,exact_plan)
        driver_result(dict(status="ACTUAL_EXACT_INPUT_FETCH_READY_FOR_INDEPENDENT_EXPECTED_B_REVIEW",
            job_id=b.cfg["job_id"],originals_dir=str(exact_root)))
        p8=b.production_parse(b.records["phase8"])
        b.assurance.shape(p8,b.execution.ADMIN_BINDING_SCHEMA)
        boot=b.production_parse(b.records["bootstrap"])
        need(p8["role"]=="BINDER" and p8["phase_id"]==8 and p8["source_git_sha"]==SOURCE
             and p8["selection_sha256"]==b.resource_sha and p8["supervisor_context_sha256"]==sha(b.records["context"])
             and p8["scope_start_mono_ns"]<p8["deadline_mono_ns"]<=p8["scope_start_mono_ns"]+240_000_000_000,"PREARMED_BINDER_SCOPE")
        native_end=utc(boot["created_utc"])+timedelta(microseconds=(p8["deadline_mono_ns"]-boot["ended_mono_ns"])//1000)
        exact_cutoff=min(utc(b.selected["valid_until"]),exact_client_end,native_end)-timedelta(seconds=LIMITS["publication_seconds"])
        driver_checkpoint("EXACT_REQUEST",bound=b)
        exact_request=exact_checker_request(b,exact_root)
        driver_checkpoint("EXACT_REQUEST",bound=b,status="OK")
        put(b.state/"EXACT_CHECKER_REQUEST.record",canonical(exact_request))
        # Driver-owned exact seal follows only a pure reviewer decision.
        driver_checkpoint("WAIT_EXACT_DECISION",bound=b)
        watch.until(lambda:ready_marker(b,"EXACT_REVIEW_DECISION.record"),exact_cutoff)
        seal_plan=mechanical_plan(b,"EXACT_SEAL");put(b.state/"EXACT_SEAL.plan.record",canonical(seal_plan))
        driver_checkpoint("EXACT_SEAL",bound=b)
        seal_exact(b.state/"ORCHESTRATION_CONFIG.record",cutoff_epoch_ns=int(exact_cutoff.timestamp()*10**9))
        exact_marker=ready_marker(b,"EXACT_INPUT_RELEASE.ready.record");need(exact_marker is not None,"PREARMED_EXACT_SEAL_UNCERTAIN")
        marker_value=parse(exact_marker)
        need(set(marker_value)=={"schema_version","source_sha","selection_sha256","input_sha256","release_sha256",
            "release_bytes","substantive_checks","sealed_utc"} and marker_value["schema_version"]=="stage12_local_exact_review_ready_v1"
            and marker_value["source_sha"]==SOURCE and marker_value["selection_sha256"]==b.sha
            and marker_value["substantive_checks"]=="PASS_ALL_REQUIRED","PREARMED_EXACT_REVIEW")
        release=read_original(b.review_dir/"EXACT_INPUT_RELEASE.record",8192)
        need(sha(release)==marker_value["release_sha256"] and len(release)==marker_value["release_bytes"],"PREARMED_EXACT_REVIEW")
        rel=lambda key:Path(b.selected["paths"][key]).relative_to(b.root)
        originals=dict(input=read_original(exact_root/rel("input"),4*2**20),
            review_binding=read_original(exact_root/rel("binding")/"integration_review.binding.json",4*2**20),
            factual_review=factual,context=read_original(exact_root/rel("context"),65536),
            resource_selection=b.resource_raw,phase8_binding=read_original(exact_root/"binder_resources/admin_binding.record",8192))
        need(sha(originals["input"])==marker_value["input_sha256"],"PREARMED_EXACT_REVIEW")
        driver_checkpoint("EXACT_PUBLICATION_PLAN",bound=b)
        plan=b.helper.publication_plan(b.selection_raw,release,originals,selection_sha256=b.sha,source_sha=SOURCE,
            job_id=b.cfg["job_id"],reviewer_release_sha256=marker_value["release_sha256"],observed_utc=z(now_utc()),
            slurm_state="RUNNING",local_factual_command_start_ns=local_factual_origin,local_observed_ns=time.monotonic_ns(),existing_paths=())
        driver_checkpoint("EXACT_PUBLICATION_PLAN",bound=b,status="OK")
        guard="\n".join(["printf -v handoff_now '%(%s)T' -1",'test "$handoff_now" -lt '+str(int(exact_cutoff.timestamp()))])+"\n"
        plan["command"]=guard+plan["command"]
        plan.update(role="EXACT_PUBLISH",units=11,execution=DRIVER_EXECUTION,argv=["ssh","-T","-o","BatchMode=yes","-o","ConnectTimeout=20",b.cfg["host"],plan["command"]],
            timeout=LIMITS["publication_seconds"],maximum_stdout=8192,maximum_stderr=8192)
        put(b.state/"EXACT_PUBLISH.plan.record",canonical(plan))
        driver_checkpoint("EXACT_PUBLISH",bound=b)
        code,out,_=v.run(plan);receipt=b.helper.validate_publication_result(plan,returncode=code,stdout=out)
        put(b.state/"EXACT_PUBLISHED.record",canonical(receipt))
        return dict(status="CONTROL_HANDOFFS_PUBLISHED_NATIVE_B_PENDING",source_sha=SOURCE,job_id=b.cfg["job_id"],
            native_acceptance="REQUIRES_ACTUAL_BINDER_HANDOFF_AND_B_TERMINAL_VALIDATION")
    except BaseException as error:
        primary_failure=error
        retain_driver_failure(error,bound=b)
        attempt_driver_checkpoint("FAILURE",bound=b,status="FAILED",error=error)
        raise
    finally:
        if watch is not None:
            attempt_driver_checkpoint("WATCH_STOP",bound=b)
            try:
                watch.stop()
            except BaseException as cleanup_error:
                retain_driver_failure(cleanup_error,bound=b,cleanup=True)
                if primary_failure is None:retain_driver_failure(cleanup_error,bound=b)
                attempt_driver_checkpoint("WATCH_STOP",bound=b,status="FAILED",error=cleanup_error)
                if primary_failure is None:raise
            else:
                attempt_driver_checkpoint("WATCH_STOP",bound=b,status="OK")

def extract_exact(bound,raw,plan):
    # Closed selected directories include implicit parents omitted by GNU tar.
    need(0<len(raw)<=LIMITS["exact_tar_bytes"],"PREARMED_EXACT_ARCHIVE")
    root=bound.state/"exact-input-originals"
    fixed,binding,directories=exact_archive_layout(bound,plan["expected_relative_roots"])
    inventory=[];seen=set();files=set();headers=set();items=[];total=0
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
        for item in archive:
            rel=archive_relative(item,"PREARMED_EXACT_ARCHIVE")
            need(rel not in seen and len(seen)<LIMITS["exact_files"]+len(directories),"PREARMED_EXACT_ARCHIVE")
            seen.add(rel)
            if item.isdir():
                need(rel in directories and item.mode==0o700
                     and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"],"PREARMED_EXACT_ARCHIVE")
                headers.add(rel);continue
            need(item.isfile() and rel not in directories
                 and (rel in fixed or rel.parent in {binding,binding/"resource_evidence"})
                 and archive_parents({rel})<=directories and item.mode==0o600
                 and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"]
                 and 0<=item.size<=4*2**20 and len(files)<LIMITS["exact_files"],"PREARMED_EXACT_ARCHIVE")
            total+=item.size;need(total<=LIMITS["exact_tar_bytes"],"PREARMED_EXACT_ARCHIVE")
            files.add(rel);items.append((rel,item))
        effective=archive_parents(files)|{binding}
        need(fixed<=files and binding in (headers|archive_parents(files))
             and effective<=directories and headers<=effective,"PREARMED_EXACT_ARCHIVE")
        root.mkdir(mode=0o700)
        for rel in sorted(effective,key=lambda p:(len(p.parts),str(p))):
            (root/rel).mkdir(mode=0o700)
        for rel,item in items:
            body=archive.extractfile(item).read(item.size+1)
            need(len(body)==item.size,"PREARMED_EXACT_ARCHIVE")
            put(root/rel,body)
            inventory.append(dict(path=str(rel),bytes=len(body),sha256=sha(body),
                original_mode=item.mode,original_uid=item.uid,original_gid=item.gid))
    exact_copied_tree(root,files,effective)
    need(read_original(bound.state/"EXACT_FETCH.stdout",LIMITS["exact_tar_bytes"])==raw,"PREARMED_EXACT_FETCH_CHANGED")
    put(bound.state/"EXACT_INPUT_INVENTORY.record",canonical(inventory))
    return root,inventory

def collector_file_limit(bound, rel, ready):
    text=str(rel)
    fixed={"bootstrap/bootstrap.record":4*2**20,"bootstrap/manifest.record":65536,
        "context.record":65536,"collector.wait.record":65536,"collector.handoff.record":65536,
        "review_resources/admin_binding.record":65536,"review_resources/bootstrap_prefix.record":65536}
    for name in ("admin_binding","bootstrap_prefix"):
        fixed["collector_resources/"+name+".record"]=65536
    for name in ("preopening","opener_return","monitor_terminal","worker_validation","supervisor_terminal"):
        fixed["collector_resources/"+name+".record"]=8192
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
    compiled=accounting.validate_inventory(bound.selected["accounting_inventory"])
    stream=next(row for row in compiled["monitor_streams"] if row["phase_id"]==6)
    stage=next(row for row in bound.resource["limits"]["stages"] if row["id"]==6)
    rows=stream["maximum_rows"]
    need(stream["deadline_ms"]==stage["deadline_ms"]
         and bound.resource["monitor"]["period_ms"]==500
         and rows<=bound.resource["limits"]["monitor_rows"],"PREARMED_ARCHIVE_MEMBER")
    fixed["collector_resources/observations.bin"]=rows*1024
    if text in fixed:return fixed[text]
    if re.fullmatch(r"collector_resources/originals/[0-9a-f]{64}\.record",text):return 15360
    if text=="review_resources/originals/"+ready["first_start_original_sha256"]+".record":return 15360
    raise RuntimeError("PREARMED_ARCHIVE_MEMBER")

def pure_configuration(config_path):
    """Metadata-only pre-tool validation. Never imports production modules."""
    raw=read_original(config_path,4*2**20);cfg=parse(raw)
    catalog_selected=cfg.get("schema_version") in (CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA)
    need(set(cfg)==(CONFIG_KEYS|{"local_record_catalog"} if catalog_selected else CONFIG_KEYS)
         and cfg["schema_version"] in (SCHEMA,CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA) and cfg["source_sha"]==SOURCE
         and cfg["limits"]==LIMITS and cfg["host"]=="goethe"
         and type(cfg["job_id"]) is str and re.fullmatch(r"[1-9][0-9]{0,19}",cfg["job_id"]),"PREARMED_CONFIG")
    voucher_raw=ref(cfg["vouchers"],65536);voucher=parse(voucher_raw)
    selection_raw=ref(cfg["selection"],4*2**20);selection=json.loads(selection_raw)
    need((cfg["schema_version"]==SIMPLE_CATALOG_SCHEMA)==
         (selection.get("rep_admin_budget_adoption",{}).get("window",{}).get("version")==
          "SYNTHETIC_AND_COLLECTION_OPERATING_WINDOW_r4"),"PREARMED_CONFIG")
    resource_raw=ref(cfg["resource_selection"],65536)
    validate_role_ownership(voucher,cfg,sha(selection_raw),sha(resource_raw),
                            sha(canonical({k:v for k,v in cfg.items() if k!="vouchers"})),
                            selection["rep_admin_budget_adoption"]["window"]["owner_authority_sha256"]
                            if cfg["schema_version"]==SIMPLE_CATALOG_SCHEMA else None)
    need(selection["source_sha"]==SOURCE,"PREARMED_VOUCHER")
    return cfg,raw,voucher_raw

def _role_request(cfg,config_raw,role):
    need(role in REVIEWER_ROLES,"PREARMED_DRIVER_OWNERSHIP")
    state=absolute(cfg["state_dir"]);review=absolute(cfg["review_dir"])
    if role=="CHECKER":
        script=cfg["checker_script"];input_path=state/"CHECKER_INPUT.record";report=review/"FACTUAL_CHECKER_FINDINGS.record"
    else:
        script=cfg["exact_checker_script"];input_path=state/"EXACT_CHECKER_INPUT.record";report=review/"EXACT_CHECKER_FINDINGS.record"
    argv=[cfg["python_executable"],"-B",script["path"],"--config",str(input_path),"--report",str(report)]
    script_raw=ref(script,256*1024,private=False);input_raw=read_original(input_path,4*2**20)
    return dict(schema_version="stage12_independent_review_cli_request_v2",role=role,units=2,
        argv=argv,shell_command="exec "+shlex.join(argv),source_sha=SOURCE,job_id=cfg["job_id"],
        selection_sha256=cfg["selection"]["sha256"],resource_selection_sha256=cfg["resource_selection"]["sha256"],
        script_sha256=sha(script_raw),checker_input_sha256=sha(input_raw),configuration_sha256=sha(config_raw),
        report_path=str(report),voucher_sha256=cfg["vouchers"]["sha256"],execution="INDEPENDENT_REVIEWER")


def independent_request(cfg,config_raw,role):
    need(role in REVIEWER_ROLES, "PREARMED_DRIVER_OWNERSHIP")
    request = _role_request(cfg,config_raw,role)
    need(request["execution"] == "INDEPENDENT_REVIEWER", "PREARMED_DRIVER_OWNERSHIP")
    return request


def checker_request(bound,checker_path,*,evidence_use="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"):
    need(evidence_use in ("FRESH_SAME_ALLOCATION_FINDINGS_ONLY","HISTORICAL_REHEARSAL"),"PREARMED_CHECKER_INPUT")
    cfg=parse(read_original(checker_path,4*2**20))
    need(type(cfg["job_id"]) is int and cfg["job_id"]==int(bound.cfg["job_id"])
         and cfg["evidence_use"]==evidence_use,"PREARMED_CHECKER_INPUT")
    return independent_request(bound.cfg,bound.raw,"CHECKER")

def claim_independent(config_path,role):
    """Pure pre-tool SPENT claim for the two reviewer-run fixed checker CLIs."""
    need(role in ("CHECKER","EXACT_CHECKER"),"PREARMED_REVIEW_ROLE")
    cfg,raw,voucher_raw=pure_configuration(config_path)
    state=absolute(cfg["state_dir"]);request_raw=read_original(state/(role+"_REQUEST.record"),8192);request=parse(request_raw)
    need(request==independent_request(cfg,raw,role) and request["execution"]=="INDEPENDENT_REVIEWER","PREARMED_CHECKER_REQUEST")
    spent=dict(schema_version="stage12_handoff_voucher_spent_v1",role=role,units=2,
        voucher_sha256=sha(voucher_raw),configuration_sha256=sha(raw),plan_sha256=sha(request_raw),
        launch_attempt_utc=z(now_utc()),no_refund=True)
    put(state/(role+".SPENT.record"),canonical(spent))
    return dict(shell_command=request["shell_command"],max_external_units=2,
        spent_sha256=sha(canonical(spent)),report_path=request["report_path"])

def complete_independent(config_path,role,*,returncode):
    """Pure record of the actual tool outcome; contains no approval."""
    need(role in ("CHECKER","EXACT_CHECKER"),"PREARMED_REVIEW_ROLE")
    cfg,raw,_=pure_configuration(config_path);state=absolute(cfg["state_dir"])
    request_raw=read_original(state/(role+"_REQUEST.record"),8192);request=parse(request_raw)
    spent_raw=read_original(state/(role+".SPENT.record"),8192);spent=parse(spent_raw)
    need(spent["role"]==role and spent["units"]==2 and spent["plan_sha256"]==sha(request_raw)
         and spent["configuration_sha256"]==sha(raw),"PREARMED_CHECKER_REQUEST")
    report_raw=read_original(absolute(request["report_path"]),2**20);report=parse(report_raw)
    need(type(returncode) is int and returncode==0 and report["required_checks"]=="ALL_COMPLETED"
         and report["authority"]=="NONE_FINDINGS_ONLY"
         and report["evidence_use"]=="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"
         and report["checker_input_sha256"]==request["checker_input_sha256"]
         and report["checker_sha256"]==request["script_sha256"],"PREARMED_CHECKER_FAILED")
    result=dict(schema_version="stage12_independent_checker_completed_v1",role=role,returncode=returncode,
        report_sha256=sha(report_raw),report_bytes=len(report_raw),spent_sha256=sha(spent_raw),
        checker_input_sha256=request["checker_input_sha256"],request_sha256=sha(request_raw),
        observed_utc=z(now_utc()),approval="NONE_FINDINGS_ONLY_INDEPENDENT_REVIEWER_DECISION_REQUIRED")
    put(state/(role+".completed.record"),canonical(result))
    return result

def atomic_local(source,destination):
    check_seal_write(destination)
    # Same native NOREPLACE operations as accepted s09_reference_io, without
    # importing pipeline modules into the metadata-only reviewer's resident.
    import ctypes
    source=artifact_path(source);destination=artifact_path(destination)
    need(source.parent==destination.parent and not os.path.lexists(destination),"PREARMED_TARGET_EXISTS")
    ancestors=ancestor_snapshot(destination)
    parent_before=destination.parent.lstat()
    need(stat.S_IMODE(parent_before.st_mode)==0o700 and parent_before.st_uid==os.geteuid(),"PREARMED_PRIVATE")
    source_before=source.lstat()
    need(stat.S_ISREG(source_before.st_mode) and stat.S_IMODE(source_before.st_mode)==0o600
         and source_before.st_nlink==1 and source_before.st_uid==os.geteuid(),"PREARMED_PRIVATE")
    library=ctypes.CDLL(None,use_errno=True)
    if sys.platform=="linux":
        function=library.renameat2;function.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
        arguments=(-100,os.fsencode(source),-100,os.fsencode(destination),1)
    elif sys.platform=="darwin":
        function=library.renamex_np;function.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
        arguments=(os.fsencode(source),os.fsencode(destination),4)
    else:raise RuntimeError("PREARMED_ATOMIC_UNSUPPORTED")
    function.restype=ctypes.c_int
    need(ancestor_snapshot(destination)==ancestors,"PREARMED_PARENT_CHANGED")
    need(function(*arguments)==0,"PREARMED_ATOMIC_UNCERTAIN")
    need(ancestor_snapshot(destination)==ancestors and identity(destination.lstat())[:-1]==identity(source_before)[:-1]
         and not os.path.lexists(source),"PREARMED_ATOMIC_UNCERTAIN")
    fd=os.open(destination.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def publish_private_ready(path,raw):
    temporary=path.with_name(path.name+".tmp-"+sha(raw)[:12])
    put(temporary,raw);atomic_local(temporary,path)
    need(read_original(path,len(raw))==raw,"PREARMED_ATOMIC_UNCERTAIN")

FACT_DECISION_KEYS={"schema_version","disposition","checker_report_sha256","checker_input_sha256",
    "source_sha","job_id","selection_sha256","resource_selection_sha256","collector_ready_sha256",
    "originals_tar_sha256","originals_inventory_sha256","reviewed_utc"}

def write_decision(config_path,role,decision):
    """Publish only the supplied closed reviewer decision; never derives PASS."""
    cfg,_,_=pure_configuration(config_path)
    need(role in ("FACTUAL_SEAL","EXACT_SEAL") and type(decision) is dict,"PREARMED_REVIEW_DECISION")
    if role=="FACTUAL_SEAL":
        keys=FACT_DECISION_KEYS;schema="stage12_independent_factual_decision_v1";name="FACTUAL_REVIEW_DECISION.record"
    else:
        keys={"schema_version","disposition","findings_sha256","checker_input_sha256","source_sha","job_id",
            "selection_sha256","input_sha256","review_binding_sha256","resource_selection_sha256","factual_review_sha256","reviewed_utc"}
        schema="stage12_independent_exact_input_decision_v1";name="EXACT_REVIEW_DECISION.record"
    need(set(decision)==keys and decision["schema_version"]==schema
         and decision["disposition"]=="PASS_ALL_REQUIRED" and decision["source_sha"]==SOURCE
         and decision["job_id"]==cfg["job_id"] and decision["selection_sha256"]==cfg["selection"]["sha256"]
         and decision["resource_selection_sha256"]==cfg["resource_selection"]["sha256"],"PREARMED_REVIEW_DECISION")
    utc(decision["reviewed_utc"])
    path=absolute(cfg["review_dir"])/name;publish_private_ready(path,canonical(decision))
    return dict(path=str(path),sha256=sha(canonical(decision)),status="SUPPLIED_REVIEWER_DECISION_PUBLISHED")


def claim_driver_slot(config_path, role, *, cutoff_epoch_ns=None):
    global _SEAL_AUTHORIZATION
    entered=time.monotonic_ns()
    need(role in ("FACTUAL_SEAL", "EXACT_SEAL") and type(cutoff_epoch_ns) is int, "PREARMED_DRIVER_OWNERSHIP")
    owner=_DRIVER.get("bound")
    need(owner is not None and _DRIVER.get("armed_pid")==os.getpid(), "PREARMED_DRIVER_OWNERSHIP")
    cfg,raw,_=pure_configuration(config_path);state=absolute(cfg["state_dir"])
    need(raw==owner.raw and cfg["state_dir"]==str(owner.state), "PREARMED_DRIVER_OWNERSHIP")
    plan_raw=read_original(state/(role+".plan.record"),16384);plan=parse(plan_raw)
    need(plan==mechanical_plan(owner,role) and plan["execution"]==DRIVER_EXECUTION
        and plan["configuration_sha256"]==sha(raw), "PREARMED_DRIVER_OWNERSHIP")
    clock=dict(end_mono_ns=entered+45*10**9,end_epoch_ns=min(cutoff_epoch_ns,int(utc(owner.selected["valid_until"]).timestamp()*10**9)))
    check_seal_clock(clock)
    claim_path=state/(role+".DRIVER_CLAIM.record")
    claim_raw=canonical(dict(role=role,execution=DRIVER_EXECUTION,external_units=0,
        plan_sha256=sha(plan_raw),pid=os.getpid(),configuration_sha256=sha(raw)))
    put(claim_path,claim_raw)
    _SEAL_AUTHORIZATION=dict(role=role,pid=os.getpid(),review_dir=cfg["review_dir"],claim_path=str(claim_path),claim_sha256=sha(claim_raw),**clock)
    check_seal_clock(_SEAL_AUTHORIZATION)
    return cfg


def seal_exact(config_path, *, cutoff_epoch_ns=None):
    cfg=claim_driver_slot(config_path,"EXACT_SEAL",cutoff_epoch_ns=cutoff_epoch_ns)
    checker=load_script(cfg["exact_checker_script"]["path"],"driver_owned_exact_sealer")
    checker.h._SEAL_AUTHORIZATION = dict(_SEAL_AUTHORIZATION)
    state=absolute(cfg["state_dir"]);review=absolute(cfg["review_dir"])
    result=checker.seal(state/"EXACT_CHECKER_INPUT.record", review/"EXACT_CHECKER_FINDINGS.record", review/"EXACT_REVIEW_DECISION.record")
    check_seal_clock(_SEAL_AUTHORIZATION)
    return result

def seal_factual(config_path, *, cutoff_epoch_ns=None):
    claim_driver_slot(config_path, "FACTUAL_SEAL",cutoff_epoch_ns=cutoff_epoch_ns)
    b=Bound(read_original(config_path,4*2**20));state=b.state;review=b.review_dir
    decision_raw=read_original(review/"FACTUAL_REVIEW_DECISION.record",8192);decision=parse(decision_raw)
    findings_raw=read_original(review/"FACTUAL_CHECKER_FINDINGS.record",2**20);findings=parse(findings_raw)
    completion=parse(read_original(state/"CHECKER.completed.record",8192))
    need(set(decision)==FACT_DECISION_KEYS and decision["schema_version"]=="stage12_independent_factual_decision_v1"
         and decision["disposition"]=="PASS_ALL_REQUIRED"
         and decision["checker_report_sha256"]==sha(findings_raw)
         and decision["checker_input_sha256"]==findings["checker_input_sha256"]
         and completion["report_sha256"]==sha(findings_raw) and completion["returncode"]==0,"PREARMED_REVIEW_DECISION")
    ready=parse(read_original(state/"COLLECTOR_READY.record",2**20))
    b.records={key:read_original(state/"collector-originals"/Path(path).relative_to(b.root),4*2**20)
               for key,path in b.names.items() if key in b.required}
    need(b.readiness()==ready,"PREARMED_REVIEW_DECISION")
    b.archive_sha=sha(read_original(state/"COLLECTOR_FETCH.stdout",LIMITS["collector_tar_bytes"]))
    b.inventory_sha=sha(read_original(state/"COLLECTOR_INVENTORY.record",2**20))
    expected={"source_sha":SOURCE,"job_id":b.cfg["job_id"],"selection_sha256":b.sha,
        "resource_selection_sha256":b.resource_sha,"collector_ready_sha256":sha(canonical(ready)),
        "originals_tar_sha256":b.archive_sha,"originals_inventory_sha256":b.inventory_sha}
    need(all(decision[k]==v for k,v in expected.items()),"PREARMED_REVIEW_DECISION")
    factual=dict(schema_version="stage12_ra_g1_independent_bootstrap_review_v1",disposition="PASS",
        source_sha=SOURCE,job_id=int(b.cfg["job_id"]),selection_sha256=b.sha,resource_selection_sha256=b.resource_sha,
        bootstrap_sha256=ready["raw_sha256"]["bootstrap"],bootstrap_manifest_sha256=ready["raw_sha256"]["manifest"],
        collector_wait_sha256=ready["raw_sha256"]["wait"],collector_handoff_sha256=ready["raw_sha256"]["handoff"],
        originals_archive_sha256=b.archive_sha,originals_inventory_sha256=b.inventory_sha,
        independent_report_sha256=sha(findings_raw),independent_decision_sha256=sha(decision_raw),
        exact_B_input_release="NOT_ISSUED",native_physical_maximum="NOT_PROVEN",
        review_scope="INDEPENDENT_FACTUAL_ORIGINALS_NOT_HARD_CONTAINMENT")
    factual_raw=b.controller.canonical(factual)
    marker=dict(schema_version=READY,job_id=b.cfg["job_id"],source_sha=SOURCE,selection_sha256=b.sha,
        resource_selection_sha256=b.resource_sha,collector_ready_sha256=sha(canonical(ready)),
        originals_tar_sha256=b.archive_sha,originals_inventory_sha256=b.inventory_sha,
        checker_report_sha256=sha(findings_raw),reviewer_decision_sha256=sha(decision_raw),
        factual_review_sha256=sha(factual_raw),factual_review_bytes=len(factual_raw),
        substantive_checks="PASS_ALL_REQUIRED",sealed_utc=z(now_utc()))
    b.factual_plan(ready,canonical(marker),factual_raw,findings_raw)
    put(review/"BOOTSTRAP_REVIEW.record",factual_raw)
    publish_private_ready(review/"FACTUAL_REVIEW.ready.record",canonical(marker))
    check_seal_clock(_SEAL_AUTHORIZATION)
    return dict(status="REVIEWER_DECISION_MECHANICALLY_SEALED_NOT_NATIVE_ACCEPTANCE",
        factual_review_sha256=sha(factual_raw),independent_decision_sha256=sha(decision_raw))

def mechanical_plan(bound,role):
    # Validate the current reviewer decision before spending a sealer slot.
    need(role in ("FACTUAL_SEAL","EXACT_SEAL"),"PREARMED_REVIEW_ROLE")
    factual=role=="FACTUAL_SEAL"
    decision=parse(read_original(bound.review_dir/("FACTUAL_REVIEW_DECISION.record" if factual else "EXACT_REVIEW_DECISION.record"),8192))
    report_raw=read_original(bound.review_dir/("FACTUAL_CHECKER_FINDINGS.record" if factual else "EXACT_CHECKER_FINDINGS.record"),2**20)
    report=parse(report_raw)
    keys=FACT_DECISION_KEYS if factual else {"schema_version","disposition","findings_sha256","checker_input_sha256","source_sha","job_id","selection_sha256","input_sha256","review_binding_sha256","resource_selection_sha256","factual_review_sha256","reviewed_utc"}
    schema="stage12_independent_factual_decision_v1" if factual else "stage12_independent_exact_input_decision_v1"
    need(set(decision)==keys and decision["schema_version"]==schema
         and decision["disposition"]=="PASS_ALL_REQUIRED" and decision["source_sha"]==SOURCE
         and decision["job_id"]==bound.cfg["job_id"] and decision["selection_sha256"]==bound.sha
         and decision["resource_selection_sha256"]==bound.resource_sha
         and decision["checker_report_sha256" if factual else "findings_sha256"]==sha(report_raw)
         and decision["checker_input_sha256"]==report["checker_input_sha256"]
         and report["required_checks"]=="ALL_COMPLETED" and report["authority"]=="NONE_FINDINGS_ONLY"
         and report["evidence_use"]=="FRESH_SAME_ALLOCATION_FINDINGS_ONLY","PREARMED_REVIEW_DECISION")
    checker_role="CHECKER" if factual else "EXACT_CHECKER"
    completion=parse(read_original(bound.state/(checker_role+".completed.record"),8192))
    need(completion["returncode"]==0 and completion["report_sha256"]==sha(report_raw),"PREARMED_REVIEW_DECISION")
    need(utc(decision["reviewed_utc"])<=now_utc(),"PREARMED_REVIEW_DECISION")
    return dict(schema_version="stage12_single_driver_mechanical_seal_v2",role=role,
        execution=DRIVER_EXECUTION,external_units=0,configuration_sha256=sha(bound.raw),
        source_sha=SOURCE,job_id=bound.cfg["job_id"],selection_sha256=bound.sha,
        resource_selection_sha256=bound.resource_sha,decision_sha256=sha(canonical(decision)),
        findings_sha256=sha(report_raw))


def exact_checker_request(bound, exact_root):
    b=bound
    need(b.cfg["schema_version"] in (CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA) and b.local_catalog is not None,"PREARMED_LOCAL_CATALOG_REQUIRED")
    config=dict(schema_version=CATALOG_EXACT_SCHEMA,local_record_catalog=b.cfg["local_record_catalog"],
        orchestration_config=dict(path=str(b.state/"ORCHESTRATION_CONFIG.record"),sha256=sha(b.raw)),
        collector_checker_config=dict(path=str(b.state/"CHECKER_INPUT.record"),sha256=sha(read_original(b.state/"CHECKER_INPUT.record",4*2**20))),
        input_dir=str(exact_root),
        input_archive=dict(path=str(b.state/"EXACT_FETCH.stdout"),sha256=sha(read_original(b.state/"EXACT_FETCH.stdout",LIMITS["exact_tar_bytes"]))),
        input_inventory=dict(path=str(b.state/"EXACT_INPUT_INVENTORY.record"),sha256=sha(read_original(b.state/"EXACT_INPUT_INVENTORY.record",2**20))),
        factual_review=dict(path=str(b.review_dir/"BOOTSTRAP_REVIEW.record"),sha256=sha(read_original(b.review_dir/"BOOTSTRAP_REVIEW.record",8192))),
        factual_publication_result=dict(path=str(b.state/"FACTUAL_PUBLISH.result.record"),sha256=sha(read_original(b.state/"FACTUAL_PUBLISH.result.record",8192))),
        evidence_use="FRESH_SAME_ALLOCATION_FINDINGS_ONLY")
    path=b.state/"EXACT_CHECKER_INPUT.record";put(path,canonical(config))
    return independent_request(b.cfg,b.raw,"EXACT_CHECKER")

DRIVER_OPERATIONS=("CONFIG_READ","STATIC_VALIDATION","PREFLIGHT","ARM","WATCH","COLLECTOR_READY","COLLECTOR_FETCH","COLLECTOR_EXTRACT","CHECKER_REQUEST","WAIT_FACTUAL_DECISION","FACTUAL_SEAL","FACTUAL_PUBLISH","WAIT_BINDER","EXACT_PLAN","EXACT_FETCH","EXACT_EXTRACT","EXACT_REQUEST","WAIT_EXACT_DECISION","EXACT_SEAL","EXACT_PUBLICATION_PLAN","EXACT_PUBLISH","WATCH_STOP","DRIVER_EXIT","FAILURE")
SAFE_DRIVER_CODES=LOCAL_CATALOG_CODES | frozenset(('RA_G1_HANDOFF_BINDING','RA_G1_HANDOFF_DEADLINE','RA_G1_HANDOFF_INELIGIBLE','RA_G1_HANDOFF_JOB','RA_G1_HANDOFF_LOCAL_TIMELINE','RA_G1_HANDOFF_ORIGINAL','RA_G1_HANDOFF_PATH','RA_G1_HANDOFF_POLICY','RA_G1_HANDOFF_PUBLICATION_UNCERTAIN','RA_G1_HANDOFF_SEALED_BYTES','RA_G1_HANDOFF_WINDOW','PREARMED_DRIVER_OWNERSHIP', 'PREARMED_', 'PREARMED_ANCESTOR', 'PREARMED_ANCESTOR_BOUND', 'PREARMED_ARCHIVE', 'PREARMED_ARCHIVE_MEMBER', 'PREARMED_ARTIFACT_PATH', 'PREARMED_ATOMIC_UNCERTAIN', 'PREARMED_ATOMIC_UNSUPPORTED', 'PREARMED_BINDER_CLOSED', 'PREARMED_BINDER_SCOPE', 'PREARMED_BOOTSTRAP', 'PREARMED_CANONICAL', 'PREARMED_CANONICAL_PRODUCTION', 'PREARMED_CHANGED_CONTROL', 'PREARMED_CHECKER_FAILED', 'PREARMED_CHECKER_INPUT', 'PREARMED_CHECKER_REQUEST', 'PREARMED_CHECKER_SCHEMA', 'PREARMED_CHILD_OUTPUT', 'PREARMED_CHILD_TIMEOUT', 'PREARMED_CLIENT_DEADLINE', 'PREARMED_CLOCK', 'PREARMED_COLLECTOR', 'PREARMED_COLLECTOR_CLOSURE', 'PREARMED_CONFIG', 'PREARMED_CONTEXT', 'PREARMED_DIAGNOSTIC_LIMIT', 'PREARMED_EXACT_ARCHIVE', 'PREARMED_EXACT_FETCH_CHANGED', 'PREARMED_EXACT_FETCH_UNCERTAIN', 'PREARMED_EXACT_INVENTORY', 'PREARMED_EXACT_REVIEW', 'PREARMED_EXACT_SEAL_UNCERTAIN', 'PREARMED_FACTUAL_PUBLICATION_UNCERTAIN', 'PREARMED_FACTUAL_SEAL_UNCERTAIN', 'PREARMED_FAILED_UNCLASSIFIED', 'PREARMED_FETCH_CHANGED', 'PREARMED_FETCH_FRAMING', 'PREARMED_FETCH_UNCERTAIN', 'PREARMED_HANDOFF_BINDING', 'PREARMED_JOB', 'PREARMED_NATIVE_TERMINAL', 'PREARMED_NOT_APPROVAL', 'PREARMED_ORIGINAL', 'PREARMED_ORIGINALS', 'PREARMED_PARENT_CHANGED', 'PREARMED_PATH', 'PREARMED_PREFLIGHT_STAGE', 'PREARMED_PRIVATE', 'PREARMED_REFERENCE', 'PREARMED_REFERENCE_CHANGED', 'PREARMED_RESOURCE', 'PREARMED_RESOURCE_REVIEW', 'PREARMED_REVIEW_BINDING', 'PREARMED_REVIEW_CLOSED', 'PREARMED_REVIEW_DECISION', 'PREARMED_REVIEW_INCOMPLETE', 'PREARMED_REVIEW_LATE', 'PREARMED_REVIEW_ROLE', 'PREARMED_REVIEW_START', 'PREARMED_SHELL_ARGUMENTS', 'PREARMED_SHORT_READ', 'PREARMED_SOURCE', 'PREARMED_SOURCE_BOUND', 'PREARMED_STREAM_HEADER', 'PREARMED_STREAM_PATH', 'PREARMED_STREAM_RECORD', 'PREARMED_TARGET_EXISTS', 'PREARMED_UNISSUED_FIELDS', 'PREARMED_VOUCHER', 'PREARMED_VOUCHER_CHANGED', 'PREARMED_WATCH_ENDED', 'PREARMED_WATCH_OUTPUT', 'PREARMED_WRITE_UNCERTAIN', 'RA_G1_ACCOUNTING_CHANGED', 'RA_G1_ACCOUNTING_INVALID', 'RA_G1_FIELDS'))
_DRIVER={"seq":0,"bytes":0,"operation":"CONFIG_READ","bound":None,"first_failure":None,"cleanup_failure":None,"diagnostics_uncertain":False,"first_diagnostic_failure":None}


def safe_driver_error(error):
    unknown=dict(family="UNKNOWN",code="UNCLASSIFIED",field=None,errno=None)
    try:
        kind=type(error)
        if kind is KeyError:
            args=BaseException.args.__get__(error)
            names={"monitor_rows":"MONITOR_ROWS","maximum_rows":"MAXIMUM_ROWS","deadline_ms":"DEADLINE_MS","accounting_inventory":"ACCOUNTING_INVENTORY"}
            return dict(family="KEY_ERROR",code="MISSING_REQUIRED_FIELD",field=names.get(args[0]) if len(args)==1 and type(args[0]) is str else None,errno=None)
        if kind is RuntimeError:
            args=BaseException.args.__get__(error)
            if len(args)==1 and type(args[0]) is str and args[0] in SAFE_DRIVER_CODES:
                return dict(family="CLOSED_CONTRACT_CODE",code=args[0],field=None,errno=None)
        # Identity dispatch never invokes an unsupported metaclass equality,
        # hash, descriptor, string conversion or instance getter.
        if any(kind is native for native in (OSError,FileNotFoundError,PermissionError,FileExistsError,NotADirectoryError,IsADirectoryError)):
            number=OSError.errno.__get__(error)
            return dict(family="OS_ERROR",code="OS_ERROR",field=None,errno=number if type(number) is int and 0<=number<=4095 else None)
    except BaseException:
        return unknown
    return unknown


def driver_presence(bound):
    names={"checker_request":"CHECKER_REQUEST.record","checker_spent":"CHECKER.SPENT.record","checker_completed":"CHECKER.completed.record","factual_published":"FACTUAL_PUBLISHED.record","exact_checker_request":"EXACT_CHECKER_REQUEST.record"}
    review={"checker_findings":"FACTUAL_CHECKER_FINDINGS.record","reviewer_decision":"FACTUAL_REVIEW_DECISION.record","factual_ready":"FACTUAL_REVIEW.ready.record","exact_release":"EXACT_INPUT_RELEASE.record"}
    if bound is None:return {key:"NOT_CHECKED" for key in (*names,*review)}
    if bound.unissued:return {key:"DEFERRED_UNISSUED" for key in (*names,*review)}
    result={}
    for keys,root in ((names,bound.state),(review,bound.review_dir)):
        for key,name in keys.items():
            try:artifact_path(root/name).lstat();result[key]="PRESENT"
            except FileNotFoundError:result[key]="ABSENT"
            except Exception:result[key]="UNKNOWN"
    return result


def retain_driver_failure(error,*,bound=None,cleanup=False):
    # Store only primitive unknown state BEFORE classification/clock/output.
    # The actual work exception remains local to run's re-raise, never here.
    if bound is not None:_DRIVER["bound"]=bound
    key="cleanup_failure" if cleanup else "first_failure"
    if _DRIVER[key] is not None:return _DRIVER[key]
    operation="WATCH_STOP" if cleanup else _DRIVER["operation"]
    value=dict(operation=operation,safe_error=dict(family="UNKNOWN",code="UNCLASSIFIED",field=None,errno=None),actual_mono_ns=None)
    _DRIVER[key]=value
    try:value["safe_error"]=safe_driver_error(error)
    except BaseException:_DRIVER["diagnostics_uncertain"]=True
    try:value["actual_mono_ns"]=time.monotonic_ns()
    except BaseException:_DRIVER["diagnostics_uncertain"]=True
    return value


def attempt_driver_checkpoint(operation,*,bound=None,status="ENTER",error=None):
    try:return driver_checkpoint(operation,bound=bound,status=status,error=error)
    except BaseException as diagnostic_error:
        _DRIVER["diagnostics_uncertain"]=True
        if _DRIVER["first_diagnostic_failure"] is None:
            _DRIVER["first_diagnostic_failure"]=dict(stage="CHECKPOINT",safe_error=dict(family="UNKNOWN",code="UNCLASSIFIED",field=None,errno=None))
            try:_DRIVER["first_diagnostic_failure"]["safe_error"]=safe_driver_error(diagnostic_error)
            except BaseException:pass
        # The possibly partial attempt remains charged; it is never retried.
        return None


def driver_checkpoint(operation,*,bound=None,status="ENTER",error=None):
    if error is not None:retain_driver_failure(error,bound=bound)
    need(operation in DRIVER_OPERATIONS and status in ("ENTER","OK","FAILED"),"PREARMED_DIAGNOSTIC_LIMIT")
    if bound is not None:_DRIVER["bound"]=bound
    bound=_DRIVER["bound"]
    if operation!="FAILURE":_DRIVER["operation"]=operation
    fault=None if error is None else safe_driver_error(error)
    record=dict(schema_version="stage12_task_driver_checkpoint_v1",seq=_DRIVER["seq"]+1,
        event=operation,operation=_DRIVER["operation"],status=status,source_sha=SOURCE,
        job_id=None if bound is None else bound.cfg["job_id"],actual_mono_ns=time.monotonic_ns(),actual_utc=z(now_utc()),
        safe_error=fault,first_failure=_DRIVER["first_failure"],cleanup_failure=_DRIVER["cleanup_failure"],
        diagnostics_uncertain=_DRIVER["diagnostics_uncertain"],first_diagnostic_failure=_DRIVER["first_diagnostic_failure"],
        presence=driver_presence(bound),presence_is_not_approval=True)
    raw=canonical(record)
    # Ordinary progress cannot consume the two reserved failure records.
    maximum_records=32 if status=="FAILED" else 30
    maximum_bytes=32768 if status=="FAILED" else 28672
    need(len(raw)<=2048 and _DRIVER["seq"]<maximum_records
         and _DRIVER["bytes"]+len(raw)<=maximum_bytes,"PREARMED_DIAGNOSTIC_LIMIT")
    _DRIVER["seq"]+=1;_DRIVER["bytes"]+=len(raw)
    print(raw.decode(),end="",flush=True)
    return record


def driver_result(result):
    # Existing result messages have a separate32KiB reserve: at most four
    # messages of8192B; total checkpoint+result stdout is at most64KiB.
    raw=canonical(result)
    need(len(raw)<=8192 and _DRIVER.get("results",0)<4,"PREARMED_DIAGNOSTIC_LIMIT")
    _DRIVER["results"]=_DRIVER.get("results",0)+1
    print(raw.decode(),end="",flush=True)


def static_preflight(bound):
    need(bound.cfg["schema_version"] in (CATALOG_SCHEMA,SIMPLE_CATALOG_SCHEMA) and bound.local_catalog is not None,"PREARMED_LOCAL_CATALOG_REQUIRED")
    need(bound.unissued,"PREARMED_UNISSUED_FIELDS")
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
    compiled=accounting.validate_inventory(bound.selected["accounting_inventory"])
    streams={row["phase_id"]:row for row in compiled["monitor_streams"]}
    stages={row["id"]:row for row in bound.resource["limits"]["stages"]}
    need(all(streams[phase]["deadline_ms"]==stages[phase]["deadline_ms"] for phase in (6,7)),"PREARMED_PREFLIGHT_STAGE")
    cap=collector_file_limit(bound,Path("collector_resources/observations.bin"),None)
    need(cap==streams[6]["maximum_rows"]*1024,"PREARMED_PREFLIGHT_STAGE")
    checker=load_script(Path(bound.cfg["checker_script"]["path"]),"preflight_fixed_checker_schema")
    need(checker.SCHEMA=="stage12_task_factual_checker_input_v1","PREARMED_CHECKER_SCHEMA")
    return dict(schema_version="stage12_task_unissued_preflight_v1",status="KNOWN_STATIC_INPUTS_VALIDATED_NO_AUTHORITY",source_sha=SOURCE,
        selection_sha256=bound.sha,resource_selection_sha256=bound.resource_sha,resource_review_sha256=sha(bound.review_raw),
        checker_sha256=bound.checker_sha,checker_input_schema=checker.SCHEMA,checker_input_keys=sorted(checker.CONFIG_KEYS),
        stage6_maximum_rows=streams[6]["maximum_rows"],stage7_maximum_rows=streams[7]["maximum_rows"],
        stage6_observation_bytes=cap,stage6_deadline_ms=stages[6]["deadline_ms"],stage7_deadline_ms=stages[7]["deadline_ms"],
        deferred_fields=["job_id","state_dir","review_dir","vouchers"],
        deferred_facts=["ACTUAL_JOB_CONTEXT","READINESS","FETCH","NATIVE_FACTS","FIRST_START_ACK","ACTUAL_CHECKER_INPUT_AND_REQUEST"],
        no_files_or_processes_created=True,approval="NONE")


def prepare_checker_handoff(bound,raw,stderr,ready,*,evidence_use="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"):
    driver_checkpoint("COLLECTOR_EXTRACT",bound=bound)
    destination,_inventory,codec=extract_collector(bound,raw,stderr,ready)
    driver_checkpoint("COLLECTOR_EXTRACT",bound=bound,status="OK")
    driver_checkpoint("CHECKER_REQUEST",bound=bound)
    cfg=checker_config(bound,destination,codec,evidence_use=evidence_use)
    checker=load_script(Path(bound.cfg["checker_script"]["path"]),"handoff_fixed_checker_schema")
    need(set(cfg)==checker.CONFIG_KEYS and cfg["schema_version"]==checker.SCHEMA,"PREARMED_CHECKER_SCHEMA")
    checker_path=bound.state/"CHECKER_INPUT.record";put(checker_path,canonical(cfg))
    request=checker_request(bound,checker_path,evidence_use=evidence_use)
    put(bound.state/"CHECKER_REQUEST.record",canonical(request))
    driver_checkpoint("CHECKER_REQUEST",bound=bound,status="OK")
    return destination,request


def main(argv=None):
    _DRIVER.update(seq=0,bytes=0,results=0,operation="CONFIG_READ",bound=None,first_failure=None,cleanup_failure=None,diagnostics_uncertain=False,first_diagnostic_failure=None)
    driver_checkpoint("CONFIG_READ")
    p=argparse.ArgumentParser();p.add_argument("--config",required=True,type=Path)
    p.add_argument("--action",choices=("preflight","inspect","arm"),required=True);args=p.parse_args(argv)
    driver_checkpoint("STATIC_VALIDATION")
    b=Bound(read_original(args.config,4*2**20),unissued=args.action=="preflight")
    driver_checkpoint("STATIC_VALIDATION",bound=b,status="OK")
    if args.action=="preflight":
        driver_checkpoint("PREFLIGHT",bound=b)
        result=static_preflight(b)
    elif args.action=="inspect":
        result=dict(schema_version=b.cfg["schema_version"],source_sha=SOURCE,job_id=b.cfg["job_id"],roles=ROLES,
            maximum_child_units=sum(ROLES.values()),maximum_runner_units=1,
            inprocess_driver_roles=["FACTUAL_SEAL","EXACT_SEAL"],approval="NONE")
    else:result=run(b)
    driver_checkpoint("DRIVER_EXIT",bound=b,status="OK")
    driver_result(result)

if __name__=="__main__":
    try:main()
    except Exception as error:
        first=retain_driver_failure(error)
        attempt_driver_checkpoint("FAILURE",status="FAILED",error=error)
        try:
            driver_result(dict(status="FAILED_NO_FURTHER_PUBLICATION",code=first["safe_error"]["code"],
                operation=first["operation"],first_failure=first,cleanup_failure=_DRIVER["cleanup_failure"],
                diagnostics_uncertain=_DRIVER["diagnostics_uncertain"],presence=driver_presence(_DRIVER["bound"]),
                presence_is_not_approval=True))
        except BaseException:
            _DRIVER["diagnostics_uncertain"]=True
        raise SystemExit(1)

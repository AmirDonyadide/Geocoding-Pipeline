"""Task-only current REP512 preparation; no approval, child launch or live facts.

Use the exact repository .venv interpreter. Read-only derive() executes the four
pure assignments from the real build() producer, not invented bootstrap facts.
finalize() requires independently issued current review originals. All writes
are private/exclusive; this program does not transfer, submit or start a driver.
"""
from __future__ import annotations
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

WINDOW_END = "2026-11-13T19:13:21.620987Z"
BASE = Path(__file__).resolve().parents[2]
ROOT = Path("/Users/amir/Documents/GitHub/safe_geocoding_pipeline")
REFERENCES = Path(__file__).with_name("GENUINE_INPUT_REFERENCES.record")

def need(value, code="CURRENT_PREPARATION_BINDING"):
    if not value: raise RuntimeError(code)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def ident(s): return(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,
                       s.st_size,s.st_mtime_ns,s.st_ctime_ns)

def read_ref(value, maximum=4*2**20):
    need(type(value) is dict and set(value)=={"path","sha256"})
    p=Path(value["path"])
    need(p.is_absolute() and p.resolve(strict=True)==p and ".." not in p.parts)
    before=p.lstat();need(stat.S_ISREG(before.st_mode) and before.st_nlink==1
        and before.st_size<=maximum and before.st_uid==os.geteuid())
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW);out=bytearray()
    try:
        need(ident(os.fstat(fd))==ident(before))
        while True:
            raw=os.read(fd,min(65536,maximum+1-len(out)))
            need(len(out)+len(raw)<=maximum)
            out.extend(raw)
            if not raw:break
        need(ident(os.fstat(fd))==ident(before)==ident(p.lstat()))
    finally:os.close(fd)
    raw=bytes(out);need(sha(raw)==value["sha256"])
    return raw

def ref(p):
    p=Path(p).resolve(strict=True)
    return dict(path=str(p),sha256=sha(p.read_bytes()))

def put(p, raw):
    p=Path(p);need(p.parent.is_dir() and stat.S_IMODE(p.parent.stat().st_mode)==0o700)
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view);need(n>0);view=view[n:]
        os.fsync(fd)
    finally:os.close(fd)
    fd=os.open(p.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return dict(path=str(p),sha256=sha(raw))

def module(name):
    p=ROOT/"scripts"/(name+".py")
    spec=importlib.util.spec_from_file_location("current_prep_"+name,p)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

def core():
    sys.path.insert(0,str(ROOT/"src"))
    return module("stage12_ra_g1_allocation"),module("stage12_prepare_ra_g1")

def factory_assignments(preparer, allocation):
    """Only known pure source-owned build() expressions; no bootstrap invented."""
    path=Path(preparer.__file__);tree=ast.parse(path.read_text())
    build=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="build")
    env=dict(preparer.__dict__,allocation=allocation)
    result={}
    for name in ("policy","graph","descriptor_inventory","paths"):
        matches=[n.value for n in build.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)]
        need(len(matches)==1,"CURRENT_PREPARATION_FACTORY_SHAPE")
        expression=ast.Expression(body=deepcopy(matches[0]));ast.fix_missing_locations(expression)
        result[name]=eval(compile(expression,str(path),"eval"),env)
        env[name]=result[name]
    return result

def prepare_assets(*args, **kwargs):
    raise RuntimeError("CURRENT_PREPARATION_USE_REVIEWED_REBIND_SUPPORT")

NATIVE_LAYOUT_VERSION = "stage12_rep_direct_allocation_separate_records_v1"
NATIVE_PROJECT = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
NATIVE_CONTROLLED = NATIVE_PROJECT/"derived/controlled/stage12/client_diagnostics"


def selected_native_layout(native_root, native_records, native_source):
    """Select disjoint native roots; this does not create or attest to them."""
    values=(native_root,native_records,native_source)
    need(all(type(value) is str for value in values), "CURRENT_PREPARATION_NATIVE_LAYOUT")
    nr,nrec,ns=map(Path,values)
    need(all(str(path)==value for path,value in zip((nr,nrec,ns),values)),
        "CURRENT_PREPARATION_NATIVE_LAYOUT")
    need(all(path.is_absolute() and str(path)==os.path.normpath(str(path))
        and ".." not in path.parts and str(path).startswith(str(NATIVE_PROJECT)+"/")
        and not any(ord(ch)<32 or ord(ch)==127 for ch in str(path))
        and not any(part in {"public","HOLDOUT",".git",".ssh",".aws",".config","credentials","secrets"}
                    or part.startswith(".env") for part in path.parts) for path in (nr,nrec,ns)),
        "CURRENT_PREPARATION_NATIVE_LAYOUT")
    base=nrec.parent
    need(nr.parent==NATIVE_CONTROLLED and nr.name.startswith("ra_g1_") and nr.name!="ra_g1_"
        and nrec.name=="records" and base.parent==NATIVE_CONTROLLED and base!=nr
        and ns.parent==NATIVE_PROJECT/"integration_stage12"
        and all(left!=right and not left.is_relative_to(right) and not right.is_relative_to(left)
                for left,right in ((nr,base),(nr,ns),(base,ns))), "CURRENT_PREPARATION_NATIVE_LAYOUT")
    return dict(version=NATIVE_LAYOUT_VERSION,allocation_root=str(nr),records=str(nrec),
        records_base=str(base),controlled_parent=str(NATIVE_CONTROLLED),source=str(ns),
        allocation_creation_owner="NATIVE_COLLECTOR_EXCLUSIVE")


def derive(*, final_source_sha, source_tree, source_inventory_ref, source_report_ref,
           native_source, native_root, native_records, valid_from, intent_id,
           qualification_bundle_ref, qualification_review_ref, owner_authority_ref,
           backend_inventory_ref, remote_directory_adoption_ref, window_grant_nonce):
    ctl,preparer=core()
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
    gate=module("stage12_ra_g1_environment_launch")
    verifier=module("stage12_ra_g1_terminal_verify")
    windows=gate.window_module()
    need(WINDOW_END==windows.HANDOFF_WINDOW_END and valid_from==windows.HANDOFF_WINDOW_START,
         "CURRENT_PREPARATION_WINDOW_BINDING")
    # No unknown placeholders or historical findings can activate this adapter.
    qraw=read_ref(qualification_bundle_ref,65536)
    qrraw=read_ref(qualification_review_ref,65536)
    oraw=read_ref(owner_authority_ref,1024*1024)
    qualification=ctl.parse(qraw)
    need(sha(qraw)==windows.Q2_BUNDLE and sha(qrraw)==windows.Q2_REVIEW,
         "CURRENT_PREPARATION_HISTORICAL_Q2_BINDING")
    need(type(window_grant_nonce) is str and len(window_grant_nonce)==64
         and set(window_grant_nonce)<=set("0123456789abcdef") and set(window_grant_nonce)!={"0"},
         "CURRENT_PREPARATION_WINDOW_BINDING")
    window=dict(version=windows.HANDOFF_WINDOW_VERSION, scope=ctl.SCOPE,
        valid_from=windows.HANDOFF_WINDOW_START,valid_until=windows.HANDOFF_WINDOW_END,
        policy_sha256=windows.digest(windows.handoff_descriptor()),
        owner_authority_sha256=sha(oraw),grant_nonce=window_grant_nonce)
    windows.validate_window(window,scope=ctl.SCOPE,now_epoch_ns=time.time_ns(),
                            required_remaining_seconds=windows.REP_REMAINING)
    verifier.validate_qualification(qualification,expected_window=qualification["window"],
        expected_original_source_git_sha=windows.ORIGINAL_SOURCE,
        expected_original_job_id=int(windows.ORIGINAL_JOB),
        expected_original_selection_sha256=windows.ORIGINAL_SELECTION,
        expected_collector_source_git_sha=windows.Q2_SOURCE,
        expected_qualification_review_sha256=sha(qrraw),
        expected_remote_directory_scope=verifier.REMOTE_DIRECTORY_SCOPE)
    remote_raw=read_ref(remote_directory_adoption_ref,65536)
    remote_adoption=json.loads(remote_raw)
    need(remote_adoption.get("version")=="stage12_selected_remote_directory_identity_adoption_v1"
        and remote_adoption.get("policy_sha256")==gate.REMOTE_DIRECTORY_PROPOSAL_SHA256
        and remote_adoption.get("finite_inventory_sha256")==gate.REMOTE_DIRECTORY_INVENTORY_SHA256,
        "CURRENT_PREPARATION_REMOTE_POLICY_BINDING")
    pins=json.loads(REFERENCES.read_text())
    template=ctl.parse(read_ref(pins["REP512_template"]))
    genuine=ctl.parse(read_ref(pins["native_backend_selection"]))
    rows=ctl.parse(read_ref(source_inventory_ref))
    need(type(rows)is list and 1<=len(rows)<=2048)
    need([r["path"] for r in rows]==sorted(set(r["path"] for r in rows)))
    for row in rows:
        p=ROOT/row["path"];need(p.is_file() and p.resolve()==p and p.stat().st_size==row["bytes"])
        h=hashlib.sha256()
        with p.open("rb") as f:
            while block:=f.read(65536):h.update(block)
        need(h.hexdigest()==row["sha256"],"CURRENT_PREPARATION_SOURCE_CHANGED")
    backends=ctl.parse(read_ref(backend_inventory_ref))
    ac.validate_backends(backends)
    need(len(backends)==5 and all("linux" in r["path"] and "darwin" not in r["path"]
                                 and r["stat_scope"]=="PREPARATION_HOST_SNAPSHOT" for r in backends),
         "CURRENT_PREPARATION_NATIVE_BACKEND_ORIGINAL_REQUIRED")
    originals={name:read_ref(pin) for name,pin in pins["records"].items()}
    objects={name:ctl.parse(raw) for name,raw in originals.items()}
    need(objects["adoption"]["decision"]=="ADOPTED_PROSPECTIVELY_WITH_EXPLICIT_LOCAL_REPAIR_OVERRIDE")
    need(objects["project_approval"]["attribution"]=="OWNER_REPORTED_PROJECT_APPROVAL_NOT_ADMIN_ATTESTATION")
    oldroot=Path(genuine["paths"]["allocation_root"])
    layout=selected_native_layout(native_root,native_records,native_source)
    nr,nrec,ns=map(Path,(layout["allocation_root"],layout["records"],layout["source"]))
    paths={}
    for key,value in genuine["paths"].items():
        paths[key]=str(ns if key=="source" else nrec if key=="records" else nr if key=="allocation_root"
                       else nrec/Path(value).name if key=="log" else nr/Path(value).relative_to(oldroot))
    allocation=deepcopy(genuine)
    allocation.update(version=ctl.REP512_VERSION,scope=ctl.SCOPE,source_sha=final_source_sha,
                      source_files=rows,paths=paths,limits=deepcopy(ctl.REP_ADMIN_LIMITS),
                      intent_id=intent_id,valid_from=valid_from,valid_until=WINDOW_END)
    allocation.pop("resource_selection_sha256",None)
    allocation["records"]={name:pins["records"][name]["sha256"] for name in ("adoption","project_approval")}
    for key in ("bootstrap_prefix_adoption","rep_admin_budget_adoption","rep_first64_512_adoption"):
        allocation[key]=objects[key];allocation[key+"_sha256"]=pins["records"][key]["sha256"]
    original_admin=objects["rep_admin_budget_adoption"]
    windowed_admin=dict(schema_version=windows.HANDOFF_WINDOW_ADOPTION,scope=ctl.SCOPE,
        window=window,original_adoption=original_admin,
        original_adoption_sha256=pins["records"]["rep_admin_budget_adoption"]["sha256"],
        grant_kind=windows.REP_GRANT,maximum_submissions=1,
        qualification_bundle_sha256=sha(qraw),qualification_review_sha256=sha(qrraw),
        historical_grant_consumed=True,original_budget_terms_unchanged=True)
    allocation["rep_admin_budget_adoption"]=windowed_admin
    allocation["rep_admin_budget_adoption_sha256"]=ctl.digest(windowed_admin)
    originals["original_rep_admin_budget_adoption"]=originals["rep_admin_budget_adoption"]
    originals["rep_admin_budget_adoption"]=ctl.canonical(windowed_admin)
    inventory,accounting=ac.compile_inventory(rows,backends,ctl.SCOPE,
        bootstrap_successor=True,shared_lease_successor=True,rep_admin_successor=True,
        first64_512_successor=True)
    allocation["accounting_inventory"],allocation["accounting"]=inventory,accounting
    raw_report=read_ref(source_report_ref,1024*1024)
    produced=factory_assignments(preparer,allocation)
    required=dict(source_sha=final_source_sha,scope=ctl.SCOPE,source_files=len(rows),
                  source_bytes=sum(r["bytes"] for r in rows),
                  descriptor_inventory_sha256=ctl.digest(produced["descriptor_inventory"]),
                  workload_graph_sha256=ctl.digest(produced["graph"]),
                  paths_sha256=ctl.digest(produced["paths"]),
                  accounting_inventory_sha256=ctl.digest(inventory),
                  implementation_review_sha256=sha(raw_report))
    return dict(status="DERIVED_BINDINGS_ONLY_NOT_REVIEW_APPROVAL",source_tree=source_tree,native_layout=layout,
                allocation=allocation,required_resource_review=required,
                produced=produced,source_report=source_report_ref,source_inventory=source_inventory_ref,
                originals=originals,backend_source=backend_inventory_ref,
                qualification=qualification,qualification_raw=qraw,qualification_review_raw=qrraw,
                owner_authority_raw=oraw,qualification_bundle_ref=qualification_bundle_ref,
                qualification_review_ref=qualification_review_ref,owner_authority_ref=owner_authority_ref,
                remote_directory_adoption_ref=remote_directory_adoption_ref,remote_directory_adoption_raw=remote_raw,
                native_full_hashes="PENDING_IN_NEW_ALLOCATION_NOT_INVENTED",
                local_template_scope="ONLY_REP512_ADOPTION_OBJECTS_NOT_MAC_BACKEND_OR_TEST_REVIEWS")

def attach_local_catalog(cfg, *, selected_raw, local_records_dir, output, helper, controller):
    """Bind exact local copies without changing any selected native path."""
    selected=controller.validate_selection(controller.parse(selected_raw))
    need(cfg["schema_version"]==helper.SCHEMA and "local_record_catalog" not in cfg
        and cfg["source_sha"]==selected["source_sha"]
        and cfg["selection"]["sha256"]==sha(selected_raw)
        and cfg["records_dir"]==selected["paths"]["records"],"CURRENT_PREPARATION_LOCAL_CATALOG_BINDING")
    output=Path(output)
    reference=helper.create_local_catalog(selected_raw,local_records_dir,
        output/"local_record_catalog",output/"LOCAL_RECORD_CATALOG.record",controller)
    return dict(cfg,schema_version=helper.CATALOG_SCHEMA,local_record_catalog=reference)


def finalize(derived, *, software_review_ref, resource_review_ref, environment_adoption_ref,
             assets, output):
    ctl,preparer=core();gate=module("stage12_ra_g1_environment_launch")
    allocation=deepcopy(derived["allocation"])
    swraw=read_ref(software_review_ref,16384);rrraw=read_ref(resource_review_ref,65536)
    sw,rr=ctl.parse(swraw),ctl.parse(rrraw)
    need(sw.get("disposition")==rr.get("disposition")=="PASS"
         and sw.get("source_sha")==rr.get("source_sha")==allocation["source_sha"],
         "CURRENT_PREPARATION_ACTUAL_REVIEW_REQUIRED")
    need(sw["report_sha256"]==derived["source_report"]["sha256"])
    need(all(rr.get(k)==v for k,v in derived["required_resource_review"].items()),
         "CURRENT_PREPARATION_RESOURCE_REVIEW_BINDING")
    binding=gate.validate_binding(sw.get("environment_gate_binding"),allocation)
    need(binding["source_tree"]==derived["source_tree"]
         and binding["handoff_assets_sha256"]==assets["inventory"]["sha256"]
         and binding["adoption_sha256"]==environment_adoption_ref["sha256"])
    allocation["records"].update(software_review=sha(swraw),resource_review=sha(rrraw))
    selected=preparer.resource_selection(allocation,
        policy_sha256=ctl.digest(derived["produced"]["policy"]),
        adoption_sha256=allocation["records"]["adoption"],
        descriptor_inventory_sha256=rr["descriptor_inventory_sha256"],
        graph_sha256=rr["workload_graph_sha256"],paths_sha256=rr["paths_sha256"],
        implementation_review_sha256=sw["report_sha256"])
    allocation["resource_selection_sha256"]=ctl.digest(selected)
    ctl.validate_selection(allocation)
    need(binding["version"]==gate.HANDOFF_COLLECTION_BINDING
        and binding["remote_directory_scope"]==gate.REMOTE_DIRECTORY_SCOPE
        and binding["transport_evidence_version"]==gate.REMOTE_TRANSPORT_VERSION
        and binding["remote_directory_adoption_sha256"]==derived["remote_directory_adoption_ref"]["sha256"]
        and assets["remote_directory_policy_binding"]=={k:binding[k] for k in gate.REMOTE_COLLECTION_FIELDS},
        "CURRENT_PREPARATION_COLLECTION_GATE_REQUIRED")
    need(binding["qualification_bundle_sha256"]==derived["qualification_bundle_ref"]["sha256"]
         and binding["qualification_review_sha256"]==derived["qualification_review_ref"]["sha256"]
         and binding["owner_authority_sha256"]==derived["owner_authority_ref"]["sha256"],
         "CURRENT_PREPARATION_QUALIFICATION_BINDING")
    companion=dict(version=gate.HANDOFF_COLLECTION_VERSION,scope=gate.SCOPE,
        state="ISSUED_FOR_COLLECTION_QUALIFIED_ONE_FRESH_REP",source_git_sha=allocation["source_sha"],
        source_tree=binding["source_tree"],**{k:binding[k] for k in (*gate.COLLECTION_BINDING_HASHES,*gate.REMOTE_COLLECTION_FIELDS)},
        selection_sha256=ctl.digest(allocation),resource_selection_sha256=ctl.digest(selected),
        software_review_sha256=allocation["records"]["software_review"],
        resource_review_sha256=allocation["records"]["resource_review"],
        source_inventory_sha256=allocation["accounting_inventory"]["source_inventory_sha256"],
        valid_from=allocation["valid_from"],valid_until=WINDOW_END,outer_window_end=WINDOW_END,
        grant_kind=gate.window_module().REP_GRANT,maximum_submissions=1,
        task_profiling="DISABLED",budget=deepcopy(gate.BUDGET),history=deepcopy(gate.COLLECTION_HISTORY),
        window=deepcopy(allocation["rep_admin_budget_adoption"]["window"]))
    verifier=module("stage12_ra_g1_terminal_verify")
    proof=gate.validate_gate(companion,allocation,binding,now_epoch_ns=time.time_ns(),
        qualification=derived["qualification"],qualification_validator=verifier.validate_qualification)
    output=Path(output);output.mkdir(mode=0o700)
    records=output/"records";records.mkdir(mode=0o700)
    uploads=[]
    def retain(raw,name,remote_name=None):
        pin=put(records/name,raw)
        uploads.append(dict(local=pin["path"],remote=str(Path(allocation["paths"]["records"])/(remote_name or name)),
                            bytes=len(raw),sha256=pin["sha256"]))
        return pin
    for name,raw in derived["originals"].items(): retain(raw,sha(raw)+".record")
    retain(swraw,sha(swraw)+".record");retain(rrraw,sha(rrraw)+".record")
    report_raw=read_ref(derived["source_report"],1024*1024)
    retain(report_raw,sha(report_raw)+".md")
    adraw=read_ref(environment_adoption_ref,1024*1024)
    retain(adraw,sha(adraw)+".record")
    retain(derived["qualification_raw"],binding["qualification_bundle_sha256"]+".collection-qualification.record")
    retain(derived["qualification_review_raw"],binding["qualification_review_sha256"]+".qualification-review.record")
    retain(derived["owner_authority_raw"],binding["owner_authority_sha256"]+".owner-authority.record")
    retain(derived["remote_directory_adoption_raw"],binding["remote_directory_adoption_sha256"]+".remote-directory-adoption.record")
    graw=ctl.canonical(companion);gsha=sha(graw)
    gatepin=retain(graw,gsha+".environment-gate.record")
    refs={name:put(output/(name+".record"),ctl.canonical(value)) for name,value in {
        "SELECTION":allocation,"RESOURCE_SELECTION":selected,"RESOURCE_REVIEW":rr,
        "SOFTWARE_REVIEW":sw,"SOURCE_FILES":allocation["source_files"],
        "ACCOUNTING_INVENTORY":allocation["accounting_inventory"],
        "INVOCATION_GRAPH":derived["produced"]["graph"],
        "DESCRIPTOR_INVENTORY":derived["produced"]["descriptor_inventory"],
        "PATH_BINDINGS":derived["produced"]["paths"],"NATIVE_RECORD_UPLOADS":uploads,
        "ENVIRONMENT_GATE_PROOF":proof}.items()}
    # Actual parsers on final materialized canonical bytes, after all edits.
    ctl.validate_selection(ctl.parse(read_ref(refs["SELECTION"])))
    actual_resource=ctl.parse(read_ref(refs["RESOURCE_SELECTION"]))
    preparer.m.validate_selection(actual_resource)
    gate.validate_gate(ctl.parse(read_ref(gatepin)),allocation,binding,now_epoch_ns=time.time_ns(),
        qualification=ctl.parse(read_ref(derived["qualification_bundle_ref"],65536)),
        qualification_validator=verifier.validate_qualification)
    hspec=importlib.util.spec_from_file_location("current_prepared_handoff",Path(assets["directory"])/"prearmed_handoff.py")
    h=importlib.util.module_from_spec(hspec);hspec.loader.exec_module(h)
    cfg=dict(schema_version=h.SCHEMA,source_sha=allocation["source_sha"],source_dir=str(ROOT),
        python_executable=str(ROOT/".venv/bin/python"),source_inventory=refs["SOURCE_FILES"],
        selection=refs["SELECTION"],resource_selection=refs["RESOURCE_SELECTION"],
        resource_review=refs["RESOURCE_REVIEW"],job_id=None,host="goethe",expected_uid=60099,
        expected_gid=58194,state_dir=None,review_dir=None,checker_script=assets["files"]["factual_evidence_check.py"],
        exact_checker_script=assets["files"]["exact_input_check.py"],
        records_dir=allocation["paths"]["records"],vouchers=None,limits=h.LIMITS)
    cfg=attach_local_catalog(cfg,selected_raw=ctl.canonical(allocation),
        local_records_dir=records,output=output,helper=h,controller=ctl)
    template=put(output/"HANDOFF_CONFIG_UNISSUED.record",h.canonical(cfg))
    h.Bound(read_ref(template),unissued=True)
    result=dict(status="CANONICAL_BINDINGS_GENERATED_NOT_NATIVE_READY_OR_SUBMISSION",
        source_sha=allocation["source_sha"],selection=refs["SELECTION"],
        resource_selection=refs["RESOURCE_SELECTION"],resource_review=refs["RESOURCE_REVIEW"],
        source_inventory=refs["SOURCE_FILES"],gate=gatepin,gate_sha256=gsha,
        record_uploads=refs["NATIVE_RECORD_UPLOADS"],handoff_unissued=template,assets=assets,
        actual_source_entry_requires_gate_environment_variable="STAGE12_RA_ENVIRONMENT_GATE_SHA",
        gate_sha_passed_after_asset_hashing_not_embedded=True,
        actual_job_vouchers_factual_and_input_reviews="UNISSUED_UNTIL_GENUINE_SAME_ALLOCATION_FACTS",
        native_actual_ready="REQUIRED_INSIDE_COLLECTOR_WITH_SAME_ROLE_ORIGIN")
    put(output/"PREPARATION_RESULT.record",ctl.canonical(result))
    return result

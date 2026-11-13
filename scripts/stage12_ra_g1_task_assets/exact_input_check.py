"""Fixed after-factual exact-input check and separately invoked reviewer sealer.

Findings issue no approval. The independent reviewer must examine all originals
and write a separate sealed decision before invoking seal(); no expected B work
runs before a successful, exact factual-publication receipt.
"""
from pathlib import Path
import argparse
import importlib.util

SPEC=importlib.util.spec_from_file_location("exact_task_handoff",Path(__file__).with_name("prearmed_handoff.py"))
h=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(h)
SCHEMA="stage12_task_exact_input_checker_local_catalog_v2"
KEYS={"schema_version","orchestration_config","collector_checker_config","input_dir","input_archive",
      "input_inventory","factual_review","factual_publication_result","evidence_use","local_record_catalog"}

def setup(config_path):
    raw=h.read_original(config_path,4*2**20);cfg=h.parse(raw)
    h.need(set(cfg)==KEYS and cfg["schema_version"]==SCHEMA
        and cfg["evidence_use"] in ("HISTORICAL_REHEARSAL","FRESH_SAME_ALLOCATION_FINDINGS_ONLY"),"PREARMED_EXACT_CONFIG")
    bound=h.Bound(h.ref(cfg["orchestration_config"],4*2**20))
    h.need(bound.cfg["schema_version"] in (h.CATALOG_SCHEMA,h.SIMPLE_CATALOG_SCHEMA) and bound.local_catalog is not None
        and cfg["local_record_catalog"]==bound.cfg["local_record_catalog"],"PREARMED_LOCAL_CATALOG_BINDING")
    return cfg,raw,bound

def input_originals(cfg,bound):
    root=h.absolute(cfg["input_dir"]);inventory=h.parse(h.ref(cfg["input_inventory"],2**20))
    tar_raw=h.ref(cfg["input_archive"],16*2**20)
    h.need(type(inventory) is list and 0<len(inventory)<=256,"PREARMED_EXACT_INVENTORY")
    fixed,binding,directories=h.exact_archive_layout(bound)
    paths=set();data_bytes=0;seen=set();headers=set()
    import io,tarfile
    with tarfile.open(fileobj=io.BytesIO(tar_raw),mode="r:") as archive:
        members={}
        for item in archive:
            rel=h.archive_relative(item,"PREARMED_EXACT_INVENTORY")
            h.need(rel not in seen and len(seen)<256+len(directories),"PREARMED_EXACT_INVENTORY")
            seen.add(rel)
            if item.isdir():
                h.need(rel in directories and item.mode==0o700
                    and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"],"PREARMED_EXACT_INVENTORY")
                headers.add(rel);continue
            h.need(item.isfile() and rel not in directories
                and (rel in fixed or rel.parent in {binding,binding/"resource_evidence"})
                and h.archive_parents({rel})<=directories and item.mode==0o600
                and item.uid==bound.cfg["expected_uid"] and item.gid==bound.cfg["expected_gid"]
                and 0<=item.size<=4*2**20 and len(members)<256,"PREARMED_EXACT_INVENTORY")
            raw=archive.extractfile(item).read(item.size+1);data_bytes+=len(raw)
            h.need(len(raw)==item.size and data_bytes<=16*2**20,"PREARMED_EXACT_INVENTORY")
            members[str(rel)]=(raw,item)
    file_paths={Path(p) for p in members};effective=h.archive_parents(file_paths)|{binding}
    h.need(fixed<=file_paths and binding in (headers|h.archive_parents(file_paths))
        and effective<=directories and headers<=effective,"PREARMED_EXACT_INVENTORY")
    h.exact_copied_tree(root,file_paths,effective)
    for row in inventory:
        h.need(type(row) is dict and set(row)=={"path","bytes","sha256","original_mode","original_uid","original_gid"}
            and type(row["path"]) is str and row["path"] not in paths and row["path"] in members,"PREARMED_EXACT_INVENTORY")
        raw,item=members[row["path"]]
        h.need(row["bytes"]==len(raw) and row["sha256"]==h.sha(raw)
            and row["original_mode"]==item.mode and row["original_uid"]==item.uid
            and row["original_gid"]==item.gid,"PREARMED_EXACT_INVENTORY")
        h.need(h.read_original(root/row["path"],4*2**20)==raw,"PREARMED_EXACT_ORIGINAL")
        paths.add(row["path"])
    h.need(paths==set(members),"PREARMED_EXACT_INVENTORY")
    return root,inventory,members

def checked(config_path):
    cfg,cfg_raw,b=setup(config_path);c=b.controller;s=b.selected
    factual_raw=h.ref(cfg["factual_review"],8192);factual=b.production_parse(factual_raw)
    # A real zero exit and exact durable readback precede every producer call.
    publication=h.parse(h.ref(cfg["factual_publication_result"],8192))
    stdout=h.read_original(Path(cfg["factual_publication_result"]["path"]).with_name("FACTUAL_PUBLISH.stdout"),8192)
    h.need(publication["returncode"]==0 and publication["uncertain"] is None
        and publication["stdout_sha256"]==h.sha(stdout)
        and stdout==(h.sha(factual_raw)+"  "+s["paths"]["review"]+"\n").encode(),
        "PREARMED_FACTUAL_PUBLICATION_REQUIRED")
    collector_cfg=h.parse(h.ref(cfg["collector_checker_config"],4*2**20))
    h.need(collector_cfg["source_sha"]==h.SOURCE and collector_cfg["job_id"]==int(b.cfg["job_id"])
        and collector_cfg["selection"]["sha256"]==b.sha,"PREARMED_EXACT_COLLECTOR")
    collector=h.absolute(collector_cfg["originals_dir"])
    bootstrap_raw=h.read_original(collector/"bootstrap/bootstrap.record",4*2**20)
    manifest_raw=h.read_original(collector/"bootstrap/manifest.record",65536)
    bootstrap=b.production_parse(bootstrap_raw);manifest=b.production_parse(manifest_raw)
    h.need(manifest["bootstrap_sha256"]==h.sha(bootstrap_raw) and manifest["source_sha"]==h.SOURCE
        and bootstrap["source_sha"]==h.SOURCE and str(bootstrap["job_id"])==b.cfg["job_id"]
        and factual["disposition"]=="PASS" and factual["source_sha"]==h.SOURCE
        and factual["selection_sha256"]==b.sha
        and factual["bootstrap_manifest_sha256"]==h.sha(manifest_raw),"PREARMED_EXACT_COLLECTOR")
    root,inventory,members=input_originals(cfg,b)
    h.need(b.local_catalog is not None,"PREARMED_LOCAL_CATALOG_REQUIRED")
    def role(name):
        return b.local_catalog.role(name)
    software=role("software_review")
    report=b.local_catalog.report(software["report_sha256"])
    producer=h.load_script(b.source/"scripts/stage12_prepare_ra_g1.py","fixed_exact_actual_producer")
    bootstrap=dict(bootstrap);bootstrap["manifest_sha256"]=h.sha(manifest_raw)
    data,objects=producer.build(s,bootstrap,implementation_report=report,source_files=s["source_files"],
        adoption=role("adoption"),project_approval=role("project_approval"),
        resource_review=role("resource_review"),independent_bootstrap_review=factual,issued=True)
    h.need(c.digest(objects["resource_selection"])==s["resource_selection_sha256"]==b.resource_sha,"PREARMED_EXACT_RESOURCE")
    bundle=Path(s["paths"]["binding"]).relative_to(b.root)
    expected={str(Path(s["paths"]["input"]).relative_to(b.root)):c.canonical(data)}
    def materialize(name,raw):
        name=str(bundle/name)
        h.need(name not in expected or expected[name]==raw,"PREARMED_EXACT_COLLISION")
        expected[name]=raw
    for values in objects["resource_evidence"].values():
        for digest,value in values.items():
            materialize(Path("resource_evidence")/(digest+".record"),c.canonical(value))
    for name,value in objects["role_records"].items():materialize(Path(name+".record"),c.canonical(value))
    for name in ("diagnostic_selection","diagnostic_resources"):
        materialize(Path(name+".record"),c.canonical(objects[name]))
    materialize(Path("integration_review.binding.json"),c.canonical(objects["integration_review"]))
    materialize(Path("integration_review.md"),report)
    h.need(len(expected)<=128 and sum(map(len,expected.values()))<=16*2**20,"PREARMED_EXACT_PRODUCER_BOUND")
    extras={str(Path(s["paths"]["context"]).relative_to(b.root)):None,
        str(Path(s["paths"]["review"]).relative_to(b.root)):factual_raw,
        "review_resources/admin_binding.record":None,"binder_resources/admin_binding.record":None}
    h.need(set(members)==set(expected)|set(extras),"PREARMED_EXACT_MATERIALIZATION")
    for path,raw in expected.items():
        h.need(members[path][0]==raw,"PREARMED_EXACT_MATERIALIZATION")
    for path,raw in extras.items():
        if raw is not None:h.need(members[path][0]==raw,"PREARMED_EXACT_FACTUAL")
    diagnostic=h.load_script(b.source/"scripts/stage12_ra_g1_diagnostic.py","fixed_exact_actual_diagnostic")
    actual_raw=members[str(Path(s["paths"]["input"]).relative_to(b.root))][0]
    actual=b.production_parse(actual_raw)
    diagnostic.validate_envelope(actual,h.SOURCE,for_execution=True)
    diagnostic.validate_workloads(actual)
    diagnostic.validate_resource_family(actual["version"],b.resource)
    diagnostic.validate_grants(actual,root/bundle)
    context_raw=members[str(Path(s["paths"]["context"]).relative_to(b.root))][0]
    context=b.execution.validate_supervisor_context(b.production_parse(context_raw))
    p7=b.production_parse(members["review_resources/admin_binding.record"][0])
    p8=b.production_parse(members["binder_resources/admin_binding.record"][0])
    for binding in (p7,p8):
        b.assurance.shape(binding,b.execution.ADMIN_BINDING_SCHEMA)
        h.need(binding["source_git_sha"]==h.SOURCE and binding["selection_sha256"]==b.resource_sha
            and binding["supervisor_context_sha256"]==h.sha(context_raw),"PREARMED_EXACT_PHASE")
    h.need(p7["role"]=="REVIEW" and p7["phase_id"]==7 and p8["role"]=="BINDER" and p8["phase_id"]==8
        and p8["scope_start_mono_ns"]<p8["deadline_mono_ns"]<=p8["scope_start_mono_ns"]+240_000_000_000
        and context["source_git_sha"]==h.SOURCE and str(context["slurm_job_id"])==b.cfg["job_id"]
        and context["run_nonce"]==s["intent_id"] and context["selection_sha256"]==b.resource_sha
        and context["private_paths"]==dict(allocation_root=str(b.root),
            resource_evidence_root=s["paths"]["output"],scratch_root=str(b.root)),"PREARMED_EXACT_PHASE")
    h.need(actual["configuration"]["command_paths"]==dict(source=s["paths"]["source"],input=s["paths"]["input"],
        output=s["paths"]["output"],evidence_bundle=s["paths"]["binding"])
        and actual["configuration"]["resource_execution"]==dict(schema_version=b.execution.EXECUTION_REQUEST,
        supervisor_context_path=s["paths"]["context"],supervisor_context_sha256=h.sha(context_raw)),"PREARMED_EXACT_PATH")
    return dict(schema_version="stage12_task_exact_input_findings_v1",required_checks="ALL_COMPLETED",
        authority="NONE_FINDINGS_ONLY",evidence_use=cfg["evidence_use"],source_sha=h.SOURCE,job_id=b.cfg["job_id"],
        selection_sha256=b.sha,resource_selection_sha256=b.resource_sha,checker_input_sha256=h.sha(cfg_raw),
        checker_sha256=h.sha(h.read_original(Path(__file__).resolve(),256*1024,private=False)),
        input_sha256=h.sha(actual_raw),review_binding_sha256=h.sha(members[str(bundle/"integration_review.binding.json")][0]),
        factual_review_sha256=h.sha(factual_raw),input_archive_sha256=cfg["input_archive"]["sha256"],
        input_inventory_sha256=cfg["input_inventory"]["sha256"],
        local_record_catalog_sha256=cfg["local_record_catalog"]["sha256"],whole_materialized_paths=len(expected),
        total_regular_originals=len(inventory),expected_B_derived_after_actual_factual_publication=True,
        native_current_identity_restatted=False,native_binder_acceptance="NOT_OBSERVED_SOURCE_GATE_REMAINS_REQUIRED")

DECISION_KEYS={"schema_version","disposition","findings_sha256","checker_input_sha256","source_sha","job_id",
    "selection_sha256","input_sha256","review_binding_sha256","resource_selection_sha256","factual_review_sha256","reviewed_utc"}

def seal(config_path, findings_path, decision_path):
    """Independent reviewer action only, after examining the fixed findings."""
    cfg,cfg_raw,b=setup(config_path)
    findings_raw=h.read_original(findings_path,2**20);findings=h.parse(findings_raw)
    decision_raw=h.read_original(decision_path,8192);decision=h.parse(decision_raw)
    completion=h.parse(h.read_original(b.state/"EXACT_CHECKER.completed.record",8192))
    h.need(completion["returncode"]==0 and completion["report_sha256"]==h.sha(findings_raw)
        and completion["checker_input_sha256"]==h.sha(cfg_raw),"PREARMED_EXACT_DECISION")
    h.need(Path(findings_path)==b.review_dir/"EXACT_CHECKER_FINDINGS.record"
        and Path(decision_path)==b.review_dir/"EXACT_REVIEW_DECISION.record"
        and set(decision)==DECISION_KEYS and decision["schema_version"]=="stage12_independent_exact_input_decision_v1"
        and decision["disposition"]=="PASS_ALL_REQUIRED","PREARMED_EXACT_DECISION")
    h.need(findings["required_checks"]=="ALL_COMPLETED" and findings["authority"]=="NONE_FINDINGS_ONLY"
        and findings["evidence_use"]==cfg["evidence_use"]=="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"
        and findings["checker_input_sha256"]==h.sha(cfg_raw)
        and decision["findings_sha256"]==h.sha(findings_raw),"PREARMED_EXACT_DECISION")
    for key in ("checker_input_sha256","source_sha","job_id","selection_sha256","input_sha256",
                "review_binding_sha256","resource_selection_sha256","factual_review_sha256"):
        h.need(decision[key]==findings[key],"PREARMED_EXACT_DECISION")
    h.utc(decision["reviewed_utc"])
    root,inventory,members=input_originals(cfg,b)
    input_path=str(Path(b.selected["paths"]["input"]).relative_to(b.root))
    binding_path=str(Path(b.selected["paths"]["binding"]).relative_to(b.root)/"integration_review.binding.json")
    h.need(h.sha(members[input_path][0])==findings["input_sha256"]
        and h.sha(members[binding_path][0])==findings["review_binding_sha256"],"PREARMED_EXACT_CHANGED")
    release=dict(schema_version="stage12_ra_g1_exact_input_release_v1",disposition="PASS",
        selection_sha256=b.sha,source_sha=h.SOURCE,input_sha256=findings["input_sha256"],
        review_binding_sha256=findings["review_binding_sha256"],
        bootstrap_review_sha256=findings["factual_review_sha256"],resource_selection_sha256=b.resource_sha)
    raw=b.controller.canonical(release);h.put(b.review_dir/"EXACT_INPUT_RELEASE.record",raw)
    marker=dict(schema_version="stage12_local_exact_review_ready_v1",source_sha=h.SOURCE,
        selection_sha256=b.sha,input_sha256=findings["input_sha256"],release_sha256=h.sha(raw),
        release_bytes=len(raw),substantive_checks="PASS_ALL_REQUIRED",sealed_utc=h.z(h.now_utc()))
    temporary=b.review_dir/"EXACT_INPUT_RELEASE.ready.tmp"
    ready=b.review_dir/"EXACT_INPUT_RELEASE.ready.record"
    marker_raw=h.canonical(marker);h.put(temporary,marker_raw)
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io
    s09_reference_io._atomic_rename(temporary,ready)
    s09_reference_io.fsync_directory(b.review_dir)
    h.need(h.read_original(ready,8192)==marker_raw,"PREARMED_EXACT_WRITE_UNCERTAIN")
    return dict(status="INDEPENDENT_REVIEWER_RELEASE_SEALED_NOT_NATIVE_ACCEPTANCE",release_sha256=h.sha(raw))

SAFE_EXACT_CODES=h.SAFE_DRIVER_CODES | frozenset(('PREARMED_EXACT_ARGUMENTS', 'PREARMED_EXACT_CHANGED', 'PREARMED_EXACT_COLLECTOR', 'PREARMED_EXACT_COLLISION', 'PREARMED_EXACT_CONFIG', 'PREARMED_EXACT_DECISION', 'PREARMED_EXACT_FACTUAL', 'PREARMED_EXACT_INVENTORY', 'PREARMED_EXACT_MATERIALIZATION', 'PREARMED_EXACT_ORIGINAL', 'PREARMED_EXACT_PATH', 'PREARMED_EXACT_PHASE', 'PREARMED_EXACT_PRODUCER_BOUND', 'PREARMED_EXACT_RESOURCE', 'PREARMED_EXACT_WRITE_UNCERTAIN', 'PREARMED_FACTUAL_PUBLICATION_REQUIRED', 'PREARMED_LOCAL_CATALOG_BINDING', 'PREARMED_LOCAL_CATALOG_REQUIRED'))


def safe_failure(error):
    code=error.args[0] if type(error) is RuntimeError and len(error.args)==1 \
        and type(error.args[0]) is str and error.args[0] in SAFE_EXACT_CODES else "PREARMED_EXACT_FAILED_UNCLASSIFIED"
    result=dict(required_checks="FAILED_OR_INCOMPLETE",authority="NONE_FINDINGS_ONLY",code=code)
    diagnostic=h.catalog_diagnostic(error)
    if diagnostic is not None:result["local_catalog_failure"]=diagnostic
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--config",required=True,type=Path)
    p.add_argument("--report",type=Path);p.add_argument("--seal-findings",type=Path);p.add_argument("--decision",type=Path)
    args=p.parse_args(argv)
    if args.report:
        result=checked(args.config);h.put(args.report,h.canonical(result))
    else:
        h.need(args.seal_findings is not None and args.decision is not None,"PREARMED_EXACT_ARGUMENTS")
        result=seal(args.config,args.seal_findings,args.decision)
    print(h.canonical(result).decode(),end="",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as error:
        print(h.canonical(safe_failure(error)).decode(),end="",flush=True)
        raise SystemExit(1)

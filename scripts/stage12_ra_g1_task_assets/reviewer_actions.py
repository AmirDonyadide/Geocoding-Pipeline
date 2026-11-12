"""Pure fixed reviewer actions; no production-module imports or child launches."""
import hashlib
import importlib.util
from pathlib import Path
OPS_SHA256 = "6a960a99dd7dd49ac092584e4cdf3649179aebf16d109bbdc481d5bf64fa1b25"
path=Path(__file__).with_name("prearmed_handoff.py")
if hashlib.sha256(path.read_bytes()).hexdigest()!=OPS_SHA256:
    raise RuntimeError("FROZEN_REVIEW_ACTION_SOURCE_CHANGED")
spec=importlib.util.spec_from_file_location("frozen_prearmed_review_actions",path)
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)

def claim(config_path, role):
    return ops.claim_independent(config_path,role)

def completed(config_path, role, *, actual_returncode):
    return ops.complete_independent(config_path,role,returncode=actual_returncode)

def decide(config_path, role, *, verdict, examined):
    """The explicit nonauthor verdict is supplied, never defaulted or inferred."""
    ops.need(role in ("FACTUAL_SEAL","EXACT_SEAL"),"PREARMED_REVIEW_ROLE")
    ops.need(verdict in ("PASS_ALL_REQUIRED","REFUSE"),"PREARMED_REVIEW_VERDICT")
    if verdict=="REFUSE":
        return dict(status="INDEPENDENT_REVIEWER_REFUSED_NO_DECISION_ACTIVATED")
    ops.need(examined=="EXAMINED_CURRENT_FINDINGS_AND_ORIGINALS","PREARMED_REVIEW_EXAMINATION_REQUIRED")
    cfg,_,_=ops.pure_configuration(config_path)
    state=Path(cfg["state_dir"]);review=Path(cfg["review_dir"])
    checker_role="CHECKER" if role=="FACTUAL_SEAL" else "EXACT_CHECKER"
    request=ops.parse(ops.read_original(state/(checker_role+"_REQUEST.record"),8192))
    completion=ops.parse(ops.read_original(state/(checker_role+".completed.record"),8192))
    report_raw=ops.read_original(review/("FACTUAL_CHECKER_FINDINGS.record" if role=="FACTUAL_SEAL" else "EXACT_CHECKER_FINDINGS.record"),2**20)
    report=ops.parse(report_raw)
    ops.need(report["required_checks"]=="ALL_COMPLETED" and report["authority"]=="NONE_FINDINGS_ONLY"
        and report["evidence_use"]=="FRESH_SAME_ALLOCATION_FINDINGS_ONLY"
        and report["source_sha"]==cfg["source_sha"] and str(report["job_id"])==cfg["job_id"]
        and report["selection_sha256"]==cfg["selection"]["sha256"]
        and report["resource_selection_sha256"]==cfg["resource_selection"]["sha256"]
        and report["checker_input_sha256"]==request["checker_input_sha256"]
        and report["checker_sha256"]==request["script_sha256"]
        and completion["returncode"]==0 and completion["report_sha256"]==ops.sha(report_raw)
        and completion["request_sha256"]==ops.sha(ops.read_original(state/(checker_role+"_REQUEST.record"),8192)),
        "PREARMED_REVIEW_BINDING")
    common=dict(disposition=verdict,checker_input_sha256=report["checker_input_sha256"],
        source_sha=cfg["source_sha"],job_id=cfg["job_id"],selection_sha256=cfg["selection"]["sha256"],
        resource_selection_sha256=cfg["resource_selection"]["sha256"],reviewed_utc=ops.z(ops.now_utc()))
    if role=="FACTUAL_SEAL":
        ready_raw=ops.read_original(state/"COLLECTOR_READY.record",2**20)
        decision=dict(common,schema_version="stage12_independent_factual_decision_v1",
            checker_report_sha256=ops.sha(report_raw),collector_ready_sha256=ops.sha(ready_raw),
            originals_tar_sha256=report["originals_tar_sha256"],
            originals_inventory_sha256=report["originals_inventory_sha256"])
    else:
        decision=dict(common,schema_version="stage12_independent_exact_input_decision_v1",
            findings_sha256=ops.sha(report_raw),input_sha256=report["input_sha256"],
            review_binding_sha256=report["review_binding_sha256"],
            factual_review_sha256=report["factual_review_sha256"])
    return ops.write_decision(config_path,role,decision)

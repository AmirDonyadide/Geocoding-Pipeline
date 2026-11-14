"""Direct synthetic-original recovery; no paired completion or workload acceptance."""
from __future__ import annotations
import time
ENTRY_MONO_NS = time.monotonic_ns()
ENTRY_EPOCH_NS = time.time_ns()
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import stat
import sys
import stage12_ra_g1_terminal_collect as tc
import stage12_ra_g1_terminal_parent as parent
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_verify as verifier
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics

PLAN_VERSION = "stage12_direct_terminal_recovery_plan_v1"
RESULT_VERSION = "stage12_direct_terminal_recovery_integrity_v1"
REVIEW_VERSION = "stage12_direct_terminal_recovery_independent_review_v1"
REOPEN_VERSION = "stage12_direct_terminal_recovery_reopen_v1"
EXPORT_VERSION = "stage12_direct_terminal_export_v1"
WORKLOAD_VERSION = "stage12_direct_recovery_original_workload_v1"
SCOPE = "DIRECT_TERMINAL_RECOVERY_NO_SERVICE"
POOL_BYTES, POOL_CREATIONS = 24*2**30, 450000
DIRECT_CONSUMER_PATHS = (
    "scripts/stage12_ra_g1_direct_recovery.py",
    "scripts/stage12_ra_g1_terminal_collect.py",
    "scripts/stage12_ra_g1_terminal_transport.py",
    "scripts/stage12_ra_g1_terminal_parent.py",
    "scripts/stage12_ra_g1_terminal_verify.py",
    "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_diagnostics.py",
    "cluster/goethe_nhr/stage12_ra_g1_direct_export.sbatch",
)
ARTIFACTS = (("selection", "selection.record", 65536),
             ("archive", "terminal.s12c", 3*2**30),
             ("before", "before.jsonl", 128*2**20),
             ("after", "after.jsonl", 128*2**20),
             ("workload", "WORKLOAD_VERIFICATION.record", 1048576))
CODES = frozenset(("DIRECT_PLAN", "DIRECT_SOURCE", "DIRECT_COHORT", "DIRECT_EXPORT",
                   "DIRECT_DEADLINE", "DIRECT_PROOF", "DIRECT_REVIEW", "DIRECT_MIRROR",
                   "TERMINAL_ORIGINAL_INVALID","TERMINAL_PROOF_WRITE_OR_EXTERNAL_DENIED"))


def need(value, code="DIRECT_PLAN"):
    if not value:
        raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def consumer_digest(rows):
    need(type(rows) is list and [row["path"] for row in rows] == sorted(DIRECT_CONSUMER_PATHS))
    for row in rows:
        need(type(row) is dict and set(row) == {"path", "bytes", "sha256"})
        tc.uint(row["bytes"], True);parent.hash_string(row["sha256"])
        need(row["bytes"] <= 262144)
    return digest(tc.canonical(rows))


def validate_plan(plan, *, offline=False, test_root=None):
    parent.fields(plan, "version scope nonce approval_sha256 purpose originals software selection_template allowed_inert_fifos required_inert_fifos export_logs original_workload window_end_epoch_ns test_only")
    need(plan["version"] == PLAN_VERSION and plan["scope"] == SCOPE
         and type(plan["test_only"]) is bool and plan["test_only"] == offline)
    need(type(plan["nonce"]) is str and __import__("re").fullmatch(r"[0-9a-f]{32}", plan["nonce"]))
    parent.hash_string(plan["approval_sha256"])
    need(plan["approval_sha256"] != "0"*64 and plan["purpose"] in ("OLD_B_F_RECOVERY", "POST_B"))
    parent.fields(plan["software"], "source_git_sha inventory_sha256 consumer_inventory")
    software = plan["software"]
    need(type(software["source_git_sha"]) is str
         and __import__("re").fullmatch(r"[0-9a-f]{40}", software["source_git_sha"]))
    need(software["inventory_sha256"] == consumer_digest(software["consumer_inventory"]), "DIRECT_SOURCE")
    originals = plan["originals"]
    need(type(originals) is list and len(originals) == (2 if plan["purpose"] == "OLD_B_F_RECOVERY" else 1))
    need([row["role"] for row in originals] == (["B", "F"] if len(originals) == 2 else ["B"]))
    for row in originals:
        parent.fields(row, "role job_id source_git_sha identity_kind identity_sha256 terminal_sha256")
        tc.uint(row["job_id"], True)
        need(__import__("re").fullmatch(r"[0-9a-f]{40}", row["source_git_sha"]))
        need(row["identity_kind"] == ("ALLOCATION_SELECTION" if row["role"] == "B" else "COLLECTION_BINDING"))
        parent.hash_string(row["identity_sha256"]);parent.hash_string(row["terminal_sha256"])
    need(len({row["job_id"] for row in originals}) == len(originals))
    value = deepcopy(plan["selection_template"])
    need(value["version"] == tc.FIFO_VERSION and value["state"] == "TEMPLATE"
         and value["approval_sha256"] is None and value["inert_fifos"] == [])
    need(value["job_id"] == originals[0]["job_id"]
         and value["source_git_sha"] == originals[0]["source_git_sha"])
    need(value["valid_until_epoch_ns"] == plan["window_end_epoch_ns"])
    if not offline:
        need(value["limits"] == parent.PRACTICAL)
        base = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/client_diagnostics")
        for row in value["roots"]:
            path = tc.absolute(row["path"])
            need(path != base and tc.contained(path, base), "DIRECT_COHORT")
        for row in value["external_files"]:
            need(tc.contained(tc.absolute(row["path"]), base), "DIRECT_COHORT")
    value.update(state="TEST_ONLY" if offline else "ISSUED",
                 approval_sha256=None if offline else plan["approval_sha256"])
    selected = tc.Selection(value, offline, test_root)
    allowed = plan["allowed_inert_fifos"]
    need(type(allowed) is list and len(allowed) <= 16 and len(set(allowed)) == len(allowed))
    for logical in allowed:
        parts = selected.relative(logical).split("/")
        need(len(parts) > 1 and parts[0] in selected.roots and logical not in selected.logs)
    required = plan["required_inert_fifos"]
    need(type(required) is list and len(set(required)) == len(required)
         and set(required) <= set(allowed))
    logs=plan["export_logs"]
    need(type(logs) is list and [row["label"] for row in logs]==["export_stdout","export_stderr"])
    for row in logs:
        parent.fields(row,"label path");path=tc.absolute(row["path"])
        if offline: need(tc.contained(path,test_root) and path!=test_root,"DIRECT_COHORT")
        else: need(tc.contained(path,base) and path!=base,"DIRECT_COHORT")
    need(logs[0]["path"]!=logs[1]["path"],"DIRECT_COHORT")
    work=plan["original_workload"]
    parent.fields(work,"selection_path selection_sha256 verifier_sha256 required_for_B_acceptance")
    path=tc.absolute(work["selection_path"])
    need(any(tc.contained(path,root) for root in selected.roots.values())
         or path in selected.external.values(),"DIRECT_COHORT")
    need(work["selection_sha256"]==originals[0]["identity_sha256"]
         and work["verifier_sha256"]==next(row["sha256"] for row in software["consumer_inventory"]
             if row["path"]=="scripts/stage12_ra_g1_terminal_verify.py")
         and type(work["required_for_B_acceptance"]) is bool
         and work["required_for_B_acceptance"]==(plan["purpose"]=="POST_B"),"DIRECT_COHORT")
    return selected


def _selected_cohort(plan,value,*,offline,test_root):
    base=validate_plan(plan,offline=offline,test_root=test_root)
    selected=tc.Selection(value,offline,test_root)
    expected=deepcopy(base.value);expected["inert_fifos"]=value["inert_fifos"]
    need(value==expected and set(plan["required_inert_fifos"])<=set(selected.inert)
         <=set(plan["allowed_inert_fifos"]),"DIRECT_COHORT")
    return selected


class _ReadBudget(tc.Budget):
    def __init__(self, selected, entered, maximum_calls):
        super().__init__(selected, entered)
        self.read_calls, self.maximum_calls = 0, maximum_calls
    def read(self, fd, amount):
        need(self.maximum_calls is None or self.read_calls < self.maximum_calls, "DIRECT_PROOF")
        self.read_calls += 1
        return super().read(fd, amount)


class Role:
    """The existing codec budget, shared by transfer, decode and local reopen."""
    def __init__(self, selected, entered, epoch_end, *, review=False, native_export=False, initial_control=None):
        self.budget = _ReadBudget(selected, entered, None if native_export else 131072 if review else 262144)
        if review:
            self.budget.end = min(self.budget.end, entered + 120*10**9)
            self.budget.l = dict(self.budget.l, read_bytes=min(self.budget.l["read_bytes"], 4*2**30))
        self.budget.epoch_end = min(self.budget.epoch_end, epoch_end)
        if initial_control is not None:
            self.budget.counts["read_bytes"]=initial_control.read_bytes
            self.budget.read_calls=initial_control.read_calls
            need(self.budget.counts["read_bytes"]<=self.budget.l["read_bytes"]
                 and (self.budget.maximum_calls is None or self.budget.read_calls<=self.budget.maximum_calls),"DIRECT_PROOF")
        self.wire_bytes = 0
    @property
    def read_calls(self): return self.budget.read_calls
    @property
    def end(self): return self.budget.end
    @property
    def epoch_end(self): return self.budget.epoch_end
    @property
    def cleanup_uncertain(self): return self.budget.cleanup_uncertain
    @cleanup_uncertain.setter
    def cleanup_uncertain(self, value): self.budget.cleanup_uncertain = value
    @property
    def read_bytes(self): return self.budget.counts["read_bytes"]
    def check(self): self.budget.check()
    def read(self, fd, amount):
        return self.budget.read(fd, amount)
    def claim(self, amount, creation=False):
        if creation: self.budget.claim("creations", 1)
        self.budget.claim("write_bytes", amount)


class Transfer:
    def __init__(self, role): self.role = role
    def __getattr__(self, name): return getattr(self.role, name)
    @property
    def cleanup_uncertain(self): return self.role.cleanup_uncertain
    @cleanup_uncertain.setter
    def cleanup_uncertain(self, value): self.role.cleanup_uncertain = value
    def read(self, fd, amount):
        # One cumulative plaintext framing/payload stop, not one per batch.
        tc.need(self.role.wire_bytes + amount <= self.role.budget.l["wire_bytes"], "WIRE_BYTES")
        raw = self.role.read(fd, amount)
        self.role.wire_bytes += len(raw)
        return raw


def _write(path, raw, budget):
    fd = tc.create_file(path, budget)
    try:
        budget.write(fd, raw);tc.finish_file(fd, path, budget)
    finally: tc.close_owned(budget, (fd,))


def _source_map(plan, role):
    prepared = diagnostics.FirstFailureDescriptor()
    source_root = Path(__file__).absolute().parent.parent
    rows = plan["software"]["consumer_inventory"]
    # Mandatory executable identity is never weakened by diagnostic uncertainty.
    for row in rows:
        parent.source_hash(source_root/row["path"], row["sha256"], role)
    try:
        modules = [("DIRECT_RECOVERY", sys.modules[__name__]), ("COLLECTION_CORE", tc),
                   ("COLLECTION_PARENT", parent), ("COLLECTION_TRANSPORT", transport),
                   ("COLLECTION_VERIFIER",verifier)]
        calls = [0]
        class Pins:
            @property
            def cleanup_uncertain(self): return role.cleanup_uncertain
            @cleanup_uncertain.setter
            def cleanup_uncertain(self, value): role.cleanup_uncertain = value
            def check(self): role.check()
            def read(self, fd, amount):
                need(calls[0] < 64, "DIRECT_SOURCE");calls[0] += 1
                return role.read(fd, amount)
        def verify(path, row):
            parent.source_hash(path, row["sha256"], Pins());return True
        prepared = diagnostics.prepare_direct_recovery_failure_descriptor(
            modules, rows, source_root=source_root, verify_source=verify)
    except BaseException:
        pass
    return prepared


def _failure(error, operation, prepared):
    try: first = prepared.capture(error)
    except BaseException:
        first = dict(exception_class="UNKNOWN",frames=[],retention_uncertain=True)
    code = parent.safe_code(error)
    if type(error) is RuntimeError and len(error.args) == 1 and type(error.args[0]) is str and error.args[0] in CODES:
        code = error.args[0]
    return dict(status="INCOMPLETE", operation=operation, code=code, first_failure=first,
                observed_mono_ns=time.monotonic_ns(), observed_epoch_ns=time.time_ns(),
                historical_cause_not_inferred=True)


def _bind_fifos(plan, selected):
    value = deepcopy(selected.value)
    status = []
    for logical in plan["allowed_inert_fifos"]:
        parts = logical.split("/")
        root = selected.roots[parts[0]]
        tc.ancestors(root);tc.private(root.lstat(), "DIR", selected.uid, selected.gid)
        path = root.joinpath(*parts[1:]);chain = tc.ancestors(path)
        try: info = path.lstat()
        except FileNotFoundError:
            need(logical not in plan["required_inert_fifos"], "DIRECT_COHORT")
            tc.check_ancestors(chain);status.append(dict(path=logical, status="ABSENT_ENOENT"));continue
        tc.need(stat.S_ISFIFO(info.st_mode), "SPECIAL")
        tc.need(stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1
                and [info.st_uid, info.st_gid] == [selected.uid, selected.gid], "PRIVATE")
        tc.check_ancestors(chain)
        value["inert_fifos"].append(dict(path=logical, identity=list(tc.ident(info))))
        status.append(dict(path=logical, status="PRESENT_INERT_ONLY", identity=list(tc.ident(info))))
    return value, status


def cohort_matches(plan, selection):
    template = plan["selection_template"]
    return all(selection.get(key) == template.get(key)
               for key in ("version", "source_uid", "source_gid", "roots", "external_files",
                           "required_logs", "job_id", "source_git_sha"))


def _publish_manifests(output, selected, summary, role):
    # The unchanged Sorter retains every generation. Its final run is derived
    # from the actual member count and its fixed row-count/fan-in algorithm.
    runs=(summary["members"]+selected.limits["sort_records"]-1)//selected.limits["sort_records"]
    generation=0
    while runs>1:
        runs=(runs+selected.limits["merge_fan_in"]-1)//selected.limits["merge_fan_in"]
        generation+=1
    for phase in ("before","after"):
        target=output/(phase+".jsonl");fd=tc.create_file(target,role.budget);source=None
        try:
            origin="scientific_after" if phase=="after" else phase
            source=parent._FreshReader(output/f"{origin}.g{generation:02d}.r00000000.jsonl",role,selected.limits["manifest_bytes"])
            while raw:=source.read(65536): role.budget.write(fd,raw)
            actual=source.finish()
            need(actual["bytes"]==summary["manifest_bytes"] and actual["sha256"]==summary["manifest_sha256"],"DIRECT_EXPORT")
            tc.finish_file(fd,target,role.budget)
        finally:
            if source is not None: source.close()
            tc.close_owned(role.budget,(fd,))


def _workload(plan,role,prepared):
    """Actual original native-path reader, with no new owner or read allowance."""
    work=plan["original_workload"]
    raw=parent.read_original(Path(work["selection_path"]),role,1048576)
    need(digest(raw)==work["selection_sha256"],"DIRECT_COHORT")
    original=tc.parse(raw)
    need(original.get("source_sha")==plan["originals"][0]["source_git_sha"],"DIRECT_COHORT")
    result=dict(version=WORKLOAD_VERSION,original_source_sha=original["source_sha"],
        original_selection_sha256=work["selection_sha256"],verifier_sha256=work["verifier_sha256"],
        required_for_B_acceptance=work["required_for_B_acceptance"],complete=False,
        status="VERIFIER_REJECTED_OR_UNSUPPORTED",proof=None,first_failure=None,
        original_timed_acceptance_repaired=False)
    def check_read(amount):
        role.check();tc.uint(amount)
        tc.need(role.budget.counts["read_bytes"]+amount<=role.budget.l["read_bytes"],"READ_BYTES")
        need(role.budget.maximum_calls is None or role.read_calls<role.budget.maximum_calls,"DIRECT_PROOF")
        role.budget.read_calls+=1
    def charge_read(amount): role.budget.claim("read_bytes",amount)
    try:
        actual=verifier.verify_original_workload(original,check=role.check,
            charge_read=charge_read,check_read=check_read)
        need(type(actual) is dict and type(actual.get("complete")) is bool
             and actual.get("source_sha")==original["source_sha"]
             and actual.get("allocation_selection_sha256")==work["selection_sha256"],"DIRECT_PROOF")
        result.update(complete=actual["complete"],status=actual["status"],proof=actual)
    except Exception as error:
        # Unsupported/incomplete scientific originals remain negative evidence;
        # exhaustion or cleanup uncertainty cannot be turned into recovery.
        failure=_failure(error,"SCIENTIFIC_REOPEN",prepared)
        if type(error) is tc.Stop or role.cleanup_uncertain:
            try: error.direct_recovery_failure=failure
            except BaseException: pass
            raise
        result["first_failure"]=failure
    parent.source_hash(Path(__file__).absolute().parent/"stage12_ra_g1_terminal_verify.py",work["verifier_sha256"],role)
    need(len(tc.canonical(result))<=1048576,"DIRECT_PROOF")
    role.check();return result


def export_archive(plan, output, *, export_end_epoch_ns, offline=False, test_root=None, initial_control=None):
    selected = validate_plan(plan, offline=offline, test_root=test_root)
    if not offline:
        from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
        require_goethe_nhr_slurm("stage12_direct_terminal_recovery_export")
        need(os.environ.get("STAGE12_DR_SHA") == plan["software"]["source_git_sha"]
             and os.environ.get("STAGE12_DR_SOURCE") == str(Path(__file__).absolute().parent.parent),
             "DIRECT_SOURCE")
    role = Role(selected, ENTRY_MONO_NS, min(plan["window_end_epoch_ns"], export_end_epoch_ns),
                native_export=True,initial_control=initial_control)
    prepared = diagnostics.FirstFailureDescriptor();operation = "VERIFY_SOFTWARE"
    try:
        prepared = _source_map(plan, role);operation = "BIND_SOURCE"
        value, fifo_status = _bind_fifos(plan, selected)
        selected = tc.Selection(value, offline, test_root)
        output = tc.absolute(str(output));selected.disjoint_output(output, test_root if offline else None)
        if not offline:
            base=Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline/derived/controlled/stage12/client_diagnostics")
            need(output!=base and tc.contained(output,base),"DIRECT_COHORT")
        tc.mkdir(output, role.budget)
        _write(output/"selection.record", tc.canonical(value), role.budget)
        operation = "EXPORT"
        fd = tc.create_file(output/"terminal.s12c", role.budget)
        stream=os.fdopen(fd,"wb",buffering=0)
        try:
            exported = tc.export(selected, output, stream, role.budget)
            tc.finish_file(stream.fileno(), output/"terminal.s12c", role.budget)
        finally:
            active=sys.exc_info()[1]
            try: stream.close()
            except BaseException:
                role.cleanup_uncertain=True
                if active is None: raise tc.Stop("CLOSE_UNCERTAIN")
        operation="SCIENTIFIC_REOPEN"
        workload=_workload(plan,role,prepared)
        # Cover the original verifier as well as export with the same complete
        # source identity/hash namespace. No success can join mismatched data.
        operation="POST_SCIENTIFIC_SOURCE_INVENTORY"
        final_source=tc.make_manifest(output,"scientific_after",tc.Source(selected,role.budget),selected,role.budget)
        need(tc.summarize(final_source,selected,role.budget)==exported["summary"],"DIRECT_COHORT")
        _write(output/"WORKLOAD_VERIFICATION.record",tc.canonical(workload),role.budget)
        operation = "EXPORT_READBACK"
        _publish_manifests(output,selected,exported["summary"],role)
        artifacts = []
        for label, name, maximum in ARTIFACTS:
            fact = parent.hash_original(output/name, role, maximum)
            artifacts.append(dict(label=label, name=name, bytes=fact["bytes"], sha256=fact["sha256"],
                                  identity=fact["identity"]))
        job = 0 if offline else int(os.environ["SLURM_JOB_ID"])
        need(offline or job not in {row["job_id"] for row in plan["originals"]}, "DIRECT_EXPORT")
        result = dict(version=EXPORT_VERSION, status="EXPORT_COMPLETE_NOT_LOCAL_RECOVERY",
            plan_sha256=digest(tc.canonical(plan)), selection_sha256=selected.sha,
            software_source_sha=plan["software"]["source_git_sha"],
            export_job_id=job, artifacts=artifacts, summary=exported["summary"], fifo_status=fifo_status,
            scientific_after_source_manifest_verified=True,
            entry_mono_ns=ENTRY_MONO_NS, entry_epoch_ns=ENTRY_EPOCH_NS,
            deadline_mono_ns=role.end, export_end_epoch_ns=role.epoch_end,
            completed_mono_ns=time.monotonic_ns(), completed_epoch_ns=time.time_ns(),
            counters=dict(role.budget.counts), read_calls=role.read_calls,cleanup_uncertain=role.cleanup_uncertain,
            original_outcomes_unchanged=True, native_or_scientific_acceptance=False)
        role.check();need(not role.cleanup_uncertain, "DIRECT_EXPORT")
        _write(output/"DIRECT_EXPORT.record", tc.canonical(result), role.budget)
        need(parent.read_original(output/"DIRECT_EXPORT.record", role, 65536) == tc.canonical(result))
        role.check()
        return result
    except BaseException as error:
        failure = _failure(error, operation, prepared)
        try: error.direct_recovery_failure = failure
        except BaseException: pass
        failure["cleanup_uncertain"] = role.cleanup_uncertain
        if role.budget.output_path is not None:
            try: _write(output/"DIRECT_EXPORT_INCOMPLETE.record", tc.canonical(failure), role.budget)
            except BaseException: failure["retention_uncertain"] = True
        raise


def _opener_view(selected, archive, end):
    # A data-only adapter to the existing generic opener. No READY is asserted,
    # constructed, received, published or required anywhere in this workflow.
    return dict(collection_selection=selected.value,
        scope=parent.TEST if selected.value["scope"] == "TEST_ONLY_INVENTED" else parent.NATIVE,
        context=dict(selection_sha256=selected.sha, overall_deadline_epoch_ns=end),
        artifacts=[dict(bytes=archive["bytes"], sha256=archive["sha256"])])


def recover_archive(plan, remote_output, local_output, *, export_terminal,
                    offline=False, test_root=None, testing_batch_factory=None, entry=None, initial_control=None):
    entered, epoch = (time.monotonic_ns(),time.time_ns()) if entry is None else entry
    base_selected = validate_plan(plan, offline=offline, test_root=test_root)
    role = Role(base_selected, entered, plan["window_end_epoch_ns"],initial_control=initial_control)
    prepared = diagnostics.FirstFailureDescriptor();operation = "VERIFY_SOFTWARE"
    output = tc.absolute(str(local_output))
    discovery, artifacts, mirror = (output/name for name in ("discovery", "artifacts", "mirror"))
    wire = Transfer(role)
    def fetch(rows, target):
        # Existing transport writes raw file data directly. Reserve its complete
        # admitted size before any write; no byte can evade the role's8GiB stop.
        role.budget.claim("write_bytes", sum(row.get("bytes",row.get("maximum")) for row in rows))
        kwargs = dict(expected_uid=base_selected.uid, expected_gid=base_selected.gid,
            local_directory_scope=transport.TASK_LOCAL_DIRECTORY_SCOPE,
            remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)
        if testing_batch_factory is not None:
            need(offline);kwargs.update(testing_argv=testing_batch_factory(rows), nonce="1"*32)
        return transport.fetch_batch(rows, target, wire, **kwargs)[0]
    try:
        prepared = _source_map(plan, role);operation = "LOCAL_CREATE"
        tc.mkdir(output, role.budget)
        # Precreate siblings before taking the immutable source archive's chain.
        for path in (discovery, artifacts, mirror): tc.mkdir(path, role.budget)
        operation = "DISCOVERY_TRANSFER"
        discovery_rows = [dict(label=label,path=str(Path(remote_output)/name),maximum=65536,
                               local_name=label+".original")
                          for label,name in (("selection","selection.record"),("export","DIRECT_EXPORT.record"))]
        first = fetch(discovery_rows, discovery)
        selection_raw = parent.read_original(discovery/"selection.original", role, 65536)
        selection_value = tc.parse(selection_raw)
        selected=_selected_cohort(plan,selection_value,offline=offline,test_root=test_root)
        exported_raw = parent.read_original(discovery/"export.original", role, 65536)
        exported = tc.parse(exported_raw)
        need(exported["version"] == EXPORT_VERSION and exported["status"] == "EXPORT_COMPLETE_NOT_LOCAL_RECOVERY"
             and exported["plan_sha256"] == digest(tc.canonical(plan))
             and exported["selection_sha256"] == digest(selection_raw)
             and exported["cleanup_uncertain"] is False, "DIRECT_EXPORT")
        need(exported["completed_mono_ns"] < exported["deadline_mono_ns"]
             and exported["completed_epoch_ns"] < exported["export_end_epoch_ns"], "DIRECT_DEADLINE")
        if offline:
            need(export_terminal == dict(kind="TEST_ONLY_ACTUAL_LOCAL_CHILD",exit_code=0), "DIRECT_EXPORT")
        else:
            need(export_terminal["kind"] == "SLURM_TERMINAL"
                 and export_terminal["job_id"] == exported["export_job_id"]
                 and export_terminal["scheduler_state"] == "COMPLETED"
                 and export_terminal["exit_code"] == 0 and export_terminal["signal"] == 0, "DIRECT_EXPORT")
            parent.hash_string(export_terminal["submission_sha256"]);parent.hash_string(export_terminal["terminal_sha256"])
        rows = []
        for label,name,maximum in ARTIFACTS:
            source = next(row for row in exported["artifacts"] if row["label"] == label)
            need(source["name"] == name and source["bytes"] <= maximum, "DIRECT_EXPORT")
            rows.append(dict(label=label,path=str(Path(remote_output)/name),bytes=source["bytes"],
                             sha256=source["sha256"],local_name=label+".original"))
        rows.append(dict(label="export",path=str(Path(remote_output)/"DIRECT_EXPORT.record"),
                         bytes=len(exported_raw),sha256=digest(exported_raw),local_name="export.original"))
        rows.extend(dict(**row,maximum=65536,local_name=row["label"]+".original") for row in plan["export_logs"])
        operation = "COMPLETE_TRANSFER"
        transfer = fetch(rows, artifacts)
        need(parent.read_original(artifacts/"selection.original",role,65536) == selection_raw, "DIRECT_COHORT")
        workload_raw=parent.read_original(artifacts/"workload.original",role,1048576)
        need(digest(workload_raw)==next(row["sha256"] for row in rows if row["label"]=="workload"),"DIRECT_PROOF")
        workload=tc.parse(workload_raw)
        operation = "LOCAL_DECODE_AND_MIRROR"
        source = parent._FreshReader(artifacts/"archive.original", role, rows[1]["bytes"])
        try:
            decoded = tc.receive(selected, mirror, source, role.budget)
            archive_identity = source.finish()
        finally: source.close()
        need(decoded["summary"] == exported["summary"] and decoded["archive_sha256"] == rows[1]["sha256"]
             and archive_identity["sha256"] == rows[1]["sha256"] and decoded["independently_rehashed"] is True)
        operation = "DURABLE_LOCAL_REOPEN"
        archive, opened = parent.open_retained_archive(
            _opener_view(selected,rows[1],role.epoch_end),artifacts,role)
        need(opened["summary"] == decoded["summary"] and archive["sha256"] == decoded["archive_sha256"])
        bindings = [dict(label=label,original_path=str(path),local_path=str(mirror/"originals"/label))
                    for label,path in {**selected.roots,**selected.external}.items()]
        role.check();need(not role.cleanup_uncertain, "DIRECT_PROOF")
        inventory = plan["software"]["consumer_inventory"]
        result = dict(version=RESULT_VERSION,status="DIRECT_RECOVERY_INTEGRITY_COMPLETE_PENDING_REVIEW",
            scope=SCOPE,plan_sha256=digest(tc.canonical(plan)),originals=deepcopy(plan["originals"]),
            software_source_sha=plan["software"]["source_git_sha"],
            software_inventory_sha256=plan["software"]["inventory_sha256"],
            recovery_consumer_inventory=deepcopy(inventory),recovery_consumer_inventory_sha256=consumer_digest(inventory),
            selection=selection_value,selection_sha256=selected.sha,export=exported,export_terminal=export_terminal,
            transport=dict(discovery=first,complete=transfer),archive_open=opened,workload_verification=workload,
            mirror=dict(status="COMPLETE_SOURCE_MEMBERSHIP_REHASHED",summary=decoded["summary"],
                        archive_sha256=decoded["archive_sha256"],bindings=bindings,inert_root=str(mirror/"inert-metadata")),
            durable_local=dict(fsync_and_source_readback=True,archive_identity=archive["identity"]),
            entry_mono_ns=entered,entry_epoch_ns=epoch,deadline_mono_ns=role.end,
            window_end_epoch_ns=role.epoch_end,completed_mono_ns=time.monotonic_ns(),completed_epoch_ns=time.time_ns(),
            role_counters=dict(role.budget.counts),transport_wire_bytes=role.wire_bytes,
            cleanup_uncertain=False,original_outcomes_unchanged=True,native_or_scientific_acceptance=False)
        raw = tc.canonical(result);need(len(raw) <= 2**20, "DIRECT_PROOF")
        _write(output/"DIRECT_RECOVERY_RESULT.record",raw,role.budget)
        need(parent.read_original(output/"DIRECT_RECOVERY_RESULT.record",role,2**20) == raw, "DIRECT_PROOF")
        role.check()
        return result
    except BaseException as error:
        failure = _failure(error,operation,prepared)
        try: error.direct_recovery_failure = failure
        except BaseException: pass
        failure.update(cleanup_uncertain=role.cleanup_uncertain,
                       transport=getattr(error,"transport_diagnostic",None))
        try: _write(output/"DIRECT_RECOVERY_INCOMPLETE.record",tc.canonical(failure),role.budget)
        except BaseException: failure["retention_uncertain"] = True
        raise


def _integrity(proof, *, allow_test_only=False):
    parent.fields(proof, "version status scope plan_sha256 originals software_source_sha software_inventory_sha256 recovery_consumer_inventory recovery_consumer_inventory_sha256 selection selection_sha256 export export_terminal transport archive_open workload_verification mirror durable_local entry_mono_ns entry_epoch_ns deadline_mono_ns window_end_epoch_ns completed_mono_ns completed_epoch_ns role_counters transport_wire_bytes cleanup_uncertain original_outcomes_unchanged native_or_scientific_acceptance")
    need(len(tc.canonical(proof)) <= 2**20, "DIRECT_PROOF")
    need(proof["version"] == RESULT_VERSION and proof["status"] == "DIRECT_RECOVERY_INTEGRITY_COMPLETE_PENDING_REVIEW"
         and proof["scope"] == SCOPE, "DIRECT_PROOF")
    testing = proof["selection"]["scope"] == "TEST_ONLY_INVENTED"
    need(not testing or allow_test_only, "DIRECT_PROOF")
    selected = tc.Selection(proof["selection"], testing,
        Path(proof["selection"]["roots"][0]["path"]).parent if testing else None)
    need(selected.sha == proof["selection_sha256"] == proof["archive_open"]["selection_sha256"]
         and selected.value["job_id"] == proof["originals"][0]["job_id"]
         and selected.value["source_git_sha"] == proof["originals"][0]["source_git_sha"], "DIRECT_PROOF")
    parent.fields(proof["transport"], "discovery complete")
    for evidence in proof["transport"].values():
        parent.validate_transport_evidence(evidence, remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)
    files = proof["transport"]["complete"]["files"]
    need([row["label"] for row in files] == ["selection","archive","before","after","workload","export","export_stdout","export_stderr"]
         and [row["label"] for row in proof["transport"]["discovery"]["files"]] == ["selection","export"], "DIRECT_PROOF")
    lookup = {row["label"]:row for row in files}
    exported = proof["export"]
    need(exported["version"] == EXPORT_VERSION and exported["status"] == "EXPORT_COMPLETE_NOT_LOCAL_RECOVERY"
         and exported["plan_sha256"] == proof["plan_sha256"]
         and exported["selection_sha256"] == selected.sha
         and exported["software_source_sha"] == proof["software_source_sha"]
         and exported["cleanup_uncertain"] is False
         and exported["scientific_after_source_manifest_verified"] is True
         and exported["original_outcomes_unchanged"] is True
         and exported["native_or_scientific_acceptance"] is False, "DIRECT_PROOF")
    need([row["label"] for row in exported["artifacts"]] == [row[0] for row in ARTIFACTS], "DIRECT_PROOF")
    for row, (label,name,maximum) in zip(exported["artifacts"], ARTIFACTS):
        need(row["name"] == name and row["bytes"] <= maximum
             and (row["bytes"],row["sha256"]) == (lookup[label]["bytes"],lookup[label]["sha256"]), "DIRECT_PROOF")
    need(lookup["selection"]["sha256"] == selected.sha
         and lookup["export"]["sha256"] == digest(tc.canonical(exported)), "DIRECT_PROOF")
    work=proof["workload_verification"]
    need(work["version"]==WORKLOAD_VERSION and type(work["complete"]) is bool
         and work["original_source_sha"]==proof["originals"][0]["source_git_sha"]
         and work["original_selection_sha256"]==proof["originals"][0]["identity_sha256"]
         and work["verifier_sha256"]==next(row["sha256"] for row in proof["recovery_consumer_inventory"]
              if row["path"]=="scripts/stage12_ra_g1_terminal_verify.py")
         and digest(tc.canonical(work))==lookup["workload"]["sha256"]
         and work["original_timed_acceptance_repaired"] is False,"DIRECT_PROOF")
    if work["complete"]:
        need(work["first_failure"] is None and work["proof"]["complete"] is True
             and work["status"]==work["proof"]["status"]=="FRESH_ORIGINAL_CONTENT_AND_TIMED_RECORDS_VERIFIED"
             and work["proof"]["allocation_selection_sha256"]==work["original_selection_sha256"]
             and work["proof"]["source_sha"]==work["original_source_sha"],"DIRECT_PROOF")
    for row in proof["transport"]["discovery"]["files"]:
        need((row["sha256"],row["bytes"],row["path"]) == tuple(lookup[row["label"]][key] for key in ("sha256","bytes","path")), "DIRECT_PROOF")
    archive = lookup["archive"]
    opened = proof["archive_open"]
    parent.fields(opened,"version status selection_sha256 archive_sha256 summary actual_read_bytes actual_read_calls entered_epoch_ns completed_epoch_ns source_identity native_or_scientific_acceptance")
    need(opened["version"] == "stage12_readonly_collection_archive_open_v1" and opened["status"] == "COMPLETE"
         and opened["archive_sha256"] == archive["sha256"]
         and opened["summary"] == proof["mirror"]["summary"] == exported["summary"]
         and opened["native_or_scientific_acceptance"] is False
         and opened["actual_read_bytes"] <= selected.limits["read_bytes"]
         and opened["actual_read_calls"] <= 262144, "DIRECT_PROOF")
    need(all(lookup[label]["sha256"]==opened["summary"]["manifest_sha256"]
             and lookup[label]["bytes"]==opened["summary"]["manifest_bytes"] for label in ("before","after")),"DIRECT_PROOF")
    bindings = proof["mirror"]["bindings"]
    need(type(bindings) is list and [row["label"] for row in bindings] == list({**selected.roots,**selected.external})
         and all(row["original_path"] == str({**selected.roots,**selected.external}[row["label"]]) for row in bindings), "DIRECT_MIRROR")
    for value in (proof,exported):
        need(type(value["entry_mono_ns"]) is int and type(value["entry_epoch_ns"]) is int
             and value["entry_mono_ns"] <= value["completed_mono_ns"] < value["deadline_mono_ns"]
             and value["deadline_mono_ns"]-value["entry_mono_ns"] <= selected.limits["seconds"]*10**9, "DIRECT_DEADLINE")
    need(exported["completed_epoch_ns"] < exported["export_end_epoch_ns"] <= proof["window_end_epoch_ns"]
         and proof["entry_epoch_ns"] <= proof["completed_epoch_ns"] < proof["window_end_epoch_ns"]
         and proof["transport_wire_bytes"] <= selected.limits["wire_bytes"], "DIRECT_DEADLINE")
    need(proof["mirror"]["archive_sha256"] == archive["sha256"]
         and proof["mirror"]["status"] == "COMPLETE_SOURCE_MEMBERSHIP_REHASHED"
         and proof["durable_local"]["fsync_and_source_readback"] is True
         and proof["durable_local"]["archive_identity"] == opened["source_identity"]
         and proof["cleanup_uncertain"] is False and proof["original_outcomes_unchanged"] is True
         and proof["native_or_scientific_acceptance"] is False, "DIRECT_PROOF")
    if testing:
        need(proof["export_terminal"] == dict(kind="TEST_ONLY_ACTUAL_LOCAL_CHILD",exit_code=0), "DIRECT_PROOF")
    else:
        terminal = proof["export_terminal"]
        need(terminal["kind"] == "SLURM_TERMINAL" and terminal["job_id"] == exported["export_job_id"]
             and terminal["scheduler_state"] == "COMPLETED" and terminal["exit_code"] == terminal["signal"] == 0, "DIRECT_PROOF")
        parent.hash_string(terminal["submission_sha256"]);parent.hash_string(terminal["terminal_sha256"])
    for counts in (proof["role_counters"],exported["counters"]):
        need(type(counts) is dict and set(counts) == {"read_bytes","write_bytes","creations","operations","scanned_entries","wire_bytes"}, "DIRECT_PROOF")
        for name,value in counts.items():
            tc.uint(value);need(value <= selected.limits[name], "DIRECT_PROOF")
    return selected


def reopen_recovery(plan, proof, local_output, review_output, *, offline=False, test_root=None):
    """One actual independent archive AND complete local mirror reopening.

    New spill metadata is separate from immutable originals. The single owner
    retains its original120s/4GiB/131072-read stops throughout both openers.
    """
    entered, epoch = time.monotonic_ns(),time.time_ns()
    selected = _integrity(proof,allow_test_only=offline)
    need(proof["plan_sha256"] == digest(tc.canonical(plan)) and proof["originals"]==plan["originals"]
         and proof["software_source_sha"]==plan["software"]["source_git_sha"]
         and proof["software_inventory_sha256"]==plan["software"]["inventory_sha256"]
         and proof["recovery_consumer_inventory"]==plan["software"]["consumer_inventory"]
         and proof["recovery_consumer_inventory_sha256"]==plan["software"]["inventory_sha256"],"DIRECT_PROOF")
    selected=_selected_cohort(plan,proof["selection"],offline=offline,test_root=test_root)
    need(proof["workload_verification"]["required_for_B_acceptance"]==plan["original_workload"]["required_for_B_acceptance"],"DIRECT_PROOF")
    need([{key:row[key] for key in ("label","path")} for row in proof["transport"]["complete"]["files"][-2:]]==plan["export_logs"],"DIRECT_COHORT")
    role = Role(selected,entered,plan["window_end_epoch_ns"],review=True)
    prepared=diagnostics.FirstFailureDescriptor();operation="VERIFY_SOFTWARE"
    output, retained = tc.absolute(str(review_output)),tc.absolute(str(local_output))
    try:
        prepared=_source_map(plan,role);operation="INDEPENDENT_REOPEN"
        selected.disjoint_output(output,test_root if offline else None)
        need(not tc.contained(output,retained) and not tc.contained(retained,output), "DIRECT_MIRROR")
        tc.mkdir(output,role.budget)
        artifacts,mirror=retained/"artifacts",retained/"mirror"
        lookup={row["label"]:row for row in proof["transport"]["complete"]["files"]}
        for label in ("selection","export","export_stdout","export_stderr"):
            actual=parent.hash_original(artifacts/(label+".original"),role,65536)
            need((actual["sha256"],actual["bytes"])==(lookup[label]["sha256"],lookup[label]["bytes"]),"DIRECT_PROOF")
        need(parent.read_original(artifacts/"selection.original",role,65536)==tc.canonical(proof["selection"])
             and parent.read_original(artifacts/"export.original",role,65536)==tc.canonical(proof["export"]),"DIRECT_PROOF")
        workload_raw=parent.read_original(artifacts/"workload.original",role,1048576)
        need(workload_raw==tc.canonical(proof["workload_verification"])
             and digest(workload_raw)==lookup["workload"]["sha256"],"DIRECT_PROOF")
        archive = next(row for row in proof["transport"]["complete"]["files"] if row["label"] == "archive")
        actual, opened=parent.open_retained_archive(_opener_view(selected,archive,role.epoch_end),artifacts,role)
        need(opened["summary"] == proof["archive_open"]["summary"] and actual["sha256"] == archive["sha256"], "DIRECT_PROOF")
        roots={name:mirror/"originals"/name for name in selected.roots}
        external={name:mirror/"originals"/name for name in selected.external}
        bindings=[dict(label=label,original_path=str(path),local_path=str(mirror/"originals"/label))
                  for label,path in {**selected.roots,**selected.external}.items()]
        need(proof["mirror"]["bindings"] == bindings and proof["mirror"]["inert_root"] == str(mirror/"inert-metadata"), "DIRECT_MIRROR")
        with os.scandir(mirror/"originals") as entries:
            seen=set()
            for entry in entries:
                role.budget.scan();need(entry.name in roots or entry.name in external,"DIRECT_MIRROR");seen.add(entry.name)
            need(seen == set(roots)|set(external),"DIRECT_MIRROR")
        local=tc.Source(selected,role.budget,roots,external,local=True,
                        inert_root=mirror/"inert-metadata" if selected.inert else None)
        manifest=tc.make_manifest(output,"reopen",local,selected,role.budget,project=True)
        current=tc.Lines(manifest,role.budget,selected.limits["record_bytes"]);before=None
        try:
            before=tc.Lines(artifacts/"before.original",role.budget,selected.limits["record_bytes"])
            while (raw:=before.next()) is not None:
                need(current.next() == tc.canonical(tc.content(tc.parse(raw))),"DIRECT_MIRROR")
            need(current.next() is None,"DIRECT_MIRROR")
        finally: tc.close_owned(role.budget,(current.fd,before.fd if before else None))
        role.check();need(not role.cleanup_uncertain,"DIRECT_PROOF")
        result=dict(version=REOPEN_VERSION,status="COMPLETE",result_sha256=digest(tc.canonical(proof)),
            plan_sha256=proof["plan_sha256"],archive_sha256=archive["sha256"],summary=opened["summary"],
            complete_mirror_rehashed=True,entry_mono_ns=entered,entry_epoch_ns=epoch,
            completed_mono_ns=time.monotonic_ns(),completed_epoch_ns=time.time_ns(),deadline_mono_ns=role.end,
            window_end_epoch_ns=role.epoch_end,read_calls=role.read_calls,counters=dict(role.budget.counts),
            cleanup_uncertain=False,native_or_scientific_acceptance=False)
        _write(output/"DIRECT_REOPEN.record",tc.canonical(result),role.budget)
        need(parent.read_original(output/"DIRECT_REOPEN.record",role,65536)==tc.canonical(result),"DIRECT_PROOF")
        role.check();return result
    except BaseException as error:
        failure=_failure(error,operation,prepared);failure["cleanup_uncertain"]=role.cleanup_uncertain
        try: error.direct_recovery_failure=failure
        except BaseException: pass
        if role.budget.output_path is not None:
            try: _write(output/"DIRECT_REOPEN_INCOMPLETE.record",tc.canonical(failure),role.budget)
            except BaseException: failure["retention_uncertain"]=True
        raise


def validate_recovery_proof(proof, *, review, expected_plan_sha256,
                            expected_software_source_sha, expected_software_inventory_sha256,
                            expected_review_sha256, expected_consumer_inventory_sha256=None,
                            allow_test_only=False):
    _integrity(proof,allow_test_only=allow_test_only)
    need(proof.get("version") == RESULT_VERSION
         and proof.get("status") == "DIRECT_RECOVERY_INTEGRITY_COMPLETE_PENDING_REVIEW"
         and proof.get("scope") == SCOPE and proof.get("plan_sha256") == expected_plan_sha256
         and proof.get("software_source_sha") == expected_software_source_sha
         and proof.get("software_inventory_sha256") == expected_software_inventory_sha256, "DIRECT_PROOF")
    inventory_sha = consumer_digest(proof["recovery_consumer_inventory"])
    need(proof["recovery_consumer_inventory_sha256"] == inventory_sha == expected_software_inventory_sha256)
    need(expected_consumer_inventory_sha256 is None or expected_consumer_inventory_sha256 == inventory_sha)
    need(type(review) is dict and len(tc.canonical(review)) <= 65536
         and digest(tc.canonical(review)) == expected_review_sha256, "DIRECT_REVIEW")
    need(review.get("version") == REVIEW_VERSION and review.get("status") == "PASS"
         and review.get("independent_review") is True
         and review.get("reviewer_role") == "INDEPENDENT_REVIEWER"
         and review.get("actual_reopened") is True
         and review.get("result_sha256") == digest(tc.canonical(proof)), "DIRECT_REVIEW")
    reopened=review["reopen"]
    need(reopened["version"] == REOPEN_VERSION and reopened["status"] == "COMPLETE"
         and reopened["result_sha256"] == review["result_sha256"]
         and reopened["plan_sha256"] == proof["plan_sha256"]
         and reopened["archive_sha256"] == proof["archive_open"]["archive_sha256"]
         and reopened["summary"] == proof["archive_open"]["summary"]
         and reopened["complete_mirror_rehashed"] is True and reopened["cleanup_uncertain"] is False
         and reopened["native_or_scientific_acceptance"] is False
         and reopened["entry_mono_ns"] <= reopened["completed_mono_ns"] < reopened["deadline_mono_ns"]
         and reopened["deadline_mono_ns"]-reopened["entry_mono_ns"] <= 120*10**9
         and reopened["entry_epoch_ns"] <= reopened["completed_epoch_ns"] < reopened["window_end_epoch_ns"]
         and reopened["read_calls"] <= 131072 and reopened["counters"]["read_bytes"] <= 4*2**30,"DIRECT_REVIEW")
    for key in ("plan_sha256","software_source_sha","software_inventory_sha256","recovery_consumer_inventory_sha256"):
        need(review.get(key) == proof[key], "DIRECT_REVIEW")
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("export", "recover"))
    parser.add_argument("--plan",type=Path,required=True);parser.add_argument("--plan-sha256",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--window-end-epoch-ns",type=int,required=True)
    parser.add_argument("--export-end-epoch-ns",type=int)
    parser.add_argument("--remote-output",type=Path)
    parser.add_argument("--export-terminal",type=Path);parser.add_argument("--export-terminal-sha256")
    parser.add_argument("--offline-invented",action="store_true");parser.add_argument("--test-root",type=Path)
    args = parser.parse_args(argv)
    try:
        os.umask(0o077)
        if args.action == "export" and not args.offline_invented:
            from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
            require_goethe_nhr_slurm("stage12_direct_terminal_recovery_export")
        # This is the SAME original900s role origin; it is not preparation time
        # followed by a reset. Carry every bootstrap read into its role owner.
        bootstrap = parent.Control(ENTRY_MONO_NS,args.window_end_epoch_ns,900)
        raw = parent.read_original(args.plan,bootstrap,65536)
        need(digest(raw) == args.plan_sha256)
        plan = tc.parse(raw);need(plan["window_end_epoch_ns"] == args.window_end_epoch_ns)
        if args.action == "export":
            need(args.export_end_epoch_ns is not None)
            result = export_archive(plan,args.output,export_end_epoch_ns=args.export_end_epoch_ns,
                offline=args.offline_invented,test_root=args.test_root,initial_control=bootstrap)
        else:
            outcome_raw = parent.read_original(args.export_terminal,bootstrap,65536)
            need(digest(outcome_raw) == args.export_terminal_sha256)
            result = recover_archive(plan,args.remote_output,args.output,export_terminal=tc.parse(outcome_raw),
                offline=args.offline_invented,test_root=args.test_root,entry=(ENTRY_MONO_NS,ENTRY_EPOCH_NS),initial_control=bootstrap)
        sys.stdout.buffer.write(tc.canonical(dict(status=result["status"],native_or_scientific_acceptance=False)))
        return 0
    except BaseException as error:
        failure = getattr(error,"direct_recovery_failure",None)
        if failure is None: failure = _failure(error,"CLI",diagnostics.FirstFailureDescriptor())
        # The private failure original retains bounded transport diagnostics;
        # the CLI emits only the closed first-failure discriminator.
        public={key:failure[key] for key in ("status","operation","code","first_failure","historical_cause_not_inferred")}
        public["cleanup_uncertain"]=failure.get("cleanup_uncertain",False)
        sys.stderr.buffer.write(tc.canonical(public));return 2


if __name__ == "__main__":
    raise SystemExit(main())

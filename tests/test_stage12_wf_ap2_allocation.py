"""Bounded synthetic bootstrap/binder tests; never live evidence or a job."""

import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "allocation_test", ROOT / "scripts/stage12_wf_ap2_allocation.py"
)
allocation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(allocation)
NOW = "2026-11-08T12:00:00.000000Z"
BEFORE = "2026-11-08T00:00:00.000000Z"
AFTER = "2026-11-09T00:00:00.000000Z"
H = "a" * 64


@pytest.fixture(autouse=True)
def offline_denial(monkeypatch, request):
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport

    def denied(*args, **kwargs):
        raise AssertionError("allocation test attempted prohibited access")

    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, denied)
    monkeypatch.setattr(s12_transport.Secret, "runtime", denied)
    monkeypatch.setattr(s12_transport.Secret, "private_file", denied)
    permitted = {
        "test_supervisor_parent_capture_accounting_and_failed_utility",
        "test_actual_guard_parent_fsync_denies_near_miss",
        "test_installed_extra_metadata_scope_denies_escape_sensitive_and_fd",
        "test_supervisor_keeps_original_epoch_and_rejects_future_or_changed_boot",
    }
    if request.node.name in permitted:
        original_run = subprocess.run

        def bounded_local_test_process(args, **kwargs):
            assert args[:2] == ["bash", "-c"] or args[:3] == [
                sys.executable,
                "-B",
                "-c",
            ]
            assert kwargs.get("timeout", 0) <= 10
            assert len(args[-1]) <= 20000
            # No service/credential environment is inherited by the explicit
            # isolated audit/supervisor test children.
            kwargs["env"] = {
                "PATH": os.defpath,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
            return original_run(args, **kwargs)

        monkeypatch.setattr(subprocess, "run", bounded_local_test_process)
    else:
        for name in ("Popen", "run", "check_output", "check_call", "call"):
            monkeypatch.setattr(subprocess, name, denied)


def private(path):
    path.mkdir(parents=True, mode=0o700)
    path.chmod(0o700)
    return path


def write(path, value, raw=False):
    data = value if raw else allocation.canonical(value)
    path.write_bytes(data)
    path.chmod(0o600)
    return allocation.sha(data)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    project = private(tmp_path / "project")
    parent = private(project / "controlled")
    private(project / "integration_stage12")
    source = private(project / "integration_stage12/source")
    private(source / "scripts")
    write(source / "scripts/marker.py", b"# synthetic source\n", raw=True)
    monkeypatch.setattr(allocation, "PROJECT", project)
    monkeypatch.setattr(allocation, "PARENT", parent)
    paths = {name: str(parent / name) for name in allocation.PATHS}
    paths.update(
        source=str(source),
        input=str(parent / "binding/input.json"),
        evidence=str(parent / "binding/evidence"),
    )
    records = private(Path(paths["records"]))
    limits = {
        "stages": {
            name: dict(zip(("seconds", "bytes", "creations"), cap, strict=True))
            for name, cap in allocation.STAGES.items()
        },
        "rss_bytes": 768 * 2**20,
        "native_threads": 256,
        "whole_seconds": 8160,
        "whole_creations": 130000,
        "whole_bytes": 77561069568,
        "max_enforcement_checks": 4096,
        "max_runtime_inventory_checks": 8,
    }
    selection = dict(
        version=allocation.VERSION,
        scope=allocation.SCOPE,
        status="ISSUED",
        source_sha="b" * 40,
        source_files=[
            {
                "path": "scripts/marker.py",
                "sha256": allocation.sha(b"# synthetic source\n"),
            }
        ],
        paths=paths,
        anchors={key: None for key in allocation.ANCHORS},
        valid_from=BEFORE,
        valid_until=AFTER,
        replay_sha256=allocation.sha((ROOT / allocation.REPLAY).read_bytes()),
        limits=limits,
    )

    source_rows = []
    for name in sorted(allocation.REQUIRED_SOURCE_FILES):
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = (ROOT / name).read_bytes()
        write(destination, raw, raw=True)
        source_rows.append({"path": name, "sha256": allocation.sha(raw)})
    source_rows.append(selection["source_files"][0])
    selection["source_files"] = sorted(source_rows, key=lambda row: row["path"])

    def put(value, raw=False):
        data = value if raw else allocation.canonical(value)
        token = allocation.sha(data)
        write(records / (token + (".evidence" if raw else ".json")), data, raw=True)
        return token

    proof = put(
        b"SYNTHETIC TEST ONLY. No competent authority or capacity attested.\n", raw=True
    )
    for stage, key in (("A", "a_capacity"), ("B", "b_capacity")):
        selection["anchors"][key] = put(
            dict(
                version="stage12_wf_ap2_capacity_fact_v1",
                scope=allocation.SCOPE,
                record_origin="COMPETENT_AUTHORITY_ORIGINAL",
                authority_role="STORAGE_CAPACITY_AUTHORITY",
                proof_document_sha256=proof,
                controlled_parent=str(parent),
                work_stage=stage,
                file_data_bytes=limits["whole_bytes"],
                creation_attempts=130000,
                physical_capacity_bytes=limits["whole_bytes"],
                inode_capacity=130000,
                physical_and_transient_coverage_verified=True,
                capacity_entitlement_verified=True,
                valid_from=BEFORE,
                valid_until=AFTER,
            )
        )
    selection["anchors"]["coverage"] = put(
        dict(
            version="stage12_wf_ap2_domain_coverage_v1",
            scope=allocation.SCOPE,
            record_origin="COMPETENT_AUTHORITY_ORIGINAL",
            authority_role="RUNTIME_ENFORCEMENT_AUTHORITY",
            proof_document_sha256=proof,
            domain_prefix="/sys/fs/cgroup/test",
            complete_job_descendants=True,
            host_namespace_scope_verified=True,
            nondelegated_no_escape=True,
            maximum_memory_bytes=6 * 2**30,
            swap_max_bytes=0,
            finite_pids_required=True,
            valid_from=BEFORE,
            valid_until=AFTER,
        )
    )
    selection["anchors"]["method"] = put(
        dict(
            version="stage12_wf_ap2_method_evidence_v1",
            scope=allocation.SCOPE,
            method=m.METHOD,
            source_sha=selection["source_sha"],
            proof_document_sha256=proof,
        )
    )
    selection["anchors"]["logical"] = put(
        dict(
            version="stage12_wf_ap2_logical_evidence_v1",
            scope=allocation.SCOPE,
            source_sha=selection["source_sha"],
            proof_document_sha256=proof,
            allocations=[
                dict(name=name, bytes=size)
                for name, size in zip(
                    m.ARENAS,
                    [65536, 8 * 2**20, 4096 * 512, 65536, 32768, 16384, 0],
                    strict=True,
                )
            ],
        )
    )
    selection["anchors"]["reviewer_role"] = put(
        dict(
            version="stage12_wf_ap2_reviewer_role_v1",
            scope=allocation.SCOPE,
            purpose="INDEPENDENT_ALLOCATION_FACT_REVIEW",
            approval_source_sha256=proof,
            reviewer="SYNTHETIC_TEST_REVIEWER",
        )
    )

    def issue_owner():
        selection["anchors"]["owner"] = put(
            dict(
                version="stage12_wf_ap2_allocation_owner_v1",
                scope=allocation.SCOPE,
                source_sha=selection["source_sha"],
                selection_scope_sha256=allocation.selection_scope(selection),
                approval_source_sha256=proof,
                maximum_allocations=1,
                collect_A=True,
                conditional_B=True,
                valid_from=BEFORE,
                valid_until=AFTER,
            )
        )

    issue_owner()
    return selection, allocation.Records(records), put, issue_owner


def kernel():
    return dict(
        version="stage12_wf_ap2_kernel_observation_v1",
        origin="ACTUAL_READ_ONLY_KERNEL_OBSERVATION",
        pid=123,
        boot_id="11111111-1111-1111-1111-111111111111",
        namespaces={"cgroup": 51, "mnt": 52},
        membership="0::/test/job",
        status="CapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapInh:\t0000000000000000\nCapAmb:\t0000000000000000\nNoNewPrivs:\t1",
        mountinfo="1 0 0:1 / /sys/fs/cgroup ro - cgroup2 cgroup rw",
        leaf_identity=dict(device=31, inode=32, mode=0o755, uid=0, gid=0),
        leaf="/sys/fs/cgroup/test/job",
        leaf_procs="123",
        ancestors=[
            dict(
                path="/sys/fs/cgroup/test/job",
                identity=dict(device=31, inode=32, mode=0o755, uid=0, gid=0),
                **{
                    "memory.max": str(6 * 2**30),
                    "memory.high": "max",
                    "memory.swap.max": "0",
                    "pids.max": "64",
                    "pids.current": "3",
                    "writable_control": False,
                },
            )
        ],
        errors=[],
        reads=[],
        read_bytes=0,
    )


def bootstrap_and_review(selection, records, monkeypatch):
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_JOB_NOT_EXECUTED")
    b = allocation.Budget(
        selection["paths"]["bootstrap"],
        max_bytes=2**20,
        max_creations=32,
        deadline=10**30,
    )
    b.write("kernel_after.json", kernel())
    b.write("runtime.json", {"scope": "SYNTHETIC_TEST_ONLY"})
    facts = dict(
        version="stage12_wf_ap2_bootstrap_facts_v1",
        source_sha=selection["source_sha"],
        selection_scope_sha256=allocation.selection_scope(selection),
        job_id=os.environ["SLURM_JOB_ID"],
        created_utc=NOW,
        runtime_inventory_sha256=allocation.digest({"scope": "SYNTHETIC_TEST_ONLY"}),
        kernel_after_sha256=allocation.digest(kernel()),
    )
    b.write("facts.json", facts)
    token = b.close("BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED")
    review = dict(
        version="stage12_wf_ap2_independent_fact_review_v1",
        scope=allocation.SCOPE,
        decision="RELEASE_B",
        reviewer="SYNTHETIC_TEST_REVIEWER",
        reviewer_role_sha256=selection["anchors"]["reviewer_role"],
        source_sha=selection["source_sha"],
        selection_scope_sha256=allocation.selection_scope(selection),
        bootstrap_manifest_sha256=token,
        coverage_sha256=selection["anchors"]["coverage"],
        capacity_sha256=selection["anchors"]["b_capacity"],
        method_sha256=selection["anchors"]["method"],
        logical_sha256=selection["anchors"]["logical"],
        configuration_sha256=H,
        runtime_bound_scope_sha256=H,
        verified_utc=NOW,
        valid_until=AFTER,
    )
    return facts, review


def test_ready_requires_real_separately_bound_capacity(setup):
    selection, records, _, issue = setup
    assert allocation.ready(selection, records, NOW)["A_ready"]
    selection["anchors"]["a_capacity"] = None
    issue()
    with pytest.raises(allocation.AllocationError, match="MISSING_EVIDENCE"):
        allocation.ready(selection, records, NOW)


def test_owner_offline_authority_does_not_replace_capacity(setup):
    selection, records, put, issue = setup
    row = records.get(selection["anchors"]["a_capacity"])
    row["capacity_entitlement_verified"] = False
    selection["anchors"]["a_capacity"] = put(row)
    issue()
    with pytest.raises(allocation.AllocationError):
        allocation.ready(selection, records, NOW)


def test_A_capacity_covers_review_binding_final_and_logs(setup):
    selection, records, put, issue = setup
    row = records.get(selection["anchors"]["a_capacity"])
    row.update(
        file_data_bytes=32 * 2**20,
        physical_capacity_bytes=32 * 2**20,
        creation_attempts=256,
        inode_capacity=256,
    )
    selection["anchors"]["a_capacity"] = put(row)
    issue()
    with pytest.raises(allocation.AllocationError, match="CAPACITY"):
        allocation.ready(selection, records, NOW)


def test_source_and_owner_scope_changes_rejected(setup):
    selection, records, _, _ = setup
    selection["limits"]["native_threads"] -= 1
    with pytest.raises(allocation.AllocationError):
        allocation.ready(selection, records, NOW)


def test_expiry_and_underbudgeted_whole_graph_rejected(setup):
    selection, records, _, _ = setup
    with pytest.raises(allocation.AllocationError, match="EXPIRED"):
        allocation.ready(selection, records, AFTER)
    selection["limits"]["whole_bytes"] -= 1
    with pytest.raises(allocation.AllocationError):
        allocation.validate_selection(selection)


@pytest.mark.parametrize(
    "field", ["whole_seconds", "review_seconds", "native_threads", "whole_creations"]
)
def test_lower_unhonored_selection_is_rejected(setup, field):
    selection, _, _, _ = setup
    if field == "review_seconds":
        selection["limits"]["stages"]["review"]["seconds"] -= 1
    else:
        selection["limits"][field] = 1
    with pytest.raises(allocation.AllocationError):
        allocation.validate_selection(selection)


@pytest.mark.parametrize(
    "mutation", ["unknown", "swap", "delegated", "membership", "capabilities"]
)
def test_kernel_unknowns_and_escape_conditions_fail_closed(mutation):
    value = kernel()
    if mutation == "unknown":
        value["ancestors"][0]["memory.max"] = None
    if mutation == "swap":
        value["ancestors"][0]["memory.swap.max"] = "1"
    if mutation == "delegated":
        value["ancestors"][0]["writable_control"] = True
    if mutation == "membership":
        value["leaf_procs"] = "other"
    if mutation == "capabilities":
        value["status"] = value["status"].replace(
            "CapEff:\t0000000000000000", "CapEff:\t0000000000000001"
        )
    with pytest.raises(allocation.AllocationError):
        allocation.domain_from_kernel(value)


def test_exact_stage_reopening_and_aggregate_nested_budget(tmp_path):
    root = private(tmp_path / "private")
    budget = allocation.Budget(
        root / "stage", max_bytes=4096, max_creations=8, deadline=10**30
    )
    budget.mkdir("evidence")
    budget.mkdir("evidence/sampling_evidence")
    budget.write("evidence/sampling_evidence/a.record", {"test": True})
    budget.write("input.json", {"test": True})
    budget.close("TEST_ONLY")
    assert budget.creations == 6
    assert allocation.verify_stage(budget.root)["status"] == "TEST_ONLY"
    write(budget.root / "evidence/extra.record", {})
    with pytest.raises(allocation.AllocationError, match="INVENTORY_CHANGED"):
        allocation.verify_stage(budget.root)


def test_no_budget_refund_and_no_commit_after_partial_write(tmp_path, monkeypatch):
    root = private(tmp_path / "private")
    budget = allocation.Budget(
        root / "stage", max_bytes=128, max_creations=8, deadline=10**30
    )
    monkeypatch.setattr(
        allocation.os,
        "write",
        lambda *args: (_ for _ in ()).throw(OSError(28, "unsafe text never retained")),
    )
    with pytest.raises(OSError):
        budget.write("partial.json", {"test": True})
    assert budget.poisoned and budget.bytes > 0 and budget.creations == 2
    with pytest.raises(allocation.AllocationError, match="UNCERTAIN_IO"):
        budget.close("FALSE_SUCCESS")


def test_budget_boundary_and_deadline_prevent_late_write(tmp_path):
    root = private(tmp_path / "private")
    budget = allocation.Budget(
        root / "stage", max_bytes=3, max_creations=8, deadline=5, clock=lambda: 1
    )
    budget.write("a", {})
    with pytest.raises(allocation.AllocationError, match="BUDGET"):
        budget.write("b", {})
    budget.clock = lambda: 5
    with pytest.raises(allocation.AllocationError, match="DEADLINE"):
        budget.close("LATE")


@pytest.mark.parametrize(
    "mutation", ["stale", "source", "reviewer", "bootstrap", "domain"]
)
def test_release_rejects_stale_or_changed_bindings(setup, monkeypatch, mutation):
    selection, records, _, _ = setup
    _, review = bootstrap_and_review(selection, records, monkeypatch)
    current = kernel()
    if mutation == "stale":
        review["valid_until"] = NOW
    if mutation == "source":
        review["source_sha"] = "f" * 40
    if mutation == "reviewer":
        review["reviewer"] = "OTHER"
    if mutation == "bootstrap":
        review["bootstrap_manifest_sha256"] = H
    if mutation == "domain":
        current["leaf_identity"]["inode"] += 1
    with pytest.raises(allocation.AllocationError):
        allocation.verify_release(
            selection,
            records,
            selection["paths"]["bootstrap"],
            review,
            now=NOW,
            kernel_reader=lambda: current,
        )


def test_fresh_review_cannot_promote_incomplete_bootstrap(setup, monkeypatch):
    selection, records, _, _ = setup
    _, review = bootstrap_and_review(selection, records, monkeypatch)
    path = Path(selection["paths"]["bootstrap"], "manifest.json")
    manifest = allocation.parse(path.read_bytes())
    manifest["status"] = "INCOMPLETE"
    # Recompute the otherwise-consistent reviewed hash. Stage grammar itself
    # must reject this; a trusted review cannot manufacture completion.
    review["bootstrap_manifest_sha256"] = write(path, manifest)
    with pytest.raises(allocation.AllocationError, match="STAGE_INCOMPLETE"):
        allocation.verify_release(
            selection,
            records,
            selection["paths"]["bootstrap"],
            review,
            now=NOW,
            kernel_reader=kernel,
        )


def test_all_release_conditions_then_actual_materializer_parsers(setup, monkeypatch):
    selection, records, _, _ = setup
    facts, review = bootstrap_and_review(selection, records, monkeypatch)
    facts, domain, _, logical = allocation.verify_release(
        selection,
        records,
        selection["paths"]["bootstrap"],
        review,
        now=NOW,
        kernel_reader=kernel,
    )
    # Materialization uses actual production contracts with explicit synthetic
    # records. It never invokes execution or claims a real capacity authority.
    selection["paths"]["source"] = str(ROOT)
    budget = allocation.Budget(
        selection["paths"]["binding"],
        max_bytes=64 * 2**20,
        max_creations=512,
        deadline=10**30,
    )
    subjects = allocation.materialize(
        selection,
        facts,
        domain,
        logical,
        {"scope": "SYNTHETIC_TEST_ONLY"},
        review,
        records,
        None,
        for_review=True,
    )
    assert subjects["status"] == "UNISSUED_REVIEW_SUBJECTS"
    review.update(
        configuration_sha256=allocation.digest(subjects["configuration"]),
        runtime_bound_scope_sha256=allocation.digest(subjects["runtime_bound_scope"]),
    )
    result = allocation.materialize(
        selection,
        facts,
        domain,
        logical,
        {"scope": "SYNTHETIC_TEST_ONLY"},
        review,
        records,
        budget,
    )
    (
        data,
        roles,
        resource_record,
        selected_record,
        binding_review,
        review_text,
        proofs,
    ) = result
    assert sum(len(x["work"]) for x in data["configuration"]["campaigns"]) == 107
    assert (
        sum(
            x["plan"]["budgets"]["data_attempts"]
            + x["plan"]["budgets"]["control_http_attempts"]
            for x in data["configuration"]["campaigns"]
        )
        == 535
    )
    budget.mkdir("evidence")
    budget.mkdir("evidence/sampling_evidence")
    for role, value in roles.items():
        budget.write("evidence/" + role + ".record", value)
    for name, value in [
        ("diagnostic_resources.record", resource_record),
        ("diagnostic_selection.record", selected_record),
        ("integration_review.binding.json", binding_review),
        ("integration_review.md", review_text),
    ]:
        budget.write("evidence/" + name, value)
    for token, value in proofs.items():
        budget.write("evidence/sampling_evidence/" + token + ".record", value)
    budget.write("input.json", data)
    budget.close("TEST_ONLY_NEVER_EXECUTABLE")
    allocation.verify_stage(budget.root)
    diagnostic = allocation._module(
        ROOT, "stage12_wf_ap2_diagnostic.py", "materializer_actual_parser"
    )
    diagnostic.validate_grants(data, budget.root / "evidence")
    assert all(row["authority"] == "TEST_ONLY_NO_SERVICE" for row in roles.values())


def prepare_complete_binding(setup, monkeypatch):
    """Actual collector/binder with explicitly fake observations and guards.

    This is process-local orchestration coverage, not authority issuance or a
    Goethe allocation. The separate child test exercises the real audit hook.
    """
    import safe_geocoding_pipeline.execution_policy as policy

    selection, records, _, _ = setup
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_JOB_NOT_EXECUTED")
    monkeypatch.setattr(policy, "require_goethe_nhr_slurm", lambda *args: None)
    monkeypatch.setattr(allocation, "collection_guard", lambda *args, **kwargs: None)
    monkeypatch.setattr(allocation, "now_utc", lambda: NOW)
    original_module = allocation._module
    monkeypatch.setattr(
        allocation,
        "_module",
        lambda source, filename, name: original_module(ROOT, filename, name),
    )
    source = Path(selection["paths"]["source"])
    private(source / "docs/scientific_assets")
    write(source / allocation.REPLAY, (ROOT / allocation.REPLAY).read_bytes(), raw=True)
    selected_path = Path(selection["paths"]["records"]).parent / "selection.json"
    selected_hash = write(selected_path, selection)
    result = allocation.collect(
        selection,
        selected_path,
        selected_hash,
        kernel_reader=lambda **kwargs: kernel(),
        inventory_reader=lambda *args, **kwargs: {"scope": "SYNTHETIC_TEST_ONLY"},
        thread_reader=lambda: 1,
    )
    assert result["B_released"] is False
    assert (
        allocation.verify_stage(selection["paths"]["bootstrap"])["status"]
        == "BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED"
    )
    review = dict(
        version="stage12_wf_ap2_independent_fact_review_v1",
        scope=allocation.SCOPE,
        decision="RELEASE_B",
        reviewer="SYNTHETIC_TEST_REVIEWER",
        reviewer_role_sha256=selection["anchors"]["reviewer_role"],
        source_sha=selection["source_sha"],
        selection_scope_sha256=allocation.selection_scope(selection),
        bootstrap_manifest_sha256=result["manifest_sha256"],
        coverage_sha256=selection["anchors"]["coverage"],
        capacity_sha256=selection["anchors"]["b_capacity"],
        method_sha256=selection["anchors"]["method"],
        logical_sha256=selection["anchors"]["logical"],
        configuration_sha256=H,
        runtime_bound_scope_sha256=H,
        verified_utc=NOW,
        valid_until=AFTER,
    )
    facts = allocation.parse(
        Path(selection["paths"]["bootstrap"], "facts.json").read_bytes()
    )
    subjects = allocation.materialize(
        selection,
        facts,
        allocation.domain_from_kernel(kernel()),
        records.get(selection["anchors"]["logical"]),
        {"scope": "SYNTHETIC_TEST_ONLY"},
        review,
        records,
        None,
        for_review=True,
    )
    review.update(
        configuration_sha256=allocation.digest(subjects["configuration"]),
        runtime_bound_scope_sha256=allocation.digest(subjects["runtime_bound_scope"]),
    )
    write(Path(selection["paths"]["review"]), review)
    return selection, selected_hash


def test_actual_collector_and_binder_complete_exclusive_publications(
    setup, monkeypatch
):
    selection, selected_hash = prepare_complete_binding(setup, monkeypatch)
    result = allocation.bind(selection, selected_hash, kernel_reader=kernel)
    final = allocation.verify_stage(selection["paths"]["binding"])
    assert final["status"] == "BOUND_AFTER_INDEPENDENT_VERIFICATION"
    assert result["input_sha256"] == allocation.sha(
        Path(selection["paths"]["input"]).read_bytes()
    )
    assert final["charged_creations_before_manifest"] + 1 <= 512
    assert final["charged_bytes_before_manifest"] < 64 * 2**20
    facts = allocation.parse(
        Path(selection["paths"]["bootstrap"], "facts.json").read_bytes()
    )
    assert facts["resource_watermarks"]["maximum_observed_native_threads"] == 1
    assert facts["resource_watermarks"]["maximum_observed_rss_bytes"] > 0


def test_failure_between_binding_steps_never_publishes_input(setup, monkeypatch):
    selection, selected_hash = prepare_complete_binding(setup, monkeypatch)
    original_write = allocation.Budget.write

    def failed_write(self, name, value):
        if name == "evidence/diagnostic_resources.record":
            self.poisoned = True
            raise OSError(28, "synthetic failure not retained")
        return original_write(self, name, value)

    monkeypatch.setattr(allocation.Budget, "write", failed_write)
    with pytest.raises(OSError):
        allocation.bind(selection, selected_hash, kernel_reader=kernel)
    assert not Path(selection["paths"]["input"]).exists()
    assert not Path(selection["paths"]["binding"], "manifest.json").exists()
    assert Path(selection["paths"]["evidence"], "owner.record").exists()


def test_derived_configuration_must_match_independently_reviewed_bytes(
    setup, monkeypatch
):
    selection, selected_hash = prepare_complete_binding(setup, monkeypatch)
    path = Path(selection["paths"]["review"])
    review = allocation.parse(path.read_bytes())
    review["configuration_sha256"] = H
    write(path, review)
    with pytest.raises(allocation.AllocationError, match="DERIVED_REVIEW_MISMATCH"):
        allocation.bind(selection, selected_hash, kernel_reader=kernel)
    assert not Path(selection["paths"]["input"]).exists()
    assert not Path(selection["paths"]["evidence"]).exists()


def test_supervisor_parent_capture_accounting_and_failed_utility():
    script = ROOT / "cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch"
    command = f'''source "{script}"
stage12_check() {{ :; }}
STAGE12_UTILITIES=0
stage12_capture actual printf hello
[[ "$actual" == hello && "$STAGE12_UTILITIES" == 1 ]]
if stage12_capture failed bash -c 'exit 7'; then exit 99; else [[ $? == 7 ]]; fi
[[ "$STAGE12_UTILITIES" == 2 ]]
'''
    result = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr


def test_supervisor_keeps_original_epoch_and_rejects_future_or_changed_boot():
    script = ROOT / "cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch"
    command = f'''source "{script}"
STAGE12_NOW=200
STAGE12_EPOCH_START=100
STAGE12_BOOT=synthetic_boot
STAGE12_EPOCH_BOOT=synthetic_boot
stage12_apply_epoch
[[ "$STAGE12_START" == 100 && "$STAGE12_END" == 816100 ]]
STAGE12_EPOCH_START=201
if (stage12_apply_epoch); then exit 90; fi
STAGE12_EPOCH_START=100
STAGE12_EPOCH_BOOT=changed_boot
if (stage12_apply_epoch); then exit 91; fi
'''
    result = subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr


def test_source_git_checks_cannot_refresh_index_or_run_fsmonitor():
    script = (ROOT / "cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch").read_text()
    assert "export GIT_OPTIONAL_LOCKS=0" in script
    assert (
        script.count(
            "git --no-optional-locks -c core.fsmonitor=false -c core.untrackedCache=false -C"
        )
        == 3
    )
    assert (
        "unset GIT_DIR GIT_WORK_TREE GIT_CONFIG_COUNT GIT_CONFIG_PARAMETERS" in script
    )


def test_actual_guard_parent_fsync_denies_near_miss(tmp_path):
    # Child process contains the irreversible real audit hook. Local simulated
    # Linux process identity is NOT actual Goethe/Linux execution evidence.
    root = private(tmp_path / "private")
    output = root / "bootstrap"
    records = private(root / "records")
    config = root / "selection.json"
    write(config, {})
    command = f"""
import importlib.util, pathlib, sys
sys.path.insert(0, {str(ROOT / "src")!r})
spec=importlib.util.spec_from_file_location('collector', {str(ROOT / "scripts/stage12_wf_ap2_allocation.py")!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.collection_guard(pathlib.Path({str(ROOT)!r}), pathlib.Path({str(output)!r}), pathlib.Path({str(records)!r}), pathlib.Path({str(config)!r}))
b=m.Budget(pathlib.Path({str(output)!r}),max_bytes=4096,max_creations=8,deadline=10**30)
b.write('original.json',{{'synthetic':True}});b.close('TEST_ONLY');m.verify_stage(b.root)
for action in (lambda: pathlib.Path({str(root / "near-miss")!r}).read_bytes(),lambda: list(pathlib.Path({str(root)!r}).iterdir())):
    try: action()
    except (m.AllocationError, FileNotFoundError): pass
    else: raise AssertionError('near-miss admitted')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", command],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_installed_extra_metadata_scope_denies_escape_sensitive_and_fd(tmp_path):
    root = private(tmp_path / "private")
    output = root / "binding"
    records = private(root / "records")
    bootstrap = private(root / "bootstrap")
    sensitive = private(bootstrap / "credentials")
    outside = root / "outside"
    write(outside, {"synthetic": True})
    write(bootstrap / "metadata.json", {"synthetic": True})
    write(sensitive / "original", {"synthetic": True})
    (bootstrap / "link").symlink_to(outside)
    config = root / "selection.json"
    write(config, {})
    command = f"""
import importlib.util, os, pathlib, sys
sys.path.insert(0, {str(ROOT / "src")!r})
spec=importlib.util.spec_from_file_location('collector', {str(ROOT / "scripts/stage12_wf_ap2_allocation.py")!r})
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fd=os.open({str(outside)!r},os.O_RDONLY)
m.collection_guard(pathlib.Path({str(ROOT)!r}), pathlib.Path({str(output)!r}), pathlib.Path({str(records)!r}), pathlib.Path({str(config)!r}), extra_reads=(pathlib.Path({str(bootstrap)!r}),))
assert pathlib.Path({str(bootstrap / "metadata.json")!r}).read_bytes()
for action in (lambda: pathlib.Path({str(bootstrap) + "/../outside"!r}).read_bytes(),lambda: pathlib.Path({str(bootstrap / "link")!r}).read_bytes(),lambda: pathlib.Path({str(sensitive / "original")!r}).read_bytes(),lambda: os.fdopen(fd,'rb',closefd=False)):
    try: action()
    except m.AllocationError: pass
    else: raise AssertionError('escape admitted')
os.close(fd)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", command],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr

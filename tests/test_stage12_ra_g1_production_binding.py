"""Real production-shape binding I/O; all facts/approvals are synthetic, unissued.

The scoped hook forwards the unchanged production audit callback for real file
operations. Native seccomp and the cgroup membership original are explicitly
simulated. This test never earns Goethe, kernel, execution or service authority.
"""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_s12_ra_g1_core import G, H, capacity, facts, selection
from test_stage12_ra_g1_allocation import synthetic_accounting
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_storage
from safe_geocoding_pipeline.preprocessing.stages import s12_transport

ROOT = Path(__file__).resolve().parents[1]
NATIVE_LABEL = "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT"


def source_inventory():
    """Pin actual code/assets needed by the builder; no protected data discovery."""
    paths = {ROOT / "pyproject.toml"}
    for directory in ("src", "scripts", "tests"):
        paths.update((ROOT / directory).rglob("*.py"))
    paths.update((ROOT / "docs/scientific_assets").glob("*.json"))
    return [
        dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size,
             sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(paths)
    ]


@pytest.fixture(scope="module")
def private_source(tmp_path_factory):
    source = tmp_path_factory.mktemp("binding_source").resolve()
    source.chmod(0o700)
    rows = source_inventory()
    for row in rows:
        path = source / row["path"]
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        raw = (ROOT / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
        path.write_bytes(raw)
        path.chmod(0o600)
    for directory in source.rglob("*"):
        if directory.is_dir():
            directory.chmod(0o700)
    return source, rows


@pytest.fixture
def production(tmp_path, monkeypatch, private_source):
    source, sources = private_source

    def actual_script(name):
        spec = importlib.util.spec_from_file_location(name, source / "scripts" / (name + ".py"))
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded

    controller = actual_script("stage12_ra_g1_allocation")
    preparer = actual_script("stage12_prepare_ra_g1")
    diagnostic = actual_script("stage12_ra_g1_diagnostic")
    monkeypatch.setattr(controller, "now", lambda: "2026-01-01T00:00:00.000000Z")
    private = tmp_path.resolve()
    private.chmod(0o700)
    root, records = private / "ra_g1_binding_synthetic", private / "records"
    records.mkdir(mode=0o700)
    report = b"SYNTHETIC_ONLY, UNISSUED, NOT A LIVE INDEPENDENT RELEASE\n"
    report_hash = hashlib.sha256(report).hexdigest()
    report_path = records / (report_hash + ".md")
    report_path.write_bytes(report)
    report_path.chmod(0o600)
    originals = {
        "adoption": dict(origin="SYNTHETIC_ONLY_NOT_AUTHORITY"),
        "project_approval": dict(origin="SYNTHETIC_ONLY_NOT_APPROVAL"),
        "software_review": dict(origin="SYNTHETIC_ONLY", source_sha=G,
                                disposition="PASS", report_sha256=report_hash),
        "resource_review": dict(origin="SYNTHETIC_ONLY", source_sha=G,
                                disposition="PASS"),
    }
    for value in originals.values():
        path = records / (controller.digest(value) + ".record")
        path.write_bytes(controller.canonical(value))
        path.chmod(0o600)
    paths = dict(source=str(source), records=str(records), allocation_root=str(root))
    paths.update({key: str(root / name) for key, name in (
        ("bootstrap", "bootstrap"), ("binding", "binding"), ("input", "input.json"),
        ("output", "diagnostic"), ("review", "bootstrap_review.record"),
        ("release", "exact_release.record"), ("outcome", "outcome.record"),
        ("context", "context.record"), ("worker_return", "worker_return.record"),
        ("supervisor_state", "supervisor_state.record"), ("tail", "tail.record"),
    )})
    paths["log"] = str(records / "slurm.log")
    inventory, _ = synthetic_accounting(sources)
    _, adoption, _ = bootstrap_inputs()
    inventory, totals = ac.compile_inventory(
        sources, inventory["backends"], controller.SCOPE,
        bootstrap_successor=True, shared_lease_successor=True,
    )
    replay = ROOT / "docs/scientific_assets/stage12_wf_ap2_representative_replay_v1.json"
    allocation = dict(
        version=controller.SHARED_LEASE_VERSION, scope=controller.SCOPE, source_sha=G,
        valid_from="2026-01-01T00:00:00.000000Z",
        valid_until="2026-01-02T00:00:00.000000Z", paths=paths, source_files=sources,
        accounting_inventory=inventory, accounting=totals, limits=deepcopy(controller.LIMITS),
        replay_sha256=controller.digest(controller.parse(replay.read_bytes())),
        resource_selection_sha256=H, intent_id=H,
        records={name: controller.digest(value) for name, value in originals.items()},
        bootstrap_prefix_adoption=adoption,
        bootstrap_prefix_adoption_sha256=controller.digest(adoption),
    )
    env, kernel = facts(), {"SYNTHETIC_ONLY_NOT_KERNEL_ORIGINALS": True}
    env["observation_inventory_sha256"] = controller.digest(kernel)
    bootstrap = dict(
        source_sha=G, scope=controller.SCOPE, facts=env, manifest_sha256=H,
        job_id="SYNTHETIC_ONLY_NOT_A_JOB", created_utc=allocation["valid_from"],
        runtime_inventory={"SYNTHETIC_ONLY_NOT_RUNTIME_PROOF": True},
        capacity=capacity(selection(controller.SCOPE)), kernel_originals=kernel,
        capacity_originals={"root": [["SYNTHETIC_ONLY"]], "statvfs": {"SYNTHETIC": True}},
        capacity_method={"SYNTHETIC": True}, capacity_restrictions={"SYNTHETIC": True},
        resource_execution=dict(
            schema_version="stage12_resource_execution_request_ra_g1_v1",
            supervisor_context_path=paths["context"], supervisor_context_sha256=H,
        ),
    )
    kwargs = dict(
        implementation_report=report, source_files=sources, adoption=originals["adoption"],
        project_approval=originals["project_approval"], resource_review=originals["resource_review"],
        independent_bootstrap_review=dict(origin="SYNTHETIC_ONLY", disposition="PASS",
                                         source_sha=G, bootstrap_manifest_sha256=H),
        issued=False,
    )
    # Resolve the actual pure builder's acyclic selected pointer; no duplicate compiler.
    _, objects = preparer.build(allocation, bootstrap, **kwargs)
    allocation["resource_selection_sha256"] = controller.digest(objects["resource_selection"])
    assert controller.validate_selection(allocation) == allocation
    assert "evidence" not in allocation["paths"]
    return SimpleNamespace(controller=controller, preparer=preparer, diagnostic=diagnostic,
                           allocation=allocation, bootstrap=bootstrap, kwargs=kwargs,
                           root=root, records=records, private=private, source=source)


@contextmanager
def installed_production_audit(case, run, monkeypatch):
    """Real registered Python audit, reversible scope; native/cgroup simulation only."""
    controller = case.controller
    state = dict(armed=False, events=0, native_simulation_calls=0)
    real_add_hook, real_spec = sys.addaudithook, importlib.util.spec_from_file_location
    real_module, real_open = controller.module, os.open
    membership = case.records / "synthetic_cgroup_original.record"
    membership.write_bytes(b"0::/SYNTHETIC_ONLY_NOT_ACTUAL_CGROUP\n")
    membership.chmod(0o600)

    def register(callback):
        def scoped(event, args):
            if state["armed"]:
                state["events"] += 1
                callback(event, args)
        real_add_hook(scoped)

    def spec(name, location, *args, **kwargs):
        result = real_spec(name, location, *args, **kwargs)
        if name == "ap2_existing_guard":
            original_loader = result.loader

            class NativeSimulationLoader:
                def create_module(self, selected_spec):
                    return original_loader.create_module(selected_spec)

                def exec_module(self, loaded):
                    original_loader.exec_module(loaded)
                    assert Path(loaded.__file__).resolve() == case.source / "scripts/stage12_scale120_diagnostic.py"

                    def simulated_native_only():
                        state["native_simulation_calls"] += 1
                        return NATIVE_LABEL

                    loaded.deny_linux_network = simulated_native_only

            result.loader = NativeSimulationLoader()
        return result

    def open_original(path, flags, *args, **kwargs):
        if str(path) == f"/proc/{os.getpid()}/cgroup":
            path = membership
        return real_open(path, flags, *args, **kwargs)

    def actual_module(source, name):
        loaded = real_module(source, name)
        assert Path(loaded.__file__).resolve() == case.source / "scripts" / (name + ".py")
        return loaded

    # Record original values so the actual installer's process-wide assignments restore.
    for target, names in (
        (socket, ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr")),
        (socket.socket, ("connect", "connect_ex", "bind", "listen", "sendto")),
        (subprocess, ("Popen", "run", "call", "check_output", "check_call")),
        (s12_transport.Secret, ("runtime", "private_file")),
    ):
        for name in names:
            value = target.__dict__[name] if target is s12_transport.Secret else getattr(target, name)
            monkeypatch.setattr(target, name, value)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setattr(sys, "addaudithook", register)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", spec)
    monkeypatch.setattr(controller, "module", actual_module)
    monkeypatch.setattr(os, "open", open_original)
    result = controller.install_denials(case.allocation, check=run.check, read_charge=run.read_charge)
    assert state["native_simulation_calls"] == 1
    assert result["native_filesystem_isolation"] == "NOT_CLAIMED"
    state["armed"] = True
    try:
        yield state
    finally:
        state["armed"] = False


def materialize(run, case, data, objects):
    """Use the production controller's charged exclusive writer and fresh reader."""
    bundle = Path(case.allocation["paths"]["binding"])
    run.mkdir(case.root)
    run.mkdir(bundle)
    run.mkdir(bundle / "resource_evidence")
    for values in objects["resource_evidence"].values():
        for identity, value in values.items():
            path = bundle / "resource_evidence" / (identity + ".record")
            if path.exists():
                assert run.original(path) == case.controller.canonical(value)
            else:
                run.write(path, value)
    for role, value in objects["role_records"].items():
        run.write(bundle / (role + ".record"), value)
    for name, value in (
        ("diagnostic_selection.record", objects["diagnostic_selection"]),
        ("diagnostic_resources.record", objects["diagnostic_resources"]),
        ("integration_review.binding.json", objects["integration_review"]),
    ):
        run.write(bundle / name, value)
    run.write_raw(bundle / "integration_review.md", case.kwargs["implementation_report"])
    run.write(case.allocation["paths"]["input"], data)
    return bundle


def test_production_selection_real_builder_materializes_and_reopens_under_actual_audit(
    production, monkeypatch
):
    case = production
    assert Path(case.preparer.__file__).resolve() == case.source / "scripts/stage12_prepare_ra_g1.py"
    run = case.controller.Run(case.allocation, stage="bind", stage_seconds=120)
    try:
        with installed_production_audit(case, run, monkeypatch) as audit:
            run.sources()
            before = (run.checks, run.read_calls, run.read_bytes)
            data, objects = case.preparer.build(case.allocation, case.bootstrap, **case.kwargs)
            assert case.controller.digest(objects["resource_selection"]) == case.allocation["resource_selection_sha256"]
            assert data["selection"]["status"] == "UNISSUED"
            assert data["configuration"]["command_paths"] == {
                "source": case.allocation["paths"]["source"],
                "input": case.allocation["paths"]["input"],
                "output": case.allocation["paths"]["output"],
                "evidence_bundle": case.allocation["paths"]["binding"],
            }
            bundle = materialize(run, case, data, objects)
            actual = case.controller.parse(run.original(case.allocation["paths"]["input"]))
            assert actual == data
            case.diagnostic.validate_envelope(actual, G, for_execution=False)
            case.diagnostic.validate_workloads(actual)
            case.diagnostic.validate_resource_family(actual["version"], objects["resource_selection"])

            class ChargedOriginals:
                def read(self, path, *, limit, original):
                    return run.original(path, limit=limit)

            with s12_storage.read_view(ChargedOriginals()):
                case.diagnostic.validate_grants(actual, bundle)
            bound = case.controller.parse(run.original(
                bundle / "resource_evidence" / (case.controller.digest(objects["binding"]) + ".record")
            ))
            assert bound == objects["binding"]
            for campaign, phase in zip(actual["configuration"]["campaigns"], actual["phases"], strict=True):
                contract.validate_plan(campaign["plan"], campaign["profile"])
                assurance.validate_record(bound, campaign["profile"], phase["start"], contract,
                                          assurance.configuration_scope(actual["configuration"]))
            assert case.diagnostic.public_input_layout(
                Path(case.allocation["paths"]["input"]), bundle, case.private
            )
            for path in (case.root, *case.root.rglob("*")):
                assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
                if path.is_file():
                    assert path.stat().st_nlink == 1
            with pytest.raises(RuntimeError, match="RA_G1_DIAGNOSTIC_SELECTION_UNISSUED"):
                case.diagnostic.validate_envelope(actual, G, for_execution=True)
            with pytest.raises(PermissionError, match="RA_G1_DIAGNOSTIC_ACCESS_DENIED"):
                os.open(case.preparer.__file__, os.O_WRONLY | os.O_NOFOLLOW)
            with pytest.raises(PermissionError, match="RA_G1_DIAGNOSTIC_ACCESS_DENIED"):
                run.original(case.records / "synthetic_cgroup_original.record")
            run.sources()
            assert all(after > initial for after, initial in zip(
                (run.checks, run.read_calls, run.read_bytes), before, strict=True
            ))
            assert run.file_attempts > 20 and run.write_bytes > 0 and run.creations > 20
            assert run.checks <= case.allocation["accounting"]["check_calls"]
            assert run.read_calls <= case.allocation["accounting"]["original_read_calls"]
            assert audit["events"] > 100
    finally:
        run.close()


@pytest.mark.parametrize("mutation", ["extra_evidence", "replace_binding"])
def test_closed_production_selection_refuses_an_evidence_convenience_alias(production, mutation):
    allocation = deepcopy(production.allocation)
    allocation["paths"]["evidence"] = allocation["paths"]["binding"]
    if mutation == "replace_binding":
        del allocation["paths"]["binding"]
    with pytest.raises(RuntimeError, match="RA_G1_PATH"):
        production.controller.validate_selection(allocation)


def test_real_controller_preserves_mode_and_precreation_accounting_guards(production):
    case = production
    run = case.controller.Run(case.allocation, stage="bind", stage_seconds=120)
    try:
        run.mkdir(case.root)
        target = case.root / "synthetic_mode.record"
        run.write(target, {"SYNTHETIC_ONLY": True})
        target.chmod(0o644)
        with pytest.raises(RuntimeError, match="RA_G1_ORIGINAL_CHANGED"):
            run.original(target)
        before = run.write_bytes
        run.byte_limit = before
        denied = case.root / "underfunded.record"
        with pytest.raises(RuntimeError, match="RA_G1_COUNTER_LIMIT"):
            run.write(denied, {"SYNTHETIC_ONLY": True})
        assert not denied.exists()
        assert run.write_bytes > before
    finally:
        run.close()


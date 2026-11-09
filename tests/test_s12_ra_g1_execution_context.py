"""Explicit Linux simulation; these fixtures are never a live runtime release."""

from copy import deepcopy
import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as base
from test_s12_ra_g1_core import H, G, selection, binding


@pytest.fixture
def linux_simulation(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("SAFE_EXECUTION_SITE", "goethe-nhr")
    monkeypatch.setenv("SLURM_JOB_ID", "42")
    worker, supervisor = os.getpid(), os.getpid() + 10
    uid = os.geteuid()
    state = {"worker_start": 20, "supervisor_start": 10, "boot": "1" * 32}

    def raw(path, *, check, read_charge):
        check()
        read_charge(1, 8192)
        text = str(path)
        pid = int(Path(path).parts[2])
        if text.endswith("/stat"):
            parent = supervisor if pid == worker else 1
            start = (
                state["worker_start"] if pid == worker else state["supervisor_start"]
            )
            return f"{pid} (python) S {parent} " + "0 " * 17 + str(start) + "\n"
        if text.endswith("/status"):
            return f"Uid:\t{uid} {uid} {uid} {uid}\n"
        if text.endswith("/cgroup"):
            return "0::/selected\n"
        raise AssertionError("unexpected proc source")

    monkeypatch.setattr(e, "_kernel_text", raw)
    monkeypatch.setattr(
        e,
        "_live_domain",
        lambda **kw: dict(
            domain="/sys/fs/cgroup/selected",
            membership="0::/selected",
            boot_id=state["boot"],
            cgroup_namespace_inode=100,
            mount_namespace_inode=101,
        ),
    )
    allocation = tmp_path / "allocation"
    scratch = tmp_path / "scratch"
    allocation.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    evidence = allocation / "resource"
    selected = selection()
    paths = dict(
        allocation_root=str(allocation),
        resource_evidence_root=str(evidence),
        scratch_root=str(scratch),
    )
    context = e.capture_supervisor_context(
        scope=selected["scope"],
        source_git_sha=G,
        selection=selected,
        private_paths=paths,
        supervisor_pid=supervisor,
        run_nonce=H,
        check=lambda: None,
        read_charge=lambda n, k: None,
        clock_ns=lambda: 100,
    )
    return selected, context, evidence, state


def test_linux_simulation_actual_role_parser_and_closed_context(linux_simulation):
    selected, context, evidence, state = linux_simulation
    actual = e.validate_current_supervisor(
        context,
        binding=binding(selected),
        selection=selected,
        evidence_root=evidence,
        check=lambda: None,
        read_charge=lambda n, k: None,
        clock_ns=lambda: 200,
    )
    assert actual["pids"] == (os.getpid(), context["supervisor"]["pid"])
    assert Path(f"/proc/{os.getpid()}/stat") in actual["proc_paths"]
    assert all(
        "environ" not in str(path) and "/fd" not in str(path)
        for path in actual["proc_paths"]
    )
    assert "configuration_sha256" not in context and "binding_sha256" not in context
    state["supervisor_start"] += 1
    with pytest.raises(base.Stage12Error):
        e.validate_current_supervisor(
            context,
            binding=binding(selected),
            selection=selected,
            evidence_root=evidence,
            check=lambda: None,
            read_charge=lambda n, k: None,
            clock_ns=lambda: 200,
        )


def test_linux_simulation_context_mutation_job_boot_and_request_fail(
    linux_simulation, tmp_path, monkeypatch
):
    selected, context, evidence, state = linux_simulation
    path = evidence.parent / "supervisor.record"
    path.write_bytes(base.canonical(context))
    path.chmod(0o600)
    request = dict(
        schema_version=e.EXECUTION_REQUEST,
        supervisor_context_path=str(path),
        supervisor_context_sha256=c.digest(context),
    )
    assert (
        e.read_supervisor_context(
            request, check=lambda: None, read_charge=lambda n, k: None
        )
        == context
    )
    wrong = {**request, "unexpected": True}
    with pytest.raises(base.Stage12Error):
        e.validate_execution_request(wrong)
    state["boot"] = "2" * 32
    with pytest.raises(base.Stage12Error):
        e.validate_current_supervisor(
            context,
            binding=binding(selected),
            selection=selected,
            evidence_root=evidence,
            check=lambda: None,
            read_charge=lambda n, k: None,
            clock_ns=lambda: 200,
        )
    state["boot"] = context["boot_id"]
    monkeypatch.setenv("SLURM_JOB_ID", "43")
    with pytest.raises(base.Stage12Error):
        e.validate_current_supervisor(
            context,
            binding=binding(selected),
            selection=selected,
            evidence_root=evidence,
            check=lambda: None,
            read_charge=lambda n, k: None,
            clock_ns=lambda: 200,
        )
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(base.Stage12Error):
        e.read_supervisor_context(
            request, check=lambda: None, read_charge=lambda n, k: None
        )


def test_linux_simulation_protected_paths_are_explicit_not_public_prerequisite(
    linux_simulation,
):
    selected, context, evidence, state = linux_simulation
    assert context["protected_paths"] is None
    protected = deepcopy(context)
    protected["scope"] = "DEVELOPMENT_LOCAL_PREPARATION"
    with pytest.raises(base.Stage12Error):
        e.validate_supervisor_context(protected)
    protected["protected_paths"] = dict(
        bindings_path=str(evidence.parent / "bound.record"),
        registered_paths_record_sha256=H,
    )
    e.validate_supervisor_context(protected)

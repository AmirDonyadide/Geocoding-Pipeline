"""Small real closure/audit regression; invented workload, no native eligibility."""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_diagnostics as diagnostics,
    s12_public_reader as reader,
    s12_public_recovery as recovery,
    s12_public_runtime as runtime,
    s12_ra_g1_rep_ack_contract as ack,
    s12_ra_g1_rep_fair_contract as fair,
    s12_retrieval_contract as c,
    s12_transport as transport,
)
from stage12_synthetic import body, feature
from test_stage12_public_operations_v2 import H, KEY, offline  # noqa: F401
from test_stage12_public_sampling_integration import RealClock
from test_stage12_rep_ack_queue import selected_inputs

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fair_closure_selected_diagnostic", ROOT / "scripts/stage12_ra_g1_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def installed_audit(monkeypatch, output, input_path, evidence):
    """Install the real callback; disable only its post-test lifetime.

    Kernel seccomp is explicitly TEST_ONLY on this Mac. PublicReader's Linux
    path spelling is selected independently; the actual host dir_fd resolver,
    open calls, private ownership, audit predicate and denial remain unchanged.
    """
    armed = {"value": False, "opens": 0}
    hook, specification = sys.addaudithook, importlib.util.spec_from_file_location

    def register(callback):
        def audit(event, values):
            if armed["value"]:
                armed["opens"] += event == "open"
                callback(event, values)
        hook(audit)

    def spec(name, location, *args, **kwargs):
        result = specification(name, location, *args, **kwargs)
        if name == "ap2_existing_guard":
            actual = result.loader

            class HostKernelFixture:
                def create_module(self, selected):
                    return actual.create_module(selected)

                def exec_module(self, loaded):
                    actual.exec_module(loaded)
                    loaded.deny_linux_network = lambda: "TEST_ONLY_KERNEL_NOT_QUALIFIED"

            result.loader = HostKernelFixture()
        return result

    for target, names in (
        (socket, ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr")),
        (socket.socket, ("connect", "connect_ex", "bind", "listen", "sendto")),
        (subprocess, ("Popen", "run", "call", "check_output", "check_call")),
    ):
        for name in names:
            monkeypatch.setattr(target, name, getattr(target, name))
    monkeypatch.setattr(os, "open", os.open)
    monkeypatch.setattr(sys, "addaudithook", register)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", spec)
    _, native, _, limit, _, _ = diagnostic.install_denials(
        ROOT, output, input_path, evidence
    )
    assert native == "TEST_ONLY_KERNEL_NOT_QUALIFIED"
    limit[0] = 10000
    return armed


@pytest.mark.parametrize("wire", [ack, fair], ids=["ACK", "fair_service"])
def test_actual_second_snapshot_reopening_uses_selected_relative_work_reader(
    offline, tmp_path, monkeypatch, wire
):
    """Actual ACK caller, writer, staged snapshot, audit and full reopening.

    The tiny source-owned two-row authority/kernel/transport inputs are labelled
    TEST_ONLY. This proves the closure interface, never the native 512 program.
    """
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
    from test_stage12_ra_g1_integration import ra_inputs

    # The retained input is a genuine recovered original; only the tiny
    # programmatic workload/authorities below are invented. Native input role
    # strings stay intact and the local backing relationship is explicit.
    retained = os.environ.get("STAGE12_CLOSURE_RETAINED_INPUT")
    if retained:
        with open(retained, "rb") as original:
            before = os.fstat(original.fileno())
            assert 0 < before.st_size <= 2**20
            raw_input = original.read(2**20 + 1)
            assert before == os.fstat(original.fileno()) == os.stat(retained, follow_symlinks=False)
        assert len(raw_input) == before.st_size
        assert hashlib.sha256(raw_input).hexdigest() == "eaf28997d597f8df587a0c5c43b407600dc726154b3a102ffd5d8716f81eca44"
    else:
        native_root = "/panfs/TEST_ONLY/controlled/client_diagnostics/ra_g1_TEST_ONLY"
        raw_input = c.canonical(dict(configuration=dict(command_paths=dict(
            input=native_root + "/input.json", output=native_root + "/diagnostic",
            evidence_bundle=native_root + "/binding", source="/panfs/TEST_ONLY/integration_stage12/source_TEST_ONLY",
        ))))
    native_paths = json.loads(raw_input)["configuration"]["command_paths"]
    allocation = tmp_path / Path(native_paths["output"]).parent.name
    allocation.mkdir(mode=0o700)
    evidence = allocation / "binding"
    evidence.mkdir(mode=0o700)
    selected_input = allocation / "input.json"
    selected_input.write_bytes(raw_input)
    selected_input.chmod(0o600)
    output = allocation / "diagnostic"
    output.mkdir(mode=0o700)
    phase = output / "first64"
    outside = allocation / "outside"
    outside.write_bytes(b"NOT_AUTHORIZED")
    outside.chmod(0o600)
    alias = output / "alias"
    alias.symlink_to(outside)

    clock = RealClock()
    if wire is fair:
        from test_stage12_rep_fair_service import selected_inputs as fair_inputs
        p, plan, start, authority = fair_inputs(clock)
    else:
        p, plan, start, authority = selected_inputs(ack, clock)
    inventory = ra_inputs()[-1]
    failure = diagnostics.Failures(clock, closure=True)
    captured, stages, calls = [], [], []
    actual_snapshot = recovery.write_snapshot

    def snapshot(writer, value, **kwargs):
        captured.append(writer)
        return actual_snapshot(writer, value, **kwargs)

    actual_boundary = failure.closure_boundary

    def boundary(stage, **kwargs):
        stages.append((stage, kwargs.get("completed", False)))
        return actual_boundary(stage, **kwargs)

    monkeypatch.setattr(recovery, "write_snapshot", snapshot)
    monkeypatch.setattr(failure, "closure_boundary", boundary)
    monkeypatch.setattr(reader, "sys", SimpleNamespace(platform="linux"))
    armed = installed_audit(monkeypatch, output, selected_input, evidence)

    def dispatch(work, target, hooks):
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        calls.append(work["work_id"])
        raw = body([feature()])
        result = transport.Capture(
            "VALIDATION_REQUIRED", "OK", 200, "application/json", "identity",
            None, raw, len(raw), 1,
        )
        hooks.completed(result)
        return result

    report = None
    try:
        armed["value"] = True
        report = cli.run_operations_block(
            p, plan, start, work_factory=lambda: iter(authority.rows),
            output=phase, block_id=1, authority=authority, clock=clock,
            dispatch=dispatch, runtime_inventory=inventory, runtime_key=KEY,
            control_adapters={}, monitor=None, free_bytes=lambda: 2**40,
            segment_authority=H, writer_exclusion_evidence=H, epoch="1" * 64,
            writer_release_evidence=H, public_validation=Validation(),
            task_deadline_ns=clock.now_ns() + 180 * 10**9,
            diagnostics=failure,
        )
        # The actual failure before repair occurs after durable snapshot persist,
        # inside its second FreshReads/verify stage, before the exclusive seal.
        assert calls == [1, 2]
        assert ("REVALIDATE_FRESH", False) in stages
        assert report["report_complete"] is True, failure.snapshot()
        assert ("REVALIDATE_FRESH", True) in stages
        assert runtime.reopen_completed(
            phase, p, plan, start,
            validation_sha256=wire.digest(Validation().descriptor()),
        ) == report["blocks"][0]
        assert failure.snapshot()["closure_boundary"]["first_failure"] is None
        for path in (outside, alias, Path(f"/proc/{os.getpid()}/fd/0")):
            with pytest.raises(PermissionError):
                os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        assert armed["opens"] > 0
    finally:
        armed["value"] = False
        for writer in captured:
            writer.abort()
            assert not writer.thread.is_alive()
        result = dict(
            scope="TEST_ONLY_CURRENT_CLOSURE_INTERFACE_NOT_NATIVE_OR_HISTORICAL_CAUSE",
            input_origin="GENUINE_BOUND_RETAINED_ORIGINAL" if retained else "SYNTHETIC_TEST_ONLY",
            selected_test_profile=wire.PROFILE,
            genuine_input_sha256=hashlib.sha256(raw_input).hexdigest(),
            native_paths=native_paths,
            physical_backing=dict(output=str(output), input=str(selected_input), evidence_bundle=str(evidence), source=str(ROOT)),
            platform="LINUX_READER_PATH_SELECTION_WITH_REAL_HOST_DIR_FD_AND_INSTALLED_AUDIT",
            denial_predicates="UNCHANGED", calls=calls, closure_stages=stages,
            diagnostics=failure.snapshot(),
            report_complete=report.get("report_complete") if report else None,
            all_owned_writers_joined=all(not writer.thread.is_alive() for writer in captured),
        )
        raw = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
        assert len(raw) <= 16384
        fd = os.open(tmp_path / "CLOSURE_RESULT.record", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            assert os.write(fd, raw) == len(raw)
        finally:
            os.close(fd)

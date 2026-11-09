"""Finite public workflow tests use invented originals, never service grants."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import os
from pathlib import Path
import sys
import time

import pytest

from test_stage12_public_operations_v2 import offline  # noqa:F401
from test_stage12_ra_g1_public_preparation import synthetic_inputs, public_accounting
from test_s12_ra_g1_core import observation, original_observation, H, G
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "public_workflow", ROOT / "scripts/stage12_ra_g1_public_workflow.py"
)
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)


def inputs(tmp_path):
    _, _, bootstrap, kwargs = synthetic_inputs()
    selected = deepcopy(bootstrap["capacity"])
    from test_stage12_ra_g1_public_preparation import builder

    template, allocation, _, _ = synthetic_inputs()
    allocation["paths"] = {
        key: str(tmp_path / key) for key in ("source", "input", "output", "evidence")
    }
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    code = source / "invented.py"
    code.write_bytes(b"# invented code only\n")
    code.chmod(0o644)
    sources = [
        dict(
            path="invented.py",
            bytes=code.stat().st_size,
            sha256=w.hashed(code.read_bytes()),
        )
    ]
    allocation["source_files"] = sources
    allocation["accounting_inventory"], allocation["accounting"] = public_accounting(
        sources
    )
    selected = builder.compile_selection(
        allocation,
        template,
        policy_sha256=H,
        adoption_sha256=H,
        descriptor_inventory_sha256=H,
        paths_sha256=H,
        implementation_review_sha256=H,
    )
    records = tmp_path / "records"
    records.mkdir(mode=0o700)
    root = tmp_path / "allocation"
    paths = {key: str(root / key) for key in w.PATHS}
    paths.update(
        source=str(source),
        records=str(records),
        allocation_root=str(root),
        output=str(tmp_path / ("or2_" + H)),
    )
    start = datetime.now(timezone.utc) - timedelta(minutes=1)
    end = start + timedelta(days=1)

    def stamp(x):
        return x.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    selected.update(valid_from=stamp(start), valid_until=stamp(end))
    s = dict(
        version=w.VERSION,
        scope=w.SCOPE,
        source_sha=G,
        intent_id=H,
        task_id=H,
        valid_from=stamp(start),
        valid_until=stamp(end),
        paths=paths,
        limits=deepcopy(w.LIMITS),
        records={key: H for key in w.RECORDS},
        source_files=sources,
        accounting=allocation["accounting"],
        accounting_inventory=allocation["accounting_inventory"],
        resource_selection_sha256=w.digest(selected),
    )
    return s, selected, kwargs


def run_at(tmp_path):
    s, selected, _ = inputs(tmp_path)
    at = time.monotonic_ns()
    run = w.Run(s, selected, epoch_ns=at, role_entry_ns=at)
    return run


def test_public_selection_exact_paths_limits_and_no_protected_scope(tmp_path):
    s, _, _ = inputs(tmp_path)
    w.validate_selection(s)
    for key in ("scope", "limits", "paths"):
        bad = deepcopy(s)
        if key == "scope":
            bad[key] = "DEVELOPMENT_ONLY"
        elif key == "limits":
            bad[key]["non_b_bytes"] += 1
        else:
            bad[key]["configuration"] = "/OUTSIDE/public.json"
        with pytest.raises(RuntimeError):
            w.validate_selection(bad)


def test_public_original_one_byte_reads_charge_actual_bytes_and_eof(
    tmp_path, monkeypatch
):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    path = root / "original.record"
    path.write_bytes(b"abcd")
    path.chmod(0o600)
    real = os.read
    charges = []
    monkeypatch.setattr(w.os, "read", lambda fd, size: real(fd, min(1, size)))
    assert (
        w.original(
            path, limit=8, charge=lambda calls, size: charges.append((calls, size))
        )
        == b"abcd"
    )
    assert sum(row[0] for row in charges) == 5
    assert sum(row[1] for row in charges) == 4
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        w.original(path)


def test_public_metadata_partial_write_is_poisoned_and_never_refunded(
    tmp_path, monkeypatch
):
    run = run_at(tmp_path)
    root = Path(run.s["paths"]["allocation_root"])
    run.mkdir(root)
    target = root / "partial.record"
    real = os.write
    calls = []

    def partial(fd, raw):
        calls.append(True)
        if len(calls) == 1:
            return real(fd, raw[:3])
        raise OSError("synthetic uncertain write")

    monkeypatch.setattr(w.os, "write", partial)
    try:
        with pytest.raises(OSError):
            run.write_raw(target, b"invented-original")
        assert target.read_bytes() == b"inv" and run.poisoned
        assert (
            run.metadata_bytes == len(b"invented-original")
            and run.metadata_creations == 2
        )
        with pytest.raises(RuntimeError):
            run.write_raw(root / "retry.record", b"retry")
        assert not (root / "retry.record").exists()
    finally:
        run.close()


def test_public_source_stream_stops_at_captured_size_plus_eof(tmp_path, monkeypatch):
    run = run_at(tmp_path)
    real = os.read
    requests = []

    def one_byte(fd, size):
        requests.append(size)
        return real(fd, min(size, 1))

    monkeypatch.setattr(w.os, "read", one_byte)
    try:
        run.sources()
        expected = run.s["source_files"][0]["bytes"]
        snap = run.ledger.snapshot_source()
        assert (
            snap["source_read_calls"] == expected + 1
            and snap["source_read_bytes"] == expected
        )
        assert requests[-1] == 1
        code = Path(run.s["paths"]["source"]) / "invented.py"
        code.write_bytes(code.read_bytes() + b"growth")
        with pytest.raises(RuntimeError):
            run.sources()
    finally:
        run.close()


def test_public_provider_closed_until_explicit_runtime_opener(tmp_path):
    guard = w.ProviderGuard(tmp_path)
    called = []
    try:
        with pytest.raises(RuntimeError):
            guard.provider(lambda: called.append(True), released=lambda: False)
        assert called == []
        with pytest.raises(RuntimeError, match="PROVIDER_CLOSED"):
            sys.audit("socket.connect", object(), ("public.invalid", 443))
        secret = object()
        assert guard.provider(lambda: secret, released=lambda: True) is secret
        assert guard.opened
        with pytest.raises(RuntimeError):
            guard.provider(lambda: secret, released=lambda: True)
    finally:
        guard.close()


def retain(run, role, raw, suffix):
    identity = w.hashed(raw)
    run.s["records"][role] = identity
    path = Path(run.s["paths"]["records"]) / (identity + suffix)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_public_launch_gate_requires_retained_complete_source_exact_B(tmp_path):
    run = run_at(tmp_path)
    kwargs = synthetic_inputs()[3]
    try:
        report = kwargs["representative_report"]
        manifest = kwargs["representative_manifest"]
        outcome = kwargs["representative_outcome"]
        retain(run, "representative_outcome", w.canonical(outcome), ".record")
        report_path = retain(run, "representative_report", report, ".md")
        retain(run, "representative_manifest", manifest, ".manifest")
        assert w.verify_launch_gate(run.s, run.read)[0]["actual_reopening"]
        report_path.write_bytes(report + b"changed")
        with pytest.raises(RuntimeError):
            w.verify_launch_gate(run.s, run.read)
    finally:
        run.close()


def test_public_review_timeout_is_nonreset_and_no_fabricated_review(
    tmp_path, monkeypatch
):
    run = run_at(tmp_path)
    run.mkdir(Path(run.s["paths"]["allocation_root"]))
    try:
        path = Path(run.s["paths"]["review"])
        at = time.monotonic_ns()
        with pytest.raises(RuntimeError, match="REVIEW_TIMEOUT"):
            w.wait_record(run, path, at - 1)
        assert not path.exists()
    finally:
        run.close()


def test_public_wait_uses_actual_os_return_and_exact_worker_identity(tmp_path):
    # Tiny no-input child; this is a synthetic protocol test, never a live PASS.
    pid = os.posix_spawn(
        sys.executable, [sys.executable, "-c", "pass"], {"PATH": os.defpath}
    )
    actual, status = os.waitpid(pid, 0)
    assert actual == pid and status == 0
    s, _, _ = inputs(tmp_path)
    context = dict(supervisor=dict(pid=os.getpid()))
    value = dict(
        version=w.WAIT,
        source_sha=G,
        selection_sha256=w.digest(s),
        supervisor_pid=os.getpid(),
        pid=pid,
        exit_code=0,
        wait_status=status,
        observed_mono_ns_lower=time.monotonic_ns(),
    )
    w.validate_wait(value, s, context, pid)
    for key, changed in [
        ("pid", pid + 1),
        ("wait_status", True),
        ("exit_code", 1),
        ("selection_sha256", "3" * 64),
    ]:
        bad = dict(value, **{key: changed})
        with pytest.raises(RuntimeError):
            w.validate_wait(bad, s, context, pid)


def test_public_setup_monitor_precedes_metadata_and_actual_source_open(
    tmp_path, monkeypatch
):
    run = run_at(tmp_path)
    run.mkdir(Path(run.s["paths"]["allocation_root"]))
    actual_start = e.start_administrative_session
    context = dict(
        supervisor=dict(pid=os.getppid()), visible_cgroup_path="/SYNTHETIC/ONLY"
    )
    monkeypatch.setattr(e, "capture_supervisor_context", lambda **kw: context)
    monkeypatch.setattr(
        e,
        "_process_identity",
        lambda pid, **kw: (dict(pid=pid, start_ticks=0, uid=os.getuid()), os.getppid()),
    )

    def start(**kwargs):
        def observer_factory(retain):
            def acquire(kind):
                row = observation(run.selected, enter=time.monotonic_ns(), kind=kind)
                row["phase_id"] = 13
                row["counters"] = run.counters()
                row["visible_identity_inventory_sha256"] = retain(
                    original_observation(row)
                )
                return {
                    key: row[key]
                    for key in (
                        "readings",
                        "counters",
                        "native_visibility",
                        "visible_identity_inventory_sha256",
                    )
                }

            return acquire

        return actual_start(**kwargs, observer_factory=observer_factory, test_only=True)

    monkeypatch.setattr(e, "start_administrative_session", start)
    try:
        w.begin_setup(run)
        assert run.session.monitor.coverage.seq >= 1 and not run.session.completed
        before = run.ledger.snapshot_source()
        artifact = Path(run.s["paths"]["allocation_root"]) / "synthetic_metadata.record"
        run.write(artifact, {"SYNTHETIC_ONLY": True})
        opened = []

        def actual_open():
            run.sources()
            opened.append(True)
            return w.parse(run.read(artifact))

        result, _ = run.session.freeze_and_open(
            frozen_data_inventory_sha256=w.digest({"SYNTHETIC_ONLY": True}),
            actual_opener=actual_open,
        )
        assert result == {"SYNTHETIC_ONLY": True} and opened == [True]
        assert run.session.completed and run.session.protocol.state == "MONITOR_CLOSED"
        assert (
            run.ledger.snapshot_source()["source_read_calls"]
            > before["source_read_calls"]
        )
        assert run.controls.snapshot()["monitor_rows"] >= 2
    finally:
        run.close()


def test_public_final_handoff_derives_only_successful_exact_suffix_and_tail_carry(
    tmp_path,
):
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
        ApplicationControls,
    )

    run = run_at(tmp_path)
    run.mkdir(Path(run.s["paths"]["allocation_root"]))
    run.controls = ApplicationControls(run.selected, check=run.check)
    run.controls.reserve_components(run.non_b_bytes, run.non_b_creations)
    for phase in range(1, 13):
        run.ledger.enter_stage(phase)
    run.role_end = run.end
    try:
        value = run.final_handoff({"SYNTHETIC_ONLY": True}, {"SYNTHETIC_ONLY": True})
        raw = (
            Path(run.s["paths"]["allocation_root"]) / "worker_handoff.record"
        ).read_bytes()
        assert w.parse(raw) == value
        final = w.derive_worker_prefix(value, len(raw))
        assert final == run.ledger.snapshot_source()
        assert (
            final["source_read_calls"]
            == value["source_counter_prefix"]["source_read_calls"] + 2
        )
        assert final["source_read_bytes"] == value["source_counter_prefix"][
            "source_read_bytes"
        ] + len(raw)
        assert (
            final["identity_checks"]
            == value["source_counter_prefix"]["identity_checks"] + 3
        )
        tail = w.Run(
            run.s,
            run.selected,
            epoch_ns=run.epoch,
            role_entry_ns=time.monotonic_ns(),
            terminal=True,
        )
        try:
            tail.ledger.read_charge(1, 7)
            tail.ledger.add_verified_prefix(final)
            assert (
                tail.ledger.snapshot_source()["source_read_calls"]
                == final["source_read_calls"] + 1
            )
            assert tail.ledger.limit_basis()["phase_id"] == 14
            assert tail.ledger.limit_basis()["stage_entry_source_prefix"] == final
            with pytest.raises(Exception):
                tail.ledger.add_verified_prefix(final)
        finally:
            tail.close()
    finally:
        run.close()


def test_public_final_handoff_short_write_cannot_supply_a_qualified_prefix(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
        ApplicationControls,
    )

    run = run_at(tmp_path)
    run.mkdir(Path(run.s["paths"]["allocation_root"]))
    run.controls = ApplicationControls(run.selected, check=run.check)
    run.controls.reserve_components(run.non_b_bytes, run.non_b_creations)
    for phase in range(1, 13):
        run.ledger.enter_stage(phase)
    run.role_end = run.end
    real = os.write
    monkeypatch.setattr(w.os, "write", lambda fd, raw: real(fd, raw[:3]))
    try:
        with pytest.raises(RuntimeError, match="WRITE_UNCERTAIN"):
            run.final_handoff({}, {})
        assert run.poisoned and run.metadata_bytes == 8192
        assert (
            Path(run.s["paths"]["allocation_root"]) / "worker_handoff.record"
        ).stat().st_size == 3
    finally:
        run.close()


def test_public_shell_syntax_and_finite_source_roles(tmp_path):
    shell = (
        ROOT / "cluster/goethe_nhr/stage12_ra_g1_public_allocation.sbatch"
    ).read_text()
    assert shell.count("public_run 8040 PHASE_RUNNER") == 1
    assert shell.count("public_run 120 TERMINAL_VERIFIER") == 1
    assert "rsync" not in shell and "git pull" not in shell
    assert 'wait "$pid"' in shell and "wait_status" in shell
    assert "COLLECTOR)" not in shell and "BINDER)" not in shell


@pytest.mark.parametrize(
    "kind",
    ["public-worker", "public-verify", "representative", "public-metadata-missing"],
)
def test_isolated_actual_main_imports_own_checkout_and_keeps_genuine_prefix_available(
    tmp_path, kind
):
    """Real installed metadata supplies version only; every code module is pinned."""
    s, selected, _ = inputs(tmp_path)
    clean = tmp_path / "clean_checkout"
    for relative in (
        ".",
        "scripts",
        "src",
        "src/safe_geocoding_pipeline",
        "src/safe_geocoding_pipeline/preprocessing",
        "src/safe_geocoding_pipeline/preprocessing/stages",
    ):
        (clean / relative).mkdir(mode=0o700)
    for relative in (
        "pyproject.toml",
        "scripts/stage12_ra_g1_public_workflow.py",
        "scripts/stage12_ra_g1_allocation.py",
        "src/safe_geocoding_pipeline/__init__.py",
        "src/safe_geocoding_pipeline/execution_policy.py",
        "src/safe_geocoding_pipeline/preprocessing/__init__.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/__init__.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_accounting.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_source_counters.py",
    ):
        target = clean / relative
        target.write_bytes((ROOT / relative).read_bytes())
        target.chmod(0o600)
    assert not list(clean.rglob("*.egg-info")) and not list(clean.rglob("*.dist-info"))
    s["paths"]["source"] = str(clean)
    if kind == "representative":
        from test_stage12_ra_g1_allocation_controller import controller
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_ra_g1_accounting as ac,
        )

        rep = controller()
        root = Path(s["paths"]["allocation_root"])
        paths = {
            key: str(root / key)
            for key in (
                "bootstrap",
                "binding",
                "input",
                "output",
                "review",
                "release",
                "outcome",
                "context",
                "worker_return",
                "supervisor_state",
                "tail",
            )
        }
        paths.update(
            source=str(clean),
            allocation_root=str(root),
            records=s["paths"]["records"],
            log=str(Path(s["paths"]["records"]) / "slurm.log"),
        )
        inv, account = ac.compile_inventory(
            s["source_files"], s["accounting_inventory"]["backends"], rep.SCOPE
        )
        s = dict(
            version=rep.VERSION,
            scope=rep.SCOPE,
            source_sha=G,
            valid_from=s["valid_from"],
            valid_until=s["valid_until"],
            paths=paths,
            source_files=s["source_files"],
            accounting=account,
            accounting_inventory=inv,
            limits=rep.LIMITS,
            replay_sha256=H,
            resource_selection_sha256=H,
            intent_id=H,
            records={
                key: H
                for key in (
                    "adoption",
                    "project_approval",
                    "software_review",
                    "resource_review",
                )
            },
        )
        script = clean / "scripts/stage12_ra_g1_allocation.py"
    else:
        script = clean / "scripts/stage12_ra_g1_public_workflow.py"
    selection_path = tmp_path / "selection.json"
    selection_path.write_bytes(w.canonical(s))
    selection_path.chmod(0o600)
    selected_path = tmp_path / "resource.json"
    selected_path.write_bytes(w.canonical(selected))
    selected_path.chmod(0o600)
    marker = tmp_path / "observed_local_stop.json"
    child_code = """
import importlib.util,json,os,pathlib,sys
script,selection,identity,resource,kind,marker=sys.argv[1:]
def deny(event,args):
    if event.startswith(("socket.","subprocess.","os.system","os.exec","os.spawn")):
        raise RuntimeError("SYNTHETIC_CHILD_NETWORK_PROCESS_DENIED")
    if event=="open" and args and isinstance(args[0],(str,bytes)):
        name=os.fsdecode(args[0]).lower()
        if any(part in name for part in ("/holdout/","/protected_synthetic_sentinel","/.ssh/","pelias_api_key")):
            raise RuntimeError("SYNTHETIC_CHILD_PROVIDER_PROTECTED_DENIED")
sys.addaudithook(deny)
spec=importlib.util.spec_from_file_location("actual_source_entry",script)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def save(value):
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:os.write(fd,json.dumps(value,sort_keys=True).encode());os.fsync(fd)
    finally:os.close(fd)
def project_origins():
    checkout=pathlib.Path(script).resolve().parents[1]
    paths={name:str(pathlib.Path(value.__file__).resolve()) for name,value in sys.modules.items()
        if (name=="safe_geocoding_pipeline" or name.startswith("safe_geocoding_pipeline."))
        and getattr(value,"__file__",None)}
    assert paths and all(pathlib.Path(path).is_relative_to(checkout/"src"/"safe_geocoding_pipeline")
        for path in paths.values())
    import importlib.metadata
    project=sys.modules["safe_geocoding_pipeline"]
    distribution=importlib.metadata.distribution(project.DISTRIBUTION_NAME)
    return dict(project_files=paths,version=project.__version__,distribution=project.DISTRIBUTION_NAME,
        metadata_path=str(distribution._path))
if kind=="public-metadata-missing":
    import importlib.metadata
    try:importlib.metadata.distribution("safe-geocoding-pipeline")
    except importlib.metadata.PackageNotFoundError:
        save(dict(state="REAL_DISTRIBUTION_METADATA_MISSING"))
    else:raise SystemExit(91)
    def no_run(*args,**kwargs):
        fd=os.open(marker+".run",os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
        raise RuntimeError("RUN_MUST_NOT_START_WITHOUT_METADATA")
    module.Run=no_run
    raise SystemExit(module.main(["worker","--selection",selection,"--selection-sha256",identity,
        "--resource-selection",resource]))
elif kind=="representative":
    def stop(*args,**kwargs):
        save(dict(state="AFTER_REAL_COMPILER_BEFORE_NATIVE_DENIAL_TEST_STOP",
            compiler=sys.modules["safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_accounting"].__file__,
            **project_origins()))
        raise SystemExit(2)
    module.install_denials=stop
    sys.argv=[script,"collect","--selection",selection,"--selection-sha256",identity]
    module.main()
else:
    command="worker" if kind=="public-worker" else "verify"
    original=getattr(module,"worker" if command=="worker" else "verifier")
    def observe(run):
        before=run.ledger.snapshot_source()
        info=dict(phase=run.ledger.limit_basis()["phase_id"],prefix_spent=run.ledger._prefix_added,
            source_read_calls=before["source_read_calls"],source_read_bytes=before["source_read_bytes"],
            identity_checks=before["identity_checks"])
        try:return original(run)
        except Exception as error:
            info.update(state="REAL_SITE_GUARD_REJECTED",code=getattr(error,"code",None))
            info.update(project_origins());save(info);raise
    setattr(module,"worker" if command=="worker" else "verifier",observe)
    raise SystemExit(module.main([command,"--selection",selection,"--selection-sha256",identity,
        "--resource-selection",resource]))
"""
    capture = tmp_path / "child_output.log"
    fd = os.open(capture, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        pid = os.posix_spawn(
            sys.executable,
            [
                sys.executable,
                "-I",
                *(["-S"] if kind == "public-metadata-missing" else []),
                "-B",
                "-c",
                child_code,
                str(script),
                str(selection_path),
                w.hashed(selection_path.read_bytes()),
                str(selected_path),
                kind,
                str(marker),
            ],
            {
                "PATH": os.defpath,
                "SAFE_EXECUTION_SITE": "macos",
                "STAGE12_RA_EPOCH_NS": str(time.monotonic_ns()),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            file_actions=[(os.POSIX_SPAWN_DUP2, fd, 1), (os.POSIX_SPAWN_DUP2, fd, 2)],
        )
        _, status = os.waitpid(pid, 0)
    finally:
        os.close(fd)
    assert os.waitstatus_to_exitcode(status) == 2, capture.read_text()
    import json

    observed = json.loads(marker.read_bytes())
    if kind == "public-metadata-missing":
        assert observed["state"] == "REAL_DISTRIBUTION_METADATA_MISSING"
        assert "RA_G1_PROJECT_DISTRIBUTION_REQUIRED" in capture.read_text()
        assert not Path(str(marker) + ".run").exists()
    elif kind == "representative":
        assert observed["state"] == "AFTER_REAL_COMPILER_BEFORE_NATIVE_DENIAL_TEST_STOP"
        assert Path(observed["compiler"]).is_relative_to(clean / "src")
    else:
        assert observed["state"] == "REAL_SITE_GUARD_REJECTED"
        assert observed["code"] == "HEAVY_PROCESS_CLUSTER_REQUIRED"
        assert observed["phase"] == (13 if kind == "public-worker" else 14)
        assert observed["prefix_spent"] is False
        assert (
            observed["source_read_calls"] > 0
            and observed["source_read_bytes"] > 0
            and observed["identity_checks"] > 0
        )
    if kind != "public-metadata-missing":
        assert (
            observed["version"] == "0.2.0"
            and observed["distribution"] == "safe-geocoding-pipeline"
        )
        assert (
            Path(observed["metadata_path"]).name
            == "safe_geocoding_pipeline-0.2.0.dist-info"
        )
        assert all(
            Path(path).is_relative_to(clean / "src" / "safe_geocoding_pipeline")
            for path in observed["project_files"].values()
        )
    assert not Path(s["paths"]["allocation_root"]).exists()


def test_public_existing_distribution_version_matches_pinned_project():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["name"] == "safe-geocoding-pipeline"
    assert project["version"] == w.SOURCE_PROJECT_VERSION == "0.2.0"

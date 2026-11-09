"""Allocation-controller author tests; all authority/kernel inputs SYNTHETIC_ONLY.

Private local file I/O is real. No live kernel, geocoder, protected input or
source/controller permission is obtained or issued by these orchestration fakes.
"""

from copy import deepcopy
from contextlib import contextmanager
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_core import selection, binding, facts, H, G
from test_stage12_ra_g1_allocation import synthetic_accounting

ROOT = Path(__file__).resolve().parents[1]


def controller():
    spec = importlib.util.spec_from_file_location(
        "synthetic_allocation_controller", ROOT / "scripts/stage12_ra_g1_allocation.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def world(tmp_path, monkeypatch, offline):  # noqa: F811
    m = controller()
    monkeypatch.setattr(m, "now", lambda: "2026-01-01T00:00:00.000000Z")
    source, records = tmp_path / "source", tmp_path / "records"
    source.mkdir(mode=0o700)
    records.mkdir(mode=0o700)
    code = b"# SYNTHETIC_ONLY, NOT AN EXECUTABLE REVIEWED SOURCE\n"
    (source / "synthetic_only.py").write_bytes(code)
    report = b"SYNTHETIC_ONLY INDEPENDENT-REVIEW FIXTURE, NO LIVE RELEASE\n"
    report_hash = hashlib.sha256(report).hexdigest()
    (records / (report_hash + ".md")).write_bytes(report)
    (records / (report_hash + ".md")).chmod(0o600)
    objects = {
        "adoption": dict(
            origin="SYNTHETIC_ONLY",
            decision="ADOPTED_PROSPECTIVELY_WITH_EXPLICIT_LOCAL_REPAIR_OVERRIDE",
        ),
        "project_approval": dict(
            origin="SYNTHETIC_ONLY",
            attribution="OWNER_REPORTED_PROJECT_APPROVAL_NOT_ADMIN_ATTESTATION",
            scope=m.SCOPE,
        ),
        "software_review": dict(
            origin="SYNTHETIC_ONLY",
            disposition="PASS",
            source_sha=G,
            report_sha256=report_hash,
        ),
        "resource_review": dict(
            origin="SYNTHETIC_ONLY",
            disposition="PASS",
            source_sha=G,
            descriptor_inventory_sha256=H,
            workload_graph_sha256=H,
            paths_sha256=H,
        ),
    }
    hashes = {}
    for name, value in objects.items():
        identity = m.digest(value)
        hashes[name] = identity
        path = records / (identity + ".record")
        path.write_bytes(m.canonical(value))
        path.chmod(0o600)
    root = tmp_path / "allocation"
    paths = dict(source=str(source), records=str(records), allocation_root=str(root))
    paths.update(
        {
            key: str(
                root
                / (
                    key
                    + (
                        ".record"
                        if key not in ("bootstrap", "binding", "output")
                        else ""
                    )
                )
            )
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
                "log",
            )
        }
    )
    paths["log"] = str(records / "slurm.log")
    selected = selection("REPRESENTATIVE_NO_SERVICE")
    s = dict(
        version=m.VERSION,
        scope=m.SCOPE,
        source_sha=G,
        valid_from="2026-01-01T00:00:00.000000Z",
        valid_until="2026-01-02T00:00:00.000000Z",
        paths=paths,
        source_files=[
            dict(
                path="synthetic_only.py",
                bytes=len(code),
                sha256=hashlib.sha256(code).hexdigest(),
            )
        ],
        accounting=dict(
            identity_calls=100000,
            check_calls=1000000,
            original_read_calls=1000000,
            original_read_bytes=2**32,
        ),
        limits=deepcopy(m.LIMITS),
        replay_sha256=H,
        resource_selection_sha256=m.digest(selected),
        intent_id=H,
        records=hashes,
    )
    s["accounting_inventory"], s["accounting"] = synthetic_accounting(s["source_files"])

    from test_s12_ra_g1_accounting import inputs as accounting_test_inputs
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting

    _, backend_arithmetic_fixture = accounting_test_inputs()
    s["accounting_inventory"], s["accounting"] = s12_ra_g1_accounting.compile_inventory(
        s["source_files"], backend_arithmetic_fixture, m.SCOPE
    )

    @contextmanager
    def run(stage):
        value = m.Run(deepcopy(s), stage=stage, stage_seconds=30)
        try:
            yield value
        finally:
            value.close()

    return NS(
        m=m,
        s=s,
        root=root,
        source=source,
        records=records,
        objects=objects,
        selected=selected,
        run=run,
    )


def put(world, path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(world.m.canonical(value))
    path.chmod(0o600)
    return world.m.digest(value)


def test_ready_uses_exact_synthetic_originals_and_changed_source_denies(world):
    with world.run("ready") as run:
        assert world.m.ready(run)
        assert run.write_bytes == run.creations == 0
    (world.source / "synthetic_only.py").write_bytes(b"changed")
    with world.run("ready") as run:
        with pytest.raises(RuntimeError, match="RA_G1_SOURCE_CHANGED"):
            world.m.ready(run)


@pytest.mark.parametrize("mutation", ["grow", "truncate"])
def test_source_hash_has_captured_byte_boundary_and_change_detection(
    world, monkeypatch, mutation
):
    target = world.source / "synthetic_only.py"
    saved_read = world.m.os.read
    calls = []

    def changed_read(fd, amount):
        raw = saved_read(fd, amount)
        calls.append(amount)
        if len(calls) == 1:
            with target.open("ab" if mutation == "grow" else "wb") as stream:
                stream.write(b"CHANGED" if mutation == "grow" else b"")
        return raw

    monkeypatch.setattr(world.m.os, "read", changed_read)
    with world.run("ready") as run:
        with pytest.raises(RuntimeError, match="RA_G1_SOURCE_CHANGED"):
            run.sources()
    assert calls == [len(b"# SYNTHETIC_ONLY, NOT AN EXECUTABLE REVIEWED SOURCE\n"), 1]


def test_private_unicode_fsync_readback_and_exact_actual_read_accounting(world):
    world.root.mkdir(mode=0o700)
    with world.run("collect") as run:
        payload = dict(origin="SYNTHETIC_ONLY", native="Αθήνα ایران 😀", postal="00123")
        path = world.root / "unicode.record"
        assert run.write(path, payload) == world.m.digest(payload)
        raw = path.read_bytes()
        assert raw.isascii() and b"\\u" in raw and world.m.parse(raw) == payload
        assert run.read_calls > 0, (
            "writer fsync/readback must consume actual original-read counters"
        )
        big = world.root / "large.record"
        big.write_bytes(b"x" * 9000)
        big.chmod(0o600)
        before = (run.read_calls, run.read_bytes)
        assert run.original(big, limit=10000) == b"x" * 9000
        assert (run.read_calls - before[0], run.read_bytes - before[1]) == (4, 9000)


@pytest.mark.parametrize("stage", ["ready", "collect", "bind", "verify"])
def test_stage_partitions_are_nonrefundable_and_fail_before_create(world, stage):
    world.root.mkdir(mode=0o700)
    with world.run(stage) as run:
        run.charge(run.byte_limit, creations=run.creation_limit)
        with pytest.raises(RuntimeError, match="RA_G1_COUNTER_LIMIT"):
            run.write(world.root / (stage + ".record"), {"origin": "SYNTHETIC_ONLY"})
        assert not (world.root / (stage + ".record")).exists()
        assert run.creations == run.creation_limit + 1
        assert run.write_bytes > run.byte_limit


def test_missing_stale_and_noncanonical_records_and_deadlines_fail(world, monkeypatch):
    world.root.mkdir(mode=0o700)
    with world.run("collect") as run:
        run.end = world.m.time.monotonic_ns() - 1
        with pytest.raises(RuntimeError, match="RA_G1_DEADLINE"):
            run.check()
    with world.run("bind") as run:
        with pytest.raises(RuntimeError, match="RA_G1_REVIEW_TIMEOUT"):
            world.m.wait_record(
                run,
                world.root / "missing.record",
                deadline_ns=world.m.time.monotonic_ns() - 1,
            )
    for raw in (b'{"a":1,"a":2}\n', b'{"a":1} ', b'{"a":NaN}\n'):
        with pytest.raises((RuntimeError, ValueError)):
            world.m.parse(raw)


def test_uncertain_writer_preserves_first_error_and_partial_file(world, monkeypatch):
    world.root.mkdir(mode=0o700)
    first = OSError(28, "SYNTHETIC_ONLY unsafe detail must not enter safe diagnostics")

    def fail(fd):
        raise first

    monkeypatch.setattr(world.m.os, "fsync", fail)
    with world.run("collect") as run:
        path = world.root / "partial.record"
        with pytest.raises(OSError) as actual:
            run.write(path, {"origin": "SYNTHETIC_ONLY"})
        assert actual.value is first and run.poisoned and path.exists()
        charged = (run.write_bytes, run.creations)
        with pytest.raises(RuntimeError, match="RA_G1_WRITE_UNCERTAIN"):
            run.write(world.root / "must-not-exist", {})
        assert (run.write_bytes, run.creations) == charged


def test_metadata_original_refuses_symlink_hardlink_wrong_mode(world):
    world.root.mkdir(mode=0o700)
    path = world.root / "original.record"
    path.write_bytes(b"{}\n")
    path.chmod(0o600)
    alias = world.root / "alias.record"
    alias.symlink_to(path)
    with pytest.raises(RuntimeError):
        world.m.read(alias)
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        world.m.read(path)


def test_original_phase_endpoints_cannot_borrow_parent_suffix_time(world):
    row = dict(phase_id=1, phase_start_ns=100, phase_deadline_ns=200)
    originals = dict(
        opener_return=dict(actual_opener_return_ns=140),
        monitor_terminal=dict(
            coverage_start_ns=110, final_observation_ns=150, last_ack_ns=160
        ),
        worker_validation=dict(first_pass_end_ns=180),
    )
    world.m.validate_original_phase_times(row, originals, world.selected, 1000)
    for family, key in (
        ("opener_return", "actual_opener_return_ns"),
        ("monitor_terminal", "final_observation_ns"),
        ("monitor_terminal", "last_ack_ns"),
        ("worker_validation", "first_pass_end_ns"),
    ):
        altered = deepcopy(originals)
        altered[family][key] = 200
        with pytest.raises(RuntimeError, match="RA_G1_DEADLINE"):
            world.m.validate_original_phase_times(row, altered, world.selected, 1000)


def test_future_epoch_and_external_stdout_parent_are_explicit(world):
    selected = deepcopy(world.s)
    selected["paths"]["log"] = str(world.records / "slurm.log")
    world.m.validate_selection(selected)
    selected["paths"]["log"] = str(world.root / "slurm.log")
    with pytest.raises(RuntimeError, match="RA_G1_PATH"):
        world.m.validate_selection(selected)
    with pytest.raises(RuntimeError, match="RA_G1_DEADLINE"):
        world.m.Run(world.s, epoch_ns=world.m.time.monotonic_ns() + 10**12)


def test_safe_failure_keeps_first_static_cause_without_message_or_path(world):
    world.root.mkdir(mode=0o700)
    with world.run("collect") as run:
        first = world.m.safe_failure(
            OSError(28, "SYNTHETIC_SECRET_PRIVATE_ADDRESS /private/path"), run
        )
        assert (
            first["family"] == "OS_ERROR"
            and first["errno"] == 28
            and b"SYNTHETIC_SECRET" not in world.m.canonical(first)
        )
        assert world.m.safe_failure(RuntimeError("RA_G1_DEADLINE"), run) == first


@pytest.fixture
def orchestration(world, monkeypatch):
    import stat
    from safe_geocoding_pipeline import execution_policy
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_assurance as assurance,
        s12_ra_g1_execution as execution,
        s12_public_runtime as runtime,
        s12_ra_g1_monitor as monitor,
    )

    m = world.m
    selected = world.selected
    selected["limits"].update(assurance.SCOPE_CEILINGS[m.SCOPE])
    original = selected["limits"]["stages"][0]
    selected["limits"]["stages"] = [
        {
            **original,
            "id": i,
            "phase": i,
            "deadline_ms": 20000 if i <= 4 else 120000,
            "attempts": 10 if i <= 4 else 0,
            "events": 100 if i <= 4 else 0,
        }
        for i in range(1, 9)
    ]
    selected["limits"]["stages"][6]["deadline_ms"] = 600000
    selected["limits"]["application_counters"]["ADMIN_FILE"] = 4096
    world.s["resource_selection_sha256"] = m.digest(selected)
    env = facts()
    env["pids_max"] = assurance.unknown("UNAVAILABLE", "INACCESSIBLE")
    identity = dict(
        domain="/sys/fs/cgroup/SYNTHETIC",
        device=1,
        inode=2,
        boot_id=env["boot_id"],
        cgroup_namespace_inode=1,
        mount_namespace_inode=2,
        membership="0::/SYNTHETIC",
    )
    texts = {
        "/proc/123/cgroup": "0::/SYNTHETIC\n",
        "/proc/sys/kernel/random/boot_id": env["boot_id"] + "\n",
        "/sys/fs/cgroup/SYNTHETIC/memory.max": str(12 * 2**30) + "\n",
        "/sys/fs/cgroup/SYNTHETIC/memory.high": str(6 * 2**30) + "\n",
        "/sys/fs/cgroup/SYNTHETIC/memory.swap.max": "0\n",
    }
    raw = dict(
        visible_identity=identity,
        records={
            path: dict(
                text=text,
                identity=[1, 2, stat.S_IFREG | 0o444, 0, 0],
                acquired_mono_ns=1,
            )
            for path, text in texts.items()
        },
    )
    env.update(
        visible_identity_inventory_sha256=m.digest(identity),
        visible_membership_sha256=m.digest({"membership": identity["membership"]}),
        observation_inventory_sha256=m.digest(raw),
    )
    monkeypatch.setattr(
        execution_policy, "require_goethe_nhr_slurm", lambda reason: None
    )
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_ONLY_NOT_A_JOB")
    monkeypatch.setattr(
        assurance,
        "observe_current_facts",
        lambda *a, **kw: (deepcopy(env), deepcopy(raw)),
    )
    context = dict(
        origin="SYNTHETIC_ONLY",
        supervisor=dict(pid=12345),
        private_paths=dict(
            allocation_root=str(world.root),
            resource_evidence_root=world.s["paths"]["output"],
            scratch_root=str(world.root),
        ),
        visible_cgroup_path="/sys/fs/cgroup/SYNTHETIC",
    )
    monkeypatch.setattr(
        execution, "capture_supervisor_context", lambda **kw: deepcopy(context)
    )
    monkeypatch.setattr(
        runtime,
        "runtime_inventory",
        lambda *a, **kw: dict(origin="SYNTHETIC_ONLY", actual_backend_hashing=False),
    )
    calls = []

    class FakeAdmin:
        def __init__(self, run, role):
            self.root = world.root / (role.lower() + "_resources")
            run.mkdir(self.root)
            self.phase = execution.ADMIN_ROLES[role]
            self.binding = dict(role=role, origin="SYNTHETIC_ONLY")
            self.deadline = run.end
            put(world, self.root / "admin_binding.record", self.binding)

        def freeze_and_open(
            self, *, frozen_data_inventory_sha256, actual_opener, **kwargs
        ):
            actual_opener()
            records = {
                name: dict(origin="SYNTHETIC_ONLY", phase=self.phase)
                for name in (
                    "preopening",
                    "opener_return",
                    "monitor_terminal",
                    "worker_validation",
                )
            }
            for name, value in records.items():
                put(world, self.root / (name + ".record"), value)
            return None, records

    monkeypatch.setattr(
        m, "start_admin", lambda run, role, ctx, **kw: FakeAdmin(run, role)
    )
    monkeypatch.setattr(
        m,
        "verify_administrative_sessions",
        lambda *a, **kw: calls.append(
            "administrative-originals-verified-by-test-double"
        ),
    )
    bound = binding(selected)
    data = dict(
        origin="SYNTHETIC_ONLY_NONEXECUTABLE",
        configuration=dict(
            campaigns=[
                dict(profile=dict(sampling_runtime_bound_sha256=m.digest(bound)))
            ]
        ),
    )
    evidence = {
        "runtime_bounds": {m.digest(bound): bound},
        "selections": {m.digest(selected): selected},
    }
    role_record = dict(origin="SYNTHETIC_ONLY")
    integration = dict(origin="SYNTHETIC_ONLY")
    objects = dict(
        resource_selection=selected,
        resource_evidence=evidence,
        role_records={"synthetic": role_record},
        diagnostic_selection=role_record,
        diagnostic_resources=role_record,
        integration_review=integration,
    )

    def build(*a, **kw):
        assert kw["issued"] is True
        assert a[1]["facts"]["origin"] == "SYNTHETIC_TEST_ONLY"
        calls.append("build-fake-not-live-issuance")
        return deepcopy(data), deepcopy(objects)

    def validate(value, *a, **kw):
        assert value["origin"] == "SYNTHETIC_ONLY_NONEXECUTABLE"

    builder = NS(resource_selection=lambda *a, **kw: deepcopy(selected), build=build)
    diagnostic = NS(
        validate_envelope=validate, validate_workloads=lambda value: validate(value)
    )
    monkeypatch.setattr(
        m,
        "module",
        lambda source, name: builder if name == "stage12_prepare_ra_g1" else diagnostic,
    )
    return NS(
        **{key: value for key, value in world.__dict__.items() if key != "objects"},
        context=context,
        env=env,
        raw=raw,
        data=data,
        objects=objects,
        bound=bound,
        calls=calls,
        monitor=monitor,
        execution=execution,
    )


def collect_and_release(world):
    m = world.m
    with world.run("collect") as run:
        result = m.collect(run)
    assert result["status"] == "BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED"
    bootstrap_manifest = m.parse(
        m.read(Path(world.s["paths"]["bootstrap"]) / "manifest.record")
    )
    review = dict(
        origin="SYNTHETIC_ONLY",
        disposition="PASS",
        source_sha=G,
        bootstrap_manifest_sha256=m.digest(bootstrap_manifest),
        selection_sha256=m.digest(world.s),
    )
    put(world, world.s["paths"]["review"], review)
    release = dict(
        schema_version="stage12_ra_g1_exact_input_release_v1",
        disposition="PASS",
        selection_sha256=m.digest(world.s),
        source_sha=G,
        input_sha256=m.digest(world.data),
        review_binding_sha256=m.digest(world.objects["integration_review"]),
        bootstrap_review_sha256=m.digest(review),
        resource_selection_sha256=m.digest(world.selected),
    )
    put(world, world.s["paths"]["release"], release)
    returned = dict(
        version="stage12_ra_g1_supervisor_wait_v1",
        source_sha=G,
        selection_sha256=m.digest(world.s),
        supervisor_pid=world.context["supervisor"]["pid"],
        pid=__import__("os").getpid(),
        exit_code=0,
        wait_status=0,
        acquired_mono_ns=__import__("time").monotonic_ns(),
    )
    put(world, world.root / "collector.wait.record", returned)
    return review, release


def test_collect_bind_and_actual_opener_reopen_synthetic_originals(orchestration):
    world = orchestration
    collect_and_release(world)
    with world.run("bind") as run:
        result = world.m.bind(run)
        assert result["status"] == "EXACT_DIAGNOSTIC_RELEASED"
        assert run.predecessor_handoff_sha256 is not None and run.read_calls > 0
    assert "build-fake-not-live-issuance" in world.calls
    assert (world.root / "collector.handoff.record").exists() and (
        world.root / "binder.handoff.record"
    ).exists()


@pytest.mark.parametrize(
    "field",
    [
        "source_sha",
        "input_sha256",
        "bootstrap_review_sha256",
        "resource_selection_sha256",
    ],
)
def test_mismatched_exact_release_keeps_binding_attempt_and_never_handoff(
    orchestration, field
):
    world = orchestration
    _, release = collect_and_release(world)
    release[field] = "3" * (40 if field == "source_sha" else 64)
    put(world, world.s["paths"]["release"], release)
    with world.run("bind") as run:
        with pytest.raises(RuntimeError, match="RA_G1_EXACT_INPUT_REVIEW_REQUIRED"):
            world.m.bind(run)
    assert Path(world.s["paths"]["binding"]).exists()
    assert not (world.root / "binder.handoff.record").exists()


def test_bootstrap_manifest_cannot_bind_different_returned_original(orchestration):
    world = orchestration
    collect_and_release(world)
    path = Path(world.s["paths"]["bootstrap"]) / "bootstrap.record"
    value = world.m.parse(world.m.read(path))
    value["source_sha"] = "3" * 40
    put(world, path, value)
    with world.run("bind") as run:
        with pytest.raises(RuntimeError, match="RA_G1_BOOTSTRAP_BINDING"):
            world.m.bind(run)


def test_handoff_success_suffix_matches_actual_counter_prefix(world):
    world.root.mkdir(mode=0o700)
    context = dict(origin="SYNTHETIC_ONLY", supervisor=dict(pid=12345))
    with world.run("collect") as run:
        world.m.write_handoff(run, context)
        # The genuine CLI executes this one final successful check before rc=0.
        run.check()
        raw = world.m.read(world.root / "collector.handoff.record")
        value = world.m.parse(raw)
        assert world.m.handoff_counters(value, len(raw)) == run.counter_prefix()


def bind_and_wait(world):
    import os
    import time

    collect_and_release(world)
    with world.run("bind") as run:
        world.m.bind(run)
    returned = dict(
        version="stage12_ra_g1_supervisor_wait_v1",
        source_sha=G,
        selection_sha256=world.m.digest(world.s),
        supervisor_pid=world.context["supervisor"]["pid"],
        pid=os.getpid(),
        exit_code=0,
        wait_status=0,
        acquired_mono_ns=time.monotonic_ns(),
    )
    put(world, world.root / "binder.wait.record", returned)
    return returned


def test_handoff_is_deferred_original_checked_and_never_resets_bootstrap(
    orchestration, monkeypatch
):
    world = orchestration
    bind_and_wait(world)
    with world.run("verify") as run:
        run.read_charge(3, 7)
        before = (run.read_calls, run.read_bytes, run.checks)
        original, returned = world.m.adopt_handoff(run, world.context, stage="bind")
        assert (
            run.read_calls > before[0]
            and run.read_bytes > before[1]
            and run.checks > before[2]
        )
        got = world.m.load_verified_handoff(
            world.context,
            world.selected,
            check=run.check,
            read_charge=run.read_charge,
            deadline_ns=run.end,
            write_record=run.write,
            counter_digest=lambda: world.m.digest(run.counter_prefix()),
        )
        assert got["initial_usage"]["invocations"]["EXCLUSIVE_FILE"] == 0
        assert got["source_counter_prefix"]["source_read_calls"] > 0
        assert got["original"] == original
        before = len(world.calls)
        got["verify_before_data"]()
        assert len(world.calls) == before + 1
        with pytest.raises(RuntimeError, match="RA_G1_HANDOFF"):
            got["verify_before_data"]()
        bad = deepcopy(returned)
        bad["exit_code"] = 1
        put(world, world.root / "binder.wait.record", bad)
        with pytest.raises(RuntimeError, match="RA_G1_CHILD_FAILED"):
            world.m.load_verified_handoff(
                world.context,
                world.selected,
                check=run.check,
                read_charge=run.read_charge,
                deadline_ns=run.end,
            )


def test_complete_verifier_fresh_callbacks_and_tail_counter_originals(
    orchestration, monkeypatch
):
    import time

    world = orchestration
    m = world.m
    returned = bind_and_wait(world)
    put(world, world.s["paths"]["worker_return"], returned)
    output = Path(world.s["paths"]["output"])
    output.mkdir(mode=0o700)
    binder = m.parse(m.read(world.root / "binder.handoff.record"))
    carried = m.handoff_counters(
        binder, len(m.read(world.root / "binder.handoff.record"))
    )
    counters = {key: 0 for key in world.monitor.COUNTERS}
    counters.update(
        source_read_calls=carried["source_read_calls"] + 100,
        source_read_bytes=carried["source_read_bytes"] + 1000,
        identity_checks=carried["checks"] + 100,
    )
    sessions = []
    now = time.monotonic_ns()
    for phase in range(1, 6):
        label = "synthetic" + str(phase)
        root = output / (label + "_resources")
        root.mkdir(mode=0o700)
        sessions.append(
            dict(
                label=label,
                root=str(root),
                phase_id=phase,
                phase_start_ns=now - 1000000,
                phase_deadline_ns=now + 1000000000,
            )
        )
        originals = dict(
            preopening=dict(origin="SYNTHETIC_ONLY"),
            opener_return=dict(actual_opener_return_ns=now),
            monitor_terminal=dict(
                coverage_start_ns=now - 500000,
                final_observation_ns=now,
                last_ack_ns=now,
            ),
            worker_validation=dict(first_pass_end_ns=now),
        )
        for name, value in originals.items():
            put(world, root / (name + ".record"), value)
    summary = dict(
        complete=True,
        attempts=106,
        resource_sessions=sessions,
        resource_counters=counters,
        origin="SYNTHETIC_ONLY",
    )
    put(world, output / "summary.json", summary)
    monkeypatch.setattr(
        world.execution, "validate_current_supervisor", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        world.monitor, "reopen_phase_protocol", lambda **kw: NS(origin="SYNTHETIC_ONLY")
    )
    observed = []

    def admin(*args, **kw):
        kw["read_charge"](1, 19)
        assert kw["terminal_name"] == "final_verification.record"
        return [dict(origin="SYNTHETIC_ONLY", role=row["role"]) for row in args[2]]

    monkeypatch.setattr(m, "verify_administrative_sessions", admin)

    def tail(**kw):
        kw["charge_read"](1, 23)
        identity = kw["current_counter_sha256"]()
        observed.append(identity)
        return kw["persist_terminal"](
            dict(origin="SYNTHETIC_ONLY", counter_sha256=identity), lambda: None
        )

    monkeypatch.setattr(world.monitor, "verify_tail", tail)
    with world.run("verify") as run:
        run.started = now - 10**9  # Explicit synthetic inherited shell epoch.
        result = m.verify(run)
        assert run.read_calls > counters["source_read_calls"]
        assert len(result["resource_terminal_records"]) == 5
        assert len(result["administrative_terminal_records"]) == 3
        assert set(observed) <= set(result["counter_originals"])
        snapshots = [
            result["counter_originals"][identity]["verifier_prefix"][
                "source_read_calls"
            ]
            for identity in observed
        ]
        assert snapshots == sorted(set(snapshots))
        assert result == m.parse(m.read(world.s["paths"]["tail"]))


def test_exact_path_policy_denies_provider_secrets_raw_and_source_mutation(world):
    m = world.m
    assert m.allocation_path_policy(world.s, world.source / "synthetic_only.py")
    assert not m.allocation_path_policy(
        world.s, world.source / "synthetic_only.py", write=True
    )
    assert not m.allocation_path_policy(world.s, world.source / "raw_source.csv")
    assert not m.allocation_path_policy(world.s, world.root / ".env")
    assert not m.allocation_path_policy(world.s, Path.home() / ".ssh" / "id_ed25519")
    assert not m.allocation_path_policy(
        world.s, world.root / "collector.wait.record", write=True
    )
    assert m.allocation_path_policy(world.s, world.root / "collector.wait.record")


def test_administrative_monitor_partition_charged_before_creation(world):
    world.root.mkdir(mode=0o700)
    with world.run("collect") as run:
        run.selected_resource = world.selected
        run.administrative_partition = dict(
            bytes_start=0,
            creations_start=0,
            logical_write_bytes=1024,
            application_creations=1,
        )
        run.monitor_charge(1024, 1)
        with pytest.raises(RuntimeError, match="RA_G1_COUNTER_LIMIT"):
            run.monitor_charge(1, 1)
        assert (
            run.monitor_usage["bytes"] == 1025 and run.monitor_usage["creations"] == 2
        )


def test_installed_denial_callback_explicit_linux_simulation(world, monkeypatch):
    """Exercise installed callbacks only; this never earns a Linux native guard."""
    import os
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport

    m = world.m
    original_open = os.open
    membership = world.records / "synthetic-cgroup-original"
    membership.write_bytes(b"0::/SYNTHETIC\n")
    membership.chmod(0o600)

    def substitute(path, flags, *a, **kw):
        if str(path) == f"/proc/{os.getpid()}/cgroup":
            return original_open(membership, flags, *a, **kw)
        return original_open(path, flags, *a, **kw)

    monkeypatch.setattr(m.os, "open", substitute)
    monkeypatch.setattr(m.sys, "dont_write_bytecode", False)
    for name in ("runtime", "private_file"):
        monkeypatch.setattr(
            s12_transport.Secret, name, s12_transport.Secret.__dict__[name]
        )

    def denied(*a, **kw):
        raise PermissionError("SYNTHETIC_ONLY_DENIED")

    guard = NS()

    def install(*args):
        assert callable(guard.open_allowed)
        return (
            NS(origin="SYNTHETIC_ONLY_NO_SECCOMP"),
            "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT",
            [0],
            [None],
            lambda n: None,
            denied,
        )

    guard.install_denials = install
    monkeypatch.setattr(m, "module", lambda *a: guard)
    charged = []
    m.install_denials(
        world.s, read_charge=lambda calls, size: charged.append((calls, size))
    )

    def allows(path, write=False, self_proc=None):
        return guard.open_allowed(
            path,
            write=write,
            source=world.source,
            output=world.root,
            input_path=world.root / "input.record",
            evidence=world.records,
            self_proc=self_proc,
        )

    assert allows(world.source / "synthetic_only.py")
    assert not allows(world.source / "raw.csv") and not allows(
        world.records / "undeclared.record"
    )
    assert allows("/sys/fs/cgroup/SYNTHETIC/memory.max")
    assert not allows("/sys/fs/cgroup/other/memory.max") and not allows(
        "/sys/fs/cgroup/SYNTHETIC/memory.max", True
    )
    assert not allows("/proc/999999/status")
    assert any(calls for calls, size in charged) and any(
        size for calls, size in charged
    )
    with pytest.raises(PermissionError, match="SYNTHETIC_ONLY_DENIED"):
        s12_transport.Secret.runtime()


def test_administrative_entry_uses_closed_stage_creation_key(world, monkeypatch):
    """Real controller builder, synthetic kernel/monitor only: no live authority."""
    import os
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_execution as execution,
    )

    world.root.mkdir(mode=0o700)
    selected = deepcopy(world.selected)
    selected["limits"]["stages"].append(
        {
            **selected["limits"]["stages"][0],
            "id": 6,
            "phase": 6,
            "attempts": 0,
            "events": 0,
            "creations": 7,
        }
    )
    monkeypatch.setattr(world.m, "resource_selection", lambda run: selected)
    monkeypatch.setattr(
        execution,
        "_process_identity",
        lambda pid, **kw: (
            dict(pid=pid, start_ticks=123, uid=os.getuid()),
            os.getppid(),
        ),
    )
    captured = []

    def synthetic_monitor(**kw):
        captured.append(kw)
        kw["directory_charge"](0, 1)
        root = Path(kw["evidence_root"])
        root.mkdir(mode=0o700)
        return NS(root=root, binding=kw["binding"], phase=kw["binding"]["phase_id"])

    monkeypatch.setattr(execution, "start_administrative_session", synthetic_monitor)
    context = dict(
        supervisor=dict(pid=os.getppid()),
        visible_cgroup_path="/sys/fs/cgroup/SYNTHETIC",
    )
    with world.run("collect") as run:
        run.selected_resource = selected
        world.m.start_admin(
            run, "COLLECTOR", context, scope_start_ns=world.m.time.monotonic_ns()
        )
        assert run.administrative_partition["application_creations"] == 7
        assert captured[0]["binding"]["ap_dispatch_authority"] == "DENIED"
        assert (world.root / "collector_resources" / "admin_binding.record").exists()

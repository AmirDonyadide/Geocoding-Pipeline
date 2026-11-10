"""Current cadence/ACK repair with real readers and private kernel fixtures.

These are local synthetic controls, never Linux enforcement or B qualification.
"""

from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
import sysconfig
import threading
import time
from types import SimpleNamespace

import pytest

from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_ra_g1_native_root_sessions import KernelSession
from test_stage12_ra_g1_rep_admin_budget import selected as current_selection
from test_stage12_ra_g1_integration import (
    H as AUTHORITY_H, KEY, RealClock, SyntheticAuthority, Validation, ra_inputs,
)
from test_s12_ra_g1_core import H, selection
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

REPO = Path(__file__).resolve().parents[1]
HOST = sys.platform
sysconfig.get_config_vars()  # Preserve the host ABI before the proc fixture.


def script(name):
    spec = importlib.util.spec_from_file_location(
        "cadence_" + name, REPO / "scripts" / (name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def resources(tmp_path, monkeypatch):
    active = []

    def start(*, enabled=True, observe_delay=0, ack_delay=0, trigger=None,
              before_codec=None, selected=None):
        root = tmp_path / str(len(active))
        root.mkdir(mode=0o700)
        env = {key: os.environ.get(key) for key in ("SAFE_EXECUTION_SITE", "SLURM_JOB_ID")}
        kernel = KernelSession(root, monkeypatch)
        monkeypatch.setattr(sys, "platform", HOST)
        for key, value in env.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        evidence = kernel.output / "resource"
        evidence.mkdir(mode=0o700)
        originals = evidence / "originals"
        originals.mkdir(mode=0o700)
        limit = time.monotonic_ns() + 15_000_000_000
        foreground = threading.get_ident()
        checks = [0]

        def check():
            if threading.get_ident() == foreground:
                checks[0] += 1
            c.require(time.monotonic_ns() < limit, "RA_G1_DEADLINE")

        writer = m.ObservationWriter(
            evidence / "observations.bin", maximum_rows=30,
            charge=lambda n, k: None, check=check, original_root=originals,
            charge_read=lambda n, k: None,
        )
        pids = (kernel.worker, kernel.supervisor)
        observer = m.LinuxObserver(
            pids=pids, cgroup_path=kernel.domain, root=kernel.output,
            native_paths=(kernel.native,), native_roots=(kernel.output,),
            counter_provider=lambda: dict.fromkeys(m.COUNTERS, 0),
            retain_originals=lambda value: writer.stage_original(m.export_original_observation(value)),
            admitted_process_provider=lambda: pids, read_charge=lambda n, k: None,
            check=check,
        )
        owners, maximum, calls = [0], [0], []

        def observe(kind):
            owners[0] += 1
            maximum[0] = max(maximum[0], owners[0])
            try:
                if kind == "PERIODIC" and (trigger is None or trigger.is_set()):
                    time.sleep(observe_delay)
                return observer(kind)
            finally:
                calls.append(kind)
                owners[0] -= 1

        def prewrite(size, creates):
            if writer.current_seq >= 2 and size == m.CODEC_BYTES and creates == 0:
                if before_codec is not None:
                    before_codec()
                time.sleep(ack_delay)

        writer.prewrite = prewrite
        chosen = current_selection() if selected is None else selected
        monitor = m.ResourceMonitor(
            observer=observe, writer=writer, selected=chosen,
            binding_sha256=H, phase_id=1, seed_sha256=H,
            deadline_ns=limit, check=check, start_to_start=enabled,
        )
        value = SimpleNamespace(monitor=monitor, writer=writer, selected=chosen,
                                kernel=kernel, checks=checks, maximum=maximum, calls=calls)
        active.append(value)
        monitor.start()
        assert type(observer) is m.LinuxObserver and writer.acked >= 1
        return value

    yield start
    for value in active:
        value.monitor.stop_event.set()
        value.monitor.thread.join(3)
        with value.writer.condition:
            value.writer.closing = True
            value.writer.condition.notify_all()
        value.writer.thread.join(3)
        assert not value.monitor.thread.is_alive()
        assert not value.writer.thread.is_alive()


def reopen(value, opener):
    monitor, writer = value.monitor, value.writer
    rows = list(m.read_observations(writer.path, maximum_rows=30,
                                   check=lambda: None, charge_read=lambda n, k: None))
    coverage = m.Coverage(binding_sha256=H, selection_sha256=m.old.digest(value.selected),
                          phase_id=1, seed_sha256=H, selected=value.selected,
                          scope_start_ns=monitor.scope_start)
    for row in rows:
        raw = m.read_original_observation(
            writer.original_root / (row["visible_identity_inventory_sha256"] + ".record"),
            expected_sha256=row["visible_identity_inventory_sha256"],
            check=lambda: None, charge_read=lambda n, k: None,
        )
        m.validate_original_observation(raw, observation=row)
        coverage.add(row)
    coverage.require_complete(opener_return_ns=opener, last_ack_ns=writer.ack_ns)
    assert rows[-1]["kind"] == "FINAL"
    return rows


def test_actual_919ms_acquire_ack_continuous_foreground_and_final_reopen(resources):
    value = resources(observe_delay=.620, ack_delay=.299)
    until = time.monotonic() + 2.6
    waited = False
    while time.monotonic() < until:
        checks = value.checks[0]
        entered = time.monotonic_ns()
        row = value.monitor.barrier()
        waited |= time.monotonic_ns() - entered > 50_000_000
        assert value.checks[0] == checks + 1
        assert value.writer.acked >= row["seq"]
        assert time.monotonic_ns() - row["enter_mono_ns"] <= m.MAX_GAP_NS
        time.sleep(.01)
    opener = time.monotonic_ns()
    value.monitor.finish(opener_return_ns=opener)
    rows = reopen(value, opener)
    assert waited and value.maximum[0] == 1
    assert all(b["enter_mono_ns"] - a["enter_mono_ns"] <= m.MAX_GAP_NS
               for a, b in zip(rows, rows[1:]))


def test_start_anchor_skips_elapsed_time_without_catchup(resources):
    value = resources(observe_delay=.650)
    until = time.monotonic() + 2.1
    while value.monitor.seq < 3 and time.monotonic() < until:
        time.sleep(.01)
    assert value.monitor.failure is None and value.monitor.seq >= 3
    opener = time.monotonic_ns()
    value.monitor.finish(opener_return_ns=opener)
    rows = reopen(value, opener)
    enters = [row["enter_mono_ns"] for row in rows if row["kind"] != "FINAL"]
    assert all(m.PERIOD_NS <= b - a <= m.MAX_GAP_NS for a, b in zip(enters, enters[1:]))
    assert value.maximum[0] == 1


def test_fast_poll_spacing_is_at_least_selected_period(resources):
    value = resources()
    until = time.monotonic() + 2
    while value.monitor.seq < 3 and time.monotonic() < until:
        time.sleep(.005)
    assert value.monitor.seq >= 3 and value.monitor.failure is None
    opener = time.monotonic_ns()
    value.monitor.finish(opener_return_ns=opener)
    rows = reopen(value, opener)
    periodic = [row for row in rows if row["kind"] != "FINAL"]
    assert all(b["enter_mono_ns"] - a["enter_mono_ns"] >= m.PERIOD_NS
               for a, b in zip(periodic, periodic[1:]))


def test_real_public_constructor_has_cadence_and_durable_start_without_prefix(tmp_path, monkeypatch):
    kernel = KernelSession(tmp_path, monkeypatch)
    arguments = kernel.arguments("PUBLIC_SYNTHETIC_ONLY", native_roots=(kernel.output,))
    value = e.start_session(**arguments, start_to_start=True)
    try:
        receipt = value.require_start_acknowledged()
        assert type(value.observer) is m.LinuxObserver
        assert value.monitor.start_to_start is True
        assert value.bootstrap_prefix is None
        assert receipt["row"]["kind"] == "START"
        assert receipt["ack_ns"] >= receipt["row"]["exit_mono_ns"]
        assert value.writer.acked >= 1 and value.writer.path.stat().st_size >= 1024
    finally:
        value.abort()
        value.monitor.stop_event.set()
        value.monitor.thread.join(1)
        with value.writer.condition:
            value.writer.closing = True
            value.writer.condition.notify_all()
        value.writer.thread.join(1)
        assert not value.monitor.thread.is_alive()
        assert not value.writer.thread.is_alive()


def test_cold_stale_inclusive_boundary_and_original_deadline(resources):
    value = resources()
    monitor = value.monitor
    monitor.stop_event.set()
    monitor.thread.join(2)
    enter = monitor.last["enter_mono_ns"]
    monitor.clock = lambda: enter + m.MAX_GAP_NS
    assert monitor.barrier()["seq"] == 1
    monitor.clock = lambda: enter + m.MAX_GAP_NS + 1
    with pytest.raises(c.Stage12Error, match="RA_G1_MONITOR_GAP"):
        monitor.barrier()
    assert monitor.failure == "RA_G1_MONITOR_GAP"


def test_inflight_ack_age_or_invalid_coverage_never_refreshes_old_row(resources):
    value = resources(observe_delay=.050, ack_delay=1.050)
    while time.monotonic_ns() - value.monitor.last["enter_mono_ns"] <= 1_010_000_000:
        time.sleep(.005)
    with pytest.raises(c.Stage12Error, match="RA_G1_MONITOR_GAP"):
        value.monitor.barrier()
    assert value.monitor.last["seq"] == 1
    assert value.writer.acked < value.writer.rows


def test_writer_failure_wakes_waiter_and_preserves_actual_primary(resources):
    release = threading.Event()

    def fail():
        assert release.wait(3)
        raise OSError(28, "SYNTHETIC_UNSAFE_TEXT")

    value = resources(observe_delay=.050, before_codec=fail)
    while time.monotonic_ns() - value.monitor.last["enter_mono_ns"] <= 1_010_000_000:
        time.sleep(.005)
    timer = threading.Timer(.05, release.set)
    timer.start()
    try:
        with pytest.raises(c.Stage12Error, match="RA_G1_WRITE_UNCERTAIN"):
            value.monitor.barrier()
    finally:
        release.set()
        timer.join(1)
    state = value.monitor.diagnostic_snapshot()
    assert state["first_primary"]["source"] == "WRITER"
    assert state["first_primary"]["errno"] == 28
    assert "SYNTHETIC_UNSAFE_TEXT" not in repr(state)


def test_original_deadline_cannot_be_reset_by_inflight_wait(resources):
    value = resources(observe_delay=.050, ack_delay=.5)
    value.monitor.deadline = time.monotonic_ns() - 1
    with pytest.raises(c.Stage12Error, match="RA_G1_DEADLINE"):
        value.monitor.barrier()


def test_actual_held1817_ack_admission_propagates_latched_resource_failure(resources, tmp_path):
    profile, plan, start, record, selected, rows, inventory = ra_inputs()
    held = threading.Event()
    value = resources(observe_delay=1.10, trigger=held, selected=selected)
    clock = RealClock()
    authority = SyntheticAuthority(profile, plan, start, record, selected, rows, clock)
    authority.resource_monitor = value.monitor
    admitted = authority.resource_prewrite
    authority.resource_prewrite = lambda **kwargs: (admitted(**kwargs), value.monitor.barrier(**kwargs))
    checks, after, latched, dispatched = [0], [0], [None], []

    def check():
        held.set()
        checks[0] += 1
        if value.monitor.failure is not None:
            after[0] += 1
            latched[0] = latched[0] or time.monotonic_ns()
        assert checks[0] < 2000  # Independent bounded test stop, not a new phase limit.

    diagnostic = script("stage12_ra_g1_diagnostic")
    report = None
    with diagnostic.instrumentation(check) as state:
        state["target"] = 1817
        try:
            report = cli.run_operations_block(
                profile, plan, start, work_factory=lambda: iter(rows), output=tmp_path / "campaign",
                block_id=1, authority=authority, clock=clock, dispatch=lambda *args: dispatched.append(args),
                runtime_inventory=inventory, runtime_key=KEY, control_adapters={}, monitor=None,
                free_bytes=lambda: 2**40, segment_authority=AUTHORITY_H,
                writer_exclusion_evidence=AUTHORITY_H, epoch="1"*64, writer_release_evidence=AUTHORITY_H,
                public_validation=Validation(), task_deadline_ns=clock.now_ns()+180*10**9,
            )
        except (c.Stage12Error, RuntimeError) as error:
            assert error.args == ("RA_G1_MONITOR_GAP",)
    assert not dispatched and (report is None or not report["report_complete"])
    assert value.monitor.failure == "RA_G1_MONITOR_GAP"
    assert state["target"] == 1817 and state["regular"] < 1817
    assert after[0] <= 4 and latched[0] is not None


def test_exact_current_family_mode_and_public_admitted_origin():
    assert e.resource_cadence_mode(current_selection()) is True
    legacy = selection("REPRESENTATIVE_NO_SERVICE")
    assert e.resource_cadence_mode(legacy) is False
    public = selection("PUBLIC_SYNTHETIC_ONLY")
    assert e.resource_cadence_mode(public) is False
    assert e.resource_cadence_mode(public, True) is True
    protected = selection("DEVELOPMENT_ONLY")
    assert e.resource_cadence_mode(protected) is False
    with pytest.raises(c.Stage12Error):
        e.resource_cadence_mode(protected, True)
    workflow = script("stage12_ra_g1_public_workflow")
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
    current = dict(version=workflow.SHARED_LEASE_VERSION, accounting_inventory=dict(
        schema_version=accounting.SHARED_LEASE_VERSION, bootstrap_proof_record_count=0))
    assert workflow.current_resource_cadence(current) is True
    for key, bad in (("version", workflow.VERSION),):
        changed = deepcopy(current)
        changed[key] = bad
        assert workflow.current_resource_cadence(changed) is False
    changed = deepcopy(current)
    changed["accounting_inventory"]["bootstrap_proof_record_count"] = 3
    assert workflow.current_resource_cadence(changed) is False


@pytest.mark.parametrize("setup_mode,requested", [(True, False), (False, True)])
def test_public_setup_and_runtime_reject_both_mode_mismatches(monkeypatch, tmp_path, setup_mode, requested):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime

    # A metadata-only unverified session prototype reaches this early guard;
    # the lower execution-site fixture confers no native/job authority.
    monkeypatch.setattr(runtime, "require_goethe_nhr_slurm", lambda *args: None)
    session = e.AdministrativePhaseSession.__new__(e.AdministrativePhaseSession)
    session.binding = dict(role="PUBLIC_SETUP", scope="PUBLIC_SYNTHETIC_ONLY",
                           source_git_sha="2"*40, process_pid=os.getpid())
    session.completed = False
    session.protocol = SimpleNamespace(state="RUNNING")
    session.monitor = SimpleNamespace(start_to_start=setup_mode)
    with pytest.raises(c.Stage12Error, match="RA_G1_SELECTION_BINDING"):
        runtime.execute(dict(version=runtime.RA_CONFIG), bundle=None, review=None,
                        review_hash=H, repository=tmp_path, git_sha="2"*40,
                        setup_session=session, setup_opener=lambda: None,
                        resource_start_to_start=requested)


def test_public_legacy_setup_stub_without_mode_keeps_false_default(monkeypatch, tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime

    monkeypatch.setattr(runtime, "require_goethe_nhr_slurm", lambda *args: None)
    session = e.AdministrativePhaseSession.__new__(e.AdministrativePhaseSession)
    session.binding = dict(role="PUBLIC_SETUP", scope="PUBLIC_SYNTHETIC_ONLY",
                           source_git_sha="2"*40, process_pid=os.getpid())
    session.completed = False
    session.protocol = SimpleNamespace(state="RUNNING")
    session.monitor = SimpleNamespace()
    # The unchanged next gate rejects missing real ledger/handoff. The mode
    # guard itself accepts the historical false default without new fields.
    with pytest.raises(c.Stage12Error, match="RA_G1_HANDOFF"):
        runtime.execute(dict(version=runtime.RA_CONFIG), bundle=None, review=None,
                        review_hash=H, repository=tmp_path, git_sha="2"*40,
                        setup_session=session, setup_opener=lambda: None)

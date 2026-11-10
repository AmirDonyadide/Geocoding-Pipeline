"""Scoped RA-G1 author verification: synthetic records, no live authority."""

from copy import deepcopy
from types import SimpleNamespace
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as strict
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_scratch as scratch
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as timing
from test_stage12_wf_ap2_assurance import m2_inputs

H, G = "1" * 64, "2" * 40
FROM, UNTIL = "2026-01-01T00:00:00.000000Z", "2026-01-02T00:00:00.000000Z"


def selection(scope="PUBLIC_SYNTHETIC_ONLY"):
    limits = {
        key: 1
        for key in a.LIMITS
        if key not in ("python_roles", "stages", "application_counters")
    }
    limits.update(
        processing_ms=20000,
        scheduler_s=21,
        processes=4,
        threads=256,
        utilities=256,
        python_invocations=5,
        attempts=10,
        native_invocations=0
        if scope in ("REPRESENTATIVE_NO_SERVICE", "PUBLIC_SYNTHETIC_ONLY")
        else 1,
        logical_write_bytes=2**30,
        creations=10000,
        monitor_rows=100,
        monitor_bytes=102400,
        monitor_creations=5,
        closure_reserve_bytes=256 * 2**20,
        closure_reserve_creations=4096,
        telemetry_chunks=2980 if scope == "PUBLIC_SYNTHETIC_ONLY" else 1500,
    )
    monitor_scopes = (
        9
        if scope == "REPRESENTATIVE_NO_SERVICE"
        else (14 if scope == "PUBLIC_SYNTHETIC_ONLY" else 3)
    )
    limits["telemetry_bytes"] = 2 * limits["telemetry_chunks"] * 32768
    limits["telemetry_creations"] = limits["telemetry_chunks"] + 1
    limits["monitor_bytes"] = 16384 * limits["monitor_rows"] + 8192 * (
        4 * monitor_scopes + 16
    )
    limits["monitor_creations"] = 2 * limits["monitor_rows"] + 4 * monitor_scopes + 16
    if scope == "DEVELOPMENT_LOCAL_PREPARATION":
        limits["attempts"] = 0
    limits["python_roles"] = [{"role": role, "maximum": 1} for role in a.ROLES]
    limits["stages"] = [
        dict(
            id=1,
            phase=1,
            deadline_ms=20000,
            reserve_ms=1,
            attempts=0 if scope == "DEVELOPMENT_LOCAL_PREPARATION" else 10,
            events=100,
            logical_write_bytes=2**30,
            creations=100,
            source_read_calls=100,
            source_read_bytes=100000,
            check_calls=100,
        )
    ]
    limits["application_counters"] = {role: 10 for role in m.ROLES}
    return dict(
        schema_version=a.SELECTION,
        scope=scope,
        policy_sha256=H,
        adoption_sha256=H,
        source_git_sha=G,
        descriptor_inventory_sha256=H,
        workload_graph_sha256=H,
        limits=limits,
        monitor=dict(
            period_ms=500,
            max_observed_interval_ms=1000,
            self_rss_stop_bytes=768 * 2**20,
            aggregate_rss_stop_bytes=768 * 2**20
            if scope == "REPRESENTATIVE_NO_SERVICE"
            else 5 * 2**30,
            visible_threads_stop=256,
            native_visible_file_stop_bytes=8589934592,
            shared_free_margin_bytes=1342177280,
            free_inode_margin=4096,
            scope="SELF_AND_REGISTERED_VISIBLE",
            required_observation_set_sha256=H,
        ),
        authority_requirement_inventory_sha256=H,
        paths_sha256=H,
        valid_from=FROM,
        valid_until=UNTIL,
        review_sha256=H,
    )


def facts():
    result = dict(
        schema_version=a.CURRENT,
        origin="SYNTHETIC_TEST_ONLY",
        observation_inventory_sha256=H,
        visible_identity_inventory_sha256=H,
        boot_id="1" * 32,
        cgroup_namespace_inode=1,
        mount_namespace_inode=2,
        visible_membership_sha256=H,
        ancestor_coverage="NOT_ESTABLISHED",
        descendant_coverage="NOT_ESTABLISHED",
        native_maximum="NOT_PROVEN",
        physical_capacity="NOT_RESERVED_OR_PROVEN",
    )
    result.update(
        {
            key: a.known(value, "KERNEL", "VISIBLE_CGROUP", 1)
            for key, value in (
                ("memory_max_bytes", 12 * 2**30),
                ("memory_high_bytes", 6 * 2**30),
                ("swap_max_bytes", 0),
            )
        }
    )
    result["pids_max"] = a.unknown("UNAVAILABLE", "NOT_EXPOSED")
    return result


def capacity(selected):
    return dict(
        schema_version=a.CAPACITY,
        scope=selected["scope"],
        selection_sha256=contract.digest(selected),
        owner_reported_approval_sha256=H,
        observed_utc=FROM,
        root_identity_inventory_sha256=H,
        filesystem_originals_sha256=H,
        accounting_method_sha256=H,
        bavail_bytes=a.known(2**40, "FILESYSTEM", "FILESYSTEM_SHARED", 1),
        favail=a.known(100000, "FILESYSTEM", "FILESYSTEM_SHARED", 1),
        physical_accounting_coverage="UNKNOWN_NATIVE_OR_DELETED_OPEN",
        assurance="BEST_EFFORT_SHARED_SNAPSHOT",
        entitlement="NOT_ASSERTED",
        reservation="NONE",
        restrictions_inventory_sha256=H,
    )


def binding(selected):
    result = {key: H for key, spec in a.SCHEMA.items() if spec == "D"}
    values = [65536, 8 * 2**20, 4096 * 512, sum(scratch.RA_G1_CAPS.values()), 32768, 16384, a.MIN_OTHER_LOGICAL]
    result.update(
        schema_version=a.BOUND,
        scope=selected["scope"],
        method=a.METHOD,
        source_git_sha=G,
        selection_sha256=contract.digest(selected),
        initial_environment_observation_sha256=contract.digest(facts()),
        maximum_identity_checks=100,
        maximum_original_read_calls=100000,
        maximum_original_read_bytes=2**30,
        logical_allocations=[
            dict(name=name, bytes=value, evidence_sha256=H)
            for name, value in zip(a.ARENAS, values, strict=True)
        ],
        total_logical_bytes=sum(values),
        logical_scratch_bytes=sum(scratch.RA_G1_CAPS.values()),
        valid_from=FROM,
        valid_until=UNTIL,
        native_component_guarantee="NOT_CLAIMED",
        job_domain_guarantee="NOT_ESTABLISHED",
        physical_capacity_guarantee="NOT_RESERVED_OR_PROVEN",
    )
    return result


def observation(selected, *, seq=1, enter=100, exit_ns=None, kind="START", previous=H):
    exit_ns = enter if exit_ns is None else exit_ns
    meanings = {
        "self_rss_peak_bytes": ("PROCESS", "SELF", 300 * 1024),
        "registered_visible_rss_bytes": ("PROCESS", "REGISTERED_VISIBLE", 200 * 1024),
        "visible_native_threads": ("PROCESS", "REGISTERED_VISIBLE", 2),
        "visible_processes": ("PROCESS", "REGISTERED_VISIBLE", 1),
        "shared_bavail_bytes": ("FILESYSTEM", "FILESYSTEM_SHARED", 2**40),
        "shared_favail": ("FILESYSTEM", "FILESYSTEM_SHARED", 100000),
        "visible_native_file_bytes": ("FILESYSTEM", "REGISTERED_VISIBLE", 0),
    }
    readings = {
        key: a.known(value, origin, scope, enter)
        for key, (origin, scope, value) in meanings.items()
    }
    native = dict(
        registered_paths_checked=0,
        visible_linked_files=0,
        discovered_names=0,
        maximum_discovered_names=64,
        discovery_status="COMPLETE_KNOWN_NAMESPACE",
        visible_allocated_bytes=readings["visible_native_file_bytes"],
        unknown_native_file_count="NOT_PROVEN",
        deleted_open_bytes="NOT_MEASURED",
    )
    return dict(
        schema_version=m.OBSERVATION,
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        seq=seq,
        previous_sha256=previous,
        kind=kind,
        enter_mono_ns=enter,
        exit_mono_ns=exit_ns,
        readings=readings,
        counters={key: 0 for key in m.COUNTERS},
        native_visibility=native,
        visible_identity_inventory_sha256=H,
    )


def original_observation(row):
    import stat

    pid, at = 123, row["enter_mono_ns"]
    kernel = []
    texts = {
        "PID_CGROUP": "0::/selected\n",
        "PID_STATUS": "Pid:\t123\nUid:\t42 42 42 42\nVmRSS:\t200 kB\nVmHWM:\t300 kB\nThreads:\t2\n",
        "PID_STAT": "123 (python) S " + "0 " * 18 + "1\n",
    }
    for source, text in texts.items():
        kernel.append(
            dict(
                source=source,
                pid=pid,
                text=text,
                acquired_mono_ns=at,
                identity=[1, 2, stat.S_IFREG | 0o444, 42, 42],
            )
        )
    return dict(
        schema_version=m.ORIGINAL_OBSERVATION,
        origin="SYNTHETIC_TEST_ONLY",
        kernel_records=kernel,
        self_pid=pid,
        cgroup_visible_members="UNAVAILABLE",
        filesystem=dict(
            f_frsize=4096,
            f_bavail=2**28,
            f_favail=100000,
            f_blocks=2**29,
            f_files=200000,
        ),
        native=[],
        registered_process_start_ticks=[[123, 1]],
        proc_records=3,
        read_calls=6,
        read_bytes=sum(len(text) for text in texts.values()),
        counters=deepcopy(row["counters"]),
    )


class Authority:
    test_only = True
    configuration_scope_sha256 = H
    clock = SimpleNamespace(utc=lambda: FROM)

    def __init__(self, selected):
        self.selected, self.original, self.current = selected, facts(), facts()
        self.charges, self.grants = 0, []

    def charge_identity_check(self, record):
        self.charges += 1

    def resource_facts(self, record):
        return deepcopy(self.current)

    def initial_resource_facts(self, record):
        return deepcopy(self.original)

    def resource_selection(self, record):
        return self.selected

    def capacity_observation(self, record):
        return capacity(self.selected)

    def require(self, role, digest, context):
        assert digest != "0" * 64
        self.grants.append(role)


def test_ra01_successors_are_distinct_and_old_strict_fixture_still_accepts():
    profile, plan, start, record, _ = m2_inputs()
    strict.validate_bound(record, profile, start)
    assert contract.PROFILE != strict.PROFILE
    with pytest.raises(c.Stage12Error):
        contract.validate(profile, contract.PROFILE)
    with pytest.raises(c.Stage12Error):
        a.shape(record, a.SCHEMA)
    with pytest.raises(c.Stage12Error):
        strict.validate(binding(selection()), strict.BOUND)
    assert strict.POLICY["supplementary_chunk_files"] == 1500
    assert contract.POLICY["supplementary_chunk_files"] == 2980


def test_ra02_actual_dated_limits_not_upgraded_and_missing_pid_coverage_accepted():
    selected = selection()
    auth = Authority(selected)
    result = a.verify_runtime(binding(selected), auth, {})
    assert result["memory_max_bytes"]["value"] == 12 * 2**30
    assert result["memory_high_bytes"]["value"] == 6 * 2**30
    assert result["swap_max_bytes"]["value"] == 0
    assert result["descendant_coverage"] == "NOT_ESTABLISHED"
    assert result["pids_max"]["status"] == "UNAVAILABLE"
    assert "sampling_domain_coverage" not in auth.grants
    auth.test_only = False
    with pytest.raises(c.Stage12Error):
        a.verify_current_facts(binding(selected), auth)


@pytest.mark.parametrize(
    "field", ["boot_id", "memory_max_bytes", "visible_identity_inventory_sha256"]
)
def test_ra03_changed_current_facts_stop(field):
    selected = selection()
    auth = Authority(selected)
    auth.current[field] = (
        "2" * 32
        if field == "boot_id"
        else (
            "2" * 64
            if field.endswith("sha256")
            else a.known(6 * 2**30, "KERNEL", "VISIBLE_CGROUP", 2)
        )
    )
    with pytest.raises(c.Stage12Error):
        a.verify_current_facts(binding(selected), auth)


def test_ra03_representative_never_leaks_service_scope():
    selected = selection("REPRESENTATIVE_NO_SERVICE")
    auth = Authority(selected)
    with pytest.raises(c.Stage12Error):
        a.verify_runtime(binding(selected), auth, {})
    auth.diagnostic_scope, auth.service_authority = "REPRESENTATIVE_NO_SERVICE", False
    a.verify_runtime(binding(selected), auth, {})
    auth.service_authority = True
    with pytest.raises(c.Stage12Error):
        a.verify_runtime(binding(selected), auth, {})


def test_ra04_logical_boundaries_and_concurrent_scratch_partition():
    selected, record = selection(), binding(selection())
    profile = {
        "sampling_runtime_bound_sha256": contract.digest(record),
        "sampling_assurance_method": a.METHOD,
    }
    start = dict(client_git_sha=G, runtime_inventory_sha256=H)
    a.validate_record(record, profile, start, contract)
    assert sum(scratch.CAPS.values()) == 63616
    assert sum(scratch.RA_G1_CAPS.values()) == 65152
    with scratch.lease("KERNEL"), scratch.ra_g1_lease("MONITOR_CODEC"):
        with pytest.raises(c.Stage12Error):
            with scratch.lease("KERNEL"):
                pass
    with pytest.raises(c.Stage12Error):
        with scratch.lease("MONITOR_CODEC"):
            pass
    record["logical_scratch_bytes"] = a.LEGACY_LOGICAL_SCRATCH_BYTES - 1
    record["logical_allocations"][3]["bytes"] = a.LEGACY_LOGICAL_SCRATCH_BYTES - 1
    record["total_logical_bytes"] = sum(row["bytes"] for row in record["logical_allocations"])
    profile["sampling_runtime_bound_sha256"] = contract.digest(record)
    with pytest.raises(c.Stage12Error):
        a.validate_record(record, profile, start, contract)
    assert selected["monitor"]["period_ms"] == 500


@pytest.mark.parametrize(
    "field,value",
    [("processes", 5), ("threads", 257), ("python_invocations", 6), ("utilities", 257)],
)
def test_ra05_roster_caps(field, value):
    selected = selection()
    selected["limits"][field] = value
    with pytest.raises(c.Stage12Error):
        a.validate_selection(selected)


@pytest.mark.parametrize(
    "gap,allowed", [(999999999, True), (1000000000, True), (1000000001, False)]
)
def test_ra06_real_acquisition_gap_inclusive_boundary(gap, allowed):
    selected = selection()
    coverage = m.Coverage(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        seed_sha256=H,
        selected=selected,
        scope_start_ns=100,
    )
    first = observation(selected)
    coverage.add(first)
    final = observation(
        selected, seq=2, enter=100 + gap, kind="FINAL", previous=coverage.head
    )
    if allowed:
        coverage.add(final)
        coverage.require_complete(opener_return_ns=100, last_ack_ns=100 + gap)
    else:
        with pytest.raises(c.Stage12Error):
            coverage.add(final)


def test_ra06_codec_all_uint64_max_closed_export_and_padding():
    selected = selection()
    row = observation(selected)
    maximum = 2**64 - 1
    row["counters"] = {key: maximum for key in m.COUNTERS}
    raw = m.pack_observation(row)
    assert len(raw) == 1024 and m.unpack_observation(raw) == row
    assert len(m.export_observation(row)) <= 8192
    damaged = raw[:-1] + b"\x01"
    with pytest.raises(c.Stage12Error):
        m.unpack_observation(damaged)
    row["unexpected"] = "secret-not-echoed"
    with pytest.raises(c.Stage12Error):
        m.pack_observation(row)


@pytest.mark.parametrize(
    "key,limit",
    [
        ("self_rss_peak_bytes", 768 * 2**20),
        ("registered_visible_rss_bytes", 5 * 2**30),
        ("visible_native_threads", 256),
        ("visible_native_file_bytes", 8589934592),
    ],
)
def test_ra06_threshold_equality_and_exceedance(key, limit):
    selected, row = selection(), observation(selection())
    row["readings"][key]["value"] = limit
    if key == "visible_native_file_bytes":
        row["native_visibility"]["visible_allocated_bytes"] = deepcopy(
            row["readings"][key]
        )
    m.thresholds(row, selected)
    row["readings"][key]["value"] += 1
    if key == "visible_native_file_bytes":
        row["native_visibility"]["visible_allocated_bytes"] = deepcopy(
            row["readings"][key]
        )
    with pytest.raises(c.Stage12Error):
        m.thresholds(row, selected)


def test_ra06_acquisition_duration_and_ack_cannot_refresh_old_observation():
    selected = selection()
    row = observation(selected, exit_ns=1000000101)
    with pytest.raises(c.Stage12Error):
        m.thresholds(row, selected)
    monitor = m.ResourceMonitor(
        observer=lambda kind: None,
        writer=SimpleNamespace(poisoned=False, acked=1, ack_ns=2000000000),
        selected=selected, binding_sha256=H, phase_id=1, seed_sha256=H,
        deadline_ns=2000000000, check=lambda: None, clock_ns=lambda: 1000000101)
    monitor.last = observation(selected)
    with pytest.raises(c.Stage12Error):
        monitor.barrier()


def test_ra07_capacity_margin_exact_and_unknown_not_zero():
    record = capacity(selection())
    record["bavail_bytes"]["value"], record["favail"]["value"] = 1342177290, 4097
    a.check_capacity(record, next_write_bytes=10, next_creations=1)
    record["bavail_bytes"]["value"] -= 1
    with pytest.raises(c.Stage12Error):
        a.check_capacity(record, next_write_bytes=10, next_creations=1)
    record["bavail_bytes"] = a.unknown()
    with pytest.raises(c.Stage12Error):
        a.validate_capacity(record)
    assert record["entitlement"] == "NOT_ASSERTED" and record["reservation"] == "NONE"


def test_ra07_private_ancestors_and_symlinks_reject(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    original = a.private_root_identity(root)
    root.chmod(0o755)
    with pytest.raises(c.Stage12Error):
        a.private_root_identity(root)
    root.chmod(0o700)
    renamed = tmp_path / "renamed"
    root.rename(renamed)
    root.symlink_to(renamed, target_is_directory=True)
    with pytest.raises(c.Stage12Error):
        a.private_root_identity(root)
    assert original


def test_ra08_single_bounded_writer_fresh_readback_and_mutation(tmp_path):
    root = tmp_path / "monitor"
    root.mkdir(mode=0o700)
    selected = selection()
    charges = []
    writer = m.ObservationWriter(
        root / "observations.bin",
        maximum_rows=2,
        charge=lambda n, k: charges.append((n, k)),
        check=lambda: None,
    )
    deadline = time.monotonic_ns() + 5_000_000_000
    first = observation(selected)
    block = m.pack_observation(first)
    writer.append(block, 1, deadline)
    writer.wait(1, deadline)
    writer.close(deadline)
    assert writer.released and charges == [(0, 1), (1024, 0)]
    assert list(m.read_observations(writer.path, maximum_rows=2)) == [first]
    writer.path.write_bytes(block[:-1])
    with pytest.raises(c.Stage12Error):
        list(m.read_observations(writer.path, maximum_rows=2))


def test_ra12_opener_late_return_never_manufactures_record():
    now = [100]
    protocol = m.PhaseProtocol(
        binding_sha256=H,
        selection_sha256=H,
        phase_id=1,
        deadline_ns=200,
        check=lambda: None,
        clock_ns=lambda: now[0],
    )
    protocol.state, protocol.inventory = "PREOPEN_READY", H
    protocol.closure = {"original_observation_prefix_sha256": H}

    def late():
        now[0] = 200

    with pytest.raises(c.Stage12Error):
        protocol.open(late)
    assert protocol.opener is None


def test_ra13_counter_reset_and_native_unknowns_are_not_silenced():
    selected = selection()
    scope = m.Coverage(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        seed_sha256=H,
        selected=selected,
        scope_start_ns=100,
    )
    first = observation(selected)
    first["counters"]["SQLITE"] = 1
    scope.add(first)
    final = observation(selected, seq=2, enter=500, kind="FINAL", previous=scope.head)
    with pytest.raises(c.Stage12Error):
        scope.add(final)
    assert final["native_visibility"]["deleted_open_bytes"] == "NOT_MEASURED"
    final["native_visibility"]["discovery_status"] = "OVERFLOW"
    with pytest.raises(c.Stage12Error):
        m.validate(final)


def test_ra14_missing_final_or_failed_child_cannot_qualify():
    selected = selection()
    scope = m.Coverage(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        seed_sha256=H,
        selected=selected,
        scope_start_ns=100,
    )
    scope.add(observation(selected))
    with pytest.raises(c.Stage12Error):
        scope.require_complete(opener_return_ns=100, last_ack_ns=100)
    protocol = m.PhaseProtocol(
        binding_sha256=H,
        selection_sha256=H,
        phase_id=1,
        deadline_ns=1000,
        check=lambda: None,
        clock_ns=lambda: 100,
    )
    with pytest.raises(c.Stage12Error):
        protocol.advance("TERMINAL_SUCCESS")
    protocol.state = "UNCERTAIN"
    with pytest.raises(c.Stage12Error):
        protocol.advance("DATA_FROZEN")


def test_ra10_timing_successor_caps_and_incompatible_methods_reject():
    assert timing.selected_max_files(timing.RA_SCHEMA, timing.RA_POLICY) == 2980
    assert (
        timing.selected_max_files(timing.RA_SCHEMA, timing.RA_PROTECTED_POLICY) == 1500
    )
    assert timing.selected_max_files(timing.SCHEMA, timing.POLICY_VERSION) == 1500
    with pytest.raises(Exception):
        timing.selected_max_files(timing.SCHEMA, timing.RA_POLICY)
    with pytest.raises(Exception):
        timing.selected_max_files(timing.RA_SCHEMA, timing.POLICY_VERSION)


def test_ra14_complete_acyclic_original_tail_and_postwrite_deadline(tmp_path):
    selected = selection()
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    scope = m.Coverage(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        seed_sha256=H,
        selected=selected,
        scope_start_ns=100,
    )
    first = observation(selected)
    first_original = original_observation(first)
    first["visible_identity_inventory_sha256"] = contract.digest(first_original)
    scope.add(first)
    prefix = scope.inventory_sha256()
    closure = dict(
        schema_version=m.CLOSURE,
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        original_observation_prefix_sha256=prefix,
        last_seq=1,
        monitor_coverage="COMPLETE_SELECTED_SCOPE",
        max_observed_gap_ns=0,
        counter_totals_sha256=contract.digest(first["counters"]),
        original_inventory_sha256=H,
        first_failure=None,
        cleanup_failure=None,
        outcome="PENDING_OPEN",
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        accepted_risk_inventory_sha256=H,
        actual_opener_record_sha256=None,
    )
    now = [120]
    protocol = m.PhaseProtocol(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        deadline_ns=1000,
        check=lambda: None,
        clock_ns=lambda: now[0],
    )
    protocol.freeze(H)
    protocol.preopen(closure)
    called = []

    def opener():
        called.append("actual")
        now[0] = 150
        return "opened"

    result, opener_record = protocol.open(opener)
    assert result == "opened" and called == ["actual"]
    final = observation(
        selected, seq=2, enter=200, exit_ns=210, kind="FINAL", previous=scope.head
    )
    final_original = original_observation(final)
    final["visible_identity_inventory_sha256"] = contract.digest(final_original)
    scope.add(final)
    original_map = {
        contract.digest(original): original
        for original in (first_original, final_original)
    }
    writer = SimpleNamespace(released=True, poisoned=False, ack_ns=220)
    monitor = SimpleNamespace(
        writer=writer, failure=None, coverage=scope, binding=H, phase=1, scope_start=100
    )
    terminal = m.monitor_terminal_record(
        monitor, opener_return=opener_record, prefix_H0_sha256=prefix
    )
    assert terminal["coverage_end_ns"] == 210
    protocol.monitor_closed(terminal)
    path = root / "monitor.bin"
    path.write_bytes(m.pack_observation(first) + m.pack_observation(final))
    path.chmod(0o600)
    # Reconstruct existing original history; no opener is invoked here.
    now[0] = 300
    restored = m.reopen_phase_protocol(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        closure=closure,
        opener_return=opener_record,
        monitor_terminal=terminal,
        deadline_ns=1000,
        check=lambda: None,
        clock_ns=lambda: now[0],
    )
    assert called == ["actual"] and restored.state == "MONITOR_CLOSED"
    child = dict(pid=123, wait_status=0, acquired_mono_ns=250)
    terminal_phase = m.verify_tail(
        protocol=restored,
        monitor_path=path,
        selected=selected,
        seed_sha256=H,
        child_result=child,
        genuine_wait_status=0,
        expected_child_pid=123,
        current_counter_sha256=H,
        persist_terminal=lambda record, guard: record,
        original_observation_reader=original_map.__getitem__,
        test_only=True,
    )
    assert (
        restored.state == "TERMINAL_SUCCESS"
        and terminal_phase["disposition"] == "COMPLETE_SELECTED_SCOPE"
    )
    restored = m.reopen_phase_protocol(
        binding_sha256=H,
        selection_sha256=contract.digest(selected),
        phase_id=1,
        closure=closure,
        opener_return=opener_record,
        monitor_terminal=terminal,
        deadline_ns=1000,
        check=lambda: None,
        clock_ns=lambda: now[0],
    )

    def late_write(record, guard):
        now[0] = 1000
        return record

    with pytest.raises(c.Stage12Error):
        m.verify_tail(
            protocol=restored,
            monitor_path=path,
            selected=selected,
            seed_sha256=H,
            child_result=child,
            genuine_wait_status=0,
            expected_child_pid=123,
            current_counter_sha256=H,
            persist_terminal=late_write,
            original_observation_reader=original_map.__getitem__,
            test_only=True,
        )
    assert restored.state != "TERMINAL_SUCCESS"


def test_ra10_actual_new_timing_wire_roundtrip_and_old_reader_rejects(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    from test_stage12_public_operations_v2 import FakeClock
    from test_stage12_wf_ap2_timing import row

    clock = FakeClock()
    value = timing.Checkpoints(
        tmp_path / "timing",
        timing_binding=dict(policy_sha256=H, source_sha256=H, task_sha256=H),
        phase_windows=[dict(phase_id=1, selected_phase_ms=20000)],
        cumulative_deadline_ns=100_000_000_000,
        clock_ns=clock.now_ns,
        timing_schema=timing.RA_SCHEMA,
        timing_policy_version=timing.RA_POLICY,
        max_files=2980,
    )
    value.phase_open(1, timeout_seconds=2)
    value.record(row())
    value.phase_close(1, timeout_seconds=2)
    value.close(timeout_seconds=2)
    snapshot = value.snapshot()
    assert snapshot["schema"] == timing.RA_SCHEMA
    result = cp.read_prefix(
        value.root,
        max_files=2980,
        expected_binding=dict(policy_sha256=H, source_sha256=H, task_sha256=H),
        expected_snapshot=snapshot,
    )
    assert not result["incomplete"]
    old_result = timing.read_prefix(value.root)
    assert old_result["incomplete"]


def test_ra06_actual_independent_monitor_writer_and_final_coverage(tmp_path):
    import time

    root = tmp_path / "monitor"
    root.mkdir(mode=0o700)
    selected = selection()
    writer = m.ObservationWriter(
        root / "stream.bin",
        maximum_rows=100,
        charge=lambda n, k: None,
        check=lambda: None,
    )

    def observer(kind):
        row = observation(selected, enter=time.monotonic_ns(), kind=kind)
        return {
            key: row[key]
            for key in (
                "readings",
                "counters",
                "native_visibility",
                "visible_identity_inventory_sha256",
            )
        }

    monitor = m.ResourceMonitor(
        observer=observer,
        writer=writer,
        selected=selected,
        binding_sha256=H,
        phase_id=1,
        seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        check=lambda: None,
    )
    monitor.start()
    time.sleep(0.55)
    monitor.barrier()
    actual_return = time.monotonic_ns()
    final = monitor.finish(opener_return_ns=actual_return)
    assert final["kind"] == "FINAL" and final["enter_mono_ns"] >= actual_return
    assert monitor.seq >= 3 and writer.released and not writer.thread.is_alive()
    assert monitor.coverage.max_gap <= 1_000_000_000
    assert [row["kind"] for row in m.read_observations(writer.path, maximum_rows=100)][
        -1
    ] == "FINAL"


def test_ra08_uncertain_monitor_writer_retains_charges_and_partial_original(
    tmp_path, monkeypatch
):
    import time

    root = tmp_path / "monitor"
    root.mkdir(mode=0o700)
    charges = []
    writer = m.ObservationWriter(
        root / "stream.bin",
        maximum_rows=2,
        charge=lambda n, k: charges.append((n, k)),
        check=lambda: None,
    )

    def fail(fd):
        raise OSError(28, "unsafe detail not exposed")

    monkeypatch.setattr(m.os, "fsync", fail)
    deadline = time.monotonic_ns() + 5_000_000_000
    writer.append(m.pack_observation(observation(selection())), 1, deadline)
    with pytest.raises(c.Stage12Error):
        writer.wait(1, deadline)
    writer.thread.join(1)
    assert (
        writer.poisoned and not writer.released and writer.path.stat().st_size == 1024
    )
    assert charges == [(0, 1), (1024, 0)]


def test_ra06_original_15360_boundary_plus_codec_fits_selected_16384(tmp_path):
    row = observation(selection())
    original = original_observation(row)
    assert original["origin"] == "SYNTHETIC_TEST_ONLY"
    with pytest.raises(c.Stage12Error):
        m.validate_original_observation(original)
    # Original source strings remain <=8192; no dropped original field.
    for _ in range(4):
        original["read_bytes"] = sum(
            len(item["text"]) for item in original["kernel_records"]
        )
        remaining = 15360 - len(c.canonical(original))
        if not remaining:
            break
        if remaining < 0:
            original["kernel_records"][2]["text"] = original["kernel_records"][2][
                "text"
            ][:remaining]
        else:
            for item in reversed(original["kernel_records"]):
                addition = min(8192 - len(item["text"]), remaining)
                item["text"] += " " * addition
                remaining -= addition
                if not remaining:
                    break
    original["read_bytes"] = sum(
        len(item["text"]) for item in original["kernel_records"]
    )
    raw = m.export_original_observation(original, allow_synthetic=True)
    assert len(raw) == 15360 and len(m.pack_observation(row)) + len(raw) == 16384
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    path = root / "original.record"
    path.write_bytes(raw)
    path.chmod(0o600)
    assert (
        m.read_original_observation(
            path, expected_sha256=contract.digest(original), test_only=True
        )
        == original
    )
    original["kernel_records"][1]["text"] += " "
    original["read_bytes"] += 1
    with pytest.raises(Exception):
        m.export_original_observation(original, allow_synthetic=True)


def test_ra13_original_hash_alone_cannot_replace_resource_value_agreement():
    row = observation(selection())
    original = original_observation(row)
    row["visible_identity_inventory_sha256"] = contract.digest(original)
    m.validate_original_observation(original, observation=row, allow_synthetic=True)
    row["readings"]["registered_visible_rss_bytes"]["value"] += 1024
    with pytest.raises(c.Stage12Error):
        m.validate_original_observation(original, observation=row, allow_synthetic=True)


def test_ra03_zero_visible_memory_limit_is_not_ignored():
    selected = selection()
    auth = Authority(selected)
    auth.original["memory_max_bytes"]["value"] = 0
    auth.current = deepcopy(auth.original)
    record = binding(selected)
    record["initial_environment_observation_sha256"] = contract.digest(auth.original)
    with pytest.raises(c.Stage12Error):
        a.verify_runtime(record, auth, {})


def test_ra06_published_prefix_excludes_pending_unacknowledged_acquisition():
    import threading
    import time

    selected = selection()
    pending, release = threading.Event(), threading.Event()

    class Writer:
        acked, ack_ns, poisoned, released = 0, 0, False, False

        def append(self, block, seq, deadline):
            pass

        def wait(self, seq, deadline):
            if seq == 2:
                pending.set()
                assert release.wait(0.5)
            self.acked, self.ack_ns = seq, time.monotonic_ns()

        def close(self, deadline):
            self.released = True

    writer = Writer()

    def observer(kind):
        row = observation(selected, enter=time.monotonic_ns(), kind=kind)
        return {
            key: row[key]
            for key in (
                "readings",
                "counters",
                "native_visibility",
                "visible_identity_inventory_sha256",
            )
        }

    monitor = m.ResourceMonitor(
        observer=observer,
        writer=writer,
        selected=selected,
        binding_sha256=H,
        phase_id=1,
        seed_sha256=H,
        deadline_ns=time.monotonic_ns() + 5_000_000_000,
        check=lambda: None,
    )
    monitor.start()
    try:
        assert pending.wait(1)
        prefix = monitor.prefix()
        assert monitor.coverage.seq == 2 and prefix["last_seq"] == 1
        prefix["counters"]["SQLITE"] = 100
        assert monitor.prefix()["counters"]["SQLITE"] == 0
    finally:
        release.set()
        monitor.finish(opener_return_ns=time.monotonic_ns())


def test_ra02_original_environment_recomputes_values_and_rejects_rehashed_mismatch():
    import stat

    current = facts()
    current["pids_max"] = a.unknown("UNAVAILABLE", "INACCESSIBLE")
    identity = dict(
        domain="/sys/fs/cgroup/synthetic/job",
        device=1,
        inode=2,
        boot_id=current["boot_id"],
        cgroup_namespace_inode=1,
        mount_namespace_inode=2,
        membership="0::/synthetic/job",
    )
    texts = {
        "/proc/123/cgroup": "0::/synthetic/job\n",
        "/proc/sys/kernel/random/boot_id": current["boot_id"] + "\n",
        "/sys/fs/cgroup/synthetic/job/memory.max": str(12 * 2**30) + "\n",
        "/sys/fs/cgroup/synthetic/job/memory.high": str(6 * 2**30) + "\n",
        "/sys/fs/cgroup/synthetic/job/memory.swap.max": "0\n",
    }
    original = dict(
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
    current["visible_identity_inventory_sha256"] = contract.digest(identity)
    current["visible_membership_sha256"] = contract.digest(
        {"membership": identity["membership"]}
    )
    current["observation_inventory_sha256"] = contract.digest(original)
    assert a.validate_environment_originals(current, c.canonical(original)) == original
    original["records"]["/sys/fs/cgroup/synthetic/job/memory.high"]["text"] = "0\n"
    current["observation_inventory_sha256"] = contract.digest(original)
    with pytest.raises(c.Stage12Error):
        a.validate_environment_originals(current, original)


def test_ra07_selected_native_root_separate_from_evidence_and_no_outside_or_symlink(
    tmp_path, monkeypatch
):
    import os
    from pathlib import Path

    evidence, native, outside = (
        tmp_path / name for name in ("evidence", "native", "outside")
    )
    for root in (evidence, native, outside):
        root.mkdir(mode=0o700)
    file = native / "database.db"
    file.write_bytes(b"synthetic native file")
    file.chmod(0o600)
    real_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        return (
            path
            if str(path) == "/sys/fs/cgroup/synthetic-test"
            else real_resolve(path, *args, **kwargs)
        )

    monkeypatch.setattr(Path, "resolve", resolve)
    arguments = dict(
        pids=(os.getpid(),),
        cgroup_path="/sys/fs/cgroup/synthetic-test",
        root=evidence,
        native_paths=(file,),
        native_roots=(native,),
        counter_provider=lambda: {key: 0 for key in m.COUNTERS},
        retain_originals=lambda value: contract.digest(value),
        admitted_process_provider=lambda: (os.getpid(),),
        read_charge=lambda n, k: None,
    )
    observer = m.LinuxObserver(**arguments)
    assert observer.paths == (file,) and observer.native_roots == (native,)
    with pytest.raises(c.Stage12Error):
        m.LinuxObserver(**{**arguments, "native_paths": (outside / "database.db",)})
    alias = tmp_path / "alias"
    alias.symlink_to(native, target_is_directory=True)
    with pytest.raises(c.Stage12Error):
        m.LinuxObserver(
            **{
                **arguments,
                "native_roots": (alias,),
                "native_paths": (alias / "database.db",),
            }
        )


@pytest.mark.parametrize("scope", a.SCOPES)
def test_ra03_adopted_scope_ceilings_at_bound_and_over(scope):
    selected = selection(scope)
    selected["limits"].update(a.SCOPE_CEILINGS[scope])
    if scope in ("DEVELOPMENT_ONLY", "DEVELOPMENT_LOCAL_PREPARATION"):
        selected["limits"]["creations"] = 100000
    a.validate_selection(selected)
    for field, maximum in a.SCOPE_CEILINGS[scope].items():
        candidate = deepcopy(selected)
        candidate["limits"][field] = maximum + 1
        with pytest.raises(c.Stage12Error, match="RA_G1_ADOPTED_CEILING"):
            a.validate_selection(candidate)


def test_ra03_finite_child_deadlines_and_closure_reserve_cannot_weaken():
    selected = selection("REPRESENTATIVE_NO_SERVICE")
    selected["limits"]["closure_reserve_creations"] = 4095
    with pytest.raises(c.Stage12Error):
        a.validate_selection(selected)
    selected = selection("REPRESENTATIVE_NO_SERVICE")
    selected["limits"]["stages"][0]["deadline_ms"] = 346001
    selected["limits"]["processing_ms"] = 8160000
    selected["limits"]["scheduler_s"] = 8400
    with pytest.raises(c.Stage12Error):
        a.validate_selection(selected)


def test_ra07_capacity_original_units_hashes_and_current_root(tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    method = {"method": "CURRENT_STATVFS_SHARED_SNAPSHOT_NOT_RESERVATION"}
    restrictions = {
        "known": "SITE_PROJECT_RULES_PRESERVED",
        "unknown": "NOT_ESTABLISHED",
    }
    cap, originals = a.observe_capacity(
        root,
        scope="PUBLIC_SYNTHETIC_ONLY",
        selection_sha256=H,
        owner_reported_approval_sha256=H,
        accounting_method_sha256=contract.digest(method),
        restrictions_inventory_sha256=contract.digest(restrictions),
        observed_utc=FROM,
    )
    a.validate_capacity_originals(
        cap,
        originals["root"],
        originals["statvfs"],
        method,
        restrictions,
        root_path=root,
    )
    raw = deepcopy(originals["statvfs"])
    raw["f_frsize"] *= 2
    changed = deepcopy(cap)
    changed["filesystem_originals_sha256"] = contract.digest(raw)
    with pytest.raises(c.Stage12Error, match="RA_G1_CAPACITY_VALUE_CHANGED"):
        a.validate_capacity_originals(
            changed, originals["root"], raw, method, restrictions
        )
    root.chmod(0o755)
    with pytest.raises(c.Stage12Error):
        a.validate_capacity_originals(
            cap,
            originals["root"],
            originals["statvfs"],
            method,
            restrictions,
            root_path=root,
        )


def test_ra13_bounded_backend_reader_full_bytes_eof_and_mutation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import hashlib

    path = tmp_path / "synthetic_backend.so"
    path.write_bytes(b"x" * 9000)
    path.chmod(0o600)
    monkeypatch.setattr(
        "importlib.import_module", lambda name: SimpleNamespace(__file__=str(path))
    )
    calls = []
    reader = a.bounded_backend_reader(lambda n, size: calls.append((n, size)))
    assert (
        reader("_hashlib", path, lambda: None)
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert sum(n for n, _ in calls) == 4 and sum(size for _, size in calls) == 9000
    checks = [0]

    def mutate():
        checks[0] += 1
        if checks[0] == 3:
            with path.open("ab") as stream:
                stream.write(b"mutation")

    with pytest.raises(c.Stage12Error):
        reader("_hashlib", path, mutate)


@pytest.mark.parametrize(
    "scope,science_count",
    [("REPRESENTATIVE_NO_SERVICE", 4), ("PUBLIC_SYNTHETIC_ONLY", 11)],
)
def test_ra12_actual_whole_task_admin_scope_valid_and_budgeted(scope, science_count):
    selected = selection(scope)
    selected["limits"].update(a.SCOPE_CEILINGS[scope])
    stage = selected["limits"]["stages"][0]
    selected["limits"]["stages"] = [
        {**stage, "id": i, "phase": i} for i in range(1, science_count + 1)
    ]
    admin = {
        **stage,
        "id": science_count + 1,
        "phase": science_count + 1,
        "deadline_ms": 120000,
        "reserve_ms": 5000,
        "attempts": 0,
        "events": 0,
        "logical_write_bytes": 16 * 2**20,
        "creations": 256,
    }
    selected["limits"]["stages"].append(admin)
    a.validate_selection(selected)
    for field in ("attempts", "events"):
        broken = deepcopy(selected)
        broken["limits"]["stages"][-1][field] = 1
        with pytest.raises(c.Stage12Error, match="RA_G1_ADMIN_SCOPE"):
            a.validate_selection(broken)
    selected["limits"]["stages"][-1]["deadline_ms"] = (
        6194001 if scope == "REPRESENTATIVE_NO_SERVICE" else 2020001
    )
    with pytest.raises(c.Stage12Error, match="RA_G1_ADOPTED_CEILING"):
        a.validate_selection(selected)

"""Synthetic M2/AP2 gates and mocked kernel interfaces; never live evidence."""

from copy import deepcopy
import io
from pathlib import PurePosixPath
from types import SimpleNamespace as NS
import stat
import threading

import pytest

from test_stage12_public_operations_v2 import FakeClock, H, offline  # noqa: F401
from test_stage12_public_sampling_contract import ap_inputs
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as old,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as a
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_scratch as scratch


def evidence(label):
    return c.sha(("SYNTHETIC TEST ONLY: " + label).encode()).hex()


def m2_inputs():
    profile, plan, start, rows, runtime, strict = ap_inputs()
    values = [65536, 8 * 2**20, 4096 * 512, 65536, 32768, 16384, 0]
    record = dict(
        schema_version=m.BOUND,
        scope=a.SCOPE,
        method=m.METHOD,
        sampling_policy_sha256=a.POLICY_SHA,
        client_git_sha=start["client_git_sha"],
        runtime_inventory_sha256=start["runtime_inventory_sha256"],
        configuration_scope_sha256=H,
        invocation_graph_sha256=evidence("graph"),
        technical_review_record_sha256=evidence("review"),
        enforcement_evidence_sha256=evidence("kernel enforcement"),
        domain_coverage_evidence_sha256=evidence("domain coverage"),
        method_evidence_sha256=[evidence("logical inventory")],
        maximum_enforcement_checks=128,
        maximum_runtime_inventory_checks=64,
        evidence_origin="SYNTHETIC_TEST_ONLY",
        valid_from="2026-01-01T00:00:00.000000Z",
        valid_until="2026-01-02T00:00:00.000000Z",
        logical_allocations=[
            dict(name=name, bytes=size, evidence_sha256=H)
            for name, size in zip(m.ARENAS, values, strict=True)
        ],
        total_logical_bytes=sum(values),
        logical_scratch_bytes=65536,
        native_component_guarantee="NOT_CLAIMED",
        native_scratch_guarantee="NOT_CLAIMED",
        domain=dict(
            path="/sys/fs/cgroup/synthetic/job",
            device=71,
            inode=99,
            cgroup_namespace_inode=61,
            mount_namespace_inode=62,
            boot_id="1" * 32,
            memory_max_bytes=m.MAX_JOB_BYTES,
            swap_max_bytes=0,
            pids_max=64,
        ),
    )
    profile.update(
        schema_version=a.PROFILE,
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
        sampling_runtime_bound_sha256=a.digest(record),
        **a.assurance_fields(),
    )
    plan.update(
        schema_version=a.PLAN,
        operations_profile_sha256=a.digest(profile),
        history_limits=dict(
            maximum_entries=100000,
            maximum_name_bytes=256,
            maximum_total_name_bytes=25600000,
            page_entries=8,
            maximum_depth=8,
            maximum_file_bytes=2**26,
        ),
    )
    start.update(
        schema_version=a.START,
        rule_bundle_sha256=a.RULE_BUNDLE,
        profile_sha256=a.digest(profile),
        plan_sha256=a.digest(plan),
        sampling_policy_sha256=a.POLICY_SHA,
        **a.assurance_fields(),
    )
    return profile, plan, start, record, strict


def repin(profile, plan, start, record):
    profile["sampling_runtime_bound_sha256"] = a.digest(record)
    plan["operations_profile_sha256"] = a.digest(profile)
    start["profile_sha256"], start["plan_sha256"] = a.digest(profile), a.digest(plan)


def facts(record):
    return {
        **deepcopy(record["domain"]),
        "membership_matches": True,
        "nondelegated": True,
        "no_capabilities": True,
        "descendants_share_domain": True,
        "no_new_privileges": True,
        "pids_current": 4,
        "observation_origin": "KERNEL_CGROUP_V2",
    }


class SyntheticAuthority:
    """Exact test purposes, evidence hashes and contexts; always denies live grants."""

    test_only = True
    configuration_scope_sha256 = H

    def __init__(self, profile, plan, start, record):
        self.profile, self.plan, self.start = deepcopy((profile, plan, start))
        self.record = deepcopy(record)
        self.clock = FakeClock()
        self.observed = facts(record)
        self.calls = []
        self.enforcement_checks = 0
        self.runtime_inventory_checks = 0
        context = dict(profile=self.profile, plan=self.plan, start=self.start)
        self.expected = {
            "sampling_enforcement_domain": (
                record["enforcement_evidence_sha256"],
                record,
            ),
            "sampling_domain_coverage": (
                record["domain_coverage_evidence_sha256"],
                record,
            ),
            "sampling_invocation_graph": (record["invocation_graph_sha256"], context),
            "sampling_runtime_bound": (a.digest(record), context),
            "sampling_bound_review": (record["technical_review_record_sha256"], record),
            "operator_allowance": (
                profile["operator_allowance"]["record_sha256"],
                profile,
            ),
            "transport_profile": (profile["transport_profile_sha256"], profile),
            "plan_selection": (plan["selection_basis_sha256"], plan),
            "resources": (
                profile["resources"]["resource_review_sha256"],
                profile["resources"],
            ),
            "monitoring": (
                profile["monitoring"]["gaps_record_sha256"],
                profile["monitoring"],
            ),
        }
        for key in (
            "policy_freeze_record_sha256",
            "implementation_authorization_sha256",
            "implementation_review_sha256",
            "initial_workload_authority_sha256",
        ):
            self.expected[key] = start[key], context
        if profile["resources"]["admission_memory_bytes"] != a.MEMORY:
            self.expected["capacity_change"] = (
                profile["resources"]["capacity_basis_sha256"],
                profile["resources"],
            )

    def sampling_bound(self, profile, start):
        c.require(
            profile == self.profile and start == self.start, "SYNTHETIC_BINDING_DENIED"
        )
        return deepcopy(self.record)

    def enforcement_facts(self, record):
        c.require(record == self.record, "SYNTHETIC_BINDING_DENIED")
        return deepcopy(self.observed)

    def charge_enforcement_check(self, record):
        c.require(record == self.record, "SYNTHETIC_BINDING_DENIED")
        self.enforcement_checks += 1
        c.require(
            self.enforcement_checks <= record["maximum_enforcement_checks"],
            "SYNTHETIC_ENFORCEMENT_LIMIT",
        )

    def charge_runtime_inventory_check(self, record):
        c.require(record == self.record, "SYNTHETIC_BINDING_DENIED")
        self.runtime_inventory_checks += 1
        c.require(
            self.runtime_inventory_checks <= record["maximum_runtime_inventory_checks"],
            "SYNTHETIC_RUNTIME_INVENTORY_LIMIT",
        )

    def require(self, purpose, digest, context):
        c.require(
            self.record["evidence_origin"] == "SYNTHETIC_TEST_ONLY",
            "SYNTHETIC_LIVE_GRANT_DENIED",
        )
        if purpose == "rate_state":
            matches = [(row["evidence_sha256"], row) for row in self.profile["states"]]
        elif purpose == "control_recipe":
            matches = [
                (row["implementation_contract_sha256"], row)
                for row in self.plan["control_recipes"]
            ]
        else:
            c.require(purpose in self.expected, "SYNTHETIC_PURPOSE_DENIED")
            matches = [self.expected[purpose]]
        c.require((digest, context) in matches, "SYNTHETIC_CONTEXT_DENIED")
        self.calls.append(purpose)


def test_public_successor_requires_actual_closed_record_and_review_contexts():
    profile, plan, start, record, _ = m2_inputs()
    authority = SyntheticAuthority(profile, plan, start, record)
    a.verify_authorities(profile, plan, start, authority)
    assert set(authority.expected) <= set(authority.calls)
    assert authority.calls.count("sampling_bound_review") == 1
    with pytest.raises(c.Stage12Error):
        authority.require(
            "sampling_bound_review", record["technical_review_record_sha256"], {}
        )
    with pytest.raises(c.Stage12Error):
        authority.require("unknown", H, record)
    with pytest.raises(c.Stage12Error):
        authority.require("sampling_enforcement_domain", H, record)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "bool",
        "zero",
        "unknown_method",
        "native_claim",
        "strict_record",
        "job_request",
        "high_only",
    ],
)
def test_closed_record_types_unknowns_and_incompatible_assurance_reject(mutation):
    profile, plan, start, record, strict = m2_inputs()
    if mutation == "missing":
        record.pop("domain_coverage_evidence_sha256")
    elif mutation == "extra":
        record["requested_scheduler_memory"] = m.MAX_JOB_BYTES
    elif mutation == "bool":
        record["domain"]["pids_max"] = True
    elif mutation == "zero":
        record["enforcement_evidence_sha256"] = "0" * 64
    elif mutation == "unknown_method":
        record["method"] = "MEASURED_RSS"
    elif mutation == "native_claim":
        record["native_component_guarantee"] = "CLOSED_ALLOCATION_INVENTORY"
    elif mutation == "strict_record":
        record = strict
    elif mutation == "job_request":
        record["domain"].pop("memory_max_bytes")
        record["domain"]["requested_memory_bytes"] = m.MAX_JOB_BYTES
    else:
        record["domain"].pop("memory_max_bytes")
        record["domain"]["memory_high_bytes"] = m.MAX_JOB_BYTES
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


@pytest.mark.parametrize(
    "key,value",
    [
        ("scope", "DEVELOPMENT_ONLY"),
        ("client_git_sha", "f" * 40),
        ("runtime_inventory_sha256", "f" * 64),
        ("sampling_policy_sha256", "f" * 64),
    ],
)
def test_actual_source_runtime_scope_and_policy_bindings_reject(key, value):
    profile, plan, start, record, _ = m2_inputs()
    record[key] = value
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


def test_configuration_scope_and_actual_record_digest_are_required():
    profile, plan, start, record, _ = m2_inputs()
    m.validate_record(record, profile, start, a, H)
    with pytest.raises(c.Stage12Error):
        m.validate_record(record, profile, start, a, "f" * 64)
    record["configuration_scope_sha256"] = "f" * 64
    with pytest.raises(c.Stage12Error):
        m.validate_record(record, profile, start, a)


@pytest.mark.parametrize(
    "key,value",
    [
        ("memory_max_bytes", 12 * 2**30),
        ("swap_max_bytes", 1),
        ("pids_max", 0),
        ("path", "/sys/fs/cgroup/../escape"),
    ],
)
def test_domain_envelope_is_actual_finite_and_non_escaping(key, value):
    profile, plan, start, record, _ = m2_inputs()
    record["domain"][key] = value
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


def test_logical_16mib_and_64kib_exact_boundaries_and_inventory():
    profile, plan, start, record, _ = m2_inputs()
    record["logical_allocations"][-1]["bytes"] = (
        m.LOGICAL_BYTES - record["total_logical_bytes"]
    )
    record["total_logical_bytes"] = m.LOGICAL_BYTES
    repin(profile, plan, start, record)
    a.validate_bound(record, profile, start)
    for mutation in (
        "logical_over",
        "scratch_over",
        "small_scratch",
        "duplicate_arena",
        "native_family",
    ):
        changed = deepcopy(record)
        if mutation == "logical_over":
            changed["logical_allocations"][-1]["bytes"] += 1
            changed["total_logical_bytes"] += 1
        elif mutation in ("scratch_over", "small_scratch"):
            size = (
                65537 if mutation == "scratch_over" else sum(scratch.CAPS.values()) - 1
            )
            changed["logical_allocations"][3]["bytes"] = changed[
                "logical_scratch_bytes"
            ] = size
            if mutation == "scratch_over":
                changed["logical_allocations"][-1]["bytes"] -= size - 65536
            changed["total_logical_bytes"] = sum(
                row["bytes"] for row in changed["logical_allocations"]
            )
        elif mutation == "duplicate_arena":
            changed["logical_allocations"][-1]["name"] = "TRACE_METADATA"
        else:
            changed["method"] = "STRICT_COMPONENT_NATIVE_INVENTORY"
        repin(profile, plan, start, changed)
        with pytest.raises(c.Stage12Error):
            a.validate_bound(changed, profile, start)


@pytest.mark.parametrize(
    "key",
    [
        "membership_matches",
        "nondelegated",
        "no_capabilities",
        "descendants_share_domain",
        "no_new_privileges",
    ],
)
def test_fresh_domain_facts_require_every_enforcement_term(key):
    profile, plan, start, record, _ = m2_inputs()
    authority = SyntheticAuthority(profile, plan, start, record)
    authority.observed[key] = False
    with pytest.raises(c.Stage12Error):
        m.verify_current_facts(record, authority)


@pytest.mark.parametrize("key", list(m.DOMAIN))
def test_every_recorded_domain_identity_and_limit_matches_fresh_facts(key):
    profile, plan, start, record, _ = m2_inputs()
    authority = SyntheticAuthority(profile, plan, start, record)
    value = authority.observed[key]
    authority.observed[key] = (
        value + 1
        if type(value) is int
        else "/sys/fs/cgroup/changed"
        if key == "path"
        else "2" * 32
    )
    with pytest.raises(c.Stage12Error):
        m.verify_current_facts(record, authority)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "bool",
        "expired",
        "not_yet",
        "scope",
        "test_flag",
        "pids",
        "live",
    ],
)
def test_facts_and_runtime_evidence_are_closed_current_and_test_separated(mutation):
    profile, plan, start, record, _ = m2_inputs()
    authority = SyntheticAuthority(profile, plan, start, record)
    if mutation == "missing":
        authority.observed.pop("membership_matches")
    elif mutation == "extra":
        authority.observed["requested_memory"] = m.MAX_JOB_BYTES
    elif mutation == "bool":
        authority.observed["pids_current"] = False
    elif mutation == "expired":
        authority.clock.advance(86400 * 10**9)
    elif mutation == "not_yet":
        authority.clock.advance(-1_000_000_000)
    elif mutation == "scope":
        authority.configuration_scope_sha256 = "f" * 64
    elif mutation == "test_flag":
        authority.test_only = False
    elif mutation == "pids":
        authority.observed["pids_current"] = 65
    else:
        record["evidence_origin"] = authority.record["evidence_origin"] = (
            "LIVE_KERNEL_EVIDENCE"
        )
    with pytest.raises(c.Stage12Error):
        m.verify_runtime(
            record, authority, dict(profile=profile, plan=plan, start=start)
        )


def test_old_strict_and_new_method_versions_cannot_adopt_each_other():
    profile, plan, start, record, strict = m2_inputs()
    old_profile, _, old_start, *_ = ap_inputs()
    old_profile["sampling_runtime_bound_sha256"] = old.digest(record)
    with pytest.raises(c.Stage12Error):
        old.validate_bound(record, old_profile, old_start)
    profile["sampling_runtime_bound_sha256"] = a.digest(strict)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(strict, profile, start)
    for version in (a.PROFILE, a.START, a.REPORT, a.SNAPSHOT):
        assert a.SCHEMAS[version]["sampling_assurance_method"] == "=" + m.METHOD
    assert a.POLICY["supplementary_chunk_rows"] == 56
    assert a.POLICY["logical_component_memory_bytes"] == 16777216
    assert "incremental_component_memory_bytes" not in a.POLICY


def test_public_acyclic_configuration_binding_keeps_work_and_resource_content():
    profile, plan, start, record, _ = m2_inputs()
    config = dict(
        campaigns=[dict(profile=profile, plan=plan, work=[dict(synthetic_work=1)])],
        resources=dict(allocated_disk_bytes=2**30),
    )
    expected = m.configuration_scope(config)
    changed = deepcopy(config)
    changed["campaigns"][0]["profile"]["sampling_runtime_bound_sha256"] = "f" * 64
    changed["campaigns"][0]["plan"]["operations_profile_sha256"] = a.digest(
        changed["campaigns"][0]["profile"]
    )
    assert m.configuration_scope(changed) == expected
    changed["campaigns"][0]["work"][0]["synthetic_work"] = 2
    assert m.configuration_scope(changed) != expected


class Kernel:
    """Only invented kernel paths; unsupported access is an assertion failure."""

    def __init__(self):
        self.mount, self.parent, self.root = (
            "/sys/fs/cgroup",
            "/sys/fs/cgroup/synthetic",
            "/sys/fs/cgroup/synthetic/job",
        )
        self.nodes = {
            name: NS(
                st_mode=stat.S_IFDIR | 0o755, st_uid=0, st_gid=0, st_dev=71, st_ino=ino
            )
            for name, ino in ((self.mount, 97), (self.parent, 98), (self.root, 99))
        }
        self.nodes.update(
            {"/proc/self/ns/cgroup": NS(st_ino=61), "/proc/self/ns/mnt": NS(st_ino=62)}
        )
        self.reads = {}
        for path in (self.root, self.parent):
            for name, value in (
                ("memory.max", str(m.MAX_JOB_BYTES)),
                ("memory.swap.max", "0"),
                ("pids.max", "64"),
            ):
                self.reads[path + "/" + name] = value
        self.reads.update(
            {
                self.root + "/pids.current": "4",
                "/proc/self/cgroup": "0::/synthetic/job",
                "/proc/self/status": "Pid:\t4242\nCapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapInh:\t0000000000000000\nCapAmb:\t0000000000000000\nCapBnd:\t000001ffffffffff\nNoNewPrivs:\t1",
                "/proc/sys/kernel/random/boot_id": "11111111-1111-1111-1111-111111111111",
            }
        )
        self.lines = {
            "/proc/self/mountinfo": [
                "29 23 0:26 / /sys/fs/cgroup rw,nosuid,nodev,noexec - cgroup2 cgroup rw"
            ],
            self.root + "/cgroup.procs": ["4242"],
        }
        self.writable = set()
        self.on_read = lambda path: None
        self.on_stat = lambda path: None

    def install(self, monkeypatch):
        kernel = self

        class FakePath:
            def __init__(self, value):
                self.value = PurePosixPath(str(value))

            def __str__(self):
                return str(self.value)

            def __truediv__(self, other):
                return FakePath(self.value / other)

            def __eq__(self, other):
                return isinstance(other, FakePath) and self.value == other.value

            @property
            def parent(self):
                return FakePath(self.value.parent)

            def relative_to(self, other):
                return self.value.relative_to(other.value)

            def resolve(self, *, strict):
                assert strict is True
                return self

            def stat(self, **_):
                path = str(self)
                kernel.on_stat(path)
                assert path in kernel.nodes, "UNEXPECTED_KERNEL_STAT"
                return deepcopy(kernel.nodes[path])

        def read(path, maximum=2048):
            path = str(path)
            kernel.on_read(path)
            if path not in kernel.reads:
                raise FileNotFoundError("SYNTHETIC_MISSING_KERNEL_KNOB")
            raw = kernel.reads[path]
            assert len(raw) <= maximum
            return raw

        def lines(path):
            path = str(path)
            assert path in kernel.lines, "UNEXPECTED_KERNEL_LINES"
            yield from kernel.lines[path]

        monkeypatch.setattr(m, "Path", FakePath)
        monkeypatch.setattr(m.sys, "platform", "linux")
        monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
        monkeypatch.setattr(m.os, "getpid", lambda: 4242)
        monkeypatch.setattr(
            m.os, "access", lambda path, flag: str(path) in kernel.writable
        )
        monkeypatch.setattr(m, "_kernel_read", read)
        monkeypatch.setattr(m, "_kernel_lines", lines)
        return self


@pytest.fixture
def kernel(monkeypatch):
    return Kernel().install(monkeypatch)


def test_mocked_kernel_root_knob_absence_is_allowed_with_finite_ancestors(kernel):
    *_, record, strict = m2_inputs()
    observed = m.observe_linux_domain(record["domain"])
    assert observed == facts(record)


@pytest.mark.parametrize("name", ["memory.max", "memory.swap.max", "pids.max"])
def test_nonroot_missing_limit_never_becomes_an_unbounded_default(kernel, name):
    *_, record, strict = m2_inputs()
    kernel.reads.pop(kernel.parent + "/" + name)
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


@pytest.mark.parametrize(
    "mutation",
    [
        "subtree_mount",
        "wrong_mount_type",
        "duplicate_mount",
        "wrong_membership",
        "wrong_actual_pid",
        "capabilities",
        "no_new_privs",
        "delegated",
        "no_memory",
        "soft_high",
        "large_memory",
        "swap",
    ],
)
def test_mocked_kernel_rejects_incomplete_or_escape_capable_enforcement(
    kernel, mutation
):
    *_, record, strict = m2_inputs()
    if mutation == "subtree_mount":
        kernel.lines["/proc/self/mountinfo"][0] = kernel.lines["/proc/self/mountinfo"][
            0
        ].replace("0:26 / /sys", "0:26 /hidden /sys")
    elif mutation == "wrong_mount_type":
        kernel.lines["/proc/self/mountinfo"][0] = kernel.lines["/proc/self/mountinfo"][
            0
        ].replace(" - cgroup2 ", " - tmpfs ")
    elif mutation == "duplicate_mount":
        kernel.lines["/proc/self/mountinfo"] *= 2
    elif mutation == "wrong_membership":
        kernel.reads["/proc/self/cgroup"] = "0::/other/job"
    elif mutation == "wrong_actual_pid":
        kernel.lines[kernel.root + "/cgroup.procs"] = ["1", "4243"]
    elif mutation == "capabilities":
        kernel.reads["/proc/self/status"] = kernel.reads["/proc/self/status"].replace(
            "CapEff:\t0000000000000000", "CapEff:\t0000000000000001"
        )
    elif mutation == "no_new_privs":
        kernel.reads["/proc/self/status"] = kernel.reads["/proc/self/status"].replace(
            "NoNewPrivs:\t1", "NoNewPrivs:\t0"
        )
    elif mutation == "delegated":
        kernel.writable.add(kernel.parent + "/cgroup.procs")
    else:
        for path in (kernel.root, kernel.parent):
            if mutation in ("no_memory", "soft_high"):
                kernel.reads[path + "/memory.max"] = "max"
                kernel.reads[path + "/memory.high"] = str(m.MAX_JOB_BYTES)
            elif mutation == "large_memory":
                kernel.reads[path + "/memory.max"] = str(12 * 2**30)
            else:
                kernel.reads[path + "/memory.swap.max"] = "1"
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


@pytest.mark.parametrize("target", ["root", "ancestor"])
def test_kernel_domain_and_ancestor_replacement_during_acquisition_reject(
    kernel, target
):
    *_, record, strict = m2_inputs()

    def mutate(path):
        if path == "/proc/self/status":
            changed = kernel.root if target == "root" else kernel.parent
            kernel.nodes[changed].st_ino += 100

    kernel.on_read = mutate
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


def test_kernel_ancestor_scan_has_a_finite_depth_bound(kernel):
    *_, record, strict = m2_inputs()
    path = kernel.mount
    for index in range(34):
        path += "/d"
        kernel.nodes[path] = NS(
            st_mode=stat.S_IFDIR | 0o755,
            st_uid=0,
            st_gid=0,
            st_dev=71,
            st_ino=100 + index,
        )
    binding = {**record["domain"], "path": path}
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(binding)


@pytest.mark.parametrize(
    "bad_status",
    [
        "CapEff:\tzz\nNoNewPrivs:\t1",
        "CapEff:\nNoNewPrivs:\t1",
        "CapEff:\t0\nCapEff:\t0\nNoNewPrivs:\t1",
        "CapEff:\t0",
    ],
)
def test_kernel_status_malformed_caps_and_privilege_fields_are_static_rejections(
    kernel, bad_status
):
    *_, record, strict = m2_inputs()
    kernel.reads["/proc/self/status"] = bad_status
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


def test_original_kernel_reader_handles_short_reads_and_rejects_one_extra_byte(
    monkeypatch,
):
    payload = bytearray(b"64\n")
    closed = []
    monkeypatch.setattr(m.os, "open", lambda path, flags: 77)
    info = NS(st_mode=stat.S_IFREG | 0o444, st_uid=0, st_gid=0, st_dev=71, st_ino=99)
    monkeypatch.setattr(m.os, "fstat", lambda fd: deepcopy(info))
    monkeypatch.setattr(m, "Path", lambda path: NS(stat=lambda **kw: deepcopy(info)))
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(m.os, "close", closed.append)

    def read(fd, maximum):
        part = bytes(payload[: min(1, maximum)])
        del payload[: len(part)]
        return part

    monkeypatch.setattr(m.os, "read", read)
    assert m._kernel_read("/synthetic/kernel", 64) == "64"
    payload[:] = b"x" * 65
    with pytest.raises(c.Stage12Error):
        m._kernel_read("/synthetic/kernel", 64)
    assert closed == [77, 77]


def test_scratch_partitions_are_finite_exclusive_and_do_not_claim_native_bounds():
    assert sum(scratch.CAPS.values()) == 63616 <= 65536
    with scratch.lease("TIMING", requested=38912):
        with scratch.lease("EVENT", requested=8256):
            with pytest.raises(c.Stage12Error, match="WF_AP2_SCRATCH_REENTRANT"):
                with scratch.lease("TIMING"):
                    pass
    for requested in (38913, True, -1):
        with pytest.raises(c.Stage12Error):
            with scratch.lease("TIMING", requested=requested):
                pass
    entered, release, other = threading.Event(), threading.Event(), threading.Event()

    def holder():
        with scratch.lease("TIMING"):
            entered.set()
            assert release.wait(2)

    def contender():
        with scratch.lease("TIMING"):
            other.set()

    first, second = threading.Thread(target=holder), threading.Thread(target=contender)
    first.start()
    assert entered.wait(2)
    second.start()
    try:
        assert not other.wait(0.02)
    finally:
        release.set()
        first.join(2)
        second.join(2)
    assert other.is_set() and not first.is_alive() and not second.is_alive()


def test_enforcement_check_budget_is_cumulative_and_failed_observation_keeps_charge():
    profile, plan, start, record, _ = m2_inputs()
    record["maximum_enforcement_checks"] = 1
    repin(profile, plan, start, record)
    authority = SyntheticAuthority(profile, plan, start, record)
    authority.observed["no_capabilities"] = False
    with pytest.raises(c.Stage12Error):
        m.verify_current_facts(record, authority)
    assert authority.enforcement_checks == 1
    authority.observed["no_capabilities"] = True
    calls = []
    authority.enforcement_facts = lambda rec: calls.append(rec) or facts(rec)
    with pytest.raises(c.Stage12Error):
        m.verify_current_facts(record, authority)
    assert authority.enforcement_checks == 2 and not calls


@pytest.mark.parametrize("namespace", ["/proc/self/ns/cgroup", "/proc/self/ns/mnt"])
def test_kernel_namespace_switch_during_observation_is_rejected(kernel, namespace):
    *_, record, strict = m2_inputs()

    def mutate(path):
        if path == "/proc/self/status":
            kernel.nodes[namespace].st_ino += 10

    kernel.on_read = mutate
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


@pytest.mark.parametrize(
    "knob,value",
    [("memory.max", str(12 * 2**30)), ("memory.swap.max", "1"), ("pids.max", "128")],
)
def test_changed_effective_ancestor_limit_is_freshly_rejected(kernel, knob, value):
    *_, record, strict = m2_inputs()

    def mutate(path):
        if path == kernel.root + "/pids.current":
            for ancestor in (kernel.root, kernel.parent):
                kernel.reads[ancestor + "/" + knob] = value

    kernel.on_read = mutate
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


@pytest.mark.parametrize(
    "field",
    [
        "sampling_policy_sha256",
        "client_git_sha",
        "runtime_inventory_sha256",
        "configuration_scope_sha256",
        "invocation_graph_sha256",
        "technical_review_record_sha256",
        "enforcement_evidence_sha256",
        "domain_coverage_evidence_sha256",
    ],
)
def test_no_zero_identity_or_evidence_hash_can_issue_a_record(field):
    profile, plan, start, record, _ = m2_inputs()
    record[field] = "0" * len(record[field])
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


def test_public_profile_start_and_plan_keep_closed_method_and_history_contracts():
    profile, plan, start, record, _ = m2_inputs()
    a.validate_profile(profile)
    a.validate_plan(plan, profile)
    a.validate(start, a.START)
    for field, value in [
        ("sampling_assurance_method", "CLOSED_ALLOCATION_INVENTORY"),
        ("unknown", 1),
        ("sampling_runtime_bound_sha256", None),
    ]:
        changed = deepcopy(profile)
        changed[field] = value
        with pytest.raises(c.Stage12Error):
            a.validate_profile(changed)
    changed = deepcopy(start)
    changed.pop("sampling_assurance_method")
    with pytest.raises(c.Stage12Error):
        a.validate(changed, a.START)
    raw = c.canonical(profile).replace(
        b'"scope":', b'"scope":"PUBLIC_SYNTHETIC_ONLY","scope":'
    )
    with pytest.raises(c.Stage12Error):
        a.parse(raw, a.PROFILE)
    for field in (
        "additional_event_tokens",
        "additional_file_data_bytes",
        "additional_file_entries",
    ):
        changed = deepcopy(plan)
        changed["sampling_budget"][field] = 1
        with pytest.raises(c.Stage12Error):
            a.validate_plan(changed, profile)
    changed = deepcopy(plan)
    changed["history_limits"]["page_entries"] = 513
    with pytest.raises(c.Stage12Error):
        a.validate_plan(changed, profile)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "unsorted", "too_many"])
def test_method_evidence_is_finite_unique_and_canonical(mutation):
    profile, plan, start, record, _ = m2_inputs()
    if mutation == "empty":
        selected = []
    elif mutation == "duplicate":
        selected = [H, H]
    elif mutation == "unsorted":
        selected = sorted([H, evidence("second")], reverse=True)
    else:
        selected = sorted(evidence(str(index)) for index in range(17))
    record["method_evidence_sha256"] = selected
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


@pytest.mark.parametrize(
    "field", ["maximum_enforcement_checks", "maximum_runtime_inventory_checks"]
)
@pytest.mark.parametrize("mutation", ["zero", "missing"])
def test_finite_precharged_check_counters_are_mandatory_positive_fields(
    field, mutation
):
    profile, plan, start, record, _ = m2_inputs()
    if mutation == "zero":
        record[field] = 0
    else:
        record.pop(field)
    repin(profile, plan, start, record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, profile, start)


@pytest.mark.parametrize(
    "payload", [b"x" * 2048 + b"\n", b"unterminated", b"x\n" * 4097]
)
def test_original_kernel_line_reader_rejects_oversized_unterminated_or_excess_rows(
    monkeypatch, payload
):
    info = NS(st_mode=stat.S_IFREG | 0o444, st_uid=0, st_gid=0, st_dev=71, st_ino=99)
    closed = []
    monkeypatch.setattr(m.os, "open", lambda path, flags: 77)
    monkeypatch.setattr(m.os, "fstat", lambda fd: deepcopy(info))
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(m.os, "close", closed.append)
    monkeypatch.setattr(m.os, "fdopen", lambda *args, **kwargs: io.BytesIO(payload))
    monkeypatch.setattr(m, "Path", lambda path: NS(stat=lambda **kw: deepcopy(info)))
    with pytest.raises(c.Stage12Error):
        list(m._kernel_lines("/synthetic/kernel"))
    assert closed == [77]


@pytest.mark.parametrize("field", ["CapEff", "CapPrm", "CapInh", "CapAmb"])
@pytest.mark.parametrize("mutation", ["nonzero", "missing"])
def test_kernel_capability_sets_cannot_be_restored_after_nnp(kernel, field, mutation):
    *_, record, strict = m2_inputs()
    status = kernel.reads["/proc/self/status"]
    if mutation == "nonzero":
        status = status.replace(
            field + ":\t0000000000000000", field + ":\t0000000000000001"
        )
    else:
        status = "\n".join(
            line for line in status.splitlines() if not line.startswith(field + ":")
        )
    kernel.reads["/proc/self/status"] = status
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


def test_nonzero_capability_bounding_ceiling_alone_is_not_effective_authority(kernel):
    *_, record, strict = m2_inputs()
    assert "CapBnd:\t000001ffffffffff" in kernel.reads["/proc/self/status"]
    observed = m.observe_linux_domain(record["domain"])
    assert observed["no_capabilities"] and observed["no_new_privileges"]


def test_original_kernel_line_reader_rechecks_identity_when_consumer_closes_early(
    monkeypatch,
):
    info = NS(st_mode=stat.S_IFREG | 0o444, st_uid=0, st_gid=0, st_dev=71, st_ino=99)
    closed = []
    monkeypatch.setattr(m.os, "open", lambda path, flags: 77)
    monkeypatch.setattr(m.os, "fstat", lambda fd: deepcopy(info))
    monkeypatch.setattr(m.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(m.os, "close", closed.append)
    monkeypatch.setattr(
        m.os, "fdopen", lambda *args, **kwargs: io.BytesIO(b"one\ntwo\n")
    )
    monkeypatch.setattr(m, "Path", lambda path: NS(stat=lambda **kw: deepcopy(info)))
    stream = m._kernel_lines("/synthetic/kernel")
    assert next(stream) == "one"
    info.st_ino += 1
    with pytest.raises(c.Stage12Error, match="WF_AP2_KERNEL_CHANGED"):
        stream.close()
    assert closed == [77]

"""Invented proc/mount facts only; no host cgroup or quota access."""

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest


SPEC = spec_from_file_location(
    "stage12_native_enforcement_observer",
    Path(__file__).resolve().parents[1]
    / "scripts/stage12_native_enforcement_observer.py",
)
observer = module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


@pytest.fixture
def host(tmp_path, monkeypatch):
    proc = tmp_path / "proc_self"
    cgroup = tmp_path / "sys_cgroup"
    work = tmp_path / "controlled"
    for path in (proc, cgroup, work):
        path.mkdir()
    for key in ("TMPDIR", "TMP", "TEMP", "SQLITE_TMPDIR", "DUCKDB_TMP_DIRECTORY"):
        monkeypatch.delenv(key, raising=False)
    (proc / "limits").write_text(
        "Limit                     Soft Limit           Hard Limit           Units\n"
        "Max resident set          unlimited            unlimited            bytes\n"
        "Max address space         12345                45678                bytes\n"
        "Max file size             4096                 8192                 bytes\n"
    )
    (proc / "status").write_text(
        "Name:\tnever-emit-this-name\nVmRSS:\t12 kB\nVmHWM:\t20 kB\n"
    )
    return proc, cgroup, work


def collect(host, *, paths=None):
    proc, cgroup, work = host
    return observer._collect(
        reader=observer._Reader(proc_root=proc, sys_root=cgroup),
        workspace_root=work,
        runtime_paths=paths or {},
        requested_slurm_memory_bytes=6 * 2**30,
        allowed_roots=(work,),
        pid=123,
    )


def v2(host, *, root="/", member="/slurm/job_17/step_batch"):
    proc, cgroup, work = host
    (proc / "mountinfo").write_text(
        f"1 0 0:30 {root} {cgroup} rw - cgroup2 cgroup rw\n"
        f"2 0 0:40 / {work} rw - panfs panfs rw\n"
    )
    (proc / "cgroup").write_text(f"0::{member}\n")
    node = cgroup / Path(member).relative_to(root)
    leaf = node
    while True:
        node.mkdir(parents=True, exist_ok=True)
        values = {
            "memory.max": "max",
            "memory.high": "max",
            "memory.current": "1024",
            "memory.peak": "2048",
            "memory.events": "high 2\noom 0\noom_kill 0\nsecret 88\n",
            "memory.events.local": "oom_kill 0\n",
            "memory.oom.group": "1",
            "memory.swap.max": "0",
        }
        for name, value in values.items():
            (node / name).write_text(value)
        if node == cgroup:
            break
        node = node.parent
    (leaf / "cgroup.procs").write_text("123\n987\n")
    return leaf


def test_v2_effective_ancestor_limit_and_requested_memory_remain_distinct(host):
    leaf = v2(host)
    (leaf / "memory.max").write_text(str(8 * 2**30))
    (leaf.parent / "memory.max").write_text(str(7 * 2**30))
    result = collect(host)
    memory = result["memory"]
    assert result["requested_slurm_memory_bytes"] == 6 * 2**30
    assert memory["visible_hierarchy_hard_limit_bytes"] == 7 * 2**30
    assert memory["observed_finite_ceiling_bytes"] == 7 * 2**30
    assert memory["effective_hard_limit_bytes"] is None
    assert memory["hidden_ancestors_outside_mount"] is None
    assert memory["effective_hard_limit_status"] == "UNKNOWN_NAMESPACE_HOST_ROOT_SCOPE"
    assert memory["limiting_visible_controller_path"] == str(leaf.parent)
    assert memory["membership_pid_present"] is True
    assert memory["oom_completion_guaranteed"] is False
    assert result["proc_memory"] == {"VmRSS_bytes": 12 * 1024, "VmHWM_bytes": 20 * 1024}
    encoded = observer._encode(result)
    assert b"never-emit-this-name" not in encoded and b"secret" not in encoded
    assert len(encoded) < observer.MAX_OUTPUT_BYTES


def test_absent_membership_or_unreadable_hard_limit_is_unknown(host):
    leaf = v2(host)
    (leaf / "memory.max").write_text("4096")
    (leaf.parent / "memory.max").unlink()
    result = collect(host)["memory"]
    assert result["observed_finite_ceiling_bytes"] == 4096
    assert result["effective_hard_limit_bytes"] is None
    (leaf / "cgroup.procs").write_text("987\n")
    result = collect(host)["memory"]
    assert result["effective_hard_limit_bytes"] is None
    assert result["observed_finite_ceiling_bytes"] is None


def test_hidden_ancestor_domain_is_not_complete_effective_limit(host):
    leaf = v2(host, root="/slurm", member="/slurm/job_17/step_batch")
    (leaf / "memory.max").write_text("4096")
    result = collect(host)["memory"]
    assert result["observed_finite_ceiling_bytes"] == 4096
    assert result["hidden_ancestors_outside_mount"] is True
    assert result["effective_hard_limit_bytes"] is None


def test_v1_hierarchy_and_kernel_unlimited_sentinel(host):
    proc, cgroup, work = host
    leaf = cgroup / "slurm/job_17"
    leaf.mkdir(parents=True)
    (proc / "mountinfo").write_text(
        f"1 0 0:30 / {cgroup} rw - cgroup cgroup rw,memory\n"
    )
    (proc / "cgroup").write_text("4:memory:/slurm/job_17\n")
    for node in (leaf, leaf.parent, cgroup):
        for name in observer.V1_FILES:
            (node / name).write_text("0")
        (node / "memory.use_hierarchy").write_text("1")
        (node / "memory.limit_in_bytes").write_text(str(2**63 - 4096))
        (node / "memory.oom_control").write_text(
            "oom_kill_disable 0\nunder_oom 0\noom_kill 0\n"
        )
        (node / "memory.stat").write_text("hierarchical_memory_limit 8192\nrss 1000\n")
    (leaf / "memory.limit_in_bytes").write_text("16384")
    (leaf.parent / "memory.limit_in_bytes").write_text("8192")
    (leaf / "cgroup.procs").write_text("123\n")
    memory = collect(host)["memory"]
    assert memory["version"] == 1
    assert memory["visible_hierarchy_hard_limit_bytes"] == 8192
    (leaf.parent / "memory.use_hierarchy").write_text("0")
    assert collect(host)["memory"]["visible_hierarchy_hard_limit_bytes"] == 16384


def test_hybrid_inactive_v2_mount_does_not_hide_v1_memory_controller(host):
    proc, cgroup, work = host
    inactive = cgroup / "unified"
    active = cgroup / "memory"
    inactive.mkdir()
    active.mkdir()
    leaf = active / "slurm/job_17"
    leaf.mkdir(parents=True)
    (proc / "mountinfo").write_text(
        f"1 0 0:30 / {inactive} rw - cgroup2 cgroup rw\n"
        f"2 0 0:31 / {active} rw - cgroup cgroup rw,memory\n"
    )
    (proc / "cgroup").write_text("0::/system.slice\n4:memory:/slurm/job_17\n")
    for node in (leaf, leaf.parent, active):
        for name in observer.V1_FILES:
            (node / name).write_text("0")
        (node / "memory.use_hierarchy").write_text("1")
        (node / "memory.limit_in_bytes").write_text("8192")
    (leaf / "cgroup.procs").write_text("123\n")
    result = collect(host)["memory"]
    assert result["version"] == 1
    assert result["visible_hierarchy_hard_limit_bytes"] == 8192
    assert result["candidate_memory_controller_checks"][0]["version"] == 2
    assert (
        result["candidate_memory_controller_checks"][0]["hard_limit_read_status"]
        == "UNKNOWN_UNAVAILABLE"
    )


def test_no_matching_memory_mount_and_wrong_membership_never_guessed(host):
    proc, cgroup, _ = host
    (proc / "mountinfo").write_text(
        f"1 0 0:30 /other {cgroup} rw - cgroup2 cgroup rw\n"
    )
    (proc / "cgroup").write_text("0::/slurm/job_17\n")
    assert collect(host)["memory"]["status"] == "UNKNOWN_MEMBERSHIP_MOUNT_BINDING"


def test_filesystem_available_is_not_quota_or_entitlement_and_env_is_scoped(
    host, monkeypatch
):
    _, _, work = host
    v2(host)
    monkeypatch.setenv("TMPDIR", str(work / "temp"))
    monkeypatch.setenv("SQLITE_TMPDIR", "/not-allowlisted/never-emit-this")
    monkeypatch.setenv("API_KEY", "must-not-be-read-or-emitted")
    report = collect(host, paths={"duckdb_database": work / "future/database.duckdb"})
    disk = report["filesystem_paths"]["duckdb_database"]
    assert disk["statvfs_path"] == str(work)
    assert disk["capacity_entitlement_or_reservation_proved"] is False
    assert disk["aggregate_byte_inode_enforcement_proved"] is False
    assert (
        report["quota"]["byte_hard"] is None and report["quota"]["inode_hard"] is None
    )
    assert report["quota"]["no_results_means_unlimited"] is False
    assert report["temporary_environment"]["TMPDIR"]["path"] == str(work / "temp")
    encoded = json.dumps(report)
    assert (
        "never-emit-this" not in encoded
        and "must-not-be-read-or-emitted" not in encoded
    )


def test_runtime_roles_outside_root_and_symlink_escape_are_rejected_or_unknown(
    host, tmp_path
):
    _, _, work = host
    v2(host)
    with pytest.raises(ValueError, match="NATIVE_RUNTIME_ROLE_REJECTED"):
        collect(host, paths={"arbitrary": work / "x"})
    with pytest.raises(ValueError, match="NATIVE_RUNTIME_PATH_REJECTED"):
        collect(host, paths={"sqlite_temp": tmp_path / "x"})
    (work / "escape").symlink_to(tmp_path, target_is_directory=True)
    disk = collect(host, paths={"sqlite_temp": work / "escape/file"})[
        "filesystem_paths"
    ]["sqlite_temp"]
    assert disk["status"] == "UNKNOWN_PATH_OUTSIDE_CONTROLLED_ROOT"


def test_read_allowlist_and_single_file_read_bound(host):
    proc, cgroup, work = host
    reader = observer._Reader(proc_root=proc, sys_root=cgroup)
    with pytest.raises(ValueError, match="NATIVE_READ_REJECTED"):
        reader.read(proc / "environ")
    with pytest.raises(ValueError, match="NATIVE_READ_REJECTED"):
        reader.read(work / "memory.max")
    (proc / "status").write_bytes(b"x" * (observer.MAX_READ_BYTES + 1))
    assert reader.read(proc / "status") == (None, "UNKNOWN_READ_LIMIT")


def test_deadline_is_static_and_limits_preserve_linux_meanings(host):
    reader = observer._Reader(proc_root=host[0], sys_root=host[1])
    reader.started -= observer.MAX_SECONDS + 1
    with pytest.raises(observer.ObservationLimit, match="NATIVE_OBSERVATION_DEADLINE"):
        reader.check()
    parsed = observer._limits((host[0] / "limits").read_text(), "OBSERVED")
    assert parsed["values"]["Max resident set"]["hard"] == "UNLIMITED_AT_RLIMIT"
    assert parsed["values"]["Max address space"]["hard"] == 45678
    assert (
        parsed["rlimit_fsize_is_per_file_not_aggregate_storage_or_inode_limit"] is True
    )


def test_public_entry_requires_shared_goethe_guard(monkeypatch, host):
    from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError

    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        observer.collect_native_enforcement(host[2])

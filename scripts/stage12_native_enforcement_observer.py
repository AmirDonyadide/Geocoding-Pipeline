"""Read-only, bounded kernel/filesystem observations for one no-service job.

This does not run a workload, open a database, infer storage entitlement, or
prove successful cleanup after an OOM kill. Call ``collect_native_enforcement``
inside the parent diagnostic's network/provider/subprocess denial. Only the CLI
creates one exclusive 0600 JSON report; collection itself creates no files.
No generic subprocess, proc-path, environment-dump or source-input interface is
provided. Metadata reads are allowlisted and bounded. A parent walltime watchdog
is still required for a kernel/filesystem call that does not return.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import resource
import sys
import time


MAX_OUTPUT_BYTES = 2**20
MAX_READ_BYTES = 2**16
MAX_TOTAL_READ_BYTES = 2**21
MAX_ANCESTORS = 32
MAX_SECONDS = 20
CONTROLLED_ROOTS = (
    Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline"),
    Path("/work/footprint/donyadidegan/safe_geocoding_pipeline"),
)
RUNTIME_ROLES = frozenset(
    {
        "duckdb_database",
        "duckdb_wal",
        "duckdb_spill",
        "sqlite_database",
        "sqlite_journal",
        "sqlite_wal",
        "sqlite_temp",
        "python_temp",
        "native_workspace",
    }
)
PROC_NAMES = frozenset({"limits", "cgroup", "mountinfo", "status"})
V2_FILES = (
    "memory.max",
    "memory.high",
    "memory.current",
    "memory.peak",
    "memory.events",
    "memory.events.local",
    "memory.oom.group",
    "memory.swap.max",
)
V1_FILES = (
    "memory.limit_in_bytes",
    "memory.soft_limit_in_bytes",
    "memory.usage_in_bytes",
    "memory.max_usage_in_bytes",
    "memory.failcnt",
    "memory.oom_control",
    "memory.use_hierarchy",
    "memory.stat",
    "memory.memsw.limit_in_bytes",
)
CGROUP_NAMES = frozenset((*V1_FILES, *V2_FILES, "cgroup.procs"))
LIMIT_NAMES = (
    "Max cpu time",
    "Max file size",
    "Max resident set",
    "Max address space",
    "Max locked memory",
    "Max data size",
    "Max open files",
)


class ObservationLimit(Exception):
    """Static error category; never expose exception text from the host."""


def _canonical(path: str | Path) -> Path:
    value = Path(path)
    if not value.is_absolute() or ".." in value.parts:
        raise ValueError("NATIVE_PATH_REJECTED")
    return value


def _below(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path == root or path.is_relative_to(root) for root in roots)


def _decode_mount(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), value)


def _mounts(raw: str) -> list[dict]:
    result = []
    for line in raw.splitlines():
        left, separator, right = line.partition(" - ")
        fields, tail = left.split(), right.split()
        if not separator or len(fields) < 6 or len(tail) < 3:
            continue
        try:
            root = str(_canonical(_decode_mount(fields[3])))
            mount = str(_canonical(_decode_mount(fields[4])))
        except ValueError:
            continue
        result.append(
            {
                "root": root,
                "mount": mount,
                "fs_type": tail[0],
                "options": set(fields[5].split(",")) | set(tail[2].split(",")),
            }
        )
    return result


def _memberships(raw: str) -> list[dict]:
    result = []
    for line in raw.splitlines():
        fields = line.split(":", 2)
        if len(fields) != 3 or not fields[0].isdigit():
            continue
        try:
            path = str(_canonical(fields[2]))
        except ValueError:
            continue
        result.append(
            {
                "hierarchy": int(fields[0]),
                "controllers": fields[1].split(","),
                "path": path,
            }
        )
    return result


class _Reader:
    def __init__(
        self, *, proc_root=Path("/proc/self"), sys_root=Path("/sys/fs/cgroup")
    ):
        self.proc_root, self.sys_root = Path(proc_root), Path(sys_root)
        self.total = 0
        self.started = time.monotonic()

    def check(self):
        if time.monotonic() - self.started >= MAX_SECONDS:
            raise ObservationLimit("NATIVE_OBSERVATION_DEADLINE")

    def read(self, path: Path) -> tuple[str | None, str]:
        self.check()
        if not (
            path.parent == self.proc_root
            and path.name in PROC_NAMES
            or _below(path, (self.sys_root,))
            and path.name in CGROUP_NAMES
        ):
            raise ValueError("NATIVE_READ_REJECTED")
        if self.total + MAX_READ_BYTES + 1 > MAX_TOTAL_READ_BYTES:
            raise ObservationLimit("NATIVE_OBSERVATION_READ_BUDGET")
        try:
            # Proc/cgroup files conventionally report st_size=0; bound the read,
            # never trust st_size and never emit arbitrary text from these files.
            with path.open("rb") as stream:
                raw = stream.read(MAX_READ_BYTES + 1)
            self.total += len(raw)
            if len(raw) > MAX_READ_BYTES:
                return None, "UNKNOWN_READ_LIMIT"
            return raw.decode("ascii", errors="strict"), "OBSERVED"
        except (OSError, UnicodeError):
            return None, "UNKNOWN_UNAVAILABLE"


def _number(raw: str | None, status: str, *, v1_hard=False) -> dict:
    if raw is None:
        return {"status": status, "value": None}
    value = raw.strip()
    if value == "max":
        return {"status": "NO_FINITE_LIMIT_AT_THIS_NODE", "value": None}
    if not value.isdigit():
        return {"status": "UNKNOWN_FORMAT", "value": None}
    amount = int(value)
    if v1_hard and amount >= (2**63 - 2**20):
        return {"status": "KERNEL_V1_UNLIMITED_SENTINEL", "value": None}
    return {"status": "OBSERVED", "value": amount}


def _pairs(raw: str | None, status: str, allowed: set[str]) -> dict:
    if raw is None:
        return {"status": status, "values": {}}
    values = {}
    for line in raw.splitlines():
        cells = line.split()
        if len(cells) == 2 and cells[0] in allowed and cells[1].isdigit():
            values[cells[0]] = int(cells[1])
    return {"status": "OBSERVED" if values else "UNKNOWN_FORMAT", "values": values}


def _memory(
    reader: _Reader, mounts: list[dict], memberships: list[dict], pid: int
) -> dict:
    matches = []
    for member in memberships:
        for mount in mounts:
            version = (
                2
                if mount["fs_type"] == "cgroup2" and member["controllers"] == [""]
                else 1
            )
            if version == 1 and not (
                mount["fs_type"] == "cgroup"
                and "memory" in member["controllers"]
                and "memory" in mount["options"]
            ):
                continue
            point, root, path = (
                Path(mount["mount"]),
                Path(mount["root"]),
                Path(member["path"]),
            )
            if not _below(point, (reader.sys_root,)) or not _below(path, (root,)):
                continue
            matches.append((version, mount, member, point / path.relative_to(root)))
    if not matches:
        return {
            "status": "UNKNOWN_MEMBERSHIP_MOUNT_BINDING",
            "effective_hard_limit_bytes": None,
        }
    # A hybrid host can expose a cgroup2 mount without its memory controller;
    # prefer a bound hierarchy that actually exposes the memory hard-limit file.
    # Otherwise retain unknown rather than guessing a mount or controller.
    matches.sort(key=lambda m: (m[0], len(m[1]["root"])), reverse=True)
    candidate_checks = []
    selected = None
    for candidate in matches:
        version, _, _, leaf = candidate
        name = "memory.max" if version == 2 else "memory.limit_in_bytes"
        raw, status = reader.read(leaf / name)
        hard = _number(raw, status, v1_hard=version == 1)
        candidate_checks.append(
            {
                "version": version,
                "leaf_controller_path": str(leaf),
                "hard_limit_read_status": hard["status"],
            }
        )
        if hard["status"] in {
            "OBSERVED",
            "NO_FINITE_LIMIT_AT_THIS_NODE",
            "KERNEL_V1_UNLIMITED_SENTINEL",
        }:
            selected = candidate
            break
    if selected is not None:
        matches = [selected]
    version, mount, member, leaf = matches[0]
    boundary = Path(mount["mount"])
    chain = []
    node = leaf
    complete = True
    while True:
        if len(chain) >= MAX_ANCESTORS:
            complete = False
            break
        values = {}
        for name in V2_FILES if version == 2 else V1_FILES:
            raw, status = reader.read(node / name)
            if name.startswith("memory.events"):
                values[name] = _pairs(
                    raw,
                    status,
                    {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"},
                )
            elif name == "memory.oom_control":
                values[name] = _pairs(
                    raw, status, {"oom_kill_disable", "under_oom", "oom_kill"}
                )
            elif name == "memory.stat":
                values[name] = _pairs(
                    raw,
                    status,
                    {"hierarchical_memory_limit", "hierarchical_memsw_limit"},
                )
            else:
                values[name] = _number(
                    raw,
                    status,
                    v1_hard=name
                    in {"memory.limit_in_bytes", "memory.memsw.limit_in_bytes"},
                )
        chain.append({"controller_path": str(node), "values": values})
        if node == boundary:
            break
        node = node.parent
    raw, member_status = reader.read(leaf / "cgroup.procs")
    process_present = (
        pid in {int(x) for x in raw.split() if x.isdigit()} if raw is not None else None
    )
    hard_name = "memory.max" if version == 2 else "memory.limit_in_bytes"
    finite = []
    unknown = not complete
    for index, entry in enumerate(chain):
        if version == 1 and index > 0:
            hierarchy = entry["values"]["memory.use_hierarchy"]
            if hierarchy["status"] != "OBSERVED":
                unknown = True
                continue
            if hierarchy["value"] != 1:
                continue
        hard = entry["values"][hard_name]
        if hard["status"] == "OBSERVED":
            finite.append((hard["value"], entry["controller_path"]))
        elif hard["status"] not in {
            "NO_FINITE_LIMIT_AT_THIS_NODE",
            "KERNEL_V1_UNLIMITED_SENTINEL",
        }:
            unknown = True
    binding = process_present is True
    ceiling = min(finite) if finite else None
    return {
        "status": "OBSERVED" if binding else "UNKNOWN_PROCESS_MEMBERSHIP_CONFIRMATION",
        "version": version,
        "candidate_memory_controller_checks": candidate_checks,
        "membership_path": member["path"],
        "mount_root": mount["root"],
        "mount_point": mount["mount"],
        "leaf_controller_path": str(leaf),
        "membership_pid_present": process_present,
        "membership_read_status": member_status,
        "visible_ancestor_chain_complete": complete,
        "hidden_ancestors_outside_mount": True if mount["root"] != "/" else None,
        "namespace_host_root_scope_status": "UNKNOWN_NOT_INDEPENDENTLY_ESTABLISHED",
        "ancestors": chain,
        "observed_finite_ceiling_bytes": ceiling[0] if ceiling and binding else None,
        "limiting_visible_controller_path": ceiling[1] if ceiling and binding else None,
        "visible_hierarchy_hard_limit_bytes": ceiling[0]
        if ceiling and binding and not unknown
        else None,
        "effective_hard_limit_bytes": None,
        "effective_hard_limit_status": "UNKNOWN_NAMESPACE_HOST_ROOT_SCOPE",
        "oom_completion_guaranteed": False,
        "interpretation": "Kernel containment may terminate processes; it does not guarantee a report, database closure, cleanup, publication or successful completion. memory.high is throttling, not the hard memory.max limit. A finite visible ceiling is not a reservation or successful-workload proof. Mount root '/' can be namespace-relative; hidden host ancestors may impose a lower limit. The exact global effective minimum remains unknown without independent namespace/host-root scope evidence.",
    }


def _limits(raw: str | None, status: str) -> dict:
    result = {"status": status, "values": {}}
    if raw is None:
        return result
    for line in raw.splitlines():
        for name in LIMIT_NAMES:
            if not line.startswith(name + " "):
                continue
            fields = line[len(name) :].split()
            if len(fields) < 2:
                continue

            def value(text):
                return (
                    int(text)
                    if text.isdigit()
                    else "UNLIMITED_AT_RLIMIT"
                    if text == "unlimited"
                    else "UNKNOWN"
                )

            result["values"][name] = {
                "soft": value(fields[0]),
                "hard": value(fields[1]),
                "units": fields[2]
                if len(fields) == 3 and fields[2] in {"bytes", "seconds", "files"}
                else "UNKNOWN",
            }
    result["linux_rlimit_rss_is_not_process_memory_containment"] = True
    result["rlimit_as_is_virtual_address_space_not_rss"] = True
    result["rlimit_fsize_is_per_file_not_aggregate_storage_or_inode_limit"] = True
    return result


def _filesystem(
    path: Path, mounts: list[dict], allowed: tuple[Path, ...], reader: _Reader, statvfs
) -> dict:
    reader.check()
    resolved = path.resolve(strict=False)
    if not _below(resolved, allowed):
        return {"status": "UNKNOWN_PATH_OUTSIDE_CONTROLLED_ROOT"}
    probe = resolved
    try:
        while not probe.exists() and _below(probe.parent, allowed):
            probe = probe.parent
        if not probe.exists():
            return {"status": "UNKNOWN_PATH_UNAVAILABLE", "declared_path": str(path)}
        resolved = probe.resolve(strict=True)
        if not _below(resolved, allowed):
            return {"status": "UNKNOWN_PATH_OUTSIDE_CONTROLLED_ROOT"}
        fs = statvfs(resolved)
        metadata = resolved.stat()
    except OSError:
        return {"status": "UNKNOWN_FILESYSTEM_METADATA", "declared_path": str(path)}
    candidates = [m for m in mounts if _below(resolved, (Path(m["mount"]),))]
    mount = max(candidates, key=lambda m: len(m["mount"])) if candidates else None
    return {
        "status": "OBSERVED",
        "declared_path": str(path),
        "statvfs_path": str(resolved),
        "path_already_exists": path.exists(),
        "st_dev": metadata.st_dev,
        "mount_point": mount["mount"] if mount else None,
        "mount_root": mount["root"] if mount else None,
        "fs_type": mount["fs_type"] if mount else None,
        "mount_quota_hints": sorted(
            mount["options"] & {"usrquota", "grpquota", "prjquota", "pquota", "quota"}
        )
        if mount
        else [],
        "fragment_size_bytes": fs.f_frsize,
        "block_size_bytes": fs.f_bsize,
        "filesystem_blocks": fs.f_blocks,
        "filesystem_free_blocks": fs.f_bfree,
        "available_blocks_for_unprivileged_user": fs.f_bavail,
        "filesystem_inodes": fs.f_files,
        "filesystem_free_inodes": fs.f_ffree,
        "available_inodes_for_unprivileged_user": fs.f_favail,
        "available_bytes_observed": fs.f_bavail * fs.f_frsize,
        "capacity_entitlement_or_reservation_proved": False,
        "aggregate_byte_inode_enforcement_proved": False,
        "metadata_and_unlinked_allocation_bound_proved": False,
    }


def _collect(
    *,
    reader,
    workspace_root,
    runtime_paths,
    requested_slurm_memory_bytes,
    allowed_roots,
    pid,
    statvfs=os.statvfs,
):
    root = _canonical(workspace_root)
    allowed = tuple(_canonical(p).resolve(strict=False) for p in allowed_roots)
    if not _below(root.resolve(strict=False), allowed):
        raise ValueError("NATIVE_WORKSPACE_REJECTED")
    if len(runtime_paths) > len(RUNTIME_ROLES) or set(runtime_paths) - RUNTIME_ROLES:
        raise ValueError("NATIVE_RUNTIME_ROLE_REJECTED")
    if requested_slurm_memory_bytes is not None and (
        type(requested_slurm_memory_bytes) is not int
        or requested_slurm_memory_bytes <= 0
    ):
        raise ValueError("NATIVE_REQUESTED_MEMORY_REJECTED")
    paths = {key: _canonical(value) for key, value in runtime_paths.items()}
    if any(not _below(path, (root,)) for path in paths.values()):
        raise ValueError("NATIVE_RUNTIME_PATH_REJECTED")
    mount_raw, mount_status = reader.read(reader.proc_root / "mountinfo")
    member_raw, member_status = reader.read(reader.proc_root / "cgroup")
    mounts = _mounts(mount_raw or "")
    members = _memberships(member_raw or "")
    limit_raw, limit_status = reader.read(reader.proc_root / "limits")
    status_raw, status_status = reader.read(reader.proc_root / "status")
    rss = {}
    for line in (status_raw or "").splitlines():
        cells = line.split()
        if (
            len(cells) == 3
            and cells[0] in {"VmPeak:", "VmSize:", "VmHWM:", "VmRSS:"}
            and cells[1].isdigit()
            and cells[2] == "kB"
        ):
            rss[cells[0][:-1] + "_bytes"] = int(cells[1]) * 1024
    memory = _memory(reader, mounts, members, pid)
    job_value = os.environ.get("SLURM_JOB_ID", "")
    slurm_job_id = int(job_value) if job_value.isdigit() else None
    member_path = memory.get("membership_path", "")
    environments = {}
    for key in ("TMPDIR", "TMP", "TEMP", "SQLITE_TMPDIR", "DUCKDB_TMP_DIRECTORY"):
        value = os.environ.get(key)
        if value is None:
            environments[key] = {"status": "UNSET_IN_THIS_PROCESS"}
            continue
        try:
            value_path = _canonical(value)
            environments[key] = (
                {"status": "OBSERVED_CONTROLLED_PATH", "path": str(value_path)}
                if _below(value_path.resolve(strict=False), allowed)
                else {"status": "SET_OUTSIDE_ALLOWLIST_VALUE_WITHHELD"}
            )
        except (ValueError, OSError):
            environments[key] = {"status": "SET_VALUE_WITHHELD"}
    filesystem = {"workspace": _filesystem(root, mounts, allowed, reader, statvfs)}
    for name, path in sorted(paths.items()):
        filesystem[name] = _filesystem(path, mounts, allowed, reader, statvfs)
        filesystem[name]["path_binding"] = "CALLER_DECLARED_NOT_ENGINE_VERIFIED"
    usage = resource.getrusage(resource.RUSAGE_SELF)
    report = {
        "schema_version": "stage12_native_enforcement_observation_v1",
        "scope": "READ_ONLY_METADATA_NO_SERVICE_NO_PROTECTED_INPUT",
        "observation_is_atomic": False,
        "observation_is_point_in_time_only": True,
        "pid": pid,
        "uid": os.getuid(),
        "gid": os.getgid(),
        "supplementary_gids": sorted(os.getgroups()),
        "slurm_job_id": slurm_job_id,
        "cgroup_path_contains_slurm_job_component": bool(
            slurm_job_id is not None
            and any(
                component in {f"job_{slurm_job_id}", f"job-{slurm_job_id}.scope"}
                for component in Path(member_path).parts
            )
        ),
        "requested_slurm_memory_bytes": requested_slurm_memory_bytes,
        "requested_slurm_memory_is_kernel_enforcement_evidence": False,
        "mountinfo_status": mount_status,
        "cgroup_membership_status": member_status,
        "memory": memory,
        "process_limits": _limits(limit_raw, limit_status),
        "proc_status_status": status_status,
        "proc_memory": rss,
        "getrusage_ru_maxrss_raw": usage.ru_maxrss,
        "getrusage_ru_maxrss_unit": "KiB"
        if sys.platform.startswith("linux")
        else "bytes"
        if sys.platform == "darwin"
        else "UNKNOWN",
        "filesystem_paths": filesystem,
        "runtime_path_roles_unprovided": sorted(RUNTIME_ROLES - set(paths)),
        "temporary_environment": environments,
        "temporary_environment_is_engine_path_confirmation": False,
        "deleted_open_native_files": {
            "status": "UNKNOWN_NOT_ENUMERATED",
            "enforcement_domain": "Depends on each actual backing filesystem; unlinked files can retain allocation until close. No FD or directory scan was performed.",
        },
        "quota": {
            "status": "UNKNOWN_REQUIRES_FINITE_PREDECLARED_EXTERNAL_METADATA",
            "user_uid": os.getuid(),
            "group_gid": os.getgid(),
            "project_id": None,
            "byte_current": None,
            "byte_soft": None,
            "byte_hard": None,
            "byte_grace": None,
            "inode_current": None,
            "inode_soft": None,
            "inode_hard": None,
            "inode_grace": None,
            "no_results_means_unlimited": False,
            "free_space_means_entitlement": False,
        },
        "no_executable_protected_resource_model_issued": True,
        "limits": {
            "seconds_cooperative": MAX_SECONDS,
            "parent_watchdog_required_for_blocked_kernel_io": True,
            "output_bytes": MAX_OUTPUT_BYTES,
            "output_files": 1,
            "read_bytes_per_file": MAX_READ_BYTES,
            "read_bytes_total": MAX_TOTAL_READ_BYTES,
            "ancestor_nodes": MAX_ANCESTORS,
        },
        "metadata_bytes_read": reader.total,
        "elapsed_ns": int((time.monotonic() - reader.started) * 1e9),
    }
    reader.check()
    if len(_encode(report)) > MAX_OUTPUT_BYTES:
        raise ObservationLimit("NATIVE_OBSERVATION_OUTPUT_BUDGET")
    return report


def collect_native_enforcement(
    workspace_root: Path,
    runtime_paths: dict[str, Path] | None = None,
    requested_slurm_memory_bytes: int | None = None,
) -> dict:
    """Observe this scheduled process; writes/opens no workload/native files.

    Runtime roles describe intended paths only. They must be independently
    reconciled to actual engine settings; no database is opened to manufacture
    such a reconciliation. Missing roles and unsupported quota facts stay unknown.
    """
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage12 read-only native enforcement observation")
    if not sys.platform.startswith("linux"):
        raise ValueError("NATIVE_LINUX_REQUIRED")
    return _collect(
        reader=_Reader(),
        workspace_root=workspace_root,
        runtime_paths=runtime_paths or {},
        requested_slurm_memory_bytes=requested_slurm_memory_bytes,
        allowed_roots=CONTROLLED_ROOTS,
        pid=os.getpid(),
    )


def _encode(report: dict) -> bytes:
    return (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--requested-slurm-memory-bytes", type=int)
    parser.add_argument(
        "--runtime-path", action="append", default=[], metavar="ROLE=PATH"
    )
    args = parser.parse_args()
    try:
        paths = {}
        for value in args.runtime_path:
            role, separator, path = value.partition("=")
            if not separator or role in paths:
                raise ValueError("NATIVE_RUNTIME_ROLE_REJECTED")
            paths[role] = Path(path)
        output = _canonical(args.output)
        root = _canonical(args.workspace_root)
        if output.parent != root or output.is_symlink():
            raise ValueError("NATIVE_OUTPUT_REJECTED")
        report = collect_native_enforcement(
            root, paths, args.requested_slurm_memory_bytes
        )
        payload = _encode(report)
        fd = os.open(
            output, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    except (ValueError, ObservationLimit, OSError, RuntimeError):
        print("NATIVE_OBSERVATION_FAILED_STATIC", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

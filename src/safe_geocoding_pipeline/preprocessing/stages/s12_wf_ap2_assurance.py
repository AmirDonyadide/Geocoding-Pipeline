"""WF-AP2 M2: logical arenas plus independently evidenced kernel job domain.

No native-inclusive component bound is asserted. This module reads enforcement;
it never changes cgroups, quotas, permissions or scheduler settings. Missing
competent coverage evidence, inaccessible ancestors or unsupported platforms
remain execution failures. Synthetic adapters are explicit test injection only.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import stat
import sys

from . import s12_public_operations as old
from . import s12_retrieval_contract as c

METHOD = "LOGICAL_ARENAS_AND_ENFORCED_JOB_DOMAIN"
BOUND = "stage12_public_sampling_runtime_bound_v2"
MAX_JOB_BYTES = 6 * 2**30
LOGICAL_BYTES = 16 * 2**20
SCRATCH_BYTES = 65536
ARENAS = (
    "SAMPLE_SLOTS",
    "HISTORY_PAGES",
    "TELEMETRY_RING",
    "SERIALIZATION_SCRATCH",
    "TRACE_METADATA",
    "CONTROLLER_METADATA",
    "OTHER_LOGICAL",
)
DOMAIN = {
    "path": "S",
    "device": "U",
    "inode": "P",
    "cgroup_namespace_inode": "P",
    "mount_namespace_inode": "P",
    "boot_id": "UUID",
    "memory_max_bytes": "P",
    "swap_max_bytes": "U",
    "pids_max": "P",
}
SCHEMA = {
    "schema_version": "=" + BOUND,
    "scope": old.enum("PUBLIC_SYNTHETIC_ONLY", "DEVELOPMENT_ONLY"),
    "method": "=" + METHOD,
    "sampling_policy_sha256": "D",
    "client_git_sha": "G",
    "runtime_inventory_sha256": "D",
    "configuration_scope_sha256": "D",
    "invocation_graph_sha256": "D",
    "maximum_enforcement_checks": "P",
    "maximum_runtime_inventory_checks": "P",
    "technical_review_record_sha256": "D",
    "enforcement_evidence_sha256": "D",
    "domain_coverage_evidence_sha256": "D",
    "method_evidence_sha256": ["D"],
    "evidence_origin": old.enum("LIVE_KERNEL_EVIDENCE", "SYNTHETIC_TEST_ONLY"),
    "valid_from": "Z",
    "valid_until": "Z",
    "logical_allocations": [
        {"name": old.enum(*ARENAS), "bytes": "U", "evidence_sha256": "D"}
    ],
    "total_logical_bytes": "P",
    "logical_scratch_bytes": "P",
    "native_component_guarantee": "=NOT_CLAIMED",
    "native_scratch_guarantee": "=NOT_CLAIMED",
    "domain": DOMAIN,
}
FACTS = {
    **DOMAIN,
    "membership_matches": "B",
    "nondelegated": "B",
    "no_capabilities": "B",
    "descendants_share_domain": "B",
    "no_new_privileges": "B",
    "pids_current": "U",
    "observation_origin": "=KERNEL_CGROUP_V2",
}


def shape(value, spec):
    if spec == "S":
        c.require(
            type(value) is str and value.isascii() and len(value) <= 1024,
            "WF_AP2_EVIDENCE_FIELDS",
        )
    elif spec == "UUID":
        c.require(
            type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None,
            "WF_AP2_EVIDENCE_FIELDS",
        )
    elif isinstance(spec, list):
        c.require(type(value) is list and len(value) <= 64, "WF_AP2_EVIDENCE_BOUND")
        for row in value:
            shape(row, spec[0])
    elif isinstance(spec, dict) and "enum" not in spec:
        c.require(
            type(value) is dict and set(value) == set(spec), "WF_AP2_EVIDENCE_FIELDS"
        )
        for key, child in spec.items():
            shape(value[key], child)
    else:
        old.validate_type(value, spec)
        if spec in ("D", "G"):
            c.require(set(value) != {"0"}, "WF_AP2_EVIDENCE_UNKNOWN")


def configuration_scope(config, *, plan=None):
    """Exact acyclic projection; complete config still needs its genuine grant.

    Only the later grant/bound/SlotBinding pointers are excluded, never their
    policies, source/runtime identities, selected resources or workload bytes.
    """
    from copy import deepcopy

    if "runtime" in config:
        # Reuse the adopted RS1 acyclic operation-scope projection. Its excluded
        # derived profile/start/admission pointers are independently checked by
        # actual complete-config authority and the exact campaign validators.
        from . import s12_b2_resources as resources

        c.require(plan is not None, "WF_AP2_CONFIGURATION_BINDING")
        paths = config.get("command_paths")
        c.require(
            type(paths) is dict
            and set(paths) == {"output_path", "scratch_path"}
            and all(type(v) is str and Path(v).is_absolute() for v in paths.values()),
            "WF_AP2_CONFIGURATION_BINDING",
        )
        selected = resources.command_scope_record(
            config,
            plan_binding=resources.workload_binding(plan)
            if config["runtime"]["campaign"] is not None
            else None,
        )
        selected["command_paths"] = dict(paths)
        selected["member_plan_binding_sha256"] = resources.workload_binding(plan)
        if "bootstrap_work_file" in config:
            selected["bootstrap_work_file"] = config["bootstrap_work_file"]
        return old.digest(selected)
    projected = deepcopy(config)
    runtime = projected.get("runtime")
    if type(runtime) is dict:
        runtime.pop("authority_sha256", None)
        resource = runtime.get("resource_retention")
        if type(resource) is dict:
            resource.pop("slot_binding_sha256", None)

    def profile(value):
        if type(value) is dict and "sampling_runtime_bound_sha256" in value:
            value.pop("sampling_runtime_bound_sha256")

    # Exact supported configuration locations; never recursively erase a field
    # in arbitrary caller content or a scientific/authority evidence record.
    for campaign in projected.get("campaigns", ()):
        profile(campaign.get("profile"))
        if type(campaign.get("plan")) is dict:
            campaign["plan"]["operations_profile_sha256"] = old.digest(
                campaign["profile"]
            )
    if type(runtime) is dict:
        campaign = runtime.get("campaign")
        if type(campaign) is dict:
            # Protected configs normally reference profile records by hash;
            # use the separately reviewed profile-scope projection below.
            campaign.pop("sampling_runtime_bound_sha256", None)
    return old.digest(projected)


def validate_record(record, profile, start, contract, configuration_scope_sha256=None):
    shape(record, SCHEMA)
    c.require(record["scope"] == contract.SCOPE, "WF_AP2_SCOPE")
    c.require(record["valid_from"] < record["valid_until"], "WF_AP2_EXPIRED")
    c.require(
        old.digest(record) == profile["sampling_runtime_bound_sha256"]
        and record["sampling_policy_sha256"] == contract.POLICY_SHA
        and record["client_git_sha"] == start["client_git_sha"]
        and record["runtime_inventory_sha256"] == start["runtime_inventory_sha256"],
        "WF_AP2_SOURCE_BINDING",
    )
    if configuration_scope_sha256 is not None:
        c.require(
            record["configuration_scope_sha256"] == configuration_scope_sha256,
            "WF_AP2_CONFIGURATION_BINDING",
        )
    allocations = record["logical_allocations"]
    c.require(
        [row["name"] for row in allocations] == list(ARENAS), "WF_AP2_LOGICAL_INVENTORY"
    )
    by_name = {row["name"]: row["bytes"] for row in allocations}
    from .s12_wf_ap2_scratch import CAPS

    c.require(
        sum(by_name.values()) == record["total_logical_bytes"] <= LOGICAL_BYTES
        and by_name["SAMPLE_SLOTS"] >= 65536
        and by_name["HISTORY_PAGES"] == 8 * 2**20
        and by_name["TELEMETRY_RING"] >= 4096 * 512
        and by_name["SERIALIZATION_SCRATCH"]
        == record["logical_scratch_bytes"]
        <= SCRATCH_BYTES,
        "WF_AP2_LOGICAL_LIMIT",
    )
    c.require(
        record["logical_scratch_bytes"] >= sum(CAPS.values()), "WF_AP2_LOGICAL_LIMIT"
    )
    c.require(
        by_name["TRACE_METADATA"] >= 32768 and by_name["CONTROLLER_METADATA"] >= 16384,
        "WF_AP2_LOGICAL_LIMIT",
    )
    evidence = record["method_evidence_sha256"]
    c.require(
        1 <= len(evidence) <= 16 and evidence == sorted(set(evidence)),
        "WF_AP2_EVIDENCE_BOUND",
    )
    domain = record["domain"]
    c.require(
        0 < domain["memory_max_bytes"] <= MAX_JOB_BYTES
        and domain["swap_max_bytes"] == 0,
        "WF_AP2_JOB_ENFORCEMENT",
    )
    _domain_path(domain["path"])


def verify_runtime(record, authority, context):
    """Require fresh facts AND separately competent coverage/review grants."""
    facts = verify_current_facts(record, authority)
    authority.require(
        "sampling_enforcement_domain", record["enforcement_evidence_sha256"], record
    )
    authority.require(
        "sampling_domain_coverage", record["domain_coverage_evidence_sha256"], record
    )
    authority.require(
        "sampling_invocation_graph", record["invocation_graph_sha256"], context
    )
    return facts


def verify_current_facts(record, authority):
    """Fresh current enforcement without recursive grant resolution."""
    charge = getattr(authority, "charge_enforcement_check", None)
    c.require(callable(charge), "WF_AP2_ENFORCEMENT_BUDGET_REQUIRED")
    charge(record)
    c.require(
        callable(getattr(authority, "enforcement_facts", None)),
        "WF_AP2_ENFORCEMENT_REQUIRED",
    )
    if record["evidence_origin"] == "SYNTHETIC_TEST_ONLY":
        c.require(
            getattr(authority, "test_only", False) is True,
            "WF_AP2_TEST_AUTHORITY_DENIED",
        )
    actual_scope = getattr(authority, "configuration_scope_sha256", None)
    c.require(
        type(actual_scope) is str
        and actual_scope == record["configuration_scope_sha256"],
        "WF_AP2_CONFIGURATION_BINDING",
    )
    clock = getattr(authority, "clock", None)
    c.require(
        clock is not None
        and record["valid_from"] <= clock.utc() < record["valid_until"],
        "WF_AP2_EXPIRED",
    )
    facts = authority.enforcement_facts(record)
    shape(facts, FACTS)
    for key in DOMAIN:
        c.require(facts[key] == record["domain"][key], "WF_AP2_ENFORCEMENT_CHANGED")
    c.require(
        all(
            facts[key] is True
            for key in (
                "membership_matches",
                "nondelegated",
                "no_capabilities",
                "descendants_share_domain",
                "no_new_privileges",
            )
        )
        and facts["pids_current"] <= facts["pids_max"],
        "WF_AP2_ENFORCEMENT_INCOMPLETE",
    )
    return facts


def _domain_path(value):
    c.require(
        type(value) is str
        and len(value) <= 1024
        and re.fullmatch(r"/sys/fs/cgroup(?:/[A-Za-z0-9_.-]+)*", value) is not None
        and all(part not in (".", "..") for part in value.split("/")),
        "WF_AP2_DOMAIN_PATH",
    )
    return Path(value)


def _kernel_read(path, maximum=2048):
    import codecs

    c.require(type(maximum) is int and 0 < maximum <= 2048, "WF_AP2_KERNEL_SOURCE")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        c.require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid in (0, os.geteuid())
            and not info.st_mode & 0o022,
            "WF_AP2_KERNEL_SOURCE",
        )
        raw, used = bytearray(maximum + 1), 0
        while used <= maximum:
            part = os.read(fd, maximum + 1 - used)
            if not part:
                break
            raw[used : used + len(part)] = part
            used += len(part)
        c.require(used <= maximum, "WF_AP2_KERNEL_SOURCE")
        del part
        current = os.fstat(fd)
        observed = Path(path).stat(follow_symlinks=False)
        c.require(
            _kernel_identity(info)
            == _kernel_identity(current)
            == _kernel_identity(observed),
            "WF_AP2_KERNEL_CHANGED",
        )
        return codecs.decode(memoryview(raw)[:used], "ascii").strip()
    finally:
        os.close(fd)


def _limit(path):
    raw = _kernel_read(path, 64)
    if raw == "max":
        return None
    c.require(raw.isdecimal() and str(int(raw)) == raw, "WF_AP2_KERNEL_SOURCE")
    return old.uint(int(raw))


def _status_field(text, key, pattern):
    values = [
        line.partition(":")[2].strip()
        for line in text.splitlines()
        if line.partition(":")[0] == key
    ]
    c.require(
        len(values) == 1 and re.fullmatch(pattern, values[0]) is not None,
        "WF_AP2_KERNEL_SOURCE",
    )
    return values[0]


def _kernel_lines(path):
    """Bounded original kernel lines, no whole mount/process inventory list."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        c.require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid in (0, os.geteuid())
            and not info.st_mode & 0o022,
            "WF_AP2_KERNEL_SOURCE",
        )
        with os.fdopen(fd, "rb", closefd=False, buffering=0) as stream:
            for _ in range(4096):
                raw = stream.readline(2049)
                if not raw:
                    return
                c.require(
                    len(raw) <= 2048 and raw.endswith(b"\n"), "WF_AP2_KERNEL_SOURCE"
                )
                yield raw.decode("ascii").strip()
            c.require(not stream.read(1), "WF_AP2_KERNEL_SOURCE")
    finally:
        try:
            # A closed early iterator still checks the actual opened kernel
            # object; preserve an already initiating read/parse failure.
            if sys.exc_info()[0] in (None, GeneratorExit):
                c.require(
                    _kernel_identity(info)
                    == _kernel_identity(os.fstat(fd))
                    == _kernel_identity(Path(path).stat(follow_symlinks=False)),
                    "WF_AP2_KERNEL_CHANGED",
                )
        finally:
            os.close(fd)


def _kernel_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def runtime_facts(*, check=lambda: None):
    """Actual build/backend observations; no allocator/native upper-bound claim."""
    import gc
    import hashlib
    import importlib
    import platform
    import struct
    import sysconfig
    from . import s12_wf_ap2_scratch as scratch

    backends = []
    for name in ("_hashlib", "_ssl", "_sqlite3", "_duckdb", "pyarrow.lib"):
        check()
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve(strict=True)
        digest = hashlib.sha256()
        with scratch.lease("HASH"):
            buffer = bytearray(4096)
            with path.open("rb", buffering=0) as stream:
                before = os.fstat(stream.fileno())
                while size := stream.readinto(buffer):
                    check()
                    digest.update(memoryview(buffer)[:size])
                after = os.fstat(stream.fileno())
            c.require(
                _kernel_identity(before) == _kernel_identity(after)
                and (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                "WF_AP2_RUNTIME_CHANGED",
            )
        backends.append(
            {
                "module": name,
                "binary_name": path.name,
                "binary_sha256": digest.hexdigest(),
            }
        )
    check()
    allocator = os.environ.get("PYTHONMALLOC")
    allocator_selection = allocator if allocator in {
        "default", "debug", "malloc", "malloc_debug", "pymalloc", "pymalloc_debug",
        "mimalloc", "mimalloc_debug",
    } else ("DEFAULT_REQUEST_NOT_EFFECTIVE_ALLOCATOR_PROOF" if allocator is None else "OTHER_REQUEST_NOT_ECHOED")
    return {
        "version": "stage12_wf_ap2_runtime_observations_v1",
        "python": platform.python_version(),
        "build": list(platform.python_build()),
        "implementation": sys.implementation.name,
        "cache_tag": sys.implementation.cache_tag,
        "SOABI": sysconfig.get_config_var("SOABI"),
        "pointer_bytes": struct.calcsize("P"),
        "byteorder": sys.byteorder,
        "gil_enabled": sys._is_gil_enabled()
        if hasattr(sys, "_is_gil_enabled")
        else "NOT_REPORTED",
        "gc_thresholds": list(gc.get_threshold()),
        "allocator_build_flags": {
            key: sysconfig.get_config_var(key)
            for key in ("WITH_PYMALLOC", "WITH_MIMALLOC")
        },
        "allocator_environment_selection": allocator_selection,
        "effective_allocator_upper_bound": "NOT_CLAIMED_M2_ENFORCES_COMPLETE_JOB_DOMAIN",
        "native_transitive_build_closure": "NOT_ATTESTED_BY_THESE_POINT_IN_TIME_MODULE_OBSERVATIONS",
        "backends": backends,
    }


def observe_linux_domain(binding):
    from . import s12_wf_ap2_scratch as scratch

    with scratch.lease("KERNEL"):
        return _observe_linux_domain(binding)


def _observe_linux_domain(binding):
    """Read actual cgroup-v2 domain; never infer host coverage from this alone.

    Independent coverage evidence binds the actual namespaces/boot/mount/domain.
    This reader rejects unsupported/unreadable or delegated domains. A cgroup
    cap is NOT a physical-storage/native-file/capacity proof.
    """
    c.require(
        sys.platform == "linux" and os.geteuid() != 0, "WF_AP2_PLATFORM_UNSUPPORTED"
    )
    root = _domain_path(binding["path"])
    c.require(root.resolve(strict=True) == root, "WF_AP2_DOMAIN_PATH")
    mount = Path("/sys/fs/cgroup")
    chain = []
    identities = []
    ns_before = (
        Path("/proc/self/ns/cgroup").stat().st_ino,
        Path("/proc/self/ns/mnt").stat().st_ino,
    )
    node = root
    while True:
        info = node.stat(follow_symlinks=False)
        c.require(
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == 0
            and not info.st_mode & 0o022,
            "WF_AP2_DELEGATED_DOMAIN",
        )
        chain.append(node)
        identities.append(_kernel_identity(info))
        if node == mount:
            break
        c.require(len(chain) <= 32, "WF_AP2_DOMAIN_PATH")
        node = node.parent
    # A v2 mount plus the actual unified membership is required. Host/mount
    # namespace provenance remains separately attested, never inferred from PID1.
    from contextlib import closing

    matching_mount = False
    mount_count = 0
    with closing(_kernel_lines(Path("/proc/self/mountinfo"))) as mounts:
        for line in mounts:
            columns = line.split()
            c.require(len(columns) >= 6, "WF_AP2_KERNEL_SOURCE")
            if columns[4] == str(mount):
                mount_count += 1
                matching_mount = " - cgroup2 " in line and columns[3] == "/"
    c.require(matching_mount and mount_count == 1, "WF_AP2_CGROUP_V2_REQUIRED")
    membership = _kernel_read(Path("/proc/self/cgroup"), 2048)
    expected = "/" + str(root.relative_to(mount)) if root != mount else "/"
    c.require(membership == "0::" + expected, "WF_AP2_MEMBERSHIP")
    del membership
    status = _kernel_read(Path("/proc/self/status"), 2048)
    # NoNewPrivs restricts exec gains, not capset from an existing permitted
    # set. No effective/permitted/inheritable/ambient authority may survive.
    for key in ("CapEff", "CapPrm", "CapInh", "CapAmb"):
        caps = _status_field(status, key, r"[0-9a-fA-F]{1,16}")
        c.require(int(caps, 16) == 0, "WF_AP2_CAPABILITIES")
    privileges = _status_field(status, "NoNewPrivs", r"[01]")
    c.require(privileges == "1", "WF_AP2_PRIVILEGE_ESCAPE")
    del status
    limits = {name: [] for name in ("memory.max", "memory.swap.max", "pids.max")}
    for ancestor in chain:
        for name in limits:
            try:
                value = _limit(ancestor / name)
            except FileNotFoundError:
                # Only the verified v2 hierarchy root has no upper controller
                # knob. Missing nonroot/permission/other failures stay fatal.
                c.require(ancestor == mount, "WF_AP2_KERNEL_SOURCE")
                value = None
            if value is not None:
                limits[name].append(value)
        for name in (
            "cgroup.procs",
            "cgroup.threads",
            "cgroup.subtree_control",
            "memory.max",
            "memory.swap.max",
            "pids.max",
        ):
            c.require(
                not os.access(ancestor / name, os.W_OK), "WF_AP2_DELEGATED_DOMAIN"
            )
    c.require(all(limits.values()), "WF_AP2_UNBOUNDED_DOMAIN")
    memory, swap, pids = (min(limits[x]) for x in limits)
    c.require(
        0 < memory <= MAX_JOB_BYTES and swap == 0 and pids > 0, "WF_AP2_JOB_ENFORCEMENT"
    )
    with closing(_kernel_lines(root / "cgroup.procs")) as procs:
        member = any(line == str(os.getpid()) for line in procs)
    c.require(member, "WF_AP2_MEMBERSHIP")
    info = root.stat(follow_symlinks=False)
    facts = {
        "path": str(root),
        "device": info.st_dev,
        "inode": info.st_ino,
        "cgroup_namespace_inode": Path("/proc/self/ns/cgroup").stat().st_ino,
        "mount_namespace_inode": Path("/proc/self/ns/mnt").stat().st_ino,
        "boot_id": _kernel_read(Path("/proc/sys/kernel/random/boot_id"), 64).replace(
            "-", ""
        ),
        "memory_max_bytes": memory,
        "swap_max_bytes": swap,
        "pids_max": pids,
        "membership_matches": True,
        "nondelegated": True,
        "no_capabilities": True,
        "descendants_share_domain": True,
        "no_new_privileges": True,
        "pids_current": _limit(root / "pids.current"),
        "observation_origin": "KERNEL_CGROUP_V2",
    }
    # Detect domain/path changes across acquisition. Limits are read again at
    # every invocation; an earlier successful observation is not a later token.
    c.require(
        (info.st_dev, info.st_ino) == (binding["device"], binding["inode"]),
        "WF_AP2_ENFORCEMENT_CHANGED",
    )
    for ancestor, identity in zip(chain, identities, strict=True):
        c.require(
            _kernel_identity(ancestor.stat(follow_symlinks=False)) == identity,
            "WF_AP2_KERNEL_CHANGED",
        )
    c.require(
        (facts["cgroup_namespace_inode"], facts["mount_namespace_inode"]) == ns_before,
        "WF_AP2_NAMESPACE_CHANGED",
    )
    for name, expected_limit in (
        ("memory.max", memory),
        ("memory.swap.max", swap),
        ("pids.max", pids),
    ):
        observed_limits = []
        for ancestor in chain:
            try:
                current_limit = _limit(ancestor / name)
            except FileNotFoundError:
                c.require(ancestor == mount, "WF_AP2_KERNEL_CHANGED")
                current_limit = None
            if current_limit is not None:
                observed_limits.append(current_limit)
        c.require(
            observed_limits and min(observed_limits) == expected_limit,
            "WF_AP2_ENFORCEMENT_CHANGED",
        )
    return facts

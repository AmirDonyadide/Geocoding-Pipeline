"""Closed WF-AP2 bootstrap and delegated binding; never invents live facts.

`ready` is a pre-submission metadata check. `collect` and `bind` are the first
two of three permitted compute Python invocations; the existing denied driver
is the third. Capacity/coverage originals must be supplied under trusted hashes.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import socket
import stat
import sys
import time

VERSION = "stage12_wf_ap2_allocation_selection_v1"
SCOPE = "WF_AP2_REPRESENTATIVE_DIAGNOSTIC_TEST_ONLY_NO_SERVICE"
PROJECT = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
PARENT = PROJECT / "derived/controlled/stage12/client_diagnostics"
REPLAY = "docs/scientific_assets/stage12_wf_ap2_representative_replay_v1.json"
PUBLIC_VALIDATOR = "849a0863876b75dcef322a46d74c2558708cb8611046c8235869090cce621ae2"
ANCHORS = (
    "owner",
    "a_capacity",
    "b_capacity",
    "coverage",
    "method",
    "logical",
    "reviewer_role",
)
STAGES = {
    "A": (120, 32 * 2**20, 256),
    "review": (600, 64 * 2**20, 512),
    "binding": (120, 64 * 2**20, 512),
    "B": (7200, 72 * 2**30, 120000),
    "final": (120, 64 * 2**20, 256),
}
PATHS = (
    "source",
    "records",
    "bootstrap",
    "binding",
    "input",
    "evidence",
    "output",
    "review",
    "outcome",
)
MAX_READ = 2**20
REQUIRED_SOURCE_FILES = frozenset(
    {
        "scripts/stage12_wf_ap2_allocation.py",
        "scripts/stage12_wf_ap2_diagnostic.py",
        "scripts/stage12_diverse_offline_diagnostic.py",
        "scripts/stage12_scale120_diagnostic.py",
        "scripts/stage12_native_enforcement_observer.py",
        "cluster/goethe_nhr/stage12_wf_ap2_allocation.sbatch",
        "src/safe_geocoding_pipeline/execution_policy.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_runtime.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_storage.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_transport.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_wf_ap2_assurance.py",
        "src/safe_geocoding_pipeline/preprocessing/stages/s12_wf_ap2_contract.py",
    }
)


class AllocationError(RuntimeError):
    """Static categories only; callers never print arbitrary exceptions."""


def need(condition, code="AP2_ALLOCATION_INVALID"):
    if not condition:
        raise AllocationError(code)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(canonical(value))


def fields(value, names):
    need(type(value) is dict and set(value) == set(names))


def hash_value(value, size=64):
    return (
        type(value) is str
        and re.fullmatch("[0-9a-f]{%d}" % size, value) is not None
        and set(value) != {"0"}
    )


def uint(value, positive=False):
    need(type(value) is int and int(positive) <= value < 2**64)
    return value


def utc(value):
    need(
        type(value) is str
        and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z", value)
    )
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=timezone.utc
    )


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def private_directory(path):
    path = Path(path)
    need(
        path.is_absolute() and ".." not in path.parts and path.resolve() == path,
        "AP2_ALLOCATION_PATH",
    )
    info = path.stat(follow_symlinks=False)
    need(
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.getuid(),
        "AP2_ALLOCATION_PRIVATE",
    )


def original(path, *, limit=MAX_READ, private=True):
    path = Path(path)
    if private:
        private_directory(path.parent)
    before = path.stat(follow_symlinks=False)
    need(
        stat.S_ISREG(before.st_mode) and before.st_nlink == 1, "AP2_ALLOCATION_ORIGINAL"
    )
    if private:
        need(
            before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600,
            "AP2_ALLOCATION_PRIVATE",
        )
    need(before.st_size <= limit, "AP2_ALLOCATION_READ_BOUND")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        need(
            identity(os.fstat(fd)) == identity(before), "AP2_ALLOCATION_SOURCE_CHANGED"
        )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        need(
            len(raw) <= limit
            and identity(os.fstat(fd)) == identity(before)
            and identity(path.stat(follow_symlinks=False)) == identity(before),
            "AP2_ALLOCATION_SOURCE_CHANGED",
        )
        return raw
    finally:
        os.close(fd)


def parse(raw):
    def unique(pairs):
        value = {}
        for key, cell in pairs:
            need(key not in value, "AP2_ALLOCATION_DUPLICATE")
            value[key] = cell
        return value

    value = json.loads(raw, object_pairs_hook=unique)
    need(canonical(value) == raw, "AP2_ALLOCATION_CANONICAL")
    return value


def selection_scope(value):
    selected = deepcopy(value)
    selected["anchors"].pop("owner")
    return digest(selected)


def validate_selection(value, *, paths=True):
    fields(
        value,
        (
            "version",
            "scope",
            "status",
            "source_sha",
            "source_files",
            "paths",
            "anchors",
            "valid_from",
            "valid_until",
            "replay_sha256",
            "limits",
        ),
    )
    need(
        value["version"] == VERSION
        and value["scope"] == SCOPE
        and value["status"] == "ISSUED"
    )
    need(hash_value(value["source_sha"], 40) and hash_value(value["replay_sha256"]))
    need(utc(value["valid_from"]) < utc(value["valid_until"]))
    fields(value["anchors"], ANCHORS)
    for name, token in value["anchors"].items():
        need(token is None or hash_value(token))
    fields(value["paths"], PATHS)
    selected = value["paths"]
    need(len(set(selected.values())) == len(selected))
    for name, text in selected.items():
        path = Path(text)
        need(
            type(text) is str
            and re.fullmatch(r"/[A-Za-z0-9_./-]+", text)
            and path.is_absolute()
            and ".." not in path.parts
        )
        if paths:
            expected_parent = (
                PROJECT / "integration_stage12" if name == "source" else PARENT
            )
            if name in ("input", "evidence"):
                expected_parent = Path(selected["binding"])
            need(path.parent == expected_parent, "AP2_ALLOCATION_PATH")
    need(
        Path(selected["input"]).name == "input.json"
        and Path(selected["evidence"]).name == "evidence"
    )
    fields(
        value["limits"],
        (
            "stages",
            "rss_bytes",
            "native_threads",
            "whole_seconds",
            "whole_creations",
            "whole_bytes",
            "max_enforcement_checks",
            "max_runtime_inventory_checks",
        ),
    )
    limits = value["limits"]
    fields(limits["stages"], STAGES)
    for name, upper in STAGES.items():
        fields(limits["stages"][name], ("seconds", "bytes", "creations"))
        for cell, cap in zip(("seconds", "bytes", "creations"), upper, strict=True):
            need(0 < uint(limits["stages"][name][cell], True) <= cap)
        # This first release has one exact time selection. Supporting a lower
        # configurable stage time requires a new reviewed launcher binding.
        need(limits["stages"][name]["seconds"] == upper[0])
    need(limits["stages"]["B"]["seconds"] == 7200)
    need(0 < uint(limits["rss_bytes"], True) <= 768 * 2**20)
    need(uint(limits["native_threads"], True) == 256)
    need(uint(limits["whole_seconds"], True) == 8160)
    need(
        sum(v["seconds"] for v in limits["stages"].values()) <= limits["whole_seconds"]
    )
    need(0 < uint(limits["whole_creations"], True) <= 130000)
    need(0 < uint(limits["whole_bytes"], True) <= 77561069568)
    need(
        sum(v["bytes"] for v in limits["stages"].values()) + 16 * 2**20
        <= limits["whole_bytes"]
    )
    need(
        sum(v["creations"] for v in limits["stages"].values()) + 8
        <= limits["whole_creations"]
    )
    need(0 < uint(limits["max_enforcement_checks"], True) <= 4096)
    need(0 < uint(limits["max_runtime_inventory_checks"], True) <= 8)
    need(type(value["source_files"]) is list and 1 <= len(value["source_files"]) <= 128)
    names = []
    for entry in value["source_files"]:
        fields(entry, ("path", "sha256"))
        name = Path(entry["path"])
        need(
            not name.is_absolute()
            and ".." not in name.parts
            and hash_value(entry["sha256"])
        )
        need(name.parts[0] in ("src", "scripts", "cluster", "docs"))
        need(str(name) != REPLAY, "AP2_ALLOCATION_A_PAYLOAD")
        names.append(str(name))
    need(names == sorted(set(names)))
    need(REQUIRED_SOURCE_FILES <= set(names), "AP2_ALLOCATION_SOURCE_INVENTORY")


def load_selection(path, expected):
    raw = original(path)
    need(sha(raw) == expected, "AP2_ALLOCATION_SELECTION_CHANGED")
    result = parse(raw)
    validate_selection(result)
    return result


class Records:
    def __init__(self, root):
        self.root = Path(root)
        private_directory(self.root)

    def raw(self, token, *, structured=True):
        need(hash_value(token), "AP2_ALLOCATION_MISSING_EVIDENCE")
        raw = original(self.root / (token + (".json" if structured else ".evidence")))
        need(sha(raw) == token, "AP2_ALLOCATION_EVIDENCE_CHANGED")
        return raw

    def get(self, token):
        return parse(self.raw(token))


def check_window(selection, now):
    need(
        selection["valid_from"] <= now < selection["valid_until"],
        "AP2_ALLOCATION_EXPIRED",
    )


def owner(selection, records, now):
    row = records.get(selection["anchors"]["owner"])
    fields(
        row,
        (
            "version",
            "scope",
            "source_sha",
            "selection_scope_sha256",
            "approval_source_sha256",
            "maximum_allocations",
            "collect_A",
            "conditional_B",
            "valid_from",
            "valid_until",
        ),
    )
    need(
        row["version"] == "stage12_wf_ap2_allocation_owner_v1" and row["scope"] == SCOPE
    )
    need(
        row["source_sha"] == selection["source_sha"]
        and row["selection_scope_sha256"] == selection_scope(selection)
    )
    need(
        row["maximum_allocations"] == 1
        and row["collect_A"] is True
        and type(row["conditional_B"]) is bool
    )
    need(
        utc(row["valid_from"])
        <= utc(selection["valid_from"])
        <= utc(now)
        < utc(selection["valid_until"])
        <= utc(row["valid_until"])
    )
    records.raw(row["approval_source_sha256"], structured=False)
    return row


def capacity(selection, records, stage, now):
    row = records.get(
        selection["anchors"]["a_capacity" if stage == "A" else "b_capacity"]
    )
    fields(
        row,
        (
            "version",
            "scope",
            "record_origin",
            "authority_role",
            "proof_document_sha256",
            "controlled_parent",
            "work_stage",
            "file_data_bytes",
            "creation_attempts",
            "physical_capacity_bytes",
            "inode_capacity",
            "physical_and_transient_coverage_verified",
            "capacity_entitlement_verified",
            "valid_from",
            "valid_until",
        ),
    )
    need(row["version"] == "stage12_wf_ap2_capacity_fact_v1" and row["scope"] == SCOPE)
    need(
        row["record_origin"] == "COMPETENT_AUTHORITY_ORIGINAL"
        and row["authority_role"] == "STORAGE_CAPACITY_AUTHORITY"
    )
    need(row["controlled_parent"] == str(PARENT) and row["work_stage"] == stage)
    need(
        row["physical_and_transient_coverage_verified"] is True
        and row["capacity_entitlement_verified"] is True
    )
    need(
        utc(row["valid_from"])
        <= utc(selection["valid_from"])
        <= utc(now)
        < utc(selection["valid_until"])
        <= utc(row["valid_until"])
    )
    selected = selection["limits"]["stages"][stage]
    # A's trusted record covers all non-B orchestration, including independent
    # review, binder, outcome/log persistence and partial failures. B has its
    # separate capacity record; neither cap is reset or borrowed by a stage.
    required_bytes, required_entries = selected["bytes"], selected["creations"]
    if stage == "A":
        required_bytes = (
            sum(
                v["bytes"] for k, v in selection["limits"]["stages"].items() if k != "B"
            )
            + 16 * 2**20
        )
        required_entries = (
            sum(
                v["creations"]
                for k, v in selection["limits"]["stages"].items()
                if k != "B"
            )
            + 8
        )
    need(
        uint(row["file_data_bytes"], True) >= required_bytes
        and uint(row["creation_attempts"], True) >= required_entries
        and uint(row["physical_capacity_bytes"], True) >= required_bytes
        and uint(row["inode_capacity"], True) >= required_entries,
        "AP2_ALLOCATION_CAPACITY",
    )
    records.raw(row["proof_document_sha256"], structured=False)
    return row


def ready(selection, records, now):
    """Metadata-only pre-submission gate. No future kernel identity is required."""
    validate_selection(selection)
    check_window(selection, now)
    owner(selection, records, now)
    capacity(selection, records, "A", now)
    return {
        "A_ready": True,
        "B_released": False,
        "selection_scope_sha256": selection_scope(selection),
    }


class Budget:
    """One owner, precharge, exclusive writes, no refunds after uncertainty."""

    def __init__(
        self,
        root,
        *,
        max_bytes,
        max_creations,
        deadline,
        clock=time.monotonic_ns,
        check=lambda: None,
    ):
        self.root = Path(root)
        private_directory(self.root.parent)
        self.max_bytes, self.max_creations = max_bytes, max_creations
        self.deadline, self.clock, self.extra_check = deadline, clock, check
        self.bytes = self.creations = 0
        self.poisoned = False
        self.inventory = []
        self.directories = []
        self.charge(0)
        try:
            self.root.mkdir(mode=0o700)
            self.sync(self.root.parent)
        except BaseException:
            self.poisoned = True
            raise

    def check(self):
        need(not self.poisoned, "AP2_ALLOCATION_UNCERTAIN_IO")
        need(self.clock() < self.deadline, "AP2_ALLOCATION_DEADLINE")
        self.extra_check()

    def charge(self, size):
        self.check()
        need(
            self.bytes + size <= self.max_bytes
            and self.creations + 1 <= self.max_creations,
            "AP2_ALLOCATION_BUDGET",
        )
        self.bytes += size
        self.creations += 1

    @staticmethod
    def sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def path(self, name):
        need(type(name) is str and len(name) <= 256, "AP2_ALLOCATION_PATH")
        parts = name.split("/")
        need(
            1 <= len(parts) <= 3
            and all(
                re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", p) and p not in (".", "..")
                for p in parts
            ),
            "AP2_ALLOCATION_PATH",
        )
        return self.root / name

    def mkdir(self, name):
        path = self.path(name)
        private_directory(path.parent)
        self.charge(0)
        try:
            path.mkdir(mode=0o700)
            self.sync(path.parent)
            self.check()
        except BaseException:
            self.poisoned = True
            raise
        self.directories.append(name)

    def write(self, name, obj):
        return self.write_raw(name, canonical(obj))

    def write_raw(self, name, raw):
        path = self.path(name)
        private_directory(path.parent)
        need(type(raw) is bytes)

        need(len(raw) <= MAX_READ, "AP2_ALLOCATION_WRITE_BOUND")
        self.charge(len(raw))
        try:
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                view = memoryview(raw)
                while view:
                    count = os.write(fd, view)
                    need(count > 0, "AP2_ALLOCATION_WRITE_FAILED")
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            self.sync(path.parent)
            need(original(path) == raw, "AP2_ALLOCATION_READBACK_FAILED")
            self.check()
        except BaseException:
            self.poisoned = True
            raise
        self.inventory.append({"name": name, "bytes": len(raw), "sha256": sha(raw)})
        return sha(raw)

    def close(self, status):
        return self.write(
            "manifest.json",
            {
                "version": "stage12_wf_ap2_stage_manifest_v1",
                "status": status,
                "inventory": self.inventory.copy(),
                "directories": self.directories.copy(),
                "charged_bytes_before_manifest": self.bytes,
                "charged_creations_before_manifest": self.creations,
            },
        )


def verify_stage(root, expected=None, *, expected_status=None):
    raw = original(Path(root) / "manifest.json")
    if expected is not None:
        need(sha(raw) == expected, "AP2_ALLOCATION_MANIFEST_CHANGED")
    obj = parse(raw)
    fields(
        obj,
        (
            "version",
            "status",
            "inventory",
            "directories",
            "charged_bytes_before_manifest",
            "charged_creations_before_manifest",
        ),
    )
    need(obj["version"] == "stage12_wf_ap2_stage_manifest_v1")
    if expected_status is not None:
        need(obj["status"] == expected_status, "AP2_ALLOCATION_STAGE_INCOMPLETE")
    need(type(obj["inventory"]) is list and len(obj["inventory"]) <= 512)
    names = []
    for row in obj["inventory"]:
        fields(row, ("name", "bytes", "sha256"))
        need(
            type(row["name"]) is str
            and len(row["name"]) <= 256
            and 1 <= len(row["name"].split("/")) <= 3
            and all(
                re.fullmatch(r"[a-zA-Z0-9_.-]{1,128}", p) and p not in (".", "..")
                for p in row["name"].split("/")
            )
        )
        data = original(Path(root) / row["name"])
        need(
            len(data) == row["bytes"] and sha(data) == row["sha256"],
            "AP2_ALLOCATION_ORIGINAL_CHANGED",
        )
        names.append(row["name"])
    directories = obj["directories"]
    need(
        type(directories) is list
        and len(directories) <= 512
        and len(set(directories)) == len(directories)
    )
    observed_files, observed_dirs = set(), set()
    for parent, dirs, files in os.walk(root, followlinks=False):
        need(
            len(observed_files) + len(observed_dirs) + len(dirs) + len(files) <= 512,
            "AP2_ALLOCATION_INVENTORY_BOUND",
        )
        for name in dirs:
            path = Path(parent) / name
            private_directory(path)
            observed_dirs.add(str(path.relative_to(root)))
        for name in files:
            observed_files.add(str((Path(parent) / name).relative_to(root)))
    need(
        len(names) == len(set(names))
        and observed_files == set(names) | {"manifest.json"}
        and observed_dirs == set(directories),
        "AP2_ALLOCATION_INVENTORY_CHANGED",
    )
    need(
        original(Path(root) / "manifest.json") == raw, "AP2_ALLOCATION_MANIFEST_CHANGED"
    )
    return obj


def verify_source(selection, check=lambda: None):
    root = Path(selection["paths"]["source"])
    for row in selection["source_files"]:
        check()
        need(
            sha(original(root / row["path"], limit=4 * 2**20, private=False))
            == row["sha256"],
            "AP2_ALLOCATION_SOURCE_CHANGED",
        )


def _module(source, filename, name):
    spec = importlib.util.spec_from_file_location(
        name, Path(source) / "scripts" / filename
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe_kernel(
    *,
    read_root=Path("/proc/self"),
    cgroup_root=Path("/sys/fs/cgroup"),
    check=lambda: None,
):
    """Bounded originals; no qualification from namespace links alone."""
    total = 0
    errors = []
    reads = []

    def read(path, limit=65536):
        nonlocal total
        check()
        need(len(reads) < 256, "AP2_ALLOCATION_KERNEL_READ_COUNT")
        started = time.monotonic_ns()
        need(total + limit + 1 <= 2 * 2**20, "AP2_ALLOCATION_KERNEL_READ_BOUND")
        try:
            with Path(path).open("rb", buffering=0) as stream:
                raw = stream.read(limit + 1)
            total += len(raw)
            need(
                len(raw) <= limit and raw.count(b"\n") <= 2048,
                "AP2_ALLOCATION_KERNEL_READ_BOUND",
            )
            result = raw.decode("ascii").strip()
            reads.append(
                {
                    "kind": Path(path).name,
                    "started_mono_ns": started,
                    "ended_mono_ns": time.monotonic_ns(),
                    "bytes": len(raw),
                    "status": "READ",
                }
            )
            return result
        except (FileNotFoundError, PermissionError, UnicodeError):
            errors.append({"kind": Path(path).name, "status": "UNAVAILABLE"})
            reads.append(
                {
                    "kind": Path(path).name,
                    "started_mono_ns": started,
                    "ended_mono_ns": time.monotonic_ns(),
                    "bytes": None,
                    "status": "UNAVAILABLE",
                }
            )
            return None

    def ident(path):
        info = Path(path).stat(follow_symlinks=False)
        return {
            "device": info.st_dev,
            "inode": info.st_ino,
            "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid,
            "gid": info.st_gid,
        }

    initial_ns = {
        name: (read_root / "ns" / name).stat().st_ino for name in ("mnt", "cgroup")
    }
    boot = read(Path("/proc/sys/kernel/random/boot_id"), 64)
    membership, status = (
        read(read_root / "cgroup", 2048),
        read(read_root / "status", 8192),
    )
    mounts = read(read_root / "mountinfo")
    need(
        membership is not None
        and membership.startswith("0::/")
        and "\n" not in membership,
        "AP2_ALLOCATION_CGROUP_V2",
    )
    relative = membership[3:]
    need(".." not in Path(relative).parts, "AP2_ALLOCATION_CGROUP_V2")
    node = cgroup_root / relative.lstrip("/")
    before = ident(node)
    ancestors = []
    current = node
    while True:
        check()
        need(
            len(ancestors) < 32 and current.is_relative_to(cgroup_root),
            "AP2_ALLOCATION_ANCESTOR_BOUND",
        )
        row = {"path": str(current), "identity": ident(current)}
        for name in (
            "memory.max",
            "memory.high",
            "memory.swap.max",
            "pids.max",
            "pids.current",
        ):
            row[name] = read(current / name, 128)
        row["writable_control"] = any(
            os.access(current / n, os.W_OK)
            for n in (
                "memory.max",
                "memory.swap.max",
                "pids.max",
                "cgroup.procs",
                "cgroup.threads",
                "cgroup.subtree_control",
            )
        )
        ancestors.append(row)
        if current == cgroup_root:
            break
        current = current.parent
    procs = read(node / "cgroup.procs")
    end_ns = {name: (read_root / "ns" / name).stat().st_ino for name in initial_ns}
    need(
        initial_ns == end_ns
        and ident(node) == before
        and read(Path("/proc/sys/kernel/random/boot_id"), 64) == boot,
        "AP2_ALLOCATION_DOMAIN_CHANGED",
    )
    return {
        "version": "stage12_wf_ap2_kernel_observation_v1",
        "origin": "ACTUAL_READ_ONLY_KERNEL_OBSERVATION",
        "pid": os.getpid(),
        "boot_id": boot,
        "namespaces": initial_ns,
        "membership": membership,
        "status": status,
        "mountinfo": mounts,
        "leaf_identity": before,
        "leaf": str(node),
        "leaf_procs": procs,
        "ancestors": ancestors,
        "errors": errors,
        "reads": reads,
        "read_bytes": total,
        "coverage_authority_claim": False,
    }


def domain_from_kernel(value):
    """Derive known values, never turn unavailability/max into zero."""
    need(value["origin"] == "ACTUAL_READ_ONLY_KERNEL_OBSERVATION")
    need(value["boot_id"] is not None and value["mountinfo"] is not None)
    mount_lines = [
        x
        for x in value["mountinfo"].splitlines()
        if " - cgroup2 " in x and x.split()[4] == "/sys/fs/cgroup"
    ]
    need(
        len(mount_lines) == 1 and mount_lines[0].split()[3] == "/",
        "AP2_ALLOCATION_MOUNT_SCOPE",
    )
    minima = {}
    for name in ("memory.max", "memory.swap.max", "pids.max"):
        finite = []
        for row in value["ancestors"]:
            raw = row[name]
            need(
                raw is not None or row["path"] == "/sys/fs/cgroup",
                "AP2_ALLOCATION_KERNEL_UNKNOWN",
            )
            if raw is not None and raw != "max":
                need(raw.isdigit(), "AP2_ALLOCATION_KERNEL_UNKNOWN")
                finite.append(int(raw))
        need(bool(finite), "AP2_ALLOCATION_UNBOUNDED")
        minima[name] = min(finite)
    need(
        0 < minima["memory.max"] <= 6 * 2**30
        and minima["memory.swap.max"] == 0
        and minima["pids.max"] > 0,
        "AP2_ALLOCATION_ENFORCEMENT",
    )
    for row in value["ancestors"]:
        need(
            row["identity"]["uid"] == 0
            and not row["identity"]["mode"] & 0o022
            and not row["writable_control"],
            "AP2_ALLOCATION_DELEGATED",
        )
    need(
        value["leaf_procs"] is not None
        and str(value["pid"]) in value["leaf_procs"].splitlines(),
        "AP2_ALLOCATION_MEMBERSHIP",
    )
    need(value["status"] is not None)
    for key in ("CapEff", "CapPrm", "CapInh", "CapAmb"):
        cells = re.findall(
            r"^" + key + r":\s*([0-9a-fA-F]{1,16})\s*$", value["status"], re.M
        )
        need(len(cells) == 1 and int(cells[0], 16) == 0, "AP2_ALLOCATION_CAPABILITIES")
    return {
        "path": value["leaf"],
        "device": value["leaf_identity"]["device"],
        "inode": value["leaf_identity"]["inode"],
        "cgroup_namespace_inode": value["namespaces"]["cgroup"],
        "mount_namespace_inode": value["namespaces"]["mnt"],
        "boot_id": value["boot_id"].replace("-", ""),
        "memory_max_bytes": minima["memory.max"],
        "swap_max_bytes": minima["memory.swap.max"],
        "pids_max": minima["pids.max"],
    }


def same_domain(a, b):
    need(a == b, "AP2_ALLOCATION_DOMAIN_CHANGED")


def collection_guard(source, output, records, selection_path, *, extra_reads=()):
    """Read-only collector scope; no native-isolation claim or privilege change."""
    diagnostic = _module(
        source, "stage12_wf_ap2_diagnostic.py", "ap2_collection_policy"
    )
    proc = diagnostic.capture_self_proc_identity()
    parent = diagnostic.capture_output_parent(output)
    for extra_root in extra_reads:
        private_directory(extra_root)
    extra_identities = {
        root: identity(root.stat(follow_symlinks=False)) for root in extra_reads
    }

    def deny(*args, **kwargs):
        raise AllocationError("AP2_ALLOCATION_ACCESS_DENIED")

    def descriptor_path(fd):
        if sys.platform == "linux":
            need(proc.current(), "AP2_ALLOCATION_PROCESS_CHANGED")
            return os.readlink("/proc/self/fd/" + str(fd))
        import fcntl

        return os.fsdecode(
            fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0]
        )

    def allowed(path, write, flags=0):
        if type(path) is int:
            path = descriptor_path(path)
        path = Path(os.fsdecode(path))
        parent_open = diagnostic.parent_handle_allowed(
            path, flags, output=output, binding=parent
        )
        resolved = Path(os.path.realpath(path))
        eligible_extra = (
            path.is_absolute()
            and ".." not in path.parts
            and path == resolved
            and not any(
                part in {".ssh", ".config", "credentials", ".git"}
                or part.startswith(".env")
                for part in path.parts
            )
        )
        extra = (
            not write
            and eligible_extra
            and any(
                (path == root or path.is_relative_to(root))
                and identity(root.stat(follow_symlinks=False)) == extra_identities[root]
                for root in extra_reads
            )
        )
        need(
            parent_open
            or extra
            or diagnostic.open_allowed(
                path,
                write=write,
                source=source,
                output=output,
                input_path=selection_path,
                evidence=records,
                self_proc=proc,
            ),
            "AP2_ALLOCATION_ACCESS_DENIED",
        )

    def audit(event, args):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            deny()
        if event == "open":
            flags = args[2] if type(args[2]) is int else 0
            write = bool(
                flags
                & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            )
            allowed(args[0], write, flags)
        if event in ("os.listdir", "os.scandir"):
            path = args[0] if args[0] is not None else os.getcwd()
            if type(path) is int:
                path = descriptor_path(path)
            need(
                Path(os.fsdecode(path)) != output.parent, "AP2_ALLOCATION_ACCESS_DENIED"
            )
            allowed(path, False)
        if event == "os.mkdir":
            allowed(args[0], True)
        if event in (
            "os.remove",
            "os.rmdir",
            "os.rename",
            "os.link",
            "os.symlink",
            "os.chmod",
            "os.chown",
            "os.truncate",
        ):
            deny()

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, deny)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, deny)
    sys.addaudithook(audit)
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport

    s12_transport.Secret.runtime = s12_transport.Secret.private_file = deny


def native_threads():
    with Path("/proc/self/status").open("rb", buffering=0) as stream:
        raw = stream.read(8193)
    need(len(raw) <= 8192, "AP2_ALLOCATION_PROCESS_STATUS_BOUND")
    cells = re.findall(rb"^Threads:\s*(\d+)\s*$", raw, re.M)
    need(len(cells) == 1, "AP2_ALLOCATION_PROCESS_STATUS")
    return int(cells[0])


def collect(
    selection,
    selection_path,
    selection_hash,
    *,
    clock=time.monotonic_ns,
    kernel_reader=observe_kernel,
    inventory_reader=None,
    thread_reader=native_threads,
):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("WF-AP2 bounded metadata bootstrap")
    start = clock()
    records = Records(selection["paths"]["records"])
    ready(selection, records, now_utc())
    selected = selection["limits"]["stages"]["A"]
    deadline = start + selected["seconds"] * 10**9
    watermarks = {
        "checks": 0,
        "maximum_observed_rss_bytes": 0,
        "maximum_observed_native_threads": 0,
        "first_check_mono_ns": None,
        "last_check_mono_ns": None,
    }

    def check():
        tick = clock()
        need(tick < deadline, "AP2_ALLOCATION_DEADLINE")
        check_window(selection, now_utc())
        watermarks["checks"] += 1
        need(watermarks["checks"] <= 4096, "AP2_ALLOCATION_CHECK_COUNT")
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
        threads = thread_reader()
        watermarks["maximum_observed_rss_bytes"] = max(
            watermarks["maximum_observed_rss_bytes"], rss
        )
        watermarks["maximum_observed_native_threads"] = max(
            watermarks["maximum_observed_native_threads"], threads
        )
        watermarks["first_check_mono_ns"] = watermarks["first_check_mono_ns"] or tick
        watermarks["last_check_mono_ns"] = tick
        need(rss <= selection["limits"]["rss_bytes"], "AP2_ALLOCATION_RSS")
        need(
            0 < threads <= selection["limits"]["native_threads"],
            "AP2_ALLOCATION_THREADS",
        )

    source, output = (
        Path(selection["paths"]["source"]),
        Path(selection["paths"]["bootstrap"]),
    )
    verify_source(selection, check)
    collection_guard(
        source, output, Path(selection["paths"]["records"]), selection_path
    )
    budget = Budget(
        output,
        max_bytes=selected["bytes"],
        max_creations=selected["creations"],
        deadline=deadline,
        clock=clock,
        check=check,
    )
    kernel = kernel_reader(check=check)
    budget.write("kernel.json", kernel)
    if inventory_reader is None:
        from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime

        inventory_reader = s12_public_runtime.runtime_inventory
    inventory = inventory_reader(PUBLIC_VALIDATOR, successor=True, check=check)
    budget.write("runtime.json", inventory)
    verify_source(selection, check)
    after = kernel_reader(check=check)
    for key in ("boot_id", "namespaces", "membership", "leaf_identity", "leaf"):
        need(kernel[key] == after[key], "AP2_ALLOCATION_DOMAIN_CHANGED")
    budget.write("kernel_after.json", after)
    budget.write(
        "facts.json",
        {
            "version": "stage12_wf_ap2_bootstrap_facts_v1",
            "selection_sha256": selection_hash,
            "selection_scope_sha256": selection_scope(selection),
            "source_sha": selection["source_sha"],
            "job_id": os.environ["SLURM_JOB_ID"],
            "started_mono_ns": start,
            "observed_end_mono_ns": clock(),
            "created_utc": now_utc(),
            "runtime_inventory_sha256": digest(inventory),
            "kernel_sha256": digest(kernel),
            "kernel_after_sha256": digest(after),
            "qualifies_M2": False,
            "B_released": False,
            "resource_watermarks": watermarks.copy(),
            "watermark_coverage": "SAMPLED_CHECK_BOUNDARIES_NOT_NATIVE_ENFORCEMENT_PROOF",
        },
    )
    b_possible = (
        all(
            selection["anchors"][key] is not None
            for key in ("b_capacity", "coverage", "method", "logical", "reviewer_role")
        )
        and owner(selection, records, now_utc())["conditional_B"]
    )
    launch_fields = [
        selection["source_sha"],
        *(selection["paths"][key] for key in PATHS),
        "1" if b_possible else "0",
    ]
    budget.write_raw(
        "supervisor.fields", ("\n".join(launch_fields) + "\n").encode("ascii")
    )
    budget.close("BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED")
    verify_stage(output)
    budget.check()
    return {
        "status": "BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED",
        "manifest_sha256": sha(original(output / "manifest.json")),
        "B_released": False,
    }


def verify_release(
    selection, records, bootstrap, review, *, now, kernel_reader=observe_kernel
):
    """Only verify supplied original authority/facts; create no assertion here."""
    own = owner(selection, records, now)
    need(own["conditional_B"] is True, "AP2_ALLOCATION_B_NOT_AUTHORIZED")
    cap = capacity(selection, records, "B", now)
    fields(
        review,
        (
            "version",
            "scope",
            "decision",
            "reviewer",
            "reviewer_role_sha256",
            "source_sha",
            "selection_scope_sha256",
            "bootstrap_manifest_sha256",
            "coverage_sha256",
            "capacity_sha256",
            "method_sha256",
            "logical_sha256",
            "configuration_sha256",
            "runtime_bound_scope_sha256",
            "verified_utc",
            "valid_until",
        ),
    )
    need(
        review["version"] == "stage12_wf_ap2_independent_fact_review_v1"
        and review["scope"] == SCOPE
        and review["decision"] == "RELEASE_B",
        "AP2_ALLOCATION_REVIEW_REJECTED",
    )
    need(type(review["reviewer"]) is str and 0 < len(review["reviewer"]) <= 128)
    need(
        hash_value(review["configuration_sha256"])
        and hash_value(review["runtime_bound_scope_sha256"])
    )
    for field, anchor in (
        ("reviewer_role_sha256", "reviewer_role"),
        ("coverage_sha256", "coverage"),
        ("capacity_sha256", "b_capacity"),
        ("method_sha256", "method"),
        ("logical_sha256", "logical"),
    ):
        need(
            review[field] == selection["anchors"][anchor], "AP2_ALLOCATION_REVIEW_SCOPE"
        )
    role = records.get(review["reviewer_role_sha256"])
    fields(role, ("version", "scope", "purpose", "approval_source_sha256", "reviewer"))
    need(
        role["version"] == "stage12_wf_ap2_reviewer_role_v1"
        and role["scope"] == SCOPE
        and role["purpose"] == "INDEPENDENT_ALLOCATION_FACT_REVIEW"
        and role["reviewer"] == review["reviewer"],
        "AP2_ALLOCATION_REVIEW_ROLE",
    )
    records.raw(role["approval_source_sha256"], structured=False)
    need(
        review["source_sha"] == selection["source_sha"]
        and review["selection_scope_sha256"] == selection_scope(selection),
        "AP2_ALLOCATION_REVIEW_SCOPE",
    )
    need(
        utc(review["verified_utc"])
        <= utc(now)
        < utc(review["valid_until"])
        <= utc(selection["valid_until"]),
        "AP2_ALLOCATION_REVIEW_STALE",
    )
    need(
        review["bootstrap_manifest_sha256"]
        == sha(original(Path(bootstrap) / "manifest.json"))
    )
    verify_stage(
        bootstrap, expected_status="BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED"
    )
    facts = parse(original(Path(bootstrap) / "facts.json"))
    need(
        facts["source_sha"] == selection["source_sha"]
        and facts["selection_scope_sha256"] == selection_scope(selection)
        and facts["job_id"] == os.environ.get("SLURM_JOB_ID"),
        "AP2_ALLOCATION_JOB_CHANGED",
    )
    need(
        utc(facts["created_utc"]) <= utc(review["verified_utc"]),
        "AP2_ALLOCATION_REVIEW_STALE",
    )
    initial = parse(original(Path(bootstrap) / "kernel_after.json"))
    domain = domain_from_kernel(initial)
    current = kernel_reader()
    same_domain(domain, domain_from_kernel(current))
    coverage = records.get(selection["anchors"]["coverage"])
    fields(
        coverage,
        (
            "version",
            "scope",
            "record_origin",
            "authority_role",
            "proof_document_sha256",
            "domain_prefix",
            "complete_job_descendants",
            "host_namespace_scope_verified",
            "nondelegated_no_escape",
            "maximum_memory_bytes",
            "swap_max_bytes",
            "finite_pids_required",
            "valid_from",
            "valid_until",
        ),
    )
    need(
        coverage["version"] == "stage12_wf_ap2_domain_coverage_v1"
        and coverage["scope"] == SCOPE
        and coverage["record_origin"] == "COMPETENT_AUTHORITY_ORIGINAL"
        and coverage["authority_role"] == "RUNTIME_ENFORCEMENT_AUTHORITY",
        "AP2_ALLOCATION_COVERAGE",
    )
    prefix = Path(coverage["domain_prefix"])
    need(
        prefix.is_absolute()
        and ".." not in prefix.parts
        and Path(domain["path"]).is_relative_to(prefix)
    )
    need(
        coverage["complete_job_descendants"] is True
        and coverage["host_namespace_scope_verified"] is True
        and coverage["nondelegated_no_escape"] is True
        and coverage["finite_pids_required"] is True
    )
    need(
        domain["memory_max_bytes"]
        <= uint(coverage["maximum_memory_bytes"], True)
        <= 6 * 2**30
        and coverage["swap_max_bytes"] == 0
    )
    need(
        utc(coverage["valid_from"])
        <= utc(selection["valid_from"])
        <= utc(now)
        < utc(selection["valid_until"])
        <= utc(coverage["valid_until"])
    )
    records.raw(coverage["proof_document_sha256"], structured=False)
    method = records.get(selection["anchors"]["method"])
    logical = records.get(selection["anchors"]["logical"])
    fields(
        method, ("version", "scope", "method", "source_sha", "proof_document_sha256")
    )
    need(
        method["version"] == "stage12_wf_ap2_method_evidence_v1"
        and method["scope"] == SCOPE
        and method["method"] == "LOGICAL_ARENAS_AND_ENFORCED_JOB_DOMAIN"
        and method["source_sha"] == selection["source_sha"]
    )
    records.raw(method["proof_document_sha256"], structured=False)
    fields(
        logical,
        ("version", "scope", "source_sha", "proof_document_sha256", "allocations"),
    )
    need(
        logical["version"] == "stage12_wf_ap2_logical_evidence_v1"
        and logical["scope"] == SCOPE
        and logical["source_sha"] == selection["source_sha"]
    )
    records.raw(logical["proof_document_sha256"], structured=False)
    return facts, domain, cap, logical


def materialize(
    selection,
    facts,
    domain,
    logical,
    runtime_inventory,
    review,
    records,
    budget,
    *,
    for_review=False,
):
    """Derive UNISSUED review subjects or bind independently verified facts."""
    source = Path(selection["paths"]["source"])
    diagnostic = _module(
        source, "stage12_wf_ap2_diagnostic.py", "ap2_binding_diagnostic"
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as a
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_assets,
        s12_operations,
        s12_response,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_probe,
        s12_public_matrix as matrix,
    )

    replay = parse(original(source / REPLAY, private=False, limit=4 * 2**20))
    need(digest(replay) == selection["replay_sha256"])
    need(
        replay["version"] == "stage12_wf_ap2_representative_replay_v1"
        and replay["scope"] == "PUBLIC_SYNTHETIC_REPLAY_NO_SERVICE_AUTHORITY"
    )
    window_start, window_end = selection["valid_from"], selection["valid_until"]
    roles = {
        role: {
            "version": "stage12_diagnostic_test_authority_v1",
            "scope": SCOPE,
            "role": role,
            "authority": "TEST_ONLY_NO_SERVICE",
        }
        for role in ("owner", "operator", "policy_freeze", "selection", "transport")
    }
    role_hashes = {role: digest(value) for role, value in roles.items()}
    resources = {
        "admission_memory_bytes": 4 * 2**30,
        "capacity_basis_sha256": selection["anchors"]["b_capacity"],
        "process_overhead_bytes": 2**30,
        "job_memory_bytes": 6 * 2**30,
        "pending_request_bytes": 2**20,
        "per_attempt_disk_bound_bytes": 2**27,
        "fixed_campaign_disk_bound_bytes": 2**27,
        "allocated_disk_bytes": selection["limits"]["stages"]["B"]["bytes"],
        "resource_review_sha256": role_hashes["selection"],
        "scheduler_guard_ms": 100,
        "writer_guard_ms": 5000,
    }
    transport = {"scope": SCOPE, "authority": "TEST_ONLY_NO_NETWORK"}
    preserved = s12_assets.hashes()
    campaigns, phases = [], []
    # The temporary nonzero pointer is removed by the adopted acyclic scope;
    # it is never persisted as a supported bound or used for execution.
    pending_pointer = digest(
        {
            "scope": "UNPERSISTED_BINDING_PLACEHOLDER",
            "selection": selection_scope(selection),
        }
    )
    for index, (label, duration, hold, count) in zip(
        (0, 9, 10, 0), diagnostic.PHASES, strict=True
    ):
        work, recipes = matrix.work_for(index, digest(transport))
        work = work[:count]
        controls = count if label == "controls8" else 0
        data = count - controls
        observations = (duration + 49) // 50 + 2
        f = 4 * observations + 8
        sample_bytes = 4096 * f + 8 * (512 * f + 4096)
        profile = {
            "schema_version": a.PROFILE,
            "scope": a.SCOPE,
            "rule_bundle_sha256": a.RULE_BUNDLE,
            "policy_freeze_record_sha256": role_hashes["policy_freeze"],
            "preserved": {
                "operations_v1_sha256": preserved[s12_operations.VERSION].hex(),
                "materialization_sha256": preserved[a.c.MATERIALIZATION].hex(),
                "response_validation_sha256": preserved[s12_response.VALIDATION].hex(),
                "public_audit_source_sha256": "b43134525b99b60767d9661d334ccf743d101f06e85be42350483048a1c9d8f4",
            },
            "transport_profile_sha256": digest(transport),
            "operator_allowance": {
                "record_sha256": role_hashes["operator"],
                "rate_ceiling": {"num": 1, "den": 1},
                "connections": 2,
                "valid_from": window_start,
                "valid_until": window_end,
            },
            "states": [
                {
                    "state_id": 1,
                    "rate": {"num": 1, "den": 1},
                    "connections": 2,
                    "admitted_operations": 2,
                    "evidence_sha256": role_hashes["selection"],
                }
            ],
            "resources": deepcopy(resources),
            "monitoring": {
                "mode": "PUBLIC_GAPS_ONLY",
                "gaps_record_sha256": role_hashes["selection"],
            },
            "sampling_policy_sha256": a.POLICY_SHA,
            "sampling_runtime_bound_sha256": pending_pointer,
            **a.assurance_fields(),
        }
        budget_row = {
            "data_observations": data,
            "required_control_observations": controls,
            "reserved_control_observations": 0,
            "data_attempts": 5 * data,
            "control_http_attempts": 5 * controls,
            "administrative_operations": 0,
            "administrative_duration_ms": 0,
            "active_duration_ms": duration,
            "storage_bytes": (5 * count + 1) * 2**27 + sample_bytes,
            "event_count": 19 * 5 * count + 40 + 2 * observations + 4,
        }
        plan = {
            "schema_version": a.PLAN,
            "scope": a.SCOPE,
            "operations_profile_sha256": digest(profile),
            "fixture_inventory_sha256": digest(s12_probe.fixtures()),
            "work_manifest_sha256": a.manifest_digest(work),
            "control_recipes": recipes,
            "blocks": [
                {
                    "block_id": 1,
                    "state_id": 1,
                    "observation_ids": [x["work_id"] for x in work],
                    "reserved_control_ids": [],
                    "budget": deepcopy(budget_row),
                    "evaluation": "EXPLORATORY",
                    "criteria": None,
                    "fallback_state_ids": [],
                    "transition_from": None,
                }
            ],
            "experiment_kind": "PERFORMANCE",
            "capability_parent_sha256": None,
            "budgets": budget_row,
            "window_start": window_start,
            "window_end": window_end,
            "shutdown_reserve_ms": 80000,
            "selection_basis_sha256": role_hashes["selection"],
            "sampling_budget": {
                "maximum_segments": 1,
                "maximum_observations": observations,
                "maximum_inventory_versions_per_segment": 8,
                "additional_event_tokens": 2 * observations + 4,
                "additional_file_data_bytes": sample_bytes,
                "additional_file_entries": f + 8,
            },
            "history_limits": {
                "maximum_entries": 150000,
                "maximum_name_bytes": 256,
                "maximum_total_name_bytes": 38400000,
                "page_entries": 128,
                "maximum_depth": 8,
                "maximum_file_bytes": 2**26,
            },
        }
        campaigns.append(
            {"label": label, "profile": profile, "plan": plan, "work": work}
        )
        phases.append(
            {
                "label": label,
                "epoch_id": digest(
                    [facts["job_id"], selection_scope(selection), label, "epoch"]
                ),
                "hold_regular_acks": hold,
            }
        )
    config = {
        "version": diagnostic.CONFIG_VERSION,
        "window_start": window_start,
        "window_end": window_end,
        "sources": role_hashes,
        "transport": transport,
        "campaigns": campaigns,
        "resources": resources,
        "public_validation_sha256": PUBLIC_VALIDATOR,
        "command_paths": {
            key: selection["paths"][mapped]
            for key, mapped in (
                ("source", "source"),
                ("input", "input"),
                ("output", "output"),
                ("evidence_bundle", "evidence"),
            )
        },
    }
    graph = {
        "version": "stage12_wf_ap2_allocation_graph_v1",
        "scope": SCOPE,
        "source_sha": selection["source_sha"],
        "job_id": facts["job_id"],
        "selection_scope_sha256": selection_scope(selection),
        "domain": domain,
        "limits": selection["limits"],
        "python_invocations": ["COLLECT", "BIND", "DENIED_DIAGNOSTIC"],
        "no_protected_graph": True,
    }
    enforcement = {
        "version": "stage12_wf_ap2_actual_enforcement_v1",
        "scope": SCOPE,
        "bootstrap_manifest_sha256": review["bootstrap_manifest_sha256"],
        "domain": domain,
        "original_kernel_sha256": facts["kernel_after_sha256"],
    }
    allocations = []
    need(type(logical["allocations"]) is list and len(logical["allocations"]) == 7)
    for name, row in zip(m.ARENAS, logical["allocations"], strict=True):
        fields(row, ("name", "bytes"))
        need(row["name"] == name)
        allocations.append({**row, "evidence_sha256": selection["anchors"]["logical"]})
    bound = {
        "schema_version": m.BOUND,
        "scope": a.SCOPE,
        "method": m.METHOD,
        "sampling_policy_sha256": a.POLICY_SHA,
        "client_git_sha": selection["source_sha"],
        "runtime_inventory_sha256": digest(runtime_inventory),
        "configuration_scope_sha256": m.configuration_scope(config),
        "invocation_graph_sha256": digest(graph),
        "maximum_enforcement_checks": selection["limits"]["max_enforcement_checks"],
        "maximum_runtime_inventory_checks": selection["limits"][
            "max_runtime_inventory_checks"
        ],
        "technical_review_record_sha256": pending_pointer,
        "enforcement_evidence_sha256": digest(enforcement),
        "domain_coverage_evidence_sha256": selection["anchors"]["coverage"],
        "method_evidence_sha256": [selection["anchors"]["method"]],
        "evidence_origin": "LIVE_KERNEL_EVIDENCE",
        "valid_from": window_start,
        "valid_until": window_end,
        "logical_allocations": allocations,
        "total_logical_bytes": sum(x["bytes"] for x in allocations),
        "logical_scratch_bytes": next(
            x["bytes"] for x in allocations if x["name"] == "SERIALIZATION_SCRATCH"
        ),
        "native_component_guarantee": "NOT_CLAIMED",
        "native_scratch_guarantee": "NOT_CLAIMED",
        "domain": domain,
    }
    subject = dict(bound)
    subject.pop("technical_review_record_sha256")
    technical = {
        "version": "stage12_wf_ap2_bound_review_v1",
        "scope": a.SCOPE,
        "disposition": "PASS",
        "bound_scope_sha256": digest(subject),
        "reviewer_role_evidence_sha256": selection["anchors"]["reviewer_role"],
    }
    bound["technical_review_record_sha256"] = digest(technical)
    proof_objects = {
        digest(bound): bound,
        digest(technical): technical,
        digest(graph): graph,
        digest(enforcement): enforcement,
        digest(review): review,
    }
    for anchor in ("coverage", "method", "logical", "reviewer_role"):
        proof_objects[selection["anchors"][anchor]] = records.get(
            selection["anchors"][anchor]
        )
    for item in campaigns:
        item["profile"]["sampling_runtime_bound_sha256"] = digest(bound)
        item["plan"]["operations_profile_sha256"] = digest(item["profile"])
    need(
        m.configuration_scope(config) == bound["configuration_scope_sha256"],
        "AP2_ALLOCATION_BINDING_CYCLE",
    )
    if for_review:
        # Pure canonical review subjects. No files or issuing records are
        # emitted; the independent reviewer must inspect/hash these bytes.
        return {
            "status": "UNISSUED_REVIEW_SUBJECTS",
            "configuration": config,
            "runtime_bound_scope": subject,
        }
    need(
        digest(config) == review["configuration_sha256"]
        and digest(subject) == review["runtime_bound_scope_sha256"],
        "AP2_ALLOCATION_DERIVED_REVIEW_MISMATCH",
    )

    integration_text = {
        "version": "stage12_wf_ap2_delegated_binding_review_v1",
        "independent_fact_review_sha256": digest(review),
        "mechanical_binding_under_owner_delegation": True,
        "owner_review_of_future_hashes_claimed": False,
        "operator_or_capacity_attestation_created": False,
    }
    sampling_evidence = {
        "runtime_bounds": [digest(bound)],
        "technical_reviews": [digest(technical)],
        "enforcement": [digest(enforcement)],
        "coverage": [selection["anchors"]["coverage"]],
        "graphs": [digest(graph)],
        "methods": sorted(
            {
                selection["anchors"]["method"],
                selection["anchors"]["reviewer_role"],
                digest(review),
            }
        ),
        "logical": [selection["anchors"]["logical"]],
    }
    binding_review = {
        "version": diagnostic.REVIEW_VERSION,
        "scope": SCOPE,
        "disposition": "PASS",
        "configuration_sha256": digest(config),
        "report_sha256": digest(integration_text),
        "source_files": selection["source_files"],
        "sampling_evidence": sampling_evidence,
    }
    for item, phase in zip(campaigns, phases, strict=True):
        phase["start"] = {
            "schema_version": a.START,
            "scope": a.SCOPE,
            "campaign_id": digest(
                [selection_scope(selection), facts["job_id"], item["label"]]
            ),
            "profile_sha256": digest(item["profile"]),
            "plan_sha256": digest(item["plan"]),
            "rule_bundle_sha256": a.RULE_BUNDLE,
            "policy_freeze_record_sha256": role_hashes["policy_freeze"],
            "implementation_authorization_sha256": role_hashes["owner"],
            "implementation_review_sha256": digest(binding_review),
            "initial_workload_authority_sha256": role_hashes["owner"],
            "client_git_sha": selection["source_sha"],
            "runtime_inventory_sha256": digest(runtime_inventory),
            "created_utc": facts["created_utc"],
            "sampling_policy_sha256": a.POLICY_SHA,
            **a.assurance_fields(),
        }
    limits = selection["limits"]
    data = {
        "version": diagnostic.VERSION,
        "scope": SCOPE,
        "source_sha": selection["source_sha"],
        "selection": {
            "status": "ISSUED",
            "authority_sha256": pending_pointer,
            "resource_review_sha256": pending_pointer,
        },
        "limits": {
            "seconds": 7200,
            "maximum_bytes": limits["stages"]["B"]["bytes"],
            "maximum_creations": limits["stages"]["B"]["creations"],
            "rss_bytes": limits["rss_bytes"],
            "maximum_input_bytes": 4 * 2**20,
            "summary_reserve_bytes": 2**20,
            "native_helper_bytes_reserve": 128 * 2**20,
            "native_helper_creation_reserve": 64,
        },
        "configuration": config,
        "phases": phases,
        "runtime_inventory": runtime_inventory,
        "responses": replay["responses"],
    }
    resources_record = {
        "version": "stage12_wf_ap2_diagnostic_resources_v1",
        "scope": SCOPE,
        "source_sha": selection["source_sha"],
        "limits": data["limits"],
        "resources": resources,
        "status": "ISSUED",
        "capacity_entitlement_verified": True,
    }
    data["selection"]["resource_review_sha256"] = digest(resources_record)
    selection_record = {
        "version": "stage12_wf_ap2_diagnostic_selection_v1",
        "scope": SCOPE,
        "status": "ISSUED",
        "input_scope_sha256": diagnostic.input_scope(data),
        "source_sha": selection["source_sha"],
        "resource_review_sha256": digest(resources_record),
        "service_authority": False,
    }
    data["selection"]["authority_sha256"] = digest(selection_record)
    diagnostic.validate_envelope(data, selection["source_sha"], for_execution=True)
    diagnostic.validate_workloads(data)
    for item, phase in zip(campaigns, phases, strict=True):
        a.validate_plan(item["plan"], item["profile"])
        a.validate(phase["start"], a.START)
        m.validate_record(
            bound, item["profile"], phase["start"], a, m.configuration_scope(config)
        )
    return (
        data,
        roles,
        resources_record,
        selection_record,
        binding_review,
        integration_text,
        proof_objects,
    )


def bind(
    selection, selection_hash, *, clock=time.monotonic_ns, kernel_reader=observe_kernel
):
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("WF-AP2 delegated factual binding")
    start = clock()
    now = now_utc()
    check_window(selection, now)
    records = Records(selection["paths"]["records"])
    collection_guard(
        Path(selection["paths"]["source"]),
        Path(selection["paths"]["binding"]),
        Path(selection["paths"]["records"]),
        Path(selection["paths"]["review"]),
        extra_reads=(Path(selection["paths"]["bootstrap"]),),
    )
    review_raw = original(selection["paths"]["review"])
    review = parse(review_raw)
    facts, domain, _, logical = verify_release(
        selection,
        records,
        selection["paths"]["bootstrap"],
        review,
        now=now,
        kernel_reader=kernel_reader,
    )
    selected = selection["limits"]["stages"]["binding"]
    budget = Budget(
        selection["paths"]["binding"],
        max_bytes=selected["bytes"],
        max_creations=selected["creations"],
        deadline=start + selected["seconds"] * 10**9,
        clock=clock,
        check=lambda: check_window(selection, now_utc()),
    )
    verify_source(selection, budget.check)
    inventory = parse(original(Path(selection["paths"]["bootstrap"]) / "runtime.json"))
    need(digest(inventory) == facts["runtime_inventory_sha256"])
    result = materialize(
        selection, facts, domain, logical, inventory, review, records, budget
    )
    (
        data,
        roles,
        resource_record,
        selected_record,
        binding_review,
        review_text,
        proofs,
    ) = result
    # Persist prepared output in a new root; no overwrite/repair of partial B
    # publication. All roots/copies retain their original precharge on failure.
    evidence = Path(selection["paths"]["evidence"])
    need(
        evidence == budget.root / "evidence"
        and Path(selection["paths"]["input"]) == budget.root / "input.json"
    )
    budget.mkdir("evidence")
    budget.mkdir("evidence/sampling_evidence")
    for role, value in roles.items():
        budget.write("evidence/" + role + ".record", value)
    budget.write("evidence/diagnostic_resources.record", resource_record)
    budget.write("evidence/diagnostic_selection.record", selected_record)
    budget.write("evidence/integration_review.md", review_text)
    budget.write("evidence/integration_review.binding.json", binding_review)
    for token, value in proofs.items():
        need(digest(value) == token)
        budget.write("evidence/sampling_evidence/" + token + ".record", value)
    diagnostic = _module(
        Path(selection["paths"]["source"]),
        "stage12_wf_ap2_diagnostic.py",
        "ap2_final_binding_validator",
    )
    diagnostic.validate_grants(data, evidence)
    need(
        sha(original(selection["paths"]["review"])) == sha(review_raw),
        "AP2_ALLOCATION_REVIEW_CHANGED",
    )
    same_domain(domain, domain_from_kernel(kernel_reader()))
    verify_stage(
        selection["paths"]["bootstrap"],
        expected_status="BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED",
    )
    verify_source(selection, budget.check)
    # Reopen the review and all capacity/coverage originals, and remeasure the
    # same domain after materialization. A stale pre-binding acceptance cannot
    # issue the final input after a change or expiry.
    verify_release(
        selection,
        records,
        selection["paths"]["bootstrap"],
        parse(original(selection["paths"]["review"])),
        now=now_utc(),
        kernel_reader=kernel_reader,
    )
    # Every output, including the input, shares the one precharged transaction.
    input_hash = budget.write("input.json", data)
    budget.write(
        "binding_result.json",
        {
            "version": "stage12_wf_ap2_binding_result_v1",
            "selection_sha256": selection_hash,
            "source_sha": selection["source_sha"],
            "input_sha256": input_hash,
            "review_binding_sha256": digest(binding_review),
            "independent_fact_review_sha256": sha(review_raw),
            "bootstrap_manifest_sha256": review["bootstrap_manifest_sha256"],
            "status": "BOUND_AFTER_INDEPENDENT_VERIFICATION",
            "actual_domain": domain,
            "binding_elapsed_ns": clock() - start,
        },
    )
    budget.close("BOUND_AFTER_INDEPENDENT_VERIFICATION")
    verify_stage(budget.root, expected_status="BOUND_AFTER_INDEPENDENT_VERIFICATION")
    budget.check()
    return {"input_sha256": input_hash, "review_binding_sha256": digest(binding_review)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("ready", "collect", "bind"))
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    args = parser.parse_args()
    try:
        selected = load_selection(args.selection, args.selection_sha256)
        if args.operation == "ready":
            result = ready(selected, Records(selected["paths"]["records"]), now_utc())
        else:
            sys.path.insert(0, str(Path(selected["paths"]["source"]) / "src"))
            result = (
                collect(selected, args.selection, args.selection_sha256)
                if args.operation == "collect"
                else bind(selected, args.selection_sha256)
            )
        print(json.dumps(result, sort_keys=True))
        return 0
    except (AllocationError, OSError, ValueError, TypeError, KeyError):
        print("AP2_ALLOCATION_GATED_OR_INCOMPLETE", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

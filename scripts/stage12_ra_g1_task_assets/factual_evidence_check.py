#!/usr/bin/env python3
"""Task-scoped portable review of original RA-G1 COLLECTOR evidence.

This program produces findings, never an approval, release, or runtime record.
Copied originals are checked as copied originals. Native inode/time identities
are preserved as source-owned proof bindings, never replaced by local stat data.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import sys
import tarfile
import time
from types import SimpleNamespace
from datetime import datetime, timezone

SCHEMA = "stage12_task_factual_checker_input_v1"
MAX_FILES = 512
MAX_ORIGINAL_BYTES = 16 * 2**20
MAX_ARCHIVE_BYTES = 16 * 2**20
MAX_SECONDS = 120
MAX_RSS = 768 * 2**20
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
REFERENCES = {"selection", "resource_selection", "resource_review", "originals_tar", "originals_inventory"}
CONFIG_KEYS = {"schema_version", "source_sha", "source_dir", "job_id", "evidence_use", "originals_dir", "first_start_codec"} | REFERENCES
SAFE_CODES = frozenset({
    "RA_G1_FIELDS", "RA_G1_CANONICAL_REQUIRED", "RA_G1_PROTOCOL", "RA_G1_ORIGINAL_CHANGED",
    "RA_G1_MONITOR_GAP", "RA_G1_MONITOR_INCOMPLETE", "RA_G1_READ_LIMIT", "RA_G1_COUNTER_LIMIT",
    "RA_G1_BOOTSTRAP_REQUIRED", "RA_G1_BOOTSTRAP_EVIDENCE", "RA_G1_BOOTSTRAP_LIMIT",
    "RA_G1_DEADLINE", "RA_G1_CHILD_FAILED", "RA_G1_SELECTION_BINDING", "RA_G1_SCOPE",
    "RA_G1_CAPACITY_BINDING", "RA_G1_CAPACITY_VALUE_CHANGED", "RA_G1_CAPACITY_ORIGINAL_CHANGED",
    "RA_G1_ACCOUNTING_UNAVAILABLE", "RA_G1_SHARED_MARGIN", "RA_G1_NATIVE_DISCOVERY",
    "RA_G1_SYNTHETIC_DENIED", "RA_G1_PROCESS_SCOPE", "RA_G1_REQUIRED_READING",
})


LOCAL_CODES = frozenset(('ADMIN_BINDING', 'ARCHIVE_DIRECTORY_MEMBERSHIP', 'ARCHIVE_DIRECTORY_MODE', 'ARCHIVE_HASH', 'ARCHIVE_ITEM_LIMIT', 'ARCHIVE_LENGTH', 'ARCHIVE_MEMBERSHIP', 'ARCHIVE_METADATA', 'BACKEND_HASH_BINDING', 'BACKEND_INVENTORY', 'BOOTSTRAP_BINDING', 'BOOTSTRAP_CLOCKS', 'BOOTSTRAP_FIELDS', 'BOOTSTRAP_PROTOCOL_BINDING', 'BOUND_FILE_HASH', 'CAPACITY_CLOCK_BINDING', 'CAPACITY_PATH_BINDING', 'CHECKER_DEADLINE', 'CHECKER_RSS_LIMIT', 'CONFIG_IDENTITY', 'CONFIG_SCOPE', 'CONFIG_SHAPE', 'CONTEXT_BINDING', 'CONTEXT_PATH_BINDING', 'COUNTER_LIMIT', 'COUNTER_MONOTONIC', 'COUNTER_SHAPE', 'DIRECTORY_DEPTH', 'DIRECTORY_ITEM_LIMIT', 'DUPLICATE_JSON_KEY', 'ENVIRONMENT_CHANGED', 'ENVIRONMENT_CONTEXT_BINDING', 'EXACT_DIRECTORY_MEMBERSHIP', 'EXACT_ORIGINAL_MEMBERSHIP', 'FILE_LIMIT', 'FIRST_START_BINDING', 'FROZEN_ORIGINAL_INVENTORY', 'FULL_MONITOR_INVENTORY', 'HANDOFF_BINDING', 'INVENTORY_DUPLICATE', 'INVENTORY_LIMIT', 'INVENTORY_SHAPE', 'JOB_SOURCE_BINDING', 'KERNEL_TIMESTAMP_BOUNDS', 'LOCAL_ANCESTOR_CHANGED', 'LOCAL_ANCESTOR_TYPE', 'LOCAL_FILE_CHANGED', 'LOCAL_FILE_IDENTITY', 'LOCAL_FILE_TYPE', 'LOCAL_PRIVATE_MODE', 'LOCAL_PRIVATE_ROOT', 'LOCAL_READ_LENGTH', 'LOCAL_SYMLINK', 'MISSING_MONITOR_PREFIX', 'MISSING_ORIGINAL', 'MODULE_SOURCE_MISMATCH', 'MONITOR_ROW_BOUND', 'NONCANONICAL_JSON', 'NONFINITE_JSON', 'NONRESET_PHASE_DEADLINE', 'OFFLINE_PROCESS_NETWORK_DENIED', 'ORIGINAL_BYTE_LIMIT', 'ORIGINAL_CLOSURE_ORDER', 'ORIGINAL_LENGTH', 'ORIGINAL_MODE', 'ORIGINAL_OWNER_BINDING', 'ORIGINAL_WINDOW_BINDING', 'PREFIX_INVENTORY', 'RAW_ORIGINAL_MEMBERSHIP', 'REFERENCE_SHAPE', 'REPORT_LIMIT', 'REPORT_WRITE', 'REQUIRED_SOURCE_MEMBER', 'RESOURCE_ACCOUNTING_BINDING', 'RESOURCE_BINDING', 'RESOURCE_REVIEW_BINDING', 'REVIEW_BINDING', 'REVIEW_BOOTSTRAP_CLOCKS', 'REVIEW_NONRESET_DEADLINE', 'REVIEW_ORIGINAL_MEMBERSHIP', 'REVIEW_PREFIX_BINDING', 'REVIEW_START_CODEC_BINDING', 'REVIEW_START_CODEC_MISSING', 'REVIEW_START_CODEC_REFERENCE', 'REVIEW_START_CODEC_SIZE', 'REVIEW_START_RAW_BINDING', 'RUNTIME_BINDING', 'RUNTIME_ENVIRONMENT_BINDING', 'SECRET_PROTECTED_PATH_DENIED', 'SECRET_SOURCE_MEMBER', 'SOURCE_BINDING', 'SOURCE_BYTES', 'SOURCE_DIRECTORY', 'SOURCE_INVENTORY', 'SUPERVISOR_TAIL_BINDING', 'SUPERVISOR_WAIT_PROOF', 'UNEXPECTED_ORIGINAL', 'UNEXPECTED_REVIEW_CODEC', 'UNSAFE_LOCAL_PATH', 'UNSAFE_MEMBER', 'WAIT_EXACT_INTEGER_TYPES'))


class CheckFailure(Exception):
    pass


def require(value, code):
    if not value:
        raise CheckFailure(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def parse(raw):
    def pairs(items):
        require(len({key for key, _ in items}) == len(items), "DUPLICATE_JSON_KEY")
        return dict(items)
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(CheckFailure("NONFINITE_JSON")))
    require(canonical(value) == raw, "NONCANONICAL_JSON")
    return value


def uint(value):
    return type(value) is int and 0 <= value < 2**64


def sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def relative_name(value):
    require(type(value) is str and value and "\\" not in value and "\x00" not in value, "UNSAFE_MEMBER")
    p = PurePosixPath(value)
    require(bool(p.parts) and not p.is_absolute() and str(p) == value and all(x not in (".", "..") for x in p.parts), "UNSAFE_MEMBER")
    return value


def no_links(path):
    p = Path(path)
    require(p.is_absolute() and str(p) == os.path.abspath(p), "UNSAFE_LOCAL_PATH")
    for current in (p, *p.parents):
        require(not stat.S_ISLNK(current.lstat().st_mode), "LOCAL_SYMLINK")
    return p


def directory_chain(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.abspath(path) and len(path.parts) <= 64, "UNSAFE_LOCAL_PATH")
    chain = []
    for current in (path, *path.parents):
        info = current.lstat()
        require(not stat.S_ISLNK(info.st_mode), "LOCAL_SYMLINK")
        require(stat.S_ISDIR(info.st_mode), "LOCAL_ANCESTOR_TYPE")
        chain.append((str(current), info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid))
    return tuple(chain)


class Budget:
    def __init__(self):
        self.start = time.monotonic_ns()
        self.checks = self.read_calls = self.read_bytes = 0

    def check(self):
        self.checks += 1
        require(time.monotonic_ns() - self.start < MAX_SECONDS * 10**9, "CHECKER_DEADLINE")
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        require(rss * (1 if sys.platform == "darwin" else 1024) <= MAX_RSS, "CHECKER_RSS_LIMIT")

    def charge(self, calls, size):
        self.read_calls += calls
        self.read_bytes += size
        self.check()


def read_file(path, limit, budget, *, private=True, expected=None):
    path = no_links(path)
    ancestors = directory_chain(path.parent)
    before_path = path.lstat()
    budget.check()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(all(getattr(before_path, k) == getattr(before, k) for k in IDENTITY_FIELDS), "LOCAL_FILE_CHANGED")
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.geteuid(), "LOCAL_FILE_IDENTITY")
        require(not private or stat.S_IMODE(before.st_mode) == 0o600, "LOCAL_PRIVATE_MODE")
        require(0 <= before.st_size <= limit, "FILE_LIMIT")
        result = bytearray()
        while True:
            budget.check()
            raw = os.read(fd, min(65536, limit + 1 - len(result)))
            budget.charge(1, len(raw))
            if not raw:
                break
            result.extend(raw)
            require(len(result) <= limit, "FILE_LIMIT")
        after, current = os.fstat(fd), path.stat(follow_symlinks=False)
        require(len(result) == before.st_size, "LOCAL_READ_LENGTH")
        require(all(getattr(before, k) == getattr(after, k) == getattr(current, k) for k in IDENTITY_FIELDS), "LOCAL_FILE_CHANGED")
        require(directory_chain(path.parent) == ancestors, "LOCAL_ANCESTOR_CHANGED")
        require(expected is None or hashlib.sha256(result).hexdigest() == expected, "BOUND_FILE_HASH")
        return bytes(result)
    finally:
        os.close(fd)


def read_reference(spec, limit, budget):
    require(type(spec) is dict and set(spec) == {"path", "sha256"} and sha(spec["sha256"]), "REFERENCE_SHAPE")
    return read_file(spec["path"], limit, budget, expected=spec["sha256"])


def source_metadata(selection, budget):
    """Validate the entire finite metadata set before opening source content."""
    rows = selection["source_files"]
    require(type(rows) is list and 1 <= len(rows) <= 2048, "SOURCE_INVENTORY")
    names = []
    for row in rows:
        budget.check()
        require(type(row) is dict and set(row) == {"path", "bytes", "sha256"} and sha(row["sha256"]) and uint(row["bytes"]) and row["bytes"] <= 4 * 2**20, "SOURCE_INVENTORY")
        name = relative_name(row["path"])
        require(not any(x in {".ssh", "credentials", "secrets", "HOLDOUT"} for x in PurePosixPath(name).parts), "SECRET_SOURCE_MEMBER")
        names.append(name)
    require(names == sorted(set(names)), "SOURCE_INVENTORY")
    require(sum(r["bytes"] for r in rows) <= 64 * 2**20, "SOURCE_INVENTORY")
    for name in ("scripts/stage12_ra_g1_allocation.py", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_assurance.py", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_monitor.py", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_execution.py"):
        require(name in names, "REQUIRED_SOURCE_MEMBER")
    return rows


def load_modules(source, selection, budget):
    rows = source_metadata(selection, budget)
    source = no_links(source)
    require(source.is_dir(), "SOURCE_DIRECTORY")
    # No filesystem acceptance is cached: all selected original source bytes are
    # freshly read, hashed, identity-checked and checked for EOF on this run.
    for row in rows:
        raw = read_file(source / row["path"], 4 * 2**20, budget, private=False, expected=row["sha256"])
        require(len(raw) == row["bytes"], "SOURCE_BYTES")
    sys.path.insert(0, str(source / "src"))
    spec = importlib.util.spec_from_file_location("stage12_task_original_allocation", source / "scripts/stage12_ra_g1_allocation.py")
    ctl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ctl)
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    for module in (a, m, e):
        require(Path(module.__file__).resolve().is_relative_to(source / "src"), "MODULE_SOURCE_MISMATCH")
    return ctl, a, m, e


def inventory_originals(config, budget):
    inventory_raw = read_reference(config["originals_inventory"], 1024 * 1024, budget)
    rows = parse(inventory_raw)
    require(type(rows) is list and 1 <= len(rows) <= MAX_FILES, "INVENTORY_LIMIT")
    indexed = {}
    for row in rows:
        require(type(row) is dict and set(row) == {"path", "bytes", "sha256", "original_mode", "original_uid", "original_gid"}, "INVENTORY_SHAPE")
        name = relative_name(row["path"])
        require(name not in indexed and uint(row["bytes"]) and sha(row["sha256"]), "INVENTORY_DUPLICATE")
        require(row["original_mode"] == 0o600 and uint(row["original_uid"]) and uint(row["original_gid"]), "ORIGINAL_MODE")
        indexed[name] = row
    require(sum(r["bytes"] for r in rows) <= MAX_ORIGINAL_BYTES, "ORIGINAL_BYTE_LIMIT")
    root = no_links(config["originals_dir"])
    require(root.is_dir() and stat.S_IMODE(root.stat().st_mode) == 0o700, "LOCAL_PRIVATE_ROOT")
    actual = set()
    actual_dirs = set()
    expected_dirs = {str(p) for name in indexed for p in PurePosixPath(name).parents if str(p) != "."}
    # Fixed depth and finite item count; never materialize an arbitrary walk.
    pending = [(root, 0)]
    visits = 0
    while pending:
        folder, depth = pending.pop()
        require(depth <= 4, "DIRECTORY_DEPTH")
        with os.scandir(folder) as stream:
            for entry in stream:
                visits += 1
                budget.check()
                require(visits <= MAX_FILES + 32, "DIRECTORY_ITEM_LIMIT")
                require(not entry.is_symlink(), "LOCAL_SYMLINK")
                if entry.is_dir(follow_symlinks=False):
                    require(stat.S_IMODE(entry.stat(follow_symlinks=False).st_mode) == 0o700, "LOCAL_PRIVATE_ROOT")
                    actual_dirs.add(str(Path(entry.path).relative_to(root)))
                    pending.append((Path(entry.path), depth + 1))
                else:
                    require(entry.is_file(follow_symlinks=False), "LOCAL_FILE_TYPE")
                    actual.add(str(Path(entry.path).relative_to(root)))
    require(actual == set(indexed), "EXACT_ORIGINAL_MEMBERSHIP")
    require(actual_dirs == expected_dirs, "EXACT_DIRECTORY_MEMBERSHIP")
    for name, row in indexed.items():
        raw = read_file(root / name, MAX_ORIGINAL_BYTES, budget, expected=row["sha256"])
        require(len(raw) == row["bytes"], "ORIGINAL_LENGTH")
    archive_path = no_links(config["originals_tar"]["path"])
    archive_raw = read_reference(config["originals_tar"], MAX_ARCHIVE_BYTES, budget)
    # Hash the bounded archive, then stream members without a getmembers list or
    # extraction. No external tar, subprocess, native root remapping, or links.
    del archive_raw
    found = set()
    archive_dirs = set()
    with tarfile.open(archive_path, "r|") as archive:
        for ordinal, member in enumerate(archive, 1):
            budget.check()
            require(ordinal <= MAX_FILES + 32, "ARCHIVE_ITEM_LIMIT")
            name = relative_name(member.name.rstrip("/"))
            if member.isdir():
                require(member.mode == 0o700 and name in expected_dirs and name not in archive_dirs, "ARCHIVE_DIRECTORY_MODE")
                archive_dirs.add(name)
                continue
            require(member.isfile() and name in indexed and name not in found, "ARCHIVE_MEMBERSHIP")
            row = indexed[name]
            require(member.mode == row["original_mode"] and member.uid == row["original_uid"] and member.gid == row["original_gid"] and member.size == row["bytes"], "ARCHIVE_METADATA")
            stream = archive.extractfile(member)
            h = hashlib.sha256()
            count = 0
            while True:
                raw = stream.read(65536)
                budget.charge(1, len(raw))
                if not raw:
                    break
                count += len(raw)
                require(count <= row["bytes"], "ARCHIVE_LENGTH")
                h.update(raw)
            require(count == row["bytes"] and h.hexdigest() == row["sha256"], "ARCHIVE_HASH")
            found.add(name)
    require(found == set(indexed), "ARCHIVE_MEMBERSHIP")
    require(archive_dirs == expected_dirs, "ARCHIVE_DIRECTORY_MEMBERSHIP")
    # Independent final archive read/hash detects source replacement during the
    # streaming pass, without trusting cached size or modification times.
    read_reference(config["originals_tar"], MAX_ARCHIVE_BYTES, budget)
    return root, indexed


def validate_facts(config, budget):
    require(type(config) is dict and set(config) == CONFIG_KEYS and config["schema_version"] == SCHEMA, "CONFIG_SHAPE")
    require(type(config["source_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}", config["source_sha"]) and type(config["job_id"]) is int and config["job_id"] > 0, "CONFIG_IDENTITY")
    require(config["evidence_use"] in {"HISTORICAL_REHEARSAL", "FRESH_SAME_ALLOCATION_FINDINGS_ONLY"}, "CONFIG_SCOPE")
    selection = parse(read_reference(config["selection"], 4 * 2**20, budget))
    require(selection["source_sha"] == config["source_sha"], "SOURCE_BINDING")
    ctl, a, m, e = load_modules(config["source_dir"], selection, budget)
    ctl.validate_selection(selection)
    selected = ctl.parse(read_reference(config["resource_selection"], 1024 * 1024, budget))
    a.validate_selection(selected)
    review = ctl.parse(read_reference(config["resource_review"], 1024 * 1024, budget))
    require(digest(selected) == selection["resource_selection_sha256"] and selected["source_git_sha"] == config["source_sha"] and selected["scope"] == selection["scope"] == "REPRESENTATIVE_NO_SERVICE", "RESOURCE_BINDING")
    require(digest(review) == selection["records"]["resource_review"] and review["scope"] == "REPRESENTATIVE_NO_SERVICE", "RESOURCE_REVIEW_BINDING")
    require(review["disposition"] == "PASS" and review["source_sha"] == config["source_sha"] and review["source_files"] == len(selection["source_files"]) and review["source_bytes"] == sum(r["bytes"] for r in selection["source_files"]), "RESOURCE_REVIEW_BINDING")
    for key in ("descriptor_inventory_sha256", "workload_graph_sha256", "paths_sha256"):
        require(selected[key] == review[key], "RESOURCE_REVIEW_BINDING")
    require(review["accounting_inventory_sha256"] == digest(selection["accounting_inventory"]), "RESOURCE_ACCOUNTING_BINDING")
    root, inventory = inventory_originals(config, budget)
    def original(name, limit=65536):
        require(name in inventory, "MISSING_ORIGINAL")
        return ctl.parse(read_file(root / name, limit, budget, expected=inventory[name]["sha256"]))
    boot, manifest = original("bootstrap/bootstrap.record", limit=4 * 2**20), original("bootstrap/manifest.record")
    require(set(boot) == {"capacity", "capacity_method", "capacity_originals", "capacity_restrictions", "counters", "created_utc", "ended_mono_ns", "facts", "job_id", "kernel_originals", "resource_execution", "runtime_inventory", "scope", "second_facts", "second_kernel_originals", "source_sha", "started_mono_ns"}, "BOOTSTRAP_FIELDS")
    ctl.validate_bootstrap_originals(SimpleNamespace(s=selection), canonical(boot), canonical(manifest))
    require(selection["valid_from"] <= boot["created_utc"] <= selection["valid_until"] and selected["valid_from"] <= boot["created_utc"] <= selected["valid_until"], "ORIGINAL_WINDOW_BINDING")
    datetime.strptime(boot["created_utc"], "%Y-%m-%dT%H:%M:%S.%fZ")
    context, wait, handoff = original("context.record"), original("collector.wait.record"), original("collector.handoff.record")
    e.validate_supervisor_context(context)
    require(boot["job_id"] == str(config["job_id"]) and context["slurm_job_id"] == config["job_id"] and boot["source_sha"] == context["source_git_sha"] == config["source_sha"], "JOB_SOURCE_BINDING")
    require(context["selection_sha256"] == digest(selected) and context["run_nonce"] == selection["intent_id"], "CONTEXT_BINDING")
    require(context["private_paths"] == {"allocation_root": selection["paths"]["allocation_root"], "resource_evidence_root": selection["paths"]["output"], "scratch_root": selection["paths"]["allocation_root"]} and context["protected_paths"] is None, "CONTEXT_PATH_BINDING")
    require(boot["resource_execution"] == {"schema_version": "stage12_resource_execution_request_ra_g1_v1", "supervisor_context_path": selection["paths"]["context"], "supervisor_context_sha256": digest(context)}, "CONTEXT_BINDING")
    for key in ("facts", "second_facts"):
        a.validate_environment_originals(boot[key], boot["kernel_originals" if key == "facts" else "second_kernel_originals"])
        for field in ("boot_id", "cgroup_namespace_inode", "mount_namespace_inode"):
            require(boot[key][field] == context[field], "ENVIRONMENT_CONTEXT_BINDING")
    require(all(boot["facts"][k] == boot["second_facts"][k] for k in ("boot_id", "cgroup_namespace_inode", "mount_namespace_inode", "visible_identity_inventory_sha256")), "ENVIRONMENT_CHANGED")
    for originals in (boot["kernel_originals"], boot["second_kernel_originals"]):
        require(all(boot["started_mono_ns"] <= r["acquired_mono_ns"] <= boot["ended_mono_ns"] for r in originals["records"].values()), "KERNEL_TIMESTAMP_BOUNDS")
    capacity = boot["capacity"]
    a.validate_capacity(capacity, selection_sha256=digest(selected), scope=selected["scope"])
    a.validate_capacity_originals(capacity, boot["capacity_originals"]["root"], boot["capacity_originals"]["statvfs"], boot["capacity_method"], boot["capacity_restrictions"])
    require(boot["capacity_originals"]["root"][0][0] == selection["paths"]["allocation_root"] and capacity["owner_reported_approval_sha256"] == selection["records"]["project_approval"], "CAPACITY_PATH_BINDING")
    cap_time = capacity["bavail_bytes"]["acquired_mono_ns"]
    require(cap_time == capacity["favail"]["acquired_mono_ns"] and boot["started_mono_ns"] <= cap_time <= boot["ended_mono_ns"], "CAPACITY_CLOCK_BINDING")
    a.check_capacity(capacity, next_write_bytes=240 * 2**20, next_creations=1544, now_mono_ns=cap_time)
    runtime = boot["runtime_inventory"]
    require(runtime["job_id"] == str(config["job_id"]) and runtime["scientific_identity_verified"] is False and runtime["resource_sampling_is_service_monitoring"] is False, "RUNTIME_BINDING")
    backends = runtime["wf_ap2_runtime"]["backends"]
    require(type(backends) is list and len(backends) == len(selection["accounting_inventory"]["backends"]) == 5, "BACKEND_INVENTORY")
    require({r["module"]: r["binary_sha256"] for r in backends} == {r["module"]: r["sha256"] for r in selection["accounting_inventory"]["backends"]} and len({r["module"] for r in backends}) == len(backends), "BACKEND_HASH_BINDING")
    require(runtime["wf_ap2_runtime"]["environment_observation_sha256"] == digest(boot["facts"]), "RUNTIME_ENVIRONMENT_BINDING")
    records = {n: original("collector_resources/" + n + ".record") for n in ("admin_binding", "bootstrap_prefix", "preopening", "opener_return", "monitor_terminal", "worker_validation", "supervisor_terminal")}
    binding, bootstrap, pre, opener, terminal, worker, tail = (records[n] for n in ("admin_binding", "bootstrap_prefix", "preopening", "opener_return", "monitor_terminal", "worker_validation", "supervisor_terminal"))
    e.AdministrativePhaseSession.validate_binding(None, binding)
    require(binding["role"] == "COLLECTOR" and binding["phase_id"] == 6 and binding["source_git_sha"] == config["source_sha"] and binding["selection_sha256"] == digest(selected) and binding["supervisor_context_sha256"] == digest(context), "ADMIN_BINDING")
    stage = next(r for r in selected["limits"]["stages"] if r["id"] == 6)
    require(binding["deadline_mono_ns"] == binding["scope_start_mono_ns"] + stage["deadline_ms"] * 10**6, "NONRESET_PHASE_DEADLINE")
    require(type(wait.get("exit_code")) is int and type(wait.get("wait_status")) is int, "WAIT_EXACT_INTEGER_TYPES")
    ctl.validate_wait_record(wait, source_sha=config["source_sha"], allocation_selection_sha256=digest(selection), supervisor_pid=context["supervisor"]["pid"], process_pid=binding["process_pid"])
    require(all(row["original_uid"] == context["worker_uid"] for row in inventory.values()) and binding["process_uid"] == context["worker_uid"], "ORIGINAL_OWNER_BINDING")
    require(handoff["source_sha"] == config["source_sha"] and handoff["allocation_selection_sha256"] == digest(selection) and handoff["resource_selection_sha256"] == digest(selected) and handoff["supervisor_context_sha256"] == digest(context) and handoff["process_pid"] == wait["pid"] and handoff["stage"] == "collect" and handoff["predecessor_handoff_sha256"] is None, "HANDOFF_BINDING")
    require(handoff["administrative_sessions"] == [{"role": "COLLECTOR", "phase_id": 6, "root": str(Path(selection["paths"]["allocation_root"]) / "collector_resources"), "binding_sha256": digest(binding), "worker_validation_sha256": digest(worker)}], "HANDOFF_BINDING")
    carried = ctl.handoff_counters(handoff, len(canonical(handoff)))
    require(all(uint(v) for v in boot["counters"].values()) and set(boot["counters"]) == {"checks", "creations", "read_bytes", "read_calls", "write_bytes"}, "COUNTER_SHAPE")
    for bk, hk in (("checks", "checks"), ("read_bytes", "source_read_bytes"), ("read_calls", "source_read_calls")):
        require(boot["counters"][bk] <= handoff["counter_prefix"][hk] <= carried[hk], "COUNTER_MONOTONIC")
    for key, maximum in (("checks", selection["accounting"]["check_calls"]), ("source_read_calls", selection["accounting"]["original_read_calls"]), ("source_read_bytes", selection["accounting"]["original_read_bytes"])):
        require(uint(carried[key]) and carried[key] <= maximum, "COUNTER_LIMIT")
    for key, maximum in (("bytes", selected["limits"]["monitor_bytes"]), ("creations", selected["limits"]["monitor_creations"]), ("rows", selected["limits"]["monitor_rows"])):
        require(uint(carried["monitor_usage"][key]) and carried["monitor_usage"][key] <= maximum, "COUNTER_LIMIT")
    a.shape(bootstrap, a.BOOTSTRAP_EVIDENCE_SCHEMA)
    a.validate_bootstrap_adoption(bootstrap["adoption_original"], selected)
    require(bootstrap["binding_sha256"] == digest(binding) and bootstrap["selection_sha256"] == digest(selected) and bootstrap["phase_id"] == 6 and bootstrap["role"] == "COLLECTOR" and bootstrap["adoption_original"] == selection["bootstrap_prefix_adoption"] and bootstrap["bootstrap_adoption_sha256"] == selected["bootstrap_prefix_adoption_sha256"] and bootstrap["bootstrap_policy_sha256"] == selected["bootstrap_prefix_policy_sha256"], "BOOTSTRAP_BINDING")
    entry, end, enter, exit_ns, ack, deadline = (bootstrap[k] for k in ("source_entry_mono_ns", "bootstrap_end_mono_ns", "first_start_enter_mono_ns", "first_start_exit_mono_ns", "first_start_ack_mono_ns", "phase_deadline_mono_ns"))
    require(entry == binding["scope_start_mono_ns"] and deadline == binding["deadline_mono_ns"] and entry <= end <= enter <= exit_ns <= ack < deadline and ack - entry <= 30 * 10**9 and enter - end <= 10**9 and exit_ns - enter <= 10**9 and bootstrap["first_start_seq"] == 1, "BOOTSTRAP_CLOCKS")
    require(terminal["coverage_start_ns"] == end and all(records[n].get("bootstrap_evidence_sha256") == digest(bootstrap) for n in ("preopening", "opener_return", "monitor_terminal", "worker_validation", "supervisor_terminal")), "BOOTSTRAP_PROTOCOL_BINDING")
    for n in ("preopening", "opener_return", "monitor_terminal", "supervisor_terminal"):
        m.validate(records[n])
    # Native supervisor-tail time is the only replay clock. This is explicitly
    # historical protocol reconstruction, never current Mac/Goethe time.
    protocol = m.reopen_phase_protocol(binding_sha256=digest(binding), selection_sha256=digest(selected), phase_id=6, closure=pre, opener_return=opener, monitor_terminal=terminal, deadline_ns=deadline, check=budget.check, clock_ns=lambda: tail["tail_check_start_ns"])
    e.validate_worker_validation(worker, protocol=protocol)
    frozen = [{"path": selection["paths"]["bootstrap"] + "/bootstrap.record", "sha256": digest(boot)}, {"path": selection["paths"]["bootstrap"] + "/manifest.record", "sha256": digest(manifest)}, {"path": selection["paths"]["context"], "sha256": digest(context)}]
    require(digest(frozen) == pre["original_inventory_sha256"] == opener["frozen_data_inventory_sha256"], "FROZEN_ORIGINAL_INVENTORY")
    seed = digest({"schema_version": "stage12_resource_monitor_seed_ra_g1_v1", "binding_sha256": digest(binding), "selection_sha256": digest(selected), "phase_id": 6})
    coverage = m.Coverage(binding_sha256=digest(binding), selection_sha256=digest(selected), phase_id=6, seed_sha256=seed, selected=selected, scope_start_ns=end)
    max_rows = math.ceil(stage["deadline_ms"] / selected["monitor"]["period_ms"]) + 2
    require(max_rows <= selected["limits"]["monitor_rows"] and max_rows <= MAX_FILES - 13, "MONITOR_ROW_BOUND")
    raw_names = set()
    prefix_found = False
    first = None
    for row in m.read_observations(root / "collector_resources/observations.bin", maximum_rows=max_rows, check=budget.check, charge_read=budget.charge):
        require(coverage.seq < max_rows, "MONITOR_ROW_BOUND")
        name = "collector_resources/originals/" + row["visible_identity_inventory_sha256"] + ".record"
        require(name in inventory and name not in raw_names, "RAW_ORIGINAL_MEMBERSHIP")
        raw_names.add(name)
        raw_original = m.read_original_observation(root / name, expected_sha256=row["visible_identity_inventory_sha256"], check=budget.check, charge_read=budget.charge)
        m.validate_original_observation(raw_original, observation=row)
        if first is None:
            first = row
            require(row["seq"] == 1 and row["kind"] == "START" and digest(row) == bootstrap["first_start_record_sha256"] and row["visible_identity_inventory_sha256"] == bootstrap["first_start_original_sha256"] and row["enter_mono_ns"] == enter and row["exit_mono_ns"] == exit_ns, "FIRST_START_BINDING")
        coverage.add(row)
        if coverage.seq == pre["last_seq"]:
            require(coverage.inventory_sha256() == pre["original_observation_prefix_sha256"] == terminal["prefix_H0_sha256"] and digest(row["counters"]) == pre["counter_totals_sha256"] and coverage.max_gap == pre["max_observed_gap_ns"], "PREFIX_INVENTORY")
            prefix_found = True
    require(first is not None and prefix_found, "MISSING_MONITOR_PREFIX")
    require(raw_names == {n for n in inventory if n.startswith("collector_resources/originals/")}, "RAW_ORIGINAL_MEMBERSHIP")
    coverage.require_complete(opener_return_ns=opener["actual_opener_return_ns"], last_ack_ns=terminal["last_ack_ns"])
    require(coverage.seq == terminal["last_seq"] == worker["verified_original_rows"] == handoff["counter_prefix"]["monitor_usage"]["rows"] and coverage.max_gap == terminal["max_gap_ns"] == worker["max_gap_ns"] and coverage.inventory_sha256() == terminal["full_monitor_inventory_sha256"] == worker["full_monitor_inventory_sha256"] and coverage.head == terminal["final_observation_sha256"] and coverage.last_exit == terminal["final_observation_ns"], "FULL_MONITOR_INVENTORY")
    wait_core = {k: wait[k] for k in ("pid", "wait_status", "acquired_mono_ns")}
    require(tail["child_result_original_sha256"] == digest(wait_core) and tail["child_exit_code"] == 0 and tail["child_signal"] is None and tail["first_failure"] is None and tail["cleanup_failure"] is None and tail["disposition"] == "COMPLETE_SELECTED_SCOPE", "SUPERVISOR_WAIT_PROOF")
    require(tail["binding_sha256"] == digest(binding) and tail["selection_sha256"] == digest(selected) and tail["phase_id"] == 6 and tail["opener_return_sha256"] == digest(opener) and tail["monitor_terminal_sha256"] == digest(terminal), "SUPERVISOR_TAIL_BINDING")
    require(worker["first_pass_end_ns"] <= wait["acquired_mono_ns"] <= tail["tail_check_start_ns"] <= tail["tail_check_end_ns"] <= tail["terminal_prewrite_ns"] < deadline and terminal["writer_state"] == "HEALTHY_RELEASED" and opener["opener_disposition"] == "DATA_OPENED", "ORIGINAL_CLOSURE_ORDER")
    review_timing = None
    review_names = {n for n in inventory if n.startswith("review_resources/")}
    if review_names or config["evidence_use"] == "FRESH_SAME_ALLOCATION_FINDINGS_ONLY":
        review_binding = original("review_resources/admin_binding.record")
        review_prefix = original("review_resources/bootstrap_prefix.record")
        e.AdministrativePhaseSession.validate_binding(None, review_binding)
        a.shape(review_prefix, a.BOOTSTRAP_EVIDENCE_SCHEMA)
        a.validate_bootstrap_adoption(review_prefix["adoption_original"], selected)
        review_stage = next(r for r in selected["limits"]["stages"] if r["id"] == 7)
        require(review_binding["role"] == "REVIEW" and review_binding["phase_id"] == 7 and review_binding["source_git_sha"] == config["source_sha"] and review_binding["selection_sha256"] == digest(selected) and review_binding["supervisor_context_sha256"] == digest(context) and review_binding["process_uid"] == context["worker_uid"], "REVIEW_BINDING")
        require(review_binding["deadline_mono_ns"] == review_binding["scope_start_mono_ns"] + review_stage["deadline_ms"] * 10**6, "REVIEW_NONRESET_DEADLINE")
        require(review_prefix["role"] == "REVIEW" and review_prefix["phase_id"] == 7 and review_prefix["binding_sha256"] == digest(review_binding) and review_prefix["selection_sha256"] == digest(selected) and review_prefix["bootstrap_policy_sha256"] == selected["bootstrap_prefix_policy_sha256"] and review_prefix["bootstrap_adoption_sha256"] == selected["bootstrap_prefix_adoption_sha256"] and review_prefix["adoption_original"] == selection["bootstrap_prefix_adoption"], "REVIEW_PREFIX_BINDING")
        rp_entry, rp_end, rp_enter, rp_exit, rp_ack, rp_deadline = (review_prefix[k] for k in ("source_entry_mono_ns", "bootstrap_end_mono_ns", "first_start_enter_mono_ns", "first_start_exit_mono_ns", "first_start_ack_mono_ns", "phase_deadline_mono_ns"))
        require(rp_entry == review_binding["scope_start_mono_ns"] and rp_deadline == review_binding["deadline_mono_ns"] and rp_entry <= rp_end <= rp_enter <= rp_exit <= rp_ack < rp_deadline and rp_ack - rp_entry <= 30 * 10**9 and rp_enter - rp_end <= 10**9 and rp_exit - rp_enter <= 10**9 and review_prefix["first_start_seq"] == 1, "REVIEW_BOOTSTRAP_CLOCKS")
        rp_raw_name = "review_resources/originals/" + review_prefix["first_start_original_sha256"] + ".record"
        require(review_names == {"review_resources/admin_binding.record", "review_resources/bootstrap_prefix.record", rp_raw_name}, "REVIEW_ORIGINAL_MEMBERSHIP")
        rp_raw = m.read_original_observation(root / rp_raw_name, expected_sha256=review_prefix["first_start_original_sha256"], check=budget.check, charge_read=budget.charge)
        require(rp_raw["self_pid"] == review_binding["process_pid"] and all(rp_enter <= r["acquired_mono_ns"] <= rp_exit for r in rp_raw["kernel_records"]), "REVIEW_START_RAW_BINDING")
        require(config["first_start_codec"] is not None, "REVIEW_START_CODEC_MISSING")
        codec_ref = config["first_start_codec"]
        require(type(codec_ref) is dict and set(codec_ref) == {"path", "sha256", "offset", "bytes"} and codec_ref["offset"] == 0 and codec_ref["bytes"] == m.CODEC_BYTES and sha(codec_ref["sha256"]), "REVIEW_START_CODEC_REFERENCE")
        first_raw = read_file(codec_ref["path"], m.CODEC_BYTES, budget, expected=codec_ref["sha256"])
        require(len(first_raw) == m.CODEC_BYTES, "REVIEW_START_CODEC_SIZE")
        review_first = m.unpack_observation(first_raw)
        m.validate_original_observation(rp_raw, observation=review_first)
        m.thresholds(review_first, selected)
        review_seed = digest({"schema_version": "stage12_resource_monitor_seed_ra_g1_v1", "binding_sha256": digest(review_binding), "selection_sha256": digest(selected), "phase_id": 7})
        require(review_first["seq"] == 1 and review_first["kind"] == "START" and review_first["phase_id"] == 7 and review_first["binding_sha256"] == digest(review_binding) and review_first["selection_sha256"] == digest(selected) and review_first["previous_sha256"] == review_seed and digest(review_first) == review_prefix["first_start_record_sha256"] and review_first["visible_identity_inventory_sha256"] == review_prefix["first_start_original_sha256"] and review_first["enter_mono_ns"] == rp_enter and review_first["exit_mono_ns"] == rp_exit, "REVIEW_START_CODEC_BINDING")
        review_timing = {"review_scope_start_mono_ns": rp_entry, "review_deadline_mono_ns": rp_deadline, "review_first_start_ack_mono_ns": rp_ack, "bootstrap_created_utc": boot["created_utc"], "bootstrap_started_mono_ns": boot["started_mono_ns"], "bootstrap_ended_mono_ns": boot["ended_mono_ns"], "scope": "ORIGINAL_REVIEW_START_AND_NATIVE_DEADLINE_ONLY_NOT_COMPLETE_REVIEW_COVERAGE"}
    else:
        require(config["first_start_codec"] is None, "UNEXPECTED_REVIEW_CODEC")
    require(set(inventory) == {"bootstrap/bootstrap.record", "bootstrap/manifest.record", "context.record", "collector.wait.record", "collector.handoff.record", "collector_resources/observations.bin", *("collector_resources/" + n + ".record" for n in records)} | raw_names | review_names, "UNEXPECTED_ORIGINAL")
    # Re-read every retained original after semantic validation. This does not
    # replace source-owned native identity checks; it detects local mutation.
    for name, row in inventory.items():
        read_file(root / name, MAX_ORIGINAL_BYTES, budget, expected=row["sha256"])
    findings = {"required_checks": "ALL_COMPLETED", "authority": "NONE_FINDINGS_ONLY", "evidence_use": config["evidence_use"], "source_sha": config["source_sha"], "job_id": config["job_id"], "selection_sha256": digest(selection), "resource_selection_sha256": digest(selected), "bootstrap_sha256": digest(boot), "bootstrap_manifest_sha256": digest(manifest), "original_files": len(inventory), "original_bytes": sum(r["bytes"] for r in inventory.values()), "source_files_freshly_hashed": len(selection["source_files"]), "monitor_rows": coverage.seq, "maximum_admin_gap_ns": coverage.max_gap, "first_start_ack_from_source_entry_ns": ack - entry, "capacity_age_at_collector_end_ns": boot["ended_mono_ns"] - cap_time, "capacity_scope": "ORIGINAL_SHARED_MARGIN_AT_ORIGINAL_ACQUISITION_ONLY_NO_ENTITLEMENT_OR_RESERVATION", "protocol_clock_scope": "RETAINED_NATIVE_SUPERVISOR_TAIL_TIME_NOT_CURRENT_COMPUTE_TIME", "native_identity_scope": "BOUND_SOURCE_OWNED_ORIGINAL_PROOFS_CURRENT_REMOTE_ROOT_AND_MONITOR_INODE_RESTAT_NOT_PERFORMED", "worker_source_identity_sha256": worker["monitor_source_identity_sha256"], "bootstrap_root_identity_sha256": bootstrap["root_identity_inventory_sha256"], "review_timing": review_timing, "b_input_derived": False, "release_or_factual_authority_issued": False, "scientific_or_workflow_pass": "NOT_ASSERTED"}
    findings.update(originals_tar_sha256=config["originals_tar"]["sha256"], originals_inventory_sha256=config["originals_inventory"]["sha256"], collector_wait_sha256=inventory["collector.wait.record"]["sha256"], collector_handoff_sha256=inventory["collector.handoff.record"]["sha256"], supervisor_context_sha256=digest(context))
    return findings


def install_offline_denials():
    def audit(event, args):
        if event.startswith(("socket.", "subprocess.")) or event in {"os.system", "os.posix_spawn", "os.exec", "os.fork", "pty.spawn"}:
            raise CheckFailure("OFFLINE_PROCESS_NETWORK_DENIED")
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            text = os.fsdecode(args[0])
            if any(part in {".ssh", ".aws", "credentials", "secrets", "HOLDOUT"} for part in Path(text).parts):
                raise CheckFailure("SECRET_PROTECTED_PATH_DENIED")
    sys.addaudithook(audit)


def run(config, budget=None):
    budget = Budget() if budget is None else budget
    try:
        finding = validate_facts(config, budget)
        exit_code = 0
    except BaseException as error:
        if type(error) is CheckFailure and len(error.args) == 1 and error.args[0] in LOCAL_CODES:
            code = error.args[0]
        elif (type(error) is RuntimeError or type(error).__name__ == "Stage12Error") and len(error.args) == 1 and error.args[0] in SAFE_CODES:
            code = error.args[0]
        else:
            code = "UNCLASSIFIED_CHECKER_FAILURE"
        finding = {"required_checks": "FAILED_OR_INCOMPLETE", "authority": "NONE_FINDINGS_ONLY", "safe_failure_code": code, "exception_kind": type(error).__name__ if type(error).__name__ in {"CheckFailure", "Stage12Error", "RuntimeError", "OSError", "ValueError", "TypeError", "KeyError", "FileNotFoundError"} else "UNCLASSIFIED", "release_or_factual_authority_issued": False}
        exit_code = 1
    finding.update(schema_version="stage12_task_factual_checker_findings_v1", checker_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), actual_local_started_mono_ns=budget.start, actual_local_finished_mono_ns=time.monotonic_ns(), checker_checks=budget.checks, checker_read_calls=budget.read_calls, checker_read_bytes=budget.read_bytes)
    return finding, exit_code


def main(argv=None):
    os.umask(0o077)
    sys.dont_write_bytecode = True
    install_offline_denials()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--report", required=True, help="New exclusive findings path; never an authority path")
    args = parser.parse_args(argv)
    budget = Budget()
    config_raw = read_file(args.config, 65536, budget)
    config = parse(config_raw)
    finding, status = run(config, budget)
    finding["checker_input_sha256"] = hashlib.sha256(config_raw).hexdigest()
    raw = canonical(finding)
    require(len(raw) <= 65536, "REPORT_LIMIT")
    destination = Path(args.report)
    no_links(destination.parent)
    budget.check()
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            budget.check()
            written = os.write(fd, view)
            require(written > 0, "REPORT_WRITE")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    pfd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(pfd)
    finally:
        os.close(pfd)
    budget.check()
    read_file(destination, 65536, budget, expected=hashlib.sha256(raw).hexdigest())
    print(json.dumps({"required_checks": finding["required_checks"], "authority": "NONE_FINDINGS_ONLY", "report_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
    return status


if __name__ == "__main__":
    try:
        result = main()
    except BaseException:
        # Invalid configuration, failed/uncertain report persistence, interrupted
        # checks and argparse failures never print exception arguments or paths.
        print('{"authority":"NONE_FINDINGS_ONLY","required_checks":"FAILED_OR_INCOMPLETE","safe_failure_code":"CHECKER_ENTRY_OR_REPORT_FAILED"}')
        result = 2
    raise SystemExit(result)

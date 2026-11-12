# ruff: noqa: E402 -- original entry anchors and exact source import setup precede later imports.
#!/usr/bin/env python3
"""One task-scoped synthetic terminal pair; no submission, SSH or service access."""

from __future__ import annotations
import time as _clock

_ENTRY_MONO_NS = _clock.monotonic_ns()
_ENTRY_EPOCH_NS = _clock.time_ns()

import argparse
import hashlib
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

import stage12_ra_g1_terminal_collect as tc

VERSION = "stage12_terminal_pair_v1"
AUTH_VERSION = "stage12_terminal_pair_authority_v1"
TERMINAL_VERSION = "stage12_terminal_source_terminal_v1"
READY_VERSION = "stage12_terminal_transport_ready_v1"
RECEIPT_VERSION = "stage12_terminal_local_retention_v1"
FINAL_VERSION = "stage12_terminal_final_log_verification_v1"
NATIVE = "NATIVE_SYNTHETIC_TERMINAL"
TEST = "TEST_ONLY_INVENTED"
WINDOW_END_NS = 1794424401620987000  # Legacy family, never extended.
SUCCESSOR_VERSION = "stage12_terminal_same_domain_pair_v2"
SUCCESSOR_AUTH_VERSION = "stage12_terminal_same_domain_pair_authority_v2"
SUCCESSOR_READY_VERSION = "stage12_terminal_same_domain_transport_ready_v2"
SUCCESSOR_FINAL_VERSION = "stage12_terminal_same_domain_final_log_verification_v2"
SUCCESSOR_RECEIPT_VERSION = "stage12_terminal_same_domain_local_retention_v2"
QUALIFICATION_VERSION = "stage12_terminal_collection_qualification_v1"
ONESHOT_ADMISSION_VERSION = "stage12_collection_oneshot_admission_v1"
SELECTED_PAIR_ADMISSION_VERSION = "stage12_collection_selected_pair_admission_v2"
SELECTED_PAIR_CONTROL_VERSION = "stage12_task_oneshot_selected_pair_v2"
SELECTED_PAIR_DIRECTORY_RULE = "SELECTED_FINAL_DIRECTORY_ENOENT_V1"
ONESHOT_CONTROL_LIMITS = (
    ("version", "stage12_task_oneshot_controls_v1"),
    ("maximum_probes", 16), ("probe_seconds", 15),
    ("minimum_start_spacing_seconds", 120),
    ("spacing_anchor", "PREVIOUS_DURABLE_RECORD_ACK_PLUS_120_SECONDS"),
    ("maximum_process_units", 208),
    ("combined_read_call_bound", 173646), ("global_read_call_cap", 262144),
    ("additional_read_calls", 65570), ("additional_read_bytes", 17891328),
    ("callback_inclusive_write_bytes", 5308416), ("callback_inclusive_creations", 86),
    ("controller_seconds", 1800),
)
SELECTED_PAIR_CONTROL_LIMITS = tuple(
    (key, {"version": SELECTED_PAIR_CONTROL_VERSION, "maximum_process_units": 228,
           "callback_inclusive_write_bytes": 5832704, "callback_inclusive_creations": 104}.get(key, expected))
    for key, expected in ONESHOT_CONTROL_LIMITS
) + (("directory_readiness", SELECTED_PAIR_DIRECTORY_RULE),)
ONESHOT_SOURCE_FIELDS = (
    ("stage12_ra_g1_one_shot_controls.py", "one_shot_controls_sha256"),
    ("stage12_ra_g1_collection_driver.py", "collection_driver_sha256"),
    ("stage12_ra_g1_terminal_transport.py", "transport_sha256"),
)

SUCCESSOR_CONTEXT_FIELDS = "window collection_purpose original_source_root original_producer_path original_producer_sha256"


def family_end(value):
    if value.get("version") in (SUCCESSOR_VERSION, SUCCESSOR_READY_VERSION):
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
        return windows.epoch_ns(windows.WINDOW_END)
    return WINDOW_END_NS


def validate_collection_window(value, *, now_epoch_ns, required_remaining_seconds):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    return windows.validate_window(value, scope="TERMINAL_COLLECTION_NO_SERVICE",
                                   now_epoch_ns=now_epoch_ns,
                                   required_remaining_seconds=required_remaining_seconds)

PRACTICAL = dict(
    members=131072,
    payload_bytes=1073741824,
    manifest_bytes=134217728,
    record_bytes=8192,
    path_bytes=1024,
    name_bytes=255,
    depth=16,
    sort_records=512,
    sort_buffer_bytes=8388608,
    merge_fan_in=16,
    chunk_bytes=65536,
    wire_bytes=3221225472,
    read_bytes=34359738368,
    write_bytes=8589934592,
    creations=140000,
    operations=100000000,
    scanned_entries=524288,
    seconds=900,
)
TERMINAL_STATES = frozenset(
    {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "TIMEOUT",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "BOOT_FAIL",
        "DEADLINE",
        "PREEMPTED",
    }
)
SAFE_CODES = frozenset(
    {
        "BINDING",
        "AUTHORITY",
        "SCOPE",
        "DEADLINE",
        "SOURCE_CHANGED",
        "TERMINAL",
        "CONTEXT",
        "LIMITS",
        "PATH",
        "PRIVATE",
        "OUTPUT",
        "READ_BYTES",
        "READ_CALLS",
        "CREATIONS",
        "WRITE_BYTES",
        "STDERR",
        "CHILD_EXIT",
        "CHILD_LIFECYCLE",
        "SUMMARY",
        "RETENTION",
        "FINAL_LOGS",
        "CLOSE_UNCERTAIN",
        "UNCLASSIFIED", "DOMAIN", "FRAME", "ANCESTOR", "ANCESTOR_CHANGED", "TRUNCATED", "PROTOCOL", "PAYLOAD_HASH",
    }
)


def need(value, code):
    if not value:
        raise tc.Stop(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def fields(value, expected, code="BINDING"):
    need(type(value) is dict and set(value) == set(expected.split()), code)


def hash_string(value):
    need(type(value) is str and tc.HEX.fullmatch(value), "BINDING")
    return value


class Control:
    """Fixed parent/local counters; logical limits do not certify native containment."""

    def __init__(self, entered, epoch_end, seconds, output=None):
        self.entered = entered
        self.end = entered + seconds * 10**9
        self.epoch_end = epoch_end
        self.output = output
        self.read_bytes = self.read_calls = self.write_bytes = self.creations = 0
        self.cleanup_uncertain = False

    def check(self):
        need(
            time.monotonic_ns() < self.end and time.time_ns() < self.epoch_end,
            "DEADLINE",
        )

    def read(self, fd, amount):
        self.check()
        need(
            self.read_calls < 262144 and self.read_bytes + amount <= 8 * 2**30,
            "READ_CALLS",
        )
        self.read_calls += 1
        raw = os.read(fd, amount)
        self.read_bytes += len(raw)
        self.check()
        return raw

    def claim(self, amount, creation=False):
        self.check()
        need(self.write_bytes + amount <= 16 * 2**20, "WRITE_BYTES")
        if creation:
            need(self.creations < 128, "CREATIONS")
            self.creations += 1
        self.write_bytes += amount

    def record(self, path, value, maximum=65536):
        need(maximum in (65536, 1048576), "WRITE_BYTES")
        raw = tc.canonical(value)
        need(len(raw) <= maximum, "WRITE_BYTES")
        parent = path.parent
        chain = tc.ancestors(path, links=False)
        tc.private(parent.lstat(), "DIR", os.geteuid())
        # One permanent intent owns each final name. Failed pending writes remain.
        self.claim(0, True)
        intent = path.with_name(path.name + ".reservation")
        intentfd = os.open(
            intent, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            os.fsync(intentfd)
        finally:
            tc.close_owned(self, (intentfd,))
        self.claim(len(raw), True)
        pending = path.with_name(path.name + ".pending")
        fd = os.open(
            pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        try:
            view = memoryview(raw)
            while view:
                self.check()
                n = os.write(fd, view)
                need(n > 0, "WRITE_BYTES")
                view = view[n:]
            os.fsync(fd)
        finally:
            tc.close_owned(self, (fd,))
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise tc.Stop("OUTPUT")
        tc.check_ancestors(chain)
        os.rename(pending, path)  # exclusive intent + sole private-directory writer
        parentfd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parentfd)
        finally:
            tc.close_owned(self, (parentfd,))
        tc.check_ancestors(chain)
        need(read_original(path, self, maximum) == raw, "SOURCE_CHANGED")
        self.check()
        return digest(raw)


def read_original(path, control, maximum):
    path = tc.absolute(str(path))
    chain = tc.ancestors(path)
    before = path.lstat()
    tc.private(before, "FILE", os.geteuid())
    need(before.st_size <= maximum, "READ_BYTES")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        need(tc.ident(os.fstat(fd)) == tc.ident(before), "SOURCE_CHANGED")
        parts = []
        left = before.st_size
        while left:
            raw = control.read(fd, min(65536, left))
            need(raw, "SOURCE_CHANGED")
            parts.append(raw)
            left -= len(raw)
        need(not control.read(fd, 1), "SOURCE_CHANGED")
        need(
            tc.ident(os.fstat(fd)) == tc.ident(path.lstat()) == tc.ident(before),
            "SOURCE_CHANGED",
        )
    finally:
        tc.close_owned(control, (fd,))
    tc.check_ancestors(chain)
    return b"".join(parts)  # maximum64KiB control records only


def hash_original(path, control, maximum):
    path = tc.absolute(str(path))
    chain = tc.ancestors(path)
    before = path.lstat()
    tc.private(before, "FILE", os.geteuid())
    need(before.st_size <= maximum, "READ_BYTES")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    sha = hashlib.sha256()
    size = 0
    try:
        need(tc.ident(os.fstat(fd)) == tc.ident(before), "SOURCE_CHANGED")
        while True:
            raw = control.read(fd, 65536)
            if not raw:
                break
            size += len(raw)
            need(size <= maximum, "READ_BYTES")
            sha.update(raw)
        need(
            size == before.st_size
            and tc.ident(os.fstat(fd)) == tc.ident(path.lstat()) == tc.ident(before),
            "SOURCE_CHANGED",
        )
    finally:
        tc.close_owned(control, (fd,))
    tc.check_ancestors(chain)
    return dict(bytes=size, sha256=sha.hexdigest(), identity=list(tc.ident(before)))


def load_control(path, expected, control):
    raw = read_original(path, control, 65536)
    need(digest(raw) == hash_string(expected), "BINDING")
    return tc.parse(raw)


def validate_authority(authority, binding, offline):
    successor = binding.get("version") == SUCCESSOR_VERSION
    admission_field = "collection_admission_sha256" if successor else "environment_gate_sha256"
    fields(
        authority,
        ("version scope state grant_nonce adoption_sha256 "+admission_field+" source_git_sha original_job_id original_scheduler_sha256 original_log_policy_sha256 max_collection_jobs max_collection_seconds collection_pool_bytes collection_pool_creations control_pool_bytes window_start_epoch_ns valid_until_epoch_ns") + (" window collection_purpose historical_collection_sha256" if successor else ""),
        "AUTHORITY",
    )
    need(
        authority["version"] == (SUCCESSOR_AUTH_VERSION if successor else AUTH_VERSION)
        and authority["grant_nonce"] == binding["grant_nonce"]
        and authority["scope"] == binding["scope"]
        and authority["source_git_sha"] == binding["source_git_sha"]
        and authority["original_job_id"] == binding["original_job_id"]
        and hash_string(authority["original_scheduler_sha256"])
        == binding["original_scheduler_sha256"]
        and hash_string(authority["original_log_policy_sha256"])
        == binding["original_log_policy_sha256"],
        "AUTHORITY",
    )
    for key in [
        "original_job_id",
        "max_collection_jobs",
        "max_collection_seconds",
        "collection_pool_bytes",
        "collection_pool_creations",
        "control_pool_bytes",
        "window_start_epoch_ns",
        "valid_until_epoch_ns",
    ]:
        tc.uint(authority[key])
    need(
        authority["max_collection_jobs"] == 1
        and authority["max_collection_seconds"] == 1800
        and authority["collection_pool_bytes"] == 25769803776
        and authority["collection_pool_creations"] == 450000
        and authority["control_pool_bytes"] == 67108864,
        "AUTHORITY",
    )
    need(
        authority["window_start_epoch_ns"] == binding["window_start_epoch_ns"]
        and authority["valid_until_epoch_ns"] == binding["valid_until_epoch_ns"],
        "AUTHORITY",
    )
    if successor:
        hash_string(authority[admission_field])
        need(authority["window"] == binding["window"] and authority["collection_purpose"] == binding["collection_purpose"] and authority["historical_collection_sha256"] == digest(tc.canonical(binding["historical_collection"])), "AUTHORITY")
    if offline:
        need(
            authority["state"] == "TEST_ONLY"
            and authority["adoption_sha256"] is None
            and (successor or authority["environment_gate_sha256"] is None),
            "AUTHORITY",
        )
    else:
        need(
            authority["state"] == "ISSUED"
            and authority["adoption_sha256"] != "0" * 64
            and authority[admission_field] != "0" * 64,
            "AUTHORITY",
        )
        hash_string(authority["adoption_sha256"])
        hash_string(authority[admission_field])


def validate_collection_source_scope(binding, offline):
    """Closed workload boundaries for the two specifically authorized collections."""
    if offline:
        return
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    job=binding["original_job_id"]
    need(type(job) is int and job > 0, "SCOPE")
    if binding["collection_purpose"] == "QUALIFICATION":
        need(binding["original_source_git_sha"] == windows.ORIGINAL_SOURCE
             and job == int(windows.ORIGINAL_JOB)
             and binding["original_selection_sha256"] == windows.ORIGINAL_SELECTION, "SCOPE")
    else:
        need(binding["collection_purpose"] == "POST_B"
             and binding["original_source_git_sha"] == binding["source_git_sha"]
             and job not in (int(windows.ORIGINAL_JOB),1813045), "SCOPE")


def validate_binding(binding, offline, test_root):
    successor = binding.get("version") == SUCCESSOR_VERSION
    fields(
        binding,
        "version scope state grant_nonce authority_sha256 original_job_id original_source_git_sha source_git_sha helper_sha256 parent_sha256 interpreter_path selection_template_path selection_template_sha256 original_terminal_path original_terminal_sha256 original_scheduler_path original_scheduler_sha256 original_log_policy original_log_policy_sha256 original_selection_path original_selection_sha256 allocation_producer_sha256 verifier_path verifier_sha256 output_path seconds window_start_epoch_ns valid_until_epoch_ns allowed_inert_fifo_paths collection_external_logs" + (" window collection_purpose original_source_root original_producer_path historical_collection collection_admission_path" if successor else ""),
    )
    need(
        binding["version"] in (VERSION, SUCCESSOR_VERSION)
        and type(binding["grant_nonce"]) is str
        and re.fullmatch(r"[0-9a-f]{32}", binding["grant_nonce"]),
        "BINDING",
    )
    for key in [
        "authority_sha256",
        "helper_sha256",
        "parent_sha256",
        "selection_template_sha256",
        "original_terminal_sha256",
        "original_scheduler_sha256",
        "original_log_policy_sha256",
        "original_selection_sha256",
        "allocation_producer_sha256",
        "verifier_sha256",
    ]:
        hash_string(binding[key])
    for key in ["source_git_sha", "original_source_git_sha"]:
        need(
            type(binding[key]) is str and re.fullmatch(r"[0-9a-f]{40}", binding[key]),
            "BINDING",
        )
    for key in [
        "original_job_id",
        "seconds",
        "window_start_epoch_ns",
        "valid_until_epoch_ns",
    ]:
        tc.uint(binding[key])
    need(
        1 <= binding["seconds"] <= 1800
        and binding["window_start_epoch_ns"] < binding["valid_until_epoch_ns"],
        "LIMITS",
    )
    need(
        type(binding["allowed_inert_fifo_paths"]) is list
        and binding["allowed_inert_fifo_paths"]
        in ([], ["allocation/supervisor_wait.fifo"]),
        "BINDING",
    )
    policy = binding["original_log_policy"]
    fields(policy, "external_files required_logs", "BINDING")
    need(
        type(policy["external_files"]) is list
        and len(policy["external_files"]) <= 14
        and type(policy["required_logs"]) is list
        and 1 <= len(policy["required_logs"]) <= 16,
        "BINDING",
    )
    need(
        digest(tc.canonical(policy)) == binding["original_log_policy_sha256"], "BINDING"
    )
    external_labels = set()
    external_paths = set()
    for row in policy["external_files"]:
        fields(row, "label path", "BINDING")
        path = tc.absolute(row["path"])
        need(
            type(row["label"]) is str
            and tc.LABEL.fullmatch(row["label"])
            and row["label"] not in external_labels
            and path not in external_paths,
            "BINDING",
        )
        external_labels.add(row["label"])
        external_paths.add(path)
    need(len(set(policy["required_logs"])) == len(policy["required_logs"]), "BINDING")
    for logical in policy["required_logs"]:
        tc.path_text(logical)
    logs = binding["collection_external_logs"]
    need(type(logs) is list and 1 <= len(logs) <= 16, "BINDING")
    names, log_paths = set(), set()
    for row in logs:
        fields(row, "label path")
        need(
            type(row["label"]) is str
            and tc.LABEL.fullmatch(row["label"])
            and row["label"] not in names,
            "BINDING",
        )
        names.add(row["label"])
        log_path = tc.absolute(row["path"])
        need(log_path not in log_paths, "BINDING")
        log_paths.add(log_path)
    for key in [
        "interpreter_path",
        "selection_template_path",
        "original_terminal_path",
        "original_scheduler_path",
        "original_selection_path",
        "verifier_path",
        "output_path",
    ]:
        p = tc.absolute(binding[key])
        if offline and key not in ("interpreter_path", "verifier_path"):
            need(test_root is not None and tc.contained(p, test_root), "SCOPE")
    if offline:
        need(binding["scope"] == TEST and binding["state"] == "TEST_ONLY", "SCOPE")
    else:
        need(
            binding["scope"] == NATIVE
            and binding["state"] == "ISSUED"
            and binding["original_job_id"] > 0
            and binding["seconds"] == 1800
            and binding["source_git_sha"] != "0" * 40
            and binding["original_source_git_sha"] != "0" * 40
            and binding["valid_until_epoch_ns"] <= family_end(binding),
            "SCOPE",
        )

    if successor:
        need(binding["collection_purpose"] in ("QUALIFICATION", "POST_B"), "BINDING")
        validate_collection_source_scope(binding,offline)
        source = tc.absolute(binding["original_source_root"])
        producer = tc.absolute(binding["original_producer_path"])
        need(producer == source / "scripts/stage12_ra_g1_allocation.py", "BINDING")
        admission_path = tc.absolute(binding["collection_admission_path"])
        need(admission_path == tc.absolute(binding["selection_template_path"]).parent/"collection_admission.record", "BINDING")
        if offline:
            need(tc.contained(admission_path,test_root), "SCOPE")
        history = binding["historical_collection"]
        if binding["collection_purpose"] == "QUALIFICATION":
            fields(history, "job_id source_git_sha scheduler_state exit_code signal raw_scheduler_sha256 roots", "BINDING")
            need(history["job_id"] == 1813045 and type(history["job_id"]) is int
                 and history["source_git_sha"] == binding["original_source_git_sha"]
                 and history["scheduler_state"] in TERMINAL_STATES and history["scheduler_state"] != "COMPLETED", "BINDING")
            tc.uint(history["exit_code"])
            tc.uint(history["signal"])
            hash_string(history["raw_scheduler_sha256"])
            base = tc.absolute(binding["original_selection_path"]).parent.parent
            need(history["roots"] == [dict(label=name, path=str(base/name)) for name in ("terminal_pair","terminal_bindings","terminal_logs")], "BINDING")
        else:
            need(history is None, "BINDING")
        if not offline:
            validate_collection_window(binding["window"], now_epoch_ns=time.time_ns(), required_remaining_seconds=1920)
            from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
            need(binding["window_start_epoch_ns"] == windows.epoch_ns(windows.WINDOW_START)
                 and binding["valid_until_epoch_ns"] == windows.epoch_ns(windows.WINDOW_END), "BINDING")


def validate_oneshot_control_policy(policy, *, selected_remote_pair=None):
    """Closed historical or explicitly selected final-directory successor."""
    selected = selected_remote_pair is not None
    limits = SELECTED_PAIR_CONTROL_LIMITS if selected else ONESHOT_CONTROL_LIMITS
    fields(policy, " ".join(key for key,_ in limits)
           + " " + " ".join(key for _,key in ONESHOT_SOURCE_FIELDS)
           + (" selected_remote_pair" if selected else ""), "AUTHORITY")
    for key, expected in limits:
        need(type(policy[key]) is type(expected) and policy[key] == expected, "AUTHORITY")
    if selected:
        path = tc.absolute(selected_remote_pair)
        need(str(path) == selected_remote_pair and path != path.parent
             and len(selected_remote_pair) <= 1024
             and __import__("re").fullmatch(r"[A-Za-z0-9_./-]+", selected_remote_pair)
             and policy["selected_remote_pair"] == selected_remote_pair, "AUTHORITY")
    for _,key in ONESHOT_SOURCE_FIELDS:
        hash_string(policy[key])
        need(policy[key] != "0"*64, "AUTHORITY")
    return policy


def validate_collection_admission(value, binding, authority, offline):
    selected_pair = type(value) is dict and value.get("version") == SELECTED_PAIR_ADMISSION_VERSION
    oneshot = type(value) is dict and value.get("version") in (ONESHOT_ADMISSION_VERSION, SELECTED_PAIR_ADMISSION_VERSION)
    fields(value, "version scope state source_git_sha original_job_id original_source_git_sha original_selection_sha256 original_source_root allocation_producer_sha256 historical_collection_sha256 window grant_nonce collection_purpose helper_sha256 parent_sha256 verifier_sha256 collection_plan_sha256 collection_review_sha256 software_review_sha256 process_graph_sha256 maximum_preparation_and_native_processes max_collection_jobs max_collection_seconds collection_pool_bytes collection_pool_creations control_pool_bytes B_authorized public_authorized protected_authorized scientific_acceptance" + (" one_shot_control_policy" if oneshot else ""), "AUTHORITY")
    need(value["version"] in ("stage12_collection_only_admission_v1", ONESHOT_ADMISSION_VERSION, SELECTED_PAIR_ADMISSION_VERSION) and value["scope"] == "TERMINAL_COLLECTION_NO_SERVICE"
         and value["state"] == ("TEST_ONLY" if offline else "ISSUED"), "AUTHORITY")
    for key in ("source_git_sha","original_job_id","original_source_git_sha","original_selection_sha256","original_source_root",
                "allocation_producer_sha256","window","grant_nonce","helper_sha256","parent_sha256","verifier_sha256","collection_purpose"):
        need(value[key] == binding[key], "AUTHORITY")
    need(value["historical_collection_sha256"] == digest(tc.canonical(binding["historical_collection"])), "AUTHORITY")
    for key in ("collection_plan_sha256","collection_review_sha256","software_review_sha256","process_graph_sha256"):
        hash_string(value[key])
        need(value[key] != "0"*64, "AUTHORITY")
    for key in ("max_collection_jobs","max_collection_seconds","collection_pool_bytes","collection_pool_creations","control_pool_bytes"):
        tc.uint(value[key])
        need(value[key] == authority[key], "AUTHORITY")
    need(type(value["maximum_preparation_and_native_processes"]) is int
         and value["maximum_preparation_and_native_processes"] == (228 if selected_pair else 208 if oneshot else 69), "AUTHORITY")
    if oneshot:
        policy = value["one_shot_control_policy"]
        validate_oneshot_control_policy(policy, selected_remote_pair=binding["output_path"] if selected_pair else None)
    need(all(value[key] is False for key in ("B_authorized","public_authorized","protected_authorized","scientific_acceptance")), "SCOPE")
    if not offline:
        validate_collection_window(value["window"],now_epoch_ns=time.time_ns(),
                                   required_remaining_seconds=12240 if binding["collection_purpose"] == "QUALIFICATION" else 1920)
    return value


def source_hash(path, expected, control):
    """Source may be0644; inputs/output originals remain private0600."""
    before = path.lstat()
    chain = tc.ancestors(path)
    need(
        stat_regular(before)
        and before.st_uid == os.geteuid()
        and before.st_nlink == 1
        and not before.st_mode & 0o022
        and before.st_size <= 262144,
        "PRIVATE",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    sha = hashlib.sha256()
    try:
        need(tc.ident(os.fstat(fd)) == tc.ident(before), "SOURCE_CHANGED")
        while raw := control.read(fd, 65536):
            sha.update(raw)
        need(
            tc.ident(os.fstat(fd)) == tc.ident(path.lstat()) == tc.ident(before),
            "SOURCE_CHANGED",
        )
    finally:
        tc.close_owned(control, (fd,))
    tc.check_ancestors(chain)
    need(sha.hexdigest() == expected, "SOURCE_CHANGED")


def stat_regular(value):
    import stat

    return stat.S_ISREG(value.st_mode)


def bind_template(value, binding, control, offline, test_root):
    need(
        value.get("state") == "TEMPLATE" and value.get("version") == tc.FIFO_VERSION,
        "BINDING",
    )
    actual = dict(value)
    actual["state"] = "TEST_ONLY" if offline else "ISSUED"
    actual["scope"] = "TEST_ONLY_INVENTED" if offline else "NATIVE_TERMINAL_ORIGINALS"
    actual["approval_sha256"] = None if offline else binding["authority_sha256"]
    need(actual["job_id"] in ("ORIGINAL_JOB_ID", binding["original_job_id"]), "BINDING")
    actual["job_id"] = binding["original_job_id"]
    need(
        actual["source_git_sha"] == binding["original_source_git_sha"]
        and actual["valid_until_epoch_ns"] == binding["valid_until_epoch_ns"],
        "BINDING",
    )
    if not offline:
        need(actual["limits"] == PRACTICAL, "LIMITS")
    declarations = actual["inert_fifos"]
    need(
        type(declarations) is list
        and all(
            type(r) is dict and set(r) == {"path", "identity"} and r["identity"] is None
            for r in declarations
        ),
        "BINDING",
    )
    need(
        [r["path"] for r in declarations] == binding["allowed_inert_fifo_paths"],
        "BINDING",
    )
    roots = {r["label"]: tc.absolute(r["path"]) for r in actual["roots"]}
    actual["inert_fifos"] = []
    for row in declarations:
        parts = row["path"].split("/")
        need(parts[0] in roots, "BINDING")
        fifo = roots[parts[0]].joinpath(*parts[1:])
        chain = tc.ancestors(fifo)
        info = fifo.lstat()
        import stat

        need(
            stat.S_ISFIFO(info.st_mode)
            and info.st_uid == actual["source_uid"]
            and info.st_gid == actual["source_gid"]
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_nlink == 1,
            "PRIVATE",
        )
        tc.check_ancestors(chain)
        control.check()
        actual["inert_fifos"].append(
            dict(path=row["path"], identity=list(tc.ident(info)))
        )
    selected = tc.Selection(actual, offline, test_root)
    return actual, selected


def verified_source_module(control, expected_source_sha256, filename, *, source_path=None):
    """Execute only verified bytes from the fixed reviewed producer sibling."""
    from types import ModuleType

    need(
        filename in ("stage12_ra_g1_allocation.py", "stage12_ra_g1_terminal_verify.py"),
        "BINDING",
    )
    path = Path(__file__).absolute().with_name(filename) if source_path is None else tc.absolute(str(source_path))
    need(source_path is None or filename == "stage12_ra_g1_allocation.py", "BINDING")
    before = path.lstat()
    chain = tc.ancestors(path)
    need(
        stat_regular(before)
        and before.st_uid == os.geteuid()
        and before.st_nlink == 1
        and not before.st_mode & 0o022
        and before.st_size <= 262144,
        "PRIVATE",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    parts = []
    size = 0
    try:
        need(tc.ident(os.fstat(fd)) == tc.ident(before), "SOURCE_CHANGED")
        while raw := control.read(fd, 65536):
            size += len(raw)
            need(size <= 262144, "READ_BYTES")
            parts.append(raw)
        need(
            size == before.st_size
            and tc.ident(os.fstat(fd)) == tc.ident(path.lstat()) == tc.ident(before),
            "SOURCE_CHANGED",
        )
    finally:
        tc.close_owned(control, (fd,))
    tc.check_ancestors(chain)
    source = b"".join(parts)  # one bounded reviewed code module, never payload data
    need(digest(source) == hash_string(expected_source_sha256), "SOURCE_CHANGED")
    module = ModuleType("stage12_terminal_bound_" + filename[:-3])
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    control.check()
    return module


def allocation_producer(control, expected_source_sha256, producer_path=None):
    return verified_source_module(
        control, expected_source_sha256, "stage12_ra_g1_allocation.py", source_path=producer_path
    )


def load_control_large(
    path, expected, control, producer_source_sha256, *, return_producer=False, producer_path=None
):
    raw = read_original(path, control, 1048576)
    need(digest(raw) == hash_string(expected), "BINDING")
    producer = allocation_producer(control, producer_source_sha256, producer_path)
    value = producer.parse(
        raw
    )  # actual allocation producer contract, ensure_ascii=True
    need(producer.digest(value) == expected, "BINDING")
    return (value, producer) if return_producer else value


def verify_workload(path, selection, control, expected_hash, original_selection_sha256):
    need(
        path == Path(__file__).absolute().with_name("stage12_ra_g1_terminal_verify.py"),
        "BINDING",
    )
    module = verified_source_module(
        control, expected_hash, "stage12_ra_g1_terminal_verify.py"
    )
    proof_bytes = proof_reads = 0

    def charge_read(amount):
        nonlocal proof_bytes, proof_reads
        need(type(amount) is int and amount >= 0, "READ_BYTES")
        proof_bytes += amount
        proof_reads += 1
        need(proof_bytes <= 32 * 2**30 and proof_reads <= 1000000, "READ_BYTES")
        control.check()

    result = module.verify_original_workload(
        selection, check=control.check, charge_read=charge_read
    )
    need(type(result) is dict and type(result.get("complete")) is bool, "SUMMARY")
    need(
        result.get("schema") == module.VERSION
        and result.get("scope") == "REPRESENTATIVE_NO_SERVICE"
        and result.get("source_sha") == selection.get("source_sha")
        and result.get("allocation_selection_sha256") == original_selection_sha256,
        "SUMMARY",
    )
    if result["complete"]:
        need(
            result.get("status") == "FRESH_ORIGINAL_CONTENT_AND_TIMED_RECORDS_VERIFIED",
            "SUMMARY",
        )
    source_hash(path, expected_hash, control)
    return result


def validate_original_scheduler(raw, terminal):
    """Exact top job from sacct -n -P --format=JobIDRaw,State,ExitCode."""
    try:
        text = raw.decode("ascii")
    except UnicodeError:
        raise tc.Stop("TERMINAL") from None
    rows = text.splitlines()
    need(1 <= len(rows) <= 32, "TERMINAL")
    found = []
    job = str(terminal["job_id"])
    for line in rows:
        columns = line.split("|")
        need(len(columns) == 3, "TERMINAL")
        identifier, state, code = (value.strip() for value in columns)
        need(identifier == job or identifier.startswith(job + "."), "TERMINAL")
        if identifier != job:
            continue
        state = state.split(" ")[0]
        need(
            state in TERMINAL_STATES and re.fullmatch(r"[0-9]+:[0-9]+", code),
            "TERMINAL",
        )
        exit_code, child_signal = map(int, code.split(":"))
        tc.uint(exit_code)
        tc.uint(child_signal)
        found.append((state, exit_code, child_signal))
    need(
        found
        == [(terminal["scheduler_state"], terminal["exit_code"], terminal["signal"])],
        "TERMINAL",
    )


def original_candidate_eligible(terminal, verification):
    return (
        verification.get("complete") is True
        and terminal.get("scheduler_state") == "COMPLETED"
        and type(terminal.get("exit_code")) is int
        and terminal["exit_code"] == 0
        and type(terminal.get("signal")) is int
        and terminal["signal"] == 0
    )


def validate_original_namespace(original, template, binding, producer, offline):
    need(
        type(original) is dict
        and original.get("version") == producer.REP512_VERSION
        and original.get("scope") == producer.SCOPE == "REPRESENTATIVE_NO_SERVICE",
        "SCOPE",
    )
    if not offline:
        producer.validate_selection(
            original
        )  # actual production schema, no copied predicate
    paths = original.get("paths")
    if binding.get("version") == SUCCESSOR_VERSION:
        need(type(paths) is dict and paths.get("source") == binding["original_source_root"], "BINDING")
    need(
        type(paths) is dict and {"allocation_root", "records"} <= set(paths), "BINDING"
    )
    roots = [
        dict(label="allocation", path=str(tc.absolute(paths["allocation_root"]))),
        dict(label="records", path=str(tc.absolute(paths["records"]))),
    ]
    if binding.get("version") == SUCCESSOR_VERSION and binding["historical_collection"] is not None:
        roots += binding["historical_collection"]["roots"]
    need(template.get("roots") == roots, "BINDING")
    policy = binding["original_log_policy"]
    need(
        template.get("external_files") == policy["external_files"]
        and template.get("required_logs") == policy["required_logs"],
        "BINDING",
    )
    # A failed source may lack never-published input/tail/campaign directories.
    # Do not create them or require their existence as evidence of completion.


def child_argv(helper, selection_path, selected, output, offline, test_root, role):
    result = [
        sys.executable,
        "-B",
        "-u",
        str(helper),
        role,
        "--selection",
        str(selection_path),
        "--selection-sha256",
        selected.sha,
        "--output",
        str(output),
    ]
    if offline:
        result.extend(["--offline-invented", "--test-root", str(test_root)])
    return result


def require_stderr_bytes(size):
    tc.uint(size)
    need(size <= 2 * 2**20, "STDERR")


def require_full_collection_window(binding, now_epoch_ns):
    tc.uint(now_epoch_ns)
    remaining = 12240 if binding.get("version") == SUCCESSOR_VERSION and binding["collection_purpose"] == "QUALIFICATION" else 1920
    need(now_epoch_ns + remaining * 10**9 <= min(binding["valid_until_epoch_ns"], family_end(binding)), "DEADLINE")
    if binding.get("version") == SUCCESSOR_VERSION:
        validate_collection_window(binding["window"], now_epoch_ns=now_epoch_ns, required_remaining_seconds=remaining)


def role_kill_at(deadline_ns, parent_end_ns):
    return min(deadline_ns, parent_end_ns) - 5 * 10**9


def require_role_time(row, observed_ns):
    tc.uint(observed_ns)
    need(observed_ns < row["deadline_ns"], "DEADLINE")


def stop_children(children, end, control):
    uncertain = False
    for proc in children:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException:
                uncertain = True
    for proc in children:
        try:
            proc.wait(timeout=max(0.001, (end - time.monotonic_ns()) / 1e9))
        except BaseException:
            uncertain = True
    if uncertain:
        control.cleanup_uncertain = True
    return not uncertain


def run_pair(
    binding,
    authority,
    template,
    terminal,
    output,
    offline,
    test_root,
    entered_mono,
    entered_epoch,
):
    validate_binding(binding, offline, test_root)
    validate_authority(authority, binding, offline)
    need(
        binding["window_start_epoch_ns"]
        <= time.time_ns()
        < binding["valid_until_epoch_ns"],
        "DEADLINE",
    )
    fields(
        terminal,
        "version job_id source_git_sha workload_selection_sha256 scope scheduler_state exit_code signal raw_scheduler_sha256 observed_epoch_ns",
    )
    tc.uint(terminal["job_id"])
    tc.uint(terminal["observed_epoch_ns"])
    tc.uint(terminal["exit_code"])
    tc.uint(terminal["signal"])
    need(
        hash_string(terminal["raw_scheduler_sha256"])
        == binding["original_scheduler_sha256"],
        "TERMINAL",
    )
    need(
        terminal["version"] == TERMINAL_VERSION
        and terminal["job_id"] == binding["original_job_id"]
        and terminal["source_git_sha"] == binding["original_source_git_sha"]
        and terminal["scope"] == "PUBLIC_SYNTHETIC_ONLY"
        and terminal["scheduler_state"] in TERMINAL_STATES,
        "TERMINAL",
    )
    if not offline:
        require_full_collection_window(binding, time.time_ns())
    hash_string(terminal["workload_selection_sha256"])
    need(
        binding["window_start_epoch_ns"]
        <= terminal["observed_epoch_ns"]
        <= time.time_ns()
        and terminal["observed_epoch_ns"] < binding["valid_until_epoch_ns"],
        "TERMINAL",
    )
    collection_job = 0
    if not offline:
        from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

        require_goethe_nhr_slurm("stage12_terminal_original_pair")
        value = os.environ.get("SLURM_JOB_ID", "")
        need(re.fullmatch(r"[1-9][0-9]*", value), "CONTEXT")
        collection_job = int(value)
        need(collection_job != binding["original_job_id"], "CONTEXT")
    overall_epoch_end = min(
        binding["valid_until_epoch_ns"], entered_epoch + binding["seconds"] * 10**9
    )
    # Preserve120s for genuine terminal job/log retention and independent review.
    reserve = 120 if not offline else min(2, binding["seconds"] // 4)
    control = Control(
        entered_mono,
        overall_epoch_end - reserve * 10**9,
        binding["seconds"] - reserve,
        output,
    )
    helper = Path(tc.__file__).absolute()
    parent = Path(__file__).absolute()
    source_hash(helper, binding["helper_sha256"], control)
    source_hash(parent, binding["parent_sha256"], control)
    need(Path(binding["interpreter_path"]) == Path(sys.executable), "BINDING")
    verifier_path = tc.absolute(binding["verifier_path"])
    need(
        verifier_path == parent.with_name("stage12_ra_g1_terminal_verify.py"), "BINDING"
    )
    source_hash(verifier_path, binding["verifier_sha256"], control)
    if binding["version"] == SUCCESSOR_VERSION:
        admission = load_control(Path(binding["collection_admission_path"]), authority["collection_admission_sha256"], control)
        validate_collection_admission(admission, binding, authority, offline)
        if admission["version"] in (ONESHOT_ADMISSION_VERSION, SELECTED_PAIR_ADMISSION_VERSION):
            for filename, key in ONESHOT_SOURCE_FIELDS:
                source_hash(parent.with_name(filename), admission["one_shot_control_policy"][key], control)
    original_selection, original_producer = load_control_large(
        Path(binding["original_selection_path"]),
        binding["original_selection_sha256"],
        control,
        binding["allocation_producer_sha256"],
        return_producer=True,
        producer_path=binding.get("original_producer_path"),
    )
    need(
        binding["original_selection_sha256"] == terminal["workload_selection_sha256"],
        "BINDING",
    )
    raw_scheduler = read_original(
        Path(binding["original_scheduler_path"]), control, 65536
    )
    need(digest(raw_scheduler) == binding["original_scheduler_sha256"], "TERMINAL")
    validate_original_scheduler(raw_scheduler, terminal)
    need(
        original_selection.get("source_sha") == binding["original_source_git_sha"],
        "BINDING",
    )
    validate_original_namespace(
        original_selection, template, binding, original_producer, offline
    )
    actual, selected = bind_template(template, binding, control, offline, test_root)
    need(output == Path(binding["output_path"]), "OUTPUT")
    selected.disjoint_output(output, test_root if offline else None)
    tc.ancestors(output)
    tc.private(output.parent.lstat(), "DIR", os.geteuid())
    control.claim(0, True)
    output.mkdir(mode=0o700)
    control.record(output / "issued-selection.record", actual)
    sourceinfo = dict(
        version=VERSION,
        status="PAIR_ENTERED_NOT_COMPLETE",
        scope=binding["scope"],
        original_job_id=binding["original_job_id"],
        collection_job_id=collection_job,
        original_source_git_sha=binding["original_source_git_sha"],
        collection_source_git_sha=binding["source_git_sha"],
        original_scheduler_state=terminal["scheduler_state"],
        original_exit_code=terminal["exit_code"],
        original_signal=terminal["signal"],
        original_scheduler_sha256=terminal["raw_scheduler_sha256"],
        original_workload_selection_sha256=binding["original_selection_sha256"],
        collection_uid=os.geteuid(),
        selection_sha256=selected.sha,
        binding_sha256=digest(tc.canonical(binding)),
        authority_sha256=binding["authority_sha256"],
        entry_mono_ns=entered_mono,
        entry_epoch_ns=entered_epoch,
        overall_deadline_epoch_ns=overall_epoch_end,
        parent_deadline_epoch_ns=control.epoch_end,
        external_logs=binding["collection_external_logs"],
        native_or_scientific_acceptance=False,
    )
    if binding["version"] == SUCCESSOR_VERSION:
        sourceinfo.update(version=SUCCESSOR_VERSION, window=binding["window"], collection_purpose=binding["collection_purpose"], original_source_root=binding["original_source_root"], original_producer_path=binding["original_producer_path"], original_producer_sha256=binding["allocation_producer_sha256"])
    control.record(output / "PAIR_CONTEXT.record", sourceinfo)
    filesystem_enter = time.monotonic_ns()
    destination_info = output.lstat()
    tc.private(destination_info, "DIR", os.geteuid())
    destination_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        need(tc.ident(os.fstat(destination_fd)) == tc.ident(destination_info), "OUTPUT")
        fs = os.fstatvfs(destination_fd)  # one actual selected-destination acquisition
        filesystem_exit = time.monotonic_ns()
        need(
            tc.ident(os.fstat(destination_fd))
            == tc.ident(output.lstat())
            == tc.ident(destination_info),
            "OUTPUT",
        )
    finally:
        tc.close_owned(control, (destination_fd,))
    raw_fs = {
        name: getattr(fs, name, None)
        for name in [
            "f_bsize",
            "f_frsize",
            "f_blocks",
            "f_bfree",
            "f_bavail",
            "f_files",
            "f_ffree",
            "f_favail",
            "f_flag",
            "f_namemax",
        ]
    }
    available = (
        fs.f_bavail * fs.f_frsize
        if type(fs.f_bavail) is int
        and fs.f_bavail >= 0
        and type(fs.f_frsize) is int
        and fs.f_frsize > 0
        else None
    )
    control.record(
        output / "FILESYSTEM_OBSERVATION.record",
        dict(
            version=VERSION,
            scope="FILESYSTEM_REPORTED_NOT_RESERVED",
            acquisition_enter_mono_ns=filesystem_enter,
            acquisition_exit_mono_ns=filesystem_exit,
            selected_destination=str(output),
            selected_private_directory_identity=list(tc.ident(destination_info)),
            raw_fields=raw_fs,
            derived_available_unreserved_bytes=available,
            inode_availability_interpretation="RAW_REPORTED_VALUE_NOT_ENTITLEMENT_OR_GUARANTEE",
            project_quota_and_entitlement="UNKNOWN_NOT_QUERIED",
            capacity_or_native_containment_guarantee=False,
        ),
    )
    need(available is not None and available > 0, "OUTPUT")
    selection_path = output / "issued-selection.record"
    children = []
    lifecycle = []
    readfd = writefd = None
    selector = selectors.DefaultSelector()
    handles = []
    first_code = None
    exits = {}
    joined = False
    try:
        readfd, writefd = os.pipe()
        env = {
            "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(helper.parent.parent / "src"),
        }
        if not offline:
            env.update(
                SAFE_EXECUTION_SITE=os.environ.get("SAFE_EXECUTION_SITE", ""),
                SLURM_JOB_ID=os.environ.get("SLURM_JOB_ID", ""),
            )
        for role in ["receive", "export"]:
            control.check()
            logpath = output / (role + ".stderr")
            control.claim(0, True)
            logfd = os.open(logpath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            handles.append(logfd)
            argv = child_argv(
                helper,
                selection_path,
                selected,
                output / role,
                offline,
                test_root,
                role,
            )
            role_entered = time.monotonic_ns()
            proc = subprocess.Popen(
                argv,
                stdin=readfd if role == "receive" else subprocess.DEVNULL,
                stdout=writefd if role == "export" else subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                close_fds=True,
                start_new_session=True,
                env=env,
            )
            children.append(proc)
            lifecycle.append(
                dict(
                    role=role,
                    pid=proc.pid,
                    popen_enter_ns=role_entered,
                    popen_return_ns=time.monotonic_ns(),
                    deadline_ns=min(
                        control.end, role_entered + selected.limits["seconds"] * 10**9
                    ),
                    observed_exit_ns=None,
                    joined_ns=None,
                )
            )
            lifecycle[-1]["kill_at_ns"] = role_kill_at(
                lifecycle[-1]["deadline_ns"], control.end
            )
            selector.register(
                proc.stderr,
                selectors.EVENT_READ,
                dict(role=role, fd=logfd, size=0, proc=proc),
            )
        os.close(readfd)
        readfd = None
        os.close(writefd)
        writefd = None
        while selector.get_map() or any(p.poll() is None for p in children):
            control.check()
            for index, proc in enumerate(children):
                if proc.poll() is None:
                    need(
                        time.monotonic_ns() < lifecycle[index]["kill_at_ns"], "DEADLINE"
                    )
            for key, _ in selector.select(timeout=0.05):
                raw = os.read(key.fileobj.fileno(), 65536)
                data = key.data
                if not raw:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                data["size"] += len(raw)
                require_stderr_bytes(data["size"])
                control.claim(len(raw))
                view = memoryview(raw)
                while view:
                    control.check()
                    n = os.write(data["fd"], view)
                    need(n > 0, "WRITE_BYTES")
                    view = view[n:]
            for index, proc in enumerate(children):
                value = proc.poll()
                if value is not None and lifecycle[index]["observed_exit_ns"] is None:
                    lifecycle[index]["observed_exit_ns"] = time.monotonic_ns()
                    require_role_time(
                        lifecycle[index], lifecycle[index]["observed_exit_ns"]
                    )
                if value is not None and value != 0:
                    raise tc.Stop("CHILD_EXIT")
        for index, proc in enumerate(children):
            exits["receive" if index == 0 else "export"] = proc.wait(timeout=0.1)
            lifecycle[index]["joined_ns"] = time.monotonic_ns()
            if lifecycle[index]["observed_exit_ns"] is None:
                lifecycle[index]["observed_exit_ns"] = lifecycle[index]["joined_ns"]
            require_role_time(lifecycle[index], lifecycle[index]["joined_ns"])
        joined = True
        need(exits == {"receive": 0, "export": 0}, "CHILD_EXIT")
        for fd in handles:
            os.fsync(fd)
        source_hash(helper, binding["helper_sha256"], control)
        source_hash(parent, binding["parent_sha256"], control)
        sender = tc.parse(
            read_original(output / "export/COLLECTION_COMPLETE.record", control, 16384)
        )
        receiver = tc.parse(
            read_original(output / "receive/COLLECTION_COMPLETE.record", control, 16384)
        )
        need(
            sender["status"] == receiver["status"] == "COLLECTION_INTEGRITY_COMPLETE"
            and sender["selection_sha256"]
            == receiver["selection_sha256"]
            == selected.sha
            and sender["summary"] == receiver["summary"]
            and receiver["independently_rehashed"] is True,
            "SUMMARY",
        )
        workload_verification = verify_workload(
            verifier_path,
            original_selection,
            control,
            binding["verifier_sha256"],
            binding["original_selection_sha256"],
        )
        verification_path = output / "WORKLOAD_VERIFICATION.record"
        verification_sha = control.record(
            verification_path, workload_verification, 1048576
        )
        artifacts = []
        for label, relative, maximum, expected in [
            (
                "archive",
                "terminal.s12c",
                selected.limits["wire_bytes"],
                receiver["archive_sha256"],
            ),
            (
                "before",
                "before.jsonl",
                selected.limits["manifest_bytes"],
                sender["summary"]["manifest_sha256"],
            ),
            (
                "after",
                "after.jsonl",
                selected.limits["manifest_bytes"],
                sender["summary"]["manifest_sha256"],
            ),
        ]:
            path = output / "receive" / relative
            value = hash_original(path, control, maximum)
            need(value["sha256"] == expected, "SOURCE_CHANGED")
            artifacts.append(dict(label=label, path=str(path), **value))
        proof_hash = hash_original(verification_path, control, 1048576)
        need(proof_hash["sha256"] == verification_sha, "SOURCE_CHANGED")
        artifacts.append(
            dict(label="verification", path=str(verification_path), **proof_hash)
        )
        ready = dict(
            version=SUCCESSOR_READY_VERSION if binding["version"] == SUCCESSOR_VERSION else READY_VERSION,
            scope=binding["scope"],
            context=sourceinfo,
            artifacts=artifacts,
            parent_controls_byte_limit=16 * 2**20,
            local_retention_byte_limit=selected.limits["wire_bytes"]
            + 2 * selected.limits["manifest_bytes"]
            + 1048576,
            local_receipt_path=str(output / "RETENTION_RECEIPT.record"),
            native_or_scientific_acceptance=False,
        )
        if binding["version"] == SUCCESSOR_VERSION:
            ready["collection_selection"] = actual
        ready_sha = control.record(output / "TRANSPORT_READY.record", ready)
        receipt_path = output / "RETENTION_RECEIPT.record"
        while not receipt_path.exists():
            control.check()
            time.sleep(0.05)
        receipt = tc.parse(read_original(receipt_path, control, 65536))
        validate_receipt(receipt, ready, ready_sha)
        receipt_ack_sha = control.record(
            output / "RETENTION_RECEIPT_ACK.record",
            dict(
                version=binding["version"],
                status="RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED",
                ready_sha256=ready_sha,
                receipt_sha256=digest(tc.canonical(receipt)),
                receipt=receipt,
                original_job_id=binding["original_job_id"],
                collection_job_id=collection_job,
                acknowledgement_mono_ns=time.monotonic_ns(),
                native_or_scientific_acceptance=False,
            ),
        )
        for row in artifacts:
            actual_hash = hash_original(Path(row["path"]), control, row["bytes"])
            need(
                actual_hash == {k: row[k] for k in ["bytes", "sha256", "identity"]},
                "SOURCE_CHANGED",
            )
        control.check()
        need(not control.cleanup_uncertain, "CLOSE_UNCERTAIN")
        result = dict(
            version=binding["version"],
            status="PROVISIONAL_INTEGRITY_COMPLETE_PENDING_TERMINAL_LOGS_AND_REVIEW",
            scope=binding["scope"],
            context=sourceinfo,
            ready_sha256=ready_sha,
            receipt_sha256=digest(tc.canonical(receipt)),
            receipt_ack_sha256=receipt_ack_sha,
            exits=exits,
            child_lifecycle=lifecycle,
            children_joined=True,
            local_transport_and_hash_receipt_verified=True,
            workload_verification_complete=workload_verification["complete"],
            candidate_native_eligible=original_candidate_eligible(
                terminal, workload_verification
            ),
            native_or_scientific_acceptance=False,
            read_bytes=control.read_bytes,
            read_calls=control.read_calls,
            control_write_bytes=control.write_bytes,
            control_creations=control.creations,
            complete_mono_ns=time.monotonic_ns(),
            complete_epoch_ns=time.time_ns(),
        )
        control.record(output / "PAIR_PROVISIONAL_COMPLETE.record", result)
        control.check()
        return result
    except BaseException as error:
        first_code = safe_code(error)
        if not stop_children(
            children,
            min(
                [control.end, time.monotonic_ns() + 5 * 10**9]
                + [row["deadline_ns"] for row in lifecycle]
            ),
            control,
        ):
            first_code = first_code or "CHILD_LIFECYCLE"
        if output.exists():
            try:
                control.record(
                    output / "PAIR_INCOMPLETE.record",
                    dict(
                        version=binding["version"],
                        status="INCOMPLETE",
                        primary_code=first_code,
                        children_joined=all(p.poll() is not None for p in children),
                        cleanup_uncertain=control.cleanup_uncertain,
                        native_or_scientific_acceptance=False,
                    ),
                )
            except BaseException:
                pass
        raise
    finally:
        close_error = False
        for fd in [readfd, writefd, *handles]:
            if fd is not None:
                try:
                    os.close(fd)
                except BaseException:
                    close_error = True
        try:
            remaining = list(selector.get_map().values())
        except BaseException:
            remaining = []
            close_error = True
        for key in remaining:
            try:
                key.fileobj.close()
            except BaseException:
                close_error = True
        try:
            selector.close()
        except BaseException:
            close_error = True
        if close_error:
            control.cleanup_uncertain = True
            active = sys.exc_info()[1]
            if type(active) is tc.Stop:
                active.cleanup_uncertain = True
            if active is None:
                raise tc.Stop("CLOSE_UNCERTAIN")
        if not joined and any(p.poll() is None for p in children):
            control.cleanup_uncertain = True


def validate_transport_domain(value):
    fields(value, "host boot_id mount_namespace session_nonce session_pid", "DOMAIN")
    need(type(value["host"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", value["host"]), "DOMAIN")
    need(type(value["boot_id"]) is str and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", value["boot_id"]), "DOMAIN")
    need(type(value["mount_namespace"]) is str and re.fullmatch(r"mnt:\[[0-9]{1,20}\]", value["mount_namespace"]), "DOMAIN")
    need(type(value["session_nonce"]) is str and re.fullmatch(r"[0-9a-f]{32}", value["session_nonce"]), "DOMAIN")
    tc.uint(value["session_pid"], True)


def validate_transport_evidence(evidence, ready=None):
    fields(evidence, "version domain_before domain_after ancestors files exit_code observed_joined", "DOMAIN")
    need(evidence["version"] == "stage12_same_session_transfer_v2" and evidence["exit_code"] == 0
         and type(evidence["exit_code"]) is int and evidence["observed_joined"] is True, "CHILD_EXIT")
    validate_transport_domain(evidence["domain_before"])
    validate_transport_domain(evidence["domain_after"])
    need(evidence["domain_before"] == evidence["domain_after"], "DOMAIN")
    need(type(evidence["ancestors"]) is list and 1 <= len(evidence["ancestors"]) <= 1280, "ANCESTOR")
    seen = set()
    import stat
    for row in evidence["ancestors"]:
        fields(row, "path before after", "ANCESTOR")
        path = tc.absolute(row["path"])
        need(path not in seen, "ANCESTOR")
        seen.add(path)
        for value in (row["before"], row["after"]):
            need(type(value) is list and len(value) == 9, "ANCESTOR")
            for n in value:
                tc.uint(n)
            need(stat.S_ISDIR(value[2]), "ANCESTOR")
        need(row["before"][:6] == row["after"][:6], "ANCESTOR_CHANGED")
    need(type(evidence["files"]) is list and 1 <= len(evidence["files"]) <= 16, "FRAME")
    labels, paths = set(), set()
    for row in evidence["files"]:
        fields(row, "label path before after bytes sha256", "FRAME")
        path = tc.absolute(row["path"])
        need(type(row["label"]) is str and tc.LABEL.fullmatch(row["label"]) and row["label"] not in labels and path not in paths, "FRAME")
        labels.add(row["label"])
        paths.add(path)
        identity = row["before"]
        need(type(identity) is list and len(identity) == 9 and identity == row["after"], "SOURCE_CHANGED")
        for n in identity:
            tc.uint(n)
        tc.uint(row["bytes"])
        hash_string(row["sha256"])
        need(stat.S_ISREG(identity[2]) and stat.S_IMODE(identity[2]) == 0o600 and identity[5] == 1
             and identity[6] == row["bytes"], "PRIVATE")
        need(all(parent in seen for parent in path.parents), "ANCESTOR")
    if ready is not None:
        need([{k: r[k] for k in ("label", "path", "bytes", "sha256")} for r in evidence["files"]]
             == [{k: r[k] for k in ("label", "path", "bytes", "sha256")} for r in ready["artifacts"]], "RETENTION")
        need(all(r["before"][3] == ready["context"]["collection_uid"] for r in evidence["files"]), "PRIVATE")
    need(len(tc.canonical(evidence)) <= 49152, "LIMITS")
    return evidence


def validate_archive_open(value, ready):
    fields(value, "version status selection_sha256 archive_sha256 summary actual_read_bytes actual_read_calls entered_epoch_ns completed_epoch_ns source_identity native_or_scientific_acceptance", "RETENTION")
    need(value["version"] == "stage12_readonly_collection_archive_open_v1" and value["status"] == "COMPLETE"
         and value["selection_sha256"] == ready["context"]["selection_sha256"]
         and value["archive_sha256"] == ready["artifacts"][0]["sha256"]
         and value["native_or_scientific_acceptance"] is False, "RETENTION")
    fields(value["summary"], "members payload_bytes manifest_bytes manifest_sha256", "SUMMARY")
    for key in ("actual_read_bytes", "actual_read_calls", "entered_epoch_ns", "completed_epoch_ns"):
        tc.uint(value[key])
    need(value["entered_epoch_ns"] <= value["completed_epoch_ns"] < ready["context"]["overall_deadline_epoch_ns"]
         and value["actual_read_bytes"] <= 8*2**30 and value["actual_read_calls"] <= 262144, "DEADLINE")
    need(type(value["source_identity"]) is list and len(value["source_identity"]) == 9, "RETENTION")
    for n in value["source_identity"]:
        tc.uint(n)


class _FreshReader:
    """One immutable FD with bounded buffering; no write or source materialization."""

    def __init__(self, path, control, maximum):
        self.path, self.control = tc.absolute(str(path)), control
        self.chain = tc.ancestors(self.path)
        self.before = self.path.lstat()
        tc.private(self.before, "FILE", os.geteuid())
        need(self.before.st_size <= maximum, "READ_BYTES")
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        self.buffer = bytearray()
        self.returned = self.fetched = 0
        self.sha = hashlib.sha256()
        self.closed = False
        try:
            need(tc.ident(os.fstat(self.fd)) == tc.ident(self.before), "SOURCE_CHANGED")
        except BaseException:
            self.close()
            raise

    def read(self, amount):
        need(type(amount) is int and 0 <= amount <= 65536, "READ_BYTES")
        while len(self.buffer) < amount and self.fetched < self.before.st_size:
            part = self.control.read(self.fd, min(65536, self.before.st_size - self.fetched))
            need(part, "TRUNCATED")
            self.fetched += len(part)
            self.sha.update(part)
            self.buffer.extend(part)
        out = bytes(self.buffer[:amount])
        del self.buffer[:len(out)]
        self.returned += len(out)
        return out

    def line(self, limit):
        raw = bytearray()
        while True:
            if not self.buffer and self.fetched < self.before.st_size:
                part = self.control.read(self.fd, min(65536, self.before.st_size - self.fetched))
                need(part, "TRUNCATED")
                self.fetched += len(part)
                self.sha.update(part)
                self.buffer.extend(part)
            if not self.buffer:
                need(not raw, "FRAME")
                return None
            pos = self.buffer.find(b"\n")
            size = len(self.buffer) if pos < 0 else pos + 1
            need(len(raw) + size <= limit, "FRAME")
            raw.extend(self.buffer[:size])
            del self.buffer[:size]
            self.returned += size
            if pos >= 0:
                return bytes(raw)

    def finish(self):
        need(not self.buffer and self.returned == self.fetched == self.before.st_size, "TRUNCATED")
        need(not self.control.read(self.fd, 1)
             and tc.ident(os.fstat(self.fd)) == tc.ident(self.before) == tc.ident(self.path.lstat()), "SOURCE_CHANGED")
        tc.check_ancestors(self.chain)
        return dict(bytes=self.fetched, sha256=self.sha.hexdigest(), identity=list(tc.ident(self.before)))

    def close(self):
        if not self.closed:
            self.closed = True
            tc.close_owned(self.control, (self.fd,))


def open_retained_archive(ready, local_root, control):
    """Actual read-only complete frame/payload opener, using tc's wire/row contracts."""
    selected = tc.Selection(ready["collection_selection"], ready["scope"] == TEST,
                            tc.absolute(ready["collection_selection"]["roots"][0]["path"]).parent if ready["scope"] == TEST else None)
    need(selected.sha == ready["context"]["selection_sha256"], "BINDING")
    root = Path(local_root)
    entered = time.time_ns()
    archive = _FreshReader(root / "archive.original", control, ready["artifacts"][0]["bytes"])
    readers = []
    class Wire(tc.WireIn):
        def __init__(self):
            self.s = selected
        def read(self, n):
            return archive.read(n)
    wire = Wire()
    summary = None
    try:
        need(wire.exact(len(selected.magic)) == selected.magic, "PROTOCOL")
        frame = wire.frame()
        tc.frame_kind(frame, "BEGIN", {"version", "scope", "selection_sha256"})
        need(frame == dict(kind="BEGIN", version=selected.version, scope=tc.SCOPE, selection_sha256=selected.sha), "BINDING")
        before_frame = wire.frame()
        tc.frame_kind(before_frame, "BEFORE", {"summary"})
        summary = before_frame["summary"]
        fields(summary, "members payload_bytes manifest_bytes manifest_sha256", "SUMMARY")
        for key in ("members", "payload_bytes", "manifest_bytes"):
            tc.uint(summary[key])
            need(summary[key] <= selected.limits[key], "LIMITS")
        hash_string(summary["manifest_sha256"])
        before = _FreshReader(root / "before.original", control, selected.limits["manifest_bytes"])
        readers.append(before)
        count = payload = length = 0
        sha = hashlib.sha256()
        previous = None
        found, inert = set(), set()
        for _ in range(summary["members"]):
            raw = before.line(selected.limits["record_bytes"])
            need(raw is not None, "TRUNCATED")
            row = tc.validate_row(tc.parse(raw), selected)
            key = row["path"].encode()
            need(previous is None or previous < key, "PROTOCOL")
            previous = key
            frame = wire.frame()
            tc.frame_kind(frame, "MEMBER", {"entry"})
            need(tc.canonical(frame["entry"]) == raw, "PROTOCOL")
            count += 1
            length += len(raw)
            payload += row["size"] if row["kind"] == "FILE" else 0
            sha.update(raw)
            if row["path"] in selected.logs:
                need(row["kind"] == "FILE", "PROTOCOL")
                found.add(row["path"])
            if row["kind"] == "FIFO_INERT":
                inert.add(row["path"])
        need(before.line(selected.limits["record_bytes"]) is None and found == selected.logs and inert == set(selected.inert), "PROTOCOL")
        manifest = before.finish()
        need(summary == dict(members=count, payload_bytes=payload, manifest_bytes=length, manifest_sha256=sha.hexdigest()), "SUMMARY")
        need(manifest["sha256"] == summary["manifest_sha256"], "PAYLOAD_HASH")
        before.close()
        frame = wire.frame()
        tc.frame_kind(frame, "DATA", {"summary"})
        need(frame["summary"] == summary, "SUMMARY")
        before = _FreshReader(root / "before.original", control, selected.limits["manifest_bytes"])
        readers.append(before)
        for _ in range(summary["members"]):
            raw = before.line(selected.limits["record_bytes"])
            need(raw is not None, "TRUNCATED")
            row = tc.validate_row(tc.parse(raw), selected)
            frame = wire.frame()
            tc.frame_kind(frame, "ENTRY", {"entry"})
            need(tc.canonical(frame["entry"]) == raw, "PROTOCOL")
            if row["kind"] == "FILE":
                left, content_sha = row["size"], hashlib.sha256()
                while left:
                    part = wire.read(min(65536, left))
                    need(part, "TRUNCATED")
                    left -= len(part)
                    content_sha.update(part)
                need(content_sha.hexdigest() == row["sha256"], "PAYLOAD_HASH")
        need(before.line(selected.limits["record_bytes"]) is None, "PROTOCOL")
        need(before.finish()["sha256"] == summary["manifest_sha256"], "SOURCE_CHANGED")
        before.close()
        frame = wire.frame()
        tc.frame_kind(frame, "AFTER", {"summary"})
        need(frame["summary"] == summary, "SUMMARY")
        after = _FreshReader(root / "after.original", control, selected.limits["manifest_bytes"])
        readers.append(after)
        for _ in range(summary["members"]):
            raw = after.line(selected.limits["record_bytes"])
            need(raw is not None, "TRUNCATED")
            frame = wire.frame()
            tc.frame_kind(frame, "MEMBER", {"entry"})
            need(tc.canonical(frame["entry"]) == raw, "SOURCE_CHANGED")
        need(after.line(selected.limits["record_bytes"]) is None, "PROTOCOL")
        need(after.finish()["sha256"] == summary["manifest_sha256"], "SOURCE_CHANGED")
        after.close()
        frame = wire.frame()
        tc.frame_kind(frame, "END", {"summary", "scope"})
        need(frame["summary"] == summary and frame["scope"] == tc.SCOPE and not wire.read(1), "PROTOCOL")
        actual = archive.finish()
        need(actual["bytes"] == ready["artifacts"][0]["bytes"] and actual["sha256"] == ready["artifacts"][0]["sha256"], "PAYLOAD_HASH")
        return actual, dict(version="stage12_readonly_collection_archive_open_v1", status="COMPLETE",
                            selection_sha256=selected.sha, archive_sha256=actual["sha256"], summary=summary,
                            actual_read_bytes=control.read_bytes, actual_read_calls=control.read_calls,
                            entered_epoch_ns=entered, completed_epoch_ns=time.time_ns(),
                            source_identity=actual["identity"], native_or_scientific_acceptance=False)
    finally:
        for reader in [archive, *readers]:
            reader.close()


def validate_ready(ready):
    successor = ready.get("version") == SUCCESSOR_READY_VERSION
    fields(
        ready,
        "version scope context artifacts parent_controls_byte_limit local_retention_byte_limit local_receipt_path native_or_scientific_acceptance" + (" collection_selection" if successor else ""),
    )
    need(
        ready["version"] in (READY_VERSION, SUCCESSOR_READY_VERSION)
        and ready["scope"] in (TEST, NATIVE)
        and ready["native_or_scientific_acceptance"] is False,
        "RETENTION",
    )
    need(
        type(ready["artifacts"]) is list
        and [r.get("label") for r in ready["artifacts"]]
        == ["archive", "before", "after", "verification"],
        "RETENTION",
    )
    limits = {
        "archive": 3 * 2**30,
        "before": 128 * 2**20,
        "after": 128 * 2**20,
        "verification": 1048576,
    }
    for row in ready["artifacts"]:
        fields(row, "label path bytes sha256 identity")
        tc.absolute(row["path"])
        hash_string(row["sha256"])
        tc.uint(row["bytes"])
        need(
            row["bytes"] <= limits[row["label"]]
            and type(row["identity"]) is list
            and len(row["identity"]) == 9,
            "RETENTION",
        )
        for number in row["identity"]:
            tc.uint(number)
    tc.absolute(ready["local_receipt_path"])
    tc.uint(ready["parent_controls_byte_limit"])
    tc.uint(ready["local_retention_byte_limit"])
    need(
        ready["parent_controls_byte_limit"] == 16 * 2**20
        and sum(r["bytes"] for r in ready["artifacts"])
        <= ready["local_retention_byte_limit"]
        <= 3 * 2**30 + 2 * 128 * 2**20 + 1048576,
        "RETENTION",
    )
    context = ready["context"]
    successor = ready["version"] == SUCCESSOR_READY_VERSION
    fields(
        context,
        "version status scope original_job_id collection_job_id original_source_git_sha collection_source_git_sha original_workload_selection_sha256 collection_uid original_scheduler_state original_exit_code original_signal original_scheduler_sha256 selection_sha256 binding_sha256 authority_sha256 entry_mono_ns entry_epoch_ns overall_deadline_epoch_ns parent_deadline_epoch_ns external_logs native_or_scientific_acceptance" + (" " + SUCCESSOR_CONTEXT_FIELDS if successor else ""),
        "RETENTION",
    )
    need(
        context["version"] == (SUCCESSOR_VERSION if successor else VERSION)
        and context["scope"] == ready["scope"]
        and context["native_or_scientific_acceptance"] is False,
        "RETENTION",
    )
    for key in [
        "original_job_id",
        "collection_job_id",
        "collection_uid",
        "original_exit_code",
        "original_signal",
        "entry_mono_ns",
        "entry_epoch_ns",
        "overall_deadline_epoch_ns",
        "parent_deadline_epoch_ns",
    ]:
        tc.uint(context[key])
    need(
        context["entry_epoch_ns"]
        < context["parent_deadline_epoch_ns"]
        <= context["overall_deadline_epoch_ns"],
        "DEADLINE",
    )
    for key in [
        "selection_sha256",
        "original_workload_selection_sha256",
        "original_scheduler_sha256",
        "binding_sha256",
        "authority_sha256",
    ]:
        hash_string(context[key])


def validate_receipt(receipt, ready, ready_sha):
    successor = ready["version"] == SUCCESSOR_READY_VERSION
    fields(
        receipt,
        "version scope ready_sha256 original_job_id collection_job_id selection_sha256 artifacts local_root local_root_identity local_start_epoch_ns local_complete_epoch_ns actual_read_bytes actual_read_calls native_or_scientific_acceptance" + (" transport_evidence whole_collection_opener" if successor else ""),
    )
    need(
        receipt["version"] == (SUCCESSOR_RECEIPT_VERSION if successor else RECEIPT_VERSION)
        and receipt["scope"] == ready["scope"]
        and receipt["ready_sha256"] == ready_sha
        and receipt["native_or_scientific_acceptance"] is False,
        "RETENTION",
    )
    ctx = ready["context"]
    if successor:
        validate_transport_evidence(receipt["transport_evidence"], ready)
        validate_archive_open(receipt["whole_collection_opener"], ready)
    for key in [
        "original_job_id",
        "collection_job_id",
        "local_start_epoch_ns",
        "local_complete_epoch_ns",
        "actual_read_bytes",
        "actual_read_calls",
    ]:
        tc.uint(receipt[key])
    hash_string(receipt["selection_sha256"])
    hash_string(receipt["ready_sha256"])
    need(type(receipt["artifacts"]) is list, "RETENTION")
    for row in receipt["artifacts"]:
        fields(row, "label bytes sha256 local_identity", "RETENTION")
        tc.uint(row["bytes"])
        identity = row["local_identity"]
        need(type(identity) is list and len(identity) == 9, "RETENTION")
        for number in identity:
            tc.uint(number)
        import stat

        need(
            stat.S_ISREG(identity[2])
            and stat.S_IMODE(identity[2]) == 0o600
            and identity[5] == 1
            and identity[6] == row["bytes"],
            "PRIVATE",
        )
        hash_string(row["sha256"])
    tc.absolute(receipt["local_root"])
    root_identity = receipt["local_root_identity"]
    need(type(root_identity) is list and len(root_identity) == 5, "RETENTION")
    for number in root_identity:
        tc.uint(number)
    import stat

    need(
        stat.S_ISDIR(root_identity[2]) and stat.S_IMODE(root_identity[2]) == 0o700,
        "PRIVATE",
    )
    for key in ["original_job_id", "collection_job_id", "selection_sha256"]:
        need(receipt[key] == ctx[key], "RETENTION")
    need(
        [
            {k: row[k] for k in ["label", "bytes", "sha256"]}
            for row in receipt["artifacts"]
        ]
        == [
            {k: row[k] for k in ["label", "bytes", "sha256"]}
            for row in ready["artifacts"]
        ],
        "RETENTION",
    )
    need(
        type(receipt["local_start_epoch_ns"]) is int
        and ctx["entry_epoch_ns"]
        <= receipt["local_start_epoch_ns"]
        <= receipt["local_complete_epoch_ns"]
        < ctx["parent_deadline_epoch_ns"],
        "DEADLINE",
    )


def verify_retention(
    ready,
    ready_sha,
    local_root,
    receipt_path,
    entered_mono,
    entered_epoch,
    *,
    control=None,
    transport_evidence=None,
):
    validate_ready(ready)
    need(digest(tc.canonical(ready)) == ready_sha, "RETENTION")
    ctx = ready["context"]
    if ready["version"] == SUCCESSOR_READY_VERSION:
        need(ready["collection_selection"] is not None, "BINDING")
    if control is None:
        control = Control(entered_mono, ctx["parent_deadline_epoch_ns"], 900)
    else:
        # A connected transport retains its original time/counter owner. The
        # authenticated remote deadline can tighten it, never restart it.
        need(type(control) is Control, "RETENTION")
        control.epoch_end = min(control.epoch_end, ctx["parent_deadline_epoch_ns"])
    control.check()
    local_root = tc.absolute(str(local_root))
    tc.ancestors(local_root)
    tc.private(local_root.lstat(), "DIR", os.geteuid())
    expected_names = {row["label"] + ".original" for row in ready["artifacts"]}
    with os.scandir(local_root) as entries:
        seen = set()
        for entry in entries:
            control.check()
            need(entry.name in expected_names and entry.name not in seen, "RETENTION")
            seen.add(entry.name)
        need(seen == expected_names, "RETENTION")
    result_artifacts = []
    opener = None
    for row in ready["artifacts"]:
        path = local_root / (row["label"] + ".original")
        if ready["version"] == SUCCESSOR_READY_VERSION and row["label"] == "archive":
            got, opener = open_retained_archive(ready, local_root, control)
        else:
            got = hash_original(path, control, row["bytes"])
        need(
            got["bytes"] == row["bytes"] and got["sha256"] == row["sha256"], "RETENTION"
        )
        result_artifacts.append(
            dict(
                {k: row[k] for k in ["label", "bytes", "sha256"]},
                local_identity=got["identity"],
            )
        )
    receipt = dict(
        version=SUCCESSOR_RECEIPT_VERSION if ready["version"] == SUCCESSOR_READY_VERSION else RECEIPT_VERSION,
        scope=ready["scope"],
        ready_sha256=ready_sha,
        original_job_id=ctx["original_job_id"],
        collection_job_id=ctx["collection_job_id"],
        selection_sha256=ctx["selection_sha256"],
        artifacts=result_artifacts,
        local_root=str(local_root),
        local_root_identity=list(tc.ident(local_root.lstat())[:5]),
        local_start_epoch_ns=entered_epoch,
        local_complete_epoch_ns=time.time_ns(),
        actual_read_bytes=control.read_bytes,
        actual_read_calls=control.read_calls,
        native_or_scientific_acceptance=False,
    )
    if ready["version"] == SUCCESSOR_READY_VERSION:
        receipt["transport_evidence"] = transport_evidence
        receipt["whole_collection_opener"] = opener
    validate_receipt(receipt, ready, ready_sha)
    need(tc.contained(tc.absolute(str(receipt_path)), local_root), "PATH")
    control.record(receipt_path, receipt)
    control.check()
    return receipt


def verify_local_retained(ready, receipt, retained_root, control):
    validate_ready(ready)
    validate_receipt(receipt, ready, digest(tc.canonical(ready)))
    root = tc.absolute(str(retained_root))
    need(root == tc.absolute(receipt["local_root"]), "RETENTION")
    tc.ancestors(root)
    tc.private(root.lstat(), "DIR", os.geteuid())
    need(
        list(tc.ident(root.lstat())[:5]) == receipt["local_root_identity"],
        "SOURCE_CHANGED",
    )
    opener = None
    for expected, stored in zip(ready["artifacts"], receipt["artifacts"], strict=True):
        if ready["version"] == SUCCESSOR_READY_VERSION and expected["label"] == "archive":
            current, opener = open_retained_archive(ready, root, control)
        else:
            current = hash_original(root / (expected["label"] + ".original"), control, expected["bytes"])
        need(
            current["bytes"] == expected["bytes"]
            and current["sha256"] == expected["sha256"]
            and current["identity"] == stored["local_identity"],
            "SOURCE_CHANGED",
        )
    control.check()
    return opener


def verify_final_logs(
    provisional,
    provisional_sha,
    terminal,
    index,
    local_root,
    result_path,
    entered_mono,
    entered_epoch,
    *,
    retained_root=None,
    control=None,
):
    need(
        type(provisional) is dict
        and provisional.get("version") in (VERSION, SUCCESSOR_VERSION)
        and provisional.get("status")
        == "PROVISIONAL_INTEGRITY_COMPLETE_PENDING_TERMINAL_LOGS_AND_REVIEW"
        and provisional.get("children_joined") is True
        and provisional.get("exits") == {"receive": 0, "export": 0}
        and type(provisional.get("workload_verification_complete")) is bool
        and provisional.get("native_or_scientific_acceptance") is False,
        "FINAL_LOGS",
    )
    need(digest(tc.canonical(provisional)) == provisional_sha, "FINAL_LOGS")
    ctx = provisional["context"]
    fields(
        terminal,
        "version collection_job_id source_git_sha binding_sha256 scope scheduler_state exit_code start_epoch_ns end_epoch_ns observed_epoch_ns",
        "TERMINAL",
    )
    need(
        terminal["version"] == "stage12_terminal_collection_scheduler_v1"
        and terminal["scope"] == ctx["scope"]
        and terminal["collection_job_id"] == ctx["collection_job_id"]
        and terminal["source_git_sha"] == ctx["collection_source_git_sha"]
        and terminal["binding_sha256"] == ctx["binding_sha256"]
        and terminal["scheduler_state"] == "COMPLETED"
        and terminal["exit_code"] == "0:0",
        "TERMINAL",
    )
    for key in [
        "collection_job_id",
        "start_epoch_ns",
        "end_epoch_ns",
        "observed_epoch_ns",
    ]:
        tc.uint(terminal[key])
    need(
        terminal["start_epoch_ns"]
        <= ctx["entry_epoch_ns"]
        <= terminal["end_epoch_ns"]
        <= terminal["observed_epoch_ns"]
        <= time.time_ns()
        and terminal["end_epoch_ns"] < ctx["overall_deadline_epoch_ns"],
        "DEADLINE",
    )
    effective_end = min(
        ctx["overall_deadline_epoch_ns"],
        terminal["start_epoch_ns"] + 1800 * 10**9,
        family_end(ctx),
    )
    if control is None:
        control = Control(entered_mono, effective_end, 120)
    else:
        control.epoch_end = min(control.epoch_end, effective_end)
        need(control.end == entered_mono + 120*10**9, "DEADLINE")
    control.check()
    fields(
        index,
        "version context_sha256 logs transport_start_epoch_ns transport_complete_epoch_ns" + (" transport_evidence" if ctx["version"] == SUCCESSOR_VERSION else ""),
        "FINAL_LOGS",
    )
    need(
        index["version"] == ("stage12_terminal_same_domain_log_copies_v2" if ctx["version"] == SUCCESSOR_VERSION else "stage12_terminal_log_copies_v1")
        and index["context_sha256"] == digest(tc.canonical(ctx))
        and type(index["logs"]) is list,
        "FINAL_LOGS",
    )
    tc.uint(index["transport_start_epoch_ns"])
    tc.uint(index["transport_complete_epoch_ns"])
    need(
        terminal["end_epoch_ns"]
        <= index["transport_start_epoch_ns"]
        <= index["transport_complete_epoch_ns"]
        < ctx["overall_deadline_epoch_ns"],
        "DEADLINE",
    )
    expected = {r["label"]: r["path"] for r in ctx["external_logs"]}
    need(1 <= len(expected) <= 16 and len(index["logs"]) == len(expected), "FINAL_LOGS")
    root = tc.absolute(str(local_root))
    tc.ancestors(root)
    tc.private(root.lstat(), "DIR", os.geteuid())
    ready_raw = read_original(root / "transport-ready.original", control, 65536)
    need(digest(ready_raw) == provisional["ready_sha256"], "RETENTION")
    ready = tc.parse(ready_raw)
    validate_ready(ready)
    need(ready["context"] == ctx, "RETENTION")
    receipt_raw = read_original(root / "retention-receipt.original", control, 65536)
    need(digest(receipt_raw) == provisional["receipt_sha256"], "RETENTION")
    receipt = tc.parse(receipt_raw)
    validate_receipt(receipt, ready, provisional["ready_sha256"])
    ack_raw = read_original(root / "retention-ack.original", control, 65536)
    need(digest(ack_raw) == provisional["receipt_ack_sha256"], "RETENTION")
    ack = tc.parse(ack_raw)
    fields(
        ack,
        "version status ready_sha256 receipt_sha256 receipt original_job_id collection_job_id acknowledgement_mono_ns native_or_scientific_acceptance",
        "RETENTION",
    )
    need(
        ack["version"] == ctx["version"]
        and ack["status"] == "RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED"
        and ack["ready_sha256"] == provisional["ready_sha256"]
        and ack["receipt_sha256"] == provisional["receipt_sha256"]
        and tc.canonical(ack["receipt"]) == receipt_raw
        and ack["original_job_id"] == ctx["original_job_id"]
        and ack["collection_job_id"] == ctx["collection_job_id"]
        and ack["native_or_scientific_acceptance"] is False,
        "RETENTION",
    )
    tc.uint(ack["acknowledgement_mono_ns"])
    need(
        ctx["entry_mono_ns"]
        <= ack["acknowledgement_mono_ns"]
        <= provisional["complete_mono_ns"],
        "RETENTION",
    )
    need(retained_root is not None, "RETENTION")
    opener = verify_local_retained(ready, receipt, retained_root, control)
    seen = set()
    size = 0
    hashes = []
    for row in index["logs"]:
        fields(
            row,
            "label remote_path source_identity_before source_identity_after bytes sha256 local_name",
            "FINAL_LOGS",
        )
        need(
            row["label"] in expected
            and row["label"] not in seen
            and row["remote_path"] == expected[row["label"]]
            and row["local_name"] == row["label"] + ".log.original",
            "FINAL_LOGS",
        )
        seen.add(row["label"])
        tc.uint(row["bytes"])
        hash_string(row["sha256"])
        identity = row["source_identity_before"]
        need(
            type(identity) is list
            and len(identity) == 9
            and identity == row["source_identity_after"],
            "SOURCE_CHANGED",
        )
        for number in identity:
            tc.uint(number)
        import stat

        need(
            stat.S_ISREG(identity[2])
            and stat.S_IMODE(identity[2]) == 0o600
            and identity[3] == ctx["collection_uid"]
            and identity[5] == 1
            and identity[6] == row["bytes"],
            "PRIVATE",
        )
        size += row["bytes"]
        need(size <= 16 * 2**20, "FINAL_LOGS")
        actual = hash_original(root / row["local_name"], control, row["bytes"])
        need(
            actual["bytes"] == row["bytes"] and actual["sha256"] == row["sha256"],
            "FINAL_LOGS",
        )
        hashes.append({k: row[k] for k in ["label", "bytes", "sha256"]})
    need(seen == set(expected), "FINAL_LOGS")
    control.check()
    result = dict(
        version=SUCCESSOR_FINAL_VERSION if ctx["version"] == SUCCESSOR_VERSION else FINAL_VERSION,
        status="COLLECTION_INTEGRITY_COMPLETE",
        scope=ctx["scope"],
        provisional_sha256=provisional_sha,
        terminal_sha256=digest(tc.canonical(terminal)),
        log_index_sha256=digest(tc.canonical(index)),
        original_job_id=ctx["original_job_id"],
        collection_job_id=ctx["collection_job_id"],
        original_workload_selection_sha256=ctx["original_workload_selection_sha256"],
        collection_selection_sha256=ctx["selection_sha256"],
        logs=hashes,
        local_retained_artifacts_freshly_reopened=True,
        workload_verification_complete=provisional["workload_verification_complete"],
        candidate_native_eligible=provisional.get("candidate_native_eligible") is True,
        independent_outcome_review_still_required=True,
        native_or_scientific_acceptance=False,
        original_overall_deadline_epoch_ns=ctx["overall_deadline_epoch_ns"],
        observed_complete_epoch_ns=time.time_ns(),
    )
    if ctx["version"] == SUCCESSOR_VERSION:
        validate_transport_evidence(index["transport_evidence"])
        need([{k:r[k] for k in ("label","path","bytes","sha256")} for r in index["transport_evidence"]["files"]] == [dict(label=r["label"],path=r["remote_path"],bytes=r["bytes"],sha256=r["sha256"]) for r in index["logs"]], "FINAL_LOGS")
        result["whole_collection_opener"] = opener
        result["collection_source_git_sha"] = ctx["collection_source_git_sha"]
        result["original_source_git_sha"] = ctx["original_source_git_sha"]
    need(tc.contained(tc.absolute(str(result_path)), root), "PATH")
    control.record(result_path, result)
    control.check()
    return result


def safe_code(error):
    return (
        error.args[0]
        if type(error) is tc.Stop
        and len(error.args) == 1
        and type(error.args[0]) is str
        and error.args[0] in (SAFE_CODES | tc.STOP_CODES)
        else "UNCLASSIFIED"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["run-pair", "verify-retention", "verify-final-logs"]
    )
    parser.add_argument("--binding", type=Path)
    parser.add_argument("--binding-sha256")
    parser.add_argument("--authority", type=Path)
    parser.add_argument("--authority-sha256")
    parser.add_argument("--ready", type=Path)
    parser.add_argument("--ready-sha256")
    parser.add_argument("--local-root", type=Path)
    parser.add_argument("--retained-root", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    parser.add_argument("--provisional", type=Path)
    parser.add_argument("--provisional-sha256")
    parser.add_argument("--collection-terminal", type=Path)
    parser.add_argument("--collection-terminal-sha256")
    parser.add_argument("--log-index", type=Path)
    parser.add_argument("--log-index-sha256")
    parser.add_argument("--result-out", type=Path)
    parser.add_argument("--same-domain-successor", action="store_true")
    parser.add_argument("--offline-invented", action="store_true")
    parser.add_argument("--test-root", type=Path)
    args = parser.parse_args(argv)
    try:
        os.umask(0o077)
        bootstrap = Control(
            _ENTRY_MONO_NS,
            (family_end({"version": SUCCESSOR_VERSION}) if args.same_domain_successor else WINDOW_END_NS) if not args.offline_invented else time.time_ns() + 30 * 10**9,
            5,
        )
        if args.action == "verify-final-logs":
            provisional = load_control(
                args.provisional, args.provisional_sha256, bootstrap
            )
            need(args.same_domain_successor == (provisional.get("version") == SUCCESSOR_VERSION), "SCOPE")
            terminal = load_control(
                args.collection_terminal, args.collection_terminal_sha256, bootstrap
            )
            index = load_control(args.log_index, args.log_index_sha256, bootstrap)
            result = verify_final_logs(
                provisional,
                args.provisional_sha256,
                terminal,
                index,
                args.local_root,
                args.result_out,
                _ENTRY_MONO_NS,
                _ENTRY_EPOCH_NS,
                retained_root=args.retained_root,
            )
        elif args.action == "verify-retention":
            ready = load_control(args.ready, args.ready_sha256, bootstrap)
            need(args.same_domain_successor == (ready.get("version") == SUCCESSOR_READY_VERSION), "SCOPE")
            result = verify_retention(
                ready,
                args.ready_sha256,
                args.local_root,
                args.receipt_out,
                _ENTRY_MONO_NS,
                _ENTRY_EPOCH_NS,
            )
        else:
            if not args.offline_invented:
                from safe_geocoding_pipeline.execution_policy import (
                    require_goethe_nhr_slurm,
                )

                require_goethe_nhr_slurm("stage12_terminal_original_pair")
            binding = load_control(args.binding, args.binding_sha256, bootstrap)
            need(args.same_domain_successor == (binding.get("version") == SUCCESSOR_VERSION), "SCOPE")
            validate_binding(binding, args.offline_invented, args.test_root)
            authority = load_control(args.authority, args.authority_sha256, bootstrap)
            need(binding["authority_sha256"] == args.authority_sha256, "AUTHORITY")
            template = load_control(
                Path(binding["selection_template_path"]),
                binding["selection_template_sha256"],
                bootstrap,
            )
            terminal = load_control(
                Path(binding["original_terminal_path"]),
                binding["original_terminal_sha256"],
                bootstrap,
            )
            result = run_pair(
                binding,
                authority,
                template,
                terminal,
                Path(binding["output_path"]),
                args.offline_invented,
                args.test_root,
                _ENTRY_MONO_NS,
                _ENTRY_EPOCH_NS,
            )
        sys.stdout.write(
            tc.canonical(
                dict(
                    version=VERSION,
                    status=result.get("status", "RETENTION_VERIFIED"),
                    native_or_scientific_acceptance=False,
                )
            ).decode()
        )
        sys.stdout.flush()
        return 0
    except BaseException as error:
        sys.stderr.write(
            tc.canonical(
                dict(
                    version=VERSION,
                    status="INCOMPLETE",
                    code=safe_code(error),
                    cleanup_uncertain=getattr(error, "cleanup_uncertain", False)
                    is True,
                    native_or_scientific_acceptance=False,
                )
            ).decode()
        )
        sys.stderr.flush()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

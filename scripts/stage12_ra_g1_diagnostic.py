"""Explicit RA-G1 representative replay: scoped originals, TEST_ONLY transport.

No selection/evidence is issued here. UNISSUED inputs are non-executable. The
shared Goethe guard, pinned original review bundle, LIVE_KERNEL_OBSERVATION and
actual fresh scoped Linux observations are required before fixture/workload use.
Complete containment and physical-capacity guarantees are not claimed.
The scheduler, capture, sampler, writer and openers are the production code.
"""
# ruff: noqa: E402 -- source-entry clocks precede dependency imports.

from __future__ import annotations

# The selected resource prefix includes all imports after this source-entry clock.
import time

_ENTRY_MONO_NS = time.monotonic_ns()
_ENTRY_CPU_NS = time.process_time_ns()

from contextlib import contextmanager
from collections import namedtuple
from bisect import bisect_left
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import socket
import stat
import subprocess
import sys
import threading

VERSION = "stage12_ra_g1_representative_diagnostic_input_v1"
BOOTSTRAP_VERSION = "stage12_ra_g1_representative_bootstrap30_diagnostic_input_v1"
SHARED_LEASE_VERSION = "stage12_ra_g1_shared_lease_representative_input_v1"
REP_ADMIN_VERSION = "stage12_ra_g1_rep_admin_budget_representative_input_v1"
REP_ADMIN_SELECTION = "stage12_resource_selection_rep_admin_budget_ra_g1_v1"
REP512_VERSION = "stage12_ra_g1_rep_first64_512_representative_input_v1"
REP512_SELECTION = "stage12_resource_selection_rep_first64_512_ra_g1_v1"
REP_ADMIN_VERSIONS = (REP_ADMIN_VERSION, REP512_VERSION)
ACTIVE_DIAGNOSTIC_TRACE = None
ACTIVE_DIAGNOSTIC_CHECK = None
BOOTSTRAP_SELECTION = "stage12_resource_selection_bootstrap30_ra_g1_v1"
CONFIG_VERSION = "stage12_ra_g1_representative_configuration_v1"
REVIEW_VERSION = "stage12_representative_review_binding_ra_g1_v1"
SCOPE = "REPRESENTATIVE_NO_SERVICE"
PHASES = (
    ("first64", 346000, 1817, 64),
    ("deep32_size40", 300000, 1572, 32),
    ("controls8", 180000, 200, 8),
    ("malformed", 180000, 0, 3),
)
REP512_PHASES = (("first64", 512000, 1817, 64), *PHASES[1:])


def phases_for(version):
    return REP512_PHASES if version == REP512_VERSION else PHASES


_RESOURCE_PURPOSES = frozenset(
    (
        "sampling_runtime_bound",
        "sampling_bound_review",
        "resource_policy",
        "resource_adoption",
        "resource_selection",
        "resource_technical_review",
        "resource_risk_inventory",
        "owner_reported_project_approval",
        "resource_invocation_graph",
    )
)
_TOP = frozenset(
    (
        "version",
        "scope",
        "source_sha",
        "selection",
        "limits",
        "configuration",
        "phases",
        "runtime_inventory",
        "responses",
    )
)
_LIMITS = frozenset(
    (
        "seconds",
        "maximum_bytes",
        "maximum_creations",
        "rss_bytes",
        "maximum_input_bytes",
        "summary_reserve_bytes",
        "native_helper_bytes_reserve",
        "native_helper_creation_reserve",
    )
)


_CONFIG = frozenset(
    (
        "version",
        "window_start",
        "window_end",
        "sources",
        "transport",
        "campaigns",
        "resources",
        "public_validation_sha256",
        "command_paths",
        "resource_execution",
    )
)


def require(condition, code="RA_G1_DIAGNOSTIC_INPUT_INVALID"):
    if not condition:
        raise RuntimeError(code)


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


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class PhaseDeadlineExpired(TimeoutError):
    """Static diagnostic classification; never a successful negative result."""


class PhaseBoundary:
    TAGS = frozenset(
        (
            "PHASE_OPEN",
            "CAPTURE",
            "SAMPLING_INSPECTION",
            "OBSERVER_CLOSE",
            "NORMAL_OPEN",
            "NEGATIVE_OPEN",
            "CONTROL_VERIFY",
            "RUNTIME_RECHECK",
        )
    )

    def __init__(self, clock, end_ns, phase_id, global_check, persist=None):
        self.clock, self.end_ns, self.phase_id = clock, end_ns, phase_id
        self.global_check = global_check
        self.started_ns = clock.now_ns()
        self.rows = []
        self.persist = persist
        self.checkpoint_ordinal = 0
        self.persistence_uncertain = False

    def checkpoint(self):
        if self.persist is not None:
            self.checkpoint_ordinal += 1
            require(self.checkpoint_ordinal <= 16, "RA_G1_DIAGNOSTIC_TRACE_BOUND")
            try:
                self.persist(self.checkpoint_ordinal, self.snapshot())
            except BaseException:
                self.persistence_uncertain = True
                raise

    def check(self):
        self.global_check()
        if self.clock.now_ns() >= self.end_ns:
            raise PhaseDeadlineExpired("RA_G1_DIAGNOSTIC_PHASE_DEADLINE")

    def remaining(self):
        self.check()
        return min(5, (self.end_ns - self.clock.now_ns()) / 1e9)

    def operation(self, tag, action, *args, **kwargs):
        require(tag in self.TAGS and len(self.rows) < 8, "RA_G1_DIAGNOSTIC_TRACE_BOUND")
        self.check()
        row = dict(
            operation=tag,
            entered_ns=self.clock.now_ns(),
            completed_ns=None,
            returned=False,
            deadline_ns=self.end_ns,
        )
        self.rows.append(row)
        self.checkpoint()
        self.check()
        try:
            result = action(*args, **kwargs)
        except BaseException:
            row["completed_ns"] = self.clock.now_ns()
            try:
                self.checkpoint()
            except BaseException:
                self.persistence_uncertain = True
            # Preserve the initiating exception even if the deadline also crossed.
            raise
        row["completed_ns"] = self.clock.now_ns()
        self.checkpoint()
        self.check()
        row["returned"] = True
        return result

    def snapshot(self):
        return dict(
            phase_id=self.phase_id,
            started_ns=self.started_ns,
            deadline_ns=self.end_ns,
            checkpoint_ordinal=self.checkpoint_ordinal,
            persistence_uncertain=self.persistence_uncertain,
            operations=[dict(row) for row in self.rows],
        )


def safe_failure(error):
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import (
        classify,
    )

    family, code, number = classify(error)
    if (type(error) is RuntimeError and len(error.args) == 1
            and type(error.args[0]) is str and error.args[0] == "RA_G1_DIAGNOSTIC_PATH_SCOPE"):
        code = "RA_G1_DIAGNOSTIC_PATH_SCOPE"
    return {"family": family, "code": code, "errno": number}


def expected_stopped_rejection(action, check):
    """Only the completed-opener's exact disposition rejection is expected.

    Caller first freshly validates STOPPED original snapshot/ledger/raw evidence.
    Deadline, I/O, source mutation and uncertain-writer exceptions propagate.
    """
    from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

    check()
    try:
        action()
    except c.Stage12Error as error:
        check()
        if type(error) is not c.Stage12Error or error.args != (
            "S12_PUBLIC_OPERATIONS_INVALID",
        ):
            raise
        return
    check()
    require(False, "RA_G1_DIAGNOSTIC_NEGATIVE_ADOPTED")


def hash_value(value, size=64):
    return (
        type(value) is str
        and len(value) == size
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def input_scope(data):
    value = dict(data)
    value["selection"] = {
        key: cell
        for key, cell in data["selection"].items()
        if key != "authority_sha256"
    }
    return digest(value)


def validate_envelope(data, source_sha, *, for_execution, defer_response_payloads=False):
    """Pure bounded metadata shape; this never creates a usable assurance record."""
    require(type(data) is dict and set(data) == _TOP)
    require(data["version"] in (VERSION, BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS) and data["scope"] == SCOPE)
    require(
        not defer_response_payloads
        or (for_execution and data["version"] in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS))
    )
    require(hash_value(source_sha, 40) and data["source_sha"] == source_sha)
    selected = data["selection"]
    require(
        type(selected) is dict
        and set(selected) == {"status", "authority_sha256", "resource_review_sha256"}
    )
    require(selected["status"] in ("UNISSUED", "ISSUED"))
    require(
        hash_value(selected["authority_sha256"])
        and hash_value(selected["resource_review_sha256"])
    )
    if for_execution:
        require(selected["status"] == "ISSUED", "RA_G1_DIAGNOSTIC_SELECTION_UNISSUED")
    limits = data["limits"]
    require(type(limits) is dict and set(limits) == _LIMITS)
    require(all(type(v) is int and 0 < v < 2**64 for v in limits.values()))
    require(
        limits["seconds"] == 7200
        and limits["summary_reserve_bytes"] == 2**20
        and limits["maximum_creations"] == (204860 if data["version"] == REP512_VERSION else 184184)
        and limits["maximum_bytes"] == 72 * 2**30
        and limits["rss_bytes"] == 768 * 2**20
    )
    require(
        limits["maximum_input_bytes"] <= 64 * 2**20 and limits["maximum_bytes"] < 2**63
    )
    require(limits["rss_bytes"] <= 6 * 2**30)
    require(
        limits["maximum_bytes"]
        > limits["summary_reserve_bytes"] + limits["native_helper_bytes_reserve"]
    )
    config = data["configuration"]
    require(
        type(config) is dict
        and set(config) == _CONFIG
        and config.get("version") == CONFIG_VERSION
    )
    require(
        config.get("transport") == {"scope": SCOPE, "authority": "TEST_ONLY_NO_NETWORK"}
    )
    require(
        type(config.get("sources")) is dict
        and set(config["sources"])
        == {"owner", "operator", "policy_freeze", "selection", "transport"}
    )
    require(all(hash_value(value) for value in config["sources"].values()))
    require(type(config.get("campaigns")) is list and len(config["campaigns"]) == 4)
    require(
        type(config["command_paths"]) is dict
        and set(config["command_paths"])
        == {"source", "input", "output", "evidence_bundle"}
        and all(
            type(path) is str and Path(path).is_absolute()
            for path in config["command_paths"].values()
        )
    )
    require(type(data["phases"]) is list and len(data["phases"]) == 4)
    for item, phase, (label, duration, hold, count) in zip(
        config["campaigns"], data["phases"], phases_for(data["version"]), strict=True
    ):
        require(
            type(item) is dict and set(item) == {"label", "profile", "plan", "work"}
        )
        require(
            type(phase) is dict
            and set(phase) == {"label", "start", "epoch_id", "hold_regular_acks"}
        )
        require(
            item["label"] == phase["label"] == label
            and phase["hold_regular_acks"] == hold
        )
        require(hash_value(phase["epoch_id"]))
        profile, plan, start = item["profile"], item["plan"], phase["start"]
        require(
            profile.get("schema_version") == "stage12_transport_operations_ra_g1_v1"
        )
        require(
            plan.get("schema_version")
            == "stage12_public_characterization_plan_ra_g1_v1"
        )
        require(
            start.get("schema_version") == "stage12_public_operations_campaign_ra_g1_v1"
        )
        require(
            start["client_git_sha"] == source_sha
            and start["profile_sha256"] == digest(profile)
            and start["plan_sha256"] == digest(plan)
        )
        require(start["runtime_inventory_sha256"] == digest(data["runtime_inventory"]))
        require(
            plan["budgets"]["active_duration_ms"]
            == plan["blocks"][0]["budget"]["active_duration_ms"]
            == duration
        )
        if data["version"] == REP512_VERSION:
            observations = (duration + 49) // 50 + 2
            require(plan["sampling_budget"]["maximum_observations"] == observations
                and plan["sampling_budget"]["additional_event_tokens"] == 2 * observations + 4
                and plan["budgets"]["event_count"] == 19 * 5 * count + 40 + 2 * observations + 4,
                "RA_G1_DIAGNOSTIC_RESOURCE_FAMILY")
        require(type(item["work"]) is list and len(item["work"]) == count)
        require(profile["transport_profile_sha256"] == digest(config["transport"]))
        require(profile["resources"] == config["resources"])
    require(
        config["resources"]["task_logical_write_ceiling_bytes"]
        <= limits["maximum_bytes"]
    )
    require(type(data["responses"]) is list and len(data["responses"]) == 48)
    keys = set()
    for row in data["responses"]:
        require(
            type(row) is dict
            and set(row)
            == {"fixture_id", "size", "raw_utf8", "payload_sha256", "origin"}
        )
        require(
            hash_value(row["fixture_id"])
            and type(row["size"]) is int
            and row["size"] in (1, 40)
        )
        require(type(row["raw_utf8"]) is str and hash_value(row["payload_sha256"]))
        require(
            row["origin"] in ("RETAINED_PUBLIC_BODY", "MANUALLY_INVENTED_PUBLIC_BODY")
        )
        key = row["fixture_id"], row["size"]
        require(key not in keys)
        keys.add(key)
    if not defer_response_payloads:
        materialize_response_bodies(data)
    return data


def materialize_response_bodies(data, *, check=lambda: None):
    """Decode TEST_ONLY transport bodies only after acknowledged live monitoring.

    Offline envelope validation also uses these unchanged payload checks. The
    bounded canonical live input necessarily contains payload strings; that
    control read does not construct transport response bytes or iterate work.
    """
    bodies = {}
    for row in data["responses"]:
        check()
        payload = row["raw_utf8"].encode("utf8")
        require(0 < len(payload) <= 65536)
        require(hashlib.sha256(payload).hexdigest() == row["payload_sha256"])
        bodies[row["fixture_id"], row["size"]] = payload
    check()
    return bodies


def validate_resource_family(input_version, selected):
    require(
        input_version in (VERSION, BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS)
        and selected.get("scope") == SCOPE
        and selected.get("schema_version")
        == (
            REP512_SELECTION if input_version == REP512_VERSION else
            REP_ADMIN_SELECTION if input_version == REP_ADMIN_VERSION else BOOTSTRAP_SELECTION
            if input_version in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS)
            else "stage12_resource_selection_ra_g1_v1"
        ),
        "RA_G1_DIAGNOSTIC_RESOURCE_FAMILY",
    )


def start_phase_resource(
    execution, *, source_entry_ns, phase_id, clock_ns, input_version=VERSION, **arguments
):
    """Preserve phase origins while opting only REP's first START into the prefix."""
    validate_resource_family(input_version, arguments["selection"])
    bootstrap = {}
    if phase_id == 1 and input_version in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS):
        bootstrap["bootstrap_prefix"] = dict(
            role="PHASE_RUNNER",
            source_entry_ns=source_entry_ns,
            bootstrap_end_ns=clock_ns(),
        )
    return execution.start_session(
        phase_id=phase_id, clock_ns=clock_ns, **arguments, **bootstrap
    )


def prepare_first_phase(session, data, *, initialize_runtime, validation, check):
    """The real START and retained ACK original precede all runtime/work setup."""
    session.require_start_acknowledged()
    actual_runtime = initialize_runtime()
    bodies = materialize_response_bodies(data, check=check)
    control_raw = canonical(
        {
            "type": "FeatureCollection",
            "features": [],
            "geocoding": {"version": "TEST_ONLY"},
        }
    )
    adapter = validation.Validation(validation.CORPUS_VERSION)
    return actual_runtime, bodies, control_raw, adapter


def validate_workloads(data):
    """Exact public corpus, successor contracts and cumulative T3 reservation."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as a
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix

    campaign = data["configuration"]["campaigns"]
    indices = (0, 9, 10, 0)
    wanted = set()
    rows_bound = ordinals = events = selected_bytes = 0
    cuts = 9
    for index, (item, phase) in enumerate(zip(campaign, data["phases"], strict=True)):
        profile, plan = item["profile"], item["plan"]
        a.validate_plan(plan, profile)
        a.validate(phase["start"], a.START)
        a.verify_work_manifest(lambda: iter(item["work"]), plan)
        expected, controls = matrix.work_for(
            indices[index], profile["transport_profile_sha256"]
        )
        if index == 3:
            expected = expected[:3]
        require(item["work"] == expected and plan["control_recipes"] == controls)
        require(
            profile["states"][0]["connections"] == 2
            and profile["states"][0]["admitted_operations"] == 2
            and len(profile["states"]) == 1
        )
        require(profile["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY")
        require(plan["shutdown_reserve_ms"] == 80000)
        require(
            profile["policy_freeze_record_sha256"]
            == data["configuration"]["sources"]["policy_freeze"]
        )
        start = phase["start"]
        require(
            start["sampling_policy_sha256"] == a.POLICY_SHA
            and start["rule_bundle_sha256"] == a.RULE_BUNDLE
        )
        require(
            start["policy_freeze_record_sha256"]
            == profile["policy_freeze_record_sha256"]
        )
        if index < 2:
            wanted.update(
                (work["fixture_id"], work["result_limit"]) for work in expected
            )
        maximum = plan["sampling_budget"]["maximum_observations"]
        attempts = (
            plan["budgets"]["data_attempts"] + plan["budgets"]["control_http_attempts"]
        )
        rows_bound += maximum + attempts + 16
        ordinals += attempts
        events += plan["budgets"]["event_count"]
        selected_bytes += plan["budgets"]["storage_bytes"]
        cuts += (plan["budgets"]["active_duration_ms"] + 4999) // 5000
    require(wanted == {(row["fixture_id"], row["size"]) for row in data["responses"]})
    require(rows_bound // 56 + cuts + 1 <= 1500, "RA_G1_DIAGNOSTIC_TIMING_RESERVATION")
    require(
        events
        + 24 * ordinals
        + 128 * 4
        + 128
        + 1501
        + data["limits"]["native_helper_creation_reserve"]
        <= data["limits"]["maximum_creations"],
        "RA_G1_DIAGNOSTIC_CREATION_RESERVATION",
    )
    require(
        selected_bytes
        # Existing os.write instrumentation conservatively also charges the
        # independent timing writer and instrumented helper writes.
        + 2 * 1500 * 32768
        + 2**20
        + 2 * data["limits"]["native_helper_bytes_reserve"]
        <= data["limits"]["maximum_bytes"],
        "RA_G1_DIAGNOSTIC_BYTE_RESERVATION",
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_response as validation,
    )

    require(
        data["configuration"]["public_validation_sha256"]
        == digest(validation.descriptor(validation.CORPUS_VERSION))
    )
    require(
        data["limits"]["native_helper_bytes_reserve"] >= 128 * 2**20
        and data["limits"]["native_helper_creation_reserve"] >= 64
    )


def _proc_identity(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


class SelfProcIdentity(
    namedtuple(
        "_SelfProcIdentity",
        "pid root_identity process_identity mount_namespace_identity",
    )
):
    __slots__ = ()

    def current(self):
        if self.root_identity is None or os.getpid() != self.pid:
            return False
        try:
            return (
                os.path.realpath("/proc/self") == f"/proc/{self.pid}"
                and _proc_identity(Path("/proc")) == self.root_identity
                and _proc_identity(Path(f"/proc/{self.pid}")) == self.process_identity
                and _proc_identity(Path("/proc/self/ns/mnt"))
                == self.mount_namespace_identity
            )
        except OSError:
            return False

    def permits(self, original, resolved):
        if not self.current():
            return False
        return any(
            str(original) in (f"/proc/self/{name}", f"/proc/{self.pid}/{name}")
            and str(resolved) == f"/proc/{self.pid}/{name}"
            for name in ("status", "stat", "cgroup", "mountinfo")
        )


def capture_self_proc_identity():
    """Current process/mount binding, never a general /proc permission."""
    pid = os.getpid()
    if sys.platform != "linux":
        return SelfProcIdentity(pid, None, None, None)
    require(os.path.realpath("/proc/self") == f"/proc/{pid}")
    result = SelfProcIdentity(
        pid,
        _proc_identity(Path("/proc")),
        _proc_identity(Path(f"/proc/{pid}")),
        _proc_identity(Path("/proc/self/ns/mnt")),
    )
    require(result.current(), "RA_G1_DIAGNOSTIC_PROCESS_CHANGED")
    return result


def capture_output_parent(output):
    parent = Path(output).parent
    require(parent.resolve(strict=True) == parent, "RA_G1_DIAGNOSTIC_PARENT_CHANGED")
    info = parent.stat(follow_symlinks=False)
    require(
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid(),
        "RA_G1_DIAGNOSTIC_PARENT_CHANGED",
    )
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def parent_handle_allowed(path, flags, output, binding):
    allowed_flags = (
        os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        return (
            Path(path) == Path(output).parent
            and flags & os.O_DIRECTORY != 0
            and flags & ~allowed_flags == 0
            and capture_output_parent(output) == binding
        )
    except (OSError, RuntimeError):
        return False


def public_input_layout(input_path, bundle, controlled):
    """One exact successor allocation layout; no historical binding alias."""
    allocation = input_path.parent
    if not (
        allocation.parent == controlled
        and allocation.name.startswith("ra_g1_")
        and input_path.name == "input.json"
        and bundle == allocation / "binding"
    ):
        return False
    try:
        for path in (allocation, bundle):
            info = path.stat(follow_symlinks=False)
            if not (
                stat.S_ISDIR(info.st_mode)
                and info.st_uid == os.geteuid()
                and stat.S_IMODE(info.st_mode) == 0o700
                and not path.is_symlink()
            ):
                return False
        return True
    except OSError:
        return False


def _source_read_digest(entries, metadata=None):
    """Stream the existing canonical grammar with one bounded hash workspace."""
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_bounded import Canonical
    from safe_geocoding_pipeline.preprocessing.stages.s12_wf_ap2_scratch import lease

    result = hashlib.sha256()
    encoder = json.JSONEncoder(ensure_ascii=True, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)

    def emit(value, maximum):
        count = Canonical(maximum, count_only=True)
        count.value(value)
        iterator = encoder.iterencode(value)
        chunk = raw = None
        try:
            for chunk in iterator:
                # Validated row paths have <=512 UTF8 bytes; other scalars are
                # fixed metadata or 64-character hashes. ASCII escapes fit 2KiB.
                require(len(chunk) <= 2048, "RA_G1_SOURCE_INVENTORY")
                raw = chunk.encode("ascii")
                result.update(raw)
                raw = chunk = None
        finally:
            raw = chunk = None
            iterator.close()

    def source_array():
        result.update(b"[")
        for ordinal, (name, size, identity) in enumerate(entries):
            if ordinal:
                result.update(b",")
            emit(dict(path=name, bytes=size, sha256=identity), 2048)
        result.update(b"]")

    with lease("HASH"):
        if metadata is None:
            source_array()
        else:
            result.update(b"{")
            for ordinal, key in enumerate(sorted((*metadata, "source_files"))):
                if ordinal:
                    result.update(b",")
                emit(key, 128)
                result.update(b":")
                if key == "source_files":
                    source_array()
                else:
                    emit(metadata[key], 65536)
            result.update(b"}")
        result.update(b"\n")
    return result.hexdigest()


class _ReviewedSourceReads(tuple):
    """Immutable selected names only; every lookup retains fresh path checks."""

    __slots__ = ()

    def __new__(cls, source, rows, expected_inventory_sha256, *, metadata=None, review_sha256=None):
        prefix = str(source)
        require(source.is_absolute() and len(prefix) <= 512
                and type(rows) is list and 1 <= len(rows) <= 2048,
                "RA_G1_SOURCE_INVENTORY")
        previous, total, entries = None, 0, []
        for row in rows:
            require(type(row) is dict and set(row) == {"path", "bytes", "sha256"},
                    "RA_G1_SOURCE_INVENTORY")
            name, size, identity = row["path"], row["bytes"], row["sha256"]
            require(type(name) is str and len(name) <= 512
                    and len(name.encode("utf8")) <= 512,
                    "RA_G1_SOURCE_INVENTORY")
            relative = Path(name)
            require(not relative.is_absolute() and ".." not in relative.parts
                    and str(relative) == name
                    and not any(part in {".ssh", ".config", "credentials", ".git"}
                                or part.startswith(".env") for part in relative.parts)
                    and not any(ord(character) < 32 or ord(character) == 127 for character in name)
                    and (previous is None or previous < name)
                    and type(size) is int and 0 <= size <= 64 * 2**20
                    and type(identity) is str and len(identity) == 64
                    and all(character in "0123456789abcdef" for character in identity),
                    "RA_G1_SOURCE_INVENTORY")
            entries.append((name, size, identity))
            previous, total = name, total + size
        require(total <= 64 * 2**20
                and expected_inventory_sha256 == _source_read_digest(entries),
                "RA_G1_SOURCE_INVENTORY")
        if metadata is not None:
            require(review_sha256 == _source_read_digest(entries, metadata), "RA_G1_SOURCE_INVENTORY")
        return tuple.__new__(cls, (prefix + "/", tuple(row[0] for row in entries), threading.Lock()))

    def permits(self, original, resolved):
        if original != resolved:
            return False
        text = str(original)
        prefix, names, query_lock = self
        if not text.startswith(prefix) or len(text) > len(prefix) + 512:
            return False
        # Serialize only the <=512-character query, never filesystem I/O.
        with query_lock:
            relative = text[len(prefix):]
            try:
                position = bisect_left(names, relative)
                matched = position < len(names) and names[position] == relative
            finally:
                del relative
        if not matched:
            return False
        try:
            return stat.S_ISREG(original.lstat().st_mode)
        except OSError:
            return False


def open_allowed(path, *, write, source, output, input_path, evidence, self_proc=None, source_reads=None):
    """Pure audit policy. Kernel/library allowances contain no protected inputs."""
    original = Path(os.fsdecode(path))
    if not original.is_absolute() or ".." in original.parts:
        return False
    path = Path(os.path.realpath(original))
    if any(
        part in {".ssh", ".config", "credentials", ".git"} or part.startswith(".env")
        for part in (*original.parts, *path.parts)
    ):
        return False
    if original.is_relative_to("/proc") or path.is_relative_to("/proc"):
        if write:
            return False
        if str(original) == str(path) and str(path) in (
            "/proc/sys/kernel/random/boot_id",
            "/proc/meminfo",
        ):
            return True
        return (self_proc or capture_self_proc_identity()).permits(original, path)
    output = Path(output)
    if write:
        return (
            path == output
            or path.is_relative_to(output)
            or (
                original == path
                and path
                in {
                    output.parent / role / "supervisor_terminal.record"
                    for role in ("review_resources", "binder_resources")
                }
            )
        )
    safe = (
        source / "src",
        source / "scripts",
        source / "docs/scientific_assets",
        source / "tests",
        source / "cluster",
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        evidence,
        output.parent / "collector_resources",
        output.parent / "review_resources",
        output.parent / "binder_resources",
    )
    if (
        path == input_path
        or (
            original == path
            and path
            in {
                output.parent / name
                for name in (
                    "context.record",
                    "collector.handoff.record",
                    "binder.handoff.record",
                    "collector.wait.record",
                    "binder.wait.record",
                )
            }
        )
        or path == output
        or path.is_relative_to(output)
        or any(path == root or path.is_relative_to(root) for root in safe)
    ):
        return True
    if source_reads is not None and source_reads.permits(original, path):
        return True
    kernel_files = {
        "/dev/null",
        "/dev/urandom",
    }
    return str(path) in kernel_files or path.is_relative_to("/sys/fs/cgroup")


def build_live_authority(data, bundle, review, review_hash, source, source_sha, clock):
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import Authority

    return Authority(
        data["configuration"],
        bundle,
        review,
        review_hash,
        source,
        source_sha,
        clock,
        diagnostic=True,
        defer_source_fence=True,
        deadline_check=lambda: require(
            time.monotonic_ns() < _ENTRY_MONO_NS + 7200 * 10**9,
            "RA_G1_DIAGNOSTIC_DEADLINE",
        ),
    )


def install_denials(source, output, input_path, evidence):
    """Reuse the existing process network guard and Python audit/provider denial.

    The returned native guard label is earned only by the actual guard call.
    Python path/provider denial is not described as native filesystem isolation.
    """
    spec = importlib.util.spec_from_file_location(
        "ap2_existing_guard", source / "scripts/stage12_scale120_diagnostic.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    network = guard.deny_linux_network()

    self_proc = capture_self_proc_identity()
    # Source-owned direct parent only; no arbitrary PID or fd traversal grant.
    parent_pid = os.getppid()
    parent_identity = (
        _proc_identity(Path(f"/proc/{parent_pid}")) if sys.platform == "linux" else None
    )
    original_permits = SelfProcIdentity.permits

    def permits_roster(self, original, resolved):
        if original_permits(self, original, resolved):
            return True
        return bool(
            self.current()
            and parent_identity is not None
            and _proc_identity(Path(f"/proc/{parent_pid}")) == parent_identity
            and str(original) == str(resolved)
            and str(resolved)
            in {
                f"/proc/{parent_pid}/status",
                f"/proc/{parent_pid}/stat",
                f"/proc/{parent_pid}/cgroup",
            }
        )

    SelfProcIdentity.permits = permits_roster
    parent_binding = capture_output_parent(output)
    original_open = os.open
    access_context = threading.local()

    def fd_path(fd):
        if sys.platform == "linux":
            require(self_proc.current(), "RA_G1_DIAGNOSTIC_PROCESS_CHANGED")
            return os.readlink(f"/proc/{self_proc.pid}/fd/{fd}")
        import fcntl

        return os.fsdecode(
            fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0]
        )

    def access_path(path, directory_fd=None):
        if isinstance(path, int):
            return fd_path(path)
        value = os.fsdecode(path)
        if not os.path.isabs(value):
            base = (
                fd_path(directory_fd) if directory_fd not in (None, -1) else os.getcwd()
            )
            value = os.path.join(base, value)
        return value

    def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
        previous = getattr(access_context, "path", None)
        access_context.path = access_path(path, dir_fd)
        try:
            return original_open(path, flags, mode, dir_fd=dir_fd)
        finally:
            access_context.path = previous

    os.open = tracked_open

    def denied(*args, **kwargs):
        raise PermissionError("RA_G1_DIAGNOSTIC_ACCESS_DENIED")

    creations = [0]
    selected_limit = [None]
    source_reads = [None]
    lock = threading.Lock()

    def bind_reviewed_source_reads(authority, bound):
        from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import Authority, ROLES

        require(type(authority) is Authority and authority.repository == source
                and authority.git_sha == bound["source_git_sha"]
                and authority.diagnostic_scope == SCOPE and authority.service_authority is False
                and authority.configuration_scope_sha256 == bound["configuration_scope_sha256"],
                "RA_G1_SOURCE_INVENTORY")
        review = authority.review
        metadata = {key: value for key, value in review.items() if key != "source_files"}
        require(set(metadata) == {"version", "scope", "disposition", "configuration_sha256", "report_sha256", "resource_evidence"}
                and metadata["version"] == REVIEW_VERSION and metadata["scope"] == SCOPE
                and metadata["disposition"] == "PASS", "RA_G1_SOURCE_INVENTORY")
        require(all(type(metadata[key]) is str and len(metadata[key]) == 64
                    and all(char in "0123456789abcdef" for char in metadata[key])
                    for key in ("configuration_sha256", "report_sha256")), "RA_G1_SOURCE_INVENTORY")
        require(type(metadata["resource_evidence"]) is dict
                and set(metadata["resource_evidence"]) == set(ROLES), "RA_G1_SOURCE_INVENTORY")
        frozen_evidence = {}
        for key, values in metadata["resource_evidence"].items():
            require(type(key) is str and len(key) <= 64 and type(values) is list
                    and 1 <= len(values) <= 64
                    and all(type(value) is str and len(value) == 64
                            and all(char in "0123456789abcdef" for char in value) for value in values),
                    "RA_G1_SOURCE_INVENTORY")
            frozen_evidence[key] = tuple(values)
        metadata["resource_evidence"] = frozen_evidence
        selected = _ReviewedSourceReads(source, review["source_files"], bound["source_inventory_sha256"],
                                        metadata=metadata, review_sha256=authority.review_hash)
        with lock:
            require(source_reads[0] is None, "RA_G1_SOURCE_INVENTORY")
            source_reads[0] = selected

    def audit(event, values):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes, int)):
            flags = values[2] if type(values[2]) is int else 0
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            resolved = getattr(access_context, "path", None) or access_path(values[0])
            parent_handle = parent_handle_allowed(
                resolved, flags, output, parent_binding
            )
            if not parent_handle and not open_allowed(
                resolved,
                write=write,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
                self_proc=self_proc,
                **({"source_reads": source_reads[0]}
                   if not write and source_reads[0] is not None else {}),
            ):
                denied()
            if flags & os.O_CREAT and not isinstance(values[0], int):
                charge(1)
        elif event == "os.mkdir":
            if not open_allowed(
                access_path(values[0], values[2]),
                write=True,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
                self_proc=self_proc,
            ):
                denied()
            charge(1)
        elif (
            event in ("os.listdir", "os.scandir")
            and values
            and isinstance(values[0], (str, bytes, int))
        ):
            if not open_allowed(
                access_path(values[0]),
                write=False,
                source=source,
                output=output,
                input_path=input_path,
                evidence=evidence,
                self_proc=self_proc,
            ):
                denied()
        elif event in ("os.remove", "os.rmdir", "os.rename", "os.link", "os.symlink"):
            if event == "os.symlink":
                denied()  # No symlink artifact is admissible in this path.
            targets = (
                ((values[0], values[2]), (values[1], values[3]))
                if event in ("os.rename", "os.link")
                else ((values[0], values[1]),)
            )
            for path, directory in targets:
                if not open_allowed(
                    access_path(path, directory),
                    write=True,
                    source=source,
                    output=output,
                    input_path=input_path,
                    evidence=evidence,
                    self_proc=self_proc,
                ):
                    denied()
            if event == "os.link":
                charge(1)

    def charge(amount):
        with lock:
            creations[0] += amount
            require(
                selected_limit[0] is not None and creations[0] <= selected_limit[0],
                "RA_G1_DIAGNOSTIC_CREATION_LIMIT",
            )

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "call", "check_output", "check_call"):
        setattr(subprocess, name, denied)
    sys.addaudithook(audit)
    guard.bind_reviewed_source_reads = bind_reviewed_source_reads
    return guard, network, creations, selected_limit, charge, denied


def validate_grants(data, bundle):
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    for role, identity in data["configuration"]["sources"].items():
        raw = io.read(bundle / (role + ".record"), limit=32768)
        require(hashlib.sha256(raw).hexdigest() == identity)
        require(
            io.metadata(raw)
            == {
                "version": "stage12_diagnostic_test_authority_v1",
                "scope": SCOPE,
                "role": role,
                "authority": "TEST_ONLY_NO_SERVICE",
            },
            "RA_G1_DIAGNOSTIC_AUTHORITY_SCOPE",
        )
    selected = io.metadata(io.read(bundle / "diagnostic_selection.record", limit=32768))
    require(digest(selected) == data["selection"]["authority_sha256"])
    require(
        selected
        == {
            "version": "stage12_ra_g1_diagnostic_selection_v1",
            "scope": SCOPE,
            "status": "ISSUED",
            "input_scope_sha256": input_scope(data),
            "source_sha": data["source_sha"],
            "resource_review_sha256": data["selection"]["resource_review_sha256"],
            "service_authority": False,
        },
        "RA_G1_DIAGNOSTIC_SELECTION_UNISSUED",
    )
    review = io.metadata(io.read(bundle / "diagnostic_resources.record", limit=32768))
    require(digest(review) == data["selection"]["resource_review_sha256"])
    require(
        review
        == {
            "version": "stage12_ra_g1_diagnostic_resources_v1",
            "scope": SCOPE,
            "source_sha": data["source_sha"],
            "limits": data["limits"],
            "resources": data["configuration"]["resources"],
            "status": "ISSUED",
            "method": "LOGICAL_LIMITS_AND_SCOPED_MONITORING",
            "capacity_entitlement": "NOT_ASSERTED",
            "native_physical_maximum": "NOT_PROVEN",
        },
        "RA_G1_DIAGNOSTIC_RESOURCE_REVIEW_REQUIRED",
    )


@contextmanager
def instrumentation(check):
    """Existing sole-writer hold hook; it never blocks the sampler/writer thread."""
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_scheduler as scheduler,
    )

    state = dict(current=None, regular=0, role=None, held=False, target=0)
    original_init, original_event, original_call = (
        scheduler.Coordinator.__init__,
        journal.Journal.event,
        journal.Writer.call,
    )

    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        state["current"] = self

    def event(self, kind, body, **kwargs):
        result = original_event(self, kind, body, **kwargs)
        if kind == "RESOURCE_SAMPLE":
            state["role"] = body["observation"]["role"]
        if kind == "SAMPLE_ACK" and state["role"] == "REGULAR":
            state["regular"] += 1
        return result

    def call(self, action, *args, **kwargs):
        current = state["current"]
        if (
            current is not None
            and threading.current_thread() is not self.thread
            and not state["held"]
            and not current.slots
            and getattr(action, "__self__", None) is current.journal
            and getattr(action, "__name__", None) == "verify_storage"
        ):
            def held_check():
                check()
                resource = getattr(current.authority, "resource_monitor", None)
                if getattr(resource, "start_to_start", False) is True:
                    failure = resource.failure
                    require(failure is None, failure or "RA_G1_MONITOR_INCOMPLETE")

            while state["regular"] < state["target"]:
                held_check()
                require(
                    not self.failed.is_set() and current.stop_reason is None,
                    "RA_G1_DIAGNOSTIC_HOLD_FAILED",
                )
                time.sleep(0.005)
            while True:
                with current.ap_sampler.lock:
                    witnessed = current.ap_sampler.witnessed
                if witnessed >= state["target"]:
                    break
                held_check()
                require(
                    not self.failed.is_set() and current.stop_reason is None,
                    "RA_G1_DIAGNOSTIC_HOLD_FAILED",
                )
                time.sleep(0.005)
            state["held"] = True
        return original_call(self, action, *args, **kwargs)

    scheduler.Coordinator.__init__, journal.Journal.event, journal.Writer.call = (
        initialize,
        event,
        call,
    )
    try:
        yield state
    finally:
        scheduler.Coordinator.__init__, journal.Journal.event, journal.Writer.call = (
            original_init,
            original_event,
            original_call,
        )


def execute(args, *, started_ns, cpu_started_ns):
    """Exact denied RA-G1 representative data path, not a service adapter."""
    source = args.source.resolve(strict=True)
    sys.path.insert(0, str(source / "src"))
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("WF-AP2 representative denied diagnostic")
    os.umask(0o077)
    require(
        args.evidence_bundle is not None and hash_value(args.evidence_review_sha256),
        "RA_G1_DIAGNOSTIC_LIVE_PROOF_REQUIRED",
    )
    bundle = args.evidence_bundle.resolve(strict=True)
    output, input_path = args.output.absolute(), args.input.resolve(strict=True)
    project = Path("/panfs/vdura1/footprint/donyadidegan/safe_geocoding_pipeline")
    controlled = project / "derived/controlled/stage12/client_diagnostics"
    require(
        source.parent == project / "integration_stage12"
        and output.parent.parent == controlled
        and output.parent.name.startswith("ra_g1_")
        and input_path.parent == output.parent
        and public_input_layout(input_path, bundle, controlled),
        "RA_G1_DIAGNOSTIC_PATH_SCOPE",
    )
    require(
        not output.exists()
        and Path(__file__).resolve() == source / "scripts/stage12_ra_g1_diagnostic.py"
    )
    guard, network_guard, creations, creation_limit, charge_entries, denied = (
        install_denials(source, output, input_path, bundle)
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport

    transport.Secret.runtime = transport.Secret.private_file = denied
    # Provider/path/network denial is active BEFORE opening any input payload.
    with input_path.open("rb") as stream:
        raw = stream.read(4 * 2**20 + 1)
    require(
        len(raw) <= 4 * 2**20 and hashlib.sha256(raw).hexdigest() == args.input_sha256
    )
    data = json.loads(raw)
    require(canonical(data) == raw)
    require(data.get("version") in (SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS), "RA_G1_DIAGNOSTIC_RESOURCE_FAMILY")
    validate_envelope(
        data,
        args.source_sha,
        for_execution=True,
        defer_response_payloads=data.get("version") in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS),
    )
    require(
        data["configuration"]["command_paths"]
        == {
            "source": str(source),
            "input": str(input_path),
            "output": str(output),
            "evidence_bundle": str(bundle),
        },
        "RA_G1_DIAGNOSTIC_PATH_SCOPE",
    )
    limits = data["limits"]
    require(len(raw) <= limits["maximum_input_bytes"])
    creation_limit[0] = limits["maximum_creations"]
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_assurance as assurance,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as ap
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_response as validation,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_sampling as sampling,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operational_audit as oa,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import (
        Failures, FOREGROUND_MODULES, prepare_first_failure_descriptor,
    )

    transport.Secret.runtime = transport.Secret.private_file = denied
    config, clock = data["configuration"], runtime.Clock()
    require(
        config["resource_execution"]["supervisor_context_path"]
        == str(output.parent / "context.record"),
        "RA_G1_SUPERVISOR_CONTEXT",
    )
    review_raw = storage.read(
        bundle / "integration_review.binding.json", limit=4 * 2**20
    )
    require(hashlib.sha256(review_raw).hexdigest() == args.evidence_review_sha256)
    original = build_live_authority(
        data,
        bundle,
        storage.metadata(review_raw),
        args.evidence_review_sha256,
        source,
        args.source_sha,
        clock,
    )
    authority = original
    actual_runtime = data["runtime_inventory"]
    record = original.sampling_bound(
        config["campaigns"][0]["profile"], data["phases"][0]["start"]
    )
    selected = original.resource_selection(record)
    validate_resource_family(data["version"], selected)
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_execution as execution,
    )

    allocation = importlib.util.spec_from_file_location(
        "ra_g1_denied_allocation", source / "scripts/stage12_ra_g1_allocation.py"
    )
    allocation_module = importlib.util.module_from_spec(allocation)
    allocation.loader.exec_module(allocation_module)
    context = execution.read_supervisor_context(
        config["resource_execution"],
        check=original._deadline_check,
        read_charge=original.charge_original,
    )
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (limits["maximum_bytes"], limits["maximum_bytes"])
    )
    budget = guard.ArtifactBudget(
        limits["maximum_bytes"] - limits["summary_reserve_bytes"]
    )
    handoff = allocation_module.load_verified_handoff(
        context,
        selected,
        check=original._deadline_check,
        read_charge=original.charge_original,
        deadline_ns=started_ns + limits["seconds"] * 10**9,
        write_record=lambda path, value: storage.write(path, canonical(value)),
        counter_digest=lambda: ap.digest(original.counters()),
    )
    original.add_source_counter_prefix(handoff["source_counter_prefix"])
    budget.charge(handoff["initial_usage"]["bytes"])
    guard.install_artifact_accounting(storage, journal, budget)
    budget.charge(limits["native_helper_bytes_reserve"])
    charge_entries(limits["native_helper_creation_reserve"])
    storage.reserve(output)
    deadline = started_ns + limits["seconds"] * 10**9

    def check():
        require(clock.now_ns() < deadline, "RA_G1_DIAGNOSTIC_DEADLINE")
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        require(
            rss * (1 if sys.platform == "darwin" else 1024) <= limits["rss_bytes"],
            "RA_G1_DIAGNOSTIC_RSS_LIMIT",
        )
        require(not budget.snapshot()["exceeded"])

    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
        ApplicationControls,
    )

    original.allocation_controls = ApplicationControls(
        selected, check=check, initial_usage=handoff["initial_usage"]
    )
    original.allocation_controls.reserve_components(
        2 * 1500 * 32768 + limits["native_helper_bytes_reserve"],
        1501 + limits["native_helper_creation_reserve"],
    )
    global ACTIVE_DIAGNOSTIC_TRACE, ACTIVE_DIAGNOSTIC_CHECK
    runtime_trace = allocation_module.StartupTrace(started_ns, clock_ns=clock.now_ns)
    runtime_trace.enable_monitor_diagnostics()
    runtime_trace.set_controller_command("phase_runner")
    runtime_trace.first_start("PHASE_RUNNER")
    runtime_trace.reserve_phase_stdout(original.allocation_controls)
    ACTIVE_DIAGNOSTIC_TRACE, ACTIVE_DIAGNOSTIC_CHECK = runtime_trace, check
    observer = timing.SamplingTiming(
        output / "public_path_timing",
        phase_count=4,
        timing_schema=cp.RA_SCHEMA,
        timing_policy_version=ap.POLICY_VERSION,
        timing_binding=dict(
            policy_sha256=ap.POLICY_SHA,
            source_sha256=digest(data["source_sha"]),
            task_sha256=args.input_sha256,
        ),
        phase_windows=[
            dict(phase_id=i, selected_phase_ms=entry[1])
            for i, entry in enumerate(phases_for(data["version"]), 1)
        ],
        cumulative_deadline_ns=deadline,
        clock_ns=clock.now_ns,
        budget_charge=budget.charge,
    )
    resource_observation = {
        "method": assurance.METHOD,
        "native_maximum": "NOT_PROVEN",
        "physical_capacity": "NOT_RESERVED_OR_PROVEN",
    }
    bodies, control_raw, adapter = None, None, None
    attempts, phases, failure = 0, [], None
    boundaries, first_failure, cleanup_failure = [], None, None
    observer_stage_enabled = getattr(args, "observer_stages", False) is True
    # Only already-loaded, exactly selected modules are eligible. Pinning uses
    # the same bounded original source guards; denial remains active throughout.
    foreground_specs = []
    for module_id, relative in FOREGROUND_MODULES:
        name = (__name__ if module_id == "DIAGNOSTIC" else
                relative.removeprefix("src/").removesuffix(".py").replace("/", "."))
        module = sys.modules.get(name)
        if type(module) is type(sys):
            foreground_specs.append((module_id, module))
    foreground_descriptor = prepare_first_failure_descriptor(
        foreground_specs, original.review["source_files"], source_root=source,
        verify_source=original.verify_diagnostic_source,
    )
    capture_failures = Failures(
        clock, closure=True, observer=observer_stage_enabled,
        first_failure_descriptor=foreground_descriptor, sampling=True,
    )

    def closure_mark(stage, *, completed=False, deadline=None, deadline_ns=None, guard=None):
        try:
            capture_failures.closure_boundary(
                stage, completed=completed, deadline=deadline, deadline_ns=deadline_ns,
                guard=guard or ("DIAGNOSTIC_PHASE" if deadline is not None else None),
            )
        except BaseException:
            try:
                capture_failures.closure_fault()
            except BaseException:
                pass

    cleanup_failure_count = 0
    negative_ready = threading.Event()
    attempts_lock = threading.Lock()
    negative_starts = 0
    resource_sessions = []
    active_resource = None

    def dispatch(work, target, hooks):
        nonlocal attempts, negative_starts
        check()
        with attempts_lock:
            attempts += 1
            require(attempts <= 107, "RA_G1_DIAGNOSTIC_ATTEMPT_LIMIT")
            if current_label == "malformed":
                negative_starts += 1
                if negative_starts >= 2:
                    negative_ready.set()
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, check)
        if current_label == "malformed":
            while not negative_ready.wait(0.005):
                check()
            payload = b"{broken"
        else:
            time.sleep(0.005)
            payload = (
                control_raw
                if work["kind"] == "SERVICE_CONTROL"
                else bodies[work["fixture_id"], work["result_limit"]]
            )
        result = transport.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "identity",
            None,
            payload,
            len(payload),
            5,
        )
        hooks.completed(result)
        return result

    def initialize_current_runtime():
        runtime.verify_successor_assets(source, contract=ap,
            rep_admin_successor=data["version"] in REP_ADMIN_VERSIONS,
            first64_512_successor=data["version"] == REP512_VERSION)
        require(
            (source / "docs/scientific_assets" / (data["version"] + ".json")).read_bytes()
            == canonical(descriptor(data["version"])),
            "RA_G1_DIAGNOSTIC_DESCRIPTOR_CHANGED",
        )
        validate_grants(data, bundle)
        for item, phase in zip(config["campaigns"], data["phases"], strict=True):
            original.bind(item, item["plan"], phase["start"])
            record = authority.sampling_bound(item["profile"], phase["start"])
            assurance.verify_runtime(
                record,
                authority,
                dict(profile=item["profile"], plan=item["plan"], start=phase["start"]),
            )
        # Only genuine current proof permits public corpus/workload preparation.
        validate_workloads(data)
        original.charge_runtime_inventory_check(original.runtime_inventory_budget())
        actual_runtime = runtime.runtime_inventory(
            config["public_validation_sha256"],
            successor=True,
            resource_assurance="RA-G1-r1",
            environment_observation_sha256=record[
                "initial_environment_observation_sha256"
            ],
            backend_reader=assurance.bounded_backend_reader(original.charge_original),
            check=original._deadline_check,
        )
        require(
            actual_runtime == data["runtime_inventory"],
            "RA_G1_DIAGNOSTIC_RUNTIME_CHANGED",
        )
        return actual_runtime

    try:
        with instrumentation(check) as state:
            for phase_id, (item, phase) in enumerate(
                zip(config["campaigns"], data["phases"], strict=True), 1
            ):
                check()
                current_label = item["label"]
                state.update(
                    current=None,
                    regular=0,
                    role=None,
                    held=False,
                    target=phase["hold_regular_acks"],
                )
                profile, plan, start = item["profile"], item["plan"], phase["start"]
                original.bind(item, plan, start)
                phase_start_ns = started_ns if phase_id == 1 else clock.now_ns()
                phase_deadline = min(
                    deadline,
                    phase_start_ns + plan["budgets"]["active_duration_ms"] * 10**6,
                )

                def persist_phase(ordinal, value):
                    raw = canonical(value)
                    require(len(raw) <= 16384, "RA_G1_DIAGNOSTIC_TRACE_BOUND")
                    path = output / f"phase{phase_id:02d}_timing_{ordinal:02d}.json"
                    storage.write(path, raw)
                    require(storage.read(path, limit=16384) == raw)

                boundary = PhaseBoundary(
                    clock, phase_deadline, phase_id, check, persist_phase
                )
                boundaries.append(boundary)
                original._deadline_check = boundary.check
                from safe_geocoding_pipeline.preprocessing.stages import (
                    s12_ra_g1_execution as execution,
                )
                from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
                    ApplicationControls,
                )

                bound = original.sampling_bound(profile, start)
                selected = original.resource_selection(bound)
                if original.allocation_controls is None:
                    original.allocation_controls = ApplicationControls(
                        selected, check=check
                    )
                    original.allocation_controls.reserve_components(
                        2 * 1500 * 32768 + limits["native_helper_bytes_reserve"],
                        1501 + limits["native_helper_creation_reserve"],
                    )
                active_resource = start_phase_resource(
                    execution,
                    source_entry_ns=started_ns,
                    input_version=data["version"],
                    authority=original,
                    config=config,
                    binding=bound,
                    selection=selected,
                    evidence_root=output / (current_label + "_resources"),
                    deadline_ns=phase_deadline,
                    phase_id=phase_id,
                    check=boundary.check,
                    counters=original.counters,
                    charge=original.allocation_controls.monitor_charge,
                    read_charge=original.charge_original,
                    clock_ns=clock.now_ns,
                    native_roots=(output,),
                    scope_start_ns=phase_start_ns,
                    startup_trace=runtime_trace,
                    **({"observer_stages": capture_failures} if observer_stage_enabled else {}),
                )
                runtime_trace.bind_monitor(active_resource.monitor)
                if phase_id == 1:

                    def initialize_first_runtime():
                        handoff["verify_before_data"]()
                        guard.bind_reviewed_source_reads(original, bound)
                        original.source_fence()
                        current = initialize_current_runtime()
                        original.bind(item, plan, start)
                        return current

                    actual_runtime, bodies, control_raw, adapter = prepare_first_phase(
                        active_resource,
                        data,
                        initialize_runtime=initialize_first_runtime,
                        validation=validation,
                        check=boundary.check,
                    )
                else:
                    active_resource.require_start_acknowledged()
                with (
                    storage.allocation_controls(original.allocation_controls),
                    storage.cooperative_io(boundary.check),
                ):
                    boundary.operation(
                        "PHASE_OPEN",
                        observer.phase_open,
                        phase_id,
                        phase_deadline_ns=phase_deadline,
                        timeout_seconds=boundary.remaining(),
                    )
                    root = output / current_label
                    report = boundary.operation(
                        "CAPTURE",
                        cli.run_operations_block,
                        profile,
                        plan,
                        start,
                        work_factory=lambda: iter(item["work"]),
                        output=root,
                        block_id=1,
                        authority=authority,
                        clock=clock,
                        dispatch=dispatch,
                        runtime_inventory=actual_runtime,
                        runtime_key=b"DIAGNOSTIC_TEST_ONLY",
                        control_adapters=matrix.adapters(plan),
                        monitor=None,
                        free_bytes=lambda: runtime.filesystem_free_bytes(output),
                        segment_authority=config["sources"]["owner"],
                        writer_exclusion_evidence=config["sources"]["owner"],
                        epoch=phase["epoch_id"],
                        writer_release_evidence=config["sources"]["owner"],
                        public_validation=adapter,
                        timing_observer=observer,
                        diagnostics=capture_failures,
                        task_deadline_ns=phase_deadline,
                    )
                    closure_mark("SAMPLING_INSPECTION", deadline=boundary)
                    summaries = boundary.operation(
                        "SAMPLING_INSPECTION",
                        sampling.inspect,
                        lambda: journal.read_events(
                            root, ap.digest(start), contract=ap
                        ),
                        profile,
                        start,
                        maximum_segments=1,
                        contract=ap,
                    )
                    require(
                        summaries and all(row["complete"] for row in summaries),
                        "RA_G1_DIAGNOSTIC_SAMPLING_INCOMPLETE",
                    )
                    closure_mark("SAMPLING_INSPECTION", completed=True, deadline=boundary)
                    closure_mark("T3_PHASE_CLOSE", deadline=boundary)
                    boundary.operation(
                        "OBSERVER_CLOSE",
                        observer.phase_close,
                        phase_id,
                        quiescent=True,
                        timeout_seconds=boundary.remaining(),
                    )
                    closure_mark("T3_PHASE_CLOSE", completed=True, deadline=boundary)
                    require(state["regular"] >= phase["hold_regular_acks"])
                    from safe_geocoding_pipeline.preprocessing.stages import (
                        s12_public_recovery as recovery,
                    )
                    from safe_geocoding_pipeline.preprocessing.stages import (
                        s12_retrieval_contract as retrieval_contract,
                    )

                    negative = current_label == "malformed"
                    require(
                        (
                            not report["report_complete"]
                            and report["disposition"] == "STOPPED"
                            and 2 <= negative_starts <= 3
                        )
                        if negative
                        else (
                            report["report_complete"]
                            and report["disposition"] == "COMPLETED"
                        )
                    )

                    def open_phase_originals():
                        if negative:
                            stopped = ap.parse(
                                storage.read(root / "snapshot.json"), ap.SNAPSHOT
                            )
                            require(stopped["disposition"] == "STOPPED")
                            original_state = recovery.replay(
                                journal.read_events(
                                    root, ap.digest(start), contract=ap
                                ),
                                contract=ap,
                            )
                            recovery.snapshot_evidence(
                                root,
                                stopped,
                                original_state,
                                ap.digest(report["blocks"][0]),
                                check=boundary.check,
                            )
                            for event in journal.read_events(
                                root, ap.digest(start), contract=ap
                            ):
                                if event["kind"] == "ATTEMPT_FINALIZED":
                                    work = item["work"][event["body"]["work_id"] - 1]
                                    name = audit.name_for(
                                        work["work_id"], event["body"]["attempt"]
                                    )
                                    attempt_root = root / "attempts" / name
                                    terminal = audit.reopen(
                                        attempt_root,
                                        name,
                                        validator=adapter.validator(work, attempt_root),
                                        context=oa.DataContext(adapter),
                                    )
                                    require(terminal["outcome"] == "CONTRACT_FAILURE")
                        else:
                            opened = runtime.reopen_completed(
                                root,
                                profile,
                                plan,
                                start,
                                validation_sha256=config["public_validation_sha256"],
                                control_adapters=matrix.adapters(plan),
                            )
                            require(opened == report["blocks"][0])
                            if current_label == "controls8":
                                require(
                                    len(
                                        boundary.operation(
                                            "CONTROL_VERIFY",
                                            matrix.verify_controls,
                                            root,
                                            plan,
                                        )
                                    )
                                    == 4
                                )
                        require(
                            (root / "_SEGMENT_SEALED").is_file()
                            and (root / "_WRITER_RELEASED.json").is_file()
                        )
                        original.charge_runtime_inventory_check(
                            original.runtime_inventory_budget()
                        )
                        closure_mark("RUNTIME_RECHECK", deadline=boundary)
                        require(
                            boundary.operation(
                                "RUNTIME_RECHECK",
                                runtime.runtime_inventory,
                                config["public_validation_sha256"],
                                successor=True,
                                resource_assurance="RA-G1-r1",
                                environment_observation_sha256=record[
                                    "initial_environment_observation_sha256"
                                ],
                                check=boundary.check,
                                backend_reader=assurance.bounded_backend_reader(
                                    original.charge_original
                                ),
                            )
                            == actual_runtime,
                            "RA_G1_DIAGNOSTIC_RUNTIME_CHANGED",
                        )
                        closure_mark("RUNTIME_RECHECK", completed=True, deadline=boundary)
                        assurance.verify_current_facts(bound, authority)
                        original.source_fence()
                        boundary.check()
                        if negative:
                            # Raise only after all required negative originals and
                            # runtime checks validate. Time/I/O failures propagate.
                            return runtime.reopen_completed(
                                root,
                                profile,
                                plan,
                                start,
                                validation_sha256=config["public_validation_sha256"],
                            )
                        return opened

                    closure_mark("NEGATIVE_OPEN" if negative else "NORMAL_OPEN", deadline=boundary)
                    capture_failures.resource_boundary("CALLER_CHECK", deadline_ns=phase_deadline)
                    _, resource_records = boundary.operation(
                        "NEGATIVE_OPEN" if negative else "NORMAL_OPEN",
                        active_resource.freeze_and_open,
                        diagnostics=capture_failures,
                        frozen_data_inventory_sha256=ap.digest(report),
                        actual_opener=open_phase_originals,
                        **(
                            {
                                "expected_negative_sha256": ap.digest(
                                    {
                                        "label": "malformed",
                                        "expected": "S12_PUBLIC_OPERATIONS_INVALID",
                                    }
                                ),
                                "is_expected_negative": lambda error: (
                                    type(error) is retrieval_contract.Stage12Error
                                    and error.args == ("S12_PUBLIC_OPERATIONS_INVALID",)
                                ),
                            }
                            if negative
                            else {}
                        ),
                    )
                    closure_mark("NEGATIVE_OPEN" if negative else "NORMAL_OPEN", completed=True, deadline=boundary)
                    boundary.check()
                    resource_sessions.append(
                        dict(
                            phase_id=phase_id,
                            phase_start_ns=phase_start_ns,
                            phase_deadline_ns=phase_deadline,
                            label=current_label,
                            root=str(active_resource.root),
                            selection_sha256=ap.digest(selected),
                            binding_sha256=ap.digest(bound),
                            records=resource_records,
                        )
                    )
                    original.release_coordinator()
                    active_resource = None
                    original._deadline_check = check
                    phases.append(
                        dict(
                            label=current_label,
                            report_complete=report["report_complete"],
                            campaign_report_sha256=ap.digest(report),
                            regular_acknowledgements=state["regular"],
                            original_reopen=True,
                        )
                    )
        require(106 <= attempts <= 107)
    except BaseException as error:
        if active_resource is not None:
            try:
                capture_failures.resource_failure(error, session=active_resource)
            except BaseException:
                capture_failures.closure_fault()
        try:
            capture_failures.record("RUNTIME", error)
        except BaseException:
            capture_failures.closure_fault()
        runtime_trace("START_FAILED", error=error)
        first_failure = dict(
            at_mono_ns=clock.now_ns(), phase_id=len(boundaries), **safe_failure(error)
        )
        failure = "RA_G1_DIAGNOSTIC_INCOMPLETE"
    finally:
        if active_resource is not None:
            try:
                active_resource.abort()
            except BaseException as error:
                cleanup_failure_count += 1
                cleanup_failure = dict(at_mono_ns=clock.now_ns(), **safe_failure(error))
                failure = failure or "RA_G1_DIAGNOSTIC_RESOURCE_CLEANUP_FAILED"
        final_resource = None
        final_phase_deadline_ns = None
        final_bound_window = (None, None)
        try:
            check()
            if failure is None and len(phases) == 4:
                from safe_geocoding_pipeline.preprocessing.stages import (
                    s12_ra_g1_execution as execution,
                )

                bound = original.sampling_bound(
                    config["campaigns"][-1]["profile"], data["phases"][-1]["start"]
                )
                selected = original.resource_selection(bound)
                final_start_ns = clock.now_ns()
                final_resource = execution.start_session(
                    authority=original,
                    config=config,
                    binding=bound,
                    selection=selected,
                    evidence_root=output / "whole_task_resources",
                    deadline_ns=min(deadline, final_start_ns + 120 * 10**9),
                    phase_id=5,
                    check=check,
                    counters=original.counters,
                    charge=original.allocation_controls.monitor_charge,
                    read_charge=original.charge_original,
                    clock_ns=clock.now_ns,
                    native_roots=(output,),
                    startup_trace=runtime_trace,
                    **({"observer_stages": capture_failures} if observer_stage_enabled else {}),
                )
                runtime_trace.bind_monitor(final_resource.monitor)
            closure_mark("T3_CLOSE", deadline_ns=deadline, guard="GLOBAL_TASK")
            summary = observer.close(
                timeout_seconds=min(5, (deadline - clock.now_ns()) / 1e9)
            )
            closure_mark("T3_CLOSE", completed=True, deadline_ns=deadline, guard="GLOBAL_TASK")
            require(summary["final_timing_coverage_complete"])

            def associate(ordinal, row):
                check()
                phase_id = (
                    row["phase_id"]
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else row["legacy_row"][0]
                )
                require(1 <= phase_id <= 4)
                item = config["campaigns"][phase_id - 1]
                root = output / item["label"]
                sequence = (
                    row["sample_event_seq"]
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else row["legacy_row"][4]
                )
                event = ap.parse(
                    storage.read(root / "events" / f"{sequence:020d}.json", limit=4096),
                    ap.EVENT,
                )
                ack = (
                    ap.parse(
                        storage.read(
                            root / "events" / f"{row['ack_event_seq']:020d}.json",
                            limit=4096,
                        ),
                        ap.EVENT,
                    )
                    if row["row_kind"] == "PERIODIC_ASYNC"
                    else None
                )
                timing.verify_sampling_association(
                    row, event, phase_id=phase_id, ack_event=ack, contract=ap
                )

            def actual_whole_open():
                with storage.cooperative_io(final_resource.check):
                    for item, phase in zip(
                        config["campaigns"], data["phases"], strict=True
                    ):
                        check()
                        root = output / item["label"]
                        if item["label"] == "malformed":
                            stopped = ap.parse(
                                storage.read(root / "snapshot.json"), ap.SNAPSHOT
                            )
                            state = recovery.replay(
                                journal.read_events(
                                    root, ap.digest(phase["start"]), contract=ap
                                ),
                                contract=ap,
                            )
                            recovery.snapshot_evidence(
                                root,
                                stopped,
                                state,
                                ap.digest(
                                    storage.metadata(
                                        storage.read(root / "block_report.json")
                                    )
                                ),
                                check=check,
                            )
                            expected_stopped_rejection(
                                lambda: runtime.reopen_completed(
                                    root,
                                    item["profile"],
                                    item["plan"],
                                    phase["start"],
                                    validation_sha256=config[
                                        "public_validation_sha256"
                                    ],
                                ),
                                check,
                            )
                        else:
                            runtime.reopen_completed(
                                root,
                                item["profile"],
                                item["plan"],
                                phase["start"],
                                validation_sha256=config["public_validation_sha256"],
                                control_adapters=matrix.adapters(item["plan"]),
                            )
                    with storage.cooperative_io(final_resource.check):
                        final_resource.check()
                        closure_mark("T3_REREAD", deadline_ns=final_resource.deadline, guard="WHOLE_TASK_RESOURCE")
                        reopened = cp.read_prefix(
                            observer.checkpoints.root,
                            timing_schema=cp.RA_SCHEMA,
                            expected_binding=summary["checkpoint"]["timing_binding"],
                            expected_snapshot=summary["checkpoint"],
                            record_consumer=associate,
                        )
                        closure_mark("T3_REREAD", completed=True, deadline_ns=final_resource.deadline, guard="WHOLE_TASK_RESOURCE")
                        check()
                    require(
                        not reopened["incomplete"], "RA_G1_DIAGNOSTIC_TIMING_INCOMPLETE"
                    )
                    original.source_fence()
                    return reopened

            if final_resource is not None:
                original._deadline_check = final_resource.check
                closure_mark("WHOLE_OPEN", deadline_ns=final_resource.deadline, guard="WHOLE_TASK_RESOURCE")
                _, final_records = final_resource.freeze_and_open(
                    frozen_data_inventory_sha256=ap.digest(
                        {"phases": phases, "timing": summary}
                    ),
                    actual_opener=actual_whole_open,
                )
                closure_mark("WHOLE_OPEN", completed=True, deadline_ns=final_resource.deadline, guard="WHOLE_TASK_RESOURCE")
                resource_sessions.append(
                    dict(
                        phase_id=5,
                        phase_start_ns=final_start_ns,
                        phase_deadline_ns=final_resource.deadline,
                        label="whole_task",
                        root=str(final_resource.root),
                        selection_sha256=ap.digest(selected),
                        binding_sha256=ap.digest(bound),
                        records=final_records,
                    )
                )
                final_phase_deadline_ns = final_resource.deadline
                final_bound_window = (final_resource.binding["valid_from"], final_resource.binding["valid_until"])
                final_resource = None
            else:
                # On a failed task retain supplementary evidence; it grants no completion.
                with storage.cooperative_io(check):
                    closure_mark("T3_REREAD", deadline_ns=deadline, guard="GLOBAL_TASK")
                    cp.read_prefix(
                        observer.checkpoints.root,
                        timing_schema=cp.RA_SCHEMA,
                        expected_binding=summary["checkpoint"]["timing_binding"],
                        expected_snapshot=summary["checkpoint"],
                        record_consumer=associate,
                    )
                    closure_mark("T3_REREAD", completed=True, deadline_ns=deadline, guard="GLOBAL_TASK")
        except BaseException as error:
            try:
                capture_failures.record("RUNTIME_REOPEN" if failure is None else "CLEANUP", error)
            except BaseException:
                capture_failures.closure_fault()
            cleanup_failure_count += 1
            if cleanup_failure is None:
                cleanup_failure = dict(at_mono_ns=clock.now_ns(), **safe_failure(error))
            if final_resource is not None:
                try:
                    final_resource.abort()
                except BaseException:
                    cleanup_failure_count += 1
            summary = timing.safe_call(observer, "snapshot")
            failure = failure or "RA_G1_DIAGNOSTIC_TIMING_INCOMPLETE"
    # Permanent precharge precedes the final counter prefix. The exclusive
    # summary write is intentionally outside allocation_controls to avoid a
    # second charge; uncertainty retains this full reservation.
    original.allocation_controls.claim("ADMIN_FILE", limits["summary_reserve_bytes"])
    result = dict(
        version=data["version"],
        scope=SCOPE,
        source_sha=args.source_sha,
        input_sha256=args.input_sha256,
        complete=failure is None and len(phases) == 4,
        error=failure,
        initiating_failure=first_failure,
        initiating_failure_scope="CAUGHT_FOREGROUND_EXCEPTION_ONLY_SEE_CAPTURE_AND_MONITOR",
        capture_failure_diagnostics=capture_failures.snapshot(),
        resource_monitor_failure=runtime_trace.monitor_primary(),
        cleanup_failure=cleanup_failure,
        cleanup_failure_count=cleanup_failure_count,
        phase_timings=[boundary.snapshot() for boundary in boundaries],
        attempts=attempts,
        expected_attempts=106,
        maximum_attempts=107,
        phases=phases,
        timing=summary,
        resource_observation=resource_observation,
        resource_sessions=resource_sessions,
        resource_counters=original.counters(),
        network_guard=network_guard,
        filesystem_guard="PYTHON_AUDIT_PATH_DENIAL_NOT_NATIVE_FILESYSTEM_ISOLATION",
        native_component_bound_claim=False,
        logical_artifact_accounting=budget.snapshot(),
        charged_creation_attempts=creations[0],
        elapsed_ns=clock.now_ns() - started_ns,
        cpu_ns=time.process_time_ns() - cpu_started_ns,
    )
    summary_raw = canonical(result)
    require(
        len(summary_raw) <= limits["summary_reserve_bytes"],
        "RA_G1_DIAGNOSTIC_SUMMARY_LIMIT",
    )
    storage.write(output / "summary.json", summary_raw)
    check()
    if result["complete"]:
        def final_diagnostic_check(final_deadline_ns=final_phase_deadline_ns,
                                   valid_from=final_bound_window[0], valid_until=final_bound_window[1]):
            check()
            require(type(final_deadline_ns) is int and clock.now_ns() < final_deadline_ns,
                    "RA_G1_DIAGNOSTIC_PHASE_DEADLINE")
            require(valid_from <= clock.utc() < valid_until, "RA_G1_EXPIRED")
        ACTIVE_DIAGNOSTIC_CHECK = final_diagnostic_check
    return 0 if result["complete"] else 1


def descriptor(version=VERSION):
    require(version in (VERSION, BOOTSTRAP_VERSION, SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS))
    value = dict(
        descriptor_version=version,
        configuration_version=CONFIG_VERSION,
        review_binding_version=REVIEW_VERSION,
        scope=SCOPE,
        live_instance=False,
        default_selection_status="UNISSUED_NON_EXECUTABLE",
        explicit_entrypoint="scripts/stage12_ra_g1_diagnostic.py",
        top_fields=sorted(_TOP),
        required_resource_fields=sorted(_LIMITS),
        configuration_fields=sorted(_CONFIG),
        profile_family="stage12_transport_operations_ra_g1_v1",
        plan_family="stage12_public_characterization_plan_ra_g1_v1",
        start_family="stage12_public_operations_campaign_ra_g1_v1",
        live_resource_record_family="stage12_resource_assurance_binding_ra_g1_v1",
        required_resource_purposes=sorted(_RESOURCE_PURPOSES),
        phases=[
            dict(
                label=label,
                proposed_phase_ms=duration,
                required_regular_ack_hold=hold,
                planned_work=count,
            )
            for label, duration, hold, count in phases_for(version)
        ],
        proposed_total_seconds=7200,
        expected_attempts=106,
        maximum_attempts=107,
        assurance="RA_G1_ACTUAL_SCOPED_OBSERVATIONS_AND_SELECTED_MONITORING",
        service_authority=False,
        native_component_bound_claim=False,
        input_authority="NO_RECORDS_ISSUED;EXACT_REVIEWED_RESOURCES_AND_WORKLOAD_GRANT_REQUIRED",
    )
    if version in (SHARED_LEASE_VERSION, *REP_ADMIN_VERSIONS):
        value.update(runtime_diagnostic_version="stage12_ra_g1_startup_monitor_trace_v2",
            diagnostic_stdout_bytes=8192,
            required_accounting_inventory="stage12_ra_g1_shared_lease_accounting_inventory_v1")
    if version in REP_ADMIN_VERSIONS:
        value.update(required_accounting_inventory="stage12_ra_g1_rep_admin_budget_accounting_inventory_v1",
            required_resource_selection=REP_ADMIN_SELECTION, representative_admin_seconds={
                "collector":120, "review":480, "binder_complete":240, "binder_process":720})
    if version == REP512_VERSION:
        value.update(required_accounting_inventory="stage12_ra_g1_rep_first64_512_accounting_inventory_v1",
            required_resource_selection=REP512_SELECTION, maximum_creations=204860,
            maximum_event_files=57237, historical_first64_ms=346000)
    return value


def main():
    import argparse

    started_ns, cpu_started_ns = _ENTRY_MONO_NS, _ENTRY_CPU_NS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-bundle", type=Path, required=True)
    parser.add_argument("--evidence-review-sha256", required=True)
    parser.add_argument("--observer-stages", action="store_true",
                        help="Retain bounded supplementary resource observer-stage diagnostics")
    args = parser.parse_args()
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.alarm(7200)
    return execute(args, started_ns=started_ns, cpu_started_ns=cpu_started_ns)


def cli_entry():
    try:
        exit_code = main()
    except BaseException as error:
        print(
            canonical(
                dict(failure=safe_failure(error), observed_mono_ns=time.monotonic_ns())
            ).decode(),
            end="",
        )
        exit_code = 1
    trace = ACTIVE_DIAGNOSTIC_TRACE
    if trace is not None:
        try:
            trace("EXIT_REPORT_ENTER")
            trace.emit(sys.stdout)
            if exit_code == 0:
                require(callable(ACTIVE_DIAGNOSTIC_CHECK), "RA_G1_DIAGNOSTIC_LIVE_PROOF_REQUIRED")
                ACTIVE_DIAGNOSTIC_CHECK()
        except BaseException as error:
            print(canonical(dict(failure=safe_failure(error), observed_mono_ns=time.monotonic_ns())).decode(), end="")
            exit_code = 1
    signal.alarm(0)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(cli_entry())

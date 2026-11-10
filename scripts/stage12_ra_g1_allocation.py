"""RA-G1 finite same-allocation metadata, binding and terminal verification.

This successor never certifies hard memory, descendant or physical containment.
Only reviewed originals and exact delegated technical facts can release B.
"""

from __future__ import annotations

# Clock precedes all subsequent controller imports; monitor START includes them.
import time

ROLE_ENTRY_NS = time.monotonic_ns()

# ruff: noqa: E402
try:
    import argparse
    from bisect import bisect_left
    from types import MappingProxyType
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    import hashlib
    import importlib.util
    import json
    import os
    from pathlib import Path
    import resource
    import signal
    import stat
    import sys
    import threading
except BaseException:
    print('{"schema_version":"stage12_ra_g1_startup_trace_v1","trace_status":"EARLY_STDLIB_FAILURE","role_entry_mono_ns":'
          + str(ROLE_ENTRY_NS) + ',"failure_mono_ns":' + str(time.monotonic_ns())
          + ',"code":"UNKNOWN","counter_prefix":null,"output_reservation":"PRECHARGED_STARTUP_LOG_OBSERVED_COUNTERS_UNKNOWN","truncated":false,"hard_kill_guarantee":"NONE"}')
    raise SystemExit(1) from None

STDLIB_IMPORTS_DONE_NS = time.monotonic_ns()

VERSION = "stage12_ra_g1_allocation_selection_v1"
BOOTSTRAP_VERSION = "stage12_ra_g1_bootstrap30_allocation_selection_v1"
SHARED_LEASE_VERSION = "stage12_ra_g1_shared_lease_allocation_selection_v1"
DIAGNOSTIC_VERSION = "stage12_ra_g1_startup_monitor_trace_v2"
SCOPE = "REPRESENTATIVE_NO_SERVICE"
SOURCE_PROJECT_VERSION = "0.2.0"  # Exact reviewed pyproject.toml, not a fallback.
LIMITS = dict(
    processing_seconds=8160,
    scheduler_seconds=8400,
    diagnostic_seconds=7200,
    collector_seconds=120,
    review_seconds=600,
    binder_seconds=120,
    final_seconds=120,
    non_b_bytes=240 * 2**20,
    non_b_creations=1544,
    worker_rss_bytes=768 * 2**20,
    maximum_processes=4,
    maximum_utilities=256,
    maximum_python_invocations=5,
    writer_guard_ms=5000,
)


def need(value, code="RA_G1_ALLOCATION_INVALID"):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def h(value, n=64):
    return (
        type(value) is str
        and len(value) == n
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        name, Path(source) / "scripts" / (name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


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


def private(path):
    path = Path(path)
    need(path.is_absolute() and str(path) == os.path.abspath(path), "RA_G1_PATH")
    info = path.lstat()
    need(
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o700,
        "RA_G1_PATH",
    )
    return identity(info)[:6]


def read(
    path, limit=4 * 2**20, check=lambda: None, read_charge=lambda calls, size: None
):
    path = Path(path)
    private(path.parent)
    check()
    before = path.lstat()
    need(
        stat.S_ISREG(before.st_mode)
        and before.st_nlink == 1
        and before.st_uid == os.geteuid()
        and stat.S_IMODE(before.st_mode) == 0o600
        and before.st_size <= limit,
        "RA_G1_ORIGINAL_CHANGED",
    )
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        need(identity(os.fstat(fd)) == identity(before), "RA_G1_ORIGINAL_CHANGED")
        chunks = bytearray()
        while True:
            check()
            read_charge(1, 0)
            raw = os.read(fd, min(4096, limit + 1 - len(chunks)))
            read_charge(0, len(raw))
            need(len(chunks) + len(raw) <= limit, "RA_G1_READ_LIMIT")
            chunks.extend(raw)
            if not raw:
                break
        need(
            identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
            "RA_G1_ORIGINAL_CHANGED",
        )
        return bytes(chunks)
    finally:
        os.close(fd)


def parse(raw):
    def pairs(items):
        need(len({k for k, v in items}) == len(items), "RA_G1_FIELDS")
        return dict(items)

    value = json.loads(raw, object_pairs_hook=pairs)
    need(canonical(value) == raw, "RA_G1_CANONICAL_REQUIRED")
    return value


def _validate_legacy_selection(s):
    need(
        set(s)
        == {
            "version",
            "scope",
            "source_sha",
            "valid_from",
            "valid_until",
            "paths",
            "source_files",
            "accounting",
            "accounting_inventory",
            "limits",
            "replay_sha256",
            "records",
            "resource_selection_sha256",
            "intent_id",
        },
        "RA_G1_FIELDS",
    )
    need(
        s["version"] == VERSION
        and s["scope"] == SCOPE
        and h(s["source_sha"], 40)
        and h(s["replay_sha256"])
        and h(s["resource_selection_sha256"])
        and h(s["intent_id"]),
        "RA_G1_SELECTION_BINDING",
    )
    need(s["limits"] == LIMITS, "RA_G1_LIMITS")
    need(
        set(s["accounting"])
        == {
            "identity_calls",
            "original_read_calls",
            "original_read_bytes",
            "check_calls",
        }
        and all(type(x) is int and 0 < x < 2**64 for x in s["accounting"].values()),
        "RA_G1_ACCOUNTING",
    )
    need(
        type(s["source_files"]) is list
        and 1 <= len(s["source_files"]) <= 2048
        and sum(x["bytes"] for x in s["source_files"]) <= 64 * 2**20,
        "RA_G1_SOURCE_INVENTORY",
    )
    names = []
    for row in s["source_files"]:
        need(
            set(row) == {"path", "bytes", "sha256"}
            and type(row["bytes"]) is int
            and 0 <= row["bytes"] <= 4 * 2**20
            and h(row["sha256"]),
            "RA_G1_SOURCE_INVENTORY",
        )
        p = Path(row["path"])
        need(not p.is_absolute() and ".." not in p.parts, "RA_G1_PATH")
        names.append(str(p))
    need(names == sorted(set(names)), "RA_G1_SOURCE_INVENTORY")
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting

    s12_ra_g1_accounting.validate_inventory(s["accounting_inventory"])
    need(
        s["accounting_inventory"]["sources"] == s["source_files"]
        and s["accounting_inventory"]["accounting"] == s["accounting"]
        and s["accounting_inventory"]["scope"] == s["scope"],
        "RA_G1_ACCOUNTING",
    )
    keys = {
        "source",
        "allocation_root",
        "records",
        "bootstrap",
        "binding",
        "input",
        "output",
        "review",
        "release",
        "outcome",
        "context",
        "worker_return",
        "supervisor_state",
        "tail",
        "log",
    }
    need(
        set(s["paths"]) == keys
        and all(
            type(x) is str
            and Path(x).is_absolute()
            and str(Path(x)) == os.path.abspath(x)
            for x in s["paths"].values()
        ),
        "RA_G1_PATH",
    )
    root = Path(s["paths"]["allocation_root"])
    need(len(set(s["paths"].values())) == len(s["paths"]), "RA_G1_PATH")
    for key, path in s["paths"].items():
        if key == "log":
            need(Path(path).parent == Path(s["paths"]["records"]), "RA_G1_PATH")
        elif key not in ("source", "records", "allocation_root"):
            need(Path(path).is_relative_to(root), "RA_G1_PATH")
    need(
        set(s["records"])
        == {"adoption", "project_approval", "software_review", "resource_review"}
        and all(h(x) for x in s["records"].values()),
        "RA_G1_AUTHORITY_REQUIRED",
    )
    for date in ("valid_from", "valid_until"):
        need(
            datetime.strptime(s[date], "%Y-%m-%dT%H:%M:%S.%fZ").tzinfo is None,
            "RA_G1_WINDOW",
        )
    need(s["valid_from"] < s["valid_until"], "RA_G1_WINDOW")
    return s


def validate_selection(value):
    if value.get("version") not in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION):
        return _validate_legacy_selection(value)
    extra = {"bootstrap_prefix_adoption", "bootstrap_prefix_adoption_sha256"}
    need(extra <= set(value), "RA_G1_BOOTSTRAP_REQUIRED")
    base = {key: item for key, item in value.items() if key not in extra}
    base["version"] = VERSION
    _validate_legacy_selection(base)
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
    expected_inventory = (accounting.SHARED_LEASE_VERSION if value["version"] == SHARED_LEASE_VERSION else accounting.BOOTSTRAP_VERSION)
    need(value["scope"] == SCOPE and value["accounting_inventory"]["schema_version"] == expected_inventory,
         "RA_G1_BOOTSTRAP_POLICY")
    if value["version"] == SHARED_LEASE_VERSION:
        need(value["accounting_inventory"].get("bootstrap_proof_record_count") == 3, "RA_G1_ACCOUNTING")
    selected = {"bootstrap_prefix_adoption_sha256": value["bootstrap_prefix_adoption_sha256"]}
    assurance.validate_bootstrap_adoption(value["bootstrap_prefix_adoption"], selected)
    return value


def synchronized(method):
    def locked(self, *args, **kwargs):
        with self._counter_lock:
            return method(self, *args, **kwargs)

    return locked


class StartupTrace:
    """Supplementary bounded prefix, never a monitor receipt or closure."""

    EVENTS = tuple("ROLE_ENTRY STDLIB_IMPORTS_DONE MAIN_ENTER MAIN_SETUP_DONE PIPELINE_IMPORTS_ENTER PIPELINE_IMPORTS_DONE SETUP_COMPLETE ADMIN_START_ENTER SESSION_SETUP_ENTER WRITER_CREATED FIRST_ACQUIRE_ENTER FIRST_ACQUIRE_EXIT COVERAGE_BEFORE COVERAGE_AFTER PACK_BEFORE PACK_AFTER APPEND_BEFORE APPEND_AFTER WRITER_ENTER ORIGINAL_PERSIST_ENTER ORIGINAL_FSYNC_BEFORE ORIGINAL_FSYNC_AFTER ORIGINAL_READBACK_BEFORE ORIGINAL_READBACK_AFTER ORIGINAL_PERSIST_EXIT CODEC_APPEND_ENTER CODEC_FSYNC_BEFORE CODEC_FSYNC_AFTER CODEC_READBACK_BEFORE CODEC_READBACK_AFTER ACK_PUBLISHED START_ACK START_FAILED WRITER_FAILURE ABORT_FAILED RUN_CLOSE_ENTER RUN_CLOSE_DONE EXIT_REPORT_ENTER UNKNOWN_EVENT".split())
    MAX_ENTRIES = 48
    MAX_BYTES = 8192

    def __init__(self, role_entry_ns=ROLE_ENTRY_NS, *, clock_ns=time.monotonic_ns):
        self.lock = threading.Lock()
        self.clock = clock_ns
        self.backing = bytearray(self.MAX_ENTRIES * 16)
        self.used = 0
        self.output_reserved = False
        self.dropped = self.unknown = 0
        self.primary = self.cleanup = None
        self.admin = self.writer = None
        self.controller_command = "UNKNOWN"
        self.administrative_role = "UNKNOWN"
        self.administrative_phase_id = None
        self.instrumentation_faults = 0
        self.claimed = False
        self.monitor_diagnostics = False
        self.monitor_source = None
        self.monitor_state = None
        self.output_basis = "RESERVED_METADATA"
        self("ROLE_ENTRY", role_entry_ns)

    def __call__(self, event, at_mono_ns=None, *, writer=None, error=None, cleanup=False):
        if event not in self.EVENTS:
            event = "UNKNOWN_EVENT"
        at = self.clock() if at_mono_ns is None else at_mono_ns
        if type(at) is not int or not 0 <= at < 2**64 - 1:
            at = None
        failure = None
        if error is not None:
            safe = safe_failure(error)
            failure = {key: safe[key] for key in ("family", "code", "errno", "at_mono_ns")}
            failure["event"] = event
        with self.lock:
            if writer is not None:
                self.writer = writer
            self.unknown = min(2**64 - 1, self.unknown + int(event == "UNKNOWN_EVENT" or at is None))
            if self.used < self.MAX_ENTRIES:
                offset = self.used * 16
                self.backing[offset:offset + 8] = self.EVENTS.index(event).to_bytes(8, "big")
                self.backing[offset + 8:offset + 16] = (2**64 - 1 if at is None else at).to_bytes(8, "big")
                self.used += 1
            else:
                self.dropped = min(2**64 - 1, self.dropped + 1)
            if failure is not None:
                if cleanup and self.cleanup is None:
                    self.cleanup = failure
                elif not cleanup and self.primary is None:
                    self.primary = failure

    def note_instrumentation_fault(self):
        with self.lock:
            self.instrumentation_faults = min(2**64 - 1, self.instrumentation_faults + 1)

    def set_controller_command(self, command):
        with self.lock:
            self.controller_command = command if command in (("ready", "collect", "bind", "verify", "phase_runner") if self.monitor_diagnostics else ("ready", "collect", "bind", "verify")) else "UNKNOWN"

    def first_start(self, role=None):
        with self.lock:
            if self.claimed:
                return None
            self.claimed = True
            phases = {"COLLECTOR": 6, "REVIEW": 7, "BINDER": 8}
            if self.monitor_diagnostics:
                phases["PHASE_RUNNER"] = 1
            self.administrative_role = role if role in phases else "UNKNOWN"
            self.administrative_phase_id = phases.get(role)
        self("ADMIN_START_ENTER")
        return self

    def reserve_stdout(self, run):
        # One supplementary stdout record; no file creation and no budget
        # increase. Reserve before role work, so failure/deadline cannot erase
        # the initiating cause while attempting to charge its diagnostic.
        run.charge(self.MAX_BYTES, creations=0)
        with self.lock:
            self.admin = run
            self.output_reserved = True

    def _startup_snapshot(self):
        with self.lock:
            def status(owner):
                if owner is None:
                    return "UNKNOWN"
                value = getattr(owner, "poisoned", None)
                return "UNKNOWN" if type(value) is not bool else ("POISONED" if value else "HEALTHY")
            entries = []
            for index in range(self.used):
                offset = index * 16
                code = int.from_bytes(self.backing[offset:offset + 8], "big")
                at = int.from_bytes(self.backing[offset + 8:offset + 16], "big")
                entries.append(dict(event=self.EVENTS[code], at_mono_ns=None if at == 2**64 - 1 else at))
            return dict(schema_version="stage12_ra_g1_startup_trace_v1",
                trace_status="INCOMPLETE_INSTRUMENTATION" if self.instrumentation_faults else "BOUNDED_PREFIX_NOT_CLOSURE", first_start_only=True,
                controller_command=self.controller_command,
                administrative_role=self.administrative_role,
                administrative_phase_id=self.administrative_phase_id,
                instrumentation_faults=self.instrumentation_faults,
                persistence_uncertainty="STDOUT_ACK_IS_NOT_LOG_FSYNC_OR_FINAL_COVERAGE",
                entries=entries, truncated=bool(self.dropped),
                dropped_entries=self.dropped, unknown_entries=self.unknown,
                primary_failure=None if self.primary is None else dict(self.primary),
                cleanup_failure=None if self.cleanup is None else dict(self.cleanup),
                writer_status=dict(admin=status(self.admin), monitor=status(self.writer)),
                persistence="EXISTING_PRECHARGED_SUPERVISOR_STDOUT_LOG_ONLY",
                controller_scope="COLLECTOR_BINDER_REVIEW_FIRST_START_AND_VERIFIER_SETUP",
                phase_runner="EXISTING_TELEMETRY_UNCHANGED_NOT_IN_THIS_TRACE",
                interpreter_import_or_hardkill_coverage="NOT_GUARANTEED",
                logical_backing_bytes=len(self.backing), failure_state_allowance_bytes=1024,
                serialization_maximum_bytes=self.MAX_BYTES,
                serialization_scope="OUTSIDE_CONTROLLER_ACTIONS_NO_AP_SCRATCH_LEASE",
                output_reservation=dict(bytes=self.MAX_BYTES,creation_attempts=0,
                    basis="EXISTING_CONTROLLER_METADATA_AND_PRECHARGED_16MIB_LOG",
                    observed_counter_charge="RESERVED_METADATA" if self.output_reserved else None),
                maximum_json_bytes=self.MAX_BYTES, hard_kill_guarantee="NONE")



    DIAGNOSTIC_STAGES = frozenset("IDLE CHECK OBSERVER COVERAGE PACK APPEND WAIT_ACK POST_ACK_CHECK PUBLISH ORIGINAL_WRITE ORIGINAL_FSYNC ORIGINAL_READBACK CODEC_WRITE CODEC_FSYNC CODEC_READBACK ACK CLOSED BARRIER".split())
    DIAGNOSTIC_CODES = frozenset(('PUBLIC_PROBE_EVIDENCE_WRITE_FAILED', 'PUBLIC_PROBE_EXECUTABLE_MISMATCH', 'RA_G1_COUNTER_LIMIT', 'RA_G1_DEADLINE', 'RA_G1_MONITOR_GAP', 'RA_G1_MONITOR_INCOMPLETE', 'RA_G1_MONITOR_THRESHOLD', 'RA_G1_NATIVE_DISCOVERY', 'RA_G1_ORIGINAL_CHANGED', 'RA_G1_PROCESS_SCOPE', 'RA_G1_PROTOCOL', 'RA_G1_READ_LIMIT', 'RA_G1_REQUIRED_READING', 'RA_G1_WRITE_UNCERTAIN', 'RESPONSE_CONTRACT_INVALID', 'RETRY_BUDGET_EXHAUSTED', 'S12_CAPTURE_INCOMPLETE', 'S12_METADATA_INVALID', 'S12_PRIVATE_FILE_INVALID', 'S12_PUBLIC_AUTHORITY_CHANGED', 'S12_PUBLIC_AUTHORITY_SCOPE', 'S12_PUBLIC_OPERATIONS_INVALID', 'S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH', 'S12_PUBLIC_WINDOW_CLOSED', 'SECRET_ECHO_DETECTED', 'UNKNOWN', 'WF_AP2_SCRATCH_LIMIT', 'WF_AP2_SCRATCH_REENTRANT'))

    def enable_monitor_diagnostics(self):
        with self.lock:
            self.monitor_diagnostics = True

    @classmethod
    def validated_monitor_snapshot(cls, value):
        """Copy only the closed, fixed scalar diagnostic; never exception text."""
        def fields(item, expected):
            need(type(item) is dict and set(item) == set(expected), "RA_G1_FIELDS")

        def integer(item, nullable=False):
            need((nullable and item is None) or type(item) is int and 0 <= item < 2**64, "RA_G1_FIELDS")
            return item

        def enumeration(item, choices, nullable=False):
            need((nullable and item is None) or type(item) is str and item in choices, "RA_G1_FIELDS")
            return item

        def fault(item):
            if item is None:
                return None
            fields(item, ("family", "code", "errno", "mono_ns", "source", "stage"))
            number = item["errno"]
            need(number is None or type(number) is int and 0 <= number <= 4095, "RA_G1_FIELDS")
            return dict(
                family=enumeration(item["family"], ("STAGE12_ERROR", "OS_ERROR", "UNKNOWN")),
                code=enumeration(item["code"], cls.DIAGNOSTIC_CODES),
                errno=number, mono_ns=integer(item["mono_ns"], True),
                source=enumeration(item["source"], ("WRITER", "MONITOR")),
                stage=enumeration(item["stage"], cls.DIAGNOSTIC_STAGES),
            )

        fields(value, ("phase_id", "monitor_failure", "first_primary", "acquisition", "published", "writer"))
        acquisition = value["acquisition"]
        fields(acquisition, ("kind", "stage", "enter_mono_ns", "exit_mono_ns"))
        acquisition = dict(
            kind=enumeration(acquisition["kind"], ("START", "PERIODIC", "FINAL"), True),
            stage=enumeration(acquisition["stage"], cls.DIAGNOSTIC_STAGES),
            enter_mono_ns=integer(acquisition["enter_mono_ns"], True),
            exit_mono_ns=integer(acquisition["exit_mono_ns"], True),
        )
        published = value["published"]
        if published is not None:
            fields(published, ("seq", "enter_mono_ns", "exit_mono_ns", "ack_mono_ns"))
            published = {key: integer(published[key], key != "seq") for key in published}
        writer = value["writer"]
        if writer is not None:
            fields(writer, ("rows", "acked", "ack_ns", "poisoned", "closing", "released",
                            "thread_alive", "current_seq", "stage", "first_failure"))
            copied = {}
            for key in ("rows", "acked", "ack_ns", "current_seq"):
                copied[key] = integer(writer[key], key in ("ack_ns", "current_seq"))
            for key in ("poisoned", "closing", "released", "thread_alive"):
                need(type(writer[key]) is bool, "RA_G1_FIELDS")
                copied[key] = writer[key]
            copied["stage"] = enumeration(writer["stage"], cls.DIAGNOSTIC_STAGES)
            copied["first_failure"] = fault(writer["first_failure"])
            writer = copied
        return dict(
            phase_id=integer(value["phase_id"]),
            monitor_failure=enumeration(value["monitor_failure"], cls.DIAGNOSTIC_CODES, True),
            first_primary=fault(value["first_primary"]), acquisition=acquisition,
            published=published, writer=writer,
        )

    def bind_monitor(self, monitor):
        if self.monitor_diagnostics:
            with self.lock:
                self.monitor_source = monitor

    def monitor_failure(self, value):
        if not self.monitor_diagnostics:
            return
        try:
            actual = self.validated_monitor_snapshot(value)
        except BaseException:
            self.note_instrumentation_fault()
            return
        fault = actual["first_primary"]
        with self.lock:
            if self.monitor_state is None:
                self.monitor_state = actual
            if self.primary is None and fault is not None:
                self.primary = dict(
                    family="CONTRACT_OR_GUARD" if fault["family"] == "STAGE12_ERROR" else fault["family"],
                    code=fault["code"], errno=fault["errno"], at_mono_ns=fault["mono_ns"],
                    event="MONITOR_RUNTIME_FAILURE",
                )

    def monitor_primary(self):
        with self.lock:
            if not self.monitor_diagnostics or self.monitor_state is None:
                return None
            fault = self.monitor_state["first_primary"]
            if fault is None:
                return None
            return dict(
                family="CONTRACT_OR_GUARD" if fault["family"] == "STAGE12_ERROR" else fault["family"],
                code=fault["code"] if fault["code"] in SAFE_CODES else "UNKNOWN",
                errno=fault["errno"], at_mono_ns=fault["mono_ns"],
            )

    def snapshot(self):
        value = self._startup_snapshot()
        if not self.monitor_diagnostics:
            return value
        with self.lock:
            source = self.monitor_source
            actual = self.monitor_state
        if actual is None and source is not None:
            try:
                actual = self.validated_monitor_snapshot(source.diagnostic_snapshot())
            except BaseException:
                self.note_instrumentation_fault()
        with self.lock:
            # A failure published while the healthy snapshot was copied wins.
            actual = self.monitor_state if self.monitor_state is not None else actual
            value["primary_failure"] = None if self.primary is None else dict(self.primary)
            value["instrumentation_faults"] = self.instrumentation_faults
        value.update(
            schema_version=DIAGNOSTIC_VERSION, first_start_only=False,
            trace_status="INCOMPLETE_INSTRUMENTATION" if value["instrumentation_faults"] else "BOUNDED_DIAGNOSTIC_NOT_CLOSURE",
            runtime_monitor=actual, runtime_logical_scalar_bytes=31*8,
        )
        value["controller_scope"] = "ALL_SOURCE_OWNED_ATTACHED_MONITOR_SCOPES"
        value["phase_runner"] = "SOURCE_OWNED_ATTACHMENT" if self.controller_command == "phase_runner" else "NOT_IN_THIS_PROCESS"
        value["output_reservation"]["observed_counter_charge"] = self.output_basis if self.output_reserved else None
        return value

    def reserve_phase_stdout(self, controls):
        # stdout belongs to the existing finite log. No output file is created.
        controls.reserve_components(self.MAX_BYTES, 0)
        with self.lock:
            self.output_reserved = True
            self.output_basis = "RESERVED_PHASE_LOG"


    def encoded_snapshot(self):
        """Count closed bounded scalars before allocating the output arena.

        No output-sized Unicode string is constructed. The two encoder passes
        see the same private snapshot; JSON scalar chunks are at most 512 ASCII
        bytes. Python allocator/encoder internals are monitored risk, not a
        native memory theorem.
        """
        value = self.snapshot()
        nodes = 0

        def validate_scalar_tree(item, depth=0):
            nonlocal nodes
            nodes += 1
            need(nodes <= 512 and depth <= 8, "RA_G1_WRITE_LIMIT")
            if item is None or type(item) is bool:
                return
            if type(item) is int:
                need(0 <= item <= 2**64 - 1, "RA_G1_WRITE_LIMIT")
            elif type(item) is str:
                need(len(item) <= 128 and all(32 <= ord(ch) < 127 for ch in item), "RA_G1_WRITE_LIMIT")
            elif type(item) is list:
                need(len(item) <= self.MAX_ENTRIES, "RA_G1_WRITE_LIMIT")
                for child in item:
                    validate_scalar_tree(child, depth + 1)
            elif type(item) is dict:
                need(len(item) <= 32 and all(type(key) is str for key in item), "RA_G1_WRITE_LIMIT")
                for key, child in item.items():
                    validate_scalar_tree(key, depth + 1)
                    validate_scalar_tree(child, depth + 1)
            else:
                need(False, "RA_G1_WRITE_LIMIT")

        validate_scalar_tree(value)
        encoder = json.JSONEncoder(ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        total = 1  # canonical LF
        for chunk in encoder.iterencode(value):
            need(chunk.isascii() and len(chunk) <= 512, "RA_G1_WRITE_LIMIT")
            total += len(chunk)
            need(total <= self.MAX_BYTES, "RA_G1_WRITE_LIMIT")
        arena = bytearray(total)
        offset = 0
        for chunk in encoder.iterencode(value):
            need(chunk.isascii() and len(chunk) <= 512, "RA_G1_WRITE_LIMIT")
            for start in range(0, len(chunk), 256):
                raw = chunk[start:start + 256].encode("ascii")
                end = offset + len(raw)
                need(end < total, "RA_G1_WRITE_LIMIT")
                arena[offset:end] = raw
                offset = end
        need(offset + 1 == total, "RA_G1_WRITE_LIMIT")
        arena[offset] = 10
        return arena

    def emit(self, output):
        raw = self.encoded_snapshot()
        output.flush()  # earlier status record precedes the supplementary record
        binary = getattr(output, "buffer", None)
        if binary is not None:
            position = 0
            view = memoryview(raw)
            while position < len(raw):
                written = binary.write(view[position:])
                need(type(written) is int and 0 < written <= len(raw) - position, "RA_G1_WRITE_UNCERTAIN")
                position += written
            binary.flush()
        else:
            for start in range(0, len(raw), 256):
                chunk = raw[start:start + 256].decode("ascii")
                need(output.write(chunk) == len(chunk), "RA_G1_WRITE_UNCERTAIN")
            output.flush()


PROCESS_TRACE = StartupTrace()
PROCESS_TRACE("STDLIB_IMPORTS_DONE", STDLIB_IMPORTS_DONE_NS)


class Run:
    def __init__(self, s, *, epoch_ns=None, stage_seconds=None, stage="collect"):
        self.role_enter_ns = ROLE_ENTRY_NS
        self.startup_trace = PROCESS_TRACE
        if s.get("version") == SHARED_LEASE_VERSION:
            self.startup_trace.enable_monitor_diagnostics()
        PROCESS_TRACE.admin = self
        self._counter_lock = threading.RLock()
        self.s = validate_selection(s)
        observed_now = time.monotonic_ns()
        self.started = observed_now if epoch_ns is None else epoch_ns
        need(
            type(self.started) is int
            and 0 <= self.started <= observed_now
            and observed_now - self.started <= 8160 * 10**9,
            "RA_G1_DEADLINE",
        )
        self.end = min(
            self.started + 8160 * 10**9,
            time.monotonic_ns() + (stage_seconds or 8160) * 10**9,
        )
        self.checks = self.read_calls = self.read_bytes = self.write_bytes = (
            self.creations
        ) = 0
        self.poisoned = False
        self.first_failure = None
        self.file_attempts = 0
        self.monitor_usage = dict(bytes=0, creations=0, rows=0, directories=0)
        self.carried_metadata = {}
        self.predecessor_handoff_sha256 = None
        self.carried_source_prefix = None
        self.selected_resource = None
        self.admin_records = []
        self.active_scope_deadline = None
        self.administrative_partition = None
        self.stage = stage
        self.byte_limit, self.creation_limit = {
            "ready": (0, 0),
            "collect": (32 * 2**20, 256),
            "bind": (160 * 2**20, 1024),
            "verify": (32 * 2**20, 128),
        }[stage]
        self._pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ra-g1-admin-writer"
        )

    @synchronized
    def check(self):
        self.checks += 1
        need(not self.poisoned, "RA_G1_WRITE_UNCERTAIN")
        need(
            time.monotonic_ns() < self.end
            and (
                self.active_scope_deadline is None
                or time.monotonic_ns() < self.active_scope_deadline
            )
            and self.s["valid_from"] <= now() < self.s["valid_until"],
            "RA_G1_DEADLINE",
        )
        need(self.checks <= self.s["accounting"]["check_calls"], "RA_G1_CHECK_BUDGET")
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (
            1 if sys.platform == "darwin" else 1024
        )
        need(rss <= 768 * 2**20, "RA_G1_MONITOR_THRESHOLD")

    @synchronized
    def read_charge(self, calls, size):
        self.check()
        need(
            type(calls) is int and calls >= 0 and type(size) is int and size >= 0,
            "RA_G1_READ_LIMIT",
        )
        self.read_calls += calls
        self.read_bytes += size
        need(
            self.read_calls <= self.s["accounting"]["original_read_calls"]
            and self.read_bytes <= self.s["accounting"]["original_read_bytes"],
            "RA_G1_READ_LIMIT",
        )

    def original(self, path, limit=4 * 2**20):
        self.check()
        return read(path, limit, self.check, self.read_charge)

    @synchronized
    def charge(self, size, creations=1):
        self.check()
        need(
            type(size) is int
            and size >= 0
            and type(creations) is int
            and creations >= 0,
            "RA_G1_COUNTER_LIMIT",
        )
        self.write_bytes += size
        self.creations += creations
        need(
            self.write_bytes <= self.byte_limit
            and self.creations <= self.creation_limit,
            "RA_G1_COUNTER_LIMIT",
        )

    def prewrite(self, parent, size, creations=1):
        private(parent)
        v = os.statvfs(parent)
        need(
            v.f_frsize > 0
            and v.f_favail >= 4096 + creations
            and v.f_bavail * v.f_frsize >= 1342177280 + size,
            "RA_G1_SHARED_MARGIN",
        )

    def write(self, path, value):
        return self.write_raw(path, canonical(value))

    def write_raw(self, path, raw, *, monitor=False):
        self.check()
        path = Path(path)
        need(type(raw) is bytes and len(raw) <= 4 * 2**20, "RA_G1_WRITE_LIMIT")
        (self.monitor_charge(8192, 1) if monitor else self.charge(len(raw)))
        if not monitor:
            self.file_attempts += 1
        self.prewrite(path.parent, len(raw))

        def action():
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            try:
                view = memoryview(raw)
                while view:
                    n = os.write(fd, view)
                    need(n > 0, "RA_G1_WRITE_UNCERTAIN")
                    view = view[n:]
                os.fsync(fd)
            finally:
                os.close(fd)
            parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
            need(
                read(path, check=self.check, read_charge=self.read_charge) == raw,
                "RA_G1_WRITE_UNCERTAIN",
            )

        future = self._pool.submit(action)
        try:
            future.result(
                timeout=min(5, max(0, (self.end - time.monotonic_ns()) / 1e9))
            )
            self.check()
        except BaseException:
            self.poisoned = True
            raise
        return hashlib.sha256(raw).hexdigest()

    def write_monitor_record(self, path, value):
        raw = canonical(value)
        need(len(raw) <= 8192, "RA_G1_WRITE_LIMIT")
        return self.write_raw(path, raw, monitor=True)

    def mkdir(self, path):
        path = Path(path)
        self.charge(0)
        self.prewrite(path.parent, 0)
        path.mkdir(mode=0o700)
        private(path)
        self.check()

    def record(self, name):
        identity = self.s["records"][name]
        raw = self.original(Path(self.s["paths"]["records"]) / (identity + ".record"))
        need(hashlib.sha256(raw).hexdigest() == identity, "RA_G1_AUTHORITY_CHANGED")
        return parse(raw)

    def sources(self):
        root = Path(self.s["paths"]["source"])
        private(root)
        for row in self.s["source_files"]:
            self.check()
            p = root / row["path"]
            before = p.lstat()
            need(
                stat.S_ISREG(before.st_mode) and before.st_size == row["bytes"],
                "RA_G1_SOURCE_CHANGED",
            )
            fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
            hsh = hashlib.sha256()
            try:
                need(identity(before) == identity(os.fstat(fd)), "RA_G1_SOURCE_CHANGED")
                remaining = row["bytes"]
                while remaining:
                    self.check()
                    self.read_charge(1, 0)
                    raw = os.read(fd, min(4096, remaining))
                    self.read_charge(0, len(raw))
                    need(bool(raw), "RA_G1_SOURCE_CHANGED")
                    hsh.update(raw)
                    remaining -= len(raw)
                self.check()
                self.read_charge(1, 0)
                extra = os.read(fd, 1)
                self.read_charge(0, len(extra))
                need(
                    not extra
                    and identity(before)
                    == identity(os.fstat(fd))
                    == identity(p.lstat())
                    and hsh.hexdigest() == row["sha256"],
                    "RA_G1_SOURCE_CHANGED",
                )
            finally:
                os.close(fd)

    @synchronized
    def monitor_charge(self, size, creations=0, directory=False):
        self.check()
        need(
            type(size) is int
            and size >= 0
            and type(creations) is int
            and creations >= 0,
            "RA_G1_COUNTER_LIMIT",
        )
        self.monitor_usage["bytes"] += size
        self.monitor_usage["creations"] += creations
        self.monitor_usage["directories"] += creations if directory else 0
        self.monitor_usage["rows"] += int(size == 15360 and creations == 1)
        limits = self.selected_resource["limits"]
        if self.administrative_partition is not None:
            partition = self.administrative_partition
            need(
                self.monitor_usage["bytes"] - partition["bytes_start"]
                <= partition["logical_write_bytes"]
                and self.monitor_usage["creations"] - partition["creations_start"]
                <= partition["application_creations"],
                "RA_G1_COUNTER_LIMIT",
            )
        need(
            self.monitor_usage["creations"] - self.monitor_usage["directories"]
            <= limits["application_counters"]["ADMIN_FILE"],
            "RA_G1_COUNTER_LIMIT",
        )
        need(
            self.monitor_usage["bytes"] <= limits["monitor_bytes"]
            and self.monitor_usage["creations"] <= limits["monitor_creations"]
            and self.monitor_usage["rows"] <= limits["monitor_rows"],
            "RA_G1_COUNTER_LIMIT",
        )

    def monitor_directory_charge(self, size, creations):
        self.monitor_charge(size, creations, directory=True)

    @synchronized
    def resource_counters(self):
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m

        values = {key: 0 for key in m.COUNTERS}
        files = self.monitor_usage["creations"] - self.monitor_usage["directories"]
        need(files >= 0, "RA_G1_COUNTER_LIMIT")
        values.update(
            ADMIN_FILE=files,
            application_write_reserved_bytes=self.monitor_usage["bytes"],
            application_creations_charged=self.monitor_usage["creations"],
            monitor_observations_charged=self.monitor_usage["rows"],
            monitor_write_bytes_charged=self.monitor_usage["bytes"],
            source_read_calls=self.read_calls,
            source_read_bytes=self.read_bytes,
            identity_checks=self.checks,
        )
        return values

    @synchronized
    def counter_prefix(self):
        metadata = {key: dict(value) for key, value in self.carried_metadata.items()}
        metadata[self.stage] = dict(
            write_bytes=self.write_bytes,
            creations=self.creations,
            file_attempts=self.file_attempts,
        )
        return dict(
            source_read_calls=self.read_calls,
            source_read_bytes=self.read_bytes,
            checks=self.checks,
            monitor_usage=dict(self.monitor_usage),
            metadata=metadata,
        )

    def close(self):
        self._pool.shutdown(wait=not self.poisoned, cancel_futures=True)


def ready(run):
    run.check()
    run.sources()
    s = run.s
    for name in ("adoption", "project_approval", "software_review", "resource_review"):
        run.record(name)
    review = run.record("software_review")
    need(
        review.get("disposition") == "PASS"
        and review.get("source_sha") == s["source_sha"],
        "RA_G1_REVIEW_REQUIRED",
    )
    resource_review = run.record("resource_review")
    need(
        resource_review.get("disposition") == "PASS"
        and resource_review.get("source_sha") == s["source_sha"],
        "RA_G1_REVIEW_REQUIRED",
    )
    adoption = run.record("adoption")
    need(
        adoption.get("decision")
        == "ADOPTED_PROSPECTIVELY_WITH_EXPLICIT_LOCAL_REPAIR_OVERRIDE",
        "RA_G1_AUTHORITY_REQUIRED",
    )
    project = run.record("project_approval")
    need(
        project.get("attribution")
        == "OWNER_REPORTED_PROJECT_APPROVAL_NOT_ADMIN_ATTESTATION"
        and project.get("scope") == SCOPE,
        "RA_G1_AUTHORITY_REQUIRED",
    )
    run.prewrite(Path(s["paths"]["allocation_root"]).parent, 240 * 2**20, 1544)
    return True


def resource_selection(run):
    if run.selected_resource is None:
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_ra_g1_assurance as a,
            s12_ra_g1_contract as contract,
        )

        review = run.record("resource_review")
        run.selected_resource = module(
            run.s["paths"]["source"], "stage12_prepare_ra_g1"
        ).resource_selection(
            run.s,
            policy_sha256=digest(contract.descriptors()[a.POLICY]),
            adoption_sha256=run.s["records"]["adoption"],
            descriptor_inventory_sha256=review["descriptor_inventory_sha256"],
            graph_sha256=review["workload_graph_sha256"],
            paths_sha256=review["paths_sha256"],
            implementation_review_sha256=run.record("software_review")["report_sha256"],
        )
        need(
            digest(run.selected_resource) == run.s["resource_selection_sha256"],
            "RA_G1_SELECTION_BINDING",
        )
    return run.selected_resource


def administrative_risk(selected):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a

    value = dict(
        schema_version=a.RISK,
        scope=SCOPE,
        method=a.METHOD,
        policy_sha256=selected["policy_sha256"],
        adoption_sha256=selected["adoption_sha256"],
        entries=[
            dict(
                risk=kind,
                observation_scope="GUARDED_ADMINISTRATIVE_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "NOT_OBSERVABLE",
                control="FINITE_GUARDED_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "EXPLICIT_ACCEPTED_UNKNOWN",
                maximum="NOT_PROVEN",
                evidence_sha256=selected["adoption_sha256"],
            )
            for kind in a.RISKS
        ],
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        complete_descendant_coverage="NOT_ESTABLISHED",
    )
    a.validate_risk_inventory(value)
    return value


def start_admin(run, role, context, *, scope_start_ns):
    startup_trace = run.startup_trace.first_start(role)
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e

    selected = resource_selection(run)
    if getattr(run.startup_trace, "monitor_diagnostics", False):
        startup_trace = run.startup_trace
    phase = e.ADMIN_ROLES[role]
    limits = next(
        (row for row in selected["limits"]["stages"] if row["id"] == phase), None
    )
    need(limits is not None, "RA_G1_ADMIN_SCOPE")
    end = min(run.end, scope_start_ns + limits["deadline_ms"] * 10**6)
    run.active_scope_deadline = end
    process, parent = e._process_identity(
        os.getpid(), check=run.check, read_charge=run.read_charge
    )
    need(parent == context["supervisor"]["pid"], "RA_G1_PROCESS_SCOPE")
    risk = administrative_risk(selected)
    bound = dict(
        schema_version=e.ADMIN_BINDING,
        scope=SCOPE,
        method="LOGICAL_LIMITS_AND_SCOPED_MONITORING",
        role=role,
        phase_id=phase,
        source_git_sha=run.s["source_sha"],
        selection_sha256=digest(selected),
        adoption_sha256=selected["adoption_sha256"],
        supervisor_context_sha256=digest(context),
        risk_inventory_sha256=digest(risk),
        process_pid=process["pid"],
        process_start_ticks=process["start_ticks"],
        process_uid=process["uid"],
        scope_start_mono_ns=scope_start_ns,
        deadline_mono_ns=end,
        service_authority="DENIED",
        protected_input_authority="DENIED",
        ap_dispatch_authority="DENIED",
    )
    root = Path(run.s["paths"]["allocation_root"]) / (role.lower() + "_resources")
    run.administrative_partition = dict(
        bytes_start=run.monitor_usage["bytes"],
        creations_start=run.monitor_usage["creations"],
        logical_write_bytes=limits["logical_write_bytes"],
        application_creations=limits["creations"],
    )
    bootstrap_prefix = None
    if selected.get("schema_version") == e.a.BOOTSTRAP_SELECTION and role in ("COLLECTOR", "REVIEW"):
        bootstrap_prefix = dict(role=role, source_entry_ns=scope_start_ns,
                                bootstrap_end_ns=time.monotonic_ns())
    session = e.start_administrative_session(
        binding=bound,
        selection=selected,
        evidence_root=root,
        pids=(os.getpid(), context["supervisor"]["pid"]),
        cgroup_path=Path(context["visible_cgroup_path"]),
        counters=run.resource_counters,
        charge=run.monitor_charge,
        directory_charge=run.monitor_directory_charge,
        check=run.check,
        read_charge=run.read_charge,
        scope_start_ns=scope_start_ns,
        deadline_ns=end,
        startup_trace=startup_trace,
        bootstrap_prefix=bootstrap_prefix,
        bootstrap_adoption_reader=lambda identity: run.original(
            Path(run.s["paths"]["records"]) / (identity + ".record"), limit=8192),
    )
    if getattr(run.startup_trace, "monitor_diagnostics", False):
        run.startup_trace.bind_monitor(session.monitor)
    run.write(root / "admin_binding.record", bound)
    risk_path = Path(run.s["paths"]["allocation_root"]) / "administrative_risk.record"
    if risk_path.exists():
        need(parse(run.original(risk_path)) == risk, "RA_G1_ORIGINAL_CHANGED")
    else:
        run.write(risk_path, risk)
    return session


def finish_admin(run, session, paths, opener):
    frozen = []
    for path in paths:
        path = Path(path)
        frozen.append(
            dict(path=str(path), sha256=hashlib.sha256(run.original(path)).hexdigest())
        )

    def actual_opener():
        for row in frozen:
            need(
                hashlib.sha256(run.original(row["path"])).hexdigest() == row["sha256"],
                "RA_G1_ORIGINAL_CHANGED",
            )
        return opener()

    _, records = session.freeze_and_open(
        frozen_data_inventory_sha256=digest(frozen), actual_opener=actual_opener
    )
    run.active_scope_deadline = None
    run.administrative_partition = None
    row = dict(
        role=session.binding["role"],
        phase_id=session.phase,
        root=str(session.root),
        binding_sha256=digest(session.binding),
        worker_validation_sha256=digest(records["worker_validation"]),
    )
    run.admin_records.append(row)
    return row


HANDOFF = "stage12_ra_g1_administrative_handoff_v1"
HANDOFF_KEYS = {
    "schema_version",
    "source_sha",
    "allocation_selection_sha256",
    "resource_selection_sha256",
    "scope",
    "stage",
    "supervisor_context_sha256",
    "process_pid",
    "counter_prefix",
    "predecessor_handoff_sha256",
    "administrative_sessions",
    "post_prefix_contract",
}
HANDOFF_CONTRACT = (
    "ONE_EXCLUSIVE_FULL_WRITE_FSYNC_ONE_FULL_READ_EOF_AND_ONE_SUCCESSFUL_MAIN_CHECK"
)


def write_handoff(run, context):
    # Source-controlled success performs exactly two original read calls here.
    # Short writes/reads fail; no future observation is guessed in the prefix.
    run.check()
    value = dict(
        schema_version=HANDOFF,
        scope=SCOPE,
        source_sha=run.s["source_sha"],
        allocation_selection_sha256=digest(run.s),
        resource_selection_sha256=run.s["resource_selection_sha256"],
        stage=run.stage,
        supervisor_context_sha256=digest(context),
        process_pid=os.getpid(),
        counter_prefix=run.counter_prefix(),
        predecessor_handoff_sha256=run.predecessor_handoff_sha256,
        administrative_sessions=run.admin_records,
        post_prefix_contract=HANDOFF_CONTRACT,
    )
    raw = canonical(value)
    need(len(raw) <= 65536, "RA_G1_WRITE_LIMIT")
    path = Path(run.s["paths"]["allocation_root"]) / (
        "collector.handoff.record"
        if run.stage == "collect"
        else "binder.handoff.record"
    )
    run.charge(len(raw))
    run.file_attempts += 1
    run.prewrite(path.parent, len(raw))
    end = min(run.end, time.monotonic_ns() + 5 * 10**9)

    def action():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            need(os.write(fd, raw) == len(raw), "RA_G1_WRITE_UNCERTAIN")
            os.fsync(fd)
        finally:
            os.close(fd)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            run.read_charge(1, 0)
            observed = os.read(fd, len(raw))
            run.read_charge(0, len(observed))
            need(observed == raw, "RA_G1_WRITE_UNCERTAIN")
            run.read_charge(1, 0)
            extra = os.read(fd, 1)
            run.read_charge(0, len(extra))
            need(not extra, "RA_G1_WRITE_UNCERTAIN")
        finally:
            os.close(fd)
        run.check()
        need(time.monotonic_ns() < end, "RA_G1_DEADLINE")

    future = run._pool.submit(action)
    try:
        future.result(timeout=max(0, (end - time.monotonic_ns()) / 1e9))
    except BaseException:
        run.poisoned = True
        raise
    return hashlib.sha256(raw).hexdigest()


def handoff_counters(value, raw_size):
    need(
        set(value) == HANDOFF_KEYS
        and value["schema_version"] == HANDOFF
        and value["scope"] == SCOPE
        and value["stage"] in ("collect", "bind")
        and value["post_prefix_contract"] == HANDOFF_CONTRACT,
        "RA_G1_HANDOFF",
    )
    prefix = value["counter_prefix"]
    need(
        set(prefix)
        == {
            "source_read_calls",
            "source_read_bytes",
            "checks",
            "monitor_usage",
            "metadata",
        },
        "RA_G1_HANDOFF",
    )
    result = json.loads(canonical(prefix))
    # These exact deltas follow only from a genuine successful same-source CLI
    # return; the original prefix itself does not claim future readback facts.
    result["source_read_calls"] += 2
    result["source_read_bytes"] += raw_size
    result["checks"] += 7
    row = result["metadata"][value["stage"]]
    row["write_bytes"] += raw_size
    row["creations"] += 1
    row["file_attempts"] += 1
    return result


def validate_wait_record(
    value, *, source_sha, allocation_selection_sha256, supervisor_pid, process_pid=None
):
    keys = {
        "version",
        "source_sha",
        "selection_sha256",
        "supervisor_pid",
        "pid",
        "exit_code",
        "wait_status",
        "acquired_mono_ns",
    }
    need(
        type(value) is dict
        and set(value) == keys
        and value["version"] == "stage12_ra_g1_supervisor_wait_v1"
        and value["source_sha"] == source_sha
        and value["selection_sha256"] == allocation_selection_sha256
        and value["supervisor_pid"] == supervisor_pid
        and type(value["pid"]) is int
        and value["pid"] > 0
        and value["exit_code"] == 0
        and value["wait_status"] == 0
        and type(value["acquired_mono_ns"]) is int
        and value["acquired_mono_ns"] >= 0
        and (process_pid is None or value["pid"] == process_pid),
        "RA_G1_CHILD_FAILED",
    )
    return value


def load_handoff_prefix(context, selected, *, stage, check, read_charge):
    root = Path(context["private_paths"]["allocation_root"])
    stem = "collector" if stage == "collect" else "binder"
    raw = read(root / (stem + ".handoff.record"), 65536, check, read_charge)
    value = parse(raw)
    need(
        value["source_sha"] == selected["source_git_sha"]
        and value["resource_selection_sha256"] == digest(selected)
        and value["supervisor_context_sha256"] == digest(context)
        and value["stage"] == stage,
        "RA_G1_HANDOFF",
    )
    returned = parse(read(root / (stem + ".wait.record"), 65536, check, read_charge))
    validate_wait_record(
        returned,
        source_sha=value["source_sha"],
        allocation_selection_sha256=value["allocation_selection_sha256"],
        supervisor_pid=context["supervisor"]["pid"],
        process_pid=value["process_pid"],
    )
    return value, handoff_counters(value, len(raw)), digest(value), returned


def adopt_handoff(run, context, *, stage):
    value, totals, identity_value, returned = load_handoff_prefix(
        context,
        resource_selection(run),
        stage=stage,
        check=run.check,
        read_charge=run.read_charge,
    )
    need(value["allocation_selection_sha256"] == digest(run.s), "RA_G1_HANDOFF")
    with run._counter_lock:
        run.read_calls += totals["source_read_calls"]
        run.read_bytes += totals["source_read_bytes"]
        run.checks += totals["checks"]
        run.monitor_usage = dict(totals["monitor_usage"])
        run.carried_metadata = {
            key: dict(row) for key, row in totals["metadata"].items()
        }
        run.predecessor_handoff_sha256 = identity_value
        run.carried_source_prefix = dict(totals)
    run.check()
    return value, returned


def collect(run):
    run.startup_trace("PIPELINE_IMPORTS_ENTER")
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_assurance as a,
        s12_ra_g1_execution as e,
        s12_public_runtime as runtime,
    )

    run.startup_trace("PIPELINE_IMPORTS_DONE")
    require_goethe_nhr_slurm("RA-G1 actual no-service allocation metadata")
    s = run.s
    run.mkdir(s["paths"]["allocation_root"])
    run.mkdir(s["paths"]["bootstrap"])
    root = Path(s["paths"]["bootstrap"])
    start = time.monotonic_ns()
    facts, originals = a.observe_current_facts(
        check=run.check, read_charge=run.read_charge
    )
    a.validate_environment_originals(facts, originals)
    selected = module(s["paths"]["source"], "stage12_prepare_ra_g1").resource_selection(
        s,
        policy_sha256=a.old.digest(
            __import__(
                "safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_contract",
                fromlist=["descriptors"],
            ).descriptors()[a.POLICY]
        ),
        adoption_sha256=s["records"]["adoption"],
        descriptor_inventory_sha256=run.record("resource_review")[
            "descriptor_inventory_sha256"
        ],
        graph_sha256=run.record("resource_review")["workload_graph_sha256"],
        paths_sha256=run.record("resource_review")["paths_sha256"],
        implementation_review_sha256=run.record("software_review")["report_sha256"],
    )
    need(digest(selected) == s["resource_selection_sha256"], "RA_G1_SELECTION_BINDING")
    run.selected_resource = selected
    # Same source-owned shell remains parent of collector, binder, worker and verifier.
    context = e.capture_supervisor_context(
        scope=SCOPE,
        source_git_sha=s["source_sha"],
        selection=selected,
        run_nonce=s["intent_id"],
        private_paths=dict(
            allocation_root=s["paths"]["allocation_root"],
            resource_evidence_root=s["paths"]["output"],
            scratch_root=s["paths"]["allocation_root"],
        ),
        supervisor_pid=os.getppid(),
        timeout_pid=None,
        check=run.check,
        read_charge=run.read_charge,
    )
    run.startup_trace("SETUP_COMPLETE")
    administrative = start_admin(
        run, "COLLECTOR", context, scope_start_ns=run.role_enter_ns
    )
    ready(run)
    run.write(s["paths"]["context"], context)
    method = {"method": "CURRENT_STATVFS_SHARED_SNAPSHOT_NOT_RESERVATION"}
    restrictions = {
        "known": "SITE_PROJECT_RULES_PRESERVED",
        "unknown": "NOT_ESTABLISHED",
    }
    cap, capraw = a.observe_capacity(
        s["paths"]["allocation_root"],
        scope=SCOPE,
        selection_sha256=digest(selected),
        owner_reported_approval_sha256=s["records"]["project_approval"],
        accounting_method_sha256=digest(method),
        restrictions_inventory_sha256=digest(restrictions),
        observed_utc=now(),
    )
    a.check_capacity(cap, next_write_bytes=240 * 2**20, next_creations=1544)
    inventory = runtime.runtime_inventory(
        "849a0863876b75dcef322a46d74c2558708cb8611046c8235869090cce621ae2",
        successor=True,
        resource_assurance="RA-G1-r1",
        environment_observation_sha256=digest(facts),
        backend_reader=a.bounded_backend_reader(run.read_charge),
        check=run.check,
    )
    second, second_originals = a.observe_current_facts(
        originals, check=run.check, read_charge=run.read_charge
    )
    a.validate_environment_originals(second, second_originals)
    need(
        all(
            facts[k] == second[k]
            for k in (
                "boot_id",
                "cgroup_namespace_inode",
                "mount_namespace_inode",
                "visible_identity_inventory_sha256",
            )
        ),
        "RA_G1_RUNTIME_CHANGED",
    )
    payload = dict(
        source_sha=s["source_sha"],
        scope=SCOPE,
        job_id=os.environ["SLURM_JOB_ID"],
        created_utc=now(),
        facts=facts,
        kernel_originals=originals,
        capacity=cap,
        capacity_originals=capraw,
        capacity_method=method,
        capacity_restrictions=restrictions,
        runtime_inventory=inventory,
        resource_execution={
            "schema_version": "stage12_resource_execution_request_ra_g1_v1",
            "supervisor_context_path": s["paths"]["context"],
            "supervisor_context_sha256": digest(context),
        },
        second_facts=second,
        second_kernel_originals=second_originals,
        started_mono_ns=start,
        ended_mono_ns=time.monotonic_ns(),
        counters=dict(
            checks=run.checks,
            read_calls=run.read_calls,
            read_bytes=run.read_bytes,
            write_bytes=run.write_bytes,
            creations=run.creations,
        ),
    )
    identity_value = run.write(root / "bootstrap.record", payload)
    run.write(
        root / "manifest.record",
        dict(
            schema_version="stage12_ra_g1_bootstrap_manifest_v1",
            source_sha=s["source_sha"],
            bootstrap_sha256=identity_value,
            scope=SCOPE,
            originals_status="ACTUAL_SCOPED_OBSERVATIONS_NOT_CONTAINMENT_PROOF",
        ),
    )

    def actual_bootstrap_open():
        original = run.original(root / "bootstrap.record")
        manifest_original = run.original(root / "manifest.record")
        value = validate_bootstrap_originals(run, original, manifest_original)
        a.validate_environment_originals(value["facts"], value["kernel_originals"])
        a.validate_environment_originals(
            value["second_facts"], value["second_kernel_originals"]
        )
        a.validate_capacity_originals(
            value["capacity"],
            value["capacity_originals"]["root"],
            value["capacity_originals"]["statvfs"],
            value["capacity_method"],
            value["capacity_restrictions"],
            root_path=s["paths"]["allocation_root"],
        )
        run.sources()
        return value

    finish_admin(
        run,
        administrative,
        [root / "bootstrap.record", root / "manifest.record", s["paths"]["context"]],
        actual_bootstrap_open,
    )
    handoff = write_handoff(run, context)
    return dict(
        status="BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED",
        bootstrap_sha256=identity_value,
        handoff_sha256=handoff,
    )


def wait_record(run, path, *, deadline_ns):
    while not Path(path).exists():
        run.check()
        need(time.monotonic_ns() < deadline_ns, "RA_G1_REVIEW_TIMEOUT")
        time.sleep(0.25)
    return parse(run.original(path))


def validate_bootstrap_originals(run, raw, manifest_raw):
    payload, manifest = parse(raw), parse(manifest_raw)
    need(
        set(manifest)
        == {
            "schema_version",
            "source_sha",
            "bootstrap_sha256",
            "scope",
            "originals_status",
        }
        and manifest["schema_version"] == "stage12_ra_g1_bootstrap_manifest_v1"
        and manifest["source_sha"] == run.s["source_sha"]
        and manifest["bootstrap_sha256"] == hashlib.sha256(raw).hexdigest()
        and manifest["scope"] == SCOPE
        and manifest["originals_status"]
        == "ACTUAL_SCOPED_OBSERVATIONS_NOT_CONTAINMENT_PROOF",
        "RA_G1_BOOTSTRAP_BINDING",
    )
    need(
        payload["source_sha"] == run.s["source_sha"] and payload["scope"] == SCOPE,
        "RA_G1_BOOTSTRAP_BINDING",
    )
    return payload


def bind(run):
    s = run.s
    resource_selection(run)
    context = parse(run.original(s["paths"]["context"]))
    carried, collector_return = adopt_handoff(run, context, stage="collect")
    review_session = start_admin(
        run, "REVIEW", context, scope_start_ns=run.role_enter_ns
    )
    verify_administrative_sessions(
        context,
        resource_selection(run),
        carried["administrative_sessions"],
        collector_return,
        check=run.check,
        read_charge=run.read_charge,
        write_record=lambda path, value: run.write(path, value),
        counter_digest=lambda: digest(run.counter_prefix()),
        deadline_ns=run.end,
    )
    run.sources()
    root = Path(s["paths"]["bootstrap"])
    raw = run.original(root / "bootstrap.record")
    b = parse(raw)
    manifest = run.original(root / "manifest.record")
    validate_bootstrap_originals(run, raw, manifest)
    b["manifest_sha256"] = hashlib.sha256(manifest).hexdigest()
    end = min(run.end, time.monotonic_ns() + 600 * 10**9)
    review = wait_record(run, s["paths"]["review"], deadline_ns=end)
    need(
        review.get("disposition") == "PASS"
        and review.get("source_sha") == s["source_sha"]
        and review.get("bootstrap_manifest_sha256") == b["manifest_sha256"]
        and review.get("selection_sha256") == digest(s),
        "RA_G1_BOOTSTRAP_REVIEW_REQUIRED",
    )
    finish_admin(
        run,
        review_session,
        [root / "bootstrap.record", root / "manifest.record", s["paths"]["review"]],
        lambda: validate_bootstrap_originals(
            run,
            run.original(root / "bootstrap.record"),
            run.original(root / "manifest.record"),
        ),
    )
    bind_enter = time.monotonic_ns()
    binding_session = start_admin(run, "BINDER", context, scope_start_ns=bind_enter)
    end = min(run.end, binding_session.deadline)
    run.mkdir(s["paths"]["binding"])
    bundle = Path(s["paths"]["binding"])
    run.mkdir(bundle / "resource_evidence")
    software = run.record("software_review")
    report = run.original(
        Path(s["paths"]["records"]) / (software["report_sha256"] + ".md")
    )
    builder = module(s["paths"]["source"], "stage12_prepare_ra_g1")
    data, objects = builder.build(
        s,
        b,
        implementation_report=report,
        source_files=s["source_files"],
        adoption=run.record("adoption"),
        project_approval=run.record("project_approval"),
        resource_review=run.record("resource_review"),
        independent_bootstrap_review=review,
        issued=True,
    )
    need(
        digest(objects["resource_selection"]) == s["resource_selection_sha256"],
        "RA_G1_SELECTION_BINDING",
    )
    for role, values in objects["resource_evidence"].items():
        for identity_value, value in values.items():
            path = bundle / "resource_evidence" / (identity_value + ".record")
            if path.exists():
                need(run.original(path) == canonical(value), "RA_G1_EVIDENCE_CHANGED")
            else:
                run.write(path, value)
    for role, value in objects["role_records"].items():
        run.write(bundle / (role + ".record"), value)
    run.write(bundle / "diagnostic_selection.record", objects["diagnostic_selection"])
    run.write(bundle / "diagnostic_resources.record", objects["diagnostic_resources"])
    run.write(bundle / "integration_review.binding.json", objects["integration_review"])
    run.write_raw(bundle / "integration_review.md", report)
    run.write(s["paths"]["input"], data)
    diagnostic = module(s["paths"]["source"], "stage12_ra_g1_diagnostic")
    diagnostic.validate_envelope(
        parse(run.original(s["paths"]["input"])), s["source_sha"], for_execution=True
    )
    diagnostic.validate_workloads(data)
    release = wait_record(run, s["paths"]["release"], deadline_ns=end)
    need(
        set(release)
        == {
            "schema_version",
            "disposition",
            "selection_sha256",
            "source_sha",
            "input_sha256",
            "review_binding_sha256",
            "bootstrap_review_sha256",
            "resource_selection_sha256",
        }
        and release["schema_version"] == "stage12_ra_g1_exact_input_release_v1"
        and release["disposition"] == "PASS"
        and release["source_sha"] == s["source_sha"]
        and release["selection_sha256"] == digest(s)
        and release["input_sha256"] == digest(data)
        and release["review_binding_sha256"] == digest(objects["integration_review"])
        and release["bootstrap_review_sha256"] == digest(review)
        and release["resource_selection_sha256"] == s["resource_selection_sha256"],
        "RA_G1_EXACT_INPUT_REVIEW_REQUIRED",
    )
    run.sources()
    run.check()

    def actual_binding_open():
        actual_data = parse(run.original(s["paths"]["input"]))
        need(actual_data == data, "RA_G1_EVIDENCE_CHANGED")
        diagnostic.validate_envelope(actual_data, s["source_sha"], for_execution=True)
        diagnostic.validate_workloads(actual_data)
        need(
            parse(run.original(s["paths"]["release"])) == release,
            "RA_G1_EXACT_INPUT_REVIEW_REQUIRED",
        )
        for values in objects["resource_evidence"].values():
            for hash_value, value in values.items():
                need(
                    parse(
                        run.original(
                            bundle / "resource_evidence" / (hash_value + ".record")
                        )
                    )
                    == value,
                    "RA_G1_EVIDENCE_CHANGED",
                )
        run.sources()
        return actual_data

    finish_admin(
        run,
        binding_session,
        [
            s["paths"]["input"],
            s["paths"]["review"],
            s["paths"]["release"],
            bundle / "integration_review.binding.json",
        ],
        actual_binding_open,
    )
    handoff = write_handoff(run, context)
    return {
        "status": "EXACT_DIAGNOSTIC_RELEASED",
        "input_sha256": digest(data),
        "review_binding_sha256": digest(objects["integration_review"]),
        "handoff_sha256": handoff,
    }


def validate_original_phase_times(row, originals, selected, global_deadline_ns):
    start, end = row["phase_start_ns"], row["phase_deadline_ns"]
    need(
        type(start) is int
        and type(end) is int
        and 0 <= start < end <= global_deadline_ns,
        "RA_G1_DEADLINE",
    )
    phase = next(
        (
            value
            for value in selected["limits"]["stages"]
            if value["id"] == row["phase_id"]
        ),
        None,
    )
    need(
        phase is not None and end <= start + phase["deadline_ms"] * 10**6,
        "RA_G1_DEADLINE",
    )
    terminal = originals["monitor_terminal"]
    need(
        start <= terminal["coverage_start_ns"]
        and originals["opener_return"]["actual_opener_return_ns"] < end
        and terminal["final_observation_ns"] < end
        and terminal["last_ack_ns"] < end
        and originals["worker_validation"]["first_pass_end_ns"] < end,
        "RA_G1_DEADLINE",
    )


def carry_worker_source_prefix(run, worker):
    """Keep the actual worker watermark plus this verifier's fresh deltas."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m

    need(
        type(worker) is dict
        and set(worker) == set(m.COUNTERS)
        and all(type(value) is int and value >= 0 for value in worker.values()),
        "RA_G1_COUNTER_LIMIT",
    )
    carried = run.carried_source_prefix
    need(carried is not None, "RA_G1_HANDOFF")
    with run._counter_lock:
        for attribute, key, old_key in (
            ("read_calls", "source_read_calls", "source_read_calls"),
            ("read_bytes", "source_read_bytes", "source_read_bytes"),
            ("checks", "identity_checks", "checks"),
        ):
            need(worker[key] >= carried[old_key], "RA_G1_COUNTER_LIMIT")
            setattr(
                run, attribute, getattr(run, attribute) + worker[key] - carried[old_key]
            )
    run.check()


def verify(run):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m

    s = run.s
    context = parse(run.original(s["paths"]["context"]))
    adopt_handoff(run, context, stage="bind")
    run.sources()
    child = parse(run.original(s["paths"]["worker_return"]))
    validate_wait_record(
        child,
        source_sha=s["source_sha"],
        allocation_selection_sha256=digest(s),
        supervisor_pid=context["supervisor"]["pid"],
    )
    data = parse(run.original(s["paths"]["input"]))
    summary = parse(run.original(Path(s["paths"]["output"]) / "summary.json"))
    need(
        summary["complete"]
        and 106 <= summary["attempts"] <= 107
        and len(summary["resource_sessions"]) == 5,
        "RA_G1_DIAGNOSTIC_INCOMPLETE",
    )
    need(
        [row["phase_id"] for row in summary["resource_sessions"]] == list(range(1, 6)),
        "RA_G1_DIAGNOSTIC_INCOMPLETE",
    )
    worker_start_ns = summary["resource_sessions"][0]["phase_start_ns"]
    need(
        type(worker_start_ns) is int and run.started <= worker_start_ns,
        "RA_G1_DEADLINE",
    )
    worker_deadline_ns = min(run.end, worker_start_ns + 7200 * 10**9)
    carry_worker_source_prefix(run, summary["resource_counters"])
    binding_root = Path(s["paths"]["binding"])
    evidence = binding_root / "resource_evidence"
    first = data["configuration"]["campaigns"][0]
    bound = parse(
        run.original(
            evidence / (first["profile"]["sampling_runtime_bound_sha256"] + ".record")
        )
    )
    selected = parse(run.original(evidence / (bound["selection_sha256"] + ".record")))
    reports = []
    counter_originals = {}

    def current_counter_original():
        value = dict(
            schema_version="stage12_ra_g1_verifier_counter_prefix_v1",
            worker_prefix=summary["resource_counters"],
            verifier_prefix=run.counter_prefix(),
            observed_mono_ns=time.monotonic_ns(),
            semantics="ACTUAL_PREFIX_BEFORE_TERMINAL_WRITE_GUARDED_SUFFIX_FOLLOWS",
        )
        identity_value = digest(value)
        counter_originals[identity_value] = value
        return identity_value

    administrative_reports = []
    for stage in ("collect", "bind"):
        carried, totals, identity_value, returned = load_handoff_prefix(
            context,
            selected,
            stage=stage,
            check=run.check,
            read_charge=run.read_charge,
        )
        need(carried["allocation_selection_sha256"] == digest(s), "RA_G1_HANDOFF")
        administrative_reports.extend(
            verify_administrative_sessions(
                context,
                selected,
                carried["administrative_sessions"],
                returned,
                check=run.check,
                read_charge=run.read_charge,
                write_record=lambda path, value: run.write(path, value),
                counter_digest=current_counter_original,
                deadline_ns=run.end,
                terminal_name="final_verification.record",
            )
        )
    need(len(administrative_reports) == 3, "RA_G1_ADMIN_SCOPE")
    for row in summary["resource_sessions"]:
        run.check()
        root = Path(row["root"])
        need(
            root == Path(s["paths"]["output"]) / (row["label"] + "_resources"),
            "RA_G1_PATH",
        )
        records = {
            name: parse(run.original(root / (name + ".record")))
            for name in (
                "preopening",
                "opener_return",
                "monitor_terminal",
                "worker_validation",
            )
        }
        validate_original_phase_times(row, records, selected, worker_deadline_ns)
        protocol = m.reopen_phase_protocol(
            binding_sha256=digest(bound),
            selection_sha256=digest(selected),
            phase_id=row["phase_id"],
            closure=records["preopening"],
            opener_return=records["opener_return"],
            monitor_terminal=records["monitor_terminal"],
            deadline_ns=run.end,
            check=run.check,
        )
        seed = digest(
            dict(
                schema_version="stage12_resource_monitor_seed_ra_g1_v1",
                binding_sha256=digest(bound),
                selection_sha256=digest(selected),
                phase_id=row["phase_id"],
            )
        )

        e.validate_current_supervisor(
            context,
            binding=bound,
            selection=selected,
            evidence_root=Path(s["paths"]["output"]),
            check=run.check,
            read_charge=run.read_charge,
        )

        def original_reader(identity_value):
            return m.read_original_observation(
                root / "originals" / (identity_value + ".record"),
                expected_sha256=identity_value,
                check=run.check,
                charge_read=run.read_charge,
            )

        def persist_terminal(value, check):
            check()
            run.write(root / "supervisor_terminal.record", value)
            actual = parse(run.original(root / "supervisor_terminal.record"))
            check()
            return actual

        reports.append(
            m.verify_tail(
                protocol=protocol,
                monitor_path=root / "observations.bin",
                selected=selected,
                seed_sha256=seed,
                child_result={
                    "pid": child["pid"],
                    "wait_status": child["wait_status"],
                    "acquired_mono_ns": child["acquired_mono_ns"],
                },
                genuine_wait_status=child["wait_status"],
                expected_child_pid=child["pid"],
                current_counter_sha256=current_counter_original,
                persist_terminal=persist_terminal,
                original_observation_reader=original_reader,
                worker_validation=records["worker_validation"],
                charge_read=run.read_charge,
            )
        )
    run.check()
    result = dict(
        version="stage12_ra_g1_allocation_terminal_v1",
        status="COMPLETE_REPRESENTATIVE_NO_SERVICE",
        source_sha=s["source_sha"],
        selection_sha256=digest(s),
        input_sha256=digest(data),
        summary_sha256=digest(summary),
        supervisor_wait_sha256=digest(child),
        resource_terminal_records=reports,
        administrative_terminal_records=administrative_reports,
        counter_originals=counter_originals,
        completed_mono_ns=time.monotonic_ns(),
        deadline_mono_ns=run.end,
        coverage="SCOPED_MONITORING_PLUS_GUARDED_SUFFIX_NOT_CONTAINMENT",
    )
    run.write(s["paths"]["tail"], result)
    run.check()
    return result


SOURCE_PERMISSION_MAXIMUM_ROWS = 2048
SOURCE_PERMISSION_MAXIMUM_CHARACTERS = 512
SOURCE_PERMISSION_MAXIMUM_ROOT_CHARACTERS = 512
SOURCE_PERMISSION_MAXIMUM_ROOT_PARTS = 64
SOURCE_PERMISSION_INDEX_REFERENCE_BYTES = 81920
SOURCE_PERMISSION_FIXED_LOGICAL_BYTES = 1024
SOURCE_PERMISSION_QUERY_LOGICAL_BYTES = 8192
SOURCE_PERMISSION_APPLICATION_CALLERS = 4
SOURCE_PERMISSION_LOGICAL_BYTES = (
    SOURCE_PERMISSION_INDEX_REFERENCE_BYTES
    + SOURCE_PERMISSION_FIXED_LOGICAL_BYTES
    + SOURCE_PERMISSION_APPLICATION_CALLERS * SOURCE_PERMISSION_QUERY_LOGICAL_BYTES
)
_SOURCE_PERMISSION_BINDING_KEYS = (
    "version", "scope", "source_sha", "valid_from", "valid_until",
    "replay_sha256", "resource_selection_sha256", "intent_id",
    "bootstrap_prefix_adoption_sha256",
)


class _SourcePermissionIndex(tuple):
    """Immutable selected membership, not a filesystem or validity cache.

    Relative strings are borrowed from a genuinely validated selection. Fresh
    binding comparisons reject stale permission inputs. Native tuple/dict
    headers, allocator retention and unexpected native callbacks are NOT_PROVEN.
    The explicit logical subreservation is within the existing OTHER_LOGICAL
    arena; no file-write counter or physical-memory entitlement is invented.
    """

    __slots__ = ()

    def __new__(cls, selected):
        need(type(selected) is dict and type(selected.get("paths")) is dict
             and type(selected["paths"].get("source")) is str,
             "RA_G1_SOURCE_INDEX_UNSUPPORTED")
        source_text = selected["paths"]["source"]
        need(len(source_text) <= SOURCE_PERMISSION_MAXIMUM_ROOT_CHARACTERS
             and source_text.count("/") <= SOURCE_PERMISSION_MAXIMUM_ROOT_PARTS,
             "RA_G1_SOURCE_INDEX_UNSUPPORTED")
        rows = selected.get("source_files")
        need(type(rows) is list and 1 <= len(rows) <= SOURCE_PERMISSION_MAXIMUM_ROWS,
             "RA_G1_SOURCE_INDEX_UNSUPPORTED")
        for row in rows:
            need(type(row) is dict and type(row.get("path")) is str
                 and len(row["path"]) <= SOURCE_PERMISSION_MAXIMUM_CHARACTERS,
                 "RA_G1_SOURCE_INDEX_UNSUPPORTED")
        validate_selection(selected)
        source_parts = len(Path(source_text).parts)
        need(source_parts <= SOURCE_PERMISSION_MAXIMUM_ROOT_PARTS,
             "RA_G1_SOURCE_INDEX_UNSUPPORTED")
        need(1 <= len(rows) <= SOURCE_PERMISSION_MAXIMUM_ROWS,
             "RA_G1_SOURCE_INVENTORY")
        names = tuple(row["path"] for row in rows)
        entries = tuple((row["path"], row["bytes"], row["sha256"]) for row in rows)
        policy = MappingProxyType({
            "version": selected["version"],
            "paths": MappingProxyType(dict(selected["paths"])),
            "records": MappingProxyType(dict(selected["records"])),
            "bootstrap_prefix_adoption_sha256": selected.get(
                "bootstrap_prefix_adoption_sha256"),
        })
        scalar_binding = tuple(selected.get(key) for key in _SOURCE_PERMISSION_BINDING_KEYS)
        return tuple.__new__(cls, (
            selected, rows, names, entries, policy, scalar_binding, tuple(selected), source_parts,
        ))

    @property
    def policy(self):
        return self[4]

    def matches(self, selected):
        if (selected is not self[0]
            or type(selected) is not dict
            or len(selected) != len(self[6])
            or any(key not in selected for key in self[6])
            or selected.get("source_files") is not self[1]
            or len(self[1]) != len(self[3])):
            return False
        for key, value in zip(_SOURCE_PERMISSION_BINDING_KEYS, self[5]):
            current = selected.get(key)
            if type(current) is not type(value) or current != value:
                return False
        for key in ("paths", "records"):
            current, frozen = selected.get(key), self.policy[key]
            if type(current) is not dict or len(current) != len(frozen):
                return False
            for name, value in frozen.items():
                item = current.get(name)
                if type(item) is not str or item != value:
                    return False
        for row, entry in zip(self[1], self[3]):
            if (type(row) is not dict or len(row) != 3
                or type(row.get("path")) is not str or row["path"] != entry[0]
                or type(row.get("bytes")) is not int or row["bytes"] != entry[1]
                or type(row.get("sha256")) is not str or row["sha256"] != entry[2]):
                return False
        return len(self[1]) == len(self[3])

    def contains(self, resolved, source):
        if resolved == source:
            return True
        text, source_text = str(resolved), str(source)
        if (len(text) > len(source_text) + 1 + SOURCE_PERMISSION_MAXIMUM_CHARACTERS
            or text.count("/") > self[7] + SOURCE_PERMISSION_MAXIMUM_CHARACTERS // 2 + 1
            or not resolved.is_relative_to(source)):
            return False
        parts, first = resolved.parts, self[7]
        characters = len(parts) - first - 1
        for position in range(first, len(parts)):
            characters += len(parts[position])
            if characters > SOURCE_PERMISSION_MAXIMUM_CHARACTERS:
                return False
        relative = "/".join(parts[first:])
        names = self[2]
        position = bisect_left(names, relative)
        if position < len(names) and names[position] == relative:
            return True
        prefix = relative + "/"
        position = bisect_left(names, prefix)
        return position < len(names) and names[position].startswith(prefix)


def allocation_path_policy(s, path, write=False, *, source_index=None):
    original = Path(os.fsdecode(path))
    if not original.is_absolute() or ".." in original.parts:
        return False
    resolved = Path(os.path.realpath(original))
    if any(
        part in {".ssh", ".config", "credentials", ".git"} or part.startswith(".env")
        for part in (*original.parts, *resolved.parts)
    ):
        return False
    if source_index is not None:
        need(type(source_index) is _SourcePermissionIndex and source_index.matches(s),
             "RA_G1_SOURCE_CHANGED")
        s = source_index.policy
    root = Path(s["paths"]["allocation_root"])
    controls = {
        Path(s["paths"][key]) for key in ("worker_return", "supervisor_state")
    } | {root / (stem + ".wait.record") for stem in ("collector", "binder")}
    if write:
        return (
            resolved == original
            and resolved not in controls
            and (resolved == root or resolved.is_relative_to(root))
        )
    if resolved == original and (resolved == root or resolved.is_relative_to(root)):
        return True
    if (not write and s.get("version") in (BOOTSTRAP_VERSION, SHARED_LEASE_VERSION)
            and resolved == original == Path(s["paths"]["records"]) / (s["bootstrap_prefix_adoption_sha256"] + ".record")):
        return True
    if resolved == original and resolved in {
        Path(s["paths"]["records"]) / (identity + ".record")
        for identity in s["records"].values()
    }:
        return True
    source = Path(s["paths"]["source"])
    if source_index is None:
        exact = {source / row["path"] for row in s["source_files"]}
        directories = {source}
        for item in exact:
            parent = item.parent
            while parent.is_relative_to(source):
                directories.add(parent)
                parent = parent.parent
        if resolved == original and (resolved in exact or resolved in directories):
            return True
    elif resolved == original and source_index.contains(resolved, source):
        return True
    for prefix in (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()):
        if resolved == prefix or resolved.is_relative_to(prefix):
            return True
    if str(resolved) in ("/dev/null", "/dev/urandom"):
        return True
    return False


def install_denials(s, *, check=lambda: None, read_charge=lambda calls, size: None):
    """Actual existing native network guard plus narrowed Python access policy."""
    source_index = _SourcePermissionIndex(s)
    source = Path(s["paths"]["source"])
    sys.dont_write_bytecode = True
    guard = module(source, "stage12_ra_g1_diagnostic")
    record_root = Path(s["paths"]["records"])
    review = parse(
        read(
            record_root / (s["records"]["software_review"] + ".record"),
            check=check,
            read_charge=read_charge,
        )
    )
    need(h(review.get("report_sha256")), "RA_G1_REVIEW_REQUIRED")
    report = record_root / (review["report_sha256"] + ".md")

    fd = os.open(f"/proc/{os.getpid()}/cgroup", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        chunks = bytearray()
        while True:
            check()
            read_charge(1, 0)
            piece = os.read(fd, min(4096, 8193 - len(chunks)))
            read_charge(0, len(piece))
            need(len(chunks) + len(piece) <= 8192, "RA_G1_READ_LIMIT")
            chunks.extend(piece)
            if not piece:
                break
        membership = chunks.decode("ascii").strip()
    finally:
        os.close(fd)
    need(membership.startswith("0::/"), "RA_G1_PROCESS_SCOPE")
    domain = Path("/sys/fs/cgroup" + membership[3:].rstrip("/"))

    def allowed(path, *, write, source, output, input_path, evidence, self_proc=None):
        original = Path(os.fsdecode(path))
        resolved = Path(os.path.realpath(original))
        if original.is_relative_to("/proc") or resolved.is_relative_to("/proc"):
            return not write and (
                str(original) == str(resolved) == "/proc/sys/kernel/random/boot_id"
                or self_proc is not None
                and self_proc.permits(original, resolved)
            )
        if original.is_relative_to("/sys/fs/cgroup"):
            if write:
                return False
            return (
                original == resolved
                and original.parent == domain
                and original.name
                in {
                    "memory.max",
                    "memory.high",
                    "memory.swap.max",
                    "pids.max",
                    "cgroup.procs",
                }
            )
        if not write and original == resolved == report:
            return True
        return allocation_path_policy(s, path, write, source_index=source_index)

    guard.open_allowed = allowed
    native, network, creations, selected, charge, denied = guard.install_denials(
        source,
        Path(s["paths"]["allocation_root"]),
        Path(s["paths"]["input"]),
        record_root,
    )
    need(
        network == "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT",
        "RA_G1_NATIVE_DENIAL_REQUIRED",
    )
    selected[0] = 184184 + 1544
    sys.dont_write_bytecode = True
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport

    transport.Secret.runtime = classmethod(denied)
    transport.Secret.private_file = classmethod(denied)
    return dict(
        network=network,
        python_path_scope="EXACT_SOURCE_RUNTIME_CONTROLLED_METADATA_AND_SELF_PARENT_KERNEL",
        native_filesystem_isolation="NOT_CLAIMED",
    )


SAFE_CODES = frozenset(
    "RA_G1_ALLOCATION_INVALID RA_G1_CANONICAL_REQUIRED RA_G1_FIELDS RA_G1_PATH RA_G1_SELECTION_BINDING RA_G1_LIMITS RA_G1_ACCOUNTING RA_G1_SOURCE_INVENTORY RA_G1_AUTHORITY_REQUIRED RA_G1_WINDOW RA_G1_DEADLINE RA_G1_WRITE_UNCERTAIN RA_G1_CHECK_BUDGET RA_G1_MONITOR_THRESHOLD RA_G1_MONITOR_GAP RA_G1_BOOTSTRAP_REQUIRED RA_G1_BOOTSTRAP_LIMIT RA_G1_BOOTSTRAP_POLICY RA_G1_BOOTSTRAP_EVIDENCE RA_G1_REQUIRED_READING RA_G1_NATIVE_DISCOVERY RA_G1_PROTOCOL RA_G1_MONITOR_INCOMPLETE RA_G1_READ_LIMIT RA_G1_COUNTER_LIMIT RA_G1_SHARED_MARGIN RA_G1_WRITE_LIMIT RA_G1_SOURCE_CHANGED RA_G1_SOURCE_INDEX_UNSUPPORTED RA_G1_AUTHORITY_CHANGED RA_G1_ORIGINAL_CHANGED RA_G1_REVIEW_REQUIRED RA_G1_REVIEW_TIMEOUT RA_G1_BOOTSTRAP_BINDING RA_G1_BOOTSTRAP_REVIEW_REQUIRED RA_G1_EVIDENCE_CHANGED RA_G1_EXACT_INPUT_REVIEW_REQUIRED RA_G1_CHILD_FAILED RA_G1_DIAGNOSTIC_INCOMPLETE RA_G1_HANDOFF RA_G1_ADMIN_SCOPE RA_G1_PROCESS_SCOPE RA_G1_NATIVE_DENIAL_REQUIRED RA_G1_PROJECT_DISTRIBUTION_INCOMPATIBLE RA_G1_PROJECT_DISTRIBUTION_REQUIRED".split()
)


def safe_failure(error, run=None):
    code = "UNKNOWN"
    family = "UNKNOWN"
    number = None
    # Preserve genuine static pipeline guard codes without importing the
    # pipeline during an early/bootstrap failure. Exact types exclude arbitrary
    # ValueError/RuntimeError subclasses and their unconstrained messages.
    loaded_contract = sys.modules.get(
        "safe_geocoding_pipeline.preprocessing.stages.s12_retrieval_contract"
    )
    stage12_error = (
        None
        if loaded_contract is None
        else loaded_contract.__dict__.get("Stage12Error")
    )
    if (
        (type(error) is RuntimeError or type(error) is stage12_error)
        and len(error.args) == 1
        and type(error.args[0]) is str
        and error.args[0] in SAFE_CODES
    ):
        family = "CONTRACT_OR_GUARD"
        code = error.args[0]
    elif isinstance(error, PermissionError):
        family = "ACCESS_DENIED"
    elif isinstance(error, TimeoutError):
        family = "TIMEOUT"
    elif isinstance(error, OSError):
        family = "OS_ERROR"
        if type(error.errno) is int and 0 <= error.errno <= 4095:
            number = error.errno
    if run is not None and run.poisoned:
        family = "WRITE_UNCERTAIN"
    trace = None if run is None else getattr(run, "startup_trace", None)
    primary_reader = getattr(trace, "monitor_primary", None)
    primary = primary_reader() if callable(primary_reader) else None
    if primary is not None:
        family, code, number = primary["family"], primary["code"], primary["errno"]
    value = dict(
        schema_version="stage12_ra_g1_allocation_failure_v1",
        status="INCOMPLETE",
        family=family,
        code=code,
        errno=number,
        at_mono_ns=time.monotonic_ns() if primary is None else primary["at_mono_ns"],
        counter_prefix=None if run is None else run.counter_prefix(),
        writer="UNKNOWN"
        if run is None
        else ("POISONED" if run.poisoned else "HEALTHY"),
    )
    if run is not None:
        if run.first_failure is None:
            run.first_failure = value
        return run.first_failure
    return value


def main():
    PROCESS_TRACE("MAIN_ENTER")
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["ready", "collect", "bind", "verify"])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--selection-sha256", required=True)
    args = parser.parse_args()
    PROCESS_TRACE.set_controller_command(args.command)
    bootstrap_counts = {"checks": 0, "read_calls": 0, "read_bytes": 0}

    def bootstrap_check():
        bootstrap_counts["checks"] += 1
        need(time.monotonic_ns() - ROLE_ENTRY_NS < 120 * 10**9, "RA_G1_DEADLINE")

    def bootstrap_read(calls, size):
        bootstrap_counts["read_calls"] += calls
        bootstrap_counts["read_bytes"] += size

    raw = read(args.selection, check=bootstrap_check, read_charge=bootstrap_read)
    need(
        hashlib.sha256(raw).hexdigest() == args.selection_sha256,
        "RA_G1_SELECTION_BINDING",
    )
    parsed = parse(raw)
    # The launcher executes this exact pinned file, not an installed project or
    # a package path supplied by an unvalidated selection.
    own_checkout = Path(__file__).resolve().parents[1]
    need(
        parsed.get("paths", {}).get("source") == str(own_checkout),
        "RA_G1_SOURCE_CHANGED",
    )
    sys.path.insert(0, str(own_checkout / "src"))
    bootstrap_check()
    from importlib.metadata import PackageNotFoundError

    try:
        import safe_geocoding_pipeline as package
    except PackageNotFoundError:
        raise RuntimeError("RA_G1_PROJECT_DISTRIBUTION_REQUIRED") from None
    package_root = own_checkout / "src" / "safe_geocoding_pipeline"
    need(
        package.DISTRIBUTION_NAME == "safe-geocoding-pipeline"
        and package.__version__ == SOURCE_PROJECT_VERSION
        and Path(package.__file__).resolve(strict=True) == package_root / "__init__.py"
        and [Path(value).resolve(strict=True) for value in package.__path__]
        == [package_root],
        "RA_G1_PROJECT_DISTRIBUTION_INCOMPATIBLE",
    )
    bootstrap_check()
    s = validate_selection(parsed)
    epoch = os.environ.get("STAGE12_RA_EPOCH_NS")
    need(epoch is not None and epoch.isdigit(), "RA_G1_EPOCH_REQUIRED")
    install_denials(s, check=bootstrap_check, read_charge=bootstrap_read)
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("RA-G1 allocation controller metadata")
    need(s["version"] == SHARED_LEASE_VERSION, "RA_G1_ACCOUNTING")
    os.umask(0o077)
    run = Run(
        s,
        epoch_ns=int(epoch),
        stage_seconds={"ready": 120, "collect": 120, "bind": 720, "verify": 120}[
            args.command
        ],
        stage=args.command,
    )
    if run.stage != "ready":
        PROCESS_TRACE.reserve_stdout(run)
    run.checks += bootstrap_counts["checks"]
    run.read_calls += bootstrap_counts["read_calls"]
    run.read_bytes += bootstrap_counts["read_bytes"]
    run.check()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    old_soft, old_hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(
        resource.RLIMIT_FSIZE,
        (
            min(16 * 2**20, old_soft)
            if old_soft != resource.RLIM_INFINITY
            else 16 * 2**20,
            old_hard,
        ),
    )
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.alarm(max(1, (run.end - time.monotonic_ns()) // 10**9))
    PROCESS_TRACE("MAIN_SETUP_DONE")
    result = None
    failure = None
    try:
        result = {"ready": ready, "collect": collect, "bind": bind, "verify": verify}[
            args.command
        ](run)
    except BaseException as error:
        PROCESS_TRACE("START_FAILED", error=error)
        failure = safe_failure(error, run)
    finally:
        PROCESS_TRACE("RUN_CLOSE_ENTER")
        try:
            run.close()
            PROCESS_TRACE("RUN_CLOSE_DONE")
        except BaseException as cleanup:
            PROCESS_TRACE("ABORT_FAILED", error=cleanup, cleanup=True)
            if failure is None:
                failure = safe_failure(cleanup, run)
    if failure is not None:
        print(canonical(failure).decode(), end="")
        return 1
    print(canonical(result).decode(), end="")
    if run.stage == "ready":
        run.check()  # The one non-ready success check follows trace emission.
    return 0


def cli_entry():
    """Retain supplementary prefix even when main bootstrap/imports fail."""
    try:
        result = main()
    except BaseException as error:
        PROCESS_TRACE("START_FAILED", error=error)
        print(canonical(safe_failure(error)).decode(), end="")
        result = 1
    PROCESS_TRACE("EXIT_REPORT_ENTER")
    if PROCESS_TRACE.controller_command == "ready" or getattr(PROCESS_TRACE.admin, "stage", None) == "ready":
        return result  # Legacy standalone read-only ready has no metadata output grant.
    try:
        PROCESS_TRACE.emit(sys.stdout)
        if result == 0 and PROCESS_TRACE.admin is not None:
            PROCESS_TRACE.admin.check()  # emission cannot create a late successful return
    except BaseException as error:
        diagnostic_run = PROCESS_TRACE.admin if PROCESS_TRACE.output_reserved else None
        print(canonical(safe_failure(error, diagnostic_run)).decode(), end="")
        return 1
    return result


def verify_administrative_sessions(
    context,
    selected,
    rows,
    returned,
    *,
    check,
    read_charge,
    write_record,
    counter_digest,
    deadline_ns,
    terminal_name="supervisor_terminal.record",
):
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_execution as e,
        s12_ra_g1_monitor as m,
    )

    need(
        terminal_name in ("supervisor_terminal.record", "final_verification.record"),
        "RA_G1_PATH",
    )
    need(
        type(rows) is list
        and 1 <= len(rows) <= 3
        and len({row["role"] for row in rows}) == len(rows),
        "RA_G1_ADMIN_SCOPE",
    )
    root = Path(context["private_paths"]["allocation_root"])
    reports = []
    for row in rows:
        need(
            set(row)
            == {
                "role",
                "phase_id",
                "root",
                "binding_sha256",
                "worker_validation_sha256",
            }
            and row["role"] in e.ADMIN_ROLES
            and row["phase_id"] == e.ADMIN_ROLES[row["role"]]
            and Path(row["root"]) == root / (row["role"].lower() + "_resources"),
            "RA_G1_ADMIN_SCOPE",
        )
        folder = Path(row["root"])
        bound = parse(read(folder / "admin_binding.record", 65536, check, read_charge))
        e.AdministrativePhaseSession.validate_binding(None, bound)
        need(
            digest(bound) == row["binding_sha256"]
            and bound["source_git_sha"] == selected["source_git_sha"]
            and bound["selection_sha256"] == digest(selected)
            and bound["supervisor_context_sha256"] == digest(context)
            and bound["process_pid"] == returned["pid"],
            "RA_G1_ADMIN_SCOPE",
        )
        originals = {
            name: parse(read(folder / (name + ".record"), 8192, check, read_charge))
            for name in (
                "preopening",
                "opener_return",
                "monitor_terminal",
                "worker_validation",
            )
        }
        need(
            digest(originals["worker_validation"]) == row["worker_validation_sha256"]
            and originals["worker_validation"]["first_pass_end_ns"]
            < bound["deadline_mono_ns"],
            "RA_G1_DEADLINE",
        )
        validate_original_phase_times(
            dict(
                phase_id=row["phase_id"],
                phase_start_ns=bound["scope_start_mono_ns"],
                phase_deadline_ns=bound["deadline_mono_ns"],
            ),
            originals,
            selected,
            deadline_ns,
        )
        e.validate_current_supervisor(
            context,
            binding=bound,
            selection=selected,
            evidence_root=context["private_paths"]["resource_evidence_root"],
            check=check,
            read_charge=read_charge,
        )
        protocol = m.reopen_phase_protocol(
            binding_sha256=digest(bound),
            selection_sha256=digest(selected),
            phase_id=row["phase_id"],
            closure=originals["preopening"],
            opener_return=originals["opener_return"],
            monitor_terminal=originals["monitor_terminal"],
            deadline_ns=deadline_ns,
            check=check,
        )
        seed = digest(
            dict(
                schema_version="stage12_resource_monitor_seed_ra_g1_v1",
                binding_sha256=digest(bound),
                selection_sha256=digest(selected),
                phase_id=row["phase_id"],
            )
        )

        def raw_original(identity_value):
            return m.read_original_observation(
                folder / "originals" / (identity_value + ".record"),
                expected_sha256=identity_value,
                check=check,
                charge_read=read_charge,
            )

        def persist(value, guard):
            guard()
            write_record(folder / terminal_name, value)
            actual = parse(read(folder / terminal_name, 8192, check, read_charge))
            guard()
            return actual

        reports.append(
            m.verify_tail(
                protocol=protocol,
                monitor_path=folder / "observations.bin",
                selected=selected,
                seed_sha256=seed,
                child_result={
                    key: returned[key]
                    for key in ("pid", "wait_status", "acquired_mono_ns")
                },
                genuine_wait_status=returned["wait_status"],
                expected_child_pid=returned["pid"],
                current_counter_sha256=counter_digest,
                persist_terminal=persist,
                original_observation_reader=raw_original,
                worker_validation=originals["worker_validation"],
                charge_read=read_charge,
            )
        )
    return reports


def load_verified_handoff(
    context,
    selected,
    *,
    check,
    read_charge,
    deadline_ns,
    stage="bind",
    write_record=None,
    counter_digest=None,
    defer=True,
):
    """Minimal original prefix now; mandatory fresh full proofs before DATA.

    Returned source counters are carried prefixes: caller adds them to its own
    already observed bootstrap reads, never overwrites those deltas. Resource
    usage seeds B controls before any new charge. The closure verifies originals
    once and persists genuine predecessor terminal records under caller guards.
    """
    value, totals, identity_value, returned = load_handoff_prefix(
        context, selected, stage=stage, check=check, read_charge=read_charge
    )
    usage = totals["monitor_usage"]
    files = usage["creations"] - usage["directories"]
    need(files >= 0, "RA_G1_HANDOFF")
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m

    invocations = {role: 0 for role in m.ROLES}
    invocations.update(ADMIN_FILE=files)
    initial = dict(
        invocations=invocations,
        bytes=usage["bytes"],
        creations=usage["creations"],
        monitor_rows=usage["rows"],
        monitor_bytes=usage["bytes"],
    )
    called = [False]

    def verify():
        need(
            not called[0] and callable(write_record) and callable(counter_digest),
            "RA_G1_HANDOFF",
        )
        called[0] = True
        return verify_administrative_sessions(
            context,
            selected,
            value["administrative_sessions"],
            returned,
            check=check,
            read_charge=read_charge,
            write_record=write_record,
            counter_digest=counter_digest,
            deadline_ns=deadline_ns,
        )

    result = dict(
        handoff_sha256=identity_value,
        initial_usage=initial,
        source_counter_prefix=dict(
            source_read_calls=totals["source_read_calls"],
            source_read_bytes=totals["source_read_bytes"],
            identity_checks=totals["checks"],
        ),
        administrative_metadata=totals["metadata"],
        verify_before_data=verify,
        original=value,
    )
    if not defer:
        result["terminal_records"] = verify()
    return result


def descriptor(version=VERSION):
    """Closed successor selection; no instance, authority or capacity is issued."""
    need(version in (VERSION, BOOTSTRAP_VERSION, SHARED_LEASE_VERSION))
    value = dict(
        descriptor_version=version,
        scope=SCOPE,
        limits=LIMITS,
        source_fields=["path", "bytes", "sha256"],
        accounting_inventory="RECOMPUTE_FROM_EXACT_SOURCE_BACKEND_AND_FINITE_GRAPH",
        authority_roles=[
            "adoption",
            "project_approval",
            "software_review",
            "resource_review",
        ],
        stages=["ready", "collect", "bind", "verify"],
        required_existing_project_distribution={
            "name": "safe-geocoding-pipeline",
            "version": SOURCE_PROJECT_VERSION,
            "origin": "EXISTING_RUNTIME_METADATA_NOT_PROJECT_CODE_IDENTITY",
            "package_code": "EXACT_PINNED_CHECKOUT_SRC_ONLY",
        },
        final_verifier="GUARDED_ADMINISTRATIVE_SUFFIX_NOT_PERIODIC_MONITORING",
        containment_claim="NOT_ESTABLISHED",
        physical_capacity_claim="NOT_RESERVED_OR_PROVEN",
    )
    if version == SHARED_LEASE_VERSION:
        value.update(runtime_diagnostic_version=DIAGNOSTIC_VERSION, diagnostic_bytes=8192,
            required_accounting_inventory="stage12_ra_g1_shared_lease_accounting_inventory_v1",
            bootstrap_proof_record_count=3)
    return value


if __name__ == "__main__":
    raise SystemExit(cli_entry())

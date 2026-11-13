"""Bounded, secret-safe supplementary public failure diagnostics.

Not controller evidence or authority. A caller may persist this outside the
campaign after an uncertain writer; it cannot repair closure or exact counts.
"""

from __future__ import annotations

import hashlib
import types
import threading
import time
from . import s12_retrieval_contract as c
from . import s12_public_recovery as recovery

TAGS = frozenset(
    (
        "UNCLASSIFIED",
        "PREFLIGHT",
        "READINESS",
        "ADMISSION",
        "DISPATCH",
        "CAPTURE_FINALIZE",
        "WRITER_ACTION",
        "WRITER_WAIT",
        "SAMPLER",
        "COMPARISON",
        "REPORT",
        "RECONCILIATION",
        "CLOSURE",
        "CLEANUP",
        "RUNTIME_REOPEN",
        "RUNTIME",
    )
)
CODES = frozenset(
    (
        "S12_PUBLIC_WINDOW_CLOSED",
        "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
        "S12_PUBLIC_OPERATIONS_INVALID",
        "S12_PRIVATE_FILE_INVALID",
        "S12_CAPTURE_INCOMPLETE",
        "RESPONSE_CONTRACT_INVALID",
        "S12_METADATA_INVALID",
        "RETRY_BUDGET_EXHAUSTED",
        "SECRET_ECHO_DETECTED",
        "S12_PUBLIC_AUTHORITY_CHANGED",
        "S12_PUBLIC_AUTHORITY_SCOPE",
        "PUBLIC_PROBE_EXECUTABLE_MISMATCH",
        "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
    )
)


CLOSURE_GUARDS = frozenset(("CAPTURE_CUMULATIVE", "DIAGNOSTIC_PHASE", "GLOBAL_TASK", "WHOLE_TASK_RESOURCE"))

CLOSURE_STAGES = frozenset((
    "STORAGE_RECONCILE", "SAMPLING_VERIFY", "SNAPSHOT_PRECHECK",
    "PREPARE_ORIGINAL_VERIFY", "PREPARE_EVIDENCE", "PREPARE_STORAGE",
    "FRESH_FINISH", "SNAPSHOT_PERSIST", "REVALIDATE_FRESH",
    "REVALIDATE_ORIGINAL_VERIFY", "REVALIDATE_EVIDENCE", "REVALIDATE_STORAGE",
    "SNAPSHOT_SEAL", "ORIGINAL_WORK_VERIFY", "ORIGINAL_RECEIPT_VERIFY",
    "ORIGINAL_REPLAY", "CAMPAIGN_REPORT", "CAMPAIGN_PERSIST", "WRITER_RELEASE",
    "SAMPLING_INSPECTION", "T3_PHASE_CLOSE", "T3_CLOSE", "NORMAL_OPEN",
    "NEGATIVE_OPEN", "RUNTIME_RECHECK", "T3_REREAD", "WHOLE_OPEN",
))


def classify(error):
    # Never stringify arbitrary objects, subclasses, messages or unsafe content.
    family, code, number = "UNCLASSIFIED", None, None
    if isinstance(error, recovery.FinalizationExpired):
        family = "CUMULATIVE_DEADLINE"
    elif type(error) is c.Stage12Error:
        family = "STAGE12"
        if (
            len(error.args) == 1
            and type(error.args[0]) is str
            and error.args[0] in CODES
        ):
            code = error.args[0]
    elif isinstance(error, TimeoutError):
        family = "TIMEOUT"
    elif isinstance(error, OSError):
        family = "OS_ERROR"
        if type(error.errno) is int and 0 <= error.errno <= 4095:
            number = error.errno
    elif type(error) is KeyboardInterrupt:
        family = "INTERRUPTED"
    return family, code, number


RESOURCE_STAGES = frozenset((
    "CALLER_CHECK", "CHECK", "STATE", "START_ACK", "BARRIER", "FREEZE", "PREFIX",
    "PREOPEN_RECORD", "PREOPEN_PERSIST", "PREOPEN_BIND", "PREFIX_REREAD",
    "DATA_OPENER", "OPENER_RECORD", "MONITOR_FINISH", "TERMINAL_RECORD",
    "WORKER_REREAD", "WORKER_RECORD", "COMPLETE_CHECK",
))
RESOURCE_CODES = CODES | frozenset((
    "UNKNOWN", "ACCESS_DENIED", "RA_G1_MONITOR_GAP", "RA_G1_MONITOR_THRESHOLD",
    "RA_G1_REQUIRED_READING", "RA_G1_DEADLINE", "RA_G1_WRITE_UNCERTAIN",
    "RA_G1_ORIGINAL_CHANGED", "RA_G1_NATIVE_DISCOVERY", "RA_G1_PROTOCOL",
    "RA_G1_PROCESS_SCOPE", "RA_G1_READ_LIMIT", "RA_G1_COUNTER_LIMIT",
    "RA_G1_MONITOR_INCOMPLETE", "RA_G1_BOOTSTRAP_REQUIRED", "RA_G1_BOOTSTRAP_EVIDENCE",
    "RA_G1_BOOTSTRAP_LIMIT", "RA_G1_PRECHARGE", "RA_G1_SHARED_MARGIN",
    "RA_G1_PATH", "RA_G1_RECORD_LIMIT", "RA_G1_SELECTION_BINDING",
    "WF_AP2_SCRATCH_LIMIT", "WF_AP2_SCRATCH_REENTRANT",
))
RESOURCE_PROGRESS = frozenset((
    "IDLE", "CHECK", "OBSERVER", "COVERAGE", "PACK", "APPEND", "WAIT_ACK",
    "POST_ACK_CHECK", "PUBLISH", "ORIGINAL_WRITE", "ORIGINAL_FSYNC",
    "ORIGINAL_READBACK", "CODEC_WRITE", "CODEC_FSYNC", "CODEC_READBACK",
    "ACK", "CLOSED", "BARRIER",
))


def _resource_uint(value):
    return value if type(value) is int and 0 <= value < 2**64 else None


def _resource_tag(value, allowed):
    return value if type(value) is str and value in allowed else None


def _resource_fault(error):
    family, code, number = classify(error)
    if type(error) is c.Stage12Error and len(error.args) == 1:
        code = _resource_tag(error.args[0], RESOURCE_CODES)
    return dict(family=family, code=code, errno=number)


def _resource_copy(row):
    # Only internally constructed fixed-schema dictionaries reach this copier.
    return {key: _resource_copy(value) if type(value) is dict else value
            for key, value in row.items()} if row is not None else None


def _resource_monitor_state(monitor):
    # Copy only the existing owner's fixed, public scalar schema. No arbitrary
    # object/message/path/trace is retained, including in failure fallbacks.
    data = monitor.diagnostic_snapshot()
    def fault(row):
        if type(row) is not dict:
            return None
        return dict(family=_resource_tag(row.get("family"), ("STAGE12_ERROR", "OS_ERROR", "UNKNOWN")),
                    code=_resource_tag(row.get("code"), RESOURCE_CODES),
                    errno=(row.get("errno") if type(row.get("errno")) is int and 0 <= row.get("errno") <= 4095 else None), mono_ns=_resource_uint(row.get("mono_ns")),
                    source=_resource_tag(row.get("source"), ("WRITER", "MONITOR")),
                    stage=_resource_tag(row.get("stage"), RESOURCE_PROGRESS))
    result = dict(phase_id=_resource_uint(data.get("phase_id")),
                  monitor_failure=_resource_tag(data.get("monitor_failure"), RESOURCE_CODES),
                  first_primary=fault(data.get("first_primary")))
    for section, numbers, tags, flags in (
        ("acquisition", ("enter_mono_ns", "exit_mono_ns"),
         {"kind": ("START", "PERIODIC", "FINAL"), "stage": RESOURCE_PROGRESS}, ()),
        ("published", ("seq", "enter_mono_ns", "exit_mono_ns", "ack_mono_ns"), {}, ()),
        ("writer", ("rows", "acked", "ack_ns", "current_seq"), {"stage": RESOURCE_PROGRESS},
         ("poisoned", "closing", "released", "thread_alive")),
    ):
        row = data.get(section)
        if type(row) is not dict:
            result[section] = None
            continue
        selected = {key: _resource_uint(row.get(key)) for key in numbers}
        selected.update((key, _resource_tag(row.get(key), allowed)) for key, allowed in tags.items())
        selected.update((key, row.get(key) if type(row.get(key)) is bool else None) for key in flags)
        if section == "writer":
            selected["first_failure"] = fault(row.get("first_failure"))
        result[section] = selected
    return result



OBSERVER_STAGES = (
    "KERNEL_LEASE_WAIT", "ADMITTED_PROCESS", "KERNEL_READ_PARSE", "NATIVE_PATHS",
    "STATVFS", "COUNTERS", "ORIGINAL_VALIDATE", "RETAIN_DIGEST",
)
OBSERVER_ROWS = OBSERVER_STAGES + ("OUTER_UNATTRIBUTED",)
OBSERVER_SLOW_NS = 1_000_000_000


def _observer_rows():
    return {stage: dict(count=0, wall_ns=0, thread_cpu_ns=0, maximum_wall_ns=0,
                        maximum_thread_cpu_ns=0, failures=0) for stage in OBSERVER_ROWS}


def _observer_sample(owner):
    # These supplementary clocks never consume an enforcement clock callback.
    wall = cpu = None
    try:
        wall = _resource_uint(time.monotonic_ns())
        cpu_clock = getattr(time, "thread_time_ns", None)
        cpu = _resource_uint(cpu_clock()) if callable(cpu_clock) else None
    except BaseException:
        owner.observer_fault()
    if wall is None or cpu is None:
        owner.observer_fault()
        with owner.lock:
            owner.observer_wall_complete &= wall is not None
            owner.observer_cpu_complete &= cpu is not None
    return wall, cpu


def _observer_delta(start, end):
    return end - start if type(start) is int and type(end) is int and end >= start else None



def _observer_add(owner, row, key, amount):
    # Caller holds the existing owner lock; overflow is explicit uncertainty.
    value = row[key] + amount
    if value > 2**64 - 1:
        owner.observer_faults = min(2**64 - 1, owner.observer_faults + 1)
    row[key] = min(2**64 - 1, value)


class _ObserverStage:
    """One of eight fixed LinuxObserver boundaries; never holds a work lock."""

    def __init__(self, call, stage):
        self.call, self.stage, self.done = call, stage, False
        self.start = (None, None)

    def __enter__(self):
        if self.call.owner is not None:
            self.start = _observer_sample(self.call.owner)
            self.call.boundary(self.stage, self.start, completed=False)
        return self

    def complete(self, error=None):
        if self.done or self.call.owner is None:
            return
        self.done = True
        try:
            ended = _observer_sample(self.call.owner)
            self.call.stage_complete(self.stage, self.start, ended, error)
        except BaseException:
            self.call.owner.observer_fault()

    def __exit__(self, error_type, error, traceback):
        self.complete(error)
        return False


class _ObserverCall:
    """Fixed supplementary state for one real observer invocation, not a profiler."""

    def __init__(self, owner, kind, phase_id):
        self.owner = owner if type(owner) is Failures and owner.observer_enabled else None
        self.record = None
        if self.owner is None:
            return
        try:
            started = _observer_sample(self.owner)
            with self.owner.lock:
                if self.owner.observer_calls == 2**64 - 1:
                    self.owner.observer_faults = min(2**64 - 1, self.owner.observer_faults + 1)
                else:
                    self.owner.observer_calls += 1
                self.record = dict(
                    phase_id=_resource_uint(phase_id), kind=_resource_tag(kind, ("START", "PERIODIC", "FINAL")),
                    observer_call_ordinal=self.owner.observer_calls,
                    start_wall_ns=started[0], start_thread_cpu_ns=started[1],
                    end_wall_ns=None, end_thread_cpu_ns=None, wall_ns=None, thread_cpu_ns=None,
                    returned=False, failure=None, active_stage=None,
                    last_entered=None, last_completed=None, stages=_observer_rows())
                self.owner.observer_last = self.record
        except BaseException:
            self.owner.observer_fault()
            self.owner = None

    def __enter__(self):
        return self

    def stage(self, stage):
        if type(stage) is not str or stage not in OBSERVER_STAGES:
            if self.owner is not None:
                self.owner.observer_fault()
            return _ObserverStage(_ObserverCall(None, None, None), None)
        return _ObserverStage(self, stage)

    def boundary(self, stage, sample, *, completed):
        try:
            row = dict(stage=stage, wall_ns=sample[0], thread_cpu_ns=sample[1])
            with self.owner.lock:
                self.record["last_completed" if completed else "last_entered"] = row
                self.record["active_stage"] = None if completed else stage
        except BaseException:
            self.owner.observer_fault()

    def stage_complete(self, stage, started, ended, error):
        wall, cpu = (_observer_delta(started[0], ended[0]),
                     _observer_delta(started[1], ended[1]))
        with self.owner.lock:
            for rows in (self.record["stages"], self.owner.observer_totals):
                row = rows[stage]
                _observer_add(self.owner, row, "count", 1)
                _observer_add(self.owner, row, "failures", int(error is not None))
                if wall is not None:
                    _observer_add(self.owner, row, "wall_ns", wall)
                    row["maximum_wall_ns"] = max(row["maximum_wall_ns"], wall)
                if cpu is not None:
                    _observer_add(self.owner, row, "thread_cpu_ns", cpu)
                    row["maximum_thread_cpu_ns"] = max(row["maximum_thread_cpu_ns"], cpu)
        if stage != "OUTER_UNATTRIBUTED":
            self.boundary(stage, ended, completed=True)
        if error is not None:
            self.failed(error, stage, ended, "FIRST_STAGE_FAILURE_BEFORE_CLEANUP")

    def failed(self, error, stage, sample, point):
        try:
            fault = dict(**_resource_fault(error), stage=stage,
                         wall_ns=sample[0], thread_cpu_ns=sample[1])
            with self.owner.lock:
                if self.record["failure"] is None:
                    self.record["failure"] = fault
                if self.owner.observer_first_failed is None:
                    retained = _resource_copy(self.record)
                    retained["snapshot_point"] = point
                    retained["observed_end_wall_ns"] = sample[0]
                    retained["observed_end_thread_cpu_ns"] = sample[1]
                    self.owner.observer_first_failed = retained
        except BaseException:
            self.owner.observer_fault()

    def __exit__(self, error_type, error, traceback):
        if self.owner is None:
            return False
        try:
            ended = _observer_sample(self.owner)
            wall = _observer_delta(self.record["start_wall_ns"], ended[0])
            cpu = _observer_delta(self.record["start_thread_cpu_ns"], ended[1])
            with self.owner.lock:
                self.record.update(end_wall_ns=ended[0], end_thread_cpu_ns=ended[1],
                                   wall_ns=wall, thread_cpu_ns=cpu, returned=error is None)
                # Coarse stages do not overlap. Setup, release, result construction
                # and instrumentation gaps remain explicitly unattributed.
                stage_wall = sum(self.record["stages"][name]["wall_ns"] for name in OBSERVER_STAGES)
                stage_cpu = sum(self.record["stages"][name]["thread_cpu_ns"] for name in OBSERVER_STAGES)
            residual = (_observer_delta(stage_wall, wall), _observer_delta(stage_cpu, cpu))
            self.stage_complete("OUTER_UNATTRIBUTED", (0, 0), residual, None)
            if error is not None:
                self.failed(error, self.record["active_stage"] or "OUTER_UNATTRIBUTED", ended, "CALL_EXIT_AFTER_CLEANUP")
            with self.owner.lock:
                if wall is not None and wall > OBSERVER_SLOW_NS and self.owner.observer_first_slow is None:
                    self.owner.observer_first_slow = _resource_copy(self.record)
                    self.owner.observer_first_slow["snapshot_point"] = "CALL_EXIT_AFTER_CLEANUP"
        except BaseException:
            self.owner.observer_fault()
        return False


def observer_acquisition(owner, *, kind, phase_id):
    return _ObserverCall(owner, kind, phase_id)



# Explicit opt-in metadata only; none of these records can release a runtime gate.
FOREGROUND_VERSION = "stage12_foreground_first_failure_discriminator_v1"
FOREGROUND_MAX_FRAMES = 4
FOREGROUND_MAX_TRACEBACK_VISITS = 32
FOREGROUND_MAX_CODES = 4096
FOREGROUND_MAX_NODES = 32768
FOREGROUND_MAX_POSITIONS = 32768
FOREGROUND_MAX_LINE_ENTRIES = 262144
FOREGROUND_MAX_SOURCE_BYTES = 1048576
FOREGROUND_MODULES = (
    ("DIAGNOSTIC", "scripts/stage12_ra_g1_diagnostic.py"),
    ("PUBLIC_RESPONSE", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_response.py"),
    ("PUBLIC_RUNTIME", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_runtime.py"),
    ("PUBLIC_AUTHORITY", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_public.py"),
    ("PUBLIC_SAMPLING", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_sampling.py"),
    ("PUBLIC_SCHEDULER", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_scheduler.py"),
    ("PUBLIC_OPERATIONS", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_operations.py"),
    ("PUBLIC_RECOVERY", "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_recovery.py"),
    ("RETRIEVAL_GUARD", "src/safe_geocoding_pipeline/preprocessing/stages/s12_retrieval_contract.py"),
    ("RESPONSE_GUARD", "src/safe_geocoding_pipeline/preprocessing/stages/s12_response.py"),
    ("RA_ASSURANCE", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_assurance.py"),
    ("RA_CONTRACT", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_contract.py"),
    ("PROBE_CLI", "src/safe_geocoding_pipeline/preprocessing/stage12_probe_cli.py"),
    ("RA_EXECUTION", "src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_execution.py"),
)
_FOREGROUND_CLASSES = (
    (RuntimeError, "RUNTIME_ERROR"), (ValueError, "VALUE_ERROR"),
    (TypeError, "TYPE_ERROR"), (KeyError, "KEY_ERROR"),
    (IndexError, "INDEX_ERROR"), (AttributeError, "ATTRIBUTE_ERROR"),
    (AssertionError, "ASSERTION_ERROR"), (OSError, "OS_ERROR"),
    (PermissionError, "PERMISSION_ERROR"), (FileNotFoundError, "FILE_NOT_FOUND"),
    (TimeoutError, "TIMEOUT"), (MemoryError, "MEMORY_ERROR"),
    (OverflowError, "OVERFLOW_ERROR"), (KeyboardInterrupt, "INTERRUPTED"),
    (c.Stage12Error, "STAGE12_ERROR"),
    (recovery.FinalizationExpired, "FINALIZATION_EXPIRED"),
)


class FirstFailureDescriptor:
    """Bounded code identity catalogue; retains no frame, error or file contents."""

    def __init__(self):
        self._codes = types.MappingProxyType({})
        self._classes = _FOREGROUND_CLASSES
        self.source_map_sha256 = None
        self.preparation_uncertain = True

    def capture(self, error):
        tb = frame = code = row = None
        try:
            kind = next((label for cls, label in self._classes
                         if type(error) is cls), "UNKNOWN")
            frames = []
            visits = mapped = unmapped = 0
            trimmed = False
            tb = BaseException.__dict__["__traceback__"].__get__(error, BaseException)
            unavailable = tb is None
            while tb is not None and visits < FOREGROUND_MAX_TRACEBACK_VISITS:
                visits += 1
                frame = tb.tb_frame
                code = frame.f_code
                row = self._codes.get(id(code))
                line = tb.tb_lineno
                # A filename supplied by an exception/code object is never an ID.
                if row is not None and row[0] is code and line in row[4]:
                    mapped += 1
                    if len(frames) == FOREGROUND_MAX_FRAMES:
                        del frames[0]
                        trimmed = True
                    frames.append(dict(module=row[1], function=row[2],
                                       source_sha256=row[3], line=line))
                else:
                    unmapped += 1
                tb = tb.tb_next
            return dict(exception_class=kind, frames=frames, visited=visits,
                        mapped=mapped, unmapped=unmapped,
                        traceback_unavailable=unavailable,
                        traversal_truncated=tb is not None,
                        leaf_frames_truncated=trimmed,
                        retention_uncertain=self.preparation_uncertain)
        except BaseException:
            return dict(exception_class="UNKNOWN", frames=[], visited=0,
                        mapped=0, unmapped=0, traceback_unavailable=True,
                        traversal_truncated=False, leaf_frames_truncated=False,
                        retention_uncertain=True)
        finally:
            tb = frame = code = row = error = None


def prepare_first_failure_descriptor(specs, source_rows, *, source_root, verify_source):
    """Pin already-loaded modules using the caller's actual original reader.

    verify_source(path, selected_row) must return exact True after the caller's
    bounded streaming hash, complete EOF and fd/path/ancestor checks. No source
    bytes, imports, acceptance cache or filesystem bypass are retained. This may
    run under the existing selected-source read policy. Missing/changed pins make
    supplementary retention uncertain; the scientific source guards still run.
    """
    try:
        if not (type(specs) in (tuple, list) and 1 <= len(specs) <= len(FOREGROUND_MODULES)
                and type(source_rows) is list and 1 <= len(source_rows) <= 2048):
            raise ValueError
        inventory = {row["path"]: row for row in source_rows}
        if len(inventory) != len(source_rows):
            raise ValueError
        allowed = dict(FOREGROUND_MODULES)
        codes, pins, seen = {}, [], set()
        classes = list(_FOREGROUND_CLASSES)
        nodes = positions_seen = line_entries = source_bytes = 0
        for module_id, module in specs:
            if type(module_id) is not str or module_id not in allowed or module_id in seen:
                raise ValueError
            seen.add(module_id)
            if type(module) is not types.ModuleType:
                raise ValueError
            relative = allowed[module_id]
            selected = inventory[relative]
            path = source_root / relative
            if not (type(selected) is dict and type(selected.get("bytes")) is int
                    and 0 <= selected["bytes"] <= FOREGROUND_MAX_SOURCE_BYTES
                    and type(selected.get("sha256")) is str and len(selected["sha256"]) == 64
                    and set(selected["sha256"]) <= set("0123456789abcdef")):
                raise ValueError
            if str(module.__file__) != str(path):
                raise ValueError
            source_bytes += selected["bytes"]
            if (source_bytes > FOREGROUND_MAX_SOURCE_BYTES
                    or verify_source(path, selected) is not True):
                raise ValueError
            namespace = vars(module)
            if module_id == "PUBLIC_SAMPLING":
                failure_class = namespace.get("SamplingFailure")
                if (type(failure_class) is type and issubclass(failure_class, RuntimeError)
                        and failure_class.__name__ == "SamplingFailure"
                        and failure_class.__module__ == module.__name__):
                    classes.append((failure_class, "SAMPLING_FAILURE"))
            pending = []
            for value in namespace.values():
                nodes += 1
                if nodes > FOREGROUND_MAX_NODES:
                    raise ValueError
                members = (value,) if type(value) is types.FunctionType else ()
                if type(value) is type and value.__module__ == module.__name__:
                    if len(vars(value)) > FOREGROUND_MAX_NODES:
                        raise ValueError
                    members = tuple(vars(value).values())
                for member in members:
                    nodes += 1
                    if nodes > FOREGROUND_MAX_NODES:
                        raise ValueError
                    if type(member) in (staticmethod, classmethod):
                        member = member.__func__
                    functions = ((member,) if type(member) is types.FunctionType else
                                 tuple(f for f in (member.fget, member.fset, member.fdel)
                                       if type(f) is types.FunctionType)
                                 if type(member) is property else ())
                    for function in functions:
                        if function.__globals__ is namespace:
                            if len(pending) >= FOREGROUND_MAX_CODES:
                                raise ValueError
                            pending.append(function.__code__)
            while pending:
                code = pending.pop()
                nodes += 1
                if nodes > FOREGROUND_MAX_NODES:
                    raise ValueError
                if id(code) in codes or code.co_filename != str(path):
                    continue
                name = code.co_qualname
                if (len(codes) >= FOREGROUND_MAX_CODES or not 1 <= len(name) <= 128
                        or not name.isascii()
                        or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.<>" for ch in name)):
                    raise ValueError
                selected_lines = set()
                line_iterator = iter(code.co_lines())
                while True:
                    # Count iterator/EOF attempts before the call, not afterward.
                    if line_entries >= FOREGROUND_MAX_LINE_ENTRIES:
                        raise ValueError
                    line_entries += 1
                    try:
                        _, _, line = next(line_iterator)
                    except StopIteration:
                        break
                    if type(line) is int and 1 <= line < 2**32 and line not in selected_lines:
                        if positions_seen + len(selected_lines) >= FOREGROUND_MAX_POSITIONS:
                            raise ValueError
                        selected_lines.add(line)
                lines = frozenset(selected_lines)
                positions_seen += len(lines)
                if not lines or positions_seen > FOREGROUND_MAX_POSITIONS:
                    raise ValueError
                codes[id(code)] = (code, module_id, name, selected["sha256"], lines)
                if len(code.co_consts) > FOREGROUND_MAX_NODES - nodes:
                    raise ValueError
                for value in code.co_consts:
                    nodes += 1
                    if type(value) is types.CodeType:
                        if len(pending) >= FOREGROUND_MAX_CODES:
                            raise ValueError
                        pending.append(value)
            pins.append((module_id, selected["sha256"]))
        if not codes:
            raise ValueError
        digest = hashlib.sha256(repr(sorted(pins)).encode("ascii")).hexdigest()
        prepared = FirstFailureDescriptor()
        prepared._codes = types.MappingProxyType(codes)
        prepared._classes = tuple(classes)
        prepared.source_map_sha256 = digest
        prepared.preparation_uncertain = False
        return prepared
    except BaseException:
        return FirstFailureDescriptor()


SAMPLING_FAULT_VERSION = "stage12_sampling_first_fault_discriminator_v1"
_SAMPLING_CODES = frozenset("ACQUISITION_GAP OBSERVATION_COUNT_LIMIT OBSERVATION_BYTE_LIMIT OBSERVATION_EVENT_LIMIT OBSERVATION_STORAGE_LIMIT ACK_AGE_LIMIT ACQUISITION_FAILED CLOCK_INVALID OWNER_FAILED SOURCE_CHANGED WRITE_UNCERTAIN READBACK_FAILED ACK_UNCERTAIN DRAIN_EXPIRED MISSING_TERMINAL SCHEMA_INCOMPATIBLE ORDER_INVALID".split())
_SAMPLING_TAGS = {
    "code": _SAMPLING_CODES,
    "stage": frozenset(("ACQUIRE", "RESERVE", "APPEND", "ACK", "WITNESS", "DRAIN", "UNAVAILABLE")),
    "predicate_origin": frozenset(("ACQUISITION_INTERVAL", "HEALTH_FRESHNESS", "HEALTH_CLOCK_ORDER", "UNAVAILABLE")),
    "caller_context": frozenset(("ACQUIRE", "OWNER", "SERVICE", "CLOSE", "COORDINATOR_SNAPSHOT", "UNSPECIFIED")),
    "operands_status": frozenset(("AVAILABLE", "PARTIAL", "UNAVAILABLE")),
}
_SAMPLING_NUMBERS = ("previous_observed_mono_ns", "candidate_observed_mono_ns",
                     "health_time_mono_ns", "check_mono_ns", "reserved_seq")


def _sampling_fault_copy(row):
    keys = {"version", "bound_ns", *_SAMPLING_TAGS, *_SAMPLING_NUMBERS}
    valid = (type(row) is dict and len(row) == len(keys)
             and all(type(key) is str and len(key) <= 64 for key in row)
             and set(row) == keys)
    data = row if valid else {}
    result = {"version": SAMPLING_FAULT_VERSION}
    version = data.get("version")
    uncertain = not valid or type(version) is not str or version != SAMPLING_FAULT_VERSION
    for key, allowed in _SAMPLING_TAGS.items():
        value = data.get(key)
        result[key] = value if type(value) is str and len(value) <= 64 and value in allowed else None
        uncertain |= result[key] is None
    for key in _SAMPLING_NUMBERS:
        value = data.get(key)
        result[key] = _resource_uint(value)
        uncertain |= value is not None and result[key] is None
    if result["reserved_seq"] == 0:
        result["reserved_seq"] = None
    bound = data.get("bound_ns")
    result["bound_ns"] = bound if type(bound) is int and bound == 100000000 else None
    uncertain |= result["bound_ns"] is None
    return result, uncertain


class Failures:
    """Two fixed records plus counters; first initiating failure never replaced."""

    def __init__(self, clock, *, closure=False, observer=False, first_failure_descriptor=None, sampling=False):
        self.clock = clock
        self.lock = threading.Lock()
        self.first = None
        self.secondary = None
        self.secondary_count = 0
        self.response_rejection = None
        self.foreground_enabled = first_failure_descriptor is not None
        self.foreground_descriptor = (first_failure_descriptor
            if type(first_failure_descriptor) is FirstFailureDescriptor else None)
        self.foreground_first = None
        self.foreground_faults = int(self.foreground_enabled and self.foreground_descriptor is None)
        self.sampling_enabled = sampling is True
        self.sampling_first = None
        self.sampling_faults = 0
        # Opt-in supplementary successor: no historical/default snapshot change.
        self.closure_enabled = closure is True
        self.closure_entered = None
        self.closure_completed = None
        self.closure_first = None
        self.closure_faults = 0
        self.closure_ordinal = 0
        self.closure_deadline_ordinal = 0
        self._closure_deadline = None
        self._closure_deadline_ns = None
        self.resource_entered = self.resource_completed = None
        self.resource_first = self.resource_cleanup = None
        self.resource_cleanup_count = 0
        self.observer_enabled = observer is True
        self.observer_wall_complete = self.observer_cpu_complete = True
        self.observer_calls = self.observer_faults = 0
        self.observer_totals = _observer_rows() if self.observer_enabled else None
        self.observer_last = self.observer_first_failed = self.observer_first_slow = None

    def observer_fault(self):
        try:
            with self.lock:
                self.observer_faults = min(2**64 - 1, self.observer_faults + 1)
        except BaseException:
            pass

    def closure_fault(self):
        # A supplementary failure can never replace an original exception.
        try:
            with self.lock:
                self.closure_faults = min(2**64 - 1, self.closure_faults + 1)
        except BaseException:
            pass

    def closure_boundary(self, stage, *, completed=False, writer=None, deadline=None, deadline_ns=None, guard=None):
        """Last actual boundary facts, never a claim about the failing callee.

        No I/O, worker, callback replacement or deadline enforcement occurs here.
        A completed inner boundary is not labelled as an active outer operation.
        """
        if not self.closure_enabled:
            return
        try:
            if type(stage) is not str or stage not in CLOSURE_STAGES:
                self.closure_fault()
                return
            now = self.clock.now_ns()
            end = getattr(deadline, "end_ns", None) if deadline is not None else deadline_ns
            if guard is not None and (type(guard) is not str or guard not in CLOSURE_GUARDS):
                self.closure_fault()
                guard = None
            if type(now) is not int or not 0 <= now < 2**64:
                self.closure_fault()
                return
            if type(end) is not int or not 0 < end < 2**64:
                end = None
            failed = writer.failed.is_set() if writer is not None else None
            with self.lock:
                if deadline is not None and deadline is not self._closure_deadline:
                    self.closure_deadline_ordinal += 1
                    self._closure_deadline, self._closure_deadline_ns = deadline, end
                unchanged = deadline is self._closure_deadline and end == self._closure_deadline_ns
                if deadline is not None and not unchanged:
                    self.closure_faults = min(2**64 - 1, self.closure_faults + 1)
                self.closure_ordinal += 1
                row = {"stage": stage, "ordinal": self.closure_ordinal, "mono_ns": now,
                       "deadline_ns": end, "deadline_identity": self.closure_deadline_ordinal if deadline is not None else None,
                       "deadline_identity_unchanged": unchanged if deadline is not None else None,
                       "writer_failed": failed, "guard_kind": guard,
                       "deadline_unit": "MONOTONIC_NS" if end is not None else None,
                       "deadline_identity_source": "ACTUAL_BOUND_OBJECT" if deadline is not None else "ACTUAL_ORIGINAL_SCALAR" if end is not None else "UNAVAILABLE"}
                if completed:
                    self.closure_completed = row
                else:
                    self.closure_entered = row
        except BaseException:
            self.closure_fault()

    def record(
        self, tag, error, *, work_id=None, attempt=None, writer=None, deadline=None
    ):
        family, code, number = classify(error)
        row = {
            "operation": tag if tag in TAGS else "UNCLASSIFIED",
            "family": family,
            "code": code,
            "errno": number,
            "mono_ns": self.clock.now_ns(),
            "work_id": work_id
            if type(work_id) is int and 0 < work_id < 2**64
            else None,
            "attempt": attempt if type(attempt) is int and 1 <= attempt <= 5 else None,
            "writer_failed": writer.failed.is_set() if writer is not None else None,
            "deadline_expired": deadline.remaining_seconds() <= 0 if deadline else None,
        }
        with self.lock:
            if self.first is None:
                self.first = row
                if self.foreground_enabled:
                    try:
                        if self.foreground_descriptor is None:
                            raise ValueError
                        self.foreground_first = self.foreground_descriptor.capture(error)
                    except BaseException:
                        # Cached scalar assignment cannot replace the initiating error.
                        self.foreground_faults = 1
            else:
                self.secondary_count += 1
                if self.secondary is None:
                    self.secondary = row
            if (self.closure_enabled and tag != "CLEANUP"
                    and self.closure_entered is not None and self.closure_first is None):
                self.closure_first = {
                    "failure": row.copy(),
                    "last_entered": self.closure_entered.copy(),
                    "last_completed": self.closure_completed.copy() if self.closure_completed else None,
                }

    def resource_boundary(self, stage, *, completed=False, deadline_ns=None):
        if not self.closure_enabled:
            return
        try:
            if type(stage) is not str or stage not in RESOURCE_STAGES:
                self.closure_fault()
                return
            row = dict(stage=stage, mono_ns=_resource_uint(self.clock.now_ns()),
                       deadline_ns=_resource_uint(deadline_ns), guard="ORIGINAL_RESOURCE_PHASE")
            with self.lock:
                if completed:
                    self.resource_completed = row
                else:
                    self.resource_entered = row
        except BaseException:
            self.closure_fault()

    def resource_failure(self, error, *, session, cleanup=False):
        if not self.closure_enabled:
            return
        try:
            now = self.clock.now_ns()
            row = dict(**_resource_fault(error), mono_ns=_resource_uint(now),
                       deadline_ns=_resource_uint(session.deadline),
                       session_failed=session.failed if type(session.failed) is bool else None,
                       session_completed=session.completed if type(session.completed) is bool else None,
                       protocol_state=_resource_tag(session.protocol.state,
                           ("RUNNING", "DATA_FROZEN", "PREOPEN_READY", "OPENING", "OPEN_RETURNED", "MONITOR_CLOSED", "CHILD_EXITED", "TAIL_VERIFIED", "TERMINAL_SUCCESS", "UNCERTAIN", "INCOMPLETE")),
                       monitor=_resource_monitor_state(session.monitor))
            row["snapshot_completed_mono_ns"] = _resource_uint(self.clock.now_ns())
            with self.lock:
                captured = dict(failure=row,
                    last_entered=self.resource_entered.copy() if self.resource_entered else None,
                    last_completed=self.resource_completed.copy() if self.resource_completed else None)
                if cleanup:
                    self.resource_cleanup_count = min(2**64-1, self.resource_cleanup_count + 1)
                    if self.resource_cleanup is None:
                        self.resource_cleanup = captured
                elif self.resource_first is None:
                    self.resource_first = captured
        except BaseException:
            self.closure_fault()

    def record_sampling_fault(self, row):
        """Copy only the Sampler's first fixed descriptor; never call it back."""
        if not self.sampling_enabled:
            return
        try:
            selected, uncertain = _sampling_fault_copy(row)
            with self.lock:
                if self.sampling_first is None:
                    self.sampling_first = selected
                    self.sampling_faults += int(uncertain)
        except BaseException:
            try:
                with self.lock:
                    self.sampling_faults = 1
            except BaseException:
                pass

    def rejected(self, reason):
        with self.lock:
            if self.response_rejection is None:
                self.response_rejection = (
                    reason
                    if type(reason) is str and reason in CODES
                    else "UNCLASSIFIED"
                )

    def snapshot(self):
        with self.lock:
            result = {
                "version": "stage12_public_failure_diagnostics_v1",
                "scope": "SUPPLEMENTARY_NOT_CLOSURE_EVIDENCE",
                "first_initiating_failure": self.first.copy() if self.first else None,
                "first_secondary_failure": self.secondary.copy()
                if self.secondary
                else None,
                "secondary_observations": self.secondary_count,
                "earlier_response_rejection": self.response_rejection,
            }
            if self.foreground_enabled:
                first = self.foreground_first
                copied = None if first is None else dict(first, frames=[dict(row) for row in first["frames"]])
                descriptor = self.foreground_descriptor
                result["foreground_first_failure"] = dict(
                    version=FOREGROUND_VERSION,
                    source_map_sha256=descriptor.source_map_sha256 if descriptor is not None else None,
                    first_failure=copied, observation_faults=self.foreground_faults,
                    retention_uncertain=(self.foreground_faults != 0 or descriptor is None
                        or descriptor.preparation_uncertain or first is not None and first["retention_uncertain"]))
            if self.sampling_enabled:
                result["sampling_first_fault"] = dict(
                    version=SAMPLING_FAULT_VERSION,
                    first_fault=self.sampling_first.copy() if self.sampling_first is not None else None,
                    observation_faults=self.sampling_faults,
                    retention_uncertain=self.sampling_faults != 0)
            if self.closure_enabled:
                result["closure_boundary"] = {
                    "version": "stage12_public_closure_boundary_diagnostics_v1",
                    "scope": "LAST_BOUNDARIES_NOT_CAUSE_OR_CLOSURE_PROOF",
                    "last_entered": self.closure_entered.copy() if self.closure_entered else None,
                    "last_completed": self.closure_completed.copy() if self.closure_completed else None,
                    "first_failure": {key: (value.copy() if value else None)
                                      for key, value in self.closure_first.items()} if self.closure_first else None,
                    "observation_faults": self.closure_faults,
                    "retention_uncertain": self.closure_faults != 0,
                    "persistence": "NOT_ESTABLISHED_BY_IN_MEMORY_SNAPSHOT",
                }
                result["resource_preopening"] = dict(
                    version="stage12_resource_preopening_diagnostics_v1",
                    scope="SUPPLEMENTARY_PREABORT_NOT_ACCEPTANCE_OR_CAUSE_PROOF",
                    first_failure=_resource_copy(self.resource_first),
                    first_cleanup_failure=_resource_copy(self.resource_cleanup),
                    cleanup_observations=self.resource_cleanup_count,
                    last_entered=self.resource_entered.copy() if self.resource_entered else None,
                    last_completed=self.resource_completed.copy() if self.resource_completed else None,
                    persistence="NOT_ESTABLISHED_BY_IN_MEMORY_SNAPSHOT")
            if self.observer_enabled:
                result["observer_stages"] = dict(
                    version="stage12_resource_observer_stages_v1",
                    scope="SUPPLEMENTARY_COARSE_TIMING_NOT_COVERAGE_OR_CAUSE_PROOF",
                    clocks="INDEPENDENT_MONOTONIC_NS_AND_CURRENT_THREAD_CPU_NS",
                    interval="CALL_OWNER_EXCLUDES_FINAL_RECORDING_OVERHEAD",
                    stage_completion="STAGE_ATTEMPT_ENDED_NOT_SUCCESS",
                    slow_observation_threshold_ns=OBSERVER_SLOW_NS,
                    aggregate_rows=9, owner_retained_stage_rows_maximum=36,
                    calls=self.observer_calls, observation_faults=self.observer_faults,
                    retention_uncertain=self.observer_faults != 0,
                    wall_clock_complete=self.observer_wall_complete,
                    thread_cpu_clock_complete=self.observer_cpu_complete,
                    totals=_resource_copy(self.observer_totals),
                    last_acquisition=_resource_copy(self.observer_last),
                    first_failed_acquisition=_resource_copy(self.observer_first_failed),
                    first_slow_acquisition=_resource_copy(self.observer_first_slow),
                    persistence="NOT_ESTABLISHED_BY_IN_MEMORY_SNAPSHOT")
            return result

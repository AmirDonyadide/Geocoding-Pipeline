"""Finite 120-row scale validation with instrumented no-service transport. Invoke with a pinned synthetic input.

This execution asset is NOT a service runner or authority provider. Network,
process creation, credentials and reads outside source/runtime/output are denied.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone


class ArtifactBudget:
    """Conservative logical bytes, no path cache or recurring directory scan.

    Reserve before every reviewed artifact write. Partial/failed writes retain
    the whole reservation. One MiB of the fixed128MiB cap is left for bounded
    final metrics, watchdog notice and outer logs. This is diagnostic accounting,
    never campaign evidence or a replacement for the client's storage checks.
    """

    def __init__(self, limit=127 * 2**20):
        if type(limit) is not int or limit < 0:
            raise ValueError("SYNTHETIC_ARTIFACT_ACCOUNTING_INVALID")
        self.limit = limit
        self.charged = 0
        self.exceeded = False
        self.lock = threading.Lock()

    def charge(self, size):
        if type(size) is not int or size < 0:
            raise ValueError("SYNTHETIC_ARTIFACT_ACCOUNTING_INVALID")
        with self.lock:
            if size > self.limit - self.charged:
                self.exceeded = True
                raise RuntimeError("SYNTHETIC_ARTIFACT_LIMIT")
            self.charged += size

    def snapshot(self):
        with self.lock:
            return {
                "charged_upper_bytes": self.charged,
                "limit_bytes": self.limit,
                "exceeded": self.exceeded,
            }


def install_artifact_accounting(io, journal, budget):
    """Cover actual source write paths in BOTH pinned client versions.

    io.write uses buffered file writes; stream_array uses os.write. The legacy
    write_array uses its own buffered stream, so charge its fixed delimiters and
    canonical rows as consumed. No event-history traversal is added. Returns
    originals for isolated unit-test restoration; production replay exits once.
    """
    old_write, old_append, old_array = io.write, os.write, journal.Journal.write_array

    def write(path, raw):
        budget.charge(len(raw))
        return old_write(path, raw)

    def append(fd, raw):
        budget.charge(len(raw))
        return old_append(fd, raw)

    def array(self, name, rows):
        budget.charge(3)

        def charged_rows():
            for row in rows:
                # Includes one conservative separator byte for the first row.
                budget.charge(len(journal.c.canonical(row)))
                yield row

        return old_array(self, name, charged_rows())

    io.write, os.write, journal.Journal.write_array = write, append, array
    return old_write, old_append, old_array


def deny_linux_network():
    """Kernel guard for Goethe, in addition to Python audit/provider denial.

    No package/tool installation. Fail closed on an unsupported Linux ABI or
    unavailable seccomp. x32/other ABIs cannot bypass the syscall number set.
    """
    if sys.platform != "linux":
        return "LOCAL_PYTHON_AUDIT_ONLY"
    if platform.machine() != "x86_64":
        raise RuntimeError("SYNTHETIC_DIAGNOSTIC_UNSUPPORTED_ABI")

    class Filter(ctypes.Structure):
        _fields_ = [
            ("code", ctypes.c_ushort),
            ("jt", ctypes.c_ubyte),
            ("jf", ctypes.c_ubyte),
            ("k", ctypes.c_uint),
        ]

    class Program(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ushort), ("filters", ctypes.POINTER(Filter))]

    denied = 0x00050001  # SECCOMP_RET_ERRNO | EPERM
    instructions = [
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xC000003E),
        (0x06, 0, 0, denied),
        (0x20, 0, 0, 0),
        (0x45, 0, 1, 0x40000000),
        (0x06, 0, 0, denied),
    ]
    # socket/connect/accept/send/receive/bind/listen/socketpair + io_uring.
    for number in (
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        49,
        50,
        53,
        288,
        299,
        307,
        425,
        426,
        427,
    ):
        instructions += [(0x15, 0, 1, number), (0x06, 0, 0, denied)]
    instructions.append((0x06, 0, 0, 0x7FFF0000))
    filters = (Filter * len(instructions))(*(Filter(*x) for x in instructions))
    program = Program(len(instructions), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) or libc.prctl(22, 2, ctypes.byref(program), 0, 0):
        raise RuntimeError("SYNTHETIC_DIAGNOSTIC_NETWORK_GUARD_UNAVAILABLE")
    # Must fail before a socket exists; no connect or service call is made.
    if libc.socket(2, 1, 0) != -1 or ctypes.get_errno() != 1:
        raise RuntimeError("SYNTHETIC_DIAGNOSTIC_NETWORK_GUARD_INVALID")
    return "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700)
    raw = args.input.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.input_sha256
    data = json.loads(raw)
    assert data["scope"] == "INVENTED_SYNTHETIC_ONLY_NO_SERVICE"
    assert data["version"] == "stage12_scale120_synthetic_input_v1"
    assert len(data["work"]) == 120
    assert data["profile"]["states"][0]["rate"] == {"num": 1, "den": 1}
    assert data["profile"]["resource_sample_period_ms"] == 100
    assert data["profile"]["resources"]["writer_guard_ms"] == 5000
    assert data["plan"]["shutdown_reserve_ms"] == 80000
    for budget in (data["plan"]["budgets"], data["plan"]["blocks"][0]["budget"]):
        assert budget["active_duration_ms"] == 500000
        assert budget["data_attempts"] == 180
        assert budget["event_count"] == 20000
        assert budget["data_observations"] == 120
    source = args.source.resolve()
    sys.path.insert(0, str(source / "src"))
    allowed = tuple(
        str(p.resolve())
        for p in (
            source,
            args.output,
            args.input,
            Path(sys.prefix),
            Path(sys.base_prefix),
            Path(__file__).parent,
        )
    )
    guard_metrics = {"open_checks": 0, "realpath_ns": 0}
    guard_lock = threading.Lock()

    def denied(*_a, **_k):
        raise PermissionError("SYNTHETIC_DIAGNOSTIC_ACCESS_DENIED")

    def audit(event, values):
        if event.startswith(("socket.", "subprocess.")) or event in (
            "os.system",
            "os.fork",
            "os.posix_spawn",
            "os.exec",
        ):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            guard_start = time.monotonic_ns()
            path = os.path.realpath(os.fsdecode(values[0]))
            guard_elapsed = time.monotonic_ns() - guard_start
            with guard_lock:
                guard_metrics["open_checks"] += 1
                guard_metrics["realpath_ns"] += guard_elapsed
            if any(
                x in Path(path).parts for x in (".ssh", ".config", "credentials")
            ) or any(x.startswith(".env") for x in Path(path).parts):
                denied()
            if path not in ("/dev/null", "/dev/urandom") and not any(
                path == p or path.startswith(p + "/") for p in allowed
            ):
                denied()

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "call", "check_output", "check_call"):
        setattr(subprocess, name, denied)
    network_guard = deny_linux_network()
    # Dependencies may read their installation/system timezone metadata on import.
    # Import before the strict read-root guard; no data/provider call occurs here.
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as j,
        s12_public_scheduler as sched,
        s12_public_operations as o,
        s12_public_response as validation,
        s12_public_reporting as reporting,
        s12_public_recovery as recovery,
        s12_storage as io,
        s12_transport as transport,
        s12_retrieval_contract as c,
    )

    transport.Secret.runtime = denied
    transport.Secret.private_file = denied
    sys.addaudithook(audit)
    artifact_budget = ArtifactBudget()
    install_artifact_accounting(io, j, artifact_budget)
    watchdog_stop = threading.Event()
    watchdog_start = time.monotonic()
    watchdog_metrics = {"checks": 0, "storage_scans": 0}

    def watchdog():
        while not watchdog_stop.wait(0.25):
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_bytes = rss if sys.platform == "darwin" else rss * 1024
            reason = (
                "RUNTIME"
                if time.monotonic() - watchdog_start >= 600
                else ("MEMORY" if rss_bytes >= 768 * 2**20 else None)
            )
            watchdog_metrics["checks"] += 1
            if artifact_budget.snapshot()["exceeded"]:
                reason = "ARTIFACTS"
            if reason:
                (args.output / "HARD_LIMIT.json").write_text(
                    json.dumps({"reason": reason})
                )
                os._exit(124)  # Preserve partial files; never attempt false closure.

    threading.Thread(
        target=watchdog, name="bounded-diagnostic-watchdog", daemon=True
    ).start()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 2**20, 128 * 2**20))
    signal.signal(signal.SIGALRM, lambda *_: denied())
    signal.alarm(600)
    epoch = time.monotonic_ns()
    cpu0 = time.process_time_ns()
    attempts = 0
    lock = threading.Lock()
    metrics = {}
    metric_overhead_ns = 0
    first_instrumented_error = None

    def note_error(tag, error):
        nonlocal first_instrumented_error
        code = (
            error.args[0]
            if type(error) is c.Stage12Error and len(error.args) == 1
            else None
        )
        if type(code) is not str or code not in {
            "S12_PUBLIC_WINDOW_CLOSED",
            "PUBLIC_PROBE_EVIDENCE_WRITE_FAILED",
            "S12_PRIVATE_FILE_INVALID",
            "S12_PUBLIC_STORAGE_ACCOUNTING_MISMATCH",
        }:
            code = None
        family = (
            "CUMULATIVE_DEADLINE"
            if isinstance(error, recovery.FinalizationExpired)
            else (
                "TIMEOUT"
                if isinstance(error, TimeoutError)
                else "STAGE12"
                if type(error) is c.Stage12Error
                else "OS_ERROR"
                if isinstance(error, OSError)
                else "UNCLASSIFIED"
            )
        )
        with lock:
            if first_instrumented_error is None:
                first_instrumented_error = {
                    "static_tag": tag,
                    "family": family,
                    "code": code,
                    "mono_ns": time.monotonic_ns(),
                }

    finalizing = False
    reopening = False
    diagnostic_scanning = False
    stage_metrics = {}
    stage_local = threading.local()

    def stage_call(tag, action, *a, **kw):
        # Fixed static tags and a bounded nesting stack, never an event trace.
        stack = getattr(stage_local, "stack", [])
        stage_local.stack = stack
        assert len(stack) < 32
        entry = [time.monotonic_ns(), time.thread_time_ns(), 0, 0]
        stack.append(entry)
        try:
            return action(*a, **kw)
        finally:
            wall = time.monotonic_ns() - entry[0]
            cpu = time.thread_time_ns() - entry[1]
            stack.pop()
            if stack:
                stack[-1][2] += wall
                stack[-1][3] += cpu
            with lock:
                value = stage_metrics.setdefault(tag, [0, 0, 0, 0, 0])
                value[0] += 1
                value[1] += wall
                value[2] += cpu
                value[3] += wall - entry[2]
                value[4] += cpu - entry[3]

    def stage_wrap(owner, name, tag):
        original = getattr(owner, name)

        def measured(*a, **kw):
            return stage_call(tag, original, *a, **kw)

        setattr(owner, name, measured)

    def add(tag, elapsed, items=0):
        nonlocal metric_overhead_ns
        begin = time.monotonic_ns()
        bucket = (
            9
            if diagnostic_scanning
            else 8
            if reopening
            else 7
            if finalizing
            else min(6, (attempts + 19) // 20)
        )
        with lock:
            cell = metrics.setdefault(tag, [[0, 0, 0, 0] for _ in range(10)])[bucket]
            cell[0] += 1
            cell[1] += elapsed
            cell[2] = max(cell[2], elapsed)
            cell[3] += items
            metric_overhead_ns += time.monotonic_ns() - begin

    def wrap(owner, name, tag, generator=False):
        original = getattr(owner, name)
        if generator:

            def call(*a, **kw):
                iterator = iter(original(*a, **kw))
                while True:
                    t = time.monotonic_ns()
                    try:
                        row = next(iterator)
                    except StopIteration:
                        add(tag, time.monotonic_ns() - t)
                        return
                    add(tag, time.monotonic_ns() - t, 1)
                    yield row
        else:

            def call(*a, **kw):
                t = time.monotonic_ns()
                try:
                    return original(*a, **kw)
                except BaseException as error:
                    note_error(tag, error)
                    raise
                finally:
                    add(tag, time.monotonic_ns() - t)

        setattr(owner, name, call)

    for owner, name, tag, gen in (
        (j, "read_events", "validated_event_rows", True),
        (j, "tree_bytes", "storage_tree_scan", False),
        (j.Writer, "call", "writer_wait", False),
        (j.Writer, "_execute", "writer_action", False),
        (sched.Coordinator, "_resource", "resource_acquire_persist", False),
        (o, "verify_work_manifest", "work_manifest", False),
        (o, "verify_authorities", "fixed_authority_profile", False),
        (reporting, "block_report", "block_report", False),
        (recovery, "write_snapshot", "snapshot_prepare_validate_commit", False),
        (recovery, "snapshot_evidence", "original_closure_verification", False),
        (recovery, "unclean_reconciliation", "reconciliation", False),
        (recovery, "work_ledger", "ledger_rows", True),
        (io, "fsync_directory", "directory_fsync", False),
    ):
        wrap(owner, name, tag, gen)
    if hasattr(j, "MeasurementPrefix"):
        wrap(j.MeasurementPrefix, "events", "measurement_projection_rows", True)
        wrap(j.MeasurementPrefix, "build", "prefix_construction")
        wrap(j.MeasurementPrefix, "verify_original", "original_prefix_verification")
    wrap(reporting, "exact_stats", "exact_statistics")
    wrap(os, "fsync", "file_fsync")
    oldread = io.read

    def read(path, **kw):
        tag = (
            "read_event"
            if path.parent.name == "events"
            else ("read_work" if path.parent.name == "work" else "read_other")
        )
        t = time.monotonic_ns()
        try:
            return oldread(path, **kw)
        finally:
            add(tag, time.monotonic_ns() - t)

    io.read = read
    original_reader = io.original_read

    def physical_read(path, **kw):
        t = time.monotonic_ns()
        raw = original_reader(path, **kw)
        add("physical_original_read_bytes", time.monotonic_ns() - t, len(raw))
        return raw

    io.original_read = physical_read
    original_array, original_os_read = j.read_array, os.read
    array_local = threading.local()

    def stream_read(fd, count):
        t = time.monotonic_ns()
        raw = original_os_read(fd, count)
        if getattr(array_local, "active", False):
            add("array_stream_read_bytes", time.monotonic_ns() - t, len(raw))
        return raw

    def array_reads(*a, **kw):
        iterator = iter(original_array(*a, **kw))
        first = True
        while True:
            previous = getattr(array_local, "active", False)
            array_local.active = True
            t = time.monotonic_ns()
            try:
                row = next(iterator)
            except StopIteration:
                return
            finally:
                array_local.active = previous
                if first:
                    add("array_stream_traversals", time.monotonic_ns() - t)
                    first = False
            yield row

    os.read = stream_read
    j.read_array = array_reads
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_fresh_reads import (
        FreshReads,
    )

    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_fresh_reads as fresh_reads,
    )

    original_work_read = fresh_reads._work_read

    def measured_work_read(path):
        t = time.monotonic_ns()
        raw = original_work_read(path)
        add("physical_work_read_bytes", time.monotonic_ns() - t, len(raw))
        return raw

    fresh_reads._work_read = measured_work_read
    for owner, name, tag in (
        (fresh_reads, "work_manifest_digest", "per_attempt_work_validation"),
        (FreshReads, "__enter__", "fresh_stage_load"),
        (FreshReads, "finish", "fresh_stage_finish"),
        (j.MeasurementPrefix, "build", "prefix"),
        (j.MeasurementPrefix, "verify_original", "prefix_original_check"),
        (reporting, "block_report", "report"),
        (recovery, "write_snapshot", "snapshot_all"),
        (recovery, "snapshot_evidence", "snapshot_evidence"),
        (j.Journal, "reconcile_storage", "storage_reconciliation"),
    ):
        stage_wrap(owner, name, tag)
    oldwrite = io.write

    def persisted(path, raw):
        tag = {
            "snapshot.json": "snapshot_persistence",
            "block_report.json": "block_report_persistence",
            "campaign_report.json": "campaign_report_persistence",
            "_SEGMENT_SEALED": "segment_seal_persistence",
            "_WRITER_RELEASED.json": "writer_release_persistence",
        }.get(path.name, "other_artifact_persistence")
        t = time.monotonic_ns()
        try:
            return stage_call(tag, oldwrite, path, raw)
        finally:
            add(tag, time.monotonic_ns() - t)

    io.write = persisted
    coordinator = None
    periodic_count = 0
    oldinit = sched.Coordinator.__init__

    def initialize(self, *a, **kw):
        nonlocal coordinator
        oldinit(self, *a, **kw)
        assert coordinator is None
        coordinator = self

    sched.Coordinator.__init__ = initialize
    oldevent = j.Journal.event

    def event(self, kind, body, **kw):
        nonlocal periodic_count
        result = oldevent(self, kind, body, **kw)
        if kind == "RESOURCE" and body["cause"] == "PERIODIC":
            with lock:
                periodic_count += 1
        return result

    j.Journal.event = event
    oldadmit = sched.Coordinator.admit

    def admit(self, *a, **kw):
        oldready = self.size_ready

        def ready(pending):
            t = time.monotonic_ns()
            try:
                return oldready(pending)
            finally:
                add("size_ready", time.monotonic_ns() - t)

        self.size_ready = ready
        try:
            return oldadmit(self, *a, **kw)
        except BaseException as error:
            note_error("admission", error)
            raise
        finally:
            self.size_ready = oldready

    sched.Coordinator.admit = admit
    oldcall = j.Writer.call
    stress_complete = False

    def call(self, action, *a, **kw):
        nonlocal finalizing, stress_complete
        # Capture-side comparison prefix is pinned AFTER this existing storage
        # boundary. Hold on the coordinator thread BEFORE submitting its action,
        # never while occupying the writer or a sample slot.
        if (
            coordinator is not None
            and getattr(action, "__self__", None) is coordinator.journal
            and getattr(action, "__name__", None) == "verify_storage"
            and not stress_complete
            and attempts == 120
            and not coordinator.slots
        ):
            assert threading.current_thread() is not self.thread
            assert attempts == 120 and not coordinator.slots
            finalizing = True
            stress_start = time.monotonic_ns()
            while periodic_count < 6259:
                assert time.monotonic_ns() < epoch + 420 * 10**9
                assert not coordinator.writer.failed.is_set()
                assert coordinator.stop_reason is None
                assert (
                    coordinator.journal.normal_event_headroom()
                    > coordinator.journal.closure_events
                )
                time.sleep(0.01)
            stress_complete = True
            add("actual_sample_population_stress", time.monotonic_ns() - stress_start)
        return oldcall(self, action, *a, **kw)

    j.Writer.call = call
    oldstream = j.Journal.stream_array

    def stream(self, name, rows):
        if name == "repeat_comparison.json":
            assert stress_complete and periodic_count >= 6259

        def compared():
            iterator = iter(rows)
            while True:
                start = time.monotonic_ns()
                try:
                    row = next(iterator)
                except StopIteration:
                    add("comparison_derivation", time.monotonic_ns() - start)
                    return
                add("comparison_derivation", time.monotonic_ns() - start, 1)
                yield row

        t = time.monotonic_ns()
        try:
            stage = {
                "repeat_comparison.json": "comparisons",
                "work_ledger.json": "work_ledger",
                "remaining_work_ledger.json": "remaining_ledger",
                "event_inventory.json": "event_inventory_prepare",
                "attempt_inventory.json": "attempt_inventory_prepare",
                "measurement_event_prefix.json": "stream_projection",
            }.get(name, "other_stream")
            return stage_call(
                stage,
                oldstream,
                self,
                name,
                compared() if name == "repeat_comparison.json" else rows,
            )
        finally:
            add(
                "comparison_persistence"
                if name == "repeat_comparison.json"
                else "finalization_stream",
                time.monotonic_ns() - t,
            )

    j.Journal.stream_array = stream

    class Clock:
        def now_ns(self):
            return time.monotonic_ns()

        def utc(self):
            # Synthetic calendar; elapsed time and observation timestamps are real.
            return (
                datetime(2026, 1, 1, tzinfo=timezone.utc)
                + timedelta(microseconds=(self.now_ns() - epoch) // 1000)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        def wait_until(self, ns):
            time.sleep(max(0, (ns - self.now_ns()) / 1e9))

    authority_root = args.output / "synthetic_authority"
    authority_root.mkdir(mode=0o700)
    authority_records = []
    for i in range(5):
        path = authority_root / f"test_only_{i}.json"
        body = c.canonical(
            {"scope": "INVENTED_SYNTHETIC_ONLY_NO_AUTHORITY", "ordinal": i}
        )
        io.write(path, body)
        authority_records.append((path, c.sha(body)))

    class Authority:
        def require(self, purpose, identity, context):
            t = time.monotonic_ns()
            try:
                assert identity == data["synthetic_authority_sha256"]
                assert purpose in data["synthetic_authority_purposes"]
                for path, digest in authority_records:
                    assert c.sha(io.read(path)) == digest
                assert o.digest(data["profile"]) == data["start"]["profile_sha256"]
                assert o.digest(data["plan"]) == data["start"]["plan_sha256"]
            finally:
                add("synthetic_fixed_authority_check", time.monotonic_ns() - t)

    def free():
        t = time.monotonic_ns()
        try:
            st = os.statvfs(args.output)
            return st.f_bavail * st.f_frsize
        finally:
            add("resource_acquisition", time.monotonic_ns() - t)

    def dispatch(work, target, hooks):
        nonlocal attempts
        assert attempts < 180
        attempts += 1
        hooks.started(time.monotonic_ns())
        hooks.emit(lambda: None, lambda: None)
        time.sleep(
            0.2
        )  # Explicitly simulated service latency, identical for both runs.
        matches = [
            x
            for x in data["synthetic_responses"]
            if (x["fixture_id"], x["size"])
            == (work["fixture_id"], work["result_limit"])
        ]
        assert len(matches) == 1
        body = matches[0]["raw_utf8"].encode("utf-8")
        assert 0 < len(body) <= 65536
        result = transport.Capture(
            "VALIDATION_REQUIRED",
            "OK",
            200,
            "application/json",
            "identity",
            None,
            body,
            len(body),
            200,
        )
        hooks.completed(result)
        return result

    diagnostics = None
    extra = {}
    try:
        from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import (
            Failures,
        )
    except ImportError:
        pass
    else:
        diagnostics = Failures(Clock())
        extra["diagnostics"] = diagnostics
    result = None
    exception_family = None
    try:
        result = cli.run_operations_block(
            data["profile"],
            data["plan"],
            data["start"],
            work_factory=lambda: iter(data["work"]),
            output=args.output / "campaign",
            block_id=1,
            authority=Authority(),
            clock=Clock(),
            dispatch=dispatch,
            runtime_inventory=data["runtime"],
            runtime_key=b"INVENTED_TEST_KEY_ONLY",
            control_adapters={},
            monitor=None,
            free_bytes=free,
            segment_authority=data["synthetic_authority_sha256"],
            writer_exclusion_evidence=data["synthetic_authority_sha256"],
            epoch=data["synthetic_authority_sha256"],
            writer_release_evidence=data["synthetic_authority_sha256"],
            public_validation=validation.Validation(validation.FAMILY_VERSION),
            ascending_sizes=False,
            task_deadline_ns=epoch + 500 * 10**9,
            **extra,
        )
    except BaseException as exc:
        exception_family = "OS_ERROR" if isinstance(exc, OSError) else "UNCLASSIFIED"
    execution_ns = time.monotonic_ns() - epoch
    execution_cpu_ns = time.process_time_ns() - cpu0
    finalizing = True
    reopening = True
    reopen_start = time.monotonic_ns()
    reopened = False
    opener_invoked_ns = opener_completed_ns = None
    reopen_family = None
    try:
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_public_runtime as runtime,
        )

        if result and result["disposition"] == "COMPLETED":
            phase_deadline = recovery.Deadline(Clock(), epoch + 500 * 10**9)
            with io.cooperative_io(phase_deadline.check):
                phase_deadline.check()
                opener_invoked_ns = time.monotonic_ns()
                stage_call(
                    "actual_opener",
                    runtime.reopen_completed,
                    args.output / "campaign",
                    data["profile"],
                    data["plan"],
                    data["start"],
                    validation_sha256=o.digest(
                        validation.descriptor(validation.FAMILY_VERSION)
                    ),
                )
                phase_deadline.check()
                opener_completed_ns = time.monotonic_ns()
            reopened = True
    except BaseException as error:
        note_error("actual_reopen", error)
        reopen_family = (
            "CUMULATIVE_DEADLINE"
            if isinstance(error, recovery.FinalizationExpired)
            else "OS_ERROR"
            if isinstance(error, OSError)
            else "UNCLASSIFIED"
        )
    reopen_ns = time.monotonic_ns() - reopen_start
    phase_elapsed_ns = time.monotonic_ns() - epoch
    diagnostic_scanning = True
    events = j.read_events(args.output / "campaign", o.digest(data["start"]))
    last = None
    gaps = samples = finals = event_count = 0
    maxgap = 0
    starts = []  # Fixed <=180 synthetic attempts, never an event-history trace.
    last_ack = None
    peak_pending = peak_operations = 0
    for event in events:
        event_count += 1
        if event["kind"] == "SEGMENT_OPEN":
            last = event["mono_ns"]
        if event["kind"] == "ATTEMPT_FINALIZED":
            finals += 1
        if event["kind"] == "ATTEMPT_STARTED":
            assert len(starts) < 180
            starts.append(event["body"]["started_mono_ns"])
        if event["kind"] == "AUDIT_TIMING":
            last_ack = event["body"]["finalized_event_ack_ns"]
        if event["kind"] == "RESOURCE":
            peak_pending = max(peak_pending, event["body"]["pending_count"])
            peak_operations = max(peak_operations, event["body"]["admitted_operations"])
        if event["kind"] == "RESOURCE" and event["body"]["cause"] == "PERIODIC":
            now = event["body"]["observed_mono_ns"]
            assert last is not None and now >= last
            gap = now - last
            gaps += gap > 100_000_000
            maxgap = max(maxgap, gap)
            last = now
            samples += 1
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = rss if sys.platform == "darwin" else rss * 1024
    artifact_bytes = sum(
        p.stat().st_size for p in args.output.rglob("*") if p.is_file()
    )
    artifact_state = artifact_budget.snapshot()
    with guard_lock:
        guard_state = dict(guard_metrics)
    accounting_consistent = artifact_bytes <= artifact_state["charged_upper_bytes"]
    pairs = (
        list(j.read_array(args.output / "campaign/repeat_comparison.json"))
        if (args.output / "campaign/repeat_comparison.json").exists()
        else []
    )
    assert len(pairs) <= 114
    payload = {
        "comparison_count": len(pairs),
        "all_comparisons_equal": bool(pairs) and all(row["equal"] for row in pairs),
        "scope": data["scope"],
        "network_guard": network_guard,
        "input_sha256": args.input_sha256,
        "source": str(source),
        "python": sys.version,
        "platform": sys.platform,
        "clock": "REAL_MONOTONIC_NS_SYNTHETIC_UTC_CALENDAR",
        "elapsed_ns": execution_ns,
        "cpu_ns": execution_cpu_ns,
        "synthetic_attempts": attempts,
        "finalized_attempt_events": finals,
        "events": event_count,
        "start_count": len(starts),
        "start_cadence": {
            "numerator": max(0, len(starts) - 1),
            "denominator_ns": starts[-1] - starts[0] if len(starts) > 1 else None,
        },
        "durable_data_rate": {
            "numerator": finals if reopened else None,
            "confirmed_min": finals if reopened else 0,
            "denominator_ns": last_ack - starts[0] if last_ack and starts else None,
        },
        "peak_pending_count": peak_pending,
        "peak_admitted_operations": peak_operations,
        "periodic_samples": samples,
        "gaps_over_100ms": gaps,
        "max_gap_ns": maxgap,
        "rss_lifetime_peak_bytes": rss_bytes,
        "artifact_bytes": artifact_bytes,
        "bounds_met": (
            rss_bytes < 768 * 2**20
            and artifact_bytes < 128 * 2**20
            and accounting_consistent
            and not artifact_state["exceeded"]
        ),
        "metrics_fields": ["calls", "inclusive_ns", "max_ns", "yielded_rows"],
        "metric_buckets": [
            "pre_dispatch",
            "attempt1_20",
            "attempt21_40",
            "attempt41_60",
            "attempt61_80",
            "attempt81_100",
            "attempt101_120",
            "finalization",
            "actual_reopening",
            "post_run_diagnostic_scan",
        ],
        "metrics": metrics,
        "physical_read_units": "physical_original_read_bytes: calls are completed original file reads; yielded_rows is byte count. Cache hits excluded. physical_work_read_bytes separately reports the new fresh work-reader calls/bytes, which bypass io.original_read; sum these two non-overlapping byte categories for those readers. array_stream_read_bytes reports actual bytes returned by os.read within read_array (calls include EOF); array_stream_traversals counts initiated traversals including empty/failed ones. read_* tags are logical calls.",
        "stage_metrics_fields": [
            "calls",
            "inclusive_wall_ns",
            "inclusive_thread_cpu_ns",
            "exclusive_same_thread_wall_ns",
            "exclusive_same_thread_cpu_ns",
        ],
        "stage_metrics": stage_metrics,
        "stage_metrics_limitations": "Exclusive subtracts nested stage_call only; other work remains charged to caller. Writer thread work overlaps coordinator waits. Post-run scans are separate; no instrumentation time subtracted.",
        "opener_invoked_mono_ns": opener_invoked_ns,
        "opener_completed_mono_ns": opener_completed_ns,
        "reopen_ns": reopen_ns,
        "phase_through_reopen_ns": phase_elapsed_ns,
        "remaining_phase_ns": 500 * 10**9 - phase_elapsed_ns,
        "sampling_diagnostics": coordinator.sampling_snapshot()
        if coordinator
        else None,
        "sampling_diagnostic_units": "count,total_ns,max_ns; persistence_ack includes failed waits and is not ACK proof; slot_busy count only; supplementary not closure evidence",
        "stress_population_minimum": 6259,
        "full_reopen_pass": reopened,
        "reopen_exception_family": reopen_family,
        "watchdog": watchdog_metrics,
        "artifact_accounting": artifact_state,
        "artifact_accounting_consistent": accounting_consistent,
        "artifact_inventory_scans": 1,
        "artifact_bytes_excludes": "BOUNDED_FINAL_MEASUREMENTS_AND_OUTER_LOGS",
        "read_guard": guard_state,
        "aggregation_overhead_ns": metric_overhead_ns,
        "exception_family": exception_family,
        "first_instrumented_error": first_instrumented_error,
        "result": result,
        "diagnostics": diagnostics.snapshot() if diagnostics else None,
        "complete_seal": (args.output / "campaign/_SEGMENT_SEALED").exists(),
    }
    measurement_bytes = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    # Leave the other half of the fixed one-MiB margin for bounded notices/logs.
    if len(measurement_bytes) > 512 * 1024:
        raise RuntimeError("SYNTHETIC_MEASUREMENT_LIMIT")
    (args.output / "MEASUREMENTS.json").write_bytes(measurement_bytes)
    print(
        json.dumps(
            {
                k: payload[k]
                for k in (
                    "elapsed_ns",
                    "synthetic_attempts",
                    "finalized_attempt_events",
                    "gaps_over_100ms",
                    "max_gap_ns",
                    "complete_seal",
                    "bounds_met",
                )
            }
        )
    )
    watchdog_stop.set()
    signal.alarm(0)
    passed = bool(
        payload["bounds_met"]
        and result
        and result["disposition"] == "COMPLETED"
        and result["report_complete"]
        and reopened
        and finals == 120
        and attempts == 120
        and gaps == 0
        and samples >= 6259
        and len(pairs) == 114
        and all(row["equal"] for row in pairs)
        and payload["complete_seal"]
        and phase_elapsed_ns <= 500 * 10**9
        and not artifact_budget.snapshot()["exceeded"]
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

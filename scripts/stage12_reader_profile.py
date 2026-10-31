"""Bounded no-service original-reader and sample-acknowledgement diagnostic.

This profiles retained synthetic evidence. It neither dispatches requests nor
qualifies a campaign. Comparison function bodies are compiled verbatim from the
selected source so both versions use their actual validation/derivation logic.
"""

from __future__ import annotations
import argparse
import ast
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import socket
import struct
import subprocess
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    for name in ("source", "fixture", "input", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700)
    sys.path.insert(0, str(args.source / "src"))
    from stage12_scale120_diagnostic import (
        deny_linux_network,
        ArtifactBudget,
        install_artifact_accounting,
    )
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_fresh_reads as fresh,
        s12_public_runtime as runtime,
        s12_public_operations as o,
        s12_public_response as validation,
        s12_public_journal as j,
        s12_public_scheduler as sched,
        s12_public_operational_audit as oa,
        s12_public_audit as audit,
        s12_storage as io,
        s12_transport as transport,
        s12_retrieval_contract as c,
        s12_response as response,
    )
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_work_index import (
        WorkIndex,
    )

    raw = args.input.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.input_sha256
    data = json.loads(raw)
    assert data["scope"] == "INVENTED_SYNTHETIC_ONLY_NO_SERVICE"
    assert len(data["work"]) == 120
    assert data["profile"]["resource_sample_period_ms"] == 100
    assert data["profile"]["resources"]["writer_guard_ms"] == 5000
    epoch = time.monotonic_ns()
    metrics = {}
    stage = "SETUP"
    gate = threading.Lock()
    local = threading.local()
    stages = {}
    active = False
    records = deque(maxlen=8192)
    dropped = 0
    record_struct = struct.Struct("<6Q4I")
    stage_codes = {
        "SETUP": 0,
        "WORK120": 1,
        "COMPARISON": 2,
        "OPENER": 3,
        "DONE": 4,
        "BETWEEN": 5,
    }
    budget = ArtifactBudget(limit=32 * 2**20)
    install_artifact_accounting(io, j, budget)
    allowed = tuple(
        os.path.realpath(p)
        for p in (
            args.source,
            args.fixture,
            args.input,
            args.output,
            Path(sys.prefix),
            Path(sys.base_prefix),
            Path(__file__).parent,
        )
    )

    def denied(*a, **k):
        raise PermissionError("SYNTHETIC_DIAGNOSTIC_ACCESS_DENIED")

    def metric(name, elapsed, amount=0):
        with gate:
            cell = metrics.setdefault(stage, {}).setdefault(name, [0, 0, 0, 0])
            cell[0] += 1
            cell[1] += elapsed
            cell[2] = max(cell[2], elapsed)
            cell[3] += amount

    def audit_guard(event, values):
        if event.startswith(("socket.", "subprocess.")) or event in (
            "os.system",
            "os.fork",
            "os.posix_spawn",
            "os.exec",
        ):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            before = time.monotonic_ns()
            path = os.path.realpath(os.fsdecode(values[0]))
            if active:
                metric("guard_realpath", time.monotonic_ns() - before)
            parts = Path(path).parts
            if any(x in parts for x in (".ssh", ".config", "credentials")) or any(
                x.startswith(".env") for x in parts
            ):
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
    transport.Secret.runtime = denied
    transport.Secret.private_file = denied
    network_guard = deny_linux_network()
    sys.addaudithook(audit_guard)

    def check():
        assert time.monotonic_ns() - epoch < 300 * 10**9, "PROFILE_PROCESS_DEADLINE"
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        assert (rss if sys.platform == "darwin" else rss * 1024) < 768 * 2**20, (
            "PROFILE_MEMORY"
        )
        assert not budget.snapshot()["exceeded"], "PROFILE_STORAGE"

    signal.signal(signal.SIGALRM, lambda *a: denied())
    signal.alarm(300)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 2**20, 128 * 2**20))
    watchdog_stop = threading.Event()

    def watchdog():
        while not watchdog_stop.wait(0.25):
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak = rss if sys.platform == "darwin" else rss * 1024
            reason = (
                "RUNTIME"
                if time.monotonic_ns() - epoch >= 300 * 10**9
                else "MEMORY"
                if peak >= 768 * 2**20
                else "ARTIFACTS"
                if budget.snapshot()["exceeded"]
                else None
            )
            if reason:
                (args.output / "HARD_LIMIT.json").write_text(
                    json.dumps({"reason": reason})
                )
                os._exit(124)

    threading.Thread(
        target=watchdog, name="bounded-profile-watchdog", daemon=True
    ).start()

    def free_bytes():
        info = os.statvfs(args.output)
        return info.f_bavail * info.f_frsize

    def wrap(owner, name, label, size=False):
        old = getattr(owner, name)

        def call(*a, **k):
            before = time.monotonic_ns()
            value = None
            try:
                value = old(*a, **k)
                return value
            finally:
                if active:
                    metric(
                        label,
                        time.monotonic_ns() - before,
                        len(value) if size and value is not None else 0,
                    )

        setattr(owner, name, call)

    for name in ("open", "close", "stat", "lstat", "fstat", "read", "pread", "fsync"):
        wrap(os, name, "os_" + name, name in ("read", "pread"))
    for name in ("private_directory", "metadata", "_checkpoint", "original_read"):
        wrap(io, name, "io_" + name, name == "original_read")
    wrap(fresh, "_work_read", "physical_work_read", True)
    wrap(o, "parse", "event_parse")
    wrap(c, "canonical", "canonical")
    wrap(c, "sha", "hash")
    wrap(j.Writer, "call", "writer_wait")
    wrap(j.Writer, "_execute", "writer_action")
    # Bounded associations, not event evidence or substituted timestamps.
    oldevent, oldsubmit = j.Journal.event, j.Writer.submit

    def event(self, kind, body, **kw):
        if kind != "RESOURCE" or body["cause"] != "PERIODIC":
            return oldevent(self, kind, body, **kw)
        row = [
            body["observed_mono_ns"],
            0,
            0,
            0,
            0,
            0,
            stage_codes[stage],
            stage_codes[stage],
            0,
            0,
        ]
        local.row = row
        local.journal = self
        try:
            result = oldevent(self, kind, body, **kw)
            row[4] = time.monotonic_ns()
            return result
        except BaseException:
            row[9] |= 1
            raise

    def submit(self, action, **kw):
        row = getattr(local, "row", None)
        journal = getattr(local, "journal", None)
        if not kw.get("periodic") or row is None:
            return oldsubmit(self, action, **kw)
        row[1] = time.monotonic_ns()

        def actual():
            row[2] = time.monotonic_ns()
            row[7] = stage_codes[stage]
            try:
                result = action()
                row[8] = journal.seq
                return result
            except BaseException:
                row[9] |= 2
                raise
            finally:
                row[3] = time.monotonic_ns()

        return oldsubmit(self, actual, **kw)

    j.Journal.event = event
    j.Writer.submit = submit
    oldsample, oldresource = sched.Coordinator.sample_if_due, sched.Coordinator.resource

    def released():
        nonlocal dropped
        row = getattr(local, "row", None)
        if row is None:
            return
        row[5] = time.monotonic_ns()
        local.row = None
        local.journal = None
        with gate:
            dropped += int(len(records) == records.maxlen)
            records.append(record_struct.pack(*row))

    def sample(self, *a, **kw):
        try:
            return oldsample(self, *a, **kw)
        finally:
            released()

    def resource_call(self, cause, *a, **kw):
        try:
            return oldresource(self, cause, *a, **kw)
        finally:
            if cause == "PERIODIC":
                released()

    sched.Coordinator.sample_if_due = sample
    sched.Coordinator.resource = resource_call

    class Clock:
        def now_ns(self):
            return time.monotonic_ns()

        def utc(self):
            return (
                datetime(2026, 1, 1, tzinfo=timezone.utc)
                + timedelta(microseconds=(self.now_ns() - epoch) // 1000)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        def wait_until(self, ns):
            time.sleep(max(0, ns - self.now_ns()) / 1e9)

    class SyntheticAuthority:
        def require(self, purpose, identity, context):
            assert identity == data["synthetic_authority_sha256"]

    # Extract exact function bodies, never a replacement scheduler/validator.
    source_text = (
        args.source / "src/safe_geocoding_pipeline/preprocessing/stage12_probe_cli.py"
    ).read_text()
    root_ast = ast.parse(source_text)
    selected = {}
    for node in ast.walk(root_ast):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "locate_attempt",
            "verify_at",
            "comparisons",
        ):
            assert node.name not in selected
            selected[node.name] = node
    assert set(selected) == {"locate_attempt", "verify_at", "comparisons"}
    function_hashes = {
        name: hashlib.sha256(
            ast.get_source_segment(source_text, node).encode()
        ).hexdigest()
        for name, node in selected.items()
    }

    def works():
        return iter(runtime.plan_work(args.fixture, data["plan"]))

    index = WorkIndex(
        works,
        lambda key: io.metadata(io.read(args.fixture / "work" / f"{key:020d}.json")),
        data["plan"],
    )
    namespace = dict(cli.__dict__)
    namespace.update(
        output=args.fixture,
        public_validation=validation.Validation(validation.FAMILY_VERSION),
        po=o,
        pj=j,
        audit=audit,
        oa=oa,
        c=c,
        io=io,
        response=response,
        profile=data["profile"],
        plan=data["plan"],
        start=data["start"],
        comparison_pairs=lambda: index.pairs(1),
        comparison_events=lambda: j.read_events(args.fixture, o.digest(data["start"])),
    )
    exec(
        compile(
            ast.Module(body=list(selected.values()), type_ignores=[]),
            "<selected-comparison-functions>",
            "exec",
        ),
        namespace,
    )
    namespace["verify_receipt"] = lambda row, event: namespace["verify_at"](
        args.fixture, row, event
    )
    controller = None
    failure = None
    outcomes = {}

    def stage_call(name, fn):
        nonlocal stage, active
        stage = name
        active = True
        start = time.monotonic_ns()
        cpu = time.process_time_ns()
        try:
            check()
            value = fn()
            check()
            return value
        finally:
            end = time.monotonic_ns()
            stages[name] = {
                "start_mono_ns": start,
                "end_mono_ns": end,
                "wall_ns": end - start,
                "cpu_ns": time.process_time_ns() - cpu,
            }
            active = False
            stage = "BETWEEN"

    try:
        h = data["synthetic_authority_sha256"]
        controller = sched.Coordinator(
            data["profile"],
            data["plan"],
            data["start"],
            authority=SyntheticAuthority(),
            clock=Clock(),
            root=args.output / "sample_trace",
            block_id=1,
            segment_authority=h,
            writer_exclusion_evidence=h,
            epoch=h,
            free_bytes=free_bytes,
        )
        controller.journal.enable_accounting()
        controller.writer.check_deadline = check
        controller.start_sampling()

        def work():
            digest = None
            for _ in range(120):
                value = controller.writer.cooperative(
                    lambda: fresh.work_manifest_digest(args.fixture / "work", 120)
                )
                assert digest is None or digest == value
                digest = value
            return digest

        outcomes["work_digest"] = stage_call("WORK120", work)

        def comparison():
            with (
                io.cooperative_io(check),
                fresh.FreshReads(args.fixture / "attempts", check=check),
            ):
                return controller.journal.stream_array(
                    "repeat_comparison.json", namespace["comparisons"]()
                )

        outcomes["comparison_digest"] = stage_call("COMPARISON", comparison)
        assert controller.stop_sampling()
        controller.resource("PERIODIC")
        expected = list(j.read_array(args.fixture / "repeat_comparison.json"))
        actual = list(j.read_array(args.output / "sample_trace/repeat_comparison.json"))
        assert (
            actual == expected
            and len(actual) == 114
            and all(x["equal"] for x in actual)
        )
        outcomes["comparisons"] = len(actual)

        def opener():
            with io.cooperative_io(check):
                return runtime.reopen_completed(
                    args.fixture,
                    data["profile"],
                    data["plan"],
                    data["start"],
                    validation_sha256=o.digest(
                        validation.descriptor(validation.FAMILY_VERSION)
                    ),
                )

        outcomes["opened_report"] = stage_call("OPENER", opener)
    except BaseException as error:
        failure = (
            type(error).__name__
            if type(error).__name__
            in (
                "Stage12Error",
                "AssertionError",
                "OSError",
                "PermissionError",
                "TimeoutError",
            )
            else "UNCLASSIFIED"
        )
    finally:
        active = False
        stage = "DONE"
        if controller is not None:
            controller.stop_sampling()
            controller.writer.abort()
        signal.alarm(0)
        watchdog_stop.set()
        raw = b"".join(records)
        (args.output / "SAMPLE_ASSOCIATIONS.bin").write_bytes(raw)
        samples = [r[0] for r in struct.iter_unpack("<6Q4I", raw)]
        gaps = (
            [b - a for a, b in zip([controller.opened_ns] + samples, samples)]
            if controller is not None
            else []
        )
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        payload = {
            "scope": "PARTIAL_PATH_PROFILE_NO_SERVICE_NOT_COMPLETION",
            "source": str(args.source),
            "input_sha256": args.input_sha256,
            "function_sha256": function_hashes,
            "stages": stages,
            "metrics": metrics,
            "metric_fields": ["calls", "inclusive_ns", "max_ns", "bytes"],
            "outcomes": outcomes,
            "failure_family": failure,
            "network_guard": network_guard,
            "sample_format": "<6Q4I",
            "sample_fields": [
                "observed_ns",
                "enqueued_ns",
                "writer_start_ns",
                "action_end_ns",
                "ack_return_ns",
                "slot_released_ns",
                "observed_stage",
                "writer_stage",
                "event_seq",
                "failure_flags",
            ],
            "stage_codes": stage_codes,
            "sample_count": len(samples),
            "sample_dropped": dropped,
            "max_gap_ns": max(gaps, default=None),
            "gaps_over_100ms": sum(x > 100_000_000 for x in gaps),
            "sampling_diagnostics": controller.sampling_snapshot()
            if controller
            else None,
            "rss_peak_bytes": rss if sys.platform == "darwin" else rss * 1024,
            "elapsed_ns": time.monotonic_ns() - epoch,
            "artifact_accounting": budget.snapshot(),
            "limitations": "Nested timers are not additive. Syscall/guard instrumentation adds identical bounded work. Baseline-first cache/load order remains a confounder. Read-only completed synthetic fixture; separate incomplete sampling journal; no HTTP attempts, live authority, campaign completion or service throughput claim. The real opener is executed afresh.",
        }
        (args.output / "MEASUREMENTS.json").write_text(
            json.dumps(payload, indent=2) + "\n"
        )
    return 0 if failure is None else 1


if __name__ == "__main__":
    try:
        exit_code = main()
    except BaseException as error:
        family = type(error).__name__
        if family not in {
            "Stage12Error",
            "AssertionError",
            "OSError",
            "PermissionError",
            "TimeoutError",
        }:
            family = "UNCLASSIFIED"
        # Setup/teardown failures must not echo arbitrary messages or locals.
        sys.stderr.write(
            json.dumps({"failure": "PROFILE_SETUP_OR_FATAL_FAILURE", "family": family})
            + "\n"
        )
        exit_code = 1
    raise SystemExit(exit_code)

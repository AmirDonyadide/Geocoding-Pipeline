"""Finite complete matrix replay; explicit synthetic authority/transport only.

Production scheduler, writer, capture, comparisons, closure and openers execute
unchanged. This does not invoke the live CLI or contact a service. The 20/sec
synthetic profile is an invented transport input. The prospective 7,200-second
whole-process deadline includes setup and actual whole-task reopening; neither
that allowance nor the synthetic pace establishes public service capacity.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from collections import deque
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import threading
import time

SCOPE = "INVENTED_SYNTHETIC_MATRIX_REPLAY_NO_SERVICE_AUTHORITY"
MAX_SECONDS = 7200
MAX_BYTES = 256 * 2**20
MAX_FILES = 50000
MAX_RSS = 768 * 2**20
MIN_PERIODIC_PER_PHASE = 200
MIN_PERIODIC_SIZE40 = 900
H = hashlib.sha256(SCOPE.encode()).hexdigest()
CHECKPOINT_LIMITS = {
    "interval_ms": 5000,
    "max_files": 1500,
    "max_file_bytes": 32768,
    "ring_records": 4096,
    "records_per_checkpoint": 128,
}


def main():
    started = time.monotonic_ns()
    cpu_started = time.process_time_ns()
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.alarm(MAX_SECONDS)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--wf-ap2",
        action="store_true",
        help="Explicit prospective AP2/M2 representative family; live proof and separate diagnostic grant required",
    )
    parser.add_argument("--evidence-bundle", type=Path)
    parser.add_argument("--evidence-review-sha256")
    args = parser.parse_args()
    if args.wf_ap2:
        from stage12_wf_ap2_diagnostic import execute

        return execute(args, started_ns=started, cpu_started_ns=cpu_started)
    os.umask(0o077)
    raw = args.input.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.input_sha256
    data = json.loads(raw)
    assert data["scope"] == SCOPE
    assert data["source_sha"] == args.source_sha
    assert len(args.source_sha) == 40 and all(
        ch in "0123456789abcdef" for ch in args.source_sha
    )
    assert data["version"] == "stage12_complete_matrix_synthetic_input_v2"
    assert data["checkpoints"] == CHECKPOINT_LIMITS
    assert data["limits"] == {
        "seconds": MAX_SECONDS,
        "bytes": MAX_BYTES,
        "files": MAX_FILES,
        "rss_bytes": MAX_RSS,
        "attempts": 584,
        "synthetic_rate": 20,
        "minimum_periodic_per_phase": MIN_PERIODIC_PER_PHASE,
        "minimum_periodic_size40": MIN_PERIODIC_SIZE40,
    }
    from stage12_diagnostic_checkpoints import Checkpoints

    source = args.source.resolve()
    assert not args.output.exists()
    args.output.mkdir(mode=0o700)
    sys.path.insert(0, str(source / "src"))
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
        s12_public_matrix as matrix,
        s12_public_scheduler as scheduler,
        s12_public_journal as journal,
        s12_public_operations as operations,
        s12_public_response as validation,
        s12_public_diagnostics as diagnostics,
        s12_public_recovery as recovery,
        s12_retrieval_contract as contract,
        s12_storage as storage,
        s12_transport as transport,
    )

    assert contract.canonical(data) == raw
    matrix.validate_matrix(data["configuration"])

    spec = importlib.util.spec_from_file_location(
        "scale120_guard", source / "scripts/stage12_scale120_diagnostic.py"
    )
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    network_guard = guard.deny_linux_network()

    def denied(*_args, **_kwargs):
        raise PermissionError("SYNTHETIC_DIAGNOSTIC_ACCESS_DENIED")

    allowed = [
        source,
        args.output.resolve(),
        args.input.resolve(),
        Path(__file__).resolve().parent,
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
    ]
    # Reserve the resource helper's entire finite native-file allowance, since
    # native database/Arrow creation need not trigger Python's audit hook.
    created_entries = 64
    entry_lock = threading.Lock()

    def charge_entry(path):
        nonlocal created_entries
        path = Path(os.path.realpath(os.fsdecode(path)))
        if path == args.output.resolve() or path.is_relative_to(args.output.resolve()):
            with entry_lock:
                assert created_entries < MAX_FILES
                created_entries += 1

    def audit(event, values):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            path = Path(os.path.realpath(os.fsdecode(values[0])))
            if any(
                part in {".ssh", ".config", "credentials"} or part.startswith(".env")
                for part in path.parts
            ):
                denied()
            if str(path) not in {"/dev/null", "/dev/urandom"} and not any(
                path == root or path.is_relative_to(root) for root in allowed
            ):
                denied()
            if type(values[2]) is int and values[2] & os.O_CREAT:
                charge_entry(values[0])
        if event == "os.mkdir":
            charge_entry(values[0])

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "call", "check_output", "check_call"):
        setattr(subprocess, name, denied)
    transport.Secret.runtime = transport.Secret.private_file = denied
    sys.addaudithook(audit)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))
    stop_watchdog = threading.Event()
    active_stage = "RESOURCE"
    active_phase = None
    budget = guard.ArtifactBudget(MAX_BYTES - 2**20)
    guard.install_artifact_accounting(storage, journal, budget)

    # This independent supplementary writer never calls the campaign writer.
    # It charges each complete selected chunk BEFORE writing; failed/partial
    # writes retain the entire allocation. Both writers share the diagnostic
    # byte/file ceiling, not a scientific evidence stream or sampler slot.
    checkpoints = Checkpoints(
        args.output / "diagnostic_checkpoints",
        clock_ns=time.monotonic_ns,
        budget_charge=budget.charge,
        interval_seconds=CHECKPOINT_LIMITS["interval_ms"] / 1000,
        max_files=CHECKPOINT_LIMITS["max_files"],
        max_bytes=CHECKPOINT_LIMITS["max_file_bytes"],
        ring_size=CHECKPOINT_LIMITS["ring_records"],
        chunk_records=CHECKPOINT_LIMITS["records_per_checkpoint"],
    )

    def limit_check():
        if time.monotonic_ns() >= started + MAX_SECONDS * 10**9:
            raise recovery.FinalizationExpired()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        assert (rss if sys.platform == "darwin" else rss * 1024) < MAX_RSS
        assert not budget.snapshot()["exceeded"]
        checkpoints.check()

    def watchdog():
        while not stop_watchdog.wait(0.25):
            try:
                limit_check()
            except BaseException:
                # Supplementary diagnostic only; never a controller seal.
                try:
                    notice = json.dumps(
                        {
                            "stage": active_stage,
                            "phase": active_phase,
                            "elapsed_ns": time.monotonic_ns() - started,
                            "complete": False,
                            "scope": SCOPE,
                        },
                        sort_keys=True,
                    ).encode()
                    with (args.output / "HARD_LIMIT.json").open("xb") as stream:
                        stream.write(notice)
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    os._exit(124)

    threading.Thread(
        target=watchdog, name="synthetic-matrix-watchdog", daemon=True
    ).start()

    resource_spec = importlib.util.spec_from_file_location(
        "stage12_resource_observer",
        source / "scripts/stage12_resource_characterization.py",
    )
    resource_module = importlib.util.module_from_spec(resource_spec)
    resource_spec.loader.exec_module(resource_module)
    resource_observation = resource_module.characterize(args.output / "resource")
    # Native database/Parquet writes bypass the Python write instrumentation.
    # Charge the entire retained prefix before the matrix can allocate anything;
    # duplicate accounting of instrumented helper writes stays conservative.
    budget.charge(
        sum(
            path.stat().st_size
            for path in (args.output / "resource").rglob("*")
            if path.is_file()
        )
    )
    limit_check()
    active_stage = "MATRIX_PREPARE"

    class Clock:
        def now_ns(self):
            return time.monotonic_ns()

        def utc(self):
            return (
                datetime(2026, 1, 1, tzinfo=timezone.utc)
                + timedelta(microseconds=(self.now_ns() - started) // 1000)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        def wait_until(self, until):
            time.sleep(max(0, until - self.now_ns()) / 1e9)

    clock = Clock()
    config = deepcopy(data["configuration"])
    assert len(config["campaigns"]) == 11
    assert (
        sum(x["plan"]["budgets"]["data_observations"] for x in config["campaigns"])
        == 576
    )
    assert (
        sum(
            x["plan"]["budgets"]["required_control_observations"]
            for x in config["campaigns"]
        )
        == 8
    )
    matrix.validate_matrix(config)
    assert all(
        x["profile"]["states"][0]["rate"] == {"num": 20, "den": 1}
        for x in config["campaigns"]
    )
    adapter = validation.Validation(validation.CORPUS_VERSION)
    assert operations.digest(adapter.descriptor()) == config["public_validation_sha256"]
    output = args.output / "matrix"
    storage.reserve(output)
    storage.write(output / "configuration.json", contract.canonical(config))
    runtime_inventory = {
        "scope": SCOPE,
        "transport": "RETAINED_PUBLIC_BODY_REPLAY_PLUS_INVENTED_CONTROLS",
        "authority": "INVENTED_TEST_ONLY",
        "key": "INVENTED_TEST_KEY_ONLY",
        "clock": "REAL_MONOTONIC_SYNTHETIC_UTC",
        "source_sha": data["source_sha"],
    }
    storage.write(
        output / "runtime_inventory.json", contract.canonical(runtime_inventory)
    )
    attempts = 0
    current = None
    phase_periodic = 0
    totals = {"periodic_samples": 0, "event_files": 0}
    phase_metrics = []
    operation_metrics = {}
    metrics_lock = threading.Lock()
    sample_records = deque(maxlen=4096)
    sample_records_dropped = 0
    sample_local = threading.local()
    collection_stage = "CAPTURE"
    last_phase_report_complete = None

    def retain_sample(row):
        nonlocal sample_records_dropped
        with metrics_lock:
            if len(sample_records) == sample_records.maxlen:
                sample_records_dropped += 1
            sample_records.append(row)
        # Bounded memory-only submission after slot release. The independent
        # checkpoint thread performs all supplementary disk work.
        checkpoints.record(row)

    def measured(tag, fn):
        def run(*a, **kw):
            begin = time.monotonic_ns()
            try:
                return fn(*a, **kw)
            finally:
                duration = time.monotonic_ns() - begin
                with metrics_lock:
                    row = operation_metrics.setdefault(tag, [0, 0, 0])
                    row[0] += 1
                    row[1] += duration
                    row[2] = max(row[2], duration)

        return run

    for owner, name, tag in (
        (journal.Writer, "call", "writer_wait"),
        (journal.Writer, "_execute", "writer_action"),
        (runtime, "reopen_completed", "actual_opener"),
        (recovery, "write_snapshot", "snapshot"),
        (matrix, "reconcile", "aggregate_original_reopening"),
    ):
        setattr(owner, name, measured(tag, getattr(owner, name)))
    old_init = scheduler.Coordinator.__init__

    def initialize(self, *a, **kw):
        nonlocal current
        old_init(self, *a, **kw)
        current = self

    scheduler.Coordinator.__init__ = initialize
    old_event = journal.Journal.event

    def event(self, kind, body, **kw):
        nonlocal phase_periodic
        enqueue = time.monotonic_ns()
        phase_at_entry, stage_at_entry = active_phase, collection_stage
        result = old_event(self, kind, body, **kw)
        if kind == "RESOURCE" and body["cause"] == "PERIODIC":
            phase_periodic += 1
            totals["periodic_samples"] += 1
            timing = kw.get("periodic_timing") or {}
            row = [
                phase_at_entry,
                stage_at_entry,
                getattr(sample_local, "entered", None),
                body["observed_mono_ns"],
                enqueue,
                timing.get("writer_start_ns"),
                timing.get("writer_done_ns"),
                time.monotonic_ns(),
                None,
            ]
            if getattr(sample_local, "entered", None) is None:
                retain_sample(row)  # Final explicit sample has no sampler entry.
            else:
                sample_local.row = row
        return result

    journal.Journal.event = event
    old_sample = scheduler.Coordinator.sample_if_due

    def sampled(self):
        sample_local.entered = time.monotonic_ns()
        sample_local.row = None
        try:
            return old_sample(self)
        finally:
            if sample_local.row is not None:
                sample_local.row[-1] = time.monotonic_ns()
                retain_sample(sample_local.row)
            sample_local.entered = None
            sample_local.row = None

    scheduler.Coordinator.sample_if_due = sampled
    old_call = journal.Writer.call
    hold_done = False
    sample_target = MIN_PERIODIC_PER_PHASE

    def hold_call(self, action, *a, **kw):
        nonlocal hold_done, collection_stage
        if (
            current is not None
            and not hold_done
            and not current.slots
            and getattr(action, "__self__", None) is current.journal
            and getattr(action, "__name__", None) == "verify_storage"
        ):
            while phase_periodic < sample_target:
                limit_check()
                assert not current.writer.failed.is_set()
                assert current.stop_reason is None
                time.sleep(0.005)
            hold_done = True
            collection_stage = "COMPARISON_STORAGE_AND_SOURCE_SETUP"
            checkpoints.set_phase(active_phase, collection_stage)
        return old_call(self, action, *a, **kw)

    journal.Writer.call = hold_call
    synthetic_records = {}
    for name in config["sources"]:
        value = contract.canonical({"scope": SCOPE, "role": name})
        synthetic_records[contract.sha(value).hex()] = value

    class Authority:
        def __init__(self, item, start):
            self.item, self.start = item, start

        def require(self, purpose, identity, context):
            limit_check()
            profile, plan = self.item["profile"], self.item["plan"]
            values = {
                "policy_freeze_record_sha256": config["sources"]["policy_freeze"],
                "implementation_authorization_sha256": config["sources"]["owner"],
                "implementation_review_sha256": H,
                "initial_workload_authority_sha256": config["sources"]["owner"],
                "operator_allowance": config["sources"]["operator"],
                "transport_profile": operations.digest(config["transport"]),
                "plan_selection": config["sources"]["selection"],
                "rate_state": config["sources"]["selection"],
                "resources": config["sources"]["selection"],
                "monitoring": config["sources"]["selection"],
                "segment_open": config["sources"]["owner"],
                "writer_exclusion": config["sources"]["owner"],
                "runtime_preflight": config["sources"]["owner"],
                "writer_release": config["sources"]["owner"],
                "dispatch": config["sources"]["owner"],
                "control_recipe": operations.digest(matrix.check_descriptor()),
            }
            assert purpose in values and identity == values[purpose]
            for key, value in (
                ("profile", profile),
                ("plan", plan),
                ("start", self.start),
            ):
                if key in context:
                    assert context[key] == value
            assert self.start["profile_sha256"] == operations.digest(profile)
            assert self.start["plan_sha256"] == operations.digest(plan)

    responses = {
        (row["fixture_id"], row["size"]): row["raw_utf8"].encode("utf-8")
        for row in data["responses"]
    }
    assert len(responses) == 288 and all(
        0 < len(x) <= 65536 for x in responses.values()
    )
    control_raw = contract.canonical(
        {
            "type": "FeatureCollection",
            "features": [],
            "geocoding": {"version": "synthetic-test-only"},
        }
    )

    def dispatch(work, target, hooks):
        nonlocal attempts
        limit_check()
        assert attempts < 584
        attempts += 1
        hooks.started(clock.now_ns())
        hooks.emit(lambda: None, limit_check)
        time.sleep(0.005)  # Explicit synthetic transport delay, not service latency.
        payload = (
            control_raw
            if work["kind"] == "SERVICE_CONTROL"
            else responses[(work["fixture_id"], work["result_limit"])]
        )
        capture = transport.Capture(
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
        hooks.completed(capture)
        return capture

    failures = diagnostics.Failures(clock)
    result = None
    error_record = None
    try:
        for item in config["campaigns"]:
            phase_periodic = 0
            sample_target = (
                MIN_PERIODIC_SIZE40
                if item["label"] == "size40_deep"
                else MIN_PERIODIC_PER_PHASE
            )
            hold_done = False
            current = None
            active_phase = item["label"]
            active_stage = "PHASE_EXECUTION"
            collection_stage = "CAPTURE"
            last_phase_report_complete = None
            checkpoints.set_phase(active_phase, collection_stage)
            checkpoints.flush(timeout=5)
            limit_check()
            phase_started = clock.now_ns()
            storage.write(
                args.output / (item["label"] + "_DIAGNOSTIC_STARTED.json"),
                contract.canonical(
                    {
                        "scope": SCOPE,
                        "label": item["label"],
                        "started_mono_ns": phase_started,
                        "prior_completed_phases": len(phase_metrics),
                        "prior_periodic_observations": totals["periodic_samples"],
                        "periodic_target": sample_target,
                        "attempts_before": attempts,
                    }
                ),
            )
            profile, plan = item["profile"], item["plan"]
            controls = matrix.adapters(plan)
            start = {
                "schema_version": operations.START,
                "scope": operations.SCOPE,
                "campaign_id": os.urandom(32).hex(),
                "profile_sha256": operations.digest(profile),
                "plan_sha256": operations.digest(plan),
                "rule_bundle_sha256": operations.RULE_BUNDLE,
                "policy_freeze_record_sha256": config["sources"]["policy_freeze"],
                "implementation_authorization_sha256": config["sources"]["owner"],
                "implementation_review_sha256": H,
                "initial_workload_authority_sha256": config["sources"]["owner"],
                "client_git_sha": data["source_sha"],
                "runtime_inventory_sha256": operations.digest(runtime_inventory),
                "created_utc": clock.utc(),
            }
            deadline = min(
                started + MAX_SECONDS * 10**9,
                phase_started + plan["budgets"]["active_duration_ms"] * 10**6,
            )
            check = recovery.Deadline(clock, deadline).check
            report = cli.run_operations_block(
                profile,
                plan,
                start,
                work_factory=lambda: iter(item["work"]),
                output=output / item["label"],
                block_id=1,
                authority=Authority(item, start),
                clock=clock,
                dispatch=dispatch,
                runtime_inventory=runtime_inventory,
                runtime_key=b"INVENTED_TEST_KEY_ONLY",
                control_adapters=controls,
                monitor=None,
                free_bytes=lambda: 2**60,
                segment_authority=config["sources"]["owner"],
                writer_exclusion_evidence=config["sources"]["owner"],
                epoch=os.urandom(32).hex(),
                writer_release_evidence=config["sources"]["owner"],
                public_validation=adapter,
                ascending_sizes=False,
                task_deadline_ns=deadline,
                diagnostics=failures,
            )
            last_phase_report_complete = report["report_complete"]
            assert report["disposition"] == "COMPLETED" and report["report_complete"]
            active_stage = "PHASE_REOPEN"
            checkpoints.set_phase(active_phase, active_stage)
            reopen_begin = clock.now_ns()
            with storage.cooperative_io(check):
                block = runtime.reopen_completed(
                    output / item["label"],
                    profile,
                    plan,
                    start,
                    validation_sha256=config["public_validation_sha256"],
                    control_adapters=controls,
                )
                check()
                control_pairs = matrix.verify_controls(output / item["label"], plan)
                check()
            assert matrix.gate(block, item, config["capability"])
            storage.write(
                output / (item["label"] + "_CAPABILITY_GATE.json"),
                contract.canonical(
                    {
                        "version": "stage12_public_matrix_phase_gate_v1",
                        "configuration_sha256": operations.digest(config),
                        "block_report_sha256": operations.digest(block),
                        "control_comparisons": control_pairs,
                        "disposition": "PASS_EXACT_PHASE_NOT_RATE_QUALIFICATION",
                        "cumulative_attempts": attempts,
                    }
                ),
            )
            phase_metrics.append(
                {
                    "label": item["label"],
                    "elapsed_ns": clock.now_ns() - phase_started,
                    "actual_opener_ns": clock.now_ns() - reopen_begin,
                    "periodic_samples": phase_periodic,
                    "sampling_metrics": current.sampling_snapshot(),
                    "report_complete": report["report_complete"],
                }
            )
            storage.write(
                args.output / (item["label"] + "_DIAGNOSTIC_COMPLETED.json"),
                contract.canonical(phase_metrics[-1]),
            )
            checkpoints.set_phase(active_phase, "PHASE_COMPLETE_AFTER_ACTUAL_REOPEN")
            checkpoints.flush(timeout=5)
            limit_check()
        active_stage = "AGGREGATE_REOPEN_AND_COMPARISON"
        checkpoints.set_phase(None, active_stage)
        checkpoints.flush(timeout=5)
        with storage.cooperative_io(limit_check):
            result = matrix.reconcile(config, output, limit_check)
        assert result["actual_attempts"] == attempts == 584
        assert len(result["cross_size_comparisons"]) == 1024
        storage.write(output / "matrix_reconciliation.json", contract.canonical(result))
        assert storage.read(
            output / "matrix_reconciliation.json"
        ) == contract.canonical(result)
        limit_check()
    except BaseException as error:
        family, code, number = diagnostics.classify(error)
        error_record = {
            "family": family,
            "code": code,
            "errno": number,
            "phase": None if current is None else current.block["block_id"],
        }
    finally:
        # Checkpoint shutdown and final diagnostic accounting are part of the
        # non-resetting deadline. No successful summary may follow expiry.
        try:
            checkpoints.close(timeout=5)
            limit_check()
        except BaseException as error:
            if error_record is None:
                family, code, number = diagnostics.classify(error)
                error_record = {
                    "family": family,
                    "code": code,
                    "errno": number,
                    "phase": None,
                }
        elapsed = clock.now_ns() - started
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        files = [p for p in args.output.rglob("*") if p.is_file()]
        artifact_bytes = sum(p.stat().st_size for p in files)
        summary = {
            "scope": SCOPE,
            "resource_observation_complete": resource_observation is not None,
            "active_stage_at_summary": active_stage,
            "input_sha256": args.input_sha256,
            "source_sha": data["source_sha"],
            "network_guard": network_guard,
            "synthetic_rate": 20,
            "synthetic_latency_ms": 5,
            "elapsed_ns": elapsed,
            "timing_scope": "THROUGH_CHECKPOINT_CLOSE_BEFORE_SUMMARY_WRITE_AND_STDOUT",
            "cpu_ns": time.process_time_ns() - cpu_started,
            "remaining_ns": MAX_SECONDS * 10**9 - elapsed,
            "process_lifetime_peak_rss_bytes": rss
            if sys.platform == "darwin"
            else rss * 1024,
            "artifact_bytes_before_summary": artifact_bytes,
            "files_before_summary": len(files),
            "artifact_accounting": budget.snapshot(),
            "attempts": attempts,
            "charged_creation_attempts": created_entries,
            "complete": result is not None and error_record is None,
            "error": error_record,
            "phases": phase_metrics,
            "current_phase_label": active_phase,
            "current_phase_report_complete": last_phase_report_complete,
            "current_sampling_metrics": current.sampling_snapshot()
            if current is not None
            else None,
            "sample_record_fields": [
                "phase",
                "stage_at_event_enter",
                "collector_enter_ns",
                "observed_ns",
                "event_enter_ns",
                "writer_start_ns",
                "writer_done_ns",
                "event_ack_ns",
                "collector_return_after_slot_release_ns",
            ],
            "sample_records": list(sample_records),
            "sample_records_dropped": sample_records_dropped,
            "sample_record_scope": "SUPPLEMENTARY_BOUNDED_TAIL_ACTUAL_TIMES_NOT_COVERAGE_AUTHORITY",
            "metrics": operation_metrics,
            "failure_diagnostics": failures.snapshot(),
            "checkpoint_evidence": checkpoints.snapshot(),
            "data_observations": None
            if result is None
            else result["data_observations"],
            "controls": None if result is None else result["control_exchanges"],
            "same_size_comparisons": None
            if result is None
            else result["same_size_comparisons"],
            "cross_size_comparisons": None
            if result is None
            else len(result["cross_size_comparisons"]),
            "live_capacity_or_scientific_authority": False,
        }
        storage.write(args.output / "summary.json", contract.canonical(summary))
        assert artifact_bytes < MAX_BYTES and len(files) < MAX_FILES
        print(contract.canonical(summary).decode(), end="")
        sys.stdout.flush()
        # Keep both internal guards active through potentially blocking output.
        # This terminal marker is supplementary: exit zero, exact original
        # reopening and all selected criteria are still required for PASS.
        limit_check()
        storage.write(
            args.output / "DIAGNOSTIC_TERMINAL.json",
            contract.canonical(
                {
                    "scope": SCOPE,
                    "source_sha": data["source_sha"],
                    "input_sha256": args.input_sha256,
                    "after_summary_and_stdout_mono_ns": clock.now_ns(),
                    "elapsed_ns": clock.now_ns() - started,
                    "internal_deadline_mono_ns": started + MAX_SECONDS * 10**9,
                    "complete": result is not None and error_record is None,
                }
            ),
        )
        limit_check()
        signal.alarm(0)
        stop_watchdog.set()
    return 0 if result is not None and error_record is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

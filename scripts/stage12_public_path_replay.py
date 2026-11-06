"""Finite real-public-adapter replay. Kernel network and provider access denied.

Transport delays, key and authority-record contents are TEST_ONLY. The actual
clock/wait, filesystem observer, authority reader, coordinator, writer, response
validators, report, closure and completed openers execute without substitutes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import signal
import socket
import subprocess
import sys
import threading
import time

SCOPE = "TEST_ONLY_REAL_PUBLIC_ADAPTER_REPLAY_NO_SERVICE_AUTHORITY"
LIMITS = {
    "seconds": 7200,
    "artifact_bytes": 256 * 2**20,
    "creations": 50000,
    "rss_bytes": 768 * 2**20,
    "attempts": 171,
    "response_bytes": 65536,
}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def parent_fsync_open(path, flags, output):
    """Permit only the output parent's read-only directory handle, not its files."""
    forbidden = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    required = os.O_DIRECTORY | os.O_NOFOLLOW
    return (
        type(flags) is int
        and flags & required == required
        and not flags & forbidden
        and path == output.resolve().parent
    )


def main():
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("input", "source", "output", "metadata"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--started-ns", type=int, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    assert args.metadata == Path(str(args.output) + "_allocation_metadata")
    assert not args.metadata.is_symlink()
    assert 0 < args.started_ns <= entered
    deadline = args.started_ns + LIMITS["seconds"] * 10**9
    assert time.monotonic_ns() < deadline
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.alarm(max(1, math.ceil((deadline - time.monotonic_ns()) / 10**9)))
    source = args.source.resolve()
    sys.path.insert(0, str(source / "src"))
    from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm

    require_goethe_nhr_slurm("stage12 real public adapter replay; no service")
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
        s12_public_matrix as matrix,
        s12_public_scheduler as scheduler,
        s12_public_journal as journal,
        s12_public_operations as operations,
        s12_public_response as validation,
        s12_public_timing as timing,
        s12_public_diagnostics as diagnostics,
        s12_public_recovery as recovery,
        s12_public_checkpoints as checkpoints,
        s12_public_audit as data_audit,
        s12_public_operational_audit as capture_audit,
        s12_retrieval_contract as contract,
        s12_storage as storage,
        s12_transport as transport,
    )

    guard = load_module(
        "replay_guard", source / "scripts/stage12_scale120_diagnostic.py"
    )
    native = load_module(
        "native_enforcement", source / "scripts/stage12_native_enforcement_observer.py"
    )
    schema = load_module(
        "replay_input_schema", source / "scripts/stage12_prepare_public_path_replay.py"
    )
    network_guard = guard.deny_linux_network()

    def denied(*_a, **_kw):
        raise PermissionError("PUBLIC_REPLAY_ACCESS_DENIED")

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "listen", "sendto"):
        setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "call", "check_output", "check_call"):
        setattr(subprocess, name, denied)
    transport.Secret.runtime = transport.Secret.private_file = denied
    allowed = [
        source,
        args.output.resolve(),
        args.input.resolve(),
        args.metadata.resolve(),
        Path(sys.prefix).resolve(),
        Path(sys.base_prefix).resolve(),
        Path("/proc/self").resolve(),
        Path("/sys/fs/cgroup").resolve(),
    ]
    proc_self = Path("/proc/self").resolve()
    cgroup_root = Path("/sys/fs/cgroup").resolve()
    creation_count = 24  # Pre-reserve all fixed launcher metadata creations.
    creation_lock = threading.Lock()

    def audit(event, values):
        nonlocal creation_count
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            path = Path(os.path.realpath(os.fsdecode(values[0])))
            if path.is_relative_to(proc_self) and (
                path.parent != proc_self or path.name not in native.PROC_NAMES
            ):
                denied()
            if (
                path.is_relative_to(cgroup_root)
                and path.name not in native.CGROUP_NAMES
            ):
                denied()
            if any(
                part in (".ssh", ".config", "credentials") or part.startswith(".env")
                for part in path.parts
            ):
                denied()
            if (
                str(path) not in ("/dev/null", "/dev/urandom")
                and not any(
                    path == root or path.is_relative_to(root) for root in allowed
                )
                and not parent_fsync_open(path, values[2], args.output)
            ):
                denied()
            creating = type(values[2]) is int and bool(values[2] & os.O_CREAT)
        else:
            creating = event == "os.mkdir"
            path = Path(os.path.realpath(os.fsdecode(values[0]))) if creating else None
        if creating:
            assert path == args.output.resolve() or path.is_relative_to(
                args.output.resolve()
            )
            with creation_lock:
                assert creation_count < LIMITS["creations"]
                creation_count += 1

    sys.addaudithook(audit)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (LIMITS["artifact_bytes"], LIMITS["artifact_bytes"])
    )
    assert args.input.stat().st_size <= 8 * 2**20
    raw = args.input.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.input_sha256
    data = json.loads(raw)
    assert contract.canonical(data) == raw and data["scope"] == SCOPE
    assert data["version"] == "stage12_public_path_replay_input_v1"
    assert set(data) == {
        "scope",
        "version",
        "source_sha",
        "limits",
        "scenarios",
        "configuration",
        "test_only_authority_records",
        "response_cases",
        "authority_source_files",
        "code_review_report_utf8",
        "code_review_report_sha256",
        "synthetic_delay_ms",
        "interpretation",
        "source_inputs",
    }
    assert data["source_sha"] == args.source_sha and data["limits"] == LIMITS
    assert data["scenarios"] == schema.SCENARIOS
    assert data["synthetic_delay_ms"] == {"ordinary": 5, "every_eighth_work": 20}
    assert len(args.source_sha) == 40 and all(
        x in "0123456789abcdef" for x in args.source_sha
    )
    runtime.validate_config(data["configuration"])
    storage.reserve(args.output)
    budget = guard.ArtifactBudget(LIMITS["artifact_bytes"] - 2**20)
    guard.install_artifact_accounting(storage, journal, budget)
    metadata_files = [p for p in args.metadata.iterdir() if p.is_file()]
    assert (
        len(metadata_files) <= 24
        and sum(p.stat().st_size for p in metadata_files) <= 2**20
    )
    budget.charge(sum(p.stat().st_size for p in metadata_files))
    stop_watchdog = threading.Event()
    active = "NATIVE_OBSERVATION"
    current = None

    def limit_check():
        if time.monotonic_ns() >= deadline:
            raise recovery.FinalizationExpired()
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        assert (rss if sys.platform == "darwin" else rss * 1024) < LIMITS["rss_bytes"]
        assert not budget.snapshot()["exceeded"]

    def watch():
        while not stop_watchdog.wait(0.25):
            try:
                limit_check()
            except BaseException:
                try:
                    storage.write(
                        args.output / "HARD_LIMIT.json",
                        contract.canonical(
                            {
                                "scope": SCOPE,
                                "active": active,
                                "complete": False,
                                "actual_mono_ns": time.monotonic_ns(),
                            }
                        ),
                    )
                finally:
                    os._exit(124)

    threading.Thread(target=watch, daemon=True, name="public-replay-watchdog").start()
    roles = {
        name: args.output / "declared_native_workspace" / name
        for name in native.RUNTIME_ROLES
    }
    facts = native.collect_native_enforcement(
        args.output, roles, requested_slurm_memory_bytes=6 * 2**30
    )
    storage.write(
        args.output / "NATIVE_ENFORCEMENT_OBSERVATION.json", contract.canonical(facts)
    )
    clock = runtime.Clock()
    config = data["configuration"]
    bundle = args.output / "TEST_ONLY_AUTHORITY_RECORDS"
    storage.reserve(bundle)
    assert set(data["test_only_authority_records"]) == set(config["sources"])
    for name, text in data["test_only_authority_records"].items():
        assert json.loads(text) == {
            "scope": SCOPE,
            "role": name,
            "claim": "TEST_ONLY_NOT_AN_OPERATOR_OR_INSTITUTIONAL_ATTESTATION",
        }
        assert contract.sha(text.encode()).hex() == config["sources"][name]
        storage.write(bundle / (name + ".record"), text.encode())
    note = data["code_review_report_utf8"].encode()
    assert contract.sha(note).hex() == data["code_review_report_sha256"]
    storage.write(bundle / "integration_review.md", note)
    names = data["authority_source_files"]
    assert (
        isinstance(names, list)
        and 0 < len(names) <= 256
        and names == sorted(set(names))
    )
    for name in names:
        path = Path(name)
        assert not path.is_absolute() and ".." not in path.parts
        assert path.parts[0] in ("src", "tests", "scripts", "docs", "cluster")
        assert path.suffix in (".py", ".json", ".sbatch")
        assert (source / path).resolve().is_relative_to(source)
    review = {
        "version": "stage12_public_integration_review_binding_v1",
        "scope": operations.SCOPE,
        "disposition": "PASS",
        "configuration_sha256": operations.digest(config),
        "report_sha256": contract.sha(note).hex(),
        "source_files": [
            {"path": name, "sha256": contract.sha((source / name).read_bytes()).hex()}
            for name in names
        ],
    }
    authority = runtime.Authority(
        config,
        bundle,
        review,
        operations.digest(review),
        source,
        args.source_sha,
        clock,
    )
    observer = None  # Disabled baseline has no checkpoint thread or disk work.
    attempts = 0
    envelope = runtime.Envelope(
        clock, LIMITS["attempts"], LIMITS["seconds"], matrix=True
    )
    adapter = validation.Validation(validation.CORPUS_VERSION)
    for case in data["response_cases"]:
        assert contract.sha(case["raw_utf8"].encode()).hex() == case["payload_sha256"]
    responses = {
        (x["label"], x["work_id"]): x["raw_utf8"].encode()
        for x in data["response_cases"]
    }
    assert len(responses) == 96 and all(
        0 < len(x) <= LIMITS["response_bytes"] for x in responses.values()
    )
    metrics = {}
    metrics_lock = threading.Lock()
    phase_periodic = 0
    phase_deadline = None
    sample_target = 0
    hold_done = False
    explicit_hold_ns = 0
    init = scheduler.Coordinator.__init__

    def initialize(self, *a, **kw):
        nonlocal current
        init(self, *a, **kw)
        current = self

    scheduler.Coordinator.__init__ = initialize
    old_event = journal.Journal.event

    def event(self, kind, body, **kw):
        nonlocal phase_periodic
        result = old_event(self, kind, body, **kw)
        if kind == "RESOURCE" and body["cause"] == "PERIODIC":
            phase_periodic += 1
        return result

    journal.Journal.event = event
    old_call = journal.Writer.call

    def call(self, action, *a, **kw):
        nonlocal hold_done, explicit_hold_ns
        if (
            current is not None
            and not hold_done
            and not current.slots
            and getattr(action, "__self__", None) is current.journal
            and getattr(action, "__name__", None) == "verify_storage"
        ):
            hold_started = clock.now_ns()
            try:
                while phase_periodic < sample_target:
                    limit_check()
                    phase_deadline.check()
                    assert not self.failed.is_set() and current.stop_reason is None
                    time.sleep(0.005)
            finally:
                explicit_hold_ns += clock.now_ns() - hold_started
            hold_done = True
        return old_call(self, action, *a, **kw)

    journal.Writer.call = call

    def measured(tag, fn):
        def run(*a, **kw):
            begin = time.monotonic_ns()
            try:
                return fn(*a, **kw)
            finally:
                with metrics_lock:
                    row = metrics.setdefault(tag, [0, 0, 0])
                    elapsed = time.monotonic_ns() - begin
                    row[0] += 1
                    row[1] += elapsed
                    row[2] = max(row[2], elapsed)

        return run

    for owner, name, tag in (
        (journal.Writer, "call", "writer_call"),
        (journal.Writer, "_execute", "writer_action_and_tail"),
        (runtime, "reopen_completed", "actual_completed_opener"),
    ):
        setattr(owner, name, measured(tag, getattr(owner, name)))
    scenario_rows = []
    failure = None
    failures = diagnostics.Failures(clock)
    try:
        for index, scenario in enumerate(data["scenarios"], 1):
            active = scenario["name"]
            current = None
            phase_periodic = 0
            hold_done = False
            explicit_hold_ns = 0
            sample_target = scenario["minimum_periodic"]
            item = next(
                x for x in config["campaigns"] if x["label"] == scenario["label"]
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
                "implementation_review_sha256": operations.digest(review),
                "initial_workload_authority_sha256": config["sources"]["owner"],
                "client_git_sha": args.source_sha,
                "runtime_inventory_sha256": operations.digest({"scope": SCOPE}),
                "created_utc": clock.utc(),
            }
            authority.bind(item, plan, start)
            if scenario["observer"]:
                if observer is None:
                    observer = timing.PublicTiming(
                        args.output / "supplementary_timing",
                        phase_count=5,
                        budget_charge=budget.charge,
                    )
                observer.set_phase(index)
                observer.boundary()
            phase_started = clock.now_ns()
            cpu = time.process_time_ns()
            phase_deadline = recovery.Deadline(
                clock,
                min(
                    deadline,
                    phase_started + plan["budgets"]["active_duration_ms"] * 10**6,
                ),
            )
            path = args.output / scenario["name"]
            before_attempts = attempts

            def dispatch(work, target, hooks):
                nonlocal attempts
                limit_check()
                envelope.charge()
                attempts += 1
                authority.recheck()
                bound = envelope.wrap(hooks)
                began = clock.now_ns()
                bound.started(began)
                bound.emit(lambda: None, limit_check)
                time.sleep(0.020 if work["work_id"] % 8 == 0 else 0.005)
                payload = (
                    contract.canonical(
                        {
                            "type": "FeatureCollection",
                            "features": [],
                            "geocoding": {"version": "INVENTED_CONTROL_ONLY"},
                        }
                    )
                    if work["kind"] == "SERVICE_CONTROL"
                    else responses[(item["label"], work["work_id"])]
                )
                if scenario["expected"] != "COMPLETE" and work["work_id"] == 2:
                    payload = b"{"
                capture = transport.Capture(
                    "VALIDATION_REQUIRED",
                    "OK",
                    200,
                    "application/json",
                    "identity",
                    None,
                    payload,
                    len(payload),
                    (clock.now_ns() - began) // 10**6,
                )
                bound.completed(capture)
                return capture

            report = cli.run_operations_block(
                profile,
                plan,
                start,
                work_factory=lambda: iter(item["work"]),
                output=path,
                block_id=1,
                authority=authority,
                clock=clock,
                dispatch=dispatch,
                runtime_inventory={"scope": SCOPE},
                runtime_key=b"INVENTED_TEST_KEY_ONLY",
                control_adapters=controls,
                monitor=None,
                free_bytes=lambda: runtime.filesystem_free_bytes(args.output),
                segment_authority=config["sources"]["owner"],
                writer_exclusion_evidence=config["sources"]["owner"],
                epoch=os.urandom(32).hex(),
                writer_release_evidence=config["sources"]["owner"],
                public_validation=adapter,
                ascending_sizes=item["ascending_sizes"],
                task_deadline_ns=phase_deadline.end_ns,
                diagnostics=failures,
                timing_observer=observer if scenario["observer"] else None,
            )
            observer.sampling(current.sampling_snapshot()) if scenario[
                "observer"
            ] else None
            opener_started = clock.now_ns()
            block = None
            rejected = False
            try:
                with storage.cooperative_io(phase_deadline.check):
                    block = runtime.reopen_completed(
                        path,
                        profile,
                        plan,
                        start,
                        validation_sha256=config["public_validation_sha256"],
                        control_adapters=controls,
                    )
                    phase_deadline.check()
            except contract.Stage12Error:
                rejected = True
                if scenario["expected"] == "COMPLETE":
                    raise
            if scenario["expected"] == "COMPLETE":
                assert (
                    report["report_complete"] and report["disposition"] == "COMPLETED"
                )
                assert block is not None and matrix.gate(
                    block, item, config["capability"]
                )
                control_pairs = matrix.verify_controls(path, plan)
            else:
                assert rejected and not report["report_complete"]
                assert 2 <= attempts - before_attempts <= 3
                assert (path / "_SEGMENT_SEALED").is_file()
                assert (path / "_WRITER_RELEASED.json").is_file()
                remaining = list(
                    journal.read_array(path / "remaining_work_ledger.json")
                )
                ledger = list(journal.read_array(path / "work_ledger.json"))
                assert len(ledger) == 64 and {r["work_id"] for r in ledger} == set(
                    range(1, 65)
                )
                assert {r["work_id"] for r in remaining} == {
                    r["work_id"]
                    for r in ledger
                    if r["state"] in ("UNBEGUN", "RETRY_DUE", "UNUSED_RESERVED_CONTROL")
                }
                for work_id in (1, 2):
                    directory = path / "attempts" / data_audit.name_for(work_id, 1)
                    work = item["work"][work_id - 1]
                    terminal = data_audit.reopen(
                        directory,
                        directory.name,
                        validator=adapter.validator(work, directory),
                        context=capture_audit.DataContext(adapter),
                    )
                    assert terminal["outcome"] == (
                        "CONTRACT_FAILURE"
                        if work_id == 2
                        else (
                            "SUCCESS_ZERO_CANDIDATES"
                            if terminal["candidate_count"] == 0
                            else "SUCCESS_WITH_CANDIDATES"
                        )
                    )
                    if work_id == 2:
                        from safe_geocoding_pipeline.preprocessing.stages import (
                            s12_response as response,
                        )

                        assert (
                            response.decompress(
                                storage.read(directory / (directory.name + ".zst")),
                                length=terminal["application_payload_bytes"],
                                expected_hash=bytes.fromhex(
                                    terminal["response_sha256"]
                                ),
                            )
                            == b"{"
                        )
                control_pairs = []
            row = {
                "name": scenario["name"],
                "label": item["label"],
                "observer": scenario["observer"],
                "expected": scenario["expected"],
                "report_complete": report["report_complete"],
                "actual_opener_rejected": rejected,
                "opener_elapsed_ns": clock.now_ns() - opener_started,
                "phase_elapsed_ns": clock.now_ns() - phase_started,
                "cpu_ns": time.process_time_ns() - cpu,
                "periodic_observations": phase_periodic,
                "explicit_stress_hold_ns_included_in_phase": explicit_hold_ns,
                "attempts": attempts - before_attempts,
                "sampler_aggregates": current.sampling_snapshot(),
                "control_pairs": control_pairs,
                "operator_authority": "TEST_ONLY_RECORDS_REAL_READER",
                "report_sha256": operations.digest(report),
            }
            scenario_rows.append(row)
            storage.write(
                args.output / (scenario["name"] + "_RESULT.json"),
                contract.canonical(row),
            )
            if observer is not None:
                observer.boundary()
            phase_deadline.check()
            limit_check()
        assert 170 <= attempts <= LIMITS["attempts"] and len(scenario_rows) == 5
    except BaseException as error:
        family, code, errno = diagnostics.classify(error)
        failure = {"family": family, "code": code, "errno": errno, "stage": active}
    finally:
        try:
            if observer is not None:
                observer.close()
        except BaseException:
            if failure is None:
                failure = {
                    "family": "SUPPLEMENTARY_PERSISTENCE_FAILED",
                    "code": None,
                    "errno": None,
                    "stage": active,
                }
        limit_check()
        # One phase inventory at a time: <=20,000 safe digest entries, never a
        # population-sized cache. Join every retained row to freshly read bytes.
        indexed_phase = None
        event_hashes = {}
        association_count = 0
        unlinked_rows = 0
        association_digest = hashlib.sha256()

        def associate(ordinal, row):
            nonlocal indexed_phase, event_hashes, association_count, unlinked_rows
            limit_check()
            fields = dict(zip(checkpoints.PUBLIC_FIELDS, row, strict=True))
            phase_id = fields["phase_id"]
            assert 1 <= phase_id <= len(data["scenarios"])
            root = args.output / data["scenarios"][phase_id - 1]["name"]
            if fields["event_seq"] is None:
                unlinked_rows += 1
                return
            if indexed_phase != phase_id:
                event_hashes = {}
                for entry in journal.read_array(root / "event_inventory.json"):
                    parts = Path(entry["path"]).parts
                    assert (
                        len(parts) == 4
                        and parts[0] == "segments"
                        and parts[2] == "events"
                    )
                    key = (int(parts[1]), int(Path(parts[3]).stem))
                    assert key not in event_hashes and len(event_hashes) < 20000
                    event_hashes[key] = entry["sha256"]
                indexed_phase = phase_id
            event_raw = storage.read(
                root / "events" / f"{fields['event_seq']:020d}.json"
            )
            assert (
                contract.sha(event_raw).hex()
                == event_hashes[(fields["segment_id"], fields["event_seq"])]
            )
            event = operations.parse(event_raw, operations.EVENT)
            timing.verify_association(row, event, phase_id=phase_id)
            association_digest.update(
                contract.canonical([ordinal, row, contract.sha(event_raw).hex()])
            )
            association_count += 1

        association_verified = False
        try:
            assert observer is not None and observer.snapshot()["persistence_complete"]
            joined = checkpoints.read_prefix(
                args.output / "supplementary_timing", record_consumer=associate
            )
            assert not joined["incomplete"] and unlinked_rows == 0
            association_verified = True
        except BaseException:
            if failure is None:
                failure = {
                    "family": "SUPPLEMENTARY_ASSOCIATION_INCOMPLETE",
                    "code": None,
                    "errno": None,
                    "stage": active,
                }
        storage.write(
            args.output / "TIMING_ASSOCIATION.json",
            contract.canonical(
                {
                    "scope": "SUPPLEMENTARY_EXACT_ORIGINAL_ASSOCIATIONS_NOT_SAMPLING_AUTHORITY",
                    "linked_rows": association_count,
                    "unlinked_rows": unlinked_rows,
                    "verified_complete_retained_associations": association_verified,
                    "association_digest_sha256": association_digest.hexdigest(),
                    "source_sha": args.source_sha,
                    "input_sha256": args.input_sha256,
                }
            ),
        )
        limit_check()
        files = [p for p in args.output.rglob("*") if p.is_file()]
        summary = {
            "scope": SCOPE,
            "source_sha": args.source_sha,
            "input_sha256": args.input_sha256,
            "complete_representative_replay": failure is None
            and len(scenario_rows) == 5
            and association_verified,
            "failure": failure,
            "attempts": attempts,
            "scenarios": scenario_rows,
            "elapsed_before_summary_ns": clock.now_ns() - args.started_ns,
            "peak_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_units": "bytes" if sys.platform == "darwin" else "KiB",
            "file_data_bytes_before_summary": sum(p.stat().st_size for p in files),
            "files_before_summary": len(files),
            "charged_creations_before_summary": creation_count,
            "artifact_budget_before_summary": budget.snapshot(),
            "timing": observer.snapshot()
            if observer is not None
            else {"enabled": False, "persistence_complete": False},
            "nested_metrics": metrics,
            "failures": failures.snapshot(),
            "network_guard": network_guard,
            "native_observer_is_point_in_time_not_entitlement": True,
            "service_capacity_or_scientific_claim": False,
        }
        storage.write(args.output / "summary.json", contract.canonical(summary))
        print(
            contract.canonical(
                {
                    "scope": SCOPE,
                    "complete": summary["complete_representative_replay"],
                    "attempts": attempts,
                    "failure": failure,
                }
            ).decode(),
            end="",
            flush=True,
        )
        storage.write(
            args.output / "REPLAY_TERMINAL.json",
            contract.canonical(
                {
                    "scope": SCOPE,
                    "source_sha": args.source_sha,
                    "input_sha256": args.input_sha256,
                    "complete": summary["complete_representative_replay"],
                    "elapsed_ns": clock.now_ns() - args.started_ns,
                    "deadline_mono_ns": deadline,
                    "completed_mono_ns": clock.now_ns(),
                }
            ),
        )
        limit_check()
        stop_watchdog.set()
        signal.alarm(0)
    return 0 if failure is None and len(scenario_rows) == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())

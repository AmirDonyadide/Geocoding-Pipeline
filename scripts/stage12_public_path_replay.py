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
    "attempts": 107,
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
    scenario_tools = load_module(
        "replay_scenario", source / "scripts/stage12_replay_scenario.py"
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
    access = scenario_tools.AccessGuard(
        allowed=allowed,
        output=args.output,
        proc_self=proc_self,
        cgroup_root=cgroup_root,
        proc_names=native.PROC_NAMES,
        cgroup_names=native.CGROUP_NAMES,
        maximum_creations=LIMITS["creations"],
    )
    sys.addaudithook(access.audit)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(
        resource.RLIMIT_FSIZE, (LIMITS["artifact_bytes"], LIMITS["artifact_bytes"])
    )
    assert args.input.stat().st_size <= 8 * 2**20
    raw = args.input.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == args.input_sha256
    data = json.loads(raw)
    assert contract.canonical(data) == raw and data["scope"] == SCOPE
    assert data["version"] == schema.VERSION
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
        "expected_attempts",
        "diagnostic_source_files",
    }
    assert data["source_sha"] == args.source_sha and data["limits"] == LIMITS
    assert data["scenarios"] == schema.SCENARIOS
    assert data["synthetic_delay_ms"] == {"ordinary": 5, "every_eighth_work": 20}
    assert len(args.source_sha) == 40 and all(
        x in "0123456789abcdef" for x in args.source_sha
    )
    assert data["expected_attempts"] == schema.EXPECTED_ATTEMPTS == 106
    assert set(data["diagnostic_source_files"]) == set(schema.DIAGNOSTIC_PATHS)
    for name, digest in data["diagnostic_source_files"].items():
        assert contract.sha((source / name).read_bytes()).hex() == digest
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
    storage.write(
        args.output / "CARRIED_RESOURCE_SCOPE.json",
        contract.canonical(
            {
                "scope": "PRIOR_JOB_1809317_ONLY_NOT_CURRENT_ENFORCEMENT_OR_ENTITLEMENT",
                "native_record_sha256": "db3445d782bee74be760928c97e26e1186aa7aad4bff86218a0cf5df04d5a6d7",
                "storage_facts_and_existing_requests": "CARRIED_UNCHANGED_NOT_REAUDITED",
                "current_diagnostic_rss_and_artifact_watchdogs": "UNCHANGED_OBSERVED_LIMITS_NOT_NATIVE_ALLOCATION_PROOF",
            }
        ),
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
    observer = None  # Construct one bounded observer before the first scenario.
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
    sequence = scenario_tools.ScenarioSequence(data["scenarios"])
    scenario_rows = sequence.rows
    failure = None
    failures = diagnostics.Failures(clock)
    try:
        for index, scenario in sequence.pending():
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
                        phase_count=len(data["scenarios"]),
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

            def payload_for(work):
                if scenario["expected"] != "COMPLETE" and work["work_id"] == 2:
                    return b"{"
                if work["kind"] == "SERVICE_CONTROL":
                    return contract.canonical(
                        {
                            "type": "FeatureCollection",
                            "features": [],
                            "geocoding": {"version": "INVENTED_CONTROL_ONLY"},
                        }
                    )
                return responses[(item["label"], work["work_id"])]

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
                payload = payload_for(work)
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

            run_error = None
            report = None
            try:
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
            except BaseException as error:
                run_error = error
            verified = {}
            opener_elapsed_ns = 0

            def classify(error):
                family, code, errno = diagnostics.classify(error)
                return {"family": family, "code": code, "errno": errno}

            def note_failure(value):
                nonlocal failure
                sequence.note(dict(value, stage=active))
                if failure is None:
                    failure = sequence.first_failure

            def safety():
                limit_check()
                phase_deadline.check()
                scenario_tools.live_safety(
                    current,
                    root=path,
                    isolation=bool(network_guard),
                    check=phase_deadline.check,
                )

            def verify():
                nonlocal verified
                verified = scenario_tools.verify_closed(
                    path,
                    item,
                    start,
                    validation_sha256=config["public_validation_sha256"],
                    check=phase_deadline.check,
                    expected_payload=payload_for,
                )
                assert verified["campaign"] == report
                assert phase_periodic >= sample_target
                diagnostic_state = failures.snapshot()
                assert diagnostic_state["first_initiating_failure"] is None
                assert diagnostic_state["first_secondary_failure"] is None
                facts = scenario_tools.assess(
                    verified,
                    negative=scenario["expected"] != "COMPLETE",
                    attempts=attempts - before_attempts,
                    item=item,
                    selection=config["capability"],
                )
                if scenario["expected"] == "COMPLETE" and facts["verdict"] == "PASS":
                    assert matrix.gate(verified["block"], item, config["capability"])
                return dict(
                    facts,
                    block_report_sha256=operations.digest(verified["block"]),
                    control_pairs=verified["control_pairs"],
                    sampling=verified["sampling"],
                    source_binding=verified["source_binding"],
                )

            def checkpoint():
                # All sampler/worker/writer work is quiescent. This is independent
                # supplementary I/O, never an authoritative writer reuse.
                try:
                    if current is not None:
                        observer.sampling(current.sampling_snapshot())
                    observer.boundary()
                finally:
                    snap = observer.snapshot()
                    storage.write(
                        args.output / (scenario["name"] + "_TIMING_BEFORE_OPENER.json"),
                        contract.canonical(
                            {
                                "phase_id": index,
                                "source_sha": args.source_sha,
                                "input_sha256": args.input_sha256,
                                "disposition": "PREFIX_ONLY_NOT_FINAL_COVERAGE",
                                "timing": snap,
                            }
                        ),
                    )
                cp = snap["checkpoint"]
                assert (
                    not snap["observer_failure_count"]
                    and not snap["outstanding_traces"]
                )
                assert (
                    cp is not None
                    and not cp["failure_code"]
                    and not cp["persistence_uncertain"]
                )
                assert (
                    not cp["dropped_unpersisted_rows"]
                    and cp["persisted_watermark"] == cp["observed_rows"]
                )
                return snap

            def reopen():
                nonlocal opener_elapsed_ns
                began = clock.now_ns()
                try:
                    with storage.cooperative_io(phase_deadline.check):
                        opened = runtime.reopen_completed(
                            path,
                            profile,
                            plan,
                            start,
                            validation_sha256=config["public_validation_sha256"],
                            control_adapters=controls,
                        )
                        phase_deadline.check()
                    return opened == verified["block"]
                finally:
                    opener_elapsed_ns = clock.now_ns() - began

            def revalidate():
                assert (
                    scenario_tools.fresh_binding(path, check=phase_deadline.check)
                    == verified["source_binding"]
                )

            def persist(kind, row):
                phase_deadline.check()
                limit_check()
                row.update(
                    phase_elapsed_ns=clock.now_ns() - phase_started,
                    cpu_ns=time.process_time_ns() - cpu,
                    opener_elapsed_ns=opener_elapsed_ns,
                )
                with storage.cooperative_io(phase_deadline.check):
                    storage.write(
                        args.output / (scenario["name"] + "_" + kind + ".json"),
                        contract.canonical(row),
                    )

            row = scenario_tools.conclude(
                row={
                    "name": scenario["name"],
                    "label": item["label"],
                    "phase_id": index,
                    "observer": True,
                    "expected": scenario["expected"],
                    "report_complete": report["report_complete"]
                    if report is not None
                    else None,
                    "attempts": attempts - before_attempts,
                    "periodic_observations": phase_periodic,
                    "explicit_stress_hold_ns_included_in_phase": explicit_hold_ns,
                    "sampler_aggregates": current.sampling_snapshot()
                    if current is not None
                    else None,
                    "operator_authority": "TEST_ONLY_RECORDS_REAL_READER",
                    "source_sha": args.source_sha,
                    "input_sha256": args.input_sha256,
                },
                safety=safety,
                verify=verify,
                opener=reopen,
                revalidate=revalidate,
                checkpoint=checkpoint,
                persist=persist,
                classify=classify,
                on_failure=note_failure,
                run_error=run_error,
            )
            sequence.record(row)
            phase_deadline.check()
            limit_check()
        if len(scenario_rows) == len(data["scenarios"]):
            assert schema.EXPECTED_ATTEMPTS <= attempts <= LIMITS["attempts"]
    except BaseException as error:
        family, code, errno = diagnostics.classify(error)
        if failure is None:
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
            and len(scenario_rows) == len(data["scenarios"])
            and association_verified,
            "failure": failure,
            "attempts": attempts,
            "scenarios": scenario_rows,
            "elapsed_before_summary_ns": clock.now_ns() - args.started_ns,
            "peak_rss_native_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "rss_units": "bytes" if sys.platform == "darwin" else "KiB",
            "file_data_bytes_before_summary": sum(p.stat().st_size for p in files),
            "files_before_summary": len(files),
            "charged_creations_before_summary": access.creations,
            "artifact_budget_before_summary": budget.snapshot(),
            "timing": observer.snapshot()
            if observer is not None
            else {"enabled": False, "persistence_complete": False},
            "nested_metrics": metrics,
            "failures": failures.snapshot(),
            "network_guard": network_guard,
            "resource_evidence_scope": "PRIOR_JOB_1809317_ONLY_NOT_CURRENT_ENFORCEMENT_OR_ENTITLEMENT",
            "service_capacity_or_scientific_claim": False,
            "observer_overhead": "UNVERIFIED_NO_MATCHED_COMPARISON",
            "aggregate_disposition": "COMPLETE"
            if failure is None
            and len(scenario_rows) == len(data["scenarios"])
            and association_verified
            else "INCOMPLETE",
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
    return 0 if failure is None and len(scenario_rows) == len(data["scenarios"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

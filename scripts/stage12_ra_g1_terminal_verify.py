"""Read-only post-run verification for the selected synthetic representative.

This is content revalidation in the collection domain, never a replacement for
an original timed opener. Historical monotonic values are compared only to
other originals from that execution. No live PhaseProtocol or supervisor is
manufactured in the collection job.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import hashlib
import os
import sys

VERSION = "stage12_terminal_original_workload_verification_v1"
MAX_READ_BYTES = 32 * 2**30
MAX_READS = 1_000_000
MAX_OPENS = 500_000


def need(value):
    if not value:
        raise RuntimeError("TERMINAL_ORIGINAL_INVALID")


@contextmanager
def bounded_reads(check, charge_read):
    counts = dict(read_calls=0, returned_bytes=0, opens=0)
    active = [True]
    originals = {
        name: getattr(os, name)
        for name in ("read", "pread", "readv", "preadv")
        if hasattr(os, name)
    }

    def audit(event, args):
        if not active[0]:
            return
        if event in ("open", "os.scandir"):
            counts["opens"] += 1
            need(counts["opens"] <= MAX_OPENS)
            if event == "open" and len(args) > 2 and type(args[2]) is int:
                need(not args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in {
            "os.system",
            "os.fork",
            "os.posix_spawn",
            "os.mkdir",
            "os.rename",
            "os.remove",
            "os.rmdir",
            "os.chmod",
            "os.chown",
            "os.link",
            "os.symlink",
            "os.truncate",
            "os.utime",
        }:
            raise RuntimeError("TERMINAL_PROOF_WRITE_OR_EXTERNAL_DENIED")

    def wrap(name, original):
        def called(*args):
            check()
            counts["read_calls"] += 1
            need(counts["read_calls"] <= MAX_READS)
            if name.endswith("v"):
                need(
                    type(args[1]) in (list, tuple)
                    and len(args[1]) <= 32
                    and all(
                        type(part) in (bytes, bytearray, memoryview) for part in args[1]
                    )
                )
            requested = (
                sum(
                    part.nbytes if isinstance(part, memoryview) else len(part)
                    for part in args[1]
                )
                if name.endswith("v")
                else args[1]
            )
            need(
                type(requested) is int
                and requested >= 0
                and counts["returned_bytes"] + requested <= MAX_READ_BYTES
            )
            value = original(*args)
            size = value if name.endswith("v") else len(value)
            counts["returned_bytes"] += size
            need(counts["returned_bytes"] <= MAX_READ_BYTES)
            charge_read(size)
            check()
            return value

        return called

    sys.addaudithook(audit)
    for name, original in originals.items():
        setattr(os, name, wrap(name, original))
    try:
        yield counts
    finally:
        active[0] = False
        for name, original in originals.items():
            setattr(os, name, original)


def _object(io, contract, path, limit=2**20):
    raw = io.original_read(Path(path), limit=limit)
    value = io.metadata(raw)
    need(contract.c.canonical(value) == raw)
    return value


def _module(source, name, source_rows, check, charge_read):
    """Execute only freshly hashed selected code bytes, with no reload race."""
    from types import ModuleType

    selected = [row for row in source_rows if row["path"] == "scripts/" + name + ".py"]
    need(len(selected) == 1 and 0 < selected[0]["bytes"] <= 2**20)
    path = source / selected[0]["path"]

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

    import stat

    chain = []
    need(len(path.parts) <= 80)
    for parent in reversed(path.parents):
        value = parent.lstat()
        need(stat.S_ISDIR(value.st_mode))
        chain.append((parent, identity(value)[:5]))
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size == selected[0]["bytes"])
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    raw = bytearray()
    try:
        need(identity(os.fstat(fd)) == identity(before))
        while len(raw) < before.st_size:
            check()
            part = os.read(fd, min(4096, before.st_size - len(raw)))
            need(bool(part))
            raw.extend(part)
        need(
            not os.read(fd, 1)
            and identity(os.fstat(fd)) == identity(before) == identity(path.lstat())
        )
    finally:
        os.close(fd)
    need(hashlib.sha256(raw).hexdigest() == selected[0]["sha256"])
    for parent, expected in chain:
        need(identity(parent.lstat())[:5] == expected)
    check()
    module = ModuleType("terminal_readonly_" + name)
    module.__file__ = str(path)
    exec(compile(bytes(raw), str(path), "exec"), module.__dict__)
    check()
    return module


def verify_resource(
    root,
    bound_sha,
    selected,
    phase_id,
    deadline,
    io,
    contract,
    check,
    *,
    expected_frozen_sha=None,
    expected_negative=False,
    test_only=False,
):
    """Revalidate typed historical records against fresh current original bytes."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a

    roots = Path(root)
    records = {
        name: _object(io, contract, roots / (name + ".record"), 16384)
        for name in (
            "preopening",
            "opener_return",
            "monitor_terminal",
            "worker_validation",
        )
    }
    closure, opened, terminal, worker = (records[k] for k in records)
    for value in records.values():
        m.validate(value)
        need(value["binding_sha256"] == bound_sha and value["phase_id"] == phase_id)
        if "selection_sha256" in value:
            need(value["selection_sha256"] == contract.digest(selected))
    need(
        closure["outcome"] == "PENDING_OPEN"
        and closure["actual_opener_record_sha256"] is None
        and closure["monitor_coverage"] == "COMPLETE_SELECTED_SCOPE"
        and opened["preopening_closure_sha256"] == contract.digest(closure)
        and opened["validated_monitor_prefix_sha256"]
        == closure["original_observation_prefix_sha256"]
        and opened["frozen_data_inventory_sha256"]
        == closure["original_inventory_sha256"]
        and opened["failure"] is None
        and opened["opener_disposition"]
        == ("EXPECTED_NEGATIVE_REJECTED" if expected_negative else "DATA_OPENED")
        and terminal["opener_return_sha256"] == contract.digest(opened)
        and terminal["prefix_H0_sha256"]
        == closure["original_observation_prefix_sha256"]
        and terminal["disposition"] == "CLOSED_SELECTED_SCOPE"
        and terminal["writer_state"] == "HEALTHY_RELEASED"
        and opened["actual_opener_return_ns"] < deadline
        and terminal["last_ack_ns"] < deadline
    )
    if expected_frozen_sha is not None:
        need(opened["frozen_data_inventory_sha256"] == expected_frozen_sha)
    bootstrap = None
    scope_start = terminal["coverage_start_ns"]
    bootstrap_required = a.bootstrap_role(selected, phase_id) is not None
    need(
        all(
            bootstrap_required == ("bootstrap_evidence_sha256" in value)
            for value in records.values()
        )
    )
    if bootstrap_required:
        need(
            all(
                value.get("bootstrap_evidence_sha256")
                == worker["bootstrap_evidence_sha256"]
                for value in records.values()
            )
        )
        bootstrap = _object(io, contract, roots / "bootstrap_prefix.record", 16384)
        need(contract.digest(bootstrap) == worker["bootstrap_evidence_sha256"])
        scope_start = bootstrap["bootstrap_end_mono_ns"]
        need(terminal["coverage_start_ns"] == scope_start)
    seed = contract.digest(
        dict(
            schema_version="stage12_resource_monitor_seed_ra_g1_v1",
            binding_sha256=bound_sha,
            selection_sha256=contract.digest(selected),
            phase_id=phase_id,
        )
    )
    coverage = m.Coverage(
        binding_sha256=bound_sha,
        selection_sha256=contract.digest(selected),
        phase_id=phase_id,
        seed_sha256=seed,
        selected=selected,
        scope_start_ns=scope_start,
    )
    names = set()
    prefix = None
    first = None
    stream_hash = hashlib.sha256()
    for row in m.read_observations(
        roots / "observations.bin",
        maximum_rows=selected["limits"]["monitor_rows"],
        check=check,
    ):
        if first is None:
            first = row
        identity = row["visible_identity_inventory_sha256"]
        original = m.read_original_observation(
            roots / "originals" / (identity + ".record"),
            expected_sha256=identity,
            check=check,
            test_only=test_only,
        )
        m.validate_original_observation(
            original, observation=row, allow_synthetic=test_only
        )
        names.add(identity + ".record")
        coverage.add(row)
        stream_hash.update(m.pack_observation(row))
        if coverage.seq == closure["last_seq"]:
            prefix = coverage.inventory_sha256()
            need(
                contract.digest(row["counters"]) == closure["counter_totals_sha256"]
                and coverage.max_gap == closure["max_observed_gap_ns"]
            )
    check()
    actual_names = set()
    with os.scandir(roots / "originals") as scan:
        for entry in scan:
            check()
            need(entry.is_file(follow_symlinks=False) and not entry.is_symlink())
            actual_names.add(entry.name)
            need(len(actual_names) <= selected["limits"]["monitor_rows"])
    need(
        actual_names == names
        and coverage.head == terminal["final_observation_sha256"]
        and coverage.seq == terminal["last_seq"]
        and coverage.inventory_sha256() == terminal["full_monitor_inventory_sha256"]
        and prefix == closure["original_observation_prefix_sha256"]
        and coverage.max_gap == terminal["max_gap_ns"]
        and coverage.last_exit == terminal["final_observation_ns"]
    )
    info = (roots / "observations.bin").stat(follow_symlinks=False)
    actual_source = dict(
        device=info.st_dev,
        inode=info.st_ino,
        mode=info.st_mode,
        uid=info.st_uid,
        gid=info.st_gid,
        nlink=info.st_nlink,
        bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
        sha256=stream_hash.hexdigest(),
    )
    need(contract.digest(actual_source) == worker["monitor_source_identity_sha256"])
    coverage.require_complete(
        opener_return_ns=opened["actual_opener_return_ns"],
        last_ack_ns=terminal["last_ack_ns"],
    )
    # Immutable value projection only; no live PhaseProtocol/clock is constructed.
    history = SimpleNamespace(
        binding=bound_sha,
        selection=contract.digest(selected),
        phase=phase_id,
        closure=closure,
        opener=opened,
        terminal=terminal,
        deadline=deadline,
        bootstrap_evidence_sha256=contract.digest(bootstrap) if bootstrap else None,
    )
    e.validate_worker_validation(worker, protocol=history)
    if bootstrap:
        a.validate_bootstrap_evidence(
            bootstrap, selected, binding_sha256=bound_sha, root=roots, first=first
        )
    check()
    return dict(
        phase_id=phase_id,
        rows=coverage.seq,
        head_sha256=coverage.head,
        maximum_gap_ns=coverage.max_gap,
        current_content_revalidated=True,
        historical_identity_not_a_current_environment_claim=True,
    )


def verify_original_workload(selection, *, check, charge_read):
    """Fresh original readers; no writes, clocks or eligibility are repaired."""
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operations as contract,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_recovery as recovery,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_journal as journal,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_operational_audit as oa,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as ap

    need(
        type(selection) is dict
        and selection.get("scope") == "REPRESENTATIVE_NO_SERVICE"
        and selection.get("version")
        == "stage12_ra_g1_rep_first64_512_allocation_selection_v1"
        and type(selection.get("source_sha")) is str
        and len(selection["source_sha"]) == 40
        and set(selection["source_sha"]) <= set("0123456789abcdef")
    )
    paths = selection["paths"]
    root, source = Path(paths["output"]), Path(paths["source"])
    # Import the reviewed source-owned public control adapter before read-only audit.
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix

    result = dict(
        schema=VERSION,
        complete=False,
        scope="REPRESENTATIVE_NO_SERVICE",
        source_sha=selection["source_sha"],
        allocation_selection_sha256=contract.digest(selection),
        status="ORIGINAL_WORKLOAD_INCOMPLETE",
        original_timed_acceptance_repaired=False,
        current_environment_or_old_clock_equivalence_asserted=False,
    )
    with bounded_reads(check, charge_read) as counts, io.cooperative_io(check):
        check()
        if not (root / "summary.json").is_file() or not Path(paths["tail"]).is_file():
            result["counts"] = dict(counts)
            return result
        controller = _module(
            source,
            "stage12_ra_g1_allocation",
            selection["source_files"],
            check,
            charge_read,
        )
        data = _object(io, contract, paths["input"], 4 * 2**20)
        summary = _object(io, contract, root / "summary.json")
        tail = _object(io, contract, paths["tail"])
        state = _object(io, contract, paths["supervisor_state"], 16384)
        need(
            data["source_sha"]
            == summary["source_sha"]
            == tail["source_sha"]
            == selection["source_sha"]
            and summary["input_sha256"] == controller.digest(data)
            and tail["selection_sha256"] == controller.digest(selection)
            and tail["summary_sha256"] == controller.digest(summary)
            and tail["input_sha256"] == controller.digest(data)
            and tail["version"] == "stage12_ra_g1_allocation_terminal_v1"
            and state["source_sha"] == selection["source_sha"]
            and state["selection_sha256"] == controller.digest(selection)
            and type(tail["completed_mono_ns"]) is int
            and type(tail["deadline_mono_ns"]) is int
            and tail["completed_mono_ns"]
            < tail["deadline_mono_ns"]
            <= state["deadline_mono_ns"]
        )
        result.update(
            summary_sha256=controller.digest(summary),
            input_sha256=controller.digest(data),
        )
        if (
            summary["complete"] is not True
            or tail["status"] != "COMPLETE_REPRESENTATIVE_NO_SERVICE"
        ):
            result["counts"] = dict(counts)
            return result
        # Reuse the actual source validator with a read-only validation view;
        # no admission, authority, current supervisor or clock is constructed.
        source_view = SimpleNamespace(
            s=selection, check=check, read_charge=lambda calls, size: None
        )
        controller.Run.sources(source_view)
        child = _object(io, contract, paths["worker_return"], 16384)
        context = _object(io, contract, paths["context"], 65536)
        controller.validate_wait_record(
            child,
            source_sha=selection["source_sha"],
            allocation_selection_sha256=contract.digest(selection),
            supervisor_pid=context["supervisor"]["pid"],
        )
        need(tail["supervisor_wait_sha256"] == controller.digest(child))
        need(
            state["status"] == "COMPLETE_REPRESENTATIVE_NO_SERVICE"
            and type(state["exit_code"]) is int
            and state["exit_code"] == 0
            and 106 <= summary["attempts"] <= 107
            and len(summary["phases"]) == 4
            and len(summary["resource_sessions"]) == 5
            and len(tail["resource_terminal_records"]) == 5
            and len(tail["administrative_terminal_records"]) == 3
        )
        for row in (
            tail["resource_terminal_records"] + tail["administrative_terminal_records"]
        ):
            from safe_geocoding_pipeline.preprocessing.stages import (
                s12_ra_g1_monitor as m,
            )

            m.validate(row)
            need(
                row["disposition"]
                in ("COMPLETE_SELECTED_SCOPE", "EXPECTED_NEGATIVE_VERIFIED")
            )
        diagnostic = _module(
            source,
            "stage12_ra_g1_diagnostic",
            selection["source_files"],
            check,
            charge_read,
        )
        diagnostic.validate_envelope(data)
        originals = tail["counter_originals"]
        need(type(originals) is dict and len(originals) <= 32)
        for identity, value in originals.items():
            need(
                identity == controller.digest(value)
                and value["worker_prefix"] == summary["resource_counters"]
            )
        for terminal in (
            tail["resource_terminal_records"] + tail["administrative_terminal_records"]
        ):
            need(terminal["root_counter_watermarks_sha256"] in originals)
        config = data["configuration"]
        phases = []
        frozen_data = {}
        for item, phase in zip(config["campaigns"], data["phases"], strict=True):
            check()
            campaign = root / item["label"]
            if item["label"] == "malformed":
                stopped = ap.parse(io.read(campaign / "snapshot.json"), ap.SNAPSHOT)
                need(stopped["disposition"] == "STOPPED")
                original_state = recovery.replay(
                    journal.read_events(
                        campaign, ap.digest(phase["start"]), contract=ap
                    ),
                    contract=ap,
                )
                block = io.metadata(io.read(campaign / "block_report.json"))
                recovery.snapshot_evidence(
                    campaign, stopped, original_state, ap.digest(block), check=check
                )
                diagnostic.expected_stopped_rejection(
                    lambda: runtime.reopen_completed(
                        campaign,
                        item["profile"],
                        item["plan"],
                        phase["start"],
                        validation_sha256=config["public_validation_sha256"],
                    ),
                    check,
                )
                for event in journal.read_events(
                    campaign, ap.digest(phase["start"]), contract=ap
                ):
                    if event["kind"] != "ATTEMPT_FINALIZED":
                        continue
                    work = io.metadata(
                        io.read(
                            campaign / "work" / f"{event['body']['work_id']:020d}.json"
                        )
                    )
                    name = audit.name_for(work["work_id"], event["body"]["attempt"])
                    attempt_root = campaign / "attempts" / name
                    adapter = runtime.validation_for(config["public_validation_sha256"])
                    terminal = audit.reopen(
                        attempt_root,
                        name,
                        validator=adapter.validator(work, attempt_root),
                        context=oa.DataContext(adapter),
                    )
                    need(terminal["outcome"] == "CONTRACT_FAILURE")
                opened = "EXPECTED_NEGATIVE_REJECTED"
            else:
                opened = runtime.reopen_completed(
                    campaign,
                    item["profile"],
                    item["plan"],
                    phase["start"],
                    validation_sha256=config["public_validation_sha256"],
                    control_adapters=matrix.adapters(item["plan"]),
                )
                if item["label"] == "controls8":
                    need(len(matrix.verify_controls(campaign, item["plan"])) == 4)
            need(
                (campaign / "_SEGMENT_SEALED").is_file()
                and (campaign / "_WRITER_RELEASED.json").is_file()
            )
            frozen_data[len(phases) + 1] = contract.digest(
                _object(io, contract, campaign / "campaign_report.json")
            )
            phases.append(
                dict(
                    label=item["label"],
                    original_data_reopened=True,
                    report_sha256=ap.digest(opened)
                    if isinstance(opened, dict)
                    else None,
                )
            )
        resource_rows = []
        need(
            [row["phase_id"] for row in summary["resource_sessions"]]
            == list(range(1, 6))
        )
        worker_deadline = min(
            state["deadline_mono_ns"],
            summary["resource_sessions"][0]["phase_start_ns"] + 7200 * 10**9,
        )
        selected = None
        for row in summary["resource_sessions"]:
            item = config["campaigns"][min(row["phase_id"], 4) - 1]
            bound_sha = item["profile"]["sampling_runtime_bound_sha256"]
            bound = _object(
                io,
                contract,
                Path(paths["binding"]) / "resource_evidence" / (bound_sha + ".record"),
                65536,
            )
            need(
                contract.digest(bound) == bound_sha
                and row["binding_sha256"] == bound_sha
            )
            selected = _object(
                io,
                contract,
                Path(paths["binding"])
                / "resource_evidence"
                / (bound["selection_sha256"] + ".record"),
                65536,
            )
            need(
                contract.digest(selected)
                == bound["selection_sha256"]
                == row["selection_sha256"]
            )
            need(Path(row["root"]) == root / (row["label"] + "_resources"))
            originals = {
                name: _object(
                    io, contract, Path(row["root"]) / (name + ".record"), 16384
                )
                for name in (
                    "preopening",
                    "opener_return",
                    "monitor_terminal",
                    "worker_validation",
                )
            }
            controller.validate_original_phase_times(
                row, originals, selected, worker_deadline
            )
            frozen = (
                contract.digest(
                    dict(phases=summary["phases"], timing=summary["timing"])
                )
                if row["phase_id"] == 5
                else frozen_data[row["phase_id"]]
            )
            resource_rows.append(
                verify_resource(
                    row["root"],
                    bound_sha,
                    selected,
                    row["phase_id"],
                    row["phase_deadline_ns"],
                    io,
                    contract,
                    check,
                    expected_frozen_sha=frozen,
                    expected_negative=(row["label"] == "malformed"),
                )
            )

        def associate(ordinal, row):
            check()
            phase_id = (
                row["phase_id"]
                if row["row_kind"] == "PERIODIC_ASYNC"
                else row["legacy_row"][0]
            )
            need(1 <= phase_id <= 4)
            campaign = root / config["campaigns"][phase_id - 1]["label"]
            seq = (
                row["sample_event_seq"]
                if row["row_kind"] == "PERIODIC_ASYNC"
                else row["legacy_row"][4]
            )
            event = ap.parse(
                io.read(campaign / "events" / f"{seq:020d}.json", limit=4096), ap.EVENT
            )
            ack = (
                ap.parse(
                    io.read(
                        campaign / "events" / f"{row['ack_event_seq']:020d}.json",
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

        checkpoint = summary["timing"]["checkpoint"]
        reopened = cp.read_prefix(
            root / "public_path_timing",
            timing_schema=cp.RA_SCHEMA,
            expected_binding=checkpoint["timing_binding"],
            expected_snapshot=checkpoint,
            record_consumer=associate,
        )
        check()
        need(
            not reopened["incomplete"]
            and summary["timing"]["final_timing_coverage_complete"]
        )
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_ra_g1_execution as execution,
        )

        for role, phase_id in (("collector", 6), ("review", 7), ("binder", 8)):
            admin_root = Path(paths["allocation_root"]) / (role + "_resources")
            admin_bound = _object(
                io, contract, admin_root / "admin_binding.record", 16384
            )
            execution.AdministrativePhaseSession.validate_binding(None, admin_bound)
            need(
                admin_bound["role"] == role.upper()
                and admin_bound["scope"] == "REPRESENTATIVE_NO_SERVICE"
                and admin_bound["selection_sha256"] == contract.digest(selected)
                and admin_bound["supervisor_context_sha256"] == contract.digest(context)
                and admin_bound["deadline_mono_ns"] <= state["deadline_mono_ns"]
                and admin_bound["deadline_mono_ns"]
                <= admin_bound["scope_start_mono_ns"]
                + selection["limits"][role + "_seconds"] * 10**9
                and admin_bound["phase_id"] == phase_id
                and admin_bound["source_git_sha"] == selection["source_sha"]
            )
            resource_rows.append(
                verify_resource(
                    admin_root,
                    contract.digest(admin_bound),
                    selected,
                    phase_id,
                    admin_bound["deadline_mono_ns"],
                    io,
                    contract,
                    check,
                )
            )
        result.update(
            complete=True,
            status="FRESH_ORIGINAL_CONTENT_AND_TIMED_RECORDS_VERIFIED",
            data_phases=phases,
            resource_phases=resource_rows,
            timing_prefix_sha256=contract.digest(reopened),
            counts=dict(counts),
        )
    check()
    return result


# Pure, source-bound gate for independently reviewed collection qualification.
# Runtime callers must freshly read the canonical bundle and pin the genuine
# independent review hash. This function cannot authenticate a human issuer.
QUALIFICATION_VERSION = "stage12_terminal_collection_qualification_v1"


def _q_canonical(value):
    import json
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _q_digest(value):
    return hashlib.sha256(_q_canonical(value)).hexdigest()


def _q_fields(value, keys):
    need(type(value) is dict and set(value) == set(keys.split()))


def _q_hash(value, size=64):
    need(type(value) is str and len(value) == size and set(value) <= set("0123456789abcdef") and set(value) != {"0"})
    return value


def _q_uint(value):
    need(type(value) is int and value >= 0)
    return value


def _q_domain(value):
    import re
    _q_fields(value, "host boot_id mount_namespace session_nonce session_pid")
    need(type(value["host"]) is str and re.fullmatch(r"[A-Za-z0-9_.-]{1,255}", value["host"]))
    need(type(value["boot_id"]) is str and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", value["boot_id"]))
    need(type(value["mount_namespace"]) is str and re.fullmatch(r"mnt:\[[0-9]{1,20}\]", value["mount_namespace"]))
    _q_hash(value["session_nonce"],32)
    need(_q_uint(value["session_pid"]) > 0)


REMOTE_DIRECTORY_SCOPE = "stage12_task_remote_directory_identity_v1"
REMOTE_TRANSPORT_VERSION = "stage12_same_session_transfer_v3_remote_directory_identity"
REMOTE_QUALIFICATION_VERSION = "stage12_terminal_collection_qualification_remote_directory_v2"
REMOTE_READY_VERSION = "stage12_terminal_remote_directory_transport_ready_v3"


def _q_transfer(evidence, expected, *, remote_directory_scope=None):
    import stat
    need(remote_directory_scope is None or remote_directory_scope == REMOTE_DIRECTORY_SCOPE)
    selected = remote_directory_scope is not None
    _q_fields(evidence, "version domain_before domain_after ancestors files exit_code observed_joined" + (" remote_directory_scope" if selected else ""))
    if selected:
        need(evidence["remote_directory_scope"] == REMOTE_DIRECTORY_SCOPE)
    need(evidence["version"] == (REMOTE_TRANSPORT_VERSION if selected else "stage12_same_session_transfer_v2")
         and type(evidence["exit_code"]) is int and evidence["exit_code"] == 0 and evidence["observed_joined"] is True)
    _q_domain(evidence["domain_before"])
    _q_domain(evidence["domain_after"])
    need(evidence["domain_before"] == evidence["domain_after"])
    need(type(evidence["ancestors"]) is list and 1 <= len(evidence["ancestors"]) <= 1280)
    ancestors = set()
    for row in evidence["ancestors"]:
        _q_fields(row,"path before after")
        need(type(row["path"]) is str and row["path"].startswith("/") and ".." not in Path(row["path"]).parts)
        need(row["path"] not in ancestors)
        ancestors.add(row["path"])
        for identity in (row["before"],row["after"]):
            need(type(identity) is list and len(identity) == 9)
            for n in identity:
                _q_uint(n)
            need(stat.S_ISDIR(identity[2]))
        need(row["before"][:5 if selected else 6] == row["after"][:5 if selected else 6])
    need(type(evidence["files"]) is list and len(evidence["files"]) == len(expected))
    for row, target in zip(evidence["files"],expected,strict=True):
        _q_fields(row,"label path before after bytes sha256")
        need({k:row[k] for k in ("label","path","bytes","sha256")} == target)
        need(type(row["before"]) is list and len(row["before"]) == 9 and row["before"] == row["after"])
        for n in row["before"]:
            _q_uint(n)
        info=row["before"]
        need(stat.S_ISREG(info[2]) and stat.S_IMODE(info[2]) == 0o600 and info[5] == 1 and info[6] == row["bytes"])
        need(all(str(parent) in ancestors for parent in Path(row["path"]).parents))
        _q_hash(row["sha256"])


def _q_open(value, ready):
    _q_fields(value,"version status selection_sha256 archive_sha256 summary actual_read_bytes actual_read_calls entered_epoch_ns completed_epoch_ns source_identity native_or_scientific_acceptance")
    need(value["version"] == "stage12_readonly_collection_archive_open_v1" and value["status"] == "COMPLETE"
         and value["selection_sha256"] == ready["context"]["selection_sha256"]
         and value["archive_sha256"] == ready["artifacts"][0]["sha256"] and value["native_or_scientific_acceptance"] is False)
    for key in ("actual_read_bytes","actual_read_calls","entered_epoch_ns","completed_epoch_ns"):
        _q_uint(value[key])
    need(value["actual_read_bytes"] <= 8*2**30 and value["actual_read_calls"] <= 262144)
    need(value["entered_epoch_ns"] <= value["completed_epoch_ns"] < ready["context"]["overall_deadline_epoch_ns"])
    _q_fields(value["summary"],"members payload_bytes manifest_bytes manifest_sha256")
    for key in ("members","payload_bytes","manifest_bytes"):
        _q_uint(value["summary"][key])
        need(value["summary"][key] <= ready["collection_selection"]["limits"][key])
    _q_hash(value["summary"]["manifest_sha256"])
    need(value["summary"]["manifest_sha256"] == ready["artifacts"][1]["sha256"] == ready["artifacts"][2]["sha256"])
    need(type(value["source_identity"]) is list and len(value["source_identity"]) == 9)
    for n in value["source_identity"]:
        _q_uint(n)


def validate_qualification(bundle, *, expected_window, expected_original_source_git_sha,
                           expected_original_job_id, expected_original_selection_sha256,
                           expected_collector_source_git_sha, expected_qualification_review_sha256,
                           expected_remote_directory_scope=None):
    """Validate freshly read complete originals; never qualify the failed source B."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    need(expected_remote_directory_scope is None or expected_remote_directory_scope == REMOTE_DIRECTORY_SCOPE)
    selected_remote = expected_remote_directory_scope is not None
    _q_fields(bundle,"version window review final provisional ready receipt ack terminal index transport opener" + (" remote_directory_scope" if selected_remote else ""))
    need(len(_q_canonical(bundle)) <= 65536 and bundle["version"] == (REMOTE_QUALIFICATION_VERSION if selected_remote else QUALIFICATION_VERSION))
    if selected_remote:
        need(bundle["remote_directory_scope"] == expected_remote_directory_scope)
    window=bundle["window"]
    need(window["scope"] == "TERMINAL_COLLECTION_NO_SERVICE")
    need({k:v for k,v in window.items() if k != "scope"} == {k:v for k,v in expected_window.items() if k != "scope"})
    windows.validate_window(window,scope="TERMINAL_COLLECTION_NO_SERVICE",
                            now_epoch_ns=windows.epoch_ns(windows.WINDOW_START),required_remaining_seconds=12240)
    for sha in (expected_original_source_git_sha,expected_collector_source_git_sha):
        _q_hash(sha,40)
    _q_hash(expected_original_selection_sha256)
    _q_hash(expected_qualification_review_sha256)
    need(expected_original_source_git_sha == windows.ORIGINAL_SOURCE and expected_original_job_id == int(windows.ORIGINAL_JOB)
         and expected_original_selection_sha256 == windows.ORIGINAL_SELECTION
         and expected_collector_source_git_sha != expected_original_source_git_sha)
    ready, receipt, ack = (bundle[k] for k in ("ready","receipt","ack"))
    final, provisional, terminal, index, transport, review = (bundle[k] for k in ("final","provisional","terminal","index","transport","review"))
    ctx=ready["context"]
    need(ready["version"] == (REMOTE_READY_VERSION if selected_remote else "stage12_terminal_same_domain_transport_ready_v2")
         and ready["scope"] == ctx["scope"] == "NATIVE_SYNTHETIC_TERMINAL"
         and ctx["version"] == provisional["version"] == ack["version"] == "stage12_terminal_same_domain_pair_v2"
         and ctx["collection_purpose"] == "QUALIFICATION" and ctx["window"] == window)
    if selected_remote:
        need(ctx.get("remote_directory_scope") == REMOTE_DIRECTORY_SCOPE
             and ctx.get("transport_evidence_version") == REMOTE_TRANSPORT_VERSION)
    else:
        need("remote_directory_scope" not in ctx and "transport_evidence_version" not in ctx)
    need(ctx["original_job_id"] == expected_original_job_id
         and ctx["original_source_git_sha"] == expected_original_source_git_sha
         and ctx["original_workload_selection_sha256"] == expected_original_selection_sha256
         and ctx["collection_source_git_sha"] == expected_collector_source_git_sha
         and type(ctx["collection_job_id"]) is int and ctx["collection_job_id"] > 0
         and ctx["collection_job_id"] not in (expected_original_job_id,1813045)
         and ctx["original_scheduler_state"] == "FAILED" and ctx["original_exit_code"] != 0)
    _q_hash(ctx["original_producer_sha256"])
    need(ctx["original_producer_path"] == ctx["original_source_root"] + "/scripts/stage12_ra_g1_allocation.py")
    need(_q_digest(ready["collection_selection"]) == ctx["selection_sha256"])
    need(provisional["context"] == ctx and provisional["status"] == "PROVISIONAL_INTEGRITY_COMPLETE_PENDING_TERMINAL_LOGS_AND_REVIEW"
         and provisional["children_joined"] is True and provisional["exits"] == {"receive":0,"export":0}
         and provisional["local_transport_and_hash_receipt_verified"] is True
         and provisional["candidate_native_eligible"] is False)
    for name in ("ready","receipt","ack"):
        key={"ready":"ready_sha256","receipt":"receipt_sha256","ack":"receipt_ack_sha256"}[name]
        need(provisional[key] == _q_digest(bundle[name]))
    need(receipt["version"] == "stage12_terminal_same_domain_local_retention_v2"
         and receipt["ready_sha256"] == _q_digest(ready) and receipt["selection_sha256"] == ctx["selection_sha256"])
    need(ack["status"] == "RETENTION_RECEIPT_DURABLY_ACKNOWLEDGED" and ack["receipt"] == receipt
         and ack["receipt_sha256"] == _q_digest(receipt) and ack["ready_sha256"] == _q_digest(ready))
    need(terminal["version"] == "stage12_terminal_collection_scheduler_v1"
         and terminal["scheduler_state"] == "COMPLETED" and terminal["exit_code"] == "0:0"
         and terminal["source_git_sha"] == expected_collector_source_git_sha
         and terminal["binding_sha256"] == ctx["binding_sha256"])
    need(terminal["start_epoch_ns"] <= ctx["entry_epoch_ns"] <= terminal["end_epoch_ns"] <= terminal["observed_epoch_ns"]
         <= review["reviewed_epoch_ns"] < ctx["overall_deadline_epoch_ns"]
         and ctx["entry_epoch_ns"] + 12240*10**9 <= windows.epoch_ns(windows.WINDOW_END))
    need(final["version"] == "stage12_terminal_same_domain_final_log_verification_v2"
         and final["status"] == "COLLECTION_INTEGRITY_COMPLETE"
         and final["local_retained_artifacts_freshly_reopened"] is True
         and final["candidate_native_eligible"] is False
         and final["provisional_sha256"] == _q_digest(provisional)
         and final["terminal_sha256"] == _q_digest(terminal) and final["log_index_sha256"] == _q_digest(index)
         and final["original_workload_selection_sha256"] == expected_original_selection_sha256)
    for value in (receipt,ack,terminal,final,transport):
        need(value["collection_job_id"] == ctx["collection_job_id"])
    for value in (receipt,ack,final,transport):
        need(value["original_job_id"] == expected_original_job_id and value["native_or_scientific_acceptance"] is False)
    need(transport["version"] == ("stage12_terminal_remote_directory_bounded_transport_v3" if selected_remote else "stage12_terminal_same_domain_bounded_transport_v2")
         and transport["status"] == "LOCAL_STREAMS_HASHED_AWAITING_NATIVE_ACK"
         and transport["ready_sha256"] == _q_digest(ready) and transport["receipt_sha256"] == _q_digest(receipt)
         and transport["transport_evidence"] == receipt["transport_evidence"])
    _q_transfer(receipt["transport_evidence"],[{k:r[k] for k in ("label","path","bytes","sha256")} for r in ready["artifacts"]], remote_directory_scope=expected_remote_directory_scope)
    need(index["version"] == "stage12_terminal_same_domain_log_copies_v2"
         and index["context_sha256"] == _q_digest(ctx)
         and terminal["end_epoch_ns"] <= index["transport_start_epoch_ns"] <= index["transport_complete_epoch_ns"] <= final["observed_complete_epoch_ns"])
    need([{k:r[k] for k in ("label","remote_path")} for r in index["logs"]] == [dict(label=r["label"],remote_path=r["path"]) for r in ctx["external_logs"]])
    _q_transfer(index["transport_evidence"],[dict(label=r["label"],path=r["remote_path"],bytes=r["bytes"],sha256=r["sha256"]) for r in index["logs"]], remote_directory_scope=expected_remote_directory_scope)
    for row, evidence in zip(index["logs"],index["transport_evidence"]["files"],strict=True):
        need(row["source_identity_before"] == evidence["before"] == row["source_identity_after"] == evidence["after"])
    _q_open(receipt["whole_collection_opener"],ready)
    _q_open(bundle["opener"],ready)
    need(bundle["opener"] == final["whole_collection_opener"]
         and terminal["end_epoch_ns"] <= bundle["opener"]["entered_epoch_ns"]
         and receipt["whole_collection_opener"]["completed_epoch_ns"] <= receipt["local_complete_epoch_ns"]
         and receipt["local_complete_epoch_ns"] < ctx["parent_deadline_epoch_ns"])
    _q_fields(review,"version scope status collection_job_id collection_source_git_sha original_job_id original_source_git_sha original_selection_sha256 final_sha256 ready_sha256 receipt_ack_sha256 terminal_sha256 index_sha256 transport_sha256 opener_sha256 reviewed_epoch_ns reviewer_role independent_review")
    need(review["version"] == "stage12_terminal_collection_qualification_review_v1" and review["scope"] == window["scope"]
         and review["status"] == "PASS" and review["reviewer_role"] == "INDEPENDENT_COLLECTION_QUALIFICATION"
         and review["independent_review"] is True and _q_digest(review) == expected_qualification_review_sha256)
    need(review["collection_job_id"] == ctx["collection_job_id"] and review["collection_source_git_sha"] == expected_collector_source_git_sha
         and review["original_job_id"] == expected_original_job_id and review["original_source_git_sha"] == expected_original_source_git_sha
         and review["original_selection_sha256"] == expected_original_selection_sha256)
    for name,key in (("final","final_sha256"),("ready","ready_sha256"),("ack","receipt_ack_sha256"),("terminal","terminal_sha256"),
                     ("index","index_sha256"),("transport","transport_sha256"),("opener","opener_sha256")):
        need(review[key] == _q_digest(bundle[name]))
    return bundle

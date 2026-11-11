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

"""B2 clean same-window reconciliation; no public conversion or unclean repair."""

from __future__ import annotations
import json
import hashlib
from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_reporting as reporting
from . import s12_b2_inventory as metadata
from . import s12_public_journal as j
from . import s12_public_recovery as replay_engine
from . import s12_storage as io


def _lineage(root, plan):
    if "history_limits" in plan:
        from . import s12_paged_history as history
        return history.lineage(root, plan["sampling_budget"]["maximum_segments"])
    return metadata.lineage(root, plan["budgets"]["administrative_operations"])


def events(root, start, plan):
    """Fresh original event chain, finite disk ordering, no population list."""
    from . import s12_b2_operations as operations

    o = operations.for_start(start)
    last, segment, epoch, mono, closed, seq = None, 0, None, 0, True, 0
    amounts = plan["budgets"]
    for node in _lineage(root, plan):
        if getattr(o, "PAGED_HISTORY", False):
            from . import s12_paged_history as history

            paths = history.event_paths(node / "events", plan["history_limits"])
        else:
            paths = metadata.ordered_files(
                node / "events",
                max_files=amounts["event_count"],
                max_scratch_bytes=operations.parse_selected(
                    io.read(node / "profile.json")
                )["resources"]["fixed_campaign_disk_bound_bytes"],
            )
        for path in paths:
            seq += 1
            b.require(
                seq <= amounts["event_count"]
                and path.parent == node / "events"
                and path.name == f"{seq:020d}.json",
                "B2_EVENT_MEMBERSHIP",
            )
            raw = io.read(path)
            obj = o.parse(raw, o.EVENT)
            b.require(
                obj["seq"] == seq
                and obj["previous_event_sha256"] == last
                and obj["campaign_start_sha256"] == b.digest(start),
                "B2_EVENT_CHAIN",
            )
            if obj["kind"] == "SEGMENT_OPEN":
                b.require(
                    closed
                    and obj["segment_id"] == segment + 1
                    and obj["epoch_id"] != epoch,
                    "B2_EVENT_CHAIN",
                )
                segment, epoch, mono, closed = (
                    obj["segment_id"],
                    obj["epoch_id"],
                    0,
                    False,
                )
            b.require(
                not closed
                and obj["segment_id"] == segment
                and obj["epoch_id"] == epoch
                and obj["mono_ns"] >= mono,
                "B2_EVENT_CHAIN",
            )
            if obj["kind"] == "SEGMENT_CLOSE":
                closed = True
            last, mono = b.sha(raw).hex(), obj["mono_ns"]
            yield obj


def _segment_inventory(node, area, plan):
    b.require(area in ("events", "attempts"), "B2_METADATA_ROLE")
    role = "event_inventory.json" if area == "events" else "attempt_inventory.json"
    bound = metadata.array_bounds(plan, role)
    admission = b.parse(
        io.read(node / "segment_admission.json"), "stage12_segment_admission_b2_v1"
    )
    segment = admission["segment_id"]
    if "history_limits" in plan:
        from . import s12_paged_history as history

        paths = history.ordered_files(node / area, plan["history_limits"])
    else:
        paths = metadata.ordered_files(
            node / area,
            max_files=bound["max_rows"],
            max_scratch_bytes=o.parse_selected(io.read(node / "profile.json"))[
                "resources"
            ]["fixed_campaign_disk_bound_bytes"],
        )
    count = 0
    for path in paths:
        count += 1
        b.require(count <= bound["max_rows"], "B2_INVENTORY_BOUND")
        yield {
            "path": f"segments/{segment:020d}/{area}/{path.relative_to(node / area)}",
            "sha256": b.sha(io.read(path)).hex(),
        }


def inventory(root, area, plan):
    role = "event_inventory.json" if area == "events" else "attempt_inventory.json"
    max_rows, count = metadata.array_bounds(plan, role)["max_rows"], 0
    for node in _lineage(root, plan):
        for row in _segment_inventory(node, area, plan):
            count += 1
            b.require(count <= max_rows, "B2_INVENTORY_BOUND")
            yield row


def inventory_heads(root, area, plan):
    """All exact canonical prefix hashes in one fresh original traversal."""
    role = "event_inventory.json" if area == "events" else "attempt_inventory.json"
    max_rows, count = metadata.array_bounds(plan, role)["max_rows"], 0
    fingerprint = hashlib.sha256(b"[")
    heads = {}
    for node in _lineage(root, plan):
        for row in _segment_inventory(node, area, plan):
            b.require(count < max_rows, "B2_INVENTORY_BOUND")
            if count:
                fingerprint.update(b",")
            fingerprint.update(b.canonical(row)[:-1])
            count += 1
        prefix = fingerprint.copy()
        prefix.update(b"]\n")
        heads[str(node)] = prefix.hexdigest()
    return heads


def _reopen(
    root,
    start,
    profile,
    plan,
    *,
    works,
    verify_receipt,
    scratch,
    authority,
    require_paused=False,
):
    """Read every predecessor; all retained sources must match sealed identities."""
    from . import s12_b2_operations as operations

    o = operations.for_profile(profile)
    o.verify_authorities(profile, plan, start, authority)
    b.require(
        io.read(root / "campaign_start.json") == b.canonical(start), "B2_START_BINDING"
    )
    snap = o.parse(io.read(root / "snapshot.json"), o.SNAPSHOT)
    b.require(
        io.read(root / "_SEGMENT_SEALED", limit=0) == b""
        and snap["campaign_start_sha256"] == b.digest(start),
        "B2_RECOVERY_UNSEALED",
    )
    if require_paused:
        b.require(
            snap["disposition"] == "PAUSED_CLEAN"
            and snap["controller"]["resume_eligible"],
            "B2_UNCLEAN_RECOVERY_BLOCKED",
        )
    b.require(
        snap["disposition"] in ("PAUSED_CLEAN", "COMPLETED")
        and snap["service_evidence_state"] == "CLOSED_OBSERVATIONAL",
        "B2_UNCLEAN_RECOVERY_BLOCKED",
    )
    for key in (
        "observation_binding_id",
        "window_plan_sha256",
        "privacy_permission_sha256",
    ):
        b.require(snap[key] == start[key], "WINDOW_TRANSFER_FORBIDDEN")

    def source():
        return events(root, start, plan)

    index = reporting.Index(
        scratch,
        source,
        works,
        verify_receipt,
        max_bytes=(o.resources_view(profile) if getattr(o,"RA_ENABLED",False) else profile["resources"])["fixed_campaign_disk_bound_bytes"],
    )
    try:
        original_inventories = {
            area: inventory_heads(root, area, plan) for area in ("events", "attempts")
        }
        node = root
        previous = None
        seen = set()
        while node is not None:
            b.require(str(node) not in seen, "B2_RECOVERY_CYCLE")
            seen.add(str(node))
            b.require(
                len(seen) <= plan["budgets"]["administrative_operations"],
                "B2_RECOVERY_CYCLE",
            )
            current = o.parse(io.read(node / "snapshot.json"), o.SNAPSHOT)
            for name, obj in (("profile.json", profile), ("plan.json", plan)):
                b.require(
                    io.read(node / name) == b.canonical(obj), "B2_RECOVERY_BINDING"
                )
            b.require(
                o.manifest_digest(metadata.read_role(node, "work.json", plan))
                == plan["work_manifest_sha256"],
                "B2_WORK_MANIFEST",
            )
            b.require(
                io.read(node / "campaign_start.json") == b.canonical(start)
                and io.read(node / "_SEGMENT_SEALED", limit=0) == b"",
                "B2_RECOVERY_UNSEALED",
            )
            for name, field in (
                ("event_inventory.json", "event_inventory_sha256"),
                ("attempt_inventory.json", "attempt_inventory_sha256"),
                ("work_ledger.json", "work_ledger_sha256"),
                ("operations_report.json", "operations_report_sha256"),
            ):
                b.require(
                    (
                        b.sha(io.read(node / name)).hex()
                        if name == "operations_report.json"
                        else o.manifest_digest(metadata.read_role(node, name, plan))
                    )
                    == current[field],
                    "B2_RECOVERY_INVENTORY",
                )
            for area, field in (
                ("events", "event_inventory_sha256"),
                ("attempts", "attempt_inventory_sha256"),
            ):
                b.require(
                    original_inventories[area][str(node)] == current[field],
                    "B2_RECOVERY_INVENTORY",
                )
            report = o.parse(io.read(node / "operations_report.json"), o.REPORT)
            measured = (
                o.parse(io.read(node / "measurement_report.json"), o.MEASUREMENT)
                if getattr(o, "AP_ENABLED", False)
                else b.parse(
                    io.read(node / "measurement_report.json"),
                    "stage12_development_measurement_report_b2_v1",
                )
            )
            if getattr(o, "AP_ENABLED", False):
                from .s12_public_sampling import inspect

                summaries = inspect(
                    lambda: events(node, start, plan),
                    profile,
                    start,
                    maximum_segments=plan["sampling_budget"]["maximum_segments"],
                    contract=o,
                )
                close = next(
                    e
                    for e in events(node, start, plan)
                    if e["seq"] == summaries[-1]["close_event_seq"]
                )
                b.require(
                    current["sampling"] == summaries[-1]
                    and current["sampling_policy_sha256"] == o.POLICY_SHA
                    and current["sampling_close_event_sha256"] == o.digest(close)
                    and all(row["complete"] for row in summaries),
                    "B2_SAMPLING_INCOMPLETE",
                )
            b.require(
                report["measurement_report_sha256"] == b.digest(measured)
                and measured["resource_sampling_complete"]
                and measured["receipts_complete"]
                and report["segment_closure_sha256"]
                == current["segment_closure_sha256"],
                "B2_RECOVERY_REPORT",
            )
            release = io.metadata(io.read(node / "_WRITER_RELEASED.json"))
            b.require(
                release
                == {
                    "snapshot_sha256": b.digest(current),
                    "writer_release_evidence_sha256": current[
                        "writer_release_evidence_sha256"
                    ],
                },
                "B2_WRITER_UNCERTAIN",
            )
            from . import s12_b2_evidence as evidence
            from .s12_b2_pipeline import bootstrap_spent

            admission = b.parse(
                io.read(node / "segment_admission.json"),
                "stage12_segment_admission_b2_v1",
            )
            opened = [
                event
                for event in index.all()
                if event["kind"] == "SEGMENT_OPEN"
                and event["segment_id"] == current["segment_id"]
            ]
            b.require(
                len(opened) == 1
                and admission["segment_id"] == current["segment_id"]
                and admission["operations_campaign_sha256"] == b.digest(start)
                and admission["campaign_start_sha256"]
                == start["scientific_campaign_start_sha256"]
                and admission["epoch_id"] == opened[0]["epoch_id"]
                and b.digest(admission)
                == opened[0]["body"]["segment_admission_sha256"],
                "B2_SEGMENT_BINDING",
            )
            evidence.release_authority(
                authority.records,
                current["writer_release_evidence_sha256"],
                campaign_id=start["campaign_id"],
                segment_nonce=admission["segment_nonce"],
                now=current["sealed_utc"],
                authority=authority,
            )
            spent = bootstrap_spent(
                authority.records,
                current["bootstrap_acquisition_sha256"],
                plan,
                profile,
                start,
            )
            b.require(
                spent
                == {
                    "operations": current["controller"]["administrative_operations"],
                    "duration_ms": current["controller"]["administrative_duration_ms"],
                    "bytes": current["controller"]["administrative_bytes"],
                },
                "B2_ADMIN_ACCOUNTING",
            )
            b.require(
                io.read(node / "administrative_ledger.json")
                == authority.records.raw(current["bootstrap_acquisition_sha256"]),
                "B2_ADMIN_BINDING",
            )
            closure = authority.records.get(
                current["segment_closure_sha256"], "segment_closure"
            )
            b.require(
                closure["resource_report_sha256"] == b.digest(measured)
                and closure["attempt_inventory_sha256"]
                == current["attempt_inventory_sha256"]
                and closure["controller_reconciliation_sha256"]
                == current["work_ledger_sha256"]
                and closure["campaign_start_sha256"]
                == start["scientific_campaign_start_sha256"]
                and closure["window_plan_sha256"] == start["window_plan_sha256"]
                and closure["preflight_sha256"]
                == admission["preflight_observation_sha256"]
                and closure["segment_nonce"] == admission["segment_nonce"]
                and closure["disposition"] == "CLOSED_OBSERVATIONAL",
                "B2_RECOVERY_CLOSURE",
            )
            prefix_index = index.prefix(measured["input_last_event_seq"])
            recomputed = reporting.measurement(
                prefix_index,
                profile,
                plan,
                start,
                attempt_inventory=current["attempt_inventory_sha256"],
                administrative_spent=measured["administrative_spent"],
                disposition=current["disposition"],
                defer_source_validation=True,
                timing_evidence=measured.get("timing_evidence"),
            )
            b.require(recomputed == measured, "B2_RECOVERY_REPORT")
            if getattr(o, "AP_ENABLED", False):
                b.require(
                    current["timing_evidence"]
                    == measured["timing_evidence"]
                    == report["timing_evidence"],
                    "B2_TIMING_BINDING",
                )
                o.verify_timing(node, current["timing_evidence"])
            # The original epoch's BEGIN charges, including controls, must fit
            # that exact planned slot. No cumulative counter is reset.
            from . import s12_b2_planning as planning

            slot = planning.planned_slot(authority.records, plan, admission)
            charges = sum(
                1
                for event in index.all()
                if event["segment_id"] == current["segment_id"]
                and event["kind"] == "BEGIN_DURABLE"
            )
            b.require(charges <= slot["max_attempts"], "B2_SEGMENT_ATTEMPTS")
            authority.require(
                "prior_segment_closure", current["segment_closure_sha256"], current
            )
            if previous is not None:
                b.require(
                    previous["predecessor_closure_sha256"]
                    == current["segment_closure_sha256"]
                    and previous["segment_id"] == current["segment_id"] + 1,
                    "B2_PREDECESSOR_MISMATCH",
                )
            previous = current
            node = j.predecessor_root(node)
        b.require(
            previous["segment_id"] == 1
            and previous["predecessor_closure_sha256"] is None,
            "B2_PREDECESSOR_MISMATCH",
        )
        state = replay_engine.replay(index.all(), contract=o)
        b.require(
            state["closed"]
            and not state["unfinished"]
            and state["breaker_reason"] is None
            and state["last_event"]["seq"] == snap["last_event_seq"]
            and b.digest(state["last_event"]) == snap["last_event_sha256"],
            "B2_UNCLEAN_RECOVERY_BLOCKED",
        )
        for key in (
            "state_id",
            "block_id",
            "last_ticket",
            "consecutive_retryable",
            "recent",
            "overload_carry",
            "breaker_reason",
            "cooldown_delay_ms",
            "active_duration_ms",
        ):
            b.require(snap["controller"][key] == state[key], "B2_CONTROLLER_MISMATCH")
        b.require(
            o.manifest_digest(index.ledger()) == snap["work_ledger_sha256"],
            "B2_LEDGER_MISMATCH",
        )

        def remaining():
            return (r for r in index.ledger() if r["state"] in ("UNBEGUN", "RETRY_DUE"))

        b.require(
            o.manifest_digest(remaining())
            == snap["controller"]["remaining_work_ledger_sha256"],
            "B2_LEDGER_MISMATCH",
        )
        charged = {"DATA": 0, "SERVICE_CONTROL": 0}
        complete = True
        for row in index.ledger():
            b.require(
                row["state"] not in ("UNKNOWN_DELIVERY", "TERMINAL"),
                "B2_UNCLEAN_RECOVERY_BLOCKED",
            )
            work = json.loads(
                index.db.execute(
                    "select body from work where id=?", (row["work_id"],)
                ).fetchone()[0]
            )
            charged[work["kind"]] += len(row["charged_ordinals"])
            complete &= row["state"] == "DURABLE_SUCCESS"
        b.require(
            (charged["DATA"], charged["SERVICE_CONTROL"])
            == (
                snap["controller"]["charged_data_attempts"],
                snap["controller"]["charged_control_attempts"],
            ),
            "B2_ATTEMPT_ACCOUNTING",
        )
        b.require(snap["disposition"] != "COMPLETED" or complete, "B2_WORK_TOTALITY")
        # Fresh original membership/content again before accepting any prior
        # prefix view. No stage-local index survives to authorize another stage.
        b.require(
            all(
                inventory_heads(root, area, plan) == original_inventories[area]
                for area in ("events", "attempts")
            ),
            "B2_RECOVERY_INVENTORY",
        )
    except BaseException:
        try:
            index.close()
        except BaseException:
            pass  # A second source/close failure cannot replace the first.
        raise
    else:
        index.close()
    # Return factories which reread immutable ledgers; no population cache.
    return {
        "snapshot": snap,
        "state_id": state["state_id"],
        "block_charged": charged,
        "cooldown_delay_ms": state["cooldown_delay_ms"],
        "consecutive_retryable": state["consecutive_retryable"],
        "recent": state["recent"],
        "overload_carry": state["overload_carry"],
        "cooldown_trigger": state["cooldown_trigger"],
        "block_durations_ms": state["block_durations_ms"],
        "ledger": lambda: metadata.read_role(root, "work_ledger.json", plan),
    }


def clean_continuation(
    root,
    start,
    profile,
    plan,
    *,
    authority,
    new_segment_authority,
    works,
    verify_receipt,
    scratch,
):
    result = reopen(
        root,
        start,
        profile,
        plan,
        works=works,
        verify_receipt=verify_receipt,
        scratch=scratch,
        authority=authority,
        require_paused=True,
    )
    authority.require(
        "same_window_continuation",
        new_segment_authority,
        {"start": start, "snapshot": result["snapshot"]},
    )
    # The coordinator applies every carried delay only AFTER its new journal
    # acknowledges SEGMENT_OPEN. No entry-clock timestamp is returned here.
    return result


def reopen(root, start, profile, plan, **kwargs):
    contract = o.for_profile(profile)
    if not getattr(contract, "PAGED_HISTORY", False):
        return _reopen(root, start, profile, plan, **kwargs)
    # Independent opener scope, never a token inherited from report/persistence.
    contract.verify_authorities(profile, plan, start, kwargs["authority"])
    from . import s12_paged_history as history

    def roots():
        return _lineage(root, plan)

    with (
        history.selected(plan["history_limits"]),
        history.ChainFresh(root.parent, roots, limits=plan["history_limits"]),
    ):
        return _reopen(root, start, profile, plan, **kwargs)

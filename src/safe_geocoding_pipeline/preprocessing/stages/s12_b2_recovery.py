"""B2 clean same-window reconciliation; no public conversion or unclean repair."""

from __future__ import annotations
import json
from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_reporting as reporting
from . import s12_public_journal as j
from . import s12_public_recovery as replay_engine
from . import s12_storage as io


def events(root, start):
    return j.read_events(root, b.digest(start), contract=o)


def inventory(root, area):
    return j.evidence_inventory(root, area, contract=o)


def reopen(
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
    o.verify_authorities(profile, plan, start, authority)
    b.require(
        io.read(root / "campaign_start.json") == b.canonical(start), "B2_START_BINDING"
    )
    snap = b.parse(io.read(root / "snapshot.json"), o.SNAPSHOT)
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
        current = b.parse(io.read(node / "snapshot.json"), o.SNAPSHOT)
        for name, obj in (("profile.json", profile), ("plan.json", plan)):
            b.require(io.read(node / name) == b.canonical(obj), "B2_RECOVERY_BINDING")
        b.require(
            o.manifest_digest(j.read_array(node / "work.json"))
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
                b.sha(io.read(node / name)).hex() == current[field],
                "B2_RECOVERY_INVENTORY",
            )
        for area, field in (
            ("events", "event_inventory_sha256"),
            ("attempts", "attempt_inventory_sha256"),
        ):
            b.require(
                o.manifest_digest(inventory(node, area)) == current[field],
                "B2_RECOVERY_INVENTORY",
            )
        report = b.parse(io.read(node / "operations_report.json"), o.REPORT)
        measured = b.parse(
            io.read(node / "measurement_report.json"),
            "stage12_development_measurement_report_b2_v1",
        )
        b.require(
            report["measurement_report_sha256"] == b.digest(measured)
            and measured["resource_sampling_complete"]
            and measured["receipts_complete"]
            and report["segment_closure_sha256"] == current["segment_closure_sha256"],
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
            io.read(node / "segment_admission.json"), "stage12_segment_admission_b2_v1"
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
            and closure["preflight_sha256"] == admission["preflight_observation_sha256"]
            and closure["segment_nonce"] == admission["segment_nonce"]
            and closure["disposition"] == "CLOSED_OBSERVATIONAL",
            "B2_RECOVERY_CLOSURE",
        )
        prefix = lambda node=node, n=measured["input_last_event_seq"]: (
            e for e in events(node, start) if e["seq"] <= n
        )
        prefix_index = reporting.Index(
            scratch.parent / (scratch.name + "_prefix_" + str(current["segment_id"])),
            prefix,
            works,
            verify_receipt,
            max_bytes=profile["resources"]["fixed_campaign_disk_bound_bytes"],
        )
        try:
            recomputed = reporting.measurement(
                prefix_index,
                profile,
                plan,
                start,
                attempt_inventory=current["attempt_inventory_sha256"],
                administrative_spent=measured["administrative_spent"],
                disposition=current["disposition"],
            )
            b.require(recomputed == measured, "B2_RECOVERY_REPORT")
        finally:
            prefix_index.close()
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
        previous["segment_id"] == 1 and previous["predecessor_closure_sha256"] is None,
        "B2_PREDECESSOR_MISMATCH",
    )
    source = lambda: events(root, start)
    state = replay_engine.replay(source(), contract=o)
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
    index = reporting.Index(
        scratch,
        source,
        works,
        verify_receipt,
        max_bytes=profile["resources"]["fixed_campaign_disk_bound_bytes"],
    )
    try:
        b.require(
            o.manifest_digest(index.ledger()) == snap["work_ledger_sha256"],
            "B2_LEDGER_MISMATCH",
        )
        remaining = lambda: (
            r for r in index.ledger() if r["state"] in ("UNBEGUN", "RETRY_DUE")
        )
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
    finally:
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
        "ledger": lambda: j.read_array(root / "work_ledger.json"),
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

"""Public O-r2 reconciliation. Unclean histories never resume network work."""

from __future__ import annotations
import hashlib

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import Any
from itertools import islice, zip_longest

from . import s12_public_journal as journal
from . import s12_public_operations as o
from . import s12_retrieval_contract as c
from . import s12_storage as io


class FinalizationExpired(RuntimeError):
    """Cumulative limit, never a response-contract or unavailable-receipt error."""


class Deadline:
    def __init__(self, clock, end_ns):
        self.clock, self.end_ns = clock, end_ns

    def check(self):
        if self.clock.now_ns() >= self.end_ns:
            raise FinalizationExpired("S12_PUBLIC_FINALIZATION_DEADLINE")

    def remaining_seconds(self):
        return max(0, self.end_ns - self.clock.now_ns()) / 1e9


def replay(events: Iterable[dict[str, Any]], *, contract: Any = o) -> dict[str, Any]:
    """Reconstruct bounded controller state, not a trusted snapshot cache."""
    o = contract
    active: dict[tuple[int, int], dict[str, Any]] = {}
    awaiting: dict[tuple[int, int], int] = {}
    recent: deque[dict[str, Any]] = deque(maxlen=20)
    overloads: deque[tuple[int, tuple[int, int]]] = deque()
    consecutive = last_ticket = finalized = charged = cooldown = 0
    cooldown_until = 0
    active_duration_ms = 0
    segment_opened = 0
    block_durations: dict[int, int] = {}
    cooldown_trigger = None
    state_id = block_id = 0
    breaker = None
    closed = False
    last = None
    for event in events:
        o.validate(event, o.EVENT)
        kind, b, mono = event["kind"], event["body"], event["mono_ns"]
        key = (b.get("work_id"), b.get("attempt"))
        if kind == "SEGMENT_OPEN":
            o.require(not active and not awaiting)
            state_id, block_id, closed = b["state_id"], b["block_id"], False
            segment_opened = mono
            cooldown_until = mono + cooldown * 1_000_000
            overloads = deque((mono, k) for _, k in overloads)
        elif kind == "BEGIN_DURABLE":
            o.require(not closed and key not in active and len(active) < 4)
            active[key] = {"start": None, "commit": None, "ticket": None}
            charged += 1
        elif kind == "ATTEMPT_STARTED":
            o.require(key in active and active[key]["start"] is None)
            active[key]["start"] = b["started_mono_ns"]
        elif kind == "EMIT_COMMITTED":
            o.require(
                key in active
                and active[key]["start"] is not None
                and active[key]["commit"] is None
            )
            active[key]["commit"] = b["committed_mono_ns"]
        elif kind == "EMISSION":
            o.require(
                key in active
                and active[key]["commit"] is not None
                and b["entered_mono_ns"] >= active[key]["commit"]
            )
        elif kind == "NETWORK_DONE":
            o.require(
                key in active
                and active[key]["start"] is not None
                and active[key]["ticket"] is None
            )
            # Event persistence order can differ from registered completion order.
            o.require(
                b["ticket"] > finalized
                and all(x["ticket"] != b["ticket"] for x in active.values())
            )
            active[key]["ticket"] = b["ticket"]
            last_ticket = max(last_ticket, b["ticket"])
        elif kind == "ATTEMPT_FINALIZED":
            o.require(
                key in active
                and active[key]["ticket"] == b["ticket"] == finalized + 1
                and b["outcome"]["value"] != "UNKNOWN_DELIVERY"
            )
            retryable = b["outcome"]["value"] == "TECHNICAL_FAILURE_RETRYABLE"
            consecutive = consecutive + 1 if retryable else 0
            recent.append(
                {
                    "ticket": b["ticket"],
                    "retryable": retryable,
                    "elapsed_ms": b["elapsed_ms"],
                }
            )
            awaiting[key] = active.pop(key)["start"]
            finalized = b["ticket"]
        elif kind == "AUDIT_TIMING":
            o.require(key in awaiting)
            times = [
                b[k]
                for k in (
                    "writer_enqueued_ns",
                    "writer_started_ns",
                    "receipt_reopened_ns",
                    "finalized_event_ack_ns",
                    "reservation_released_ns",
                )
            ]
            o.require(times == sorted(times) and times[0] >= awaiting.pop(key))
        elif kind == "EARLY_SIGNAL" and b["status"] in (429, 503):
            o.require(all(k != key for _, k in overloads))
            overloads.append((b["observed_mono_ns"], key))
        if kind == "EARLY_SIGNAL" and b["signal"] in ("OVERLOAD", "RETRYABLE_5XX"):
            cooldown = max(
                cooldown if mono < cooldown_until else 0,
                30_000,
                (b["retry_after_seconds"] or 0) * 1000,
            )
            cooldown_until = max(
                cooldown_until,
                b["observed_mono_ns"]
                + max(30_000, (b["retry_after_seconds"] or 0) * 1000) * 1_000_000,
            )
            cooldown_trigger = {
                "trigger_work_id": b["work_id"],
                "trigger_attempt": b["attempt"],
            }
        elif kind == "COOLDOWN":
            o.require(
                cooldown_trigger is not None and b["until_mono_ns"] == cooldown_until
            )
        elif kind == "DOWNSHIFT":
            o.require(b["from_state"] == state_id and b["to_state"] < state_id)
            state_id = b["to_state"]
        elif kind == "STOP":
            breaker = b["primary_reason"] or "TERMINAL_FAILURE"
        elif kind == "SEGMENT_CLOSE":
            o.require(b["last_ticket"] == last_ticket)
            if b["disposition"] in ("PAUSED_CLEAN", "COMPLETED"):
                o.require(
                    not active
                    and not awaiting
                    and finalized == last_ticket
                    and breaker is None
                )
            closed = True
            elapsed = (mono - segment_opened + 999_999) // 1_000_000
            active_duration_ms += elapsed
            block_durations[block_id] = block_durations.get(block_id, 0) + elapsed
            if mono >= cooldown_until:
                cooldown = 0
        while overloads and overloads[0][0] < mono - 60_000_000_000:
            overloads.popleft()
        last = event
    o.require(last is not None)
    return {
        "state_id": state_id,
        "block_id": block_id,
        "begins_charged": charged,
        "last_ticket": last_ticket,
        "consecutive_retryable": consecutive,
        "recent": list(recent),
        "overload_carry": [{"work_id": k[0], "attempt": k[1]} for _, k in overloads],
        "breaker_reason": breaker,
        "cooldown_delay_ms": cooldown,
        "cooldown_trigger": cooldown_trigger,
        "active_duration_ms": active_duration_ms,
        "block_durations_ms": block_durations,
        "closed": closed,
        "unfinished": len(active) + len(awaiting),
        "last_event": last,
    }


def work_ledger(
    work_factory: Callable[[], Iterable[dict[str, Any]]],
    event_factory: Callable[[], Iterable[dict[str, Any]]],
    verify_receipt: Callable[[dict[str, Any], dict[str, Any]], None],
    *,
    contract: Any = o,
    batch_size: int = 1,
) -> Iterator[dict[str, Any]]:
    """Bounded attempt joins; legacy/B2 callers retain the one-work default."""
    o = contract
    o.require(type(batch_size) is int and 1 <= batch_size <= 128)

    def evidence():
        source = iter(work_factory())
        fingerprint = None
        while batch := list(islice(source, batch_size)):
            states = {w["work_id"]: (w, [], {}) for w in batch}
            o.require(len(states) == len(batch))
            transcript = hashlib.sha256()
            for event in event_factory():
                if batch_size > 1:
                    transcript.update(c.canonical(event))
                b = event["body"]
                if b.get("work_id") not in states:
                    continue
                work, begins, final = states[b["work_id"]]
                if event["kind"] == "BEGIN_DURABLE":
                    begins.append(b["attempt"])
                    o.require(
                        begins == list(range(1, len(begins) + 1)) and len(begins) <= 5
                    )
                elif event["kind"] == "ATTEMPT_FINALIZED":
                    o.require(
                        b["attempt"] in begins
                        and b["attempt"] not in final
                        and b["outcome"]["kind"] == work["kind"]
                    )
                    verify_receipt(work, b)
                    final[b["attempt"]] = b
            if batch_size > 1:
                digest = transcript.digest()
                if fingerprint is None:
                    fingerprint = digest
                else:
                    o.require(digest == fingerprint)
            for work in batch:
                yield states[work["work_id"]]

    for work, begins, final in evidence():
        selected = None
        last_outcome = None
        delay = None
        if not begins:
            state = "UNBEGUN"
        elif begins[-1] not in final or len(final) != len(begins):
            state, last_outcome = (
                "UNKNOWN_DELIVERY",
                {"kind": work["kind"], "value": "UNKNOWN_DELIVERY"},
            )
        else:
            last = final[begins[-1]]
            last_outcome = last["outcome"]
            successes = [
                n
                for n, b in final.items()
                if b["outcome"]["value"] in (*c.SUCCESS, "CONTROL_SUCCESS")
            ]
            o.require(not successes or successes == [begins[-1]])
            if successes:
                state, selected = "DURABLE_SUCCESS", last["receipt_inventory_sha256"]
            elif (
                last_outcome["value"] == "TECHNICAL_FAILURE_RETRYABLE"
                and begins[-1] < 5
            ):
                state, delay = "RETRY_DUE", last["retry_delay_ms"]
                o.uint(delay, True)
            else:
                state = "TERMINAL"
        row = {
            "work_id": work["work_id"],
            "charged_ordinals": begins,
            "selected_receipt_sha256": selected,
            "last_outcome": last_outcome,
            "retry_delay_ms": delay,
            "state": state,
        }
        o.validate_type(row, "WorkLedgerRow")
        yield row


def unclean_reconciliation(
    root: Path,
    start_hash: str,
    *,
    verify_known: Callable[[Path, dict[str, Any]], bool] | None = None,
    contract: Any = o,
) -> dict[str, Any]:
    """Known-file inventory and lower bounds only; no fabricated snapshot."""
    o = contract
    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_history import Known

        known = Known(root, verify_known)
        return {
            "disposition": "RECOVERY_BLOCKED",
            "report_complete": False,
            "begins_charged": {"value": None, "confirmed_min": known.confirmed},
            "known_files": known,
            "known_sealed_receipts_verified": known.verified
            if verify_known is not None
            else None,
            "snapshot": None,
            "reconciliation_reasons": ["AUDIT_FAILED", "STOPPED", "UNKNOWN_DELIVERY"],
        }
    files = []
    confirmed = 0
    verified = 0
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        try:
            raw = (
                io.read(path, limit=4096)
                if (
                    getattr(o, "AP_ENABLED", False)
                    or o.PROFILE == "stage12_transport_operations_v3"
                )
                and path.parent.name == "events"
                else io.read(path)
            )
            files.append(
                {"path": str(path.relative_to(root)), "sha256": c.sha(raw).hex()}
            )
            if (
                path.name == "begin.json"
                or path.name.endswith("_begin.json")
                and not path.name.endswith("_validation_begin.json")
            ):
                obj = io.metadata(raw)
                o.require(type(obj.get("attempt")) is int and 1 <= obj["attempt"] <= 5)
                confirmed += 1
                if verify_known is not None:
                    verified += bool(verify_known(path.parent, obj))
        except (c.Stage12Error, OSError):
            continue
    return {
        "disposition": "RECOVERY_BLOCKED",
        "report_complete": False,
        "begins_charged": {"value": None, "confirmed_min": confirmed},
        "known_files": files,
        "known_sealed_receipts_verified": verified
        if verify_known is not None
        else None,
        "snapshot": None,
        "reconciliation_reasons": ["AUDIT_FAILED", "STOPPED", "UNKNOWN_DELIVERY"],
    }


def snapshot_evidence(
    root: Path,
    snapshot: dict[str, Any],
    state: dict[str, Any],
    block_hash: str,
    *,
    check: Callable[[], None],
) -> tuple[str, str | None]:
    """Fresh exact original-content checks, shared by publication and reopening.

    Fixed-size bindings only. Inventory/ledger rows stream; no campaign cache.
    The supplied state/report head must come from a freshly validated chain.
    """
    from . import s12_public_operations as o

    if snapshot.get("schema_version") == "stage12_public_recovery_snapshot_v2":
        from . import s12_public_sampling_contract as o
    elif snapshot.get("schema_version") == "stage12_public_recovery_snapshot_v3":
        from . import s12_wf_ap2_contract as o
    elif snapshot.get("schema_version") == "stage12_public_recovery_snapshot_ra_g1_v1":
        from . import s12_ra_g1_contract as o
    elif snapshot.get("schema_version") == "stage12_representative_snapshot_coverage_ra_g1_v1":
        from . import s12_ra_g1_rep_coverage_contract as o
    elif snapshot.get("schema_version") == "stage12_representative_snapshot_fair_service_ra_g1_v1":
        from . import s12_ra_g1_rep_fair_contract as o
    elif snapshot.get("schema_version") == "stage12_representative_snapshot_ack_queue_ra_g1_v1":
        from . import s12_ra_g1_rep_ack_contract as o
    check()
    o.validate(snapshot, o.SNAPSHOT)
    o.require(
        c.sha(io.read(root / "campaign_start.json")).hex()
        == snapshot["campaign_start_sha256"]
    )
    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_sampling import inspect

        profile = o.parse(io.read(root / "operations_profile.json"), o.PROFILE)
        plan = o.parse(io.read(root / "workload.json"), o.PLAN)
        start = o.parse(io.read(root / "campaign_start.json"), o.START)
        summaries = inspect(
            lambda: journal.read_events(root, o.digest(start), contract=o),
            profile,
            start,
            maximum_segments=plan["sampling_budget"]["maximum_segments"],
            contract=o,
        )
        close = next(
            e
            for e in journal.read_events(root, o.digest(start), contract=o)
            if e["seq"] == summaries[-1]["close_event_seq"]
        )
        o.require(
            snapshot["sampling"] == summaries[-1]
            and snapshot["sampling_policy_sha256"] == o.POLICY_SHA
            and snapshot["sampling_close_event_sha256"] == o.digest(close)
        )
        if snapshot["disposition"] in ("COMPLETED", "PAUSED_CLEAN"):
            o.require(summaries[-1]["workload_complete"] if getattr(o, "AP_COVERAGE_ONLY", False) else summaries[-1]["complete"])
    last = state["last_event"]
    o.require(
        state["closed"]
        and last["kind"] == "SEGMENT_CLOSE"
        and last["body"]["disposition"] == snapshot["disposition"]
        and last["segment_id"] == snapshot["segment_id"]
        and last["seq"] == snapshot["last_event_seq"]
        and o.digest(last) == snapshot["last_event_sha256"]
        and last["body"]["closure_evidence_sha256"]
        == snapshot["closure_evidence_sha256"]
    )
    ctl = snapshot["controller"]
    for name in (
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
        o.require(ctl[name] == state[name])
    o.require(
        ctl["event_count"] == last["seq"]
        and ctl["charged_data_attempts"] + ctl["charged_control_attempts"]
        == state["begins_charged"]
        and (not ctl["resume_eligible"] or snapshot["disposition"] == "PAUSED_CLEAN")
    )
    if snapshot["disposition"] in ("COMPLETED", "PAUSED_CLEAN"):
        o.require(not state["unfinished"] and state["breaker_reason"] is None)
    for name, expected in (
        ("event_inventory.json", snapshot["event_inventory_sha256"]),
        ("attempt_inventory.json", snapshot["attempt_inventory_sha256"]),
        ("work_ledger.json", snapshot["work_ledger_sha256"]),
        ("remaining_work_ledger.json", ctl["remaining_work_ledger_sha256"]),
    ):
        o.require(
            o.manifest_digest(journal.read_array(root / name, check=check)) == expected
        )
    for area in ("events", "attempts"):
        o.require(
            o.manifest_digest(journal.evidence_inventory(root, area, contract=o))
            == snapshot[area[:-1] + "_inventory_sha256"]
        )
    report = io.metadata(io.read(root / "block_report.json"))
    o.validate_type(report, "BlockReport")
    o.require(o.digest(report) == block_hash and report["block_id"] == ctl["block_id"])
    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_history import hash_file
    else:

        def hash_file(path):
            return c.sha(io.read(path)).hex()

    comparison = hash_file(root / "repeat_comparison.json")
    o.require(snapshot["closure_evidence_sha256"] in (None, comparison))
    projection = root / "measurement_event_prefix.json"
    projection_hash = hash_file(projection) if projection.exists() else None
    check()
    return comparison, projection_hash


def write_snapshot(
    writer: journal.Writer,
    snapshot: dict[str, Any],
    *,
    verify: Callable[[], tuple[dict[str, Any], str]],
    log: journal.Journal,
    state_binding: Callable[[], tuple],
    read_stage=None,
    deadline=None,
) -> str:
    """Prepare/validate/persist/revalidate/commit under one cumulative budget.

    Expensive original reads run on the coordinator; each persistence action
    still has the unchanged writer guard. No prepared token grants authority.
    A timeout may leave an unsealed partial file, never a follow-on seal/release.
    """
    o = log.contract
    failures = writer.failures

    def mark(stage, *, completed=False):
        if failures is not None:
            try:
                failures.closure_boundary(stage, completed=completed, writer=writer, deadline=deadline, guard="CAPTURE_CUMULATIVE")
            except BaseException:
                # Supplementary retention must not replace publication failure.
                try:
                    failures.closure_fault()
                except BaseException:
                    pass

    mark("SNAPSHOT_PRECHECK")
    fence = writer.closure_fence
    o.require(fence is not None and log.writer is writer)
    fence.check()
    o.validate(snapshot, o.SNAPSHOT)
    raw = c.canonical(snapshot)
    frozen = (
        log.start_hash,
        log.segment,
        log.epoch,
        log.seq,
        log.last_hash,
        log.segment_closed,
        state_binding(),
    )
    o.require(
        frozen[5]
        and frozen[:2] == (snapshot["campaign_start_sha256"], snapshot["segment_id"])
        and frozen[3:5] == (snapshot["last_event_seq"], snapshot["last_event_sha256"])
    )

    def bound():
        fence.check()
        o.require(c.canonical(snapshot) == raw)
        o.require(
            frozen
            == (
                log.start_hash,
                log.segment,
                log.epoch,
                log.seq,
                log.last_hash,
                log.segment_closed,
                state_binding(),
            )
        )

    def validate(extra_bytes, *, revalidate=False):
        verify_stage = "REVALIDATE_ORIGINAL_VERIFY" if revalidate else "PREPARE_ORIGINAL_VERIFY"
        evidence_stage = "REVALIDATE_EVIDENCE" if revalidate else "PREPARE_EVIDENCE"
        storage_stage = "REVALIDATE_STORAGE" if revalidate else "PREPARE_STORAGE"
        mark(verify_stage)
        bound()
        state, report_hash = verify()
        mark(verify_stage, completed=True)
        o.require(state["last_event"]["epoch_id"] == frozen[2])
        mark(evidence_stage)
        identities = snapshot_evidence(
            writer.root,
            snapshot,
            state,
            report_hash,
            check=writer.check_deadline,
        )
        mark(evidence_stage, completed=True)
        mark(storage_stage)
        o.require(
            log.prior_bytes + log.reconcile_storage()
            == snapshot["controller"]["stored_bytes"] + extra_bytes
        )
        bound()
        mark(storage_stage, completed=True)
        return identities, c.canonical(state["last_event"])

    try:
        for name in (
            "snapshot.json",
            "_SEGMENT_SEALED",
            "campaign_report.json",
            "_WRITER_RELEASED.json",
        ):
            o.require(not (writer.root / name).exists())
        with io.cooperative_io(writer.check_deadline):
            prepared = validate(0)
            if read_stage is not None:
                mark("FRESH_FINISH")
                read_stage.finish()
                bound()
                mark("FRESH_FINISH", completed=True)

            def persist():
                bound()
                writer.assert_owner()
                io.write(writer.root / "snapshot.json", raw)
                o.require(io.read(writer.root / "snapshot.json") == raw)
                bound()

            mark("SNAPSHOT_PERSIST")
            writer.call(persist)
            mark("SNAPSHOT_PERSIST", completed=True)
            if read_stage is None:
                o.require(validate(len(raw), revalidate=True) == prepared)
            else:
                from .s12_public_fresh_reads import FreshReads

                if (
                    getattr(o, "AP_ENABLED", False)
                    or o.PROFILE == "stage12_transport_operations_v3"
                ):
                    from .s12_public_history import Fresh as FreshReads

                    if getattr(o, "PAGED_HISTORY", False):
                        from functools import partial
                        from . import s12_paged_history as history

                        FreshReads = partial(history.Fresh, limits=history.current())

                mark("REVALIDATE_FRESH")
                with FreshReads(
                    writer.root, check=fence.check_live, boundary=fence.check,
                    **({"descriptor_relative": True}
                       if o.PROFILE in (
                           "stage12_transport_operations_ra_g1_v1",
                           "stage12_transport_operations_rep_ack_queue_ra_g1_v1",
                           "stage12_transport_operations_rep_fair_service_ra_g1_v1",
                           "stage12_transport_operations_rep_coverage_ra_g1_v1",
                       ) else {}),
                ):
                    o.require(validate(len(raw), revalidate=True) == prepared)
                bound()
                mark("REVALIDATE_FRESH", completed=True)

            def commit():
                bound()
                writer.assert_owner()
                o.require(io.read(writer.root / "snapshot.json") == raw)
                o.require(
                    io.read(
                        writer.root
                        / "events"
                        / f"{snapshot['last_event_seq']:020d}.json"
                    )
                    == prepared[1]
                )
                bound()
                io.write(writer.root / "_SEGMENT_SEALED", b"")
                o.require(io.read(writer.root / "_SEGMENT_SEALED", limit=0) == b"")
                bound()

            mark("SNAPSHOT_SEAL")
            writer.call(commit)
            mark("SNAPSHOT_SEAL", completed=True)
            return c.sha(raw).hex()
    except BaseException as error:
        # Capture the original boundary/state BEFORE defensive writer poisoning.
        if failures is not None and getattr(failures, "closure_enabled", False):
            try:
                failures.record("CLOSURE", error, writer=writer, deadline=deadline)
            except BaseException:
                try:
                    failures.closure_fault()
                except BaseException:
                    pass
        # No recovery/cleanup path may finish an uncertain publication.
        writer.failed.set()
        writer.stop()
        raise


def clean_continuation(
    root: Path,
    expected_start: dict[str, Any],
    profile: dict[str, Any],
    plan: dict[str, Any],
    *,
    authority: o.Authority,
    new_segment_authority: str,
    now_ns: int,
    work_factory: Callable[[], Iterable[dict[str, Any]]],
    verify_receipt: Callable[[dict[str, Any], dict[str, Any]], None],
) -> dict[str, Any]:
    """Return checked rebase instructions, never dispatch or modify old files."""
    from . import s12_public_operations as o

    if profile.get("schema_version") == "stage12_transport_operations_v3":
        from . import s12_public_sampling_contract as o
    elif profile.get("schema_version") == "stage12_transport_operations_v4":
        from . import s12_wf_ap2_contract as o
    elif profile.get("schema_version") == "stage12_transport_operations_ra_g1_v1":
        from . import s12_ra_g1_contract as o
    elif profile.get("schema_version") == "stage12_transport_operations_rep_coverage_ra_g1_v1":
        from . import s12_ra_g1_rep_coverage_contract as o
    elif profile.get("schema_version") == "stage12_transport_operations_rep_fair_service_ra_g1_v1":
        from . import s12_ra_g1_rep_fair_contract as o
    elif profile.get("schema_version") == "stage12_transport_operations_rep_ack_queue_ra_g1_v1":
        from . import s12_ra_g1_rep_ack_contract as o
    o.verify_authorities(profile, plan, expected_start, authority)
    o.require(io.read(root / "campaign_start.json") == c.canonical(expected_start))
    o.require(io.read(root / "_SEGMENT_SEALED", limit=0) == b"")
    snapshot = o.parse(io.read(root / "snapshot.json"), o.SNAPSHOT)
    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        o.require(snapshot["segment_id"] < plan["sampling_budget"]["maximum_segments"])
    o.require(
        snapshot["campaign_start_sha256"] == o.digest(expected_start)
        and snapshot["disposition"] == "PAUSED_CLEAN"
        and snapshot["controller"]["resume_eligible"]
    )
    # Inventory pins are redundant checks against actual immutable source files.
    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_history import hash_file
    else:

        def hash_file(path):
            return c.sha(io.read(path)).hex()

    node, visited = root, set()
    while node is not None:
        o.require(str(node) not in visited)
        visited.add(str(node))
        current = o.parse(io.read(node / "snapshot.json"), o.SNAPSHOT)
        for name, field in (
            ("event_inventory.json", "event_inventory_sha256"),
            ("attempt_inventory.json", "attempt_inventory_sha256"),
            ("work_ledger.json", "work_ledger_sha256"),
        ):
            o.require(hash_file(node / name) == current[field])
        o.require(
            hash_file(node / "remaining_work_ledger.json")
            == current["controller"]["remaining_work_ledger_sha256"]
        )
        o.require(
            o.manifest_digest(journal.evidence_inventory(node, "events", contract=o))
            == current["event_inventory_sha256"]
        )
        o.require(
            o.manifest_digest(journal.evidence_inventory(node, "attempts", contract=o))
            == current["attempt_inventory_sha256"]
        )
        block_report = io.metadata(io.read(node / "block_report.json"))
        o.validate_type(block_report, "BlockReport")
        closed_hash = None
        for event in journal.read_events(node, o.digest(expected_start), contract=o):
            if (
                event["kind"] == "BLOCK_CLOSED"
                and event["body"]["block_id"] == current["controller"]["block_id"]
            ):
                closed_hash = event["body"]["report_sha256"]
        o.require(closed_hash == o.digest(block_report))
        release = io.metadata(io.read(node / "_WRITER_RELEASED.json"))
        o.require(
            release
            == {
                "writer_release_evidence_sha256": current[
                    "writer_release_evidence_sha256"
                ],
                "snapshot_sha256": o.digest(current),
            }
        )
        node = journal.predecessor_root(node)

    def event_factory():
        return journal.read_events(root, o.digest(expected_start), contract=o)

    if (
        getattr(o, "AP_ENABLED", False)
        or o.PROFILE == "stage12_transport_operations_v3"
    ):
        from .s12_public_sampling import inspect

        summaries = inspect(
            event_factory,
            profile,
            expected_start,
            maximum_segments=plan["sampling_budget"]["maximum_segments"],
            contract=o,
        )
        o.require(all(x["workload_complete"] if getattr(o, "AP_COVERAGE_ONLY", False) else x["complete"] for x in summaries))
    state = replay(event_factory(), contract=o)
    o.require(
        state["closed"] and not state["unfinished"] and state["breaker_reason"] is None
    )
    last = state["last_event"]
    o.require(
        last["kind"] == "SEGMENT_CLOSE"
        and last["body"]["disposition"] == "PAUSED_CLEAN"
        and last["seq"] == snapshot["last_event_seq"]
        and o.digest(last) == snapshot["last_event_sha256"]
    )
    for name in (
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
        o.require(snapshot["controller"][name] == state[name])

    def ledger():
        for row, stored in zip_longest(
            work_ledger(work_factory, event_factory, verify_receipt, contract=o),
            journal.read_array(root / "work_ledger.json"),
        ):
            o.require(row is not None and stored is not None)
            o.validate_type(stored, "WorkLedgerRow")
            if stored["state"] == "UNUSED_RESERVED_CONTROL":
                o.require(
                    row["state"] == "UNBEGUN"
                    and any(
                        row["work_id"] in b["reserved_control_ids"]
                        for b in plan["blocks"]
                    )
                )
                row["state"] = "UNUSED_RESERVED_CONTROL"
            o.require(row == stored)
            yield row

    o.require(o.manifest_digest(ledger()) == snapshot["work_ledger_sha256"])
    remaining = (
        row
        for row in ledger()
        if row["state"] in ("UNBEGUN", "RETRY_DUE", "UNUSED_RESERVED_CONTROL")
    )
    o.require(
        o.manifest_digest(remaining)
        == snapshot["controller"]["remaining_work_ledger_sha256"]
    )
    total_bytes = journal.tree_bytes(
        root,
        frozenset(
            {
                "snapshot.json",
                "_SEGMENT_SEALED",
                "campaign_report.json",
                "_WRITER_RELEASED.json",
            }
        ),
    )
    node = journal.predecessor_root(root)
    while node is not None:
        total_bytes = o.checked(total_bytes + journal.tree_bytes(node))
        node = journal.predecessor_root(node)
    o.require(total_bytes == snapshot["controller"]["stored_bytes"])
    for row in ledger():
        o.require(row["state"] not in ("UNKNOWN_DELIVERY", "TERMINAL"))
    charged = {"DATA": 0, "SERVICE_CONTROL": 0}
    block_charged = charged.copy()
    for row in ledger():
        work = next(w for w in work_factory() if w["work_id"] == row["work_id"])
        charged[work["kind"]] += len(row["charged_ordinals"])
        if work["block_id"] == state["block_id"]:
            block_charged[work["kind"]] += len(row["charged_ordinals"])
    o.require(
        (charged["DATA"], charged["SERVICE_CONTROL"])
        == (
            snapshot["controller"]["charged_data_attempts"],
            snapshot["controller"]["charged_control_attempts"],
        )
    )
    o.require(
        snapshot["controller"]["event_count"] == last["seq"]
        and snapshot["controller"]["administrative_operations"] == 0
    )
    authority.require(
        "predecessor_termination",
        snapshot["writer_release_evidence_sha256"],
        {"root": str(root), "snapshot": snapshot},
    )
    authority.require(
        "clean_continuation",
        new_segment_authority,
        {
            "start": expected_start,
            "snapshot": snapshot,
            "profile": profile,
            "plan": plan,
        },
    )
    authority.require(
        "fresh_runtime_and_monitoring",
        new_segment_authority,
        {"profile": profile, "plan": plan},
    )
    # Return durations/history only. The caller's clock was read before the
    # predecessor and runtime gates; it cannot be the new segment's epoch.
    return {
        "state_id": state["state_id"],
        "block_id": state["block_id"],
        "cooldown_delay_ms": state["cooldown_delay_ms"],
        "recent": state["recent"],
        "consecutive_retryable": state["consecutive_retryable"],
        "overload_carry": state["overload_carry"],
        "ledger": ledger,
        "block_charged": block_charged,
        "block_durations_ms": state["block_durations_ms"],
        "cooldown_trigger": state["cooldown_trigger"],
        "snapshot": snapshot,
    }


def required_work_complete(plan, work_factory, ledger_factory, *, through_block=None):
    """Totality from the reconciled ledger, including required control work.

    Only never-begun reserved controls may be unused. A reserved control with a
    retry due is real outstanding work. Keep just one row of each stream resident.
    """
    complete = True
    for work, row in zip_longest(work_factory(), ledger_factory()):
        o.require(work is not None and row is not None)
        o.require(work["work_id"] == row["work_id"])
        if through_block is not None and work["block_id"] > through_block:
            continue
        reserved = plan["blocks"][work["block_id"] - 1]["reserved_control_ids"]
        unused = (
            work["work_id"] in reserved
            and not row["charged_ordinals"]
            and row["state"] in ("UNBEGUN", "UNUSED_RESERVED_CONTROL")
        )
        complete = complete and (row["state"] == "DURABLE_SUCCESS" or unused)
    return complete

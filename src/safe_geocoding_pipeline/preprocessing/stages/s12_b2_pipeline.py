"""Explicit observational campaign orchestration using reviewed O-r2 mechanics."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from dataclasses import dataclass
from typing import Callable
import json

from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_audit as audit
from . import s12_b2_reporting as reporting
from . import s12_b2_inventory as metadata
from . import s12_b2_recovery as recovery
from . import s12_b2_evidence as evidence
from . import s12_response as response
from . import s12_b2_catalog as catalog_module
from . import s12_public_scheduler as scheduler
from . import s12_public_journal as journal
from . import s12_public_recovery as replay_engine
from . import s12_public_operational_audit as transport_audit
from . import s12_retrieval_contract as c
from . import s12_storage as io


@dataclass(frozen=True)
class ResponseRules:
    layers: frozenset[str]
    sources: frozenset[str]
    expected_echo: Callable[[dict], dict]
    evidence_sha256: str

    def kwargs(self):
        return {
            "layers": self.layers,
            "sources": self.sources,
            "expected_echo": self.expected_echo,
        }


def acquisition_bounds(records, profile, phase):
    admin = profile["administrative"]
    contract = records.get(
        admin["acquisition_contract_sha256"], "bounded_acquisition_contract"
    )
    for name in ("preflight", "postflight"):
        for key, value in contract[name].items():
            b.require(value <= admin[key], "B2_ADMIN_SUBBOUND")
    return {
        **contract[phase],
        "acquisition_contract_sha256": admin["acquisition_contract_sha256"],
    }


def reserve_administration(records, profile, plan, spent, *, preflight):
    phases = ("preflight", "postflight") if preflight else ("postflight",)
    bounds = [acquisition_bounds(records, profile, x) for x in phases]
    b.require(
        spent["operations"] + len(phases)
        <= plan["budgets"]["administrative_operations"]
        and b.uint(spent["duration_ms"] + sum(x["max_duration_ms"] for x in bounds))
        <= plan["budgets"]["administrative_duration_ms"]
        and b.uint(spent["bytes"] + sum(x["max_total_bytes"] for x in bounds))
        <= profile["administrative"]["max_total_bytes"],
        "B2_ADMIN_CLOSURE_RESERVE",
    )
    return bounds[0]


def bootstrap_spent(records, bootstrap_hash, plan, profile, start):
    """Cumulative exactly-once administrative accounting from immutable begins."""
    chain = []
    seen = set()
    h = bootstrap_hash
    while h is not None:
        b.require(h not in seen, "B2_ADMIN_CYCLE")
        seen.add(h)
        x = records.get(h, "bootstrap_administration")
        b.require(
            bool(x["attempts"])
            and x["campaign_id"] == start["campaign_id"]
            and x["plan_sha256"] == b.digest(plan)
            and x["status"] == "SEALED",
            "B2_ADMIN_INCOMPLETE",
        )
        chain.append(x)
        h = x["predecessor_bootstrap_sha256"]
        b.require(
            len(chain) <= plan["budgets"]["administrative_operations"],
            "B2_ADMIN_BUDGET",
        )
    count = duration = size = 0
    previous = None
    previous_segment = None
    segment_entries = 0
    used_segments = set()
    for ledger in reversed(chain):
        for entry in ledger["attempts"]:
            if ledger["segment_nonce"] != previous_segment:
                b.require(
                    previous_segment is None or segment_entries == 2,
                    "B2_ADMIN_PHASE_ORDER",
                )
                b.require(
                    ledger["segment_nonce"] not in used_segments, "B2_ADMIN_PHASE_ORDER"
                )
                used_segments.add(ledger["segment_nonce"])
                previous_segment = ledger["segment_nonce"]
                segment_entries = 0
            segment_entries += 1
            b.require(segment_entries <= 2, "B2_ADMIN_PHASE_ORDER")
            expected_bounds = acquisition_bounds(
                records, profile, "preflight" if segment_entries == 1 else "postflight"
            )
            count += 1
            b.require(
                entry["cumulative_ordinal"] == count
                and entry["finish_sha256"] is not None,
                "B2_ADMIN_INCOMPLETE",
            )
            begin = records.get(entry["begin_sha256"], "evidence_acquisition_begin")
            finish = records.get(entry["finish_sha256"], "evidence_acquisition")
            b.require(
                finish["authority_sha256"] == begin["authority_sha256"]
                and finish["acquisition_contract_sha256"]
                == begin["acquisition_contract_sha256"]
                and len(finish["records"]) <= begin["bounds"]["max_records"]
                and all(
                    len(records.raw(h)) <= begin["bounds"]["max_record_bytes"]
                    for h in finish["records"]
                ),
                "B2_ADMIN_BINDING",
            )
            b.require(
                begin["cumulative_ordinal"] == count
                and begin["campaign_id"] == start["campaign_id"]
                and begin["segment_nonce"] == ledger["segment_nonce"]
                and begin["predecessor_begin_sha256"] == previous
                and begin["bounds"] == expected_bounds,
                "B2_ADMIN_BINDING",
            )
            b.require(
                finish["begin_sha256"] == entry["begin_sha256"]
                and finish["attempt_id"] == count
                and finish["epoch_id"] == begin["epoch_id"]
                and finish["finished_mono_ns"] >= begin["started_mono_ns"]
                and finish["elapsed_ms"]
                == (finish["finished_mono_ns"] - begin["started_mono_ns"] + 999999)
                // 1000000
                and finish["outcome"] == "ACQUIRED"
                and 0 < len(finish["records"]) <= expected_bounds["max_records"]
                and finish["elapsed_ms"] <= expected_bounds["max_duration_ms"]
                and finish["total_bytes"] <= expected_bounds["max_total_bytes"],
                "B2_ADMIN_INCOMPLETE",
            )
            b.require(
                sum(len(records.raw(r)) for r in finish["records"])
                == finish["total_bytes"],
                "B2_ADMIN_BINDING",
            )
            duration += finish["elapsed_ms"]
            size += finish["total_bytes"]
            previous = entry["begin_sha256"]
        b.require(
            ledger["spent"]
            == {"operations": count, "duration_ms": duration, "bytes": size},
            "B2_ADMIN_BINDING",
        )
    b.require(
        count <= plan["budgets"]["administrative_operations"]
        and duration <= plan["budgets"]["administrative_duration_ms"]
        and size <= profile["administrative"]["max_total_bytes"],
        "B2_ADMIN_BUDGET",
    )
    return {"operations": count, "duration_ms": duration, "bytes": size}


def run_segment(
    output: Path,
    profile,
    plan,
    start,
    scientific_start,
    admission,
    *,
    catalog,
    work_factory,
    gate,
    clock,
    dispatch,
    runtime_inventory,
    key: bytes,
    rules: ResponseRules,
    control_adapters: dict,
    free_bytes: Callable,
    writer_release_evidence: str,
    close_segment: Callable,
    predecessor: Path | None = None,
    pause_requested: Callable | None = None,
    notice: Callable | None = None,
    phase_check: Callable[[], None] | None = None,
    phase_remaining_seconds: Callable[[], float] | None = None,
):
    """No defaults for authority, live resource values, response rules or transport.

    close_segment imports actually reviewed pre/post/account/closure records;
    it must return a retained closure digest, never a bare success boolean.
    Synthetic callers supply unmistakably test-only records and adapters.
    """
    phase_entered_ns = clock.now_ns()
    if phase_check is not None:
        phase_check()
    catalog.verify()
    gate.validate_campaign(start, plan, admission)
    o.verify_authorities(profile, plan, start, gate)
    b.validate(scientific_start, "stage12_campaign_provenance_b2_v1")
    b.validate(admission, "stage12_segment_admission_b2_v1")
    b.require(
        start["scientific_campaign_start_sha256"] == b.digest(scientific_start)
        and admission["campaign_start_sha256"] == b.digest(scientific_start)
        and admission["operations_campaign_sha256"] == b.digest(start)
        and admission["window_plan_sha256"] == start["window_plan_sha256"]
        and admission["privacy_permission_sha256"]
        == start["privacy_permission_sha256"],
        "B2_CAMPAIGN_BINDING",
    )
    for key_name in (
        "campaign_id",
        "observation_binding_id",
        "window_plan_sha256",
        "privacy_permission_sha256",
        "scientific_decision_sha256",
        "stage11_input_binding_sha256",
        "materialization_contract_sha256",
        "retrieval_policy_id",
        "response_validation_contract_sha256",
        "response_extraction_contract_sha256",
        "candidate_schema_sha256",
        "response_interpretation_sha256",
    ):
        b.require(scientific_start[key_name] == start[key_name], "B2_CAMPAIGN_BINDING")
    b.require(
        scientific_start["operations_policy_sha256"] == b.digest(profile)
        and scientific_start["workload_sha256"] == b.digest(plan)
        and b.digest(runtime_inventory)
        == start["runtime_inventory_sha256"]
        == scientific_start["runtime_inventory_sha256"],
        "B2_RUNTIME_BINDING",
    )
    b.require(
        catalog.binding["population_scope"] == plan["population_scope"] == gate.scope
        and b.digest(catalog.binding) == plan["stage11_input_binding_sha256"],
        "B2_POPULATION_SCOPE",
    )
    gate.require(
        "response_rules",
        rules.evidence_sha256,
        {"interpretation": start["response_interpretation_sha256"]},
    )
    o.verify_work_manifest(work_factory, plan)
    slot = gate.validate_workload(
        catalog,
        profile,
        plan,
        work_factory,
        admission,
        output.parent / (output.name + "_selection.sqlite"),
    )
    b.require(
        type(slot) is dict
        and type(slot.get("max_attempts")) is int
        and slot["max_attempts"] > 0,
        "B2_SEGMENT_UNPLANNED",
    )
    segment_attempt_limit = slot["max_attempts"]
    recipes = {x["recipe_id"]: x for x in plan["control_recipes"]}
    b.require(set(control_adapters) == set(recipes), "B2_CONTROL_ADAPTER_REQUIRED")

    def target(row):
        if row["kind"] == "DATA":
            return c.materialize(
                catalog.core(row["query_semantic_id"]),
                bytes.fromhex(row["query_semantic_id"]),
                c.policy(row["result_limit"]),
                target_limit=profile["resources"]["pending_request_bytes"],
            )[0]
        return control_adapters[row["recipe_id"]].target(recipes[row["recipe_id"]])

    bound = 0
    for row in o.work_rows(work_factory(), plan):
        value = target(row)
        b.require(
            type(value) is bytes
            and len(value) > 0
            and len(value) <= profile["resources"]["pending_request_bytes"],
            "REQUEST_TARGET_TOO_LARGE",
        )
        bound = max(bound, len(value))
        del value
    b.require(bound > 0, "B2_EMPTY_WORKLOAD")

    def locate(work_id, ordinal):
        node = output
        while node is not None:
            path = node / "attempts" / f"{work_id:020d}_{ordinal:02d}"
            if path.exists():
                return path
            node = predecessor if node == output else journal.predecessor_root(node)
        b.require(False, "B2_RECEIPT_MISSING")

    def verify_receipt(row, event):
        root = locate(row["work_id"], event["attempt"])
        b.require(
            b.sha(io.read(root / "receipt.json")).hex()
            == event["receipt_inventory_sha256"],
            "B2_RECEIPT_CHANGED",
        )
        if row["kind"] == "DATA":
            result, _, _ = audit.reopen(root, **rules.kwargs())
        else:
            result = audit.report_control(
                root, recipes[row["recipe_id"]], control_adapters[row["recipe_id"]]
            )
        b.require(
            result["outcome"] == event["outcome"]["value"], "B2_RECEIPT_ASSOCIATION"
        )
        return result

    spent = bootstrap_spent(
        gate.records, admission["bootstrap_acquisition_sha256"], plan, profile, start
    )
    reserve_administration(gate.records, profile, plan, spent, preflight=False)
    b.require(spent["operations"] % 2 == 1, "B2_ADMIN_PHASE_ORDER")
    bootstrap = gate.records.get(
        admission["bootstrap_acquisition_sha256"], "bootstrap_administration"
    )
    b.require(
        bootstrap["segment_nonce"] == admission["segment_nonce"]
        and any(
            admission["preflight_observation_sha256"]
            in gate.records.get(e["finish_sha256"], "evidence_acquisition")["records"]
            for e in bootstrap["attempts"]
            if e["finish_sha256"] is not None
        ),
        "B2_PREFLIGHT_NOT_ACQUIRED",
    )
    rebase = None
    if predecessor is not None:
        scratch = output.parent / (output.name + "_reconcile.sqlite")
        rebase = recovery.clean_continuation(
            predecessor,
            start,
            profile,
            plan,
            authority=gate,
            new_segment_authority=admission["fresh_workload_authority_sha256"],
            works=work_factory,
            verify_receipt=verify_receipt,
            scratch=scratch,
        )
        b.require(
            bootstrap["predecessor_bootstrap_sha256"]
            == rebase["snapshot"]["bootstrap_acquisition_sha256"],
            "B2_ADMIN_PREDECESSOR",
        )
        b.require(
            admission["segment_id"] == rebase["snapshot"]["segment_id"] + 1
            and admission["predecessor_closure_sha256"]
            == rebase["snapshot"]["segment_closure_sha256"],
            "B2_PREDECESSOR_MISMATCH",
        )
    else:
        b.require(
            admission["segment_id"] == 1
            and admission["predecessor_closure_sha256"] is None,
            "B2_PREDECESSOR_MISMATCH",
        )
    gate.admit(admission["preflight_observation_sha256"], admission["segment_nonce"])
    evidence.release_authority(
        gate.records,
        writer_release_evidence,
        campaign_id=start["campaign_id"],
        segment_nonce=admission["segment_nonce"],
        now=clock.utc(),
        authority=gate,
    )
    carried_ms = (
        rebase["snapshot"]["controller"]["active_duration_ms"]
        if rebase is not None
        else 0
    )
    remaining_ms = plan["budgets"]["active_duration_ms"] - carried_ms
    b.require(remaining_ms > 0, "B2_PHASE_DEADLINE")
    phase_deadline_ns = phase_entered_ns + remaining_ms * 1_000_000

    def cumulative_check():
        b.require(clock.now_ns() < phase_deadline_ns, "B2_PHASE_DEADLINE")
        if phase_check is not None:
            phase_check()

    def cumulative_remaining():
        remaining = max(0, phase_deadline_ns - clock.now_ns()) / 1e9
        if phase_remaining_seconds is not None:
            remaining = min(remaining, phase_remaining_seconds())
        return remaining

    cumulative_check()
    ctl = scheduler.Coordinator(
        profile,
        plan,
        start,
        authority=gate,
        clock=clock,
        root=output,
        block_id=1,
        segment_authority=admission["fresh_workload_authority_sha256"],
        writer_exclusion_evidence=admission["writer_exclusion_evidence_sha256"],
        epoch=admission["epoch_id"],
        free_bytes=free_bytes,
        predecessor=predecessor,
        rebase=rebase,
        contract=o,
        segment_body={"segment_admission_sha256": b.digest(admission)},
        original_events=lambda node, binding: recovery.events(node, binding, plan),
        cumulative_check=cumulative_check,
        cumulative_remaining=cumulative_remaining,
    )
    gate.require("retrieval_limit", start["retrieval_policy_id"], plan)
    ctl.size_ready = lambda pending: (
        pending.work["kind"] == "SERVICE_CONTROL"
        or pending.work["result_limit"] == plan["result_limit"]
    )
    segment_initial_charge = sum(ctl.charged.values())
    writer, log = ctl.writer, ctl.journal
    records = {}
    last_response = clock.utc()

    def events():
        return recovery.events(output, start, plan)

    checkpoints = ExitStack()
    checkpoints.enter_context(io.cooperative_io(cumulative_check))
    try:
        ctl.start_sampling()
        writer.call(lambda: io.reserve(output / "attempts"))
        writer.call(lambda: log.write("segment_admission.json", admission))
        writer.call(lambda: log.write("scientific_start.json", scientific_start))
        writer.call(lambda: log.write("profile.json", profile))
        writer.call(lambda: log.write("plan.json", plan))
        for retained in (profile, plan, start, scientific_start, admission):
            writer.call(
                lambda retained=retained: gate.records.put(
                    b.canonical(retained),
                    owner=writer.assert_owner,
                    secret_guard=lambda raw: response.secret_guard(raw, key),
                )
            )
        metadata.stream_array(log, "work.json", o.work_rows(work_factory(), plan), plan)
        log.event(
            "PREFLIGHT_OBSERVED",
            {
                "record_sha256": admission["preflight_observation_sha256"],
                "authority_sha256": admission["fresh_workload_authority_sha256"],
                "service_evidence_state": "PROVISIONAL",
                "continuous_service_state": "NOT_VERIFIED",
            },
        )

        def begin(pending):
            row = pending.work
            root = output / "attempts" / f"{row['work_id']:020d}_{pending.attempt:02d}"
            gate.before_dispatch()
            if row["kind"] == "DATA":
                return audit.begin(
                    root,
                    row,
                    pending.attempt,
                    pending.target,
                    scientific_start=scientific_start,
                    admission=admission,
                    epoch=admission["epoch_id"],
                    now=clock.utc(),
                    core=catalog.core(row["query_semantic_id"]),
                )
            return audit.begin_control(
                root,
                {
                    "schema_version": o.CONTROL_BEGIN,
                    "campaign_start_sha256": b.digest(start),
                    "profile_sha256": b.digest(profile),
                    "plan_sha256": b.digest(plan),
                    "segment_id": log.segment,
                    "work_id": row["work_id"],
                    "attempt": pending.attempt,
                    "recipe_sha256": recipes[row["recipe_id"]]["recipe_sha256"],
                    "request_target_sha256": b.sha(pending.target).hex(),
                    "started_utc": clock.utc(),
                },
            )

        def worker(slot):
            def record_hash(capture):
                record = transport_audit.transport_record(
                    slot.pending.work, slot.key[1], capture, clock.utc()
                )
                transport_audit.validate_transport(record)
                records[slot.key] = record
                return b.digest(record)

            def persist():
                io.write(
                    locate(*slot.key) / "transport.json", b.canonical(records[slot.key])
                )

            is_control = slot.pending.work["kind"] == "SERVICE_CONTROL"
            timing = {}
            original_persist = persist

            def persist_control():
                original_persist()
                if is_control:
                    io.write(
                        locate(*slot.key) / "control_timing.json", b.canonical(timing)
                    )

            hooks = ctl.hooks(slot, record_hash, persist_control)

            class SafeHooks:
                def attempt_deadline_ns(self, started, maximum):
                    return (
                        min(
                            maximum,
                            started
                            + recipes[slot.pending.work["recipe_id"]]["max_duration_ms"]
                            * 1_000_000,
                        )
                        if is_control
                        else maximum
                    )

                def control_deadline(self):
                    if is_control and slot.started_ns is not None:
                        return (
                            slot.started_ns
                            + recipes[slot.pending.work["recipe_id"]]["max_duration_ms"]
                            * 1_000_000
                        )
                    return None

                def started(self, mono):
                    hooks.started(mono)

                def signal(self, *args):
                    hooks.signal(*args)

                def completed(self, capture):
                    if is_control:
                        ended = clock.now_ns()
                        b.require(
                            slot.started_ns is not None and ended >= slot.started_ns,
                            "B2_CONTROL_TIMING",
                        )
                        timing.update(
                            schema_version="stage12_control_timing_b2_v1",
                            begin_sha256=slot.begin_hash,
                            epoch_id=admission["epoch_id"],
                            started_mono_ns=slot.started_ns,
                            completed_mono_ns=ended,
                            max_duration_ms=recipes[slot.pending.work["recipe_id"]][
                                "max_duration_ms"
                            ],
                        )
                        if (
                            ended > self.control_deadline()
                            or capture.elapsed_ms > timing["max_duration_ms"]
                        ):
                            ctl.terminal("TERMINAL", "TIMEOUT")
                    hooks.completed(capture)

                def emit(self, write, deadline):
                    def guarded_write():
                        gate.before_dispatch()
                        write()
                        gate.emitted()

                    def bounded_deadline():
                        deadline()
                        cap = self.control_deadline()
                        b.require(cap is None or clock.now_ns() < cap, "TIMEOUT")

                    hooks.emit(guarded_write, bounded_deadline)

            try:
                capture = dispatch(slot.pending.work, slot.pending.target, SafeHooks())
                b.require(
                    slot.capture == capture and slot.ticket is not None,
                    "B2_UNACCOUNTED_DELIVERY",
                )
            except BaseException:
                with ctl.safety:
                    ctl.state, ctl.stop_reason = (
                        "RECOVERY_BLOCKED",
                        "UNACCOUNTED_DELIVERY",
                    )
                    slot.connection = False
                    ctl.wake.set()
                raise

        def finish(slot):
            nonlocal last_response
            gate.check()
            row = slot.pending.work
            root = locate(*slot.key)
            last_response = max(last_response, records[slot.key]["finished_utc"])
            if row["kind"] == "DATA":
                return audit.finish(
                    root,
                    records[slot.key],
                    slot.capture.payload,
                    key=key,
                    now=clock.utc(),
                    **rules.kwargs(),
                )
            return audit.finish_control(
                root,
                records[slot.key],
                slot.capture.payload,
                recipes[row["recipe_id"]],
                control_adapters[row["recipe_id"]],
                key=key,
            )

        resume_index = None
        if rebase:
            resume_index = catalog_module.connect(output / "resume_index.sqlite")
            resume_index.execute("create table prior(id integer primary key,body blob)")
            for row in rebase["ledger"]():
                resume_index.execute(
                    "insert into prior values(?,?)", (row["work_id"], b.canonical(row))
                )
            resume_index.commit()

        def old(row):
            saved = (
                resume_index.execute(
                    "select body from prior where id=?", (row["work_id"],)
                ).fetchone()
                if resume_index
                else None
            )
            return json.loads(saved[0]) if saved else None

        def pending(row):
            previous = old(row)
            n = (
                previous["charged_ordinals"][-1] + 1
                if previous and previous["state"] == "RETRY_DUE"
                else 1
            )
            due = (
                ctl.opened_ns + previous["retry_delay_ms"] * 1000000
                if previous and previous["state"] == "RETRY_DUE"
                else clock.now_ns()
            )
            materialized = target(row)
            b.require(len(materialized) <= bound, "REQUEST_TARGET_TOO_LARGE")
            return scheduler.Pending(row, materialized, n, due)

        ordinary = iter(
            r
            for r in work_factory()
            if old(r) is None or old(r)["state"] in ("UNBEGUN", "RETRY_DUE")
        )
        exhausted = False
        futures = {}
        with ThreadPoolExecutor(
            max_workers=ctl.capacity, thread_name_prefix="stage12-b2-http"
        ) as pool:
            while True:
                ctl.tick()
                if notice is not None:
                    h = notice()
                    if h is not None:
                        # Immediate latch precedes evidence read/persistence.
                        ctl.terminal("DRIFT", "KNOWN_CHANGE")
                        gate.interrupt(h)
                        log.event(
                            "NOTICE_RECEIVED",
                            {
                                "record_sha256": h,
                                "authority_sha256": admission[
                                    "fresh_workload_authority_sha256"
                                ],
                                "service_evidence_state": "QUARANTINED",
                                "continuous_service_state": "NOT_VERIFIED",
                            },
                            closure=True,
                        )
                if (
                    sum(ctl.charged.values()) - segment_initial_charge
                    >= segment_attempt_limit
                ):
                    ctl.pause_pending = True
                if pause_requested is not None and pause_requested():
                    ctl.pause_pending = True
                with ctl.safety:
                    control_deadlines = [
                        s.started_ns
                        + recipes[s.pending.work["recipe_id"]]["max_duration_ms"]
                        * 1_000_000
                        for s in ctl.slots.values()
                        if s.pending.work["kind"] == "SERVICE_CONTROL"
                        and s.started_ns is not None
                        and s.ticket is None
                    ]
                if ctl.stop_reason is None and any(
                    clock.now_ns() > x for x in control_deadlines
                ):
                    ctl.terminal("TERMINAL", "TIMEOUT")
                if ctl.stop_reason is None:
                    while (
                        not ctl.pause_pending
                        and not exhausted
                        and ctl.can_refill(bound)
                    ):
                        row = next(ordinary, None)
                        if row is None:
                            exhausted = True
                            break
                        ctl.queue(pending(row))
                    slot = ctl.admit(begin)
                    if slot is not None:
                        futures[slot.key] = pool.submit(worker, slot)
                    slot = None
                next_slot = next(
                    (
                        s
                        for s in ctl.slots.values()
                        if s.ticket == ctl.finalized_ticket + 1
                        and s.key in futures
                        and futures[s.key].done()
                    ),
                    None,
                )
                if next_slot is not None:
                    futures.pop(next_slot.key).result()
                    retry = ctl.finalize(next_slot, lambda slot=next_slot: finish(slot))
                    records.pop(next_slot.key, None)
                    if retry is not None:
                        ctl.queue(retry)
                    retry = next_slot = None
                    continue
                failed = [
                    k
                    for k, f in futures.items()
                    if f.done() and f.exception() is not None
                ]
                for k in failed:
                    futures.pop(k)
                if ctl.stop_reason:
                    if all(f.done() for f in futures.values()):
                        break
                elif (
                    exhausted and not ctl.pending or ctl.pause_pending
                ) and not ctl.slots:
                    break
                if futures:
                    ctl.wake.wait(
                        max(
                            0,
                            ctl.next_wakeup_ns(ctl.next_start_ns, *control_deadlines)
                            - clock.now_ns(),
                        )
                        / 1e9
                    )
                    ctl.wake.clear()
                elif ctl.pending:
                    clock.wait_until(
                        ctl.next_wakeup_ns(
                            ctl.next_start_ns,
                            ctl.cooldown_until,
                            *(p.due_ns for p in ctl.pending),
                        )
                    )
        if resume_index:
            resume_index.close()
        b.require(ctl.stop_sampling(), "B2_SAMPLER_UNCERTAIN")
        ctl.resource("PERIODIC")
        attempt_hash = o.manifest_digest(recovery.inventory(output, "attempts", plan))
        writer.check_deadline()
        index = reporting.Index(
            output.parent / (output.name + "_report_index.sqlite"),
            events,
            work_factory,
            verify_receipt,
            max_bytes=profile["resources"]["fixed_campaign_disk_bound_bytes"],
        )
        try:
            disposition = (
                ctl.state
                if ctl.stop_reason
                else "COMPLETED"
                if all(row["state"] == "DURABLE_SUCCESS" for row in index.ledger())
                else "PAUSED_CLEAN"
            )
            writer.check_deadline()
            measured = reporting.measurement(
                index,
                profile,
                plan,
                start,
                attempt_inventory=attempt_hash,
                administrative_spent=spent,
                disposition=disposition,
            )
            writer.call(lambda: log.write("measurement_report.json", measured))
            ledger_hash = metadata.stream_array(
                log, "work_ledger.json", index.ledger(), plan
            )
            remaining_hash = metadata.stream_array(
                log,
                "remaining_work_ledger.json",
                (r for r in index.ledger() if r["state"] in ("UNBEGUN", "RETRY_DUE")),
                plan,
            )
        except BaseException:
            try:
                index.close()
            except BaseException:
                pass  # Preserve the initiating failure; partial evidence stays.
            raise
        else:
            index.close()
            writer.check_deadline()
        b.require(
            not ctl.stop_reason
            and measured["resource_sampling_complete"]
            and measured["receipts_complete"]
            and (disposition == "PAUSED_CLEAN" or measured["report_complete"]),
            "B2_CAMPAIGN_INCOMPLETE",
        )
        close_info = {
            "scientific_start_sha256": b.digest(scientific_start),
            "admission": admission,
            "measurement_report_sha256": b.digest(measured),
            "attempt_inventory_sha256": attempt_hash,
            "controller_reconciliation_sha256": ledger_hash,
            "last_response_utc": last_response,
        }
        # Adapter yields retained nonsecret record bytes; imports and all fsyncs
        # use the same sole writer. No hidden network/polling in this interface.
        prior_begin = bootstrap["attempts"][-1]["begin_sha256"]
        post_bounds = reserve_administration(
            gate.records, profile, plan, spent, preflight=False
        )
        begin_admin, finish_admin = evidence.acquire(
            gate.records,
            lambda: close_segment(close_info),
            writer=writer,
            clock=clock,
            campaign_id=start["campaign_id"],
            segment_nonce=admission["segment_nonce"],
            epoch_id=admission["epoch_id"],
            bounds=post_bounds,
            authority=gate,
            authority_hash=admission["fresh_workload_authority_sha256"],
            ordinal=spent["operations"] + 1,
            predecessor_begin=prior_begin,
            secret_guard=lambda raw: response.secret_guard(raw, key),
        )
        final_admin = evidence.append_administration(
            gate.records,
            previous_hash=admission["bootstrap_acquisition_sha256"],
            begin=begin_admin,
            finish=finish_admin,
            plan=plan,
            authority_hash=admission["fresh_workload_authority_sha256"],
            writer=writer,
        )
        spent = bootstrap_spent(gate.records, final_admin, plan, profile, start)
        closures = []
        for h in finish_admin["records"]:
            try:
                obj = b.parse(gate.records.raw(h))
            except c.Stage12Error:
                continue
            if obj["schema_version"] == "stage12_segment_closure_b2_v1":
                closures.append(h)
        b.require(len(closures) == 1, "CLOSURE_MISSING")
        closure_hash = closures[0]
        writer.call(
            lambda: log.write(
                "administrative_ledger.json",
                gate.records.get(final_admin, "bootstrap_administration"),
            )
        )

        closure = gate.segment_closure(
            closure_hash,
            start_hash=b.digest(scientific_start),
            attempt_inventory=attempt_hash,
            controller_reconciliation=ledger_hash,
            resource_report=b.digest(measured),
            last_response_utc=last_response,
            predecessor=admission["predecessor_closure_sha256"],
        )
        for kind, h in (
            ("POSTFLIGHT_OBSERVED", closure["postflight_sha256"]),
            ("SEGMENT_REVIEWED", closure_hash),
        ):
            log.event(
                kind,
                {
                    "record_sha256": h,
                    "authority_sha256": closure["review_decision_sha256"],
                    "service_evidence_state": "CLOSED_OBSERVATIONAL",
                    "continuous_service_state": "NOT_VERIFIED",
                },
                closure=True,
            )
        log.event(
            "SEGMENT_CLOSE",
            {
                "disposition": disposition,
                "closure_evidence_sha256": closure_hash,
                "last_ticket": ctl.last_ticket,
            },
            closure=True,
        )
        state = replay_engine.replay(events(), contract=o)
        event_hash = metadata.stream_array(
            log,
            "event_inventory.json",
            recovery.inventory(output, "events", plan),
            plan,
        )
        attempt_hash = metadata.stream_array(
            log,
            "attempt_inventory.json",
            recovery.inventory(output, "attempts", plan),
            plan,
        )
        final = {
            k: v
            for k, v in measured.items()
            if k not in ("input_last_event_seq", "administrative_spent")
        }
        final["counts"] = {
            **measured["counts"],
            "administrative_operations": reporting.statistics.count(
                spent["operations"], spent["operations"]
            ),
        }
        final.update(
            schema_version=o.REPORT,
            event_inventory_sha256=event_hash,
            service_evidence_state="CLOSED_OBSERVATIONAL",
            measurement_report_sha256=b.digest(measured),
            segment_closure_sha256=closure_hash,
            campaign_closure_sha256=None,
        )
        b.validate(final)
        final_hash = writer.call(lambda: log.write("operations_report.json", final))
        evidence.release_authority(
            gate.records,
            writer_release_evidence,
            campaign_id=start["campaign_id"],
            segment_nonce=admission["segment_nonce"],
            now=clock.utc(),
            authority=gate,
        )
        controller = {
            k: state[k]
            for k in (
                "state_id",
                "block_id",
                "last_ticket",
                "consecutive_retryable",
                "recent",
                "overload_carry",
                "breaker_reason",
                "cooldown_delay_ms",
                "active_duration_ms",
            )
        }
        controller.update(
            charged_data_attempts=ctl.charged["DATA"],
            charged_control_attempts=ctl.charged["SERVICE_CONTROL"],
            administrative_operations=spent["operations"],
            administrative_duration_ms=spent["duration_ms"],
            administrative_bytes=spent["bytes"],
            stored_bytes=log.stored_bytes,
            event_count=log.seq,
            remaining_work_ledger_sha256=remaining_hash,
            monitoring_state="CLOSED_OBSERVATIONAL",
            resume_eligible=disposition == "PAUSED_CLEAN",
        )
        snapshot = {
            "schema_version": o.SNAPSHOT,
            "campaign_start_sha256": b.digest(start),
            "segment_id": log.segment,
            "last_event_seq": log.seq,
            "last_event_sha256": log.last_hash,
            "event_inventory_sha256": event_hash,
            "attempt_inventory_sha256": attempt_hash,
            "work_ledger_sha256": ledger_hash,
            "controller": controller,
            "closure_evidence_sha256": closure_hash,
            "writer_release_evidence_sha256": writer_release_evidence,
            "sealed_utc": clock.utc(),
            "disposition": disposition,
            "observation_binding_id": start["observation_binding_id"],
            "window_plan_sha256": start["window_plan_sha256"],
            "privacy_permission_sha256": start["privacy_permission_sha256"],
            "predecessor_closure_sha256": admission["predecessor_closure_sha256"],
            "segment_closure_sha256": closure_hash,
            "operations_report_sha256": final_hash,
            "bootstrap_acquisition_sha256": final_admin,
            "service_evidence_state": "CLOSED_OBSERVATIONAL",
            "continuous_service_state": "NOT_VERIFIED",
        }
        b.validate(snapshot)
        writer.call(lambda: log.write("snapshot.json", snapshot))
        writer.release(
            {
                "snapshot_sha256": b.digest(snapshot),
                "writer_release_evidence_sha256": writer_release_evidence,
            },
            segment_seal=True,
        )
        recovery.reopen(
            output,
            start,
            profile,
            plan,
            works=work_factory,
            verify_receipt=verify_receipt,
            scratch=output.parent / (output.name + "_reopen.sqlite"),
            authority=gate,
        )
        catalog.verify()
        return final
    except BaseException:
        ctl.stop_sampling()
        writer.abort()
        # Caller preserves the failed directory; never manufactures a clean
        # snapshot, retries unknown delivery, or prints exception payloads.
        raise
    finally:
        ctl.stop_sampling()
        checkpoints.close()


def prepare_bootstrap(
    root,
    *,
    records,
    raw_factory,
    clock,
    profile,
    plan,
    start,
    segment_nonce,
    epoch_id,
    authority,
    authority_hash,
    writer_release_evidence,
    secret_guard,
    previous_hash=None,
):
    """Acquire fresh local preflight bytes before opening the campaign writer."""
    o.validate_plan(plan, profile)
    authority.require(
        "bootstrap_writer",
        authority_hash,
        {"campaign_id": start["campaign_id"], "segment_nonce": segment_nonce},
    )
    evidence.release_authority(
        records,
        writer_release_evidence,
        campaign_id=start["campaign_id"],
        segment_nonce=segment_nonce,
        now=clock.utc(),
        authority=authority,
    )
    spent = (
        bootstrap_spent(records, previous_hash, plan, profile, start)
        if previous_hash
        else {"operations": 0, "duration_ms": 0, "bytes": 0}
    )
    b.require(spent["operations"] % 2 == 0, "B2_ADMIN_PHASE_ORDER")
    pre_bounds = reserve_administration(records, profile, plan, spent, preflight=True)
    prior = (
        records.get(previous_hash, "bootstrap_administration")["attempts"][-1][
            "begin_sha256"
        ]
        if previous_hash
        else None
    )
    writer = journal.Writer(
        root, 1, profile["resources"]["writer_guard_ms"], lambda: None
    )
    try:
        begin, finish = evidence.acquire(
            records,
            raw_factory,
            writer=writer,
            clock=clock,
            campaign_id=start["campaign_id"],
            segment_nonce=segment_nonce,
            epoch_id=epoch_id,
            bounds=pre_bounds,
            authority=authority,
            authority_hash=authority_hash,
            ordinal=spent["operations"] + 1,
            predecessor_begin=prior,
            secret_guard=secret_guard,
        )
        ledger = evidence.append_administration(
            records,
            previous_hash=previous_hash,
            begin=begin,
            finish=finish,
            plan=plan,
            authority_hash=authority_hash,
            writer=writer,
        )
        writer.call(
            lambda: io.write(root / "administrative_ledger.json", records.raw(ledger))
        )
        bootstrap_spent(records, ledger, plan, profile, start)
        writer.release(
            {
                "bootstrap_sha256": ledger,
                "writer_release_evidence_sha256": writer_release_evidence,
            }
        )
        b.require(
            io.metadata(io.read(root / "_WRITER_RELEASED.json"))
            == {
                "bootstrap_sha256": ledger,
                "writer_release_evidence_sha256": writer_release_evidence,
            },
            "B2_WRITER_UNCERTAIN",
        )
        return ledger
    except BaseException:
        writer.abort()
        raise

"""Validated on-disk report joins; unknown receipts never become exact successes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_catalog as catalog
from . import s12_public_reporting as statistics
from . import s12_retrieval_contract as c


class Index:
    """One report-lifetime bounded SQLite index; sources are rechecked on exit."""

    def __init__(
        self,
        path: Path,
        events: Callable,
        works: Callable,
        verify_receipt: Callable,
        *,
        max_bytes: int,
    ):
        b.require(not path.exists(), "B2_REPORT_INDEX_EXISTS")
        self.path, self.events, self.works, self.verify = (
            path,
            events,
            works,
            verify_receipt,
        )
        self.db = catalog.connect(path)
        self.db.execute("pragma page_size=4096")
        self.db.execute("pragma max_page_count=" + str(max(1, max_bytes // 4096)))
        self.db.executescript(
            "create table event(seq integer primary key, kind text, work integer, attempt integer, epoch text, body blob);create index event_work on event(work,seq);create table work(id integer primary key, body blob);create table verified(work integer,attempt integer,valid integer,terminal blob,primary key(work,attempt));"
        )
        for work in works():
            self.db.execute(
                "insert into work values(?,?)", (work["work_id"], b.canonical(work))
            )
        self.work_hash = o.manifest_digest(works())

        def indexed_events():
            for event in events():
                self.db.execute(
                    "insert into event values(?,?,?,?,?,?)",
                    (
                        event["seq"],
                        event["kind"],
                        event["body"].get("work_id"),
                        event["body"].get("attempt"),
                        event["epoch_id"],
                        b.canonical(event),
                    ),
                )
                yield event

        self.event_hash = o.manifest_digest(indexed_events())
        self.db.commit()
        for work in self.rows():
            for event in self.for_work(work["work_id"]):
                if event["kind"] != "ATTEMPT_FINALIZED":
                    continue
                body = event["body"]
                terminal = None
                try:
                    terminal = verify_receipt(work, body)
                    begins = [
                        e["body"]
                        for e in self.for_work(work["work_id"])
                        if e["kind"] == "BEGIN_DURABLE"
                        and e["body"]["attempt"] == body["attempt"]
                    ]
                    b.require(
                        type(terminal) is dict
                        and terminal["outcome"] == body["outcome"]["value"]
                        and len(begins) == 1
                        and terminal["begin_sha256"] == begins[0]["begin_sha256"],
                        "B2_RECEIPT_ASSOCIATION",
                    )
                    if work["kind"] == "SERVICE_CONTROL":
                        timing = terminal["_control_timing"]
                        starts = [
                            e
                            for e in self.for_work(work["work_id"])
                            if e["kind"] == "ATTEMPT_STARTED"
                            and e["body"]["attempt"] == body["attempt"]
                        ]
                        done = [
                            e
                            for e in self.for_work(work["work_id"])
                            if e["kind"] == "NETWORK_DONE"
                            and e["body"]["attempt"] == body["attempt"]
                        ]
                        b.require(
                            len(starts) == len(done) == 1
                            and timing["epoch_id"]
                            == starts[0]["epoch_id"]
                            == done[0]["epoch_id"]
                            and timing["started_mono_ns"]
                            == starts[0]["body"]["started_mono_ns"]
                            and timing["started_mono_ns"]
                            <= timing["completed_mono_ns"]
                            <= done[0]["body"]["completed_mono_ns"],
                            "B2_CONTROL_TIMING",
                        )
                    valid = 1
                except (c.Stage12Error, OSError, KeyError, ValueError):
                    valid = 0
                self.db.execute(
                    "insert into verified values(?,?,?,?)",
                    (
                        work["work_id"],
                        body["attempt"],
                        valid,
                        b.canonical(terminal) if valid else None,
                    ),
                )
        self.db.commit()

    def rows(self):
        for (raw,) in self.db.execute("select body from work order by id"):
            yield json.loads(raw)

    def all(self):
        for (raw,) in self.db.execute("select body from event order by seq"):
            yield json.loads(raw)

    def for_work(self, work_id):
        for (raw,) in self.db.execute(
            "select body from event where work=? order by seq", (work_id,)
        ):
            yield json.loads(raw)

    def verified(self, work_id, attempt):
        row = self.db.execute(
            "select valid,terminal from verified where work=? and attempt=?",
            (work_id, attempt),
        ).fetchone()
        return json.loads(row[1]) if row and row[0] else None

    def ledger(self):
        for work in self.rows():
            begins = []
            final = {}
            invalid = False
            for event in self.for_work(work["work_id"]):
                x = event["body"]
                ordinal = x.get("attempt")
                if event["kind"] == "BEGIN_DURABLE":
                    begins.append(ordinal)
                    b.require(
                        begins == list(range(1, len(begins) + 1)) and len(begins) <= 5,
                        "B2_ATTEMPT_HISTORY",
                    )
                elif event["kind"] == "ATTEMPT_FINALIZED":
                    b.require(
                        ordinal in begins
                        and ordinal not in final
                        and x["outcome"]["kind"] == work["kind"],
                        "B2_ATTEMPT_HISTORY",
                    )
                    final[ordinal] = x
                    invalid |= self.verified(work["work_id"], ordinal) is None
            state = "UNBEGUN"
            outcome = selected = delay = None
            if begins:
                if invalid or len(final) != len(begins):
                    state = "UNKNOWN_DELIVERY"
                    outcome = {"kind": work["kind"], "value": "UNKNOWN_DELIVERY"}
                else:
                    last = final[begins[-1]]
                    outcome = last["outcome"]
                    successes = [
                        i
                        for i, x in final.items()
                        if x["outcome"]["value"] in (*c.SUCCESS, "CONTROL_SUCCESS")
                    ]
                    b.require(
                        not successes or successes == [begins[-1]],
                        "B2_DUPLICATE_DISPATCH",
                    )
                    b.require(
                        all(
                            final[i]["outcome"]["value"]
                            == "TECHNICAL_FAILURE_RETRYABLE"
                            for i in begins[:-1]
                        ),
                        "B2_ATTEMPT_AFTER_TERMINAL",
                    )
                    if successes:
                        state = "DURABLE_SUCCESS"
                        selected = last["receipt_inventory_sha256"]
                    elif (
                        outcome["value"] == "TECHNICAL_FAILURE_RETRYABLE"
                        and begins[-1] < 5
                    ):
                        state = "RETRY_DUE"
                        delay = last["retry_delay_ms"]
                        b.uint(delay, True)
                    else:
                        state = "TERMINAL"
            row = {
                "work_id": work["work_id"],
                "charged_ordinals": begins,
                "selected_receipt_sha256": selected,
                "last_outcome": outcome,
                "retry_delay_ms": delay,
                "state": state,
            }
            b.validate_type(row, "WorkLedgerRow")
            yield row

    def verify_sources(self):
        b.require(
            o.manifest_digest(self.events()) == self.event_hash
            and o.manifest_digest(self.works()) == self.work_hash,
            "B2_REPORT_SOURCE_CHANGED",
        )

    def close(self):
        try:
            self.verify_sources()
        finally:
            self.db.close()


def measurement(
    index: Index,
    profile,
    plan,
    start,
    *,
    attempt_inventory: str,
    administrative_spent: dict,
    disposition: str,
):
    o.validate_plan(plan, profile)
    counts = dict.fromkeys(o.COUNT_KEYS, 0)
    counts.update(
        planned_data=plan["budgets"]["data_observations"],
        required_controls=plan["budgets"]["required_control_observations"],
        reserved_controls=0,
        administrative_operations=administrative_spent["operations"],
    )
    unknown = set()
    resources = True
    periodic = False
    last_observed = None
    sample_period = 100_000_000
    epochs = set()
    first = last = None
    tail = None
    mutations = {}
    finals = network = timings = 0
    for event in index.all():
        tail = event
        k, x = event["kind"], event["body"]
        epochs.add(event["epoch_id"])
        if k == "SEGMENT_OPEN":
            if last_observed is not None and not periodic:
                resources = False
            last_observed = event["mono_ns"]
            periodic = False
        elif k == "BEGIN_DURABLE":
            counts["begins_charged"] += 1
        elif k == "ATTEMPT_STARTED":
            counts["attempt_starts"] += 1
            work = json.loads(
                index.db.execute(
                    "select body from work where id=?", (x["work_id"],)
                ).fetchone()[0]
            )
            counts[
                "control_attempt_starts"
                if work["kind"] == "SERVICE_CONTROL"
                else "first_attempt_starts"
                if x["attempt"] == 1
                else "retry_attempt_starts"
            ] += 1
            first = (
                x["started_mono_ns"]
                if first is None
                else min(first, x["started_mono_ns"])
            )
        elif k == "EMIT_COMMITTED":
            counts["emission_commits"] += 1
        elif k == "EMISSION":
            counts["emissions_entered"] += x["result"] != "UNKNOWN"
        elif k == "NETWORK_DONE":
            network += 1
        elif k == "ATTEMPT_FINALIZED":
            finals += 1
            receipt = index.verified(x["work_id"], x["attempt"])
            if receipt is None:
                unknown.update(
                    (
                        "http_completions",
                        "http_200",
                        "durable_valid_data",
                        "durable_valid_zero",
                        "durable_retryable",
                        "durable_terminal_failure",
                        "unprocessed_data",
                    )
                )
            else:
                counts["http_completions"] += x["status"] is not None
                counts["http_200"] += x["status"] == 200
                counts["durable_valid_data"] += (
                    x["outcome"]["kind"] == "DATA" and receipt["outcome"] in c.SUCCESS
                )
                counts["durable_valid_zero"] += (
                    x["outcome"]["kind"] == "DATA"
                    and receipt["outcome"] == c.SUCCESS[1]
                )
                counts["durable_retryable"] += (
                    receipt["outcome"] == "TECHNICAL_FAILURE_RETRYABLE"
                )
                counts["durable_terminal_failure"] += (
                    receipt["outcome"] in o.FAILURES
                    and receipt["outcome"] != "TECHNICAL_FAILURE_RETRYABLE"
                )
        elif k == "AUDIT_TIMING":
            timings += 1
        elif k == "RESOURCE":
            mutations[x["cause"]] = mutations.get(x["cause"], 0) + 1
            if (
                x["cause"] in ("PERIODIC", "START_RESERVE")
                and x["free_allocated_disk_bytes"] is None
            ):
                resources = False
            if x["cause"] == "PERIODIC":
                observed = x["observed_mono_ns"]
                resources &= (
                    last_observed is not None
                    and 0 <= observed - last_observed <= sample_period
                    and observed <= event["mono_ns"]
                    and x["free_allocated_disk_bytes"] is not None
                )
                last_observed = observed
                last = observed
                periodic = True
        elif k == "COOLDOWN":
            counts["cooldown_events"] += 1
        elif k == "DOWNSHIFT":
            counts["downshift_events"] += 1
        elif k == "STOP":
            counts["breakers"] += 1
    complete = True
    for row in index.ledger():
        work = json.loads(
            index.db.execute(
                "select body from work where id=?", (row["work_id"],)
            ).fetchone()[0]
        )
        complete &= row["state"] == "DURABLE_SUCCESS"
        if row["state"] == "UNKNOWN_DELIVERY":
            counts["unknown_delivery"] += 1
            unknown.update(
                (
                    "http_completions",
                    "http_200",
                    "durable_retryable",
                    "durable_terminal_failure",
                )
            )
            if work["kind"] == "DATA":
                unknown.update(
                    ("durable_valid_data", "durable_valid_zero", "unprocessed_data")
                )
        elif work["kind"] == "DATA" and row["state"] not in (
            "DURABLE_SUCCESS",
            "TERMINAL",
        ):
            counts["unprocessed_data"] += 1
    resources &= bool(
        periodic
        and tail
        and tail["kind"] == "RESOURCE"
        and tail["body"]["cause"] == "PERIODIC"
        and mutations.get("STATE_CHANGE", 0) == len(epochs)
        and mutations.get("START_RESERVE", 0)
        == mutations.get("QUEUE_REMOVE", 0)
        == counts["begins_charged"]
        and mutations.get("CONNECTION_RELEASE", 0) == network
        and mutations.get("RESERVATION_RELEASE", 0) == finals
        and mutations.get("QUEUE_ADD", 0) >= counts["begins_charged"]
    )
    receipts_ok = not unknown and counts["unknown_delivery"] == 0
    duration = (
        0
        if first is None and counts["begins_charged"] == 0 and len(epochs) == 1
        else last - first
        if first is not None
        and last is not None
        and last >= first
        and len(epochs) == 1
        and receipts_ok
        else None
    )

    def values():
        for work in index.rows():
            started = {}
            done = {}
            timing = {}
            for event in index.for_work(work["work_id"]):
                x = event["body"]
                n = x.get("attempt")
                if event["kind"] == "ATTEMPT_STARTED":
                    started[n] = x["started_mono_ns"]
                elif event["kind"] == "NETWORK_DONE":
                    done[n] = x["elapsed_ms"]
                elif event["kind"] == "AUDIT_TIMING":
                    b.require(n not in timing, "B2_TIMING_DUPLICATE")
                    timing[n] = x
            for ordinal in sorted(done):
                if index.verified(work["work_id"], ordinal) is None:
                    continue
                yield "transport_all", done[ordinal]
                if work["kind"] == "DATA":
                    yield "transport_data", done[ordinal]
                if ordinal in timing:
                    x = timing[ordinal]
                    ordered = [
                        x[k]
                        for k in (
                            "writer_enqueued_ns",
                            "writer_started_ns",
                            "receipt_reopened_ns",
                            "finalized_event_ack_ns",
                            "reservation_released_ns",
                        )
                    ]
                    b.require(
                        ordered == sorted(ordered)
                        and ordinal in started
                        and ordered[0] >= started[ordinal],
                        "B2_TIMING_INVALID",
                    )
                    yield (
                        "writer_wait",
                        (x["receipt_reopened_ns"] - x["writer_enqueued_ns"] + 999999)
                        // 1000000,
                    )
                    if work["kind"] == "DATA":
                        yield (
                            "full_slot_data",
                            (x["reservation_released_ns"] - started[ordinal] + 999999)
                            // 1000000,
                        )

    latencies = statistics.exact_stats(values, tuple(o.TYPES["Latencies"]))
    timing_ok = timings == finals == network
    if not receipts_ok or not timing_ok:
        for metric in latencies.values():
            for k in ("p50_ms", "p95_ms", "p99_ms", "max_ms"):
                metric[k] = None
    rate = lambda name: statistics.ratio(
        None if name in unknown else counts[name], duration, per_second=True
    )
    rates = {
        "data_first_dispatch_per_s": rate("first_attempt_starts"),
        "all_attempts_per_s": rate("attempt_starts"),
        "http_completions_per_s": rate("http_completions"),
        "durable_data_per_s": rate("durable_valid_data"),
        "retry_fraction": statistics.ratio(
            counts["retry_attempt_starts"],
            counts["first_attempt_starts"] + counts["retry_attempt_starts"],
        ),
    }
    if duration is None:
        rates = dict.fromkeys(rates)
    reasons = []
    if not resources or not timing_ok:
        reasons.append("INSUFFICIENT_MEASUREMENT")
    if not receipts_ok:
        reasons.append("UNKNOWN_DELIVERY")
    if not complete:
        reasons.append("INCOMPLETE_WORK")
    report = {
        "schema_version": "stage12_development_measurement_report_b2_v1",
        "scope": "DEVELOPMENT_ONLY",
        "campaign_start_sha256": b.digest(start),
        "profile_sha256": b.digest(profile),
        "plan_sha256": b.digest(plan),
        "event_inventory_sha256": index.event_hash,
        "attempt_inventory_sha256": attempt_inventory,
        "work_ledger_sha256": o.manifest_digest(index.ledger()),
        "continuous_service_state": "NOT_VERIFIED",
        "resource_sampling_complete": bool(resources),
        "receipts_complete": receipts_ok,
        "counts": {
            k: statistics.count(None if k in unknown else v, v)
            for k, v in counts.items()
        },
        "rates": rates,
        "latencies": latencies,
        "duration_ns": duration,
        "disposition": disposition,
        "reasons": sorted(reasons),
        "report_complete": bool(resources and receipts_ok and complete and timing_ok),
        "population_scope": plan["population_scope"],
        "input_last_event_seq": tail["seq"],
        "administrative_spent": administrative_spent,
    }
    b.validate(report)
    index.verify_sources()
    return report

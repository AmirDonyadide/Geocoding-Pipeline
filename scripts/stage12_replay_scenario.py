"""Bounded no-service diagnostic checks; never live campaign continuation."""

from __future__ import annotations

import hashlib
from collections import Counter
from itertools import zip_longest
import os
from pathlib import Path
import stat
import threading

from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_audit as audit,
    s12_public_journal as journal,
    s12_public_matrix as matrix,
    s12_public_operations as o,
    s12_public_operational_audit as capture,
    s12_public_recovery as recovery,
    s12_public_reporting as reporting,
    s12_public_response as validation,
    s12_public_runtime as runtime,
    s12_response as response,
    s12_retrieval_contract as c,
    s12_storage as io,
)
from safe_geocoding_pipeline.preprocessing.stages.s12_public_fresh_reads import (
    FreshReads,
)
from safe_geocoding_pipeline.preprocessing.stages.s12_public_work_index import WorkIndex


def parent_fsync_open(path, flags, output):
    forbidden = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    required = os.O_DIRECTORY | os.O_NOFOLLOW
    return (
        type(flags) is int
        and flags & required == required
        and not flags & forbidden
        and path == output.resolve().parent
    )


class AccessGuard:
    """The actual installed audit policy, independently exercised in a child."""

    def __init__(
        self,
        *,
        allowed,
        output,
        proc_self,
        cgroup_root,
        proc_names,
        cgroup_names,
        maximum_creations,
    ):
        self.allowed = tuple(Path(p).resolve() for p in allowed)
        self.output = output.resolve()
        self.proc_self, self.cgroup_root = proc_self.resolve(), cgroup_root.resolve()
        self.proc_names, self.cgroup_names = proc_names, cgroup_names
        self.maximum_creations = maximum_creations
        self.creations = 24  # Fixed launcher metadata reservation, never refunded.
        self.lock = threading.Lock()

    @staticmethod
    def denied(*_a, **_kw):
        raise PermissionError("PUBLIC_REPLAY_ACCESS_DENIED")

    def audit(self, event, values):
        if event.startswith(
            ("socket.", "subprocess.", "os.exec", "os.spawn")
        ) or event in ("os.system", "os.fork", "os.posix_spawn"):
            self.denied()
        if event == "open" and isinstance(values[0], (str, bytes)):
            path = Path(os.path.realpath(os.fsdecode(values[0])))
            if path.is_relative_to(self.proc_self) and (
                path.parent != self.proc_self or path.name not in self.proc_names
            ):
                self.denied()
            if (
                path.is_relative_to(self.cgroup_root)
                and path.name not in self.cgroup_names
            ):
                self.denied()
            if any(
                part in (".ssh", ".config", "credentials") or part.startswith(".env")
                for part in path.parts
            ):
                self.denied()
            if (
                str(path) not in ("/dev/null", "/dev/urandom")
                and not any(path == p or path.is_relative_to(p) for p in self.allowed)
                and not parent_fsync_open(path, values[2], self.output)
            ):
                self.denied()
            creating = type(values[2]) is int and bool(values[2] & os.O_CREAT)
        else:
            creating = event == "os.mkdir"
            path = Path(os.path.realpath(os.fsdecode(values[0]))) if creating else None
        if creating:
            c.require(
                path == self.output or path.is_relative_to(self.output),
                "REPLAY_CREATION_SCOPE_INVALID",
            )
            with self.lock:
                c.require(
                    self.creations < self.maximum_creations, "REPLAY_CREATION_LIMIT"
                )
                self.creations += 1


def live_safety(ctl, *, root, isolation, check):
    """Post-release ownership checks; a pre-release fence cannot be reused."""
    check()
    c.require(isolation is True and ctl is not None, "REPLAY_ISOLATION_UNVERIFIED")
    writer = ctl.writer
    c.require(
        writer.root.absolute() == Path(root).absolute(), "REPLAY_ROOT_SCOPE_INVALID"
    )
    c.require(
        writer.closed
        and not writer.failed.is_set()
        and not writer.thread.is_alive()
        and writer.mailbox.empty()
        and writer.periodic.empty(),
        "REPLAY_WRITER_UNSAFE",
    )
    c.require(
        ctl.sample_stop.is_set()
        and not ctl.sample_join_failed
        and ctl.sample_thread is not None
        and not ctl.sample_thread.is_alive()
        and not ctl.sample_busy
        and not ctl.slots
        and not ctl.begin_in_progress
        and not any(
            t.name.startswith("stage12-public-http") for t in threading.enumerate()
        ),
        "REPLAY_WORKERS_UNJOINED",
    )
    c.require(ctl.sample_slot.acquire(blocking=False), "REPLAY_SAMPLE_SLOT_BUSY")
    ctl.sample_slot.release()
    fence = writer.closure_fence
    info = writer.root.stat(follow_symlinks=False)
    io.private_directory(writer.root)
    c.require(
        fence is not None
        and fence.writer is writer
        and fence.owner == threading.get_ident()
        and fence.path == writer.root.resolve()
        and fence.identity == (info.st_dev, info.st_ino)
        and stat.S_ISDIR(info.st_mode),
        "REPLAY_EXCLUSION_INVALID",
    )


def binding(view):
    """A bounded identity over every freshly read member, checked again later."""
    digest = hashlib.sha256()
    for name, identity in sorted(view.directories.items()):
        digest.update(c.canonical(["directory", name, *identity]))
    for name in sorted(view.inputs):
        info = (view.root / name).stat(follow_symlinks=False)
        digest.update(
            c.canonical(
                [
                    "file",
                    name,
                    view.hashes[name].hex(),
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_uid,
                    info.st_gid,
                    info.st_nlink,
                    info.st_size,
                ]
            )
        )
    info = view.root.stat(follow_symlinks=False)
    return (
        str(view.root.resolve()),
        info.st_dev,
        info.st_ino,
        len(view.inputs),
        digest.hexdigest(),
    )


def fresh_binding(root, *, check):
    with io.cooperative_io(check), FreshReads(root, check=check) as view:
        result = binding(view)
    return result


def bounded_rows(rows, limit, *, validate=lambda row: None):
    result = []
    for row in rows:
        c.require(len(result) < limit, "REPLAY_ROW_BOUND_EXCEEDED")
        validate(row)
        result.append(row)
    return result


def comparison_row(row):
    c.require(
        type(row) is dict and set(row) == {"first_work_id", "next_work_id", "equal"}
    )
    c.require(type(row["equal"]) is bool)
    for key in ("first_work_id", "next_work_id"):
        o.uint(row[key], True)
        c.require(row[key] <= 64)


class ScenarioSequence:
    """Four independent diagnostic roots; never a live work scheduler."""

    def __init__(self, scenarios):
        c.require(
            0 < len(scenarios) <= 4
            and len({s["name"] for s in scenarios}) == len(scenarios)
        )
        self.scenarios, self.rows, self.first_failure = scenarios, [], None

    def note(self, failure):
        if self.first_failure is None and failure is not None:
            self.first_failure = dict(failure)

    def pending(self):
        for index, scenario in enumerate(self.scenarios, 1):
            yield index, scenario
            c.require(len(self.rows) == index, "REPLAY_SCENARIO_RESULT_MISSING")
            if not self.rows[-1]["safe_to_continue"]:
                break

    def record(self, row):
        c.require(
            len(self.rows) < len(self.scenarios)
            and row["name"] == self.scenarios[len(self.rows)]["name"],
            "REPLAY_SCENARIO_ORDER_INVALID",
        )
        c.require(
            row["safe_to_continue"] or row["unexpected_failure"] is not None,
            "REPLAY_UNSAFE_DISPOSITION_MISSING",
        )
        self.note(row["unexpected_failure"])
        self.rows.append(row)


def measurement(events, *, maximum_events, period_ns):
    """Prove hard rows/timings separately from actual periodic schedule gaps."""
    mutations, timings = Counter(), set()
    starts = finals = networks = segments = resource_count = periodic_count = 0
    prior = tail = None
    gaps, gap_count, maximum_gap = [], 0, 0

    def gap(first, second, seq):
        nonlocal gap_count, maximum_gap
        value = second - first
        maximum_gap = max(maximum_gap, value)
        if not 0 <= value <= period_ns:
            gap_count += 1
            if len(gaps) < 16:
                gaps.append({"to_seq": seq, "gap_ns": value})

    for event in events():
        c.require(event["seq"] <= maximum_events)
        tail = event
        body = event["body"]
        if event["kind"] == "SEGMENT_OPEN":
            segments += 1
            prior = event["mono_ns"]
        elif event["kind"] == "BEGIN_DURABLE":
            starts += 1
        elif event["kind"] == "NETWORK_DONE":
            networks += 1
        elif event["kind"] == "ATTEMPT_FINALIZED":
            finals += 1
        elif event["kind"] == "AUDIT_TIMING":
            key = (body["work_id"], body["attempt"])
            c.require(
                key not in timings and len(timings) < 64, "REPLAY_TIMING_ROWS_INVALID"
            )
            timings.add(key)
        elif event["kind"] == "RESOURCE":
            resource_count += 1
            mutations[body["cause"]] += 1
            if body["cause"] == "PERIODIC":
                c.require(prior is not None)
                gap(prior, body["observed_mono_ns"], event["seq"])
                prior = body["observed_mono_ns"]
                periodic_count += 1
    c.require(
        segments == 1
        and resource_count
        and periodic_count
        and tail is not None
        and tail["kind"] == "RESOURCE"
        and tail["body"]["cause"] == "PERIODIC"
        and mutations["STATE_CHANGE"] >= segments
        and mutations["START_RESERVE"] == mutations["QUEUE_REMOVE"] == starts
        and mutations["CONNECTION_RELEASE"] == networks
        and mutations["RESERVATION_RELEASE"] == finals
        and mutations["QUEUE_ADD"] >= starts
        and len(timings) == finals == networks,
        "REPLAY_HARD_RESOURCE_ROWS_INVALID",
    )
    return {
        "periodic_count": periodic_count,
        "schedule_gap_count": gap_count,
        "maximum_gap_ns": maximum_gap,
        "first_gaps": gaps,
        "gap_rows_truncated": max(0, gap_count - len(gaps)),
        "hard_rows_and_timing_validated": True,
        "final_observed_to_header_ns": tail["mono_ns"] - prior,
    }


def verify_closed(root, item, start, *, validation_sha256, check, expected_payload):
    """Fresh original checks, including incomplete reports; no eligibility waiver.

    At most64 work/receipt identifiers and32 comparison rows are materialized.
    Event/inventory traversals stream. Actual completed opening remains separate.
    """
    with io.cooperative_io(check), FreshReads(root, check=check) as view:
        adapter = runtime.validation_for(validation_sha256)
        profile, plan = item["profile"], item["plan"]
        controls = matrix.adapters(plan)
        start_raw = io.read(root / "campaign_start.json")
        snap_raw, campaign_raw = (
            io.read(root / "snapshot.json"),
            io.read(root / "campaign_report.json"),
        )
        snapshot, campaign = (
            o.parse(snap_raw, o.SNAPSHOT),
            o.parse(campaign_raw, o.REPORT),
        )
        block = io.metadata(io.read(root / "block_report.json"))
        o.validate_type(block, "BlockReport")
        c.require(
            start_raw == c.canonical(start)
            and start["profile_sha256"] == o.digest(profile)
            and start["plan_sha256"] == o.digest(plan)
        )
        c.require(
            io.read(root / "_SEGMENT_SEALED", limit=0) == b""
            and io.metadata(io.read(root / "_WRITER_RELEASED.json"))
            == {
                "snapshot_sha256": o.digest(snapshot),
                "writer_release_evidence_sha256": snapshot[
                    "writer_release_evidence_sha256"
                ],
            }
        )

        def works():
            return runtime.plan_work(root, plan)

        o.verify_work_manifest(works, plan)
        index = WorkIndex(
            works,
            lambda key: runtime.read_object(root / "work" / f"{key:020d}.json"),
            plan,
        )
        rows = {}
        for row in works():
            c.require(len(rows) < 64 and row["work_id"] not in rows)
            rows[row["work_id"]] = row
        c.require(list(rows.values()) == item["work"])

        def events():
            return journal.read_events(root, o.digest(start))

        state = recovery.replay(events())
        c.require(state["closed"] and not state["unfinished"])
        recovery.snapshot_evidence(root, snapshot, state, o.digest(block), check=check)
        projection = journal.MeasurementPrefix.from_closed(
            root, o.digest(start), block["input_last_event_seq"], check=check
        )
        finals, stops = {}, []
        for event in events():
            check()
            if event["kind"] == "ATTEMPT_FINALIZED":
                body = event["body"]
                c.require(
                    body["work_id"] in rows
                    and body["work_id"] not in finals
                    and body["attempt"] == 1
                )
                finals[body["work_id"]] = body
            if event["kind"] == "STOP":
                c.require(len(stops) < 4)
                stops.append(event["body"])

        def receipt(work, final):
            check()
            name = audit.name_for(work["work_id"], final["attempt"])
            path = root / "attempts" / name
            if work["kind"] == "SERVICE_CONTROL":
                recipe = next(
                    x
                    for x in plan["control_recipes"]
                    if x["recipe_id"] == work["recipe_id"]
                )
                control = controls[work["recipe_id"]]
                begin = io.metadata(io.read(path / "begin.json"))
                c.require(
                    io.metadata(io.read(path / "recipe.json")) == recipe
                    and begin["campaign_start_sha256"] == o.digest(start)
                    and begin["profile_sha256"] == o.digest(profile)
                    and begin["plan_sha256"] == o.digest(plan)
                    and begin["work_id"] == work["work_id"]
                    and begin["attempt"] == 1
                    and begin["request_target_sha256"]
                    == c.sha(control.target(recipe)).hex()
                    and c.sha(io.read(path / "inventory.json")).hex()
                    == final["receipt_inventory_sha256"]
                )
                terminal = capture.reopen_control(path, control, key=None)
                frame = path / "raw.zst"
            else:
                c.require(
                    c.sha(io.read(path / (name + "_receipt.json"))).hex()
                    == final["receipt_inventory_sha256"]
                )
                terminal = audit.reopen(
                    path,
                    name,
                    validator=adapter.validator(work, path),
                    context=capture.DataContext(adapter),
                )
                frame = path / (name + ".zst")
            raw = response.decompress(
                io.read(frame),
                length=terminal["application_payload_bytes"],
                expected_hash=bytes.fromhex(terminal["response_sha256"]),
            )
            c.require(
                raw == expected_payload(work), "REPLAY_PAYLOAD_ASSOCIATION_INVALID"
            )
            return terminal

        ledgers = bounded_rows(
            journal.read_array(root / "work_ledger.json", check=check),
            64,
            validate=lambda row: o.validate_type(row, "WorkLedgerRow"),
        )
        c.require(len(ledgers) == len(rows))
        for actual, retained in zip_longest(
            recovery.work_ledger(works, events, receipt, batch_size=128), ledgers
        ):
            c.require(actual is not None and actual == retained)
        remaining = bounded_rows(
            journal.read_array(root / "remaining_work_ledger.json", check=check),
            64,
            validate=lambda row: o.validate_type(row, "WorkLedgerRow"),
        )
        c.require(
            remaining
            == [
                x
                for x in ledgers
                if x["state"] in ("UNBEGUN", "RETRY_DUE", "UNUSED_RESERVED_CONTROL")
            ]
        )
        retained_comparisons = bounded_rows(
            journal.read_array(root / "repeat_comparison.json", check=check),
            32,
            validate=comparison_row,
        )
        comparisons = []
        for first, second in index.pairs(1):
            shapes = []
            for work in (first, second):
                final = finals.get(work["work_id"])
                if final is None or final["outcome"]["value"] not in c.SUCCESS:
                    shapes.append(None)
                    continue
                terminal = receipt(work, final)
                c.require(terminal["outcome"] in c.SUCCESS)
                shapes.append(
                    validation.shapes(
                        expected_payload(work), work, version=adapter.VERSION
                    )
                )
            comparisons.append(
                {
                    "first_work_id": first["work_id"],
                    "next_work_id": second["work_id"],
                    "equal": shapes[0] is not None and shapes[0] == shapes[1],
                }
            )
        c.require(retained_comparisons == comparisons)
        recomputed = reporting.block_report(
            plan,
            profile,
            1,
            events=lambda: (
                e
                for e in projection.events()
                if e["seq"] <= block["input_last_event_seq"]
            ),
            works=works,
            verified_receipt=receipt,
            repeat_evidence=lambda: (
                c.sha(io.read(root / "repeat_comparison.json")).hex(),
                all(x["equal"] for x in comparisons),
            ),
            monitoring_closed=lambda: True,
            work_index=index,
        )
        c.require(recomputed == block)
        closed = bounded_rows((e for e in events() if e["kind"] == "BLOCK_CLOSED"), 1)
        c.require(
            len(closed) == 1 and closed[0]["body"]["report_sha256"] == o.digest(block)
        )
        expected_campaign = reporting.campaign_report(
            start,
            event_inventory_sha256=snapshot["event_inventory_sha256"],
            attempt_inventory_sha256=snapshot["attempt_inventory_sha256"],
            snapshots=[o.digest(snapshot)],
            blocks=[block],
            disposition=snapshot["disposition"],
            scientific_identity_verified=False,
            reconciliation_reasons=[]
            if snapshot["disposition"] == "COMPLETED"
            else ["INCOMPLETE_WORK"],
            plan=plan,
        )
        c.require(campaign == expected_campaign)
        c.require(
            journal.tree_bytes(
                root,
                frozenset(
                    {
                        "snapshot.json",
                        "_SEGMENT_SEALED",
                        "campaign_report.json",
                        "_WRITER_RELEASED.json",
                    }
                ),
                check=check,
            )
            == snapshot["controller"]["stored_bytes"]
        )
        projection.verify_original()
        o.verify_work_manifest(works, plan)
        c.require(
            io.read(root / "snapshot.json") == snap_raw
            and io.read(root / "campaign_report.json") == campaign_raw
            and io.read(root / "campaign_start.json") == start_raw
        )
        sampling = measurement(
            lambda: (
                e
                for e in projection.events()
                if e["seq"] <= block["input_last_event_seq"]
            ),
            maximum_events=plan["budgets"]["event_count"],
            period_ns=profile["resource_sample_period_ms"] * 10**6,
        )
        c.require(
            block["resource_sampling_complete"]
            == (sampling["schedule_gap_count"] == 0),
            "REPLAY_OTHER_MEASUREMENT_FAILURE",
        )
        return {
            "block": block,
            "campaign": campaign,
            "ledger": ledgers,
            "finals": finals,
            "state": state,
            "snapshot": snapshot,
            "comparisons": comparisons,
            "control_pairs": matrix.verify_controls(root, plan) if controls else [],
            "source_binding": binding(view),
            "stops": stops,
            "sampling": sampling,
        }


def assess(verified, *, negative, attempts, item, selection):
    b, campaign, ledger = verified["block"], verified["campaign"], verified["ledger"]
    counts = {k: v["value"] for k, v in b["counts"].items()}
    c.require(
        all(v is not None for v in counts.values())
        and b["receipts_complete"]
        and b["monitoring_complete"],
        "REPLAY_NON_SAMPLING_FAILURE",
    )
    c.require(
        all(
            counts[k] == 0
            for k in (
                "unknown_delivery",
                "durable_retryable",
                "retry_attempt_starts",
                "cooldown_events",
                "downshift_events",
                "breakers",
            )
        ),
        "REPLAY_UNEXPECTED_TRANSPORT_FAILURE",
    )
    c.require(counts["attempt_starts"] == attempts)
    for stat_name, p95, p99 in (
        ("transport_all", "http_p95_ms", "http_p99_ms"),
        *(
            ([("full_slot_data", "slot_p95_ms", "slot_p99_ms")])
            if item["plan"]["budgets"]["data_observations"]
            else []
        ),
    ):
        value = b["latencies"][stat_name]
        c.require(
            value["p95_ms"] is not None
            and value["p99_ms"] is not None
            and value["p95_ms"] <= selection[p95]
            and value["p99_ms"] <= selection[p99],
            "REPLAY_LATENCY_GATE_FAILED",
        )
    c.require(
        b["peaks"]["writer_wait_ms"] is not None
        and b["peaks"]["writer_wait_ms"] <= selection["max_writer_wait_ms"],
        "REPLAY_WRITER_GATE_FAILED",
    )
    if negative:
        c.require(
            attempts in (2, 3)
            and len(ledger) == 64
            and counts["durable_terminal_failure"] == 1
            and counts["durable_valid_data"] == attempts - 1
            and counts["http_200"] == attempts
            and verified["snapshot"]["disposition"] == "STOPPED"
            and not campaign["report_complete"],
            "REPLAY_NEGATIVE_MISMATCH",
        )
        for row in ledger:
            wid = row["work_id"]
            expected = (
                "TERMINAL"
                if wid == 2
                else "DURABLE_SUCCESS"
                if wid == 1 or (wid == 3 and attempts == 3)
                else "UNBEGUN"
            )
            c.require(
                row["state"] == expected
                and row["charged_ordinals"] == ([] if expected == "UNBEGUN" else [1]),
                "REPLAY_NEGATIVE_LEDGER_MISMATCH",
            )
        c.require(verified["finals"][2]["outcome"]["value"] == "CONTRACT_FAILURE")
        c.require(
            verified["finals"][2]["reason"] == "RESPONSE_CONTRACT_INVALID"
            and verified["state"]["breaker_reason"] == "TERMINAL_FAILURE"
            and verified["stops"]
            == [
                {
                    "why": "TERMINAL",
                    "primary_reason": "TERMINAL_FAILURE",
                    "trigger_event_seq": None,
                }
            ],
            "REPLAY_NEGATIVE_STOP_MISMATCH",
        )
        verdict = (
            "EXPECTED_NEGATIVE_PASS"
            if b["resource_sampling_complete"]
            else "NEGATIVE_SAMPLING_INCOMPLETE"
        )
    else:
        expected_reasons = ["EXPLORATORY_NO_QUALIFICATION"] + (
            [] if b["resource_sampling_complete"] else ["INSUFFICIENT_MEASUREMENT"]
        )
        c.require(
            verified["snapshot"]["disposition"] == "COMPLETED"
            and verified["state"]["breaker_reason"] is None
            and all(x["state"] == "DURABLE_SUCCESS" for x in ledger)
            and counts["durable_terminal_failure"] == counts["unprocessed_data"] == 0
            and attempts == len(ledger)
            and not verified["stops"]
            and b["reasons"] == expected_reasons
            and counts["durable_valid_data"]
            == item["plan"]["budgets"]["data_observations"]
            and counts["control_attempt_starts"]
            == item["plan"]["budgets"]["required_control_observations"]
            and all(x["equal"] for x in verified["comparisons"]),
            "REPLAY_NON_SAMPLING_FAILURE",
        )
        c.require(
            campaign["report_complete"] == b["resource_sampling_complete"],
            "REPLAY_NON_SAMPLING_FAILURE",
        )
        verdict = "PASS" if b["resource_sampling_complete"] else "SAMPLING_INCOMPLETE"
    return {
        "verdict": verdict,
        "expected_opener_rejection": negative or not b["resource_sampling_complete"],
        "unexpected_failure": None
        if verdict in ("PASS", "EXPECTED_NEGATIVE_PASS")
        else {"family": "SAMPLING_INCOMPLETE", "code": None, "errno": None},
    }


def expected_rejection(error, *, negative):
    """Whitelist the real eligibility gate, not a generic operations error.

    Inspect only code identity and a fixed source offset. Never read or retain
    traceback locals/messages/paths. A changed opener body fails closed until
    this diagnostic binding is reviewed. Exact source bytes are pinned in input.
    """
    if not isinstance(error, c.Stage12Error) or error.args != (
        "S12_PUBLIC_OPERATIONS_INVALID",
    ):
        return False
    code = runtime._reopen_completed.__code__
    offset = 71 if negative else 218
    node, depth = error.__traceback__, 0
    while node is not None and depth < 32:
        if node.tb_frame.f_code is code:
            return node.tb_lineno == code.co_firstlineno + offset
        depth += 1
        node = node.tb_next
    return False


def conclude(
    *,
    row,
    safety,
    verify,
    opener,
    revalidate,
    checkpoint,
    persist,
    classify,
    on_failure=lambda value: None,
    run_error=None,
):
    """Persist pre-opener evidence even when the real opener must reject it."""
    result = dict(
        row,
        verdict="UNSAFE",
        safe_to_continue=False,
        originals_validated=False,
        actual_opener_rejected=None,
        unexpected_failure=None,
        secondary_failure=None,
    )
    if run_error is not None:
        result["unexpected_failure"] = classify(run_error)
        on_failure(result["unexpected_failure"])
    try:
        c.require(run_error is None, "REPLAY_RUN_DID_NOT_RETURN")
        safety()
        facts = verify()
        result.update(facts)
        result["originals_validated"] = True
    except BaseException as error:
        if result["unexpected_failure"] is None:
            result["unexpected_failure"] = classify(error)
        else:
            result["secondary_failure"] = classify(error)
    if result["unexpected_failure"] is not None:
        on_failure(result["unexpected_failure"])
    try:
        result["supplementary_timing"] = checkpoint()
    except BaseException as error:
        result["secondary_failure"] = classify(error)
        result["unexpected_failure"] = result["unexpected_failure"] or {
            "family": "SUPPLEMENTARY_INCOMPLETE",
            "code": None,
            "errno": None,
        }
        result["verdict"] = "UNSAFE"
        on_failure(result["unexpected_failure"])
    persist(
        "RESULT",
        dict(
            result,
            completed_opener_state="NOT_INVOKED",
            candidate_verdict=result["verdict"],
            verdict="UNSAFE" if result["verdict"] == "UNSAFE" else "PENDING_OPENER",
        ),
    )
    if result["originals_validated"] and result["verdict"] != "UNSAFE":
        try:
            opened = opener()
            c.require(
                not result["expected_opener_rejection"],
                "REPLAY_OPENER_ACCEPTED_INCOMPLETE",
            )
            c.require(opened is True, "REPLAY_OPENER_RESULT_INVALID")
            result["actual_opener_rejected"] = False
            revalidate()
            safety()
            result["safe_to_continue"] = True
        except BaseException as error:
            if result["expected_opener_rejection"] and expected_rejection(
                error, negative=row["expected"] != "COMPLETE"
            ):
                result["actual_opener_rejected"] = True
                try:
                    revalidate()
                    safety()
                    result["safe_to_continue"] = True
                except BaseException as unsafe:
                    result["secondary_failure"] = classify(unsafe)
                    result["unexpected_failure"] = result[
                        "unexpected_failure"
                    ] or classify(unsafe)
            else:
                result["secondary_failure"] = classify(error)
            if not result["safe_to_continue"]:
                result["unexpected_failure"] = result["unexpected_failure"] or classify(
                    error
                )
                result["verdict"] = "UNSAFE"
                on_failure(result["unexpected_failure"])
    persist("OUTCOME", result)
    return result

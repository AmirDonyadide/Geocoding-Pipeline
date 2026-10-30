"""Deterministic O-r2 measurements; no rates inferred from synthetic targets."""

from __future__ import annotations

import hashlib
from itertools import islice

from collections.abc import Callable, Iterable, Iterator
from typing import Any

from . import s12_probe as probe
from . import s12_public_operations as o
from . import s12_retrieval_contract as c


_TIMING_JOIN_WORKS = 8  # Fixed engineering bound, unrelated to live rates or C/T/N.


def count(value: int | None, lower: int = 0) -> dict[str, int | None]:
    result = {"value": value, "confirmed_min": lower if value is None else value}
    o.validate_type(result, "Count")
    return result


def ratio(
    numerator: int | None, denominator: int | None, *, per_second: bool = False
) -> dict[str, int] | None:
    if numerator is None or denominator in (None, 0):
        return None
    result = {
        "num": o.checked(numerator * (10**9 if per_second else 1)),
        "den": o.uint(denominator, True),
    }
    return result


def exact_stats(
    values: Callable[[], Iterable[tuple[str, int]]], names: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    """Search all exact nearest ranks together, with constant-size state.

    Each round reopens the validated source. A transcript digest also rejects a
    source that changes between rounds; no event/value cache survives a scan.
    At most three search intervals per metric and uint64-bit rounds are needed.
    """

    def scan(middles):
        counts = dict.fromkeys(names, 0)
        maxima = dict.fromkeys(names, 0)
        below = {name: dict.fromkeys(middles.get(name, ()), 0) for name in names}
        fingerprint = hashlib.sha256()
        for name, value in values():
            o.require(name in counts)
            o.uint(value)
            fingerprint.update(bytes([names.index(name)]))
            fingerprint.update(value.to_bytes(8, "big"))
            counts[name] = o.checked(counts[name] + 1)
            maxima[name] = max(maxima[name], value)
            for middle in below[name]:
                below[name][middle] += value <= middle
        return counts, maxima, fingerprint.digest(), below

    counts, maxima, fingerprint, _ = scan({})
    bounds = {name: {q: [0, maxima[name]] for q in (50, 95, 99)} for name in names}
    while True:
        middles = {
            name: {(lo + hi) // 2 for lo, hi in bounds[name].values() if lo < hi}
            for name in names
        }
        if not any(middles.values()):
            break
        n, maximum, digest, below = scan(middles)
        o.require((n, maximum, digest) == (counts, maxima, fingerprint))
        for name in names:
            for q, (lo, hi) in bounds[name].items():
                if lo == hi:
                    continue
                middle = (lo + hi) // 2
                rank = (q * counts[name] + 99) // 100
                bounds[name][q] = (
                    [lo, middle] if below[name][middle] >= rank else [middle + 1, hi]
                )
    return {
        name: {
            "n": counts[name],
            **{
                f"p{q}_ms": bounds[name][q][0] if counts[name] else None
                for q in (50, 95, 99)
            },
            "max_ms": maxima[name] if counts[name] else None,
        }
        for name in names
    }


def stat(values: Callable[[], Iterable[int]]) -> dict[str, Any]:
    return exact_stats(lambda: (("value", v) for v in values()), ("value",))["value"]


def block_events(
    events: Callable[[], Iterable[dict[str, Any]]], block_id: int
) -> Iterator[dict[str, Any]]:
    current = None
    for event in events():
        if event["kind"] == "SEGMENT_OPEN":
            current = event["body"]["block_id"]
        if current == block_id:
            yield event


def block_report(
    plan: dict[str, Any],
    profile: dict[str, Any],
    block_id: int,
    *,
    events: Callable[[], Iterable[dict[str, Any]]],
    works: Callable[[], Iterable[dict[str, Any]]],
    verified_receipt: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    repeat_evidence: Callable[[], tuple[str, bool]],
    monitoring_closed: Callable[[], bool],
) -> dict[str, Any]:
    """Read source evidence, never a mutable aggregate cache or trimmed window."""
    o.validate_plan(plan, profile)
    block = plan["blocks"][block_id - 1]

    prefix_hash = None
    last_seq = 0

    def source():
        # Every traversal still uses the caller's validated reader. Bind every
        # pass to the SAME complete event prefix, including other blocks, with
        # only a hash/ordinal retained between scans.
        nonlocal prefix_hash, last_seq
        fingerprint = hashlib.sha256(b"[")
        current, final_seq = None, 0
        for i, event in enumerate(events()):
            if i:
                fingerprint.update(b",")
            fingerprint.update(
                c.canonical(
                    {
                        "path": f"events/{event['seq']:020d}.json",
                        "sha256": o.digest(event),
                    }
                )[:-1]
            )
            final_seq = event["seq"]
            if event["kind"] == "SEGMENT_OPEN":
                current = event["body"]["block_id"]
            if current == block_id:
                yield event
        fingerprint.update(b"]\n")
        digest = fingerprint.hexdigest()
        if prefix_hash is None:
            prefix_hash, last_seq = digest, final_seq
        else:
            o.require((digest, final_seq) == (prefix_hash, last_seq))

    counts = dict.fromkeys(o.COUNT_KEYS, 0)
    counts["planned_data"] = block["budget"]["data_observations"]
    counts["required_controls"] = block["budget"]["required_control_observations"]
    counts["reserved_controls"] = block["budget"]["reserved_control_observations"]
    reasons: set[str] = set()
    starts = ends = None
    timing_count = resource_count = segments = finals = 0
    mutations: dict[str, int] = {}
    network_done = 0
    receipts_ok = True
    unknown_counts: set[str] = set()
    unknown_cells: set[tuple[str, int]] = set()
    cells: dict[tuple[str, int], list[int]] = {}
    fixtures = {x["fixture_id"]: x for x in probe.fixtures()}
    peaks = {k: None for k in o.TYPES["Peaks"]}
    sample_period = profile["resource_sample_period_ms"] * 1_000_000
    last_periodic_ns = None
    schedule_ok = True
    periodic_seen = False

    def work_for(work_id: int) -> dict[str, Any]:
        row = next((r for r in works() if r["work_id"] == work_id), None)
        o.require(row is not None)
        return row

    tail = None
    for event in source():
        tail = event
        kind, b = event["kind"], event["body"]
        if kind == "SEGMENT_OPEN":
            segments += 1
            if last_periodic_ns is not None and not periodic_seen:
                schedule_ok = False
            last_periodic_ns, periodic_seen = event["mono_ns"], False
        elif kind == "SEGMENT_CLOSE":
            schedule_ok = (
                schedule_ok
                and periodic_seen
                and (0 <= event["mono_ns"] - last_periodic_ns <= sample_period)
            )
        elif kind == "BEGIN_DURABLE":
            counts["begins_charged"] += 1
        elif kind == "ATTEMPT_STARTED":
            counts["attempt_starts"] += 1
            starts = (
                b["started_mono_ns"]
                if starts is None
                else min(starts, b["started_mono_ns"])
            )
            row = work_for(b["work_id"])
            key = (
                "control_attempt_starts"
                if row["kind"] == "SERVICE_CONTROL"
                else "first_attempt_starts"
                if b["attempt"] == 1
                else "retry_attempt_starts"
            )
            counts[key] += 1
        elif kind == "EMIT_COMMITTED":
            counts["emission_commits"] += 1
        elif kind == "EMISSION":
            # WRITE_FAILED is an actual write entry, not a successful response.
            counts["emissions_entered"] += b["result"] != "UNKNOWN"
        elif kind == "ATTEMPT_FINALIZED":
            finals += 1
        elif kind == "AUDIT_TIMING":
            o.require(work_for(b["work_id"])["block_id"] == block_id)
            timing_count += 1
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
            o.require(times == sorted(times))
        elif kind == "RESOURCE":
            resource_count += 1
            mutations[b["cause"]] = mutations.get(b["cause"], 0) + 1
            for target, key in (
                ("connection_slots", "connection_slots"),
                ("admitted", "admitted_operations"),
                ("pending_count", "pending_count"),
                ("pending_bytes", "pending_bytes"),
                ("reserved_bytes", "reserved_bytes"),
            ):
                peaks[target] = max(peaks[target] or 0, b[key])
            if b["free_allocated_disk_bytes"] is not None:
                peaks["min_free_allocated_disk_bytes"] = (
                    b["free_allocated_disk_bytes"]
                    if peaks["min_free_allocated_disk_bytes"] is None
                    else min(
                        peaks["min_free_allocated_disk_bytes"],
                        b["free_allocated_disk_bytes"],
                    )
                )
            if b["cause"] == "PERIODIC":
                ends = b["observed_mono_ns"]
                schedule_ok = (
                    schedule_ok
                    and last_periodic_ns is not None
                    and (0 <= ends - last_periodic_ns <= sample_period)
                )
                last_periodic_ns, periodic_seen = ends, True
            if b["cause"] in ("PERIODIC", "START_RESERVE"):
                schedule_ok = schedule_ok and b["free_allocated_disk_bytes"] is not None
        elif kind == "NETWORK_DONE":
            o.require(work_for(b["work_id"])["block_id"] == block_id)
            network_done += 1
        elif kind == "COOLDOWN":
            counts["cooldown_events"] += 1
            reasons.add("OVERLOAD_OR_COOLDOWN")
        elif kind == "DOWNSHIFT":
            counts["downshift_events"] += 1
            reasons.add("RATE_CHANGED")
        elif kind == "STOP":
            counts["breakers"] += b["why"] == "BREAKER"
            reasons.add("STOPPED")
    timing_unique = True
    # Per-work checks retain at most five attempt ordinals, including unused controls.
    for row in works():
        if row["block_id"] != block_id:
            continue
        begun, finished = [], []
        timing_ordinals = {}
        outcomes = []
        if row["kind"] == "DATA":
            cell = (
                fixtures[row["fixture_id"]]["core"]["search_mode"],
                row["result_limit"],
            )
            cells.setdefault(cell, [0, 0])[0] += 1
        for event in source():
            b = event["body"]
            if b.get("work_id") != row["work_id"]:
                continue
            if event["kind"] == "AUDIT_TIMING":
                o.require(1 <= b["attempt"] <= 5)
                timing_ordinals[b["attempt"]] = timing_ordinals.get(b["attempt"], 0) + 1
            elif event["kind"] == "BEGIN_DURABLE":
                o.require(len(begun) < 5)
                begun.append(b["attempt"])
            elif event["kind"] == "ATTEMPT_FINALIZED":
                o.require(len(finished) < 5)
                finished.append(b["attempt"])
                try:
                    terminal = verified_receipt(row, b)
                    o.require(
                        b["outcome"]
                        == {"kind": row["kind"], "value": terminal["outcome"]}
                    )
                except (c.Stage12Error, OSError):
                    receipts_ok = False
                    outcomes.append(None)
                    unknown_counts.update(
                        (
                            "http_completions",
                            "http_200",
                            "durable_retryable",
                            "durable_terminal_failure",
                            "unknown_delivery",
                        )
                    )
                    if row["kind"] == "DATA":
                        unknown_counts.update(
                            ("durable_valid_data", "durable_valid_zero")
                        )
                        unknown_cells.add(cell)
                    continue
                outcome = terminal["outcome"]
                outcomes.append(outcome)
                counts["http_completions"] += b["status"] is not None
                counts["http_200"] += b["status"] == 200
                counts["durable_retryable"] += outcome == "TECHNICAL_FAILURE_RETRYABLE"
                counts["durable_terminal_failure"] += (
                    outcome in o.FAILURES and outcome != "TECHNICAL_FAILURE_RETRYABLE"
                )
                if row["kind"] == "DATA" and outcome in c.SUCCESS:
                    counts["durable_valid_data"] += 1
                    counts["durable_valid_zero"] += outcome == c.SUCCESS[1]
                    cells[cell][1] += 1
        o.require(
            begun == list(range(1, len(begun) + 1))
            and len(begun) <= 5
            and len(finished) == len(set(finished))
        )
        timing_unique = timing_unique and all(
            timing_ordinals.get(a, 0) == 1 for a in finished
        )
        counts["unknown_delivery"] += len(set(begun) - set(finished))
        # A finalized event whose receipt is unavailable cannot establish that
        # work was processed. Use the SAME verified outcomes as the counts above.
        last_known = not outcomes or outcomes[-1] is not None
        success = bool(outcomes) and outcomes[-1] in (*c.SUCCESS, "CONTROL_SUCCESS")
        o.require(sum(x in (*c.SUCCESS, "CONTROL_SUCCESS") for x in outcomes) <= 1)
        if row["kind"] == "DATA":
            if not last_known:
                unknown_counts.add("unprocessed_data")
            else:
                counts["unprocessed_data"] += not success
        elif row["work_id"] in block["reserved_control_ids"] and not begun:
            counts["unused_reserved_controls"] += 1
        elif not success:
            reasons.add("INCOMPLETE_WORK")

    def single_values(row) -> Iterator[tuple[str, int]]:
        # Existing bounded one-work path preserves all malformed duplicate values.
        started, timings = {}, []
        timing_overflow = False
        for event in source():
            body = event["body"]
            if body.get("work_id") != row["work_id"]:
                continue
            kind = event["kind"]
            if kind in ("ATTEMPT_STARTED", "AUDIT_TIMING", "NETWORK_DONE"):
                o.require(1 <= body["attempt"] <= 5)
            if kind == "ATTEMPT_STARTED":
                started.setdefault(body["attempt"], body["started_mono_ns"])
            elif kind == "AUDIT_TIMING":
                if len(timings) < 5:
                    timings.append(body)
                else:
                    timing_overflow = True
            elif kind == "NETWORK_DONE":
                yield "transport_all", body["elapsed_ms"]
                if row["kind"] == "DATA":
                    yield "transport_data", body["elapsed_ms"]
        # Malformed duplicate timing records may exceed five even though
        # ordinals cannot. Preserve their known n / INCOMPLETE statistics
        # without keeping an unbounded list: only this case needs a rescan.
        selected_timings = (
            (
                e["body"]
                for e in source()
                if e["kind"] == "AUDIT_TIMING"
                and e["body"]["work_id"] == row["work_id"]
            )
            if timing_overflow
            else iter(timings)
        )
        for timing in selected_timings:
            yield (
                "writer_wait",
                (timing["receipt_reopened_ns"] - timing["writer_enqueued_ns"] + 999_999)
                // 1_000_000,
            )
            if row["kind"] == "DATA":
                o.require(timing["attempt"] in started)
                yield (
                    "full_slot_data",
                    (
                        timing["reservation_released_ns"]
                        - started[timing["attempt"]]
                        + 999_999
                    )
                    // 1_000_000,
                )

    def values() -> Iterator[tuple[str, int]]:
        # Fixed eight-work join, rebuilt on EVERY percentile scan. No event or
        # campaign-sized cache survives; at most 8 * 5 starts/timings/transports
        # are retained. Every batch consumes the same fully validated prefix.
        selected = (row for row in works() if row["block_id"] == block_id)
        while batch := list(islice(selected, _TIMING_JOIN_WORKS)):
            ids = {row["work_id"] for row in batch}
            o.require(len(ids) == len(batch))
            starts = {key: {} for key in ids}
            timings = {key: [] for key in ids}
            transports = {key: [] for key in ids}
            overflow = set()
            for event in source():
                body = event["body"]
                key = body.get("work_id")
                if key not in ids:
                    continue
                kind = event["kind"]
                if kind in ("ATTEMPT_STARTED", "AUDIT_TIMING", "NETWORK_DONE"):
                    o.require(1 <= body["attempt"] <= 5)
                if kind == "ATTEMPT_STARTED":
                    starts[key].setdefault(body["attempt"], body["started_mono_ns"])
                elif kind in ("AUDIT_TIMING", "NETWORK_DONE"):
                    target = timings[key] if kind == "AUDIT_TIMING" else transports[key]
                    if len(target) < 5:
                        target.append(
                            body if kind == "AUDIT_TIMING" else body["elapsed_ms"]
                        )
                    else:
                        overflow.add(key)
            for row in batch:
                key = row["work_id"]
                if key in overflow:
                    # Never truncate malformed duplicates into a complete report.
                    yield from single_values(row)
                    continue
                for elapsed in transports[key]:
                    yield "transport_all", elapsed
                    if row["kind"] == "DATA":
                        yield "transport_data", elapsed
                for timing in timings[key]:
                    yield (
                        "writer_wait",
                        (
                            timing["receipt_reopened_ns"]
                            - timing["writer_enqueued_ns"]
                            + 999_999
                        )
                        // 1_000_000,
                    )
                    if row["kind"] == "DATA":
                        o.require(timing["attempt"] in starts[key])
                        yield (
                            "full_slot_data",
                            (
                                timing["reservation_released_ns"]
                                - starts[key][timing["attempt"]]
                                + 999_999
                            )
                            // 1_000_000,
                        )

    latencies = exact_stats(values, tuple(o.TYPES["Latencies"]))
    peaks["writer_wait_ms"] = latencies["writer_wait"]["max_ms"]
    timing_ok = timing_count == finals == network_done and timing_unique
    # Tail was observed during the initial full pass, and every subsequent
    # complete pass is bound to its exact prefix digest.
    mutations_ok = bool(
        tail
        and tail["kind"] == "RESOURCE"
        and tail["body"]["cause"] == "PERIODIC"
        and resource_count
        and mutations.get("STATE_CHANGE", 0) >= segments
        and mutations.get("START_RESERVE", 0)
        == mutations.get("QUEUE_REMOVE", 0)
        == counts["begins_charged"]
        and mutations.get("CONNECTION_RELEASE", 0) == network_done
        and mutations.get("RESERVATION_RELEASE", 0) == finals
        and mutations.get("QUEUE_ADD", 0) >= counts["begins_charged"]
    )
    resources_ok = mutations_ok and schedule_ok and periodic_seen
    if not mutations_ok:
        for key in (
            "connection_slots",
            "admitted",
            "pending_count",
            "pending_bytes",
            "reserved_bytes",
        ):
            peaks[key] = None
    if not timing_ok:
        peaks["writer_wait_ms"] = None
        for key in ("full_slot_data", "writer_wait"):
            for q in ("p50_ms", "p95_ms", "p99_ms", "max_ms"):
                latencies[key][q] = None
    duration = (
        0
        if starts is None and not counts["begins_charged"]
        else ends - starts
        if ends is not None and starts is not None and ends >= starts
        else None
    )
    if segments != 1:
        duration = None  # Monotonic values from different epochs are incomparable.
    rates = {
        "data_first_dispatch_per_s": ratio(
            counts["first_attempt_starts"], duration, per_second=True
        ),
        "all_attempts_per_s": ratio(
            counts["attempt_starts"], duration, per_second=True
        ),
        "http_completions_per_s": ratio(
            None
            if "http_completions" in unknown_counts
            else counts["http_completions"],
            duration,
            per_second=True,
        ),
        "durable_data_per_s": ratio(
            None
            if "durable_valid_data" in unknown_counts
            else counts["durable_valid_data"],
            duration,
            per_second=True,
        ),
        "retry_fraction": ratio(
            counts["retry_attempt_starts"],
            counts["first_attempt_starts"] + counts["retry_attempt_starts"],
        ),
    }
    if duration is None:
        rates = dict.fromkeys(rates)
    if counts["unknown_delivery"]:
        reasons.add("UNKNOWN_DELIVERY")
    if counts["unprocessed_data"]:
        reasons.add("INCOMPLETE_WORK")
    if counts["durable_terminal_failure"]:
        reasons.add("UNSAFE_RESPONSE")
    if not receipts_ok or not timing_ok:
        reasons.add("AUDIT_FAILED")
    if not resources_ok or segments != 1 or not duration:
        reasons.add("INSUFFICIENT_MEASUREMENT")
    monitor_ok = monitoring_closed()
    if not monitor_ok:
        reasons.add("MONITOR_FAILED")
    repeat_hash, repeated = repeat_evidence()
    o.validate_type(repeat_hash, "D")
    if not repeated:
        reasons.add("REPEAT_DISAGREEMENT")
    criteria = block["criteria"]
    if criteria is not None:
        checks = [
            duration is not None
            and criteria["min_duration_ms"] * 1_000_000
            <= duration
            <= criteria["max_duration_ms"] * 1_000_000,
            counts["durable_valid_data"] >= criteria["min_valid_data"],
        ]
        for key, bound in (
            ("all_attempts_per_s", "min_attempt_rate"),
            ("durable_data_per_s", "min_durable_data_rate"),
        ):
            checks.append(
                rates[key] is not None and o.rate_le(criteria[bound], rates[key])
            )
        checks.append(
            rates["retry_fraction"] is not None
            and o.rate_le(rates["retry_fraction"], criteria["max_retry_fraction"])
        )
        for metric, prefix in (("transport_data", "http"), ("full_slot_data", "slot")):
            for q in (95, 99):
                value = latencies[metric][f"p{q}_ms"]
                checks.append(
                    value is not None and value <= criteria[f"max_{prefix}_p{q}_ms"]
                )
        for key, bound in (
            ("pending_count", "max_pending_count"),
            ("pending_bytes", "max_pending_bytes"),
            ("reserved_bytes", "max_reserved_bytes"),
            ("writer_wait_ms", "max_writer_wait_ms"),
        ):
            checks.append(peaks[key] is not None and peaks[key] <= criteria[bound])
        checks.extend(
            cells.get((cell["mode"], cell["size"]), [0, 0])[1]
            >= criteria["min_per_cell"]
            for cell in criteria["required_cells"]
        )
        if not all(checks):
            reasons.add("THRESHOLD_FAILED")
    else:
        reasons.add("EXPLORATORY_NO_QUALIFICATION")
    incomplete = bool(
        reasons.intersection(
            {
                "AUDIT_FAILED",
                "UNKNOWN_DELIVERY",
                "INCOMPLETE_WORK",
                "INSUFFICIENT_MEASUREMENT",
                "MONITOR_FAILED",
            }
        )
    )
    status = (
        "INCOMPLETE"
        if incomplete
        else "EXPLORATORY_ONLY"
        if criteria is None
        else "FAIL"
        if reasons
        else "PASS"
    )
    o.require(last_seq and prefix_hash is not None)
    result = {
        "block_id": block_id,
        "criterion_sha256": o.digest(criteria) if criteria is not None else None,
        "input_event_prefix_sha256": prefix_hash,
        "input_last_event_seq": last_seq,
        "status": status,
        "reasons": sorted(reasons),
        "duration_ns": duration,
        "counts": {
            k: count(None if k in unknown_counts else v, v) for k, v in counts.items()
        },
        "rates": rates,
        "latencies": latencies,
        "peaks": peaks,
        "cells": [
            {
                "mode": k[0],
                "size": k[1],
                "planned": v[0],
                "durable_valid": count(None if k in unknown_cells else v[1], v[1]),
            }
            for k, v in sorted(cells.items())
        ],
        "repeat_comparison_sha256": repeat_hash,
        "monitoring_complete": monitor_ok,
        "receipts_complete": receipts_ok and not counts["unknown_delivery"],
        "resource_sampling_complete": resources_ok and timing_ok,
    }
    o.validate_type(result, "BlockReport")
    return result


def campaign_report(
    start: dict[str, Any],
    *,
    event_inventory_sha256: str,
    attempt_inventory_sha256: str,
    snapshots: list[str],
    blocks: list[dict[str, Any]],
    disposition: str,
    scientific_identity_verified: bool,
    reconciliation_reasons: list[str],
    plan: dict[str, Any],
) -> dict[str, Any]:
    totals = {}
    for key in o.COUNT_KEYS:
        known = all(b["counts"][key]["value"] is not None for b in blocks)
        lower = sum(b["counts"][key]["confirmed_min"] for b in blocks)
        totals[key] = count(lower if known else None, lower)
    for key, field in (
        ("planned_data", "data_observations"),
        ("required_controls", "required_control_observations"),
        ("reserved_controls", "reserved_control_observations"),
    ):
        totals[key] = count(plan["budgets"][field])
    represented = {b["block_id"] for b in blocks}
    o.require(len(represented) == len(blocks))
    unvisited = sum(
        b["budget"]["data_observations"]
        for b in plan["blocks"]
        if b["block_id"] not in represented
    )
    unprocessed = totals["unprocessed_data"]
    lower = unprocessed["confirmed_min"] + unvisited
    totals["unprocessed_data"] = count(
        None if unprocessed["value"] is None else lower, lower
    )
    complete = (
        bool(blocks)
        and all(
            b["status"] != "INCOMPLETE"
            and b["receipts_complete"]
            and b["resource_sampling_complete"]
            and b["monitoring_complete"]
            for b in blocks
        )
        and not reconciliation_reasons
    )
    result = {
        "schema_version": o.REPORT,
        "scope": o.SCOPE,
        "campaign_start_sha256": o.digest(start),
        "profile_sha256": start["profile_sha256"],
        "plan_sha256": start["plan_sha256"],
        "event_inventory_sha256": event_inventory_sha256,
        "attempt_inventory_sha256": attempt_inventory_sha256,
        "segment_snapshot_hashes": snapshots,
        "blocks": blocks,
        "campaign_counts": totals,
        "disposition": disposition,
        "reconciliation_reasons": sorted(set(reconciliation_reasons)),
        "scientific_identity_verified": scientific_identity_verified,
        "protected_readiness": "BLOCKED",
        "approval_status": "UNISSUED",
        "report_complete": complete,
    }
    o.validate(result, o.REPORT)
    return result


def incomplete_report(
    start: dict[str, Any],
    plan: dict[str, Any],
    *,
    event_inventory_sha256: str,
    attempt_inventory_sha256: str,
    begins_lower_bound: int,
) -> dict[str, Any]:
    """No fabricated snapshots, totals or block prefix when evidence is uncertain."""
    result = campaign_report(
        start,
        event_inventory_sha256=event_inventory_sha256,
        attempt_inventory_sha256=attempt_inventory_sha256,
        snapshots=[],
        blocks=[],
        disposition="RECOVERY_BLOCKED",
        scientific_identity_verified=False,
        reconciliation_reasons=["AUDIT_FAILED", "UNKNOWN_DELIVERY", "STOPPED"],
        plan=plan,
    )
    exact = {
        "planned_data",
        "required_controls",
        "reserved_controls",
        "administrative_operations",
    }
    for key in result["campaign_counts"]:
        if key not in exact:
            result["campaign_counts"][key] = count(
                None, begins_lower_bound if key == "begins_charged" else 0
            )
    o.validate(result, o.REPORT)
    return result

"""Controlled scientific diagnostics; exact comparisons, never candidate scores.

Rows are streamed to the phase's sole writer. Per-response state is bounded by
40 byte-capped features. Portable tables are derived in disk-backed storage and
suppressed as whole tables when any nonempty cell has fewer than20 sources.
"""

from __future__ import annotations
from collections import Counter
from . import s12_b2_contract as b
from . import s12_retrieval_contract as c
from . import s12_response as response


def channel_state(candidate, channel, country):
    from . import s09_reference_contract as s9

    value, source = candidate[channel["candidate_field"]], channel["source_value"]
    comparable = (
        type(value) is str
        and type(source) is str
        and bool(value)
        and bool(source)
        and channel["granularity"] == channel["candidate_granularity"]
        and channel["granularity"] not in ("UNKNOWN", "UNRESOLVED", "NOT_EVALUABLE", "")
        and channel["comparison_method"] != s9.NO_NORM
    )
    reference = channel["kind"] == "ACCEPTED_REFERENCE"
    if reference and not channel["positive_reference"]:
        comparable = False
    if not comparable:
        return "UNEVALUABLE"
    equal = s9.normalize(channel["comparison_method"], value, country) == s9.normalize(
        channel["comparison_method"], source, country
    )
    return (
        ("REFERENCE_COMPATIBLE" if reference else "SOURCE_COMPATIBLE")
        if equal
        else "SOURCE_DISAGREEMENT"
    )


def features_delta(left, right):
    """Exact structural additions/losses/multiplicity and independent ordering."""
    a, bv = Counter(left.feature_structures), Counter(right.feature_structures)
    return {
        "feature_additions": sum((bv - a).values()),
        "feature_losses": sum((a - bv).values()),
        "reordered": left.feature_structures != right.feature_structures and a == bv,
        "feature_sequences_equal": left.feature_structures == right.feature_structures,
    }


def rank_rows(projection, raw, context, grid):
    from . import s12_b2_calibration as cal

    parsed = response.Parser(raw).parse().value["features"]
    seen = set()
    keys = set()
    features = set()
    gids = set()
    coordinates = set()
    sources = set()
    layers = set()
    first = None
    prior_grid = set()
    grid_from = 0
    for rank, (candidate, feature) in enumerate(
        zip(projection.candidates, parsed, strict=True), 1
    ):
        tokens = cal.tokens(candidate, feature, context)
        gain = tokens - seen
        K = c.framed([candidate[k] for k in cal.K_FIELDS])
        structure = projection.feature_structures[rank - 1]
        compatible = [
            x for x in gain if x[1] not in ("POTENTIAL_UNRESOLVED", "OPAQUE_EXTENSION")
        ]
        if first is None and any(
            x[1] not in ("POTENTIAL_UNRESOLVED", "OPAQUE_EXTENSION") for x in tokens
        ):
            first = rank
        states = Counter(
            (
                ch["kind"],
                channel_state(candidate, ch, context["country"]),
                ch["dependence_class"],
            )
            for ch in context["channels"]
        )
        # Alias members are retained individually by the catalog; counts here are
        # descriptive channels, not independent votes or summed evidence strength.
        dependence = Counter(x[4] for x in compatible)
        gid = candidate["gid"]
        coord = c.framed([candidate["longitude"], candidate["latitude"]])
        yield {
            "diagnostic": "ADJACENT_RANK",
            "rank": rank,
            "new_compatible_tokens": len(compatible),
            "new_unresolved_tokens": sum(x[1] == "POTENTIAL_UNRESOLVED" for x in gain),
            "new_opaque_tokens": sum(x[1] == "OPAQUE_EXTENSION" for x in gain),
            "new_K": K not in keys,
            "duplicate_K": K in keys,
            "duplicate_full_feature": structure in features,
            "new_gid": gid is not None and gid not in gids,
            "missing_gid": gid is None,
            "new_coordinate": coord not in coordinates,
            "new_source": candidate["source"] not in sources,
            "new_layer": candidate["layer"] not in layers,
            "layer": candidate["layer"],
            "source": candidate["source"],
            "coarse": candidate["layer"] != "address",
            "first_compatible_rank": first,
            "compatible_dependence": dict(sorted(dependence.items())),
            "channel_states": [
                {"kind": k, "state": v, "dependence": d, "members": n}
                for (k, v, d), n in sorted(states.items())
            ],
        }
        seen.update(tokens)
        keys.add(K)
        features.add(structure)
        coordinates.add(coord)
        sources.add(candidate["source"])
        layers.add(candidate["layer"])
        if gid is not None:
            gids.add(gid)
        if rank in grid:
            delta = seen - prior_grid
            yield {
                "diagnostic": "GRID_TRANSITION",
                "from_rank": grid_from,
                "to_rank": rank,
                "new_compatible_tokens": sum(
                    x[1] not in ("POTENTIAL_UNRESOLVED", "OPAQUE_EXTENSION")
                    for x in delta
                ),
                "new_unresolved_tokens": sum(
                    x[1] == "POTENTIAL_UNRESOLVED" for x in delta
                ),
                "new_opaque_tokens": sum(x[1] == "OPAQUE_EXTENSION" for x in delta),
                "first_compatible_rank": first,
                "compatible_only_beyond_previous_rank": first is not None
                and first > grid_from,
            }
            prior_grid = set(seen)
            grid_from = rank
    for limit in sorted(n for n in grid if n > len(parsed)):
        delta = seen - prior_grid
        yield {
            "diagnostic": "GRID_TRANSITION",
            "from_rank": grid_from,
            "to_rank": limit,
            "new_compatible_tokens": sum(
                x[1] not in ("POTENTIAL_UNRESOLVED", "OPAQUE_EXTENSION") for x in delta
            ),
            "new_unresolved_tokens": sum(x[1] == "POTENTIAL_UNRESOLVED" for x in delta),
            "new_opaque_tokens": sum(x[1] == "OPAQUE_EXTENSION" for x in delta),
            "first_compatible_rank": first,
            "compatible_only_beyond_previous_rank": first is not None
            and first > grid_from,
        }
        prior_grid = set(seen)
        grid_from = limit


def attempt_summary(segment, start_hash):
    """Finite categories over the sealed attempt prefix, DATA/control separate.

    Full semantic receipt validation is the surrounding campaign reader's duty.
    Here every contributing receipt is independently hash/inventory/association
    checked on each calculation; unavailable evidence supplies no exact totals.
    No response bodies, targets, headers or free-form errors enter this summary.
    """
    from . import s12_b2_operations as o
    from . import s12_public_journal as j
    from . import s12_b2_inventory as metadata
    from . import s12_b2_recovery as recovery
    from . import s12_public_operational_audit as oa
    from . import s12_public_reporting as stats
    from . import s12_storage as io

    labels = (
        "NO_HTTP_RESPONSE",
        "HTTP_200",
        "OTHER_2XX",
        "HTTP_3XX",
        "HTTP_401_403",
        "HTTP_429",
        "OTHER_4XX",
        "HTTP_5XX",
        "OTHER_HTTP",
    )
    reasons = tuple(o.TYPES["Reason"]["enum"])
    result = {
        kind: {
            "charged_attempts": 0,
            "unverified_attempts": 0,
            "categories": {},
            "application_bytes_observed": 0,
            "unknown_application_attempts": 0,
            "received_body_bytes": 0,
            "retained_raw_bytes": 0,
            "retained_compressed_bytes": 0,
        }
        for kind in ("DATA", "SERVICE_CONTROL")
    }

    def bucket(status):
        return (
            "NO_HTTP_RESPONSE"
            if status is None
            else "HTTP_200"
            if status == 200
            else "OTHER_2XX"
            if 200 <= status < 300
            else "HTTP_3XX"
            if 300 <= status < 400
            else "HTTP_401_403"
            if status in (401, 403)
            else "HTTP_429"
            if status == 429
            else "OTHER_4XX"
            if 400 <= status < 500
            else "HTTP_5XX"
            if 500 <= status < 600
            else "OTHER_HTTP"
        )

    def locate(work, attempt):
        node = segment
        while node is not None:
            unit = node / "attempts" / f"{work:020d}_{attempt:02d}"
            if unit.exists():
                return unit
            node = j.predecessor_root(node)
        raise c.Stage12Error("B2_RECEIPT_MISSING")

    plan = b.parse(io.read(segment / "plan.json"), o.PLAN)
    start = b.parse(io.read(segment / "campaign_start.json"), o.START)
    b.require(b.digest(start) == start_hash, "B2_START_BINDING")
    for event in recovery.events(segment, start, plan):
        x = event["body"]
        if event["kind"] == "ATTEMPT_STARTED":
            # Kind is encoded by the corresponding finalized outcome; starts
            # without finals are charged below from the authoritative work rows.
            continue
        if event["kind"] != "ATTEMPT_FINALIZED":
            continue
        kind = x["outcome"]["kind"]
        row = result[kind]
        try:
            unit = locate(x["work_id"], x["attempt"])
            raw = io.read(unit / "receipt.json")
            b.require(
                b.sha(raw).hex() == x["receipt_inventory_sha256"], "B2_RECEIPT_CHANGED"
            )
            inventory = io.metadata(raw)["files"]
            io.verify_inventory(unit, inventory, extra={"receipt.json", "_SEALED"})
            b.require(io.read(unit / "_SEALED", limit=0) == b"", "B2_RECEIPT_UNSEALED")
            terminal = (
                b.parse(io.read(unit / "finish.json"), o.CONTROL_FINISH)
                if kind == "SERVICE_CONTROL"
                else b.parse(
                    io.read(unit / "validation.json"), "stage12_data_receipt_b2_v1"
                )
            )
            transport = io.metadata(io.read(unit / "transport.json"))
            oa.validate_transport(transport)
            begin = io.metadata(io.read(unit / "begin.json"))
            b.require(
                terminal["begin_sha256"] == b.digest(begin)
                and begin["attempt"] == x["attempt"]
                and terminal[
                    "transport_record_sha256"
                    if kind == "SERVICE_CONTROL"
                    else "transport_sha256"
                ]
                == b.digest(transport)
                and terminal["outcome"] == x["outcome"]["value"]
                and terminal["reason"] == x["reason"]
                and transport["status"] == x["status"]
                and transport["attempt"] == x["attempt"]
                and transport["call"] == x["work_id"],
                "B2_RECEIPT_ASSOCIATION",
            )
            reason = terminal["reason"]
            b.require(reason in reasons, "B2_FINITE_REASON")
            payload = transport["payload_bytes"]
            # payload_bytes is null for rejected/unavailable application bodies;
            # zero is only exact when the transport positively observed zero.
            payload_unknown = payload is None and transport["received_body_bytes"] > 0
            payload = payload or 0
            raw_entries = [v for v in inventory if v["path"] == "raw.zst"]
            retained = (
                terminal["application_payload_bytes"]
                if kind == "SERVICE_CONTROL"
                else terminal["response_bytes"]
            )
            b.require(
                (len(raw_entries) == 1 and type(retained) is int)
                or (not raw_entries and retained is None),
                "B2_RAW_ACCOUNTING",
            )
            io.verify_inventory(unit, inventory, extra={"receipt.json", "_SEALED"})
            b.require(io.read(unit / "receipt.json") == raw, "B2_RECEIPT_CHANGED")
        except (c.Stage12Error, OSError, KeyError, ValueError):
            row["unverified_attempts"] += 1
            continue
        key = (bucket(transport["status"]), reason)
        counts = row["categories"].setdefault(
            key, {"attempts": 0, "retries": 0, "final_failures": 0}
        )
        counts["attempts"] += 1
        counts["retries"] += x["attempt"] > 1
        counts["final_failures"] += (
            terminal["outcome"] not in (*c.SUCCESS, "CONTROL_SUCCESS")
            and x["retry_delay_ms"] is None
        )
        row["application_bytes_observed"] += payload
        row["unknown_application_attempts"] += payload_unknown
        row["received_body_bytes"] += transport["received_body_bytes"]
        row["retained_raw_bytes"] += retained or 0
        row["retained_compressed_bytes"] += sum(v["bytes"] for v in raw_entries)
    # Stream the retained ledger: no population-sized work-kind lookup.
    for work, ledger in zip(
        metadata.read_role(segment, "work.json", plan),
        metadata.read_role(segment, "work_ledger.json", plan),
        strict=True,
    ):
        b.require(work["work_id"] == ledger["work_id"], "B2_WORK_TOTALITY")
        row = result[work["kind"]]
        row["charged_attempts"] += len(ledger["charged_ordinals"])
    for row in result.values():
        known = sum(x["attempts"] for x in row["categories"].values())
        row["unverified_attempts"] = max(
            row["unverified_attempts"], row["charged_attempts"] - known
        )
        exact = row["unverified_attempts"] == 0
        row["categories"] = [
            {
                "http_category": h,
                "reason": reason,
                **{k: stats.count(v if exact else None, v) for k, v in counts.items()},
            }
            for (h, reason), counts in sorted(row["categories"].items())
        ]
        for name in (
            "application_bytes_observed",
            "received_body_bytes",
            "retained_raw_bytes",
            "retained_compressed_bytes",
        ):
            value = row[name]
            known = exact and (
                name != "application_bytes_observed"
                or row["unknown_application_attempts"] == 0
            )
            row[name] = stats.count(value if known else None, value)
        row["denominator"] = (
            "ALL_CHARGED_ATTEMPTS_OF_THIS_KIND; retries counted again; bytes exclude receipt metadata"
        )
        row["category_totals_exact"] = exact
    return {
        "by_kind": result,
        "http_category_domain": list(labels),
        "error_category_domain": list(reasons),
        "missing_category_interpretation": "ZERO_ONLY_WHEN_CATEGORY_TOTALS_EXACT;OTHERWISE_UNKNOWN",
    }


def publication_summary(
    root,
    *,
    catalog,
    rules,
    scratch,
    plan,
    segment,
    n_decision,
    adequacy,
    output_root=None,
):
    """Stream complete controlled rank/stratum/convergence tables; safe marginals.

    SQLite cache is2MiB, spill is disk. Full structural bytes, not hashes alone,
    key convergence. This diagnostic never deduplicates published candidate rows.
    """
    import os, json
    from . import s12_b2_catalog as catalogs
    from . import s12_b2_publication as pub
    from . import s12_raw_packs as packs
    from . import s12_storage as io

    output_root = root if output_root is None else output_root
    db = catalogs.connect(scratch)
    db.executescript("""create table cell(tab text,label text,source text,q blob,n integer,primary key(tab,label,source,q));
    create table convergence(source text,u text,representation text,family text,kind text,value blob,q blob,primary key(source,u,representation,family,kind,value,q));
    create table sources(source text primary key);""")
    paths = []

    def stream(name, rows):
        path = output_root / name
        from . import s12_b2_allocation_limits as limits

        limits.claim("PREFIX_FILE")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            for row in rows:
                raw = b.canonical(row)
                io.charge_write(path, len(raw))
                view = memoryview(raw)
                while view:
                    n = os.write(fd, view)
                    b.require(n > 0, "B2_DIAGNOSTIC_WRITE")
                    view = view[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        io.fsync_directory(output_root)
        paths.append(name)

    def cell(tab, label, source, q):
        db.execute(
            "insert into cell values(?,?,?,?,1) on conflict(tab,label,source,q) do update set n=n+1",
            (tab, label, source, q),
        )

    def ranks():
        for e in pub.relation_rows(root, "request_execution"):
            physical = io.read(
                root / "raw_packs" / e["raw_pack_key"], limit=packs.MAX_COMPRESSED
            )
            raw = response.decompress(
                physical[
                    e["raw_frame_offset"] : e["raw_frame_offset"]
                    + e["raw_frame_length"]
                ],
                length=e["response_bytes"],
                expected_hash=e["response_sha256"],
            )
            q = e["query_semantic_id"]
            work = {"query_semantic_id": q.hex(), "result_limit": plan["result_limit"]}
            p = response.extract(
                raw,
                e["request_execution_id"],
                size=plan["result_limit"],
                http_status=200,
                content_type="application/json",
                encoding="identity",
                layers=rules.layers,
                sources=rules.sources,
                expected_echo=rules.expected_echo(work),
                expected_hash=e["response_sha256"],
            )
            for context in catalog.contexts(q):
                source = context["stable_source_row_id_v1"]
                u = context["query_context_id"]
                db.execute("insert or ignore into sources values(?)", (source,))
                families = [
                    x[0]
                    for x in catalog.db.execute(
                        "select distinct f.name from family f join mapping m on m.h=f.h where f.u=? and m.q=? order by f.name",
                        (bytes.fromhex(u), q),
                    )
                ]
                base = {
                    "semantic": q.hex(),
                    "source_row": source,
                    "context": u,
                    "representation": context["representation"],
                    "families": families,
                }
                for row in rank_rows(
                    p, raw, context, sorted({1, 3, 5, plan["result_limit"]})
                ):
                    for metric in (
                        "new_compatible_tokens",
                        "new_unresolved_tokens",
                        "new_opaque_tokens",
                        "new_K",
                        "duplicate_K",
                        "duplicate_full_feature",
                        "new_gid",
                        "missing_gid",
                        "new_coordinate",
                        "new_source",
                        "new_layer",
                        "coarse",
                    ):
                        if metric in row:
                            label = str(row.get("rank", row.get("to_rank")))
                            db.execute(
                                "insert into cell values(?,?,?,?,?) on conflict(tab,label,source,q) do update set n=n+excluded.n",
                                (
                                    row["diagnostic"] + "_" + metric,
                                    label,
                                    source,
                                    q,
                                    int(row[metric]),
                                ),
                            )
                    yield {**base, **row}
                for dim, value in [
                    ("country", context["country"]),
                    ("mode", catalog.core(q)["search_mode"]),
                    ("script", context["script"]),
                    ("capability", context["capability"]),
                    ("completeness", context["completeness"]),
                    ("representation", context["representation"]),
                    ("country_capability", [context["country"], context["capability"]]),
                    *[("family", x) for x in families],
                ]:
                    cell(
                        "strata_" + dim, b.canonical(value).decode().strip(), source, q
                    )
                cell("candidate_count", str(len(p.candidates)), source, q)
                cell("terminal_state", e["terminal_state"], source, q)
                for candidate, structure in zip(
                    p.candidates, p.feature_structures, strict=True
                ):
                    cell("rank", str(candidate["rank"]), source, q)
                    layer = (
                        candidate["layer"]
                        if candidate["layer"]
                        in (
                            "address",
                            "street",
                            "venue",
                            "locality",
                            "localadmin",
                            "county",
                            "region",
                            "country",
                            "neighbourhood",
                            "borough",
                            "macroregion",
                            "macrocounty",
                            "continent",
                        )
                        else "OTHER"
                    )
                    source_label = (
                        candidate["source"]
                        if candidate["source"]
                        in (
                            "openstreetmap",
                            "openaddresses",
                            "geonames",
                            "whosonfirst",
                            "synthetic",
                        )
                        else "OTHER"
                    )
                    confidence = candidate["confidence"]
                    confidence_bin = (
                        "NULL"
                        if confidence is None
                        else "[0,.25)"
                        if confidence < 0.25
                        else "[.25,.5)"
                        if confidence < 0.5
                        else "[.5,.75)"
                        if confidence < 0.75
                        else "[.75,1]"
                    )
                    match = (
                        candidate["match_type"]
                        if candidate["match_type"]
                        in ("exact", "interpolated", "fallback")
                        else "NULL"
                        if candidate["match_type"] is None
                        else "OTHER"
                    )
                    for tab, label in [
                        ("layer", layer),
                        ("source", source_label),
                        ("confidence_descriptive", confidence_bin),
                        ("match_type_descriptive", match),
                    ]:
                        cell(tab, label, source, q)
                    for family in families:
                        for kind, value in [
                            ("FEATURE", c.framed([structure])),
                            *(
                                [("GID", candidate["gid"].encode())]
                                if candidate["gid"] is not None
                                else []
                            ),
                        ]:
                            db.execute(
                                "insert or ignore into convergence values(?,?,?,?,?,?,?)",
                                (
                                    source,
                                    u,
                                    context["representation"],
                                    family,
                                    kind,
                                    value,
                                    q,
                                ),
                            )

    try:
        stream("controlled_rank_diagnostics.jsonl", ranks())
        stream(
            "controlled_strata.jsonl",
            (
                {
                    "table": tab,
                    "cell": json.loads(label) if tab.startswith("strata_") else label,
                    "distinct_sources": sources,
                    "distinct_semantics": queries,
                    "occurrences": n,
                }
                for tab, label, sources, queries, n in db.execute(
                    "select tab,label,count(distinct source),count(distinct q),sum(n) from cell group by tab,label order by tab,label"
                )
            ),
        )
        # Full exact-value groups are controlled. Portable summaries release no key.
        stream(
            "controlled_convergence.jsonl",
            (
                {
                    "source_row": source,
                    "context": u,
                    "representation": rep,
                    "family": family,
                    "kind": kind,
                    "value_hex": value.hex(),
                    "semantic_incidence": n,
                    "meaning": "CORRELATED_INCIDENCE_NOT_INDEPENDENT_CONFIDENCE",
                }
                for source, u, rep, family, kind, value, n in db.execute(
                    "select source,u,representation,family,kind,value,count(distinct q) from convergence group by source,u,representation,family,kind,value order by source,u,representation,family,kind,value"
                )
            ),
        )
        tables = {}
        for tab in (
            "candidate_count",
            "rank",
            "terminal_state",
            "layer",
            "source",
            "confidence_descriptive",
            "match_type_descriptive",
            *(
                x[0]
                for x in db.execute(
                    "select distinct tab from cell where tab like 'ADJACENT_RANK_%' or tab like 'GRID_TRANSITION_%' order by tab"
                )
            ),
        ):
            rows = [
                {"label": label, "distinct_sources": sources, "observations": n}
                for label, sources, n in db.execute(
                    "select label,count(distinct source),sum(n) from cell where tab=? group by label order by label",
                    (tab,),
                )
            ]
            safe = bool(rows) and all(x["distinct_sources"] >= 20 for x in rows)
            tables[tab] = {
                "cells": rows if safe else None,
                "release": "SIZE_RULE_ELIGIBLE;EXTERNAL_RELEASE_PLAN_UNISSUED"
                if safe
                else "WHOLE_TABLE_SUPPRESSED_INCLUDING_TOTALS",
            }
        source_count = db.execute("select count(*) from sources").fetchone()[0]
    finally:
        db.close()
    from . import s12_b2_operations as o

    report = b.parse(io.read(segment / "operations_report.json"), o.REPORT)
    measured = b.parse(
        io.read(segment / "measurement_report.json"),
        "stage12_development_measurement_report_b2_v1",
    )
    return {
        "scientific": {
            "histograms": tables,
            "full_strata": "CONTROLLED_ONLY; cross-table differencing release not authorized",
            "convergence": "CONTROLLED_EXACT_CONTEXT_REPRESENTATION_FAMILY; shared queries/ancestry are correlated",
            "witness_curves": "CONTROLLED_ADJACENT_AND_G_TRANSITIONS; no scoring",
            "source_denominator": source_count if source_count >= 20 else None,
            "adequacy": None
            if adequacy is None
            else {
                k: adequacy[k]
                for k in (
                    "population_complete",
                    "coverage_complete",
                    "repeats_stable",
                    "tail_adequate",
                    "eligible_limits",
                    "proposed_limit",
                    "disposition",
                    "scientific_N_selected",
                )
            },
            "N_decision": None
            if n_decision is None
            else {
                "result_limit": n_decision["result_limit"],
                "decision": "EXPLICIT_SEPARATE_OWNER_DECISION",
                "rationale_record_sha256": b.digest(n_decision),
            },
            "controlled_artifacts": io.file_inventory(output_root, tuple(paths)),
            "denominators": "context-candidate/rank incidences; distinct sources separately; no summed strength",
        },
        "operational": {
            "attempt_categories_and_bytes": attempt_summary(
                segment, report["campaign_start_sha256"]
            ),
            "published_successful_response_bytes": {
                "uncompressed_application_bytes": sum(
                    e["response_bytes"]
                    for e in pub.relation_rows(root, "request_execution")
                ),
                "physical_compressed_bytes": sum(
                    p.stat().st_size for p in (root / "raw_packs").rglob("*.zst")
                ),
                "denominator": "ONE_SELECTED_SUCCESS_PER_EXECUTION; raw pack frames only; excludes retries, controls and metadata",
            },
            "counts": measured["counts"],
            "duration_ns": measured["duration_ns"],
            "rates": measured["rates"]
            if "rates" in measured
            else {
                k: v
                for k, v in measured.items()
                if "throughput" in k or "fraction" in k
            },
            "timings": {
                k: v
                for k, v in measured.items()
                if k == "latencies" or "latency" in k or "percentile" in k
            },
            "sampling_complete": measured["resource_sampling_complete"],
            "receipts_complete": measured["receipts_complete"],
            "campaign_report_sha256": b.digest(report),
            "measurement_sha256": b.digest(measured),
            "storage_bytes": sum(
                x["bytes"]
                for x in io.file_inventory(
                    root,
                    tuple(
                        str(p.relative_to(root))
                        for p in root.rglob("*")
                        if p.is_file()
                        and p.relative_to(root).parts[0]
                        in (
                            "request_execution",
                            "request_attempt",
                            "request_candidate",
                            "mapback",
                            "raw_packs",
                            "retrieval_policy.json",
                        )
                    ),
                )
            )
            + sum(x["bytes"] for x in io.file_inventory(output_root, tuple(paths))),
            "checkpoint_adoption": "FULL_PREDECESSOR_REOPEN_REQUIRED",
            "integrity": "ZERO_LOSS_MAPBACK_AND_EXACT_RELATION_REOPEN_REQUIRED",
        },
    }

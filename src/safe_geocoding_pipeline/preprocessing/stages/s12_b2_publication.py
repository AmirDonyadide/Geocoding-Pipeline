"""B2 four-relation assembly, zero-loss map-back and immutable publication."""

from __future__ import annotations

import os
import re
import hashlib
from pathlib import Path
from typing import Callable
from datetime import datetime

import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_publication as accepted
from . import s09_reference_io as accepted_io
from . import s11_semantic_io as upio
from . import s12_publication as v1pub
from . import s12_b2_contract as b
from . import s12_b2_allocation_limits as limits
from . import s12_b2_inventory as metadata
from . import s12_b2_operations as o
from . import s12_b2_audit as audit
from . import s12_b2_evidence as evidence
from . import s12_b2_recovery as recovery
from . import s12_b2_catalog as catalog_module
from . import s12_b2_diagnostics as diagnostics
from . import s12_raw_packs as packs
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_response as response

VERSION = "stage12_publication_record_b2_v1"
CALIBRATION = "STAGE12_DEVELOPMENT_OBSERVATIONAL_CALIBRATION_EVIDENCE"
FINAL = "STAGE12_DEVELOPMENT_OBSERVATIONAL_PELIAS_CANDIDATE"
BINDINGS = []
for key in v1pub.BINDINGS:
    if key == "pelias_deployment_fingerprint":
        BINDINGS.extend(("observation_binding_id", "campaign_id"))
    elif key not in ("index_data_identity", "effective_behavior_id"):
        BINDINGS.append(key)
BINDINGS = tuple(BINDINGS) + (
    "window_plan_sha256",
    "campaign_closure_sha256",
    "window_closure_sha256",
    "calibration_evidence_inventory_sha256",
    "privacy_permission_sha256",
    "scientific_decision_sha256",
)
DATASET_BINDINGS = []
for key in c.DATASET_BINDINGS:
    if key == "pelias_deployment_fingerprint":
        DATASET_BINDINGS.extend(("observation_binding_id", "campaign_id"))
    elif key not in ("index_data_identity", "effective_behavior_id"):
        DATASET_BINDINGS.append(key)
DATASET_BINDINGS = tuple(DATASET_BINDINGS) + (
    "window_plan_sha256",
    "campaign_closure_sha256",
    "window_closure_sha256",
    "calibration_evidence_inventory_sha256",
    "privacy_permission_sha256",
    "scientific_decision_sha256",
)


def registration(namespace, key, bindings):
    role = namespace.removeprefix(b.SYNTHETIC + "_")
    b.require(
        role in (CALIBRATION, FINAL)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", key) is not None
        and set(bindings) == set(BINDINGS),
        "B2_REGISTRATION_INVALID",
    )
    for name, value in bindings.items():
        if role == CALIBRATION and name in (
            "owner_freeze_sha256",
            "window_closure_sha256",
            "calibration_evidence_inventory_sha256",
        ):
            b.require(value is None, "B2_CALIBRATION_FORWARD_REFERENCE")
        else:
            b.validate_type(value, "G" if name == "executable_sha" else "D")
    body = {
        "record_version": VERSION,
        "namespace": namespace,
        "publication_key": key,
        "bindings": bindings,
    }
    return {
        "stage12_registration_id": c.identity(
            "SAFE:stage12-publication-record:b2:v1",
            [("record_version", VERSION), ("record_body", b.canonical(body))],
        ).hex(),
        "body": body,
    }


def relation_rows(root, name):
    if name == "retrieval_policy":
        policy = io.metadata(io.read(root / "retrieval_policy.json"))
        policy["retrieval_policy_id"] = bytes.fromhex(policy["retrieval_policy_id"])
        c.validate_policy(policy)
        yield policy
        return
    for path in sorted((root / name).glob("part-*.parquet")):
        upio.private(path)
        with pq.ParquetFile(path, page_checksum_verification=True) as pf:
            b.require(
                pf.schema_arrow.equals(b.schema(name), check_metadata=True),
                "B2_RELATION_SCHEMA",
            )
            for batch in pf.iter_batches(batch_size=1, use_threads=False):
                yield batch.to_pylist()[0]


def relation_record(root, name):
    count = sum(1 for _ in relation_rows(root, name))
    return {
        "name": name,
        "count": count,
        "sha256": b.relation_hash(name, count, relation_rows(root, name)).hex(),
        "scientific_sha256": None
        if name == "request_attempt"
        else b.relation_hash(
            name, count, relation_rows(root, name), scientific=True
        ).hex(),
    }


def capture_hashes(rows):
    count = sum(1 for _ in rows())
    raw = hashlib.sha256(b"SAFE:stage12-response-set:b2:v1\0" + c.framed([count]))
    ctx = hashlib.sha256(b"SAFE:stage12-capture-context:b2:v1\0" + c.framed([count]))
    previous = None
    for row in rows():
        q = row["request_execution_id"]
        b.require(previous is None or previous < q, "B2_CAPTURE_ORDER")
        previous = q
        raw.update(c.framed([q, row["response_sha256"], row["response_bytes"]]))
        ctx.update(
            c.framed(
                [
                    q,
                    row["request_target_sha256"],
                    row["http_status"],
                    row["content_type"],
                    row["content_encoding"],
                    True,
                ]
            )
        )
    return raw.digest(), ctx.digest()


def dataset(bindings, relations, raw_set, summary):
    fields = [
        (k, bytes.fromhex(bindings[k]) if bindings[k] is not None else None)
        for k in DATASET_BINDINGS
    ]
    fields.extend(
        [
            (
                "scientific_relations",
                [
                    (r["name"], bytes.fromhex(r["scientific_sha256"]), r["count"])
                    for r in relations
                    if r["scientific_sha256"] is not None
                ],
            ),
            ("raw_response_set_sha256", raw_set),
            ("scientific_summary_sha256", summary),
        ]
    )
    return c.identity("SAFE:stage12-dataset:b2:v1", fields).hex()


def sql_rows(connection, query):
    cursor = connection.cursor()
    cursor.execute("SET TimeZone='UTC'")
    try:
        yield from upio.rows(cursor, query)
    finally:
        cursor.close()


def assemble(
    root: Path,
    scratch: Path,
    *,
    segment: Path,
    start,
    scientific_start,
    profile,
    plan,
    catalog,
    rules,
    verify_campaign: Callable,
    memory_bytes: int,
):
    """At most one response and bounded Arrow batches; sorts spill to scratch."""
    verify_campaign()
    b.uint(memory_bytes, True)
    io.reserve(scratch)
    sql = limits.duck_connect(
        upio.connect, scratch, memory=str(memory_bytes) + "B", threads=1
    )
    sql.execute("SET TimeZone='UTC'")
    writers = {
        name: limits.relation_writer(
            scratch / name,
            b.schema(name),
            batch_rows=128,
            batch_bytes=1024 * 1024,
            target_file_bytes=16 * 1024 * 1024,
        )
        for name in ("request_execution", "request_attempt", "request_candidate")
    }
    sql.execute(
        "create table final_event(work ubigint, ordinal ubigint, delay ubigint)"
    )
    for event in recovery.events(segment, start, plan):
        if event["kind"] == "ATTEMPT_FINALIZED":
            sql.execute(
                "insert into final_event values(?,?,?)",
                [
                    event["body"]["work_id"],
                    event["body"]["attempt"],
                    event["body"]["retry_delay_ms"],
                ],
            )
    sql.execute(
        "create table selected(execution blob primary key, semantic blob, unit varchar, target blob, response blob, bytes ubigint, status ubigint, media varchar, coding varchar)"
    )
    sql.execute("create table contributing_sources(source varchar primary key)")

    def locate(work_id, ordinal):
        node = segment
        while node is not None:
            path = node / "attempts" / f"{work_id:020d}_{ordinal:02d}"
            if path.exists():
                return path
            from . import s12_public_journal as j

            node = j.predecessor_root(node)
        b.require(False, "B2_RECEIPT_MISSING")

    work_factory = lambda: metadata.read_role(segment, "work.json", plan)
    ledger_factory = lambda: metadata.read_role(segment, "work_ledger.json", plan)
    from itertools import zip_longest

    data_count = 0
    for work, ledger in zip_longest(work_factory(), ledger_factory()):
        b.require(
            work is not None
            and ledger is not None
            and work["work_id"] == ledger["work_id"]
            and ledger["state"] == "DURABLE_SUCCESS",
            "B2_WORK_TOTALITY",
        )
        if work["kind"] != "DATA":
            continue
        data_count += 1
        for context in catalog.contexts(bytes.fromhex(work["query_semantic_id"])):
            sql.execute(
                "insert or ignore into contributing_sources values(?)",
                [context["stable_source_row_id_v1"]],
            )
        selected = None
        for ordinal in ledger["charged_ordinals"]:
            unit = locate(work["work_id"], ordinal)
            receipt, projection, raw = audit.reopen(unit, **rules.kwargs())
            begin, _, origin, admission = audit.context(unit)
            record = io.metadata(io.read(unit / "transport.json"))
            b.require(origin == scientific_start, "B2_CAMPAIGN_BINDING")
            attempt = {k: None for k in b.columns("request_attempt")}
            attempt.update(
                attempt_id=bytes.fromhex(begin["attempt_id"]),
                request_execution_id=bytes.fromhex(begin["request_execution_id"]),
                campaign_id=bytes.fromhex(start["campaign_id"]),
                attempt_number=ordinal,
                campaign_start_sha256=bytes.fromhex(b.digest(scientific_start)),
                operations_policy_sha256=bytes.fromhex(b.digest(profile)),
                started_utc=b.stamp(begin["started_utc"]),
                finished_utc=b.stamp(receipt["finished_utc"]),
                elapsed_ms=record["elapsed_ms"],
                http_status=record["status"],
                outcome=receipt["outcome"],
                reason_code=receipt["reason"],
                received_body_bytes=record["received_body_bytes"],
                application_payload_bytes=receipt["response_bytes"],
                content_type=record["content_type"],
                content_encoding=record["content_encoding"],
                retry_after_seconds=record["retry_after_seconds"],
                segment_nonce=bytes.fromhex(begin["segment_nonce"]),
                preflight_observation_sha256=bytes.fromhex(
                    begin["preflight_observation_sha256"]
                ),
                response_validation_contract_sha256=bytes.fromhex(
                    receipt["validation_sha256"]
                ),
                response_sha256=bytes.fromhex(receipt["response_sha256"])
                if receipt["response_sha256"]
                else None,
            )
            # Retain the exact selected retry delay from its controller event.
            final = sql.execute(
                "select delay from final_event where work=? and ordinal=?",
                [work["work_id"], ordinal],
            ).fetchall()
            b.require(len(final) == 1, "B2_ATTEMPT_HISTORY")
            attempt["retry_delay_ms"] = final[0][0]
            b.row_bytes("request_attempt", attempt)
            writers["request_attempt"].append(attempt)
            if receipt["outcome"] in c.SUCCESS:
                b.require(
                    selected is None
                    and ordinal == ledger["charged_ordinals"][-1]
                    and raw is not None
                    and projection is not None,
                    "B2_ATTEMPT_HISTORY",
                )
                selected = (unit, receipt, projection, begin, record)
        b.require(selected is not None, "B2_WORK_TOTALITY")
        unit, receipt, projection, begin, record = selected
        sql.execute(
            "insert into selected values(?,?,?,?,?,?,?,?,?)",
            [
                bytes.fromhex(begin["request_execution_id"]),
                bytes.fromhex(work["query_semantic_id"]),
                str(unit),
                bytes.fromhex(begin["request_target_sha256"]),
                bytes.fromhex(receipt["response_sha256"]),
                receipt["response_bytes"],
                record["status"],
                record["content_type"],
                record["content_encoding"],
            ],
        )
        for row in projection.candidates:
            writers["request_candidate"].append(row)
    b.require(data_count == plan["budgets"]["data_observations"], "B2_WORK_TOTALITY")

    def fragments():
        for row in sql_rows(
            sql, "select execution,unit,response,bytes from selected order by execution"
        ):
            yield (
                row["execution"],
                Path(row["unit"]) / "raw.zst",
                row["bytes"],
                row["response"],
            )

    for entry in packs.pack(root / "raw_packs", fragments()):
        execution = bytes.fromhex(entry["request_execution_id"])
        row = sql.execute(
            "select semantic,unit,target from selected where execution=?", [execution]
        ).fetchone()
        receipt, projection, _ = audit.reopen(Path(row[1]), **rules.kwargs())
        begin, work, _, _ = audit.context(Path(row[1]))
        result = {k: None for k in b.columns("request_execution")}
        result.update(
            request_execution_id=execution,
            query_semantic_id=row[0],
            retrieval_policy_id=c.policy(plan["result_limit"])["retrieval_policy_id"],
            materialization_contract_sha256=bytes.fromhex(
                start["materialization_contract_sha256"]
            ),
            observation_binding_id=bytes.fromhex(start["observation_binding_id"]),
            campaign_id=bytes.fromhex(start["campaign_id"]),
            request_target_sha256=row[2],
            terminal_state=receipt["outcome"],
            reason_code="OK",
            terminal_attempt_id=bytes.fromhex(begin["attempt_id"]),
            candidate_count=receipt["candidate_count"],
            response_sha256=bytes.fromhex(entry["response_sha256"]),
            response_bytes=entry["response_bytes"],
            raw_pack_key=entry["raw_pack_key"],
            raw_frame_offset=entry["raw_frame_offset"],
            raw_frame_length=entry["raw_frame_length"],
            response_completed_utc=b.stamp(receipt["finished_utc"]),
        )
        writers["request_execution"].append(result)
    for name, writer in writers.items():
        writer.close()
        ordered = limits.relation_writer(
            root / name,
            b.schema(name),
            batch_rows=128,
            batch_bytes=1024 * 1024,
            target_file_bytes=16 * 1024 * 1024,
        )
        query = (
            "select * from "
            + upio.parquet_sql(writer.paths)
            + " order by "
            + ",".join(c.KEYS[name])
        )
        for row in sql_rows(sql, query):
            b.row_bytes(name, row)
            ordered.append(row)
        ordered.close()
    policy = c.policy(plan["result_limit"])
    io.write(
        root / "retrieval_policy.json",
        b.canonical(
            {**policy, "retrieval_policy_id": policy["retrieval_policy_id"].hex()}
        ),
    )
    # Complete original map retained separately; candidates never inner-join away
    # zero responses or contexts that had no eligible Stage11 request.
    map_schema = pa.schema(
        [
            pa.field("query_context_id", pa.string()),
            pa.field("stable_source_row_id_v1", pa.string()),
            pa.field("hypothesis_id", pa.string()),
            pa.field("query_semantic_id", pa.string()),
        ]
    )
    mapwriter = limits.relation_writer(
        root / "mapback",
        map_schema,
        batch_rows=128,
        batch_bytes=1024 * 1024,
        target_file_bytes=16 * 1024 * 1024,
    )
    for row in catalog.mapback():
        mapwriter.append(row)
    mapwriter.close()

    def captures():
        for x in sql_rows(
            sql,
            "select execution, target, response,bytes,status,media,coding from selected order by execution",
        ):
            yield {
                "request_execution_id": x["execution"],
                "request_target_sha256": x["target"],
                "response_sha256": x["response"],
                "response_bytes": x["bytes"],
                "http_status": x["status"],
                "content_type": x["media"],
                "content_encoding": x["coding"],
            }

    raw_set, context_hash = capture_hashes(captures)
    contributing_sources = sql.execute(
        "select count(*) from contributing_sources"
    ).fetchone()[0]
    sql.close()
    verify_campaign()
    return {
        "relations": [relation_record(root, name) for name in c.RELATIONS],
        "raw_response_set_sha256": raw_set.hex(),
        "capture_context_sha256": context_hash.hex(),
        "planned": data_count,
        "summary_source_count": contributing_sources,
    }


def scientific_reopen(
    root,
    manifest,
    *,
    catalog,
    rules,
    scratch: Path,
    memory_bytes: int,
    gate,
    verify_campaign,
    verify_calibration=None,
    verify_final_retention=None,
):
    catalog.verify()
    retained = io.metadata(io.read(root / "campaign.json"))
    start, science, plan, profile = (
        retained[x] for x in ("operations_start", "scientific_start", "plan", "profile")
    )
    bind = manifest["publication_bindings"]
    contract=o.for_profile(profile)
    if getattr(contract,"RA_ENABLED",False):
        b.require(manifest.get("manifest_version") == contract.PUBLICATION_MANIFEST and
                  manifest.get("resource_assurance") == contract.publication_resource_summary(profile),"B2_RA_PUBLICATION_BINDING")
        bound_authority=getattr(gate,"authority",gate)
        b.require(callable(getattr(bound_authority,"resource_prewrite",None)),"B2_RA_MONITOR_REQUIRED")
        bound_authority.resource_prewrite(next_write_bytes=0,next_creations=0)
    else:
        b.require("resource_assurance" not in manifest,"B2_RA_MIXED_METHOD")
    final = manifest["kind"].removeprefix(b.SYNTHETIC + "_") == FINAL
    n_decision = (
        b.parse(io.read(root / "N_decision.json"), "stage12_n_decision_b2_v1")
        if final
        else None
    )
    inventory = (
        io.metadata(io.read(root / "calibration_inventory.json"))["entries"]
        if final
        else None
    )
    segments = scientific_authority(
        segment=Path(retained["operational_root"]),
        start=start,
        scientific_start=science,
        profile=profile,
        plan=plan,
        gate=gate,
        campaign_closure_hash=retained["campaign_closure_sha256"],
        verify_campaign=verify_campaign,
        window_closure_hash=bind["window_closure_sha256"],
        calibration_inventory=inventory,
        n_decision=n_decision,
        verify_calibration=verify_calibration,
        verify_final_retention=verify_final_retention,
    )
    b.require(
        segments == retained["ordered_segment_closures"], "B2_PUBLICATION_BINDING"
    )
    expected = {
        "campaign_id": start["campaign_id"],
        "observation_binding_id": start["observation_binding_id"],
        "retrieval_policy_id": start["retrieval_policy_id"],
        "window_plan_sha256": start["window_plan_sha256"],
        "privacy_permission_sha256": start["privacy_permission_sha256"],
        "scientific_decision_sha256": start["scientific_decision_sha256"],
        "campaign_closure_sha256": retained["campaign_closure_sha256"],
        "stage12_input_binding_sha256": b.digest(catalog.binding),
        "campaign_manifest_sha256": b.digest(retained),
        "summary_sha256": b.sha(io.read(root / "summary.json")).hex(),
        "profile_sha256": b.digest(profile),
        "operations_sha256": b.digest(profile),
        "workload_sha256": b.digest(plan),
        "executable_sha": start["client_git_sha"],
        "runtime_inventory_sha256": start["runtime_inventory_sha256"],
        "owner_freeze_sha256": b.digest(n_decision) if final else None,
        "calibration_evidence_inventory_sha256": b.digest(inventory) if final else None,
        "schema_sha256": b.digest(b.assets()[b.SCHEMA]),
        "contract_sha256": b.digest(
            b.assets()["stage12_pelias_retrieval_contract_b2_v1"]
        ),
        "calibration_protocol_sha256": b.digest(
            b.assets()["stage12_calibration_protocol_b2_v1"]
        ),
        "candidate_relation_sha256": next(
            x["sha256"]
            for x in manifest["relations"]
            if x["name"] == "request_candidate"
        ),
        "projection_provenance_sha256": b.digest(
            {
                "profile": b.digest(profile),
                "campaign": b.digest(science),
                "schema": b.digest(b.assets()[b.SCHEMA]),
            }
        ),
        "adopted_checkpoint_inventory_sha256": o.manifest_digest(
            metadata.read_role(
                Path(retained["operational_root"]), "attempt_inventory.json", plan
            )
        ),
    }
    b.require(all(bind[k] == v for k, v in expected.items()), "B2_PUBLICATION_BINDING")
    b.require(
        manifest["population_scope"] == plan["population_scope"]
        and manifest["workload_kind"] == plan["workload_kind"],
        "B2_PUBLICATION_BINDING",
    )
    records = [relation_record(root, n) for n in c.RELATIONS]
    b.require(records == manifest["relations"], "B2_RELATION_HASH")
    policy = next(relation_rows(root, "retrieval_policy"))
    execution_count = 0
    # One execution at a time; bounded external-order candidate/attempt merge.
    candidates = iter(relation_rows(root, "request_candidate"))
    candidate = next(candidates, None)
    io.reserve(scratch)
    sql = limits.duck_connect(
        upio.connect, scratch, memory=str(memory_bytes) + "B", threads=1
    )
    sql.execute("SET TimeZone='UTC'")
    sql.execute("create table seen(q blob primary key, execution blob unique)")
    sql.execute(
        "create table captures(execution blob primary key,target blob,response blob,bytes ubigint,status ubigint,media varchar,coding varchar)"
    )
    attempt_paths = tuple(sorted((root / "request_attempt").glob("part-*.parquet")))
    attempt_iter = iter(
        sql_rows(
            sql,
            "select * from "
            + upio.parquet_sql(attempt_paths)
            + " order by request_execution_id,attempt_number",
        )
    )
    attempt = next(attempt_iter, None)
    attempt_count = 0
    # Attempt IDs sort independently of execution IDs. A bounded disk join is
    # used by the caller's assembly; reopen independently scans at most five
    # attempts per execution without trusting that index.
    bindings = manifest["publication_bindings"]
    scientific_start = io.metadata(io.read(root / "campaign.json"))["scientific_start"]
    b.validate(scientific_start, "stage12_campaign_provenance_b2_v1")
    b.verify_executable_science(scientific_start)
    b.require(
        bindings["validation_sha256"]
        == scientific_start["response_validation_contract_sha256"]
        and bindings["extraction_sha256"]
        == scientific_start["response_extraction_contract_sha256"],
        "B2_EXECUTABLE_CONTRACT_MISMATCH",
    )
    for execution in relation_rows(root, "request_execution"):
        execution_count += 1
        q = execution["query_semantic_id"]
        core = catalog.core(q)
        target, _ = c.materialize(core, q, policy, target_limit=2**32)
        b.require(
            execution["request_target_sha256"] == b.sha(b"GET\0" + target),
            "B2_REQUEST_BINDING",
        )
        expected = b.execution_id(
            q,
            policy["retrieval_policy_id"],
            execution["materialization_contract_sha256"],
            execution["observation_binding_id"],
            execution["campaign_id"],
        )
        b.require(
            expected == execution["request_execution_id"]
            and execution["retrieval_policy_id"] == policy["retrieval_policy_id"]
            and execution["terminal_state"] in c.SUCCESS,
            "B2_EXECUTION_ID",
        )
        sql.execute("insert into seen values(?,?)", [q, expected])
        b.require(
            execution["materialization_contract_sha256"].hex()
            == scientific_start["materialization_contract_sha256"],
            "B2_EXECUTION_BINDING",
        )
        for k in ("observation_binding_id", "campaign_id"):
            b.require(execution[k].hex() == bindings[k], "B2_EXECUTION_BINDING")
        actual_attempts = []
        while attempt is not None and attempt["request_execution_id"] == expected:
            actual_attempts.append(attempt)
            attempt_count += 1
            b.require(len(actual_attempts) <= 5, "B2_ATTEMPT_HISTORY")
            attempt = next(attempt_iter, None)
        actual_attempts.sort(key=lambda x: x["attempt_number"])
        b.require(
            1 <= len(actual_attempts) <= 5
            and [x["attempt_number"] for x in actual_attempts]
            == list(range(1, len(actual_attempts) + 1)),
            "B2_ATTEMPT_HISTORY",
        )
        for x in actual_attempts:
            b.require(
                x["campaign_id"] == execution["campaign_id"]
                and x["attempt_id"]
                == b.attempt_id(expected, x["campaign_id"], x["attempt_number"]),
                "B2_ATTEMPT_ID",
            )
        for x in actual_attempts:
            b.require(
                x["campaign_start_sha256"].hex() == b.digest(scientific_start)
                and x["operations_policy_sha256"].hex()
                == scientific_start["operations_policy_sha256"]
                and x["response_validation_contract_sha256"].hex()
                == scientific_start["response_validation_contract_sha256"],
                "B2_ATTEMPT_BINDING",
            )
        selected = actual_attempts[-1]
        b.require(
            selected["attempt_id"] == execution["terminal_attempt_id"]
            and selected["outcome"] == execution["terminal_state"]
            and selected["response_sha256"] == execution["response_sha256"]
            and all(
                x["outcome"] == "TECHNICAL_FAILURE_RETRYABLE"
                for x in actual_attempts[:-1]
            ),
            "B2_ATTEMPT_HISTORY",
        )
        b.require(
            selected["application_payload_bytes"] == execution["response_bytes"]
            and selected["finished_utc"] == execution["response_completed_utc"],
            "B2_CAPTURE_LENGTH",
        )
        sql.execute(
            "insert into captures values(?,?,?,?,?,?,?)",
            [
                expected,
                execution["request_target_sha256"],
                execution["response_sha256"],
                execution["response_bytes"],
                selected["http_status"],
                selected["content_type"],
                selected["content_encoding"],
            ],
        )
        path = root / "raw_packs" / execution["raw_pack_key"]
        physical = io.read(path, limit=packs.MAX_COMPRESSED)
        offset = execution["raw_frame_offset"]
        length = execution["raw_frame_length"]
        b.require(offset + length <= len(physical), "B2_RAW_LOCATOR")
        pack_receipt = io.metadata(io.read(path.parent / "receipt.json"))
        b.require(
            io.read(path.parent / "_SEALED", limit=0) == b""
            and pack_receipt["physical_sha256"] == b.sha(physical).hex(),
            "B2_RAW_PACK_INVALID",
        )
        frame = next(
            (
                f
                for f in pack_receipt["frames"]
                if f["request_execution_id"] == expected.hex()
            ),
            None,
        )
        b.require(
            frame is not None
            and frame["raw_frame_offset"] == offset
            and frame["raw_frame_length"] == length
            and frame["response_sha256"] == execution["response_sha256"].hex(),
            "B2_RAW_LOCATOR",
        )
        raw = response.decompress(
            physical[offset : offset + length],
            length=execution["response_bytes"],
            expected_hash=execution["response_sha256"],
        )
        work = {"query_semantic_id": q.hex(), "result_limit": policy["result_limit"]}
        projection = response.extract(
            raw,
            expected,
            size=policy["result_limit"],
            http_status=selected["http_status"],
            content_type=selected["content_type"],
            encoding=selected["content_encoding"],
            layers=rules.layers,
            sources=rules.sources,
            expected_echo=rules.expected_echo(work),
            expected_hash=execution["response_sha256"],
        )
        b.require(
            len(projection.candidates) == execution["candidate_count"],
            "B2_CANDIDATE_COUNT",
        )
        for expected_row in projection.candidates:
            b.require(
                candidate is not None
                and b.row_bytes("request_candidate", candidate)
                == b.row_bytes("request_candidate", expected_row),
                "B2_PROJECTION_MISMATCH",
            )
            candidate = next(candidates, None)
    b.require(
        candidate is None
        and attempt is None
        and attempt_count
        == next(r["count"] for r in records if r["name"] == "request_attempt")
        and execution_count == manifest["planned"],
        "B2_RELATION_TOTALITY",
    )

    def checked_captures():
        for x in sql_rows(sql, "select * from captures order by execution"):
            yield {
                "request_execution_id": x["execution"],
                "request_target_sha256": x["target"],
                "response_sha256": x["response"],
                "response_bytes": x["bytes"],
                "http_status": x["status"],
                "content_type": x["media"],
                "content_encoding": x["coding"],
            }

    raw_hash, context_hash = capture_hashes(checked_captures)
    b.require(
        raw_hash.hex() == manifest["raw_response_set_sha256"]
        and context_hash.hex() == manifest["capture_context_sha256"],
        "B2_CAPTURE_SET_MISMATCH",
    )
    sql.close()
    from itertools import zip_longest

    actual_map = upio.parquet_rows(
        tuple(sorted((root / "mapback").glob("part-*.parquet")))
    )
    for left, right in zip_longest(actual_map, catalog.mapback()):
        b.require(left is not None and left == right, "B2_MAPBACK_LOSS")
    if manifest["workload_kind"] in ("FULL_C", "DIRECT_N"):
        b.require(
            execution_count == catalog.binding["semantic_count"],
            "B2_POPULATION_TOTALITY",
        )
        # PK uniqueness + exact membership + equal cardinality proves full coverage.
    projection_id = b.projection_id(
        bytes.fromhex(manifest["raw_response_set_sha256"]),
        bytes.fromhex(manifest["capture_context_sha256"]),
        bytes.fromhex(start["response_validation_contract_sha256"]),
        bytes.fromhex(start["response_extraction_contract_sha256"]),
        bytes.fromhex(start["candidate_schema_sha256"]),
    ).hex()
    b.require(
        bind["response_projection_id"] == projection_id
        and bind["scientific_result_sha256"]
        == dataset(
            bind,
            manifest["relations"],
            bytes.fromhex(manifest["raw_response_set_sha256"]),
            bytes.fromhex(bind["summary_sha256"]),
        ),
        "B2_SCIENTIFIC_HASH",
    )
    retained_summary = io.metadata(io.read(root / "summary.json"))
    diagnostic_root = scratch / "diagnostics_recomputed"
    io.reserve(diagnostic_root)
    adequacy = verify_calibration() if final else None
    if final:
        b.require(
            io.read(root / "calibration_result.json") == b.canonical(adequacy),
            "B2_CALIBRATION_REPORT_CHANGED",
        )
    recomputed = diagnostics.publication_summary(
        root,
        catalog=catalog,
        rules=rules,
        scratch=scratch / "diagnostics.sqlite",
        plan=plan,
        segment=Path(retained["operational_root"]),
        n_decision=n_decision,
        adequacy=adequacy,
        output_root=diagnostic_root,
    )
    b.require(
        all(retained_summary[k] == v for k, v in recomputed.items()),
        "B2_SUMMARY_MISMATCH",
    )
    catalog.verify()
    return records


def validate_terminal(root, expected_hash, *, committed, validate_science):
    accepted.check_parent(root)
    accepted_io.topology(root)
    raw = io.read(root / "manifest.json")
    b.require(b.sha(raw) == expected_hash, "B2_MANIFEST_HASH")
    manifest = io.metadata(raw)
    ra_manifest=manifest.get("manifest_version") == "stage12_pelias_retrieval_manifest_b2_ra_g1_v1"
    if ra_manifest:
        from . import s12_b2_ra_g1_contract as ra
    b.require(
        set(manifest) - ({"resource_assurance"} if ra_manifest else set())
        == {
            "manifest_version",
            "kind",
            "population_scope",
            "workload_kind",
            "publication_bindings",
            "inventory",
            "relations",
            "raw_response_set_sha256",
            "capture_context_sha256",
            "planned",
            "completed",
            "unprocessed",
            "failures",
            "continuous_service_state",
            "service_evidence_state",
        }
        and manifest["manifest_version"] == (ra.PUBLICATION_MANIFEST if ra_manifest else "stage12_pelias_retrieval_manifest_b2_v1"),
        "B2_MANIFEST_SCHEMA",
    )
    if ra_manifest:
        ra.validate_type(manifest["resource_assurance"],ra.PUBLICATION_RESOURCE_SCHEMA)
        retained=io.metadata(io.read(root/"campaign.json"))
        b.require(retained["profile"]["schema_version"] == ra.PROFILE and
                  manifest["resource_assurance"] == ra.publication_resource_summary(retained["profile"]),"B2_RA_PUBLICATION_BINDING")
    bindings = {
        **manifest["publication_bindings"],
        "manifest_sha256": expected_hash.hex(),
    }
    expected = registration(manifest["kind"], root.name, bindings)
    b.require(
        io.read(root / "registration.json") == b.canonical(expected),
        "B2_REGISTRATION_INVALID",
    )
    b.require(
        manifest["continuous_service_state"] == "NOT_VERIFIED"
        and manifest["service_evidence_state"] == "CLOSED_OBSERVATIONAL"
        and manifest["failures"] == manifest["unprocessed"] == 0
        and manifest["completed"] == manifest["planned"],
        "B2_PUBLICATION_INCOMPLETE",
    )
    b.require(
        manifest["kind"].startswith(b.SYNTHETIC + "_")
        == (manifest["population_scope"] == b.SYNTHETIC),
        "B2_POPULATION_SCOPE",
    )
    if manifest["population_scope"] == b.DEVELOPMENT and manifest["workload_kind"] in (
        "FULL_C",
        "DIRECT_N",
    ):
        b.require(manifest["planned"] == 105805, "B2_ACCEPTED_POPULATION_REQUIRED")
    b.require(
        b.digest(manifest["inventory"]) == bindings["inventory_sha256"],
        "B2_INVENTORY_HASH",
    )
    io.verify_inventory(
        root,
        manifest["inventory"],
        extra={"manifest.json", "registration.json"}
        | ({"_COMMITTED"} if committed else set()),
    )
    if committed:
        b.require(io.read(root / "_COMMITTED", limit=0) == b"", "B2_SEAL_INVALID")
    validate_science(root, manifest)
    return manifest


def publish(root, *, build, validate_science, fault=lambda phase: None):
    """Accepted exclusive reservation/seal protocol in a distinct namespace."""
    attempted = False
    try:
        with accepted.anchor(root) as parent_fd:
            os.mkdir(root.name, 0o700, dir_fd=parent_fd)
            fd = os.open(
                root.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                accepted.ownership(root, parent_fd, fd)
                os.fsync(parent_fd)
                fault("reserved")
                manifest = build(root)
                b.require(
                    "manifest_sha256" not in manifest["publication_bindings"],
                    "B2_SELF_REFERENCE",
                )
                io.write(root / "manifest.json", b.canonical(manifest))
                h = b.sha(io.read(root / "manifest.json"))
                io.write(
                    root / "registration.json",
                    b.canonical(
                        registration(
                            manifest["kind"],
                            root.name,
                            {
                                **manifest["publication_bindings"],
                                "manifest_sha256": h.hex(),
                            },
                        )
                    ),
                )
                accepted_io.fsync_tree(root)
                os.fsync(parent_fd)
                validate_terminal(
                    root, h, committed=False, validate_science=validate_science
                )
                fault("before_seal")
                accepted.ownership(root, parent_fd, fd)
                attempted = True
                accepted.create_seal(root, fd)
                fault("after_seal")
                os.fsync(fd)
                os.fsync(parent_fd)
                validate_terminal(
                    root, h, committed=True, validate_science=validate_science
                )
            finally:
                os.close(fd)
        validate_terminal(root, h, committed=True, validate_science=validate_science)
        return h
    except BaseException as error:
        if attempted and isinstance(error, Exception):
            raise c.Stage12Error("B2_PUBLICATION_OUTCOME_UNKNOWN") from None
        raise


def scientific_authority(
    *,
    segment,
    start,
    scientific_start,
    profile,
    plan,
    gate,
    campaign_closure_hash,
    verify_campaign,
    window_closure_hash=None,
    calibration_inventory=None,
    n_decision=None,
    verify_calibration=None,
    verify_final_retention=None,
):
    from . import s12_b2_operations as operations
    o = operations.for_profile(profile)
    verify_campaign()
    b.verify_executable_science(scientific_start)
    o.validate_plan(plan, profile)
    gate.require("publication", start["initial_workload_authority_sha256"], plan)
    final = n_decision is not None
    if final:
        b.validate(n_decision, "stage12_n_decision_b2_v1")
        b.require(
            window_closure_hash is not None
            and calibration_inventory is not None
            and verify_calibration is not None
            and verify_final_retention is not None,
            "B2_FINAL_INPUT_REQUIRED",
        )
        b.require(
            n_decision["decision"] == "SELECTED"
            and n_decision["result_limit"] == plan["result_limit"]
            and n_decision["retrieval_policy_id"] == start["retrieval_policy_id"]
            and n_decision["window_plan_sha256"] == start["window_plan_sha256"]
            and n_decision["calibration_inventory_sha256"]
            == b.digest(calibration_inventory),
            "B2_N_DECISION_MISMATCH",
        )
        gate.require("N_selection", b.digest(n_decision), n_decision)
        b.require(
            calibration_inventory
            == sorted(
                calibration_inventory,
                key=lambda x: (x["workload_kind"], x["publication_sha256"]),
            )
            and len({x["publication_sha256"] for x in calibration_inventory})
            == len(calibration_inventory),
            "B2_CALIBRATION_INVENTORY",
        )
        for entry in calibration_inventory:
            b.require(
                set(entry)
                == {
                    "workload_kind",
                    "publication_sha256",
                    "campaign_closure_sha256",
                    "window_plan_sha256",
                    "workload_sha256",
                }
                and entry["workload_kind"] in ("FULL_C", "TAIL", "PAIRED")
                and entry["window_plan_sha256"] == start["window_plan_sha256"],
                "B2_CALIBRATION_INVENTORY",
            )
        adequacy = verify_calibration()
        b.validate(adequacy, "stage12_calibration_result_b2_v1")
        window_plan = gate.records.get(start["window_plan_sha256"], "window_plan")
        core = gate.records.get(
            window_plan["calibration_plan_sha256"], "calibration_plan"
        )
        b.require(
            adequacy["window_plan_sha256"] == start["window_plan_sha256"]
            and adequacy["population_scope"] == plan["population_scope"]
            and adequacy["calibration_inventory_sha256"]
            == b.digest(calibration_inventory)
            and window_plan["dispatch_from"]
            <= n_decision["decided_utc"]
            < window_plan["dispatch_until"],
            "B2_N_DECISION_MISMATCH",
        )
        if n_decision["result_limit"] == core["C"]:
            full = [x for x in calibration_inventory if x["workload_kind"] == "FULL_C"]
            b.require(
                len(full) == 1
                and plan["workload_kind"] == "FULL_C"
                and full[0]["workload_sha256"] == b.digest(plan)
                and full[0]["campaign_closure_sha256"] == campaign_closure_hash,
                "B2_FULL_C_REUSE",
            )
        else:
            b.require(plan["workload_kind"] == "DIRECT_N", "B2_DIRECT_N_REQUIRED")
        b.require(
            adequacy["disposition"] == "ELIGIBLE_FOR_OWNER_REVIEW"
            and plan["result_limit"] in adequacy["eligible_limits"],
            "B2_CALIBRATION_INADEQUATE",
        )
        b.require(
            b.digest(adequacy) == n_decision["adequacy_report_sha256"],
            "B2_N_DECISION_MISMATCH",
        )
        verify_final_retention()
    else:
        b.require(
            window_closure_hash is calibration_inventory is None
            and plan["workload_kind"] in ("FULL_C", "TAIL", "PAIRED"),
            "B2_CALIBRATION_FORWARD_REFERENCE",
        )
    node = segment
    segments = []
    from . import s12_public_journal as j

    while node is not None:
        snap = o.parse(io.read(node / "snapshot.json"), o.SNAPSHOT)
        segments.append(snap["segment_closure_sha256"])
        node = j.predecessor_root(node)
    segments.reverse()
    evidence.campaign_closure(
        gate.records,
        campaign_closure_hash,
        plan=plan,
        start=scientific_start,
        segments=segments,
        authority=gate,
        population_scope=plan["population_scope"],
    )
    if final:
        window = gate.records.get(window_closure_hash, "window_closure")
        expected = {
            campaign_closure_hash,
            *[x["campaign_closure_sha256"] for x in calibration_inventory],
        }
        b.require(
            set(window["ordered_campaign_closure_hashes"]) == expected,
            "B2_WINDOW_TOTALITY",
        )
        evidence.window_closure(
            gate.records,
            window_closure_hash,
            window_hash=start["window_plan_sha256"],
            campaigns=window["ordered_campaign_closure_hashes"],
            authority=gate,
        )
    return segments


def publish_campaign(
    root,
    scratch,
    *,
    segment,
    start,
    scientific_start,
    profile,
    plan,
    catalog,
    rules,
    gate,
    campaign_closure_hash,
    verify_campaign,
    memory_bytes,
    window_closure_hash=None,
    calibration_inventory=None,
    n_decision=None,
    verify_calibration=None,
    verify_final_retention=None,
    fault=lambda phase: None,
):
    """Calibrations publish before N; final candidates need all real gates.

    Verification callbacks reopen complete retained calibration publications and
    execute the fixed witness checks. They cannot be substituted by a digest.
    The entrypoint constructs these from the declared artifact paths.
    """
    segments = scientific_authority(
        segment=segment,
        start=start,
        scientific_start=scientific_start,
        profile=profile,
        plan=plan,
        gate=gate,
        campaign_closure_hash=campaign_closure_hash,
        verify_campaign=verify_campaign,
        window_closure_hash=window_closure_hash,
        calibration_inventory=calibration_inventory,
        n_decision=n_decision,
        verify_calibration=verify_calibration,
        verify_final_retention=verify_final_retention,
    )
    final = n_decision is not None
    descriptors = b.assets()
    hashes = {name: b.digest(obj) for name, obj in descriptors.items()}
    b.require(
        start["candidate_schema_sha256"] == b.digest(b.descriptor("request_candidate"))
        and start["response_extraction_contract_sha256"] == hashes[b.EXTRACTION],
        "B2_PROJECTION_BINDING",
    )
    role = FINAL if final else CALIBRATION
    namespace = (
        b.SYNTHETIC + "_" if plan["population_scope"] == b.SYNTHETIC else ""
    ) + role
    counter = 0

    def validate(root, manifest):
        nonlocal counter
        counter += 1
        scientific_reopen(
            root,
            manifest,
            catalog=catalog,
            rules=rules,
            scratch=scratch / ("reopen_" + str(counter)),
            memory_bytes=memory_bytes,
            gate=gate,
            verify_campaign=verify_campaign,
            verify_calibration=verify_calibration,
            verify_final_retention=verify_final_retention,
        )

    io.reserve(scratch)

    def build(root):
        assembled = assemble(
            root,
            scratch / "assembly",
            segment=segment,
            start=start,
            scientific_start=scientific_start,
            profile=profile,
            plan=plan,
            catalog=catalog,
            rules=rules,
            verify_campaign=verify_campaign,
            memory_bytes=memory_bytes,
        )
        projection = b.projection_id(
            bytes.fromhex(assembled["raw_response_set_sha256"]),
            bytes.fromhex(assembled["capture_context_sha256"]),
            bytes.fromhex(start["response_validation_contract_sha256"]),
            bytes.fromhex(start["response_extraction_contract_sha256"]),
            bytes.fromhex(start["candidate_schema_sha256"]),
        ).hex()
        summary = {
            "summary_version": "stage12_pelias_retrieval_summary_b2_v1",
            "population_scope": plan["population_scope"],
            "observation_evidence": {
                "provenance_model": "MAINTAINED_SERVICE_OBSERVATIONS",
                "data_generation_status": "UNVERIFIED",
                "continuous_service_state": "NOT_VERIFIED",
                "service_evidence_state": "CLOSED_OBSERVATIONAL",
                "limitations": [
                    "INCOMPLETE_SOURCE_INDEX_PROVENANCE",
                    "PREPOST_NOT_CONTINUOUS_VERIFICATION",
                    "UNDETECTED_INTERVENING_CHANGE_POSSIBLE",
                    "CORRESPONDENCE_NOT_INSTALLED_CONTENTS",
                    "NO_IDENTICAL_FUTURE_RESULTS_GUARANTEE",
                ],
            },
            "permission_status": "VERIFIED_FOR_EXACT_DECLARED_SCOPE"
            if plan["population_scope"] == b.DEVELOPMENT
            else "SYNTHETIC_TEST_ONLY_NOT_PERMISSION",
            "window_applicability": "SAME_DECLARED_WINDOW_ONLY",
            "interruptions": len(segments) - 1,
            "counts": {
                "semantic_requests": assembled["planned"]
                if assembled["summary_source_count"] >= 20
                else None,
                "source_rows": assembled["summary_source_count"]
                if assembled["summary_source_count"] >= 20
                else None,
            },
            "suppression": "SMALL_CELLS_AND_COMPLEMENTS_SUPPRESSED;NO_ROW_IDENTIFIERS_OR_TEXT",
        }
        adequacy = verify_calibration() if final else None
        if adequacy is not None:
            io.write(root / "calibration_result.json", b.canonical(adequacy))
        summary.update(
            diagnostics.publication_summary(
                root,
                catalog=catalog,
                rules=rules,
                scratch=scratch / "diagnostics.sqlite",
                plan=plan,
                segment=segment,
                n_decision=n_decision,
                adequacy=adequacy,
            )
        )
        io.write(root / "summary.json", b.canonical(summary))
        del assembled["summary_source_count"]
        io.write(
            root / "campaign.json",
            b.canonical(
                {
                    "scientific_start": scientific_start,
                    "operations_start": start,
                    "plan": plan,
                    "profile": profile,
                    "ordered_segment_closures": segments,
                    "campaign_closure_sha256": campaign_closure_hash,
                    "operational_root": str(segment),
                }
            ),
        )
        if final:
            io.write(
                root / "calibration_inventory.json",
                b.canonical({"entries": calibration_inventory}),
            )
            io.write(root / "N_decision.json", b.canonical(n_decision))
        inventory = io.file_inventory(
            root,
            tuple(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()),
        )
        relations = assembled["relations"]
        candidate = next(x for x in relations if x["name"] == "request_candidate")
        bindings = {
            "stage12_input_binding_sha256": b.digest(catalog.binding),
            "inventory_sha256": b.digest(inventory),
            "executable_sha": start["client_git_sha"],
            "runtime_inventory_sha256": start["runtime_inventory_sha256"],
            "contract_sha256": hashes["stage12_pelias_retrieval_contract_b2_v1"],
            "profile_sha256": b.digest(profile),
            "schema_sha256": hashes[b.SCHEMA],
            "validation_sha256": start["response_validation_contract_sha256"],
            "extraction_sha256": start["response_extraction_contract_sha256"],
            "response_projection_id": projection,
            "campaign_manifest_sha256": b.sha(io.read(root / "campaign.json")).hex(),
            "projection_provenance_sha256": b.digest(
                {
                    "profile": b.digest(profile),
                    "campaign": b.digest(scientific_start),
                    "schema": hashes[b.SCHEMA],
                }
            ),
            "operations_sha256": b.digest(profile),
            "retrieval_policy_id": start["retrieval_policy_id"],
            "observation_binding_id": start["observation_binding_id"],
            "campaign_id": start["campaign_id"],
            "candidate_relation_sha256": candidate["sha256"],
            "summary_sha256": b.digest(summary),
            "calibration_protocol_sha256": hashes["stage12_calibration_protocol_b2_v1"],
            "workload_sha256": b.digest(plan),
            "adopted_checkpoint_inventory_sha256": o.manifest_digest(
                metadata.read_role(segment, "attempt_inventory.json", plan)
            ),
            "owner_freeze_sha256": b.digest(n_decision) if final else None,
            "window_plan_sha256": start["window_plan_sha256"],
            "campaign_closure_sha256": campaign_closure_hash,
            "window_closure_sha256": window_closure_hash,
            "calibration_evidence_inventory_sha256": b.digest(calibration_inventory)
            if final
            else None,
            "privacy_permission_sha256": start["privacy_permission_sha256"],
            "scientific_decision_sha256": start["scientific_decision_sha256"],
        }
        bindings["scientific_result_sha256"] = dataset(
            bindings,
            relations,
            bytes.fromhex(assembled["raw_response_set_sha256"]),
            bytes.fromhex(bindings["summary_sha256"]),
        )
        contract=o.for_profile(profile)
        return {
            **({"resource_assurance":contract.publication_resource_summary(profile)} if getattr(contract,"RA_ENABLED",False) else {}),
            "manifest_version": contract.PUBLICATION_MANIFEST if getattr(contract,"RA_ENABLED",False) else "stage12_pelias_retrieval_manifest_b2_v1",
            "kind": namespace,
            "population_scope": plan["population_scope"],
            "workload_kind": plan["workload_kind"],
            "publication_bindings": bindings,
            "inventory": inventory,
            **assembled,
            "completed": assembled["planned"],
            "unprocessed": 0,
            "failures": 0,
            "continuous_service_state": "NOT_VERIFIED",
            "service_evidence_state": "CLOSED_OBSERVATIONAL",
        }

    return publish(root, build=build, validate_science=validate, fault=fault)


class ArtifactReader:
    """Report-lifetime disk index over a fully reopened immutable publication.

    Each response hash is checked on access; complete sources reopen before and
    after calibration. The disk index never authorizes work or becomes evidence.
    """

    def __init__(
        self, root, expected_hash, *, scratch, catalog, rules, validate_artifact
    ):
        from . import s12_b2_calibration as calibration

        self.root, self.expected_hash, self.rules = root, expected_hash, rules
        self.validate_artifact = validate_artifact
        manifest = validate_artifact()
        b.require(
            b.sha(io.read(root / "manifest.json")) == expected_hash, "B2_MANIFEST_HASH"
        )
        self.db = catalog_module.connect(scratch)
        self.db.execute("create table execution(q blob primary key,e blob)")
        for row in relation_rows(root, "request_execution"):
            encoded = {
                k: v.hex()
                if isinstance(v, bytes)
                else v.isoformat()
                if isinstance(v, datetime)
                else v
                for k, v in row.items()
            }
            self.db.execute(
                "insert into execution values(?,?)",
                (row["query_semantic_id"], b.canonical(encoded)),
            )
        self.db.commit()
        self.catalog = catalog
        self.manifest = manifest
        plan = io.metadata(io.read(root / "campaign.json"))["plan"]
        bind = manifest["publication_bindings"]
        self.observation = calibration.Observation(
            plan["workload_kind"],
            plan["result_limit"],
            plan["repetition"],
            manifest["population_scope"],
            bind["window_plan_sha256"],
            manifest["planned"],
            o.manifest_digest(q.hex() for q in self.ids()),
            expected_hash.hex(),
            bind["campaign_closure_sha256"],
            bind["workload_sha256"],
            self.read,
            self.ids,
            self.validate,
        )

    def ids(self):
        for (q,) in self.db.execute("select q from execution order by q"):
            yield q

    def validate(self):
        manifest = self.validate_artifact()
        b.require(
            b.sha(io.read(self.root / "manifest.json")) == self.expected_hash
            and manifest == self.manifest,
            "B2_ARTIFACT_CHANGED",
        )

    def read(self, q):
        import json

        row = self.db.execute("select e from execution where q=?", (q,)).fetchone()
        b.require(row is not None, "B2_CALIBRATION_TOTALITY")
        e = json.loads(row[0])
        physical = io.read(
            self.root / "raw_packs" / e["raw_pack_key"], limit=packs.MAX_COMPRESSED
        )
        raw = response.decompress(
            physical[
                e["raw_frame_offset"] : e["raw_frame_offset"] + e["raw_frame_length"]
            ],
            length=e["response_bytes"],
            expected_hash=bytes.fromhex(e["response_sha256"]),
        )
        policy = next(relation_rows(self.root, "retrieval_policy"))
        work = {"query_semantic_id": q.hex(), "result_limit": policy["result_limit"]}
        # Accepted successful artifacts have the frozen200/JSON/identity transport
        # contract; full reopening separately validates each selected attempt.
        projection = response.extract(
            raw,
            bytes.fromhex(e["request_execution_id"]),
            size=policy["result_limit"],
            http_status=200,
            content_type="application/json",
            encoding="identity",
            layers=self.rules.layers,
            sources=self.rules.sources,
            expected_echo=self.rules.expected_echo(work),
            expected_hash=bytes.fromhex(e["response_sha256"]),
        )
        return projection, raw

    def close(self):
        self.db.close()

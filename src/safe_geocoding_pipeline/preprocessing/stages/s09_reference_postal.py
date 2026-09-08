"""External exact GeoNames joins and streaming complete multi-witness sets.

All tables here except the final evidence/members are private operational
scratch. Their purpose is bounded-memory lookup reuse, not another source map.
No geographic association is joined across different GeoNames record IDs.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import duckdb

from . import s09_reference_contract as c
from . import s09_reference_evaluator as e
from . import s09_reference_io as io


REQUEST_SCHEMA = pa.schema(
    [
        pa.field("lookup_identity", pa.binary(32), nullable=False),
        pa.field("country", pa.large_string(), nullable=False),
        pa.field("question", pa.large_string(), nullable=False),
        pa.field("key1", pa.large_string(), nullable=False),
        pa.field("key2", pa.large_string()),
        pa.field(
            "draft",
            pa.struct(c.relation_schema("candidate_reference_evidence")),
            nullable=False,
        ),
    ]
)
_WITNESS_TYPE = c.relation_schema("reference_match_member").field("witness").type
CACHE_SCHEMA = pa.schema(
    [
        pa.field("lookup_identity", pa.binary(32), nullable=False),
        pa.field("witness_count", pa.uint64(), nullable=False),
        pa.field("single_witness", _WITNESS_TYPE),
        pa.field("match_set_id", pa.binary(32)),
    ]
)


def postal_request(
    prepared: e.PreparedEvaluation, *, profile: bytes, stage08_logical: bytes
) -> dict[str, Any]:
    c.require(
        prepared.reference == c.GN and prepared.unavailable_reason is None,
        "POSTAL_REQUEST_PREREQUISITES_FAILED",
    )
    lookup = e.lookup_identity(prepared, None)
    draft = e.evidence_row(
        prepared,
        e.LookupResult("NOT_EVALUABLE", "COMPONENT_CAPABILITY_MISSING"),
        profile=profile,
        stage08_logical=stage08_logical,
        lookup=lookup,
        witness_count=0,
        single_witness=None,
        match_set_id=None,
    )
    # draft is a private scheduling carrier, never a scientific output. Every
    # field describing the pending result is replaced after the complete join.
    return {
        "lookup_identity": lookup,
        "country": prepared.question.country,
        "question": prepared.question.question_id,
        "key1": prepared.keys[1],
        "key2": prepared.keys[2] if len(prepared.keys) > 2 else None,
        "draft": draft,
    }


def _postal_witness(row: Mapping[str, Any]) -> dict[str, Any]:
    object_id = row["reference_object_id"]
    return {
        "reference_object_id": object_id,
        "witness_role": "SUPPORT",
        "fields": [
            {"reference_object_id": object_id, "field_name": name, "ordinal": 0}
            for name in row["fields"]
        ],
    }


def _match_hasher(lookup: bytes, count: int) -> Any:
    digest = hashlib.sha256(struct.pack(">Q", 4))
    for item in ("SAFE_STAGE09", "V1", "MATCH_SET"):
        digest.update(c.framed(item))
    digest.update(b"\x05" + struct.pack(">Q", 2))
    digest.update(c.framed(lookup))
    digest.update(b"\x05" + struct.pack(">Q", count))
    return digest


def validate_full_lookup_keys(
    db: duckdb.DuckDBPyConnection, paths: Sequence[Path]
) -> None:
    """Guard digest equality against unequal full keys, including across shards."""
    collision = db.execute(
        "SELECT count(*) FROM (SELECT lookup_identity FROM ("
        "SELECT DISTINCT lookup_identity,country,question,key1,key2 FROM "
        + io.parquet_sql(paths)
        + ") GROUP BY lookup_identity HAVING count(*)<>1)"
    ).fetchone()
    c.require(collision == (0,), "LOOKUP_DIGEST_COLLISION_FULL_KEY_MISMATCH")


def resolve_postal_requests(
    request_paths: Sequence[Path],
    index_paths: Sequence[Path],
    work: Path,
    capabilities: Mapping[bytes, Mapping[str, Any]],
    *,
    memory: str = "8GB",
    threads: int = 4,
) -> tuple[list[Path], list[Path], dict[str, int]]:
    work.mkdir(mode=0o700)
    evidence_writer = io.RelationWriter(
        work / "evidence", c.relation_schema("candidate_reference_evidence")
    )
    member_writer = io.RelationWriter(
        work / "members", c.relation_schema("reference_match_member")
    )
    cache_writer = io.RelationWriter(work / "lookup_cache", CACHE_SCHEMA)
    with io.bounded_connection(
        work / "spill",
        memory=memory,
        threads=threads,
        database=work / "postal_work.duckdb",
    ) as db:
        db.execute(
            f"CREATE VIEW scheduled AS SELECT * FROM {io.parquet_sql(request_paths)}"
        )
        db.execute(f"CREATE VIEW postal AS SELECT * FROM {io.parquet_sql(index_paths)}")
        db.execute(
            "CREATE TABLE requests AS SELECT DISTINCT lookup_identity,country,question,key1,key2 FROM scheduled"
        )
        collision = db.execute(
            "SELECT count(*) FROM (SELECT lookup_identity FROM requests GROUP BY lookup_identity HAVING count(*)<>1)"
        ).fetchone()
        c.require(collision == (0,), "LOOKUP_DIGEST_COLLISION_FULL_KEY_MISMATCH")
        invalid = db.execute(
            "SELECT count(*) FROM requests WHERE question NOT IN ('Q05','Q06','Q07','Q09','Q10','Q11') OR key1='' OR (question IN ('Q06','Q07','Q11') AND (key2 IS NULL OR key2=''))"
        ).fetchone()
        c.require(invalid == (0,), "POSTAL_REQUEST_SCOPE_INVALID")
        admin_key = "CASE WHEN r.question IN ('Q07','Q11') THEN r.key2 ELSE r.key1 END"
        admin_match = (
            f"({admin_key}=g.admin1 OR {admin_key}=g.admin2 OR {admin_key}=g.admin3)"
        )
        conditions = {
            "Q05": "r.key1=g.postcode",
            "Q06": "r.key1=g.postcode AND r.key2=g.locality",
            "Q07": "r.key1=g.postcode AND " + admin_match,
            "Q09": "r.key1=g.locality",
            "Q10": admin_match,
            "Q11": "r.key1=g.locality AND " + admin_match,
        }
        branches = []
        for question, condition in conditions.items():
            fields = ["'country_code'"]
            if question in ("Q05", "Q06", "Q07"):
                fields.append("'postal_code'")
            if question in ("Q06", "Q09", "Q11"):
                fields.append("'place_name'")
            if question in ("Q07", "Q10", "Q11"):
                fields.extend(
                    f"CASE WHEN {admin_key}=g.admin{i} THEN 'admin_name{i}' ELSE NULL END"
                    for i in (1, 2, 3)
                )
            projection = (
                "SELECT r.lookup_identity,g.reference_object_id,list_sort(list_filter(["
                + ",".join(fields)
                + "], x -> x IS NOT NULL)) fields FROM requests r JOIN postal g ON r.country=g.country AND "
            )
            # Give each admin level an equality hash-join key. A country-only
            # join with an OR residual is quadratic for common admin names.
            # Project all matched field names in every branch, then collapse
            # exact duplicates when one record names the same admin twice.
            conditions_for_question = (
                [
                    condition.replace(admin_match, f"{admin_key}=g.admin{i}")
                    for i in (1, 2, 3)
                ]
                if question in ("Q07", "Q10", "Q11")
                else [condition]
            )
            for branch_condition in conditions_for_question:
                branches.append(
                    projection
                    + branch_condition
                    + " WHERE r.question="
                    + io.sql_literal(question)
                )
        db.execute(
            "CREATE TABLE matches AS SELECT DISTINCT * FROM ("
            + " UNION ALL ".join(branches)
            + ")"
        )
        c.require(
            db.execute(
                "SELECT count(*) FROM (SELECT lookup_identity,reference_object_id FROM matches GROUP BY ALL HAVING count(*)<>1)"
            ).fetchone()
            == (0,),
            "POSTAL_MATCH_OBJECT_KEY_COLLISION",
        )
        db.execute(
            "CREATE TABLE match_counts AS SELECT lookup_identity,count(*)::UBIGINT witness_count FROM matches GROUP BY lookup_identity"
        )
        current = None
        count = 0
        seen = 0
        digest = None
        single = None

        def finish() -> None:
            if current is not None:
                c.require(
                    seen == count and digest is not None,
                    "POSTAL_MATCH_TOTALITY_MISMATCH",
                )
                cache_writer.append(
                    {
                        "lookup_identity": current,
                        "witness_count": count,
                        "single_witness": single if count == 1 else None,
                        "match_set_id": digest.digest() if count > 1 else None,
                    }
                )

        query = "SELECT m.*,c.witness_count FROM matches m JOIN match_counts c USING(lookup_identity) ORDER BY lookup_identity,reference_object_id"
        for row in io.sorted_rows(db, query):
            if row["lookup_identity"] != current:
                finish()
                current, count, seen = row["lookup_identity"], row["witness_count"], 0
                digest = _match_hasher(current, count)
                single = None
            found = _postal_witness(row)
            assert digest is not None
            digest.update(c.framed(c.witness_tuple(found)))
            if count == 1:
                single = found
            seen += 1
        finish()
        cache_writer.close()
        db.execute(
            f"CREATE VIEW cache AS SELECT * FROM {io.parquet_sql(cache_writer.paths)}"
        )
        # Derive member ordinals only after complete-set identities exist. The
        # extra external pass avoids ever buffering a country-sized match set.
        query = "SELECT c.match_set_id,m.*,row_number() OVER(PARTITION BY m.lookup_identity ORDER BY m.reference_object_id)-1 AS member_ordinal FROM matches m JOIN cache c USING(lookup_identity) WHERE c.witness_count>1 ORDER BY m.lookup_identity,m.reference_object_id"
        for row in io.sorted_rows(db, query):
            member_writer.append(
                {
                    "match_set_id": row["match_set_id"],
                    "member_ordinal": row["member_ordinal"],
                    "witness": _postal_witness(row),
                }
            )
        db.execute(
            "CREATE TABLE recorded_postcodes AS SELECT DISTINCT country,postcode FROM postal WHERE postcode<>''"
        )
        db.execute(
            "CREATE TABLE result_cache AS SELECT r.lookup_identity,c.witness_count,c.single_witness,c.match_set_id, CASE WHEN c.witness_count>0 THEN 'SUPPORTED' ELSE 'NOT_FOUND' END result_state, CASE WHEN c.witness_count>0 THEN 'EXACT_REFERENCE_SUPPORT' WHEN r.question IN ('Q06','Q07') AND p.postcode IS NOT NULL THEN 'REFERENCE_ASSOCIATION_MISMATCH' WHEN r.question IN ('Q06','Q07','Q11') THEN 'RELATION_ABSENT_FROM_REFERENCE' ELSE 'VALUE_ABSENT_FROM_REFERENCE' END reason_code FROM requests r LEFT JOIN cache c USING(lookup_identity) LEFT JOIN recorded_postcodes p ON r.question IN ('Q06','Q07') AND p.country=r.country AND p.postcode=r.key1"
        )
        # This join shares cached lookup work, not evidence/source identities.
        query = "SELECT s.draft,r.* FROM scheduled s JOIN result_cache r USING(lookup_identity)"
        for row in io.sorted_rows(db, query):
            draft = row["draft"]
            c.require(
                draft["reference_slot"] == c.GN
                and draft["capability_id"] in capabilities,
                "POSTAL_DRAFT_BINDING_INVALID",
            )
            draft.update(
                result_state=row["result_state"],
                reason_code=row["reason_code"],
                witness_count=row["witness_count"] or 0,
                single_witness=row["single_witness"],
                match_set_id=row["match_set_id"],
            )
            c.validate_evidence_semantics(draft, capabilities[draft["capability_id"]])
            evidence_writer.append(draft)
        metrics = {}
        for metric, table in (
            ("scheduled", "scheduled"),
            ("distinct_lookups", "requests"),
            ("matched_public_records", "matches"),
        ):
            aggregate = db.execute(f"SELECT count(*) FROM {table}").fetchone()
            c.require(aggregate is not None, "POSTAL_AGGREGATE_MISSING")
            assert aggregate is not None
            metrics[metric] = int(aggregate[0])
        c.require(
            evidence_writer.rows == metrics["scheduled"],
            "POSTAL_EVIDENCE_TOTALITY_MISMATCH",
        )
    evidence_writer.close()
    member_writer.close()
    return evidence_writer.paths, member_writer.paths, metrics

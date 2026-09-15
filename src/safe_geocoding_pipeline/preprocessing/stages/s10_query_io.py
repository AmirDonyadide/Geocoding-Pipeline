"""Stage 10 schema constraints and bounded logical/physical artifact I/O."""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from . import s09_reference_io as upstream_io
from . import s09_reference_pack as pack
from . import s10_query_contract as c

MANIFEST_NAME = "stage10_query_manifest.json"
SUMMARY_NAME = "query_generation_summary.json"
SUCCESS_NAME = "_SUCCESS.json"
RelationWriter = upstream_io.RelationWriter
parquet_sql = upstream_io.parquet_sql
sql_literal = upstream_io.sql_literal
write_exclusive = upstream_io.write_exclusive
fsync_directory = upstream_io.fsync_directory


def write_json(path: Path, value: Any) -> None:
    write_exclusive(path, c.canonical(value))


def output_schema(name: str) -> Any:
    """Attach the frozen closed constraints to the physical Arrow schema."""
    base = c.schema(name)
    constraints = {
        "primary_key": c.PRIMARY_KEYS[name],
        "canonical_order": c.ORDER_KEYS[name],
        "unique_key": [
            "query_context_id",
            "representation_fingerprint" if name == "query_hypothesis" else "family",
        ],
        "upstream_occurrence_fk": ["stable_source_row_id_v1", "stage08_representation"],
        "candidate_fk": "stage06_exact_candidate_id",
        "membership_fk": ["query_context_id", "hypothesis_id"],
        "families": c.FAMILIES,
        "roles": c.ROLES,
        "eligibility": ["ELIGIBLE", "INELIGIBLE"],
        "membership": ["FIRST_MEMBER", "CONVERGENT_MEMBER", "NONE"],
        "field_disposition": ["INCLUDE", "OMIT", "NOT_APPLICABLE"],
        "reasons": c.REASONS,
        "selectors": c.SELECTORS,
        "list_bounds": {
            "reason_codes": 18,
            "lineage": 7,
            "transformations": 4,
            "field_decisions": 6,
            "removed_lines": 4,
        },
        "rank": [1, 5],
        "selection_status": c.MODE,
        "encoding": c.ENCODING,
        "design_package_sha256": c.DESIGN_PACKAGE_SHA256,
    }
    return base.with_metadata(
        {**base.metadata, b"stage10_constraints": c.canonical(constraints)}
    )


def arrow_value_chunks(value: Any, kind: Any) -> Iterator[bytes]:
    """Hash nested Arrow values without constructing giant Python component lists."""
    if not value.is_valid:
        yield from c.value_chunks(None)
    elif pa.types.is_struct(kind):
        yield b"\x05" + struct.pack(">Q", len(kind))
        for field in kind:
            yield from arrow_value_chunks(value[field.name], field.type)
    elif pa.types.is_list(kind) or pa.types.is_large_list(kind):
        values = value.values
        yield b"\x05" + struct.pack(">Q", len(values))
        for scalar in values:
            yield from arrow_value_chunks(scalar, kind.value_type)
    else:
        yield from c.value_chunks(value.as_py())


def arrow_row_chunks(batch: Any, ordinal: int) -> Iterator[bytes]:
    yield struct.pack(">Q", len(batch.schema))
    for index, field in enumerate(batch.schema):
        yield from arrow_value_chunks(batch.column(index)[ordinal], field.type)


def relation_fingerprint(
    name: str, count: int, rows: Iterable[Mapping[str, Any]]
) -> bytes:
    digest = hashlib.sha256(b"SAFE:stage10-relation:v1\0")
    for chunk in c.framed((c.schema_fingerprint(name), count)):
        digest.update(chunk)
    seen = 0
    previous: tuple[Any, ...] | None = None
    for row in rows:
        key = tuple(row[k] for k in c.ORDER_KEYS[name])
        c.require(
            previous is None or previous < key,
            "STAGE10_RELATION_ORDER_OR_DUPLICATE_INVALID",
        )
        previous = key
        for chunk in c.framed(c.ordered_values(row, output_schema(name))):
            digest.update(chunk)
        seen += 1
    c.require(seen == count, "STAGE10_RELATION_COUNT_MISMATCH")
    return digest.digest()


def validate_values(row: Mapping[str, Any], name: str) -> None:
    c.require(
        set(row) == set(c.schema(name).names), "STAGE10_COLUMN_ALLOWLIST_MISMATCH"
    )
    c.require(row["stage08_representation"] in c.ROLES, "STAGE10_ROLE_INVALID")
    for key in (
        "query_context_id",
        "stable_source_row_id_v1",
        "stage06_exact_candidate_id",
    ):
        c.require(
            isinstance(row[key], bytes) and len(row[key]) == 32,
            "STAGE10_ID_TYPE_INVALID",
        )
    if name == "query_hypothesis":
        c.validate_intent(row["intent"])
        c.require(
            row["representation_fingerprint"] == c.intent_fingerprint(row["intent"]),
            "STAGE10_INTENT_ID_MISMATCH",
        )
        c.require(
            1
            <= row["generation_rank"]
            <= c.ROLE_CEILINGS[row["stage08_representation"]]
            and row["selection_status"] == c.MODE,
            "STAGE10_RANK_OR_SELECTION_INVALID",
        )
        return
    family = row["family"]
    c.require(
        family in c.FAMILIES
        and row["eligibility_rule_id"] == f"stage10_q{family[1:]}_eligibility_v1",
        "STAGE10_FAMILY_RULE_INVALID",
    )
    eligible = row["eligibility_state"] == "ELIGIBLE"
    c.require(
        row["eligibility_state"] in ("ELIGIBLE", "INELIGIBLE"),
        "STAGE10_ELIGIBILITY_INVALID",
    )
    c.require(
        (
            eligible
            and row["membership_state"] in ("FIRST_MEMBER", "CONVERGENT_MEMBER")
            and isinstance(row["hypothesis_id"], bytes)
            and len(row["hypothesis_id"]) == 32
        )
        or (
            not eligible
            and row["membership_state"] == "NONE"
            and row["hypothesis_id"] is None
        ),
        "STAGE10_MEMBERSHIP_INVALID",
    )
    reasons = row["reason_codes"]
    c.require(
        len(reasons) <= 18
        and len(set(reasons)) == len(reasons)
        and all(v in c.REASONS and v != "QUERY_BUDGET_SUPPRESSION" for v in reasons)
        and row["primary_reason"] == (reasons[0] if reasons else None),
        "STAGE10_REASONS_INVALID",
    )
    if row["membership_state"] == "CONVERGENT_MEMBER":
        c.require(
            row["primary_reason"] == "EXACT_SEMANTIC_DUPLICATE",
            "STAGE10_CONVERGENCE_REASON_INVALID",
        )
    selectors = [v["selector_id"] for v in row["lineage"]]
    expected = [
        v
        for v in c.SELECTORS
        if v not in ("SOURCE_LINES_V1", "PARSER_COMPONENTS_V1")
        or (v == "SOURCE_LINES_V1" and family in ("Q3", "Q5"))
        or (v == "PARSER_COMPONENTS_V1" and family == "Q5")
    ]
    c.require(selectors == expected, "STAGE10_SELECTOR_MEMBERSHIP_INVALID")
    c.require(
        len(row["transformations"]) <= 4
        and [v["ordinal"] for v in row["transformations"]]
        == list(range(len(row["transformations"]))),
        "STAGE10_TRANSFORM_SEQUENCE_INVALID",
    )
    fields = row["field_decisions"]
    c.require(
        [v["field"] for v in fields]
        == (
            [
                "address",
                "postalcode",
                "locality",
                "region",
                "country",
                "boundary_country",
            ]
            if family == "Q4"
            else []
        ),
        "STAGE10_FIELD_DECISION_SLOTS_INVALID",
    )
    for field in fields:
        c.require(
            field["disposition"] in ("INCLUDE", "OMIT", "NOT_APPLICABLE")
            and len(set(field["reason_codes"])) == len(field["reason_codes"])
            and all(v in c.REASONS for v in field["reason_codes"]),
            "STAGE10_FIELD_DECISION_INVALID",
        )
    removed = row["removed_lines"]
    c.require(
        len(removed) <= 4 and (not removed or family == "Q5" and eligible),
        "STAGE10_REMOVAL_SCOPE_INVALID",
    )
    slots = [v["source_slot"] for v in removed]
    c.require(
        slots == sorted(set(slots)) and all(1 <= v <= 4 for v in slots),
        "STAGE10_REMOVAL_SLOTS_INVALID",
    )
    for value in removed:
        c.require(
            value["category"] in ("UNIT", "LEVEL")
            and value["start_codepoint"] < value["end_codepoint_exclusive"],
            "STAGE10_REMOVAL_INTERVAL_INVALID",
        )


def canonicalize(
    connection: duckdb.DuckDBPyConnection,
    name: str,
    paths: Sequence[Path],
    output: Path,
) -> dict[str, Any]:
    query = f"SELECT * FROM {parquet_sql(paths)} ORDER BY " + ",".join(
        c.ORDER_KEYS[name]
    )
    writer = RelationWriter(output, output_schema(name))
    for row in upstream_io.sorted_rows(connection, query, batch_rows=1):
        validate_values(row, name)
        writer.append(row)
    writer.close()
    logical = relation_fingerprint(
        name, writer.rows, upstream_io.parquet_rows(writer.paths, batch_rows=1)
    )
    return {
        "name": name,
        "row_count": writer.rows,
        "schema_sha256": c.schema_fingerprint(name).hex(),
        "logical_sha256": logical.hex(),
        "files": [
            {
                "relative_path": path.relative_to(output.parent).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": c.sha256_file(path),
            }
            for path in writer.paths
        ],
    }


def validate_relation(root: Path, record: Mapping[str, Any]) -> tuple[Path, ...]:
    name = record["name"]
    c.require(
        name in c.RELATIONS
        and record["schema_sha256"] == c.schema_fingerprint(name).hex(),
        "STAGE10_RELATION_SCHEMA_ID_MISMATCH",
    )
    paths = []
    for item in record["files"]:
        path = pack.confined(root, item["relative_path"])
        pack.regular_private(path)
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_ARTIFACT_BYTE_MISMATCH",
        )
        with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
            c.require(
                parquet.schema_arrow.equals(output_schema(name), check_metadata=True),
                "STAGE10_ARTIFACT_SCHEMA_MISMATCH",
            )
        paths.append(path)
    rows = upstream_io.parquet_rows(paths, batch_rows=1)

    def checked() -> Iterator[dict[str, Any]]:
        for row in rows:
            validate_values(row, name)
            yield row

    c.require(
        relation_fingerprint(name, record["row_count"], checked()).hex()
        == record["logical_sha256"],
        "STAGE10_ARTIFACT_LOGICAL_MISMATCH",
    )
    return tuple(paths)


def check_identity(
    row: Mapping[str, Any], name: str, upstream: bytes, inputs: bytes, science: bytes
) -> None:
    context = c.context_id(
        upstream, row["stable_source_row_id_v1"], row["stage08_representation"]
    )
    c.require(row["query_context_id"] == context, "STAGE10_CONTEXT_ID_MISMATCH")
    if name == "query_hypothesis":
        expected = c.identity(
            "stage10-hypothesis:v1",
            inputs,
            science,
            context,
            row["representation_fingerprint"],
        )
        c.require(row["hypothesis_id"] == expected, "STAGE10_HYPOTHESIS_ID_MISMATCH")
    else:
        expected = c.identity(
            "stage10-family-decision:v1", inputs, science, context, row["family"]
        )
        c.require(
            row["family_decision_id"] == expected, "STAGE10_FAMILY_DECISION_ID_MISMATCH"
        )


def profile_fingerprint(science: bytes) -> bytes:
    return c.identity(
        "stage10-profile:v1",
        c.PROFILE,
        science,
        c.budget_fingerprint(),
        c.POLICY,
        c.ENCODING,
    )


def dataset_fingerprint(
    inputs: bytes,
    science: bytes,
    relations: Sequence[Mapping[str, Any]],
    summary_sha256: bytes,
) -> bytes:
    c.require(
        tuple(r["name"] for r in relations) == tuple(c.RELATIONS),
        "STAGE10_DATASET_RELATION_ORDER_INVALID",
    )
    return c.identity(
        "stage10-dataset:v1",
        inputs,
        science,
        c.budget_fingerprint(),
        profile_fingerprint(science),
        c.schema_bundle_fingerprint(),
        tuple(
            (r["name"], bytes.fromhex(r["logical_sha256"]), r["row_count"])
            for r in relations
        ),
        summary_sha256,
    )

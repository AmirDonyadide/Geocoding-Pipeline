"""Invented full-schema upstream artifacts and exact context pipeline faults."""

from __future__ import annotations

from typing import Any

import copy
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s06_exact_deduplication as s6
from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s8
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as s9
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_input as a8
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as upstream_io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as contexts
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as families
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from test_stage09_reference_evaluator import (
    reference_view as reference_view,
    source as _source,
)
from test_stage10_query_evidence import fixture_rows
from test_stage10_query_families import SyntheticTransform


source: Any = _source


def complete(schema: Any, provided: Any) -> Any:
    def value(field: Any, supplied: Any) -> Any:
        if supplied is None and field.nullable:
            return None
        kind = field.type
        if pa.types.is_struct(kind):
            return complete(kind, supplied or {})
        if pa.types.is_list(kind) or pa.types.is_large_list(kind):
            return [value(kind.value_field, item) for item in supplied or []]
        if supplied is not None:
            return supplied
        if pa.types.is_boolean(kind):
            return False
        if pa.types.is_integer(kind):
            return 0
        if pa.types.is_fixed_size_binary(kind):
            return b"0" * kind.byte_width
        return ""

    return {field.name: value(field, provided.get(field.name)) for field in schema}


@pytest.fixture
def synthetic_inputs(reference_view: Any, tmp_path: Any, request: Any) -> Any:
    root = tmp_path / "invented-upstream"
    root.mkdir(mode=0o700)
    text = "12 α road unit 5"
    candidate_id = s6.exact_candidate_id_v1(text)
    components = [
        {"label": label, "value": value}
        for label, value in (
            ("house_number", "12"),
            ("road", "α road"),
            ("unit", "unit 5"),
        )
    ]
    same_country = getattr(request, "param", False)
    candidate = complete(
        s8.candidate_evidence_schema(),
        {
            "stage06_exact_candidate_id": candidate_id,
            "stage06_candidate_lower": text,
            "stage06_occurrence_count": 4,
            "stage06_standard_occurrence_count": 2,
            "stage06_native_occurrence_count": 2,
            "stage07_trusted_country_iso_code": "US" if same_country else None,
            "stage07_country_provenance_status": "COUNTRY_UNANIMOUS_VALID"
            if same_country
            else "COUNTRY_CONFLICT",
            "stage07_parse_status": "PARSED_NONEMPTY",
            "stage07_libpostal_components": components,
            "stage08_raw_component_count": 3,
            "stage08_mapped_component_count": 3,
        },
    )
    sources, lines, evidence_rows = [], [], []
    objects = dict(reference_view.objects)
    members = {}
    for index, country in enumerate(("US", "US" if same_country else "DE", "US")):
        present = index < 2
        row = {
            **source(),
            "stable_source_row_id_v1": bytes([index + 1]) * 32,
            "stage03_clean_country_iso_code": country,
            "stage08_source_row_ordinal": index,
        }
        for role in c.ROLES:
            row[f"stage06_{role.lower()}_exact_candidate_id"] = (
                candidate_id if present else None
            )
            row[f"stage08_{role.lower()}_representation_status"] = (
                "PRESENT" if present else "UNAVAILABLE"
            )
        for field in ("city", "postcode", "region_in_country", "country_iso_code"):
            row[f"stage04_lower_{field}"] = row[f"stage03_clean_{field}"].lower()
        row = complete(s8.source_candidate_map_schema(), row)
        sources.append(row)
        source_lines = (
            ("12 α road", "unit 5", "", "")
            if index == 0
            else ("12 α", "road", "unit 5", "")
            if present
            else ("", "", "", "")
        )
        line_row = {"stable_source_row_id_v1": row["stable_source_row_id_v1"]}
        for role in c.ROLES:
            line_row.update(
                zip(
                    inputs.source_line_fields(role),
                    (
                        candidate_id if present else None,
                        *source_lines,
                        text if present else "",
                        present,
                        sum(bool(x) for x in source_lines),
                        "".join("1" if x else "0" for x in source_lines),
                    ),
                    strict=True,
                )
            )
        lines.append(complete(inputs.row_projection_schema(), line_row))
        if present:
            _, _, checks, access = fixture_rows(reference_view, row=row, cand=candidate)
            evidence_rows.extend(checks)
            objects.update(access.objects)
            for identifier, witnesses in access.members.items():
                for ordinal, witness in enumerate(witnesses):
                    members[(identifier, ordinal)] = {
                        "match_set_id": identifier,
                        "member_ordinal": ordinal,
                        "witness": witness,
                    }
    component_rows = [
        complete(
            s8.parser_component_evidence_schema(),
            {
                "stage06_exact_candidate_id": candidate_id,
                "stage08_component_ordinal": ordinal,
                "stage08_raw_libpostal_label": item["label"],
                "stage08_raw_libpostal_value": item["value"],
                "stage08_label_mapping_status": "MAPPED",
                "stage08_safe_parser_evidence_component": "PARSER_"
                + item["label"].upper(),
                "stage08_evidence_class": "PARSER_EVIDENCE",
            },
        )
        for ordinal, item in enumerate(components)
    ]
    records = {
        "candidate_evidence": [candidate],
        "parser_component_evidence": component_rows,
        "source_candidate_map": sources,
        "stage06_row_map": lines,
        "candidate_reference_evidence": evidence_rows,
        "reference_match_member": list(members.values()),
        "reference_object": list(objects.values()),
        "reference_capability": list(reference_view.capabilities.values()),
        "reference_registry": list(reference_view.registry.values()),
    }
    paths = {}
    for name, values in records.items():
        schema = (
            inputs.STAGE08_SCHEMAS[name]
            if name in inputs.STAGE08_SCHEMAS
            else inputs.row_projection_schema()
            if name == "stage06_row_map"
            else s9.relation_schema(name)
        )
        directory = root / name
        directory.mkdir(mode=0o700)
        path = directory / "synthetic.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [complete(schema, row) for row in values], schema=schema
            ),
            path,
        )
        path.chmod(0o600)
        paths[name] = (path,)
    accepted = a8.AcceptedStage08(
        root,
        {},
        {name: paths[name] for name in inputs.STAGE08_SCHEMAS},
        {"SYNTHETIC_ONLY": True},
    )
    return inputs.AcceptedInputs(accepted, {}, {}, {}, paths, {"SYNTHETIC_ONLY": True})


@pytest.fixture
def workspace(synthetic_inputs: Any, tmp_path: Any) -> Any:
    work = contexts.ContextWorkspace(
        synthetic_inputs, tmp_path / "private-work", b"s" * 32
    )
    try:
        work.prepare()
        yield work
    finally:
        work.close()


def test_occurrence_pipeline_country_boundary_mapback(workspace: Any) -> None:
    emitted = []
    contexts_seen = []
    for context in workspace.contexts():
        contexts_seen.append(
            (
                context.source_id,
                context.role,
                context.identifier,
                context.fields.country,
            )
        )
        hypotheses, decisions = families.generate(context, SyntheticTransform())
        assert len(decisions) == 6
        for row in hypotheses:
            io.validate_values(row, "query_hypothesis")
            io.check_identity(
                row,
                "query_hypothesis",
                context.upstream_identity,
                context.input_identity,
                context.science_identity,
            )
        for row in decisions:
            io.validate_values(row, "query_family_decision")
            io.check_identity(
                row,
                "query_family_decision",
                context.upstream_identity,
                context.input_identity,
                context.science_identity,
            )
        assert all(
            row["query_context_id"] == context.identifier
            for row in hypotheses + decisions
        )
        emitted.extend(hypotheses)
    assert len(contexts_seen) == len({x[2] for x in contexts_seen}) == 4
    assert {x[3] for x in contexts_seen} == {"US", "DE"}
    assert len(emitted) == 14
    assert sorted(
        sum(r["stable_source_row_id_v1"] == bytes([i]) * 32 for r in emitted)
        for i in (1, 2)
    ) == [7, 7]
    assert len({r["stage06_exact_candidate_id"] for r in emitted}) == 1
    assert (
        len(
            {
                r["intent"]["text"]
                for r in emitted
                if r["intent"]["text"] is not None and "\n" in r["intent"]["text"]
            }
        )
        == 2
    )


def test_arrow_selector_encoding_preserves_nested_order_without_python_lists() -> None:
    schema = pa.schema(
        [
            pa.field(
                "nested",
                pa.large_list(pa.struct([pa.field("value", pa.large_string())])),
            ),
            pa.field("optional", pa.large_string()),
        ]
    )
    row: dict[str, Any] = {
        "nested": [{"value": "α"}, {"value": "α"}, {"value": ""}],
        "optional": None,
    }
    batch = pa.RecordBatch.from_pylist([row], schema=schema)
    assert b"".join(io.arrow_row_chunks(batch, 0)) == contexts.encoded(
        c.ordered_values(row, schema)
    )
    changed = pa.RecordBatch.from_pylist(
        [{**row, "nested": list(reversed(row["nested"]))}], schema=schema
    )
    assert (
        hashlib.sha256(b"".join(io.arrow_row_chunks(changed, 0))).digest()
        != hashlib.sha256(b"".join(io.arrow_row_chunks(batch, 0))).digest()
    )


@pytest.mark.parametrize("fault", ["ordinal", "source_slot", "country_context"])
def test_workspace_corruption_fails_without_protected_values(
    workspace: Any, fault: Any
) -> None:
    if fault == "ordinal":
        workspace.db.execute(
            "UPDATE stage10_components SET stage08_component_ordinal=9 WHERE stage08_component_ordinal=2"
        )
    elif fault == "source_slot":
        workspace.db.execute(
            "UPDATE stage10_lines SET stage05_native_candidate_lower='invented-corruption'"
        )
    else:
        workspace.db.execute(
            "UPDATE stage10_sources SET stage03_clean_country_iso_code='JP'"
        )
    with pytest.raises(c.Stage10Error) as raised:
        for context in workspace.contexts():
            families.generate(context, SyntheticTransform())
    assert "invented-corruption" not in str(raised.value)


def test_io_roundtrip_and_duplicate_rejection(workspace: Any, tmp_path: Any) -> None:
    rows = []
    for context in workspace.contexts():
        rows.extend(families.generate(context, SyntheticTransform())[0])
    writer = io.RelationWriter(
        tmp_path / "unordered", io.output_schema("query_hypothesis")
    )
    for row in reversed(rows):
        writer.append(row)
    writer.close()
    output = tmp_path / "artifact"
    output.mkdir()
    record = io.canonicalize(
        workspace.db, "query_hypothesis", writer.paths, output / "query_hypothesis"
    )
    assert record["row_count"] == 14
    paths = io.validate_relation(output, record)
    ordered = list(upstream_io.parquet_rows(paths))
    with pytest.raises(c.Stage10Error, match="ORDER_OR_DUPLICATE"):
        io.relation_fingerprint("query_hypothesis", 15, [ordered[0], *ordered])
    altered = copy.deepcopy(record)
    altered["files"][0]["sha256"] = "0" * 64
    with pytest.raises(c.Stage10Error, match="BYTE_MISMATCH"):
        io.validate_relation(output, altered)


@pytest.mark.parametrize("synthetic_inputs", [True], indirect=True)
def test_context_pipeline_reaches_four_standard_five_native(workspace: Any) -> None:
    maxima: dict[str, int] = {}
    source_totals: dict[bytes, int] = {}
    for context in workspace.contexts():
        hypotheses, decisions = families.generate(context, SyntheticTransform())
        assert len(decisions) == 6
        maxima[context.role] = max(maxima.get(context.role, 0), len(hypotheses))
        source_totals[context.source_id] = source_totals.get(
            context.source_id, 0
        ) + len(hypotheses)
    assert maxima == {"STANDARD": 4, "NATIVE": 5}
    assert set(source_totals.values()) == {9}


def test_reference_certificate_observes_transaction_and_exact_sections(
    synthetic_inputs: Any, tmp_path: Any
) -> None:
    work = contexts.ContextWorkspace(
        synthetic_inputs, tmp_path / "witness-work", b"s" * 32
    )
    work.prepare()
    try:
        ctx = next(work.contexts())
        rows = list(
            contexts.sql_rows(
                work.db,
                "SELECT * FROM stage10_source_reference WHERE stable_source_row_id_v1=? AND stage06_exact_candidate_id=? ORDER BY evidence_id",
                [ctx.source_id, ctx.candidate_id],
            )
        )
        selected = {}
        access = work.reference
        assert access is not None

        def select(section: Any, key: Any, values: Any) -> Any:
            selected[(section, key)] = contexts.encoded(values)

        def registry(key: Any) -> Any:
            select(
                4,
                key,
                c.ordered_values(
                    access.registry(key), s9.relation_schema("reference_registry")
                ),
            )

        def obj(key: Any) -> Any:
            record = access.object(key)
            select(
                2, key, c.ordered_values(record, s9.relation_schema("reference_object"))
            )
            registry(record["reference_version_id"])
            if record["explicit_parent_id"] is not None:
                obj(record["explicit_parent_id"])

        for row in rows:
            if row["reference_version_id"] is not None:
                registry(row["reference_version_id"])
            for field in ("capability_id", "rule_capability_id"):
                if row[field] is not None:
                    select(
                        3,
                        row[field],
                        c.ordered_values(
                            access.capability(row[field]),
                            s9.relation_schema("reference_capability"),
                        ),
                    )
            if row["single_witness"] is not None:
                v = s9.witness_tuple(row["single_witness"])
                select(0, contexts.encoded(v), v)
            if row["match_set_id"] is not None:
                for member in access.members(row["match_set_id"]):
                    select(
                        1,
                        contexts.encoded(
                            (member["match_set_id"], member["member_ordinal"])
                        ),
                        c.ordered_values(
                            member, s9.relation_schema("reference_match_member")
                        ),
                    )
            for witness in access.witnesses(row):
                obj(witness["reference_object_id"])
                for pointer in witness["fields"]:
                    obj(pointer["reference_object_id"])
        digest = hashlib.sha256()
        for (section, key), payload in sorted(selected.items()):
            digest.update(contexts.encoded((section,)))
            digest.update(payload)
        actual = ctx.certificates["REFERENCE_WITNESSES_V1"]
        assert actual["selected_count"] == len(selected) > 10
        assert actual["selected_stream_sha256"] == digest.digest()
        # Cached certificate retains the same complete evidence selection.
        assert access.witness_certificate(rows) == actual
    finally:
        work.close()


def test_cache_has_fixed_byte_and_entry_ceilings() -> None:
    cache = contexts.ByteCache(8192)
    for i in range(10000):
        cache.put(i.to_bytes(4, "big"), {"invented": i}, 128)
        assert cache.size <= 8192 and len(cache.items) <= 256
    cache.put(b"oversize", "unused", 8193)
    assert cache.get(b"oversize") is None


def test_nested_arrow_certificate_handles_large_component_list() -> None:
    rows = [{"value": "invented", "ordinal": i} for i in range(20000)]
    schema = pa.schema(
        [
            pa.field(
                "components",
                pa.large_list(
                    pa.struct([("value", pa.string()), ("ordinal", pa.uint64())])
                ),
            )
        ]
    )
    batch = pa.RecordBatch.from_pylist([{"components": rows}], schema=schema)
    expected = hashlib.sha256(
        b"".join(c.framed((tuple(("invented", i) for i in range(20000)),)))
    ).digest()
    digest = hashlib.sha256()
    for chunk in io.arrow_row_chunks(batch, 0):
        digest.update(chunk)
    assert digest.digest() == expected

"""Canonical reference material is prepared once; witness multiplicity adds no SQL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_reference_store as store
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs


def test_prepared_and_legacy_certificates_identical_without_lookup_sql(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    try:
        legacy = cx.ReferenceAccess(work.db, work.root)
        prepared = work.reference
        assert prepared is not None
        rows = list(
            cx.sql_rows(
                work.db, "SELECT * FROM stage10_source_reference ORDER BY evidence_id"
            )
        )
        # Eviction cannot reintroduce per-component SQL or canonical encoding.
        prepared.cache = cx.ByteCache(1)
        before = work.progress.timings["database_execute"]["calls"]
        registry_count = work.progress.counts["reference_registry_encodes"]
        outputs = []
        for n in (1, 10, 100):
            prepared.certificates = cx.ByteCache(1)
            outputs.append(prepared.witness_certificate(rows * n))
        assert outputs[0] == outputs[1] == outputs[2]
        assert work.progress.timings["database_execute"]["calls"] == before
        assert work.progress.counts["reference_registry_encodes"] == registry_count
        assert outputs[0] == legacy.witness_certificate(rows)
        # Different witness subsets use complete keys, even after eviction.
        for row in rows:
            assert prepared.witness_certificate([row]) == legacy.witness_certificate(
                [row]
            )
    finally:
        work.close()


def test_all_material_roundtrips_and_malformed_framing_rejected(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    try:
        for lookup in work.reference_store.lookups.values():
            for ordinal in range(lookup.count):
                row, payload = lookup.material(ordinal)
                assert cx.encoded(c.ordered_values(row, lookup.schema)) == payload
                with pytest.raises(c.Stage10Error, match="CACHE_FRAME"):
                    store.decode(payload[:-1], lookup.schema)
        ref = work.reference
        assert ref is not None
        identifier = next(
            cx.sql_rows(work.db, "SELECT reference_version_id FROM stage10_registry")
        )["reference_version_id"]
        before = ref.registry(identifier)
        work.db.execute(
            "UPDATE stage10_registry SET dataset_name='invented changed registry' WHERE reference_version_id=?",
            [identifier],
        )
        after = ref.registry(identifier)
        assert before != after
        assert after["dataset_name"] == "invented changed registry"
    finally:
        work.close()


def test_member_stream_scales_without_sql_and_keeps_exact_certificate(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    import pyarrow as pa
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_contract as s9,
    )

    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "members", b"s" * 32)
    work.prepare()
    try:
        row = next(
            cx.sql_rows(
                work.db,
                "SELECT * FROM stage10_source_reference WHERE single_witness IS NOT NULL LIMIT 1",
            )
        )
        for count in (2, 2000):
            identifier = bytes([count % 251]) * 32
            members = [
                {
                    "match_set_id": identifier,
                    "member_ordinal": n,
                    "witness": row["single_witness"],
                }
                for n in range(count)
            ]
            work.db.register(
                "invented_members",
                pa.Table.from_pylist(
                    members, schema=s9.relation_schema("reference_match_member")
                ),
            )
            work.db.execute("DELETE FROM stage10_members")
            work.db.execute(
                "INSERT INTO stage10_members SELECT * FROM invented_members"
            )
            work.db.unregister("invented_members")
            work.reference_store.prepare()
            selected = [
                {
                    **row,
                    "single_witness": None,
                    "match_set_id": identifier,
                    "witness_count": count,
                }
            ]
            legacy = cx.ReferenceAccess(work.db, work.root)
            expected = legacy.witness_certificate(selected)
            prepared = work.reference
            assert prepared is not None
            before = work.progress.timings["database_execute"]["calls"]
            assert prepared.witness_certificate(selected) == expected
            # Large selectors may require one external sort, independent of members.
            statements = work.progress.timings["database_execute"]["calls"] - before
            assert statements <= 1
    finally:
        work.close()


def test_parser_component_growth_has_constant_sql_per_context(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    import dataclasses
    from functools import partial
    import pyarrow as pa
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_families as families,
    )
    from test_stage10_query_families import context, SyntheticTransform

    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "parser", b"s" * 32)
    work.prepare()
    try:
        base = next(cx.sql_rows(work.db, "SELECT * FROM stage10_components LIMIT 1"))
        candidate = base["stage06_exact_candidate_id"]
        for count in (3, 3000):
            values = [
                {
                    **base,
                    "stage08_component_ordinal": n,
                    "stage08_raw_libpostal_value": "invented",
                }
                for n in range(count)
            ]
            work.db.register(
                "invented_components",
                pa.Table.from_pylist(values, schema=cx.component_schema()),
            )
            work.db.execute("DELETE FROM stage10_components")
            work.db.execute(
                "INSERT INTO stage10_components SELECT * FROM invented_components"
            )
            work.db.unregister("invented_components")
            work.component_cache = cx.ByteCache(1)
            ctx = dataclasses.replace(
                context(tmp_path),
                components=partial(work.components, candidate),
                component_count=count,
            )
            before = work.progress.timings["database_execute"]["calls"]
            _, decisions = families.generate(ctx, SyntheticTransform())
            assert len(decisions) == 6
            assert work.progress.timings["database_execute"]["calls"] - before <= 2
    finally:
        work.close()

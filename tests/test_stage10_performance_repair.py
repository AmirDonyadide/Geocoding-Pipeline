"""Old/new scientific equality and algorithmic performance guards, invented data."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s8
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_input as a8
from safe_geocoding_pipeline.preprocessing.stages import s10_query_checkpoints as units
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_materializer as m
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_query_families import SyntheticTransform
from test_stage10_review_remediation import prior_scientific_projection

ORIGINAL = "f83480d60449bcc904c0c622e394e12df3c3f2d9"


def original_module(name: str, root: Path) -> Any:
    relative = f"src/safe_geocoding_pipeline/preprocessing/stages/{name}.py"
    raw = subprocess.check_output(["git", "show", f"{ORIGINAL}:{relative}"])
    inventory = json.loads(
        subprocess.check_output(
            [
                "git",
                "show",
                f"{ORIGINAL}:docs/scientific_assets/stage10_implementation_inventory_v1.json",
            ]
        )
    )
    assert hashlib.sha256(raw).hexdigest() == next(
        item["sha256"] for item in inventory["files"] if item["path"] == relative
    )
    path = root / (name + ".py")
    path.write_bytes(raw)
    module_name = "safe_geocoding_pipeline.preprocessing.stages._original_" + name
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def colliding_fixture() -> dict[str, Any]:
    binding = c.identity(
        "stage10-context-input:v1",
        bytes.fromhex(a8.STAGE08_MANIFEST_SHA256),
        bytes.fromhex(inputs.STAGE06_MANIFEST),
        bytes.fromhex(inputs.STAGE09_MANIFEST),
    )
    sources = []
    for number in range(10000):
        source = hashlib.sha256(f"invented source {number}".encode()).digest()
        if all(
            c.context_id(binding, source, role).hex().startswith("0")
            for role in c.ROLES
        ):
            sources.append(source)
        if len(sources) == 2:
            break
    assert len(sources) == 2
    return {"same_country": True, "source_ids": [*sources, b"z" * 32]}


COLLIDING = colliding_fixture()


@pytest.mark.parametrize("synthetic_inputs", [False, True], indirect=True)
@pytest.mark.parametrize("page_rows", [1, 2, 64])
def test_original_and_repaired_complete_rows_are_identical(
    synthetic_inputs: Any, tmp_path: Path, page_rows: int
) -> None:
    old = original_module("s10_query_contexts", tmp_path)
    old_family = original_module("s10_query_families", tmp_path)
    old.families = old_family
    runtime = SyntheticTransform()
    before = old.ContextWorkspace(synthetic_inputs, tmp_path / "old", b"s" * 32)
    after = cx.ContextWorkspace(synthetic_inputs, tmp_path / "repaired", b"s" * 32)
    try:
        before.prepare()
        after.prepare()
        expected = [old_family.generate(ctx, runtime) for ctx in before.contexts()]
        observed = [
            prior_scientific_projection(f.generate(ctx, runtime))
            for ctx in after.contexts(page_rows=page_rows)
        ]
        assert (
            observed == expected
        )  # includes payloads, every selector, reason, ID, membership
        for slot, name in enumerate(c.RELATIONS):
            rows = [row for pair in expected for row in pair[slot]]
            actual = [row for pair in observed for row in pair[slot]]
            assert io.relation_fingerprint(
                name, len(rows), rows
            ) == io.relation_fingerprint(name, len(actual), actual)
        count = after.db.execute(
            "SELECT count(*) FROM stage10_context_diagnostics"
        ).fetchone()
        assert count is not None and count[0] == 4
        assert after.progress.observe_wal(after.root / "context.duckdb") == 0
    finally:
        before.close()
        after.close()


@pytest.mark.parametrize("limit", [64, 2 * 1024 * 1024])
def test_selector_spill_and_memory_have_exact_old_stream(
    limit: int, tmp_path: Path
) -> None:
    old = original_module("s10_query_contexts", tmp_path)
    db = duckdb.connect()
    selected = ops.SelectorAccumulator(db, tmp_path, limit)
    rows = [
        (4, b"registry", ("invented", ["one", "two"])),
        (0, b"witness", (b"opaque",)),
        (2, b"object", ("Greek α", 7)),
    ]
    try:
        for section, key, values in rows * 3:
            selected.add(section, key, cx.encoded(values))
        digest = hashlib.sha256()
        for section, _, values in sorted(rows):
            digest.update(old.encoded((section,)))
            digest.update(old.encoded(values))
        assert selected.certificate() == {
            "selector_id": "REFERENCE_WITNESSES_V1",
            "selected_count": 3,
            "selected_stream_sha256": digest.digest(),
        }
        assert selected.size <= limit
    finally:
        selected.close()
        db.close()


@pytest.mark.parametrize("limit", [64, 1024 * 1024])
def test_selector_collision_never_hidden_by_dedup_or_spill(
    limit: int, tmp_path: Path
) -> None:
    db = duckdb.connect()
    selected = ops.SelectorAccumulator(db, tmp_path, limit)
    try:
        with pytest.raises(c.Stage10Error, match="SELECTOR_ID_COLLISION"):
            selected.add(4, b"same", b"invented A")
            selected.add(4, b"same", b"invented B")
            selected.certificate()
    finally:
        selected.close()
        db.close()


def test_registry_encoded_once_and_no_selector_sql_writes(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    ref = work.reference
    assert ref is not None
    record = work.db.execute(
        "SELECT reference_version_id FROM stage10_registry LIMIT 1"
    ).fetchone()
    assert record is not None
    identifier = record[0]
    ref.selection = ops.SelectorAccumulator(work.db, work.root)
    calls = 0
    original = cx.encoded

    def measured(values: Any) -> bytes:
        nonlocal calls
        calls += 1
        return original(values)

    monkeypatch.setattr(cx, "encoded", measured)
    before = work.progress.timings["database_execute"]["calls"]
    try:
        for _ in range(100):
            ref._select_registry(identifier)
        assert calls == 0  # Canonical bytes were prepared once, before contexts.
        assert work.progress.timings["database_execute"]["calls"] - before == 0
        assert work.progress.counts["reference_registry_encodes"] == 3
        assert ref.selection.certificate()["selected_count"] == 1
        assert work.progress.observe_wal(work.root / "context.duckdb") == 0
    finally:
        ref.selection.close()
        ref.selection = None
        work.close()


def test_registry_eviction_recomputes_exact_material(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "work", b"s" * 32)
    work.prepare()
    ref = work.reference
    assert ref is not None
    record = work.db.execute(
        "SELECT reference_version_id FROM stage10_registry LIMIT 1"
    ).fetchone()
    assert record is not None
    identifier = record[0]
    expected = ref._material("registry", "reference_version_id", identifier)
    ref.cache = cx.ByteCache(1)
    assert ref._material("registry", "reference_version_id", identifier) == expected
    assert not ref.cache.items
    work.close()


def test_context_pages_do_not_repeat_upstream_join(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "indexed", b"s" * 32)
    work.prepare()
    queries = []
    execute = ops.TimedConnection.execute

    def traced(self: Any, query: str, parameters: Any = None) -> Any:
        queries.append(query)
        return execute(self, query, parameters)

    monkeypatch.setattr(ops.TimedConnection, "execute", traced)
    try:
        rows = list(work.context_rows(page_rows=1))
        assert len(rows) == 4 and len(queries) == 5
        assert all(
            "FROM stage10_generation_contexts" in q and "JOIN" not in q for q in queries
        )
        assert work.progress.timings["context_index_preparation"]["calls"] == 1
    finally:
        work.close()


def test_large_parser_certificate_matches_original_once(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    old = original_module("s10_query_contexts", tmp_path)
    before = old.ContextWorkspace(synthetic_inputs, tmp_path / "old", b"s" * 32)
    after = cx.ContextWorkspace(synthetic_inputs, tmp_path / "new", b"s" * 32)
    before.prepare()
    after.prepare()
    schema = cx.component_schema()
    base_row = next(cx.sql_rows(after.db, "SELECT * FROM stage10_components LIMIT 1"))
    rows = [
        {
            **base_row,
            "stage08_component_ordinal": n,
            "stage08_raw_libpostal_value": f"invented {n}",
        }
        for n in range(10000)
    ]
    for work in (before, after):
        work.db.execute("DELETE FROM stage10_components")
        work.db.register(
            "invented_components", pa.Table.from_pylist(rows, schema=schema)
        )
        work.db.execute(
            "INSERT INTO stage10_components SELECT * FROM invented_components"
        )
        work.db.unregister("invented_components")
        work.db.execute(
            "UPDATE stage10_candidates SET stage08_raw_component_count=10000"
        )
    expected = before.parser_certificate(base_row["stage06_exact_candidate_id"])
    after.db.execute("DROP TABLE stage10_parser_certificates")
    shutil.rmtree(after.root / "parser_certificates")  # generated invented fixture only
    cx.component_schema.cache_clear()
    factory, calls = s8.parser_component_evidence_schema, 0

    def measured() -> Any:
        nonlocal calls
        calls += 1
        return factory()

    monkeypatch.setattr(s8, "parser_component_evidence_schema", measured)
    after.prepare_parser_certificates()
    assert after.parser_certificate(base_row["stage06_exact_candidate_id"]) == expected
    assert expected["selected_count"] == 10000 and calls == 1
    before.close()
    after.close()


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_checkpoint_partition_and_page_sizes_do_not_change_relations(
    synthetic_inputs: Any, tmp_path: Path
) -> None:
    records = []
    for limit in (1, 2, 64):
        work = cx.ContextWorkspace(
            synthetic_inputs, tmp_path / f"work-{limit}", b"s" * 32
        )
        work.prepare()
        try:
            records.append(
                m.generate_catalog(
                    work, SyntheticTransform(), "a" * 40, unit_contexts=limit
                )
            )
            prefix = m.validate_checkpoint(
                work.root / "shards/0", m.checkpoint_binding(work, "a" * 40), "0"
            )
            assert prefix["context_count"] == 4
            assert prefix["unit_count"] == (4 + limit - 1) // limit
            for record in units.index_rows(work.root / "shards/0"):
                unit = work.root / "shards/0/units" / f"{record['ordinal']:06}"
                assert (
                    len(
                        units.validate_unit(
                            unit, m.checkpoint_binding(work, "a" * 40), "0"
                        )["context_ids"]
                    )
                    <= limit
                )
        finally:
            work.close()
    assert len({tuple(r["logical_sha256"] for r in result) for result in records}) == 1


@pytest.mark.parametrize("synthetic_inputs", [COLLIDING], indirect=True)
def test_resume_reuses_complete_units_and_regenerates_incomplete(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    work = cx.ContextWorkspace(synthetic_inputs, tmp_path / "interrupted", b"s" * 32)
    work.prepare()
    original, calls = f.generate, 0

    def interrupted(context: Any, runtime: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise c.Stage10Error("SYNTHETIC_INTERRUPTION")
        return original(context, runtime)

    with monkeypatch.context() as patch:
        patch.setattr(f, "generate", interrupted)
        with pytest.raises(c.Stage10Error, match="SYNTHETIC_INTERRUPTION"):
            m.generate_catalog(work, SyntheticTransform(), "a" * 40, unit_contexts=1)
    first = work.root / "shards/0/units/000000/checkpoint.json"
    digest = c.sha256_file(first)
    assert not (work.root / "shards/0/checkpoint.json").exists()
    assert not (work.root / "shards/0/units/000002/checkpoint.json").exists()
    resumed = cx.ContextWorkspace(synthetic_inputs, tmp_path / "resumed", b"s" * 32)
    resumed.prepare()
    records = m.generate_catalog(
        resumed,
        SyntheticTransform(),
        "a" * 40,
        unit_contexts=1,
        resume=work.root / "shards",
    )
    assert resumed.progress.counts["checkpoints_reused"] == 2
    assert resumed.progress.counts["contexts_completed"] == 4
    assert [r["row_count"] for r in records] == [18, 24]
    assert c.sha256_file(first) == digest
    m.replay(resumed, SyntheticTransform())
    work.close()
    resumed.close()


def test_progress_contains_only_aggregate_fixed_fields(tmp_path: Path) -> None:
    progress = ops.Progress(tmp_path / "progress")
    progress.counts["contexts_completed"] = 3
    with progress.measure("Q5"):
        pass
    progress.record()
    report = c.read_json(tmp_path / "progress/progress-000000.json")
    assert report["counts"]["contexts_completed"] == 3
    assert report["timings_inclusive"]["Q5"]["calls"] == 1
    assert not any(
        key in c.canonical(report)
        for key in (b"query_text", b"query_context_id", b"source_id", b"parameters")
    )


def test_operational_bounds_fail_without_suppressing_families() -> None:
    with pytest.raises(c.Stage10Error, match="BUFFER_INVALID"):
        ops.SelectorAccumulator(None, None, 0)
    with pytest.raises(c.Stage10Error, match="SIZE_INVALID"):
        units.key_window(None, "0", None, 65)

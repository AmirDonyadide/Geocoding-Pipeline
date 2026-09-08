"""Optional local public-asset checks; never a protected-input test."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_evaluator as e
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_pack as p


@pytest.fixture(scope="module")
def public_inputs():
    repository = Path(__file__).resolve().parents[1]
    root = repository / "external_data/stage09_reference_freeze_v1"
    if not root.is_dir():
        pytest.skip(
            "Exact optional public reference assets not present; no download attempted"
        )
    lock = p.verify_lock(
        root, repository / "docs/scientific_assets/stage09_reference_pack_lock_v1.json"
    )
    return p.PublicInputs(root, lock, p.registry_rows(lock))


def test_exact_public_lock_inventory_and_scientific_members(public_inputs):
    assert len(public_inputs.lock["file_inventory"]) == 25
    assert (
        sum(len(f["member_inventory"]) for f in public_inputs.lock["file_inventory"])
        == 263
    )
    assert (
        public_inputs.asset(c.ISO)["sha256"].hex()
        == "f01b812b57fba9f31ff621bf33e7c7570a01964dbeb5be2167e94decf538c89f"
    )
    assert (
        public_inputs.asset(c.LIA)["sha256"].hex()
        == "acc76495cb29c995e73d41dd2f0c51c87695b6395a767d439f7780403deb092f"
    )
    assert (
        public_inputs.asset(c.GN)["sha256"].hex()
        == "2a9780179d77fe299e52226931bf1d170767928eca773374b0ec543e64c6d198"
    )
    for row in public_inputs.registry:
        assert len(row["assets"]) <= 512
        assert row["license_expression"] and row["lineage"]


def test_actual_public_capability_expansion_and_field_witness_bounds(public_inputs):
    import sys
    import pyarrow as pa

    iso, metadata = public_inputs.small_objects()
    assert len(iso) == 5295 and len(metadata) == 12261
    matrix = p.matrix_capabilities(public_inputs.lock, public_inputs.registry)
    assert len(matrix) == 3752
    lia = next(r for r in public_inputs.registry if r["reference_id"] == c.LIA)
    rules = p.metadata_rule_capabilities(
        metadata,
        [r for r in matrix if r["reference_version_id"] == lia["reference_version_id"]],
    )
    with duckdb.connect() as db:
        decoded_registry = pa.Table.from_pylist(
            public_inputs.registry, schema=c.relation_schema("reference_registry")
        ).to_pylist()
        decoded_caps = pa.Table.from_pylist(
            [r for r in matrix + rules if e.runtime_capability(r)],
            schema=c.relation_schema("reference_capability"),
        ).to_pylist()
        view = e.SmallReferenceView(
            decoded_registry, decoded_caps, iso + metadata, connection=db
        )
        seen = set()

        def deep_size(value):
            if id(value) in seen:
                return 0
            seen.add(id(value))
            n = sys.getsizeof(value)
            if isinstance(value, dict):
                n += sum(deep_size(k) + deep_size(v) for k, v in value.items())
            elif isinstance(value, (list, tuple, set)):
                n += sum(deep_size(v) for v in value)
            return n

        assert deep_size(vars(view)) < 64 * 1024 * 1024
        for obj in metadata:
            if obj["country_code"] is not None and obj["object_kind"] in (
                "FORMAT_ADMIN",
                "FORMAT_LOCALITY",
            ):
                assert len(view._ancestry(obj)) <= 12
        for question, country_count in (
            ("Q03", 194),
            ("Q15", 94),
            ("Q04", 176),
            ("Q10", 48),
            ("Q08", 24),
            ("Q09", 6),
            ("Q11", 6),
        ):
            assert (
                sum(
                    r["enabled"]
                    for r in matrix
                    if r["reference_version_id"] == lia["reference_version_id"]
                    and r["question_catalog_id"] == question
                )
                == country_count
            )
        for row in matrix:
            if view.by_version[row["reference_version_id"]]["reference_id"] == c.GN:
                assert not row["negative_authority"]
            if not row["enabled"]:
                assert not row["negative_authority"] and not row["positive_authority"]


def test_actual_frozen_patterns_in_exact_runtime(public_inputs):
    c.require_runtime()
    data = public_inputs.json_data(c.LIA)
    patterns = set()
    examples = []
    excluded = []
    for key, node in data.items():
        if node.get("zip"):
            if p.safe_pattern(node["zip"]):
                patterns.add(node["zip"])
                for example in node.get("zipex", "").split(","):
                    if example:
                        examples.append((node["zip"], example, "/" not in key))
            else:
                excluded.append(key + "/zip")
        for pattern in node.get("sub_zips", "").split("~"):
            if pattern and p.safe_pattern(pattern):
                patterns.add(pattern)
    assert excluded == ["BH/zip"] and len(patterns) == 1255 and len(examples) == 1092
    import re

    with duckdb.connect() as db:
        for pattern in sorted(patterns):
            for probe in (
                "",
                "0",
                "00000",
                "12345",
                "12345-6789",
                "A1A 1A1",
                "999999",
                "12345\n",
                "١٢٣٤٥",
            ):
                observed = db.execute(
                    "SELECT regexp_full_match(?,?),regexp_matches(?,?)",
                    [probe, pattern, probe, "^(?:" + pattern + ")"],
                ).fetchone()
                assert observed == (
                    bool(re.fullmatch(pattern, probe, re.ASCII)),
                    bool(re.match("(?:" + pattern + ")", probe, re.ASCII)),
                )
        for pattern, value, full in examples:
            sql = (
                "SELECT regexp_full_match(?,?)"
                if full
                else "SELECT regexp_matches(?,?)"
            )
            assert db.execute(
                sql, [value, pattern if full else "^(?:" + pattern + ")"]
            ).fetchone() == (True,)

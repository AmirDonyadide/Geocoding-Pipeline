"""Full invented catalog/publication replay, faults and shard-order invariance."""

from __future__ import annotations

from typing import Any
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io


import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as contexts
from safe_geocoding_pipeline.preprocessing.stages import s10_query_materializer as m
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s10_query_summary as s
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_query_families import SyntheticTransform


def catalog(
    accepted: Any, root: Any, *, order: Any = m.SHARDS, resume: Any = None
) -> Any:
    runtime = SyntheticTransform()
    work = contexts.ContextWorkspace(
        accepted, root, c.science_fingerprint(runtime.asset_binding)
    )
    work.prepare()
    records = m.generate_catalog(work, runtime, "a" * 40, order=order, resume=resume)
    return work, m.CatalogArtifact(
        work,
        runtime,
        records,
        {"execution_git_sha": "a" * 40},
        {"lock_sha256": "b" * 64},
    )


@pytest.mark.parametrize("synthetic_inputs", [True], indirect=True)
def test_full_catalog_publish_and_reopen(synthetic_inputs: Any, tmp_path: Any) -> None:
    work, artifact = catalog(synthetic_inputs, tmp_path / "work")
    try:
        report = artifact.expected_summary
        assert report["artifact_row_counts"]["query_hypothesis"]["count"] == 18
        assert report["artifact_row_counts"]["query_family_decision"]["count"] == 24
        assert report["context_counts"]["contexts"]["count"] == 4
        assert report["coverage_counts"]["source_rows_without_hypothesis"]["count"] == 1
        assert report["engineering_counts"]["contexts_at_ceiling"]["count"] == 2
        assert report["operating_budget"] is None
        diagnostic = tmp_path / "diagnostic"
        diagnostic.mkdir(mode=0o700)
        io.write_exclusive(diagnostic / pub.PROGRESS, b"in_progress\n")
        manifest = artifact.build(diagnostic)
        io.write_json(diagnostic / io.MANIFEST_NAME, manifest)
        artifact.validate(
            diagnostic, c.sha256_file(diagnostic / io.MANIFEST_NAME), False
        )
        result = pub.publish(tmp_path / "final", artifact.build, artifact.validate)
        assert result.disposition == "PASS"
        assert (
            artifact.validate(result.path, result.manifest_sha256, True)
            == result.manifest
        )
        adopted = pub.publish(
            result.path,
            lambda _: pytest.fail("rebuild"),
            artifact.validate,
            expected_manifest=result.manifest_sha256,
        )
        assert adopted.disposition == "ADOPT_EXISTING_EXACT_COMMITTED"
        for scope, expected in [
            ("HYPOTHESES_PER_CONTEXT", 5),
            ("HYPOTHESES_PER_SOURCE_ROW", 9),
            ("CONTEXTS_PER_SOURCE_ROW", 2),
        ]:
            assert (
                next(
                    x["maximum"]
                    for x in report["histograms"]["extrema"]
                    if x["scope"] == scope
                )
                == expected
            )
        # Summaries contain only closed dimensions and aggregate values.
        encoded = c.canonical(report)
        assert "α".encode() not in encoded and b"unit 5" not in encoded
    finally:
        work.close()


def test_reverse_shards_and_verified_resume(
    synthetic_inputs: Any, tmp_path: Any
) -> None:
    work, artifact = catalog(synthetic_inputs, tmp_path / "first")
    other, reversed_artifact = catalog(
        synthetic_inputs, tmp_path / "reversed", order=tuple(reversed(m.SHARDS))
    )
    reused, reused_artifact = catalog(
        synthetic_inputs, tmp_path / "reuse", resume=work.root / "shards"
    )
    try:
        assert (
            artifact.expected_summary
            == reversed_artifact.expected_summary
            == reused_artifact.expected_summary
        )
        assert (
            [r["logical_sha256"] for r in artifact.records]
            == [r["logical_sha256"] for r in reversed_artifact.records]
            == [r["logical_sha256"] for r in reused_artifact.records]
        )
        m.replay(reused, reused_artifact.runtime)
        checkpoint = m.validate_checkpoint(
            work.root / "shards" / "0", m.checkpoint_binding(work, "a" * 40), "0"
        )
        wrong = {**checkpoint["binding"], "execution_git_sha": "c" * 40}
        with pytest.raises(c.Stage10Error, match="BINDING"):
            m.validate_checkpoint(work.root / "shards" / "0", wrong, "0")
    finally:
        work.close()
        other.close()
        reused.close()


@pytest.mark.parametrize(
    "fault",
    [
        "cross_context",
        "orphan",
        "duplicate",
        "deleted_decision",
        "changed_intent",
        "changed_lineage",
    ],
)
def test_catalog_corruption_fails(
    synthetic_inputs: Any, tmp_path: Any, fault: Any
) -> None:
    work, artifact = catalog(synthetic_inputs, tmp_path / "work")
    try:
        db = work.db
        for name in c.RELATIONS:
            db.execute(f"CREATE TABLE mutated_{name} AS SELECT * FROM {name}")
            db.execute(f"DROP VIEW {name}")
            db.execute(f"ALTER TABLE mutated_{name} RENAME TO {name}")
        if fault == "cross_context":
            db.execute(
                "UPDATE query_family_decision SET query_context_id=repeat('x',32)::BLOB WHERE family='Q2'"
            )
        elif fault == "orphan":
            db.execute(
                "UPDATE query_family_decision SET hypothesis_id=repeat('x',32)::BLOB WHERE family='Q2'"
            )
        elif fault == "duplicate":
            db.execute(
                "INSERT INTO query_hypothesis SELECT * FROM query_hypothesis LIMIT 1"
            )
        elif fault == "deleted_decision":
            db.execute("DELETE FROM query_family_decision WHERE family='Q6'")
        elif fault == "changed_intent":
            db.execute(
                "UPDATE query_hypothesis SET intent=struct_update(intent,text:='invented mutation') WHERE intent.text IS NOT NULL"
            )
        else:
            db.execute("UPDATE query_family_decision SET lineage=[] WHERE family='Q3'")
        with pytest.raises(c.Stage10Error):
            s.validate_integrity(db)
            m.replay(work, artifact.runtime)
    finally:
        work.close()


def test_unknown_summary_field_rejected() -> None:
    with pytest.raises(c.Stage10Error, match="SUMMARY"):
        s.reconcile_summary({"protected_example": "invented"}, {})

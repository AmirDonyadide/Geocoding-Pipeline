import pytest
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from stage12_b2_synthetic import Authority, H, offline
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_lineage as lineage,
    s12_b2_contract as b,
    s12_b2_calibration as cal,
    s12_retrieval_contract as c,
)


def interpretation(namespace="ISO_ALPHA3"):
    return {
        "country_namespace": namespace,
        "candidate_levels": {
            k: "UNKNOWN"
            for k in ("locality", "localadmin", "county", "region", "macroregion")
        },
        "source_levels": {"city": "UNKNOWN", "region": "UNKNOWN"},
    }


def project(inputs, tmp_path, namespace="ISO_ALPHA3"):
    tmp_path.chmod(0o700)
    value = interpretation(namespace)
    return lineage.LineageProjection.synthetic(
        inputs,
        scratch=tmp_path / "projection",
        memory_bytes=64 * 1024 * 1024,
        reload_accepted=lambda: inputs,
        authority=Authority(),
        interpretation=value,
        interpretation_sha256=b.digest(value),
    )


def test_concrete_accepted_lineage_projection_preserves_roles_and_positive_witnesses(
    synthetic_inputs, tmp_path
):
    p = project(synthetic_inputs, tmp_path)
    try:
        rows = []
        for row in p.rows():
            channels = list(row["channels"])
            rows.append({**row, "channels": channels})
            assert row["script"] == "MIXED" and row["completeness"][0]
            assert channels and all(
                x["dependence_class"] != "PROVEN_DISJOINT" for x in channels
            )
            assert all(
                x["candidate_granularity"] == "UNKNOWN"
                for x in channels
                if x["kind"] == "SOURCE_ADMIN"
            )
        assert len(rows) == 4 and {x["representation"] for x in rows} == {
            "STANDARD",
            "NATIVE",
        }
        by_source = {}
        for row in rows:
            by_source.setdefault(row["stable_source_row_id_v1"], []).append(row)
        for same in by_source.values():
            assert [
                x["origin_claim_key"]
                for x in same[0]["channels"]
                if x["kind"].startswith("SOURCE_")
            ] == [
                x["origin_claim_key"]
                for x in same[1]["channels"]
                if x["kind"].startswith("SOURCE_")
            ]
        assert any(
            x["kind"] == "ACCEPTED_REFERENCE" for row in rows for x in row["channels"]
        )
        p.validate()
    finally:
        p.close()


def test_unknown_country_namespace_stays_unevaluable(synthetic_inputs, tmp_path):
    p = project(synthetic_inputs, tmp_path, "UNKNOWN")
    try:
        for row in p.rows():
            channel = next(iter(row["channels"]))
            assert (
                channel["kind"] == "SOURCE_COUNTRY"
                and channel["source_value"] is None
                and channel["comparison_method"] == "NOT_APPLIED_V1"
            )
    finally:
        p.close()


def test_missing_capability_is_integrity_failure(synthetic_inputs, tmp_path):
    p = project(synthetic_inputs, tmp_path)
    try:
        p.db.execute("delete from stage10_capabilities where question_catalog_id='Q01'")
        with pytest.raises(Exception, match="CARDINALITY"):
            next(p.rows())
    finally:
        p.close()


def test_exact_ISO_namespace_projection_and_shared_alias_tokens(
    synthetic_inputs, tmp_path
):
    from stage12_synthetic import body, feature
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    p = project(synthetic_inputs, tmp_path, "ISO_ALPHA2")
    try:
        context = next(p.rows())
        context["channels"] = list(context["channels"])
        country = next(x for x in context["channels"] if x["kind"] == "SOURCE_COUNTRY")
        assert country["source_value"] in ("US", "DE")
        f = feature()
        f["properties"]["country_a"] = country["source_value"]
        raw = body([f])
        projection = response.extract(
            raw,
            b.sha(b"synthetic projection"),
            size=5,
            http_status=200,
            content_type="application/json",
            encoding="absent",
            layers=frozenset({"address"}),
            sources=frozenset({"synthetic"}),
            expected_echo={},
        )
        tokens = cal.tokens(
            projection.candidates[0],
            response.Parser(raw).parse().value["features"][0],
            context,
        )
        assert any(t[1] == "SOURCE_COUNTRY" for t in tokens)
        reference = next(
            x for x in context["channels"] if x["kind"] == "ACCEPTED_REFERENCE"
        )
        assert (
            reference["origin_detail"]["question"] == "Q01"
            and reference["positive_reference"]
        )
        assert any(t[1] == "ACCEPTED_REFERENCE" for t in tokens)
        duplicate = {
            **reference,
            "origin_detail": {**reference["origin_detail"], "field_ordinal": 999},
        }
        context["channels"].append(duplicate)
        assert (
            cal.tokens(
                projection.candidates[0],
                response.Parser(raw).parse().value["features"][0],
                context,
            )
            == tokens
        )
    finally:
        p.close()


def test_missing_ISO_alpha3_field_is_not_invented(synthetic_inputs, tmp_path):
    p = project(synthetic_inputs, tmp_path, "ISO_ALPHA3")
    try:
        for row in p.rows():
            channel = next(iter(row["channels"]))
            # This intentionally minimal accepted-schema fixture has alpha2 only.
            assert (
                channel["source_value"] is None
                and channel["comparison_method"] == "NOT_APPLIED_V1"
            )
    finally:
        p.close()


def test_synthetic_constructor_cannot_satisfy_accepted_chain(
    synthetic_inputs, tmp_path
):
    p = project(synthetic_inputs, tmp_path)
    try:
        assert p.population_scope == b.SYNTHETIC
        with pytest.raises(c.Stage12Error, match="B2_ACCEPTED_LINEAGE_REQUIRED"):
            p.assert_accepted_chain()
    finally:
        p.close()


def test_test_lineage_rejected_before_any_accepted_input_read(
    synthetic_inputs, tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as catalogs

    p = project(synthetic_inputs, tmp_path)
    monkeypatch.setattr(
        catalogs,
        "load_stage11",
        lambda *_: pytest.fail("must reject before protected artifact read"),
    )
    try:
        with pytest.raises(c.Stage12Error, match="B2_CONCRETE_LINEAGE_REQUIRED"):
            catalogs.build_accepted(
                tmp_path / "catalog",
                tmp_path / "unopened",
                {},
                repository=tmp_path,
                lineage=p,
                authority=Authority(),
                scratch=tmp_path / "unopened-scratch",
                memory_bytes=64 * 1024 * 1024,
            )
    finally:
        p.close()

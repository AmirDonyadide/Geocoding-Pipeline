"""Synthetic reference/source evidence; all address-like values are invented."""

from __future__ import annotations

import io

import duckdb
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_evaluator as e
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_pack as p
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_questions as q


@pytest.fixture
def reference_view():
    countries = ["DE", "US", "JP", "CA", "BR", "CN", "BH", "GB", "AF"]
    registry = []
    for i, family in enumerate(c.FAMILIES):
        assets = (
            [
                {
                    "role": "DATA_JSON",
                    "relative_path": "iso_3166-1_synthetic.json",
                    "member_path": None,
                    "asset_id": b"1" * 32,
                },
                {
                    "role": "DATA_JSON",
                    "relative_path": "iso_3166-2_synthetic.json",
                    "member_path": None,
                    "asset_id": b"2" * 32,
                },
            ]
            if family == c.ISO
            else [
                {
                    "relative_path": "synthetic.zip",
                    "member_path": "i18naddress/data/all.json"
                    if family == c.LIA
                    else "allCountries.txt",
                    "asset_id": bytes([i + 3]) * 32,
                }
            ]
        )
        registry.append(
            {
                "reference_id": family,
                "reference_version_id": bytes([i + 1]) * 32,
                "countries": countries
                if family != c.GN
                else [x for x in countries if x != "AF"],
                "assets": assets,
                "limitations": [],
            }
        )
    templates = []
    for question in c.CATALOG:
        for family in question.references:
            if family == "NONE":
                continue
            enabled_countries = (
                ["GLOBAL"]
                if question.question_id in ("Q01", "Q14")
                else list(countries)
            )
            if family == c.GN and question.question_id in ("Q05", "Q06", "Q07"):
                enabled_countries = [
                    x for x in enabled_countries if x not in ("CA", "CN", "GB", "AF")
                ]
            elif family == c.GN:
                enabled_countries.remove("AF")
            if family == c.LIA and question.question_id == "Q04":
                enabled_countries = [
                    x for x in enabled_countries if x not in ("CN", "BH")
                ]
            negative = (
                family == c.ISO
                and question.question_id == "Q02"
                or family == c.LIA
                and question.question_id in ("Q04", "Q08")
            )
            templates.append(
                {
                    "reference_id": family,
                    "question_catalog_id": question.question_id,
                    "country_scope_selector": enabled_countries,
                    "positive_authority": True,
                    "positive_authority_basis": "SYNTHETIC_EXPLICIT_RECORD",
                    "negative_authority": negative,
                    "negative_authority_basis": "EXPLICIT_CODE_PARENT"
                    if family == c.ISO and negative
                    else "EXPLICIT_FORMAT_RULE"
                    if negative
                    else "NONE",
                    "object_gate": "SYNTHETIC_EXPLICIT_FIELDS",
                }
            )
    lock = {
        "capability_registry": {
            "rules": templates,
            "geonames_full_code_disabled_countries": ["CA", "CN", "GB"],
            "geonames_major_code_only_countries": ["BR"],
        }
    }
    matrix = p.matrix_capabilities(lock, registry)
    iso1 = [{"alpha_2": cc, "name": "Synthetic " + cc} for cc in countries]
    iso2 = [
        {"code": "DE-EX", "name": "Beispielregion", "type": "Synthetic"},
        {"code": "US-EX", "name": "Example State", "type": "Synthetic"},
    ]
    objects = list(
        p.iso_objects(iso1, registry[0], registry[0]["assets"][0], subdivision=False)
    )
    objects += list(
        p.iso_objects(iso2, registry[0], registry[0]["assets"][1], subdivision=True)
    )
    metadata = {
        cc: {"key": cc, "fmt": "%C %Z", "require": "CZ", "zip": r"\d{5}"}
        for cc in countries
    }
    metadata["AF"] = {"key": "AF"}
    metadata["BH"]["zip"] = r"\b\d{4}"
    metadata["US"].update(
        sub_keys="EX~CF", sub_names="Example State~Conflict State", sub_zips="00~99"
    )
    metadata["US/EX"] = {
        "key": "EX",
        "name": "Example State",
        "zip": "00",
        "sub_keys": "Exampletown",
        "sub_lnames": "Exámpletown",
    }
    metadata["US/CF"] = {"key": "CF", "name": "Conflict State", "zip": "00"}
    metadata["US/EX/Exampletown"] = {
        "key": "Exampletown",
        "name": "Exampletown",
        "lname": "Exámpletown",
    }
    metadata["JP"].update(sub_keys="例県", sub_names="例県", sub_lnames="Reiken")
    metadata["JP/例県"] = {"key": "例県", "name": "例県", "lname": "Reiken"}
    metadata["CA"].update(sub_keys="EX", sub_names="Exemple", sub_zips="00")
    metadata["CA--fr"] = {
        "key": "CA",
        "lang": "fr",
        "sub_keys": "EX",
        "sub_names": "Exemple",
        "sub_zips": "00",
    }
    metadata["CA/EX"] = {"key": "EX", "name": "Exemple", "zip": "00"}
    metadata["CA/EX--fr"] = {"key": "EX", "name": "Exemple", "zip": "00", "lang": "fr"}
    objects += p.metadata_objects(metadata, registry[1], registry[1]["assets"][0])
    rules = p.metadata_rule_capabilities(
        [
            o
            for o in objects
            if o["reference_version_id"] == registry[1]["reference_version_id"]
        ],
        [
            r
            for r in matrix
            if r["reference_version_id"] == registry[1]["reference_version_id"]
        ],
    )
    with duckdb.connect() as connection:
        yield e.SmallReferenceView(
            registry, matrix + rules, objects, connection=connection
        )


def candidate(country="us", component_count=0):
    return {
        "stage06_exact_candidate_id": b"c" * 32,
        "stage07_trusted_country_iso_code": country,
        "stage07_country_provenance_status": "COUNTRY_UNANIMOUS_VALID"
        if country
        else "COUNTRY_MISSING",
        "stage08_raw_component_count": component_count,
    }


def source(
    country="us", postcode="00123", locality="Exampletown", admin="Example State"
):
    return {
        "stable_source_row_id_v1": b"s" * 32,
        "stage06_standard_exact_candidate_id": b"c" * 32,
        "stage06_native_exact_candidate_id": b"c" * 32,
        "stage03_clean_country_iso_code": country,
        "stage03_clean_postcode": postcode,
        "stage03_clean_city": locality,
        "stage03_clean_region_in_country": admin,
    }


def evaluate(view, question, family, **values):
    prepared = view.prepare(
        next(
            x
            for x in q.source_questions(
                source(**values), candidate(values.get("country", "us"))
            )
            if x.question_id == question
        ),
        family,
    )
    result = view.lookup_small(prepared)
    row, members = e.finalize_small(
        prepared, result, profile=b"p" * 32, stage08_logical=b"8" * 32
    )
    return row, list(members)


@pytest.mark.parametrize(
    "question,family,values,state,reason",
    [
        ("Q01", c.ISO, {}, "SUPPORTED", "EXACT_REFERENCE_SUPPORT"),
        (
            "Q02",
            c.ISO,
            {"admin": "US-EX"},
            "SUPPORTED",
            "EXPLICIT_CODE_COUNTRY_SUPPORT",
        ),
        (
            "Q02",
            c.ISO,
            {"admin": "DE-EX"},
            "CONTRADICTED",
            "EXPLICIT_CODE_COUNTRY_CONFLICT",
        ),
        (
            "Q02",
            c.ISO,
            {"admin": "XX-EX"},
            "NOT_EVALUABLE",
            "EXPLICIT_CODE_NOT_IDENTIFIED",
        ),
        ("Q03", c.LIA, {}, "SUPPORTED", "EXPLICIT_RULE_SUPPORT"),
        ("Q15", c.LIA, {}, "SUPPORTED", "EXPLICIT_RULE_SUPPORT"),
        (
            "Q15",
            c.LIA,
            {"country": "af"},
            "NOT_EVALUABLE",
            "COMPONENT_CAPABILITY_MISSING",
        ),
        ("Q04", c.LIA, {}, "SUPPORTED", "EXPLICIT_RULE_SUPPORT"),
        ("Q04", c.LIA, {"postcode": "1234X"}, "CONTRADICTED", "EXPLICIT_RULE_CONFLICT"),
        ("Q04", c.LIA, {"postcode": "١٢٣٤٥"}, "CONTRADICTED", "EXPLICIT_RULE_CONFLICT"),
        (
            "Q04",
            c.LIA,
            {"country": "bh"},
            "NOT_EVALUABLE",
            "PATTERN_DIALECT_UNSUPPORTED",
        ),
        (
            "Q04",
            c.LIA,
            {"country": "cn"},
            "NOT_EVALUABLE",
            "ALTERNATE_RULE_SEMANTICS_UNSUPPORTED",
        ),
        ("Q08", c.LIA, {}, "SUPPORTED", "EXPLICIT_RULE_SUPPORT"),
        ("Q08", c.LIA, {"postcode": "99123"}, "CONTRADICTED", "EXPLICIT_RULE_CONFLICT"),
        (
            "Q08",
            c.LIA,
            {"postcode": "99A23"},
            "NOT_EVALUABLE",
            "COUNTRY_FORMAT_PREREQUISITE_FAILED",
        ),
        (
            "Q08",
            c.LIA,
            {"admin": "Conflict State"},
            "NOT_EVALUABLE",
            "REFERENCE_INTERNAL_CONFLICT",
        ),
        (
            "Q08",
            c.LIA,
            {"country": "ca", "admin": "Exemple"},
            "NOT_EVALUABLE",
            "ADMIN_IDENTITY_UNRESOLVED",
        ),
        ("Q09", c.LIA, {}, "SUPPORTED", "EXACT_REFERENCE_SUPPORT"),
        (
            "Q09",
            c.LIA,
            {"locality": "Exa\u0301mpletown"},
            "SUPPORTED",
            "EXACT_REFERENCE_SUPPORT",
        ),
        (
            "Q09",
            c.LIA,
            {"locality": "Unrecordedplace"},
            "NOT_FOUND",
            "VALUE_ABSENT_FROM_REFERENCE",
        ),
        ("Q10", c.ISO, {"admin": "US-EX"}, "SUPPORTED", "EXACT_REFERENCE_SUPPORT"),
        ("Q10", c.ISO, {"admin": "DE-EX"}, "NOT_FOUND", "VALUE_ABSENT_FROM_REFERENCE"),
        (
            "Q10",
            c.LIA,
            {"country": "jp", "admin": "例県"},
            "SUPPORTED",
            "EXACT_REFERENCE_SUPPORT",
        ),
        (
            "Q10",
            c.LIA,
            {"country": "jp", "admin": "Reiken"},
            "SUPPORTED",
            "EXACT_REFERENCE_SUPPORT",
        ),
        ("Q11", c.LIA, {}, "SUPPORTED", "EXACT_REFERENCE_SUPPORT"),
        (
            "Q11",
            c.LIA,
            {"admin": "Conflict State"},
            "NOT_FOUND",
            "RELATION_ABSENT_FROM_REFERENCE",
        ),
        ("Q12", "NONE", {}, "NOT_EVALUABLE", "CAPABILITY_NOT_CONFIGURED"),
    ],
)
def test_frozen_scoped_semantics(
    reference_view, question, family, values, state, reason
):
    row, members = evaluate(reference_view, question, family, **values)
    assert (row["result_state"], row["reason_code"]) == (state, reason)
    assert not members
    if question != "Q02":
        assert row["country_assessment"] == "COUNTRY_UNRESOLVED"


@pytest.mark.parametrize(
    "country,postcode,reason",
    [
        ("ca", "A1A 1A1", "REFERENCE_GRANULARITY_INSUFFICIENT"),
        ("gb", "AB1 2CD", "REFERENCE_GRANULARITY_INSUFFICIENT"),
        ("us", "00123-4567", "REFERENCE_GRANULARITY_INSUFFICIENT"),
        ("af", "00123", "COUNTRY_NOT_COVERED"),
        (None, "00123", "COUNTRY_CONTEXT_UNRESOLVED"),
    ],
)
def test_geonames_coverage_gate(reference_view, country, postcode, reason):
    question = next(
        x
        for x in q.source_questions(
            source(country=country, postcode=postcode), candidate(country)
        )
        if x.question_id == "Q05"
    )
    prepared = reference_view.prepare(question, c.GN)
    assert prepared.unavailable_reason == reason
    assert not prepared.capability["negative_authority"]


@pytest.mark.parametrize(
    "pattern",
    [
        r"\b\d{4}",
        r"(?i)[A-Z]+",
        r"(?=1)1",
        r"(1)\1",
        r"\w+",
        "例",
        r"\d+?",
        "(?P<x>1)(?P=x)",
    ],
)
def test_regex_grammar_rejects_unsupported_semantics(pattern):
    assert not p.safe_pattern(pattern)


@pytest.mark.parametrize(
    "pattern", [r"\d{5}", "9[0-5]|96[01]", "[A-Z] ?[0-9]", "^(?:00|99)[0-9]{3}$"]
)
def test_regex_grammar_allows_frozen_subset(pattern):
    assert p.safe_pattern(pattern)


def components(labels):
    for ordinal, (label, value) in enumerate(labels):
        yield {
            "stage06_exact_candidate_id": b"c" * 32,
            "stage08_component_ordinal": ordinal,
            "stage08_safe_parser_evidence_component": label,
            "stage08_raw_libpostal_value": value,
        }


def test_duplicate_parser_ordinals_are_not_coalesced_or_cross_producted(reference_view):
    labels = [
        ("PARSER_POSTCODE", "00123"),
        ("PARSER_POSTCODE", "00123"),
        ("PARSER_CITY", "Exampletown"),
    ]
    questions = list(
        q.parser_questions(candidate(component_count=3), components(labels))
    )
    assert len([x for x in questions if x.question_id == "Q04"]) == 2
    relation = next(x for x in questions if x.question_id == "Q06")
    assert relation.observations[1].observed_role_count == 2
    assert relation.observations[1].origin_field is None
    assert (
        reference_view.prepare(relation, c.GN).unavailable_reason
        == "AMBIGUOUS_COMPONENT_SET"
    )


def test_parser_country_and_source_country_remain_separate(reference_view):
    questions = list(
        q.parser_questions(candidate(None, 1), components([("PARSER_COUNTRY", "de")]))
    )
    parser_country = next(x for x in questions if x.question_id == "Q14")
    prepared = reference_view.prepare(parser_country, c.ISO)
    row, _ = e.finalize_small(
        prepared,
        reference_view.lookup_small(prepared),
        profile=b"p" * 32,
        stage08_logical=b"8" * 32,
    )
    assert (
        row["result_state"] == "SUPPORTED"
        and row["country_assessment"] == "COUNTRY_UNRESOLVED"
    )
    assert (
        reference_view.prepare(
            next(x for x in questions if x.question_id == "Q03"), c.LIA
        ).unavailable_reason
        == "COUNTRY_CONTEXT_UNRESOLVED"
    )


def test_identity_and_complete_witnesses_are_reference_order_independent(
    reference_view,
):
    first, members1 = evaluate(
        reference_view, "Q10", c.LIA, country="ca", admin="Exemple"
    )
    reverse = e.SmallReferenceView(
        list(reversed(list(reference_view.registry.values()))),
        list(reversed(list(reference_view.capabilities.values()))),
        list(reversed(list(reference_view.objects.values()))),
        connection=reference_view.connection,
    )
    second, members2 = evaluate(reverse, "Q10", c.LIA, country="ca", admin="Exemple")
    assert first == second and members1 == members2
    assert first["witness_count"] == 2 and first["single_witness"] is None
    assert len(members1) == 2
    assert (
        members1[0]["witness"]["reference_object_id"]
        != members1[1]["witness"]["reference_object_id"]
    )


def test_geonames_projection_excludes_coordinate_and_accuracy_fields():
    registry = {"countries": ["US"], "reference_version_id": b"v" * 32}
    asset = {"asset_id": b"a" * 32, "member_path": "allCountries.txt"}
    raw = "US\t00123\tExampletown\tExample State\tEX\tExample County\tE1\t\t\t12.345\t67.890\t4\n"
    obj = next(p.geonames_objects(io.StringIO(raw), registry, asset))
    assert len(obj["fields"]) == 9
    assert all(f["original_value"] not in ("12.345", "67.890") for f in obj["fields"])
    index = p.geonames_index_row(obj)
    assert index["postcode"] == "00123" and index["admin1"] == "example state"
    assert set(index) == set(p.GN_INDEX_SCHEMA.names)


def test_postal_batch_join_four_states_mismatch_reuse_and_complete_members(
    reference_view, tmp_path
):
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as rio
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_postal as postal,
    )

    registry = reference_view.registry[c.GN]
    asset = registry["assets"][0]
    raw = "".join(
        f"US\t00123\tExampletown\tExample State\tEX\tCounty {i}\t{i}\tExample State\tEX\t0\t0\t4\n"
        for i in range(7)
    )
    objects = list(p.geonames_objects(io.StringIO(raw), registry, asset))
    index = rio.RelationWriter(tmp_path / "index", p.GN_INDEX_SCHEMA)
    for obj in reversed(objects):
        index.append(p.geonames_index_row(obj))
    index.close()
    writer = rio.RelationWriter(tmp_path / "requests", postal.REQUEST_SCHEMA)
    for number, values in enumerate(
        ({}, {"locality": "Missingplace"}, {"postcode": "00999"}, {})
    ):
        src = source(**values)
        src["stable_source_row_id_v1"] = bytes([number]) * 32
        for question in q.source_questions(src, candidate()):
            if question.question_id not in ("Q05", "Q06", "Q07", "Q09", "Q10", "Q11"):
                continue
            prepared = reference_view.prepare(question, c.GN)
            writer.append(
                postal.postal_request(
                    prepared, profile=b"p" * 32, stage08_logical=b"8" * 32
                )
            )
    writer.close()
    evidence_paths, member_paths, metrics = postal.resolve_postal_requests(
        writer.paths,
        index.paths,
        tmp_path / "resolved",
        reference_view.capabilities,
        memory="128MB",
        threads=1,
    )
    evidence = list(rio.parquet_rows(evidence_paths))
    members = list(rio.parquet_rows(member_paths))
    assert len(evidence) == 24 and metrics["distinct_lookups"] < 24
    assert {row["result_state"] for row in evidence} == {"SUPPORTED", "NOT_FOUND"}
    assert any(
        row["reason_code"] == "REFERENCE_ASSOCIATION_MISMATCH" for row in evidence
    )
    assert all(row["witness_count"] in (0, 7) for row in evidence)
    # The same name at two admin levels must remain one object witness,
    # recording both fields, even with separate equality-join branches.
    for row in evidence:
        if row["question_catalog_id"] == "Q10":
            matched = next(
                m for m in members if m["match_set_id"] == row["match_set_id"]
            )
            names = {f["field_name"] for f in matched["witness"]["fields"]}
            assert {"admin_name1", "admin_name3"} <= names
    for row in evidence:
        selected = [m for m in members if m["match_set_id"] == row["match_set_id"]]
        if row["witness_count"]:
            assert len(selected) == 7
            assert row["match_set_id"] == c.identity(
                "MATCH_SET",
                (
                    row["lookup_identity"],
                    tuple(c.witness_tuple(m["witness"]) for m in selected),
                ),
            )
    assert len({row["evidence_id"] for row in evidence}) == 24
    assert len({(m["match_set_id"], m["member_ordinal"]) for m in members}) == len(
        members
    )


@pytest.fixture
def synthetic_stage08_db(reference_view, tmp_path):
    import pyarrow as pa
    from safe_geocoding_pipeline.preprocessing.stages import s08_address_evidence as s08
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as rio

    source_rows = [source(), source(locality="Missingplace")]
    for n, row in enumerate(source_rows):
        row.update(
            stable_source_row_id_v1=bytes([n]) * 32,
            stage08_source_row_ordinal=n,
            stage08_standard_representation_status="PRESENT",
            stage08_native_representation_status="PRESENT",
        )
    with rio.bounded_connection(
        tmp_path / "stage08-spill", memory="128MB", threads=1
    ) as db:
        for name, table in (
            ("candidate_evidence", pa.Table.from_pylist([candidate()])),
            ("source_candidate_map", pa.Table.from_pylist(source_rows)),
            (
                "parser_component_evidence",
                pa.Table.from_pylist([], schema=s08.parser_component_evidence_schema()),
            ),
        ):
            db.register("synthetic_fixture", table)
            db.execute(f"CREATE TABLE {name} AS SELECT * FROM synthetic_fixture")
            db.unregister("synthetic_fixture")
        db.execute(
            "CREATE VIEW stage08_occurrence AS " + s08.REPRESENTATION_OCCURRENCE_SQL
        )
        yield db


def test_shard_checkpoint_resume_and_coverage_preserve_stage08_grain(
    reference_view, synthetic_stage08_db, tmp_path
):
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as rio
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_execution as run,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_coverage as coverage,
    )

    registry = reference_view.registry[c.GN]
    raw = "US\t00123\tExampletown\tExample State\tEX\tCounty One\t1\t\t\t0\t0\t4\n"
    obj = next(p.geonames_objects(io.StringIO(raw), registry, registry["assets"][0]))
    index = rio.RelationWriter(tmp_path / "index", p.GN_INDEX_SCHEMA)
    index.append(p.geonames_index_row(obj))
    index.close()
    binding = run.checkpoint_binding(
        profile=b"p" * 32,
        input_binding=b"i" * 32,
        pack=b"r" * 32,
        executable="f" * 40,
        group=6,
    )
    checkpoint = run.materialize_group(
        synthetic_stage08_db,
        reference_view,
        index.paths,
        tmp_path / "shard",
        group=6,
        profile=b"p" * 32,
        stage08_logical=b"8" * 32,
        binding=binding,
        memory="128MB",
        threads=1,
    )
    assert checkpoint["metrics"]["scheduled_evaluations"] == 55
    copied = run.adopt_checkpoint(tmp_path / "shard", tmp_path / "adopted", binding)
    assert copied["relations"] == checkpoint["relations"]
    with pytest.raises(c.Stage09Error, match="BINDING_OR_STATE"):
        run.validate_checkpoint(
            tmp_path / "shard", {**binding, "execution_git_sha": "e" * 40}
        )
    evidence_paths = [
        tmp_path / "shard" / f["relative_path"]
        for f in checkpoint["relations"][0]["files"]
    ]
    synthetic_stage08_db.execute(
        "CREATE VIEW evidence AS SELECT * FROM " + rio.parquet_sql(evidence_paths)
    )
    coverage.register_question_slots(synthetic_stage08_db)
    counts = {
        "candidate_evidence": 1,
        "source_candidate_map": 2,
        "standard_occurrences": 2,
        "native_occurrences": 2,
        "representation_occurrence_v1": 4,
    }
    summaries = list(
        coverage.coverage_rows(
            synthetic_stage08_db, reference_view.registry[c.ISO]["countries"], counts
        )
    )
    global_evaluation = [
        r
        for r in summaries
        if r["summary_kind"] == "EVALUATION" and r["country_scope"] == "ALL"
    ]
    assert sum(r["count"] for r in global_evaluation) == 55
    source_support = next(
        r
        for r in summaries
        if r["summary_kind"] == "SOURCE_INCIDENCE"
        and r["question_catalog_id"] == "Q06"
        and r["reference_slot"] == c.GN
        and r["result_state"] == "SUPPORTED"
    )
    assert source_support["count"] == 1 and source_support["denominator"] == 2
    occurrences = next(
        r
        for r in summaries
        if r["summary_kind"] == "OCCURRENCE_INCIDENCE"
        and r["representation"] == "ALL"
        and r["question_catalog_id"] == "Q06"
        and r["reference_slot"] == c.GN
        and r["result_state"] == "SUPPORTED"
    )
    assert occurrences["count"] == 2 and occurrences["denominator"] == 4
    metrics = coverage.aggregate_metrics(synthetic_stage08_db)
    assert (
        metrics["candidates_without_evidence"] == 0 and metrics["evidence_rows"] == 55
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_validation as validation,
    )

    public_objects = rio.RelationWriter(
        tmp_path / "objects", c.relation_schema("reference_object")
    )
    for public_object in (*reference_view.objects.values(), obj):
        public_objects.append(public_object)
    public_objects.close()
    synthetic_stage08_db.execute("DROP VIEW evaluation_dimensions")
    synthetic_stage08_db.execute("DROP VIEW evidence")
    member_paths = [
        tmp_path / "shard" / f["relative_path"]
        for f in checkpoint["relations"][1]["files"]
    ]
    checks = validation.validate_integrity(
        synthetic_stage08_db,
        reference_view,
        evidence_paths,
        member_paths,
        public_objects.paths,
        index.paths,
        profile=b"p" * 32,
        stage08_logical=b"8" * 32,
        counts=counts,
    )
    assert all(v == "PASS" for v in checks.values())


def test_complete_synthetic_candidate_publication_and_reopen(
    reference_view, synthetic_stage08_db, tmp_path, monkeypatch
):
    """Full coordinator uses invented tables; the protected entry point is not bypassed."""
    import copy
    from types import SimpleNamespace
    import pyarrow.parquet as pq
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_materializer as materializer,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_index as public_index,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_input as upstream,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as rio

    registry = copy.deepcopy(list(reference_view.registry.values()))
    for row in registry:
        row.update(
            dataset_name="Synthetic fixture",
            dataset_release="SYNTHETIC_V1",
            edition="SYNTHETIC_V1",
            evidence_family=row["reference_id"],
            retrieval_utc="2000-01-01T00:00:00Z",
            effective_date=None,
            license_expression="CC0-1.0",
            license_note="Invented test fixture",
            normalization_contract=c.NORMALIZATION_VERSION,
            lineage=[],
            raw_dataset_sha256=b"r" * 32,
        )
        for asset in row["assets"]:
            asset.update(
                role=asset.get("role", "DATA_MEMBER"),
                source_url="urn:synthetic:test",
                retrieval_utc="2000-01-01T00:00:00Z",
                publisher_release="SYNTHETIC_V1",
                last_modified=None,
                etag=None,
                bytes=0,
                sha256=b"a" * 32,
                media_type="application/octet-stream",
                provenance="SYNTHETIC_TEST_ONLY",
            )
    gn_registry = next(r for r in registry if r["reference_id"] == c.GN)
    postal_object = next(
        p.geonames_objects(
            io.StringIO(
                "US\t00123\tExampletown\tExample State\tEX\tCounty One\t1\t\t\t0\t0\t4\n"
            ),
            gn_registry,
            gn_registry["assets"][0],
        )
    )
    iso = [
        obj
        for obj in reference_view.objects.values()
        if obj["object_kind"].startswith("ISO_")
    ]
    metadata = [
        obj
        for obj in reference_view.objects.values()
        if obj["object_kind"].startswith("FORMAT_")
    ]
    raw = SimpleNamespace(
        root=tmp_path / "invented-raw",
        registry=registry,
        lock={"compatibility_audit": {"geonames": {"rows": 1}}},
        small_objects=lambda: (iso, metadata),
        postal_objects=lambda: iter([postal_object]),
    )
    matrix = [
        row
        for row in reference_view.capabilities.values()
        if row["scope_locator"] == "COUNTRY_MATRIX"
    ]
    monkeypatch.setattr(p, "matrix_capabilities", lambda lock, registry: matrix)
    public = public_index.build_public_pack(raw, tmp_path / "public-pack", "f" * 40)
    public_index.validate_public_pack(public.path, public.manifest_sha256, inputs=raw)
    # Self-consistent published hashes are insufficient if the projection
    # does not equal its immutable raw origin. No ID or index is modified.
    original_value = postal_object["fields"][0]["original_value"]
    postal_object["fields"][0]["original_value"] = "synthetic altered origin"
    with pytest.raises(c.Stage09Error, match="POSTAL_RAW_DERIVATION_MISMATCH"):
        public_index.validate_public_pack(
            public.path, public.manifest_sha256, inputs=raw
        )
    postal_object["fields"][0]["original_value"] = original_value
    import copy

    changed_matrix = copy.deepcopy(matrix)
    changed_matrix[0]["enabled"] = not changed_matrix[0]["enabled"]
    with monkeypatch.context() as mutation:
        mutation.setattr(
            p, "matrix_capabilities", lambda lock, registry: changed_matrix
        )
        with pytest.raises(
            c.Stage09Error, match="CAPABILITY_RAW_LOCK_DERIVATION_MISMATCH"
        ):
            public_index.validate_public_pack(
                public.path, public.manifest_sha256, inputs=raw
            )
    paths = {}
    for name in (
        "candidate_evidence",
        "source_candidate_map",
        "parser_component_evidence",
    ):
        table = synthetic_stage08_db.execute(f"SELECT * FROM {name}").to_arrow_table()
        path = tmp_path / (name + ".parquet")
        pq.write_table(table, path)
        path.chmod(0o600)
        paths[name] = (path,)
    binding = {
        "split": "SYNTHETIC",
        "stage08_logical_dataset_sha256": "8" * 64,
        "stage08_relation_logical_fingerprints": {
            "representation_occurrence_v1": "9" * 64
        },
        "counts": {
            "candidate_evidence": 1,
            "parser_component_evidence": 0,
            "source_candidate_map": 2,
            "standard_occurrences": 2,
            "native_occurrences": 2,
            "representation_occurrence_v1": 4,
        },
    }
    accepted = upstream.AcceptedStage08(tmp_path, {}, paths, binding)
    config = materializer.Stage09Config(
        tmp_path, tmp_path, tmp_path, public.path, tmp_path / "candidate", "f" * 40
    )
    work = tmp_path / "work"
    work.mkdir(mode=0o700)

    def build(root):
        return materializer._build_candidate(
            root, work, config, accepted, raw, public.manifest, public.manifest_sha256
        )

    def validate(root, digest, published):
        return materializer.validate_candidate(
            root,
            digest,
            published=published,
            config=config,
            accepted=accepted,
            raw=raw,
            public_manifest=public.manifest,
            public_sha=public.manifest_sha256,
        )

    result = rio.publish(config.output_directory, build, validate)
    assert result.manifest["development_metrics"]["evidence_rows"] == 55
    assert result.manifest["stage09_accepted"] is False
    assert (
        validate(result.path, result.manifest_sha256, True)["logical_sha256"]
        == result.manifest["logical_sha256"]
    )

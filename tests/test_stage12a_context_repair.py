"""Invented real-path lookup/SQLite regressions; no protected inputs or timing gate."""

import json
import sqlite3
import time

import pyarrow as pa
import pytest

from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage12_b2_lineage import project
from stage12_b2_synthetic import Authority, H, offline as offline
from safe_geocoding_pipeline.preprocessing.stages import (
    s10_query_contexts as contexts,
    s10_query_contract as s10,
    s11_semantic_contract as s11,
    s12_b2_catalog as catalog,
    s12_b2_contract as b,
    s12_b2_lineage as lineage,
    s12_retrieval_contract as c,
    s12_storage as io,
    s12a_local_preparation as local,
)


def baseline_country(projection, code):
    """Preserved pre-repair Python projection used as the equivalence oracle."""
    if not isinstance(code, str) or not code:
        return None, None
    wanted = lineage.s9.normalize(lineage.s9.ISO_NORM, code)
    found = None
    for row in contexts.sql_rows(
        projection.db, "select * from stage10_objects where object_kind='ISO_COUNTRY'"
    ):
        fields = {x["field_name"]: x["original_value"] for x in row["fields"]}
        if wanted in (fields.get("alpha_2"), fields.get("alpha_3")):
            b.require(found is None, "B2_COUNTRY_AMBIGUOUS")
            found = fields
    if found is None:
        return None, None
    namespace = projection.interpretation["country_namespace"]
    return found.get("alpha_2"), found.get(
        "alpha_2" if namespace == "ISO_ALPHA2" else "alpha_3"
    ) if namespace != "UNKNOWN" else None


def baseline_capability(projection, country):
    vector = []
    for question in lineage.s9.CATALOG:
        for reference in question.references:
            if reference == "NONE":
                vector.append(
                    [
                        question.question_id,
                        reference,
                        False,
                        "UNAVAILABLE",
                        False,
                        False,
                    ]
                )
                continue
            scope = (
                "GLOBAL"
                if question.question_id in ("Q01", "Q14")
                else country or "UNRESOLVED"
            )
            row = contexts.one(
                projection.db,
                "select c.* from stage10_capabilities c join stage10_registry r using(reference_version_id) where r.reference_id=? and c.question_catalog_id=? and c.country_scope=? and c.scope_locator=?",
                [reference, question.question_id, scope, "COUNTRY_MATRIX"],
            )
            vector.append(
                [
                    question.question_id,
                    reference,
                    row["enabled"],
                    row["granularity"],
                    row["positive_authority"],
                    row["negative_authority"],
                ]
            )
    return vector


@pytest.mark.parametrize("namespace", ["UNKNOWN", "ISO_ALPHA2", "ISO_ALPHA3"])
def test_country_sql_preserves_last_field_missing_null_and_ambiguity(
    synthetic_inputs, tmp_path, namespace
):
    p = project(synthetic_inputs, tmp_path, namespace)
    try:
        original = next(
            row
            for row in contexts.sql_rows(
                p.db, "select * from stage10_objects where object_kind='ISO_COUNTRY'"
            )
            if any(
                x["field_name"] == "alpha_2" and x["original_value"] == "DE"
                for x in row["fields"]
            )
        )
        atom = original["fields"][0]

        def field(name, text):
            return {**atom, "field_name": name, "original_value": text}

        no_alpha = [
            x
            for x in original["fields"]
            if x["field_name"] not in ("alpha_2", "alpha_3")
        ]
        cases = [
            original["fields"],
            no_alpha + [field("alpha_2", "XX"), field("alpha_2", "DE")],
            no_alpha + [field("alpha_2", "DE"), field("alpha_2", "XX")],
            no_alpha
            + [
                field("alpha_2", "DE"),
                field("alpha_3", "BAD"),
                field("alpha_3", "DEU"),
            ],
            no_alpha + [field("alpha_3", "DEU")],
            no_alpha
            + [field("alpha_2", "DE"), field("alpha_2", None), field("alpha_3", "DEU")],
            no_alpha,
        ]
        for fields in cases:
            p.db.execute(
                "update stage10_objects set fields=? where reference_object_id=?",
                [fields, original["reference_object_id"]],
            )
            for code in ("DE", "DEU", "XX", "ZZ", "", None, 123):
                assert p.country(code) == baseline_country(p, code)
        for malformed in (None, [None]):
            p.db.execute(
                "update stage10_objects set fields=? where reference_object_id=?",
                [malformed, original["reference_object_id"]],
            )
            for method in (p.country, lambda code: baseline_country(p, code)):
                with pytest.raises(TypeError):
                    method("DE")
        p.db.execute(
            "update stage10_objects set fields=? where reference_object_id=?",
            [original["fields"], original["reference_object_id"]],
        )
        p.db.execute(
            "insert into stage10_objects select * replace(? as reference_object_id) from stage10_objects where reference_object_id=?",
            [b.sha(b"invented duplicated country"), original["reference_object_id"]],
        )
        for method in (p.country, lambda code: baseline_country(p, code)):
            with pytest.raises(c.Stage12Error, match="B2_COUNTRY_AMBIGUOUS"):
                method("DE")
    finally:
        p.close()


def test_capability_batch_fresh_order_cardinality_and_bounded_rows(
    synthetic_inputs, tmp_path, monkeypatch
):
    p = project(synthetic_inputs, tmp_path)
    try:
        assert len(p.capability("DE")) == 19
        assert p.capability("DE") == baseline_capability(p, "DE")
        raw = contexts.sql_rows
        returned = []

        def observed(db, query, parameters=(), **kwargs):
            for row in raw(db, query, parameters, **kwargs):
                if "select req.ordinal" in query:
                    returned.append(row)
                yield row

        monkeypatch.setattr(contexts, "sql_rows", observed)
        p.db.execute(
            "create temp table saved_capabilities as select * from stage10_capabilities"
        )
        p.db.execute("delete from stage10_capabilities where question_catalog_id='Q01'")
        p.db.execute(
            "insert into stage10_capabilities select s.* from saved_capabilities s cross join range(100) where s.question_catalog_id='Q15'"
        )
        for method in (lambda country: baseline_capability(p, country), p.capability):
            with pytest.raises(
                s10.Stage10Error, match="STAGE10_EXACT_KEY_CARDINALITY_INVALID"
            ):
                method("DE")
        assert len(returned) == 1 and returned[0]["ordinal"] == 1
        p.db.execute("delete from stage10_capabilities")
        p.db.execute(
            "insert into stage10_capabilities select * from saved_capabilities"
        )
        p.db.execute(
            "insert into stage10_capabilities select s.* from saved_capabilities s cross join range(100) where s.question_catalog_id='Q01'"
        )
        returned.clear()
        with pytest.raises(
            s10.Stage10Error, match="STAGE10_EXACT_KEY_CARDINALITY_INVALID"
        ):
            p.capability("DE")
        assert len(returned) == 2 and all(x["ordinal"] == 0 for x in returned)
        assert all(
            set(row)
            == {
                "ordinal",
                "enabled",
                "granularity",
                "positive_authority",
                "negative_authority",
            }
            for row in returned
        )
        p.db.execute("delete from stage10_capabilities")
        p.db.execute(
            "insert into stage10_capabilities select * from saved_capabilities"
        )
        assert p.capability("DE") == baseline_capability(p, "DE")
        p.db.execute(
            "update stage10_capabilities set enabled=not enabled where question_catalog_id='Q01'"
        )
        assert p.capability("DE") == baseline_capability(p, "DE")
        assert p.capability("DE")[0][2] is False
    finally:
        p.close()


@pytest.mark.parametrize("path", ["execute", "fetchall", "iteration"])
@pytest.mark.parametrize("code", ["S12A_RUNTIME_LIMIT", "S12A_FREE_SPACE"])
def test_actual_sqlite_callback_restores_first_guard_identity(tmp_path, path, code):
    tmp_path.chmod(0o700)
    db = catalog.connect(tmp_path / "guard.sqlite")
    expected = c.Stage12Error(code)
    first = []
    armed = path == "execute"

    def check():
        if armed:
            raise expected

    check = local.remember_guard_failure(check, first)
    query = "with recursive n(x) as(values(1) union all select x+1 from n where x<100000) select x from n"
    try:
        with pytest.raises(c.Stage12Error) as raised:
            try:
                with io.cooperative_io(check):
                    if path == "execute":
                        db.execute("select sum(x) from (" + query + ")").fetchone()
                    else:
                        cursor = db.execute(query)
                        armed = True
                        if path == "fetchall":
                            cursor.fetchall()
                        else:
                            list(cursor)
            except sqlite3.OperationalError as error:
                assert error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
                assert first == [expected]
                frames = 0
                traceback = expected.__traceback__
                while traceback is not None:
                    frames += 1
                    traceback = traceback.tb_next
                assert frames <= 2  # Existing SQLite callback and I/O safe point.
                local.restore_sqlite_guard(error, first)
        assert raised.value is expected and first == []
        assert local.safe_failure(raised.value, "CATALOG_BUILD")["code"] == code
    finally:
        db.close()


def test_unrelated_sqlite_errors_and_unobserved_interrupt_are_not_guard_causes(
    tmp_path,
):
    tmp_path.chmod(0o700)
    db = catalog.connect(tmp_path / "unrelated.sqlite")
    first = [c.Stage12Error("S12A_RUNTIME_LIMIT")]
    try:
        try:
            db.execute("select * from invented_missing_table")
        except sqlite3.OperationalError as error:
            original = error
            with pytest.raises(sqlite3.OperationalError) as raised:
                local.restore_sqlite_guard(error, first)
        assert raised.value is original and first == []
        assert (
            local.safe_failure(raised.value, "CATALOG_BUILD")["code"]
            == "UPSTREAM_OR_UNCLASSIFIED_FAILURE"
        )
        db.set_progress_handler(lambda: 1, 1000)
        try:
            db.execute(
                "with recursive n(x) as(values(1) union all select x+1 from n where x<100000) select sum(x) from n"
            )
        except sqlite3.OperationalError as error:
            original = error
            assert error.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT
            with pytest.raises(sqlite3.OperationalError) as raised:
                local.restore_sqlite_guard(error, first)
        assert raised.value is original and first == []
    finally:
        db.close()


@pytest.mark.parametrize("value", [0, 9, 13, 65535, None, -1, 65536, True, "9", 9.0])
def test_safe_sqlite_numeric_discriminator_is_exact_bounded_and_secret_free(value):
    error = sqlite3.OperationalError("INVENTED_SECRET_SQL_CANARY")
    error.sqlite_errorcode = value
    error.sqlite_errorname = "INVENTED_SECRET_NAME_CANARY"
    report = local.safe_failure(error, "CATALOG_BUILD")
    assert report["sqlite_errorcode"] == (
        value if type(value) is int and 0 <= value <= 65535 else None
    )
    assert report["code"] == "UPSTREAM_OR_UNCLASSIFIED_FAILURE"
    assert "CANARY" not in json.dumps(report)
    assert "sqlite_errorname" not in report


def test_missing_and_non_sqlite_discriminators_are_unavailable():
    assert (
        local.safe_failure(
            sqlite3.OperationalError("INVENTED_CANARY"), "CATALOG_BUILD"
        )["sqlite_errorcode"]
        is None
    )
    other = ValueError("INVENTED_CANARY")
    other.sqlite_errorcode = 13
    assert local.safe_failure(other, "CATALOG_BUILD")["sqlite_errorcode"] is None
    sql = sqlite3.OperationalError("INVENTED_CANARY")
    sql.sqlite_errorcode = 9.0
    first = [c.Stage12Error("S12A_RUNTIME_LIMIT")]
    with pytest.raises(sqlite3.OperationalError) as raised:
        local.restore_sqlite_guard(sql, first)
    assert raised.value is sql and first == []


def build_invented_catalog(projection, path):
    intent = s10.full_intent("Invented profiling passage", "DE")
    core = s11.project(intent, s10.MODE)
    q = s11.semantic_id(s11.core_bytes(core))
    semantic = [{"query_semantic_id": q, "core": core}]
    hypotheses, mapping, families = [], [], []
    for source, role in projection.db.execute(
        "select stable_source_row_id_v1,stage08_representation from b2_occurrences order by 1,2"
    ).fetchall():
        u = s10.context_id(projection.accepted.context_binding, source, role)
        h = b.sha(u)
        hypotheses.append(
            {
                "hypothesis_id": h,
                "query_context_id": u,
                "stable_source_row_id_v1": source,
                "stage08_representation": role,
                "intent": intent,
                "selection_status": s10.MODE,
            }
        )
        mapping.append({"hypothesis_id": h, "query_semantic_id": q})
        families.append({"query_context_id": u, "hypothesis_id": h, "family": "Q1"})
    mapping.sort(key=lambda row: row["hypothesis_id"])
    binding = {
        "schema_version": "stage12_stage11_input_binding_b2_v1",
        "population_scope": b.SYNTHETIC,
        "manifest_sha256": H,
        "dataset_sha256": H,
        "semantic_sha256": s11.relation_digest("semantic_request", 1, semantic).hex(),
        "map_sha256": s11.relation_digest("hypothesis_request_map", 4, mapping).hex(),
        "semantic_count": 1,
        "map_count": 4,
        "source_count": 2,
        "upstream_acceptance_sha256": H,
    }
    built = catalog.Catalog.build(
        path,
        binding,
        semantics=lambda: iter(semantic),
        mapping=lambda: iter(mapping),
        hypotheses=lambda: iter(hypotheses),
        contexts=projection.rows,
        families=lambda: iter(families),
        authority=Authority(),
    )
    try:
        rows = [{**row, "channels": list(row["channels"])} for row in built.contexts(q)]
        return b.digest(
            {
                "core": built.core(q),
                "contexts": rows,
                "mapback": list(built.mapback()),
                "memberships": [
                    tuple(value.hex() for value in row)
                    for row in built.db.execute(
                        "select q,cell,source from membership order by q,cell,source"
                    )
                ],
            }
        )
    finally:
        built.close()


def test_bounded_many_country_real_catalog_equivalence_and_measurement(
    synthetic_inputs, tmp_path, monkeypatch
):
    p = project(synthetic_inputs, tmp_path, "UNKNOWN")
    try:
        base = contexts.one(
            p.db,
            "select * from stage10_objects where object_kind='ISO_COUNTRY' limit 1",
            [],
        )
        rows = []
        for index in range(240):
            fields = []
            for ordinal, (name, text) in enumerate(
                [
                    ("alpha_2", f"T{index:03}"),
                    ("alpha_3", f"TEST{index:03}"),
                    *(
                        (f"invented_field_{k}", f"Invented {index} {k}")
                        for k in range(20)
                    ),
                ]
            ):
                fields.append(
                    {
                        **base["fields"][0],
                        "field_name": name,
                        "original_value": text,
                        "ordinal": ordinal,
                    }
                )
            rows.append(
                {
                    **base,
                    "reference_object_id": b.sha(f"INVENTED_COUNTRY_{index}".encode()),
                    "fields": fields,
                }
            )
        p.db.register(
            "invented_countries",
            pa.Table.from_pylist(
                rows, schema=lineage.s9.relation_schema("reference_object")
            ),
        )
        p.db.execute("insert into stage10_objects select * from invented_countries")
        p.db.unregister("invented_countries")
        p.db.execute(
            "create temp table pad_basis as select * from stage10_objects where object_kind<>'ISO_COUNTRY' limit 1"
        )
        p.db.execute(
            "insert into stage10_objects select p.* replace(from_hex(sha256('invented-other-'||i::varchar)) as reference_object_id) from pad_basis p cross join range(25000) t(i)"
        )
        assert p.db.execute(
            "select count(*) from stage10_objects where object_kind='ISO_COUNTRY'"
        ).fetchone() == (249,)
        original_sql = contexts.sql_rows
        current_country, current_capability = p.country, p.capability
        measurements = []
        for label in ("baseline", "repaired"):
            counts = {
                "capability_queries": 0,
                "country_queries": 0,
                "country_rows": 0,
                "evidence_queries": 0,
            }

            def counted(db, query, parameters=(), **kwargs):
                category = (
                    "capability_queries"
                    if "stage10_capabilities" in query and "stage10_registry" in query
                    else "country_queries"
                    if "object_kind='ISO_COUNTRY'" in query
                    else "evidence_queries"
                    if "from b2_evidence " in query
                    else None
                )
                if category:
                    counts[category] += 1
                for row in original_sql(db, query, parameters, **kwargs):
                    if category == "country_queries":
                        counts["country_rows"] += 1
                    yield row

            p.country = (
                (lambda code: baseline_country(p, code))
                if label == "baseline"
                else current_country
            )
            p.capability = (
                (lambda country: baseline_capability(p, country))
                if label == "baseline"
                else current_capability
            )
            p.access = contexts.ReferenceAccess(p.db)
            digests = []
            started = time.perf_counter()
            with monkeypatch.context() as patcher:
                patcher.setattr(contexts, "sql_rows", counted)
                for index in range(3):
                    digests.append(
                        build_invented_catalog(p, tmp_path / f"{label}_{index}.sqlite")
                    )
            measurements.append(
                {
                    "case": label,
                    "contexts": 12,
                    "seconds": round(time.perf_counter() - started, 6),
                    "counts": counts,
                    "logical_catalog_sha256": digests[0],
                }
            )
            assert len(set(digests)) == 1
        before, after = measurements
        assert before["logical_catalog_sha256"] == after["logical_catalog_sha256"]
        assert (
            before["counts"]["capability_queries"] == 204
            and after["counts"]["capability_queries"] == 12
        )
        assert (
            before["counts"]["country_queries"]
            == after["counts"]["country_queries"]
            == 24
        )
        assert (
            before["counts"]["country_rows"] == 5976
            and after["counts"]["country_rows"] == 24
        )
        assert (
            before["counts"]["evidence_queries"]
            == after["counts"]["evidence_queries"]
            == 12
        )
        print(
            json.dumps(
                {
                    "scope": "INVENTED_REAL_PROJECTION_DUCKDB_SQLITE",
                    "protected_rows": 0,
                    "historical_cause_inferred": False,
                    "measurements": measurements,
                },
                sort_keys=True,
            )
        )
    finally:
        p.close()

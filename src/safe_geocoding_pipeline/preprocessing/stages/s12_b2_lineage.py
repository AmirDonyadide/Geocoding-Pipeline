"""Concrete bounded Stage8/9 occurrence/witness projection for Stage12.

Consumes exact accepted artifacts through their existing guarded readers. It
never opens HOLDOUT, reruns reference questions, invents aliases or maps an
arbitrary source region to admin1. Unknown interpretation stays unevaluable.
"""

from . import s12_b2_contract as b
from . import s12_b2_allocation_limits as limits
from . import s12_storage as io
from . import s10_query_contract as s10
from . import s10_query_input as inputs
from . import s10_query_contexts as contexts
from . import s10_query_transliteration as unicode16
from . import s09_reference_contract as s9
from . import s11_semantic_io as sqlio


def shape_bytes(row):
    def convert(x):
        if isinstance(x, bytes):
            return {"bytes": x.hex()}
        if isinstance(x, dict):
            return {k: convert(v) for k, v in x.items()}
        if isinstance(x, (tuple, list)):
            return [convert(v) for v in x]
        return x

    return b.canonical(convert(row))


_PRODUCTION_CONSTRUCTION = object()
_TEST_CONSTRUCTION = object()


class LineageProjection:
    @classmethod
    def synthetic(cls, accepted, **kwargs):
        b.require(
            accepted.binding == {"SYNTHETIC_ONLY": True},
            "B2_SYNTHETIC_LINEAGE_REQUIRED",
        )
        return cls(accepted, _construction=_TEST_CONSTRUCTION, **kwargs)

    @classmethod
    def open(
        cls,
        *,
        stage08_root,
        stage09_root,
        stage06_root,
        scratch,
        memory_bytes,
        authority,
        interpretation,
        interpretation_sha256,
    ):
        authority.require(
            "protected_lineage_input", interpretation_sha256, interpretation
        )

        # Existing consume_inputs enforces Goethe/DEVELOPMENT and all accepted identities.
        def reload():
            return inputs.consume_inputs(stage08_root, stage09_root, stage06_root)

        accepted = reload()
        return cls(
            accepted,
            _construction=_PRODUCTION_CONSTRUCTION,
            scratch=scratch,
            memory_bytes=memory_bytes,
            reload_accepted=reload,
            authority=authority,
            interpretation=interpretation,
            interpretation_sha256=interpretation_sha256,
        )

    def __init__(
        self,
        accepted,
        *,
        scratch,
        memory_bytes,
        reload_accepted,
        authority,
        interpretation,
        interpretation_sha256,
        _construction,
    ):
        b.require(
            _construction is _PRODUCTION_CONSTRUCTION
            or _construction is _TEST_CONSTRUCTION,
            "B2_LINEAGE_CONSTRUCTION",
        )
        self.population_scope = (
            b.DEVELOPMENT if _construction is _PRODUCTION_CONSTRUCTION else b.SYNTHETIC
        )
        self.accepted = accepted
        if self.population_scope == b.DEVELOPMENT:
            self.assert_accepted_chain()
        b.require(
            set(interpretation)
            == {"country_namespace", "candidate_levels", "source_levels"},
            "B2_INTERPRETATION_FIELDS",
        )
        b.require(
            interpretation["country_namespace"]
            in ("ISO_ALPHA2", "ISO_ALPHA3", "UNKNOWN"),
            "B2_COUNTRY_NAMESPACE",
        )
        allowed = {"locality", "localadmin", "county", "region", "macroregion"}
        b.require(
            set(interpretation["candidate_levels"]) == allowed
            and set(interpretation["source_levels"]) == {"city", "region"},
            "B2_INTERPRETATION_FIELDS",
        )
        b.require(
            all(
                type(x) is str and x
                for x in [
                    *interpretation["candidate_levels"].values(),
                    *interpretation["source_levels"].values(),
                ]
            ),
            "B2_INTERPRETATION_FIELDS",
        )
        b.require(
            b.digest(interpretation) == interpretation_sha256, "B2_INTERPRETATION_HASH"
        )
        authority.require(
            "witness_interpretation", interpretation_sha256, interpretation
        )
        self.accepted, self.reload, self.interpretation = (
            accepted,
            reload_accepted,
            interpretation,
        )
        self.binding_sha256 = b.digest(
            {
                "accepted_input_sha256": accepted.identifier.hex(),
                "interpretation_sha256": interpretation_sha256,
                "algorithm": "stage12_accepted_lineage_projection_b2_v1",
            }
        )
        io.reserve(scratch)
        b.uint(memory_bytes, True)
        self.db = limits.duck_connect(
            sqlio.connect, scratch, memory=str(memory_bytes) + "B", threads=1
        )
        accepted.register_views(self.db)
        # Explicit external keyed tables; no full reference object collection.
        for name, source, key in [
            ("registry", "reference_registry", "reference_version_id"),
            ("capabilities", "reference_capability", "capability_id"),
            ("objects", "reference_object", "reference_object_id"),
            ("members", "reference_match_member", "match_set_id"),
        ]:
            self.db.execute(
                f"create table stage10_{name} as select * from {source} order by {key}"
            )
            self.db.execute(f"create index b2_{name}_key on stage10_{name}({key})")
        self.access = contexts.ReferenceAccess(self.db)
        self.db.execute(
            "create table b2_evidence as select * from candidate_reference_evidence order by stage06_exact_candidate_id,stable_source_row_id_v1,evidence_id"
        )
        self.db.execute(
            "create index b2_evidence_key on b2_evidence(stage06_exact_candidate_id,stable_source_row_id_v1)"
        )
        self.validate_source_relations()
        self.db.execute(
            "create table b2_occurrences as select o.*,s as source,l as lines from stage08_occurrence o join source_candidate_map s using(stable_source_row_id_v1) join stage06_row_map l using(stable_source_row_id_v1)"
        )
        b.require(
            self.db.execute("select count(*) from b2_occurrences").fetchone()[0]
            == self.db.execute("select count(*) from stage08_occurrence").fetchone()[0],
            "B2_LINEAGE_TOTALITY",
        )
        self.validate()

    def validate_source_relations(self):
        """Check source population before any occurrence/query inner join.

        Accepted source rows without a representation remain in this population.
        The expected occurrence relation is reconstructed only from the accepted
        representation slots; no query outcome selects a source row or role.
        """
        checks = (
            "select count(*) from (select stable_source_row_id_v1 from source_candidate_map group by 1 having count(*)<>1)",
            "select count(*) from (select stable_source_row_id_v1 from stage06_row_map group by 1 having count(*)<>1)",
            "select count(*) from source_candidate_map s full outer join stage06_row_map l using(stable_source_row_id_v1) where s.stable_source_row_id_v1 is null or l.stable_source_row_id_v1 is null or s.stage06_standard_exact_candidate_id is distinct from l.stage06_standard_exact_candidate_id or s.stage06_native_exact_candidate_id is distinct from l.stage06_native_exact_candidate_id",
            "select count(*) from source_candidate_map where (stage08_standard_representation_status='PRESENT') is distinct from (stage06_standard_exact_candidate_id is not null) or (stage08_native_representation_status='PRESENT') is distinct from (stage06_native_exact_candidate_id is not null)",
        )
        for query in checks:
            b.require(self.db.execute(query).fetchone() == (0,), "B2_SOURCE_POPULATION")
        expected = """select stable_source_row_id_v1,'STANDARD' as stage08_representation,
            stage06_standard_exact_candidate_id as stage06_exact_candidate_id
            from source_candidate_map where stage08_standard_representation_status='PRESENT'
            union all select stable_source_row_id_v1,'NATIVE',stage06_native_exact_candidate_id
            from source_candidate_map where stage08_native_representation_status='PRESENT'"""
        actual = "select stable_source_row_id_v1,stage08_representation,stage06_exact_candidate_id from stage08_occurrence"
        for left, right in ((actual, expected), (expected, actual)):
            b.require(
                self.db.execute(
                    f"select count(*) from (({left}) except all ({right}))"
                ).fetchone()
                == (0,),
                "B2_OCCURRENCE_TOTALITY",
            )
        b.require(
            self.db.execute(
                "select count(*) from (select stable_source_row_id_v1,stage08_representation from stage08_occurrence group by all having count(*)<>1)"
            ).fetchone()
            == (0,),
            "B2_OCCURRENCE_TOTALITY",
        )
        if self.population_scope == b.DEVELOPMENT:
            b.require(
                self.db.execute("select count(*) from source_candidate_map").fetchone()
                == (35000,),
                "B2_SOURCE_POPULATION",
            )
            from .s01_identity import stable_source_row_id_v1

            for row in self.source_rows():
                b.require(
                    stable_source_row_id_v1(
                        bytes.fromhex(row["source_file_sha256"]),
                        row["source_logical_record_number"],
                    ).hex()
                    == row["stable_source_row_id_v1"],
                    "B2_SOURCE_LINEAGE",
                )

    def source_rows(self):
        """Exact original identity fields, independent of generated contexts."""
        for row in contexts.sql_rows(
            self.db,
            "select id,source_file,source_logical_record_number,stable_source_row_id_v1,source_file_sha256 from source_candidate_map order by stable_source_row_id_v1",
        ):
            yield {
                **row,
                "stable_source_row_id_v1": row["stable_source_row_id_v1"].hex(),
                "source_file_sha256": row["source_file_sha256"].hex(),
            }

    def assert_accepted_chain(self):
        b.require(
            self.population_scope == b.DEVELOPMENT
            and type(self.accepted) is inputs.AcceptedInputs,
            "B2_ACCEPTED_LINEAGE_REQUIRED",
        )
        value = self.accepted.binding
        expected = {
            "stage08": inputs.accepted8.STAGE08_MANIFEST_SHA256,
            "stage09": inputs.STAGE09_MANIFEST,
            "stage06_row_map": inputs.STAGE06_MANIFEST,
        }
        b.require(
            value.get("split") == "DEVELOPMENT"
            and all(
                value.get(k, {}).get("manifest_sha256") == v
                for k, v in expected.items()
            )
            and value["stage09"].get("reference_pack", {}).get("manifest_sha256")
            == inputs.PUBLIC_MANIFEST,
            "B2_ACCEPTED_LINEAGE_REQUIRED",
        )

    def validate(self):
        if self.population_scope == b.DEVELOPMENT:
            self.assert_accepted_chain()
        current = self.reload()
        b.require(
            current.binding == self.accepted.binding
            and current.identifier == self.accepted.identifier,
            "B2_LINEAGE_CHANGED",
        )
        self.validate_source_relations()

    def country(self, code):
        # Exact accepted ISO country object fields, not a hand-maintained mapping.
        if not isinstance(code, str) or not code:
            return None, None
        wanted = s9.normalize(s9.ISO_NORM, code)
        found = None
        for row in contexts.sql_rows(
            self.db, "select * from stage10_objects where object_kind='ISO_COUNTRY'"
        ):
            fields = {x["field_name"]: x["original_value"] for x in row["fields"]}
            if wanted in (fields.get("alpha_2"), fields.get("alpha_3")):
                b.require(found is None, "B2_COUNTRY_AMBIGUOUS")
                found = fields
        if found is None:
            return None, None
        namespace = self.interpretation["country_namespace"]
        return found.get("alpha_2"), found.get(
            "alpha_2" if namespace == "ISO_ALPHA2" else "alpha_3"
        ) if namespace != "UNKNOWN" else None

    def capability(self, country):
        vector = []
        for question in s9.CATALOG:
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
                    self.db,
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

    def source_channels(self, source, country, candidate_country):
        sid = source["stable_source_row_id_v1"]
        for (
            kind,
            field,
            source_field,
            value,
            granularity,
            candidate_granularity,
            method,
        ) in (
            (
                "SOURCE_COUNTRY",
                "country_a",
                "country_iso_code",
                candidate_country,
                "COUNTRY",
                "COUNTRY",
                s9.ISO_NORM if candidate_country else s9.NO_NORM,
            ),
            (
                "SOURCE_POSTCODE",
                "postalcode",
                "postcode",
                source["stage03_clean_postcode"],
                "FULL_POSTCODE",
                "FULL_POSTCODE",
                s9.SEPARATOR_NORM
                if country in s9.POSTCODE_SEPARATORS
                else s9.EXACT_NORM,
            ),
            (
                "SOURCE_LOCALITY",
                "locality",
                "city",
                source["stage03_clean_city"],
                self.interpretation["source_levels"]["city"],
                self.interpretation["candidate_levels"]["locality"],
                s9.NAME_NORM,
            ),
            (
                "SOURCE_ADMIN",
                "region",
                "region_in_country",
                source["stage03_clean_region_in_country"],
                self.interpretation["source_levels"]["region"],
                self.interpretation["candidate_levels"]["region"],
                s9.NAME_NORM,
            ),
        ):
            yield {
                "kind": kind,
                "candidate_field": field,
                "comparison_method": method,
                "source_value": value,
                "granularity": granularity,
                "candidate_granularity": candidate_granularity,
                "origin_claim_key": b.sha(b.framed([sid, source_field])).hex(),
                "ancestry_group": "ORBIS_SOURCE",
                "dependence_class": "SELF/DERIVED_FROM",
                "positive_reference": False,
                "origin_record_sha256": b.sha(shape_bytes(source)).hex(),
            }

    def channels(self, occurrence, country, candidate_country):
        source = occurrence["source"]
        yield from self.source_channels(source, country, candidate_country)
        rows = contexts.sql_rows(
            self.db,
            "select * from b2_evidence where stage06_exact_candidate_id=? and ((evidence_scope='SOURCE_ROW' and stable_source_row_id_v1=?) or (evidence_scope='PARSER_CANDIDATE' and stable_source_row_id_v1 is null)) order by evidence_id",
            [
                occurrence["stage06_exact_candidate_id"],
                occurrence["stable_source_row_id_v1"],
            ],
        )
        for row in rows:
            if row["question_catalog_id"] not in (
                "Q01",
                "Q04",
                "Q05",
                "Q06",
                "Q07",
                "Q08",
                "Q09",
                "Q10",
                "Q11",
            ):
                continue
            # Unevaluable/nonpositive accepted states remain represented explicitly;
            # they cannot manufacture a compatibility or contradiction token.
            cap = (
                self.access.capability(row["capability_id"])
                if row["capability_id"]
                else None
            )
            if cap:
                b.require(
                    cap["reference_version_id"] == row["reference_version_id"]
                    and cap["question_catalog_id"] == row["question_catalog_id"],
                    "B2_WITNESS_BINDING",
                )
            registry = (
                self.access.registry(row["reference_version_id"])
                if row["reference_version_id"]
                else None
            )
            ancestry = (
                b.sha(
                    shape_bytes(
                        sorted(
                            registry["lineage"],
                            key=lambda x: (x["token"], x["parent_token"]),
                        )
                    )
                ).hex()
                if registry
                else "UNKNOWN"
            )
            # Unknown/shared external importer ancestry is never disjoint by default.
            dependence = (
                "POSSIBLE_SHARED" if registry and registry["lineage"] else "UNKNOWN"
            )
            for witness in self.access.witnesses(row):
                obj = self.access.object(witness["reference_object_id"])
                b.require(
                    obj["reference_version_id"] == row["reference_version_id"],
                    "B2_WITNESS_BINDING",
                )
                for pointer in witness["fields"]:
                    target = self.access.object(pointer["reference_object_id"])
                    b.require(
                        target["reference_version_id"] == row["reference_version_id"],
                        "B2_WITNESS_BINDING",
                    )
                    values = [
                        x
                        for x in target["fields"]
                        if x["field_name"] == pointer["field_name"]
                        and x["ordinal"] == pointer["ordinal"]
                    ]
                    b.require(len(values) == 1, "B2_WITNESS_POINTER")
                    field = values[0]
                    name = field["field_name"]
                    role = (
                        "COUNTRY"
                        if name in ("alpha_2", "alpha_3")
                        else "POSTCODE"
                        if name in ("postal_code", "postcode")
                        else "LOCALITY"
                        if name in ("place_name", "locality", "city")
                        else "LOCALITY"
                        if target["object_kind"]
                        in ("FORMAT_LOCALITY", "FORMAT_DEPENDENT_LOCALITY")
                        and field["alias_role"]
                        in ("EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS")
                        else "ADMIN"
                        if name.startswith("admin_name")
                        or target["object_kind"] == "ISO_ADMIN"
                        or (
                            target["object_kind"] == "FORMAT_ADMIN"
                            and field["alias_role"]
                            in ("EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS")
                        )
                        else None
                    )
                    if role is None:
                        continue
                    args = [
                        a
                        for a in row["arguments"]
                        if a["role"] == ("COUNTRY_CODE" if role == "COUNTRY" else role)
                    ]
                    for arg in args:
                        candidate_field = {
                            "COUNTRY": "country_a",
                            "POSTCODE": "postalcode",
                            "LOCALITY": "locality",
                            "ADMIN": "region",
                        }[role]
                        expected_level = (
                            "COUNTRY"
                            if role == "COUNTRY"
                            else "FULL_POSTCODE"
                            if role == "POSTCODE"
                            else self.interpretation["candidate_levels"][
                                candidate_field
                            ]
                        )
                        level = (
                            "COUNTRY"
                            if role == "COUNTRY"
                            else "FULL_POSTCODE"
                            if role == "POSTCODE"
                            and cap
                            and cap["granularity"] == "FULL_POSTCODE"
                            else field["geographic_level"] or "UNKNOWN"
                        )
                        value = field["original_value"]
                        if role == "COUNTRY":
                            _, value = self.country(value)
                        positive = (
                            row["evidence_scope"] == "SOURCE_ROW"
                            and row["result_state"] == "SUPPORTED"
                            and witness["witness_role"] == "SUPPORT"
                            and cap is not None
                            and cap["enabled"]
                            and cap["positive_authority"]
                            and cap["country_scope"] in ("GLOBAL", country)
                            and target["country_code"] in (None, country)
                        )
                        yield {
                            "kind": "ACCEPTED_REFERENCE",
                            "candidate_field": candidate_field,
                            "comparison_method": arg["normalization_id"],
                            "source_value": value,
                            "granularity": level,
                            "candidate_granularity": expected_level,
                            "origin_claim_key": b.sha(
                                b.framed(
                                    [
                                        occurrence["stable_source_row_id_v1"],
                                        row["question_catalog_id"],
                                        arg["origin_relation"],
                                        arg["origin_field"],
                                        arg["component_ordinal"],
                                    ]
                                )
                            ).hex(),
                            "ancestry_group": ancestry,
                            "dependence_class": dependence,
                            "positive_reference": positive,
                            "origin_record_sha256": b.sha(
                                shape_bytes(
                                    {
                                        "evidence": row,
                                        "witness": witness,
                                        "pointer": pointer,
                                    }
                                )
                            ).hex(),
                            "origin_detail": {
                                "accepted_evidence_id": row["evidence_id"].hex(),
                                "question": row["question_catalog_id"],
                                "result_state": row["result_state"],
                                "witness_object_id": witness[
                                    "reference_object_id"
                                ].hex(),
                                "field_object_id": pointer["reference_object_id"].hex(),
                                "field_name": pointer["field_name"],
                                "field_ordinal": pointer["ordinal"],
                                "argument_origin_relation": arg["origin_relation"],
                                "argument_origin_field": arg["origin_field"],
                                "argument_component_ordinal": arg["component_ordinal"],
                            },
                        }

    def rows(self):
        for row in contexts.sql_rows(
            self.db,
            "select * from b2_occurrences order by stable_source_row_id_v1,stage08_representation",
        ):
            role = row["stage08_representation"]
            source = row["source"]
            lines = row["lines"]
            fields = inputs.source_line_fields(role)
            text = lines[fields[5]]
            b.require(
                lines[fields[0]] == row["stage06_exact_candidate_id"]
                and text == " ".join(lines[x] for x in fields[1:5] if lines[x]),
                "B2_SOURCE_LINEAGE",
            )
            country, code = self.country(source["stage03_clean_country_iso_code"])
            scripts = {unicode16.scripts().script_for(ch) for ch in text} - {
                "Common",
                "Inherited",
            }
            yield {
                "query_context_id": s10.context_id(
                    self.accepted.context_binding, row["stable_source_row_id_v1"], role
                ).hex(),
                "stable_source_row_id_v1": row["stable_source_row_id_v1"].hex(),
                "country": country or "UNRESOLVED",
                "script": "COMMON_ONLY"
                if not scripts
                else next(iter(scripts))
                if len(scripts) == 1
                else "MIXED",
                "capability": self.capability(country),
                "completeness": [
                    text != "",
                    source["stage03_clean_postcode"] != "",
                    source["stage03_clean_city"] != "",
                    source["stage03_clean_region_in_country"] != "",
                ],
                "representation": role,
                "channels": self.channels(row, country, code),
                "origin_sha256": b.sha(
                    shape_bytes({"binding": self.binding_sha256, "occurrence": row})
                ).hex(),
            }

    def close(self):
        self.db.close()

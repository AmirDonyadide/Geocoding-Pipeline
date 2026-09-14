"""Public frozen assets and invented inputs only; no protected data access."""

import json
from pathlib import Path
import re

import duckdb
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_pack as p
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_evaluator as e
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_questions as q

c.require_runtime()
repo = Path(__file__).resolve().parents[2]
raw_root = repo / "external_data/stage09_reference_freeze_v1"
lock = p.verify_lock(
    raw_root, repo / "docs/scientific_assets/stage09_reference_pack_lock_v1.json"
)
registry = p.registry_rows(lock)
raw = p.PublicInputs(raw_root, lock, registry)
data = raw.json_data(c.LIA)
iso, metadata = raw.small_objects()
matrix = p.matrix_capabilities(lock, registry)
lia_version = next(
    x["reference_version_id"] for x in registry if x["reference_id"] == c.LIA
)
rules = p.metadata_rule_capabilities(
    metadata, [x for x in matrix if x["reference_version_id"] == lia_version]
)
results = []
with duckdb.connect() as db:
    view = e.SmallReferenceView(registry, matrix + rules, iso + metadata, connection=db)

    def evaluate(
        case, country, question, postcode="", admin="", locality="", expected=None
    ):
        candidate = {
            "stage06_exact_candidate_id": b"c" * 32,
            "stage07_trusted_country_iso_code": country.lower() if country else None,
            "stage07_country_provenance_status": "COUNTRY_UNANIMOUS_VALID"
            if country
            else "COUNTRY_MISSING",
        }
        source = {
            "stable_source_row_id_v1": b"s" * 32,
            "stage06_standard_exact_candidate_id": b"c" * 32,
            "stage06_native_exact_candidate_id": b"c" * 32,
            "stage03_clean_country_iso_code": country or "",
            "stage03_clean_postcode": postcode,
            "stage03_clean_region_in_country": admin,
            "stage03_clean_city": locality,
        }
        item = next(
            x
            for x in q.source_questions(source, candidate)
            if x.question_id == question
        )
        family = c.ISO if question == "Q02" else c.LIA
        prepared = view.prepare(item, family)
        answer = view.lookup_small(prepared)
        assert (answer.state, answer.reason) == expected, (
            case,
            answer.state,
            answer.reason,
        )
        results.append(
            {
                "case": case,
                "country": country,
                "question": question,
                "state": answer.state,
                "reason": answer.reason,
            }
        )

    S = ("SUPPORTED", "EXPLICIT_RULE_SUPPORT")
    C = ("CONTRADICTED", "EXPLICIT_RULE_CONFLICT")
    evaluate("valid_with_leading_zero", "IT", "Q04", "00123", expected=S)
    evaluate("short_numeric", "IT", "Q04", "0123", expected=C)
    evaluate("outer_whitespace_preserved", "IT", "Q04", " 00123 ", expected=C)
    evaluate("wrong_hyphen_boundary", "IT", "Q04", "00-123", expected=C)
    evaluate("brazil_optional_hyphen", "BR", "Q04", "00123-456", expected=S)
    evaluate("brazil_no_hyphen", "BR", "Q04", "00123456", expected=S)
    evaluate("sweden_optional_space", "SE", "Q04", "001 23", expected=S)
    evaluate("sweden_nonbreaking_space", "SE", "Q04", "001\u00a023", expected=C)
    evaluate("unicode_digits_not_coerced", "IT", "Q04", "００１２３", expected=C)
    evaluate(
        "disabled_regex_bahrain",
        "BH",
        "Q04",
        "1234",
        expected=("NOT_EVALUABLE", "PATTERN_DIALECT_UNSUPPORTED"),
    )
    evaluate(
        "china_subnational_exceptions",
        "CN",
        "Q04",
        "123456",
        expected=("NOT_EVALUABLE", "ALTERNATE_RULE_SEMANTICS_UNSUPPORTED"),
    )
    evaluate(
        "country_without_rule",
        "AQ",
        "Q04",
        "00123",
        expected=("NOT_EVALUABLE", "COMPONENT_CAPABILITY_MISSING"),
    )
    evaluate(
        "missing_country",
        "",
        "Q04",
        "00123",
        expected=("NOT_EVALUABLE", "COUNTRY_CONTEXT_UNRESOLVED"),
    )
    evaluate(
        "country_without_admin_subkeys",
        "DE",
        "Q10",
        admin="Invented Region",
        expected=("NOT_EVALUABLE", "COMPONENT_CAPABILITY_MISSING"),
    )
    evaluate(
        "country_with_subkeys",
        "US",
        "Q10",
        admin="CA",
        expected=("SUPPORTED", "EXACT_REFERENCE_SUPPORT"),
    )
    evaluate(
        "unknown_enum_is_open_miss",
        "US",
        "Q10",
        admin="Invented Region",
        expected=("NOT_FOUND", "VALUE_ABSENT_FROM_REFERENCE"),
    )
    evaluate("prefix_allowed", "US", "Q08", "90123", admin="CA", expected=S)
    evaluate(
        "prefix_alternation_second_branch", "US", "Q08", "96123", admin="CA", expected=S
    )
    evaluate("prefix_conflict", "US", "Q08", "00123", admin="CA", expected=C)
    evaluate(
        "prefix_requires_full_format",
        "US",
        "Q08",
        "90",
        admin="CA",
        expected=("NOT_EVALUABLE", "COUNTRY_FORMAT_PREREQUISITE_FAILED"),
    )
    evaluate(
        "recognized_full_iso_owner",
        "US",
        "Q02",
        admin="US-CA",
        expected=("SUPPORTED", "EXPLICIT_CODE_COUNTRY_SUPPORT"),
    )
    evaluate(
        "positive_iso_owner_conflict",
        "IT",
        "Q02",
        admin="US-CA",
        expected=("CONTRADICTED", "EXPLICIT_CODE_COUNTRY_CONFLICT"),
    )
    evaluate(
        "unrecognized_iso_not_contradiction",
        "IT",
        "Q02",
        admin="US-FAKE",
        expected=("NOT_EVALUABLE", "EXPLICIT_CODE_NOT_IDENTIFIED"),
    )
    # Independent enabled-country expansion oracle for frozen Q04, derived from
    # country roots and any nonempty alternate field in that country's tree.
    countries = set(
        next(x["countries"] for x in registry if x["reference_id"] == c.ISO)
    )
    independently_enabled = set()
    for country in countries:
        rule = data[country].get("zip")
        alternate = any(
            any(
                node.get(field) and node[field].strip("~")
                for field in ("xzip", "sub_xzips")
            )
            for key, node in data.items()
            if key.split("/")[0].split("--")[0] == country
        )
        if rule and country != "BH" and not alternate:
            re.compile(rule, re.ASCII)
            independently_enabled.add(country)
    actual = {
        r["country_scope"]
        for r in matrix
        if r["reference_version_id"] == lia_version
        and r["question_catalog_id"] == "Q04"
        and r["enabled"]
    }
    assert actual == independently_enabled
    print(
        json.dumps(
            {
                "checks": results,
                "independent_enabled_q04_countries": len(actual),
                "status": "PASS",
            },
            sort_keys=True,
            indent=2,
        )
    )

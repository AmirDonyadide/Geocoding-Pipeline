"""Scoped use of accepted Stage 9 witnesses; never rerun a reference lookup."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from . import s09_reference_contract as s9
from . import s09_reference_questions as questions
from . import s10_query_contract as c


class ReferenceAccess(Protocol):
    def capability(self, identifier: bytes) -> Mapping[str, Any]: ...
    def object(self, identifier: bytes) -> Mapping[str, Any]: ...
    def witnesses(self, evidence: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]: ...


@dataclass(frozen=True)
class FieldPolicy:
    country: str | None
    locality: str | None
    postcode: str | None
    locality_reasons: tuple[str, ...]
    postcode_reasons: tuple[str, ...]
    contradiction_capabilities: tuple[str, ...]


def _capability(
    row: Mapping[str, Any],
    access: ReferenceAccess,
    *,
    negative: bool = False,
    rule: bool = False,
) -> Mapping[str, Any] | None:
    identifier = row["rule_capability_id" if rule else "capability_id"]
    if identifier is None:
        return None
    cap = access.capability(identifier)
    c.require(
        cap["capability_id"] == identifier
        and cap["reference_version_id"] == row["reference_version_id"]
        and cap["question_catalog_id"] == row["question_catalog_id"],
        "STAGE10_REFERENCE_CAPABILITY_LINEAGE_INVALID",
    )
    c.require(
        rule or cap["scope_locator"] == "COUNTRY_MATRIX",
        "STAGE10_REFERENCE_MATRIX_SCOPE_INVALID",
    )
    if (
        not cap["enabled"]
        or not cap["negative_authority" if negative else "positive_authority"]
    ):
        return None
    if negative:
        c.require(row["reference_slot"] == s9.LIA, "STAGE10_NEGATIVE_AUTHORITY_INVALID")
    return cap


def _field_matches(
    witness: Mapping[str, Any],
    access: ReferenceAccess,
    object_id: bytes,
    field_name: str,
    value: str,
    method: str,
) -> bool:
    for pointer in witness["fields"]:
        if (
            pointer["reference_object_id"] != object_id
            or pointer["field_name"] != field_name
        ):
            continue
        obj = access.object(object_id)
        fields = [
            f
            for f in obj["fields"]
            if f["field_name"] == field_name and f["ordinal"] == pointer["ordinal"]
        ]
        c.require(len(fields) == 1, "STAGE10_REFERENCE_FIELD_LOCATOR_INVALID")
        if s9.normalize(method, fields[0]["original_value"]) == s9.normalize(
            method, value
        ):
            return True
    return False


def _supported(
    row: Mapping[str, Any],
    access: ReferenceAccess,
    source: Mapping[str, Any],
    country: str,
    *,
    locality: bool = False,
    postcode: bool = False,
) -> bool:
    if row["result_state"] != "SUPPORTED":
        return False
    cap = _capability(row, access)
    if cap is None or cap["country_scope"] != country:
        return False
    if postcode and cap["granularity"] != "FULL_POSTCODE":
        return False
    for witness in access.witnesses(row):
        obj = access.object(witness["reference_object_id"])
        c.require(
            obj["reference_version_id"] == row["reference_version_id"],
            "STAGE10_WITNESS_VERSION_MISMATCH",
        )
        if witness["witness_role"] != "SUPPORT" or obj["country_code"] != country:
            continue
        if row["reference_slot"] == s9.GN:
            if obj["object_kind"] != "POSTAL_ASSOCIATION":
                continue
            names = {
                p["field_name"]
                for p in witness["fields"]
                if p["reference_object_id"] == obj["reference_object_id"]
            }
            if locality and "place_name" not in names:
                continue
            if postcode and "postal_code" not in names:
                continue
            # Same-record Q06 support is already established in accepted S9.
            # Verify exact witnessed field values using the bound argument rule.
            success = True
            for needed, role, field, source_field in (
                (locality, "LOCALITY", "place_name", "stage03_clean_city"),
                (postcode, "POSTCODE", "postal_code", "stage03_clean_postcode"),
            ):
                if not needed:
                    continue
                arg = next(a for a in row["arguments"] if a["role"] == role)
                pointers = [
                    p
                    for p in witness["fields"]
                    if p["reference_object_id"] == obj["reference_object_id"]
                    and p["field_name"] == field
                ]
                found = False
                for pointer in pointers:
                    for entry in obj["fields"]:
                        if (
                            entry["field_name"] == field
                            and entry["ordinal"] == pointer["ordinal"]
                        ):
                            found |= s9.normalize(
                                arg["normalization_id"],
                                entry["original_value"],
                                country,
                            ) == s9.normalize(
                                arg["normalization_id"], source[source_field], country
                            )
                success &= found
            if success:
                return True
        elif (
            row["reference_slot"] == s9.LIA
            and locality
            and not postcode
            and obj["object_kind"] == "FORMAT_LOCALITY"
        ):
            for pointer in witness["fields"]:
                if pointer["reference_object_id"] != obj["reference_object_id"]:
                    continue
                for field in obj["fields"]:
                    if (
                        field["field_name"] == pointer["field_name"]
                        and field["ordinal"] == pointer["ordinal"]
                        and field["alias_role"]
                        in ("EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS")
                    ):
                        if s9.normalize(
                            s9.NAME_NORM, field["original_value"]
                        ) == s9.normalize(s9.NAME_NORM, source["stage03_clean_city"]):
                            return True
    return False


def _postcode_conflict_certificate(
    row: Mapping[str, Any],
    rule: Mapping[str, Any],
    access: ReferenceAccess,
    country: str,
    source: Mapping[str, Any],
) -> None:
    witnesses = iter(access.witnesses(row))
    witness = next(witnesses, None)
    c.require(
        witness is not None and next(witnesses, None) is None,
        "STAGE10_POSTCODE_CONTRADICTION_WITNESS_INVALID",
    )
    assert witness is not None
    obj = access.object(witness["reference_object_id"])
    c.require(
        witness["witness_role"] == "CONTRADICTION"
        and obj["country_code"] == country
        and obj["reference_version_id"] == row["reference_version_id"]
        and obj["asset_id"] == row["reference_asset_id"],
        "STAGE10_POSTCODE_CONTRADICTION_WITNESS_INVALID",
    )
    pointers = witness["fields"]
    selected = []
    for pointer in pointers:
        pointed = access.object(pointer["reference_object_id"])
        fields = [
            f
            for f in pointed["fields"]
            if f["field_name"] == pointer["field_name"]
            and f["ordinal"] == pointer["ordinal"]
        ]
        c.require(
            len(fields) == 1
            and pointed["country_code"] == country
            and pointed["reference_version_id"] == row["reference_version_id"],
            "STAGE10_POSTCODE_CONTRADICTION_WITNESS_INVALID",
        )
        selected.append((pointed, fields[0]))
    if row["question_catalog_id"] == "Q04":
        c.require(
            obj["object_kind"] == "FORMAT_COUNTRY"
            and obj["source_locator"] == country
            and rule["scope_locator"] == country + "/zip"
            and len(selected) == 1
            and selected[0][0]["reference_object_id"] == obj["reference_object_id"]
            and selected[0][1]["field_name"] == "zip"
            and selected[0][1]["source_field_locator"] == country + "/zip"
            and bool(selected[0][1]["original_value"]),
            "STAGE10_POSTCODE_CONTRADICTION_WITNESS_INVALID",
        )
        return
    prefixes = [
        f
        for f in obj["fields"]
        if f["field_name"] in ("zip", "sub_zips") and f["original_value"]
    ]
    expected_scope = "PREFIX_BUNDLE:" + json.dumps(
        [
            obj["source_locator"],
            country + "/zip",
            *sorted(f["source_field_locator"] for f in prefixes),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    selected_locators = [f["source_field_locator"] for _, f in selected]
    names = [
        f
        for pointed, f in selected
        if pointed["reference_object_id"] == obj["reference_object_id"]
        and f["alias_role"] in ("EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS")
    ]
    roots = [
        (pointed, f)
        for pointed, f in selected
        if pointed["object_kind"] == "FORMAT_COUNTRY"
        and pointed["source_locator"] == country
        and f["field_name"] == "zip"
        and f["source_field_locator"] == country + "/zip"
        and f["original_value"]
    ]
    c.require(
        obj["object_kind"] == "FORMAT_ADMIN"
        and bool(prefixes)
        and rule["scope_locator"] == expected_scope
        and len(roots) == 1
        and all(
            selected_locators.count(f["source_field_locator"]) == 1 for f in prefixes
        )
        and any(
            s9.normalize(s9.NAME_NORM, f["original_value"])
            == s9.normalize(s9.NAME_NORM, source["stage03_clean_region_in_country"])
            for f in names
        )
        and not any(
            f["field_name"] in ("xzip", "sub_xzips") and f["original_value"]
            for f in obj["fields"]
        ),
        "STAGE10_POSTCODE_CONTRADICTION_WITNESS_INVALID",
    )


def evaluate_source_fields(
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    access: ReferenceAccess,
) -> FieldPolicy:
    """Only a source/candidate pair's fixed scheduled checks enter this gate."""
    expected = {
        (q.question_id, r): q
        for q in questions.source_questions(source, candidate)
        for r in s9.QUESTIONS[q.question_id].references
    }
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in rows:
        key = (row["question_catalog_id"], row["reference_slot"])
        c.require(
            key in expected
            and key not in indexed
            and row["evidence_scope"] == "SOURCE_ROW"
            and row["stable_source_row_id_v1"] == source["stable_source_row_id_v1"]
            and row["stage06_exact_candidate_id"]
            == candidate["stage06_exact_candidate_id"],
            "STAGE10_SOURCE_EVIDENCE_GRAIN_INVALID",
        )
        q = expected[key]
        arguments = [
            o.argument(q.question_id, key[1], q.country)[0] for o in q.observations
        ]
        c.require(
            row["arguments"] == arguments
            and row["interpretation"] == q.interpretation
            and row["claim_scope"] == s9.QUESTIONS[q.question_id].claim_scope,
            "STAGE10_SOURCE_ARGUMENT_LINEAGE_INVALID",
        )
        c.require(
            row["result_state"] in s9.STATES
            and not (key[1] == s9.GN and row["result_state"] == "CONTRADICTED"),
            "STAGE10_REFERENCE_STATE_INVALID",
        )
        indexed[key] = row
    c.require(set(indexed) == set(expected), "STAGE10_SOURCE_EVIDENCE_INCOMPLETE")
    raw_country = source["stage03_clean_country_iso_code"]
    country: str | None = None
    if isinstance(raw_country, str) and re.fullmatch(r"[A-Za-z]{2}", raw_country):
        code = s9.ascii_upper(raw_country)
        row = indexed[("Q01", s9.ISO)]
        cap = _capability(row, access)
        if (
            row["result_state"] == "SUPPORTED"
            and cap is not None
            and cap["country_scope"] == "GLOBAL"
        ):
            for witness in access.witnesses(row):
                obj = access.object(witness["reference_object_id"])
                if (
                    obj["object_kind"] == "ISO_COUNTRY"
                    and obj["reference_version_id"] == row["reference_version_id"]
                    and obj["country_code"] == code
                    and witness["witness_role"] == "SUPPORT"
                    and _field_matches(
                        witness,
                        access,
                        obj["reference_object_id"],
                        "alpha_2",
                        code,
                        s9.ISO_NORM,
                    )
                ):
                    country = code
    if country is None:
        return FieldPolicy(
            None,
            None,
            None,
            ("COUNTRY_CONTEXT_UNAVAILABLE",),
            ("COUNTRY_CONTEXT_UNAVAILABLE",),
            (),
        )
    locality = source["stage03_clean_city"]
    postcode = source["stage03_clean_postcode"]
    locality_ok = bool(locality) and any(
        _supported(indexed[("Q09", family)], access, source, country, locality=True)
        for family in (s9.LIA, s9.GN)
    )
    postcode_ok = bool(postcode) and _supported(
        indexed[("Q05", s9.GN)], access, source, country, postcode=True
    )
    contradictions = []
    for question, contradiction in (
        ("Q04", "FORMAT_RULE_CONFLICT"),
        ("Q08", "PREFIX_RULE_CONFLICT"),
    ):
        row = indexed[(question, s9.LIA)]
        if row["result_state"] != "CONTRADICTED":
            continue
        matrix = _capability(row, access, negative=True)
        rule = _capability(row, access, negative=True, rule=True)
        if (
            matrix is None
            or rule is None
            or matrix["country_scope"] != country
            or rule["country_scope"] != country
        ):
            continue
        # Exact source argument equality above includes postcode and Q08 admin;
        # the country capability must also agree with this occurrence's boundary.
        if row["contradiction_type"] != contradiction:
            continue
        _postcode_conflict_certificate(row, rule, access, country, source)
        contradictions.append(question)
    if contradictions:
        postcode_ok = False
    if locality_ok and postcode_ok:
        postcode_ok = _supported(
            indexed[("Q06", s9.GN)],
            access,
            source,
            country,
            locality=True,
            postcode=True,
        )
    return FieldPolicy(
        country,
        locality if locality_ok else None,
        postcode if postcode_ok else None,
        ()
        if locality_ok
        else (
            "SOURCE_FIELD_UNAVAILABLE"
            if not locality
            else "INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE",
        ),
        ()
        if postcode_ok
        else (
            "CONTRADICTION_GATE"
            if contradictions
            else "SOURCE_FIELD_UNAVAILABLE"
            if not postcode
            else "INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE",
        ),
        tuple(contradictions),
    )

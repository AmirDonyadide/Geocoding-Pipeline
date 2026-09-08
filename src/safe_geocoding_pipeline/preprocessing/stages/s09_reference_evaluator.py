"""Conservative scoped evaluations. No network, geocoder, correction or fuzzy path."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import duckdb

from . import s09_reference_contract as c
from . import s09_reference_pack as p
from .s09_reference_questions import EvaluationQuestion


def pointer(obj: Mapping[str, Any], entry: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reference_object_id": obj["reference_object_id"],
        "field_name": entry["field_name"],
        "ordinal": entry["ordinal"],
    }


def witness(
    obj: Mapping[str, Any], fields: Sequence[Mapping[str, Any]], role: str = "SUPPORT"
) -> dict[str, Any]:
    unique = {
        (f["reference_object_id"], f["field_name"], f["ordinal"]): dict(f)
        for f in fields
    }
    c.require(0 < len(unique) <= 16, "WITNESS_FIELD_BOUND_INVALID")
    return {
        "reference_object_id": obj["reference_object_id"],
        "witness_role": role,
        "fields": [unique[key] for key in sorted(unique)],
    }


def field_named(obj: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    entries = [f for f in obj["fields"] if f["field_name"] == name]
    c.require(len(entries) == 1, "REFERENCE_REQUIRED_FIELD_MISSING_OR_AMBIGUOUS")
    return dict(entries[0])


@dataclass(frozen=True)
class PreparedEvaluation:
    question: EvaluationQuestion
    reference: str
    capability: Mapping[str, Any] | None
    asset: bytes | None
    arguments: Sequence[Mapping[str, Any]]
    keys: tuple[str | None, ...]
    unavailable_reason: str | None


@dataclass(frozen=True)
class LookupResult:
    state: str
    reason: str
    witnesses: Sequence[Mapping[str, Any]] = ()
    contradiction: str | None = None
    rule_capability: Mapping[str, Any] | None = None


class SmallReferenceView:
    """One bounded ISO/metadata index per process; size fixed by the public lock."""

    def __init__(
        self,
        registry: Sequence[Mapping[str, Any]],
        capabilities: Sequence[Mapping[str, Any]],
        objects: Sequence[Mapping[str, Any]],
        *,
        connection: duckdb.DuckDBPyConnection,
    ) -> None:
        self.registry = {r["reference_id"]: r for r in registry}
        self.by_version = {r["reference_version_id"]: r for r in registry}
        self.objects = {o["reference_object_id"]: o for o in objects}
        c.require(len(self.objects) == len(objects), "REFERENCE_OBJECT_ID_COLLISION")
        # Arrow decoding does not share repeated strings/lists between rows.
        # Intern only this fixed public registry in a local pool; protected
        # lookup values never enter these pools or process-global interning.
        texts: dict[str, str] = {}
        lists: dict[tuple[str, ...], list[str]] = {}

        def compact(row: Mapping[str, Any]) -> dict[str, Any]:
            result = {}
            for key, value in row.items():
                key = texts.setdefault(key, key)
                if isinstance(value, str):
                    value = texts.setdefault(value, value)
                elif isinstance(value, list):
                    elements = tuple(texts.setdefault(v, v) for v in value)
                    value = lists.setdefault(elements, list(elements))
                result[key] = value
            return result

        selected = [compact(r) for r in capabilities if runtime_capability(r)]
        self.capabilities = {r["capability_id"]: r for r in selected}
        c.require(
            len(self.capabilities) == len(selected), "REFERENCE_CAPABILITY_ID_COLLISION"
        )
        self.matrix = {
            (
                self.by_version[r["reference_version_id"]]["reference_id"],
                r["country_scope"],
                r["question_catalog_id"],
            ): r
            for r in selected
            if r["scope_locator"] == "COUNTRY_MATRIX"
        }
        self.rules = {
            (r["country_scope"], r["question_catalog_id"], r["scope_locator"]): r
            for r in selected
            if r["scope_locator"] != "COUNTRY_MATRIX"
        }
        self.country_codes: dict[str, Mapping[str, Any]] = {}
        self.admin_codes: dict[str, Mapping[str, Any]] = {}
        self.roots: dict[str, Mapping[str, Any]] = {}
        self.aliases: dict[
            tuple[str, str, str, str], list[tuple[Mapping[str, Any], Mapping[str, Any]]]
        ] = defaultdict(list)
        self.prefix_rules: dict[bytes, Mapping[str, Any]] = {}
        self.connection = connection
        self.assets: dict[tuple[str, str], bytes] = {}
        for obj in objects:
            family = self.by_version[obj["reference_version_id"]]["reference_id"]
            country = obj["country_code"]
            if obj["object_kind"] == "ISO_COUNTRY":
                self.country_codes[field_named(obj, "alpha_2")["original_value"]] = obj
            elif obj["object_kind"] == "ISO_ADMIN":
                self.admin_codes[field_named(obj, "code")["original_value"]] = obj
            elif (
                obj["object_kind"] == "FORMAT_COUNTRY"
                and obj["source_locator"] == country
            ):
                self.roots[country] = obj
            if (
                obj["object_kind"]
                not in ("ISO_ADMIN", "FORMAT_ADMIN", "FORMAT_LOCALITY")
                or country is None
            ):
                continue
            for entry in obj["fields"]:
                eligible = (
                    entry["field_name"] == "name"
                    if family == c.ISO
                    else entry["alias_role"]
                    in ("EXPLICIT_KEY", "NATIVE_ALIAS", "LATIN_ALIAS")
                )
                if eligible and entry["original_value"]:
                    key = c.normalize(c.NAME_NORM, entry["original_value"])
                    self.aliases[(family, country, obj["object_kind"], key)].append(
                        (obj, entry)
                    )
        expected_matrix = {
            (reference, scope, question.question_id)
            for question in c.CATALOG
            for reference in question.references
            if reference != "NONE"
            for scope in (
                ["GLOBAL"]
                if question.question_id in ("Q01", "Q14")
                else [*self.registry[c.ISO]["countries"], "UNRESOLVED"]
            )
        }
        c.require(
            set(self.matrix) == expected_matrix, "REFERENCE_MATRIX_INVENTORY_INCOMPLETE"
        )
        by_locator = {
            o["source_locator"]: o
            for o in objects
            if o["object_kind"] == "FORMAT_ADMIN"
        }
        for rule in self.rules.values():
            if rule["question_catalog_id"] == "Q08" and rule[
                "scope_locator"
            ].startswith("PREFIX_BUNDLE:"):
                locator = json.loads(
                    rule["scope_locator"].removeprefix("PREFIX_BUNDLE:")
                )[0]
                c.require(locator in by_locator, "PREFIX_OBJECT_UNRESOLVED")
                self.prefix_rules[by_locator[locator]["reference_object_id"]] = rule
        # A present enabled raw rule with a missing index certificate is an
        # incomplete index, not ordinary missing metadata.
        for country, root in self.roots.items():
            names = {f["field_name"] for f in root["fields"] if f["original_value"]}
            for question, name in (("Q03", "fmt"), ("Q04", "zip"), ("Q15", "require")):
                if self.matrix[(c.LIA, country, question)]["enabled"] and name in names:
                    c.require(
                        (country, question, country + "/" + name) in self.rules,
                        "EXPECTED_RULE_CAPABILITY_MISSING",
                    )

    def asset_id(self, reference: str, question: str) -> bytes:
        if (reference, question) in self.assets:
            return self.assets[(reference, question)]
        assets = self.registry[reference]["assets"]
        if reference == c.ISO:
            marker = "iso_3166-1_" if question in ("Q01", "Q14") else "iso_3166-2_"
            selected = [
                a
                for a in assets
                if a["relative_path"].startswith(marker)
                and a["member_path"] is None
                and a["role"] == "DATA_JSON"
            ]
        elif reference == c.LIA:
            selected = [
                a for a in assets if a["member_path"] == "i18naddress/data/all.json"
            ]
        else:
            selected = [a for a in assets if a["member_path"] == "allCountries.txt"]
        c.require(len(selected) == 1, "SCIENTIFIC_ASSET_NOT_UNIQUE")
        result = bytes(selected[0]["asset_id"])
        self.assets[(reference, question)] = result
        return result

    def prepare(
        self, question: EvaluationQuestion, reference: str
    ) -> PreparedEvaluation:
        catalog = c.QUESTIONS[question.question_id]
        c.require(reference in catalog.references, "REFERENCE_SLOT_NOT_SCHEDULED")
        c.require(
            tuple(o.role for o in question.observations) == catalog.roles,
            "QUESTION_ARGUMENT_ROLES_INVALID",
        )
        arguments, keys = zip(
            *(
                o.argument(question.question_id, reference, question.country)
                for o in question.observations
            ),
            strict=True,
        )
        capability = None
        asset = None
        reason = None
        if reference == "NONE":
            reason = "CAPABILITY_NOT_CONFIGURED"
        else:
            scope = (
                "GLOBAL" if question.question_id in ("Q01", "Q14") else question.country
            )
            capability = self.matrix.get((reference, scope, question.question_id))
            c.require(capability is not None, "COUNTRY_MATRIX_ROW_MISSING")
            asset = self.asset_id(reference, question.question_id)
            assert capability is not None
            if question.scope == "PARSER_CANDIDATE" and question.question_id == "Q02":
                reason = "SOURCE_ONLY_QUESTION"
            elif scope == "UNRESOLVED":
                reason = "COUNTRY_CONTEXT_UNRESOLVED"
            elif any(
                o.observed_role_count == 0
                or (o.observed_role_count == 1 and not o.value)
                for o in question.observations
            ):
                reason = "MISSING_COMPONENT"
            elif any(o.observed_role_count > 1 for o in question.observations):
                reason = "AMBIGUOUS_COMPONENT_SET"
            elif (
                scope != "GLOBAL" and scope not in self.registry[reference]["countries"]
            ):
                reason = "COUNTRY_NOT_COVERED"
            elif not capability["enabled"]:
                reason = "COMPONENT_CAPABILITY_MISSING"
                if (
                    reference == c.GN
                    and question.question_id in ("Q05", "Q06", "Q07")
                    and "PARTIAL_POSTCODE_NO_FULL_CODE_AUTHORITY"
                    in capability["limitations"]
                ):
                    reason = "REFERENCE_GRANULARITY_INSUFFICIENT"
                elif (
                    reference == c.LIA
                    and question.question_id == "Q04"
                    and scope in ("BH", "CN")
                ):
                    reason = (
                        "PATTERN_DIALECT_UNSUPPORTED"
                        if scope == "BH"
                        else "ALTERNATE_RULE_SEMANTICS_UNSUPPORTED"
                    )
            elif (
                reference == c.GN
                and question.question_id in ("Q05", "Q06", "Q07")
                and scope == "US"
                and not re.fullmatch(r"[0-9]{5}", keys[1] or "")
            ):
                reason = "REFERENCE_GRANULARITY_INSUFFICIENT"
        return PreparedEvaluation(
            question, reference, capability, asset, arguments, tuple(keys), reason
        )

    def _rule(
        self, country: str, question: str, field: str
    ) -> Mapping[str, Any] | None:
        return self.rules.get((country, question, country + "/" + field))

    def _regex(self, value: str, pattern: str, *, prefix: bool = False) -> bool:
        c.require(p.safe_pattern(pattern), "ENABLED_REGEX_OUTSIDE_FROZEN_GRAMMAR")
        sql = (
            "SELECT regexp_matches(?, ?)"
            if prefix
            else "SELECT regexp_full_match(?, ?)"
        )
        expression = "^(?:" + pattern + ")" if prefix else pattern
        row = self.connection.execute(sql, [value, expression]).fetchone()
        c.require(row is not None, "REGEX_ENGINE_RESULT_MISSING")
        assert row is not None
        return bool(row[0])

    def _ancestry(self, obj: Mapping[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        current = obj
        depth = 0
        while True:
            keys = [f for f in current["fields"] if f["alias_role"] == "EXPLICIT_KEY"]
            c.require(bool(keys), "METADATA_PATH_WITNESS_MISSING")
            # All supplied key aliases are positive fields; raw tilde lists
            # are EXPLICIT_FIELD and never aliases.
            result.extend(pointer(current, f) for f in keys)
            if current["explicit_parent_id"] is None:
                break
            c.require(
                depth < 3 and current["explicit_parent_id"] in self.objects,
                "METADATA_PARENT_PATH_INVALID",
            )
            current = self.objects[current["explicit_parent_id"]]
            depth += 1
        return result

    def _name_witnesses(
        self, family: str, country: str, kind: str, key: str
    ) -> list[Mapping[str, Any]]:
        grouped: dict[bytes, tuple[Mapping[str, Any], list[dict[str, Any]]]] = {}
        for obj, entry in self.aliases.get((family, country, kind, key), ()):
            if obj["reference_object_id"] not in grouped:
                fields = (
                    self._ancestry(obj)
                    if family == c.LIA
                    else [pointer(obj, field_named(obj, "code"))]
                )
                grouped[obj["reference_object_id"]] = (obj, fields)
            grouped[obj["reference_object_id"]][1].append(pointer(obj, entry))
        return [witness(obj, fields) for obj, fields in grouped.values()]

    def lookup_small(self, prepared: PreparedEvaluation) -> LookupResult:
        if prepared.unavailable_reason:
            return LookupResult("NOT_EVALUABLE", prepared.unavailable_reason)
        q, country, keys = (
            prepared.question.question_id,
            prepared.question.country,
            prepared.keys,
        )
        if prepared.reference == c.ISO:
            obj = None
            if q in ("Q01", "Q14"):
                obj = self.country_codes.get(keys[0] or "")
                if obj is not None:
                    return LookupResult(
                        "SUPPORTED",
                        "EXACT_REFERENCE_SUPPORT",
                        (witness(obj, [pointer(obj, field_named(obj, "alpha_2"))]),),
                    )
            elif q == "Q02":
                obj = self.admin_codes.get(keys[1] or "")
                if obj is None:
                    return LookupResult("NOT_EVALUABLE", "EXPLICIT_CODE_NOT_IDENTIFIED")
                same = obj["country_code"] == country
                state, role = (
                    ("SUPPORTED", "SUPPORT")
                    if same
                    else ("CONTRADICTED", "CONTRADICTION")
                )
                return LookupResult(
                    state,
                    "EXPLICIT_CODE_COUNTRY_SUPPORT"
                    if same
                    else "EXPLICIT_CODE_COUNTRY_CONFLICT",
                    (witness(obj, [pointer(obj, field_named(obj, "code"))], role),),
                    None if same else "EXPLICIT_CODE_COUNTRY_CONFLICT",
                )
            elif q == "Q10":
                if prepared.arguments[1]["normalization_id"] == c.ISO_NORM:
                    obj = self.admin_codes.get(keys[1] or "")
                    if obj is not None and obj["country_code"] == country:
                        return LookupResult(
                            "SUPPORTED",
                            "EXACT_REFERENCE_SUPPORT",
                            (witness(obj, [pointer(obj, field_named(obj, "code"))]),),
                        )
                else:
                    matches = self._name_witnesses(
                        c.ISO, country, "ISO_ADMIN", keys[1] or ""
                    )
                    if matches:
                        return LookupResult(
                            "SUPPORTED", "EXACT_REFERENCE_SUPPORT", matches
                        )
            return LookupResult("NOT_FOUND", "VALUE_ABSENT_FROM_REFERENCE")
        c.require(prepared.reference == c.LIA, "POSTAL_LOOKUP_REQUIRES_BATCH_INDEX")
        root = self.roots.get(country)
        if q in ("Q03", "Q04", "Q15"):
            name = {"Q03": "fmt", "Q04": "zip", "Q15": "require"}[q]
            rule = self._rule(country, q, name)
            if root is None or rule is None:
                return LookupResult(
                    "NOT_EVALUABLE",
                    "NO_COUNTRY_PATTERN"
                    if q == "Q04"
                    else "COMPONENT_CAPABILITY_MISSING",
                )
            entry = field_named(root, name)
            supported = q != "Q04" or self._regex(
                keys[1] or "", entry["original_value"]
            )
            return LookupResult(
                "SUPPORTED" if supported else "CONTRADICTED",
                "EXPLICIT_RULE_SUPPORT" if supported else "EXPLICIT_RULE_CONFLICT",
                (
                    witness(
                        root,
                        [pointer(root, entry)],
                        "SUPPORT" if supported else "CONTRADICTION",
                    ),
                ),
                None if supported else "FORMAT_RULE_CONFLICT",
                rule,
            )
        if q == "Q08":
            admins = self._name_witnesses(c.LIA, country, "FORMAT_ADMIN", keys[2] or "")
            if len(admins) != 1:
                return LookupResult("NOT_EVALUABLE", "ADMIN_IDENTITY_UNRESOLVED")
            admin = self.objects[admins[0]["reference_object_id"]]
            rule = self.prefix_rules.get(admin["reference_object_id"])
            if rule is None:
                return LookupResult("NOT_EVALUABLE", "NO_PREFIX_RULE")
            if root is None or self._rule(country, "Q04", "zip") is None:
                return LookupResult("NOT_EVALUABLE", "NO_COUNTRY_PATTERN")
            country_zip = field_named(root, "zip")
            if not self._regex(keys[1] or "", country_zip["original_value"]):
                return LookupResult(
                    "NOT_EVALUABLE", "COUNTRY_FORMAT_PREREQUISITE_FAILED"
                )
            prefixes = [
                f
                for f in admin["fields"]
                if f["field_name"] in ("zip", "sub_zips") and f["original_value"]
            ]
            results = {
                self._regex(keys[1] or "", entry["original_value"], prefix=True)
                for entry in prefixes
            }
            conflict = len(results) != 1
            supported = results == {True}
            role = (
                "CONFLICTING_REFERENCE"
                if conflict
                else "SUPPORT"
                if supported
                else "CONTRADICTION"
            )
            fields = (
                list(admins[0]["fields"])
                + [pointer(root, country_zip)]
                + [pointer(admin, f) for f in prefixes]
            )
            return LookupResult(
                "NOT_EVALUABLE"
                if conflict
                else "SUPPORTED"
                if supported
                else "CONTRADICTED",
                "REFERENCE_INTERNAL_CONFLICT"
                if conflict
                else "EXPLICIT_RULE_SUPPORT"
                if supported
                else "EXPLICIT_RULE_CONFLICT",
                (witness(admin, fields, role),),
                None if conflict or supported else "PREFIX_RULE_CONFLICT",
                rule,
            )
        if q in ("Q09", "Q10"):
            kind = "FORMAT_LOCALITY" if q == "Q09" else "FORMAT_ADMIN"
            matches = self._name_witnesses(c.LIA, country, kind, keys[1] or "")
            return (
                LookupResult("SUPPORTED", "EXACT_REFERENCE_SUPPORT", matches)
                if matches
                else LookupResult("NOT_FOUND", "VALUE_ABSENT_FROM_REFERENCE")
            )
        c.require(q == "Q11", "QUESTION_DISPATCH_INVALID")
        localities = self._name_witnesses(
            c.LIA, country, "FORMAT_LOCALITY", keys[1] or ""
        )
        admin_paths = {
            w["reference_object_id"]: w
            for w in self._name_witnesses(c.LIA, country, "FORMAT_ADMIN", keys[2] or "")
        }
        matches = []
        for local in localities:
            obj = self.objects[local["reference_object_id"]]
            parent = obj["explicit_parent_id"]
            if parent in admin_paths:
                matches.append(
                    witness(obj, [*local["fields"], *admin_paths[parent]["fields"]])
                )
        return (
            LookupResult("SUPPORTED", "EXACT_REFERENCE_SUPPORT", matches)
            if matches
            else LookupResult("NOT_FOUND", "RELATION_ABSENT_FROM_REFERENCE")
        )


def lookup_identity(
    prepared: PreparedEvaluation, rule: Mapping[str, Any] | None
) -> bytes:
    c.require(
        prepared.capability is not None and prepared.asset is not None,
        "LOOKUP_BINDING_MISSING",
    )
    assert prepared.capability is not None
    return c.identity(
        "LOOKUP",
        (
            prepared.capability["reference_version_id"],
            prepared.asset,
            prepared.capability["capability_id"],
            None if rule is None else rule["capability_id"],
            prepared.question.question_id,
            c.QUESTIONS[prepared.question.question_id].claim_scope,
            tuple(
                (a["role"], a["normalization_id"], a["value_granularity"], key)
                for a, key in zip(prepared.arguments, prepared.keys, strict=True)
            ),
        ),
    )


def runtime_capability(row: Mapping[str, Any]) -> bool:
    """Positive enumeration rows remain in the pack, not in a second RAM copy.

    Generic enumeration checks use the matrix plus witnessed object fields,
    exactly as the frozen contract specifies. Only performed-rule certificates
    need random access by ID in the evaluator.
    """
    return row["scope_locator"] == "COUNTRY_MATRIX" or row["question_catalog_id"] in (
        "Q03",
        "Q04",
        "Q08",
        "Q15",
    )


def evidence_row(
    prepared: PreparedEvaluation,
    result: LookupResult,
    *,
    profile: bytes,
    stage08_logical: bytes,
    lookup: bytes | None,
    witness_count: int,
    single_witness: Mapping[str, Any] | None,
    match_set_id: bytes | None,
) -> dict[str, Any]:
    capability = prepared.capability
    rule_id = (
        None
        if result.rule_capability is None
        else result.rule_capability["capability_id"]
    )
    version = None if capability is None else capability["reference_version_id"]
    cap_id = None if capability is None else capability["capability_id"]
    question = prepared.question
    assessment = (
        "COUNTRY_" + result.state
        if question.scope == "SOURCE_ROW"
        and question.question_id == "Q02"
        and result.state in ("SUPPORTED", "CONTRADICTED")
        else "COUNTRY_UNRESOLVED"
    )
    row = {
        "evidence_id": c.identity(
            "EVIDENCE",
            (
                profile,
                question.question_identity(stage08_logical),
                prepared.reference,
                version,
                cap_id,
                rule_id,
            ),
        ),
        "stage06_exact_candidate_id": question.candidate_id,
        "evidence_scope": question.scope,
        "stable_source_row_id_v1": question.source_id,
        "question_catalog_id": question.question_id,
        "reference_slot": prepared.reference,
        "reference_version_id": version,
        "reference_asset_id": prepared.asset,
        "capability_id": cap_id,
        "rule_capability_id": rule_id,
        "evidence_family": None if prepared.reference == "NONE" else prepared.reference,
        "interpretation": question.interpretation,
        "claim_scope": c.QUESTIONS[question.question_id].claim_scope,
        "arguments": list(prepared.arguments),
        "result_state": result.state,
        "reason_code": result.reason,
        "contradiction_type": result.contradiction,
        "country_assessment": assessment,
        "country_assessment_basis": "NO_UNIFORM_WITNESS"
        if assessment == "COUNTRY_UNRESOLVED"
        else "EXPLICIT_SOURCE_SUBDIVISION_CODE",
        "lookup_identity": lookup,
        "witness_count": witness_count,
        "single_witness": single_witness,
        "match_set_id": match_set_id,
        "evidence_class": "REFERENCE_EVIDENCE",
    }
    c.validate_evidence_semantics(row, capability)
    return row


def finalize_small(
    prepared: PreparedEvaluation,
    result: LookupResult,
    *,
    profile: bytes,
    stage08_logical: bytes,
) -> tuple[dict[str, Any], Iterable[dict[str, Any]]]:
    # Only the lock-bounded ISO/metadata path uses this collection. Unbounded
    # GeoNames match sets use the external sorted streaming path instead.
    unique = {c.framed(c.witness_tuple(w)): w for w in result.witnesses}
    witnesses = [unique[key] for key in sorted(unique)]
    performed = prepared.unavailable_reason is None and (
        result.state in ("SUPPORTED", "CONTRADICTED", "NOT_FOUND")
        or result.reason == "REFERENCE_INTERNAL_CONFLICT"
    )
    lookup = lookup_identity(prepared, result.rule_capability) if performed else None
    match_id = (
        c.identity("MATCH_SET", (lookup, tuple(c.witness_tuple(w) for w in witnesses)))
        if len(witnesses) > 1
        else None
    )
    row = evidence_row(
        prepared,
        result,
        profile=profile,
        stage08_logical=stage08_logical,
        lookup=lookup,
        witness_count=len(witnesses),
        single_witness=witnesses[0] if len(witnesses) == 1 else None,
        match_set_id=match_id,
    )
    return row, (
        {"match_set_id": match_id, "member_ordinal": i, "witness": w}
        for i, w in enumerate(witnesses)
        if match_id is not None
    )

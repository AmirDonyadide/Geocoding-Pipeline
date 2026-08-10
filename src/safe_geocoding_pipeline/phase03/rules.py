from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..phase02.fingerprints import canonical_json_bytes
from .constants import (
    ADDRESS_FIELDS,
    COMPONENTS,
    CONFIDENCES,
    ELIGIBLE_FIELDS,
    RULE_EXECUTION_DISPOSITIONS,
)
from .errors import Phase03Error

RULE_KEYS = frozenset(
    {
        "rule_id",
        "rule_version",
        "execution_disposition",
        "component",
        "representation",
        "eligible_source_fields",
        "preconditions",
        "match_input",
        "comparison_normalization",
        "matching_condition",
        "extraction_condition",
        "candidate_behavior",
        "confidence",
        "selection_priority",
        "conflict_behavior",
        "maximum_input_utf8_bytes",
        "reference_ids",
        "required_tests",
    }
)
MATCHERS = frozenset(
    {
        "WHOLE_FIELD_CONTENT",
        "COUNTRY_REFERENCE_EXACT",
        "MARKER_WITH_IDENTIFIER",
        "SEGMENT_LEADING_MARKER_WITH_NAME",
        "SEGMENT_ENDING_LEGAL_FORM",
        "PHRASE_PRESENT",
        "BOUNDED_EDGE_HOUSE_NUMBER",
    }
)
EXTRACTORS = frozenset(
    {
        "WHOLE_FIELD_SPAN",
        "COUNTRY_ALPHA2_VALUE",
        "MARKER_AND_IDENTIFIER_SPAN",
        "IDENTIFIER_ONLY_SPAN",
        "WHOLE_TRIMMED_SEGMENT_SPAN",
        "MATCHED_PHRASE_SPAN",
        "MATCHED_EDGE_TOKEN_SPAN",
    }
)
PRECONDITION_OPERATORS = frozenset(
    {
        "ALL",
        "ANY",
        "NOT",
        "EQ",
        "IN",
        "SEMANTIC_STATE_IS",
        "EVALUATION_STATUS_IS",
        "CANDIDATE_COUNT",
    }
)
MATCH_INPUTS = frozenset({"RAW_WHOLE_FIELD", "RAW_CODEPOINT_TOKENS"})
COMPARISON_NORMALIZATIONS = frozenset({"NFC_TOKEN", "ASCII_LOWER"})
CONFLICT_BEHAVIORS = frozenset(
    {
        "NONE",
        "POSTCODE_DIFFERENT_VALUES_CONFLICT",
        "LOCALITY_DIFFERENT_VALUES_CONFLICT",
        "REGION_DIFFERENT_VALUES_CONFLICT",
        "COUNTRY_DIFFERENT_VALUES_CONFLICT",
        "UNIT_HOUSE_NUMBER_ROLE_CONFLICT",
        "BUILDING_ORGANIZATION_ROLE_CONFLICT",
        "HOUSE_NUMBER_ROLE_AMBIGUITY",
    }
)
BEHAVIOR_VALUES = frozenset({"NORMALIZED_EXTRACTED_TEXT", "REFERENCE_ALPHA2", "NONE"})


@dataclass(frozen=True, slots=True)
class RuleSpec:
    rule_id: str
    rule_version: int | str
    execution_disposition: str
    component: str
    representation: str
    eligible_source_fields: tuple[str, ...]
    preconditions: dict[str, Any]
    match_input: str
    comparison_normalization: tuple[str, ...]
    matching_condition: dict[str, Any]
    extraction_condition: dict[str, Any]
    candidate_behavior: dict[str, Any]
    confidence: str
    selection_priority: int
    conflict_behavior: str
    maximum_input_utf8_bytes: int
    reference_ids: tuple[str, ...]
    required_tests: tuple[str, ...]

    @property
    def matcher(self) -> str:
        return str(self.matching_condition["matcher"])

    @property
    def extractor(self) -> str:
        return str(self.extraction_condition["extractor"])

    @property
    def selectable(self) -> bool:
        return self.execution_disposition == "AUTHORITATIVE_SELECTABLE"

    @property
    def development_shadow_only(self) -> bool:
        return self.execution_disposition == "DEVELOPMENT_SHADOW_ONLY"


@dataclass(frozen=True, slots=True)
class RuleRegistry:
    schema_version: str
    registry_version: str
    rules: tuple[RuleSpec, ...]
    canonical_bytes: bytes

    @property
    def fingerprint(self) -> str:
        import hashlib

        return hashlib.sha256(self.canonical_bytes).hexdigest()

    def ordered_rules(self) -> tuple[RuleSpec, ...]:
        return tuple(
            sorted(
                self.rules,
                key=lambda rule: (rule.selection_priority, rule.rule_id.encode()),
            )
        )


def _validate_precondition(value: object) -> None:
    if not isinstance(value, dict) or len(value) != 1:
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "precondition must be a one-operator object"
        )
    operator, argument = next(iter(value.items()))
    if operator not in PRECONDITION_OPERATORS:
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "unregistered precondition operator"
        )
    if operator in {"ALL", "ANY"}:
        if not isinstance(argument, list) or not argument:
            raise Phase03Error(
                "RULE_REGISTRY_INVALID", "compound precondition requires children"
            )
        for child in argument:
            _validate_precondition(child)
    elif operator == "NOT":
        _validate_precondition(argument)
    elif operator == "SEMANTIC_STATE_IS":
        if argument not in {
            "SEMANTIC_MISSING",
            "AMBIGUOUS_PLACEHOLDER_LIKE",
            "CONTENT",
        }:
            raise Phase03Error("RULE_REGISTRY_INVALID", "invalid semantic state")
    elif operator == "EVALUATION_STATUS_IS":
        if argument not in {
            "FULLY_EVALUATED",
            "PARTIALLY_SKIPPED_OVERSIZED",
            "NOT_EVALUATED_OVERSIZED",
        }:
            raise Phase03Error("RULE_REGISTRY_INVALID", "invalid evaluation status")
    elif operator == "CANDIDATE_COUNT":
        if type(argument) is not int or argument < 0:
            raise Phase03Error("RULE_REGISTRY_INVALID", "invalid candidate count")
    elif operator in {"EQ", "IN"}:
        if not isinstance(argument, dict) or len(argument) != 1:
            raise Phase03Error("RULE_REGISTRY_INVALID", "invalid comparison predicate")
        key, expected = next(iter(argument.items()))
        if key not in {"semantic_state", "evaluation_status", "candidate_count"}:
            raise Phase03Error("RULE_REGISTRY_INVALID", "unknown predicate field")
        if operator == "IN" and (not isinstance(expected, list) or not expected):
            raise Phase03Error("RULE_REGISTRY_INVALID", "IN requires values")


def _validate_token_phrases(value: object, *, name: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(
            not isinstance(phrase, list)
            or not phrase
            or any(not isinstance(token, str) or not token for token in phrase)
            for phrase in value
        )
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", f"invalid {name}")


def _validate_matcher_parameters(matcher: str, parameters: object) -> None:
    if not isinstance(parameters, dict):
        raise Phase03Error("RULE_REGISTRY_INVALID", "matcher parameters must be object")
    expected_keys: dict[str, set[str]] = {
        "WHOLE_FIELD_CONTENT": set(),
        "COUNTRY_REFERENCE_EXACT": {"authority"},
        "MARKER_WITH_IDENTIFIER": {"markers", "identifier_max_codepoints"},
        "SEGMENT_LEADING_MARKER_WITH_NAME": {
            "markers",
            "name_max_tokens",
            "name_max_codepoints",
        },
        "SEGMENT_ENDING_LEGAL_FORM": {"forms"},
        "PHRASE_PRESENT": {"phrases"},
        "BOUNDED_EDGE_HOUSE_NUMBER": {
            "allow_alphanumeric",
            "allow_range",
            "allow_slash_or_hyphen",
        },
    }
    if set(parameters) != expected_keys[matcher]:
        raise Phase03Error("RULE_REGISTRY_INVALID", "matcher parameter schema mismatch")
    if matcher == "COUNTRY_REFERENCE_EXACT":
        if parameters["authority"] != "CONTROLLED_REFERENCE":
            raise Phase03Error("RULE_REGISTRY_INVALID", "country authority invalid")
    elif matcher == "MARKER_WITH_IDENTIFIER":
        _validate_token_phrases(parameters["markers"], name="markers")
        if type(parameters["identifier_max_codepoints"]) is not int or not (
            1 <= parameters["identifier_max_codepoints"] <= 32
        ):
            raise Phase03Error("RULE_REGISTRY_INVALID", "identifier bound invalid")
    elif matcher == "SEGMENT_LEADING_MARKER_WITH_NAME":
        _validate_token_phrases(parameters["markers"], name="markers")
        if type(parameters["name_max_tokens"]) is not int or not (
            1 <= parameters["name_max_tokens"] <= 4
        ):
            raise Phase03Error("RULE_REGISTRY_INVALID", "name token bound invalid")
        if type(parameters["name_max_codepoints"]) is not int or not (
            1 <= parameters["name_max_codepoints"] <= 64
        ):
            raise Phase03Error("RULE_REGISTRY_INVALID", "name length bound invalid")
    elif matcher == "SEGMENT_ENDING_LEGAL_FORM":
        _validate_token_phrases(parameters["forms"], name="forms")
    elif matcher == "PHRASE_PRESENT":
        _validate_token_phrases(parameters["phrases"], name="phrases")
    elif matcher == "BOUNDED_EDGE_HOUSE_NUMBER" and any(
        type(parameters[key]) is not bool for key in expected_keys[matcher]
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "house matcher flags invalid")


def _validate_extractor_parameters(extractor: str, parameters: object) -> None:
    if parameters != {"span_behavior": "RAW_CODEPOINTS"}:
        raise Phase03Error("RULE_REGISTRY_INVALID", "extractor parameters invalid")


def _as_rule(value: object) -> RuleSpec:
    if not isinstance(value, dict) or set(value) != RULE_KEYS:
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "rule fields differ from the approved contract"
        )
    rule_id = value["rule_id"]
    if (
        not isinstance(rule_id, str)
        or re.fullmatch(r"[A-Z][A-Z0-9_]*", rule_id) is None
    ):
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "rule_id must be stable uppercase symbolic text"
        )
    _validate_precondition(value["preconditions"])
    matcher = value["matching_condition"]
    extractor = value["extraction_condition"]
    behavior = value["candidate_behavior"]
    disposition = value["execution_disposition"]
    if (
        not isinstance(matcher, dict)
        or set(matcher) != {"matcher", "parameters"}
        or matcher["matcher"] not in MATCHERS
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "unregistered matcher")
    if (
        not isinstance(extractor, dict)
        or set(extractor) != {"extractor", "parameters"}
        or extractor["extractor"] not in EXTRACTORS
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "unregistered extractor")
    _validate_matcher_parameters(str(matcher["matcher"]), matcher["parameters"])
    _validate_extractor_parameters(str(extractor["extractor"]), extractor["parameters"])
    if (
        not isinstance(behavior, dict)
        or set(behavior) != {"mode", "value"}
        or behavior.get("mode")
        not in {
            "SELECTABLE",
            "SELECTABLE_WITH_PLACEHOLDER_COLLISION_GUARD",
            "CANDIDATE_ONLY",
            "DIAGNOSTIC_ONLY",
        }
        or behavior.get("value") not in BEHAVIOR_VALUES
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid candidate behavior")
    if disposition not in RULE_EXECUTION_DISPOSITIONS:
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid execution disposition")
    allowed_dispositions = {
        "SELECTABLE": {"AUTHORITATIVE_SELECTABLE"},
        "SELECTABLE_WITH_PLACEHOLDER_COLLISION_GUARD": {
            "AUTHORITATIVE_SELECTABLE"
        },
        "CANDIDATE_ONLY": {
            "AUTHORITATIVE_CANDIDATE_ONLY",
            "DEVELOPMENT_SHADOW_ONLY",
        },
        "DIAGNOSTIC_ONLY": {"AUTHORITATIVE_DIAGNOSTIC_ONLY"},
    }
    if disposition not in allowed_dispositions[str(behavior["mode"])]:
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "candidate behavior and disposition disagree"
        )
    fields = value["eligible_source_fields"]
    if (
        not isinstance(fields, list)
        or not fields
        or len(set(fields)) != len(fields)
        or any(field not in ELIGIBLE_FIELDS for field in fields)
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid eligible source field")
    component = value["component"]
    if component not in {*COMPONENTS, "DIAGNOSTIC_ONLY"}:
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid component")
    representation = value["representation"]
    if representation not in {"NON_NATIVE", "NATIVE", "SHARED", "ANY"}:
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid representation")
    confidence = value["confidence"]
    if confidence not in CONFIDENCES[:-1]:
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid fixed confidence")
    priority = value["selection_priority"]
    maximum = value["maximum_input_utf8_bytes"]
    if (
        not isinstance(priority, int)
        or priority < 0
        or not isinstance(maximum, int)
        or maximum < 1
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid priority or input limit")
    tests = value["required_tests"]
    references = value["reference_ids"]
    normalization = value["comparison_normalization"]
    match_input = value["match_input"]
    if (
        not isinstance(tests, list)
        or not tests
        or not all(isinstance(item, str) and item for item in tests)
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "mandatory test IDs are required")
    if not isinstance(references, list) or not all(
        isinstance(item, str) and item for item in references
    ):
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "reference IDs must be an ordered string list"
        )
    if (
        not isinstance(normalization, list)
        or len(set(normalization)) != len(normalization)
        or any(item not in COMPARISON_NORMALIZATIONS for item in normalization)
    ):
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "comparison normalization must be explicit"
        )
    if match_input not in MATCH_INPUTS:
        raise Phase03Error("RULE_REGISTRY_INVALID", "match input is unsupported")
    if matcher["matcher"] in {"WHOLE_FIELD_CONTENT", "COUNTRY_REFERENCE_EXACT"}:
        if match_input != "RAW_WHOLE_FIELD" or normalization:
            raise Phase03Error("RULE_REGISTRY_INVALID", "whole-field matcher contract")
    elif match_input != "RAW_CODEPOINT_TOKENS" or "NFC_TOKEN" not in normalization:
        raise Phase03Error("RULE_REGISTRY_INVALID", "token matcher contract")
    if value["conflict_behavior"] not in CONFLICT_BEHAVIORS:
        raise Phase03Error("RULE_REGISTRY_INVALID", "conflict behavior unsupported")
    rule_version = value["rule_version"]
    if not (
        (type(rule_version) is int and rule_version > 0)
        or (isinstance(rule_version, str) and bool(rule_version))
    ):
        raise Phase03Error("RULE_REGISTRY_INVALID", "invalid rule version")
    if component == "DIAGNOSTIC_ONLY" and behavior["mode"] != "DIAGNOSTIC_ONLY":
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "diagnostic rule cannot emit a component"
        )
    if (
        component != "DIAGNOSTIC_ONLY"
        and not set(fields).issubset(set(ADDRESS_FIELDS))
        and representation == "ANY"
    ):
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "ANY representation is limited to address lines"
        )
    return RuleSpec(
        rule_id=rule_id,
        rule_version=value["rule_version"],
        execution_disposition=str(disposition),
        component=component,
        representation=representation,
        eligible_source_fields=tuple(fields),
        preconditions=value["preconditions"],
        match_input=str(value["match_input"]),
        comparison_normalization=tuple(normalization),
        matching_condition=matcher,
        extraction_condition=extractor,
        candidate_behavior=behavior,
        confidence=confidence,
        selection_priority=priority,
        conflict_behavior=str(value["conflict_behavior"]),
        maximum_input_utf8_bytes=maximum,
        reference_ids=tuple(references),
        required_tests=tuple(tests),
    )


def load_rule_registry(path: Path | None = None) -> RuleRegistry:
    try:
        data = (
            path.read_bytes()
            if path is not None
            else files(__package__)
            .joinpath("resources/rule_registry_v2.json")
            .read_bytes()
        )
        value = json.loads(data.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error(
            "RULE_REGISTRY_READ_FAILURE", type(error).__name__
        ) from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "registry_version",
        "rules",
    }:
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "registry root differs from approved schema"
        )
    if value["schema_version"] != "phase03_rule_registry_schema_v2":
        raise Phase03Error("RULE_REGISTRY_INVALID", "unsupported registry schema")
    if value["registry_version"] != "phase03_rule_registry_v2":
        raise Phase03Error("RULE_REGISTRY_INVALID", "unexpected registry version")
    if not isinstance(value["rules"], list):
        raise Phase03Error("RULE_REGISTRY_INVALID", "rules must be a list")
    rules = tuple(_as_rule(item) for item in value["rules"])
    identities = [rule.rule_id for rule in rules]
    priorities = [(rule.selection_priority, rule.rule_id) for rule in rules]
    if len(set(identities)) != len(identities):
        raise Phase03Error("RULE_REGISTRY_INVALID", "duplicate rule identity")
    if priorities != sorted(priorities, key=lambda item: (item[0], item[1].encode())):
        raise Phase03Error(
            "RULE_REGISTRY_INVALID", "registry rules are not in execution order"
        )
    return RuleRegistry(
        schema_version=str(value["schema_version"]),
        registry_version=str(value["registry_version"]),
        rules=rules,
        canonical_bytes=canonical_json_bytes(value),
    )

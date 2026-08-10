from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..phase02.fingerprints import fingerprint
from .config import Phase03Config
from .constants import (
    ADDRESS_FIELDS,
    COMPONENTS,
    CONFLICT_FLAGS,
    DIAGNOSTIC_FLAGS,
    EVIDENCE_KINDS,
    POSTCODE_FLAGS,
    REPRESENTATIONS,
)
from .errors import Phase03Error
from .models import Candidate, RawSpan, SelectedComponent, TransformResult
from .references import CountryReference, ScriptReference
from .rules import RuleRegistry, RuleSpec
from .text import (
    Token,
    classify_placeholder,
    enforce_runtime_contract,
    normalize_derived_text,
    representation_for_field,
    tokenize_with_spans,
)

_COMPONENT_TO_SCALAR = {
    ("STREET", "NON_NATIVE"): "street_clean",
    ("HOUSE_NUMBER", "NON_NATIVE"): "house_number_clean",
    ("UNIT", "NON_NATIVE"): "unit_clean",
    ("FLOOR", "NON_NATIVE"): "floor_clean",
    ("BUILDING", "NON_NATIVE"): "building_clean",
    ("ORGANIZATION", "NON_NATIVE"): "organization_clean",
    ("POSTCODE", "SHARED"): "postcode_clean",
    ("LOCALITY", "SHARED"): "locality_clean",
    ("REGION", "SHARED"): "region_clean",
    ("COUNTRY", "SHARED"): "country_clean",
    ("STREET", "NATIVE"): "street_native_clean",
    ("HOUSE_NUMBER", "NATIVE"): "house_number_native_clean",
    ("UNIT", "NATIVE"): "unit_native_clean",
    ("FLOOR", "NATIVE"): "floor_native_clean",
    ("BUILDING", "NATIVE"): "building_native_clean",
    ("ORGANIZATION", "NATIVE"): "organization_native_clean",
    ("LOCALITY", "NATIVE"): "locality_native_clean",
    ("REGION", "NATIVE"): "region_native_clean",
    ("COUNTRY", "NATIVE"): "country_native_clean",
}
_CONFLICT_BY_COMPONENT = {
    "COUNTRY": "COUNTRY_MULTIPLE_CANDIDATES",
    "POSTCODE": "POSTCODE_MULTIPLE_CANDIDATES",
    "LOCALITY": "LOCALITY_MULTIPLE_CANDIDATES",
    "REGION": "REGION_MULTIPLE_CANDIDATES",
    "STREET": "STREET_MULTIPLE_CANDIDATES",
    "HOUSE_NUMBER": "HOUSE_NUMBER_MULTIPLE_CANDIDATES",
}
_COMPONENTS_BY_CONFLICT = {
    "COUNTRY_MULTIPLE_CANDIDATES": {"COUNTRY"},
    "COUNTRY_SOURCE_CONFLICT": {"COUNTRY"},
    "POSTCODE_MULTIPLE_CANDIDATES": {"POSTCODE"},
    "POSTCODE_SOURCE_CONFLICT": {"POSTCODE"},
    "LOCALITY_MULTIPLE_CANDIDATES": {"LOCALITY"},
    "LOCALITY_SOURCE_CONFLICT": {"LOCALITY"},
    "REGION_MULTIPLE_CANDIDATES": {"REGION"},
    "REGION_SOURCE_CONFLICT": {"REGION"},
    "STREET_MULTIPLE_CANDIDATES": {"STREET"},
    "HOUSE_NUMBER_MULTIPLE_CANDIDATES": {"HOUSE_NUMBER"},
    "HOUSE_NUMBER_POSTCODE_ROLE_CONFLICT": {"HOUSE_NUMBER", "POSTCODE"},
    "UNIT_HOUSE_NUMBER_ROLE_CONFLICT": {"UNIT", "HOUSE_NUMBER"},
    "BUILDING_ORGANIZATION_ROLE_CONFLICT": {"BUILDING", "ORGANIZATION"},
    "COMPONENT_SPAN_OVERLAP_CONFLICT": set(COMPONENTS),
    "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT": {"HOUSE_NUMBER"},
    "NATIVE_NON_NATIVE_POSTCODE_CONFLICT": {"POSTCODE"},
    "NATIVE_NON_NATIVE_COUNTRY_CONFLICT": {"COUNTRY"},
}
_COUNTRY_SOURCE_METHOD = {
    "ALPHA2": "STRUCTURED_ALPHA2_EXACT",
    "ALPHA3": "STRUCTURED_ALPHA3_EXACT",
    "NAME": "STRUCTURED_COUNTRY_NAME_EXACT",
}
_COUNTRY_FREE_METHOD = {
    "ALPHA2": "FREEFORM_ALPHA2_EXACT",
    "ALPHA3": "FREEFORM_ALPHA3_EXACT",
    "NAME": "FREEFORM_COUNTRY_NAME_EXACT",
}


@dataclass(frozen=True, slots=True)
class _Match:
    value_span: tuple[int, int]
    evidence_spans: tuple[tuple[int, int], ...]
    reference_value: str | None = None
    reference_kind: str | None = None


def _precondition_matches(
    expression: dict[str, Any], context: Mapping[str, Any]
) -> bool:
    operator, argument = next(iter(expression.items()))
    if operator == "ALL":
        return all(_precondition_matches(item, context) for item in argument)
    if operator == "ANY":
        return any(_precondition_matches(item, context) for item in argument)
    if operator == "NOT":
        return not _precondition_matches(argument, context)
    if operator == "SEMANTIC_STATE_IS":
        return bool(context.get("semantic_state") == argument)
    if operator == "EVALUATION_STATUS_IS":
        return bool(context.get("evaluation_status") == argument)
    if operator == "CANDIDATE_COUNT":
        return bool(context.get("candidate_count") == argument)
    if operator in {"EQ", "IN"}:
        if not isinstance(argument, dict) or len(argument) != 1:
            return False
        key, expected = next(iter(argument.items()))
        return (
            context.get(key) == expected
            if operator == "EQ"
            else context.get(key) in expected
        )
    raise Phase03Error("UNREGISTERED_PRECONDITION_OPERATOR")


def _find_sequences(
    tokens: Sequence[Token], phrases: Sequence[Sequence[str]]
) -> list[tuple[int, int]]:
    comparisons = [token.comparison for token in tokens]
    matches: list[tuple[int, int]] = []
    for phrase in phrases:
        width = len(phrase)
        for start in range(0, len(tokens) - width + 1):
            if comparisons[start : start + width] == list(phrase):
                matches.append((start, start + width))
    return sorted(set(matches))


def _identifier_token(token: Token, maximum: int) -> bool:
    return (
        token.kind == "WORD"
        and len(token.raw) <= maximum
        and any(
            unicodedata.category(character)[0] in {"L", "N"} for character in token.raw
        )
    )


def _marker_matches(raw: str, tokens: Sequence[Token], rule: RuleSpec) -> list[_Match]:
    parameters = rule.matching_condition["parameters"]
    results: list[_Match] = []
    if rule.matcher == "MARKER_WITH_IDENTIFIER":
        maximum = int(parameters["identifier_max_codepoints"])
        for start, end in _find_sequences(tokens, parameters["markers"]):
            if end >= len(tokens) or not _identifier_token(tokens[end], maximum):
                continue
            identifier = tokens[end]
            whole = (tokens[start].start, identifier.end)
            value_span = (
                (identifier.start, identifier.end)
                if rule.extractor == "IDENTIFIER_ONLY_SPAN"
                else whole
            )
            results.append(_Match(value_span, (value_span,)))
    elif rule.matcher == "SEGMENT_LEADING_MARKER_WITH_NAME":
        first_nonspace = len(raw) - len(raw.lstrip())
        for start, end in _find_sequences(tokens, parameters["markers"]):
            if tokens[start].start != first_nonspace:
                continue
            words: list[Token] = []
            for token in tokens[end:]:
                if (
                    token.raw in {",", ";"}
                    or "\n" in raw[tokens[end].start : token.end]
                ):
                    break
                if token.kind == "WORD":
                    words.append(token)
                if len(words) == int(parameters["name_max_tokens"]):
                    break
            if not words:
                continue
            span = (words[0].start, words[-1].end)
            if span[1] - span[0] <= int(parameters["name_max_codepoints"]):
                results.append(_Match(span, (span,)))
    elif rule.matcher == "SEGMENT_ENDING_LEGAL_FORM":
        trimmed_start = len(raw) - len(raw.lstrip())
        trimmed_end = len(raw.rstrip())
        for start, end in _find_sequences(tokens, parameters["forms"]):
            if end == len(tokens) and start > 0 and tokens[-1].end == trimmed_end:
                if any(token.kind == "WORD" for token in tokens[:start]):
                    results.append(
                        _Match(
                            (trimmed_start, trimmed_end),
                            ((trimmed_start, trimmed_end),),
                        )
                    )
    elif rule.matcher == "PHRASE_PRESENT":
        for start, end in _find_sequences(tokens, parameters["phrases"]):
            span = (tokens[start].start, tokens[end - 1].end)
            results.append(_Match(span, (span,)))
    elif rule.matcher == "BOUNDED_EDGE_HOUSE_NUMBER":
        results.extend(_house_edge_matches(tokens))
    return results


def _house_token_is_bounded(value: str) -> bool:
    if len(value) > 16 or not any(character.isdigit() for character in value):
        return False
    if re.fullmatch(r"[0-9]{4}", value) and 1900 <= int(value) <= 2099:
        return False
    if re.fullmatch(r"[0-9]+", value):
        return len(value) <= 4
    return re.fullmatch(r"[\w]+", value, flags=re.UNICODE) is not None


def _house_edge_matches(tokens: Sequence[Token]) -> list[_Match]:
    if len(tokens) < 2 or not any(
        token.kind == "WORD" and any(char.isalpha() for char in token.raw)
        for token in tokens
    ):
        return []
    candidates: list[tuple[int, int]] = []
    for index in {0, len(tokens) - 1}:
        token = tokens[index]
        if token.kind == "WORD" and _house_token_is_bounded(token.raw):
            candidates.append((token.start, token.end))
    for start in (0, max(0, len(tokens) - 3)):
        chunk = tokens[start : start + 3]
        if (
            len(chunk) == 3
            and chunk[1].raw in {"-", "/"}
            and all(
                item.kind == "WORD" and _house_token_is_bounded(item.raw)
                for item in (chunk[0], chunk[2])
            )
        ):
            if start == 0 or start + 3 == len(tokens):
                candidates.append((chunk[0].start, chunk[2].end))
    return [_Match(span, (span,)) for span in sorted(set(candidates))]


def _whole_field_match(raw: str) -> list[_Match]:
    return [_Match((0, len(raw)), ((0, len(raw)),))] if raw else []


def _candidate_sort_key(candidate: Candidate) -> tuple[Any, ...]:
    return (
        candidate.selection_priority,
        candidate.rule_id.encode(),
        COMPONENTS.index(candidate.component),
        REPRESENTATIONS.index(candidate.representation),
        candidate.value.encode("utf-8"),
        tuple(
            (span.source_field, span.start_character, span.end_character_exclusive)
            for span in candidate.spans
        ),
    )


def _ordered(values: set[str], vocabulary: Sequence[str]) -> list[str]:
    unknown = values - set(vocabulary)
    if unknown:
        raise Phase03Error("UNREGISTERED_VOCABULARY_VALUE", ",".join(sorted(unknown)))
    return [item for item in vocabulary if item in values]


def _registered_overlap_conflicts(candidates: Sequence[Candidate]) -> set[str]:
    registered_pairs = {
        "UNIT_HOUSE_NUMBER_ROLE_CONFLICT": {"UNIT", "HOUSE_NUMBER"},
        "BUILDING_ORGANIZATION_ROLE_CONFLICT": {"BUILDING", "ORGANIZATION"},
    }
    conflicts: set[str] = set()
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            components = {left.component, right.component}
            for flag, required_components in registered_pairs.items():
                if components != required_components or flag not in {
                    left.conflict_behavior,
                    right.conflict_behavior,
                }:
                    continue
                if any(
                    left_span.source_field == right_span.source_field
                    and left_span.start_character < right_span.end_character_exclusive
                    and right_span.start_character < left_span.end_character_exclusive
                    for left_span in left.spans
                    for right_span in right.spans
                ):
                    conflicts.add(flag)
    return conflicts


def select_candidates(
    candidates: Sequence[Candidate], existing_conflicts: set[str] | None = None
) -> tuple[list[SelectedComponent], set[str], bool]:
    """Apply deterministic priority/tie/conflict selection to registered candidates."""
    conflicts = set(existing_conflicts or ())
    groups: dict[tuple[str, str], list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.selectable and candidate.confidence != "LOW":
            groups[(candidate.component, candidate.representation)].append(candidate)
    selected: list[SelectedComponent] = []
    ambiguous = False
    for key in sorted(
        groups,
        key=lambda item: (COMPONENTS.index(item[0]), REPRESENTATIONS.index(item[1])),
    ):
        group = groups[key]
        best_priority = min(candidate.selection_priority for candidate in group)
        best = [
            candidate
            for candidate in group
            if candidate.selection_priority == best_priority
        ]
        values = {candidate.value for candidate in best}
        all_values = {candidate.value for candidate in group}
        if len(all_values) > 1:
            flag = _CONFLICT_BY_COMPONENT.get(key[0])
            if flag:
                conflicts.add(flag)
            ambiguous = True
            continue
        if len(values) != 1:
            ambiguous = True
            continue
        value = next(iter(values))
        supporting = [candidate for candidate in group if candidate.value == value]
        selected.append(
            SelectedComponent(
                component=key[0],
                representation=key[1],
                value=value,
                confidence=min(
                    (candidate.confidence for candidate in supporting),
                    key=("HIGH", "MEDIUM", "LOW").index,
                ),
                source_fields=tuple(
                    dict.fromkeys(
                        field
                        for candidate in supporting
                        for field in candidate.source_fields
                    )
                ),
                rule_ids=tuple(
                    dict.fromkeys(candidate.rule_id for candidate in supporting)
                ),
            )
        )
    return selected, conflicts, ambiguous


def postcode_diagnostics(raw: str, state: str, normalized: str | None) -> list[str]:
    flags: set[str] = set()
    if raw == "":
        flags.add("POSTCODE_SOURCE_EMPTY")
    if state == "SEMANTIC_MISSING":
        flags.add("POSTCODE_SEMANTIC_MISSING")
    elif state == "AMBIGUOUS_PLACEHOLDER_LIKE":
        flags.add("POSTCODE_AMBIGUOUS_PLACEHOLDER_LIKE")
    elif raw.isdigit():
        flags.add("POSTCODE_DIGITS_ONLY")
        if len(raw) > 1 and raw.startswith("0"):
            flags.add("POSTCODE_LEADING_ZERO")
    elif re.fullmatch(r"[0-9]+\.[0-9]+", raw):
        flags.add("POSTCODE_DECIMAL_LOOKING")
    elif raw.isalpha():
        flags.add("POSTCODE_ALPHABETIC")
    elif any(char.isalpha() for char in raw) and any(char.isdigit() for char in raw):
        flags.add("POSTCODE_ALPHANUMERIC")
    elif state == "CONTENT":
        flags.add("POSTCODE_OTHER")
    if any(char.isspace() for char in raw):
        flags.add("POSTCODE_CONTAINS_WHITESPACE")
    if "-" in raw:
        flags.add("POSTCODE_CONTAINS_HYPHEN")
    if normalized is not None and normalized != raw:
        flags.add("POSTCODE_NORMALIZED_WHITESPACE")
    return _ordered(flags, POSTCODE_FLAGS)


def native_relationship(
    non_native: str, native: str, scripts: ScriptReference | None
) -> str:
    non_state, native_state = (
        classify_placeholder(non_native),
        classify_placeholder(native),
    )
    if non_state == native_state == "SEMANTIC_MISSING":
        return "BOTH_SEMANTICALLY_MISSING"
    if non_state == "SEMANTIC_MISSING" and native_state != "SEMANTIC_MISSING":
        return "NATIVE_ONLY"
    if native_state == "SEMANTIC_MISSING" and non_state != "SEMANTIC_MISSING":
        return "NON_NATIVE_ONLY"
    if non_native == native:
        return "EXACT_EQUAL"
    if unicodedata.normalize("NFC", non_native) == unicodedata.normalize("NFC", native):
        return "NFC_EQUAL"
    if scripts is None:
        return "MIXED_OR_UNDETERMINED"
    left, right = (
        scripts.distinctive_scripts(non_native),
        scripts.distinctive_scripts(native),
    )
    if len(left) == len(right) == 1:
        return "SAME_SCRIPT_DIFFERENT" if left == right else "DIFFERENT_SCRIPT"
    return "MIXED_OR_UNDETERMINED"


def _completeness(values: Mapping[str, str | None]) -> str:
    country, locality = values["country_clean"], values["locality_clean"]
    street, house = values["street_clean"], values["house_number_clean"]
    building, postcode = values["building_clean"], values["postcode_clean"]
    if country and locality and street and house and postcode:
        return "A_POINT_CORE_WITH_POSTCODE"
    if country and locality and street and house:
        return "B_POINT_CORE"
    if country and locality and street:
        return "C_STREET_LEVEL"
    if country and locality and not street and not house:
        return "D_LOCALITY_LEVEL"
    if country and not any((locality, street, house, building)):
        return "E_COUNTRY_ONLY"
    if any((street, house, building)) and (not country or not locality):
        return "F_ADDRESS_WITH_GEOGRAPHY_GAPS"
    if any(value for key, value in values.items() if key.endswith("_clean")):
        return "G_OTHER_PARTIAL"
    return "Z_NO_COMPONENTS"


class Phase03Engine:
    def __init__(
        self,
        config: Phase03Config,
        registry: RuleRegistry,
        *,
        country_reference: CountryReference | None = None,
        script_reference: ScriptReference | None = None,
        implementation_fingerprint: bytes,
    ) -> None:
        config.validate()
        enforce_runtime_contract(
            config.expected_python_version, config.expected_unicode_version
        )
        if len(implementation_fingerprint) != 32:
            raise ValueError("implementation fingerprint must be 32 bytes")
        self.config = config
        self.registry = registry
        self.country_reference = country_reference
        self.script_reference = script_reference
        self.implementation_fingerprint = implementation_fingerprint
        self.configuration_fingerprint = bytes.fromhex(
            fingerprint(
                {
                    "version": "phase03_effective_configuration_v1",
                    "base_configuration_fingerprint": (
                        config.configuration_fingerprint().hex()
                    ),
                    "rule_registry_fingerprint": registry.fingerprint,
                    "country_assignment_reference": (
                        {
                            "reference_id": country_reference.assignment_manifest.reference_id,
                            "artifact_sha256": (
                                country_reference.assignment_manifest.artifact_sha256
                            ),
                            "loader_schema_version": (
                                country_reference.assignment_manifest.loader_schema_version
                            ),
                        }
                        if country_reference
                        else {"reference_id": config.country_reference_version}
                    ),
                    "country_name_reference": (
                        {
                            "reference_id": country_reference.name_manifest.reference_id,
                            "artifact_sha256": (
                                country_reference.name_manifest.artifact_sha256
                            ),
                            "loader_schema_version": (
                                country_reference.name_manifest.loader_schema_version
                            ),
                        }
                        if country_reference
                        else {"reference_id": config.country_reference_version}
                    ),
                    "script_reference": (
                        {
                            "reference_id": script_reference.manifest.reference_id,
                            "artifact_sha256": script_reference.manifest.artifact_sha256,
                            "loader_schema_version": (
                                script_reference.manifest.loader_schema_version
                            ),
                            "unicode_version": script_reference.manifest.unicode_version,
                        }
                        if script_reference
                        else {"reference_id": config.unicode_reference_version}
                    ),
                }
            )
        )

    def transform(self, row: Mapping[str, Any]) -> TransformResult:
        self._validate_input(row)
        raw = {
            field: str(row[field])
            for field in (
                *ADDRESS_FIELDS,
                "postcode",
                "city",
                "region_in_country",
                "country_iso_code",
            )
        }
        states = {field: classify_placeholder(value) for field, value in raw.items()}
        byte_lengths = {
            field: len(value.encode("utf-8")) for field, value in raw.items()
        }
        safe = {
            field: byte_lengths[field] <= self.config.per_field_freeform_limit_bytes
            for field in raw
        }
        address_total = sum(byte_lengths[field] for field in ADDRESS_FIELDS)
        if address_total > self.config.combined_freeform_limit_bytes:
            running = 0
            for field in ADDRESS_FIELDS:
                running += byte_lengths[field]
                if (
                    running > self.config.combined_freeform_limit_bytes
                    and byte_lengths[field] > 0
                ):
                    safe[field] = False
        skipped = [field for field in raw if not safe[field]]
        evaluated = [field for field in raw if safe[field]]
        evaluation = (
            "FULLY_EVALUATED"
            if not skipped
            else "PARTIALLY_SKIPPED_OVERSIZED"
            if evaluated
            else "NOT_EVALUATED_OVERSIZED"
        )
        candidates: list[Candidate] = []
        diagnostics: set[str] = set()
        conflicts: set[str] = set()
        historical_spans: list[tuple[str, int, int, str]] = []
        country_kinds: dict[tuple[str, str], str] = {}
        country_input_class = self._country_input_class(
            raw["country_iso_code"], states["country_iso_code"]
        )
        if country_input_class == "REGION_LIKE":
            diagnostics.add("COUNTRY_STRUCTURED_REGION_LIKE")
        elif country_input_class in {"ALPHA2_CASE_VARIANT", "UNKNOWN_TEXT"}:
            diagnostics.add("COUNTRY_STRUCTURED_UNRECOGNIZED")

        for field, state in states.items():
            if state == "AMBIGUOUS_PLACEHOLDER_LIKE":
                diagnostics.add("AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT")
        if skipped:
            diagnostics.add("OVERSIZED_INPUT")

        candidate_limit_reached = False
        for rule in self.registry.ordered_rules():
            if candidate_limit_reached:
                break
            for field in rule.eligible_source_fields:
                value = raw[field]
                if not safe[field] or byte_lengths[field] > min(
                    rule.maximum_input_utf8_bytes,
                    self.config.per_field_freeform_limit_bytes,
                ):
                    continue
                context = {
                    "semantic_state": states[field],
                    "evaluation_status": evaluation,
                    "candidate_count": len(candidates),
                }
                if not _precondition_matches(rule.preconditions, context):
                    continue
                matches: list[_Match]
                if rule.matcher == "WHOLE_FIELD_CONTENT":
                    matches = _whole_field_match(value)
                elif rule.matcher == "COUNTRY_REFERENCE_EXACT":
                    matches = self._country_matches(value, states[field])
                else:
                    matches = _marker_matches(value, tokenize_with_spans(value), rule)
                for match in matches:
                    if rule.component == "DIAGNOSTIC_ONLY":
                        diagnostics.add("HISTORICAL_EVIDENCE")
                        historical_spans.append(
                            (field, *match.evidence_spans[0], rule.rule_id)
                        )
                        continue
                    candidate_value = match.reference_value or normalize_derived_text(
                        value[match.value_span[0] : match.value_span[1]]
                    )
                    if candidate_value is None:
                        continue
                    representation = (
                        representation_for_field(field)
                        if rule.representation == "ANY"
                        else rule.representation
                    )
                    spans = tuple(
                        RawSpan(field, start, end)
                        for start, end in match.evidence_spans
                    )
                    selectable = rule.selectable
                    if states[field] == "AMBIGUOUS_PLACEHOLDER_LIKE":
                        selectable = False
                    candidate = Candidate(
                        component=rule.component,
                        value=candidate_value,
                        representation=representation,
                        confidence=rule.confidence,
                        rule_id=rule.rule_id,
                        selection_priority=rule.selection_priority,
                        selectable=selectable,
                        spans=spans,
                        source_fields=(field,),
                        conflict_behavior=rule.conflict_behavior,
                    )
                    candidates.append(candidate)
                    if rule.component == "COUNTRY" and match.reference_kind:
                        country_kinds[(field, candidate.value)] = match.reference_kind
                    if not self._within_candidate_limits(candidates):
                        candidates.pop()
                        diagnostics.add("CANDIDATE_LIMIT_EXCEEDED")
                        candidate_limit_reached = True
                        break

        explicit_role_spans = {
            (span.source_field, span.start_character, span.end_character_exclusive)
            for candidate in candidates
            if candidate.component in {"UNIT", "FLOOR", "PO_BOX"}
            and candidate.confidence == "HIGH"
            for span in candidate.spans
        }
        candidates = [
            candidate
            for candidate in candidates
            if not (
                candidate.component == "HOUSE_NUMBER"
                and any(
                    (
                        span.source_field,
                        span.start_character,
                        span.end_character_exclusive,
                    )
                    in explicit_role_spans
                    for span in candidate.spans
                )
            )
        ]
        conflicts.update(_registered_overlap_conflicts(candidates))
        self._apply_country_collision(
            raw, states, candidates, country_kinds, diagnostics, conflicts
        )
        structured_country_values = {
            candidate.value
            for candidate in candidates
            if candidate.component == "COUNTRY"
            and candidate.source_fields == ("country_iso_code",)
        }
        freeform_country_values = {
            candidate.value
            for candidate in candidates
            if candidate.component == "COUNTRY"
            and candidate.source_fields != ("country_iso_code",)
        }
        if states["country_iso_code"] == "SEMANTIC_MISSING" and freeform_country_values:
            diagnostics.add("STRUCTURED_GEOGRAPHY_MISSING_FREEFORM_PRESENT")
        if (
            structured_country_values
            and freeform_country_values - structured_country_values
        ):
            conflicts.add("COUNTRY_SOURCE_CONFLICT")
        candidates = sorted(candidates, key=_candidate_sort_key)
        selected, conflicts, ambiguous = select_candidates(candidates, conflicts)
        conflicted_components = {
            component
            for flag in conflicts
            for component in _COMPONENTS_BY_CONFLICT.get(flag, set())
        }
        selected = [
            item for item in selected if item.component not in conflicted_components
        ]
        if any(candidate.component == "PO_BOX" for candidate in candidates):
            diagnostics.update({"PO_BOX_EVIDENCE", "PROBABLE_NON_PHYSICAL"})
        if any(candidate.component == "ORGANIZATION" for candidate in candidates):
            diagnostics.add("PROBABLE_ORGANIZATION_TEXT")
        if historical_spans:
            diagnostics.add("HISTORICAL_EVIDENCE")

        selected_values: dict[str, str | None] = {
            name: None for name in _COMPONENT_TO_SCALAR.values()
        }
        for item in selected:
            scalar = _COMPONENT_TO_SCALAR.get((item.component, item.representation))
            if scalar is not None:
                selected_values[scalar] = item.value

        selected_keys_for_assignment = {
            (item.component, item.representation, item.value) for item in selected
        }
        candidate_fields = {
            span.source_field
            for candidate in candidates
            if (candidate.component, candidate.representation, candidate.value)
            in selected_keys_for_assignment
            for span in candidate.spans
        }
        unassigned_fields = [
            field
            for field in ADDRESS_FIELDS
            if safe[field]
            and states[field] == "CONTENT"
            and field not in candidate_fields
        ]
        if unassigned_fields:
            diagnostics.add("UNASSIGNED_CONTENT_PRESENT")

        parse_status = self._parse_status(
            selected, conflicts, ambiguous, unassigned_fields, states, evaluation
        )
        completeness = _completeness(selected_values)
        country_method, country_confidence = self._country_result(
            selected, candidates, country_kinds, conflicts, diagnostics
        )
        native_relationships = [
            {
                "line_number": line,
                "relationship": native_relationship(
                    raw[f"street_address_line_{line}"],
                    raw[f"street_address_line_{line}_native"],
                    self.script_reference,
                ),
            }
            for line in range(1, 5)
        ]
        if any(item["relationship"] == "NATIVE_ONLY" for item in native_relationships):
            diagnostics.add("NATIVE_ONLY_CONTENT")
        if any(
            item["relationship"] == "NON_NATIVE_ONLY" for item in native_relationships
        ):
            diagnostics.add("NON_NATIVE_ONLY_CONTENT")
        if any(
            item["relationship"]
            in {"SAME_SCRIPT_DIFFERENT", "DIFFERENT_SCRIPT", "MIXED_OR_UNDETERMINED"}
            for item in native_relationships
        ):
            diagnostics.add("NATIVE_NON_NATIVE_TEXT_DIFFERENT")

        is_fully_evaluated = evaluation == "FULLY_EVALUATED"
        is_po_box = any(item.component == "PO_BOX" for item in selected)
        is_historical = bool(historical_spans)
        has_organization = any(
            candidate.component == "ORGANIZATION" for candidate in candidates
        )
        possible_company_only = has_organization and not any(
            selected_values[name]
            for name in (
                "street_clean",
                "house_number_clean",
                "building_clean",
                "postcode_clean",
                "locality_clean",
            )
        )
        if possible_company_only:
            diagnostics.add("POSSIBLE_COMPANY_ONLY")

        core: dict[str, Any] = {
            "stable_source_row_id_v1": row["stable_source_row_id_v1"],
            "id": row["id"],
            "source_file": row["source_file"],
            "source_logical_record_number": row["source_logical_record_number"],
            "source_file_sha256": row["source_file_sha256"],
            **selected_values,
            "country_input_class": country_input_class,
            "country_parse_method": country_method,
            "country_parse_confidence": country_confidence,
            "address_parse_status": parse_status,
            "address_completeness_class": completeness,
            "address_conflict_flags": _ordered(conflicts, CONFLICT_FLAGS),
            "address_diagnostic_flags": _ordered(diagnostics, DIAGNOSTIC_FLAGS),
            "postcode_diagnostic_flags": postcode_diagnostics(
                raw["postcode"],
                states["postcode"],
                normalize_derived_text(raw["postcode"]),
            ),
            "selected_component_provenance": self._selected_provenance(selected),
            "native_non_native_relationships": native_relationships,
            "diagnostic_evaluation_status": evaluation,
            "skipped_oversized_fields": [
                field
                for field in (
                    *ADDRESS_FIELDS,
                    "postcode",
                    "city",
                    "region_in_country",
                    "country_iso_code",
                )
                if field in skipped
            ],
            "is_po_box": is_po_box
            if is_fully_evaluated
            else (True if is_po_box else None),
            "is_historical": is_historical
            if is_fully_evaluated
            else (True if is_historical else None),
            "probable_non_physical_address": is_po_box
            if is_fully_evaluated
            else (True if is_po_box else None),
            "possible_company_only": possible_company_only
            if is_fully_evaluated
            else (True if possible_company_only else None),
            "input_max_field_utf8_bytes": max(byte_lengths.values()),
            "parser_version": self.config.parser_version,
            "rule_registry_version": self.registry.registry_version,
            "cleaning_rules_version": self.config.cleaning_rules_version,
            "placeholder_policy_version": self.config.placeholder_policy_version,
            "country_reference_version": self.country_reference.version
            if self.country_reference
            else self.config.country_reference_version,
            "unicode_reference_version": self.script_reference.version
            if self.script_reference
            else self.config.unicode_reference_version,
            "diagnostic_vocabulary_version": self.config.diagnostic_vocabulary_version,
            "component_schema_version": self.config.component_schema_version,
            "phase03_version": self.config.phase03_version,
            "configuration_fingerprint": self.configuration_fingerprint,
            "implementation_fingerprint": self.implementation_fingerprint,
        }
        evidence = self._evidence_rows(
            row,
            raw,
            states,
            candidates,
            selected,
            conflicts,
            diagnostics,
            historical_spans,
            unassigned_fields,
        )
        return TransformResult(
            core_row=core, evidence_rows=evidence, candidates=tuple(candidates)
        )

    def _validate_input(self, row: Mapping[str, Any]) -> None:
        required = {
            *ADDRESS_FIELDS,
            "postcode",
            "city",
            "region_in_country",
            "country_iso_code",
            "id",
            "source_file",
            "source_logical_record_number",
            "stable_source_row_id_v1",
            "source_file_sha256",
        }
        if not required.issubset(row):
            raise Phase03Error(
                "PHASE02_ROW_SCHEMA_MISMATCH", "required fields are absent"
            )
        if any(
            not isinstance(row[field], str)
            for field in (
                *ADDRESS_FIELDS,
                "postcode",
                "city",
                "region_in_country",
                "country_iso_code",
                "id",
                "source_file",
            )
        ):
            raise Phase03Error(
                "PHASE02_ROW_TYPE_MISMATCH", "raw/provenance strings are required"
            )
        if (
            not isinstance(row["stable_source_row_id_v1"], bytes)
            or len(row["stable_source_row_id_v1"]) != 32
        ):
            raise Phase03Error("PHASE02_STABLE_ID_INVALID")
        if (
            not isinstance(row["source_file_sha256"], bytes)
            or len(row["source_file_sha256"]) != 32
        ):
            raise Phase03Error("PHASE02_SOURCE_HASH_INVALID")
        if (
            not isinstance(row["source_logical_record_number"], int)
            or row["source_logical_record_number"] < 1
        ):
            raise Phase03Error("PHASE02_SOURCE_ROW_NUMBER_INVALID")

    def _country_matches(self, raw: str, state: str) -> list[_Match]:
        if self.country_reference is None or state == "SEMANTIC_MISSING":
            return []
        record, kind = self.country_reference.exact_lookup(raw)
        if record is None:
            return []
        return [_Match((0, len(raw)), ((0, len(raw)),), record.alpha2, kind)]

    def _country_input_class(self, raw: str, state: str) -> str:
        if state != "CONTENT":
            return state
        if self.country_reference:
            record, kind = self.country_reference.exact_lookup(raw)
            if record:
                return {
                    "ALPHA2": "ALPHA2_ASSIGNED_EXACT",
                    "ALPHA3": "ALPHA3_ASSIGNED_EXACT",
                    "NAME": "COUNTRY_NAME_EXACT",
                }[kind]
            if (
                len(raw) == 2
                and raw.upper() != raw
                and self.country_reference.exact_lookup(raw.upper())[0]
            ):
                return "ALPHA2_CASE_VARIANT"
        if len(raw) > 3 and any(char.isspace() for char in raw):
            return "REGION_LIKE"
        return "UNKNOWN_TEXT"

    def _within_candidate_limits(self, candidates: list[Candidate]) -> bool:
        counts: dict[str, int] = defaultdict(int)
        for candidate in candidates:
            counts[candidate.component] += 1
        return not (
            len(candidates) > self.config.max_candidates_per_row
            or any(
                count > self.config.max_candidates_per_component
                for count in counts.values()
            )
        )

    def _apply_country_collision(
        self,
        raw: Mapping[str, str],
        states: Mapping[str, str],
        candidates: list[Candidate],
        country_kinds: dict[tuple[str, str], str],
        diagnostics: set[str],
        conflicts: set[str],
    ) -> None:
        if states["country_iso_code"] != "AMBIGUOUS_PLACEHOLDER_LIKE":
            return
        freeform = [
            candidate
            for candidate in candidates
            if candidate.component == "COUNTRY"
            and candidate.source_fields != ("country_iso_code",)
        ]
        if (
            raw["country_iso_code"] == "Na"
            and freeform
            and {candidate.value for candidate in freeform} == {"NA"}
        ):
            span = RawSpan("country_iso_code", 0, 2)
            candidates.append(
                Candidate(
                    component="COUNTRY",
                    value="NA",
                    representation="SHARED",
                    confidence="HIGH",
                    rule_id="COUNTRY_STRUCTURED_REFERENCE_V1",
                    selection_priority=40,
                    selectable=True,
                    spans=(span,),
                    source_fields=("country_iso_code",),
                    conflict_behavior="COUNTRY_DIFFERENT_VALUES_CONFLICT",
                )
            )
            country_kinds[("country_iso_code", "NA")] = "CORROBORATED_COLLISION"
            diagnostics.add("PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED")
        elif freeform:
            conflicts.add("COUNTRY_SOURCE_CONFLICT")
            diagnostics.add("PLACEHOLDER_REFERENCE_COLLISION_UNRESOLVED")
        else:
            diagnostics.add("PLACEHOLDER_REFERENCE_COLLISION_UNRESOLVED")

    def _parse_status(
        self,
        selected: Sequence[SelectedComponent],
        conflicts: set[str],
        ambiguous: bool,
        unassigned: Sequence[str],
        states: Mapping[str, str],
        evaluation: str,
    ) -> str:
        if conflicts:
            return "CONFLICT"
        if ambiguous:
            return "AMBIGUOUS"
        address_components = {item.component for item in selected} & {
            "STREET",
            "HOUSE_NUMBER",
            "UNIT",
            "FLOOR",
            "BUILDING",
            "ORGANIZATION",
            "PO_BOX",
        }
        if address_components:
            return (
                "PARTIAL" if unassigned or evaluation != "FULLY_EVALUATED" else "PARSED"
            )
        if any(state == "CONTENT" for state in states.values()):
            return "UNPARSEABLE" if unassigned else "INSUFFICIENT"
        return "INSUFFICIENT"

    def _country_result(
        self,
        selected: Sequence[SelectedComponent],
        candidates: Sequence[Candidate],
        kinds: Mapping[tuple[str, str], str],
        conflicts: set[str],
        diagnostics: set[str],
    ) -> tuple[str, str]:
        if any(flag.startswith("COUNTRY_") for flag in conflicts):
            return "CONFLICT", "UNRESOLVED"
        country = next(
            (
                item
                for item in selected
                if item.component == "COUNTRY" and item.representation == "SHARED"
            ),
            None,
        )
        if country is None:
            return "UNRESOLVED", "UNRESOLVED"
        if "PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED" in diagnostics:
            return "MULTISOURCE_CORROBORATED_PLACEHOLDER_COLLISION", "HIGH"
        kinds_for_value = {
            kinds[(field, candidate.value)]
            for candidate in candidates
            if candidate.value == country.value
            for field in candidate.source_fields
            if (field, candidate.value) in kinds
        }
        if len(country.source_fields) > 1:
            return "MULTISOURCE_AGREEMENT", country.confidence
        source_field = country.source_fields[0]
        kind = next(iter(kinds_for_value), "NONE")
        mapping = (
            _COUNTRY_SOURCE_METHOD
            if source_field == "country_iso_code"
            else _COUNTRY_FREE_METHOD
        )
        return mapping.get(kind, "UNRESOLVED"), country.confidence

    def _selected_provenance(
        self, selected: Sequence[SelectedComponent]
    ) -> list[dict[str, Any]]:
        return [
            {
                "component": item.component,
                "representation": item.representation,
                "source_fields": list(item.source_fields),
                "rule_ids": list(item.rule_ids),
                "confidence": item.confidence,
            }
            for item in sorted(
                selected,
                key=lambda item: (
                    COMPONENTS.index(item.component),
                    REPRESENTATIONS.index(item.representation),
                ),
            )
        ]

    def _evidence_rows(
        self,
        row: Mapping[str, Any],
        raw: Mapping[str, str],
        states: Mapping[str, str],
        candidates: Sequence[Candidate],
        selected: Sequence[SelectedComponent],
        conflicts: set[str],
        diagnostics: set[str],
        historical_spans: Sequence[tuple[str, int, int, str]],
        unassigned_fields: Sequence[str],
    ) -> list[dict[str, Any]]:
        selected_keys = {
            (item.component, item.representation, item.value) for item in selected
        }
        groups: list[dict[str, Any]] = []
        for candidate in candidates:
            is_selected = (
                candidate.component,
                candidate.representation,
                candidate.value,
            ) in selected_keys
            trivial = candidate.rule_id in {
                "POSTCODE_STRUCTURED_DIRECT_V1",
                "LOCALITY_STRUCTURED_DIRECT_V1",
                "REGION_STRUCTURED_DIRECT_V1",
                "COUNTRY_STRUCTURED_REFERENCE_V1",
            }
            if is_selected and trivial and not conflicts:
                continue
            kind = (
                "SELECTED_NONTRIVIAL_COMPONENT"
                if is_selected
                else "UNSELECTED_CANDIDATE"
            )
            candidate_conflicts = [
                flag
                for flag in CONFLICT_FLAGS
                if flag in conflicts
                and candidate.component in _COMPONENTS_BY_CONFLICT.get(flag, set())
            ]
            if candidate_conflicts:
                kind = "CONFLICTING_EVIDENCE"
            groups.append(
                {
                    "kind": kind,
                    "component": candidate.component,
                    "representation": candidate.representation,
                    "candidate_value": candidate.value,
                    "selected": is_selected,
                    "confidence": candidate.confidence,
                    "rule_id": candidate.rule_id,
                    "conflict_flag": candidate_conflicts[0]
                    if candidate_conflicts
                    else None,
                    "diagnostic_flag": None,
                    "spans": candidate.spans,
                }
            )
        for field, state in states.items():
            if state == "AMBIGUOUS_PLACEHOLDER_LIKE":
                groups.append(
                    {
                        "kind": "AMBIGUOUS_PLACEHOLDER",
                        "component": None,
                        "representation": None,
                        "candidate_value": None,
                        "selected": False,
                        "confidence": None,
                        "rule_id": None,
                        "conflict_flag": None,
                        "diagnostic_flag": "AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT",
                        "spans": (RawSpan(field, 0, len(raw[field])),),
                    }
                )
        for field, start, end, rule_id in historical_spans:
            groups.append(
                {
                    "kind": "UNASSIGNED_MATERIAL_CONTENT",
                    "component": None,
                    "representation": None,
                    "candidate_value": None,
                    "selected": False,
                    "confidence": None,
                    "rule_id": rule_id,
                    "conflict_flag": None,
                    "diagnostic_flag": "HISTORICAL_EVIDENCE",
                    "spans": (RawSpan(field, start, end),),
                }
            )
        for field in unassigned_fields:
            groups.append(
                {
                    "kind": "UNASSIGNED_MATERIAL_CONTENT",
                    "component": None,
                    "representation": representation_for_field(field),
                    "candidate_value": None,
                    "selected": False,
                    "confidence": None,
                    "rule_id": None,
                    "conflict_flag": None,
                    "diagnostic_flag": "UNASSIGNED_CONTENT_PRESENT",
                    "spans": (RawSpan(field, 0, len(raw[field])),),
                }
            )
        groups.sort(
            key=lambda group: (
                EVIDENCE_KINDS.index(group["kind"]),
                COMPONENTS.index(group["component"])
                if group["component"] in COMPONENTS
                else len(COMPONENTS),
                REPRESENTATIONS.index(group["representation"])
                if group["representation"] in REPRESENTATIONS
                else len(REPRESENTATIONS),
                (group["candidate_value"] or "").encode(),
                group["rule_id"] or "",
                tuple(
                    (
                        span.source_field,
                        span.start_character,
                        span.end_character_exclusive,
                    )
                    for span in group["spans"]
                ),
            )
        )
        output: list[dict[str, Any]] = []
        for evidence_id, group in enumerate(groups, start=1):
            spans = sorted(
                group["spans"],
                key=lambda span: (
                    ADDRESS_FIELDS.index(span.source_field)
                    if span.source_field in ADDRESS_FIELDS
                    else 100
                    + (
                        "postcode",
                        "city",
                        "region_in_country",
                        "country_iso_code",
                    ).index(span.source_field),
                    span.start_character,
                    span.end_character_exclusive,
                ),
            )
            for span_ordinal, span in enumerate(spans, start=1):
                span.validate(raw[span.source_field])
                output.append(
                    {
                        "stable_source_row_id_v1": row["stable_source_row_id_v1"],
                        "source_file": row["source_file"],
                        "source_logical_record_number": row[
                            "source_logical_record_number"
                        ],
                        "evidence_id": evidence_id,
                        "span_ordinal": span_ordinal,
                        "evidence_kind": group["kind"],
                        "component": group["component"],
                        "representation": group["representation"],
                        "candidate_value": group["candidate_value"],
                        "selected": group["selected"],
                        "confidence": group["confidence"],
                        "rule_id": group["rule_id"],
                        "source_field": span.source_field,
                        "start_character": span.start_character,
                        "end_character_exclusive": span.end_character_exclusive,
                        "conflict_flag": group["conflict_flag"],
                        "diagnostic_flag": group["diagnostic_flag"],
                        "parser_version": self.config.parser_version,
                        "rule_registry_version": self.registry.registry_version,
                        "phase03_version": self.config.phase03_version,
                    }
                )
        return output

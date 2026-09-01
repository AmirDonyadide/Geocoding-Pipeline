"""Prospective Stage 7 v2 component-readiness screen.

This module is design-diagnostic code.  It does not alter the immutable Stage 7
v1 registry and it does not map libpostal labels into Stage 8 fields.  The rule
uses only trusted Stage 6 provenance and the ordered raw Stage 7 parse.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from .s07_country_eligibility import (
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
)
from .s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
)


READINESS_RULE_VERSION = "stage07_component_readiness_rule_v1"

COMPONENTS_READY = "COMPONENTS_READY"
COMPONENTS_ABSTAIN = "COMPONENTS_ABSTAIN"
NOT_ASSESSED = "NOT_ASSESSED"
READINESS_STATUSES = (COMPONENTS_READY, COMPONENTS_ABSTAIN, NOT_ASSESSED)

NOT_ATTEMPTED_NOT_ELIGIBLE = "NOT_ATTEMPTED_NOT_ELIGIBLE"
TECHNICAL_STATUSES = (PARSED_NONEMPTY, PARSED_EMPTY, NOT_ATTEMPTED_NOT_ELIGIBLE)

REASON_ELIGIBILITY_MISSING = "PARSER_ELIGIBILITY_MISSING_COUNTRY"
REASON_ELIGIBILITY_PARTIAL = "PARSER_ELIGIBILITY_PARTIAL_COUNTRY"
REASON_ELIGIBILITY_INVALID = "PARSER_ELIGIBILITY_INVALID_COUNTRY"
REASON_ELIGIBILITY_AMBIGUOUS = "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY"
REASON_PARSED_EMPTY = "PARSED_EMPTY_NO_COMPONENTS"
REASON_EMPTY_COMPONENT_VALUE = "EMPTY_COMPONENT_VALUE"
REASON_RAW_ALIGNMENT = "RAW_ORDERED_SUBSTRING_ALIGNMENT_FAILURE"
REASON_LEXICAL_LOSS = "LEXICAL_NUMERIC_MATERIAL_LOSS"
REASON_LEXICAL_DUPLICATION = "LEXICAL_NUMERIC_MATERIAL_DUPLICATION"
REASON_LEXICAL_DIVERGENCE = "LEXICAL_NUMERIC_REORDER_OR_SUBSTITUTION"
REASON_INTERNAL_BOUNDARY = "TOKEN_INTERNAL_COMPONENT_BOUNDARY"
REASON_TINY_FRAGMENT = "TOKEN_INTERNAL_SINGLE_CODEPOINT_FRAGMENT"
REASON_FRAGMENTATION = "LEXICAL_RUN_SPLIT_ACROSS_THREE_OR_MORE_COMPONENTS"
REASON_REPEATED_LABEL = "ADJACENT_REPEATED_LABEL_AT_INTERNAL_BOUNDARY"

REASON_ORDER = (
    REASON_ELIGIBILITY_MISSING,
    REASON_ELIGIBILITY_PARTIAL,
    REASON_ELIGIBILITY_INVALID,
    REASON_ELIGIBILITY_AMBIGUOUS,
    REASON_PARSED_EMPTY,
    REASON_EMPTY_COMPONENT_VALUE,
    REASON_RAW_ALIGNMENT,
    REASON_LEXICAL_LOSS,
    REASON_LEXICAL_DUPLICATION,
    REASON_LEXICAL_DIVERGENCE,
    REASON_INTERNAL_BOUNDARY,
    REASON_TINY_FRAGMENT,
    REASON_FRAGMENTATION,
    REASON_REPEATED_LABEL,
)

STRUCTURAL_ABSTENTION_REASONS = frozenset(
    {
        REASON_EMPTY_COMPONENT_VALUE,
        REASON_RAW_ALIGNMENT,
        REASON_LEXICAL_LOSS,
        REASON_LEXICAL_DUPLICATION,
        REASON_LEXICAL_DIVERGENCE,
        REASON_INTERNAL_BOUNDARY,
        REASON_TINY_FRAGMENT,
        REASON_FRAGMENTATION,
        REASON_REPEATED_LABEL,
    }
)

_ELIGIBILITY_REASON: dict[str, str] = {
    PARSER_ELIGIBILITY_MISSING_COUNTRY: REASON_ELIGIBILITY_MISSING,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY: REASON_ELIGIBILITY_PARTIAL,
    PARSER_ELIGIBILITY_INVALID_COUNTRY: REASON_ELIGIBILITY_INVALID,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY: REASON_ELIGIBILITY_AMBIGUOUS,
}


class Stage07ReadinessError(ValueError):
    """A prospective readiness input violates its fail-closed contract."""


@dataclass(frozen=True, slots=True)
class StructuralSignals:
    """Mechanically derived parser-local evidence, never semantic truth."""

    raw_ordered_substrings: bool
    lexical_numeric_stream_equal: bool
    internal_boundary_count: int
    internal_single_codepoint_fragment_count: int
    maximum_components_per_lexical_run: int
    adjacent_repeated_label_internal_boundary_count: int
    candidate_lexical_numeric_codepoints: int
    output_lexical_numeric_codepoints: int
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReadinessDecision:
    """One prospective readiness outcome and its deterministic evidence."""

    status: str
    reason_codes: tuple[str, ...]
    signals: StructuralSignals | None


def _is_lexical_numeric(character: str) -> bool:
    return unicodedata.category(character)[0] in {"L", "M", "N"}


def _stream_and_source_positions(value: str) -> tuple[str, tuple[int, ...]]:
    characters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(value):
        if _is_lexical_numeric(character):
            characters.append(character)
            positions.append(index)
    return "".join(characters), tuple(positions)


def _is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    offset = 0
    for character in haystack:
        if character == needle[offset]:
            offset += 1
            if offset == len(needle):
                return True
    return False


def _ordered_substrings(
    candidate: str, components: tuple[LibpostalComponent, ...]
) -> bool:
    offset = 0
    for component in components:
        found = candidate.find(component.value, offset)
        if found < 0:
            return False
        offset = found + len(component.value)
    return True


def structural_signals(
    candidate: str, components: tuple[LibpostalComponent, ...]
) -> StructuralSignals:
    """Return exact, linear-time structural signals for one parsed candidate."""
    if not isinstance(candidate, str):
        raise Stage07ReadinessError("candidate must be a string")
    if not components:
        raise Stage07ReadinessError("nonempty parse must contain a component")

    candidate_stream, source_positions = _stream_and_source_positions(candidate)
    component_streams = tuple(
        _stream_and_source_positions(component.value)[0] for component in components
    )
    output_stream = "".join(component_streams)
    stream_equal = candidate_stream == output_stream
    raw_ordered = _ordered_substrings(candidate, components)
    reasons: set[str] = set()
    if any(component.value == "" for component in components):
        reasons.add(REASON_EMPTY_COMPONENT_VALUE)
    if not raw_ordered:
        reasons.add(REASON_RAW_ALIGNMENT)

    if not stream_equal:
        if _is_subsequence(output_stream, candidate_stream):
            reasons.add(REASON_LEXICAL_LOSS)
        elif _is_subsequence(candidate_stream, output_stream):
            reasons.add(REASON_LEXICAL_DUPLICATION)
        else:
            reasons.add(REASON_LEXICAL_DIVERGENCE)

    internal_offsets: set[int] = set()
    component_spans: list[tuple[int, int, int]] = []
    cumulative = 0
    for index, stream in enumerate(component_streams):
        start = cumulative
        cumulative += len(stream)
        component_spans.append((start, cumulative, index))
        if stream and 0 < cumulative < len(candidate_stream) and stream_equal:
            if source_positions[cumulative] == source_positions[cumulative - 1] + 1:
                internal_offsets.add(cumulative)
    if internal_offsets:
        reasons.add(REASON_INTERNAL_BOUNDARY)

    tiny_fragments = 0
    if stream_equal:
        for start, end, _ in component_spans:
            if end - start != 1:
                continue
            if start in internal_offsets or end in internal_offsets:
                tiny_fragments += 1
    if tiny_fragments:
        reasons.add(REASON_TINY_FRAGMENT)

    maximum_per_run = 0
    if stream_equal and candidate_stream:
        run_starts = [0]
        for offset in range(1, len(source_positions)):
            if source_positions[offset] != source_positions[offset - 1] + 1:
                run_starts.append(offset)
        run_bounds = tuple(zip(run_starts, (*run_starts[1:], len(candidate_stream))))
        for run_start, run_end in run_bounds:
            intersections = sum(
                start < run_end and end > run_start
                for start, end, _ in component_spans
                if end > start
            )
            maximum_per_run = max(maximum_per_run, intersections)
    if maximum_per_run >= 3:
        reasons.add(REASON_FRAGMENTATION)

    repeated_internal = 0
    if stream_equal:
        previous_nonempty: tuple[int, int] | None = None
        for start, end, index in component_spans:
            if end == start:
                continue
            if previous_nonempty is not None:
                previous_end, previous_index = previous_nonempty
                if (
                    previous_end == start
                    and start in internal_offsets
                    and components[previous_index].label == components[index].label
                ):
                    repeated_internal += 1
            previous_nonempty = (end, index)
    if repeated_internal:
        reasons.add(REASON_REPEATED_LABEL)

    ordered_reasons = tuple(reason for reason in REASON_ORDER if reason in reasons)
    return StructuralSignals(
        raw_ordered_substrings=raw_ordered,
        lexical_numeric_stream_equal=stream_equal,
        internal_boundary_count=len(internal_offsets),
        internal_single_codepoint_fragment_count=tiny_fragments,
        maximum_components_per_lexical_run=maximum_per_run,
        adjacent_repeated_label_internal_boundary_count=repeated_internal,
        candidate_lexical_numeric_codepoints=len(candidate_stream),
        output_lexical_numeric_codepoints=len(output_stream),
        reason_codes=ordered_reasons,
    )


def decide_component_readiness(
    *,
    parser_applicability: str,
    technical_status: str,
    candidate: str,
    components: tuple[LibpostalComponent, ...] | None,
    standard_occurrence_count: int,
    native_occurrence_count: int,
) -> ReadinessDecision:
    """Apply the frozen prospective readiness rule to one candidate.

    Representation provenance is retained for validation stratification but is
    never itself an abstention trigger.  The discovery sample does not establish
    that NATIVE provenance or any script causes parser error.
    """
    if parser_applicability != PARSER_ELIGIBLE_COUNTRY:
        reason = _ELIGIBILITY_REASON.get(parser_applicability)
        if reason is None or technical_status != NOT_ATTEMPTED_NOT_ELIGIBLE:
            raise Stage07ReadinessError("applicability/technical status mismatch")
        if components is not None:
            raise Stage07ReadinessError("not-attempted row cannot contain components")
        return ReadinessDecision(NOT_ASSESSED, (reason,), None)

    if technical_status == PARSED_EMPTY:
        if components != ():
            raise Stage07ReadinessError("PARSED_EMPTY requires exact empty components")
        return ReadinessDecision(COMPONENTS_ABSTAIN, (REASON_PARSED_EMPTY,), None)
    if technical_status != PARSED_NONEMPTY or components is None or not components:
        raise Stage07ReadinessError("eligible v2 row must be a successful parse")
    if standard_occurrence_count < 0 or native_occurrence_count < 0:
        raise Stage07ReadinessError("occurrence counts cannot be negative")
    if standard_occurrence_count + native_occurrence_count < 1:
        raise Stage07ReadinessError("candidate has no representation provenance")

    signals = structural_signals(candidate, components)
    ordered_reasons = signals.reason_codes
    status = COMPONENTS_ABSTAIN if ordered_reasons else COMPONENTS_READY
    return ReadinessDecision(status, ordered_reasons, signals)


__all__ = [
    "COMPONENTS_ABSTAIN",
    "COMPONENTS_READY",
    "NOT_ASSESSED",
    "NOT_ATTEMPTED_NOT_ELIGIBLE",
    "READINESS_RULE_VERSION",
    "READINESS_STATUSES",
    "REASON_ORDER",
    "ReadinessDecision",
    "Stage07ReadinessError",
    "STRUCTURAL_ABSTENTION_REASONS",
    "StructuralSignals",
    "TECHNICAL_STATUSES",
    "decide_component_readiness",
    "structural_signals",
]

"""Bounded occurrence-local Q1–Q6 generation; never geocoding or correction."""

from __future__ import annotations

import re
import struct
import tempfile
import unicodedata
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from contextlib import nullcontext
from functools import cached_property
from pathlib import Path
from typing import Any, Protocol

from . import s10_query_contract as c
from . import s10_query_transliteration as transliteration
from .s10_query_evidence import FieldPolicy
from .s10_query_operations import Progress

ComponentReader = Callable[[bool], Iterator[Mapping[str, Any]]]
UNIT = re.compile(r"(?:unit|suite|apt|apartment) [0-9]+[a-z]?")
LEVEL = re.compile(r"(?:floor|level) [0-9]+")


class TransformRuntime(Protocol):
    asset_binding: bytes

    def transform(self, script: str, value: str) -> str: ...


@dataclass(frozen=True)
class QueryContext:
    upstream_identity: bytes
    input_identity: bytes
    science_identity: bytes
    source_id: bytes
    role: str
    candidate_id: bytes
    text: str
    lines: tuple[str, str, str, str]
    line_mask: str
    line_count: int
    parse_status: str
    component_count: int
    components: ComponentReader
    source_lower_geography: tuple[str, str, str, str]
    source_clean_postcode: str
    source_clean_locality: str
    fields: FieldPolicy
    certificates: Mapping[str, Mapping[str, Any]]
    spool_root: Path
    progress: Progress | None = None

    @cached_property
    def identifier(self) -> bytes:
        return c.context_id(self.upstream_identity, self.source_id, self.role)

    def validate(self) -> None:
        c.require(
            self.role in c.ROLES and len(self.candidate_id) == 32 and bool(self.text),
            "STAGE10_CONTEXT_INVALID",
        )
        c.require(
            len(self.lines) == 4
            and all(isinstance(s, str) for s in self.lines)
            and " ".join(s for s in self.lines if s) == self.text
            and self.line_count == sum(bool(s) for s in self.lines)
            and self.line_mask == "".join("1" if s else "0" for s in self.lines),
            "STAGE10_SOURCE_BOUNDARY_LINEAGE_INVALID",
        )
        c.require(
            set(self.certificates) == set(c.SELECTORS), "STAGE10_SELECTOR_SET_INVALID"
        )
        for name, certificate in self.certificates.items():
            c.require(
                certificate["selector_id"] == name
                and certificate["selected_count"] >= 0
                and len(certificate["selected_stream_sha256"]) == 32,
                "STAGE10_SELECTOR_CERTIFICATE_INVALID",
            )


@dataclass(frozen=True)
class FamilyResult:
    intent: Mapping[str, Any] | None
    reasons: tuple[str, ...] = ()
    transformations: tuple[Mapping[str, Any], ...] = ()
    fields: tuple[Mapping[str, Any], ...] = ()
    removed: tuple[Mapping[str, Any], ...] = ()


def step(
    ordinal: int, transform: str, before: Any, after: Any, asset: bytes | None = None
) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "transform_id": transform,
        "transform_asset_binding": asset,
        "input_value_sha256": c.identity("stage10-transform-value:v1", before),
        "output_value_sha256": c.identity("stage10-transform-value:v1", after),
    }


def _line_intervals(lines: Sequence[str]) -> list[tuple[int, int, int, str]]:
    result = []
    offset = 0
    for slot, line in enumerate(lines, 1):
        if line:
            result.append((slot, offset, offset + len(line), line))
            offset += len(line) + 1
    return result


def _source_veto(line: str, geography: Sequence[str]) -> bool:
    for value in geography:
        if not value:
            continue
        start = 0
        while (start := line.find(value, start)) >= 0:
            end = start + len(value)
            left = start == 0 or unicodedata.category(line[start - 1])[0] not in "LN"
            right = end == len(line) or unicodedata.category(line[end])[0] not in "LN"
            if left and right:
                return True
            start += 1
    return False


def strip_units(context: QueryContext) -> FamilyResult:
    """Full sequence alignment spills fixed-size offsets, never all components."""
    targets = {
        (start, end): (slot, line, "UNIT" if UNIT.fullmatch(line) else "LEVEL")
        for slot, start, end, line in _line_intervals(context.lines)
        if UNIT.fullmatch(line) or LEVEL.fullmatch(line)
    }
    if not targets:
        return FamilyResult(None, ("FAMILY_INELIGIBLE",))
    if context.parse_status != "PARSED_NONEMPTY" or context.component_count == 0:
        return FamilyResult(None, ("PARSER_EVIDENCE_UNUSABLE",))
    matched: dict[int, dict[str, Any]] = {}
    with tempfile.TemporaryFile(mode="w+b", dir=context.spool_root) as offsets:
        cursor = 0
        count = 0
        for component in context.components(False):
            ordinal = component["stage08_component_ordinal"]
            c.require(ordinal == count, "STAGE10_COMPONENT_ORDINAL_INVALID")
            value = component["stage08_raw_libpostal_value"]
            if not value:
                return FamilyResult(None, ("PARSER_EVIDENCE_UNUSABLE",))
            start = context.text.find(value, cursor)
            if start < 0:
                return FamilyResult(None, ("UNIT_ALIGNMENT_AMBIGUOUS",))
            end = start + len(value)
            offsets.write(struct.pack(">QQQ", ordinal, start, end))
            for (line_start, line_end), (slot, line, category) in targets.items():
                if start < line_end and end > line_start:
                    if (start, end) != (line_start, line_end) or component[
                        "stage08_raw_libpostal_label"
                    ] != category.lower():
                        return FamilyResult(None, ("PARSER_EVIDENCE_UNUSABLE",))
                    c.require(slot not in matched, "STAGE10_UNIT_INTERVAL_OVERLAP")
                    matched[slot] = {
                        "source_slot": slot,
                        "start_codepoint": start,
                        "end_codepoint_exclusive": end,
                        "category": category,
                        "grammar_id": "stage10_whole_line_" + category.lower() + "_v1",
                        "stage08_component_ordinal": ordinal,
                    }
            cursor = end
            count += 1
        c.require(count == context.component_count, "STAGE10_COMPONENT_COUNT_INVALID")
        if len(matched) != len(targets):
            return FamilyResult(None, ("PARSER_EVIDENCE_UNUSABLE",))
        cursor = len(context.text)
        count = context.component_count
        for component in context.components(True):
            count -= 1
            c.require(
                component["stage08_component_ordinal"] == count,
                "STAGE10_REVERSE_COMPONENT_ORDINAL_INVALID",
            )
            value = component["stage08_raw_libpostal_value"]
            start = context.text.rfind(value, 0, cursor)
            if start < 0:
                return FamilyResult(None, ("UNIT_ALIGNMENT_AMBIGUOUS",))
            end = start + len(value)
            offsets.seek(count * 24)
            if offsets.read(24) != struct.pack(">QQQ", count, start, end):
                return FamilyResult(None, ("UNIT_ALIGNMENT_AMBIGUOUS",))
            cursor = start
        c.require(count == 0, "STAGE10_REVERSE_COMPONENT_COUNT_INVALID")
    if any(
        _source_veto(line, context.source_lower_geography)
        for _, line, _ in targets.values()
    ):
        return FamilyResult(None, ("UNIT_SOURCE_FIELD_CONFLICT",))
    remaining = tuple(
        "" if slot in matched else line for slot, line in enumerate(context.lines, 1)
    )
    text = " ".join(line for line in remaining if line)
    transformations = (
        step(0, "WHOLE_LINE_UNIT_LEVEL_REMOVE_V1", context.lines, remaining),
        step(1, "SOURCE_SPACE_JOIN_V1", remaining, text),
    )
    if not text:
        return FamilyResult(
            None, ("EMPTY_RESULT_AFTER_TRANSFORMATION",), transformations
        )
    if not any(
        any(unicodedata.category(ch).startswith("L") for ch in line)
        and any("0" <= ch <= "9" for ch in line)
        for line in remaining
        if line
    ):
        return FamilyResult(None, ("FAMILY_INELIGIBLE",), transformations)
    assert context.fields.country is not None
    return FamilyResult(
        c.full_intent(text, context.fields.country),
        transformations=transformations,
        removed=tuple(matched[slot] for slot in sorted(matched)),
    )


def _structured(context: QueryContext) -> FamilyResult:
    policy = context.fields
    assert policy.country is not None
    decisions = []
    for field, value, reasons in (
        ("address", context.text, ()),
        ("postalcode", policy.postcode, policy.postcode_reasons),
        ("locality", policy.locality, policy.locality_reasons),
        ("region", None, ("ADMIN_LEVEL_NOT_ESTABLISHED",)),
        ("country", None, ()),
        ("boundary_country", policy.country, ()),
    ):
        # Field-slot policy, not a classification of source values or parser
        # tokens. An omitted geographic slot cannot be filled by parser-only
        # evidence, including when a source/reference gate rejected its source
        # value. Retain that gate's reason separately. Never label an included
        # source field parser-only, or enumerate repeated parser components.
        if value is None and field in ("postalcode", "locality", "region", "country"):
            reasons = (*reasons, "PARSER_ONLY_FIELD_EXCLUDED")
        decisions.append(
            {
                "field": field,
                "disposition": "INCLUDE" if value is not None else "OMIT",
                "reason_codes": list(reasons),
            }
        )
    if policy.postcode is None and policy.locality is None:
        return FamilyResult(
            None, ("INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE",), fields=tuple(decisions)
        )
    intent = c.full_intent(context.text, policy.country)
    intent.update(
        endpoint="/v1/search/structured",
        search_mode="STRUCTURED",
        text=None,
        address=context.text,
        postalcode=policy.postcode,
        locality=policy.locality,
    )
    trace = step(
        0,
        "SOURCE_STRUCTURED_FIELDS_V1",
        (
            context.text,
            context.source_clean_postcode,
            context.source_clean_locality,
            policy.country,
        ),
        c.intent_values(intent),
    )
    return FamilyResult(intent, transformations=(trace,), fields=tuple(decisions))


def _transliterated(context: QueryContext, runtime: TransformRuntime) -> FamilyResult:
    script = transliteration.eligible_script(context.text, check_marks=False)
    if script is None:
        return FamilyResult(None, ("UNSUPPORTED_SCRIPT_TRANSLITERATION",))
    normalized = unicodedata.normalize("NFC", context.text)
    traces = [step(0, "NFC_U16_V1", context.text, normalized, runtime.asset_binding)]
    if transliteration.eligible_script(normalized, check_marks=True) != script:
        return FamilyResult(
            None, ("UNSUPPORTED_SCRIPT_TRANSLITERATION",), tuple(traces)
        )
    with (
        context.progress.measure("icu_transform") if context.progress else nullcontext()
    ):
        converted = runtime.transform(script, normalized)
    traces.append(
        step(
            1,
            "ICU_GREK_LATN_77_1" if script == "Greek" else "ICU_CYRL_LATN_77_1",
            normalized,
            converted,
            runtime.asset_binding,
        )
    )
    output = unicodedata.normalize("NFC", converted)
    traces.append(step(2, "NFC_U16_V1", converted, output, runtime.asset_binding))
    if not output:
        return FamilyResult(None, ("EMPTY_RESULT_AFTER_TRANSFORMATION",), tuple(traces))
    # Unchanged output is eligible convergence even if the original target script
    # remains. The frozen gate expressly orders unchanged before residual script.
    if output != context.text and not transliteration.output_supported(output):
        return FamilyResult(
            None, ("TRANSLITERATION_UNSUPPORTED_OUTPUT",), tuple(traces)
        )
    assert context.fields.country is not None
    return FamilyResult(
        c.full_intent(output, context.fields.country), transformations=tuple(traces)
    )


def _family(
    context: QueryContext, family: str, runtime: TransformRuntime
) -> FamilyResult:
    if (family == "Q1" and context.role != "STANDARD") or (
        family in ("Q2", "Q6") and context.role != "NATIVE"
    ):
        return FamilyResult(None, ("REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE",))
    country = context.fields.country
    if country is None:
        fields = (
            tuple(
                {"field": field, "disposition": "NOT_APPLICABLE", "reason_codes": []}
                for field in (
                    "address",
                    "postalcode",
                    "locality",
                    "region",
                    "country",
                    "boundary_country",
                )
            )
            if family == "Q4"
            else ()
        )
        return FamilyResult(None, ("COUNTRY_CONTEXT_UNAVAILABLE",), fields=fields)
    if family in ("Q1", "Q2"):
        return FamilyResult(
            c.full_intent(context.text, country),
            transformations=(
                step(0, "EXACT_CANDIDATE_V1", context.text, context.text),
            ),
        )
    if family == "Q3":
        text = "\n".join(line for line in context.lines if line)
        return FamilyResult(
            c.full_intent(text, country),
            transformations=(step(0, "SOURCE_LF_JOIN_V1", context.lines, text),),
        )
    if family == "Q4":
        return _structured(context)
    if family == "Q5":
        with (
            context.progress.measure("q5_alignment")
            if context.progress
            else nullcontext()
        ):
            return strip_units(context)
    c.require(family == "Q6", "STAGE10_FAMILY_INVALID")
    return _transliterated(context, runtime)


def generate(
    context: QueryContext, runtime: TransformRuntime
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    context.validate()
    common = {
        "query_context_id": context.identifier,
        "stable_source_row_id_v1": context.source_id,
        "stage08_representation": context.role,
        "stage06_exact_candidate_id": context.candidate_id,
    }
    hypotheses: dict[bytes, dict[str, Any]] = {}
    decisions = []
    for family in c.FAMILIES:
        with (
            context.progress.measure(family)
            if context.progress is not None
            else nullcontext()
        ):
            result = _family(context, family, runtime)
        reasons = list(result.reasons)
        hypothesis_id = None
        membership = "NONE"
        if result.intent is not None:
            fingerprint = c.intent_fingerprint(result.intent)
            hypothesis_id = c.identity(
                "stage10-hypothesis:v1",
                context.input_identity,
                context.science_identity,
                context.identifier,
                fingerprint,
            )
            if fingerprint in hypotheses:
                c.require(
                    c.intent_values(hypotheses[fingerprint]["intent"])
                    == c.intent_values(result.intent),
                    "STAGE10_INTENT_HASH_COLLISION",
                )
                membership = "CONVERGENT_MEMBER"
                reasons.append("EXACT_SEMANTIC_DUPLICATE")
            else:
                membership = "FIRST_MEMBER"
                hypotheses[fingerprint] = {
                    **common,
                    "hypothesis_id": hypothesis_id,
                    "representation_fingerprint": fingerprint,
                    "intent": dict(result.intent),
                    "generation_rank": len(hypotheses) + 1,
                    "selection_status": c.MODE,
                }
        selectors = {
            "CANDIDATE_V1",
            "OCCURRENCE_V1",
            "SOURCE_CONTEXT_V1",
            "SOURCE_REFERENCE_V1",
            "REFERENCE_WITNESSES_V1",
        }
        if family in ("Q3", "Q5"):
            selectors.add("SOURCE_LINES_V1")
        if family == "Q5":
            selectors.add("PARSER_COMPONENTS_V1")
        c.require(
            all(reason in c.REASONS for reason in reasons), "STAGE10_REASON_INVALID"
        )
        reasons = sorted(set(reasons), key=c.REASONS.index)
        decisions.append(
            {
                **common,
                "family_decision_id": c.identity(
                    "stage10-family-decision:v1",
                    context.input_identity,
                    context.science_identity,
                    context.identifier,
                    family,
                ),
                "family": family,
                "eligibility_state": "ELIGIBLE"
                if result.intent is not None
                else "INELIGIBLE",
                "membership_state": membership,
                "hypothesis_id": hypothesis_id,
                "primary_reason": reasons[0] if reasons else None,
                "reason_codes": reasons,
                "eligibility_rule_id": f"stage10_q{family[1:]}_eligibility_v1",
                "lineage": [
                    dict(context.certificates[name])
                    for name in c.SELECTORS
                    if name in selectors
                ],
                "transformations": list(result.transformations),
                "field_decisions": list(result.fields),
                "removed_lines": list(result.removed),
            }
        )
    c.require(
        len(hypotheses) <= c.CONTEXT_CEILING
        and len(hypotheses) <= c.ROLE_CEILINGS[context.role],
        "STAGE10_ENGINEERING_CEILING_VIOLATION",
    )
    c.require(len(decisions) == 6, "STAGE10_FAMILY_DECISION_CARDINALITY")
    return [hypotheses[key] for key in sorted(hypotheses)], decisions

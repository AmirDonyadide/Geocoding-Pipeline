from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from ..phase02.schema import exact_schema_matches
from .constants import (
    ADDRESS_FIELDS,
    PARSE_STATUSES,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_2,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V5,
)
from .development_pattern_profiler import (
    _artifact_state,
    _pattern,
    _pattern_tokens,
    _reject_locked_paths,
    _segment_value,
)
from .pilot_runner import read_identity_set
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .targeted_experiment_review import (
    REVIEWER_IDS,
    targeted_review_context_schema,
    targeted_review_label_schema,
)
from .text import normalize_derived_text
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)


PROFILER_VERSION: Final = "phase03_development_hypothesis_intersection_profiler_v1"
REPORT_SCHEMA_VERSION: Final = "phase03_development_hypothesis_intersection_profile_v1"
EXPECTED_DEVELOPMENT_IDENTITY_ARTIFACT_SHA256: Final = (
    "cab12eb1c1c2f61b8bbc5b53dff604e7569233518e5fb3c88467d848e648d71a"
)
EXPECTED_DEVELOPMENT_PAYLOAD_SHA256: Final = (
    "dc78fd5c814739008a9ce24e91c66bf7c1121898b06ce2dfc53b0620b07a3cb1"
)
EXPECTED_BASELINE_CONFIGURATION: Final = (
    "25962a126cd5d30c13607bd564aa250e91096e6961745670772a1ce31b76ac4d"
)
EXPECTED_BASELINE_CORE_SHA256: Final = (
    "644b22865486c27ecb7bd15297fc131a7fa282758fb245bc8c6e885dacfecaf5"
)
EXPECTED_BASELINE_EVIDENCE_SHA256: Final = (
    "0f7ddae89755f2d8c6d2973e09be4670e851fb58867d8233998d10aa23443baa"
)
EXPECTED_CANDIDATE_CONFIGURATION: Final = (
    "89370fddf5f9dae8f381f62344df4da96f0b3dc34627cff23a8068555b909a73"
)
EXPECTED_CANDIDATE_CORE_SHA256: Final = (
    "28efa83eed2870c681891e9f0ecc526c8b5abdf3c6305dd63ef3f0ff2811f10f"
)
EXPECTED_CANDIDATE_EVIDENCE_SHA256: Final = (
    "ca6be7107a0dc72903542030a3b0846fe9e15ceee4bf2c9352682b4817f37b16"
)
ROLE_RULES: Final = {
    "UNIT_EXPLICIT_SEGMENT_V3": "UNIT",
    "FLOOR_EXPLICIT_SEGMENT_V3": "FLOOR",
    "BUILDING_EXPLICIT_SEGMENT_V3": "BUILDING",
    "ORGANIZATION_LEGAL_FORM_V3": "ORGANIZATION",
}
STREET_RULE: Final = "STREET_EXPLICIT_DESIGNATOR_V3"
TARGET_COMPONENTS: Final = frozenset({"STREET", "HOUSE_NUMBER"})
ROLE_COMPONENTS: Final = frozenset(ROLE_RULES.values())
_CANDIDATE_KINDS: Final = frozenset(
    {
        "SELECTED_NONTRIVIAL_COMPONENT",
        "UNSELECTED_CANDIDATE",
        "COMPETING_CANDIDATE",
        "CONFLICTING_EVIDENCE",
    }
)
_HOUSELIKE_LINE_TOKENS: Final = frozenset(
    {"HOUSELIKE_NUM", "LETTER_SUFFIX_NUMBER", "SLASH_NUMBER", "HYPHEN_NUMBER"}
)
_NUMERIC_PATTERN_TOKENS: Final = frozenset(
    {
        "HOUSELIKE_NUM",
        "NUM",
        "ALNUM",
        "LETTER_SUFFIX_NUMBER",
        "SLASH_NUMBER",
        "HYPHEN_NUMBER",
    }
)
_REGISTERED_OVERLAP_PAIRS: Final = frozenset(
    {frozenset(("UNIT", "HOUSE_NUMBER")), frozenset(("BUILDING", "ORGANIZATION"))}
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_YEAR = re.compile(r"[0-9]{4}")
_PAIR = re.compile(r"([0-9]{1,4})([/\-])([0-9]{1,4})")


@dataclass(frozen=True, slots=True)
class ProfileArtifacts:
    report_json: Path
    intersections_csv: Path
    interpretation_markdown: Path
    profile_fingerprint: str
    rows: int


@dataclass(frozen=True, slots=True)
class RuleEvidenceSemantics:
    confidence: str
    selection_priority: int


@dataclass(frozen=True, slots=True)
class _EvidenceGroup:
    stable_id: bytes
    evidence_id: int
    evidence_kind: str
    component: str | None
    representation: str | None
    candidate_value: str | None
    selected: bool
    confidence: str | None
    rule_id: str | None
    conflict_flag: str | None
    diagnostic_flag: str | None
    spans: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True, slots=True)
class _H3Relationship:
    stable_id: bytes
    street_evidence_id: int
    street_field: str
    number_field: str
    orientation: str
    reasons: frozenset[str]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _population_digest(name: str, identities: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    domain = f"safe_geocoding_pipeline:{PROFILER_VERSION}:{name}\0".encode()
    digest.update(domain)
    ordered = sorted(set(identities))
    for identity in ordered:
        digest.update(identity)
    digest.update(len(ordered).to_bytes(8, "big"))
    return digest.hexdigest()


def _group_evidence(rows: Sequence[Mapping[str, Any]]) -> tuple[_EvidenceGroup, ...]:
    grouped: dict[tuple[bytes, int], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[
            (bytes(row["stable_source_row_id_v1"]), int(row["evidence_id"]))
        ].append(row)
    result: list[_EvidenceGroup] = []
    for (stable_id, evidence_id), spans in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        first = spans[0]
        result.append(
            _EvidenceGroup(
                stable_id=stable_id,
                evidence_id=evidence_id,
                evidence_kind=str(first["evidence_kind"]),
                component=cast(str | None, first["component"]),
                representation=cast(str | None, first["representation"]),
                candidate_value=cast(str | None, first["candidate_value"]),
                selected=bool(first["selected"]),
                confidence=cast(str | None, first["confidence"]),
                rule_id=cast(str | None, first["rule_id"]),
                conflict_flag=cast(str | None, first["conflict_flag"]),
                diagnostic_flag=cast(str | None, first["diagnostic_flag"]),
                spans=tuple(
                    sorted(
                        (
                            str(span["source_field"]),
                            int(span["start_character"]),
                            int(span["end_character_exclusive"]),
                        )
                        for span in spans
                    )
                ),
            )
        )
    return tuple(result)


def _spans_overlap(left: _EvidenceGroup, right: _EvidenceGroup) -> bool:
    return any(
        left_field == right_field and left_start < right_end and right_start < left_end
        for left_field, left_start, left_end in left.spans
        for right_field, right_start, right_end in right.spans
    )


def _candidate(group: _EvidenceGroup) -> bool:
    return group.evidence_kind in _CANDIDATE_KINDS and group.component is not None


def _identity_order_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_development_hypothesis_profile_order_v1\0"
    )
    for ordinal, row in enumerate(rows, start=1):
        digest.update(ordinal.to_bytes(8, "big"))
        digest.update(bytes(row["stable_source_row_id_v1"]))
    digest.update(len(rows).to_bytes(8, "big"))
    return digest.hexdigest()


def _read_parsers(
    *,
    payload_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    candidate_core_path: Path,
    candidate_evidence_path: Path,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    payload_file = pq.ParquetFile(
        payload_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_schema_matches(payload_file.schema_arrow):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_PAYLOAD_SCHEMA_MISMATCH")
    files = [
        pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        for path in (
            baseline_core_path,
            baseline_evidence_path,
            candidate_core_path,
            candidate_evidence_path,
        )
    ]
    if not exact_core_schema_matches(
        files[0].schema_arrow
    ) or not exact_core_schema_matches(files[2].schema_arrow):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_CORE_SCHEMA_MISMATCH")
    if not exact_evidence_schema_matches(
        files[1].schema_arrow
    ) or not exact_evidence_schema_matches(files[3].schema_arrow):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_EVIDENCE_SCHEMA_MISMATCH")
    return cast(
        tuple[
            list[dict[str, Any]],
            list[dict[str, Any]],
            list[dict[str, Any]],
            list[dict[str, Any]],
            list[dict[str, Any]],
        ],
        (
            payload_file.read(use_threads=False).to_pylist(),
            files[0].read(use_threads=False).to_pylist(),
            files[1].read(use_threads=False).to_pylist(),
            files[2].read(use_threads=False).to_pylist(),
            files[3].read(use_threads=False).to_pylist(),
        ),
    )


def _validate_parser_rows(
    *,
    core_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    payload_by_id: Mapping[bytes, Mapping[str, Any]],
    expected_parser: str,
    expected_registry: str,
    expected_configuration: str,
) -> None:
    validate_core_rows(core_rows)
    raw_by_id = {
        identity: {
            field: str(row[field])
            for field in (
                *ADDRESS_FIELDS,
                "postcode",
                "city",
                "region_in_country",
                "country_iso_code",
            )
        }
        for identity, row in payload_by_id.items()
    }
    validate_evidence_rows(evidence_rows, raw_values_by_id=raw_by_id)
    validate_core_evidence_relationship(core_rows, evidence_rows)
    if {str(row["parser_version"]) for row in core_rows} != {expected_parser}:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_PARSER_VERSION_MISMATCH")
    if {str(row["rule_registry_version"]) for row in core_rows} != {expected_registry}:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_REGISTRY_VERSION_MISMATCH")
    configurations = {
        bytes(row["configuration_fingerprint"]).hex() for row in core_rows
    }
    if configurations != {expected_configuration}:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_CONFIGURATION_MISMATCH")


def _h1_profile(
    *,
    core_by_id: Mapping[bytes, Mapping[str, Any]],
    groups_by_id: Mapping[bytes, Sequence[_EvidenceGroup]],
) -> tuple[set[bytes], dict[str, JsonValue]]:
    population = {
        identity
        for identity, row in core_by_id.items()
        if "COMPONENT_SPAN_OVERLAP_CONFLICT" in row["address_conflict_flags"]
    }
    pair_rows: dict[str, set[bytes]] = defaultdict(set)
    pair_memberships: Counter[str] = Counter()
    involved_groups: set[tuple[bytes, int]] = set()
    rules: dict[str, set[bytes]] = defaultdict(set)
    street_house: set[bytes] = set()
    selected_affected: set[bytes] = set()
    residual_role: set[bytes] = set()
    for identity in population:
        candidates = [
            group
            for group in groups_by_id.get(identity, ())
            if _candidate(group) and group.confidence not in {None, "LOW"}
        ]
        matched = False
        for index, left in enumerate(candidates):
            for right in candidates[index + 1 :]:
                components = frozenset((str(left.component), str(right.component)))
                if (
                    left.component == right.component
                    or components in _REGISTERED_OVERLAP_PAIRS
                    or not _spans_overlap(left, right)
                ):
                    continue
                matched = True
                label = "+".join(sorted(components))
                pair_rows[label].add(identity)
                pair_memberships[label] += 1
                involved_groups.update(
                    ((identity, left.evidence_id), (identity, right.evidence_id))
                )
                for rule_id in (left.rule_id, right.rule_id):
                    if rule_id is not None:
                        rules[rule_id].add(identity)
                if components == frozenset(("STREET", "HOUSE_NUMBER")):
                    street_house.add(identity)
                if left.selected or right.selected:
                    selected_affected.add(identity)
        if not matched:
            raise ValueError("H1_FLAGGED_ROW_WITHOUT_RECONSTRUCTED_OVERLAP")
        role_groups = [
            group for group in candidates if group.component in ROLE_COMPONENTS
        ]
        residual_groups = [
            group
            for group in groups_by_id.get(identity, ())
            if group.evidence_kind == "UNASSIGNED_MATERIAL_CONTENT"
        ]
        if any(
            _spans_overlap(role, residual)
            for role in role_groups
            for residual in residual_groups
        ):
            residual_role.add(identity)
    status = Counter(
        str(core_by_id[item]["address_parse_status"]) for item in population
    )
    return population, {
        "unique_rows": len(population),
        "population_digest": _population_digest("H1", population),
        "relevant_evidence_group_memberships": len(involved_groups),
        "overlap_component_pairs": {
            key: {
                "unique_rows": len(pair_rows[key]),
                "pair_memberships": pair_memberships[key],
            }
            for key in sorted(pair_rows)
        },
        "street_house_span_overlap_rows": len(street_house),
        "residual_role_span_overlap_rows": len(residual_role),
        "selected_value_affected_rows": len(selected_affected),
        "parser_status_distribution": {
            value: status[value] for value in PARSE_STATUSES
        },
        "rule_evidence_categories": {
            rule_id: len(identities) for rule_id, identities in sorted(rules.items())
        },
    }


def _priority_relation(role_priority: int, target_priority: int) -> str:
    if role_priority < target_priority:
        return "ROLE_STRONGER_PRIORITY"
    if role_priority == target_priority:
        return "EQUAL_PRIORITY"
    return "ROLE_WEAKER_PRIORITY"


def _confidence_relation(role: str, target: str) -> str:
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    if order[role] < order[target]:
        return "ROLE_HIGHER_CONFIDENCE"
    if order[role] == order[target]:
        return "EQUAL_CONFIDENCE"
    return "ROLE_LOWER_CONFIDENCE"


def _h2_profile(
    *,
    payload_by_id: Mapping[bytes, Mapping[str, Any]],
    groups_by_id: Mapping[bytes, Sequence[_EvidenceGroup]],
    rule_semantics: Mapping[str, RuleEvidenceSemantics],
) -> tuple[set[bytes], dict[str, JsonValue]]:
    population: set[bytes] = set()
    role_rows: dict[str, set[bytes]] = defaultdict(set)
    target_selected: set[bytes] = set()
    priority_rows: dict[str, set[bytes]] = defaultdict(set)
    confidence_rows: dict[str, set[bytes]] = defaultdict(set)
    overlap_memberships = 0
    multiple_roles: set[bytes] = set()
    hyphen_rows: set[bytes] = set()
    for identity, groups in groups_by_id.items():
        roles = [group for group in groups if group.rule_id in ROLE_RULES]
        targets = [
            group
            for group in groups
            if _candidate(group) and group.component in TARGET_COMPONENTS
        ]
        seen_role_types: set[str] = set()
        for role in roles:
            for target in targets:
                if not _spans_overlap(role, target):
                    continue
                if role.rule_id is None or target.rule_id is None:
                    raise ValueError("H2_RULE_ID_MISSING")
                try:
                    role_semantics = rule_semantics[role.rule_id]
                    target_semantics = rule_semantics[target.rule_id]
                except KeyError as error:
                    raise ValueError("H2_RULE_SEMANTICS_MISSING") from error
                population.add(identity)
                role_type = ROLE_RULES[role.rule_id]
                role_rows[role_type].add(identity)
                seen_role_types.add(role_type)
                overlap_memberships += 1
                priority_rows[
                    _priority_relation(
                        role_semantics.selection_priority,
                        target_semantics.selection_priority,
                    )
                ].add(identity)
                confidence_rows[
                    _confidence_relation(
                        role_semantics.confidence, target_semantics.confidence
                    )
                ].add(identity)
                if target.selected:
                    target_selected.add(identity)
        if len(seen_role_types) > 1:
            multiple_roles.add(identity)
        for group in groups:
            if group.evidence_kind != "UNASSIGNED_MATERIAL_CONTENT":
                continue
            value = _segment_value(payload_by_id[identity], group.spans)
            if _pattern(value) == "HYPHEN_NUMBER WORDS":
                hyphen_rows.add(identity)
    return population, {
        "unique_rows": len(population),
        "population_digest": _population_digest("H2", population),
        "overlap_relationship_memberships": overlap_memberships,
        "role_rows": {
            role: len(role_rows[role])
            for role in ("BUILDING", "UNIT", "FLOOR", "ORGANIZATION")
        },
        "multiple_competing_role_type_rows": len(multiple_roles),
        "selected_street_or_house_overlap_rows": len(target_selected),
        "priority_relation_rows": {
            key: len(value) for key, value in sorted(priority_rows.items())
        },
        "confidence_relation_rows": {
            key: len(value) for key, value in sorted(confidence_rows.items())
        },
        "hyphen_number_words": {
            "all_unassigned_pattern_rows": len(hyphen_rows),
            "intersection_with_h2_rows": len(hyphen_rows & population),
        },
    }


def _date_or_year_reason(value: str) -> str | None:
    normalized = normalize_derived_text(value)
    if normalized is None:
        return "ADJACENT_LINE_NOT_NUMERIC_ONLY"
    if _YEAR.fullmatch(normalized) and 1900 <= int(normalized) <= 2099:
        return "YEAR_STYLE"
    pair = _PAIR.fullmatch(normalized)
    if pair is not None:
        _, separator, right = pair.groups()
        if separator == "/" and len(right) == 2 and right.startswith("0"):
            return "DATE_STYLE"
    return None


def _representation_disagrees(
    payload: Mapping[str, Any], field_name: str, value: str
) -> bool:
    index = ADDRESS_FIELDS.index(field_name)
    counterpart = ADDRESS_FIELDS[(index + 4) if index < 4 else (index - 4)]
    counterpart_value = str(payload[counterpart])
    if not counterpart_value:
        return False
    normalized = normalize_derived_text(value)
    counterpart_normalized = normalize_derived_text(counterpart_value)
    return normalized != counterpart_normalized


def _h3_profile(
    *,
    payload_by_id: Mapping[bytes, Mapping[str, Any]],
    core_by_id: Mapping[bytes, Mapping[str, Any]],
    groups_by_id: Mapping[bytes, Sequence[_EvidenceGroup]],
    rule_semantics: Mapping[str, RuleEvidenceSemantics],
) -> tuple[set[bytes], dict[str, JsonValue]]:
    preliminary: list[tuple[bytes, _EvidenceGroup, str, str, set[str]]] = []
    for identity, groups in groups_by_id.items():
        explicit_streets = [group for group in groups if group.rule_id == STREET_RULE]
        role_groups = [group for group in groups if group.rule_id in ROLE_RULES]
        for street in explicit_streets:
            street_fields = {span[0] for span in street.spans}
            if len(street_fields) != 1:
                continue
            street_field = next(iter(street_fields))
            if street_field not in ADDRESS_FIELDS:
                continue
            field_index = ADDRESS_FIELDS.index(street_field)
            representation_start = 0 if field_index < 4 else 4
            line = field_index % 4
            for offset, orientation in (
                (-1, "NUMBER_THEN_STREET"),
                (1, "STREET_THEN_NUMBER"),
            ):
                adjacent_line = line + offset
                if not 0 <= adjacent_line < 4:
                    continue
                number_field = ADDRESS_FIELDS[representation_start + adjacent_line]
                value = str(payload_by_id[identity][number_field])
                if not value:
                    continue
                tokens = _pattern_tokens(value)
                numeric_count = sum(
                    token in _NUMERIC_PATTERN_TOKENS for token in tokens
                )
                if numeric_count == 0:
                    continue
                reasons: set[str] = set()
                if numeric_count != 1:
                    reasons.add("MULTIPLE_NUMBER_TOKENS")
                if len(tokens) != 1 or tokens[0] not in _HOUSELIKE_LINE_TOKENS:
                    reasons.add("ADJACENT_LINE_NOT_NUMERIC_ONLY")
                risk = _date_or_year_reason(value)
                if risk is not None:
                    reasons.add(risk)
                structured_postcode = normalize_derived_text(
                    str(payload_by_id[identity]["postcode"])
                )
                if (
                    structured_postcode is not None
                    and normalize_derived_text(value) == structured_postcode
                ):
                    reasons.add("POSTCODE_MATCH")
                if _representation_disagrees(
                    payload_by_id[identity], number_field, value
                ):
                    reasons.add("REPRESENTATION_DISAGREEMENT")
                street_semantics = rule_semantics[STREET_RULE]
                for role in role_groups:
                    if not any(span[0] == number_field for span in role.spans):
                        continue
                    assert role.rule_id is not None
                    role_meta = rule_semantics[role.rule_id]
                    if (
                        role_meta.selection_priority
                        < street_semantics.selection_priority
                    ):
                        reasons.add("STRONGER_COMPETING_ROLE")
                preliminary.append(
                    (identity, street, number_field, orientation, reasons)
                )

    structural_relationship_counts: Counter[tuple[bytes, int]] = Counter(
        (identity, street.evidence_id)
        for identity, street, _, _, reasons in preliminary
        if not reasons & {"MULTIPLE_NUMBER_TOKENS", "ADJACENT_LINE_NOT_NUMERIC_ONLY"}
    )
    relationships: list[_H3Relationship] = []
    for identity, street, number_field, orientation, reasons in preliminary:
        final_reasons = set(reasons)
        if structural_relationship_counts[(identity, street.evidence_id)] > 1:
            final_reasons.add("MULTIPLE_ADJACENT_NUMBER_LINES")
        relationships.append(
            _H3Relationship(
                stable_id=identity,
                street_evidence_id=street.evidence_id,
                street_field=street.spans[0][0],
                number_field=number_field,
                orientation=orientation,
                reasons=frozenset(final_reasons),
            )
        )
    eligible = {item.stable_id for item in relationships if not item.reasons}
    raw_ids = {item.stable_id for item in relationships}
    exclusion_rows: dict[str, set[bytes]] = defaultdict(set)
    exclusion_memberships: Counter[str] = Counter()
    orientations: Counter[str] = Counter()
    for item in relationships:
        if not item.reasons:
            orientations[item.orientation] += 1
        for reason in item.reasons:
            exclusion_rows[reason].add(item.stable_id)
            exclusion_memberships[reason] += 1
    existing_street = {
        identity
        for identity in eligible
        if core_by_id[identity]["street_clean"] is not None
        or core_by_id[identity]["street_native_clean"] is not None
    }
    existing_house = {
        identity
        for identity in eligible
        if core_by_id[identity]["house_number_clean"] is not None
        or core_by_id[identity]["house_number_native_clean"] is not None
    }
    status = Counter(str(core_by_id[item]["address_parse_status"]) for item in eligible)
    return eligible, {
        "raw_candidate_relationship_memberships": len(relationships),
        "raw_candidate_unique_rows": len(raw_ids),
        "unique_rows": len(eligible),
        "population_digest": _population_digest("H3", eligible),
        "orientation_relationship_counts": dict(sorted(orientations.items())),
        "exclusions": {
            reason: {
                "unique_rows": len(exclusion_rows[reason]),
                "relationship_memberships": exclusion_memberships[reason],
            }
            for reason in sorted(exclusion_rows)
        },
        "competing_role_exclusion_rows": len(exclusion_rows["STRONGER_COMPETING_ROLE"]),
        "multiple_number_exclusion_rows": len(
            exclusion_rows["MULTIPLE_NUMBER_TOKENS"]
            | exclusion_rows["MULTIPLE_ADJACENT_NUMBER_LINES"]
        ),
        "postcode_date_year_exclusion_rows": len(
            exclusion_rows["POSTCODE_MATCH"]
            | exclusion_rows["DATE_STYLE"]
            | exclusion_rows["YEAR_STYLE"]
        ),
        "representation_disagreement_exclusion_rows": len(
            exclusion_rows["REPRESENTATION_DISAGREEMENT"]
        ),
        "existing_street_selection_rows": len(existing_street),
        "existing_house_number_selection_rows": len(existing_house),
        "existing_street_and_house_selection_rows": len(
            existing_street & existing_house
        ),
        "parser_status_distribution": {
            value: status[value] for value in PARSE_STATUSES
        },
    }


def _review_coverage(
    *,
    context_path: Path | None,
    labels_path: Path | None,
    populations: Mapping[str, set[bytes]],
    expected_rows: int,
) -> dict[str, JsonValue]:
    if (context_path is None) != (labels_path is None):
        raise ValueError("TARGETED_REVIEW_COVERAGE_INPUTS_MUST_BE_PAIRED")
    if context_path is None or labels_path is None:
        return {
            "targeted_v3_1_r01": "NOT_SUPPLIED",
            "other_valid_reusable_development_labels": 0,
            "other_label_basis": "NO_OTHER_APPROVED_COMPLETED_LABEL_SET",
        }
    _reject_locked_paths((context_path, labels_path))
    context_file = pq.ParquetFile(
        context_path, page_checksum_verification=True, pre_buffer=True
    )
    labels_file = pq.ParquetFile(
        labels_path, page_checksum_verification=True, pre_buffer=True
    )
    if not context_file.schema_arrow.remove_metadata().equals(
        targeted_review_context_schema(), check_metadata=False
    ):
        raise ValueError("TARGETED_REVIEW_CONTEXT_SCHEMA_MISMATCH")
    if not labels_file.schema_arrow.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    ):
        raise ValueError("TARGETED_REVIEW_LABEL_SCHEMA_MISMATCH")
    context = context_file.read(
        columns=["stable_source_row_id_v1"], use_threads=False
    ).to_pylist()
    labels = labels_file.read(use_threads=False).to_pylist()
    if len(context) != expected_rows or len(labels) != expected_rows:
        raise ValueError("TARGETED_REVIEW_COVERAGE_COUNT_MISMATCH")
    if any(str(row["reviewer_id"]) != REVIEWER_IDS[0] for row in labels):
        raise ValueError("TARGETED_REVIEW_COVERAGE_REVIEWER_MISMATCH")
    experiment_iterations = {str(row["experiment_iteration"]) for row in labels}
    if len(experiment_iterations) != 1:
        raise ValueError("TARGETED_REVIEW_COVERAGE_ITERATION_MISMATCH")
    iteration = next(iter(experiment_iterations))
    identity_by_hash: dict[str, bytes] = {}
    for row in context:
        identity = bytes(row["stable_source_row_id_v1"])
        digest = hashlib.sha256(
            b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
        )
        encoded = iteration.encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(identity)
        identity_by_hash[digest.hexdigest()] = identity
    label_hashes = {str(row["hashed_review_id"]) for row in labels}
    if label_hashes != set(identity_by_hash):
        raise ValueError("TARGETED_REVIEW_COVERAGE_IDENTITY_MISMATCH")
    reviewed = set(identity_by_hash.values())
    per_hypothesis: dict[str, JsonValue] = {}
    for name, population in populations.items():
        overlap = population & reviewed
        per_hypothesis[name] = {
            "identity_overlap_rows": len(overlap),
            "identity_overlap_digest": _population_digest(
                f"{name}_TARGETED_R01_OVERLAP", overlap
            ),
            "scientifically_reusable_rows": 0,
            "compatibility_reason": (
                "V3_1_REVIEW_ASSESSED_SAME_LINE_EMBEDDED_V4_EVIDENCE_NOT_"
                f"{name}_HYPOTHESIS"
            ),
        }
    return {
        "targeted_v3_1_r01": {
            "completed_rows": len(reviewed),
            "context_sha256": _sha256(context_path),
            "controlled_labels_sha256": _sha256(labels_path),
            "per_hypothesis": per_hypothesis,
        },
        "other_valid_reusable_development_labels": 0,
        "other_label_basis": "NO_OTHER_APPROVED_COMPLETED_LABEL_SET",
    }


def _intersection_report(populations: Mapping[str, set[bytes]]) -> dict[str, JsonValue]:
    h1, h2, h3 = populations["H1"], populations["H2"], populations["H3"]
    triple = h1 & h2 & h3
    regions = {
        "H1_ONLY": h1 - h2 - h3,
        "H2_ONLY": h2 - h1 - h3,
        "H3_ONLY": h3 - h1 - h2,
        "H1_H2_ONLY": (h1 & h2) - h3,
        "H1_H3_ONLY": (h1 & h3) - h2,
        "H2_H3_ONLY": (h2 & h3) - h1,
        "H1_H2_H3": triple,
    }
    union = h1 | h2 | h3
    return {
        "matrix": {
            left: {
                right: len(populations[left] & populations[right])
                for right in ("H1", "H2", "H3")
            }
            for left in ("H1", "H2", "H3")
        },
        "exclusive_regions": {
            name: {
                "rows": len(values),
                "population_digest": _population_digest(name, values),
            }
            for name, values in regions.items()
        },
        "union": {
            "rows": len(union),
            "population_digest": _population_digest("H1_H2_H3_UNION", union),
        },
    }


def _csv_bytes(
    hypotheses: Mapping[str, Mapping[str, JsonValue]],
    intersections: Mapping[str, JsonValue],
) -> bytes:
    matrix = cast(Mapping[str, Mapping[str, int]], intersections["matrix"])
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        (
            "hypothesis",
            "unique_rows",
            "H1_intersection",
            "H2_intersection",
            "H3_intersection",
        )
    )
    for name in ("H1", "H2", "H3"):
        writer.writerow(
            (
                name,
                hypotheses[name]["unique_rows"],
                matrix[name]["H1"],
                matrix[name]["H2"],
                matrix[name]["H3"],
            )
        )
    return buffer.getvalue().encode()


def _markdown_bytes(report: Mapping[str, Any]) -> bytes:
    hypotheses = cast(Mapping[str, Mapping[str, Any]], report["hypotheses"])
    matrix = cast(Mapping[str, Mapping[str, int]], report["intersections"]["matrix"])
    lines = [
        "# Phase 3 DEVELOPMENT hypothesis intersection profile",
        "",
        "Status: `SANITIZED_DEVELOPMENT_DIAGNOSTIC_ONLY`.",
        "",
        "This report quantifies three preregistered structural hypotheses on the fixed 8,000-row DEVELOPMENT corpus. It does not implement or approve a parser rule.",
        "",
        "| Hypothesis | Unique rows | H1 overlap | H2 overlap | H3 overlap |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in ("H1", "H2", "H3"):
        lines.append(
            f"| {name} | {hypotheses[name]['unique_rows']} | {matrix[name]['H1']} | {matrix[name]['H2']} | {matrix[name]['H3']} |"
        )
    lines.extend(
        (
            "",
            "H1 is the existing component-span-overlap conflict population. H2 is explicit role evidence overlapping street/house evidence. H3 is the narrow adjacent explicit-street/house-like-line population after all frozen diagnostic exclusions.",
            "",
            "Exact counts are opportunity sizes, not evidence of correctness. Any implementation requires fictional boundary tests and a separately approved targeted DEVELOPMENT review.",
            "",
            "No raw values, identities, filesystem paths, source spans, protected notes, or production examples are included.",
            "",
        )
    )
    return "\n".join(lines).encode()


def _write_outputs(
    output_directory: Path,
    *,
    report_bytes: bytes,
    csv_bytes: bytes,
    markdown_bytes: bytes,
) -> None:
    output_directory.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = output_directory.parent / f".{output_directory.name}.in_progress"
    if output_directory.exists() or temporary.exists():
        raise FileExistsError("development hypothesis profile output already exists")
    temporary.mkdir(mode=0o700)
    files = {
        "phase03_development_hypothesis_intersection_profile.json": report_bytes,
        "phase03_development_hypothesis_intersections.csv": csv_bytes,
        "phase03_development_hypothesis_intersection_profile.md": markdown_bytes,
    }
    try:
        for name, data in files.items():
            path = temporary / name
            with path.open("xb") as stream:
                os.chmod(path, 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        descriptor = os.open(output_directory.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        if temporary.exists():
            for path in temporary.iterdir():
                path.unlink()
            temporary.rmdir()
        raise


def profile_development_hypothesis_intersections(
    *,
    development_payload_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    candidate_core_path: Path,
    candidate_evidence_path: Path,
    development_identities_path: Path,
    output_directory: Path,
    rule_semantics: Mapping[str, RuleEvidenceSemantics],
    targeted_r01_context_path: Path | None = None,
    targeted_r01_labels_path: Path | None = None,
    expected_rows: int = 8_000,
    expected_targeted_review_rows: int = 11,
    expected_identity_artifact_sha256: str = (
        EXPECTED_DEVELOPMENT_IDENTITY_ARTIFACT_SHA256
    ),
    expected_payload_sha256: str = EXPECTED_DEVELOPMENT_PAYLOAD_SHA256,
    expected_baseline_core_sha256: str = EXPECTED_BASELINE_CORE_SHA256,
    expected_baseline_evidence_sha256: str = EXPECTED_BASELINE_EVIDENCE_SHA256,
    expected_candidate_core_sha256: str = EXPECTED_CANDIDATE_CORE_SHA256,
    expected_candidate_evidence_sha256: str = EXPECTED_CANDIDATE_EVIDENCE_SHA256,
    expected_baseline_configuration: str = EXPECTED_BASELINE_CONFIGURATION,
    expected_candidate_configuration: str = EXPECTED_CANDIDATE_CONFIGURATION,
    production: bool,
) -> ProfileArtifacts:
    """Profile exact H1/H2/H3 DEVELOPMENT populations without changing parsing."""
    if production:
        require_goethe_nhr_slurm("phase03.development-hypothesis-intersection-profile")
    if (
        expected_rows < 1
        or expected_targeted_review_rows < 1
        or not all(
            _HEX64.fullmatch(value)
            for value in (
                expected_identity_artifact_sha256,
                expected_payload_sha256,
                expected_baseline_core_sha256,
                expected_baseline_evidence_sha256,
                expected_candidate_core_sha256,
                expected_candidate_evidence_sha256,
                expected_baseline_configuration,
                expected_candidate_configuration,
            )
        )
    ):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_PROFILE_CONFIGURATION_INVALID")
    paths = (
        development_payload_path,
        baseline_core_path,
        baseline_evidence_path,
        candidate_core_path,
        candidate_evidence_path,
        development_identities_path,
        output_directory,
    )
    optional_paths = tuple(
        path
        for path in (targeted_r01_context_path, targeted_r01_labels_path)
        if path is not None
    )
    _reject_locked_paths((*paths, *optional_paths))
    inputs = paths[:-1] + optional_paths
    before = {
        path.name + f":{index}": _artifact_state(path)
        for index, path in enumerate(inputs)
    }
    if _sha256(development_identities_path) != expected_identity_artifact_sha256:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_IDENTITY_ARTIFACT_SHA_MISMATCH")
    if _sha256(development_payload_path) != expected_payload_sha256:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_PAYLOAD_SHA_MISMATCH")
    expected_parser_hashes = {
        baseline_core_path: expected_baseline_core_sha256,
        baseline_evidence_path: expected_baseline_evidence_sha256,
        candidate_core_path: expected_candidate_core_sha256,
        candidate_evidence_path: expected_candidate_evidence_sha256,
    }
    if any(
        _sha256(path) != expected for path, expected in expected_parser_hashes.items()
    ):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_PARSER_ARTIFACT_SHA_MISMATCH")
    identity_metadata, identities = read_identity_set(development_identities_path)
    if (
        identity_metadata.get("partition") != "DEVELOPMENT"
        or len(identities) != expected_rows
    ):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_IDENTITY_SET_MISMATCH")
    payload, baseline_core, baseline_evidence, candidate_core, candidate_evidence = (
        _read_parsers(
            payload_path=development_payload_path,
            baseline_core_path=baseline_core_path,
            baseline_evidence_path=baseline_evidence_path,
            candidate_core_path=candidate_core_path,
            candidate_evidence_path=candidate_evidence_path,
        )
    )
    if (
        len(payload) != expected_rows
        or len(baseline_core) != expected_rows
        or len(candidate_core) != expected_rows
    ):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_ROW_COUNT_MISMATCH")
    identity_set = set(identities)
    payload_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in payload}
    baseline_by_id = {
        bytes(row["stable_source_row_id_v1"]): row for row in baseline_core
    }
    candidate_by_id = {
        bytes(row["stable_source_row_id_v1"]): row for row in candidate_core
    }
    if (
        len(payload_by_id) != expected_rows
        or len(baseline_by_id) != expected_rows
        or len(candidate_by_id) != expected_rows
        or set(payload_by_id) != identity_set
        or set(baseline_by_id) != identity_set
        or set(candidate_by_id) != identity_set
    ):
        raise ValueError("DEVELOPMENT_HYPOTHESIS_IDENTITY_RECONCILIATION_MISMATCH")
    if [bytes(row["stable_source_row_id_v1"]) for row in baseline_core] != [
        bytes(row["stable_source_row_id_v1"]) for row in candidate_core
    ]:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_CORE_ORDER_MISMATCH")
    _validate_parser_rows(
        core_rows=baseline_core,
        evidence_rows=baseline_evidence,
        payload_by_id=payload_by_id,
        expected_parser=PARSER_VERSION_V2_1,
        expected_registry=RULE_REGISTRY_VERSION_V3,
        expected_configuration=expected_baseline_configuration,
    )
    _validate_parser_rows(
        core_rows=candidate_core,
        evidence_rows=candidate_evidence,
        payload_by_id=payload_by_id,
        expected_parser=PARSER_VERSION_V3_2,
        expected_registry=RULE_REGISTRY_VERSION_V5,
        expected_configuration=expected_candidate_configuration,
    )
    candidate_groups_by_id: dict[bytes, list[_EvidenceGroup]] = defaultdict(list)
    for group in _group_evidence(candidate_evidence):
        if group.stable_id not in identity_set:
            raise ValueError("DEVELOPMENT_HYPOTHESIS_UNKNOWN_EVIDENCE_IDENTITY")
        candidate_groups_by_id[group.stable_id].append(group)

    h1, h1_report = _h1_profile(
        core_by_id=candidate_by_id, groups_by_id=candidate_groups_by_id
    )
    h2, h2_report = _h2_profile(
        payload_by_id=payload_by_id,
        groups_by_id=candidate_groups_by_id,
        rule_semantics=rule_semantics,
    )
    h3, h3_report = _h3_profile(
        payload_by_id=payload_by_id,
        core_by_id=candidate_by_id,
        groups_by_id=candidate_groups_by_id,
        rule_semantics=rule_semantics,
    )
    populations = {"H1": h1, "H2": h2, "H3": h3}
    intersections = _intersection_report(populations)
    h3_report["overlap_with_h1_rows"] = len(h3 & h1)
    h3_report["overlap_with_h2_rows"] = len(h3 & h2)
    review_coverage = _review_coverage(
        context_path=targeted_r01_context_path,
        labels_path=targeted_r01_labels_path,
        populations=populations,
        expected_rows=expected_targeted_review_rows,
    )
    after = {
        path.name + f":{index}": _artifact_state(path)
        for index, path in enumerate(inputs)
    }
    if before != after:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_INPUT_MUTATED")
    hypotheses: dict[str, Mapping[str, JsonValue]] = {
        "H1": h1_report,
        "H2": h2_report,
        "H3": h3_report,
    }
    input_artifacts = {
        role: {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for role, path in zip(
            (
                "development_payload",
                "baseline_core",
                "baseline_evidence",
                "candidate_core",
                "candidate_evidence",
                "development_identities",
                *(
                    ("targeted_r01_context", "targeted_r01_labels")
                    if optional_paths
                    else ()
                ),
            ),
            inputs,
            strict=True,
        )
    }
    report: dict[str, JsonValue] = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "profiler_version": PROFILER_VERSION,
        "status": "SANITIZED_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "rows": expected_rows,
        "development_identity_verification": {
            "partition": "DEVELOPMENT",
            "count": len(identities),
            "identity_artifact_sha256": expected_identity_artifact_sha256,
            "identity_population_digest": _population_digest("DEVELOPMENT", identities),
            "core_identity_order_digest": _identity_order_digest(candidate_core),
        },
        "parser_bindings": {
            "baseline_parser": PARSER_VERSION_V2_1,
            "baseline_registry": RULE_REGISTRY_VERSION_V3,
            "baseline_configuration_fingerprint": expected_baseline_configuration,
            "candidate_parser": PARSER_VERSION_V3_2,
            "candidate_registry": RULE_REGISTRY_VERSION_V5,
            "candidate_configuration_fingerprint": expected_candidate_configuration,
        },
        "definitions": {
            "H1": "EXISTING_COMPONENT_SPAN_OVERLAP_CONFLICT",
            "H2": "EXPLICIT_ROLE_EVIDENCE_OVERLAPS_STREET_OR_HOUSE_EVIDENCE",
            "H3": "ADJACENT_EXPLICIT_STREET_AND_SINGLE_HOUSELIKE_LINE_AFTER_EXCLUSIONS",
            "H2_strength_note": "CONFIDENCE_AND_REGISTRY_PRIORITY_REPORTED_SEPARATELY_NO_NEW_ARBITRATION",
        },
        "hypotheses": cast(JsonValue, hypotheses),
        "intersections": cast(JsonValue, intersections),
        "review_coverage": review_coverage,
        "input_artifacts": cast(JsonValue, input_artifacts),
        "privacy": {
            "raw_values_reported": False,
            "identities_reported": False,
            "source_spans_reported": False,
            "filesystem_paths_reported": False,
            "protected_notes_reported": False,
            "locked_rows_read": 0,
        },
        "scientific_guardrails": {
            "parser_output_modified": False,
            "parser_rule_implementation_authorized": False,
            "selector_rerun": False,
            "frequency_implies_correctness": False,
        },
    }
    payload_without_fingerprint = report.copy()
    report["profile_fingerprint"] = fingerprint(payload_without_fingerprint)
    report_bytes = canonical_json_bytes(report)
    csv_bytes = _csv_bytes(hypotheses, intersections)
    markdown_bytes = _markdown_bytes(report)
    _write_outputs(
        output_directory,
        report_bytes=report_bytes,
        csv_bytes=csv_bytes,
        markdown_bytes=markdown_bytes,
    )
    parsed = json.loads(
        (
            output_directory
            / "phase03_development_hypothesis_intersection_profile.json"
        ).read_text()
    )
    if parsed != report:
        raise ValueError("DEVELOPMENT_HYPOTHESIS_REPORT_READBACK_MISMATCH")
    return ProfileArtifacts(
        report_json=output_directory
        / "phase03_development_hypothesis_intersection_profile.json",
        intersections_csv=output_directory
        / "phase03_development_hypothesis_intersections.csv",
        interpretation_markdown=output_directory
        / "phase03_development_hypothesis_intersection_profile.md",
        profile_fingerprint=str(report["profile_fingerprint"]),
        rows=expected_rows,
    )

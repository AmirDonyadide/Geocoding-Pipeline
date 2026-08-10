from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .constants import (
    ADDRESS_FIELDS,
    COMPLETENESS_CLASSES,
    COMPONENTS,
    CONFIDENCES,
    CONFLICT_FLAGS,
    CORE_COLUMNS,
    COUNTRY_INPUT_CLASSES,
    COUNTRY_PARSE_METHODS,
    DIAGNOSTIC_FLAGS,
    EVALUATION_STATUSES,
    EVIDENCE_COLUMNS,
    EVIDENCE_KINDS,
    NATIVE_RELATIONSHIPS,
    PARSE_STATUSES,
    POSTCODE_FLAGS,
    REPRESENTATIONS,
    STRUCTURED_GEOGRAPHY_FIELDS,
)
from .errors import Phase03Error

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


def _is_ordered_vocabulary_subset(
    values: Sequence[str], vocabulary: Sequence[str]
) -> bool:
    return len(values) == len(set(values)) and list(values) == [
        item for item in vocabulary if item in set(values)
    ]


def validate_core_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_ids: Sequence[tuple[bytes, str, int]] | None = None,
) -> None:
    seen: set[bytes] = set()
    for ordinal, row in enumerate(rows, start=1):
        if tuple(row.keys()) != CORE_COLUMNS:
            raise Phase03Error("CORE_ROW_SCHEMA_MISMATCH")
        stable_id = row["stable_source_row_id_v1"]
        if (
            not isinstance(stable_id, bytes)
            or len(stable_id) != 32
            or stable_id in seen
        ):
            raise Phase03Error("CORE_IDENTITY_INVALID")
        seen.add(stable_id)
        if (
            not isinstance(row["source_file_sha256"], bytes)
            or len(row["source_file_sha256"]) != 32
            or not isinstance(row["configuration_fingerprint"], bytes)
            or len(row["configuration_fingerprint"]) != 32
            or not isinstance(row["implementation_fingerprint"], bytes)
            or len(row["implementation_fingerprint"]) != 32
        ):
            raise Phase03Error("CORE_BINARY_IDENTITY_INVALID")
        for name, value in row.items():
            if (
                name.endswith("_clean")
                and value is not None
                and (not isinstance(value, str) or not value)
            ):
                raise Phase03Error("EMPTY_SELECTED_COMPONENT")
        if row["address_parse_status"] not in PARSE_STATUSES:
            raise Phase03Error("PARSE_STATUS_INVALID")
        if row["address_completeness_class"] not in COMPLETENESS_CLASSES:
            raise Phase03Error("COMPLETENESS_CLASS_INVALID")
        if row["diagnostic_evaluation_status"] not in EVALUATION_STATUSES:
            raise Phase03Error("EVALUATION_STATUS_INVALID")
        if row["country_input_class"] not in COUNTRY_INPUT_CLASSES:
            raise Phase03Error("COUNTRY_INPUT_CLASS_INVALID")
        if row["country_parse_method"] not in COUNTRY_PARSE_METHODS:
            raise Phase03Error("COUNTRY_PARSE_METHOD_INVALID")
        if row["country_parse_confidence"] not in CONFIDENCES:
            raise Phase03Error("COUNTRY_PARSE_CONFIDENCE_INVALID")
        if not _is_ordered_vocabulary_subset(
            row["address_conflict_flags"], CONFLICT_FLAGS
        ):
            raise Phase03Error("CONFLICT_VOCABULARY_INVALID")
        if not _is_ordered_vocabulary_subset(
            row["address_diagnostic_flags"], DIAGNOSTIC_FLAGS
        ):
            raise Phase03Error("DIAGNOSTIC_VOCABULARY_INVALID")
        if not _is_ordered_vocabulary_subset(
            row["postcode_diagnostic_flags"], POSTCODE_FLAGS
        ):
            raise Phase03Error("POSTCODE_VOCABULARY_INVALID")
        allowed_skipped = (*ADDRESS_FIELDS, *STRUCTURED_GEOGRAPHY_FIELDS)
        if not _is_ordered_vocabulary_subset(
            row["skipped_oversized_fields"], allowed_skipped
        ):
            raise Phase03Error("SKIPPED_FIELD_VOCABULARY_INVALID")
        relationships = row["native_non_native_relationships"]
        if [item["line_number"] for item in relationships] != [1, 2, 3, 4] or any(
            item["relationship"] not in NATIVE_RELATIONSHIPS for item in relationships
        ):
            raise Phase03Error("NATIVE_RELATIONSHIP_INVALID")
        selected = {
            (item["component"], item["representation"])
            for item in row["selected_component_provenance"]
        }
        for item in row["selected_component_provenance"]:
            if (
                item["component"] not in COMPONENTS
                or item["representation"] not in REPRESENTATIONS
                or item["confidence"] not in CONFIDENCES[:-1]
                or not item["source_fields"]
                or len(item["source_fields"]) != len(set(item["source_fields"]))
                or not item["rule_ids"]
                or len(item["rule_ids"]) != len(set(item["rule_ids"]))
            ):
                raise Phase03Error("SELECTED_PROVENANCE_INVALID")
            scalar = _COMPONENT_TO_SCALAR.get(
                (item["component"], item["representation"])
            )
            if scalar is not None and row[scalar] is None:
                raise Phase03Error("SELECTED_PROVENANCE_WITHOUT_VALUE")
        selected_scalars = {
            _COMPONENT_TO_SCALAR[key] for key in selected if key in _COMPONENT_TO_SCALAR
        }
        populated_scalars = {
            name
            for name, value in row.items()
            if name.endswith("_clean") and value is not None
        }
        if selected_scalars != populated_scalars:
            raise Phase03Error("SELECTED_VALUE_PROVENANCE_MISMATCH")
        if expected_ids is not None:
            expected_stable, expected_provider, expected_ordinal = expected_ids[
                ordinal - 1
            ]
            if (
                stable_id != expected_stable
                or row["id"] != expected_provider
                or row["source_logical_record_number"] != expected_ordinal
            ):
                raise Phase03Error("CORE_SOURCE_IDENTITY_MISMATCH")
        if len(selected) != len(row["selected_component_provenance"]):
            raise Phase03Error("SELECTED_PROVENANCE_DUPLICATE")
        selected_order = [
            (item["component"], item["representation"])
            for item in row["selected_component_provenance"]
        ]
        if selected_order != sorted(
            selected_order,
            key=lambda item: (
                COMPONENTS.index(item[0]),
                REPRESENTATIONS.index(item[1]),
            ),
        ):
            raise Phase03Error("SELECTED_PROVENANCE_ORDER_INVALID")


def validate_evidence_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    raw_values_by_id: Mapping[bytes, Mapping[str, str]] | None = None,
) -> None:
    previous: tuple[int, int, int] | None = None
    for row in rows:
        if tuple(row.keys()) != EVIDENCE_COLUMNS:
            raise Phase03Error("EVIDENCE_ROW_SCHEMA_MISMATCH")
        if row["evidence_kind"] not in EVIDENCE_KINDS:
            raise Phase03Error("EVIDENCE_VOCABULARY_INVALID")
        if (
            not isinstance(row["stable_source_row_id_v1"], bytes)
            or len(row["stable_source_row_id_v1"]) != 32
        ):
            raise Phase03Error("EVIDENCE_IDENTITY_INVALID")
        if row["component"] is not None and row["component"] not in COMPONENTS:
            raise Phase03Error("EVIDENCE_COMPONENT_INVALID")
        if (
            row["representation"] is not None
            and row["representation"] not in REPRESENTATIONS
        ):
            raise Phase03Error("EVIDENCE_REPRESENTATION_INVALID")
        if row["confidence"] is not None and row["confidence"] not in CONFIDENCES[:-1]:
            raise Phase03Error("EVIDENCE_CONFIDENCE_INVALID")
        if (
            row["conflict_flag"] is not None
            and row["conflict_flag"] not in CONFLICT_FLAGS
        ):
            raise Phase03Error("EVIDENCE_CONFLICT_INVALID")
        if (
            row["diagnostic_flag"] is not None
            and row["diagnostic_flag"] not in DIAGNOSTIC_FLAGS
        ):
            raise Phase03Error("EVIDENCE_DIAGNOSTIC_INVALID")
        if row["source_field"] not in {*ADDRESS_FIELDS, *STRUCTURED_GEOGRAPHY_FIELDS}:
            raise Phase03Error("EVIDENCE_SOURCE_FIELD_INVALID")
        key = (
            row["source_logical_record_number"],
            row["evidence_id"],
            row["span_ordinal"],
        )
        if previous is not None and key <= previous:
            raise Phase03Error("EVIDENCE_ORDER_INVALID")
        previous = key
        if row["start_character"] >= row["end_character_exclusive"]:
            raise Phase03Error("EVIDENCE_SPAN_INVALID")
        if row["candidate_value"] is not None and not row["candidate_value"]:
            raise Phase03Error("EVIDENCE_EMPTY_CANDIDATE")
        if row["selected"] and row["evidence_kind"] != "SELECTED_NONTRIVIAL_COMPONENT":
            raise Phase03Error("EVIDENCE_SELECTION_INVALID")
        if row["evidence_kind"] in {
            "SELECTED_NONTRIVIAL_COMPONENT",
            "UNSELECTED_CANDIDATE",
            "COMPETING_CANDIDATE",
            "CONFLICTING_EVIDENCE",
        } and any(
            row[name] is None
            for name in (
                "component",
                "representation",
                "candidate_value",
                "confidence",
                "rule_id",
            )
        ):
            raise Phase03Error("EVIDENCE_CANDIDATE_INCOMPLETE")
        if raw_values_by_id is not None:
            raw = raw_values_by_id[row["stable_source_row_id_v1"]][row["source_field"]]
            if row["end_character_exclusive"] > len(raw):
                raise Phase03Error("EVIDENCE_SPAN_INVALID")


def validate_core_evidence_relationship(
    core_rows: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
) -> None:
    core_by_id = {row["stable_source_row_id_v1"]: row for row in core_rows}
    evidence_ids_by_source: dict[bytes, set[int]] = {}
    span_ordinals_by_group: dict[tuple[bytes, int], list[int]] = {}
    group_signature: dict[tuple[bytes, int], tuple[Any, ...]] = {}
    signature_fields = (
        "evidence_kind",
        "component",
        "representation",
        "candidate_value",
        "selected",
        "confidence",
        "rule_id",
        "conflict_flag",
        "diagnostic_flag",
    )
    for row in evidence_rows:
        stable_id = row["stable_source_row_id_v1"]
        core = core_by_id.get(stable_id)
        if core is None:
            raise Phase03Error("EVIDENCE_ORPHAN_IDENTITY")
        if (
            row["source_file"] != core["source_file"]
            or row["source_logical_record_number"]
            != core["source_logical_record_number"]
        ):
            raise Phase03Error("EVIDENCE_SOURCE_IDENTITY_MISMATCH")
        if any(
            row[key] != core[key]
            for key in ("parser_version", "rule_registry_version", "phase03_version")
        ):
            raise Phase03Error("EVIDENCE_VERSION_MISMATCH")
        evidence_id = row["evidence_id"]
        key = (stable_id, evidence_id)
        evidence_ids_by_source.setdefault(stable_id, set()).add(evidence_id)
        span_ordinals_by_group.setdefault(key, []).append(row["span_ordinal"])
        signature = tuple(row[field] for field in signature_fields)
        if key in group_signature and group_signature[key] != signature:
            raise Phase03Error("EVIDENCE_GROUP_INCONSISTENT")
        group_signature[key] = signature
        if row["selected"]:
            provenance = {
                (item["component"], item["representation"])
                for item in core["selected_component_provenance"]
            }
            if (row["component"], row["representation"]) not in provenance:
                raise Phase03Error("EVIDENCE_SELECTION_PROVENANCE_MISMATCH")
    for evidence_ids in evidence_ids_by_source.values():
        if evidence_ids != set(range(1, max(evidence_ids) + 1)):
            raise Phase03Error("EVIDENCE_ID_SEQUENCE_INVALID")
    for ordinals in span_ordinals_by_group.values():
        if ordinals != list(range(1, len(ordinals) + 1)):
            raise Phase03Error("EVIDENCE_SPAN_SEQUENCE_INVALID")


def privacy_safe_failure(code: str, detail: str = "") -> dict[str, str]:
    safe_code = (
        code if re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code) else "UNKNOWN_FAILURE"
    )
    safe_detail = (
        detail
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]{0,79}", detail)
        else "REDACTED"
        if detail
        else ""
    )
    return {"failure_code": safe_code, "failure_detail_type": safe_detail}

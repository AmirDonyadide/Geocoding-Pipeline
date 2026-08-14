from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

import pyarrow as pa

from .constants import MANUAL_REVIEW_REASON_CODES_VERSION
from .review import canonicalize_manual_review_reason_codes

MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2: Final = "phase03_manual_review_labels_v2"
MANUAL_REVIEW_LABEL_VOCABULARY_VERSION: Final = "manual_review_label_vocabularies_v1"
REVIEW_PROGRESS_SCHEMA_VERSION: Final = "phase03_review_progress_sqlite_v1"
REVIEW_EXPORT_MANIFEST_VERSION: Final = "phase03_review_export_manifest_v1"
REVIEWED_PARSER_COMMIT: Final = "f9699cbc88150defd764489fe10338d134e8ff61"
MAX_PROTECTED_NOTE_CHARACTERS: Final = 500

COMPONENT_LABEL_VALUES: Final = (
    "CORRECT",
    "INCORRECT",
    "MISSED",
    "NOT_PRESENT",
    "CANNOT_ASSESS",
)
ERROR_CONDITION_LABEL_VALUES: Final = ("ABSENT", "PRESENT", "CANNOT_ASSESS")
CONFLICT_LABEL_VALUES: Final = (
    "CORRECT",
    "INCORRECT",
    "NOT_APPLICABLE",
    "CANNOT_ASSESS",
)
OVERALL_LABEL_VALUES: Final = (
    "ACCEPTABLE",
    "NOT_ACCEPTABLE",
    "CANNOT_ASSESS",
)
ASSIGNMENT_ROLE_VALUES: Final = ("PRIMARY", "INDEPENDENT_SECOND")

COMPONENT_LABEL_FIELDS: Final = (
    "street_label",
    "house_number_label",
    "unit_label",
    "floor_label",
    "building_label",
    "organization_address_role_label",
    "postcode_label",
    "locality_label",
    "region_label",
    "country_label",
)
ERROR_CONDITION_LABEL_FIELDS: Final = (
    "parser_overreach_label",
    "missed_information_label",
    "unsafe_handling_label",
)
ALL_REVIEW_LABEL_FIELDS: Final = COMPONENT_LABEL_FIELDS + (
    "conflict_correctness_label",
    *ERROR_CONDITION_LABEL_FIELDS,
    "overall_parse_acceptability_label",
)

_PSEUDONYMOUS_REVIEWER_ID = re.compile(r"R[0-9]{2}")
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}")
_UNCERTAINTY_REASONS = {
    "SOURCE_AMBIGUOUS",
    "INSUFFICIENT_SOURCE_EVIDENCE",
}
_COMPONENT_INCORRECT_REASONS = {
    "WRONG_COMPONENT_ROLE",
    "WRONG_VALUE",
    "WRONG_SPAN_BOUNDARY",
    "FALSE_POSITIVE_EXTRACTION",
    "WRONG_NORMALIZATION",
    "WRONG_PROVENANCE",
}
_PARSER_OVERREACH_REASONS = {
    "FALSE_POSITIVE_EXTRACTION",
    "WRONG_COMPONENT_ROLE",
}
_CONFLICT_INCORRECT_REASONS = {
    "WRONG_CONFLICT_DETECTION",
    "MISSED_CONFLICT",
}


def manual_review_schema_v2() -> pa.Schema:
    label = pa.string()
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("pilot_version", pa.string(), nullable=False),
            pa.field("sample_partition", pa.string(), nullable=False),
            pa.field("reviewer_id", pa.string(), nullable=False),
            pa.field("review_round", pa.uint8(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
            pa.field("assignment_role", pa.string(), nullable=False),
            *(pa.field(name, label, nullable=False) for name in COMPONENT_LABEL_FIELDS),
            pa.field("conflict_correctness_label", label, nullable=False),
            *(
                pa.field(name, label, nullable=False)
                for name in ERROR_CONDITION_LABEL_FIELDS
            ),
            pa.field("overall_parse_acceptability_label", label, nullable=False),
            pa.field("reason_codes", pa.list_(pa.string()), nullable=False),
            pa.field("reason_codes_version", pa.string(), nullable=False),
            pa.field("label_vocabulary_version", pa.string(), nullable=False),
            pa.field("adjudicated_label", label, nullable=True),
            pa.field("adjudicator_id", pa.string(), nullable=True),
            pa.field("label_schema_version", pa.string(), nullable=False),
        ]
    )


def validate_reviewer_id(reviewer_id: str) -> None:
    if not _PSEUDONYMOUS_REVIEWER_ID.fullmatch(reviewer_id):
        raise ValueError("reviewer ID must be a pseudonymous code like R01")


def _validate_exact_label(
    row: Mapping[str, Any], field: str, allowed: Sequence[str]
) -> str:
    value = row.get(field)
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"invalid closed label value for {field}")
    return value


def _requires_any(
    condition: bool,
    reasons: set[str],
    applicable: set[str],
    message: str,
) -> None:
    if condition and reasons.isdisjoint(applicable):
        raise ValueError(message)


def validate_completed_review_record_v2(
    row: Mapping[str, Any], *, protected_note: str | None = None
) -> tuple[str, ...]:
    """Validate one completed portable-v2 reviewer record.

    Protected notes participate in validation but are intentionally absent from
    the portable row returned by the caller.
    """
    if set(row) != set(manual_review_schema_v2().names):
        raise ValueError("portable v2 review-label schema mismatch")
    hashed_id = row.get("hashed_review_id")
    if not isinstance(hashed_id, str) or not _LOWER_HEX_64.fullmatch(hashed_id):
        raise ValueError("hashed review ID must be 64 lowercase hex characters")
    reviewer_id = row.get("reviewer_id")
    if not isinstance(reviewer_id, str):
        raise ValueError("reviewer ID must be text")
    validate_reviewer_id(reviewer_id)
    if row.get("sample_partition") != "DEVELOPMENT":
        raise ValueError("manual review may contain DEVELOPMENT records only")
    if row.get("review_round") != 1:
        raise ValueError("review interface v1 supports review round 1 only")
    if not isinstance(row.get("is_independent_review"), bool):
        raise ValueError("independent-review designation must be boolean")
    assignment_role = _validate_exact_label(
        row, "assignment_role", ASSIGNMENT_ROLE_VALUES
    )
    expected_role = {"R01": "PRIMARY", "R02": "INDEPENDENT_SECOND"}.get(reviewer_id)
    if expected_role is None or assignment_role != expected_role:
        raise ValueError("reviewer ID and assignment role are inconsistent")
    if assignment_role == "INDEPENDENT_SECOND" and not row["is_independent_review"]:
        raise ValueError("independent second reviewer lost frozen designation")
    if row.get("reason_codes_version") != MANUAL_REVIEW_REASON_CODES_VERSION:
        raise ValueError("manual-review reason-code version mismatch")
    if row.get("label_vocabulary_version") != MANUAL_REVIEW_LABEL_VOCABULARY_VERSION:
        raise ValueError("manual-review label-vocabulary version mismatch")
    if row.get("label_schema_version") != MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2:
        raise ValueError("manual-review label-schema version mismatch")
    if (
        row.get("adjudicated_label") is not None
        or row.get("adjudicator_id") is not None
    ):
        raise ValueError("adjudication is outside the reviewer-record workflow")
    pilot_version = row.get("pilot_version")
    if not isinstance(pilot_version, str) or not pilot_version:
        raise ValueError("pilot version must be non-empty text")

    component_values = {
        field: _validate_exact_label(row, field, COMPONENT_LABEL_VALUES)
        for field in COMPONENT_LABEL_FIELDS
    }
    conflict = _validate_exact_label(
        row, "conflict_correctness_label", CONFLICT_LABEL_VALUES
    )
    error_values = {
        field: _validate_exact_label(row, field, ERROR_CONDITION_LABEL_VALUES)
        for field in ERROR_CONDITION_LABEL_FIELDS
    }
    overall = _validate_exact_label(
        row, "overall_parse_acceptability_label", OVERALL_LABEL_VALUES
    )

    if (
        protected_note is not None
        and len(protected_note) > MAX_PROTECTED_NOTE_CHARACTERS
    ):
        raise ValueError("protected note exceeds 500 Unicode characters")
    reason_codes = row.get("reason_codes")
    if not isinstance(reason_codes, (list, tuple)):
        raise ValueError("manual-review reason codes must be a sequence")
    canonical = canonicalize_manual_review_reason_codes(
        reason_codes,
        protected_adjudication_note=protected_note,
    )
    if tuple(reason_codes) != canonical:
        raise ValueError("manual-review reason codes are not canonical")
    if not canonical:
        raise ValueError("a completed review requires at least one reason code")
    reasons = set(canonical)
    if "CORRECT_AS_IS" in reasons and len(reasons) != 1:
        raise ValueError("CORRECT_AS_IS is exclusive of error reason codes")

    missed = any(value == "MISSED" for value in component_values.values())
    if missed and error_values["missed_information_label"] != "PRESENT":
        raise ValueError("component MISSED requires missed information PRESENT")
    if error_values["missed_information_label"] == "ABSENT" and missed:
        raise ValueError("missed information ABSENT forbids component MISSED")

    _requires_any(
        any(value == "INCORRECT" for value in component_values.values()),
        reasons,
        _COMPONENT_INCORRECT_REASONS,
        "component INCORRECT requires an applicable error reason",
    )
    _requires_any(
        missed,
        reasons,
        {"MISSED_EXTRACTABLE_COMPONENT"},
        "component MISSED requires MISSED_EXTRACTABLE_COMPONENT",
    )
    _requires_any(
        error_values["parser_overreach_label"] == "PRESENT",
        reasons,
        _PARSER_OVERREACH_REASONS,
        "parser overreach PRESENT requires an applicable error reason",
    )
    _requires_any(
        error_values["missed_information_label"] == "PRESENT",
        reasons,
        {"MISSED_EXTRACTABLE_COMPONENT"},
        "missed information PRESENT requires MISSED_EXTRACTABLE_COMPONENT",
    )
    _requires_any(
        error_values["unsafe_handling_label"] == "PRESENT",
        reasons,
        {"UNSAFE_INPUT_HANDLING"},
        "unsafe handling PRESENT requires UNSAFE_INPUT_HANDLING",
    )
    _requires_any(
        conflict == "INCORRECT",
        reasons,
        _CONFLICT_INCORRECT_REASONS,
        "conflict INCORRECT requires an applicable conflict reason",
    )
    _requires_any(
        overall == "NOT_ACCEPTABLE",
        reasons,
        reasons - {"CORRECT_AS_IS"},
        "NOT_ACCEPTABLE requires an applicable reason",
    )
    cannot_assess = (
        any(value == "CANNOT_ASSESS" for value in component_values.values())
        or conflict == "CANNOT_ASSESS"
        or any(value == "CANNOT_ASSESS" for value in error_values.values())
        or overall == "CANNOT_ASSESS"
    )
    _requires_any(
        cannot_assess,
        reasons,
        _UNCERTAINTY_REASONS,
        "CANNOT_ASSESS requires an applicable uncertainty reason",
    )

    has_error_state = (
        any(
            value in {"INCORRECT", "MISSED", "CANNOT_ASSESS"}
            for value in component_values.values()
        )
        or conflict in {"INCORRECT", "CANNOT_ASSESS"}
        or any(value in {"PRESENT", "CANNOT_ASSESS"} for value in error_values.values())
        or overall in {"NOT_ACCEPTABLE", "CANNOT_ASSESS"}
    )
    if "CORRECT_AS_IS" in reasons and has_error_state:
        raise ValueError("CORRECT_AS_IS conflicts with review labels")
    return canonical


def portable_v2_privacy_columns() -> frozenset[str]:
    return frozenset(manual_review_schema_v2().names)

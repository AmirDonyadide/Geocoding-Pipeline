from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any

import pyarrow as pa

from .constants import (
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
)

MANUAL_REVIEW_REASON_CODE_DEFINITIONS_V1 = {
    "CORRECT_AS_IS": "The parser/result is correct for the available source evidence.",
    "SOURCE_AMBIGUOUS": (
        "The source itself supports multiple reasonable interpretations."
    ),
    "INSUFFICIENT_SOURCE_EVIDENCE": (
        "The reviewer cannot establish the component from the supplied source."
    ),
    "WRONG_COMPONENT_ROLE": (
        "Extracted text belongs to another role, for example unit vs house number."
    ),
    "WRONG_VALUE": (
        "The component role is appropriate but the selected value is wrong."
    ),
    "WRONG_SPAN_BOUNDARY": (
        "The correct source region was targeted but span boundaries are incorrect."
    ),
    "FALSE_POSITIVE_EXTRACTION": (
        "The parser created structure not supported by the source."
    ),
    "MISSED_EXTRACTABLE_COMPONENT": (
        "A component was clearly extractable under the review standard but was not "
        "identified."
    ),
    "WRONG_NORMALIZATION": (
        "The underlying component is correct but the derived normalization changed "
        "it incorrectly."
    ),
    "WRONG_PROVENANCE": (
        "The value is correct but its recorded source/rule provenance is wrong."
    ),
    "WRONG_CONFLICT_DETECTION": (
        "The parser reported a conflict that is not supported."
    ),
    "MISSED_CONFLICT": "A genuine conflict was present but not reported.",
    "UNSUPPORTED_FORMAT": (
        "The source contains a legitimate pattern intentionally outside parser v1 "
        "coverage."
    ),
    "UNSAFE_INPUT_HANDLING": (
        "Operational safety/oversized handling was incorrect."
    ),
    "OTHER_ADJUDICATION_REQUIRED": (
        "No existing closed reason fits. This requires an adjudication note and "
        "should be rare."
    ),
}
MANUAL_REVIEW_REASON_CODES_V1 = tuple(MANUAL_REVIEW_REASON_CODE_DEFINITIONS_V1)
_REASON_CODE_ORDER = {
    code: index for index, code in enumerate(MANUAL_REVIEW_REASON_CODES_V1)
}


def hashed_review_id(stable_source_row_id_v1: bytes, pilot_version: str) -> str:
    if len(stable_source_row_id_v1) != 32:
        raise ValueError("stable source row ID must be 32 bytes")
    digest = hashlib.sha256()
    digest.update(b"safe_geocoding_pipeline:phase03_review_id_v1\0")
    digest.update(len(pilot_version.encode()).to_bytes(8, "big"))
    digest.update(pilot_version.encode())
    digest.update(stable_source_row_id_v1)
    return digest.hexdigest()


def manual_review_schema() -> pa.Schema:
    label = pa.string()
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("pilot_version", pa.string(), nullable=False),
            pa.field("sample_partition", pa.string(), nullable=False),
            pa.field("reviewer_id", pa.string(), nullable=False),
            pa.field("review_round", pa.uint8(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
            pa.field("street_label", label, nullable=True),
            pa.field("house_number_label", label, nullable=True),
            pa.field("unit_floor_building_label", label, nullable=True),
            pa.field("organization_address_role_label", label, nullable=True),
            pa.field("postcode_locality_region_country_label", label, nullable=True),
            pa.field("conflict_correctness_label", label, nullable=True),
            pa.field("parser_overreach_label", label, nullable=True),
            pa.field("missed_information_label", label, nullable=True),
            pa.field("unsafe_handling_label", label, nullable=True),
            pa.field("overall_parse_acceptability_label", label, nullable=True),
            pa.field("reason_codes", pa.list_(pa.string()), nullable=False),
            pa.field("reason_codes_version", pa.string(), nullable=False),
            pa.field("adjudicated_label", label, nullable=True),
            pa.field("adjudicator_id", pa.string(), nullable=True),
            pa.field("label_schema_version", pa.string(), nullable=False),
        ]
    )


PROHIBITED_REVIEW_COLUMNS = frozenset(
    {
        "id",
        "provider_id",
        "street_address_line_1",
        "street_address_line_2",
        "street_address_line_3",
        "street_address_line_4",
        "raw_address",
        "postcode",
        "city",
    }
)


def validate_portable_review_columns(columns: set[str]) -> None:
    if columns & PROHIBITED_REVIEW_COLUMNS:
        raise ValueError(
            "portable review labels contain prohibited raw identity/address columns"
        )
    if columns != set(manual_review_schema().names):
        raise ValueError("portable review-label schema mismatch")


def canonicalize_manual_review_reason_codes(
    reason_codes: Iterable[str],
    *,
    protected_adjudication_note: str | None = None,
) -> tuple[str, ...]:
    """Validate and canonically order the closed v1 reason vocabulary.

    The optional note is a controlled-environment input and is never part of the
    portable review-label schema.
    """
    if isinstance(reason_codes, (str, bytes)):
        raise ValueError("manual-review reason codes must be a sequence")
    values = tuple(reason_codes)
    if any(not isinstance(value, str) for value in values):
        raise ValueError("manual-review reason code must be text")
    unknown = set(values) - set(MANUAL_REVIEW_REASON_CODES_V1)
    if unknown:
        raise ValueError("unknown manual-review reason code")
    canonical = tuple(sorted(set(values), key=_REASON_CODE_ORDER.__getitem__))
    if (
        "OTHER_ADJUDICATION_REQUIRED" in canonical
        and (
            protected_adjudication_note is None
            or not protected_adjudication_note.strip()
        )
    ):
        raise ValueError(
            "OTHER_ADJUDICATION_REQUIRED requires a protected adjudication note"
        )
    return canonical


def validate_portable_review_row(
    row: Mapping[str, Any],
    *,
    protected_adjudication_note: str | None = None,
) -> None:
    """Validate portable review structure without accepting confidential text."""
    validate_portable_review_columns(set(row))
    if row["reason_codes_version"] != MANUAL_REVIEW_REASON_CODES_VERSION:
        raise ValueError("manual-review reason-code version mismatch")
    if row["label_schema_version"] != MANUAL_REVIEW_LABEL_SCHEMA_VERSION:
        raise ValueError("manual-review label-schema version mismatch")
    reason_codes = row["reason_codes"]
    if not isinstance(reason_codes, (list, tuple)):
        raise ValueError("manual-review reason codes must be a sequence")
    canonical = canonicalize_manual_review_reason_codes(
        reason_codes,
        protected_adjudication_note=protected_adjudication_note,
    )
    if tuple(reason_codes) != canonical:
        raise ValueError("manual-review reason codes are not canonical")

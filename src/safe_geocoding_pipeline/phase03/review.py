from __future__ import annotations

import hashlib

import pyarrow as pa


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

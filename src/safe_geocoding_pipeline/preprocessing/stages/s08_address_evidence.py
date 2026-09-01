"""Frozen Stage 8 lossless address-evidence projection.

Stage 8 copies the accepted Stage 7 v2 candidate relation, exposes its raw
ordered libpostal list as a reversible long evidence index, and projects the
accepted Stage 6 source-row map.  It does not normalize, validate, correct,
score, geocode, or promote parser output to semantic truth.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s03_cleaning import EXPECTED_PYARROW_VERSION, EXPECTED_PYTHON_VERSION
from .s06_exact_deduplication import (
    ROW_MAP_DIRECTORY as STAGE06_ROW_MAP_DIRECTORY,
    STAGE06_CONTRACT_VERSION,
    STAGE06_PROFILE_VERSION,
    Stage06ArtifactIdentity,
    Stage06ValidationError,
    _fsync_directory,
    _manifest_artifacts as _stage06_manifest_artifacts,
    row_map_schema,
)
from .s07_country_eligibility import (
    COUNTRY_CONFLICTING,
    COUNTRY_INVALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_PROVENANCE_STATUSES,
    COUNTRY_UNANIMOUS_VALID,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
)
from .s07_libpostal_adapter import PARSED_EMPTY, PARSED_NONEMPTY
from .s07_parser_evidence import (
    NO_STRUCTURAL_WARNINGS_DETECTED,
    PARSER_EXECUTION_ORIGIN,
    STAGE07_EVIDENCE_CONTRACT_VERSION,
    STAGE07_EVIDENCE_MANIFEST_NAME,
    STAGE07_EVIDENCE_PROFILE_VERSION,
    STAGE07_EVIDENCE_SCHEMA_VERSION,
    STRUCTURAL_WARNINGS_NOT_EVALUATED,
    STRUCTURAL_WARNINGS_PRESENT,
    _output_artifacts as _stage07_output_artifacts,
    stage07_evidence_schema,
)
from .s07_parsing import Stage07ValidationError


STAGE08_CONTRACT_VERSION = "stage08_address_evidence_projection_contract_v1"
STAGE08_PROFILE_VERSION = "stage08_address_evidence_projection_profile_v1"
STAGE08_SCHEMA_BUNDLE_VERSION = "stage08_address_evidence_projection_schema_v1"
STAGE08_SEMANTIC_TAXONOMY_VERSION = "stage08_semantic_classification_v1"
STAGE08_LABEL_MAPPING_VERSION = "stage08_libpostal_label_mapping_v1"
STAGE08_OCCURRENCE_VIEW_VERSION = "stage08_representation_occurrence_view_v1"
STAGE08_LOGICAL_ENCODING_VERSION = "stage08_address_evidence_logical_encoding_v1"
STAGE08_VALIDATION_VERSION = "stage08_address_evidence_validation_v1"
STAGE08_MANIFEST_VERSION = "stage08_address_evidence_manifest_v1"

CANDIDATE_SCHEMA_VERSION = "stage08_candidate_evidence_schema_v1"
COMPONENT_SCHEMA_VERSION = "stage08_parser_component_evidence_schema_v1"
SOURCE_MAP_SCHEMA_VERSION = "stage08_source_candidate_map_schema_v1"
OCCURRENCE_SCHEMA_VERSION = "stage08_representation_occurrence_schema_v1"

STAGE08_MANIFEST_NAME = "stage08_address_evidence_manifest.json"
STAGE08_SUCCESS_NAME = "_SUCCESS.json"
STAGE08_IN_PROGRESS_NAME = "_IN_PROGRESS"
CANDIDATE_DIRECTORY = "candidate_evidence/data"
COMPONENT_DIRECTORY = "parser_component_evidence/data"
SOURCE_MAP_DIRECTORY = "source_candidate_map/data"
MAPPING_METADATA_PATH = "metadata/stage08_libpostal_label_mapping_v1.json"
SCHEMA_METADATA_PATH = "metadata/stage08_schema_contract_v1.json"

SOURCE_VALUE = "SOURCE_VALUE"
SOURCE_LINEAGE = "SOURCE_LINEAGE"
UPSTREAM_DERIVED_REPRESENTATION = "UPSTREAM_DERIVED_REPRESENTATION"
TRUSTED_SOURCE_CONTEXT = "TRUSTED_SOURCE_CONTEXT"
PARSER_TECHNICAL_PROVENANCE = "PARSER_TECHNICAL_PROVENANCE"
PARSER_EVIDENCE = "PARSER_EVIDENCE"
STRUCTURAL_DIAGNOSTIC = "STRUCTURAL_DIAGNOSTIC"
MECHANICAL_INDEX = "MECHANICAL_INDEX"
ALLOWED_SEMANTIC_CLASSES = (
    SOURCE_VALUE,
    SOURCE_LINEAGE,
    UPSTREAM_DERIVED_REPRESENTATION,
    TRUSTED_SOURCE_CONTEXT,
    PARSER_TECHNICAL_PROVENANCE,
    PARSER_EVIDENCE,
    STRUCTURAL_DIAGNOSTIC,
    MECHANICAL_INDEX,
)
PROHIBITED_OUTPUT_CLASSES = (
    "HYPOTHESIS",
    "REFERENCE_EVIDENCE",
    "GEOCODER_RESULT",
    "ACCEPTED_MATCH",
)

COMPONENT_INDEX_EMITTED = "COMPONENT_INDEX_EMITTED"
COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL = (
    "COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL"
)
COMPONENT_INDEX_EMPTY = "COMPONENT_INDEX_EMPTY"
COMPONENT_INDEX_STATUSES = (
    COMPONENT_INDEX_EMITTED,
    COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL,
    COMPONENT_INDEX_EMPTY,
)
MAPPED_DEFINED_LABEL = "MAPPED_DEFINED_LABEL"
UNMAPPED_LABEL = "UNMAPPED_LABEL"
LABEL_MAPPING_STATUSES = (MAPPED_DEFINED_LABEL, UNMAPPED_LABEL)
PRESENT = "PRESENT"
ABSENT = "ABSENT"
REPRESENTATION_STATUSES = (PRESENT, ABSENT)
STANDARD = "STANDARD"
NATIVE = "NATIVE"
BOTH = "BOTH"
REPRESENTATION_SCOPES = (STANDARD, NATIVE, BOTH)

LIBPOSTAL_SOURCE_COMMIT = "25099c506612b34b23b1bfe286ca6321fcf06f35"
LIBPOSTAL_SOURCE_README_SHA256 = (
    "14b9589f17f2cd88b2972d89bd98b463ed598885ec9b8778b11a8a128d7d43cb"
)
LIBPOSTAL_LABEL_MAPPING: Mapping[str, str] = {
    "house": "PARSER_HOUSE",
    "category": "PARSER_CATEGORY",
    "near": "PARSER_NEAR",
    "house_number": "PARSER_HOUSE_NUMBER",
    "road": "PARSER_ROAD",
    "unit": "PARSER_UNIT",
    "level": "PARSER_LEVEL",
    "staircase": "PARSER_STAIRCASE",
    "entrance": "PARSER_ENTRANCE",
    "po_box": "PARSER_PO_BOX",
    "postcode": "PARSER_POSTCODE",
    "suburb": "PARSER_SUBURB",
    "city_district": "PARSER_CITY_DISTRICT",
    "city": "PARSER_CITY",
    "island": "PARSER_ISLAND",
    "state_district": "PARSER_STATE_DISTRICT",
    "state": "PARSER_STATE",
    "country_region": "PARSER_COUNTRY_REGION",
    "country": "PARSER_COUNTRY",
    "world_region": "PARSER_WORLD_REGION",
}

REPRESENTATION_OCCURRENCE_SQL = """SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'STANDARD'::VARCHAR AS stage08_representation,
  0::UTINYINT AS stage08_representation_ordinal,
  stage06_standard_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_standard_representation_status = 'PRESENT'
UNION ALL
SELECT
  stage08_source_row_ordinal,
  stable_source_row_id_v1,
  'NATIVE'::VARCHAR AS stage08_representation,
  1::UTINYINT AS stage08_representation_ordinal,
  stage06_native_exact_candidate_id AS stage06_exact_candidate_id
FROM source_candidate_map
WHERE stage08_native_representation_status = 'PRESENT'
ORDER BY stage08_source_row_ordinal, stage08_representation_ordinal"""

ACCEPTED_STAGE07_MANIFEST_SHA256 = (
    "f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266"
)
ACCEPTED_STAGE07_CONTRACT_FINGERPRINT = (
    "c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4"
)
ACCEPTED_STAGE07_SCHEMA_FINGERPRINT = (
    "b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2"
)
ACCEPTED_STAGE07_LOGICAL_DATASET_SHA256 = (
    "0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530"
)
ACCEPTED_PARSER_BUNDLE_FINGERPRINT = (
    "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
)
ACCEPTED_STAGE06_MANIFEST_SHA256 = (
    "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
)
ACCEPTED_STAGE06_SCHEMA_FINGERPRINT = (
    "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
)
ACCEPTED_STAGE06_LOGICAL_DATASET_SHA256 = (
    "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
)
ACCEPTED_STAGE06_ROW_MAP_LOGICAL_SHA256 = (
    "1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1"
)
ACCEPTED_STAGE06_INPUT_BINDING_SHA256 = (
    "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_MEMORY_LIMIT_RE = re.compile(r"^[1-9][0-9]*(?:MB|GB)$")
_CONTRACT_DOMAIN = b"SAFE_STAGE08_ADDRESS_EVIDENCE_CONTRACT_V1"
_MAPPING_DOMAIN = b"SAFE_STAGE08_LIBPOSTAL_LABEL_MAPPING_V1"
_SCHEMA_DOMAIN = b"SAFE_STAGE08_ARROW_SCHEMA_V1"
_SCHEMA_BUNDLE_DOMAIN = b"SAFE_STAGE08_SCHEMA_BUNDLE_V1"
_CANDIDATE_LOGICAL_DOMAIN = b"SAFE_STAGE08_CANDIDATE_EVIDENCE_LOGICAL_V1"
_COMPONENT_LOGICAL_DOMAIN = b"SAFE_STAGE08_COMPONENT_EVIDENCE_LOGICAL_V1"
_SOURCE_MAP_LOGICAL_DOMAIN = b"SAFE_STAGE08_SOURCE_CANDIDATE_MAP_LOGICAL_V1"
_OCCURRENCE_LOGICAL_DOMAIN = b"SAFE_STAGE08_REPRESENTATION_OCCURRENCE_LOGICAL_V1"
_DATASET_LOGICAL_DOMAIN = b"SAFE_STAGE08_ADDRESS_EVIDENCE_DATASET_V1"
_SEMANTIC_METADATA_KEY = b"stage08_semantic_class"
_FORBIDDEN_FIELD_FRAGMENTS = (
    "component_readiness",
    "components_ready",
    "components_abstain",
    "confidence",
    "correctness",
    "verified_component",
    "source_truth",
    "accepted_match",
    "hypothesis",
    "geocoder",
    "coordinate",
    "validity",
    "score",
)

SOURCE_COPY_FIELDS = (
    "id",
    "source_file",
    "source_logical_record_number",
    "stable_source_row_id_v1",
    "source_file_sha256",
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
    "stage03_clean_postcode",
    "stage03_clean_city",
    "stage03_clean_region_in_country",
    "stage03_clean_country_iso_code",
    "stage04_lower_postcode",
    "stage04_lower_city",
    "stage04_lower_region_in_country",
    "stage04_lower_country_iso_code",
    "stage06_standard_exact_candidate_id",
    "stage06_native_exact_candidate_id",
)


class Stage08ValidationError(RuntimeError):
    """Privacy-safe fail-closed Stage 8 error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage08ValidationError(code, detail)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest_bytes(value: str) -> bytes:
    if _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_FINGERPRINT", "A Stage 8 fingerprint is malformed")
    return bytes.fromhex(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage08ValidationError(
            code, "A controlled JSON file is malformed"
        ) from error
    if not isinstance(value, dict):
        _fail(code, "A controlled JSON value is not an object")
    return cast(dict[str, Any], value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_runtime() -> None:
    expected_python = ".".join(str(value) for value in EXPECTED_PYTHON_VERSION)
    if platform.python_version() != expected_python:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not pinned")
    if pa.__version__ != EXPECTED_PYARROW_VERSION or duckdb.__version__ != "1.5.5":
        _fail("RUNTIME_VERSION_MISMATCH", "Arrow/DuckDB runtime is not pinned")


def _field(
    name: str, data_type: pa.DataType, nullable: bool, semantic: str
) -> pa.Field:
    if semantic not in ALLOWED_SEMANTIC_CLASSES:
        _fail("SEMANTIC_CLASS_INVALID", "A Stage 8 semantic class differs")
    return pa.field(
        name,
        data_type,
        nullable=nullable,
        metadata={_SEMANTIC_METADATA_KEY: semantic.encode("ascii")},
    )


_CANDIDATE_SEMANTIC_CLASSES: Mapping[str, str] = {
    "stage06_exact_candidate_id": UPSTREAM_DERIVED_REPRESENTATION,
    "stage06_candidate_lower": UPSTREAM_DERIVED_REPRESENTATION,
    "stage06_occurrence_count": SOURCE_LINEAGE,
    "stage06_standard_occurrence_count": SOURCE_LINEAGE,
    "stage06_native_occurrence_count": SOURCE_LINEAGE,
    "stage07_country_provenance_status": TRUSTED_SOURCE_CONTEXT,
    "stage07_trusted_country_iso_code": TRUSTED_SOURCE_CONTEXT,
    "stage07_valid_country_occurrence_count": TRUSTED_SOURCE_CONTEXT,
    "stage07_missing_country_occurrence_count": TRUSTED_SOURCE_CONTEXT,
    "stage07_invalid_country_occurrence_count": TRUSTED_SOURCE_CONTEXT,
    "stage07_distinct_valid_country_count": TRUSTED_SOURCE_CONTEXT,
    "stage07_parser_applicability_status": PARSER_TECHNICAL_PROVENANCE,
    "stage07_parse_status": PARSER_TECHNICAL_PROVENANCE,
    "stage07_parser_execution_origin": PARSER_TECHNICAL_PROVENANCE,
    "stage07_libpostal_components": PARSER_EVIDENCE,
    "stage07_structural_warning_status": STRUCTURAL_DIAGNOSTIC,
    "stage07_structural_warning_reason_codes": STRUCTURAL_DIAGNOSTIC,
    "stage07_raw_ordered_substrings": STRUCTURAL_DIAGNOSTIC,
    "stage07_lexical_numeric_stream_equal": STRUCTURAL_DIAGNOSTIC,
    "stage07_internal_boundary_count": STRUCTURAL_DIAGNOSTIC,
    "stage07_internal_single_codepoint_fragment_count": STRUCTURAL_DIAGNOSTIC,
    "stage07_maximum_components_per_lexical_run": STRUCTURAL_DIAGNOSTIC,
    "stage07_adjacent_repeated_label_internal_boundary_count": STRUCTURAL_DIAGNOSTIC,
    "stage07_candidate_lexical_numeric_codepoints": STRUCTURAL_DIAGNOSTIC,
    "stage07_output_lexical_numeric_codepoints": STRUCTURAL_DIAGNOSTIC,
}


def _candidate_base_schema() -> pa.Schema:
    upstream = stage07_evidence_schema()
    if tuple(upstream.names) != tuple(_CANDIDATE_SEMANTIC_CLASSES):
        _fail("UPSTREAM_SCHEMA_DEFINITION_MISMATCH", "Stage 7 field order differs")
    fields = [
        _field(
            item.name,
            item.type,
            item.nullable,
            _CANDIDATE_SEMANTIC_CLASSES[item.name],
        )
        for item in upstream
    ]
    fields.extend(
        (
            _field(
                "stage08_representation_scope", pa.string(), False, MECHANICAL_INDEX
            ),
            _field("stage08_raw_component_count", pa.uint64(), False, MECHANICAL_INDEX),
            _field(
                "stage08_mapped_component_count", pa.uint64(), False, MECHANICAL_INDEX
            ),
            _field(
                "stage08_unmapped_component_count", pa.uint64(), False, MECHANICAL_INDEX
            ),
            _field(
                "stage08_component_index_status", pa.string(), False, MECHANICAL_INDEX
            ),
        )
    )
    return pa.schema(fields)


def _component_base_schema() -> pa.Schema:
    return pa.schema(
        (
            _field(
                "stage06_exact_candidate_id",
                pa.binary(32),
                False,
                UPSTREAM_DERIVED_REPRESENTATION,
            ),
            _field("stage08_component_ordinal", pa.uint64(), False, MECHANICAL_INDEX),
            _field(
                "stage08_raw_libpostal_label", pa.large_string(), False, PARSER_EVIDENCE
            ),
            _field(
                "stage08_raw_libpostal_value", pa.large_string(), False, PARSER_EVIDENCE
            ),
            _field(
                "stage08_label_mapping_status", pa.string(), False, MECHANICAL_INDEX
            ),
            _field(
                "stage08_safe_parser_evidence_component",
                pa.string(),
                True,
                PARSER_EVIDENCE,
            ),
            _field("stage08_evidence_class", pa.string(), False, PARSER_EVIDENCE),
        )
    )


def _source_map_base_schema() -> pa.Schema:
    upstream = row_map_schema()
    by_name = {item.name: item for item in upstream}
    semantic = {
        "id": SOURCE_VALUE,
        "source_file": SOURCE_LINEAGE,
        "source_logical_record_number": SOURCE_LINEAGE,
        "stable_source_row_id_v1": SOURCE_LINEAGE,
        "source_file_sha256": SOURCE_LINEAGE,
        "postcode": SOURCE_VALUE,
        "city": SOURCE_VALUE,
        "region_in_country": SOURCE_VALUE,
        "country_iso_code": SOURCE_VALUE,
        "stage03_clean_postcode": UPSTREAM_DERIVED_REPRESENTATION,
        "stage03_clean_city": UPSTREAM_DERIVED_REPRESENTATION,
        "stage03_clean_region_in_country": UPSTREAM_DERIVED_REPRESENTATION,
        "stage03_clean_country_iso_code": UPSTREAM_DERIVED_REPRESENTATION,
        "stage04_lower_postcode": UPSTREAM_DERIVED_REPRESENTATION,
        "stage04_lower_city": UPSTREAM_DERIVED_REPRESENTATION,
        "stage04_lower_region_in_country": UPSTREAM_DERIVED_REPRESENTATION,
        "stage04_lower_country_iso_code": UPSTREAM_DERIVED_REPRESENTATION,
        "stage06_standard_exact_candidate_id": SOURCE_LINEAGE,
        "stage06_native_exact_candidate_id": SOURCE_LINEAGE,
    }
    fields: list[pa.Field] = []
    for name in SOURCE_COPY_FIELDS[:5]:
        item = by_name[name]
        fields.append(_field(name, item.type, item.nullable, semantic[name]))
    fields.append(
        _field("stage08_source_row_ordinal", pa.uint64(), False, MECHANICAL_INDEX)
    )
    for name in SOURCE_COPY_FIELDS[5:]:
        item = by_name[name]
        fields.append(_field(name, item.type, item.nullable, semantic[name]))
    fields.extend(
        (
            _field(
                "stage08_standard_representation_status",
                pa.string(),
                False,
                MECHANICAL_INDEX,
            ),
            _field(
                "stage08_native_representation_status",
                pa.string(),
                False,
                MECHANICAL_INDEX,
            ),
        )
    )
    return pa.schema(fields)


def _occurrence_base_schema() -> pa.Schema:
    return pa.schema(
        (
            _field("stage08_source_row_ordinal", pa.uint64(), False, MECHANICAL_INDEX),
            _field("stable_source_row_id_v1", pa.binary(32), False, SOURCE_LINEAGE),
            _field("stage08_representation", pa.string(), False, SOURCE_LINEAGE),
            _field(
                "stage08_representation_ordinal", pa.uint8(), False, MECHANICAL_INDEX
            ),
            _field(
                "stage06_exact_candidate_id",
                pa.binary(32),
                False,
                UPSTREAM_DERIVED_REPRESENTATION,
            ),
        )
    )


def _metadata_text(metadata: Mapping[bytes, bytes] | None) -> dict[str, str]:
    return {
        key.decode("ascii"): value.decode("ascii")
        for key, value in sorted((metadata or {}).items())
    }


def _describe_schema(schema: pa.Schema) -> dict[str, object]:
    return {
        "metadata": _metadata_text(schema.metadata),
        "fields": [
            {
                "name": item.name,
                "type": str(item.type),
                "nullable": item.nullable,
                "metadata": _metadata_text(item.metadata),
            }
            for item in schema
        ],
    }


@dataclass(frozen=True, slots=True)
class Stage08InputBinding:
    stage07_contract: str
    stage07_profile: str
    stage07_schema: str
    stage07_contract_fingerprint: str
    stage07_schema_fingerprint: str
    stage07_logical_dataset_sha256: str
    stage07_manifest_sha256: str
    parser_bundle_fingerprint: str
    stage06_contract: str
    stage06_profile: str
    stage06_schema_fingerprint: str
    stage06_logical_dataset_sha256: str
    stage06_row_map_logical_sha256: str
    stage06_input_binding_sha256: str
    stage06_manifest_sha256: str
    candidate_rows: int
    parsed_nonempty_rows: int
    parsed_empty_rows: int
    raw_component_rows: int
    maximum_component_count: int
    maximum_candidate_codepoints: int
    source_rows: int
    occurrence_rows: int
    standard_occurrences: int
    native_occurrences: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def accepted_stage08_input_binding() -> Stage08InputBinding:
    return Stage08InputBinding(
        stage07_contract=STAGE07_EVIDENCE_CONTRACT_VERSION,
        stage07_profile=STAGE07_EVIDENCE_PROFILE_VERSION,
        stage07_schema=STAGE07_EVIDENCE_SCHEMA_VERSION,
        stage07_contract_fingerprint=ACCEPTED_STAGE07_CONTRACT_FINGERPRINT,
        stage07_schema_fingerprint=ACCEPTED_STAGE07_SCHEMA_FINGERPRINT,
        stage07_logical_dataset_sha256=ACCEPTED_STAGE07_LOGICAL_DATASET_SHA256,
        stage07_manifest_sha256=ACCEPTED_STAGE07_MANIFEST_SHA256,
        parser_bundle_fingerprint=ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
        stage06_contract=STAGE06_CONTRACT_VERSION,
        stage06_profile=STAGE06_PROFILE_VERSION,
        stage06_schema_fingerprint=ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
        stage06_logical_dataset_sha256=ACCEPTED_STAGE06_LOGICAL_DATASET_SHA256,
        stage06_row_map_logical_sha256=ACCEPTED_STAGE06_ROW_MAP_LOGICAL_SHA256,
        stage06_input_binding_sha256=ACCEPTED_STAGE06_INPUT_BINDING_SHA256,
        stage06_manifest_sha256=ACCEPTED_STAGE06_MANIFEST_SHA256,
        candidate_rows=51_779,
        parsed_nonempty_rows=51_774,
        parsed_empty_rows=5,
        raw_component_rows=6_106_088,
        maximum_component_count=881_338,
        maximum_candidate_codepoints=25_920_495,
        source_rows=35_000,
        occurrence_rows=69_747,
        standard_occurrences=34_822,
        native_occurrences=34_925,
    )


def validate_stage08_input_binding(
    binding: Stage08InputBinding, *, authoritative_development: bool
) -> None:
    if (
        binding.stage07_contract != STAGE07_EVIDENCE_CONTRACT_VERSION
        or binding.stage07_profile != STAGE07_EVIDENCE_PROFILE_VERSION
        or binding.stage07_schema != STAGE07_EVIDENCE_SCHEMA_VERSION
        or binding.stage06_contract != STAGE06_CONTRACT_VERSION
        or binding.stage06_profile != STAGE06_PROFILE_VERSION
    ):
        _fail("UPSTREAM_CONTRACT_MISMATCH", "An upstream contract/profile differs")
    for value in (
        binding.stage07_contract_fingerprint,
        binding.stage07_schema_fingerprint,
        binding.stage07_logical_dataset_sha256,
        binding.stage07_manifest_sha256,
        binding.parser_bundle_fingerprint,
        binding.stage06_schema_fingerprint,
        binding.stage06_logical_dataset_sha256,
        binding.stage06_row_map_logical_sha256,
        binding.stage06_input_binding_sha256,
        binding.stage06_manifest_sha256,
    ):
        _digest_bytes(value)
    counts = (
        binding.candidate_rows,
        binding.parsed_nonempty_rows,
        binding.parsed_empty_rows,
        binding.raw_component_rows,
        binding.maximum_component_count,
        binding.maximum_candidate_codepoints,
        binding.source_rows,
        binding.occurrence_rows,
        binding.standard_occurrences,
        binding.native_occurrences,
    )
    if any(isinstance(value, bool) or value < 0 for value in counts):
        _fail("INVALID_ROW_COUNT", "An input-binding count is invalid")
    if (
        binding.candidate_rows
        != binding.parsed_nonempty_rows + binding.parsed_empty_rows
        or binding.occurrence_rows
        != binding.standard_occurrences + binding.native_occurrences
        or binding.candidate_rows < 1
        or binding.source_rows < 1
    ):
        _fail("INPUT_TOTALITY_MISMATCH", "Input-binding totals differ")
    if authoritative_development and binding != accepted_stage08_input_binding():
        _fail(
            "AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH",
            "The Stage 8 DEVELOPMENT binding differs",
        )


def stage08_label_mapping_fingerprint() -> str:
    payload = {
        "version": STAGE08_LABEL_MAPPING_VERSION,
        "source_commit": LIBPOSTAL_SOURCE_COMMIT,
        "source_readme_sha256": LIBPOSTAL_SOURCE_README_SHA256,
        "comparison": "CASE_SENSITIVE_EXACT_STRING",
        "mapping": list(LIBPOSTAL_LABEL_MAPPING.items()),
        "unmapped": {
            "status": UNMAPPED_LABEL,
            "safe_component": None,
            "raw_preserved": True,
        },
    }
    digest = hashlib.sha256(_MAPPING_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


def stage08_contract_fingerprint(binding: Stage08InputBinding) -> str:
    validate_stage08_input_binding(binding, authoritative_development=False)
    payload = {
        "contract": STAGE08_CONTRACT_VERSION,
        "profile": STAGE08_PROFILE_VERSION,
        "schema_bundle": STAGE08_SCHEMA_BUNDLE_VERSION,
        "semantic_taxonomy": STAGE08_SEMANTIC_TAXONOMY_VERSION,
        "label_mapping": STAGE08_LABEL_MAPPING_VERSION,
        "label_mapping_fingerprint": stage08_label_mapping_fingerprint(),
        "occurrence_view": STAGE08_OCCURRENCE_VIEW_VERSION,
        "occurrence_view_sql": REPRESENTATION_OCCURRENCE_SQL,
        "logical_encoding": STAGE08_LOGICAL_ENCODING_VERSION,
        "validation": STAGE08_VALIDATION_VERSION,
        "manifest": STAGE08_MANIFEST_VERSION,
        "input_binding": binding.to_dict(),
        "base_schemas": {
            "candidate_evidence": _describe_schema(_candidate_base_schema()),
            "parser_component_evidence": _describe_schema(_component_base_schema()),
            "source_candidate_map": _describe_schema(_source_map_base_schema()),
            "representation_occurrence_v1": _describe_schema(_occurrence_base_schema()),
        },
        "status_vocabularies": {
            "component_index": list(COMPONENT_INDEX_STATUSES),
            "label_mapping": list(LABEL_MAPPING_STATUSES),
            "representation_status": list(REPRESENTATION_STATUSES),
            "representation_scope": list(REPRESENTATION_SCOPES),
        },
        "ordering": {
            "candidate": "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES",
            "component": "ASCENDING_UNSIGNED_CANDIDATE_ID_BYTES_THEN_ORDINAL",
            "source": "EXACT_ACCEPTED_STAGE06_SOURCE_ROW_ORDER",
            "occurrence": "SOURCE_ROW_ORDINAL_THEN_REPRESENTATION_ORDINAL",
        },
        "losslessness": {
            "complete_stage07_row": True,
            "raw_nested_authoritative": True,
            "ordered_long_reversible": True,
            "duplicates_preserved": True,
            "unknown_labels_preserved": True,
            "source_rows_preserved": True,
            "occurrence_map_preserved": True,
        },
        "semantic_trust_fields": False,
        "component_readiness_gate": False,
        "reference_behavior": False,
        "parser_calls": 0,
    }
    digest = hashlib.sha256(_CONTRACT_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


def _schema_metadata(
    relation_schema_version: str,
    binding: Stage08InputBinding,
    contract_fingerprint: str,
) -> Mapping[bytes, bytes]:
    values = {
        "stage08_contract_version": STAGE08_CONTRACT_VERSION,
        "stage08_profile_version": STAGE08_PROFILE_VERSION,
        "stage08_schema_bundle_version": STAGE08_SCHEMA_BUNDLE_VERSION,
        "stage08_relation_schema_version": relation_schema_version,
        "stage08_semantic_taxonomy_version": STAGE08_SEMANTIC_TAXONOMY_VERSION,
        "stage08_label_mapping_version": STAGE08_LABEL_MAPPING_VERSION,
        "stage08_label_mapping_fingerprint": stage08_label_mapping_fingerprint(),
        "stage08_contract_fingerprint": contract_fingerprint,
        "upstream_stage07_manifest_sha256": binding.stage07_manifest_sha256,
        "upstream_stage07_logical_dataset_sha256": (
            binding.stage07_logical_dataset_sha256
        ),
        "upstream_stage06_manifest_sha256": binding.stage06_manifest_sha256,
        "upstream_stage06_row_map_logical_sha256": (
            binding.stage06_row_map_logical_sha256
        ),
        "parser_evidence_is_semantic_truth": "false",
    }
    return {key.encode("ascii"): value.encode("ascii") for key, value in values.items()}


def candidate_evidence_schema(
    binding: Stage08InputBinding | None = None,
) -> pa.Schema:
    current = accepted_stage08_input_binding() if binding is None else binding
    contract = stage08_contract_fingerprint(current)
    return _candidate_base_schema().with_metadata(
        _schema_metadata(CANDIDATE_SCHEMA_VERSION, current, contract)
    )


def parser_component_evidence_schema(
    binding: Stage08InputBinding | None = None,
) -> pa.Schema:
    current = accepted_stage08_input_binding() if binding is None else binding
    contract = stage08_contract_fingerprint(current)
    return _component_base_schema().with_metadata(
        _schema_metadata(COMPONENT_SCHEMA_VERSION, current, contract)
    )


def source_candidate_map_schema(
    binding: Stage08InputBinding | None = None,
) -> pa.Schema:
    current = accepted_stage08_input_binding() if binding is None else binding
    contract = stage08_contract_fingerprint(current)
    return _source_map_base_schema().with_metadata(
        _schema_metadata(SOURCE_MAP_SCHEMA_VERSION, current, contract)
    )


def representation_occurrence_schema(
    binding: Stage08InputBinding | None = None,
) -> pa.Schema:
    current = accepted_stage08_input_binding() if binding is None else binding
    contract = stage08_contract_fingerprint(current)
    return _occurrence_base_schema().with_metadata(
        _schema_metadata(OCCURRENCE_SCHEMA_VERSION, current, contract)
    )


def _schema_fingerprint(version: str, schema: pa.Schema) -> str:
    payload = {"version": version, "schema": _describe_schema(schema)}
    digest = hashlib.sha256(_SCHEMA_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


def stage08_schema_fingerprints(
    binding: Stage08InputBinding | None = None,
) -> dict[str, str]:
    current = accepted_stage08_input_binding() if binding is None else binding
    return {
        "candidate_evidence": _schema_fingerprint(
            CANDIDATE_SCHEMA_VERSION, candidate_evidence_schema(current)
        ),
        "parser_component_evidence": _schema_fingerprint(
            COMPONENT_SCHEMA_VERSION, parser_component_evidence_schema(current)
        ),
        "source_candidate_map": _schema_fingerprint(
            SOURCE_MAP_SCHEMA_VERSION, source_candidate_map_schema(current)
        ),
        "representation_occurrence_v1": _schema_fingerprint(
            OCCURRENCE_SCHEMA_VERSION, representation_occurrence_schema(current)
        ),
    }


def stage08_schema_bundle_fingerprint(
    binding: Stage08InputBinding | None = None,
) -> str:
    current = accepted_stage08_input_binding() if binding is None else binding
    payload = {
        "version": STAGE08_SCHEMA_BUNDLE_VERSION,
        "schemas": stage08_schema_fingerprints(current),
    }
    digest = hashlib.sha256(_SCHEMA_BUNDLE_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)
    return digest.hexdigest()


def _assert_semantic_boundary(*schemas: pa.Schema) -> None:
    for schema in schemas:
        for item in schema:
            semantic = (item.metadata or {}).get(_SEMANTIC_METADATA_KEY)
            if (
                semantic is None
                or semantic.decode("ascii") not in ALLOWED_SEMANTIC_CLASSES
            ):
                _fail("SEMANTIC_CLASS_INVALID", "A field semantic class is absent")
            folded = item.name.casefold()
            if any(fragment in folded for fragment in _FORBIDDEN_FIELD_FRAGMENTS):
                _fail(
                    "SEMANTIC_TRUST_VOCABULARY_PROHIBITED", "A field name is prohibited"
                )


@dataclass(frozen=True, slots=True)
class Stage08Config:
    stage07_output_directory: Path
    stage06_output_directory: Path
    output_directory: Path
    execution_git_sha: str
    binding: Stage08InputBinding = accepted_stage08_input_binding()
    authoritative_development: bool = True
    controlled_execution: bool = True
    input_batch_rows: int = 16
    candidate_output_batch_rows: int = 32
    component_batch_rows: int = 65_536
    target_batch_bytes: int = 128 * 1024 * 1024
    candidate_shard_rows: int = 2_048
    component_shard_rows: int = 500_000
    source_shard_rows: int = 4_096
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        validate_stage08_input_binding(
            self.binding, authoritative_development=self.authoritative_development
        )
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA is malformed")
        for value in (
            self.input_batch_rows,
            self.candidate_output_batch_rows,
            self.component_batch_rows,
            self.target_batch_bytes,
            self.candidate_shard_rows,
            self.component_shard_rows,
            self.source_shard_rows,
        ):
            if isinstance(value, bool) or value < 1:
                _fail("INVALID_BATCH_SIZE", "A bounded Stage 8 size is invalid")
        if _MEMORY_LIMIT_RE.fullmatch(self.duckdb_memory_limit) is None:
            _fail("INVALID_MEMORY_LIMIT", "DuckDB memory limit is malformed")
        if (
            isinstance(self.duckdb_threads, bool)
            or self.duckdb_threads < 1
            or self.duckdb_threads > 64
        ):
            _fail("INVALID_THREAD_COUNT", "DuckDB thread count is invalid")
        _reject_scope_paths(
            self.stage07_output_directory,
            self.stage06_output_directory,
            self.output_directory,
        )
        for key, metadata_value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(metadata_value, str)
                or not metadata_value
                or len(metadata_value) > 128
                or "\x00" in metadata_value
            ):
                _fail("INVALID_OPERATIONAL_METADATA", "Operational metadata differs")


@dataclass(frozen=True, slots=True)
class Stage08ArtifactIdentity:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int | None = None

    def to_dict(self) -> dict[str, str | int]:
        values: dict[str, str | int] = {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }
        if self.row_count is not None:
            values["row_count"] = self.row_count
        return values


@dataclass(frozen=True, slots=True)
class Stage08Outcome:
    output_directory: Path
    manifest_sha256: str
    logical_dataset_sha256: str
    contract_fingerprint: str
    schema_bundle_fingerprint: str
    candidate_rows: int
    component_rows: int
    source_rows: int
    occurrence_rows: int
    metrics: Mapping[str, object]
    publication_validation_milliseconds: int = 0


@dataclass(frozen=True, slots=True)
class _ValidatedInputs:
    stage07_paths: tuple[Path, ...]
    stage06_row_map_paths: tuple[Path, ...]


def _reject_scope_paths(*paths: Path) -> None:
    for path in paths:
        folded_parts = tuple(part.casefold() for part in path.parts)
        if any("holdout" in part for part in folded_parts):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "Stage 8 rejects HOLDOUT paths")
        if any("production" in part for part in folded_parts):
            _fail("PRODUCTION_ACCESS_PROHIBITED", "Stage 8 rejects production paths")


def _require_file(path: Path, code: str) -> None:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage08ValidationError(code, "A required file is unavailable") from error
    if path.is_symlink() or not stat.S_ISREG(status.st_mode):
        _fail(code, "A required path is not a regular file")


def _require_directory(path: Path, code: str) -> None:
    try:
        status = path.stat(follow_symlinks=False)
    except OSError as error:
        raise Stage08ValidationError(
            code, "A required directory is unavailable"
        ) from error
    if path.is_symlink() or not stat.S_ISDIR(status.st_mode):
        _fail(code, "A required path is not a directory")


def _require_mode(path: Path, expected: int, code: str = "PERMISSION_FAILURE") -> None:
    try:
        mode = stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except OSError as error:
        raise Stage08ValidationError(code, "A required mode is unavailable") from error
    if path.is_symlink() or mode != expected:
        _fail(code, "A controlled path is not owner-only")


def _validated_inputs(config: Stage08Config) -> _ValidatedInputs:
    _require_directory(config.stage07_output_directory, "STAGE07_INPUT_INVALID")
    _require_mode(config.stage07_output_directory, 0o700)
    stage07_manifest_path = (
        config.stage07_output_directory / STAGE07_EVIDENCE_MANIFEST_NAME
    )
    _require_file(stage07_manifest_path, "STAGE07_MANIFEST_INVALID")
    _require_mode(stage07_manifest_path, 0o600)
    if _sha256_file(stage07_manifest_path) != config.binding.stage07_manifest_sha256:
        _fail("STAGE07_MANIFEST_SHA256_MISMATCH", "Stage 7 manifest differs")
    stage07_manifest = _load_json(stage07_manifest_path, "STAGE07_MANIFEST_INVALID")
    stage07_scientific = stage07_manifest.get("scientific_identity")
    stage07_physical = stage07_manifest.get("physical_identity")
    if not isinstance(stage07_scientific, dict) or not isinstance(
        stage07_physical, dict
    ):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 identity sections are absent")
    stage07_input_binding = stage07_scientific.get("input_binding")
    if (
        stage07_scientific.get("stage07_contract_version")
        != config.binding.stage07_contract
        or stage07_scientific.get("stage07_profile_version")
        != config.binding.stage07_profile
        or stage07_scientific.get("stage07_schema_version")
        != config.binding.stage07_schema
        or stage07_scientific.get("stage07_contract_fingerprint")
        != config.binding.stage07_contract_fingerprint
        or stage07_scientific.get("stage07_schema_fingerprint")
        != config.binding.stage07_schema_fingerprint
        or stage07_scientific.get("stage07_logical_dataset_sha256_v2")
        != config.binding.stage07_logical_dataset_sha256
        or stage07_scientific.get("candidate_count") != config.binding.candidate_rows
        or not isinstance(stage07_input_binding, dict)
        or stage07_input_binding.get("stage06_manifest_sha256")
        != config.binding.stage06_manifest_sha256
        or stage07_input_binding.get("parser_bundle_fingerprint")
        != config.binding.parser_bundle_fingerprint
    ):
        _fail("STAGE07_INPUT_BINDING_MISMATCH", "Stage 7 scientific identity differs")
    try:
        stage07_artifacts = _stage07_output_artifacts(
            config.stage07_output_directory, stage07_physical
        )
    except Stage07ValidationError as error:
        raise Stage08ValidationError(
            "STAGE07_ARTIFACT_INVALID", "Stage 7 artifact validation failed"
        ) from error
    stage07_success_path = config.stage07_output_directory / "_SUCCESS.json"
    _require_file(stage07_success_path, "STAGE07_TERMINAL_INVALID")
    _require_mode(stage07_success_path, 0o600)
    stage07_success = _load_json(stage07_success_path, "STAGE07_TERMINAL_INVALID")
    if (
        stage07_success.get("manifest_sha256") != config.binding.stage07_manifest_sha256
        or stage07_success.get("logical_dataset_sha256_v2")
        != config.binding.stage07_logical_dataset_sha256
        or stage07_success.get("schema_fingerprint")
        != config.binding.stage07_schema_fingerprint
        or stage07_success.get("candidate_count") != config.binding.candidate_rows
    ):
        _fail("STAGE07_TERMINAL_INVALID", "Stage 7 terminal binding differs")
    stage07_paths = tuple(
        config.stage07_output_directory / item.relative_path
        for item in stage07_artifacts
    )
    if (
        sum(item.row_count for item in stage07_artifacts)
        != config.binding.candidate_rows
    ):
        _fail("STAGE07_INPUT_BINDING_MISMATCH", "Stage 7 artifact row count differs")
    expected_stage07_schema = stage07_evidence_schema()
    for path in stage07_paths:
        reopened = pq.ParquetFile(path, page_checksum_verification=True).schema_arrow
        if not reopened.remove_metadata().equals(expected_stage07_schema):
            _fail("STAGE07_SCHEMA_MISMATCH", "Stage 7 Parquet schema differs")

    _require_directory(config.stage06_output_directory, "STAGE06_INPUT_INVALID")
    _require_mode(config.stage06_output_directory, 0o700)
    stage06_manifest_path = config.stage06_output_directory / "stage06_manifest.json"
    _require_file(stage06_manifest_path, "STAGE06_MANIFEST_INVALID")
    _require_mode(stage06_manifest_path, 0o600)
    if _sha256_file(stage06_manifest_path) != config.binding.stage06_manifest_sha256:
        _fail("STAGE06_MANIFEST_SHA256_MISMATCH", "Stage 6 manifest differs")
    stage06_manifest = _load_json(stage06_manifest_path, "STAGE06_MANIFEST_INVALID")
    stage06_scientific = stage06_manifest.get("scientific_identity")
    stage06_physical = stage06_manifest.get("physical_identity")
    if not isinstance(stage06_scientific, dict) or not isinstance(
        stage06_physical, dict
    ):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 identity sections are absent")
    if (
        stage06_scientific.get("stage06_contract_version")
        != config.binding.stage06_contract
        or stage06_scientific.get("stage06_profile_version")
        != config.binding.stage06_profile
        or stage06_scientific.get("stage06_schema_fingerprint")
        != config.binding.stage06_schema_fingerprint
        or stage06_scientific.get("stage06_logical_dataset_sha256_v1")
        != config.binding.stage06_logical_dataset_sha256
        or stage06_scientific.get("stage06_row_map_logical_sha256_v1")
        != config.binding.stage06_row_map_logical_sha256
        or stage06_physical.get("stage06_input_binding_sha256")
        != config.binding.stage06_input_binding_sha256
        or stage06_scientific.get("source_row_count") != config.binding.source_rows
    ):
        _fail("STAGE06_INPUT_BINDING_MISMATCH", "Stage 6 scientific identity differs")
    try:
        stage06_artifacts: tuple[Stage06ArtifactIdentity, ...] = (
            _stage06_manifest_artifacts(
                config.stage06_output_directory,
                stage06_physical,
                key="row_map_artifacts",
                directory=STAGE06_ROW_MAP_DIRECTORY,
            )
        )
    except Stage06ValidationError as error:
        raise Stage08ValidationError(
            "STAGE06_ARTIFACT_INVALID", "Stage 6 artifact validation failed"
        ) from error
    if sum(item.row_count for item in stage06_artifacts) != config.binding.source_rows:
        _fail("STAGE06_INPUT_BINDING_MISMATCH", "Stage 6 row-map count differs")
    stage06_success_path = config.stage06_output_directory / "_SUCCESS.json"
    _require_file(stage06_success_path, "STAGE06_TERMINAL_INVALID")
    _require_mode(stage06_success_path, 0o600)
    stage06_success = _load_json(stage06_success_path, "STAGE06_TERMINAL_INVALID")
    if (
        stage06_success.get("stage06_manifest_sha256")
        != config.binding.stage06_manifest_sha256
        or stage06_success.get("stage06_logical_dataset_sha256_v1")
        != config.binding.stage06_logical_dataset_sha256
        or stage06_success.get("stage06_schema_fingerprint")
        != config.binding.stage06_schema_fingerprint
        or stage06_success.get("stage06_input_binding_sha256")
        != config.binding.stage06_input_binding_sha256
        or stage06_success.get("source_row_count") != config.binding.source_rows
    ):
        _fail("STAGE06_TERMINAL_INVALID", "Stage 6 terminal binding differs")
    stage06_paths = tuple(
        config.stage06_output_directory / item.relative_path
        for item in stage06_artifacts
    )
    expected_row_map = row_map_schema()
    for path in stage06_paths:
        reopened = pq.ParquetFile(path, page_checksum_verification=True).schema_arrow
        if not reopened.remove_metadata().equals(expected_row_map):
            _fail("STAGE06_SCHEMA_MISMATCH", "Stage 6 row-map schema differs")
    return _ValidatedInputs(
        stage07_paths=stage07_paths,
        stage06_row_map_paths=stage06_paths,
    )


def _iter_batches(
    paths: Sequence[Path], columns: Sequence[str], batch_rows: int
) -> Iterator[pa.RecordBatch]:
    for path in paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        for batch in parquet.iter_batches(batch_size=batch_rows, columns=list(columns)):
            yield batch


def _iter_rows(
    paths: Sequence[Path], columns: Sequence[str], batch_rows: int
) -> Iterator[tuple[pa.RecordBatch, int]]:
    for batch in _iter_batches(paths, columns, batch_rows):
        for index in range(batch.num_rows):
            yield batch, index


class _CanonicalRelationHasher:
    def __init__(
        self, domain: bytes, contract_fingerprint: str, schema: pa.Schema
    ) -> None:
        self._digest = hashlib.sha256(domain)
        self._digest.update(_digest_bytes(contract_fingerprint))
        self._digest.update(
            _digest_bytes(_schema_fingerprint("logical_relation_schema", schema))
        )
        self.row_count = 0

    def _bytes(self, value: bytes) -> None:
        self._digest.update(struct.pack(">Q", len(value)))
        self._digest.update(value)

    def _scalar(self, value: pa.Scalar, data_type: pa.DataType) -> None:
        if not value.is_valid:
            self._digest.update(b"\x00")
            return
        self._digest.update(b"\x01")
        if pa.types.is_string(data_type) or pa.types.is_large_string(data_type):
            raw = value.as_py()
            if not isinstance(raw, str):
                _fail("LOGICAL_ENCODING_FAILURE", "A string scalar is malformed")
            self._bytes(raw.encode("utf-8", errors="strict"))
            return
        if pa.types.is_fixed_size_binary(data_type):
            raw = value.as_py()
            if not isinstance(raw, bytes) or len(raw) != data_type.byte_width:
                _fail("LOGICAL_ENCODING_FAILURE", "A fixed binary scalar is malformed")
            self._bytes(raw)
            return
        if pa.types.is_unsigned_integer(data_type):
            raw = value.as_py()
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                _fail("LOGICAL_ENCODING_FAILURE", "An unsigned scalar is malformed")
            self._digest.update(struct.pack(">Q", raw))
            return
        if pa.types.is_boolean(data_type):
            raw = value.as_py()
            if not isinstance(raw, bool):
                _fail("LOGICAL_ENCODING_FAILURE", "A bool scalar is malformed")
            self._digest.update(b"\x01" if raw else b"\x00")
            return
        if pa.types.is_large_list(data_type) or pa.types.is_list(data_type):
            list_scalar = cast(pa.ListScalar, value)
            child = list_scalar.values
            self._digest.update(struct.pack(">Q", len(child)))
            for child_scalar in child:
                self._scalar(child_scalar, data_type.value_type)
            return
        if pa.types.is_struct(data_type):
            struct_scalar = cast(pa.StructScalar, value)
            for position, child_field in enumerate(data_type):
                self._scalar(struct_scalar[position], child_field.type)
            return
        _fail("LOGICAL_ENCODING_FAILURE", "An unsupported Arrow type was encountered")

    def update_batch(self, batch: pa.RecordBatch) -> None:
        for row_index in range(batch.num_rows):
            self._digest.update(b"\x02")
            for column_index, field in enumerate(batch.schema):
                self._scalar(batch.column(column_index)[row_index], field.type)
            self.row_count += 1

    def update_python_row(self, values: Sequence[object], schema: pa.Schema) -> None:
        if len(values) != len(schema):
            _fail("LOGICAL_ENCODING_FAILURE", "A logical row width differs")
        batch = pa.RecordBatch.from_arrays(
            [
                pa.array((value,), type=field.type)
                for value, field in zip(values, schema)
            ],
            schema=schema,
        )
        self.update_batch(batch)

    def hexdigest(self) -> str:
        result = self._digest.copy()
        result.update(b"\x00ROWS" + struct.pack(">Q", self.row_count))
        return result.hexdigest()


def _dataset_fingerprint(
    *,
    contract: str,
    schema_bundle: str,
    mapping: str,
    candidate: str,
    component: str,
    source: str,
    occurrence: str,
    counts: Sequence[int],
) -> str:
    digest = hashlib.sha256(_DATASET_LOGICAL_DOMAIN)
    for value in (
        contract,
        schema_bundle,
        mapping,
        candidate,
        component,
        source,
        occurrence,
    ):
        digest.update(_digest_bytes(value))
    for count_value in counts:
        digest.update(struct.pack(">Q", count_value))
    return digest.hexdigest()


def _components_for_row(batch: pa.RecordBatch, index: int) -> pa.StructArray:
    position = batch.schema.get_field_index("stage07_libpostal_components")
    scalar = batch.column(position)[index]
    if not scalar.is_valid:
        _fail("RAW_COMPONENT_STRUCTURE_INVALID", "The raw component list is null")
    values = cast(pa.ListScalar, scalar).values
    if not isinstance(values, pa.StructArray) or values.null_count:
        _fail("RAW_COMPONENT_STRUCTURE_INVALID", "The raw component child differs")
    labels = values.field("label")
    raw_values = values.field("value")
    if labels.null_count or raw_values.null_count:
        _fail("RAW_COMPONENT_STRUCTURE_INVALID", "A raw component member is null")
    return values


def _mapping_arrays(labels: pa.Array) -> tuple[pa.Array, pa.Array, int]:
    mapped_values: list[str | None] = []
    statuses: list[str] = []
    unmapped = 0
    for scalar in labels:
        raw = scalar.as_py()
        if not isinstance(raw, str):
            _fail("RAW_COMPONENT_STRUCTURE_INVALID", "A raw label is not text")
        mapped = LIBPOSTAL_LABEL_MAPPING.get(raw)
        mapped_values.append(mapped)
        if mapped is None:
            statuses.append(UNMAPPED_LABEL)
            unmapped += 1
        else:
            statuses.append(MAPPED_DEFINED_LABEL)
    return (
        pa.array(statuses, type=pa.string()),
        pa.array(mapped_values, type=pa.string()),
        unmapped,
    )


def _component_batch(
    candidate_id: bytes,
    ordinal: int,
    values: pa.StructArray,
    schema: pa.Schema,
) -> tuple[pa.RecordBatch, int]:
    labels = values.field("label")
    raw_values = values.field("value")
    statuses, mapped, unmapped = _mapping_arrays(labels)
    length = len(values)
    arrays = [
        pa.array((candidate_id for _ in range(length)), type=pa.binary(32)),
        pa.array(range(ordinal, ordinal + length), type=pa.uint64()),
        labels,
        raw_values,
        statuses,
        mapped,
        pa.array((PARSER_EVIDENCE for _ in range(length)), type=pa.string()),
    ]
    return pa.RecordBatch.from_arrays(arrays, schema=schema), unmapped


def _representation_scope(standard_count: int, native_count: int) -> str:
    if standard_count > 0 and native_count > 0:
        return BOTH
    if standard_count > 0 and native_count == 0:
        return STANDARD
    if native_count > 0 and standard_count == 0:
        return NATIVE
    _fail("CANDIDATE_OCCURRENCE_INVALID", "A candidate has no representation scope")


def _validate_country_state(batch: pa.RecordBatch, index: int) -> None:
    def value(name: str) -> object:
        return batch.column(batch.schema.get_field_index(name))[index].as_py()

    occurrence = value("stage06_occurrence_count")
    valid = value("stage07_valid_country_occurrence_count")
    missing = value("stage07_missing_country_occurrence_count")
    invalid = value("stage07_invalid_country_occurrence_count")
    distinct = value("stage07_distinct_valid_country_count")
    status = value("stage07_country_provenance_status")
    trusted = value("stage07_trusted_country_iso_code")
    applicability = value("stage07_parser_applicability_status")
    if (
        any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in (occurrence, valid, missing, invalid, distinct)
        )
        or status not in COUNTRY_PROVENANCE_STATUSES
    ):
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Country provenance counts differ")
    occurrence_count = cast(int, occurrence)
    valid_count = cast(int, valid)
    missing_count = cast(int, missing)
    invalid_count = cast(int, invalid)
    distinct_count = cast(int, distinct)
    status_value = cast(str, status)
    if valid_count + missing_count + invalid_count != occurrence_count:
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Country provenance counts differ")
    applicability_by_status: Mapping[str, str] = {
        COUNTRY_UNANIMOUS_VALID: PARSER_ELIGIBLE_COUNTRY,
        COUNTRY_MISSING: PARSER_ELIGIBILITY_MISSING_COUNTRY,
        COUNTRY_PARTIAL: PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
        COUNTRY_INVALID: PARSER_ELIGIBILITY_INVALID_COUNTRY,
        COUNTRY_CONFLICTING: PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    }
    expected_applicability = applicability_by_status[status_value]
    if applicability != expected_applicability:
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Parser applicability differs")
    if status == COUNTRY_UNANIMOUS_VALID:
        if (
            not isinstance(trusted, str)
            or not trusted
            or valid_count != occurrence_count
            or missing_count != 0
            or invalid_count != 0
            or distinct_count != 1
        ):
            _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Trusted country differs")
    elif trusted is not None:
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Unresolved country is non-null")
    if status == COUNTRY_MISSING and not (
        missing_count == occurrence_count
        and valid_count == invalid_count == distinct_count == 0
    ):
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Missing-country evidence differs")
    if status == COUNTRY_PARTIAL and not (
        valid_count > 0 and missing_count + invalid_count > 0 and distinct_count == 1
    ):
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Partial-country evidence differs")
    if status == COUNTRY_INVALID and not (
        invalid_count > 0 and valid_count == distinct_count == 0
    ):
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Invalid-country evidence differs")
    if status == COUNTRY_CONFLICTING and distinct_count < 2:
        _fail("COUNTRY_PROVENANCE_INCONSISTENT", "Conflicting-country evidence differs")


def _validate_stage07_row(
    batch: pa.RecordBatch, index: int, components: pa.StructArray
) -> None:
    def value(name: str) -> object:
        return batch.column(batch.schema.get_field_index(name))[index].as_py()

    candidate_id = value("stage06_exact_candidate_id")
    candidate = value("stage06_candidate_lower")
    total = value("stage06_occurrence_count")
    standard = value("stage06_standard_occurrence_count")
    native = value("stage06_native_occurrence_count")
    technical = value("stage07_parse_status")
    origin = value("stage07_parser_execution_origin")
    warning = value("stage07_structural_warning_status")
    applicability = value("stage07_parser_applicability_status")
    reasons = value("stage07_structural_warning_reason_codes")
    if (
        not isinstance(candidate_id, bytes)
        or len(candidate_id) != 32
        or not isinstance(candidate, str)
        or not candidate
        or any(
            isinstance(item, bool) or not isinstance(item, int)
            for item in (total, standard, native)
        )
        or origin != PARSER_EXECUTION_ORIGIN
        or technical not in (PARSED_NONEMPTY, PARSED_EMPTY)
    ):
        _fail("STAGE07_ROW_INCONSISTENT", "A Stage 7 candidate row differs")
    total_count = cast(int, total)
    standard_count = cast(int, standard)
    native_count = cast(int, native)
    if total_count <= 0 or total_count != standard_count + native_count:
        _fail("STAGE07_ROW_INCONSISTENT", "Candidate occurrence counts differ")
    if (technical == PARSED_NONEMPTY) != (len(components) > 0):
        _fail("TECHNICAL_STATUS_MISMATCH", "Technical status/list differs")
    if not isinstance(reasons, list) or not all(
        isinstance(item, str) for item in reasons
    ):
        _fail("WARNING_FIELD_INCONSISTENT", "Warning reasons differ")
    signal_names = (
        "stage07_raw_ordered_substrings",
        "stage07_lexical_numeric_stream_equal",
        "stage07_internal_boundary_count",
        "stage07_internal_single_codepoint_fragment_count",
        "stage07_maximum_components_per_lexical_run",
        "stage07_adjacent_repeated_label_internal_boundary_count",
        "stage07_candidate_lexical_numeric_codepoints",
        "stage07_output_lexical_numeric_codepoints",
    )
    signals = tuple(value(name) for name in signal_names)
    if applicability != PARSER_ELIGIBLE_COUNTRY:
        if (
            warning != STRUCTURAL_WARNINGS_NOT_EVALUATED
            or reasons
            or any(item is not None for item in signals)
        ):
            _fail("WARNING_FIELD_INCONSISTENT", "Unresolved warning state differs")
    elif technical == PARSED_EMPTY:
        if (
            warning != STRUCTURAL_WARNINGS_PRESENT
            or reasons != ["PARSED_EMPTY_NO_COMPONENTS"]
            or any(item is not None for item in signals)
        ):
            _fail("WARNING_FIELD_INCONSISTENT", "Parsed-empty warning state differs")
    elif warning not in (
        STRUCTURAL_WARNINGS_PRESENT,
        NO_STRUCTURAL_WARNINGS_DETECTED,
    ) or any(item is None for item in signals):
        _fail("WARNING_FIELD_INCONSISTENT", "Evaluated warning state differs")
    _validate_country_state(batch, index)


class _RelationWriter:
    def __init__(
        self,
        *,
        root: Path,
        directory: str,
        schema: pa.Schema,
        shard_rows: int,
        row_group_rows: int,
        target_batch_bytes: int,
    ) -> None:
        self.root = root
        self.relative_directory = directory
        self.directory = root / directory
        self.directory.mkdir(parents=True, mode=0o700)
        self.directory.chmod(0o700)
        self.directory.parent.chmod(0o700)
        self.schema = schema
        self.shard_rows = shard_rows
        self.row_group_rows = row_group_rows
        self.target_batch_bytes = target_batch_bytes
        self.artifacts: list[Stage08ArtifactIdentity] = []
        self._writer: pq.ParquetWriter | None = None
        self._path: Path | None = None
        self._shard_number = 0
        self._written_rows = 0
        self._pending: list[pa.RecordBatch] = []
        self._pending_rows = 0
        self._pending_bytes = 0

    def _start(self) -> None:
        self._shard_number += 1
        self._written_rows = 0
        self._path = self.directory / f"part-{self._shard_number:06d}.parquet"
        self._writer = pq.ParquetWriter(
            self._path,
            self.schema,
            compression="zstd",
            use_dictionary=False,
            write_statistics=True,
            write_page_checksum=True,
            data_page_size=1024 * 1024,
            write_batch_size=min(self.row_group_rows, 65_536),
        )

    def _flush(self) -> None:
        if not self._pending:
            return
        if self._writer is None:
            self._start()
        assert self._writer is not None
        table = pa.Table.from_batches(self._pending, schema=self.schema)
        self._writer.write_table(
            table, row_group_size=min(self.row_group_rows, table.num_rows)
        )
        self._written_rows += table.num_rows
        self._pending = []
        self._pending_rows = 0
        self._pending_bytes = 0

    def _close(self) -> None:
        if self._writer is None or self._path is None:
            return
        self._flush()
        self._writer.close()
        self._path.chmod(0o600)
        self.artifacts.append(
            Stage08ArtifactIdentity(
                relative_path=self._path.relative_to(self.root).as_posix(),
                size_bytes=self._path.stat(follow_symlinks=False).st_size,
                sha256=_sha256_file(self._path),
                row_count=self._written_rows,
            )
        )
        self._writer = None
        self._path = None

    def write(self, batch: pa.RecordBatch) -> None:
        if not batch.schema.equals(self.schema, check_metadata=True):
            _fail("OUTPUT_SCHEMA_MISMATCH", "A writer batch schema differs")
        offset = 0
        while offset < batch.num_rows:
            if self._writer is None:
                self._start()
            capacity = self.shard_rows - self._written_rows - self._pending_rows
            if capacity <= 0:
                self._close()
                continue
            length = min(capacity, batch.num_rows - offset)
            piece = batch.slice(offset, length)
            self._pending.append(piece)
            self._pending_rows += length
            self._pending_bytes += piece.nbytes
            offset += length
            if (
                self._pending_rows >= self.row_group_rows
                or self._pending_bytes >= self.target_batch_bytes
                or self._written_rows + self._pending_rows == self.shard_rows
            ):
                self._flush()
            if self._written_rows == self.shard_rows:
                self._close()

    def finish(self) -> tuple[Stage08ArtifactIdentity, ...]:
        if self._writer is None and not self.artifacts:
            self._start()
        self._close()
        return tuple(self.artifacts)


def _artifact_identity(root: Path, relative_path: str) -> Stage08ArtifactIdentity:
    path = root / relative_path
    return Stage08ArtifactIdentity(
        relative_path=relative_path,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
    )


def _write_json_exclusive(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                value,
                stream,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    path.chmod(0o600)


def _mapping_payload() -> dict[str, object]:
    return {
        "version": STAGE08_LABEL_MAPPING_VERSION,
        "fingerprint": stage08_label_mapping_fingerprint(),
        "libpostal_source_commit": LIBPOSTAL_SOURCE_COMMIT,
        "libpostal_source_readme_sha256": LIBPOSTAL_SOURCE_README_SHA256,
        "comparison": "CASE_SENSITIVE_EXACT_STRING",
        "mapping": dict(LIBPOSTAL_LABEL_MAPPING),
        "unmapped_policy": {
            "mapping_status": UNMAPPED_LABEL,
            "safe_component": None,
            "raw_label_value_and_ordinal_retained": True,
        },
        "semantic_class": PARSER_EVIDENCE,
        "semantic_truth_claim": False,
    }


def _schema_contract_payload(binding: Stage08InputBinding) -> dict[str, object]:
    schemas = {
        "candidate_evidence": candidate_evidence_schema(binding),
        "parser_component_evidence": parser_component_evidence_schema(binding),
        "source_candidate_map": source_candidate_map_schema(binding),
        "representation_occurrence_v1": representation_occurrence_schema(binding),
    }
    return {
        "version": STAGE08_SCHEMA_BUNDLE_VERSION,
        "contract": STAGE08_CONTRACT_VERSION,
        "profile": STAGE08_PROFILE_VERSION,
        "contract_fingerprint": stage08_contract_fingerprint(binding),
        "schema_bundle_fingerprint": stage08_schema_bundle_fingerprint(binding),
        "schema_fingerprints": stage08_schema_fingerprints(binding),
        "semantic_taxonomy": STAGE08_SEMANTIC_TAXONOMY_VERSION,
        "allowed_semantic_classes": list(ALLOWED_SEMANTIC_CLASSES),
        "prohibited_output_classes": list(PROHIBITED_OUTPUT_CLASSES),
        "schemas": {name: _describe_schema(schema) for name, schema in schemas.items()},
        "input_binding": binding.to_dict(),
        "occurrence_view": {
            "version": STAGE08_OCCURRENCE_VIEW_VERSION,
            "materialized": False,
            "canonical_sql": REPRESENTATION_OCCURRENCE_SQL,
        },
    }


def _duckdb_paths(paths: Sequence[Path]) -> str:
    escaped = ["'" + str(path).replace("'", "''") + "'" for path in paths]
    return "[" + ",".join(escaped) + "]"


def _duckdb_reconciliation(
    *,
    candidate_paths: Sequence[Path],
    component_paths: Sequence[Path],
    source_paths: Sequence[Path],
    config: Stage08Config,
    temporary_parent: Path,
) -> dict[str, object]:
    temporary = temporary_parent / f".stage08_duckdb_{os.getpid()}_{time.time_ns()}"
    temporary.mkdir(mode=0o700)
    connection = duckdb.connect(":memory:")
    try:

        def fetch_one(query: str) -> tuple[Any, ...]:
            result = connection.execute(query).fetchone()
            if result is None:
                _fail("DUCKDB_RECONCILIATION_FAILURE", "An aggregate row is absent")
            return result

        connection.execute(f"SET memory_limit='{config.duckdb_memory_limit}'")
        connection.execute(f"SET threads={config.duckdb_threads}")
        escaped_temporary = str(temporary).replace("'", "''")
        connection.execute(f"SET temp_directory='{escaped_temporary}'")
        connection.execute(
            "CREATE TEMP VIEW candidate_evidence AS SELECT * FROM read_parquet("
            + _duckdb_paths(candidate_paths)
            + ")"
        )
        connection.execute(
            "CREATE TEMP VIEW parser_component_evidence AS SELECT * FROM read_parquet("
            + _duckdb_paths(component_paths)
            + ")"
        )
        connection.execute(
            "CREATE TEMP VIEW source_candidate_map AS SELECT * FROM read_parquet("
            + _duckdb_paths(source_paths)
            + ")"
        )
        candidate_count, candidate_distinct = fetch_one(
            "SELECT count(*), count(DISTINCT stage06_exact_candidate_id) FROM candidate_evidence"
        )
        source_count, source_distinct, ordinal_distinct, min_ordinal, max_ordinal = (
            fetch_one(
                "SELECT count(*), count(DISTINCT stable_source_row_id_v1), "
                "count(DISTINCT stage08_source_row_ordinal), "
                "min(stage08_source_row_ordinal), max(stage08_source_row_ordinal) "
                "FROM source_candidate_map"
            )
        )
        component_count, component_key_distinct = fetch_one(
            "SELECT count(*), count(DISTINCT (stage06_exact_candidate_id, stage08_component_ordinal)) "
            "FROM parser_component_evidence"
        )
        dangling_components = fetch_one(
            "SELECT count(*) FROM parser_component_evidence p LEFT JOIN candidate_evidence c "
            "USING (stage06_exact_candidate_id) WHERE c.stage06_exact_candidate_id IS NULL"
        )[0]
        occurrence = fetch_one(
            "WITH occurrence AS ("
            "SELECT stage06_standard_exact_candidate_id AS candidate_id, 'STANDARD' AS rep "
            "FROM source_candidate_map WHERE stage08_standard_representation_status='PRESENT' "
            "UNION ALL "
            "SELECT stage06_native_exact_candidate_id AS candidate_id, 'NATIVE' AS rep "
            "FROM source_candidate_map WHERE stage08_native_representation_status='PRESENT') "
            "SELECT count(*), count(*) FILTER (WHERE rep='STANDARD'), "
            "count(*) FILTER (WHERE rep='NATIVE') FROM occurrence"
        )
        occurrence_mismatches = fetch_one(
            "WITH occurrence AS ("
            "SELECT stage06_standard_exact_candidate_id AS candidate_id, 1 AS s, 0 AS n "
            "FROM source_candidate_map WHERE stage08_standard_representation_status='PRESENT' "
            "UNION ALL "
            "SELECT stage06_native_exact_candidate_id AS candidate_id, 0 AS s, 1 AS n "
            "FROM source_candidate_map WHERE stage08_native_representation_status='PRESENT'), "
            "counts AS (SELECT candidate_id, count(*) total, sum(s) standard, sum(n) native "
            "FROM occurrence GROUP BY candidate_id) "
            "SELECT count(*) FROM candidate_evidence c FULL OUTER JOIN counts o "
            "ON c.stage06_exact_candidate_id=o.candidate_id WHERE "
            "c.stage06_exact_candidate_id IS NULL OR o.candidate_id IS NULL OR "
            "c.stage06_occurrence_count<>o.total OR "
            "c.stage06_standard_occurrence_count<>o.standard OR "
            "c.stage06_native_occurrence_count<>o.native"
        )[0]
        component_count_mismatches = fetch_one(
            "WITH counts AS (SELECT stage06_exact_candidate_id candidate_id, count(*) total, "
            "count(*) FILTER (WHERE stage08_label_mapping_status='MAPPED_DEFINED_LABEL') mapped, "
            "count(*) FILTER (WHERE stage08_label_mapping_status='UNMAPPED_LABEL') unmapped "
            "FROM parser_component_evidence GROUP BY stage06_exact_candidate_id) "
            "SELECT count(*) FROM candidate_evidence c LEFT JOIN counts x "
            "ON c.stage06_exact_candidate_id=x.candidate_id WHERE "
            "c.stage08_raw_component_count<>coalesce(x.total,0) OR "
            "c.stage08_mapped_component_count<>coalesce(x.mapped,0) OR "
            "c.stage08_unmapped_component_count<>coalesce(x.unmapped,0)"
        )[0]
        mapping = fetch_one(
            "SELECT count(*) FILTER (WHERE stage08_label_mapping_status='MAPPED_DEFINED_LABEL'), "
            "count(*) FILTER (WHERE stage08_label_mapping_status='UNMAPPED_LABEL'), "
            "count(DISTINCT stage08_raw_libpostal_label) FILTER "
            "(WHERE stage08_label_mapping_status='UNMAPPED_LABEL') "
            "FROM parser_component_evidence"
        )
        return {
            "candidate_rows": int(candidate_count),
            "candidate_distinct_ids": int(candidate_distinct),
            "source_rows": int(source_count),
            "source_distinct_ids": int(source_distinct),
            "source_distinct_ordinals": int(ordinal_distinct),
            "source_min_ordinal": None if min_ordinal is None else int(min_ordinal),
            "source_max_ordinal": None if max_ordinal is None else int(max_ordinal),
            "component_rows": int(component_count),
            "component_distinct_keys": int(component_key_distinct),
            "dangling_component_rows": int(dangling_components),
            "occurrence_rows": int(occurrence[0]),
            "standard_occurrences": int(occurrence[1]),
            "native_occurrences": int(occurrence[2]),
            "occurrence_count_mismatches": int(occurrence_mismatches),
            "component_count_mismatches": int(component_count_mismatches),
            "mapped_component_rows": int(mapping[0]),
            "unmapped_component_rows": int(mapping[1]),
            "distinct_unmapped_labels": int(mapping[2]),
        }
    except duckdb.Error as error:
        raise Stage08ValidationError(
            "DUCKDB_RECONCILIATION_FAILURE", "Bounded reconciliation failed"
        ) from error
    finally:
        connection.close()
        shutil.rmtree(temporary, ignore_errors=True)


def _topology(root: Path) -> tuple[set[str], set[str]]:
    directories: set[str] = set()
    files: set[str] = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        status = path.stat(follow_symlinks=False)
        if path.is_symlink():
            _fail("TOPOLOGY_FAILURE", "A publication symlink is prohibited")
        if stat.S_ISDIR(status.st_mode):
            directories.add(relative)
            _require_mode(path, 0o700)
        elif stat.S_ISREG(status.st_mode):
            files.add(relative)
            _require_mode(path, 0o600)
        else:
            _fail("TOPOLOGY_FAILURE", "A publication path type is prohibited")
    return directories, files


def _output_artifacts(
    root: Path,
    raw: object,
    *,
    directory: str,
    require_nonempty: bool = True,
) -> tuple[Stage08ArtifactIdentity, ...]:
    if not isinstance(raw, list) or (require_nonempty and not raw):
        _fail("MANIFEST_INVALID", "An artifact list is absent")
    artifacts: list[Stage08ArtifactIdentity] = []
    for sequence, value in enumerate(raw, start=1):
        if not isinstance(value, dict):
            _fail("MANIFEST_INVALID", "An artifact entry is malformed")
        try:
            item = Stage08ArtifactIdentity(
                relative_path=str(value["relative_path"]),
                size_bytes=int(value["size_bytes"]),
                sha256=str(value["sha256"]),
                row_count=int(value["row_count"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise Stage08ValidationError(
                "MANIFEST_INVALID", "Artifact fields differ"
            ) from error
        if item.relative_path != f"{directory}/part-{sequence:06d}.parquet":
            _fail("MANIFEST_INVALID", "Artifact order/topology differs")
        _digest_bytes(item.sha256)
        path = root / item.relative_path
        _require_file(path, "ARTIFACT_INVALID")
        _require_mode(path, 0o600)
        if (
            path.stat(follow_symlinks=False).st_size != item.size_bytes
            or _sha256_file(path) != item.sha256
        ):
            _fail("ARTIFACT_MISMATCH", "An artifact physical identity differs")
        artifacts.append(item)
    return tuple(artifacts)


class _BatchStream:
    def __init__(self, batches: Iterator[pa.RecordBatch]) -> None:
        self._batches = batches
        self._current: pa.RecordBatch | None = None
        self._offset = 0

    def _ensure(self) -> bool:
        while self._current is None or self._offset == self._current.num_rows:
            try:
                self._current = next(self._batches)
                self._offset = 0
            except StopIteration:
                self._current = None
                return False
        return True

    def one(self, code: str) -> tuple[pa.RecordBatch, int]:
        if not self._ensure():
            _fail(code, "A compared output stream ended early")
        assert self._current is not None
        result = self._current, self._offset
        self._offset += 1
        return result

    def take(self, rows: int, code: str) -> Iterator[pa.RecordBatch]:
        remaining = rows
        while remaining:
            if not self._ensure():
                _fail(code, "A compared output stream ended early")
            assert self._current is not None
            length = min(remaining, self._current.num_rows - self._offset)
            yield self._current.slice(self._offset, length)
            self._offset += length
            remaining -= length

    def exhausted(self) -> bool:
        return not self._ensure()


def _compare_scalar(left: pa.Scalar, right: pa.Scalar, code: str) -> None:
    if not left.equals(right):
        _fail(code, "An exact projected value differs")


def _occurrence_hash_row(
    logical: _CanonicalRelationHasher,
    schema: pa.Schema,
    source_ordinal: int,
    stable_id: bytes,
    representation: str,
    candidate_id: bytes,
) -> None:
    representation_ordinal = 0 if representation == STANDARD else 1
    logical.update_python_row(
        (
            source_ordinal,
            stable_id,
            representation,
            representation_ordinal,
            candidate_id,
        ),
        schema,
    )


def materialize_stage08(config: Stage08Config) -> Stage08Outcome:
    """Materialize, falsification-validate, and atomically publish Stage 8."""
    config.validate()
    if config.controlled_execution:
        require_goethe_nhr_slurm("stage08-address-evidence-projection")
    _validate_runtime()
    inputs = _validated_inputs(config)
    schemas = (
        candidate_evidence_schema(config.binding),
        parser_component_evidence_schema(config.binding),
        source_candidate_map_schema(config.binding),
        representation_occurrence_schema(config.binding),
    )
    _assert_semantic_boundary(*schemas)
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "The Stage 8 output already exists")
    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "The Stage 8 attempt already exists")
    old_umask = os.umask(0o077)
    manifest_sha = ""
    prepublication_started = 0.0
    try:
        temporary.mkdir(mode=0o700)
        in_progress = temporary / STAGE08_IN_PROGRESS_NAME
        in_progress.write_text("in_progress\n", encoding="ascii")
        in_progress.chmod(0o600)
        contract = stage08_contract_fingerprint(config.binding)
        schema_bundle = stage08_schema_bundle_fingerprint(config.binding)
        mapping_fingerprint = stage08_label_mapping_fingerprint()
        candidate_schema, component_schema, source_schema, occurrence_schema = schemas
        candidate_writer = _RelationWriter(
            root=temporary,
            directory=CANDIDATE_DIRECTORY,
            schema=candidate_schema,
            shard_rows=config.candidate_shard_rows,
            row_group_rows=config.candidate_output_batch_rows,
            target_batch_bytes=config.target_batch_bytes,
        )
        component_writer = _RelationWriter(
            root=temporary,
            directory=COMPONENT_DIRECTORY,
            schema=component_schema,
            shard_rows=config.component_shard_rows,
            row_group_rows=config.component_batch_rows,
            target_batch_bytes=config.target_batch_bytes,
        )
        source_writer = _RelationWriter(
            root=temporary,
            directory=SOURCE_MAP_DIRECTORY,
            schema=source_schema,
            shard_rows=config.source_shard_rows,
            row_group_rows=min(config.source_shard_rows, 2_048),
            target_batch_bytes=config.target_batch_bytes,
        )
        candidate_logical = _CanonicalRelationHasher(
            _CANDIDATE_LOGICAL_DOMAIN, contract, candidate_schema
        )
        component_logical = _CanonicalRelationHasher(
            _COMPONENT_LOGICAL_DOMAIN, contract, component_schema
        )
        source_logical = _CanonicalRelationHasher(
            _SOURCE_MAP_LOGICAL_DOMAIN, contract, source_schema
        )
        occurrence_logical = _CanonicalRelationHasher(
            _OCCURRENCE_LOGICAL_DOMAIN, contract, occurrence_schema
        )
        candidate_rows = 0
        component_rows = 0
        mapped_rows = 0
        unmapped_rows = 0
        maximum_components = 0
        maximum_candidate_codepoints = 0
        previous_candidate_id: bytes | None = None
        technical_counts: Counter[str] = Counter()
        applicability_counts: Counter[str] = Counter()
        warning_counts: Counter[str] = Counter()
        index_counts: Counter[str] = Counter()
        stage07_columns = tuple(stage07_evidence_schema().names)
        for batch, index in _iter_rows(
            inputs.stage07_paths, stage07_columns, config.input_batch_rows
        ):
            components = _components_for_row(batch, index)
            _validate_stage07_row(batch, index, components)
            candidate_id = batch.column(0)[index].as_py()
            candidate_text = batch.column(1)[index].as_py()
            assert isinstance(candidate_id, bytes) and isinstance(candidate_text, str)
            if (
                previous_candidate_id is not None
                and candidate_id <= previous_candidate_id
            ):
                _fail(
                    "CANDIDATE_ORDER_FAILURE", "Candidate ID order/uniqueness differs"
                )
            previous_candidate_id = candidate_id
            standard_count = batch.column(3)[index].as_py()
            native_count = batch.column(4)[index].as_py()
            assert isinstance(standard_count, int) and isinstance(native_count, int)
            raw_count = len(components)
            candidate_unmapped = 0
            ordinal = 0
            while ordinal < raw_count:
                length = min(config.component_batch_rows, raw_count - ordinal)
                output_batch, chunk_unmapped = _component_batch(
                    candidate_id,
                    ordinal,
                    components.slice(ordinal, length),
                    component_schema,
                )
                component_writer.write(output_batch)
                component_logical.update_batch(output_batch)
                candidate_unmapped += chunk_unmapped
                component_rows += length
                ordinal += length
            candidate_mapped = raw_count - candidate_unmapped
            if raw_count == 0:
                index_status = COMPONENT_INDEX_EMPTY
            elif candidate_unmapped:
                index_status = COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL
            else:
                index_status = COMPONENT_INDEX_EMITTED
            arrays = [
                batch.column(position).slice(index, 1)
                for position in range(batch.num_columns)
            ]
            arrays.extend(
                (
                    pa.array(
                        (_representation_scope(standard_count, native_count),),
                        type=pa.string(),
                    ),
                    pa.array((raw_count,), type=pa.uint64()),
                    pa.array((candidate_mapped,), type=pa.uint64()),
                    pa.array((candidate_unmapped,), type=pa.uint64()),
                    pa.array((index_status,), type=pa.string()),
                )
            )
            candidate_batch = pa.RecordBatch.from_arrays(
                arrays, schema=candidate_schema
            )
            candidate_writer.write(candidate_batch)
            candidate_logical.update_batch(candidate_batch)
            candidate_rows += 1
            mapped_rows += candidate_mapped
            unmapped_rows += candidate_unmapped
            maximum_components = max(maximum_components, raw_count)
            maximum_candidate_codepoints = max(
                maximum_candidate_codepoints, len(candidate_text)
            )
            technical = batch.column(
                batch.schema.get_field_index("stage07_parse_status")
            )[index].as_py()
            applicability = batch.column(
                batch.schema.get_field_index("stage07_parser_applicability_status")
            )[index].as_py()
            warning = batch.column(
                batch.schema.get_field_index("stage07_structural_warning_status")
            )[index].as_py()
            assert (
                isinstance(technical, str)
                and isinstance(applicability, str)
                and isinstance(warning, str)
            )
            technical_counts[technical] += 1
            applicability_counts[applicability] += 1
            warning_counts[warning] += 1
            index_counts[index_status] += 1
        candidate_artifacts = candidate_writer.finish()
        component_artifacts = component_writer.finish()

        source_rows = 0
        occurrence_rows = 0
        standard_occurrences = 0
        native_occurrences = 0
        for input_batch in _iter_batches(
            inputs.stage06_row_map_paths, SOURCE_COPY_FIELDS, config.input_batch_rows
        ):
            ordinals = pa.array(
                range(source_rows, source_rows + input_batch.num_rows), type=pa.uint64()
            )
            by_name = {
                name: input_batch.column(position)
                for position, name in enumerate(SOURCE_COPY_FIELDS)
            }
            standard_ids = by_name["stage06_standard_exact_candidate_id"]
            native_ids = by_name["stage06_native_exact_candidate_id"]
            standard_status = pa.array(
                (ABSENT if item.as_py() is None else PRESENT for item in standard_ids),
                type=pa.string(),
            )
            native_status = pa.array(
                (ABSENT if item.as_py() is None else PRESENT for item in native_ids),
                type=pa.string(),
            )
            arrays = [by_name[name] for name in SOURCE_COPY_FIELDS[:5]]
            arrays.append(ordinals)
            arrays.extend(by_name[name] for name in SOURCE_COPY_FIELDS[5:])
            arrays.extend((standard_status, native_status))
            output_batch = pa.RecordBatch.from_arrays(arrays, schema=source_schema)
            source_writer.write(output_batch)
            source_logical.update_batch(output_batch)
            stable_ids = by_name["stable_source_row_id_v1"]
            for index in range(input_batch.num_rows):
                stable_id = stable_ids[index].as_py()
                if not isinstance(stable_id, bytes) or len(stable_id) != 32:
                    _fail("SOURCE_IDENTITY_INVALID", "A stable source ID is malformed")
                for representation, values in (
                    (STANDARD, standard_ids),
                    (NATIVE, native_ids),
                ):
                    candidate_id = values[index].as_py()
                    if candidate_id is None:
                        continue
                    if not isinstance(candidate_id, bytes) or len(candidate_id) != 32:
                        _fail(
                            "SOURCE_MAPPING_INVALID",
                            "A source candidate ID is malformed",
                        )
                    _occurrence_hash_row(
                        occurrence_logical,
                        occurrence_schema,
                        source_rows + index,
                        stable_id,
                        representation,
                        candidate_id,
                    )
                    occurrence_rows += 1
                    if representation == STANDARD:
                        standard_occurrences += 1
                    else:
                        native_occurrences += 1
            source_rows += input_batch.num_rows
        source_artifacts = source_writer.finish()
        if (
            candidate_rows != config.binding.candidate_rows
            or technical_counts[PARSED_NONEMPTY] != config.binding.parsed_nonempty_rows
            or technical_counts[PARSED_EMPTY] != config.binding.parsed_empty_rows
            or component_rows != config.binding.raw_component_rows
            or maximum_components != config.binding.maximum_component_count
            or maximum_candidate_codepoints
            != config.binding.maximum_candidate_codepoints
            or source_rows != config.binding.source_rows
            or occurrence_rows != config.binding.occurrence_rows
            or standard_occurrences != config.binding.standard_occurrences
            or native_occurrences != config.binding.native_occurrences
        ):
            _fail("TOTALITY_FAILURE", "Stage 8 materialization totals differ")
        candidate_paths = tuple(
            temporary / item.relative_path for item in candidate_artifacts
        )
        component_paths = tuple(
            temporary / item.relative_path for item in component_artifacts
        )
        source_paths = tuple(
            temporary / item.relative_path for item in source_artifacts
        )
        reconciliation = _duckdb_reconciliation(
            candidate_paths=candidate_paths,
            component_paths=component_paths,
            source_paths=source_paths,
            config=config,
            temporary_parent=parent,
        )
        expected_reconciliation = {
            "candidate_rows": candidate_rows,
            "candidate_distinct_ids": candidate_rows,
            "source_rows": source_rows,
            "source_distinct_ids": source_rows,
            "source_distinct_ordinals": source_rows,
            "source_min_ordinal": 0,
            "source_max_ordinal": source_rows - 1,
            "component_rows": component_rows,
            "component_distinct_keys": component_rows,
            "dangling_component_rows": 0,
            "occurrence_rows": occurrence_rows,
            "standard_occurrences": standard_occurrences,
            "native_occurrences": native_occurrences,
            "occurrence_count_mismatches": 0,
            "component_count_mismatches": 0,
            "mapped_component_rows": mapped_rows,
            "unmapped_component_rows": unmapped_rows,
        }
        if any(
            reconciliation.get(key) != value
            for key, value in expected_reconciliation.items()
        ):
            _fail("RECONCILIATION_FAILURE", "Stage 8 relational reconciliation differs")
        candidate_sha = candidate_logical.hexdigest()
        component_sha = component_logical.hexdigest()
        source_sha = source_logical.hexdigest()
        occurrence_sha = occurrence_logical.hexdigest()
        logical_dataset = _dataset_fingerprint(
            contract=contract,
            schema_bundle=schema_bundle,
            mapping=mapping_fingerprint,
            candidate=candidate_sha,
            component=component_sha,
            source=source_sha,
            occurrence=occurrence_sha,
            counts=(candidate_rows, component_rows, source_rows, occurrence_rows),
        )
        _write_json_exclusive(temporary / MAPPING_METADATA_PATH, _mapping_payload())
        _write_json_exclusive(
            temporary / SCHEMA_METADATA_PATH, _schema_contract_payload(config.binding)
        )
        metadata_artifacts = (
            _artifact_identity(temporary, MAPPING_METADATA_PATH),
            _artifact_identity(temporary, SCHEMA_METADATA_PATH),
        )
        metrics: dict[str, object] = {
            "CANDIDATE_ROWS": candidate_rows,
            "COMPONENT_ROWS": component_rows,
            "SOURCE_ROWS": source_rows,
            "OCCURRENCE_ROWS": occurrence_rows,
            "STANDARD_OCCURRENCES": standard_occurrences,
            "NATIVE_OCCURRENCES": native_occurrences,
            "MAPPED_COMPONENT_ROWS": mapped_rows,
            "UNMAPPED_COMPONENT_ROWS": unmapped_rows,
            "DISTINCT_UNMAPPED_LABELS": reconciliation["distinct_unmapped_labels"],
            "MAXIMUM_COMPONENT_COUNT": maximum_components,
            "MAXIMUM_CANDIDATE_CODEPOINTS": maximum_candidate_codepoints,
            "TECHNICAL_STATUS_COUNTS": dict(sorted(technical_counts.items())),
            "APPLICABILITY_STATUS_COUNTS": dict(sorted(applicability_counts.items())),
            "STRUCTURAL_WARNING_STATUS_COUNTS": dict(sorted(warning_counts.items())),
            "COMPONENT_INDEX_STATUS_COUNTS": dict(sorted(index_counts.items())),
            "PARSER_CALLS": 0,
            "SEMANTIC_TRUST_FIELDS": 0,
            "REFERENCE_LOOKUPS": 0,
            "NETWORK_CALLS": 0,
        }
        manifest = {
            "stage08_manifest_version": STAGE08_MANIFEST_VERSION,
            "status": "STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED",
            "scientific_identity": {
                "contract": STAGE08_CONTRACT_VERSION,
                "profile": STAGE08_PROFILE_VERSION,
                "schema_bundle": STAGE08_SCHEMA_BUNDLE_VERSION,
                "semantic_taxonomy": STAGE08_SEMANTIC_TAXONOMY_VERSION,
                "label_mapping": STAGE08_LABEL_MAPPING_VERSION,
                "occurrence_view": STAGE08_OCCURRENCE_VIEW_VERSION,
                "logical_encoding": STAGE08_LOGICAL_ENCODING_VERSION,
                "contract_fingerprint": contract,
                "schema_bundle_fingerprint": schema_bundle,
                "schema_fingerprints": stage08_schema_fingerprints(config.binding),
                "label_mapping_fingerprint": mapping_fingerprint,
                "input_binding": config.binding.to_dict(),
                "relation_logical_fingerprints": {
                    "candidate_evidence": candidate_sha,
                    "parser_component_evidence": component_sha,
                    "source_candidate_map": source_sha,
                    "representation_occurrence_v1": occurrence_sha,
                },
                "logical_dataset_sha256": logical_dataset,
                "representation_occurrence_view": {
                    "materialized": False,
                    "canonical_sql": REPRESENTATION_OCCURRENCE_SQL,
                    "row_count": occurrence_rows,
                },
            },
            "physical_identity": {
                "candidate_evidence_artifacts": [
                    item.to_dict() for item in candidate_artifacts
                ],
                "parser_component_evidence_artifacts": [
                    item.to_dict() for item in component_artifacts
                ],
                "source_candidate_map_artifacts": [
                    item.to_dict() for item in source_artifacts
                ],
                "metadata_artifacts": [item.to_dict() for item in metadata_artifacts],
                "owner_only_permissions": True,
                "atomic_publication": True,
                "prepublication_reopen_validation": True,
                "bounded_memory": {
                    "input_batch_rows": config.input_batch_rows,
                    "candidate_output_batch_rows": config.candidate_output_batch_rows,
                    "component_batch_rows": config.component_batch_rows,
                    "target_batch_bytes": config.target_batch_bytes,
                    "candidate_shard_rows": config.candidate_shard_rows,
                    "component_shard_rows": config.component_shard_rows,
                    "source_shard_rows": config.source_shard_rows,
                    "population_sized_component_buffer": False,
                    "giant_rows_skipped_or_truncated": False,
                },
            },
            "development_metrics": metrics,
            "reconciliation": reconciliation,
            "validation": {
                "version": STAGE08_VALIDATION_VERSION,
                "exact_candidate_identity": "PASS",
                "exact_stage07_candidate_fields": "PASS",
                "raw_component_preservation": "PASS",
                "component_index_reversibility": "PASS",
                "duplicate_and_unknown_label_preservation": "PASS",
                "source_row_identity": "PASS",
                "representation_slot_correctness": "PASS",
                "occurrence_map_back": "PASS",
                "applicability_technical_provenance": "PASS",
                "warning_field_preservation": "PASS",
                "semantic_trust_vocabulary_absent": "PASS",
                "later_stage_behavior_absent": "PASS",
                "holdout_and_production_excluded": "PASS",
            },
            "privacy": {
                "row_values_in_manifest": False,
                "protected_values_logged": False,
                "external_services": False,
                "holdout_access": False,
                "production_access": False,
            },
            "operational_provenance": {
                "execution_git_sha": config.execution_git_sha,
                "created_at_utc": _utc_now(),
                "python_version": platform.python_version(),
                "pyarrow_version": pa.__version__,
                "duckdb_version": duckdb.__version__,
                **dict(config.operational_metadata or {}),
            },
        }
        _write_json_exclusive(temporary / STAGE08_MANIFEST_NAME, manifest)
        manifest_sha = _sha256_file(temporary / STAGE08_MANIFEST_NAME)
        _write_json_exclusive(
            temporary / STAGE08_SUCCESS_NAME,
            {
                "status": "STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED",
                "manifest_sha256": manifest_sha,
                "logical_dataset_sha256": logical_dataset,
                "contract_fingerprint": contract,
                "schema_bundle_fingerprint": schema_bundle,
                "candidate_rows": candidate_rows,
                "component_rows": component_rows,
                "source_rows": source_rows,
                "occurrence_rows": occurrence_rows,
            },
        )
        in_progress.unlink()
        for directory in (
            temporary / CANDIDATE_DIRECTORY,
            (temporary / CANDIDATE_DIRECTORY).parent,
            temporary / COMPONENT_DIRECTORY,
            (temporary / COMPONENT_DIRECTORY).parent,
            temporary / SOURCE_MAP_DIRECTORY,
            (temporary / SOURCE_MAP_DIRECTORY).parent,
            temporary / "metadata",
            temporary,
        ):
            _fsync_directory(directory)
        prepublication_started = time.perf_counter()
        validate_stage08_bundle(
            temporary,
            expected_manifest_sha256=manifest_sha,
            config=replace(
                config, output_directory=temporary, controlled_execution=False
            ),
        )
        if config.output_directory.exists() or config.output_directory.is_symlink():
            _fail("OUTPUT_COLLISION", "The Stage 8 output appeared before publication")
        os.rename(temporary, config.output_directory)
        _fsync_directory(parent)
    except (Stage08ValidationError, duckdb.Error, pa.ArrowException):
        raise
    except OSError as error:
        raise Stage08ValidationError(
            "STAGE08_PUBLICATION_FAILURE", "Stage 8 publication failed"
        ) from error
    finally:
        os.umask(old_umask)
    outcome = validate_stage08_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_sha,
        config=replace(config, controlled_execution=False),
    )
    return replace(
        outcome,
        publication_validation_milliseconds=round(
            (time.perf_counter() - prepublication_started) * 1_000
        ),
    )


def validate_stage08_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    config: Stage08Config,
) -> Stage08Outcome:
    """Independently reopen and falsification-check a Stage 8 publication."""
    config.validate()
    if config.controlled_execution:
        require_goethe_nhr_slurm("stage08-address-evidence-validation")
    _validate_runtime()
    _digest_bytes(expected_manifest_sha256)
    _reject_scope_paths(output_directory)
    inputs = _validated_inputs(config)
    _require_directory(output_directory, "STAGE08_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700)
    manifest_path = output_directory / STAGE08_MANIFEST_NAME
    success_path = output_directory / STAGE08_SUCCESS_NAME
    _require_file(manifest_path, "STAGE08_TERMINAL_MISSING")
    _require_file(success_path, "STAGE08_TERMINAL_MISSING")
    _require_mode(manifest_path, 0o600)
    _require_mode(success_path, 0o600)
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        _fail("MANIFEST_SHA256_MISMATCH", "The Stage 8 manifest SHA differs")
    manifest = _load_json(manifest_path, "MANIFEST_INVALID")
    success = _load_json(success_path, "SUCCESS_MARKER_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    privacy = manifest.get("privacy")
    recorded_metrics = manifest.get("development_metrics")
    recorded_reconciliation = manifest.get("reconciliation")
    operational = manifest.get("operational_provenance")
    if not all(
        isinstance(item, dict)
        for item in (
            scientific,
            physical,
            validation,
            privacy,
            recorded_metrics,
            recorded_reconciliation,
            operational,
        )
    ):
        _fail("MANIFEST_INVALID", "A manifest section is absent")
    scientific = cast(dict[str, object], scientific)
    physical = cast(dict[str, object], physical)
    validation = cast(dict[str, object], validation)
    privacy = cast(dict[str, object], privacy)
    recorded_metrics = cast(dict[str, object], recorded_metrics)
    recorded_reconciliation = cast(dict[str, object], recorded_reconciliation)
    operational = cast(dict[str, object], operational)
    bounded = physical.get("bounded_memory")
    contract = stage08_contract_fingerprint(config.binding)
    schema_bundle = stage08_schema_bundle_fingerprint(config.binding)
    mapping_fingerprint = stage08_label_mapping_fingerprint()
    schema_fingerprints = stage08_schema_fingerprints(config.binding)
    if (
        manifest.get("stage08_manifest_version") != STAGE08_MANIFEST_VERSION
        or manifest.get("status")
        != "STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED"
        or success.get("status")
        != "STAGE08_ADDRESS_EVIDENCE_IMPLEMENTATION_CANDIDATE_MATERIALIZED"
        or success.get("manifest_sha256") != expected_manifest_sha256
        or scientific.get("contract") != STAGE08_CONTRACT_VERSION
        or scientific.get("profile") != STAGE08_PROFILE_VERSION
        or scientific.get("schema_bundle") != STAGE08_SCHEMA_BUNDLE_VERSION
        or scientific.get("semantic_taxonomy") != STAGE08_SEMANTIC_TAXONOMY_VERSION
        or scientific.get("label_mapping") != STAGE08_LABEL_MAPPING_VERSION
        or scientific.get("occurrence_view") != STAGE08_OCCURRENCE_VIEW_VERSION
        or scientific.get("logical_encoding") != STAGE08_LOGICAL_ENCODING_VERSION
        or scientific.get("contract_fingerprint") != contract
        or scientific.get("schema_bundle_fingerprint") != schema_bundle
        or scientific.get("schema_fingerprints") != schema_fingerprints
        or scientific.get("label_mapping_fingerprint") != mapping_fingerprint
        or scientific.get("input_binding") != config.binding.to_dict()
        or validation.get("version") != STAGE08_VALIDATION_VERSION
        or any(value != "PASS" for key, value in validation.items() if key != "version")
        or privacy
        != {
            "row_values_in_manifest": False,
            "protected_values_logged": False,
            "external_services": False,
            "holdout_access": False,
            "production_access": False,
        }
        or physical.get("owner_only_permissions") is not True
        or physical.get("atomic_publication") is not True
        or physical.get("prepublication_reopen_validation") is not True
        or not isinstance(bounded, dict)
        or bounded
        != {
            "input_batch_rows": config.input_batch_rows,
            "candidate_output_batch_rows": config.candidate_output_batch_rows,
            "component_batch_rows": config.component_batch_rows,
            "target_batch_bytes": config.target_batch_bytes,
            "candidate_shard_rows": config.candidate_shard_rows,
            "component_shard_rows": config.component_shard_rows,
            "source_shard_rows": config.source_shard_rows,
            "population_sized_component_buffer": False,
            "giant_rows_skipped_or_truncated": False,
        }
        or operational.get("execution_git_sha") != config.execution_git_sha
        or operational.get("python_version") != platform.python_version()
        or operational.get("pyarrow_version") != pa.__version__
        or operational.get("duckdb_version") != duckdb.__version__
        or any(
            operational.get(key) != value
            for key, value in (config.operational_metadata or {}).items()
        )
    ):
        _fail("SCIENTIFIC_IDENTITY_MISMATCH", "Stage 8 identity/semantics differ")
    candidate_artifacts = _output_artifacts(
        output_directory,
        physical.get("candidate_evidence_artifacts"),
        directory=CANDIDATE_DIRECTORY,
    )
    component_artifacts = _output_artifacts(
        output_directory,
        physical.get("parser_component_evidence_artifacts"),
        directory=COMPONENT_DIRECTORY,
    )
    source_artifacts = _output_artifacts(
        output_directory,
        physical.get("source_candidate_map_artifacts"),
        directory=SOURCE_MAP_DIRECTORY,
    )
    metadata_raw = physical.get("metadata_artifacts")
    if not isinstance(metadata_raw, list) or len(metadata_raw) != 2:
        _fail("MANIFEST_INVALID", "Metadata artifacts differ")
    metadata_artifacts: list[Stage08ArtifactIdentity] = []
    for expected_path, raw in zip(
        (MAPPING_METADATA_PATH, SCHEMA_METADATA_PATH), metadata_raw
    ):
        if not isinstance(raw, dict):
            _fail("MANIFEST_INVALID", "A metadata artifact is malformed")
        item = Stage08ArtifactIdentity(
            relative_path=str(raw.get("relative_path")),
            size_bytes=int(raw.get("size_bytes", -1)),
            sha256=str(raw.get("sha256")),
        )
        if item.relative_path != expected_path:
            _fail("MANIFEST_INVALID", "Metadata artifact order differs")
        _digest_bytes(item.sha256)
        path = output_directory / item.relative_path
        _require_file(path, "ARTIFACT_INVALID")
        _require_mode(path, 0o600)
        if (
            path.stat(follow_symlinks=False).st_size != item.size_bytes
            or _sha256_file(path) != item.sha256
        ):
            _fail("ARTIFACT_MISMATCH", "A metadata artifact differs")
        metadata_artifacts.append(item)
    mapping_payload = _load_json(
        output_directory / MAPPING_METADATA_PATH, "MAPPING_METADATA_INVALID"
    )
    schema_payload = _load_json(
        output_directory / SCHEMA_METADATA_PATH, "SCHEMA_METADATA_INVALID"
    )
    if (
        mapping_payload != _mapping_payload()
        or schema_payload != _schema_contract_payload(config.binding)
    ):
        _fail("METADATA_CONTRACT_MISMATCH", "Mapping/schema metadata differs")
    expected_directories = {
        "candidate_evidence",
        CANDIDATE_DIRECTORY,
        "parser_component_evidence",
        COMPONENT_DIRECTORY,
        "source_candidate_map",
        SOURCE_MAP_DIRECTORY,
        "metadata",
    }
    expected_files = {
        STAGE08_MANIFEST_NAME,
        STAGE08_SUCCESS_NAME,
        MAPPING_METADATA_PATH,
        SCHEMA_METADATA_PATH,
        *(item.relative_path for item in candidate_artifacts),
        *(item.relative_path for item in component_artifacts),
        *(item.relative_path for item in source_artifacts),
    }
    directories, files = _topology(output_directory)
    if directories != expected_directories or files != expected_files:
        _fail("TOPOLOGY_FAILURE", "Stage 8 artifact topology differs")
    candidate_schema = candidate_evidence_schema(config.binding)
    component_schema = parser_component_evidence_schema(config.binding)
    source_schema = source_candidate_map_schema(config.binding)
    occurrence_schema = representation_occurrence_schema(config.binding)
    _assert_semantic_boundary(
        candidate_schema, component_schema, source_schema, occurrence_schema
    )
    artifact_groups = (
        (candidate_artifacts, candidate_schema),
        (component_artifacts, component_schema),
        (source_artifacts, source_schema),
    )
    for artifacts, schema in artifact_groups:
        for item in artifacts:
            reopened = pq.ParquetFile(
                output_directory / item.relative_path, page_checksum_verification=True
            ).schema_arrow
            if not reopened.equals(schema, check_metadata=True):
                _fail("OUTPUT_SCHEMA_MISMATCH", "A reopened Arrow schema differs")
    candidate_paths = tuple(
        output_directory / item.relative_path for item in candidate_artifacts
    )
    component_paths = tuple(
        output_directory / item.relative_path for item in component_artifacts
    )
    source_paths = tuple(
        output_directory / item.relative_path for item in source_artifacts
    )
    candidate_output = _BatchStream(
        _iter_batches(candidate_paths, candidate_schema.names, config.input_batch_rows)
    )
    component_output = _BatchStream(
        _iter_batches(
            component_paths, component_schema.names, config.component_batch_rows
        )
    )
    candidate_logical = _CanonicalRelationHasher(
        _CANDIDATE_LOGICAL_DOMAIN, contract, candidate_schema
    )
    component_logical = _CanonicalRelationHasher(
        _COMPONENT_LOGICAL_DOMAIN, contract, component_schema
    )
    candidate_rows = 0
    component_rows = 0
    mapped_rows = 0
    unmapped_rows = 0
    maximum_components = 0
    maximum_candidate_codepoints = 0
    previous_id: bytes | None = None
    technical_counts: Counter[str] = Counter()
    applicability_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    index_counts: Counter[str] = Counter()
    stage07_columns = tuple(stage07_evidence_schema().names)
    for input_batch, input_index in _iter_rows(
        inputs.stage07_paths, stage07_columns, config.input_batch_rows
    ):
        output_batch, output_index = candidate_output.one("CANDIDATE_ROW_MISMATCH")
        components = _components_for_row(input_batch, input_index)
        _validate_stage07_row(input_batch, input_index, components)
        for position in range(len(stage07_columns)):
            _compare_scalar(
                input_batch.column(position)[input_index],
                output_batch.column(position)[output_index],
                "STAGE07_FIELD_PRESERVATION_FAILURE",
            )
        candidate_id = input_batch.column(0)[input_index].as_py()
        candidate_text = input_batch.column(1)[input_index].as_py()
        standard_count = input_batch.column(3)[input_index].as_py()
        native_count = input_batch.column(4)[input_index].as_py()
        assert isinstance(candidate_id, bytes) and isinstance(candidate_text, str)
        assert isinstance(standard_count, int) and isinstance(native_count, int)
        if previous_id is not None and candidate_id <= previous_id:
            _fail("CANDIDATE_ORDER_FAILURE", "Candidate order differs")
        previous_id = candidate_id
        raw_count = len(components)
        candidate_unmapped = 0
        ordinal = 0
        while ordinal < raw_count:
            chunk_length = min(config.component_batch_rows, raw_count - ordinal)
            expected, chunk_unmapped = _component_batch(
                candidate_id,
                ordinal,
                components.slice(ordinal, chunk_length),
                component_schema,
            )
            expected_offset = 0
            for observed in component_output.take(
                chunk_length, "COMPONENT_INDEX_REVERSIBILITY_FAILURE"
            ):
                expected_piece = expected.slice(expected_offset, observed.num_rows)
                for position in range(len(component_schema)):
                    if not expected_piece.column(position).equals(
                        observed.column(position)
                    ):
                        _fail(
                            "COMPONENT_INDEX_REVERSIBILITY_FAILURE",
                            "A component ordinal/label/value/mapping differs",
                        )
                component_logical.update_batch(observed)
                expected_offset += observed.num_rows
            candidate_unmapped += chunk_unmapped
            component_rows += chunk_length
            ordinal += chunk_length
        candidate_mapped = raw_count - candidate_unmapped
        index_status = (
            COMPONENT_INDEX_EMPTY
            if raw_count == 0
            else (
                COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL
                if candidate_unmapped
                else COMPONENT_INDEX_EMITTED
            )
        )
        expected_appended = (
            _representation_scope(standard_count, native_count),
            raw_count,
            candidate_mapped,
            candidate_unmapped,
            index_status,
        )
        for offset, expected_value in enumerate(
            expected_appended, start=len(stage07_columns)
        ):
            if output_batch.column(offset)[output_index].as_py() != expected_value:
                _fail(
                    "CANDIDATE_INDEX_MISMATCH", "A candidate mechanical field differs"
                )
        candidate_logical.update_batch(output_batch.slice(output_index, 1))
        technical = input_batch.column(
            input_batch.schema.get_field_index("stage07_parse_status")
        )[input_index].as_py()
        applicability = input_batch.column(
            input_batch.schema.get_field_index("stage07_parser_applicability_status")
        )[input_index].as_py()
        warning = input_batch.column(
            input_batch.schema.get_field_index("stage07_structural_warning_status")
        )[input_index].as_py()
        assert (
            isinstance(technical, str)
            and isinstance(applicability, str)
            and isinstance(warning, str)
        )
        technical_counts[technical] += 1
        applicability_counts[applicability] += 1
        warning_counts[warning] += 1
        index_counts[index_status] += 1
        mapped_rows += candidate_mapped
        unmapped_rows += candidate_unmapped
        maximum_components = max(maximum_components, raw_count)
        maximum_candidate_codepoints = max(
            maximum_candidate_codepoints, len(candidate_text)
        )
        candidate_rows += 1
    if not candidate_output.exhausted() or not component_output.exhausted():
        _fail("OUTPUT_ROW_MISMATCH", "A candidate/component output has added rows")

    source_output = _BatchStream(
        _iter_batches(source_paths, source_schema.names, config.input_batch_rows)
    )
    source_logical = _CanonicalRelationHasher(
        _SOURCE_MAP_LOGICAL_DOMAIN, contract, source_schema
    )
    occurrence_logical = _CanonicalRelationHasher(
        _OCCURRENCE_LOGICAL_DOMAIN, contract, occurrence_schema
    )
    source_rows = 0
    occurrence_rows = 0
    standard_occurrences = 0
    native_occurrences = 0
    for input_batch, input_index in _iter_rows(
        inputs.stage06_row_map_paths, SOURCE_COPY_FIELDS, config.input_batch_rows
    ):
        output_batch, output_index = source_output.one("SOURCE_ROW_MISMATCH")
        expected_source_positions = (
            *range(5),
            *range(6, 6 + len(SOURCE_COPY_FIELDS) - 5),
        )
        for input_position, output_position in enumerate(expected_source_positions):
            _compare_scalar(
                input_batch.column(input_position)[input_index],
                output_batch.column(output_position)[output_index],
                "SOURCE_FIELD_PRESERVATION_FAILURE",
            )
        if output_batch.column(5)[output_index].as_py() != source_rows:
            _fail("SOURCE_ROW_ORDINAL_FAILURE", "Source row ordinal differs")
        standard_id = input_batch.column(
            SOURCE_COPY_FIELDS.index("stage06_standard_exact_candidate_id")
        )[input_index].as_py()
        native_id = input_batch.column(
            SOURCE_COPY_FIELDS.index("stage06_native_exact_candidate_id")
        )[input_index].as_py()
        expected_statuses = (
            ABSENT if standard_id is None else PRESENT,
            ABSENT if native_id is None else PRESENT,
        )
        if (
            tuple(
                output_batch.column(len(source_schema) - 2 + offset)[
                    output_index
                ].as_py()
                for offset in range(2)
            )
            != expected_statuses
        ):
            _fail(
                "REPRESENTATION_SLOT_FAILURE",
                "A representation presence status differs",
            )
        source_logical.update_batch(output_batch.slice(output_index, 1))
        stable_id = input_batch.column(
            SOURCE_COPY_FIELDS.index("stable_source_row_id_v1")
        )[input_index].as_py()
        assert isinstance(stable_id, bytes)
        for representation, candidate_id in (
            (STANDARD, standard_id),
            (NATIVE, native_id),
        ):
            if candidate_id is None:
                continue
            assert isinstance(candidate_id, bytes)
            _occurrence_hash_row(
                occurrence_logical,
                occurrence_schema,
                source_rows,
                stable_id,
                representation,
                candidate_id,
            )
            occurrence_rows += 1
            if representation == STANDARD:
                standard_occurrences += 1
            else:
                native_occurrences += 1
        source_rows += 1
    if not source_output.exhausted():
        _fail("SOURCE_ROW_MISMATCH", "The source-map output has added rows")
    reconciliation = _duckdb_reconciliation(
        candidate_paths=candidate_paths,
        component_paths=component_paths,
        source_paths=source_paths,
        config=config,
        temporary_parent=output_directory.parent,
    )
    relation_logical = {
        "candidate_evidence": candidate_logical.hexdigest(),
        "parser_component_evidence": component_logical.hexdigest(),
        "source_candidate_map": source_logical.hexdigest(),
        "representation_occurrence_v1": occurrence_logical.hexdigest(),
    }
    logical_dataset = _dataset_fingerprint(
        contract=contract,
        schema_bundle=schema_bundle,
        mapping=mapping_fingerprint,
        candidate=relation_logical["candidate_evidence"],
        component=relation_logical["parser_component_evidence"],
        source=relation_logical["source_candidate_map"],
        occurrence=relation_logical["representation_occurrence_v1"],
        counts=(candidate_rows, component_rows, source_rows, occurrence_rows),
    )
    expected_metrics = {
        "CANDIDATE_ROWS": candidate_rows,
        "COMPONENT_ROWS": component_rows,
        "SOURCE_ROWS": source_rows,
        "OCCURRENCE_ROWS": occurrence_rows,
        "STANDARD_OCCURRENCES": standard_occurrences,
        "NATIVE_OCCURRENCES": native_occurrences,
        "MAPPED_COMPONENT_ROWS": mapped_rows,
        "UNMAPPED_COMPONENT_ROWS": unmapped_rows,
        "DISTINCT_UNMAPPED_LABELS": reconciliation["distinct_unmapped_labels"],
        "MAXIMUM_COMPONENT_COUNT": maximum_components,
        "MAXIMUM_CANDIDATE_CODEPOINTS": maximum_candidate_codepoints,
        "TECHNICAL_STATUS_COUNTS": dict(sorted(technical_counts.items())),
        "APPLICABILITY_STATUS_COUNTS": dict(sorted(applicability_counts.items())),
        "STRUCTURAL_WARNING_STATUS_COUNTS": dict(sorted(warning_counts.items())),
        "COMPONENT_INDEX_STATUS_COUNTS": dict(sorted(index_counts.items())),
        "PARSER_CALLS": 0,
        "SEMANTIC_TRUST_FIELDS": 0,
        "REFERENCE_LOOKUPS": 0,
        "NETWORK_CALLS": 0,
    }
    occurrence_view = scientific.get("representation_occurrence_view")
    if (
        candidate_rows != config.binding.candidate_rows
        or component_rows != config.binding.raw_component_rows
        or source_rows != config.binding.source_rows
        or occurrence_rows != config.binding.occurrence_rows
        or standard_occurrences != config.binding.standard_occurrences
        or native_occurrences != config.binding.native_occurrences
        or technical_counts[PARSED_NONEMPTY] != config.binding.parsed_nonempty_rows
        or technical_counts[PARSED_EMPTY] != config.binding.parsed_empty_rows
        or maximum_components != config.binding.maximum_component_count
        or maximum_candidate_codepoints != config.binding.maximum_candidate_codepoints
        or scientific.get("relation_logical_fingerprints") != relation_logical
        or scientific.get("logical_dataset_sha256") != logical_dataset
        or not isinstance(occurrence_view, dict)
        or occurrence_view
        != {
            "materialized": False,
            "canonical_sql": REPRESENTATION_OCCURRENCE_SQL,
            "row_count": occurrence_rows,
        }
        or recorded_metrics != expected_metrics
        or recorded_reconciliation != reconciliation
        or success.get("logical_dataset_sha256") != logical_dataset
        or success.get("contract_fingerprint") != contract
        or success.get("schema_bundle_fingerprint") != schema_bundle
        or success.get("candidate_rows") != candidate_rows
        or success.get("component_rows") != component_rows
        or success.get("source_rows") != source_rows
        or success.get("occurrence_rows") != occurrence_rows
        or sum(cast(int, item.row_count) for item in candidate_artifacts)
        != candidate_rows
        or sum(cast(int, item.row_count) for item in component_artifacts)
        != component_rows
        or sum(cast(int, item.row_count) for item in source_artifacts) != source_rows
    ):
        _fail("STAGE08_RECONCILIATION_FAILURE", "Stage 8 reopen evidence differs")
    expected_reconciliation = {
        "candidate_rows": candidate_rows,
        "candidate_distinct_ids": candidate_rows,
        "source_rows": source_rows,
        "source_distinct_ids": source_rows,
        "source_distinct_ordinals": source_rows,
        "source_min_ordinal": 0,
        "source_max_ordinal": source_rows - 1,
        "component_rows": component_rows,
        "component_distinct_keys": component_rows,
        "dangling_component_rows": 0,
        "occurrence_rows": occurrence_rows,
        "standard_occurrences": standard_occurrences,
        "native_occurrences": native_occurrences,
        "occurrence_count_mismatches": 0,
        "component_count_mismatches": 0,
        "mapped_component_rows": mapped_rows,
        "unmapped_component_rows": unmapped_rows,
    }
    if any(
        reconciliation.get(key) != value
        for key, value in expected_reconciliation.items()
    ):
        _fail("STAGE08_RECONCILIATION_FAILURE", "Relational totality differs")
    return Stage08Outcome(
        output_directory=output_directory,
        manifest_sha256=expected_manifest_sha256,
        logical_dataset_sha256=logical_dataset,
        contract_fingerprint=contract,
        schema_bundle_fingerprint=schema_bundle,
        candidate_rows=candidate_rows,
        component_rows=component_rows,
        source_rows=source_rows,
        occurrence_rows=occurrence_rows,
        metrics=expected_metrics,
    )


__all__ = [
    "ABSENT",
    "BOTH",
    "COMPONENT_INDEX_EMPTY",
    "COMPONENT_INDEX_EMITTED",
    "COMPONENT_INDEX_EMITTED_WITH_UNMAPPED_LABEL",
    "LIBPOSTAL_LABEL_MAPPING",
    "MAPPED_DEFINED_LABEL",
    "NATIVE",
    "PARSER_EVIDENCE",
    "PRESENT",
    "REPRESENTATION_OCCURRENCE_SQL",
    "STAGE08_CONTRACT_VERSION",
    "STAGE08_LABEL_MAPPING_VERSION",
    "STAGE08_PROFILE_VERSION",
    "STAGE08_SCHEMA_BUNDLE_VERSION",
    "STANDARD",
    "Stage08Config",
    "Stage08InputBinding",
    "Stage08Outcome",
    "Stage08ValidationError",
    "UNMAPPED_LABEL",
    "accepted_stage08_input_binding",
    "candidate_evidence_schema",
    "materialize_stage08",
    "parser_component_evidence_schema",
    "representation_occurrence_schema",
    "source_candidate_map_schema",
    "stage08_contract_fingerprint",
    "stage08_label_mapping_fingerprint",
    "stage08_schema_bundle_fingerprint",
    "stage08_schema_fingerprints",
    "validate_stage08_bundle",
    "validate_stage08_input_binding",
]

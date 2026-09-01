"""Lossless Stage 7 v2 parser-evidence projection.

This module never calls libpostal.  It projects the immutable accepted Stage 6
registry, immutable Stage 7 v1 raw parser registry, and frozen country-
eligibility evidence into a new evidence-only artifact.  Structural signals
are warnings, not assertions that a parse is semantically correct or safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import struct
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s03_cleaning import EXPECTED_PYARROW_VERSION, EXPECTED_PYTHON_VERSION
from .s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    REGISTRY_DIRECTORY as STAGE06_REGISTRY_DIRECTORY,
    ROW_MAP_DIRECTORY as STAGE06_ROW_MAP_DIRECTORY,
    _manifest_artifacts as _stage06_manifest_artifacts,
    registry_schema,
)
from .s07_component_readiness import (
    READINESS_RULE_VERSION,
    REASON_PARSED_EMPTY,
    StructuralSignals,
    structural_signals,
)
from .s07_country_eligibility import (
    COUNTRY_PROVENANCE_STATUSES,
    PARSER_ELIGIBILITY_STATUSES,
    PARSER_ELIGIBLE_COUNTRY,
)
from .s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    LibpostalComponent,
)
from .s07_output_schema import component_list_field, component_list_type
from .s07_parsing import (
    ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
    ACCEPTED_STAGE06_MANIFEST_SHA256,
    ACCEPTED_STAGE06_NATIVE_OCCURRENCES,
    ACCEPTED_STAGE06_OCCURRENCES,
    ACCEPTED_STAGE06_REGISTRY_ROWS,
    ACCEPTED_STAGE06_STANDARD_OCCURRENCES,
    STAGE07_CONTRACT_VERSION as STAGE07_V1_CONTRACT_VERSION,
    STAGE07_MANIFEST_NAME as STAGE07_V1_MANIFEST_NAME,
    STAGE07_PROFILE_VERSION as STAGE07_V1_PROFILE_VERSION,
    STAGE07_STATUS_VOCABULARY,
    Stage07ArtifactIdentity,
    Stage07ValidationError,
    _artifact_identity,
    _fsync_directory,
    _iter_batches,
    _load_json,
    _manifest_artifacts as _stage07_v1_manifest_artifacts,
    _mapback_metrics,
    _reject_holdout_paths,
    _require_directory,
    _require_file,
    _require_mode,
    _sha256_file,
    _topology,
    _write_json_exclusive,
)


STAGE07_EVIDENCE_CONTRACT_VERSION = "stage07_parser_evidence_contract_v2"
STAGE07_EVIDENCE_PROFILE_VERSION = "stage07_parser_evidence_profile_v2"
STAGE07_EVIDENCE_SCHEMA_VERSION = "stage07_parser_evidence_schema_v2"
STAGE07_EVIDENCE_MANIFEST_VERSION = "stage07_parser_evidence_manifest_v2"
STAGE07_EVIDENCE_VALIDATION_VERSION = "stage07_parser_evidence_validation_v2"
STAGE07_EVIDENCE_MANIFEST_NAME = "stage07_parser_evidence_manifest.json"
STAGE07_EVIDENCE_SUCCESS_NAME = "_SUCCESS.json"
STAGE07_EVIDENCE_IN_PROGRESS_NAME = "_IN_PROGRESS"
STAGE07_EVIDENCE_REGISTRY_DIRECTORY = "registry/data"

STRUCTURAL_WARNING_FEATURE_VERSION = "stage07_structural_warning_features_v1"
STRUCTURAL_WARNING_SOURCE_SHA256 = (
    "dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9"
)
NO_STRUCTURAL_WARNINGS_DETECTED = "NO_STRUCTURAL_WARNINGS_DETECTED"
STRUCTURAL_WARNINGS_PRESENT = "STRUCTURAL_WARNINGS_PRESENT"
STRUCTURAL_WARNINGS_NOT_EVALUATED = "STRUCTURAL_WARNINGS_NOT_EVALUATED"
STRUCTURAL_WARNING_STATUSES = (
    NO_STRUCTURAL_WARNINGS_DETECTED,
    STRUCTURAL_WARNINGS_PRESENT,
    STRUCTURAL_WARNINGS_NOT_EVALUATED,
)
PARSER_EXECUTION_ORIGIN = "REUSED_IMMUTABLE_STAGE07_V1"

ACCEPTED_STAGE07_V1_MANIFEST_SHA256 = (
    "98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77"
)
ACCEPTED_ELIGIBILITY_ARTIFACT_SHA256 = (
    "a6ba110c0519873af898dcec0b5188a1db2659fe31aa619613cffcfdf82e499c"
)
ACCEPTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256 = (
    "8395b0b5f8e0943dc6dd1a9c9553ea571294fc7bbe61fc9b9b1e6e8fd1cea1a6"
)
ACCEPTED_ELIGIBILITY_POLICY_MANIFEST_SHA256 = (
    "49dcda13e36d2692885efadffb606fa96207fc174a3385041c07af9bf0d1026a"
)
ACCEPTED_ELIGIBLE_CANDIDATES = 50_685
ACCEPTED_UNRESOLVED_CANDIDATES = 1_094

_SCHEMA_DOMAIN = b"SAFE_STAGE07_PARSER_EVIDENCE_SCHEMA_V2"
_CONTRACT_DOMAIN = b"SAFE_STAGE07_PARSER_EVIDENCE_CONTRACT_V2"
_LOGICAL_DOMAIN = b"SAFE_STAGE07_PARSER_EVIDENCE_LOGICAL_V2"
_DATASET_DOMAIN = b"SAFE_STAGE07_PARSER_EVIDENCE_DATASET_V2"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

WARNING_REASON_FIELD = "stage07_structural_warning_reason_codes"
WARNING_STATUS_FIELD = "stage07_structural_warning_status"
APPLICABILITY_FIELD = "stage07_parser_applicability_status"
COUNTRY_STATUS_FIELD = "stage07_country_provenance_status"
TRUSTED_COUNTRY_FIELD = "stage07_trusted_country_iso_code"
EXECUTION_ORIGIN_FIELD = "stage07_parser_execution_origin"

SIGNAL_FIELDS = (
    "stage07_raw_ordered_substrings",
    "stage07_lexical_numeric_stream_equal",
    "stage07_internal_boundary_count",
    "stage07_internal_single_codepoint_fragment_count",
    "stage07_maximum_components_per_lexical_run",
    "stage07_adjacent_repeated_label_internal_boundary_count",
    "stage07_candidate_lexical_numeric_codepoints",
    "stage07_output_lexical_numeric_codepoints",
)

ELIGIBILITY_COLUMNS = (
    "candidate_id",
    "occurrence_count",
    "standard_occurrence_count",
    "native_occurrence_count",
    "valid_country_occurrence_count",
    "missing_country_occurrence_count",
    "invalid_country_occurrence_count",
    "distinct_valid_country_count",
    "country_provenance_status",
    "unanimous_country_code",
    "libpostal_eligibility",
    "stage07_parse_status",
)


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ValidationError(code, detail)


def _digest(value: str) -> bytes:
    if _SHA256_RE.fullmatch(value) is None:
        _fail("INVALID_FINGERPRINT", "An evidence-only fingerprint is malformed")
    return bytes.fromhex(value)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_runtime() -> None:
    expected_python = ".".join(str(value) for value in EXPECTED_PYTHON_VERSION)
    if platform.python_version() != expected_python:
        _fail("RUNTIME_VERSION_MISMATCH", "Python runtime is not pinned")
    if pa.__version__ != EXPECTED_PYARROW_VERSION or duckdb.__version__ != "1.5.5":
        _fail("RUNTIME_VERSION_MISMATCH", "Arrow/DuckDB runtime is not pinned")


def warning_reason_type() -> pa.DataType:
    # Parquet reopens list children with the canonical ``element`` name.  Use
    # that name in the frozen schema so an exact metadata-aware reopen is
    # stable across publication and validation.
    return pa.large_list(pa.field("element", pa.large_string(), nullable=False))


def stage07_evidence_schema() -> pa.Schema:
    return pa.schema(
        (
            *registry_schema(),
            pa.field(COUNTRY_STATUS_FIELD, pa.string(), nullable=False),
            pa.field(TRUSTED_COUNTRY_FIELD, pa.string(), nullable=True),
            pa.field(
                "stage07_valid_country_occurrence_count", pa.uint64(), nullable=False
            ),
            pa.field(
                "stage07_missing_country_occurrence_count", pa.uint64(), nullable=False
            ),
            pa.field(
                "stage07_invalid_country_occurrence_count", pa.uint64(), nullable=False
            ),
            pa.field(
                "stage07_distinct_valid_country_count", pa.uint32(), nullable=False
            ),
            pa.field(APPLICABILITY_FIELD, pa.string(), nullable=False),
            pa.field("stage07_parse_status", pa.string(), nullable=False),
            pa.field(EXECUTION_ORIGIN_FIELD, pa.string(), nullable=False),
            component_list_field(),
            pa.field(WARNING_STATUS_FIELD, pa.string(), nullable=False),
            pa.field(WARNING_REASON_FIELD, warning_reason_type(), nullable=False),
            pa.field(SIGNAL_FIELDS[0], pa.bool_(), nullable=True),
            pa.field(SIGNAL_FIELDS[1], pa.bool_(), nullable=True),
            *(pa.field(name, pa.uint64(), nullable=True) for name in SIGNAL_FIELDS[2:]),
        )
    )


def stage07_evidence_schema_fingerprint() -> str:
    digest = hashlib.sha256(_SCHEMA_DOMAIN)
    digest.update(STAGE07_EVIDENCE_SCHEMA_VERSION.encode("ascii"))
    for field in stage07_evidence_schema():
        for value in (field.name, str(field.type), str(field.nullable).lower()):
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Stage07EvidenceBinding:
    stage06_manifest_sha256: str
    stage07_v1_manifest_sha256: str
    eligibility_artifact_sha256: str
    eligibility_audit_manifest_sha256: str
    eligibility_policy_manifest_sha256: str
    parser_bundle_fingerprint: str
    stage06_candidate_rows: int
    stage06_occurrences: int
    stage06_standard_occurrences: int
    stage06_native_occurrences: int
    eligible_candidates: int
    unresolved_candidates: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


def accepted_stage07_evidence_binding() -> Stage07EvidenceBinding:
    return Stage07EvidenceBinding(
        stage06_manifest_sha256=ACCEPTED_STAGE06_MANIFEST_SHA256,
        stage07_v1_manifest_sha256=ACCEPTED_STAGE07_V1_MANIFEST_SHA256,
        eligibility_artifact_sha256=ACCEPTED_ELIGIBILITY_ARTIFACT_SHA256,
        eligibility_audit_manifest_sha256=ACCEPTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256,
        eligibility_policy_manifest_sha256=ACCEPTED_ELIGIBILITY_POLICY_MANIFEST_SHA256,
        parser_bundle_fingerprint=ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
        stage06_candidate_rows=ACCEPTED_STAGE06_REGISTRY_ROWS,
        stage06_occurrences=ACCEPTED_STAGE06_OCCURRENCES,
        stage06_standard_occurrences=ACCEPTED_STAGE06_STANDARD_OCCURRENCES,
        stage06_native_occurrences=ACCEPTED_STAGE06_NATIVE_OCCURRENCES,
        eligible_candidates=ACCEPTED_ELIGIBLE_CANDIDATES,
        unresolved_candidates=ACCEPTED_UNRESOLVED_CANDIDATES,
    )


def validate_stage07_evidence_binding(
    binding: Stage07EvidenceBinding, *, authoritative_development: bool
) -> None:
    for value in (
        binding.stage06_manifest_sha256,
        binding.stage07_v1_manifest_sha256,
        binding.eligibility_artifact_sha256,
        binding.eligibility_audit_manifest_sha256,
        binding.eligibility_policy_manifest_sha256,
        binding.parser_bundle_fingerprint,
    ):
        _digest(value)
    counts = (
        binding.stage06_candidate_rows,
        binding.stage06_occurrences,
        binding.stage06_standard_occurrences,
        binding.stage06_native_occurrences,
        binding.eligible_candidates,
        binding.unresolved_candidates,
    )
    if any(isinstance(value, bool) or value < 0 for value in counts):
        _fail("INVALID_ROW_COUNT", "An evidence-only binding count is invalid")
    if binding.stage06_occurrences != (
        binding.stage06_standard_occurrences + binding.stage06_native_occurrences
    ) or binding.stage06_candidate_rows != (
        binding.eligible_candidates + binding.unresolved_candidates
    ):
        _fail("TOTALITY_FAILURE", "Evidence-only binding totals differ")
    if authoritative_development and binding != accepted_stage07_evidence_binding():
        _fail("AUTHORITATIVE_DEVELOPMENT_BINDING_MISMATCH", "Evidence binding differs")


def stage07_evidence_contract_fingerprint(binding: Stage07EvidenceBinding) -> str:
    validate_stage07_evidence_binding(binding, authoritative_development=False)
    payload = {
        "contract": STAGE07_EVIDENCE_CONTRACT_VERSION,
        "profile": STAGE07_EVIDENCE_PROFILE_VERSION,
        "schema": STAGE07_EVIDENCE_SCHEMA_VERSION,
        "schema_fingerprint": stage07_evidence_schema_fingerprint(),
        "binding": binding.to_dict(),
        "technical_status_vocabulary": list(STAGE07_STATUS_VOCABULARY),
        "warning_status_vocabulary": list(STRUCTURAL_WARNING_STATUSES),
        "warning_feature_version": STRUCTURAL_WARNING_FEATURE_VERSION,
        "warning_feature_source_sha256": STRUCTURAL_WARNING_SOURCE_SHA256,
        "historical_readiness_rule": READINESS_RULE_VERSION,
        "readiness_status_fields_published": False,
        "semantic_trust_claims": False,
        "parser_calls": 0,
        "stage07_v1_raw_output_preserved": True,
        "exact_stage06_candidate_preserved": True,
    }
    digest = hashlib.sha256(_CONTRACT_DOMAIN)
    encoded = _canonical_json(payload)
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    return digest.hexdigest()


def _schema_metadata(
    binding: Stage07EvidenceBinding, contract_fingerprint: str
) -> dict[bytes, bytes]:
    return {
        b"stage07_contract_version": STAGE07_EVIDENCE_CONTRACT_VERSION.encode("ascii"),
        b"stage07_profile_version": STAGE07_EVIDENCE_PROFILE_VERSION.encode("ascii"),
        b"stage07_schema_version": STAGE07_EVIDENCE_SCHEMA_VERSION.encode("ascii"),
        b"stage07_schema_fingerprint": stage07_evidence_schema_fingerprint().encode(
            "ascii"
        ),
        b"stage07_contract_fingerprint": contract_fingerprint.encode("ascii"),
        b"stage07_v1_manifest_sha256": binding.stage07_v1_manifest_sha256.encode(
            "ascii"
        ),
        b"parser_bundle_fingerprint": binding.parser_bundle_fingerprint.encode("ascii"),
        b"semantic_trust_claims": b"false",
    }


@dataclass(frozen=True, slots=True)
class Stage07EvidenceConfig:
    stage06_output_directory: Path
    stage07_v1_output_directory: Path
    eligibility_artifact: Path
    eligibility_audit_manifest: Path
    output_directory: Path
    execution_git_sha: str
    binding: Stage07EvidenceBinding = accepted_stage07_evidence_binding()
    authoritative_development: bool = True
    production: bool = True
    input_batch_rows: int = 64
    output_batch_rows: int = 64
    target_batch_bytes: int = 128 * 1024 * 1024
    output_shard_rows: int = 4_096
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        validate_stage07_evidence_binding(
            self.binding, authoritative_development=self.authoritative_development
        )
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA is malformed")
        for value in (
            self.input_batch_rows,
            self.output_batch_rows,
            self.target_batch_bytes,
            self.output_shard_rows,
        ):
            if isinstance(value, bool) or value < 1:
                _fail("INVALID_BATCH_SIZE", "A bounded evidence size is invalid")
        _reject_holdout_paths(
            self.stage06_output_directory,
            self.stage07_v1_output_directory,
            self.eligibility_artifact,
            self.eligibility_audit_manifest,
            self.output_directory,
        )
        for key, operational_value in (self.operational_metadata or {}).items():
            if key not in {"execution_site", "slurm_job_id"} or not operational_value:
                _fail("INVALID_OPERATIONAL_METADATA", "Operational metadata differs")


@dataclass(frozen=True, slots=True)
class Stage07EvidenceOutcome:
    output_directory: Path
    manifest_sha256: str
    logical_dataset_sha256_v2: str
    schema_fingerprint: str
    contract_fingerprint: str
    candidate_count: int
    shard_count: int
    metrics: Mapping[str, object]
    publication_validation_milliseconds: int = 0


@dataclass(frozen=True, slots=True)
class _ValidatedInputs:
    stage06_registry_paths: tuple[Path, ...]
    stage06_row_map_paths: tuple[Path, ...]
    stage07_v1_paths: tuple[Path, ...]
    eligibility_path: Path
    stage07_v1_identity: Mapping[str, object]


def _validate_eligibility(config: Stage07EvidenceConfig) -> None:
    _require_file(config.eligibility_artifact, "ELIGIBILITY_ARTIFACT_INVALID")
    _require_mode(config.eligibility_artifact, 0o600, "PERMISSION_FAILURE")
    if (
        _sha256_file(config.eligibility_artifact)
        != config.binding.eligibility_artifact_sha256
    ):
        _fail("ELIGIBILITY_ARTIFACT_MISMATCH", "Eligibility artifact SHA differs")
    _require_file(config.eligibility_audit_manifest, "ELIGIBILITY_MANIFEST_INVALID")
    _require_mode(config.eligibility_audit_manifest, 0o600, "PERMISSION_FAILURE")
    if (
        _sha256_file(config.eligibility_audit_manifest)
        != config.binding.eligibility_audit_manifest_sha256
    ):
        _fail("ELIGIBILITY_MANIFEST_MISMATCH", "Eligibility manifest SHA differs")
    manifest = _load_json(
        config.eligibility_audit_manifest, "ELIGIBILITY_MANIFEST_INVALID"
    )
    artifacts = manifest.get("artifacts")
    if (
        manifest.get("version") != "stage07_country_eligibility_audit_manifest_v1"
        or manifest.get("status") != "STAGE07_COUNTRY_ELIGIBILITY_AUDIT_COMPLETE"
        or manifest.get("eligibility_manifest_sha256")
        != config.binding.eligibility_policy_manifest_sha256
        or not isinstance(artifacts, list)
        or not any(
            isinstance(item, dict)
            and item.get("relative_path") == config.eligibility_artifact.name
            and item.get("sha256") == config.binding.eligibility_artifact_sha256
            for item in artifacts
        )
    ):
        _fail("ELIGIBILITY_MANIFEST_MISMATCH", "Eligibility manifest binding differs")
    parquet = pq.ParquetFile(
        config.eligibility_artifact, page_checksum_verification=True
    )
    if not set(ELIGIBILITY_COLUMNS).issubset(parquet.schema_arrow.names):
        _fail("ELIGIBILITY_SCHEMA_MISMATCH", "Eligibility columns differ")


def _validated_inputs(config: Stage07EvidenceConfig) -> _ValidatedInputs:
    _validate_eligibility(config)
    stage06_manifest_path = config.stage06_output_directory / "stage06_manifest.json"
    _require_file(stage06_manifest_path, "STAGE06_MANIFEST_INVALID")
    _require_mode(stage06_manifest_path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(stage06_manifest_path) != config.binding.stage06_manifest_sha256:
        _fail("STAGE06_MANIFEST_SHA256_MISMATCH", "Stage 6 manifest differs")
    stage06_manifest = _load_json(stage06_manifest_path, "STAGE06_MANIFEST_INVALID")
    stage06_physical = stage06_manifest.get("physical_identity")
    if not isinstance(stage06_physical, dict):
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 physical identity is absent")
    stage06_registry = _stage06_manifest_artifacts(
        config.stage06_output_directory,
        stage06_physical,
        key="registry_artifacts",
        directory=STAGE06_REGISTRY_DIRECTORY,
    )
    stage06_row_map = _stage06_manifest_artifacts(
        config.stage06_output_directory,
        stage06_physical,
        key="row_map_artifacts",
        directory=STAGE06_ROW_MAP_DIRECTORY,
    )

    v1_manifest_path = config.stage07_v1_output_directory / STAGE07_V1_MANIFEST_NAME
    _require_file(v1_manifest_path, "STAGE07_V1_MANIFEST_INVALID")
    _require_mode(v1_manifest_path, 0o600, "PERMISSION_FAILURE")
    if _sha256_file(v1_manifest_path) != config.binding.stage07_v1_manifest_sha256:
        _fail("STAGE07_V1_MANIFEST_SHA256_MISMATCH", "Stage 7 v1 manifest differs")
    v1_manifest = _load_json(v1_manifest_path, "STAGE07_V1_MANIFEST_INVALID")
    scientific = v1_manifest.get("scientific_identity")
    physical = v1_manifest.get("physical_identity")
    if (
        not isinstance(scientific, dict)
        or not isinstance(physical, dict)
        or scientific.get("stage07_contract_version") != STAGE07_V1_CONTRACT_VERSION
        or scientific.get("stage07_profile_version") != STAGE07_V1_PROFILE_VERSION
        or scientific.get("candidate_count") != config.binding.stage06_candidate_rows
        or scientific.get("status_vocabulary") != list(STAGE07_STATUS_VOCABULARY)
    ):
        _fail("STAGE07_V1_BINDING_MISMATCH", "Stage 7 v1 scientific identity differs")
    stage06_binding = scientific.get("stage06_binding")
    if (
        not isinstance(stage06_binding, dict)
        or stage06_binding.get("stage06_manifest_sha256")
        != config.binding.stage06_manifest_sha256
        or stage06_binding.get("parser_bundle_fingerprint")
        != config.binding.parser_bundle_fingerprint
    ):
        _fail("STAGE07_V1_BINDING_MISMATCH", "Stage 7 v1 upstream binding differs")
    v1_artifacts = _stage07_v1_manifest_artifacts(
        config.stage07_v1_output_directory, physical
    )
    return _ValidatedInputs(
        stage06_registry_paths=tuple(
            config.stage06_output_directory / item.relative_path
            for item in stage06_registry
        ),
        stage06_row_map_paths=tuple(
            config.stage06_output_directory / item.relative_path
            for item in stage06_row_map
        ),
        stage07_v1_paths=tuple(
            config.stage07_v1_output_directory / item.relative_path
            for item in v1_artifacts
        ),
        eligibility_path=config.eligibility_artifact,
        stage07_v1_identity={
            "contract": scientific["stage07_contract_version"],
            "profile": scientific["stage07_profile_version"],
            "schema_fingerprint": scientific["stage07_schema_fingerprint"],
            "logical_dataset_sha256_v1": scientific[
                "stage07_logical_dataset_sha256_v1"
            ],
            "manifest_sha256": config.binding.stage07_v1_manifest_sha256,
            "parser_bundle_fingerprint": config.binding.parser_bundle_fingerprint,
        },
    )


def _rows(
    paths: Sequence[Path], columns: Sequence[str], batch_rows: int
) -> Iterable[tuple[pa.RecordBatch, int]]:
    for batch in _iter_batches(paths, columns, batch_rows):
        for index in range(batch.num_rows):
            yield batch, index


def _components_from_scalar(value: pa.Scalar) -> tuple[LibpostalComponent, ...]:
    raw = value.as_py()
    if not isinstance(raw, list):
        _fail("STAGE07_V1_STRUCTURE_INVALID", "Raw component list is malformed")
    result: list[LibpostalComponent] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("STAGE07_V1_STRUCTURE_INVALID", "A raw component is malformed")
        result.append(LibpostalComponent(label=item["label"], value=item["value"]))
    return tuple(result)


def _warning_values(
    applicability: str,
    technical_status: str,
    candidate: str,
    components: tuple[LibpostalComponent, ...],
) -> tuple[str, tuple[str, ...], StructuralSignals | None]:
    if applicability != PARSER_ELIGIBLE_COUNTRY:
        return STRUCTURAL_WARNINGS_NOT_EVALUATED, (), None
    if technical_status == PARSED_EMPTY:
        if components:
            _fail("TECHNICAL_STATUS_MISMATCH", "PARSED_EMPTY has components")
        return STRUCTURAL_WARNINGS_PRESENT, (REASON_PARSED_EMPTY,), None
    if technical_status != PARSED_NONEMPTY or not components:
        _fail("TECHNICAL_STATUS_MISMATCH", "PARSED_NONEMPTY has no components")
    signals = structural_signals(candidate, components)
    status = (
        STRUCTURAL_WARNINGS_PRESENT
        if signals.reason_codes
        else NO_STRUCTURAL_WARNINGS_DETECTED
    )
    return status, signals.reason_codes, signals


def _one_row_batch(
    stage06_batch: pa.RecordBatch,
    stage06_index: int,
    v1_batch: pa.RecordBatch,
    v1_index: int,
    eligibility: Mapping[str, object],
    warning_status: str,
    reason_codes: tuple[str, ...],
    signals: StructuralSignals | None,
    schema: pa.Schema,
) -> pa.RecordBatch:
    arrays: list[pa.Array] = [
        stage06_batch.column(index).slice(stage06_index, 1)
        for index in range(len(REGISTRY_COLUMNS))
    ]
    arrays.extend(
        (
            pa.array((eligibility["country_provenance_status"],), type=pa.string()),
            pa.array((eligibility["unanimous_country_code"],), type=pa.string()),
            pa.array(
                (eligibility["valid_country_occurrence_count"],), type=pa.uint64()
            ),
            pa.array(
                (eligibility["missing_country_occurrence_count"],), type=pa.uint64()
            ),
            pa.array(
                (eligibility["invalid_country_occurrence_count"],), type=pa.uint64()
            ),
            pa.array((eligibility["distinct_valid_country_count"],), type=pa.uint32()),
            pa.array((eligibility["libpostal_eligibility"],), type=pa.string()),
            v1_batch.column(5).slice(v1_index, 1),
            pa.array((PARSER_EXECUTION_ORIGIN,), type=pa.string()),
            v1_batch.column(6).slice(v1_index, 1),
            pa.array((warning_status,), type=pa.string()),
            pa.array((reason_codes,), type=warning_reason_type()),
            pa.array(
                (None if signals is None else signals.raw_ordered_substrings,),
                type=pa.bool_(),
            ),
            pa.array(
                (None if signals is None else signals.lexical_numeric_stream_equal,),
                type=pa.bool_(),
            ),
        )
    )
    numeric = (
        None
        if signals is None
        else (
            signals.internal_boundary_count,
            signals.internal_single_codepoint_fragment_count,
            signals.maximum_components_per_lexical_run,
            signals.adjacent_repeated_label_internal_boundary_count,
            signals.candidate_lexical_numeric_codepoints,
            signals.output_lexical_numeric_codepoints,
        )
    )
    arrays.extend(
        pa.array((None if numeric is None else numeric[index],), type=pa.uint64())
        for index in range(6)
    )
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


class _LogicalHasher:
    def __init__(self, contract_fingerprint: str) -> None:
        self._digest = hashlib.sha256(_LOGICAL_DOMAIN)
        self._digest.update(_digest(contract_fingerprint))

    def _bytes(self, value: bytes) -> None:
        self._digest.update(len(value).to_bytes(8, "big"))
        self._digest.update(value)

    def _text(self, value: str) -> None:
        self._bytes(value.encode("utf-8", errors="strict"))

    def _optional_text(self, value: str | None) -> None:
        self._digest.update(b"\x00" if value is None else b"\x01")
        if value is not None:
            self._text(value)

    def _optional_bool(self, value: bool | None) -> None:
        self._digest.update(
            b"\x00" if value is None else (b"\x02" if value else b"\x01")
        )

    def _optional_uint(self, value: int | None) -> None:
        self._digest.update(b"\x00" if value is None else b"\x01")
        if value is not None:
            self._digest.update(struct.pack(">Q", value))

    def update(
        self,
        *,
        candidate_id: bytes,
        candidate: str,
        counts: Sequence[int],
        country_status: str,
        country_code: str | None,
        country_counts: Sequence[int],
        applicability: str,
        technical_status: str,
        components: Sequence[LibpostalComponent],
        warning_status: str,
        reasons: Sequence[str],
        signals: StructuralSignals | None,
    ) -> None:
        self._bytes(candidate_id)
        self._text(candidate)
        for value in (*counts, *country_counts):
            self._digest.update(struct.pack(">Q", value))
        self._text(country_status)
        self._optional_text(country_code)
        self._text(applicability)
        self._text(technical_status)
        self._text(PARSER_EXECUTION_ORIGIN)
        self._digest.update(struct.pack(">Q", len(components)))
        for component in components:
            self._text(component.label)
            self._text(component.value)
        self._text(warning_status)
        self._digest.update(struct.pack(">Q", len(reasons)))
        for reason in reasons:
            self._text(reason)
        self._optional_bool(None if signals is None else signals.raw_ordered_substrings)
        self._optional_bool(
            None if signals is None else signals.lexical_numeric_stream_equal
        )
        for optional_value in (
            None if signals is None else signals.internal_boundary_count,
            None
            if signals is None
            else signals.internal_single_codepoint_fragment_count,
            None if signals is None else signals.maximum_components_per_lexical_run,
            None
            if signals is None
            else signals.adjacent_repeated_label_internal_boundary_count,
            None if signals is None else signals.candidate_lexical_numeric_codepoints,
            None if signals is None else signals.output_lexical_numeric_codepoints,
        ):
            self._optional_uint(optional_value)

    def hexdigest(self) -> str:
        return self._digest.hexdigest()


def _dataset_fingerprint(contract: str, registry: str, rows: int) -> str:
    digest = hashlib.sha256(_DATASET_DOMAIN)
    digest.update(_digest(contract))
    digest.update(_digest(registry))
    digest.update(struct.pack(">Q", rows))
    return digest.hexdigest()


def _eligibility_values(batch: pa.RecordBatch, index: int) -> dict[str, object]:
    values = {
        name: batch.column(position)[index].as_py()
        for position, name in enumerate(ELIGIBILITY_COLUMNS)
    }
    candidate_id = values["candidate_id"]
    if not isinstance(candidate_id, bytes):
        _fail("ELIGIBILITY_STRUCTURE_INVALID", "Eligibility candidate ID differs")
    for key in (
        "occurrence_count",
        "standard_occurrence_count",
        "native_occurrence_count",
        "valid_country_occurrence_count",
        "missing_country_occurrence_count",
        "invalid_country_occurrence_count",
        "distinct_valid_country_count",
    ):
        if isinstance(values[key], bool) or not isinstance(values[key], int):
            _fail("ELIGIBILITY_STRUCTURE_INVALID", "Eligibility count differs")
    if (
        values["country_provenance_status"] not in COUNTRY_PROVENANCE_STATUSES
        or values["libpostal_eligibility"] not in PARSER_ELIGIBILITY_STATUSES
        or values["stage07_parse_status"] not in STAGE07_STATUS_VOCABULARY
        or (
            values["unanimous_country_code"] is not None
            and not isinstance(values["unanimous_country_code"], str)
        )
    ):
        _fail("ELIGIBILITY_STRUCTURE_INVALID", "Eligibility status differs")
    return values


def _write_row(
    *,
    stage06_batch: pa.RecordBatch,
    stage06_index: int,
    v1_batch: pa.RecordBatch,
    v1_index: int,
    eligibility_batch: pa.RecordBatch,
    eligibility_index: int,
    schema: pa.Schema,
    logical: _LogicalHasher,
) -> tuple[pa.RecordBatch, str, tuple[str, ...]]:
    eligibility = _eligibility_values(eligibility_batch, eligibility_index)
    candidate_id = stage06_batch.column(0)[stage06_index].as_py()
    candidate = stage06_batch.column(1)[stage06_index].as_py()
    counts = tuple(
        int(stage06_batch.column(position)[stage06_index].as_py())
        for position in range(2, 5)
    )
    if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
        _fail("STAGE06_STRUCTURE_INVALID", "Stage 6 candidate structure differs")
    for position in range(len(REGISTRY_COLUMNS)):
        if (
            stage06_batch.column(position)[stage06_index]
            != v1_batch.column(position)[v1_index]
        ):
            _fail("STAGE07_V1_UPSTREAM_MISMATCH", "Stage 7 v1 changed Stage 6")
    if candidate_id != eligibility["candidate_id"] or counts != (
        eligibility["occurrence_count"],
        eligibility["standard_occurrence_count"],
        eligibility["native_occurrence_count"],
    ):
        _fail("ELIGIBILITY_UPSTREAM_MISMATCH", "Eligibility row differs from Stage 6")
    technical_status = v1_batch.column(5)[v1_index].as_py()
    if (
        not isinstance(technical_status, str)
        or technical_status != eligibility["stage07_parse_status"]
    ):
        _fail("TECHNICAL_STATUS_MISMATCH", "Eligibility/v1 technical status differs")
    components = _components_from_scalar(v1_batch.column(6)[v1_index])
    if (technical_status == PARSED_NONEMPTY) != bool(components):
        _fail("TECHNICAL_STATUS_MISMATCH", "Stage 7 v1 status/list differs")
    applicability = cast(str, eligibility["libpostal_eligibility"])
    warning_status, reasons, signals = _warning_values(
        applicability, technical_status, candidate, components
    )
    country_counts = (
        cast(int, eligibility["valid_country_occurrence_count"]),
        cast(int, eligibility["missing_country_occurrence_count"]),
        cast(int, eligibility["invalid_country_occurrence_count"]),
        cast(int, eligibility["distinct_valid_country_count"]),
    )
    logical.update(
        candidate_id=candidate_id,
        candidate=candidate,
        counts=counts,
        country_status=cast(str, eligibility["country_provenance_status"]),
        country_code=cast(str | None, eligibility["unanimous_country_code"]),
        country_counts=country_counts,
        applicability=applicability,
        technical_status=technical_status,
        components=components,
        warning_status=warning_status,
        reasons=reasons,
        signals=signals,
    )
    return (
        _one_row_batch(
            stage06_batch,
            stage06_index,
            v1_batch,
            v1_index,
            eligibility,
            warning_status,
            reasons,
            signals,
            schema,
        ),
        warning_status,
        reasons,
    )


def _next_or_fail(
    iterator: Iterator[tuple[pa.RecordBatch, int]], code: str
) -> tuple[pa.RecordBatch, int]:
    try:
        return next(iterator)
    except StopIteration:
        _fail(code, "An upstream evidence stream ended early")


def materialize_stage07_evidence(
    config: Stage07EvidenceConfig,
) -> Stage07EvidenceOutcome:
    """Publish the bounded evidence-only projection atomically."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-parser-evidence-v2")
    _validate_runtime()
    inputs = _validated_inputs(config)
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Evidence output already exists")
    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Evidence temporary output already exists")
    old_umask = os.umask(0o077)
    manifest_sha = ""
    try:
        temporary.mkdir(mode=0o700)
        registry_directory = temporary / STAGE07_EVIDENCE_REGISTRY_DIRECTORY
        registry_directory.mkdir(parents=True, mode=0o700)
        registry_directory.parent.chmod(0o700)
        (temporary / STAGE07_EVIDENCE_IN_PROGRESS_NAME).write_text(
            "in_progress\n", encoding="ascii"
        )
        (temporary / STAGE07_EVIDENCE_IN_PROGRESS_NAME).chmod(0o600)
        contract = stage07_evidence_contract_fingerprint(config.binding)
        schema = stage07_evidence_schema().with_metadata(
            _schema_metadata(config.binding, contract)
        )
        logical = _LogicalHasher(contract)
        stage06_rows = iter(
            _rows(
                inputs.stage06_registry_paths, REGISTRY_COLUMNS, config.input_batch_rows
            )
        )
        v1_rows = iter(
            _rows(
                inputs.stage07_v1_paths,
                (
                    *REGISTRY_COLUMNS,
                    "stage07_parse_status",
                    "stage07_libpostal_components",
                ),
                config.input_batch_rows,
            )
        )
        eligibility_rows = iter(
            _rows(
                (inputs.eligibility_path,), ELIGIBILITY_COLUMNS, config.input_batch_rows
            )
        )
        artifacts: list[Stage07ArtifactIdentity] = []
        pending: list[pa.RecordBatch] = []
        pending_bytes = 0
        writer: pq.ParquetWriter | None = None
        writer_path: Path | None = None
        shard_rows = 0
        shard_number = 0
        rows = 0
        occurrences = 0
        standard_occurrences = 0
        native_occurrences = 0
        applicability_counts: Counter[str] = Counter()
        technical_counts: Counter[str] = Counter()
        warning_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()

        def start_writer() -> None:
            nonlocal writer, writer_path, shard_number, shard_rows
            shard_number += 1
            shard_rows = 0
            writer_path = registry_directory / f"part-{shard_number:06d}.parquet"
            writer = pq.ParquetWriter(
                writer_path,
                schema,
                compression="zstd",
                use_dictionary=False,
                write_statistics=True,
                write_page_checksum=True,
                data_page_size=1024 * 1024,
                write_batch_size=256,
            )

        def flush_pending() -> None:
            nonlocal pending, pending_bytes
            if not pending:
                return
            if writer is None:
                start_writer()
            assert writer is not None
            table = pa.Table.from_batches(pending, schema=schema)
            writer.write_table(
                table, row_group_size=min(config.output_batch_rows, table.num_rows)
            )
            pending = []
            pending_bytes = 0

        def close_writer() -> None:
            nonlocal writer, writer_path
            if writer is None or writer_path is None:
                return
            flush_pending()
            writer.close()
            writer_path.chmod(0o600)
            artifacts.append(_artifact_identity(temporary, writer_path, shard_rows))
            writer = None
            writer_path = None

        try:
            while True:
                try:
                    stage06_batch, stage06_index = next(stage06_rows)
                except StopIteration:
                    break
                v1_batch, v1_index = _next_or_fail(v1_rows, "STAGE07_V1_ROW_MISMATCH")
                eligibility_batch, eligibility_index = _next_or_fail(
                    eligibility_rows, "ELIGIBILITY_ROW_MISMATCH"
                )
                row_batch, warning_status, reasons = _write_row(
                    stage06_batch=stage06_batch,
                    stage06_index=stage06_index,
                    v1_batch=v1_batch,
                    v1_index=v1_index,
                    eligibility_batch=eligibility_batch,
                    eligibility_index=eligibility_index,
                    schema=schema,
                    logical=logical,
                )
                if writer is None:
                    start_writer()
                if shard_rows == config.output_shard_rows:
                    close_writer()
                    start_writer()
                pending.append(row_batch)
                pending_bytes += row_batch.nbytes
                shard_rows += 1
                rows += 1
                counts = [
                    int(stage06_batch.column(index)[stage06_index].as_py())
                    for index in range(2, 5)
                ]
                occurrences += counts[0]
                standard_occurrences += counts[1]
                native_occurrences += counts[2]
                applicability = eligibility_batch.column(
                    ELIGIBILITY_COLUMNS.index("libpostal_eligibility")
                )[eligibility_index].as_py()
                technical = v1_batch.column(5)[v1_index].as_py()
                assert isinstance(applicability, str) and isinstance(technical, str)
                applicability_counts[applicability] += 1
                technical_counts[technical] += 1
                warning_counts[warning_status] += 1
                reason_counts.update(reasons)
                if (
                    len(pending) >= config.output_batch_rows
                    or pending_bytes >= config.target_batch_bytes
                    or shard_rows == config.output_shard_rows
                ):
                    flush_pending()
            try:
                next(v1_rows)
                _fail("STAGE07_V1_ROW_MISMATCH", "Stage 7 v1 contains added rows")
            except StopIteration:
                pass
            try:
                next(eligibility_rows)
                _fail("ELIGIBILITY_ROW_MISMATCH", "Eligibility contains added rows")
            except StopIteration:
                pass
            close_writer()
        finally:
            if writer is not None:
                writer.close()
        if (
            rows != config.binding.stage06_candidate_rows
            or occurrences != config.binding.stage06_occurrences
            or standard_occurrences != config.binding.stage06_standard_occurrences
            or native_occurrences != config.binding.stage06_native_occurrences
            or applicability_counts[PARSER_ELIGIBLE_COUNTRY]
            != config.binding.eligible_candidates
            or sum(applicability_counts.values())
            - applicability_counts[PARSER_ELIGIBLE_COUNTRY]
            != config.binding.unresolved_candidates
        ):
            _fail("TOTALITY_FAILURE", "Evidence-only totality differs")
        registry_logical = logical.hexdigest()
        dataset_logical = _dataset_fingerprint(contract, registry_logical, rows)
        metrics: dict[str, object] = {
            "CANDIDATE_ROWS": rows,
            "INPUT_OCCURRENCES": occurrences,
            "STANDARD_OCCURRENCES": standard_occurrences,
            "NATIVE_OCCURRENCES": native_occurrences,
            "APPLICABILITY_STATUS_COUNTS": dict(sorted(applicability_counts.items())),
            "TECHNICAL_STATUS_COUNTS": dict(sorted(technical_counts.items())),
            "STRUCTURAL_WARNING_STATUS_COUNTS": dict(sorted(warning_counts.items())),
            "STRUCTURAL_WARNING_REASON_COUNTS": dict(sorted(reason_counts.items())),
            "PARSER_CALLS": 0,
            "SEMANTIC_TRUST_CLAIMS": 0,
        }
        manifest = {
            "stage07_manifest_version": STAGE07_EVIDENCE_MANIFEST_VERSION,
            "status": "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_MATERIALIZED",
            "scientific_identity": {
                "stage07_contract_version": STAGE07_EVIDENCE_CONTRACT_VERSION,
                "stage07_profile_version": STAGE07_EVIDENCE_PROFILE_VERSION,
                "stage07_schema_version": STAGE07_EVIDENCE_SCHEMA_VERSION,
                "stage07_schema_fingerprint": stage07_evidence_schema_fingerprint(),
                "stage07_contract_fingerprint": contract,
                "stage07_registry_logical_sha256_v2": registry_logical,
                "stage07_logical_dataset_sha256_v2": dataset_logical,
                "input_binding": config.binding.to_dict(),
                "stage07_v1_identity": dict(inputs.stage07_v1_identity),
                "technical_status_vocabulary": list(STAGE07_STATUS_VOCABULARY),
                "parser_execution_origin": PARSER_EXECUTION_ORIGIN,
                "structural_warning_status_vocabulary": list(
                    STRUCTURAL_WARNING_STATUSES
                ),
                "structural_warning_feature_version": STRUCTURAL_WARNING_FEATURE_VERSION,
                "structural_warning_feature_source_sha256": STRUCTURAL_WARNING_SOURCE_SHA256,
                "historical_failed_readiness_rule": READINESS_RULE_VERSION,
                "component_readiness_status_published": False,
                "raw_components_type": str(component_list_type()),
                "candidate_count": rows,
            },
            "scientific_semantics": {
                "guarantees": [
                    "EXACT_STAGE06_CANDIDATE_PRESERVATION",
                    "EXACT_RAW_ORDERED_STAGE07_V1_LIBPOSTAL_OUTPUT_PRESERVATION",
                    "PARSER_BUNDLE_AND_LINEAGE_PROVENANCE",
                    "COUNTRY_APPLICABILITY_EVIDENCE",
                    "EXACT_HISTORICAL_TECHNICAL_EXECUTION_STATUS",
                    "DETERMINISTIC_STRUCTURAL_WARNING_FEATURES_WHERE_APPLICABLE",
                    "FULL_OCCURRENCE_MAP_BACK",
                    "NO_SOURCE_INFORMATION_LOSS",
                ],
                "does_not_guarantee": [
                    "CORRECT_SEMANTIC_COMPONENT_LABELS",
                    "CORRECT_COMPONENT_BOUNDARIES",
                    "POSTAL_OR_ADDRESS_VALIDITY",
                    "GEOGRAPHIC_TRUTH",
                    "NO_WARNING_IMPLIES_SEMANTIC_CORRECTNESS",
                ],
                "raw_libpostal_components_are": "HYPOTHESES_AND_EVIDENCE_NOT_SOURCE_TRUTH",
            },
            "physical_identity": {
                "registry_artifacts": [item.to_dict() for item in artifacts],
                "owner_only_permissions": True,
                "atomic_publication": True,
                "bounded_memory_architecture": {
                    "ordered_three_way_streaming_merge": True,
                    "one_candidate_nested_result_deserialized_at_a_time": True,
                    "bounded_arrow_batches": True,
                    "population_sized_python_registry": False,
                    "population_sized_python_component_buffer": False,
                    "input_batch_rows": config.input_batch_rows,
                    "output_batch_rows": config.output_batch_rows,
                    "target_batch_bytes": config.target_batch_bytes,
                    "output_shard_rows": config.output_shard_rows,
                },
            },
            "development_metrics": metrics,
            "validation": {
                "validation_contract_version": STAGE07_EVIDENCE_VALIDATION_VERSION,
                "exact_stage06_registry_preservation": "PASS",
                "exact_stage07_v1_status_preservation": "PASS",
                "exact_raw_ordered_component_preservation": "PASS",
                "country_applicability_binding": "PASS",
                "warning_rule_reproducibility": "PASS",
                "no_component_readiness_gate": "PASS",
                "zero_semantic_trust_claims": "PASS",
                "zero_parser_calls": "PASS",
                "bounded_streaming": "PASS",
                "holdout_exclusion": "PASS",
                "production_exclusion": "PASS",
                "stage08_not_started": "PASS",
            },
            "operational_provenance": {
                "execution_git_sha": config.execution_git_sha,
                "created_at_utc": _utc_now(),
                "python_version": platform.python_version(),
                "pyarrow_version": pa.__version__,
                "duckdb_version": duckdb.__version__,
                "parser_calls": 0,
                **dict(config.operational_metadata or {}),
            },
        }
        _write_json_exclusive(temporary / STAGE07_EVIDENCE_MANIFEST_NAME, manifest)
        manifest_sha = _sha256_file(temporary / STAGE07_EVIDENCE_MANIFEST_NAME)
        _write_json_exclusive(
            temporary / STAGE07_EVIDENCE_SUCCESS_NAME,
            {
                "status": "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_MATERIALIZED",
                "manifest_sha256": manifest_sha,
                "logical_dataset_sha256_v2": dataset_logical,
                "schema_fingerprint": stage07_evidence_schema_fingerprint(),
                "candidate_count": rows,
                "shard_count": len(artifacts),
            },
        )
        (temporary / STAGE07_EVIDENCE_IN_PROGRESS_NAME).unlink()
        for directory in (registry_directory, registry_directory.parent, temporary):
            _fsync_directory(directory)
        os.replace(temporary, config.output_directory)
        _fsync_directory(parent)
    except (Stage07ValidationError, duckdb.Error, pa.ArrowException):
        raise
    except OSError as error:
        raise Stage07ValidationError(
            "STAGE07_EVIDENCE_PUBLICATION_FAILURE", "Evidence publication failed"
        ) from error
    finally:
        os.umask(old_umask)
    validation_started = time.perf_counter()
    outcome = validate_stage07_evidence_bundle(
        config.output_directory,
        expected_manifest_sha256=manifest_sha,
        config=replace(
            config, output_directory=config.output_directory, production=False
        ),
    )
    return replace(
        outcome,
        publication_validation_milliseconds=round(
            (time.perf_counter() - validation_started) * 1_000
        ),
    )


def _output_artifacts(
    root: Path, physical: Mapping[str, object]
) -> tuple[Stage07ArtifactIdentity, ...]:
    values = physical.get("registry_artifacts")
    if not isinstance(values, list) or not values:
        _fail("STAGE07_EVIDENCE_MANIFEST_INVALID", "Registry artifacts are absent")
    artifacts: list[Stage07ArtifactIdentity] = []
    for sequence, raw in enumerate(values, start=1):
        if not isinstance(raw, dict):
            _fail("STAGE07_EVIDENCE_MANIFEST_INVALID", "Artifact entry is malformed")
        try:
            item = Stage07ArtifactIdentity(
                relative_path=str(raw["relative_path"]),
                size_bytes=int(raw["size_bytes"]),
                sha256=str(raw["sha256"]),
                row_count=int(raw["row_count"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise Stage07ValidationError(
                "STAGE07_EVIDENCE_MANIFEST_INVALID", "Artifact fields differ"
            ) from error
        if (
            item.relative_path
            != f"{STAGE07_EVIDENCE_REGISTRY_DIRECTORY}/part-{sequence:06d}.parquet"
        ):
            _fail("STAGE07_EVIDENCE_MANIFEST_INVALID", "Artifact order differs")
        _digest(item.sha256)
        path = root / item.relative_path
        _require_file(path, "STAGE07_EVIDENCE_ARTIFACT_INVALID")
        _require_mode(path, 0o600, "PERMISSION_FAILURE")
        if (
            path.stat(follow_symlinks=False).st_size != item.size_bytes
            or _sha256_file(path) != item.sha256
        ):
            _fail("STAGE07_EVIDENCE_ARTIFACT_MISMATCH", "Artifact identity differs")
        artifacts.append(item)
    return tuple(artifacts)


def _output_warning_values(batch: pa.RecordBatch, index: int) -> tuple[object, ...]:
    start = batch.schema.get_field_index(WARNING_STATUS_FIELD)
    return tuple(
        batch.column(position)[index].as_py()
        for position in range(start, batch.num_columns)
    )


def validate_stage07_evidence_bundle(
    output_directory: Path,
    *,
    expected_manifest_sha256: str,
    config: Stage07EvidenceConfig,
) -> Stage07EvidenceOutcome:
    """Independently reopen and replay every evidence-only row."""
    config.validate()
    _validate_runtime()
    _digest(expected_manifest_sha256)
    _reject_holdout_paths(output_directory)
    inputs = _validated_inputs(config)
    _require_directory(output_directory, "STAGE07_EVIDENCE_OUTPUT_INVALID")
    _require_mode(output_directory, 0o700, "PERMISSION_FAILURE")
    manifest_path = output_directory / STAGE07_EVIDENCE_MANIFEST_NAME
    success_path = output_directory / STAGE07_EVIDENCE_SUCCESS_NAME
    _require_file(manifest_path, "STAGE07_EVIDENCE_TERMINAL_MISSING")
    _require_file(success_path, "STAGE07_EVIDENCE_TERMINAL_MISSING")
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        _fail("STAGE07_EVIDENCE_MANIFEST_SHA256_MISMATCH", "Manifest SHA differs")
    manifest = _load_json(manifest_path, "STAGE07_EVIDENCE_MANIFEST_INVALID")
    success = _load_json(success_path, "STAGE07_EVIDENCE_SUCCESS_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    validation = manifest.get("validation")
    semantics = manifest.get("scientific_semantics")
    if not all(
        isinstance(value, dict)
        for value in (scientific, physical, validation, semantics)
    ):
        _fail("STAGE07_EVIDENCE_MANIFEST_INVALID", "Manifest sections differ")
    scientific = cast(dict[str, object], scientific)
    physical = cast(dict[str, object], physical)
    validation = cast(dict[str, object], validation)
    semantics = cast(dict[str, object], semantics)
    contract = stage07_evidence_contract_fingerprint(config.binding)
    if (
        manifest.get("stage07_manifest_version") != STAGE07_EVIDENCE_MANIFEST_VERSION
        or manifest.get("status")
        != "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("status")
        != "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or success.get("manifest_sha256") != expected_manifest_sha256
        or scientific.get("stage07_contract_version")
        != STAGE07_EVIDENCE_CONTRACT_VERSION
        or scientific.get("stage07_profile_version") != STAGE07_EVIDENCE_PROFILE_VERSION
        or scientific.get("stage07_schema_version") != STAGE07_EVIDENCE_SCHEMA_VERSION
        or scientific.get("stage07_schema_fingerprint")
        != stage07_evidence_schema_fingerprint()
        or scientific.get("stage07_contract_fingerprint") != contract
        or scientific.get("input_binding") != config.binding.to_dict()
        or scientific.get("stage07_v1_identity") != dict(inputs.stage07_v1_identity)
        or scientific.get("component_readiness_status_published") is not False
        or scientific.get("technical_status_vocabulary")
        != list(STAGE07_STATUS_VOCABULARY)
        or scientific.get("structural_warning_status_vocabulary")
        != list(STRUCTURAL_WARNING_STATUSES)
        or scientific.get("raw_components_type") != str(component_list_type())
        or semantics.get("raw_libpostal_components_are")
        != "HYPOTHESES_AND_EVIDENCE_NOT_SOURCE_TRUTH"
        or validation.get("validation_contract_version")
        != STAGE07_EVIDENCE_VALIDATION_VERSION
        or any(
            value != "PASS"
            for key, value in validation.items()
            if key != "validation_contract_version"
        )
    ):
        _fail("STAGE07_EVIDENCE_IDENTITY_MISMATCH", "Evidence identity differs")
    artifacts = _output_artifacts(output_directory, physical)
    expected_directories = {"registry", STAGE07_EVIDENCE_REGISTRY_DIRECTORY}
    expected_files = {
        STAGE07_EVIDENCE_MANIFEST_NAME,
        STAGE07_EVIDENCE_SUCCESS_NAME,
        *(item.relative_path for item in artifacts),
    }
    directories, files = _topology(output_directory)
    if directories != expected_directories or files != expected_files:
        _fail("STAGE07_EVIDENCE_ARTIFACT_MISMATCH", "Output topology differs")
    bounded = physical.get("bounded_memory_architecture")
    if (
        physical.get("owner_only_permissions") is not True
        or physical.get("atomic_publication") is not True
        or not isinstance(bounded, dict)
        or bounded.get("ordered_three_way_streaming_merge") is not True
        or bounded.get("one_candidate_nested_result_deserialized_at_a_time") is not True
        or bounded.get("population_sized_python_registry") is not False
    ):
        _fail("BOUNDED_MEMORY_CONTRACT_MISMATCH", "Bounded architecture differs")
    schema = stage07_evidence_schema().with_metadata(
        _schema_metadata(config.binding, contract)
    )
    output_paths = tuple(output_directory / item.relative_path for item in artifacts)
    for path in output_paths:
        if not pq.ParquetFile(
            path, page_checksum_verification=True
        ).schema_arrow.equals(schema, check_metadata=True):
            _fail("OUTPUT_SCHEMA_MISMATCH", "Evidence schema differs")
    stage06_rows = iter(
        _rows(inputs.stage06_registry_paths, REGISTRY_COLUMNS, config.input_batch_rows)
    )
    v1_rows = iter(
        _rows(
            inputs.stage07_v1_paths,
            (*REGISTRY_COLUMNS, "stage07_parse_status", "stage07_libpostal_components"),
            config.input_batch_rows,
        )
    )
    eligibility_rows = iter(
        _rows((inputs.eligibility_path,), ELIGIBILITY_COLUMNS, config.input_batch_rows)
    )
    output_rows = iter(_rows(output_paths, schema.names, config.input_batch_rows))
    logical = _LogicalHasher(contract)
    rows = 0
    applicability_counts: Counter[str] = Counter()
    technical_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    while True:
        try:
            stage06_batch, stage06_index = next(stage06_rows)
        except StopIteration:
            break
        v1_batch, v1_index = _next_or_fail(v1_rows, "STAGE07_V1_ROW_MISMATCH")
        eligibility_batch, eligibility_index = _next_or_fail(
            eligibility_rows, "ELIGIBILITY_ROW_MISMATCH"
        )
        output_batch, output_index = _next_or_fail(output_rows, "OUTPUT_ROW_MISMATCH")
        expected_batch, warning_status, reasons = _write_row(
            stage06_batch=stage06_batch,
            stage06_index=stage06_index,
            v1_batch=v1_batch,
            v1_index=v1_index,
            eligibility_batch=eligibility_batch,
            eligibility_index=eligibility_index,
            schema=schema,
            logical=logical,
        )
        for position in range(len(schema)):
            if (
                expected_batch.column(position)[0]
                != output_batch.column(position)[output_index]
            ):
                _fail("OUTPUT_VALUE_MISMATCH", "Evidence projection value differs")
        applicability = output_batch.column(
            schema.get_field_index(APPLICABILITY_FIELD)
        )[output_index].as_py()
        technical = output_batch.column(schema.get_field_index("stage07_parse_status"))[
            output_index
        ].as_py()
        assert isinstance(applicability, str) and isinstance(technical, str)
        applicability_counts[applicability] += 1
        technical_counts[technical] += 1
        warning_counts[warning_status] += 1
        reason_counts.update(reasons)
        rows += 1
    for iterator, code in (
        (v1_rows, "STAGE07_V1_ROW_MISMATCH"),
        (eligibility_rows, "ELIGIBILITY_ROW_MISMATCH"),
        (output_rows, "OUTPUT_ROW_MISMATCH"),
    ):
        try:
            next(iterator)
            _fail(code, "A compared stream contains added rows")
        except StopIteration:
            pass
    registry_logical = logical.hexdigest()
    dataset_logical = _dataset_fingerprint(contract, registry_logical, rows)
    mapback = _mapback_metrics(config.stage06_output_directory, output_paths)
    expected_mapback = {
        "TOTAL_OCCURRENCES": config.binding.stage06_occurrences,
        "STANDARD_OCCURRENCES": config.binding.stage06_standard_occurrences,
        "NATIVE_OCCURRENCES": config.binding.stage06_native_occurrences,
        "MISSING_STAGE07_ROWS": 0,
        "NON_UNIQUE_STAGE07_ROWS": 0,
    }
    recorded = manifest.get("development_metrics")
    observed_counts = {
        "APPLICABILITY_STATUS_COUNTS": dict(sorted(applicability_counts.items())),
        "TECHNICAL_STATUS_COUNTS": dict(sorted(technical_counts.items())),
        "STRUCTURAL_WARNING_STATUS_COUNTS": dict(sorted(warning_counts.items())),
        "STRUCTURAL_WARNING_REASON_COUNTS": dict(sorted(reason_counts.items())),
    }
    if (
        not isinstance(recorded, dict)
        or any(recorded.get(key) != value for key, value in observed_counts.items())
        or recorded.get("PARSER_CALLS") != 0
        or recorded.get("SEMANTIC_TRUST_CLAIMS") != 0
        or mapback != expected_mapback
        or rows != config.binding.stage06_candidate_rows
        or scientific.get("candidate_count") != rows
        or scientific.get("stage07_registry_logical_sha256_v2") != registry_logical
        or scientific.get("stage07_logical_dataset_sha256_v2") != dataset_logical
        or success.get("logical_dataset_sha256_v2") != dataset_logical
        or success.get("schema_fingerprint") != stage07_evidence_schema_fingerprint()
        or success.get("candidate_count") != rows
        or success.get("shard_count") != len(artifacts)
        or sum(item.row_count for item in artifacts) != rows
    ):
        _fail(
            "STAGE07_EVIDENCE_RECONCILIATION_FAILURE", "Evidence reconciliation differs"
        )
    return Stage07EvidenceOutcome(
        output_directory=output_directory,
        manifest_sha256=expected_manifest_sha256,
        logical_dataset_sha256_v2=dataset_logical,
        schema_fingerprint=stage07_evidence_schema_fingerprint(),
        contract_fingerprint=contract,
        candidate_count=rows,
        shard_count=len(artifacts),
        metrics={**recorded, "MAP_BACK": mapback},
    )


__all__ = [
    "ACCEPTED_ELIGIBILITY_ARTIFACT_SHA256",
    "ACCEPTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256",
    "ACCEPTED_STAGE07_V1_MANIFEST_SHA256",
    "NO_STRUCTURAL_WARNINGS_DETECTED",
    "STAGE07_EVIDENCE_CONTRACT_VERSION",
    "STAGE07_EVIDENCE_MANIFEST_NAME",
    "STAGE07_EVIDENCE_PROFILE_VERSION",
    "STRUCTURAL_WARNINGS_NOT_EVALUATED",
    "STRUCTURAL_WARNINGS_PRESENT",
    "STRUCTURAL_WARNING_FEATURE_VERSION",
    "Stage07EvidenceBinding",
    "Stage07EvidenceConfig",
    "Stage07EvidenceOutcome",
    "accepted_stage07_evidence_binding",
    "materialize_stage07_evidence",
    "stage07_evidence_contract_fingerprint",
    "stage07_evidence_schema",
    "stage07_evidence_schema_fingerprint",
    "validate_stage07_evidence_binding",
    "validate_stage07_evidence_bundle",
]

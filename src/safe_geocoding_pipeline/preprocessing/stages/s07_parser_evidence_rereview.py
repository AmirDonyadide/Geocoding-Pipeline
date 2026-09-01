"""Independent, bounded rereview of the published Stage 7 evidence projection.

This module is review-only.  It never imports or calls a parser and it never
publishes a replacement Stage 7 registry.  It independently reopens the frozen
Stage 6, Stage 7 v1, country-eligibility, and evidence-only v2 artifacts and
compares their complete ordered content.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import stat
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s07_component_readiness import (
    REASON_PARSED_EMPTY,
    StructuralSignals,
    structural_signals,
)
from .s07_libpostal_adapter import LibpostalComponent


REVIEW_VERSION = "stage07_parser_evidence_v2_independent_rereview_v1"
REVIEWED_CANDIDATE_SHA = "656a16d3d1f33cb152ace557c26f42df047bc7d6"
IMPLEMENTATION_SHA = "e684d84a8d68498ea790542143c8e125b3eb87b5"

EXPECTED_STAGE06_MANIFEST_SHA256 = (
    "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
)
EXPECTED_STAGE07_V1_MANIFEST_SHA256 = (
    "98d4e9efd2e46bb725aa68d7c207065efb2089c59cdcba8bbe6ef3536d9f8f77"
)
EXPECTED_ELIGIBILITY_ARTIFACT_SHA256 = (
    "a6ba110c0519873af898dcec0b5188a1db2659fe31aa619613cffcfdf82e499c"
)
EXPECTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256 = (
    "8395b0b5f8e0943dc6dd1a9c9553ea571294fc7bbe61fc9b9b1e6e8fd1cea1a6"
)
EXPECTED_ELIGIBILITY_POLICY_MANIFEST_SHA256 = (
    "49dcda13e36d2692885efadffb606fa96207fc174a3385041c07af9bf0d1026a"
)
EXPECTED_V2_MANIFEST_SHA256 = (
    "f58410877a7810562df7985c7316de7546d4dd8e11a647fd659c53a272e9c266"
)
EXPECTED_PARSER_BUNDLE_FINGERPRINT = (
    "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
)
EXPECTED_CONTRACT_FINGERPRINT = (
    "c9561e6d08263b2a8824ff66f2a3aa8521e3ff880759abc14173cce440ced8a4"
)
EXPECTED_SCHEMA_FINGERPRINT = (
    "b0e0e83ea3d929b7df8a6a5f64c2e8eb026395a917da90e97a98858b27e9ead2"
)
EXPECTED_LOGICAL_DATASET_SHA256 = (
    "0f0706c1396803737f22845837753878bfd2e8b3f9af59b48cfcc1b8c5774530"
)
EXPECTED_WARNING_SOURCE_SHA256 = (
    "dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9"
)
EXPECTED_CANDIDATES = 51_779
EXPECTED_OCCURRENCES = 69_747
EXPECTED_STANDARD_OCCURRENCES = 34_822
EXPECTED_NATIVE_OCCURRENCES = 34_925

REGISTRY_COLUMNS = (
    "stage06_exact_candidate_id",
    "stage06_candidate_lower",
    "stage06_occurrence_count",
    "stage06_standard_occurrence_count",
    "stage06_native_occurrence_count",
)
V1_COLUMNS = (
    *REGISTRY_COLUMNS,
    "stage07_parse_status",
    "stage07_libpostal_components",
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
V2_COLUMNS = (
    *REGISTRY_COLUMNS,
    "stage07_country_provenance_status",
    "stage07_trusted_country_iso_code",
    "stage07_valid_country_occurrence_count",
    "stage07_missing_country_occurrence_count",
    "stage07_invalid_country_occurrence_count",
    "stage07_distinct_valid_country_count",
    "stage07_parser_applicability_status",
    "stage07_parse_status",
    "stage07_parser_execution_origin",
    "stage07_libpostal_components",
    "stage07_structural_warning_status",
    "stage07_structural_warning_reason_codes",
    "stage07_raw_ordered_substrings",
    "stage07_lexical_numeric_stream_equal",
    "stage07_internal_boundary_count",
    "stage07_internal_single_codepoint_fragment_count",
    "stage07_maximum_components_per_lexical_run",
    "stage07_adjacent_repeated_label_internal_boundary_count",
    "stage07_candidate_lexical_numeric_codepoints",
    "stage07_output_lexical_numeric_codepoints",
)

COUNTRY_TO_APPLICABILITY = {
    "COUNTRY_UNANIMOUS_VALID": "PARSER_ELIGIBLE_COUNTRY",
    "COUNTRY_MISSING": "PARSER_ELIGIBILITY_MISSING_COUNTRY",
    "COUNTRY_PARTIAL": "PARSER_ELIGIBILITY_PARTIAL_COUNTRY",
    "COUNTRY_INVALID": "PARSER_ELIGIBILITY_INVALID_COUNTRY",
    "COUNTRY_CONFLICTING": "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY",
}
WARNING_STATUSES = (
    "NO_STRUCTURAL_WARNINGS_DETECTED",
    "STRUCTURAL_WARNINGS_PRESENT",
    "STRUCTURAL_WARNINGS_NOT_EVALUATED",
)
TECHNICAL_STATUSES = ("PARSED_NONEMPTY", "PARSED_EMPTY")
EXECUTION_ORIGIN = "REUSED_IMMUTABLE_STAGE07_V1"

EXPECTED_APPLICABILITY_COUNTS = {
    "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY": 14,
    "PARSER_ELIGIBILITY_INVALID_COUNTRY": 355,
    "PARSER_ELIGIBILITY_MISSING_COUNTRY": 721,
    "PARSER_ELIGIBILITY_PARTIAL_COUNTRY": 4,
    "PARSER_ELIGIBLE_COUNTRY": 50_685,
}
EXPECTED_TECHNICAL_COUNTS = {"PARSED_EMPTY": 5, "PARSED_NONEMPTY": 51_774}
EXPECTED_WARNING_COUNTS = {
    "NO_STRUCTURAL_WARNINGS_DETECTED": 33_811,
    "STRUCTURAL_WARNINGS_NOT_EVALUATED": 1_094,
    "STRUCTURAL_WARNINGS_PRESENT": 16_874,
}
EXPECTED_REASON_COUNTS = {
    "LEXICAL_NUMERIC_MATERIAL_LOSS": 39,
    "LEXICAL_NUMERIC_REORDER_OR_SUBSTITUTION": 1,
    "LEXICAL_RUN_SPLIT_ACROSS_THREE_OR_MORE_COMPONENTS": 6_317,
    "PARSED_EMPTY_NO_COMPONENTS": 4,
    "RAW_ORDERED_SUBSTRING_ALIGNMENT_FAILURE": 7_750,
    "TOKEN_INTERNAL_COMPONENT_BOUNDARY": 10_105,
    "TOKEN_INTERNAL_SINGLE_CODEPOINT_FRAGMENT": 2_426,
}

_RAW_DIGEST_DOMAIN = b"SAFE_STAGE07_INDEPENDENT_REREVIEW_RAW_V1_V2"
_WARNING_DIGEST_DOMAIN = b"SAFE_STAGE07_INDEPENDENT_REREVIEW_WARNINGS"


class Stage07IndependentRereviewError(RuntimeError):
    """A privacy-safe independent rereview assertion failed."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07IndependentRereviewError(code, detail)


@dataclass(frozen=True, slots=True)
class Artifact:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int


@dataclass(frozen=True, slots=True)
class RereviewConfig:
    stage06_root: Path
    stage07_v1_root: Path
    eligibility_artifact: Path
    eligibility_audit_manifest: Path
    stage07_v2_root: Path
    source_root: Path
    output_directory: Path
    review_git_sha: str
    reviewed_candidate_sha: str = REVIEWED_CANDIDATE_SHA
    batch_rows: int = 32

    def validate(self) -> None:
        if self.reviewed_candidate_sha != REVIEWED_CANDIDATE_SHA:
            _fail("REVIEWED_SHA_MISMATCH", "The reviewed candidate SHA differs")
        if len(self.review_git_sha) != 40:
            _fail("REVIEW_SHA_INVALID", "The independent review SHA is malformed")
        if self.batch_rows < 1:
            _fail("BATCH_ROWS_INVALID", "The independent batch size is invalid")
        for path in (
            self.stage06_root,
            self.stage07_v1_root,
            self.eligibility_artifact,
            self.eligibility_audit_manifest,
            self.stage07_v2_root,
            self.source_root,
            self.output_directory,
        ):
            lowered = tuple(
                part.casefold() for part in path.resolve(strict=False).parts
            )
            if any("holdout" in part for part in lowered):
                _fail("HOLDOUT_ACCESS_PROHIBITED", "A rereview path names HOLDOUT")
            if any("production" in part for part in lowered):
                _fail(
                    "PRODUCTION_ACCESS_PROHIBITED", "A rereview path names production"
                )


@dataclass(frozen=True, slots=True)
class RereviewOutcome:
    output_directory: Path
    evidence_sha256: str
    candidate_count: int
    occurrence_count: int
    raw_preservation_digest: str
    warning_replay_digest: str
    metrics: Mapping[str, object]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07IndependentRereviewError(
            "CONTROLLED_READ_FAILURE", "A controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07IndependentRereviewError(
            "CONTROLLED_JSON_INVALID", "A controlled manifest is malformed"
        ) from error
    if not isinstance(value, dict):
        _fail("CONTROLLED_JSON_INVALID", "A controlled manifest is not an object")
    return cast(dict[str, Any], value)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)


def _require_file(path: Path, expected_mode: int = 0o600) -> None:
    if path.is_symlink() or not path.is_file() or _mode(path) != expected_mode:
        _fail("CONTROLLED_FILE_INVALID", "A controlled file or mode differs")


def _require_directory(path: Path, expected_mode: int = 0o700) -> None:
    if path.is_symlink() or not path.is_dir() or _mode(path) != expected_mode:
        _fail("CONTROLLED_DIRECTORY_INVALID", "A controlled directory or mode differs")


def _manifest_artifacts(
    root: Path,
    manifest: Mapping[str, Any],
    *,
    key: str,
    directory: str,
) -> tuple[Artifact, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict):
        _fail("MANIFEST_IDENTITY_INVALID", "Physical identity is absent")
    raw = physical.get(key)
    if not isinstance(raw, list) or not raw:
        _fail("MANIFEST_IDENTITY_INVALID", "Artifact identity is absent")
    artifacts: list[Artifact] = []
    for sequence, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            _fail("MANIFEST_IDENTITY_INVALID", "An artifact identity is malformed")
        try:
            artifact = Artifact(
                relative_path=str(item["relative_path"]),
                size_bytes=int(item["size_bytes"]),
                sha256=str(item["sha256"]),
                row_count=int(item["row_count"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise Stage07IndependentRereviewError(
                "MANIFEST_IDENTITY_INVALID", "Artifact fields differ"
            ) from error
        if artifact.relative_path != f"{directory}/part-{sequence:06d}.parquet":
            _fail("MANIFEST_IDENTITY_INVALID", "Artifact order differs")
        path = root / artifact.relative_path
        _require_file(path)
        if (
            path.stat(follow_symlinks=False).st_size != artifact.size_bytes
            or _sha256_file(path) != artifact.sha256
        ):
            _fail("ARTIFACT_IDENTITY_MISMATCH", "An artifact identity differs")
        artifacts.append(artifact)
    return tuple(artifacts)


def _paths(root: Path, artifacts: Sequence[Artifact]) -> tuple[Path, ...]:
    return tuple(root / item.relative_path for item in artifacts)


def _rows(
    paths: Sequence[Path], columns: Sequence[str], batch_rows: int
) -> Iterator[tuple[pa.RecordBatch, int]]:
    for path in paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True)
        for batch in parquet.iter_batches(
            batch_size=batch_rows, columns=columns, use_threads=False
        ):
            for index in range(batch.num_rows):
                yield batch, index


def _next(
    rows: Iterator[tuple[pa.RecordBatch, int]], code: str
) -> tuple[pa.RecordBatch, int]:
    try:
        return next(rows)
    except StopIteration:
        _fail(code, "A controlled row stream ended early")


def _scalar(batch: pa.RecordBatch, index: int, name: str) -> pa.Scalar:
    position = batch.schema.get_field_index(name)
    if position < 0:
        _fail("SCHEMA_MISMATCH", "A required column is absent")
    return batch.column(position)[index]


def _assert_equal(left: pa.Scalar, right: pa.Scalar, code: str) -> None:
    if left != right:
        _fail(code, "A protected row value differs")


def _components(value: pa.Scalar) -> tuple[LibpostalComponent, ...]:
    raw = value.as_py()
    if not isinstance(raw, list):
        _fail("COMPONENT_STRUCTURE_INVALID", "The raw component stream is malformed")
    output: list[LibpostalComponent] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("COMPONENT_STRUCTURE_INVALID", "A raw component is malformed")
        output.append(LibpostalComponent(label=item["label"], value=item["value"]))
    return tuple(output)


def _digest_bytes(digest: Any, value: bytes) -> None:
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _digest_text(digest: Any, value: str) -> None:
    _digest_bytes(digest, value.encode("utf-8", errors="strict"))


def _digest_optional(digest: Any, value: object) -> None:
    if value is None:
        digest.update(b"\x00")
        return
    digest.update(b"\x01")
    if isinstance(value, bool):
        digest.update(b"\x01" if value else b"\x00")
    elif isinstance(value, int):
        digest.update(value.to_bytes(8, "big"))
    elif isinstance(value, str):
        _digest_text(digest, value)
    else:
        _fail("DIGEST_VALUE_INVALID", "A rereview digest value is unsupported")


def _warning_tuple(signals: StructuralSignals | None) -> tuple[object, ...]:
    if signals is None:
        return (None,) * 8
    return (
        signals.raw_ordered_substrings,
        signals.lexical_numeric_stream_equal,
        signals.internal_boundary_count,
        signals.internal_single_codepoint_fragment_count,
        signals.maximum_components_per_lexical_run,
        signals.adjacent_repeated_label_internal_boundary_count,
        signals.candidate_lexical_numeric_codepoints,
        signals.output_lexical_numeric_codepoints,
    )


def _validate_country_invariants(values: Mapping[str, object]) -> None:
    occurrence = cast(int, values["occurrence_count"])
    valid = cast(int, values["valid_country_occurrence_count"])
    missing = cast(int, values["missing_country_occurrence_count"])
    invalid = cast(int, values["invalid_country_occurrence_count"])
    distinct = cast(int, values["distinct_valid_country_count"])
    status = cast(str, values["country_provenance_status"])
    country = values["unanimous_country_code"]
    applicability = cast(str, values["libpostal_eligibility"])
    if valid + missing + invalid != occurrence:
        _fail("COUNTRY_COUNT_MISMATCH", "Country occurrence counts do not reconcile")
    if COUNTRY_TO_APPLICABILITY.get(status) != applicability:
        _fail("COUNTRY_APPLICABILITY_MISMATCH", "Country/applicability differs")
    if status == "COUNTRY_UNANIMOUS_VALID":
        if (
            valid != occurrence
            or missing != 0
            or invalid != 0
            or distinct != 1
            or not isinstance(country, str)
            or len(country) != 2
            or country != country.upper()
        ):
            _fail("COUNTRY_STATUS_MISMATCH", "Unanimous country invariants differ")
        return
    if country is not None:
        _fail("COUNTRY_STATUS_MISMATCH", "An unresolved country row has a code")
    if status == "COUNTRY_MISSING":
        valid_status = missing == occurrence and valid == invalid == distinct == 0
    elif status == "COUNTRY_PARTIAL":
        valid_status = valid > 0 and distinct == 1 and missing + invalid > 0
    elif status == "COUNTRY_INVALID":
        valid_status = valid == distinct == 0 and invalid > 0
    elif status == "COUNTRY_CONFLICTING":
        valid_status = valid > 0 and distinct >= 2
    else:
        valid_status = False
    if not valid_status:
        _fail("COUNTRY_STATUS_MISMATCH", "An unresolved country invariant differs")


def _validate_v2_schema(path: Path) -> None:
    schema = pq.ParquetFile(path, page_checksum_verification=True).schema_arrow
    if tuple(schema.names) != V2_COLUMNS:
        _fail("V2_SCHEMA_MISMATCH", "The evidence-only columns differ")
    components = pa.large_list(
        pa.field(
            "element",
            pa.struct(
                (
                    pa.field("label", pa.large_string(), nullable=False),
                    pa.field("value", pa.large_string(), nullable=False),
                )
            ),
            nullable=False,
        )
    )
    reasons = pa.large_list(pa.field("element", pa.large_string(), nullable=False))
    expected_fields = (
        pa.field(V2_COLUMNS[0], pa.binary(32), nullable=False),
        pa.field(V2_COLUMNS[1], pa.string(), nullable=False),
        *(pa.field(name, pa.uint64(), nullable=False) for name in V2_COLUMNS[2:5]),
        pa.field(V2_COLUMNS[5], pa.string(), nullable=False),
        pa.field(V2_COLUMNS[6], pa.string(), nullable=True),
        *(pa.field(name, pa.uint64(), nullable=False) for name in V2_COLUMNS[7:10]),
        pa.field(V2_COLUMNS[10], pa.uint32(), nullable=False),
        *(pa.field(name, pa.string(), nullable=False) for name in V2_COLUMNS[11:14]),
        pa.field(V2_COLUMNS[14], components, nullable=False),
        pa.field(V2_COLUMNS[15], pa.string(), nullable=False),
        pa.field(V2_COLUMNS[16], reasons, nullable=False),
        *(pa.field(name, pa.bool_(), nullable=True) for name in V2_COLUMNS[17:19]),
        *(pa.field(name, pa.uint64(), nullable=True) for name in V2_COLUMNS[19:]),
    )
    if tuple(schema) != expected_fields:
        _fail("V2_SCHEMA_MISMATCH", "The evidence-only Arrow types differ")
    metadata = schema.metadata or {}
    expected_metadata = {
        b"stage07_contract_version": b"stage07_parser_evidence_contract_v2",
        b"stage07_profile_version": b"stage07_parser_evidence_profile_v2",
        b"stage07_schema_version": b"stage07_parser_evidence_schema_v2",
        b"stage07_schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT.encode("ascii"),
        b"stage07_contract_fingerprint": EXPECTED_CONTRACT_FINGERPRINT.encode("ascii"),
        b"stage07_v1_manifest_sha256": EXPECTED_STAGE07_V1_MANIFEST_SHA256.encode(
            "ascii"
        ),
        b"parser_bundle_fingerprint": EXPECTED_PARSER_BUNDLE_FINGERPRINT.encode(
            "ascii"
        ),
        b"semantic_trust_claims": b"false",
    }
    if metadata != expected_metadata:
        _fail("V2_SCHEMA_METADATA_MISMATCH", "Schema metadata differs")
    forbidden = {
        "COMPONENTS_READY",
        "COMPONENTS_ABSTAIN",
        "component_readiness",
        "semantic_trust",
        "geographic_truth",
    }
    if any(
        any(token.casefold() in name.casefold() for token in forbidden)
        for name in schema.names
    ):
        _fail("SEMANTIC_TRUST_FIELD_PRESENT", "A semantic-trust field is published")


def _validate_v2_topology(root: Path, artifacts: Sequence[Artifact]) -> None:
    expected_directories = {"registry", "registry/data"}
    expected_files = {
        "stage07_parser_evidence_manifest.json",
        "_SUCCESS.json",
        *(item.relative_path for item in artifacts),
    }
    directories: set[str] = set()
    files: set[str] = set()
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        _require_directory(current_path)
        for name in directory_names:
            path = current_path / name
            _require_directory(path)
            directories.add(path.relative_to(root).as_posix())
        for name in file_names:
            path = current_path / name
            _require_file(path)
            files.add(path.relative_to(root).as_posix())
    if directories != expected_directories or files != expected_files:
        _fail("V2_TOPOLOGY_MISMATCH", "The evidence-only artifact topology differs")


def _validate_no_parser_call(source_root: Path) -> None:
    projection = (
        source_root
        / "src/safe_geocoding_pipeline/preprocessing/stages/s07_parser_evidence.py"
    )
    readiness = (
        source_root
        / "src/safe_geocoding_pipeline/preprocessing/stages/s07_component_readiness.py"
    )
    if (
        _sha256_file(projection)
        != "0e7ed9c7dfc7ae53dd7db3bf28357830cf14cf71dc395b710635092f60c39fbb"
    ):
        _fail("IMPLEMENTATION_SOURCE_MISMATCH", "The projection source differs")
    if _sha256_file(readiness) != EXPECTED_WARNING_SOURCE_SHA256:
        _fail("WARNING_SOURCE_MISMATCH", "The frozen warning source differs")
    tree = ast.parse(projection.read_text(encoding="utf-8"), filename=str(projection))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            if any(
                module == "postal" or module.startswith("postal.") for module in modules
            ):
                _fail("PARSER_CALL_PRESENT", "The v2 projection imports pypostal")
        if isinstance(node, ast.Call):
            function = node.func
            if (
                isinstance(function, ast.Name)
                and function.id in {"parse_address", "PypostalParser"}
            ) or (isinstance(function, ast.Attribute) and function.attr == "parse"):
                _fail("PARSER_CALL_PRESENT", "The v2 projection contains a parser call")


def _validate_manifest_identities(
    *,
    stage06_manifest: Mapping[str, Any],
    v1_manifest: Mapping[str, Any],
    eligibility_manifest: Mapping[str, Any],
    v2_manifest: Mapping[str, Any],
) -> None:
    v1_scientific = v1_manifest.get("scientific_identity")
    v2_scientific = v2_manifest.get("scientific_identity")
    v2_semantics = v2_manifest.get("scientific_semantics")
    v2_validation = v2_manifest.get("validation")
    if not all(
        isinstance(value, dict)
        for value in (v1_scientific, v2_scientific, v2_semantics, v2_validation)
    ):
        _fail("MANIFEST_IDENTITY_INVALID", "A scientific identity is absent")
    v1_scientific = cast(dict[str, Any], v1_scientific)
    v2_scientific = cast(dict[str, Any], v2_scientific)
    v2_semantics = cast(dict[str, Any], v2_semantics)
    v2_validation = cast(dict[str, Any], v2_validation)
    stage06_binding = v1_scientific.get("stage06_binding")
    input_binding = v2_scientific.get("input_binding")
    v1_identity = v2_scientific.get("stage07_v1_identity")
    if not all(
        isinstance(value, dict)
        for value in (stage06_binding, input_binding, v1_identity)
    ):
        _fail("LINEAGE_BINDING_INVALID", "An upstream binding is absent")
    stage06_binding = cast(dict[str, Any], stage06_binding)
    input_binding = cast(dict[str, Any], input_binding)
    v1_identity = cast(dict[str, Any], v1_identity)
    if (
        v1_scientific.get("stage07_contract_version")
        != "stage07_libpostal_parsing_contract_v1"
        or v1_scientific.get("stage07_profile_version")
        != "stage07_libpostal_parsing_profile_v1"
        or v1_scientific.get("candidate_count") != EXPECTED_CANDIDATES
        or v1_scientific.get("status_vocabulary") != list(TECHNICAL_STATUSES)
        or stage06_binding.get("stage06_manifest_sha256")
        != EXPECTED_STAGE06_MANIFEST_SHA256
        or stage06_binding.get("parser_bundle_fingerprint")
        != EXPECTED_PARSER_BUNDLE_FINGERPRINT
        or input_binding.get("stage06_manifest_sha256")
        != EXPECTED_STAGE06_MANIFEST_SHA256
        or input_binding.get("stage07_v1_manifest_sha256")
        != EXPECTED_STAGE07_V1_MANIFEST_SHA256
        or input_binding.get("eligibility_artifact_sha256")
        != EXPECTED_ELIGIBILITY_ARTIFACT_SHA256
        or input_binding.get("eligibility_audit_manifest_sha256")
        != EXPECTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256
        or input_binding.get("eligibility_policy_manifest_sha256")
        != EXPECTED_ELIGIBILITY_POLICY_MANIFEST_SHA256
        or input_binding.get("parser_bundle_fingerprint")
        != EXPECTED_PARSER_BUNDLE_FINGERPRINT
        or v2_scientific.get("stage07_contract_version")
        != "stage07_parser_evidence_contract_v2"
        or v2_scientific.get("stage07_profile_version")
        != "stage07_parser_evidence_profile_v2"
        or v2_scientific.get("stage07_schema_fingerprint")
        != EXPECTED_SCHEMA_FINGERPRINT
        or v2_scientific.get("stage07_contract_fingerprint")
        != EXPECTED_CONTRACT_FINGERPRINT
        or v2_scientific.get("stage07_logical_dataset_sha256_v2")
        != EXPECTED_LOGICAL_DATASET_SHA256
        or v1_identity.get("contract") != v1_scientific.get("stage07_contract_version")
        or v1_identity.get("profile") != v1_scientific.get("stage07_profile_version")
        or v1_identity.get("schema_fingerprint")
        != v1_scientific.get("stage07_schema_fingerprint")
        or v1_identity.get("logical_dataset_sha256_v1")
        != v1_scientific.get("stage07_logical_dataset_sha256_v1")
        or v1_identity.get("manifest_sha256") != EXPECTED_STAGE07_V1_MANIFEST_SHA256
        or v1_identity.get("parser_bundle_fingerprint")
        != EXPECTED_PARSER_BUNDLE_FINGERPRINT
        or v2_scientific.get("component_readiness_status_published") is not False
        or v2_scientific.get("technical_status_vocabulary") != list(TECHNICAL_STATUSES)
        or v2_scientific.get("structural_warning_status_vocabulary")
        != list(WARNING_STATUSES)
        or v2_semantics.get("raw_libpostal_components_are")
        != "HYPOTHESES_AND_EVIDENCE_NOT_SOURCE_TRUTH"
        or "NO_WARNING_IMPLIES_SEMANTIC_CORRECTNESS"
        not in cast(list[object], v2_semantics.get("does_not_guarantee", []))
        or v2_validation.get("no_component_readiness_gate") != "PASS"
        or v2_validation.get("zero_semantic_trust_claims") != "PASS"
        or v2_validation.get("zero_parser_calls") != "PASS"
        or eligibility_manifest.get("eligibility_manifest_sha256")
        != EXPECTED_ELIGIBILITY_POLICY_MANIFEST_SHA256
    ):
        _fail("SCIENTIFIC_IDENTITY_MISMATCH", "A contract or lineage binding differs")
    stage06_physical = stage06_manifest.get("physical_identity")
    if not isinstance(stage06_physical, dict):
        _fail("LINEAGE_BINDING_INVALID", "Stage 6 physical identity is absent")


def _validate_tracked_reports(
    source_root: Path,
    *,
    applicability_counts: Mapping[str, int],
    technical_counts: Mapping[str, int],
    warning_counts: Mapping[str, int],
    reason_counts: Mapping[str, int],
) -> None:
    development = _load_json(
        source_root / "reports/development/stage07_parser_evidence_v2_development.json"
    )
    current = _load_json(
        source_root / "reports/development/stage07_development_candidate_report.json"
    )
    reconciliation = development.get("reconciliation")
    mapback = development.get("occurrence_map_back")
    current_candidate = current.get("current_candidate")
    post_stage07 = current.get("post_stage07_architecture")
    if not all(
        isinstance(value, dict)
        for value in (reconciliation, mapback, current_candidate, post_stage07)
    ):
        _fail("SANITIZED_REPORT_MISMATCH", "A sanitized report section is absent")
    reconciliation = cast(dict[str, Any], reconciliation)
    mapback = cast(dict[str, Any], mapback)
    current_candidate = cast(dict[str, Any], current_candidate)
    post_stage07 = cast(dict[str, Any], post_stage07)
    if (
        development.get("manifest_sha256") != EXPECTED_V2_MANIFEST_SHA256
        or development.get("contract_fingerprint") != EXPECTED_CONTRACT_FINGERPRINT
        or development.get("schema_fingerprint") != EXPECTED_SCHEMA_FINGERPRINT
        or development.get("logical_dataset_sha256_v2")
        != EXPECTED_LOGICAL_DATASET_SHA256
        or development.get("applicability_status_counts") != dict(applicability_counts)
        or development.get("technical_status_counts") != dict(technical_counts)
        or development.get("structural_warning_status_counts") != dict(warning_counts)
        or development.get("structural_warning_reason_counts") != dict(reason_counts)
        or reconciliation.get("candidate_rows_input") != EXPECTED_CANDIDATES
        or reconciliation.get("candidate_rows_output") != EXPECTED_CANDIDATES
        or reconciliation.get("exact_raw_stage07_v1_preservation") != "PASS"
        or reconciliation.get("exact_stage06_preservation") != "PASS"
        or mapback
        != {
            "missing": 0,
            "native": EXPECTED_NATIVE_OCCURRENCES,
            "non_unique": 0,
            "standard": EXPECTED_STANDARD_OCCURRENCES,
            "total": EXPECTED_OCCURRENCES,
        }
        or development.get("zero_parser_calls") is not True
        or development.get("semantic_trust_claims") != 0
        or current.get("verdict")
        != "STAGE07_EVIDENCE_ONLY_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REREVIEW"
        or current_candidate.get("manifest_sha256") != EXPECTED_V2_MANIFEST_SHA256
        or current_candidate.get("candidate_rows") != EXPECTED_CANDIDATES
        or current_candidate.get("occurrence_map_back") != EXPECTED_OCCURRENCES
        or current_candidate.get("parser_calls") != 0
        or current_candidate.get("semantic_trust_claims") != 0
        or current_candidate.get("component_readiness_gate_published") is not False
        or current_candidate.get("raw_components_are_hypotheses_and_evidence")
        is not True
        or current_candidate.get("absence_of_structural_warning_implies_semantic_trust")
        is not False
        or post_stage07.get("parser_components_are_hypotheses_and_evidence") is not True
        or post_stage07.get("component_readiness_semantic_gate") is not False
        or post_stage07.get("structural_warning_absence_implies_trust") is not False
    ):
        _fail("SANITIZED_REPORT_MISMATCH", "Sanitized reports differ from evidence")


def _mapback_metrics(
    row_map_paths: Sequence[Path], v2_paths: Sequence[Path]
) -> dict[str, int]:
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("SET threads=1")
        row = connection.execute(
            """
            WITH occurrences AS (
              SELECT stage06_standard_exact_candidate_id AS candidate_id,
                     'STANDARD' AS representation
              FROM read_parquet(?)
              WHERE stage06_standard_exact_candidate_id IS NOT NULL
              UNION ALL
              SELECT stage06_native_exact_candidate_id AS candidate_id,
                     'NATIVE' AS representation
              FROM read_parquet(?)
              WHERE stage06_native_exact_candidate_id IS NOT NULL
            ), registry AS (
              SELECT stage06_exact_candidate_id AS candidate_id, count(*) AS copies
              FROM read_parquet(?) GROUP BY 1
            )
            SELECT count(*),
                   count(*) FILTER (WHERE representation = 'STANDARD'),
                   count(*) FILTER (WHERE representation = 'NATIVE'),
                   count(*) FILTER (WHERE registry.candidate_id IS NULL),
                   count(*) FILTER (WHERE copies != 1)
            FROM occurrences LEFT JOIN registry USING (candidate_id)
            """,
            (
                [str(path) for path in row_map_paths],
                [str(path) for path in row_map_paths],
                [str(path) for path in v2_paths],
            ),
        ).fetchone()
    except duckdb.Error as error:
        raise Stage07IndependentRereviewError(
            "MAPBACK_QUERY_FAILURE", "The independent map-back query failed"
        ) from error
    finally:
        connection.close()
    if row is None:
        _fail("MAPBACK_QUERY_FAILURE", "The independent map-back result is absent")
    return {
        "total": int(row[0]),
        "standard": int(row[1]),
        "native": int(row[2]),
        "missing": int(row[3]),
        "non_unique": int(row[4]),
    }


def _write_json_atomic(directory: Path, payload: Mapping[str, object]) -> str:
    if directory.exists() or directory.is_symlink():
        _fail("OUTPUT_COLLISION", "The independent evidence output already exists")
    parent = directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{directory.name}.{os.getpid()}.in_progress"
    temporary.mkdir(mode=0o700)
    path = temporary / "stage07_evidence_independent_rereview.json"
    encoded = (
        json.dumps(
            payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    evidence_sha = hashlib.sha256(encoded).hexdigest()
    os.replace(temporary, directory)
    return evidence_sha


def run_independent_rereview(config: RereviewConfig) -> RereviewOutcome:
    """Reopen and independently reconcile every controlled evidence row."""
    config.validate()
    require_goethe_nhr_slurm("stage07-evidence-only-independent-rereview")
    _validate_no_parser_call(config.source_root)

    for root in (config.stage06_root, config.stage07_v1_root, config.stage07_v2_root):
        _require_directory(root)
    for path in (config.eligibility_artifact, config.eligibility_audit_manifest):
        _require_file(path)

    stage06_manifest_path = config.stage06_root / "stage06_manifest.json"
    v1_manifest_path = config.stage07_v1_root / "stage07_manifest.json"
    v2_manifest_path = config.stage07_v2_root / "stage07_parser_evidence_manifest.json"
    v2_success_path = config.stage07_v2_root / "_SUCCESS.json"
    for path in (
        stage06_manifest_path,
        v1_manifest_path,
        v2_manifest_path,
        v2_success_path,
    ):
        _require_file(path)
    if (
        _sha256_file(stage06_manifest_path) != EXPECTED_STAGE06_MANIFEST_SHA256
        or _sha256_file(v1_manifest_path) != EXPECTED_STAGE07_V1_MANIFEST_SHA256
        or _sha256_file(config.eligibility_artifact)
        != EXPECTED_ELIGIBILITY_ARTIFACT_SHA256
        or _sha256_file(config.eligibility_audit_manifest)
        != EXPECTED_ELIGIBILITY_AUDIT_MANIFEST_SHA256
        or _sha256_file(v2_manifest_path) != EXPECTED_V2_MANIFEST_SHA256
    ):
        _fail("IMMUTABLE_INPUT_IDENTITY_MISMATCH", "An immutable manifest differs")

    stage06_manifest = _load_json(stage06_manifest_path)
    v1_manifest = _load_json(v1_manifest_path)
    eligibility_manifest = _load_json(config.eligibility_audit_manifest)
    v2_manifest = _load_json(v2_manifest_path)
    v2_success = _load_json(v2_success_path)
    _validate_manifest_identities(
        stage06_manifest=stage06_manifest,
        v1_manifest=v1_manifest,
        eligibility_manifest=eligibility_manifest,
        v2_manifest=v2_manifest,
    )
    if (
        v2_success.get("manifest_sha256") != EXPECTED_V2_MANIFEST_SHA256
        or v2_success.get("candidate_count") != EXPECTED_CANDIDATES
        or v2_success.get("logical_dataset_sha256_v2")
        != EXPECTED_LOGICAL_DATASET_SHA256
        or v2_success.get("schema_fingerprint") != EXPECTED_SCHEMA_FINGERPRINT
    ):
        _fail("SUCCESS_MARKER_MISMATCH", "The terminal success marker differs")

    stage06_registry = _manifest_artifacts(
        config.stage06_root,
        stage06_manifest,
        key="registry_artifacts",
        directory="registry/data",
    )
    stage06_row_map = _manifest_artifacts(
        config.stage06_root,
        stage06_manifest,
        key="row_map_artifacts",
        directory="row_map/data",
    )
    v1_registry = _manifest_artifacts(
        config.stage07_v1_root,
        v1_manifest,
        key="registry_artifacts",
        directory="registry/data",
    )
    v2_registry = _manifest_artifacts(
        config.stage07_v2_root,
        v2_manifest,
        key="registry_artifacts",
        directory="registry/data",
    )
    _validate_v2_topology(config.stage07_v2_root, v2_registry)
    v2_paths = _paths(config.stage07_v2_root, v2_registry)
    for path in v2_paths:
        _validate_v2_schema(path)

    stage06_rows = _rows(
        _paths(config.stage06_root, stage06_registry),
        REGISTRY_COLUMNS,
        config.batch_rows,
    )
    v1_rows = _rows(
        _paths(config.stage07_v1_root, v1_registry), V1_COLUMNS, config.batch_rows
    )
    eligibility_rows = _rows(
        (config.eligibility_artifact,), ELIGIBILITY_COLUMNS, config.batch_rows
    )
    v2_rows = _rows(v2_paths, V2_COLUMNS, config.batch_rows)

    raw_digest = hashlib.sha256(_RAW_DIGEST_DOMAIN)
    warning_digest = hashlib.sha256(_WARNING_DIGEST_DOMAIN)
    applicability_counts: Counter[str] = Counter()
    technical_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    rows = 0
    occurrences = 0
    standard_occurrences = 0
    native_occurrences = 0

    for stage06_batch, stage06_index in stage06_rows:
        v1_batch, v1_index = _next(v1_rows, "V1_STREAM_EARLY_END")
        eligibility_batch, eligibility_index = _next(
            eligibility_rows, "ELIGIBILITY_STREAM_EARLY_END"
        )
        v2_batch, v2_index = _next(v2_rows, "V2_STREAM_EARLY_END")

        for name in REGISTRY_COLUMNS:
            source = _scalar(stage06_batch, stage06_index, name)
            _assert_equal(
                source, _scalar(v1_batch, v1_index, name), "V1_STAGE06_MISMATCH"
            )
            _assert_equal(
                source, _scalar(v2_batch, v2_index, name), "V2_STAGE06_MISMATCH"
            )

        eligibility = {
            name: _scalar(eligibility_batch, eligibility_index, name).as_py()
            for name in ELIGIBILITY_COLUMNS
        }
        mapping = {
            "candidate_id": REGISTRY_COLUMNS[0],
            "occurrence_count": REGISTRY_COLUMNS[2],
            "standard_occurrence_count": REGISTRY_COLUMNS[3],
            "native_occurrence_count": REGISTRY_COLUMNS[4],
            "country_provenance_status": "stage07_country_provenance_status",
            "unanimous_country_code": "stage07_trusted_country_iso_code",
            "valid_country_occurrence_count": "stage07_valid_country_occurrence_count",
            "missing_country_occurrence_count": "stage07_missing_country_occurrence_count",
            "invalid_country_occurrence_count": "stage07_invalid_country_occurrence_count",
            "distinct_valid_country_count": "stage07_distinct_valid_country_count",
            "libpostal_eligibility": "stage07_parser_applicability_status",
            "stage07_parse_status": "stage07_parse_status",
        }
        for eligibility_name, v2_name in mapping.items():
            # The frozen eligibility artifact intentionally uses some physical
            # Arrow types that differ from the v2 schema (for example binary
            # versus fixed-size binary candidate IDs).  The scientific
            # contract is exact logical-value preservation, so compare the
            # decoded scalar values here; the v2 physical types are checked
            # independently by ``_validate_v2_schema``.
            if (
                _scalar(eligibility_batch, eligibility_index, eligibility_name).as_py()
                != _scalar(v2_batch, v2_index, v2_name).as_py()
            ):
                _fail(
                    "ELIGIBILITY_COPY_MISMATCH",
                    "A protected eligibility value differs",
                )
        _validate_country_invariants(eligibility)

        v1_status = _scalar(v1_batch, v1_index, "stage07_parse_status")
        v2_status = _scalar(v2_batch, v2_index, "stage07_parse_status")
        _assert_equal(v1_status, v2_status, "TECHNICAL_STATUS_MISMATCH")
        v1_components = _scalar(v1_batch, v1_index, "stage07_libpostal_components")
        v2_components = _scalar(v2_batch, v2_index, "stage07_libpostal_components")
        _assert_equal(v1_components, v2_components, "RAW_COMPONENT_MISMATCH")
        if (
            _scalar(v2_batch, v2_index, "stage07_parser_execution_origin").as_py()
            != EXECUTION_ORIGIN
        ):
            _fail("EXECUTION_ORIGIN_MISMATCH", "The v1 reuse origin differs")

        candidate_id = _scalar(
            stage06_batch, stage06_index, REGISTRY_COLUMNS[0]
        ).as_py()
        candidate = _scalar(stage06_batch, stage06_index, REGISTRY_COLUMNS[1]).as_py()
        status = v1_status.as_py()
        if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
            _fail("STAGE06_STRUCTURE_INVALID", "The Stage 6 registry type differs")
        components = _components(v1_components)
        if status == "PARSED_NONEMPTY":
            if not components:
                _fail("TECHNICAL_STATUS_MISMATCH", "PARSED_NONEMPTY has no component")
        elif status == "PARSED_EMPTY":
            if components:
                _fail("TECHNICAL_STATUS_MISMATCH", "PARSED_EMPTY has components")
        else:
            _fail("TECHNICAL_STATUS_MISMATCH", "An unknown technical status exists")

        applicability = cast(str, eligibility["libpostal_eligibility"])
        expected_signals: StructuralSignals | None
        if applicability != "PARSER_ELIGIBLE_COUNTRY":
            expected_warning = "STRUCTURAL_WARNINGS_NOT_EVALUATED"
            expected_reasons: tuple[str, ...] = ()
            expected_signals = None
        elif status == "PARSED_EMPTY":
            expected_warning = "STRUCTURAL_WARNINGS_PRESENT"
            expected_reasons = (REASON_PARSED_EMPTY,)
            expected_signals = None
        else:
            first = structural_signals(candidate, components)
            second = structural_signals(candidate, components)
            if first != second:
                _fail(
                    "WARNING_NONDETERMINISM", "Two independent warning replays differ"
                )
            expected_signals = first
            expected_reasons = first.reason_codes
            expected_warning = (
                "STRUCTURAL_WARNINGS_PRESENT"
                if expected_reasons
                else "NO_STRUCTURAL_WARNINGS_DETECTED"
            )

        observed_warning = _scalar(
            v2_batch, v2_index, "stage07_structural_warning_status"
        ).as_py()
        observed_reasons = _scalar(
            v2_batch, v2_index, "stage07_structural_warning_reason_codes"
        ).as_py()
        if observed_warning != expected_warning or observed_reasons != list(
            expected_reasons
        ):
            _fail("WARNING_REPLAY_MISMATCH", "A frozen warning result differs")
        for name, expected in zip(
            V2_COLUMNS[-8:], _warning_tuple(expected_signals), strict=True
        ):
            if _scalar(v2_batch, v2_index, name).as_py() != expected:
                _fail("WARNING_SIGNAL_MISMATCH", "A frozen warning signal differs")

        _digest_bytes(raw_digest, candidate_id)
        _digest_text(raw_digest, candidate)
        for count_name in REGISTRY_COLUMNS[2:]:
            raw_digest.update(
                int(_scalar(stage06_batch, stage06_index, count_name).as_py()).to_bytes(
                    8, "big"
                )
            )
        _digest_text(raw_digest, cast(str, status))
        raw_digest.update(len(components).to_bytes(8, "big"))
        for component in components:
            _digest_text(raw_digest, component.label)
            _digest_text(raw_digest, component.value)

        _digest_bytes(warning_digest, candidate_id)
        _digest_text(warning_digest, expected_warning)
        warning_digest.update(len(expected_reasons).to_bytes(8, "big"))
        for reason in expected_reasons:
            _digest_text(warning_digest, reason)
        for value in _warning_tuple(expected_signals):
            _digest_optional(warning_digest, value)

        count_values = [
            int(_scalar(stage06_batch, stage06_index, name).as_py())
            for name in REGISTRY_COLUMNS[2:]
        ]
        occurrences += count_values[0]
        standard_occurrences += count_values[1]
        native_occurrences += count_values[2]
        applicability_counts[applicability] += 1
        technical_counts[cast(str, status)] += 1
        warning_counts[expected_warning] += 1
        reason_counts.update(expected_reasons)
        rows += 1

    for stream, code in (
        (v1_rows, "V1_STREAM_ADDED_ROWS"),
        (eligibility_rows, "ELIGIBILITY_STREAM_ADDED_ROWS"),
        (v2_rows, "V2_STREAM_ADDED_ROWS"),
    ):
        try:
            next(stream)
        except StopIteration:
            continue
        _fail(code, "A controlled row stream contains added rows")

    mapback = _mapback_metrics(_paths(config.stage06_root, stage06_row_map), v2_paths)
    expected_mapback = {
        "total": EXPECTED_OCCURRENCES,
        "standard": EXPECTED_STANDARD_OCCURRENCES,
        "native": EXPECTED_NATIVE_OCCURRENCES,
        "missing": 0,
        "non_unique": 0,
    }
    if (
        rows != EXPECTED_CANDIDATES
        or occurrences != EXPECTED_OCCURRENCES
        or standard_occurrences != EXPECTED_STANDARD_OCCURRENCES
        or native_occurrences != EXPECTED_NATIVE_OCCURRENCES
        or mapback != expected_mapback
    ):
        _fail("TOTALITY_MISMATCH", "Candidate or occurrence totality differs")

    observed_applicability = dict(sorted(applicability_counts.items()))
    observed_technical = dict(sorted(technical_counts.items()))
    observed_warnings = dict(sorted(warning_counts.items()))
    observed_reasons = dict(sorted(reason_counts.items()))
    recorded = v2_manifest.get("development_metrics")
    operational = v2_manifest.get("operational_provenance")
    physical = v2_manifest.get("physical_identity")
    if not all(isinstance(value, dict) for value in (recorded, operational, physical)):
        _fail("MANIFEST_METRICS_INVALID", "A v2 manifest evidence section is absent")
    recorded = cast(dict[str, Any], recorded)
    operational = cast(dict[str, Any], operational)
    physical = cast(dict[str, Any], physical)
    bounded = physical.get("bounded_memory_architecture")
    if (
        observed_applicability != EXPECTED_APPLICABILITY_COUNTS
        or observed_technical != EXPECTED_TECHNICAL_COUNTS
        or observed_warnings != EXPECTED_WARNING_COUNTS
        or observed_reasons != EXPECTED_REASON_COUNTS
        or recorded.get("CANDIDATE_ROWS") != rows
        or recorded.get("INPUT_OCCURRENCES") != occurrences
        or recorded.get("STANDARD_OCCURRENCES") != standard_occurrences
        or recorded.get("NATIVE_OCCURRENCES") != native_occurrences
        or recorded.get("APPLICABILITY_STATUS_COUNTS") != observed_applicability
        or recorded.get("TECHNICAL_STATUS_COUNTS") != observed_technical
        or recorded.get("STRUCTURAL_WARNING_STATUS_COUNTS") != observed_warnings
        or recorded.get("STRUCTURAL_WARNING_REASON_COUNTS") != observed_reasons
        or recorded.get("PARSER_CALLS") != 0
        or recorded.get("SEMANTIC_TRUST_CLAIMS") != 0
        or operational.get("execution_git_sha") != IMPLEMENTATION_SHA
        or operational.get("parser_calls") != 0
        or not isinstance(bounded, dict)
        or bounded.get("ordered_three_way_streaming_merge") is not True
        or bounded.get("one_candidate_nested_result_deserialized_at_a_time") is not True
        or bounded.get("bounded_arrow_batches") is not True
        or bounded.get("population_sized_python_registry") is not False
        or bounded.get("population_sized_python_component_buffer") is not False
    ):
        _fail("MACHINE_EVIDENCE_MISMATCH", "Machine evidence or bounds differ")
    _validate_tracked_reports(
        config.source_root,
        applicability_counts=observed_applicability,
        technical_counts=observed_technical,
        warning_counts=observed_warnings,
        reason_counts=observed_reasons,
    )

    metrics: dict[str, object] = {
        "candidate_rows": rows,
        "occurrence_map_back": mapback,
        "applicability_status_counts": observed_applicability,
        "technical_status_counts": observed_technical,
        "structural_warning_status_counts": observed_warnings,
        "structural_warning_reason_counts": observed_reasons,
        "exact_stage06_preservation": "PASS",
        "exact_stage07_v1_raw_ordered_output_preservation": "PASS",
        "country_and_technical_consistency": "PASS",
        "warning_replay_twice_exact": "PASS",
        "parser_calls": 0,
        "semantic_trust_claims": 0,
    }
    payload: dict[str, object] = {
        "version": REVIEW_VERSION,
        "status": "STAGE07_EVIDENCE_ONLY_INDEPENDENT_REREVIEW_MACHINE_PASS",
        "reviewed_candidate_sha": config.reviewed_candidate_sha,
        "review_git_sha": config.review_git_sha,
        "implementation_sha": IMPLEMENTATION_SHA,
        "v2_manifest_sha256": EXPECTED_V2_MANIFEST_SHA256,
        "v2_contract_fingerprint": EXPECTED_CONTRACT_FINGERPRINT,
        "v2_schema_fingerprint": EXPECTED_SCHEMA_FINGERPRINT,
        "raw_preservation_digest": raw_digest.hexdigest(),
        "warning_replay_digest": warning_digest.hexdigest(),
        "metrics": metrics,
        "controlled_scope": {
            "holdout_accessed": False,
            "production_accessed": False,
            "parser_calls": 0,
            "stage08_started": False,
        },
    }
    evidence_sha = _write_json_atomic(config.output_directory, payload)
    return RereviewOutcome(
        output_directory=config.output_directory,
        evidence_sha256=evidence_sha,
        candidate_count=rows,
        occurrence_count=mapback["total"],
        raw_preservation_digest=raw_digest.hexdigest(),
        warning_replay_digest=warning_digest.hexdigest(),
        metrics=metrics,
    )


__all__ = [
    "REVIEWED_CANDIDATE_SHA",
    "REVIEW_VERSION",
    "RereviewConfig",
    "RereviewOutcome",
    "Stage07IndependentRereviewError",
    "run_independent_rereview",
]

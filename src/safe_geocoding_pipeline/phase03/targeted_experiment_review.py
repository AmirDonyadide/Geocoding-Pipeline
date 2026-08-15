from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import textwrap
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes
from ..phase02.schema import base_staging_schema, exact_schema_matches
from .constants import (
    CORE_COLUMNS,
    EVIDENCE_SCHEMA_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
    PARSER_VERSION_V2,
    PARSER_VERSION_V3,
    RULE_REGISTRY_VERSION_V3,
    RULE_REGISTRY_VERSION_V4,
)
from .pilot_runner import read_identity_set
from .review import (
    MANUAL_REVIEW_REASON_CODES_V1,
    canonicalize_manual_review_reason_codes,
)
from .review_v2 import (
    COMPONENT_LABEL_VALUES,
    ERROR_CONDITION_LABEL_VALUES,
    MAX_PROTECTED_NOTE_CHARACTERS,
    OVERALL_LABEL_VALUES,
)
from .rules import load_rule_registry
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .semantic import core_digest, evidence_digest
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)

TARGETED_REVIEW_VERSION: Final = "phase03_parser_v3_targeted_review_v1"
TARGETED_REVIEW_SCHEMA_VERSION: Final = "phase03_parser_v3_targeted_review_labels_v1"
TARGETED_LABEL_VOCABULARY_VERSION: Final = (
    "phase03_parser_v3_targeted_review_vocabularies_v1"
)
TARGETED_PROGRESS_SCHEMA_VERSION: Final = (
    "phase03_parser_v3_targeted_review_progress_sqlite_v1"
)
TARGETED_SCORE_VERSION: Final = "phase03_parser_v3_targeted_review_score_v1"
TARGETED_REVIEW_SEED: Final = (
    "safe_geocoding_pipeline:phase03_parser_v3_targeted_review_v1:seed:1"
)
EXPERIMENTAL_RULE_IDS: Final = (
    "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
    "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4",
)
REVIEWER_IDS: Final = ("Targeted-R01", "Targeted-R02")
ASSIGNMENT_ROLES: Final = {
    "Targeted-R01": "PRIMARY",
    "Targeted-R02": "INDEPENDENT_SECOND",
}
JOINT_LABEL_VALUES: Final = (
    "CORRECT",
    "INCORRECT",
    "NOT_APPLICABLE",
    "CANNOT_ASSESS",
)
RESIDUAL_ROLE_VALUES: Final = (
    "BUILDING",
    "UNIT",
    "FLOOR",
    "ORGANIZATION",
    "OTHER_KNOWN_ROLE",
    "UNKNOWN_RESIDUAL",
    "NO_MEANINGFUL_RESIDUAL",
    "CANNOT_ASSESS",
)
CANDIDATE_SUPPORT_VALUES: Final = (
    "SUPPORTED",
    "NOT_SUPPORTED",
    "NOT_APPLICABLE",
    "CANNOT_ASSESS",
)
BLIND_COMPARISON_VALUES: Final = (
    "PARSE_A_CORRECT_ONLY",
    "PARSE_B_CORRECT_ONLY",
    "BOTH_CORRECT",
    "BOTH_INCORRECT",
    "CANNOT_ASSESS",
)
TARGETED_LABEL_FIELDS: Final = (
    "street_label",
    "house_number_label",
    "joint_street_house_label",
    "residual_role_label",
    "candidate_support_label",
    "blind_parse_comparison_label",
    "parser_overreach_label",
    "missed_information_label",
    "overall_parse_acceptability_label",
)
_SCIENTIFIC_CORE_FIELDS: Final = CORE_COLUMNS[5:41]
_LOWER_HEX_64 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_RAW_DISPLAY_FIELDS: Final = (
    "street_address_line_1",
    "street_address_line_2",
    "street_address_line_3",
    "street_address_line_4",
    "street_address_line_1_native",
    "street_address_line_2_native",
    "street_address_line_3_native",
    "street_address_line_4_native",
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
    "location_information",
)
_PARSE_DISPLAY_FIELDS: Final = (
    "street_clean",
    "house_number_clean",
    "unit_clean",
    "floor_clean",
    "building_clean",
    "organization_clean",
    "postcode_clean",
    "locality_clean",
    "region_clean",
    "country_clean",
    "street_native_clean",
    "house_number_native_clean",
    "unit_native_clean",
    "floor_native_clean",
    "building_native_clean",
    "organization_native_clean",
    "address_parse_status",
    "address_completeness_class",
    "address_conflict_flags",
    "address_diagnostic_flags",
    "diagnostic_evaluation_status",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _reject_locked_path(path: Path) -> None:
    if any("locked" in part.casefold() for part in path.parts):
        raise ValueError("LOCKED paths are prohibited in targeted DEVELOPMENT review")


def _require_owner_only(path: Path) -> None:
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError("targeted-review artifact must be owner-only")
    _reject_locked_path(path.resolve(strict=True))
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("targeted-review artifact parent must be owner-only")


def current_repository_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not _COMMIT.fullmatch(commit):
        raise ValueError("current Git commit is invalid")
    return commit


def targeted_review_implementation_fingerprint() -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_targeted_review_implementation_v1\0"
    )
    root = Path(__file__).resolve().parent
    for name in ("targeted_experiment_review.py", "targeted_review_cli.py"):
        path = root / name
        digest.update(len(name.encode()).to_bytes(8, "big"))
        digest.update(name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def targeted_review_label_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("experiment_iteration", pa.string(), nullable=False),
            pa.field("reviewer_id", pa.string(), nullable=False),
            pa.field("review_round", pa.uint8(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
            pa.field("assignment_role", pa.string(), nullable=False),
            *(
                pa.field(name, pa.string(), nullable=False)
                for name in TARGETED_LABEL_FIELDS
            ),
            pa.field("reason_codes", pa.list_(pa.string()), nullable=False),
            pa.field("reason_codes_version", pa.string(), nullable=False),
            pa.field("label_vocabulary_version", pa.string(), nullable=False),
            pa.field("label_schema_version", pa.string(), nullable=False),
        ]
    )


def targeted_review_template_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("hashed_review_id", pa.string(), nullable=False),
            pa.field("experiment_iteration", pa.string(), nullable=False),
            pa.field("is_independent_review", pa.bool_(), nullable=False),
        ]
    )


def targeted_review_context_schema() -> pa.Schema:
    fields = list(base_staging_schema())
    fields.extend(
        [
            pa.field("baseline_core_json", pa.string(), nullable=False),
            pa.field("experimental_core_json", pa.string(), nullable=False),
            pa.field("baseline_evidence_json", pa.string(), nullable=False),
            pa.field("experimental_evidence_json", pa.string(), nullable=False),
            pa.field("targeted_case_metadata_json", pa.string(), nullable=False),
        ]
    )
    return pa.schema(fields)


def _hashed_review_id(identity: bytes, experiment_iteration: str) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
    )
    encoded = experiment_iteration.encode()
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(identity)
    return digest.hexdigest()


def _population_digest(identities: Sequence[bytes]) -> str:
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_population_v1\0"
    )
    for ordinal, identity in enumerate(sorted(identities), start=1):
        digest.update(ordinal.to_bytes(8, "big"))
        digest.update(identity)
    digest.update(len(identities).to_bytes(8, "big"))
    return digest.hexdigest()


def _rank(identity: bytes, reviewer_id: str) -> bytes:
    digest = hashlib.sha256()
    digest.update(TARGETED_REVIEW_SEED.encode())
    digest.update(b"\0order\0")
    digest.update(reviewer_id.encode())
    digest.update(identity)
    return digest.digest()


def _experimental_is_parse_a(identity: bytes, reviewer_id: str) -> bool:
    digest = hashlib.sha256()
    digest.update(TARGETED_REVIEW_SEED.encode())
    digest.update(b"\0blind-parse-order\0")
    digest.update(reviewer_id.encode())
    digest.update(identity)
    return bool(digest.digest()[0] & 1)


def _read_core(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_core_schema_matches(parquet.schema_arrow):
        raise ValueError("targeted-review core schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_core_rows(rows)
    return rows


def _read_evidence(path: Path) -> list[dict[str, Any]]:
    parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
    if not exact_evidence_schema_matches(parquet.schema_arrow):
        raise ValueError("targeted-review evidence schema mismatch")
    rows = cast(list[dict[str, Any]], parquet.read(use_threads=False).to_pylist())
    validate_evidence_rows(rows)
    return rows


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _canonical_json_text(value: Any) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class PreparedTargetedReview:
    context_path: Path
    template_path: Path
    manifest_path: Path
    population_count: int
    population_digest: str


def prepare_targeted_review_artifacts(
    *,
    development_payload_path: Path,
    development_identities_path: Path,
    baseline_core_path: Path,
    baseline_evidence_path: Path,
    experimental_core_path: Path,
    experimental_evidence_path: Path,
    output_directory: Path,
    experiment_iteration: str,
    experimental_parser_commit: str,
    review_implementation_commit: str,
    expected_development_rows: int,
    expected_population_count: int,
    production: bool,
) -> PreparedTargetedReview:
    """Create immutable protected review inputs without initializing labels."""
    paths = (
        development_payload_path,
        development_identities_path,
        baseline_core_path,
        baseline_evidence_path,
        experimental_core_path,
        experimental_evidence_path,
        output_directory,
    )
    for path in paths:
        _reject_locked_path(path)
    if production:
        from ..execution_policy import require_goethe_nhr_slurm

        require_goethe_nhr_slurm("phase03-targeted-parser-v3-review-prepare")
    if expected_development_rows < 1 or expected_population_count < 1:
        raise ValueError("targeted-review expected counts must be positive")
    if not experiment_iteration or not _COMMIT.fullmatch(experimental_parser_commit):
        raise ValueError("targeted-review experiment provenance is invalid")
    if not _COMMIT.fullmatch(review_implementation_commit):
        raise ValueError("targeted-review implementation commit is invalid")
    if output_directory.exists():
        raise FileExistsError("targeted-review output already exists")
    input_paths = paths[:-1]
    for path in input_paths:
        if not path.is_file():
            raise FileNotFoundError("targeted-review input is missing")
        if path.is_symlink():
            raise ValueError("targeted-review input may not be a symbolic link")
        _reject_locked_path(path.resolve(strict=True))
    before = {
        str(path): (file_sha256(path), path.stat().st_size) for path in input_paths
    }

    identity_metadata, identities = read_identity_set(development_identities_path)
    if identity_metadata.get("partition") != "DEVELOPMENT":
        raise ValueError("targeted-review identity set is not DEVELOPMENT")
    if len(identities) != expected_development_rows or len(set(identities)) != len(
        identities
    ):
        raise ValueError("targeted-review DEVELOPMENT identity count mismatch")
    identity_set = set(identities)

    payload_file = pq.ParquetFile(
        development_payload_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_schema_matches(payload_file.schema_arrow):
        raise ValueError("targeted-review Phase 2 payload schema mismatch")
    payload = payload_file.read(use_threads=False)
    if payload.num_rows != expected_development_rows:
        raise ValueError("targeted-review Phase 2 payload row count mismatch")
    payload_ids = [bytes(value) for value in payload["stable_source_row_id_v1"]]
    if len(set(payload_ids)) != len(payload_ids) or set(payload_ids) != identity_set:
        raise ValueError("targeted-review payload identity mismatch")

    baseline = _read_core(baseline_core_path)
    baseline_evidence = _read_evidence(baseline_evidence_path)
    experimental = _read_core(experimental_core_path)
    experimental_evidence = _read_evidence(experimental_evidence_path)
    if (
        len(baseline) != expected_development_rows
        or len(experimental) != expected_development_rows
    ):
        raise ValueError("targeted-review core row count mismatch")
    baseline_ids = [bytes(row["stable_source_row_id_v1"]) for row in baseline]
    experimental_ids = [bytes(row["stable_source_row_id_v1"]) for row in experimental]
    if baseline_ids != experimental_ids or set(baseline_ids) != identity_set:
        raise ValueError("targeted-review core identity/order mismatch")
    if {row["parser_version"] for row in baseline} != {PARSER_VERSION_V2}:
        raise ValueError("targeted-review baseline parser mismatch")
    if {row["rule_registry_version"] for row in baseline} != {RULE_REGISTRY_VERSION_V3}:
        raise ValueError("targeted-review baseline registry mismatch")
    if {row["parser_version"] for row in experimental} != {PARSER_VERSION_V3}:
        raise ValueError("targeted-review experimental parser mismatch")
    if {row["rule_registry_version"] for row in experimental} != {
        RULE_REGISTRY_VERSION_V4
    }:
        raise ValueError("targeted-review experimental registry mismatch")
    baseline_configuration_fingerprints = {
        bytes(row["configuration_fingerprint"]) for row in baseline
    }
    experimental_configuration_fingerprints = {
        bytes(row["configuration_fingerprint"]) for row in experimental
    }
    if (
        len(baseline_configuration_fingerprints) != 1
        or len(experimental_configuration_fingerprints) != 1
    ):
        raise ValueError("targeted-review configuration fingerprint is not uniform")
    validate_core_evidence_relationship(baseline, baseline_evidence)
    validate_core_evidence_relationship(experimental, experimental_evidence)
    if {
        bytes(row["stable_source_row_id_v1"]) for row in baseline_evidence
    } - identity_set or {
        bytes(row["stable_source_row_id_v1"]) for row in experimental_evidence
    } - identity_set:
        raise ValueError("targeted-review evidence identity mismatch")

    changed_ids = {
        bytes(before_row["stable_source_row_id_v1"])
        for before_row, after_row in zip(baseline, experimental, strict=True)
        if any(
            before_row[field] != after_row[field] for field in _SCIENTIFIC_CORE_FIELDS
        )
    }
    evidence_ids = {
        bytes(row["stable_source_row_id_v1"])
        for row in experimental_evidence
        if row["rule_id"] in EXPERIMENTAL_RULE_IDS
    }
    population = tuple(sorted(changed_ids | evidence_ids))
    if len(population) != expected_population_count:
        raise ValueError(
            "TARGETED_REVIEW_POPULATION_COUNT_MISMATCH: "
            f"computed={len(population)} expected={expected_population_count} "
            f"changed={len(changed_ids)} experimental_evidence={len(evidence_ids)}"
        )

    baseline_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in baseline}
    experimental_by_id = {
        bytes(row["stable_source_row_id_v1"]): row for row in experimental
    }
    baseline_evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    experimental_evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    for row in baseline_evidence:
        baseline_evidence_by_id.setdefault(
            bytes(row["stable_source_row_id_v1"]), []
        ).append(row)
    for row in experimental_evidence:
        experimental_evidence_by_id.setdefault(
            bytes(row["stable_source_row_id_v1"]), []
        ).append(row)
    for identity in evidence_ids:
        experiment_rows = [
            row
            for row in experimental_evidence_by_id[identity]
            if row["rule_id"] in EXPERIMENTAL_RULE_IDS
        ]
        observed_rules = {str(row["rule_id"]) for row in experiment_rows}
        selection_states = {bool(row["selected"]) for row in experiment_rows}
        if observed_rules != set(EXPERIMENTAL_RULE_IDS) or len(selection_states) != 1:
            raise ValueError(
                "targeted-review experimental street/house evidence is not paired"
            )
    payload_by_id = {
        bytes(row["stable_source_row_id_v1"]): row for row in payload.to_pylist()
    }

    context_rows: list[dict[str, Any]] = []
    template_rows: list[dict[str, Any]] = []
    for identity in population:
        experiment_rows = [
            row
            for row in experimental_evidence_by_id.get(identity, [])
            if row["rule_id"] in EXPERIMENTAL_RULE_IDS
        ]
        evidence_groups = {int(row["evidence_id"]) for row in experiment_rows}
        metadata = {
            "scientific_output_changed": identity in changed_ids,
            "experimental_evidence_present": identity in evidence_ids,
            "experimental_candidate_group_count": len(evidence_groups),
            "experimental_selected": any(
                bool(row["selected"]) for row in experiment_rows
            ),
        }
        context_rows.append(
            {
                **payload_by_id[identity],
                "baseline_core_json": _canonical_json_text(baseline_by_id[identity]),
                "experimental_core_json": _canonical_json_text(
                    experimental_by_id[identity]
                ),
                "baseline_evidence_json": _canonical_json_text(
                    baseline_evidence_by_id.get(identity, [])
                ),
                "experimental_evidence_json": _canonical_json_text(
                    experimental_evidence_by_id.get(identity, [])
                ),
                "targeted_case_metadata_json": _canonical_json_text(metadata),
            }
        )
        template_rows.append(
            {
                "hashed_review_id": _hashed_review_id(identity, experiment_iteration),
                "experiment_iteration": experiment_iteration,
                "is_independent_review": True,
            }
        )

    temporary = output_directory.with_name(
        f".{output_directory.name}.prepare.{os.getpid()}"
    )
    temporary.mkdir(parents=True, mode=0o700)
    temporary.chmod(0o700)
    try:
        context_path = temporary / "protected_targeted_review_context.parquet"
        template_path = temporary / "protected_targeted_review_template.parquet"
        manifest_path = temporary / "targeted_review_input_manifest.json"
        pq.write_table(
            pa.Table.from_pylist(context_rows, schema=targeted_review_context_schema()),
            context_path,
            compression="zstd",
            compression_level=3,
            row_group_size=max(1, len(context_rows)),
            write_statistics=False,
            write_page_checksum=True,
        )
        pq.write_table(
            pa.Table.from_pylist(
                template_rows, schema=targeted_review_template_schema()
            ),
            template_path,
            compression="zstd",
            compression_level=3,
            row_group_size=max(1, len(template_rows)),
            write_statistics=False,
            write_page_checksum=True,
        )
        context_path.chmod(0o600)
        template_path.chmod(0o600)
        verified_context = pq.ParquetFile(
            context_path, page_checksum_verification=True, pre_buffer=True
        )
        verified_template = pq.ParquetFile(
            template_path, page_checksum_verification=True, pre_buffer=True
        )
        if (
            verified_context.metadata.num_rows != len(population)
            or verified_template.metadata.num_rows != len(population)
            or not verified_context.schema_arrow.remove_metadata().equals(
                targeted_review_context_schema(), check_metadata=False
            )
            or not verified_template.schema_arrow.remove_metadata().equals(
                targeted_review_template_schema(), check_metadata=False
            )
        ):
            raise ValueError("targeted-review artifact read-back validation failed")
        manifest: dict[str, JsonValue] = {
            "manifest_version": "phase03_parser_v3_targeted_review_input_manifest_v1",
            "status": "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS",
            "experiment_iteration": experiment_iteration,
            "experimental_parser_commit": experimental_parser_commit,
            "review_implementation_commit": review_implementation_commit,
            "review_implementation_fingerprint": targeted_review_implementation_fingerprint(),
            "targeted_review_version": TARGETED_REVIEW_VERSION,
            "targeted_review_seed": TARGETED_REVIEW_SEED,
            "population_definition": (
                "SCIENTIFIC_OUTPUT_CHANGE_UNION_EXPERIMENTAL_RULE_EVIDENCE"
            ),
            "development_rows": expected_development_rows,
            "development_identity_digest": str(identity_metadata["identity_digest"]),
            "scientific_output_change_rows": len(changed_ids),
            "experimental_rule_evidence_rows": len(evidence_ids),
            "targeted_review_population_rows": len(population),
            "targeted_review_population_digest": _population_digest(population),
            "reviewer_1_rows": len(population),
            "reviewer_2_rows": len(population),
            "all_rows_independent_double_review": True,
            "locked_rows_read": 0,
            "input_artifacts": {},
            "output_artifacts": {
                "protected_context": {
                    "artifact_name": context_path.name,
                    "sha256": file_sha256(context_path),
                    "size_bytes": context_path.stat().st_size,
                },
                "protected_template": {
                    "artifact_name": template_path.name,
                    "sha256": file_sha256(template_path),
                    "size_bytes": template_path.stat().st_size,
                },
            },
            "parser_versions": {
                "baseline": PARSER_VERSION_V2,
                "experimental": PARSER_VERSION_V3,
            },
            "rule_registry_versions": {
                "baseline": RULE_REGISTRY_VERSION_V3,
                "experimental": RULE_REGISTRY_VERSION_V4,
            },
            "rule_registry_fingerprints": {
                "baseline": load_rule_registry(
                    registry_version=RULE_REGISTRY_VERSION_V3
                ).fingerprint,
                "experimental": load_rule_registry(
                    registry_version=RULE_REGISTRY_VERSION_V4
                ).fingerprint,
            },
            "configuration_fingerprints": {
                "baseline": bytes(baseline[0]["configuration_fingerprint"]).hex(),
                "experimental": bytes(
                    experimental[0]["configuration_fingerprint"]
                ).hex(),
            },
            "semantic_digests": {
                "baseline_core": core_digest(
                    baseline, str(baseline[0]["component_schema_version"])
                ).hex(),
                "baseline_evidence": evidence_digest(
                    baseline_evidence, EVIDENCE_SCHEMA_VERSION
                ).hex(),
                "experimental_core": core_digest(
                    experimental, str(experimental[0]["component_schema_version"])
                ).hex(),
                "experimental_evidence": evidence_digest(
                    experimental_evidence, EVIDENCE_SCHEMA_VERSION
                ).hex(),
            },
            "page_checksums_verified": True,
            "portable_raw_values": False,
            "scientific_promotion_decision": "NOT_EVALUATED",
        }
        artifact_roles = (
            "development_payload",
            "development_identities",
            "baseline_core",
            "baseline_evidence",
            "experimental_core",
            "experimental_evidence",
        )
        manifest_inputs = cast(dict[str, JsonValue], manifest["input_artifacts"])
        for role, path in zip(artifact_roles, input_paths, strict=True):
            sha256, size = before[str(path)]
            if file_sha256(path) != sha256 or path.stat().st_size != size:
                raise ValueError("targeted-review read-only input changed")
            manifest_inputs[role] = {"sha256": sha256, "size_bytes": size}
        with manifest_path.open("xb") as stream:
            os.chmod(manifest_path, 0o600)
            stream.write(canonical_json_bytes(manifest) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        _fsync_parent(output_directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return PreparedTargetedReview(
        output_directory / "protected_targeted_review_context.parquet",
        output_directory / "protected_targeted_review_template.parquet",
        output_directory / "targeted_review_input_manifest.json",
        len(population),
        _population_digest(population),
    )


def _validate_exact(value: Any, allowed: Sequence[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"invalid targeted-review value for {field}")
    return value


def validate_targeted_labels(
    labels: Mapping[str, str],
    reason_codes: Iterable[str],
    *,
    protected_note: str | None,
) -> tuple[str, ...]:
    if set(labels) != set(TARGETED_LABEL_FIELDS):
        raise ValueError("targeted-review label field mismatch")
    street = _validate_exact(labels["street_label"], COMPONENT_LABEL_VALUES, "street")
    house = _validate_exact(
        labels["house_number_label"], COMPONENT_LABEL_VALUES, "house_number"
    )
    joint = _validate_exact(
        labels["joint_street_house_label"], JOINT_LABEL_VALUES, "joint"
    )
    residual = _validate_exact(
        labels["residual_role_label"], RESIDUAL_ROLE_VALUES, "residual_role"
    )
    candidate = _validate_exact(
        labels["candidate_support_label"],
        CANDIDATE_SUPPORT_VALUES,
        "candidate_support",
    )
    comparison = _validate_exact(
        labels["blind_parse_comparison_label"],
        BLIND_COMPARISON_VALUES,
        "blind_parse_comparison",
    )
    overreach = _validate_exact(
        labels["parser_overreach_label"],
        ERROR_CONDITION_LABEL_VALUES,
        "parser_overreach",
    )
    missed = _validate_exact(
        labels["missed_information_label"],
        ERROR_CONDITION_LABEL_VALUES,
        "missed_information",
    )
    overall = _validate_exact(
        labels["overall_parse_acceptability_label"], OVERALL_LABEL_VALUES, "overall"
    )
    if (
        protected_note is not None
        and len(protected_note) > MAX_PROTECTED_NOTE_CHARACTERS
    ):
        raise ValueError("protected note exceeds 500 Unicode characters")
    canonical = canonicalize_manual_review_reason_codes(
        reason_codes, protected_adjudication_note=protected_note
    )
    if not canonical:
        raise ValueError("completed targeted review requires a reason code")
    reasons = set(canonical)
    uncertain = (
        "CANNOT_ASSESS" in {street, house, joint, residual, candidate, comparison}
        or overreach == "CANNOT_ASSESS"
        or missed == "CANNOT_ASSESS"
        or overall == "CANNOT_ASSESS"
    )
    if uncertain and reasons.isdisjoint(
        {"SOURCE_AMBIGUOUS", "INSUFFICIENT_SOURCE_EVIDENCE"}
    ):
        raise ValueError("uncertain targeted review requires an uncertainty reason")
    if (street == "MISSED" or house == "MISSED") and missed != "PRESENT":
        raise ValueError("component MISSED requires missed information PRESENT")
    if missed == "ABSENT" and (street == "MISSED" or house == "MISSED"):
        raise ValueError("missed information ABSENT forbids component MISSED")
    if (street == "MISSED" or house == "MISSED" or missed == "PRESENT") and (
        "MISSED_EXTRACTABLE_COMPONENT" not in reasons
    ):
        raise ValueError("missed extraction requires MISSED_EXTRACTABLE_COMPONENT")
    if (
        street == "INCORRECT" or house == "INCORRECT" or joint == "INCORRECT"
    ) and reasons.isdisjoint(
        {
            "WRONG_COMPONENT_ROLE",
            "WRONG_VALUE",
            "WRONG_SPAN_BOUNDARY",
            "FALSE_POSITIVE_EXTRACTION",
            "WRONG_NORMALIZATION",
            "WRONG_PROVENANCE",
        }
    ):
        raise ValueError("incorrect targeted result requires an applicable reason")
    if overreach == "PRESENT" and reasons.isdisjoint(
        {"FALSE_POSITIVE_EXTRACTION", "WRONG_COMPONENT_ROLE"}
    ):
        raise ValueError("parser overreach requires an applicable reason")
    if "CORRECT_AS_IS" in reasons and len(reasons) != 1:
        raise ValueError("CORRECT_AS_IS is exclusive")
    if "CORRECT_AS_IS" in reasons and (
        street in {"INCORRECT", "MISSED", "CANNOT_ASSESS"}
        or house in {"INCORRECT", "MISSED", "CANNOT_ASSESS"}
        or joint in {"INCORRECT", "CANNOT_ASSESS"}
        or candidate in {"NOT_SUPPORTED", "CANNOT_ASSESS"}
        or comparison in {"BOTH_INCORRECT", "CANNOT_ASSESS"}
        or overreach != "ABSENT"
        or missed != "ABSENT"
        or overall != "ACCEPTABLE"
    ):
        raise ValueError("CORRECT_AS_IS conflicts with targeted-review labels")
    return canonical


@dataclass(frozen=True, slots=True)
class TargetedReviewBinding:
    experiment_iteration: str
    context_sha256: str
    context_size_bytes: int
    template_sha256: str
    template_size_bytes: int
    population_count: int
    population_digest: str
    implementation_commit: str
    implementation_fingerprint: str

    def as_metadata(self) -> dict[str, str]:
        return {
            "progress_schema_version": TARGETED_PROGRESS_SCHEMA_VERSION,
            "experiment_iteration": self.experiment_iteration,
            "context_sha256": self.context_sha256,
            "context_size_bytes": str(self.context_size_bytes),
            "template_sha256": self.template_sha256,
            "template_size_bytes": str(self.template_size_bytes),
            "population_count": str(self.population_count),
            "population_digest": self.population_digest,
            "implementation_commit": self.implementation_commit,
            "implementation_fingerprint": self.implementation_fingerprint,
            "targeted_review_seed": TARGETED_REVIEW_SEED,
            "label_schema_version": TARGETED_REVIEW_SCHEMA_VERSION,
            "label_vocabulary_version": TARGETED_LABEL_VOCABULARY_VERSION,
            "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
        }


class TargetedReviewStore:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        _reject_locked_path(path)
        if not path.is_file():
            raise FileNotFoundError("targeted-review progress database is missing")
        _require_owner_only(path)
        uri = f"file:{path}?mode=ro" if readonly else str(path)
        self.connection = sqlite3.connect(uri, uri=readonly)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            self.connection.close()
            raise ValueError("targeted-review progress database integrity check failed")

    def __enter__(self) -> TargetedReviewStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.connection.close()

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        binding: TargetedReviewBinding,
        reviewer_id: str,
        identities: Sequence[tuple[str, bytes]],
    ) -> TargetedReviewStore:
        if reviewer_id not in REVIEWER_IDS or not identities:
            raise ValueError("invalid targeted-review assignment")
        path.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
        path.parent.chmod(0o700)
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(
                """
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE assignment(
                    hashed_review_id TEXT PRIMARY KEY,
                    display_order INTEGER NOT NULL UNIQUE,
                    status TEXT NOT NULL CHECK(status IN ('PENDING','IN_PROGRESS','COMPLETE')),
                    is_independent_review INTEGER NOT NULL CHECK(is_independent_review=1)
                );
                CREATE TABLE label(
                    hashed_review_id TEXT PRIMARY KEY REFERENCES assignment(hashed_review_id),
                    labels_json TEXT NOT NULL,
                    reason_codes_json TEXT NOT NULL,
                    protected_note TEXT,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE review_cursor(
                    reviewer_id TEXT PRIMARY KEY,
                    current_display_order INTEGER NOT NULL
                );
                """
            )
            metadata = {
                **binding.as_metadata(),
                "reviewer_id": reviewer_id,
                "assignment_role": ASSIGNMENT_ROLES[reviewer_id],
                "expected_assignment_count": str(len(identities)),
            }
            with connection:
                connection.executemany(
                    "INSERT INTO metadata(key,value) VALUES(?,?)", metadata.items()
                )
                ordered = sorted(
                    identities, key=lambda item: (_rank(item[1], reviewer_id), item[1])
                )
                connection.executemany(
                    "INSERT INTO assignment VALUES(?,?,?,1)",
                    (
                        (hashed_id, display_order, "PENDING")
                        for display_order, (hashed_id, _) in enumerate(ordered)
                    ),
                )
                connection.execute(
                    "INSERT INTO review_cursor VALUES(?,0)", (reviewer_id,)
                )
            connection.execute("PRAGMA wal_checkpoint(FULL)")
        finally:
            connection.close()
        path.chmod(0o600)
        _fsync_parent(path)
        return cls(path)

    def metadata(self) -> dict[str, str]:
        return {
            str(row[0]): str(row[1])
            for row in self.connection.execute(
                "SELECT key,value FROM metadata ORDER BY key"
            )
        }

    def assignment_ids(self) -> tuple[str, ...]:
        return tuple(
            str(row[0])
            for row in self.connection.execute(
                "SELECT hashed_review_id FROM assignment ORDER BY display_order"
            )
        )

    def current_assignment(self) -> dict[str, Any] | None:
        reviewer = self.metadata()["reviewer_id"]
        row = self.connection.execute(
            """
            SELECT * FROM assignment
            WHERE display_order=(SELECT current_display_order FROM review_cursor WHERE reviewer_id=?)
            """,
            (reviewer,),
        ).fetchone()
        if row is not None and row["status"] != "COMPLETE":
            return dict(row)
        row = self.connection.execute(
            "SELECT * FROM assignment WHERE status!='COMPLETE' ORDER BY display_order LIMIT 1"
        ).fetchone()
        return None if row is None else dict(row)

    def save_completed(
        self,
        hashed_review_id: str,
        labels: Mapping[str, str],
        reason_codes: Iterable[str],
        *,
        protected_note: str | None,
    ) -> None:
        canonical = validate_targeted_labels(
            labels, reason_codes, protected_note=protected_note
        )
        assignment = self.connection.execute(
            "SELECT * FROM assignment WHERE hashed_review_id=?", (hashed_review_id,)
        ).fetchone()
        if assignment is None:
            raise KeyError("targeted review identity is not assigned")
        next_row = self.connection.execute(
            "SELECT display_order FROM assignment WHERE display_order>? ORDER BY display_order LIMIT 1",
            (assignment["display_order"],),
        ).fetchone()
        next_order = int(next_row[0]) if next_row else int(assignment["display_order"])
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO label VALUES(?,?,?,?,?)
                ON CONFLICT(hashed_review_id) DO UPDATE SET
                  labels_json=excluded.labels_json,
                  reason_codes_json=excluded.reason_codes_json,
                  protected_note=excluded.protected_note,
                  updated_at_utc=excluded.updated_at_utc
                """,
                (
                    hashed_review_id,
                    _canonical_json_text(dict(labels)),
                    _canonical_json_text(list(canonical)),
                    protected_note,
                    utc_now(),
                ),
            )
            self.connection.execute(
                "UPDATE assignment SET status='COMPLETE' WHERE hashed_review_id=?",
                (hashed_review_id,),
            )
            self.connection.execute(
                "UPDATE review_cursor SET current_display_order=?", (next_order,)
            )

    def summary(self) -> dict[str, JsonValue]:
        counts = {
            str(row[0]): int(row[1])
            for row in self.connection.execute(
                "SELECT status,COUNT(*) FROM assignment GROUP BY status"
            )
        }
        total = sum(counts.values())
        complete = counts.get("COMPLETE", 0)
        return {
            "status": "COMPLETE" if complete == total else "IN_PROGRESS",
            "reviewer_id": self.metadata()["reviewer_id"],
            "assignment_count": total,
            "complete_count": complete,
            "pending_count": total - complete,
        }

    def completed_rows(self) -> list[dict[str, Any]]:
        if self.summary()["status"] != "COMPLETE":
            raise ValueError("targeted reviewer assignments are incomplete")
        metadata = self.metadata()
        result: list[dict[str, Any]] = []
        rows = self.connection.execute(
            """
            SELECT a.hashed_review_id,l.labels_json,l.reason_codes_json,l.protected_note
            FROM assignment a JOIN label l USING(hashed_review_id)
            ORDER BY a.hashed_review_id
            """
        )
        for row in rows:
            labels = json.loads(str(row["labels_json"]))
            reasons = json.loads(str(row["reason_codes_json"]))
            validate_targeted_labels(
                labels, reasons, protected_note=row["protected_note"]
            )
            result.append(
                {
                    "hashed_review_id": str(row["hashed_review_id"]),
                    "experiment_iteration": metadata["experiment_iteration"],
                    "reviewer_id": metadata["reviewer_id"],
                    "review_round": 1,
                    "is_independent_review": True,
                    "assignment_role": metadata["assignment_role"],
                    **labels,
                    "reason_codes": reasons,
                    "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                    "label_vocabulary_version": TARGETED_LABEL_VOCABULARY_VERSION,
                    "label_schema_version": TARGETED_REVIEW_SCHEMA_VERSION,
                }
            )
        return result


@dataclass(frozen=True, slots=True)
class TargetedContext:
    path: Path
    table: pa.Table
    experiment_iteration: str
    by_hashed_id: Mapping[str, int]

    @classmethod
    def open(cls, path: Path, experiment_iteration: str) -> TargetedContext:
        _reject_locked_path(path)
        _require_owner_only(path)
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        if not parquet.schema_arrow.remove_metadata().equals(
            targeted_review_context_schema(), check_metadata=False
        ):
            raise ValueError("targeted-review context schema mismatch")
        table = parquet.read(use_threads=False)
        mapping: dict[str, int] = {}
        for index, raw in enumerate(table["stable_source_row_id_v1"]):
            hashed = _hashed_review_id(bytes(raw.as_py()), experiment_iteration)
            if hashed in mapping:
                raise ValueError("targeted-review context identity duplicate")
            mapping[hashed] = index
        return cls(path, table, experiment_iteration, mapping)

    def case(self, hashed_review_id: str, reviewer_id: str) -> dict[str, Any]:
        index = self.by_hashed_id[hashed_review_id]
        identity = bytes(self.table["stable_source_row_id_v1"][index].as_py())
        baseline = json.loads(str(self.table["baseline_core_json"][index].as_py()))
        experimental = json.loads(
            str(self.table["experimental_core_json"][index].as_py())
        )
        evidence = json.loads(
            str(self.table["experimental_evidence_json"][index].as_py())
        )
        experimental_is_a = _experimental_is_parse_a(identity, reviewer_id)
        parse_a = experimental if experimental_is_a else baseline
        parse_b = baseline if experimental_is_a else experimental
        candidates = []
        for row in evidence:
            if row.get("rule_id") not in EXPERIMENTAL_RULE_IDS:
                continue
            candidates.append(
                {
                    "component": row.get("component"),
                    "candidate_value": row.get("candidate_value"),
                    "confidence": row.get("confidence"),
                    "source_field": row.get("source_field"),
                    "start_character": row.get("start_character"),
                    "end_character_exclusive": row.get("end_character_exclusive"),
                }
            )
        raw = {field: self.table[field][index].as_py() for field in _RAW_DISPLAY_FIELDS}
        return {
            "hashed_review_id": hashed_review_id,
            "raw": raw,
            "parse_a": {field: parse_a.get(field) for field in _PARSE_DISPLAY_FIELDS},
            "parse_b": {field: parse_b.get(field) for field in _PARSE_DISPLAY_FIELDS},
            "candidate_hypotheses": candidates,
        }


def initialize_targeted_review_workspace(
    *,
    context_path: Path,
    template_path: Path,
    manifest_path: Path,
    output_directory: Path,
    implementation_commit: str,
) -> tuple[Path, Path]:
    for path in (context_path, template_path, manifest_path, output_directory):
        _reject_locked_path(path)
    if output_directory.exists():
        raise FileExistsError("targeted-review progress output already exists")
    if implementation_commit != current_repository_commit():
        raise ValueError("targeted-review implementation commit mismatch")
    for path in (context_path, template_path, manifest_path):
        _require_owner_only(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS":
        raise ValueError("targeted-review input manifest status mismatch")
    if manifest.get("review_implementation_commit") != implementation_commit:
        raise ValueError("targeted-review input was prepared by another commit")
    if (
        manifest.get("review_implementation_fingerprint")
        != targeted_review_implementation_fingerprint()
    ):
        raise ValueError("targeted-review implementation fingerprint mismatch")
    output_artifacts = manifest.get("output_artifacts")
    if not isinstance(output_artifacts, dict):
        raise ValueError("targeted-review input manifest is incomplete")
    for role, path in (
        ("protected_context", context_path),
        ("protected_template", template_path),
    ):
        expected = output_artifacts.get(role)
        if (
            not isinstance(expected, dict)
            or expected.get("sha256") != file_sha256(path)
            or expected.get("size_bytes") != path.stat().st_size
        ):
            raise ValueError("targeted-review prepared artifact identity mismatch")
    template_file = pq.ParquetFile(
        template_path, page_checksum_verification=True, pre_buffer=True
    )
    if not template_file.schema_arrow.remove_metadata().equals(
        targeted_review_template_schema(), check_metadata=False
    ):
        raise ValueError("targeted-review template schema mismatch")
    template = template_file.read(use_threads=False).to_pylist()
    population_count = int(manifest["targeted_review_population_rows"])
    if len(template) != population_count or not all(
        row["is_independent_review"] is True for row in template
    ):
        raise ValueError("targeted-review template count/designation mismatch")
    experiment_iteration = str(manifest["experiment_iteration"])
    context = TargetedContext.open(context_path, experiment_iteration)
    identities: list[tuple[str, bytes]] = []
    for row in template:
        hashed = str(row["hashed_review_id"])
        if not _LOWER_HEX_64.fullmatch(hashed) or hashed not in context.by_hashed_id:
            raise ValueError("targeted-review template identity mismatch")
        index = context.by_hashed_id[hashed]
        identity = bytes(context.table["stable_source_row_id_v1"][index].as_py())
        identities.append((hashed, identity))
    if len({item[0] for item in identities}) != population_count:
        raise ValueError("targeted-review template identity duplicate")
    binding = TargetedReviewBinding(
        experiment_iteration=experiment_iteration,
        context_sha256=file_sha256(context_path),
        context_size_bytes=context_path.stat().st_size,
        template_sha256=file_sha256(template_path),
        template_size_bytes=template_path.stat().st_size,
        population_count=population_count,
        population_digest=str(manifest["targeted_review_population_digest"]),
        implementation_commit=implementation_commit,
        implementation_fingerprint=targeted_review_implementation_fingerprint(),
    )
    temporary = output_directory.with_name(
        f".{output_directory.name}.initialize.{os.getpid()}"
    )
    temporary.mkdir(parents=True, mode=0o700)
    temporary.chmod(0o700)
    try:
        paths = []
        for reviewer in REVIEWER_IDS:
            path = temporary / reviewer / "targeted_review_progress.sqlite3"
            with TargetedReviewStore.create(
                path, binding=binding, reviewer_id=reviewer, identities=identities
            ):
                pass
            paths.append(path)
        if (
            file_sha256(context_path) != binding.context_sha256
            or context_path.stat().st_size != binding.context_size_bytes
            or file_sha256(template_path) != binding.template_sha256
            or template_path.stat().st_size != binding.template_size_bytes
        ):
            raise ValueError(
                "targeted-review prepared input changed during initialization"
            )
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        _fsync_parent(output_directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return (
        output_directory / REVIEWER_IDS[0] / "targeted_review_progress.sqlite3",
        output_directory / REVIEWER_IDS[1] / "targeted_review_progress.sqlite3",
    )


def _wrap(label: str, value: Any, width: int = 100) -> list[str]:
    prefix = f"{label}: "
    text = "" if value is None else str(value)
    wrapped = textwrap.wrap(
        text, width=max(10, width - len(prefix)), replace_whitespace=False
    ) or [""]
    return [prefix + wrapped[0], *(" " * len(prefix) + part for part in wrapped[1:])]


def render_targeted_case(case: Mapping[str, Any]) -> str:
    lines = [f"Review ID: {case['hashed_review_id']}", "", "PROTECTED SOURCE"]
    for field, value in cast(Mapping[str, Any], case["raw"]).items():
        lines.extend(_wrap(field, value))
    for name in ("parse_a", "parse_b"):
        lines.extend(("", name.upper().replace("_", " ")))
        for field, value in cast(Mapping[str, Any], case[name]).items():
            lines.extend(_wrap(field, value))
    lines.extend(("", "BLINDED CANDIDATE HYPOTHESES"))
    for index, candidate in enumerate(
        cast(Sequence[Mapping[str, Any]], case["candidate_hypotheses"]), start=1
    ):
        lines.append(f"-- Candidate {index} --")
        for field, value in candidate.items():
            lines.extend(_wrap(field, value))
    lines.append(
        "[Parser versions, rule IDs, and selected/rejected state are intentionally hidden.]"
    )
    return "\n".join(lines)


def _prompt_choice(
    field: str, choices: Sequence[str], input_fn: Callable[[str], str]
) -> str:
    menu = " ".join(f"{index + 1}={value}" for index, value in enumerate(choices))
    while True:
        answer = input_fn(f"{field} [{menu}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]


def collect_targeted_labels(
    *, input_fn: Callable[[str], str] = input
) -> tuple[dict[str, str], tuple[str, ...], str | None]:
    labels = {
        "street_label": _prompt_choice(
            "street_label", COMPONENT_LABEL_VALUES, input_fn
        ),
        "house_number_label": _prompt_choice(
            "house_number_label", COMPONENT_LABEL_VALUES, input_fn
        ),
        "joint_street_house_label": _prompt_choice(
            "joint_street_house_label", JOINT_LABEL_VALUES, input_fn
        ),
        "residual_role_label": _prompt_choice(
            "residual_role_label", RESIDUAL_ROLE_VALUES, input_fn
        ),
        "candidate_support_label": _prompt_choice(
            "candidate_support_label", CANDIDATE_SUPPORT_VALUES, input_fn
        ),
        "blind_parse_comparison_label": _prompt_choice(
            "blind_parse_comparison_label", BLIND_COMPARISON_VALUES, input_fn
        ),
        "parser_overreach_label": _prompt_choice(
            "parser_overreach_label", ERROR_CONDITION_LABEL_VALUES, input_fn
        ),
        "missed_information_label": _prompt_choice(
            "missed_information_label", ERROR_CONDITION_LABEL_VALUES, input_fn
        ),
        "overall_parse_acceptability_label": _prompt_choice(
            "overall_parse_acceptability_label", OVERALL_LABEL_VALUES, input_fn
        ),
    }
    reason_menu = " ".join(
        f"{index + 1}={value}"
        for index, value in enumerate(MANUAL_REVIEW_REASON_CODES_V1)
    )
    while True:
        raw = input_fn(f"reason codes, comma-separated [{reason_menu}]: ").strip()
        try:
            positions = tuple(int(value.strip()) for value in raw.split(","))
        except ValueError:
            continue
        if positions and all(
            1 <= value <= len(MANUAL_REVIEW_REASON_CODES_V1) for value in positions
        ):
            reasons = tuple(
                MANUAL_REVIEW_REASON_CODES_V1[value - 1] for value in positions
            )
            break
    note_value = input_fn("protected note (optional, max 500 characters): ")
    note = note_value or None
    canonical = validate_targeted_labels(labels, reasons, protected_note=note)
    return labels, canonical, note


def run_targeted_review(
    *, progress_database: Path, context_path: Path, line_mode: bool = False
) -> None:
    # The line interface is deliberately the fallback and the testable core. A
    # minimal curses wrapper pages the same text and delegates label entry.
    with TargetedReviewStore(progress_database) as store:
        metadata = store.metadata()
        if metadata["implementation_commit"] != current_repository_commit():
            raise ValueError("targeted-review checkout commit changed")
        if (
            metadata["implementation_fingerprint"]
            != targeted_review_implementation_fingerprint()
        ):
            raise ValueError("targeted-review implementation changed")
        if file_sha256(context_path) != metadata["context_sha256"]:
            raise ValueError("targeted-review protected context changed")
        context = TargetedContext.open(context_path, metadata["experiment_iteration"])

        def line_application() -> None:
            while assignment := store.current_assignment():
                hashed = str(assignment["hashed_review_id"])
                print(
                    render_targeted_case(context.case(hashed, metadata["reviewer_id"]))
                )
                print(json.dumps(store.summary(), sort_keys=True))
                command = (
                    input("[s] label/save  [x] label/save+quit  [q] quit: ")
                    .strip()
                    .lower()
                )
                if command == "q":
                    return
                if command not in {"s", "x"}:
                    continue
                try:
                    labels, reasons, note = collect_targeted_labels()
                    store.save_completed(hashed, labels, reasons, protected_note=note)
                except ValueError as error:
                    print(f"VALIDATION_ERROR: {error}")
                    continue
                if command == "x":
                    return

        if line_mode:
            line_application()
            return
        try:
            import curses
        except ImportError:
            line_application()
            return

        try:

            def application(screen: Any) -> None:
                while assignment := store.current_assignment():
                    hashed = str(assignment["hashed_review_id"])
                    rendered = render_targeted_case(
                        context.case(hashed, metadata["reviewer_id"])
                    ).splitlines()
                    offset = 0
                    while True:
                        height, width = screen.getmaxyx()
                        screen.erase()
                        for row, line in enumerate(
                            rendered[offset : offset + max(1, height - 2)]
                        ):
                            screen.addnstr(row, 0, line, max(1, width - 1))
                        screen.addnstr(
                            height - 1, 0, "j/k=scroll s=label q=quit", width - 1
                        )
                        screen.refresh()
                        key = screen.get_wch()
                        if key == "q":
                            return
                        if key == "j":
                            offset = min(max(0, len(rendered) - 1), offset + 1)
                        elif key == "k":
                            offset = max(0, offset - 1)
                        elif key == "s":
                            curses.endwin()
                            try:
                                labels, reasons, note = collect_targeted_labels()
                                store.save_completed(
                                    hashed, labels, reasons, protected_note=note
                                )
                            except ValueError as error:
                                print(f"VALIDATION_ERROR: {error}")
                                input("Press Enter to return: ")
                            break

            curses.wrapper(application)
        except (OSError, curses.error):
            line_application()


def _unblind_comparison(label: str, *, experimental_is_a: bool) -> str:
    if label in {"BOTH_CORRECT", "BOTH_INCORRECT", "CANNOT_ASSESS"}:
        return label
    a_is_correct = label == "PARSE_A_CORRECT_ONLY"
    experimental_correct = a_is_correct == experimental_is_a
    return (
        "V2_INCORRECT_V3_CORRECT" if experimental_correct else "V2_CORRECT_V3_INCORRECT"
    )


def score_completed_targeted_review(
    *,
    reviewer_one_database: Path,
    reviewer_two_database: Path,
    context_path: Path,
    output_path: Path,
) -> dict[str, JsonValue]:
    for path in (
        reviewer_one_database,
        reviewer_two_database,
        context_path,
        output_path,
    ):
        _reject_locked_path(path)
    if output_path.exists():
        raise FileExistsError("targeted-review score output exists")
    with (
        TargetedReviewStore(reviewer_one_database, readonly=True) as first,
        TargetedReviewStore(reviewer_two_database, readonly=True) as second,
    ):
        first_binding = {
            k: v
            for k, v in first.metadata().items()
            if k not in {"reviewer_id", "assignment_role"}
        }
        second_binding = {
            k: v
            for k, v in second.metadata().items()
            if k not in {"reviewer_id", "assignment_role"}
        }
        if first_binding != second_binding:
            raise ValueError("targeted reviewer stores have different bindings")
        first_rows = first.completed_rows()
        second_rows = second.completed_rows()
        metadata = first.metadata()
    if (
        file_sha256(context_path) != metadata["context_sha256"]
        or context_path.stat().st_size != int(metadata["context_size_bytes"])
    ):
        raise ValueError("targeted-review protected context identity changed")
    if {row["hashed_review_id"] for row in first_rows} != {
        row["hashed_review_id"] for row in second_rows
    }:
        raise ValueError("targeted reviewers have different identity sets")
    context = TargetedContext.open(context_path, metadata["experiment_iteration"])
    by_reviewer = dict(zip(REVIEWER_IDS, (first_rows, second_rows), strict=True))
    per_reviewer: dict[str, JsonValue] = {}
    label_by_key = {
        (str(row["hashed_review_id"]), str(row["reviewer_id"])): row
        for row in first_rows + second_rows
    }
    for reviewer, rows in by_reviewer.items():
        selected: Counter[str] = Counter()
        rejected: Counter[str] = Counter()
        comparison: Counter[str] = Counter()
        component_correct = 0
        component_assessed = 0
        joint_correct = 0
        joint_assessed = 0
        for row in rows:
            hashed = str(row["hashed_review_id"])
            index = context.by_hashed_id[hashed]
            identity = bytes(context.table["stable_source_row_id_v1"][index].as_py())
            case_metadata = json.loads(
                str(context.table["targeted_case_metadata_json"][index].as_py())
            )
            is_selected = bool(case_metadata["experimental_selected"])
            if is_selected:
                street = str(row["street_label"])
                house = str(row["house_number_label"])
                joint = str(row["joint_street_house_label"])
                selected["street_exact_correct"] += street == "CORRECT"
                selected["house_number_exact_correct"] += house == "CORRECT"
                selected["joint_street_house_exact_correct"] += joint == "CORRECT"
                selected["incorrect"] += (
                    street == "INCORRECT"
                    or house == "INCORRECT"
                    or joint == "INCORRECT"
                    or row["candidate_support_label"] == "NOT_SUPPORTED"
                )
                selected["uncertain"] += (
                    street == "CANNOT_ASSESS"
                    or house == "CANNOT_ASSESS"
                    or joint == "CANNOT_ASSESS"
                    or row["candidate_support_label"] == "CANNOT_ASSESS"
                )
                for value in (street, house):
                    if value in {"CORRECT", "INCORRECT"}:
                        component_assessed += 1
                        component_correct += value == "CORRECT"
                if joint in {"CORRECT", "INCORRECT"}:
                    joint_assessed += 1
                    joint_correct += joint == "CORRECT"
            elif bool(case_metadata["experimental_evidence_present"]):
                support = str(row["candidate_support_label"])
                rejected["correctly_rejected"] += support == "NOT_SUPPORTED"
                rejected["would_have_been_correct_if_promoted"] += (
                    support == "SUPPORTED"
                )
                rejected["ambiguous_uncertain"] += support == "CANNOT_ASSESS"
            unblinded = _unblind_comparison(
                str(row["blind_parse_comparison_label"]),
                experimental_is_a=_experimental_is_parse_a(identity, reviewer),
            )
            comparison[unblinded] += 1
        per_reviewer[reviewer] = {
            "selected_experimental_rows": dict(sorted(selected.items())),
            "rejected_candidate_rows": dict(sorted(rejected.items())),
            "parser_comparison": {
                key: comparison[key]
                for key in (
                    "BOTH_CORRECT",
                    "V2_INCORRECT_V3_CORRECT",
                    "V2_CORRECT_V3_INCORRECT",
                    "BOTH_INCORRECT",
                    "CANNOT_ASSESS",
                )
            },
            "new_selection_precision": {
                "numerator": component_correct,
                "denominator": component_assessed,
            },
            "joint_street_house_precision": {
                "numerator": joint_correct,
                "denominator": joint_assessed,
            },
            "false_positive_count": selected["incorrect"],
            "false_negative_opportunity_count": rejected[
                "would_have_been_correct_if_promoted"
            ],
        }
    agreement_fields = TARGETED_LABEL_FIELDS + ("reason_codes",)
    agreement_count = 0
    total_comparisons = 0
    disagreement_identities = 0
    for hashed in sorted(context.by_hashed_id):
        first_label = label_by_key[(hashed, REVIEWER_IDS[0])]
        second_label = label_by_key[(hashed, REVIEWER_IDS[1])]
        row_agrees = True
        for field in agreement_fields:
            total_comparisons += 1
            if first_label[field] == second_label[field]:
                agreement_count += 1
            else:
                row_agrees = False
        disagreement_identities += not row_agrees
    payload: dict[str, JsonValue] = {
        "report_version": TARGETED_SCORE_VERSION,
        "status": "TARGETED_REVIEW_SCORED_NO_PROMOTION_THRESHOLD_APPLIED",
        "number_reviewed": len(context.by_hashed_id),
        "review_completion": {
            REVIEWER_IDS[0]: len(first_rows),
            REVIEWER_IDS[1]: len(second_rows),
        },
        "reviewer_agreement": {
            "exact_field_agreement_numerator": agreement_count,
            "exact_field_agreement_denominator": total_comparisons,
        },
        "adjudication_needed_count": disagreement_identities,
        "per_reviewer": per_reviewer,
        "scientific_promotion_threshold_applied": False,
        "raw_values_reported": False,
        "identities_reported": False,
        "locked_rows_read": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    _fsync_parent(output_path)
    return payload


def export_completed_targeted_labels(
    *,
    reviewer_one_database: Path,
    reviewer_two_database: Path,
    output_path: Path,
) -> Path:
    for path in (reviewer_one_database, reviewer_two_database, output_path):
        _reject_locked_path(path)
    if output_path.exists():
        raise FileExistsError("targeted label export exists")
    with (
        TargetedReviewStore(reviewer_one_database, readonly=True) as first,
        TargetedReviewStore(reviewer_two_database, readonly=True) as second,
    ):
        first_metadata = first.metadata()
        second_metadata = second.metadata()
        first_binding = {
            key: value
            for key, value in first_metadata.items()
            if key not in {"reviewer_id", "assignment_role"}
        }
        second_binding = {
            key: value
            for key, value in second_metadata.items()
            if key not in {"reviewer_id", "assignment_role"}
        }
        if first_binding != second_binding:
            raise ValueError("targeted reviewer stores have different bindings")
        first_rows = first.completed_rows()
        second_rows = second.completed_rows()
        if {row["hashed_review_id"] for row in first_rows} != {
            row["hashed_review_id"] for row in second_rows
        }:
            raise ValueError("targeted reviewers have different identity sets")
        rows = first_rows + second_rows
    if len({(row["hashed_review_id"], row["reviewer_id"]) for row in rows}) != len(
        rows
    ):
        raise ValueError("targeted portable labels contain duplicate reviewer keys")
    output_path.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    pq.write_table(
        pa.Table.from_pylist(rows, schema=targeted_review_label_schema()),
        temporary,
        compression="zstd",
        compression_level=3,
        write_statistics=False,
        write_page_checksum=True,
    )
    temporary.chmod(0o600)
    verified = pq.ParquetFile(
        temporary, page_checksum_verification=True, pre_buffer=True
    )
    if verified.metadata.num_rows != len(
        rows
    ) or not verified.schema_arrow.remove_metadata().equals(
        targeted_review_label_schema(), check_metadata=False
    ):
        raise ValueError("targeted portable label export validation failed")
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    _fsync_parent(output_path)
    return output_path

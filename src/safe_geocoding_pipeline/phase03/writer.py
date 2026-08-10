from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from .config import Phase03Config
from .errors import Phase03Error
from .schema import (
    core_schema,
    evidence_schema,
    exact_core_schema_matches,
    exact_evidence_schema_matches,
    schema_with_metadata,
)
from .semantic import core_digest, evidence_digest
from .validation import (
    validate_core_evidence_relationship,
    validate_core_rows,
    validate_evidence_rows,
)

CORE_DICTIONARY_COLUMNS = [
    "source_file",
    "country_input_class",
    "country_parse_method",
    "country_parse_confidence",
    "address_parse_status",
    "address_completeness_class",
    "diagnostic_evaluation_status",
    "parser_version",
    "rule_registry_version",
    "cleaning_rules_version",
    "placeholder_policy_version",
    "country_reference_version",
    "unicode_reference_version",
    "diagnostic_vocabulary_version",
    "component_schema_version",
    "phase03_version",
]
EVIDENCE_DICTIONARY_COLUMNS = [
    "source_file",
    "evidence_kind",
    "component",
    "representation",
    "confidence",
    "rule_id",
    "source_field",
    "conflict_flag",
    "diagnostic_flag",
    "parser_version",
    "rule_registry_version",
    "phase03_version",
]


@dataclass(frozen=True, slots=True)
class ShardWriteResult:
    core_rows: int
    evidence_rows: int
    core_semantic_digest: str
    evidence_semantic_digest: str
    core_sha256: str
    evidence_sha256: str
    core_bytes: int
    evidence_bytes: int
    page_checksums_verified: bool
    parquet_metadata: tuple[tuple[str, str], ...]


def _write_table(
    path: Path,
    rows: list[dict[str, Any]],
    schema: pa.Schema,
    dictionaries: list[str],
    config: Phase03Config,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    table = pa.Table.from_pylist(rows, schema=schema)
    try:
        pq.write_table(
            table,
            path,
            version=config.parquet_version,
            data_page_version=config.data_page_version,
            compression=config.compression,
            compression_level=config.compression_level,
            row_group_size=config.batch_rows,
            use_dictionary=dictionaries,
            write_statistics=False,
            write_page_checksum=True,
            store_schema=True,
            use_compliant_nested_type=True,
        )
    except (OSError, pa.ArrowException) as error:
        raise Phase03Error("PARQUET_WRITE_FAILURE", type(error).__name__) from error
    path.chmod(0o600)
    _fsync_file_and_parent(path)


def _fsync_file_and_parent(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_rows(
    path: Path,
    *,
    core: bool,
    required_metadata: dict[str, str],
) -> list[dict[str, Any]]:
    try:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        observed = parquet.schema_arrow
        matches = (
            exact_core_schema_matches(observed)
            if core
            else exact_evidence_schema_matches(observed)
        )
        if not matches:
            raise Phase03Error("PARQUET_SCHEMA_MISMATCH")
        observed_metadata = {
            key.decode(): value.decode()
            for key, value in (observed.metadata or {}).items()
        }
        if observed_metadata != required_metadata:
            raise Phase03Error("PARQUET_METADATA_MISMATCH")
        table = parquet.read(use_threads=False)
        if any(
            parquet.metadata.row_group(i).column(j).statistics is not None
            for i in range(parquet.metadata.num_row_groups)
            for j in range(parquet.metadata.row_group(i).num_columns)
        ):
            raise Phase03Error("SENSITIVE_PARQUET_STATISTICS")
        return cast(list[dict[str, Any]], table.to_pylist())
    except Phase03Error:
        raise
    except (OSError, pa.ArrowException) as error:
        raise Phase03Error(
            "PARQUET_READ_OR_CHECKSUM_FAILURE", type(error).__name__
        ) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _phase03_metadata(
    config: Phase03Config,
    supplied: dict[str, str],
    core_rows: list[dict[str, Any]],
) -> dict[str, str]:
    if not core_rows:
        raise Phase03Error("EMPTY_CORE_SHARD")
    row_keys = (
        "phase03_version",
        "parser_version",
        "rule_registry_version",
        "cleaning_rules_version",
        "placeholder_policy_version",
        "country_reference_version",
        "unicode_reference_version",
        "diagnostic_vocabulary_version",
        "component_schema_version",
    )
    row_values: dict[str, str] = {}
    for key in row_keys:
        values = {str(row[key]) for row in core_rows}
        if len(values) != 1:
            raise Phase03Error("INCONSISTENT_CORE_VERSION_METADATA", key)
        row_values[key] = values.pop()
    configuration_values = {
        bytes(row["configuration_fingerprint"]).hex() for row in core_rows
    }
    if len(configuration_values) != 1:
        raise Phase03Error("INCONSISTENT_CORE_CONFIGURATION_FINGERPRINT")
    implementation_values = {
        bytes(row["implementation_fingerprint"]).hex() for row in core_rows
    }
    if len(implementation_values) != 1:
        raise Phase03Error("INCONSISTENT_CORE_IMPLEMENTATION_FINGERPRINT")
    required = {
        **row_values,
        "evidence_schema_version": config.evidence_schema_version,
        "evidence_sidecar_policy_version": config.evidence_sidecar_policy_version,
        "manual_review_reason_codes_version": (
            config.manual_review_reason_codes_version
        ),
        "manual_review_label_schema_version": (
            config.manual_review_label_schema_version
        ),
        "python_runtime_version": ".".join(map(str, config.expected_python_version)),
        "unicode_runtime_version": config.expected_unicode_version,
        "configuration_fingerprint": configuration_values.pop(),
        "implementation_fingerprint": implementation_values.pop(),
    }
    configured_values = {
        "phase03_version": config.phase03_version,
        "parser_version": config.parser_version,
        "rule_registry_version": config.rule_registry_version,
        "cleaning_rules_version": config.cleaning_rules_version,
        "placeholder_policy_version": config.placeholder_policy_version,
        "diagnostic_vocabulary_version": config.diagnostic_vocabulary_version,
        "component_schema_version": config.component_schema_version,
    }
    if any(required[key] != value for key, value in configured_values.items()):
        raise Phase03Error("CORE_VERSION_CONFIGURATION_CONFLICT")
    conflicting = {
        key
        for key, value in supplied.items()
        if key in required and required[key] != value
    }
    if conflicting:
        raise Phase03Error("PARQUET_METADATA_CONFIGURATION_CONFLICT")
    return {**supplied, **required}


def atomic_promote_pair(
    temporary_core: Path,
    temporary_evidence: Path,
    final_core: Path,
    final_evidence: Path,
) -> None:
    if final_core.exists() or final_evidence.exists():
        raise Phase03Error("FINAL_OUTPUT_EXISTS")
    final_core.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    final_evidence.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.replace(temporary_core, final_core)
    try:
        os.replace(temporary_evidence, final_evidence)
    except OSError as error:
        try:
            os.replace(final_core, temporary_core)
        except OSError as rollback_error:
            raise Phase03Error(
                "ATOMIC_PAIR_ROLLBACK_FAILURE", type(rollback_error).__name__
            ) from error
        raise Phase03Error(
            "ATOMIC_PAIR_PROMOTION_FAILURE", type(error).__name__
        ) from error
    _fsync_file_and_parent(final_core)
    _fsync_file_and_parent(final_evidence)


def write_validate_and_promote_synthetic_shard(
    *,
    core_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    temporary_core: Path,
    temporary_evidence: Path,
    final_core: Path,
    final_evidence: Path,
    config: Phase03Config,
    metadata: dict[str, str],
) -> ShardWriteResult:
    """Write a fictional/authorized in-memory shard; never discovers Phase 2 data."""
    validate_core_rows(core_rows)
    validate_evidence_rows(evidence_rows)
    validate_core_evidence_relationship(core_rows, evidence_rows)
    required_metadata = _phase03_metadata(config, metadata, core_rows)
    core_source_digest = core_digest(core_rows, config.component_schema_version)
    evidence_source_digest = evidence_digest(
        evidence_rows, config.evidence_schema_version
    )
    _write_table(
        temporary_core,
        core_rows,
        schema_with_metadata(core_schema(), required_metadata),
        CORE_DICTIONARY_COLUMNS,
        config,
    )
    _write_table(
        temporary_evidence,
        evidence_rows,
        schema_with_metadata(evidence_schema(), required_metadata),
        EVIDENCE_DICTIONARY_COLUMNS,
        config,
    )
    read_core = _read_rows(
        temporary_core, core=True, required_metadata=required_metadata
    )
    read_evidence = _read_rows(
        temporary_evidence, core=False, required_metadata=required_metadata
    )
    validate_core_rows(read_core)
    validate_evidence_rows(read_evidence)
    validate_core_evidence_relationship(read_core, read_evidence)
    core_read_digest = core_digest(read_core, config.component_schema_version)
    evidence_read_digest = evidence_digest(
        read_evidence, config.evidence_schema_version
    )
    if (
        core_source_digest != core_read_digest
        or evidence_source_digest != evidence_read_digest
    ):
        raise Phase03Error("SEMANTIC_DIGEST_MISMATCH")
    core_hash, evidence_hash = _sha256(temporary_core), _sha256(temporary_evidence)
    core_size, evidence_size = (
        temporary_core.stat().st_size,
        temporary_evidence.stat().st_size,
    )
    atomic_promote_pair(temporary_core, temporary_evidence, final_core, final_evidence)
    return ShardWriteResult(
        core_rows=len(core_rows),
        evidence_rows=len(evidence_rows),
        core_semantic_digest=core_source_digest.hex(),
        evidence_semantic_digest=evidence_source_digest.hex(),
        core_sha256=core_hash,
        evidence_sha256=evidence_hash,
        core_bytes=core_size,
        evidence_bytes=evidence_size,
        page_checksums_verified=True,
        parquet_metadata=tuple(sorted(required_metadata.items())),
    )


def revalidate_completed_pair(
    *,
    core_path: Path,
    evidence_path: Path,
    expected: ShardWriteResult,
    config: Phase03Config,
) -> ShardWriteResult:
    """Revalidate both COMPLETE products before a resume reuses the shard."""
    required_metadata = dict(expected.parquet_metadata)
    core_rows = _read_rows(core_path, core=True, required_metadata=required_metadata)
    evidence_rows = _read_rows(
        evidence_path, core=False, required_metadata=required_metadata
    )
    validate_core_rows(core_rows)
    validate_evidence_rows(evidence_rows)
    validate_core_evidence_relationship(core_rows, evidence_rows)
    observed = ShardWriteResult(
        core_rows=len(core_rows),
        evidence_rows=len(evidence_rows),
        core_semantic_digest=core_digest(
            core_rows, config.component_schema_version
        ).hex(),
        evidence_semantic_digest=evidence_digest(
            evidence_rows, config.evidence_schema_version
        ).hex(),
        core_sha256=_sha256(core_path),
        evidence_sha256=_sha256(evidence_path),
        core_bytes=core_path.stat().st_size,
        evidence_bytes=evidence_path.stat().st_size,
        page_checksums_verified=True,
        parquet_metadata=tuple(sorted(required_metadata.items())),
    )
    if observed != expected:
        raise Phase03Error("COMPLETE_SHARD_REVALIDATION_MISMATCH")
    return observed

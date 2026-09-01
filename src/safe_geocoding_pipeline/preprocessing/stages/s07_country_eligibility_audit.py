"""Metadata-only Stage 7 parser country-eligibility audit.

The protected part of this diagnostic reads candidate IDs, occurrence lineage,
trusted upstream country codes, existing parse statuses, and the immutable
120-case review classifications.  It never reads candidate text or parser
component values and makes no parser calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from .s06_exact_deduplication import REGISTRY_COLUMNS, ROW_MAP_ID_COLUMNS
from .s07_context_provenance import (
    EXPECTED_CLASSIFICATION_COUNTS,
    EXPECTED_SELECTION_ROWS,
    SELECTION_FINGERPRINT,
    _validate_review_inputs,
    _validate_stage06_identity,
)
from .s07_country_eligibility import (
    COUNTRY_CONFLICTING,
    COUNTRY_CONTEXT_UNRESOLVED,
    COUNTRY_INVALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_UNANIMOUS_VALID,
    DEEPPARSE,
    ELIGIBLE_BOTH,
    ELIGIBLE_DEEPPARSE_ONLY,
    ELIGIBLE_LIBPOSTAL_ONLY,
    ELIGIBLE_NEITHER,
    JOINT_ELIGIBILITY_STATUSES,
    LIBPOSTAL,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBILITY_STATUSES,
    PARSER_ELIGIBLE_COUNTRY,
    PARSER_NOT_APPLICABLE_COUNTRY,
    TRUSTED_COUNTRY_FIELD,
    load_eligibility_manifest,
)
from .s07_parsing import (
    ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
    ACCEPTED_STAGE06_MANIFEST_SHA256,
    ACCEPTED_STAGE06_OCCURRENCES,
    ACCEPTED_STAGE06_REGISTRY_ROWS,
    ACCEPTED_STAGE06_STANDARD_OCCURRENCES,
    ACCEPTED_STAGE06_NATIVE_OCCURRENCES,
    STAGE07_CONTRACT_VERSION,
    STAGE07_MANIFEST_NAME,
    STAGE07_MANIFEST_VERSION,
    STAGE07_PROFILE_VERSION,
    STAGE07_STATUS_VOCABULARY,
    _manifest_artifacts as _stage07_manifest_artifacts,
)


AUDIT_VERSION = "stage07_country_eligibility_audit_v1"
AUDIT_MANIFEST_NAME = "stage07_country_eligibility_manifest.json"
AUDIT_SUCCESS_NAME = "_SUCCESS.json"
EXPECTED_STAGE07_ROWS = 51_779
EXPECTED_STAGE07_OCCURRENCES = 69_747
EXPECTED_SOURCE_ROWS = 35_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Stage07CountryEligibilityAuditError(RuntimeError):
    """Privacy-safe metadata audit failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07CountryEligibilityAuditError(code, detail)


@dataclass(frozen=True, slots=True)
class CountryEligibilityAuditConfig:
    stage06_output_directory: Path
    stage07_output_directory: Path
    selection_path: Path
    classifications_path: Path
    eligibility_manifest_path: Path
    output_directory: Path
    execution_git_sha: str
    expected_stage06_manifest_sha256: str = ACCEPTED_STAGE06_MANIFEST_SHA256
    expected_stage07_manifest_sha256: str = ""
    expected_selection_fingerprint: str = SELECTION_FINGERPRINT
    expected_source_rows: int = EXPECTED_SOURCE_ROWS
    expected_registry_rows: int = ACCEPTED_STAGE06_REGISTRY_ROWS
    expected_occurrences: int = ACCEPTED_STAGE06_OCCURRENCES
    expected_standard_occurrences: int = ACCEPTED_STAGE06_STANDARD_OCCURRENCES
    expected_native_occurrences: int = ACCEPTED_STAGE06_NATIVE_OCCURRENCES
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    authoritative_development: bool = True

    @property
    def production(self) -> bool:
        """Compatibility name for reused fail-closed Stage 6/review validators."""
        return self.authoritative_development

    def validate(self) -> None:
        for fingerprint in (
            self.expected_stage06_manifest_sha256,
            self.expected_stage07_manifest_sha256,
            self.expected_selection_fingerprint,
        ):
            if _SHA256_RE.fullmatch(fingerprint) is None:
                _fail("INVALID_FINGERPRINT", "A configured fingerprint is malformed")
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_SHA", "Execution Git SHA is malformed")
        for count in (
            self.expected_source_rows,
            self.expected_registry_rows,
            self.expected_occurrences,
            self.expected_standard_occurrences,
            self.expected_native_occurrences,
            self.duckdb_threads,
        ):
            if isinstance(count, bool) or count < 1:
                _fail("INVALID_EXPECTATION", "A bounded count is invalid")
        if re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", self.duckdb_memory_limit) is None:
            _fail("INVALID_MEMORY_LIMIT", "DuckDB memory limit is malformed")
        paths = (
            self.stage06_output_directory,
            self.stage07_output_directory,
            self.selection_path,
            self.classifications_path,
            self.eligibility_manifest_path,
            self.output_directory,
        )
        if any(
            "holdout" in part.casefold()
            for path in paths
            for part in path.resolve(strict=False).parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")
        if self.authoritative_development and (
            self.expected_stage06_manifest_sha256 != ACCEPTED_STAGE06_MANIFEST_SHA256
            or self.expected_selection_fingerprint != SELECTION_FINGERPRINT
            or self.expected_source_rows != EXPECTED_SOURCE_ROWS
            or self.expected_registry_rows != ACCEPTED_STAGE06_REGISTRY_ROWS
            or self.expected_occurrences != ACCEPTED_STAGE06_OCCURRENCES
            or self.expected_standard_occurrences
            != ACCEPTED_STAGE06_STANDARD_OCCURRENCES
            or self.expected_native_occurrences != ACCEPTED_STAGE06_NATIVE_OCCURRENCES
        ):
            _fail("ACCEPTED_BINDING_MISMATCH", "DEVELOPMENT binding differs")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07CountryEligibilityAuditError(
            "ARTIFACT_READ_FAILURE", "A bound artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07CountryEligibilityAuditError(
            "JSON_INVALID", "A bound JSON artifact could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("JSON_INVALID", "A bound JSON artifact is not an object")
    return value


def _require_mode(path: Path, mode: int) -> None:
    if path.is_symlink() or not path.exists():
        _fail("ARTIFACT_TOPOLOGY_INVALID", "An artifact is absent or a symlink")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        _fail("PERMISSION_FAILURE", "An owner-only mode differs")


def _write_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validate_stage07_identity(
    config: CountryEligibilityAuditConfig,
) -> tuple[tuple[Path, ...], dict[str, object]]:
    root = config.stage07_output_directory
    _require_mode(root, 0o700)
    manifest_path = root / STAGE07_MANIFEST_NAME
    _require_mode(manifest_path, 0o600)
    if _sha256_file(manifest_path) != config.expected_stage07_manifest_sha256:
        _fail("STAGE07_MANIFEST_SHA256_MISMATCH", "Stage 7 manifest differs")
    manifest = _load_json(manifest_path)
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if (
        manifest.get("stage07_manifest_version") != STAGE07_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_7_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or not isinstance(scientific, dict)
        or not isinstance(physical, dict)
        or scientific.get("stage07_contract_version") != STAGE07_CONTRACT_VERSION
        or scientific.get("stage07_profile_version") != STAGE07_PROFILE_VERSION
        or scientific.get("candidate_count") != config.expected_registry_rows
        or scientific.get("status_vocabulary") != list(STAGE07_STATUS_VOCABULARY)
    ):
        _fail("STAGE07_BINDING_MISMATCH", "Stage 7 scientific identity differs")
    stage06_binding = scientific.get("stage06_binding")
    if (
        not isinstance(stage06_binding, dict)
        or stage06_binding.get("stage06_manifest_sha256")
        != config.expected_stage06_manifest_sha256
        or stage06_binding.get("stage06_registry_rows") != config.expected_registry_rows
        or stage06_binding.get("stage06_occurrences") != config.expected_occurrences
        or stage06_binding.get("parser_bundle_fingerprint")
        != ACCEPTED_PARSER_BUNDLE_FINGERPRINT
    ):
        _fail("STAGE07_BINDING_MISMATCH", "Stage 7 upstream binding differs")
    artifacts = _stage07_manifest_artifacts(root, physical)
    if sum(item.row_count for item in artifacts) != config.expected_registry_rows:
        _fail("STAGE07_ROW_COUNT_MISMATCH", "Stage 7 artifact rows differ")
    paths = tuple(root / item.relative_path for item in artifacts)
    return paths, {
        "contract": scientific["stage07_contract_version"],
        "profile": scientific["stage07_profile_version"],
        "manifest_sha256": config.expected_stage07_manifest_sha256,
        "candidate_rows": config.expected_registry_rows,
        "artifact_count": len(paths),
        "parser_bundle_fingerprint": ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
    }


def _query_int(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None or isinstance(row[0], bool):
        _fail("AUDIT_QUERY_FAILURE", "An aggregate count is absent")
    return int(row[0])


def _count_by(
    connection: duckdb.DuckDBPyConnection, relation: str, column: str
) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT {column}, count(*) FROM {relation} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    result: dict[str, int] = {}
    for key, count in rows:
        if not isinstance(key, str) or isinstance(count, bool):
            _fail("AUDIT_QUERY_FAILURE", "A category count is malformed")
        result[key] = int(count)
    return result


def _nested_counts(
    connection: duckdb.DuckDBPyConnection,
    relation: str,
    first: str,
    second: str,
) -> dict[str, dict[str, int]]:
    rows = connection.execute(
        f"SELECT {first}, {second}, count(*) FROM {relation} "
        "GROUP BY 1, 2 ORDER BY 1, 2"
    ).fetchall()
    result: dict[str, dict[str, int]] = {}
    for first_value, second_value, count in rows:
        if not isinstance(first_value, str) or not isinstance(second_value, str):
            _fail("AUDIT_QUERY_FAILURE", "A cross-tab category is malformed")
        result.setdefault(first_value, {})[second_value] = int(count)
    return result


def _build_relations(
    connection: duckdb.DuckDBPyConnection,
    *,
    row_paths: tuple[Path, ...],
    registry_paths: tuple[Path, ...],
    stage07_paths: tuple[Path, ...],
    selection: pa.Table,
    classifications: pa.Table,
    valid_country_codes: frozenset[str],
    deepparse_trained_country_codes: frozenset[str],
) -> None:
    connection.register("selection_arrow", selection)
    connection.register("classifications_arrow", classifications)
    connection.register(
        "valid_country_codes_arrow",
        pa.table({"country_code": sorted(valid_country_codes)}),
    )
    connection.register(
        "deepparse_trained_codes_arrow",
        pa.table({"country_code": sorted(deepparse_trained_country_codes)}),
    )
    connection.read_parquet([str(path) for path in row_paths]).create_view(
        "stage06_row_map"
    )
    connection.read_parquet([str(path) for path in registry_paths]).create_view(
        "stage06_registry"
    )
    connection.read_parquet([str(path) for path in stage07_paths]).create_view(
        "stage07_registry"
    )
    connection.execute(
        f"""
        CREATE TEMP VIEW stage06_occurrences AS
        SELECT
            stable_source_row_id_v1 AS source_identity,
            {ROW_MAP_ID_COLUMNS[0]} AS candidate_id,
            'STANDARD'::VARCHAR AS representation,
            {TRUSTED_COUNTRY_FIELD} AS country_context
        FROM stage06_row_map
        WHERE {ROW_MAP_ID_COLUMNS[0]} IS NOT NULL
        UNION ALL
        SELECT
            stable_source_row_id_v1 AS source_identity,
            {ROW_MAP_ID_COLUMNS[1]} AS candidate_id,
            'NATIVE'::VARCHAR AS representation,
            {TRUSTED_COUNTRY_FIELD} AS country_context
        FROM stage06_row_map
        WHERE {ROW_MAP_ID_COLUMNS[1]} IS NOT NULL
        """
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE candidate_country_audit AS
        WITH marked AS (
            SELECT
                o.*,
                o.country_context IS NULL OR o.country_context = '' AS is_missing,
                v.country_code IS NOT NULL AS is_valid
            FROM stage06_occurrences o
            LEFT JOIN valid_country_codes_arrow v
              ON o.country_context = v.country_code
        ), aggregated AS (
            SELECT
                candidate_id,
                count(*)::UBIGINT AS observed_occurrence_count,
                count(*) FILTER (WHERE representation='STANDARD')::UBIGINT
                    AS observed_standard_occurrence_count,
                count(*) FILTER (WHERE representation='NATIVE')::UBIGINT
                    AS observed_native_occurrence_count,
                count(*) FILTER (WHERE is_valid)::UBIGINT
                    AS valid_country_occurrence_count,
                count(*) FILTER (WHERE is_missing)::UBIGINT
                    AS missing_country_occurrence_count,
                count(*) FILTER (WHERE NOT is_missing AND NOT is_valid)::UBIGINT
                    AS invalid_country_occurrence_count,
                count(DISTINCT country_context) FILTER (WHERE is_valid)::UINTEGER
                    AS distinct_valid_country_count,
                min(country_context) FILTER (WHERE is_valid)::VARCHAR
                    AS sole_valid_country
            FROM marked
            GROUP BY candidate_id
        ), classified AS (
            SELECT
                r.{REGISTRY_COLUMNS[0]} AS candidate_id,
                r.{REGISTRY_COLUMNS[2]} AS occurrence_count,
                r.{REGISTRY_COLUMNS[3]} AS standard_occurrence_count,
                r.{REGISTRY_COLUMNS[4]} AS native_occurrence_count,
                a.valid_country_occurrence_count,
                a.missing_country_occurrence_count,
                a.invalid_country_occurrence_count,
                a.distinct_valid_country_count,
                CASE
                    WHEN a.distinct_valid_country_count >= 2
                        THEN '{COUNTRY_CONFLICTING}'
                    WHEN a.distinct_valid_country_count = 1
                      AND a.valid_country_occurrence_count = a.observed_occurrence_count
                        THEN '{COUNTRY_UNANIMOUS_VALID}'
                    WHEN a.distinct_valid_country_count = 1
                        THEN '{COUNTRY_PARTIAL}'
                    WHEN a.invalid_country_occurrence_count > 0
                        THEN '{COUNTRY_INVALID}'
                    ELSE '{COUNTRY_MISSING}'
                END::VARCHAR AS country_provenance_status,
                CASE
                    WHEN a.distinct_valid_country_count = 1
                      AND a.valid_country_occurrence_count = a.observed_occurrence_count
                    THEN a.sole_valid_country
                    ELSE NULL
                END::VARCHAR AS unanimous_country_code
            FROM stage06_registry r
            JOIN aggregated a ON a.candidate_id = r.{REGISTRY_COLUMNS[0]}
            WHERE r.{REGISTRY_COLUMNS[2]} = a.observed_occurrence_count
              AND r.{REGISTRY_COLUMNS[3]} = a.observed_standard_occurrence_count
              AND r.{REGISTRY_COLUMNS[4]} = a.observed_native_occurrence_count
        )
        SELECT
            c.*,
            CASE c.country_provenance_status
                WHEN '{COUNTRY_UNANIMOUS_VALID}' THEN '{PARSER_ELIGIBLE_COUNTRY}'
                WHEN '{COUNTRY_MISSING}' THEN '{PARSER_ELIGIBILITY_MISSING_COUNTRY}'
                WHEN '{COUNTRY_PARTIAL}' THEN '{PARSER_ELIGIBILITY_PARTIAL_COUNTRY}'
                WHEN '{COUNTRY_INVALID}' THEN '{PARSER_ELIGIBILITY_INVALID_COUNTRY}'
                ELSE '{PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY}'
            END::VARCHAR AS libpostal_eligibility,
            CASE
                WHEN c.country_provenance_status = '{COUNTRY_UNANIMOUS_VALID}'
                  AND d.country_code IS NOT NULL THEN '{PARSER_ELIGIBLE_COUNTRY}'
                WHEN c.country_provenance_status = '{COUNTRY_UNANIMOUS_VALID}'
                    THEN '{PARSER_NOT_APPLICABLE_COUNTRY}'
                WHEN c.country_provenance_status = '{COUNTRY_MISSING}'
                    THEN '{PARSER_ELIGIBILITY_MISSING_COUNTRY}'
                WHEN c.country_provenance_status = '{COUNTRY_PARTIAL}'
                    THEN '{PARSER_ELIGIBILITY_PARTIAL_COUNTRY}'
                WHEN c.country_provenance_status = '{COUNTRY_INVALID}'
                    THEN '{PARSER_ELIGIBILITY_INVALID_COUNTRY}'
                ELSE '{PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY}'
            END::VARCHAR AS deepparse_eligibility
        FROM classified c
        LEFT JOIN deepparse_trained_codes_arrow d
          ON c.unanimous_country_code = d.country_code
        ORDER BY c.candidate_id
        """
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE candidate_eligibility_audit AS
        SELECT
            c.*,
            s.stage07_parse_status,
            CASE
                WHEN c.libpostal_eligibility NOT IN (
                    '{PARSER_ELIGIBLE_COUNTRY}', '{PARSER_NOT_APPLICABLE_COUNTRY}'
                ) OR c.deepparse_eligibility NOT IN (
                    '{PARSER_ELIGIBLE_COUNTRY}', '{PARSER_NOT_APPLICABLE_COUNTRY}'
                ) THEN '{COUNTRY_CONTEXT_UNRESOLVED}'
                WHEN c.libpostal_eligibility = '{PARSER_ELIGIBLE_COUNTRY}'
                  AND c.deepparse_eligibility = '{PARSER_ELIGIBLE_COUNTRY}'
                    THEN '{ELIGIBLE_BOTH}'
                WHEN c.libpostal_eligibility = '{PARSER_ELIGIBLE_COUNTRY}'
                    THEN '{ELIGIBLE_LIBPOSTAL_ONLY}'
                WHEN c.deepparse_eligibility = '{PARSER_ELIGIBLE_COUNTRY}'
                    THEN '{ELIGIBLE_DEEPPARSE_ONLY}'
                ELSE '{ELIGIBLE_NEITHER}'
            END::VARCHAR AS joint_eligibility
        FROM candidate_country_audit c
        LEFT JOIN stage07_registry s
          ON s.{REGISTRY_COLUMNS[0]} = c.candidate_id
        ORDER BY c.candidate_id
        """
    )
    connection.execute(
        """
        CREATE TEMP VIEW occurrence_eligibility_audit AS
        SELECT
            o.source_identity,
            o.candidate_id,
            o.representation,
            c.country_provenance_status,
            c.libpostal_eligibility,
            c.deepparse_eligibility,
            c.joint_eligibility
        FROM stage06_occurrences o
        JOIN candidate_eligibility_audit c USING (candidate_id)
        """
    )
    connection.execute(
        f"""
        CREATE TEMP TABLE source_row_eligibility_audit AS
        WITH summarized AS (
            SELECT
                source_identity,
                bool_or(libpostal_eligibility = '{PARSER_ELIGIBLE_COUNTRY}')
                    AS libpostal_any_eligible,
                bool_or(deepparse_eligibility = '{PARSER_ELIGIBLE_COUNTRY}')
                    AS deepparse_any_eligible,
                bool_or(libpostal_eligibility NOT IN (
                    '{PARSER_ELIGIBLE_COUNTRY}', '{PARSER_NOT_APPLICABLE_COUNTRY}'
                )) AS libpostal_any_unresolved,
                bool_or(deepparse_eligibility NOT IN (
                    '{PARSER_ELIGIBLE_COUNTRY}', '{PARSER_NOT_APPLICABLE_COUNTRY}'
                )) AS deepparse_any_unresolved
            FROM occurrence_eligibility_audit
            GROUP BY source_identity
        )
        SELECT
            *,
            CASE
                WHEN libpostal_any_eligible THEN 'ROW_AT_LEAST_ONE_ELIGIBLE'
                WHEN libpostal_any_unresolved
                    THEN 'ROW_COUNTRY_CONTEXT_UNRESOLVED_NO_ELIGIBLE'
                ELSE 'ROW_NO_REPRESENTATION_ELIGIBLE'
            END::VARCHAR AS libpostal_row_eligibility,
            CASE
                WHEN deepparse_any_eligible THEN 'ROW_AT_LEAST_ONE_ELIGIBLE'
                WHEN deepparse_any_unresolved
                    THEN 'ROW_COUNTRY_CONTEXT_UNRESOLVED_NO_ELIGIBLE'
                ELSE 'ROW_NO_REPRESENTATION_ELIGIBLE'
            END::VARCHAR AS deepparse_row_eligibility
        FROM summarized
        ORDER BY source_identity
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE selection_eligibility_audit AS
        SELECT
            s.review_order,
            s.stage06_exact_candidate_id AS candidate_id,
            s.input_codepoints,
            q.classification,
            c.country_provenance_status,
            c.libpostal_eligibility,
            c.deepparse_eligibility,
            c.joint_eligibility,
            c.stage07_parse_status
        FROM selection_arrow s
        JOIN classifications_arrow q USING (review_order)
        JOIN candidate_eligibility_audit c
          ON c.candidate_id = s.stage06_exact_candidate_id
        ORDER BY s.review_order
        """
    )


def _validate_reconciliation(
    connection: duckdb.DuckDBPyConnection, config: CountryEligibilityAuditConfig
) -> None:
    expected = {
        "source_rows": config.expected_source_rows,
        "occurrences": config.expected_occurrences,
        "standard": config.expected_standard_occurrences,
        "native": config.expected_native_occurrences,
        "candidates": config.expected_registry_rows,
        "selection": EXPECTED_SELECTION_ROWS,
    }
    observed = {
        "source_rows": _query_int(
            connection, "SELECT count(*) FROM source_row_eligibility_audit"
        ),
        "occurrences": _query_int(
            connection, "SELECT count(*) FROM occurrence_eligibility_audit"
        ),
        "standard": _query_int(
            connection,
            "SELECT count(*) FROM occurrence_eligibility_audit "
            "WHERE representation='STANDARD'",
        ),
        "native": _query_int(
            connection,
            "SELECT count(*) FROM occurrence_eligibility_audit "
            "WHERE representation='NATIVE'",
        ),
        "candidates": _query_int(
            connection, "SELECT count(*) FROM candidate_eligibility_audit"
        ),
        "selection": _query_int(
            connection, "SELECT count(*) FROM selection_eligibility_audit"
        ),
    }
    if observed != expected:
        _fail("AUDIT_RECONCILIATION_FAILURE", "Population totals differ")
    if _query_int(
        connection,
        "SELECT count(*) - count(DISTINCT candidate_id) "
        "FROM candidate_eligibility_audit",
    ):
        _fail("AUDIT_RECONCILIATION_FAILURE", "Candidate IDs are duplicated")
    if _query_int(
        connection,
        "SELECT count(*) FROM candidate_eligibility_audit "
        "WHERE stage07_parse_status IS NULL",
    ):
        _fail("AUDIT_RECONCILIATION_FAILURE", "A Stage 7 status is absent")
    if set(
        _count_by(connection, "candidate_eligibility_audit", "libpostal_eligibility")
    ) - set(PARSER_ELIGIBILITY_STATUSES) or set(
        _count_by(connection, "candidate_eligibility_audit", "deepparse_eligibility")
    ) - set(PARSER_ELIGIBILITY_STATUSES):
        _fail("AUDIT_RECONCILIATION_FAILURE", "Parser status vocabulary differs")
    if set(
        _count_by(connection, "candidate_eligibility_audit", "joint_eligibility")
    ) - set(JOINT_ELIGIBILITY_STATUSES):
        _fail("AUDIT_RECONCILIATION_FAILURE", "Joint status vocabulary differs")


def _parser_metrics(
    connection: duckdb.DuckDBPyConnection, *, parser: str
) -> dict[str, object]:
    column = "libpostal_eligibility" if parser == LIBPOSTAL else "deepparse_eligibility"
    candidate_counts = _count_by(connection, "candidate_eligibility_audit", column)
    occurrence_counts = _count_by(connection, "occurrence_eligibility_audit", column)
    row_counts = _count_by(
        connection,
        "source_row_eligibility_audit",
        "libpostal_row_eligibility"
        if parser == LIBPOSTAL
        else "deepparse_row_eligibility",
    )
    eligible = candidate_counts.get(PARSER_ELIGIBLE_COUNTRY, 0)
    reviewed_eligible = _query_int(
        connection,
        f"SELECT count(*) FROM selection_eligibility_audit "
        f"WHERE {column}='{PARSER_ELIGIBLE_COUNTRY}'",
    )
    classification_counts = _nested_counts(
        connection,
        f"(SELECT '{parser}'::VARCHAR AS parser, classification "
        f"FROM selection_eligibility_audit WHERE {column}="
        f"'{PARSER_ELIGIBLE_COUNTRY}')",
        "parser",
        "classification",
    ).get(parser, {})
    result: dict[str, object] = {
        "source_row_counts": row_counts,
        "occurrence_counts": occurrence_counts,
        "candidate_counts": candidate_counts,
        "all_candidates": EXPECTED_STAGE07_ROWS,
        "eligible_candidates": eligible,
        "coverage_rate": eligible / EXPECTED_STAGE07_ROWS,
        "future_attempted_parser_calls": eligible,
        "future_skipped_parser_calls": EXPECTED_STAGE07_ROWS - eligible,
        "reviewed_eligible_candidates": reviewed_eligible,
        "reviewed_eligible_classification_counts": classification_counts,
        "reviewed_eligible_maximum_input_codepoints": _query_int(
            connection,
            f"SELECT coalesce(max(input_codepoints), 0)::BIGINT "
            f"FROM selection_eligibility_audit "
            f"WHERE {column}='{PARSER_ELIGIBLE_COUNTRY}'",
        ),
        "reviewed_eligible_giant_candidates": _query_int(
            connection,
            f"SELECT count(*) FROM selection_eligibility_audit "
            f"WHERE {column}='{PARSER_ELIGIBLE_COUNTRY}' "
            "AND input_codepoints >= 1000000",
        ),
        "usable_parse_definition": "PLAUSIBLE_PARSE_PLUS_PARTIAL_BUT_USABLE_PARSE",
        "reviewed_eligible_usable_count": classification_counts.get(
            "PLAUSIBLE_PARSE", 0
        )
        + classification_counts.get("PARTIAL_BUT_USABLE_PARSE", 0),
    }
    if reviewed_eligible:
        result["reviewed_eligible_usable_rate"] = (
            cast(int, result["reviewed_eligible_usable_count"]) / reviewed_eligible
        )
    if parser == LIBPOSTAL:
        technical = _count_by(
            connection,
            f"(SELECT stage07_parse_status FROM candidate_eligibility_audit "
            f"WHERE {column}='{PARSER_ELIGIBLE_COUNTRY}')",
            "stage07_parse_status",
        )
        result.update(
            {
                "existing_authoritative_calls": EXPECTED_STAGE07_ROWS,
                "eligibility_matched_technical_status_counts": technical,
                "eligibility_matched_technical_rate_denominator": eligible,
                "technical_failures": 0,
            }
        )
    else:
        result.update(
            {
                "technical_status_counts": "NOT_YET_RUN",
                "semantic_quality": "NOT_YET_REVIEWED",
            }
        )
    return result


def _aggregate(
    connection: duckdb.DuckDBPyConnection,
    *,
    config: CountryEligibilityAuditConfig,
    eligibility_manifest_sha256: str,
    stage06: dict[str, object],
    stage07: dict[str, object],
    classification_counts: dict[str, int],
) -> dict[str, object]:
    country_counts = _count_by(
        connection, "candidate_eligibility_audit", "country_provenance_status"
    )
    libpostal = _parser_metrics(connection, parser=LIBPOSTAL)
    deepparse = _parser_metrics(connection, parser=DEEPPARSE)
    joint_candidates = _count_by(
        connection, "candidate_eligibility_audit", "joint_eligibility"
    )
    joint_occurrences = _count_by(
        connection, "occurrence_eligibility_audit", "joint_eligibility"
    )
    selection_by_parser = {
        LIBPOSTAL: _nested_counts(
            connection,
            "selection_eligibility_audit",
            "libpostal_eligibility",
            "classification",
        ),
        DEEPPARSE: _nested_counts(
            connection,
            "selection_eligibility_audit",
            "deepparse_eligibility",
            "classification",
        ),
    }
    return {
        "audit_version": AUDIT_VERSION,
        "scope": "NON_AUTHORITATIVE_METADATA_ONLY_NO_CANDIDATE_TEXT_NO_PARSER_CALLS",
        "eligibility_manifest_sha256": eligibility_manifest_sha256,
        "stage06_binding": stage06,
        "stage07_binding": stage07,
        "selection_fingerprint": config.expected_selection_fingerprint,
        "classification_counts_unchanged": classification_counts,
        "trusted_country_field": TRUSTED_COUNTRY_FIELD,
        "country_inference_used": False,
        "country_provenance_candidate_counts": country_counts,
        "parsers": {LIBPOSTAL: libpostal, DEEPPARSE: deepparse},
        "overlap": {
            "candidate_counts": joint_candidates,
            "occurrence_counts": joint_occurrences,
        },
        "qualitative_selection": {
            "selected_candidates": EXPECTED_SELECTION_ROWS,
            "parser_eligibility_by_original_classification": selection_by_parser,
            "classifications_changed": False,
        },
        "metric_denominators": {
            "coverage": "ELIGIBLE_CANDIDATES_DIVIDED_BY_ALL_UNIQUE_CANDIDATES",
            "technical_success": "TECHNICAL_OUTCOMES_AMONG_ELIGIBLE_ATTEMPTED_CANDIDATES",
            "semantic_quality": "ORIGINAL_QUALITATIVE_COUNTS_AMONG_REVIEWED_ELIGIBLE_CANDIDATES",
            "usable": "PLAUSIBLE_PARSE_PLUS_PARTIAL_BUT_USABLE_PARSE",
        },
        "design_consequences": {
            "primary_parse_key": "STAGE06_EXACT_CANDIDATE_ID_FOR_CONTEXT_INDEPENDENT_PARSER",
            "eligibility_decidable_before_parse": True,
            "conflicting_candidate_country_requires_abstention_or_future_candidate_plus_country_key": True,
            "stage06_key_changed": False,
            "authoritative_stage07_output_changed": False,
            "deepparse_zero_shot_countries_eligible": False,
            "unsupported_country_is_parser_failure": False,
        },
        "privacy": {
            "candidate_text_read": False,
            "parser_components_read": False,
            "parser_calls": 0,
            "holdout_accessed": False,
            "production_accessed": False,
            "network_calls": 0,
        },
    }


def run_country_eligibility_audit(
    config: CountryEligibilityAuditConfig,
) -> dict[str, object]:
    """Run and atomically publish the owner-only metadata audit."""
    config.validate()
    if config.authoritative_development:
        require_goethe_nhr_slurm("stage07-country-eligibility-audit")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Eligibility audit output already exists")
    eligibility = load_eligibility_manifest(config.eligibility_manifest_path)
    row_paths, registry_paths, stage06 = _validate_stage06_identity(cast(Any, config))
    stage07_paths, stage07 = _validate_stage07_identity(config)
    selection, classifications, classification_counts = _validate_review_inputs(
        cast(Any, config)
    )
    selection_lengths = pq.ParquetFile(
        config.selection_path, page_checksum_verification=True
    ).read(columns=["review_order", "input_codepoints"], use_threads=False)
    if selection_lengths.num_rows != selection.num_rows or not selection_lengths.column(
        "review_order"
    ).equals(selection.column("review_order")):
        _fail("SELECTION_FINGERPRINT_MISMATCH", "Selection length metadata differs")
    selection = selection.append_column(
        "input_codepoints", selection_lengths.column("input_codepoints")
    )
    if config.authoritative_development and (
        classification_counts != EXPECTED_CLASSIFICATION_COUNTS
    ):
        _fail("CLASSIFICATION_ARTIFACT_INVALID", "Review totals differ")

    parent = config.output_directory.parent
    partial = parent / f".{config.output_directory.name}.partial.{os.getpid()}"
    old_umask = os.umask(0o077)
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent.chmod(0o700)
        partial.mkdir(mode=0o700)
        spill = partial / "duckdb_spill"
        spill.mkdir(mode=0o700)
        connection = duckdb.connect(":memory:")
        connection.execute("SET memory_limit=?", [config.duckdb_memory_limit])
        connection.execute("SET threads=?", [config.duckdb_threads])
        connection.execute("SET temp_directory=?", [str(spill)])
        connection.execute("SET preserve_insertion_order=false")
        _build_relations(
            connection,
            row_paths=row_paths,
            registry_paths=registry_paths,
            stage07_paths=stage07_paths,
            selection=selection,
            classifications=classifications,
            valid_country_codes=eligibility.valid_iso_alpha2_codes,
            deepparse_trained_country_codes=(
                eligibility.deepparse_trained_country_codes
            ),
        )
        _validate_reconciliation(connection, config)
        candidate_path = partial / "stage07_candidate_country_eligibility.parquet"
        selection_path = partial / "stage07_selection_country_eligibility.parquet"
        connection.execute(
            "COPY candidate_eligibility_audit TO ? "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 8192)",
            [str(candidate_path)],
        )
        connection.execute(
            "COPY selection_eligibility_audit TO ? "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 120)",
            [str(selection_path)],
        )
        candidate_path.chmod(0o600)
        selection_path.chmod(0o600)
        aggregate = _aggregate(
            connection,
            config=config,
            eligibility_manifest_sha256=eligibility.sha256,
            stage06=stage06,
            stage07=stage07,
            classification_counts=classification_counts,
        )
        aggregate_path = partial / "stage07_country_eligibility_aggregate.json"
        _write_json(aggregate_path, aggregate)
        files = (candidate_path, selection_path, aggregate_path)
        file_identities = [
            {
                "relative_path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in files
        ]
        manifest = {
            "version": "stage07_country_eligibility_audit_manifest_v1",
            "status": "STAGE07_COUNTRY_ELIGIBILITY_AUDIT_COMPLETE",
            "execution_git_sha": config.execution_git_sha,
            "eligibility_manifest_sha256": eligibility.sha256,
            "aggregate_sha256": _sha256_file(aggregate_path),
            "artifacts": file_identities,
            "owner_only": True,
            "candidate_text_present": False,
        }
        manifest_path = partial / AUDIT_MANIFEST_NAME
        _write_json(manifest_path, manifest)
        success_path = partial / AUDIT_SUCCESS_NAME
        _write_json(
            success_path,
            {
                "status": "STAGE07_COUNTRY_ELIGIBILITY_AUDIT_COMPLETE",
                "manifest_sha256": _sha256_file(manifest_path),
                "aggregate_sha256": manifest["aggregate_sha256"],
            },
        )
        shutil.rmtree(spill)
        for path in partial.iterdir():
            if path.is_file():
                path.chmod(0o600)
        _fsync_directory(partial)
        os.replace(partial, config.output_directory)
        _fsync_directory(parent)
        return aggregate
    except (Stage07CountryEligibilityAuditError, duckdb.Error):
        raise
    except OSError as error:
        raise Stage07CountryEligibilityAuditError(
            "AUDIT_PUBLICATION_FAILURE", "Eligibility audit publication failed"
        ) from error
    finally:
        if connection is not None:
            connection.close()
        os.umask(old_umask)


__all__ = [
    "AUDIT_MANIFEST_NAME",
    "AUDIT_SUCCESS_NAME",
    "AUDIT_VERSION",
    "CountryEligibilityAuditConfig",
    "Stage07CountryEligibilityAuditError",
    "run_country_eligibility_audit",
]

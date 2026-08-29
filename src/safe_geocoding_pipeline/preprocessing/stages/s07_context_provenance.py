"""Protected provenance audit for the rejected Stage 7 context-hint option.

The pinned pypostal wrapper exposes ``language`` and ``country`` arguments, but
the pinned libpostal implementation explicitly sets both values to ``NULL``
before parser-context construction.  This diagnostic therefore makes no parser
calls.  It verifies that public source evidence and measures whether accepted
Stage 6 occurrence provenance could have supported parse-once country/language
context if the frozen parser had implemented it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..reporting.stage07 import QUALITATIVE_CLASSIFICATIONS
from .s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    ROW_MAP_ID_COLUMNS,
    STAGE06_CONTRACT_VERSION,
    STAGE06_MANIFEST_NAME,
    STAGE06_MANIFEST_VERSION,
    STAGE06_PROFILE_VERSION,
)
from .s07_parser_bundle import (
    LIBPOSTAL_SOURCE_COMMIT,
    PYPPOSTAL_SOURCE_COMMIT,
    ParserBundleOutcome,
    validate_parser_bundle,
)
from .s07_parsing import (
    ACCEPTED_STAGE06_LOGICAL_FINGERPRINT,
    ACCEPTED_STAGE06_MANIFEST_SHA256,
    ACCEPTED_STAGE06_OCCURRENCES,
    ACCEPTED_STAGE06_REGISTRY_ROWS,
    ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
    ACCEPTED_STAGE06_STANDARD_OCCURRENCES,
    ACCEPTED_STAGE06_NATIVE_OCCURRENCES,
    ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
)
from .s07_quality_root_cause import _selection_fingerprint


DIAGNOSTIC_VERSION = "stage07_context_provenance_diagnostic_v1"
SELECTION_FINGERPRINT = (
    "1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844"
)
COUNTRY_FIELD = "stage04_lower_country_iso_code"
EXPECTED_SELECTION_ROWS = 120
EXPECTED_TARGET_ROWS = 18
EXPECTED_CLASSIFICATION_COUNTS = {
    "CLEAR_MISPARSE": 11,
    "PARTIAL_BUT_USABLE_PARSE": 41,
    "PLAUSIBLE_PARSE": 30,
    "QUESTIONABLE_PARSE": 7,
    "UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE": 31,
}

PYPPOSTAL_PARSER_SOURCE_SHA256 = (
    "5fe25a6a23ed4845a6a22d25836c27e3651e603a64668b44f2a290178e306d02"
)
LIBPOSTAL_HEADER_SOURCE_SHA256 = (
    "d537b0709c4882919a3d6209b952c30ea072cf0ee90f3eeff655eb8c512df6bb"
)
LIBPOSTAL_ADDRESS_PARSER_SOURCE_SHA256 = (
    "a129328e4ac2301ccffdc092811a09663f01802e97c8be780c704e51a0e59222"
)

COUNTRY_CONTEXT_STATUSES = (
    "NO_USABLE_EXPLICIT_COUNTRY",
    "UNANIMOUS_ONE_COUNTRY",
    "PARTIAL_ONE_COUNTRY",
    "CONTEXT_AMBIGUOUS_FOR_PARSE_ONCE",
)
TARGET_CLASSIFICATIONS = ("CLEAR_MISPARSE", "QUESTIONABLE_PARSE")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_PYPPOSTAL_SIGNATURE = re.compile(
    r"def\s+parse_address\(address,\s*language=None,\s*country=None\):"
)
_PYPPOSTAL_FORWARDING = re.compile(
    r"_parser\.parse_address\(address,\s*language=language,\s*country=country\)"
)
_LIBPOSTAL_OPTIONS_STRUCT = re.compile(
    r"typedef\s+struct\s+libpostal_address_parser_options\s*\{\s*"
    r"char\s*\*language;\s*char\s*\*country;\s*"
    r"\}\s*libpostal_address_parser_options_t;",
    re.S,
)
_LIBPOSTAL_FORCED_NULL = re.compile(
    r"This parser was trained without knowing language/country\..*?"
    r"language\s*=\s*NULL;\s*country\s*=\s*NULL;\s*"
    r"address_parser_context_fill\(context,\s*parser,\s*tokenized_str,\s*"
    r"language,\s*country\);",
    re.S,
)


class Stage07ContextDiagnosticError(RuntimeError):
    """Privacy-safe fail-closed context diagnostic error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ContextDiagnosticError(code, detail)


@dataclass(frozen=True, slots=True)
class ContextProvenanceConfig:
    stage06_output_directory: Path
    parser_bundle_directory: Path
    selection_path: Path
    classifications_path: Path
    pypostal_parser_source: Path
    libpostal_header_source: Path
    libpostal_address_parser_source: Path
    output_directory: Path
    execution_git_sha: str
    expected_stage06_manifest_sha256: str = ACCEPTED_STAGE06_MANIFEST_SHA256
    expected_parser_bundle_fingerprint: str = ACCEPTED_PARSER_BUNDLE_FINGERPRINT
    expected_selection_fingerprint: str = SELECTION_FINGERPRINT
    expected_source_rows: int = 35_000
    expected_registry_rows: int = ACCEPTED_STAGE06_REGISTRY_ROWS
    expected_occurrences: int = ACCEPTED_STAGE06_OCCURRENCES
    expected_standard_occurrences: int = ACCEPTED_STAGE06_STANDARD_OCCURRENCES
    expected_native_occurrences: int = ACCEPTED_STAGE06_NATIVE_OCCURRENCES
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    production: bool = True

    def validate(self) -> None:
        for fingerprint in (
            self.expected_stage06_manifest_sha256,
            self.expected_parser_bundle_fingerprint,
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
            self.parser_bundle_directory,
            self.selection_path,
            self.classifications_path,
            self.pypostal_parser_source,
            self.libpostal_header_source,
            self.libpostal_address_parser_source,
            self.output_directory,
        )
        if any(
            "holdout" in part.casefold()
            for path in paths
            for part in path.resolve(strict=False).parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")
        if self.production and (
            self.expected_stage06_manifest_sha256 != ACCEPTED_STAGE06_MANIFEST_SHA256
            or self.expected_parser_bundle_fingerprint
            != ACCEPTED_PARSER_BUNDLE_FINGERPRINT
            or self.expected_selection_fingerprint != SELECTION_FINGERPRINT
            or self.expected_source_rows != 35_000
            or self.expected_registry_rows != ACCEPTED_STAGE06_REGISTRY_ROWS
            or self.expected_occurrences != ACCEPTED_STAGE06_OCCURRENCES
            or self.expected_standard_occurrences
            != ACCEPTED_STAGE06_STANDARD_OCCURRENCES
            or self.expected_native_occurrences != ACCEPTED_STAGE06_NATIVE_OCCURRENCES
        ):
            _fail("ACCEPTED_BINDING_MISMATCH", "Protected diagnostic binding differs")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise Stage07ContextDiagnosticError(
            "ARTIFACT_READ_FAILURE", "A bound artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07ContextDiagnosticError(
            "JSON_INVALID", "A bound JSON artifact could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("JSON_INVALID", "A bound JSON artifact is not an object")
    return value


def _require_mode(path: Path, mode: int) -> None:
    if path.is_symlink() or not path.exists():
        _fail("ARTIFACT_TOPOLOGY_INVALID", "A bound artifact is absent or a symlink")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        _fail("PERMISSION_FAILURE", "A protected artifact mode differs")


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


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_public_source(path: Path, expected_sha256: str) -> str:
    _require_mode(path, 0o600)
    if _sha256_file(path) != expected_sha256:
        _fail("PARSER_SOURCE_IDENTITY_MISMATCH", "Pinned parser source hash differs")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise Stage07ContextDiagnosticError(
            "PARSER_SOURCE_READ_FAILURE", "Pinned parser source is unreadable"
        ) from error


def _validate_parser_api_sources(config: ContextProvenanceConfig) -> dict[str, object]:
    pypostal = _read_public_source(
        config.pypostal_parser_source, PYPPOSTAL_PARSER_SOURCE_SHA256
    )
    header = _read_public_source(
        config.libpostal_header_source, LIBPOSTAL_HEADER_SOURCE_SHA256
    )
    implementation = _read_public_source(
        config.libpostal_address_parser_source,
        LIBPOSTAL_ADDRESS_PARSER_SOURCE_SHA256,
    )
    if (
        _PYPPOSTAL_SIGNATURE.search(pypostal) is None
        or _PYPPOSTAL_FORWARDING.search(pypostal) is None
        or _LIBPOSTAL_OPTIONS_STRUCT.search(header) is None
        or _LIBPOSTAL_FORCED_NULL.search(implementation) is None
    ):
        _fail("PARSER_API_EVIDENCE_MISMATCH", "Pinned API source semantics differ")
    return {
        "libpostal_source_commit": LIBPOSTAL_SOURCE_COMMIT,
        "pypostal_source_commit": PYPPOSTAL_SOURCE_COMMIT,
        "pypostal_signature": "parse_address(address, language=None, country=None)",
        "pypostal_exposed_context_parameters": ["language", "country"],
        "libpostal_options_struct_fields": ["language", "country"],
        "libpostal_native_option_handling": (
            "LANGUAGE_AND_COUNTRY_FORCED_NULL_BEFORE_CONTEXT_FILL"
        ),
        "effective_context_parameters": [],
        "applicable_context_variants": [],
        "pypostal_parser_source_sha256": PYPPOSTAL_PARSER_SOURCE_SHA256,
        "libpostal_header_source_sha256": LIBPOSTAL_HEADER_SOURCE_SHA256,
        "libpostal_address_parser_source_sha256": (
            LIBPOSTAL_ADDRESS_PARSER_SOURCE_SHA256
        ),
    }


def _manifest_artifacts(
    root: Path,
    physical: dict[str, Any],
    key: str,
    expected_rows: int,
) -> tuple[Path, ...]:
    raw = physical.get(key)
    if not isinstance(raw, list) or not raw:
        _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact list is absent")
    paths: list[Path] = []
    observed_rows = 0
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"relative_path", "row_count", "sha256", "size_bytes"}
            or not isinstance(item["relative_path"], str)
            or not isinstance(item["row_count"], int)
            or not isinstance(item["size_bytes"], int)
            or not isinstance(item["sha256"], str)
            or _SHA256_RE.fullmatch(item["sha256"]) is None
        ):
            _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact identity is malformed")
        relative = Path(item["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            _fail("STAGE06_MANIFEST_INVALID", "Stage 6 artifact path is unsafe")
        path = root / relative
        _require_mode(path, 0o600)
        if (
            path.stat(follow_symlinks=False).st_size != item["size_bytes"]
            or _sha256_file(path) != item["sha256"]
        ):
            _fail("STAGE06_ARTIFACT_MISMATCH", "Stage 6 artifact identity differs")
        observed_rows += item["row_count"]
        paths.append(path)
    if observed_rows != expected_rows:
        _fail("STAGE06_ROW_COUNT_MISMATCH", "Stage 6 artifact row count differs")
    return tuple(paths)


def _validate_stage06_identity(
    config: ContextProvenanceConfig,
) -> tuple[tuple[Path, ...], tuple[Path, ...], dict[str, object]]:
    root = config.stage06_output_directory
    _require_mode(root, 0o700)
    manifest_path = root / STAGE06_MANIFEST_NAME
    _require_mode(manifest_path, 0o600)
    if _sha256_file(manifest_path) != config.expected_stage06_manifest_sha256:
        _fail("STAGE06_MANIFEST_SHA256_MISMATCH", "Accepted manifest SHA differs")
    manifest = _load_json(manifest_path)
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if (
        manifest.get("stage06_manifest_version") != STAGE06_MANIFEST_VERSION
        or manifest.get("status") != "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED"
        or not isinstance(scientific, dict)
        or not isinstance(physical, dict)
        or scientific.get("stage06_contract_version") != STAGE06_CONTRACT_VERSION
        or scientific.get("stage06_profile_version") != STAGE06_PROFILE_VERSION
        or scientific.get("source_row_count") != config.expected_source_rows
        or scientific.get("unique_candidate_count") != config.expected_registry_rows
        or scientific.get("registry_columns") != list(REGISTRY_COLUMNS)
        or scientific.get("row_map_id_columns") != list(ROW_MAP_ID_COLUMNS)
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Accepted Stage 6 identity differs")
    if config.production and (
        scientific.get("stage06_schema_fingerprint")
        != ACCEPTED_STAGE06_SCHEMA_FINGERPRINT
        or scientific.get("stage06_logical_dataset_sha256_v1")
        != ACCEPTED_STAGE06_LOGICAL_FINGERPRINT
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Accepted Stage 6 fingerprint differs")
    row_paths = _manifest_artifacts(
        root, physical, "row_map_artifacts", int(scientific["source_row_count"])
    )
    registry_paths = _manifest_artifacts(
        root, physical, "registry_artifacts", config.expected_registry_rows
    )
    identity: dict[str, object] = {
        "contract": scientific["stage06_contract_version"],
        "profile": scientific["stage06_profile_version"],
        "schema_fingerprint": scientific.get("stage06_schema_fingerprint"),
        "logical_fingerprint": scientific.get("stage06_logical_dataset_sha256_v1"),
        "manifest_sha256": config.expected_stage06_manifest_sha256,
        "registry_rows": config.expected_registry_rows,
        "occurrences": config.expected_occurrences,
        "standard_occurrences": config.expected_standard_occurrences,
        "native_occurrences": config.expected_native_occurrences,
        "row_map_artifact_count": len(row_paths),
        "registry_artifact_count": len(registry_paths),
    }
    return row_paths, registry_paths, identity


def _validate_review_inputs(
    config: ContextProvenanceConfig,
) -> tuple[pa.Table, pa.Table, dict[str, int]]:
    _require_mode(config.selection_path, 0o600)
    _require_mode(config.classifications_path, 0o600)
    selection = pq.ParquetFile(
        config.selection_path, page_checksum_verification=True
    ).read(
        columns=["review_order", "stage06_exact_candidate_id", "selection_reasons"],
        use_threads=False,
    )
    if _selection_fingerprint(selection) != config.expected_selection_fingerprint:
        _fail("SELECTION_FINGERPRINT_MISMATCH", "Immutable selection differs")
    artifact = _load_json(config.classifications_path)
    if (
        set(artifact) != {"selection_fingerprint", "classifications"}
        or artifact.get("selection_fingerprint")
        != config.expected_selection_fingerprint
        or not isinstance(artifact.get("classifications"), list)
    ):
        _fail("CLASSIFICATION_ARTIFACT_INVALID", "Classification framing differs")
    rows = cast(list[Any], artifact["classifications"])
    by_order: dict[int, str] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"review_order", "classification"}
            or not isinstance(row["review_order"], int)
            or row["classification"] not in QUALITATIVE_CLASSIFICATIONS
            or row["review_order"] in by_order
        ):
            _fail("CLASSIFICATION_ARTIFACT_INVALID", "Classification row differs")
        by_order[row["review_order"]] = row["classification"]
    if set(by_order) != set(range(1, EXPECTED_SELECTION_ROWS + 1)):
        _fail("CLASSIFICATION_ARTIFACT_INVALID", "Classification coverage differs")
    counts = dict(sorted(Counter(by_order.values()).items()))
    if config.production and counts != EXPECTED_CLASSIFICATION_COUNTS:
        _fail("CLASSIFICATION_ARTIFACT_INVALID", "Classification totals differ")
    classification_table = pa.table(
        {
            "review_order": pa.array(sorted(by_order), type=pa.uint32()),
            "classification": pa.array(
                [by_order[index] for index in sorted(by_order)], type=pa.string()
            ),
        }
    )
    return selection, classification_table, counts


def _query_int(connection: duckdb.DuckDBPyConnection, query: str) -> int:
    row = connection.execute(query).fetchone()
    if row is None or not isinstance(row[0], int):
        _fail("AUDIT_QUERY_FAILURE", "A bounded audit count is absent")
    return row[0]


def _count_by(
    connection: duckdb.DuckDBPyConnection, relation: str, column: str
) -> dict[str, int]:
    rows = connection.execute(
        f"SELECT {column}, count(*) FROM {relation} GROUP BY 1 ORDER BY 1"
    ).fetchall()
    result: dict[str, int] = {}
    for key, count in rows:
        if not isinstance(key, str) or not isinstance(count, int):
            _fail("AUDIT_QUERY_FAILURE", "A bounded category result is malformed")
        result[key] = count
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
        if (
            not isinstance(first_value, str)
            or not isinstance(second_value, str)
            or not isinstance(count, int)
        ):
            _fail("AUDIT_QUERY_FAILURE", "A bounded cross-tab is malformed")
        result.setdefault(first_value, {})[second_value] = count
    return result


def _build_audit_relations(
    connection: duckdb.DuckDBPyConnection,
    *,
    row_paths: tuple[Path, ...],
    registry_paths: tuple[Path, ...],
    selection: pa.Table,
    classifications: pa.Table,
) -> None:
    connection.register("immutable_selection_arrow", selection)
    connection.register("review_classifications_arrow", classifications)
    connection.read_parquet([str(path) for path in row_paths]).create_view(
        "stage06_row_map"
    )
    connection.read_parquet([str(path) for path in registry_paths]).create_view(
        "stage06_registry_source"
    )
    connection.execute(
        f"""
        CREATE TEMP VIEW stage06_occurrences AS
        SELECT
            {ROW_MAP_ID_COLUMNS[0]} AS candidate_id,
            'STANDARD'::VARCHAR AS representation,
            {COUNTRY_FIELD} AS country_context
        FROM stage06_row_map
        WHERE {ROW_MAP_ID_COLUMNS[0]} IS NOT NULL
        UNION ALL
        SELECT
            {ROW_MAP_ID_COLUMNS[1]} AS candidate_id,
            'NATIVE'::VARCHAR AS representation,
            {COUNTRY_FIELD} AS country_context
        FROM stage06_row_map
        WHERE {ROW_MAP_ID_COLUMNS[1]} IS NOT NULL
        """
    )
    connection.execute(
        f"""
        CREATE TEMP VIEW stage06_registry_metadata AS
        SELECT
            {REGISTRY_COLUMNS[0]} AS candidate_id,
            {REGISTRY_COLUMNS[2]} AS occurrence_count,
            {REGISTRY_COLUMNS[3]} AS standard_occurrence_count,
            {REGISTRY_COLUMNS[4]} AS native_occurrence_count
        FROM stage06_registry_source
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE candidate_context_audit AS
        WITH marked AS (
            SELECT
                candidate_id,
                representation,
                country_context,
                country_context IS NOT NULL
                    AND regexp_full_match(country_context, '^[a-z]{2}$') AS usable
            FROM stage06_occurrences
        ), aggregated AS (
            SELECT
                candidate_id,
                count(*)::UBIGINT AS observed_occurrence_count,
                count(*) FILTER (WHERE representation = 'STANDARD')::UBIGINT
                    AS observed_standard_occurrence_count,
                count(*) FILTER (WHERE representation = 'NATIVE')::UBIGINT
                    AS observed_native_occurrence_count,
                count(*) FILTER (WHERE usable)::UBIGINT
                    AS usable_country_occurrence_count,
                count(*) FILTER (
                    WHERE country_context IS NULL OR country_context = ''
                )::UBIGINT AS missing_country_occurrence_count,
                count(*) FILTER (
                    WHERE country_context IS NOT NULL
                      AND country_context != '' AND NOT usable
                )::UBIGINT AS invalid_country_occurrence_count,
                count(DISTINCT country_context) FILTER (WHERE usable)::UINTEGER
                    AS distinct_usable_country_count,
                count(DISTINCT country_context) FILTER (
                    WHERE usable AND representation = 'STANDARD'
                )::UINTEGER AS standard_distinct_usable_country_count,
                count(DISTINCT country_context) FILTER (
                    WHERE usable AND representation = 'NATIVE'
                )::UINTEGER AS native_distinct_usable_country_count,
                coalesce(
                    list_sort(list_distinct(list(country_context) FILTER (
                        WHERE usable AND representation = 'STANDARD'
                    ))), []::VARCHAR[]
                ) AS standard_context_set,
                coalesce(
                    list_sort(list_distinct(list(country_context) FILTER (
                        WHERE usable AND representation = 'NATIVE'
                    ))), []::VARCHAR[]
                ) AS native_context_set,
                count(*) FILTER (
                    WHERE representation = 'STANDARD' AND NOT usable
                ) > 0 AS standard_has_unusable_context,
                count(*) FILTER (
                    WHERE representation = 'NATIVE' AND NOT usable
                ) > 0 AS native_has_unusable_context
            FROM marked
            GROUP BY candidate_id
        )
        SELECT
            r.candidate_id,
            r.occurrence_count,
            r.standard_occurrence_count,
            r.native_occurrence_count,
            a.usable_country_occurrence_count,
            a.missing_country_occurrence_count,
            a.invalid_country_occurrence_count,
            a.distinct_usable_country_count,
            a.standard_distinct_usable_country_count,
            a.native_distinct_usable_country_count,
            CASE
                WHEN a.distinct_usable_country_count = 0
                    THEN 'NO_USABLE_EXPLICIT_COUNTRY'
                WHEN a.distinct_usable_country_count >= 2
                    THEN 'CONTEXT_AMBIGUOUS_FOR_PARSE_ONCE'
                WHEN a.usable_country_occurrence_count = a.observed_occurrence_count
                    THEN 'UNANIMOUS_ONE_COUNTRY'
                ELSE 'PARTIAL_ONE_COUNTRY'
            END::VARCHAR AS country_context_status,
            a.distinct_usable_country_count >= 2
                AS context_ambiguous_for_parse_once,
            a.distinct_usable_country_count = 1
                AND a.usable_country_occurrence_count = a.observed_occurrence_count
                AS country_only_parse_once_eligible,
            false AS effective_context_variant_eligible,
            'NO_EXPLICIT_LANGUAGE_FIELD'::VARCHAR AS explicit_language_status,
            r.standard_occurrence_count > 0 AND r.native_occurrence_count > 0
                AS both_representations,
            CASE
                WHEN r.standard_occurrence_count > 0 AND r.native_occurrence_count > 0
                THEN a.standard_context_set != a.native_context_set
                  OR a.standard_has_unusable_context != a.native_has_unusable_context
                ELSE false
            END AS context_differs_across_standard_native
        FROM stage06_registry_metadata r
        JOIN aggregated a ON a.candidate_id = r.candidate_id
        WHERE r.occurrence_count = a.observed_occurrence_count
          AND r.standard_occurrence_count = a.observed_standard_occurrence_count
          AND r.native_occurrence_count = a.observed_native_occurrence_count
        ORDER BY r.candidate_id
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE selection_context_audit AS
        SELECT
            s.review_order,
            s.stage06_exact_candidate_id AS candidate_id,
            c.classification,
            a.occurrence_count,
            a.standard_occurrence_count,
            a.native_occurrence_count,
            a.usable_country_occurrence_count,
            a.missing_country_occurrence_count,
            a.invalid_country_occurrence_count,
            a.distinct_usable_country_count,
            a.country_context_status,
            a.context_ambiguous_for_parse_once,
            a.country_only_parse_once_eligible,
            a.effective_context_variant_eligible,
            a.explicit_language_status,
            a.both_representations,
            a.context_differs_across_standard_native
        FROM immutable_selection_arrow s
        JOIN review_classifications_arrow c USING (review_order)
        JOIN candidate_context_audit a
          ON a.candidate_id = s.stage06_exact_candidate_id
        ORDER BY s.review_order
        """
    )


def _validate_reconciliation(
    connection: duckdb.DuckDBPyConnection, config: ContextProvenanceConfig
) -> None:
    expected = {
        "occurrences": config.expected_occurrences,
        "standard": config.expected_standard_occurrences,
        "native": config.expected_native_occurrences,
        "registry": config.expected_registry_rows,
        "selection": EXPECTED_SELECTION_ROWS,
    }
    observed = {
        "occurrences": _query_int(
            connection, "SELECT count(*) FROM stage06_occurrences"
        ),
        "standard": _query_int(
            connection,
            "SELECT count(*) FROM stage06_occurrences WHERE representation='STANDARD'",
        ),
        "native": _query_int(
            connection,
            "SELECT count(*) FROM stage06_occurrences WHERE representation='NATIVE'",
        ),
        "registry": _query_int(
            connection, "SELECT count(*) FROM candidate_context_audit"
        ),
        "selection": _query_int(
            connection, "SELECT count(*) FROM selection_context_audit"
        ),
    }
    if observed != expected:
        _fail("AUDIT_RECONCILIATION_FAILURE", "Candidate/occurrence totals differ")
    if _query_int(
        connection,
        "SELECT count(*) - count(DISTINCT candidate_id) FROM candidate_context_audit",
    ):
        _fail("AUDIT_RECONCILIATION_FAILURE", "Candidate audit contains duplicate IDs")
    if _query_int(
        connection,
        "SELECT count(*) FROM stage06_registry_metadata r LEFT JOIN "
        "candidate_context_audit a USING (candidate_id) WHERE a.candidate_id IS NULL",
    ):
        _fail("AUDIT_RECONCILIATION_FAILURE", "A registry candidate is unreconciled")
    status_counts = _count_by(
        connection, "candidate_context_audit", "country_context_status"
    )
    if set(status_counts) - set(COUNTRY_CONTEXT_STATUSES):
        _fail("AUDIT_RECONCILIATION_FAILURE", "Country status vocabulary differs")


def _aggregate(
    connection: duckdb.DuckDBPyConnection,
    *,
    config: ContextProvenanceConfig,
    api: dict[str, object],
    bundle: ParserBundleOutcome,
    stage06: dict[str, object],
    classification_counts: dict[str, int],
) -> dict[str, object]:
    population_status = _count_by(
        connection, "candidate_context_audit", "country_context_status"
    )
    selection_status = _count_by(
        connection, "selection_context_audit", "country_context_status"
    )
    target_status = _count_by(
        connection,
        "(SELECT * FROM selection_context_audit WHERE classification IN "
        "('CLEAR_MISPARSE','QUESTIONABLE_PARSE'))",
        "country_context_status",
    )
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "scientific_scope": "NON_AUTHORITATIVE_METADATA_ONLY_NO_PARSER_CALLS",
        "decision": "CONTEXT_AWARE_LIBPOSTAL_NOT_SUFFICIENT",
        "decision_basis": "PINNED_LIBPOSTAL_EXPLICITLY_IGNORES_EXPOSED_CONTEXT_OPTIONS",
        "api_evidence": api,
        "parser_bundle": {
            "fingerprint": bundle.parser_bundle_fingerprint,
            "manifest_sha256": bundle.manifest_sha256,
            "artifact_count": bundle.artifact_count,
            "total_size_bytes": bundle.total_size_bytes,
        },
        "stage06_binding": stage06,
        "selection_fingerprint": config.expected_selection_fingerprint,
        "classification_counts": classification_counts,
        "trusted_upstream_context": {
            "country_field": COUNTRY_FIELD,
            "country_eligibility_rule": "EXACT_ASCII_LOWERCASE_TWO_LETTER_CODE",
            "language_field_present": False,
            "language_inference_used": False,
            "country_inference_used": False,
        },
        "population_audit": {
            "candidates": config.expected_registry_rows,
            "country_context_status_counts": population_status,
            "no_usable_explicit_country": population_status.get(
                "NO_USABLE_EXPLICIT_COUNTRY", 0
            ),
            "unanimous_one_country": population_status.get("UNANIMOUS_ONE_COUNTRY", 0),
            "partial_one_country": population_status.get("PARTIAL_ONE_COUNTRY", 0),
            "conflicting_countries": population_status.get(
                "CONTEXT_AMBIGUOUS_FOR_PARSE_ONCE", 0
            ),
            "no_explicit_language": config.expected_registry_rows,
            "unanimous_one_explicit_language": 0,
            "conflicting_explicit_languages": 0,
            "unique_country_language_combination": 0,
            "country_only_parse_once_eligible": _query_int(
                connection,
                "SELECT count(*) FROM candidate_context_audit "
                "WHERE country_only_parse_once_eligible",
            ),
            "candidates_with_missing_country_occurrences": _query_int(
                connection,
                "SELECT count(*) FROM candidate_context_audit "
                "WHERE missing_country_occurrence_count > 0",
            ),
            "candidates_with_invalid_country_occurrences": _query_int(
                connection,
                "SELECT count(*) FROM candidate_context_audit "
                "WHERE invalid_country_occurrence_count > 0",
            ),
            "missing_country_occurrences": _query_int(
                connection,
                "SELECT sum(missing_country_occurrence_count)::BIGINT "
                "FROM candidate_context_audit",
            ),
            "invalid_country_occurrences": _query_int(
                connection,
                "SELECT sum(invalid_country_occurrence_count)::BIGINT "
                "FROM candidate_context_audit",
            ),
            "effective_context_variant_eligible": 0,
            "both_representation_candidates": _query_int(
                connection,
                "SELECT count(*) FROM candidate_context_audit WHERE both_representations",
            ),
            "context_differs_across_standard_native": _query_int(
                connection,
                "SELECT count(*) FROM candidate_context_audit "
                "WHERE context_differs_across_standard_native",
            ),
        },
        "selection_audit": {
            "candidates": EXPECTED_SELECTION_ROWS,
            "country_context_status_counts": selection_status,
            "country_only_parse_once_eligible": _query_int(
                connection,
                "SELECT count(*) FROM selection_context_audit "
                "WHERE country_only_parse_once_eligible",
            ),
            "effective_context_variant_eligible": 0,
            "context_differs_across_standard_native": _query_int(
                connection,
                "SELECT count(*) FROM selection_context_audit "
                "WHERE context_differs_across_standard_native",
            ),
            "classification_country_status_counts": _nested_counts(
                connection,
                "selection_context_audit",
                "classification",
                "country_context_status",
            ),
        },
        "target_audit": {
            "cases": EXPECTED_TARGET_ROWS,
            "clear_misparse": classification_counts.get("CLEAR_MISPARSE", 0),
            "questionable_parse": classification_counts.get("QUESTIONABLE_PARSE", 0),
            "country_context_status_counts": target_status,
            "country_only_parse_once_eligible": _query_int(
                connection,
                "SELECT count(*) FROM selection_context_audit WHERE "
                "classification IN ('CLEAR_MISPARSE','QUESTIONABLE_PARSE') "
                "AND country_only_parse_once_eligible",
            ),
            "effective_context_variant_eligible": 0,
        },
        "variant_execution": {
            "variants_created": 0,
            "protected_parser_calls": 0,
            "candidate_text_inspections": 0,
            "deterministic_repeats": "NOT_APPLICABLE_NO_EFFECTIVE_VARIANTS",
            "paired_llm_assessment": "NOT_PERFORMED_NO_EFFECTIVE_VARIANTS",
            "owner_authorization_exercised": False,
            "target_improvements": "NOT_APPLICABLE",
            "target_regressions": "NOT_APPLICABLE",
            "control_regressions": "NOT_APPLICABLE",
            "label_error_repairs": "NOT_APPLICABLE",
            "boundary_error_repairs": "NOT_APPLICABLE",
            "script_stratum_effects": "NOT_APPLICABLE",
        },
        "future_parse_key": {
            "candidate_plus_context_required_for_conflicting_candidates_if_future_"
            "effective_context_exists": population_status.get(
                "CONTEXT_AMBIGUOUS_FOR_PARSE_ONCE", 0
            )
            > 0,
            "stage06_key_changed": False,
            "current_stage07_authoritative_output_changed": False,
        },
        "privacy": {
            "holdout_accessed": False,
            "production_accessed": False,
            "web_or_external_api_used": False,
            "candidate_text_in_sanitized_aggregate": False,
        },
    }


def run_context_provenance_diagnostic(
    config: ContextProvenanceConfig,
) -> dict[str, object]:
    """Run the no-parse API/provenance audit and publish owner-only evidence."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-context-provenance-diagnostic")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output path already exists")

    api = _validate_parser_api_sources(config)
    bundle = validate_parser_bundle(
        config.parser_bundle_directory,
        expected_parser_bundle_fingerprint=config.expected_parser_bundle_fingerprint,
    )
    row_paths, registry_paths, stage06 = _validate_stage06_identity(config)
    selection, classifications, classification_counts = _validate_review_inputs(config)

    parent = config.output_directory.parent
    old_umask = os.umask(0o077)
    partial = parent / f".{config.output_directory.name}.partial.{os.getpid()}"
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        _require_mode(parent, 0o700)
        if partial.exists() or partial.is_symlink():
            _fail("OUTPUT_COLLISION", "Diagnostic partial path already exists")
        partial.mkdir(mode=0o700)
        spill = partial / ".spill"
        spill.mkdir(mode=0o700)
        database = partial / ".audit.duckdb"
        connection = duckdb.connect(str(database))
        database.chmod(0o600)
        escaped_spill = str(spill).replace("'", "''")
        connection.execute(f"SET memory_limit='{config.duckdb_memory_limit}'")
        connection.execute(f"SET threads={config.duckdb_threads}")
        connection.execute("SET preserve_insertion_order=false")
        connection.execute(f"SET temp_directory='{escaped_spill}'")
        _build_audit_relations(
            connection,
            row_paths=row_paths,
            registry_paths=registry_paths,
            selection=selection,
            classifications=classifications,
        )
        _validate_reconciliation(connection, config)
        aggregate = _aggregate(
            connection,
            config=config,
            api=api,
            bundle=bundle,
            stage06=stage06,
            classification_counts=classification_counts,
        )
        candidate_path = partial / "stage07_context_candidate_audit.parquet"
        selection_path = partial / "stage07_context_selection_audit.parquet"
        candidate_sql_path = str(candidate_path).replace("'", "''")
        selection_sql_path = str(selection_path).replace("'", "''")
        connection.execute(
            f"COPY candidate_context_audit TO '{candidate_sql_path}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 4096)"
        )
        connection.execute(
            f"COPY selection_context_audit TO '{selection_sql_path}' "
            "(FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 120)"
        )
        connection.close()
        connection = None
        database.unlink()
        shutil.rmtree(spill)
        for path in (candidate_path, selection_path):
            path.chmod(0o600)
            _fsync_file(path)
        if (
            pq.ParquetFile(candidate_path).metadata.num_rows
            != config.expected_registry_rows
            or pq.ParquetFile(selection_path).metadata.num_rows
            != EXPECTED_SELECTION_ROWS
            or "stage06_candidate_lower" in pq.read_schema(candidate_path).names
            or COUNTRY_FIELD in pq.read_schema(candidate_path).names
            or set(partial.iterdir()) != {candidate_path, selection_path}
        ):
            _fail("AUDIT_PUBLICATION_INVALID", "Protected Parquet readback differs")

        aggregate_path = partial / "stage07_context_provenance_aggregate.json"
        manifest_path = partial / "stage07_context_provenance_manifest.json"
        success_path = partial / "STAGE07_CONTEXT_PROVENANCE_DIAGNOSTIC_COMPLETE"
        _write_json(aggregate_path, aggregate)
        manifest = {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "status": "STAGE07_CONTEXT_PROVENANCE_DIAGNOSTIC_COMPLETE",
            "execution_git_sha": config.execution_git_sha,
            "selection_fingerprint": config.expected_selection_fingerprint,
            "parser_bundle_fingerprint": bundle.parser_bundle_fingerprint,
            "stage06_manifest_sha256": config.expected_stage06_manifest_sha256,
            "selection_sha256": _sha256_file(config.selection_path),
            "classifications_sha256": _sha256_file(config.classifications_path),
            "aggregate_sha256": _sha256_file(aggregate_path),
            "candidate_audit_sha256": _sha256_file(candidate_path),
            "selection_audit_sha256": _sha256_file(selection_path),
            "candidate_audit_rows": config.expected_registry_rows,
            "selection_audit_rows": EXPECTED_SELECTION_ROWS,
            "parser_calls": 0,
            "created_at_epoch_seconds": int(time.time()),
            "protected_values_in_aggregate": False,
        }
        _write_json(manifest_path, manifest)
        _write_json(
            success_path,
            {
                "status": "STAGE07_CONTEXT_PROVENANCE_DIAGNOSTIC_COMPLETE",
                "manifest_sha256": _sha256_file(manifest_path),
            },
        )
        _fsync_directory(partial)
        os.replace(partial, config.output_directory)
        _fsync_directory(parent)
    except (duckdb.Error, OSError) as error:
        raise Stage07ContextDiagnosticError(
            "CONTEXT_AUDIT_EXECUTION_FAILURE", "Protected metadata audit failed"
        ) from error
    finally:
        if connection is not None:
            connection.close()
        os.umask(old_umask)
    return aggregate


__all__ = [
    "ContextProvenanceConfig",
    "Stage07ContextDiagnosticError",
    "run_context_provenance_diagnostic",
]

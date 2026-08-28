"""Aggregate-only controlled Stage 7 libpostal design diagnostic."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import resource
import shutil
import stat
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..reporting.stage06 import (
    STAGE06_REVIEW_PATH,
    stage06_review_schema,
)
from ..script_reference import ScriptReference, unicode_script_reference_paths
from .s06_exact_deduplication import (
    REGISTRY_COLUMNS,
    ROW_MAP_ID_COLUMNS,
    STAGE06_MANIFEST_NAME,
    validate_stage06_bundle,
)
from .s07_libpostal_adapter import (
    PARSED_EMPTY,
    PARSED_NONEMPTY,
    ParsedAddress,
    PypostalParser,
    Stage07ParserError,
    ordered_parse_sha256,
)
from .s07_parser_bundle import validate_parser_bundle


STAGE07_DESIGN_DIAGNOSTIC_VERSION = "stage07_libpostal_design_diagnostic_v1"
STAGE07_DESIGN_DIAGNOSTIC_NAME = "stage07_design_diagnostic.json"
STAGE07_DESIGN_SUCCESS_NAME = "_SUCCESS.json"
STAGE07_DESIGN_SELECTION_DOMAIN = b"SAFE_STAGE07_DESIGN_SELECTION_V1"

ACCEPTED_STAGE06_CONTRACT = "stage06_early_exact_deduplication_contract_v1"
ACCEPTED_STAGE06_PROFILE = "stage06_early_exact_deduplication_profile_v1"
ACCEPTED_STAGE06_SCHEMA_FINGERPRINT = (
    "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
)
ACCEPTED_STAGE06_LOGICAL_FINGERPRINT = (
    "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
)
ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT = (
    "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
)
ACCEPTED_STAGE06_MANIFEST_FINGERPRINT = (
    "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
)
ACCEPTED_BENCHMARK_FINGERPRINT = (
    "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
)
ACCEPTED_FIXED_500_FINGERPRINT = (
    "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
)
ACCEPTED_STAGE06_ROWS = 51_779
ACCEPTED_SOURCE_ROWS = 35_000
ACCEPTED_OCCURRENCES = 69_747
ACCEPTED_STANDARD_OCCURRENCES = 34_822
ACCEPTED_NATIVE_OCCURRENCES = 34_925
ACCEPTED_FIXED500_ROWS = 500
ACCEPTED_FIXED500_OCCURRENCES = 937
ACCEPTED_FIXED500_UNIQUE_CANDIDATES = 613
ACCEPTED_CASE_VARIANT_GROUPS = 123
ACCEPTED_CASE_VARIANT_SURFACES = 246
ACCEPTED_GIANT_CANDIDATES = 23
GIANT_MINIMUM_CODEPOINTS = 1_000_000
ACCEPTED_MAXIMUM_CODEPOINTS = 25_920_495

_ROW_MAP_DIRECTORY = "row_map/data"
_REGISTRY_DIRECTORY = "registry/data"
_SHA256_LENGTH = 64
_GIT_SHA_LENGTH = 40
_SAMPLE_PER_STRATUM = 16
_ORDINARY_SAMPLE_COUNT = 64
_DETERMINISM_SAMPLE_COUNT = 64


class Stage07DesignDiagnosticError(RuntimeError):
    """Privacy-safe controlled diagnostic failure."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class Stage07DesignDiagnosticConfig:
    stage05_output_directory: Path
    stage06_output_directory: Path
    expected_stage06_manifest_sha256: str
    stage06_review_directory: Path
    expected_stage06_review_manifest_sha256: str
    parser_bundle_directory: Path
    expected_parser_bundle_fingerprint: str
    output_directory: Path
    execution_git_sha: str
    giant_timeout_seconds: int = 900
    giant_address_space_bytes: int = 48 * 1024 * 1024 * 1024
    fresh_process_timeout_seconds: int = 1_800
    duckdb_memory_limit: str = "8GB"
    duckdb_threads: int = 4
    production: bool = True
    authoritative_development: bool = True

    def validate(self) -> None:
        for value in (
            self.expected_stage06_manifest_sha256,
            self.expected_stage06_review_manifest_sha256,
            self.expected_parser_bundle_fingerprint,
        ):
            _require_sha256(value)
        if len(self.execution_git_sha) != _GIT_SHA_LENGTH or any(
            character not in "0123456789abcdef" for character in self.execution_git_sha
        ):
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be exact")
        if (
            self.giant_timeout_seconds < 1
            or self.giant_address_space_bytes < 8 * 1024 * 1024 * 1024
            or self.fresh_process_timeout_seconds < 1
            or self.duckdb_threads < 1
            or not self.duckdb_memory_limit
        ):
            _fail("INVALID_DIAGNOSTIC_BOUNDS", "Diagnostic bounds are invalid")
        _reject_holdout_paths(
            self.stage05_output_directory,
            self.stage06_output_directory,
            self.stage06_review_directory,
            self.parser_bundle_directory,
            self.output_directory,
        )


@dataclass(frozen=True, slots=True)
class Stage07DesignDiagnosticOutcome:
    output_directory: Path
    diagnostic_sha256: str
    parser_bundle_fingerprint: str
    diagnostic_candidate_count: int
    gate_result: str


@dataclass(frozen=True, slots=True)
class _CandidateFeatures:
    length_bucket: str
    script_bucket: str
    representation_bucket: str
    occurrence_bucket: str
    numeric_heavy: bool
    punctuation_heavy: bool
    giant: bool

    def reasons(self) -> tuple[str, ...]:
        values = [
            f"LENGTH:{self.length_bucket}",
            f"SCRIPT:{self.script_bucket}",
            f"REPRESENTATION:{self.representation_bucket}",
            f"OCCURRENCE:{self.occurrence_bucket}",
        ]
        if self.numeric_heavy:
            values.append("NUMERIC_HEAVY")
        if self.punctuation_heavy:
            values.append("PUNCTUATION_HEAVY")
        if self.giant:
            values.append("GIANT")
        return tuple(values)


@dataclass(frozen=True, slots=True)
class _IsolatedParseResult:
    ok: bool
    failure: str
    status: str
    component_count: int
    label_counts: Mapping[str, int]
    output_codepoints: int
    elapsed_seconds: float
    ordered_parse_sha256: str
    input_codepoints: int
    input_sha256: str


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07DesignDiagnosticError(code, detail)


def _require_sha256(value: str) -> None:
    if len(value) != _SHA256_LENGTH or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail("INVALID_FINGERPRINT", "A required SHA-256 is malformed")


def _reject_holdout_paths(*paths: Path) -> None:
    if any(
        "holdout" in part.casefold()
        for path in paths
        for part in path.resolve(strict=False).parts
    ):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")


def _require_mode(path: Path, expected: int) -> None:
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != expected:
        _fail("PERMISSION_FAILURE", "Controlled path permissions differ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07DesignDiagnosticError(
            "DIAGNOSTIC_READ_FAILURE", "A controlled artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07DesignDiagnosticError(
            "MANIFEST_INVALID", "A controlled manifest could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("MANIFEST_INVALID", "Manifest root is not an object")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _artifact_paths(
    root: Path, manifest: Mapping[str, Any], key: str, prefix: str
) -> tuple[Path, ...]:
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(physical.get(key), list):
        _fail("MANIFEST_INVALID", "Stage 6 physical identity is malformed")
    paths: list[Path] = []
    for raw in physical[key]:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("MANIFEST_INVALID", "Stage 6 artifact identity is malformed")
        relative = cast(str, raw["relative_path"])
        if not relative.startswith(f"{prefix}/"):
            _fail("MANIFEST_INVALID", "Stage 6 artifact path is outside its role")
        path = root / relative
        if not path.is_file() or path.is_symlink():
            _fail("ARTIFACT_INVALID", "Stage 6 artifact is absent or unsafe")
        _require_mode(path, 0o600)
        if path.stat().st_size != raw.get("size_bytes") or _sha256_file(
            path
        ) != raw.get("sha256"):
            _fail("ARTIFACT_MISMATCH", "Stage 6 artifact identity differs")
        paths.append(path)
    return tuple(paths)


def _validated_stage06_manifest(
    config: Stage07DesignDiagnosticConfig,
) -> dict[str, Any]:
    outcome = validate_stage06_bundle(
        config.stage06_output_directory,
        expected_manifest_sha256=config.expected_stage06_manifest_sha256,
        stage05_output_directory=config.stage05_output_directory,
        authoritative_development=config.authoritative_development,
        duckdb_memory_limit=config.duckdb_memory_limit,
        duckdb_threads=config.duckdb_threads,
    )
    if config.authoritative_development and (
        outcome.manifest_sha256 != ACCEPTED_STAGE06_MANIFEST_FINGERPRINT
        or outcome.schema_fingerprint != ACCEPTED_STAGE06_SCHEMA_FINGERPRINT
        or outcome.logical_dataset_sha256_v1 != ACCEPTED_STAGE06_LOGICAL_FINGERPRINT
        or outcome.input_binding_sha256 != ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT
        or outcome.unique_candidate_count != ACCEPTED_STAGE06_ROWS
        or outcome.row_count != ACCEPTED_SOURCE_ROWS
    ):
        _fail("STAGE06_BINDING_MISMATCH", "Accepted Stage 6 identity differs")
    return _load_json(config.stage06_output_directory / STAGE06_MANIFEST_NAME)


def _fixed_candidate_ids(config: Stage07DesignDiagnosticConfig) -> tuple[bytes, ...]:
    root = config.stage06_review_directory
    if not root.is_dir() or root.is_symlink():
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 directory is invalid")
    _require_mode(root, 0o700)
    manifest_path = root / "stage06_review_manifest.json"
    if (
        not manifest_path.is_file()
        or _sha256_file(manifest_path) != config.expected_stage06_review_manifest_sha256
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 manifest differs")
    _require_mode(manifest_path, 0o600)
    manifest = _load_json(manifest_path)
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if (
        manifest.get("status")
        != "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or not isinstance(scientific, dict)
        or scientific.get("review_subset_fingerprint") != ACCEPTED_FIXED_500_FINGERPRINT
        or not isinstance(physical, dict)
        or physical.get("stage06_manifest_sha256")
        != config.expected_stage06_manifest_sha256
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 identity differs")
    artifacts = physical.get("artifacts")
    if not isinstance(artifacts, list):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 artifacts are malformed")
    identity = next(
        (
            raw
            for raw in artifacts
            if isinstance(raw, dict) and raw.get("relative_path") == STAGE06_REVIEW_PATH
        ),
        None,
    )
    path = root / STAGE06_REVIEW_PATH
    if (
        not isinstance(identity, dict)
        or not path.is_file()
        or path.is_symlink()
        or path.stat().st_size != identity.get("size_bytes")
        or _sha256_file(path) != identity.get("sha256")
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 artifact differs")
    _require_mode(path, 0o600)
    try:
        table = pq.ParquetFile(path, page_checksum_verification=True).read(
            use_threads=False
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage07DesignDiagnosticError(
            "FIXED500_INVALID", "Stage 6 fixed-500 artifact could not be read"
        ) from error
    if (
        table.schema.remove_metadata() != stage06_review_schema()
        or table.num_rows != ACCEPTED_FIXED500_ROWS
        or table.column("review_order").to_pylist()
        != list(range(1, ACCEPTED_FIXED500_ROWS + 1))
        or any(
            not all(cast(list[bool], table.column(name).to_pylist()))
            for name in stage06_review_schema().names[5:11]
        )
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 rows differ")
    occurrences: list[bytes] = []
    for name in ROW_MAP_ID_COLUMNS:
        occurrences.extend(
            cast(bytes, value)
            for value in table.column(name).to_pylist()
            if value is not None
        )
    unique = tuple(sorted(set(occurrences)))
    if config.authoritative_development and (
        len(occurrences) != ACCEPTED_FIXED500_OCCURRENCES
        or len(unique) != ACCEPTED_FIXED500_UNIQUE_CANDIDATES
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 candidate counts differ")
    return unique


def _configure_duckdb(
    connection: duckdb.DuckDBPyConnection,
    *,
    memory_limit: str,
    threads: int,
    spill_directory: Path,
) -> None:
    connection.execute("SET enable_progress_bar = false")
    connection.execute("SET preserve_insertion_order = false")
    connection.execute("SET memory_limit = ?", [memory_limit])
    connection.execute("SET threads = ?", [threads])
    connection.execute("SET temp_directory = ?", [str(spill_directory)])


def _clean_surface_groups(
    row_map_paths: Sequence[Path],
    *,
    work_directory: Path,
    memory_limit: str,
    threads: int,
    authoritative_development: bool,
) -> dict[bytes, tuple[str, ...]]:
    database = work_directory / "clean_surfaces.duckdb"
    spill = work_directory / "duckdb_spill"
    spill.mkdir(mode=0o700)
    connection = duckdb.connect(str(database))
    database.chmod(0o600)
    try:
        _configure_duckdb(
            connection,
            memory_limit=memory_limit,
            threads=threads,
            spill_directory=spill,
        )
        connection.read_parquet([str(path) for path in row_map_paths]).create_view(
            "stage06_row_map"
        )
        reader = connection.execute(
            f"""
            WITH surfaces AS (
                SELECT
                    {ROW_MAP_ID_COLUMNS[0]} AS candidate_id,
                    stage05_standard_candidate_clean AS clean_surface
                FROM stage06_row_map
                WHERE {ROW_MAP_ID_COLUMNS[0]} IS NOT NULL
                UNION ALL
                SELECT
                    {ROW_MAP_ID_COLUMNS[1]} AS candidate_id,
                    stage05_native_candidate_clean AS clean_surface
                FROM stage06_row_map
                WHERE {ROW_MAP_ID_COLUMNS[1]} IS NOT NULL
            ), distinct_surfaces AS (
                SELECT DISTINCT candidate_id, clean_surface
                FROM surfaces
            ), variant_ids AS (
                SELECT candidate_id
                FROM distinct_surfaces
                GROUP BY candidate_id
                HAVING count(*) > 1
            )
            SELECT d.candidate_id, d.clean_surface
            FROM distinct_surfaces d
            JOIN variant_ids v USING (candidate_id)
            ORDER BY d.candidate_id, d.clean_surface
            """
        ).fetch_record_batch(rows_per_batch=128)
        grouped: dict[bytes, list[str]] = defaultdict(list)
        for batch in reader:
            for row_index in range(batch.num_rows):
                candidate_id = batch.column(0)[row_index].as_py()
                clean_surface = batch.column(1)[row_index].as_py()
                if not isinstance(candidate_id, bytes) or not isinstance(
                    clean_surface, str
                ):
                    _fail("CLEAN_VARIANT_INVALID", "Clean surface rows are malformed")
                grouped[candidate_id].append(clean_surface)
    except Stage07DesignDiagnosticError:
        raise
    except (OSError, duckdb.Error, pa.ArrowException) as error:
        raise Stage07DesignDiagnosticError(
            "CLEAN_VARIANT_FAILURE", "Clean variants could not be grouped"
        ) from error
    finally:
        connection.close()
    result = {key: tuple(values) for key, values in grouped.items()}
    if authoritative_development and (
        len(result) != ACCEPTED_CASE_VARIANT_GROUPS
        or sum(len(values) for values in result.values())
        != ACCEPTED_CASE_VARIANT_SURFACES
        or any(len(values) != 2 for values in result.values())
    ):
        _fail("CLEAN_VARIANT_INVALID", "Accepted clean-variant counts differ")
    return result


def _script_reference() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


def _length_bucket(length: int) -> str:
    if length <= 24:
        return "1_TO_24"
    if length <= 99:
        return "25_TO_99"
    if length <= 1_023:
        return "100_TO_1023"
    if length < GIANT_MINIMUM_CODEPOINTS:
        return "1024_TO_999999"
    return "1000000_OR_MORE"


def _script_bucket(value: str, reference: ScriptReference) -> str:
    if len(value) >= GIANT_MINIMUM_CODEPOINTS:
        return "GIANT_SEPARATE_SAFETY_CLASS"
    scripts = reference.distinctive_scripts(value)
    if not scripts:
        return "COMMON_OR_UNKNOWN_ONLY"
    if len(scripts) > 1:
        return "MIXED_SCRIPT"
    script = next(iter(scripts))
    return {
        "Latin": "LATIN",
        "Arabic": "ARABIC",
        "Cyrillic": "CYRILLIC",
        "Han": "HAN",
        "Hangul": "HANGUL",
    }.get(script, f"OTHER_{script.upper()}")


def _candidate_features(
    value: str,
    *,
    occurrence_count: int,
    standard_count: int,
    native_count: int,
    script_reference: ScriptReference,
) -> _CandidateFeatures:
    length = len(value)
    if standard_count and native_count:
        representation = "BOTH"
    elif standard_count:
        representation = "STANDARD_ONLY"
    elif native_count:
        representation = "NATIVE_ONLY"
    else:
        representation = "INVALID"
    numeric = 0
    punctuation = 0
    if length < GIANT_MINIMUM_CODEPOINTS:
        for character in value:
            category = unicodedata.category(character)
            numeric += category.startswith("N")
            punctuation += category.startswith("P") or category.startswith("S")
    return _CandidateFeatures(
        length_bucket=_length_bucket(length),
        script_bucket=_script_bucket(value, script_reference),
        representation_bucket=representation,
        occurrence_bucket="REPEATED" if occurrence_count > 1 else "SINGLETON",
        numeric_heavy=bool(length and numeric * 2 >= length),
        punctuation_heavy=bool(length and punctuation * 5 >= length),
        giant=length >= GIANT_MINIMUM_CODEPOINTS,
    )


def _bounded_add(bucket: list[bytes], candidate_id: bytes, maximum: int) -> None:
    bucket.append(candidate_id)
    bucket.sort()
    if len(bucket) > maximum:
        bucket.pop()


def _iter_registry(
    registry_paths: Sequence[Path], *, batch_rows: int = 64
) -> Iterable[pa.RecordBatch]:
    try:
        for path in registry_paths:
            parquet = pq.ParquetFile(path, page_checksum_verification=True)
            yield from parquet.iter_batches(
                batch_size=batch_rows, columns=list(REGISTRY_COLUMNS), use_threads=False
            )
    except (OSError, pa.ArrowException) as error:
        raise Stage07DesignDiagnosticError(
            "REGISTRY_READ_FAILURE", "Stage 6 registry could not be streamed"
        ) from error


def _diagnostic_selection(
    registry_paths: Sequence[Path],
    *,
    fixed_ids: Sequence[bytes],
    case_ids: Sequence[bytes],
    script_reference: ScriptReference,
    authoritative_development: bool,
) -> tuple[set[bytes], set[bytes], dict[str, int], str]:
    buckets: dict[str, list[bytes]] = defaultdict(list)
    stratum_available: Counter[str] = Counter()
    giant_ids: set[bytes] = set()
    observed_rows = 0
    maximum_length = 0
    for batch in _iter_registry(registry_paths):
        for row_index in range(batch.num_rows):
            candidate_id = batch.column(0)[row_index].as_py()
            candidate = batch.column(1)[row_index].as_py()
            occurrence_count = int(batch.column(2)[row_index].as_py())
            standard_count = int(batch.column(3)[row_index].as_py())
            native_count = int(batch.column(4)[row_index].as_py())
            if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
                _fail("REGISTRY_INVALID", "Stage 6 registry row is malformed")
            features = _candidate_features(
                candidate,
                occurrence_count=occurrence_count,
                standard_count=standard_count,
                native_count=native_count,
                script_reference=script_reference,
            )
            observed_rows += 1
            maximum_length = max(maximum_length, len(candidate))
            if features.giant:
                giant_ids.add(candidate_id)
            for reason in features.reasons():
                stratum_available[reason] += 1
                _bounded_add(buckets[reason], candidate_id, _SAMPLE_PER_STRATUM)
            _bounded_add(
                buckets["ORDINARY_HASH_BASELINE"], candidate_id, _ORDINARY_SAMPLE_COUNT
            )
    sampled = {candidate_id for values in buckets.values() for candidate_id in values}
    selected = set(fixed_ids) | set(case_ids) | giant_ids | sampled
    if authoritative_development and (
        observed_rows != ACCEPTED_STAGE06_ROWS
        or len(giant_ids) != ACCEPTED_GIANT_CANDIDATES
        or maximum_length != ACCEPTED_MAXIMUM_CODEPOINTS
    ):
        _fail("REGISTRY_INVALID", "Accepted Stage 6 diagnostic selection differs")
    digest = hashlib.sha256(STAGE07_DESIGN_SELECTION_DOMAIN)
    for candidate_id in sorted(selected):
        digest.update(len(candidate_id).to_bytes(8, "big"))
        digest.update(candidate_id)
    return (
        selected,
        giant_ids,
        dict(sorted(stratum_available.items())),
        digest.hexdigest(),
    )


def _isolated_parse_child(
    candidate: str, send_connection: Any, address_space_bytes: int
) -> None:
    try:
        resource.setrlimit(
            resource.RLIMIT_AS, (address_space_bytes, address_space_bytes)
        )
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)
        input_encoded = candidate.encode("utf-8", errors="strict")
        parser = PypostalParser()
        started = time.perf_counter()
        result = parser.parse(candidate)
        elapsed = time.perf_counter() - started
        label_counts = Counter(component.label for component in result.components)
        send_connection.send(
            {
                "ok": True,
                "failure": "",
                "status": result.status,
                "component_count": len(result.components),
                "label_counts": dict(label_counts),
                "output_codepoints": sum(
                    len(component.value) for component in result.components
                ),
                "elapsed_seconds": elapsed,
                "ordered_parse_sha256": ordered_parse_sha256(result),
                "input_codepoints": len(candidate),
                "input_sha256": hashlib.sha256(input_encoded).hexdigest(),
            }
        )
    except Exception:
        try:
            send_connection.send(
                {
                    "ok": False,
                    "failure": "PARSER_EXCEPTION",
                    "status": "",
                    "component_count": 0,
                    "label_counts": {},
                    "output_codepoints": 0,
                    "elapsed_seconds": 0.0,
                    "ordered_parse_sha256": "",
                    "input_codepoints": 0,
                    "input_sha256": "",
                }
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        send_connection.close()


def _isolated_parse(
    candidate: str, *, timeout_seconds: int, address_space_bytes: int
) -> _IsolatedParseResult:
    expected_sha = hashlib.sha256(
        candidate.encode("utf-8", errors="strict")
    ).hexdigest()
    context = multiprocessing.get_context("fork")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_isolated_parse_child,
        args=(candidate, send, address_space_bytes),
    )
    process.start()
    send.close()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(30)
        receive.close()
        return _IsolatedParseResult(
            False, "TIMEOUT", "", 0, {}, 0, float(timeout_seconds), "", 0, ""
        )
    payload: dict[str, Any] | None = None
    if receive.poll():
        payload = cast(dict[str, Any], receive.recv())
    receive.close()
    if process.exitcode != 0 or payload is None:
        return _IsolatedParseResult(
            False, "PROCESS_CRASH", "", 0, {}, 0, 0.0, "", 0, ""
        )
    result = _IsolatedParseResult(
        ok=bool(payload["ok"]),
        failure=str(payload["failure"]),
        status=str(payload["status"]),
        component_count=int(payload["component_count"]),
        label_counts=cast(dict[str, int], payload["label_counts"]),
        output_codepoints=int(payload["output_codepoints"]),
        elapsed_seconds=float(payload["elapsed_seconds"]),
        ordered_parse_sha256=str(payload["ordered_parse_sha256"]),
        input_codepoints=int(payload["input_codepoints"]),
        input_sha256=str(payload["input_sha256"]),
    )
    if result.ok and (
        result.input_codepoints != len(candidate) or result.input_sha256 != expected_sha
    ):
        return _IsolatedParseResult(
            False, "INPUT_MISMATCH", "", 0, {}, 0, 0.0, "", 0, ""
        )
    return result


def _fresh_process_child(
    candidates: Sequence[str], batch_rows: int, send_connection: Any
) -> None:
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        os.close(devnull)
        parser = PypostalParser()
        digests: list[str] = []
        for offset in range(0, len(candidates), batch_rows):
            for candidate in candidates[offset : offset + batch_rows]:
                digests.append(ordered_parse_sha256(parser.parse(candidate)))
        send_connection.send(
            {
                "ok": True,
                "digests": digests,
                "initialization_seconds": parser.initialization_seconds,
            }
        )
    except Exception:
        try:
            send_connection.send(
                {"ok": False, "digests": [], "initialization_seconds": 0.0}
            )
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        send_connection.close()


def _fresh_process_digests(
    candidates: Sequence[str], *, batch_rows: int, timeout_seconds: int
) -> tuple[list[str], float, str]:
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_fresh_process_child, args=(list(candidates), batch_rows, send)
    )
    process.start()
    send.close()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(30)
        receive.close()
        return [], 0.0, "TIMEOUT"
    payload: dict[str, Any] | None = None
    if receive.poll():
        payload = cast(dict[str, Any], receive.recv())
    receive.close()
    if process.exitcode != 0 or payload is None or payload.get("ok") is not True:
        return [], 0.0, "PROCESS_FAILURE"
    return (
        cast(list[str], payload["digests"]),
        float(payload["initialization_seconds"]),
        "PASS",
    )


def _difference_types(
    canonical: ParsedAddress, surface: ParsedAddress
) -> frozenset[str]:
    if canonical == surface:
        return frozenset()
    differences: set[str] = set()
    if bool(canonical.components) != bool(surface.components):
        differences.add("EMPTY_NONEMPTY_DIFFERENCE")
    if len(canonical.components) != len(surface.components):
        differences.add("COMPONENT_COUNT_DIFFERENCE")
    canonical_labels = tuple(component.label for component in canonical.components)
    surface_labels = tuple(component.label for component in surface.components)
    canonical_values = tuple(component.value for component in canonical.components)
    surface_values = tuple(component.value for component in surface.components)
    if canonical_labels != surface_labels:
        differences.add("LABEL_DIFFERENCE")
    if canonical_values != surface_values:
        differences.add("VALUE_DIFFERENCE")
    canonical_pairs = Counter(
        (component.label, component.value) for component in canonical.components
    )
    surface_pairs = Counter(
        (component.label, component.value) for component in surface.components
    )
    if canonical_pairs == surface_pairs:
        differences.add("ORDERING_DIFFERENCE")
    return frozenset(differences)


def _nearest_rank(values: Sequence[int], numerator: int, denominator: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, (len(ordered) * numerator + denominator - 1) // denominator - 1)
    return ordered[index]


def _distribution(values: Sequence[int]) -> dict[str, int | float]:
    if not values:
        return {key: 0 for key in ("min", "median", "mean", "p95", "p99", "max")}
    return {
        "min": min(values),
        "median": _nearest_rank(values, 50, 100),
        "mean": round(sum(values) / len(values), 6),
        "p95": _nearest_rank(values, 95, 100),
        "p99": _nearest_rank(values, 99, 100),
        "max": max(values),
    }


def _write_json(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_stage07_design_diagnostic(
    config: Stage07DesignDiagnosticConfig,
) -> Stage07DesignDiagnosticOutcome:
    """Run the aggregate-only protected parser design gate."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-libpostal-design-diagnostic")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output already exists")

    total_started = time.perf_counter()
    bundle = validate_parser_bundle(
        config.parser_bundle_directory,
        expected_parser_bundle_fingerprint=config.expected_parser_bundle_fingerprint,
    )
    stage06_manifest = _validated_stage06_manifest(config)
    row_map_paths = _artifact_paths(
        config.stage06_output_directory,
        stage06_manifest,
        "row_map_artifacts",
        _ROW_MAP_DIRECTORY,
    )
    registry_paths = _artifact_paths(
        config.stage06_output_directory,
        stage06_manifest,
        "registry_artifacts",
        _REGISTRY_DIRECTORY,
    )
    fixed_ids = _fixed_candidate_ids(config)

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    _require_mode(parent, 0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic temporary output already exists")
    temporary.mkdir(mode=0o700)
    work = temporary / "work"
    work.mkdir(mode=0o700)

    case_surfaces = _clean_surface_groups(
        row_map_paths,
        work_directory=work,
        memory_limit=config.duckdb_memory_limit,
        threads=config.duckdb_threads,
        authoritative_development=config.authoritative_development,
    )
    scripts = _script_reference()
    selected, giant_ids, strata_available, selection_fingerprint = (
        _diagnostic_selection(
            registry_paths,
            fixed_ids=fixed_ids,
            case_ids=tuple(case_surfaces),
            script_reference=scripts,
            authoritative_development=config.authoritative_development,
        )
    )

    giant_results: list[_IsolatedParseResult] = []
    giant_result_by_id: dict[bytes, _IsolatedParseResult] = {}
    maximum_giant_result: _IsolatedParseResult | None = None
    giant_started = time.perf_counter()
    observed_giant_ids: set[bytes] = set()
    giant_features: dict[bytes, _CandidateFeatures] = {}
    for batch in _iter_registry(registry_paths):
        for row_index in range(batch.num_rows):
            candidate_id = batch.column(0)[row_index].as_py()
            if candidate_id not in giant_ids:
                continue
            candidate = batch.column(1)[row_index].as_py()
            occurrence_count = int(batch.column(2)[row_index].as_py())
            standard_count = int(batch.column(3)[row_index].as_py())
            native_count = int(batch.column(4)[row_index].as_py())
            if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
                _fail("REGISTRY_INVALID", "Giant registry row is malformed")
            giant_features[candidate_id] = _candidate_features(
                candidate,
                occurrence_count=occurrence_count,
                standard_count=standard_count,
                native_count=native_count,
                script_reference=scripts,
            )
            giant_result = _isolated_parse(
                candidate,
                timeout_seconds=config.giant_timeout_seconds,
                address_space_bytes=config.giant_address_space_bytes,
            )
            giant_results.append(giant_result)
            giant_result_by_id[candidate_id] = giant_result
            observed_giant_ids.add(candidate_id)
            if len(candidate) == ACCEPTED_MAXIMUM_CODEPOINTS:
                maximum_giant_result = giant_result
    giant_elapsed = time.perf_counter() - giant_started
    if observed_giant_ids != giant_ids:
        _fail("GIANT_CANDIDATE_MISMATCH", "A giant candidate was not resolved")

    parser = PypostalParser()
    canonical_results: dict[bytes, ParsedAddress] = {}
    deterministic_candidates: dict[bytes, str] = {}
    component_counts: list[int] = []
    output_codepoints: list[int] = []
    label_frequencies: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    repeated_label_candidates = 0
    maximum_label_repetition = 0
    parse_errors = 0
    parse_seconds = 0.0
    script_stats: dict[str, Counter[str]] = defaultdict(Counter)
    length_stats: dict[str, Counter[str]] = defaultdict(Counter)
    representation_stats: dict[str, Counter[str]] = defaultdict(Counter)
    observed_selected: set[bytes] = set()
    for batch in _iter_registry(registry_paths):
        for row_index in range(batch.num_rows):
            candidate_id = batch.column(0)[row_index].as_py()
            if candidate_id not in selected or candidate_id in giant_ids:
                continue
            candidate = batch.column(1)[row_index].as_py()
            occurrence_count = int(batch.column(2)[row_index].as_py())
            standard_count = int(batch.column(3)[row_index].as_py())
            native_count = int(batch.column(4)[row_index].as_py())
            if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
                _fail("REGISTRY_INVALID", "Selected registry row is malformed")
            features = _candidate_features(
                candidate,
                occurrence_count=occurrence_count,
                standard_count=standard_count,
                native_count=native_count,
                script_reference=scripts,
            )
            started = time.perf_counter()
            try:
                parsed = parser.parse(candidate)
            except Stage07ParserError:
                parse_errors += 1
                observed_selected.add(candidate_id)
                continue
            parse_seconds += time.perf_counter() - started
            canonical_results[candidate_id] = parsed
            observed_selected.add(candidate_id)
            if len(deterministic_candidates) < _DETERMINISM_SAMPLE_COUNT:
                deterministic_candidates[candidate_id] = candidate
            count = len(parsed.components)
            component_counts.append(count)
            output_codepoints.append(sum(len(item.value) for item in parsed.components))
            labels = Counter(item.label for item in parsed.components)
            label_frequencies.update(labels)
            maximum_label_repetition = max(
                maximum_label_repetition, max(labels.values(), default=0)
            )
            repeated_label_candidates += int(
                any(value > 1 for value in labels.values())
            )
            status_counts[parsed.status] += 1
            for bucket, stats in (
                (features.script_bucket, script_stats),
                (features.length_bucket, length_stats),
                (features.representation_bucket, representation_stats),
            ):
                stats[bucket]["CANDIDATES"] += 1
                stats[bucket][parsed.status] += 1
                stats[bucket]["COMPONENTS"] += count

    if observed_selected != selected - giant_ids:
        _fail("DIAGNOSTIC_SELECTION_MISMATCH", "A selected candidate was not resolved")

    for candidate_id in sorted(observed_giant_ids):
        giant_result = giant_result_by_id[candidate_id]
        if not giant_result.ok:
            parse_errors += 1
            continue
        status_counts[giant_result.status] += 1
        component_counts.append(giant_result.component_count)
        output_codepoints.append(giant_result.output_codepoints)
        label_frequencies.update(giant_result.label_counts)
        maximum_label_repetition = max(
            maximum_label_repetition,
            max(giant_result.label_counts.values(), default=0),
        )
        repeated_label_candidates += int(
            any(value > 1 for value in giant_result.label_counts.values())
        )
        script_stats["GIANT_SEPARATE_SAFETY_CLASS"]["CANDIDATES"] += 1
        script_stats["GIANT_SEPARATE_SAFETY_CLASS"][giant_result.status] += 1
        script_stats["GIANT_SEPARATE_SAFETY_CLASS"]["COMPONENTS"] += (
            giant_result.component_count
        )
        length_stats["1000000_OR_MORE"]["CANDIDATES"] += 1
        length_stats["1000000_OR_MORE"][giant_result.status] += 1
        length_stats["1000000_OR_MORE"]["COMPONENTS"] += giant_result.component_count
        representation = giant_features[candidate_id].representation_bucket
        representation_stats[representation]["CANDIDATES"] += 1
        representation_stats[representation][giant_result.status] += 1
        representation_stats[representation]["COMPONENTS"] += (
            giant_result.component_count
        )

    difference_type_groups: Counter[str] = Counter()
    groups_equal = 0
    groups_different = 0
    case_surface_errors = 0
    for candidate_id, surfaces in case_surfaces.items():
        canonical = canonical_results.get(candidate_id)
        if canonical is None:
            case_surface_errors += len(surfaces)
            groups_different += 1
            continue
        group_differences: set[str] = set()
        for surface in surfaces:
            try:
                surface_result = parser.parse(surface)
            except Stage07ParserError:
                case_surface_errors += 1
                group_differences.add("PARSER_ERROR_DIFFERENCE")
                continue
            group_differences.update(_difference_types(canonical, surface_result))
        if group_differences:
            groups_different += 1
            difference_type_groups.update(group_differences)
        else:
            groups_equal += 1

    deterministic_ids = sorted(deterministic_candidates)[:_DETERMINISM_SAMPLE_COUNT]
    deterministic_values = [
        deterministic_candidates[value] for value in deterministic_ids
    ]
    baseline_digests = [
        ordered_parse_sha256(canonical_results[candidate_id])
        for candidate_id in deterministic_ids
    ]
    same_process_digests: list[str] = []
    for candidate in deterministic_values:
        try:
            same_process_digests.append(ordered_parse_sha256(parser.parse(candidate)))
        except Stage07ParserError:
            same_process_digests.append("")
    fresh_one, fresh_one_init, fresh_one_status = _fresh_process_digests(
        deterministic_values,
        batch_rows=1,
        timeout_seconds=config.fresh_process_timeout_seconds,
    )
    reversed_values = list(reversed(deterministic_values))
    fresh_many_reversed, fresh_many_init, fresh_many_status = _fresh_process_digests(
        reversed_values,
        batch_rows=17,
        timeout_seconds=config.fresh_process_timeout_seconds,
    )
    fresh_many = list(reversed(fresh_many_reversed))
    same_process_mismatches = sum(
        left != right
        for left, right in zip(baseline_digests, same_process_digests, strict=True)
    )
    fresh_one_mismatches = (
        sum(
            left != right
            for left, right in zip(baseline_digests, fresh_one, strict=True)
        )
        if len(fresh_one) == len(baseline_digests)
        else len(baseline_digests)
    )
    fresh_many_mismatches = (
        sum(
            left != right
            for left, right in zip(baseline_digests, fresh_many, strict=True)
        )
        if len(fresh_many) == len(baseline_digests)
        else len(baseline_digests)
    )

    giant_failures = Counter(result.failure or "PASS" for result in giant_results)
    giant_successes = sum(result.ok for result in giant_results)
    maximum_result_payload = {
        "status": maximum_giant_result.status if maximum_giant_result else "MISSING",
        "success": bool(maximum_giant_result and maximum_giant_result.ok),
        "runtime_seconds": round(
            maximum_giant_result.elapsed_seconds if maximum_giant_result else 0.0, 6
        ),
        "component_count": (
            maximum_giant_result.component_count if maximum_giant_result else 0
        ),
        "input_codepoints": ACCEPTED_MAXIMUM_CODEPOINTS,
        "exact_full_input_verified": bool(
            maximum_giant_result
            and maximum_giant_result.ok
            and maximum_giant_result.input_codepoints == ACCEPTED_MAXIMUM_CODEPOINTS
        ),
    }
    determinism_mismatches = (
        same_process_mismatches + fresh_one_mismatches + fresh_many_mismatches
    )
    scientific_conflicts: list[str] = []
    if groups_different or case_surface_errors:
        scientific_conflicts.append("LOWERCASE_PARSE_ONCE_CASE_VARIANT_CONFLICT")
    if giant_successes != len(giant_results):
        scientific_conflicts.append("GIANT_CANDIDATE_PARSER_LIMITATION")
    if parse_errors:
        scientific_conflicts.append("PROTECTED_CANDIDATE_PARSER_FAILURE")
    if (
        determinism_mismatches
        or fresh_one_status != "PASS"
        or fresh_many_status != "PASS"
    ):
        scientific_conflicts.append("PARSER_NONDETERMINISM")
    if (
        status_counts[PARSED_NONEMPTY] + status_counts[PARSED_EMPTY]
        != len(selected) - parse_errors
    ):
        scientific_conflicts.append("PARSER_STATUS_RECONCILIATION_FAILURE")
    gate_result = "PASS" if not scientific_conflicts else "SCIENTIFIC_CONFLICT"

    shutil.rmtree(work)
    total_seconds = time.perf_counter() - total_started
    payload: dict[str, object] = {
        "stage07_design_diagnostic_version": STAGE07_DESIGN_DIAGNOSTIC_VERSION,
        "status": "STAGE07_DESIGN_DIAGNOSTIC_COMPLETE",
        "gate_result": gate_result,
        "scientific_conflicts": scientific_conflicts,
        "privacy": "AGGREGATE_ONLY_NO_PROTECTED_VALUES",
        "parser_bundle": {
            "parser_bundle_fingerprint": bundle.parser_bundle_fingerprint,
            "parser_model_data_fingerprint": bundle.parser_model_data_fingerprint,
            "pypostal_runtime_fingerprint": bundle.pypostal_runtime_fingerprint,
            "libpostal_shared_library_sha256": bundle.libpostal_shared_library_sha256,
            "parser_bundle_manifest_sha256": bundle.manifest_sha256,
        },
        "input_binding": {
            "stage06_contract": ACCEPTED_STAGE06_CONTRACT,
            "stage06_profile": ACCEPTED_STAGE06_PROFILE,
            "stage06_schema_fingerprint": ACCEPTED_STAGE06_SCHEMA_FINGERPRINT,
            "stage06_logical_fingerprint": ACCEPTED_STAGE06_LOGICAL_FINGERPRINT,
            "stage06_input_binding_fingerprint": (
                ACCEPTED_STAGE06_INPUT_BINDING_FINGERPRINT
            ),
            "stage06_manifest_fingerprint": ACCEPTED_STAGE06_MANIFEST_FINGERPRINT,
            "benchmark_fingerprint": ACCEPTED_BENCHMARK_FINGERPRINT,
            "fixed_500_fingerprint": ACCEPTED_FIXED_500_FINGERPRINT,
            "stage06_registry_rows": ACCEPTED_STAGE06_ROWS,
            "source_rows": ACCEPTED_SOURCE_ROWS,
            "occurrences": ACCEPTED_OCCURRENCES,
            "standard_occurrences": ACCEPTED_STANDARD_OCCURRENCES,
            "native_occurrences": ACCEPTED_NATIVE_OCCURRENCES,
        },
        "selection": {
            "diagnostic_unique_candidates": len(selected),
            "selection_fingerprint": selection_fingerprint,
            "fixed500_unique_candidates": len(fixed_ids),
            "clean_variant_canonical_candidates": len(case_surfaces),
            "giant_candidates": len(giant_ids),
            "stratum_available_counts": strata_available,
            "sample_per_stratum": _SAMPLE_PER_STRATUM,
            "ordinary_hash_sample": _ORDINARY_SAMPLE_COUNT,
        },
        "parse_metrics": {
            "parser_initialization_seconds": round(parser.initialization_seconds, 6),
            "canonical_parse_seconds_excluding_giants": round(parse_seconds, 6),
            "giant_parse_elapsed_seconds": round(giant_elapsed, 6),
            "total_diagnostic_seconds": round(total_seconds, 6),
            "candidates_per_second_excluding_initialization": round(
                (len(selected) - len(giant_ids)) / parse_seconds, 6
            )
            if parse_seconds
            else 0.0,
            "statuses": dict(sorted(status_counts.items())),
            "parser_errors": parse_errors,
            "component_count_distribution": _distribution(component_counts),
            "component_count_frequency": dict(
                sorted(Counter(component_counts).items())
            ),
            "output_value_codepoint_distribution": _distribution(output_codepoints),
            "label_vocabulary": sorted(label_frequencies),
            "label_frequencies": dict(sorted(label_frequencies.items())),
            "repeated_label_candidates": repeated_label_candidates,
            "maximum_same_label_repetition": maximum_label_repetition,
            "one_component_candidates": component_counts.count(1),
            "many_component_candidates_ge_8": sum(
                value >= 8 for value in component_counts
            ),
            "script_stratified": {
                key: dict(sorted(value.items()))
                for key, value in sorted(script_stats.items())
            },
            "length_stratified": {
                key: dict(sorted(value.items()))
                for key, value in sorted(length_stats.items())
            },
            "representation_stratified": {
                key: dict(sorted(value.items()))
                for key, value in sorted(representation_stats.items())
            },
        },
        "clean_variant_safety": {
            "groups_tested": len(case_surfaces),
            "clean_surfaces_tested": sum(
                len(values) for values in case_surfaces.values()
            ),
            "groups_with_exact_parse_equality": groups_equal,
            "groups_with_parse_differences": groups_different,
            "parser_errors": case_surface_errors,
            "difference_type_group_counts": dict(
                sorted(difference_type_groups.items())
            ),
            "lowercase_parse_once_safe": groups_different == 0
            and case_surface_errors == 0,
        },
        "giant_safety": {
            "candidates_tested": len(giant_results),
            "successful": giant_successes,
            "failure_counts": dict(sorted(giant_failures.items())),
            "timeout_seconds_per_candidate": config.giant_timeout_seconds,
            "address_space_bytes_per_candidate": config.giant_address_space_bytes,
            "safe_truncation_applied": False,
            "substring_parse_applied": False,
            "maximum_candidate": maximum_result_payload,
        },
        "determinism": {
            "candidates_tested": len(deterministic_values),
            "same_process_mismatches": same_process_mismatches,
            "fresh_process_batch1_mismatches": fresh_one_mismatches,
            "fresh_process_batch17_reversed_mismatches": fresh_many_mismatches,
            "fresh_process_batch1_status": fresh_one_status,
            "fresh_process_batch17_status": fresh_many_status,
            "fresh_process_initialization_seconds": [
                round(fresh_one_init, 6),
                round(fresh_many_init, 6),
            ],
            "worker_policy": "SINGLE_PROCESS_DEVELOPMENT",
            "concurrent_worker_invariance": "NOT_APPLICABLE_NO_CONCURRENCY_USED",
        },
        "scope": {
            "holdout_accessed": False,
            "production_stage02_started": False,
            "production_stage03_started": False,
            "production_stage04_started": False,
            "production_stage05_started": False,
            "production_stage06_started": False,
            "production_stage07_started": False,
            "stage08_started": False,
            "geocoding_performed": False,
            "external_service_used_for_protected_data": False,
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "created_at_utc": _utc_now(),
        },
    }
    diagnostic_path = temporary / STAGE07_DESIGN_DIAGNOSTIC_NAME
    _write_json(diagnostic_path, payload)
    diagnostic_sha = _sha256_file(diagnostic_path)
    _write_json(
        temporary / STAGE07_DESIGN_SUCCESS_NAME,
        {
            "status": "STAGE07_DESIGN_DIAGNOSTIC_COMPLETE",
            "gate_result": gate_result,
            "diagnostic_sha256": diagnostic_sha,
            "parser_bundle_fingerprint": bundle.parser_bundle_fingerprint,
            "diagnostic_unique_candidates": len(selected),
        },
    )
    for path in temporary.iterdir():
        if path.is_file():
            _require_mode(path, 0o600)
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return Stage07DesignDiagnosticOutcome(
        output_directory=config.output_directory,
        diagnostic_sha256=diagnostic_sha,
        parser_bundle_fingerprint=bundle.parser_bundle_fingerprint,
        diagnostic_candidate_count=len(selected),
        gate_result=gate_result,
    )


__all__ = [
    "Stage07DesignDiagnosticConfig",
    "Stage07DesignDiagnosticError",
    "Stage07DesignDiagnosticOutcome",
    "run_stage07_design_diagnostic",
]

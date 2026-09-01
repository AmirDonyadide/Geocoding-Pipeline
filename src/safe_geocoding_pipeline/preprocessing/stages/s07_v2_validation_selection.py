"""Freeze the Stage 7 v2 fixed-frame validation selection.

This protected diagnostic applies the already-frozen component-readiness rule
to the 604 semantically untouched candidates projected from the immutable
fixed-500 source-row frame.  It is machine-only: candidate/component values
are used solely by the deterministic rule and are never printed or placed in
Git-safe evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, NoReturn, cast

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..reporting.stage06 import stage06_review_schema
from ..script_reference import ScriptReference, unicode_script_reference_paths
from .s06_exact_deduplication import REGISTRY_COLUMNS
from .s07_component_readiness import (
    COMPONENTS_ABSTAIN,
    COMPONENTS_READY,
    NOT_ASSESSED,
    NOT_ATTEMPTED_NOT_ELIGIBLE,
    READINESS_RULE_VERSION,
    REASON_ORDER,
    decide_component_readiness,
)
from .s07_country_eligibility import PARSER_ELIGIBLE_COUNTRY
from .s07_libpostal_adapter import LibpostalComponent
from .s07_output_schema import STAGE07_COMPONENTS_FIELD, STAGE07_STATUS_FIELD
from .s07_parsing import (
    ACCEPTED_PARSER_BUNDLE_FINGERPRINT,
    ACCEPTED_STAGE06_REGISTRY_ROWS,
    STAGE07_CONTRACT_VERSION,
    STAGE07_MANIFEST_NAME,
    STAGE07_MANIFEST_VERSION,
    STAGE07_PROFILE_VERSION,
    STAGE07_STATUS_VOCABULARY,
    _manifest_artifacts,
)
from .s07_quality_root_cause import SELECTION_FINGERPRINT, _selection_fingerprint
from .s07_v2_readiness_audit import (
    ELIGIBILITY_ARTIFACT_SHA256,
    EXPECTED_FIXED_CANDIDATES,
    EXPECTED_FIXED_OCCURRENCES,
    EXPECTED_FIXED_ROWS,
    SELECTION_ARTIFACT_SHA256,
    STAGE06_FIXED_SHA256,
    _candidate_id_fingerprint,
    _fixed_candidate_ids,
)


VALIDATION_FREEZE_VERSION = "stage07_v2_validation_selection_freeze_v1"
SELECTION_CONTRACT_VERSION = "stage07_component_readiness_validation_selection_v1"
EXPECTED_EXISTING_SELECTION_ROWS = 120
EXPECTED_UNTOUCHED_CANDIDATES = 604
TARGET_SAMPLE_SIZE = 240
TARGET_READY = 120
TARGET_ABSTAIN = 120
FROZEN_READINESS_RULE_SOURCE_SHA256 = (
    "dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9"
)
FIXED500_CANDIDATE_SET_FINGERPRINT = (
    "8834a191efe0a77c5ace78760bd131e2c11bd904097b47e5ba1177f4172a5696"
)

COUNTRY_FREQUENCY_BANDS = (
    "COUNTRY_SINGLETON",
    "COUNTRY_LOW_2_TO_4",
    "COUNTRY_MEDIUM_5_TO_14",
    "COUNTRY_HIGH_15_OR_MORE",
)
REPRESENTATION_ORDER = ("STANDARD_ONLY", "NATIVE_ONLY", "BOTH")

SELECTION_ALGORITHM: Mapping[str, object] = {
    "version": SELECTION_CONTRACT_VERSION,
    "population": "604_UNTOUCHED_FIXED500_CANDIDATES",
    "semantic_sample_excludes": [NOT_ASSESSED],
    "arm_targets": {
        COMPONENTS_READY: TARGET_READY,
        COMPONENTS_ABSTAIN: TARGET_ABSTAIN,
    },
    "short_arm_transfer": (
        "TAKE_COMPLETE_SHORT_ARM_AND_TRANSFER_UNUSED_CAPACITY_TO_OTHER_ARM"
    ),
    "abstain_phase_addition_budgets_at_120": {
        "reason_code_round_robin": 40,
        "script_round_robin": 24,
        "representation_round_robin": 18,
        "country_frequency_band_round_robin": 18,
        "country_diversity_then_global_hash_fill": 20,
    },
    "ready_phase_addition_budgets_at_120": {
        "script_round_robin": 36,
        "representation_round_robin": 30,
        "country_frequency_band_round_robin": 24,
        "country_diversity_then_global_hash_fill": 30,
    },
    "smaller_arm_budget_scaling": "INTEGER_FLOOR_PROPORTIONAL_TO_ARM_TARGET",
    "category_order": {
        "reason": list(REASON_ORDER),
        "script": "LEXICOGRAPHIC",
        "representation": list(REPRESENTATION_ORDER),
        "country_frequency_band": list(COUNTRY_FREQUENCY_BANDS),
        "country": "DOMAIN_SEPARATED_SHA256_OF_COUNTRY_CODE",
    },
    "candidate_tie_break": "DOMAIN_SEPARATED_SHA256_OF_CANDIDATE_ID",
    "review_order": "DOMAIN_SEPARATED_SHA256_OF_CANDIDATE_ID",
    "candidate_text_in_rank": False,
    "parser_values_in_rank": False,
}

VALIDATION_THRESHOLDS: Mapping[str, object] = {
    "READY_PRECISION_MINIMUM_PERCENT": 95.0,
    "CLEAR_MISPARSE_READY_LEAKAGE_MAXIMUM_PERCENT": 2.5,
    "CLEAR_MISPARSE_READY_LEAKAGE_MAXIMUM_COUNT": 2,
    "STRUCTURAL_REASON_REPLAY_EXACT": True,
    "USABLE_ABSTENTION_RATE_MAXIMUM_PERCENT": 40.0,
    "ELIGIBLE_FRAME_ABSTENTION_COVERAGE_MINIMUM_PERCENT": 10.0,
    "ELIGIBLE_FRAME_ABSTENTION_COVERAGE_MAXIMUM_PERCENT": 70.0,
    "MINIMUM_ASSESSABLE_FOR_STRATUM_PASS_FAIL": 20,
    "UNASSESSABLE_EXCLUDED_FROM_PRIMARY_DENOMINATORS": True,
    "THRESHOLD_TUNING_AFTER_LABELS": False,
}

_SELECTION_DOMAIN = b"SAFE_STAGE07_V2_VALIDATION_SELECTION_V1"
_UNTOUCHED_DOMAIN = b"SAFE_STAGE07_V2_UNTOUCHED_FIXED500_CANDIDATES_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Stage07V2ValidationSelectionError(RuntimeError):
    """Fail-closed, privacy-safe validation-selection error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07V2ValidationSelectionError(code, detail)


@dataclass(frozen=True, slots=True)
class ValidationSelectionConfig:
    stage06_fixed500_path: Path
    existing_selection_path: Path
    eligibility_path: Path
    stage07_output_directory: Path
    expected_stage07_manifest_sha256: str
    output_directory: Path
    execution_git_sha: str
    expected_stage06_fixed_sha256: str = STAGE06_FIXED_SHA256
    expected_existing_selection_sha256: str = SELECTION_ARTIFACT_SHA256
    expected_eligibility_sha256: str = ELIGIBILITY_ARTIFACT_SHA256
    expected_fixed_candidates: int = EXPECTED_FIXED_CANDIDATES
    expected_fixed_occurrences: int = EXPECTED_FIXED_OCCURRENCES
    expected_untouched_candidates: int = EXPECTED_UNTOUCHED_CANDIDATES
    expected_stage07_rows: int = ACCEPTED_STAGE06_REGISTRY_ROWS
    authoritative_development: bool = True

    def validate(self) -> None:
        for value in (
            self.expected_stage07_manifest_sha256,
            self.expected_stage06_fixed_sha256,
            self.expected_existing_selection_sha256,
            self.expected_eligibility_sha256,
        ):
            if _SHA256_RE.fullmatch(value) is None:
                _fail("INVALID_FINGERPRINT", "A configured fingerprint is malformed")
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_SHA", "Execution Git SHA is malformed")
        for count in (
            self.expected_fixed_candidates,
            self.expected_fixed_occurrences,
            self.expected_untouched_candidates,
            self.expected_stage07_rows,
        ):
            if isinstance(count, bool) or count < 1:
                _fail("INVALID_EXPECTATION", "A configured row count is invalid")
        paths = (
            self.stage06_fixed500_path,
            self.existing_selection_path,
            self.eligibility_path,
            self.stage07_output_directory,
            self.output_directory,
        )
        if any(
            "holdout" in part.casefold()
            for path in paths
            for part in path.resolve(strict=False).parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")
        if self.authoritative_development and (
            self.expected_stage06_fixed_sha256 != STAGE06_FIXED_SHA256
            or self.expected_existing_selection_sha256 != SELECTION_ARTIFACT_SHA256
            or self.expected_eligibility_sha256 != ELIGIBILITY_ARTIFACT_SHA256
            or self.expected_fixed_candidates != EXPECTED_FIXED_CANDIDATES
            or self.expected_fixed_occurrences != EXPECTED_FIXED_OCCURRENCES
            or self.expected_untouched_candidates != EXPECTED_UNTOUCHED_CANDIDATES
            or self.expected_stage07_rows != ACCEPTED_STAGE06_REGISTRY_ROWS
        ):
            _fail("FROZEN_BINDING_MISMATCH", "DEVELOPMENT binding differs")


@dataclass(frozen=True, slots=True)
class ValidationFrameRow:
    candidate_id: bytes
    parser_applicability: str
    technical_status: str
    component_readiness: str
    reason_codes: tuple[str, ...]
    representation: str
    country_code: str | None
    country_frequency_band: str | None
    script_bucket: str | None
    input_codepoints: int | None
    component_count: int | None
    internal_boundary_count: int | None
    internal_single_codepoint_fragment_count: int | None
    maximum_components_per_lexical_run: int | None
    adjacent_repeated_label_internal_boundary_count: int | None
    candidate: str | None
    components: tuple[LibpostalComponent, ...] | None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07V2ValidationSelectionError(
            "ARTIFACT_READ_FAILURE", "A bound artifact could not be read"
        ) from error
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07V2ValidationSelectionError(
            "JSON_INVALID", "A bound JSON artifact could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("JSON_INVALID", "A bound JSON artifact is not an object")
    return value


def _require_private_file(path: Path, expected_sha256: str) -> None:
    if path.is_symlink() or not path.is_file():
        _fail("ARTIFACT_INVALID", "A protected artifact is absent or a symlink")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o600:
        _fail("PERMISSION_FAILURE", "A protected file mode differs")
    if _sha256_file(path) != expected_sha256:
        _fail("ARTIFACT_SHA256_MISMATCH", "A protected artifact hash differs")


def _require_private_directory(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        _fail("ARTIFACT_INVALID", "A protected directory is absent or a symlink")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o700:
        _fail("PERMISSION_FAILURE", "A protected directory mode differs")


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


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _representation(standard: int, native: int) -> str:
    if standard < 0 or native < 0 or standard + native < 1:
        _fail("PROVENANCE_INVALID", "Representation counts are invalid")
    if standard and native:
        return "BOTH"
    return "STANDARD_ONLY" if standard else "NATIVE_ONLY"


def _script_bucket(value: str, reference: ScriptReference) -> str:
    scripts = reference.distinctive_scripts(value)
    if not scripts:
        return "COMMON_OR_UNKNOWN_ONLY"
    if len(scripts) > 1:
        return "MIXED_SCRIPT"
    return next(iter(scripts)).upper()


def _country_frequency_band(frequency: int) -> str:
    if frequency < 1:
        _fail("COUNTRY_FREQUENCY_INVALID", "Country frequency is invalid")
    if frequency == 1:
        return COUNTRY_FREQUENCY_BANDS[0]
    if frequency <= 4:
        return COUNTRY_FREQUENCY_BANDS[1]
    if frequency <= 14:
        return COUNTRY_FREQUENCY_BANDS[2]
    return COUNTRY_FREQUENCY_BANDS[3]


def _domain_rank(domain: str, candidate_id: bytes) -> bytes:
    if len(candidate_id) != 32:
        _fail("CANDIDATE_ID_INVALID", "A candidate ID length differs")
    digest = hashlib.sha256(_SELECTION_DOMAIN)
    encoded = domain.encode("ascii")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(candidate_id)
    return digest.digest()


def _country_rank(country_code: str) -> bytes:
    digest = hashlib.sha256(_SELECTION_DOMAIN)
    digest.update(b"COUNTRY_ORDER")
    digest.update(country_code.encode("ascii"))
    return digest.digest()


def _untouched_fingerprint(candidate_ids: Iterable[bytes]) -> str:
    digest = hashlib.sha256(_UNTOUCHED_DOMAIN)
    for candidate_id in sorted(candidate_ids):
        digest.update(len(candidate_id).to_bytes(8, "big"))
        digest.update(candidate_id)
    return digest.hexdigest()


def _validate_frozen_rule_source() -> None:
    source = Path(__file__).with_name("s07_component_readiness.py")
    if _sha256_file(source) != FROZEN_READINESS_RULE_SOURCE_SHA256:
        _fail("READINESS_RULE_MUTATED", "Frozen rule source identity differs")


def _load_fixed_and_existing_ids(
    config: ValidationSelectionConfig,
) -> tuple[set[bytes], set[bytes], set[bytes]]:
    _require_private_file(
        config.stage06_fixed500_path, config.expected_stage06_fixed_sha256
    )
    fixed = pq.ParquetFile(
        config.stage06_fixed500_path, page_checksum_verification=True
    ).read(use_threads=False)
    if (
        fixed.schema.remove_metadata() != stage06_review_schema()
        or fixed.num_rows != EXPECTED_FIXED_ROWS
    ):
        _fail("FIXED500_INVALID", "Fixed-500 artifact shape differs")
    occurrences, fixed_ids = _fixed_candidate_ids(fixed)
    if (
        len(occurrences) != config.expected_fixed_occurrences
        or len(fixed_ids) != config.expected_fixed_candidates
        or (
            config.authoritative_development
            and _candidate_id_fingerprint(fixed_ids)
            != FIXED500_CANDIDATE_SET_FINGERPRINT
        )
    ):
        _fail("FIXED500_INVALID", "Fixed-500 candidate binding differs")

    _require_private_file(
        config.existing_selection_path, config.expected_existing_selection_sha256
    )
    full_existing = pq.ParquetFile(
        config.existing_selection_path, page_checksum_verification=True
    ).read(use_threads=False)
    if (
        full_existing.num_rows != EXPECTED_EXISTING_SELECTION_ROWS
        or _selection_fingerprint(full_existing) != SELECTION_FINGERPRINT
    ):
        _fail("EXISTING_SELECTION_INVALID", "Existing selection binding differs")
    existing_ids = set(
        cast(
            list[bytes],
            full_existing.column("stage06_exact_candidate_id").to_pylist(),
        )
    )
    if len(existing_ids) != EXPECTED_EXISTING_SELECTION_ROWS:
        _fail("EXISTING_SELECTION_INVALID", "Existing selection IDs differ")
    untouched = fixed_ids - existing_ids
    if len(untouched) != config.expected_untouched_candidates:
        _fail("UNTOUCHED_FRAME_INVALID", "Untouched candidate count differs")
    return fixed_ids, existing_ids, untouched


def _load_eligibility(
    config: ValidationSelectionConfig, untouched: set[bytes]
) -> dict[bytes, dict[str, object]]:
    _require_private_file(config.eligibility_path, config.expected_eligibility_sha256)
    columns = (
        "candidate_id",
        "standard_occurrence_count",
        "native_occurrence_count",
        "country_provenance_status",
        "unanimous_country_code",
        "libpostal_eligibility",
        "stage07_parse_status",
    )
    table = pq.ParquetFile(
        config.eligibility_path, page_checksum_verification=True
    ).read(columns=list(columns), use_threads=False)
    if table.num_rows != config.expected_stage07_rows:
        _fail("ELIGIBILITY_INVALID", "Eligibility row count differs")
    result: dict[bytes, dict[str, object]] = {}
    for index in range(table.num_rows):
        candidate_id = table.column(0)[index].as_py()
        if not isinstance(candidate_id, bytes):
            _fail("ELIGIBILITY_INVALID", "Eligibility candidate ID differs")
        if candidate_id not in untouched:
            continue
        row = {name: table.column(name)[index].as_py() for name in columns[1:]}
        if candidate_id in result:
            _fail("ELIGIBILITY_INVALID", "Eligibility candidate is duplicated")
        result[candidate_id] = row
    if set(result) != untouched:
        _fail("ELIGIBILITY_INVALID", "Eligibility coverage differs")
    return result


def _validate_stage07_identity(
    config: ValidationSelectionConfig,
) -> tuple[Path, ...]:
    root = config.stage07_output_directory
    _require_private_directory(root)
    manifest_path = root / STAGE07_MANIFEST_NAME
    _require_private_file(manifest_path, config.expected_stage07_manifest_sha256)
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
        or scientific.get("candidate_count") != config.expected_stage07_rows
        or scientific.get("status_vocabulary") != list(STAGE07_STATUS_VOCABULARY)
    ):
        _fail("STAGE07_BINDING_MISMATCH", "Stage 7 scientific identity differs")
    stage06_binding = scientific.get("stage06_binding")
    if (
        not isinstance(stage06_binding, dict)
        or stage06_binding.get("parser_bundle_fingerprint")
        != ACCEPTED_PARSER_BUNDLE_FINGERPRINT
        or stage06_binding.get("stage06_registry_rows") != config.expected_stage07_rows
    ):
        _fail("STAGE07_BINDING_MISMATCH", "Stage 7 upstream binding differs")
    artifacts = _manifest_artifacts(root, physical)
    if sum(item.row_count for item in artifacts) != config.expected_stage07_rows:
        _fail("STAGE07_BINDING_MISMATCH", "Stage 7 artifact rows differ")
    return tuple(root / item.relative_path for item in artifacts)


def _components_from_value(value: object) -> tuple[LibpostalComponent, ...]:
    if not isinstance(value, list):
        _fail("STAGE07_ROW_INVALID", "A component list is absent")
    result: list[LibpostalComponent] = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("STAGE07_ROW_INVALID", "A component item differs")
        result.append(LibpostalComponent(label=item["label"], value=item["value"]))
    return tuple(result)


def _select_authorized_stage07_values(
    stage07_paths: Sequence[Path], eligible_ids: set[bytes]
) -> dict[bytes, tuple[str, int, int, str, tuple[LibpostalComponent, ...]]]:
    """Materialize nested values only for the exact eligible untouched IDs.

    DuckDB first scans only the candidate-ID column to prove complete unique
    coverage.  The second relation keeps the exact ID semi-join in the scan
    plan and emits candidate/components only for matched IDs; unrelated nested
    rows are never returned to Python.
    """
    target = pa.table(
        {"candidate_id": pa.array(sorted(eligible_ids), type=pa.binary(32))}
    )
    connection = duckdb.connect(":memory:")
    try:
        connection.execute("SET threads=1")
        connection.execute("SET preserve_insertion_order=false")
        connection.register("authorized_target_ids", target)
        paths = [str(path) for path in stage07_paths]
        count_row = connection.execute(
            f"""
            SELECT count(*), count(DISTINCT s.{REGISTRY_COLUMNS[0]})
            FROM read_parquet(?) AS s
            SEMI JOIN authorized_target_ids AS t
              ON s.{REGISTRY_COLUMNS[0]} = t.candidate_id
            """,
            [paths],
        ).fetchone()
        if count_row != (len(eligible_ids), len(eligible_ids)):
            _fail("SELECTIVE_READ_IDENTITY_FAILURE", "Selected Stage 7 IDs differ")
        reader = connection.execute(
            f"""
            SELECT
              s.{REGISTRY_COLUMNS[0]},
              s.{REGISTRY_COLUMNS[1]},
              s.{REGISTRY_COLUMNS[3]},
              s.{REGISTRY_COLUMNS[4]},
              s.{STAGE07_STATUS_FIELD},
              s.{STAGE07_COMPONENTS_FIELD}
            FROM read_parquet(?) AS s
            SEMI JOIN authorized_target_ids AS t
              ON s.{REGISTRY_COLUMNS[0]} = t.candidate_id
            ORDER BY s.{REGISTRY_COLUMNS[0]}
            """,
            [paths],
        ).to_arrow_reader(batch_size=16)
        result: dict[
            bytes, tuple[str, int, int, str, tuple[LibpostalComponent, ...]]
        ] = {}
        for batch in reader:
            for index in range(batch.num_rows):
                candidate_id = batch.column(0)[index].as_py()
                candidate = batch.column(1)[index].as_py()
                standard = batch.column(2)[index].as_py()
                native = batch.column(3)[index].as_py()
                status = batch.column(4)[index].as_py()
                raw_components = batch.column(5)[index].as_py()
                if (
                    not isinstance(candidate_id, bytes)
                    or candidate_id not in eligible_ids
                    or candidate_id in result
                    or not isinstance(candidate, str)
                    or isinstance(standard, bool)
                    or not isinstance(standard, int)
                    or isinstance(native, bool)
                    or not isinstance(native, int)
                    or not isinstance(status, str)
                ):
                    _fail("STAGE07_ROW_INVALID", "A selected Stage 7 row differs")
                result[candidate_id] = (
                    candidate,
                    standard,
                    native,
                    status,
                    _components_from_value(raw_components),
                )
    except Stage07V2ValidationSelectionError:
        raise
    except (duckdb.Error, pa.ArrowException) as error:
        raise Stage07V2ValidationSelectionError(
            "SELECTIVE_READ_FAILURE", "Authorized Stage 7 values could not be read"
        ) from error
    finally:
        connection.close()
    if set(result) != eligible_ids:
        _fail("SELECTIVE_READ_IDENTITY_FAILURE", "Selected Stage 7 coverage differs")
    return result


def _frame_row(
    *,
    candidate_id: bytes,
    meta: Mapping[str, object],
    stage07: tuple[str, int, int, str, tuple[LibpostalComponent, ...]] | None,
    scripts: ScriptReference,
) -> ValidationFrameRow:
    applicability = meta.get("libpostal_eligibility")
    standard = meta.get("standard_occurrence_count")
    native = meta.get("native_occurrence_count")
    country_code = meta.get("unanimous_country_code")
    published_status = meta.get("stage07_parse_status")
    if (
        not isinstance(applicability, str)
        or isinstance(standard, bool)
        or not isinstance(standard, int)
        or isinstance(native, bool)
        or not isinstance(native, int)
        or (country_code is not None and not isinstance(country_code, str))
        or not isinstance(published_status, str)
    ):
        _fail("ELIGIBILITY_INVALID", "Eligibility metadata types differ")
    representation = _representation(standard, native)
    if applicability != PARSER_ELIGIBLE_COUNTRY:
        if stage07 is not None:
            _fail("SCOPE_VIOLATION", "Unresolved candidate values were materialized")
        unresolved_decision = decide_component_readiness(
            parser_applicability=applicability,
            technical_status=NOT_ATTEMPTED_NOT_ELIGIBLE,
            candidate="",
            components=None,
            standard_occurrence_count=standard,
            native_occurrence_count=native,
        )
        return ValidationFrameRow(
            candidate_id=candidate_id,
            parser_applicability=applicability,
            technical_status=NOT_ATTEMPTED_NOT_ELIGIBLE,
            component_readiness=unresolved_decision.status,
            reason_codes=unresolved_decision.reason_codes,
            representation=representation,
            country_code=None,
            country_frequency_band=None,
            script_bucket=None,
            input_codepoints=None,
            component_count=None,
            internal_boundary_count=None,
            internal_single_codepoint_fragment_count=None,
            maximum_components_per_lexical_run=None,
            adjacent_repeated_label_internal_boundary_count=None,
            candidate=None,
            components=None,
        )
    if stage07 is None or country_code is None:
        _fail("ELIGIBILITY_INVALID", "Eligible candidate evidence is absent")
    candidate, stage07_standard, stage07_native, technical_status, components = stage07
    if (
        stage07_standard != standard
        or stage07_native != native
        or technical_status != published_status
    ):
        _fail("STAGE07_BINDING_MISMATCH", "Selected Stage 7 metadata differs")
    decision = decide_component_readiness(
        parser_applicability=applicability,
        technical_status=technical_status,
        candidate=candidate,
        components=components,
        standard_occurrence_count=standard,
        native_occurrence_count=native,
    )
    signals = decision.signals
    return ValidationFrameRow(
        candidate_id=candidate_id,
        parser_applicability=applicability,
        technical_status=technical_status,
        component_readiness=decision.status,
        reason_codes=decision.reason_codes,
        representation=representation,
        country_code=country_code,
        country_frequency_band=None,
        script_bucket=_script_bucket(candidate, scripts),
        input_codepoints=len(candidate),
        component_count=len(components),
        internal_boundary_count=signals.internal_boundary_count if signals else 0,
        internal_single_codepoint_fragment_count=(
            signals.internal_single_codepoint_fragment_count if signals else 0
        ),
        maximum_components_per_lexical_run=(
            signals.maximum_components_per_lexical_run if signals else 0
        ),
        adjacent_repeated_label_internal_boundary_count=(
            signals.adjacent_repeated_label_internal_boundary_count if signals else 0
        ),
        candidate=candidate,
        components=components,
    )


def _assign_country_bands(
    rows: Sequence[ValidationFrameRow],
) -> list[ValidationFrameRow]:
    frequencies = Counter(
        row.country_code
        for row in rows
        if row.component_readiness in {COMPONENTS_READY, COMPONENTS_ABSTAIN}
        and row.country_code is not None
    )
    result: list[ValidationFrameRow] = []
    for row in rows:
        if row.country_code is None:
            result.append(row)
        else:
            result.append(
                replace(
                    row,
                    country_frequency_band=_country_frequency_band(
                        frequencies[row.country_code]
                    ),
                )
            )
    return result


def _category_values(row: ValidationFrameRow, dimension: str) -> tuple[str, ...]:
    if dimension == "reason":
        return row.reason_codes
    if dimension == "script" and row.script_bucket is not None:
        return (row.script_bucket,)
    if dimension == "representation":
        return (row.representation,)
    if dimension == "country_frequency_band" and row.country_frequency_band:
        return (row.country_frequency_band,)
    return ()


def _round_robin_add(
    *,
    pool: Sequence[ValidationFrameRow],
    selected: list[ValidationFrameRow],
    selected_ids: set[bytes],
    dimension: str,
    category_order: Sequence[str],
    additions: int,
    arm_target: int,
) -> None:
    queues: dict[str, list[ValidationFrameRow]] = {}
    for category in category_order:
        queues[category] = sorted(
            (row for row in pool if category in _category_values(row, dimension)),
            key=lambda row: _domain_rank(
                f"{dimension.upper()}:{category}", row.candidate_id
            ),
        )
    added = 0
    offsets = {category: 0 for category in category_order}
    while added < additions and len(selected) < arm_target:
        progress = False
        for category in category_order:
            queue = queues[category]
            offset = offsets[category]
            while offset < len(queue) and queue[offset].candidate_id in selected_ids:
                offset += 1
            offsets[category] = offset
            if offset >= len(queue):
                continue
            row = queue[offset]
            offsets[category] += 1
            selected.append(row)
            selected_ids.add(row.candidate_id)
            added += 1
            progress = True
            if added >= additions or len(selected) >= arm_target:
                break
        if not progress:
            break


def _arm_target_counts(ready: int, abstain: int) -> dict[str, int]:
    if ready + abstain < TARGET_SAMPLE_SIZE:
        _fail(
            "VALIDATION_POPULATION_TOO_SMALL", "Eligible validation frame is too small"
        )
    targets = {
        COMPONENTS_READY: min(TARGET_READY, ready),
        COMPONENTS_ABSTAIN: min(TARGET_ABSTAIN, abstain),
    }
    remaining = TARGET_SAMPLE_SIZE - sum(targets.values())
    for arm, available in (
        (COMPONENTS_READY, ready),
        (COMPONENTS_ABSTAIN, abstain),
    ):
        transfer = min(remaining, available - targets[arm])
        targets[arm] += transfer
        remaining -= transfer
    if remaining:
        _fail("VALIDATION_POPULATION_TOO_SMALL", "Arm transfer cannot fill sample")
    return targets


def _scaled_budget(value_at_120: int, target: int) -> int:
    return (value_at_120 * target) // 120


def _select_arm(
    pool: Sequence[ValidationFrameRow], *, arm: str, target: int
) -> list[ValidationFrameRow]:
    selected: list[ValidationFrameRow] = []
    selected_ids: set[bytes] = set()
    script_order = sorted(
        {row.script_bucket for row in pool if row.script_bucket is not None}
    )
    if arm == COMPONENTS_ABSTAIN:
        _round_robin_add(
            pool=pool,
            selected=selected,
            selected_ids=selected_ids,
            dimension="reason",
            category_order=REASON_ORDER,
            additions=_scaled_budget(40, target),
            arm_target=target,
        )
        phase_budgets = (
            ("script", 24),
            ("representation", 18),
            ("country_frequency_band", 18),
        )
    else:
        phase_budgets = (
            ("script", 36),
            ("representation", 30),
            ("country_frequency_band", 24),
        )
    category_orders: Mapping[str, Sequence[str]] = {
        "script": script_order,
        "representation": REPRESENTATION_ORDER,
        "country_frequency_band": COUNTRY_FREQUENCY_BANDS,
    }
    for dimension, budget in phase_budgets:
        _round_robin_add(
            pool=pool,
            selected=selected,
            selected_ids=selected_ids,
            dimension=dimension,
            category_order=category_orders[dimension],
            additions=_scaled_budget(budget, target),
            arm_target=target,
        )

    countries = sorted(
        {row.country_code for row in pool if row.country_code is not None},
        key=_country_rank,
    )
    represented = {row.country_code for row in selected}
    for country in countries:
        if len(selected) >= target:
            break
        if country in represented:
            continue
        candidates = sorted(
            (
                row
                for row in pool
                if row.country_code == country and row.candidate_id not in selected_ids
            ),
            key=lambda row: _domain_rank(f"COUNTRY:{country}", row.candidate_id),
        )
        if candidates:
            selected.append(candidates[0])
            selected_ids.add(candidates[0].candidate_id)
            represented.add(country)

    for row in sorted(
        pool, key=lambda item: _domain_rank(f"GLOBAL_FILL:{arm}", item.candidate_id)
    ):
        if len(selected) >= target:
            break
        if row.candidate_id not in selected_ids:
            selected.append(row)
            selected_ids.add(row.candidate_id)
    if len(selected) != target or len(selected_ids) != target:
        _fail("SELECTION_TOTALITY_FAILURE", "An arm target was not filled")
    return selected


def freeze_validation_selection(
    rows: Sequence[ValidationFrameRow],
) -> list[ValidationFrameRow]:
    """Select exactly 240 predictions without semantic labels or text ranking."""
    eligible = [
        row
        for row in rows
        if row.component_readiness in {COMPONENTS_READY, COMPONENTS_ABSTAIN}
    ]
    ready_pool = [
        row for row in eligible if row.component_readiness == COMPONENTS_READY
    ]
    abstain_pool = [
        row for row in eligible if row.component_readiness == COMPONENTS_ABSTAIN
    ]
    targets = _arm_target_counts(len(ready_pool), len(abstain_pool))
    selected = [
        *_select_arm(
            ready_pool, arm=COMPONENTS_READY, target=targets[COMPONENTS_READY]
        ),
        *_select_arm(
            abstain_pool,
            arm=COMPONENTS_ABSTAIN,
            target=targets[COMPONENTS_ABSTAIN],
        ),
    ]
    selected.sort(key=lambda row: _domain_rank("REVIEW_ORDER", row.candidate_id))
    if (
        len(selected) != TARGET_SAMPLE_SIZE
        or len({row.candidate_id for row in selected}) != TARGET_SAMPLE_SIZE
    ):
        _fail("SELECTION_TOTALITY_FAILURE", "Validation selection is not exact")
    return selected


def _selection_fingerprint_v1(
    *,
    selected: Sequence[ValidationFrameRow],
    untouched_fingerprint: str,
    stage07_manifest_sha256: str,
) -> str:
    digest = hashlib.sha256(_SELECTION_DOMAIN)
    for value in (
        SELECTION_CONTRACT_VERSION,
        READINESS_RULE_VERSION,
        FROZEN_READINESS_RULE_SOURCE_SHA256,
        FIXED500_CANDIDATE_SET_FINGERPRINT,
        SELECTION_FINGERPRINT,
        untouched_fingerprint,
        stage07_manifest_sha256,
    ):
        encoded = value.encode("ascii")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for payload in (SELECTION_ALGORITHM, VALIDATION_THRESHOLDS):
        encoded = _canonical_json(payload)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    for review_order, row in enumerate(selected, start=1):
        payload = {
            "review_order": review_order,
            "candidate_id_hex": row.candidate_id.hex(),
            "component_readiness": row.component_readiness,
            "reason_codes": list(row.reason_codes),
            "representation": row.representation,
            "script_bucket": row.script_bucket,
            "country_code": row.country_code,
            "country_frequency_band": row.country_frequency_band,
            "input_codepoints": row.input_codepoints,
            "component_count": row.component_count,
        }
        encoded = _canonical_json(payload)
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _large_string_list_type() -> pa.LargeListType:
    return pa.large_list(pa.field("element", pa.large_string(), nullable=False))


def _frame_schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field("stage06_exact_candidate_id", pa.binary(32), False),
            pa.field("parser_applicability", pa.string(), False),
            pa.field("technical_status", pa.string(), False),
            pa.field("component_readiness", pa.string(), False),
            pa.field("readiness_reason_codes", _large_string_list_type(), False),
            pa.field("representation", pa.string(), False),
            pa.field("country_code", pa.string(), True),
            pa.field("country_frequency_band", pa.string(), True),
            pa.field("script_bucket", pa.string(), True),
            pa.field("input_codepoints", pa.uint64(), True),
            pa.field("component_count", pa.uint64(), True),
            pa.field("internal_boundary_count", pa.uint64(), True),
            pa.field("internal_single_codepoint_fragment_count", pa.uint64(), True),
            pa.field("maximum_components_per_lexical_run", pa.uint64(), True),
            pa.field(
                "adjacent_repeated_label_internal_boundary_count", pa.uint64(), True
            ),
        )
    )


def _selection_schema() -> pa.Schema:
    return pa.schema((pa.field("review_order", pa.uint32(), False), *_frame_schema()))


def _review_schema() -> pa.Schema:
    return pa.schema(
        (
            *_selection_schema(),
            pa.field("stage06_candidate_lower", pa.large_string(), False),
            pa.field(STAGE07_STATUS_FIELD, pa.string(), False),
            pa.field(
                STAGE07_COMPONENTS_FIELD,
                pa.large_list(
                    pa.field(
                        "element",
                        pa.struct(
                            (
                                pa.field("label", pa.large_string(), False),
                                pa.field("value", pa.large_string(), False),
                            )
                        ),
                        False,
                    )
                ),
                False,
            ),
        )
    )


def _frame_record(row: ValidationFrameRow) -> dict[str, object]:
    return {
        "stage06_exact_candidate_id": row.candidate_id,
        "parser_applicability": row.parser_applicability,
        "technical_status": row.technical_status,
        "component_readiness": row.component_readiness,
        "readiness_reason_codes": list(row.reason_codes),
        "representation": row.representation,
        "country_code": row.country_code,
        "country_frequency_band": row.country_frequency_band,
        "script_bucket": row.script_bucket,
        "input_codepoints": row.input_codepoints,
        "component_count": row.component_count,
        "internal_boundary_count": row.internal_boundary_count,
        "internal_single_codepoint_fragment_count": (
            row.internal_single_codepoint_fragment_count
        ),
        "maximum_components_per_lexical_run": row.maximum_components_per_lexical_run,
        "adjacent_repeated_label_internal_boundary_count": (
            row.adjacent_repeated_label_internal_boundary_count
        ),
    }


def _counter_by(
    rows: Iterable[ValidationFrameRow],
    value: Callable[[ValidationFrameRow], str | None],
) -> dict[str, int]:
    return dict(sorted(Counter(item for row in rows if (item := value(row))).items()))


def _cross_counts(
    rows: Sequence[ValidationFrameRow],
    value: Callable[[ValidationFrameRow], str | None],
) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        item = value(row)
        if item is not None:
            result[row.component_readiness][item] += 1
    return {
        status: dict(sorted(counts.items()))
        for status, counts in sorted(result.items())
    }


def _reason_counts(rows: Sequence[ValidationFrameRow]) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        for reason in row.reason_codes:
            result[row.component_readiness][reason] += 1
    return {
        status: dict(sorted(counts.items()))
        for status, counts in sorted(result.items())
    }


def _aggregate(
    *,
    config: ValidationSelectionConfig,
    frame: Sequence[ValidationFrameRow],
    selected: Sequence[ValidationFrameRow],
    selection_fingerprint: str,
    untouched_fingerprint: str,
    stage07_artifact_count: int,
) -> dict[str, object]:
    eligible = [row for row in frame if row.component_readiness != NOT_ASSESSED]
    readiness_counts = _counter_by(frame, lambda row: row.component_readiness)
    selected_counts = _counter_by(selected, lambda row: row.component_readiness)
    abstain = readiness_counts.get(COMPONENTS_ABSTAIN, 0)
    eligible_count = len(eligible)
    abstention_percent = (100.0 * abstain / eligible_count) if eligible_count else 0.0
    return {
        "version": VALIDATION_FREEZE_VERSION,
        "status": "STAGE07_V2_VALIDATION_SELECTION_FROZEN",
        "execution_git_sha": config.execution_git_sha,
        "readiness_rule": {
            "id": READINESS_RULE_VERSION,
            "source_sha256": FROZEN_READINESS_RULE_SOURCE_SHA256,
            "changed_after_frame_values_read": False,
        },
        "bindings": {
            "fixed500_candidate_set_fingerprint": FIXED500_CANDIDATE_SET_FINGERPRINT,
            "existing_120_selection_fingerprint": SELECTION_FINGERPRINT,
            "untouched_604_candidate_set_fingerprint": untouched_fingerprint,
            "stage07_manifest_sha256": config.expected_stage07_manifest_sha256,
            "stage07_artifact_count": stage07_artifact_count,
            "eligibility_artifact_sha256": config.expected_eligibility_sha256,
        },
        "frame": {
            "candidates": len(frame),
            "readiness_counts": readiness_counts,
            "applicability_counts": _counter_by(
                frame, lambda row: row.parser_applicability
            ),
            "technical_status_counts": _counter_by(
                frame, lambda row: row.technical_status
            ),
            "representation_by_readiness": _cross_counts(
                frame, lambda row: row.representation
            ),
            "script_by_readiness": _cross_counts(frame, lambda row: row.script_bucket),
            "country_frequency_band_by_readiness": _cross_counts(
                frame, lambda row: row.country_frequency_band
            ),
            "reason_code_by_readiness": _reason_counts(frame),
            "eligible_abstention_coverage_percent": abstention_percent,
            "eligible_abstention_coverage_predeclared_range_pass": (
                10.0 <= abstention_percent <= 70.0
            ),
        },
        "selection": {
            "contract": SELECTION_CONTRACT_VERSION,
            "algorithm": SELECTION_ALGORITHM,
            "candidate_count": len(selected),
            "fingerprint": selection_fingerprint,
            "readiness_counts": selected_counts,
            "representation_by_readiness": _cross_counts(
                selected, lambda row: row.representation
            ),
            "script_by_readiness": _cross_counts(
                selected, lambda row: row.script_bucket
            ),
            "country_frequency_band_by_readiness": _cross_counts(
                selected, lambda row: row.country_frequency_band
            ),
            "reason_code_by_readiness": _reason_counts(selected),
            "unique_country_count": len(
                {row.country_code for row in selected if row.country_code is not None}
            ),
            "predictions_frozen_before_semantic_review": True,
            "semantic_labels_present": False,
        },
        "validation_thresholds": VALIDATION_THRESHOLDS,
        "scope": {
            "authoritative_registry_id_rows_scanned": config.expected_stage07_rows,
            "full_registry_nested_rows_materialized": 0,
            "candidate_values_materialized": eligible_count,
            "component_streams_materialized": eligible_count,
            "unresolved_candidate_values_materialized": 0,
            "unrelated_nested_rows_returned_to_python": 0,
            "semantic_content_inspected_by_human_or_llm": 0,
            "parser_calls": 0,
            "network_calls": 0,
            "holdout_accessed": False,
            "production_accessed": False,
            "stage8_started": False,
        },
        "next_authorization_scope": {
            "candidate_count": TARGET_SAMPLE_SIZE,
            "artifact": "stage07_v2_validation_review.parquet",
            "allowed_purpose": "FRESH_STAGE07_V2_SEMANTIC_VALIDATION_ONLY",
            "holdout": False,
            "production": False,
        },
    }


def _validate_published_selection_bundle(
    *,
    output_directory: Path,
    expected_manifest_sha256: str,
    expected_selection_fingerprint: str,
    expected_frame_rows: int,
) -> None:
    """Reopen the publication without semantically reading review values."""
    _require_private_directory(output_directory)
    expected_files = {
        "stage07_v2_validation_frame.parquet",
        "stage07_v2_validation_selection.parquet",
        "stage07_v2_validation_review.parquet",
        "stage07_v2_validation_selection_aggregate.json",
        "stage07_v2_validation_selection_manifest.json",
        "_SUCCESS.json",
    }
    observed_files = {
        path.name
        for path in output_directory.iterdir()
        if path.is_file() and not path.is_symlink()
    }
    if observed_files != expected_files or any(
        path.is_symlink() or not path.is_file() for path in output_directory.iterdir()
    ):
        _fail("PUBLICATION_TOPOLOGY_INVALID", "Published output topology differs")
    for path in output_directory.iterdir():
        if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o600:
            _fail("PERMISSION_FAILURE", "A published file mode differs")

    manifest_path = output_directory / "stage07_v2_validation_selection_manifest.json"
    success_path = output_directory / "_SUCCESS.json"
    if _sha256_file(manifest_path) != expected_manifest_sha256:
        _fail("PUBLICATION_MANIFEST_MISMATCH", "Published manifest hash differs")
    manifest = _load_json(manifest_path)
    success = _load_json(success_path)
    if (
        manifest.get("status") != "STAGE07_V2_VALIDATION_SELECTION_FROZEN"
        or manifest.get("selection_fingerprint") != expected_selection_fingerprint
        or manifest.get("semantic_review_started") is not False
        or success.get("status") != "STAGE07_V2_VALIDATION_SELECTION_FROZEN"
        or success.get("manifest_sha256") != expected_manifest_sha256
        or success.get("selection_fingerprint") != expected_selection_fingerprint
    ):
        _fail("PUBLICATION_BINDING_MISMATCH", "Published terminal binding differs")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 4:
        _fail("PUBLICATION_MANIFEST_INVALID", "Published artifact list differs")
    for raw in artifacts:
        if (
            not isinstance(raw, dict)
            or set(raw) != {"relative_path", "size_bytes", "sha256"}
            or not isinstance(raw["relative_path"], str)
            or not isinstance(raw["size_bytes"], int)
            or not isinstance(raw["sha256"], str)
        ):
            _fail("PUBLICATION_MANIFEST_INVALID", "An artifact identity differs")
        path = output_directory / raw["relative_path"]
        if (
            path.name not in expected_files
            or path.stat(follow_symlinks=False).st_size != raw["size_bytes"]
            or _sha256_file(path) != raw["sha256"]
        ):
            _fail("PUBLICATION_ARTIFACT_MISMATCH", "An artifact hash differs")

    frame_path = output_directory / "stage07_v2_validation_frame.parquet"
    selection_path = output_directory / "stage07_v2_validation_selection.parquet"
    review_path = output_directory / "stage07_v2_validation_review.parquet"
    frame_file = pq.ParquetFile(frame_path, page_checksum_verification=True)
    selection_file = pq.ParquetFile(selection_path, page_checksum_verification=True)
    review_file = pq.ParquetFile(review_path, page_checksum_verification=True)
    if (
        frame_file.schema_arrow != _frame_schema()
        or selection_file.schema_arrow != _selection_schema()
        or review_file.schema_arrow != _review_schema()
        or frame_file.metadata.num_rows != expected_frame_rows
        or selection_file.metadata.num_rows != TARGET_SAMPLE_SIZE
        or review_file.metadata.num_rows != TARGET_SAMPLE_SIZE
    ):
        _fail("PUBLICATION_SCHEMA_MISMATCH", "Published Parquet shape differs")

    identity_columns = [
        "review_order",
        "stage06_exact_candidate_id",
        "component_readiness",
        "readiness_reason_codes",
    ]
    selection_identity = selection_file.read(
        columns=identity_columns, use_threads=False
    )
    review_identity = review_file.read(columns=identity_columns, use_threads=False)
    if not selection_identity.equals(review_identity):
        _fail("PUBLICATION_REVIEW_MISMATCH", "Selection/review identity differs")
    orders = selection_identity.column("review_order").to_pylist()
    candidate_ids = selection_identity.column("stage06_exact_candidate_id").to_pylist()
    if (
        orders != list(range(1, TARGET_SAMPLE_SIZE + 1))
        or len(set(candidate_ids)) != TARGET_SAMPLE_SIZE
    ):
        _fail("PUBLICATION_SELECTION_MISMATCH", "Published selection totality differs")
    aggregate = _load_json(
        output_directory / "stage07_v2_validation_selection_aggregate.json"
    )
    selection = aggregate.get("selection")
    if (
        not isinstance(selection, dict)
        or selection.get("candidate_count") != TARGET_SAMPLE_SIZE
        or selection.get("fingerprint") != expected_selection_fingerprint
        or selection.get("semantic_labels_present") is not False
    ):
        _fail("PUBLICATION_AGGREGATE_MISMATCH", "Aggregate selection binding differs")
    _validate_frozen_rule_source()


def run_validation_selection_freeze(
    config: ValidationSelectionConfig,
) -> dict[str, object]:
    """Apply the frozen rule and atomically publish the 240-case selection."""
    config.validate()
    if config.authoritative_development:
        require_goethe_nhr_slurm("stage07-v2-validation-selection-freeze")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Validation output already exists")
    _validate_frozen_rule_source()
    _, _, untouched = _load_fixed_and_existing_ids(config)
    eligibility = _load_eligibility(config, untouched)
    stage07_paths = _validate_stage07_identity(config)
    eligible_ids = {
        candidate_id
        for candidate_id, meta in eligibility.items()
        if meta.get("libpostal_eligibility") == PARSER_ELIGIBLE_COUNTRY
    }
    selected_values = _select_authorized_stage07_values(stage07_paths, eligible_ids)
    scripts = ScriptReference.from_artifact(
        unicode_script_reference_paths()["unicode_manifest"],
        unicode_script_reference_paths()["unicode_artifact"],
    )
    frame = _assign_country_bands(
        [
            _frame_row(
                candidate_id=candidate_id,
                meta=eligibility[candidate_id],
                stage07=selected_values.get(candidate_id),
                scripts=scripts,
            )
            for candidate_id in sorted(untouched)
        ]
    )
    if len(frame) != config.expected_untouched_candidates:
        _fail("FRAME_TOTALITY_FAILURE", "Validation frame count differs")
    selected = freeze_validation_selection(frame)
    untouched_fingerprint = _untouched_fingerprint(untouched)
    selection_fingerprint = _selection_fingerprint_v1(
        selected=selected,
        untouched_fingerprint=untouched_fingerprint,
        stage07_manifest_sha256=config.expected_stage07_manifest_sha256,
    )

    parent = config.output_directory.parent
    partial = parent / f".{config.output_directory.name}.partial.{os.getpid()}"
    old_umask = os.umask(0o077)
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent.chmod(0o700)
        partial.mkdir(mode=0o700)
        frame_path = partial / "stage07_v2_validation_frame.parquet"
        selection_path = partial / "stage07_v2_validation_selection.parquet"
        review_path = partial / "stage07_v2_validation_review.parquet"
        aggregate_path = partial / "stage07_v2_validation_selection_aggregate.json"

        frame_records = [_frame_record(row) for row in frame]
        selection_records = [
            {"review_order": order, **_frame_record(row)}
            for order, row in enumerate(selected, start=1)
        ]
        review_records = []
        for order, row in enumerate(selected, start=1):
            if row.candidate is None or row.components is None:
                _fail("SELECTION_INVALID", "Selected review evidence is absent")
            review_records.append(
                {
                    **selection_records[order - 1],
                    "stage06_candidate_lower": row.candidate,
                    STAGE07_STATUS_FIELD: row.technical_status,
                    STAGE07_COMPONENTS_FIELD: [
                        {"label": item.label, "value": item.value}
                        for item in row.components
                    ],
                }
            )
        pq.write_table(
            pa.Table.from_pylist(frame_records, schema=_frame_schema()),
            frame_path,
            compression="zstd",
            write_page_checksum=True,
            row_group_size=64,
        )
        pq.write_table(
            pa.Table.from_pylist(selection_records, schema=_selection_schema()),
            selection_path,
            compression="zstd",
            write_page_checksum=True,
            row_group_size=64,
        )
        pq.write_table(
            pa.Table.from_pylist(review_records, schema=_review_schema()),
            review_path,
            compression="zstd",
            write_page_checksum=True,
            row_group_size=16,
        )
        for path in (frame_path, selection_path, review_path):
            path.chmod(0o600)

        aggregate = _aggregate(
            config=config,
            frame=frame,
            selected=selected,
            selection_fingerprint=selection_fingerprint,
            untouched_fingerprint=untouched_fingerprint,
            stage07_artifact_count=len(stage07_paths),
        )
        _write_json(aggregate_path, aggregate)
        artifacts = [frame_path, selection_path, review_path, aggregate_path]
        manifest = {
            "version": "stage07_v2_validation_selection_manifest_v1",
            "status": "STAGE07_V2_VALIDATION_SELECTION_FROZEN",
            "execution_git_sha": config.execution_git_sha,
            "readiness_rule_id": READINESS_RULE_VERSION,
            "readiness_rule_source_sha256": FROZEN_READINESS_RULE_SOURCE_SHA256,
            "selection_contract": SELECTION_CONTRACT_VERSION,
            "selection_fingerprint": selection_fingerprint,
            "semantic_review_started": False,
            "post_publication_validation_contract": (
                "stage07_v2_validation_selection_reopen_v1"
            ),
            "artifacts": [
                {
                    "relative_path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
                for path in artifacts
            ],
            "owner_only": True,
            "protected_values_in_aggregate": False,
        }
        manifest_path = partial / "stage07_v2_validation_selection_manifest.json"
        _write_json(manifest_path, manifest)
        _write_json(
            partial / "_SUCCESS.json",
            {
                "status": "STAGE07_V2_VALIDATION_SELECTION_FROZEN",
                "manifest_sha256": _sha256_file(manifest_path),
                "aggregate_sha256": _sha256_file(aggregate_path),
                "selection_fingerprint": selection_fingerprint,
                "post_publication_validation_required": True,
            },
        )
        for path in partial.iterdir():
            if path.is_file():
                path.chmod(0o600)
        _fsync_directory(partial)
        os.replace(partial, config.output_directory)
        _fsync_directory(parent)
        _validate_published_selection_bundle(
            output_directory=config.output_directory,
            expected_manifest_sha256=_sha256_file(
                config.output_directory
                / "stage07_v2_validation_selection_manifest.json"
            ),
            expected_selection_fingerprint=selection_fingerprint,
            expected_frame_rows=config.expected_untouched_candidates,
        )
        return aggregate
    except (Stage07V2ValidationSelectionError, pa.ArrowException, OSError):
        raise
    finally:
        os.umask(old_umask)


__all__ = [
    "COUNTRY_FREQUENCY_BANDS",
    "FROZEN_READINESS_RULE_SOURCE_SHA256",
    "SELECTION_ALGORITHM",
    "SELECTION_CONTRACT_VERSION",
    "Stage07V2ValidationSelectionError",
    "TARGET_SAMPLE_SIZE",
    "VALIDATION_THRESHOLDS",
    "ValidationFrameRow",
    "ValidationSelectionConfig",
    "freeze_validation_selection",
    "run_validation_selection_freeze",
]

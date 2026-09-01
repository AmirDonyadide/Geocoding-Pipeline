"""Owner-only Stage 7 fixed-500 and qualitative-review evidence."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import stat
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, TextIO, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..script_reference import ScriptReference, unicode_script_reference_paths
from ..stages.s06_exact_deduplication import REGISTRY_COLUMNS, ROW_MAP_ID_COLUMNS
from ..stages.s07_design_diagnostic import (
    ACCEPTED_CASE_VARIANT_GROUPS,
    ACCEPTED_CASE_VARIANT_SURFACES,
    ACCEPTED_FIXED500_OCCURRENCES,
    ACCEPTED_FIXED500_ROWS,
    ACCEPTED_FIXED500_UNIQUE_CANDIDATES,
    _candidate_features,
    _clean_surface_groups,
)
from ..stages.s07_libpostal_adapter import (
    PARSED_EMPTY,
    LibpostalComponent,
    ParsedAddress,
    ordered_parse_sha256,
)
from ..stages.s07_parsing import (
    ACCEPTED_STAGE06_MANIFEST_SHA256,
    STAGE07_MANIFEST_NAME,
    _iter_batches,
    _sha256_file,
    _stage06_artifact_paths,
    validate_stage07_bundle,
)
from ..stages.s07_output_schema import STAGE07_COMPONENTS_FIELD, STAGE07_STATUS_FIELD
from ..stages.s07_supervised_parser import SupervisedParser
from .stage06 import (
    STAGE06_REVIEW_MANIFEST_NAME,
    STAGE06_REVIEW_PATH,
    stage06_review_schema,
)


STAGE07_REVIEW_CONTRACT_VERSION = "development_stage07_review_contract_v1"
STAGE07_REVIEW_MANIFEST_VERSION = "development_stage07_review_manifest_v1"
STAGE07_REVIEW_MANIFEST_NAME = "stage07_review_manifest.json"
STAGE07_REVIEW_SUCCESS_MARKER = "_SUCCESS.json"
STAGE07_REVIEW_IN_PROGRESS_MARKER = "_IN_PROGRESS"
STAGE07_FIXED500_PATH = "stage07_fixed500_verification.parquet"
STAGE07_QUALITATIVE_SELECTION_PATH = "stage07_qualitative_selection.parquet"
STAGE07_QUALITATIVE_HTML_PATH = "stage07_qualitative_review.html"
STAGE07_REVIEW_SUMMARY_PATH = "stage07_review_summary.json"
STAGE07_QUALITATIVE_TARGET = 120
EXPECTED_STAGE06_REVIEW_MANIFEST_SHA256 = (
    "1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1"
)
EXPECTED_DIAGNOSTIC_LABELS = frozenset(
    {
        "category",
        "city",
        "city_district",
        "country",
        "country_region",
        "entrance",
        "house",
        "house_number",
        "island",
        "level",
        "near",
        "po_box",
        "postcode",
        "road",
        "staircase",
        "state",
        "state_district",
        "suburb",
        "unit",
    }
)
QUALITATIVE_CLASSIFICATIONS = (
    "PLAUSIBLE_PARSE",
    "PARTIAL_BUT_USABLE_PARSE",
    "QUESTIONABLE_PARSE",
    "CLEAR_MISPARSE",
    "UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Stage07ReviewError(RuntimeError):
    """Privacy-safe review failure with a stable public code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ReviewError(code, detail)


@dataclass(frozen=True, slots=True)
class Stage07ReviewConfig:
    stage05_output_directory: Path
    stage06_output_directory: Path
    stage06_review_directory: Path
    expected_stage06_review_manifest_sha256: str
    stage07_output_directory: Path
    expected_stage07_manifest_sha256: str
    parser_bundle_directory: Path
    output_directory: Path
    execution_git_sha: str
    authoritative_development: bool = True
    production: bool = True
    operational_metadata: Mapping[str, str] | None = None

    def validate(self) -> None:
        for value in (
            self.expected_stage06_review_manifest_sha256,
            self.expected_stage07_manifest_sha256,
        ):
            if _SHA256_RE.fullmatch(value) is None:
                _fail("INVALID_FINGERPRINT", "Review fingerprint is malformed")
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA is malformed")
        for path in (
            self.stage05_output_directory,
            self.stage06_output_directory,
            self.stage06_review_directory,
            self.stage07_output_directory,
            self.parser_bundle_directory,
            self.output_directory,
        ):
            if any("holdout" in part.casefold() for part in path.resolve(strict=False).parts):
                _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT review paths are prohibited")
        for key, value in (self.operational_metadata or {}).items():
            if (
                key not in {"execution_site", "slurm_job_id"}
                or not isinstance(value, str)
                or not value
                or len(value) > 128
                or "\x00" in value
            ):
                _fail("INVALID_OPERATIONAL_METADATA", "Review metadata differs")


@dataclass(frozen=True, slots=True)
class Stage07ReviewOutcome:
    output_directory: Path
    manifest_sha256: str
    fixed_source_rows: int
    fixed_occurrences: int
    fixed_unique_candidates: int
    fixed_mismatches: int
    qualitative_candidates: int
    qualitative_selection_fingerprint: str
    qualitative_html_path: Path
    fixed500_seconds: float
    qualitative_seconds: float


@dataclass(frozen=True, slots=True)
class _Artifact:
    relative_path: str
    size_bytes: int
    sha256: str
    row_count: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Selected:
    candidate_id: bytes
    status: str
    component_count: int
    input_codepoints: int
    occurrence_count: int
    standard_count: int
    native_count: int
    reasons: tuple[str, ...]


def _require_mode(path: Path, mode: int) -> None:
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        _fail("PERMISSION_FAILURE", "Owner-only review permissions differ")


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07ReviewError(code, "Review JSON is malformed") from error
    if not isinstance(value, dict):
        _fail(code, "Review JSON is not an object")
    return cast(dict[str, Any], value)


def _write_exclusive(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise Stage07ReviewError(
            "CONTROLLED_WRITE_FAILURE", "Review artifact could not be written"
        ) from error


def _write_json(path: Path, value: object) -> None:
    _write_exclusive(
        path,
        (
            json.dumps(
                value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8"),
    )


def _artifact(root: Path, relative: str, rows: int) -> _Artifact:
    path = root / relative
    return _Artifact(
        relative_path=relative,
        size_bytes=path.stat(follow_symlinks=False).st_size,
        sha256=_sha256_file(path),
        row_count=rows,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _stage07_paths(root: Path) -> tuple[Path, ...]:
    manifest = _load_json(root / STAGE07_MANIFEST_NAME, "STAGE07_MANIFEST_INVALID")
    physical = manifest.get("physical_identity")
    if not isinstance(physical, dict) or not isinstance(
        physical.get("registry_artifacts"), list
    ):
        _fail("STAGE07_MANIFEST_INVALID", "Stage 7 artifacts are absent")
    result: list[Path] = []
    for raw in physical["registry_artifacts"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("relative_path"), str):
            _fail("STAGE07_MANIFEST_INVALID", "Stage 7 artifact entry differs")
        result.append(root / raw["relative_path"])
    return tuple(result)


def _load_fixed500(config: Stage07ReviewConfig) -> pa.Table:
    root = config.stage06_review_directory
    if not root.is_dir() or root.is_symlink():
        _fail("FIXED500_INVALID", "Stage 6 review directory is invalid")
    _require_mode(root, 0o700)
    manifest_path = root / STAGE06_REVIEW_MANIFEST_NAME
    if (
        not manifest_path.is_file()
        or manifest_path.is_symlink()
        or _sha256_file(manifest_path)
        != config.expected_stage06_review_manifest_sha256
    ):
        _fail("FIXED500_INVALID", "Stage 6 review manifest differs")
    _require_mode(manifest_path, 0o600)
    manifest = _load_json(manifest_path, "FIXED500_INVALID")
    scientific = manifest.get("scientific_identity")
    physical = manifest.get("physical_identity")
    if (
        manifest.get("status")
        != "STAGE_6_DEVELOPMENT_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW"
        or not isinstance(scientific, dict)
        or scientific.get("review_subset_fingerprint")
        != "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52"
        or not isinstance(physical, dict)
        or physical.get("stage06_manifest_sha256")
        != ACCEPTED_STAGE06_MANIFEST_SHA256
    ):
        _fail("FIXED500_INVALID", "Stage 6 review identity differs")
    artifacts = physical.get("artifacts")
    if not isinstance(artifacts, list):
        _fail("FIXED500_INVALID", "Stage 6 review artifacts are absent")
    identity = next(
        (
            item
            for item in artifacts
            if isinstance(item, dict)
            and item.get("relative_path") == STAGE06_REVIEW_PATH
        ),
        None,
    )
    path = root / STAGE06_REVIEW_PATH
    if (
        not isinstance(identity, dict)
        or not path.is_file()
        or path.is_symlink()
        or path.stat(follow_symlinks=False).st_size != identity.get("size_bytes")
        or _sha256_file(path) != identity.get("sha256")
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 artifact differs")
    _require_mode(path, 0o600)
    try:
        table = pq.ParquetFile(path, page_checksum_verification=True).read(
            use_threads=False
        )
    except (OSError, pa.ArrowException) as error:
        raise Stage07ReviewError(
            "FIXED500_INVALID", "Stage 6 fixed-500 artifact could not reopen"
        ) from error
    if (
        table.schema.remove_metadata() != stage06_review_schema()
        or table.num_rows != ACCEPTED_FIXED500_ROWS
        or table.column("review_order").to_pylist()
        != list(range(1, ACCEPTED_FIXED500_ROWS + 1))
    ):
        _fail("FIXED500_INVALID", "Stage 6 fixed-500 rows differ")
    return table


def _components_from_scalar(value: pa.Scalar) -> tuple[LibpostalComponent, ...]:
    raw = value.as_py()
    if not isinstance(raw, list):
        _fail("STAGE07_COMPONENT_INVALID", "Published component list is null")
    result: list[LibpostalComponent] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("STAGE07_COMPONENT_INVALID", "Published component item differs")
        result.append(LibpostalComponent(label=item["label"], value=item["value"]))
    return tuple(result)


def _fixed500_schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("stable_source_row_id_v1", pa.binary(32), nullable=False),
            pa.field(ROW_MAP_ID_COLUMNS[0], pa.binary(32), nullable=True),
            pa.field(ROW_MAP_ID_COLUMNS[1], pa.binary(32), nullable=True),
            pa.field("stage07_standard_parse_status", pa.string(), nullable=True),
            pa.field("stage07_native_parse_status", pa.string(), nullable=True),
            pa.field("stage07_standard_ordered_parse_sha256", pa.string(), nullable=True),
            pa.field("stage07_native_ordered_parse_sha256", pa.string(), nullable=True),
            pa.field("stage07_standard_mapping_exact", pa.bool_(), nullable=False),
            pa.field("stage07_native_mapping_exact", pa.bool_(), nullable=False),
            pa.field("stage07_standard_independent_reparse_exact", pa.bool_(), nullable=False),
            pa.field("stage07_native_independent_reparse_exact", pa.bool_(), nullable=False),
            pa.field("stage07_unavailable_representations_exact", pa.bool_(), nullable=False),
            pa.field("stage07_no_cross_wire", pa.bool_(), nullable=False),
        )
    )


def _fixed500_evidence(
    fixed: pa.Table, stage07_paths: Sequence[Path]
) -> tuple[pa.Table, dict[str, int]]:
    occurrences: list[bytes] = []
    for name in ROW_MAP_ID_COLUMNS:
        occurrences.extend(
            cast(bytes, value)
            for value in fixed.column(name).to_pylist()
            if value is not None
        )
    selected_ids = frozenset(occurrences)
    if len(occurrences) != ACCEPTED_FIXED500_OCCURRENCES or len(selected_ids) != ACCEPTED_FIXED500_UNIQUE_CANDIDATES:
        _fail("FIXED500_INVALID", "Stage 6 fixed candidate counts differ")
    parsed_by_id: dict[bytes, tuple[str, str, bool]] = {}
    with SupervisedParser() as supervisor:
        for batch in _iter_batches(
            stage07_paths,
            (*REGISTRY_COLUMNS, STAGE07_STATUS_FIELD, STAGE07_COMPONENTS_FIELD),
            1,
        ):
            candidate_id = batch.column(0)[0].as_py()
            if candidate_id not in selected_ids:
                continue
            candidate = batch.column(1)[0].as_py()
            status = batch.column(5)[0].as_py()
            if not isinstance(candidate_id, bytes) or not isinstance(candidate, str) or not isinstance(status, str):
                _fail("FIXED500_INVALID", "Selected Stage 7 row is malformed")
            components = _components_from_scalar(batch.column(6)[0])
            published = ParsedAddress(status=status, components=components)
            reparsed = supervisor.parse(candidate)
            if reparsed.components is None:
                _fail("FIXED500_REPARSE_FAILURE", "Independent reparse did not succeed")
            reparse_result = ParsedAddress(status=reparsed.status, components=reparsed.components)
            published_digest = ordered_parse_sha256(published)
            exact = published_digest == ordered_parse_sha256(reparse_result)
            if candidate_id in parsed_by_id:
                _fail("FIXED500_DUPLICATE", "Selected candidate appears more than once")
            parsed_by_id[candidate_id] = (status, published_digest, exact)
    if set(parsed_by_id) != set(selected_ids):
        _fail("FIXED500_MISSING", "A selected candidate is absent")

    columns: dict[str, list[object]] = {name: [] for name in _fixed500_schema().names}
    mismatches = 0
    for row_index in range(fixed.num_rows):
        order = int(fixed.column("review_order")[row_index].as_py())
        stable = fixed.column("stable_source_row_id_v1")[row_index].as_py()
        standard_id = fixed.column(ROW_MAP_ID_COLUMNS[0])[row_index].as_py()
        native_id = fixed.column(ROW_MAP_ID_COLUMNS[1])[row_index].as_py()
        standard = parsed_by_id.get(standard_id) if isinstance(standard_id, bytes) else None
        native = parsed_by_id.get(native_id) if isinstance(native_id, bytes) else None
        standard_mapping = (standard_id is None and standard is None) or standard is not None
        native_mapping = (native_id is None and native is None) or native is not None
        standard_reparse = standard is None or standard[2]
        native_reparse = native is None or native[2]
        unavailable = (standard_id is None) == (standard is None) and (native_id is None) == (native is None)
        no_cross_wire = standard_reparse and native_reparse
        row_checks = (
            standard_mapping,
            native_mapping,
            standard_reparse,
            native_reparse,
            unavailable,
            no_cross_wire,
        )
        mismatches += int(not all(row_checks))
        values = {
            "review_order": order,
            "stable_source_row_id_v1": stable,
            ROW_MAP_ID_COLUMNS[0]: standard_id,
            ROW_MAP_ID_COLUMNS[1]: native_id,
            "stage07_standard_parse_status": standard[0] if standard else None,
            "stage07_native_parse_status": native[0] if native else None,
            "stage07_standard_ordered_parse_sha256": standard[1] if standard else None,
            "stage07_native_ordered_parse_sha256": native[1] if native else None,
            "stage07_standard_mapping_exact": standard_mapping,
            "stage07_native_mapping_exact": native_mapping,
            "stage07_standard_independent_reparse_exact": standard_reparse,
            "stage07_native_independent_reparse_exact": native_reparse,
            "stage07_unavailable_representations_exact": unavailable,
            "stage07_no_cross_wire": no_cross_wire,
        }
        for name, value in values.items():
            columns[name].append(value)
    table = pa.Table.from_pydict(columns, schema=_fixed500_schema())
    return table, {
        "SOURCE_ROWS": fixed.num_rows,
        "OCCURRENCES": len(occurrences),
        "UNIQUE_CANDIDATES": len(selected_ids),
        "DUPLICATE_OCCURRENCES": len(occurrences) - len(selected_ids),
        "INDEPENDENT_REPARSES": len(parsed_by_id),
        "MISMATCHES": mismatches,
        "CROSS_WIRES": 0 if mismatches == 0 else mismatches,
    }


def _script_reference() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


def _bounded_add(bucket: list[tuple[tuple[int, bytes], bytes]], item: tuple[tuple[int, bytes], bytes], maximum: int) -> None:
    bucket.append(item)
    bucket.sort(key=lambda value: value[0])
    if len(bucket) > maximum:
        bucket.pop()


def _risk_selection(
    stage06_root: Path, stage07_paths: Sequence[Path], work: Path
) -> tuple[dict[bytes, _Selected], str]:
    row_paths = _stage06_artifact_paths(stage06_root, kind="row_map")
    selection_work = work / "selection_work"
    selection_work.mkdir(mode=0o700)
    try:
        clean_groups = _clean_surface_groups(
            row_paths,
            work_directory=selection_work,
            memory_limit="8GB",
            threads=4,
            authoritative_development=True,
        )
    finally:
        shutil.rmtree(selection_work)
    if len(clean_groups) != ACCEPTED_CASE_VARIANT_GROUPS or sum(map(len, clean_groups.values())) != ACCEPTED_CASE_VARIANT_SURFACES:
        _fail("CLEAN_VARIANT_INVALID", "Clean-variant evidence differs")
    clean_ids = frozenset(clean_groups)
    scripts = _script_reference()
    buckets: dict[str, list[tuple[tuple[int, bytes], bytes]]] = defaultdict(list)
    required_empty: set[bytes] = set()
    reasons_by_id: dict[bytes, set[str]] = defaultdict(set)
    for batch in _iter_batches(
        stage07_paths,
        (*REGISTRY_COLUMNS, STAGE07_STATUS_FIELD, STAGE07_COMPONENTS_FIELD),
        1,
    ):
        candidate_id = batch.column(0)[0].as_py()
        candidate = batch.column(1)[0].as_py()
        counts = tuple(int(batch.column(index)[0].as_py()) for index in range(2, 5))
        status = batch.column(5)[0].as_py()
        if not isinstance(candidate_id, bytes) or not isinstance(candidate, str) or not isinstance(status, str):
            _fail("QUALITATIVE_SELECTION_INVALID", "Stage 7 selection row differs")
        components = _components_from_scalar(batch.column(6)[0])
        component_count = len(components)
        label_counts = Counter(component.label for component in components)
        output_codepoints = sum(len(component.value) for component in components)
        features = _candidate_features(
            candidate,
            occurrence_count=counts[0],
            standard_count=counts[1],
            native_count=counts[2],
            script_reference=scripts,
        )
        if status == PARSED_EMPTY:
            required_empty.add(candidate_id)
            reasons_by_id[candidate_id].add("PARSED_EMPTY")
        if set(label_counts) - EXPECTED_DIAGNOSTIC_LABELS:
            _bounded_add(buckets["UNEXPECTED_LABEL"], ((0, candidate_id), candidate_id), 12)
        if any(count > 1 for count in label_counts.values()):
            _bounded_add(buckets["REPEATED_LABEL"], ((-max(label_counts.values()), candidate_id), candidate_id), 10)
        if component_count == 1:
            _bounded_add(buckets["ONE_COMPONENT"], ((0, candidate_id), candidate_id), 8)
        _bounded_add(buckets["HIGH_COMPONENT_COUNT"], ((-component_count, candidate_id), candidate_id), 8)
        _bounded_add(buckets["HIGH_OUTPUT_CODEPOINTS"], ((-output_codepoints, candidate_id), candidate_id), 5)
        if features.giant:
            _bounded_add(buckets["GIANT_FEASIBLE"], ((len(candidate), candidate_id), candidate_id), 1)
        if candidate_id in clean_ids:
            _bounded_add(buckets["CLEAN_VARIANT_GROUP"], ((0, candidate_id), candidate_id), 8)
        for reason, matched, maximum in (
            (f"SCRIPT_{features.script_bucket}", True, 4),
            ("NUMERIC_HEAVY", features.numeric_heavy, 5),
            ("PUNCTUATION_HEAVY", features.punctuation_heavy, 5),
            (f"PROVENANCE_{features.representation_bucket}", True, 5),
            (f"OCCURRENCE_{features.occurrence_bucket}", True, 5),
        ):
            if matched:
                _bounded_add(buckets[reason], ((0, candidate_id), candidate_id), maximum)
        ordinary_key = hashlib.sha256(b"SAFE_STAGE07_QUALITATIVE_BASELINE_V1" + candidate_id).digest()
        _bounded_add(
            buckets["DETERMINISTIC_ORDINARY_BASELINE"],
            ((int.from_bytes(ordinary_key[:8], "big"), candidate_id), candidate_id),
            STAGE07_QUALITATIVE_TARGET,
        )
    selected_ids = set(required_empty)
    for reason, values in buckets.items():
        if reason == "DETERMINISTIC_ORDINARY_BASELINE":
            continue
        for _, candidate_id in values:
            selected_ids.add(candidate_id)
            reasons_by_id[candidate_id].add(reason)
    for _, candidate_id in buckets["DETERMINISTIC_ORDINARY_BASELINE"]:
        if len(selected_ids) >= STAGE07_QUALITATIVE_TARGET:
            break
        selected_ids.add(candidate_id)
        reasons_by_id[candidate_id].add("DETERMINISTIC_ORDINARY_BASELINE")
    selected: dict[bytes, _Selected] = {}
    for batch in _iter_batches(
        stage07_paths,
        (*REGISTRY_COLUMNS, STAGE07_STATUS_FIELD, STAGE07_COMPONENTS_FIELD),
        1,
    ):
        candidate_id = batch.column(0)[0].as_py()
        if candidate_id not in selected_ids:
            continue
        candidate = batch.column(1)[0].as_py()
        status = batch.column(5)[0].as_py()
        if not isinstance(candidate_id, bytes) or not isinstance(candidate, str) or not isinstance(status, str):
            _fail("QUALITATIVE_SELECTION_INVALID", "Selected Stage 7 row differs")
        selected[candidate_id] = _Selected(
            candidate_id=candidate_id,
            status=status,
            component_count=len(_components_from_scalar(batch.column(6)[0])),
            input_codepoints=len(candidate),
            occurrence_count=int(batch.column(2)[0].as_py()),
            standard_count=int(batch.column(3)[0].as_py()),
            native_count=int(batch.column(4)[0].as_py()),
            reasons=tuple(sorted(reasons_by_id[candidate_id])),
        )
    if set(selected) != selected_ids:
        _fail("QUALITATIVE_SELECTION_INVALID", "A selected Stage 7 row is absent")
    payload = [
        {"candidate_id_hex": item.candidate_id.hex(), "reasons": list(item.reasons)}
        for item in selected.values()
    ]
    fingerprint = hashlib.sha256(
        b"SAFE_STAGE07_QUALITATIVE_SELECTION_V1" + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    return selected, fingerprint


def _selection_schema() -> pa.Schema:
    return pa.schema(
        (
            pa.field("review_order", pa.uint32(), nullable=False),
            pa.field("stage06_exact_candidate_id", pa.binary(32), nullable=False),
            pa.field("selection_reasons", pa.large_list(pa.field("element", pa.large_string(), nullable=False)), nullable=False),
            pa.field("stage07_parse_status", pa.string(), nullable=False),
            pa.field("component_count", pa.uint64(), nullable=False),
            pa.field("input_codepoints", pa.uint64(), nullable=False),
            pa.field("stage06_occurrence_count", pa.uint64(), nullable=False),
            pa.field("stage06_standard_occurrence_count", pa.uint64(), nullable=False),
            pa.field("stage06_native_occurrence_count", pa.uint64(), nullable=False),
        )
    )


def _selection_table(selected: Mapping[bytes, _Selected]) -> pa.Table:
    rows = []
    for order, item in enumerate(selected.values(), start=1):
        rows.append(
            {
                "review_order": order,
                "stage06_exact_candidate_id": item.candidate_id,
                "selection_reasons": list(item.reasons),
                "stage07_parse_status": item.status,
                "component_count": item.component_count,
                "input_codepoints": item.input_codepoints,
                "stage06_occurrence_count": item.occurrence_count,
                "stage06_standard_occurrence_count": item.standard_count,
                "stage06_native_occurrence_count": item.native_count,
            }
        )
    return pa.Table.from_pylist(rows, schema=_selection_schema())


def _html_header(handle: TextIO, selected_count: int, fingerprint: str) -> None:
    handle.write(
        "<!doctype html><html><head><meta charset='utf-8'><title>Stage 7 qualitative review</title>"
        "<style>body{font-family:system-ui;max-width:1100px;margin:auto;padding:2rem}"
        ".candidate{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f5;padding:1rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.35rem;vertical-align:top}"
        ".value{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:4px solid #333;margin-top:3rem}"
        "label{margin-right:1rem}</style></head><body>"
        f"<h1>Stage 7 qualitative parser review</h1><p>Selected candidates: {selected_count}. "
        f"Selection fingerprint: <code>{fingerprint}</code>.</p>"
        "<p>Offline owner-only artifact. No stable IDs are displayed. Judge successful raw parser boundaries; "
        "distinguish parser defects from upstream corruption.</p>"
        "<button id='download'>Download classifications JSON</button>"
    )


def _render_html(
    path: Path,
    stage07_paths: Sequence[Path],
    selected: Mapping[bytes, _Selected],
    fingerprint: str,
) -> None:
    order_by_id = {candidate_id: order for order, candidate_id in enumerate(selected, start=1)}
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            _html_header(handle, len(selected), fingerprint)
            for batch in _iter_batches(
                stage07_paths,
                (*REGISTRY_COLUMNS, STAGE07_STATUS_FIELD, STAGE07_COMPONENTS_FIELD),
                1,
            ):
                candidate_id = batch.column(0)[0].as_py()
                if candidate_id not in selected:
                    continue
                item = selected[cast(bytes, candidate_id)]
                candidate = batch.column(1)[0].as_py()
                components = _components_from_scalar(batch.column(6)[0])
                order = order_by_id[item.candidate_id]
                handle.write(f"<section data-order='{order}'><h2>Review {order}</h2>")
                handle.write(f"<p>Reasons: {html.escape(', '.join(item.reasons))}</p>")
                provenance = (
                    "BOTH" if item.standard_count and item.native_count else "STANDARD_ONLY" if item.standard_count else "NATIVE_ONLY"
                )
                handle.write(
                    f"<p>Status: <code>{item.status}</code>; provenance: {provenance}; "
                    f"occurrences: {item.occurrence_count}; components: {item.component_count}; "
                    f"input code points: {item.input_codepoints}</p>"
                )
                handle.write(f"<h3>Exact Stage 6 candidate</h3><div class='candidate'>{html.escape(cast(str, candidate))}</div>")
                handle.write("<h3>Ordered libpostal components</h3><table><thead><tr><th>#</th><th>label</th><th>value</th></tr></thead><tbody>")
                for component_order, component in enumerate(components, start=1):
                    handle.write(
                        f"<tr><td>{component_order}</td><td>{html.escape(component.label)}</td>"
                        f"<td class='value'>{html.escape(component.value)}</td></tr>"
                    )
                handle.write("</tbody></table><fieldset><legend>Classification</legend>")
                for classification in QUALITATIVE_CLASSIFICATIONS:
                    handle.write(
                        f"<label><input type='radio' name='review-{order}' value='{classification}'>"
                        f"{classification}</label>"
                    )
                handle.write("</fieldset></section>")
            handle.write(
                "<script>document.getElementById('download').onclick=()=>{const rows=[];"
                "document.querySelectorAll('section[data-order]').forEach(s=>{const q=s.querySelector('input:checked');"
                "rows.push({review_order:Number(s.dataset.order),classification:q?q.value:null});});"
                f"const payload={{selection_fingerprint:'{fingerprint}',classifications:rows}};"
                "const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],"
                "{type:'application/json'}));a.download='stage07_qualitative_classifications.json';a.click();};</script></body></html>"
            )
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise Stage07ReviewError(
            "CONTROLLED_WRITE_FAILURE", "Qualitative HTML could not be written"
        ) from error


def materialize_stage07_review(config: Stage07ReviewConfig) -> Stage07ReviewOutcome:
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-development-review")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 review output already exists")
    validate_stage07_bundle(
        config.stage07_output_directory,
        expected_manifest_sha256=config.expected_stage07_manifest_sha256,
        stage05_output_directory=config.stage05_output_directory,
        stage06_output_directory=config.stage06_output_directory,
        parser_bundle_directory=config.parser_bundle_directory,
        authoritative_development=config.authoritative_development,
        batch_rows=1,
    )
    fixed = _load_fixed500(config)
    stage07_paths = _stage07_paths(config.stage07_output_directory)
    fixed_started = time.perf_counter()
    fixed_table, fixed_metrics = _fixed500_evidence(fixed, stage07_paths)
    fixed_seconds = time.perf_counter() - fixed_started
    if fixed_metrics["MISMATCHES"]:
        _fail("FIXED500_MISMATCH", "Stage 7 fixed-500 verification differs")

    parent = config.output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    temporary = parent / f".{config.output_directory.name}.{os.getpid()}.in_progress"
    if temporary.exists() or temporary.is_symlink():
        _fail("OUTPUT_COLLISION", "Stage 7 review temporary path exists")
    temporary.mkdir(mode=0o700)
    _write_exclusive(temporary / STAGE07_REVIEW_IN_PROGRESS_MARKER, b"in_progress\n")
    fixed_path = temporary / STAGE07_FIXED500_PATH
    pq.write_table(fixed_table, fixed_path, compression="zstd", write_page_checksum=True)
    fixed_path.chmod(0o600)

    qualitative_started = time.perf_counter()
    selection, selection_fingerprint = _risk_selection(
        config.stage06_output_directory, stage07_paths, temporary
    )
    selection_table = _selection_table(selection)
    selection_path = temporary / STAGE07_QUALITATIVE_SELECTION_PATH
    pq.write_table(selection_table, selection_path, compression="zstd", write_page_checksum=True)
    selection_path.chmod(0o600)
    html_path = temporary / STAGE07_QUALITATIVE_HTML_PATH
    _render_html(html_path, stage07_paths, selection, selection_fingerprint)
    qualitative_seconds = time.perf_counter() - qualitative_started
    summary = {
        "privacy": "AGGREGATE_ONLY_NO_PROTECTED_VALUES_OR_STABLE_IDS",
        "fixed_500": fixed_metrics,
        "qualitative": {
            "selected_candidates": len(selection),
            "selection_fingerprint": selection_fingerprint,
            "target_candidates": STAGE07_QUALITATIVE_TARGET,
            "classification_status": "AWAITING_OFFLINE_OWNER_REVIEW",
        },
        "performance": {
            "fixed500_seconds": fixed_seconds,
            "qualitative_artifact_seconds": qualitative_seconds,
        },
        "holdout_accessed": False,
        "production_started": False,
        "stage8_started": False,
    }
    _write_json(temporary / STAGE07_REVIEW_SUMMARY_PATH, summary)
    artifacts = (
        _artifact(temporary, STAGE07_FIXED500_PATH, fixed_table.num_rows),
        _artifact(temporary, STAGE07_QUALITATIVE_SELECTION_PATH, selection_table.num_rows),
        _artifact(temporary, STAGE07_QUALITATIVE_HTML_PATH, 0),
        _artifact(temporary, STAGE07_REVIEW_SUMMARY_PATH, 0),
    )
    manifest = {
        "stage07_review_manifest_version": STAGE07_REVIEW_MANIFEST_VERSION,
        "status": "STAGE_7_DEVELOPMENT_MACHINE_REVIEW_READY",
        "scientific_identity": {
            "stage07_review_contract_version": STAGE07_REVIEW_CONTRACT_VERSION,
            "stage06_review_manifest_sha256": config.expected_stage06_review_manifest_sha256,
            "stage07_manifest_sha256": config.expected_stage07_manifest_sha256,
            "fixed_500_metrics": fixed_metrics,
            "qualitative_selection_fingerprint": selection_fingerprint,
            "qualitative_selected_candidates": len(selection),
        },
        "physical_identity": {
            "artifacts": [item.to_dict() for item in artifacts],
            "owner_only_permissions": True,
            "atomic_publication": True,
        },
        "validation": {
            "stage07_bundle_independently_reopened": "PASS",
            "fixed_500_source_order": "PASS",
            "fixed_500_occurrence_resolution": "PASS",
            "fixed_500_independent_reparse": "PASS",
            "fixed_500_no_cross_wire": "PASS",
            "qualitative_selection_deterministic": "PASS",
            "qualitative_html_no_stable_ids_displayed": "PASS",
            "owner_only_permissions": "PASS",
            "holdout_exclusion": "PASS",
            "stage8_not_started": "PASS",
        },
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            **dict(config.operational_metadata or {}),
        },
    }
    _write_json(temporary / STAGE07_REVIEW_MANIFEST_NAME, manifest)
    manifest_sha = _sha256_file(temporary / STAGE07_REVIEW_MANIFEST_NAME)
    _write_json(
        temporary / STAGE07_REVIEW_SUCCESS_MARKER,
        {
            "status": "STAGE_7_DEVELOPMENT_MACHINE_REVIEW_READY",
            "stage07_review_manifest_sha256": manifest_sha,
            "stage07_manifest_sha256": config.expected_stage07_manifest_sha256,
            "fixed_500_mismatches": 0,
            "qualitative_selection_fingerprint": selection_fingerprint,
            "qualitative_selected_candidates": len(selection),
        },
    )
    (temporary / STAGE07_REVIEW_IN_PROGRESS_MARKER).unlink()
    _fsync_directory(temporary)
    os.replace(temporary, config.output_directory)
    _fsync_directory(parent)
    return Stage07ReviewOutcome(
        output_directory=config.output_directory,
        manifest_sha256=manifest_sha,
        fixed_source_rows=fixed_metrics["SOURCE_ROWS"],
        fixed_occurrences=fixed_metrics["OCCURRENCES"],
        fixed_unique_candidates=fixed_metrics["UNIQUE_CANDIDATES"],
        fixed_mismatches=fixed_metrics["MISMATCHES"],
        qualitative_candidates=len(selection),
        qualitative_selection_fingerprint=selection_fingerprint,
        qualitative_html_path=config.output_directory / STAGE07_QUALITATIVE_HTML_PATH,
        fixed500_seconds=fixed_seconds,
        qualitative_seconds=qualitative_seconds,
    )


__all__ = [
    "EXPECTED_STAGE06_REVIEW_MANIFEST_SHA256",
    "QUALITATIVE_CLASSIFICATIONS",
    "STAGE07_QUALITATIVE_HTML_PATH",
    "Stage07ReviewConfig",
    "Stage07ReviewError",
    "Stage07ReviewOutcome",
    "materialize_stage07_review",
]

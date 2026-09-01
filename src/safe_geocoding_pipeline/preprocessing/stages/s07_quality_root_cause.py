"""Protected, aggregate-only root-cause diagnostic for 18 Stage 7 review cases."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..reporting.stage07 import QUALITATIVE_CLASSIFICATIONS
from ..script_reference import ScriptReference, unicode_script_reference_paths
from .s06_exact_deduplication import REGISTRY_COLUMNS
from .s07_libpostal_adapter import (
    LibpostalComponent,
    ParsedAddress,
    ordered_parse_sha256,
)
from .s07_output_schema import STAGE07_COMPONENTS_FIELD, STAGE07_STATUS_FIELD
from .s07_supervised_parser import SupervisedParser


DIAGNOSTIC_VERSION = "stage07_quality_root_cause_diagnostic_v1"
SELECTION_FINGERPRINT = (
    "1507900b27e4503eb33836c8465217092e9ffb8de2f1b6ef05026690be11a844"
)
TARGET_CLASSIFICATIONS = frozenset({"CLEAR_MISPARSE", "QUESTIONABLE_PARSE"})
EXPECTED_CASES = 18
PARSER_BUNDLE_FINGERPRINT = (
    "f3c6db7e9f11ab75b2207be773e946d531dbba763008d9f7e5036d8c923dc2ae"
)
ROOT_CAUSES = (
    "TRUE_LIBPOSTAL_LABEL_ERROR",
    "TRUE_LIBPOSTAL_BOUNDARY_ERROR",
    "SCRIPT_SPECIFIC_PARSER_WEAKNESS",
    "TRANSLITERATION_OR_ROMANIZATION_DAMAGE",
    "MULTI_ADDRESS_OR_MULTI_RECORD_INPUT",
    "STAGE5_RECONSTRUCTION_ARTIFACT",
    "STAGE3_4_CLEANING_ARTIFACT",
    "SOURCE_CORRUPTION",
    "AMBIGUOUS_BUT_INFORMATION_PRESERVED",
    "OTHER",
)

_PATTERNS = {
    "TRUE_LIBPOSTAL_LABEL_ERROR": re.compile(
        r"mislabel|wrong label|incompatible|assigned .* (?:city|state|road|house|postcode)",
        re.I,
    ),
    "TRUE_LIBPOSTAL_BOUNDARY_ERROR": re.compile(
        r"boundar|split|fragment|inside word|mid-word", re.I
    ),
    "SCRIPT_SPECIFIC_PARSER_WEAKNESS": re.compile(
        r"script[- ]specific|non[- ]latin|hangul|thai|lao|hebrew|greek|"
        r"cyrillic|arabic|persian|cjk|han script|transliterated[- ]script",
        re.I,
    ),
    "TRANSLITERATION_OR_ROMANIZATION_DAMAGE": re.compile(
        r"transliter|romani[sz]", re.I
    ),
    "MULTI_ADDRESS_OR_MULTI_RECORD_INPUT": re.compile(
        r"multi-address|multi-record|concatenat", re.I
    ),
    "STAGE5_RECONSTRUCTION_ARTIFACT": re.compile(r"stage\s*5|reconstruct", re.I),
    "STAGE3_4_CLEANING_ARTIFACT": re.compile(r"stage\s*[34]|cleaning|lowercas", re.I),
    "SOURCE_CORRUPTION": re.compile(
        r"upstream corrupt|source corrupt|malformed source|non-address", re.I
    ),
}
_STAGE8_DETERMINISTIC_RECOVERY = re.compile(
    r"stage\s*8.{0,80}(?:deterministic|straightforward|fixed mapping).{0,80}recover",
    re.I,
)


class Stage07QualityDiagnosticError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07QualityDiagnosticError(code, detail)


@dataclass(frozen=True, slots=True)
class QualityDiagnosticConfig:
    selection_path: Path
    classifications_path: Path
    comments_path: Path
    stage07_registry_paths: tuple[Path, ...]
    output_directory: Path
    execution_git_sha: str
    production: bool = True

    def validate(self) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", self.execution_git_sha) is None:
            _fail("INVALID_GIT_SHA", "Execution Git SHA differs")
        paths = (
            self.selection_path,
            self.classifications_path,
            self.comments_path,
            *self.stage07_registry_paths,
            self.output_directory,
        )
        if any(
            "holdout" in part.casefold()
            for path in paths
            for part in path.resolve(strict=False).parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")
        if not self.stage07_registry_paths:
            _fail("REGISTRY_ABSENT", "Stage 7 registry paths are absent")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07QualityDiagnosticError(
            "REVIEW_ARTIFACT_INVALID", "Review JSON could not be read"
        ) from error


def _require_private(path: Path, mode: int) -> None:
    if path.is_symlink() or not path.exists():
        _fail("PROTECTED_ARTIFACT_INVALID", "Protected artifact is absent")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != mode:
        _fail("PERMISSION_FAILURE", "Protected artifact permissions differ")


def _scripts() -> ScriptReference:
    paths = unicode_script_reference_paths()
    return ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )


def _script_bucket(candidate: str, reference: ScriptReference) -> str:
    scripts = reference.distinctive_scripts(candidate)
    if not scripts:
        return "COMMON_OR_UNKNOWN_ONLY"
    if len(scripts) > 1:
        return "MIXED_SCRIPT"
    return next(iter(scripts)).upper()


def _components(value: pa.Scalar) -> tuple[LibpostalComponent, ...]:
    raw = value.as_py()
    if not isinstance(raw, list):
        _fail("STAGE07_ROW_INVALID", "Component list is absent")
    result: list[LibpostalComponent] = []
    for item in raw:
        if (
            not isinstance(item, dict)
            or set(item) != {"label", "value"}
            or not isinstance(item["label"], str)
            or not isinstance(item["value"], str)
        ):
            _fail("STAGE07_ROW_INVALID", "Component framing differs")
        result.append(LibpostalComponent(label=item["label"], value=item["value"]))
    return tuple(result)


def _strip_whitespace(value: str) -> str:
    return "".join(character for character in value if not character.isspace())


def _lexical_numeric_stream(value: str) -> str:
    return "".join(
        character
        for character in value
        if unicodedata.category(character)[0] in {"L", "M", "N"}
    )


def _ordered_substrings(
    candidate: str, components: tuple[LibpostalComponent, ...]
) -> bool:
    offset = 0
    for component in components:
        found = candidate.find(component.value, offset)
        if found < 0:
            return False
        offset = found + len(component.value)
    return True


def _iter_selected_registry_batches(
    paths: tuple[Path, ...], selected_ids: set[bytes]
) -> Iterator[pa.RecordBatch]:
    """Yield only selected rows; population candidate values never reach Python."""
    dataset = ds.dataset([str(path) for path in paths], format="parquet")
    scanner = dataset.scanner(
        columns=[*REGISTRY_COLUMNS, STAGE07_STATUS_FIELD, STAGE07_COMPONENTS_FIELD],
        filter=ds.field(REGISTRY_COLUMNS[0]).isin(sorted(selected_ids)),
        batch_size=1,
        use_threads=False,
    )
    yield from scanner.to_batches()


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _reason_codes(comment: str, classification: str) -> set[str]:
    codes = {code for code, pattern in _PATTERNS.items() if pattern.search(comment)}
    if classification == "QUESTIONABLE_PARSE" and not (
        {"TRUE_LIBPOSTAL_LABEL_ERROR", "TRUE_LIBPOSTAL_BOUNDARY_ERROR"} & codes
    ):
        codes.add("AMBIGUOUS_BUT_INFORMATION_PRESERVED")
    if not codes:
        codes.add("OTHER")
    return codes


def _selection_fingerprint(selection: pa.Table) -> str:
    required = {
        "review_order",
        "stage06_exact_candidate_id",
        "selection_reasons",
    }
    if selection.num_rows != 120 or not required.issubset(selection.column_names):
        _fail("SELECTION_INVALID", "Immutable selection shape differs")
    rows: list[tuple[int, bytes, list[str]]] = []
    seen_orders: set[int] = set()
    seen_ids: set[bytes] = set()
    for index in range(selection.num_rows):
        order = selection.column("review_order")[index].as_py()
        candidate_id = selection.column("stage06_exact_candidate_id")[index].as_py()
        reasons = selection.column("selection_reasons")[index].as_py()
        if (
            not isinstance(order, int)
            or not isinstance(candidate_id, bytes)
            or len(candidate_id) != 32
            or not isinstance(reasons, list)
            or not reasons
            or not all(isinstance(reason, str) and reason for reason in reasons)
            or order in seen_orders
            or candidate_id in seen_ids
        ):
            _fail("SELECTION_INVALID", "Immutable selection row differs")
        seen_orders.add(order)
        seen_ids.add(candidate_id)
        rows.append((order, candidate_id, reasons))
    if seen_orders != set(range(1, 121)):
        _fail("SELECTION_INVALID", "Immutable review order differs")
    payload = [
        {"candidate_id_hex": candidate_id.hex(), "reasons": reasons}
        for _, candidate_id, reasons in sorted(rows)
    ]
    return hashlib.sha256(
        b"SAFE_STAGE07_QUALITATIVE_SELECTION_V1"
        + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def _stage8_recoverability(*, comment: str, codes: set[str]) -> str:
    true_parser_error = bool(
        {"TRUE_LIBPOSTAL_LABEL_ERROR", "TRUE_LIBPOSTAL_BOUNDARY_ERROR"} & codes
    )
    upstream = bool(
        {
            "TRANSLITERATION_OR_ROMANIZATION_DAMAGE",
            "MULTI_ADDRESS_OR_MULTI_RECORD_INPUT",
            "STAGE5_RECONSTRUCTION_ARTIFACT",
            "STAGE3_4_CLEANING_ARTIFACT",
            "SOURCE_CORRUPTION",
        }
        & codes
    )
    if true_parser_error:
        return "NOT_SAFELY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
    if upstream:
        return "UPSTREAM_INPUT_REQUIRES_NON_STAGE8_REPAIR"
    if _STAGE8_DETERMINISTIC_RECOVERY.search(comment):
        return "DETERMINISTICALLY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
    return "INCONCLUSIVE"


def _controlling_conclusion(records: list[dict[str, object]]) -> str:
    parser_error_cases = sum(
        bool(
            {
                "TRUE_LIBPOSTAL_LABEL_ERROR",
                "TRUE_LIBPOSTAL_BOUNDARY_ERROR",
            }
            & set(cast(list[str], record["root_cause_codes"]))
        )
        for record in records
    )
    script_specific_cases = sum(
        "SCRIPT_SPECIFIC_PARSER_WEAKNESS" in cast(list[str], record["root_cause_codes"])
        for record in records
    )
    upstream_cases = sum(bool(record["upstream_cause_indicated"]) for record in records)
    ambiguous_cases = sum(
        "AMBIGUOUS_BUT_INFORMATION_PRESERVED"
        in cast(list[str], record["root_cause_codes"])
        for record in records
    )
    recoverable_cases = sum(
        record["stage8_recoverability_assessment"]
        == "DETERMINISTICALLY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
        for record in records
    )
    if parser_error_cases:
        if script_specific_cases or upstream_cases or ambiguous_cases:
            return "MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE"
        return "STAGE07_INTRINSIC_LIBPOSTAL_QUALITY_PROBLEM"
    if upstream_cases == len(records):
        return "UPSTREAM_INPUT_QUALITY_PROBLEM"
    if recoverable_cases == len(records):
        return "STAGE08_MAPPING_CAN_RESOLVE_WITHOUT_INFORMATION_LOSS"
    return "EVIDENCE_INCONCLUSIVE"


def run_quality_root_cause_diagnostic(
    config: QualityDiagnosticConfig,
) -> dict[str, object]:
    """Reparse exactly the 18 selected cases and publish protected diagnostics."""
    config.validate()
    if config.production:
        require_goethe_nhr_slurm("stage07-quality-root-cause")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Diagnostic output already exists")
    for path in (
        config.selection_path,
        config.classifications_path,
        config.comments_path,
        *config.stage07_registry_paths,
    ):
        _require_private(path, 0o600)
    selection = pq.ParquetFile(
        config.selection_path, page_checksum_verification=True
    ).read(use_threads=False)
    if _selection_fingerprint(selection) != SELECTION_FINGERPRINT:
        _fail("SELECTION_INVALID", "Immutable selection fingerprint differs")
    classifications = _load_json(config.classifications_path)
    comments = _load_json(config.comments_path)
    if (
        not isinstance(classifications, dict)
        or classifications.get("selection_fingerprint") != SELECTION_FINGERPRINT
        or set(classifications) != {"selection_fingerprint", "classifications"}
        or not isinstance(classifications.get("classifications"), list)
        or not isinstance(comments, list)
    ):
        _fail("REVIEW_ARTIFACT_INVALID", "Review artifact schema differs")
    class_rows = cast(list[Any], classifications["classifications"])
    class_by_order: dict[int, str] = {}
    for row in class_rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"review_order", "classification"}
            or not isinstance(row["review_order"], int)
            or row["classification"] not in QUALITATIVE_CLASSIFICATIONS
            or row["review_order"] in class_by_order
        ):
            _fail("REVIEW_ARTIFACT_INVALID", "Classification row differs")
        class_by_order[row["review_order"]] = row["classification"]
    comment_by_order: dict[int, str] = {}
    for row in comments:
        if (
            not isinstance(row, dict)
            or set(row) != {"review_order", "classification", "comment"}
            or not isinstance(row["review_order"], int)
            or not isinstance(row["comment"], str)
            or not row["comment"]
            or row["classification"] != class_by_order.get(row["review_order"])
            or row["review_order"] in comment_by_order
        ):
            _fail("REVIEW_ARTIFACT_INVALID", "Abstract comment row differs")
        comment_by_order[row["review_order"]] = row["comment"]
    if (
        len(class_by_order) != 120
        or set(class_by_order) != set(range(1, 121))
        or set(comment_by_order) != set(class_by_order)
    ):
        _fail("REVIEW_ARTIFACT_INVALID", "Review coverage differs")

    selected: dict[bytes, dict[str, object]] = {}
    for index in range(selection.num_rows):
        order = int(selection.column("review_order")[index].as_py())
        classification = class_by_order.get(order)
        if classification not in TARGET_CLASSIFICATIONS:
            continue
        candidate_id = selection.column("stage06_exact_candidate_id")[index].as_py()
        reasons = selection.column("selection_reasons")[index].as_py()
        if not isinstance(candidate_id, bytes) or not isinstance(reasons, list):
            _fail("SELECTION_INVALID", "Selected diagnostic row differs")
        selected[candidate_id] = {
            "review_order": order,
            "classification": classification,
            "comment": comment_by_order[order],
            "selection_reasons": tuple(str(reason) for reason in reasons),
        }
    if len(selected) != EXPECTED_CASES:
        _fail("TARGET_COUNT_MISMATCH", "Diagnostic target count differs")

    reference = _scripts()
    records: list[dict[str, object]] = []
    parsed_inputs = 0
    with SupervisedParser() as supervisor:
        for batch in _iter_selected_registry_batches(
            config.stage07_registry_paths, set(selected)
        ):
            if batch.num_rows == 0:
                continue
            candidate_id = batch.column(0)[0].as_py()
            if candidate_id not in selected:
                continue
            candidate = batch.column(1)[0].as_py()
            if not isinstance(candidate_id, bytes) or not isinstance(candidate, str):
                _fail("STAGE07_ROW_INVALID", "Candidate framing differs")
            published_components = _components(batch.column(6)[0])
            published_status = batch.column(5)[0].as_py()
            published = ParsedAddress(
                status=str(published_status), components=published_components
            )
            reparsed = supervisor.parse(candidate)
            if reparsed.components is None:
                _fail("REPARSE_FAILURE", "Frozen parser did not return normally")
            repeated = Counter(component.label for component in published_components)
            meta = selected[candidate_id]
            classification = cast(str, meta["classification"])
            codes = _reason_codes(cast(str, meta["comment"]), classification)
            ordered_exact = _ordered_substrings(candidate, published_components)
            stream_exact = _strip_whitespace(candidate) == _strip_whitespace(
                "".join(component.value for component in published_components)
            )
            label_error = "TRUE_LIBPOSTAL_LABEL_ERROR" in codes
            boundary_error = "TRUE_LIBPOSTAL_BOUNDARY_ERROR" in codes
            upstream = bool(
                {
                    "TRANSLITERATION_OR_ROMANIZATION_DAMAGE",
                    "MULTI_ADDRESS_OR_MULTI_RECORD_INPUT",
                    "STAGE5_RECONSTRUCTION_ARTIFACT",
                    "STAGE3_4_CLEANING_ARTIFACT",
                    "SOURCE_CORRUPTION",
                }
                & codes
            )
            comment = cast(str, meta["comment"])
            stage8_recoverability = _stage8_recoverability(comment=comment, codes=codes)
            component_stream = "".join(
                component.value for component in published_components
            )
            records.append(
                {
                    "review_order": cast(int, meta["review_order"]),
                    "stage06_exact_candidate_id": candidate_id,
                    "classification": classification,
                    "root_cause_codes": sorted(codes),
                    "script_family": _script_bucket(candidate, reference),
                    "mixed_script": len(reference.distinctive_scripts(candidate)) > 1,
                    "representation": (
                        "BOTH"
                        if int(batch.column(3)[0].as_py())
                        and int(batch.column(4)[0].as_py())
                        else "STANDARD"
                        if int(batch.column(3)[0].as_py())
                        else "NATIVE"
                    ),
                    "candidate_codepoints": len(candidate),
                    "component_count": len(published_components),
                    "repeated_label_count": sum(
                        1 for value in repeated.values() if value > 1
                    ),
                    "maximum_label_repetition": max(repeated.values(), default=0),
                    "selection_reasons": list(
                        cast(tuple[str, ...], meta["selection_reasons"])
                    ),
                    "source_information_in_stage6_assessment": (
                        "PRESENT_FOR_REVIEWED_PARSER_DEFECT"
                        if label_error or boundary_error
                        else "UPSTREAM_DAMAGE_INDICATED"
                        if upstream
                        else "INCONCLUSIVE"
                    ),
                    "stage07_row_retains_exact_stage6_candidate": True,
                    "all_component_values_are_ordered_input_substrings": ordered_exact,
                    "non_whitespace_component_stream_equals_input": stream_exact,
                    "lexical_numeric_component_stream_equals_input": (
                        _lexical_numeric_stream(candidate)
                        == _lexical_numeric_stream(component_stream)
                    ),
                    "problem_only_semantic_label_assignment": (
                        label_error and not boundary_error and not upstream
                    ),
                    "mechanical_component_omission_observed": not stream_exact,
                    "information_lost_from_stage07_row": False,
                    "word_or_token_internal_split_reported": boundary_error,
                    "stage8_recoverability_assessment": stage8_recoverability,
                    "upstream_cause_indicated": upstream,
                    "published_ordered_parse_sha256": ordered_parse_sha256(published),
                    "reparse_ordered_parse_sha256": ordered_parse_sha256(
                        ParsedAddress(
                            status=reparsed.status, components=reparsed.components
                        )
                    ),
                    "deterministic_exact_reparse": published.status == reparsed.status
                    and published.components == reparsed.components,
                }
            )
            parsed_inputs += 1
    if parsed_inputs != EXPECTED_CASES:
        _fail("TARGET_COVERAGE_MISMATCH", "Not every target candidate was reparsed")

    root_counts = Counter(
        code
        for record in records
        for code in cast(list[str], record["root_cause_codes"])
    )
    script_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    provenance_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    mixed_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    script_root_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    provenance_root_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    root_classification_cluster: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        script = cast(str, record["script_family"])
        classification = cast(str, record["classification"])
        representation = cast(str, record["representation"])
        mixed = "MIXED_SCRIPT" if record["mixed_script"] else "SINGLE_SCRIPT"
        script_cluster[script][classification] += 1
        provenance_cluster[representation][classification] += 1
        mixed_cluster[mixed][classification] += 1
        for code in cast(list[str], record["root_cause_codes"]):
            script_root_cluster[script][code] += 1
            provenance_root_cluster[representation][code] += 1
            root_classification_cluster[code][classification] += 1
    true_parser_error_cases = sum(
        bool(
            {"TRUE_LIBPOSTAL_LABEL_ERROR", "TRUE_LIBPOSTAL_BOUNDARY_ERROR"}
            & set(cast(list[str], record["root_cause_codes"]))
        )
        for record in records
    )
    aggregate: dict[str, object] = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "selection_fingerprint": SELECTION_FINGERPRINT,
        "parser_bundle_fingerprint": PARSER_BUNDLE_FINGERPRINT,
        "cases": len(records),
        "classification_counts": dict(
            sorted(Counter(cast(str, r["classification"]) for r in records).items())
        ),
        "root_cause_counts": {code: root_counts[code] for code in ROOT_CAUSES},
        "script_classification_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(script_cluster.items())
        },
        "provenance_classification_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(provenance_cluster.items())
        },
        "mixed_script_classification_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(mixed_cluster.items())
        },
        "root_cause_classification_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(root_classification_cluster.items())
        },
        "script_root_cause_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(script_root_cluster.items())
        },
        "provenance_root_cause_counts": {
            key: dict(sorted(value.items()))
            for key, value in sorted(provenance_root_cluster.items())
        },
        "component_stream_preserves_non_whitespace_input": sum(
            bool(r["non_whitespace_component_stream_equals_input"]) for r in records
        ),
        "component_stream_preserves_lexical_numeric_input": sum(
            bool(r["lexical_numeric_component_stream_equals_input"]) for r in records
        ),
        "mechanical_component_omission_observed": sum(
            bool(r["mechanical_component_omission_observed"]) for r in records
        ),
        "information_lost_from_stage07_row": sum(
            bool(r["information_lost_from_stage07_row"]) for r in records
        ),
        "true_libpostal_label_error_cases": sum(
            "TRUE_LIBPOSTAL_LABEL_ERROR" in cast(list[str], r["root_cause_codes"])
            for r in records
        ),
        "true_libpostal_boundary_error_cases": sum(
            "TRUE_LIBPOSTAL_BOUNDARY_ERROR" in cast(list[str], r["root_cause_codes"])
            for r in records
        ),
        "true_libpostal_error_cases": true_parser_error_cases,
        "upstream_input_problem_cases": sum(
            bool(r["upstream_cause_indicated"]) for r in records
        ),
        "stage8_deterministically_recoverable_cases": sum(
            r["stage8_recoverability_assessment"]
            == "DETERMINISTICALLY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
            for r in records
        ),
        "stage8_not_safely_recoverable_without_guessing": sum(
            r["stage8_recoverability_assessment"]
            == "NOT_SAFELY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
            for r in records
        ),
        "stage8_recoverability_inconclusive": sum(
            r["stage8_recoverability_assessment"] == "INCONCLUSIVE" for r in records
        ),
        "stage8_nonmapping_upstream_repair_cases": sum(
            r["stage8_recoverability_assessment"]
            == "UPSTREAM_INPUT_REQUIRES_NON_STAGE8_REPAIR"
            for r in records
        ),
        "clear_case_assessment": {
            "cases": sum(r["classification"] == "CLEAR_MISPARSE" for r in records),
            "source_information_present_for_reviewed_parser_defect": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and r["source_information_in_stage6_assessment"]
                == "PRESENT_FOR_REVIEWED_PARSER_DEFECT"
                for r in records
            ),
            "component_stream_preserves_lexical_numeric_input": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and bool(r["lexical_numeric_component_stream_equals_input"])
                for r in records
            ),
            "semantic_label_only": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and bool(r["problem_only_semantic_label_assignment"])
                for r in records
            ),
            "information_lost_from_stage07_row": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and bool(r["information_lost_from_stage07_row"])
                for r in records
            ),
            "word_or_token_internal_split_reported": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and bool(r["word_or_token_internal_split_reported"])
                for r in records
            ),
            "stage8_deterministically_recoverable": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and r["stage8_recoverability_assessment"]
                == "DETERMINISTICALLY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
                for r in records
            ),
            "stage8_not_safely_recoverable_without_guessing": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and r["stage8_recoverability_assessment"]
                == "NOT_SAFELY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
                for r in records
            ),
            "upstream_cause_indicated": sum(
                r["classification"] == "CLEAR_MISPARSE"
                and bool(r["upstream_cause_indicated"])
                for r in records
            ),
        },
        "deterministic_exact_reparse": sum(
            bool(r["deterministic_exact_reparse"]) for r in records
        ),
        "parser_crashes": supervisor.first_attempt_crashes,
        "worker_restarts": supervisor.worker_restarts,
        "controlling_conclusion": _controlling_conclusion(records),
    }
    schema = pa.schema(
        (
            pa.field("review_order", pa.uint32(), False),
            pa.field("stage06_exact_candidate_id", pa.binary(32), False),
            pa.field("classification", pa.string(), False),
            pa.field("root_cause_codes", pa.list_(pa.string()), False),
            pa.field("script_family", pa.string(), False),
            pa.field("mixed_script", pa.bool_(), False),
            pa.field("representation", pa.string(), False),
            pa.field("candidate_codepoints", pa.uint64(), False),
            pa.field("component_count", pa.uint64(), False),
            pa.field("repeated_label_count", pa.uint64(), False),
            pa.field("maximum_label_repetition", pa.uint64(), False),
            pa.field("selection_reasons", pa.list_(pa.string()), False),
            pa.field("source_information_in_stage6_assessment", pa.string(), False),
            pa.field("stage07_row_retains_exact_stage6_candidate", pa.bool_(), False),
            pa.field(
                "all_component_values_are_ordered_input_substrings", pa.bool_(), False
            ),
            pa.field("non_whitespace_component_stream_equals_input", pa.bool_(), False),
            pa.field(
                "lexical_numeric_component_stream_equals_input", pa.bool_(), False
            ),
            pa.field("problem_only_semantic_label_assignment", pa.bool_(), False),
            pa.field("mechanical_component_omission_observed", pa.bool_(), False),
            pa.field("information_lost_from_stage07_row", pa.bool_(), False),
            pa.field("word_or_token_internal_split_reported", pa.bool_(), False),
            pa.field("stage8_recoverability_assessment", pa.string(), False),
            pa.field("upstream_cause_indicated", pa.bool_(), False),
            pa.field("published_ordered_parse_sha256", pa.string(), False),
            pa.field("reparse_ordered_parse_sha256", pa.string(), False),
            pa.field("deterministic_exact_reparse", pa.bool_(), False),
        )
    )
    old_umask = os.umask(0o077)
    try:
        parent = config.output_directory.parent
        parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        parent.chmod(0o700)
        _require_private(parent, 0o700)
        partial = parent / (f".{config.output_directory.name}.partial.{os.getpid()}")
        if partial.exists() or partial.is_symlink():
            _fail("OUTPUT_COLLISION", "Diagnostic partial output already exists")
        partial.mkdir(mode=0o700)
        table_path = partial / "stage07_quality_root_cause_cases.parquet"
        aggregate_path = partial / "stage07_quality_root_cause_aggregate.json"
        manifest_path = partial / "stage07_quality_root_cause_manifest.json"
        success_path = partial / "STAGE07_QUALITY_ROOT_CAUSE_DIAGNOSTIC_COMPLETE"
        pq.write_table(
            pa.Table.from_pylist(records, schema=schema),
            table_path,
            compression="zstd",
            write_page_checksum=True,
        )
        table_path.chmod(0o600)
        _fsync_file(table_path)
        _write_json(aggregate_path, aggregate)
        manifest = {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "status": "STAGE07_QUALITY_ROOT_CAUSE_DIAGNOSTIC_COMPLETE",
            "selection_fingerprint": SELECTION_FINGERPRINT,
            "parser_bundle_fingerprint": PARSER_BUNDLE_FINGERPRINT,
            "execution_git_sha": config.execution_git_sha,
            "case_count": len(records),
            "aggregate_sha256": _sha256_file(aggregate_path),
            "table_sha256": _sha256_file(table_path),
            "selection_sha256": _sha256_file(config.selection_path),
            "classifications_sha256": _sha256_file(config.classifications_path),
            "comments_sha256": _sha256_file(config.comments_path),
            "stage07_registry_artifacts": [
                {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
                for path in config.stage07_registry_paths
            ],
            "created_at_epoch_seconds": int(time.time()),
            "protected_values_in_aggregate": False,
        }
        _write_json(manifest_path, manifest)
        _write_json(
            success_path,
            {
                "status": "STAGE07_QUALITY_ROOT_CAUSE_DIAGNOSTIC_COMPLETE",
                "manifest_sha256": _sha256_file(manifest_path),
            },
        )
        _fsync_directory(partial)
        os.replace(partial, config.output_directory)
        _fsync_directory(parent)
    finally:
        os.umask(old_umask)
    return aggregate


__all__ = [
    "QualityDiagnosticConfig",
    "Stage07QualityDiagnosticError",
    "run_quality_root_cause_diagnostic",
]

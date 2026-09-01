"""Protected Stage 7 v2 discovery/readiness and fixed-500 metadata audit.

Only the already-authorized 120 qualitative candidates are allowed to expose
candidate/component values to this computation.  Every other operation is over
IDs, counts, provenance, statuses, fingerprints, or already-materialized
metadata.  Git-safe output is aggregate-only.
"""

from __future__ import annotations

import hashlib
import html
import json
import mmap
import os
import re
import stat
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from ..reporting.stage06 import stage06_review_schema
from ..reporting.stage07 import (
    QUALITATIVE_CLASSIFICATIONS,
    _fixed500_schema,
)
from .s06_exact_deduplication import ROW_MAP_ID_COLUMNS
from .s07_component_readiness import (
    COMPONENTS_ABSTAIN,
    COMPONENTS_READY,
    NOT_ATTEMPTED_NOT_ELIGIBLE,
    READINESS_RULE_VERSION,
    decide_component_readiness,
)
from .s07_country_eligibility import PARSER_ELIGIBLE_COUNTRY
from .s07_libpostal_adapter import LibpostalComponent
from .s07_quality_root_cause import SELECTION_FINGERPRINT, _selection_fingerprint


AUDIT_VERSION = "stage07_v2_readiness_design_audit_v2"
EXPECTED_FIXED_ROWS = 500
EXPECTED_FIXED_OCCURRENCES = 937
EXPECTED_FIXED_CANDIDATES = 613
EXPECTED_SELECTION_ROWS = 120
EXPECTED_ROOT_CAUSE_ROWS = 18
EXPECTED_ELIGIBLE_CANDIDATES = 50_685
EXPECTED_UNRESOLVED_CANDIDATES = 1_094

STAGE06_FIXED_SHA256 = (
    "624978c807fce7f9a76383b76d88e52eb85fa9bfbd5c41ced071d4a40c079190"
)
STAGE07_FIXED_SHA256 = (
    "67d259f8094be926677bd9f6b372aad5a90d459d9b10c85f3590dfe177b6ecdf"
)
SELECTION_ARTIFACT_SHA256 = (
    "9e6c83b3d8fc284d905870cbe9c3d51d95e73efb7bd5991664c3da876b0de138"
)
ROOT_CAUSE_ARTIFACT_SHA256 = (
    "4b4d8eaeeafe703b88242a9da9dd62d6937d7957c5798fdebd138c17a9d6524a"
)
ELIGIBILITY_ARTIFACT_SHA256 = (
    "a6ba110c0519873af898dcec0b5188a1db2659fe31aa619613cffcfdf82e499c"
)
QUALITATIVE_HTML_SHA256 = (
    "b681fcc9ea2d971195e503d24cdd1c7339c7cf40dcf74c8a21a79fd84daf93b9"
)

_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class Stage07V2ReadinessAuditError(RuntimeError):
    """Privacy-safe failure with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07V2ReadinessAuditError(code, detail)


@dataclass(frozen=True, slots=True)
class ReadinessAuditConfig:
    stage06_fixed500_path: Path
    stage07_fixed500_path: Path
    qualitative_selection_path: Path
    classifications_path: Path
    root_cause_path: Path
    eligibility_path: Path
    qualitative_html_path: Path
    output_directory: Path
    execution_git_sha: str
    authoritative_development: bool = True

    def validate(self) -> None:
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_SHA", "Execution Git SHA differs")
        paths = (
            self.stage06_fixed500_path,
            self.stage07_fixed500_path,
            self.qualitative_selection_path,
            self.classifications_path,
            self.root_cause_path,
            self.eligibility_path,
            self.qualitative_html_path,
            self.output_directory,
        )
        if any(
            "holdout" in part.casefold()
            for path in paths
            for part in path.resolve(strict=False).parts
        ):
            _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_private_file(path: Path, expected_sha256: str | None = None) -> None:
    if not path.is_file() or path.is_symlink():
        _fail("ARTIFACT_INVALID", "A protected input is absent or a symlink")
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != 0o600:
        _fail("PERMISSION_FAILURE", "A protected input mode differs")
    if expected_sha256 is not None and _sha256_file(path) != expected_sha256:
        _fail("ARTIFACT_SHA256_MISMATCH", "A protected input hash differs")


def _load_classifications(path: Path) -> dict[int, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07V2ReadinessAuditError(
            "CLASSIFICATION_INVALID", "Classification JSON is malformed"
        ) from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"selection_fingerprint", "classifications"}
        or payload.get("selection_fingerprint") != SELECTION_FINGERPRINT
        or not isinstance(payload.get("classifications"), list)
    ):
        _fail("CLASSIFICATION_INVALID", "Classification binding differs")
    result: dict[int, str] = {}
    for raw in cast(list[Any], payload["classifications"]):
        if (
            not isinstance(raw, dict)
            or set(raw) != {"review_order", "classification"}
            or not isinstance(raw["review_order"], int)
            or raw["classification"] not in QUALITATIVE_CLASSIFICATIONS
            or raw["review_order"] in result
        ):
            _fail("CLASSIFICATION_INVALID", "A classification row differs")
        result[raw["review_order"]] = cast(str, raw["classification"])
    if set(result) != set(range(1, EXPECTED_SELECTION_ROWS + 1)):
        _fail("CLASSIFICATION_INVALID", "Classification coverage differs")
    return result


def _fixed_candidate_ids(table: pa.Table) -> tuple[list[bytes], set[bytes]]:
    occurrences: list[bytes] = []
    for name in ROW_MAP_ID_COLUMNS:
        occurrences.extend(
            value
            for value in table.column(name).to_pylist()
            if isinstance(value, bytes)
        )
    unique = set(occurrences)
    if (
        len(occurrences) != EXPECTED_FIXED_OCCURRENCES
        or len(unique) != EXPECTED_FIXED_CANDIDATES
    ):
        _fail("FIXED500_RECONCILIATION_FAILURE", "Fixed candidate totals differ")
    return occurrences, unique


def _candidate_id_fingerprint(candidate_ids: set[bytes]) -> str:
    digest = hashlib.sha256(b"SAFE_STAGE07_V2_FIXED500_CANDIDATE_SET_V1")
    for candidate_id in sorted(candidate_ids):
        digest.update(len(candidate_id).to_bytes(8, "big"))
        digest.update(candidate_id)
    return digest.hexdigest()


def _representation(standard: int, native: int) -> str:
    if standard and native:
        return "BOTH"
    if standard:
        return "STANDARD_ONLY"
    if native:
        return "NATIVE_ONLY"
    _fail("PROVENANCE_INVALID", "A candidate has no representation occurrence")


def _metadata_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("METADATA_INVALID", "An expected integer metadata value differs")
    return value


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


def _cross_tab(records: list[dict[str, object]], key: str) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        classification = cast(str, record["classification"])
        for value in cast(tuple[str, ...], record[key]):
            result[value][classification] += 1
    return {
        reason: dict(sorted(counts.items()))
        for reason, counts in sorted(result.items())
    }


_SECTION_PREFIX = b"<section data-order='"
_CANDIDATE_PREFIX = b"<h3>Exact Stage 6 candidate</h3><div class='candidate'>"
_CANDIDATE_SUFFIX = b"</div>"
_COMPONENTS_PREFIX = (
    b"<h3>Ordered libpostal components</h3><table><thead><tr><th>#</th>"
    b"<th>label</th><th>value</th></tr></thead><tbody>"
)
_COMPONENTS_SUFFIX = b"</tbody></table>"
_ROW_PREFIX = b"<tr><td>"
_ORDER_LABEL_SEPARATOR = b"</td><td>"
_LABEL_VALUE_SEPARATOR = b"</td><td class='value'>"
_ROW_SUFFIX = b"</td></tr>"


@dataclass(frozen=True, slots=True)
class _ReviewHtmlRow:
    review_order: int
    candidate: str
    components: tuple[LibpostalComponent, ...]


@dataclass(frozen=True, slots=True)
class _SelectedReview:
    review_order: int
    candidate_id: bytes
    classification: str
    parse_status: str
    component_count: int
    input_codepoints: int


def _decode_html_text(value: bytes) -> str:
    try:
        return html.unescape(value.decode("utf-8", errors="strict"))
    except UnicodeError as error:
        raise Stage07V2ReadinessAuditError(
            "QUALITATIVE_HTML_INVALID", "Review HTML contains invalid UTF-8"
        ) from error


def _find_required(
    document: mmap.mmap, marker: bytes, start: int, stop: int, detail: str
) -> int:
    offset = document.find(marker, start, stop)
    if offset < 0:
        _fail("QUALITATIVE_HTML_INVALID", detail)
    return offset


def _iter_qualitative_html_rows(path: Path) -> Iterator[_ReviewHtmlRow]:
    """Stream the exact pre-materialized 120-case review without registry access."""
    try:
        with (
            path.open("rb") as handle,
            mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as document,
        ):
            cursor = 0
            for expected_order in range(1, EXPECTED_SELECTION_ROWS + 1):
                marker = f"<section data-order='{expected_order}'>".encode("ascii")
                section = _find_required(
                    document,
                    marker,
                    cursor,
                    len(document),
                    "A required review section is absent",
                )
                if document.find(_SECTION_PREFIX, cursor, section) >= 0:
                    _fail(
                        "QUALITATIVE_HTML_INVALID",
                        "Review section ordering or coverage differs",
                    )
                next_section = document.find(_SECTION_PREFIX, section + len(marker))
                section_stop = next_section if next_section >= 0 else len(document)

                candidate_start = _find_required(
                    document,
                    _CANDIDATE_PREFIX,
                    section + len(marker),
                    section_stop,
                    "A review candidate field is absent",
                ) + len(_CANDIDATE_PREFIX)
                candidate_stop = _find_required(
                    document,
                    _CANDIDATE_SUFFIX,
                    candidate_start,
                    section_stop,
                    "A review candidate field is unterminated",
                )
                candidate = _decode_html_text(document[candidate_start:candidate_stop])

                component_start = _find_required(
                    document,
                    _COMPONENTS_PREFIX,
                    candidate_stop,
                    section_stop,
                    "The ordered component table is absent",
                ) + len(_COMPONENTS_PREFIX)
                component_stop = _find_required(
                    document,
                    _COMPONENTS_SUFFIX,
                    component_start,
                    section_stop,
                    "The ordered component table is unterminated",
                )
                components: list[LibpostalComponent] = []
                row_cursor = component_start
                while True:
                    row_start = document.find(_ROW_PREFIX, row_cursor, component_stop)
                    if row_start < 0:
                        break
                    order_start = row_start + len(_ROW_PREFIX)
                    order_stop = _find_required(
                        document,
                        _ORDER_LABEL_SEPARATOR,
                        order_start,
                        component_stop,
                        "A component order field is malformed",
                    )
                    try:
                        component_order = int(document[order_start:order_stop])
                    except ValueError as error:
                        raise Stage07V2ReadinessAuditError(
                            "QUALITATIVE_HTML_INVALID",
                            "A component order value is malformed",
                        ) from error
                    if component_order != len(components) + 1:
                        _fail(
                            "QUALITATIVE_HTML_INVALID",
                            "Ordered component framing differs",
                        )
                    label_start = order_stop + len(_ORDER_LABEL_SEPARATOR)
                    label_stop = _find_required(
                        document,
                        _LABEL_VALUE_SEPARATOR,
                        label_start,
                        component_stop,
                        "A component label field is malformed",
                    )
                    value_start = label_stop + len(_LABEL_VALUE_SEPARATOR)
                    value_stop = _find_required(
                        document,
                        _ROW_SUFFIX,
                        value_start,
                        component_stop,
                        "A component value field is malformed",
                    )
                    components.append(
                        LibpostalComponent(
                            label=_decode_html_text(document[label_start:label_stop]),
                            value=_decode_html_text(document[value_start:value_stop]),
                        )
                    )
                    row_cursor = value_stop + len(_ROW_SUFFIX)
                if row_cursor != component_stop:
                    trailing = document[row_cursor:component_stop]
                    if trailing:
                        _fail(
                            "QUALITATIVE_HTML_INVALID",
                            "Unexpected ordered component table content exists",
                        )
                yield _ReviewHtmlRow(
                    review_order=expected_order,
                    candidate=candidate,
                    components=tuple(components),
                )
                cursor = component_stop + len(_COMPONENTS_SUFFIX)
            if document.find(_SECTION_PREFIX, cursor) >= 0:
                _fail(
                    "QUALITATIVE_HTML_INVALID",
                    "Unexpected additional review sections exist",
                )
    except OSError as error:
        raise Stage07V2ReadinessAuditError(
            "QUALITATIVE_HTML_INVALID", "Review HTML could not be read"
        ) from error


def run_v2_readiness_design_audit(
    config: ReadinessAuditConfig,
) -> dict[str, object]:
    """Publish aggregate discovery-detector and fixed-500 suitability evidence."""
    config.validate()
    if config.authoritative_development:
        require_goethe_nhr_slurm("stage07-v2-readiness-design-audit")
    if config.output_directory.exists() or config.output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Audit output already exists")
    for path, expected in (
        (config.stage06_fixed500_path, STAGE06_FIXED_SHA256),
        (config.stage07_fixed500_path, STAGE07_FIXED_SHA256),
        (config.qualitative_selection_path, SELECTION_ARTIFACT_SHA256),
        (config.root_cause_path, ROOT_CAUSE_ARTIFACT_SHA256),
        (config.eligibility_path, ELIGIBILITY_ARTIFACT_SHA256),
        (config.qualitative_html_path, QUALITATIVE_HTML_SHA256),
        (config.classifications_path, None),
    ):
        _require_private_file(path, expected)

    stage06_fixed = pq.ParquetFile(
        config.stage06_fixed500_path, page_checksum_verification=True
    ).read(use_threads=False)
    stage07_fixed = pq.ParquetFile(
        config.stage07_fixed500_path, page_checksum_verification=True
    ).read(use_threads=False)
    if (
        stage06_fixed.schema.remove_metadata() != stage06_review_schema()
        or stage07_fixed.schema.remove_metadata() != _fixed500_schema()
        or stage06_fixed.num_rows != EXPECTED_FIXED_ROWS
        or stage07_fixed.num_rows != EXPECTED_FIXED_ROWS
        or not stage06_fixed.column("review_order").equals(
            stage07_fixed.column("review_order")
        )
    ):
        _fail("FIXED500_ARTIFACT_INVALID", "Fixed-500 shape or lineage differs")
    _, fixed_ids = _fixed_candidate_ids(stage06_fixed)
    _, stage07_fixed_ids = _fixed_candidate_ids(stage07_fixed)
    if fixed_ids != stage07_fixed_ids:
        _fail("FIXED500_IDENTITY_MISMATCH", "Stage 6/7 candidate sets differ")

    selection = pq.ParquetFile(
        config.qualitative_selection_path, page_checksum_verification=True
    ).read(use_threads=False)
    if _selection_fingerprint(selection) != SELECTION_FINGERPRINT:
        _fail("SELECTION_INVALID", "Qualitative selection fingerprint differs")
    classifications = _load_classifications(config.classifications_path)
    selected_by_id: dict[bytes, _SelectedReview] = {}
    selected_by_order: dict[int, _SelectedReview] = {}
    for index in range(selection.num_rows):
        order = selection.column("review_order")[index].as_py()
        candidate_id = selection.column("stage06_exact_candidate_id")[index].as_py()
        parse_status = selection.column("stage07_parse_status")[index].as_py()
        component_count = selection.column("component_count")[index].as_py()
        input_codepoints = selection.column("input_codepoints")[index].as_py()
        if (
            not isinstance(order, int)
            or not isinstance(candidate_id, bytes)
            or not isinstance(parse_status, str)
            or not isinstance(component_count, int)
            or not isinstance(input_codepoints, int)
            or candidate_id in selected_by_id
            or order in selected_by_order
        ):
            _fail("SELECTION_INVALID", "A qualitative selection row differs")
        selected = _SelectedReview(
            review_order=order,
            candidate_id=candidate_id,
            classification=classifications[order],
            parse_status=parse_status,
            component_count=component_count,
            input_codepoints=input_codepoints,
        )
        selected_by_id[candidate_id] = selected
        selected_by_order[order] = selected
    if set(selected_by_order) != set(range(1, EXPECTED_SELECTION_ROWS + 1)):
        _fail("SELECTION_INVALID", "Qualitative review ordering differs")
    selected_ids = set(selected_by_id)

    root_cause = pq.ParquetFile(
        config.root_cause_path, page_checksum_verification=True
    ).read(use_threads=False)
    if root_cause.num_rows != EXPECTED_ROOT_CAUSE_ROWS:
        _fail("ROOT_CAUSE_INVALID", "Root-cause row count differs")
    root_by_id: dict[bytes, dict[str, object]] = {}
    for index in range(root_cause.num_rows):
        row = {
            name: root_cause.column(name)[index].as_py()
            for name in root_cause.column_names
        }
        candidate_id = row.get("stage06_exact_candidate_id")
        if not isinstance(candidate_id, bytes) or candidate_id not in selected_ids:
            _fail("ROOT_CAUSE_INVALID", "Root-cause identity differs")
        root_by_id[candidate_id] = row
    if len(root_by_id) != EXPECTED_ROOT_CAUSE_ROWS:
        _fail("ROOT_CAUSE_INVALID", "Root-cause identities are duplicated")

    eligibility = pq.ParquetFile(
        config.eligibility_path, page_checksum_verification=True
    ).read(use_threads=False)
    required_eligibility = {
        "candidate_id",
        "standard_occurrence_count",
        "native_occurrence_count",
        "country_provenance_status",
        "unanimous_country_code",
        "libpostal_eligibility",
        "stage07_parse_status",
    }
    if not required_eligibility.issubset(eligibility.column_names):
        _fail("ELIGIBILITY_INVALID", "Eligibility columns differ")
    eligibility_by_id: dict[bytes, dict[str, object]] = {}
    eligible_count = 0
    for index in range(eligibility.num_rows):
        candidate_id = eligibility.column("candidate_id")[index].as_py()
        if not isinstance(candidate_id, bytes):
            _fail("ELIGIBILITY_INVALID", "Eligibility identity differs")
        row = {
            name: eligibility.column(name)[index].as_py()
            for name in required_eligibility
        }
        if row["libpostal_eligibility"] == PARSER_ELIGIBLE_COUNTRY:
            eligible_count += 1
        if candidate_id in fixed_ids or candidate_id in selected_ids:
            eligibility_by_id[candidate_id] = row
    if (
        eligibility.num_rows != 51_779
        or eligible_count != EXPECTED_ELIGIBLE_CANDIDATES
        or eligibility.num_rows - eligible_count != EXPECTED_UNRESOLVED_CANDIDATES
        or set(eligibility_by_id) != fixed_ids | selected_ids
    ):
        _fail("ELIGIBILITY_RECONCILIATION_FAILURE", "Eligibility totals differ")

    discovery_records: list[dict[str, object]] = []
    seen_registry_ids: set[bytes] = set()
    for html_row in _iter_qualitative_html_rows(config.qualitative_html_path):
        selected = selected_by_order[html_row.review_order]
        candidate_id = selected.candidate_id
        candidate = html_row.candidate
        if (
            len(candidate) != selected.input_codepoints
            or len(html_row.components) != selected.component_count
        ):
            _fail(
                "QUALITATIVE_HTML_INVALID",
                "Review HTML candidate or component counts differ from selection",
            )
        meta = eligibility_by_id[candidate_id]
        applicability = cast(str, meta["libpostal_eligibility"])
        published_status = selected.parse_status
        if meta["stage07_parse_status"] != published_status:
            _fail("SELECTION_INVALID", "Selected parse status binding differs")
        if applicability == PARSER_ELIGIBLE_COUNTRY:
            components = html_row.components
            technical_status = published_status
        else:
            components = None
            technical_status = NOT_ATTEMPTED_NOT_ELIGIBLE
        decision = decide_component_readiness(
            parser_applicability=applicability,
            technical_status=technical_status,
            candidate=candidate,
            components=components,
            standard_occurrence_count=_metadata_int(meta["standard_occurrence_count"]),
            native_occurrence_count=_metadata_int(meta["native_occurrence_count"]),
        )
        discovery_records.append(
            {
                "review_order": selected.review_order,
                "stage06_exact_candidate_id": candidate_id,
                "classification": selected.classification,
                "representation": _representation(
                    _metadata_int(meta["standard_occurrence_count"]),
                    _metadata_int(meta["native_occurrence_count"]),
                ),
                "parser_applicability": applicability,
                "technical_status_v2": technical_status,
                "component_readiness": decision.status,
                "readiness_reason_codes": decision.reason_codes,
                "structural_reason_codes": (
                    decision.signals.reason_codes if decision.signals else ()
                ),
            }
        )
        seen_registry_ids.add(candidate_id)
    if seen_registry_ids != selected_ids:
        _fail("REGISTRY_COVERAGE_FAILURE", "Not every authorized row was evaluated")

    fixed_metadata: list[dict[str, object]] = []
    for candidate_id in sorted(fixed_ids):
        meta = eligibility_by_id[candidate_id]
        fixed_metadata.append(
            {
                "stage06_exact_candidate_id": candidate_id,
                "representation": _representation(
                    _metadata_int(meta["standard_occurrence_count"]),
                    _metadata_int(meta["native_occurrence_count"]),
                ),
                "country_provenance_status": meta["country_provenance_status"],
                "unanimous_country_code": meta["unanimous_country_code"],
                "libpostal_eligibility": meta["libpostal_eligibility"],
                "overlaps_existing_120": candidate_id in selected_ids,
                "overlaps_existing_18": candidate_id in root_by_id,
            }
        )

    output_parent = config.output_directory.parent
    output_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_parent.chmod(0o700)
    config.output_directory.mkdir(mode=0o700)
    discovery_path = config.output_directory / "stage07_v2_discovery_signals.parquet"
    fixed_path = config.output_directory / "stage07_v2_fixed500_metadata.parquet"
    pq.write_table(
        pa.Table.from_pylist(discovery_records),
        discovery_path,
        compression="zstd",
        write_page_checksum=True,
    )
    pq.write_table(
        pa.Table.from_pylist(fixed_metadata),
        fixed_path,
        compression="zstd",
        write_page_checksum=True,
    )
    discovery_path.chmod(0o600)
    fixed_path.chmod(0o600)

    readiness_counts = Counter(
        cast(str, record["component_readiness"]) for record in discovery_records
    )
    readiness_by_classification: dict[str, Counter[str]] = defaultdict(Counter)
    for record in discovery_records:
        readiness_by_classification[cast(str, record["classification"])][
            cast(str, record["component_readiness"])
        ] += 1
    fixed_representation = Counter(
        cast(str, record["representation"]) for record in fixed_metadata
    )
    fixed_eligibility = Counter(
        cast(str, record["libpostal_eligibility"]) for record in fixed_metadata
    )
    fixed_country_codes = {
        record["unanimous_country_code"]
        for record in fixed_metadata
        if isinstance(record["unanimous_country_code"], str)
    }

    clear_ids = {
        candidate_id
        for candidate_id, selected in selected_by_id.items()
        if selected.classification == "CLEAR_MISPARSE"
    }
    predicted_by_id = {
        cast(bytes, record["stage06_exact_candidate_id"]): cast(
            str, record["component_readiness"]
        )
        for record in discovery_records
    }
    boundary_clear_ids = {
        candidate_id
        for candidate_id, row in root_by_id.items()
        if row.get("classification") == "CLEAR_MISPARSE"
        and bool(row.get("word_or_token_internal_split_reported"))
    }
    label_only_clear_ids = {
        candidate_id
        for candidate_id, row in root_by_id.items()
        if row.get("classification") == "CLEAR_MISPARSE"
        and bool(row.get("problem_only_semantic_label_assignment"))
    }

    aggregate: dict[str, object] = {
        "audit_version": AUDIT_VERSION,
        "scope": "EXISTING_AUTHORIZED_120_VALUES_PLUS_METADATA_ONLY_FIXED500",
        "semantic_input": {
            "source": "EXISTING_OWNER_ONLY_QUALITATIVE_REVIEW_HTML",
            "sha256": QUALITATIVE_HTML_SHA256,
            "selected_candidates": EXPECTED_SELECTION_ROWS,
            "authoritative_registry_nested_scan": False,
        },
        "readiness_rule_version": READINESS_RULE_VERSION,
        "fixed500": {
            "row_selection_fingerprint": "014f7c1373380b265f34e2ecb76614161b320e2bb972befb8f53994cc5a1dd52",
            "stage06_review_artifact_sha256": STAGE06_FIXED_SHA256,
            "stage06_review_manifest_sha256": "1eda47b375a432788e5f8366ce73e5364fdf97efac1742bd95981a15b87c0fb1",
            "stage07_fixed500_artifact_sha256": STAGE07_FIXED_SHA256,
            "source_rows": EXPECTED_FIXED_ROWS,
            "occurrences": EXPECTED_FIXED_OCCURRENCES,
            "unique_candidates": EXPECTED_FIXED_CANDIDATES,
            "candidate_set_fingerprint": _candidate_id_fingerprint(fixed_ids),
            "representation_counts": dict(sorted(fixed_representation.items())),
            "eligibility_counts": dict(sorted(fixed_eligibility.items())),
            "unanimous_country_count": len(fixed_country_codes),
            "overlap_existing_120": len(fixed_ids & selected_ids),
            "overlap_existing_18": len(fixed_ids & set(root_by_id)),
            "remaining_unreviewed_candidates": len(fixed_ids - selected_ids),
            "candidate_script_metadata_available": False,
            "candidate_length_metadata_available": False,
            "candidate_structural_signal_metadata_available": False,
        },
        "discovery": {
            "selection_fingerprint": SELECTION_FINGERPRINT,
            "selected_candidates": EXPECTED_SELECTION_ROWS,
            "readiness_counts": dict(sorted(readiness_counts.items())),
            "readiness_by_classification": {
                key: dict(sorted(value.items()))
                for key, value in sorted(readiness_by_classification.items())
            },
            "reason_by_classification": _cross_tab(
                discovery_records, "readiness_reason_codes"
            ),
            "structural_signal_by_classification": _cross_tab(
                discovery_records, "structural_reason_codes"
            ),
            "clear_misparse_cases": len(clear_ids),
            "clear_misparse_abstained": sum(
                predicted_by_id[item] == COMPONENTS_ABSTAIN for item in clear_ids
            ),
            "clear_misparse_leaked_ready": sum(
                predicted_by_id[item] == COMPONENTS_READY for item in clear_ids
            ),
            "boundary_clear_cases": len(boundary_clear_ids),
            "boundary_clear_abstained": sum(
                predicted_by_id[item] == COMPONENTS_ABSTAIN
                for item in boundary_clear_ids
            ),
            "label_only_clear_cases": len(label_only_clear_ids),
            "label_only_clear_abstained": sum(
                predicted_by_id[item] == COMPONENTS_ABSTAIN
                for item in label_only_clear_ids
            ),
            "label_only_clear_leaked_ready": sum(
                predicted_by_id[item] == COMPONENTS_READY
                for item in label_only_clear_ids
            ),
        },
        "privacy": {
            "candidate_values_read": EXPECTED_SELECTION_ROWS,
            "candidate_values_read_outside_authorized_120": 0,
            "component_streams_read": EXPECTED_SELECTION_ROWS,
            "component_streams_read_outside_authorized_120": 0,
            "authoritative_registry_rows_scanned": 0,
            "authoritative_registry_nested_rows_decoded": 0,
            "fixed500_nonoverlap_values_read": 0,
            "protected_values_in_aggregate": False,
            "holdout_accessed": False,
            "production_accessed": False,
            "parser_calls": 0,
            "network_calls": 0,
        },
    }
    aggregate_path = config.output_directory / "stage07_v2_readiness_aggregate.json"
    _write_json(aggregate_path, aggregate)
    manifest = {
        "version": "stage07_v2_readiness_design_audit_manifest_v2",
        "status": "STAGE07_V2_READINESS_DESIGN_AUDIT_COMPLETE",
        "execution_git_sha": config.execution_git_sha,
        "artifacts": [
            {
                "relative_path": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for path in (discovery_path, fixed_path, aggregate_path)
        ],
        "owner_only": True,
        "protected_values_in_aggregate": False,
    }
    manifest_path = config.output_directory / "stage07_v2_readiness_manifest.json"
    _write_json(manifest_path, manifest)
    _write_json(
        config.output_directory / "_SUCCESS.json",
        {
            "status": "STAGE07_V2_READINESS_DESIGN_AUDIT_COMPLETE",
            "manifest_sha256": _sha256_file(manifest_path),
            "aggregate_sha256": _sha256_file(aggregate_path),
        },
    )
    for path in config.output_directory.iterdir():
        path.chmod(0o600)
    directory_descriptor = os.open(config.output_directory, os.O_RDONLY)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    return aggregate


__all__ = [
    "AUDIT_VERSION",
    "ReadinessAuditConfig",
    "Stage07V2ReadinessAuditError",
    "run_v2_readiness_design_audit",
]

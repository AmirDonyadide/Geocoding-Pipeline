from __future__ import annotations

import json
import os
import re
import shutil
import textwrap
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pyarrow as pa
import pyarrow.parquet as pq

from .review import (
    canonicalize_manual_review_reason_codes,
    hashed_review_id,
    manual_review_schema,
)
from .review_progress import (
    REVIEWER_ONE_ID,
    REVIEWER_TWO_ID,
    ProgressBinding,
    ReviewAssignment,
    ReviewProgressStore,
    current_interface_fingerprint,
    current_repository_commit,
    file_sha256,
)
from .review_v2 import (
    ALL_REVIEW_LABEL_FIELDS,
    COMPONENT_LABEL_FIELDS,
    COMPONENT_LABEL_VALUES,
    CONFLICT_LABEL_VALUES,
    ERROR_CONDITION_LABEL_FIELDS,
    ERROR_CONDITION_LABEL_VALUES,
    OVERALL_LABEL_VALUES,
    REVIEWED_PARSER_COMMIT,
)
from .review import MANUAL_REVIEW_REASON_CODES_V1

RAW_REVIEW_FIELDS: Final = (
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
SELECTED_COMPONENT_FIELDS: Final = (
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
    "locality_native_clean",
    "region_native_clean",
    "country_native_clean",
)
CORE_DIAGNOSTIC_FIELDS: Final = (
    "address_parse_status",
    "address_completeness_class",
    "diagnostic_evaluation_status",
    "address_conflict_flags",
    "address_diagnostic_flags",
    "postcode_diagnostic_flags",
    "skipped_oversized_fields",
    "country_parse_method",
    "country_parse_confidence",
    "is_po_box",
    "is_historical",
    "probable_non_physical_address",
    "possible_company_only",
    "selected_component_provenance",
)
PROTECTED_CONTEXT_REQUIRED_COLUMNS: Final = (
    "stable_source_row_id_v1",
    *RAW_REVIEW_FIELDS,
    "phase03_core_json",
    "phase03_evidence_json",
)
_V1_LABEL_FIELDS = (
    "street_label",
    "house_number_label",
    "unit_floor_building_label",
    "organization_address_role_label",
    "postcode_locality_region_country_label",
    "conflict_correctness_label",
    "parser_overreach_label",
    "missed_information_label",
    "unsafe_handling_label",
    "overall_parse_acceptability_label",
)
REVIEW_LABEL_HELP: Final = (
    "COMPONENT: CORRECT=selected correctly; INCORRECT=selected but wrong; "
    "MISSED=safely extractable but not selected; NOT_PRESENT=no extractable "
    "instance; CANNOT_ASSESS=unreliable judgment.",
    "ERROR CONDITIONS: ABSENT, PRESENT, or CANNOT_ASSESS.",
    "CONFLICT: CORRECT, INCORRECT, NOT_APPLICABLE, or CANNOT_ASSESS.",
    "OVERALL: ACCEPTABLE, NOT_ACCEPTABLE, or CANNOT_ASSESS. ACCEPTABLE does "
    "not require every component to be CORRECT.",
)


class CursesInterfaceUnavailable(RuntimeError):
    """Raised only when the host terminal cannot run the optional curses UI."""


def _reject_locked_path(path: Path) -> None:
    if any("locked" in part.casefold() for part in path.parts):
        raise ValueError(
            "LOCKED paths are prohibited in the DEVELOPMENT review interface"
        )


def _require_owner_only(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("review artifacts may not be symbolic links")
    if path.stat().st_mode & 0o077:
        raise ValueError("review artifacts and directories must be owner-only")
    if path.parent.stat().st_mode & 0o077:
        raise ValueError("review artifact parent directory must be owner-only")


def _source_path_identity(path: Path) -> str:
    resolved = path.resolve(strict=True)
    repository_root = Path(__file__).resolve().parents[3]
    try:
        return resolved.relative_to(repository_root).as_posix()
    except ValueError:
        return str(resolved)


@dataclass(frozen=True, slots=True)
class ValidatedReviewInputs:
    context_path: Path
    portable_v1_path: Path
    context_table: pa.Table
    portable_rows: tuple[dict[str, Any], ...]
    hashed_id_to_context_index: Mapping[str, int]
    binding: ProgressBinding
    designated_double_review_ids: frozenset[str]


def validate_review_inputs(
    context_path: Path,
    portable_v1_path: Path,
    *,
    interface_implementation_commit: str,
    interface_implementation_fingerprint: str,
    expected_review_count: int = 800,
    expected_double_review_count: int = 200,
    require_owner_only: bool = True,
) -> ValidatedReviewInputs:
    _reject_locked_path(context_path)
    _reject_locked_path(portable_v1_path)
    if context_path == portable_v1_path:
        raise ValueError("protected context and portable v1 inputs must differ")
    for path in (context_path, portable_v1_path):
        if not path.is_file():
            raise FileNotFoundError("required review input artifact is missing")
        if require_owner_only:
            _require_owner_only(path)

    context_file = pq.ParquetFile(
        context_path, page_checksum_verification=True, pre_buffer=True
    )
    labels_file = pq.ParquetFile(
        portable_v1_path, page_checksum_verification=True, pre_buffer=True
    )
    if (
        labels_file.schema_arrow.remove_metadata()
        != manual_review_schema().remove_metadata()
    ):
        raise ValueError("portable review v1 schema mismatch")
    if context_file.metadata.num_rows != expected_review_count:
        raise ValueError("protected review context row count mismatch")
    if labels_file.metadata.num_rows != expected_review_count:
        raise ValueError("portable review v1 row count mismatch")
    missing = set(PROTECTED_CONTEXT_REQUIRED_COLUMNS) - set(
        context_file.schema_arrow.names
    )
    if missing:
        raise ValueError("protected review context schema is incomplete")

    context = context_file.read(use_threads=False)
    labels = labels_file.read(use_threads=False).to_pylist()
    if len(labels) != expected_review_count:
        raise ValueError("portable v1 labels did not read completely")
    hashed_ids: list[str] = []
    pilot_versions = {str(row["pilot_version"]) for row in labels}
    if len(pilot_versions) != 1:
        raise ValueError("portable v1 contains multiple pilot versions")
    pilot_version = next(iter(pilot_versions))
    for row in labels:
        if row["sample_partition"] != "DEVELOPMENT":
            raise ValueError("portable review input contains non-DEVELOPMENT rows")
        if row["reviewer_id"] != "" or row["review_round"] != 1:
            raise ValueError("portable v1 input is not an unused review template")
        if any(row[field] is not None for field in _V1_LABEL_FIELDS):
            raise ValueError("portable v1 review template already contains labels")
        if (
            row["reason_codes"]
            or row["adjudicated_label"] is not None
            or row["adjudicator_id"] is not None
        ):
            raise ValueError("portable v1 review template is not empty")
        hashed_value = str(row["hashed_review_id"])
        if not re.fullmatch(r"[0-9a-f]{64}", hashed_value):
            raise ValueError("portable v1 hashed review ID is invalid")
        hashed_ids.append(hashed_value)
    if len(set(hashed_ids)) != expected_review_count:
        raise ValueError("portable v1 hashed review identities are not unique")
    designated = {
        str(row["hashed_review_id"])
        for row in labels
        if bool(row["is_independent_review"])
    }
    if len(designated) != expected_double_review_count:
        raise ValueError("independent double-review designation count mismatch")

    context_mapping: dict[str, int] = {}
    stable_ids = context["stable_source_row_id_v1"].to_pylist()
    for index, raw_identity in enumerate(stable_ids):
        identity = bytes(raw_identity)
        if len(identity) != 32:
            raise ValueError("protected context stable identity is invalid")
        hashed_value = hashed_review_id(identity, pilot_version)
        if hashed_value in context_mapping:
            raise ValueError("protected context contains duplicate review identity")
        context_mapping[hashed_value] = index
        core = json.loads(str(context["phase03_core_json"][index].as_py()))
        evidence = json.loads(str(context["phase03_evidence_json"][index].as_py()))
        if not isinstance(core, dict) or not isinstance(evidence, list):
            raise ValueError("protected Phase 3 context JSON has invalid shape")
        if any(not isinstance(item, dict) for item in evidence):
            raise ValueError("protected Phase 3 evidence JSON has invalid row shape")
    if set(context_mapping) != set(hashed_ids):
        raise ValueError(
            "protected context and portable v1 identities do not reconcile"
        )

    binding = ProgressBinding(
        pilot_version=pilot_version,
        protected_context_path=_source_path_identity(context_path),
        protected_context_sha256=file_sha256(context_path),
        protected_context_size_bytes=context_path.stat().st_size,
        portable_v1_path=_source_path_identity(portable_v1_path),
        portable_v1_sha256=file_sha256(portable_v1_path),
        portable_v1_size_bytes=portable_v1_path.stat().st_size,
        reviewed_parser_commit=REVIEWED_PARSER_COMMIT,
        interface_implementation_commit=interface_implementation_commit,
        interface_implementation_fingerprint=interface_implementation_fingerprint,
    )
    binding.validate()
    return ValidatedReviewInputs(
        context_path,
        portable_v1_path,
        context,
        tuple(labels),
        context_mapping,
        binding,
        frozenset(designated),
    )


def initialize_review_workspace(
    context_path: Path,
    portable_v1_path: Path,
    output_directory: Path,
    *,
    interface_implementation_commit: str,
    interface_implementation_fingerprint: str,
    expected_review_count: int = 800,
    expected_double_review_count: int = 200,
    require_owner_only: bool = True,
) -> tuple[Path, Path]:
    _reject_locked_path(output_directory)
    if output_directory.exists():
        raise FileExistsError("review workspace output already exists")
    validated = validate_review_inputs(
        context_path,
        portable_v1_path,
        interface_implementation_commit=interface_implementation_commit,
        interface_implementation_fingerprint=interface_implementation_fingerprint,
        expected_review_count=expected_review_count,
        expected_double_review_count=expected_double_review_count,
        require_owner_only=require_owner_only,
    )
    temporary = output_directory.with_name(
        f".{output_directory.name}.initialize.{os.getpid()}"
    )
    if temporary.exists():
        raise FileExistsError("review workspace temporary output already exists")
    temporary.mkdir(parents=True, mode=0o700)
    temporary.chmod(0o700)
    try:
        reviewer_one = [
            ReviewAssignment(
                hashed_review_id=str(row["hashed_review_id"]),
                reviewer_id=REVIEWER_ONE_ID,
                review_round=1,
                assignment_role="PRIMARY",
                is_independent_review=bool(row["is_independent_review"]),
                display_order=index,
            )
            for index, row in enumerate(validated.portable_rows)
        ]
        reviewer_two = [
            ReviewAssignment(
                hashed_review_id=str(row["hashed_review_id"]),
                reviewer_id=REVIEWER_TWO_ID,
                review_round=1,
                assignment_role="INDEPENDENT_SECOND",
                is_independent_review=True,
                display_order=index,
            )
            for index, row in enumerate(validated.portable_rows)
            if bool(row["is_independent_review"])
        ]
        first_path = temporary / REVIEWER_ONE_ID / "review_progress.sqlite3"
        second_path = temporary / REVIEWER_TWO_ID / "review_progress.sqlite3"
        with ReviewProgressStore.create(
            first_path,
            binding=validated.binding,
            reviewer_id=REVIEWER_ONE_ID,
            reviewer_role="PRIMARY",
            assignments=reviewer_one,
        ):
            pass
        with ReviewProgressStore.create(
            second_path,
            binding=validated.binding,
            reviewer_id=REVIEWER_TWO_ID,
            reviewer_role="INDEPENDENT_SECOND",
            assignments=reviewer_two,
        ):
            pass
        os.replace(temporary, output_directory)
        output_directory.chmod(0o700)
        return (
            output_directory / REVIEWER_ONE_ID / "review_progress.sqlite3",
            output_directory / REVIEWER_TWO_ID / "review_progress.sqlite3",
        )
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


class ReviewContextRepository:
    def __init__(self, context_path: Path, store: ReviewProgressStore) -> None:
        _reject_locked_path(context_path)
        _require_owner_only(context_path)
        metadata = store.metadata()
        if _source_path_identity(context_path) != metadata["protected_context_path"]:
            raise ValueError("protected context path changed")
        if context_path.stat().st_size != int(metadata["protected_context_size_bytes"]):
            raise ValueError("protected context size changed")
        if file_sha256(context_path) != metadata["protected_context_sha256"]:
            raise ValueError("protected context hash changed")
        parquet = pq.ParquetFile(
            context_path, page_checksum_verification=True, pre_buffer=True
        )
        missing = set(PROTECTED_CONTEXT_REQUIRED_COLUMNS) - set(
            parquet.schema_arrow.names
        )
        if missing:
            raise ValueError("protected review context schema changed")
        self.table = parquet.read(use_threads=False)
        self.pilot_version = metadata["pilot_version"]
        self._by_hashed_id: dict[str, int] = {}
        for index, value in enumerate(
            self.table["stable_source_row_id_v1"].to_pylist()
        ):
            hashed_value = hashed_review_id(bytes(value), self.pilot_version)
            self._by_hashed_id[hashed_value] = index
        assigned = set(store.assignment_ids())
        if not assigned.issubset(self._by_hashed_id):
            raise ValueError("reviewer assignments are absent from protected context")

    def case(self, hashed_review_id_value: str) -> dict[str, Any]:
        try:
            index = self._by_hashed_id[hashed_review_id_value]
        except KeyError as error:
            raise KeyError("assigned review context is missing") from error
        row = {name: self.table[name][index].as_py() for name in RAW_REVIEW_FIELDS}
        row["hashed_review_id"] = hashed_review_id_value
        row["core"] = json.loads(str(self.table["phase03_core_json"][index].as_py()))
        row["evidence"] = json.loads(
            str(self.table["phase03_evidence_json"][index].as_py())
        )
        return row


def _preview(value: Any, *, limit: int = 1_000) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n[preview {limit}/{len(text)} characters; press v for paged viewer]"


def _wrap(label: str, value: Any, width: int) -> list[str]:
    prefix = f"{label}: "
    available = max(10, width - len(prefix))
    wrapped = textwrap.wrap(
        _preview(value),
        width=available,
        replace_whitespace=False,
        drop_whitespace=False,
    ) or [""]
    return [prefix + wrapped[0], *(" " * len(prefix) + item for item in wrapped[1:])]


def render_review_case(
    case: Mapping[str, Any], *, width: int = 100, evidence_expanded: bool = False
) -> list[str]:
    lines = [f"Review ID: {case['hashed_review_id']}", "", "ORIGINAL INPUT"]
    for field in RAW_REVIEW_FIELDS:
        lines.extend(_wrap(field, case.get(field), width))
    core = case.get("core")
    if not isinstance(core, dict):
        raise ValueError("protected core context is invalid")
    lines.extend(("", "PHASE 3 SELECTED COMPONENTS"))
    for field in SELECTED_COMPONENT_FIELDS:
        lines.extend(_wrap(field, core.get(field), width))
    lines.extend(("", "STATUS / CONFLICTS / DIAGNOSTICS"))
    for field in CORE_DIAGNOSTIC_FIELDS:
        lines.extend(_wrap(field, core.get(field), width))
    evidence = case.get("evidence")
    if not isinstance(evidence, list):
        raise ValueError("protected evidence context is invalid")
    lines.extend(("", f"EVIDENCE ({len(evidence)} rows)"))
    if not evidence_expanded:
        lines.append("[collapsed; press e to expand]")
    else:
        allowed = (
            "component",
            "candidate_value",
            "selected",
            "confidence",
            "rule_id",
            "source_field",
            "start_character",
            "end_character_exclusive",
            "conflict_flag",
            "diagnostic_flag",
        )
        for index, item in enumerate(evidence, start=1):
            if not isinstance(item, dict):
                raise ValueError("protected evidence row is invalid")
            lines.append(f"-- Evidence {index} --")
            for field in allowed:
                lines.extend(_wrap(field, item.get(field), width))
    saved = case.get("saved_review")
    if saved is not None:
        if not isinstance(saved, dict):
            raise ValueError("saved reviewer labels have invalid shape")
        lines.extend(("", "THIS REVIEWER'S SAVED LABELS"))
        for field in ALL_REVIEW_LABEL_FIELDS:
            lines.extend(_wrap(field, saved.get(field), width))
        lines.extend(_wrap("reason_codes", saved.get("reason_codes"), width))
        lines.extend(_wrap("protected_note", saved.get("protected_note"), width))
    return lines


def paged_field_segments(
    value: str, *, page_characters: int = 4_000
) -> list[tuple[int, str]]:
    if page_characters < 1:
        raise ValueError("page size must be positive")
    return [
        (offset, value[offset : offset + page_characters])
        for offset in range(0, max(1, len(value)), page_characters)
    ] or [(0, "")]


def _prompt_choice_line(
    prompt: str, choices: Sequence[str], input_fn: Callable[[str], str]
) -> str:
    while True:
        rendered = " ".join(
            f"{index + 1}={value}" for index, value in enumerate(choices)
        )
        answer = input_fn(f"{prompt} [{rendered}]: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        if answer in choices:
            return answer


def collect_labels_line(
    *, input_fn: Callable[[str], str] = input
) -> tuple[dict[str, str], tuple[str, ...], str | None]:
    labels: dict[str, str] = {}
    for field in COMPONENT_LABEL_FIELDS:
        labels[field] = _prompt_choice_line(field, COMPONENT_LABEL_VALUES, input_fn)
    labels["conflict_correctness_label"] = _prompt_choice_line(
        "conflict_correctness_label", CONFLICT_LABEL_VALUES, input_fn
    )
    for field in ERROR_CONDITION_LABEL_FIELDS:
        labels[field] = _prompt_choice_line(
            field, ERROR_CONDITION_LABEL_VALUES, input_fn
        )
    labels["overall_parse_acceptability_label"] = _prompt_choice_line(
        "overall_parse_acceptability_label", OVERALL_LABEL_VALUES, input_fn
    )
    reason_menu = " ".join(
        f"{index + 1}={value}"
        for index, value in enumerate(MANUAL_REVIEW_REASON_CODES_V1)
    )
    while True:
        raw = input_fn(f"reason codes, comma-separated [{reason_menu}]: ").strip()
        try:
            numbers = [int(value.strip()) for value in raw.split(",") if value.strip()]
        except ValueError:
            continue
        if numbers and all(
            1 <= value <= len(MANUAL_REVIEW_REASON_CODES_V1) for value in numbers
        ):
            reasons = tuple(
                MANUAL_REVIEW_REASON_CODES_V1[value - 1] for value in numbers
            )
            break
    note_value = input_fn("protected note (optional, max 500 characters): ")
    note = note_value if note_value else None
    canonical = canonicalize_manual_review_reason_codes(
        reasons, protected_adjudication_note=note
    )
    return labels, canonical, note


def _previous_assignment(
    store: ReviewProgressStore, current_order: int
) -> dict[str, Any] | None:
    row = store.connection.execute(
        "SELECT * FROM assignment WHERE display_order<? ORDER BY display_order DESC LIMIT 1",
        (current_order,),
    ).fetchone()
    return None if row is None else dict(row)


def _next_assignment(
    store: ReviewProgressStore, current_order: int
) -> dict[str, Any] | None:
    row = store.connection.execute(
        """
        SELECT * FROM assignment
        WHERE display_order>? AND status!='COMPLETE'
        ORDER BY display_order LIMIT 1
        """,
        (current_order,),
    ).fetchone()
    return None if row is None else dict(row)


def _resume_assignment(store: ReviewProgressStore) -> dict[str, Any] | None:
    current = store.assignment_at(store.cursor())
    if current is None or current["status"] == "COMPLETE":
        return store.next_incomplete()
    return current


def _case_with_saved_review(
    store: ReviewProgressStore,
    repository: ReviewContextRepository,
    hashed_review_id_value: str,
) -> dict[str, Any]:
    case = repository.case(hashed_review_id_value)
    case["saved_review"] = store.label_values(hashed_review_id_value)
    return case


def run_line_review(
    store: ReviewProgressStore,
    repository: ReviewContextRepository,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    current = _resume_assignment(store)
    evidence_expanded = False
    while current is not None:
        hashed_id_value = str(current["hashed_review_id"])
        store.mark_in_progress(hashed_id_value)
        case = _case_with_saved_review(store, repository, hashed_id_value)
        output_fn(
            "\n".join(render_review_case(case, evidence_expanded=evidence_expanded))
        )
        output_fn(json.dumps(store.summary(), sort_keys=True))
        command = (
            input_fn(
                "[s] label/save  [x] label/save+quit  [e] evidence  [v] long field  "
                "[h] label help  [p] previous  [i] incomplete  [q] quit: "
            )
            .strip()
            .lower()
        )
        if command == "q":
            return
        if command == "e":
            evidence_expanded = not evidence_expanded
            continue
        if command == "h":
            output_fn("\n".join(REVIEW_LABEL_HELP))
            continue
        if command == "v":
            field = input_fn(f"field name ({', '.join(RAW_REVIEW_FIELDS)}): ").strip()
            if field in RAW_REVIEW_FIELDS:
                value = "" if case.get(field) is None else str(case[field])
                for offset, segment in paged_field_segments(value):
                    output_fn(
                        f"[{field} characters {offset}:{offset + len(segment)}]\n{segment}"
                    )
                    if (
                        offset + len(segment) < len(value)
                        and input_fn("Enter=next page, q=stop: ").strip().lower() == "q"
                    ):
                        break
            continue
        if command == "p":
            previous = _previous_assignment(store, int(current["display_order"]))
            if previous is not None:
                current = previous
                store.move_cursor(int(current["display_order"]))
            continue
        if command == "i":
            incomplete = store.next_incomplete(after=int(current["display_order"]))
            if incomplete is not None:
                current = incomplete
                store.move_cursor(int(current["display_order"]))
            continue
        if command not in {"s", "x"}:
            continue
        try:
            labels, reasons, note = collect_labels_line(input_fn=input_fn)
            store.save_completed(
                hashed_id_value,
                labels,
                reasons,
                protected_note=note,
            )
        except ValueError as error:
            output_fn(f"VALIDATION_ERROR: {error}")
            continue
        if command == "x":
            return
        next_assignment = _next_assignment(store, int(current["display_order"]))
        current = next_assignment or store.next_incomplete()


def run_curses_review(
    store: ReviewProgressStore, repository: ReviewContextRepository
) -> None:
    try:
        import curses
    except ImportError as error:
        raise CursesInterfaceUnavailable("curses is not available") from error

    def application(screen: Any) -> None:
        curses.curs_set(0)
        current = _resume_assignment(store)
        evidence_expanded = False
        scroll = 0
        message = ""
        while current is not None:
            hashed_id_value = str(current["hashed_review_id"])
            store.mark_in_progress(hashed_id_value)
            height, width = screen.getmaxyx()
            lines = render_review_case(
                _case_with_saved_review(store, repository, hashed_id_value),
                width=max(20, width - 1),
                evidence_expanded=evidence_expanded,
            )
            screen.erase()
            for row, line in enumerate(lines[scroll : scroll + max(1, height - 3)]):
                try:
                    screen.addnstr(row, 0, line, max(1, width - 1))
                except curses.error:
                    pass
            footer = (
                "s=label/save x=label/save+quit e=evidence v=long-field j/k=scroll "
                "h=help p=previous i=incomplete q=quit"
            )
            screen.addnstr(max(0, height - 2), 0, footer, max(1, width - 1))
            screen.addnstr(max(0, height - 1), 0, message, max(1, width - 1))
            screen.refresh()
            key = screen.get_wch()
            message = ""
            if key == "q":
                return
            if key == "j":
                scroll = min(max(0, len(lines) - 1), scroll + 1)
            elif key == "k":
                scroll = max(0, scroll - 1)
            elif key == "e":
                evidence_expanded = not evidence_expanded
                scroll = 0
            elif key == "h":
                curses.endwin()
                print("\n".join(REVIEW_LABEL_HELP))
                input("Press Enter to return to the review interface: ")
                screen.clear()
                screen.refresh()
            elif key == "v":
                curses.endwin()
                case = repository.case(hashed_id_value)
                field = input(f"field name ({', '.join(RAW_REVIEW_FIELDS)}): ").strip()
                if field in RAW_REVIEW_FIELDS:
                    value = "" if case.get(field) is None else str(case[field])
                    for offset, segment in paged_field_segments(value):
                        print(
                            f"[{field} characters {offset}:{offset + len(segment)}]"
                            f"\n{segment}"
                        )
                        if (
                            offset + len(segment) < len(value)
                            and input("Enter=next page, q=stop: ").strip().lower()
                            == "q"
                        ):
                            break
                screen.clear()
                screen.refresh()
            elif key == "p":
                previous = _previous_assignment(store, int(current["display_order"]))
                if previous is not None:
                    current = previous
                    store.move_cursor(int(current["display_order"]))
                    scroll = 0
            elif key == "i":
                incomplete = store.next_incomplete(after=int(current["display_order"]))
                if incomplete is not None:
                    current = incomplete
                    store.move_cursor(int(current["display_order"]))
                    scroll = 0
            elif key in {"s", "x"}:
                curses.endwin()
                try:
                    labels, reasons, note = collect_labels_line()
                    store.save_completed(
                        hashed_id_value,
                        labels,
                        reasons,
                        protected_note=note,
                    )
                    if key == "x":
                        return
                    current = (
                        _next_assignment(store, int(current["display_order"]))
                        or store.next_incomplete()
                    )
                    scroll = 0
                except ValueError as error:
                    message = f"VALIDATION_ERROR: {error}"
                finally:
                    screen.refresh()

    try:
        curses.wrapper(application)
    except (curses.error, OSError) as error:
        raise CursesInterfaceUnavailable(
            "curses terminal initialization failed"
        ) from error


def run_review_interface(
    progress_database: Path,
    context_path: Path,
    *,
    line_mode: bool = False,
) -> None:
    _reject_locked_path(progress_database)
    _reject_locked_path(context_path)
    _require_owner_only(progress_database)
    _require_owner_only(context_path)
    with ReviewProgressStore(progress_database) as store:
        if (
            store.metadata()["interface_implementation_fingerprint"]
            != current_interface_fingerprint()
        ):
            raise ValueError("review-interface implementation fingerprint changed")
        if (
            store.metadata()["interface_implementation_commit"]
            != current_repository_commit()
        ):
            raise ValueError("review-interface implementation commit changed")
        repository = ReviewContextRepository(context_path, store)
        if line_mode:
            run_line_review(store, repository)
            return
        try:
            run_curses_review(store, repository)
        except CursesInterfaceUnavailable:
            run_line_review(store, repository)

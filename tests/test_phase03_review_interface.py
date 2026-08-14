from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase03.constants import (
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
)
from safe_geocoding_pipeline.phase03.review import (
    hashed_review_id,
    manual_review_schema,
)
from safe_geocoding_pipeline.phase03.review_cli import implementation_fingerprint
from safe_geocoding_pipeline.phase03.review_cli import main as review_cli_main
from safe_geocoding_pipeline.phase03.review_interface import (
    CursesInterfaceUnavailable,
    ReviewContextRepository,
    initialize_review_workspace,
    paged_field_segments,
    render_review_case,
    run_line_review,
    run_review_interface,
    validate_review_inputs,
)
from safe_geocoding_pipeline.phase03.review_progress import (
    REVIEWER_ONE_ID,
    REVIEWER_TWO_ID,
    ProgressBinding,
    ReviewAssignment,
    ReviewProgressStore,
    current_repository_commit,
    export_completed_reviews,
)
from safe_geocoding_pipeline.phase03.review_v2 import (
    ALL_REVIEW_LABEL_FIELDS,
    COMPONENT_LABEL_FIELDS,
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
    MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
    REVIEW_EXPORT_MANIFEST_VERSION,
    manual_review_schema_v2,
    validate_completed_review_record_v2,
    validate_reviewer_id,
)

_PILOT_VERSION = "phase03_pilot_synthetic_review_v1"
_PARSER_COMMIT = "f9699cbc88150defd764489fe10338d134e8ff61"
_INTERFACE_COMMIT = current_repository_commit()
_INTERFACE_FINGERPRINT = implementation_fingerprint()


def _identity(index: int) -> bytes:
    return index.to_bytes(32, "big")


def _write_synthetic_inputs(
    directory: Path, *, count: int = 8, double_count: int = 2
) -> tuple[Path, Path, tuple[str, ...]]:
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    stable_ids = [_identity(index + 1) for index in range(count)]
    review_ids = tuple(hashed_review_id(value, _PILOT_VERSION) for value in stable_ids)
    context_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    for index, (stable_id, review_id) in enumerate(zip(stable_ids, review_ids)):
        core = {
            "id": f"PROVIDER-SECRET-{index}",
            "street_clean": f"Example Street {index}",
            "house_number_clean": str(index + 1),
            "address_parse_status": "PARSED",
            "address_completeness_class": "COMPLETE",
            "diagnostic_evaluation_status": "EVALUATED",
            "address_conflict_flags": [],
            "address_diagnostic_flags": [],
        }
        evidence = [
            {
                "component": "street",
                "candidate_value": f"Example Street {index}",
                "selected": True,
                "confidence": "HIGH",
                "rule_id": "SYNTHETIC_RULE_V1",
                "source_field": "street_address_line_1",
                "start_character": 0,
                "end_character_exclusive": 14,
            }
        ]
        context_rows.append(
            {
                "id": f"PROVIDER-SECRET-{index}",
                "stable_source_row_id_v1": stable_id,
                "street_address_line_1": f"Fictional Straße {index}",
                "street_address_line_2": "ساختمان آزمایشی" if index == 0 else "",
                "street_address_line_3": "",
                "street_address_line_4": "",
                "street_address_line_1_native": "架空住所" if index == 0 else "",
                "street_address_line_2_native": "",
                "street_address_line_3_native": "",
                "street_address_line_4_native": "",
                "postcode": f"00{index:03d}",
                "city": "Fictional City",
                "region_in_country": "Test Region",
                "country_iso_code": "DE",
                "location_information": "no_geocoding_information",
                "phase03_core_json": json.dumps(core, sort_keys=True),
                "phase03_evidence_json": json.dumps(evidence, sort_keys=True),
            }
        )
        label_rows.append(
            {
                "hashed_review_id": review_id,
                "pilot_version": _PILOT_VERSION,
                "sample_partition": "DEVELOPMENT",
                "reviewer_id": "",
                "review_round": 1,
                "is_independent_review": index < double_count,
                "street_label": None,
                "house_number_label": None,
                "unit_floor_building_label": None,
                "organization_address_role_label": None,
                "postcode_locality_region_country_label": None,
                "conflict_correctness_label": None,
                "parser_overreach_label": None,
                "missed_information_label": None,
                "unsafe_handling_label": None,
                "overall_parse_acceptability_label": None,
                "reason_codes": [],
                "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                "adjudicated_label": None,
                "adjudicator_id": None,
                "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
            }
        )
    context_path = directory / "protected_review_context.parquet"
    labels_path = directory / "portable_review_labels.parquet"
    pq.write_table(
        pa.Table.from_pylist(context_rows),
        context_path,
        compression="zstd",
        write_statistics=False,
        write_page_checksum=True,
    )
    pq.write_table(
        pa.Table.from_pylist(label_rows, schema=manual_review_schema()),
        labels_path,
        compression="zstd",
        write_statistics=False,
        write_page_checksum=True,
    )
    context_path.chmod(0o600)
    labels_path.chmod(0o600)
    return context_path, labels_path, review_ids


def _valid_labels() -> dict[str, str]:
    values = {field: "CORRECT" for field in COMPONENT_LABEL_FIELDS}
    values.update(
        {
            "conflict_correctness_label": "NOT_APPLICABLE",
            "parser_overreach_label": "ABSENT",
            "missed_information_label": "ABSENT",
            "unsafe_handling_label": "ABSENT",
            "overall_parse_acceptability_label": "ACCEPTABLE",
        }
    )
    return values


def _portable_record(
    *,
    labels: dict[str, str] | None = None,
    reasons: list[str] | None = None,
    reviewer_id: str = "R01",
) -> dict[str, Any]:
    return {
        "hashed_review_id": "c" * 64,
        "pilot_version": _PILOT_VERSION,
        "sample_partition": "DEVELOPMENT",
        "reviewer_id": reviewer_id,
        "review_round": 1,
        "is_independent_review": False,
        "assignment_role": "PRIMARY",
        **(labels or _valid_labels()),
        "reason_codes": reasons or ["CORRECT_AS_IS"],
        "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
        "label_vocabulary_version": MANUAL_REVIEW_LABEL_VOCABULARY_VERSION,
        "adjudicated_label": None,
        "adjudicator_id": None,
        "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION_V2,
    }


def _initialize_small_workspace(
    tmp_path: Path, *, count: int = 8, double_count: int = 2
) -> tuple[Path, Path, Path, tuple[str, ...]]:
    context, v1_labels, review_ids = _write_synthetic_inputs(
        tmp_path / "inputs", count=count, double_count=double_count
    )
    first, second = initialize_review_workspace(
        context,
        v1_labels,
        tmp_path / "progress",
        interface_implementation_commit=_INTERFACE_COMMIT,
        interface_implementation_fingerprint=_INTERFACE_FINGERPRINT,
        expected_review_count=count,
        expected_double_review_count=double_count,
    )
    return context, first, second, review_ids


def _complete(store: ReviewProgressStore) -> None:
    for review_id in store.assignment_ids():
        store.save_completed(
            review_id,
            _valid_labels(),
            ["CORRECT_AS_IS"],
            protected_note=None,
            updated_at_utc="2026-08-14T10:00:00Z",
        )


def test_v2_schema_is_new_component_specific_and_v1_is_unchanged() -> None:
    v1 = manual_review_schema()
    v2 = manual_review_schema_v2()
    assert len(v1) == 21
    assert v1.names[8] == "unit_floor_building_label"
    assert v1.names[10] == "postcode_locality_region_country_label"
    assert len(v2) == 28
    assert v2.names[7:17] == list(COMPONENT_LABEL_FIELDS)
    assert "unit_floor_building_label" not in v2.names
    assert "postcode_locality_region_country_label" not in v2.names
    assert all(not v2.field(field).nullable for field in ALL_REVIEW_LABEL_FIELDS)


@pytest.mark.parametrize("reviewer_id", ["amir", "user@example.test", "R1", "R001"])
def test_reviewer_ids_are_closed_pseudonyms(reviewer_id: str) -> None:
    with pytest.raises(ValueError, match="pseudonymous"):
        validate_reviewer_id(reviewer_id)


def test_closed_labels_and_cross_field_rules() -> None:
    record = _portable_record()
    assert validate_completed_review_record_v2(record) == ("CORRECT_AS_IS",)

    invalid = dict(record)
    invalid["street_label"] = "YES"
    with pytest.raises(ValueError, match="closed label"):
        validate_completed_review_record_v2(invalid)

    wrong_role = dict(record)
    wrong_role["assignment_role"] = "INDEPENDENT_SECOND"
    with pytest.raises(ValueError, match="assignment role"):
        validate_completed_review_record_v2(wrong_role)

    missed = _valid_labels()
    missed["street_label"] = "MISSED"
    with pytest.raises(ValueError, match="missed information PRESENT"):
        validate_completed_review_record_v2(
            _portable_record(labels=missed, reasons=["MISSED_EXTRACTABLE_COMPONENT"])
        )
    missed["missed_information_label"] = "PRESENT"
    assert validate_completed_review_record_v2(
        _portable_record(labels=missed, reasons=["MISSED_EXTRACTABLE_COMPONENT"])
    ) == ("MISSED_EXTRACTABLE_COMPONENT",)


def test_reason_requirements_notes_and_acceptable_semantics() -> None:
    labels = _valid_labels()
    labels["street_label"] = "INCORRECT"
    with pytest.raises(ValueError, match="INCORRECT requires"):
        validate_completed_review_record_v2(
            _portable_record(labels=labels, reasons=["UNSUPPORTED_FORMAT"])
        )
    labels["overall_parse_acceptability_label"] = "ACCEPTABLE"
    assert validate_completed_review_record_v2(
        _portable_record(labels=labels, reasons=["WRONG_VALUE"])
    ) == ("WRONG_VALUE",)

    other = _portable_record(reasons=["OTHER_ADJUDICATION_REQUIRED"])
    with pytest.raises(ValueError, match="protected adjudication note"):
        validate_completed_review_record_v2(other)
    with pytest.raises(ValueError, match="exceeds 500"):
        validate_completed_review_record_v2(other, protected_note="x" * 501)
    assert validate_completed_review_record_v2(
        other, protected_note="Needs controlled adjudication."
    ) == ("OTHER_ADJUDICATION_REQUIRED",)
    with pytest.raises(ValueError, match="unknown manual-review reason"):
        validate_completed_review_record_v2(
            _portable_record(reasons=["ARBITRARY_REASON"])
        )
    with pytest.raises(ValueError, match="not canonical"):
        validate_completed_review_record_v2(
            _portable_record(reasons=["WRONG_VALUE", "WRONG_COMPONENT_ROLE"])
        )


def test_initialization_freezes_assignments_and_separates_reviewers(
    tmp_path: Path,
) -> None:
    context, first_path, second_path, review_ids = _initialize_small_workspace(tmp_path)
    assert context.exists()
    with (
        ReviewProgressStore(first_path, readonly=True) as first,
        ReviewProgressStore(second_path, readonly=True) as second,
    ):
        assert first.reviewer_id() == REVIEWER_ONE_ID
        assert second.reviewer_id() == REVIEWER_TWO_ID
        assert first.assignment_count() == 8
        assert second.assignment_count() == 2
        assert first.assignment_ids() == review_ids
        assert second.assignment_ids() == review_ids[:2]
        assert all(
            bool(first.assignment(review_id)["is_independent_review"])
            for review_id in review_ids[:2]
        )
        assert not any(
            bool(first.assignment(review_id)["is_independent_review"])
            for review_id in review_ids[2:]
        )
        assert all(
            bool(second.assignment(review_id)["is_independent_review"])
            and second.assignment(review_id)["assignment_role"] == "INDEPENDENT_SECOND"
            for review_id in review_ids[:2]
        )
        assert first.metadata()["reviewer_role"] == "PRIMARY"
        assert second.metadata()["reviewer_role"] == "INDEPENDENT_SECOND"
    assert first_path.stat().st_mode & 0o077 == 0
    assert second_path.stat().st_mode & 0o077 == 0


def test_production_sized_assignment_model_is_exactly_800_plus_200(
    tmp_path: Path,
) -> None:
    _, first_path, second_path, _ = _initialize_small_workspace(
        tmp_path, count=800, double_count=200
    )
    with (
        ReviewProgressStore(first_path, readonly=True) as first,
        ReviewProgressStore(second_path, readonly=True) as second,
    ):
        assert first.assignment_count() == 800
        assert second.assignment_count() == 200
        assert (
            sum(
                bool(first.assignment(review_id)["is_independent_review"])
                for review_id in first.assignment_ids()
            )
            == 200
        )
        assert all(
            bool(second.assignment(review_id)["is_independent_review"])
            for review_id in second.assignment_ids()
        )


def test_invalid_save_rolls_back_and_resume_is_durable(tmp_path: Path) -> None:
    _, first_path, _, review_ids = _initialize_small_workspace(tmp_path)
    with ReviewProgressStore(first_path) as store:
        start_cursor = store.cursor()
        invalid = _valid_labels()
        invalid["postcode_label"] = "MISSED"
        with pytest.raises(ValueError):
            store.save_completed(
                review_ids[0], invalid, ["CORRECT_AS_IS"], protected_note=None
            )
        assert store.cursor() == start_cursor
        assert store.assignment(review_ids[0])["status"] == "PENDING"
        store.save_completed(
            review_ids[0],
            _valid_labels(),
            ["CORRECT_AS_IS"],
            protected_note=None,
            updated_at_utc="2026-08-14T10:00:00Z",
        )
        assert store.summary()["complete_count"] == 1
    with ReviewProgressStore(first_path) as resumed:
        assert resumed.integrity_check() == "ok"
        assert resumed.summary()["complete_count"] == 1
        assert resumed.cursor() == 1


def test_fully_completed_store_resumes_as_complete_without_reopening_last_case(
    tmp_path: Path,
) -> None:
    context, first_path, _, _ = _initialize_small_workspace(tmp_path)
    with ReviewProgressStore(first_path) as store:
        _complete(store)
        repository = ReviewContextRepository(context, store)

        def unexpected_prompt(_: str) -> str:
            raise AssertionError("completed review must not prompt again")

        run_line_review(store, repository, input_fn=unexpected_prompt)
        assert store.summary()["remaining_count"] == 0


def test_input_validation_fails_closed_on_hash_change_and_locked_path(
    tmp_path: Path,
) -> None:
    context, labels, _ = _write_synthetic_inputs(tmp_path / "inputs")
    validated = validate_review_inputs(
        context,
        labels,
        interface_implementation_commit=_INTERFACE_COMMIT,
        interface_implementation_fingerprint=_INTERFACE_FINGERPRINT,
        expected_review_count=8,
        expected_double_review_count=2,
    )
    assert validated.binding.reviewed_parser_commit == _PARSER_COMMIT
    assert validated.binding.protected_context_path == str(context.resolve())
    assert validated.binding.portable_v1_path == str(labels.resolve())
    labels.write_bytes(labels.read_bytes() + b"changed")
    with pytest.raises(Exception):
        validate_review_inputs(
            context,
            labels,
            interface_implementation_commit=_INTERFACE_COMMIT,
            interface_implementation_fingerprint=_INTERFACE_FINGERPRINT,
            expected_review_count=8,
            expected_double_review_count=2,
        )
    with pytest.raises(ValueError, match="LOCKED"):
        validate_review_inputs(
            tmp_path / "locked" / "protected.parquet",
            labels,
            interface_implementation_commit=_INTERFACE_COMMIT,
            interface_implementation_fingerprint=_INTERFACE_FINGERPRINT,
        )


def test_render_is_unicode_capable_and_whitelists_display_fields() -> None:
    case = {
        "hashed_review_id": "d" * 64,
        "provider_id": "DO-NOT-DISPLAY",
        "stable_source_row_id_v1": b"secret",
        **{
            field: ""
            for field in (
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
        },
        "core": {
            "id": "DO-NOT-DISPLAY",
            "street_clean": "架空 Straße",
            "address_parse_status": "PARSED",
        },
        "evidence": [{"component": "street", "candidate_value": "架空 Straße"}],
    }
    lines = render_review_case(case, evidence_expanded=True)
    rendered = "\n".join(lines)
    assert "架空 Straße" in rendered
    assert "DO-NOT-DISPLAY" not in rendered
    assert "stable_source_row_id_v1" not in rendered
    assert paged_field_segments("x" * 9, page_characters=4) == [
        (0, "xxxx"),
        (4, "xxxx"),
        (8, "x"),
    ]


def test_curses_failure_uses_line_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, first_path, _, _ = _initialize_small_workspace(tmp_path)
    called: list[str] = []

    def unavailable(*_: object) -> None:
        raise CursesInterfaceUnavailable("synthetic unavailable terminal")

    def fallback(*_: object) -> None:
        called.append("line")

    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.review_interface.run_curses_review",
        unavailable,
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.review_interface.run_line_review",
        fallback,
    )
    run_review_interface(first_path, context)
    assert called == ["line"]


def test_resume_fails_closed_if_interface_identity_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, first_path, _, _ = _initialize_small_workspace(tmp_path)
    called: list[str] = []
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.review_interface.current_interface_fingerprint",
        lambda: "0" * 64,
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.review_interface.run_line_review",
        lambda *_: called.append("line"),
    )
    with pytest.raises(ValueError, match="fingerprint changed"):
        run_review_interface(first_path, context, line_mode=True)
    assert not called


def test_completed_export_is_exact_private_atomic_and_sanitized(tmp_path: Path) -> None:
    _, first_path, second_path, _ = _initialize_small_workspace(tmp_path)
    with ReviewProgressStore(first_path) as first:
        first_id, *remaining = first.assignment_ids()
        first.save_completed(
            first_id,
            _valid_labels(),
            ["CORRECT_AS_IS"],
            protected_note="PROTECTED-NOTE-SECRET",
            updated_at_utc="2026-08-14T10:00:00Z",
        )
        for review_id in remaining:
            first.save_completed(
                review_id,
                _valid_labels(),
                ["CORRECT_AS_IS"],
                protected_note=None,
                updated_at_utc="2026-08-14T10:00:00Z",
            )
    with ReviewProgressStore(second_path) as second:
        _complete(second)
    parquet_path, manifest_path = export_completed_reviews(
        first_path,
        second_path,
        tmp_path / "export",
        export_timestamp_utc="2026-08-14T12:00:00Z",
        expected_reviewer_one_records=8,
        expected_reviewer_two_records=2,
    )
    parquet = pq.ParquetFile(
        parquet_path, page_checksum_verification=True, pre_buffer=True
    )
    assert parquet.metadata.num_rows == 10
    assert parquet.schema_arrow.remove_metadata() == manual_review_schema_v2()
    rows = parquet.read(use_threads=False).to_pylist()
    assert {row["reviewer_id"] for row in rows} == {"R01", "R02"}
    assert sum(row["reviewer_id"] == "R01" for row in rows) == 8
    assert sum(row["reviewer_id"] == "R02" for row in rows) == 2
    assert all(
        row["assignment_role"]
        == ("PRIMARY" if row["reviewer_id"] == "R01" else "INDEPENDENT_SECOND")
        for row in rows
    )
    assert all(
        row["is_independent_review"] for row in rows if row["reviewer_id"] == "R02"
    )
    assert not any(
        name in manual_review_schema_v2().names
        for name in ("protected_note", "id", "stable_source_row_id_v1", "raw_address")
    )
    for row_group in range(parquet.metadata.num_row_groups):
        for column in range(parquet.metadata.row_group(row_group).num_columns):
            assert (
                parquet.metadata.row_group(row_group).column(column).statistics is None
            )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == REVIEW_EXPORT_MANIFEST_VERSION
    assert (
        manifest["input_artifacts"]["protected_review_context"]["artifact_id"]
        == "phase03_protected_review_context"
    )
    assert (
        manifest["input_artifacts"]["portable_review_labels_v1"]["artifact_id"]
        == "phase03_portable_review_labels_v1"
    )
    assert manifest["reviewed_parser_commit"] == _PARSER_COMMIT
    assert manifest["review_interface_implementation_commit"] == _INTERFACE_COMMIT
    assert (
        manifest["review_interface_implementation_fingerprint"]
        == _INTERFACE_FINGERPRINT
    )
    assert manifest["reviewer_1_record_count"] == 8
    assert manifest["reviewer_2_record_count"] == 2
    assert manifest["total_reviewer_record_count"] == 10
    assert manifest["protected_or_raw_values_in_manifest"] is False
    manifest_text = manifest_path.read_text(encoding="utf-8")
    for prohibited in (
        "Fictional Straße",
        "PROVIDER-SECRET",
        "protected_note",
        "stable_source_row_id_v1",
        "candidate_value",
        "PROTECTED-NOTE-SECRET",
        str(tmp_path),
        "/work/footprint/",
        "/home/footprint/",
        "/Users/",
    ):
        assert prohibited not in manifest_text
    assert "PROTECTED-NOTE-SECRET" not in parquet_path.read_bytes().decode("latin-1")
    assert parquet_path.stat().st_mode & 0o077 == 0
    assert manifest_path.stat().st_mode & 0o077 == 0


def test_export_rejects_incomplete_or_mismatched_reviewer_state(tmp_path: Path) -> None:
    _, first_path, second_path, _ = _initialize_small_workspace(tmp_path)
    with pytest.raises(ValueError, match="incomplete"):
        export_completed_reviews(
            first_path,
            second_path,
            tmp_path / "incomplete-export",
            expected_reviewer_one_records=8,
            expected_reviewer_two_records=2,
        )


def test_schema_fingerprint_is_deterministic_and_real() -> None:
    first = implementation_fingerprint()
    second = implementation_fingerprint()
    assert first == second
    assert len(first) == 64
    int(first, 16)


def test_cli_schema_output_is_sanitized(capsys: pytest.CaptureFixture[str]) -> None:
    assert review_cli_main(["schema"]) == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert (
        payload["interface_implementation_fingerprint"] == implementation_fingerprint()
    )
    assert [
        field["name"] for field in payload["fields"]
    ] == manual_review_schema_v2().names
    assert "street_address_line_1" not in output


def test_progress_binding_and_assignment_reject_personal_or_repeat_review() -> None:
    binding = ProgressBinding(
        pilot_version=_PILOT_VERSION,
        protected_context_path="/controlled/protected_review_context.parquet",
        protected_context_sha256="1" * 64,
        protected_context_size_bytes=1,
        portable_v1_path="/controlled/portable_review_labels.parquet",
        portable_v1_sha256="2" * 64,
        portable_v1_size_bytes=1,
        reviewed_parser_commit=_PARSER_COMMIT,
        interface_implementation_commit=_INTERFACE_COMMIT,
        interface_implementation_fingerprint=_INTERFACE_FINGERPRINT,
    )
    binding.validate()
    with pytest.raises(ValueError, match="pseudonymous"):
        ReviewAssignment(
            "3" * 64, "alice@example.test", 1, "PRIMARY", False, 0
        ).validate()
    with pytest.raises(ValueError, match="review round 1"):
        ReviewAssignment("3" * 64, "R01", 2, "PRIMARY", True, 0).validate()


def test_review_interface_modules_have_no_network_client_imports() -> None:
    root = Path(__file__).parents[1] / "src/safe_geocoding_pipeline/phase03"
    prohibited = {"aiohttp", "http", "httpx", "requests", "socket", "urllib"}
    for name in (
        "review_v2.py",
        "review_progress.py",
        "review_interface.py",
        "review_cli.py",
    ):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert imports.isdisjoint(prohibited)

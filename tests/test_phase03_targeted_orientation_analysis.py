from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from phase03_helpers import phase02_row
from safe_geocoding_pipeline.phase03.constants import (
    MANUAL_REVIEW_REASON_CODES_VERSION,
)
from safe_geocoding_pipeline.phase03.targeted_experiment_review import (
    TARGETED_LABEL_FIELDS,
    TARGETED_LABEL_VOCABULARY_VERSION,
    TARGETED_REVIEW_SCHEMA_VERSION,
    targeted_review_context_schema,
    targeted_review_label_schema,
)
from safe_geocoding_pipeline.phase03.targeted_orientation_analysis import (
    ORIENTATION_REPORT_VERSION,
    analyze_targeted_v3_1_orientations,
)
from safe_geocoding_pipeline.phase03.targeted_review_population import file_sha256

_ITERATION = (
    "phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253"
)
_HOUSE = "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"
_STREET = "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-orientation:{index}".encode()).digest()


def _review_id(identity: bytes) -> str:
    encoded = _ITERATION.encode()
    return hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
        + len(encoded).to_bytes(8, "big")
        + encoded
        + identity
    ).hexdigest()


def _base_row(index: int, raw: str) -> dict[str, Any]:
    row = phase02_row(
        id=f"fictional-{index}",
        street_address_line_1=raw,
        postcode="12345",
        city="Fiction City",
        region_in_country="Fiction Region",
        country_iso_code="XZ",
        source_file="fictional.parquet",
        source_logical_record_number=index + 1,
        stable_source_row_id_v1=_identity(index),
        source_file_sha256=bytes.fromhex("22" * 32),
    )
    row.update(
        {
            "batch_priority": "fictional",
            "location_information": "no_geocoding_information",
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_phase02_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
    )
    return row


def _evidence(
    identity: bytes,
    *,
    house_span: tuple[int, int],
    street_span: tuple[int, int],
    selected: bool,
) -> list[dict[str, Any]]:
    common = {
        "stable_source_row_id_v1": identity.hex(),
        "source_file": "fictional.parquet",
        "source_logical_record_number": 1,
        "representation": "NON_NATIVE",
        "source_field": "street_address_line_1",
        "confidence": "MEDIUM",
        "selected": selected,
    }
    return [
        {
            **common,
            "rule_id": _HOUSE,
            "component": "HOUSE_NUMBER",
            "candidate_value": "12",
            "start_character": house_span[0],
            "end_character_exclusive": house_span[1],
        },
        {
            **common,
            "rule_id": _STREET,
            "component": "STREET",
            "candidate_value": "Fiction Street",
            "start_character": street_span[0],
            "end_character_exclusive": street_span[1],
        },
    ]


def _label(
    index: int,
    *,
    street: str,
    house: str,
    joint: str,
) -> dict[str, Any]:
    values = {
        "street_label": street,
        "house_number_label": house,
        "joint_street_house_label": joint,
        "residual_role_label": "UNKNOWN_RESIDUAL",
        "candidate_support_label": (
            "SUPPORTED" if joint == "CORRECT" else "NOT_SUPPORTED"
        ),
        "blind_parse_comparison_label": (
            "PARSE_A_CORRECT_ONLY" if joint == "CORRECT" else "BOTH_INCORRECT"
        ),
        "parser_overreach_label": "ABSENT" if joint == "CORRECT" else "PRESENT",
        "missed_information_label": "ABSENT",
        "overall_parse_acceptability_label": (
            "ACCEPTABLE" if joint == "CORRECT" else "NOT_ACCEPTABLE"
        ),
    }
    assert set(values) == set(TARGETED_LABEL_FIELDS)
    return {
        "hashed_review_id": _review_id(_identity(index)),
        "experiment_iteration": _ITERATION,
        "reviewer_id": "Targeted-R01",
        "review_round": 1,
        "is_independent_review": True,
        "assignment_role": "PRIMARY",
        **values,
        "reason_codes": [
            "CORRECT_AS_IS" if joint == "CORRECT" else "FALSE_POSITIVE_EXTRACTION"
        ],
        "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
        "label_vocabulary_version": TARGETED_LABEL_VOCABULARY_VERSION,
        "label_schema_version": TARGETED_REVIEW_SCHEMA_VERSION,
    }


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path, tuple[str, ...]]:
    tmp_path.chmod(0o700)
    context_rows: list[dict[str, Any]] = []
    labels: list[dict[str, Any]] = []
    raw_values: list[str] = []
    label_outcomes = [
        ("CORRECT", "CORRECT", "CORRECT"),
        ("CORRECT", "CORRECT", "INCORRECT"),
        ("CORRECT", "INCORRECT", "INCORRECT"),
        ("INCORRECT", "INCORRECT", "INCORRECT"),
        ("INCORRECT", "INCORRECT", "INCORRECT"),
    ]
    for index in range(11):
        if index < 4:
            raw = f"Fiction Street 12 Annex{chr(65 + index)}"
            evidence = _evidence(
                _identity(index),
                house_span=(15, 17),
                street_span=(0, 14),
                selected=True,
            )
            label_values = ("CORRECT", "CORRECT", "CORRECT")
            changed = True
        elif index < 9:
            suffix = chr(65 + index)
            raw = f"Annex{suffix} 12 Fiction Street"
            residual_end = len(f"Annex{suffix}")
            evidence = _evidence(
                _identity(index),
                house_span=(residual_end + 1, residual_end + 3),
                street_span=(residual_end + 4, len(raw)),
                selected=True,
            )
            label_values = label_outcomes[index - 4]
            changed = True
        else:
            raw = f"Wing{index} 12 Fiction Street"
            residual_end = len(f"Wing{index}")
            evidence = _evidence(
                _identity(index),
                house_span=(residual_end + 1, residual_end + 3),
                street_span=(residual_end + 4, len(raw)),
                selected=False,
            )
            label_values = ("MISSED", "MISSED", "NOT_APPLICABLE")
            changed = False
        raw_values.append(raw)
        row = _base_row(index, raw)
        row.update(
            {
                "baseline_core_json": "{}",
                "experimental_core_json": "{}",
                "baseline_evidence_json": "[]",
                "experimental_evidence_json": json.dumps(
                    evidence, sort_keys=True, separators=(",", ":")
                ),
                "targeted_case_metadata_json": json.dumps(
                    {
                        "scientific_output_changed": changed,
                        "experimental_evidence_present": True,
                        "experimental_candidate_group_count": 1,
                        "experimental_selected": changed,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
        context_rows.append(row)
        labels.append(
            _label(
                index,
                street=label_values[0],
                house=label_values[1],
                joint=label_values[2],
            )
        )
    context_path = tmp_path / "protected-context.parquet"
    labels_path = tmp_path / "controlled-labels.parquet"
    pq.write_table(
        pa.Table.from_pylist(context_rows, schema=targeted_review_context_schema()),
        context_path,
        write_statistics=False,
        write_page_checksum=True,
    )
    metadata = {
        b"review_design": b"SINGLE_REVIEWER",
        b"primary_reviewer": b"Targeted-R01",
        b"primary_review_complete": b"true",
        b"primary_review_rows": b"11",
        b"independent_second_review": b"SKIPPED_BY_EXPLICIT_DECISION",
        b"locked_rows_read": b"0",
    }
    pq.write_table(
        pa.Table.from_pylist(
            labels, schema=targeted_review_label_schema()
        ).replace_schema_metadata(metadata),
        labels_path,
        write_statistics=False,
        write_page_checksum=True,
    )
    context_path.chmod(0o600)
    labels_path.chmod(0o600)
    manifest_path = tmp_path / "input-manifest.json"
    manifest = {
        "status": "TARGETED_REVIEW_INPUT_PREPARED_NO_LABELS",
        "experiment_iteration": _ITERATION,
        "development_rows": 8_000,
        "targeted_review_population_rows": 11,
        "scientific_output_change_rows": 9,
        "experimental_rule_evidence_rows": 11,
        "locked_rows_read": 0,
        "output_artifacts": {
            "protected_context": {"sha256": file_sha256(context_path)}
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    manifest_path.chmod(0o600)
    return manifest_path, context_path, labels_path, tuple(raw_values)


def test_orientation_analysis_confirms_split_and_is_privacy_safe(
    tmp_path: Path,
) -> None:
    manifest, context, labels, raw_values = _write_inputs(tmp_path)
    output = tmp_path / "output" / "orientation.json"
    output.parent.mkdir(mode=0o700)
    payload = analyze_targeted_v3_1_orientations(
        input_manifest_path=manifest,
        protected_context_path=context,
        controlled_labels_path=labels,
        output_path=output,
        implementation_commit="a" * 40,
        production=False,
    )
    assert payload["report_version"] == ORIENTATION_REPORT_VERSION
    assert payload["status"] == "PARSER_V3_1_ORIENTATION_HYPOTHESIS_CONFIRMED"
    aggregates = cast(dict[str, dict[str, int]], payload["orientation_aggregates"])
    assert aggregates["STREET_NUMBER_RESIDUAL"]["selected_rows"] == 4
    assert aggregates["STREET_NUMBER_RESIDUAL"]["joint_street_house_correct_count"] == 4
    assert aggregates["RESIDUAL_NUMBER_STREET"]["selected_rows"] == 5
    assert aggregates["RESIDUAL_NUMBER_STREET"]["joint_street_house_correct_count"] == 1
    assert aggregates["RESIDUAL_NUMBER_STREET"]["incorrect_or_overreach_count"] == 4
    assert aggregates["OTHER_OR_UNCLASSIFIABLE"]["selected_rows"] == 0
    assert payload["locked_rows_read"] == 0
    serialized = output.read_text(encoding="utf-8")
    assert not any(value in serialized for value in raw_values)
    assert not any(_review_id(_identity(index)) in serialized for index in range(11))
    assert str(tmp_path) not in serialized
    assert "candidate_value" not in serialized
    assert "start_character" not in serialized


def test_orientation_analysis_reports_a_falsified_hypothesis(
    tmp_path: Path,
) -> None:
    manifest, context, labels, _ = _write_inputs(tmp_path)
    table = pq.read_table(labels)
    rows = table.to_pylist()
    rows[0]["joint_street_house_label"] = "INCORRECT"
    rows[0]["candidate_support_label"] = "NOT_SUPPORTED"
    rows[0]["parser_overreach_label"] = "PRESENT"
    rows[0]["overall_parse_acceptability_label"] = "NOT_ACCEPTABLE"
    rows[0]["reason_codes"] = ["FALSE_POSITIVE_EXTRACTION"]
    pq.write_table(
        pa.Table.from_pylist(
            rows, schema=targeted_review_label_schema()
        ).replace_schema_metadata(table.schema.metadata),
        labels,
        write_statistics=False,
        write_page_checksum=True,
    )
    labels.chmod(0o600)
    output = tmp_path / "falsified" / "orientation.json"
    payload = analyze_targeted_v3_1_orientations(
        input_manifest_path=manifest,
        protected_context_path=context,
        controlled_labels_path=labels,
        output_path=output,
        implementation_commit="a" * 40,
        production=False,
    )
    assert payload["status"] == "PARSER_V3_1_ORIENTATION_HYPOTHESIS_NOT_CONFIRMED"
    hypothesis = cast(dict[str, Any], payload["hypothesis"])
    assert hypothesis["confirmed"] is False

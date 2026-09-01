from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stage07_v2_validation_selection_cli import (
    main,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_component_readiness import (
    COMPONENTS_ABSTAIN,
    COMPONENTS_READY,
    REASON_ORDER,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    LibpostalComponent,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_output_schema import (
    STAGE07_COMPONENTS_FIELD,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parsing import stage07_schema
from safe_geocoding_pipeline.preprocessing.stages.s07_v2_validation_selection import (
    COUNTRY_FREQUENCY_BANDS,
    FROZEN_READINESS_RULE_SOURCE_SHA256,
    SELECTION_CONTRACT_VERSION,
    Stage07V2ValidationSelectionError,
    ValidationFrameRow,
    ValidationSelectionConfig,
    _country_frequency_band,
    _frame_schema,
    _review_schema,
    _select_authorized_stage07_values,
    _selection_fingerprint_v1,
    _selection_schema,
    _validate_frozen_rule_source,
    freeze_validation_selection,
)


def _candidate_id(index: int) -> bytes:
    return index.to_bytes(32, "big")


def _row(index: int, readiness: str) -> ValidationFrameRow:
    reasons = (
        (REASON_ORDER[4 + (index % (len(REASON_ORDER) - 4))],)
        if readiness == COMPONENTS_ABSTAIN
        else ()
    )
    representations = ("STANDARD_ONLY", "NATIVE_ONLY", "BOTH")
    scripts = ("LATIN", "HAN", "THAI", "MIXED_SCRIPT")
    return ValidationFrameRow(
        candidate_id=_candidate_id(index),
        parser_applicability="PARSER_ELIGIBLE_COUNTRY",
        technical_status="PARSED_NONEMPTY",
        component_readiness=readiness,
        reason_codes=reasons,
        representation=representations[index % len(representations)],
        country_code=f"C{index % 50:02d}",
        country_frequency_band=COUNTRY_FREQUENCY_BANDS[index % 4],
        script_bucket=scripts[index % len(scripts)],
        input_codepoints=20 + index,
        component_count=2,
        internal_boundary_count=int(readiness == COMPONENTS_ABSTAIN),
        internal_single_codepoint_fragment_count=0,
        maximum_components_per_lexical_run=2,
        adjacent_repeated_label_internal_boundary_count=0,
        candidate=f"synthetic candidate {index}",
        components=(LibpostalComponent("road", f"synthetic {index}"),),
    )


def test_freeze_selects_exact_balanced_240_deterministically() -> None:
    rows = [
        *(_row(index, COMPONENTS_READY) for index in range(1, 151)),
        *(_row(index, COMPONENTS_ABSTAIN) for index in range(151, 301)),
    ]

    first = freeze_validation_selection(rows)
    second = freeze_validation_selection(list(reversed(rows)))

    assert len(first) == 240
    assert len({row.candidate_id for row in first}) == 240
    assert sum(row.component_readiness == COMPONENTS_READY for row in first) == 120
    assert sum(row.component_readiness == COMPONENTS_ABSTAIN for row in first) == 120
    assert [row.candidate_id for row in first] == [row.candidate_id for row in second]
    selected_reasons = {reason for row in first for reason in row.reason_codes}
    assert selected_reasons == set(REASON_ORDER[4:])
    assert {row.representation for row in first} == {
        "STANDARD_ONLY",
        "NATIVE_ONLY",
        "BOTH",
    }
    assert {row.script_bucket for row in first} == {
        "LATIN",
        "HAN",
        "THAI",
        "MIXED_SCRIPT",
    }


def test_selection_rank_does_not_use_candidate_or_component_values() -> None:
    rows = [
        *(_row(index, COMPONENTS_READY) for index in range(1, 151)),
        *(_row(index, COMPONENTS_ABSTAIN) for index in range(151, 301)),
    ]
    changed = [
        replace(
            row,
            candidate=f"different protected value {index}",
            components=(LibpostalComponent("different", str(index)),),
        )
        for index, row in enumerate(rows)
    ]

    assert [row.candidate_id for row in freeze_validation_selection(rows)] == [
        row.candidate_id for row in freeze_validation_selection(changed)
    ]


def test_selection_fingerprint_binds_predictions_and_reason_codes() -> None:
    selected = [
        *(_row(index, COMPONENTS_READY) for index in range(1, 121)),
        *(_row(index, COMPONENTS_ABSTAIN) for index in range(121, 241)),
    ]
    selected.sort(key=lambda row: row.candidate_id)
    first = _selection_fingerprint_v1(
        selected=selected,
        untouched_fingerprint="1" * 64,
        stage07_manifest_sha256="2" * 64,
    )
    changed = list(selected)
    changed[0] = replace(
        changed[0],
        component_readiness=COMPONENTS_ABSTAIN,
        reason_codes=(REASON_ORDER[4],),
    )

    assert first != _selection_fingerprint_v1(
        selected=changed,
        untouched_fingerprint="1" * 64,
        stage07_manifest_sha256="2" * 64,
    )


def test_country_frequency_bands_are_exact() -> None:
    assert _country_frequency_band(1) == "COUNTRY_SINGLETON"
    assert _country_frequency_band(2) == "COUNTRY_LOW_2_TO_4"
    assert _country_frequency_band(4) == "COUNTRY_LOW_2_TO_4"
    assert _country_frequency_band(5) == "COUNTRY_MEDIUM_5_TO_14"
    assert _country_frequency_band(14) == "COUNTRY_MEDIUM_5_TO_14"
    assert _country_frequency_band(15) == "COUNTRY_HIGH_15_OR_MORE"
    with pytest.raises(Stage07V2ValidationSelectionError, match="frequency"):
        _country_frequency_band(0)


def test_selective_stage07_reader_returns_only_authorized_ids(tmp_path: Path) -> None:
    rows = []
    for index in range(1, 8):
        rows.append(
            {
                "stage06_exact_candidate_id": _candidate_id(index),
                "stage06_candidate_lower": f"synthetic {index}",
                "stage06_occurrence_count": 1,
                "stage06_standard_occurrence_count": 1,
                "stage06_native_occurrence_count": 0,
                "stage07_parse_status": "PARSED_NONEMPTY",
                STAGE07_COMPONENTS_FIELD: [
                    {"label": "road", "value": f"synthetic {index}"}
                ],
            }
        )
    table = pa.Table.from_pylist(rows, schema=stage07_schema())
    first = tmp_path / "part-000001.parquet"
    second = tmp_path / "part-000002.parquet"
    pq.write_table(table.slice(0, 3), first)
    pq.write_table(table.slice(3), second)
    targets = {_candidate_id(2), _candidate_id(6)}

    selected = _select_authorized_stage07_values((first, second), targets)

    assert set(selected) == targets
    assert selected[_candidate_id(2)][0] == "synthetic 2"
    assert selected[_candidate_id(6)][4] == (LibpostalComponent("road", "synthetic 6"),)


def test_protected_output_schemas_keep_large_offsets_and_raw_order() -> None:
    assert pa.types.is_large_list(_frame_schema().field("readiness_reason_codes").type)
    assert pa.types.is_large_list(
        _selection_schema().field("readiness_reason_codes").type
    )
    components = _review_schema().field(STAGE07_COMPONENTS_FIELD).type
    assert pa.types.is_large_list(components)
    assert [field.name for field in components.value_type] == ["label", "value"]
    assert all(pa.types.is_large_string(field.type) for field in components.value_type)


def test_frozen_rule_source_identity_is_unchanged() -> None:
    assert SELECTION_CONTRACT_VERSION == (
        "stage07_component_readiness_validation_selection_v1"
    )
    assert FROZEN_READINESS_RULE_SOURCE_SHA256 == (
        "dbdaf434c68bb2110cfc76eb296f4c955f7ad950c549255c0d4e1c8aae17deb9"
    )
    _validate_frozen_rule_source()


def test_config_rejects_holdout(tmp_path: Path) -> None:
    with pytest.raises(Stage07V2ValidationSelectionError, match="HOLDOUT"):
        ValidationSelectionConfig(
            stage06_fixed500_path=tmp_path / "fixed.parquet",
            existing_selection_path=tmp_path / "selection.parquet",
            eligibility_path=tmp_path / "eligibility.parquet",
            stage07_output_directory=tmp_path / "stage07",
            expected_stage07_manifest_sha256="1" * 64,
            output_directory=tmp_path / "HOLDOUT" / "output",
            execution_git_sha="2" * 40,
            authoritative_development=False,
        ).validate()


def test_cli_requires_all_inputs() -> None:
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2

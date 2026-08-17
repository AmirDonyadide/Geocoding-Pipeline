from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V2,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3,
    PARSER_VERSION_V3_1,
    PARSER_VERSION_V3_2,
)
from safe_geocoding_pipeline.phase03.development_comparison import (
    compare_development_parser_v2_1_v3_1_outputs,
    compare_development_parser_v2_1_v3_2_outputs,
    compare_development_parser_v2_v3_outputs,
)
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema

from phase03_helpers import engine, phase02_row


def _write(path: Path, rows: list[dict[str, object]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        compression="zstd",
        compression_level=3,
        version="2.4",
        data_page_version="1.0",
        write_page_checksum=True,
        write_statistics=False,
    )


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    v2_root = tmp_path / "v2-reference"
    v3_root = tmp_path / "v3-experiment"
    v2_root.mkdir()
    v3_root.mkdir()
    v2 = engine(v2_root, parser_version=PARSER_VERSION_V2)
    v3 = engine(v3_root, parser_version=PARSER_VERSION_V3)
    source_rows = [
        phase02_row(
            street_address_line_1="Annex 12 Example Street",
            postcode="12345",
            city="Fiction City",
            country_iso_code="XZ",
        ),
        phase02_row(
            id="fictional-provider-0002",
            stable_source_row_id_v1=bytes.fromhex("44" * 32),
            source_logical_record_number=2,
            street_address_line_1="34 Sample Road",
            postcode="54321",
            city="Sample City",
            country_iso_code="XZ",
        ),
    ]
    v2_results = [v2.transform(row) for row in source_rows]
    v3_results = [v3.transform(row) for row in source_rows]
    v2_core = tmp_path / "v2-core.parquet"
    v2_evidence = tmp_path / "v2-evidence.parquet"
    v3_core = tmp_path / "v3-core.parquet"
    v3_evidence = tmp_path / "v3-evidence.parquet"
    _write(v2_core, [item.core_row for item in v2_results], core_schema())
    _write(
        v2_evidence,
        [row for item in v2_results for row in item.evidence_rows],
        evidence_schema(),
    )
    _write(v3_core, [item.core_row for item in v3_results], core_schema())
    _write(
        v3_evidence,
        [row for item in v3_results for row in item.evidence_rows],
        evidence_schema(),
    )
    return v2_core, v2_evidence, v3_core, v3_evidence


def test_v2_v3_comparison_is_complete_sanitized_and_non_decisional(
    tmp_path: Path,
) -> None:
    v2_core, v2_evidence, v3_core, v3_evidence = _inputs(tmp_path)
    output = tmp_path / "comparison.json"
    payload = compare_development_parser_v2_v3_outputs(
        v2_core,
        v2_evidence,
        v3_core,
        v3_evidence,
        output,
        expected_rows=2,
    )
    assert payload["status"] == "EXPERIMENTAL_COMPARISON_COMPLETE_NO_PROMOTION_DECISION"
    assert payload["scientific_threshold_applied"] is False
    assert payload["rows"] == 2
    assert payload["identity_order_equal"] is True
    assert payload["changes"]["rows_with_scientific_output_change"] == 1
    assert payload["changes"]["newly_partial_rows"] == 1
    assert payload["changes"]["newly_parsed_rows"] == 0
    assert payload["changes"]["rows_with_new_conflicts"] == 0
    assert payload["experimental"]["selected_native_components"]["street"] == 0
    assert (
        payload["experimental"]["selected_component_rows_any_representation"]["street"]
        == 2
    )
    changes = payload["changes"]["component_selection_changes"]
    assert changes["street"] == {
        "newly_selected": 1,
        "lost_selection": 0,
        "changed_selection": 0,
    }
    assert changes["house_number"] == {
        "newly_selected": 1,
        "lost_selection": 0,
        "changed_selection": 0,
    }
    rule_metrics = payload["experimental"]["experimental_rule_evidence"]
    assert (
        rule_metrics["HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"]["selected_count"]
        == 1
    )
    assert (
        rule_metrics["STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V4"]["selected_count"] == 1
    )
    assert payload["page_checksums_verified"] is True
    assert output.stat().st_mode & 0o777 == 0o600
    serialized = output.read_text(encoding="utf-8")
    assert "Annex 12 Example Street" not in serialized
    assert "Example Street" not in serialized
    assert "fictional-provider" not in serialized
    assert str(tmp_path) not in serialized
    assert json.loads(serialized) == payload


def test_v2_v3_comparison_fails_closed_on_wrong_roles_and_identity_order(
    tmp_path: Path,
) -> None:
    v2_core, v2_evidence, v3_core, v3_evidence = _inputs(tmp_path)
    with pytest.raises(ValueError, match="parser-version"):
        compare_development_parser_v2_v3_outputs(
            v2_core,
            v2_evidence,
            v2_core,
            v2_evidence,
            tmp_path / "wrong-role.json",
            expected_rows=2,
        )
    revised = (
        pq.ParquetFile(v3_core, page_checksum_verification=True).read().to_pylist()
    )
    reordered = tmp_path / "v3-reordered"
    _write(reordered, list(reversed(revised)), core_schema())
    with pytest.raises(ValueError, match="identity/order"):
        compare_development_parser_v2_v3_outputs(
            v2_core,
            v2_evidence,
            reordered,
            v3_evidence,
            tmp_path / "wrong-order.json",
            expected_rows=2,
        )


def test_repaired_v2_1_v3_1_comparison_requires_repaired_roles(
    tmp_path: Path,
) -> None:
    baseline_root = tmp_path / "v2-1"
    revised_root = tmp_path / "v3-1"
    baseline_root.mkdir()
    revised_root.mkdir()
    baseline_parser = engine(baseline_root, parser_version=PARSER_VERSION_V2_1)
    revised_parser = engine(revised_root, parser_version=PARSER_VERSION_V3_1)
    rows = [
        phase02_row(
            street_address_line_1="Annex 12 Example Street",
            postcode="12345",
            city="Fiction City",
            country_iso_code="XZ",
        )
    ]
    baseline_results = [baseline_parser.transform(row) for row in rows]
    revised_results = [revised_parser.transform(row) for row in rows]
    baseline_core = tmp_path / "v2-1-core.parquet"
    baseline_evidence = tmp_path / "v2-1-evidence.parquet"
    revised_core = tmp_path / "v3-1-core.parquet"
    revised_evidence = tmp_path / "v3-1-evidence.parquet"
    _write(
        baseline_core,
        [result.core_row for result in baseline_results],
        core_schema(),
    )
    _write(
        baseline_evidence,
        [row for result in baseline_results for row in result.evidence_rows],
        evidence_schema(),
    )
    _write(
        revised_core,
        [result.core_row for result in revised_results],
        core_schema(),
    )
    _write(
        revised_evidence,
        [row for result in revised_results for row in result.evidence_rows],
        evidence_schema(),
    )
    output = tmp_path / "repaired-comparison.json"
    payload = compare_development_parser_v2_1_v3_1_outputs(
        baseline_core,
        baseline_evidence,
        revised_core,
        revised_evidence,
        output,
        expected_rows=1,
    )
    assert payload["report_version"] == (
        "phase03_development_parser_v2_1_v3_1_comparison_v1"
    )
    assert payload["baseline"]["parser_version"] == PARSER_VERSION_V2_1
    assert payload["experimental"]["parser_version"] == PARSER_VERSION_V3_1
    assert payload["changes"]["rows_with_scientific_output_change"] == 1
    with pytest.raises(ValueError, match="parser-version"):
        compare_development_parser_v2_v3_outputs(
            baseline_core,
            baseline_evidence,
            revised_core,
            revised_evidence,
            tmp_path / "historical-role-rejection.json",
            expected_rows=1,
        )


def test_repaired_v2_1_v3_2_comparison_uses_narrowed_rule_identity(
    tmp_path: Path,
) -> None:
    baseline_root = tmp_path / "v2-1"
    revised_root = tmp_path / "v3-2"
    baseline_root.mkdir()
    revised_root.mkdir()
    baseline_parser = engine(baseline_root, parser_version=PARSER_VERSION_V2_1)
    revised_parser = engine(revised_root, parser_version=PARSER_VERSION_V3_2)
    rows = [
        phase02_row(
            street_address_line_1="Example Street 12 Annex",
            postcode="12345",
            city="Fiction City",
            country_iso_code="XZ",
        ),
        phase02_row(
            id="fictional-provider-0002",
            stable_source_row_id_v1=bytes.fromhex("44" * 32),
            source_logical_record_number=2,
            street_address_line_1="Annex 12 Example Street",
            postcode="54321",
            city="Sample City",
            country_iso_code="XZ",
        ),
    ]
    baseline_results = [baseline_parser.transform(row) for row in rows]
    revised_results = [revised_parser.transform(row) for row in rows]
    baseline_core = tmp_path / "v2-1-core.parquet"
    baseline_evidence = tmp_path / "v2-1-evidence.parquet"
    revised_core = tmp_path / "v3-2-core.parquet"
    revised_evidence = tmp_path / "v3-2-evidence.parquet"
    _write(
        baseline_core,
        [result.core_row for result in baseline_results],
        core_schema(),
    )
    _write(
        baseline_evidence,
        [row for result in baseline_results for row in result.evidence_rows],
        evidence_schema(),
    )
    _write(
        revised_core,
        [result.core_row for result in revised_results],
        core_schema(),
    )
    _write(
        revised_evidence,
        [row for result in revised_results for row in result.evidence_rows],
        evidence_schema(),
    )
    output = tmp_path / "narrowed-comparison.json"
    payload = compare_development_parser_v2_1_v3_2_outputs(
        baseline_core,
        baseline_evidence,
        revised_core,
        revised_evidence,
        output,
        expected_rows=2,
    )
    assert payload["report_version"] == (
        "phase03_development_parser_v2_1_v3_2_comparison_v1"
    )
    assert payload["experimental"]["parser_version"] == PARSER_VERSION_V3_2
    assert payload["changes"]["rows_with_scientific_output_change"] == 1
    rule_metrics = payload["experimental"]["experimental_rule_evidence"]
    assert set(rule_metrics) == {
        "HOUSE_NUMBER_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
        "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
    }
    assert all(item["candidate_count"] == 1 for item in rule_metrics.values())
    assert all(item["selected_count"] == 1 for item in rule_metrics.values())
    serialized = output.read_text(encoding="utf-8")
    assert "Example Street 12 Annex" not in serialized
    assert "Annex 12 Example Street" not in serialized
    assert str(tmp_path) not in serialized

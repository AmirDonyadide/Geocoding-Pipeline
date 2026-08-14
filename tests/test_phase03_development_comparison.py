from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase03.constants import (
    PARSER_VERSION_V1,
    PARSER_VERSION_V2,
)
from safe_geocoding_pipeline.phase03.development_comparison import (
    compare_development_parser_outputs,
)
from safe_geocoding_pipeline.phase03.schema import core_schema

from phase03_helpers import engine, phase02_row


def _write_core(path: Path, rows: list[dict[str, object]]) -> None:
    table = pa.Table.from_pylist(rows, schema=core_schema())
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=3,
        version="2.4",
        data_page_version="1.0",
        write_page_checksum=True,
        write_statistics=False,
    )


def _comparison_inputs(tmp_path: Path) -> tuple[Path, Path]:
    v1 = engine(tmp_path, parser_version=PARSER_VERSION_V1)
    v2 = engine(tmp_path, parser_version=PARSER_VERSION_V2)
    input_rows = [
        phase02_row(street_address_line_1="12 Example Street"),
        phase02_row(
            id="fictional-provider-0002",
            stable_source_row_id_v1=bytes.fromhex("44" * 32),
            source_logical_record_number=2,
            street_address_line_1="Flat 42",
        ),
    ]
    baseline = tmp_path / "baseline.parquet"
    revised = tmp_path / "revised.parquet"
    _write_core(baseline, [v1.transform(row).core_row for row in input_rows])
    _write_core(revised, [v2.transform(row).core_row for row in input_rows])
    return baseline, revised


def test_sanitized_development_comparison_reports_aggregates_only(
    tmp_path: Path,
) -> None:
    baseline, revised = _comparison_inputs(tmp_path)
    output = tmp_path / "comparison.json"
    payload = compare_development_parser_outputs(
        baseline,
        revised,
        output,
        expected_rows=2,
    )
    assert payload["status"] == "COMPARISON_COMPLETE_NO_SCIENTIFIC_THRESHOLD_APPLIED"
    assert payload["rows"] == 2
    assert payload["identity_order_equal"] is True
    assert payload["baseline"]["selected_components"]["street"] == 0
    assert payload["revised"]["selected_components"]["street"] == 1
    assert payload["revised"]["selected_components"]["house_number"] == 1
    assert payload["revised"]["selected_components"]["unit"] == 1
    assert set(payload["revised"]["address_parse_status"]) == {
        "PARSED",
        "PARTIAL",
        "AMBIGUOUS",
        "CONFLICT",
        "UNPARSEABLE",
        "INSUFFICIENT",
    }
    assert set(payload["revised"]["conflicts_by_type"]) == {
        "COUNTRY_SOURCE_CONFLICT",
        "COUNTRY_MULTIPLE_CANDIDATES",
        "POSTCODE_SOURCE_CONFLICT",
        "POSTCODE_MULTIPLE_CANDIDATES",
        "LOCALITY_SOURCE_CONFLICT",
        "LOCALITY_MULTIPLE_CANDIDATES",
        "REGION_SOURCE_CONFLICT",
        "REGION_MULTIPLE_CANDIDATES",
        "STREET_MULTIPLE_CANDIDATES",
        "HOUSE_NUMBER_MULTIPLE_CANDIDATES",
        "HOUSE_NUMBER_POSTCODE_ROLE_CONFLICT",
        "UNIT_HOUSE_NUMBER_ROLE_CONFLICT",
        "BUILDING_ORGANIZATION_ROLE_CONFLICT",
        "COMPONENT_SPAN_OVERLAP_CONFLICT",
        "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT",
        "NATIVE_NON_NATIVE_POSTCODE_CONFLICT",
        "NATIVE_NON_NATIVE_COUNTRY_CONFLICT",
    }
    assert payload["revised"]["selected_components"]["postcode"] == 0
    assert payload["revised"]["selected_provenance_by_representation"] == {
        "NON_NATIVE": 3,
        "NATIVE": 0,
        "SHARED": 0,
    }
    assert output.stat().st_mode & 0o777 == 0o600
    serialized = output.read_text(encoding="utf-8")
    assert "Example Street" not in serialized
    assert "Flat 42" not in serialized
    assert "fictional-provider" not in serialized
    assert str(tmp_path) not in serialized
    assert set(json.loads(serialized)) == set(payload)


def test_development_comparison_rejects_identity_or_order_mismatch(
    tmp_path: Path,
) -> None:
    baseline, revised = _comparison_inputs(tmp_path)
    revised_rows = pq.ParquetFile(
        revised, page_checksum_verification=True
    ).read().to_pylist()
    _write_core(tmp_path / "reordered.parquet", list(reversed(revised_rows)))
    with pytest.raises(ValueError, match="identity/order"):
        compare_development_parser_outputs(
            baseline,
            tmp_path / "reordered.parquet",
            tmp_path / "comparison.json",
            expected_rows=2,
        )


def test_development_comparison_rejects_wrong_parser_role(tmp_path: Path) -> None:
    baseline, _ = _comparison_inputs(tmp_path)
    with pytest.raises(ValueError, match="parser-version"):
        compare_development_parser_outputs(
            baseline,
            baseline,
            tmp_path / "comparison.json",
            expected_rows=2,
        )


def test_development_comparison_rejects_wrong_registry_role(tmp_path: Path) -> None:
    baseline, revised = _comparison_inputs(tmp_path)
    revised_rows = pq.ParquetFile(
        revised, page_checksum_verification=True
    ).read().to_pylist()
    revised_rows[0]["rule_registry_version"] = "phase03_rule_registry_v2"
    wrong = tmp_path / "wrong-registry.parquet"
    _write_core(wrong, revised_rows)
    with pytest.raises(ValueError, match="rule-registry"):
        compare_development_parser_outputs(
            baseline,
            wrong,
            tmp_path / "comparison.json",
            expected_rows=2,
        )

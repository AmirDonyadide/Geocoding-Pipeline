from __future__ import annotations

from pathlib import Path

from safe_geocoding_pipeline.phase03.benchmark import run_scenario
from safe_geocoding_pipeline.phase03.constants import PARSER_VERSION_V2


def test_synthetic_benchmark_is_fictional_validated_and_privacy_safe(
    tmp_path: Path,
) -> None:
    metrics = run_scenario(
        scenario="CANDIDATE_HEAVY",
        row_count=12,
        output_directory=tmp_path,
    )
    assert metrics["synthetic_rows"] == 12
    assert metrics["evidence_rows"] > 0
    assert metrics["candidates_per_source_row"] > 1
    assert metrics["semantic_digest_validation"] == "PASS"
    assert metrics["page_checksum_validation"] == "PASS"
    assert not any(
        forbidden in str(metrics)
        for forbidden in ("Fictional Research", "Exampleville", "PO Box")
    )


def test_parser_v2_recall_stress_benchmark_reports_synthetic_quality_only(
    tmp_path: Path,
) -> None:
    metrics = run_scenario(
        scenario="PARSER_RECALL_STRESS",
        row_count=12,
        output_directory=tmp_path,
        parser_version=PARSER_VERSION_V2,
    )
    assert metrics["parser_version"] == PARSER_VERSION_V2
    quality = metrics["synthetic_quality_no_acceptance_threshold"]
    assert quality["street_clean"]["recall"] == 1.0
    assert quality["house_number_clean"]["precision"] == 1.0
    assert quality["unit_clean"]["recall"] == 1.0
    assert "acceptance" not in str(quality).lower()

from __future__ import annotations

from pathlib import Path

from safe_geocoding_pipeline.phase03.benchmark import run_scenario


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

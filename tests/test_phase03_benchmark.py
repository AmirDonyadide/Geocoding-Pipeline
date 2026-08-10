from __future__ import annotations

import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase03.benchmark import run_scenario

DEFAULT_COUNTRY_ARTIFACT = Path(
    "external_data/phase03/references/un_m49_20260810T203327Z/"
    "un_m49_country_area_codes_v1.json"
)


def test_synthetic_benchmark_is_fictional_validated_and_privacy_safe(
    tmp_path: Path,
) -> None:
    artifact = Path(
        os.environ.get(
            "PHASE03_COUNTRY_REFERENCE_ARTIFACT", str(DEFAULT_COUNTRY_ARTIFACT)
        )
    )
    if not artifact.exists():
        pytest.skip("controlled UN M49 operational artifact is not provisioned")
    metrics = run_scenario(
        scenario="CANDIDATE_HEAVY",
        row_count=12,
        country_artifact=artifact,
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

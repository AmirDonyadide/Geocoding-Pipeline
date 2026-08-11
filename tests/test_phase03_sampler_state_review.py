from __future__ import annotations

from pathlib import Path
import json

import pytest

from safe_geocoding_pipeline.phase03.models import PilotCandidate
from safe_geocoding_pipeline.phase03.constants import EVIDENCE_SIDECAR_POLICY_VERSION
from safe_geocoding_pipeline.phase03.cli import main as phase03_main
from safe_geocoding_pipeline.phase03.review import (
    hashed_review_id,
    manual_review_schema,
    validate_portable_review_columns,
)
from safe_geocoding_pipeline.phase03.sampler import (
    PilotSamplingConfig,
    select_and_seal_pilot,
)
from safe_geocoding_pipeline.phase03.state import Phase03RunState

from phase03_helpers import engine, phase02_row


def _population(count: int = 200) -> list[PilotCandidate]:
    values: list[PilotCandidate] = []
    for index in range(count):
        country = f"country_{index % 10}"
        script = "rare_script" if index < 3 else f"script_{index % 4}"
        values.append(
            PilotCandidate(
                stable_source_row_id_v1=index.to_bytes(32, "big"),
                strata={
                    "country_cohort": country,
                    "script_category": script,
                    "postcode_type": f"postcode_{index % 5}",
                    "structured_completeness": f"complete_{index % 3}",
                },
                targeted_safety_case=index == 199,
            )
        )
    return values


def test_pilot_sampler_is_deterministic_stratified_separated_and_order_independent() -> (
    None
):
    config = PilotSamplingConfig(
        development_count=30,
        locked_evaluation_count=20,
        minimum_per_stratum=3,
        maximum_primary_stratum=8,
    )
    population = _population()
    first = select_and_seal_pilot(
        population,
        config=config,
        input_phase02_manifest_identity="fictional-phase02-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
    )
    second = select_and_seal_pilot(
        reversed(population),
        config=config,
        input_phase02_manifest_identity="fictional-phase02-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
    )
    assert first == second
    assert len(first.development_ids) == 30
    assert len(first.locked_evaluation_ids) == 20
    assert set(first.development_ids).isdisjoint(first.locked_evaluation_ids)
    assert (199).to_bytes(32, "big") in {
        *first.development_ids,
        *first.locked_evaluation_ids,
    }
    selected = set(first.development_ids) | set(first.locked_evaluation_ids)
    selected_candidates = [
        candidate
        for candidate in population
        if candidate.stable_source_row_id_v1 in selected
    ]
    assert {index.to_bytes(32, "big") for index in range(3)} <= selected
    country_counts: dict[str, int] = {}
    for candidate in selected_candidates:
        country = candidate.strata["country_cohort"]
        country_counts[country] = country_counts.get(country, 0) + 1
    assert max(country_counts.values()) <= config.maximum_primary_stratum
    for key, value in {
        (key, value)
        for candidate in population
        for key, value in candidate.strata.items()
    }:
        available = sum(candidate.strata.get(key) == value for candidate in population)
        represented = sum(
            candidate.strata.get(key) == value for candidate in selected_candidates
        )
        assert represented >= min(available, config.minimum_per_stratum)
    assert not any(
        isinstance(value, (list, tuple)) for value in first.portable_summary().values()
    )
    assert "locked_evaluation_ids" not in first.portable_summary()


def test_pilot_sampler_rejects_duplicate_ids_and_unfillable_caps() -> None:
    population = _population(20)
    with pytest.raises(ValueError, match="duplicate stable IDs"):
        select_and_seal_pilot(
            population + [population[0]],
            config=PilotSamplingConfig(
                development_count=5,
                locked_evaluation_count=5,
                minimum_per_stratum=1,
                maximum_primary_stratum=5,
            ),
            input_phase02_manifest_identity="fictional",
        )


def test_full_size_synthetic_sampler_keeps_locked_identities_out_of_summary() -> None:
    population = [
        PilotCandidate(
            stable_source_row_id_v1=index.to_bytes(32, "big"),
            strata={
                "country_cohort": f"country_{index % 50}",
                "script_category": f"script_{index % 12}",
                "postcode_type": f"postcode_{index % 8}",
                "structured_completeness": f"complete_{index % 6}",
            },
            targeted_safety_case=index < 25,
        )
        for index in range(25_000)
    ]
    config = PilotSamplingConfig()
    first = select_and_seal_pilot(
        population,
        config=config,
        input_phase02_manifest_identity="fictional-phase02-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
    )
    second = select_and_seal_pilot(
        reversed(population),
        config=config,
        input_phase02_manifest_identity="fictional-phase02-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
    )
    assert first == second
    assert len(first.development_ids) == 8_000
    assert len(first.locked_evaluation_ids) == 4_000
    assert set(first.development_ids).isdisjoint(first.locked_evaluation_ids)
    summary = first.portable_summary()
    assert summary["development_count"] == 8_000
    assert summary["locked_evaluation_count"] == 4_000
    assert "development_ids" not in summary
    assert "locked_evaluation_ids" not in summary
    with pytest.raises(ValueError, match="quotas/caps cannot"):
        select_and_seal_pilot(
            population,
            config=PilotSamplingConfig(
                development_count=10,
                locked_evaluation_count=10,
                minimum_per_stratum=1,
                maximum_primary_stratum=1,
            ),
            input_phase02_manifest_identity="fictional",
        )


def test_run_state_resume_identity_transitions_and_integrity(tmp_path: Path) -> None:
    path = tmp_path / "phase03.sqlite3"
    with Phase03RunState(path) as state:
        state.prepare_shard(
            "fictional.parquet",
            phase02_output_sha256="11" * 32,
            configuration_fingerprint="22" * 32,
            implementation_fingerprint="33" * 32,
        )
        state.transition(
            "fictional.parquet",
            "WRITING",
            attempt=1,
            temporary_core_path=".in_progress/core.tmp",
            temporary_evidence_path=".in_progress/evidence.tmp",
        )
        state.transition("fictional.parquet", "VALIDATING")
        state.transition(
            "fictional.parquet",
            "COMPLETE",
            core_semantic_digest="44" * 32,
            evidence_semantic_digest="55" * 32,
            core_output_sha256="66" * 32,
            evidence_output_sha256="77" * 32,
            final_core_path="core/fictional.parquet",
            final_evidence_path="evidence/fictional.parquet",
        )
        assert state.get("fictional.parquet")["status"] == "COMPLETE"
        assert state.integrity_check() == "ok"
        with pytest.raises(RuntimeError, match="identity changed"):
            state.prepare_shard(
                "fictional.parquet",
                phase02_output_sha256="99" * 32,
                configuration_fingerprint="22" * 32,
                implementation_fingerprint="33" * 32,
            )
        with pytest.raises(ValueError, match="invalid Phase 3 state transition"):
            state.transition("fictional.parquet", "WRITING", attempt=2)
    assert not (tmp_path / "_SUCCESS.json").exists()


def test_manual_review_schema_uses_hashed_identity_and_excludes_raw_values() -> None:
    schema = manual_review_schema()
    assert "hashed_review_id" in schema.names
    assert "id" not in schema.names
    assert "raw_address" not in schema.names
    assert "postcode" not in schema.names
    validate_portable_review_columns(set(schema.names))
    first = hashed_review_id(bytes.fromhex("11" * 32), "phase03_pilot_v1")
    second = hashed_review_id(bytes.fromhex("11" * 32), "phase03_pilot_v1")
    assert first == second and len(first) == 64
    with pytest.raises(ValueError, match="prohibited"):
        validate_portable_review_columns(set(schema.names) | {"raw_address"})


def test_evidence_sidecar_is_sparse_for_direct_structured_propagation(
    tmp_path: Path,
) -> None:
    parser = engine(tmp_path)
    direct = parser.transform(
        phase02_row(postcode="00123", city="Exampleville", country_iso_code="XZ")
    )
    marker = parser.transform(
        phase02_row(street_address_line_1="Apt 7B", city="Exampleville")
    )
    assert len(direct.evidence_rows) == 0
    assert len(marker.evidence_rows) == 2
    assert {item["component"] for item in marker.evidence_rows} == {
        "UNIT",
        "HOUSE_NUMBER",
    }
    assert next(
        item
        for item in marker.evidence_rows
        if item["component"] == "HOUSE_NUMBER"
    )["selected"] is False
    assert EVIDENCE_SIDECAR_POLICY_VERSION == "evidence_sidecar_policy_v1"


def test_phase03_cli_is_validation_only_and_privacy_safe(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert phase03_main(["framework-info"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FRAMEWORK_ONLY"
    assert payload["pilot_ready"] is True
    assert payload["real_pilot_authorized"] is False
    assert payload["production_country_reference"] == (
        "country_reference_v2_iso_normative_cldr_46_1_operational"
    )
    assert payload["production_script_reference"] == (
        "unicode_ucd_16_0_0_scripts_20240430"
    )
    assert "transform" not in payload

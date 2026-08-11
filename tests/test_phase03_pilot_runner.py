from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import fictional_country_reference, fictional_script_reference
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.models import PilotCandidate
from safe_geocoding_pipeline.phase03.pilot_runner import (
    SAMPLING_COLUMNS,
    ProductionSamplingContract,
    Phase01SafetyLocationTracker,
    REVIEW_TARGETS,
    ReviewCandidate,
    SQLitePilotCandidateStore,
    address_line_structure_v1,
    classify_postcode_v1,
    classify_sampling_row_v1,
    country_sampling_group_v1,
    load_phase01_safety_locations,
    marker_strata_v1,
    materialize_development_payload,
    read_identity_set,
    representation_strata_v1,
    sampling_contract_summary,
    select_development_review_sample_plan,
    select_development_review_sample,
    write_identity_set,
    write_pilot_seal,
    write_review_artifacts,
)
from safe_geocoding_pipeline.phase03.review import manual_review_schema
from safe_geocoding_pipeline.phase03.sampler import PilotSamplingConfig
from safe_geocoding_pipeline.phase03.sampler import PilotSelection
from safe_geocoding_pipeline.phase03.rules import load_rule_registry


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional:{index}".encode()).digest()


def _phase02_row(index: int) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in base_staging_schema():
        if pa.types.is_string(field.type):
            row[field.name] = ""
        elif pa.types.is_uint64(field.type):
            row[field.name] = index + 1
        else:
            row[field.name] = _identity(index)
    row.update(
        {
            "id": f"fictional-provider-{index}",
            "street_address_line_1": f"Fictional Road {index}",
            "postcode": f"0{index:04d}",
            "country_iso_code": "XZ",
            "location_information": "no_geocoding_information",
            "source_file": "fictional.parquet",
            "stable_source_row_id_v1": _identity(index),
            "source_file_sha256": bytes.fromhex("22" * 32),
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
    )
    return row


def _write_phase02(path: Path, rows: list[dict[str, Any]]) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=base_staging_schema()),
        path,
        write_page_checksum=True,
        write_statistics=False,
    )


def test_production_contract_is_frozen_and_approved() -> None:
    contract = ProductionSamplingContract()
    contract.validate(production=True)
    summary = sampling_contract_summary(contract)
    assert summary["selected_columns"] == list(SAMPLING_COLUMNS)
    assert summary["expected_selected_column_passes"] == 2
    assert summary["future_payload_passes"] == 1
    assert summary["status"] == "APPROVED"
    assert summary["unresolved_scientific_decisions"] == []
    assert contract.review_allocations == REVIEW_TARGETS
    assert contract.fingerprint() == (
        "0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7"
    )


def test_production_candidate_store_requires_approved_contract(tmp_path: Path) -> None:
    config = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=1,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    with pytest.raises(Phase03Error, match="PILOT_PRODUCTION_CONTRACT_NOT_APPROVED"):
        SQLitePilotCandidateStore(
            tmp_path / "production.sqlite3", config=config, data_scope="PRODUCTION"
        )
    with pytest.raises(Phase03Error, match="PILOT_PRODUCTION_STATE_BINDING_MISSING"):
        SQLitePilotCandidateStore(
            tmp_path / "production-bound.sqlite3",
            config=config,
            data_scope="PRODUCTION",
            classification_contract=ProductionSamplingContract(),
        )


def test_full_sampling_classifier_uses_explicit_fictional_contract(
    tmp_path: Path,
) -> None:
    contract = ProductionSamplingContract(
        country_large_min_count=10,
        country_medium_min_count=3,
        structured_high_min_fields=4,
        structured_medium_min_fields=2,
        review_allocations=(("parse_status", "CONFLICT", 1),),
        approval_status="APPROVED",
    )
    contract.validate(production=True)
    row: dict[str, Any] = {name: "" for name in SAMPLING_COLUMNS}
    row.update(
        {
            "stable_source_row_id_v1": _identity(100),
            "source_file": "fictional.csv",
            "source_logical_record_number": 101,
            "street_address_line_1": "PO Box 7",
            "street_address_line_1_native": "شارع",
            "postcode": "0123",
            "city": "Fiction City",
            "region_in_country": "Fiction Region",
            "country_iso_code": "XZ",
            "location_information": "previous_geocoding_failure",
        }
    )
    candidate = classify_sampling_row_v1(
        row,
        contract=contract,
        country_reference=fictional_country_reference(tmp_path),
        script_reference=fictional_script_reference(tmp_path),
        rule_registry=load_rule_registry(),
        country_counts={"ASSIGNED:XZ": 100},
    )
    assert candidate.strata["primary_country_group"] == "ASSIGNED:XZ"
    assert candidate.strata["country_cohort"] == "LARGE"
    assert candidate.strata["structured_completeness"] == "HIGH"
    assert candidate.strata["postcode_lexical"] == "LEADING_ZERO_ASCII_DIGITS"
    assert candidate.strata["marker_po_box"] == "PO_BOX_MARKER_PRESENT"
    assert candidate.strata["location_information"] == (
        "PREVIOUS_GEOCODING_FAILURE"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "SEMANTIC_MISSING"),
        ("Na", "AMBIGUOUS_PLACEHOLDER_LIKE"),
        ("12.5", "DECIMAL_LOOKING"),
        ("+12.5", "OTHER"),
        ("12 34", "CONTAINS_UNICODE_WHITESPACE"),
        ("12-34", "CONTAINS_ASCII_HYPHEN"),
        ("0123", "LEADING_ZERO_ASCII_DIGITS"),
        ("123", "ASCII_DIGITS"),
        ("ABC", "ASCII_LETTERS"),
        ("A12", "ASCII_ALPHANUMERIC"),
        ("١٢٣", "OTHER"),
    ],
)
def test_postcode_precedence_is_exact_and_string_safe(raw: str, expected: str) -> None:
    assert classify_postcode_v1(raw) == expected


def test_country_sampling_preserves_na_safety(tmp_path: Path) -> None:
    reference = fictional_country_reference(tmp_path)
    assert country_sampling_group_v1("NA", reference) == (
        "ASSIGNED:NA",
        "ASSIGNED_EXACT",
    )
    assert country_sampling_group_v1("Na", reference) == (
        "AMBIGUOUS_PLACEHOLDER",
        "AMBIGUOUS_PLACEHOLDER",
    )
    unusual, category = country_sampling_group_v1("xz", reference)
    assert unusual.startswith("UNUSUAL:")
    assert category == "UNUSUAL"


def test_line_and_script_classifiers_do_not_infer_language(tmp_path: Path) -> None:
    row = {name: "" for name in SAMPLING_COLUMNS}
    row.update(
        {
            "street_address_line_1": "Cafe\u0301",
            "street_address_line_1_native": "Café",
        }
    )
    assert address_line_structure_v1(row)["line_count_relationship"] == "EQUAL"
    representation = representation_strata_v1(row, fictional_script_reference(tmp_path))
    assert representation["native_relationship"] == "NFC_EQUIVALENT"
    assert representation["non_native_script"] == "LATIN_ONLY"
    assert representation["native_script"] == "LATIN_ONLY"
    row["street_address_line_2"] = "X" * 65_537
    representation = representation_strata_v1(row, fictional_script_reference(tmp_path))
    assert representation["representation_oversized_skipped"] == "TRUE"
    assert representation["non_native_script"] == "OVERSIZED_SKIPPED"


def test_ambiguous_address_lines_do_not_count_as_content(tmp_path: Path) -> None:
    row = {name: "" for name in SAMPLING_COLUMNS}
    row["street_address_line_1"] = "Na"
    row["street_address_line_1_native"] = "شارع"
    structure = address_line_structure_v1(row)
    assert structure == {
        "non_native_line_count": "0",
        "native_line_count": "1",
        "line_count_relationship": "MORE_NATIVE",
        "non_native_ambiguous_present": "TRUE",
        "native_ambiguous_present": "FALSE",
    }
    representation = representation_strata_v1(row, fictional_script_reference(tmp_path))
    assert representation["native_relationship"] == "NATIVE_ONLY"
    assert representation["non_native_script"] == "NO_CONTENT"
    assert representation["native_script"] == "SINGLE_NON_LATIN"


def test_marker_strata_reuse_frozen_registry_and_keep_house_shadow_only() -> None:
    row = {name: "" for name in SAMPLING_COLUMNS}
    row["street_address_line_1"] = "12 Fictional Road"
    values = marker_strata_v1(row, load_rule_registry())
    assert values["shadow_house_candidate"] == "SHADOW_HOUSE_CANDIDATE_PRESENT"
    assert "house_number_clean" not in values
    assert "street_clean" not in values


def test_phase01_safety_locations_use_only_sanitized_provenance(tmp_path: Path) -> None:
    path = tmp_path / "phase01_anomalies.csv"
    path.write_text(
        "relative_path,logical_record_number,anomaly_type,message_code\n"
        "fictional_1.csv,7,MULTILINE_RECORD,FICTIONAL\n"
        "fictional_1.csv,7,OVERSIZED_FIELD,FICTIONAL\n"
        "fictional_2.csv,9,OTHER,FICTIONAL\n",
        encoding="utf-8",
    )
    assert load_phase01_safety_locations(path) == {
        ("fictional_1.csv", 7): ("MULTILINE_RECORD", "OVERSIZED_FIELD")
    }
    tracker = Phase01SafetyLocationTracker.from_report(path)
    assert tracker.observe("ordinary.csv", 1) is False
    assert tracker.observe("fictional_1.csv", 7) is True
    tracker.validate_complete()
    with pytest.raises(ValueError, match="more than once"):
        tracker.observe("fictional_1.csv", 7)


def _candidate(index: int) -> PilotCandidate:
    return PilotCandidate(
        _identity(index),
        {
            "primary_country_group": f"ASSIGNED:C{index % 30:02d}",
            "country_cohort": "COUNTRY_COHORT_LARGE"
            if index % 3
            else "COUNTRY_COHORT_RARE",
            "postcode_lexical": f"POSTCODE_CLASS_{index % 10}",
            "script_category": f"SCRIPT_CLASS_{index % 4}",
        },
        targeted_safety_case=index in {1, 2, 3},
    )


def _selection(
    path: Path, population: list[PilotCandidate], batch_size: int
) -> PilotSelection:
    config = PilotSamplingConfig(
        development_count=8_000,
        locked_evaluation_count=4_000,
        minimum_per_stratum=50,
        maximum_primary_stratum=500,
        primary_stratum="primary_country_group",
    )
    store = SQLitePilotCandidateStore(path, config=config)
    try:
        assert store.ingest(population, batch_size=batch_size) == len(population)
        return store.select(
            input_phase02_manifest_identity="fictional-phase02-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
        )
    finally:
        store.close()


def test_out_of_core_12000_selection_is_order_and_batch_independent(
    tmp_path: Path,
) -> None:
    population = [_candidate(index) for index in range(13_500)]
    first = _selection(tmp_path / "first.sqlite3", population, 137)
    second = _selection(tmp_path / "second.sqlite3", list(reversed(population)), 997)
    assert len(first.development_ids) == 8_000
    assert len(first.locked_evaluation_ids) == 4_000
    assert set(first.development_ids).isdisjoint(first.locked_evaluation_ids)
    assert first.development_ids == second.development_ids
    assert first.locked_evaluation_ids == second.locked_evaluation_ids
    assert first.seal == second.seal


def test_every_rare_primary_group_row_is_forced_into_pilot(tmp_path: Path) -> None:
    population = [_candidate(index) for index in range(13_500)]
    rare_ids: set[bytes] = set()
    adjusted: list[PilotCandidate] = []
    for index, candidate in enumerate(population):
        strata = dict(candidate.strata)
        if index < 40:
            strata["primary_country_group"] = "ASSIGNED:RA"
            strata["country_cohort"] = "RARE"
            rare_ids.add(candidate.stable_source_row_id_v1)
        else:
            strata["country_cohort"] = "LARGE"
        adjusted.append(
            PilotCandidate(
                candidate.stable_source_row_id_v1,
                strata,
                candidate.targeted_safety_case,
            )
        )
    selection = _selection(tmp_path / "rare.sqlite3", adjusted, 311)
    assert rare_ids.issubset(
        set(selection.development_ids) | set(selection.locked_evaluation_ids)
    )


def test_candidate_store_rejects_duplicate_identity(tmp_path: Path) -> None:
    config = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=1,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    store = SQLitePilotCandidateStore(tmp_path / "duplicates.sqlite3", config=config)
    try:
        with pytest.raises(ValueError, match="duplicate stable IDs"):
            store.ingest([_candidate(1), _candidate(1)])
    finally:
        store.close()


def test_identity_storage_and_seal_are_exact_atomic_and_owner_only(
    tmp_path: Path,
) -> None:
    identities = [_identity(index) for index in range(5)]
    path = tmp_path / "controlled" / "development.identities.bin"
    metadata = write_identity_set(
        path,
        identities,
        partition="DEVELOPMENT",
        manifest_identity="fictional-manifest",
        sampling_config_fingerprint="aa" * 32,
    )
    observed_metadata, observed = read_identity_set(path)
    assert observed_metadata == metadata
    assert observed == tuple(sorted(identities))
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    damaged = tmp_path / "damaged.bin"
    damaged.write_bytes(path.read_bytes()[:-1] + b"x")
    with pytest.raises(ValueError, match="checksum"):
        read_identity_set(damaged)

    # Construct a minimal portable seal without persisting identities in JSON.
    from safe_geocoding_pipeline.phase03.models import PilotSeal

    seal = PilotSeal(
        pilot_version="phase03_pilot_v1",
        sampling_config_fingerprint="aa" * 32,
        seed="fictional-seed",
        development_identity_digest="bb" * 32,
        locked_evaluation_identity_digest="cc" * 32,
        selection_timestamp="2026-01-01T00:00:00Z",
        input_phase02_manifest_identity="fictional-manifest",
        development_count=5,
        locked_evaluation_count=2,
    )
    seal_path = tmp_path / "controlled" / "pilot_seal.json"
    write_pilot_seal(
        seal_path,
        seal,
        sampler_version="phase03_pilot_runner_v1",
        git_commit="deadbeef",
        reference_configuration_fingerprint="dd" * 32,
    )
    seal_text = seal_path.read_text()
    assert "stable_source_row_id" not in seal_text
    assert seal_path.stat().st_mode & 0o777 == 0o600


def test_development_only_payload_join_and_reconciliation(tmp_path: Path) -> None:
    rows = [_phase02_row(index) for index in range(8)]
    first = tmp_path / "synthetic_b.parquet"
    second = tmp_path / "synthetic_a.parquet"
    _write_phase02(first, list(reversed(rows[:4])))
    _write_phase02(second, list(reversed(rows[4:])))
    development = {_identity(index) for index in (0, 2, 4, 6)}
    locked = {_identity(index) for index in (1, 3)}
    output = tmp_path / "controlled" / "development.parquet"
    assert (
        materialize_development_payload(
            [second, first],
            output,
            development_ids=development,
            locked_ids=locked,
            batch_rows=2,
            expected_development_count=4,
        )
        == 4
    )
    values = {
        bytes(value)
        for value in pq.ParquetFile(
            output, page_checksum_verification=True
        ).read()["stable_source_row_id_v1"].to_pylist()
    }
    assert values == development
    assert values.isdisjoint(locked)
    assert output.stat().st_mode & 0o777 == 0o600


def test_development_join_rejects_missing_duplicate_and_partition_overlap(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.parquet"
    _write_phase02(source, [_phase02_row(0), _phase02_row(0)])
    with pytest.raises(ValueError, match="more than once"):
        materialize_development_payload(
            [source],
            tmp_path / "duplicate.parquet",
            development_ids={_identity(0)},
            locked_ids=set(),
            expected_development_count=1,
        )
    with pytest.raises(ValueError, match="overlap"):
        materialize_development_payload(
            [source],
            tmp_path / "overlap.parquet",
            development_ids={_identity(0)},
            locked_ids={_identity(0)},
        )
    with pytest.raises(ValueError, match="missing"):
        materialize_development_payload(
            [source],
            tmp_path / "missing.parquet",
            development_ids={_identity(9)},
            locked_ids=set(),
            expected_development_count=1,
        )


def test_candidate_store_shard_resume_is_atomic_and_fingerprint_bound(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=1,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    path = tmp_path / "resumable.sqlite3"
    store = SQLitePilotCandidateStore(path, config=config)
    assert store.ingest_shard(
        "fictional-shard-1", "sha256:fictional", [_candidate(1), _candidate(2)]
    ) == (2, False)
    assert store.ingest_shard(
        "fictional-shard-1", "sha256:fictional", []
    ) == (2, True)
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        store.ingest_shard("fictional-shard-1", "sha256:changed", [])
    store.close()

    reopened = SQLitePilotCandidateStore(path, config=config)
    assert reopened.ingest_shard(
        "fictional-shard-1", "sha256:fictional", []
    ) == (2, True)
    reopened.close()

    incompatible = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=2,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    with pytest.raises(ValueError, match="configuration mismatch"):
        SQLitePilotCandidateStore(path, config=incompatible)
    with pytest.raises(ValueError, match="configuration mismatch"):
        SQLitePilotCandidateStore(
            path,
            config=config,
            classification_contract_fingerprint="changed-contract",
        )


def test_safety_locations_survive_candidate_store_resume(tmp_path: Path) -> None:
    config = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=1,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    candidate = _candidate(99)
    targeted = PilotCandidate(
        candidate.stable_source_row_id_v1,
        candidate.strata,
        True,
        "fictional.csv",
        7,
    )
    path = tmp_path / "safety-resume.sqlite3"
    store = SQLitePilotCandidateStore(path, config=config)
    assert store.ingest_shard("one", "hash", [targeted]) == (1, False)
    assert store.safety_locations() == {("fictional.csv", 7)}
    store.close()
    reopened = SQLitePilotCandidateStore(path, config=config)
    assert reopened.ingest_shard("one", "hash", []) == (1, True)
    assert reopened.safety_locations() == {("fictional.csv", 7)}
    reopened.close()


def test_failed_shard_ingest_rolls_back_all_candidates(tmp_path: Path) -> None:
    config = PilotSamplingConfig(
        development_count=1,
        locked_evaluation_count=1,
        minimum_per_stratum=1,
        maximum_primary_stratum=2,
        primary_stratum="primary_country_group",
    )
    store = SQLitePilotCandidateStore(tmp_path / "rollback.sqlite3", config=config)
    with pytest.raises(ValueError, match="duplicate stable IDs"):
        store.ingest_shard(
            "fictional-failed", "sha256:fictional", [_candidate(1), _candidate(1)]
        )
    assert store.connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0] == 0
    assert store.connection.execute("SELECT COUNT(*) FROM checkpoint").fetchone()[0] == 0
    store.close()


def test_review_sampler_and_writers_are_deterministic_and_privacy_safe(
    tmp_path: Path,
) -> None:
    candidates = [
        ReviewCandidate(
            _identity(index),
            {
                "parse_status": "CONFLICT" if index % 5 == 0 else "PARSED",
                "shadow_house": "PRESENT" if index % 7 == 0 else "ABSENT",
            },
        )
        for index in range(100)
    ]
    allocations = (("parse_status", "CONFLICT", 10), ("shadow_house", "PRESENT", 5))
    first = select_development_review_sample(
        candidates, target_count=25, allocations=allocations
    )
    second = select_development_review_sample(
        reversed(candidates), target_count=25, allocations=allocations
    )
    assert first == second
    protected_rows = [
        {
            "stable_source_row_id_v1": identity,
            "fictional_raw_address": "Fictional context only",
        }
        for identity in first
    ]
    context, labels = write_review_artifacts(
        tmp_path / "review", protected_rows=protected_rows, review_ids=first,
        pilot_version="phase03_pilot_v1",
        independent_double_review_ids=first[:5],
    )
    assert context.stat().st_mode & 0o777 == 0o600
    assert labels.stat().st_mode & 0o777 == 0o600
    assert labels.parent.stat().st_mode & 0o777 == 0o700
    portable = pq.ParquetFile(labels, page_checksum_verification=True).read()
    assert portable.schema.names == manual_review_schema().names
    assert "fictional_raw_address" not in portable.schema.names
    assert "stable_source_row_id_v1" not in portable.schema.names
    assert "id" not in portable.schema.names
    assert portable.num_rows == 25
    assert sum(portable["is_independent_review"].to_pylist()) == 5


def test_frozen_800_row_review_plan_and_double_review_are_deterministic() -> None:
    candidates = []
    for index in range(8_000):
        strata = {
            "primary_country_cohort": ("LARGE", "MEDIUM", "RARE")[index % 3],
            "structured_completeness": ("HIGH", "MEDIUM", "LOW", "NONE")[index % 4],
            "script_category": ("LATIN_ONLY", "SINGLE_NON_LATIN")[index % 2],
            "address_parse_status": (
                "PARTIAL",
                "AMBIGUOUS",
                "CONFLICT",
                "UNPARSEABLE",
                "PARSED",
            )[index % 5],
            "diagnostic_evaluation_status": "INSUFFICIENT" if index % 7 == 0 else "SUFFICIENT",
        }
        for _, category, _ in REVIEW_TARGETS[5:]:
            if index % 13 == 0:
                strata[f"review_case:{category}"] = "TRUE"
        candidates.append(ReviewCandidate(_identity(index), strata))
    first = select_development_review_sample_plan(candidates)
    second = select_development_review_sample_plan(reversed(candidates))
    assert first == second
    assert len(first.review_ids) == 800
    assert len(first.broad_representation_ids) == 400
    assert len(first.independent_double_review_ids) == 200
    assert set(first.independent_double_review_ids).issubset(first.review_ids)


def test_unavailable_review_target_is_diagnostic_not_silent_failure() -> None:
    candidates = [
        ReviewCandidate(
            _identity(index),
            {
                "primary_country_cohort": "LARGE",
                "structured_completeness": "HIGH",
                "script_category": "LATIN_ONLY",
                "address_parse_status": "PARSED",
            },
        )
        for index in range(1_000)
    ]
    plan = select_development_review_sample_plan(candidates)
    assert len(plan.review_ids) == 800
    assert any(value.startswith("TARGET_NOT_FULLY_AVAILABLE:") for value in plan.diagnostics)


def test_sampling_selected_column_contract_excludes_provider_id() -> None:
    assert "id" not in SAMPLING_COLUMNS
    assert "batch_priority" not in SAMPLING_COLUMNS
    assert "source_file_sha256" not in SAMPLING_COLUMNS
    assert len(SAMPLING_COLUMNS) == 16


def test_pilot_plan_cli_does_not_read_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from safe_geocoding_pipeline.phase03.cli import main

    missing = tmp_path / "does-not-exist"
    assert main(
        [
            "pilot-plan",
            "--input-path",
            str(missing),
            "--output-path",
            str(tmp_path / "future-output"),
            "--git-commit",
            "fictional-commit",
        ]
    ) == 0
    payload = capsys.readouterr().out
    assert '"data_read":false' in payload
    assert '"status":"APPROVED"' in payload
    assert '"pass_1_columns":["country_iso_code"]' in payload
    assert '"candidate_state_backend":"SQLite"' in payload
    assert '"minimum_free_disk_bytes":26843545600' in payload
    assert not missing.exists()


def test_fictional_end_to_end_pilot_runner(tmp_path: Path) -> None:
    config = PilotSamplingConfig(
        development_count=8,
        locked_evaluation_count=4,
        minimum_per_stratum=1,
        maximum_primary_stratum=4,
        primary_stratum="primary_country_group",
    )
    candidates = [
        PilotCandidate(
            _identity(index),
            {
                "primary_country_group": f"ASSIGNED:F{index % 5}",
                "postcode_lexical": f"POSTCODE_{index % 3}",
                "script_category": f"SCRIPT_{index % 2}",
            },
            targeted_safety_case=index == 0,
        )
        for index in range(20)
    ]
    store = SQLitePilotCandidateStore(tmp_path / "e2e.sqlite3", config=config)
    assert store.ingest_shard("shard-a", "hash-a", candidates[:10]) == (10, False)
    assert store.ingest_shard("shard-b", "hash-b", candidates[10:]) == (10, False)
    selection = store.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
    )
    store.close()
    controlled = tmp_path / "controlled"
    development_path = controlled / "development.identities.bin"
    locked_path = controlled / "locked.identities.bin"
    write_identity_set(
        development_path,
        selection.development_ids,
        partition="DEVELOPMENT",
        manifest_identity="fictional-manifest",
        sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
    )
    write_identity_set(
        locked_path,
        selection.locked_evaluation_ids,
        partition="LOCKED_EVALUATION",
        manifest_identity="fictional-manifest",
        sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
    )
    write_pilot_seal(
        controlled / "seal.json",
        selection.seal,
        sampler_version="phase03_pilot_runner_v1",
        git_commit="fictional",
        reference_configuration_fingerprint="aa" * 32,
    )
    source_rows = [_phase02_row(index) for index in range(20)]
    shard_a = tmp_path / "fictional-a.parquet"
    shard_b = tmp_path / "fictional-b.parquet"
    _write_phase02(shard_a, source_rows[:10])
    _write_phase02(shard_b, source_rows[10:])
    payload = controlled / "development-payload.parquet"
    assert materialize_development_payload(
        [shard_b, shard_a],
        payload,
        development_ids=set(selection.development_ids),
        locked_ids=set(selection.locked_evaluation_ids),
        expected_development_count=8,
        batch_rows=3,
    ) == 8
    review_population = [
        ReviewCandidate(
            identity,
            {"parse_status": "CONFLICT" if index % 3 == 0 else "PARSED"},
        )
        for index, identity in enumerate(selection.development_ids)
    ]
    review_ids = select_development_review_sample(
        review_population,
        target_count=4,
        allocations=(("parse_status", "CONFLICT", 1),),
    )
    context_rows = [
        {
            "stable_source_row_id_v1": identity,
            "fictional_raw_address": "Synthetic Lane",
        }
        for identity in review_ids
    ]
    context, labels = write_review_artifacts(
        tmp_path / "review",
        protected_rows=context_rows,
        review_ids=review_ids,
        pilot_version="fictional-pilot",
    )
    assert pq.ParquetFile(context, page_checksum_verification=True).metadata.num_rows == 4
    assert pq.ParquetFile(labels, page_checksum_verification=True).metadata.num_rows == 4
    assert set(selection.development_ids).isdisjoint(selection.locked_evaluation_ids)

from __future__ import annotations

import csv
import hashlib
import json
import os
import stat
import struct
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from phase03_helpers import fictional_script_reference
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase01.config import (
    DEFAULT_PARSER_FIELD_LIMIT_CHARS,
)
from safe_geocoding_pipeline.phase01.constants import INVENTORY_VERSION
from safe_geocoding_pipeline.phase01.population import POPULATION_SCOPE_VERSION
from safe_geocoding_pipeline.preprocessing.benchmark_runner import (
    DEVELOPMENT_RELATIVE_PATH,
    HOLDOUT_RELATIVE_PATH,
    MANIFEST_NAME,
    SUCCESS_MARKER,
    SUMMARY_JSON_NAME,
    BenchmarkRunConfig,
    materialize_benchmark_sample,
    validate_materialized_benchmark,
)
from safe_geocoding_pipeline.preprocessing.benchmark_sample import (
    ALLOCATION_POLICY_VERSION,
    BENCHMARK_CONTRACT_VERSION,
    BENCHMARK_FINGERPRINT_DOMAIN,
    FEATURE_CONTRACT_VERSION,
    SELECTION_ALGORITHM_VERSION,
    BenchmarkCandidate,
    BenchmarkConfig,
    BenchmarkSelection,
    BenchmarkSourceProjection,
    BenchmarkValidationError,
    SamplingFeatures,
    SamplingPolicy,
    allocate_country_targets,
    benchmark_fingerprint_v1,
    build_quota_targets,
    classify_sampling_features,
    finalize_selection,
    make_candidate_heaps,
    offer_candidate,
    profile_feature_groups,
    rank_key_v1,
    split_rank_v1,
)
from safe_geocoding_pipeline.preprocessing.stages.s00_inventory import (
    parser_contract_fingerprint_v1,
)
from safe_geocoding_pipeline.raw_csv import SOURCE_COLUMNS, source_schema_fingerprint


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-row-{index}".encode()).digest()


def _feature(
    *,
    country: str = "DE",
    location: str = "previous_geocoding_failure",
    presence: str = "BOTH_PRESENT",
    equality: str = "EXACTLY_EQUAL",
    script: str = "LATIN_ONLY",
    challenge: bool = False,
) -> SamplingFeatures:
    return SamplingFeatures(
        location_information_stratum=location,
        batch_priority_stratum="1",
        country_stratum=country,
        standard_native_presence_class=presence,
        standard_native_equality_class=equality,
        standard_line_count=1,
        native_line_count=1,
        postcode_present=True,
        city_present=True,
        region_present=True,
        country_present=True,
        missingness_class=(
            "POSTCODE_PRESENT_CITY_PRESENT_REGION_PRESENT_COUNTRY_PRESENT"
        ),
        standard_script_class=script,
        native_script_class=script,
        combined_script_class=script,
        challenge_flag=challenge,
        challenge_reasons=("PREVIOUS_GEOCODING_FAILURE",) if challenge else (),
    )


def _candidate(
    index: int,
    *,
    source_file: str | None = None,
    features: SamplingFeatures | None = None,
) -> BenchmarkCandidate:
    return BenchmarkCandidate(
        stable_source_row_id_v1=_identity(index),
        source_file=source_file or f"fictional_{index % 3}.csv",
        source_logical_record_number=index + 1,
        features=features or _feature(country=("DE", "JP", "BR")[index % 3]),
    )


def _tiny_policy() -> SamplingPolicy:
    return SamplingPolicy(
        minimum_per_source_file=1,
        minimum_per_location=1,
        minimum_per_batch_priority=1,
        minimum_per_country=1,
        country_extra_budget=2,
        minimum_per_presence_class=1,
        minimum_per_equality_class=1,
        minimum_per_line_count=1,
        minimum_per_script_class=1,
        minimum_per_missingness_class=1,
        minimum_per_challenge_reason=1,
    )


def _select(
    candidates: list[BenchmarkCandidate], *, development: int, holdout: int
) -> BenchmarkSelection:
    counts = profile_feature_groups(
        (candidate.source_file, candidate.features) for candidate in candidates
    )
    country_non_latin = Counter(
        candidate.features.country_stratum
        for candidate in candidates
        if candidate.features.combined_script_class
        in {"NON_LATIN_PRESENT", "MIXED_SCRIPT"}
    )
    config = BenchmarkConfig(development, holdout, _tiny_policy())
    targets = build_quota_targets(counts, country_non_latin, policy=config.policy)
    quota_heaps, global_heap = make_candidate_heaps(
        targets, total_count=config.total_count
    )
    for candidate in candidates:
        offer_candidate(candidate, quota_heaps=quota_heaps, global_heap=global_heap)
    return finalize_selection(
        targets=targets,
        counts=counts,
        quota_heaps=quota_heaps,
        global_heap=global_heap,
        config=config,
    )


def _raw_row(**updates: str) -> dict[str, str]:
    row = {column: "" for column in SOURCE_COLUMNS}
    row.update(
        {
            "id": "fictional-provider-id",
            "street_address_line_1": "Fictional Road 001",
            "street_address_line_1_native": "Fictional Road 001",
            "postcode": "00123",
            "city": "Example City",
            "region_in_country": "Example Region",
            "country_iso_code": "DE",
            "batch_priority": "1",
            "location_information": "previous_geocoding_failure",
        }
    )
    row.update(updates)
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SOURCE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _write_scope(path: Path, relative_paths: list[str]) -> str:
    payload = {
        "population_scope_version": POPULATION_SCOPE_VERSION,
        "population_id": "benchmark-v1-fictional-population",
        "phase01_inventory_version": INVENTORY_VERSION,
        "source_schema_fingerprint": source_schema_fingerprint(SOURCE_COLUMNS),
        "parser_field_limit_chars": DEFAULT_PARSER_FIELD_LIMIT_CHARS,
        "expected_source_count": len(relative_paths),
        "relative_paths": sorted(relative_paths),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _synthetic_run_config(tmp_path: Path, output_name: str) -> BenchmarkRunConfig:
    source_root = tmp_path / "sources"
    if not source_root.exists():
        source_root.mkdir()
        for file_index in range(3):
            rows = []
            for row_index in range(12):
                updates: dict[str, str] = {
                    "id": f"fictional-{file_index}-{row_index}",
                    "country_iso_code": ("DE", "JP", "BR")[
                        (file_index + row_index) % 3
                    ],
                    "location_information": (
                        "previous_geocoding_failure"
                        if row_index % 2
                        else "no_geocoding_information"
                    ),
                }
                if row_index % 4 == 0:
                    updates["street_address_line_1_native"] = "東京架空一丁目"
                if row_index % 5 == 0:
                    updates["postcode"] = ""
                rows.append(_raw_row(**updates))
            _write_csv(source_root / f"fictional_{file_index}.csv", rows)
    scope = tmp_path / "population_scope.json"
    if not scope.exists():
        scope_hash = _write_scope(
            scope, [f"fictional_{index}.csv" for index in range(3)]
        )
    else:
        scope_hash = hashlib.sha256(scope.read_bytes()).hexdigest()
    return BenchmarkRunConfig(
        source_root=source_root,
        population_scope_file=scope,
        expected_population_scope_sha256=scope_hash,
        expected_source_count=3,
        output_directory=tmp_path / output_name,
        adopting_git_commit="a" * 40,
        benchmark_config=BenchmarkConfig(12, 6, _tiny_policy()),
        output_batch_rows=4,
        production=False,
        operational_metadata={"synthetic_run": output_name},
    )


def test_deterministic_selection_exact_disjoint_and_reproducible() -> None:
    candidates = [_candidate(index) for index in range(100)]
    first = _select(candidates, development=35, holdout=15)
    second = _select(list(reversed(candidates)), development=35, holdout=15)
    assert [item.stable_source_row_id_v1 for item in first.development] == [
        item.stable_source_row_id_v1 for item in second.development
    ]
    assert [item.stable_source_row_id_v1 for item in first.holdout] == [
        item.stable_source_row_id_v1 for item in second.holdout
    ]
    assert len(first.development) == 35
    assert len(first.holdout) == 15
    assert not (
        {item.stable_source_row_id_v1 for item in first.development}
        & {item.stable_source_row_id_v1 for item in first.holdout}
    )
    assert len({item.stable_source_row_id_v1 for item in first.all_candidates}) == 50


def test_rank_and_split_keys_depend_only_on_immutable_identity() -> None:
    identity = _identity(1)
    first = _candidate(1, features=_feature(country="DE"))
    changed_address_features = _feature(
        country="JP",
        presence="NATIVE_ONLY",
        equality="NOT_BOTH_PRESENT",
        script="NON_LATIN_PRESENT",
    )
    second = _candidate(1, features=changed_address_features)
    assert first.stable_source_row_id_v1 == second.stable_source_row_id_v1 == identity
    assert rank_key_v1("quota-selection", identity) == rank_key_v1(
        "quota-selection", second.stable_source_row_id_v1
    )
    assert split_rank_v1(identity) == split_rank_v1(second.stable_source_row_id_v1)


@pytest.mark.parametrize(
    ("updates", "presence", "equality"),
    [
        ({"street_address_line_1_native": ""}, "STANDARD_ONLY", "NOT_BOTH_PRESENT"),
        (
            {"street_address_line_1": "", "street_address_line_1_native": "東京"},
            "NATIVE_ONLY",
            "NOT_BOTH_PRESENT",
        ),
        ({}, "BOTH_PRESENT", "EXACTLY_EQUAL"),
        (
            {"street_address_line_1_native": "fictional road 001"},
            "BOTH_PRESENT",
            "CASE_ONLY_OR_TRIVIALLY_EQUAL",
        ),
        (
            {"street_address_line_1_native": "別の通り"},
            "BOTH_PRESENT",
            "MATERIALLY_DIFFERENT",
        ),
        (
            {"street_address_line_1": "", "street_address_line_1_native": ""},
            "NEITHER_PRESENT",
            "NOT_BOTH_PRESENT",
        ),
    ],
)
def test_standard_native_presence_and_equality_categories(
    tmp_path: Path,
    updates: dict[str, str],
    presence: str,
    equality: str,
) -> None:
    observed = classify_sampling_features(
        _raw_row(**updates), script_reference=fictional_script_reference(tmp_path)
    )
    assert observed.standard_native_presence_class == presence
    assert observed.standard_native_equality_class == equality


def test_line_counts_missingness_and_challenge_are_raw_and_deterministic(
    tmp_path: Path,
) -> None:
    row = _raw_row(
        street_address_line_2="  ",
        street_address_line_2_native="第二行",
        postcode="",
        city="",
        region_in_country="",
        country_iso_code="",
    )
    observed = classify_sampling_features(
        row, script_reference=fictional_script_reference(tmp_path)
    )
    assert observed.standard_line_count == 2
    assert observed.native_line_count == 2
    assert observed.missingness_class == (
        "POSTCODE_MISSING_CITY_MISSING_REGION_MISSING_COUNTRY_MISSING"
    )
    assert observed.challenge_flag
    assert "POSTCODE_MISSING" in observed.challenge_reasons
    assert "MULTIPLE_ADDRESS_LINES" in observed.challenge_reasons


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ABC", "LATIN_ONLY"),
        ("Москва", "NON_LATIN_PRESENT"),
        ("AБ", "MIXED_SCRIPT"),
        ("123 -", "COMMON_OR_UNKNOWN_ONLY"),
        ("", "EMPTY"),
    ],
)
def test_script_classification(tmp_path: Path, value: str, expected: str) -> None:
    row = _raw_row(
        street_address_line_1=value,
        street_address_line_1_native="",
    )
    observed = classify_sampling_features(
        row, script_reference=fictional_script_reference(tmp_path)
    )
    assert observed.standard_script_class == expected


def test_rare_strata_country_weighting_and_source_coverage() -> None:
    candidates = []
    for index in range(120):
        country = "RARE" if index < 2 else ("JP" if index < 40 else "DE")
        script = "NON_LATIN_PRESENT" if country == "JP" else "LATIN_ONLY"
        candidates.append(
            _candidate(
                index,
                source_file=f"source_{index % 6}.csv",
                features=_feature(country=country, script=script),
            )
        )
    selection = _select(candidates, development=35, holdout=15)
    selected = selection.all_candidates
    assert {candidate.source_file for candidate in selected} == {
        f"source_{index}.csv" for index in range(6)
    }
    assert sum(item.features.country_stratum == "RARE" for item in selected) >= 1
    targets = allocate_country_targets(
        {"DE": 1_000, "JP": 1_000},
        {"DE": 0, "JP": 1_000},
        policy=_tiny_policy(),
    )
    assert targets["JP"] >= targets["DE"]


def test_impossible_quota_degrades_deterministically_and_is_reported() -> None:
    candidates = [
        _candidate(
            index,
            source_file=f"source_{index}.csv",
            features=_feature(country=f"C{index}"),
        )
        for index in range(8)
    ]
    selection = _select(candidates, development=2, holdout=1)
    assert len(selection.all_candidates) == 3
    assert any(item.shortfall > 0 for item in selection.quota_diagnostics)
    rerun = _select(list(reversed(candidates)), development=2, holdout=1)
    assert [item.stable_source_row_id_v1 for item in selection.all_candidates] == [
        item.stable_source_row_id_v1 for item in rerun.all_candidates
    ]


def _manual_fingerprint_bytes(
    *,
    scope_version: str,
    population_id: str,
    scope_sha: str,
    parser_sha: str,
    script_id: str,
    sources: list[BenchmarkSourceProjection],
    selection: BenchmarkSelection,
    config: BenchmarkConfig,
) -> bytes:
    payload = bytearray(BENCHMARK_FINGERPRINT_DOMAIN)

    def text(value: str) -> None:
        raw = value.encode("utf-8")
        payload.extend(struct.pack(">Q", len(raw)))
        payload.extend(raw)

    def uint(value: int) -> None:
        payload.extend(struct.pack(">Q", value))

    for value in (
        BENCHMARK_CONTRACT_VERSION,
        FEATURE_CONTRACT_VERSION,
        SELECTION_ALGORITHM_VERSION,
        ALLOCATION_POLICY_VERSION,
        scope_version,
        population_id,
        script_id,
    ):
        text(value)
    payload.extend(bytes.fromhex(scope_sha))
    payload.extend(bytes.fromhex(parser_sha))
    uint(config.development_count)
    uint(config.holdout_count)
    for key, policy_value in config.policy.to_dict().items():
        text(key)
        text(policy_value) if isinstance(policy_value, str) else uint(policy_value)
    ordered_sources = sorted(sources, key=lambda item: item.relative_path)
    uint(len(ordered_sources))
    uint(sum(item.logical_record_count for item in ordered_sources))
    for source in ordered_sources:
        text(source.relative_path)
        uint(source.size_bytes)
        payload.extend(bytes.fromhex(source.sha256))
        uint(source.logical_record_count)
    for split_name, candidates in (
        ("DEVELOPMENT", selection.development),
        ("HOLDOUT", selection.holdout),
    ):
        text(split_name)
        identities = sorted(item.stable_source_row_id_v1 for item in candidates)
        uint(len(identities))
        for identity in identities:
            payload.extend(identity)
    return bytes(payload)


def test_benchmark_fingerprint_independent_golden_and_population_sensitivity() -> None:
    config = BenchmarkConfig(2, 1, _tiny_policy())
    selection = _select(
        [_candidate(index) for index in range(6)], development=2, holdout=1
    )
    sources = [
        BenchmarkSourceProjection("a.csv", 10, "11" * 32, 3),
        BenchmarkSourceProjection("b.csv", 20, "22" * 32, 3),
    ]
    observed = benchmark_fingerprint_v1(
        population_scope_version="stage00_population_scope_v1",
        population_id="fictional-population",
        population_scope_sha256="33" * 32,
        parser_contract_fingerprint="44" * 32,
        unicode_script_reference_id="fictional-script-v1",
        sources=sources,
        selection=selection,
        config=config,
    )
    manual = hashlib.sha256(
        _manual_fingerprint_bytes(
            scope_version="stage00_population_scope_v1",
            population_id="fictional-population",
            scope_sha="33" * 32,
            parser_sha="44" * 32,
            script_id="fictional-script-v1",
            sources=sources,
            selection=selection,
            config=config,
        )
    ).hexdigest()
    assert observed == manual
    assert (
        observed == "40ff47f01431a9dc323622ecdb7836344c308d66f19567a37c13801793622727"
    )
    changed_sources = [
        BenchmarkSourceProjection("a.csv", 10, "11" * 32, 3),
        BenchmarkSourceProjection("b.csv", 20, "22" * 32, 4),
    ]
    assert (
        benchmark_fingerprint_v1(
            population_scope_version="stage00_population_scope_v1",
            population_id="fictional-population",
            population_scope_sha256="33" * 32,
            parser_contract_fingerprint="44" * 32,
            unicode_script_reference_id="fictional-script-v1",
            sources=changed_sources,
            selection=selection,
            config=config,
        )
        != observed
    )


def test_synthetic_materialization_is_exact_private_atomic_and_repeatable(
    tmp_path: Path,
) -> None:
    first = materialize_benchmark_sample(_synthetic_run_config(tmp_path, "first"))
    second = materialize_benchmark_sample(_synthetic_run_config(tmp_path, "second"))
    assert first.benchmark_fingerprint == second.benchmark_fingerprint
    assert first.development_rows == second.development_rows == 12
    assert first.holdout_rows == second.holdout_rows == 6
    validate_materialized_benchmark(first.output_directory)
    development = pq.read_table(
        first.output_directory / DEVELOPMENT_RELATIVE_PATH,
        columns=["id", "postcode", "benchmark_split"],
    )
    holdout = pq.read_table(
        first.output_directory / HOLDOUT_RELATIVE_PATH,
        columns=["benchmark_split"],
    )
    assert development.num_rows == 12
    assert holdout.num_rows == 6
    assert set(development["benchmark_split"].to_pylist()) == {"DEVELOPMENT"}
    assert set(holdout["benchmark_split"].to_pylist()) == {"HOLDOUT"}
    assert "00123" in development["postcode"].to_pylist()
    for root, directories, files in os.walk(first.output_directory):
        assert stat.S_IMODE(Path(root).stat().st_mode) == 0o700
        for directory in directories:
            assert stat.S_IMODE((Path(root) / directory).stat().st_mode) == 0o700
        for file_name in files:
            assert stat.S_IMODE((Path(root) / file_name).stat().st_mode) == 0o600
    summary = (first.output_directory / SUMMARY_JSON_NAME).read_bytes()
    for protected in (
        b"Fictional Road 001",
        b"Example City",
        b"00123",
        b"fictional-provider-id",
        b"stable_source_row_id_v1",
        b"fictional_0.csv",
    ):
        assert protected not in summary


def test_output_collision_tampering_and_partial_output_fail_closed(
    tmp_path: Path,
) -> None:
    config = _synthetic_run_config(tmp_path, "benchmark")
    outcome = materialize_benchmark_sample(config)
    with pytest.raises(BenchmarkValidationError, match="OUTPUT_COLLISION"):
        materialize_benchmark_sample(config)
    manifest = outcome.output_directory / MANIFEST_NAME
    original = manifest.read_bytes()
    manifest.write_bytes(
        original.replace(b"BENCHMARK_SAMPLE_V1_ACCEPTED", b"X" * 28, 1)
    )
    manifest.chmod(0o600)
    with pytest.raises(BenchmarkValidationError, match="TERMINAL_MISMATCH"):
        validate_materialized_benchmark(outcome.output_directory)

    partial = tmp_path / "partial"
    partial.mkdir(mode=0o700)
    (partial / "development").mkdir(mode=0o700)
    (partial / "holdout").mkdir(mode=0o700)
    (partial / "_IN_PROGRESS").write_text("incomplete", encoding="utf-8")
    (partial / "_IN_PROGRESS").chmod(0o600)
    with pytest.raises(BenchmarkValidationError, match="INCOMPLETE"):
        validate_materialized_benchmark(partial)


def test_validator_recomputes_selected_identity_and_scientific_fingerprint(
    tmp_path: Path,
) -> None:
    outcome = materialize_benchmark_sample(_synthetic_run_config(tmp_path, "benchmark"))
    manifest_path = outcome.output_directory / MANIFEST_NAME
    success_path = outcome.output_directory / SUCCESS_MARKER
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = manifest["scientific_identity"]["selected_source_rows"]
    assert isinstance(selected, list)
    selected[0]["source_logical_record_number"] = (
        selected[0]["source_logical_record_number"] % 12
    ) + 1
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path.chmod(0o600)
    success = json.loads(success_path.read_text(encoding="utf-8"))
    success["benchmark_manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    success["benchmark_manifest_size_bytes"] = manifest_path.stat().st_size
    success_path.write_text(
        json.dumps(success, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    success_path.chmod(0o600)
    with pytest.raises(BenchmarkValidationError, match="IDENTITY_MISMATCH"):
        validate_materialized_benchmark(outcome.output_directory)


def test_production_guard_precedes_source_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    config = BenchmarkRunConfig(
        source_root=tmp_path / "absent-source-root",
        population_scope_file=tmp_path / "absent-scope.json",
        expected_population_scope_sha256="11" * 32,
        expected_source_count=1,
        output_directory=tmp_path / "must-not-exist",
        adopting_git_commit="a" * 40,
    )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_benchmark_sample(config)
    assert not config.output_directory.exists()


def test_expected_source_symlink_fails_closed(tmp_path: Path) -> None:
    config = _synthetic_run_config(tmp_path, "benchmark")
    target = config.source_root / "fictional_0.csv"
    replacement = config.source_root / "replacement.csv"
    target.rename(replacement)
    target.symlink_to(replacement.name)
    with pytest.raises(BenchmarkValidationError, match="SOURCE_POPULATION_MISMATCH"):
        materialize_benchmark_sample(config)


def test_cluster_and_transfer_assets_enforce_controlled_execution() -> None:
    sbatch = Path("cluster/goethe_nhr/benchmark_sample_v1.sbatch").read_text(
        encoding="utf-8"
    )
    transfer = Path("scripts/transfer_benchmark_sources_to_goethe_nhr.sh").read_text(
        encoding="utf-8"
    )
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in sbatch
    assert "SLURM_JOB_ID:?SLURM_JOB_ID is required" in sbatch
    assert "BENCHMARK_POPULATION_SCOPE_SHA256" in sbatch
    assert "BENCHMARK_EXPECTED_SOURCE_COUNT" in sbatch
    assert "safe-geocoding-benchmark-sample" in sbatch
    assert "--checksum" in transfer
    assert "--files-from" in transfer
    assert "ServerAliveInterval=30" in transfer
    assert ".TRANSFER_IN_PROGRESS" in transfer
    assert "REMOTE_SOURCE_ALREADY_COMPLETE" in transfer
    assert "SOURCE_SCOPE_MEMBERSHIP_MISMATCH" in transfer
    assert "_TRANSFER_COMPLETE" in transfer
    for forbidden in ("1405", "1411", "2822", "csv_files"):
        assert forbidden not in sbatch
        assert forbidden not in transfer


def test_source_population_change_changes_fingerprint() -> None:
    config = BenchmarkConfig(2, 1, _tiny_policy())
    selection = _select(
        [_candidate(index) for index in range(6)], development=2, holdout=1
    )
    first = benchmark_fingerprint_v1(
        population_scope_version="stage00_population_scope_v1",
        population_id="fictional",
        population_scope_sha256="11" * 32,
        parser_contract_fingerprint=parser_contract_fingerprint_v1(),
        unicode_script_reference_id="fictional-script-v1",
        sources=[BenchmarkSourceProjection("a.csv", 1, "22" * 32, 6)],
        selection=selection,
        config=config,
    )
    second = benchmark_fingerprint_v1(
        population_scope_version="stage00_population_scope_v1",
        population_id="fictional",
        population_scope_sha256="11" * 32,
        parser_contract_fingerprint=parser_contract_fingerprint_v1(),
        unicode_script_reference_id="fictional-script-v1",
        sources=[BenchmarkSourceProjection("a.csv", 1, "33" * 32, 6)],
        selection=selection,
        config=config,
    )
    assert first != second

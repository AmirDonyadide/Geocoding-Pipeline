from __future__ import annotations

import copy
import hashlib
import heapq
import json
import random
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.phase03.models import PilotCandidate
from safe_geocoding_pipeline.phase03.pilot_runner import (
    SAMPLING_COLUMNS,
    ProductionSamplingContract,
    SQLiteCandidateStoreSettings,
    SQLitePilotCandidateStore,
)
from safe_geocoding_pipeline.phase03.pilot_select_benchmark import (
    BENCHMARK_VERSION,
    _first_trace_divergence,
    _persist_selection_mismatch,
    _selection_mismatch_payload,
    _selection_status_mismatch_payload,
    _selection_from_snapshot,
    _sqlite_full_state_digest,
    compare_runs,
)
from safe_geocoding_pipeline.phase03.pilot_selection import (
    BoundedPilotSelection,
    ExactBoundedCandidateReducer,
    PilotSelectionInfeasibleError,
    SelectionTrace,
    bounded_snapshot_state,
)
from safe_geocoding_pipeline.phase03.pilot_selection_runtime import (
    BoundedShardTask,
    reduce_production_shards_bounded,
    write_compact_selected_state,
)
from safe_geocoding_pipeline.phase03.sampler import PilotSamplingConfig, PilotSelection

_BENCHMARK_MATRIX = (
    ("baseline", "baseline-sqlite"),
    ("optimized", "optimized-sqlite"),
    ("optimized_mmap", "optimized-sqlite"),
    ("bounded_1", "bounded-parallel"),
    ("bounded_4", "bounded-parallel"),
    ("bounded_16", "bounded-parallel"),
)


def _portable_trace_stage() -> dict[str, object]:
    return {
        "available": 0,
        "category": None,
        "cumulative_selected_digest": "10" * 32,
        "cumulative_selected_digest_before": "10" * 32,
        "dimension": None,
        "primary_group_count_digest": "20" * 32,
        "primary_group_count_digest_before": "20" * 32,
        "primary_group_counts": [],
        "primary_group_counts_before": [],
        "represented_after": 0,
        "represented_before": 0,
        "selected_count_after": 0,
        "selected_count_before": 0,
        "selected_this_stage_count": 0,
        "selected_this_stage_digest": "30" * 32,
        "stage_index": 0,
        "stage_type": "TARGETED_SAFETY",
        "target": 0,
    }


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-optimized-selection:{index}".encode()).digest()


def _population(size: int) -> list[PilotCandidate]:
    result: list[PilotCandidate] = []
    for index in range(size):
        primary = f"ASSIGNED:F{index % 19:02d}"
        cohort = "RARE" if index < 17 else ("MEDIUM", "LARGE")[index % 2]
        result.append(
            PilotCandidate(
                _identity(index),
                {
                    "primary_country_group": primary,
                    "country_cohort": cohort,
                    "postcode_lexical": f"POSTCODE_{index % 11}",
                    "script_category": f"SCRIPT_{index % 7}",
                    "structured_completeness": f"COMPLETENESS_{index % 4}",
                    "overlap": "EVEN" if index % 2 == 0 else "ODD",
                },
                targeted_safety_case=index in {23, 101},
            )
        )
    return result


def _config() -> PilotSamplingConfig:
    return PilotSamplingConfig(
        development_count=800,
        locked_evaluation_count=400,
        minimum_per_stratum=13,
        maximum_primary_stratum=80,
        primary_stratum="primary_country_group",
    )


def _baseline(
    path: Path,
    population: Iterable[PilotCandidate],
    *,
    config: PilotSamplingConfig,
) -> PilotSelection:
    store = SQLitePilotCandidateStore(path, config=config)
    try:
        store.ingest(population, batch_size=137)
        return store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
        )
    finally:
        store.close()


def _sqlite_selection(
    path: Path,
    population: Iterable[PilotCandidate],
    *,
    config: PilotSamplingConfig,
    settings: SQLiteCandidateStoreSettings,
) -> tuple[PilotSelection, dict[str, int | str]]:
    store = SQLitePilotCandidateStore(path, config=config, settings=settings)
    try:
        store.ingest(population)
        selection = store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
        )
        return selection, store.sqlite_runtime_settings()
    finally:
        store.close()


def _bounded(
    partitions: Iterable[Iterable[PilotCandidate]],
    *,
    config: PilotSamplingConfig,
    merge_reverse: bool = False,
) -> PilotSelection:
    snapshots = []
    for partition in partitions:
        reducer = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
        for candidate in partition:
            reducer.accept(candidate)
        snapshots.append(reducer.snapshot)
    if merge_reverse:
        snapshots.reverse()
    merged = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for snapshot in snapshots:
        merged.merge(snapshot)
    return merged.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint=config.fingerprint(),
    ).selection


def test_bounded_selection_matches_reference_and_is_shard_order_invariant(
    tmp_path: Path,
) -> None:
    population = _population(2_000)
    reference = _baseline(tmp_path / "reference.sqlite3", population, config=_config())
    partitions = [population[index::5] for index in range(5)]
    bounded = _bounded(partitions, config=_config())
    reversed_merge = _bounded(
        [list(reversed(partition)) for partition in reversed(partitions)],
        config=_config(),
        merge_reverse=True,
    )
    assert bounded.development_ids == reference.development_ids
    assert bounded.locked_evaluation_ids == reference.locked_evaluation_ids
    assert reversed_merge.development_ids == reference.development_ids
    assert reversed_merge.locked_evaluation_ids == reference.locked_evaluation_ids
    assert bounded.seal.development_identity_digest == (
        reference.seal.development_identity_digest
    )
    assert bounded.seal.locked_evaluation_identity_digest == (
        reference.seal.locked_evaluation_identity_digest
    )
    assert (
        reference.seal.development_identity_digest
        == "eebe16c294d0a59f08413777a2a033594bc8df4d2f2907eff192e8ba4ac48b25"
    )
    assert (
        reference.seal.locked_evaluation_identity_digest
        == "1f141116964d4c1b6442a71a1afc87386f883fcd75a4e764c81431e2c099713d"
    )


def test_optimized_sqlite_settings_and_selection_match_reference(
    tmp_path: Path,
) -> None:
    population = _population(2_000)
    baseline, baseline_runtime = _sqlite_selection(
        tmp_path / "baseline.sqlite3",
        population,
        config=_config(),
        settings=SQLiteCandidateStoreSettings.baseline(),
    )
    optimized_settings = SQLiteCandidateStoreSettings.optimized(
        cache_size_mib=64,
        mmap_size_mib=16,
        insertion_batch_size=257,
    )
    optimized, optimized_runtime = _sqlite_selection(
        tmp_path / "optimized.sqlite3",
        reversed(population),
        config=_config(),
        settings=optimized_settings,
    )
    assert optimized.development_ids == baseline.development_ids
    assert optimized.locked_evaluation_ids == baseline.locked_evaluation_ids
    assert optimized.seal == baseline.seal
    assert baseline_runtime["journal_mode"] == "DELETE"
    assert baseline_runtime["synchronous"] == 2
    assert baseline_runtime["temp_store"] == 1
    assert optimized_runtime == {
        "journal_mode": "OFF",
        "synchronous": 0,
        "temp_store": 2,
        "cache_size": -(64 * 1_024),
        "mmap_size": 16 * 1_024**2,
    }


def test_sqlite_backend_identity_is_operational_not_scientific(
    tmp_path: Path,
) -> None:
    population = _population(2_000)
    baseline, _ = _sqlite_selection(
        tmp_path / "baseline.sqlite3",
        population,
        config=_config(),
        settings=SQLiteCandidateStoreSettings.baseline(),
    )
    optimized, _ = _sqlite_selection(
        tmp_path / "optimized.sqlite3",
        population,
        config=_config(),
        settings=SQLiteCandidateStoreSettings.optimized(cache_size_mib=8),
    )
    assert (
        SQLiteCandidateStoreSettings.baseline().fingerprint()
        != SQLiteCandidateStoreSettings.optimized(cache_size_mib=8).fingerprint()
    )
    assert baseline.seal.sampling_config_fingerprint == (
        optimized.seal.sampling_config_fingerprint
    )


def test_disposable_optimized_sqlite_state_reconstructs_exactly(
    tmp_path: Path,
) -> None:
    population = _population(2_000)
    interrupted_path = tmp_path / "interrupted.sqlite3"
    settings = SQLiteCandidateStoreSettings.optimized(cache_size_mib=8)
    interrupted = SQLitePilotCandidateStore(
        interrupted_path, config=_config(), settings=settings
    )
    interrupted.ingest(population[:777])
    interrupted.close()
    with pytest.raises(ValueError, match="disposable and must be rebuilt"):
        SQLitePilotCandidateStore(
            interrupted_path, config=_config(), settings=settings
        )
    interrupted_path.unlink()
    reconstructed, _ = _sqlite_selection(
        interrupted_path,
        population,
        config=_config(),
        settings=settings,
    )
    clean, _ = _sqlite_selection(
        tmp_path / "clean.sqlite3",
        population,
        config=_config(),
        settings=settings,
    )
    assert reconstructed == clean


@pytest.mark.parametrize("partition_count", [1, 4, 16, 40])
def test_bounded_selection_is_worker_count_invariant(partition_count: int) -> None:
    population = _population(2_000)
    partitions = [population[index::partition_count] for index in range(partition_count)]
    observed = _bounded(partitions, config=_config())
    expected = _bounded([population], config=_config())
    assert observed.development_ids == expected.development_ids
    assert observed.locked_evaluation_ids == expected.locked_evaluation_ids


def test_bounded_selection_rejects_cross_partition_duplicate_ids() -> None:
    population = _population(2_000)
    duplicated = PilotCandidate(
        population[0].stable_source_row_id_v1,
        dict(population[0].strata),
    )
    first = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=True)
    second = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=True)
    first.accept(population[0])
    second.accept(duplicated)
    with pytest.raises(ValueError, match="duplicate stable IDs"):
        first.merge(second.snapshot)


def test_bounded_selection_reconstruction_after_interruption_is_exact() -> None:
    population = _population(2_000)
    interrupted = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=True)
    for candidate in population[:777]:
        interrupted.accept(candidate)
    reconstructed = _bounded([population], config=_config())
    second_reconstruction = _bounded(
        [population[:777], population[777:]], config=_config()
    )
    assert reconstructed == second_reconstruction


def test_bounded_selection_preserves_stable_id_tie_breaking(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def constant_score(_domain: bytes, _identity_value: bytes) -> bytes:
        return b"\x11" * 32

    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.pilot_runner._score", constant_score
    )
    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.pilot_selection._score", constant_score
    )
    population = _population(2_000)
    reference = _baseline(tmp_path / "tie.sqlite3", population, config=_config())
    bounded = _bounded([population[::2], population[1::2]], config=_config())
    assert bounded.development_ids == reference.development_ids
    assert bounded.locked_evaluation_ids == reference.locked_evaluation_ids


def test_bounded_state_retains_all_rare_rows_and_caps_other_state() -> None:
    population = _population(2_000)
    reducer = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=True)
    for candidate in population:
        reducer.accept(candidate)
    rare_ids = {
        candidate.stable_source_row_id_v1
        for candidate in population
        if candidate.strata["country_cohort"] == "RARE"
    }
    assert rare_ids.issubset(reducer.snapshot.mandatory)
    assert all(
        len(heap) <= _config().maximum_primary_stratum
        for heap in reducer.snapshot.quota_heaps.values()
    )
    assert all(
        len(heap) <= _config().maximum_primary_stratum
        for heap in reducer.snapshot.fill_heaps.values()
    )


def _overlapping_quota_regression_population() -> list[PilotCandidate]:
    rows = (
        (3010, "P1", "MEDIUM", "C0", "C0", "C1"),
        (3011, "P2", "LARGE", "C2", "C2", "C0"),
        (3013, "P2", "MEDIUM", "C0", "C0", "C2"),
        (3014, "P0", "MEDIUM", "C1", "C1", "C1"),
        (3015, "P2", "MEDIUM", "C2", "C2", "C0"),
        (3018, "P2", "MEDIUM", "C2", "C2", "C1"),
        (3023, "P0", "MEDIUM", "C2", "C0", "C0"),
        (3024, "P3", "MEDIUM", "C1", "C1", "C2"),
        (3025, "P1", "LARGE", "C1", "C2", "C0"),
    )
    return [
        PilotCandidate(
            index.to_bytes(32, "big"),
            {
                "primary_country_group": primary,
                "country_cohort": cohort,
                "d0": d0,
                "d1": d1,
                "d2": d2,
            },
        )
        for index, primary, cohort, d0, d1, d2 in rows
    ]


def _merge_bound_occupancy_regression_population() -> list[PilotCandidate]:
    """Nine fictional rows that exposed v3 merge-time quota truncation."""

    rows = (
        (1000, "P0", "MEDIUM", {"d0": "C1", "d1": "C1", "d3": "C2"}),
        (
            1001,
            "P0",
            "LARGE",
            {"d0": "C0", "d1": "C2", "d3": "C0", "d4": "C1"},
        ),
        (1002, "P4", "LARGE", {"d2": "C2", "d4": "C1"}),
        (1003, "P4", "MEDIUM", {"d0": "C1", "d2": "C0", "d3": "C0"}),
        (1004, "P1", "MEDIUM", {"d1": "C1", "d2": "C0", "d3": "C1"}),
        (1005, "P2", "MEDIUM", {"d1": "C1", "d4": "C2"}),
        (
            1006,
            "P4",
            "MEDIUM",
            {"d0": "C0", "d2": "C2", "d3": "C1", "d4": "C0"},
        ),
        (
            1007,
            "P4",
            "LARGE",
            {"d1": "C1", "d2": "C2", "d3": "C0"},
        ),
        (
            1008,
            "P2",
            "LARGE",
            {"d0": "C1", "d2": "C2", "d3": "C1", "d4": "C1"},
        ),
    )
    return [
        PilotCandidate(
            index.to_bytes(32, "big"),
            {
                "primary_country_group": primary,
                "country_cohort": cohort,
                **strata,
            },
        )
        for index, primary, cohort, strata in rows
    ]


def test_merge_preserves_primary_cap_frontier_and_exact_replay_state(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=2,
        maximum_primary_stratum=3,
        primary_stratum="primary_country_group",
    )
    population = _merge_bound_occupancy_regression_population()
    reference_trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(population)
        reference = store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            trace=reference_trace,
        )
        effective_fingerprint = store.effective_sampling_fingerprint
    finally:
        store.close()

    worker = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        worker.accept(candidate)
    merged = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    merged.merge(worker.snapshot)
    assert max(len(heap) for heap in merged.snapshot.quota_heaps.values()) == 3

    bounded_trace = SelectionTrace()
    bounded = merged.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint=effective_fingerprint,
        trace=bounded_trace,
    ).selection
    assert bounded == reference
    assert _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=False
    ) is None
    # Fixed-size frontier retention is scientifically exact but intentionally
    # does not preserve every rejected fill-cursor row after a primary reaches
    # its cap.  That observability boundary is reported separately.
    cursor_difference = _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=True
    )
    assert cursor_difference is not None
    assert cursor_difference[1] is not None
    assert cursor_difference[1].stage_type == "DETERMINISTIC_FILL"

    regression_stage = reference_trace.stages[9]
    assert (
        regression_stage.stage_type,
        regression_stage.dimension,
        regression_stage.category,
    ) == ("SECONDARY_QUOTA", "d2", "C2")
    assert regression_stage.represented_before == 2
    assert regression_stage.candidates_cap_blocked == 1
    assert regression_stage.selected_count_after == 7
    assert regression_stage.primary_group_counts == (
        ("P0", 2),
        ("P1", 1),
        ("P2", 1),
        ("P4", 3),
    )
    assert regression_stage.cumulative_selected_digest == (
        "70b5471bff87ce3e33d96f46af6fa488e3e01fc831fc3005b3090dfab408cf39"
    )
    # v3 incorrectly re-truncated merged quota heaps to 2 rows.  At this
    # stage it selected fictional identity 1008, recorded zero cap blocks,
    # and produced this different cumulative-state digest:
    assert regression_stage.cumulative_selected_digest != (
        "403ebd6273875d3343f50c21dd8436b38f3729cebca400ee8336f6b184e9c360"
    )

    # Preserve a diagnostic reproduction of v3 without reintroducing that
    # implementation: emulate only its merge-time C -> minimum truncation.
    v3_snapshot = copy.deepcopy(worker.snapshot)
    for heap in v3_snapshot.quota_heaps.values():
        retained = sorted(heap, key=lambda entry: (-entry[0], entry[1]))[
            : config.minimum_per_stratum
        ]
        heap[:] = retained
        heapq.heapify(heap)
    v3_replay = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    v3_replay.snapshot = v3_snapshot
    v3_trace = SelectionTrace()
    v3_selection = v3_replay.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint=effective_fingerprint,
        trace=v3_trace,
    ).selection
    v3_divergence = _first_trace_divergence(
        reference_trace, v3_trace, include_cursor_diagnostics=False
    )
    assert v3_divergence is not None
    assert v3_divergence[0] == 9
    assert v3_divergence[1] is not None and v3_divergence[2] is not None
    assert (
        v3_divergence[1].stage_type,
        v3_divergence[1].dimension,
        v3_divergence[1].category,
    ) == ("SECONDARY_QUOTA", "d2", "C2")
    assert v3_divergence[1].represented_before == v3_divergence[2].represented_before == 2
    assert v3_divergence[1].candidates_cap_blocked == 1
    assert v3_divergence[2].candidates_cap_blocked == 0
    assert v3_divergence[1].selected_count_after == 7
    assert v3_divergence[2].selected_count_after == 8
    assert v3_divergence[2].cumulative_selected_digest == (
        "403ebd6273875d3343f50c21dd8436b38f3729cebca400ee8336f6b184e9c360"
    )
    payload = _selection_mismatch_payload(
        subset_identity="aa" * 32,
        files=[{"output_file": "fictional.parquet", "output_sha256": "bb" * 32}],
        row_count=len(population),
        reference=reference,
        bounded=v3_selection,
        reference_trace=reference_trace,
        bounded_trace=v3_trace,
    )
    persisted_divergence = payload["first_scientific_state_divergence"]
    assert isinstance(persisted_divergence, dict)
    assert persisted_divergence["first_differing_stage_index"] == 9
    assert persisted_divergence["pre_stage_primary_occupancy_differences"] == []
    assert len(persisted_divergence["post_stage_primary_occupancy_differences"]) == 1
    serialized = json.dumps(payload, sort_keys=True)
    assert all(f'"P{index}"' not in serialized for index in range(5))
    assert all(identity.to_bytes(32, "big").hex() not in serialized for identity in range(1000, 1009))


def test_overlapping_quota_regression_matches_frozen_reference(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=2,
        maximum_primary_stratum=5,
        primary_stratum="primary_country_group",
    )
    population = _overlapping_quota_regression_population()
    reference_trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(population)
        reference = store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            trace=reference_trace,
        )
        effective_fingerprint = store.effective_sampling_fingerprint
    finally:
        store.close()

    worker = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        worker.accept(candidate)
    reducer = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    reducer.merge(worker.snapshot)
    bounded_trace = SelectionTrace()
    bounded = reducer.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint=effective_fingerprint,
        trace=bounded_trace,
    ).selection

    assert reference == bounded
    assert tuple(
        int.from_bytes(identity, "big")
        for identity in reference.development_ids + reference.locked_evaluation_ids
    ) == (3011, 3010, 3024, 3015, 3014, 3013, 3025, 3018)
    assert reference.seal.development_identity_digest == (
        "dd78d76439d48b995b4f20f983f3f3e7cb08878a24dbbf8214ab7cdf0ec8034f"
    )
    assert reference.seal.locked_evaluation_identity_digest == (
        "08b1dc06a736e6ddc18b8da8ad78b8f563dcb5f6b96c21ccc4b5feb55c7fcfd2"
    )
    reference_stage = next(
        stage
        for stage in reference_trace.stages
        if (stage.dimension, stage.category) == ("d0", "C2")
    )
    bounded_stage = next(
        stage
        for stage in bounded_trace.stages
        if (stage.dimension, stage.category) == ("d0", "C2")
    )
    assert reference_stage.represented_before == reference_stage.target == 2
    assert tuple(
        int.from_bytes(event[0], "big") for event in reference_stage.selected_events
    ) == (3018,)
    assert bounded_stage.selected_events == reference_stage.selected_events
    assert bounded_stage.cumulative_selected_digest == (
        reference_stage.cumulative_selected_digest
    )


def test_mismatch_artifact_is_atomic_protected_and_privacy_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=2,
        maximum_primary_stratum=5,
        primary_stratum="primary_country_group",
    )
    population = _overlapping_quota_regression_population()
    reference_trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(population)
        reference = store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            trace=reference_trace,
        )
    finally:
        store.close()
    bounded_trace = SelectionTrace(
        stages=[replace(stage) for stage in reference_trace.stages]
    )
    replacement = (9999).to_bytes(32, "big")
    bounded = PilotSelection(
        reference.development_ids[:-1] + (replacement,),
        reference.locked_evaluation_ids,
        reference.seal,
    )
    payload = _selection_mismatch_payload(
        subset_identity="aa" * 32,
        files=[{"output_file": "fictional.parquet", "output_sha256": "bb" * 32}],
        row_count=9,
        reference=reference,
        bounded=bounded,
        reference_trace=reference_trace,
        bounded_trace=bounded_trace,
    )
    assert payload["mismatch_kind"] == "SCIENTIFIC_IDENTITY_OR_ASSIGNMENT"
    assert payload["metadata_equal"] is True
    assert payload["only_reference_count"] == payload["only_bounded_count"] == 1
    serialized = json.dumps(payload, sort_keys=True)
    assert reference.development_ids[-1].hex() not in serialized
    assert replacement.hex() not in serialized

    protected = tmp_path / "protected"
    monkeypatch.setenv("PHASE03_BENCHMARK_MISMATCH_DIRECTORY", str(protected))
    local, persistent = _persist_selection_mismatch(
        tmp_path / "run", run_label="baseline", payload=payload
    )
    assert local.is_file()
    assert persistent is not None and persistent.is_file()
    assert local.stat().st_mode & 0o777 == 0o600
    assert persistent.stat().st_mode & 0o777 == 0o600
    assert protected.stat().st_mode & 0o777 == 0o700
    assert not list(protected.glob("*.tmp"))


def test_mismatch_artifact_distinguishes_metadata_only_difference(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=2,
        maximum_primary_stratum=5,
        primary_stratum="primary_country_group",
    )
    trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(_overlapping_quota_regression_population())
        reference = store.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            trace=trace,
        )
    finally:
        store.close()
    metadata_only = PilotSelection(
        reference.development_ids,
        reference.locked_evaluation_ids,
        replace(reference.seal, selection_timestamp="2026-01-02T00:00:00Z"),
    )
    payload = _selection_mismatch_payload(
        subset_identity="aa" * 32,
        files=[{"output_file": "fictional.parquet", "output_sha256": "bb" * 32}],
        row_count=9,
        reference=reference,
        bounded=metadata_only,
        reference_trace=trace,
        bounded_trace=SelectionTrace(stages=[replace(stage) for stage in trace.stages]),
    )
    assert payload["identity_result_equal"] is True
    assert payload["metadata_equal"] is False
    assert payload["mismatch_kind"] == "METADATA_ONLY"


def _quota_infeasible_population() -> tuple[PilotSamplingConfig, list[PilotCandidate]]:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=3,
        maximum_primary_stratum=4,
        primary_stratum="primary_country_group",
    )
    population = [
        PilotCandidate(
            _identity(index),
            {
                "primary_country_group": "P1",
                "country_cohort": "RARE",
                "quota_case": "OTHER",
            },
        )
        for index in range(4)
    ]
    population.extend(
        PilotCandidate(
            _identity(100 + index),
            {
                "primary_country_group": "P1",
                "country_cohort": "LARGE",
                "quota_case": "TARGET",
            },
        )
        for index in range(3)
    )
    population.extend(
        PilotCandidate(
            _identity(200 + index),
            {
                "primary_country_group": "P2",
                "country_cohort": "MEDIUM",
                "quota_case": "OTHER",
            },
        )
        for index in range(10)
    )
    return config, population


def test_small_subset_can_legitimately_be_quota_infeasible_without_relaxation(
    tmp_path: Path,
) -> None:
    config, population = _quota_infeasible_population()
    reference_trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(population)
        with pytest.raises(PilotSelectionInfeasibleError) as reference_raised:
            store.select(
                input_phase02_manifest_identity="fictional-manifest",
                selection_timestamp="2026-01-01T00:00:00Z",
                trace=reference_trace,
            )
    finally:
        store.close()

    reducer = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        reducer.accept(candidate)
    bounded_trace = SelectionTrace()
    with pytest.raises(PilotSelectionInfeasibleError) as raised:
        reducer.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            effective_sampling_fingerprint="aa" * 32,
            trace=bounded_trace,
        )
    assert raised.value.privacy_safe_diagnostic() == {
        "available": 3,
        "candidates_considered": 3,
        "category": "LARGE",
        "cap_blocked_candidates": 3,
        "dimension": "country_cohort",
        "primary_cap": 4,
        "reason_code": "MINIMUM_STRATUM_QUOTA",
        "represented": 0,
        "target": 3,
    }
    assert reference_raised.value.privacy_safe_diagnostic() == (
        raised.value.privacy_safe_diagnostic()
    )
    assert _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=True
    ) is None

    bounded, status, diagnostic = _selection_from_snapshot(
        reducer.snapshot,
        pilot_config=config,
        subset_identity="fictional-manifest",
        effective_fingerprint="aa" * 32,
    )
    assert bounded is None
    assert status == "NOT_APPLICABLE_SUBSET_INFEASIBLE"
    assert diagnostic == raised.value.privacy_safe_diagnostic()


def test_infeasible_frontier_reports_exact_counts_beyond_retained_bound(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=3,
        maximum_primary_stratum=3,
        primary_stratum="primary_country_group",
    )
    population = [
        PilotCandidate(
            _identity(index),
            {
                "primary_country_group": "P1",
                "country_cohort": "RARE",
                "quota_case": "OTHER",
            },
        )
        for index in range(3)
    ]
    population.extend(
        PilotCandidate(
            _identity(100 + index),
            {
                "primary_country_group": "P1",
                "country_cohort": "LARGE",
                "quota_case": "TARGET",
            },
        )
        for index in range(7)
    )
    population.extend(
        PilotCandidate(
            _identity(200 + index),
            {
                "primary_country_group": "P2",
                "country_cohort": "MEDIUM",
                "quota_case": "OTHER",
            },
        )
        for index in range(8)
    )

    reference_trace = SelectionTrace()
    store = SQLitePilotCandidateStore(tmp_path / "reference.sqlite3", config=config)
    try:
        store.ingest(population)
        with pytest.raises(PilotSelectionInfeasibleError) as reference_raised:
            store.select(
                input_phase02_manifest_identity="fictional-manifest",
                selection_timestamp="2026-01-01T00:00:00Z",
                trace=reference_trace,
            )
    finally:
        store.close()

    worker = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        worker.accept(candidate)
    bounded = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    bounded.merge(worker.snapshot)
    bounded_trace = SelectionTrace()
    with pytest.raises(PilotSelectionInfeasibleError) as bounded_raised:
        bounded.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            effective_sampling_fingerprint="aa" * 32,
            trace=bounded_trace,
        )
    expected = reference_raised.value.privacy_safe_diagnostic()
    assert bounded_raised.value.privacy_safe_diagnostic() == expected
    assert expected["candidates_considered"] == 7
    assert expected["cap_blocked_candidates"] == 7
    reference_stage = reference_trace.stages[-1]
    bounded_stage = bounded_trace.stages[-1]
    assert bounded_stage.candidates_considered == reference_stage.candidates_considered == 7
    assert bounded_stage.candidates_cap_blocked == reference_stage.candidates_cap_blocked == 7
    assert reference_stage.cap_blocked_digest_complete is True
    assert bounded_stage.cap_blocked_digest_complete is False
    assert bounded_stage.frontier_digest_complete is False
    assert _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=False
    ) is None


def test_infeasible_status_artifact_reports_first_scientific_state_divergence() -> None:
    config, population = _quota_infeasible_population()
    reference = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        reference.accept(candidate)
    reference_trace = SelectionTrace()
    with pytest.raises(PilotSelectionInfeasibleError) as raised:
        reference.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            effective_sampling_fingerprint="aa" * 32,
            trace=reference_trace,
        )
    final_stage = reference_trace.stages[-1]
    bounded_trace = SelectionTrace(
        stages=[
            *reference_trace.stages[:-1],
            replace(
                final_stage,
                selected_count_after=final_stage.selected_count_after + 1,
            ),
        ]
    )
    diagnostic = raised.value.privacy_safe_diagnostic()
    payload = _selection_status_mismatch_payload(
        subset_identity="aa" * 32,
        files=[{"output_file": "fictional.parquet", "output_sha256": "bb" * 32}],
        row_count=len(population),
        reference_status="NOT_APPLICABLE_SUBSET_INFEASIBLE",
        bounded_status="NOT_APPLICABLE_SUBSET_INFEASIBLE",
        reference_infeasibility=diagnostic,
        bounded_infeasibility=diagnostic,
        reference_trace=reference_trace,
        bounded_trace=bounded_trace,
    )
    assert payload["mismatch_kind"] == "SCIENTIFIC_TRACE_STATE"
    divergence = payload["first_scientific_state_divergence"]
    assert isinstance(divergence, dict)
    assert divergence["first_differing_stage_index"] == final_stage.stage_index
    assert divergence["differing_fields"] == ["selected_count_after"]


def test_trace_mismatch_artifact_redacts_country_group_category() -> None:
    config, population = _quota_infeasible_population()
    reducer = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
    for candidate in population:
        reducer.accept(candidate)
    trace = SelectionTrace()
    with pytest.raises(PilotSelectionInfeasibleError) as raised:
        reducer.select(
            input_phase02_manifest_identity="fictional-manifest",
            selection_timestamp="2026-01-01T00:00:00Z",
            effective_sampling_fingerprint="aa" * 32,
            trace=trace,
        )
    stage = replace(
        trace.stages[-1], dimension="country_group", category="ASSIGNED:FICTIONAL"
    )
    reference_trace = SelectionTrace(stages=[*trace.stages[:-1], stage])
    bounded_trace = SelectionTrace(
        stages=[
            *trace.stages[:-1],
            replace(stage, selected_count_after=stage.selected_count_after + 1),
        ]
    )
    diagnostic = raised.value.privacy_safe_diagnostic()
    payload = _selection_status_mismatch_payload(
        subset_identity="aa" * 32,
        files=[{"output_file": "fictional.parquet", "output_sha256": "bb" * 32}],
        row_count=len(population),
        reference_status="NOT_APPLICABLE_SUBSET_INFEASIBLE",
        bounded_status="NOT_APPLICABLE_SUBSET_INFEASIBLE",
        reference_infeasibility=diagnostic,
        bounded_infeasibility=diagnostic,
        reference_trace=reference_trace,
        bounded_trace=bounded_trace,
    )
    serialized = json.dumps(payload, sort_keys=True)
    assert "ASSIGNED:FICTIONAL" not in serialized
    assert "COUNTRY_GROUP_SHA256:" in serialized


def test_randomized_reference_and_merged_bounded_replay_are_exact(
    tmp_path: Path,
) -> None:
    """Exercise overlapping strata, caps, feasibility, and merge order."""

    config = PilotSamplingConfig(
        development_count=4,
        locked_evaluation_count=4,
        minimum_per_stratum=2,
        maximum_primary_stratum=4,
        primary_stratum="primary_country_group",
    )
    for seed in range(64):
        randomizer = random.Random(seed)
        size = randomizer.randint(8, 16)
        population = []
        primary_population = Counter[str]()
        for index in range(size):
            eligible_primaries = [
                primary
                for primary in ("P0", "P1", "P2", "P3")
                if primary_population[primary] < config.maximum_primary_stratum
            ]
            primary = randomizer.choice(eligible_primaries)
            primary_population[primary] += 1
            strata = {
                "primary_country_group": primary,
                "country_cohort": randomizer.choice(("MEDIUM", "LARGE")),
            }
            for dimension in ("d0", "d1", "d2", "d3"):
                if randomizer.random() < 0.8:
                    strata[dimension] = randomizer.choice(("C0", "C1", "C2"))
            population.append(
                PilotCandidate((10_000 + index).to_bytes(32, "big"), strata)
            )

        reference_trace = SelectionTrace()
        store = SQLitePilotCandidateStore(
            tmp_path / f"random-reference-{seed}.sqlite3", config=config
        )
        try:
            store.ingest(population)
            try:
                reference_selection = store.select(
                    input_phase02_manifest_identity="fictional-manifest",
                    selection_timestamp="2026-01-01T00:00:00Z",
                    trace=reference_trace,
                )
                reference_error = None
            except PilotSelectionInfeasibleError as error:
                reference_selection = None
                reference_error = error
            effective_fingerprint = store.effective_sampling_fingerprint
        finally:
            store.close()

        partition_count = (1, 4, 16)[seed % 3]
        workers = []
        for partition in (
            population[offset::partition_count] for offset in range(partition_count)
        ):
            worker = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
            for candidate in partition:
                worker.accept(candidate)
            workers.append(worker)
        if seed % 2:
            workers.reverse()
        merged = ExactBoundedCandidateReducer(config, track_all_seen_ids=True)
        for worker in workers:
            merged.merge(worker.snapshot)
        bounded_trace = SelectionTrace()
        try:
            bounded_selection = merged.select(
                input_phase02_manifest_identity="fictional-manifest",
                selection_timestamp="2026-01-01T00:00:00Z",
                effective_sampling_fingerprint=effective_fingerprint,
                trace=bounded_trace,
            ).selection
            bounded_error = None
        except PilotSelectionInfeasibleError as error:
            bounded_selection = None
            bounded_error = error

        assert _first_trace_divergence(
            reference_trace, bounded_trace, include_cursor_diagnostics=False
        ) is None
        if reference_error is None:
            assert bounded_error is None
            assert bounded_selection == reference_selection
        else:
            assert bounded_selection is None
            assert bounded_error is not None
            assert bounded_error.privacy_safe_diagnostic() == (
                reference_error.privacy_safe_diagnostic()
            )


def test_canonical_selector_state_is_shard_and_completion_order_invariant() -> None:
    population = _population(2_000)
    reducers = []
    for partition in (population[::3], population[1::3], population[2::3]):
        reducer = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=False)
        for candidate in partition:
            reducer.accept(candidate)
        reducers.append(reducer)
    forward = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=False)
    reverse = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=False)
    for reducer in reducers:
        forward.merge(reducer.snapshot)
    for reducer in reversed(reducers):
        reverse.merge(reducer.snapshot)
    assert bounded_snapshot_state(forward.snapshot) == bounded_snapshot_state(
        reverse.snapshot
    )


def test_sqlite_full_state_digest_is_backend_invariant(tmp_path: Path) -> None:
    population = _population(2_000)
    hashes = []
    for name, settings in (
        ("baseline", SQLiteCandidateStoreSettings.baseline()),
        ("optimized", SQLiteCandidateStoreSettings.optimized(cache_size_mib=8)),
    ):
        store = SQLitePilotCandidateStore(
            tmp_path / f"{name}.sqlite3", config=_config(), settings=settings
        )
        try:
            store.ingest_shard("fictional.parquet", "11" * 32, population)
            hashes.append(_sqlite_full_state_digest(store.connection))
        finally:
            store.close()
    assert hashes[0] == hashes[1]


def test_reference_and_bounded_engines_produce_exact_8000_4000_split(
    tmp_path: Path,
) -> None:
    config = PilotSamplingConfig(
        development_count=8_000,
        locked_evaluation_count=4_000,
        minimum_per_stratum=50,
        maximum_primary_stratum=500,
        primary_stratum="primary_country_group",
    )
    population = [
        PilotCandidate(
            _identity(index),
            {
                "primary_country_group": f"ASSIGNED:F{index % 24:02d}",
                "country_cohort": "LARGE",
                "postcode_lexical": f"POSTCODE_{index % 9}",
                "script_category": f"SCRIPT_{index % 5}",
            },
        )
        for index in range(14_400)
    ]
    reference = _baseline(tmp_path / "reference-12k.sqlite3", population, config=config)
    bounded = _bounded(
        [population[index::7] for index in range(7)], config=config
    )
    assert len(reference.development_ids) == len(bounded.development_ids) == 8_000
    assert (
        len(reference.locked_evaluation_ids)
        == len(bounded.locked_evaluation_ids)
        == 4_000
    )
    assert bounded.development_ids == reference.development_ids
    assert bounded.locked_evaluation_ids == reference.locked_evaluation_ids


def test_compact_selected_state_is_durable_complete_and_review_compatible(
    tmp_path: Path,
) -> None:
    population = _population(2_000)
    reducer = ExactBoundedCandidateReducer(_config(), track_all_seen_ids=True)
    for candidate in population:
        reducer.accept(candidate)
    bounded: BoundedPilotSelection = reducer.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint="aa" * 32,
    )
    output = tmp_path / "controlled" / "candidate_state.sqlite3"
    write_compact_selected_state(
        output,
        bounded_selection=bounded,
        checkpoints=(("fictional.parquet", "bb" * 32, 2_000),),
        config=_config(),
        classification_contract=ProductionSamplingContract(),
        production_binding_fingerprint="cc" * 32,
    )
    assert output.stat().st_mode & 0o777 == 0o600
    connection = sqlite3.connect(f"file:{output}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("SELECT COUNT(*) FROM candidate").fetchone() == (
            _config().total_count,
        )
        assert connection.execute("SELECT COUNT(*) FROM selected").fetchone() == (
            _config().total_count,
        )
        assert connection.execute("SELECT COUNT(*) FROM membership").fetchone()[0] > (
            _config().total_count
        )
        assert connection.execute(
            "SELECT value FROM run_metadata WHERE key='candidate_population_scope'"
        ).fetchone() == ("SELECTED_ONLY",)
    finally:
        connection.close()


def test_parallel_parquet_reduction_is_worker_invariant(tmp_path: Path) -> None:
    countries = ("US", "DE", "FR", "JP")
    tasks: list[BoundedShardTask] = []
    sampling_schema = pa.schema(
        [
            pa.field(
                name,
                pa.binary(32)
                if name == "stable_source_row_id_v1"
                else pa.uint64()
                if name == "source_logical_record_number"
                else pa.string(),
                nullable=False,
            )
            for name in SAMPLING_COLUMNS
        ]
    )
    for shard_index in range(4):
        rows = []
        for row_index in range(200):
            absolute_index = shard_index * 200 + row_index
            row: dict[str, object] = {name: "" for name in SAMPLING_COLUMNS}
            row.update(
                {
                    "stable_source_row_id_v1": _identity(absolute_index),
                    "source_file": f"fictional_{shard_index}.csv",
                    "source_logical_record_number": row_index + 1,
                    "street_address_line_1": f"Fictional Road {absolute_index}",
                    "postcode": f"0{absolute_index:04d}",
                    "city": "Fiction City",
                    "country_iso_code": countries[absolute_index % len(countries)],
                    "location_information": "no_geocoding_information",
                }
            )
            rows.append(row)
        path = tmp_path / f"fictional_{shard_index}.parquet"
        pq.write_table(
            pa.Table.from_pylist(rows, schema=sampling_schema),
            path,
            write_page_checksum=True,
            write_statistics=False,
        )
        tasks.append(BoundedShardTask(path, hashlib.sha256(path.read_bytes()).hexdigest()))

    config = PilotSamplingConfig(
        development_count=80,
        locked_evaluation_count=40,
        minimum_per_stratum=5,
        maximum_primary_stratum=40,
        primary_stratum="primary_country_group",
    )
    contract = ProductionSamplingContract()
    counts = Counter({f"ASSIGNED:{country}": 200 for country in countries})
    one_worker = reduce_production_shards_bounded(
        tasks,
        country_counts=counts,
        safety_locations=frozenset(),
        contract=contract,
        pilot_config=config,
        worker_count=1,
        batch_rows=73,
    ).reducer.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint="aa" * 32,
    )
    two_workers = reduce_production_shards_bounded(
        list(reversed(tasks)),
        country_counts=counts,
        safety_locations=frozenset(),
        contract=contract,
        pilot_config=config,
        worker_count=2,
        batch_rows=73,
    ).reducer.select(
        input_phase02_manifest_identity="fictional-manifest",
        selection_timestamp="2026-01-01T00:00:00Z",
        effective_sampling_fingerprint="aa" * 32,
    )
    assert one_worker.selection == two_workers.selection
    assert one_worker.population_count == two_workers.population_count == 800


def test_benchmark_comparison_requires_byte_identical_identity_artifacts(
    tmp_path: Path,
) -> None:
    common = {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_mode": "FINAL_EQUIVALENCE",
        "subset_identity": "11" * 32,
        "row_count": 12_000,
        "input_shards": ["fictional.parquet"],
        "per_shard_rows": [{"row_count": 12_000, "shard": "fictional.parquet"}],
        "development_file_sha256": "22" * 32,
        "locked_file_sha256": "33" * 32,
        "development_identity_digest": "44" * 32,
        "locked_identity_digest": "55" * 32,
        "selection_fingerprint": "66" * 32,
        "selection_trace": [_portable_trace_stage()],
        "population_strata_digest": "77" * 32,
        "selected_state_digest": "88" * 32,
        "sampling_config_fingerprint": "99" * 32,
        "source_tree_fingerprint": "aa" * 32,
        "selector_relevant_state_hash": "bb" * 32,
        "state_counts": {"row_count": 12_000},
        "final_selection_status": "FEASIBLE_AND_RUN",
        "infeasibility": None,
        "input_kind": "QUOTA_FEASIBLE_CORPUS",
    }
    runs = []
    for label, engine in _BENCHMARK_MATRIX:
        directory = tmp_path / label
        directory.mkdir()
        workers = int(label.removeprefix("bounded_")) if label.startswith("bounded_") else 1
        (directory / "benchmark_result.json").write_text(
            json.dumps(
                {
                    **common,
                    "engine": engine,
                    "run_label": label,
                    "worker_count": workers,
                    "sqlite_settings": (
                        {"mmap_size_bytes": 8 * 1024**3}
                        if label == "optimized_mmap"
                        else {"mmap_size_bytes": 0}
                        if engine == "optimized-sqlite"
                        else None
                    ),
                    "sqlite_full_state_hash": (
                        "cc" * 32 if engine != "bounded-parallel" else None
                    ),
                }
            ),
            encoding="utf-8",
        )
        runs.append(directory)
    output = tmp_path / "equivalence.json"
    payload = compare_runs(runs, output)
    assert payload["equivalence"] == "FINAL_SELECTION_BYTE_IDENTICAL"
    assert payload["final_selection_equivalence_proven"] is True
    assert "stable_source_row_id" not in output.read_text(encoding="utf-8")

    mismatched = json.loads(
        (runs[-1] / "benchmark_result.json").read_text(encoding="utf-8")
    )
    mismatched["locked_file_sha256"] = "ff" * 32
    (runs[-1] / "benchmark_result.json").write_text(
        json.dumps(mismatched), encoding="utf-8"
    )
    identity_failure = tmp_path / "identity-failure.json"
    with pytest.raises(ValueError, match="PILOT_SELECTION_EQUIVALENCE_FAILURE"):
        compare_runs(runs, identity_failure)
    assert identity_failure.is_file()
    assert (tmp_path / "selection_mismatch.json").is_file()

    mismatched["locked_file_sha256"] = common["locked_file_sha256"]
    mismatched["selection_trace"][0]["selected_count_after"] = 1
    (runs[-1] / "benchmark_result.json").write_text(
        json.dumps(mismatched), encoding="utf-8"
    )
    trace_failure = tmp_path / "trace-failure.json"
    with pytest.raises(ValueError, match="PILOT_SELECTION_EQUIVALENCE_FAILURE"):
        compare_runs(runs, trace_failure)
    trace_payload = json.loads(trace_failure.read_text(encoding="utf-8"))
    divergence = trace_payload["field_mismatches"]["scientific_selection_trace"]
    assert divergence["bounded_16"]["first_differing_stage_index"] == 0
    assert divergence["bounded_16"]["differing_fields"] == [
        "selected_count_after"
    ]


def test_infeasible_performance_subset_proves_state_but_not_final_selection(
    tmp_path: Path,
) -> None:
    common = {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_mode": "PERFORMANCE_STATE",
        "development_file_sha256": None,
        "development_identity_digest": None,
        "final_selection_status": "NOT_APPLICABLE_SUBSET_INFEASIBLE",
        "infeasibility": {"reason_code": "MINIMUM_STRATUM_QUOTA"},
        "input_kind": "PERFORMANCE_SUBSET",
        "input_shards": ["fictional.parquet"],
        "per_shard_rows": [{"row_count": 100_000, "shard": "fictional.parquet"}],
        "locked_file_sha256": None,
        "locked_identity_digest": None,
        "population_strata_digest": "11" * 32,
        "row_count": 100_000,
        "sampling_config_fingerprint": "22" * 32,
        "selected_state_digest": None,
        "selection_fingerprint": None,
        "selection_trace": [_portable_trace_stage()],
        "selector_relevant_state_hash": "33" * 32,
        "source_tree_fingerprint": "44" * 32,
        "state_counts": {"row_count": 100_000},
        "subset_identity": "55" * 32,
    }
    runs = []
    for label, engine in _BENCHMARK_MATRIX:
        directory = tmp_path / label
        directory.mkdir()
        workers = int(label.removeprefix("bounded_")) if label.startswith("bounded_") else 1
        (directory / "benchmark_result.json").write_text(
            json.dumps(
                {
                    **common,
                    "engine": engine,
                    "run_label": label,
                    "worker_count": workers,
                    "sqlite_settings": (
                        {"mmap_size_bytes": 8 * 1024**3}
                        if label == "optimized_mmap"
                        else {"mmap_size_bytes": 0}
                        if engine == "optimized-sqlite"
                        else None
                    ),
                    "sqlite_full_state_hash": (
                        "66" * 32 if engine != "bounded-parallel" else None
                    ),
                }
            ),
            encoding="utf-8",
        )
        runs.append(directory)
    payload = compare_runs(runs, tmp_path / "state-equivalence.json")
    assert payload["equivalence"] == (
        "PRESELECTION_STATE_IDENTICAL_FINAL_SELECTION_NOT_APPLICABLE"
    )
    assert payload["final_selection_equivalence_proven"] is False

    baseline = json.loads(
        (runs[0] / "benchmark_result.json").read_text(encoding="utf-8")
    )
    baseline["benchmark_mode"] = "FINAL_EQUIVALENCE"
    (runs[0] / "benchmark_result.json").write_text(
        json.dumps(baseline), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="PILOT_SELECTION_EQUIVALENCE_FAILURE"):
        compare_runs(runs, tmp_path / "must-not-claim-final.json")


def test_cluster_benchmark_is_subset_only_and_preserves_cancelled_job_evidence() -> None:
    script = (
        Path(__file__).parents[1]
        / "cluster"
        / "goethe_nhr"
        / "phase03_pilot_select_benchmark.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --partition=general1" in script
    assert "#SBATCH --time=1-00:00:00" in script
    assert "#SBATCH --tmp=50000" in script
    assert "GNU_TIME_BIN" in script
    assert '"${GNU_TIME_BIN}" -v' in script
    assert "/usr/bin/time -v" not in script
    assert 'for shard_count in 1 5 10' in script
    assert "expected_rows=100000,500000,1000000" in script
    assert (
        "safe_geocoding_pipeline_benchmark_v4" in script
        and "safe_geocoding_pipeline_benchmark_v3" not in script
    )
    assert "benchmark_repo_root=${BENCHMARK_REPO_ROOT}" in script
    assert "benchmark_baseline_commit=${PHASE03_BENCHMARK_BASE_COMMIT}" in script
    assert "benchmark_source_sha256=${observed_source_sha256}" in script
    assert "benchmark_checkout_validation=PASS" in script
    assert "node_local_storage_validation=PASS" in script
    assert "cancelled_production_job_1747122_evidence=PRESERVED" in script
    assert '"cancelled_production_job_1747122_evidence": "PRESERVED"' in script
    assert "existing_production_job_1747122=UNTOUCHED" not in script
    assert '"production_job_1747122_modified"' not in script
    assert "failed_benchmark_1747375_evidence=PRESERVED" in script
    assert "failed_benchmark_1747527_evidence=PRESERVED" in script
    assert '"benchmark_version": "phase03_pilot_select_benchmark_v4"' in script
    assert "failed_benchmark_1747430_evidence=PRESERVED" in script
    assert "PHASE03_BENCHMARK_MISMATCH_DIRECTORY" in script
    assert "benchmark_stage_fail=" in script
    assert "PERFORMANCE_STATE" in script
    assert "FINAL_EQUIVALENCE" in script
    assert "construct-corpus" in script
    assert "scancel" not in script
    assert "phase03_development_pilot.sbatch" not in script
    assert "pilot-materialize-development" not in script

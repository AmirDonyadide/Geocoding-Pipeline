from __future__ import annotations

import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from .config import Phase03Config
from .pilot_runner import (
    SAMPLING_COLUMNS,
    ProductionSamplingContract,
    SQLiteCandidateStoreSettings,
    SQLitePilotCandidateStore,
    classify_sampling_row_v1,
)
from .pilot_selection import (
    BoundedCandidateSnapshot,
    BoundedPilotSelection,
    ExactBoundedCandidateReducer,
)
from .references import CountryReference, ScriptReference, load_production_references
from .rules import RuleRegistry, load_rule_registry
from .sampler import PilotSamplingConfig
from .text import enforce_runtime_contract


@dataclass(frozen=True, slots=True)
class BoundedShardTask:
    path: Path
    shard_identity: str


@dataclass(frozen=True, slots=True)
class BoundedShardResult:
    shard_id: str
    shard_identity: str
    row_count: int
    snapshot: BoundedCandidateSnapshot


@dataclass(frozen=True, slots=True)
class BoundedReductionResult:
    reducer: ExactBoundedCandidateReducer
    checkpoints: tuple[tuple[str, str, int], ...]


@dataclass(frozen=True, slots=True)
class _WorkerConfiguration:
    country_counts: dict[str, int]
    safety_locations: frozenset[tuple[str, int]]
    contract: ProductionSamplingContract
    pilot_config: PilotSamplingConfig
    batch_rows: int


_WORKER_CONFIGURATION: _WorkerConfiguration | None = None
_WORKER_COUNTRY_REFERENCE: CountryReference | None = None
_WORKER_SCRIPT_REFERENCE: ScriptReference | None = None
_WORKER_RULE_REGISTRY: RuleRegistry | None = None


def _initialize_worker(configuration: _WorkerConfiguration) -> None:
    global _WORKER_CONFIGURATION
    global _WORKER_COUNTRY_REFERENCE
    global _WORKER_SCRIPT_REFERENCE
    global _WORKER_RULE_REGISTRY
    enforce_runtime_contract()
    phase03_config = Phase03Config()
    phase03_config.validate()
    country_reference, script_reference = load_production_references(
        expected_country_reference_id=phase03_config.country_reference_version,
        expected_unicode_reference_id=phase03_config.unicode_reference_version,
    )
    _WORKER_CONFIGURATION = configuration
    _WORKER_COUNTRY_REFERENCE = country_reference
    _WORKER_SCRIPT_REFERENCE = script_reference
    _WORKER_RULE_REGISTRY = load_rule_registry()


def _reduce_shard(task: BoundedShardTask) -> BoundedShardResult:
    configuration = _WORKER_CONFIGURATION
    country_reference = _WORKER_COUNTRY_REFERENCE
    script_reference = _WORKER_SCRIPT_REFERENCE
    rule_registry = _WORKER_RULE_REGISTRY
    if (
        configuration is None
        or country_reference is None
        or script_reference is None
        or rule_registry is None
    ):
        raise RuntimeError("bounded pilot worker was not initialized")
    reducer = ExactBoundedCandidateReducer(
        configuration.pilot_config, track_all_seen_ids=True
    )
    parquet = pq.ParquetFile(
        task.path, page_checksum_verification=True, pre_buffer=True
    )
    for batch in parquet.iter_batches(
        batch_size=configuration.batch_rows,
        columns=list(SAMPLING_COLUMNS),
        use_threads=False,
    ):
        for row in batch.to_pylist():
            location = (
                str(row["source_file"]),
                int(row["source_logical_record_number"]),
            )
            reducer.accept(
                classify_sampling_row_v1(
                    row,
                    contract=configuration.contract,
                    country_reference=country_reference,
                    script_reference=script_reference,
                    rule_registry=rule_registry,
                    country_counts=configuration.country_counts,
                    targeted_safety_case=location in configuration.safety_locations,
                )
            )
    snapshot = reducer.snapshot
    # Phase 2's validated reconciliation proves cross-shard uniqueness for this
    # exact production snapshot. The per-shard set has already checked local
    # duplicates and is deliberately omitted from the merge payload.
    snapshot.seen_ids = None
    return BoundedShardResult(
        task.path.name,
        task.shard_identity,
        snapshot.row_count,
        snapshot,
    )


def reduce_production_shards_bounded(
    tasks: list[BoundedShardTask],
    *,
    country_counts: Counter[str],
    safety_locations: frozenset[tuple[str, int]],
    contract: ProductionSamplingContract,
    pilot_config: PilotSamplingConfig,
    worker_count: int,
    batch_rows: int = 25_000,
) -> BoundedReductionResult:
    if worker_count < 1:
        raise ValueError("bounded pilot worker count must be positive")
    if batch_rows < 1:
        raise ValueError("bounded pilot batch size must be positive")
    configuration = _WorkerConfiguration(
        dict(country_counts), safety_locations, contract, pilot_config, batch_rows
    )
    merged = ExactBoundedCandidateReducer(pilot_config, track_all_seen_ids=False)
    checkpoints: list[tuple[str, str, int]] = []
    if worker_count == 1:
        _initialize_worker(configuration)
        for task in tasks:
            result = _reduce_shard(task)
            merged.merge(result.snapshot)
            checkpoints.append(
                (result.shard_id, result.shard_identity, result.row_count)
            )
            print(
                f"pilot_select_shard_complete={result.shard_id} rows={result.row_count}",
                file=sys.stderr,
                flush=True,
            )
    else:
        with ProcessPoolExecutor(
            max_workers=worker_count,
            initializer=_initialize_worker,
            initargs=(configuration,),
        ) as executor:
            futures = {executor.submit(_reduce_shard, task): task for task in tasks}
            try:
                for future in as_completed(futures):
                    result = future.result()
                    del futures[future]
                    merged.merge(result.snapshot)
                    checkpoints.append(
                        (result.shard_id, result.shard_identity, result.row_count)
                    )
                    print(
                        f"pilot_select_shard_complete={result.shard_id} rows={result.row_count}",
                        file=sys.stderr,
                        flush=True,
                    )
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
    ordered_checkpoints = tuple(
        sorted(checkpoints, key=lambda value: value[0].encode("utf-8"))
    )
    return BoundedReductionResult(merged, ordered_checkpoints)


def write_compact_selected_state(
    path: Path,
    *,
    bounded_selection: BoundedPilotSelection,
    checkpoints: tuple[tuple[str, str, int], ...],
    config: PilotSamplingConfig,
    classification_contract: ProductionSamplingContract,
    production_binding_fingerprint: str,
    data_scope: str = "PRODUCTION",
) -> None:
    """Atomically persist only selected state needed by DEVELOPMENT review."""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    if temporary.exists():
        raise FileExistsError(temporary)
    store = SQLitePilotCandidateStore(
        temporary,
        config=config,
        settings=SQLiteCandidateStoreSettings.baseline(),
        data_scope=data_scope,
        classification_contract=classification_contract,
        production_binding_fingerprint=production_binding_fingerprint,
    )
    try:
        store.ingest(bounded_selection.selected_candidates)
        with store.connection:
            store.connection.executemany(
                "INSERT INTO selected VALUES (?,?)",
                (
                    (
                        candidate.stable_source_row_id_v1,
                        candidate.strata[config.primary_stratum],
                    )
                    for candidate in bounded_selection.selected_candidates
                ),
            )
            store.connection.executemany(
                "INSERT INTO checkpoint VALUES (?,?,?,'COMPLETE')", checkpoints
            )
            store.connection.execute(
                "INSERT INTO run_metadata VALUES (?,?)",
                ("candidate_population_scope", "SELECTED_ONLY"),
            )
            store.connection.execute(
                "INSERT INTO run_metadata VALUES (?,?)",
                ("selection_engine", "bounded-parallel"),
            )
        store.validate_integrity()
    finally:
        store.close()
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)

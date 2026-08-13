from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import resource
import sqlite3
import time
import unicodedata
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import duckdb
import pyarrow
import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from ..phase02.schema import exact_schema_matches
from .config import Phase03Config
from .pilot_orchestration import load_country_profile, load_phase02_manifest
from .pilot_runner import (
    SAMPLING_COLUMNS,
    Phase01SafetyLocationTracker,
    ProductionSamplingContract,
    SQLiteCandidateStoreSettings,
    SQLitePilotCandidateStore,
    classify_sampling_row_v1,
    effective_sampling_fingerprint,
    load_phase01_safety_locations,
    proposed_production_pilot_config,
    write_identity_set,
)
from .pilot_selection_runtime import (
    BoundedShardTask,
    reduce_production_shards_bounded,
    write_compact_selected_state,
)
from .pilot_selection import (
    BoundedCandidateSnapshot,
    BoundedPilotSelection,
    ExactBoundedCandidateReducer,
    PilotSelectionInfeasibleError,
    SelectionTrace,
    SelectionTraceStage,
    bounded_snapshot_state,
)
from .sampler import PilotSamplingConfig, PilotSelection
from .references import load_production_references
from .rules import load_rule_registry
from .text import enforce_runtime_contract

BENCHMARK_VERSION = "phase03_pilot_select_benchmark_v4"
CORPUS_VERSION = "phase03_pilot_select_equivalence_corpus_v2"
CORPUS_BATCH_SHARDS = 16
BENCHMARK_TIMESTAMP = "2026-01-01T00:00:00Z"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _peak_rss_bytes() -> int:
    own = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    children = int(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)
    scale = 1 if platform.system() == "Darwin" else 1024
    return max(own, children) * scale


def _directory_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _population_strata_digest(counts: Counter[tuple[str, str]]) -> str:
    payload: list[JsonValue] = [
        {"category": category, "count": count, "dimension": dimension}
        for (dimension, category), count in sorted(
            counts.items(), key=lambda item: (item[0][0].encode(), item[0][1].encode())
        )
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sqlite_population_counts(connection: sqlite3.Connection) -> Counter[tuple[str, str]]:
    return Counter(
        {
            (str(dimension), str(category)): int(count)
            for dimension, category, count in connection.execute(
                "SELECT dimension,category,COUNT(*) FROM membership "
                "GROUP BY dimension,category ORDER BY dimension,category"
            )
        }
    )


def _sqlite_full_state_digest(connection: sqlite3.Connection) -> str:
    """Hash every exact candidate/membership value in SQLite's canonical order."""

    digest = hashlib.sha256(b"phase03:pilot-select-benchmark:sqlite-state-v1\0")
    queries = (
        (
            "candidate",
            "SELECT stable_id,primary_group,quota_score,fill_score,split_score,targeted "
            "FROM candidate ORDER BY stable_id",
        ),
        (
            "membership",
            "SELECT dimension,category,stable_id FROM membership "
            "ORDER BY dimension,category,stable_id",
        ),
        (
            "safety_location",
            "SELECT source_file,logical_record_number FROM safety_location "
            "ORDER BY source_file,logical_record_number",
        ),
        (
            "checkpoint",
            "SELECT shard_id,shard_identity,row_count,status FROM checkpoint "
            "ORDER BY shard_id",
        ),
    )
    for table, query in queries:
        digest.update(table.encode("ascii") + b"\0")
        row_count = 0
        for row in connection.execute(query):
            row_count += 1
            digest.update(len(row).to_bytes(4, "big"))
            for value in row:
                raw = bytes(value) if isinstance(value, bytes) else str(value).encode()
                digest.update(len(raw).to_bytes(8, "big"))
                digest.update(raw)
        digest.update(row_count.to_bytes(8, "big"))
    return digest.hexdigest()


def _selection_from_snapshot(
    snapshot: BoundedCandidateSnapshot,
    *,
    pilot_config: PilotSamplingConfig,
    subset_identity: str,
    effective_fingerprint: str,
    trace: SelectionTrace | None = None,
) -> tuple[
    BoundedPilotSelection | None,
    str,
    dict[str, int | str | None] | None,
]:
    reducer = ExactBoundedCandidateReducer(pilot_config, track_all_seen_ids=False)
    reducer.merge(snapshot)
    try:
        bounded = reducer.select(
            input_phase02_manifest_identity=subset_identity,
            selection_timestamp=BENCHMARK_TIMESTAMP,
            effective_sampling_fingerprint=effective_fingerprint,
            trace=trace,
        )
    except PilotSelectionInfeasibleError as error:
        return (
            None,
            "NOT_APPLICABLE_SUBSET_INFEASIBLE",
            error.privacy_safe_diagnostic(),
        )
    return bounded, "FEASIBLE_AND_RUN", None


def _privacy_safe_identity(identity: bytes) -> str:
    return hashlib.sha256(
        b"phase03:pilot-select-mismatch-identity-v1\0" + identity
    ).hexdigest()


def _ordered_identity_fingerprint(
    development: tuple[bytes, ...], locked: tuple[bytes, ...]
) -> str:
    digest = hashlib.sha256(b"phase03:pilot-select-scientific-result-v1\0")
    for partition, values in ((b"DEVELOPMENT", development), (b"LOCKED", locked)):
        digest.update(len(partition).to_bytes(8, "big"))
        digest.update(partition)
        digest.update(len(values).to_bytes(8, "big"))
        for identity in values:
            digest.update(identity)
    return digest.hexdigest()


def _metadata_payload(selection: PilotSelection) -> dict[str, str]:
    seal = selection.seal
    return {
        "input_phase02_manifest_identity": seal.input_phase02_manifest_identity,
        "pilot_version": seal.pilot_version,
        "sampling_config_fingerprint": seal.sampling_config_fingerprint,
        "seed": seal.seed,
        "selection_timestamp": seal.selection_timestamp,
    }


def _metadata_fingerprint(selection: PilotSelection) -> str:
    return hashlib.sha256(
        canonical_json_bytes(cast(JsonValue, _metadata_payload(selection)))
    ).hexdigest()


def _trace_quota_digest(trace: SelectionTrace) -> str:
    payload: list[JsonValue] = [
        {
            "category": stage.category,
            "dimension": stage.dimension,
            "frontier_digest": stage.frontier_digest,
            "stage_index": stage.stage_index,
        }
        for stage in trace.stages
        if stage.stage_type == "SECONDARY_QUOTA"
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _trace_fill_digest(trace: SelectionTrace) -> str | None:
    stages = [stage for stage in trace.stages if stage.stage_type == "DETERMINISTIC_FILL"]
    return stages[0].frontier_digest if len(stages) == 1 else None


def _hashed_primary_counts(stage: SelectionTraceStage | None) -> list[dict[str, JsonValue]]:
    if stage is None:
        return []
    return [
        {
            "count": count,
            "primary_group_sha256": hashlib.sha256(
                b"phase03:pilot-select-primary-group-v1\0" + primary.encode("utf-8")
            ).hexdigest(),
        }
        for primary, count in stage.primary_group_counts
    ]


def _privacy_safe_trace_category(
    dimension: str | None, category: str | None
) -> str | None:
    if category is None:
        return None
    if category.startswith("UNUSUAL:"):
        return "UNUSUAL_REDACTED"
    if dimension in {"country_group", "primary_country_group"}:
        return "COUNTRY_GROUP_SHA256:" + hashlib.sha256(
            b"phase03:pilot-select-country-group-v1\0" + category.encode("utf-8")
        ).hexdigest()
    return category


def _privacy_safe_trace_events(
    events: Sequence[tuple[bytes, str, str]],
) -> list[dict[str, JsonValue]]:
    return [
        {
            "identity_sha256": _privacy_safe_identity(identity),
            "primary_group_sha256": hashlib.sha256(
                b"phase03:pilot-select-primary-group-v1\0"
                + primary.encode("utf-8")
            ).hexdigest(),
            "rank": rank,
        }
        for identity, rank, primary in events[:16]
    ]


def _trace_stage_payload(stage: SelectionTraceStage | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {
        "available": stage.available,
        "candidates_cap_blocked": stage.candidates_cap_blocked,
        "candidates_considered": stage.candidates_considered,
        "cap_blocked_digest": stage.cap_blocked_digest,
        "cap_blocked_digest_complete": stage.cap_blocked_digest_complete,
        "cap_blocked_events": _privacy_safe_trace_events(stage.cap_blocked_events),
        "category": _privacy_safe_trace_category(stage.dimension, stage.category),
        "cumulative_selected_digest_before": (
            stage.cumulative_selected_digest_before
        ),
        "cumulative_selected_digest": stage.cumulative_selected_digest,
        "dimension": stage.dimension,
        "fill_frontier_digest": stage.fill_frontier_digest,
        "frontier_digest": stage.frontier_digest,
        "frontier_digest_complete": stage.frontier_digest_complete,
        "primary_group_count_digest_before": (
            stage.primary_group_count_digest_before
        ),
        "primary_group_count_digest": stage.primary_group_count_digest,
        "primary_group_counts_before": _hashed_primary_counts_before(stage),
        "primary_group_counts": _hashed_primary_counts(stage),
        "quota_frontier_digest": stage.quota_frontier_digest,
        "represented_before": stage.represented_before,
        "represented_after": stage.represented_after,
        "selected_count_before": stage.selected_count_before,
        "selected_count_after": stage.selected_count_after,
        "selected_this_stage_count": stage.selected_this_stage_count,
        "selected_this_stage_digest": stage.selected_this_stage_digest,
        "selected_events": _privacy_safe_trace_events(stage.selected_events),
        "stage_index": stage.stage_index,
        "stage_type": stage.stage_type,
        "target": stage.target,
    }


def _hashed_primary_counts_before(
    stage: SelectionTraceStage | None,
) -> list[dict[str, JsonValue]]:
    if stage is None:
        return []
    return [
        {
            "count": count,
            "primary_group_sha256": hashlib.sha256(
                b"phase03:pilot-select-primary-group-v1\0" + primary.encode("utf-8")
            ).hexdigest(),
        }
        for primary, count in stage.primary_group_counts_before
    ]


_SCIENTIFIC_TRACE_FIELDS = (
    "stage_index",
    "stage_type",
    "dimension",
    "category",
    "target",
    "available",
    "represented_before",
    "represented_after",
    "selected_count_before",
    "selected_count_after",
    "selected_this_stage_count",
    "selected_this_stage_digest",
    "cumulative_selected_digest_before",
    "cumulative_selected_digest",
    "primary_group_count_digest_before",
    "primary_group_count_digest",
)
_CURSOR_TRACE_FIELDS = (
    "candidates_considered",
    "candidates_cap_blocked",
    "cap_blocked_digest",
    "cap_blocked_digest_complete",
    "frontier_digest",
    "frontier_digest_complete",
)


def _first_trace_divergence(
    reference_trace: SelectionTrace,
    bounded_trace: SelectionTrace,
    *,
    include_cursor_diagnostics: bool,
) -> tuple[int, SelectionTraceStage | None, SelectionTraceStage | None, tuple[str, ...]] | None:
    fields = _SCIENTIFIC_TRACE_FIELDS + (
        _CURSOR_TRACE_FIELDS if include_cursor_diagnostics else ()
    )
    for index in range(max(len(reference_trace.stages), len(bounded_trace.stages))):
        reference_stage = (
            reference_trace.stages[index]
            if index < len(reference_trace.stages)
            else None
        )
        bounded_stage = (
            bounded_trace.stages[index] if index < len(bounded_trace.stages) else None
        )
        if reference_stage is None or bounded_stage is None:
            return index, reference_stage, bounded_stage, ("stage_presence",)
        differing = tuple(
            field
            for field in fields
            if getattr(reference_stage, field) != getattr(bounded_stage, field)
        )
        if differing:
            return index, reference_stage, bounded_stage, differing
    return None


def _primary_occupancy_difference(
    reference_stage: SelectionTraceStage | None,
    bounded_stage: SelectionTraceStage | None,
    *,
    before: bool,
) -> list[dict[str, JsonValue]]:
    reference = dict(
        ()
        if reference_stage is None
        else (
            reference_stage.primary_group_counts_before
            if before
            else reference_stage.primary_group_counts
        )
    )
    bounded = dict(
        ()
        if bounded_stage is None
        else (
            bounded_stage.primary_group_counts_before
            if before
            else bounded_stage.primary_group_counts
        )
    )
    result: list[dict[str, JsonValue]] = []
    for primary in sorted(set(reference) | set(bounded), key=lambda value: value.encode()):
        if reference.get(primary, 0) == bounded.get(primary, 0):
            continue
        result.append(
            {
                "bounded_count": bounded.get(primary, 0),
                "primary_group_sha256": hashlib.sha256(
                    b"phase03:pilot-select-primary-group-v1\0"
                    + primary.encode("utf-8")
                ).hexdigest(),
                "reference_count": reference.get(primary, 0),
            }
        )
    return result


def _trace_divergence_payload(
    divergence: tuple[
        int,
        SelectionTraceStage | None,
        SelectionTraceStage | None,
        tuple[str, ...],
    ]
    | None,
) -> dict[str, Any] | None:
    if divergence is None:
        return None
    index, reference_stage, bounded_stage, differing_fields = divergence
    return {
        "bounded_stage": _trace_stage_payload(bounded_stage),
        "differing_fields": list(differing_fields),
        "first_differing_stage_index": index,
        "post_stage_primary_occupancy_differences": _primary_occupancy_difference(
            reference_stage, bounded_stage, before=False
        ),
        "pre_stage_primary_occupancy_differences": _primary_occupancy_difference(
            reference_stage, bounded_stage, before=True
        ),
        "reference_stage": _trace_stage_payload(reference_stage),
    }


def _selection_mismatch_payload(
    *,
    subset_identity: str,
    files: Sequence[dict[str, Any]],
    row_count: int,
    reference: PilotSelection,
    bounded: PilotSelection,
    reference_trace: SelectionTrace,
    bounded_trace: SelectionTrace,
) -> dict[str, Any]:
    reference_selected = reference.development_ids + reference.locked_evaluation_ids
    bounded_selected = bounded.development_ids + bounded.locked_evaluation_ids
    reference_set = set(reference_selected)
    bounded_set = set(bounded_selected)
    first_order_difference = next(
        (
            index
            for index, (reference_id, bounded_id) in enumerate(
                zip(reference_selected, bounded_selected, strict=False)
            )
            if reference_id != bounded_id
        ),
        None,
    )
    if first_order_difference is None and len(reference_selected) != len(bounded_selected):
        first_order_difference = min(len(reference_selected), len(bounded_selected))
    scientific_divergence = _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=False
    )
    cursor_divergence = _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=True
    )
    first_stage_index = (
        scientific_divergence[0] if scientific_divergence is not None else None
    )

    identity_equal = (
        reference.development_ids == bounded.development_ids
        and reference.locked_evaluation_ids == bounded.locked_evaluation_ids
    )
    metadata_equal = _metadata_payload(reference) == _metadata_payload(bounded)
    mismatch_kind = (
        "METADATA_ONLY"
        if identity_equal and not metadata_equal
        else "SCIENTIFIC_IDENTITY_OR_ASSIGNMENT"
    )
    previous_reference_digest = (
        reference_trace.stages[first_stage_index - 1].cumulative_selected_digest
        if first_stage_index is not None
        and first_stage_index > 0
        and first_stage_index <= len(reference_trace.stages)
        else None
    )
    previous_bounded_digest = (
        bounded_trace.stages[first_stage_index - 1].cumulative_selected_digest
        if first_stage_index is not None
        and first_stage_index > 0
        and first_stage_index <= len(bounded_trace.stages)
        else None
    )
    return {
        "benchmark_version": BENCHMARK_VERSION,
        "bounded_development_count": len(bounded.development_ids),
        "bounded_fill_frontier_digest": _trace_fill_digest(bounded_trace),
        "bounded_locked_count": len(bounded.locked_evaluation_ids),
        "bounded_metadata_fingerprint": _metadata_fingerprint(bounded),
        "bounded_previous_selection_digest": previous_bounded_digest,
        "bounded_quota_frontier_digest": _trace_quota_digest(bounded_trace),
        "bounded_selected_count": len(bounded_selected),
        "bounded_selection_fingerprint": _ordered_identity_fingerprint(
            bounded.development_ids, bounded.locked_evaluation_ids
        ),
        "first_differing_ordered_position": first_order_difference,
        "first_differing_stage_index": first_stage_index,
        "first_scientific_state_divergence": _trace_divergence_payload(
            scientific_divergence
        ),
        "first_trace_divergence_including_cursor_diagnostics": (
            _trace_divergence_payload(cursor_divergence)
        ),
        "identity_result_equal": identity_equal,
        "metadata_equal": metadata_equal,
        "mismatch_kind": mismatch_kind,
        "only_bounded_count": len(bounded_set - reference_set),
        "only_bounded_identity_sha256": [
            _privacy_safe_identity(identity)
            for identity in sorted(bounded_set - reference_set)[:16]
        ],
        "only_reference_count": len(reference_set - bounded_set),
        "only_reference_identity_sha256": [
            _privacy_safe_identity(identity)
            for identity in sorted(reference_set - bounded_set)[:16]
        ],
        "reference_development_count": len(reference.development_ids),
        "reference_fill_frontier_digest": _trace_fill_digest(reference_trace),
        "reference_locked_count": len(reference.locked_evaluation_ids),
        "reference_metadata_fingerprint": _metadata_fingerprint(reference),
        "reference_previous_selection_digest": previous_reference_digest,
        "reference_quota_frontier_digest": _trace_quota_digest(reference_trace),
        "reference_selected_count": len(reference_selected),
        "reference_selection_fingerprint": _ordered_identity_fingerprint(
            reference.development_ids, reference.locked_evaluation_ids
        ),
        "row_count": row_count,
        "shards": [
            {
                "output_file": str(item["output_file"]),
                "output_sha256": str(item["output_sha256"]),
            }
            for item in files
        ],
        "subset_identity": subset_identity,
        "trace_version": reference_trace.trace_version,
    }


def _persist_selection_mismatch(
    output_directory: Path,
    *,
    run_label: str,
    payload: dict[str, Any],
) -> tuple[Path, Path | None]:
    local_path = output_directory / "selection_mismatch.json"
    _write_json(local_path, payload)
    persistent_root_raw = os.environ.get("PHASE03_BENCHMARK_MISMATCH_DIRECTORY")
    if not persistent_root_raw:
        return local_path, None
    persistent_root = Path(persistent_root_raw)
    persistent_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    persistent_root.chmod(0o700)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", run_label)
    persistent_path = persistent_root / (
        f"selection_mismatch_{safe_label}_{str(payload['subset_identity'])[:16]}.json"
    )
    _write_json(persistent_path, payload)
    return local_path, persistent_path


def _infeasibility_semantic_key(
    diagnostic: dict[str, int | str | None] | None,
) -> tuple[object, ...] | None:
    if diagnostic is None:
        return None
    return tuple(
        diagnostic.get(field)
        for field in (
            "reason_code",
            "dimension",
            "category",
            "target",
            "represented",
            "available",
            "primary_cap",
        )
    )


def _selection_status_mismatch_payload(
    *,
    subset_identity: str,
    files: Sequence[dict[str, Any]],
    row_count: int,
    reference_status: str,
    bounded_status: str,
    reference_infeasibility: dict[str, int | str | None] | None,
    bounded_infeasibility: dict[str, int | str | None] | None,
    reference_trace: SelectionTrace,
    bounded_trace: SelectionTrace,
) -> dict[str, Any]:
    scientific_divergence = _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=False
    )
    cursor_divergence = _first_trace_divergence(
        reference_trace, bounded_trace, include_cursor_diagnostics=True
    )

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "bounded_final_selection_status": bounded_status,
        "bounded_infeasibility": bounded_infeasibility,
        "first_scientific_state_divergence": _trace_divergence_payload(
            scientific_divergence
        ),
        "first_trace_divergence_including_cursor_diagnostics": (
            _trace_divergence_payload(cursor_divergence)
        ),
        "mismatch_kind": (
            "SCIENTIFIC_TRACE_STATE"
            if reference_status == bounded_status
            and _infeasibility_semantic_key(reference_infeasibility)
            == _infeasibility_semantic_key(bounded_infeasibility)
            and scientific_divergence is not None
            else "FEASIBILITY_STATUS_OR_REASON"
        ),
        "reference_final_selection_status": reference_status,
        "reference_infeasibility": reference_infeasibility,
        "row_count": row_count,
        "shards": [
            {
                "output_file": str(item["output_file"]),
                "output_sha256": str(item["output_sha256"]),
            }
            for item in files
        ],
        "subset_identity": subset_identity,
        "trace_version": reference_trace.trace_version,
    }


def _selected_state_digest(path: Path) -> str:
    """Hash selected ranks and memberships without exposing identities."""
    digest = hashlib.sha256(b"phase03:pilot-select-benchmark:selected-state-v1\0")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        for row in connection.execute(
            "SELECT c.stable_id,c.primary_group,c.quota_score,c.fill_score,"
            "c.split_score,c.targeted FROM candidate c JOIN selected s USING(stable_id) "
            "ORDER BY c.stable_id"
        ):
            for value in row:
                raw = bytes(value) if isinstance(value, bytes) else str(value).encode()
                digest.update(len(raw).to_bytes(8, "big"))
                digest.update(raw)
        for stable_id, dimension, category in connection.execute(
            "SELECT m.stable_id,m.dimension,m.category FROM membership m "
            "JOIN selected s USING(stable_id) "
            "ORDER BY m.stable_id,m.dimension,m.category"
        ):
            for raw in (
                bytes(stable_id),
                str(dimension).encode(),
                str(category).encode(),
            ):
                digest.update(len(raw).to_bytes(8, "big"))
                digest.update(raw)
    finally:
        connection.close()
    return digest.hexdigest()


def _active_corpus_binding(profile_path: Path) -> dict[str, JsonValue]:
    config = Phase03Config()
    country_reference, script_reference = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    registry = load_rule_registry()
    return {
        "country_profile_sha256": _sha256(profile_path),
        "country_reference_id": country_reference.version,
        "country_reference_sha256": (
            country_reference.assignment_manifest.artifact_sha256
        ),
        "phase03_configuration_fingerprint": (
            config.configuration_fingerprint().hex()
        ),
        "rule_registry_sha256": registry.fingerprint,
        "rule_registry_version": registry.registry_version,
        "sampling_config_fingerprint": proposed_production_pilot_config().fingerprint(),
        "sampling_contract_fingerprint": ProductionSamplingContract().fingerprint(),
        "script_reference_id": script_reference.version,
        "script_reference_sha256": script_reference.manifest.artifact_sha256,
    }


def _load_input_files(
    manifest_path: Path,
    *,
    profile_path: Path,
    shard_count: int | None,
    corpus_manifest_path: Path | None,
) -> tuple[list[dict[str, Any]], list[Path], str, str]:
    if (shard_count is None) == (corpus_manifest_path is None):
        raise ValueError("specify exactly one benchmark subset or corpus manifest")
    if shard_count is not None and shard_count not in {1, 5, 10}:
        raise ValueError("performance benchmark shard count must be one of 1, 5, or 10")
    manifest = load_phase02_manifest(manifest_path)
    reconciliation = cast(dict[str, Any], manifest.get("reconciliation"))
    if (
        manifest.get("run_id") != "phase02_20260810T173851Z_1349152b"
        or manifest.get("phase02_completion_gate") != "PASS"
        or reconciliation.get("status") != "PASS"
        or reconciliation.get("total_rows") != 20_600_000
        or reconciliation.get("distinct_stable_ids") != 20_600_000
        or reconciliation.get("duplicate_stable_ids") != 0
    ):
        raise ValueError("benchmark input is not the authoritative Phase 2 snapshot")
    authoritative_files = {
        str(item["output_file"]): cast(dict[str, Any], item)
        for item in manifest["files"]
    }
    input_kind = "PERFORMANCE_SUBSET"
    if corpus_manifest_path is None:
        files = [
            cast(dict[str, Any], item)
            for item in manifest["files"][: cast(int, shard_count)]
        ]
    else:
        corpus = json.loads(corpus_manifest_path.read_text(encoding="utf-8"))
        active_binding = _active_corpus_binding(profile_path)
        if (
            corpus.get("corpus_version") != CORPUS_VERSION
            or corpus.get("phase02_manifest_sha256") != _sha256(manifest_path)
            or corpus.get("final_selection_status") != "FEASIBLE_AND_RUN"
            or not isinstance(corpus.get("files"), list)
            or corpus.get("configuration_binding") != active_binding
        ):
            raise ValueError("quota-feasible benchmark corpus identity mismatch")
        file_names = [str(item["output_file"]) for item in corpus["files"]]
        if (
            not file_names
            or len(file_names) == 206
            or len(file_names) != len(set(file_names))
        ):
            raise ValueError("benchmark corpus must be a strict unique Phase 2 subset")
        files = []
        for corpus_file in corpus["files"]:
            name = str(corpus_file["output_file"])
            item = authoritative_files.get(name)
            if item is None or str(corpus_file.get("output_sha256")) != str(
                item["output_sha256"]
            ):
                raise ValueError("benchmark corpus contains an unknown shard identity")
            files.append(item)
        expected_corpus_identity = fingerprint(
            {
                "configuration_binding": active_binding,
                "corpus_version": CORPUS_VERSION,
                "files": corpus["files"],
                "phase02_manifest_sha256": _sha256(manifest_path),
            }
        )
        if corpus.get("corpus_identity") != expected_corpus_identity:
            raise ValueError("quota-feasible benchmark corpus fingerprint mismatch")
        input_kind = "QUOTA_FEASIBLE_CORPUS"
    paths = [manifest_path.parent / str(item["output_file"]) for item in files]
    for item, path in zip(files, paths, strict=True):
        if (
            not path.is_file()
            or _sha256(path) != item["output_sha256"]
            or not exact_schema_matches(
                pq.ParquetFile(
                    path, page_checksum_verification=True, pre_buffer=True
                ).schema_arrow
            )
        ):
            raise ValueError(f"benchmark shard identity mismatch: {path.name}")
    subset_identity = fingerprint(
        {
            "benchmark_version": BENCHMARK_VERSION,
            "phase02_manifest_sha256": _sha256(manifest_path),
            "shards": [
                {
                    "output_file": item["output_file"],
                    "output_sha256": item["output_sha256"],
                }
                for item in files
            ],
        }
    )
    return files, paths, subset_identity, input_kind


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(canonical_json_bytes(value) + b"\n")
    temporary.chmod(0o600)
    os.replace(temporary, path)
    path.chmod(0o600)


def _filtered_safety_locations(
    path: Path, source_files: set[str]
) -> dict[tuple[str, int], tuple[str, ...]]:
    return {
        key: value
        for key, value in load_phase01_safety_locations(path).items()
        if key[0] in source_files
    }


def run_engine(
    *,
    run_label: str,
    engine: str,
    manifest_path: Path,
    phase01_anomalies_path: Path,
    profile_path: Path,
    shard_count: int | None,
    corpus_manifest_path: Path | None,
    benchmark_mode: str,
    output_directory: Path,
    worker_count: int,
    sqlite_cache_size_mib: int,
    sqlite_mmap_size_mib: int,
    sqlite_insertion_batch_size: int,
) -> dict[str, Any]:
    if engine not in {"baseline-sqlite", "optimized-sqlite", "bounded-parallel"}:
        raise ValueError("unsupported benchmark selection engine")
    if benchmark_mode not in {"PERFORMANCE_STATE", "FINAL_EQUIVALENCE"}:
        raise ValueError("unsupported benchmark mode")
    files, paths, subset_identity, input_kind = _load_input_files(
        manifest_path,
        profile_path=profile_path,
        shard_count=shard_count,
        corpus_manifest_path=corpus_manifest_path,
    )
    if benchmark_mode == "FINAL_EQUIVALENCE" and input_kind != "QUOTA_FEASIBLE_CORPUS":
        raise ValueError("final equivalence requires a quota-feasible corpus")
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True, mode=0o700)
    output_directory.chmod(0o700)
    phase03_config = Phase03Config()
    country_reference, script_reference = load_production_references(
        expected_country_reference_id=phase03_config.country_reference_version,
        expected_unicode_reference_id=phase03_config.unicode_reference_version,
    )
    registry = load_rule_registry()
    contract = ProductionSamplingContract()
    pilot_config = proposed_production_pilot_config()
    country_counts = load_country_profile(
        profile_path, manifest_identity=_sha256(manifest_path)
    )
    if sum(country_counts.values()) != 20_600_000:
        raise ValueError("benchmark requires the complete production country profile")
    safety_locations = _filtered_safety_locations(
        phase01_anomalies_path, {str(item["source_file"]) for item in files}
    )
    production_binding = fingerprint(
        {
            "benchmark_subset_identity": subset_identity,
            "country_reference_id": country_reference.version,
            "country_reference_sha256": country_reference.assignment_manifest.artifact_sha256,
            "script_reference_id": script_reference.version,
            "script_reference_sha256": script_reference.manifest.artifact_sha256,
            "rule_registry_version": registry.registry_version,
            "rule_registry_sha256": registry.fingerprint,
            "phase03_configuration_fingerprint": (
                phase03_config.configuration_fingerprint().hex()
            ),
        }
    )
    classification_fingerprint = fingerprint(
        {
            "sampling_contract_fingerprint": contract.fingerprint(),
            "production_binding_fingerprint": production_binding,
        }
    )
    effective_fingerprint = effective_sampling_fingerprint(
        classification_contract_fingerprint=classification_fingerprint,
        config=pilot_config,
    )
    state_path = output_directory / "candidate_state.sqlite3"
    started = time.perf_counter()
    cpu_before = resource.getrusage(resource.RUSAGE_SELF)
    child_cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
    sqlite_settings_payload: dict[str, Any] | None = None
    sqlite_runtime_settings_payload: dict[str, int | str] | None = None
    checkpoints: list[tuple[str, str, int]] = []
    population_group_counts: Counter[tuple[str, str]]
    selector_reducer: ExactBoundedCandidateReducer
    sqlite_full_state_hash: str | None = None
    output_trace: SelectionTrace
    if engine in {"baseline-sqlite", "optimized-sqlite"}:
        settings = (
            SQLiteCandidateStoreSettings.baseline()
            if engine == "baseline-sqlite"
            else SQLiteCandidateStoreSettings.optimized(
                cache_size_mib=sqlite_cache_size_mib,
                mmap_size_mib=sqlite_mmap_size_mib,
                insertion_batch_size=sqlite_insertion_batch_size,
            )
        )
        sqlite_settings_payload = cast(dict[str, Any], settings.portable_dict())
        store = SQLitePilotCandidateStore(
            state_path,
            config=pilot_config,
            settings=settings,
            data_scope="PRODUCTION_BENCHMARK_SUBSET",
            classification_contract=contract,
            production_binding_fingerprint=production_binding,
        )
        tracker = Phase01SafetyLocationTracker(safety_locations, Counter())
        selector_reducer = ExactBoundedCandidateReducer(
            pilot_config, track_all_seen_ids=False
        )
        bounded_trace = SelectionTrace()
        reference_trace = SelectionTrace()
        try:
            for item, path in zip(files, paths, strict=True):
                parquet = pq.ParquetFile(
                    path, page_checksum_verification=True, pre_buffer=True
                )

                def candidates() -> Iterator[Any]:
                    for batch in parquet.iter_batches(
                        batch_size=25_000,
                        columns=list(SAMPLING_COLUMNS),
                        use_threads=False,
                    ):
                        for row in batch.to_pylist():
                            targeted = tracker.observe(
                                str(row["source_file"]),
                                int(row["source_logical_record_number"]),
                            )
                            candidate = classify_sampling_row_v1(
                                row,
                                contract=contract,
                                country_reference=country_reference,
                                script_reference=script_reference,
                                rule_registry=registry,
                                country_counts=country_counts,
                                targeted_safety_case=targeted,
                            )
                            selector_reducer.accept(candidate)
                            yield candidate

                row_count, _ = store.ingest_shard(
                    path.name,
                    str(item["output_sha256"]),
                    candidates(),
                    batch_size=settings.insertion_batch_size,
                )
                checkpoints.append((path.name, str(item["output_sha256"]), row_count))
            tracker.validate_complete()
            population_group_counts = _sqlite_population_counts(store.connection)
            sqlite_runtime_settings_payload = store.sqlite_runtime_settings()
            sqlite_full_state_hash = _sqlite_full_state_digest(store.connection)
            bounded_preview, final_selection_status, infeasibility = (
                _selection_from_snapshot(
                    selector_reducer.snapshot,
                    pilot_config=pilot_config,
                    subset_identity=subset_identity,
                    effective_fingerprint=effective_fingerprint,
                    trace=bounded_trace,
                )
            )
            try:
                reference_selection = store.select(
                    input_phase02_manifest_identity=subset_identity,
                    selection_timestamp=BENCHMARK_TIMESTAMP,
                    trace=reference_trace,
                )
                reference_status = "FEASIBLE_AND_RUN"
                reference_infeasibility = None
            except PilotSelectionInfeasibleError as error:
                reference_selection = None
                reference_status = "NOT_APPLICABLE_SUBSET_INFEASIBLE"
                reference_infeasibility = error.privacy_safe_diagnostic()
            row_count = sum(int(item["staging_rows"]) for item in files)
            scientific_trace_divergence = _first_trace_divergence(
                reference_trace,
                bounded_trace,
                include_cursor_diagnostics=False,
            )
            if (
                reference_status != final_selection_status
                or _infeasibility_semantic_key(reference_infeasibility)
                != _infeasibility_semantic_key(infeasibility)
                or scientific_trace_divergence is not None
            ):
                mismatch = _selection_status_mismatch_payload(
                    subset_identity=subset_identity,
                    files=files,
                    row_count=row_count,
                    reference_status=reference_status,
                    bounded_status=final_selection_status,
                    reference_infeasibility=reference_infeasibility,
                    bounded_infeasibility=infeasibility,
                    reference_trace=reference_trace,
                    bounded_trace=bounded_trace,
                )
                _persist_selection_mismatch(
                    output_directory,
                    run_label=run_label,
                    payload=mismatch,
                )
                raise ValueError("PILOT_SELECTION_EQUIVALENCE_FAILURE")
            if reference_selection is not None and bounded_preview is not None:
                selection = reference_selection
                if selection != bounded_preview.selection:
                    mismatch = _selection_mismatch_payload(
                        subset_identity=subset_identity,
                        files=files,
                        row_count=row_count,
                        reference=selection,
                        bounded=bounded_preview.selection,
                        reference_trace=reference_trace,
                        bounded_trace=bounded_trace,
                    )
                    _persist_selection_mismatch(
                        output_directory,
                        run_label=run_label,
                        payload=mismatch,
                    )
                    raise ValueError("PILOT_SELECTION_EQUIVALENCE_FAILURE")
            else:
                selection = None
            output_trace = reference_trace
        finally:
            store.close()
    else:
        reduction = reduce_production_shards_bounded(
            [
                BoundedShardTask(path, str(item["output_sha256"]))
                for item, path in zip(files, paths, strict=True)
            ],
            country_counts=country_counts,
            safety_locations=frozenset(safety_locations),
            contract=contract,
            pilot_config=pilot_config,
            worker_count=worker_count,
        )
        if reduction.reducer.snapshot.safety_locations != set(safety_locations):
            raise ValueError("benchmark safety-location reconciliation failed")
        selector_reducer = reduction.reducer
        checkpoints = list(reduction.checkpoints)
        output_trace = SelectionTrace()
        bounded, final_selection_status, infeasibility = _selection_from_snapshot(
            selector_reducer.snapshot,
            pilot_config=pilot_config,
            subset_identity=subset_identity,
            effective_fingerprint=effective_fingerprint,
            trace=output_trace,
        )
        selection = bounded.selection if bounded is not None else None
        population_group_counts = reduction.reducer.snapshot.group_counts
        if bounded is not None:
            write_compact_selected_state(
                state_path,
                bounded_selection=bounded,
                checkpoints=reduction.checkpoints,
                config=pilot_config,
                classification_contract=contract,
                production_binding_fingerprint=production_binding,
                data_scope="PRODUCTION_BENCHMARK_SUBSET",
            )
    if benchmark_mode == "FINAL_EQUIVALENCE" and selection is None:
        raise ValueError("QUOTA_FEASIBLE_CORPUS_REQUIRED")
    selector_relevant_state_hash, state_counts = bounded_snapshot_state(
        selector_reducer.snapshot
    )
    development_path = output_directory / "development.identities.bin"
    locked_path = output_directory / "locked_evaluation.identities.bin"
    if selection is not None:
        write_identity_set(
            development_path,
            selection.development_ids,
            partition="DEVELOPMENT",
            manifest_identity=subset_identity,
            sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
        )
        write_identity_set(
            locked_path,
            selection.locked_evaluation_ids,
            partition="LOCKED_EVALUATION",
            manifest_identity=subset_identity,
            sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
        )
    cpu_after = resource.getrusage(resource.RUSAGE_SELF)
    child_cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall_seconds = time.perf_counter() - started
    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "benchmark_mode": benchmark_mode,
        "candidate_state_bytes": state_path.stat().st_size if state_path.exists() else 0,
        "development_file_sha256": (
            _sha256(development_path) if development_path.exists() else None
        ),
        "development_identity_digest": (
            selection.seal.development_identity_digest if selection is not None else None
        ),
        "engine": engine,
        "git_commit": os.environ.get("PHASE03_GIT_COMMIT", "UNRECORDED"),
        "input_bytes": sum(path.stat().st_size for path in paths),
        "input_shards": [str(item["output_file"]) for item in files],
        "final_selection_status": final_selection_status,
        "infeasibility": infeasibility,
        "input_kind": input_kind,
        "locked_file_sha256": _sha256(locked_path) if locked_path.exists() else None,
        "locked_identity_digest": (
            selection.seal.locked_evaluation_identity_digest
            if selection is not None
            else None
        ),
        "peak_rss_bytes": _peak_rss_bytes(),
        "per_shard_rows": [
            {"row_count": row_count, "shard": shard_id}
            for shard_id, _, row_count in sorted(checkpoints)
        ],
        "population_strata_digest": _population_strata_digest(
            population_group_counts
        ),
        "phase02_manifest_sha256": _sha256(manifest_path),
        "pyarrow_version": pyarrow.__version__,
        "python_version": platform.python_version(),
        "retained_candidate_count": state_counts["retained_candidate_count"],
        "row_count": sum(int(item["staging_rows"]) for item in files),
        "rows_per_second": sum(int(item["staging_rows"]) for item in files)
        / wall_seconds,
        "selection_trace": [
            _trace_stage_payload(stage) for stage in output_trace.stages
        ],
        "selection_fingerprint": (
            selection.seal.sampling_config_fingerprint if selection is not None else None
        ),
        "selected_state_digest": (
            _selected_state_digest(state_path)
            if selection is not None and state_path.exists()
            else None
        ),
        "selector_relevant_state_hash": selector_relevant_state_hash,
        "shard_count": len(files),
        "state_counts": state_counts,
        "sqlite_full_state_hash": sqlite_full_state_hash,
        "sampling_config_fingerprint": pilot_config.fingerprint(),
        "run_label": run_label,
        "sqlite_settings": sqlite_settings_payload,
        "sqlite_runtime_settings": sqlite_runtime_settings_payload,
        "sqlite_version": __import__("sqlite3").sqlite_version,
        "source_tree_fingerprint": os.environ.get(
            "PHASE03_BENCHMARK_SOURCE_SHA256", "UNRECORDED"
        ),
        "subset_identity": subset_identity,
        "system_cpu_seconds": (
            cpu_after.ru_stime
            - cpu_before.ru_stime
            + child_cpu_after.ru_stime
            - child_cpu_before.ru_stime
        ),
        "temporary_disk_bytes": _directory_bytes(output_directory),
        "temporary_disk_measurement": (
            "MONOTONIC_FINAL_STATE_APPROXIMATES_PEAK"
            if engine in {"baseline-sqlite", "optimized-sqlite"}
            else "FINAL_STATE_ONLY"
        ),
        "user_cpu_seconds": (
            cpu_after.ru_utime
            - cpu_before.ru_utime
            + child_cpu_after.ru_utime
            - child_cpu_before.ru_utime
        ),
        "wall_seconds": wall_seconds,
        "worker_count": worker_count if engine == "bounded-parallel" else 1,
        "duckdb_version": duckdb.__version__,
        "unicode_version": unicodedata.unidata_version,
    }
    _write_json(output_directory / "benchmark_result.json", payload)
    return payload


def construct_quota_feasible_corpus(
    *,
    manifest_path: Path,
    phase01_anomalies_path: Path,
    profile_path: Path,
    output_path: Path,
    worker_count: int,
) -> dict[str, Any]:
    """Select a deterministic strict subset of whole shards for equivalence.

    The independent corpus order is unrelated to the frozen pilot ranks. No
    candidate identities or DEVELOPMENT/LOCKED partition is persisted.
    """

    if worker_count < 1:
        raise ValueError("corpus worker count must be positive")
    manifest = load_phase02_manifest(manifest_path)
    reconciliation = cast(dict[str, Any], manifest.get("reconciliation"))
    if (
        manifest.get("run_id") != "phase02_20260810T173851Z_1349152b"
        or manifest.get("phase02_completion_gate") != "PASS"
        or reconciliation.get("total_rows") != 20_600_000
        or reconciliation.get("distinct_stable_ids") != 20_600_000
        or reconciliation.get("duplicate_stable_ids") != 0
        or len(manifest.get("files", [])) != 206
    ):
        raise ValueError("corpus input is not the authoritative Phase 2 snapshot")
    configuration_binding = _active_corpus_binding(profile_path)
    contract = ProductionSamplingContract()
    pilot_config = proposed_production_pilot_config()
    country_counts = load_country_profile(
        profile_path, manifest_identity=_sha256(manifest_path)
    )
    if sum(country_counts.values()) != 20_600_000:
        raise ValueError("corpus construction requires the production country profile")
    all_safety = load_phase01_safety_locations(phase01_anomalies_path)
    order_domain = b"phase03:pilot-select-equivalence-corpus-v1\0"
    ordered_files = sorted(
        [cast(dict[str, Any], item) for item in manifest["files"]],
        key=lambda item: (
            hashlib.sha256(
                order_domain
                + str(item["output_file"]).encode("utf-8")
                + bytes.fromhex(str(item["output_sha256"]))
            ).digest(),
            str(item["output_file"]).encode("utf-8"),
        ),
    )
    master = ExactBoundedCandidateReducer(pilot_config, track_all_seen_ids=False)
    chosen: list[dict[str, Any]] = []
    final_status = "NOT_APPLICABLE_SUBSET_INFEASIBLE"
    infeasibility: dict[str, int | str | None] | None = None
    for offset in range(0, len(ordered_files), CORPUS_BATCH_SHARDS):
        batch = ordered_files[
            offset : min(offset + CORPUS_BATCH_SHARDS, len(ordered_files) - 1)
        ]
        if not batch:
            break
        # Never execute the frozen final selector over the complete snapshot in
        # a benchmark-corpus construction workflow.
        tasks = []
        batch_source_files = {str(item["source_file"]) for item in batch}
        for item in batch:
            path = manifest_path.parent / str(item["output_file"])
            if (
                not path.is_file()
                or _sha256(path) != item["output_sha256"]
                or not exact_schema_matches(
                    pq.ParquetFile(
                        path, page_checksum_verification=True, pre_buffer=True
                    ).schema_arrow
                )
            ):
                raise ValueError(f"corpus shard identity mismatch: {path.name}")
            tasks.append(BoundedShardTask(path, str(item["output_sha256"])))
        reduction = reduce_production_shards_bounded(
            tasks,
            country_counts=country_counts,
            safety_locations=frozenset(
                location for location in all_safety if location[0] in batch_source_files
            ),
            contract=contract,
            pilot_config=pilot_config,
            worker_count=min(worker_count, len(tasks)),
        )
        master.merge(reduction.reducer.snapshot)
        chosen.extend(batch)
        _, final_status, infeasibility = _selection_from_snapshot(
            master.snapshot,
            pilot_config=pilot_config,
            subset_identity="CORPUS_FEASIBILITY_ONLY",
            effective_fingerprint="CORPUS_FEASIBILITY_ONLY",
        )
        if final_status == "FEASIBLE_AND_RUN":
            break
    if final_status != "FEASIBLE_AND_RUN" or len(chosen) >= 206:
        raise ValueError("NO_NONPRODUCTION_QUOTA_FEASIBLE_CORPUS")
    state_hash, state_counts = bounded_snapshot_state(master.snapshot)
    corpus_files: list[JsonValue] = [
        {
            "output_file": str(item["output_file"]),
            "output_sha256": str(item["output_sha256"]),
        }
        for item in chosen
    ]
    corpus_identity = fingerprint(
        {
            "configuration_binding": configuration_binding,
            "corpus_version": CORPUS_VERSION,
            "files": corpus_files,
            "phase02_manifest_sha256": _sha256(manifest_path),
        }
    )
    payload = {
        "construction_order": "SHA256_PHASE03_CORPUS_V1",
        "configuration_binding": configuration_binding,
        "corpus_identity": corpus_identity,
        "corpus_version": CORPUS_VERSION,
        "files": corpus_files,
        "final_selection_status": final_status,
        "infeasibility": infeasibility,
        "phase02_manifest_sha256": _sha256(manifest_path),
        "row_count": master.snapshot.row_count,
        "selector_relevant_state_hash": state_hash,
        "shard_count": len(chosen),
        "state_counts": state_counts,
    }
    _write_json(output_path, payload)
    return payload


def _portable_primary_occupancy_difference(
    reference_stage: dict[str, Any],
    observed_stage: dict[str, Any],
    *,
    before: bool,
) -> list[dict[str, JsonValue]]:
    field = "primary_group_counts_before" if before else "primary_group_counts"
    reference = {
        str(item["primary_group_sha256"]): int(item["count"])
        for item in cast(list[dict[str, Any]], reference_stage[field])
    }
    observed = {
        str(item["primary_group_sha256"]): int(item["count"])
        for item in cast(list[dict[str, Any]], observed_stage[field])
    }
    return [
        {
            "observed_count": observed.get(primary_hash, 0),
            "primary_group_sha256": primary_hash,
            "reference_count": reference.get(primary_hash, 0),
        }
        for primary_hash in sorted(set(reference) | set(observed))
        if reference.get(primary_hash, 0) != observed.get(primary_hash, 0)
    ]


def _portable_trace_divergence_payload(
    reference_trace: list[dict[str, Any]],
    observed_trace: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for index in range(max(len(reference_trace), len(observed_trace))):
        reference_stage = reference_trace[index] if index < len(reference_trace) else None
        observed_stage = observed_trace[index] if index < len(observed_trace) else None
        if reference_stage is None or observed_stage is None:
            return {
                "differing_fields": ["stage_presence"],
                "first_differing_stage_index": index,
                "observed_stage": observed_stage,
                "reference_stage": reference_stage,
            }
        differing_fields = [
            field
            for field in _SCIENTIFIC_TRACE_FIELDS
            if reference_stage.get(field) != observed_stage.get(field)
        ]
        if differing_fields:
            return {
                "differing_fields": differing_fields,
                "first_differing_stage_index": index,
                "observed_stage": observed_stage,
                "post_stage_primary_occupancy_differences": (
                    _portable_primary_occupancy_difference(
                        reference_stage, observed_stage, before=False
                    )
                ),
                "pre_stage_primary_occupancy_differences": (
                    _portable_primary_occupancy_difference(
                        reference_stage, observed_stage, before=True
                    )
                ),
                "reference_stage": reference_stage,
            }
    return None


def compare_runs(paths: Sequence[Path], output_path: Path) -> dict[str, Any]:
    if len(paths) < 2:
        raise ValueError("at least two benchmark runs are required")
    values = [
        json.loads((path / "benchmark_result.json").read_text(encoding="utf-8"))
        for path in paths
    ]
    if any(value.get("benchmark_version") != BENCHMARK_VERSION for value in values):
        raise ValueError("PILOT_SELECTION_EQUIVALENCE_VERSION_MISMATCH")
    expected_labels = {
        "baseline",
        "optimized",
        "optimized_mmap",
        "bounded_1",
        "bounded_4",
        "bounded_16",
    }
    observed_labels = {str(value.get("run_label")) for value in values}
    if observed_labels != expected_labels or len(values) != len(expected_labels):
        raise ValueError("PILOT_SELECTION_EQUIVALENCE_MATRIX_INCOMPLETE")
    by_label = {str(value["run_label"]): value for value in values}
    expected_engine_workers = {
        "baseline": ("baseline-sqlite", 1),
        "optimized": ("optimized-sqlite", 1),
        "optimized_mmap": ("optimized-sqlite", 1),
        "bounded_1": ("bounded-parallel", 1),
        "bounded_4": ("bounded-parallel", 4),
        "bounded_16": ("bounded-parallel", 16),
    }
    if any(
        (value.get("engine"), value.get("worker_count"))
        != expected_engine_workers[label]
        for label, value in by_label.items()
    ):
        raise ValueError("PILOT_SELECTION_EQUIVALENCE_MATRIX_INCOMPLETE")
    optimized_settings = by_label["optimized"].get("sqlite_settings")
    mmap_settings = by_label["optimized_mmap"].get("sqlite_settings")
    if (
        not isinstance(optimized_settings, dict)
        or optimized_settings.get("mmap_size_bytes") != 0
        or not isinstance(mmap_settings, dict)
        or int(mmap_settings.get("mmap_size_bytes", 0)) <= 0
    ):
        raise ValueError("PILOT_SELECTION_EQUIVALENCE_MATRIX_INCOMPLETE")
    state_fields = (
        "benchmark_version",
        "subset_identity",
        "row_count",
        "input_shards",
        "per_shard_rows",
        "population_strata_digest",
        "selector_relevant_state_hash",
        "state_counts",
        "sampling_config_fingerprint",
        "source_tree_fingerprint",
        "final_selection_status",
        "infeasibility",
        "benchmark_mode",
        "input_kind",
    )
    mismatches: dict[str, Any] = {
        field: [value[field] for value in values]
        for field in state_fields
        if any(value[field] != values[0][field] for value in values[1:])
    }
    sqlite_values = [
        value["sqlite_full_state_hash"]
        for value in values
        if value["engine"] in {"baseline-sqlite", "optimized-sqlite"}
    ]
    if (
        len(sqlite_values) < 2
        or any(not isinstance(value, str) for value in sqlite_values)
        or len(set(sqlite_values)) != 1
    ):
        mismatches["sqlite_full_state_hash"] = sqlite_values
    final_status = str(values[0]["final_selection_status"])
    if final_status == "FEASIBLE_AND_RUN":
        identity_fields = (
            "development_file_sha256",
            "locked_file_sha256",
            "development_identity_digest",
            "locked_identity_digest",
            "selection_fingerprint",
            "selected_state_digest",
        )
        for field in identity_fields:
            if values[0][field] is None or any(
                value[field] != values[0][field] for value in values[1:]
            ):
                mismatches[field] = [value[field] for value in values]
    elif any(value["benchmark_mode"] != "PERFORMANCE_STATE" for value in values):
        mismatches["final_selection_status"] = [
            value["final_selection_status"] for value in values
        ]
    reference_trace = cast(
        list[dict[str, Any]], by_label["baseline"]["selection_trace"]
    )
    trace_divergences = {
        label: divergence
        for label, value in by_label.items()
        if label != "baseline"
        and (
            divergence := _portable_trace_divergence_payload(
                reference_trace,
                cast(list[dict[str, Any]], value["selection_trace"]),
            )
        )
        is not None
    }
    if trace_divergences:
        mismatches["scientific_selection_trace"] = trace_divergences
    if mismatches:
        failure_payload = {
            "benchmark_version": BENCHMARK_VERSION,
            "field_mismatches": mismatches,
            "mismatch_kind": "CROSS_ENGINE_EQUIVALENCE",
            "row_count": values[0]["row_count"],
            "shards": [
                {"output_file": shard}
                for shard in cast(list[str], values[0]["input_shards"])
            ],
            "subset_identity": values[0]["subset_identity"],
        }
        _write_json(output_path, failure_payload)
        _persist_selection_mismatch(
            output_path.parent,
            run_label="cross_engine_compare",
            payload=failure_payload,
        )
        raise ValueError("PILOT_SELECTION_EQUIVALENCE_FAILURE")
    equivalence = (
        "FINAL_SELECTION_BYTE_IDENTICAL"
        if final_status == "FEASIBLE_AND_RUN"
        else "PRESELECTION_STATE_IDENTICAL_FINAL_SELECTION_NOT_APPLICABLE"
    )
    payload = {
        "benchmark_version": BENCHMARK_VERSION,
        "engines": [value["engine"] for value in values],
        "equivalence": equivalence,
        "final_selection_equivalence_proven": final_status == "FEASIBLE_AND_RUN",
        "final_selection_status": final_status,
        "state": {field: values[0][field] for field in state_fields},
        "runs": values,
    }
    _write_json(output_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cluster-only Phase 3 pilot-select equivalence benchmark"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument(
        "--engine",
        choices=("baseline-sqlite", "optimized-sqlite", "bounded-parallel"),
        required=True,
    )
    run.add_argument("--run-label", required=True)
    run.add_argument("--phase02-manifest", type=Path, required=True)
    run.add_argument("--phase01-anomalies", type=Path, required=True)
    run.add_argument("--profile", type=Path, required=True)
    input_group = run.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--shard-count", type=int)
    input_group.add_argument("--corpus-manifest", type=Path)
    run.add_argument(
        "--benchmark-mode",
        choices=("PERFORMANCE_STATE", "FINAL_EQUIVALENCE"),
        required=True,
    )
    run.add_argument("--output-directory", type=Path, required=True)
    run.add_argument("--worker-count", type=int, default=1)
    run.add_argument("--sqlite-cache-size-mib", type=int, default=8_192)
    run.add_argument("--sqlite-mmap-size-mib", type=int, default=0)
    run.add_argument("--sqlite-insertion-batch-size", type=int, default=10_000)
    corpus = subparsers.add_parser("construct-corpus")
    corpus.add_argument("--phase02-manifest", type=Path, required=True)
    corpus.add_argument("--phase01-anomalies", type=Path, required=True)
    corpus.add_argument("--profile", type=Path, required=True)
    corpus.add_argument("--output", type=Path, required=True)
    corpus.add_argument("--worker-count", type=int, default=16)
    compare = subparsers.add_parser("compare")
    compare.add_argument("--run", type=Path, action="append", required=True)
    compare.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_goethe_nhr_slurm("phase03.pilot-select-benchmark")
    enforce_runtime_contract()
    if args.command == "run":
        payload = run_engine(
            run_label=args.run_label,
            engine=args.engine,
            manifest_path=args.phase02_manifest,
            phase01_anomalies_path=args.phase01_anomalies,
            profile_path=args.profile,
            shard_count=args.shard_count,
            corpus_manifest_path=args.corpus_manifest,
            benchmark_mode=args.benchmark_mode,
            output_directory=args.output_directory,
            worker_count=args.worker_count,
            sqlite_cache_size_mib=args.sqlite_cache_size_mib,
            sqlite_mmap_size_mib=args.sqlite_mmap_size_mib,
            sqlite_insertion_batch_size=args.sqlite_insertion_batch_size,
        )
    elif args.command == "construct-corpus":
        payload = construct_quota_feasible_corpus(
            manifest_path=args.phase02_manifest,
            phase01_anomalies_path=args.phase01_anomalies,
            profile_path=args.profile,
            output_path=args.output,
            worker_count=args.worker_count,
        )
    else:
        payload = compare_runs(args.run, args.output)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from ..execution_policy import require_goethe_nhr_slurm
from ..phase02.fingerprints import canonical_json_bytes, fingerprint
from ..phase02.schema import exact_schema_matches
from .config import Phase03Config
from .engine import Phase03Engine
from .errors import Phase03Error
from .pilot_runner import (
    SAMPLING_COLUMNS,
    Phase01SafetyLocationTracker,
    ProductionSamplingContract,
    ReviewCandidate,
    SQLiteCandidateStoreSettings,
    SQLitePilotCandidateStore,
    classify_sampling_row_v1,
    effective_sampling_fingerprint,
    population_country_counts,
    proposed_production_pilot_config,
    require_pilot_free_space,
    select_development_review_sample_plan,
    write_review_artifacts,
    write_identity_set,
    write_pilot_seal,
)
from .pilot_selection_runtime import (
    BoundedShardTask,
    reduce_production_shards_bounded,
    write_compact_selected_state,
)
from .references import CountryReference, ScriptReference
from .rules import RuleRegistry
from .schema import exact_core_schema_matches, exact_evidence_schema_matches
from .writer import ShardWriteResult, write_validate_and_promote_synthetic_shard

COUNTRY_PROFILE_VERSION = "phase03_country_population_profile_v1"
PILOT_ORCHESTRATION_VERSION = "phase03_pilot_orchestration_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phase02_manifest_identity(path: Path) -> str:
    return _sha256(path)


def load_phase02_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Phase03Error("PHASE02_MANIFEST_READ_FAILURE", type(error).__name__) from error
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise Phase03Error("PHASE02_MANIFEST_SCHEMA_MISMATCH")
    return cast(dict[str, Any], value)


def validate_explicit_phase02_inputs(
    manifest_path: Path,
    input_paths: Sequence[Path],
    *,
    production: bool,
) -> tuple[dict[str, Any], str]:
    if production:
        require_goethe_nhr_slurm("phase03.production-snapshot-validation")
    manifest = load_phase02_manifest(manifest_path)
    files = manifest["files"]
    expected = {Path(str(item["output_file"])).name: item for item in files}
    observed = {path.name: path for path in input_paths}
    if len(observed) != len(input_paths) or set(observed) != set(expected):
        raise Phase03Error("PHASE02_EXPLICIT_FILE_SET_MISMATCH")
    reconciliation = manifest.get("reconciliation")
    if production and (
        len(input_paths) != 206
        or manifest.get("run_id") != "phase02_20260810T173851Z_1349152b"
        or manifest.get("phase02_completion_gate") != "PASS"
        or not isinstance(reconciliation, dict)
        or reconciliation.get("status") != "PASS"
        or reconciliation.get("file_count") != 206
        or reconciliation.get("total_rows") != 20_600_000
        or reconciliation.get("distinct_stable_ids") != 20_600_000
        or reconciliation.get("duplicate_stable_ids") != 0
        or any(
            item.get("status") != "PASS"
            or item.get("staging_rows") != 100_000
            for item in files
        )
    ):
        raise Phase03Error("PHASE02_PRODUCTION_SNAPSHOT_MISMATCH")
    for name, path in sorted(observed.items()):
        item = expected[name]
        if not path.is_file() or _sha256(path) != item.get("output_sha256"):
            raise Phase03Error("PHASE02_SHARD_IDENTITY_MISMATCH", name)
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        if not exact_schema_matches(parquet.schema_arrow):
            raise Phase03Error("PHASE02_SCHEMA_MISMATCH", name)
    return manifest, phase02_manifest_identity(manifest_path)


def _iter_columns(
    paths: Sequence[Path], columns: Sequence[str], *, batch_rows: int = 25_000
) -> Iterator[dict[str, Any]]:
    for path in paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        for batch in parquet.iter_batches(
            batch_size=batch_rows, columns=list(columns), use_threads=False
        ):
            yield from batch.to_pylist()


def write_country_profile(
    manifest_path: Path,
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    country_reference: CountryReference,
    production: bool,
) -> dict[str, Any]:
    if production:
        require_goethe_nhr_slurm("phase03.pilot-profile")
    _, manifest_identity = validate_explicit_phase02_inputs(
        manifest_path, input_paths, production=production
    )
    counts = population_country_counts(
        _iter_columns(input_paths, ("country_iso_code",)), country_reference
    )
    payload: dict[str, Any] = {
        "profile_version": COUNTRY_PROFILE_VERSION,
        "phase02_manifest_identity": manifest_identity,
        "country_reference_version": country_reference.version,
        "row_count": sum(counts.values()),
        "group_count": len(counts),
        "counts": dict(sorted(counts.items())),
    }
    if production and payload["row_count"] != 20_600_000:
        raise Phase03Error("COUNTRY_PROFILE_COUNT_MISMATCH")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    if output_path.exists() or temporary.exists():
        raise FileExistsError(output_path)
    temporary.write_bytes(canonical_json_bytes(payload) + b"\n")
    temporary.chmod(0o600)
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    return payload


def load_country_profile(path: Path, *, manifest_identity: str) -> Counter[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if (
        value.get("profile_version") != COUNTRY_PROFILE_VERSION
        or value.get("phase02_manifest_identity") != manifest_identity
        or not isinstance(value.get("counts"), dict)
    ):
        raise Phase03Error("COUNTRY_PROFILE_IDENTITY_MISMATCH")
    counts = Counter({str(key): int(count) for key, count in value["counts"].items()})
    if sum(counts.values()) != int(value.get("row_count", -1)):
        raise Phase03Error("COUNTRY_PROFILE_COUNT_MISMATCH")
    return counts


def select_production_pilot(
    *,
    manifest_path: Path,
    input_paths: Sequence[Path],
    country_profile_path: Path,
    phase01_anomalies_path: Path,
    state_path: Path,
    output_directory: Path,
    country_reference: CountryReference,
    script_reference: ScriptReference,
    rule_registry: RuleRegistry,
    selection_timestamp: str,
    git_commit: str,
    phase03_configuration_fingerprint: str,
    reference_configuration_fingerprint: str,
    production: bool,
    selection_engine: str = "baseline-sqlite",
    worker_count: int = 1,
    sqlite_cache_size_mib: int = 8_192,
    sqlite_mmap_size_mib: int = 0,
    sqlite_insertion_batch_size: int = 10_000,
) -> dict[str, Any]:
    if production:
        require_goethe_nhr_slurm("phase03.pilot-select")
    contract = ProductionSamplingContract()
    contract.validate(production=production)
    if selection_engine not in {
        "baseline-sqlite",
        "optimized-sqlite",
        "bounded-parallel",
    }:
        raise ValueError("unsupported pilot selection engine")
    if worker_count < 1:
        raise ValueError("pilot selection worker count must be positive")
    if production:
        require_pilot_free_space(state_path, minimum_free_bytes=contract.minimum_free_bytes)
    manifest, manifest_identity = validate_explicit_phase02_inputs(
        manifest_path, input_paths, production=production
    )
    country_counts = load_country_profile(
        country_profile_path, manifest_identity=manifest_identity
    )
    safety = Phase01SafetyLocationTracker.from_report(phase01_anomalies_path)
    production_binding = fingerprint(
        {
            "manifest_identity": manifest_identity,
            "country_reference_id": country_reference.version,
            "country_reference_sha256": (
                country_reference.assignment_manifest.artifact_sha256
            ),
            "script_reference_id": script_reference.version,
            "script_reference_sha256": script_reference.manifest.artifact_sha256,
            "rule_registry_version": rule_registry.registry_version,
            "rule_registry_sha256": rule_registry.fingerprint,
            "phase03_configuration_fingerprint": phase03_configuration_fingerprint,
        }
    )
    pilot_config = proposed_production_pilot_config()
    file_identities = {
        Path(str(item["output_file"])).name: str(item["output_sha256"])
        for item in manifest["files"]
    }
    pass2_rows = 0
    retained_candidates: int | None = None
    if selection_engine in {"baseline-sqlite", "optimized-sqlite"}:
        sqlite_settings = (
            SQLiteCandidateStoreSettings.baseline()
            if selection_engine == "baseline-sqlite"
            else SQLiteCandidateStoreSettings.optimized(
                cache_size_mib=sqlite_cache_size_mib,
                mmap_size_mib=sqlite_mmap_size_mib,
                insertion_batch_size=sqlite_insertion_batch_size,
            )
        )
        store = SQLitePilotCandidateStore(
            state_path,
            config=pilot_config,
            settings=sqlite_settings,
            data_scope="PRODUCTION" if production else "SYNTHETIC_ONLY",
            classification_contract=contract if production else None,
            classification_contract_fingerprint=contract.fingerprint(),
            production_binding_fingerprint=production_binding if production else None,
        )
        try:
            for path in input_paths:
                parquet = pq.ParquetFile(
                    path, page_checksum_verification=True, pre_buffer=True
                )
                shard_identity = file_identities[path.name]

                def candidates() -> Iterator[Any]:
                    for batch in parquet.iter_batches(
                        batch_size=25_000,
                        columns=list(SAMPLING_COLUMNS),
                        use_threads=False,
                    ):
                        for row in batch.to_pylist():
                            targeted = safety.observe(
                                str(row["source_file"]),
                                int(row["source_logical_record_number"]),
                            )
                            yield classify_sampling_row_v1(
                                row,
                                contract=contract,
                                country_reference=country_reference,
                                script_reference=script_reference,
                                rule_registry=rule_registry,
                                country_counts=country_counts,
                                targeted_safety_case=targeted,
                            )

                shard_rows, _ = store.ingest_shard(
                    path.name,
                    shard_identity,
                    candidates(),
                    batch_size=sqlite_settings.insertion_batch_size,
                )
                pass2_rows += shard_rows
                print(
                    f"pilot_select_shard_complete={path.name} rows={shard_rows}",
                    file=sys.stderr,
                    flush=True,
                )
            if store.safety_locations() != set(safety.expected):
                raise Phase03Error(
                    "PHASE01_SAFETY_LOCATION_RECONCILIATION_FAILED"
                )
            store.validate_integrity()
            selection = store.select(
                input_phase02_manifest_identity=manifest_identity,
                selection_timestamp=selection_timestamp,
            )
            sqlite_runtime_settings = store.sqlite_runtime_settings()
        finally:
            store.close()
    else:
        if not production:
            raise ValueError("bounded production orchestration requires production=True")
        reconciliation = cast(dict[str, Any], manifest["reconciliation"])
        if (
            reconciliation.get("distinct_stable_ids")
            != reconciliation.get("total_rows")
            or reconciliation.get("duplicate_stable_ids") != 0
        ):
            raise Phase03Error("PHASE02_STABLE_ID_UNIQUENESS_NOT_PROVEN")
        reduction = reduce_production_shards_bounded(
            [
                BoundedShardTask(path, file_identities[path.name])
                for path in input_paths
            ],
            country_counts=country_counts,
            safety_locations=frozenset(safety.expected),
            contract=contract,
            pilot_config=pilot_config,
            worker_count=worker_count,
        )
        pass2_rows = reduction.reducer.snapshot.row_count
        if reduction.reducer.snapshot.safety_locations != set(safety.expected):
            raise Phase03Error("PHASE01_SAFETY_LOCATION_RECONCILIATION_FAILED")
        classification_fingerprint = fingerprint(
            {
                "sampling_contract_fingerprint": contract.fingerprint(),
                "production_binding_fingerprint": production_binding,
            }
        )
        bounded = reduction.reducer.select(
            input_phase02_manifest_identity=manifest_identity,
            selection_timestamp=selection_timestamp,
            effective_sampling_fingerprint=effective_sampling_fingerprint(
                classification_contract_fingerprint=classification_fingerprint,
                config=pilot_config,
            ),
        )
        selection = bounded.selection
        retained_candidates = bounded.retained_candidate_count
        write_compact_selected_state(
            state_path,
            bounded_selection=bounded,
            checkpoints=reduction.checkpoints,
            config=pilot_config,
            classification_contract=contract,
            production_binding_fingerprint=production_binding,
        )
        sqlite_runtime_settings = None
    if pass2_rows != sum(country_counts.values()) or (
        production and pass2_rows != 20_600_000
    ):
        raise Phase03Error("PILOT_PASS_ROW_COUNT_MISMATCH")
    output_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_directory.chmod(0o700)
    development_path = output_directory / "development.identities.bin"
    locked_path = output_directory / "locked_evaluation.identities.bin"
    write_identity_set(
        development_path,
        selection.development_ids,
        partition="DEVELOPMENT",
        manifest_identity=manifest_identity,
        sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
    )
    write_identity_set(
        locked_path,
        selection.locked_evaluation_ids,
        partition="LOCKED_EVALUATION",
        manifest_identity=manifest_identity,
        sampling_config_fingerprint=selection.seal.sampling_config_fingerprint,
    )
    write_pilot_seal(
        output_directory / "pilot_seal.json",
        selection.seal,
        sampler_version=PILOT_ORCHESTRATION_VERSION,
        git_commit=git_commit,
        reference_configuration_fingerprint=reference_configuration_fingerprint,
        sampling_contract=contract,
        phase03_configuration_fingerprint=phase03_configuration_fingerprint,
        rule_registry_fingerprint=rule_registry.fingerprint,
    )
    return {
        "status": "PASS",
        "development_count": len(selection.development_ids),
        "locked_evaluation_count": len(selection.locked_evaluation_ids),
        "disjoint": set(selection.development_ids).isdisjoint(selection.locked_evaluation_ids),
        "pilot_seal": selection.seal.portable_dict(),
        "selection_engine": selection_engine,
        "worker_count": worker_count if selection_engine == "bounded-parallel" else 1,
        "retained_candidate_count": retained_candidates,
        "sqlite_runtime_settings": sqlite_runtime_settings,
    }


def transform_development_payload(
    input_path: Path,
    output_directory: Path,
    *,
    engine: Phase03Engine,
    config: Phase03Config,
    metadata: Mapping[str, str],
    expected_development_ids: set[bytes],
) -> ShardWriteResult:
    parquet = pq.ParquetFile(input_path, page_checksum_verification=True, pre_buffer=True)
    if not exact_schema_matches(parquet.schema_arrow):
        raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
    rows = parquet.read(use_threads=False).to_pylist()
    observed_ids = {bytes(row["stable_source_row_id_v1"]) for row in rows}
    if (
        len(rows) != 8_000
        or len(observed_ids) != len(rows)
        or observed_ids != expected_development_ids
    ):
        raise Phase03Error("DEVELOPMENT_PAYLOAD_COUNT_MISMATCH", str(len(rows)))
    results = [engine.transform(row) for row in rows]
    core_rows = [result.core_row for result in results]
    evidence_rows = [evidence for result in results for evidence in result.evidence_rows]
    work = output_directory / ".in_progress"
    core = output_directory / "core" / "development.parquet"
    evidence = output_directory / "evidence" / "development.parquet"
    work.mkdir(parents=True, exist_ok=False, mode=0o700)
    return write_validate_and_promote_synthetic_shard(
        core_rows=core_rows,
        evidence_rows=evidence_rows,
        temporary_core=work / "core.parquet.tmp",
        temporary_evidence=work / "evidence.parquet.tmp",
        final_core=core,
        final_evidence=evidence,
        config=config,
        metadata=dict(metadata),
    )


def build_review_candidates(
    *,
    state_path: Path,
    core_path: Path,
    evidence_path: Path,
    development_ids: set[bytes],
) -> list[ReviewCandidate]:
    core_file = pq.ParquetFile(core_path, page_checksum_verification=True, pre_buffer=True)
    evidence_file = pq.ParquetFile(
        evidence_path, page_checksum_verification=True, pre_buffer=True
    )
    if not exact_core_schema_matches(core_file.schema_arrow):
        raise Phase03Error("PHASE03_CORE_SCHEMA_MISMATCH")
    if not exact_evidence_schema_matches(evidence_file.schema_arrow):
        raise Phase03Error("PHASE03_EVIDENCE_SCHEMA_MISMATCH")
    core_rows = core_file.read(use_threads=False).to_pylist()
    core_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in core_rows}
    if set(core_by_id) != development_ids or len(core_rows) != len(development_ids):
        raise Phase03Error("DEVELOPMENT_CORE_IDENTITY_MISMATCH")
    evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    for row in evidence_file.read(use_threads=False).to_pylist():
        identity = bytes(row["stable_source_row_id_v1"])
        if identity not in development_ids:
            raise Phase03Error("LOCKED_OR_UNKNOWN_EVIDENCE_IDENTITY")
        evidence_by_id.setdefault(identity, []).append(row)

    connection = sqlite3.connect(f"file:{state_path}?mode=ro", uri=True)
    memberships: dict[bytes, dict[str, str]] = {
        identity: {} for identity in development_ids
    }
    try:
        targeted_ids = {
            bytes(identity)
            for (identity,) in connection.execute(
                "SELECT stable_id FROM candidate WHERE targeted=1"
            )
            if bytes(identity) in development_ids
        }
        for dimension, category, identity in connection.execute(
            "SELECT dimension, category, stable_id FROM membership ORDER BY dimension, category, stable_id"
        ):
            key = bytes(identity)
            if key in memberships:
                memberships[key][str(dimension)] = str(category)
    finally:
        connection.close()

    result: list[ReviewCandidate] = []
    for identity in sorted(development_ids):
        core = core_by_id[identity]
        sampling = memberships[identity]
        strata = {
            "primary_country_cohort": sampling.get("country_cohort", "UNKNOWN"),
            "structured_completeness": sampling.get(
                "structured_completeness", "UNKNOWN"
            ),
            "script_category": sampling.get("script_category", "UNKNOWN"),
            "address_parse_status": str(core["address_parse_status"]),
            "diagnostic_evaluation_status": str(
                core["diagnostic_evaluation_status"]
            ),
        }
        relationships = {
            str(value["relationship"])
            for value in core["native_non_native_relationships"]
        }
        diagnostics = {
            str(value)
            for name in (
                "address_diagnostic_flags",
                "postcode_diagnostic_flags",
                "skipped_oversized_fields",
            )
            for value in core[name]
        }
        evidence = evidence_by_id.get(identity, [])
        rule_ids = {str(row["rule_id"]) for row in evidence if row["rule_id"]}
        review_cases = {
            "NATIVE_NON_NATIVE_DIFFERENCE": bool(
                relationships - {"EXACT_EQUAL", "NFC_EQUAL", "BOTH_MISSING"}
            ),
            "COUNTRY_REFERENCE_CASE": str(core["country_parse_method"])
            != "UNRESOLVED",
            "PO_BOX_CASE": core["is_po_box"] is True
            or sampling.get("marker_po_box") == "PO_BOX_MARKER_PRESENT",
            "UNIT_FLOOR_BUILDING_CASE": any(
                core[name] is not None
                for name in ("unit_clean", "floor_clean", "building_clean")
            )
            or any(
                sampling.get(name, "").endswith("_MARKER_PRESENT")
                for name in ("marker_unit", "marker_floor", "marker_building")
            ),
            "ORGANIZATION_CASE": core["organization_clean"] is not None
            or sampling.get("marker_organization")
            == "ORGANIZATION_MARKER_PRESENT",
            "SHADOW_HOUSE_CANDIDATE": "HOUSE_NUMBER_EDGE_CANDIDATE_V1" in rule_ids
            or sampling.get("shadow_house_candidate")
            == "SHADOW_HOUSE_CANDIDATE_PRESENT",
            "PLACEHOLDER_LIKE_CASE": any("PLACEHOLDER" in value for value in diagnostics)
            or any("AMBIGUOUS" in value for value in sampling.values()),
            "OVERSIZED_OR_SAFETY_CASE": bool(core["skipped_oversized_fields"])
            or identity in targeted_ids,
        }
        for category, present in review_cases.items():
            if present:
                strata[f"review_case:{category}"] = "TRUE"
        result.append(ReviewCandidate(identity, strata))
    return result


def materialize_development_review(
    *,
    state_path: Path,
    development_payload_path: Path,
    core_path: Path,
    evidence_path: Path,
    development_ids: set[bytes],
    output_directory: Path,
    pilot_version: str,
) -> dict[str, Any]:
    candidates = build_review_candidates(
        state_path=state_path,
        core_path=core_path,
        evidence_path=evidence_path,
        development_ids=development_ids,
    )
    selection = select_development_review_sample_plan(candidates)
    selected = set(selection.review_ids)
    payload = pq.ParquetFile(
        development_payload_path, page_checksum_verification=True, pre_buffer=True
    ).read(use_threads=False)
    if not exact_schema_matches(payload.schema):
        raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
    core_rows = pq.ParquetFile(
        core_path, page_checksum_verification=True, pre_buffer=True
    ).read(use_threads=False).to_pylist()
    evidence_rows = pq.ParquetFile(
        evidence_path, page_checksum_verification=True, pre_buffer=True
    ).read(use_threads=False).to_pylist()
    core_by_id = {bytes(row["stable_source_row_id_v1"]): row for row in core_rows}
    evidence_by_id: dict[bytes, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        evidence_by_id.setdefault(bytes(row["stable_source_row_id_v1"]), []).append(row)

    def json_safe(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.hex()
        if isinstance(value, list):
            return [json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        return value

    protected_rows = []
    for row in payload.to_pylist():
        identity = bytes(row["stable_source_row_id_v1"])
        if identity not in selected:
            continue
        protected_rows.append(
            {
                **row,
                "phase03_core_json": json.dumps(
                    json_safe(core_by_id[identity]), sort_keys=True, separators=(",", ":")
                ),
                "phase03_evidence_json": json.dumps(
                    json_safe(evidence_by_id.get(identity, [])),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    if len(protected_rows) != len(selected):
        raise Phase03Error("REVIEW_CONTEXT_IDENTITY_MISMATCH")
    context, labels = write_review_artifacts(
        output_directory,
        protected_rows=protected_rows,
        review_ids=selection.review_ids,
        independent_double_review_ids=selection.independent_double_review_ids,
        pilot_version=pilot_version,
    )
    return {
        "status": "PASS",
        "review_count": len(selection.review_ids),
        "broad_count": len(selection.broad_representation_ids),
        "targeted_added_count": len(selection.targeted_ids),
        "double_review_count": len(selection.independent_double_review_ids),
        "diagnostics": list(selection.diagnostics),
        "protected_context_path": _review_artifact_reference(
            output_directory, context
        ),
        "portable_labels_path": _review_artifact_reference(output_directory, labels),
    }


def _review_artifact_reference(output_directory: Path, artifact_path: Path) -> str:
    """Return a promotion-stable artifact reference relative to the review parent."""
    try:
        reference = artifact_path.relative_to(output_directory.parent)
    except ValueError as error:
        raise ValueError("review artifact is outside its output directory") from error
    if (
        reference.is_absolute()
        or not reference.parts
        or reference.parts[0] != output_directory.name
        or ".in_progress" in reference.parts
        or ".." in reference.parts
    ):
        raise ValueError("review artifact reference is not promotion-stable")
    return reference.as_posix()

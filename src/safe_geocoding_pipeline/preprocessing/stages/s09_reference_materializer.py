"""Stage 9 controlled DEVELOPMENT materialization and immutable validation.

No production or local protected mode exists. Synthetic tests exercise the
lower-level functions with invented, typed Stage 8 projections only.
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import duckdb

from ...execution_policy import require_goethe_nhr_slurm
from . import s09_reference_contract as c
from . import s09_reference_coverage as coverage
from . import s09_reference_evaluator as evaluator
from . import s09_reference_execution as execution
from . import s09_reference_index as index
from . import s09_reference_input as upstream
from . import s09_reference_io as io
from . import s09_reference_pack as pack
from . import s09_reference_postal as postal
from . import s09_reference_publication as publication
from . import s09_reference_validation as validation


CONTROLLED_ROOT = Path("/work/footprint/donyadidegan/safe_geocoding_pipeline")
PROTECTED_RELATIONS = (
    "candidate_reference_evidence",
    "reference_match_member",
    "coverage_summary",
)


@dataclass(frozen=True)
class Stage09Config:
    stage08_root: Path
    reference_raw_root: Path
    reference_lock: Path
    reference_pack_root: Path
    output_directory: Path
    execution_git_sha: str
    reference_pack_manifest_sha256: str | None = None
    expected_manifest_sha256: str | None = None
    resume_work_root: Path | None = None
    duckdb_memory_limit: str = "8GB"
    threads: int = 4

    def validate(self) -> None:
        require_goethe_nhr_slurm("stage09-offline-reference-evidence")
        c.require_runtime()
        c.require(
            bool(re.fullmatch("[0-9a-f]{40}", self.execution_git_sha)),
            "EXECUTABLE_SHA_INVALID",
        )
        c.require(
            self.threads == 4 and self.duckdb_memory_limit == "8GB",
            "REVIEWED_DEVELOPMENT_RESOURCES_REQUIRED",
        )
        for path in (
            self.stage08_root,
            self.reference_raw_root,
            self.reference_lock,
            self.reference_pack_root,
            self.output_directory,
            *((self.resume_work_root,) if self.resume_work_root is not None else ()),
        ):
            upstream.reject_protected_scope_path(path)
            c.require(
                path.resolve().is_relative_to(CONTROLLED_ROOT.resolve()),
                "PERSONAL_CONTROLLED_PATH_REQUIRED",
            )
        inputs = (
            self.stage08_root.resolve(),
            self.reference_raw_root.resolve(),
            self.reference_pack_root.resolve(),
        )
        output = self.output_directory.resolve()
        # Publication paths must already be canonical below the configured
        # anchor. Never erase a prohibited symlink by resolving the target.
        publication.check_parent(self.output_directory)
        publication.check_parent(self.reference_pack_root)
        for target in (self.output_directory, self.reference_pack_root):
            c.require(not target.is_symlink(), "PUBLICATION_SYMLINK_PROHIBITED")
        c.require(
            all(
                not output.is_relative_to(path) and not path.is_relative_to(output)
                for path in inputs
            ),
            "OUTPUT_INPUT_PATH_OVERLAP_PROHIBITED",
        )
        c.require(
            not inputs[2].is_relative_to(inputs[1])
            and not inputs[1].is_relative_to(inputs[2]),
            "REFERENCE_RAW_INDEX_PATH_OVERLAP_PROHIBITED",
        )
        repository = Path(__file__).resolve().parents[4]
        try:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repository,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            branch = subprocess.run(
                ["git", "symbolic-ref", "-q", "HEAD"],
                cwd=repository,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError):
            raise c.Stage09Error("EXECUTABLE_GIT_VERIFICATION_FAILED") from None
        c.require(
            head == self.execution_git_sha and not status and branch.returncode == 1,
            "CLEAN_EXACT_DETACHED_EXECUTABLE_REQUIRED",
        )
        c.require(
            c.sha256_file(
                repository / "docs/stages/STAGE09_OFFLINE_REFERENCE_EVIDENCE.md"
            )
            == c.DESIGN_SHA256,
            "FROZEN_STAGE09_DESIGN_CHANGED",
        )
        # Includes full reversed-shard validation replay and preserved work.
        # Operational headroom, not a changed scientific profile or population.
        c.require(
            shutil.disk_usage(self.output_directory.parent).free >= 256 * 1024**3,
            "DEVELOPMENT_DISK_RESERVE_INSUFFICIENT",
        )


@contextmanager
def offline_network() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise c.Stage09Error("STAGE09_NETWORK_ACCESS_PROHIBITED")

    with (
        patch.object(socket.socket, "connect", blocked),
        patch.object(socket.socket, "connect_ex", blocked),
        patch.object(socket, "create_connection", blocked),
        patch.object(socket, "getaddrinfo", blocked),
    ):
        yield


def scientific_profile(
    input_binding: bytes, public_manifest: Mapping[str, Any]
) -> bytes:
    return c.identity(
        "PROFILE",
        (
            c.PROFILE_VERSION,
            c.contract_fingerprint(),
            c.schema_bundle_fingerprint(),
            c.catalog_fingerprint(),
            c.normalization_fingerprint(),
            c.semantics_fingerprint(),
            c.SEMANTIC_RUNTIME,
            bytes.fromhex(c.LOCK_SHA256),
            bytes.fromhex(public_manifest["logical_sha256"]),
            tuple(
                (r["name"], bytes.fromhex(r["logical_sha256"]))
                for r in public_manifest["relations"]
            ),
            input_binding,
        ),
    )


def dataset_fingerprint(
    profile: bytes,
    relations: list[dict[str, Any]],
    public_logical: str,
    occurrence_logical: str,
) -> bytes:
    return c.identity(
        "DATASET",
        (
            profile,
            tuple(
                (
                    r["name"],
                    bytes.fromhex(r["schema_sha256"]),
                    r["row_count"],
                    bytes.fromhex(r["logical_sha256"]),
                )
                for r in sorted(relations, key=lambda r: r["name"])
            ),
            bytes.fromhex(public_logical),
            bytes.fromhex(occurrence_logical),
        ),
    )


def _public_paths(root: Path, manifest: Mapping[str, Any]) -> dict[str, list[Path]]:
    return {
        r["name"]: [pack.confined(root, f["relative_path"]) for f in r["files"]]
        for r in manifest["relations"]
    }


def _small_view(
    root: Path,
    public_manifest: Mapping[str, Any],
    raw: pack.PublicInputs,
    connection: duckdb.DuckDBPyConnection,
) -> evaluator.SmallReferenceView:
    paths = _public_paths(root, public_manifest)
    registry = list(io.parquet_rows(paths["reference_registry"]))
    capabilities = [
        row
        for row in io.parquet_rows(paths["reference_capability"])
        if evaluator.runtime_capability(row)
    ]
    # Read the small locked metadata again, rather than deserializing 1.8M
    # GeoNames objects to select the bounded ISO/metadata subset.
    iso, metadata = raw.small_objects()
    return evaluator.SmallReferenceView(
        registry, capabilities, iso + metadata, connection=connection
    )


def _register_inputs(
    db: duckdb.DuckDBPyConnection, accepted: upstream.AcceptedStage08
) -> None:
    accepted.register_views(db)


def _relation_paths(root: Path, record: Mapping[str, Any]) -> list[Path]:
    return [root / r["relative_path"] for r in record["files"]]


def _canonical_protected(
    db: duckdb.DuckDBPyConnection, root: Path, name: str, paths: list[Path]
) -> dict[str, Any]:
    parent = root / name
    parent.mkdir(mode=0o700)
    result = io.canonicalize(
        db,
        name,
        paths,
        parent / "data",
        collapse_exact_duplicates=name == "reference_match_member",
    )
    for record in result["files"]:
        record["relative_path"] = name + "/" + record["relative_path"]
    return result


def _metadata_payloads(
    profile: bytes,
    accepted: upstream.AcceptedStage08,
    public_root: Path,
    public_manifest_sha: str,
    public_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "stage09_schema_contract.json": {
            "contract": c.CONTRACT_VERSION,
            "profile": c.PROFILE_VERSION,
            "schema": c.SCHEMA_VERSION,
            "contract_sha256": c.contract_fingerprint().hex(),
            "profile_sha256": profile.hex(),
            "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
            "normalization_sha256": c.normalization_fingerprint().hex(),
            "semantics_sha256": c.semantics_fingerprint().hex(),
            "schemas": {name: c.schema_fingerprint(name).hex() for name in c.RELATIONS},
            "stage08_binding": dict(accepted.binding),
            "stage08_binding_sha256": accepted.fingerprint.hex(),
        },
        "stage09_question_catalog.json": {
            "catalog_sha256": c.catalog_fingerprint().hex(),
            "catalog": [q.as_tuple() for q in c.CATALOG],
        },
        "stage09_reference_pack_binding.json": {
            "lock_sha256": c.LOCK_SHA256,
            "public_pack_path": str(public_root),
            "manifest_sha256": public_manifest_sha,
            "logical_sha256": public_manifest["logical_sha256"],
            "reference_relations": public_manifest["relations"],
            "reference_index": public_manifest["reference_index"],
        },
    }


def _build_candidate(
    root: Path,
    work: Path,
    config: Stage09Config,
    accepted: upstream.AcceptedStage08,
    raw: pack.PublicInputs,
    public_manifest: Mapping[str, Any],
    public_sha: str,
) -> Mapping[str, Any]:
    started = time.monotonic()
    profile = scientific_profile(accepted.fingerprint, public_manifest)
    logical = bytes.fromhex(accepted.binding["stage08_logical_dataset_sha256"])
    postal_paths = [
        config.reference_pack_root / f["relative_path"]
        for f in public_manifest["reference_index"]["files"]
    ]
    checkpoints = []
    shard_paths: dict[str, list[Path]] = {name: [] for name in PROTECTED_RELATIONS[:2]}
    with (
        io.bounded_connection(
            work / "source-spill", database=work / "source-work.duckdb"
        ) as db,
        io.bounded_connection(
            work / "metadata-spill", memory="128MB", threads=1
        ) as metadata_db,
    ):
        _register_inputs(db, accepted)
        view = _small_view(
            config.reference_pack_root, public_manifest, raw, metadata_db
        )
        for group in range(execution.SHARD_GROUPS):
            binding = execution.checkpoint_binding(
                profile=profile,
                input_binding=accepted.fingerprint,
                pack=bytes.fromhex(public_manifest["logical_sha256"]),
                executable=config.execution_git_sha,
                group=group,
            )
            shard_root = work / f"group-{group:02}"
            resume = (
                config.resume_work_root / f"group-{group:02}"
                if config.resume_work_root
                else None
            )
            if resume is not None and (resume / "_COMPLETE.json").exists():
                checkpoint = execution.adopt_checkpoint(resume, shard_root, binding)
            else:
                checkpoint = execution.materialize_group(
                    db,
                    view,
                    postal_paths,
                    shard_root,
                    group=group,
                    profile=profile,
                    stage08_logical=logical,
                    binding=binding,
                )
            checkpoints.append(
                {
                    "path": str(shard_root),
                    "sha256": c.sha256_file(shard_root / "checkpoint.json"),
                    "binding": binding,
                    "job_id": checkpoint["job_id"],
                    "metrics": checkpoint["metrics"],
                    "adopted_from_checkpoint_sha256": checkpoint.get(
                        "adopted_from_checkpoint_sha256"
                    ),
                }
            )
            for relation in checkpoint["relations"]:
                shard_paths[relation["name"]].extend(
                    _relation_paths(shard_root, relation)
                )
        relations = [
            _canonical_protected(db, root, name, paths)
            for name, paths in shard_paths.items()
        ]
    # Full deterministic semantic replay is validation inside this same job,
    # not another submitted materialization. It re-resolves all original
    # pointers, role counts, normalizations and complete reference match sets.
    replay_relations = []
    replay_paths: dict[str, list[Path]] = {name: [] for name in PROTECTED_RELATIONS[:2]}
    replay_request_paths = []
    with (
        io.bounded_connection(
            work / "replay-source-spill", database=work / "replay-source.duckdb"
        ) as replay_db,
        io.bounded_connection(
            work / "replay-metadata-spill", memory="128MB", threads=1
        ) as metadata_db,
    ):
        _register_inputs(replay_db, accepted)
        view = _small_view(
            config.reference_pack_root, public_manifest, raw, metadata_db
        )
        for group in reversed(range(execution.SHARD_GROUPS)):
            replay_root = work / f"replay-{group:02}"
            binding = execution.checkpoint_binding(
                profile=profile,
                input_binding=accepted.fingerprint,
                pack=bytes.fromhex(public_manifest["logical_sha256"]),
                executable=config.execution_git_sha,
                group=group,
            )
            record = execution.materialize_group(
                replay_db,
                view,
                postal_paths,
                replay_root,
                group=group,
                profile=profile,
                stage08_logical=logical,
                binding=binding,
            )
            replay_request_paths.extend(
                sorted((replay_root / "postal_requests").glob("part-*.parquet"))
            )
            for relation in record["relations"]:
                replay_paths[relation["name"]].extend(
                    _relation_paths(replay_root, relation)
                )
        postal.validate_full_lookup_keys(replay_db, replay_request_paths)
        for name, paths in replay_paths.items():
            replay_relations.append(
                io.canonicalize(
                    replay_db,
                    name,
                    paths,
                    work / ("replay-merged-" + name),
                    collapse_exact_duplicates=name == "reference_match_member",
                )
            )
    validation.compare_replay(relations, replay_relations)
    with (
        io.bounded_connection(
            work / "validation-spill", database=work / "validation.duckdb"
        ) as db,
        io.bounded_connection(
            work / "validation-metadata-spill", memory="128MB", threads=1
        ) as metadata_db,
    ):
        _register_inputs(db, accepted)
        view = _small_view(
            config.reference_pack_root, public_manifest, raw, metadata_db
        )
        checks = validation.validate_integrity(
            db,
            view,
            _relation_paths(root, relations[0]),
            _relation_paths(root, relations[1]),
            _public_paths(config.reference_pack_root, public_manifest)[
                "reference_object"
            ],
            postal_paths,
            profile=profile,
            stage08_logical=logical,
            counts=accepted.binding["counts"],
        )
        checks["full_scheduling_normalization_reference_replay"] = "PASS"
        coverage.register_question_slots(db)
        writer = io.RelationWriter(
            work / "coverage-unsorted", c.relation_schema("coverage_summary")
        )
        for row in coverage.coverage_rows(
            db,
            raw.registry[0]["countries"]
            if raw.registry[0]["reference_id"] == c.ISO
            else next(
                r["countries"] for r in raw.registry if r["reference_id"] == c.ISO
            ),
            accepted.binding["counts"],
        ):
            writer.append(row)
        writer.close()
        relations.append(
            _canonical_protected(db, root, "coverage_summary", writer.paths)
        )
        metrics = coverage.aggregate_metrics(db)
    metadata_root = root / "metadata"
    metadata_root.mkdir(mode=0o700)
    metadata_inventory = []
    for name, payload in _metadata_payloads(
        profile, accepted, config.reference_pack_root, public_sha, public_manifest
    ).items():
        io.write_json(metadata_root / name, payload)
        path = metadata_root / name
        metadata_inventory.append(
            {
                "relative_path": "metadata/" + name,
                "bytes": path.stat().st_size,
                "sha256": c.sha256_file(path),
            }
        )
    return {
        "manifest_version": c.MANIFEST_VERSION,
        "kind": "STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE",
        "status": "DEVELOPMENT_CANDIDATE_AWAITING_INDEPENDENT_REVIEW",
        "stage09_accepted": False,
        "contract": c.CONTRACT_VERSION,
        "profile": c.PROFILE_VERSION,
        "schema": c.SCHEMA_VERSION,
        "contract_sha256": c.contract_fingerprint().hex(),
        "schema_bundle_sha256": c.schema_bundle_fingerprint().hex(),
        "profile_sha256": profile.hex(),
        "catalog_sha256": c.catalog_fingerprint().hex(),
        "normalization_sha256": c.normalization_fingerprint().hex(),
        "semantics_sha256": c.semantics_fingerprint().hex(),
        "stage08_binding": dict(accepted.binding),
        "stage08_binding_sha256": accepted.fingerprint.hex(),
        "reference_pack": {
            "manifest_sha256": public_sha,
            "logical_sha256": public_manifest["logical_sha256"],
            "lock_sha256": c.LOCK_SHA256,
            "path": str(config.reference_pack_root),
        },
        "relations": relations,
        "metadata_inventory": metadata_inventory,
        "validation": checks,
        "logical_sha256": dataset_fingerprint(
            profile,
            relations,
            public_manifest["logical_sha256"],
            accepted.binding["stage08_relation_logical_fingerprints"][
                "representation_occurrence_v1"
            ],
        ).hex(),
        "development_metrics": metrics,
        "checkpoints": checkpoints,
        "operational_provenance": {
            "execution_git_sha": config.execution_git_sha,
            "design_freeze_sha": c.DESIGN_COMMIT,
            "publication_protocol": publication.PROTOCOL,
            "job_id": os.environ.get("SLURM_JOB_ID", "SYNTHETIC"),
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", "SYNTHETIC"),
            "semantic_runtime": list(c.SEMANTIC_RUNTIME),
            "environment": sorted(
                (d.metadata["Name"], d.version)
                for d in importlib.metadata.distributions()
            ),
            "duckdb_source": duckdb.connect().execute("PRAGMA version").fetchone(),
            "elapsed_build_seconds": int(time.monotonic() - started),
            "requested_cpus": 4,
            "requested_memory_gib": 32,
            "duckdb_memory_limit": "8GB",
            "arrow_batch_target_bytes": 64 * 1024 * 1024,
            "work_root": str(work),
        },
        "scientific_boundary": "REFERENCE_EVIDENCE_ONLY",
        "boundary_handoff": "BOUNDARY_HANDOFF_SUFFICIENT",
        "privacy": {
            "holdout_access": False,
            "production_access": False,
            "pelias_access": False,
            "protected_values_logged": False,
            "network_calls": 0,
            "source_corrections": 0,
        },
    }


def validate_candidate(
    root: Path,
    manifest_sha: str,
    *,
    published: io.PublicationState,
    config: Stage09Config,
    accepted: upstream.AcceptedStage08,
    raw: pack.PublicInputs,
    public_manifest: Mapping[str, Any],
    public_sha: str,
) -> dict[str, Any]:
    manifest = io.validate_terminal(root, manifest_sha, published)
    profile = scientific_profile(accepted.fingerprint, public_manifest)
    c.require(
        manifest["kind"] == "STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE"
        and manifest["stage09_accepted"] is False
        and manifest["stage08_binding"] == accepted.binding
        and manifest["stage08_binding_sha256"] == accepted.fingerprint.hex()
        and manifest["profile_sha256"] == profile.hex()
        and manifest["contract_sha256"] == c.contract_fingerprint().hex()
        and manifest["schema_bundle_sha256"] == c.schema_bundle_fingerprint().hex(),
        "STAGE09_SCIENTIFIC_BINDING_MISMATCH",
    )
    c.require(
        manifest["reference_pack"]
        == {
            "manifest_sha256": public_sha,
            "logical_sha256": public_manifest["logical_sha256"],
            "lock_sha256": c.LOCK_SHA256,
            "path": str(config.reference_pack_root),
        },
        "REFERENCE_PACK_BINDING_MISMATCH",
    )
    c.require(
        manifest["operational_provenance"]["execution_git_sha"]
        == config.execution_git_sha,
        "EXECUTABLE_BINDING_MISMATCH",
    )
    c.require(
        [r["name"] for r in manifest["relations"]] == list(PROTECTED_RELATIONS),
        "PROTECTED_RELATION_SET_INVALID",
    )
    inventory = io.terminal_files(published)
    paths = {}
    for relation in manifest["relations"]:
        paths[relation["name"]] = io.validate_relation(root, relation)
        inventory.extend(r["relative_path"] for r in relation["files"])
    expected_metadata = _metadata_payloads(
        profile, accepted, config.reference_pack_root, public_sha, public_manifest
    )
    c.require(
        {r["relative_path"] for r in manifest["metadata_inventory"]}
        == {"metadata/" + name for name in expected_metadata},
        "METADATA_INVENTORY_INVALID",
    )
    for item in manifest["metadata_inventory"]:
        path = pack.confined(root, item["relative_path"])
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"]
            and path.read_bytes() == c.canonical_json(expected_metadata[path.name]),
            "METADATA_HASH_OR_BINDING_MISMATCH",
        )
        inventory.append(item["relative_path"])
    work = Path(tempfile.mkdtemp(prefix=".stage09-reopen-validation-", dir=root.parent))
    postal_paths = [
        config.reference_pack_root / f["relative_path"]
        for f in public_manifest["reference_index"]["files"]
    ]
    with (
        io.bounded_connection(
            work / "spill", database=work / "validation.duckdb"
        ) as db,
        io.bounded_connection(
            work / "metadata-spill", memory="128MB", threads=1
        ) as meta_db,
    ):
        _register_inputs(db, accepted)
        view = _small_view(config.reference_pack_root, public_manifest, raw, meta_db)
        checks = validation.validate_integrity(
            db,
            view,
            paths["candidate_reference_evidence"],
            paths["reference_match_member"],
            _public_paths(config.reference_pack_root, public_manifest)[
                "reference_object"
            ],
            postal_paths,
            profile=profile,
            stage08_logical=bytes.fromhex(
                accepted.binding["stage08_logical_dataset_sha256"]
            ),
            counts=accepted.binding["counts"],
        )
        c.require(
            all(manifest["validation"].get(k) == v for k, v in checks.items())
            and manifest["validation"]["full_scheduling_normalization_reference_replay"]
            == "PASS",
            "VALIDATION_CERTIFICATE_MISMATCH",
        )
        coverage.register_question_slots(db)
        expected = io.RelationWriter(
            work / "coverage-recomputed", c.relation_schema("coverage_summary")
        )
        for row in coverage.coverage_rows(
            db,
            next(r["countries"] for r in raw.registry if r["reference_id"] == c.ISO),
            accepted.binding["counts"],
        ):
            expected.append(row)
        expected.close()
        record = io.canonicalize(
            db, "coverage_summary", expected.paths, work / "coverage-canonical"
        )
        validation.compare_replay([record], [manifest["relations"][2]])
        c.require(
            coverage.aggregate_metrics(db) == manifest["development_metrics"],
            "DEVELOPMENT_AGGREGATES_MISMATCH",
        )
    c.require(
        dataset_fingerprint(
            profile,
            manifest["relations"],
            public_manifest["logical_sha256"],
            accepted.binding["stage08_relation_logical_fingerprints"][
                "representation_occurrence_v1"
            ],
        ).hex()
        == manifest["logical_sha256"],
        "DATASET_LOGICAL_FINGERPRINT_MISMATCH",
    )
    io.topology(root, inventory)
    return manifest


def materialize_stage09(config: Stage09Config) -> io.PublicationResult:
    config.validate()
    if os.path.lexists(config.output_directory):
        c.require(
            config.expected_manifest_sha256 is not None,
            "EXISTING_CANDIDATE_EXPECTED_HASH_REQUIRED",
        )
        c.require(
            config.reference_pack_manifest_sha256 is not None,
            "EXISTING_CANDIDATE_PACK_HASH_REQUIRED",
        )
        assert config.expected_manifest_sha256 is not None
        return validate_published_stage09(config, config.expected_manifest_sha256)
    with offline_network():
        lock = pack.verify_lock(config.reference_raw_root, config.reference_lock)
        raw = pack.PublicInputs(
            config.reference_raw_root, lock, pack.registry_rows(lock)
        )
        public_manifest: Mapping[str, Any]
        if config.reference_pack_root.exists():
            c.require(
                config.reference_pack_manifest_sha256 is not None,
                "EXISTING_PUBLIC_PACK_EXPECTED_HASH_REQUIRED",
            )
            assert config.reference_pack_manifest_sha256 is not None
            public_sha = config.reference_pack_manifest_sha256
            public_manifest = index.validate_public_pack(
                config.reference_pack_root, public_sha, inputs=raw
            )
        else:
            public_result = index.build_public_pack(
                raw, config.reference_pack_root, config.execution_git_sha
            )
            public_sha, public_manifest = (
                public_result.manifest_sha256,
                public_result.manifest,
            )
        accepted = upstream.consume_accepted_stage08(config.stage08_root)
        work = Path(
            tempfile.mkdtemp(
                prefix=".stage09-development-work-", dir=config.output_directory.parent
            )
        )
        return io.publish(
            config.output_directory,
            lambda root: _build_candidate(
                root, work, config, accepted, raw, public_manifest, public_sha
            ),
            lambda root, digest, published: validate_candidate(
                root,
                digest,
                published=published,
                config=config,
                accepted=accepted,
                raw=raw,
                public_manifest=public_manifest,
                public_sha=public_sha,
            ),
            expected_manifest=config.expected_manifest_sha256,
        )


def validate_published_stage09(
    config: Stage09Config, manifest_sha: str
) -> io.PublicationResult:
    config.validate()
    c.require(
        config.reference_pack_manifest_sha256 is not None,
        "PUBLIC_PACK_EXPECTED_HASH_REQUIRED",
    )
    assert config.reference_pack_manifest_sha256 is not None
    public_sha = config.reference_pack_manifest_sha256
    # Reject uncommitted/conflicting state before opening protected inputs.
    publication.validate_terminal(config.output_directory, manifest_sha, True)
    with offline_network():
        lock = pack.verify_lock(config.reference_raw_root, config.reference_lock)
        raw = pack.PublicInputs(
            config.reference_raw_root, lock, pack.registry_rows(lock)
        )
        public_manifest = index.validate_public_pack(
            config.reference_pack_root,
            config.reference_pack_manifest_sha256,
            inputs=raw,
        )
        accepted = upstream.consume_accepted_stage08(config.stage08_root)
        return publication.adopt(
            config.output_directory,
            manifest_sha,
            lambda root, digest, state: validate_candidate(
                root,
                digest,
                published=state,
                config=config,
                accepted=accepted,
                raw=raw,
                public_manifest=public_manifest,
                public_sha=public_sha,
            ),
        )

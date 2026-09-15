"""Exact accepted input consumption; no replacement source/candidate authority."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from . import s06_exact_deduplication as s6
from . import s08_address_evidence as s8
from . import s09_reference_contract as s9
from . import s09_reference_input as accepted8
from . import s09_reference_io as upstream_io
from . import s09_reference_pack as pack
from . import s09_reference_publication as publication9
from . import s10_query_contract as c
from . import s10_query_io as io

PROJECT_ALIAS = Path("/work/footprint/donyadidegan/safe_geocoding_pipeline")
STAGE06_MANIFEST = "e1da7b8ef04b65b1ece8e710720b57a8536841766fcf9de641f889b42eadd241"
STAGE06_LOGICAL = "2f6379c0cd5dc9654c03895cae6fdd48f3a7af528158c33e44d2030c816640b6"
STAGE06_ROW_LOGICAL = "1ff9067c521ae93d28c300d7120a03c39681ce7830bf23b6619e2ca6129a4fe1"
STAGE06_SCHEMA = "9c07b7a4c3f7a5c43ad457dcf6f7fe3fd746d54d82a731139905b30828b6c9ce"
STAGE06_BINDING = "6ba224d6d24c3631aae8aac69f4a362bb054f01d9e3d09327ec6b0fdd85a0e7d"
STAGE09_MANIFEST = "321c9d8352fac5b78612a7c8e52f6f810f92bddb1e91f7cfe348398a6d707240"
STAGE09_LOGICAL = "7ae84e149f4c9c2de7a791c9b326b88e387a70d155d8be55acf6b55e06bafae3"
STAGE09_CONTRACT = "6dc0410556bad44a6a6d1b3695beb6219c54a61dab39747a5ffa92ac9fcda3f9"
STAGE09_PROFILE = "b12be7ba06de2360ba7cd9b971c4b562b1c8df5d25c30024975869fd2b34efd1"
STAGE09_SCHEMA = "7374b70fae76149b825f523e8317577bd6d868bee3fde648ea915301d4bcb716"
STAGE09_STAGE08_BINDING = (
    "64f7678a76e3f29f57859f050329be925b216d2b1290eff5d36b9cb4482cea90"
)
PUBLIC_MANIFEST = "dd7994b907250d515470b820bcbf42993a08e4f3116409b7c94168446e1c064a"
READ_STAGE09 = ("candidate_reference_evidence", "reference_match_member")
READ_PUBLIC = ("reference_registry", "reference_capability", "reference_object")
STAGE08_SCHEMAS = {
    "candidate_evidence": s8.candidate_evidence_schema(),
    "parser_component_evidence": s8.parser_component_evidence_schema(),
    "source_candidate_map": s8.source_candidate_map_schema(),
}


def source_line_fields(role: str) -> tuple[str, ...]:
    c.require(role in c.ROLES, "STAGE10_SOURCE_ROLE_INVALID")
    prefix = role.lower()
    suffix = "_native" if role == "NATIVE" else ""
    return (
        f"stage06_{prefix}_exact_candidate_id",
        *(f"stage04_lower_street_address_line_{i}{suffix}" for i in range(1, 5)),
        f"stage05_{prefix}_candidate_lower",
        f"stage05_{prefix}_candidate_available",
        f"stage05_{prefix}_contributing_line_count",
        f"stage05_{prefix}_contributing_line_mask",
    )


def row_projection_schema() -> Any:
    selected = {
        "stable_source_row_id_v1",
        *source_line_fields("STANDARD"),
        *source_line_fields("NATIVE"),
    }
    return pa.schema([field for field in s6.row_map_schema() if field.name in selected])


def controlled_path(path: Path) -> Path:
    # Resolve the accepted configured mount alias, never arbitrary descendants.
    c.require(path.is_absolute(), "STAGE10_ABSOLUTE_INPUT_PATH_REQUIRED")
    c.require(
        not any(word in str(path).lower() for word in ("holdout", "production")),
        "STAGE10_DEVELOPMENT_SCOPE_REQUIRED",
    )
    anchor = PROJECT_ALIAS.resolve(strict=True)
    if path.is_relative_to(PROJECT_ALIAS):
        selected = anchor / path.relative_to(PROJECT_ALIAS)
    else:
        c.require(path.is_relative_to(anchor), "STAGE10_CONTROLLED_ANCHOR_REQUIRED")
        selected = path
    c.require(
        selected == selected.resolve(strict=True), "STAGE10_INPUT_SYMLINK_PROHIBITED"
    )
    return selected


def _files08(accepted: accepted8.AcceptedStage08) -> list[dict[str, Any]]:
    records = [
        r
        for name in (*STAGE08_SCHEMAS, "metadata")
        for r in accepted.manifest["physical_identity"][name + "_artifacts"]
    ]
    return sorted(
        (
            {
                "relative_path": r["relative_path"],
                "bytes": r["size_bytes"],
                "sha256": r["sha256"],
            }
            for r in records
        ),
        key=lambda r: r["relative_path"].encode("utf-8"),
    )


def _consume_stage06(
    root: Path,
) -> tuple[dict[str, Any], tuple[Path, ...], list[dict[str, Any]]]:
    pack.regular_private(root, directory=True)
    path = root / s6.STAGE06_MANIFEST_NAME
    pack.regular_private(path)
    c.require(
        c.sha256_file(path) == STAGE06_MANIFEST, "STAGE10_STAGE06_MANIFEST_MISMATCH"
    )
    c.require(
        not os.path.lexists(root / s6.STAGE06_IN_PROGRESS_MARKER),
        "STAGE10_STAGE06_UNPUBLISHED",
    )
    manifest = c.read_json(path)
    success_path = root / s6.STAGE06_SUCCESS_MARKER
    pack.regular_private(success_path)
    success = c.read_json(success_path)
    scientific = manifest["scientific_identity"]
    c.require(
        success["stage06_manifest_sha256"] == STAGE06_MANIFEST
        and success["stage06_logical_dataset_sha256_v1"] == STAGE06_LOGICAL
        and success["stage06_input_binding_sha256"] == STAGE06_BINDING
        and scientific["stage06_logical_dataset_sha256_v1"] == STAGE06_LOGICAL
        and scientific["stage06_row_map_logical_sha256_v1"] == STAGE06_ROW_LOGICAL
        and scientific["stage06_schema_fingerprint"]
        == STAGE06_SCHEMA
        == s6.stage06_schema_fingerprint()
        and scientific["source_row_count"] == 35000
        and scientific["unique_candidate_count"] == 51779,
        "STAGE10_STAGE06_ACCEPTED_BINDING_MISMATCH",
    )
    paths = []
    files = []
    count = 0
    for item in manifest["physical_identity"]["row_map_artifacts"]:
        path = pack.confined(root, item["relative_path"])
        pack.regular_private(path)
        c.require(
            path.stat().st_size == item["size_bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_STAGE06_ROW_BYTES_MISMATCH",
        )
        with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
            # Stage 6 appends run/input metadata to its fixed field schema.
            c.require(
                parquet.schema_arrow.equals(s6.row_map_schema(), check_metadata=False)
                and parquet.metadata.num_rows == item["row_count"],
                "STAGE10_STAGE06_ROW_SCHEMA_COUNT_MISMATCH",
            )
            count += parquet.metadata.num_rows
        paths.append(path)
        files.append(
            {
                "relative_path": item["relative_path"],
                "bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
        )
    c.require(
        count == 35000 and len(set(paths)) == len(paths),
        "STAGE10_STAGE06_ROW_INVENTORY_INVALID",
    )
    return (
        manifest,
        tuple(paths),
        sorted(files, key=lambda r: r["relative_path"].encode("utf-8")),
    )


def _consume_stage09(
    root: Path, expected: str
) -> tuple[dict[str, Any], dict[str, tuple[Path, ...]]]:
    manifest = publication9.validate_terminal(root, expected, True)
    for item in publication9.inventory(manifest):
        path = pack.confined(root, item["path"])
        pack.regular_private(path)
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_STAGE09_BYTE_INVENTORY_MISMATCH",
        )
    paths = {}
    for record in manifest["relations"]:
        # Validate accepted relation logical bytes without rerunning references.
        name = record["name"]
        c.require(
            record["schema_sha256"] == s9.schema_fingerprint(name).hex(),
            "STAGE10_UPSTREAM_SCHEMA_BINDING_MISMATCH",
        )
        group = []
        for item in record["files"]:
            path = pack.confined(root, item["relative_path"])
            with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
                c.require(
                    parquet.schema_arrow.equals(
                        s9.relation_schema(name), check_metadata=True
                    ),
                    "STAGE10_UPSTREAM_SCHEMA_MISMATCH",
                )
            group.append(path)
        c.require(
            s9.relation_fingerprint(
                name, record["row_count"], upstream_io.parquet_rows(group, batch_rows=1)
            ).hex()
            == record["logical_sha256"],
            "STAGE10_UPSTREAM_LOGICAL_MISMATCH",
        )
        paths[name] = tuple(group)
    return manifest, paths


@dataclass(frozen=True)
class AcceptedInputs:
    stage08: accepted8.AcceptedStage08
    stage09: Mapping[str, Any]
    public_pack: Mapping[str, Any]
    stage06: Mapping[str, Any]
    paths: Mapping[str, tuple[Path, ...]]
    binding: Mapping[str, Any]

    @cached_property
    def identifier(self) -> bytes:
        return c.identity("stage10-input:v1", c.canonical(self.binding))

    @cached_property
    def context_binding(self) -> bytes:
        return c.identity(
            "stage10-context-input:v1",
            bytes.fromhex(accepted8.STAGE08_MANIFEST_SHA256),
            bytes.fromhex(STAGE06_MANIFEST),
            bytes.fromhex(STAGE09_MANIFEST),
        )

    def register_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        self.stage08.register_views(connection)
        for name, paths in self.paths.items():
            if name in STAGE08_SCHEMAS:
                continue
            selection = (
                ",".join(row_projection_schema().names)
                if name == "stage06_row_map"
                else "*"
            )
            connection.execute(
                f"CREATE VIEW {name} AS SELECT {selection} FROM {io.parquet_sql(paths)}"
            )


def consume_inputs(
    stage08_root: Path, stage09_root: Path, stage06_root: Path
) -> AcceptedInputs:
    require_goethe_nhr_slurm("stage10-query-input")
    c.require_runtime()
    stage08_root, stage09_root, stage06_root = (
        controlled_path(path) for path in (stage08_root, stage09_root, stage06_root)
    )
    a8 = accepted8.consume_accepted_stage08(stage08_root)
    stage09, paths09 = _consume_stage09(stage09_root, STAGE09_MANIFEST)
    c.require(
        stage09["kind"] == publication9.DEVELOPMENT
        and stage09["logical_sha256"] == STAGE09_LOGICAL
        and stage09["contract_sha256"]
        == STAGE09_CONTRACT
        == s9.contract_fingerprint().hex()
        and stage09["profile_sha256"] == STAGE09_PROFILE
        and stage09["schema_bundle_sha256"]
        == STAGE09_SCHEMA
        == s9.schema_bundle_fingerprint().hex()
        and stage09["stage08_binding_sha256"]
        == STAGE09_STAGE08_BINDING
        == a8.fingerprint.hex()
        and stage09["stage08_binding"] == a8.binding
        and stage09["reference_pack"]["manifest_sha256"] == PUBLIC_MANIFEST
        and stage09["reference_pack"]["lock_sha256"] == s9.LOCK_SHA256,
        "STAGE10_STAGE09_ACCEPTED_BINDING_MISMATCH",
    )
    public_root = controlled_path(Path(stage09["reference_pack"]["path"]))
    public, public_paths = _consume_stage09(public_root, PUBLIC_MANIFEST)
    c.require(
        public["kind"] == publication9.PUBLIC
        and public["lock_sha256"] == s9.LOCK_SHA256
        and public["logical_sha256"] == stage09["reference_pack"]["logical_sha256"],
        "STAGE10_PUBLIC_PACK_BINDING_MISMATCH",
    )
    stage06, row_paths, row_files = _consume_stage06(stage06_root)
    paths = {
        **a8.paths,
        **{n: paths09[n] for n in READ_STAGE09},
        **{n: public_paths[n] for n in READ_PUBLIC},
        "stage06_row_map": row_paths,
    }

    def stage_entry(
        manifest_sha: str,
        logical: str,
        contract: str,
        contract_sha: str,
        profile_sha: str | None,
        schema_sha: str,
        transitive: Any,
        anchor: Path,
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "manifest_sha256": manifest_sha,
            "logical_sha256": logical,
            "contract": contract,
            "contract_sha256": contract_sha,
            "profile_sha256": profile_sha,
            "schema_bundle_sha256": schema_sha,
            "transitive_bindings": transitive,
            "approved_anchor": str(anchor),
            "files": files,
        }

    scientific06 = stage06["scientific_identity"]
    binding = {
        "binding_version": "stage10_input_binding_v1",
        "split": "DEVELOPMENT",
        "benchmark_sha256": accepted8.BENCHMARK_SHA256,
        "stage08": stage_entry(
            accepted8.STAGE08_MANIFEST_SHA256,
            accepted8.STAGE08_LOGICAL_SHA256,
            s8.STAGE08_CONTRACT_VERSION,
            accepted8.STAGE08_CONTRACT_SHA256,
            None,
            accepted8.STAGE08_SCHEMA_SHA256,
            dict(a8.binding),
            stage08_root,
            _files08(a8),
        ),
        "stage09": {
            **stage_entry(
                STAGE09_MANIFEST,
                STAGE09_LOGICAL,
                s9.CONTRACT_VERSION,
                STAGE09_CONTRACT,
                STAGE09_PROFILE,
                STAGE09_SCHEMA,
                stage09["stage08_binding"],
                stage09_root,
                [
                    {
                        "relative_path": f["path"],
                        "bytes": f["bytes"],
                        "sha256": f["sha256"],
                    }
                    for f in publication9.inventory(stage09)
                ],
            ),
            "reference_pack": {
                "manifest_sha256": PUBLIC_MANIFEST,
                "logical_sha256": public["logical_sha256"],
                "lock_sha256": s9.LOCK_SHA256,
                "approved_anchor": str(public_root),
                "relations": public["relations"],
                "reference_index": public["reference_index"],
            },
        },
        "stage06_row_map": stage_entry(
            STAGE06_MANIFEST,
            STAGE06_LOGICAL,
            scientific06["stage06_contract_version"],
            scientific06["stage06_contract_fingerprint"],
            None,
            STAGE06_SCHEMA,
            {
                "input_binding_sha256": STAGE06_BINDING,
                "row_map_logical_sha256": STAGE06_ROW_LOGICAL,
                "scientific_identity": scientific06,
            },
            stage06_root,
            row_files,
        ),
        "read_projection": [
            {
                "relation": n,
                "fields": list(
                    (
                        row_projection_schema()
                        if n == "stage06_row_map"
                        else STAGE08_SCHEMAS[n]
                        if n in STAGE08_SCHEMAS
                        else s9.relation_schema(n)
                    ).names
                ),
            }
            for n in sorted(paths)
        ],
    }
    return AcceptedInputs(a8, stage09, public, stage06, paths, binding)

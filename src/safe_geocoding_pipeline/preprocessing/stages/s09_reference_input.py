"""Consume the already accepted Stage 8 artifact, never reopen Stage 6/7 data.

The pinned manifest plus every owned byte hash proves that this is the accepted
artifact. No upstream rematerialization, parser replay, or historical inode
check is used. Only Stage 8's narrow columns are read by later scheduling.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.parquet as pq

from ...execution_policy import require_goethe_nhr_slurm
from . import s08_address_evidence as s08
from . import s09_reference_contract as c
from . import s09_reference_io as io
from . import s09_reference_pack as p


STAGE08_MANIFEST_SHA256 = (
    "2a50bd8c066552c9cb7505ed2d6071f1ee36161b9a2cc07f3ed364cf00237827"
)
STAGE08_LOGICAL_SHA256 = (
    "9c9d431c2c1b92712e0cb372f2661ad48f4fe8758dc0327d25aef90ab2c2d526"
)
STAGE08_CONTRACT_SHA256 = (
    "8b3c530e714177fe2c30a97d61dcc199b7f9efba58f3c17a291b817af0f24d5e"
)
STAGE08_SCHEMA_SHA256 = (
    "6c8ebecd24c495dbe2ce32125ac1cb89c4a9de4905c786b774d10ad728ed392f"
)
STAGE08_RELATIONS = {
    "candidate_evidence": "11fbd6e6e32b7dcb293c5918e9d02f19badf52cc9d9c108c910d17d92b8645aa",
    "parser_component_evidence": "8b1af702c51bd40edc22302778ae2fda5851d9af8af39636a9a9733a94916030",
    "source_candidate_map": "c4c9f8b3f425f93a1d61880f720136d1f71580871338c9a920c9abeffa93ee32",
    "representation_occurrence_v1": "57aa3dcc5caf796fbbe15b3c0df655a8f34902107ce9fed3fbb6aaf38e158774",
}
BENCHMARK_SHA256 = "014a7d2a9935bb098711e62b89df2eb93dfdd0dd1ce5ac70853f010d118acedf"
COUNTS = {
    "candidate_evidence": 51_779,
    "parser_component_evidence": 6_106_088,
    "source_candidate_map": 35_000,
    "representation_occurrence_v1": 69_747,
    "standard_occurrences": 34_822,
    "native_occurrences": 34_925,
}


def reject_protected_scope_path(path: Path) -> None:
    # Check lexical and resolved paths. This precedes protected file opening.
    for spelling in (str(path.absolute()), str(path.resolve())):
        c.require(
            not any(word in spelling.lower() for word in ("holdout", "production")),
            "STAGE09_DEVELOPMENT_SCOPE_ONLY",
        )
    c.require(not path.is_symlink(), "STAGE09_INPUT_ROOT_SYMLINK_PROHIBITED")


def accepted_binding() -> dict[str, Any]:
    return {
        "split": "DEVELOPMENT",
        "benchmark_sha256": BENCHMARK_SHA256,
        "stage08_manifest_sha256": STAGE08_MANIFEST_SHA256,
        "stage08_logical_dataset_sha256": STAGE08_LOGICAL_SHA256,
        "stage08_contract_sha256": STAGE08_CONTRACT_SHA256,
        "stage08_schema_bundle_sha256": STAGE08_SCHEMA_SHA256,
        "stage08_schema_fingerprints": s08.stage08_schema_fingerprints(),
        "stage08_mapping_sha256": s08.stage08_label_mapping_fingerprint(),
        "stage08_relation_logical_fingerprints": STAGE08_RELATIONS,
        "transitive_accepted_stage08_input_binding": s08.accepted_stage08_input_binding().to_dict(),
        "counts": COUNTS,
    }


def input_binding_fingerprint(binding: Mapping[str, Any]) -> bytes:
    def pairs(value: Any) -> Any:
        if isinstance(value, Mapping):
            return tuple((k, pairs(v)) for k, v in sorted(value.items()))
        if (
            isinstance(value, str)
            and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value)
        ):
            return bytes.fromhex(value)
        return value

    return c.identity("INPUT_BINDING", pairs(binding))


@dataclass(frozen=True)
class AcceptedStage08:
    root: Path
    manifest: Mapping[str, Any]
    paths: Mapping[str, tuple[Path, ...]]
    binding: Mapping[str, Any]

    @property
    def fingerprint(self) -> bytes:
        return input_binding_fingerprint(self.binding)

    def register_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        for name, paths in self.paths.items():
            connection.execute(
                f"CREATE VIEW {name} AS SELECT * FROM {io.parquet_sql(paths)}"
            )
        connection.execute(
            "CREATE VIEW stage08_occurrence AS " + s08.REPRESENTATION_OCCURRENCE_SQL
        )


def consume_accepted_stage08(root: Path) -> AcceptedStage08:
    # There is intentionally no controlled_execution=False or synthetic CLI
    # bypass on the protected consumer.
    require_goethe_nhr_slurm("stage09-reference-evidence-input")
    c.require_runtime()
    reject_protected_scope_path(root)
    p.regular_private(root, directory=True)
    manifest_path = root / s08.STAGE08_MANIFEST_NAME
    c.require(
        c.sha256_file(manifest_path) == STAGE08_MANIFEST_SHA256,
        "ACCEPTED_STAGE08_MANIFEST_MISMATCH",
    )
    c.require(
        not os.path.lexists(root / s08.STAGE08_IN_PROGRESS_NAME),
        "STAGE08_INPUT_NOT_PUBLISHED",
    )
    manifest = c.read_json(manifest_path)
    success = c.read_json(root / s08.STAGE08_SUCCESS_NAME)
    scientific = manifest["scientific_identity"]
    c.require(
        success["manifest_sha256"] == STAGE08_MANIFEST_SHA256
        and success["logical_dataset_sha256"] == STAGE08_LOGICAL_SHA256,
        "STAGE08_SUCCESS_BINDING_MISMATCH",
    )
    c.require(
        scientific["contract_fingerprint"]
        == STAGE08_CONTRACT_SHA256
        == s08.stage08_contract_fingerprint(s08.accepted_stage08_input_binding()),
        "STAGE08_CONTRACT_CHANGED",
    )
    c.require(
        scientific["schema_bundle_fingerprint"]
        == STAGE08_SCHEMA_SHA256
        == s08.stage08_schema_bundle_fingerprint(),
        "STAGE08_SCHEMA_CHANGED",
    )
    c.require(
        scientific["schema_fingerprints"] == s08.stage08_schema_fingerprints()
        and scientific["label_mapping_fingerprint"]
        == s08.stage08_label_mapping_fingerprint(),
        "STAGE08_MAPPING_OR_SCHEMA_CHANGED",
    )
    c.require(
        scientific["logical_dataset_sha256"] == STAGE08_LOGICAL_SHA256
        and scientific["relation_logical_fingerprints"] == STAGE08_RELATIONS,
        "STAGE08_LOGICAL_BINDING_MISMATCH",
    )
    c.require(
        scientific["input_binding"] == s08.accepted_stage08_input_binding().to_dict(),
        "STAGE08_TRANSITIVE_BINDING_MISMATCH",
    )
    c.require(
        scientific["representation_occurrence_view"]
        == {
            "materialized": False,
            "canonical_sql": s08.REPRESENTATION_OCCURRENCE_SQL,
            "row_count": 69_747,
        },
        "STAGE08_OCCURRENCE_BINDING_MISMATCH",
    )
    schemas = {
        "candidate_evidence": s08.candidate_evidence_schema(),
        "parser_component_evidence": s08.parser_component_evidence_schema(),
        "source_candidate_map": s08.source_candidate_map_schema(),
    }
    paths = {}
    inventory = [s08.STAGE08_MANIFEST_NAME, s08.STAGE08_SUCCESS_NAME]
    for relation in (*schemas, "metadata"):
        group = []
        count = 0
        for record in manifest["physical_identity"][relation + "_artifacts"]:
            path = p.confined(root, record["relative_path"])
            p.regular_private(path)
            c.require(
                path.stat().st_size == record["size_bytes"]
                and c.sha256_file(path) == record["sha256"],
                "STAGE08_OWNED_ARTIFACT_MISMATCH",
            )
            inventory.append(record["relative_path"])
            if relation != "metadata":
                with pq.ParquetFile(path, page_checksum_verification=True) as parquet:
                    c.require(
                        parquet.schema_arrow.equals(
                            schemas[relation], check_metadata=True
                        )
                        and parquet.metadata.num_rows == record["row_count"],
                        "STAGE08_OWNED_SCHEMA_OR_COUNT_MISMATCH",
                    )
                    count += parquet.metadata.num_rows
                group.append(path)
        if relation != "metadata":
            c.require(
                count == COUNTS[relation], "STAGE08_ACCEPTED_CARDINALITY_MISMATCH"
            )
            paths[relation] = tuple(group)
    io.topology(root, inventory)
    return AcceptedStage08(root, manifest, paths, accepted_binding())

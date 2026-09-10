"""Build/reopen the reusable immutable public pack; never access source rows."""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from itertools import zip_longest
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from . import s09_reference_contract as c
from . import s09_reference_io as io
from . import s09_reference_pack as p
from . import s09_reference_publication as publication


def index_schema_fingerprint() -> bytes:
    return c.identity(
        "INDEX_SCHEMA",
        (
            p.INDEX_VERSION,
            tuple((f.name, str(f.type), f.nullable) for f in p.GN_INDEX_SCHEMA),
            c.NORMALIZATION_VERSION,
            c.DESIGN_SHA256,
        ),
    )


def index_fingerprint(count: int, rows: Iterator[Mapping[str, Any]]) -> bytes:
    digest = hashlib.sha256(struct.pack(">Q", 4))
    for value in ("SAFE_STAGE09", "V1", "INDEX_RELATION"):
        digest.update(c.framed(value))
    digest.update(b"\x05" + struct.pack(">Q", 4))
    for header_value in (p.INDEX_VERSION, index_schema_fingerprint(), count):
        digest.update(c.framed(header_value))
    digest.update(b"\x05" + struct.pack(">Q", count))
    previous = None
    seen = 0
    for row in rows:
        key = row["reference_object_id"]
        c.require(previous is None or previous < key, "INDEX_OBJECT_KEY_COLLISION")
        previous = key
        for chunk in c.typed_chunks(c.ordered_values(row, p.GN_INDEX_SCHEMA)):
            digest.update(chunk)
        seen += 1
    c.require(seen == count, "INDEX_COUNT_MISMATCH")
    return digest.digest()


def pack_logical_fingerprint(
    relations: Sequence[Mapping[str, Any]], index: Mapping[str, Any]
) -> bytes:
    return c.identity(
        "PUBLIC_PACK",
        (
            bytes.fromhex(c.LOCK_SHA256),
            p.INDEX_VERSION,
            tuple(
                (
                    r["name"],
                    bytes.fromhex(r["schema_sha256"]),
                    r["row_count"],
                    bytes.fromhex(r["logical_sha256"]),
                )
                for r in sorted(relations, key=lambda r: r["name"])
            ),
            index_schema_fingerprint(),
            index["row_count"],
            bytes.fromhex(index["logical_sha256"]),
        ),
    )


def build_public_pack(
    inputs: p.PublicInputs, final: Path, execution_sha: str
) -> io.PublicationResult:
    """Called after complete raw-lock verification; indexes are built once."""
    c.require_runtime()
    work = Path(
        tempfile.mkdtemp(prefix=".stage09-public-index-work-", dir=final.parent)
    )

    def build(root: Path) -> Mapping[str, Any]:
        iso, metadata = inputs.small_objects()
        matrix = p.matrix_capabilities(inputs.lock, inputs.registry)
        lia_version = next(
            r["reference_version_id"]
            for r in inputs.registry
            if r["reference_id"] == c.LIA
        )
        capabilities = matrix + p.metadata_rule_capabilities(
            metadata, [r for r in matrix if r["reference_version_id"] == lia_version]
        )
        public = {
            "reference_registry": inputs.registry,
            "reference_capability": sorted(
                capabilities, key=lambda r: r["capability_id"]
            ),
        }
        relations = []
        for name, rows in public.items():
            writer = io.RelationWriter(root / name, c.relation_schema(name))
            for row in rows:
                writer.append(row)
            writer.close()
            logical = c.relation_fingerprint(
                name, writer.rows, io.parquet_rows(writer.paths)
            )
            relations.append(
                io.relation_record(name, root, writer.paths, writer.rows, logical)
            )
        objects = io.RelationWriter(
            work / "reference_objects_unsorted", c.relation_schema("reference_object")
        )
        index_writer = io.RelationWriter(
            work / "postal_index_unsorted", p.GN_INDEX_SCHEMA
        )
        for obj in (*iso, *metadata):
            objects.append(obj)
        postal_count = 0
        for obj in inputs.postal_objects():
            objects.append(obj)
            index_writer.append(p.geonames_index_row(obj))
            postal_count += 1
        c.require(
            postal_count == inputs.lock["compatibility_audit"]["geonames"]["rows"],
            "POSTAL_BUILD_COUNT_MISMATCH",
        )
        objects.close()
        index_writer.close()
        with io.bounded_connection(work / "spill") as connection:
            relations.append(
                io.canonicalize(
                    connection,
                    "reference_object",
                    objects.paths,
                    root / "reference_object",
                )
            )
            ordered = io.RelationWriter(root / "reference_index", p.GN_INDEX_SCHEMA)
            for row in io.sorted_rows(
                connection,
                f"SELECT * FROM {io.parquet_sql(index_writer.paths)} ORDER BY country,postcode,reference_object_id",
            ):
                ordered.append(row)
            ordered.close()
            index_logical = index_fingerprint(
                ordered.rows,
                io.sorted_rows(
                    connection,
                    f"SELECT * FROM {io.parquet_sql(ordered.paths)} ORDER BY reference_object_id",
                ),
            )
        index = {
            "recipe": p.INDEX_VERSION,
            "physical_order": ["country", "postcode", "reference_object_id"],
            "row_count": ordered.rows,
            "schema_sha256": index_schema_fingerprint().hex(),
            "logical_sha256": index_logical.hex(),
            "files": [
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": c.sha256_file(path),
                }
                for path in ordered.paths
            ],
        }
        return {
            "manifest_version": c.MANIFEST_VERSION,
            "kind": "STAGE09_PUBLIC_REFERENCE_PACK",
            "status": "DEVELOPMENT_CANDIDATE_NOT_ACCEPTED",
            "lock_sha256": c.LOCK_SHA256,
            "relations": relations,
            "reference_index": index,
            "logical_sha256": pack_logical_fingerprint(relations, index).hex(),
            "operational_provenance": {
                "execution_git_sha": execution_sha,
                "job_id": os.environ.get("SLURM_JOB_ID", "SYNTHETIC"),
                "publication_protocol": publication.PROTOCOL,
                "semantic_runtime": list(c.SEMANTIC_RUNTIME),
                "raw_reference_root": str(inputs.root),
                "preserved_build_work": str(work),
            },
            "projection": {
                "coordinates": False,
                "accuracy_fields": False,
                "geocoder_entities": False,
                "metadata_aliases_generated": False,
                "geonames_negative_authority": False,
            },
        }

    return io.publish(
        final,
        build,
        lambda root, digest, published: validate_public_pack(
            root,
            digest,
            inputs=inputs,
            published=published,
            execution_sha=execution_sha,
        ),
    )


def validate_public_pack(
    root: Path,
    manifest_sha: str,
    *,
    inputs: p.PublicInputs,
    published: io.PublicationState = True,
    execution_sha: str | None = None,
) -> dict[str, Any]:
    manifest = io.validate_terminal(root, manifest_sha, published)
    if execution_sha is not None:
        c.require(
            manifest["operational_provenance"]["execution_git_sha"] == execution_sha,
            "PUBLIC_PACK_EXECUTABLE_BINDING_MISMATCH",
        )
    c.require(
        manifest["kind"] == "STAGE09_PUBLIC_REFERENCE_PACK"
        and manifest["lock_sha256"] == c.LOCK_SHA256,
        "PUBLIC_PACK_LOCK_BINDING_MISMATCH",
    )
    c.require(
        [r["name"] for r in manifest["relations"]]
        == ["reference_registry", "reference_capability", "reference_object"],
        "PUBLIC_PACK_RELATION_SET_INVALID",
    )
    inventory = io.terminal_files(published)
    relation_paths = {}
    for relation in manifest["relations"]:
        relation_paths[relation["name"]] = io.validate_relation(root, relation)
        inventory.extend(r["relative_path"] for r in relation["files"])
    index = manifest["reference_index"]
    c.require(
        index["schema_sha256"] == index_schema_fingerprint().hex()
        and index["recipe"] == p.INDEX_VERSION
        and index["physical_order"] == ["country", "postcode", "reference_object_id"],
        "INDEX_RECIPE_MISMATCH",
    )
    paths = []
    for record in index["files"]:
        path = p.confined(root, record["relative_path"])
        c.require(
            path.stat().st_size == record["bytes"]
            and c.sha256_file(path) == record["sha256"],
            "INDEX_PHYSICAL_HASH_MISMATCH",
        )
        c.require(
            pq.read_schema(path).equals(p.GN_INDEX_SCHEMA, check_metadata=True),
            "INDEX_SCHEMA_MISMATCH",
        )
        paths.append(path)
        inventory.append(record["relative_path"])
    audit_work = Path(tempfile.mkdtemp(prefix=".stage09-index-audit-", dir=root.parent))
    with io.bounded_connection(audit_work / "spill") as connection:
        c.require(
            index_fingerprint(
                index["row_count"],
                io.sorted_rows(
                    connection,
                    f"SELECT * FROM {io.parquet_sql(paths)} ORDER BY reference_object_id",
                ),
            ).hex()
            == index["logical_sha256"],
            "INDEX_LOGICAL_HASH_MISMATCH",
        )
    c.require(
        pack_logical_fingerprint(manifest["relations"], index).hex()
        == manifest["logical_sha256"],
        "PUBLIC_PACK_LOGICAL_HASH_MISMATCH",
    )
    # Independently rederive the index from the authoritative public objects,
    # streaming in the same object-ID order. No copied raw data is needed.
    projected = (
        p.geonames_index_row(obj)
        for obj in io.parquet_rows(relation_paths["reference_object"])
        if obj["object_kind"] == "POSTAL_ASSOCIATION"
    )
    c.require(
        index_fingerprint(index["row_count"], projected).hex()
        == index["logical_sha256"],
        "INDEX_PROJECTION_NOT_EXACT",
    )
    registry = list(io.parquet_rows(relation_paths["reference_registry"]))
    versions = {r["reference_version_id"]: r for r in registry}
    c.require(
        {r["reference_id"] for r in registry} == set(c.FAMILIES),
        "PUBLIC_PACK_FAMILY_SET_INVALID",
    )
    for capability in io.parquet_rows(relation_paths["reference_capability"]):
        c.require(
            capability["reference_version_id"] in versions,
            "CAPABILITY_VERSION_FK_INVALID",
        )
        original_id = capability["capability_id"]
        c.require(
            p.set_capability_id(dict(capability))["capability_id"] == original_id,
            "CAPABILITY_IDENTITY_INVALID",
        )
        if capability["negative_authority"]:
            family = versions[capability["reference_version_id"]]["reference_id"]
            c.require(
                (
                    family == c.ISO
                    and capability["question_catalog_id"] == "Q02"
                    and capability["negative_authority_basis"] == "EXPLICIT_CODE_PARENT"
                )
                or (
                    family == c.LIA
                    and capability["question_catalog_id"] in ("Q04", "Q08")
                    and capability["negative_authority_basis"] == "EXPLICIT_FORMAT_RULE"
                ),
                "PUBLIC_PACK_NEGATIVE_AUTHORITY_INVALID",
            )
    validate_raw_projection(root, relation_paths, inputs)
    io.topology(root, inventory)
    return manifest


def validate_raw_projection(
    root: Path, paths: Mapping[str, Sequence[Path]], inputs: p.PublicInputs
) -> None:
    """Compare every object/field with its locked raw origin, using bounded RAM.

    Scientific object IDs deliberately identify locators, not field contents;
    checking those IDs and a self-consistent index alone is not sufficient.
    This also enforces all capability flags and disabled-country selectors.
    """
    c.require(
        list(io.parquet_rows(paths["reference_registry"])) == list(inputs.registry),
        "REGISTRY_RAW_LOCK_DERIVATION_MISMATCH",
    )
    iso, metadata = inputs.small_objects()
    matrix = p.matrix_capabilities(inputs.lock, inputs.registry)
    version = next(
        r["reference_version_id"] for r in inputs.registry if r["reference_id"] == c.LIA
    )
    expected_caps = sorted(
        matrix
        + p.metadata_rule_capabilities(
            metadata, [r for r in matrix if r["reference_version_id"] == version]
        ),
        key=lambda r: r["capability_id"],
    )
    c.require(
        all(
            a == b
            for a, b in zip_longest(
                expected_caps, io.parquet_rows(paths["reference_capability"])
            )
        ),
        "CAPABILITY_RAW_LOCK_DERIVATION_MISMATCH",
    )
    work = Path(tempfile.mkdtemp(prefix=".stage09-public-raw-audit-", dir=root.parent))
    with io.bounded_connection(work / "spill") as db:
        objects = io.parquet_sql(paths["reference_object"])
        observed_small = io.sorted_rows(
            db,
            f"SELECT * FROM {objects} WHERE object_kind<>'POSTAL_ASSOCIATION' ORDER BY reference_object_id",
        )
        c.require(
            all(
                a == b
                for a, b in zip_longest(
                    sorted(iso + metadata, key=lambda r: r["reference_object_id"]),
                    observed_small,
                )
            ),
            "SMALL_REFERENCE_RAW_DERIVATION_MISMATCH",
        )
        observed_postal = io.sorted_rows(
            db,
            f"SELECT * FROM {objects} WHERE object_kind='POSTAL_ASSOCIATION' ORDER BY CAST(split_part(source_locator,':',-1) AS UBIGINT)",
        )
        c.require(
            all(
                a == b for a, b in zip_longest(inputs.postal_objects(), observed_postal)
            ),
            "POSTAL_RAW_DERIVATION_MISMATCH",
        )

"""Machine-readable assets derived exactly from the owner-frozen design."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import s11_semantic_contract as c
from . import s11_semantic_input as inputs
from . import s11_semantic_summary as summary


def assets(repository: Path) -> dict[str, dict[str, Any]]:
    contract = c.contract_asset(repository)
    profile = c.profile_asset(hashlib.sha256(c.canonical(contract)).hexdigest())
    descriptors = [
        c.descriptor("semantic_request"),
        c.descriptor("hypothesis_request_map"),
        summary.descriptor(),
    ]
    return {
        c.CONTRACT: contract,
        c.PROFILE: profile,
        c.SCHEMA: {
            "schema_version": c.SCHEMA,
            "encoding_version": c.ENCODING,
            "descriptors": descriptors,
            "fingerprint_domain": "SAFE:stage11-schema-bundle:v1",
        },
        "stage11_semantic_request_descriptor_v1": c.descriptor("semantic_request"),
        "stage11_hypothesis_request_map_descriptor_v1": c.descriptor(
            "hypothesis_request_map"
        ),
        "stage11_semantic_request_summary_descriptor_v1": summary.descriptor(),
    }


def identifiers(repository: Path) -> dict[str, str]:
    values = assets(repository)
    hashes = {k: hashlib.sha256(c.canonical(v)).hexdigest() for k, v in values.items()}
    schema = c.identity(
        "stage11-schema-bundle:v1",
        *(
            bytes.fromhex(hashes[n])
            for n in (
                "stage11_semantic_request_descriptor_v1",
                "stage11_hypothesis_request_map_descriptor_v1",
                "stage11_semantic_request_summary_descriptor_v1",
            )
        ),
    )
    return {
        "contract_sha256": hashes[c.CONTRACT],
        "profile_sha256": hashes[c.PROFILE],
        "schema_bundle_sha256": schema.hex(),
    }


def verify(repository: Path) -> dict[str, str]:
    for name, value in assets(repository).items():
        c.require(
            (repository / "docs/scientific_assets" / (name + ".json")).read_bytes()
            == c.canonical(value),
            "S11_INPUT_BINDING_INVALID",
        )
    return identifiers(repository)


def verify_implementation(repository: Path) -> None:
    record = c.decode_json(
        (
            repository
            / "docs/scientific_assets/stage11_implementation_inventory_v1.json"
        ).read_bytes()
    )
    c.require(
        record["inventory_version"] == "stage11_implementation_inventory_v1"
        and hashlib.sha256(c.canonical(record["files"])).hexdigest()
        == record["files_sha256"],
        "S11_INPUT_BINDING_INVALID",
    )
    names = []
    for item in record["files"]:
        path = repository / item["path"]
        c.require(
            path.is_relative_to(repository)
            and not path.is_symlink()
            and path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "S11_INPUT_BINDING_INVALID",
        )
        names.append(item["path"])
    c.require(names == sorted(set(names)), "S11_INPUT_BINDING_INVALID")


def materialize(repository: Path) -> None:
    """Local implementation-time command only; does not read protected data."""
    directory = repository / "docs/scientific_assets"
    for name, value in assets(repository).items():
        (directory / (name + ".json")).write_bytes(c.canonical(value))
    manifest = c.decode_json(
        (directory / "stage10_remediated_manifest_1785683.json").read_bytes()
    )
    (directory / "stage11_input_binding_v1.json").write_bytes(
        c.canonical(inputs.input_asset(manifest, identifiers(repository)))
    )


def dataset(
    binding: bytes,
    asset_ids: dict[str, str],
    relations: list[dict[str, Any]],
    summary_sha: str,
) -> bytes:
    c.require(
        [r["name"] for r in relations] == list(c.RELATIONS), "S11_INPUT_BINDING_INVALID"
    )
    return c.identity(
        "stage11-dataset:v1",
        binding,
        bytes.fromhex(asset_ids["contract_sha256"]),
        bytes.fromhex(asset_ids["profile_sha256"]),
        bytes.fromhex(asset_ids["schema_bundle_sha256"]),
        c.ENCODING,
        bytes.fromhex(relations[0]["logical_sha256"]),
        relations[0]["row_count"],
        bytes.fromhex(relations[1]["logical_sha256"]),
        relations[1]["row_count"],
        bytes.fromhex(summary_sha),
    )

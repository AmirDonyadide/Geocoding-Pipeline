#!/usr/bin/env python3
"""Read-only portable Stage 10 code/design/runtime inventory validation."""

from __future__ import annotations

import hashlib
import json
import re

import pyarrow as pa
from pathlib import Path

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import (
    s10_query_execution as execution,
)
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_runtime_lock as lock

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs/scientific_assets"


def main() -> int:
    execution.verify_design(ROOT)
    runtime = c.read_json(ASSETS / "stage10_runtime_goethe_v1/runtime_build_lock.json")
    c.require(
        c.sha256_file(ASSETS / "stage10_runtime_goethe_v1/runtime_build_lock.json")
        == execution.RUNTIME_LOCK_SHA,
        "STAGE10_PORTABLE_RUNTIME_LOCK_MISMATCH",
    )
    c.require(
        lock.source_dependencies(ROOT) == runtime["runtime_source_sha256"],
        "STAGE10_LOCKED_SOURCE_CHANGED",
    )
    c.require(
        lock.semantic_fingerprint(runtime) == execution.SEMANTIC_RUNTIME,
        "STAGE10_RUNTIME_SEMANTIC_MISMATCH",
    )
    profile = c.read_json(ASSETS / "stage10_execution_profile_v1.json")
    science = bytes.fromhex(profile["science_sha256"])
    asset = c.identity(
        "stage10-transform-assets:v1",
        bytes.fromhex(profile["transliteration_spec_sha256"]),
        bytes.fromhex(execution.RUNTIME_LOCK_SHA),
    )
    c.require(
        profile["contract_sha256"] == c.contract_fingerprint().hex()
        and profile["schema_bundle_sha256"] == c.schema_bundle_fingerprint().hex()
        and profile["profile_sha256"] == io.profile_fingerprint(science).hex()
        and science == c.science_fingerprint(asset)
        and profile["operating_budget"] is None,
        "STAGE10_EXECUTION_PROFILE_MISMATCH",
    )
    descriptor = c.read_json(ASSETS / "stage10_schema_descriptor_v1.json")
    c.require(
        descriptor["schema_bundle_sha256"] == c.schema_bundle_fingerprint().hex(),
        "STAGE10_SCHEMA_DESCRIPTOR_MISMATCH",
    )
    c.require(
        [r["name"] for r in descriptor["relations"]] == list(c.RELATIONS),
        "STAGE10_SCHEMA_RELATION_SET_MISMATCH",
    )
    for relation in descriptor["relations"]:
        schema = pa.ipc.read_schema(
            pa.BufferReader(bytes.fromhex(relation["arrow_schema_ipc_hex"]))
        )
        c.require(
            schema.equals(io.output_schema(relation["name"]), check_metadata=True)
            and relation["schema_sha256"]
            == c.schema_fingerprint(relation["name"]).hex(),
            "STAGE10_SCHEMA_DESCRIPTOR_MISMATCH",
        )
    inventory = c.read_json(ASSETS / "stage10_implementation_inventory_v1.json")
    names = []
    for item in inventory["files"]:
        path = ROOT / item["path"]
        c.require(
            path.is_relative_to(ROOT) and not path.is_symlink(),
            "STAGE10_INVENTORY_PATH_INVALID",
        )
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_IMPLEMENTATION_INVENTORY_MISMATCH",
        )
        names.append(item["path"])
    c.require(names == sorted(set(names)), "STAGE10_INVENTORY_ORDER_INVALID")
    c.require(
        inventory["files_sha256"]
        == hashlib.sha256(c.canonical(inventory["files"])).hexdigest(),
        "STAGE10_INVENTORY_DIGEST_INVALID",
    )
    for name in (
        "stage10_execution_profile_v1.json",
        "stage10_schema_descriptor_v1.json",
        "stage10_implementation_inventory_v1.json",
    ):
        raw = (ASSETS / name).read_bytes()
        c.require(
            raw == c.canonical(c.read_json(ASSETS / name)),
            "STAGE10_JSON_CANONICAL_MISMATCH",
        )
        json.loads(raw)
    # New links/anchors only; accepted historical documents are unchanged.
    document = ROOT / "docs/stages/STAGE10_IMPLEMENTATION.md"
    for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
        if target.startswith(("https://", "http://")):
            continue
        path, _, anchor = target.partition("#")
        linked = (document.parent / path).resolve() if path else document
        c.require(linked.is_file(), "STAGE10_DOCUMENT_LINK_MISSING")
        if anchor:
            headings = re.findall(r"^#+\s+(.+)$", linked.read_text(), re.MULTILINE)
            slugs = {
                re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
                for text in headings
            }
            c.require(anchor in slugs, "STAGE10_DOCUMENT_ANCHOR_MISSING")
    print("STAGE10_IMPLEMENTATION_INVENTORY_VALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

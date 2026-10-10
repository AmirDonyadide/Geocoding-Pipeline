"""Exclusively invented Stage 12 fixtures; no paths to accepted row-level data."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing.stages import s12_campaign as campaign
from safe_geocoding_pipeline.preprocessing.stages import s12_deployment as deployment
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as operations
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

HASH = c.sha(b"invented stage12 test binding")
NOW = datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)


def core(
    *, structured: bool = False, text: str = "Invented Café + 7%\nخیابان"
) -> dict[str, Any]:
    return {
        **s11.CONSTANTS,
        "endpoint": "/v1/search/structured" if structured else "/v1/search",
        "search_mode": "STRUCTURED" if structured else "FULL_TEXT",
        "text": None if structured else text,
        "address": text if structured else None,
        "postalcode": "00123" if structured else None,
        "locality": None,
        "boundary_country": "DE",
    }


def cores() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    index = {k: {"invented_evidence": k} for k in deployment.CORE_KEYS["index"]}
    effective = {k: {"invented_evidence": k} for k in deployment.CORE_KEYS["effective"]}
    deploy = {k: {"invented_evidence": k} for k in deployment.CORE_KEYS["deployment"]}
    for kind, obj in (
        ("index", index),
        ("effective", effective),
        ("deployment", deploy),
    ):
        obj["schema_version"] = deployment.VERSIONS[kind]  # type: ignore[assignment]
    return index, effective, deploy


def feature() -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [-0.0, 52.123456789012345]},
        "properties": {
            "layer": "address",
            "source": "synthetic",
            "gid": "synthetic:address:0001",
            "source_id": "0001",
            "confidence": 0.1,
            "match_type": "exact",
            "accuracy": "point",
            "label": "Invented Café",
            "housenumber": "001",
            "country_a": "DEU",
        },
    }


def body(features: list[dict[str, Any]] | None = None) -> bytes:
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [feature(), feature()] if features is None else features,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def extract(
    raw: bytes, capture: dict[str, Any], *, size: int = 3
) -> response.Projection:
    return response.extract(
        raw,
        bytes.fromhex(capture["request_execution_id"]),
        size=size,
        http_status=capture["http_status"],
        content_type=capture["content_type"],
        encoding=capture["content_encoding"],
        layers=frozenset({"address", "street", "locality"}),
        sources=frozenset({"synthetic"}),
        expected_echo={},
        expected_hash=bytes.fromhex(capture["response_sha256"]),
    )


def setup(root: Path) -> tuple[dict[str, str], bytes]:
    value = core()
    retrieval = c.policy(3)
    deploy = deployment.content_identity(*cores())
    execution = deploy.execution_binding(
        s11.semantic_id(s11.core_bytes(value)), retrieval["retrieval_policy_id"], HASH
    )
    provenance = {
        k: HASH.hex()
        for k in campaign.START_KEYS
        if k not in ("campaign_version", "campaign_id")
    }
    provenance.update(
        {
            k: v.hex()
            for k, v in execution.items()
            if k not in ("identity_version", "query_semantic_id")
        }
    )
    provenance.update(
        executable_sha="1" * 40,
        operations_policy_sha256=operations.Operations().fingerprint().hex(),
    )
    start = campaign.create(root / "campaign", provenance)
    binding = campaign.checkpoint_binding(start, execution)
    target, _ = c.materialize(
        value, execution["query_semantic_id"], retrieval, target_limit=10000
    )
    return binding, target

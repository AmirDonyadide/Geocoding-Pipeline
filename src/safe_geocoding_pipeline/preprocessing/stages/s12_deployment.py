"""Content identity, separate authenticity and fail-closed deployment continuity.

Interfaces consume operator/administrative evidence; no server capability or
manifest endpoint is assumed. Missing evidence never becomes an identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from . import s12_retrieval_contract as c

MANIFEST = "stage12_pelias_deployment_manifest_v1"
CORE_KEYS = {
    "index": tuple(
        "schema_version search_engine aliases indexes snapshot imports auxiliary_data immutability".split()
    ),
    "effective": tuple(
        "schema_version endpoints omitted_layers omitted_sources no_override_language forbidden_injection search_behavior response_behavior".split()
    ),
    "deployment": tuple(
        "schema_version logical_deployment_name service_view_id applications result_configuration routes".split()
    ),
}
VERSIONS = {
    "index": "stage12_index_core_v1",
    "effective": "stage12_effective_behavior_v1",
    "deployment": "stage12_deployment_core_v1",
}
OBSERVABILITY = (
    "OBSERVABLE_AUTOMATICALLY",
    "OBSERVABLE_WITH_OPERATOR_MANIFEST",
    "NOT_CURRENTLY_OBSERVABLE",
    "UNKNOWN",
)


def core_bytes(kind: str, obj: Mapping[str, Any]) -> bytes:
    c.require(
        kind in CORE_KEYS and type(obj) is dict and set(obj) == set(CORE_KEYS[kind]),
        "IDENTITY_UNVERIFIABLE",
    )
    c.require(obj["schema_version"] == VERSIONS[kind], "IDENTITY_UNVERIFIABLE")
    return c.canonical(dict(obj))


@dataclass(frozen=True)
class Deployment:
    """Canonical immutable copies prevent post-verification object mutation."""

    index_core: bytes
    effective_core: bytes
    deployment_core: bytes
    index_data_identity: bytes
    effective_behavior_id: bytes
    pelias_deployment_fingerprint: bytes
    effective_no_override_language_behavior_id: bytes

    def execution_binding(
        self, semantic: bytes, policy: bytes, materialization: bytes
    ) -> dict[str, Any]:
        return dict(
            zip(
                c.EXECUTION_FIELDS,
                (
                    c.IDENTITY,
                    c.digest(semantic),
                    c.digest(policy),
                    c.digest(materialization),
                    self.pelias_deployment_fingerprint,
                    self.index_data_identity,
                    self.effective_behavior_id,
                ),
                strict=True,
            )
        )


def content_identity(
    index: Mapping[str, Any],
    effective: Mapping[str, Any],
    deployment: Mapping[str, Any],
) -> Deployment:
    """Hash content only. This function does not assert authenticity/completeness."""
    index_raw, effective_raw, deployment_raw = (
        core_bytes("index", index),
        core_bytes("effective", effective),
        core_bytes("deployment", deployment),
    )
    index_id = c.identity(
        "SAFE:stage12-index-data:v1",
        [("manifest_version", MANIFEST), ("index_core", index_raw)],
    )
    effective_id = c.identity(
        "SAFE:stage12-effective-behavior:v1",
        [
            ("behavior_version", VERSIONS["effective"]),
            ("effective_core", effective_raw),
        ],
    )
    deployment_id = c.identity(
        "SAFE:stage12-pelias-deployment:v1",
        [
            ("manifest_version", MANIFEST),
            ("deployment_core", deployment_raw),
            ("index_data_identity", index_id),
            ("effective_behavior_id", effective_id),
        ],
    )
    language_id = c.identity(
        "SAFE:stage12-no-override-language:v1",
        [
            ("behavior_version", VERSIONS["effective"]),
            ("language_core", c.canonical(effective["no_override_language"])),
        ],
    )
    return Deployment(
        index_raw,
        effective_raw,
        deployment_raw,
        index_id,
        effective_id,
        deployment_id,
        language_id,
    )


@dataclass(frozen=True)
class Evidence:
    """A verifier's result, bound to archived evidence and a coverage interval.

    Signature verification, topology/content acquisition and operator exclusion
    review are separate checks. A signature alone cannot establish immutability.
    """

    deployment_fingerprint: bytes
    receipt_sha256: bytes
    authenticated: bool
    immutable_content_verified: bool
    maintenance_controls_verified: bool
    route_uniformity_verified: bool
    no_secret_echo_verified: bool
    logging_controls_verified: bool
    continuity_verified: bool
    acquired_monotonic_ms: int
    valid_until_monotonic_ms: int
    completed_responses: int
    interval_closed: bool
    generation_identity: bytes | None

    def validate(self, deployment: Deployment, now_ms: int, *, protected: bool) -> None:
        c.digest(self.receipt_sha256)
        c.require(
            self.deployment_fingerprint == deployment.pelias_deployment_fingerprint,
            "DEPLOYMENT_IDENTITY_FAILURE",
        )
        checks = (
            self.authenticated,
            self.immutable_content_verified,
            self.maintenance_controls_verified,
            self.route_uniformity_verified,
            self.no_secret_echo_verified,
            self.continuity_verified,
        )
        c.require(all(v is True for v in checks), "IDENTITY_UNVERIFIABLE")
        c.require(
            not protected or self.logging_controls_verified is True,
            "IDENTITY_UNVERIFIABLE",
        )
        c.require(
            0 <= self.acquired_monotonic_ms <= now_ms <= self.valid_until_monotonic_ms,
            "IDENTITY_UNVERIFIABLE",
        )


def verify_authenticity(
    content: bytes, signature: bytes, *, verifier: Callable[[bytes, bytes], bool]
) -> bytes:
    """Verifier is configured with a pinned approved key, never key data from input."""
    try:
        valid = verifier(content, signature)
    except Exception:
        valid = False
    c.require(valid is True, "DEPLOYMENT_AUTHENTICITY_FAILURE")
    # This receipt identity is audit-only and deliberately excluded from content IDs.
    return c.sha(c.framed([c.sha(content), c.sha(signature)]))


class DriftGuard:
    def __init__(self, deployment: Deployment, mode: str, *, protected: bool = True):
        c.require(
            mode in ("PER_RESPONSE_GENERATION", "CONTROLLED_CAMPAIGN"),
            "IDENTITY_UNVERIFIABLE",
        )
        self.deployment = deployment
        self.mode = mode
        self.protected = protected
        self.current: Evidence | None = None
        self.completed = 0
        self.quarantined = False

    def accept(self, evidence: Evidence, now_ms: int) -> None:
        c.require(not self.quarantined, "DEPLOYMENT_IDENTITY_FAILURE")
        try:
            evidence.validate(self.deployment, now_ms, protected=self.protected)
            c.require(
                evidence.completed_responses == self.completed, "IDENTITY_UNVERIFIABLE"
            )
            if self.mode == "PER_RESPONSE_GENERATION":
                c.digest(evidence.generation_identity)
            self.current = evidence
        except c.Stage12Error:
            self.quarantined = True
            raise

    def before_dispatch(self, now_ms: int) -> bytes:
        c.require(
            not self.quarantined and self.current is not None, "IDENTITY_UNVERIFIABLE"
        )
        assert self.current is not None
        self.current.validate(self.deployment, now_ms, protected=self.protected)
        c.require(
            now_ms - self.current.acquired_monotonic_ms < 60_000
            and self.completed - self.current.completed_responses < 100,
            "IDENTITY_VERIFICATION_STALE",
        )
        return self.current.receipt_sha256

    def response(self, now_ms: int, generation: bytes | None = None) -> None:
        try:
            self.before_dispatch(now_ms)
            assert self.current is not None
            if self.mode == "PER_RESPONSE_GENERATION":
                c.require(
                    c.digest(generation) == self.current.generation_identity,
                    "DEPLOYMENT_IDENTITY_FAILURE",
                )
            self.completed += 1
        except c.Stage12Error:
            self.quarantined = True
            raise

    def close(self, evidence: Evidence, now_ms: int) -> bytes:
        self.accept(evidence, now_ms)
        c.require(evidence.interval_closed is True, "IDENTITY_INTERVAL_NOT_CLOSED")
        return evidence.receipt_sha256

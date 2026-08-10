from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from ..phase02.fingerprints import fingerprint
from .constants import PILOT_SEED_DOMAIN
from .models import PilotCandidate, PilotSeal


@dataclass(frozen=True, slots=True)
class PilotSamplingConfig:
    development_count: int = 8_000
    locked_evaluation_count: int = 4_000
    minimum_per_stratum: int = 50
    maximum_primary_stratum: int = 500
    primary_stratum: str = "country_cohort"
    pilot_version: str = "phase03_pilot_v1"
    seed_domain: bytes = PILOT_SEED_DOMAIN

    @property
    def total_count(self) -> int:
        return self.development_count + self.locked_evaluation_count

    def fingerprint(self) -> str:
        return fingerprint(
            {
                "development_count": self.development_count,
                "locked_evaluation_count": self.locked_evaluation_count,
                "minimum_per_stratum": self.minimum_per_stratum,
                "maximum_primary_stratum": self.maximum_primary_stratum,
                "primary_stratum": self.primary_stratum,
                "pilot_version": self.pilot_version,
                "seed_domain_hex": self.seed_domain.hex(),
            }
        )


@dataclass(frozen=True, slots=True)
class PilotSelection:
    development_ids: tuple[bytes, ...]
    locked_evaluation_ids: tuple[bytes, ...]
    seal: PilotSeal

    def portable_summary(self) -> dict[str, str | int]:
        return self.seal.portable_dict()


def _score(domain: bytes, stable_id: bytes) -> bytes:
    return hashlib.sha256(domain + b"\0" + stable_id).digest()


def _identity_digest(domain: bytes, identities: Iterable[bytes]) -> str:
    values = sorted(identities)
    digest = hashlib.sha256(domain)
    digest.update(len(values).to_bytes(8, "big"))
    for value in values:
        digest.update(value)
    return digest.hexdigest()


def select_and_seal_pilot(
    population: Iterable[PilotCandidate],
    *,
    config: PilotSamplingConfig,
    input_phase02_manifest_identity: str,
    selection_timestamp: str | None = None,
) -> PilotSelection:
    candidates = sorted(population, key=lambda item: item.stable_source_row_id_v1)
    identities = [item.stable_source_row_id_v1 for item in candidates]
    if len(set(identities)) != len(identities):
        raise ValueError("pilot population contains duplicate stable IDs")
    if config.total_count < 1 or config.minimum_per_stratum < 1:
        raise ValueError("pilot counts must be positive")
    if len(candidates) < config.total_count:
        raise ValueError("pilot population is smaller than requested sample")

    groups: dict[tuple[str, str], list[PilotCandidate]] = {}
    for candidate in candidates:
        for key, value in sorted(candidate.strata.items()):
            groups.setdefault((key, value), []).append(candidate)
    selected: dict[bytes, PilotCandidate] = {
        item.stable_source_row_id_v1: item
        for item in candidates
        if item.targeted_safety_case
    }
    primary_counts: dict[str, int] = {}
    for item in selected.values():
        primary = item.strata.get(config.primary_stratum, "")
        primary_counts[primary] = primary_counts.get(primary, 0) + 1

    def eligible(item: PilotCandidate) -> bool:
        primary = item.strata.get(config.primary_stratum, "")
        return primary_counts.get(primary, 0) < config.maximum_primary_stratum

    def add(item: PilotCandidate) -> bool:
        if item.stable_source_row_id_v1 in selected:
            return True
        if not eligible(item) or len(selected) >= config.total_count:
            return False
        selected[item.stable_source_row_id_v1] = item
        primary = item.strata.get(config.primary_stratum, "")
        primary_counts[primary] = primary_counts.get(primary, 0) + 1
        return True

    quota_domain = config.seed_domain + b":quota"
    for group_key in sorted(groups):
        group = sorted(
            groups[group_key],
            key=lambda item: _score(quota_domain, item.stable_source_row_id_v1),
        )
        target = min(len(group), config.minimum_per_stratum)
        represented = sum(item.stable_source_row_id_v1 in selected for item in group)
        for item in group:
            before = item.stable_source_row_id_v1 in selected
            if add(item) and not before:
                represented += 1
            if represented >= target:
                break
        if represented < target:
            raise ValueError("pilot quotas/caps cannot satisfy minimum stratum quota")

    fill_domain = config.seed_domain + b":fill"
    for item in sorted(
        candidates,
        key=lambda candidate: _score(fill_domain, candidate.stable_source_row_id_v1),
    ):
        if len(selected) == config.total_count:
            break
        add(item)
    if len(selected) != config.total_count:
        raise ValueError("pilot quotas/caps cannot produce the requested sample")

    split_domain = config.seed_domain + b":split"
    ordered = sorted(selected, key=lambda identity: _score(split_domain, identity))
    development = tuple(ordered[: config.development_count])
    locked = tuple(ordered[config.development_count :])
    timestamp = selection_timestamp or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    seal = PilotSeal(
        pilot_version=config.pilot_version,
        sampling_config_fingerprint=config.fingerprint(),
        seed=config.seed_domain.decode("utf-8"),
        development_identity_digest=_identity_digest(
            b"phase03:development_identities_v1\0", development
        ),
        locked_evaluation_identity_digest=_identity_digest(
            b"phase03:locked_identities_v1\0", locked
        ),
        selection_timestamp=timestamp,
        input_phase02_manifest_identity=input_phase02_manifest_identity,
        development_count=len(development),
        locked_evaluation_count=len(locked),
    )
    return PilotSelection(development, locked, seal)

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RawSpan:
    source_field: str
    start_character: int
    end_character_exclusive: int

    def validate(self, raw_value: str) -> None:
        if (
            not 0
            <= self.start_character
            < self.end_character_exclusive
            <= len(raw_value)
        ):
            raise ValueError("invalid raw source span")


@dataclass(frozen=True, slots=True)
class Candidate:
    component: str
    value: str
    representation: str
    confidence: str
    rule_id: str
    selection_priority: int
    selectable: bool
    spans: tuple[RawSpan, ...]
    source_fields: tuple[str, ...]
    conflict_behavior: str = "NONE"

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("candidate value cannot be empty")
        if not self.spans:
            raise ValueError("candidate must retain at least one raw source span")


@dataclass(frozen=True, slots=True)
class SelectedComponent:
    component: str
    representation: str
    value: str
    confidence: str
    source_fields: tuple[str, ...]
    rule_ids: tuple[str, ...]


@dataclass(slots=True)
class TransformResult:
    core_row: dict[str, Any]
    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    candidates: tuple[Candidate, ...] = ()


@dataclass(frozen=True, slots=True)
class PilotCandidate:
    stable_source_row_id_v1: bytes
    strata: dict[str, str]
    targeted_safety_case: bool = False

    def __post_init__(self) -> None:
        if len(self.stable_source_row_id_v1) != 32:
            raise ValueError("pilot stable ID must be 32 bytes")


@dataclass(frozen=True, slots=True)
class PilotSeal:
    pilot_version: str
    sampling_config_fingerprint: str
    seed: str
    development_identity_digest: str
    locked_evaluation_identity_digest: str
    selection_timestamp: str
    input_phase02_manifest_identity: str
    development_count: int
    locked_evaluation_count: int

    def portable_dict(self) -> dict[str, str | int]:
        return {
            "pilot_version": self.pilot_version,
            "sampling_config_fingerprint": self.sampling_config_fingerprint,
            "seed": self.seed,
            "development_identity_digest": self.development_identity_digest,
            "locked_evaluation_identity_digest": self.locked_evaluation_identity_digest,
            "selection_timestamp": self.selection_timestamp,
            "input_phase02_manifest_identity": self.input_phase02_manifest_identity,
            "development_count": self.development_count,
            "locked_evaluation_count": self.locked_evaluation_count,
        }

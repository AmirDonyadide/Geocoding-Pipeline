from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..phase02.fingerprints import fingerprint
from .constants import (
    CLEANING_RULES_VERSION,
    COMPONENT_SCHEMA_VERSION,
    DIAGNOSTIC_VOCABULARY_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    EXPECTED_PYTHON_VERSION,
    EXPECTED_UNICODE_VERSION,
    PARSER_VERSION,
    PHASE03_VERSION,
    PLACEHOLDER_POLICY_VERSION,
    RULE_REGISTRY_VERSION,
)


@dataclass(frozen=True, slots=True)
class Phase03Config:
    phase02_run_id: str = "phase02_20260810T173851Z_1349152b"
    output_root: Path = Path("derived/controlled/phase03_v1/runs")
    reports_root: Path = Path("reports/generated/phase03")
    per_field_freeform_limit_bytes: int = 65_536
    combined_freeform_limit_bytes: int = 262_144
    max_candidates_per_component: int = 8
    max_candidates_per_row: int = 64
    batch_rows: int = 25_000
    compression: str = "zstd"
    compression_level: int = 3
    parquet_version: str = "2.4"
    data_page_version: str = "1.0"
    expected_python_version: tuple[int, int, int] = EXPECTED_PYTHON_VERSION
    expected_unicode_version: str = EXPECTED_UNICODE_VERSION
    parser_version: str = PARSER_VERSION
    rule_registry_version: str = RULE_REGISTRY_VERSION
    cleaning_rules_version: str = CLEANING_RULES_VERSION
    placeholder_policy_version: str = PLACEHOLDER_POLICY_VERSION
    country_reference_version: str = "pending_pinned_reference_manifest"
    unicode_reference_version: str = "unicode_16.0.0_pending_scripts_digest"
    diagnostic_vocabulary_version: str = DIAGNOSTIC_VOCABULARY_VERSION
    component_schema_version: str = COMPONENT_SCHEMA_VERSION
    evidence_schema_version: str = EVIDENCE_SCHEMA_VERSION
    phase03_version: str = PHASE03_VERSION

    def validate(self) -> None:
        for name in (
            "per_field_freeform_limit_bytes",
            "combined_freeform_limit_bytes",
            "max_candidates_per_component",
            "max_candidates_per_row",
            "batch_rows",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_candidates_per_component > self.max_candidates_per_row:
            raise ValueError("per-component candidate limit exceeds per-row limit")
        if self.compression != "zstd" or self.compression_level != 3:
            raise ValueError(
                "Phase 3 synthetic framework uses provisional ZSTD level 3"
            )
        if self.parquet_version != "2.4" or self.data_page_version != "1.0":
            raise ValueError(
                "Phase 3 framework requires Parquet logical 2.4/data-page 1.0 "
                "to preserve the approved uint32 evidence ID"
            )

    def fingerprint_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["output_root"] = self.output_root.as_posix()
        payload["reports_root"] = self.reports_root.as_posix()
        payload["expected_python_version"] = list(self.expected_python_version)
        return payload

    def configuration_fingerprint(self) -> bytes:
        return bytes.fromhex(fingerprint(self.fingerprint_payload()))

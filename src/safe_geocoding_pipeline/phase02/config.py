from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .constants import AUTHORIZED_SMOKE_FILES

RunScope = Literal["TEST", "SMOKE_TEST", "FULL_CONVERSION"]


@dataclass(frozen=True, slots=True)
class Phase02Config:
    source_root: Path
    phase01_run_dir: Path
    stage00_adoption_record: Path | None = None
    expected_stage00_adoption_sha256: str | None = None
    staging_root: Path = Path("staging/controlled/phase02_v1/runs")
    reports_root: Path = Path("reports/generated/phase02")
    run_scope: RunScope = "TEST"
    include_files: tuple[str, ...] = ()
    source_root_label: str | None = None
    run_id: str | None = None
    resume_run_id: str | None = None
    parser_field_limit_chars: int = 64 * 1024 * 1024
    normal_batch_rows: int = 25_000
    isolation_threshold_bytes: int = 1024 * 1024
    hash_chunk_bytes: int = 1024 * 1024
    compression: str = "zstd"
    compression_level: int = 3
    parquet_version: str = "1.0"
    data_page_version: str = "1.0"
    duckdb_memory_limit: str = "4GB"
    require_free_bytes: int = 20 * 1024 * 1024 * 1024
    authorize_full_conversion: bool = False

    def validate(self) -> None:
        if self.run_id is not None and self.resume_run_id is not None:
            raise ValueError("run_id and resume_run_id are mutually exclusive")
        if self.run_scope not in {"TEST", "SMOKE_TEST", "FULL_CONVERSION"}:
            raise ValueError(f"Unsupported run scope: {self.run_scope}")
        for name, value in (
            ("parser_field_limit_chars", self.parser_field_limit_chars),
            ("normal_batch_rows", self.normal_batch_rows),
            ("isolation_threshold_bytes", self.isolation_threshold_bytes),
            ("hash_chunk_bytes", self.hash_chunk_bytes),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.require_free_bytes < 0:
            raise ValueError("require_free_bytes cannot be negative")
        if self.compression != "zstd":
            raise ValueError("Phase 2 v1 supports only approved zstd compression")
        if self.compression_level != 3:
            raise ValueError("Phase 2 smoke configuration requires ZSTD level 3")
        if self.parquet_version != "1.0" or self.data_page_version != "1.0":
            raise ValueError(
                "Phase 2 v1 requires conservative Parquet/data-page version 1.0"
            )
        if not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", self.duckdb_memory_limit):
            raise ValueError("duckdb_memory_limit must look like 512MB or 4GB")
        for name in self.include_files:
            candidate = Path(name)
            if candidate.name != name or candidate.suffix.lower() != ".csv":
                raise ValueError(f"--include must be a direct CSV filename: {name!r}")
        if self.run_scope == "SMOKE_TEST":
            if tuple(sorted(self.include_files)) != tuple(
                sorted(AUTHORIZED_SMOKE_FILES)
            ):
                raise ValueError(
                    "SMOKE_TEST is restricted to the two explicitly authorized Phase 2 files"
                )
        if self.run_scope == "FULL_CONVERSION":
            if self.include_files:
                raise ValueError("FULL_CONVERSION cannot use --include")
            if not self.authorize_full_conversion:
                raise ValueError(
                    "FULL_CONVERSION requires --authorize-full-conversion; this is an "
                    "operator acknowledgement and not project authorization"
                )
            if self.stage00_adoption_record is None:
                raise ValueError(
                    "FULL_CONVERSION requires an accepted Stage 0 adoption record"
                )
            if self.expected_stage00_adoption_sha256 is None or not re.fullmatch(
                r"[0-9a-f]{64}", self.expected_stage00_adoption_sha256
            ):
                raise ValueError(
                    "FULL_CONVERSION requires the exact lowercase Stage 0 adoption "
                    "record SHA-256"
                )
        elif self.authorize_full_conversion:
            raise ValueError(
                "--authorize-full-conversion is valid only for FULL_CONVERSION"
            )
        elif (
            self.stage00_adoption_record is not None
            or self.expected_stage00_adoption_sha256 is not None
        ):
            raise ValueError(
                "Stage 0 adoption identity is valid only for FULL_CONVERSION"
            )

    @property
    def portable_source_label(self) -> str:
        return self.source_root_label or self.source_root.name

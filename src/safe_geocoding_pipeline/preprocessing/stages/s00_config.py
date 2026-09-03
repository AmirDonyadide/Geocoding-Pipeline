from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .s00_constants import DEFAULT_PLACEHOLDER_CANDIDATES

RunScope = Literal["TEST", "SMOKE_TEST", "FULL_INVENTORY"]
DEFAULT_PARSER_FIELD_LIMIT_CHARS = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class InventoryConfig:
    source_root: Path
    population_scope_file: Path | None = None
    expected_population_scope_sha256: str | None = None
    reports_root: Path = Path("reports/generated/stage00")
    run_scope: RunScope = "TEST"
    include_files: tuple[str, ...] = ()
    source_root_label: str | None = None
    run_id: str | None = None
    resume_run_dir: Path | None = None
    field_warning_chars: int = 1_024
    record_warning_chars: int = 4_096
    parser_field_limit_chars: int = DEFAULT_PARSER_FIELD_LIMIT_CHARS
    insertion_batch_size: int = 1_000
    hash_chunk_bytes: int = 1024 * 1024
    categorical_max_distinct: int = 1_000
    categorical_max_value_chars: int = 256
    placeholder_candidates: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_PLACEHOLDER_CANDIDATES
    )
    require_free_bytes: int = 15 * 1024 * 1024 * 1024
    authorize_full_inventory: bool = False

    def validate(self) -> None:
        if self.run_id is not None and self.resume_run_dir is not None:
            raise ValueError("run_id and resume_run_dir are mutually exclusive")
        if self.run_scope not in {"TEST", "SMOKE_TEST", "FULL_INVENTORY"}:
            raise ValueError(f"Unsupported run scope: {self.run_scope}")
        if self.field_warning_chars < 1:
            raise ValueError("field_warning_chars must be positive")
        if self.record_warning_chars < 1:
            raise ValueError("record_warning_chars must be positive")
        if self.parser_field_limit_chars < 1:
            raise ValueError("parser_field_limit_chars must be positive")
        if self.insertion_batch_size < 1:
            raise ValueError("insertion_batch_size must be positive")
        if self.hash_chunk_bytes < 1:
            raise ValueError("hash_chunk_bytes must be positive")
        if self.categorical_max_distinct < 1:
            raise ValueError("categorical_max_distinct must be positive")
        if self.categorical_max_value_chars < 1:
            raise ValueError("categorical_max_value_chars must be positive")
        if self.require_free_bytes < 0:
            raise ValueError("require_free_bytes cannot be negative")
        if self.run_scope == "FULL_INVENTORY":
            if not self.authorize_full_inventory:
                raise ValueError(
                    "FULL_INVENTORY requires --authorize-full-inventory; this flag is an "
                    "operator safety acknowledgement, not project approval"
                )
            if self.population_scope_file is None:
                raise ValueError(
                    "FULL_INVENTORY requires an authorized population-scope file"
                )
            if self.expected_population_scope_sha256 is None:
                raise ValueError(
                    "FULL_INVENTORY requires the expected population-scope SHA-256"
                )
            if self.include_files:
                raise ValueError("FULL_INVENTORY does not accept --include")
            if self.parser_field_limit_chars != DEFAULT_PARSER_FIELD_LIMIT_CHARS:
                raise ValueError(
                    "FULL_INVENTORY requires the accepted Stage 0 parser ceiling"
                )
        elif (
            self.population_scope_file is not None
            or self.expected_population_scope_sha256 is not None
        ):
            raise ValueError(
                "Population-scope authorization is valid only for FULL_INVENTORY"
            )
        for name in self.include_files:
            candidate = Path(name)
            if candidate.name != name or candidate.suffix.lower() != ".csv":
                raise ValueError(f"--include must be a direct CSV filename: {name!r}")

    @property
    def portable_source_label(self) -> str:
        return self.source_root_label or self.source_root.name

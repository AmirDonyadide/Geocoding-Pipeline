from __future__ import annotations

from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages.s00_config import InventoryConfig
from safe_geocoding_pipeline.preprocessing.stages.s00_discovery import (
    discover_source_files,
)


def test_discovery_is_nonrecursive_sorted_and_does_not_follow_symlinks(
    source_dir: Path,
) -> None:
    (source_dir / "b.csv").write_text("x\n", encoding="utf-8")
    (source_dir / "a.csv").write_text("x\n", encoding="utf-8")
    (source_dir / "not_csv.txt").write_text("x\n", encoding="utf-8")
    nested = source_dir / "nested"
    nested.mkdir()
    (nested / "nested.csv").write_text("x\n", encoding="utf-8")
    (source_dir / "linked.csv").symlink_to(source_dir / "a.csv")

    files = discover_source_files(InventoryConfig(source_root=source_dir))
    assert [item.relative_path for item in files] == ["a.csv", "b.csv"]
    assert [item.file_id for item in files] == [1, 2]


def test_include_rejects_paths_and_missing_files(source_dir: Path) -> None:
    with pytest.raises(ValueError, match="direct CSV filename"):
        InventoryConfig(source_root=source_dir, include_files=("../x.csv",)).validate()
    with pytest.raises(FileNotFoundError, match="not found"):
        discover_source_files(
            InventoryConfig(source_root=source_dir, include_files=("missing.csv",))
        )


def test_full_inventory_requires_explicit_acknowledgement(source_dir: Path) -> None:
    with pytest.raises(ValueError, match="authorize-full-inventory"):
        InventoryConfig(source_root=source_dir, run_scope="FULL_INVENTORY").validate()

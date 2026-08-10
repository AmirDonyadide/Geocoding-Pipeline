from __future__ import annotations

from pathlib import Path

from .config import InventoryConfig
from .models import SourceFile


def discover_source_files(config: InventoryConfig) -> list[SourceFile]:
    root = config.source_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Source root is not a readable directory: {root}")

    include = set(config.include_files)
    discovered: list[Path] = []
    for child in root.iterdir():
        if child.is_symlink() or not child.is_file():
            continue
        if child.suffix.lower() != ".csv":
            continue
        if include and child.name not in include:
            continue
        discovered.append(child)

    if include:
        found = {path.name for path in discovered}
        missing = sorted(include - found)
        if missing:
            raise FileNotFoundError(f"Included CSV files were not found: {missing}")

    discovered.sort(key=lambda path: path.relative_to(root).as_posix())
    return [
        SourceFile(
            file_id=index,
            path=path,
            relative_path=path.relative_to(root).as_posix(),
            file_name=path.name,
        )
        for index, path in enumerate(discovered, start=1)
    ]

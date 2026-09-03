from __future__ import annotations

from pathlib import Path

from .s00_config import InventoryConfig
from .s00_models import SourceFile


def discover_source_files(
    config: InventoryConfig,
    *,
    authorized_relative_paths: tuple[str, ...] | None = None,
) -> list[SourceFile]:
    root = config.source_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Source root is not a readable directory: {root}")

    include = set(config.include_files)
    discovered: list[Path] = []
    for child in root.iterdir():
        if child.suffix.lower() != ".csv":
            continue
        if child.is_symlink() or not child.is_file():
            if authorized_relative_paths is not None:
                raise OSError(
                    "Authorized source population contains an unsafe CSV entry"
                )
            continue
        if include and child.name not in include:
            continue
        discovered.append(child)

    if include:
        found = {path.name for path in discovered}
        missing = sorted(include - found)
        if missing:
            raise FileNotFoundError(f"Included CSV files were not found: {missing}")

    if authorized_relative_paths is not None:
        observed = {path.name for path in discovered}
        if observed != set(authorized_relative_paths):
            raise ValueError(
                "Source directory CSV membership differs from the authorized population"
            )

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

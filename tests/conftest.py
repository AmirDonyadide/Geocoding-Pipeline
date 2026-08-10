from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    path = tmp_path / "source"
    path.mkdir()
    return path


def copy_fixture(fixtures_dir: Path, source_dir: Path, name: str) -> Path:
    destination = source_dir / name
    shutil.copyfile(fixtures_dir / name, destination)
    return destination


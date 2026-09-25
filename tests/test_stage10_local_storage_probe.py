"""Public-only filesystem probe regressions; no scheduler markers or real data."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def probe() -> Any:
    path = (
        Path(__file__).resolve().parents[1] / "scripts/stage10_local_storage_probe.py"
    )
    spec = importlib.util.spec_from_file_location("local_storage_probe", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrong_python_fails_before_io(probe: Any, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="PYTHON_ENVIRONMENT_MISMATCH"):
        probe.runtime_identity(tmp_path / "wrong/bin/python", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_runtime_identity(probe: Any) -> None:
    root = Path(__file__).resolve().parents[1]
    result = probe.runtime_identity(Path(sys.executable), root)
    assert result["duckdb_version"] == "1.5.5"
    assert result["safe_package_version"]
    assert Path(result["safe_package_location"]).is_relative_to(root / "src")


def test_duckdb_transaction_checkpoint_reopen(probe: Any, tmp_path: Path) -> None:
    result = probe.duckdb_probe(tmp_path)
    assert result["rows"] == 2048
    assert result["wal_before_checkpoint_bytes"] > 0
    assert result["wal_after_checkpoint_bytes"] == 0
    assert result["reopen_hash"] == result["expected_hash"]
    assert result["rollback_rows"] == 2048
    assert result["temporary_table_rows"] == 32


def test_copy_hash_and_owned_cleanup(probe: Any, tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    source.write_bytes(b"invented public bytes" * 100)
    result = probe.copy_probe(source, target)
    assert result["sha256_equal"]
    assert result["cleanup"] == "PASS"
    assert result["allocated_bytes_released"] > 0
    assert source.exists() and not target.exists()


def test_cleanup_refuses_other_owner_or_symlink(probe: Any, tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_bytes(b"synthetic")
    before = path.lstat()
    with pytest.raises(RuntimeError, match="OWNERSHIP"):
        probe.remove_owned_file(path, before, expected_uid=os.getuid() + 1)
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(RuntimeError, match="OWNERSHIP"):
        probe.remove_owned_file(link, link.lstat(), expected_uid=os.getuid())
    assert path.exists() and link.is_symlink()


def test_copy_does_not_replace_existing(probe: Any, tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"public")
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        probe.copy_probe(source, target)
    assert target.read_bytes() == b"keep"


def test_complete_local_io_and_cleanup(probe: Any, tmp_path: Path) -> None:
    old = os.umask(0o077)
    try:
        result = probe.local_probe(tmp_path)
        assert result["synthetic_bytes"] == 16 * 1024**2
        assert result["sqlite_rows"] == 1000
        assert result["temporary_file_cleanup"] == "PASS"
        assert result["duckdb"]["rows"] == 2048
        assert result["file_modes"] and set(result["file_modes"].values()) == {"0o600"}
        probe.cleanup_local_files(tmp_path)
        assert not tmp_path.exists()
    finally:
        os.umask(old)

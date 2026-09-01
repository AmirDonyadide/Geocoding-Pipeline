from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s07_second_parser_smoke


def _runtime_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path]:
    bundle = tmp_path / "bundle"
    model_cache = bundle / "cache"
    model_cache.mkdir(parents=True)
    model_cache.chmod(0o555)
    bundle.chmod(0o555)
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("STAGE07_SECOND_PARSER_RUNTIME_ROOT", str(runtime))
    monkeypatch.setenv("STAGE07_SECOND_PARSER_RUNTIME_ROOT", str(runtime))
    for index, name in enumerate(
        s07_second_parser_smoke._EXTERNAL_MUTABLE_DIRECTORY_ENVIRONMENT
    ):
        path = runtime / f"state-{index}"
        path.mkdir(mode=0o700)
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv("STAGE07_SECOND_PARSER_MODEL_CACHE", str(model_cache))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    return bundle, runtime


def test_external_runtime_state_is_owner_only_and_outside_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, _runtime = _runtime_environment(tmp_path, monkeypatch)
    result = s07_second_parser_smoke.validate_external_runtime_state(bundle)
    assert result["external_mutable_runtime_state"] == "PASS"
    assert result["immutable_model_cache"] == "PASS"
    assert result["python_dont_write_bytecode"] == "PASS"


def test_external_runtime_state_rejects_bundle_internal_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle, _runtime = _runtime_environment(tmp_path, monkeypatch)
    monkeypatch.setenv("HF_HOME", str(bundle / "cache"))
    with pytest.raises(RuntimeError, match="MUTABLE_RUNTIME_STATE_INSIDE_BUNDLE"):
        s07_second_parser_smoke.validate_external_runtime_state(bundle)


@pytest.mark.parametrize(
    ("mutation", "error"),
    (
        ("missing", "EXTERNAL_RUNTIME_STATE_ENVIRONMENT_MISSING"),
        ("wrong_mode", "EXTERNAL_RUNTIME_STATE_INVALID"),
        ("symlink", "EXTERNAL_RUNTIME_STATE_INVALID"),
        ("wrong_model_cache", "IMMUTABLE_MODEL_CACHE_IDENTITY_MISMATCH"),
        ("bytecode", "PYTHON_BYTECODE_SUPPRESSION_REQUIRED"),
    ),
)
def test_external_runtime_state_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    error: str,
) -> None:
    bundle, runtime = _runtime_environment(tmp_path, monkeypatch)
    if mutation == "missing":
        monkeypatch.delenv("HF_ASSETS_CACHE")
    elif mutation == "wrong_mode":
        Path(os.environ["HF_ASSETS_CACHE"]).chmod(0o755)
    elif mutation == "symlink":
        target = Path(os.environ["HF_ASSETS_CACHE"])
        replacement = runtime / "symlink-state"
        replacement.symlink_to(target, target_is_directory=True)
        monkeypatch.setenv("HF_ASSETS_CACHE", str(replacement))
    elif mutation == "wrong_model_cache":
        wrong_cache = tmp_path / "wrong-cache"
        wrong_cache.mkdir(mode=0o555)
        monkeypatch.setenv("STAGE07_SECOND_PARSER_MODEL_CACHE", str(wrong_cache))
    else:
        monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "0")
    with pytest.raises(RuntimeError, match=error):
        s07_second_parser_smoke.validate_external_runtime_state(bundle)


def test_smoke_rejects_privileged_execution_before_other_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(RuntimeError, match="ORDINARY_EXECUTION_UID_REQUIRED"):
        s07_second_parser_smoke.run_smoke(
            tmp_path / "absent-bundle",
            "a" * 64,
            "b" * 64,
            tmp_path / "output.json",
        )

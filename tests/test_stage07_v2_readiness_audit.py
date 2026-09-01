from __future__ import annotations

from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stage07_v2_readiness_cli import main
from safe_geocoding_pipeline.preprocessing.stages.s07_v2_readiness_audit import (
    ReadinessAuditConfig,
    Stage07V2ReadinessAuditError,
    _candidate_id_fingerprint,
)


def _config(tmp_path: Path, **changes: object) -> ReadinessAuditConfig:
    values: dict[str, object] = {
        "stage06_fixed500_path": tmp_path / "stage06.parquet",
        "stage07_fixed500_path": tmp_path / "stage07.parquet",
        "qualitative_selection_path": tmp_path / "selection.parquet",
        "classifications_path": tmp_path / "classifications.json",
        "root_cause_path": tmp_path / "root.parquet",
        "eligibility_path": tmp_path / "eligibility.parquet",
        "stage07_registry_paths": (tmp_path / "registry.parquet",),
        "output_directory": tmp_path / "output",
        "execution_git_sha": "1" * 40,
        "authoritative_development": False,
    }
    values.update(changes)
    return ReadinessAuditConfig(**values)  # type: ignore[arg-type]


def test_candidate_set_fingerprint_is_order_invariant_and_domain_bound() -> None:
    first = bytes.fromhex("01" * 32)
    second = bytes.fromhex("02" * 32)
    assert _candidate_id_fingerprint({first, second}) == _candidate_id_fingerprint(
        {second, first}
    )
    assert _candidate_id_fingerprint({first}) != _candidate_id_fingerprint({second})


def test_config_rejects_holdout_and_missing_registry(tmp_path: Path) -> None:
    with pytest.raises(Stage07V2ReadinessAuditError, match="HOLDOUT"):
        _config(tmp_path, output_directory=tmp_path / "HOLDOUT" / "output").validate()
    with pytest.raises(Stage07V2ReadinessAuditError, match="absent"):
        _config(tmp_path, stage07_registry_paths=()).validate()


def test_cli_requires_every_protected_input() -> None:
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2

"""Prospective diagnostic selection only; no service or heavy execution."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "diverse_diagnostic", ROOT / "scripts/stage12_diverse_offline_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def test_whole_selection_and_external_allowance_are_consistent():
    assert diagnostic.MAX_SECONDS == 7200
    assert diagnostic.MAX_BYTES == 256 * 2**20
    assert diagnostic.MAX_FILES == 50000
    assert diagnostic.MAX_RSS == 768 * 2**20
    assert diagnostic.MIN_PERIODIC_PER_PHASE == 200
    assert diagnostic.MIN_PERIODIC_SIZE40 == 900
    launcher = (
        ROOT / "cluster/goethe_nhr/stage12_diverse_offline_diagnostic.sbatch"
    ).read_text()
    assert "7210s" in launcher and "--time=02:10:00" in launcher
    assert '--source-sha "${STAGE12_DIAGNOSTIC_SHA}"' in launcher
    assert 10 * 500 + 180 < diagnostic.MAX_SECONDS


@pytest.mark.parametrize("case", ["old_version", "old_deadline", "source_mismatch"])
def test_old_or_misbound_input_rejected_before_output_or_execution(
    tmp_path, monkeypatch, case
):
    value = {
        "scope": diagnostic.SCOPE,
        "version": "stage12_complete_matrix_synthetic_input_v2",
        "source_sha": "a" * 40,
        "checkpoints": diagnostic.CHECKPOINT_LIMITS,
        "limits": {
            "seconds": 7200,
            "bytes": diagnostic.MAX_BYTES,
            "files": 50000,
            "rss_bytes": diagnostic.MAX_RSS,
            "attempts": 584,
            "synthetic_rate": 20,
            "minimum_periodic_per_phase": 200,
            "minimum_periodic_size40": 900,
        },
    }
    if case == "old_version":
        value["version"] = "stage12_complete_matrix_synthetic_input_v1"
    elif case == "old_deadline":
        value["limits"]["seconds"] = 600
    else:
        value["source_sha"] = "b" * 40
    raw = json.dumps(value).encode()
    source = tmp_path / "input.json"
    source.write_bytes(raw)
    output = tmp_path / "never_created"
    monkeypatch.setattr(diagnostic.signal, "signal", lambda *_: None)
    monkeypatch.setattr(diagnostic.signal, "alarm", lambda *_: None)
    monkeypatch.setattr(diagnostic.os, "umask", lambda *_: None)
    monkeypatch.setattr(
        "sys.argv",
        [
            "diagnostic",
            "--input",
            str(source),
            "--input-sha256",
            hashlib.sha256(raw).hexdigest(),
            "--source",
            str(ROOT),
            "--source-sha",
            "a" * 40,
            "--output",
            str(output),
        ],
    )
    with pytest.raises(AssertionError):
        diagnostic.main()
    assert not output.exists()

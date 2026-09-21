"""Sanitized phase evidence must survive failure and scheduler termination."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops


def test_phase_receipt_is_durable_immutable_snapshot(tmp_path: Path) -> None:
    progress = ops.Progress(tmp_path / "progress")
    progress.counts["contexts_completed"] = 2
    progress.event("generation_start")
    progress.counts["contexts_completed"] = 7
    progress.event("generation_complete")
    receipts = [c.read_json(p) for p in sorted((tmp_path / "progress").glob("*.json"))]
    assert [r["event"] for r in receipts] == ["generation_start", "generation_complete"]
    assert [r["counts"]["contexts_completed"] for r in receipts] == [2, 7]
    assert not list((tmp_path / "progress").glob("*.partial"))


def test_sigterm_durably_records_aggregates(tmp_path: Path) -> None:
    progress = ops.Progress(tmp_path / "progress")
    with pytest.raises(c.Stage10Error, match="TERMINATED"):
        with ops.termination_guard(progress):
            progress.event("generation_start")
            progress.counts["contexts_completed"] = 3
            os.kill(os.getpid(), signal.SIGTERM)
    receipt = c.read_json(tmp_path / "progress/progress-000001.json")
    assert receipt["event"] == "terminal_terminated"
    assert receipt["counts"]["contexts_completed"] == 3
    assert progress.terminated


def test_failed_atomic_publication_preserves_prior_receipt(
    tmp_path: Path, monkeypatch: object
) -> None:
    from typing import Any, cast

    progress = ops.Progress(tmp_path / "progress")
    progress.event("runtime_initialization_complete")
    original = (tmp_path / "progress/progress-000000.json").read_bytes()

    def interrupted(*args: Any) -> None:
        raise OSError("synthetic interruption before atomic rename")

    cast(Any, monkeypatch).setattr(os, "rename", interrupted)
    with pytest.raises(OSError):
        progress.event("generation_start")
    assert (tmp_path / "progress/progress-000000.json").read_bytes() == original
    assert not (tmp_path / "progress/progress-000001.json").exists()
    assert (tmp_path / "progress/progress-000001.json.partial").exists()


def test_production_sigterm_exits_after_receipt_without_unwinding(
    tmp_path: Path,
) -> None:
    import subprocess
    import sys

    script = """
import os, signal, sys
from pathlib import Path
from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops
root = Path(sys.argv[1])
progress = ops.Progress(root / "progress")
with ops.termination_guard(lambda: progress, exit_process=True):
    try:
        progress.event("generation_start")
        progress.counts["contexts_completed"] = 3
        os.kill(os.getpid(), signal.SIGTERM)
    finally:
        (root / "unsafe_cleanup_ran").write_text("synthetic sentinel")
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], capture_output=True
    )
    assert result.returncode == 128 + signal.SIGTERM
    assert result.stdout == result.stderr == b""
    assert not (tmp_path / "unsafe_cleanup_ran").exists()
    receipt = c.read_json(tmp_path / "progress/progress-000001.json")
    assert receipt["event"] == "terminal_terminated"
    assert receipt["counts"]["contexts_completed"] == 3

"""Guard ordering, content-free failures, private topology and concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from stage11_synthetic import fixture
from test_stage11_pipeline import ASSETS, EXE, run
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing import stage11_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_checkpoints as checkpoints,
)
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_input as source
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_io as io
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_pipeline as pipeline,
)
from safe_geocoding_pipeline.preprocessing.stages import (
    s11_semantic_publication as publication,
)
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_trace as trace


def test_guard_precedes_all_protected_access(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("protected path accessed before execution guard")

    monkeypatch.setattr(source.upstream_publication, "validate_terminal", forbidden)
    with pytest.raises(ExecutionPolicyError):
        source.load_accepted(Path("/not-opened"), {})
    with pytest.raises(ExecutionPolicyError):
        cli.execute(EXE, Path("/not-opened"))


def test_cli_portable_failure_is_content_free(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    poison = "PROTECTED_POISON_HYPOTHESIS_SQL_URL"

    def failure(*_: Any) -> Any:
        raise RuntimeError(poison)

    monkeypatch.setattr(cli, "execute", failure)
    assert (
        cli.main(["--execution-git-sha", EXE, "--output-directory", "/invented"]) == 1
    )
    output = capsys.readouterr()
    assert poison not in output.out + output.err
    assert "STAGE11_DEVELOPMENT_FAILED" in output.out


def test_preallocated_durable_failure_preserves_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    artifact = root / "candidate"
    recorder = trace.PublicationTrace(root, artifact, EXE)
    error = c.Stage11Error("S11_ID_COLLISION")
    recorder.failure(error)
    raw = (root / "failure.json").read_bytes()
    record = c.decode_json(raw)
    assert record["operational_code"] == "S11_ID_COLLISION"
    recorder.failure(RuntimeError("POISON_NEWER_ERROR"))
    assert (root / "failure.json").read_bytes() == raw
    assert b"POISON" not in raw


def test_secondary_observer_error_cannot_mask_primary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    observed = []

    def interrupt(phase: str) -> None:
        if phase == "input_unit_complete":
            raise c.Stage11Error("S11_RESOURCE_FAILURE")

    def observer(phase: str, error: BaseException | None) -> None:
        if error:
            observed.append(error)
            raise RuntimeError("POISON_SECONDARY_REPORT_ERROR")

    monkeypatch.setattr(checkpoints, "fault", interrupt)
    with pytest.raises(c.Stage11Error):
        run(root / "run", fixture(root / "input"), observer=observer)
    assert str(observed[0]) == "S11_RESOURCE_FAILURE"
    assert not (root / "run/candidate/_COMMITTED").exists()


def test_failure_receipt_never_includes_poison_exception(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    recorder = trace.PublicationTrace(root, root / "candidate", EXE)
    recorder.failure(ValueError("Invented poison text: SELECT address FROM protected"))
    raw = (root / "failure.json").read_bytes()
    assert b"Invented" not in raw and b"SELECT" not in raw and b"protected" not in raw


def test_concurrent_reservation_has_exactly_one_publisher(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    for i in range(2):
        (root / f"local{i}").mkdir(mode=0o700)
        (root / f"durable{i}").mkdir(mode=0o700)

    def publish(i: int) -> Any:
        try:
            return pipeline.run(
                inputs,
                root / "candidate",
                root / f"local{i}",
                root / f"durable{i}",
                ASSETS,
                EXE,
            )
        except c.Stage11Error:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, range(2)))
    assert sum(r is not None for r in results) == 1
    winner = next(r for r in results if r is not None)
    pipeline.reopen(winner.path, winner.manifest_sha256, True, inputs, ASSETS, EXE)


def test_reopen_failure_does_not_claim_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()

    def reject(phase: str, _: Path) -> None:
        if phase == "reopen":
            raise c.Stage11Error("S11_PUBLICATION_INVALID")

    monkeypatch.setattr(publication, "fault", reject)
    with pytest.raises(c.Stage11Error, match="COMMIT_OUTCOME_REQUIRES_RECONCILIATION"):
        run(root / "run", fixture(root / "input"))
    assert (root / "run/candidate/_COMMITTED").exists()


def test_copy_mismatch_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    src = root / "source"
    io.write_exclusive(src, b"synthetic payload")
    monkeypatch.setattr(c, "sha256_file", lambda _: "0" * 64)
    with pytest.raises(c.Stage11Error, match="S11_CHECKPOINT_INVALID"):
        io.copy_exclusive(src, root / "copy")


def test_byte_heavy_scalar_is_preserved(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    # UTF-8 framing exceeds the writer byte target and exercises one-value memory
    # accounting, while remaining below the local heavy-work threshold.
    text = "Synthetic α𐐀\n" * 350000
    inputs = fixture(root / "input", contexts=4, text=text)
    result = run(root / "run", inputs, unit_rows=2)
    cores = io.parquet_rows(
        [
            result.path / f["relative_path"]
            for f in result.manifest["relations"][0]["files"]
        ]
    )
    assert all((r["core"]["text"] or r["core"]["address"]) == text for r in cores)


def test_local_workspace_unavailable_never_falls_back(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    inputs = fixture(root / "input")
    (root / "durable").mkdir(mode=0o700)
    with pytest.raises(FileNotFoundError):
        pipeline.run(
            inputs,
            root / "candidate",
            root / "missing-local",
            root / "durable",
            ASSETS,
            EXE,
        )
    assert not (root / "candidate").exists()
    assert list((root / "durable").iterdir()) == []


def test_local_stat_failure_does_not_prevent_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path.resolve()
    recorder = trace.PublicationTrace(root, root / "candidate", EXE)
    recorder.local_workspace = root / "local"
    original = Path.is_dir

    def failing(path: Path) -> bool:
        if path == recorder.local_workspace:
            raise OSError("POISON")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", failing)
    recorder.failure(c.Stage11Error("S11_RESOURCE_FAILURE"))
    report = c.decode_json((root / "failure.json").read_bytes())
    assert report["local_workspace_status"] == "UNAVAILABLE"
    assert report["operational_code"] == "S11_RESOURCE_FAILURE"

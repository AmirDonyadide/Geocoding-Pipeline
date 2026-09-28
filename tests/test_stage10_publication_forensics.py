"""Synthetic publication transitions, quota failures and immutable diagnosis."""

from __future__ import annotations

import errno
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_storage as storage
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as ex
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as inputs
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s10_query_receipts as receipts
from safe_geocoding_pipeline.preprocessing.stages import s10_publication_trace as trace
from test_stage10_publication import build, validate
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_query_families import SyntheticTransform


def recorder(tmp_path: Path) -> trace.PublicationTrace:
    root = tmp_path / "attempt"
    root.mkdir(mode=0o700)
    return trace.PublicationTrace(root, tmp_path / "candidate", "a" * 40)


def test_complete_corrected_registration_seal_reopen_with_phase_receipts(
    tmp_path: Path,
) -> None:
    observer = recorder(tmp_path)
    result = pub.publish(observer.artifact, build, validate, observer=observer)
    phases = [
        c.read_json(p)["phase"]
        for p in sorted(observer.root.glob("publication-*.json"))
    ]
    assert phases == [
        "reservation",
        "build",
        "manifest",
        "manifest_fsync",
        "initial_validation",
        "registration_build",
        "registration_write",
        "registration_fsync",
        "prepared_validation",
        "seal_validation",
        "seal_create",
        "reopen",
        "final_check",
    ]
    assert not (observer.root / "failure.json").exists()
    assert (
        observer.root / "failure.json.partial"
    ).stat().st_size == trace.RESERVE_BYTES
    record = c.read_json(result.path / io.SUCCESS_NAME)
    assert record["bindings"]["namespace"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
    assert "stage10_input_binding_sha256" in record["bindings"]
    assert "stage10_input_sha256" not in record["bindings"]
    assert validate(result.path, result.manifest_sha256, True) == result.manifest


@pytest.mark.parametrize(
    "failure",
    ["manifest", "registration_write", "prepared_record", "seal_collision", "reopen"],
)
def test_publication_failures_leave_exact_durable_state(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    observer = recorder(tmp_path)
    original = io.write_exclusive

    def fault(phase: str, root: Path) -> None:
        if phase == failure or (
            failure == "seal_collision" and phase == "before_commit"
        ):
            if failure == "seal_collision":
                original(root / pub.SEAL, b"foreign")
            else:
                raise OSError(errno.EIO, "SYNTHETIC PRIVATE VALUE")

    def write(path: Path, value: bytes) -> None:
        if failure == "registration_write" and path.name == io.SUCCESS_NAME:
            raise OSError(errno.EDQUOT, "SYNTHETIC PRIVATE VALUE")
        original(path, value)

    monkeypatch.setattr(pub, "fault", fault)
    monkeypatch.setattr(io, "write_exclusive", write)
    with pytest.raises(c.Stage10Error):
        pub.publish(observer.artifact, build, validate, observer=observer)
    raw = (observer.root / "failure.json").read_bytes()
    report = c.read_json(observer.root / "failure.json")
    assert b"SYNTHETIC PRIVATE VALUE" not in raw
    assert (
        report["phase"]
        == {
            "manifest": "manifest",
            "registration_write": "registration_write",
            "prepared_record": "registration_write",
            "seal_collision": "seal_validation",
            "reopen": "reopen",
        }[failure]
    )
    assert report["manifest_present"]
    assert report["registration_present"] == (
        failure in ("prepared_record", "seal_collision", "reopen")
    )
    assert report["seal_present"] == (failure in ("seal_collision", "reopen"))
    observer.failure(ValueError("another private error"))
    assert (observer.root / "failure.json").read_bytes() == raw


@pytest.mark.parametrize("number", [errno.EDQUOT, errno.ENOSPC])
def test_preallocated_receipt_survives_new_allocation_failure(
    tmp_path: Path, monkeypatch: Any, number: int
) -> None:
    observer = recorder(tmp_path)

    def no_allocation(*args: Any, **kwargs: Any) -> None:
        raise OSError(number, "SYNTHETIC PRIVATE VALUE")

    monkeypatch.setattr(io, "write_exclusive", no_allocation)
    with pytest.raises(OSError):
        receipts.write(observer.root / "old_failure.json", {"status": "failure"})
    assert not (observer.root / "old_failure.json").exists()
    observer.phase = "initial_validation"
    observer.failure(OSError(number, "SYNTHETIC PRIVATE VALUE"))
    saved = c.read_json(observer.root / "failure.json")
    assert saved["errno"] == number and saved["exception_class"] == "OSError"


def test_failure_receipt_failure_preserves_original_exception(
    tmp_path: Path, monkeypatch: Any
) -> None:
    observer = recorder(tmp_path)

    def fault(phase: str, root: Path) -> None:
        if phase == "manifest":
            raise KeyboardInterrupt()

    monkeypatch.setattr(pub, "fault", fault)
    monkeypatch.setattr(observer, "failure", lambda e: (_ for _ in ()).throw(OSError()))
    with pytest.raises(KeyboardInterrupt):
        pub.publish(observer.artifact, build, validate, observer=observer)
    assert not (observer.artifact / pub.SEAL).exists()


@pytest.mark.parametrize(
    "stdout,code,expected",
    [
        (
            "Filesystem 1K-blocks Used Available Use% Mounted on\npanfs://synthetic\n 122558593750 122556955713 1638037 100% /work/footprint\n",
            0,
            1638037 * 1024,
        ),
        ("panfs://synthetic 1000 600 400 60% /work/footprint\n", 0, 400 * 1024),
        ("unrecognized", 0, None),
        ("", 1, None),
        ("panfs://synthetic 1000 600 400 60% /other\n", 0, None),
    ],
)
def test_quota_parser_fails_closed(
    stdout: str, code: int, expected: int | None, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=code, stdout=stdout),
    )
    if expected is None:
        with pytest.raises(c.Stage10Error, match="QUOTA_UNVERIFIED"):
            ex.project_quota_available()
    else:
        assert ex.project_quota_available() == expected


def test_actual_execution_handler_preserves_publication_failure(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    runtime = SyntheticTransform()
    parent = tmp_path / "development"
    parent.mkdir(mode=0o700)
    config = ex.Stage10Config(tmp_path, parent / "candidate", "a" * 40)
    monkeypatch.setenv("SLURM_JOB_ID", "SYNTHETIC_ONLY")
    monkeypatch.setattr(
        ex.Stage10Config, "preflight", lambda self, **kw: (tmp_path, tmp_path, tmp_path)
    )

    def synthetic_local(*args: Any, **kwargs: Any) -> Path:
        path = tmp_path / "local"
        path.mkdir(mode=0o700)
        return path

    monkeypatch.setattr(storage, "create_transient", synthetic_local)
    monkeypatch.setattr(
        ex,
        "runtime_ready",
        lambda *a: SimpleNamespace(
            asset_binding=runtime.asset_binding,
            lock_sha256="b" * 64,
            semantic_fingerprint="c" * 64,
            transform=runtime.transform,
            close=lambda: None,
        ),
    )
    monkeypatch.setattr(inputs, "consume_inputs", lambda *a: synthetic_inputs)

    def fail(phase: str, root: Path) -> None:
        if phase == "manifest":
            raise OSError(errno.EDQUOT, "SYNTHETIC PRIVATE VALUE")

    monkeypatch.setattr(pub, "fault", fail)
    with pytest.raises(c.Stage10Error, match="UNCOMMITTED"):
        ex.run(config)
    roots = list((parent / "work").iterdir())
    assert len(roots) == 1
    record = c.read_json(roots[0] / "failure.json")
    assert record["phase"] == "manifest" and record["errno"] == errno.EDQUOT
    assert record["counts"]["contexts_completed"] == 4
    events = [
        c.read_json(p)["event"]
        for p in (roots[0] / "workspace/progress").glob("*.json")
    ]
    assert "terminal_failure" in events


def test_read_only_forensic_path_checks_real_synthetic_checkpoints(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    import copy
    from dataclasses import replace
    from safe_geocoding_pipeline.preprocessing import (
        stage10_publication_forensics as forensic,
    )
    from safe_geocoding_pipeline.preprocessing import stage10_remediation_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as base
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_materializer as m
    from safe_geocoding_pipeline.preprocessing.stages import (
        s10_query_families as families,
    )
    from test_stage10_materializer import catalog
    from test_stage10_review_remediation import prior_scientific_projection

    anchor = synthetic_inputs.stage08.root
    records = [
        m.file_record(path, anchor)
        for paths in synthetic_inputs.paths.values()
        for path in paths
    ]
    binding = {
        stage: {"approved_anchor": str(anchor), "files": records}
        for stage in ("stage08", "stage09")
    }
    accepted = replace(synthetic_inputs, binding=binding)
    attempt = tmp_path / "attempt"
    attempt.mkdir(mode=0o700)
    work, artifact = catalog(accepted, attempt / "workspace")
    failed, prior, report = (tmp_path / name for name in ("failed", "prior", "report"))
    for folder in (failed, prior, report):
        folder.mkdir(mode=0o700)
    io.write_exclusive(failed / pub.PROGRESS, b"in_progress\n")
    current = artifact.build(failed)
    io.write_json(failed / io.MANIFEST_NAME, current)
    old = copy.deepcopy(current)
    pair = [
        list(
            base.parquet_rows(
                [failed / f["relative_path"] for f in rel["files"]], batch_rows=1
            )
        )
        for rel in current["relations"]
    ]
    historical = prior_scientific_projection(pair)
    old["relations"] = []
    for name, rows in zip(c.RELATIONS, historical, strict=True):
        writer = io.RelationWriter(prior / name, io.output_schema(name))
        for row in rows:
            writer.append(row)
        writer.close()
        old["relations"].append(m.relation_record(name, writer.paths, prior, len(rows)))
    io.write_json(prior / io.MANIFEST_NAME, old)
    io.write_exclusive(prior / pub.SEAL, b"")
    work.close()
    monkeypatch.setattr(inputs, "PROJECT_ALIAS", tmp_path)
    monkeypatch.setattr(
        forensic, "FAILED_MANIFEST", c.sha256_file(failed / io.MANIFEST_NAME)
    )
    monkeypatch.setattr(forensic, "FAILED_EXECUTABLE", "a" * 40)
    monkeypatch.setattr(
        audit, "PRIOR_MANIFEST", c.sha256_file(prior / io.MANIFEST_NAME)
    )

    def no_science(*args: Any, **kwargs: Any) -> None:
        pytest.fail("forensics generated science")

    monkeypatch.setattr(families, "generate", no_science)
    monkeypatch.setattr(m, "generate_catalog", no_science)
    monkeypatch.setattr(m, "replay", no_science)
    before = {
        str(p): c.sha256_file(p)
        for folder in (failed, prior, attempt)
        for p in folder.rglob("*")
        if p.is_file()
    }
    result = forensic.inspect(report, failed, prior, attempt)
    assert result["contexts_validated"] == 4 and result["checkpoints_validated"] > 0
    assert result["query_hypothesis_logically_equal"] and result["summary_reconciled"]
    assert result["missing_or_incorrect_required_field_decisions"] == 0
    assert (
        result["scientific_contexts_regenerated"]
        == result["certificates_generated"]
        == 0
    )
    assert all(c.sha256_file(Path(p)) == h for p, h in before.items())


def test_trace_rejects_replaced_reserve(tmp_path: Path) -> None:
    observer = recorder(tmp_path)
    original = observer.reserve.with_name("original-reserve")
    observer.reserve.rename(original)
    io.write_exclusive(observer.reserve, b" " * trace.RESERVE_BYTES)
    with pytest.raises(c.Stage10Error, match="RESERVE_INVALID"):
        observer.failure(OSError(errno.ENOSPC, "synthetic"))
    assert original.stat().st_size == trace.RESERVE_BYTES
    assert not (observer.root / "failure.json").exists()


def test_postseal_observability_failure_does_not_demote_commit(tmp_path: Path) -> None:
    observer = recorder(tmp_path)

    def observe(phase: str, error: BaseException | None) -> None:
        if phase in ("reopen", "final_check") and error is None:
            raise OSError(errno.EDQUOT, "synthetic")
        observer(phase, error)

    result = pub.publish(observer.artifact, build, validate, observer=observe)
    assert result.disposition == "PASS"
    assert validate(result.path, result.manifest_sha256, True) == result.manifest


def test_termination_uses_preallocated_failure_receipt(tmp_path: Path) -> None:
    import os
    import signal
    from safe_geocoding_pipeline.preprocessing.stages import s10_query_operations as ops

    observer = recorder(tmp_path)
    observer.phase = "initial_validation"
    with pytest.raises(c.Stage10Error, match="TERMINATED"):
        with ops.termination_guard(
            on_termination=lambda: observer.failure(
                c.Stage10Error("STAGE10_TERMINATED")
            )
        ):
            os.kill(os.getpid(), signal.SIGTERM)
    assert (
        c.read_json(observer.root / "failure.json")["operational_code"]
        == "STAGE10_TERMINATED"
    )

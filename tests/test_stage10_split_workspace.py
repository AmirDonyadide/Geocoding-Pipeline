"""Split storage guards and exact synthetic checkpoint/publication equivalence."""

from __future__ import annotations

import shutil
import os
import pwd
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contexts as cx
from safe_geocoding_pipeline.preprocessing.stages import s10_query_materializer as m
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s10_query_storage as storage
from safe_geocoding_pipeline.preprocessing.stages import s10_query_receipts as receipts
from safe_geocoding_pipeline.preprocessing.stages import (
    s10_query_execution as execution,
)
from safe_geocoding_pipeline.preprocessing.stages import s10_publication_trace as trace
from safe_geocoding_pipeline.preprocessing import stage10_remediation_audit as audit
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage10_query_families import SyntheticTransform


@pytest.fixture
def local_job(tmp_path: Path, monkeypatch: Any) -> Path:
    base = tmp_path / "local"
    base.mkdir()
    job = base / "1234"
    job.mkdir(mode=0o700)
    monkeypatch.setenv("SAFE_EXECUTION_SITE", "goethe-nhr")
    monkeypatch.setenv("SLURM_JOB_ID", "1234")
    monkeypatch.setattr(storage, "LOCAL_BASE", base)
    monkeypatch.setattr(
        pwd, "getpwuid", lambda _: SimpleNamespace(pw_name="donyadidegan")
    )
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=storage.LOCAL_RESERVE),
    )
    return job


def test_local_derivation_and_private_paths(local_job: Path) -> None:
    assert storage.local_root() == local_job
    selected = storage.create_transient("generation")
    assert selected.is_relative_to(local_job / "safe_geocoding_pipeline/stage10")
    assert selected.stat().st_mode & 0o777 == 0o700
    assert selected != storage.create_transient("generation")


@pytest.mark.parametrize(
    "failure",
    ["job", "missing", "capacity", "permissions", "owner", "symlink", "writable"],
)
def test_local_fail_closed(local_job: Path, monkeypatch: Any, failure: str) -> None:
    if failure == "job":
        monkeypatch.delenv("SLURM_JOB_ID")
    elif failure == "missing":
        local_job.rmdir()
    elif failure == "capacity":
        monkeypatch.setattr(
            shutil,
            "disk_usage",
            lambda _: SimpleNamespace(free=storage.LOCAL_RESERVE - 1),
        )
    elif failure == "permissions":
        local_job.chmod(0o755)
    elif failure == "owner":
        monkeypatch.setattr(
            pwd, "getpwuid", lambda _: SimpleNamespace(pw_name="someone_else")
        )
    elif failure == "symlink":
        local_job.rename(local_job.with_name("elsewhere"))
        local_job.symlink_to(local_job.with_name("elsewhere"), target_is_directory=True)
    else:
        monkeypatch.setattr(os, "access", lambda *a: False)
    with pytest.raises(Exception):
        storage.create_transient("generation")
    assert not (local_job / "safe_geocoding_pipeline").exists()


def test_nested_symlink_rejected(local_job: Path, tmp_path: Path) -> None:
    (local_job / "safe_geocoding_pipeline").symlink_to(
        tmp_path, target_is_directory=True
    )
    with pytest.raises(c.Stage10Error):
        storage.create_transient("generation")
    assert not (tmp_path / "stage10").exists()


def make_catalog(
    accepted: Any, transient: Path, durable: Path | None
) -> tuple[Any, Any]:
    runtime = SyntheticTransform()
    work = cx.ContextWorkspace(
        accepted,
        transient,
        c.science_fingerprint(runtime.asset_binding),
        durable_root=durable,
    )
    work.prepare()
    records = m.generate_catalog(work, runtime, "a" * 40)
    artifact = m.CatalogArtifact(
        work,
        runtime,
        records,
        {"execution_git_sha": "a" * 40},
        {"lock_sha256": "b" * 64},
    )
    return work, artifact


@pytest.mark.parametrize("synthetic_inputs", [True], indirect=True)
def test_split_equals_colocated_and_survives_local_loss(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    colocated, before = make_catalog(synthetic_inputs, tmp_path / "before", None)
    local, durable = tmp_path / "local-a", tmp_path / "durable-a"
    work, after = make_catalog(synthetic_inputs, local, durable)
    try:
        assert (local / "context.duckdb").exists()
        assert not (local / "shards").exists()
        assert not (durable / "context.duckdb").exists()
        assert work.progress.root == durable / "progress"
        assert before.records == after.records
        for name in c.RELATIONS:
            query = f"SELECT * FROM {name} ORDER BY " + ",".join(c.ORDER_KEYS[name])
            assert (
                colocated.db.execute(query).fetchall()
                == work.db.execute(query).fetchall()
            )
        assert m.checkpoint_binding(colocated, "a" * 40) == m.checkpoint_binding(
            work, "a" * 40
        )
        result = pub.publish(tmp_path / "candidate", after.build, after.validate)
        assert result.manifest["kind"] == "STAGE10_DEVELOPMENT_QUERY_PLAN"
        assert (
            after.validate(result.path, result.manifest_sha256, True) == result.manifest
        )
        assert (result.path / pub.SEAL).exists()
    finally:
        colocated.close()
        work.close()
    shutil.rmtree(local)  # Invented local loss, never a production cleanup path.
    resumed = cx.ContextWorkspace(
        synthetic_inputs,
        tmp_path / "local-b",
        work.science,
        durable_root=tmp_path / "durable-b",
    )
    resumed.prepare()
    try:

        def forbidden(*a: Any, **kw: Any) -> Any:
            pytest.fail("completed checkpoint regenerated science")

        monkeypatch.setattr(resumed, "contexts", forbidden)
        monkeypatch.setattr(
            cx.ReferenceAccess, "_cached_witness_certificate", forbidden
        )
        records = m.generate_catalog(
            resumed, SyntheticTransform(), "a" * 40, resume=durable / "shards"
        )
        assert records == after.records
        assert resumed.progress.counts["contexts_loaded"] == 0
        assert resumed.progress.counts["checkpoints_reused"] > 0
    finally:
        resumed.close()


def test_failure_receipt_survives_local_loss(tmp_path: Path) -> None:
    durable, local = tmp_path / "durable", tmp_path / "local"
    durable.mkdir(mode=0o700)
    local.mkdir(mode=0o700)
    observer = trace.PublicationTrace(durable, tmp_path / "candidate", "a" * 40)
    observer.local_workspace = local
    observer.counts["checkpoints_completed"] = 3
    local.rmdir()
    observer.failure(OSError("invented sensitive sentinel"))
    record = c.read_json(durable / "failure.json")
    assert record["local_workspace_present"] is False
    assert record["counts"]["checkpoints_completed"] == 3
    assert "sentinel" not in (durable / "failure.json").read_text()


@pytest.mark.parametrize("number", [5, 13, 70])
def test_failure_receipt_survives_unavailable_local_stat(
    tmp_path: Path, monkeypatch: Any, number: int
) -> None:
    durable, local = tmp_path / "durable", tmp_path / "local"
    durable.mkdir(mode=0o700)
    local.mkdir(mode=0o700)
    observer = trace.PublicationTrace(durable, tmp_path / "candidate", "a" * 40)
    observer.local_workspace = local
    original = Path.is_dir

    def unavailable(path: Path) -> bool:
        if path == local:
            raise OSError(number, "invented private filesystem diagnostic")
        return original(path)

    monkeypatch.setattr(Path, "is_dir", unavailable)
    observer.failure(ValueError("invented primary private value"))
    record = c.read_json(durable / "failure.json")
    assert record["local_workspace_present"] is None
    assert record["local_workspace_status"] == "UNAVAILABLE"
    assert record["exception_class"] == "ValueError"
    assert "invented" not in (durable / "failure.json").read_text()


def test_audit_uses_local_database_and_durable_result(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from test_stage10_remediation_audit import artifact_fixture

    config = artifact_fixture(tmp_path, monkeypatch)
    transient = tmp_path / "local-audit"
    transient.mkdir(mode=0o700)
    monkeypatch.setattr(type(config), "preflight", lambda self, **kw: None)
    monkeypatch.setattr(storage, "create_transient", lambda *a, **kw: transient)
    report = audit.audit(config)
    assert report["status"] == "REMEDIATION_AUDIT_PASS"
    assert (transient / "audit.duckdb").exists()
    root = (
        config.output_directory.parent
        / "work"
        / (config.output_directory.name + "_remediation_audit")
    )
    assert not (root / "audit.duckdb").exists()
    assert (root / "completed.json").exists()
    shutil.rmtree(transient)
    assert c.read_json(root / "completed.json")["status"] == "REMEDIATION_AUDIT_PASS"


def test_audit_failure_is_durable_after_local_loss(
    tmp_path: Path, monkeypatch: Any
) -> None:
    from test_stage10_remediation_audit import artifact_fixture

    config = artifact_fixture(tmp_path, monkeypatch)
    transient = tmp_path / "local-audit"
    transient.mkdir(mode=0o700)
    monkeypatch.setattr(type(config), "preflight", lambda self, **kw: None)
    monkeypatch.setattr(storage, "create_transient", lambda *a, **kw: transient)

    def fail(*a: Any) -> Any:
        shutil.rmtree(transient)
        raise OSError("invented protected value")

    monkeypatch.setattr(audit, "reconcile", fail)
    with pytest.raises(OSError):
        audit.audit(config)
    root = (
        config.output_directory.parent
        / "work"
        / (config.output_directory.name + "_remediation_audit")
    )
    record = c.read_json(root / "failure.json")
    assert record["local_workspace_present"] is False
    assert record["phase"] == "remediation_audit"
    assert "invented protected value" not in (root / "failure.json").read_text()


def test_audit_portable_report_failure_has_durable_primary_receipt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import sys
    from test_stage10_remediation_audit import artifact_fixture

    config = artifact_fixture(tmp_path, monkeypatch)
    real_write = receipts.write

    def fail_report(path: Path, value: Any) -> None:
        if path.name.endswith("_remediation_audit.json"):
            raise OSError(28, "invented private diagnostic")
        real_write(path, value)

    monkeypatch.setattr(receipts, "write", fail_report)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "audit",
            "--stage06-root",
            str(config.stage06_root),
            "--output-directory",
            str(config.output_directory),
            "--execution-git-sha",
            config.execution_git_sha,
        ],
    )
    assert audit.main() == 1
    root = (
        config.output_directory.parent
        / "work"
        / (config.output_directory.name + "_remediation_audit")
    )
    report = c.read_json(root / "failure.json")
    assert report["operational_code"] == "STAGE10_STORAGE_SPACE_EXHAUSTED"
    assert not (root / "completed.json").exists()


@pytest.mark.parametrize("fault", ["interrupt", "corrupt"])
def test_copy_fault_cannot_commit_split_artifact(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any, fault: str
) -> None:
    work, artifact = make_catalog(
        synthetic_inputs, tmp_path / "local", tmp_path / "panfs-checkpoints"
    )
    target = tmp_path / "candidate"
    real_copy = shutil.copyfileobj

    def broken(src: Any, dst: Any, *a: Any) -> None:
        if fault == "interrupt":
            dst.write(b"invented partial copy")
            raise OSError("synthetic interrupted copy")
        real_copy(src, dst, *a)
        dst.write(b"invented corrupt bytes")

    monkeypatch.setattr(shutil, "copyfileobj", broken)
    try:
        with pytest.raises(c.Stage10Error):
            pub.publish(target, artifact.build, artifact.validate)
        assert not (target / pub.SEAL).exists()
        assert not (target / "registration.json").exists()
    finally:
        work.close()


@pytest.mark.parametrize(
    "free,expected", [(storage.PANFS_RESERVE - 1, False), (storage.PANFS_RESERVE, True)]
)
def test_two_gib_gate_and_postpublication_validation(
    free: int, expected: bool, monkeypatch: Any
) -> None:
    local = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
    durable: Any = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=2))
    monkeypatch.setattr(storage, "local_root", lambda **kw: local)
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=storage.PANFS_RESERVE),
    )
    monkeypatch.setattr(execution, "project_quota_available", lambda: free)
    if expected:
        execution.storage_preflight(durable, new_generation=True)
    else:
        with pytest.raises(c.Stage10Error, match="QUOTA_RESERVE_INSUFFICIENT"):
            execution.storage_preflight(durable, new_generation=True)
    monkeypatch.setattr(
        execution,
        "project_quota_available",
        lambda: pytest.fail("fresh-run reserve reapplied after publication"),
    )
    execution.storage_preflight(durable, new_generation=False)


def test_same_filesystem_cannot_be_local_fallback(monkeypatch: Any) -> None:
    path: Any = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
    monkeypatch.setattr(storage, "local_root", lambda **kw: path)
    with pytest.raises(c.Stage10Error, match="FILESYSTEM_NOT_DISTINCT"):
        execution.storage_preflight(path, new_generation=True)


@pytest.mark.parametrize(
    "synthetic_inputs",
    [
        {
            "same_country": bool(i % 2),
            "source_ids": [bytes([i * 3 + j + 1]) * 32 for j in range(3)],
        }
        for i in range(4)
    ],
    indirect=True,
)
def test_exact_presplit_executable_equivalence(
    synthetic_inputs: Any, tmp_path: Path, monkeypatch: Any
) -> None:
    # Load immutable code from the approved Git object, checking its recorded
    # implementation hashes. Four public fixture populations total 16 contexts.
    import test_stage10_performance_repair as legacy

    monkeypatch.setattr(legacy, "ORIGINAL", "7353e3197adcb1b38cc821f48ee3d7da6d1f529c")
    old_cx = legacy.original_module("s10_query_contexts", tmp_path)
    old_m = legacy.original_module("s10_query_materializer", tmp_path)
    old_units = legacy.original_module("s10_query_checkpoints", tmp_path)
    old_families = legacy.original_module("s10_query_families", tmp_path)
    old_m.units = old_units
    old_units.families = old_families
    runtime = SyntheticTransform()
    old = old_cx.ContextWorkspace(
        synthetic_inputs,
        tmp_path / "old-panfs",
        c.science_fingerprint(runtime.asset_binding),
    )
    current = cx.ContextWorkspace(
        synthetic_inputs,
        tmp_path / "new-local",
        old.science,
        durable_root=tmp_path / "new-panfs",
    )
    try:
        old.prepare()
        current.prepare()
        before = old_m.generate_catalog(old, runtime, "a" * 40)
        after = m.generate_catalog(current, runtime, "a" * 40)
        assert before == after
        assert (
            old.progress.counts["contexts_completed"]
            == current.progress.counts["contexts_completed"]
            == 4
        )
        assert (
            old.progress.counts["family_decisions_written"]
            == current.progress.counts["family_decisions_written"]
            == 24
        )
        for name in c.RELATIONS:
            query = f"SELECT * FROM {name} ORDER BY " + ",".join(c.ORDER_KEYS[name])
            assert (
                old.db.execute(query).fetchall() == current.db.execute(query).fetchall()
            )
    finally:
        old.close()
        current.close()

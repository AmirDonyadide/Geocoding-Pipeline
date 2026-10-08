"""Guard challenges use path strings only; no protected path is opened."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import review


def test_execution_guard_precedes_protected_io(monkeypatch):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError

    with pytest.raises(ExecutionPolicyError):
        review.main()


def test_audit_path_scope_and_immutability(monkeypatch):
    monkeypatch.setenv(
        "STAGE11_REVIEW_OUTPUT",
        str(review.PROJECT / "derived/controlled/stage11/independent_review/invented"),
    )
    for path in (
        "/local/1788751/anything",
        str(review.PROJECT / "derived/controlled/stage10/holdout/anything"),
        str(review.PROJECT / "derived/controlled/stage11/production/anything"),
    ):
        with pytest.raises(PermissionError):
            review.audit("open", (path, "r", os.O_RDONLY))
    for root in (review.ARTIFACT, review.ATTEMPT, review.UPSTREAM):
        path = str(root / "invented")
        review.audit("open", (path, "r", os.O_RDONLY))
        for mode, flags in (("w", os.O_WRONLY), (None, os.O_RDWR), ("r+", os.O_RDWR)):
            with pytest.raises(PermissionError):
                review.audit("open", (path, mode, flags))
        for event in ("os.remove", "os.chmod", "os.rename", "os.mkdir"):
            with pytest.raises(PermissionError):
                review.audit(event, (path, path))
    monkeypatch.setattr(review, "DENY_ALL_LOCAL", True)
    with pytest.raises(PermissionError):
        review.audit("open", ("/local/invented/anything", "r", os.O_RDONLY))
    with pytest.raises(PermissionError):
        review.audit("socket.connect", (None, ("invented", 80)))


def test_real_audit_hook_blocks_before_open(tmp_path):
    # A child is required because Python audit hooks cannot be removed.
    script = """
import sys
import review
sys.addaudithook(review.audit)
try:
    open('/local/1788751/never-opened', 'rb')
except PermissionError:
    print('AUDIT_BLOCKED')
else:
    raise SystemExit(1)
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = (
        str(Path(review.__file__).parent) + os.pathsep + env.get("PYTHONPATH", "")
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, env=env, check=True
    )
    assert result.stdout == b"AUDIT_BLOCKED\n" and not result.stderr


def test_failure_reporting_has_no_message():
    try:
        raise ValueError("SYNTHETIC_SECRET_POISON")
    except ValueError as error:
        result = review.portable_failure(error, "synthetic")
    assert "POISON" not in str(result)
    assert result["locations"]
    assert result["exception_kind"] == "ValueError"
    assert result["errno"] is None


def test_os_failure_reporting_retains_only_safe_class_and_errno():
    result = review.portable_failure(
        OSError(28, "SYNTHETIC_SECRET_POISON"), "synthetic"
    )
    assert result["exception_kind"] == "OSError" and result["errno"] == 28
    assert "POISON" not in str(result)


def test_review_connection_requires_no_scratch_directory(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("review connection attempted scratch directory creation")

    monkeypatch.setattr(Path, "mkdir", forbidden)
    with review.review_connection() as db:
        assert db.execute(
            "SELECT current_setting('temp_directory'), current_setting('threads')"
        ).fetchone() == ("", 2)
        assert db.execute(
            "SELECT name,value FROM duckdb_settings() WHERE name IN ('autoinstall_known_extensions','autoload_known_extensions') ORDER BY name"
        ).fetchall() == [
            ("autoinstall_known_extensions", "false"),
            ("autoload_known_extensions", "false"),
        ]
        assert db.execute(
            "SELECT path FROM duckdb_databases() WHERE database_name='memory'"
        ).fetchone() == (None,)
        db.execute("CREATE TEMP TABLE test AS SELECT range AS key FROM range(128)")
        assert db.execute("SELECT count(*),sum(key) FROM test").fetchone() == (
            128,
            8128,
        )

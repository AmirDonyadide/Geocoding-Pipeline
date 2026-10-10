from __future__ import annotations

import os

import pytest

from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as t


@pytest.fixture
def key_file(tmp_path):
    tmp_path.chmod(0o700)
    path = tmp_path / "runtime_key"
    path.write_bytes(b"invented-file-secret")
    path.chmod(0o600)
    return path


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_private_file_memory_only_no_hash_or_environment_export(
    key_file, monkeypatch, ending
):
    key_file.write_bytes(b"invented-file-secret" + ending)
    monkeypatch.setattr(c, "sha", lambda _: pytest.fail("secret must not be hashed"))
    monkeypatch.delenv("SAFE_PELIAS_API_KEY", raising=False)
    before = set(os.environ)
    secret = t.Secret.private_file(str(key_file))
    assert secret.value == b"invented-file-secret"
    assert "invented-file-secret" not in repr(secret)
    assert set(os.environ) == before


@pytest.mark.parametrize("mode", [0o644, 0o640, 0o660, 0o604, 0o606, 0o602, 0o700])
def test_unsafe_permissions_rejected_before_read(key_file, monkeypatch, mode):
    key_file.chmod(mode)
    monkeypatch.setattr(t.os, "read", lambda *_: pytest.fail("unsafe file read"))
    with pytest.raises(c.Stage12Error, match="ENVIRONMENT_AUTH_FILE_INVALID"):
        t.Secret.private_file(str(key_file))


@pytest.mark.parametrize(
    "payload", [b"", b"\n", b"two\nlines", b"spaces here", b"k" * 8195, b"\xff"]
)
def test_invalid_content_static_exception(key_file, payload):
    key_file.write_bytes(payload)
    with pytest.raises(c.Stage12Error) as error:
        t.Secret.private_file(str(key_file))
    assert str(error.value) in (
        "ENVIRONMENT_AUTH_INVALID",
        "ENVIRONMENT_AUTH_FILE_INVALID",
    )
    assert "invented-file-secret" not in str(error.value)


def test_symlink_and_hardlink_rejected(key_file):
    link = key_file.parent / "link"
    link.symlink_to(key_file)
    with pytest.raises(c.Stage12Error):
        t.Secret.private_file(str(link))
    link.unlink()
    os.link(key_file, link)
    with pytest.raises(c.Stage12Error):
        t.Secret.private_file(str(key_file))


def test_nonregular_fifo_rejected_without_blocking(tmp_path):
    path = tmp_path / "fifo"
    os.mkfifo(path, 0o600)
    with pytest.raises(c.Stage12Error):
        t.Secret.private_file(str(path))


def test_wrong_owner_rejected_before_read(key_file, monkeypatch):
    monkeypatch.setattr(t.os, "geteuid", lambda: key_file.stat().st_uid + 1)
    monkeypatch.setattr(t.os, "read", lambda *_: pytest.fail("wrong-owner read"))
    with pytest.raises(c.Stage12Error):
        t.Secret.private_file(str(key_file))


def test_file_change_during_read_fails(key_file, monkeypatch):
    read = t.os.read

    def changing(fd, size):
        value = read(fd, size)
        key_file.write_bytes(b"changed-invented-secret")
        return value

    monkeypatch.setattr(t.os, "read", changing)
    with pytest.raises(c.Stage12Error, match="ENVIRONMENT_AUTH_FILE_CHANGED"):
        t.Secret.private_file(str(key_file))


def test_runtime_guard_precedes_file_access(key_file, monkeypatch):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setenv("SAFE_PELIAS_API_KEY_FILE", str(key_file))
    monkeypatch.setattr(t.Secret, "private_file", lambda _: pytest.fail("guard bypass"))
    with pytest.raises(ExecutionPolicyError):
        t.Secret.runtime()


def test_explicit_file_provider_no_fallback_or_ambiguity(key_file, monkeypatch):
    monkeypatch.setattr(t, "require_goethe_nhr_slurm", lambda _: None)
    monkeypatch.delenv("SAFE_PELIAS_API_KEY", raising=False)
    monkeypatch.setenv("SAFE_PELIAS_API_KEY_FILE", str(key_file))
    assert t.Secret.runtime().value == b"invented-file-secret"
    monkeypatch.setenv("SAFE_PELIAS_API_KEY", "other-invented-key")
    with pytest.raises(c.Stage12Error, match="AMBIGUOUS"):
        t.Secret.runtime()
    monkeypatch.delenv("SAFE_PELIAS_API_KEY")
    key_file.unlink()
    with pytest.raises(c.Stage12Error, match="FILE_INVALID"):
        t.Secret.runtime()

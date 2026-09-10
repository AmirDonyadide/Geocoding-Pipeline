from __future__ import annotations

import ctypes
import errno
import os
import subprocess
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage09_filesystem_diagnostic as d


def test_real_local_synthetic_probe_preserves_collision_sentinels(tmp_path):
    root = tmp_path / "new"
    report = d.collect_synthetic(root, "f" * 40, "SYNTHETIC")
    assert report["all_observed_effects_consistent"]
    assert len(report["cases"]) == 6
    assert report["scope"] == "SYNTHETIC_FILESYSTEM_ONLY"
    assert report["protected_payloads_opened"] == 0
    assert report["reference_payloads_opened"] == 0
    assert not report["materializer_invoked"]
    assert not report["publication_fallback_enabled"]
    assert not (root / "_SUCCESS.json").exists()
    for record in report["cases"][1:4]:
        assert record["return_code"] != 0
        assert record["source_retained_intact"]
        assert record["original_target_unchanged"]
    before = (root / d.REPORT_NAME).read_bytes()
    with pytest.raises(d.c.Stage09Error, match="TARGET_EXISTS"):
        d.collect_synthetic(root, "f" * 40, "SYNTHETIC")
    assert (root / d.REPORT_NAME).read_bytes() == before


@pytest.mark.parametrize(
    "number", [errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP, errno.EACCES]
)
def test_unavailable_operation_is_recorded_not_hidden_by_successful_baseline(
    tmp_path, monkeypatch, number
):
    original = d.native_call

    def call(source, target, operation):
        if operation == "NOREPLACE":
            return {
                "api": "SYNTHETIC_RENAMEAT2",
                "flags": 1,
                "return_code": -1,
                "errno": number,
                "errno_symbol": errno.errorcode[number],
            }
        return original(source, target, operation)

    monkeypatch.setattr(d, "native_call", call)
    report = d.collect_synthetic(tmp_path / "new", "f" * 40, "SYNTHETIC")
    assert not report["noreplace_supported_in_this_probe"]
    assert report["all_observed_effects_consistent"]
    assert all(r["errno"] == number for r in report["cases"][:4])
    assert report["cases"][-1]["return_code"] == 0


@pytest.mark.parametrize(
    "platform,name,operation,flags",
    [
        ("linux", "renameat2", "NOREPLACE", 1),
        ("linux", "renameat2", "ZERO_FLAGS", 0),
        ("darwin", "renamex_np", "NOREPLACE", 4),
        ("linux", "rename", "POSIX_BASELINE", None),
    ],
)
def test_exact_native_signature_and_immediate_errno(
    monkeypatch, tmp_path, platform, name, operation, flags
):
    from types import SimpleNamespace

    class Function:
        argtypes = None
        restype = None

        def __call__(self, *args):
            if flags is not None:
                assert args[-1] == flags
            if name == "renameat2":
                assert args[0] == -100 and args[2] == -100
            ctypes.set_errno(errno.EOPNOTSUPP)
            return -1

    function = Function()
    monkeypatch.setattr(d.sys, "platform", platform)
    monkeypatch.setattr(
        d.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace(**{name: function})
    )
    outcome = d.native_call(tmp_path / "source", tmp_path / "target", operation)
    assert outcome["errno"] == errno.EOPNOTSUPP
    assert outcome["flags"] == flags
    assert outcome["return_code"] == -1
    assert function.restype == ctypes.c_int


def test_guard_fails_before_any_directory_is_opened(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(d, "collect_synthetic", lambda *_: pytest.fail("guard bypass"))
    assert (
        d.main(
            [
                "--output-directory",
                str(tmp_path / "sensitive-canary"),
                "--execution-git-sha",
                "f" * 40,
            ]
        )
        == 1
    )
    assert "sensitive-canary" not in capsys.readouterr().err


def test_fsync_error_keeps_exact_errno_without_exception_payload(tmp_path, monkeypatch):
    def failure(_):
        raise OSError(errno.EIO, "sensitive sentinel")

    monkeypatch.setattr(d.io, "fsync_directory", failure)
    assert d._fsync_probe(tmp_path) == {
        "ok": False,
        "errno": errno.EIO,
        "errno_symbol": "EIO",
    }


def test_baseline_is_never_run_against_an_existing_target(tmp_path):
    with pytest.raises(d.c.Stage09Error, match="BASELINE_COLLISION_PROHIBITED"):
        d.probe_case(tmp_path, "case", "POSIX_BASELINE", "EMPTY_DIRECTORY")
    assert not (tmp_path / "case").exists()


def test_cli_path_allowlist_precedes_git_check(monkeypatch, tmp_path):
    monkeypatch.setattr(d, "require_goethe_nhr_slurm", lambda *_: None)
    monkeypatch.setattr(
        d.subprocess,
        "check_output",
        lambda *_args, **_kwargs: pytest.fail("outside scope"),
    )
    with pytest.raises(d.c.Stage09Error, match="SCOPE_PATH_REQUIRED"):
        d.validate_cli_target(tmp_path / "other", "f" * 40)


def test_synthetic_scopes_reject_links_and_existing_directories(tmp_path):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    root = tmp_path / "linked"
    root.symlink_to(parent)
    with pytest.raises(d.c.Stage09Error, match="TARGET_EXISTS"):
        d.collect_synthetic(root, "f" * 40, "SYNTHETIC")
    assert root.is_symlink()


def test_launcher_is_synthetic_only_no_requeue_and_syntax_valid():
    path = (
        Path(__file__).resolve().parents[1]
        / "cluster/goethe_nhr/stage09_filesystem_diagnostic.sbatch"
    )
    subprocess.run(["bash", "-n", str(path)], check=True)
    body = path.read_text()
    assert "#SBATCH --no-requeue" in body
    assert "#SBATCH --time=00:05:00" in body
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in body
    for excluded in (
        "stage09_cli",
        "--stage08-root",
        "--reference-raw-root",
        "git pull",
        "sbatch ",
        "/scratch",
    ):
        assert excluded not in body


def test_errno_success_is_not_stale(monkeypatch, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    ctypes.set_errno(errno.EACCES)
    result = d.native_call(source, tmp_path / "target", "POSIX_BASELINE")
    assert result["return_code"] == 0 and result["errno"] == 0
    assert not os.path.lexists(source)


def test_claimed_success_without_rename_does_not_validate_capability(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        d,
        "native_call",
        lambda *_: {
            "api": "SYNTHETIC",
            "flags": 1,
            "return_code": 0,
            "errno": 0,
            "errno_symbol": "NONE",
        },
    )
    report = d.collect_synthetic(tmp_path / "new", "f" * 40, "SYNTHETIC")
    assert not report["noreplace_supported_in_this_probe"]
    assert not report["all_observed_effects_consistent"]
    assert len(report["cases"]) == 6


def test_missing_native_symbol_is_reported_without_arbitrary_exception(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(d.ctypes, "CDLL", lambda *_args, **_kwargs: object())
    result = d.native_call(tmp_path / "source", tmp_path / "target", "NOREPLACE")
    assert result["return_code"] is None and result["errno"] is None
    assert result["errno_symbol"] == "SYMBOL_UNAVAILABLE"

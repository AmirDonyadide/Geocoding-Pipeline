from __future__ import annotations

import ctypes
import errno
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing import (
    stage09_exclusive_create_diagnostic as d,
)


def test_full_local_probe_all_required_cases_and_process_barriers(tmp_path):
    root = tmp_path / "new"
    report = d.collect_synthetic(root, "f" * 40, "SYNTHETIC")
    assert report["required_semantics_passed"]
    assert len(report["cases"]) == 10
    assert all(r["passed"] for r in report["cases"])
    for row in report["cases"][3:6]:
        assert (row["attempts"], row["winners"], row["losers"]) == (4, 1, 3)
        assert row["distinct_processes"] == 4
        assert row["barrier_all_ready_before_release"]
        assert row["all_workers_exit_zero"]
        assert row["reopen"]["reopens"] == 3
    assert (
        report["protected_payloads_opened"] == report["reference_payloads_opened"] == 0
    )
    assert not report["publication_protocol_integrated"]
    assert not (root / "_SUCCESS.json").exists()
    assert not (root / "_COMMITTED").exists()
    before = (root / d.REPORT).read_bytes()
    with pytest.raises(d.c.Stage09Error, match="TARGET_EXISTS"):
        d.collect_synthetic(root, "f" * 40, "SYNTHETIC")
    assert (root / d.REPORT).read_bytes() == before


@pytest.mark.parametrize("operation", ["OPEN", "MKDIR"])
def test_native_signature_flags_modes_and_immediate_errno(
    monkeypatch, tmp_path, operation
):
    class Function:
        argtypes = None
        restype = None

        def __call__(self, *args):
            assert args[0] == os.fsencode(tmp_path / "target")
            assert (args[-1].value if operation == "OPEN" else args[-1]) == (
                0o600 if operation == "OPEN" else 0o700
            )
            if operation == "OPEN":
                assert args[1] == os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                assert not args[1] & os.O_TRUNC
            ctypes.set_errno(errno.EINVAL)
            return -1

    function = Function()
    monkeypatch.setattr(
        d.ctypes,
        "CDLL",
        lambda *a, **k: SimpleNamespace(**{operation.lower(): function}),
    )
    result = d.native_create(tmp_path / "target", operation)
    assert result["return_code"] == -1
    assert result["errno"] == errno.EINVAL
    assert result["errno_symbol"] == "EINVAL"
    assert function.restype == ctypes.c_int
    assert function.argtypes == (
        [ctypes.c_char_p, ctypes.c_int]
        if operation == "OPEN"
        else [ctypes.c_char_p, ctypes.c_uint]
    )


def test_errno_success_resets_stale_error(tmp_path):
    ctypes.set_errno(errno.EACCES)
    result = d.attempt(tmp_path / "record", "OPEN", d.SENTINEL)
    assert result["won"] and result["errno"] == 0
    assert d.verify_file(tmp_path / "record", d.SENTINEL)["ok"]


@pytest.mark.parametrize("number", [errno.EINVAL, errno.EOPNOTSUPP, errno.EACCES])
def test_failed_primitive_cannot_confirm_sequential_capability(
    tmp_path, monkeypatch, number
):
    monkeypatch.setattr(
        d,
        "native_create",
        lambda *a: {
            "return_code": -1,
            "errno": number,
            "errno_symbol": errno.errorcode[number],
        },
    )
    result = d.sequential(tmp_path, "case", "OPEN")
    assert not result["passed"]
    assert result["fresh"]["errno"] == number


def test_unexpected_collision_success_never_writes_sequential_sentinel(
    tmp_path, monkeypatch
):
    path = tmp_path / "record"
    d.io.write_exclusive(path, d.SENTINEL)
    fd = os.open(path, os.O_WRONLY)
    monkeypatch.setattr(d, "native_create", lambda *a: {"return_code": fd, "errno": 0})
    result = d.attempt(path, "OPEN", None)
    assert result["won"]
    assert path.read_bytes() == d.SENTINEL


@pytest.mark.parametrize("operation", ["OPEN", "MKDIR"])
@pytest.mark.parametrize("dangling", [False, True])
def test_symlink_rejected_and_referent_unchanged(tmp_path, operation, dangling):
    row = d.symlink_case(tmp_path, operation, dangling)
    assert row["passed"]
    assert row["operation"]["errno"] == errno.EEXIST


def test_fsync_error_record_has_errno_without_exception_text(tmp_path, monkeypatch):
    monkeypatch.setattr(
        d.io,
        "fsync_directory",
        lambda p: (_ for _ in ()).throw(OSError(errno.EIO, "invented private detail")),
    )
    row = d.directory_sync(tmp_path)
    assert row == {"ok": False, "errno": errno.EIO, "errno_symbol": "EIO"}


def test_guard_precedes_any_creation_or_logging_values(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(d, "collect_synthetic", lambda *a: pytest.fail("guard bypass"))
    assert (
        d.main(
            [
                "--output-directory",
                str(tmp_path / "private-canary"),
                "--execution-git-sha",
                "f" * 40,
            ]
        )
        == 1
    )
    assert "private-canary" not in capsys.readouterr().err


def test_missing_symbol_records_unavailability(tmp_path, monkeypatch):
    monkeypatch.setattr(d.ctypes, "CDLL", lambda *a, **k: object())
    result = d.native_create(tmp_path / "target", "OPEN")
    assert result["return_code"] is None and result["errno"] is None
    assert result["errno_symbol"] == "SYMBOL_UNAVAILABLE"


def test_nonregular_or_wrong_mode_is_never_valid_reopen(tmp_path):
    path = tmp_path / "target"
    path.mkdir()
    assert not d.verify_file(path, b"")["ok"]
    file = tmp_path / "file"
    file.write_bytes(d.SENTINEL)
    file.chmod(0o644)
    assert not d.verify_file(file, d.SENTINEL)["ok"]


def test_only_exact_synthetic_links_permitted(tmp_path):
    root = tmp_path / "new"
    root.mkdir(mode=0o700)
    (root / "unplanned").symlink_to("missing")
    with pytest.raises(d.c.Stage09Error, match="UNEXPECTED_SYMLINK"):
        d.private_topology(root)


def test_launcher_is_bounded_and_synthetic_only():
    path = (
        Path(__file__).resolve().parents[1]
        / "cluster/goethe_nhr/stage09_exclusive_create_diagnostic.sbatch"
    )
    subprocess.run(["bash", "-n", str(path)], check=True)
    body = path.read_text()
    for expected in (
        "--nodes=1",
        "--cpus-per-task=1",
        "--mem=2G",
        "--time=00:05:00",
        "--no-requeue",
        "SAFE_EXECUTION_SITE=goethe-nhr",
    ):
        assert expected in body
    for forbidden in (
        "--stage08-root",
        "--reference-raw-root",
        "stage09_cli",
        "git pull",
        "sbatch ",
        "/scratch",
    ):
        assert forbidden not in body

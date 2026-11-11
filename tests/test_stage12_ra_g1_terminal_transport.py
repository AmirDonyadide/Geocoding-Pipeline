# ruff: noqa: E402
"""Small invented stream checks; no SSH or native allowance is used."""

import hashlib
from pathlib import Path
import sys
import time
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_collect as tc


def test_actual_small_stream_child_complete_identity_and_eof(tmp_path):
    source = tmp_path / "invented"
    source.write_bytes(b"invented\0payload")
    out = tmp_path / "retained"
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**10, 10)
    expected = dict(
        bytes=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    actual = transport.copy_process(["/bin/cat", str(source)], out, expected, control)
    assert (
        out.read_bytes() == source.read_bytes()
        and actual["exit_code"] == 0
        and actual["observed_joined"]
    )
    assert actual["opaque_remote_fd_identity"] == "UNOBSERVED"


@pytest.mark.parametrize("kind", ["truncated", "excess", "wrong-hash"])
def test_stream_failure_preserves_prefix_and_never_receipt(tmp_path, kind):
    source = tmp_path / "invented"
    source.write_bytes(b"01234567")
    size = 8 if kind == "wrong-hash" else 9 if kind == "truncated" else 7
    expected = dict(bytes=size, sha256="0" * 64)
    out = tmp_path / "partial"
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**10, 10)
    with pytest.raises(tc.Stop):
        transport.copy_process(["/bin/cat", str(source)], out, expected, control)
    assert out.is_file() and out.stat().st_size <= size


def test_fixed_remote_command_quotes_and_never_changes_host():
    argv = transport.remote_argv("goethe", "/controlled/public invented/file's.bin")
    assert argv[:6] == ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    assert "iflag=nofollow" in argv[-1]
    with pytest.raises(tc.Stop):
        transport.remote_argv("other-host", "/controlled/path")
    with pytest.raises(tc.Stop):
        transport.remote_argv("goethe", "/controlled/../unsafe")


def test_cleanup_reserve_expired_before_open_or_child(tmp_path, monkeypatch):
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 1_000_000_000, 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_CHILD")

    monkeypatch.setattr(transport.subprocess, "Popen", forbidden)
    output = tmp_path / "not-created"
    with pytest.raises(tc.Stop):
        transport.copy_process(
            ["unused"], output, dict(bytes=0, sha256="0" * 64), control
        )
    assert not output.exists()

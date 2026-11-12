"""Focused publication boundary checks; invented input and real child pipes only."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="module")
def transport():
    path = Path(os.environ.get(
        "S12_RECEIPT_CANDIDATE_SOURCE",
        str(Path(__file__).resolve().parents[1] / "scripts/stage12_ra_g1_terminal_transport.py"),
    ))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    spec = importlib.util.spec_from_file_location("receipt_boundary_actual_source", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invocation(transport, tmp_path, monkeypatch, script, *, seconds=5):
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT", "1")
    source = tmp_path / "remote"
    target = tmp_path / "received"
    source.mkdir(mode=0o700)
    target.mkdir(mode=0o700)
    payload = b'{"invented":"receipt-body-never-log"}\n'
    pub = dict(target=str(source / "RETENTION_RECEIPT.record"), job_id=121,
               deadline_epoch_ns=time.time_ns() + seconds * 10**9, bytes=len(payload))
    rows = [dict(label="receipt", path=pub["target"], bytes=len(payload),
                 sha256=hashlib.sha256(payload).hexdigest())]
    control = transport.pair.Control(time.monotonic_ns(), pub["deadline_epoch_ns"], seconds)
    with pytest.raises(transport.tc.Stop) as caught:
        transport.fetch_batch(
            rows, target, control, expected_uid=os.geteuid(),
            publication=pub, input_bytes=payload,
            testing_argv=[sys.executable, "-c", script], nonce="b" * 32,
        )
    return caught.value, control, payload


def script_for(lines):
    return ("import sys,time\n"
            "body=sys.stdin.buffer.read(65537)\n"
            "assert len(body)<=65536\n" + lines)


def test_generated_publication_uses_conv_excl_and_preserves_live_guard(transport, tmp_path):
    target = tmp_path / "RETENTION_RECEIPT.record"
    publication = dict(target=str(target), job_id=121,
                       deadline_epoch_ns=time.time_ns()+10**10, bytes=3)
    rows = [dict(label="receipt", path=str(target), bytes=3)]
    argv = transport.batch_remote_argv(rows, "b"*32, expected_uid=os.geteuid(),
                                       publication=publication)
    command = argv[-1]
    assert "conv=excl" in command and "oflag=excl" not in command
    assert "squeue -h -j 121 -o" in command and "RUNNING" in command
    assert "sync -f" in command and "mv -T -n" in command
    assert "upload-reservation" in command and "date +%s%N" in command
    assert "publication_mark WRITE" in command
    assert "S12PUB1|"+("b"*32) in command


def test_private_stderr_is_bounded_and_static_markers_are_nonce_bound(transport):
    nonce = "b"*32
    raw = (("S12PUB1|"+("a"*32)+"|FAILED|WRITE|5\n").encode()
           + b"x"*5000+b"\n"
           + ("S12PUB1|"+nonce+"|ENTER|WRITE\n").encode()
           + ("S12PUB1|"+nonce+"|FAILED|WRITE|1\n").encode()
           + ("S12PUB1|"+nonce+"|FAILED|ARBITRARY_SECRET|7\n").encode())
    reader = SimpleNamespace(stderr_capture=bytearray(raw), stderr_bytes=len(raw),
                             stdout_bytes=0, input_written_bytes=0,
                             input_eof_sent_mono_ns=None, streams=set())
    result = transport._publication_failure_diagnostic(reader, None, nonce, [], False)
    assert result["last_preheader_stage"] == "WRITE"
    assert result["first_prefix_failure"] == dict(stage="WRITE", exit_status=1)
    assert result["private_stderr_preview_bytes"] == 4096
    assert len(base64.b64decode(result["private_stderr_preview_b64"])) == 4096
    assert result["private_stderr_truncated_bytes"] == len(raw)-4096
    assert result["captured_stderr_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["invalid_marker_count"] == 1
    assert result["stdout_payload_retained"] is False


def test_real_preheader_exit_preserves_primary_and_joins_child(transport, tmp_path, monkeypatch):
    nonce = "b"*32
    script = script_for(
        "sys.stderr.write('S12PUB1|"+nonce+"|ENTER|WRITE\\n')\n"
        "sys.stderr.write('S12PUB1|"+nonce+"|FAILED|WRITE|7\\n')\n"
        "sys.stderr.flush()\n"
        "sys.exit(7)\n")
    error, control, payload = invocation(transport, tmp_path, monkeypatch, script)
    assert error.args == ("TRUNCATED",)
    diagnostic = error.transport_diagnostic
    observed = diagnostic["publication_check"]
    assert diagnostic["first_phase"] == "START"
    assert observed["first_prefix_failure"] == dict(stage="WRITE", exit_status=7)
    assert observed["child_exit"] == 7 and observed["observed_joined"]
    assert observed["stdout_eof"] and observed["stderr_eof"]
    assert observed["input_written_bytes"] == len(payload)
    assert observed["input_eof_sent_mono_ns"] is not None
    assert observed["cleanup_signals"] == []
    assert payload not in base64.b64decode(observed["private_stderr_preview_b64"])
    assert diagnostic["cleanup_uncertain"] and control.cleanup_uncertain


def test_real_bad_header_is_not_replaced_by_later_child_exit(transport, tmp_path, monkeypatch):
    nonce = "b"*32
    script = script_for(
        "sys.stderr.write('S12PUB1|"+nonce+"|DONE|COMPLETE\\n')\n"
        "sys.stderr.flush()\n"
        "sys.stdout.write('INVALID_HEADER\\n');sys.stdout.flush()\n"
        "sys.exit(9)\n")
    error, _, _ = invocation(transport, tmp_path, monkeypatch, script)
    assert error.args == ("FRAME",)
    observed = error.transport_diagnostic["publication_check"]
    assert observed["prefix_completed_marker"]
    assert observed["child_exit"] == 9 and observed["observed_joined"]
    assert observed["first_prefix_failure"] is None


def test_failure_diagnostic_cannot_replace_original_exception(transport, tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("invented-private-arguments-must-not-escape")
    monkeypatch.setattr(transport, "_publication_failure_diagnostic", broken)
    script = script_for("sys.exit(7)\n")
    error, _, _ = invocation(transport, tmp_path, monkeypatch, script)
    assert error.args == ("TRUNCATED",)
    assert error.transport_diagnostic["publication_check"] == dict(
        version="stage12_receipt_publication_diagnostic_v1", retention="UNCERTAIN", code="UNKNOWN")
    assert "invented-private-arguments" not in json.dumps(error.transport_diagnostic)


def test_real_stalled_preheader_preserves_deadline_and_cleanup_truth(transport, tmp_path, monkeypatch):
    script = script_for("sys.stderr.write('bounded stalled child\\n');sys.stderr.flush()\n"
                        "time.sleep(4)\n")
    started = time.monotonic_ns()
    error, control, _ = invocation(transport, tmp_path, monkeypatch, script, seconds=3)
    elapsed = time.monotonic_ns()-started
    assert error.args == ("DEADLINE",)
    observed = error.transport_diagnostic["publication_check"]
    assert observed["child_exit"] is not None and observed["observed_joined"]
    assert observed["cleanup_signals"] == ["TERM"]
    assert error.transport_diagnostic["cleanup_uncertain"] and control.cleanup_uncertain
    assert elapsed < 3*10**9


def test_actual_child_wait_failure_does_not_replace_primary(transport, tmp_path, monkeypatch):
    original_popen = transport.subprocess.Popen
    def actual_child_with_failed_wait(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        original_wait = child.wait
        def failed_wait(timeout=None):
            if timeout == 0 and child.poll() is not None:
                raise OSError("invented cleanup failure must stay private")
            return original_wait(timeout=timeout)
        child.wait = failed_wait
        return child
    monkeypatch.setattr(transport.subprocess, "Popen", actual_child_with_failed_wait)
    error, control, _ = invocation(transport, tmp_path, monkeypatch,
                                    script_for("sys.exit(7)\n"))
    assert error.args == ("TRUNCATED",)
    observed = error.transport_diagnostic["publication_check"]
    assert observed["child_exit"] == 7
    assert observed["observed_joined"] is False
    assert error.transport_diagnostic["cleanup_uncertain"] and control.cleanup_uncertain
    assert "invented cleanup failure" not in json.dumps(error.transport_diagnostic)

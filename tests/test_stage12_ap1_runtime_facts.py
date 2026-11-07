"""Standalone facts-harness contracts; no AP invocation or real network."""

from pathlib import Path
import importlib.util
import subprocess
import sys
import pytest

FILE = Path(__file__).resolve().parents[1] / "scripts/stage12_ap1_runtime_facts.py"
spec = importlib.util.spec_from_file_location("ap_facts_test", FILE)
facts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(facts)


def selected():
    return dict(
        version=facts.VERSION,
        scope="NO_SERVICE_CHARACTERIZATION_NOT_AP_WORKFLOW",
        source_sha="1" * 40,
        limits=facts.LIMITS.copy(),
        synthetic_timing_associations=True,
        output_name="ap1_runtime_facts_test",
    )


def test_closed_input_and_fixed_caps():
    assert facts.parse(facts.canonical(selected())) == selected()
    for mutate in ("extra", "memory", "source", "scope", "float", "bool"):
        obj = selected()
        if mutate == "extra":
            obj["extra"] = 1
        if mutate == "memory":
            obj["limits"]["rss_bytes"] += 1
        if mutate == "source":
            obj["source_sha"] = "UNKNOWN"
        if mutate == "scope":
            obj["scope"] = "PUBLIC_AP_WORKFLOW"
        if mutate == "float":
            obj["limits"]["seconds"] = 600.0
        if mutate == "bool":
            obj["limits"]["diagnostic_processes"] = True
        with pytest.raises(RuntimeError):
            facts.parse(facts.canonical(obj))
    with pytest.raises(RuntimeError):
        facts.parse(
            facts.canonical(selected()).replace(
                b'"version":', b'"version":"duplicate","version":'
            )
        )


def test_budget_refuses_before_creation_and_never_refunds():
    b = facts.Budget()
    b.charge(8)
    with pytest.raises(RuntimeError):
        b.charge(facts.LIMITS["file_data_bytes"])
    assert b.bytes == 8 and b.creations == 1


def test_owned_graph_deduplicates_but_is_not_native_bound():
    child = {"value": bytearray(16)}
    answer = facts.owned_graph([child, child])
    assert (
        answer["counts_by_type"]["dict"] == 1
        and answer["counts_by_type"]["bytearray"] == 1
    )
    assert "NOT_NATIVE_UPPER" in answer["interpretation"]
    with pytest.raises(RuntimeError):
        facts.owned_graph([child], maximum=1)


def test_representation_rows_use_actual_closed_decoder():
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_sampling_contract as c,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_checkpoints as cp,
    )

    row = facts.timing_row(c, 1)
    decoded = cp._ap_row(row)
    assert decoded == row and decoded is not row
    assert decoded["future_used"] is False
    assert "sampling_runtime_bound_sha256" not in row


def test_actual_installed_audit_hook_denies_without_real_dns_or_process(tmp_path):
    output = tmp_path / "allowed"
    output.mkdir()
    forbidden = tmp_path / "forbidden"
    forbidden.write_bytes(b"INVENTED_DENIED_FILE")
    code = r"""
import importlib.util,sys,pathlib
spec=importlib.util.spec_from_file_location('facts',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=pathlib.Path(sys.argv[2]);blocked=pathlib.Path(sys.argv[3]);m.denial([pathlib.Path(sys.base_prefix)],root,root/'input.json')
(root/'permitted').write_bytes(b'SYNTHETIC')
for event in ('socket.getaddrinfo','socket.connect','subprocess.Popen','os.system','os.fork'):
 try:sys.audit(event)
 except PermissionError:pass
 else:raise AssertionError('missingdenial')
try:blocked.read_bytes()
except PermissionError:pass
else:raise AssertionError('missingfiledenial')
try:(root.parent/'near_miss').write_bytes(b'NO')
except PermissionError:pass
else:raise AssertionError('missingwritedenial')
print('DENIAL_PASS_NO_REAL_DNS_OR_CHILD_LAUNCH')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(FILE), str(output), str(forbidden)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "DENIAL_PASS_NO_REAL_DNS_OR_CHILD_LAUNCH"
    assert (output / "permitted").read_bytes() == b"SYNTHETIC" and not (
        tmp_path / "near_miss"
    ).exists()


def test_private_input_rejects_symlink_mode_and_extra_bytes(tmp_path):
    import hashlib

    raw = facts.canonical(selected())
    path = tmp_path / "input.json"
    path.write_bytes(raw)
    path.chmod(0o600)
    digest = hashlib.sha256(raw).hexdigest()
    assert facts.read_input(path, digest) == selected()
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(RuntimeError):
        facts.read_input(link, digest)
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        facts.read_input(path, digest)
    path.chmod(0o600)
    path.write_bytes(raw + b" ")
    with pytest.raises(RuntimeError):
        facts.read_input(path, digest)


def test_read_identity_ignores_atime_but_not_actual_mode_change(tmp_path, monkeypatch):
    import hashlib
    import os
    from types import SimpleNamespace

    path = tmp_path / "input.json"
    raw = facts.canonical(selected())
    path.write_bytes(raw)
    path.chmod(0o600)
    digest = hashlib.sha256(raw).hexdigest()
    real = os.fstat

    def atime(fd):
        info = real(fd)
        values = {
            name: getattr(info, name)
            for name in (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
        }
        return SimpleNamespace(
            **values, st_atime=info.st_atime + 1, st_atime_ns=info.st_atime_ns + 10**9
        )

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fstat", atime)
        assert facts.read_input(path, digest) == selected()
    original_read = os.read

    def mutate(fd, n):
        result = original_read(fd, n)
        os.fchmod(fd, 0o644)
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "read", mutate)
        with pytest.raises(RuntimeError):
            facts.read_input(path, digest)

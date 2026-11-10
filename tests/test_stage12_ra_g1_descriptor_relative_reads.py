"""Explicit RA descriptor-relative originals; no proc-fd permission is granted."""

import hashlib
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_paged_history as paged
from safe_geocoding_pipeline.preprocessing.stages import s12_public_fresh_reads as fresh
from safe_geocoding_pipeline.preprocessing.stages import s12_public_history as history
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_reader as reader
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "descriptor_relative_diagnostic_under_test", ROOT / "scripts/stage12_ra_g1_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def private_tree(tmp_path):
    root = tmp_path / "root"
    storage.reserve(root)
    storage.write(root / "original", b"SYNTHETIC_ONLY")
    return root


def test_explicit_open_keeps_legacy_default_and_original_flags(tmp_path, monkeypatch):
    root = private_tree(tmp_path)
    actual_open = os.open
    calls = []

    def opened(path, flags, *args, **kwargs):
        calls.append((os.fspath(path), flags, kwargs.get("dir_fd")))
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", opened)
    for selected in (False, True):
        calls.clear()
        with reader.PublicReader(root, descriptor_relative=selected) as original:
            assert original.read(root / "original") == b"SYNTHETIC_ONLY"
            assert original.read(root / "original") == b"SYNTHETIC_ONLY"
        files = [call for call in calls if not call[1] & os.O_DIRECTORY]
        assert len(files) == 1
        name, flags, directory = files[0]
        assert flags == os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if selected:
            assert name == "original" and type(directory) is int
        else:
            assert directory is None
            assert name.endswith("/original")
            assert name.startswith("/proc/self/fd/") if sys.platform == "linux" else name == str(root / "original")


@pytest.mark.parametrize("value", [1, None, "true"])
def test_opt_in_is_an_exact_bool(tmp_path, value):
    root = private_tree(tmp_path)
    with pytest.raises(contract.Stage12Error):
        reader.PublicReader(root, descriptor_relative=value)
    with pytest.raises(contract.Stage12Error):
        fresh.FreshReads(root, descriptor_relative=value)
    with pytest.raises(contract.Stage12Error):
        history.Fresh(root, descriptor_relative=value)


@pytest.mark.parametrize("change", ["symlink", "hardlink", "mode", "replace", "root_mode", "ancestor"])
def test_relative_open_rechecks_current_paths_and_private_files(tmp_path, change):
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    root = private_tree(parent)
    path = root / "original"
    with reader.PublicReader(root, descriptor_relative=True) as original:
        assert original.read(path) == b"SYNTHETIC_ONLY"
        if change == "symlink":
            path.unlink()
            path.symlink_to(root / "missing")
        elif change == "hardlink":
            os.link(path, root / "alias")
        elif change == "mode":
            path.chmod(0o644)
        elif change == "replace":
            path.rename(root / "prior")
            storage.write(path, b"SYNTHETIC_ONLY")
        elif change == "root_mode":
            root.chmod(0o755)
        else:
            parent.rename(tmp_path / "detached")
            parent.mkdir(mode=0o700)
            root.mkdir(mode=0o700)
            storage.write(path, b"SYNTHETIC_ONLY")
        with pytest.raises((contract.Stage12Error, OSError)):
            original.read(path)
        assert original.closed and not original.files and not original.dirs


def test_relative_open_rejects_wrong_fd_and_still_observes_deadline(tmp_path, monkeypatch):
    root = private_tree(tmp_path)
    storage.write(root / "other", b"OTHER")
    actual_open = os.open

    def replaced(path, flags, *args, **kwargs):
        if path == "original" and kwargs.get("dir_fd") is not None:
            path = "other"
        return actual_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "open", replaced)
        with reader.PublicReader(root, descriptor_relative=True) as original:
            with pytest.raises(contract.Stage12Error):
                original.read(root / "original")
            assert original.closed

    state = {"expired": False}

    def check():
        if state["expired"]:
            raise RuntimeError("SYNTHETIC_DEADLINE")

    with reader.PublicReader(root, check=check, descriptor_relative=True) as original:
        state["expired"] = True
        with pytest.raises(RuntimeError, match="SYNTHETIC_DEADLINE"):
            original.read(root / "original")


@pytest.mark.parametrize("kind", ["ordinary", "history", "paged"])
@pytest.mark.parametrize("selected", [False, True])
def test_fresh_original_stages_propagate_only_explicit_opt_in(tmp_path, monkeypatch, kind, selected):
    root = private_tree(tmp_path)
    actual = reader.PublicReader
    options = []

    def create(root, *, check, **kwargs):
        options.append(kwargs.copy())
        return actual(root, check=check, **kwargs)

    monkeypatch.setattr(reader, "PublicReader", create)
    monkeypatch.setattr(history, "_reader_type", create)
    kwargs = {"descriptor_relative": True} if selected else {}
    if kind == "ordinary":
        stage = fresh.FreshReads(root, **kwargs)
    elif kind == "history":
        stage = history.Fresh(root, **kwargs)
    else:
        limits = dict(maximum_entries=32, maximum_name_bytes=128,
                      maximum_total_name_bytes=4096, page_entries=8,
                      maximum_depth=8, maximum_file_bytes=1024)
        stage = paged.Fresh(root, limits=limits, **kwargs)
    with stage:
        assert storage.read(root / "original") == b"SYNTHETIC_ONLY"
    assert options == [kwargs]
    assert not storage.has_read_view() and storage.public_original_reader() is None


def test_real_installed_audit_and_writer_allow_relative_originals_without_proc_grant(tmp_path, monkeypatch):
    """Actual audit/reader/writer; native Linux denial is explicitly simulated.

    Linux proc-fd spelling is selected only on the legacy-reader branch. The
    relative branch uses the actual current host's fd resolver and real dir_fd.
    No full runtime/admission/closure claim is made by this isolated test.
    """
    allocation = tmp_path / "allocation"
    allocation.mkdir(mode=0o700)
    output = allocation / "diagnostic"
    output.mkdir(mode=0o700)
    evidence = allocation / "binding"
    evidence.mkdir(mode=0o700)
    input_path = allocation / "input.json"
    input_path.write_bytes(b"{}\n")
    input_path.chmod(0o600)
    work = output / "work"
    work.mkdir(mode=0o700)
    value = {"SYNTHETIC_ONLY": True}
    storage.write(work / "00000000000000000001.json", contract.canonical(value))
    storage.write(output / "original", b"SYNTHETIC_ONLY")
    outside = tmp_path / "outside"
    outside.write_bytes(b"NOT_AUTHORIZED")
    outside.chmod(0o600)
    secret = output / ".env"
    # Audit must reject this path before any kernel open, including when absent.
    alias = output / "alias"
    alias.symlink_to(outside)

    armed = {"value": False, "events": 0}
    real_hook = sys.addaudithook
    real_spec = importlib.util.spec_from_file_location

    def register(callback):
        def audit(event, values):
            if armed["value"]:
                armed["events"] += 1
                callback(event, values)
        real_hook(audit)

    def specification(name, location, *args, **kwargs):
        selected_spec = real_spec(name, location, *args, **kwargs)
        if name == "ap2_existing_guard":
            loader = selected_spec.loader

            class NativeSimulation:
                def create_module(self, spec):
                    return loader.create_module(spec)

                def exec_module(self, loaded):
                    loader.exec_module(loaded)
                    loaded.deny_linux_network = lambda: "TEST_ONLY_NATIVE_LINUX_NOT_EXECUTED"

            selected_spec.loader = NativeSimulation()
        return selected_spec

    for target, names in (
        (socket, ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr")),
        (socket.socket, ("connect", "connect_ex", "bind", "listen", "sendto")),
        (subprocess, ("Popen", "run", "call", "check_output", "check_call")),
    ):
        for name in names:
            monkeypatch.setattr(target, name, getattr(target, name))
    monkeypatch.setattr(os, "open", os.open)
    monkeypatch.setattr(sys, "addaudithook", register)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", specification)
    guard, native, _, limit, _, _ = diagnostic.install_denials(ROOT, output, input_path, evidence)
    assert native == "TEST_ONLY_NATIVE_LINUX_NOT_EXECUTED"
    limit[0] = 64
    owner = journal.Writer(output / "writer", 1, 5000, lambda: None)
    try:
        armed["value"] = True

        def action():
            assert threading.current_thread() is owner.thread
            observed = fresh.work_manifest_digest(work, 1, descriptor_relative=True)
            assert observed == hashlib.sha256(contract.canonical([value])).hexdigest()
            with reader.PublicReader(output, descriptor_relative=True) as original:
                assert original.read(output / "original") == b"SYNTHETIC_ONLY"
            return observed

        assert owner.call(action) == hashlib.sha256(contract.canonical([value])).hexdigest()
        assert not owner.failed.is_set()
        with monkeypatch.context() as scoped:
            scoped.setattr(reader, "sys", SimpleNamespace(platform="linux"))
            with reader.PublicReader(output) as original:
                with pytest.raises(PermissionError, match="RA_G1_DIAGNOSTIC_ACCESS_DENIED"):
                    original.read(output / "original")
        for path in (outside, alias, Path(f"/proc/{os.getpid()}/fd/0")):
            with pytest.raises(PermissionError, match="RA_G1_DIAGNOSTIC_ACCESS_DENIED"):
                os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        assert not diagnostic.open_allowed(
            secret, write=False, source=ROOT, output=output,
            input_path=input_path, evidence=evidence,
        )
        # The outer credential guard may reject first; its denial is preserved.
        with pytest.raises(PermissionError):
            os.open(secret, os.O_RDONLY | os.O_NOFOLLOW)
        with pytest.raises(PermissionError):
            subprocess.Popen(["NEVER_EXECUTED"])
        assert armed["events"] > 0
        assert callable(guard.bind_reviewed_source_reads)
    finally:
        armed["value"] = False
        owner.abort()
        assert not owner.thread.is_alive()

"""Bounded fake Linux-path and deadline cases; no Linux execution claim."""

import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from test_stage12_public_operations_v2 import offline  # noqa:F401
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

SPEC = importlib.util.spec_from_file_location(
    "entrypoint_repair",
    Path(__file__).parents[1] / "scripts/stage12_wf_ap2_diagnostic.py",
)
d = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = d
SPEC.loader.exec_module(d)


@pytest.fixture
def simulated_proc(monkeypatch):
    original = os.path.realpath
    identities = {
        "/proc": (1, 1, 0, 0, 0),
        "/proc/4242": (1, 2, 0, 0, 0),
        "/proc/self/ns/mnt": (1, 3, 0, 0, 0),
    }
    monkeypatch.setattr(d, "_proc_identity", lambda path: identities[str(path)])
    monkeypatch.setattr(os, "getpid", lambda: 4242)
    monkeypatch.setattr(
        os.path,
        "realpath",
        lambda path, **kw: (
            str(path).replace("/proc/self", "/proc/4242", 1)
            if str(path).startswith("/proc/self")
            else original(path, **kw)
        ),
    )
    hooks = []
    monkeypatch.setattr(
        d,
        "sys",
        SimpleNamespace(
            platform="linux",
            prefix=sys.prefix,
            base_prefix=sys.base_prefix,
            addaudithook=hooks.append,
        ),
    )
    return identities, hooks


def paths(tmp_path):
    return dict(
        source=Path(__file__).parents[1],
        output=tmp_path,
        input_path=tmp_path / "input.json",
        evidence=tmp_path / "proof",
    )


@pytest.mark.parametrize("name", ["status", "cgroup", "mountinfo"])
def test_actual_installed_audit_and_original_m2_reader(
    tmp_path, monkeypatch, simulated_proc, name
):
    identities, hooks = simulated_proc
    params = paths(tmp_path)
    monkeypatch.setattr(os, "open", os.open)  # Restore installed process wrapper too.
    d.install_denials(
        params["source"], tmp_path, params["input_path"], params["evidence"]
    )
    assert len(hooks) == 1
    raw = b"NoNewPrivs:\t1\n" if name == "status" else b"ORIGINAL_MOCKED_KERNEL_BYTES\n"
    fixture = tmp_path / "kernel_original"
    fixture.write_bytes(raw)
    fixture.chmod(0o600)
    real_open, real_path = os.open, m.Path

    def guarded_open(path, flags, *args, **kwargs):
        if str(path).startswith("/proc/"):
            hooks[0]("open", (str(path), None, flags))
            return real_open(fixture, flags, *args, **kwargs)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(
        m,
        "Path",
        lambda path: fixture if str(path).startswith("/proc/") else real_path(path),
    )
    assert m._kernel_read(f"/proc/self/{name}") == raw.decode().strip()
    assert m._kernel_read(f"/proc/4242/{name}") == raw.decode().strip()
    with pytest.raises(PermissionError):
        m._kernel_read(f"/proc/4243/{name}")
    identities["/proc/4242"] = (1, 99, 0, 0, 0)
    with pytest.raises(PermissionError):
        m._kernel_read(f"/proc/self/{name}")


@pytest.mark.parametrize(
    "name",
    [
        "/proc/4243/status",
        "/proc/self/fd/1",
        "/proc/4242/fd/1",
        "/proc/self/../4242/status",
        "/proc/self/environ",
        "/proc/1/mountinfo",
    ],
)
def test_proc_near_misses_reject(tmp_path, simulated_proc, name):
    assert not d.open_allowed(
        name, write=False, self_proc=d.capture_self_proc_identity(), **paths(tmp_path)
    )


def test_actual_m2_observer_with_installed_guard_simulated_linux(
    tmp_path, monkeypatch, simulated_proc
):
    from test_stage12_wf_ap2_assurance import Kernel, m2_inputs, facts

    _, hooks = simulated_proc
    monkeypatch.setattr(os, "open", os.open)
    params = paths(tmp_path)
    d.install_denials(
        params["source"], tmp_path, params["input_path"], params["evidence"]
    )
    kernel = Kernel().install(monkeypatch)
    original_read, original_lines = m._kernel_read, m._kernel_lines
    reads = []

    def read(path, maximum=2048):
        hooks[0]("open", (str(path), None, os.O_RDONLY))
        reads.append(str(path))
        return original_read(path, maximum)

    def lines(path):
        hooks[0]("open", (str(path), None, os.O_RDONLY))
        yield from original_lines(path)

    monkeypatch.setattr(m, "_kernel_read", read)
    monkeypatch.setattr(m, "_kernel_lines", lines)
    *_, record, _ = m2_inputs()
    assert m.observe_linux_domain(record["domain"]) == facts(record)
    assert "/proc/self/status" in reads and "/proc/self/cgroup" in reads
    kernel.nodes[kernel.root].st_ino += 1
    with pytest.raises(c.Stage12Error):
        m.observe_linux_domain(record["domain"])


def test_installed_guard_fd_and_parent_handles_are_narrow(tmp_path, monkeypatch):
    hooks = []
    monkeypatch.setattr(
        d,
        "sys",
        SimpleNamespace(
            platform="darwin",
            prefix=sys.prefix,
            base_prefix=sys.base_prefix,
            addaudithook=hooks.append,
        ),
    )
    monkeypatch.setattr(os, "open", os.open)
    params = paths(tmp_path)
    guard = d.install_denials(
        params["source"], tmp_path, params["input_path"], params["evidence"]
    )
    allowed = tmp_path / "allowed"
    allowed.write_bytes(b"only invented output")
    outside = tmp_path.parent / (tmp_path.name + "_outside")
    outside.write_bytes(b"not an allowed handle")
    parent = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    inside_fd = os.open(allowed, os.O_RDONLY)
    outside_fd = os.open(outside, os.O_RDONLY)
    try:
        hooks[0]("open", (inside_fd, "r", os.O_RDONLY))
        with pytest.raises(RuntimeError, match="CREATION_LIMIT"):
            hooks[0]("os.mkdir", ("child", 0o700, parent))
        guard[3][0] = 3
        hooks[0]("os.mkdir", ("child", 0o700, parent))
        with pytest.raises(PermissionError):
            hooks[0]("open", (outside_fd, "r", os.O_RDONLY))
        with pytest.raises(PermissionError):
            hooks[0]("os.mkdir", ("../escape", 0o700, parent))
        with pytest.raises(PermissionError):
            hooks[0]("open", (f"/proc/self/fd/{inside_fd}", "r", os.O_RDONLY))
    finally:
        for fd in (parent, inside_fd, outside_fd):
            os.close(fd)


def test_write_stale_pid_namespace_and_sensitive_aliases_reject(
    tmp_path, monkeypatch, simulated_proc
):
    identities, _ = simulated_proc
    binding = d.capture_self_proc_identity()
    assert not d.open_allowed(
        "/proc/self/status", write=True, self_proc=binding, **paths(tmp_path)
    )
    identities["/proc/self/ns/mnt"] = (1, 999, 0, 0, 0)
    assert not d.open_allowed(
        "/proc/self/status", write=False, self_proc=binding, **paths(tmp_path)
    )
    assert not d.open_allowed(str(tmp_path / ".env"), write=False, **paths(tmp_path))
    monkeypatch.setattr(os, "getpid", lambda: 4243)
    assert not binding.permits(Path("/proc/4242/status"), Path("/proc/4242/status"))


class Clock:
    value = 0

    def now_ns(self):
        return self.value


@pytest.mark.parametrize("tag", sorted(d.PhaseBoundary.TAGS))
def test_each_actual_operation_rejects_completion_at_deadline(tag):
    clock = Clock()
    boundary = d.PhaseBoundary(clock, 100, 1, lambda: None)

    def work():
        clock.value = 100
        return "must not be accepted"

    with pytest.raises(d.PhaseDeadlineExpired):
        boundary.operation(tag, work)
    row = boundary.snapshot()["operations"][0]
    assert row["entered_ns"] == 0 and row["completed_ns"] == 100 and not row["returned"]


def test_cooperative_phase_expiry_and_global_expiry():
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io

    clock = Clock()
    boundary = d.PhaseBoundary(clock, 100, 1, lambda: None)

    def opener():
        clock.value = 101
        io._checkpoint()

    with io.cooperative_io(boundary.check), pytest.raises(d.PhaseDeadlineExpired):
        boundary.operation("NORMAL_OPEN", opener)
    with pytest.raises(TimeoutError):
        d.PhaseBoundary(
            Clock(), 100, 1, lambda: (_ for _ in ()).throw(TimeoutError())
        ).operation("NORMAL_OPEN", lambda: None)


@pytest.mark.parametrize(
    "error",
    [
        TimeoutError(),
        OSError(5, "unsafe message omitted"),
        c.Stage12Error("S12_PUBLIC_WRITER_FAILED"),
        c.Stage12Error("S12_PUBLIC_SOURCE_CHANGED"),
    ],
)
def test_negative_opener_does_not_swallow_other_failures(error):
    with pytest.raises(type(error)):
        d.expected_stopped_rejection(lambda: (_ for _ in ()).throw(error), lambda: None)


def test_expected_rejection_and_crossing_time_remain_distinct():
    clock = Clock()
    boundary = d.PhaseBoundary(clock, 100, 1, lambda: None)

    def reject():
        raise c.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID")

    d.expected_stopped_rejection(reject, boundary.check)

    def late_reject():
        clock.value = 100
        reject()

    with pytest.raises(d.PhaseDeadlineExpired):
        d.expected_stopped_rejection(late_reject, boundary.check)


def test_primary_survives_checkpoint_failure_and_bounded_timestamps():
    clock, persisted = Clock(), []

    def persist(number, row):
        if number == 2:
            raise OSError(5, "do not replace initiating failure")
        persisted.append(row)

    boundary = d.PhaseBoundary(clock, 100, 1, lambda: None, persist)
    primary = c.Stage12Error("RESPONSE_CONTRACT_INVALID")
    with pytest.raises(c.Stage12Error) as caught:
        boundary.operation("CAPTURE", lambda: (_ for _ in ()).throw(primary))
    assert caught.value is primary and boundary.persistence_uncertain
    assert len(persisted) == 1 and persisted[0]["operations"][0]["completed_ns"] is None
    clean = d.PhaseBoundary(clock, 100, 1, lambda: None)
    for _ in range(8):
        clean.operation("NORMAL_OPEN", lambda: None)
    with pytest.raises(RuntimeError):
        clean.operation("NORMAL_OPEN", lambda: None)


def test_completed_action_failed_checkpoint_is_uncertain_not_pass():
    def persist(number, _row):
        if number == 2:
            raise OSError(5, "invented partial persistence")

    phase = d.PhaseBoundary(Clock(), 100, 1, lambda: None, persist)
    with pytest.raises(OSError):
        phase.operation("NORMAL_OPEN", lambda: None)
    assert phase.persistence_uncertain
    assert not phase.snapshot()["operations"][0]["returned"]

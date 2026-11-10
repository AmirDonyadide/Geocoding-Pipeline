"""Exact native-root boundary; Linux kernel paths are private offline fixtures."""

import ast
import importlib.util
import os
from pathlib import Path
import threading
import time

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as base
from test_s12_ra_g1_core import Authority, G, H, binding, selection

REPO = Path(__file__).resolve().parents[1]
DIAGNOSTIC = REPO / "scripts/stage12_ra_g1_diagnostic.py"
PUBLIC = REPO / "src/safe_geocoding_pipeline/preprocessing/stages/s12_public_runtime.py"
spec = importlib.util.spec_from_file_location("native_root_diagnostic", DIAGNOSTIC)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def source_root_arguments(path, output):
    nodes = [node.value for node in ast.walk(ast.parse(path.read_text()))
             if isinstance(node, ast.keyword) and node.arg == "native_roots"]
    assert len(nodes) == 2
    return [eval(compile(ast.Expression(node), str(path), "eval"), {"output": output})
            for node in nodes]


class KernelSession:
    def __init__(self, root, monkeypatch):
        self.root = root
        self.monkeypatch = monkeypatch
        self.sessions = []
        self.charges, self.reads = [], []
        self.output = root / "output"
        self.output.mkdir(mode=0o700)
        for name in ("phase_data", "nested_existing", "scratch"):
            (self.output / name).mkdir(mode=0o700)
        self.native = self.output / "registered.db"
        self.native.write_bytes(b"SYNTHETIC_ONLY")
        self.native.chmod(0o600)
        self.worker, self.supervisor = os.getpid(), os.getppid()
        self.domain = Path("/sys/fs/cgroup/native-root-synthetic")
        kernel = root / "kernel"
        kernel.mkdir(mode=0o700)
        self.mapping = {}
        records = {
            str(self.domain / "cgroup.procs"): f"{self.worker} {self.supervisor}\n",
            "/proc/sys/kernel/random/boot_id": "11111111-1111-1111-1111-111111111111\n",
        }
        for pid in (self.worker, self.supervisor):
            parent = self.supervisor if pid == self.worker else 1
            start = 20 if pid == self.worker else 10
            records[f"/proc/{pid}/stat"] = (
                f"{pid} (synthetic) S {parent} " + "0 " * 17 + f"{start}\n"
            )
            records[f"/proc/{pid}/status"] = (
                f"Pid: {pid}\nUid: " + " ".join([str(os.geteuid())] * 4)
                + "\nVmRSS: 16384 kB\nVmHWM: 16384 kB\nThreads: 2\n"
            )
            records[f"/proc/{pid}/cgroup"] = "0::/native-root-synthetic\n"
        records[f"/proc/{self.worker}/ns/cgroup"] = "synthetic namespace\n"
        records[f"/proc/{self.worker}/ns/mnt"] = "synthetic namespace\n"
        for index, (virtual, text) in enumerate(records.items()):
            actual = kernel / str(index)
            actual.write_text(text)
            actual.chmod(0o600)
            self.mapping[virtual] = actual
        domain_actual = kernel / "domain"
        domain_actual.mkdir(mode=0o700)
        self.mapping[str(self.domain)] = domain_actual
        real_open, real_stat, real_resolve = os.open, Path.stat, Path.resolve

        def opened(path, *args, **kwargs):
            return real_open(self.mapping.get(os.fspath(path), path), *args, **kwargs)

        def stated(path, *args, **kwargs):
            return real_stat(self.mapping.get(str(path), path), *args, **kwargs)

        def resolved(path, *args, **kwargs):
            return path if str(path) in self.mapping else real_resolve(path, *args, **kwargs)

        monkeypatch.setattr(os, "open", opened)
        monkeypatch.setattr(Path, "stat", stated)
        monkeypatch.setattr(Path, "resolve", resolved)
        monkeypatch.setattr(__import__("sys"), "platform", "linux")
        monkeypatch.setenv("SAFE_EXECUTION_SITE", "goethe-nhr")
        monkeypatch.setenv("SLURM_JOB_ID", "42")

    def arguments(self, scope, *, phase=1, native_roots=None):
        selected = selection(scope)
        first = selected["limits"]["stages"][0]
        selected["limits"]["stages"] = [
            {**first, "id": index, "phase": index, "deadline_ms": 1000,
             "attempts": 10 if index == 1 else 0,
             "events": 100 if index == 1 else 0,
             "logical_write_bytes": 2**30 // phase,
             "creations": 100 // phase}
            for index in range(1, phase + 1)
        ]
        bound = binding(selected)
        authority = Authority(selected)
        context = e.capture_supervisor_context(
            scope=scope, source_git_sha=G, selection=selected,
            private_paths=dict(allocation_root=str(self.root),
                               resource_evidence_root=str(self.output),
                               scratch_root=str(self.output / "scratch")),
            supervisor_pid=self.supervisor, run_nonce=H,
            check=lambda: None, read_charge=lambda n, k: self.reads.append((n, k)),
        )
        context_path = self.root / f"context-{scope}-{phase}.record"
        context_path.write_bytes(base.canonical(context))
        context_path.chmod(0o600)
        campaigns = [{"label": f"phase{i}"} for i in range(1, 5 if scope == "REPRESENTATIVE_NO_SERVICE" else 12)]
        label = campaigns[phase - 1]["label"] if phase <= len(campaigns) else "whole_task"
        return dict(
            authority=authority, config=dict(output_directory=str(self.output), campaigns=campaigns,
                resource_execution=dict(schema_version=e.EXECUTION_REQUEST,
                    supervisor_context_path=str(context_path), supervisor_context_sha256=e.o.digest(context))),
            binding=bound, selection=selected, evidence_root=self.output / (label + "_resources"),
            deadline_ns=time.monotonic_ns() + 1_000_000_000, phase_id=phase,
            check=lambda: None, counters=lambda: {key: 0 for key in m.COUNTERS},
            charge=lambda n, k: self.charges.append((n, k)),
            read_charge=lambda n, k: self.reads.append((n, k)),
            native_paths=(self.native,), native_roots=native_roots,
            scope_start_ns=time.monotonic_ns(),
        )

    def start(self, scope, phase, native_roots):
        arguments = self.arguments(scope, phase=phase, native_roots=native_roots)
        if scope == "REPRESENTATIVE_NO_SERVICE":
            phase_id = arguments.pop("phase_id")
            value = diagnostic.start_phase_resource(e, source_entry_ns=arguments["scope_start_ns"],
                phase_id=phase_id, clock_ns=time.monotonic_ns, **arguments)
        else:
            value = e.start_session(**arguments)
        self.sessions.append(value)
        return value

    def cleanup(self):
        for session in self.sessions:
            session.abort()
            session.monitor.thread.join(1)
            session.writer.thread.join(1)
            assert not session.monitor.thread.is_alive()
            assert not session.writer.thread.is_alive()


@pytest.fixture
def kernel_session(tmp_path, monkeypatch):
    value = KernelSession(tmp_path, monkeypatch)
    yield value
    value.cleanup()


@pytest.mark.parametrize("scope,path,phase,index", [
    ("REPRESENTATIVE_NO_SERVICE", DIAGNOSTIC, 1, 0),
    ("REPRESENTATIVE_NO_SERVICE", DIAGNOSTIC, 5, 1),
    ("PUBLIC_SYNTHETIC_ONLY", PUBLIC, 1, 0),
    ("PUBLIC_SYNTHETIC_ONLY", PUBLIC, 12, 1),
])
def test_actual_source_roots_reach_real_observer_and_durable_start(kernel_session, scope, path, phase, index):
    roots = source_root_arguments(path, kernel_session.output)[index]
    assert type(roots) is tuple
    value = kernel_session.start(scope, phase, roots)
    assert type(value.observer) is m.LinuxObserver
    assert value.observer.native_roots == (kernel_session.output,)
    assert value.observer.paths == (kernel_session.native,)
    receipt = value.require_start_acknowledged()
    row = receipt["row"]
    assert row["kind"] == "START" and row["seq"] == 1
    assert receipt["ack_ns"] < value.deadline
    assert value.writer.acked >= 1
    assert value.writer.path.stat().st_size >= m.CODEC_BYTES
    assert value.original_reader(row["visible_identity_inventory_sha256"])["origin"] == "LIVE_KERNEL_OBSERVATION"
    assert row["native_visibility"]["unknown_native_file_count"] == "NOT_PROVEN"
    assert row["native_visibility"]["deleted_open_bytes"] == "NOT_MEASURED"
    assert row["native_visibility"]["registered_paths_checked"] == 1
    assert (kernel_session.output / "nested_existing").is_dir()


def test_rejected_real_observer_has_no_orphan_writer(kernel_session):
    before = set(threading.enumerate())
    with pytest.raises(base.Stage12Error, match="RA_G1_NATIVE_DISCOVERY"):
        kernel_session.start("REPRESENTATIVE_NO_SERVICE", 1, [kernel_session.output])
    assert not [thread for thread in threading.enumerate() if thread not in before]


@pytest.mark.parametrize("failure", ["close_error", "expired_clock"])
def test_constructor_cleanup_preserves_primary_and_uncertainty(kernel_session, monkeypatch, failure):
    actual_close = m.ObservationWriter.close
    captured, events = [], []

    def close(writer, deadline):
        captured.append((writer, deadline))
        if failure == "expired_clock":
            writer.clock = lambda: deadline
        actual_close(writer, deadline)
        if failure == "close_error":
            raise OSError(28, "SYNTHETIC_CLEANUP_DETAIL")

    def trace(event, *args, **kwargs):
        events.append((event, kwargs.get("cleanup", False)))

    monkeypatch.setattr(m.ObservationWriter, "close", close)
    arguments = kernel_session.arguments("REPRESENTATIVE_NO_SERVICE", native_roots=[kernel_session.output])
    original_deadline = arguments["deadline_ns"]
    arguments["startup_trace"] = trace
    with pytest.raises(base.Stage12Error, match="RA_G1_NATIVE_DISCOVERY") as caught:
        e.start_session(**arguments)
    assert caught.value.args == ("RA_G1_NATIVE_DISCOVERY",)
    assert len(captured) == 1 and captured[0][1] == original_deadline
    writer = captured[0][0]
    assert writer.closing and writer.poisoned
    assert writer.rows == writer.acked == 0
    assert writer.path.stat().st_size == 0
    writer.thread.join(1)  # Fixture ownership after original guard has failed.
    assert not writer.thread.is_alive()
    assert events.index(("START_FAILED", False)) < events.index(("ABORT_FAILED", True))


def test_selected_native_root_alias_and_unregistered_path_still_reject(kernel_session):
    alias = kernel_session.root / "alias"
    alias.symlink_to(kernel_session.output, target_is_directory=True)
    with pytest.raises(base.Stage12Error):
        kernel_session.start("REPRESENTATIVE_NO_SERVICE", 1, (alias,))
    arguments = kernel_session.arguments("PUBLIC_SYNTHETIC_ONLY", phase=12,
                                          native_roots=(kernel_session.output,))
    arguments["native_paths"] = (kernel_session.root / "outside.db",)
    with pytest.raises(base.Stage12Error, match="RA_G1_NATIVE_DISCOVERY"):
        e.start_session(**arguments)
    assert not [thread for thread in threading.enumerate()
                if thread.name == "ra-g1-evidence-writer"]

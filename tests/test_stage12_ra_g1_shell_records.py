"""Actual shell producers with real local waits; clocks/sync are explicit stubs."""

from contextlib import ExitStack
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import time
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "cluster/goethe_nhr/stage12_ra_g1_allocation.sbatch"
CONTROLLER = ROOT / "scripts/stage12_ra_g1_allocation.py"
NON_EMITTER_SHA = "15104ee5c2baff27c7552f12dd19c8a03d116ff3ba17428b321c0ca14e3f0a9e"
BASELINE_CONTROLLER_SHA = "5c631632dbdaabedee757e414dff0477af660ddd1428bfff46cbe9159848463d"
G, H = "2" * 40, "1" * 64
LEGACY_WAIT_EMITTER = '        (set -o noclobber; printf \'{"version":"stage12_ra_g1_supervisor_wait_v1","source_sha":"%s","selection_sha256":"%s","supervisor_pid":%d,"pid":%d,"exit_code":%d,"wait_status":%d,"acquired_mono_ns":%d}\\n\' "$STAGE12_RA_SHA" "$STAGE12_RA_SELECTION_SHA" "$$" "$pid" "$status" "$((status*256))" "$STAGE12_RA_NOW" > "$return_path")'
CASES = (
    ("baseline", "baseline_ra_run", "COLLECTOR", 0, 120),
    ("collector_ok", "ra_run", "COLLECTOR", 0, 120),
    ("collector_fail", "ra_run", "COLLECTOR", 7, 120),
    ("binder_ok", "ra_run", "BINDER", 0, 720),
    ("binder_fail", "ra_run", "BINDER", 7, 720),
    ("worker_ok", "ra_run", "PHASE_RUNNER", 0, 7200),
    ("worker_fail", "ra_run", "PHASE_RUNNER", 7, 7200),
)


def controller(source=None):
    spec = importlib.util.spec_from_file_location("shell_record_controller", CONTROLLER)
    module = importlib.util.module_from_spec(spec)
    if source is None:
        spec.loader.exec_module(module)
    else:
        exec(compile(source, str(CONTROLLER), "exec"), module.__dict__)
    return module


def function(source, name):
    start = source.index(name + "() {")
    end_line = source.index("\n", start)
    if source[start:end_line].endswith(" }"):
        return source[start:end_line + 1]
    return source[start:source.index("\n}\n", start) + 3]


def driver(source):
    definitions = "".join(function(source, name) for name in (
        "ra_tick", "ra_check", "ra_utility", "ra_pause", "ra_run", "ra_record"))
    current_wait = next(line for line in function(source, "ra_run").splitlines()
                        if "printf '{" in line and "supervisor_wait_v1" in line)
    old_run = function(source, "ra_run").replace(
        "ra_run() {", "baseline_ra_run() {", 1).replace(
        current_wait, LEGACY_WAIT_EMITTER, 1)
    prologue = """set -euo pipefail
umask 077
ulimit -c 0
FIXTURE=$1
STAGE12_RA_SHA='2222222222222222222222222222222222222222'
STAGE12_RA_SELECTION_SHA='1111111111111111111111111111111111111111111111111111111111111111'
STAGE12_RA_PYTHON=/bin/bash
STAGE12_RA_CHILD=''
STAGE12_RA_SYNTHETIC_TICK=0
STAGE12_RA_END_NS=8161000000000
printf '%d\\n' "$$" > "$FIXTURE/parent.pid"
"""
    stubs = """
# SYNTHETIC_MAC_CLOCK_AND_SYNC_ONLY: not a Linux durability/clock qualification.
ra_tick() { STAGE12_RA_SYNTHETIC_TICK=$((STAGE12_RA_SYNTHETIC_TICK+1)); STAGE12_RA_NOW=$((1000000000+STAGE12_RA_SYNTHETIC_TICK*1000)); }
ra_pause() { :; }
sleep() { return 97; }
timeout() {
    [[ "$#" == 6 && "$1" == --signal=TERM && "$2" == --kill-after=1s && "$3" == 5s && "$4" == sync && "$5" == -f ]]
    shift 3
    "$@"
}
sync() { [[ "$#" == 2 && "$1" == -f ]]; printf '%s\\n' "$2" >> "$FIXTURE/sync.receipts"; }
run_case() {
    local label=$1 producer=$2 role=$3 expected=$4 seconds=$5 observed=0
    STAGE12_RA_ROOT="$FIXTURE/$label"
    STAGE12_RA_RETURN="$STAGE12_RA_ROOT/worker.wait.record"
    STAGE12_RA_PYTHONS=0
    STAGE12_RA_UTILITIES=0
    export STAGE12_SYNTHETIC_WORKER_PID="$STAGE12_RA_ROOT/child.pid"
    export STAGE12_SYNTHETIC_EXIT="$expected"
    if "$producer" "$seconds" "$role" -c 'printf "%d\\n" "$$" > "$STAGE12_SYNTHETIC_WORKER_PID"; exit "$STAGE12_SYNTHETIC_EXIT"'; then observed=0; else observed=$?; fi
    [[ "$observed" == "$expected" ]]
    printf '%d|%d|%d\\n' "$observed" "$STAGE12_RA_PYTHONS" "$STAGE12_RA_UTILITIES" > "$STAGE12_RA_ROOT/returned"
}
"""
    cases = "".join("run_case %s %s %s %d %d\n" % case for case in CASES)
    terminals = """
if (
    STAGE12_RA_ROOT="$FIXTURE/terminal_fail"
    STAGE12_RA_STATE="$STAGE12_RA_ROOT/intent.record"
    STAGE12_RA_STATUS=INCOMPLETE
    trap ra_record EXIT
    exit 7
); then exit 98; else terminal_status=$?; fi
[[ "$terminal_status" == 7 ]]
STAGE12_RA_ROOT="$FIXTURE/terminal_ok"
STAGE12_RA_STATE="$STAGE12_RA_ROOT/intent.record"
STAGE12_RA_STATUS=COMPLETE_REPRESENTATIVE_NO_SERVICE
trap ra_record EXIT
exit 0
"""
    return prologue + definitions + old_run + stubs + cases + terminals


@pytest.fixture(scope="module")
def produced(tmp_path_factory):
    root = tmp_path_factory.mktemp("source_shell_records")
    os.chmod(root, 0o700)
    for name in [case[0] for case in CASES] + ["terminal_fail", "terminal_ok"]:
        (root / name).mkdir(mode=0o700)
    source = SHELL.read_text()
    script = root / "actual_source_driver.bash"
    script.write_text(driver(source))
    script.chmod(0o600)
    argv = ["/bin/bash", str(script), str(root)]
    real_popen, launches = subprocess.Popen, []

    def closed_popen(args, *positional, **keywords):
        if args != argv or launches:
            raise RuntimeError("UNPLANNED_CHILD_DENIED")
        launches.append(tuple(args))
        return real_popen(args, *positional, **keywords)

    def denied(*args, **kwargs):
        raise RuntimeError("OFFLINE_NETWORK_DENIED")

    started = time.monotonic_ns()
    with ExitStack() as stack:
        stack.enter_context(patch.object(subprocess, "Popen", closed_popen))
        stack.enter_context(patch.object(socket.socket, "connect", denied))
        stack.enter_context(patch.object(socket.socket, "connect_ex", denied))
        stack.enter_context(patch.object(socket, "create_connection", denied))
        stack.enter_context(patch.object(socket, "getaddrinfo", denied))
        result = subprocess.run(
            argv, env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
            capture_output=True, timeout=20, check=False)
        (root / "driver.stdout").write_bytes(result.stdout)
        (root / "driver.stderr").write_bytes(result.stderr)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        assert len(launches) == 1
        (root / "EXECUTION_BASIS.json").write_text(json.dumps({
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "driver_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            "elapsed_ns": time.monotonic_ns() - started,
            "python_test_processes": 1, "driver_bash": 1,
            "real_worker_bash_children": 7, "wait_noclobber_subshells": 7,
            "failure_terminal_outer_subshells": 1, "terminal_noclobber_subshells": 2,
            "total_reserved_process_units": 19,
            "clock_and_sync": "SYNTHETIC_MAC_STUBS_NOT_LINUX_QUALIFICATION",
            "real_wait_and_child_pid": True,
        }, sort_keys=True) + "\n")
        for path in root.rglob("*"):
            if path.is_file():
                path.chmod(0o600)
        yield root, controller()


def wait_path(root, label, role):
    leaf = {"COLLECTOR": "collector.wait.record",
            "BINDER": "binder.wait.record",
            "PHASE_RUNNER": "worker.wait.record"}[role]
    return root / label / leaf


def test_non_emitters_and_durability_invocations_unchanged(produced):
    root, _ = produced
    source = SHELL.read_text()
    stripped = "\n".join("<RECORD_EMITTER>" if "printf '{" in line else line
                         for line in source.splitlines()) + "\n"
    assert hashlib.sha256(stripped.encode()).hexdigest() == NON_EMITTER_SHA
    receipts = (root / "sync.receipts").read_text().splitlines()
    assert len(receipts) == 9 and len(set(receipts)) == 9
    assert all(Path(path).is_file() for path in receipts)


def test_preserved_actual_old_producer_is_rejected_and_old_mapper_stays_unknown(produced):
    root, m = produced
    raw = wait_path(root, "baseline", "COLLECTOR").read_bytes()
    with pytest.raises(RuntimeError, match="CANONICAL_REQUIRED") as captured:
        m.parse(raw)
    old_source = CONTROLLER.read_text().replace(
        "RA_G1_ALLOCATION_INVALID RA_G1_CANONICAL_REQUIRED RA_G1_FIELDS",
        "RA_G1_ALLOCATION_INVALID RA_G1_FIELDS", 1)
    assert hashlib.sha256(old_source.encode()).hexdigest() == BASELINE_CONTROLLER_SHA
    assert controller(old_source).safe_failure(captured.value)["code"] == "UNKNOWN"
    assert m.safe_failure(captured.value)["code"] == "RA_G1_CANONICAL_REQUIRED"


@pytest.mark.parametrize("label,producer,role,status,seconds", CASES[1:])
def test_real_source_waits_are_canonical_typed_and_bound_to_actual_children(
    produced, label, producer, role, status, seconds
):
    root, m = produced
    path = wait_path(root, label, role)
    raw = path.read_bytes()
    value = m.parse(raw)
    assert raw == m.canonical(value) and raw.endswith(b"\n") and not raw.endswith(b"\n\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert value["pid"] == int((root / label / "child.pid").read_text())
    assert value["supervisor_pid"] == int((root / "parent.pid").read_text())
    assert all(type(value[key]) is int for key in (
        "pid", "supervisor_pid", "exit_code", "wait_status", "acquired_mono_ns"))
    assert value["exit_code"] == status and value["wait_status"] == status * 256
    assert (root / label / "returned").read_text().strip() == f"{status}|1|1"
    arguments = dict(source_sha=G, allocation_selection_sha256=H,
                     supervisor_pid=value["supervisor_pid"], process_pid=value["pid"])
    if status:
        with pytest.raises(RuntimeError, match="CHILD_FAILED"):
            m.validate_wait_record(value, **arguments)
    else:
        assert m.validate_wait_record(value, **arguments) == value
        for key in ("source_sha", "selection_sha256", "pid"):
            changed = deepcopy(value)
            changed[key] = value[key] + 1 if key == "pid" else "3" * len(value[key])
            with pytest.raises(RuntimeError, match="CHILD_FAILED"):
                m.validate_wait_record(changed, **arguments)


@pytest.mark.parametrize("label,stage,role", [
    ("collector_ok", "collect", "COLLECTOR"), ("binder_ok", "bind", "BINDER")])
def test_actual_handoff_consumer_reopens_actual_shell_wait(produced, label, stage, role):
    root, m = produced
    directory = root / label
    waited = m.parse(wait_path(root, label, role).read_bytes())
    selected = {"source_git_sha": G}
    context = {"private_paths": {"allocation_root": str(directory)},
               "supervisor": {"pid": int((root / "parent.pid").read_text())}}
    prefix = dict(source_read_calls=0, source_read_bytes=0, checks=0,
                  monitor_usage=dict(bytes=0, creations=0, rows=0, directories=0),
                  metadata={stage: dict(write_bytes=0, creations=0, file_attempts=0)})
    handoff = dict(
        schema_version=m.HANDOFF, source_sha=G, allocation_selection_sha256=H,
        resource_selection_sha256=m.digest(selected), scope=m.SCOPE, stage=stage,
        supervisor_context_sha256=m.digest(context), process_pid=waited["pid"],
        counter_prefix=prefix, predecessor_handoff_sha256=None,
        administrative_sessions=[], post_prefix_contract=m.HANDOFF_CONTRACT)
    raw = m.canonical(handoff)
    path = directory / (("collector" if stage == "collect" else "binder") + ".handoff.record")
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o600)
    charges = []
    value, totals, identity, returned = m.load_handoff_prefix(
        context, selected, stage=stage, check=lambda: None,
        read_charge=lambda calls, size: charges.append((calls, size)))
    assert value == handoff and returned == waited and identity == m.digest(handoff)
    assert totals["source_read_calls"] == 2 and totals["checks"] == 7
    assert sum(calls for calls, _ in charges) == 4
    assert sum(size for _, size in charges) == len(raw) + len(m.canonical(waited))


@pytest.mark.parametrize("label,code,status", [
    ("terminal_ok", 0, "COMPLETE_REPRESENTATIVE_NO_SERVICE"),
    ("terminal_fail", 7, "INCOMPLETE")])
def test_actual_exit_trap_intent_is_canonical_and_preserves_contract(produced, label, code, status):
    root, m = produced
    path = root / label / "intent.record"
    raw = path.read_bytes()
    value = m.parse(raw)
    assert set(value) == set(
        "B_service_authority deadline_mono_ns exit_code observed_mono_ns_lower "
        "python_invocations selection_sha256 source_sha status utility_invocations version".split())
    assert raw == m.canonical(value)
    assert value["version"] == "stage12_ra_g1_supervisor_terminal_intent_v1"
    assert value["B_service_authority"] is False
    assert value["exit_code"] == code and value["status"] == status
    assert value["source_sha"] == G and value["selection_sha256"] == H
    assert all(type(value[key]) is int for key in (
        "deadline_mono_ns", "exit_code", "observed_mono_ns_lower",
        "python_invocations", "utility_invocations"))
    assert value["observed_mono_ns_lower"] + 10000000 < value["deadline_mono_ns"]
    assert value["python_invocations"] == 1 and value["utility_invocations"] == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_strict_reader_and_exact_safe_code_redaction(produced):
    root, m = produced
    raw = wait_path(root, "worker_ok", "PHASE_RUNNER").read_bytes()
    for invalid in (b" " + raw, raw.rstrip(b"\n"), raw + b"\n"):
        with pytest.raises(RuntimeError, match="CANONICAL_REQUIRED"):
            m.parse(invalid)
    with pytest.raises(RuntimeError, match="FIELDS"):
        m.parse(b'{"x":1,"x":1}\n')
    assert m.safe_failure(RuntimeError("RA_G1_CANONICAL_REQUIRED"))["code"] == "RA_G1_CANONICAL_REQUIRED"

    class Derived(RuntimeError):
        pass

    for error in (ValueError("RA_G1_CANONICAL_REQUIRED"),
                  Derived("RA_G1_CANONICAL_REQUIRED"),
                  RuntimeError("RA_G1_CANONICAL_REQUIRED", "UNSAFE_DETAIL"),
                  RuntimeError("RA_G1_CANONICAL_REQUIRED UNSAFE_DETAIL /private/path")):
        result = m.safe_failure(error)
        assert result["code"] == "UNKNOWN"
        assert "UNSAFE_DETAIL" not in json.dumps(result) and "/private/path" not in json.dumps(result)

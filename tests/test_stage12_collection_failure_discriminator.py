"""Closed collection failure metadata; invented callbacks are never authority."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_collection_driver as driver
import stage12_ra_g1_nonwaiting_submit as terminal
import stage12_ra_g1_one_shot_controls as observer
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_verify as verify
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics

tc = pair.tc
MODULES = (tc, pair, transport, verify)


def admission_metadata():
    def digest(module):
        return hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    policy = dict(pair.REMOTE_IDENTITY_PAIR_CONTROL_LIMITS)
    policy.update(one_shot_controls_sha256=digest(observer),
                  collection_driver_sha256=digest(driver),
                  transport_sha256=digest(transport), selected_remote_pair="/TEST_ONLY/pair")
    return dict(one_shot_control_policy=policy, helper_sha256=digest(tc),
                parent_sha256=digest(pair), verifier_sha256=digest(verify),
                submission_terminal_policy=dict(module_sha256=digest(terminal)))


def descriptor(admission=None):
    # Real original-source reader and complete hash/EOF/identity checks.
    owner = pair.Control(time.monotonic_ns(), time.time_ns() + 10**10, 10)
    result = driver.prepare_failure_descriptor(
        MODULES, observer, terminal, admission or admission_metadata(), owner)
    assert owner.read_bytes <= diagnostics.FOREGROUND_MAX_SOURCE_BYTES + 262144
    assert owner.read_calls < 256
    assert not owner.cleanup_uncertain
    return result


def test_actual_observer_exception_has_closed_class_pinned_frames_no_payload():
    prepared = descriptor()
    assert not prepared.preparation_uncertain
    error = None
    try:
        observer.rows_for({"remote_pair": None}, transport)
    except BaseException as actual:
        error = actual
    assert type(error) is TypeError
    old_tb = error.__traceback__
    result = driver.capture_failure_descriptor(prepared, error, "OBSERVE")
    assert result["exception_class"] == "TYPE_ERROR"
    assert result["operation"] == "OBSERVE"
    assert any(row["module"] == "COLLECTION_OBSERVER" for row in result["frames"])
    assert len(result["frames"]) <= 4
    assert len(json.dumps(result).encode()) < 4096
    assert error.__traceback__ is old_tb
    assert set(result["frames"][0]) == {"module", "function", "source_sha256", "line"}


def test_collection_map_can_pin_actual_exec_namespace_without_module_registration():
    prepared = descriptor()
    assert any(row[0] is driver._execute.__code__ for row in prepared._codes.values())
    assert not prepared.preparation_uncertain
    assert diagnostics.FOREGROUND_MODULES[0][0] == "DIAGNOSTIC"
    assert len(diagnostics.FOREGROUND_MODULES) == 14
    assert len(diagnostics.COLLECTION_MODULES) == 7


def test_unverified_map_and_unknown_subclass_remain_uncertain_and_redacted():
    bad = admission_metadata()
    bad["one_shot_control_policy"]["one_shot_controls_sha256"] = "0" * 64
    assert descriptor(bad).preparation_uncertain
    class PrivateTypeError(TypeError):
        pass
    error = PrivateTypeError("SECRET_ARGUMENT")
    result = driver.capture_failure_descriptor(descriptor(), error, "SECRET_OPERATION")
    assert result["exception_class"] == "UNKNOWN"
    assert result["operation"] == "UNAVAILABLE"
    assert "SECRET" not in json.dumps(result)


def test_capture_failure_cannot_replace_original_exception(monkeypatch):
    error = ValueError("SECRET_ARGUMENT")
    prepared = descriptor()
    monkeypatch.setattr(prepared, "capture", lambda original: (_ for _ in ()).throw(MemoryError()))
    result = driver.capture_failure_descriptor(prepared, error, "OBSERVE")
    assert result["retention_uncertain"] is True
    assert result["exception_class"] == "UNKNOWN"
    assert error.args == ("SECRET_ARGUMENT",)
    assert "SECRET" not in json.dumps(result)


def test_pin_short_reads_stop_before_original_shared_counter_overrun(monkeypatch):
    admission = admission_metadata()
    owner = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
    driver.install_selected_read_limit(owner, pair)
    end = owner.end
    original_read = os.read
    monkeypatch.setattr(os, "read", lambda fd, amount: original_read(fd, min(amount, 1)))
    prepared = driver.prepare_failure_descriptor(MODULES, observer, terminal, admission, owner)
    assert prepared.preparation_uncertain
    assert prepared.preparation_read_calls == driver.SOURCE_MAP_READ_ATTEMPTS == 64
    assert owner.read_calls == owner.selected_read_attempts == 64
    assert owner.read_bytes == prepared.preparation_read_bytes == 64
    assert owner.end == end and not owner.cleanup_uncertain


@pytest.mark.parametrize("limit", ["FOREGROUND_MAX_NODES", "FOREGROUND_MAX_CODES",
    "FOREGROUND_MAX_POSITIONS", "FOREGROUND_MAX_LINE_ENTRIES", "FOREGROUND_MAX_SOURCE_BYTES"])
def test_collection_map_preparation_limits_are_fail_uncertain(monkeypatch, limit):
    # Lower limits ONLY in this negative component; no accepted source/gate is bypassed.
    monkeypatch.setattr(diagnostics, limit, 1)
    assert descriptor().preparation_uncertain


def test_actual_outer_owner_captures_before_classifier_and_cleanup(tmp_path, monkeypatch):
    # Unit isolation ONLY: this admission metadata is not an authority record.
    # The separate connected smoke exercises the actual canonical validators.
    admission = admission_metadata()
    admission.update(version="TEST_ONLY_UNIT_METADATA", maximum_preparation_and_native_processes=384)
    monkeypatch.setattr(driver, "load_verified_admission", lambda *a, **kw: admission)
    observed = []
    primary = TypeError("SECRET_FIRST_EXCEPTION")
    captured = driver.capture_failure_descriptor
    def capture(prepared, error, stage):
        observed.append(("capture", error, stage))
        return captured(prepared, error, stage)
    monkeypatch.setattr(driver, "capture_failure_descriptor", capture)
    safe_code = pair.safe_code
    def classify(error):
        observed.append(("classify", error, None))
        return safe_code(error)
    monkeypatch.setattr(pair, "safe_code", classify)
    cleanup = []
    real_close = os.close
    armed = [False]
    def close(fd):
        real_close(fd)
        if armed[0] and not cleanup:
            cleanup.append(fd)
            raise OSError(5, "SECRET_CLEANUP_EXCEPTION")
    monkeypatch.setattr(driver.os, "close", close)
    def fail_poll(*a, **kw):
        armed[0] = True
        raise primary
    monkeypatch.setattr(observer, "poll", fail_poll)
    popen = subprocess.Popen
    children = []
    def launch(*a, **kw):
        proc = popen([sys.executable, "-c", "import time; time.sleep(.05)"], **kw)
        children.append(proc)
        return proc
    monkeypatch.setattr(driver.subprocess, "Popen", launch)
    records = []
    policy = admission["one_shot_control_policy"]
    task = {key: policy[key] for key in (
        "version", "maximum_probes", "probe_seconds", "minimum_start_spacing_seconds",
        "spacing_anchor", "maximum_process_units", "directory_readiness", "selected_remote_pair")}
    command = dict(task_control_selection=task, nonce="1" * 32,
                   selected_original_submission_epoch_ceiling=time.time_ns() + 30 * 10**9,
                   admission_sha256="2" * 64, submit_argv=["TEST_ONLY_FINITE_CHILD"])
    # Legacy version is matched explicitly for this isolated failure-path test.
    admission["one_shot_control_policy"]["version"] = observer.VERSION
    command["task_control_selection"]["version"] = observer.VERSION
    plan = dict(source_git_sha="0" * 40, remote_pair=policy["selected_remote_pair"],
                window_end_epoch_ns=time.time_ns() + 30 * 10**9,
                source_uid=os.geteuid(), source_gid=os.getegid(),
                local_directory_scope=transport.TASK_LOCAL_DIRECTORY_SCOPE)
    result = driver.execute(plan, command, [], [], tmp_path, MODULES, observer,
        None, None, lambda *a: None, lambda: None,
        lambda name, row: records.append((name, copy.deepcopy(row))), {})
    assert result["status"] == "INCOMPLETE"
    first = result["first_failure"]
    assert first["stage"] == "OBSERVE" and first["code"] == "UNCLASSIFIED", first
    assert first["first_failure_descriptor"]["exception_class"] == "TYPE_ERROR"
    assert observed[0] == ("capture", primary, "OBSERVE")
    assert observed[1][0] == "classify" and observed[1][1] is primary
    assert records[-2][0] == "FIRST_FAILURE.record"
    assert records[-2][1] == first
    assert cleanup and len(children) == 1 and children[0].returncode == 0
    assert "SECRET" not in json.dumps(result)

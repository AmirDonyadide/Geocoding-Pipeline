"""Focused opt-in owner tests; source/module fixtures are explicitly synthetic."""
import hashlib
import json
import os
import threading
import types
from unittest import mock

from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling_contract as sampling


class Clock:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def now_ns(self):
        with self.lock:
            self.calls += 1
            return self.calls


def _identity(value):
    return tuple(getattr(value, field) for field in
                 ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
                  "st_size", "st_mtime_ns", "st_ctime_ns"))


def _source(tmp_path, body="def fault(error):\n    raise error\n", *, module_id="DIAGNOSTIC"):
    relative = dict(d.FOREGROUND_MODULES)[module_id]
    path = tmp_path / relative
    path.parent.mkdir(mode=0o700, parents=True)
    path.write_text(body)
    module = types.ModuleType("TEST_ONLY_pinned_module")
    module.__file__ = str(path)
    exec(compile(body, str(path), "exec"), module.__dict__)
    raw = body.encode()
    selected = dict(path=relative, bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest())
    reads = []

    def verify_source(actual, row):
        assert actual == path and row == selected
        before = actual.lstat()
        fd = os.open(actual, os.O_RDONLY | os.O_NOFOLLOW)
        digest = hashlib.sha256()
        consumed = 0
        try:
            assert _identity(os.fstat(fd)) == _identity(before)
            while consumed < row["bytes"]:
                block = os.read(fd, min(4096, row["bytes"] - consumed))
                assert block
                consumed += len(block)
                digest.update(block)
            assert os.read(fd, 1) == b""
            assert _identity(os.fstat(fd)) == _identity(actual.lstat()) == _identity(before)
        finally:
            os.close(fd)
        reads.append(consumed)
        return consumed == row["bytes"] and digest.hexdigest() == row["sha256"]

    prepared = d.prepare_first_failure_descriptor(
        [(module_id, module)], [selected], source_root=tmp_path,
        verify_source=verify_source,
    )
    assert not prepared.preparation_uncertain
    assert reads == [len(raw)]
    return module, prepared, selected, verify_source


def _caught(module, error):
    try:
        module.fault(error)
    except BaseException as actual:
        return actual
    raise AssertionError("fixture did not raise")


def _ap(**changes):
    row = dict(version=d.SAMPLING_FAULT_VERSION, code="ACQUISITION_GAP", stage="ACQUIRE",
               predicate_origin="ACQUISITION_INTERVAL", caller_context="ACQUIRE",
               previous_observed_mono_ns=100, candidate_observed_mono_ns=100000101,
               health_time_mono_ns=None, check_mono_ns=100000102,
               bound_ns=100000000, reserved_seq=1, operands_status="AVAILABLE")
    row.update(changes)
    return row


def test_legacy_snapshot_schema_and_clock_are_unchanged():
    clock = Clock()
    owner = d.Failures(clock)
    owner.record("ADMISSION", TypeError("not retained"))
    result = owner.snapshot()
    assert set(result) == {"version", "scope", "first_initiating_failure",
                           "first_secondary_failure", "secondary_observations",
                           "earlier_response_rejection"}
    assert result["first_initiating_failure"]["family"] == "UNCLASSIFIED"
    assert clock.calls == 1
    owner.record_sampling_fault(_ap())
    assert owner.snapshot() == result


def test_first_admission_class_frames_and_secondary_precedence(tmp_path):
    module, prepared, selected, _ = _source(tmp_path)
    clock = Clock()
    owner = d.Failures(clock, first_failure_descriptor=prepared, sampling=True)
    error = _caught(module, TypeError("SECRET_ARGUMENT"))
    original_traceback = BaseException.__dict__["__traceback__"].__get__(error, BaseException)
    owner.record("ADMISSION", error, work_id=7, attempt=1)
    owner.record_sampling_fault(_ap())
    owner.record("CLEANUP", OSError(5, "SECRET_PATH"))
    owner.record_sampling_fault(_ap(code="DRAIN_EXPIRED", stage="DRAIN"))
    result = owner.snapshot()
    first = result["foreground_first_failure"]["first_failure"]
    assert first["exception_class"] == "TYPE_ERROR"
    assert first["frames"][-1]["module"] == "DIAGNOSTIC"
    assert first["frames"][-1]["function"] == "fault"
    assert first["frames"][-1]["source_sha256"] == selected["sha256"]
    assert result["first_initiating_failure"]["operation"] == "ADMISSION"
    assert result["first_secondary_failure"]["operation"] == "CLEANUP"
    assert result["sampling_first_fault"]["first_fault"]["code"] == "ACQUISITION_GAP"
    assert clock.calls == 2
    assert BaseException.__dict__["__traceback__"].__get__(error, BaseException) is original_traceback
    encoded = json.dumps(result)
    assert "SECRET_ARGUMENT" not in encoded and "SECRET_PATH" not in encoded
    first["frames"][0]["function"] = "MUTATED_COPY"
    assert owner.snapshot()["foreground_first_failure"]["first_failure"]["frames"][0]["function"] != "MUTATED_COPY"


def test_unknown_exception_hooks_and_secret_payload_are_not_evaluated(tmp_path):
    module, prepared, _, _ = _source(tmp_path)
    touched = []

    class Hazard(RuntimeError):
        def __str__(self):
            touched.append("str")
            raise AssertionError

        @property
        def __traceback__(self):
            touched.append("traceback")
            raise AssertionError

        @property
        def args(self):
            touched.append("args")
            raise AssertionError

    error = _caught(module, Hazard("PRIVATE_SECRET_PAYLOAD"))
    owner = d.Failures(Clock(), first_failure_descriptor=prepared)
    owner.record("ADMISSION", error)
    result = owner.snapshot()
    assert result["foreground_first_failure"]["first_failure"]["exception_class"] == "UNKNOWN"
    assert touched == [] and "PRIVATE_SECRET_PAYLOAD" not in json.dumps(result)


def test_same_filename_does_not_register_an_untrusted_code_object(tmp_path):
    module, prepared, _, _ = _source(tmp_path)
    unrelated = types.ModuleType("TEST_ONLY_unregistered")
    exec(compile("def forged():\n    raise ValueError('SECRET')\n", module.__file__, "exec"), unrelated.__dict__)
    try:
        unrelated.forged()
    except ValueError as error:
        result = prepared.capture(error)
    assert result["exception_class"] == "VALUE_ERROR"
    assert result["frames"] == [] and result["unmapped"] > 0


def test_traceback_limits_and_unavailable_are_explicit(tmp_path):
    body = "def fault(error, n=40):\n    if n: return fault(error, n-1)\n    raise error\n"
    module, prepared, _, _ = _source(tmp_path, body)
    result = prepared.capture(_caught(module, ValueError("SECRET")))
    assert result["visited"] == 32 and len(result["frames"]) == 4
    assert result["traversal_truncated"] and result["leaf_frames_truncated"]
    absent = prepared.capture(ValueError("SECRET"))
    assert absent["traceback_unavailable"] and absent["frames"] == []


def test_changed_pin_and_observer_failure_stay_uncertain(tmp_path):
    module, prepared, selected, _ = _source(tmp_path)
    bad = d.prepare_first_failure_descriptor(
        [("DIAGNOSTIC", module)], [selected], source_root=tmp_path,
        verify_source=lambda path, row: False,
    )
    assert bad.preparation_uncertain
    owner = d.Failures(Clock(), first_failure_descriptor=prepared)
    error = _caught(module, TypeError("SECRET"))
    with mock.patch.object(d.FirstFailureDescriptor, "capture", side_effect=MemoryError):
        owner.record("ADMISSION", error)
    result = owner.snapshot()
    assert result["first_initiating_failure"]["operation"] == "ADMISSION"
    assert result["foreground_first_failure"]["retention_uncertain"]
    assert result["foreground_first_failure"]["first_failure"] is None


def test_same_original_exception_propagates(tmp_path):
    module, prepared, _, _ = _source(tmp_path)
    owner = d.Failures(Clock(), first_failure_descriptor=prepared)
    original = TypeError("SECRET")
    try:
        try:
            module.fault(original)
        except BaseException as error:
            owner.record("ADMISSION", error)
            raise
    except BaseException as observed:
        assert observed is original
    else:
        raise AssertionError("original exception lost")


def test_sampling_schema_first_only_and_payload_redaction():
    assert d._SAMPLING_CODES == frozenset(sampling.TYPES["SamplingFailure"]["enum"])
    owner = d.Failures(Clock(), sampling=True)
    owner.record_sampling_fault(_ap(reserved_seq=0))
    owner.record_sampling_fault(_ap(code="WRITE_UNCERTAIN"))
    assert owner.snapshot()["sampling_first_fault"]["first_fault"]["code"] == "ACQUISITION_GAP"
    assert owner.snapshot()["sampling_first_fault"]["first_fault"]["reserved_seq"] is None
    touched = []

    class Hazard:
        def __eq__(self, other):
            touched.append("eq")
            raise AssertionError

    rejected = d.Failures(Clock(), sampling=True)
    rejected.record_sampling_fault(_ap(version=Hazard(), code="PRIVATE_SECRET", stage=Hazard()))
    result = rejected.snapshot()
    assert result["sampling_first_fault"]["retention_uncertain"]
    assert touched == [] and "PRIVATE_SECRET" not in json.dumps(result)
    rejected.record_sampling_fault(_ap())
    assert rejected.snapshot() == result


def test_concurrent_foreground_and_sampling_keep_their_first_owner(tmp_path):
    module, prepared, _, _ = _source(tmp_path)
    owner = d.Failures(Clock(), first_failure_descriptor=prepared, sampling=True)
    gate = threading.Barrier(2)
    failures = []

    def worker(index, cls):
        try:
            error = _caught(module, cls("SECRET"))
            gate.wait(timeout=2)
            owner.record("ADMISSION", error, work_id=index)
            owner.record_sampling_fault(_ap(reserved_seq=index))
        except BaseException as error:
            failures.append(type(error).__name__)

    threads = [threading.Thread(target=worker, args=(1, TypeError)),
               threading.Thread(target=worker, args=(2, ValueError))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)
    assert not failures and not any(thread.is_alive() for thread in threads)
    result = owner.snapshot()
    expected = {1: "TYPE_ERROR", 2: "VALUE_ERROR"}[result["first_initiating_failure"]["work_id"]]
    assert result["foreground_first_failure"]["first_failure"]["exception_class"] == expected
    assert result["secondary_observations"] == 1
    assert result["sampling_first_fault"]["first_fault"]["reserved_seq"] in (1, 2)


def test_added_snapshot_bytes_have_a_fixed_four_kib_envelope(tmp_path):
    name = "f" * 128
    body = f"def {name}(error,n=5):\n    if n: return {name}(error,n-1)\n    raise error\nfault={name}\n"
    module, prepared, _, _ = _source(tmp_path, body)
    owner = d.Failures(Clock(), first_failure_descriptor=prepared, sampling=True)
    owner.record("ADMISSION", _caught(module, RuntimeError("SECRET")))
    owner.record_sampling_fault(_ap(**{key: 2**64-1 for key in d._SAMPLING_NUMBERS}))
    result = owner.snapshot()
    extra = {key: result[key] for key in ("foreground_first_failure", "sampling_first_fault")}
    assert len(json.dumps(extra, sort_keys=True, separators=(",", ":")).encode()) <= 4096


def test_source_position_limit_rejects_before_retaining_extra_positions(tmp_path):
    module, _, selected, verify = _source(tmp_path)
    with mock.patch.object(d, "FOREGROUND_MAX_POSITIONS", 1):
        prepared = d.prepare_first_failure_descriptor(
            [("DIAGNOSTIC", module)], [selected], source_root=tmp_path,
            verify_source=verify,
        )
    assert prepared.preparation_uncertain and len(prepared._codes) == 0


def test_preparation_pending_and_iterator_caps_are_conservative(tmp_path):
    body = "def fault(error):\n    raise error\ndef other():\n    return None\n"
    module, _, selected, verify = _source(tmp_path, body)
    for name in ("FOREGROUND_MAX_CODES", "FOREGROUND_MAX_LINE_ENTRIES"):
        with mock.patch.object(d, name, 1):
            prepared = d.prepare_first_failure_descriptor(
                [("DIAGNOSTIC", module)], [selected], source_root=tmp_path,
                verify_source=verify,
            )
        assert prepared.preparation_uncertain and len(prepared._codes) == 0


def test_sampling_failure_class_requires_its_verified_source_module(tmp_path):
    body = "class SamplingFailure(RuntimeError):\n    pass\ndef fault(error):\n    raise error\n"
    module, prepared, selected, _ = _source(tmp_path, body, module_id="PUBLIC_SAMPLING")
    touched = []

    class Payload:
        def __str__(self):
            touched.append("str")
            raise AssertionError

        def __repr__(self):
            touched.append("repr")
            raise AssertionError

        def __eq__(self, other):
            touched.append("eq")
            raise AssertionError

    error = _caught(module, module.SamplingFailure(Payload()))
    owner = d.Failures(Clock(), first_failure_descriptor=prepared)
    owner.record("ADMISSION", error)
    assert owner.snapshot()["foreground_first_failure"]["first_failure"]["exception_class"] == "SAMPLING_FAILURE"
    unverified = d.prepare_first_failure_descriptor(
        [("PUBLIC_SAMPLING", module)], [selected], source_root=tmp_path,
        verify_source=lambda path, row: False,
    )
    assert unverified.capture(error)["exception_class"] == "UNKNOWN"

    class Child(module.SamplingFailure):
        pass

    child = _caught(module, Child(Payload()))
    assert prepared.capture(child)["exception_class"] == "UNKNOWN"
    assert touched == []
    json.dumps(owner.snapshot())

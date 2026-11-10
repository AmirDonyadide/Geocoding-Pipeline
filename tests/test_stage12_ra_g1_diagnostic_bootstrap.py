"""Direct representative runner startup tests; synthetic facts grant no execution."""

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
from test_s12_ra_g1_core import (
    Authority,
    binding,
    observation,
    original_observation,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

ROOT = Path(__file__).resolve().parents[1]
SECOND = 10**9


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location(
        "synthetic_ra_g1_diagnostic_bootstrap", ROOT / "scripts/stage12_ra_g1_diagnostic.py"
    )
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def resource_factory(tmp_path):
    """Replace only supervisor discovery; use real monitor, writer and ACK original."""
    selected, _adoption, adoption_reader = bootstrap_inputs()
    selected["limits"]["processing_ms"] = 8160000
    selected["limits"]["scheduler_s"] = 8400
    selected["limits"]["stages"][0].update(deadline_ms=346000, reserve_ms=80000)
    authority = Authority(selected)
    source_entry = 1_000_000_000
    now = [source_entry + 29 * SECOND]
    values, calls, charges, reads = [], [], [], []

    def start_session(**arguments):
        calls.append(arguments)

        def factory(retain):
            def observer(kind):
                row = observation(selected, enter=now[0], kind=kind)
                row["visible_identity_inventory_sha256"] = retain(original_observation(row))
                return {key: row[key] for key in (
                    "readings", "counters", "native_visibility", "visible_identity_inventory_sha256"
                )}
            return observer

        value = e.PhaseSession(
            authority=authority, binding=binding(selected), selection=selected,
            resource_evidence_root=tmp_path / f"phase{len(values)+1}",
            pids=(123,), counter_provider=lambda: dict.fromkeys(m.COUNTERS, 0),
            charge=lambda n,k: charges.append((n,k)), check=arguments["check"],
            deadline_ns=arguments["deadline_ns"], phase_id=arguments["phase_id"],
            admitted_process_provider=lambda: (123,),
            read_charge=lambda n,k: reads.append((n,k)), observer_factory=factory,
            clock_ns=lambda: now[0], scope_start_ns=arguments["scope_start_ns"],
            bootstrap_adoption_reader=adoption_reader,
            **({"bootstrap_prefix": arguments["bootstrap_prefix"]}
                if "bootstrap_prefix" in arguments else {}),
        )
        values.append(value)
        if result.before_start is not None:
            result.before_start(value)
        return value.start()

    result = SimpleNamespace(
        execution=SimpleNamespace(start_session=start_session),
        source_entry=source_entry, now=now, sessions=values, calls=calls,
        selected=selected, charges=charges, reads=reads,
        before_start=None,
    )
    yield result
    for value in values:
        try:
            value.abort()
        except BaseException:
            pass
        finally:
            value.monitor.stop_event.set()
            if value.monitor.thread.is_alive():
                value.monitor.thread.join(1)
            with value.writer.condition:
                value.writer.closing = True
                value.writer.condition.notify_all()
            value.writer.thread.join(1)
        assert not value.monitor.thread.is_alive() and not value.writer.thread.is_alive()


def first_session(runner, resource_factory, *, phase_id=1, scope_start=None, input_version=None):
    state = resource_factory
    return runner.start_phase_resource(
        state.execution, source_entry_ns=state.source_entry, phase_id=phase_id,
        input_version=runner.BOOTSTRAP_VERSION if input_version is None else input_version, selection=state.selected,
        clock_ns=lambda: state.now[0],
        scope_start_ns=state.source_entry if scope_start is None else scope_start,
        deadline_ns=state.source_entry + 346*SECOND, check=lambda: None,
    )


def responses():
    raw = "{\"invented_test_only\":\"東京\"}"
    return {"responses": [dict(fixture_id="1"*64, size=1, raw_utf8=raw,
        payload_sha256=hashlib.sha256(raw.encode("utf8")).hexdigest())]}


@pytest.mark.parametrize("input_family", ["BOOTSTRAP_VERSION", "SHARED_LEASE_VERSION"])
@pytest.mark.parametrize("elapsed_ns", [29*SECOND, 30*SECOND])
def test_first_entry_real_durable_ack_precedes_bodies_and_work(
    runner, resource_factory, monkeypatch, elapsed_ns, input_family
):
    state = resource_factory
    state.now[0] = state.source_entry + elapsed_ns
    value = first_session(runner, state, input_version=getattr(runner, input_family))
    events = []
    actual_ack = value.require_start_acknowledged
    actual_bodies = runner.materialize_response_bodies

    def acknowledged():
        actual_ack()  # Freshly read the real START/ACK original; no fake boolean.
        events.append("ACK")

    def initialize():
        prefix = value.monitor.prefix()
        assert prefix["last_seq"] >= 1 and value.writer.acked >= 1
        assert (value.root / "observations.bin").stat().st_size >= 1024
        assert len(list(value.original_root.iterdir())) >= 1
        events.append("RUNTIME")
        return "SYNTHETIC_CURRENT_RUNTIME"

    def bodies(data, **kwargs):
        events.append("BODY_BYTES")
        return actual_bodies(data, **kwargs)

    def adapter(version):
        events.append("ADAPTER")
        return version

    monkeypatch.setattr(value, "require_start_acknowledged", acknowledged)
    monkeypatch.setattr(runner, "materialize_response_bodies", bodies)
    runtime, encoded, control, validation = runner.prepare_first_phase(
        value, responses(), initialize_runtime=initialize,
        validation=SimpleNamespace(Validation=adapter, CORPUS_VERSION="TEST_ONLY"),
        check=value.check,
    )
    assert events == ["ACK", "RUNTIME", "BODY_BYTES", "ADAPTER"]
    assert runtime == "SYNTHETIC_CURRENT_RUNTIME" and control and validation == "TEST_ONLY"
    assert next(iter(encoded.values())).decode("utf8").endswith("東京\"}")
    assert state.calls[0]["bootstrap_prefix"] == dict(
        role="PHASE_RUNNER", source_entry_ns=state.source_entry,
        bootstrap_end_ns=state.source_entry+elapsed_ns,
    )
    assert value.monitor.scope_start == value.bootstrap_prefix["bootstrap_end_ns"]
    assert value.bootstrap_prefix["source_entry_ns"] == state.source_entry
    assert state.calls[0]["scope_start_ns"] == state.source_entry
    assert value.deadline == state.source_entry+346*SECOND
    assert value.deadline-state.now[0] == 346*SECOND-elapsed_ns
    assert runner.PHASES[0][1] == 346000
    assert state.selected["limits"]["stages"][0]["reserve_ms"] == 80000


@pytest.mark.parametrize("input_family", ["BOOTSTRAP_VERSION", "SHARED_LEASE_VERSION"])
@pytest.mark.parametrize("failure", ["late_ack", "missing_ack"])
def test_late_or_missing_real_start_ack_never_reaches_body_or_work(
    runner, resource_factory, monkeypatch, failure, input_family
):
    state = resource_factory
    real_fsync = m.os.fsync

    def before_start(value):
        def fsync(fd):
            is_stream = m.os.fstat(fd).st_ino == value.writer.path.stat().st_ino
            if is_stream and failure == "missing_ack":
                raise OSError(5, "SYNTHETIC_START_ACK_NOT_DURABLE")
            result = real_fsync(fd)
            if is_stream:
                state.now[0] = state.source_entry + 30*SECOND + 1
            return result

        monkeypatch.setattr(m.os, "fsync", fsync)

    state.before_start = before_start
    work = []
    with pytest.raises(c.Stage12Error):
        value = first_session(runner, state, input_version=getattr(runner, input_family))
        runner.prepare_first_phase(
            value, responses(), initialize_runtime=lambda: work.append("RUNTIME"),
            validation=SimpleNamespace(Validation=lambda version: work.append("ADAPTER"),
                CORPUS_VERSION="TEST_ONLY"), check=value.check,
        )
    assert work == []
    assert state.sessions and not state.sessions[0].completed
    assert state.calls[0]["deadline_ns"] == state.source_entry+346*SECOND
    if failure == "late_ack":
        assert state.sessions[0].writer.acked >= 1
    else:
        assert state.sessions[0].writer.acked == 0
        assert state.sessions[0].writer.poisoned


@pytest.mark.parametrize("input_family", ["BOOTSTRAP_VERSION", "SHARED_LEASE_VERSION"])
@pytest.mark.parametrize("phase_id", [2, 3, 4, 5])
def test_later_phase_omits_exception_and_preserves_strict_original_gap(
    runner, resource_factory, phase_id, input_family
):
    state = resource_factory
    with pytest.raises(c.Stage12Error, match="RA_G1_MONITOR_GAP"):
        first_session(runner, state, phase_id=phase_id,
            scope_start=state.now[0]-SECOND-1, input_version=getattr(runner, input_family))
    assert "bootstrap_prefix" not in state.calls[0]
    assert state.calls[0]["scope_start_ns"] == state.now[0]-SECOND-1
    assert state.calls[0]["deadline_ns"] == state.source_entry+346*SECOND
    assert not state.sessions[0].completed


def test_payload_utf8_hash_and_size_checks_remain_strict(runner):
    data = responses()
    assert len(runner.materialize_response_bodies(data)) == 1
    for mutate in ("payload_sha256", "raw_utf8"):
        changed = deepcopy(data)
        changed["responses"][0][mutate] = "0"*64 if mutate == "payload_sha256" else ""
        with pytest.raises(RuntimeError):
            runner.materialize_response_bodies(changed)
    oversized = responses()
    oversized["responses"][0]["raw_utf8"] = "東京"*65536
    with pytest.raises(RuntimeError):
        runner.materialize_response_bodies(oversized)


def test_first_phase_expiry_after_ack_cannot_reset_source_origin(
    runner, resource_factory
):
    state = resource_factory
    value = first_session(runner, state)
    state.now[0] = state.source_entry + 346*SECOND
    work = []
    with pytest.raises(c.Stage12Error, match="RA_G1_DEADLINE"):
        runner.prepare_first_phase(
            value, responses(), initialize_runtime=lambda: work.append("RUNTIME"),
            validation=SimpleNamespace(Validation=lambda version: work.append("ADAPTER"),
                CORPUS_VERSION="TEST_ONLY"), check=value.check,
        )
    assert work == [] and value.deadline == state.source_entry + 346*SECOND


@pytest.mark.parametrize("new_input,new_selection", [(False,False),(True,True),(True,False),(False,True)])
def test_bootstrap_input_and_selection_pairing_rejects_mixed_families(
    runner, new_input, new_selection
):
    family = runner.BOOTSTRAP_VERSION if new_input else runner.VERSION
    selected = dict(scope=runner.SCOPE, schema_version=runner.BOOTSTRAP_SELECTION
        if new_selection else "stage12_resource_selection_ra_g1_v1")
    if new_input == new_selection:
        runner.validate_resource_family(family, selected)
    else:
        with pytest.raises(RuntimeError, match="RA_G1_DIAGNOSTIC_RESOURCE_FAMILY"):
            runner.validate_resource_family(family, selected)


def test_default_old_input_never_requests_a_bootstrap_exception(runner):
    calls, marker = [], object()

    def start(**arguments):
        calls.append(arguments)
        return marker

    def no_prefix_clock():
        raise AssertionError("old family must not capture a bootstrap boundary")

    selected = dict(scope=runner.SCOPE, schema_version="stage12_resource_selection_ra_g1_v1")
    actual = runner.start_phase_resource(
        SimpleNamespace(start_session=start), source_entry_ns=100, phase_id=1,
        clock_ns=no_prefix_clock, selection=selected, scope_start_ns=100,
        deadline_ns=346000000100,
    )
    assert actual is marker and "bootstrap_prefix" not in calls[0]
    assert calls[0]["scope_start_ns"] == 100
    assert calls[0]["deadline_ns"] == 346000000100


def test_bootstrap_input_cannot_select_public_or_protected_scope(runner):
    for scope in ("PUBLIC_SYNTHETIC_ONLY", "DEVELOPMENT_ONLY", "DEVELOPMENT_LOCAL_PREPARATION"):
        with pytest.raises(RuntimeError, match="RA_G1_DIAGNOSTIC_RESOURCE_FAMILY"):
            runner.validate_resource_family(runner.BOOTSTRAP_VERSION,
                dict(scope=scope, schema_version=runner.BOOTSTRAP_SELECTION))

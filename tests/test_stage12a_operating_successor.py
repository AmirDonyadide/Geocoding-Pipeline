"""Operating-only 12A selection and fixed safe boundaries; invented inputs only."""

from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from test_stage10_context_pipeline import synthetic_inputs as synthetic_inputs
from test_stage09_reference_evaluator import reference_view as reference_view
from test_stage12a_catalog_lineage import configuration
from test_stage12_b2_lineage import interpretation
from stage12_b2_synthetic import Authority, offline as offline
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_lineage as lineage,
    s12_retrieval_contract as c,
    s12a_local_preparation as local,
)


def successor(tmp_path):
    value = configuration(tmp_path)
    value["resources"]["max_duration_seconds"] = 43200
    value["operating_policy"] = {
        "schema_version": local.OPERATING_POLICY,
        "application_seconds": 43200,
        "scheduler_seconds": 44100,
        "progress_policy": local.PROGRESS_VERSION,
        "decision_record_path": str(
            local.CONTROLLED_ROOT / "controls/fresh/OPERATING_DECISION.record"
        ),
        "decision_record_sha256": local.OPERATING_DECISION_SHA256,
    }
    return value


def test_legacy_controls_and_launcher_remain_unchanged(tmp_path):
    value = configuration(tmp_path)
    value["resources"]["max_duration_seconds"] = 7200
    assert local.validate_config(value) is value
    assert local.selected_operating_policy(value) is None
    local.validate_operating_entry(value, {})
    value["resources"]["max_duration_seconds"] = 7201
    with pytest.raises(c.Stage12Error, match="S12A_RESOURCE_SCOPE"):
        local.validate_config(value)
    root = Path(__file__).resolve().parents[1]
    old = (root / "cluster/goethe_nhr/stage12a_catalog_lineage.sbatch").read_bytes()
    assert (
        b.sha(old).hex()
        == "d3435407801a2e2a5b8fd972c74f0b679698a40c849319a176f8d61df764546e"
    )
    new = (
        root / "cluster/goethe_nhr/stage12a_catalog_lineage_43200.sbatch"
    ).read_text()
    assert "#SBATCH --time=12:15:00" in new
    assert "STAGE12A_OPERATING_POLICY=stage12a_operating_43200_v1" in new
    assert "STAGE12A_SCHEDULER_SECONDS=44100" in new


def test_successor_requires_exact_explicit_selection_and_native_entry(tmp_path):
    value = successor(tmp_path)
    assert local.validate_config(value) is value
    local.validate_operating_entry(
        value,
        {
            "STAGE12A_OPERATING_POLICY": local.OPERATING_POLICY,
            "STAGE12A_SCHEDULER_SECONDS": "44100",
        },
    )
    for env in (
        {},
        {"STAGE12A_OPERATING_POLICY": "UNKNOWN", "STAGE12A_SCHEDULER_SECONDS": "44100"},
        {
            "STAGE12A_OPERATING_POLICY": local.OPERATING_POLICY,
            "STAGE12A_SCHEDULER_SECONDS": "7500",
        },
    ):
        with pytest.raises(c.Stage12Error, match="S12A_OPERATING_ENTRY"):
            local.validate_operating_entry(value, env)
    with pytest.raises(c.Stage12Error, match="S12A_OPERATING_ENTRY"):
        local.validate_operating_entry(
            configuration(tmp_path),
            {
                "STAGE12A_OPERATING_POLICY": local.OPERATING_POLICY,
                "STAGE12A_SCHEDULER_SECONDS": "44100",
            },
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "UNKNOWN"),
        ("application_seconds", 7200),
        ("scheduler_seconds", 7500),
        ("progress_policy", "UNKNOWN"),
        ("decision_record_sha256", "a" * 64),
        ("extra", True),
    ],
)
def test_mixed_or_unknown_operating_records_fail_closed(tmp_path, field, value):
    config = successor(tmp_path)
    config["operating_policy"][field] = value
    with pytest.raises(c.Stage12Error, match="S12A_OPERATING_POLICY"):
        local.validate_config(config)


def test_successor_rejects_wrong_runtime_or_uncontrolled_decision(tmp_path):
    value = successor(tmp_path)
    value["resources"]["max_duration_seconds"] = 43201
    with pytest.raises(c.Stage12Error, match="S12A_RESOURCE_SCOPE"):
        local.validate_config(value)
    value = successor(tmp_path)
    value["operating_policy"]["decision_record_path"] = "/tmp/OPERATING_DECISION.record"
    with pytest.raises(c.Stage12Error, match="S12A_CONTROLLED_LOCATION"):
        local.validate_config(value)


def test_successor_progress_uses_one_original_deadline_without_resets(
    tmp_path, monkeypatch
):
    tmp_path.chmod(0o700)
    now = [1000.0]
    monkeypatch.setattr(local.time, "monotonic", lambda: now[0])
    started = now[0]
    rows = []
    progress = local.Progress(
        tmp_path / "progress.jsonl",
        started=started,
        check=lambda: local.check_duration(started, 43200),
        output=rows.append,
    )
    try:
        progress(local.PROGRESS_LABELS[0])
        now[0] += 7200
        progress(local.PROGRESS_LABELS[1])
        assert [row["elapsed_ms"] for row in rows] == [0, 7200000]
        now[0] = started + 43200
        with pytest.raises(c.Stage12Error, match="S12A_RUNTIME_LIMIT"):
            progress(local.PROGRESS_LABELS[2])
        assert progress.started == started and progress.count == 2
        with pytest.raises(c.Stage12Error, match="S12A_RUNTIME_LIMIT"):
            local.check_duration(started, 7200)
    finally:
        progress.close()


def test_bounded_progress_is_durable_safe_and_completely_read_back(
    tmp_path, monkeypatch
):
    tmp_path.chmod(0o700)
    now = [10.0]
    monkeypatch.setattr(local.time, "monotonic", lambda: now[0])
    rows, synced = [], []
    real_fsync = os.fsync

    def sync(fd):
        synced.append(fd)
        real_fsync(fd)

    monkeypatch.setattr(local.os, "fsync", sync)
    path = tmp_path / "progress.jsonl"
    progress = local.Progress(
        path,
        started=now[0],
        check=lambda: local.check_duration(10.0, 43200),
        output=rows.append,
    )
    try:
        for label in local.PROGRESS_LABELS:
            progress(label)
            now[0] += 1
        result = progress.snapshot()
        assert result["records"] == result["max_records"] == 32
        assert result["bytes"] == path.stat().st_size <= result["max_bytes"] == 16384
        assert result["sha256"] == b.sha(path.read_bytes()).hex()
        assert len(synced) >= 33 and path.stat().st_mode & 0o777 == 0o600
        assert all(
            set(row) == {"schema_version", "sequence", "boundary", "elapsed_ms"}
            for row in rows
        )
        assert rows == [json.loads(line) for line in path.read_bytes().splitlines()]
        with pytest.raises(c.Stage12Error, match="S12A_PROGRESS_BOUNDARY"):
            progress("INVENTED_PRIVATE_PATH_OR_ROW_CANARY")
        assert b"CANARY" not in path.read_bytes()
        path.write_bytes(path.read_bytes() + b"{}\n")
        with pytest.raises(c.Stage12Error, match="S12A_PROGRESS_CHANGED"):
            progress.snapshot()
    finally:
        progress.close()


def test_progress_callback_failure_is_not_reclassified_or_formatted(tmp_path):
    tmp_path.chmod(0o700)
    expected = ValueError("INVENTED_CALLBACK_CANARY")

    def output(_):
        raise expected

    progress = local.Progress(
        tmp_path / "progress.jsonl",
        started=local.time.monotonic(),
        check=lambda: None,
        output=output,
    )
    try:
        with pytest.raises(ValueError) as raised:
            progress(local.PROGRESS_LABELS[0])
        assert raised.value is expected
        assert "CANARY" not in json.dumps(
            local.safe_failure(raised.value, "LINEAGE_INPUT_VALIDATE")
        )
    finally:
        progress.close()


def test_same_width_valid_schema_progress_edit_rejects_original_byte_change(
    tmp_path, monkeypatch
):
    tmp_path.chmod(0o700)
    now = [100.0]
    monkeypatch.setattr(local.time, "monotonic", lambda: now[0])
    path = tmp_path / "progress.jsonl"
    progress = local.Progress(
        path, started=100.0, check=lambda: None, output=lambda _: None
    )
    try:
        for label in local.PROGRESS_LABELS:
            progress(label)
            now[0] += 1
        original = path.read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        rows[2]["elapsed_ms"] = 2001
        changed = b"".join(b.canonical(row) for row in rows)
        assert len(changed) == len(original)
        assert [row["elapsed_ms"] for row in rows] == sorted(
            row["elapsed_ms"] for row in rows
        )
        assert all(
            set(row) == {"schema_version", "sequence", "boundary", "elapsed_ms"}
            for row in rows
        )
        path.write_bytes(changed)
        with pytest.raises(c.Stage12Error, match="S12A_PROGRESS_CHANGED"):
            progress.snapshot()
    finally:
        progress.close()


def test_running_progress_hash_advances_only_after_successful_fsync(
    tmp_path, monkeypatch
):
    tmp_path.chmod(0o700)
    progress = local.Progress(
        tmp_path / "progress.jsonl",
        started=local.time.monotonic(),
        check=lambda: None,
        output=lambda _: None,
    )
    expected = OSError("INVENTED_FSYNC_FAILURE")

    def fail(_):
        raise expected

    monkeypatch.setattr(local.os, "fsync", fail)
    try:
        with pytest.raises(OSError) as raised:
            progress(local.PROGRESS_LABELS[0])
        assert raised.value is expected
        assert progress.emitted_sha256.digest() == b.sha(b"")
        assert progress.count == progress.bytes == 0
    finally:
        progress.close()


def test_all_five_actual_consumer_calls_have_genuine_before_after_labels(monkeypatch):
    events = []
    accepted = object()

    def consume(*args):
        events.append("CONSUMER_RETURNING")
        return accepted

    class Projection:
        def __init__(self, actual, **kwargs):
            assert actual is accepted
            self.reload = kwargs["reload_accepted"]

    monkeypatch.setattr(lineage.inputs, "consume_inputs", consume)
    p = lineage.LineageProjection.open.__func__(
        Projection,
        stage08_root=None,
        stage09_root=None,
        stage06_root=None,
        scratch=None,
        memory_bytes=1,
        authority=Authority(),
        interpretation={},
        interpretation_sha256="a" * 64,
        progress=events.append,
    )
    for _ in range(4):
        assert p.reload() is accepted
    assert events == [
        event
        for number in range(1, 6)
        for event in (
            f"ACCEPTED_INPUT_PASS_{number}_BEGIN",
            "CONSUMER_RETURNING",
            f"ACCEPTED_INPUT_PASS_{number}_END",
        )
    ]


def test_failing_consumer_keeps_primary_and_never_emits_completion(monkeypatch):
    expected = ValueError("INVENTED_CONSUMER_PRIMARY")
    events = []

    def consume(*_):
        raise expected

    def progress(label):
        events.append(label)
        if label.endswith("END"):
            raise RuntimeError("INVENTED_SECONDARY_CALLBACK")

    monkeypatch.setattr(lineage.inputs, "consume_inputs", consume)
    with pytest.raises(ValueError) as raised:
        lineage.LineageProjection.open(
            stage08_root=None,
            stage09_root=None,
            stage06_root=None,
            scratch=None,
            memory_bytes=1,
            authority=Authority(),
            interpretation={},
            interpretation_sha256="a" * 64,
            progress=progress,
        )
    assert raised.value is expected
    assert events == ["ACCEPTED_INPUT_PASS_1_BEGIN"]


def test_optional_constructor_and_context_callbacks_preserve_rows(
    synthetic_inputs, tmp_path
):
    tmp_path.chmod(0o700)
    value = interpretation()
    common = {
        "memory_bytes": 64 * 2**20,
        "reload_accepted": lambda: synthetic_inputs,
        "authority": Authority(),
        "interpretation": value,
        "interpretation_sha256": b.digest(value),
    }
    events = []
    plain = lineage.LineageProjection.synthetic(
        synthetic_inputs, scratch=tmp_path / "plain", **common
    )
    observed = lineage.LineageProjection.synthetic(
        synthetic_inputs,
        scratch=tmp_path / "observed",
        progress=events.append,
        **common,
    )

    def materialize(projection):
        return [{**row, "channels": list(row["channels"])} for row in projection.rows()]

    try:
        assert plain.progress is None
        assert materialize(plain) == materialize(observed)
        wanted = [
            label for label in local.PROGRESS_LABELS if label.startswith("LINEAGE_")
        ]
        assert events == wanted
    finally:
        plain.close()
        observed.close()


def test_run_entry_anchor_precedes_guard_without_accessing_data(tmp_path, monkeypatch):
    events = []
    expected = RuntimeError("SYNTHETIC_SITE_STOP")
    monkeypatch.setattr(
        local.time, "monotonic", lambda: events.append("ORIGINAL_ENTRY_CLOCK") or 1.0
    )

    def stop(_):
        events.append("SITE_GUARD")
        raise expected

    monkeypatch.setattr(local, "require_goethe_nhr_slurm", stop)
    with pytest.raises(RuntimeError) as raised:
        local.run(successor(tmp_path), repository=tmp_path)
    assert raised.value is expected
    assert events == ["ORIGINAL_ENTRY_CLOCK", "SITE_GUARD"]


def test_authorization_digest_binds_explicit_operating_selection(tmp_path):
    old = configuration(tmp_path)
    new = successor(tmp_path)
    assert local.authorization_record(old) != local.authorization_record(new)
    changed = deepcopy(new)
    changed["operating_policy"]["decision_record_path"] += ".substituted"
    assert local.authorization_record(changed) != local.authorization_record(new)

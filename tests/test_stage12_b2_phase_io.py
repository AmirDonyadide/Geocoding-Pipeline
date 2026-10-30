from types import SimpleNamespace
from pathlib import Path
import pytest
from stage12_b2_synthetic import World, H, KEY, offline
from test_stage12_b2_publication import publish_world
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_phase_io as phases,
    s12_b2_contract as b,
    s12_b2_calibration as cal,
    s12_storage as io,
    s12_response as response,
    s12_retrieval_contract as c,
)


def test_cli_calibration_result_is_durable_and_reopens_with_concrete_readers(tmp_path):
    w = World(tmp_path, count=1)
    specs = []
    for i, intent in enumerate(w.selection["intents"]):
        values = w.inputs(
            size=intent["size"],
            kind=intent["kind"],
            repetition=intent["repetition"],
            subset=intent["subset"],
        )
        w.run("segment_" + str(i), inputs=values)
        root = tmp_path / ("published_" + str(i))
        h, validate, closure = publish_world(
            w, values, tmp_path / ("segment_" + str(i)), root
        )
        specs.append({"path": str(root), "manifest_sha256": h.hex()})
        reader = phases.CampaignReader(
            tmp_path / ("segment_" + str(i)),
            catalog=w.catalog,
            rules=w.rules,
            gate=w.gate,
            closure_hash=closure,
            scratch=tmp_path / ("campaign_reader_" + str(i)),
            control_adapters={},
        )
        q = next(reader.ids())
        p, raw = reader.read(q)
        assert p.candidates and raw
        reader.validate()
        reader.close()
    port = SimpleNamespace(
        population_scope=b.SYNTHETIC,
        test_only=True,
        authority=w.gate.authority,
        records=w.records,
        gate=w.gate,
        response_rules=w.rules,
        control_adapters={},
        open_catalog=lambda: w.catalog,
        secret_guard=lambda raw: response.secret_guard(raw, KEY),
    )
    config = {
        "selection_sha256": w.selection_hash,
        "window_plan_sha256": w.window_hash,
        "calibration_publications": specs,
        "external_sort_memory_bytes": 64 * 1024 * 1024,
        "phase_writer_guard_ms": 5000,
        "phase_output_max_bytes": 4 * 1024 * 1024,
        "phase_output_max_rows": 10000,
    }
    result = cli.execute(
        "evaluate-calibration",
        cli.Session(
            port, config, tmp_path / "evaluation", tmp_path / "selection.sqlite", H
        ),
    )
    root = tmp_path / "evaluation"
    mh = b.sha(io.read(root / "manifest.json")).hex()
    assert (
        result
        == b.parse(io.read(root / "result.json"))
        == phases.reopen_phase(root, mh)
    )
    assert (
        result["eligible_limits"] == [1, 3, 5] and not result["scientific_N_selected"]
    )
    assert sum(1 for _ in phases.journal.read_array(root / "comparisons.json")) > 20
    with pytest.raises(FileExistsError):
        cli.execute(
            "evaluate-calibration",
            cli.Session(port, config, root, tmp_path / "new_selection.sqlite", H),
        )
    path = root / "comparisons.json"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(c.Stage12Error):
        phases.reopen_phase(root, mh)


def test_phase_output_budget_fails_without_committed_marker(tmp_path):
    tmp_path.chmod(0o700)
    writer = phases.PhaseOutput(
        tmp_path / "limited",
        writer_guard_ms=1000,
        max_bytes=10,
        max_rows=1,
        secret_guard=lambda x: None,
    )
    try:
        with pytest.raises(c.Stage12Error):
            writer.append({"invented": "too much"})
        assert not (tmp_path / "limited/_COMMITTED").exists()
    finally:
        writer.abort()

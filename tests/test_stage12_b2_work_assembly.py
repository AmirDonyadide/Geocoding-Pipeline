"""Invented LP-1 inputs only; never live permission or scientific calibration."""

import hashlib
import json

import pytest

from stage12_b2_synthetic import World, H
from test_stage12_b2_local_preparation import lp1_configuration, make_port
from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_runtime as runtime,
    s12_b2_work_assembly as assembly,
    s12_storage as io,
    s12_retrieval_contract as c,
)


def fixture(tmp_path, *, count=4):
    tmp_path.chmod(0o700)
    intent = dict(size=10, repetition=1, kind="FULL_C", count=count)
    raw = b"".join(
        b.canonical(
            dict(
                ordinal=i,
                query_semantic_id=f"{i:064x}",
                result_limit=10,
                repetition=1,
                workload_kind="FULL_C",
            )
        )
        for i in range(1, count + 1)
    )
    source = tmp_path / "intent.jsonl"
    io.write(source, raw)
    inventory = dict(rows=count, sha256=b.sha(raw).hex())
    layout = dict(
        version=assembly.VERSION,
        intent_ordinal=1,
        result_limit=10,
        repetition=1,
        max_output_bytes=100000,
        controls=[
            dict(position=1, recipe_id=1, recipe_sha256=H),
            dict(position=count + 2, recipe_id=1, recipe_sha256=H),
        ],
    )
    return source, tmp_path / "work.jsonl", inventory, intent, layout


def build(args, check=lambda: None):
    return assembly.assemble(*args, check=check)


def test_exact_associations_controls_digests_and_real_reopening(tmp_path):
    args = fixture(tmp_path)
    result = build(args)
    rows = [io.metadata(x + b"\n") for x in args[1].read_bytes().splitlines()]
    assert result["file_sha256"] == b.sha(args[1].read_bytes()).hex()
    assert result["work_manifest_sha256"] == b.digest(rows)
    assert result["file_sha256"] != result["work_manifest_sha256"]
    assert [x["work_id"] for x in rows] == list(range(1, 7))
    assert [x["kind"] for x in rows] == ["SERVICE_CONTROL"] + ["DATA"] * 4 + [
        "SERVICE_CONTROL"
    ]
    assert [x["query_semantic_id"] for x in rows[1:5]] == [
        f"{i:064x}" for i in range(1, 5)
    ]
    view = dict(
        control_recipes=[dict(recipe_id=1, recipe_sha256=H)],
        blocks=[dict(last_work_id=6)],
        result_limit=10,
        repetition=1,
        budgets=dict(data_observations=4, required_control_observations=2),
        work_manifest_sha256=result["work_manifest_sha256"],
    )
    reader = runtime.WorkFile(args[1], result["file_sha256"], view)
    reader.verify()
    assert reader.row(3) == rows[2]
    assert (
        result["service_transfer_authority"]
        == result["scientific_publication"]
        == "NOT_GRANTED"
    )
    with pytest.raises(FileExistsError):
        build(args)


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x.update(result_limit=5),
        lambda x: x.update(repetition=True),
        lambda x: x.update(unexpected=1),
        lambda x: x.pop("controls"),
        lambda x: x["controls"][1].update(position=1),
        lambda x: x["controls"][1].update(position=100),
        lambda x: x["controls"][1].update(recipe_sha256="b" * 64),
    ],
)
def test_explicit_layout_closed_and_bound_before_output(tmp_path, change):
    args = fixture(tmp_path)
    change(args[-1])
    with pytest.raises(c.Stage12Error):
        build(args)
    assert not args[1].exists()


@pytest.mark.parametrize(
    "mutation", ["duplicate", "changed", "truncated", "mode", "symlink"]
)
def test_input_change_or_invalid_order_never_produces_receipt(tmp_path, mutation):
    args = fixture(tmp_path)
    raw = args[0].read_bytes()
    if mutation == "duplicate":
        row = io.metadata(raw.splitlines(keepends=True)[1])
        row["query_semantic_id"] = f"{1:064x}"
        raw = (
            raw.splitlines(keepends=True)[0]
            + b.canonical(row)
            + b"".join(raw.splitlines(keepends=True)[2:])
        )
        args[2]["sha256"] = b.sha(raw).hex()  # Exact invalid source remains invalid.
        args[0].write_bytes(raw)
    elif mutation == "changed":
        args[0].write_bytes(raw.replace(b'"FULL_C"', b'"TAIL"'))
    elif mutation == "truncated":
        args[0].write_bytes(raw[:-1])
    elif mutation == "mode":
        args[0].chmod(0o644)
    else:
        moved = tmp_path / "moved"
        args[0].rename(moved)
        args[0].symlink_to(moved)
    with pytest.raises((c.Stage12Error, OSError)):
        build(args)


def test_prewrite_boundary_and_partial_charges_not_refunded(tmp_path):
    args = fixture(tmp_path)
    args[-1]["max_output_bytes"] = len(
        b.canonical(
            dict(
                work_id=1,
                block_id=1,
                kind="SERVICE_CONTROL",
                query_semantic_id=None,
                recipe_id=1,
                repetition=None,
                result_limit=None,
                retry_spacing_key=H,
            )
        )
    )
    charged = []
    with io.charged_writes(lambda p, n: charged.append(n)):
        with pytest.raises(c.Stage12Error, match="LP1_DISPATCH_BYTE_LIMIT"):
            build(args)
    assert sum(charged) == args[-1]["max_output_bytes"] == args[1].stat().st_size
    assert args[0].exists()


def test_deadline_partial_write_and_post_reopen_mutation(tmp_path):
    args = fixture(tmp_path)
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 8:
            raise c.Stage12Error("SYNTHETIC_DEADLINE")

    with pytest.raises(c.Stage12Error, match="SYNTHETIC_DEADLINE"):
        build(args, check)
    assert args[1].exists()
    assert args[0].exists()


def test_output_fsync_failure_preserves_partial(tmp_path, monkeypatch):
    args = fixture(tmp_path)

    def fail(_fd):
        raise OSError(28, "synthetic disk full")

    monkeypatch.setattr(assembly.os, "fsync", fail)
    with pytest.raises(OSError):
        build(args)
    assert args[1].stat().st_size > 0


def test_fresh_reopen_rejects_changed_output_and_layout(tmp_path):
    args = fixture(tmp_path)
    receipt = build(args)
    args[-1]["controls"][0]["recipe_sha256"] = "b" * 64
    with pytest.raises(c.Stage12Error):
        assembly.reopen(args[1], args[2], args[3], args[4], receipt, check=lambda: None)
    args[-1]["controls"][0]["recipe_sha256"] = H
    raw = args[1].read_bytes()
    args[1].write_bytes(raw.replace(b'"result_limit":10', b'"result_limit":20'))
    with pytest.raises(c.Stage12Error):
        assembly.reopen(args[1], args[2], args[3], args[4], receipt, check=lambda: None)


def test_linear_streaming_work_and_explicit_zero_repetition(tmp_path):
    args = fixture(tmp_path, count=10000)
    raw = args[0].read_bytes().replace(b'"repetition":1', b'"repetition":0')
    args[0].write_bytes(raw)
    args[2]["sha256"] = b.sha(raw).hex()
    args[3]["repetition"] = args[4]["repetition"] = 0
    args[4]["max_output_bytes"] = 8 * 2**20
    calls = 0

    def check():
        nonlocal calls
        calls += 1

    result = build(args, check)
    assert result["rows"] == 10002
    assert result["data_rows"] == 10000
    assert (
        calls < 60000
    )  # Fixed linear source/output passes, no per-work catalog replay.


def test_local_real_entrypoint_no_service_and_complete_work_associations(tmp_path):
    w = World(tmp_path, count=4)

    def configure(config):
        core = w.records.get(config["calibration_plan_sha256"], "calibration_plan")
        intents = json.loads(w.records.raw(core["workload_inventory_sha256"]))
        config["local_dispatch_layouts"] = [
            dict(
                version=assembly.VERSION,
                intent_ordinal=i,
                result_limit=x["result_limit"],
                repetition=x["repetition"],
                max_output_bytes=100000,
                controls=[],
            )
            for i, x in enumerate(intents, 1)
        ]

    config, out, scratch, _ = lp1_configuration(
        w, "build-workload", configure=configure
    )
    p = make_port(w, config)
    result = cli.execute("build-workload", cli.Session(p, config, out, scratch, H))
    assert len(result["dispatch_work_files"]) == len(result["inventories"]) == 8
    assert sum(x["data_rows"] for x in result["dispatch_work_files"]) == 32
    assert all(x["control_rows"] == 0 for x in result["dispatch_work_files"])
    for item in result["dispatch_work_files"]:
        assert (
            hashlib.sha256((out / item["name"]).read_bytes()).hexdigest()
            == item["file_sha256"]
        )
    assert p._closed and p.offline_guard.closed
    assert result["ready_for_service"] is False
    assert all(
        config["runtime"][k] is None
        for k in __import__(
            "safe_geocoding_pipeline.preprocessing.stages.s12_b2_local_preparation",
            fromlist=["SERVICE_FIELDS"],
        ).SERVICE_FIELDS
    )

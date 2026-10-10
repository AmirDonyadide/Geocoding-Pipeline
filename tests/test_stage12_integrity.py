from __future__ import annotations

import copy

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_integrity as integrity
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from stage12_synthetic import HASH, NOW, extract
from test_stage12_end_to_end import dataset_rows
from test_stage12_recovery import case, run


@pytest.fixture
def complete(tmp_path):
    workspace, binding, target = case(tmp_path)
    result, _ = run(workspace, binding, target)
    return binding, result.checkpoint


def test_verified_history_and_relation_foreign_keys(complete):
    binding, unit = complete
    item = integrity.HistoryUnit(
        unit, c.sha(io.read(unit / "receipt.json")), HASH, True
    )
    history, selected = integrity.history([item], binding, reopen=extract)
    assert selected == unit and len(history) == 1
    rows, _, _ = dataset_rows([(unit, binding)])
    totals = integrity.relations(
        lambda name: iter(rows[name]),
        frozenset({bytes.fromhex(binding["query_semantic_id"])}),
        campaign_id=bytes.fromhex(binding["campaign_id"]),
    )
    assert totals["request_candidate_count"] == 2


@pytest.mark.parametrize(
    "defect",
    [
        "rank_gap",
        "missing_candidate",
        "wrong_raw",
        "wrong_fk",
        "duplicate_execution",
        "wrong_attempt",
        "missing_workload",
    ],
)
def test_corrupt_complete_dataset_cannot_validate(complete, defect):
    binding, unit = complete
    rows, _, _ = dataset_rows([(unit, binding)])
    rows = copy.deepcopy(rows)
    expected = frozenset({bytes.fromhex(binding["query_semantic_id"])})
    if defect == "rank_gap":
        rows["request_candidate"][0]["rank"] = 2
    elif defect == "missing_candidate":
        rows["request_candidate"].pop()
    elif defect == "wrong_raw":
        rows["request_candidate"][0]["response_sha256"] = HASH
    elif defect == "wrong_fk":
        rows["request_candidate"][0]["request_execution_id"] = HASH
    elif defect == "duplicate_execution":
        rows["request_execution"].append(rows["request_execution"][0])
    elif defect == "wrong_attempt":
        rows["request_execution"][0]["terminal_attempt_id"] = HASH
    else:
        expected = frozenset({HASH})
    with pytest.raises(c.Stage12Error):
        integrity.relations(
            lambda name: iter(rows[name]),
            expected,
            campaign_id=bytes.fromhex(binding["campaign_id"]),
        )


def test_unknown_delivery_consumes_budget_never_adopted(tmp_path):
    workspace, binding, target = case(tmp_path)
    old = workspace / "crashed"
    io.begin(old, binding, runtime.begin_row(binding, 1, HASH, NOW))
    result, state = run(workspace, binding, target, previous=1)
    units = [
        integrity.HistoryUnit(old, c.sha(io.read(old / "begin.parquet")), HASH, False),
        integrity.HistoryUnit(
            result.checkpoint,
            c.sha(io.read(result.checkpoint / "receipt.json")),
            HASH,
            True,
        ),
    ]
    rows, selected = integrity.history(units, binding, reopen=extract)
    assert len(rows) == 2 and rows[0]["outcome"] == "UNKNOWN_DELIVERY"
    assert selected == result.checkpoint and state["dispatches"] == 1
    with pytest.raises(c.Stage12Error):
        integrity.history(units[1:], binding, reopen=extract)


def test_dispatch_exception_releases_reservation_preserves_primary(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_operations as ops

    workspace, binding, target = case(tmp_path)
    gate = ops.Admission(ops.Operations())
    with pytest.raises(StopIteration):
        run(workspace, binding, target, replies=iter(()), admission=gate)
    assert gate.reserved_bytes == 0 and gate.active == 0
    assert gate.open_reason == "TERMINAL_FAILURE"
    assert len(list(workspace.glob("*/begin.parquet"))) == 1
    assert not list(workspace.glob("*/_SEALED"))


def test_streaming_assembly_reopens_four_relations_and_raw_frames(complete, tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_assembly as assembly
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    binding, unit = complete
    root = tmp_path / "artifact"
    io.reserve(root)
    item = integrity.HistoryUnit(
        unit, c.sha(io.read(unit / "receipt.json")), HASH, True
    )
    result = assembly.assemble(
        root,
        [assembly.ExecutionUnits(binding, (item,))],
        c.policy(3),
        expected_semantic_ids=frozenset({bytes.fromhex(binding["query_semantic_id"])}),
        reopen=extract,
    )
    assert result["request_candidate_count"] == 2
    execution = next(assembly.read_relation(root, "request_execution"))
    pack = io.read(root / execution["raw_pack_key"])
    start, size = execution["raw_frame_offset"], execution["raw_frame_length"]
    raw = response.decompress(
        pack[start : start + size],
        length=execution["response_bytes"],
        expected_hash=execution["response_sha256"],
    )
    capture = io.metadata(io.read(unit / "capture.json"))["capture"]
    assert list(extract(raw, capture).candidates) == list(
        assembly.read_relation(root, "request_candidate")
    )
    bindings = {key: HASH for key in c.DATASET_BINDINGS}
    bindings["response_projection_id"] = bytes.fromhex(result["response_projection_id"])
    relations = [
        (
            name,
            bytes.fromhex(result[name + "_scientific_sha256"]),
            result[name + "_count"],
        )
        for name in ("retrieval_policy", "request_execution", "request_candidate")
    ]
    fingerprint = c.dataset_fingerprint(
        bindings, relations, bytes.fromhex(result["raw_response_set_sha256"]), HASH
    )
    assert len(fingerprint) == 32
    assert (
        c.dataset_fingerprint(
            bindings, relations, bytes.fromhex(result["raw_response_set_sha256"]), HASH
        )
        == fingerprint
    )


def test_assembled_dataset_publication_and_full_reopen(complete, tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_assembly as assembly
    from safe_geocoding_pipeline.preprocessing.stages import s12_publication as pub

    binding, unit = complete
    reference = integrity.HistoryUnit(
        unit, c.sha(io.read(unit / "receipt.json")), HASH, True
    )
    semantic_ids = frozenset({bytes.fromhex(binding["query_semantic_id"])})

    def build(root):
        result = assembly.assemble(
            root,
            [assembly.ExecutionUnits(binding, (reference,))],
            c.policy(3),
            expected_semantic_ids=semantic_ids,
            reopen=extract,
        )
        inventory = io.file_inventory(
            root,
            tuple(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()),
        )
        bindings = {key: HASH.hex() for key in pub.BINDINGS if key != "manifest_sha256"}
        bindings.update(
            executable_sha=binding["executable_sha"],
            owner_freeze_sha256=None,
            inventory_sha256=c.sha(c.canonical(inventory)).hex(),
            response_projection_id=result["response_projection_id"],
        )
        return dict(
            kind=pub.CALIBRATION,
            publication_bindings=bindings,
            planned=1,
            completed=1,
            failures=0,
            unprocessed=0,
            deployment_intervals_closed=True,
            inventory=inventory,
        )

    def validate(root, manifest):
        assembly.reopen_artifact(
            root,
            expected_semantic_ids=semantic_ids,
            campaign_id=bytes.fromhex(binding["campaign_id"]),
            validation_sha256=bytes.fromhex(
                binding["response_validation_contract_sha256"]
            ),
            extraction_sha256=bytes.fromhex(
                binding["response_extraction_contract_sha256"]
            ),
            candidate_schema_sha256=bytes.fromhex(binding["candidate_schema_sha256"]),
            reopen=extract,
        )

    root = tmp_path / "published"
    digest = pub.publish(root, build=build, validate_science=validate)
    assert (root / "_COMMITTED").exists()
    assert (
        pub.validate_terminal(root, digest, committed=True, validate_science=validate)[
            "completed"
        ]
        == 1
    )

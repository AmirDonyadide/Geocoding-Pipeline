"""Network-free full four-relation publication with clean/resume/order/replay equality."""

from __future__ import annotations

import json
from pathlib import Path

from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing.stages import s12_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from stage12_synthetic import HASH, NOW, core, extract, setup
from test_stage12_recovery import run


def request_binding(base, ordinal):
    value = core(text=f"Invented Unicode Café {ordinal}")
    semantic = s11.semantic_id(s11.core_bytes(value))
    binding = {**base, "query_semantic_id": semantic.hex()}
    scientific = {
        k: c.IDENTITY if k == "identity_version" else bytes.fromhex(binding[k])
        for k in c.EXECUTION_FIELDS
    }
    binding["request_execution_id"] = c.execution_id(scientific).hex()
    target, _ = c.materialize(value, semantic, c.policy(3), target_limit=10000)
    return binding, target


def dataset_rows(units):
    executions, attempts, candidates, captures = [], [], [], []
    for unit, binding in units:
        receipt = c.sha(io.read(unit / "receipt.json"))
        attempt, features, raw = io.adopt(
            unit,
            binding,
            expected_receipt_sha256=receipt,
            verified_interval_closure_sha256=HASH,
            reopen=extract,
        )
        assert raw is not None
        meta = io.metadata(io.read(unit / "capture.json"))["capture"]
        capture = {**meta}
        for k in ("request_execution_id", "request_target_sha256", "response_sha256"):
            capture[k] = bytes.fromhex(capture[k])
        captures.append(capture)
        execution = {k: None for k in c.columns("request_execution")}
        for k in c.EXECUTION_FIELDS[1:]:
            execution[k] = bytes.fromhex(binding[k])
        execution.update(
            request_execution_id=attempt["request_execution_id"],
            request_target_sha256=capture["request_target_sha256"],
            terminal_state=attempt["outcome"],
            reason_code="OK",
            terminal_attempt_id=attempt["attempt_id"],
            candidate_count=len(features),
            response_sha256=c.sha(raw),
            response_bytes=len(raw),
            raw_pack_key="raw.zst",
            raw_frame_offset=0,
            raw_frame_length=(unit / "raw.zst").stat().st_size,
            response_completed_utc=NOW,
        )
        executions.append(execution)
        attempts.append(attempt)
        candidates.extend(features)
    rows = {
        "retrieval_policy": [c.policy(3)],
        "request_execution": executions,
        "request_attempt": attempts,
        "request_candidate": candidates,
    }
    for relation in c.RELATIONS:
        rows[relation].sort(key=lambda row: tuple(row[k] for k in c.KEYS[relation]))
    captures.sort(key=lambda row: row["request_execution_id"])
    raw_set, context = c.capture_hashes(len(captures), captures)
    projection = c.projection_id(
        raw_set,
        context,
        HASH,
        HASH,
        c.sha(c.canonical(c.descriptor("request_candidate"))),
    )
    science = [
        (name, c.relation_hash(name, len(rows[name]), rows[name], scientific=True))
        for name in c.RELATIONS
        if name != "request_attempt"
    ]
    return rows, projection, c.sha(c.framed([projection, science]))


def test_clean_resumed_partition_order_publication_reopen_replay(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    tmp_path.chmod(0o700)
    base, _ = setup(tmp_path)
    sets = []
    for name, order in (("clean", range(6)), ("different_order", reversed(range(6)))):
        workspace = tmp_path / name
        io.reserve(workspace)
        units = []
        for ordinal in order:
            binding, target = request_binding(base, ordinal)
            result, _ = run(workspace, binding, target)
            units.append((result.checkpoint, binding))
        sets.append(units)
    # A second segment adopts the first three sealed responses and sends only
    # the remaining requests. No adopted unit is modified or hardlinked.
    resume_workspace = tmp_path / "resumed"
    io.reserve(resume_workspace)
    resumed = list(sets[0][:3])
    for ordinal in (5, 3, 4):
        binding, target = request_binding(base, ordinal)
        result, _ = run(resume_workspace, binding, target)
        resumed.append((result.checkpoint, binding))
    sets.append(resumed)
    results = [dataset_rows(units) for units in sets]
    assert results[0][1:] == results[1][1:] == results[2][1:]
    rows, projection, scientific = results[0]

    def build(root: Path):
        names = []
        for name in c.RELATIONS:
            if name == "retrieval_policy":
                # The closed empty option struct has no Parquet child field.
                # Canonical singleton metadata retains the exact logical type.
                serialized = {
                    **rows[name][0],
                    "retrieval_policy_id": rows[name][0]["retrieval_policy_id"].hex(),
                }
                io.write(root / "retrieval_policy.json", c.canonical(serialized))
                names.append("retrieval_policy.json")
            else:
                filename = name + ".parquet"
                io.write(root / filename, io.parquet_bytes(name, rows[name]))
                names.append(filename)
        inventory = io.file_inventory(root, tuple(names))
        bindings = {k: HASH.hex() for k in pub.BINDINGS if k != "manifest_sha256"}
        bindings.update(
            executable_sha="1" * 40,
            owner_freeze_sha256=None,
            inventory_sha256=c.sha(c.canonical(inventory)).hex(),
            scientific_result_sha256=scientific.hex(),
            response_projection_id=projection.hex(),
            candidate_relation_sha256=c.relation_hash(
                "request_candidate",
                len(rows["request_candidate"]),
                rows["request_candidate"],
            ).hex(),
        )
        return {
            "kind": pub.CALIBRATION,
            "publication_bindings": bindings,
            "inventory": inventory,
            "planned": 6,
            "completed": 6,
            "unprocessed": 0,
            "failures": 0,
            "deployment_intervals_closed": True,
        }

    def validate(root, manifest):
        restored = {}
        for name in c.RELATIONS:
            if name == "retrieval_policy":
                value = json.loads(io.read(root / "retrieval_policy.json"))
                value["retrieval_policy_id"] = bytes.fromhex(
                    value["retrieval_policy_id"]
                )
                c.validate_policy(value)
                restored[name] = [value]
            else:
                restored[name] = io.read_rows(io.read(root / (name + ".parquet")), name)
            assert [c.row_bytes(name, row) for row in restored[name]] == [
                c.row_bytes(name, row) for row in rows[name]
            ]
        assert len(restored["request_execution"]) == 6
        assert len(restored["request_candidate"]) == 12
        assert (
            manifest["publication_bindings"]["response_projection_id"]
            == projection.hex()
        )
        assert dataset_rows(sets[0])[2] == scientific  # Offline original-byte replay.

    published = tmp_path / "synthetic_publication"
    manifest_hash = pub.publish(published, build=build, validate_science=validate)
    pub.validate_terminal(
        published, manifest_hash, committed=True, validate_science=validate
    )

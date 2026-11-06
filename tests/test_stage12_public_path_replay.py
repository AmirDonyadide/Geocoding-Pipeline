"""Invented replay preparation; no provider, network or protected inputs."""

import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operations as operations,
    s12_public_response as validation,
    s12_public_runtime as runtime,
    s12_response as response,
    s12_retrieval_contract as contract,
)
from stage12_synthetic import body
from test_stage12_public_matrix import configuration
from test_stage12_public_operations_v2 import offline  # noqa: F401


def module(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def preparation(tmp_path):
    cfg = configuration()
    cfg["public_validation_sha256"] = operations.digest(
        validation.descriptor(validation.CORPUS_VERSION)
    )
    template = tmp_path / "template.json"
    template.write_bytes(contract.canonical(cfg))
    payload = body([])
    frame = response.compress(payload)
    prefix = tmp_path / "replayed_public"
    for work in cfg["campaigns"][0]["work"]:
        name = f"call_{work['work_id']:04d}_attempt_1"
        root = prefix / "size01_full_text" / "attempts" / name
        root.mkdir(parents=True)
        (root / (name + ".zst")).write_bytes(frame)
        (root / (name + "_capture.json")).write_bytes(
            contract.canonical(
                {
                    "capture": {
                        "application_payload_bytes": len(payload),
                        "response_sha256": contract.sha(payload).hex(),
                    }
                }
            )
        )
    old = tmp_path / "old.json"
    deep = next(x for x in cfg["campaigns"] if x["label"] == "size40_deep")
    old.write_bytes(
        contract.canonical(
            {
                "responses": [
                    {
                        "fixture_id": w["fixture_id"],
                        "size": 40,
                        "raw_utf8": payload.decode(),
                    }
                    for w in deep["work"]
                    if w["repetition"] == 0
                ]
            }
        )
    )
    review = tmp_path / "review.md"
    review.write_text("TEST ONLY invented review fixture, never execution authority.\n")
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            {"source_files": [{"path": "scripts/stage12_public_path_replay.py"}]}
        )
    )
    output = tmp_path / "selected.json"
    argv = [
        "prepare",
        "--template",
        str(template),
        "--template-sha256",
        contract.sha(template.read_bytes()).hex(),
        "--public-prefix",
        str(prefix),
        "--prior-replay-input",
        str(old),
        "--prior-input-sha256",
        contract.sha(old.read_bytes()).hex(),
        "--source-sha",
        "a" * 40,
        "--review-report",
        str(review),
        "--source-inventory",
        str(inventory),
        "--output",
        str(output),
    ]
    return argv, output, prefix


def test_canonical_preparation_associations_and_test_authority(
    preparation, monkeypatch
):
    argv, output, _ = preparation
    monkeypatch.setattr(sys, "argv", argv)
    producer = module("stage12_prepare_public_path_replay")
    producer.main()
    raw = output.read_bytes()
    value = json.loads(raw)
    assert raw == contract.canonical(value)
    runtime.validate_config(value["configuration"])
    assert len(value["response_cases"]) == 96
    assert len({(x["label"], x["work_id"]) for x in value["response_cases"]}) == 96
    assert all(
        contract.sha(x["raw_utf8"].encode()).hex() == x["payload_sha256"]
        for x in value["response_cases"]
    )
    assert all(
        json.loads(x)["claim"]
        == "TEST_ONLY_NOT_AN_OPERATOR_OR_INSTITUTIONAL_ATTESTATION"
        for x in value["test_only_authority_records"].values()
    )
    assert value["limits"] == module("stage12_public_path_replay").LIMITS
    assert value["limits"]["attempts"] == 107
    assert value["expected_attempts"] == 64 + 32 + 8 + 2 == 106
    assert len(value["scenarios"]) == 4 and all(
        x["observer"] for x in value["scenarios"]
    )
    assert value["scenarios"][0]["name"] == "enabled_first64"
    assert set(value["diagnostic_source_files"]) == set(producer.DIAGNOSTIC_PATHS)
    assert output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        producer.main()


@pytest.mark.parametrize("mutation", ["template_hash", "source_sha", "raw_hash"])
def test_preparation_rejects_changed_sources_before_output(
    preparation, monkeypatch, mutation
):
    argv, output, prefix = preparation
    if mutation == "template_hash":
        argv[argv.index("--template-sha256") + 1] = "0" * 64
    elif mutation == "source_sha":
        argv[argv.index("--source-sha") + 1] = "z" * 40
    else:
        (
            prefix
            / "size01_full_text/attempts/call_0001_attempt_1/call_0001_attempt_1.zst"
        ).write_bytes(response.compress(b"changed"))
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises((AssertionError, contract.Stage12Error)):
        module("stage12_prepare_public_path_replay").main()
    assert not output.exists()


def test_only_parent_directory_fsync_handle_is_admissible(tmp_path):
    replay = module("stage12_public_path_replay")
    output = tmp_path / "new_immutable_output"
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    assert replay.parent_fsync_open(tmp_path, flags, output)
    fd = os.open(tmp_path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    assert not replay.parent_fsync_open(tmp_path / "unrelated_input", flags, output)
    assert not replay.parent_fsync_open(tmp_path.parent, flags, output)
    assert not replay.parent_fsync_open(tmp_path, os.O_RDONLY, output)
    assert not replay.parent_fsync_open(tmp_path, flags & ~os.O_NOFOLLOW, output)
    assert not replay.parent_fsync_open(tmp_path, flags | os.O_RDWR, output)
    for extra in (os.O_CREAT, os.O_TRUNC, os.O_APPEND):
        assert not replay.parent_fsync_open(tmp_path, flags | extra, output)

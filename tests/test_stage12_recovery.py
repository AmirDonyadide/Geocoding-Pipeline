from __future__ import annotations

import copy
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_campaign as campaign
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as ops
from safe_geocoding_pipeline.preprocessing.stages import s12_publication as publication
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
from stage12_synthetic import HASH, NOW, body, extract, setup


def run(root, binding, target, *, replies=None, previous=0, admission=None):
    operations = ops.Operations()
    gate = admission or ops.Admission(operations)
    state = {"clock": 1000000, "dispatches": 0}
    responses = iter(
        replies
        or [
            transport.Capture(
                "VALIDATION_REQUIRED",
                "OK",
                200,
                "application/json",
                "identity",
                None,
                body(),
                len(body()),
                10,
            )
        ]
    )

    def dispatch(_target):
        state["dispatches"] += 1
        return next(responses)

    def wait(ms):
        state["clock"] += ms

    result = runtime.execute_one(
        root,
        binding,
        target,
        size=3,
        operations=operations,
        admission=gate,
        dispatch=dispatch,
        verify_identity=lambda: HASH,
        extract=extract,
        clock_ms=lambda: state["clock"],
        wait_ms=wait,
        now_utc=lambda: NOW,
        previous_attempts=previous,
    )
    return result, state


def case(tmp_path):
    tmp_path.chmod(0o700)
    binding, target = setup(tmp_path)
    workspace = tmp_path / "workspace"
    io.reserve(workspace)
    return workspace, binding, target


def test_end_to_end_capture_checkpoint_resume_replay(tmp_path, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *_a, **_kw: pytest.fail("synthetic integration used network"),
    )
    workspace, binding, target = case(tmp_path)
    result, state = run(workspace, binding, target)
    assert result.outcome == "SUCCESS_WITH_CANDIDATES" and result.candidates == 2
    assert state["dispatches"] == 1
    receipt = c.sha(io.read(result.checkpoint / "receipt.json"))
    attempt, candidates, raw = io.adopt(
        result.checkpoint,
        binding,
        expected_receipt_sha256=receipt,
        verified_interval_closure_sha256=HASH,
        reopen=extract,
    )
    replay = extract(
        raw, io.metadata(io.read(result.checkpoint / "capture.json"))["capture"]
    )
    assert [c.row_bytes("request_candidate", r) for r in candidates] == [
        c.row_bytes("request_candidate", r) for r in replay.candidates
    ]
    assert attempt["attempt_number"] == 1
    assert state["dispatches"] == 1


@pytest.mark.parametrize(
    "key",
    [
        "executable_sha",
        "runtime_inventory_sha256",
        "operations_policy_sha256",
        "pelias_deployment_fingerprint",
        "index_data_identity",
        "response_extraction_contract_sha256",
        "authorization_sha256",
        "campaign_id",
    ],
)
def test_changed_bindings_prevent_adoption(tmp_path, key):
    workspace, binding, target = case(tmp_path)
    result, _ = run(workspace, binding, target)
    changed = dict(binding)
    changed[key] = "a" * len(changed[key])
    with pytest.raises(c.Stage12Error):
        io.adopt(
            result.checkpoint,
            changed,
            expected_receipt_sha256=c.sha(io.read(result.checkpoint / "receipt.json")),
            verified_interval_closure_sha256=HASH,
            reopen=extract,
        )


@pytest.mark.parametrize("phase", ["raw_written", "before_seal"])
def test_interrupted_write_never_adopted(tmp_path, monkeypatch, phase):
    workspace, binding, target = case(tmp_path)
    real_finish = io.finish

    def fault(name):
        if name == phase:
            raise OSError("invented power failure")

    def finish(*args, **kwargs):
        return real_finish(*args, **kwargs, fault=fault)

    monkeypatch.setattr(io, "finish", finish)
    with pytest.raises(OSError):
        run(workspace, binding, target)
    units = list(workspace.iterdir())
    assert len(units) == 1 and not (units[0] / io.CHECKPOINT_SEAL).exists()
    with pytest.raises(c.Stage12Error):
        io.validate(units[0], binding, reopen=extract)
    assert (units[0] / "begin.parquet").exists()


def test_malformed_response_raw_retained_no_rank_compression(tmp_path):
    workspace, binding, target = case(tmp_path)
    raw = body().replace(b'"Point"', b'"LineString"', 1)
    result, state = run(
        workspace,
        binding,
        target,
        replies=[
            transport.Capture(
                "VALIDATION_REQUIRED",
                "OK",
                200,
                "application/json",
                "identity",
                None,
                raw,
                len(raw),
                10,
            )
        ],
    )
    assert (
        result.outcome == "CONTRACT_FAILURE"
        and result.candidates is None
        and state["dispatches"] == 1
    )
    unit = next(workspace.iterdir())
    attempt, rows, preserved = io.validate(
        unit, binding, reopen=extract, require_success=False
    )
    assert preserved == raw and rows == [] and attempt["outcome"] == "CONTRACT_FAILURE"
    with pytest.raises(c.Stage12Error):
        io.validate(unit, binding, reopen=extract)


def test_timeout_then_success_and_bounded_exhaustion(tmp_path):
    workspace, binding, target = case(tmp_path)
    timeout = transport.Capture(
        "TECHNICAL_FAILURE_RETRYABLE",
        "TIMEOUT",
        None,
        "ABSENT",
        "absent",
        None,
        None,
        0,
        60000,
    )
    good = transport.Capture(
        "VALIDATION_REQUIRED",
        "OK",
        200,
        "application/json",
        "identity",
        None,
        body([]),
        len(body([])),
        10,
    )
    result, state = run(workspace, binding, target, replies=[timeout, good])
    assert (
        result.outcome == "SUCCESS_ZERO_CANDIDATES"
        and result.attempts == 2
        and state["dispatches"] == 2
    )
    other = tmp_path / "exhaustion"
    io.reserve(other)
    result, state = run(other, binding, target, replies=[timeout], previous=4)
    assert (
        result.outcome == "TECHNICAL_FAILURE_FINAL"
        and result.reason == "RETRY_BUDGET_EXHAUSTED"
        and result.candidates is None
        and state["dispatches"] == 1
    )


@pytest.mark.parametrize(
    "status,reason", [(401, "AUTHENTICATION_FAILED"), (403, "AUTHORIZATION_FAILED")]
)
def test_auth_failure_no_retry(tmp_path, status, reason):
    workspace, binding, target = case(tmp_path)
    result, state = run(
        workspace,
        binding,
        target,
        replies=[
            transport.Capture(
                "TECHNICAL_FAILURE_FINAL",
                reason,
                status,
                "OTHER",
                "absent",
                None,
                None,
                0,
                10,
            )
        ],
    )
    assert result.outcome == "TECHNICAL_FAILURE_FINAL" and state["dispatches"] == 1


def test_primary_exception_not_masked():
    def primary():
        raise RuntimeError("primary")

    def receipt():
        raise OSError("receipt")

    with pytest.raises(RuntimeError, match="primary"):
        io.record_failure_preserving_primary(primary, receipt)


def test_segment_requires_closed_predecessor(tmp_path):
    tmp_path.chmod(0o700)
    setup(tmp_path)
    root = tmp_path / "campaign"
    start = io.metadata(io.read(root / "start.json"))
    first = campaign.open_segment(
        root,
        start,
        ordinal=1,
        job_id="1",
        authorization=HASH,
        predecessor_sha256=None,
        preverification_sha256=HASH,
    )
    with pytest.raises(c.Stage12Error):
        campaign.open_segment(
            root,
            start,
            ordinal=2,
            job_id="2",
            authorization=HASH,
            predecessor_sha256=HASH,
            preverification_sha256=HASH,
        )
    closure = campaign.close_segment(
        first,
        postverification_sha256=HASH,
        attempt_inventory_sha256=HASH,
        planned=2,
        completed=1,
        failed=0,
        unprocessed=1,
    )
    second = campaign.open_segment(
        root,
        start,
        ordinal=2,
        job_id="2",
        authorization=HASH,
        predecessor_sha256=closure,
        preverification_sha256=HASH,
    )
    assert second.exists() and campaign.reopen(root, start) == c.sha(c.canonical(start))


def build_publication(root: Path, *, incomplete=False):
    io.write(root / "synthetic_evidence.json", c.canonical({"invented": True}))
    inventory = io.file_inventory(root, ("synthetic_evidence.json",))
    binding = {k: HASH.hex() for k in publication.BINDINGS if k != "manifest_sha256"}
    binding.update(
        executable_sha="1" * 40,
        owner_freeze_sha256=None,
        inventory_sha256=c.sha(c.canonical(inventory)).hex(),
    )
    return {
        "kind": publication.CALIBRATION,
        "publication_bindings": binding,
        "inventory": inventory,
        "planned": 1,
        "completed": 0 if incomplete else 1,
        "failures": 0,
        "unprocessed": 1 if incomplete else 0,
        "deployment_intervals_closed": True,
    }


def validate_science(root, _manifest):
    assert io.metadata(io.read(root / "synthetic_evidence.json")) == {"invented": True}


def test_publication_full_reopen_and_no_overwrite(tmp_path):
    tmp_path.chmod(0o700)
    destination = tmp_path / "publication"
    digest = publication.publish(
        destination, build=build_publication, validate_science=validate_science
    )
    publication.validate_terminal(
        destination, digest, committed=True, validate_science=validate_science
    )
    with pytest.raises(FileExistsError):
        publication.publish(
            destination, build=build_publication, validate_science=validate_science
        )


def test_incomplete_publication_cannot_seal(tmp_path):
    tmp_path.chmod(0o700)
    destination = tmp_path / "incomplete"
    with pytest.raises(c.Stage12Error, match="INCOMPLETE"):
        publication.publish(
            destination,
            build=lambda root: build_publication(root, incomplete=True),
            validate_science=validate_science,
        )
    assert not (destination / "_COMMITTED").exists()


def test_uncertain_seal_requires_separate_authorization(tmp_path):
    tmp_path.chmod(0o700)
    destination = tmp_path / "uncertain"

    def fault(phase):
        if phase == "after_seal":
            raise OSError("invented fsync uncertainty")

    with pytest.raises(c.Stage12Error, match="AUTHORIZED_RECONCILIATION"):
        publication.publish(
            destination,
            build=build_publication,
            validate_science=validate_science,
            fault=fault,
        )
    assert (destination / "_COMMITTED").exists()


def test_forged_final_publication_or_missing_owner_freeze_rejected():
    binding = {k: HASH.hex() for k in publication.BINDINGS}
    binding["executable_sha"] = "1" * 40
    binding["owner_freeze_sha256"] = None
    with pytest.raises(c.Stage12Error):
        publication.registration(publication.FINAL, "invented", binding)
    with pytest.raises(c.Stage12Error):
        publication.registration("other namespace", "invented", copy.deepcopy(binding))

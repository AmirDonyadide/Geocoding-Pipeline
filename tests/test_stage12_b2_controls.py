import pytest
from stage12_b2_synthetic import World, H, KEY, offline
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_operational_audit as transport_audit,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


class Control:
    def target(self, recipe):
        return b"/SYNTHETIC_ONLY_control"

    def validate(self, recipe, raw):
        b.require(raw == b'{"synthetic_health":"ok"}', "B2_TEST_CONTROL_INVALID")
        return b.canonical({"scope": b.SYNTHETIC, "observed_sha256": b.sha(raw).hex()})


@pytest.mark.parametrize(
    "raw,outcome",
    [
        (b'{"synthetic_health":"ok"}', "CONTROL_SUCCESS"),
        (b'{"bad_synthetic":true}', "CONTRACT_FAILURE"),
        (KEY, "CONTRACT_FAILURE"),
    ],
)
def test_control_capture_reopens_without_DATA_projection(tmp_path, raw, outcome):
    world = World(tmp_path)
    root = tmp_path / "control"
    adapter = Control()
    recipe = {
        "recipe_id": 1,
        "recipe_sha256": H,
        "implementation_contract_sha256": H,
        "transport_profile_sha256": H,
        "purpose": "HEALTH_CHECK",
        "max_http_attempts_per_invocation": 5,
        "max_duration_ms": 10000,
    }
    begin = {
        "schema_version": o.CONTROL_BEGIN,
        "campaign_start_sha256": H,
        "profile_sha256": H,
        "plan_sha256": H,
        "segment_id": 1,
        "work_id": 1,
        "attempt": 1,
        "recipe_sha256": H,
        "request_target_sha256": b.sha(adapter.target(recipe)).hex(),
        "started_utc": world.clock.utc(),
    }
    audit.begin_control(root, begin)
    capture = transport.Capture(
        "VALIDATION_REQUIRED",
        "OK",
        200,
        "application/json",
        "absent",
        None,
        raw,
        len(raw),
        1,
    )
    record = transport_audit.transport_record(
        {"kind": "SERVICE_CONTROL", "work_id": 1}, 1, capture, world.clock.utc()
    )
    io.write(root / "transport.json", b.canonical(record))
    io.write(
        root / "control_timing.json",
        b.canonical(
            {
                "schema_version": "stage12_control_timing_b2_v1",
                "begin_sha256": b.digest(begin),
                "epoch_id": H,
                "started_mono_ns": 0,
                "completed_mono_ns": 1_000_000,
                "max_duration_ms": recipe["max_duration_ms"],
            }
        ),
    )
    finish, receipt = audit.finish_control(root, record, raw, recipe, adapter, key=KEY)
    assert (
        finish["outcome"] == outcome
        and audit.reopen_control(root, recipe, adapter) == finish
    )
    assert not (root / "candidates.parquet").exists()
    if raw == KEY:
        assert not (root / "raw.zst").exists() and finish["response_sha256"] is None
    else:
        assert (root / "raw.zst").exists()
    with pytest.raises(c.Stage12Error):
        audit.reopen(root, **world.rules.kwargs())

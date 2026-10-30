from pathlib import Path
import pytest
from stage12_b2_synthetic import World, H, offline
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def publish_world(world, inputs, segment, root):
    profile, plan, start, science, admission, rows = inputs
    snap = b.parse(io.read(segment / "snapshot.json"), o.SNAPSHOT)
    closure = world.put(
        {
            "schema_version": "stage12_campaign_closure_b2_v1",
            "window_plan_sha256": world.window_hash,
            "campaign_start_sha256": b.digest(science),
            "ordered_segment_closure_hashes": [snap["segment_closure_sha256"]],
            "workload_sha256": b.digest(plan),
            "workload_kind": plan["workload_kind"],
            "operator_campaign_account_sha256": H,
            "account_status": "NO_KNOWN_INTERVENTION",
            "disposition": "CLOSED_OBSERVATIONAL",
            "reviewed_utc": world.clock.utc(),
            "review_decision_sha256": H,
        }
    )

    def verify():
        def receipt(work, event):
            path = (
                segment / "attempts" / f"{work['work_id']:020d}_{event['attempt']:02d}"
            )
            assert (
                b.sha(io.read(path / "receipt.json")).hex()
                == event["receipt_inventory_sha256"]
            )
            return audit.reopen(path, **world.rules.kwargs())[0]

        return recovery.reopen(
            segment,
            start,
            profile,
            plan,
            works=lambda: iter(rows),
            verify_receipt=receipt,
            scratch=world.root / ("verify_" + world.nonce() + ".sqlite"),
            authority=world.gate,
        )

    expected = pub.publish_campaign(
        root,
        world.root / ("publish_work_" + world.nonce()),
        segment=segment,
        start=start,
        scientific_start=science,
        profile=profile,
        plan=plan,
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        campaign_closure_hash=closure,
        verify_campaign=verify,
        memory_bytes=64 * 1024 * 1024,
    )

    def validate():
        return pub.validate_terminal(
            root,
            expected,
            committed=True,
            validate_science=lambda path, manifest: pub.scientific_reopen(
                path,
                manifest,
                catalog=world.catalog,
                rules=world.rules,
                scratch=world.root / ("reopen_" + world.nonce()),
                memory_bytes=64 * 1024 * 1024,
                gate=world.gate,
                verify_campaign=verify,
            ),
        )

    return expected, validate, closure


def test_calibration_publication_and_reopen_before_N_window_closure(tmp_path):
    world = World(tmp_path)
    report, inputs = world.run()
    expected, validate, closure = publish_world(
        world, inputs, tmp_path / "segment", tmp_path / "published"
    )
    manifest = validate()
    assert manifest["kind"] == b.SYNTHETIC + "_" + pub.CALIBRATION
    assert manifest["publication_bindings"]["window_closure_sha256"] is None
    assert manifest["publication_bindings"]["owner_freeze_sha256"] is None
    assert (
        len(list(pub.relation_rows(tmp_path / "published", "request_execution"))) == 2
    )
    assert (
        len(list(pub.relation_rows(tmp_path / "published", "request_candidate"))) == 4
    )
    assert (tmp_path / "published/_COMMITTED").exists()
    reader = pub.ArtifactReader(
        tmp_path / "published",
        expected,
        scratch=tmp_path / "reader.sqlite",
        catalog=world.catalog,
        rules=world.rules,
        validate_artifact=validate,
    )
    assert len(list(reader.observation.semantic_ids())) == 2
    reader.validate()
    reader.close()
    with pytest.raises(FileExistsError):
        publish_world(world, inputs, tmp_path / "segment", tmp_path / "published")


@pytest.mark.parametrize(
    "target", ["raw_pack", "candidate", "registration", "summary", "manifest"]
)
def test_publication_reopen_detects_every_retained_layer_change(tmp_path, target):
    world = World(tmp_path)
    _, inputs = world.run()
    root = tmp_path / "published"
    expected, validate, _ = publish_world(world, inputs, tmp_path / "segment", root)
    paths = {
        "raw_pack": next((root / "raw_packs").rglob("*.zst")),
        "candidate": next((root / "request_candidate").glob("*.parquet")),
        "registration": root / "registration.json",
        "summary": root / "summary.json",
        "manifest": root / "manifest.json",
    }
    path = paths[target]
    raw = path.read_bytes()
    path.write_bytes(raw + b"changed synthetic evidence")
    with pytest.raises(c.Stage12Error):
        validate()


def test_raw_set_and_capture_context_recomputed_not_only_manifest_hash(tmp_path):
    world = World(tmp_path)
    _, inputs = world.run()
    root = tmp_path / "published"
    expected, validate, _ = publish_world(world, inputs, tmp_path / "segment", root)
    manifest = validate()
    manifest["raw_response_set_sha256"] = H
    with pytest.raises(c.Stage12Error, match="B2_CAPTURE_SET_MISMATCH"):
        pub.scientific_reopen(
            root,
            manifest,
            catalog=world.catalog,
            rules=world.rules,
            scratch=tmp_path / "forged_reopen",
            memory_bytes=64 * 1024 * 1024,
            gate=world.gate,
            verify_campaign=lambda: None,
        )

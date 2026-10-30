from copy import deepcopy
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from stage12_b2_synthetic import World, H, offline


def test_closed_successor_identity_and_scope(tmp_path):
    world = World(tmp_path)
    profile, plan, start, science, admission, rows = world.inputs()
    o.validate_plan(plan, profile)
    b.validate(start)
    b.validate(science)
    b.validate(admission)
    q = bytes.fromhex(rows[0]["query_semantic_id"])
    p = c.policy(5)["retrieval_policy_id"]
    x = b.execution_id(
        q,
        p,
        bytes.fromhex(science["materialization_contract_sha256"]),
        bytes.fromhex(H),
        bytes.fromhex(start["campaign_id"]),
    )
    assert x != b.execution_id(
        q,
        p,
        bytes.fromhex(science["materialization_contract_sha256"]),
        bytes.fromhex(H),
        b.sha(b"other campaign"),
    )
    assert b.attempt_id(x, bytes.fromhex(start["campaign_id"]), 1) != c.attempt_id(
        x, bytes.fromhex(start["campaign_id"]), 1
    )
    changed = deepcopy(profile)
    changed["scope"] = "PUBLIC_SYNTHETIC_ONLY"
    with pytest.raises(c.Stage12Error):
        o.validate_profile(changed)
    changed = deepcopy(profile)
    changed["resource_sample_period_ms"] = 101
    with pytest.raises(c.Stage12Error):
        o.validate_profile(changed)
    with pytest.raises(c.Stage12Error):
        b.validate({**admission, "invented": True})
    with pytest.raises(c.Stage12Error):
        b.validate_type(True, "U")
    with pytest.raises(c.Stage12Error):
        b.validate_type("0" * 64, "D")
    with pytest.raises(c.Stage12Error):
        b.parse(b'{"schema_version":"x","schema_version":"y"}\n')


def test_real_population_cannot_be_small_fixture(tmp_path):
    world = World(tmp_path)
    bad = {**world.catalog.binding, "population_scope": b.DEVELOPMENT}
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as cat

    with pytest.raises(c.Stage12Error):
        cat.Catalog.build(
            tmp_path / "bad.sqlite",
            bad,
            semantics=lambda: (),
            mapping=lambda: (),
            hypotheses=lambda: (),
            contexts=lambda: (),
            families=lambda: (),
            authority=world.gate.authority,
        )

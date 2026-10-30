from copy import deepcopy
import pytest
from stage12_b2_synthetic import World, H, KEY, offline
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_pipeline as pipe
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_planning as planning
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_evidence as evidence
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response


@pytest.mark.parametrize(
    "mutation",
    [
        "connections",
        "admission_memory",
        "rate_ceiling",
        "period",
        "missing",
        "extra",
        "reserved_monitor",
    ],
)
def test_unselected_or_weakened_operating_values_reject(tmp_path, mutation):
    world = World(tmp_path)
    profile, plan, *_ = world.inputs()
    profile = deepcopy(profile)
    plan = deepcopy(plan)
    if mutation == "connections":
        profile["operator_allowance"]["connections"] = 5
    elif mutation == "admission_memory":
        profile["resources"]["admission_memory_bytes"] = 1
    elif mutation == "rate_ceiling":
        profile["operator_allowance"]["rate_ceiling"] = {"num": 61, "den": 1}
    elif mutation == "period":
        profile["resource_sample_period_ms"] = 101
    elif mutation == "missing":
        del profile["demonstrated_ceiling_sha256"]
    elif mutation == "extra":
        profile["implicit_default"] = True
    else:
        plan["budgets"]["reserved_control_observations"] = 1
    with pytest.raises(c.Stage12Error):
        o.validate_plan(plan, profile)


def test_selection_recomputes_and_window_cannot_transfer(tmp_path):
    world = World(tmp_path)
    selected, bound = planning.load_selection(
        world.records,
        world.selection_hash,
        world.catalog,
        authority=world.gate.authority,
        scratch=tmp_path / "selection_reopen.sqlite",
    )
    assert selected == world.selection
    values = world.inputs()
    profile, plan, start, science, admission, rows = values
    slot = planning.verify_workload(
        world.records,
        world.selection_hash,
        selected,
        world.catalog,
        plan,
        lambda: iter(rows),
        admission,
        authority=world.gate.authority,
    )
    assert slot["slot_id"] == 1
    with pytest.raises(c.Stage12Error):
        planning.verify_workload(
            world.records,
            world.selection_hash,
            selected,
            world.catalog,
            plan,
            lambda: iter(rows[:1]),
            admission,
            authority=world.gate.authority,
        )
    with pytest.raises(c.Stage12Error):
        planning.verify_workload(
            world.records,
            world.selection_hash,
            selected,
            world.catalog,
            {**plan, "window_plan_sha256": H},
            lambda: iter(rows),
            admission,
            authority=world.gate.authority,
        )
    forged = {**bound, "C": 6}
    with pytest.raises(c.Stage12Error):
        planning.load_selection(
            world.records,
            world.put(forged),
            world.catalog,
            authority=world.gate.authority,
            scratch=tmp_path / "forged.sqlite",
        )


@pytest.mark.parametrize(
    "failure", ["unfinished", "failure", "oversized", "secret", "delay"]
)
def test_administrative_failures_preserve_charges_and_block(tmp_path, failure):
    world = World(tmp_path)
    profile, plan, start, science, admission, rows = world.inputs()
    if failure == "unfinished":
        ledger = world.records.get(
            admission["bootstrap_acquisition_sha256"], "bootstrap_administration"
        )
        ledger["attempts"][0]["finish_sha256"] = None
        ledger["status"] = "INCOMPLETE"
        with pytest.raises(c.Stage12Error):
            pipe.bootstrap_spent(world.records, world.put(ledger), plan, profile, start)
        return

    def load_record():
        if failure == "failure":
            raise RuntimeError("SYNTHETIC INTERRUPTED LOCAL READ")
        if failure == "delay":
            world.clock.advance(11_000_000_000)
        return (
            KEY
            if failure == "secret"
            else b"x" * (65536 + 1)
            if failure == "oversized"
            else world.records.raw(H)
        )

    root = tmp_path / "failed_bootstrap"
    with pytest.raises((c.Stage12Error, RuntimeError)):
        pipe.prepare_bootstrap(
            root,
            records=world.records,
            raw_factory=lambda: (load_record,),
            clock=world.clock,
            profile=profile,
            plan=plan,
            start=start,
            segment_nonce=admission["segment_nonce"],
            epoch_id=world.nonce(),
            authority=world.gate,
            authority_hash=H,
            writer_release_evidence=world.releases[admission["segment_nonce"]],
            secret_guard=lambda raw: response.secret_guard(raw, KEY),
            previous_hash=None,
        )
    assert (
        list(root.glob("admin_*_begin.json"))
        and not (root / "_WRITER_RELEASED.json").exists()
    )
    if failure == "failure":
        assert not list(root.glob("admin_*_finish.json"))
    else:
        finish = b.parse(io.read(next(root.glob("admin_*_finish.json"))))
        assert (
            finish["outcome"] in ("FAILED", "BUDGET_EXHAUSTED")
            and finish["records"] == []
        )
    if failure == "secret":
        assert not (world.records.root / (b.sha(KEY).hex() + ".json")).exists()


def test_cli_requires_authorization_before_port_input_or_runtime_key(tmp_path):
    from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli

    class Denied:
        test_only = True
        population_scope = b.SYNTHETIC

        class Auth:
            def require(self, *args):
                raise c.Stage12Error("SYNTHETIC_AUTHORITY_REJECTED")

        authority = Auth()

        def campaign_inputs(self):
            raise AssertionError("must not access inputs")

        def runtime_key(self):
            raise AssertionError("must not access secrets")

    with pytest.raises(c.Stage12Error):
        cli.execute(
            "run-campaign",
            cli.Session(
                Denied(),
                {"runtime_port_sha256": H},
                tmp_path / "out",
                tmp_path / "scratch",
                H,
            ),
        )


def test_new_descriptor_bytes_equal_implemented_definitions():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "docs/scientific_assets"
    for name, descriptor in b.assets().items():
        assert (root / (name + ".json")).read_bytes() == b.canonical(descriptor)
    assert (
        b.REGISTRY["schema_bundle_version"]
        == "stage12_development_observational_schemas_b2_v1"
    )

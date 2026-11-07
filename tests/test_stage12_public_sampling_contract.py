"""AP-1 synthetic records only; never an executable runtime memory proof."""

from copy import deepcopy
import pytest
from test_stage12_public_operations_v2 import (
    inputs,
    H,
    offline,  # noqa: F401
    FakeAuthority,
)  # noqa: F401
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_sampling_contract as a,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as old
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def ap_inputs(count=2, rate=20):
    profile, plan, start, rows, runtime = inputs(count, rate)
    profile.pop("resource_sample_period_ms")
    profile.update(
        schema_version=a.PROFILE,
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
    )
    profile["resources"]["writer_guard_ms"] = 5000
    names = "SLOT_ARENA INDEX_METADATA SERIALIZATION_SCRATCH PYTHON_ALLOCATOR NATIVE_HASH_IO ADDITIONAL_STACK OTHER_RETAINED".split()
    sizes = [65536, 4096, 65536, 65536, 4096, 0, 4096]
    bound = dict(
        schema_version=a.BOUND,
        scope=a.SCOPE,
        sampling_policy_sha256=a.POLICY_SHA,
        client_git_sha=start["client_git_sha"],
        runtime_inventory_sha256=a.digest(runtime),
        technical_review_record_sha256=H,
        method="CLOSED_ALLOCATION_INVENTORY",
        components=[
            dict(
                name=n,
                bound_bytes=v,
                basis="STATIC_MAXIMUM" if v else "NOT_USED",
                evidence_sha256=H,
            )
            for n, v in zip(names, sizes)
        ],
        total_component_bound_bytes=sum(sizes),
        method_evidence_sha256=[H],
    )
    profile["sampling_runtime_bound_sha256"] = a.digest(bound)
    for b in [plan["budgets"], plan["blocks"][0]["budget"]]:
        b["event_count"] = 100000
    B = plan["budgets"]["active_duration_ms"]
    A = (B + 49) // 50 + 2
    F = 4 * A + 8
    inventory_count = 8
    plan.update(
        schema_version=a.PLAN,
        operations_profile_sha256=a.digest(profile),
        sampling_budget=dict(
            maximum_segments=1,
            maximum_observations=A,
            maximum_inventory_versions_per_segment=8,
            additional_event_tokens=2 * A + 4,
            additional_file_data_bytes=4096 * F + inventory_count * (512 * F + 4096),
            additional_file_entries=F + inventory_count,
        ),
    )
    start.update(
        schema_version=a.START,
        profile_sha256=a.digest(profile),
        plan_sha256=a.digest(plan),
        rule_bundle_sha256=a.RULE_BUNDLE,
        sampling_policy_sha256=a.POLICY_SHA,
    )
    return profile, plan, start, rows, runtime, bound


class TestOnlyAuthority(FakeAuthority):
    __test__ = False

    def __init__(self, bound, reject=None):
        super().__init__(reject)
        self.bound = bound

    def sampling_bound(self, profile, start):
        return deepcopy(self.bound)

    def require(self, purpose, h, context):
        if purpose == "sampling_runtime_bound":
            self.calls.append(purpose)
            c.require(
                self.reject != purpose and h == a.digest(self.bound),
                "SYNTHETIC_AUTHORITY_REJECTED",
            )
        elif purpose == "sampling_bound_review":
            c.require(
                context == self.bound and self.reject != purpose and h == H,
                "SYNTHETIC_AUTHORITY_REJECTED",
            )
        else:
            super().require(purpose, h, context)


def test_AP01_closed_versions_and_actual_record_gate():
    p, pl, s, rows, run, bound = ap_inputs()
    a.verify_authorities(p, pl, s, TestOnlyAuthority(bound))
    with pytest.raises(c.Stage12Error):
        a.verify_authorities(p, pl, s, FakeAuthority())
    with pytest.raises(c.Stage12Error):
        old.validate_profile(p)
    for key, value in [
        ("unexpected", 1),
        ("sampling_policy_sha256", None),
        ("scope", "DEVELOPMENT"),
    ]:
        bad = deepcopy(p)
        bad[key] = value
        with pytest.raises(c.Stage12Error):
            a.validate_profile(bad)
    with pytest.raises(c.Stage12Error):
        a.parse(
            c.canonical(p).replace(
                b'"scope":', b'"scope":"PUBLIC_SYNTHETIC_ONLY","scope":'
            ),
            a.PROFILE,
        )


@pytest.mark.parametrize(
    "bad", ["wrong_client", "unknown_component", "overflow", "observed_method"]
)
def test_AP23_runtime_bounds_are_not_memory_reservations(bad):
    p, pl, s, rows, run, record = ap_inputs()
    if bad == "wrong_client":
        record["client_git_sha"] = "0" * 40
    if bad == "unknown_component":
        record["components"][1]["name"] = "UNKNOWN"
    if bad == "overflow":
        record["components"][1]["bound_bytes"] = 2**64
    if bad == "observed_method":
        record["method"] = "MEASURED_RSS"
    p["sampling_runtime_bound_sha256"] = a.digest(record)
    with pytest.raises(c.Stage12Error):
        a.validate_bound(record, p, s)


def test_AP10_AP22_cumulative_sampling_budget_cannot_reuse_old_limits():
    p, pl, s, *_ = ap_inputs()
    for field in [
        "additional_event_tokens",
        "additional_file_data_bytes",
        "additional_file_entries",
    ]:
        bad = deepcopy(pl)
        bad["sampling_budget"][field] = 1
        with pytest.raises(c.Stage12Error):
            a.validate_plan(bad, p)
    assert a.POLICY["maximum_outstanding_observations"] == 16
    assert a.POLICY["maximum_outstanding_bytes"] == 65536
    assert a.POLICY["maximum_unacknowledged_age_ms"] == 500


def test_AP01_all_successor_descriptors_and_historical_asset_bytes():
    from pathlib import Path
    from safe_geocoding_pipeline.preprocessing.stages import s12_assets

    descriptors = a.descriptors()
    assert len(descriptors) == 13
    for name, value in descriptors.items():
        assert (
            Path("docs/scientific_assets") / (name + ".json")
        ).read_bytes() == c.canonical(value)
    assert a.digest(descriptors[a.POLICY_VERSION]) == a.POLICY_SHA
    assert (
        a.digest(descriptors["stage12_public_sampling_rule_bundle_v1"]) == a.RULE_BUNDLE
    )
    assert not set(descriptors) & set(s12_assets.objects())
    for row in a.BUNDLE["baseline_contracts"]:
        if row["path"].startswith("docs/"):
            assert c.sha(Path(row["path"]).read_bytes()).hex() == row["sha256"]

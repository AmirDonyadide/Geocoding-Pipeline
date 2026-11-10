"""Historical records versus actual shared-lease live scratch; synthetic only."""

from copy import deepcopy

import pytest

from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_core import Authority, binding, selection, G, H
from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
import test_stage12_ra_g1_allocation as builder_cases
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_scratch as scratch


def with_scratch(record, size):
    result = deepcopy(record)
    result["logical_scratch_bytes"] = size
    result["logical_allocations"][3]["bytes"] = size
    result["total_logical_bytes"] = sum(row["bytes"] for row in result["logical_allocations"])
    return result


@pytest.mark.parametrize("size", [64640, 65151, 65152, 65536])
def test_historical_record_parsing_does_not_assert_current_live_support(size):
    record = with_scratch(binding(selection()), size)
    profile = {"sampling_runtime_bound_sha256": contract.digest(record),
               "sampling_assurance_method": a.METHOD}
    start = dict(client_git_sha=G, runtime_inventory_sha256=H)
    assert a.validate_record(record, profile, start, contract) == record


@pytest.mark.parametrize("size", [64640, 65151])
def test_underdeclared_current_live_backing_rejects_before_facts(size, monkeypatch):
    selected = selection()
    auth = Authority(selected)
    def forbidden(*_args):
        pytest.fail("underdeclared live backing reached original facts or authority")
    monkeypatch.setattr(auth, "resource_facts", forbidden)
    monkeypatch.setattr(auth, "initial_resource_facts", forbidden)
    monkeypatch.setattr(auth, "require", forbidden)
    with pytest.raises(c.Stage12Error, match="RA_G1_LOGICAL_LIMIT"):
        a.verify_runtime(with_scratch(binding(selected), size), auth, {})
    assert auth.charges == 0


def test_exact_current_backing_retains_all_runtime_gates():
    selected = selection()
    auth = Authority(selected)
    size = sum(scratch.RA_G1_CAPS.values())
    assert size == 65152 <= a.SCRATCH_BYTES
    result = a.verify_runtime(with_scratch(binding(selected), size), auth, {})
    assert result["origin"] == "SYNTHETIC_TEST_ONLY"
    assert auth.grants and auth.charges


@pytest.mark.parametrize("family", ["historical", "bootstrap30", "shared_lease"])
def test_real_builder_and_parsers_bind_exact_family_scratch(family, monkeypatch):
    loader = builder_cases.module
    preparer = loader("stage12_prepare_ra_g1")
    original_build = preparer.build
    captured = []
    def build(allocation, bootstrap, **kwargs):
        if family != "historical" and kwargs["source_files"]:
            _selected, adoption, _reader = bootstrap_inputs()
            allocation["version"] = (preparer.SHARED_LEASE_ALLOCATION_VERSION
                                     if family == "shared_lease"
                                     else preparer.BOOTSTRAP_ALLOCATION_VERSION)
            allocation["bootstrap_prefix_adoption"] = adoption
            allocation["bootstrap_prefix_adoption_sha256"] = contract.digest(adoption)
            allocation["accounting_inventory"], allocation["accounting"] = ac.compile_inventory(
                kwargs["source_files"], allocation["accounting_inventory"]["backends"],
                "REPRESENTATIVE_NO_SERVICE", bootstrap_successor=True,
                shared_lease_successor=family == "shared_lease")
        result = original_build(allocation, bootstrap, **kwargs)
        captured.append(result)
        return result
    monkeypatch.setattr(preparer, "build", build)
    monkeypatch.setattr(builder_cases, "module",
                        lambda name: preparer if name == "stage12_prepare_ra_g1" else loader(name))
    # Existing synthetic full-build oracle executes real schemas/phase associations.
    builder_cases.test_unissued_builder_exact_shapes_and_no_strict_capacity_certificate()
    assert len(captured) == 1
    data, bundle = captured[0]
    record = bundle["binding"]
    expected = 65152 if family == "shared_lease" else 64640
    assert record["logical_scratch_bytes"] == expected
    assert record["logical_allocations"][3]["bytes"] == expected
    assert record["total_logical_bytes"] == sum(row["bytes"] for row in record["logical_allocations"])
    assert data["selection"]["status"] == "UNISSUED"
    if family == "shared_lease":
        assert data["version"] == preparer.SHARED_LEASE_VERSION

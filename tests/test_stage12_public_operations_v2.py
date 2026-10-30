"""O-r2 invented fixtures only. All apparent authorities/values are synthetic."""

from __future__ import annotations

import copy
import socket
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s12_operations as v1
from safe_geocoding_pipeline.preprocessing.stages import s12_probe as probe
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport

H = c.sha(b"SYNTHETIC TEST ONLY - NOT AN AUTHORITY RECORD").hex()
KEY = b"SYNTHETIC_ONLY_CANARY"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*_a, **_k):
        raise AssertionError(
            "O-r2 test attempted forbidden network/process/credential access"
        )

    for name in ("create_connection", "getaddrinfo", "gethostbyname"):
        monkeypatch.setattr(socket, name, denied)
    for name in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, denied)
    for name in ("Popen", "run", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, denied)
    monkeypatch.setattr(transport.Secret, "runtime", denied)
    monkeypatch.setattr(transport.Secret, "private_file", denied)


class FakeClock:
    def __init__(self, wall_offset_ns=0):
        self.value = 0
        self.wall_offset_ns = wall_offset_ns
        self.lock = threading.RLock()

    def now_ns(self):
        with self.lock:
            return self.value

    def advance(self, ns):
        with self.lock:
            self.value += ns

    def wait_until(self, ns):
        with self.lock:
            self.value = max(self.value, ns)

    def utc(self):
        value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=(self.now_ns() + self.wall_offset_ns) // 1000
        )
        return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class FakeAuthority:
    """Test-local contract double. Never installed in a production gate."""

    def __init__(self, reject=None):
        self.reject = reject
        self.calls = []

    def require(self, purpose, evidence_sha256, context):
        self.calls.append(purpose)
        if purpose == self.reject or evidence_sha256 != H:
            raise c.Stage12Error("SYNTHETIC_AUTHORITY_REJECTED")


def inputs(count=2, rate=20, *, monitored=False):
    baseline = assets.hashes()
    profile = {
        "schema_version": o.PROFILE,
        "scope": o.SCOPE,
        "rule_bundle_sha256": o.RULE_BUNDLE,
        "policy_freeze_record_sha256": H,
        "preserved": {
            "operations_v1_sha256": baseline[v1.VERSION].hex(),
            "materialization_sha256": baseline[c.MATERIALIZATION].hex(),
            "response_validation_sha256": baseline[response.VALIDATION].hex(),
            "public_audit_source_sha256": "b43134525b99b60767d9661d334ccf743d101f06e85be42350483048a1c9d8f4",
        },
        "transport_profile_sha256": H,
        "operator_allowance": {
            "record_sha256": H,
            "rate_ceiling": {"num": 60, "den": 1},
            "connections": 4,
            "valid_from": "2026-01-01T00:00:00.000000Z",
            "valid_until": "2026-01-02T00:00:00.000000Z",
        },
        "states": [
            {
                "state_id": 1,
                "rate": {"num": rate, "den": 1},
                "connections": 4,
                "admitted_operations": 2,
                "evidence_sha256": H,
            }
        ],
        "resources": {
            "admission_memory_bytes": o.MEMORY,
            "capacity_basis_sha256": H,
            "process_overhead_bytes": 2**28,
            "job_memory_bytes": 6 * 2**30,
            "pending_request_bytes": 2**20,
            "per_attempt_disk_bound_bytes": 2**27,
            "fixed_campaign_disk_bound_bytes": 2**24,
            "allocated_disk_bytes": 2**40,
            "resource_review_sha256": H,
            "scheduler_guard_ms": 100,
            "writer_guard_ms": 1000,
        },
        "monitoring": {"mode": "PUBLIC_GAPS_ONLY", "gaps_record_sha256": H},
        "resource_sample_period_ms": 100,
    }
    if monitored:
        profile["monitoring"] = {
            "mode": "FROZEN_V1",
            "mechanism": "CONTROLLED_CAMPAIGN",
            "deployment_binding_sha256": H,
            "verifier_contract_sha256": H,
            "refresh_recipe_id": 1,
            "closure_recipe_id": 2,
            "exclusion_record_sha256": H,
        }
    fixture = probe.fixtures()[0]
    rows = [
        {
            "work_id": i,
            "block_id": 1,
            "kind": "DATA",
            "fixture_id": fixture["fixture_id"],
            "result_limit": 1,
            "repetition": i - 1,
            "recipe_id": None,
            "retry_spacing_key": fixture["fixture_id"],
        }
        for i in range(1, count + 1)
    ]
    budget = {
        "data_observations": count,
        "required_control_observations": 0,
        "reserved_control_observations": 0,
        "data_attempts": count * 5,
        "control_http_attempts": 0,
        "administrative_operations": 0,
        "administrative_duration_ms": 0,
        "active_duration_ms": 600_000,
        "storage_bytes": 2**40,
        "event_count": 10000,
    }
    plan = {
        "schema_version": o.PLAN,
        "scope": o.SCOPE,
        "operations_profile_sha256": o.digest(profile),
        "fixture_inventory_sha256": o.digest(probe.fixtures()),
        "work_manifest_sha256": o.manifest_digest(rows),
        "control_recipes": [],
        "blocks": [
            {
                "block_id": 1,
                "state_id": 1,
                "observation_ids": list(range(1, count + 1)),
                "reserved_control_ids": [],
                "budget": copy.deepcopy(budget),
                "evaluation": "EXPLORATORY",
                "criteria": None,
                "fallback_state_ids": [],
                "transition_from": None,
            }
        ],
        "experiment_kind": "PERFORMANCE",
        "capability_parent_sha256": None,
        "budgets": budget,
        "window_start": "2026-01-01T00:00:00.000000Z",
        "window_end": "2026-01-01T00:10:00.000000Z",
        "shutdown_reserve_ms": 80_000,
        "selection_basis_sha256": H,
    }
    if monitored:
        plan["control_recipes"] = [
            {
                "recipe_id": i,
                "recipe_sha256": H,
                "implementation_contract_sha256": H,
                "transport_profile_sha256": H,
                "purpose": purpose,
                "max_http_attempts_per_invocation": 1,
                "max_duration_ms": 10_000,
            }
            for i, purpose in ((1, "IDENTITY_REFRESH"), (2, "IDENTITY_CLOSURE"))
        ]
        rows += [
            {
                "work_id": count + i,
                "block_id": 1,
                "kind": "SERVICE_CONTROL",
                "fixture_id": None,
                "result_limit": None,
                "repetition": None,
                "recipe_id": i,
                "retry_spacing_key": H,
            }
            for i in (1, 2)
        ]
        plan["blocks"][0]["observation_ids"].append(count + 2)
        plan["blocks"][0]["reserved_control_ids"] = [count + 1]
        for b in (budget, plan["blocks"][0]["budget"]):
            b.update(
                required_control_observations=1,
                reserved_control_observations=1,
                control_http_attempts=2,
            )
        plan["work_manifest_sha256"] = o.manifest_digest(rows)
    runtime = {"scope": "SYNTHETIC_TEST_ONLY"}
    start = {
        "schema_version": o.START,
        "scope": o.SCOPE,
        "campaign_id": H,
        "profile_sha256": o.digest(profile),
        "plan_sha256": o.digest(plan),
        "rule_bundle_sha256": o.RULE_BUNDLE,
        "policy_freeze_record_sha256": H,
        "implementation_authorization_sha256": H,
        "implementation_review_sha256": H,
        "initial_workload_authority_sha256": H,
        "client_git_sha": "1" * 40,
        "runtime_inventory_sha256": o.digest(runtime),
        "created_utc": "2026-01-01T00:00:00.000000Z",
    }
    return profile, plan, start, rows, runtime


def rebind(profile, plan, start, rows=None):
    plan["operations_profile_sha256"] = o.digest(profile)
    if rows is not None:
        plan["work_manifest_sha256"] = o.manifest_digest(rows)
    start["profile_sha256"], start["plan_sha256"] = o.digest(profile), o.digest(plan)


def test_T01_closed_profile_no_defaults_and_preserved_v1():
    profile, plan, start, rows, _ = inputs()
    o.verify_authorities(profile, plan, start, FakeAuthority())
    o.verify_work_manifest(lambda: iter(rows), plan)
    assert o.parse(c.canonical(profile), o.PROFILE) == profile
    assert v1.Operations().requests_per_second == 1
    for key in profile:
        invalid = copy.deepcopy(profile)
        del invalid[key]
        with pytest.raises(c.Stage12Error):
            o.validate_profile(invalid)
    invalid = copy.deepcopy(profile)
    invalid["unselected_default"] = 60
    with pytest.raises(c.Stage12Error):
        o.validate_profile(invalid)
    with pytest.raises(c.Stage12Error):
        o.parse(b'{"scope":"PUBLIC_SYNTHETIC_ONLY","scope":"DEVELOPMENT"}\n', o.PROFILE)


@pytest.mark.parametrize("bad", [True, False, 0, -1, 1.5, "UNSELECTED", None, 2**64])
def test_T01_exact_types_overflow_and_unselected_rejected(bad):
    profile, *_ = inputs()
    profile["states"][0]["rate"]["num"] = bad
    with pytest.raises(c.Stage12Error):
        o.validate_profile(profile)


def test_T01_digest_is_not_authority_and_protected_is_rejected():
    profile, plan, start, _, _ = inputs()
    with pytest.raises(c.Stage12Error, match="AUTHORITY"):
        o.verify_authorities(
            profile, plan, start, FakeAuthority("implementation_review_sha256")
        )
    profile["scope"] = "DEVELOPMENT"
    with pytest.raises(c.Stage12Error):
        o.validate_profile(profile)


def test_T13_finite_totality_retries_candidate_size_and_control_budget():
    profile, plan, start, rows, _ = inputs()
    extra = copy.deepcopy(rows[-1])
    extra["work_id"] = 3
    with pytest.raises(c.Stage12Error):
        o.verify_work_manifest(lambda: iter(rows + [extra]), plan)
    rows[0]["result_limit"] = 41
    rebind(profile, plan, start, rows)
    with pytest.raises(c.Stage12Error):
        o.verify_work_manifest(lambda: iter(rows), plan)
    plan["budgets"]["administrative_operations"] = 1
    with pytest.raises(c.Stage12Error):
        o.validate_plan(plan, profile)


def test_T01_descriptor_opt_in_keeps_existing_bytes():
    old = assets.objects()
    new = assets.objects(public_operations=True)
    assert set(new) - set(old) == set(o.SCHEMAS)
    assert all(c.canonical(old[k]) == c.canonical(new[k]) for k in old)
    root = Path(__file__).resolve().parents[1]
    for name, descriptor in o.descriptors().items():
        assert descriptor["live_instance"] is False
        assert (
            root / "docs/scientific_assets" / (name + ".json")
        ).read_bytes() == c.canonical(descriptor)


@pytest.mark.parametrize(
    "rate,spacing", [(20, 50_000_000), (40, 25_000_000), (60, 16_666_667)]
)
def test_T02_integer_spacing_ceiling(rate, spacing):
    assert o.interval({"num": rate, "den": 1}) == spacing


def test_T01_focused_descriptor_validator_only():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "offline_descriptor_validator",
        root / "scripts/validate_stage12_implementation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert set(module.validate_public_operations()) == set(o.SCHEMAS)

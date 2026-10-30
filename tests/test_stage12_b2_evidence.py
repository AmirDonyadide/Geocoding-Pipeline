"""All authority, permission and operator bytes below are invented test fixtures."""

from copy import deepcopy
import pytest
from stage12_b2_synthetic import World, H, offline
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_evidence as e
from safe_geocoding_pipeline.preprocessing.stages import s12_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io


def gate_fixture(world):
    put = world.put
    now = world.clock.utc()
    records = world.records
    correspondence = put(
        {
            "schema_version": e.version("correspondence"),
            "source_kind": "ADMIN_RECORD",
            "retained_record_sha256": H,
            "asserted_issuer": "SYNTHETIC_TEST_ONLY invented operator",
            "source_locator": "synthetic/statement",
            "statement_utc": now,
            "statement_date": None,
            "acquired_utc": now,
            "signature_record_sha256": None,
        }
    )
    review = put(
        {
            "schema_version": e.version("authority_review"),
            "subject_record_sha256": correspondence,
            "issuer_role_record_sha256": H,
            "channel_evidence_sha256": H,
            "reviewer_delegation_sha256": H,
            "reviewed_utc": now,
            "result": "ATTRIBUTION_ACCEPTED",
        }
    )
    facts = [
        {
            "schema_version": e.version("observation_fact"),
            "category": "INDEX"
            if name in ("index_uuid", "document_count")
            else "SOFTWARE",
            "subject": name,
            "status": "OPERATOR_REPORTED",
            "value": {
                "kind": "COUNT",
                "decimal": "123",
                "precision": "APPROXIMATE",
                "unit": "DOCUMENTS",
            }
            if name == "document_count"
            else {"kind": "TOKEN", "text": "SYNTHETIC_TEST_ONLY " + name},
            "as_of_start": now,
            "as_of_end": now,
            "precision": "INSTANT",
            "correspondence_sha256": correspondence,
            "check_receipt_sha256": None,
        }
        for name in sorted(e.REQUIRED_SUBJECTS)
    ]
    facts.sort(
        key=lambda x: (x["category"], x["subject"], x["as_of_start"], x["status"])
    )
    inventory = put(
        {
            "schema_version": e.version("evidence_inventory"),
            "facts": facts,
            "source_record_hashes": [correspondence],
            "authority_review_hashes": [review],
            "omissions_record_sha256": H,
            "coverage_contract_sha256": H,
        }
    )
    privacy_facts = [
        {"name": n, "status": "DOCUMENTED", "record_sha256": H}
        for n in b.TYPES["PrivacyName"]["enum"]
    ]
    arrangement = put(
        {
            "schema_version": e.version("privacy_arrangement"),
            "service_view_record_sha256": H,
            "data_categories_record_sha256": H,
            "facts_inventory_sha256": put(privacy_facts),
            "facts": privacy_facts,
            "source_permission_record_sha256": H,
            "controller_role_record_sha256": H,
            "operator_role_record_sha256": H,
        }
    )
    permission = put(
        {
            "schema_version": e.version("privacy_permission"),
            "arrangement_sha256": arrangement,
            "decision": "PERMITTED",
            "controller_decision_sha256": H,
            "source_licence_review_sha256": H,
            "institutional_privacy_security_review_sha256": H,
            "project_boundary_review_sha256": H,
            "revocation_check_record_sha256": H,
            "valid_from": "2025-01-01T00:00:00.000000Z",
            "valid_until": "2027-01-01T00:00:00.000000Z",
            "permitted_workload_class": "DEVELOPMENT_ONLY",
        }
    )
    decision = put(
        {
            "schema_version": e.version("scientific_decision"),
            "decision": "ADOPT_CONDITIONAL",
            "amendment_sha256": b.AMENDMENT_SHA256,
            "schema_spec_sha256": b.SPEC_SHA256,
            "owner_delegation_sha256": H,
            "accepted_limitations_sha256": H,
            "decided_utc": now,
        }
    )
    for name in (c.MATERIALIZATION, response.VALIDATION):
        raw = c.canonical(assets.objects()[name])
        digest = b.sha(raw).hex()
        io.write(records.root / (digest + ".json"), raw)
    interpretation = put(
        {
            "schema_version": e.version("response_interpretation"),
            "materialization_sha256": assets.hashes()[c.MATERIALIZATION].hex(),
            "validation_sha256": assets.hashes()[response.VALIDATION].hex(),
            "approved_origin_record_sha256": H,
            "authentication_review_sha256": H,
            "decision_sha256": H,
            "no_secret_echo_review_sha256": H,
            "public_probe_evidence_sha256": H,
            "service_view_record_sha256": H,
            "vocabulary_echo_evidence_sha256": H,
        }
    )
    window = {
        **records.get(world.window_hash, "window_plan"),
        "privacy_permission_sha256": permission,
        "scientific_decision_sha256": decision,
        "operator_arrangement_sha256": correspondence,
        "authority_review_sha256": review,
    }
    window_hash = put(window)
    binding_hash = put(
        {
            "schema_version": e.version("observation_binding"),
            "provenance_model": "MAINTAINED_SERVICE_OBSERVATIONS",
            "data_generation_status": "UNVERIFIED",
            "continuous_service_state": "NOT_VERIFIED",
            "initial_evidence_inventory_sha256": inventory,
            "window_plan_sha256": window_hash,
            "response_interpretation_sha256": interpretation,
        }
    )
    state = {"state": "OPEN", "evidence_sha256": H}
    gate = e.Gate(
        records,
        world.gate.authority,
        population_scope=b.SYNTHETIC,
        clock=world.clock,
        window_hash=window_hash,
        permission_hash=permission,
        scientific_hash=decision,
        interpretation_hash=interpretation,
        revocation=lambda p, t: H,
        window_state=lambda h: state,
        binding_hash=binding_hash,
        selection_hash=world.selection_hash,
    )
    nonce = world.nonce()
    pre = put(
        {
            "schema_version": e.version("window_observation"),
            "window_plan_sha256": window_hash,
            "segment_nonce": nonce,
            "phase": "PREFLIGHT",
            "inventory_sha256": inventory,
            "correspondence_sha256": correspondence,
            "authority_review_sha256": review,
            "observed_from": now,
            "observed_until": now,
            "acquired_utc": now,
            "interpretation_review_sha256": H,
        }
    )
    return gate, pre, nonce, state


def test_actual_gate_keeps_point_observations_and_first_emission_age(tmp_path):
    world = World(tmp_path)
    gate, pre, nonce, state = gate_fixture(world)
    gate.admit(pre, nonce)
    gate.before_dispatch()
    world.clock.advance(60_000_001_000)
    with pytest.raises(c.Stage12Error, match="PREFLIGHT_MISSING"):
        gate.before_dispatch()
    assert (
        gate.records.get(gate.binding_hash, "observation_binding")[
            "continuous_service_state"
        ]
        == "NOT_VERIFIED"
    )


def test_actual_gate_window_closed_and_notice_block(tmp_path):
    world = World(tmp_path)
    gate, pre, nonce, state = gate_fixture(world)
    gate.admit(pre, nonce)
    gate.emitted()
    world.clock.advance(61_000_000_000)
    gate.before_dispatch()
    state["state"] = "CLOSED"
    with pytest.raises(c.Stage12Error, match="WINDOW_CLOSED"):
        gate.before_dispatch()
    gate.check()  # evidence reopening/publication is not further dispatch
    state["state"] = "OPEN"
    gate.interrupt(H)
    with pytest.raises(c.Stage12Error, match="OBSERVATION_CONTRACT_FAILURE"):
        gate.before_dispatch()


@pytest.mark.parametrize(
    "failure",
    [
        "denied",
        "expiry",
        "unknown_fact",
        "missing_source_permission",
        "revoked",
        "borrowed_attribution",
    ],
)
def test_permission_failures_are_not_scientific_approval(tmp_path, failure):
    world = World(tmp_path)
    gate, pre, nonce, state = gate_fixture(world)
    if failure == "borrowed_attribution":
        world.gate.authority.reject = "attribution"
    elif failure == "revoked":
        world.gate.authority.reject = "permission_current"
    else:
        permission = gate.records.get(gate.permission_hash, "privacy_permission")
        if failure == "denied":
            permission["decision"] = "UNRESOLVED"
        elif failure == "expiry":
            permission["valid_until"] = "2026-01-01T00:00:00.000000Z"
        else:
            arrangement = gate.records.get(
                permission["arrangement_sha256"], "privacy_arrangement"
            )
            if failure == "unknown_fact":
                arrangement["facts"][0].update(status="UNKNOWN", record_sha256=None)
                arrangement["facts_inventory_sha256"] = world.put(arrangement["facts"])
            else:
                arrangement["source_permission_record_sha256"] = None
            permission["arrangement_sha256"] = world.put(arrangement)
        gate.permission_hash = world.put(permission)
        window = gate.records.get(gate.window_hash, "window_plan")
        window["privacy_permission_sha256"] = gate.permission_hash
        gate.window_hash = world.put(window)
    with pytest.raises(c.Stage12Error):
        gate.check()


@pytest.mark.parametrize(
    "mutation",
    [
        "post_before_response",
        "mismatch",
        "missing_post",
        "unknown_account",
        "late_review",
    ],
)
def test_closure_requires_exact_available_records(tmp_path, mutation):
    world = World(tmp_path)
    gate, pre, nonce, _ = gate_fixture(world)
    gate.admit(pre, nonce)
    post = deepcopy(gate.records.get(pre, "window_observation"))
    post["phase"] = "POSTFLIGHT"
    if mutation == "mismatch":
        inventory = gate.records.get(post["inventory_sha256"], "evidence_inventory")
        inventory["facts"][0]["value"] = {
            "kind": "TOKEN",
            "text": "DIFFERENT SYNTHETIC VALUE",
        }
        post["inventory_sha256"] = world.put(inventory)
    post_hash = world.put(post)
    closure = {
        "schema_version": e.version("segment_closure"),
        "window_plan_sha256": gate.window_hash,
        "segment_nonce": nonce,
        "campaign_start_sha256": H,
        "predecessor_closure_sha256": None,
        "preflight_sha256": pre,
        "postflight_sha256": None if mutation == "missing_post" else post_hash,
        "attempt_inventory_sha256": H,
        "controller_reconciliation_sha256": H,
        "resource_report_sha256": H,
        "gap_account_sha256": None,
        "operator_account_sha256": H,
        "account_status": "UNKNOWN"
        if mutation == "unknown_account"
        else "NO_KNOWN_INTERVENTION",
        "comparison": "REPORTED_FIELDS_AGREE",
        "disposition": "CLOSED_OBSERVATIONAL",
        "reviewed_utc": "2027-01-01T00:00:00.000000Z"
        if mutation == "late_review"
        else world.clock.utc(),
        "review_decision_sha256": H,
    }
    with pytest.raises(c.Stage12Error):
        gate.segment_closure(
            world.put(closure),
            start_hash=H,
            attempt_inventory=H,
            controller_reconciliation=H,
            resource_report=H,
            last_response_utc="2026-01-01T00:00:01.000000Z"
            if mutation == "post_before_response"
            else world.clock.utc(),
        )


def test_separately_verified_closure_is_observational_only(tmp_path):
    world = World(tmp_path)
    gate, pre, nonce, _ = gate_fixture(world)
    gate.admit(pre, nonce)
    post = {**gate.records.get(pre, "window_observation"), "phase": "POSTFLIGHT"}
    closure = {
        "schema_version": e.version("segment_closure"),
        "window_plan_sha256": gate.window_hash,
        "segment_nonce": nonce,
        "campaign_start_sha256": H,
        "predecessor_closure_sha256": None,
        "preflight_sha256": pre,
        "postflight_sha256": world.put(post),
        "attempt_inventory_sha256": H,
        "controller_reconciliation_sha256": H,
        "resource_report_sha256": H,
        "gap_account_sha256": None,
        "operator_account_sha256": H,
        "account_status": "NO_KNOWN_INTERVENTION",
        "comparison": "REPORTED_FIELDS_AGREE",
        "disposition": "CLOSED_OBSERVATIONAL",
        "reviewed_utc": world.clock.utc(),
        "review_decision_sha256": H,
    }
    result = gate.segment_closure(
        world.put(closure),
        start_hash=H,
        attempt_inventory=H,
        controller_reconciliation=H,
        resource_report=H,
        last_response_utc=world.clock.utc(),
    )
    assert result["disposition"] == "CLOSED_OBSERVATIONAL"
    assert (
        gate.records.get(gate.binding_hash, "observation_binding")[
            "continuous_service_state"
        ]
        == "NOT_VERIFIED"
    )


def test_real_gate_algorithms_end_to_end_with_only_synthetic_authorities(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_planning as planning
    from test_stage12_b2_publication import publish_world

    world = World(tmp_path)
    gate, pre, nonce, state = gate_fixture(world)
    world.gate = gate
    world.window_hash = gate.window_hash
    window = gate.records.get(gate.window_hash, "window_plan")
    world.selection_hash = planning.bind_window(
        world.records,
        window["calibration_plan_sha256"],
        gate.window_hash,
        owner=lambda: None,
        secret_guard=lambda raw: None,
    )
    gate.selection_hash = world.selection_hash
    report, inputs = world.run()
    assert (
        report["report_complete"]
        and report["service_evidence_state"] == "CLOSED_OBSERVATIONAL"
    )
    expected, validate, _ = publish_world(
        world, inputs, tmp_path / "segment", tmp_path / "published"
    )
    assert expected and (tmp_path / "published/_COMMITTED").exists()

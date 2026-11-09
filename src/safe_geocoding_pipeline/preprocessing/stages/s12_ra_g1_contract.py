"""Public RA-G1 successor with exact logical resource and observation schemas."""

from __future__ import annotations

from typing import Any, Callable, cast
from copy import deepcopy
import json
from . import s12_public_operations as old
from . import s12_retrieval_contract as c
from . import s12_probe as probe
from . import s12_ra_g1_assurance as assurance
import sys

AP_ENABLED = True
M2_ENABLED = False
RA_ENABLED = True
LOGICAL_SCRATCH = True
PAGED_HISTORY = True

SCOPE = old.SCOPE
PROFILE = "stage12_transport_operations_ra_g1_v1"
PLAN = "stage12_public_characterization_plan_ra_g1_v1"
START = "stage12_public_operations_campaign_ra_g1_v1"
EVENT = "stage12_public_controller_event_ra_g1_v1"
REPORT = "stage12_public_characterization_report_ra_g1_v1"
SNAPSHOT = "stage12_public_recovery_snapshot_ra_g1_v1"
POLICY_VERSION = "stage12_public_sampling_policy_ra_g1_v1"
BOUND = "stage12_resource_assurance_binding_ra_g1_v1"
OBSERVATION = "stage12_public_resource_observation_ra_g1_v1"
SEED = "stage12_public_sampling_seed_ra_g1_v1"
TIMING = "stage12_public_path_timing_ra_g1_v1"
CONFIG = "stage12_public_sampling_runtime_configuration_ra_g1_v1"
CONTROL_BEGIN, CONTROL_FINISH = old.CONTROL_BEGIN, old.CONTROL_FINISH
RULE_BUNDLE = "19b3d57a8bd6963ad6a5b43d83b05173abff5f35fd64bc88a180ec571a7e4c8e"
RESERVATION, MEMORY, MAX_U = old.RESERVATION, old.MEMORY, old.MAX_U
require, uint, checked, digest = old.require, old.uint, old.checked, old.digest
interval, rate_le, budget = old.interval, old.rate_le, old.budget
manifest_digest, verify_work_manifest = old.manifest_digest, old.verify_work_manifest
FAILURES = old.FAILURES
fields, enum = old.fields, old.enum

POLICY = {
    "additional_sampling_threads": 0,
    "cadence_ms": 50,
    "logical_serialization_scratch_bytes": 65536,
    "fresh_terminal_event_reserve_per_segment": 4,
    "logical_component_memory_bytes": 16777216,
    "maximum_acquisition_gap_ms": 100,
    "maximum_event_wire_bytes": 4096,
    "maximum_hard_traces": 4,
    "maximum_inventory_entry_bytes": 512,
    "maximum_observation_wire_bytes": 2048,
    "maximum_original_copies_per_event": 2,
    "maximum_outstanding_bytes": 65536,
    "maximum_outstanding_observations": 16,
    "maximum_pending_drain_event_liability": 36,
    "maximum_periodic_pairs_per_turn": 1,
    "maximum_periodic_traces": 16,
    "maximum_retained_inventory_versions_per_segment": 8,
    "maximum_sampler_close_ms": 5000,
    "maximum_unacknowledged_age_ms": 500,
    "minimum_ready_hard_actions_between_pairs": 1,
    "monitoring_mode": "PUBLIC_GAPS_ONLY",
    "reserved_bytes_per_observation": 4096,
    "schema_version": "stage12_public_sampling_policy_ra_g1_v1",
    "scope": "PUBLIC_SYNTHETIC_ONLY",
    "supplementary_chunk_bytes": 32768,
    "supplementary_chunk_files": 2980,
    "supplementary_chunk_rows": 56,
    "supplementary_ring_rows": 4096,
    "writer_guard_ms": 5000,
}
POLICY.update(
    {
        "assurance_method": assurance.METHOD,
        "supplementary_header_bytes": 4096,
        "supplementary_row_bytes": 512,
        "supplementary_interval_ms": 5000,
        "supplementary_phase_gated": 1,
        "resource_monitor_period_ms": 500,
        "resource_monitor_maximum_gap_ms": 1000,
    }
)
BUNDLE = {
    "bundle_version": "stage12_ra_g1_rule_bundle_v1",
    "adopted_selection": "RA-G1-r1",
    "owner_reviewed_source_documents": {
        "AMENDMENT_DRAFT.md": "67f52d460db7d02d1c810f836b2f48e19667a7aa9d2cf4ad0ae48c21ae0cc446",
        "SCHEMA_AND_INTERFACE_SPEC.md": "193c6b749af1981e20b829a6d25d07103966e0bbffeb07c5e38ed895f5a32e25",
        "CONTINUATION_PLAN.md": "e0e2cbb8c5b43aa986551215fdd9f79c97f28b0ad94ac9508041e60c87ac47a1",
        "ACCEPTANCE_SPEC.md": "b46b7dbf023925760cf0a6a2cf979aa005f3514ba1b64dfacb6f0479f6390e3d",
        "BUNDLED_DECISION_AND_MANDATE_PROPOSED.md": "dfffb63972a5015eb5d4fc71fccf353a9e4c3e9e7f07fb2bc848df69de56b19c",
    },
    "historical_strict_family_unchanged": True,
    "native_maximum": "NOT_PROVEN",
    "physical_capacity": "NOT_RESERVED_OR_PROVEN",
}
RULE_BUNDLE = digest(BUNDLE)
POLICY_SHA = digest(POLICY)
TYPES: dict[str, Any] = deepcopy(old.TYPES)
TYPES["Resources"] = fields(
    "application_admission_memory_bytes:P requested_memory_bytes:P logical_process_overhead_bytes:P logical_pending_request_bytes:P per_attempt_logical_write_ceiling_bytes:P fixed_campaign_logical_write_ceiling_bytes:P task_logical_write_ceiling_bytes:P resource_selection_sha256:D initial_capacity_observation_sha256:D resource_review_sha256:D scheduler_guard_ms:P writer_guard_ms:P"
)
TYPES["HardState"] = fields(
    "connection_slots:U admitted_operations:U pending_count:U pending_bytes:U reserved_bytes:U selected_state_id:ID"
)
TYPES["QuiescentCut"] = fields(
    "campaign_start_sha256:D profile_sha256:D segment_id:ID epoch_id:N32 at_mono_ns:U last_prior_acquisition_seq:U prior_acquisition_head_sha256:D prior_association_head_sha256:D prefix_last_event_seq:ID prefix_last_event_sha256:D last_witness_reopened_mono_ns:U? resource_revision:U"
)
TYPES["ResourceObservation"] = fields(
    "schema_version:="
    + OBSERVATION
    + " campaign_start_sha256:D segment_id:ID epoch_id:N32 acquisition_seq:ID previous_observation_sha256:D role:Role acquire_enter_ns:U occupied_count_after_reserve:P occupied_bytes_after_reserve:P free_query_start_ns:U free_query_end_ns:U observed_mono_ns:U acquire_exit_ns:U resource_revision:U state:HardState free_allocated_disk_bytes:U cut:QuiescentCut?"
)
TYPES["Role"] = enum("REGULAR", "FINAL")
TYPES["SamplingFailure"] = enum(
    *"ACQUISITION_GAP OBSERVATION_COUNT_LIMIT OBSERVATION_BYTE_LIMIT OBSERVATION_EVENT_LIMIT OBSERVATION_STORAGE_LIMIT ACK_AGE_LIMIT ACQUISITION_FAILED CLOCK_INVALID OWNER_FAILED SOURCE_CHANGED WRITE_UNCERTAIN READBACK_FAILED ACK_UNCERTAIN DRAIN_EXPIRED MISSING_TERMINAL SCHEMA_INCOMPATIBLE ORDER_INVALID".split()
)
TYPES["SamplingBudget"] = fields(
    "maximum_segments:P maximum_observations:P maximum_inventory_versions_per_segment:P additional_event_tokens:P additional_file_data_bytes:P additional_file_entries:P"
)
TYPES["HistoryLimits"] = fields(
    "maximum_entries:P maximum_name_bytes:P maximum_total_name_bytes:P page_entries:P maximum_depth:P maximum_file_bytes:P"
)
TYPES["BoundComponent"] = {
    **fields("bound_bytes:U evidence_sha256:D"),
    "name": enum(
        *"SLOT_ARENA INDEX_METADATA SERIALIZATION_SCRATCH PYTHON_ALLOCATOR NATIVE_HASH_IO ADDITIONAL_STACK OTHER_RETAINED".split()
    ),
    "basis": enum("STATIC_MAXIMUM", "ENFORCED_ALLOCATION_LIMIT", "NOT_USED"),
}
TYPES["SamplingSummary"] = fields(
    "policy_sha256:D seed_sha256:D open_event_seq:ID? close_event_seq:ID? anchor_mono_ns:U? end_observed_mono_ns:U? last_reserved_seq:Count acquired:Count appended:Count acknowledged:Count witnessed:Count reopened:Count maximum_gap_ns:U? gap_count:Count maximum_ack_age_ns:U? missing_observation_count:Count missing_ack_count:Count maximum_outstanding_count:U? maximum_outstanding_bytes:U? acquisition_head_sha256:D? association_head_sha256:D? failure:SamplingFailure? complete:B"
)
TYPES["BlockReport"] = {**TYPES["BlockReport"], "sampling": "SamplingSummary"}
TYPES["ReportReason"]["enum"].append("SAMPLING_INCOMPLETE")
SCHEMAS: dict[str, Any] = {}
for new, prior in [
    (PROFILE, old.PROFILE),
    (PLAN, old.PLAN),
    (START, old.START),
    (REPORT, old.REPORT),
    (SNAPSHOT, old.SNAPSHOT),
]:
    SCHEMAS[new] = deepcopy(old.SCHEMAS[prior])
    SCHEMAS[new]["schema_version"] = "=" + new
SCHEMAS[PROFILE].pop("resource_sample_period_ms")
SCHEMAS[PROFILE].update(
    fields("sampling_policy_sha256:D sampling_runtime_bound_sha256:D")
)
SCHEMAS[PLAN]["sampling_budget"] = "SamplingBudget"
SCHEMAS[PLAN]["history_limits"] = "HistoryLimits"
SCHEMAS[START]["sampling_policy_sha256"] = "D"
SCHEMAS[REPORT]["sampling_segments"] = "SamplingSummary[]"
SCHEMAS[SNAPSHOT].update(
    fields(
        "sampling_policy_sha256:D sampling_close_event_sha256:D? sampling:SamplingSummary"
    )
)
BODIES: dict[str, Any] = deepcopy(old.EVENT_BODIES)
BODIES["RESOURCE"]["cause"]["enum"].remove("PERIODIC")
BODIES["RESOURCE"].update(
    fields("state_revision:U mutation:B mutation_mono_ns:U? selected_state_id:ID")
)
BODIES.update(
    {
        "SAMPLING_OPEN": fields(
            "policy_sha256:D seed_sha256:D anchor_event_seq:ID anchor_event_sha256:D anchor_mono_ns:U baseline:HardState"
        ),
        "RESOURCE_SAMPLE": fields(
            "observation:ResourceObservation observation_sha256:D"
        ),
        "SAMPLE_ACK": fields(
            "acquisition_seq:ID observation_sha256:D sample_event_seq:ID sample_event_sha256:D event_ack_mono_ns:U"
        ),
        "SAMPLING_FAULT": {
            **fields(
                "code:SamplingFailure at_mono_ns:U reserved_seq:ID? trigger_sample_event_seq:ID?"
            ),
            "stage": enum(
                *"RESERVE ACQUIRE ENQUEUE APPEND READBACK ACK DRAIN REOPEN".split()
            ),
        },
        "SAMPLING_CLOSE": {
            **fields(
                "policy_sha256:D seed_sha256:D close_requested_mono_ns:U producer_closed_mono_ns:U? cut_mono_ns:U? final_acquisition_seq:ID? final_observed_mono_ns:U? last_reserved_seq:Count acquired:Count appended:Count acknowledged:Count witnessed:Count acquisition_head_sha256:D? association_head_sha256:D? failure:SamplingFailure?"
            ),
            "result": enum("COMPLETE", "INCOMPLETE"),
        },
    }
)
HEADER = {
    k: v
    for k, v in next(
        iter(cast(dict[str, Any], old.SCHEMAS)[old.EVENT]["variants"].values())
    ).items()
    if k not in ("kind", "body")
}
HEADER["schema_version"] = "=" + EVENT
SCHEMAS[EVENT] = {
    "tag": "kind",
    "variants": {k: {**HEADER, "kind": "=" + k, "body": v} for k, v in BODIES.items()},
}
SCHEMAS[OBSERVATION] = TYPES["ResourceObservation"]
SCHEMAS[SEED] = fields(
    "schema_version:="
    + SEED
    + " campaign_start_sha256:D profile_sha256:D segment_id:ID epoch_id:N32"
)
SCHEMAS[POLICY_VERSION] = {
    k: ("=" + v if type(v) is str else "U") for k, v in POLICY.items()
}
SCHEMAS[BOUND] = deepcopy(assurance.SCHEMA)
for _version in (PROFILE, START, REPORT, SNAPSHOT):
    SCHEMAS[_version]["sampling_assurance_method"] = "=" + assurance.METHOD


def assurance_fields() -> Any:
    return {"sampling_assurance_method": assurance.METHOD}


def validate_type(value: Any, spec: Any) -> Any:
    if isinstance(spec, str):
        if spec.endswith("?"):
            if value is not None:
                validate_type(value, spec[:-1])
        elif spec.endswith("[]"):
            require(type(value) is list)
            for row in value:
                validate_type(row, spec[:-2])
        elif spec in TYPES:
            validate_type(value, TYPES[spec])
        else:
            old.validate_type(value, spec)
    elif "array" in spec:
        require(type(value) is list and len(value) == len(spec["array"]))
        for cell, kind in zip(value, spec["array"], strict=True):
            validate_type(cell, kind)
    elif "enum" in spec:
        require(type(value) is str and value in spec["enum"])
    elif "tag" in spec:
        require(type(value) is dict and value.get(spec["tag"]) in spec["variants"])
        validate_type(value, spec["variants"][value[spec["tag"]]])
    else:
        require(type(value) is dict and set(value) == set(spec))
        for k, t in spec.items():
            validate_type(value[k], t)
    if spec == "Count":
        require(value["value"] is None or value["value"] == value["confirmed_min"])


def validate(value: Any, version: Any) -> Any:
    if version == BOUND:
        assurance.shape(value, assurance.SCHEMA)
        return
    if version in (CONTROL_BEGIN, CONTROL_FINISH):
        return old.validate(value, version)
    require(version in SCHEMAS)
    validate_type(value, SCHEMAS[version])
    if version == POLICY_VERSION:
        require(value == POLICY)
    if version == OBSERVATION:
        require(len(c.canonical(value)) <= 2048)
        require(
            [
                value[k]
                for k in (
                    "acquire_enter_ns",
                    "free_query_start_ns",
                    "free_query_end_ns",
                    "observed_mono_ns",
                    "acquire_exit_ns",
                )
            ]
            == sorted(
                value[k]
                for k in (
                    "acquire_enter_ns",
                    "free_query_start_ns",
                    "free_query_end_ns",
                    "observed_mono_ns",
                    "acquire_exit_ns",
                )
            )
        )
        require(
            value["occupied_count_after_reserve"] <= 16
            and value["occupied_bytes_after_reserve"]
            == value["occupied_count_after_reserve"] * 4096
        )
        require((value["role"] == "FINAL") == (value["cut"] is not None))
    if version == EVENT:
        require(len(c.canonical(value)) <= 4096)


def parse(raw: Any, version: Any) -> Any:
    def pairs(items: Any) -> Any:
        require(len({k for k, _ in items}) == len(items))
        return dict(items)

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
        require(c.canonical(value) == raw)
        validate(value, version)
        return value
    except (ValueError, UnicodeError, TypeError):
        raise c.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID") from None


def validate_profile(profile: Any) -> None:
    validate(profile, PROFILE)
    require(profile["rule_bundle_sha256"] == RULE_BUNDLE)
    from . import s12_assets, s12_operations, s12_response

    baseline = s12_assets.hashes()
    require(
        profile["preserved"]
        == {
            "operations_v1_sha256": baseline[s12_operations.VERSION].hex(),
            "materialization_sha256": baseline[c.MATERIALIZATION].hex(),
            "response_validation_sha256": baseline[s12_response.VALIDATION].hex(),
            "public_audit_source_sha256": "b43134525b99b60767d9661d334ccf743d101f06e85be42350483048a1c9d8f4",
        }
    )
    allowance, resources = profile["operator_allowance"], profile["resources"]
    require(
        allowance["connections"] <= 4
        and allowance["valid_from"] < allowance["valid_until"]
    )
    require(
        resources["requested_memory_bytes"]
        >= checked(
            resources["application_admission_memory_bytes"]
            + resources["logical_pending_request_bytes"]
            + resources["logical_process_overhead_bytes"]
        )
    )
    require(bool(profile["states"]))
    prior = None
    for i, state in enumerate(profile["states"], 1):
        require(
            state["state_id"] == i
            and 1
            <= state["admitted_operations"]
            <= state["connections"]
            <= allowance["connections"]
        )
        require(
            checked(state["admitted_operations"] * RESERVATION)
            <= resources["application_admission_memory_bytes"]
        )
        require(rate_le(state["rate"], allowance["rate_ceiling"]))
        if prior:
            require(rate_le(prior, state["rate"]) and prior != state["rate"])
        prior = state["rate"]
        if profile["monitoring"]["mode"] == "FROZEN_V1":
            require(state["admitted_operations"] >= 2)
    if profile["monitoring"]["mode"] == "FROZEN_V1":
        require(
            10_000 + resources["scheduler_guard_ms"] + resources["writer_guard_ms"]
            < 60_000
        )
    require(
        profile["sampling_policy_sha256"] == POLICY_SHA
        and profile["sampling_assurance_method"] == assurance.METHOD
    )
    require(
        resources["requested_memory_bytes"] == 6 * 2**30
        and resources["logical_process_overhead_bytes"] >= 16777216
        and resources["writer_guard_ms"] == 5000
    )
    require(profile["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY")


def validate_plan(plan: Any, profile: Any) -> None:
    validate_profile(profile)
    validate(plan, PLAN)
    require(plan["operations_profile_sha256"] == digest(profile))
    require(plan["fixture_inventory_sha256"] == digest(probe.fixtures()))
    a, r = profile["operator_allowance"], profile["resources"]
    require(
        a["valid_from"] <= plan["window_start"] < plan["window_end"] <= a["valid_until"]
    )
    budget(plan["budgets"])
    b = plan["budgets"]
    require(b["storage_bytes"] <= r["task_logical_write_ceiling_bytes"])
    require(
        r["task_logical_write_ceiling_bytes"]
        >= checked(
            r["fixed_campaign_logical_write_ceiling_bytes"]
            + (b["data_attempts"] + b["control_http_attempts"])
            * r["per_attempt_logical_write_ceiling_bytes"]
        )
    )
    require(
        plan["shutdown_reserve_ms"]
        >= 60_000
        + r["scheduler_guard_ms"]
        + r["writer_guard_ms"]
        + (10_000 if profile["monitoring"]["mode"] == "FROZEN_V1" else 0)
    )
    require(plan["shutdown_reserve_ms"] < b["active_duration_ms"])
    recipes = plan["control_recipes"]
    require(
        [x["recipe_id"] for x in recipes]
        == sorted(set(x["recipe_id"] for x in recipes))
    )
    for recipe in recipes:
        require(
            recipe["max_http_attempts_per_invocation"] <= 5
            and recipe["max_duration_ms"] <= 60_000
        )
        require(
            recipe["transport_profile_sha256"] == profile["transport_profile_sha256"]
        )
    if profile["monitoring"]["mode"] == "FROZEN_V1":
        for field, purpose in (
            ("refresh_recipe_id", "IDENTITY_REFRESH"),
            ("closure_recipe_id", "IDENTITY_CLOSURE"),
        ):
            recipe = next(
                (x for x in recipes if x["recipe_id"] == profile["monitoring"][field]),
                None,
            )
            require(
                recipe is not None
                and recipe["purpose"] == purpose
                and recipe["max_duration_ms"] <= 10_000
            )
    require(bool(plan["blocks"]))
    seen: set[int] = set()
    for i, block in enumerate(plan["blocks"], 1):
        require(
            block["block_id"] == i
            and block["transition_from"] == (i - 1 if i > 1 else None)
        )
        require(block["state_id"] <= len(profile["states"]))
        state = profile["states"][block["state_id"] - 1]
        budget(block["budget"])
        for ids in (block["observation_ids"], block["reserved_control_ids"]):
            require(ids == sorted(set(ids)) and not seen.intersection(ids))
            seen.update(ids)
        fallbacks = block["fallback_state_ids"]
        require(fallbacks == sorted(set(fallbacks), reverse=True))
        previous = state
        for sid in fallbacks:
            require(sid < previous["state_id"])
            lower = profile["states"][sid - 1]
            require(
                lower["connections"] <= previous["connections"]
                and lower["admitted_operations"] <= previous["admitted_operations"]
            )
            previous = lower
        criteria = block["criteria"]
        require((criteria is None) == (block["evaluation"] == "EXPLORATORY"))
        if criteria is not None:
            require(
                plan["capability_parent_sha256"] is not None
                or plan["experiment_kind"] == "CAPABILITY"
            )
            require(
                criteria["min_duration_ms"]
                <= criteria["max_duration_ms"]
                <= block["budget"]["active_duration_ms"]
            )
            require(criteria["min_valid_data"] <= block["budget"]["data_observations"])
            require(
                rate_le(criteria["min_attempt_rate"], state["rate"])
                and rate_le(criteria["min_durable_data_rate"], state["rate"])
            )
            cells = [(x["mode"], x["size"]) for x in criteria["required_cells"]]
            require(
                cells == sorted(set(cells)) and all(size <= 40 for _, size in cells)
            )
            require(
                criteria["max_pending_count"] <= 2 * state["admitted_operations"]
                and criteria["max_pending_bytes"] <= r["logical_pending_request_bytes"]
                and criteria["max_reserved_bytes"]
                <= r["application_admission_memory_bytes"]
            )
    for key in b:
        require(checked(sum(x["budget"][key] for x in plan["blocks"])) <= b[key])
    from .s12_paged_history import validate_limits

    cast(Callable[..., Any], validate_limits)(plan["history_limits"])
    b = plan["sampling_budget"]
    segments = b["maximum_segments"]
    a = (plan["budgets"]["active_duration_ms"] + 49) // 50 + 2 * segments
    f, inventories = 4 * a + 8 * segments, 8 * segments
    require(
        b["maximum_inventory_versions_per_segment"] <= 8
        and b["maximum_observations"] >= a
    )
    require(
        b["additional_event_tokens"] >= checked(2 * a + 4 * segments)
        and b["additional_event_tokens"] < plan["budgets"]["event_count"]
    )
    require(
        b["additional_file_data_bytes"]
        >= checked(4096 * f + inventories * (512 * f + 4096))
        and b["additional_file_data_bytes"] < plan["budgets"]["storage_bytes"]
    )
    require(b["additional_file_entries"] >= checked(f + inventories))


def validate_bound(record: Any, profile: Any, start: Any) -> Any:
    assurance.validate_record(record, profile, start, sys.modules[__name__])


def verify_authorities(profile: Any, plan: Any, start: Any, authority: Any) -> Any:
    validate_plan(plan, profile)
    validate(start, START)
    require(
        start["profile_sha256"] == digest(profile)
        and start["plan_sha256"] == digest(plan)
        and start["sampling_policy_sha256"] == POLICY_SHA
        and start["rule_bundle_sha256"] == RULE_BUNDLE
        and start["policy_freeze_record_sha256"]
        == profile["policy_freeze_record_sha256"]
    )
    require(
        authority is not None and callable(getattr(authority, "sampling_bound", None))
    )
    record = authority.sampling_bound(profile, start)
    validate_bound(record, profile, start)
    context = {"profile": profile, "plan": plan, "start": start}
    assurance.verify_runtime(record, authority, context)
    for field in (
        "policy_freeze_record_sha256",
        "implementation_authorization_sha256",
        "implementation_review_sha256",
        "initial_workload_authority_sha256",
    ):
        authority.require(field, start[field], context)
    authority.require(
        "sampling_runtime_bound", profile["sampling_runtime_bound_sha256"], context
    )
    authority.require(
        "sampling_bound_review", record["technical_review_sha256"], record
    )
    for field, h, value in [
        ("operator_allowance", profile["operator_allowance"]["record_sha256"], profile),
        ("transport_profile", profile["transport_profile_sha256"], profile),
        ("plan_selection", plan["selection_basis_sha256"], plan),
        (
            "resources",
            profile["resources"]["resource_review_sha256"],
            profile["resources"],
        ),
        (
            "monitoring",
            profile["monitoring"]["gaps_record_sha256"],
            profile["monitoring"],
        ),
    ]:
        authority.require(field, h, value)
    for row in profile["states"]:
        authority.require("rate_state", row["evidence_sha256"], row)
    for row in plan["control_recipes"]:
        authority.require("control_recipe", row["implementation_contract_sha256"], row)


def descriptors() -> Any:
    result = {
        name: {
            "descriptor_version": name,
            "scope": SCOPE,
            "rule_bundle_sha256": RULE_BUNDLE,
            "closed": True,
            "schema": spec,
            "named_types": TYPES,
            "live_instance": False,
        }
        for name, spec in SCHEMAS.items()
    }
    result[POLICY_VERSION] = deepcopy(POLICY)
    result["stage12_ra_g1_rule_bundle_v1"] = deepcopy(BUNDLE)
    from . import s12_public_runtime as runtime

    result[CONFIG] = {
        "descriptor_version": CONFIG,
        "scope": SCOPE,
        "rule_bundle_sha256": RULE_BUNDLE,
        "closed": True,
        "outer_fields": sorted(
            runtime.FIELDS
            | {"capability", "resource_execution", "representative_validation_sha256"}
        ),
        "nested_profile": PROFILE,
        "nested_plan": PLAN,
        "live_instance": False,
    }
    result[BOUND]["scope"] = list(assurance.SCOPES)
    result[assurance.POLICY] = {
        "descriptor_version": assurance.POLICY,
        "method": assurance.METHOD,
        "normative_documents": deepcopy(BUNDLE["owner_reviewed_source_documents"]),
        "logical_component_ceiling_bytes": assurance.LOGICAL_BYTES,
        "logical_scratch_ceiling_bytes": assurance.SCRATCH_BYTES,
        "minimum_other_logical_bytes": assurance.MIN_OTHER_LOGICAL,
        "adopted_scope_ceilings": deepcopy(assurance.SCOPE_CEILINGS),
        "scope": list(assurance.SCOPES),
        "live_instance": False,
        "native_component_guarantee": "NOT_CLAIMED",
        "job_domain_guarantee": "NOT_ESTABLISHED",
        "physical_capacity_guarantee": "NOT_RESERVED_OR_PROVEN",
    }
    for name, spec in (
        (assurance.SELECTION, assurance.SELECTION_SCHEMA),
        (assurance.CAPACITY, assurance.CAPACITY_SCHEMA),
        (assurance.CURRENT, assurance.FACTS),
        (assurance.RISK, assurance.RISK_SCHEMA),
    ):
        result[name] = {
            "descriptor_version": name,
            "closed": True,
            "schema": spec,
            "live_instance": False,
        }

    from . import s12_ra_g1_monitor as monitor
    from . import s12_ra_g1_execution as execution

    for name, spec in monitor.SCHEMAS.items():
        result[name] = {
            "descriptor_version": name,
            "closed": True,
            "schema": spec,
            "maximum_canonical_bytes": 8192,
            "live_instance": False,
        }
    result[execution.ADMIN_BINDING] = {
        "descriptor_version": execution.ADMIN_BINDING,
        "closed": True,
        "schema": execution.ADMIN_BINDING_SCHEMA,
        "maximum_canonical_bytes": 8192,
        "resource_only": True,
        "live_instance": False,
    }
    result[execution.EXECUTION_REQUEST] = {
        "descriptor_version": execution.EXECUTION_REQUEST,
        "closed": True,
        "schema": {
            "schema_version": "=" + execution.EXECUTION_REQUEST,
            "supervisor_context_path": "PATH",
            "supervisor_context_sha256": "D",
        },
        "live_instance": False,
    }
    result[execution.SUPERVISOR_CONTEXT] = {
        "descriptor_version": execution.SUPERVISOR_CONTEXT,
        "closed": True,
        "schema": execution.SUPERVISOR_SCHEMA,
        "maximum_canonical_bytes": 65536,
        "context_excludes_future_config_and_binding_hashes": True,
        "live_instance": False,
    }
    from . import s12_ra_g1_accounting as accounting

    for bootstrap_successor in (False, True):
        version = accounting.BOOTSTRAP_VERSION if bootstrap_successor else accounting.VERSION
        result[version] = accounting.descriptor(bootstrap_successor=bootstrap_successor)
    result[accounting.BOOTSTRAP_VERSION] = accounting.descriptor(bootstrap_successor=True)
    result[assurance.BOOTSTRAP_POLICY] = assurance.bootstrap_policy_descriptor()
    for version, spec in ((assurance.BOOTSTRAP_SELECTION, assurance.BOOTSTRAP_SELECTION_SCHEMA),
                          (assurance.BOOTSTRAP_ADOPTION, assurance.BOOTSTRAP_ADOPTION_SCHEMA)):
        result[version] = dict(descriptor_version=version, closed=True, schema=spec,
                               maximum_canonical_bytes=8192, live_instance=False)
    return result


COUNT_KEYS = old.COUNT_KEYS

work_rows = old.work_rows

ASYNC_FIELDS = fields(
    "phase_id:P segment_id:ID epoch_id:N32 acquisition_seq:ID observation_sha256:D? role:Role resource_revision:U? future_used:B outcome:TimingOutcome acquire_enter_ns:U reserved_ns:U free_query_start_ns:U? free_query_end_ns:U? safety_wait_start_ns:U? safety_acquired_ns:U? observed_ns:U? acquire_exit_ns:U? enqueued_ns:U? writer_entry_ns:U? sample_event_seq:ID? sample_event_sha256:D? sample_header_ns:U? append_complete_ns:U? event_ack_publish_ns:U? ack_event_seq:ID? ack_event_sha256:D? ack_witness_header_ns:U? ack_witness_reopened_ns:U? pair_action_return_ns:U? pair_post_action_complete_ns:U? future_finished_observed_ns:U? credit_released_ns:U?"
)
TYPES["TimingOutcome"] = enum("COMPLETE", "FAILED", "CANCELLED", "UNCERTAIN")
TYPES["LegacyTimingRow"] = {
    "array": ["P", enum("START_RESERVE"), "TimingOutcome"] + ["U?"] * 24
}
# HARD_SYNC's fixed array is additionally checked by the unchanged legacy decoder.
TIMING_SCHEMA = {
    "tag": "row_kind",
    "variants": {
        "PERIODIC_ASYNC": {"row_kind": "=PERIODIC_ASYNC", **ASYNC_FIELDS},
        "HARD_SYNC": fields("row_kind:=HARD_SYNC legacy_row:LegacyTimingRow"),
    },
}


def validate_timing(value: Any) -> Any:
    if type(value) is dict and value.get("row_kind") == "HARD_SYNC":
        require(set(value) == {"row_kind", "legacy_row"})
        from .s12_public_checkpoints import _public_row

        row = cast(Callable[..., Any], _public_row)(value["legacy_row"])
        require(row[1] == "START_RESERVE")
        return
    validate_type(value, TIMING_SCHEMA)
    names = [
        "acquire_enter_ns",
        "reserved_ns",
        "free_query_start_ns",
        "free_query_end_ns",
        "safety_wait_start_ns",
        "safety_acquired_ns",
        "observed_ns",
        "acquire_exit_ns",
        "enqueued_ns",
        "writer_entry_ns",
        "sample_header_ns",
        "append_complete_ns",
        "event_ack_publish_ns",
        "ack_witness_header_ns",
        "ack_witness_reopened_ns",
        "pair_action_return_ns",
        "pair_post_action_complete_ns",
        "credit_released_ns",
    ]
    times = [value[k] for k in names if value[k] is not None]
    require(times == sorted(times))
    if value["outcome"] == "COMPLETE":
        require(
            all(
                value[k] is not None
                for k in ASYNC_FIELDS
                if k != "future_finished_observed_ns"
            )
        )
        require(
            (value["future_finished_observed_ns"] is not None) == value["future_used"]
        )
    if not value["future_used"]:
        require(value["future_finished_observed_ns"] is None)


def resources_view(profile: Any) -> Any:
    """Internal application ledger numbers; never an old Resources record."""
    value = profile["resources"]
    validate_type(value, TYPES["Resources"])
    return {
        "admission_memory_bytes": value["application_admission_memory_bytes"],
        "pending_request_bytes": value["logical_pending_request_bytes"],
        "process_overhead_bytes": value["logical_process_overhead_bytes"],
        "per_attempt_disk_bound_bytes": value[
            "per_attempt_logical_write_ceiling_bytes"
        ],
        "fixed_campaign_disk_bound_bytes": value[
            "fixed_campaign_logical_write_ceiling_bytes"
        ],
        "allocated_disk_bytes": value["task_logical_write_ceiling_bytes"],
        "scheduler_guard_ms": value["scheduler_guard_ms"],
        "writer_guard_ms": value["writer_guard_ms"],
    }

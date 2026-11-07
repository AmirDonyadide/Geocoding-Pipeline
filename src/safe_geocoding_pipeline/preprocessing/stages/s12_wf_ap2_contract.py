"""WF-AP2 public successor: T3 telemetry and exclusive M2 job assurance.

Derived from the preserved AP-1 mechanics; no old descriptor bytes or strict
assurance records are reinterpreted. New records are opt-in and fail closed.
"""

from __future__ import annotations
from copy import deepcopy
import json
from . import s12_public_operations as old
from . import s12_retrieval_contract as c
from . import s12_wf_ap2_assurance as assurance
import sys

AP_ENABLED = True
M2_ENABLED = True
PAGED_HISTORY = True

SCOPE = old.SCOPE
PROFILE = "stage12_transport_operations_v4"
PLAN = "stage12_public_characterization_plan_v3"
START = "stage12_public_operations_campaign_v3"
EVENT = "stage12_public_controller_event_v3"
REPORT = "stage12_public_characterization_report_v3"
SNAPSHOT = "stage12_public_recovery_snapshot_v3"
POLICY_VERSION = "stage12_public_sampling_policy_v2"
BOUND = "stage12_public_sampling_runtime_bound_v2"
OBSERVATION = "stage12_public_resource_observation_v1"
SEED = "stage12_public_sampling_seed_v1"
TIMING = "stage12_public_path_timing_v3"
CONFIG = "stage12_public_sampling_runtime_configuration_v2"
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
    "schema_version": "stage12_public_sampling_policy_v2",
    "scope": "PUBLIC_SYNTHETIC_ONLY",
    "supplementary_chunk_bytes": 32768,
    "supplementary_chunk_files": 1500,
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
        "maximum_job_domain_bytes": assurance.MAX_JOB_BYTES,
        "maximum_job_swap_bytes": 0,
    }
)
BUNDLE = {
    "bundle_version": "stage12_wf_ap2_rule_bundle_v1",
    "adopted_selection": "T3_M2_P1a_RS1_ACCEPTANCE_GRAPH",
    "owner_reviewed_source_documents": {
        "BUNDLED_OWNER_DECISION_PROPOSED.md": "e5177a1476e5a660d53c053e2710e1706d778877998bba79ef3d5f395325fd0a",
        "RS1_ACCEPTANCE_GRAPH_SUCCESSOR_PROPOSED.md": "c15a0aabbf6e851c37452e02d5ebfebd96400a78da49bbfd7c8c61b5f0de5a85",
    },
    "historical_strict_family_unchanged": True,
}
RULE_BUNDLE = digest(BUNDLE)
POLICY_SHA = digest(POLICY)
TYPES = deepcopy(old.TYPES)
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
SCHEMAS = {}
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
BODIES = deepcopy(old.EVENT_BODIES)
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
    for k, v in next(iter(old.SCHEMAS[old.EVENT]["variants"].values())).items()
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


def assurance_fields():
    return {"sampling_assurance_method": assurance.METHOD}


def validate_type(value, spec):
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


def validate(value, version):
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


def parse(raw, version):
    def pairs(items):
        require(len({k for k, _ in items}) == len(items))
        return dict(items)

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
        require(c.canonical(value) == raw)
        validate(value, version)
        return value
    except (ValueError, UnicodeError, TypeError):
        raise c.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID") from None


def legacy_profile(profile):
    value = deepcopy(profile)
    for k in ("sampling_policy_sha256", "sampling_runtime_bound_sha256"):
        value.pop(k)
    value.pop("sampling_assurance_method")
    value.update(
        schema_version=old.PROFILE,
        rule_bundle_sha256=old.RULE_BUNDLE,
        resource_sample_period_ms=100,
    )
    return value


def legacy_plan(plan, profile):
    value = deepcopy(plan)
    value.pop("sampling_budget")
    value.pop("history_limits")
    value.update(
        schema_version=old.PLAN,
        operations_profile_sha256=digest(legacy_profile(profile)),
    )
    return value


def validate_profile(profile):
    validate(profile, PROFILE)
    require(
        profile["rule_bundle_sha256"] == RULE_BUNDLE
        and profile["sampling_policy_sha256"] == POLICY_SHA
    )
    require(
        profile["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY"
        and profile["resources"]["writer_guard_ms"] == 5000
        and profile["resources"]["process_overhead_bytes"] >= 16777216
    )
    old.validate_profile(legacy_profile(profile))


def validate_plan(plan, profile):
    validate_profile(profile)
    validate(plan, PLAN)
    from .s12_paged_history import validate_limits

    validate_limits(plan["history_limits"])
    require(plan["operations_profile_sha256"] == digest(profile))
    old.validate_plan(legacy_plan(plan, profile), legacy_profile(profile))
    b = plan["sampling_budget"]
    s = b["maximum_segments"]
    a = (plan["budgets"]["active_duration_ms"] + 49) // 50 + 2 * s
    f = 4 * a + 8 * s
    i = 8 * s
    require(
        b["maximum_inventory_versions_per_segment"] <= 8
        and b["maximum_observations"] >= a
    )
    require(
        b["additional_event_tokens"] >= checked(2 * a + 4 * s)
        and b["additional_event_tokens"] < plan["budgets"]["event_count"]
    )
    require(
        b["additional_file_data_bytes"] >= checked(4096 * f + i * (512 * f + 4096))
        and b["additional_file_data_bytes"] < plan["budgets"]["storage_bytes"]
    )
    require(b["additional_file_entries"] >= checked(f + i))


def validate_bound(record, profile, start):
    assurance.validate_record(record, profile, start, sys.modules[__name__])


def verify_authorities(profile, plan, start, authority):
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
        "sampling_bound_review", record["technical_review_record_sha256"], record
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
    if profile["resources"]["admission_memory_bytes"] != MEMORY:
        authority.require(
            "capacity_change",
            profile["resources"]["capacity_basis_sha256"],
            profile["resources"],
        )


def descriptors():
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
        if name not in (OBSERVATION, SEED)
    }
    result[POLICY_VERSION] = deepcopy(POLICY)
    result["stage12_wf_ap2_rule_bundle_v1"] = deepcopy(BUNDLE)
    from . import s12_public_runtime as runtime

    result[CONFIG] = {
        "descriptor_version": CONFIG,
        "scope": SCOPE,
        "rule_bundle_sha256": RULE_BUNDLE,
        "closed": True,
        "outer_fields": sorted(runtime.FIELDS | {"capability"}),
        "nested_profile": PROFILE,
        "nested_plan": PLAN,
        "live_instance": False,
    }
    result[BOUND]["scope"] = "EXPLICIT_PUBLIC_OR_DEVELOPMENT_METHOD_ONLY"
    result["stage12_wf_ap2_bound_review_v1"] = {
        "descriptor_version": "stage12_wf_ap2_bound_review_v1",
        "closed": True,
        "live_instance": False,
        "schema": {
            "version": "=stage12_wf_ap2_bound_review_v1",
            "scope": assurance.SCHEMA["scope"],
            "disposition": "=PASS",
            "bound_scope_sha256": "D",
            "reviewer_role_evidence_sha256": "D",
        },
        "subject_projection": "canonical runtime-bound record excluding only technical_review_record_sha256",
    }
    result["stage12_wf_ap2_public_review_binding_v1"] = {
        "descriptor_version": "stage12_wf_ap2_public_review_binding_v1",
        "closed": True,
        "scope": SCOPE,
        "live_instance": False,
        "schema": {
            "version": "=stage12_wf_ap2_public_review_binding_v1",
            "disposition": "=PASS",
            "configuration_sha256": "D",
            "report_sha256": "D",
            "source_files": [{"path": "S", "sha256": "D"}],
            "scope": "=" + SCOPE,
            "sampling_evidence": {
                key: ["D"]
                for key in (
                    "runtime_bounds",
                    "technical_reviews",
                    "enforcement",
                    "coverage",
                    "graphs",
                    "methods",
                    "logical",
                )
            },
        },
        "evidence_list_limit": 64,
        "source_paths": "relative reviewed code paths; no parent traversal; exact original bytes",
        "evidence_paths": "private sampling_evidence/<actual SHA256>.record; canonical closed records bound by independent review",
    }
    result["stage12_wf_ap2_enforcement_method_v1"] = {
        "descriptor_version": "stage12_wf_ap2_enforcement_method_v1",
        "method": assurance.METHOD,
        "live_instance": False,
        "current_fact_schema": assurance.FACTS,
        "UUID": "exact32 lowercase hex, kernel boot UUID with hyphens removed",
        "S": "ASCII string<=1024 bytes; domain restricted to canonical /sys/fs/cgroup hierarchy",
        "native_component_guarantee": "NOT_CLAIMED",
        "native_scratch_guarantee": "NOT_CLAIMED",
        "maximum_effective_job_memory_bytes": assurance.MAX_JOB_BYTES,
        "maximum_swap_bytes": 0,
        "required": [
            "actual complete reviewed job/descendant/namespace coverage",
            "no delegation or effective capabilities",
            "NoNewPrivs=1",
            "finite pids.max and all ancestors",
            "fresh actual membership and limit checks",
            "exact source/runtime/configuration and invocation graph",
            "separate RS1 native/physical/capacity obligations",
        ],
        "non_proofs": [
            "scheduler memory request",
            "memory.high",
            "RSS",
            "visible12GiB limit",
            "small successful transaction",
        ],
    }
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


def validate_timing(value):
    if type(value) is dict and value.get("row_kind") == "HARD_SYNC":
        require(set(value) == {"row_kind", "legacy_row"})
        from .s12_public_checkpoints import _public_row

        row = _public_row(value["legacy_row"])
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

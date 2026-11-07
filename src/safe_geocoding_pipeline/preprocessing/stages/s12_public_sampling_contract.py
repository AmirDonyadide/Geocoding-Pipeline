"""AP-1 closed public contracts. Old O-r2 descriptors are never mutated."""

from __future__ import annotations
from copy import deepcopy
import json
from . import s12_public_operations as old
from . import s12_retrieval_contract as c

SCOPE = old.SCOPE
PROFILE = "stage12_transport_operations_v3"
PLAN = "stage12_public_characterization_plan_v2"
START = "stage12_public_operations_campaign_v2"
EVENT = "stage12_public_controller_event_v2"
REPORT = "stage12_public_characterization_report_v2"
SNAPSHOT = "stage12_public_recovery_snapshot_v2"
POLICY_VERSION = "stage12_public_sampling_policy_v1"
BOUND = "stage12_public_sampling_runtime_bound_v1"
OBSERVATION = "stage12_public_resource_observation_v1"
SEED = "stage12_public_sampling_seed_v1"
TIMING = "stage12_public_path_timing_v2"
CONFIG = "stage12_public_sampling_runtime_configuration_v1"
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
    "combined_serialization_scratch_bytes": 65536,
    "fresh_terminal_event_reserve_per_segment": 4,
    "incremental_component_memory_bytes": 16777216,
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
    "schema_version": "stage12_public_sampling_policy_v1",
    "scope": "PUBLIC_SYNTHETIC_ONLY",
    "supplementary_chunk_bytes": 32768,
    "supplementary_chunk_files": 1500,
    "supplementary_chunk_rows": 128,
    "supplementary_ring_rows": 4096,
    "writer_guard_ms": 5000,
}
BUNDLE = {
    "baseline_contracts": [
        {
            "path": "docs/scientific_assets/stage12_public_characterization_plan_v1.json",
            "sha256": "ac411d0359e52ad59b17bed33ce707498801e1a4bc04548d7fb17bf70f10fb17",
        },
        {
            "path": "docs/scientific_assets/stage12_public_characterization_report_v1.json",
            "sha256": "c9c641b9480a21def4303a6b85cf9d34f217c81c662b4a015c1052753e30f5b9",
        },
        {
            "path": "docs/scientific_assets/stage12_public_controller_event_v1.json",
            "sha256": "a9288ca05efe2f270f468f559bf33ae932faf35a97c773be0cf428a1c9e435c1",
        },
        {
            "path": "docs/scientific_assets/stage12_public_observation_validation_v3.json",
            "sha256": "849a0863876b75dcef322a46d74c2558708cb8611046c8235869090cce621ae2",
        },
        {
            "path": "docs/scientific_assets/stage12_public_operations_campaign_v1.json",
            "sha256": "32412a9e9f5331212ef9533fccae04f850bb7a048b4ef4b55d8ee3672c436a1f",
        },
        {
            "path": "docs/scientific_assets/stage12_public_recovery_snapshot_v1.json",
            "sha256": "5c519d34475227a4a69b10bd8c2e2f0177210c047fa976d16d5470d61b021326",
        },
        {
            "path": "docs/scientific_assets/stage12_transport_operations_v2.json",
            "sha256": "e6abdcc85da3b5cca1bc8ed946688069b8b5eb42d26672e8e1d45f3af3ed0e63",
        },
        {
            "path": "docs/stages/STAGE12_DATA_CONTRACT.md",
            "sha256": "99b399cb77686a073feb22de736aedcc054ec35f241df84515f57ccba12cda41",
        },
        {
            "path": "docs/stages/STAGE12_DEVELOPMENT_CALIBRATION.md",
            "sha256": "56f315ba462829f815a41514bb6499abb8694f5a8323ba51397f1fe289eeb4ad",
        },
        {
            "path": "docs/stages/STAGE12_EXECUTION_CONTRACT.md",
            "sha256": "3e00babb3da80ad6d9db43d8dfb1af47d619b95fce656572a404731d8db936ca",
        },
        {
            "path": "docs/stages/STAGE12_PELIAS_TOPN_RETRIEVAL.md",
            "sha256": "18c62b499d0edd4e55f2a560cb7daeffb30e34bd20fa68b6df5a12ab9513c78c",
        },
        {
            "path": "frozen/O-r2/OPERATING_AMENDMENT_DRAFT.md",
            "sha256": "3dd9fec3e1710e567d36a72a5ce963e300c210ceaadf3d1336d065baf4826363",
        },
        {
            "path": "frozen/O-r2/OPERATING_DESIGN.md",
            "sha256": "d5d562cfb176e236c23ced94f5d821dc505a49dcd5bc4493a052b69539ecdaa0",
        },
    ],
    "bundle_version": "stage12_public_sampling_rule_bundle_v1",
    "proposed_documents": [
        {
            "path": "ACCEPTANCE_SPEC.md",
            "sha256": "7f5ee40147a8a23c64d036c344397019c04b0c3bc7f0ab7a662908e6834ee9e8",
        },
        {
            "path": "AMENDMENT_AND_DESIGN_DRAFT.md",
            "sha256": "75e4d183123bb538bc656f3d340b96874ede2a8e4c479278557830a23241e15d",
        },
        {
            "path": "CONTRACT_MAPPING.md",
            "sha256": "1f81d581ee1af53e30290bc1aaa79f8d593d4ad4cf3bb169210f2ddfec3a7be0",
        },
        {
            "path": "PARAMETERS_DRAFT.json",
            "sha256": "8f122696e8e6b0f7f5c125fddbe175d1d9be09e62205d804af512e7aa7372c22",
        },
        {
            "path": "SCHEMA_SPEC_DRAFT.md",
            "sha256": "b83dc7a10d57d28eb95f180eaec304ccfd8aedc2733014a17e88397dbb7ff742",
        },
    ],
}
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
SCHEMAS[BOUND] = {
    **fields(
        "schema_version:="
        + BOUND
        + " scope:="
        + SCOPE
        + " sampling_policy_sha256:D client_git_sha:G runtime_inventory_sha256:D technical_review_record_sha256:D components:BoundComponent[] total_component_bound_bytes:P method_evidence_sha256:D[]"
    ),
    "method": enum("CLOSED_ALLOCATION_INVENTORY"),
}


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
    value.update(
        schema_version=old.PROFILE,
        rule_bundle_sha256=old.RULE_BUNDLE,
        resource_sample_period_ms=100,
    )
    return value


def legacy_plan(plan, profile):
    value = deepcopy(plan)
    value.pop("sampling_budget")
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
    validate(record, BOUND)
    require(
        digest(record) == profile["sampling_runtime_bound_sha256"]
        and record["sampling_policy_sha256"] == POLICY_SHA
        and record["client_git_sha"] == start["client_git_sha"]
        and record["runtime_inventory_sha256"] == start["runtime_inventory_sha256"]
    )
    names = "SLOT_ARENA INDEX_METADATA SERIALIZATION_SCRATCH PYTHON_ALLOCATOR NATIVE_HASH_IO ADDITIONAL_STACK OTHER_RETAINED".split()
    require([r["name"] for r in record["components"]] == names)
    for row in record["components"]:
        require((row["bound_bytes"] == 0) == (row["basis"] == "NOT_USED"))
    amounts = {r["name"]: r["bound_bytes"] for r in record["components"]}
    require(
        amounts["SLOT_ARENA"] >= 65536
        and amounts["SERIALIZATION_SCRATCH"] <= 65536
        and amounts["ADDITIONAL_STACK"] == 0
    )
    require(sum(amounts.values()) == record["total_component_bound_bytes"] <= 16777216)
    hashes = record["method_evidence_sha256"]
    require(1 <= len(hashes) <= 16 and hashes == sorted(set(hashes)))


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
    }
    result[POLICY_VERSION] = deepcopy(POLICY)
    result["stage12_public_sampling_rule_bundle_v1"] = deepcopy(BUNDLE)
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
    result[TIMING] = {
        "descriptor_version": TIMING,
        "scope": SCOPE,
        "closed": True,
        "schema": TIMING_SCHEMA,
        "named_types": TYPES,
        "live_instance": False,
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

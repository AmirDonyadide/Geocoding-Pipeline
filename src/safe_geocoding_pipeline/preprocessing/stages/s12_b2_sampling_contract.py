"""WF-AP2 protected composition: AP acquisition and strict SP-B-r2 science.

This family is selected by exact versions. Public corpus exceptions and public
monitoring relations are never imported. Descriptors confer no authority.
"""

from __future__ import annotations

from copy import deepcopy
import json

from . import s12_b2_contract as b
from . import s12_b2_operations as old
from . import s12_public_sampling_contract as ap1
from . import s12_retrieval_contract as c

AP_ENABLED = True
M2_ENABLED = True
PAGED_HISTORY = True
POST_SAMPLING_EVENT_KINDS = ("POSTFLIGHT_OBSERVED", "SEGMENT_REVIEWED")
SCOPE = old.SCOPE
PROFILE = "stage12_development_operations_b2_ap_v1"
PLAN = "stage12_development_workload_plan_b2_ap_v1"
START = "stage12_development_operations_campaign_b2_ap_v1"
EVENT = "stage12_development_controller_event_b2_ap_v1"
REPORT = "stage12_development_operations_report_b2_ap_v1"
SNAPSHOT = "stage12_development_recovery_snapshot_b2_ap_v1"
MEASUREMENT = "stage12_development_measurement_report_b2_ap_v1"
POLICY_VERSION = "stage12_development_sampling_policy_b2_ap_v1"
SEED = "stage12_development_sampling_seed_b2_ap_v1"
OBSERVATION = "stage12_development_resource_observation_b2_ap_v1"
BOUND = "stage12_public_sampling_runtime_bound_v2"
TIMING = "stage12_public_path_timing_v3"
TIMING_WIRE = True
ASSURANCE_METHOD = "LOGICAL_ARENAS_AND_ENFORCED_JOB_DOMAIN"
CONFIG = "stage12_development_sampling_configuration_b2_ap_v1"
SCHEMA_BUNDLE = "stage12_development_sampling_schemas_b2_ap_v1"
RULE_BUNDLE = b.digest({"composition": "WF-AP2-T3-M2-P1a", "science": b.DESIGN_SHA256})
CONTROL_BEGIN, CONTROL_FINISH = old.CONTROL_BEGIN, old.CONTROL_FINISH
RESERVATION, MEMORY, COUNT_KEYS, FAILURES = (
    old.RESERVATION,
    old.MEMORY,
    old.COUNT_KEYS,
    old.FAILURES,
)
require, uint, checked, digest = old.require, old.uint, old.checked, old.digest
interval, rate_le, manifest_digest = old.interval, old.rate_le, old.manifest_digest
ASYNC_FIELDS = ap1.ASYNC_FIELDS


def _successor():
    from . import s12_wf_ap2_contract

    return s12_wf_ap2_contract


POLICY = deepcopy(_successor().POLICY)
POLICY.update(
    schema_version=POLICY_VERSION,
    scope=SCOPE,
    monitoring_mode="OBSERVED_PREPOST_WINDOW",
)
BUNDLE = {
    "bundle_version": "stage12_development_sampling_rule_bundle_b2_ap_v1",
    "acquisition_parent_sha256": _successor().RULE_BUNDLE,
    "science_sha256": b.DESIGN_SHA256,
    "strict_response_validation": "UNCHANGED_SP_B_R2",
    "history": "P1a_BOUNDED_FRESH_ORIGINALS",
    "service_state": "OBSERVED_PREPOST_WINDOW_NOT_VERIFIED",
}
RULE_BUNDLE = digest(BUNDLE)
POLICY_SHA = digest(POLICY)
TYPES = deepcopy(old.TYPES)
for name in (
    "HardState",
    "QuiescentCut",
    "ResourceObservation",
    "Role",
    "SamplingFailure",
    "SamplingBudget",
    "SamplingSummary",
):
    TYPES[name] = deepcopy(ap1.TYPES[name])
TYPES["ResourceObservation"]["schema_version"] = "=" + OBSERVATION
TYPES["HistoryLimits"] = ap1.fields(
    "maximum_entries:P maximum_name_bytes:P maximum_total_name_bytes:P page_entries:P maximum_depth:P maximum_file_bytes:P"
)
TYPES["ProtectedTimingBinding"] = ap1.fields(
    "policy_sha256:D source_sha256:D task_sha256:D"
)
TYPES["ProtectedTimingCheckpoint"] = {
    **ap1.fields(
        "observed_rows:U persisted_watermark:U persisted_files:U reserved_files:U persisted_bytes:U reserved_bytes:U last_sha256:D timing_binding:ProtectedTimingBinding timing_policy_version:="
        + POLICY_VERSION
        + " uncertainty_count:U"
    ),
    "closed": {"const": True},
    "failure_code": {"const": None},
    "persistence_uncertain": {"const": False},
    "final_coverage_complete": {"const": True},
}
TYPES["ProtectedTimingEvidence"] = {
    "binding": "ProtectedTimingBinding",
    "checkpoint": "ProtectedTimingCheckpoint",
}
SCHEMAS = {}
for new, prior in (
    (PROFILE, old.PROFILE),
    (PLAN, old.PLAN),
    (START, old.START),
    (EVENT, old.EVENT),
    (REPORT, old.REPORT),
    (SNAPSHOT, old.SNAPSHOT),
    (MEASUREMENT, "stage12_development_measurement_report_b2_v1"),
):
    SCHEMAS[new] = deepcopy(b.SCHEMAS[prior])
    if new != EVENT:
        SCHEMAS[new]["schema_version"] = "=" + new
SCHEMAS[PROFILE].pop("resource_sample_period_ms")
SCHEMAS[PROFILE].update(
    ap1.fields("sampling_policy_sha256:D sampling_runtime_bound_sha256:D")
)
# A complete immutable resource graph is mandatory; its own selected version
# determines the exact closed schema, never an untyped permissive object.
SCHEMAS[PROFILE]["resource_retention_model"] = "ProtectedResourceModel"
SCHEMAS[PLAN].update(
    sampling_budget="SamplingBudget",
    history_limits="HistoryLimits",
    resource_retention_model_sha256="D",
    resource_workload_sha256="D",
)
SCHEMAS[START]["sampling_policy_sha256"] = "D"
for _version in (PROFILE, START, REPORT, SNAPSHOT, MEASUREMENT):
    SCHEMAS[_version]["sampling_assurance_method"] = "=" + ASSURANCE_METHOD
for version in (REPORT, MEASUREMENT):
    SCHEMAS[version]["sampling_segments"] = "SamplingSummary[]"
    SCHEMAS[version]["timing_evidence"] = "ProtectedTimingEvidence"
SCHEMAS[SNAPSHOT].update(
    sampling_policy_sha256="D",
    sampling_close_event_sha256="D?",
    sampling="SamplingSummary",
)
SCHEMAS[SNAPSHOT]["timing_evidence"] = "ProtectedTimingEvidence"
variants = SCHEMAS[EVENT]["variants"]
for spec in variants.values():
    spec["schema_version"] = "=" + EVENT
resource = variants["RESOURCE"]["body"]
resource["cause"]["enum"].remove("PERIODIC")
resource.update(
    ap1.fields("state_revision:U mutation:B mutation_mono_ns:U? selected_state_id:ID")
)
header = {k: v for k, v in variants["RESOURCE"].items() if k not in ("kind", "body")}
for kind in (
    "SAMPLING_OPEN",
    "RESOURCE_SAMPLE",
    "SAMPLE_ACK",
    "SAMPLING_FAULT",
    "SAMPLING_CLOSE",
):
    variants[kind] = {**header, "kind": "=" + kind, "body": deepcopy(ap1.BODIES[kind])}
SCHEMAS[OBSERVATION] = TYPES["ResourceObservation"]
SCHEMAS[SEED] = {**deepcopy(ap1.SCHEMAS[ap1.SEED]), "schema_version": "=" + SEED}
SCHEMAS[POLICY_VERSION] = {
    k: "=" + v if type(v) is str else {"const": v} for k, v in POLICY.items()
}


def validate_type(value, spec):
    if spec == "ProtectedResourceModel":
        from . import s12_b2_resources as resources

        resources.validate_model(value)
    elif isinstance(spec, str) and spec.endswith("?"):
        if value is not None:
            validate_type(value, spec[:-1])
    elif isinstance(spec, str) and spec.endswith("[]"):
        require(type(value) is list)
        for row in value:
            validate_type(row, spec[:-2])
    elif isinstance(spec, str) and spec in b.TYPES:
        b.validate_type(value, spec)
    elif isinstance(spec, str) and spec in TYPES:
        validate_type(value, TYPES[spec])
    elif isinstance(spec, str) and spec in SCHEMAS:
        validate_type(value, SCHEMAS[spec])
    elif isinstance(spec, dict) and "tag" in spec:
        require(type(value) is dict and value.get(spec["tag"]) in spec["variants"])
        validate_type(value, spec["variants"][value[spec["tag"]]])
    elif isinstance(spec, dict) and not ({"enum", "const", "primitive"} & set(spec)):
        require(type(value) is dict and set(value) == set(spec))
        for key, child in spec.items():
            validate_type(value[key], child)
    else:
        b.validate_type(value, spec)


def validate(value, version=None):
    version = version or value.get("schema_version")
    if version == BOUND:
        from . import s12_wf_ap2_assurance as assurance

        assurance.shape(value, assurance.SCHEMA)
        return
    if version in (CONTROL_BEGIN, CONTROL_FINISH):
        return old.validate(value, version)
    require(version in SCHEMAS)
    validate_type(value, SCHEMAS[version])
    if version == OBSERVATION:
        times = [
            value[k]
            for k in (
                "acquire_enter_ns",
                "free_query_start_ns",
                "free_query_end_ns",
                "observed_mono_ns",
                "acquire_exit_ns",
            )
        ]
        require(times == sorted(times) and len(c.canonical(value)) <= 2048)
        require(
            1 <= value["occupied_count_after_reserve"] <= 16
            and value["occupied_bytes_after_reserve"]
            == value["occupied_count_after_reserve"] * 4096
        )
        require((value["role"] == "FINAL") == (value["cut"] is not None))
    if version == EVENT:
        require(len(c.canonical(value)) <= 4096)


def parse(raw, version=None):
    from . import s12_storage as io

    value = json.loads(raw, object_pairs_hook=io.pairs)
    require(c.canonical(value) == raw)
    validate(value, version)
    return value


def legacy_profile(profile):
    value = deepcopy(profile)
    for key in (
        "sampling_policy_sha256",
        "sampling_runtime_bound_sha256",
        "sampling_assurance_method",
        "resource_retention_model",
    ):
        value.pop(key)
    value.update(
        schema_version=old.PROFILE,
        rule_bundle_sha256=old.RULE_BUNDLE,
        resource_sample_period_ms=100,
    )
    return value


def legacy_plan(plan, profile):
    value = deepcopy(plan)
    for key in (
        "sampling_budget",
        "history_limits",
        "resource_retention_model_sha256",
        "resource_workload_sha256",
    ):
        value.pop(key)
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
        profile["monitoring"]["mode"] == "OBSERVED_PREPOST_WINDOW"
        and profile["resources"]["writer_guard_ms"] == 5000
        and profile["resources"]["process_overhead_bytes"] >= 16777216
    )
    old._validate_profile_o1(legacy_profile(profile))


def validate_plan(plan, profile):
    from . import s12_b2_resources as resources
    from . import s12_paged_history as history

    validate_profile(profile)
    from . import s12_b2_acceptance_graph as graph

    require(graph.is_model(profile["resource_retention_model"]), "B2_AP_GRAPH_FAMILY")
    validate(plan, PLAN)
    require(
        plan["operations_profile_sha256"] == digest(profile)
        and plan["resource_retention_model_sha256"]
        == digest(profile["resource_retention_model"])
    )
    require(plan["resource_workload_sha256"] == resources.workload_binding(plan))
    resources.validate_plan_model(profile["resource_retention_model"], plan)
    old._validate_plan_common(
        legacy_plan(plan, profile), legacy_profile(profile), scalar_storage=False
    )
    history.validate_limits(plan["history_limits"])
    amounts = plan["sampling_budget"]
    segments = amounts["maximum_segments"]
    require(segments <= 512, "S12_PUBLIC_HISTORY_LIMIT")
    observations = (plan["budgets"]["active_duration_ms"] + 49) // 50 + 2 * segments
    files = 4 * observations + 8 * segments
    require(
        amounts["maximum_inventory_versions_per_segment"] <= 8
        and amounts["maximum_observations"] >= observations
    )
    require(
        amounts["additional_event_tokens"] >= 2 * observations + 4 * segments
        and amounts["additional_event_tokens"] < plan["budgets"]["event_count"]
    )
    require(amounts["additional_file_entries"] >= files + 8 * segments + 1502)
    require(
        amounts["additional_file_data_bytes"]
        >= 4096 * files + 8 * segments * (512 * files + 4096) + 50200576
        and amounts["additional_file_data_bytes"] < plan["budgets"]["storage_bytes"]
    )
    require(plan["history_limits"]["maximum_entries"] >= plan["budgets"]["event_count"])
    model = profile["resource_retention_model"]
    require(
        model["physical_peak_bound_bytes"]
        <= min(
            profile["resources"]["allocated_disk_bytes"],
            plan["budgets"]["storage_bytes"],
        )
    )


def work_rows(rows, plan):
    yield from old.work_rows(rows, plan)


def verify_work_manifest(factory, plan):
    require(manifest_digest(work_rows(factory(), plan)) == plan["work_manifest_sha256"])


def validate_bound(record, profile, start, **kwargs):
    from . import s12_wf_ap2_assurance as assurance
    import sys

    assurance.validate_record(
        record, profile, start, contract=sys.modules[__name__], **kwargs
    )
    require(
        record["invocation_graph_sha256"]
        == digest(profile["resource_retention_model"]),
        "B2_AP_GRAPH_BINDING",
    )
    return record


def verify_authorities(profile, plan, start, authority):
    validate_plan(plan, profile)
    validate(start, START)
    b.verify_executable_science(start)
    require(
        start["sampling_policy_sha256"] == POLICY_SHA
        and start["profile_sha256"] == digest(profile)
        and start["plan_sha256"] == digest(plan)
        and start["rule_bundle_sha256"] == RULE_BUNDLE
    )
    require(
        start["retrieval_policy_id"]
        == c.policy(plan["result_limit"])["retrieval_policy_id"].hex()
    )
    for key in (
        "population_scope",
        "window_plan_sha256",
        "stage11_input_binding_sha256",
    ):
        require(start[key] == plan[key])
    require(
        start["policy_freeze_record_sha256"] == profile["policy_freeze_record_sha256"]
    )
    for key in (
        "window_plan_sha256",
        "privacy_permission_sha256",
        "scientific_decision_sha256",
    ):
        require(start[key] == profile["monitoring"][key])
    bound_authority = getattr(authority, "authority", authority)
    require(
        bound_authority is not None
        and callable(getattr(bound_authority, "sampling_bound", None))
    )
    record = bound_authority.sampling_bound(profile, start)
    validate_bound(record, profile, start)
    from . import s12_wf_ap2_assurance as assurance

    assurance.verify_runtime(
        record, bound_authority, {"profile": profile, "plan": plan, "start": start}
    )
    context = {"profile": profile, "plan": plan, "start": start}
    for key in (
        "policy_freeze_record_sha256",
        "implementation_authorization_sha256",
        "implementation_review_sha256",
        "initial_workload_authority_sha256",
        "scientific_campaign_start_sha256",
    ):
        authority.require(key, start[key], context)
    authority.require(
        "sampling_runtime_bound", profile["sampling_runtime_bound_sha256"], context
    )
    authority.require(
        "sampling_bound_review", record["technical_review_record_sha256"], record
    )
    for key, value in (
        ("operator_allowance", profile["operator_allowance"]["record_sha256"]),
        ("transport_profile", profile["transport_profile_sha256"]),
        ("plan_selection", plan["selection_basis_sha256"]),
        ("demonstrated_ceiling", profile["demonstrated_ceiling_sha256"]),
        ("resources", profile["resources"]["resource_review_sha256"]),
        (
            "administrative_acquisition",
            profile["administrative"]["acquisition_contract_sha256"],
        ),
    ):
        authority.require(key, value, context)
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


def extra_binding_fields():
    return {"sampling_assurance_method": ASSURANCE_METHOD}


def validate_timing(value):
    return ap1.validate_timing(value)


def timing_evidence(observer):
    summary = observer.snapshot()
    require(
        summary["observer_failure_count"]
        == summary["partial_timing_rows"]
        == summary["outstanding_traces"]
        == 0,
        "B2_TIMING_INCOMPLETE",
    )
    snapshot = summary["checkpoint"]
    require(type(snapshot) is dict)
    value = {
        "binding": snapshot["timing_binding"],
        "checkpoint": {
            key: snapshot[key] for key in TYPES["ProtectedTimingCheckpoint"]
        },
    }
    validate_type(value, "ProtectedTimingEvidence")
    return value


def verify_timing(root, value):
    from . import s12_public_checkpoints as checkpoints
    from . import s12_public_timing as timing
    from . import s12_paged_history as history
    from . import s12_storage as io

    validate_type(value, "ProtectedTimingEvidence")
    require(value["binding"]["policy_sha256"] == POLICY_SHA)
    last = {"HARD_SYNC": 0, "PERIODIC_ASYNC": 0}
    counts = dict.fromkeys(last, 0)

    def original(seq):
        uint(seq, True)
        return parse(io.read(root / "events" / f"{seq:020d}.json", limit=4096), EVENT)

    def joined(_ordinal, row):
        kind = row["row_kind"]
        if kind == "HARD_SYNC":
            require(row["legacy_row"][2] == "COMPLETE", "B2_TIMING_INCOMPLETE")
            seq = row["legacy_row"][checkpoints.PUBLIC_FIELDS.index("event_seq")]
        else:
            require(row["outcome"] == "COMPLETE", "B2_TIMING_INCOMPLETE")
            seq = row["sample_event_seq"]
        require(seq > last[kind], "B2_TIMING_ASSOCIATION")
        last[kind] = seq
        counts[kind] += 1
        event = original(seq)
        ack = original(row["ack_event_seq"]) if kind == "PERIODIC_ASYNC" else None
        timing.verify_sampling_association(
            row,
            event,
            phase_id=1,
            ack_event=ack,
            contract=__import__(__name__, fromlist=["*"]),
        )

    result = checkpoints.read_prefix(
        root.parent / (root.name + "_telemetry"),
        expected_binding=value["binding"],
        expected_snapshot=value["checkpoint"],
        record_consumer=joined,
    )
    require(result["incomplete"] is False, "B2_TIMING_INCOMPLETE")
    expected = dict.fromkeys(last, 0)
    require(history.current() is not None, "S12_PUBLIC_HISTORY_LIMIT")
    for path in history.event_paths(root / "events", history.current()):
        event = parse(io.read(path, limit=4096), EVENT)
        expected["PERIODIC_ASYNC"] += event["kind"] == "RESOURCE_SAMPLE"
        expected["HARD_SYNC"] += (
            event["kind"] == "RESOURCE" and event["body"]["cause"] == "START_RESERVE"
        )
    require(expected == counts, "B2_TIMING_ASSOCIATION")
    return result


def descriptors():
    from . import s12_b2_acceptance_graph as graph

    types = deepcopy(TYPES)
    types["ProtectedResourceModel"] = {
        "tag": "schema_version",
        "variants": {graph.MODEL: graph.MODEL_SCHEMA},
    }
    return {
        SCHEMA_BUNDLE: {
            "descriptor_version": SCHEMA_BUNDLE,
            "scope": SCOPE,
            "closed": True,
            "schemas": SCHEMAS,
            "named_types": types,
            "rule_bundle_sha256": RULE_BUNDLE,
            "live_instance": False,
            "response_validation": "STRICT_SP_B_R2_NO_PUBLIC_EXCEPTION",
            "continuous_service_state": "NOT_VERIFIED",
        },
        POLICY_VERSION: deepcopy(POLICY),
        BUNDLE["bundle_version"]: deepcopy(BUNDLE),
    }


def verify_descriptors(repository=None):
    from pathlib import Path

    root = (
        Path(repository)
        if repository is not None
        else Path(__file__).resolve().parents[4]
    )
    for name, descriptor in descriptors().items():
        raw = (root / "docs" / "scientific_assets" / (name + ".json")).read_bytes()
        require(raw == c.canonical(descriptor), "B2_AP_DESCRIPTOR_MISMATCH")

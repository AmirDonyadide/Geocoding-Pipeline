"""O-r2 public-only schemas and finite plans. No authority or live defaults.

Schema descriptors describe types, never executable profiles. Authority checks
are injected by an independently authorized caller; a digest is not permission.
"""

from __future__ import annotations

import json
import hashlib
import math
import re
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime
from typing import Any, Protocol

from . import s12_probe as probe
from . import s12_retrieval_contract as c

SCOPE = "PUBLIC_SYNTHETIC_ONLY"
PROFILE = "stage12_transport_operations_v2"
PLAN = "stage12_public_characterization_plan_v1"
START = "stage12_public_operations_campaign_v1"
EVENT = "stage12_public_controller_event_v1"
REPORT = "stage12_public_characterization_report_v1"
SNAPSHOT = "stage12_public_recovery_snapshot_v1"
CONTROL_BEGIN = "stage12_public_control_begin_v1"
CONTROL_FINISH = "stage12_public_control_finish_v1"
RULE_BUNDLE = "8f3cbc25a943b65ee800227accc0e3629a7b71989340753d89b3f3acecc05435"
RESERVATION = 16_777_216 * 128
MEMORY = 4_294_967_296
MAX_U = 2**64 - 1
FAILURES = (
    "TECHNICAL_FAILURE_RETRYABLE",
    "TECHNICAL_FAILURE_FINAL",
    "CONTRACT_FAILURE",
    "DEPLOYMENT_IDENTITY_FAILURE",
)
REASONS = frozenset(
    """
OK RESPONSE_CONTRACT_INVALID AUTHENTICATION_FAILED AUTHORIZATION_FAILED
HTTP_REQUEST_REJECTED TIMEOUT RATE_LIMITED SERVER_TRANSIENT UNSUPPORTED_PROTOCOL
NETWORK_TRANSIENT ENVIRONMENT_NETWORK_INVALID RESPONSE_TRUNCATED
REDIRECT_FORBIDDEN RESPONSE_RESOURCE_LIMIT SECRET_ECHO_DETECTED
RETRY_BUDGET_EXHAUSTED RETRY_AFTER_REQUIRES_OWNER_RECOVERY TERMINAL_FAILURE
TECHNICAL_ERROR_PRESSURE OVERLOAD_PRESSURE LATENCY_PRESSURE
DEPLOYMENT_IDENTITY_FAILURE IDENTITY_UNVERIFIABLE DEPLOYMENT_AUTHENTICITY_FAILURE
IDENTITY_VERIFICATION_STALE IDENTITY_INTERVAL_NOT_CLOSED
PUBLIC_PROBE_EVIDENCE_WRITE_FAILED
""".split()
)


def require(ok: bool, reason: str = "S12_PUBLIC_OPERATIONS_INVALID") -> None:
    c.require(ok, reason)


def uint(value: Any, positive: bool = False) -> int:
    require(type(value) is int and int(positive) <= value <= MAX_U)
    return value


def checked(value: int) -> int:
    return uint(value)


def digest(obj: Any) -> str:
    return c.sha(c.canonical(obj)).hex()


def fields(text: str) -> dict[str, str]:
    return dict(item.split(":", 1) for item in text.split())


def enum(*values: str) -> dict[str, Any]:
    return {"enum": list(values)}


TYPES: dict[str, Any] = {
    "Rate": fields("num:P den:P"),
    "Fraction": fields("num:U den:P"),
    "Ratio": fields("num:U den:P"),
    "Preserved": fields(
        "operations_v1_sha256:D materialization_sha256:D response_validation_sha256:D public_audit_source_sha256:D"
    ),
    "Allowance": fields(
        "record_sha256:D rate_ceiling:Rate connections:P valid_from:Z valid_until:Z"
    ),
    "RateState": fields(
        "state_id:ID rate:Rate connections:P admitted_operations:P evidence_sha256:D"
    ),
    "Resources": fields(
        "admission_memory_bytes:P capacity_basis_sha256:D process_overhead_bytes:P job_memory_bytes:P pending_request_bytes:P per_attempt_disk_bound_bytes:P fixed_campaign_disk_bound_bytes:P allocated_disk_bytes:P resource_review_sha256:D scheduler_guard_ms:P writer_guard_ms:P"
    ),
    "Monitoring": {
        "tag": "mode",
        "variants": {
            "PUBLIC_GAPS_ONLY": fields("mode:=PUBLIC_GAPS_ONLY gaps_record_sha256:D"),
            "FROZEN_V1": fields(
                "mode:=FROZEN_V1 mechanism:Mechanism deployment_binding_sha256:D verifier_contract_sha256:D refresh_recipe_id:ID closure_recipe_id:ID exclusion_record_sha256:D"
            ),
        },
    },
    "Mechanism": enum("CONTROLLED_CAMPAIGN", "PER_RESPONSE_GENERATION"),
    "Purpose": enum(
        "AUTH_CHECK",
        "LIMIT_CHECK",
        "IDENTITY_REFRESH",
        "IDENTITY_CLOSURE",
        "HEALTH_CHECK",
    ),
    "Kind": enum("DATA", "SERVICE_CONTROL"),
    "Work": fields(
        "work_id:ID block_id:ID kind:Kind fixture_id:D? result_limit:P? repetition:U? recipe_id:ID? retry_spacing_key:D"
    ),
    "ControlRecipe": fields(
        "recipe_id:ID recipe_sha256:D implementation_contract_sha256:D transport_profile_sha256:D purpose:Purpose max_http_attempts_per_invocation:P max_duration_ms:P"
    ),
    "Budget": fields(
        "data_observations:U required_control_observations:U reserved_control_observations:U data_attempts:U control_http_attempts:U administrative_operations:U administrative_duration_ms:U active_duration_ms:P storage_bytes:P event_count:P"
    ),
    "Evaluation": enum("EXPLORATORY", "CONFIRMATORY"),
    "Experiment": enum("CAPABILITY", "PERFORMANCE"),
    "Block": fields(
        "block_id:ID state_id:ID observation_ids:ID[] reserved_control_ids:ID[] budget:Budget evaluation:Evaluation criteria:Criteria? fallback_state_ids:ID[] transition_from:ID?"
    ),
    "Mode": enum("FULL_TEXT", "STRUCTURED"),
    "Cell": fields("mode:Mode size:P"),
    "Criteria": fields(
        "min_valid_data:P min_duration_ms:P max_duration_ms:P min_attempt_rate:Rate min_durable_data_rate:Rate max_http_p95_ms:P max_http_p99_ms:P max_slot_p95_ms:P max_slot_p99_ms:P max_retry_fraction:Fraction max_pending_count:U max_pending_bytes:U max_reserved_bytes:P max_writer_wait_ms:P required_cells:Cell[] min_per_cell:P"
    ),
    "Outcome": enum(*c.OUTCOMES),
    "ControlOutcome": enum("CONTROL_SUCCESS", *FAILURES),
    "FinalOutcome": {
        "tag": "kind",
        "variants": {
            "DATA": {"kind": "=DATA", "value": "Outcome"},
            "SERVICE_CONTROL": {
                "kind": "=SERVICE_CONTROL",
                "value": enum("CONTROL_SUCCESS", *FAILURES, "UNKNOWN_DELIVERY"),
            },
        },
    },
    "Reason": enum(*sorted(REASONS)),
    "Verification": enum("VERIFIED", "FAILED", "NOT_PERFORMED"),
    "Disposition": enum(
        "PAUSED_CLEAN", "COMPLETED", "STOPPED", "QUARANTINED", "RECOVERY_BLOCKED"
    ),
    "ReportDisposition": enum(
        "PAUSED_CLEAN", "COMPLETED", "STOPPED", "QUARANTINED", "RECOVERY_BLOCKED"
    ),
    "ReportReason": enum(
        *"MISSING_AUTHORITY INCOMPLETE_WORK UNSAFE_RESPONSE REPEAT_DISAGREEMENT OVERLOAD_OR_COOLDOWN RATE_CHANGED THRESHOLD_FAILED COVERAGE_FAILED MONITOR_FAILED AUDIT_FAILED BUDGET_EXHAUSTED STOPPED UNKNOWN_DELIVERY INSUFFICIENT_MEASUREMENT EXPLORATORY_NO_QUALIFICATION".split()
    ),
    "BlockStatus": enum("PASS", "FAIL", "INCOMPLETE", "EXPLORATORY_ONLY"),
    "Count": fields("value:U? confirmed_min:U"),
    "Stat": fields("n:U p50_ms:U? p95_ms:U? p99_ms:U? max_ms:U?"),
    "Rates": fields(
        "data_first_dispatch_per_s:Ratio? all_attempts_per_s:Ratio? http_completions_per_s:Ratio? durable_data_per_s:Ratio? retry_fraction:Ratio?"
    ),
    "Latencies": fields(
        "transport_all:Stat transport_data:Stat full_slot_data:Stat writer_wait:Stat"
    ),
    "Peaks": fields(
        "connection_slots:U? admitted:U? pending_count:U? pending_bytes:U? reserved_bytes:U? writer_wait_ms:U? min_free_allocated_disk_bytes:U?"
    ),
    "CellCount": fields("mode:Mode size:P planned:U durable_valid:Count"),
    "BlockReport": fields(
        "block_id:ID criterion_sha256:D? input_event_prefix_sha256:D input_last_event_seq:ID status:BlockStatus reasons:ReportReason[] duration_ns:U? counts:Counts rates:Rates latencies:Latencies peaks:Peaks cells:CellCount[] repeat_comparison_sha256:D? monitoring_complete:B receipts_complete:B resource_sampling_complete:B"
    ),
    "PressureEntry": fields("ticket:ID retryable:B elapsed_ms:U"),
    "OverloadEntry": fields("work_id:ID attempt:P"),
    "MonitoringState": enum("PUBLIC_GAPS_ONLY", "CLOSED_VERIFIED", "UNVERIFIED"),
    "ControllerSnapshot": fields(
        "state_id:ID block_id:ID charged_data_attempts:U charged_control_attempts:U administrative_operations:U active_duration_ms:U stored_bytes:U event_count:U last_ticket:U consecutive_retryable:U recent:PressureEntry[] overload_carry:OverloadEntry[] breaker_reason:Reason? cooldown_delay_ms:U remaining_work_ledger_sha256:D monitoring_state:MonitoringState resume_eligible:B"
    ),
    "WorkState": enum(
        "UNBEGUN",
        "RETRY_DUE",
        "DURABLE_SUCCESS",
        "TERMINAL",
        "UNKNOWN_DELIVERY",
        "UNUSED_RESERVED_CONTROL",
    ),
    "WorkLedgerRow": fields(
        "work_id:ID charged_ordinals:U[] selected_receipt_sha256:D? last_outcome:FinalOutcome? retry_delay_ms:U? state:WorkState"
    ),
}
COUNT_KEYS = "planned_data required_controls reserved_controls unused_reserved_controls begins_charged attempt_starts emission_commits emissions_entered first_attempt_starts retry_attempt_starts control_attempt_starts http_completions http_200 durable_valid_data durable_valid_zero durable_retryable durable_terminal_failure unknown_delivery unprocessed_data administrative_operations cooldown_events downshift_events breakers".split()
TYPES["Counts"] = dict.fromkeys(COUNT_KEYS, "Count")
EVENT_BODIES = {
    "SEGMENT_OPEN": fields(
        "authority_sha256:D predecessor_snapshot_sha256:D? writer_exclusion_evidence_sha256:D block_id:ID state_id:ID"
    ),
    "BEGIN_DURABLE": fields("work_id:ID attempt:P begin_sha256:D"),
    "ATTEMPT_STARTED": fields("work_id:ID attempt:P started_mono_ns:U"),
    "EMIT_COMMITTED": fields("work_id:ID attempt:P committed_mono_ns:U"),
    "EMISSION": {
        **fields("work_id:ID attempt:P entered_mono_ns:U returned_mono_ns:U?"),
        "result": enum("WRITE_RETURNED", "WRITE_FAILED", "UNKNOWN"),
    },
    "EARLY_SIGNAL": {
        **fields(
            "work_id:ID attempt:P observed_mono_ns:U status:U? retry_after_seconds:U?"
        ),
        "signal": enum("OVERLOAD", "RETRYABLE_5XX", "TERMINAL", "PRIVACY", "IDENTITY"),
    },
    "NETWORK_DONE": fields(
        "work_id:ID attempt:P ticket:ID completed_mono_ns:U elapsed_ms:U transport_record_sha256:D"
    ),
    "ATTEMPT_FINALIZED": fields(
        "work_id:ID attempt:P ticket:ID outcome:FinalOutcome reason:Reason receipt_inventory_sha256:D elapsed_ms:U status:U? retry_after_seconds:U? retry_delay_ms:U?"
    ),
    "AUDIT_TIMING": fields(
        "work_id:ID attempt:P ticket:ID writer_enqueued_ns:U writer_started_ns:U receipt_reopened_ns:U finalized_event_ack_ns:U reservation_released_ns:U"
    ),
    "COOLDOWN": fields("until_mono_ns:U trigger_work_id:ID trigger_attempt:P"),
    "BACKPRESSURE": {
        "why": enum(
            "SLOTS", "REQUEST_BYTES", "WRITER", "STORAGE", "MONITORING", "TIME"
        ),
        "entered": "B",
    },
    "DOWNSHIFT": {
        **fields("from_state:ID to_state:ID basis_event_seq:ID"),
        "why": enum("RESOURCE_PRESSURE", "OVERLOAD", "OPERATOR_RESTRICTION"),
    },
    "MONITOR_RESULT": {
        **fields(
            "work_id:ID receipt_sha256:D acquired_mono_ns:U count_baseline:U interval_closed:B"
        ),
        "result": enum("VERIFIED", "FAILED"),
    },
    "RESOURCE": {
        **fields(
            "observed_mono_ns:U connection_slots:U admitted_operations:U pending_count:U pending_bytes:U reserved_bytes:U free_allocated_disk_bytes:U?"
        ),
        "cause": enum(
            "START_RESERVE",
            "CONNECTION_RELEASE",
            "QUEUE_ADD",
            "QUEUE_REMOVE",
            "RESERVATION_RELEASE",
            "STATE_CHANGE",
            "PERIODIC",
        ),
    },
    "STOP": {
        **fields("primary_reason:Reason? trigger_event_seq:ID?"),
        "why": enum(
            "BREAKER",
            "TERMINAL",
            "PRIVACY",
            "DRIFT",
            "IDENTITY_STALE",
            "AUDIT_IO",
            "BUDGET",
            "TIME",
            "RESOURCE",
            "OPERATOR",
            "UNACCOUNTED_DELIVERY",
            "MEASUREMENT_FAILURE",
        ),
    },
    "BLOCK_CLOSED": fields("block_id:ID report_sha256:D result:BlockStatus"),
    "SEGMENT_CLOSE": fields(
        "disposition:Disposition closure_evidence_sha256:D? last_ticket:U"
    ),
}
SCHEMAS = {
    PROFILE: fields(
        "schema_version:="
        + PROFILE
        + " scope:="
        + SCOPE
        + " rule_bundle_sha256:D policy_freeze_record_sha256:D preserved:Preserved transport_profile_sha256:D operator_allowance:Allowance states:RateState[] resources:Resources monitoring:Monitoring resource_sample_period_ms:P"
    ),
    PLAN: fields(
        "schema_version:="
        + PLAN
        + " scope:="
        + SCOPE
        + " operations_profile_sha256:D fixture_inventory_sha256:D work_manifest_sha256:D control_recipes:ControlRecipe[] blocks:Block[] experiment_kind:Experiment capability_parent_sha256:D? budgets:Budget window_start:Z window_end:Z shutdown_reserve_ms:P selection_basis_sha256:D"
    ),
    START: fields(
        "schema_version:="
        + START
        + " scope:="
        + SCOPE
        + " campaign_id:N32 profile_sha256:D plan_sha256:D rule_bundle_sha256:D policy_freeze_record_sha256:D implementation_authorization_sha256:D implementation_review_sha256:D initial_workload_authority_sha256:D client_git_sha:G runtime_inventory_sha256:D created_utc:Z"
    ),
    EVENT: {
        "tag": "kind",
        "variants": {
            k: {
                **fields(
                    "schema_version:="
                    + EVENT
                    + " campaign_start_sha256:D segment_id:ID seq:ID previous_event_sha256:D? epoch_id:N32 mono_ns:U utc:Z"
                ),
                "kind": "=" + k,
                "body": v,
            }
            for k, v in EVENT_BODIES.items()
        },
    },
    REPORT: fields(
        "schema_version:="
        + REPORT
        + " scope:="
        + SCOPE
        + " campaign_start_sha256:D profile_sha256:D plan_sha256:D event_inventory_sha256:D attempt_inventory_sha256:D segment_snapshot_hashes:D[] blocks:BlockReport[] campaign_counts:Counts disposition:ReportDisposition reconciliation_reasons:ReportReason[] scientific_identity_verified:B protected_readiness:=BLOCKED approval_status:=UNISSUED report_complete:B"
    ),
    SNAPSHOT: fields(
        "schema_version:="
        + SNAPSHOT
        + " campaign_start_sha256:D segment_id:ID last_event_seq:ID last_event_sha256:D event_inventory_sha256:D attempt_inventory_sha256:D work_ledger_sha256:D controller:ControllerSnapshot closure_evidence_sha256:D? writer_release_evidence_sha256:D sealed_utc:Z disposition:Disposition"
    ),
    CONTROL_BEGIN: fields(
        "schema_version:="
        + CONTROL_BEGIN
        + " campaign_start_sha256:D profile_sha256:D plan_sha256:D segment_id:ID work_id:ID attempt:P recipe_sha256:D request_target_sha256:D started_utc:Z"
    ),
    CONTROL_FINISH: fields(
        "schema_version:="
        + CONTROL_FINISH
        + " begin_sha256:D transport_record_sha256:D validation_contract_sha256:D validation_result:Verification verification_receipt_sha256:D? response_sha256:D? application_payload_bytes:U? raw_inventory_sha256:D? outcome:ControlOutcome reason:Reason"
    ),
}


def validate_type(value: Any, spec: Any) -> None:
    if isinstance(spec, str):
        if spec.endswith("?"):
            if value is not None:
                validate_type(value, spec[:-1])
        elif spec.endswith("[]"):
            require(type(value) is list)
            for item in value:
                validate_type(item, spec[:-2])
        elif spec.startswith("="):
            require(type(value) is str and value == spec[1:])
        elif spec in ("U", "P", "ID"):
            uint(value, spec != "U")
        elif spec == "B":
            require(type(value) is bool)
        elif spec in ("D", "G", "N32"):
            require(
                type(value) is str
                and re.fullmatch(
                    r"[0-9a-f]{" + ("40" if spec == "G" else "64") + "}", value
                )
                is not None
            )
        elif spec == "Z":
            require(
                type(value) is str
                and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value)
                is not None
            )
            try:
                datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
            except ValueError:
                require(False)
        else:
            validate_type(value, TYPES[spec])
            if spec in ("Rate", "Fraction"):
                require(math.gcd(value["num"], value["den"]) == 1)
                require(value["num"] <= (60 if spec == "Rate" else 1) * value["den"])
                if spec == "Rate":
                    interval(value)
            elif spec == "Count":
                require(
                    value["value"] is None or value["value"] == value["confirmed_min"]
                )
    elif "enum" in spec:
        require(type(value) is str and value in spec["enum"])
    elif "tag" in spec:
        require(type(value) is dict and type(value.get(spec["tag"])) is str)
        require(value[spec["tag"]] in spec["variants"])
        validate_type(value, spec["variants"][value[spec["tag"]]])
    else:
        require(type(value) is dict and set(value) == set(spec))
        for key, child in spec.items():
            validate_type(value[key], child)


def validate(value: dict[str, Any], version: str) -> None:
    require(version in SCHEMAS)
    validate_type(value, SCHEMAS[version])


def parse(raw: bytes, version: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        require(len({k for k, _ in items}) == len(items))
        return dict(items)

    try:
        obj = json.loads(raw, object_pairs_hook=pairs)
        require(c.canonical(obj) == raw)
        validate(obj, version)
        return obj
    except (ValueError, UnicodeError, TypeError):
        raise c.Stage12Error("S12_PUBLIC_OPERATIONS_INVALID") from None


def interval(rate: dict[str, int]) -> int:
    return uint((10**9 * rate["den"] + rate["num"] - 1) // rate["num"], True)


def rate_le(left: dict[str, int], right: dict[str, int]) -> bool:
    return left["num"] * right["den"] <= right["num"] * left["den"]


class Authority(Protocol):
    def require(
        self, purpose: str, evidence_sha256: str, context: dict[str, Any]
    ) -> None:
        """Verify actual issuer/scope/bytes/applicability or raise; no default."""


class ControlAdapter(Protocol):
    def target(self, recipe: dict[str, Any]) -> bytes:
        """Exact reviewed public request target; no config-selected URL."""

    def validate(self, recipe: dict[str, Any], raw: bytes) -> bytes:
        """Return actual canonical verification receipt bytes or raise."""


def validate_profile(profile: dict[str, Any]) -> None:
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
        resources["job_memory_bytes"]
        >= checked(
            resources["admission_memory_bytes"]
            + resources["pending_request_bytes"]
            + resources["process_overhead_bytes"]
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
            <= resources["admission_memory_bytes"]
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


def budget(value: dict[str, Any]) -> None:
    validate_type(value, "Budget")
    require(
        value["administrative_operations"] == value["administrative_duration_ms"] == 0
    )
    require(
        value["data_observations"]
        <= value["data_attempts"]
        <= checked(5 * value["data_observations"])
    )
    controls = checked(
        value["required_control_observations"] + value["reserved_control_observations"]
    )
    require(
        value["required_control_observations"]
        <= value["control_http_attempts"]
        <= checked(5 * controls)
    )
    checked(value["data_attempts"] + value["control_http_attempts"])


def validate_plan(plan: dict[str, Any], profile: dict[str, Any]) -> None:
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
    require(b["storage_bytes"] <= r["allocated_disk_bytes"])
    require(
        r["allocated_disk_bytes"]
        >= checked(
            r["fixed_campaign_disk_bound_bytes"]
            + (b["data_attempts"] + b["control_http_attempts"])
            * r["per_attempt_disk_bound_bytes"]
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
                and criteria["max_pending_bytes"] <= r["pending_request_bytes"]
                and criteria["max_reserved_bytes"] <= r["admission_memory_bytes"]
            )
    for key in b:
        require(checked(sum(x["budget"][key] for x in plan["blocks"])) <= b[key])


def work_rows(
    rows: Iterable[dict[str, Any]], plan: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Validate each row without materializing the work manifest or payloads."""
    fixtures = {f["fixture_id"]: f for f in probe.fixtures()}
    recipes = {x["recipe_id"]: x for x in plan["control_recipes"]}
    for i, row in enumerate(rows, 1):
        validate_type(row, "Work")
        require(row["work_id"] == i and row["block_id"] <= len(plan["blocks"]))
        block = plan["blocks"][row["block_id"] - 1]
        require(i in block["observation_ids"] or i in block["reserved_control_ids"])
        if row["kind"] == "DATA":
            require(
                row["fixture_id"] in fixtures
                and row["recipe_id"] is None
                and row["repetition"] is not None
            )
            require(
                row["result_limit"] is not None
                and row["result_limit"] <= 40
                and i in block["observation_ids"]
            )
            require(row["retry_spacing_key"] == row["fixture_id"])
        else:
            require(
                row["recipe_id"] in recipes
                and row["fixture_id"]
                is row["result_limit"]
                is row["repetition"]
                is None
            )
            require(
                row["retry_spacing_key"] == recipes[row["recipe_id"]]["recipe_sha256"]
            )
        yield row


def manifest_digest(rows: Iterable[dict[str, Any]]) -> str:
    """SHA256(J(rows)) without retaining the whole list in memory."""
    h = hashlib.sha256(b"[")
    for i, row in enumerate(rows):
        if i:
            h.update(b",")
        h.update(c.canonical(row)[:-1])
    h.update(b"]\n")
    return h.hexdigest()


def verify_work_manifest(
    factory: Callable[[], Iterable[dict[str, Any]]], plan: dict[str, Any]
) -> None:
    require(manifest_digest(work_rows(factory(), plan)) == plan["work_manifest_sha256"])
    # Repeated bounded scans avoid an in-memory population/work ledger.
    fixture_map = {x["fixture_id"]: x for x in probe.fixtures()}
    for block in plan["blocks"]:
        data = required = reserved = controls_cap = 0
        cells: dict[tuple[str, int], int] = {}
        last_id = 0
        for row in work_rows(factory(), plan):
            last_id = row["work_id"]
            if row["block_id"] != block["block_id"]:
                continue
            if row["kind"] == "DATA":
                data += 1
                cell = (
                    fixture_map[row["fixture_id"]]["core"]["search_mode"],
                    row["result_limit"],
                )
                cells[cell] = cells.get(cell, 0) + 1
            else:
                is_reserved = row["work_id"] in block["reserved_control_ids"]
                reserved += is_reserved
                required += not is_reserved
                recipe = next(
                    x
                    for x in plan["control_recipes"]
                    if x["recipe_id"] == row["recipe_id"]
                )
                controls_cap += recipe["max_http_attempts_per_invocation"]
        b = block["budget"]
        require(
            (data, required, reserved)
            == (
                b["data_observations"],
                b["required_control_observations"],
                b["reserved_control_observations"],
            )
        )
        require(b["control_http_attempts"] <= controls_cap)
        require(
            all(
                i <= last_id
                for x in plan["blocks"]
                for i in x["observation_ids"] + x["reserved_control_ids"]
            )
        )
        if block["criteria"]:
            criteria = block["criteria"]
            require(
                all(
                    cells.get((x["mode"], x["size"]), 0) >= criteria["min_per_cell"]
                    for x in criteria["required_cells"]
                )
            )
    for key in (
        "data_observations",
        "required_control_observations",
        "reserved_control_observations",
    ):
        require(sum(b["budget"][key] for b in plan["blocks"]) == plan["budgets"][key])
    if plan["experiment_kind"] == "CAPABILITY":
        seen_sizes: list[int] = []
        last_size = 0
        for row in work_rows(factory(), plan):
            if row["kind"] == "DATA":
                require(row["result_limit"] >= last_size)
                last_size = row["result_limit"]
                if last_size not in seen_sizes:
                    seen_sizes.append(last_size)
        require(
            seen_sizes[:4] == [1, 3, 5, 10]
            and seen_sizes == sorted(seen_sizes)
            and len(seen_sizes) <= 6
        )
        for size in seen_sizes:
            for fixture in probe.fixtures():
                if size > 10 and not fixture["deep_case"]:
                    continue
                repetitions = [
                    r["repetition"]
                    for r in factory()
                    if r["kind"] == "DATA"
                    and r["result_limit"] == size
                    and r["fixture_id"] == fixture["fixture_id"]
                ]
                require(sorted(repetitions) == [0, 1])
        require(
            plan["budgets"]["data_observations"] == 512 + 32 * (len(seen_sizes) - 4)
        )
        require(
            plan["budgets"]["required_control_observations"]
            + plan["budgets"]["reserved_control_observations"]
            <= 16
        )


def verify_authorities(
    profile: dict[str, Any],
    plan: dict[str, Any],
    start: dict[str, Any],
    authority: Authority,
) -> None:
    validate_plan(plan, profile)
    validate(start, START)
    require(
        start["profile_sha256"] == digest(profile)
        and start["plan_sha256"] == digest(plan)
    )
    require(
        start["rule_bundle_sha256"] == profile["rule_bundle_sha256"]
        and start["policy_freeze_record_sha256"]
        == profile["policy_freeze_record_sha256"]
    )
    require(authority is not None)
    for field in (
        "policy_freeze_record_sha256",
        "implementation_authorization_sha256",
        "implementation_review_sha256",
        "initial_workload_authority_sha256",
    ):
        authority.require(
            field, start[field], {"profile": profile, "plan": plan, "start": start}
        )
    authority.require(
        "operator_allowance", profile["operator_allowance"]["record_sha256"], profile
    )
    authority.require("transport_profile", profile["transport_profile_sha256"], profile)
    authority.require("plan_selection", plan["selection_basis_sha256"], plan)
    for recipe in plan["control_recipes"]:
        authority.require(
            "control_recipe", recipe["implementation_contract_sha256"], recipe
        )
    for state in profile["states"]:
        authority.require("rate_state", state["evidence_sha256"], state)
    authority.require(
        "resources",
        profile["resources"]["resource_review_sha256"],
        profile["resources"],
    )
    if profile["resources"]["admission_memory_bytes"] != MEMORY:
        authority.require(
            "capacity_change",
            profile["resources"]["capacity_basis_sha256"],
            profile["resources"],
        )
    monitor = profile["monitoring"]
    authority.require(
        "monitoring",
        monitor.get("gaps_record_sha256", monitor.get("deployment_binding_sha256")),
        monitor,
    )


def descriptors() -> dict[str, dict[str, Any]]:
    return {
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

"""Explicit B2 operations contract for the shared bounded mechanics."""

from __future__ import annotations

from typing import Any, Iterable, Callable
from . import s12_b2_contract as b
from . import s12_public_operations as public
from . import s12_retrieval_contract as c
from . import s12_assets as assets
from . import s12_response as response
from . import s12_operations as v1

PROFILE, PLAN, START, EVENT, CONTROL_BEGIN, CONTROL_FINISH, REPORT, SNAPSHOT = (
    b.REGISTRY["names"][k]
    for k in (
        "PROFILE",
        "PLAN",
        "START",
        "EVENT",
        "CONTROL_BEGIN",
        "CONTROL_FINISH",
        "REPORT",
        "SNAPSHOT",
    )
)
SCOPE = "DEVELOPMENT_ONLY"
RULE_BUNDLE = b.DESIGN_SHA256
RESERVATION, MEMORY = public.RESERVATION, public.MEMORY
TYPES, SCHEMAS = b.TYPES, b.SCHEMAS
FAILURES = tuple(TYPES["ControlOutcome"]["enum"][1:])
COUNT_KEYS = public.COUNT_KEYS
Authority = public.Authority
require, uint, checked = b.require, b.uint, b.uint
validate, validate_type, parse, digest = b.validate, b.validate_type, b.parse, b.digest
interval, rate_le, manifest_digest = (
    public.interval,
    public.rate_le,
    public.manifest_digest,
)


def validate_profile(profile: dict[str, Any]) -> None:
    validate(profile, PROFILE)
    require(profile["rule_bundle_sha256"] == RULE_BUNDLE, "B2_POLICY_MISMATCH")
    require(profile["resource_sample_period_ms"] == 100, "B2_SAMPLING_RULE")
    baseline = assets.hashes()
    require(
        profile["preserved"]
        == {
            "operations_v1_sha256": baseline[v1.VERSION].hex(),
            "materialization_sha256": baseline[c.MATERIALIZATION].hex(),
            "response_validation_sha256": baseline[response.VALIDATION].hex(),
            "public_audit_source_sha256": "b43134525b99b60767d9661d334ccf743d101f06e85be42350483048a1c9d8f4",
        },
        "B2_BASELINE_MISMATCH",
    )
    r, a = profile["resources"], profile["operator_allowance"]
    require(
        a["connections"] <= 4
        and rate_le(a["rate_ceiling"], {"num": 60, "den": 1})
        and a["valid_from"] < a["valid_until"],
        "B2_ALLOWANCE_INVALID",
    )
    require(
        r["job_memory_bytes"]
        >= checked(
            r["admission_memory_bytes"]
            + r["pending_request_bytes"]
            + r["process_overhead_bytes"]
        ),
        "B2_MEMORY_BOUND",
    )
    require(bool(profile["states"]), "B2_RATE_INVALID")
    previous = None
    for i, state in enumerate(profile["states"], 1):
        require(
            state["state_id"] == i
            and 1
            <= state["admitted_operations"]
            <= state["connections"]
            <= a["connections"],
            "B2_ADMISSION_INVALID",
        )
        require(
            state["admitted_operations"] * RESERVATION <= r["admission_memory_bytes"],
            "B2_MEMORY_BOUND",
        )
        require(rate_le(state["rate"], a["rate_ceiling"]), "B2_RATE_INVALID")
        if previous is not None:
            require(
                rate_le(previous, state["rate"]) and previous != state["rate"],
                "B2_RATE_INVALID",
            )
        previous = state["rate"]
    admin = profile["administrative"]
    require(
        admin["max_record_bytes"] <= b.MAX_METADATA
        and admin["max_record_bytes"]
        <= admin["max_total_bytes"]
        <= r["allocated_disk_bytes"],
        "B2_ADMIN_BOUND",
    )


def budget(value: dict[str, Any]) -> None:
    validate_type(value, "Budget")
    require(value["reserved_control_observations"] == 0, "B2_NO_RESERVED_MONITOR")
    require(
        value["data_observations"]
        <= value["data_attempts"]
        <= 5 * value["data_observations"],
        "B2_ATTEMPT_BUDGET",
    )
    n = value["required_control_observations"]
    require(n <= value["control_http_attempts"] <= 5 * n, "B2_ATTEMPT_BUDGET")
    checked(value["data_attempts"] + value["control_http_attempts"])


def validate_plan(plan: dict[str, Any], profile: dict[str, Any]) -> None:
    validate_profile(profile)
    validate(plan, PLAN)
    require(plan["operations_profile_sha256"] == digest(profile), "B2_PLAN_BINDING")
    require(
        plan["window_plan_sha256"] == profile["monitoring"]["window_plan_sha256"],
        "B2_WINDOW_BINDING",
    )
    a, r = profile["operator_allowance"], profile["resources"]
    require(
        a["valid_from"]
        <= plan["window_start"]
        < plan["window_end"]
        <= a["valid_until"],
        "B2_PLAN_TIME",
    )
    require(
        1 <= plan["result_limit"] <= 40 and len(plan["blocks"]) == 1,
        "B2_WORKLOAD_INVALID",
    )
    budget(plan["budgets"])
    amounts = plan["budgets"]
    require(
        60_000 + r["scheduler_guard_ms"] + r["writer_guard_ms"]
        <= plan["shutdown_reserve_ms"]
        < amounts["active_duration_ms"],
        "B2_SHUTDOWN_BOUND",
    )
    require(
        amounts["storage_bytes"] <= r["allocated_disk_bytes"]
        and r["fixed_campaign_disk_bound_bytes"]
        + (amounts["data_attempts"] + amounts["control_http_attempts"])
        * r["per_attempt_disk_bound_bytes"]
        + profile["administrative"]["max_total_bytes"]
        <= amounts["storage_bytes"],
        "B2_STORAGE_BOUND",
    )
    block = plan["blocks"][0]
    require(
        block["block_id"] == 1
        and block["transition_from"] is None
        and block["first_work_id"] == 1
        and block["last_work_id"]
        == amounts["data_observations"] + amounts["required_control_observations"]
        and block["budget"] == amounts,
        "B2_BLOCK_INVALID",
    )
    require(1 <= block["state_id"] <= len(profile["states"]), "B2_RATE_INVALID")
    previous = profile["states"][block["state_id"] - 1]
    require(
        block["fallback_state_ids"]
        == sorted(set(block["fallback_state_ids"]), reverse=True),
        "B2_RATE_INVALID",
    )
    for sid in block["fallback_state_ids"]:
        require(1 <= sid < previous["state_id"], "B2_RATE_INVALID")
        lower = profile["states"][sid - 1]
        require(
            lower["connections"] <= previous["connections"]
            and lower["admitted_operations"] <= previous["admitted_operations"],
            "B2_ADMISSION_INVALID",
        )
        previous = lower
    require(
        [x["recipe_id"] for x in plan["control_recipes"]]
        == sorted({x["recipe_id"] for x in plan["control_recipes"]}),
        "B2_CONTROL_INVALID",
    )
    for recipe in plan["control_recipes"]:
        require(
            recipe["max_http_attempts_per_invocation"] <= 5
            and recipe["max_duration_ms"] <= 60000
            and recipe["transport_profile_sha256"]
            == profile["transport_profile_sha256"],
            "B2_CONTROL_INVALID",
        )


def work_rows(rows: Iterable[dict[str, Any]], plan: dict[str, Any]):
    recipes = {r["recipe_id"]: r for r in plan["control_recipes"]}
    count = data = controls = 0
    for count, row in enumerate(rows, 1):
        validate_type(row, "Work")
        require(row["work_id"] == count and row["block_id"] == 1, "B2_WORK_ORDER")
        if row["kind"] == "DATA":
            require(
                row["query_semantic_id"] is not None
                and row["result_limit"] == plan["result_limit"]
                and row["repetition"] == plan["repetition"]
                and row["recipe_id"] is None
                and row["retry_spacing_key"] == row["query_semantic_id"],
                "B2_WORK_BINDING",
            )
            data += 1
        else:
            require(
                row["query_semantic_id"]
                is row["result_limit"]
                is row["repetition"]
                is None
                and row["recipe_id"] in recipes
                and row["retry_spacing_key"]
                == recipes[row["recipe_id"]]["recipe_sha256"],
                "B2_CONTROL_INVALID",
            )
            controls += 1
        yield row
    require(
        count == plan["blocks"][0]["last_work_id"]
        and data == plan["budgets"]["data_observations"]
        and controls == plan["budgets"]["required_control_observations"],
        "B2_WORK_TOTALITY",
    )


def verify_work_manifest(factory: Callable, plan: dict[str, Any]) -> None:
    require(
        manifest_digest(work_rows(factory(), plan)) == plan["work_manifest_sha256"],
        "B2_WORK_MANIFEST",
    )


def verify_authorities(profile, plan, start, authority):
    validate_plan(plan, profile)
    validate(start, START)
    b.verify_executable_science(start)
    require(
        start["retrieval_policy_id"]
        == c.policy(plan["result_limit"])["retrieval_policy_id"].hex(),
        "B2_RETRIEVAL_POLICY_MISMATCH",
    )
    require(
        start["profile_sha256"] == digest(profile)
        and start["plan_sha256"] == digest(plan)
        and start["rule_bundle_sha256"] == RULE_BUNDLE
        and start["policy_freeze_record_sha256"]
        == profile["policy_freeze_record_sha256"],
        "B2_START_BINDING",
    )
    require(
        start["population_scope"] == plan["population_scope"]
        and start["window_plan_sha256"] == plan["window_plan_sha256"]
        and start["stage11_input_binding_sha256"]
        == plan["stage11_input_binding_sha256"],
        "B2_START_BINDING",
    )
    for key in (
        "window_plan_sha256",
        "privacy_permission_sha256",
        "scientific_decision_sha256",
    ):
        require(start[key] == profile["monitoring"][key], "B2_START_BINDING")
    require(authority is not None, "B2_AUTHORITY_REQUIRED")
    for key in (
        "policy_freeze_record_sha256",
        "implementation_authorization_sha256",
        "implementation_review_sha256",
        "initial_workload_authority_sha256",
        "scientific_campaign_start_sha256",
    ):
        authority.require(
            key, start[key], {"profile": profile, "plan": plan, "start": start}
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
        authority.require(
            key, value, {"profile": profile, "plan": plan, "start": start}
        )
    for state in profile["states"]:
        authority.require("rate_state", state["evidence_sha256"], state)
    if profile["resources"]["admission_memory_bytes"] != MEMORY:
        authority.require(
            "capacity_change",
            profile["resources"]["capacity_basis_sha256"],
            profile["resources"],
        )
    for recipe in plan["control_recipes"]:
        authority.require(
            "control_recipe", recipe["implementation_contract_sha256"], recipe
        )

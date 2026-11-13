"""RA-G1 scoped observations and logical limits, without strict M2 claims.

The schemas are successors. A shared-space observation is never an entitlement;
visible cgroup facts are never complete descendant or native allocation proof.
"""

from __future__ import annotations

from typing import Any, Callable, cast

from copy import deepcopy
import os
from pathlib import Path
import re
import stat
import sys
import time

from . import s12_public_operations as old
from . import s12_retrieval_contract as c
from . import s12_wf_ap2_assurance as strict

METHOD = "LOGICAL_LIMITS_AND_SCOPED_MONITORING"
POLICY = "stage12_resource_assurance_policy_ra_g1_v1"
BOUND = "stage12_resource_assurance_binding_ra_g1_v1"
SELECTION = "stage12_resource_selection_ra_g1_v1"
BOOTSTRAP_SELECTION = "stage12_resource_selection_bootstrap30_ra_g1_v1"
BOOTSTRAP_POLICY = "stage12_resource_bootstrap_prefix_policy_ra_g1_v1"
BOOTSTRAP_ADOPTION = "stage12_resource_bootstrap_prefix_adoption_ra_g1_v1"
BOOTSTRAP_EVIDENCE = "stage12_resource_bootstrap_prefix_ra_g1_v1"
BOOTSTRAP_LIMIT_NS = 30_000_000_000
BOOTSTRAP_ROLES = {6: "COLLECTOR", 7: "REVIEW", 1: "PHASE_RUNNER"}
CAPACITY = "stage12_resource_capacity_observation_ra_g1_v1"
CURRENT = "stage12_resource_current_facts_ra_g1_v1"
LOGICAL_BYTES, SCRATCH_BYTES = 16 * 2**20, 65536
# Historical record floor; actual current backing is checked at live activation.
LEGACY_LOGICAL_SCRATCH_BYTES = 64640
MIN_OTHER_LOGICAL = 393216
MAX_JOB_BYTES = 6 * 2**30  # Requested allocation only, never an observed bound.
ARENAS = strict.ARENAS
SCOPES = (
    "REPRESENTATIVE_NO_SERVICE",
    "PUBLIC_SYNTHETIC_ONLY",
    "DEVELOPMENT_LOCAL_PREPARATION",
    "DEVELOPMENT_ONLY",
)
ROLES = ("COLLECTOR", "BINDER", "PHASE_RUNNER", "MONITOR", "TERMINAL_VERIFIER")
UNKNOWN = {
    "status": old.enum("UNAVAILABLE", "NOT_PROVEN", "UNBOUNDED"),
    "reason": old.enum(
        "INACCESSIBLE", "NOT_EXPOSED", "NATIVE_UNCONTROLLED", "COVERAGE_UNESTABLISHED"
    ),
}
KNOWN = {
    "status": "=KNOWN",
    "value": "U",
    "origin": old.enum("KERNEL", "PROCESS", "FILESYSTEM"),
    "scope": old.enum(
        "SELF", "REGISTERED_VISIBLE", "VISIBLE_CGROUP", "FILESYSTEM_SHARED"
    ),
    "acquired_mono_ns": "U",
}
READING = {
    "tag": "status",
    "variants": {
        "KNOWN": KNOWN,
        **{
            k: {**UNKNOWN, "status": "=" + k}
            for k in ("UNAVAILABLE", "NOT_PROVEN", "UNBOUNDED")
        },
    },
}
SCHEMA = {
    "schema_version": "=" + BOUND,
    "scope": old.enum(*SCOPES),
    "method": "=" + METHOD,
    **old.fields(
        "policy_sha256:D adoption_sha256:D selection_sha256:D source_git_sha:G source_inventory_sha256:D runtime_inventory_sha256:D configuration_scope_sha256:D invocation_graph_sha256:D owner_reported_project_approval_sha256:D technical_review_sha256:D initial_environment_observation_sha256:D risk_inventory_sha256:D maximum_identity_checks:P maximum_original_read_calls:P maximum_original_read_bytes:P"
    ),
    "logical_allocations": [
        {"name": old.enum(*ARENAS), "bytes": "U", "evidence_sha256": "D"}
    ],
    **old.fields(
        "total_logical_bytes:P logical_scratch_bytes:P valid_from:Z valid_until:Z"
    ),
    "native_component_guarantee": "=NOT_CLAIMED",
    "job_domain_guarantee": "=NOT_ESTABLISHED",
    "physical_capacity_guarantee": "=NOT_RESERVED_OR_PROVEN",
}
MONITOR_SELECTION = {
    "period_ms": "=500",
    "max_observed_interval_ms": "=1000",
    **old.fields("self_rss_stop_bytes:P aggregate_rss_stop_bytes:P"),
    "visible_threads_stop": "=256",
    "native_visible_file_stop_bytes": "=8589934592",
    "shared_free_margin_bytes": "=1342177280",
    "free_inode_margin": "=4096",
    "scope": "=SELF_AND_REGISTERED_VISIBLE",
    "required_observation_set_sha256": "D",
}
PHASE_LIMITS = old.fields(
    "id:ID phase:P deadline_ms:P reserve_ms:P attempts:U events:U logical_write_bytes:P creations:P source_read_calls:P source_read_bytes:P check_calls:P"
)
LIMITS: dict[str, Any] = {
    **old.fields(
        "processing_ms:P scheduler_s:P processes:P threads:P utilities:U python_invocations:P input_bytes:P metadata_bytes:P attempts:U logical_write_bytes:P creations:P telemetry_chunks:P telemetry_bytes:P telemetry_creations:P monitor_rows:P monitor_bytes:P monitor_creations:P closure_reserve_bytes:P closure_reserve_creations:P native_invocations:U"
    ),
    "python_roles": [{"role": old.enum(*ROLES), "maximum": "P"}],
    "stages": [PHASE_LIMITS],
    "application_counters": {
        key: "U"
        for key in (
            "SQLITE DUCKDB PARQUET_FILE RAW_PACK_FILE COMPRESSED_FRAME CANDIDATE_BUFFER EXCLUSIVE_FILE EVENT_FILE PREFIX_FILE COMPARISON_FILE ADMIN_FILE CONTROL_BEGIN CONTROL_FINISH"
        ).split()
    },
}
SELECTION_SCHEMA = {
    "schema_version": "=" + SELECTION,
    "scope": old.enum(*SCOPES),
    **old.fields(
        "policy_sha256:D adoption_sha256:D source_git_sha:G descriptor_inventory_sha256:D workload_graph_sha256:D"
    ),
    "limits": LIMITS,
    "monitor": MONITOR_SELECTION,
    **old.fields(
        "authority_requirement_inventory_sha256:D paths_sha256:D valid_from:Z valid_until:Z review_sha256:D"
    ),
}
BOOTSTRAP_SELECTION_SCHEMA = {
    **SELECTION_SCHEMA, "schema_version": "=" + BOOTSTRAP_SELECTION,
    "bootstrap_prefix_policy_sha256": "D", "bootstrap_prefix_adoption_sha256": "D",
}

REP_ADMIN_SELECTION = "stage12_resource_selection_rep_admin_budget_ra_g1_v1"
REP_ADMIN_POLICY = "stage12_rep_admin_budget_policy_ra_g1_v1"
REP_ADMIN_ADOPTION = "stage12_advisory_delegated_rep_admin_budget_continuation_v1"
REP_ADMIN_SECONDS = dict(collector=120, factual_review=480, binder_complete=240,
                         combined_binder_watchdog=720)
REP_ADMIN_SELECTION_SCHEMA = {
    **BOOTSTRAP_SELECTION_SCHEMA, "schema_version": "=" + REP_ADMIN_SELECTION,
    "rep_admin_budget_policy_sha256": "D", "rep_admin_budget_adoption_sha256": "D",
}
REP_ADMIN_ADOPTION_SCHEMA = {
    "schema_version": "=" + REP_ADMIN_ADOPTION,
    "additional_prospective_units": "=128", "administrator_attestation": "B",
    "adopted_representative_admin_seconds": {key: "=" + str(value) for key, value in REP_ADMIN_SECONDS.items()},
    "baseline": "G", "binder_operational_publication_target_seconds": "=180",
    "binder_remaining_suffix_target_seconds": "=60", "cumulative_ceiling": "=704",
    "direct_owner_detailed_statement_claimed": "B", "existing_conditional_public_unconsumed": "=2",
    "historical_job1811762": "=FAILED_INCOMPLETE_WAIT_RELEASE_CONTENT_PASS_LATE_PUBLICATION_NO_B_UNCHANGED",
    "independent_advisory_authentication": "B", "input_manifest_sha256": "D",
    "new_allocation_grant": {"consumed": "=0", "id": "=REPRESENTATIVE_ADMIN_BUDGET_SUCCESSOR_ONE",
        "maximum": "=1", "only_after_focused_verification_and_all_current_gates": "B",
        "replacement_requeue_A_rerun": "B"},
    "no_new_public_or_protected_slots": "B", "original_anchors_nonresetting": "B",
    "original_recommendation_sha256": "D", "previous_cumulative_ceiling": "=576",
    "prior_charged_actual_or_possible": "=512",
    "provenance": "=ACTUAL_USER_RELAY_OF_GPT6_ASTRA_ULTRA_RECOMMENDATION_UNDER_STANDING_HUMAN_DELEGATION",
    "public_operating_budgets_unchanged": "B", "recorded_utc": "=2026-11-10T06:16:57.603990+00:00",
    "remaining_assigned_prospectively": "=192",
    "unchanged_seconds": {"B": "=7200", "processing": "=8160", "scheduler": "=8400", "terminal_verifier": "=120"},
    "unchanged_window_end": "=2026-11-11T19:13:21.620987Z",
}


REP512_SELECTION = "stage12_resource_selection_rep_first64_512_ra_g1_v1"
REP512_POLICY = "stage12_rep_first64_512_policy_ra_g1_v1"
REP512_ADOPTION = "stage12_advisory_delegated_rep_first64_512_adoption_v1"
REP_FOREGROUND_SELECTION = "stage12_resource_selection_rep_foreground_ra_g1_v1"
REP512_SELECTIONS = (REP512_SELECTION, REP_FOREGROUND_SELECTION)
REP_ADMIN_SELECTIONS = (REP_ADMIN_SELECTION, *REP512_SELECTIONS)
REP512_SELECTION_SCHEMA = {
    **REP_ADMIN_SELECTION_SCHEMA, "schema_version": "=" + REP512_SELECTION,
    "rep_first64_512_policy_sha256": "D", "rep_first64_512_adoption_sha256": "D",
}
REP_FOREGROUND_SELECTION_SCHEMA = {
    **REP512_SELECTION_SCHEMA, "schema_version": "=" + REP_FOREGROUND_SELECTION,
}
REP512_ADOPTION_SCHEMA = {
    "schema_version":"=" + REP512_ADOPTION, "scope":"=REPRESENTATIVE_NO_SERVICE",
    "policy_sha256":"D", "original_recommendation_sha256":"D", "recorded_utc":"Z",
    "baseline_source":"=982cc871169fcb8215c163b8ed141965c829cd20",
    "baseline_manifest_sha256":"=d1d473f241a1192004349629701524f5872ba1130f50d1d467781b7de6645ceb",
    "derivation_sha256":"=59fe61efaca6187ee954f0cc9126be44b1e1388badba87598a66e2bbf0299d83",
    "provenance":"=ACTUAL_USER_RELAY_OF_GPT6_ASTRA_ULTRA_RECOMMENDATION_UNDER_STANDING_HUMAN_DELEGATION",
    "administrator_attestation":"B", "direct_owner_numerical_statement_claimed":"B",
    "prospective_only":"B", "historical_346_unchanged":"B",
    "other_stage_caps_unchanged":"B", "public_protected_budgets_unchanged":"B",
    "workload_authority_issued":"B",
}


def rep512_policy_descriptor() -> Any:
    return dict(descriptor_version=REP512_POLICY, closed=True, live_instance=False,
        scope="REPRESENTATIVE_NO_SERVICE", first64_ms=512000,
        phase1_observations=10242, phase1_sampling_event_tokens=20488,
        phase1_events=26608, phase1_creations=77767,
        global_event_files=57237, global_creations=204860,
        whole_task_creations=30177, other_phase_and_administrative_caps="UNCHANGED",
        logical_write_bytes=72 * 2**30, monitor_rows=16342, telemetry_chunks=1500,
        first64_hold_regular_acks=1817, shutdown_reserve_ms=80000,
        originals_and_deadline_origins="PRESERVED_NONRESETTING",
        public_and_protected="UNCHANGED_NO_AUTHORITY_ISSUED",
        historical_346="ORIGINAL_FAMILY_REMAINS_EXACT")


def validate_rep512_adoption(value: Any, selected: Any) -> Any:
    shape(value, REP512_ADOPTION_SCHEMA)
    c.require(value["administrator_attestation"] is False
        and value["direct_owner_numerical_statement_claimed"] is False
        and value["prospective_only"] is True and value["historical_346_unchanged"] is True
        and value["other_stage_caps_unchanged"] is True
        and value["public_protected_budgets_unchanged"] is True
        and value["workload_authority_issued"] is False
        and value["policy_sha256"] == old.digest(rep512_policy_descriptor())
        and selected["rep_first64_512_policy_sha256"] == value["policy_sha256"]
        and selected["rep_first64_512_adoption_sha256"] == old.digest(value),
        "RA_G1_SELECTION_BINDING")
    return value


def rep_admin_policy_descriptor() -> Any:
    return dict(descriptor_version=REP_ADMIN_POLICY, closed=True, live_instance=False,
        scope="REPRESENTATIVE_NO_SERVICE", administrative_seconds=REP_ADMIN_SECONDS,
        unchanged_seconds=dict(B=7200, terminal_verifier=120, processing=8160, scheduler=8400),
        role_anchors="ORIGINAL_ROLE_ENTRY_AND_BIND_ENTER_NONRESETTING",
        binder_scope="PREPARATION_REVIEW_PUBLICATION_VALIDATION_REOPENING_AND_CLOSURE",
        publication_target_seconds=180, remaining_suffix_target_seconds=60,
        operational_targets="NOT_DEADLINE_REPLACEMENTS_OR_COMPLETION_GUARANTEES",
        public_operating_budgets="UNCHANGED", original_adoption="DISTINCT_RETAINED_AUTHORITY_RECORD",
        service_authority="NOT_ISSUED", protected_authority="NOT_ISSUED")


def validate_rep_admin_adoption(value: Any, selected: Any) -> Any:
    from . import s12_ra_g1_windows as windows
    if windows.is_window_adoption(value):
        return windows.validate_adoption(value, selected,
            original_validator=validate_rep_admin_adoption,
            budget_policy_sha256=old.digest(rep_admin_policy_descriptor()))
    shape(value, REP_ADMIN_ADOPTION_SCHEMA)
    c.require(
        value["administrator_attestation"] is False
        and value["direct_owner_detailed_statement_claimed"] is False
        and value["independent_advisory_authentication"] is False
        and value["new_allocation_grant"]["only_after_focused_verification_and_all_current_gates"] is True
        and value["new_allocation_grant"]["replacement_requeue_A_rerun"] is False
        and value["no_new_public_or_protected_slots"] is True
        and value["original_anchors_nonresetting"] is True
        and value["public_operating_budgets_unchanged"] is True
        and old.digest(value) == selected["rep_admin_budget_adoption_sha256"]
        and selected["rep_admin_budget_policy_sha256"] == old.digest(rep_admin_policy_descriptor()),
        "RA_G1_SELECTION_BINDING",
    )
    if "valid_until" in selected:
        c.require(selected["valid_until"] <= value["unchanged_window_end"], "RA_G1_EXPIRED")
    return value

BOOTSTRAP_ADOPTION_SCHEMA = {
    "schema_version": "=" + BOOTSTRAP_ADOPTION,
    "scope": "=REPRESENTATIVE_NO_SERVICE", "policy_sha256": "D",
    "owner_decision_original_sha256": "D", "owner_decision_canonical_sha256": "D",
    "provenance": "=CURRENT_USER_DIRECT_RELAY_NOT_INDEPENDENT_AUTHENTICATION",
    "prospective_only": "B", "startup_ceiling_ns": "U",
    "historical_job1811420_cause": "=UNKNOWN",
}
BOOTSTRAP_EVIDENCE_SCHEMA = {
    "schema_version": "=" + BOOTSTRAP_EVIDENCE,
    "scope": "=REPRESENTATIVE_NO_SERVICE",
    "role": old.enum("COLLECTOR", "REVIEW", "PHASE_RUNNER"),
    **old.fields("binding_sha256:D selection_sha256:D bootstrap_policy_sha256:D bootstrap_adoption_sha256:D root_identity_inventory_sha256:D phase_id:P source_entry_mono_ns:U bootstrap_end_mono_ns:U phase_deadline_mono_ns:U first_start_seq:P first_start_record_sha256:D first_start_original_sha256:D first_start_enter_mono_ns:U first_start_exit_mono_ns:U first_start_ack_mono_ns:U"),
    "adoption_original": BOOTSTRAP_ADOPTION_SCHEMA,
    "unmonitored_prefix": "=OWNER_ACCEPTED_PROSPECTIVE_ONLY",
    "monitor_scope_start": "=ACTUAL_BOOTSTRAP_END",
}

CAPACITY_SCHEMA = {
    "schema_version": "=" + CAPACITY,
    "scope": old.enum(*SCOPES),
    **old.fields(
        "selection_sha256:D owner_reported_approval_sha256:D observed_utc:Z root_identity_inventory_sha256:D filesystem_originals_sha256:D accounting_method_sha256:D"
    ),
    "bavail_bytes": READING,
    "favail": READING,
    "physical_accounting_coverage": old.enum(
        "VISIBLE_LINKED_ONLY", "UNKNOWN_NATIVE_OR_DELETED_OPEN"
    ),
    "assurance": "=BEST_EFFORT_SHARED_SNAPSHOT",
    "entitlement": "=NOT_ASSERTED",
    "reservation": "=NONE",
    "restrictions_inventory_sha256": "D",
}
FACTS = {
    "schema_version": "=" + CURRENT,
    "origin": old.enum("LIVE_KERNEL_OBSERVATION", "SYNTHETIC_TEST_ONLY"),
    "observation_inventory_sha256": "D",
    "visible_identity_inventory_sha256": "D",
    "boot_id": "UUID",
    "cgroup_namespace_inode": "P",
    "mount_namespace_inode": "P",
    "visible_membership_sha256": "D",
    "memory_max_bytes": READING,
    "memory_high_bytes": READING,
    "swap_max_bytes": READING,
    "pids_max": READING,
    "ancestor_coverage": "=NOT_ESTABLISHED",
    "descendant_coverage": "=NOT_ESTABLISHED",
    "native_maximum": "=NOT_PROVEN",
    "physical_capacity": "=NOT_RESERVED_OR_PROVEN",
}


def shape(value: Any, spec: Any) -> Any:
    """Closed bounded schema engine; bool is never accepted as an integer."""
    if isinstance(spec, dict):
        if "enum" in spec:
            c.require(type(value) is str and value in spec["enum"], "RA_G1_FIELDS")
        elif "tag" in spec:
            c.require(
                type(value) is dict and value.get(spec["tag"]) in spec["variants"],
                "RA_G1_FIELDS",
            )
            shape(value, spec["variants"][value[spec["tag"]]])
        else:
            c.require(type(value) is dict and set(value) == set(spec), "RA_G1_FIELDS")
            for key, child in spec.items():
                shape(value[key], child)
    elif isinstance(spec, list):
        maximum = 643 if spec[0] is PHASE_LIMITS else 64
        c.require(type(value) is list and len(value) <= maximum, "RA_G1_RECORD_LIMIT")
        for row in value:
            shape(row, spec[0])
    elif type(spec) is str and spec.endswith("?"):
        if value is not None:
            shape(value, spec[:-1])
    elif spec == "UUID":
        c.require(
            type(value) is str and re.fullmatch(r"[0-9a-f]{32}", value) is not None,
            "RA_G1_FIELDS",
        )
    elif spec == "S":
        c.require(
            type(value) is str and value.isascii() and len(value) <= 1024,
            "RA_G1_FIELDS",
        )
    elif type(spec) is str and spec.startswith("=") and spec[1:].isdecimal():
        c.require(type(value) is int and value == int(spec[1:]), "RA_G1_FIELDS")
    else:
        old.validate_type(value, spec)
        if spec in ("D", "G"):
            c.require(set(value) != {"0"}, "RA_G1_UNKNOWN")


def known(value: Any, origin: Any, scope: Any, acquired_mono_ns: Any) -> Any:
    result = dict(
        status="KNOWN",
        value=value,
        origin=origin,
        scope=scope,
        acquired_mono_ns=acquired_mono_ns,
    )
    shape(result, READING)
    return result


def unknown(status: Any = "NOT_PROVEN", reason: Any = "COVERAGE_UNESTABLISHED") -> Any:
    result = dict(status=status, reason=reason)
    shape(result, READING)
    return result


# Adopted whole-allocation permission ceilings, not observed/native maxima.
SCOPE_CEILINGS: dict[str, dict[str, int]] = {
    "REPRESENTATIVE_NO_SERVICE": dict(
        processing_ms=8160000,
        scheduler_s=8400,
        attempts=535,
        logical_write_bytes=72 * 2**30,
        creations=184184,
        telemetry_chunks=1500,
        telemetry_bytes=2 * 1500 * 32768,
        telemetry_creations=1501,
        monitor_rows=16342,
        monitor_bytes=268173312,
        monitor_creations=32736,
        native_invocations=0,
    ),
    "PUBLIC_SYNTHETIC_ONLY": dict(
        processing_ms=8160000,
        scheduler_s=8400,
        attempts=2960,
        logical_write_bytes=512 * 2**30,
        creations=791452,
        telemetry_chunks=2980,
        telemetry_bytes=2 * 2980 * 32768,
        telemetry_creations=2981,
        monitor_rows=16352,
        monitor_bytes=268500992,
        monitor_creations=32776,
        native_invocations=0,
    ),
    "DEVELOPMENT_LOCAL_PREPARATION": dict(
        processing_ms=7200000,
        scheduler_s=7440,
        attempts=0,
        logical_write_bytes=148684001247232,
        telemetry_chunks=1500,
        telemetry_bytes=2 * 1500 * 32768,
        telemetry_creations=1501,
        monitor_rows=14410,
        monitor_bytes=236322816,
        monitor_creations=28848,
    ),
    "DEVELOPMENT_ONLY": dict(
        processing_ms=7200000,
        scheduler_s=7440,
        attempts=1100050,
        logical_write_bytes=148684001247232,
        telemetry_chunks=1500,
        telemetry_bytes=2 * 1500 * 32768,
        telemetry_creations=1501,
        monitor_rows=14410,
        monitor_bytes=236322816,
        monitor_creations=28848,
    ),
}


def validate_scope_ceilings(record: Any) -> None:
    limits, scope = record["limits"], record["scope"]
    ceilings = SCOPE_CEILINGS[scope]
    if record.get("schema_version") in REP512_SELECTIONS:
        c.require(scope == "REPRESENTATIVE_NO_SERVICE", "RA_G1_SCOPE")
        ceilings = {**ceilings, "creations":204860}
    for key, maximum in ceilings.items():
        c.require(limits[key] <= maximum, "RA_G1_ADOPTED_CEILING")
    c.require(
        limits["closure_reserve_bytes"] == 256 * 2**20
        and limits["closure_reserve_creations"] == 4096
        and limits["logical_write_bytes"] >= limits["closure_reserve_bytes"]
        and limits["creations"] >= limits["closure_reserve_creations"],
        "RA_G1_CLOSURE_RESERVE",
    )
    c.require(
        0 <= limits["scheduler_s"] * 1000 - limits["processing_ms"] <= 240000,
        "RA_G1_DEADLINE",
    )
    c.require(
        sum(row["deadline_ms"] for row in limits["stages"]) <= limits["processing_ms"],
        "RA_G1_DEADLINE",
    )
    stage_caps: tuple[int, ...]
    if scope == "REPRESENTATIVE_NO_SERVICE":
        stage_caps = (
            512000 if record.get("schema_version") in REP512_SELECTIONS else 346000,
            300000,
            180000,
            180000,
            6194000,
            120000,
            480000 if record.get("schema_version") in REP_ADMIN_SELECTIONS else 600000,
            240000 if record.get("schema_version") in REP_ADMIN_SELECTIONS else 120000,
            120000,
        )
        science_stages = 4
    elif scope == "PUBLIC_SYNTHETIC_ONLY":
        stage_caps = (500000,) * 10 + (180000, 2020000, 840000, 120000)
        science_stages = 11
    else:
        stage_caps = (7200000,) * 643
        science_stages = 643
    c.require(
        len(limits["stages"]) <= len(stage_caps)
        and all(
            row["deadline_ms"] <= maximum
            for row, maximum in zip(limits["stages"], stage_caps)
        ),
        "RA_G1_ADOPTED_CEILING",
    )
    c.require(
        all(
            row["attempts"] == row["events"] == 0
            for row in limits["stages"][science_stages:]
        ),
        "RA_G1_ADMIN_SCOPE",
    )
    c.require(
        limits["telemetry_bytes"] <= old.checked(2 * limits["telemetry_chunks"] * 32768)
        and limits["telemetry_creations"] <= limits["telemetry_chunks"] + 1,
        "RA_G1_TELEMETRY_LIMIT",
    )

    monitor_scopes = (
        9
        if scope == "REPRESENTATIVE_NO_SERVICE"
        else (14 if scope == "PUBLIC_SYNTHETIC_ONLY" else 3)
    )
    c.require(
        limits["monitor_bytes"]
        >= old.checked(
            16384 * limits["monitor_rows"] + 8192 * (4 * monitor_scopes + 16)
        )
        and limits["monitor_creations"]
        >= old.checked(2 * limits["monitor_rows"] + 4 * monitor_scopes + 16),
        "RA_G1_MONITOR_PRECHARGE",
    )
    c.require(
        limits["logical_write_bytes"]
        >= old.checked(
            limits["telemetry_bytes"]
            + limits["monitor_bytes"]
            + limits["closure_reserve_bytes"]
        )
        and limits["creations"]
        >= old.checked(
            limits["telemetry_creations"]
            + limits["monitor_creations"]
            + limits["closure_reserve_creations"]
        ),
        "RA_G1_PRECHARGE",
    )


def validate_selection(record: Any) -> Any:
    shape(record, REP_FOREGROUND_SELECTION_SCHEMA if record.get("schema_version") == REP_FOREGROUND_SELECTION
          else REP512_SELECTION_SCHEMA if record.get("schema_version") in REP512_SELECTIONS
          else REP_ADMIN_SELECTION_SCHEMA if record.get("schema_version") == REP_ADMIN_SELECTION
          else BOOTSTRAP_SELECTION_SCHEMA if record.get("schema_version") == BOOTSTRAP_SELECTION else SELECTION_SCHEMA)
    if record["schema_version"] in (BOOTSTRAP_SELECTION, *REP_ADMIN_SELECTIONS):
        c.require(record["scope"] == "REPRESENTATIVE_NO_SERVICE"
                  and record["bootstrap_prefix_policy_sha256"] == old.digest(bootstrap_policy_descriptor()),
                  "RA_G1_BOOTSTRAP_POLICY")
    if record["schema_version"] in REP_ADMIN_SELECTIONS:
        c.require(record["rep_admin_budget_policy_sha256"] == old.digest(rep_admin_policy_descriptor()), "RA_G1_SELECTION_BINDING")
    if record["schema_version"] in REP512_SELECTIONS:
        c.require(record["rep_first64_512_policy_sha256"] == old.digest(rep512_policy_descriptor()), "RA_G1_SELECTION_BINDING")
    c.require(record["valid_from"] < record["valid_until"], "RA_G1_EXPIRED")
    limits = record["limits"]
    validate_scope_ceilings(record)
    if record["schema_version"] in REP512_SELECTIONS:
        signatures = [
            (512000,80000,320,26608,43419598848,77767),
            (300000,80000,160,15088,21805826048,44478),
            (180000,80000,40,8008,5621055488,24369),
            (180000,80000,15,7533,2265612288,23293),
            (120000,5000,0,0,16777216,30177),
            (120000,5000,0,0,16777216,760),
            (480000,5000,0,0,33554432,2008),
            (240000,5000,0,0,16777216,2008),
        ]
        keys = ("deadline_ms","reserve_ms","attempts","events","logical_write_bytes","creations")
        c.require(len(limits["stages"]) == len(signatures)
            and [tuple(row[key] for key in keys) for row in limits["stages"]] == signatures
            and limits["creations"] == 204860
            and limits["application_counters"]["EVENT_FILE"] == 57237
            and limits["application_counters"]["EXCLUSIVE_FILE"] == 204860,
            "RA_G1_SELECTION_BINDING")
    c.require(
        limits["processes"] == 4
        and limits["threads"] == 256
        and limits["utilities"] <= 256
        and limits["python_invocations"] == 5,
        "RA_G1_PROCESS_LIMIT",
    )
    c.require(
        limits["python_roles"] == [{"role": role, "maximum": 1} for role in ROLES],
        "RA_G1_PROCESS_LIMIT",
    )
    rows = limits["stages"]
    c.require(
        1 <= len(rows) <= 643
        and [row["id"] for row in rows] == list(range(1, len(rows) + 1)),
        "RA_G1_STAGE_LIMIT",
    )
    c.require(
        all(
            row["reserve_ms"] < row["deadline_ms"] <= limits["processing_ms"]
            for row in rows
        ),
        "RA_G1_DEADLINE",
    )
    for phase_field, root_field in (
        ("attempts", "attempts"),
        ("logical_write_bytes", "logical_write_bytes"),
        ("creations", "creations"),
    ):
        c.require(
            old.checked(sum(row[phase_field] for row in rows)) <= limits[root_field],
            "RA_G1_PRECHARGE",
        )
    c.require(
        limits["processing_ms"] <= limits["scheduler_s"] * 1000
        and limits["closure_reserve_bytes"] >= 256 * 2**20,
        "RA_G1_PRECHARGE",
    )
    c.require(
        limits["monitor_rows"] >= 2
        and limits["monitor_bytes"] >= limits["monitor_rows"] * 1024
        and limits["monitor_creations"] >= 1,
        "RA_G1_PRECHARGE",
    )
    monitor = record["monitor"]
    expected = (
        768 * 2**20 if record["scope"] == "REPRESENTATIVE_NO_SERVICE" else 5 * 2**30
    )
    c.require(
        monitor["aggregate_rss_stop_bytes"] == expected
        and monitor["self_rss_stop_bytes"] <= expected,
        "RA_G1_MONITOR_SELECTION",
    )
    c.require(
        limits["telemetry_chunks"]
        <= (2980 if record["scope"] == "PUBLIC_SYNTHETIC_ONLY" else 1500),
        "RA_G1_TELEMETRY_LIMIT",
    )
    return record


def validate_record(
    record: Any,
    profile: Any,
    start: Any,
    contract: Any,
    configuration_scope_sha256: Any = None,
) -> Any:
    shape(record, SCHEMA)
    c.require(
        (
            record["scope"] == contract.SCOPE
            or record["scope"] == "REPRESENTATIVE_NO_SERVICE"
            and contract.SCOPE == "PUBLIC_SYNTHETIC_ONLY"
        )
        and record["valid_from"] < record["valid_until"],
        "RA_G1_SCOPE",
    )
    c.require(
        old.digest(record) == profile["sampling_runtime_bound_sha256"]
        and record["source_git_sha"] == start["client_git_sha"]
        and record["runtime_inventory_sha256"] == start["runtime_inventory_sha256"],
        "RA_G1_SOURCE_BINDING",
    )
    c.require(profile["sampling_assurance_method"] == METHOD, "RA_G1_METHOD")
    if configuration_scope_sha256 is not None:
        c.require(
            record["configuration_scope_sha256"] == configuration_scope_sha256,
            "RA_G1_CONFIGURATION_BINDING",
        )
    allocations = record["logical_allocations"]
    c.require(
        [row["name"] for row in allocations] == list(ARENAS), "RA_G1_LOGICAL_INVENTORY"
    )
    by_name = {row["name"]: row["bytes"] for row in allocations}
    c.require(
        old.checked(sum(by_name.values()))
        == record["total_logical_bytes"]
        <= LOGICAL_BYTES
        and by_name["SAMPLE_SLOTS"] >= 65536
        and by_name["HISTORY_PAGES"] == 8 * 2**20
        and by_name["TELEMETRY_RING"] >= 4096 * 512
        and by_name["SERIALIZATION_SCRATCH"] == record["logical_scratch_bytes"]
        and LEGACY_LOGICAL_SCRATCH_BYTES <= record["logical_scratch_bytes"] <= SCRATCH_BYTES
        and by_name["TRACE_METADATA"] >= 32768
        and by_name["CONTROLLER_METADATA"] >= 16384
        and by_name["OTHER_LOGICAL"] >= MIN_OTHER_LOGICAL,
        "RA_G1_LOGICAL_LIMIT",
    )
    return record


def validate_capacity(
    record: Any, *, selection_sha256: Any = None, scope: Any = None
) -> Any:
    shape(record, CAPACITY_SCHEMA)
    if selection_sha256 is not None:
        c.require(
            record["selection_sha256"] == selection_sha256, "RA_G1_CAPACITY_BINDING"
        )
    if scope is not None:
        c.require(record["scope"] == scope, "RA_G1_SCOPE")
    for key in ("bavail_bytes", "favail"):
        reading = record[key]
        c.require(
            reading["status"] == "KNOWN"
            and reading["origin"] == "FILESYSTEM"
            and reading["scope"] == "FILESYSTEM_SHARED",
            "RA_G1_CAPACITY_UNAVAILABLE",
        )
    return record


def check_capacity(
    record: Any,
    *,
    next_write_bytes: Any = 0,
    next_creations: Any = 0,
    now_mono_ns: Any = None,
) -> Any:
    validate_capacity(record)
    if now_mono_ns is not None:
        old.uint(now_mono_ns)
        c.require(
            all(
                0 <= now_mono_ns - record[key]["acquired_mono_ns"] <= 1_000_000_000
                for key in ("bavail_bytes", "favail")
            ),
            "RA_G1_CAPACITY_STALE",
        )
    old.uint(next_write_bytes)
    old.uint(next_creations)
    c.require(
        record["bavail_bytes"]["value"] >= old.checked(next_write_bytes + 1342177280)
        and record["favail"]["value"] >= old.checked(next_creations + 4096),
        "RA_G1_SHARED_MARGIN",
    )
    return record


def verify_runtime(record: Any, authority: Any, context: Any) -> Any:
    # Historical records remain readable; live execution must charge this source.
    from .s12_wf_ap2_scratch import RA_G1_CAPS

    c.require(
        sum(RA_G1_CAPS.values()) <= record["logical_scratch_bytes"] <= SCRATCH_BYTES,
        "RA_G1_LOGICAL_LIMIT",
    )
    if record["scope"] == "REPRESENTATIVE_NO_SERVICE":
        c.require(
            getattr(authority, "diagnostic_scope", None) == "REPRESENTATIVE_NO_SERVICE"
            and getattr(authority, "service_authority", None) is False,
            "RA_G1_REPRESENTATIVE_SCOPE",
        )
    facts = verify_current_facts(record, authority)
    for role, field in (
        ("resource_policy", "policy_sha256"),
        ("resource_adoption", "adoption_sha256"),
        ("resource_selection", "selection_sha256"),
        ("resource_technical_review", "technical_review_sha256"),
        ("resource_invocation_graph", "invocation_graph_sha256"),
        ("resource_risk_inventory", "risk_inventory_sha256"),
        ("owner_reported_project_approval", "owner_reported_project_approval_sha256"),
    ):
        authority.require(role, record[field], context)
    provider: Any = getattr(authority, "resource_selection", None)
    c.require(callable(provider), "RA_G1_SELECTION_REQUIRED")
    selected = validate_selection(provider(record))
    c.require(
        old.digest(selected) == record["selection_sha256"]
        and selected["scope"] == record["scope"]
        and selected["policy_sha256"] == record["policy_sha256"]
        and selected["adoption_sha256"] == record["adoption_sha256"]
        and selected["source_git_sha"] == record["source_git_sha"],
        "RA_G1_SELECTION_BINDING",
    )
    limits = [
        facts[key]["value"]
        for key in ("memory_max_bytes", "memory_high_bytes")
        if facts[key]["status"] == "KNOWN"
    ]
    c.require(
        not limits or selected["monitor"]["aggregate_rss_stop_bytes"] <= min(limits),
        "RA_G1_LOWER_LIMIT",
    )
    provider = getattr(authority, "capacity_observation", None)
    c.require(callable(provider), "RA_G1_CAPACITY_REQUIRED")
    capacity = provider(record)
    validate_capacity(
        capacity, selection_sha256=record["selection_sha256"], scope=record["scope"]
    )
    check_capacity(capacity)
    if "profile" in context:
        resources = context["profile"]["resources"]
        c.require(
            resources["resource_selection_sha256"] == record["selection_sha256"]
            and resources["initial_capacity_observation_sha256"]
            == old.digest(capacity),
            "RA_G1_CAPACITY_BINDING",
        )
    return facts


def verify_current_facts(record: Any, authority: Any) -> Any:
    shape(record, SCHEMA)
    charge: Any = getattr(authority, "charge_identity_check", None)
    provider: Any = getattr(authority, "resource_facts", None)
    c.require(callable(charge) and callable(provider), "RA_G1_CURRENT_REQUIRED")
    charge(record)
    c.require(
        getattr(authority, "configuration_scope_sha256", None)
        == record["configuration_scope_sha256"],
        "RA_G1_CONFIGURATION_BINDING",
    )
    clock = getattr(authority, "clock", None)
    c.require(
        clock is not None
        and record["valid_from"] <= clock.utc() < record["valid_until"],
        "RA_G1_EXPIRED",
    )
    facts = provider(record)
    shape(facts, FACTS)
    c.require(
        facts["origin"] == "LIVE_KERNEL_OBSERVATION"
        or getattr(authority, "test_only", False) is True,
        "RA_G1_SYNTHETIC_DENIED",
    )
    initial: Any = getattr(authority, "initial_resource_facts", None)
    c.require(callable(initial), "RA_G1_INITIAL_REQUIRED")
    original = initial(record)
    shape(original, FACTS)
    c.require(
        old.digest(original) == record["initial_environment_observation_sha256"],
        "RA_G1_INITIAL_BINDING",
    )
    for field in FACTS.keys() - {
        "observation_inventory_sha256",
        "memory_max_bytes",
        "memory_high_bytes",
        "swap_max_bytes",
        "pids_max",
    }:
        c.require(facts[field] == original[field], "RA_G1_VISIBLE_DOMAIN_CHANGED")
    for field in (
        "memory_max_bytes",
        "memory_high_bytes",
        "swap_max_bytes",
        "pids_max",
    ):
        a, b = facts[field], original[field]
        c.require(
            {k: v for k, v in a.items() if k != "acquired_mono_ns"}
            == {k: v for k, v in b.items() if k != "acquired_mono_ns"},
            "RA_G1_VISIBLE_DOMAIN_CHANGED",
        )
    c.require(
        all(
            facts[key]["status"] in ("KNOWN", "UNBOUNDED")
            for key in ("memory_max_bytes", "memory_high_bytes", "swap_max_bytes")
        ),
        "RA_G1_VISIBLE_REQUIRED",
    )
    return facts


def configuration_scope(config: Any, *, plan: Any = None) -> Any:
    """Acyclic projection removes only the successor binding pointer."""
    if "runtime" in config:
        # Protected command scope preserves all source, method and resources.
        from . import s12_b2_ra_g1_resources as resources

        c.require(plan is not None, "RA_G1_CONFIGURATION_BINDING")
        return cast(Callable[..., Any], resources.configuration_scope)(
            config, plan=plan
        )
    value = deepcopy(config)
    for campaign in value.get("campaigns", ()):
        profile = campaign.get("profile")
        c.require(
            type(profile) is dict
            and profile.get("sampling_assurance_method") == METHOD,
            "RA_G1_METHOD",
        )
        profile.pop("sampling_runtime_bound_sha256", None)
        if type(campaign.get("plan")) is dict:
            campaign["plan"]["operations_profile_sha256"] = old.digest(profile)
    return old.digest(value)


def runtime_facts(
    *,
    check: Any = lambda: None,
    backend_reader: Any = None,
    environment_observation_sha256: Any = None,
) -> Any:
    facts = cast(Callable[..., Any], strict.runtime_facts)(
        check=check, backend_reader=backend_reader
    )
    facts["version"] = "stage12_wf_ap2_runtime_observations_ra_g1_v1"
    facts["effective_allocator_upper_bound"] = (
        "NOT_PROVEN_AND_NOT_JOB_DOMAIN_GUARANTEED"
    )
    shape(environment_observation_sha256, "D")
    facts["environment_observation_sha256"] = environment_observation_sha256
    facts["resource_assurance_method"] = METHOD
    return facts


def private_root_identity(root: Any) -> Any:
    root = Path(root)
    c.require(root.is_absolute() and str(root) == os.path.abspath(root), "RA_G1_PATH")
    current = root
    rows: list[Any] = []
    while True:
        info = current.lstat()
        c.require(stat.S_ISDIR(info.st_mode) and info.st_nlink >= 1, "RA_G1_PATH")
        if current == root:
            c.require(
                info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
                "RA_G1_PATH",
            )
        c.require(len(rows) < 64, "RA_G1_PATH")
        rows.append((str(current), info.st_dev, info.st_ino, info.st_mode, info.st_uid))
        if current.parent == current:
            return rows
        current = current.parent


def observe_capacity(
    root: Any,
    *,
    scope: Any,
    selection_sha256: Any,
    owner_reported_approval_sha256: Any,
    accounting_method_sha256: Any,
    restrictions_inventory_sha256: Any,
    observed_utc: Any,
    clock_ns: Any = time.monotonic_ns,
) -> Any:
    before = private_root_identity(root)
    data = os.statvfs(root)
    at = clock_ns()
    c.require(
        data.f_frsize > 0
        and 0 <= data.f_bavail <= data.f_blocks
        and 0 <= data.f_favail <= data.f_files,
        "RA_G1_ACCOUNTING_UNAVAILABLE",
    )
    originals = {
        key: getattr(data, key)
        for key in (
            "f_bsize",
            "f_frsize",
            "f_blocks",
            "f_bfree",
            "f_bavail",
            "f_files",
            "f_ffree",
            "f_favail",
            "f_flag",
            "f_namemax",
        )
    }
    c.require(before == private_root_identity(root), "RA_G1_PATH_CHANGED")
    record = dict(
        schema_version=CAPACITY,
        scope=scope,
        selection_sha256=selection_sha256,
        owner_reported_approval_sha256=owner_reported_approval_sha256,
        observed_utc=observed_utc,
        root_identity_inventory_sha256=old.digest(before),
        filesystem_originals_sha256=old.digest(originals),
        accounting_method_sha256=accounting_method_sha256,
        bavail_bytes=known(
            old.checked(data.f_bavail * data.f_frsize),
            "FILESYSTEM",
            "FILESYSTEM_SHARED",
            at,
        ),
        favail=known(data.f_favail, "FILESYSTEM", "FILESYSTEM_SHARED", at),
        physical_accounting_coverage="UNKNOWN_NATIVE_OR_DELETED_OPEN",
        assurance="BEST_EFFORT_SHARED_SNAPSHOT",
        entitlement="NOT_ASSERTED",
        reservation="NONE",
        restrictions_inventory_sha256=restrictions_inventory_sha256,
    )
    validate_capacity(record)
    return record, {"root": before, "statvfs": originals}


def observe_current_facts(
    initial: Any = None,
    *,
    check: Any = lambda: None,
    clock_ns: Any = time.monotonic_ns,
    read_charge: Any = None,
) -> Any:
    """Observe actual visible Linux membership/limits without claiming coverage.

    Return (closed facts, original allowlisted kernel records). ``initial`` may
    be a prior original bundle; its domain is checked, never projected forward.
    Raw records are safe kernel metadata and must be retained by the collector.
    """
    from . import s12_wf_ap2_scratch as scratch

    c.require(sys.platform == "linux", "RA_G1_PLATFORM_UNSUPPORTED")
    c.require(
        read_charge is None or callable(read_charge), "RA_G1_READ_ACCOUNTING_REQUIRED"
    )
    originals = {}

    def read(path: Any, maximum: Any = 8192) -> Any:
        check()
        path = Path(path)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            c.require(
                stat.S_ISREG(before.st_mode)
                and before.st_uid in (0, os.geteuid())
                and not before.st_mode & 0o022,
                "RA_G1_KERNEL_SOURCE",
            )
            # One exact KERNEL partition across source observation and monitor.
            buffer = bytearray(maximum)
            used = 0
            while used < maximum:
                check()
                if read_charge is not None:
                    read_charge(1, 0)
                n = os.readv(fd, [memoryview(buffer)[used:]])
                if read_charge is not None:
                    read_charge(0, n)
                if not n:
                    break
                used += n
            c.require(used < maximum, "RA_G1_KERNEL_SOURCE")
            after = os.fstat(fd)
            current = path.stat(follow_symlinks=False)
            identity = kernel_identity(before)
            c.require(
                identity == kernel_identity(after) == kernel_identity(current),
                "RA_G1_KERNEL_CHANGED",
            )
            raw = memoryview(buffer)[:used].tobytes().decode("ascii")
            originals[str(path)] = {
                "text": raw,
                "identity": list(identity),
                "acquired_mono_ns": clock_ns(),
            }
            return raw.strip(), originals[str(path)]["acquired_mono_ns"]
        finally:
            os.close(fd)

    with scratch.lease("KERNEL"):
        membership, _ = read(f"/proc/{os.getpid()}/cgroup")
        c.require(
            membership.startswith("0::/")
            and "\n" not in membership
            and len(membership) <= 2048,
            "RA_G1_CGROUP_V2_REQUIRED",
        )
        suffix = membership[3:]
        c.require(
            all(part not in (".", "..") for part in suffix.split("/")),
            "RA_G1_KERNEL_SOURCE",
        )
        domain = Path("/sys/fs/cgroup" + suffix.rstrip("/"))
        c.require(domain.resolve(strict=True) == domain, "RA_G1_KERNEL_SOURCE")
        before = domain.stat(follow_symlinks=False)
        c.require(stat.S_ISDIR(before.st_mode), "RA_G1_KERNEL_SOURCE")
        boot, _ = read("/proc/sys/kernel/random/boot_id", 64)
        boot = boot.replace("-", "")
        shape(boot, "UUID")
        namespaces = {
            key: Path(path).stat().st_ino
            for key, path in (
                ("cgroup_namespace_inode", f"/proc/{os.getpid()}/ns/cgroup"),
                ("mount_namespace_inode", f"/proc/{os.getpid()}/ns/mnt"),
            )
        }
        values = {}
        for key, filename in (
            ("memory_max_bytes", "memory.max"),
            ("memory_high_bytes", "memory.high"),
            ("swap_max_bytes", "memory.swap.max"),
            ("pids_max", "pids.max"),
        ):
            try:
                text, at = read(domain / filename, 64)
            except (FileNotFoundError, PermissionError):
                c.require(key == "pids_max", "RA_G1_VISIBLE_REQUIRED")
                values[key] = unknown("UNAVAILABLE", "INACCESSIBLE")
                continue
            if text == "max":
                values[key] = unknown("UNBOUNDED", "NATIVE_UNCONTROLLED")
            else:
                c.require(
                    text.isdecimal() and str(int(text)) == text, "RA_G1_KERNEL_SOURCE"
                )
                values[key] = known(int(text), "KERNEL", "VISIBLE_CGROUP", at)
        membership_after, _ = read(f"/proc/{os.getpid()}/cgroup")
        c.require(
            membership_after == membership
            and kernel_identity(domain.stat(follow_symlinks=False))
            == kernel_identity(before)
            and namespaces
            == {
                key: Path(path).stat().st_ino
                for key, path in (
                    ("cgroup_namespace_inode", f"/proc/{os.getpid()}/ns/cgroup"),
                    ("mount_namespace_inode", f"/proc/{os.getpid()}/ns/mnt"),
                )
            },
            "RA_G1_VISIBLE_DOMAIN_CHANGED",
        )
        identity = dict(
            domain=str(domain),
            device=before.st_dev,
            inode=before.st_ino,
            boot_id=boot,
            **namespaces,
            membership=membership,
        )
        if (
            initial is not None
            and type(initial) is dict
            and "visible_identity" in initial
        ):
            c.require(
                initial["visible_identity"] == identity, "RA_G1_VISIBLE_DOMAIN_CHANGED"
            )
        originals = {"visible_identity": identity, "records": originals}
        facts = dict(
            schema_version=CURRENT,
            origin="LIVE_KERNEL_OBSERVATION",
            observation_inventory_sha256=old.digest(originals),
            visible_identity_inventory_sha256=old.digest(identity),
            boot_id=boot,
            **namespaces,
            visible_membership_sha256=old.digest({"membership": membership}),
            **values,
            ancestor_coverage="NOT_ESTABLISHED",
            descendant_coverage="NOT_ESTABLISHED",
            native_maximum="NOT_PROVEN",
            physical_capacity="NOT_RESERVED_OR_PROVEN",
        )
        shape(facts, FACTS)
        return facts, originals


RISK = "stage12_resource_risk_inventory_ra_g1_v1"
RISKS = (
    "INTERPRETER_ALLOCATOR",
    "NATIVE_HASH_TLS",
    "ARROW_CODEC_WORKSPACE",
    "THREAD_STACKS",
    "SQLITE_JOURNAL_WAL_TEMP",
    "DUCKDB_DATABASE_WAL_TEMP",
    "NATIVE_PARTIAL_WRITES",
    "FILESYSTEM_METADATA_ROUNDING",
    "DELETED_OPEN_FILES",
    "HIDDEN_DESCENDANTS",
    "UNSELECTED_ANCESTORS",
    "SHARED_CAPACITY_OTHER_USERS",
    "ABRUPT_OVERSHOOT",
    "MONITOR_DESCHEDULING_OR_LOSS",
    "UNMONITORED_ADMINISTRATIVE_SUFFIX",
)
RISK_SCHEMA = {
    "schema_version": "=" + RISK,
    "scope": old.enum(*SCOPES),
    "method": "=" + METHOD,
    **old.fields("policy_sha256:D adoption_sha256:D"),
    "entries": [
        {
            "risk": old.enum(*RISKS),
            "observation_scope": old.enum(
                "REGISTERED_VISIBLE",
                "VISIBLE_LINKED_ONLY",
                "NOT_OBSERVABLE",
                "GUARDED_ADMINISTRATIVE_SUFFIX",
            ),
            "control": old.enum(
                "LOGICAL_LIMIT_AND_MONITOR",
                "SCOPED_NATIVE_CONTROL_AND_MONITOR",
                "EXPLICIT_ACCEPTED_UNKNOWN",
                "FINITE_GUARDED_SUFFIX",
            ),
            "maximum": "=NOT_PROVEN",
            "evidence_sha256": "D",
        }
    ],
    "native_maximum": "=NOT_PROVEN",
    "physical_maximum": "=NOT_PROVEN",
    "complete_descendant_coverage": "=NOT_ESTABLISHED",
}


def validate_risk_inventory(record: Any, *, binding: Any = None) -> Any:
    shape(record, RISK_SCHEMA)
    c.require(
        [entry["risk"] for entry in record["entries"]] == list(RISKS),
        "RA_G1_RISK_INVENTORY",
    )
    if binding is not None:
        c.require(
            old.digest(record) == binding["risk_inventory_sha256"]
            and record["scope"] == binding["scope"]
            and record["policy_sha256"] == binding["policy_sha256"]
            and record["adoption_sha256"] == binding["adoption_sha256"],
            "RA_G1_RISK_BINDING",
        )
    return record


def kernel_identity(info: Any) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def validate_environment_originals(facts: Any, originals: Any) -> Any:
    """Validate actual scoped facts against their fresh retained kernel originals.

    Bytes require exact canonical JSON. This verifies observed values and object
    associations; it supplies no complete hierarchy, entitlement or live grant.
    """
    import json
    from . import s12_public_bounded as bounded

    shape(facts, FACTS)
    if type(originals) is bytes:
        c.require(len(originals) <= 65536, "RA_G1_RECORD_LIMIT")

        def pairs(items: Any) -> Any:
            c.require(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
            return dict(items)

        parsed = json.loads(originals, object_pairs_hook=pairs)
        bounded.canonical_match(parsed, originals)
        originals = parsed
    c.require(
        type(originals) is dict and set(originals) == {"visible_identity", "records"},
        "RA_G1_FIELDS",
    )
    counter = bounded.Canonical(65536, count_only=True)
    counter.value(originals)
    counter.put(b"\n")
    identity, records = originals["visible_identity"], originals["records"]
    c.require(
        type(identity) is dict
        and set(identity)
        == {
            "domain",
            "device",
            "inode",
            "boot_id",
            "cgroup_namespace_inode",
            "mount_namespace_inode",
            "membership",
        },
        "RA_G1_FIELDS",
    )
    domain = identity["domain"]
    strict_path = Path(domain) if type(domain) is str else Path(".")
    c.require(
        type(domain) is str
        and domain.startswith("/sys/fs/cgroup")
        and strict_path.is_absolute()
        and str(strict_path) == domain
        and all(part not in (".", "..") for part in strict_path.parts),
        "RA_G1_FIELDS",
    )
    for key in ("device", "inode", "cgroup_namespace_inode", "mount_namespace_inode"):
        shape(identity[key], "P" if key != "device" else "U")
    shape(identity["boot_id"], "UUID")
    membership = "0::" + (
        "/" + str(strict_path.relative_to("/sys/fs/cgroup"))
        if domain != "/sys/fs/cgroup"
        else "/"
    )
    c.require(
        identity["membership"] == membership
        and facts["boot_id"] == identity["boot_id"]
        and all(
            facts[key] == identity[key]
            for key in ("cgroup_namespace_inode", "mount_namespace_inode")
        )
        and facts["visible_membership_sha256"] == old.digest({"membership": membership})
        and facts["visible_identity_inventory_sha256"] == old.digest(identity)
        and facts["observation_inventory_sha256"] == old.digest(originals),
        "RA_G1_ORIGINAL_CHANGED",
    )
    c.require(type(records) is dict and 5 <= len(records) <= 6, "RA_G1_FIELDS")
    memberships = []
    boot = None
    controls: dict[str, Any] = {}
    for path, record in records.items():
        c.require(
            type(path) is str
            and type(record) is dict
            and set(record) == {"text", "identity", "acquired_mono_ns"},
            "RA_G1_FIELDS",
        )
        shape(record["acquired_mono_ns"], "U")
        c.require(
            type(record["identity"]) is list
            and len(record["identity"]) == 5
            and type(record["text"]) is str
            and record["text"].isascii()
            and len(record["text"]) <= 8192,
            "RA_G1_FIELDS",
        )
        for value in record["identity"]:
            shape(value, "U")
        c.require(
            stat.S_ISREG(record["identity"][2]) and not record["identity"][2] & 0o022,
            "RA_G1_FIELDS",
        )
        if re.fullmatch(r"/proc/[1-9][0-9]*/cgroup", path):
            memberships.append(record["text"].strip())
        elif path == "/proc/sys/kernel/random/boot_id":
            c.require(boot is None, "RA_G1_FIELDS")
            boot = record["text"].strip().replace("-", "")
        else:
            name = Path(path).name
            c.require(
                Path(path).parent == strict_path
                and name
                in ("memory.max", "memory.high", "memory.swap.max", "pids.max"),
                "RA_G1_FIELDS",
            )
            controls[name] = record
    c.require(
        memberships == [membership] and boot == identity["boot_id"],
        "RA_G1_ORIGINAL_CHANGED",
    )
    for key, filename in (
        ("memory_max_bytes", "memory.max"),
        ("memory_high_bytes", "memory.high"),
        ("swap_max_bytes", "memory.swap.max"),
        ("pids_max", "pids.max"),
    ):
        if filename not in controls:
            c.require(
                key == "pids_max"
                and facts[key] == unknown("UNAVAILABLE", "INACCESSIBLE"),
                "RA_G1_VISIBLE_REQUIRED",
            )
            continue
        raw = controls[filename]
        text = raw["text"].strip()
        if text == "max":
            expected = unknown("UNBOUNDED", "NATIVE_UNCONTROLLED")
        else:
            c.require(text.isdecimal() and str(int(text)) == text, "RA_G1_FIELDS")
            expected = known(
                int(text), "KERNEL", "VISIBLE_CGROUP", raw["acquired_mono_ns"]
            )
        c.require(facts[key] == expected, "RA_G1_ORIGINAL_CHANGED")
    return originals


def validate_capacity_originals(
    cap: Any,
    root_original: Any,
    statvfs_original: Any,
    method_original: Any,
    restrictions_original: Any,
    root_path: Any = None,
) -> Any:
    """Original units/values/path association, without any reservation theorem."""
    validate_capacity(cap)
    for value, field in (
        (root_original, "root_identity_inventory_sha256"),
        (statvfs_original, "filesystem_originals_sha256"),
        (method_original, "accounting_method_sha256"),
        (restrictions_original, "restrictions_inventory_sha256"),
    ):
        c.require(old.digest(value) == cap[field], "RA_G1_CAPACITY_ORIGINAL_CHANGED")
    c.require(
        type(root_original) in (list, tuple) and 1 <= len(root_original) <= 64,
        "RA_G1_FIELDS",
    )
    previous: Any = None
    for ordinal, row in enumerate(root_original):
        c.require(
            type(row) in (list, tuple)
            and len(row) == 5
            and type(row[0]) is str
            and Path(row[0]).is_absolute()
            and row[0] == os.path.abspath(row[0]),
            "RA_G1_PATH",
        )
        for value in row[1:]:
            old.uint(value)
        c.require(stat.S_ISDIR(row[3]) and row[2] > 0, "RA_G1_PATH")
        if ordinal == 0:
            c.require(stat.S_IMODE(row[3]) == 0o700, "RA_G1_PATH")
        else:
            c.require(str(Path(previous).parent) == row[0], "RA_G1_PATH")
        previous = row[0]
    c.require(previous == "/", "RA_G1_PATH")
    if root_path is not None:
        root = Path(root_path)
        c.require(
            str(root) == root_original[0][0]
            and c.canonical(private_root_identity(root)) == c.canonical(root_original),
            "RA_G1_CAPACITY_ROOT_CHANGED",
        )
    fields = "f_bsize f_frsize f_blocks f_bfree f_bavail f_files f_ffree f_favail f_flag f_namemax".split()
    shape(statvfs_original, {field: "U" for field in fields})
    raw = statvfs_original
    c.require(
        raw["f_bsize"] > 0
        and raw["f_frsize"] > 0
        and raw["f_namemax"] > 0
        and 0 <= raw["f_bavail"] <= raw["f_bfree"] <= raw["f_blocks"]
        and 0 <= raw["f_favail"] <= raw["f_ffree"] <= raw["f_files"],
        "RA_G1_ACCOUNTING_UNAVAILABLE",
    )
    c.require(
        cap["bavail_bytes"]["value"] == old.checked(raw["f_bavail"] * raw["f_frsize"])
        and cap["favail"]["value"] == raw["f_favail"],
        "RA_G1_CAPACITY_VALUE_CHANGED",
    )
    c.require(
        method_original
        == {"method": "CURRENT_STATVFS_SHARED_SNAPSHOT_NOT_RESERVATION"},
        "RA_G1_ACCOUNTING_METHOD",
    )
    c.require(
        restrictions_original
        == {"known": "SITE_PROJECT_RULES_PRESERVED", "unknown": "NOT_ESTABLISHED"},
        "RA_G1_RESTRICTIONS_INVENTORY",
    )
    c.require(
        not raw["f_flag"] & getattr(os, "ST_RDONLY", 1), "RA_G1_KNOWN_RESTRICTION"
    )
    return cap


def bounded_backend_reader(charge_read: Any) -> Callable[..., str]:
    """Five actual imported backends, one 4096-byte HASH lease, charged EOF.

    Call counts are reserved before reads; actual bytes are charged immediately
    after each bounded read. Growing/truncated/replaced originals never yield a
    qualifying hash. This returns a callback for runtime_facts(backend_reader=).
    """
    import hashlib
    import importlib
    from . import s12_wf_ap2_scratch as scratch

    c.require(callable(charge_read), "RA_G1_READ_ACCOUNTING_REQUIRED")
    names = ("_hashlib", "_ssl", "_sqlite3", "_duckdb", "pyarrow.lib")

    def read_backend(name: Any, path: Any, check: Any) -> str:
        c.require(name in names and callable(check), "RA_G1_RUNTIME_SOURCE")
        check()
        path = Path(path)
        module = importlib.import_module(name)
        filename = module.__file__
        c.require(type(filename) is str, "RA_G1_RUNTIME_SOURCE")
        actual = Path(cast(str, filename)).resolve(strict=True)
        c.require(
            path.is_absolute() and path.resolve(strict=True) == path == actual,
            "RA_G1_RUNTIME_SOURCE",
        )
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            c.require(
                stat.S_ISREG(before.st_mode)
                and before.st_size > 0
                and before.st_nlink >= 1
                and not before.st_mode & 0o022,
                "RA_G1_RUNTIME_SOURCE",
            )
            digest, consumed = hashlib.sha256(), 0
            with scratch.lease("HASH"):
                block = bytearray(4096)
                try:
                    while consumed < before.st_size:
                        check()
                        charge_read(1, 0)
                        with memoryview(block)[: min(4096, before.st_size - consumed)] as view:
                            size = os.readv(fd, [view])
                        charge_read(0, size)
                        c.require(size > 0, "RA_G1_RUNTIME_CHANGED")
                        consumed += size
                        with memoryview(block)[:size] as view:
                            digest.update(view)
                    check()
                    charge_read(1, 0)
                    with memoryview(block)[:1] as view:
                        extra = os.readv(fd, [view])
                    charge_read(0, extra)
                    c.require(extra == 0, "RA_G1_RUNTIME_CHANGED")
                finally:
                    del block
            after, current = os.fstat(fd), path.stat(follow_symlinks=False)
            fields = (
                "st_dev",
                "st_ino",
                "st_mode",
                "st_uid",
                "st_gid",
                "st_nlink",
                "st_size",
                "st_mtime_ns",
                "st_ctime_ns",
            )
            c.require(
                consumed == before.st_size
                and all(
                    getattr(before, key) == getattr(after, key) == getattr(current, key)
                    for key in fields
                )
                and path.resolve(strict=True) == path,
                "RA_G1_RUNTIME_CHANGED",
            )
            check()
            return digest.hexdigest()
        finally:
            os.close(fd)

    return read_backend


def bootstrap_policy_descriptor() -> Any:
    return dict(descriptor_version=BOOTSTRAP_POLICY, closed=True, live_instance=False,
        scope="REPRESENTATIVE_NO_SERVICE", startup_ceiling_ns=BOOTSTRAP_LIMIT_NS,
        inclusive=True, eligible_roles=[dict(phase_id=p, role=r) for p,r in BOOTSTRAP_ROLES.items()],
        source_entry_and_deadlines="UNCHANGED", monitor_scope_start="ACTUAL_BOOTSTRAP_END",
        first_start_requirement="ACTUAL_DURABLE_ACK_BEFORE_WORK_AND_EARLIER_DEADLINES",
        resource_period_ns=500_000_000, resource_max_gap_ns=1_000_000_000,
        later_sessions="NO_BOOTSTRAP_EXCEPTION", physical_coverage="NOT_CLAIMED")


def bootstrap_role(selected: Any, phase_id: Any) -> Any:
    return BOOTSTRAP_ROLES.get(phase_id) if selected.get("schema_version") in (BOOTSTRAP_SELECTION, *REP_ADMIN_SELECTIONS) else None


def validate_bootstrap_adoption(value: Any, selected: Any) -> Any:
    shape(value, BOOTSTRAP_ADOPTION_SCHEMA)
    c.require(value["prospective_only"] is True and value["startup_ceiling_ns"] == BOOTSTRAP_LIMIT_NS
              and value["policy_sha256"] == old.digest(bootstrap_policy_descriptor())
              and old.digest(value) == selected["bootstrap_prefix_adoption_sha256"], "RA_G1_BOOTSTRAP_POLICY")
    return value


def validate_bootstrap_evidence(value: Any, selected: Any, *, binding_sha256: Any, root: Any, first: Any = None) -> Any:
    shape(value, BOOTSTRAP_EVIDENCE_SCHEMA)
    role = bootstrap_role(selected, value["phase_id"])
    c.require(role is not None and value["role"] == role
              and value["binding_sha256"] == binding_sha256
              and value["selection_sha256"] == old.digest(selected)
              and value["bootstrap_policy_sha256"] == selected["bootstrap_prefix_policy_sha256"]
              and value["bootstrap_adoption_sha256"] == selected["bootstrap_prefix_adoption_sha256"]
              and value["root_identity_inventory_sha256"] == old.digest(private_root_identity(root)), "RA_G1_BOOTSTRAP_EVIDENCE")
    validate_bootstrap_adoption(value["adoption_original"], selected)
    entry, end, enter, exit_ns, ack, deadline = (value[k] for k in (
        "source_entry_mono_ns", "bootstrap_end_mono_ns", "first_start_enter_mono_ns",
        "first_start_exit_mono_ns", "first_start_ack_mono_ns", "phase_deadline_mono_ns"))
    stage = next((r for r in selected["limits"]["stages"] if r["id"] == value["phase_id"]), None)
    c.require(stage is not None and entry <= end <= enter <= exit_ns <= ack < deadline
              and ack - entry <= BOOTSTRAP_LIMIT_NS and enter - end <= 1_000_000_000
              and exit_ns - enter <= 1_000_000_000 and value["first_start_seq"] == 1
              and deadline <= entry + stage["deadline_ms"] * 1_000_000, "RA_G1_BOOTSTRAP_LIMIT")
    if first is not None:
        c.require(first["seq"] == 1 and first["kind"] == "START"
                  and old.digest(first) == value["first_start_record_sha256"]
                  and first["visible_identity_inventory_sha256"] == value["first_start_original_sha256"]
                  and first["enter_mono_ns"] == enter and first["exit_mono_ns"] == exit_ns,
                  "RA_G1_BOOTSTRAP_EVIDENCE")
    return value

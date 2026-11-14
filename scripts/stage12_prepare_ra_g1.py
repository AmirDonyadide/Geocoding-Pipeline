"""Canonical RA-G1 representative builder; no source/protected/provider access.

Only actual allocation originals and reviewed authority records can make an
executable input. This module neither submits a job nor issues human approval.
"""

from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import json

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as m
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_assets,
    s12_operations,
    s12_response,
    s12_probe,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
    ROLES,
    BOUND_REVIEW,
    DIAGNOSTIC_REVIEW,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

SCOPE = "REPRESENTATIVE_NO_SERVICE"
PUBLIC_VALIDATOR = "849a0863876b75dcef322a46d74c2558708cb8611046c8235869090cce621ae2"
PHASES = (
    ("first64", 346000, 1817, 64),
    ("deep32_size40", 300000, 1572, 32),
    ("controls8", 180000, 200, 8),
    ("malformed", 180000, 0, 3),
)
VERSION = "stage12_ra_g1_representative_diagnostic_input_v1"
BOOTSTRAP_VERSION = "stage12_ra_g1_representative_bootstrap30_diagnostic_input_v1"
BOOTSTRAP_ALLOCATION_VERSION = "stage12_ra_g1_bootstrap30_allocation_selection_v1"
SHARED_LEASE_VERSION = "stage12_ra_g1_shared_lease_representative_input_v1"
SHARED_LEASE_ALLOCATION_VERSION = "stage12_ra_g1_shared_lease_allocation_selection_v1"
REP_ADMIN_VERSION = "stage12_ra_g1_rep_admin_budget_representative_input_v1"
REP_ADMIN_ALLOCATION_VERSION = "stage12_ra_g1_rep_admin_budget_allocation_selection_v1"
REP512_VERSION = "stage12_ra_g1_rep_first64_512_representative_input_v1"
REP512_ALLOCATION_VERSION = "stage12_ra_g1_rep_first64_512_allocation_selection_v1"
REP_FOREGROUND_VERSION = "stage12_ra_g1_rep_foreground_representative_input_v1"
REP_FOREGROUND_ALLOCATION_VERSION = "stage12_ra_g1_rep_foreground_allocation_selection_v1"
REP_ACK_VERSION = "stage12_ra_g1_rep_ack_queue_representative_input_v1"
REP_ACK_ALLOCATION_VERSION = "stage12_ra_g1_rep_ack_queue_allocation_selection_v1"
REP_ACK_CONFIG_VERSION = "stage12_ra_g1_representative_ack_queue_configuration_v1"
REP_FAIR_VERSION = "stage12_ra_g1_rep_fair_service_representative_input_v1"
REP_FAIR_ALLOCATION_VERSION = "stage12_ra_g1_rep_fair_service_allocation_selection_v1"
REP_FAIR_CONFIG_VERSION = "stage12_ra_g1_representative_fair_service_configuration_v1"
REP512_ALLOCATION_VERSIONS = (REP512_ALLOCATION_VERSION, REP_FOREGROUND_ALLOCATION_VERSION, REP_ACK_ALLOCATION_VERSION, REP_FAIR_ALLOCATION_VERSION)
REP_ADMIN_ALLOCATION_VERSIONS = (REP_ADMIN_ALLOCATION_VERSION, *REP512_ALLOCATION_VERSIONS)
CONFIG_VERSION = "stage12_ra_g1_representative_configuration_v1"


def contract_for_allocation(allocation):
    if allocation.get("version")==REP_ACK_ALLOCATION_VERSION:
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_ack_contract
        return s12_ra_g1_rep_ack_contract
    if allocation.get("version")==REP_FAIR_ALLOCATION_VERSION:
        from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract
        return s12_ra_g1_rep_fair_contract
    return a


def phases_for(allocation):
    return (("first64",512000,1817,64), *PHASES[1:]) if allocation.get("version") in REP512_ALLOCATION_VERSIONS else PHASES


def canonical(value):
    return c.canonical(value)


def digest(value):
    return c.sha(canonical(value)).hex()


def selection_scope(value):
    return digest(value)


class DiagnosticConstants:
    PHASES = PHASES
    CONFIG_VERSION = CONFIG_VERSION


diagnostic = DiagnosticConstants()


def build_campaigns(selection, facts, resource_selection, capacity):
    a = contract_for_allocation(selection)
    window_start, window_end = selection["valid_from"], selection["valid_until"]
    roles = {
        role: {
            "version": "stage12_diagnostic_test_authority_v1",
            "scope": SCOPE,
            "role": role,
            "authority": "TEST_ONLY_NO_SERVICE",
        }
        for role in ("owner", "operator", "policy_freeze", "selection", "transport")
    }
    role_hashes = {role: digest(value) for role, value in roles.items()}
    resources = {
        "application_admission_memory_bytes": 4 * 2**30,
        "resource_selection_sha256": digest(resource_selection),
        "initial_capacity_observation_sha256": digest(capacity),
        "logical_process_overhead_bytes": 2**30,
        "requested_memory_bytes": 6 * 2**30,
        "logical_pending_request_bytes": 2**20,
        "per_attempt_logical_write_ceiling_bytes": 2**27,
        "fixed_campaign_logical_write_ceiling_bytes": 2**27,
        "task_logical_write_ceiling_bytes": 72 * 2**30,
        "resource_review_sha256": role_hashes["selection"],
        "scheduler_guard_ms": 100,
        "writer_guard_ms": 5000,
    }
    transport = {"scope": SCOPE, "authority": "TEST_ONLY_NO_NETWORK"}
    preserved = s12_assets.hashes()
    campaigns, phases = [], []
    # The temporary nonzero pointer is removed by the adopted acyclic scope;
    # it is never persisted as a supported bound or used for execution.
    pending_pointer = digest(
        {
            "scope": "UNPERSISTED_BINDING_PLACEHOLDER",
            "selection": selection_scope(selection),
        }
    )
    for index, (label, duration, hold, count) in zip(
        (0, 9, 10, 0), phases_for(selection), strict=True
    ):
        work, recipes = matrix.work_for(index, digest(transport))
        work = work[:count]
        controls = count if label == "controls8" else 0
        data = count - controls
        observations = (duration + 49) // 50 + 2
        f = 4 * observations + 8
        sample_bytes = 4096 * f + 8 * (512 * f + 4096)
        profile = {
            "schema_version": a.PROFILE,
            "scope": a.SCOPE,
            "rule_bundle_sha256": a.RULE_BUNDLE,
            "policy_freeze_record_sha256": role_hashes["policy_freeze"],
            "preserved": {
                "operations_v1_sha256": preserved[s12_operations.VERSION].hex(),
                "materialization_sha256": preserved[a.c.MATERIALIZATION].hex(),
                "response_validation_sha256": preserved[s12_response.VALIDATION].hex(),
                "public_audit_source_sha256": "b43134525b99b60767d9661d334ccf743d101f06e85be42350483048a1c9d8f4",
            },
            "transport_profile_sha256": digest(transport),
            "operator_allowance": {
                "record_sha256": role_hashes["operator"],
                "rate_ceiling": {"num": 1, "den": 1},
                "connections": 2,
                "valid_from": window_start,
                "valid_until": window_end,
            },
            "states": [
                {
                    "state_id": 1,
                    "rate": {"num": 1, "den": 1},
                    "connections": 2,
                    "admitted_operations": 2,
                    "evidence_sha256": role_hashes["selection"],
                }
            ],
            "resources": deepcopy(resources),
            "monitoring": {
                "mode": "PUBLIC_GAPS_ONLY",
                "gaps_record_sha256": role_hashes["selection"],
            },
            "sampling_policy_sha256": a.POLICY_SHA,
            "sampling_runtime_bound_sha256": pending_pointer,
            **a.assurance_fields(),
        }
        budget_row = {
            "data_observations": data,
            "required_control_observations": controls,
            "reserved_control_observations": 0,
            "data_attempts": 5 * data,
            "control_http_attempts": 5 * controls,
            "administrative_operations": 0,
            "administrative_duration_ms": 0,
            "active_duration_ms": duration,
            "storage_bytes": (5 * count + 1) * 2**27 + sample_bytes,
            "event_count": 19 * 5 * count + 40 + 2 * observations + 4,
        }
        plan = {
            "schema_version": a.PLAN,
            "scope": a.SCOPE,
            "operations_profile_sha256": digest(profile),
            "fixture_inventory_sha256": digest(s12_probe.fixtures()),
            "work_manifest_sha256": a.manifest_digest(work),
            "control_recipes": recipes,
            "blocks": [
                {
                    "block_id": 1,
                    "state_id": 1,
                    "observation_ids": [x["work_id"] for x in work],
                    "reserved_control_ids": [],
                    "budget": deepcopy(budget_row),
                    "evaluation": "EXPLORATORY",
                    "criteria": None,
                    "fallback_state_ids": [],
                    "transition_from": None,
                }
            ],
            "experiment_kind": "PERFORMANCE",
            "capability_parent_sha256": None,
            "budgets": budget_row,
            "window_start": window_start,
            "window_end": window_end,
            "shutdown_reserve_ms": 80000,
            "selection_basis_sha256": role_hashes["selection"],
            "sampling_budget": {
                "maximum_segments": 1,
                "maximum_observations": observations,
                "maximum_inventory_versions_per_segment": 8,
                "additional_event_tokens": 2 * observations + 4,
                "additional_file_data_bytes": sample_bytes,
                "additional_file_entries": f + 8,
            },
            "history_limits": {
                "maximum_entries": 150000,
                "maximum_name_bytes": 256,
                "maximum_total_name_bytes": 38400000,
                "page_entries": 128,
                "maximum_depth": 8,
                "maximum_file_bytes": 2**26,
            },
        }
        campaigns.append(
            {"label": label, "profile": profile, "plan": plan, "work": work}
        )
        phases.append(
            {
                "label": label,
                "epoch_id": digest(
                    [facts["job_id"], selection_scope(selection), label, "epoch"]
                ),
                "hold_regular_acks": hold,
            }
        )
    config = {
        "version": REP_FAIR_CONFIG_VERSION if selection.get("version")==REP_FAIR_ALLOCATION_VERSION else REP_ACK_CONFIG_VERSION if selection.get("version")==REP_ACK_ALLOCATION_VERSION else diagnostic.CONFIG_VERSION,
        "window_start": window_start,
        "window_end": window_end,
        "sources": role_hashes,
        "transport": transport,
        "campaigns": campaigns,
        "resources": resources,
        "public_validation_sha256": PUBLIC_VALIDATOR,
        "command_paths": {
            key: selection["paths"][mapped]
            for key, mapped in (
                ("source", "source"),
                ("input", "input"),
                ("output", "output"),
                ("evidence_bundle", "binding"),
            )
        },
    }
    return config, phases, roles


def _strict_resource_selection(
    allocation,
    *,
    policy_sha256,
    adoption_sha256,
    descriptor_inventory_sha256,
    graph_sha256,
    paths_sha256,
    implementation_review_sha256,
):
    """Compile finite declared role graph; none of these fields proves capacity."""
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_accounting as accounting_compiler,
    )

    accounting_inventory = accounting_compiler.validate_inventory(
        allocation["accounting_inventory"]
    )
    c.require(
        accounting_inventory["scope"] == SCOPE
        and accounting_inventory["sources"] == allocation["source_files"]
        and accounting_inventory["accounting"] == allocation["accounting"],
        "RA_G1_ACCOUNTING_CHANGED",
    )
    c.require(
        accounting_inventory["schema_version"]
        == (accounting_compiler.REP_FAIR_VERSION if allocation.get("version") == REP_FAIR_ALLOCATION_VERSION else accounting_compiler.REP_ACK_VERSION if allocation.get("version") == REP_ACK_ALLOCATION_VERSION else accounting_compiler.REP_FOREGROUND_VERSION if allocation.get("version") == REP_FOREGROUND_ALLOCATION_VERSION
            else accounting_compiler.REP512_VERSION if allocation.get("version") in REP512_ALLOCATION_VERSIONS
            else accounting_compiler.REP_ADMIN_VERSION if allocation.get("version") == REP_ADMIN_ALLOCATION_VERSION
            else accounting_inventory["schema_version"])
        and ((accounting_inventory["schema_version"] in (accounting_compiler.REP_ADMIN_VERSION,accounting_compiler.REP512_VERSION,accounting_compiler.REP_FOREGROUND_VERSION,accounting_compiler.REP_ACK_VERSION,accounting_compiler.REP_FAIR_VERSION))
             == (allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS)),
        "RA_G1_ACCOUNTING_CHANGED",
    )
    stage_caps = {
        row["stage_id"]: accounting_compiler.stage_accounting(
            accounting_inventory, row["stage_id"]
        )
        for row in accounting_inventory["stage_accounting"]
    }
    creation_total = 204860 if allocation.get("version") in REP512_ALLOCATION_VERSIONS else 184184
    event_total = 57237 if allocation.get("version") in REP512_ALLOCATION_VERSIONS else 50597
    bounds = []
    for n, (_, duration, _, count) in enumerate(phases_for(allocation), 1):
        observations = (duration + 49) // 50 + 2
        bounds.append(
            dict(
                id=n,
                phase=n,
                deadline_ms=duration,
                reserve_ms=80000,
                attempts=5 * count,
                events=19 * 5 * count + 40 + 2 * observations + 4,
                logical_write_bytes=(5 * count + 1) * 2**27
                + 4096 * (4 * observations + 8)
                + 8 * (512 * (4 * observations + 8) + 4096),
                creations=184184,
                **stage_caps[n],
            )
        )
    # Every selected stage retains its own sampling/event/attempt/monitor
    # liability. Remaining global monitor/preparation/closure capacity remains
    # precharged; no stage resets or refunds the parent reservation.
    for row in bounds:
        duration, attempts = row["deadline_ms"], row["attempts"]
        observations = (duration + 49) // 50 + 2
        sample_files = 4 * observations + 8 + 8
        timing_rows = observations + attempts + 16
        timing_files = (timing_rows + 55) // 56 + (duration + 4999) // 5000 + 3
        monitor_rows = (duration + 499) // 500 + 2
        row["creations"] = (
            sample_files
            + row["events"]
            + 24 * attempts
            + 128
            + timing_files
            + 2 * monitor_rows
            + 20
        )
    for identity, duration, reserved, metadata_creations in (
        (5, 120000, 16 * 2**20, 256),
        (6, 120000, 16 * 2**20, 256),
        (7, 480000 if allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS else 600000, 32 * 2**20, 64),
        (8, 240000 if allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS else 120000, 16 * 2**20, 1024),
    ):
        monitor_rows = (duration + 499) // 500 + 2
        bounds.append(
            dict(
                id=identity,
                phase=identity,
                deadline_ms=duration,
                reserve_ms=5000,
                attempts=0,
                events=0,
                logical_write_bytes=reserved,
                creations=2 * monitor_rows + 20 + metadata_creations,
                **stage_caps[identity],
            )
        )
    residual = creation_total - sum(row["creations"] for row in bounds)
    c.require(residual >= 0, "RA_G1_CREATION_PLAN_INFEASIBLE")
    # Unspent root administrative headroom is assigned to final task scope.
    bounds[4]["creations"] += residual
    counters = {role: 0 for role in m.LIMITS["application_counters"]}
    counters.update(
        COMPRESSED_FRAME=535,
        EXCLUSIVE_FILE=creation_total,
        EVENT_FILE=event_total,
        PREFIX_FILE=64,
        COMPARISON_FILE=8,
        ADMIN_FILE=4096,
        CONTROL_BEGIN=40,
        CONTROL_FINISH=40,
    )
    record = dict(
        schema_version=m.SELECTION,
        scope=SCOPE,
        policy_sha256=policy_sha256,
        adoption_sha256=adoption_sha256,
        source_git_sha=allocation["source_sha"],
        descriptor_inventory_sha256=descriptor_inventory_sha256,
        workload_graph_sha256=graph_sha256,
        limits=dict(
            processing_ms=8160000,
            scheduler_s=8400,
            processes=4,
            threads=256,
            utilities=256,
            python_invocations=5,
            python_roles=[dict(role=role, maximum=1) for role in m.ROLES],
            input_bytes=4 * 2**20,
            metadata_bytes=4 * 2**20,
            attempts=535,
            logical_write_bytes=72 * 2**30,
            creations=creation_total,
            telemetry_chunks=1500,
            telemetry_bytes=2 * 1500 * 32768,
            telemetry_creations=1501,
            monitor_rows=16342,
            monitor_bytes=268173312,
            monitor_creations=32736,
            closure_reserve_bytes=256 * 2**20,
            closure_reserve_creations=4096,
            native_invocations=0,
            stages=bounds,
            application_counters=counters,
        ),
        monitor=dict(
            period_ms=500,
            max_observed_interval_ms=1000,
            self_rss_stop_bytes=768 * 2**20,
            aggregate_rss_stop_bytes=768 * 2**20,
            visible_threads_stop=256,
            native_visible_file_stop_bytes=8 * 2**30,
            shared_free_margin_bytes=1342177280,
            free_inode_margin=4096,
            scope="SELF_AND_REGISTERED_VISIBLE",
            required_observation_set_sha256=digest(
                dict(
                    readings=[
                        "self_rss_peak_bytes",
                        "registered_visible_rss_bytes",
                        "visible_native_threads",
                        "visible_processes",
                        "shared_bavail_bytes",
                        "shared_favail",
                        "visible_native_file_bytes",
                    ],
                    coverage="REGISTERED_VISIBLE_NOT_COMPLETE_JOB",
                )
            ),
        ),
        authority_requirement_inventory_sha256=digest(
            {
                "scope": SCOPE,
                "service": False,
                "protected": False,
                "required": [
                    "owner_adoption",
                    "independent_release",
                    "actual_bootstrap_review",
                    "canonical_config_review",
                    "private_paths",
                    "usable_shared_accounting",
                ],
            }
        ),
        paths_sha256=paths_sha256,
        valid_from=allocation["valid_from"],
        valid_until=allocation["valid_until"],
        review_sha256=implementation_review_sha256,
    )
    if allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS:
        record.update(schema_version=m.REP_ADMIN_SELECTION,
            bootstrap_prefix_policy_sha256=digest(m.bootstrap_policy_descriptor()),
            bootstrap_prefix_adoption_sha256=allocation["bootstrap_prefix_adoption_sha256"],
            rep_admin_budget_policy_sha256=digest(m.rep_admin_policy_descriptor()),
            rep_admin_budget_adoption_sha256=allocation["rep_admin_budget_adoption_sha256"])
    if allocation.get("version") in REP512_ALLOCATION_VERSIONS:
        record.update(schema_version=(m.REP_FAIR_SELECTION if allocation.get("version")==REP_FAIR_ALLOCATION_VERSION else m.REP_ACK_SELECTION if allocation.get("version")==REP_ACK_ALLOCATION_VERSION else m.REP_FOREGROUND_SELECTION if allocation.get("version") == REP_FOREGROUND_ALLOCATION_VERSION else m.REP512_SELECTION),
            rep_first64_512_policy_sha256=digest(m.rep512_policy_descriptor()),
            rep_first64_512_adoption_sha256=allocation["rep_first64_512_adoption_sha256"])
    if allocation.get("version")==REP_ACK_ALLOCATION_VERSION:
        record.update(rep_ack_policy_sha256=contract_for_allocation(allocation).POLICY_SHA,
            rep_ack_policy_adoption_sha256=allocation["rep_ack_policy_adoption_sha256"])
    if allocation.get("version")==REP_FAIR_ALLOCATION_VERSION:
        record.update(rep_fair_policy_sha256=contract_for_allocation(allocation).POLICY_SHA,
            rep_fair_policy_adoption_sha256=allocation["rep_fair_policy_adoption_sha256"])
    m.validate_selection(record)
    return record


def resource_selection(allocation, **kwargs):
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    if windows.is_window_adoption(allocation.get("rep_admin_budget_adoption", {})):
        window = allocation["rep_admin_budget_adoption"]["window"]
        policy = windows.selected_descriptor(window)
        c.require(allocation.get("version") in REP512_ALLOCATION_VERSIONS
            and allocation.get("scope") == SCOPE
            and allocation.get("valid_from") == policy["valid_from"]
            and allocation.get("valid_until") == policy["valid_until"], "RA_G1_SELECTION_BINDING")
    record = _strict_resource_selection(allocation, **kwargs)
    if allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS:
        m.validate_bootstrap_adoption(allocation["bootstrap_prefix_adoption"], record)
        m.validate_rep_admin_adoption(allocation["rep_admin_budget_adoption"], record)
        if allocation.get("version") in REP512_ALLOCATION_VERSIONS:
            m.validate_rep512_adoption(allocation["rep_first64_512_adoption"], record)
        if allocation.get("version")==REP_ACK_ALLOCATION_VERSION:
            m.validate_rep_ack_adoption(allocation["rep_ack_policy_adoption"],record)
        return record
    if allocation.get("version") not in (BOOTSTRAP_ALLOCATION_VERSION, SHARED_LEASE_ALLOCATION_VERSION):
        return record
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    record = {**record, "schema_version": assurance.BOOTSTRAP_SELECTION,
        "bootstrap_prefix_policy_sha256": digest(assurance.bootstrap_policy_descriptor()),
        "bootstrap_prefix_adoption_sha256": allocation["bootstrap_prefix_adoption_sha256"]}
    assurance.validate_bootstrap_adoption(allocation["bootstrap_prefix_adoption"], record)
    return assurance.validate_selection(record)


def build(
    allocation,
    bootstrap,
    *,
    implementation_report,
    source_files,
    adoption,
    project_approval,
    resource_review,
    independent_bootstrap_review,
    issued=False,
):
    """Mechanically bind genuine facts; returns bytes for separate exact review.

    ``issued`` requires the retained independent bootstrap and software reviews.
    An exact independently checked input release is still required by supervisor.
    """
    c.require(
        bootstrap["source_sha"] == allocation["source_sha"]
        and bootstrap["scope"] == SCOPE,
        "RA_G1_BOOTSTRAP_BINDING",
    )
    actual = bootstrap["facts"]
    m.shape(actual, m.FACTS)
    c.require(
        actual["origin"] == "LIVE_KERNEL_OBSERVATION"
        or (not issued and actual["origin"] == "SYNTHETIC_TEST_ONLY"),
        "RA_G1_ACTUAL_BOOTSTRAP_REQUIRED",
    )
    c.require(
        independent_bootstrap_review["disposition"] == "PASS"
        and independent_bootstrap_review["bootstrap_manifest_sha256"]
        == bootstrap["manifest_sha256"]
        and independent_bootstrap_review["source_sha"] == allocation["source_sha"],
        "RA_G1_BOOTSTRAP_REVIEW_REQUIRED",
    )
    report_sha = c.sha(implementation_report).hex()
    c.require(
        resource_review["source_sha"] == allocation["source_sha"]
        and resource_review["disposition"] == "PASS",
        "RA_G1_RESOURCE_REVIEW_REQUIRED",
    )
    a = contract_for_allocation(allocation)
    policy = a.descriptors()[m.POLICY]
    graph = {
        "schema_version": "stage12_ra_g1_representative_invocation_graph_v1",
        "source_git_sha": allocation["source_sha"],
        "phases": [
            dict(
                id=i,
                label=label,
                duration_ms=duration,
                hold_regular_acks=hold,
                works=count,
            )
            for i, (label, duration, hold, count) in enumerate(phases_for(allocation), 1)
        ],
        "python_roles": list(m.ROLES),
        "maximum_attempts": 107,
        "expected_attempts": 106,
        "scope": SCOPE,
        "service_authority": False,
    }
    descriptor_inventory = {
        name: digest(value) for name, value in a.descriptors(
            rep_admin_successor=allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS,
            first64_512_successor=allocation.get("version") in REP512_ALLOCATION_VERSIONS,
            foreground_successor=allocation.get("version") in (REP_FOREGROUND_ALLOCATION_VERSION,REP_ACK_ALLOCATION_VERSION,REP_FAIR_ALLOCATION_VERSION),
            **({"fair_service_successor":True} if allocation.get("version")==REP_FAIR_ALLOCATION_VERSION else {"ack_queue_successor":True} if allocation.get("version")==REP_ACK_ALLOCATION_VERSION else {})).items()
    }
    paths = {
        "scope": SCOPE,
        "paths": allocation["paths"],
        "source_git_sha": allocation["source_sha"],
        "native_paths": [],
    }
    selected = resource_selection(
        allocation,
        policy_sha256=digest(policy),
        adoption_sha256=digest(adoption),
        descriptor_inventory_sha256=digest(descriptor_inventory),
        graph_sha256=digest(graph),
        paths_sha256=digest(paths),
        implementation_review_sha256=report_sha,
    )
    cap = deepcopy(bootstrap["capacity"])
    cap.update(
        selection_sha256=digest(selected),
        owner_reported_approval_sha256=digest(project_approval),
    )
    # Values/times/identities originate in the exact same allocation collector.
    m.validate_capacity(cap, selection_sha256=digest(selected), scope=SCOPE)
    config, phases, roles = build_campaigns(
        allocation, {"job_id": bootstrap["job_id"]}, selected, cap
    )
    config["resource_execution"] = deepcopy(bootstrap["resource_execution"])
    initial_digest = digest(actual)
    runtime_inventory = bootstrap["runtime_inventory"]
    evidence = {key: {} for key in ROLES}

    def retain(role, value):
        identity = digest(value)
        evidence[role][identity] = value
        return identity

    for role, value in [
        ("policies", policy),
        ("adoptions", adoption),
        ("selections", selected),
        ("observations", actual),
        ("observations", bootstrap["kernel_originals"]),
        ("capacities", cap),
        ("capacities", bootstrap["capacity_originals"]["root"]),
        ("capacities", bootstrap["capacity_originals"]["statvfs"]),
        ("capacities", bootstrap["capacity_method"]),
        ("capacities", bootstrap["capacity_restrictions"]),
        ("graphs", graph),
        ("owner_reports", project_approval),
        ("logical", resource_review),
    ]:
        retain(role, value)
    risk = dict(
        schema_version=m.RISK,
        scope=SCOPE,
        method=m.METHOD,
        policy_sha256=digest(policy),
        adoption_sha256=digest(adoption),
        entries=[
            dict(
                risk=kind,
                observation_scope="GUARDED_ADMINISTRATIVE_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "NOT_OBSERVABLE",
                control="FINITE_GUARDED_SUFFIX"
                if kind == "UNMONITORED_ADMINISTRATIVE_SUFFIX"
                else "EXPLICIT_ACCEPTED_UNKNOWN",
                maximum="NOT_PROVEN",
                evidence_sha256=digest(adoption),
            )
            for kind in m.RISKS
        ],
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        complete_descendant_coverage="NOT_ESTABLISHED",
    )
    m.validate_risk_inventory(risk)
    retain("risks", risk)
    scratch_bytes = 64640  # Preserve historical builder bytes.
    if allocation.get("version") in (SHARED_LEASE_ALLOCATION_VERSION, *REP_ADMIN_ALLOCATION_VERSIONS):
        from safe_geocoding_pipeline.preprocessing.stages.s12_wf_ap2_scratch import RA_G1_CAPS

        scratch_bytes = sum(RA_G1_CAPS.values())
    sizes = [65536, 8 * 2**20, 2**21, scratch_bytes, 32768, 16384, 5 * 2**20]
    template = dict(
        schema_version=m.BOUND,
        scope=SCOPE,
        method=m.METHOD,
        policy_sha256=digest(policy),
        adoption_sha256=digest(adoption),
        selection_sha256=digest(selected),
        source_git_sha=allocation["source_sha"],
        source_inventory_sha256=digest(source_files),
        runtime_inventory_sha256=digest(runtime_inventory),
        configuration_scope_sha256=m.configuration_scope(config),
        invocation_graph_sha256=digest(graph),
        owner_reported_project_approval_sha256=digest(project_approval),
        initial_environment_observation_sha256=initial_digest,
        risk_inventory_sha256=digest(risk),
        maximum_identity_checks=allocation["accounting"]["identity_calls"],
        maximum_original_read_calls=allocation["accounting"]["original_read_calls"],
        maximum_original_read_bytes=allocation["accounting"]["original_read_bytes"],
        logical_allocations=[
            dict(name=name, bytes=size, evidence_sha256=digest(resource_review))
            for name, size in zip(m.ARENAS, sizes, strict=True)
        ],
        total_logical_bytes=sum(sizes),
        logical_scratch_bytes=scratch_bytes,
        valid_from=allocation["valid_from"],
        valid_until=allocation["valid_until"],
        native_component_guarantee="NOT_CLAIMED",
        job_domain_guarantee="NOT_ESTABLISHED",
        physical_capacity_guarantee="NOT_RESERVED_OR_PROVEN",
    )
    bound_review = dict(
        schema_version=BOUND_REVIEW,
        scope=SCOPE,
        disposition="PASS",
        bound_scope_sha256=digest(template),
        implementation_review_sha256=report_sha,
    )
    record = {
        **template,
        "technical_review_sha256": retain("technical_reviews", bound_review),
    }
    retain("runtime_bounds", record)
    starts = []
    for item, phase in zip(config["campaigns"], phases, strict=True):
        profile, plan = item["profile"], item["plan"]
        profile["sampling_runtime_bound_sha256"] = digest(record)
        plan["operations_profile_sha256"] = digest(profile)
        start = dict(
            schema_version=a.START,
            scope=a.SCOPE,
            campaign_id=digest([bootstrap["job_id"], item["label"], "campaign"]),
            profile_sha256=digest(profile),
            plan_sha256=digest(plan),
            rule_bundle_sha256=a.RULE_BUNDLE,
            policy_freeze_record_sha256=config["sources"]["policy_freeze"],
            implementation_authorization_sha256=config["sources"]["owner"],
            implementation_review_sha256=None,
            initial_workload_authority_sha256=config["sources"]["owner"],
            client_git_sha=allocation["source_sha"],
            runtime_inventory_sha256=digest(runtime_inventory),
            created_utc=bootstrap["created_utc"],
            sampling_policy_sha256=a.POLICY_SHA,
            **a.assurance_fields(),
        )
        starts.append(start)
        phase["start"] = start
    # Configurationscope excludes only bound/profile selfpointers as specified.
    c.require(
        record["configuration_scope_sha256"] == m.configuration_scope(config),
        "RA_G1_CONFIGURATION_CYCLE",
    )
    if allocation.get("version") in (BOOTSTRAP_ALLOCATION_VERSION, SHARED_LEASE_ALLOCATION_VERSION, *REP_ADMIN_ALLOCATION_VERSIONS):
        retained = retain("adoptions", allocation["bootstrap_prefix_adoption"])
        c.require(retained == allocation["bootstrap_prefix_adoption_sha256"], "RA_G1_BOOTSTRAP_POLICY")
    if allocation.get("version") in REP_ADMIN_ALLOCATION_VERSIONS:
        retained = retain("adoptions", allocation["rep_admin_budget_adoption"])
        c.require(retained == allocation["rep_admin_budget_adoption_sha256"], "RA_G1_SELECTION_BINDING")
    if allocation.get("version") in REP512_ALLOCATION_VERSIONS:
        retained = retain("adoptions", allocation["rep_first64_512_adoption"])
        c.require(retained == allocation["rep_first64_512_adoption_sha256"], "RA_G1_SELECTION_BINDING")
    if allocation.get("version")==REP_ACK_ALLOCATION_VERSION:
        retained=retain("adoptions",allocation["rep_ack_policy_adoption"])
        c.require(retained==allocation["rep_ack_policy_adoption_sha256"],"RA_G1_SELECTION_BINDING")
    review = dict(
        version=DIAGNOSTIC_REVIEW,
        scope=SCOPE,
        disposition="PASS",
        configuration_sha256=digest(config),
        report_sha256=report_sha,
        source_files=source_files,
        resource_evidence={role: sorted(values) for role, values in evidence.items()},
    )
    for start in starts:
        start["implementation_review_sha256"] = digest(review)
    replay_path = (
        Path(__file__).resolve().parent.parent
        / "docs/scientific_assets/stage12_wf_ap2_representative_replay_v1.json"
    )
    replay = json.loads(replay_path.read_bytes())
    c.require(digest(replay) == allocation["replay_sha256"], "RA_G1_REPLAY_CHANGED")
    data = dict(
        version=(REP_FAIR_VERSION if allocation.get("version")==REP_FAIR_ALLOCATION_VERSION else REP_ACK_VERSION if allocation.get("version")==REP_ACK_ALLOCATION_VERSION else REP_FOREGROUND_VERSION if allocation.get("version") == REP_FOREGROUND_ALLOCATION_VERSION else REP512_VERSION if allocation.get("version") in REP512_ALLOCATION_VERSIONS
                  else REP_ADMIN_VERSION if allocation.get("version") == REP_ADMIN_ALLOCATION_VERSION
                 else SHARED_LEASE_VERSION if allocation.get("version") == SHARED_LEASE_ALLOCATION_VERSION
                 else BOOTSTRAP_VERSION if allocation.get("version") == BOOTSTRAP_ALLOCATION_VERSION else VERSION),
        scope=SCOPE,
        source_sha=allocation["source_sha"],
        selection={
            "status": "ISSUED" if issued else "UNISSUED",
            "authority_sha256": digest(["PENDING_SELECTION", digest(config)]),
            "resource_review_sha256": digest(
                ["PENDING_RESOURCE_REVIEW", digest(config)]
            ),
        },
        limits=dict(
            seconds=7200,
            maximum_bytes=72 * 2**30,
            maximum_creations=204860 if allocation.get("version") in REP512_ALLOCATION_VERSIONS else 184184,
            rss_bytes=768 * 2**20,
            maximum_input_bytes=4 * 2**20,
            summary_reserve_bytes=2**20,
            native_helper_bytes_reserve=128 * 2**20,
            native_helper_creation_reserve=64,
        ),
        configuration=config,
        phases=phases,
        runtime_inventory=runtime_inventory,
        responses=replay["responses"],
    )
    resource_record = dict(
        version="stage12_ra_g1_diagnostic_resources_v1",
        scope=SCOPE,
        source_sha=allocation["source_sha"],
        limits=data["limits"],
        resources=config["resources"],
        status="ISSUED",
        method=m.METHOD,
        capacity_entitlement="NOT_ASSERTED",
        native_physical_maximum="NOT_PROVEN",
    )
    data["selection"]["resource_review_sha256"] = digest(resource_record)
    projected = deepcopy(data)
    projected["selection"].pop("authority_sha256")
    selection_record = dict(
        version="stage12_ra_g1_diagnostic_selection_v1",
        scope=SCOPE,
        status="ISSUED",
        input_scope_sha256=digest(projected),
        source_sha=allocation["source_sha"],
        resource_review_sha256=digest(resource_record),
        service_authority=False,
    )
    data["selection"]["authority_sha256"] = digest(selection_record)
    for item, phase in zip(config["campaigns"], phases, strict=True):
        a.validate_plan(item["plan"], item["profile"])
        a.validate(phase["start"], a.START)
        m.validate_record(
            record, item["profile"], phase["start"], a, m.configuration_scope(config)
        )
    return data, dict(
        role_records=roles,
        resource_evidence=evidence,
        integration_review=review,
        integration_report_utf8=implementation_report.decode("utf8"),
        diagnostic_selection=selection_record,
        diagnostic_resources=resource_record,
        resource_selection=selected,
        binding=record,
        paths=paths,
        invocation_graph=graph,
        descriptor_inventory=descriptor_inventory,
    )

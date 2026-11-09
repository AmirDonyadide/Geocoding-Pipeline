"""Pure, acyclic RA-G1 public preparation; no input/provider or authority I/O.

The frozen v1 public matrix is a byte-pinned template. ``prepare`` produces an
unissued exact bound subject. ``finalize`` requires a separately supplied review
of that subject. Neither function manufactures a PASS or issues permissions.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_ra_g1_accounting as accounting_compiler,
)

from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_ra_g1_assurance as assurance,
)
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_ra_g1_execution as execution,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import (
    BOUND_REVIEW,
    REVIEW,
    PUBLIC_ROLES,
)

SCOPE = "PUBLIC_SYNTHETIC_ONLY"
TEMPLATE_SHA256 = "c0669bd39dd9b7a71aee563e97245fc054c746adcc2d4d6420fe10afd43d43f4"
PREPARED = "stage12_ra_g1_public_prepared_bound_v1"
GRAPH = "stage12_ra_g1_public_invocation_graph_v1"
OUTCOME = "stage12_ra_g1_representative_independent_outcome_v1"
ROLE_NAMES = (
    "owner",
    "operator",
    "policy_freeze",
    "selection",
    "transport",
    "size_allowance",
)
MAX_CREATIONS, MAX_LOGICAL_BYTES = 791452, 512 * 2**30


def canonical(value: Any) -> bytes:
    return c.canonical(value)


def digest(value: Any) -> str:
    return c.sha(canonical(value)).hex()


def raw_digest(value: bytes) -> str:
    c.require(type(value) is bytes, "RA_G1_ORIGINAL_REQUIRED")
    return hashlib.sha256(value).hexdigest()


def read_template(raw: bytes, *, test_only: bool = False) -> dict[str, Any]:
    c.require(
        type(test_only) is bool and type(raw) is bytes and len(raw) <= 4 * 2**20,
        "RA_G1_PUBLIC_TEMPLATE",
    )
    if not test_only:
        c.require(raw_digest(raw) == TEMPLATE_SHA256, "RA_G1_PUBLIC_TEMPLATE_CHANGED")

    def pairs(items: Any) -> dict[str, Any]:
        c.require(len({key for key, _ in items}) == len(items), "RA_G1_FIELDS")
        return dict(items)

    value = json.loads(raw, object_pairs_hook=pairs)
    c.require(
        canonical(value) == raw and value.get("version") == runtime.MATRIX_VERSION,
        "RA_G1_PUBLIC_TEMPLATE",
    )
    runtime.validate_config(value)
    totals = matrix.validate_matrix(value)
    c.require(
        totals
        == dict(
            attempts=2920,
            events=206000,
            storage_bytes=480 * 2**30,
            phase_duration_ms=5180000,
        ),
        "RA_G1_PUBLIC_TEMPLATE",
    )
    return value


def phase_budget(duration: int, attempts: int) -> dict[str, int]:
    observations = (duration + 49) // 50 + 2
    files = 4 * observations + 8
    timing_rows = observations + attempts + 16
    return dict(
        observations=observations,
        events=19 * attempts + 40 + 2 * observations + 4,
        sample_events=2 * observations + 4,
        sample_files=files + 8,
        sample_bytes=4096 * files + 8 * (512 * files + 4096),
        timing_chunks=(timing_rows + 55) // 56 + (duration + 4999) // 5000 + 3,
    )


def compile_budget(template: dict[str, Any]) -> dict[str, Any]:
    """Exact adopted integer calculation, including failure and tail liabilities."""
    phases = []
    for item in template["campaigns"]:
        ordinary = item["plan"]["budgets"]
        q = ordinary["data_attempts"] + ordinary["control_http_attempts"]
        phases.append(phase_budget(ordinary["active_duration_ms"], q))
    total = {key: sum(row[key] for row in phases) for key in phases[0]}
    total["timing_chunks"] += 1
    total["monitor_rows"] = (8160000 + 499) // 500 + 2 * 14 + 4
    total["monitor_creations"] = 2 * total["monitor_rows"] + 4 * 14 + 16
    total["monitor_bytes"] = total["monitor_creations"] * 8192
    total["creations"] = (
        total["sample_files"]
        + total["events"]
        + 24 * 2920
        + 128 * 11
        + 128
        + total["timing_chunks"]
        + 64
        + total["monitor_creations"]
        + 2048
        + 4096
    )
    total["logical_bytes"] = (
        480 * 2**30
        + total["sample_bytes"]
        + 2 * total["timing_chunks"] * 32768
        + total["monitor_bytes"]
        + 384 * 2**20
    )
    c.require(
        total["timing_chunks"] == 2980
        and total["creations"] == MAX_CREATIONS
        and total["monitor_rows"] == 16352
        and total["logical_bytes"] <= MAX_LOGICAL_BYTES,
        "RA_G1_PUBLIC_COMPILER_DISAGREEMENT",
    )
    return dict(phases=phases, totals=total)


def invocation_graph(template: dict[str, Any], source_sha: str) -> dict[str, Any]:
    compiled = compile_budget(template)
    return dict(
        schema_version=GRAPH,
        scope=SCOPE,
        source_git_sha=source_sha,
        template_sha256=digest(template),
        phases=[
            dict(
                id=i,
                label=item["label"],
                duration_ms=item["plan"]["budgets"]["active_duration_ms"],
                work_manifest_sha256=item["plan"]["work_manifest_sha256"],
            )
            for i, item in enumerate(template["campaigns"], 1)
        ],
        whole_task_phase=12,
        whole_task_deadline_ms=2000000,
        setup_phase=13,
        setup_deadline_ms=840000,
        terminal_phase=14,
        terminal_deadline_ms=120000,
        python_roles=list(assurance.ROLES),
        compiled=compiled,
        native_invocations=0,
        protected_authority=False,
    )


def compile_selection(
    allocation: dict[str, Any],
    template: dict[str, Any],
    *,
    policy_sha256: str,
    adoption_sha256: str,
    descriptor_inventory_sha256: str,
    paths_sha256: str,
    implementation_review_sha256: str,
) -> dict[str, Any]:
    graph, compiled = (
        invocation_graph(template, allocation["source_sha"]),
        compile_budget(template),
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
    stage_caps = {
        row["stage_id"]: accounting_compiler.stage_accounting(
            accounting_inventory, row["stage_id"]
        )
        for row in accounting_inventory["stage_accounting"]
    }
    stages = []
    for i, (item, phase) in enumerate(
        zip(template["campaigns"], compiled["phases"], strict=True), 1
    ):
        ordinary = item["plan"]["budgets"]
        attempts = ordinary["data_attempts"] + ordinary["control_http_attempts"]
        monitor_rows = (ordinary["active_duration_ms"] + 499) // 500 + 2
        stages.append(
            dict(
                id=i,
                phase=i,
                deadline_ms=ordinary["active_duration_ms"],
                reserve_ms=item["plan"]["shutdown_reserve_ms"],
                attempts=attempts,
                events=phase["events"],
                logical_write_bytes=ordinary["storage_bytes"] + phase["sample_bytes"],
                creations=phase["sample_files"]
                + phase["events"]
                + 24 * attempts
                + 128
                + phase["timing_chunks"]
                + 2 * monitor_rows
                + 4,
                **stage_caps[i],
            )
        )
    for i, duration, reserved, extra in (
        (12, 2000000, 64 * 2**20, 128),
        (13, 840000, 160 * 2**20, 2048),
        (14, 120000, 256 * 2**20, 4096),
    ):
        rows = (duration + 499) // 500 + 2
        stages.append(
            dict(
                id=i,
                phase=i,
                deadline_ms=duration,
                reserve_ms=5000,
                attempts=0,
                events=0,
                logical_write_bytes=reserved,
                creations=2 * rows + 4 + extra,
                **stage_caps[i],
            )
        )
    remaining = MAX_CREATIONS - sum(row["creations"] for row in stages)
    c.require(remaining >= 0, "RA_G1_PUBLIC_COMPILER_DISAGREEMENT")
    stages[11]["creations"] += remaining
    counters = {role: 0 for role in assurance.LIMITS["application_counters"]}
    counters.update(
        COMPRESSED_FRAME=2920,
        EXCLUSIVE_FILE=MAX_CREATIONS,
        EVENT_FILE=compiled["totals"]["events"],
        PREFIX_FILE=584,
        COMPARISON_FILE=1024,
        ADMIN_FILE=8192,
        CONTROL_BEGIN=40,
        CONTROL_FINISH=40,
    )
    selected = dict(
        schema_version=assurance.SELECTION,
        scope=SCOPE,
        policy_sha256=policy_sha256,
        adoption_sha256=adoption_sha256,
        source_git_sha=allocation["source_sha"],
        descriptor_inventory_sha256=descriptor_inventory_sha256,
        workload_graph_sha256=digest(graph),
        paths_sha256=paths_sha256,
        valid_from=allocation["valid_from"],
        valid_until=allocation["valid_until"],
        review_sha256=implementation_review_sha256,
        limits=dict(
            processing_ms=8160000,
            scheduler_s=8400,
            processes=4,
            threads=256,
            utilities=256,
            python_invocations=5,
            python_roles=[dict(role=role, maximum=1) for role in assurance.ROLES],
            input_bytes=4 * 2**20,
            metadata_bytes=4 * 2**20,
            attempts=2960,
            logical_write_bytes=MAX_LOGICAL_BYTES,
            creations=MAX_CREATIONS,
            telemetry_chunks=2980,
            telemetry_bytes=2 * 2980 * 32768,
            telemetry_creations=2981,
            monitor_rows=16352,
            monitor_bytes=268500992,
            monitor_creations=32776,
            closure_reserve_bytes=256 * 2**20,
            closure_reserve_creations=4096,
            native_invocations=0,
            stages=stages,
            application_counters=counters,
        ),
        monitor=dict(
            period_ms=500,
            max_observed_interval_ms=1000,
            self_rss_stop_bytes=768 * 2**20,
            aggregate_rss_stop_bytes=5 * 2**30,
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
            dict(
                scope=SCOPE,
                required=[
                    "owner_adoption",
                    "independent_release",
                    "actual_bootstrap_review",
                    "canonical_config_review",
                    "representative_complete_independent_PASS",
                    "private_paths",
                    "usable_shared_accounting",
                    "phase_specific_service_originals",
                ],
            )
        ),
    )
    assurance.validate_selection(selected)
    return selected


def verify_representative(
    record: Any, report: bytes, manifest: bytes, source_sha: str
) -> None:
    assurance.shape(
        record,
        dict(
            schema_version="=" + OUTCOME,
            scope="=REPRESENTATIVE_NO_SERVICE",
            source_git_sha="G",
            selection_sha256="D",
            input_sha256="D",
            artifact_manifest_sha256="D",
            independent_report_sha256="D",
            disposition="=PASS_COMPLETE_REPRESENTATIVE",
            expected_attempts="=106",
            maximum_attempts="=107",
            scenarios_completed="=4",
            actual_reopening="B",
            sampling_and_monitor_coverage="=COMPLETE_SELECTED_SCOPE",
            authority_attribution="=INDEPENDENT_AGENT_OUTCOME_NOT_HUMAN_OR_OPERATOR",
        ),
    )
    c.require(
        record["source_git_sha"] == source_sha
        and record["actual_reopening"] is True
        and raw_digest(report) == record["independent_report_sha256"]
        and raw_digest(manifest) == record["artifact_manifest_sha256"]
        and 0 < len(report) <= 4 * 2**20
        and 0 < len(manifest) <= 4 * 2**20,
        "RA_G1_REPRESENTATIVE_RELEASE_REQUIRED",
    )


def prepare(
    template_raw: bytes,
    allocation: dict[str, Any],
    bootstrap: dict[str, Any],
    *,
    role_originals: dict[str, bytes],
    source_files: list[dict[str, str]],
    implementation_report: bytes,
    adoption: dict[str, Any],
    project_approval: dict[str, Any],
    resource_review: dict[str, Any],
    independent_bootstrap_review: dict[str, Any],
    representative_outcome: dict[str, Any],
    representative_report: bytes,
    representative_manifest: bytes,
    test_only: bool = False,
) -> dict[str, Any]:
    """Build an unissued subject using retained originals; review happens later."""
    template = read_template(template_raw, test_only=test_only)
    c.require(source_files == allocation["source_files"], "RA_G1_SOURCE_INVENTORY")
    c.require(set(role_originals) == set(ROLE_NAMES), "RA_G1_PUBLIC_ROLE_ORIGINALS")
    role_hashes = {role: raw_digest(raw) for role, raw in role_originals.items()}
    c.require(
        all(0 < len(raw) <= 65536 for raw in role_originals.values()),
        "RA_G1_PUBLIC_ROLE_ORIGINALS",
    )
    source_sha = allocation["source_sha"]
    c.require(
        bootstrap["source_sha"] == source_sha and bootstrap["scope"] == SCOPE,
        "RA_G1_BOOTSTRAP_BINDING",
    )
    assurance.shape(bootstrap["facts"], assurance.FACTS)
    c.require(
        bootstrap["facts"]["origin"]
        == ("SYNTHETIC_TEST_ONLY" if test_only else "LIVE_KERNEL_OBSERVATION"),
        "RA_G1_ACTUAL_BOOTSTRAP_REQUIRED",
    )
    if not test_only:
        assurance.validate_environment_originals(
            bootstrap["facts"], bootstrap["kernel_originals"]
        )
    c.require(
        independent_bootstrap_review["disposition"] == "PASS"
        and independent_bootstrap_review["source_sha"] == source_sha
        and independent_bootstrap_review["bootstrap_manifest_sha256"]
        == bootstrap["manifest_sha256"],
        "RA_G1_BOOTSTRAP_REVIEW_REQUIRED",
    )
    c.require(
        resource_review["source_sha"] == source_sha
        and resource_review["disposition"] == "PASS",
        "RA_G1_RESOURCE_REVIEW_REQUIRED",
    )
    verify_representative(
        representative_outcome,
        representative_report,
        representative_manifest,
        source_sha,
    )
    execution.validate_execution_request(bootstrap["resource_execution"])
    c.require(
        1 <= len(source_files) <= 2048
        and [x["path"] for x in source_files]
        == sorted({x["path"] for x in source_files}),
        "RA_G1_SOURCE_INVENTORY",
    )
    for entry in source_files:
        assurance.shape(entry, {"path": "S", "bytes": "U", "sha256": "D"})
        c.require(entry["bytes"] <= 4 * 2**20, "RA_G1_SOURCE_INVENTORY")
        relative = Path(entry["path"])
        c.require(
            not relative.is_absolute()
            and ".." not in relative.parts
            and len(entry["path"].encode()) <= 512,
            "RA_G1_SOURCE_INVENTORY",
        )
    c.require(
        sum(row["bytes"] for row in source_files) <= 64 * 2**20,
        "RA_G1_SOURCE_INVENTORY",
    )
    descriptors = {
        name: digest(value) for name, value in contract.descriptors().items()
    }
    policy = contract.descriptors()[assurance.POLICY]
    paths = dict(
        scope=SCOPE,
        paths=deepcopy(allocation["paths"]),
        source_git_sha=source_sha,
        native_paths=[],
    )
    selected = compile_selection(
        allocation,
        template,
        policy_sha256=digest(policy),
        adoption_sha256=digest(adoption),
        descriptor_inventory_sha256=digest(descriptors),
        paths_sha256=digest(paths),
        implementation_review_sha256=raw_digest(implementation_report),
    )
    c.require(
        bootstrap["resource_selection_sha256"] == digest(selected),
        "RA_G1_SELECTION_BINDING",
    )
    capacity = deepcopy(bootstrap["capacity"])
    assurance.validate_capacity(
        capacity, selection_sha256=digest(selected), scope=SCOPE
    )
    c.require(
        capacity["owner_reported_approval_sha256"] == digest(project_approval),
        "RA_G1_CAPACITY_BINDING",
    )
    if not test_only:
        assurance.validate_capacity_originals(
            capacity,
            bootstrap["capacity_originals"]["root"],
            bootstrap["capacity_originals"]["statvfs"],
            bootstrap["capacity_method"],
            bootstrap["capacity_restrictions"],
        )
    resources = dict(
        application_admission_memory_bytes=4 * 2**30,
        requested_memory_bytes=6 * 2**30,
        logical_process_overhead_bytes=2**30,
        logical_pending_request_bytes=2**20,
        per_attempt_logical_write_ceiling_bytes=2**27,
        fixed_campaign_logical_write_ceiling_bytes=2**27,
        task_logical_write_ceiling_bytes=MAX_LOGICAL_BYTES,
        resource_selection_sha256=digest(selected),
        initial_capacity_observation_sha256=digest(capacity),
        resource_review_sha256=role_hashes["selection"],
        scheduler_guard_ms=template["resources"]["scheduler_guard_ms"],
        writer_guard_ms=5000,
    )
    config = deepcopy(template)
    config.update(
        version=runtime.RA_CONFIG,
        task_id=allocation["task_id"],
        output_directory=allocation["paths"]["output"],
        window_start=allocation["valid_from"],
        window_end=allocation["valid_until"],
        sources=role_hashes,
        resources=resources,
        resource_execution=deepcopy(bootstrap["resource_execution"]),
        representative_validation_sha256=digest(representative_outcome),
    )
    config["transport"]["configuration_evidence_sha256"] = role_hashes["transport"]
    if "approved_ip" in bootstrap:
        config["transport"]["approved_ip"] = bootstrap["approved_ip"]
    config["capability"]["operator_size_evidence_sha256"] = role_hashes[
        "size_allowance"
    ]
    budget = compile_budget(template)
    pointer = digest(
        dict(
            unissued_bound_subject=raw_digest(template_raw), selection=digest(selected)
        )
    )
    for item, phase in zip(config["campaigns"], budget["phases"], strict=True):
        profile, plan = item["profile"], item["plan"]
        profile.update(
            schema_version=contract.PROFILE,
            rule_bundle_sha256=contract.RULE_BUNDLE,
            policy_freeze_record_sha256=role_hashes["policy_freeze"],
            resources=deepcopy(resources),
            transport_profile_sha256=digest(config["transport"]),
            sampling_policy_sha256=contract.POLICY_SHA,
            sampling_runtime_bound_sha256=pointer,
            **contract.assurance_fields(),
        )
        profile.pop("resource_sample_period_ms")
        profile["operator_allowance"].update(
            record_sha256=role_hashes["operator"],
            valid_from=allocation["valid_from"],
            valid_until=allocation["valid_until"],
        )
        profile["monitoring"]["gaps_record_sha256"] = role_hashes["selection"]
        for state in profile["states"]:
            state["evidence_sha256"] = role_hashes["selection"]
        plan.update(
            schema_version=contract.PLAN,
            operations_profile_sha256=digest(profile),
            selection_basis_sha256=role_hashes["selection"],
            window_start=allocation["valid_from"],
            window_end=allocation["valid_until"],
            sampling_budget=dict(
                maximum_segments=1,
                maximum_observations=phase["observations"],
                maximum_inventory_versions_per_segment=8,
                additional_event_tokens=phase["sample_events"],
                additional_file_data_bytes=phase["sample_bytes"],
                additional_file_entries=phase["sample_files"],
            ),
            history_limits=dict(
                maximum_entries=791452,
                maximum_name_bytes=256,
                maximum_total_name_bytes=202611712,
                page_entries=128,
                maximum_depth=8,
                maximum_file_bytes=64 * 2**20,
            ),
        )
        plan["budgets"]["event_count"] = phase["events"]
        plan["budgets"]["storage_bytes"] += phase["sample_bytes"]
        plan["blocks"][0]["budget"] = deepcopy(plan["budgets"])
        for recipe in plan["control_recipes"]:
            recipe["transport_profile_sha256"] = digest(config["transport"])
        # Work identities/corpus/targets/repetitions and warning policy are fixed.
        plan["work_manifest_sha256"] = contract.manifest_digest(item["work"])
        contract.validate_plan(plan, profile)
    risk = dict(
        schema_version=assurance.RISK,
        scope=SCOPE,
        method=assurance.METHOD,
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
            for kind in assurance.RISKS
        ],
        native_maximum="NOT_PROVEN",
        physical_maximum="NOT_PROVEN",
        complete_descendant_coverage="NOT_ESTABLISHED",
    )
    assurance.validate_risk_inventory(risk)
    sizes = [65536, 8 * 2**20, 2**21, 64640, 32768, 16384, 5 * 2**20]
    bound = dict(
        schema_version=assurance.BOUND,
        scope=SCOPE,
        method=assurance.METHOD,
        policy_sha256=digest(policy),
        adoption_sha256=digest(adoption),
        selection_sha256=digest(selected),
        source_git_sha=source_sha,
        source_inventory_sha256=digest(source_files),
        runtime_inventory_sha256=digest(bootstrap["runtime_inventory"]),
        configuration_scope_sha256=assurance.configuration_scope(config),
        invocation_graph_sha256=digest(invocation_graph(template, source_sha)),
        owner_reported_project_approval_sha256=digest(project_approval),
        initial_environment_observation_sha256=digest(bootstrap["facts"]),
        risk_inventory_sha256=digest(risk),
        maximum_identity_checks=allocation["accounting"]["identity_calls"],
        maximum_original_read_calls=allocation["accounting"]["original_read_calls"],
        maximum_original_read_bytes=allocation["accounting"]["original_read_bytes"],
        logical_allocations=[
            dict(name=name, bytes=size, evidence_sha256=digest(resource_review))
            for name, size in zip(assurance.ARENAS, sizes, strict=True)
        ],
        total_logical_bytes=sum(sizes),
        logical_scratch_bytes=64640,
        valid_from=allocation["valid_from"],
        valid_until=allocation["valid_until"],
        native_component_guarantee="NOT_CLAIMED",
        job_domain_guarantee="NOT_ESTABLISHED",
        physical_capacity_guarantee="NOT_RESERVED_OR_PROVEN",
    )
    evidence = {role: {} for role in PUBLIC_ROLES}
    for role, value in [
        ("policies", policy),
        ("adoptions", adoption),
        ("selections", selected),
        ("observations", bootstrap["facts"]),
        ("observations", bootstrap["kernel_originals"]),
        ("capacities", capacity),
        ("capacities", bootstrap["capacity_originals"]["root"]),
        ("capacities", bootstrap["capacity_originals"]["statvfs"]),
        ("capacities", bootstrap["capacity_method"]),
        ("capacities", bootstrap["capacity_restrictions"]),
        ("graphs", invocation_graph(template, source_sha)),
        ("risks", risk),
        ("owner_reports", project_approval),
        ("logical", resource_review),
        ("representative_outcomes", representative_outcome),
    ]:
        evidence[role][digest(value)] = value
    return dict(
        schema_version=PREPARED,
        status="UNISSUED_REQUIRES_EXACT_TECHNICAL_REVIEW",
        test_only=test_only,
        template_sha256=raw_digest(template_raw),
        configuration=config,
        bound_subject=bound,
        bound_scope_sha256=digest(bound),
        resource_selection=selected,
        source_files=deepcopy(source_files),
        role_originals=deepcopy(role_originals),
        implementation_report=implementation_report,
        resource_evidence=evidence,
        representative_originals={
            representative_outcome["independent_report_sha256"]
            + ".md": representative_report,
            representative_outcome["artifact_manifest_sha256"]
            + ".manifest": representative_manifest,
        },
        paths=paths,
        descriptor_inventory=descriptors,
        compiled=budget,
    )


def finalize(
    prepared: dict[str, Any], technical_review: dict[str, Any], *, issued: bool = False
) -> dict[str, Any]:
    """Bind one separately issued exact review; preserve the acyclic config scope."""
    c.require(
        prepared["schema_version"] == PREPARED
        and prepared["status"] == "UNISSUED_REQUIRES_EXACT_TECHNICAL_REVIEW",
        "RA_G1_PREPARED_REQUIRED",
    )
    c.require(
        type(issued) is bool and not (issued and prepared["test_only"]),
        "RA_G1_SYNTHETIC_CANNOT_ISSUE",
    )
    bound = deepcopy(prepared["bound_subject"])
    c.require(
        digest(bound) == prepared["bound_scope_sha256"], "RA_G1_BOUND_SUBJECT_CHANGED"
    )
    assurance.shape(
        technical_review,
        dict(
            schema_version="=" + BOUND_REVIEW,
            scope="=" + SCOPE,
            disposition="=PASS",
            bound_scope_sha256="D",
            implementation_review_sha256="D",
        ),
    )
    c.require(
        technical_review["bound_scope_sha256"] == digest(bound)
        and technical_review["implementation_review_sha256"]
        == raw_digest(prepared["implementation_report"]),
        "RA_G1_EXACT_TECHNICAL_REVIEW_REQUIRED",
    )
    bound["technical_review_sha256"] = digest(technical_review)
    config = deepcopy(prepared["configuration"])
    evidence = deepcopy(prepared["resource_evidence"])
    c.require(
        digest(prepared["source_files"]) == bound["source_inventory_sha256"]
        and digest(prepared["resource_selection"]) == bound["selection_sha256"],
        "RA_G1_PREPARED_CHANGED",
    )
    for role, values in evidence.items():
        c.require(role in PUBLIC_ROLES, "RA_G1_EVIDENCE_SCOPE")
        for identity, value in values.items():
            c.require(digest(value) == identity, "RA_G1_EVIDENCE_CHANGED")
    c.require(
        {role: raw_digest(raw) for role, raw in prepared["role_originals"].items()}
        == config["sources"],
        "RA_G1_PUBLIC_ROLE_ORIGINALS",
    )
    evidence["technical_reviews"][digest(technical_review)] = deepcopy(technical_review)
    evidence["runtime_bounds"][digest(bound)] = bound
    for item in config["campaigns"]:
        item["profile"]["sampling_runtime_bound_sha256"] = digest(bound)
        item["plan"]["operations_profile_sha256"] = digest(item["profile"])
        contract.validate_plan(item["plan"], item["profile"])
    c.require(
        assurance.configuration_scope(config) == bound["configuration_scope_sha256"],
        "RA_G1_CONFIGURATION_CYCLE",
    )
    runtime.validate_config(config)
    review = dict(
        version=REVIEW,
        scope=SCOPE,
        disposition="PASS",
        configuration_sha256=digest(config),
        report_sha256=raw_digest(prepared["implementation_report"]),
        source_files=deepcopy(prepared["source_files"]),
        resource_evidence={role: sorted(values) for role, values in evidence.items()},
    )
    return dict(
        status="ISSUED" if issued else "UNISSUED",
        configuration=config,
        binding=bound,
        integration_review=review,
        integration_report=prepared["implementation_report"],
        role_originals=deepcopy(prepared["role_originals"]),
        resource_evidence=evidence,
        representative_originals=deepcopy(prepared["representative_originals"]),
        resource_selection=deepcopy(prepared["resource_selection"]),
        compiled=deepcopy(prepared["compiled"]),
    )

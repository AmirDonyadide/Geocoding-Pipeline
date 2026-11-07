"""Opt-in RS1 acceptance envelope and original-content append-only graph.

The envelope reserves every possible command, including unused commands. This
module issues neither capacity nor scientific or service authority. An absent
original, proof, grant, or selected native bound prevents execution.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import threading
from types import SimpleNamespace

from . import s12_b2_contract as b
from . import s12_b2_resources as rs
from . import s12_b2_allocation_limits as limits
from . import s12_storage as io

MODEL = "stage12_development_resource_retention_acceptance_b2_rs1_v1"
MEMBER = "stage12_resource_member_binding_b2_rs1_acceptance_v1"
BINDING = "stage12_resource_command_binding_b2_rs1_acceptance_v1"
BRANCH = "stage12_resource_N_branch_b2_rs1_acceptance_v1"
SKIP = "stage12_resource_command_skip_b2_rs1_acceptance_v1"
BEGIN = "stage12_resource_command_begin_b2_rs1_acceptance_v1"
FINISH = "stage12_resource_command_finish_b2_rs1_acceptance_v1"
CEILING = "stage12_resource_allocation_ceiling_b2_rs1_acceptance_v1"
SCOPE = "stage12_resource_command_scope_b2_rs1_acceptance_v1"
DESCRIPTOR = "stage12_resource_acceptance_graph_descriptor_b2_rs1_v1"
ADOPTED_SPEC_SHA256 = "c15a0aabbf6e851c37452e02d5ebfebd96400a78da49bbfd7c8c61b5f0de5a85"
MAX_SLOTS = 512
COUNTS = (
    "data_works",
    "data_attempts",
    "control_works",
    "control_attempts",
    "candidate_rows",
    "events",
    "ledger_rows",
)
KINDS = ("FULL_C", "TAIL", "PAIRED", "DIRECT_N")
PREREQUISITES = (
    "LOCAL_AUTHORITY",
    "CALIBRATION_SELECTION",
    "CALIBRATION_RESULT",
    "N_DECISION",
    "WINDOW_PLAN",
    "SEGMENT_CLOSURE",
    "CAMPAIGN_CLOSURE",
    "WINDOW_CLOSURE",
    "PUBLICATION_MANIFEST",
    "REVIEW_COMPLETION",
)
_LOCK = threading.Lock()


def _ledger_file_identity(info):
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
    )


def enum(*values):
    return {"enum": list(values)}


MEMBER_ENVELOPE = {
    "member_id": "P",
    "workload_kind": enum(*KINDS),
    "repetition": "U",
    "permitted_result_limits": ["P"],
    **dict.fromkeys(COUNTS, "U"),
}
SLOT = {
    "slot_id": "P",
    "phase": enum(*rs.COMMAND_PHASES),
    "member_role": enum("NONE", "FIXED_MEMBER", "SELECTED_FINAL"),
    "member_id": "P?",
    "condition": enum(
        "REQUIRED",
        "CONTINUATION_CAPACITY",
        "DIRECT_N_BRANCH",
        "OPTIONAL_INDEPENDENT_REOPEN",
    ),
    "predecessor_slot_id": "U",
    "max_duration_ms": "P",
    "max_memory_bytes": "P",
    "max_generated_bytes": "P",
    "max_generated_inodes": "P",
    "allocations": dict.fromkeys(rs.COUNTS, "U"),
    "allocation_limit_ceiling_sha256": "D",
    "predicate_version": "=RS1_ACCEPTANCE_GRAPH_V1",
}
LEDGER_LIMITS = dict.fromkeys(
    (
        "max_member_bindings",
        "max_slot_bindings",
        "max_begins",
        "max_terminals",
        "max_branch_records",
    ),
    "U",
) | dict.fromkeys(
    (
        "max_prerequisite_rows",
        "max_prerequisite_bytes",
        "max_record_bytes",
        "max_total_bytes",
        "max_entries",
    ),
    "P",
)
MODEL_SCHEMA = {
    k: deepcopy(v)
    for k, v in rs.MODEL_SCHEMA.items()
    if k not in ("member_workloads", "commands")
}
MODEL_SCHEMA.update(
    schema_version="=" + MODEL,
    parent_descriptor_sha256="D",
    successor_descriptor_sha256="D",
    adoption_sha256="D",
    window_policy="=ONE_DECLARED_SP_B_R2_WINDOW",
    member_envelopes=[MEMBER_ENVELOPE],
    slots=[SLOT],
    ledger_record_limits=LEDGER_LIMITS,
)
MEMBER_SCHEMA = {
    "schema_version": "=" + MEMBER,
    "envelope_sha256": "D",
    "member_id": "P",
    "previous_ledger_sha256": "D?",
    **dict.fromkeys(
        (
            "plan_binding_sha256",
            "exact_plan_sha256",
            "work_file_sha256",
            "window_plan_sha256",
            "calibration_selection_sha256",
        ),
        "D",
    ),
    "N_decision_sha256": "D?",
    "bound_utc": "Z",
}
BINDING_SCHEMA = {
    "schema_version": "=" + BINDING,
    "envelope_sha256": "D",
    "slot_id": "P",
    "previous_ledger_sha256": "D?",
    **dict.fromkeys(
        (
            "configuration_scope_sha256",
            "command_scope_sha256",
            "source_inventory_sha256",
            "runtime_inventory_sha256",
            "allocation_limits_sha256",
            "prerequisite_inventory_sha256",
        ),
        "D",
    ),
    "member_binding_sha256": "D?",
    "bound_utc": "Z",
}
BRANCH_SCHEMA = {
    "schema_version": "=" + BRANCH,
    **dict.fromkeys(
        (
            "envelope_sha256",
            "previous_ledger_sha256",
            "window_plan_sha256",
            "calibration_selection_sha256",
            "calibration_inventory_sha256",
            "adequacy_report_sha256",
            "N_decision_sha256",
        ),
        "D",
    ),
    "C": "P",
    "N": "P",
    "branch": enum("REUSE_FULL_C", "DIRECT_N"),
    "recorded_utc": "Z",
}
SKIP_SCHEMA = {
    "schema_version": "=" + SKIP,
    "envelope_sha256": "D",
    "slot_id": "P",
    "previous_ledger_sha256": "D?",
    "reason": enum(
        "N_EQUALS_C", "CAMPAIGN_ALREADY_COMPLETE", "INDEPENDENT_REVIEW_ALREADY_COMPLETE"
    ),
    "proof_inventory_sha256": "D",
    "branch_record_sha256": "D?",
    "recorded_utc": "Z",
}
CEILING_SCHEMA = {
    "schema_version": "=" + CEILING,
    **dict.fromkeys(limits.POSITIVE - {"command_id"}, "P"),
    "invocations": dict.fromkeys(limits.ROLES, "U"),
}
BEGIN_SCHEMA = {
    "schema_version": "=" + BEGIN,
    "envelope_sha256": "D",
    "slot_id": "P",
    "previous_ledger_sha256": "D",
    "slot_binding_sha256": "D",
    "configuration_sha256": "D",
    "authority_sha256": "D",
    "begun_utc": "Z",
}
FINISH_SCHEMA = {
    "schema_version": "=" + FINISH,
    "envelope_sha256": "D",
    "slot_id": "P",
    "previous_ledger_sha256": "D",
    "slot_binding_sha256": "D",
    "disposition": "=COMPLETED",
    "observed_bytes": "U",
    "observed_inodes": "U",
    "inventory_sha256": "D",
    "inventory_roots": [{"primitive": "absolute_path"}],
    "inventory_max_entries": "P",
    "generated_records": [{"path": {"primitive": "absolute_path"}, "sha256": "D"}],
    "completed_utc": "Z",
}
SCHEMAS = {
    MODEL: MODEL_SCHEMA,
    MEMBER: MEMBER_SCHEMA,
    BINDING: BINDING_SCHEMA,
    BRANCH: BRANCH_SCHEMA,
    SKIP: SKIP_SCHEMA,
    CEILING: CEILING_SCHEMA,
    BEGIN: BEGIN_SCHEMA,
    FINISH: FINISH_SCHEMA,
}
DESCRIPTOR_VALUE = {
    "version": DESCRIPTOR,
    "adopted_spec_sha256": ADOPTED_SPEC_SHA256,
    "parent_descriptor_sha256": rs.DESCRIPTOR_SHA256,
    "max_slots": MAX_SLOTS,
    "schemas": SCHEMAS,
    "prerequisite_kinds": list(PREREQUISITES),
    "command_scope_version": SCOPE,
    "command_paths_fields": ["output_path", "scratch_path"],
    "bootstrap_work_file_fields": ["path", "sha256"],
    "max_generated_record_paths": MAX_SLOTS,
    "max_generated_record_path_bytes": 4096,
    "configuration_scope_exclusions": [
        "runtime.authority_sha256",
        "runtime.resource_retention.slot_binding_sha256",
    ],
    "accounting": "Full union before first generated output; no skip, failure, cleanup, branch or later-slot refund; native and attributable capacity evidence remain separately mandatory.",
}
DESCRIPTOR_SHA256 = "76bb1ca77ee205fafddde1debf90d02b19d44c1dee4b4c68362162c3ec5fd9b7"
_descriptor_raw = (
    Path(__file__).resolve().parents[4]
    / "docs/scientific_assets"
    / (DESCRIPTOR + ".json")
).read_bytes()
b.require(
    b.sha(_descriptor_raw).hex() == DESCRIPTOR_SHA256
    and _descriptor_raw == b.canonical(DESCRIPTOR_VALUE),
    "B2_GRAPH_DESCRIPTOR_CHANGED",
)


def is_model(value):
    return type(value) is dict and value.get("schema_version") == MODEL


def shape(value, schema):
    if type(schema) is list:
        b.require(
            type(value) is list and len(value) <= MAX_SLOTS, "B2_GRAPH_LIST_BOUND"
        )
        for item in value:
            shape(item, schema[0])
    elif type(schema) is dict and not any(
        x in schema for x in ("enum", "const", "primitive", "tag")
    ):
        b.require(type(value) is dict and set(value) == set(schema), "B2_GRAPH_FIELDS")
        for name, child in schema.items():
            shape(value[name], child)
    else:
        b.validate_type(value, schema)


def parse(raw, expected=None):
    b.require(type(raw) is bytes and len(raw) <= b.MAX_METADATA, "B2_METADATA_LIMIT")
    value = io.metadata(raw)
    version = value.get("schema_version")
    b.require(
        version in SCHEMAS and (expected is None or expected == version),
        "B2_GRAPH_VERSION",
    )
    shape(value, SCHEMAS[version])
    if version == MODEL:
        validate_model(value)
    return value


def envelope_workload_hash(model):
    return b.digest(
        {
            "population_scope": model["population_scope"],
            "member_envelopes": model["member_envelopes"],
        }
    )


def validate_model(model):
    shape(model, MODEL_SCHEMA)
    b.require(
        model["parent_descriptor_sha256"] == rs.DESCRIPTOR_SHA256
        and model["successor_descriptor_sha256"] == DESCRIPTOR_SHA256
        and model["adopted_clauses_sha256"] == rs.ASSET["adopted_source_sha256"],
        "B2_GRAPH_ADOPTION",
    )
    b.require(model["valid_from"] < model["valid_until"], "B2_RS1_VALIDITY")
    members, slots, budget = model["member_envelopes"], model["slots"], model["limits"]
    b.require(
        0 < len(members) <= MAX_SLOTS
        and [x["member_id"] for x in members]
        == sorted({x["member_id"] for x in members})
        and sum(x["workload_kind"] == "DIRECT_N" for x in members) == 1,
        "B2_GRAPH_MEMBERS",
    )
    b.require(
        sum(x["workload_kind"] == "FULL_C" for x in members) == 1, "B2_GRAPH_FULL_C"
    )
    for member in members:
        selected = member["permitted_result_limits"]
        b.require(
            selected
            and selected == sorted(set(selected))
            and max(selected) <= 40
            and (
                member["workload_kind"] not in ("FULL_C", "DIRECT_N")
                or member["repetition"] == 0
            )
            and (member["workload_kind"] == "DIRECT_N" or len(selected) == 1),
            "B2_GRAPH_MEMBERS",
        )
        b.require(
            member["candidate_rows"] == rs.mul(member["data_works"], max(selected))
            and member["ledger_rows"]
            == rs.add(member["data_works"], member["control_works"]),
            "B2_GRAPH_MEMBER_BOUND",
        )
        for prefix in ("data", "control"):
            b.require(
                member[prefix + "_works"]
                <= member[prefix + "_attempts"]
                <= rs.mul(5, member[prefix + "_works"]),
                "B2_RS1_RETRY_BOUND",
            )
    b.require(
        model["workload_sha256"] == envelope_workload_hash(model)
        and all(budget[name] == rs.add(*(x[name] for x in members)) for name in COUNTS),
        "B2_GRAPH_WORKLOAD",
    )
    b.require(
        budget["max_response_bytes"] == 16 * 2**20
        and budget["max_candidates_per_work"]
        == max(max(x["permitted_result_limits"]) for x in members),
        "B2_RS1_RESPONSE_BOUND",
    )
    b.require(
        0 < len(slots) <= MAX_SLOTS
        and budget["commands"] == len(slots)
        and [x["slot_id"] for x in slots] == list(range(1, len(slots) + 1)),
        "B2_GRAPH_SLOTS",
    )
    b.require(
        rs.MANDATORY_COMMAND_PHASES <= {x["phase"] for x in slots},
        "B2_RS1_COMMAND_GRAPH",
    )
    b.require(
        sum(
            x["member_role"] == "SELECTED_FINAL"
            and x["phase"] == "publish"
            and x["condition"] == "REQUIRED"
            for x in slots
        )
        == 1
        and sum(
            x["member_role"] == "SELECTED_FINAL"
            and x["phase"] == "reopen"
            and x["condition"] == "REQUIRED"
            for x in slots
        )
        >= 2,
        "B2_GRAPH_FINAL_GRAPH",
    )
    direct_id = next(
        x["member_id"] for x in members if x["workload_kind"] == "DIRECT_N"
    )
    b.require(
        {
            "build-workload",
            "offline-preflight",
            "prepare-bootstrap",
            "preflight",
            "run-direct-n",
            "close-campaign",
        }
        <= {x["phase"] for x in slots if x["condition"] == "DIRECT_N_BRANCH"},
        "B2_GRAPH_DIRECT_GRAPH",
    )
    by_member = {x["member_id"]: x for x in members}
    for slot in slots:
        rs.mul(slot["max_duration_ms"], 1_000_000)
        role, condition, phase = (
            slot[x] for x in ("member_role", "condition", "phase")
        )
        b.require(
            slot["predecessor_slot_id"] == slot["slot_id"] - 1, "B2_GRAPH_PREDECESSOR"
        )
        if role == "FIXED_MEMBER":
            b.require(slot["member_id"] in by_member, "B2_GRAPH_MEMBER_ROLE")
            if slot["member_id"] == direct_id:
                b.require(
                    condition in ("DIRECT_N_BRANCH", "CONTINUATION_CAPACITY"),
                    "B2_GRAPH_DIRECT_GRAPH",
                )
        else:
            b.require(
                slot["member_id"] is None
                and (
                    phase in ("publish", "reopen")
                    if role == "SELECTED_FINAL"
                    else phase
                    in (
                        "build-catalog",
                        "plan-calibration",
                        "build-workload",
                        "offline-preflight",
                        "prepare-bootstrap",
                        "evaluate-calibration",
                        "close-window",
                    )
                ),
                "B2_GRAPH_MEMBER_ROLE",
            )
        if condition == "CONTINUATION_CAPACITY":
            b.require(
                role == "FIXED_MEMBER"
                and phase
                in ("prepare-bootstrap", "preflight", "run-campaign", "run-direct-n"),
                "B2_GRAPH_SKIP_PHASE",
            )
            b.require(
                any(
                    x["member_id"] == slot["member_id"]
                    and x["phase"] == phase
                    and x["condition"] in ("REQUIRED", "DIRECT_N_BRANCH")
                    for x in slots[: slot["slot_id"] - 1]
                ),
                "B2_GRAPH_FIRST_SEGMENT_REQUIRED",
            )
        if condition == "DIRECT_N_BRANCH":
            b.require(
                (
                    role == "FIXED_MEMBER"
                    and by_member[slot["member_id"]]["workload_kind"] == "DIRECT_N"
                    or role == "NONE"
                    and phase
                    in ("build-workload", "offline-preflight", "prepare-bootstrap")
                )
                and phase
                in (
                    "build-workload",
                    "offline-preflight",
                    "prepare-bootstrap",
                    "preflight",
                    "run-direct-n",
                    "close-campaign",
                ),
                "B2_GRAPH_SKIP_PHASE",
            )
        if condition == "OPTIONAL_INDEPENDENT_REOPEN":
            b.require(
                role == "SELECTED_FINAL"
                and phase == "reopen"
                and sum(
                    x["phase"] == "reopen"
                    and x["member_role"] == "SELECTED_FINAL"
                    and x["condition"] == "REQUIRED"
                    for x in slots[: slot["slot_id"] - 1]
                )
                >= 2,
                "B2_GRAPH_FIRST_REVIEW_REQUIRED",
            )
    ll = model["ledger_record_limits"]
    # Model, permanent owner, directory, mutation/ACTIVE uncertainty are charged
    # in addition to immutable member/binding/begin/terminal/branch records.
    expected = {
        "max_member_bindings": len(members),
        "max_slot_bindings": len(slots),
        "max_begins": len(slots),
        "max_terminals": len(slots),
        "max_branch_records": 1,
    }
    b.require(
        all(ll[k] == n for k, n in expected.items())
        and ll["max_entries"] >= rs.add(6, *expected.values())
        and ll["max_record_bytes"] <= b.MAX_METADATA
        and ll["max_prerequisite_rows"] <= MAX_SLOTS
        and ll["max_prerequisite_bytes"] <= ll["max_record_bytes"]
        and ll["max_total_bytes"] >= rs.mul(ll["max_entries"], ll["max_record_bytes"]),
        "B2_GRAPH_LEDGER_BOUND",
    )
    b.require(
        len(b.canonical(model)) <= ll["max_record_bytes"], "B2_GRAPH_LEDGER_BOUND"
    )
    components = model["components"]
    b.require(
        [x["component_id"] for x in components] == sorted(rs.COUNTS),
        "B2_RS1_CATEGORY_COVERAGE",
    )
    by_id = {x["component_id"]: x for x in components}
    totals = [0, 0, 0]
    for component in components:
        name = component["component_id"]
        count = (
            ll["max_entries"]
            if name == "ACCOUNTING_LEDGER"
            else budget[rs.COUNTS[name]]
        )
        b.require(
            component["count_bound"] == count
            and component["retained_after_phase"] is True
            and component["max_simultaneous_instances"] == count,
            "B2_RS1_COUNT_DERIVATION",
        )
        predicate = (
            "TERMINAL_BODY_ONCE"
            if name in ("DATA_RAW", "CONTROL_RAW")
            else "EVERY_ATTEMPT"
            if name
            in (
                "DATA_ATTEMPT_METADATA",
                "CONTROL_ATTEMPT_METADATA",
                "CONTROL_VERIFICATION",
            )
            else "TRANSIENT_NO_RECLAIM"
            if name
            in (
                "SQLITE_JOURNAL",
                "DUCKDB_SPILL",
                "PARTIAL_WRITES",
                "CLOSURE_UNCERTAINTY",
            )
            else "DERIVED_RETAINED"
        )
        b.require(component["state_predicate"] == predicate, "B2_RS1_STATE_PREDICATE")
        if name == "ACCOUNTING_LEDGER":
            b.require(
                component["per_instance_bytes_bound"] >= ll["max_record_bytes"]
                and component["per_instance_inodes_bound"] >= 1,
                "B2_GRAPH_LEDGER_BOUND",
            )
        totals = [
            rs.add(a, z)
            for a, z in zip(totals, rs.component_bytes(component, model), strict=True)
        ]
        b.require(
            rs.add(*(x["allocations"][name] for x in slots)) == count,
            "B2_RS1_COMMAND_COVERAGE",
        )
    b.require(
        tuple(totals)
        == (
            model["physical_peak_bound_bytes"],
            model["physical_inode_bound"],
            model["retained_payload_bound_bytes"],
        )
        and totals[0] <= model["capacity_bytes"]
        and totals[1] <= model["capacity_inodes"],
        "B2_RS1_TOTAL_MISMATCH",
    )
    for slot in slots:
        amounts = [
            rs.component_bytes({**by_id[k], "count_bound": n}, model)
            for k, n in slot["allocations"].items()
        ]
        b.require(
            slot["max_generated_bytes"] == rs.add(*(x[0] for x in amounts))
            and slot["max_generated_inodes"] == rs.add(*(x[1] for x in amounts)),
            "B2_RS1_COMMAND_DERIVATION",
        )
    return {
        "physical_bytes": totals[0],
        "inodes": totals[1],
        "payload_bytes": totals[2],
    }


def validate_plan_model(model, plan):
    validate_model(model)
    actual = rs.member_workload(plan)
    matches = [
        x
        for x in model["member_envelopes"]
        if x["workload_kind"] == plan["workload_kind"]
        and x["repetition"] == plan["repetition"]
        and plan["result_limit"] in x["permitted_result_limits"]
        and all(actual[name] <= x[name] for name in COUNTS)
    ]
    b.require(
        plan["population_scope"] == model["population_scope"]
        and plan["resource_retention_model_sha256"] == b.digest(model)
        and plan["resource_workload_sha256"] == actual["plan_binding_sha256"]
        and len(matches) == 1,
        "B2_GRAPH_PLAN_BINDING",
    )
    return matches[0]


def configuration_scope_record(config):
    """Only the two adopted exclusions; every other byte remains in scope."""
    value = deepcopy(config)
    value["runtime"].pop("authority_sha256", None)
    value["runtime"]["resource_retention"].pop("slot_binding_sha256", None)
    return value


def configuration_scope(config):
    return b.digest(configuration_scope_record(config))


def command_scope(config, *, plan_binding=None):
    """Preserved RS1 projection plus the actual successor command paths.

    Bootstrap has an actual plan before an admission exists. Its real plan and
    WorkFile stay explicit here instead of fabricating a future campaign.
    """
    paths = config.get("command_paths")
    shape(
        paths,
        {
            "output_path": {"primitive": "absolute_path"},
            "scratch_path": {"primitive": "absolute_path"},
        },
    )
    rs.inventory_roots([paths["output_path"], paths["scratch_path"]])
    bootstrap = None
    campaign = config["runtime"]["campaign"]
    if plan_binding is not None and campaign is None:
        b.validate_type(plan_binding, "D")
        b.require(
            config["runtime"]["phase"] == "prepare-bootstrap"
            and type(config.get("bootstrap")) is dict,
            "B2_GRAPH_BOOTSTRAP_MEMBER",
        )
        shape(
            config.get("bootstrap_work_file"),
            {"path": {"primitive": "absolute_path"}, "sha256": "D"},
        )
        rs.inventory_roots([config["bootstrap_work_file"]["path"]])
        bootstrap = {
            "plan_binding_sha256": plan_binding,
            "bootstrap": config["bootstrap"],
            "work_file": config["bootstrap_work_file"],
        }
    return b.digest(
        {
            "schema_version": SCOPE,
            "rs1_scope": rs.command_scope_record(
                config, plan_binding=plan_binding if campaign is not None else None
            ),
            "command_paths": paths,
            "bootstrap_member": bootstrap,
        }
    )


def authority_check(model, records, authority, *, now, source_hash, runtime_hash):
    validate_model(model)
    b.require(model["valid_from"] <= now < model["valid_until"], "B2_RS1_EXPIRED")
    b.require(
        (model["source_inventory_sha256"], model["runtime_inventory_sha256"])
        == (source_hash, runtime_hash),
        "B2_RS1_SOURCE_BINDING",
    )
    for field in (
        "adoption_sha256",
        "review_sha256",
        "retry_state_proof_sha256",
        "capacity_record_sha256",
        "capacity_owner_authority_sha256",
        "filesystem_accounting_sha256",
        "codec_inventory_sha256",
        "encoding_inventory_sha256",
    ):
        records.raw(model[field])
        authority.require(
            "resource_retention_" + field.removesuffix("_sha256"), model[field], model
        )
    for component in model["components"]:
        records.raw(component["evidence_sha256"])
        authority.require(
            "resource_retention_bound", component["evidence_sha256"], component
        )
    for slot in model["slots"]:
        ceiling = parse(records.raw(slot["allocation_limit_ceiling_sha256"]), CEILING)
        authority.require(
            "resource_retention_allocation_ceiling", b.digest(ceiling), ceiling
        )
    authority.require("resource_retention", b.digest(model), model)


def validate_ceiling(value, ceiling, model, slot):
    shape(ceiling, CEILING_SCHEMA)
    b.require(
        b.digest(ceiling) == slot["allocation_limit_ceiling_sha256"], "B2_GRAPH_CEILING"
    )
    command = {
        **slot,
        "command_id": slot["slot_id"],
        "bound_evidence_sha256": value["native_bound_evidence_sha256"],
    }
    limits.validate_binding(value, model, command)
    b.require(
        all(value[k] <= ceiling[k] for k in limits.POSITIVE - {"command_id"})
        and all(
            value["invocations"][k] <= ceiling["invocations"][k] for k in limits.ROLES
        ),
        "B2_GRAPH_CEILING",
    )
    return command


class ScientificOriginals:
    """Sources, never validation tokens, for the unchanged scientific validators.

    Factories reopen actual sources and own their bounded, charged scratch.
    ``member_source`` returns profile/plan/WorkFile/catalog/selection/admission;
    ``calibration_source`` returns catalog/selection/complete observations.
    Their outputs are validated here, rather than accepting a Boolean receipt.
    """

    def __init__(
        self,
        records,
        authority,
        *,
        member_source,
        calibration_source,
        campaign_source,
        publication_source,
        check,
    ):
        self.records, self.authority = records, authority
        self.member_source, self.calibration_source = member_source, calibration_source
        self.campaign_source, self.publication_source = (
            campaign_source,
            publication_source,
        )
        self.check = check

    def _protected_guard(self, model):
        self.check()
        if model["population_scope"] == b.DEVELOPMENT:
            from ...execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm(
                "stage12 acceptance graph original scientific validation"
            )

    def member(self, row, model):
        from . import s12_b2_operations as operations
        from . import s12_b2_planning as planning
        from . import s12_b2_runtime as runtime
        from . import s12_b2_catalog as catalogs

        self._protected_guard(model)
        source = self.member_source(row)
        profile, plan, work, catalog, selection, admission = source
        b.require(
            isinstance(work, runtime.WorkFile)
            and isinstance(catalog, catalogs.Catalog),
            "B2_GRAPH_ORIGINAL_READER",
        )
        b.require(
            self.records.raw(row["exact_plan_sha256"]) == b.canonical(plan),
            "B2_GRAPH_ORIGINAL_PLAN",
        )
        operations.validate_plan(plan, profile)
        member = validate_plan_model(model, plan)
        b.require(
            member["member_id"] == row["member_id"]
            and rs.workload_binding(plan) == row["plan_binding_sha256"]
            and plan["window_plan_sha256"] == row["window_plan_sha256"]
            and work.expected == row["work_file_sha256"],
            "B2_GRAPH_MEMBER_BINDING",
        )
        work.verify()
        catalog.verify()
        if admission is None:
            planning.verify_member_workload(
                self.records,
                row["calibration_selection_sha256"],
                selection,
                catalog,
                plan,
                work.rows,
                authority=self.authority,
            )
        else:
            planning.verify_workload(
                self.records,
                row["calibration_selection_sha256"],
                selection,
                catalog,
                plan,
                work.rows,
                admission,
                authority=self.authority,
            )
        b.require(
            (plan["workload_kind"] == "DIRECT_N")
            == (row["N_decision_sha256"] is not None)
            and (
                row["N_decision_sha256"] is None
                or plan["selection_basis_sha256"] == row["N_decision_sha256"]
            ),
            "B2_GRAPH_MEMBER_BINDING",
        )
        self.check()
        return plan

    def branch(self, row, model):
        from . import s12_b2_calibration as calibration

        self._protected_guard(model)
        catalog, selection, observations = self.calibration_source(row)
        result = calibration.evaluate(
            catalog,
            selection,
            observations,
            window_hash=row["window_plan_sha256"],
            selection_hash=row["calibration_selection_sha256"],
            authority=self.authority,
            comparison_writer=lambda value: self.check(),
        )
        decision = self.records.get(row["N_decision_sha256"], "n_decision")
        inventory = json.loads(self.records.raw(row["calibration_inventory_sha256"]))
        b.require(
            type(inventory) is list and len(inventory) == len(observations),
            "B2_CALIBRATION_INVENTORY",
        )
        window = self.records.get(row["window_plan_sha256"], "window_plan")
        bound = self.records.get(
            row["calibration_selection_sha256"], "calibration_selection"
        )
        self.authority.require("N_selection", row["N_decision_sha256"], decision)
        b.require(
            result["disposition"] == "ELIGIBLE_FOR_OWNER_REVIEW"
            and result["population_scope"] == model["population_scope"]
            and b.digest(result)
            == row["adequacy_report_sha256"]
            == decision["adequacy_report_sha256"]
            and result["calibration_inventory_sha256"]
            == row["calibration_inventory_sha256"]
            == decision["calibration_inventory_sha256"]
            and result["selection_sha256"] == row["calibration_selection_sha256"]
            and decision["decision"] == "SELECTED"
            and decision["window_plan_sha256"]
            == bound["window_plan_sha256"]
            == row["window_plan_sha256"]
            and window["dispatch_from"]
            <= decision["decided_utc"]
            < window["dispatch_until"]
            and decision["decided_utc"]
            <= row["recorded_utc"]
            < window["dispatch_until"]
            and row["N"] == decision["result_limit"]
            and row["N"] in result["eligible_limits"]
            and row["N"] in bound["grid"]
            and row["C"] == bound["C"]
            and (row["branch"] == "REUSE_FULL_C") == (row["N"] == row["C"]),
            "B2_GRAPH_N_BRANCH",
        )
        from . import s12_retrieval_contract as contract

        b.require(
            decision["retrieval_policy_id"]
            == contract.policy(row["N"])["retrieval_policy_id"].hex(),
            "B2_GRAPH_N_BRANCH",
        )
        return result

    def prerequisite(self, kind, digest, *, config, member, branch):
        raw = self.records.raw(digest)
        names = {
            "CALIBRATION_SELECTION": "calibration_selection",
            "CALIBRATION_RESULT": "calibration_result",
            "N_DECISION": "n_decision",
            "WINDOW_PLAN": "window_plan",
            "SEGMENT_CLOSURE": "segment_closure",
            "CAMPAIGN_CLOSURE": "campaign_closure",
            "WINDOW_CLOSURE": "window_closure",
        }
        if kind in names:
            value = self.records.get(digest, names[kind])
        else:
            value = io.metadata(raw)
        self.authority.require(
            "resource_graph_prerequisite_" + kind.lower(), digest, value
        )
        if member is not None and kind in ("WINDOW_PLAN", "CALIBRATION_SELECTION"):
            field = (
                "window_plan_sha256"
                if kind == "WINDOW_PLAN"
                else "calibration_selection_sha256"
            )
            b.require(member[field] == digest, "B2_GRAPH_PREREQUISITE_BINDING")
        if branch is not None and kind in ("N_DECISION", "CALIBRATION_RESULT"):
            b.require(
                digest
                == branch[
                    "N_decision_sha256"
                    if kind == "N_DECISION"
                    else "adequacy_report_sha256"
                ],
                "B2_GRAPH_PREREQUISITE_BINDING",
            )
        if branch is not None and kind in ("WINDOW_PLAN", "CALIBRATION_SELECTION"):
            b.require(
                digest
                == branch[
                    "window_plan_sha256"
                    if kind == "WINDOW_PLAN"
                    else "calibration_selection_sha256"
                ],
                "B2_GRAPH_PREREQUISITE_BINDING",
            )
        if kind == "WINDOW_CLOSURE":
            b.require(
                branch is not None
                and value["window_plan_sha256"] == branch["window_plan_sha256"],
                "B2_GRAPH_PREREQUISITE_BINDING",
            )
        if member is not None and kind == "CAMPAIGN_CLOSURE":
            b.require(
                value["workload_sha256"] == member["exact_plan_sha256"]
                and value["window_plan_sha256"] == member["window_plan_sha256"]
                and value["disposition"] == "CLOSED_OBSERVATIONAL",
                "B2_GRAPH_PREREQUISITE_BINDING",
            )
        if kind == "N_DECISION":
            b.require(
                branch is not None
                and value["decision"] == "SELECTED"
                and value["result_limit"] == branch["N"],
                "B2_GRAPH_PREREQUISITE_BINDING",
            )
        return value

    def skip(self, row, slot, member, branch, proofs):
        self.check()
        model = io.metadata(self.records.raw(row["envelope_sha256"]))
        self._protected_guard(model)
        if row["reason"] == "N_EQUALS_C":
            b.require(
                slot["condition"] == "DIRECT_N_BRANCH"
                and branch is not None
                and branch["branch"] == "REUSE_FULL_C"
                and row["branch_record_sha256"] == b.digest(branch)
                and proofs
                == [
                    {"record_kind": "N_DECISION", "sha256": branch["N_decision_sha256"]}
                ],
                "B2_GRAPH_SKIP_PROOF",
            )
            return
        if row["reason"] == "CAMPAIGN_ALREADY_COMPLETE":
            from . import s12_b2_phase_io as phase_io

            b.require(
                slot["condition"] == "CONTINUATION_CAPACITY" and member is not None,
                "B2_GRAPH_SKIP_PROOF",
            )
            reader = self.campaign_source(member)
            b.require(
                isinstance(
                    reader, (phase_io.CampaignReader, CompletedCampaignOriginal)
                ),
                "B2_GRAPH_ORIGINAL_READER",
            )
            b.require(
                reader.plan["population_scope"] == model["population_scope"],
                "B2_POPULATION_SCOPE",
            )
            result = reader.validate()
            snapshot = result["snapshot"]
            b.require(
                snapshot["disposition"] == "COMPLETED"
                and b.digest(reader.plan) == member["exact_plan_sha256"]
                and any(
                    x["record_kind"] == "SEGMENT_CLOSURE"
                    and x["sha256"] == snapshot["segment_closure_sha256"]
                    for x in proofs
                ),
                "B2_GRAPH_SKIP_PROOF",
            )
            return
        b.require(
            row["reason"] == "INDEPENDENT_REVIEW_ALREADY_COMPLETE"
            and slot["condition"] == "OPTIONAL_INDEPENDENT_REOPEN"
            and branch is not None
            and member is not None,
            "B2_GRAPH_SKIP_PROOF",
        )
        reviews = [x for x in proofs if x["record_kind"] == "REVIEW_COMPLETION"]
        b.require(len(reviews) == 1, "B2_GRAPH_SKIP_PROOF")
        review = io.metadata(self.records.raw(reviews[0]["sha256"]))
        shape(
            review,
            {
                "schema_version": "=stage12_resource_independent_review_b2_rs1_acceptance_v1",
                "population_scope": enum(b.DEVELOPMENT, b.SYNTHETIC),
                "envelope_sha256": "D",
                "member_binding_sha256": "D",
                "publication_manifest_sha256": "D",
                "N_decision_sha256": "D",
                "independent_authority_sha256": "D",
                "result": "=COMPLETE_NO_UNRESOLVED_DEFECTS",
                "completed_utc": "Z",
            },
        )
        b.require(
            review["envelope_sha256"] == row["envelope_sha256"]
            and review["population_scope"] == model["population_scope"]
            and review["member_binding_sha256"] == b.digest(member)
            and review["N_decision_sha256"] == branch["N_decision_sha256"]
            and review["completed_utc"] <= row["recorded_utc"],
            "B2_GRAPH_SKIP_PROOF",
        )
        self.records.raw(review["independent_authority_sha256"])
        self.authority.require(
            "resource_graph_independent_review", reviews[0]["sha256"], review
        )
        reader = self.publication_source(review)
        from . import s12_b2_publication as publication

        b.require(
            isinstance(reader, publication.ArtifactReader)
            and reader.expected_hash.hex() == review["publication_manifest_sha256"],
            "B2_GRAPH_ORIGINAL_READER",
        )
        reader.validate()
        retained = reader.manifest
        bindings = retained["publication_bindings"]
        b.require(
            retained["kind"].removeprefix(b.SYNTHETIC + "_") == publication.FINAL
            and retained["population_scope"] == review["population_scope"]
            and bindings["owner_freeze_sha256"] == branch["N_decision_sha256"]
            and bindings["calibration_evidence_inventory_sha256"]
            == branch["calibration_inventory_sha256"]
            and bindings["workload_sha256"] == member["exact_plan_sha256"]
            and bindings["window_plan_sha256"] == branch["window_plan_sha256"]
            and bindings["window_closure_sha256"] is not None,
            "B2_GRAPH_FINAL_BASIS",
        )


class CompletedCampaignOriginal:
    """Full original segment/receipt totality without a future campaign closure.

    This reader proves only that unused continuation slots are inapplicable.
    The mandatory later campaign-closure command remains required. Scratch and
    validation invocations have explicit positive selected limits and use the
    existing allocation counters when installed.
    """

    def __init__(
        self,
        segment,
        *,
        population_scope,
        catalog,
        rules,
        gate,
        control_adapters,
        scratch_factory,
        max_validations,
        check,
    ):
        b.require(
            population_scope in (b.SYNTHETIC, b.DEVELOPMENT), "B2_POPULATION_SCOPE"
        )
        if population_scope == b.DEVELOPMENT:
            from ...execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm("stage12 acceptance continuation original reader")
        from . import s12_b2_operations as operations

        self.segment, self.catalog, self.rules, self.gate = (
            Path(segment),
            catalog,
            rules,
            gate,
        )
        self.control_adapters, self.scratch_factory, self.check = (
            control_adapters,
            scratch_factory,
            check,
        )
        self.maximum, self.calls = b.uint(max_validations, True), 0
        self.start = operations.parse_selected(
            io.read(self.segment / "campaign_start.json")
        )
        self.plan = operations.parse_selected(io.read(self.segment / "plan.json"))
        self.profile = operations.parse_selected(io.read(self.segment / "profile.json"))
        self.original = tuple(
            b.sha(io.read(self.segment / name)).hex()
            for name in ("campaign_start.json", "plan.json", "profile.json")
        )
        b.require(
            self.plan["population_scope"] == population_scope, "B2_POPULATION_SCOPE"
        )

    def works(self):
        from . import s12_b2_inventory as inventory

        return inventory.read_role(
            self.segment, "work.json", self.plan, check=self.check
        )

    def locate(self, work_id, ordinal):
        from . import s12_b2_inventory as inventory

        found = None
        for node in inventory.lineage(
            self.segment, self.plan["budgets"]["administrative_operations"]
        ):
            self.check()
            unit = node / "attempts" / f"{work_id:020d}_{ordinal:02d}"
            if unit.exists():
                b.require(found is None, "B2_DUPLICATE_RECEIPT")
                found = unit
        b.require(found is not None, "B2_RECEIPT_MISSING")
        return found

    def receipt(self, work, event):
        from . import s12_b2_phase_io as phase_io

        return phase_io.CampaignReader.receipt(self, work, event)

    def validate(self):
        from . import s12_b2_recovery as recovery

        self.check()
        b.require(self.calls < self.maximum, "B2_GRAPH_REOPEN_BUDGET")
        self.calls += 1
        self.catalog.verify()
        b.require(
            tuple(
                b.sha(io.read(self.segment / name)).hex()
                for name in ("campaign_start.json", "plan.json", "profile.json")
            )
            == self.original,
            "B2_GRAPH_ORIGINAL_PLAN",
        )
        result = recovery.reopen(
            self.segment,
            self.start,
            self.profile,
            self.plan,
            works=self.works,
            verify_receipt=self.receipt,
            scratch=Path(self.scratch_factory()),
            authority=self.gate,
        )
        b.require(
            result["snapshot"]["disposition"] == "COMPLETED"
            and all(row["state"] == "DURABLE_SUCCESS" for row in result["ledger"]()),
            "B2_CAMPAIGN_INCOMPLETE",
        )
        self.catalog.verify()
        return result


def required_prerequisites(slot, branch):
    phase = slot["phase"]
    required = {"LOCAL_AUTHORITY"}
    if slot["member_role"] != "NONE":
        required |= {"WINDOW_PLAN", "CALIBRATION_SELECTION"}
    if phase == "close-campaign":
        required.add("SEGMENT_CLOSURE")
    if phase in ("publish", "reopen"):
        required.add("CAMPAIGN_CLOSURE")
    if phase == "reopen":
        required.add("PUBLICATION_MANIFEST")
    if phase == "evaluate-calibration":
        required |= {
            "WINDOW_PLAN",
            "CALIBRATION_SELECTION",
            "CAMPAIGN_CLOSURE",
            "PUBLICATION_MANIFEST",
        }
    if phase == "close-window":
        required |= {
            "WINDOW_PLAN",
            "CALIBRATION_SELECTION",
            "N_DECISION",
            "CALIBRATION_RESULT",
            "CAMPAIGN_CLOSURE",
        }
    if slot["member_role"] == "SELECTED_FINAL":
        required |= {"N_DECISION", "CALIBRATION_RESULT", "WINDOW_CLOSURE"}
    if branch is not None and slot["condition"] == "DIRECT_N_BRANCH":
        required |= {
            "N_DECISION",
            "CALIBRATION_RESULT",
            "WINDOW_PLAN",
            "CALIBRATION_SELECTION",
        }
    return required


class AcceptanceLedger:
    """One closed graph, exclusive mutation/active claims, no reset or salvage.

    Every API starts with a fresh directory, chain, evidence and output reopen.
    An uncertain write leaves MUTATING/ACTIVE and blocks all later instances.
    """

    def __init__(
        self,
        root,
        model,
        *,
        records,
        authority,
        originals,
        check,
        now,
        expected_head=None,
    ):
        validate_model(model)
        self.root, self.model = Path(root), model
        self.records, self.authority, self.originals = records, authority, originals
        b.require(
            isinstance(originals, ScientificOriginals)
            or model["population_scope"] == b.SYNTHETIC,
            "B2_GRAPH_ORIGINAL_READER",
        )
        self.check, self.now = check, now
        self.model_hash, self.finished, self.poisoned = b.digest(model), False, False
        self.command = self.begin_record = None
        self.generated_records = {}
        self.expected_head = expected_head
        io.private_directory(self.root.parent)
        if self.root.exists():
            b.validate_type(expected_head, "D")
        if not self.root.exists():
            self._root_check()
            io.reserve(self.root)
            io.write(
                self.root / "MUTATING.json",
                b.canonical({"envelope_sha256": self.model_hash}),
            )
            io.write(self.root / "model.json", b.canonical(model))
            io.write(
                self.root / "OWNER.json",
                b.canonical(
                    {
                        "envelope_sha256": self.model_hash,
                        "owner_sha256": model["capacity_owner_authority_sha256"],
                    }
                ),
            )
            self._release_mutation()
        self.reopen()

    def _root_check(self):
        b.require(not self.poisoned, "B2_GRAPH_BLOCKED")
        self.check()
        authority_check(
            self.model,
            self.records,
            self.authority,
            now=self.now(),
            source_hash=self.model["source_inventory_sha256"],
            runtime_hash=self.model["runtime_inventory_sha256"],
        )
        b.require(
            self.records.raw(self.model_hash) == b.canonical(self.model),
            "B2_RS1_MODEL_CHANGED",
        )

    def _sync(self):
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _release_mutation(self):
        claim = self.root / "MUTATING.json"
        raw = io.read(claim)
        claim.unlink()
        try:
            self._sync()
        except BaseException:
            # Do not turn a failed durability boundary into a reusable root.
            if not claim.exists():
                io.write(claim, raw)
            self.poisoned = True
            raise

    def _inventory(self, digest):
        raw = self.records.raw(digest)
        ll = self.model["ledger_record_limits"]
        b.require(
            len(raw) <= ll["max_prerequisite_bytes"], "B2_GRAPH_PREREQUISITE_BOUND"
        )
        value = json.loads(raw)
        b.require(
            type(value) is list
            and 0 < len(value) <= ll["max_prerequisite_rows"]
            and raw == b.canonical(value),
            "B2_GRAPH_PREREQUISITE_BOUND",
        )
        for row in value:
            shape(row, {"record_kind": enum(*PREREQUISITES), "sha256": "D"})
            self.records.raw(row["sha256"])
        b.require(
            value == sorted(value, key=lambda x: (x["record_kind"], x["sha256"]))
            and len({(x["record_kind"], x["sha256"]) for x in value}) == len(value),
            "B2_GRAPH_PREREQUISITE_BOUND",
        )
        return value

    def _member_for(self, slot, members, branch):
        if slot["member_role"] == "NONE":
            return None
        if slot["member_role"] == "FIXED_MEMBER":
            return members.get(slot["member_id"])
        b.require(branch is not None, "B2_GRAPH_N_UNSELECTED")
        kind = "FULL_C" if branch["branch"] == "REUSE_FULL_C" else "DIRECT_N"
        candidates = [
            x
            for x in members.values()
            if self.model["member_envelopes"][
                [m["member_id"] for m in self.model["member_envelopes"]].index(
                    x["member_id"]
                )
            ]["workload_kind"]
            == kind
        ]
        b.require(len(candidates) == 1, "B2_GRAPH_FINAL_BASIS")
        return candidates[0]

    def _branch_members(self, row, members):
        expected = {
            x["member_id"]
            for x in self.model["member_envelopes"]
            if x["workload_kind"] != "DIRECT_N"
        }
        b.require(set(members) == expected, "B2_GRAPH_CALIBRATION_MEMBERS")
        raw = self.records.raw(row["calibration_inventory_sha256"])
        inventory = json.loads(raw)
        b.require(
            type(inventory) is list
            and len(inventory) == len(expected)
            and raw == b.canonical(inventory),
            "B2_CALIBRATION_INVENTORY",
        )
        for entry in inventory:
            shape(
                entry,
                {
                    "workload_kind": enum("FULL_C", "TAIL", "PAIRED"),
                    "publication_sha256": "D",
                    "campaign_closure_sha256": "D",
                    "window_plan_sha256": "D",
                    "workload_sha256": "D",
                },
            )
            b.require(
                entry["window_plan_sha256"] == row["window_plan_sha256"],
                "B2_GRAPH_WINDOW_CHANGED",
            )
        b.require(
            {x["workload_sha256"] for x in inventory}
            == {x["exact_plan_sha256"] for x in members.values()},
            "B2_GRAPH_CALIBRATION_MEMBERS",
        )

    def _validate_binding(self, row, slot, members, branch, config=None):
        member = self._member_for(slot, members, branch)
        b.require(
            row["member_binding_sha256"]
            == (None if member is None else b.digest(member)),
            "B2_GRAPH_SLOT_MEMBER",
        )
        projection = io.metadata(self.records.raw(row["configuration_scope_sha256"]))
        if config is not None:
            b.require(
                configuration_scope(config) == row["configuration_scope_sha256"],
                "B2_GRAPH_CONFIGURATION_SCOPE",
            )
        cfg = projection if config is None else config
        runtime = cfg["runtime"]
        pointer = runtime["resource_retention"]
        b.require(
            pointer["model_sha256"] == self.model_hash
            and pointer["command_id"] == slot["slot_id"]
            and pointer["allocation_limits_sha256"] == row["allocation_limits_sha256"]
            and runtime["phase"] == slot["phase"]
            and b.digest(runtime["source_files"])
            == row["source_inventory_sha256"]
            == self.model["source_inventory_sha256"]
            and row["runtime_inventory_sha256"]
            == self.model["runtime_inventory_sha256"],
            "B2_GRAPH_SLOT_SCOPE",
        )
        if runtime["source_files"] or self.model["population_scope"] != b.SYNTHETIC:
            from . import s12_b2_runtime as runtime_module

            runtime_module.RuntimePort._source_check(
                SimpleNamespace(settings=runtime, check_deadline=self.check)
            )
        b.require(
            row["command_scope_sha256"]
            == command_scope(
                cfg,
                plan_binding=None if member is None else member["plan_binding_sha256"],
            ),
            "B2_GRAPH_COMMAND_SCOPE",
        )
        if member is not None:
            campaign = runtime["campaign"]
            if campaign is not None:
                b.require(
                    campaign["plan_sha256"] == member["exact_plan_sha256"]
                    and campaign["work_file_sha256"] == member["work_file_sha256"],
                    "B2_GRAPH_WORKFILE_SCOPE",
                )
            else:
                b.require(
                    slot["phase"] == "prepare-bootstrap"
                    and cfg["bootstrap"]["plan_sha256"] == member["exact_plan_sha256"]
                    and cfg["bootstrap_work_file"]["sha256"]
                    == member["work_file_sha256"],
                    "B2_GRAPH_WORKFILE_SCOPE",
                )
        value = limits.parse(self.records.raw(row["allocation_limits_sha256"]))
        ceiling = parse(
            self.records.raw(slot["allocation_limit_ceiling_sha256"]), CEILING
        )
        command = validate_ceiling(value, ceiling, self.model, slot)
        for field in ("review_sha256", "native_bound_evidence_sha256"):
            self.records.raw(value[field])
        self.authority.require(
            "resource_retention_native_bound",
            value["native_bound_evidence_sha256"],
            value,
        )
        self.authority.require(
            "resource_retention_allocation_limits",
            row["allocation_limits_sha256"],
            value,
        )
        proofs = self._inventory(row["prerequisite_inventory_sha256"])
        b.require(
            {x["record_kind"] for x in proofs} == required_prerequisites(slot, branch),
            "B2_GRAPH_PREREQUISITE_APPLICABILITY",
        )
        for kind in required_prerequisites(slot, branch) - {
            "CAMPAIGN_CLOSURE",
            "PUBLICATION_MANIFEST",
            "SEGMENT_CLOSURE",
        }:
            b.require(
                sum(x["record_kind"] == kind for x in proofs) == 1,
                "B2_GRAPH_PREREQUISITE_APPLICABILITY",
            )
        if slot["phase"] in ("evaluate-calibration", "close-window"):
            relevant = {
                x["member_id"]
                for x in self.model["member_envelopes"]
                if x["workload_kind"] != "DIRECT_N"
                or slot["phase"] == "close-window"
                and branch is not None
                and branch["branch"] == "DIRECT_N"
            }
            b.require(relevant <= set(members), "B2_GRAPH_CALIBRATION_MEMBERS")
            expected_plans = {members[key]["exact_plan_sha256"] for key in relevant}
            closures = [
                self.records.get(x["sha256"], "campaign_closure")
                for x in proofs
                if x["record_kind"] == "CAMPAIGN_CLOSURE"
            ]
            b.require(
                len(closures) == len(expected_plans)
                and {x["workload_sha256"] for x in closures} == expected_plans,
                "B2_GRAPH_CAMPAIGN_TOTALITY",
            )
            if slot["phase"] == "evaluate-calibration":
                publications = [
                    io.metadata(self.records.raw(x["sha256"]))
                    for x in proofs
                    if x["record_kind"] == "PUBLICATION_MANIFEST"
                ]
                b.require(
                    len(publications) == len(expected_plans)
                    and {
                        x["publication_bindings"]["workload_sha256"]
                        for x in publications
                    }
                    == expected_plans,
                    "B2_GRAPH_CALIBRATION_MEMBERS",
                )
            else:
                b.require(branch is not None, "B2_GRAPH_N_UNSELECTED")
        if slot["member_role"] == "SELECTED_FINAL":
            b.require(branch is not None, "B2_GRAPH_N_UNSELECTED")
            calibration = json.loads(
                self.records.raw(branch["calibration_inventory_sha256"])
            )
            selected_closures = [
                x["sha256"] for x in proofs if x["record_kind"] == "CAMPAIGN_CLOSURE"
            ]
            windows = [
                self.records.get(x["sha256"], "window_closure")
                for x in proofs
                if x["record_kind"] == "WINDOW_CLOSURE"
            ]
            expected_closures = {
                x["campaign_closure_sha256"] for x in calibration
            } | set(selected_closures)
            b.require(
                len(selected_closures) == len(windows) == 1
                and set(windows[0]["ordered_campaign_closure_hashes"])
                == expected_closures,
                "B2_GRAPH_WINDOW_TOTALITY",
            )
            if branch["branch"] == "REUSE_FULL_C":
                full = [x for x in calibration if x["workload_kind"] == "FULL_C"]
                b.require(
                    len(full) == 1
                    and full[0]["workload_sha256"] == member["exact_plan_sha256"]
                    and full[0]["campaign_closure_sha256"] == selected_closures[0],
                    "B2_GRAPH_FINAL_BASIS",
                )
        for proof in proofs:
            self.originals.prerequisite(
                proof["record_kind"],
                proof["sha256"],
                config=cfg,
                member=member,
                branch=branch,
            )
        self.authority.require("resource_graph_binding", b.digest(row), row)
        if (
            slot["member_role"] == "SELECTED_FINAL"
            and slot["phase"] == "reopen"
            and sum(
                x["member_role"] == "SELECTED_FINAL"
                and x["phase"] == "reopen"
                and x["condition"] == "REQUIRED"
                for x in self.model["slots"][: slot["slot_id"]]
            )
            >= 2
        ):
            self.authority.require(
                "resource_graph_independent_opener",
                row["configuration_scope_sha256"],
                row,
            )
        return command, value

    def reopen(self, *, allow_active=False):
        self._root_check()
        io.private_directory(self.root)
        before = self.root.stat()
        # One finite commitment, not a raw-record cache. Semantic callbacks may
        # read many other originals; directory timestamps alone cannot detect
        # an in-place change to an earlier ledger record during those callbacks.
        source = hashlib.sha256()

        def original(name, limit):
            self.check()
            path = self.root / name
            first = _ledger_file_identity(path.stat(follow_symlinks=False))
            raw = io.read(path, limit=limit)
            b.require(
                first == _ledger_file_identity(path.stat(follow_symlinks=False)),
                "B2_GRAPH_LEDGER_CHANGED",
            )
            return raw, b.canonical([name, first, b.sha(raw).hex()])

        def bound_original(name, limit):
            raw, binding = original(name, limit)
            source.update(binding)
            return raw

        b.require(
            bound_original("model.json", b.MAX_METADATA) == b.canonical(self.model)
            and bound_original("OWNER.json", b.MAX_METADATA)
            == b.canonical(
                {
                    "envelope_sha256": self.model_hash,
                    "owner_sha256": self.model["capacity_owner_authority_sha256"],
                }
            ),
            "B2_GRAPH_ROOT_CHANGED",
        )
        actual = set()
        ll = self.model["ledger_record_limits"]
        with os.scandir(self.root) as entries:
            for entry in entries:
                self.check()
                b.require(len(actual) < ll["max_entries"], "B2_GRAPH_LEDGER_BOUND")
                actual.add(entry.name)
        b.require("MUTATING.json" not in actual, "B2_GRAPH_BLOCKED")
        expected = {"model.json", "OWNER.json"}
        previous = None
        members, bindings, terminals, branch = {}, {}, {}, None
        active, total = None, 0
        last_time = self.model["valid_from"]
        index = 1
        while f"{index:06d}.json" in actual:
            name = f"{index:06d}.json"
            expected.add(name)
            raw = bound_original(name, ll["max_record_bytes"])
            total = rs.add(total, len(raw))
            b.require(total <= ll["max_total_bytes"], "B2_GRAPH_LEDGER_BOUND")
            row = io.metadata(raw)
            version = row.get("schema_version")
            b.require(
                row.get("envelope_sha256") == self.model_hash
                and row.get("previous_ledger_sha256") == previous,
                "B2_GRAPH_CHAIN",
            )
            timestamp = next(
                (
                    row[key]
                    for key in (
                        "bound_utc",
                        "recorded_utc",
                        "begun_utc",
                        "completed_utc",
                    )
                    if key in row
                ),
                None,
            )
            b.validate_type(timestamp, "Z")
            b.require(
                last_time <= timestamp <= self.now()
                and timestamp < self.model["valid_until"],
                "B2_GRAPH_RECORD_TIME",
            )
            last_time = timestamp
            slot_id = len(terminals) + 1
            slot = (
                self.model["slots"][slot_id - 1]
                if slot_id <= len(self.model["slots"])
                else None
            )
            if version == MEMBER:
                shape(row, MEMBER_SCHEMA)
                b.require(
                    slot is not None
                    and active is None
                    and slot_id not in bindings
                    and row["member_id"] not in members
                    and len(members) < ll["max_member_bindings"]
                    and slot["member_role"] != "NONE",
                    "B2_GRAPH_MEMBER_ORDER",
                )
                plan = self.originals.member(row, self.model)
                self.authority.require("resource_graph_binding", b.digest(row), row)
                b.require(
                    slot["member_id"] == row["member_id"]
                    or (slot["member_role"] == "SELECTED_FINAL" and branch is not None),
                    "B2_GRAPH_MEMBER_ORDER",
                )
                if plan["workload_kind"] == "DIRECT_N":
                    b.require(
                        branch is not None
                        and branch["branch"] == "DIRECT_N"
                        and row["N_decision_sha256"] == branch["N_decision_sha256"]
                        and plan["result_limit"] == branch["N"],
                        "B2_GRAPH_N_BRANCH",
                    )
                if members:
                    first = next(iter(members.values()))
                    b.require(
                        (
                            first["window_plan_sha256"],
                            first["calibration_selection_sha256"],
                        )
                        == (
                            row["window_plan_sha256"],
                            row["calibration_selection_sha256"],
                        ),
                        "B2_GRAPH_WINDOW_CHANGED",
                    )
                members[row["member_id"]] = row
            elif version == BRANCH:
                shape(row, BRANCH_SCHEMA)
                b.require(
                    branch is None
                    and active is None
                    and not bindings.get(slot_id)
                    and terminals
                    and self.model["slots"][slot_id - 2]["phase"]
                    == "evaluate-calibration"
                    and terminals[slot_id - 1]["schema_version"] == FINISH,
                    "B2_GRAPH_BRANCH_CHECKPOINT",
                )
                b.require(
                    members
                    and all(
                        (x["window_plan_sha256"], x["calibration_selection_sha256"])
                        == (
                            row["window_plan_sha256"],
                            row["calibration_selection_sha256"],
                        )
                        for x in members.values()
                    ),
                    "B2_GRAPH_WINDOW_CHANGED",
                )
                self._branch_members(row, members)
                self.originals.branch(row, self.model)
                self.authority.require("resource_graph_branch", b.digest(row), row)
                branch = row
            elif version == BINDING:
                shape(row, BINDING_SCHEMA)
                b.require(
                    slot is not None
                    and row["slot_id"] == slot_id
                    and slot_id not in bindings
                    and active is None,
                    "B2_GRAPH_BINDING_ORDER",
                )
                if slot["condition"] == "DIRECT_N_BRANCH":
                    b.require(
                        branch is not None and branch["branch"] == "DIRECT_N",
                        "B2_GRAPH_N_UNSELECTED",
                    )
                self._validate_binding(row, slot, members, branch)
                bindings[slot_id] = row
            elif version == SKIP:
                shape(row, SKIP_SCHEMA)
                b.require(
                    slot is not None
                    and row["slot_id"] == slot_id
                    and slot_id not in bindings
                    and active is None
                    and slot["condition"] != "REQUIRED",
                    "B2_GRAPH_SKIP_UNTOUCHED",
                )
                member = self._member_for(slot, members, branch)
                proofs = self._inventory(row["proof_inventory_sha256"])
                self._skip_proof_shape(row, slot, branch, proofs)
                self.originals.skip(row, slot, member, branch, proofs)
                self.authority.require("resource_graph_skip", b.digest(row), row)
                terminals[slot_id] = row
            elif version == BEGIN:
                shape(row, BEGIN_SCHEMA)
                b.require(
                    slot is not None
                    and row["slot_id"] == slot_id
                    and slot_id in bindings
                    and active is None
                    and row["slot_binding_sha256"] == b.digest(bindings[slot_id]),
                    "B2_GRAPH_BEGIN_ORDER",
                )
                original_config = io.metadata(
                    self.records.raw(bindings[slot_id]["configuration_scope_sha256"])
                )
                original_config["runtime"]["authority_sha256"] = row["authority_sha256"]
                original_config["runtime"]["resource_retention"][
                    "slot_binding_sha256"
                ] = row["slot_binding_sha256"]
                b.require(
                    b.digest(original_config) == row["configuration_sha256"],
                    "B2_GRAPH_CONFIGURATION_SCOPE",
                )
                authority_raw = self.records.raw(row["authority_sha256"])
                if self.model[
                    "population_scope"
                ] != b.SYNTHETIC or authority_raw.startswith(b"{"):
                    from . import s12_b2_runtime as runtime_module

                    historical = runtime_module.Authority(
                        self.records,
                        row["authority_sha256"],
                        original_config,
                        SimpleNamespace(utc=lambda: row["begun_utc"]),
                    )
                    historical.require(
                        "resource_graph_begin",
                        row["slot_binding_sha256"],
                        {
                            "configuration_sha256": runtime_module.scope_hash(
                                original_config
                            ),
                            "slot_binding_sha256": row["slot_binding_sha256"],
                        },
                    )
                else:
                    b.require(
                        authority_raw.startswith(b"B2 SYNTHETIC ONLY"),
                        "B2_GRAPH_ORIGINAL_AUTHORITY",
                    )
                active = row
            elif version == FINISH:
                shape(row, FINISH_SCHEMA)
                b.require(
                    slot is not None
                    and active is not None
                    and row["slot_id"] == slot_id
                    and row["slot_binding_sha256"] == b.digest(bindings[slot_id]),
                    "B2_GRAPH_FINISH_ORDER",
                )
                elapsed = datetime.strptime(
                    row["completed_utc"], "%Y-%m-%dT%H:%M:%S.%fZ"
                ) - datetime.strptime(active["begun_utc"], "%Y-%m-%dT%H:%M:%S.%fZ")
                micros = (
                    elapsed.days * 86400 + elapsed.seconds
                ) * 1_000_000 + elapsed.microseconds
                b.require(
                    0 <= micros <= rs.mul(slot["max_duration_ms"], 1000),
                    "B2_GRAPH_COMMAND_DEADLINE",
                )
                observed = self._observed(
                    rs.inventory_roots(row["inventory_roots"]),
                    max_entries=row["inventory_max_entries"],
                    records=row["generated_records"],
                    slot=slot,
                )
                b.require(
                    observed
                    == {
                        "bytes": row["observed_bytes"],
                        "entries": row["observed_inodes"],
                        "sha256": row["inventory_sha256"],
                    }
                    and observed["bytes"] <= slot["max_generated_bytes"]
                    and observed["entries"] <= slot["max_generated_inodes"],
                    "B2_RS1_CUMULATIVE_INVENTORY_CHANGED",
                )
                terminals[slot_id], active = row, None
            else:
                b.require(False, "B2_GRAPH_VERSION")
            previous = b.sha(raw).hex()
            index += 1
        if "ACTIVE.json" in actual:
            expected.add("ACTIVE.json")
            b.require(
                allow_active
                and active is not None
                and bound_original("ACTIVE.json", ll["max_record_bytes"])
                == b.canonical(active),
                "B2_GRAPH_BLOCKED",
            )
        else:
            b.require(active is None, "B2_GRAPH_BLOCKED")
        # Fresh original-content and inode/private-identity pass AFTER every
        # semantic/authority callback. No callback acceptance or remembered head
        # can stand in for these original reads. Two passes are charged to the
        # same non-resetting command deadline and selected ledger limits.
        final = hashlib.sha256()
        for name in ("model.json", "OWNER.json"):
            _, binding = original(name, b.MAX_METADATA)
            final.update(binding)
        for record_index in range(1, index):
            _, binding = original(f"{record_index:06d}.json", ll["max_record_bytes"])
            final.update(binding)
        if "ACTIVE.json" in actual:
            _, binding = original("ACTIVE.json", ll["max_record_bytes"])
            final.update(binding)
        final_names = set()
        with os.scandir(self.root) as entries:
            for entry in entries:
                self.check()
                b.require(len(final_names) < ll["max_entries"], "B2_GRAPH_LEDGER_BOUND")
                final_names.add(entry.name)
        io.private_directory(self.root)
        after = self.root.stat()
        b.require(
            actual == expected
            and final_names == actual
            and source.digest() == final.digest()
            and (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
            "B2_GRAPH_LEDGER_CHANGED",
        )
        b.require(
            self.expected_head is None or previous == self.expected_head,
            "B2_GRAPH_HEAD_CHANGED",
        )
        self.expected_head = previous
        (
            self.head,
            self.next_record,
            self.members,
            self.bindings,
            self.terminals,
            self.branch,
            self.active,
        ) = previous, index, members, bindings, terminals, branch, active
        self.next_slot = len(terminals) + 1
        return self.accounting()

    def accounting(self):
        return {
            "reserved_bytes": self.model["physical_peak_bound_bytes"],
            "reserved_inodes": self.model["physical_inode_bound"],
            "reserved_slots": len(self.model["slots"]),
            "terminal_slots": len(self.terminals),
            "skipped_slots": sum(
                x["schema_version"] == SKIP for x in self.terminals.values()
            ),
            "owner_acceptance": "NOT_ESTABLISHED",
        }

    def _append(self, row, *, active=False):
        self.reopen(allow_active=active)
        b.require(row["previous_ledger_sha256"] == self.head, "B2_GRAPH_CHAIN")
        raw = b.canonical(row)
        timestamp = next(
            (
                row[key]
                for key in ("bound_utc", "recorded_utc", "begun_utc", "completed_utc")
                if key in row
            ),
            None,
        )
        b.validate_type(timestamp, "Z")
        b.require(
            self.model["valid_from"]
            <= timestamp
            <= self.now()
            < self.model["valid_until"],
            "B2_GRAPH_RECORD_TIME",
        )
        b.require(
            len(raw) <= self.model["ledger_record_limits"]["max_record_bytes"],
            "B2_GRAPH_LEDGER_BOUND",
        )
        b.require(_LOCK.acquire(blocking=False), "B2_GRAPH_OWNER_BUSY")
        try:
            io.write(
                self.root / "MUTATING.json",
                b.canonical(
                    {
                        "envelope_sha256": self.model_hash,
                        "previous_ledger_sha256": self.head,
                    }
                ),
            )
            io.write(self.root / f"{self.next_record:06d}.json", raw)
            self.check()
            if row["schema_version"] == BEGIN:
                io.write(self.root / "ACTIVE.json", raw)
                self.check()
            if row["schema_version"] == FINISH:
                claim = io.read(self.root / "ACTIVE.json")
                self.check()
                (self.root / "ACTIVE.json").unlink()
                try:
                    self._sync()
                    self.check()
                except BaseException:
                    io.write(self.root / "ACTIVE.json", claim)
                    raise
            self._release_mutation()
        except BaseException:
            self.poisoned = True
            raise
        finally:
            _LOCK.release()
        self.expected_head = b.digest(row)
        try:
            self.reopen(allow_active=row["schema_version"] == BEGIN)
        except BaseException:
            self.poisoned = True
            if not (self.root / "MUTATING.json").exists():
                io.write(
                    self.root / "MUTATING.json",
                    b.canonical(
                        {
                            "envelope_sha256": self.model_hash,
                            "uncertain_record_sha256": b.digest(row),
                        }
                    ),
                )
            if (
                row["schema_version"] == FINISH
                and not (self.root / "ACTIVE.json").exists()
            ):
                io.write(self.root / "ACTIVE.json", b.canonical(self.begin_record))
            raise
        return b.digest(row)

    def append_member(self, row):
        b.require(
            not isinstance(self.originals, RuntimeOriginals), "B2_GRAPH_BINDER_REQUIRED"
        )
        shape(row, MEMBER_SCHEMA)
        self.reopen()
        b.require(self.next_slot <= len(self.model["slots"]), "B2_GRAPH_EXHAUSTED")
        slot = self.model["slots"][self.next_slot - 1]
        b.require(
            slot["member_role"] != "NONE"
            and self.next_slot not in self.bindings
            and row["member_id"] not in self.members
            and (
                slot["member_id"] == row["member_id"]
                or slot["member_role"] == "SELECTED_FINAL"
            ),
            "B2_GRAPH_MEMBER_ORDER",
        )
        self.originals.member(row, self.model)
        self.authority.require("resource_graph_binding", b.digest(row), row)
        return self._append(row)

    def append_binding(self, row, config):
        b.require(
            not isinstance(self.originals, RuntimeOriginals), "B2_GRAPH_BINDER_REQUIRED"
        )
        shape(row, BINDING_SCHEMA)
        self.reopen()
        b.require(
            row["slot_id"] == self.next_slot
            and self.next_slot <= len(self.model["slots"])
            and self.next_slot not in self.bindings,
            "B2_GRAPH_BINDING_ORDER",
        )
        self._validate_binding(
            row,
            self.model["slots"][self.next_slot - 1],
            self.members,
            self.branch,
            config,
        )
        return self._append(row)

    def append_branch(self, row):
        b.require(
            not isinstance(self.originals, RuntimeOriginals), "B2_GRAPH_BINDER_REQUIRED"
        )
        shape(row, BRANCH_SCHEMA)
        self.reopen()
        b.require(
            self.branch is None
            and self.next_slot > 1
            and self.model["slots"][self.next_slot - 2]["phase"]
            == "evaluate-calibration"
            and self.next_slot not in self.bindings,
            "B2_GRAPH_BRANCH_CHECKPOINT",
        )
        self._branch_members(row, self.members)
        self.originals.branch(row, self.model)
        self.authority.require("resource_graph_branch", b.digest(row), row)
        return self._append(row)

    def skip(self, row):
        b.require(
            not isinstance(self.originals, RuntimeOriginals), "B2_GRAPH_BINDER_REQUIRED"
        )
        shape(row, SKIP_SCHEMA)
        self.reopen()
        b.require(
            row["slot_id"] == self.next_slot
            and self.next_slot <= len(self.model["slots"])
            and self.next_slot not in self.bindings,
            "B2_GRAPH_SKIP_UNTOUCHED",
        )
        slot = self.model["slots"][self.next_slot - 1]
        b.require(slot["condition"] != "REQUIRED", "B2_GRAPH_SKIP_UNTOUCHED")
        proofs = self._inventory(row["proof_inventory_sha256"])
        self._skip_proof_shape(row, slot, self.branch, proofs)
        self.originals.skip(
            row,
            slot,
            self._member_for(slot, self.members, self.branch),
            self.branch,
            proofs,
        )
        self.authority.require("resource_graph_skip", b.digest(row), row)
        return self._append(row)

    def _skip_proof_shape(self, row, slot, branch, proofs):
        reason = row["reason"]
        expected = {
            "N_EQUALS_C": {"N_DECISION"},
            "CAMPAIGN_ALREADY_COMPLETE": {"SEGMENT_CLOSURE"},
            "INDEPENDENT_REVIEW_ALREADY_COMPLETE": {"REVIEW_COMPLETION"},
        }[reason]
        b.require(
            len(proofs) == 1 and {x["record_kind"] for x in proofs} == expected,
            "B2_GRAPH_SKIP_PROOF",
        )
        linked = (
            reason in ("N_EQUALS_C", "INDEPENDENT_REVIEW_ALREADY_COMPLETE")
            or slot["condition"] == "DIRECT_N_BRANCH"
        )
        b.require(
            row["branch_record_sha256"]
            == (b.digest(branch) if linked and branch is not None else None),
            "B2_GRAPH_SKIP_PROOF",
        )

    def begin(self, config, binding_sha256):
        self.reopen()
        b.require(
            self.next_slot in self.bindings
            and self.next_slot <= len(self.model["slots"]),
            "B2_GRAPH_UNBOUND",
        )
        binding = self.bindings[self.next_slot]
        b.require(
            binding_sha256 == b.digest(binding)
            and config["runtime"]["resource_retention"]["slot_binding_sha256"]
            == binding_sha256,
            "B2_GRAPH_SLOT_SCOPE",
        )
        self.command, selected = self._validate_binding(
            binding,
            self.model["slots"][self.next_slot - 1],
            self.members,
            self.branch,
            config,
        )
        row = {
            "schema_version": BEGIN,
            "envelope_sha256": self.model_hash,
            "slot_id": self.next_slot,
            "previous_ledger_sha256": self.head,
            "slot_binding_sha256": binding_sha256,
            "configuration_sha256": b.digest(config),
            "authority_sha256": config["runtime"]["authority_sha256"],
            "begun_utc": self.now(),
        }
        from . import s12_b2_runtime as runtime

        self.authority.require(
            "resource_graph_begin",
            binding_sha256,
            {
                "configuration_sha256": runtime.scope_hash(config),
                "slot_binding_sha256": binding_sha256,
            },
        )
        self._append(row)
        self.begin_record = row
        return self.command, selected

    def observe(self, *, physical_bytes, inodes):
        try:
            self.check()
            b.uint(physical_bytes)
            b.uint(inodes)
            b.require(
                self.command is not None
                and physical_bytes <= self.command["max_generated_bytes"]
                and inodes <= self.command["max_generated_inodes"],
                "B2_RS1_COMMAND_BOUND",
            )
        except BaseException:
            self.poisoned = True
            raise

    def reserve_record(self, path, digest, *, size):
        try:
            return self._reserve_record(path, digest, size=size)
        except BaseException:
            self.poisoned = True
            raise

    def _reserve_record(self, path, digest, *, size):
        """Register one shared-store output before creation, with no disk write."""
        self.check()
        b.uint(size)
        b.validate_type(digest, "D")
        path = Path(path)
        b.require(
            self.begin_record is not None
            and not self.finished
            and path.is_absolute()
            and ".." not in path.parts
            and path == self.records.root / (digest + ".json")
            and len(str(path).encode("utf8")) <= 4096,
            "B2_GRAPH_GENERATED_RECORD",
        )
        b.require(
            io.read(self.root / "ACTIVE.json") == b.canonical(self.begin_record),
            "B2_GRAPH_BLOCKED",
        )
        component = next(
            x for x in self.model["components"] if x["component_id"] == "INVENTORIES"
        )
        maximum = min(MAX_SLOTS, self.command["allocations"]["INVENTORIES"])
        b.require(
            str(path) not in self.generated_records
            and len(self.generated_records) < maximum
            and size <= component["per_instance_bytes_bound"],
            "B2_GRAPH_GENERATED_RECORD_BOUND",
        )
        self.generated_records[str(path)] = digest

    def _observed(self, roots, *, max_entries, records, slot):
        generated = rs.generation_inventory(
            roots, max_entries=max_entries, check=self.check
        )
        maximum = min(MAX_SLOTS, slot["allocations"]["INVENTORIES"])
        b.require(
            type(records) is list and len(records) <= maximum,
            "B2_GRAPH_GENERATED_RECORD_BOUND",
        )
        component = next(
            x for x in self.model["components"] if x["component_id"] == "INVENTORIES"
        )
        total, count, previous = generated["bytes"], generated["entries"], None
        for row in records:
            shape(row, {"path": {"primitive": "absolute_path"}, "sha256": "D"})
            path = Path(row["path"])
            b.require(
                path == self.records.root / (row["sha256"] + ".json")
                and path.is_absolute()
                and ".." not in path.parts
                and len(row["path"].encode("utf8")) <= 4096
                and (previous is None or previous < row["path"]),
                "B2_GRAPH_GENERATED_RECORD",
            )
            raw = self.records.raw(row["sha256"])
            b.require(
                len(raw) <= component["per_instance_bytes_bound"],
                "B2_GRAPH_GENERATED_RECORD_BOUND",
            )
            info = path.stat(follow_symlinks=False)
            total, count, previous = (
                rs.add(total, max(info.st_size, info.st_blocks * 512)),
                rs.add(count, 1),
                row["path"],
            )
            b.require(count <= max_entries, "B2_RS1_INVENTORY_BOUND")
        return {
            "bytes": total,
            "entries": count,
            "sha256": b.digest({"generated": generated, "generated_records": records}),
        }

    def prepare_finish(self):
        """Reserve post-report finalization without erasing any counter charge."""
        if getattr(self, "controls", None) is not None and not hasattr(
            self, "finalization_controls"
        ):
            self.reopen(allow_active=True)
            self.finalization_controls = self.controls.reserve_remaining()

    def finish(self, *, roots, max_entries):
        try:
            if hasattr(self, "finalization_controls"):
                with io.allocation_controls(self.finalization_controls):
                    return self._finish(roots=roots, max_entries=max_entries)
            return self._finish(roots=roots, max_entries=max_entries)
        except BaseException:
            self.poisoned = True
            raise

    def _finish(self, *, roots, max_entries):
        b.require(
            not self.finished and self.begin_record is not None,
            "B2_RS1_ALREADY_FINISHED",
        )
        self.reopen(allow_active=True)
        b.require(self.active == self.begin_record, "B2_GRAPH_BLOCKED")
        roots = rs.inventory_roots([str(Path(x)) for x in roots])
        records = [
            {"path": path, "sha256": digest}
            for path, digest in sorted(self.generated_records.items())
        ]
        observed = self._observed(
            roots, max_entries=max_entries, records=records, slot=self.command
        )
        self.observe(physical_bytes=observed["bytes"], inodes=observed["entries"])
        row = {
            "schema_version": FINISH,
            "envelope_sha256": self.model_hash,
            "slot_id": self.next_slot,
            "previous_ledger_sha256": self.head,
            "slot_binding_sha256": self.active["slot_binding_sha256"],
            "disposition": "COMPLETED",
            "observed_bytes": observed["bytes"],
            "observed_inodes": observed["entries"],
            "inventory_sha256": observed["sha256"],
            "inventory_roots": [str(x) for x in roots],
            "inventory_max_entries": max_entries,
            "generated_records": records,
            "completed_utc": self.now(),
        }
        result = self._append(row, active=True)
        self.finished = True
        return result


class RuntimeOriginals(ScientificOriginals):
    """Read-only original reopening at entry, before derived namespaces exist.

    Slot preparation runs full selection/adequacy algorithms through
    ScientificOriginals. Entry freshly verifies their exact retained originals,
    WorkFile membership, complete publication inventories and grants. It creates
    no validation cache or index. The normal phase gate separately recomputes
    selection and publication science with its charged scratch before service.
    """

    def __init__(self, port, root):
        self.port, self.root = port, Path(root)
        self.records, self.authority, self.check = (
            port.records,
            port.authority,
            port.check_deadline,
        )

    def configurations(self):
        yield self.port.config
        maximum = self.port.resource_model["ledger_record_limits"]["max_entries"]
        for index in range(1, maximum + 1):
            path = self.root / f"{index:06d}.json"
            if not path.exists():
                break
            row = io.metadata(io.read(path))
            if row.get("schema_version") == BINDING:
                yield io.metadata(self.records.raw(row["configuration_scope_sha256"]))

    def member(self, row, model):
        from . import s12_b2_runtime as runtime
        from . import s12_b2_operations as operations
        from . import s12_b2_planning as planning

        self.check()
        candidates = [
            cfg
            for cfg in self.configurations()
            if (cfg["runtime"].get("campaign") or cfg.get("bootstrap") or {}).get(
                "plan_sha256"
            )
            == row["exact_plan_sha256"]
        ]
        b.require(candidates, "B2_GRAPH_ORIGINAL_PLAN")
        cfg = candidates[0]
        campaign = cfg["runtime"]["campaign"]
        spec = campaign if campaign is not None else cfg["bootstrap"]
        plan = io.metadata(self.records.raw(spec["plan_sha256"]))
        profile = io.metadata(self.records.raw(spec["profile_sha256"]))
        operations.validate_plan(plan, profile)
        member = validate_plan_model(model, plan)
        b.require(
            member["member_id"] == row["member_id"]
            and rs.workload_binding(plan) == row["plan_binding_sha256"]
            and (
                spec["work_file_sha256"]
                if campaign is not None
                else cfg["bootstrap_work_file"]["sha256"]
            )
            == row["work_file_sha256"]
            and plan["window_plan_sha256"] == row["window_plan_sha256"],
            "B2_GRAPH_MEMBER_BINDING",
        )
        work = runtime.WorkFile(
            Path(
                spec["work_path"]
                if campaign is not None
                else cfg["bootstrap_work_file"]["path"]
            ),
            row["work_file_sha256"],
            plan,
            self.check,
        )
        work.verify()
        bound = self.records.get(
            row["calibration_selection_sha256"], "calibration_selection"
        )
        core = self.records.get(bound["calibration_plan_sha256"], "calibration_plan")
        b.require(
            {
                k: v
                for k, v in bound.items()
                if k
                not in (
                    "schema_version",
                    "calibration_plan_sha256",
                    "window_plan_sha256",
                )
            }
            == {k: v for k, v in core.items() if k != "schema_version"},
            "B2_SELECTION_BINDING",
        )
        tail = json.loads(self.records.raw(bound["tail_inventory_sha256"]))
        paired = json.loads(self.records.raw(bound["paired_inventory_sha256"]))
        intents = json.loads(self.records.raw(bound["workload_inventory_sha256"]))
        b.require(
            type(tail) is list
            and len(tail) <= 2000
            and type(paired) is list
            and len(paired) <= 400
            and type(intents) is list
            and 1 <= len(intents) <= 10,
            "B2_GRAPH_SELECTION_BOUND",
        )
        selection = {
            "C": bound["C"],
            "grid": bound["grid"],
            "intents": [
                {
                    "kind": x["workload_kind"],
                    "size": x["result_limit"],
                    "repetition": x["repetition"],
                    "subset": None
                    if x["workload_kind"] == "FULL_C"
                    else tail
                    if x["workload_kind"] == "TAIL"
                    else paired,
                }
                for x in intents
            ],
        }
        from . import s12_b2_catalog as catalogs

        binding = self.records.get(cfg["input_binding_sha256"], "stage11_input_binding")
        self.authority.require("protected_input", b.digest(binding), binding)
        catalog = catalogs.Catalog(
            Path(cfg["catalog_path"]),
            binding,
            expected_file_sha256=cfg["catalog_file_sha256"],
        )
        admission = (
            self.records.get(spec["admission_sha256"], "segment_admission")
            if campaign is not None
            else None
        )
        try:
            if admission is None:
                planning.verify_member_workload(
                    self.records,
                    row["calibration_selection_sha256"],
                    selection,
                    catalog,
                    plan,
                    work.rows,
                    authority=self.authority,
                )
            else:
                planning.verify_workload(
                    self.records,
                    row["calibration_selection_sha256"],
                    selection,
                    catalog,
                    plan,
                    work.rows,
                    admission,
                    authority=self.authority,
                )
        finally:
            catalog.close()
        b.require(
            (plan["workload_kind"] == "DIRECT_N")
            == (row["N_decision_sha256"] is not None)
            and (
                row["N_decision_sha256"] is None
                or plan["selection_basis_sha256"] == row["N_decision_sha256"]
            ),
            "B2_GRAPH_MEMBER_BINDING",
        )
        return plan

    def branch(self, row, model):
        result = self.records.get(row["adequacy_report_sha256"], "calibration_result")
        decision = self.records.get(row["N_decision_sha256"], "n_decision")
        selection = self.records.get(
            row["calibration_selection_sha256"], "calibration_selection"
        )
        window = self.records.get(row["window_plan_sha256"], "window_plan")
        self.authority.require("N_selection", row["N_decision_sha256"], decision)
        b.require(
            result["disposition"] == "ELIGIBLE_FOR_OWNER_REVIEW"
            and result["population_scope"] == model["population_scope"]
            and result["selection_sha256"] == row["calibration_selection_sha256"]
            and result["calibration_inventory_sha256"]
            == decision["calibration_inventory_sha256"]
            == row["calibration_inventory_sha256"]
            and decision["adequacy_report_sha256"] == row["adequacy_report_sha256"]
            and decision["decision"] == "SELECTED"
            and decision["result_limit"] == row["N"]
            and row["N"] in result["eligible_limits"]
            and row["N"] in selection["grid"]
            and row["C"] == selection["C"]
            and (row["branch"] == "REUSE_FULL_C") == (row["C"] == row["N"])
            and window["dispatch_from"]
            <= decision["decided_utc"]
            <= row["recorded_utc"]
            < window["dispatch_until"],
            "B2_GRAPH_N_BRANCH",
        )
        specs = next(
            (
                cfg["calibration_publications"]
                for cfg in self.configurations()
                if cfg.get("calibration_publications")
            ),
            None,
        )
        b.require(
            type(specs) is list and 1 <= len(specs) <= 10, "B2_CALIBRATION_TOTALITY"
        )
        inventory = []
        for spec in specs:
            self.check()
            b.require(set(spec) == {"path", "manifest_sha256"}, "B2_ARTIFACT_SPEC")
            root = Path(spec["path"])
            raw = io.read(root / "manifest.json")
            b.require(b.sha(raw).hex() == spec["manifest_sha256"], "B2_MANIFEST_HASH")
            manifest = io.metadata(raw)
            io.verify_inventory(
                root,
                manifest["inventory"],
                extra={"manifest.json", "registration.json", "_COMMITTED"},
            )
            from . import s12_b2_publication as publication

            publication.validate_terminal(
                root,
                bytes.fromhex(spec["manifest_sha256"]),
                committed=True,
                validate_science=lambda r, m: io.verify_inventory(
                    r,
                    m["inventory"],
                    extra={"manifest.json", "registration.json", "_COMMITTED"},
                ),
            )
            bindings = manifest["publication_bindings"]
            plan = io.metadata(io.read(root / "campaign.json"))["plan"]
            inventory.append(
                {
                    "workload_kind": plan["workload_kind"],
                    "publication_sha256": spec["manifest_sha256"],
                    "campaign_closure_sha256": bindings["campaign_closure_sha256"],
                    "window_plan_sha256": bindings["window_plan_sha256"],
                    "workload_sha256": bindings["workload_sha256"],
                }
            )
        inventory.sort(key=lambda x: (x["workload_kind"], x["publication_sha256"]))
        b.require(
            b.digest(inventory) == row["calibration_inventory_sha256"],
            "B2_CALIBRATION_INVENTORY",
        )
        return result

    def skip(self, row, slot, member, branch, proofs):
        if row["reason"] == "N_EQUALS_C":
            return super().skip(row, slot, member, branch, proofs)
        # Original inventory of every completed command was reopened by the
        # ledger. Reopen the finite proof and its exact grant as well. Runtime
        # never appends a SKIP: the scientific original readers already proved it
        # before the immutable terminal was provisioned.
        b.require(
            (
                row["reason"] == "CAMPAIGN_ALREADY_COMPLETE"
                and slot["condition"] == "CONTINUATION_CAPACITY"
                and member is not None
                and any(x["record_kind"] == "SEGMENT_CLOSURE" for x in proofs)
            )
            or (
                row["reason"] == "INDEPENDENT_REVIEW_ALREADY_COMPLETE"
                and slot["condition"] == "OPTIONAL_INDEPENDENT_REOPEN"
                and member is not None
                and branch is not None
                and any(x["record_kind"] == "REVIEW_COMPLETION" for x in proofs)
            ),
            "B2_GRAPH_SKIP_PROOF",
        )
        for proof in proofs:
            self.records.raw(proof["sha256"])


def bind_runtime(port):
    """Attach the real runtime to an already bound slot, before output creation."""
    pointer = port.resource_binding
    b.require(
        type(pointer) is dict
        and set(pointer)
        == {
            "model_sha256",
            "command_id",
            "allocation_limits_sha256",
            "slot_binding_sha256",
        },
        "B2_GRAPH_RUNTIME_BINDING",
    )
    for field in ("model_sha256", "allocation_limits_sha256", "slot_binding_sha256"):
        b.validate_type(pointer[field], "D")
    b.uint(pointer["command_id"], True)
    model = parse(port.records.raw(pointer["model_sha256"]), MODEL)
    authority_check(
        model,
        port.records,
        port.authority,
        now=port.clock.utc(),
        source_hash=b.digest(port.settings["source_files"]),
        # One stable graph fingerprint spans LP1 and service commands. Detailed
        # AP v2 observations stay separately bound by actual config/start/M2 and
        # are checked before BEGIN. This v1 fingerprint certifies no native,
        # codec, transitive-build, physical-allocation or capacity fact.
        runtime_hash=b.digest(port._actual_runtime_inventory(successor=False)),
    )
    b.require(pointer["command_id"] <= len(model["slots"]), "B2_GRAPH_EXHAUSTED")
    slot = model["slots"][pointer["command_id"] - 1]
    paths = port.config.get("command_paths")
    shape(
        paths,
        {
            "output_path": {"primitive": "absolute_path"},
            "scratch_path": {"primitive": "absolute_path"},
        },
    )
    b.require(
        paths == {"output_path": str(port.output), "scratch_path": str(port.scratch)},
        "B2_GRAPH_COMMAND_PATHS",
    )
    filesystem = os.statvfs(port.output.parent)
    b.require(
        model["capacity_bytes"] <= port.settings["phase_disk_capacity_bytes"]
        and model["capacity_bytes"] <= filesystem.f_bavail * filesystem.f_frsize
        and model["capacity_inodes"] <= filesystem.f_favail,
        "B2_RS1_CAPACITY_UNAVAILABLE",
    )
    b.require(
        slot["phase"] == port.phase
        and slot["max_duration_ms"] <= port.settings["phase_duration_ms"]
        and slot["max_memory_bytes"] <= port.settings["phase_memory_bytes"]
        and slot["max_generated_bytes"] <= port.settings["phase_generation_bound_bytes"]
        and slot["max_generated_inodes"] <= port.settings["phase_generation_max_files"],
        "B2_RS1_COMMAND_BOUND",
    )
    selected = limits.parse(port.records.raw(pointer["allocation_limits_sha256"]))
    ceiling = parse(port.records.raw(slot["allocation_limit_ceiling_sha256"]), CEILING)
    command = validate_ceiling(selected, ceiling, model, slot)
    root = Path(port.settings["output_parent"]) / ("rs1_acceptance_" + b.digest(model))
    b.require(
        root.is_dir()
        and root not in (port.output, port.scratch)
        and not port.output.is_relative_to(root)
        and not port.scratch.is_relative_to(root),
        "B2_GRAPH_UNBOUND",
    )
    port.resource_model, port.resource_command = model, command
    port.resource_command_deadline = (
        port.clock.now_ns() + slot["max_duration_ms"] * 1_000_000
    )
    port.allocation_limits = limits.Controls(selected, check=port.check_deadline)
    port._stack.enter_context(io.allocation_controls(port.allocation_limits))
    originals = RuntimeOriginals(port, root)
    ledger = AcceptanceLedger(
        root,
        model,
        records=port.records,
        authority=port.authority,
        originals=originals,
        check=port.check_deadline,
        now=port.clock.utc,
        expected_head=pointer["slot_binding_sha256"],
    )
    b.require(ledger.next_slot == pointer["command_id"], "B2_GRAPH_BINDING_ORDER")
    port._source_check()
    port.gate.check()
    ledger.begin(port.config, pointer["slot_binding_sha256"])
    ledger.controls = port.allocation_limits
    port.resource_ledger = ledger

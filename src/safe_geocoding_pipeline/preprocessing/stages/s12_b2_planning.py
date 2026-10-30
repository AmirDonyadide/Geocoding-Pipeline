"""Acyclic pre-outcome calibration records and exact finite workload gates."""

from __future__ import annotations

import json
from itertools import zip_longest
from . import s12_b2_contract as b
from . import s12_b2_operations as o
from . import s12_b2_calibration as cal


def store(records, obj, *, owner, secret_guard):
    return records.put(b.canonical(obj), owner=owner, secret_guard=secret_guard)


def seal_core(
    records,
    selection,
    catalog,
    *,
    lineage_hash,
    capability_hash,
    decision_hash,
    owner,
    secret_guard,
):
    """No window, campaign, observed result, or N dependency in this core."""
    put = lambda obj: store(records, obj, owner=owner, secret_guard=secret_guard)
    tail = put(selection["tail"])
    paired = put(selection["paired"])
    coverage = put(selection["coverage"])
    full = o.manifest_digest(
        row["query_semantic_id"].hex() for row in catalog.semantics()
    )
    intents = [
        {
            "schema_version": "stage12_calibration_work_intent_b2_v1",
            "workload_kind": x["kind"],
            "result_limit": x["size"],
            "repetition": x["repetition"],
            "subset_inventory_sha256": full
            if x["subset"] is None
            else tail
            if x["kind"] == "TAIL"
            else paired,
            "planned_data": x["count"],
        }
        for x in selection["intents"]
    ]
    for x in intents:
        b.validate(x)
    core = {
        "schema_version": "stage12_calibration_plan_b2_v1",
        "population_scope": catalog.binding["population_scope"],
        "stage11_input_binding_sha256": b.digest(catalog.binding),
        "lineage_binding_sha256": lineage_hash,
        "capability_evidence_sha256": capability_hash,
        "C": selection["C"],
        "T": selection["T"],
        "grid": selection["grid"],
        "tail_inventory_sha256": tail,
        "paired_inventory_sha256": paired,
        "coverage_sha256": coverage,
        "workload_inventory_sha256": put(intents),
        "decision_sha256": decision_hash,
    }
    b.validate(core)
    return put(core)


def bind_window(records, core_hash, window_hash, *, owner, secret_guard):
    core = records.get(core_hash, "calibration_plan")
    window = records.get(window_hash, "window_plan")
    b.require(window["calibration_plan_sha256"] == core_hash, "B2_SELECTION_BINDING")
    selection = {
        **core,
        "schema_version": "stage12_calibration_selection_b2_v1",
        "calibration_plan_sha256": core_hash,
        "window_plan_sha256": window_hash,
    }
    b.validate(selection)
    return store(records, selection, owner=owner, secret_guard=secret_guard)


def load_selection(records, selection_hash, catalog, *, authority, scratch):
    bound = records.get(selection_hash, "calibration_selection")
    core = records.get(bound["calibration_plan_sha256"], "calibration_plan")
    window = records.get(bound["window_plan_sha256"], "window_plan")
    b.require(
        {
            k: v
            for k, v in bound.items()
            if k
            not in ("schema_version", "calibration_plan_sha256", "window_plan_sha256")
        }
        == {k: v for k, v in core.items() if k != "schema_version"}
        and window["calibration_plan_sha256"] == bound["calibration_plan_sha256"]
        and core["stage11_input_binding_sha256"] == b.digest(catalog.binding)
        and core["population_scope"] == catalog.binding["population_scope"],
        "B2_SELECTION_BINDING",
    )
    for k in (
        "lineage_binding_sha256",
        "capability_evidence_sha256",
        "decision_sha256",
    ):
        records.raw(core[k])
        authority.require(k, core[k], core)
    # Capability support is an explicit reviewed fact, not Pelias's theoretical40.
    supported = authority.supported_size(core["capability_evidence_sha256"])
    b.uint(supported, True)
    b.require(supported <= 40, "B2_CAPABILITY_UNRESOLVED")
    result = cal.select(
        catalog,
        scratch,
        C=core["C"],
        T=core["T"],
        supported=supported,
        authority=authority,
        decision_hash=core["decision_sha256"],
    )
    b.require(
        result["grid"] == core["grid"]
        and b.digest(result["tail"]) == core["tail_inventory_sha256"]
        and b.digest(result["paired"]) == core["paired_inventory_sha256"]
        and b.digest(result["coverage"]) == core["coverage_sha256"],
        "B2_SELECTION_RECOMPUTATION",
    )
    intents = json.loads(records.raw(core["workload_inventory_sha256"]))
    full = o.manifest_digest(
        row["query_semantic_id"].hex() for row in catalog.semantics()
    )
    expected = [
        {
            "schema_version": "stage12_calibration_work_intent_b2_v1",
            "workload_kind": x["kind"],
            "result_limit": x["size"],
            "repetition": x["repetition"],
            "subset_inventory_sha256": full
            if x["subset"] is None
            else core["tail_inventory_sha256"]
            if x["kind"] == "TAIL"
            else core["paired_inventory_sha256"],
            "planned_data": x["count"],
        }
        for x in result["intents"]
    ]
    b.require(intents == expected, "B2_INTENT_TOTALITY")
    authority.require("calibration_selection", selection_hash, bound)
    return result, bound


def verify_workload(
    records, selection_hash, selection, catalog, plan, works, admission, *, authority
):
    bound = records.get(selection_hash, "calibration_selection")
    b.require(
        bound["window_plan_sha256"] == plan["window_plan_sha256"]
        and bound["population_scope"] == plan["population_scope"],
        "B2_SELECTION_BINDING",
    )
    kind = plan["workload_kind"]
    N = None
    if kind == "DIRECT_N":
        decision = records.get(plan["selection_basis_sha256"], "n_decision")
        authority.require("N_selection", plan["selection_basis_sha256"], decision)
        b.require(
            decision["decision"] == "SELECTED"
            and decision["window_plan_sha256"] == plan["window_plan_sha256"]
            and decision["result_limit"] != selection["C"]
            and decision["result_limit"] in selection["grid"],
            "B2_N_DECISION_MISMATCH",
        )
        N = decision["result_limit"]
        subset = None
        b.require(
            plan["result_limit"] == N
            and plan["repetition"] == 0
            and plan["subset_selection_sha256"] is None,
            "B2_WORK_BINDING",
        )
    else:
        b.require(
            plan["selection_basis_sha256"] == selection_hash, "B2_SELECTION_BINDING"
        )
        matched = [
            x
            for x in selection["intents"]
            if (x["kind"], x["size"], x["repetition"])
            == (kind, plan["result_limit"], plan["repetition"])
        ]
        b.require(len(matched) == 1, "B2_INTENT_TOTALITY")
        subset = matched[0]["subset"]
        b.require(
            plan["subset_selection_sha256"]
            == (
                None
                if subset is None
                else bound["tail_inventory_sha256"]
                if kind == "TAIL"
                else bound["paired_inventory_sha256"]
            ),
            "B2_SELECTION_BINDING",
        )
    expected = (
        (row["query_semantic_id"].hex() for row in catalog.semantics())
        if subset is None
        else iter(sorted(subset))
    )
    actual = (
        row["query_semantic_id"]
        for row in o.work_rows(works(), plan)
        if row["kind"] == "DATA"
    )
    for left, right in zip_longest(actual, expected):
        b.require(left is not None and left == right, "B2_WORK_TOTALITY")
    window = records.get(plan["window_plan_sha256"], "window_plan")
    schedule = records.get(window["planned_segment_plan_sha256"], "window_segment_plan")
    b.require(
        schedule["calibration_plan_sha256"] == bound["calibration_plan_sha256"]
        and schedule["population_scope"] == plan["population_scope"],
        "B2_WINDOW_PLAN",
    )
    campaigns = schedule["planned_campaigns"]
    b.require(
        [x["intent_id"] for x in campaigns] == list(range(1, len(campaigns) + 1)),
        "B2_WINDOW_PLAN",
    )
    candidates = [
        x
        for x in campaigns
        if x["workload_kind"] == kind
        and x["repetition"] == plan["repetition"]
        and (
            x["result_limit"] == plan["result_limit"]
            if kind != "DIRECT_N"
            else x["result_limit"] is None and N in x["candidate_limits"]
        )
    ]
    b.require(len(candidates) == 1, "B2_WINDOW_PLAN")
    campaign = candidates[0]
    b.require(
        campaign["planned_data"] == plan["budgets"]["data_observations"],
        "B2_WINDOW_PLAN",
    )
    b.require(
        campaign["conditional_on"]
        == ("ONLY_IF_SELECTED_N_DIFFERS_FROM_C" if kind == "DIRECT_N" else "REQUIRED"),
        "B2_WINDOW_PLAN",
    )
    slots = campaign["segment_slots"]
    b.require(
        [x["slot_id"] for x in slots] == list(range(1, len(slots) + 1))
        and 1 <= admission["segment_id"] <= len(slots),
        "B2_SEGMENT_UNPLANNED",
    )
    slot = slots[admission["segment_id"] - 1]
    b.require(
        window["dispatch_from"]
        <= slot["dispatch_from"]
        < slot["dispatch_until"]
        <= window["dispatch_until"]
        and slot["dispatch_from"] <= admission["admitted_utc"] < slot["dispatch_until"]
        and plan["budgets"]["data_attempts"] + plan["budgets"]["control_http_attempts"]
        <= slot["max_attempts"],
        "B2_SEGMENT_UNPLANNED",
    )
    authority.require(
        "planned_slot",
        window["planned_segment_plan_sha256"],
        {"slot": slot, "plan": plan, "admission": admission},
    )
    return slot

"""Retained observational evidence, independent authority and permission gates.

No network acquisition, credentials, invented signatures or installed-state
claims. Callers must provide an actually reviewed authority implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
from datetime import timedelta
import threading
import re

from . import s12_b2_contract as b
from . import s12_storage as io
from . import s12_retrieval_contract as c

PREFIX = "stage12_"
REQUIRED_SUBJECTS = frozenset(
    (
        "api_image",
        "search_image",
        "result_configuration",
        "rate_configuration",
        "index_uuid",
        "document_count",
        "service_view",
    )
)


def version(stem):
    return PREFIX + stem + "_b2_v1"


class Records:
    """Bounded content-addressed record reader; rechecks every use, no cache."""

    def __init__(self, root: Path, *, max_bytes: int = b.MAX_METADATA):
        io.private_directory(root)
        b.uint(max_bytes, True)
        b.require(max_bytes <= b.MAX_METADATA, "B2_METADATA_LIMIT")
        self.root, self.max_bytes = root, max_bytes

    def raw(self, digest: str) -> bytes:
        b.validate_type(digest, "D")
        raw = io.read(self.root / (digest + ".json"), limit=self.max_bytes)
        b.require(b.sha(raw).hex() == digest, "B2_EVIDENCE_CHANGED")
        return raw

    def get(self, digest: str, stem: str | None = None):
        return b.parse(self.raw(digest), version(stem) if stem else None)

    def put(
        self,
        raw: bytes,
        *,
        owner: Callable[[], None],
        secret_guard: Callable[[bytes], None],
    ) -> str:
        owner()
        b.require(len(raw) <= self.max_bytes, "B2_METADATA_LIMIT")
        secret_guard(raw)
        digest = b.sha(raw).hex()
        path = self.root / (digest + ".json")
        if path.exists():
            b.require(self.raw(digest) == raw, "B2_EVIDENCE_CHANGED")
        else:
            io.write(path, raw)
        b.require(self.raw(digest) == raw, "B2_EVIDENCE_CHANGED")
        return digest


def attribution(records: Records, subject: str, review: str, authority) -> None:
    obj = records.get(review, "authority_review")
    b.require(
        obj["subject_record_sha256"] == subject
        and obj["result"] == "ATTRIBUTION_ACCEPTED",
        "AUTHORITY_UNRESOLVED",
    )
    b.require(
        subject
        not in (
            obj["issuer_role_record_sha256"],
            obj["channel_evidence_sha256"],
            obj["reviewer_delegation_sha256"],
        ),
        "AUTHORITY_UNRESOLVED",
    )
    for field in (
        "issuer_role_record_sha256",
        "channel_evidence_sha256",
        "reviewer_delegation_sha256",
    ):
        records.raw(obj[field])
    authority.require("attribution", review, obj)
    records.raw(subject)


def privacy(
    records: Records,
    permission_hash: str,
    *,
    now: str,
    until: str,
    authority,
    revocation: Callable[[str, str], str],
) -> dict[str, Any]:
    permission = records.get(permission_hash, "privacy_permission")
    b.require(
        permission["decision"] == "PERMITTED"
        and permission["valid_from"] <= now <= until < permission["valid_until"],
        "PERMISSION_UNRESOLVED",
    )
    arrangement = records.get(permission["arrangement_sha256"], "privacy_arrangement")
    b.require(
        b.digest(arrangement["facts"]) == arrangement["facts_inventory_sha256"],
        "PERMISSION_UNRESOLVED",
    )
    for field in (
        "facts_inventory_sha256",
        "service_view_record_sha256",
        "data_categories_record_sha256",
    ):
        records.raw(arrangement[field])
    names = b.TYPES["PrivacyName"]["enum"]
    b.require(
        len(arrangement["facts"]) == len(names)
        and sorted(x["name"] for x in arrangement["facts"]) == sorted(names),
        "PERMISSION_UNRESOLVED",
    )
    for fact in arrangement["facts"]:
        b.require(
            fact["status"] == "DOCUMENTED" and fact["record_sha256"] is not None,
            "PERMISSION_UNRESOLVED",
        )
        records.raw(fact["record_sha256"])
    for field in (
        "source_permission_record_sha256",
        "controller_role_record_sha256",
        "operator_role_record_sha256",
    ):
        b.require(arrangement[field] is not None, "PERMISSION_UNRESOLVED")
        records.raw(arrangement[field])
    for field in (
        "controller_decision_sha256",
        "source_licence_review_sha256",
        "institutional_privacy_security_review_sha256",
        "project_boundary_review_sha256",
        "revocation_check_record_sha256",
    ):
        records.raw(permission[field])
        authority.require(field, permission[field], permission)
    current = revocation(permission_hash, now)
    records.raw(current)
    authority.require(
        "permission_current",
        current,
        {"permission": permission, "now": now, "until": until},
    )
    authority.require(
        "privacy_permission",
        permission_hash,
        {"permission": permission, "arrangement": arrangement},
    )
    return permission


def facts(
    records: Records, inventory_hash: str, authority
) -> dict[str, dict[str, Any]]:
    inventory = records.get(inventory_hash, "evidence_inventory")
    b.require(
        inventory["source_record_hashes"]
        == sorted(set(inventory["source_record_hashes"]))
        and inventory["authority_review_hashes"]
        == sorted(set(inventory["authority_review_hashes"])),
        "B2_INVENTORY_INVALID",
    )
    for h in [
        *inventory["source_record_hashes"],
        inventory["omissions_record_sha256"],
        inventory["coverage_contract_sha256"],
    ]:
        records.raw(h)
    reviews = {}
    for h in inventory["authority_review_hashes"]:
        record = records.get(h, "authority_review")
        subject = record["subject_record_sha256"]
        b.require(subject not in reviews, "B2_INVENTORY_INVALID")
        reviews[subject] = h
    result = {}
    last = None
    for fact in inventory["facts"]:
        key = (
            fact["category"],
            fact["subject"],
            fact["as_of_start"] or "",
            fact["status"],
        )
        b.require(last is None or last < key, "B2_INVENTORY_INVALID")
        last = key
        b.require(fact["subject"] not in result, "B2_INVENTORY_INVALID")
        available = fact["status"] in ("OPERATOR_REPORTED", "INDEPENDENTLY_CHECKED")
        b.require((fact["value"] is not None) == available, "B2_FACT_INVALID")
        if fact["precision"] == "UNKNOWN":
            b.require(
                fact["as_of_start"] is fact["as_of_end"] is None, "B2_FACT_INVALID"
            )
        else:
            b.require(
                fact["as_of_start"] is not None
                and fact["as_of_end"] is not None
                and fact["as_of_start"] <= fact["as_of_end"],
                "B2_FACT_INVALID",
            )
            if fact["precision"] == "INSTANT":
                b.require(fact["as_of_start"] == fact["as_of_end"], "B2_FACT_INVALID")
            if fact["precision"] == "DATE":
                start = b.stamp(fact["as_of_start"])
                end = b.stamp(fact["as_of_end"])
                b.require(
                    start.hour == start.minute == start.second == start.microsecond == 0
                    and end == start + timedelta(days=1) - timedelta(microseconds=1),
                    "B2_FACT_INVALID",
                )
        if fact["status"] == "OPERATOR_REPORTED":
            h = fact["correspondence_sha256"]
            b.require(h in reviews, "AUTHORITY_UNRESOLVED")
            attribution(records, h, reviews[h], authority)
            source = records.get(h, "correspondence")
            b.require(
                (source["statement_utc"] is None) != (source["statement_date"] is None),
                "B2_CORRESPONDENCE_INVALID",
            )
            if source["statement_date"] is not None:
                b.require(
                    re.fullmatch(r"\d{4}-\d\d-\d\d", source["statement_date"])
                    is not None,
                    "B2_CORRESPONDENCE_INVALID",
                )
            b.require(
                "://" not in source["source_locator"]
                and ".." not in Path(source["source_locator"]).parts,
                "B2_UNSAFE_LOCATOR",
            )
            records.raw(source["retained_record_sha256"])
        elif fact["status"] == "INDEPENDENTLY_CHECKED":
            b.require(fact["check_receipt_sha256"] is not None, "B2_FACT_INVALID")
            records.raw(fact["check_receipt_sha256"])
            authority.require("independent_fact", fact["check_receipt_sha256"], fact)
        if available and fact["value"]["kind"] == "COUNT":
            b.require(
                re.fullmatch(r"0|[1-9][0-9]*", fact["value"]["decimal"]) is not None,
                "B2_FACT_INVALID",
            )
        result[fact["subject"]] = fact
    authority.require(
        "evidence_coverage", inventory["coverage_contract_sha256"], inventory
    )
    return result


def observation(records, observation_hash, plan_hash, segment_nonce, phase, authority):
    obs = records.get(observation_hash, "window_observation")
    plan = records.get(plan_hash, "window_plan")
    b.require(
        obs["window_plan_sha256"] == plan_hash
        and obs["segment_nonce"] == segment_nonce
        and obs["phase"] == phase
        and obs["observed_from"] <= obs["observed_until"] <= obs["acquired_utc"],
        "OBSERVATION_CONTRACT_FAILURE",
    )
    attribution(
        records, obs["correspondence_sha256"], obs["authority_review_sha256"], authority
    )
    authority.require(
        "observation_interpretation", obs["interpretation_review_sha256"], obs
    )
    values = facts(records, obs["inventory_sha256"], authority)
    b.require(
        plan["required_comparison_subjects"]
        == sorted(set(plan["required_comparison_subjects"]))
        and REQUIRED_SUBJECTS <= set(plan["required_comparison_subjects"]),
        "B2_COMPARISON_FIELDS",
    )
    for subject in plan["required_comparison_subjects"]:
        b.require(subject in values, "PREFLIGHT_MISSING")
        fact = values[subject]
        b.require(
            fact["status"] in ("OPERATOR_REPORTED", "INDEPENDENTLY_CHECKED")
            and fact["precision"] != "UNKNOWN"
            and obs["observed_from"]
            <= fact["as_of_start"]
            <= fact["as_of_end"]
            <= obs["observed_until"],
            "PREFLIGHT_MISSING",
        )
    return obs, values


def compare_observed_fields(
    records, left_inventory, right_inventory, window_hash, authority
):
    """Equality of declared fields only, never continuous-state verification."""
    window = records.get(window_hash, "window_plan")
    left, right = (
        facts(records, left_inventory, authority),
        facts(records, right_inventory, authority),
    )
    for subject in window["required_comparison_subjects"]:
        b.require(subject in left and subject in right, "PREFLIGHT_MISSING")
        a, z = left[subject], right[subject]
        b.require(
            a["status"] in ("OPERATOR_REPORTED", "INDEPENDENTLY_CHECKED")
            and z["status"] in ("OPERATOR_REPORTED", "INDEPENDENTLY_CHECKED")
            and a["precision"] != "UNKNOWN"
            and z["precision"] != "UNKNOWN",
            "PREFLIGHT_MISSING",
        )
        b.require(
            (a["category"], a["value"], a["precision"])
            == (z["category"], z["value"], z["precision"]),
            "RECORD_DISCREPANCY",
        )


class Gate:
    """Rechecks changing authority at admission and emission, never issues it."""

    def __init__(
        self,
        records: Records,
        authority,
        *,
        population_scope: str,
        clock,
        window_hash: str,
        permission_hash: str,
        scientific_hash: str,
        interpretation_hash: str,
        revocation: Callable,
        window_state: Callable,
        binding_hash: str,
        selection_hash: str,
    ):
        b.validate_type(population_scope, "PopulationScope")
        self.records, self.authority, self.scope, self.clock = (
            records,
            authority,
            population_scope,
            clock,
        )
        (
            self.window_hash,
            self.permission_hash,
            self.scientific_hash,
            self.interpretation_hash,
        ) = window_hash, permission_hash, scientific_hash, interpretation_hash
        self.revocation = revocation
        self.window_state = window_state
        self.binding_hash = binding_hash
        self.selection_hash = selection_hash
        self.slot = None
        self.closed = False
        self.notice = None
        self.first_emitted = False
        self.emission_lock = threading.Lock()
        self.preflight_hash = self.segment_nonce = None

    def require(self, purpose, evidence_sha256, context):
        self.authority.require(purpose, evidence_sha256, context)
        if purpose == "prior_segment_closure":
            self.reconcile_closures([evidence_sha256])
        elif purpose == "campaign_closure":
            self.reconcile_closures(context["ordered_segment_closure_hashes"])
        elif purpose == "window_closure":
            self.reconcile_closures(
                h
                for campaign in context["ordered_campaign_closure_hashes"]
                for h in self.records.get(campaign, "campaign_closure")[
                    "ordered_segment_closure_hashes"
                ]
            )
        if purpose in (
            "protected_input",
            "dispatch",
            "emission",
            "segment_open",
            "publication",
            "administrative_acquisition",
            "closure",
        ):
            self.check()

    def check(self):
        b.require(self.notice is None, "OBSERVATION_CONTRACT_FAILURE")
        if self.scope == b.DEVELOPMENT:
            from ...execution_policy import require_goethe_nhr_slurm

            require_goethe_nhr_slurm("stage12 observational DEVELOPMENT")
        plan = self.records.get(self.window_hash, "window_plan")
        now = self.clock.utc()
        b.require(
            plan["dispatch_from"] < plan["dispatch_until"] < plan["closure_deadline"]
            and now <= plan["closure_deadline"],
            "WINDOW_EXPIRED",
        )
        b.require(
            plan["privacy_permission_sha256"] == self.permission_hash
            and plan["scientific_decision_sha256"] == self.scientific_hash,
            "B2_WINDOW_BINDING",
        )
        decision = self.records.get(self.scientific_hash, "scientific_decision")
        b.require(
            decision["decision"] == "ADOPT_CONDITIONAL"
            and decision["amendment_sha256"] == b.AMENDMENT_SHA256
            and decision["schema_spec_sha256"] == b.SPEC_SHA256,
            "B2_SCIENCE_UNADOPTED",
        )
        self.authority.require("scientific_decision", self.scientific_hash, decision)
        for field in ("accepted_limitations_sha256", "owner_delegation_sha256"):
            self.records.raw(decision[field])
        attribution(
            self.records,
            plan["operator_arrangement_sha256"],
            plan["authority_review_sha256"],
            self.authority,
        )
        privacy(
            self.records,
            self.permission_hash,
            now=now,
            until=plan["closure_deadline"],
            authority=self.authority,
            revocation=self.revocation,
        )
        interpretation = self.records.get(
            self.interpretation_hash, "response_interpretation"
        )
        from . import s12_assets, s12_response

        b.require(
            interpretation["materialization_sha256"]
            == s12_assets.hashes()[c.MATERIALIZATION].hex()
            and interpretation["validation_sha256"]
            == s12_assets.hashes()[s12_response.VALIDATION].hex(),
            "B2_INTERPRETATION_INVALID",
        )
        for field, h in interpretation.items():
            if field != "schema_version":
                self.records.raw(h)
        self.authority.require(
            "response_interpretation", self.interpretation_hash, interpretation
        )
        return plan

    def admit(self, preflight_hash, segment_nonce):
        plan = self.check()
        obs, _ = observation(
            self.records,
            preflight_hash,
            self.window_hash,
            segment_nonce,
            "PREFLIGHT",
            self.authority,
        )
        now = self.clock.utc()
        binding = self.records.get(self.binding_hash, "observation_binding")
        compare_observed_fields(
            self.records,
            binding["initial_evidence_inventory_sha256"],
            obs["inventory_sha256"],
            self.window_hash,
            self.authority,
        )
        predecessor = getattr(self, "predecessor_closure", None)
        if predecessor is not None:
            prior = self.records.get(predecessor, "segment_closure")
            b.require(
                prior["window_plan_sha256"] == self.window_hash
                and prior["disposition"] == "CLOSED_OBSERVATIONAL"
                and prior["postflight_sha256"] is not None,
                "CLOSURE_MISSING",
            )
            post = self.records.get(prior["postflight_sha256"], "window_observation")
            compare_observed_fields(
                self.records,
                post["inventory_sha256"],
                obs["inventory_sha256"],
                self.window_hash,
                self.authority,
            )
        b.require(
            plan["dispatch_from"] <= now < plan["dispatch_until"]
            and obs["observed_until"] <= now
            and 0
            <= (b.stamp(now) - b.stamp(obs["observed_from"])).total_seconds() * 1000
            <= plan["preflight_max_age_ms"],
            "PREFLIGHT_MISSING",
        )
        self.preflight_hash, self.segment_nonce = preflight_hash, segment_nonce
        self.first_emitted = False

    def before_dispatch(self):
        b.require(self.preflight_hash is not None, "PREFLIGHT_MISSING")
        # Only first-dispatch age applies per segment; every dispatch still checks
        # current permission/window/notices. No periodic service-state claim.
        plan = self.check()
        now = self.clock.utc()
        b.require(
            plan["dispatch_from"] <= now < plan["dispatch_until"], "WINDOW_EXPIRED"
        )
        if self.slot is not None:
            b.require(
                self.slot["dispatch_from"] <= now < self.slot["dispatch_until"],
                "B2_SEGMENT_EXPIRED",
            )
        status = self.window_state(self.window_hash)
        b.require(
            set(status) == {"state", "evidence_sha256"}
            and status["state"] == "OPEN"
            and not self.closed,
            "WINDOW_CLOSED",
        )
        self.records.raw(status["evidence_sha256"])
        self.authority.require(
            "window_open",
            status["evidence_sha256"],
            {"window_plan_sha256": self.window_hash},
        )
        with self.emission_lock:
            if not self.first_emitted:
                obs = self.records.get(self.preflight_hash, "window_observation")
                b.require(
                    0
                    <= (b.stamp(now) - b.stamp(obs["observed_from"])).total_seconds()
                    * 1000
                    <= plan["preflight_max_age_ms"],
                    "PREFLIGHT_MISSING",
                )

    def emitted(self):
        with self.emission_lock:
            self.first_emitted = True

    def validate_campaign(self, start, plan, admission):
        self.predecessor_closure = admission["predecessor_closure_sha256"]
        window = self.check()
        binding = self.records.get(self.binding_hash, "observation_binding")
        b.require(
            b.binding_id(binding).hex() == start["observation_binding_id"]
            and binding["window_plan_sha256"] == self.window_hash
            and binding["response_interpretation_sha256"] == self.interpretation_hash,
            "B2_OBSERVATION_BINDING",
        )
        b.require(
            start["window_plan_sha256"] == self.window_hash
            and start["privacy_permission_sha256"] == self.permission_hash
            and start["scientific_decision_sha256"] == self.scientific_hash
            and start["response_interpretation_sha256"] == self.interpretation_hash,
            "B2_WINDOW_BINDING",
        )
        b.require(
            window["dispatch_from"]
            <= plan["window_start"]
            < plan["window_end"]
            <= window["dispatch_until"],
            "B2_WINDOW_BINDING",
        )
        self.authority.require(
            "exact_window_workload",
            start["initial_workload_authority_sha256"],
            {"plan": plan, "window": window, "admission": admission},
        )
        facts(
            self.records, binding["initial_evidence_inventory_sha256"], self.authority
        )

    def reconcile_closures(self, closure_hashes):
        baseline = self.records.get(self.binding_hash, "observation_binding")[
            "initial_evidence_inventory_sha256"
        ]
        previous = baseline
        for h in closure_hashes:
            closure = self.records.get(h, "segment_closure")
            b.require(
                closure["window_plan_sha256"] == self.window_hash
                and closure["postflight_sha256"] is not None
                and closure["disposition"] == "CLOSED_OBSERVATIONAL",
                "CLOSURE_MISSING",
            )
            pre, _ = observation(
                self.records,
                closure["preflight_sha256"],
                self.window_hash,
                closure["segment_nonce"],
                "PREFLIGHT",
                self.authority,
            )
            post, _ = observation(
                self.records,
                closure["postflight_sha256"],
                self.window_hash,
                closure["segment_nonce"],
                "POSTFLIGHT",
                self.authority,
            )
            compare_observed_fields(
                self.records,
                previous,
                pre["inventory_sha256"],
                self.window_hash,
                self.authority,
            )
            compare_observed_fields(
                self.records,
                baseline,
                post["inventory_sha256"],
                self.window_hash,
                self.authority,
            )
            previous = post["inventory_sha256"]

    def validate_workload(self, catalog, profile, plan, works, admission, scratch):
        from . import s12_b2_planning as planning

        selection, _ = planning.load_selection(
            self.records,
            self.selection_hash,
            catalog,
            authority=self.authority,
            scratch=scratch,
        )
        self.slot = planning.verify_workload(
            self.records,
            self.selection_hash,
            selection,
            catalog,
            plan,
            works,
            admission,
            authority=self.authority,
        )
        b.require(
            self.slot["administrative_bounds"] == profile["administrative"],
            "B2_ADMIN_BOUND",
        )

    def interrupt(self, notice_hash):
        self.records.raw(notice_hash)
        self.notice = notice_hash

    def segment_closure(
        self,
        closure_hash,
        *,
        start_hash,
        attempt_inventory,
        controller_reconciliation,
        resource_report,
        last_response_utc,
        predecessor=None,
    ):
        plan = self.check()
        x = self.records.get(closure_hash, "segment_closure")
        b.require(
            x["window_plan_sha256"] == self.window_hash
            and x["segment_nonce"] == self.segment_nonce
            and x["campaign_start_sha256"] == start_hash
            and x["preflight_sha256"] == self.preflight_hash
            and x["predecessor_closure_sha256"] == predecessor,
            "OBSERVATION_CONTRACT_FAILURE",
        )
        b.require(
            x["attempt_inventory_sha256"] == attempt_inventory
            and x["controller_reconciliation_sha256"] == controller_reconciliation
            and x["resource_report_sha256"] == resource_report,
            "OBSERVATION_CONTRACT_FAILURE",
        )
        b.require(
            x["postflight_sha256"] is not None
            and x["operator_account_sha256"] is not None
            and x["account_status"] == "NO_KNOWN_INTERVENTION"
            and x["comparison"] == "REPORTED_FIELDS_AGREE"
            and x["disposition"] == "CLOSED_OBSERVATIONAL"
            and x["reviewed_utc"] <= plan["closure_deadline"],
            "CLOSURE_MISSING",
        )
        pre, pv = observation(
            self.records,
            x["preflight_sha256"],
            self.window_hash,
            self.segment_nonce,
            "PREFLIGHT",
            self.authority,
        )
        post, qv = observation(
            self.records,
            x["postflight_sha256"],
            self.window_hash,
            self.segment_nonce,
            "POSTFLIGHT",
            self.authority,
        )
        b.require(
            post["observed_from"] >= last_response_utc, "OBSERVATION_CONTRACT_FAILURE"
        )
        for subject in plan["required_comparison_subjects"]:
            b.require(
                (
                    pv[subject]["category"],
                    pv[subject]["value"],
                    pv[subject]["precision"],
                )
                == (
                    qv[subject]["category"],
                    qv[subject]["value"],
                    qv[subject]["precision"],
                ),
                "RECORD_DISCREPANCY",
            )
        if predecessor is not None:
            b.require(x["gap_account_sha256"] is not None, "CLOSURE_MISSING")
            self.records.raw(x["gap_account_sha256"])
            self.authority.require("gap_account", x["gap_account_sha256"], x)
        self.records.raw(x["operator_account_sha256"])
        self.authority.require(
            "operator_segment_account", x["operator_account_sha256"], x
        )
        self.authority.require("segment_closure", x["review_decision_sha256"], x)
        return x


def acquire(
    records: Records,
    raw_factory: Callable[[], tuple[Callable[[], bytes], ...]],
    *,
    writer,
    clock,
    campaign_id,
    segment_nonce,
    epoch_id,
    bounds,
    authority,
    authority_hash,
    ordinal,
    secret_guard,
    predecessor_begin=None,
):
    """One bounded local administrative transaction; durable begin before reads.

    Unexpected interruption leaves the begin with no finish: unknown spending,
    no dispatch. The bootstrap reconciler must preserve and block that state.
    """
    b.validate_type(bounds, "AdministrativeBounds")
    b.uint(ordinal, True)
    authority.require("administrative_acquisition", authority_hash, bounds)
    begin = {
        "schema_version": version("evidence_acquisition_begin"),
        "campaign_id": campaign_id,
        "segment_nonce": segment_nonce,
        "epoch_id": epoch_id,
        "cumulative_ordinal": ordinal,
        "predecessor_begin_sha256": predecessor_begin,
        "acquisition_contract_sha256": bounds["acquisition_contract_sha256"],
        "authority_sha256": authority_hash,
        "bounds": bounds,
        "started_mono_ns": clock.now_ns(),
        "started_utc": clock.utc(),
        "state": "IN_PROGRESS",
    }
    b.validate(begin)
    begin_raw = b.canonical(begin)
    begin_hash = b.digest(begin)
    writer.call(
        lambda: io.write(writer.root / f"admin_{ordinal:020d}_begin.json", begin_raw)
    )
    retain = lambda raw: records.put(
        raw,
        owner=writer.assert_owner,
        secret_guard=lambda body: authority.require(
            "nonsecret_record", b.sha(body).hex(), {}
        ),
    )
    writer.call(lambda: retain(begin_raw))
    hashes = []
    total = 0
    outcome = "ACQUIRED"
    try:
        loaders = raw_factory()
        b.require(
            type(loaders) is tuple
            and 0 < len(loaders) <= bounds["max_records"]
            and all(callable(x) for x in loaders),
            "B2_ADMIN_FINITE_BUNDLE_REQUIRED",
        )
        for load in loaders:
            elapsed = (clock.now_ns() - begin["started_mono_ns"] + 999999) // 1000000
            b.require(
                total < bounds["max_total_bytes"]
                and elapsed < bounds["max_duration_ms"],
                "B2_ADMIN_BUDGET",
            )
            raw = load()
            b.require(type(raw) is bytes, "B2_ADMIN_BYTES_REQUIRED")
            total = b.uint(total + len(raw))
            elapsed = (clock.now_ns() - begin["started_mono_ns"] + 999999) // 1000000
            b.require(
                len(hashes) < bounds["max_records"]
                and len(raw) <= bounds["max_record_bytes"]
                and total <= bounds["max_total_bytes"]
                and elapsed <= bounds["max_duration_ms"],
                "B2_ADMIN_BUDGET",
            )
            # The authority supplies a no-secret validation contract, not a raw
            # credential. It may reject any unsafe diagnostic body.
            secret_guard(raw)
            authority.require(
                "administrative_record", b.sha(raw).hex(), {"bytes": len(raw)}
            )
            hashes.append(
                writer.call(
                    lambda raw=raw: records.put(
                        raw,
                        owner=writer.assert_owner,
                        secret_guard=lambda body: authority.require(
                            "nonsecret_record", b.sha(body).hex(), {}
                        ),
                    )
                )
            )
    except c.Stage12Error:
        outcome = "FAILED"
    finished = clock.now_ns()
    elapsed = (finished - begin["started_mono_ns"] + 999999) // 1000000
    if elapsed > bounds["max_duration_ms"] or total > bounds["max_total_bytes"]:
        outcome = "BUDGET_EXHAUSTED"
    end = {
        "schema_version": version("evidence_acquisition"),
        "scope": "DEVELOPMENT_ONLY",
        "acquisition_contract_sha256": bounds["acquisition_contract_sha256"],
        "authority_sha256": authority_hash,
        "records": hashes,
        "total_bytes": total,
        "elapsed_ms": elapsed,
        "outcome": outcome,
        "attempt_id": ordinal,
        "begun_utc": begin["started_utc"],
        "finished_utc": clock.utc(),
        "begin_sha256": begin_hash,
        "epoch_id": epoch_id,
        "finished_mono_ns": finished,
    }
    b.validate(end)
    writer.call(
        lambda: io.write(
            writer.root / f"admin_{ordinal:020d}_finish.json", b.canonical(end)
        )
    )
    writer.call(lambda: retain(b.canonical(end)))
    return begin, end


def campaign_closure(
    records, closure_hash, *, plan, start, segments, authority, population_scope
):
    x = records.get(closure_hash, "campaign_closure")
    b.require(
        x["window_plan_sha256"] == plan["window_plan_sha256"]
        and x["campaign_start_sha256"] == b.digest(start)
        and x["workload_sha256"] == b.digest(plan)
        and x["workload_kind"] == plan["workload_kind"]
        and x["ordered_segment_closure_hashes"] == segments
        and bool(segments),
        "B2_CAMPAIGN_CLOSURE",
    )
    b.require(
        x["disposition"] == "CLOSED_OBSERVATIONAL"
        and x["account_status"] == "NO_KNOWN_INTERVENTION"
        and x["operator_campaign_account_sha256"] is not None,
        "CLOSURE_MISSING",
    )
    window = records.get(x["window_plan_sha256"], "window_plan")
    b.require(x["reviewed_utc"] <= window["closure_deadline"], "CLOSURE_MISSING")
    previous = None
    for h in segments:
        s = records.get(h, "segment_closure")
        b.require(
            s["campaign_start_sha256"] == b.digest(start)
            and s["window_plan_sha256"] == x["window_plan_sha256"]
            and s["predecessor_closure_sha256"] == previous
            and s["disposition"] == "CLOSED_OBSERVATIONAL"
            and s["account_status"] == "NO_KNOWN_INTERVENTION",
            "B2_CAMPAIGN_CLOSURE",
        )
        previous = h
    if population_scope == b.DEVELOPMENT and x["workload_kind"] in (
        "FULL_C",
        "DIRECT_N",
    ):
        b.require(
            plan["budgets"]["data_observations"] == 105805,
            "B2_ACCEPTED_POPULATION_REQUIRED",
        )
    records.raw(x["operator_campaign_account_sha256"])
    authority.require(
        "operator_campaign_account", x["operator_campaign_account_sha256"], x
    )
    authority.require("campaign_closure", x["review_decision_sha256"], x)
    return x


def window_closure(records, closure_hash, *, window_hash, campaigns, authority):
    x = records.get(closure_hash, "window_closure")
    window = records.get(window_hash, "window_plan")
    b.require(
        x["window_plan_sha256"] == window_hash
        and x["ordered_campaign_closure_hashes"] == campaigns
        and len(campaigns) == len(set(campaigns))
        and bool(campaigns)
        and x["disposition"] == "CLOSED_OBSERVATIONAL"
        and x["account_status"] == "NO_KNOWN_INTERVENTION"
        and x["operator_campaign_account_sha256"] is not None
        and x["reviewed_utc"] <= window["closure_deadline"],
        "CLOSURE_MISSING",
    )
    schedule = records.get(window["planned_segment_plan_sha256"], "window_segment_plan")
    planned = schedule["planned_campaigns"]
    b.require(
        schedule["calibration_plan_sha256"] == window["calibration_plan_sha256"]
        and [p["intent_id"] for p in planned] == list(range(1, len(planned) + 1)),
        "B2_WINDOW_PLAN",
    )
    required = [p for p in planned if p["conditional_on"] == "REQUIRED"]
    optional = [p for p in planned if p["conditional_on"] != "REQUIRED"]
    b.require(
        len(optional) == 1
        and optional[0]["workload_kind"] == "DIRECT_N"
        and planned == required + optional
        and len(campaigns) in (len(required), len(planned)),
        "B2_WINDOW_TOTALITY",
    )
    for h, intent in zip(campaigns, planned, strict=False):
        campaign = records.get(h, "campaign_closure")
        b.require(
            campaign["window_plan_sha256"] == window_hash
            and campaign["disposition"] == "CLOSED_OBSERVATIONAL"
            and campaign["account_status"] == "NO_KNOWN_INTERVENTION",
            "B2_WINDOW_CLOSURE",
        )
        plan = records.get(campaign["workload_sha256"])
        b.require(
            plan["workload_kind"] == intent["workload_kind"]
            and plan["repetition"] == intent["repetition"]
            and plan["result_limit"] in intent["candidate_limits"]
            and plan["budgets"]["data_observations"] == intent["planned_data"]
            and plan["population_scope"] == schedule["population_scope"],
            "B2_WINDOW_TOTALITY",
        )
    authority.require(
        "operator_window_account", x["operator_campaign_account_sha256"], x
    )
    authority.require("window_closure", x["review_decision_sha256"], x)
    return x


def append_administration(
    records, *, previous_hash, begin, finish, plan, authority_hash, writer
):
    previous = (
        records.get(previous_hash, "bootstrap_administration")
        if previous_hash
        else None
    )
    spent = (
        dict(previous["spent"])
        if previous
        else {"operations": 0, "duration_ms": 0, "bytes": 0}
    )
    spent["operations"] += 1
    spent["duration_ms"] += finish["elapsed_ms"]
    spent["bytes"] += finish["total_bytes"]
    obj = {
        "schema_version": version("bootstrap_administration"),
        "campaign_id": begin["campaign_id"],
        "segment_nonce": begin["segment_nonce"],
        "plan_sha256": b.digest(plan),
        "predecessor_bootstrap_sha256": previous_hash,
        "authority_sha256": authority_hash,
        "attempts": [
            {
                "cumulative_ordinal": begin["cumulative_ordinal"],
                "begin_sha256": b.digest(begin),
                "finish_sha256": b.digest(finish),
            }
        ],
        "spent": spent,
        "status": "SEALED" if finish["outcome"] == "ACQUIRED" else "INCOMPLETE",
    }
    b.validate(obj)
    return writer.call(
        lambda: records.put(
            b.canonical(obj), owner=writer.assert_owner, secret_guard=lambda raw: None
        )
    )


def release_authority(records, h, *, campaign_id, segment_nonce, now, authority):
    x = records.get(h, "writer_release_authority")
    b.require(
        x["campaign_id"] == campaign_id
        and x["segment_nonce"] == segment_nonce
        and x["valid_from"] <= now < x["valid_until"],
        "B2_WRITER_UNCERTAIN",
    )
    records.raw(x["issuer_delegation_sha256"])
    authority.require("writer_release", h, x)
    return x

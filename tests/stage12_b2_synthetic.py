"""Invented B2 fixtures. No fixture record is an institutional permission."""

from __future__ import annotations
import json
from pathlib import Path
from dataclasses import replace
from datetime import datetime, timezone

from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_catalog as catalog
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_pipeline as pipeline
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_evidence as evidence
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s11_semantic_contract as s11
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as s10
from safe_geocoding_pipeline.preprocessing.stages import s12_assets as assets
from safe_geocoding_pipeline.preprocessing.stages import s12_response as response
from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_operations_v2 import (
    FakeClock,
    inputs as public_inputs,
    offline,
)
from stage12_synthetic import body, feature

H = b.sha(b"B2 SYNTHETIC ONLY, NO AUTHORITY OR INSTITUTIONAL PERMISSION").hex()
KEY = b"B2_SYNTHETIC_CANARY_NOT_A_CREDENTIAL"


class Authority:
    def __init__(self):
        self.reject = None

    def supported_size(self, digest):
        self.require("supported_size", digest, {})
        return 40

    def require(self, purpose, digest, context):
        b.require(
            purpose != self.reject and isinstance(digest, str) and len(digest) == 64,
            "SYNTHETIC_AUTHORITY_REJECTED",
        )
        b.require(
            context.get("population_scope") != b.DEVELOPMENT,
            "SYNTHETIC_CANNOT_AUTHORIZE_DEVELOPMENT",
        )


class SyntheticGate:
    """Test-only boundary adapter; actual Gate permission logic has separate tests."""

    def __init__(self, records, clock):
        self.records, self.clock, self.authority = records, clock, Authority()
        self.scope = b.SYNTHETIC
        self.closed = False
        self.notice = None

    def require(self, *args):
        self.authority.require(*args)
        self.check()

    def check(self):
        b.require(
            not self.closed and self.notice is None, "OBSERVATION_CONTRACT_FAILURE"
        )
        return {}

    def admit(self, preflight, nonce):
        self.preflight_hash, self.segment_nonce = preflight, nonce
        self.check()

    def before_dispatch(self):
        self.check()

    def emitted(self):
        pass

    def validate_campaign(self, *args):
        self.check()

    def validate_workload(self, *args):
        self.check()

    def interrupt(self, h):
        self.notice = h

    def segment_closure(self, h, **kwargs):
        x = self.records.get(h, "segment_closure")
        b.require(x["disposition"] == "CLOSED_OBSERVATIONAL", "CLOSURE_MISSING")
        return x


class World:
    def __init__(self, root: Path, count=2):
        root.chmod(0o700)
        self.root = root
        io.reserve(root / "records")
        self.records = evidence.Records(root / "records")
        self.clock = FakeClock()
        self.gate = SyntheticGate(self.records, self.clock)
        self.counter = 0
        self.count = count
        self.catalog = self.build_catalog(count)
        io.write(
            self.records.root / (H + ".json"),
            b"B2 SYNTHETIC ONLY, NO AUTHORITY OR INSTITUTIONAL PERMISSION",
        )
        from safe_geocoding_pipeline.preprocessing.stages import (
            s12_b2_calibration as cal,
            s12_b2_planning as planning,
        )

        selected = cal.select(
            self.catalog,
            root / "initial_selection.sqlite",
            C=5,
            T=12,
            supported=40,
            authority=self.gate,
            decision_hash=H,
        )
        core = planning.seal_core(
            self.records,
            selected,
            self.catalog,
            lineage_hash=H,
            capability_hash=H,
            decision_hash=H,
            owner=lambda: None,
            secret_guard=lambda raw: response.secret_guard(raw, KEY),
        )
        core_obj = self.records.get(core, "calibration_plan")
        self.acquisition_hash = self.put(
            {
                "schema_version": "stage12_bounded_acquisition_contract_b2_v1",
                "scope": "DEVELOPMENT_ONLY",
                "preflight": {
                    "max_records": 40,
                    "max_record_bytes": 65536,
                    "max_total_bytes": 262144,
                    "max_duration_ms": 1000,
                },
                "postflight": {
                    "max_records": 40,
                    "max_record_bytes": 65536,
                    "max_total_bytes": 262144,
                    "max_duration_ms": 1000,
                },
            }
        )
        admin = {
            "max_records": 40,
            "max_record_bytes": 65536,
            "max_total_bytes": 1048576,
            "max_duration_ms": 10000,
            "acquisition_contract_sha256": self.acquisition_hash,
        }
        intents = []
        for i, x in enumerate(selected["intents"], 1):
            intents.append(
                {
                    "intent_id": i,
                    "workload_kind": x["kind"],
                    "repetition": x["repetition"],
                    "result_limit": x["size"],
                    "candidate_limits": [x["size"]],
                    "subset_inventory_sha256": o.manifest_digest(
                        r["query_semantic_id"].hex() for r in self.catalog.semantics()
                    )
                    if x["subset"] is None
                    else core_obj["tail_inventory_sha256"]
                    if x["kind"] == "TAIL"
                    else core_obj["paired_inventory_sha256"],
                    "planned_data": x["count"],
                    "conditional_on": "REQUIRED",
                    "segment_slots": [
                        {
                            "slot_id": j,
                            "dispatch_from": "2026-01-01T00:00:00.000000Z",
                            "dispatch_until": "2026-01-02T00:00:00.000000Z",
                            "max_attempts": 5 * x["count"],
                            "administrative_bounds": admin,
                        }
                        for j in (1, 2)
                    ],
                }
            )
        intents.append(
            {
                **intents[0],
                "intent_id": len(intents) + 1,
                "workload_kind": "DIRECT_N",
                "result_limit": None,
                "candidate_limits": selected["grid"],
                "conditional_on": "ONLY_IF_SELECTED_N_DIFFERS_FROM_C",
            }
        )
        segment_plan = self.put(
            {
                "schema_version": "stage12_window_segment_plan_b2_v1",
                "population_scope": b.SYNTHETIC,
                "calibration_plan_sha256": core,
                "planned_campaigns": intents,
            }
        )
        self.window_hash = self.put(
            {
                "schema_version": "stage12_window_plan_b2_v1",
                "window_nonce": self.nonce(),
                "service_view_record_sha256": H,
                "operator_arrangement_sha256": H,
                "authority_review_sha256": H,
                "dispatch_from": "2026-01-01T00:00:00.000000Z",
                "dispatch_until": "2026-01-02T00:00:00.000000Z",
                "preflight_max_age_ms": 60000,
                "closure_deadline": "2026-01-03T00:00:00.000000Z",
                "required_comparison_subjects": sorted(evidence.REQUIRED_SUBJECTS),
                "notice_procedure_sha256": H,
                "planned_segment_plan_sha256": segment_plan,
                "calibration_plan_sha256": core,
                "privacy_permission_sha256": H,
                "scientific_decision_sha256": H,
                "limitations_sha256": H,
            }
        )
        self.selection_hash = planning.bind_window(
            self.records,
            core,
            self.window_hash,
            owner=lambda: None,
            secret_guard=lambda raw: response.secret_guard(raw, KEY),
        )
        self.selection = selected
        self.runtime = {"scope": b.SYNTHETIC, "source": "invented B2 offline runtime"}
        self.rules = pipeline.ResponseRules(
            frozenset({"address", "street", "locality"}),
            frozenset({"synthetic"}),
            lambda work: {},
            H,
        )

    def put(self, obj):
        raw = b.canonical(obj)
        h = b.sha(raw).hex()
        path = self.records.root / (h + ".json")
        if not path.exists():
            io.write(path, raw)
        return h

    def nonce(self):
        self.counter += 1
        return b.sha(b"SYNTHETIC_NONCE" + str(self.counter).encode()).hex()

    def build_catalog(self, count):
        semantics = []
        contexts = []
        hypotheses = []
        mapping = []
        families = []
        for i in range(count):
            source = b.sha(f"synthetic source {i}".encode())
            u = b.sha(f"synthetic context {i}".encode())
            h = b.sha(f"synthetic hypothesis {i}".encode())
            intent = s10.full_intent(f"Invented B2 passage {i}", "DE")
            if i % 2:
                intent.update(
                    endpoint="/v1/search/structured",
                    search_mode="STRUCTURED",
                    text=None,
                    address=f"Invented B2 passage {i}",
                    postalcode="00123",
                    locality=None,
                )
            core = s11.project(intent, s10.MODE)
            q = s11.semantic_id(s11.core_bytes(core))
            semantics.append({"query_semantic_id": q, "core": core})
            mapping.append({"hypothesis_id": h, "query_semantic_id": q})
            hypotheses.append(
                {
                    "hypothesis_id": h,
                    "query_context_id": u,
                    "stable_source_row_id_v1": source,
                    "stage08_representation": "STANDARD",
                    "intent": intent,
                    "selection_status": s10.MODE,
                }
            )
            contexts.append(
                {
                    "query_context_id": u.hex(),
                    "stable_source_row_id_v1": source.hex(),
                    "country": "DE",
                    "script": "Latin",
                    "capability": "SYNTHETIC_UNSUPPORTED_REFERENCE",
                    "completeness": [True, False, False, False],
                    "representation": "STANDARD",
                    "channels": [],
                    "origin_sha256": H,
                }
            )
            families.append({"query_context_id": u, "hypothesis_id": h, "family": "Q1"})
        semantics.sort(key=lambda x: x["query_semantic_id"])
        mapping.sort(key=lambda x: x["hypothesis_id"])
        binding = {
            "schema_version": "stage12_stage11_input_binding_b2_v1",
            "population_scope": b.SYNTHETIC,
            "manifest_sha256": H,
            "dataset_sha256": H,
            "semantic_sha256": s11.relation_digest(
                "semantic_request", count, semantics
            ).hex(),
            "map_sha256": s11.relation_digest(
                "hypothesis_request_map", count, mapping
            ).hex(),
            "semantic_count": count,
            "map_count": count,
            "source_count": count,
            "upstream_acceptance_sha256": H,
        }
        return catalog.Catalog.build(
            self.root / "catalog.sqlite",
            binding,
            semantics=lambda: iter(semantics),
            mapping=lambda: iter(mapping),
            hypotheses=lambda: iter(hypotheses),
            contexts=lambda: iter(contexts),
            families=lambda: iter(families),
            authority=Authority(),
        )

    def inputs(self, *, size=5, kind="FULL_C", repetition=0, subset=None):
        public_profile, _, _, _, _ = public_inputs(self.count)
        profile = {
            **public_profile,
            "schema_version": o.PROFILE,
            "scope": o.SCOPE,
            "rule_bundle_sha256": o.RULE_BUNDLE,
            "policy_freeze_record_sha256": H,
            "monitoring": {
                "mode": "OBSERVED_PREPOST_WINDOW",
                "window_plan_sha256": self.window_hash,
                "privacy_permission_sha256": getattr(self.gate, "permission_hash", H),
                "scientific_decision_sha256": getattr(self.gate, "scientific_hash", H),
            },
            "demonstrated_ceiling_sha256": H,
            "administrative": {
                "max_records": 40,
                "max_record_bytes": 65536,
                "max_total_bytes": 1048576,
                "max_duration_ms": 10000,
                "acquisition_contract_sha256": self.acquisition_hash,
            },
        }
        profile["resource_sample_period_ms"] = 100
        profile["resources"].update(
            fixed_campaign_disk_bound_bytes=64 * 1024 * 1024,
            per_attempt_disk_bound_bytes=1024 * 1024,
            allocated_disk_bytes=512 * 1024 * 1024,
            pending_request_bytes=65536,
            writer_guard_ms=10000,
        )
        rows = []
        for semantic in self.catalog.semantics():
            q = semantic["query_semantic_id"].hex()
            if subset is not None and q not in subset:
                continue
            rows.append(
                {
                    "work_id": len(rows) + 1,
                    "block_id": 1,
                    "kind": "DATA",
                    "query_semantic_id": q,
                    "result_limit": size,
                    "repetition": repetition,
                    "recipe_id": None,
                    "retry_spacing_key": q,
                }
            )
        budgets = {
            "data_observations": len(rows),
            "required_control_observations": 0,
            "reserved_control_observations": 0,
            "data_attempts": 5 * len(rows),
            "control_http_attempts": 0,
            "administrative_operations": 40,
            "administrative_duration_ms": 10000,
            "active_duration_ms": 1000000,
            "storage_bytes": 512 * 1024 * 1024,
            "event_count": 20000,
        }
        plan = {
            "schema_version": o.PLAN,
            "scope": o.SCOPE,
            "operations_profile_sha256": b.digest(profile),
            "work_manifest_sha256": o.manifest_digest(rows),
            "control_recipes": [],
            "blocks": [
                {
                    "block_id": 1,
                    "state_id": 1,
                    "first_work_id": 1,
                    "last_work_id": len(rows),
                    "budget": budgets,
                    "fallback_state_ids": [],
                    "transition_from": None,
                }
            ],
            "budgets": budgets,
            "window_start": "2026-01-01T00:00:00.000000Z",
            "window_end": "2026-01-02T00:00:00.000000Z",
            "shutdown_reserve_ms": 80000,
            "selection_basis_sha256": self.selection_hash,
            "stage11_input_binding_sha256": b.digest(self.catalog.binding),
            "window_plan_sha256": self.window_hash,
            "workload_kind": kind,
            "subset_selection_sha256": core_subset(self, kind),
            "result_limit": size,
            "repetition": repetition,
            "population_scope": b.SYNTHETIC,
        }
        nonce = self.nonce()
        descriptors = b.assets()
        science = {
            "schema_version": "stage12_campaign_provenance_b2_v1",
            "campaign_version": "stage12_campaign_provenance_b2_v1",
            "campaign_id": nonce,
            "executable_sha": "c6b6d3ce34e42216712ed6fd6dfcef0f48bcfe13",
            "runtime_inventory_sha256": b.digest(self.runtime),
            "operations_policy_sha256": b.digest(profile),
            "authorization_sha256": H,
            "workload_sha256": b.digest(plan),
            "stage11_input_binding_sha256": b.digest(self.catalog.binding),
            "materialization_contract_sha256": assets.hashes()[c.MATERIALIZATION].hex(),
            "retrieval_policy_id": c.policy(size)["retrieval_policy_id"].hex(),
            "observation_binding_id": b.binding_id(
                self.records.get(self.gate.binding_hash, "observation_binding")
            ).hex()
            if isinstance(self.gate, evidence.Gate)
            else H,
            "response_validation_contract_sha256": assets.hashes()[
                response.VALIDATION
            ].hex(),
            "response_extraction_contract_sha256": b.digest(descriptors[b.EXTRACTION]),
            "candidate_schema_sha256": b.digest(b.descriptor("request_candidate")),
            "window_plan_sha256": self.window_hash,
            "privacy_permission_sha256": getattr(self.gate, "permission_hash", H),
            "scientific_decision_sha256": getattr(self.gate, "scientific_hash", H),
            "response_interpretation_sha256": getattr(
                self.gate, "interpretation_hash", H
            ),
        }
        start = {
            key: science[key]
            for key in (
                "campaign_id",
                "runtime_inventory_sha256",
                "observation_binding_id",
                "window_plan_sha256",
                "privacy_permission_sha256",
                "scientific_decision_sha256",
                "response_interpretation_sha256",
                "materialization_contract_sha256",
                "retrieval_policy_id",
                "stage11_input_binding_sha256",
                "response_validation_contract_sha256",
                "response_extraction_contract_sha256",
                "candidate_schema_sha256",
            )
        }
        start.update(
            schema_version=o.START,
            scope=o.SCOPE,
            profile_sha256=b.digest(profile),
            plan_sha256=b.digest(plan),
            rule_bundle_sha256=o.RULE_BUNDLE,
            policy_freeze_record_sha256=H,
            implementation_authorization_sha256=H,
            implementation_review_sha256=H,
            initial_workload_authority_sha256=H,
            client_git_sha=science["executable_sha"],
            created_utc=self.clock.utc(),
            population_scope=b.SYNTHETIC,
            scientific_campaign_start_sha256=b.digest(science),
        )
        segment = self.nonce()
        epoch = self.nonce()
        release = self.put(
            {
                "schema_version": "stage12_writer_release_authority_b2_v1",
                "campaign_id": nonce,
                "segment_nonce": segment,
                "issuer_delegation_sha256": H,
                "valid_from": "2025-01-01T00:00:00.000000Z",
                "valid_until": "2027-01-01T00:00:00.000000Z",
                "purpose": "WRITER_TERMINATION_AND_HANDOFF",
            }
        )
        preflight = self.preflight(segment)
        bootstrap = pipeline.prepare_bootstrap(
            self.root / ("bootstrap_" + segment),
            records=self.records,
            raw_factory=lambda: (lambda: self.records.raw(preflight),),
            clock=self.clock,
            profile=profile,
            plan=plan,
            start=start,
            segment_nonce=segment,
            epoch_id=epoch,
            authority=self.gate,
            authority_hash=H,
            writer_release_evidence=release,
            secret_guard=lambda raw: response.secret_guard(raw, KEY),
        )
        self.releases = getattr(self, "releases", {})
        self.releases[segment] = release
        admission = {
            "schema_version": "stage12_segment_admission_b2_v1",
            "campaign_start_sha256": b.digest(science),
            "operations_campaign_sha256": b.digest(start),
            "segment_nonce": segment,
            "segment_id": 1,
            "epoch_id": epoch,
            "preflight_observation_sha256": preflight,
            "predecessor_closure_sha256": None,
            "bootstrap_acquisition_sha256": bootstrap,
            "fresh_workload_authority_sha256": H,
            "writer_exclusion_evidence_sha256": H,
            "window_plan_sha256": self.window_hash,
            "privacy_permission_sha256": getattr(self.gate, "permission_hash", H),
            "admitted_utc": self.clock.utc(),
        }
        return profile, plan, start, science, admission, rows

    def preflight(self, segment):
        if not isinstance(self.gate, evidence.Gate):
            return H
        window = self.records.get(self.window_hash, "window_plan")
        binding = self.records.get(self.gate.binding_hash, "observation_binding")
        return self.put(
            {
                "schema_version": "stage12_window_observation_b2_v1",
                "window_plan_sha256": self.window_hash,
                "segment_nonce": segment,
                "phase": "PREFLIGHT",
                "inventory_sha256": binding["initial_evidence_inventory_sha256"],
                "correspondence_sha256": window["operator_arrangement_sha256"],
                "authority_review_sha256": window["authority_review_sha256"],
                "observed_from": self.clock.utc(),
                "observed_until": self.clock.utc(),
                "acquired_utc": self.clock.utc(),
                "interpretation_review_sha256": H,
            }
        )

    def close_segment(self, info):
        # Metadata-only finite loader tuple; synthetic records constructed after begin.
        state = {}

        def load(i):
            if "items" not in state:
                state["items"] = self._close_records(info)
            return next(state["items"])

        return tuple(
            lambda i=i: load(i)
            for i in range(6 if isinstance(self.gate, evidence.Gate) else 2)
        )

    def _close_records(self, info):
        admission = info["admission"]
        postflight = H
        imports = [self.records.raw(H)]
        if isinstance(self.gate, evidence.Gate):
            now = self.clock.utc()

            def retain(obj):
                raw = b.canonical(obj)
                imports.append(raw)
                return b.sha(raw).hex()

            pre = self.records.get(
                admission["preflight_observation_sha256"], "window_observation"
            )
            correspondence = {
                **self.records.get(pre["correspondence_sha256"], "correspondence"),
                "statement_utc": now,
                "acquired_utc": now,
            }
            ch = retain(correspondence)
            review = {
                **self.records.get(pre["authority_review_sha256"], "authority_review"),
                "subject_record_sha256": ch,
                "reviewed_utc": now,
            }
            rh = retain(review)
            inventory = self.records.get(pre["inventory_sha256"], "evidence_inventory")
            for fact in inventory["facts"]:
                fact.update(as_of_start=now, as_of_end=now, correspondence_sha256=ch)
            inventory.update(source_record_hashes=[ch], authority_review_hashes=[rh])
            ih = retain(inventory)
            postflight = retain(
                {
                    **pre,
                    "phase": "POSTFLIGHT",
                    "inventory_sha256": ih,
                    "correspondence_sha256": ch,
                    "authority_review_sha256": rh,
                    "observed_from": now,
                    "observed_until": now,
                    "acquired_utc": now,
                }
            )
        return iter(
            [
                *imports,
                b.canonical(
                    {
                        "schema_version": "stage12_segment_closure_b2_v1",
                        "window_plan_sha256": self.window_hash,
                        "segment_nonce": admission["segment_nonce"],
                        "campaign_start_sha256": info["scientific_start_sha256"],
                        "predecessor_closure_sha256": admission[
                            "predecessor_closure_sha256"
                        ],
                        "preflight_sha256": admission["preflight_observation_sha256"],
                        "postflight_sha256": postflight,
                        "attempt_inventory_sha256": info["attempt_inventory_sha256"],
                        "controller_reconciliation_sha256": info[
                            "controller_reconciliation_sha256"
                        ],
                        "resource_report_sha256": info["measurement_report_sha256"],
                        "gap_account_sha256": H
                        if admission["segment_id"] > 1
                        else None,
                        "operator_account_sha256": H,
                        "account_status": "NO_KNOWN_INTERVENTION",
                        "comparison": "REPORTED_FIELDS_AGREE",
                        "disposition": "CLOSED_OBSERVATIONAL",
                        "reviewed_utc": self.clock.utc(),
                        "review_decision_sha256": H,
                    }
                ),
            ]
        )

    def dispatch(self, work, target, hooks, *, raw=None, status=200):
        hooks.started(self.clock.now_ns())
        hooks.emit(lambda: None, lambda: None)
        if status != 200:
            from safe_geocoding_pipeline.preprocessing.stages import s12_operations

            outcome, reason = s12_operations.classify(status)
            hooks.signal(status, outcome, reason, None)
            payload = None
        else:
            outcome, reason, payload = (
                "VALIDATION_REQUIRED",
                "OK",
                body([feature()] * min(2, work["result_limit"]))
                if raw is None
                else raw,
            )
        capture = transport.Capture(
            outcome,
            reason,
            status,
            "application/json",
            "absent",
            None,
            payload,
            len(payload) if payload else 0,
            1,
        )
        hooks.completed(capture)
        return capture

    def run(self, name="segment", **options):
        inputs = options.pop("inputs", None) or self.inputs()
        profile, plan, start, science, admission, rows = inputs
        report = pipeline.run_segment(
            self.root / name,
            profile,
            plan,
            start,
            science,
            admission,
            catalog=self.catalog,
            work_factory=lambda: iter(rows),
            gate=self.gate,
            clock=self.clock,
            dispatch=options.pop("dispatch", self.dispatch),
            runtime_inventory=self.runtime,
            key=KEY,
            rules=self.rules,
            control_adapters={},
            free_bytes=lambda: 2**40,
            writer_release_evidence=self.releases[admission["segment_nonce"]],
            close_segment=options.pop("close_segment", self.close_segment),
            **options,
        )
        return report, inputs


def core_subset(world, kind):
    bound = world.records.get(world.selection_hash, "calibration_selection")
    return (
        bound["tail_inventory_sha256"]
        if kind == "TAIL"
        else bound["paired_inventory_sha256"]
        if kind == "PAIRED"
        else None
    )

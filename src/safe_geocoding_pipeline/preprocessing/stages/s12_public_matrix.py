"""Bounded frozen64-case capability orchestration, never scientific identity.

The existing O-r2 coordinator owns dispatch/capture. Exploratory fragment plans
are reconciled against one exact matrix before dispatch and again at closure.
The supplemental recipes are SERVICE_CONTROL, not additional DATA fixtures.
"""

from __future__ import annotations

from copy import deepcopy
from . import s11_semantic_contract as s11
from . import s12_probe as probe
from . import s12_public_operations as o
from . import s12_public_response as validation
from . import s12_retrieval_contract as c
from . import s12_response as response
from . import s12_public_operational_audit as audit
from . import s12_public_journal as journal
from . import s12_storage as io

VERSION = "stage12_public_diverse_capability_configuration_v1"
CHECK_VERSION = "stage12_public_parameter_check_v1"
MAIN_SIZES = (1, 3, 5, 10)
DEEP_SIZES = (20, 40)
MAX_ATTEMPTS = 2960
MAX_SECONDS = 7200
DATA_OBSERVATIONS = 576
CONTROL_OBSERVATIONS = 8


def checks():
    """Explicit invented public strings, no protected input or free-form URL."""
    values = (
        (
            "LEADING_ZERO_POSTCODE",
            "STRUCTURED",
            "US",
            None,
            "Invented ZQX passage 007",
            "02139",
            "Cambridge",
        ),
        (
            "SPACED_ALPHANUMERIC_POSTCODE",
            "STRUCTURED",
            "GB",
            None,
            "Invented ZQX passage 009",
            "SW1A 1AA",
            "London",
        ),
        (
            "POSTAL_TEXT_PERCENT_PLUS_LF",
            "FULL_TEXT",
            "DE",
            "Invented ZQX 01067 Straße + 7%\nDresden",
            None,
            None,
            None,
        ),
        (
            "AMBIGUOUS_PUBLIC_NAME_WITH_BOUNDARY",
            "FULL_TEXT",
            "CA",
            "Springfield 00100 + 7%\nQuébec",
            None,
            None,
            None,
        ),
    )
    result = []
    for number, (
        purpose,
        mode,
        country,
        text,
        address,
        postcode,
        locality,
    ) in enumerate(values, 1):
        core = {
            **s11.CONSTANTS,
            "endpoint": "/v1/search"
            if mode == "FULL_TEXT"
            else "/v1/search/structured",
            "search_mode": mode,
            "text": text,
            "address": address,
            "postalcode": postcode,
            "locality": locality,
            "boundary_country": country,
        }
        identity = s11.semantic_id(s11.core_bytes(core))
        target, _ = c.materialize(core, identity, c.policy(1), target_limit=4096)
        result.append(
            {
                "check_id": number,
                "purpose": purpose,
                "provenance": "MANUALLY_INVENTED_PUBLIC_TEST_NO_PROTECTED_SOURCE",
                "core": core,
                "semantic_id": identity.hex(),
                "size": 1,
                "target_ascii": target.decode("ascii"),
                "target_sha256": c.sha(target).hex(),
                "repetitions": 2,
            }
        )
    return result


def check_descriptor():
    return {
        "version": CHECK_VERSION,
        "scope": o.SCOPE,
        "checks": checks(),
        "response_rule": "ORDINARY_PUBLIC_SHAPES_NO_WARNING_EXCEPTION",
        "scientific_identity_verified": False,
        "privacy": "RUNTIME_KEY_GUARD_BEFORE_CAPTURE",
    }


def recipes(transport_hash):
    return [
        {
            "recipe_id": x["check_id"],
            "recipe_sha256": o.digest(x),
            "implementation_contract_sha256": o.digest(check_descriptor()),
            "transport_profile_sha256": transport_hash,
            "purpose": "LIMIT_CHECK",
            "max_http_attempts_per_invocation": 5,
            "max_duration_ms": 60000,
        }
        for x in checks()
    ]


class CheckAdapter:
    def __init__(self, recipe):
        self.recipe = deepcopy(recipe)
        self.check = checks()[recipe["recipe_id"] - 1]
        o.require(recipe in recipes(recipe["transport_profile_sha256"]))

    def target(self, recipe):
        o.require(recipe == self.recipe)
        return self.check["target_ascii"].encode("ascii")

    def validate(self, recipe, raw):
        self.target(recipe)
        features = validation.ordinary_shapes(raw, 1)
        return c.canonical(
            {
                "version": CHECK_VERSION,
                "check_sha256": o.digest(self.check),
                "request_target_sha256": self.check["target_sha256"],
                "response_sha256": c.sha(raw).hex(),
                "candidate_count": len(features),
                "scope": "PUBLIC_PARAMETER_CHECK_NOT_SCIENTIFIC_OBSERVATION",
            }
        )


def adapters(plan):
    return {r["recipe_id"]: CheckAdapter(r) for r in plan["control_recipes"]}


def fragments():
    """Fixed labels/coverage/order, independent of runtime observations."""
    cases = probe.fixtures()
    result = []
    for size in MAIN_SIZES:
        for mode in ("FULL_TEXT", "STRUCTURED"):
            group = [f for f in cases if f["core"]["search_mode"] == mode]
            result.append((f"size{size:02d}_{mode.lower()}", size, group))
    for size in DEEP_SIZES:
        result.append(
            (f"size{size:02d}_deep", size, [f for f in cases if f["deep_case"]])
        )
    result.append(("additional_parameter_checks", 1, []))
    return result


def work_for(index, transport_hash):
    _, size, group = fragments()[index]
    if group:
        rows = [
            {
                "work_id": 1 + repetition * len(group) + n,
                "block_id": 1,
                "kind": "DATA",
                "fixture_id": f["fixture_id"],
                "result_limit": size,
                "repetition": repetition,
                "recipe_id": None,
                "retry_spacing_key": f["fixture_id"],
            }
            for repetition in range(2)
            for n, f in enumerate(group)
        ]
        return rows, []
    rs = recipes(transport_hash)
    rows = [
        {
            "work_id": 1 + repetition * len(rs) + n,
            "block_id": 1,
            "kind": "SERVICE_CONTROL",
            "fixture_id": None,
            "result_limit": None,
            "repetition": None,
            "recipe_id": recipe["recipe_id"],
            "retry_spacing_key": recipe["recipe_sha256"],
        }
        for repetition in range(2)
        for n, recipe in enumerate(rs)
    ]
    return rows, rs


def binding(size_evidence):
    return {
        "version": "stage12_public_diverse_capability_selection_v1",
        "fixture_sha256": o.digest(probe.fixtures()),
        "operator_max_size": 40,
        "operator_size_evidence_sha256": size_evidence,
        "main_sizes": list(MAIN_SIZES),
        "deeper_sizes": list(DEEP_SIZES),
        "additional_checks": checks(),
        "check_contract_sha256": o.digest(check_descriptor()),
        "main_observations": 512,
        "deep_observations": 64,
        "additional_exchanges": 8,
        "http_p95_ms": 1000,
        "http_p99_ms": 1000,
        "slot_p95_ms": 2000,
        "slot_p99_ms": 2000,
        "max_writer_wait_ms": 1000,
        "omitted_boundary": "REJECTED_OFFLINE_BY_ACCEPTED_STAGE11_CONTRACT_NOT_TRANSMITTED",
    }


def validate_matrix(config):
    if (
        config.get("version")
        == "stage12_public_sampling_runtime_configuration_ra_g1_v1"
    ):
        from .s12_ra_g1_public_configuration import validate

        return validate(config)

    if config.get("version") == "stage12_public_sampling_runtime_configuration_v2":
        from . import s12_wf_ap2_contract as successor

        projected = deepcopy(config)
        projected["version"] = VERSION
        for item in projected["campaigns"]:
            successor.validate_plan(item["plan"], item["profile"])
            original_profile = item["profile"]
            item["profile"] = successor.legacy_profile(original_profile)
            item["plan"] = successor.legacy_plan(item["plan"], original_profile)
        return validate_matrix(projected)
    o.require(config["capability"] == binding(config["sources"]["size_allowance"]))
    o.require(
        config["public_validation_sha256"]
        in {
            o.digest(validation.descriptor(version))
            for version in (validation.FAMILY_VERSION, validation.CORPUS_VERSION)
        }
    )
    expected = fragments()
    o.require(len(config["campaigns"]) == len(expected))
    all_attempts = all_events = all_storage = all_time = 0
    for i, item in enumerate(config["campaigns"]):
        label, _, group = expected[i]
        profile, plan = item["profile"], item["plan"]
        rows, rs = work_for(i, profile["transport_profile_sha256"])
        o.require(
            item["label"] == label
            and item["work"] == rows
            and plan["control_recipes"] == rs
        )
        o.require(
            plan["capability_parent_sha256"] is None
            and item["ascending_sizes"] is False
        )
        o.require(
            plan["experiment_kind"] == "PERFORMANCE"
            and plan["blocks"][0]["evaluation"] == "EXPLORATORY"
        )
        o.require(
            profile["resource_sample_period_ms"] == 100
            and profile["resources"]["writer_guard_ms"] == 5000
        )
        o.require(plan["shutdown_reserve_ms"] == 80000)
        b = plan["budgets"]
        o.require(b == plan["blocks"][0]["budget"])
        o.require(b["data_observations"] == (len(rows) if group else 0))
        o.require(b["required_control_observations"] == (0 if group else 8))
        o.require(b["reserved_control_observations"] == 0)
        o.require(
            b["data_attempts"] == b["data_observations"] * 5
            and b["control_http_attempts"] == b["required_control_observations"] * 5
        )
        o.require(b["active_duration_ms"] <= 500000 and b["event_count"] <= 20000)
        all_attempts += b["data_attempts"] + b["control_http_attempts"]
        all_events += b["event_count"]
        all_storage += b["storage_bytes"]
        all_time += b["active_duration_ms"]
    o.require(all_attempts == 2920 <= config["maximum_attempts"])
    o.require(all_time <= config["active_seconds"] * 1000)
    o.require(all_storage <= config["resources"]["allocated_disk_bytes"])
    return {
        "attempts": all_attempts,
        "events": all_events,
        "storage_bytes": all_storage,
        "phase_duration_ms": all_time,
    }


def gate(block, item, selection):
    from .s12_public_runtime import qualifies

    if not qualifies(block, smoke=True):
        return False
    expected_data = item["plan"]["budgets"]["data_observations"]
    expected_controls = item["plan"]["budgets"]["required_control_observations"]
    if block["counts"]["durable_valid_data"]["value"] != expected_data:
        return False
    if block["counts"]["control_attempt_starts"]["value"] != expected_controls:
        return False
    for stat, p95, p99 in (("transport_all", "http_p95_ms", "http_p99_ms"),):
        x = block["latencies"][stat]
        if (
            x["p95_ms"] is None
            or x["p99_ms"] is None
            or x["p95_ms"] > selection[p95]
            or x["p99_ms"] > selection[p99]
        ):
            return False
    if expected_data:
        x = block["latencies"]["full_slot_data"]
        if (
            x["p95_ms"] is None
            or x["p99_ms"] is None
            or x["p95_ms"] > selection["slot_p95_ms"]
            or x["p99_ms"] > selection["slot_p99_ms"]
        ):
            return False
    wait = block["peaks"]["writer_wait_ms"]
    return wait is not None and wait <= selection["max_writer_wait_ms"]


def verify_controls(root, plan):
    """Fresh control receipts plus exact repeated full-feature equality, no key access."""
    rs = {r["recipe_id"]: r for r in plan["control_recipes"]}
    if not rs:
        return []
    final = {}
    start = io.metadata(io.read(root / "campaign_start.json"))
    for e in _events(root, start):
        if e["kind"] == "ATTEMPT_FINALIZED":
            b = e["body"]
            o.require(b["work_id"] not in final)
            final[b["work_id"]] = b
    pairs = []
    for number in rs:
        structures = []
        for wid in (number, number + 4):
            work = io.metadata(io.read(root / "work" / f"{wid:020d}.json"))
            e = final[wid]
            p = root / "attempts" / f"call_{wid:04d}_attempt_{e['attempt']}"
            adapter = CheckAdapter(rs[number])
            value = audit.reopen_control(p, adapter, key=None)
            o.require(
                value["outcome"] == "CONTROL_SUCCESS" and work["recipe_id"] == number
            )
            raw = response.decompress(
                io.read(p / "raw.zst"),
                length=value["application_payload_bytes"],
                expected_hash=bytes.fromhex(value["response_sha256"]),
            )
            structures.append(validation.ordinary_shapes(raw, 1))
        o.require(structures[0] == structures[1], "PUBLIC_PROBE_SAME_SIZE_INSTABILITY")
        pairs.append(
            {
                "recipe_id": number,
                "first_work_id": number,
                "next_work_id": number + 4,
                "equal": True,
            }
        )
    return pairs


def build_campaigns(profile, *, window_start, window_end, selection_sha256):
    """Pre-execution finite plans. Caller pins actual authority/resource records."""
    items = []
    for i, (label, _, group) in enumerate(fragments()):
        rows, rs = work_for(i, profile["transport_profile_sha256"])
        data, controls = (len(rows), 0) if group else (0, len(rows))
        budget = {
            "data_observations": data,
            "required_control_observations": controls,
            "reserved_control_observations": 0,
            "data_attempts": data * 5,
            "control_http_attempts": controls * 5,
            "administrative_operations": 0,
            "administrative_duration_ms": 0,
            "active_duration_ms": 500000 if data else 180000,
            "storage_bytes": (52 if data == 64 else 28 if data else 8) * 2**30,
            "event_count": 20000 if data else 6000,
        }
        block = {
            "block_id": 1,
            "state_id": 1,
            "observation_ids": list(range(1, len(rows) + 1)),
            "reserved_control_ids": [],
            "budget": deepcopy(budget),
            "evaluation": "EXPLORATORY",
            "criteria": None,
            "fallback_state_ids": [],
            "transition_from": None,
        }
        plan = {
            "schema_version": o.PLAN,
            "scope": o.SCOPE,
            "operations_profile_sha256": o.digest(profile),
            "fixture_inventory_sha256": o.digest(probe.fixtures()),
            "work_manifest_sha256": o.manifest_digest(rows),
            "control_recipes": rs,
            "blocks": [block],
            "experiment_kind": "PERFORMANCE",
            "capability_parent_sha256": None,
            "budgets": budget,
            "window_start": window_start,
            "window_end": window_end,
            "shutdown_reserve_ms": 80000,
            "selection_basis_sha256": selection_sha256,
        }
        items.append(
            {
                "label": label,
                "profile": deepcopy(profile),
                "plan": plan,
                "work": rows,
                "ascending_sizes": False,
            }
        )
    return items


def reconcile(config, output, check):
    """Actual original reopening of every phase, then bounded cross-size evidence.

    Metadata is bounded by the fixed584 observations/11 phases. No payload cache:
    every pair rereads/hash-validates both original bodies after receipt checks.
    """
    from . import s12_public_runtime as runtime
    from . import s12_public_audit as data_audit

    validate_matrix(config)
    o.require(io.read(output / "configuration.json") == c.canonical(config))
    attempts = events = storage = 0
    phase_rows, observations = [], {}
    for item in config["campaigns"]:
        check()
        root = output / item["label"]
        start = runtime.read_object(root / "campaign_start.json")
        with io.cooperative_io(check):
            block = runtime.reopen_completed(
                root,
                item["profile"],
                item["plan"],
                start,
                validation_sha256=config["public_validation_sha256"],
                control_adapters=adapters(item["plan"]),
            )
            o.require(gate(block, item, config["capability"]))
            control_pairs = verify_controls(root, item["plan"])
        actual_gate = runtime.read_object(
            output / (item["label"] + "_CAPABILITY_GATE.json")
        )
        o.require(
            actual_gate["configuration_sha256"] == o.digest(config)
            and actual_gate["block_report_sha256"] == o.digest(block)
            and actual_gate["control_comparisons"] == control_pairs
            and actual_gate["disposition"] == "PASS_EXACT_PHASE_NOT_RATE_QUALIFICATION"
        )
        finals = {}
        phase_events = 0
        for event in _events(root, start):
            check()
            phase_events += 1
            if event["kind"] == "ATTEMPT_FINALIZED":
                body = event["body"]
                o.require(body["work_id"] not in finals)
                finals[body["work_id"]] = body
        phase_attempts = block["counts"]["attempt_starts"]["value"]
        o.require(type(phase_attempts) is int)
        attempts += phase_attempts
        events += phase_events
        phase_storage = journal.tree_bytes(root, frozenset(), check=check)
        o.require(phase_storage <= item["plan"]["budgets"]["storage_bytes"])
        storage += phase_storage
        for work in item["work"]:
            if work["kind"] == "DATA":
                identity = (
                    work["fixture_id"],
                    work["result_limit"],
                    work["repetition"],
                )
                o.require(
                    identity not in observations
                    and len(observations) < DATA_OBSERVATIONS
                )
                observations[identity] = (root, work, finals[work["work_id"]])
        phase_rows.append(
            {
                "label": item["label"],
                "campaign_start_sha256": o.digest(start),
                "campaign_report_sha256": c.sha(
                    io.read(root / "campaign_report.json")
                ).hex(),
                "block_report_sha256": o.digest(block),
                "actual_attempts": phase_attempts,
                "events": phase_events,
                "logical_bytes": phase_storage,
                "required_control_repeat_pairs": control_pairs,
            }
        )
    o.require(
        len(observations) == DATA_OBSERVATIONS
        and attempts == DATA_OBSERVATIONS + CONTROL_OBSERVATIONS
    )
    totals = validate_matrix(config)
    o.require(attempts <= totals["attempts"] and events <= totals["events"])
    actual_task_storage = journal.tree_bytes(output, frozenset(), check=check)
    o.require(actual_task_storage <= config["resources"]["allocated_disk_bytes"])
    adapter = runtime.validation_for(config["public_validation_sha256"])

    def original(entry):
        check()
        root, work, event = entry
        name = data_audit.name_for(work["work_id"], event["attempt"])
        path = root / "attempts" / name
        o.require(
            c.sha(io.read(path / (name + "_receipt.json"))).hex()
            == event["receipt_inventory_sha256"]
        )
        terminal = data_audit.reopen(
            path,
            name,
            validator=adapter.validator(work, path),
            context=audit.DataContext(adapter),
        )
        raw = response.decompress(
            io.read(path / (name + ".zst")),
            length=terminal["application_payload_bytes"],
            expected_hash=bytes.fromhex(terminal["response_sha256"]),
        )
        return validation.shapes(raw, work, version=adapter.VERSION)

    prefixes = []
    for (fixture, size, repetition), entry in sorted(observations.items()):
        for lower in MAIN_SIZES:
            prior = observations.get((fixture, lower, repetition))
            if lower >= size or prior is None:
                continue
            o.require(len(prefixes) < 1024)
            equal = original(entry)[:lower] == original(prior)
            prefixes.append(
                {
                    "fixture_id": fixture,
                    "lower_size": lower,
                    "higher_size": size,
                    "repetition": repetition,
                    "equal": equal,
                }
            )
    o.require(len(prefixes) == 1024)
    # Prefix work is a separate fresh-read stage. Reopen each original phase
    # again before publishing the aggregate; a change since its first opening
    # cannot be hidden by the bounded metadata map or a still-matching raw body.
    for item, phase_record in zip(config["campaigns"], phase_rows):
        check()
        root = output / item["label"]
        start = runtime.read_object(root / "campaign_start.json")
        with io.cooperative_io(check):
            block = runtime.reopen_completed(
                root,
                item["profile"],
                item["plan"],
                start,
                validation_sha256=config["public_validation_sha256"],
                control_adapters=adapters(item["plan"]),
            )
        o.require(
            o.digest(start) == phase_record["campaign_start_sha256"]
            and o.digest(block) == phase_record["block_report_sha256"]
            and c.sha(io.read(root / "campaign_report.json")).hex()
            == phase_record["campaign_report_sha256"]
        )
    o.require(io.read(output / "configuration.json") == c.canonical(config))
    check()
    return {
        "version": "stage12_public_diverse_capability_result_v1",
        "scope": o.SCOPE,
        "configuration_sha256": o.digest(config),
        "data_observations": DATA_OBSERVATIONS,
        "control_exchanges": CONTROL_OBSERVATIONS,
        "same_size_comparisons": 288,
        "additional_control_repeat_comparisons": 4,
        "cross_size_comparisons": prefixes,
        "cross_size_scope": "TESTED_CASES_ONLY_NOT_UNIVERSAL_PREFIX_EQUIVALENCE",
        "actual_attempts": attempts,
        "actual_events": events,
        "actual_phase_logical_bytes": storage,
        "actual_task_logical_bytes_before_reconciliation": actual_task_storage,
        "phases": phase_rows,
        "full_frozen_capability_matrix_completed": True,
        "scientific_identity_verified": False,
        "continuous_service_state": "NOT_VERIFIED",
        "qualified_public_rates": [],
    }


def _contract(start):
    if start.get("schema_version") == "stage12_public_operations_campaign_ra_g1_v1":
        from . import s12_ra_g1_contract

        return s12_ra_g1_contract
    if start.get("schema_version") == "stage12_public_operations_campaign_v3":
        from . import s12_wf_ap2_contract

        return s12_wf_ap2_contract
    if start.get("schema_version") == "stage12_public_operations_campaign_v2":
        from . import s12_public_sampling_contract as ap

        return ap
    return o


def _events(root, start):
    contract = _contract(start)
    if getattr(contract, "PAGED_HISTORY", False):

        def rows():
            from .s12_paged_history import selected

            plan = contract.parse(io.read(root / "workload.json"), contract.PLAN)
            contract.require(contract.digest(plan) == start["plan_sha256"])
            with selected(plan["history_limits"]):
                yield from journal.read_events(root, o.digest(start), contract=contract)

        return rows()
    if contract is o:
        return journal.read_events(root, o.digest(start))
    return journal.read_events(root, o.digest(start), contract=contract)

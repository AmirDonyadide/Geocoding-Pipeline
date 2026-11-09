"""Prospective RA-G1 mechanics use invented inputs only, never live grants."""

from copy import deepcopy
import hashlib
import os
from pathlib import Path

import pytest

from stage12_b2_synthetic import World, H
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_b2_acceptance_graph import envelope as strict_envelope
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_b2_contract as b,
    s12_b2_acceptance_graph as strict,
    s12_b2_ra_g1_graph as g,
    s12_b2_ra_g1_resources as rs,
    s12_b2_ra_g1_allocation as limits,
    s12_b2_allocation_limits as strict_limits,
    s12_b2_ra_g1_contract as contract,
    s12_b2_ra_g1_local as local,
    s12_b2_local_preparation as strict_local,
    s12_b2_operations as operations,
    s12_retrieval_contract as c,
    s12_storage as io,
)

from safe_geocoding_pipeline.preprocessing.stages import s12_transport as _transport

_SECRET_METHODS = {
    name: _transport.Secret.__dict__[name] for name in ("runtime", "private_file")
}


def model(world, first_duration_ms=None, inventory_rows=None):
    original, selected = strict_envelope(world)
    result = {k: deepcopy(v) for k, v in original.items() if k not in g._REMOVED}
    result.update(
        schema_version=g.MODEL,
        successor_descriptor_sha256=g.DESCRIPTOR_SHA256,
        resource_assurance_selection_sha256=H,
        initial_capacity_observation_sha256=H,
        native_risk_inventory_sha256=H,
        physical_total_status="NOT_PROVEN",
    )
    if inventory_rows is not None:
        result["limits"]["inventory_rows"] = inventory_rows
    if first_duration_ms is not None:
        result["slots"][0]["max_duration_ms"] = first_duration_ms
    result["limits"].update(
        native_invocations=result["limits"]["sqlite_invocations"]
        + result["limits"]["duckdb_invocations"],
        monitor_rows=sum(
            (slot["max_duration_ms"] + 499) // 500 + 10 for slot in result["slots"]
        ),
    )
    ll = result["ledger_record_limits"]
    ll.update(max_total_bytes=g.LEDGER_ALLOWANCE_BYTES, max_prerequisite_bytes=2**20)
    kinds = {x["component_id"]: x for x in original["components"]}
    result["components"] = []
    for name in sorted(rs.COUNTS):
        native = name in (
            "SQLITE_INDEX",
            "SQLITE_JOURNAL",
            "DUCKDB_DATABASE",
            "DUCKDB_SPILL",
            "NATIVE_AUXILIARY",
        )
        partial = name in ("SQLITE_INDEX", "DUCKDB_SPILL")
        source = "ledger_records" if name == "ACCOUNTING_LEDGER" else rs.COUNTS[name]
        count = (
            sum(
                ll[x]
                for x in (
                    "max_member_bindings",
                    "max_slot_bindings",
                    "max_begins",
                    "max_terminals",
                    "max_branch_records",
                )
            )
            if source == "ledger_records"
            else result["limits"][source]
        )
        size = (
            g.LEDGER_ALLOWANCE_BYTES
            if name == "ACCOUNTING_LEDGER"
            else 65536
            if name in ("SQLITE_INDEX", "INVENTORIES")
            else 8192
        )
        predicate = (
            "TRANSIENT_NO_RECLAIM"
            if name == "NATIVE_AUXILIARY"
            else "DERIVED_RETAINED"
            if name == "MONITOR_EVIDENCE"
            else kinds[name]["state_predicate"]
        )
        result["components"].append(
            dict(
                component_id=name,
                count_source=source,
                count_cap=count,
                count_basis="INVOCATION"
                if native
                else "APPLICATION_WORK"
                if source
                in (
                    "data_works",
                    "control_works",
                    "data_attempts",
                    "control_attempts",
                    "candidate_rows",
                )
                else "APPLICATION_RECORD",
                max_concurrent_invocations=count,
                bound_kind="CHECKED_PARTIAL_NATIVE_CONTROL"
                if partial
                else "MONITORED_NATIVE_RISK"
                if native
                else "CHECKED_LOGICAL_BYTES",
                logical_prewrite_limit=size if not native or partial else None,
                application_creation_attempts_cap=None if native else count,
                physical_inode_status="NOT_PROVEN",
                retained_after_phase=True,
                state_predicate=predicate,
                evidence_sha256=H,
                native_role_inventory_sha256=H if native else None,
            )
        )
    components = {x["component_id"]: x for x in result["components"]}
    for slot in result["slots"]:
        slot.pop("max_generated_bytes")
        slot.pop("max_generated_inodes")
        slot["predicate_version"] = "RA_G1_ACCEPTANCE_GRAPH_V1"
        slot["allocations"] = {
            name: components[name]["count_cap"] if slot["slot_id"] == 1 else 0
            for name in rs.COUNTS
        }
        slot["logical_write_ceiling_bytes"] = (
            sum(
                (
                    x["logical_prewrite_limit"]
                    if x["component_id"] == "ACCOUNTING_LEDGER"
                    else x["count_cap"] * x["logical_prewrite_limit"]
                )
                for x in result["components"]
                if x["bound_kind"] == "CHECKED_LOGICAL_BYTES"
            )
            if slot["slot_id"] == 1
            else 1
        )
        slot["creation_attempt_ceiling"] = (
            sum(
                x["application_creation_attempts_cap"] or 0
                for x in result["components"]
            )
            if slot["slot_id"] == 1
            else 1
        )
    # Give every command a real fixed retained category, preserving positive caps.
    fixed = components["REPORTS_SEALS"]
    for slot in result["slots"]:
        slot["allocations"]["REPORTS_SEALS"] = 1
        if slot["slot_id"] == 1:
            slot["logical_write_ceiling_bytes"] -= (len(result["slots"]) - 1) * fixed[
                "logical_prewrite_limit"
            ]
            slot["creation_attempt_ceiling"] -= len(result["slots"]) - 1
        else:
            slot["logical_write_ceiling_bytes"] = fixed["logical_prewrite_limit"]
            slot["creation_attempt_ceiling"] = 1
    result.update(
        logical_write_ceiling_bytes=sum(
            x["logical_write_ceiling_bytes"] for x in result["slots"]
        ),
        retained_logical_allowance_bytes=sum(
            x["logical_write_ceiling_bytes"] for x in result["slots"]
        ),
        creation_attempt_ceiling=sum(
            x["creation_attempt_ceiling"] for x in result["slots"]
        ),
    )
    selected.update(
        schema_version=limits.VERSION,
        native_risk_inventory_sha256=selected.pop("native_bound_evidence_sha256"),
        resource_assurance_binding_sha256=H,
    )
    ceiling = {
        key: deepcopy(value)
        for key, value in selected.items()
        if key in limits.POSITIVE - {"command_id"} or key == "invocations"
    }
    ceiling["schema_version"] = g.CEILING
    for slot in result["slots"]:
        slot["allocation_limit_ceiling_sha256"] = world.put(ceiling)
    result["workload_sha256"] = g.envelope_workload_hash(result)
    selected["model_sha256"] = b.digest(result)
    return result, selected


def finish(paths):
    return dict(
        schema_version=g.FINISH,
        envelope_sha256=H,
        slot_id=1,
        previous_ledger_sha256=H,
        slot_binding_sha256=H,
        disposition="COMPLETED",
        observed_bytes=0,
        observed_inodes=0,
        inventory_sha256=H,
        inventory_roots=["/controlled/root"],
        inventory_max_entries=1024,
        generated_records=[{"path": path, "sha256": H} for path in paths],
        completed_utc="2026-11-09T00:00:00.000000Z",
    )


def test_explicit_versions_and_exact_ledger_arithmetic(tmp_path):
    world = World(tmp_path)
    value, selected = model(world)
    totals = g.validate_model(value)
    assert totals["physical_maximum"] == "NOT_PROVEN"
    assert len(value["components"]) == 32
    assert g.MAX_SLOTS == 643 and strict.MAX_SLOTS == 512
    assert (
        643 * 16 * 2**20 + (1286 + 11 + 1) * 65536 + 4 * 2**20 + 65536 + 2**20
        == g.LEDGER_ALLOWANCE_BYTES
    )
    with pytest.raises(c.Stage12Error):
        strict.validate_model(value)
    with pytest.raises(c.Stage12Error):
        strict_limits.parse(b.canonical(selected))
    assert limits.parse(b.canonical(selected)) == selected


@pytest.mark.parametrize(
    "change",
    [
        "native_zero",
        "missing_category",
        "fake_physical",
        "unknown_count",
        "fake_native_bound",
        "small_actual_population",
    ],
)
def test_model_near_misses_fail(tmp_path, change):
    world = World(tmp_path)
    value, selected = model(world)
    if change == "native_zero":
        next(x for x in value["components"] if x["component_id"] == "NATIVE_AUXILIARY")[
            "logical_prewrite_limit"
        ] = 1
    elif change == "missing_category":
        value["components"].pop()
    elif change == "fake_physical":
        value["capacity_bytes"] = 2**50
    elif change == "unknown_count":
        value["limits"]["native_invocations"] = None
    elif change == "small_actual_population":
        value["population_scope"] = b.DEVELOPMENT
    else:
        selected["native_bound_evidence_sha256"] = H
        with pytest.raises(c.Stage12Error):
            limits.parse(b.canonical(selected))
        return
    with pytest.raises(c.Stage12Error):
        g.validate_model(value)


def test_streamed_finish_full_original_and_narrow_reader(tmp_path):
    root = tmp_path / "controlled"
    root.mkdir(mode=0o700)
    # Escaped Unicode approaches the full successor format size with modest input.
    paths = ["/" + "\u0001" * 4080 + f"{n:04d}" for n in range(512)]
    row = finish(paths)
    path = root / "finish.json"
    digest = rs.write_finish(path, row)
    assert path.stat().st_size > 11 * 2**20
    opened = rs.read_finish(path)
    assert isinstance(opened["generated_records"], rs.PathArray)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert rs.digest_stream(opened) == digest
    assert len(opened["generated_records"]) == 512
    assert next(iter(opened["generated_records"]))["path"] == paths[0]
    with pytest.raises(c.Stage12Error):
        strict.parse(path.read_bytes())


@pytest.mark.parametrize(
    "change", ["truncate", "append", "duplicate", "noncanonical", "replace"]
)
def test_finish_mutations_reject_complete_original(tmp_path, change):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    path = root / "finish.json"
    row = finish(["/controlled/a", "/controlled/b"])
    rs.write_finish(path, row)
    opened = rs.read_finish(path)
    raw = path.read_bytes()
    if change == "truncate":
        path.write_bytes(raw[:-2])
    elif change == "append":
        path.write_bytes(raw + b" ")
    elif change == "duplicate":
        path.write_bytes(raw.replace(b'"slot_id":1', b'"slot_id":1,"slot_id":1'))
    elif change == "noncanonical":
        path.write_bytes(raw.replace(b'"slot_id":1', b'"slot_id": 1'))
    else:
        path.unlink()
        path.write_bytes(raw)
        path.chmod(0o600)
    with pytest.raises(c.Stage12Error):
        list(opened["generated_records"])
    if change != "replace":
        with pytest.raises(c.Stage12Error):
            rs.read_finish(path)


def test_prewrite_and_partial_write_keep_full_charge(tmp_path, monkeypatch):
    world = World(tmp_path)
    _, selected = model(world)
    selected["max_python_write_bytes"] = 65536
    selected["invocations"]["EXCLUSIVE_FILE"] = 1
    controls = limits.Controls(selected)
    root = world.root / "partial"
    root.mkdir(mode=0o700)
    original = os.write
    calls = 0

    def failing(fd, raw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic disk full")
        return original(fd, raw)

    monkeypatch.setattr(os, "write", failing)
    with io.allocation_controls(controls):
        with pytest.raises(OSError):
            rs.write_finish(root / "finish.json", finish(["/controlled/a"]))
    assert controls.counts["EXCLUSIVE_FILE"] == 1
    assert controls.python_bytes > 0
    assert (root / "finish.json").exists()
    with pytest.raises(c.Stage12Error):
        controls.claim("EXCLUSIVE_FILE")
    assert controls.usage()["native_maximum"] == "NOT_PROVEN"


def test_exact_successor_descriptor_and_local_service_denial():
    contract.verify_descriptors()
    assert operations.for_profile({"schema_version": contract.PROFILE}) is contract
    assert contract.ASSURANCE_METHOD == "LOGICAL_LIMITS_AND_SCOPED_MONITORING"
    assert local.RUNTIME_VERSION != strict_local.RUNTIME_VERSION
    assert local.ASSET["denial_policy"] == strict_local.ASSET["denial_policy"]
    assert "local_source_use_sha256" in local.REFERENCES
    with pytest.raises(c.Stage12Error):
        local.local_authority_check(
            __import__("types").SimpleNamespace(phase="build-catalog"),
            "dispatch",
            H,
            {},
        )


def ledger_and_binding(world):
    from test_stage12_b2_acceptance_graph import NoScientificOriginals

    value, selected = model(world)
    world.put(value)
    ledger = g.AcceptanceLedger(
        world.root / "ra_ledger",
        value,
        records=world.records,
        authority=world.gate,
        originals=NoScientificOriginals(),
        check=lambda: None,
        now=world.clock.utc,
    )
    cfg = {
        "runtime": {
            "phase": "plan-calibration",
            "source_files": [],
            "campaign": None,
            "authority_sha256": H,
            "phase_monitor_selection_sha256": H,
            "phase_capacity_observation_sha256": H,
            "phase_logical_write_ceiling_bytes": value["slots"][0][
                "logical_write_ceiling_bytes"
            ],
        },
        "command_paths": {
            "output_path": str(world.root / "output"),
            "scratch_path": str(world.root / "scratch"),
        },
    }
    pointer = {
        "model_sha256": b.digest(value),
        "command_id": 1,
        "allocation_limits_sha256": world.put(selected),
    }
    cfg["runtime"]["resource_retention"] = pointer
    scope = world.put(g.configuration_scope_record(cfg))
    proof = world.put(
        {
            "version": "SYNTHETIC_TEST_ONLY_GRAPH_AUTHORITY",
            "population_scope": b.SYNTHETIC,
        }
    )
    row = dict(
        schema_version=g.BINDING,
        envelope_sha256=b.digest(value),
        slot_id=1,
        previous_ledger_sha256=ledger.head,
        configuration_scope_sha256=scope,
        command_scope_sha256=g.command_scope(cfg),
        member_binding_sha256=None,
        source_inventory_sha256=value["source_inventory_sha256"],
        runtime_inventory_sha256=value["runtime_inventory_sha256"],
        allocation_limits_sha256=pointer["allocation_limits_sha256"],
        prerequisite_inventory_sha256=world.put(
            [{"record_kind": "LOCAL_AUTHORITY", "sha256": proof}]
        ),
        bound_utc=world.clock.utc(),
    )
    pointer["slot_binding_sha256"] = ledger.append_binding(row, cfg)
    return ledger, cfg, selected


def test_successful_slot_reopens_all_originals_and_keeps_full_precharge(tmp_path):
    world = World(tmp_path)
    ledger, cfg, _ = ledger_and_binding(world)
    ledger.begin(cfg, cfg["runtime"]["resource_retention"]["slot_binding_sha256"])
    before = ledger.accounting()
    root = world.root / "output"
    root.mkdir(mode=0o700)
    io.write(root / "original.json", b.canonical({"synthetic": True}))
    ledger.finish(roots=[root], max_entries=8)
    after = ledger.reopen()
    assert (
        before["logical_write_bytes_precharged"]
        == after["logical_write_bytes_precharged"]
    )
    assert after["terminal_slots"] == 1
    raw = (root / "original.json").read_bytes()
    (root / "original.json").write_bytes(raw.replace(b"true", b"null"))
    with pytest.raises(c.Stage12Error):
        ledger.reopen()


def test_uncertain_finish_blocks_root_and_preserves_active(tmp_path, monkeypatch):
    world = World(tmp_path)
    ledger, cfg, _ = ledger_and_binding(world)
    ledger.begin(cfg, cfg["runtime"]["resource_retention"]["slot_binding_sha256"])
    original = rs.write_finish

    def fail(path, row, **kwargs):
        original(path, row, **kwargs)
        raise OSError("synthetic post-write uncertainty")

    monkeypatch.setattr(rs, "write_finish", fail)
    with pytest.raises(OSError):
        ledger.finish(roots=[world.root / "output"], max_entries=8)
    assert (ledger.root / "ACTIVE.json").exists()
    assert (ledger.root / "MUTATING.json").exists()
    with pytest.raises(c.Stage12Error):
        ledger.reopen()


@pytest.mark.parametrize("N", [1, 5])
def test_ra_original_scientific_owner_N_branches_and_mutations(tmp_path, N):
    from test_stage12_b2_publication import publish_world
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_calibration as cal
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_publication as publication,
    )

    world = World(tmp_path, count=1)
    selection = cal.select(
        world.catalog,
        tmp_path / "branch_selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    readers = []
    campaign_values = []
    try:
        for index, intent in enumerate(selection["intents"]):
            values = world.inputs(
                size=intent["size"],
                kind=intent["kind"],
                repetition=intent["repetition"],
                subset=intent["subset"],
            )
            segment = tmp_path / ("branch_segment_" + str(index))
            world.run(segment.name, inputs=values)
            root = tmp_path / ("branch_publication_" + str(index))
            expected, validate, _ = publish_world(world, values, segment, root)
            campaign_values.append(values)
            readers.append(
                publication.ArtifactReader(
                    root,
                    expected,
                    scratch=tmp_path / ("branch_reader_" + str(index) + ".sqlite"),
                    catalog=world.catalog,
                    rules=world.rules,
                    validate_artifact=validate,
                )
            )
        observations = [reader.observation for reader in readers]
        report = cal.evaluate(
            world.catalog,
            selection,
            observations,
            window_hash=world.window_hash,
            selection_hash=world.selection_hash,
            authority=world.gate,
            comparison_writer=lambda row: None,
        )
        inventory = sorted(
            [
                {
                    "workload_kind": x.kind,
                    "publication_sha256": x.publication_sha256,
                    "campaign_closure_sha256": x.campaign_closure_sha256,
                    "window_plan_sha256": x.window_plan_sha256,
                    "workload_sha256": x.workload_sha256,
                }
                for x in observations
            ],
            key=lambda x: (x["workload_kind"], x["publication_sha256"]),
        )
        world.put(inventory)
        decision = {
            "schema_version": "stage12_n_decision_b2_v1",
            "window_plan_sha256": world.window_hash,
            "calibration_inventory_sha256": b.digest(inventory),
            "adequacy_report_sha256": b.digest(report),
            "owner_delegation_sha256": H,
            "result_limit": N,
            "retrieval_policy_id": c.policy(N)["retrieval_policy_id"].hex(),
            "decision": "SELECTED",
            "decided_utc": world.clock.utc(),
        }
        row = {
            "schema_version": g.BRANCH,
            "envelope_sha256": H,
            "previous_ledger_sha256": H,
            "window_plan_sha256": world.window_hash,
            "calibration_selection_sha256": world.selection_hash,
            "calibration_inventory_sha256": b.digest(inventory),
            "adequacy_report_sha256": world.put(report),
            "N_decision_sha256": world.put(decision),
            "C": 5,
            "N": N,
            "branch": "REUSE_FULL_C" if N == 5 else "DIRECT_N",
            "recorded_utc": world.clock.utc(),
        }
        originals = g.ScientificOriginals(
            world.records,
            world.gate,
            member_source=lambda row: None,
            calibration_source=lambda row: (world.catalog, selection, observations),
            campaign_source=lambda row: None,
            publication_source=lambda row: None,
            check=lambda: None,
        )
        assert originals.branch(row, {"population_scope": b.SYNTHETIC}) == report
        # The complete90-segment direct capacity has267 optional command slots.
        # N=C must skip every one without inventing a DIRECT_N member. N!=C
        # must first execute real direct work, then freshly prove completion for
        # each clean unused continuation; its first work stays mandatory.
        envelope, _ = model(world)
        envelope_hash = world.put(envelope)
        branch = dict(row, envelope_sha256=envelope_hash)
        proofs = [dict(record_kind="N_DECISION", sha256=branch["N_decision_sha256"])]
        skip = dict(
            schema_version=g.SKIP,
            envelope_sha256=envelope_hash,
            slot_id=1,
            previous_ledger_sha256=H,
            reason="N_EQUALS_C",
            proof_inventory_sha256=H,
            branch_record_sha256=b.digest(branch),
            recorded_utc=world.clock.utc(),
        )
        direct_member = None
        if N != 5:
            direct_values = world.inputs(size=N, kind="DIRECT_N")
            direct_root = tmp_path / "genuine_direct_segment"
            world.run(direct_root.name, inputs=direct_values)
            direct = g.CompletedCampaignOriginal(
                direct_root,
                population_scope=b.SYNTHETIC,
                catalog=world.catalog,
                rules=world.rules,
                gate=world.gate,
                control_adapters={},
                scratch_factory=lambda: (
                    tmp_path / ("direct_reopen_" + world.nonce() + ".sqlite")
                ),
                max_validations=268,
                check=lambda: None,
            )
            direct_member = dict(
                member_id=2, exact_plan_sha256=b.digest(direct_values[1])
            )
            originals.campaign_source = lambda member: direct
            snapshot = io.metadata(io.read(direct_root / "snapshot.json"))
            proofs = [
                dict(
                    record_kind="SEGMENT_CLOSURE",
                    sha256=snapshot["segment_closure_sha256"],
                )
            ]
            skip.update(reason="CAMPAIGN_ALREADY_COMPLETE", branch_record_sha256=None)
        completed = 0
        for segment in range(2, 91):
            for phase in ("prepare-bootstrap", "preflight", "run-direct-n"):
                slot = dict(
                    condition="CONTINUATION_CAPACITY",
                    member_role="FIXED_MEMBER",
                    member_id=2,
                    phase=phase,
                )
                originals.skip(skip, slot, direct_member, branch, proofs)
                completed += 1
        assert completed == 267
        with pytest.raises(c.Stage12Error):
            originals.skip(
                skip,
                dict(condition="REQUIRED", member_role="FIXED_MEMBER", member_id=2),
                direct_member,
                branch,
                proofs,
            )
        wrong_branch = dict(branch, branch="DIRECT_N" if N == 5 else "REUSE_FULL_C")
        wrong_skip = dict(
            skip, reason="N_EQUALS_C", branch_record_sha256=b.digest(wrong_branch)
        )
        with pytest.raises(c.Stage12Error):
            originals.skip(
                wrong_skip,
                dict(
                    condition="CONTINUATION_CAPACITY",
                    member_role="FIXED_MEMBER",
                    member_id=2,
                ),
                None,
                wrong_branch,
                [dict(record_kind="N_DECISION", sha256=branch["N_decision_sha256"])],
            )
        for mutation in (
            lambda x: x.update(N=3),
            lambda x: x.update(adequacy_report_sha256=H),
            lambda x: x.update(branch="DIRECT_N" if N == 5 else "REUSE_FULL_C"),
        ):
            changed = deepcopy(row)
            mutation(changed)
            with pytest.raises(c.Stage12Error):
                originals.branch(changed, {"population_scope": b.SYNTHETIC})
        (readers[0].root / "campaign.json").write_bytes(b"mutated original")
        with pytest.raises(c.Stage12Error):
            originals.branch(row, {"population_scope": b.SYNTHETIC})
    finally:
        for reader in readers:
            reader.close()


def ra_pipeline_inputs(world):
    """Invented RA records over actual protected pipeline/response algorithms."""
    from test_s12_ra_g1_core import binding, selection, capacity, facts
    from test_stage12_public_sampling_integration import RealClock
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_assurance as assurance,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_pipeline as pipeline

    profile, plan, start, science, admission, rows = world.inputs()
    world.clock = RealClock()
    world.gate.clock = world.clock
    selected = selection("DEVELOPMENT_ONLY")
    selected["source_git_sha"] = start["client_git_sha"]
    selected["limits"].update(processing_ms=100000, scheduler_s=101)
    selected["limits"]["stages"][0]["deadline_ms"] = 100000
    selected["valid_until"] = "2027-01-01T00:00:00.000000Z"
    bound = binding(selected)
    bound.update(
        source_git_sha=start["client_git_sha"], valid_until=selected["valid_until"]
    )
    world.runtime = {
        "version": "SYNTHETIC_TEST_ONLY_RA_RUNTIME",
        "scope": b.SYNTHETIC,
        "wf_ap2_runtime_facts": assurance.runtime_facts(
            environment_observation_sha256=bound[
                "initial_environment_observation_sha256"
            ]
        ),
    }
    start["runtime_inventory_sha256"] = science["runtime_inventory_sha256"] = b.digest(
        world.runtime
    )
    bound["runtime_inventory_sha256"] = b.digest(world.runtime)
    cap = capacity(selected)
    previous = profile["resources"]
    profile["resources"] = {
        "application_admission_memory_bytes": previous["admission_memory_bytes"],
        "requested_memory_bytes": 6 * 2**30,
        "logical_process_overhead_bytes": previous["process_overhead_bytes"],
        "logical_pending_request_bytes": previous["pending_request_bytes"],
        "per_attempt_logical_write_ceiling_bytes": previous[
            "per_attempt_disk_bound_bytes"
        ],
        "fixed_campaign_logical_write_ceiling_bytes": previous[
            "fixed_campaign_disk_bound_bytes"
        ],
        "task_logical_write_ceiling_bytes": previous["allocated_disk_bytes"],
        "resource_selection_sha256": b.digest(selected),
        "initial_capacity_observation_sha256": b.digest(cap),
        "resource_review_sha256": H,
        "scheduler_guard_ms": 100,
        "writer_guard_ms": 5000,
    }
    profile.update(
        schema_version=contract.PROFILE,
        rule_bundle_sha256=contract.RULE_BUNDLE,
        sampling_policy_sha256=contract.POLICY_SHA,
        sampling_runtime_bound_sha256=b.digest(bound),
        sampling_assurance_method=contract.ASSURANCE_METHOD,
    )
    profile.pop("resource_sample_period_ms")
    profile["states"][0].update(rate={"num": 1, "den": 1}, connections=2)
    profile["operator_allowance"].update(
        rate_ceiling={"num": 1, "den": 1}, connections=2
    )
    plan.update(
        schema_version=contract.PLAN,
        resource_retention_model_sha256=H,
        resource_workload_sha256=H,
        history_limits={
            "maximum_entries": 50000,
            "maximum_name_bytes": 1024,
            "maximum_total_name_bytes": 32 * 2**20,
            "page_entries": 4,
            "maximum_depth": 8,
            "maximum_file_bytes": 2**30,
        },
    )
    plan["budgets"]["active_duration_ms"] = 100000
    plan["blocks"][0]["budget"] = plan["budgets"]
    observations = 2002
    files = 4 * observations + 8
    plan["sampling_budget"] = {
        "maximum_segments": 1,
        "maximum_observations": observations,
        "maximum_inventory_versions_per_segment": 8,
        "additional_event_tokens": 2 * observations + 4,
        "additional_file_entries": files + 8 + 1502,
        "additional_file_data_bytes": 4096 * files
        + 8 * (512 * files + 4096)
        + 50200576,
    }
    value, _ = model(world)
    actual = rs.member_workload(plan)
    value["member_envelopes"][0] = {
        "member_id": 1,
        "workload_kind": plan["workload_kind"],
        "repetition": plan["repetition"],
        "permitted_result_limits": [plan["result_limit"]],
        **{key: actual[key] for key in g.COUNTS},
    }
    value["limits"].update(
        {key: sum(row[key] for row in value["member_envelopes"]) for key in g.COUNTS}
    )
    value["limits"]["max_candidates_per_work"] = max(
        max(x["permitted_result_limits"]) for x in value["member_envelopes"]
    )
    for component in value["components"]:
        name = component["component_id"]
        if name != "ACCOUNTING_LEDGER":
            component["count_cap"] = value["limits"][component["count_source"]]
            component["max_concurrent_invocations"] = component["count_cap"]
            if component["bound_kind"] == "CHECKED_LOGICAL_BYTES":
                component["application_creation_attempts_cap"] = component["count_cap"]
        for slot in value["slots"]:
            slot["allocations"][name] = (
                1
                if name == "REPORTS_SEALS"
                else component["count_cap"]
                if slot["slot_id"] == 1
                else 0
            )
    for slot in value["slots"]:
        slot["logical_write_ceiling_bytes"] = sum(
            (
                x["logical_prewrite_limit"]
                if x["component_id"] == "ACCOUNTING_LEDGER" and slot["slot_id"] == 1
                else slot["allocations"][x["component_id"]]
                * x["logical_prewrite_limit"]
            )
            for x in value["components"]
            if x["bound_kind"] == "CHECKED_LOGICAL_BYTES"
        )
        slot["creation_attempt_ceiling"] = sum(
            slot["allocations"][x["component_id"]]
            for x in value["components"]
            if x["bound_kind"] == "CHECKED_LOGICAL_BYTES"
        )
    value.update(
        logical_write_ceiling_bytes=sum(
            x["logical_write_ceiling_bytes"] for x in value["slots"]
        ),
        retained_logical_allowance_bytes=sum(
            x["logical_write_ceiling_bytes"] for x in value["slots"]
        ),
        creation_attempt_ceiling=sum(
            x["creation_attempt_ceiling"] for x in value["slots"]
        ),
    )
    value["workload_sha256"] = g.envelope_workload_hash(value)
    g.validate_model(value)
    profile["resource_retention_model"] = value
    plan.update(
        resource_retention_model_sha256=b.digest(value),
        resource_workload_sha256=rs.workload_binding(plan),
    )
    plan["operations_profile_sha256"] = b.digest(profile)
    science.update(
        operations_policy_sha256=b.digest(profile), workload_sha256=b.digest(plan)
    )
    start.update(
        schema_version=contract.START,
        profile_sha256=b.digest(profile),
        plan_sha256=b.digest(plan),
        rule_bundle_sha256=contract.RULE_BUNDLE,
        sampling_policy_sha256=contract.POLICY_SHA,
        scientific_campaign_start_sha256=b.digest(science),
        sampling_assurance_method=contract.ASSURANCE_METHOD,
    )
    authority = world.gate.authority
    authority.clock = world.clock
    authority.test_only = True
    authority.configuration_scope_sha256 = bound["configuration_scope_sha256"]
    authority.charge_identity_check = lambda record: None
    authority.resource_facts = authority.initial_resource_facts = lambda record: facts()
    authority.resource_selection = lambda record: selected
    authority.capacity_observation = lambda record: cap
    authority.sampling_bound = lambda profile, start: deepcopy(bound)
    # This test adapter remains unmistakably synthetic; it cannot issue live
    # monitor evidence or a real source/controller/service authorization.
    world.gate.register_coordinator = lambda coordinator: None
    world.gate.resource_prewrite = lambda **kwargs: None
    authority.resource_prewrite = world.gate.resource_prewrite
    admission.update(
        campaign_start_sha256=b.digest(science),
        operations_campaign_sha256=b.digest(start),
    )
    bootstrap = pipeline.prepare_bootstrap(
        world.root / "ra_bootstrap",
        records=world.records,
        raw_factory=lambda: (lambda: world.records.raw(H),),
        clock=world.clock,
        profile=profile,
        plan=plan,
        start=start,
        segment_nonce=admission["segment_nonce"],
        epoch_id=admission["epoch_id"],
        authority=world.gate,
        authority_hash=H,
        writer_release_evidence=world.releases[admission["segment_nonce"]],
        secret_guard=lambda raw: None,
    )
    admission["bootstrap_acquisition_sha256"] = bootstrap
    return profile, plan, start, science, admission, rows


def test_actual_ra_protected_pipeline_closed_report_and_original_reopen(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_audit as audit

    world = World(tmp_path, count=1)
    values = ra_pipeline_inputs(world)
    report, _ = world.run(inputs=values)
    profile, plan, start, *_ = values
    assert report["schema_version"] == contract.REPORT
    assert report["sampling_assurance_method"] == contract.ASSURANCE_METHOD
    assert report["counts"]["durable_valid_data"]["value"] == 1
    root = world.root / "segment"
    opened = recovery.reopen(
        root,
        start,
        profile,
        plan,
        works=lambda: iter(values[-1]),
        verify_receipt=lambda work, event: audit.reopen(
            root / "attempts" / f"{work['work_id']:020d}_{event['attempt']:02d}",
            **world.rules.kwargs(),
        )[0],
        scratch=world.root / "ra_independent.sqlite",
        authority=world.gate,
    )
    assert opened["snapshot"]["sampling"]["complete"]
    import test_stage12_b2_publication as publication_fixture

    monkeypatch.setattr(publication_fixture, "o", contract)
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_publication as publication,
    )

    expected, validate, _ = publication_fixture.publish_world(
        world, values, root, world.root / "ra_publication"
    )
    manifest = validate()
    assert manifest["manifest_version"] == contract.PUBLICATION_MANIFEST
    assert manifest["resource_assurance"]["native_maximum"] == "NOT_PROVEN"
    assert manifest["resource_assurance"] == contract.publication_resource_summary(
        profile
    )
    bad = deepcopy(manifest)
    bad["resource_assurance"]["physical_maximum"] = "PROVEN"
    path = world.root / "ra_publication" / "manifest.json"
    path.write_bytes(b.canonical(bad))
    with pytest.raises(c.Stage12Error):
        publication.validate_terminal(
            path.parent,
            b.sha(b.canonical(bad)),
            committed=True,
            validate_science=lambda *args: None,
        )


@pytest.mark.parametrize("failure", ["strict_warning", "unknown_delivery"])
def test_ra_protected_failures_preserve_evidence_and_cannot_seal(tmp_path, failure):
    import json
    from stage12_synthetic import body

    world = World(tmp_path, count=1)
    inputs = ra_pipeline_inputs(world)
    calls = []

    def dispatch(work, target, hooks):
        calls.append(work["work_id"])
        if failure == "unknown_delivery":
            hooks.started(world.clock.now_ns())
            hooks.emit(lambda: None, lambda: None)
            raise RuntimeError("SYNTHETIC uncertain writer/provider return")
        raw = json.loads(body([]))
        raw["geocoding"]["warnings"] = [
            "SYNTHETIC warning is forbidden on protected B2"
        ]
        return world.dispatch(work, target, hooks, raw=b.canonical(raw))

    with pytest.raises(c.Stage12Error):
        world.run(inputs=inputs, dispatch=dispatch)
    assert calls == [1]
    assert not (world.root / "segment" / "_SEGMENT_SEALED").exists()
    assert list((world.root / "segment" / "attempts").rglob("begin.json"))
    assert (world.root / "segment_telemetry").exists()


def ra_lp_runtime(world, monkeypatch):
    """Real RuntimePort/Gate/ledger, synthetic issuers and kernel originals only."""
    import stat
    from types import SimpleNamespace
    from test_stage12_b2_local_preparation import lp1_configuration
    from test_stage12_public_sampling_integration import RealClock
    from test_s12_ra_g1_core import (
        binding as sample_binding,
        selection as sample_selection,
        facts as sample_facts,
        observation,
        original_observation,
    )
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_assurance as assurance,
    )
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_execution as execution,
    )

    config, out, scratch, old_authority = lp1_configuration(world)
    world.clock = RealClock()
    r = config["runtime"]
    config.update(
        schema_version=contract.CONFIG,
        command_paths={"output_path": str(out), "scratch_path": str(scratch)},
    )
    context = world.put({"schema_version": "SYNTHETIC_TEST_ONLY_NOT_A_LIVE_SUPERVISOR"})
    config["resource_execution"] = {
        "schema_version": "stage12_resource_execution_request_ra_g1_v1",
        "supervisor_context_path": str(world.records.root / (context + ".json")),
        "supervisor_context_sha256": context,
    }
    paths = world.put(
        {
            "schema_version": rs.REGISTERED_PATHS,
            "scope": "DEVELOPMENT_LOCAL_PREPARATION",
            "native_roots": [str(world.root)],
            "native_paths": [str(scratch)],
            "review_sha256": H,
            "native_role_inventory_sha256": H,
        }
    )
    config["resource_paths"] = {
        "bindings_path": str(world.root / "ra_actual_binding.json"),
        "registered_paths_record_sha256": paths,
        "resource_evidence_root": str(world.root / "ra_resource_evidence"),
        "setup_counter_prefix_sha256": None,
    }
    r["version"] = local.RUNTIME_VERSION
    for key in runtime.RA_REPLACED:
        r.pop(key)
    value, allocation = model(world, first_duration_ms=120000, inventory_rows=64)
    allocation.update(sqlite_main_bytes=8 * 2**20, max_python_write_bytes=8 * 2**20)
    allocation["invocations"].update(EXCLUSIVE_FILE=200, PREFIX_FILE=20)
    next(x for x in value["components"] if x["component_id"] == "SQLITE_INDEX")[
        "logical_prewrite_limit"
    ] = 8 * 2**20
    ceiling = {
        key: deepcopy(item)
        for key, item in allocation.items()
        if key in limits.POSITIVE - {"command_id"} or key == "invocations"
    }
    ceiling["schema_version"] = g.CEILING
    value["slots"][0]["allocation_limit_ceiling_sha256"] = world.put(ceiling)
    r.update(
        phase_monitor_selection_sha256=H,
        phase_capacity_observation_sha256=H,
        phase_logical_write_ceiling_bytes=value["slots"][0][
            "logical_write_ceiling_bytes"
        ],
        phase_duration_ms=120000,
    )
    selected = sample_selection("DEVELOPMENT_LOCAL_PREPARATION")
    for key, spec in assurance.SELECTION_SCHEMA.items():
        if spec == "D":
            selected[key] = H
    selected["limits"].update(
        processing_ms=120000,
        scheduler_s=121,
        attempts=0,
        logical_write_bytes=r["phase_logical_write_ceiling_bytes"],
        creations=max(10000, value["slots"][0]["creation_attempt_ceiling"]),
        monitor_rows=250,
        monitor_bytes=250 * 16384 + 28 * 8192,
        monitor_creations=528,
        native_invocations=20,
        input_bytes=world.catalog.path.stat().st_size,
    )
    selected["limits"]["application_counters"] = dict(allocation["invocations"])
    stage = selected["limits"]["stages"][0]
    stage.update(
        deadline_ms=95000,
        attempts=0,
        logical_write_bytes=r["phase_logical_write_ceiling_bytes"],
        creations=selected["limits"]["creations"],
        source_read_calls=10000000,
        source_read_bytes=2**40,
        check_calls=1000000,
    )
    setup_stage = deepcopy(stage)
    setup_stage.update(
        id=1,
        phase=1,
        deadline_ms=20000,
        attempts=0,
        events=0,
        logical_write_bytes=8 * 2**20,
        creations=200,
    )
    stage.update(id=2, phase=2)
    terminal_stage = deepcopy(stage)
    terminal_stage.update(
        id=3,
        phase=3,
        deadline_ms=5000,
        attempts=0,
        events=0,
        logical_write_bytes=2 * 2**20,
        creations=100,
    )
    stage["logical_write_bytes"] -= 10 * 2**20
    stage["creations"] -= 300
    selected["limits"]["stages"] = [setup_stage, stage, terminal_stage]
    selected_hash = world.put(selected)
    r["phase_monitor_selection_sha256"] = selected_hash
    cap, originals = assurance.observe_capacity(
        world.root,
        scope=selected["scope"],
        selection_sha256=selected_hash,
        owner_reported_approval_sha256=H,
        accounting_method_sha256=H,
        restrictions_inventory_sha256=H,
        observed_utc=world.clock.utc(),
        clock_ns=world.clock.now_ns,
    )
    assert world.put(originals["root"]) == cap["root_identity_inventory_sha256"]
    assert world.put(originals["statvfs"]) == cap["filesystem_originals_sha256"]
    r["phase_capacity_observation_sha256"] = world.put(cap)
    facts = sample_facts()
    facts["pids_max"] = assurance.unknown("UNAVAILABLE", "INACCESSIBLE")
    identity = dict(
        domain="/sys/fs/cgroup/selected",
        device=1,
        inode=2,
        boot_id=facts["boot_id"],
        cgroup_namespace_inode=facts["cgroup_namespace_inode"],
        mount_namespace_inode=facts["mount_namespace_inode"],
        membership="0::/selected",
    )

    def raw(text):
        return {
            "text": text,
            "identity": [1, 2, stat.S_IFREG | 0o444, 0, 0],
            "acquired_mono_ns": 1,
        }

    kernel = {
        "visible_identity": identity,
        "records": {
            "/proc/123/cgroup": raw("0::/selected"),
            "/proc/sys/kernel/random/boot_id": raw(facts["boot_id"]),
            "/sys/fs/cgroup/selected/memory.max": raw(str(12 * 2**30)),
            "/sys/fs/cgroup/selected/memory.high": raw(str(6 * 2**30)),
            "/sys/fs/cgroup/selected/memory.swap.max": raw("0"),
        },
    }
    facts.update(
        observation_inventory_sha256=world.put(kernel),
        visible_identity_inventory_sha256=b.digest(identity),
        visible_membership_sha256=b.digest({"membership": "0::/selected"}),
    )
    facts_hash = world.put(facts)
    assurance.validate_environment_originals(facts, kernel)
    bound = sample_binding(selected)
    for key, spec in assurance.SCHEMA.items():
        if spec == "D":
            bound[key] = H
    bound.update(
        selection_sha256=selected_hash,
        initial_environment_observation_sha256=facts_hash,
        maximum_identity_checks=1000000,
        maximum_original_read_calls=10000000,
        maximum_original_read_bytes=2**40,
        source_inventory_sha256=b.digest(r["source_files"]),
        configuration_scope_sha256=rs.configuration_scope(config),
    )
    # Native runtime inventory is observed on this host; its kernel record is
    # labelled synthetic and cannot issue an ACCEPTED_DEVELOPMENT binding.
    fake = SimpleNamespace(
        population_scope=b.SYNTHETIC,
        settings=r,
        ra_enabled=True,
        ra_binding=bound,
        charge_ra_original_read=lambda calls, size: None,
    )
    fake._ra_backend_digest = lambda name, path, check: rs.bounded_source_digest(
        fake, path, check
    )
    inventory = runtime.RuntimePort._actual_runtime_inventory(fake, successor=True)
    bound["runtime_inventory_sha256"] = world.put(inventory)
    bound_hash = world.put(bound)
    io.write(Path(config["resource_paths"]["bindings_path"]), b.canonical(bound))
    value["source_inventory_sha256"] = b.digest(r["source_files"])
    value["runtime_inventory_sha256"] = b.digest(
        runtime.RuntimePort._actual_runtime_inventory(fake, successor=False)
    )
    value["resource_assurance_selection_sha256"] = selected_hash
    value["initial_capacity_observation_sha256"] = r[
        "phase_capacity_observation_sha256"
    ]
    allocation.update(
        model_sha256=world.put(value), resource_assurance_binding_sha256=bound_hash
    )
    r["resource_retention"] = {
        "model_sha256": b.digest(value),
        "command_id": 1,
        "allocation_limits_sha256": world.put(allocation),
    }
    # LP authority self pointers and later SlotBinding are the only scope holes.
    workload = io.metadata(world.records.raw(config["local_workload_sha256"]))
    workload["parameters_sha256"] = local.workload_parameters_hash(config)
    config["local_workload_sha256"] = world.put(workload)
    bound["configuration_scope_sha256"] = rs.configuration_scope(config)
    bound_hash = world.put(bound)
    Path(config["resource_paths"]["bindings_path"]).unlink()
    io.write(Path(config["resource_paths"]["bindings_path"]), b.canonical(bound))
    allocation["resource_assurance_binding_sha256"] = bound_hash
    r["resource_retention"]["allocation_limits_sha256"] = world.put(allocation)
    authority = {
        **old_authority,
        "schema_version": local.DESCRIPTOR,
        "local_controller_scope_sha256": world.put(
            {"schema_version": "SYNTHETIC_ONLY_LOCAL_CONTROLLER_REFERENCE"}
        ),
        "resource_assurance_binding_sha256": bound_hash,
        "configuration_scope_sha256": local.scope_hash(config),
        "workload_sha256": config["local_workload_sha256"],
        "bounds": {key: r[key] for key in local.BOUNDS},
    }
    r["local_preparation_authority_sha256"] = world.put(authority)
    current_path = Path(r["local_preparation_current_path"])
    current = io.metadata(io.read(current_path))
    current.update(
        schema_version="stage12_local_preparation_current_b2_ra_g1_v1",
        authority_sha256=r["local_preparation_authority_sha256"],
    )
    current_path.unlink()
    io.write(current_path, b.canonical(current))
    from test_stage12_b2_acceptance_graph import NoScientificOriginals

    ledger = g.AcceptanceLedger(
        world.root / ("ra_g1_acceptance_" + b.digest(value)),
        value,
        records=world.records,
        authority=world.gate,
        originals=NoScientificOriginals(),
        check=lambda: None,
        now=world.clock.utc,
    )
    projection = world.put(g.configuration_scope_record(config))
    bind = dict(
        schema_version=g.BINDING,
        envelope_sha256=b.digest(value),
        slot_id=1,
        previous_ledger_sha256=ledger.head,
        configuration_scope_sha256=projection,
        command_scope_sha256=g.command_scope(config),
        member_binding_sha256=None,
        source_inventory_sha256=value["source_inventory_sha256"],
        runtime_inventory_sha256=value["runtime_inventory_sha256"],
        allocation_limits_sha256=r["resource_retention"]["allocation_limits_sha256"],
        prerequisite_inventory_sha256=world.put(
            [
                {
                    "record_kind": "LOCAL_AUTHORITY",
                    "sha256": r["local_preparation_authority_sha256"],
                }
            ]
        ),
        bound_utc=world.clock.utc(),
    )
    r["resource_retention"]["slot_binding_sha256"] = ledger.append_binding(bind, config)
    trust = {
        "version": runtime.RA_AUTHORITY_VERSION,
        "scope_sha256": runtime.scope_hash(config),
        "population_scope": b.SYNTHETIC,
        "owner_decision_sha256": H,
        "delegation_sha256": H,
        "review_sha256": H,
        "valid_from": "2025-01-01T00:00:00.000000Z",
        "valid_until": "2027-01-01T00:00:00.000000Z",
        "phase_authority_sha256": H,
        "phase_names": [r["phase"]],
        "grants": [],
        "grant_directory": str(world.root / ("grants_" + r["phase"])),
        "dynamic_purposes": ["nonsecret_record"],
    }
    r["authority_sha256"] = world.put(trust)
    original_require = runtime.Authority.require

    def provision(self, purpose, digest, context):
        assert self.config["runtime"]["population_scope"] == b.SYNTHETIC
        subject = {
            "purpose": purpose,
            "evidence_sha256": digest,
            "context_sha256": b.digest(context),
        }
        path = Path(self._root()["grant_directory"]) / (b.digest(subject) + ".json")
        if not path.exists():
            io.write(
                path,
                b.canonical(
                    {
                        "version": "stage12_runtime_exact_grant_v1",
                        "decision": "ISSUED",
                        "subject": subject,
                        "delegation_sha256": H,
                        "review_record_sha256": H,
                    }
                ),
            )
        return original_require(self, purpose, digest, context)

    monkeypatch.setattr(runtime.Authority, "require", provision)

    def resource_session(port, charge, root, deadline, phase, binding, cls):
        def observer_factory(retain):
            def acquire(kind):
                at = port.clock.now_ns()
                row = observation(selected, enter=at, kind=kind)
                row["counters"] = port.resource_monitor_counters()
                original = original_observation(row)
                return {
                    "readings": row["readings"],
                    "counters": row["counters"],
                    "native_visibility": row["native_visibility"],
                    "visible_identity_inventory_sha256": retain(original),
                }

            return acquire

        return cls(
            authority=port.authority,
            binding=binding,
            selection=port.ra_selection,
            resource_evidence_root=root,
            pids=(os.getpid(),),
            counter_provider=port.resource_monitor_counters,
            charge=charge,
            check=port.check_resource_deadline,
            deadline_ns=deadline,
            phase_id=phase,
            admitted_process_provider=lambda: (os.getpid(),),
            read_charge=port.charge_ra_original_read,
            clock_ns=port.clock.now_ns,
            observer_factory=observer_factory,
            scope_start_ns=port.started_ns if phase == 1 else port.ra_command_entry_ns,
        )

    def factory(port, charge):
        return resource_session(
            port,
            charge,
            Path(config["resource_paths"]["resource_evidence_root"]),
            port.ra_active_scope_deadline,
            2,
            port.ra_binding,
            execution.PhaseSession,
        )

    def setup_factory(port, charge, root, deadline):
        bound = port.ra_binding
        binding = dict(
            schema_version=execution.ADMIN_BINDING,
            scope=bound["scope"],
            method=assurance.METHOD,
            role="PROTECTED_SETUP",
            phase_id=1,
            source_git_sha=bound["source_git_sha"],
            selection_sha256=bound["selection_sha256"],
            adoption_sha256=bound["adoption_sha256"],
            supervisor_context_sha256=config["resource_execution"][
                "supervisor_context_sha256"
            ],
            risk_inventory_sha256=bound["risk_inventory_sha256"],
            process_pid=os.getpid(),
            process_start_ticks=0,
            process_uid=os.getuid(),
            scope_start_mono_ns=port.started_ns,
            deadline_mono_ns=deadline,
            service_authority="DENIED",
            protected_input_authority="DENIED",
            ap_dispatch_authority="DENIED",
        )
        return resource_session(
            port,
            charge,
            root,
            deadline,
            1,
            binding,
            execution.AdministrativePhaseSession,
        )

    monkeypatch.setattr(
        strict_local, "_PROVIDER_WRAPPERS", dict(strict_local._PROVIDER_WRAPPERS)
    )
    for name in ("runtime", "private_file"):
        method = (
            classmethod(strict_local._PROVIDER_WRAPPERS[name])
            if name in strict_local._PROVIDER_WRAPPERS
            else _SECRET_METHODS[name]
        )
        monkeypatch.setattr(_transport.Secret, name, method)
    port = runtime.RuntimePort(
        config,
        _test={
            "clock": world.clock,
            "resource_facts": lambda record: deepcopy(facts),
            "resource_session_factory": factory,
            "resource_setup_factory": setup_factory,
            "key_provider": lambda: pytest.fail("LP provider called"),
            "send": lambda *args, **kwargs: pytest.fail("LP service called"),
        },
    )
    return port, config, out, scratch


def test_actual_ra_local_cli_opener_final_monitor_and_pending_no_refund(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli

    world = World(tmp_path, count=1)
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    original_source = runtime.RuntimePort._source_check
    scopes = []

    def watched_source(port):
        if isinstance(port, runtime.RuntimePort) and port.ra_enabled:
            assert port.ra_monitor is not None
            assert port.ra_monitor.coverage.seq >= 1
            scopes.append(port.ra_monitor.phase)
        return original_source(port)

    monkeypatch.setattr(runtime.RuntimePort, "_source_check", watched_source)
    port, config, out, scratch = ra_lp_runtime(world, monkeypatch)
    assert port.ra_setup_session.completed and scopes and set(scopes) == {1}
    prefix_reads = port.ra_original_read_calls
    prefix_bytes = port.ra_monitor_write_bytes
    result = cli.execute("plan-calibration", cli.Session(port, config, out, scratch, H))
    assert result["scientific_N_selected"] is False
    assert port._closed and port.offline_guard.closed
    assert port.ra_resource_session.completed
    assert port.ra_resource_session.protocol.state == "MONITOR_CLOSED"
    assert set(scopes) == {1, 2}
    assert (
        port.ra_original_read_calls > prefix_reads
        and port.ra_monitor_write_bytes > prefix_bytes
    )
    marker = rs.completion_root(
        config["runtime"]["output_parent"],
        config["runtime"]["resource_retention"]["model_sha256"],
    )
    assert (marker / "000001.pending.json").exists()
    assert not (marker / "000001.success.json").exists()
    assert not (port.resource_ledger.root / "ACTIVE.json").exists()
    assert port.resource_ledger.next_slot == 2
    with pytest.raises((c.Stage12Error, FileNotFoundError)):
        rs.require_worker_success(port, 1)


def test_ra_delayed_initialization_keeps_earliest_entry_and_rejects_first_start(
    tmp_path, monkeypatch
):
    import time
    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_runtime as runtime

    world = World(tmp_path, count=1)
    initial = runtime.RuntimePort._initialize
    source = runtime.RuntimePort._source_check
    verified = []

    def delayed(port, config, **kwargs):
        assert kwargs["direct_entry_ns"] <= time.monotonic_ns()
        time.sleep(1.05)
        return initial(port, config, **kwargs)

    def source_check(port):
        if isinstance(port, runtime.RuntimePort):
            verified.append(True)
        return source(port)

    monkeypatch.setattr(runtime.RuntimePort, "_initialize", delayed)
    monkeypatch.setattr(runtime.RuntimePort, "_source_check", source_check)
    with pytest.raises(c.Stage12Error, match="RA_G1_MONITOR_GAP"):
        ra_lp_runtime(world, monkeypatch)
    assert verified == []


def test_actual_finish_writer_keeps_only_fixed_digests_and_one_encoded_path(tmp_path):
    import gc
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_history as history,
    )

    gc.collect()
    before = history._backing
    root = Path("/SYNTHETIC/" + "/".join(["\x7f" * 240] * 15))
    generated = rs.GeneratedRecords(root)
    assert history._backing == before + 32768
    for i in range(512, 0, -1):
        generated.reserve(f"{i:064x}", 512)
    assert len(generated) == 512 and len(generated.backing) == 16384
    assert not any(
        isinstance(value, (dict, list)) for value in generated.__dict__.values()
    )
    with pytest.raises(c.Stage12Error):
        generated.reserve(f"{1:064x}", 512)
    row = finish([])
    row["generated_records"] = generated
    path = tmp_path / "actual_generated_finish.json"
    rs.write_finish(path, row)
    assert path.stat().st_size > 10 * 2**20
    opened = g.parse_finish(path)
    assert next(iter(opened["generated_records"]))["sha256"] == f"{1:064x}"
    assert history._backing == before + 32768
    del generated, row
    gc.collect()
    assert history._backing == before


def test_ra_local_missing_controller_stops_before_catalog_and_never_releases(
    tmp_path, monkeypatch
):
    from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli

    world = World(tmp_path, count=1)
    port, config, out, scratch = ra_lp_runtime(world, monkeypatch)
    authority = io.metadata(
        world.records.raw(config["runtime"]["local_preparation_authority_sha256"])
    )
    (
        world.records.root / (authority["local_controller_scope_sha256"] + ".json")
    ).unlink()
    monkeypatch.setattr(
        port,
        "open_catalog",
        lambda: pytest.fail("controller gate allowed catalog access"),
    )
    with pytest.raises((c.Stage12Error, FileNotFoundError)):
        cli.execute("plan-calibration", cli.Session(port, config, out, scratch, H))
    assert port._closed and port.offline_guard.closed
    marker = rs.completion_root(
        config["runtime"]["output_parent"],
        config["runtime"]["resource_retention"]["model_sha256"],
    )
    assert (marker / "000001.pending.json").exists() and not (
        marker / "000001.success.json"
    ).exists()


def test_ra_pending_release_needs_actual_return_and_fresh_monitor_originals(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_ra_g1_monitor as monitor,
    )

    world = World(tmp_path, count=1)
    port, config, out, scratch = ra_lp_runtime(world, monkeypatch)
    cli.execute("plan-calibration", cli.Session(port, config, out, scratch, H))
    session = port.ra_resource_session

    def guard():
        b.require(world.clock.now_ns() < port.deadline, "RA_G1_DEADLINE")

    def original(name):
        return io.metadata(io.read(session.root / (name + ".record"), limit=8192))

    protocol = monitor.reopen_phase_protocol(
        binding_sha256=port.ra_binding_sha256,
        selection_sha256=port.ra_binding["selection_sha256"],
        phase_id=session.phase,
        closure=original("preopening"),
        opener_return=original("opener_return"),
        monitor_terminal=original("monitor_terminal"),
        deadline_ns=port.deadline,
        check=guard,
        clock_ns=world.clock.now_ns,
    )
    # A tiny no-input child supplies a genuine OS wait status. This remains a
    # synthetic protocol test and never claims a representative/live job PASS.
    pid = os.posix_spawn(
        sys.executable, [sys.executable, "-c", "pass"], {"PATH": os.defpath}
    )
    actual_pid, status = os.waitpid(pid, 0)
    assert actual_pid == pid and os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
    child = {
        "pid": pid,
        "wait_status": status,
        "acquired_mono_ns": world.clock.now_ns(),
    }
    child_path = session.root / "child_return.record"
    io.write(child_path, b.canonical(child))
    terminal_path = session.root / "phase_terminal.record"

    def persist(value, check):
        check()
        io.write(terminal_path, b.canonical(value))
        check()
        return io.metadata(io.read(terminal_path, limit=8192))

    terminal = monitor.verify_tail(
        protocol=protocol,
        monitor_path=session.writer.path,
        selected=port.ra_selection,
        seed_sha256=session.seed,
        child_result=child,
        genuine_wait_status=status,
        expected_child_pid=pid,
        current_counter_sha256=b.digest(port.resource_monitor_counters()),
        persist_terminal=persist,
        original_observation_reader=lambda digest: monitor.read_original_observation(
            session.original_root / (digest + ".record"),
            expected_sha256=digest,
            check=guard,
            charge_read=port.charge_ra_original_read,
            test_only=True,
        ),
        test_only=True,
        worker_validation=original("worker_validation"),
        charge_read=port.charge_ra_original_read,
    )
    setup_tail_charges = []
    rs.verify_setup_tail(
        port.ra_pending_record,
        child,
        check=guard,
        clock_ns=world.clock.now_ns,
        charge=lambda size, creates: setup_tail_charges.append((size, creates)),
        read_charge=port.charge_ra_original_read,
        current_counter_sha256=b.digest(port.resource_monitor_counters()),
        test_only=True,
        genuine_wait_status=status,
        expected_child_pid=pid,
    )
    assert setup_tail_charges == [(8192, 1)]
    # A source-owned successful supervisor return is retained separately from
    # child evidence; the release cannot predict it before it exists.
    returned = {
        "pid": pid,
        "returncode": 0,
        "acquired_mono_ns": world.clock.now_ns(),
        "phase_terminal_sha256": b.digest(terminal),
    }
    return_path = session.root / "supervisor_return.record"
    io.write(return_path, b.canonical(returned))
    pending = port.ra_pending_record
    charged = []
    with pytest.raises(c.Stage12Error):
        rs.finalize_worker_pending(
            output_parent=world.root,
            pending_record=pending,
            phase_terminal_path=terminal_path,
            child_result_path=child_path,
            supervisor_return_path=return_path,
            actual_supervisor_returncode=1,
            expected_supervisor_pid=pid,
            check=guard,
            clock_ns=world.clock.now_ns,
            clock_utc=world.clock.utc,
            charge=lambda *args: charged.append(args),
            read_charge=port.charge_ra_original_read,
        )
    assert charged == []
    rs.finalize_worker_pending(
        output_parent=world.root,
        pending_record=pending,
        phase_terminal_path=terminal_path,
        child_result_path=child_path,
        supervisor_return_path=return_path,
        actual_supervisor_returncode=0,
        expected_supervisor_pid=pid,
        check=guard,
        clock_ns=world.clock.now_ns,
        clock_utc=world.clock.utc,
        charge=lambda *args: charged.append(args),
        read_charge=port.charge_ra_original_read,
    )
    assert charged == [(8192, 1)]
    historical = SimpleNamespace(
        settings=port.settings,
        resource_binding=port.resource_binding,
        records=port.records,
        authority=port.authority,
        test_only=True,
        check_deadline=guard,
        charge_ra_original_read=port.charge_ra_original_read,
    )
    assert rs.require_worker_success(historical, 1)["native_maximum"] == "NOT_PROVEN"
    original_file = next((session.root / "originals").iterdir())
    original_file.write_bytes(b"mutated original")
    with pytest.raises(c.Stage12Error):
        rs.require_worker_success(historical, 1)

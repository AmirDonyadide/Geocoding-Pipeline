from dataclasses import replace
import pytest
from stage12_b2_synthetic import World, H, offline
from test_stage12_b2_publication import publish_world
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_contract as b
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_calibration as cal
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_publication as pub
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import s12_b2_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def test_full_synthetic_calibration_direct_N_and_final_publication(tmp_path):
    world = World(tmp_path)
    selection = cal.select(
        world.catalog,
        tmp_path / "selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    assert selection["ordinary_observations"] == 16
    readers = []
    campaigns = []
    publication_specs = []
    for i, intent in enumerate(selection["intents"]):
        inputs = world.inputs(
            size=intent["size"],
            kind=intent["kind"],
            repetition=intent["repetition"],
            subset=intent["subset"],
        )
        world.run("segment_" + str(i), inputs=inputs)
        root = tmp_path / ("published_" + str(i))
        expected, validate, closure = publish_world(
            world, inputs, tmp_path / ("segment_" + str(i)), root
        )
        readers.append(
            pub.ArtifactReader(
                root,
                expected,
                scratch=tmp_path / ("reader_" + str(i) + ".sqlite"),
                catalog=world.catalog,
                rules=world.rules,
                validate_artifact=validate,
            )
        )
        campaigns.append(closure)
        publication_specs.append({"path": str(root), "manifest_sha256": expected.hex()})
    observations = [r.observation for r in readers]
    comparisons = []

    def evaluate():
        return cal.evaluate(
            world.catalog,
            selection,
            observations,
            window_hash=world.window_hash,
            selection_hash=world.selection_hash,
            authority=world.gate,
            comparison_writer=lambda row: None,
        )

    report = evaluate()
    assert (
        report["eligible_limits"] == [1, 3, 5]
        and report["proposed_limit"] == 1
        and report["scientific_N_selected"] is False
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
    decision = {
        "schema_version": "stage12_n_decision_b2_v1",
        "window_plan_sha256": world.window_hash,
        "calibration_inventory_sha256": b.digest(inventory),
        "adequacy_report_sha256": b.digest(report),
        "owner_delegation_sha256": H,
        "result_limit": 1,
        "retrieval_policy_id": c.policy(1)["retrieval_policy_id"].hex(),
        "decision": "SELECTED",
        "decided_utc": world.clock.utc(),
    }
    # This record is tied only to the synthetic window; no actual N is selected.
    inputs = world.inputs(size=1, kind="DIRECT_N")
    world.run("direct", inputs=inputs)
    profile, plan, start, science, admission, rows = inputs
    snap = b.parse(io.read(tmp_path / "direct/snapshot.json"), o.SNAPSHOT)
    closure = world.put(
        {
            "schema_version": "stage12_campaign_closure_b2_v1",
            "window_plan_sha256": world.window_hash,
            "campaign_start_sha256": b.digest(science),
            "ordered_segment_closure_hashes": [snap["segment_closure_sha256"]],
            "workload_sha256": b.digest(plan),
            "workload_kind": "DIRECT_N",
            "operator_campaign_account_sha256": H,
            "account_status": "NO_KNOWN_INTERVENTION",
            "disposition": "CLOSED_OBSERVATIONAL",
            "reviewed_utc": world.clock.utc(),
            "review_decision_sha256": H,
        }
    )
    window = world.put(
        {
            "schema_version": "stage12_window_closure_b2_v1",
            "window_plan_sha256": world.window_hash,
            "ordered_campaign_closure_hashes": campaigns + [closure],
            "operator_campaign_account_sha256": H,
            "account_status": "NO_KNOWN_INTERVENTION",
            "disposition": "CLOSED_OBSERVATIONAL",
            "reviewed_utc": world.clock.utc(),
            "review_decision_sha256": H,
        }
    )

    def verify():
        def receipt(work, event):
            return audit.reopen(
                tmp_path
                / "direct/attempts"
                / f"{work['work_id']:020d}_{event['attempt']:02d}",
                **world.rules.kwargs(),
            )[0]

        return recovery.reopen(
            tmp_path / "direct",
            start,
            profile,
            plan,
            works=lambda: iter(rows),
            verify_receipt=receipt,
            scratch=tmp_path / ("final_verify_" + world.nonce() + ".sqlite"),
            authority=world.gate,
        )

    from safe_geocoding_pipeline.preprocessing.stages import s12_b2_phase_io as phase_io

    direct_reader = phase_io.CampaignReader(
        tmp_path / "direct",
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        closure_hash=closure,
        scratch=tmp_path / "actual_direct_reader",
        control_adapters={},
    )
    direct = direct_reader.observation
    retention = lambda: cal.direct_n(
        world.catalog,
        observations[0],
        direct,
        N=1,
        decision=decision,
        authority=world.gate,
        comparison_writer=lambda row: None,
    )
    expected = pub.publish_campaign(
        tmp_path / "final",
        tmp_path / "final_work",
        segment=tmp_path / "direct",
        start=start,
        scientific_start=science,
        profile=profile,
        plan=plan,
        catalog=world.catalog,
        rules=world.rules,
        gate=world.gate,
        campaign_closure_hash=closure,
        verify_campaign=verify,
        memory_bytes=64 * 1024 * 1024,
        window_closure_hash=window,
        calibration_inventory=inventory,
        n_decision=decision,
        verify_calibration=evaluate,
        verify_final_retention=retention,
    )
    assert (tmp_path / "final/_COMMITTED").exists()
    assert (
        io.metadata(io.read(tmp_path / "final/manifest.json"))["kind"]
        == b.SYNTHETIC + "_" + pub.FINAL
    )
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing import stage12_development_cli as cli

    world.gate.selection_hash = world.selection_hash
    port = SimpleNamespace(
        test_only=True,
        population_scope=b.SYNTHETIC,
        authority=world.gate.authority,
        records=world.records,
        gate=world.gate,
        segment=tmp_path / "direct",
        response_rules=world.rules,
        control_adapters={},
        open_catalog=lambda: world.catalog,
        verify_campaign=verify,
    )
    config = {
        "N_decision_sha256": world.put(decision),
        "campaign_closure_sha256": closure,
        "publication_path": str(tmp_path / "final"),
        "manifest_sha256": expected.hex(),
        "calibration_publications": publication_specs,
        "external_sort_memory_bytes": 64 * 1024 * 1024,
    }
    reopened = cli.execute(
        "reopen",
        cli.Session(
            port, config, tmp_path / "unused_output", tmp_path / "cli_final_reopen", H
        ),
    )
    assert reopened["service_evidence_state"] == "CLOSED_OBSERVATIONAL"
    direct_reader.close()
    changed = replace(observations[1], window_plan_sha256=H)
    with pytest.raises(c.Stage12Error, match="WINDOW_TRANSFER_FORBIDDEN"):
        cal.evaluate(
            world.catalog,
            selection,
            [observations[0], changed, *observations[2:]],
            window_hash=world.window_hash,
            selection_hash=b.digest(selection),
            authority=world.gate,
            comparison_writer=lambda row: None,
        )
    for reader in readers:
        reader.close()


def memory_observations(world, selection, mutation=None):
    """Actual v1 projection on tiny invented bytes; no publication/capacity claim."""
    from stage12_synthetic import body, feature
    from safe_geocoding_pipeline.preprocessing.stages import s12_response as response

    observations = []
    for i, intent in enumerate(selection["intents"]):
        identifiers = (
            sorted(intent["subset"])
            if intent["subset"] is not None
            else [r["query_semantic_id"].hex() for r in world.catalog.semantics()]
        )

        def read(q, intent=intent, i=i):
            features = [feature()] * min(2, intent["size"])
            if mutation == "tail_novel" and intent["kind"] == "TAIL":
                features = [feature()] * 2 + [feature()]
                features[-1]["properties"]["name"] = "invented novel tail"
            if (
                mutation == "repeat_difference"
                and intent["kind"] == "TAIL"
                and intent["repetition"] == 1
            ):
                features[0] = feature()
                features[0]["properties"]["confidence"] = 0.123
            if (
                mutation == "paired_loss"
                and intent["kind"] == "PAIRED"
                and intent["size"] == 1
            ):
                features[0] = feature()
                features[0]["properties"]["name"] = "different paired response"
            raw = body(features)
            projection = response.extract(
                raw,
                b.sha(q + str(i).encode()),
                size=intent["size"],
                layers=world.rules.layers,
                sources=world.rules.sources,
                expected_echo={},
                http_status=200,
                content_type="application/json",
                encoding="absent",
            )
            return projection, raw

        observations.append(
            cal.Observation(
                intent["kind"],
                intent["size"],
                intent["repetition"],
                b.SYNTHETIC,
                world.window_hash,
                len(identifiers),
                o.manifest_digest(identifiers),
                b.sha(str(i).encode()).hex(),
                H,
                H,
                read,
                lambda identifiers=identifiers: (bytes.fromhex(q) for q in identifiers),
                lambda: None,
            )
        )
    return observations


@pytest.mark.parametrize(
    "mutation,disposition",
    [
        ("tail_novel", "INSUFFICIENT_CALIBRATION_DEPTH"),
        ("repeat_difference", "REPEAT_DISAGREEMENT"),
        ("paired_loss", "ELIGIBLE_FOR_OWNER_REVIEW"),
    ],
)
def test_full_population_tail_and_pair_failures(tmp_path, mutation, disposition):
    world = World(tmp_path)
    selection = world.selection
    result = cal.evaluate(
        world.catalog,
        selection,
        memory_observations(world, selection, mutation),
        window_hash=world.window_hash,
        selection_hash=world.selection_hash,
        authority=world.gate,
        comparison_writer=lambda row: None,
    )
    assert result["disposition"] == disposition
    assert result["scientific_N_selected"] is False
    if mutation == "paired_loss":
        assert 1 not in result["eligible_limits"]
    else:
        assert result["eligible_limits"] == []


@pytest.mark.parametrize(
    "mutation",
    ["missing_repeat", "partial_population", "changed_window", "missing_context"],
)
def test_calibration_rejects_missing_population_and_other_window(tmp_path, mutation):
    world = World(tmp_path)
    selection = world.selection
    observations = memory_observations(world, selection)
    if mutation == "missing_repeat":
        observations = observations[:-1]
    elif mutation == "partial_population":
        observations[0] = replace(
            observations[0], semantic_ids=lambda: iter([]), semantic_count=0
        )
    elif mutation == "changed_window":
        observations[0] = replace(observations[0], window_plan_sha256=H)
    else:
        world.catalog.db.execute(
            "update context set metadata=?",
            (b.canonical({"synthetic_tampering": True}),),
        )
        world.catalog.db.commit()
    with pytest.raises(c.Stage12Error):
        cal.evaluate(
            world.catalog,
            selection,
            observations,
            window_hash=world.window_hash,
            selection_hash=world.selection_hash,
            authority=world.gate,
            comparison_writer=lambda row: None,
        )


def test_witness_unknown_opaque_and_confidence_semantics(tmp_path):
    from stage12_synthetic import body, feature
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_response as response,
        s09_reference_contract as s9,
    )

    world = World(tmp_path)
    context = next(
        world.catalog.contexts(next(world.catalog.semantics())["query_semantic_id"])
    )

    def project(f):
        return response.extract(
            body([f]),
            bytes.fromhex(H),
            size=5,
            layers=world.rules.layers,
            sources=world.rules.sources,
            expected_echo={},
            http_status=200,
            content_type="application/json",
            encoding="absent",
        ).candidates[0]

    f = feature()
    candidate = project(f)
    original = cal.tokens(candidate, f, context)
    changed = feature()
    changed["properties"]["confidence"] = 0.125
    assert cal.tokens(project(changed), changed, context) == original
    changed["properties"]["unknown_synthetic_extension"] = {"digits": "01"}
    assert cal.tokens(project(changed), changed, context) != original
    channel = {
        "kind": "SOURCE_POSTCODE",
        "candidate_field": "postalcode",
        "comparison_method": s9.EXACT_NORM,
        "source_value": "",
        "granularity": "FULL_POSTCODE",
        "candidate_granularity": "FULL_POSTCODE",
        "origin_claim_key": "synthetic original claim",
        "ancestry_group": "synthetic common source",
        "dependence_class": "SELF/DERIVED_FROM",
        "positive_reference": False,
        "origin_record_sha256": H,
    }
    assert cal.tokens(candidate, f, {**context, "channels": [channel]}) == original
    channel["source_value"] = "different"
    assert cal.tokens(candidate, f, {**context, "channels": [channel]}) == original


def test_all_context_joint_strata_and_zero_query_mapback(tmp_path):
    import json
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_b2_catalog as cat,
        s11_semantic_contract as s11,
        s10_query_contract as s10,
    )

    world = World(tmp_path)
    semantic = next(world.catalog.semantics())
    core = semantic["core"]
    q = semantic["query_semantic_id"]
    intent = (
        s10.full_intent(core["text"], "DE")
        if core["search_mode"] == "FULL_TEXT"
        else {
            "endpoint": core["endpoint"],
            "search_mode": core["search_mode"],
            "text": None,
            "address": core["address"],
            "postalcode": core["postalcode"],
            "locality": core["locality"],
            "boundary_country": "DE",
        }
    )
    # Use a full-text invented core to keep the fixture's lineage unambiguous.
    intent = s10.full_intent("One shared invented request", "DE")
    core = s11.project(intent, s10.MODE)
    q = s11.semantic_id(s11.core_bytes(core))
    semantic = {"query_semantic_id": q, "core": core}
    contexts = []
    hypotheses = []
    mapping = []
    families = []
    for i in range(3):
        u = b.sha(f"joint context{i}".encode())
        source = b.sha(f"joint source{i}".encode())
        h = b.sha(f"joint hypothesis{i}".encode())
        contexts.append(
            {
                "query_context_id": u.hex(),
                "stable_source_row_id_v1": source.hex(),
                "country": "DE",
                "script": "Latin" if i != 1 else "Cyrillic",
                "capability": "SYNTHETIC_NONE",
                "completeness": [True, False, False, False],
                "representation": "STANDARD" if i != 1 else "NATIVE",
                "channels": [],
                "origin_sha256": H,
            }
        )
        if i < 2:
            hypotheses.append(
                {
                    "hypothesis_id": h,
                    "query_context_id": u,
                    "stable_source_row_id_v1": source,
                    "stage08_representation": contexts[-1]["representation"],
                    "intent": intent,
                    "selection_status": s10.MODE,
                }
            )
            mapping.append({"hypothesis_id": h, "query_semantic_id": q})
            families.append(
                {
                    "query_context_id": u,
                    "hypothesis_id": h,
                    "family": "Q1" if i == 0 else "Q6",
                }
            )
    mapping.sort(key=lambda x: x["hypothesis_id"])
    binding = {
        **world.catalog.binding,
        "semantic_count": 1,
        "map_count": 2,
        "source_count": 3,
        "semantic_sha256": s11.relation_digest("semantic_request", 1, [semantic]).hex(),
        "map_sha256": s11.relation_digest("hypothesis_request_map", 2, mapping).hex(),
    }
    catalog = cat.Catalog.build(
        tmp_path / "joint.sqlite",
        binding,
        semantics=lambda: iter([semantic]),
        mapping=lambda: iter(mapping),
        hypotheses=lambda: iter(hypotheses),
        contexts=lambda: iter(contexts),
        families=lambda: iter(families),
        authority=world.gate.authority,
    )
    stratum = json.loads(catalog.db.execute("select body from stratum").fetchone()[0])
    assert len(stratum[2]) == 2 and {tuple((x[0], x[3], x[4])) for x in stratum[2]} == {
        ("Latin", "STANDARD", "Q1"),
        ("Cyrillic", "NATIVE", "Q6"),
    }
    result = cal.select(
        catalog,
        tmp_path / "joint_selection.sqlite",
        C=5,
        T=12,
        supported=40,
        authority=world.gate,
        decision_hash=H,
    )
    assert result["tail"] == [q.hex()] and all(
        x["selected_sources"] >= x["required_sources"] for x in result["coverage"]
    )
    back = list(catalog.mapback())
    assert len(back) == 3 and sum(x["query_semantic_id"] is None for x in back) == 1

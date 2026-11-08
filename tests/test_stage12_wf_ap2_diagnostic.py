"""Metadata and fail-closed gate tests only; never run the paced diagnostic."""

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from stage12_synthetic import body
from test_stage12_public_matrix import configuration
from test_stage12_public_operations_v2 import H, offline  # noqa: F401
from test_stage12_wf_ap2_assurance import m2_inputs
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.preprocessing.stages import s12_public_matrix as matrix
from safe_geocoding_pipeline.preprocessing.stages import (
    s12_public_response as validation,
)
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_contract as a


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "wf_ap2_diagnostic_test", ROOT / "scripts/stage12_wf_ap2_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


def metadata_draft():
    config = configuration()
    config.update(
        version=diagnostic.CONFIG_VERSION,
        transport={"scope": diagnostic.SCOPE, "authority": "TEST_ONLY_NO_NETWORK"},
    )
    config["public_validation_sha256"] = a.digest(
        validation.descriptor(validation.CORPUS_VERSION)
    )
    config["sources"] = {
        role: diagnostic.digest(
            dict(
                version="stage12_diagnostic_test_authority_v1",
                scope=diagnostic.SCOPE,
                role=role,
                authority="TEST_ONLY_NO_SERVICE",
            )
        )
        for role in ("owner", "operator", "policy_freeze", "selection", "transport")
    }
    _, _, template, _, _ = m2_inputs()
    inventory = {"scope": "METADATA_TEST_ONLY_NEVER_LIVE_EVIDENCE"}
    selected, phases, response_keys = [], [], set()
    for number, ((label, duration, hold, count), source_index) in enumerate(
        zip(diagnostic.PHASES, (0, 9, 10, 0), strict=True), 1
    ):
        item = deepcopy(config["campaigns"][source_index])
        item.pop("ascending_sizes")
        item["label"] = label
        profile, plan = item["profile"], item["plan"]
        profile.pop("resource_sample_period_ms")
        profile.update(
            schema_version=a.PROFILE,
            rule_bundle_sha256=a.RULE_BUNDLE,
            sampling_policy_sha256=a.POLICY_SHA,
            sampling_runtime_bound_sha256=H,
            transport_profile_sha256=a.digest(config["transport"]),
            policy_freeze_record_sha256=config["sources"]["policy_freeze"],
            **a.assurance_fields(),
        )
        profile["operator_allowance"]["record_sha256"] = config["sources"]["operator"]
        profile["monitoring"]["gaps_record_sha256"] = config["sources"]["selection"]
        profile["states"][0]["evidence_sha256"] = config["sources"]["selection"]
        profile["resources"]["resource_review_sha256"] = config["sources"]["selection"]
        profile["resources"]["capacity_basis_sha256"] = config["sources"]["selection"]
        config["resources"] = deepcopy(profile["resources"])
        work, recipes = matrix.work_for(
            source_index, profile["transport_profile_sha256"]
        )
        work = work[:count]
        item["work"] = work
        plan["control_recipes"] = recipes
        plan["blocks"][0]["observation_ids"] = [row["work_id"] for row in work]
        for budget in (plan["budgets"], plan["blocks"][0]["budget"]):
            budget.update(
                data_observations=0 if number == 3 else count,
                required_control_observations=count if number == 3 else 0,
                data_attempts=0 if number == 3 else 5 * count,
                control_http_attempts=5 * count if number == 3 else 0,
                event_count=50000,
                active_duration_ms=duration,
            )
        observations = (duration + 49) // 50 + 2
        members = 4 * observations + 8
        plan.update(
            schema_version=a.PLAN,
            operations_profile_sha256=a.digest(profile),
            work_manifest_sha256=a.manifest_digest(work),
            history_limits=dict(
                maximum_entries=100000,
                maximum_name_bytes=256,
                maximum_total_name_bytes=25600000,
                page_entries=8,
                maximum_depth=8,
                maximum_file_bytes=2**26,
            ),
            sampling_budget=dict(
                maximum_segments=1,
                maximum_observations=observations,
                maximum_inventory_versions_per_segment=8,
                additional_event_tokens=2 * observations + 4,
                additional_file_data_bytes=4096 * members + 8 * (512 * members + 4096),
                additional_file_entries=members + 8,
            ),
        )
        start = deepcopy(template)
        start.update(
            client_git_sha="a" * 40,
            campaign_id=a.digest(label),
            profile_sha256=a.digest(profile),
            plan_sha256=a.digest(plan),
            runtime_inventory_sha256=a.digest(inventory),
            policy_freeze_record_sha256=config["sources"]["policy_freeze"],
            implementation_authorization_sha256=config["sources"]["owner"],
            initial_workload_authority_sha256=config["sources"]["owner"],
        )
        phases.append(
            dict(
                label=label,
                start=start,
                epoch_id=a.digest([label, "epoch"]),
                hold_regular_acks=hold,
            )
        )
        selected.append(item)
        if number < 3:
            response_keys.update(
                (row["fixture_id"], row["result_limit"]) for row in work
            )
    config["campaigns"] = selected
    config["command_paths"] = dict(
        source="/UNISSUED/source",
        input="/UNISSUED/input.json",
        output="/UNISSUED/output",
        evidence_bundle="/UNISSUED/evidence",
    )
    config = {key: config[key] for key in diagnostic._CONFIG}
    raw = body([]).decode("utf8")
    return dict(
        version=diagnostic.VERSION,
        scope=diagnostic.SCOPE,
        source_sha="a" * 40,
        selection=dict(status="UNISSUED", authority_sha256=H, resource_review_sha256=H),
        limits=dict(
            seconds=7200,
            maximum_bytes=512 * 2**30,
            maximum_creations=300000,
            rss_bytes=6 * 2**30,
            maximum_input_bytes=4 * 2**20,
            summary_reserve_bytes=2**20,
            native_helper_bytes_reserve=128 * 2**20,
            native_helper_creation_reserve=64,
        ),
        configuration=config,
        phases=phases,
        runtime_inventory=inventory,
        responses=[
            dict(
                fixture_id=fixture,
                size=size,
                raw_utf8=raw,
                payload_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                origin="MANUALLY_INVENTED_PUBLIC_BODY",
            )
            for fixture, size in sorted(response_keys)
        ],
    )


def test_prospective_metadata_exact_public_ids_holds_and_new_resource_bounds():
    draft = metadata_draft()
    diagnostic.validate_envelope(draft, "a" * 40, for_execution=False)
    diagnostic.validate_workloads(draft)
    assert [len(item["work"]) for item in draft["configuration"]["campaigns"]] == [
        64,
        32,
        8,
        3,
    ]
    assert [phase["hold_regular_acks"] for phase in draft["phases"]] == [
        1817,
        1572,
        200,
        0,
    ]
    assert (
        draft["limits"]["maximum_bytes"] != 256 * 2**20
        and draft["limits"]["maximum_creations"] != 50000
    )
    assert len(draft["responses"]) == 48
    with pytest.raises(RuntimeError, match="SELECTION_UNISSUED"):
        diagnostic.validate_envelope(draft, "a" * 40, for_execution=True)


@pytest.mark.parametrize(
    "mutation",
    [
        "legacy",
        "missing_resource",
        "unknown_resource",
        "legacy_wire",
        "wrong_hold",
        "wrong_public_id",
        "response_origin",
        "wrong_hash",
        "old_profile",
        "source",
        "source_start",
        "resource_budget",
    ],
)
def test_incompatible_or_unknown_metadata_rejects_without_dispatch(mutation):
    data = metadata_draft()
    if mutation == "legacy":
        data["version"] = "stage12_complete_matrix_synthetic_input_v2"
    elif mutation == "missing_resource":
        data["limits"].pop("maximum_creations")
    elif mutation == "unknown_resource":
        data["limits"]["imagined_entitlement"] = 1
    elif mutation == "legacy_wire":
        data["checkpoints"] = {"records_per_checkpoint": 128}
    elif mutation == "wrong_hold":
        data["phases"][0]["hold_regular_acks"] -= 1
    elif mutation == "wrong_public_id":
        data["responses"][0]["fixture_id"] = "f" * 64
    elif mutation == "response_origin":
        data["responses"][0]["origin"] = "PROTECTED"
    elif mutation == "wrong_hash":
        data["responses"][0]["payload_sha256"] = "f" * 64
    elif mutation == "old_profile":
        data["configuration"]["campaigns"][0]["profile"]["schema_version"] = (
            "stage12_transport_operations_v3"
        )
    elif mutation == "source":
        data["source_sha"] = "b" * 40
    elif mutation == "source_start":
        data["phases"][0]["start"]["client_git_sha"] = "b" * 40
    else:
        data["limits"]["maximum_creations"] = 50000
    with pytest.raises((RuntimeError, a.c.Stage12Error)):
        diagnostic.validate_envelope(data, "a" * 40, for_execution=False)
        diagnostic.validate_workloads(data)


def test_live_proof_adapter_cannot_admit_synthetic_memory_even_with_test_flag():
    reached = []

    class Original:
        clock = None
        configuration_scope_sha256 = H
        test_only = True

        def sampling_bound(self, *args):
            return {"evidence_origin": "SYNTHETIC_TEST_ONLY"}

        def enforcement_facts(self, *args):
            reached.append(True)

    adapter = diagnostic.LiveProofDiagnosticAuthority(Original())
    assert (
        adapter.test_only is False
        and adapter.diagnostic_authority == "TEST_ONLY_NO_SERVICE"
    )
    with pytest.raises(RuntimeError, match="LIVE_M2_REQUIRED"):
        adapter.sampling_bound({}, {})
    with pytest.raises(RuntimeError, match="LIVE_M2_REQUIRED"):
        adapter.enforcement_facts({"evidence_origin": "SYNTHETIC_TEST_ONLY"})
    assert not reached


def test_representative_review_cannot_reinterpret_full_matrix_family(tmp_path):
    data = metadata_draft()
    wrong = dict(
        version="stage12_wf_ap2_public_review_binding_v1",
        scope=diagnostic.SCOPE,
        disposition="PASS",
        configuration_sha256=diagnostic.digest(data["configuration"]),
        report_sha256=H,
        source_files=[],
        sampling_evidence={},
    )
    with pytest.raises(RuntimeError):
        diagnostic.build_live_authority(data, tmp_path, wrong, H, ROOT, "a" * 40, NS())
    assert diagnostic.CONFIG_VERSION != a.CONFIG


def test_goethe_gate_precedes_input_payload_or_guard_install(tmp_path, monkeypatch):
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    reached = []
    monkeypatch.setattr(
        diagnostic, "install_denials", lambda *args: reached.append(True)
    )
    args = NS(
        source=ROOT,
        evidence_bundle=None,
        evidence_review_sha256=None,
        input=tmp_path / "never_opened",
        output=tmp_path / "never_created",
    )
    with pytest.raises(ExecutionPolicyError):
        diagnostic.execute(args, started_ns=0, cpu_started_ns=0)
    assert not reached and not args.output.exists()


def test_python_path_policy_denies_protected_credentials_and_source_writes(tmp_path):
    source = tmp_path / "source"
    output = tmp_path / "output"
    evidence = tmp_path / "evidence"
    payload = tmp_path / "input"

    def allows(path, write=False):
        return diagnostic.open_allowed(
            path,
            write=write,
            source=source,
            output=output,
            input_path=payload,
            evidence=evidence,
        )

    assert allows(source / "src/a.py") and allows(output / "chunk.bin", True)
    # A literal proc spelling is no longer permission on an unsupported host.
    # Actual Linux requires the current-process binding; fake-Linux installed
    # audit/M2-original-reader coverage is in test_stage12_wf_ap2_entrypoint.
    assert allows("/proc/self/status") == (sys.platform == "linux")
    assert allows("/sys/fs/cgroup/job/memory.max")
    for path in (
        source / "data/HOLDOUT.csv",
        tmp_path / "protected.csv",
        source / ".git/config",
        source / "src/.env",
        tmp_path / ".ssh/id_rsa",
    ):
        assert not allows(path)
    assert not allows(source / "src/a.py", True) and not allows(
        evidence / "record", True
    )


def test_descriptor_is_nonlive_and_existing_launcher_remains_exact_and_opt_in():
    path = (
        ROOT
        / "docs/scientific_assets/stage12_wf_ap2_representative_diagnostic_input_v1.json"
    )
    assert path.read_bytes() == diagnostic.canonical(diagnostic.descriptor())
    assert diagnostic.descriptor()["live_instance"] is False
    launcher = (
        ROOT / "cluster/goethe_nhr/stage12_diverse_offline_diagnostic.sbatch"
    ).read_text()
    assert "STAGE12_DIAGNOSTIC_WF_AP2:-0" in launcher
    assert "rev-parse HEAD)" in launcher and "status --porcelain)" in launcher
    assert "--evidence-review-sha256" in launcher and "--wf-ap2" in launcher


def test_preparer_can_only_write_unissued_canonical_metadata(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "wf_ap2_preparer_test", ROOT / "scripts/stage12_prepare_wf_ap2_diagnostic.py"
    )
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    data = metadata_draft()
    path = tmp_path / "draft.json"
    output = tmp_path / "input.json"
    path.write_bytes(diagnostic.canonical(data))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare",
            "--draft",
            str(path),
            "--source-sha",
            "a" * 40,
            "--output",
            str(output),
        ],
    )
    prepare.main()
    assert output.read_bytes() == diagnostic.canonical(data)
    output.unlink()
    data["selection"]["status"] = "ISSUED"
    path.write_bytes(diagnostic.canonical(data))
    with pytest.raises(RuntimeError, match="CANNOT_ISSUE"):
        prepare.main()
    assert not output.exists()

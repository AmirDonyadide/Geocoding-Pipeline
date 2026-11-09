"""Builder metadata fixtures are UNISSUED and wholly synthetic."""

import importlib.util
from pathlib import Path
import pytest
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_s12_ra_g1_core import facts, capacity, selection, H, G
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

ROOT = Path(__file__).resolve().parents[1]


def synthetic_accounting(sources):
    """Explicit nonexistent backend originals: accounting math only, never issued."""
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac

    backends = [
        dict(
            ordinal=i,
            module=name,
            path=f"/SYNTHETIC_NOT_EXECUTABLE/{i}.so",
            identity={
                **dict.fromkeys(ac.IDENTITY, 1),
                "mode": 0o100600,
                "bytes": 4097,
            },
            stat_scope="PREPARATION_HOST_SNAPSHOT",
            sha256=H,
        )
        for i, name in enumerate(ac.MODULES, 1)
    ]
    return ac.compile_inventory(sources, backends, "REPRESENTATIVE_NO_SERVICE")


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_successor_entrypoint_descriptors_match_exact_assets():
    import tomllib

    assert (
        module("stage12_ra_g1_allocation").SOURCE_PROJECT_VERSION
        == tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    )
    for name in ("stage12_ra_g1_allocation", "stage12_ra_g1_diagnostic"):
        item = module(name)
        descriptor = item.descriptor()
        raw = (
            ROOT
            / "docs/scientific_assets"
            / (descriptor["descriptor_version"] + ".json")
        ).read_bytes()
        assert raw == item.canonical(descriptor)
    assert (
        module("stage12_ra_g1_diagnostic")
        .descriptor()["explicit_entrypoint"]
        .endswith("stage12_ra_g1_diagnostic.py")
    )


def test_unissued_builder_exact_shapes_and_no_strict_capacity_certificate():
    m = module("stage12_prepare_ra_g1")
    d = module("stage12_ra_g1_diagnostic")
    allocation = dict(
        source_sha=G,
        valid_from="2026-01-01T00:00:00.000000Z",
        valid_until="2026-01-02T00:00:00.000000Z",
        paths={
            key: f"/SYNTHETIC/NOT_EXECUTABLE/{key}"
            for key in ("source", "input", "output", "evidence")
        },
        replay_sha256=contract.digest(
            __import__("json").loads(
                (
                    ROOT
                    / "docs/scientific_assets/stage12_wf_ap2_representative_replay_v1.json"
                ).read_bytes()
            )
        ),
        accounting=dict(
            identity_calls=100000,
            original_read_calls=1000000,
            original_read_bytes=2**40,
            check_calls=1000000,
        ),
    )
    sources = [{"path": "SYNTHETIC", "bytes": 1, "sha256": H}]
    allocation["source_files"] = sources
    allocation["accounting_inventory"], allocation["accounting"] = synthetic_accounting(
        sources
    )
    env = facts()
    kernel = {"SYNTHETIC_ORIGINALS_ONLY": True}
    env["observation_inventory_sha256"] = contract.digest(kernel)
    bootstrap = dict(
        source_sha=G,
        scope=m.SCOPE,
        facts=env,
        manifest_sha256=H,
        job_id="SYNTHETIC_NOT_A_JOB",
        created_utc="2026-01-01T00:00:00.000000Z",
        runtime_inventory={"SYNTHETIC_ONLY": True},
        capacity=capacity(selection("REPRESENTATIVE_NO_SERVICE")),
        kernel_originals=kernel,
        capacity_originals={
            "root": [["SYNTHETIC_ONLY"]],
            "statvfs": {"SYNTHETIC": True},
        },
        capacity_method={"SYNTHETIC": True},
        capacity_restrictions={"SYNTHETIC": True},
        resource_execution={
            "schema_version": "stage12_resource_execution_request_ra_g1_v1",
            "supervisor_context_path": "/SYNTHETIC/NOT_EXECUTABLE/context.record",
            "supervisor_context_sha256": H,
        },
    )
    review = {"source_sha": G, "disposition": "PASS"}
    data, bundle = m.build(
        allocation,
        bootstrap,
        implementation_report=b"SYNTHETIC INDEPENDENT REVIEW FIXTURE ONLY",
        source_files=sources,
        adoption={"SYNTHETIC": True},
        project_approval={"OWNER_REPORTED_SYNTHETIC": True},
        resource_review=review,
        independent_bootstrap_review={**review, "bootstrap_manifest_sha256": H},
    )
    assert data["selection"]["status"] == "UNISSUED"
    d.validate_envelope(data, G, for_execution=False)
    d.validate_workloads(data)
    assert bundle["binding"]["job_domain_guarantee"] == "NOT_ESTABLISHED"
    assert bundle["diagnostic_resources"]["capacity_entitlement"] == "NOT_ASSERTED"
    assert (
        sum(
            x["plan"]["budgets"]["data_observations"]
            + x["plan"]["budgets"]["required_control_observations"]
            for x in data["configuration"]["campaigns"]
        )
        == 107
    )
    with pytest.raises(RuntimeError):
        d.validate_envelope(data, G, for_execution=True)
    with pytest.raises(c.Stage12Error):
        m.build(
            allocation,
            bootstrap,
            implementation_report=b"SYNTHETIC",
            source_files=[],
            adoption={},
            project_approval={},
            resource_review=review,
            independent_bootstrap_review={**review, "bootstrap_manifest_sha256": H},
            issued=True,
        )


def test_safe_failure_never_expands_tuple_or_echoes_secret():
    diagnostic = module("stage12_ra_g1_diagnostic")
    row = diagnostic.safe_failure(RuntimeError("INVENTED_SECRET_MUST_NOT_APPEAR"))
    assert row == {"family": "UNCLASSIFIED", "code": None, "errno": None}
    assert "INVENTED_SECRET" not in str(row)


def test_successor_cli_completion_requires_matrix_and_diagnostics():
    from safe_geocoding_pipeline.preprocessing import stage12_operations_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import (
        s12_public_runtime as runtime,
    )

    config = {"version": runtime.RA_CONFIG, "campaigns": [{"label": "one"}]}
    result = {
        "full_frozen_capability_matrix_completed": True,
        "completed_phases": ["one"],
        "qualified_public_rates": [],
        "diagnostic_persistence_complete": True,
    }
    assert cli.result_exit_status(config, result) == 0
    for field in (
        "full_frozen_capability_matrix_completed",
        "diagnostic_persistence_complete",
    ):
        bad = dict(result)
        bad[field] = False
        assert cli.result_exit_status(config, bad) == 1


def test_allocation_non_b_partitions_do_not_reset_the_envelope():
    allocation = module("stage12_ra_g1_allocation")
    assert allocation.LIMITS["non_b_bytes"] == (32 + 160 + 32 + 16) * 2**20
    assert allocation.LIMITS["non_b_creations"] == 256 + 1024 + 128 + 136


def test_canonical_duplicate_keys_and_reformatted_bytes_reject():
    allocation = module("stage12_ra_g1_allocation")
    for raw in (b'{"a":1,"a":1}\n', b'{"a": 1}\n'):
        with pytest.raises(RuntimeError):
            allocation.parse(raw)


def test_new_read_rejects_changed_mode_link_and_oversized_original(tmp_path):
    allocation = module("stage12_ra_g1_allocation")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    path = root / "record"
    path.write_bytes(b"original")
    path.chmod(0o600)
    assert allocation.read(path) == b"original"
    with pytest.raises(RuntimeError):
        allocation.read(path, limit=3)
    path.chmod(0o644)
    with pytest.raises(RuntimeError):
        allocation.read(path)
    path.chmod(0o600)
    link = root / "link"
    link.symlink_to(path)
    with pytest.raises(RuntimeError):
        allocation.read(link)


def test_exact_successor_layout_and_no_old_root_alias(tmp_path):
    d = module("stage12_ra_g1_diagnostic")
    controlled = tmp_path / "controlled"
    controlled.mkdir(mode=0o700)
    allocation = controlled / "ra_g1_synthetic"
    allocation.mkdir(mode=0o700)
    bundle = allocation / "binding"
    bundle.mkdir(mode=0o700)
    assert d.public_input_layout(allocation / "input.json", bundle, controlled)
    assert not d.public_input_layout(controlled / "input.json", bundle, controlled)
    assert not d.public_input_layout(allocation / "other.json", bundle, controlled)
    assert not d.public_input_layout(
        allocation / "input.json", allocation / "evidence", controlled
    )


def test_canonical_unicode_agrees_with_runtime_bytes():
    allocation = module("stage12_ra_g1_allocation")
    value = {"invented": "Σão\\\n東京"}
    assert allocation.canonical(value) == c.canonical(value)


def test_context_read_grant_is_readonly_and_does_not_cover_neighbors(tmp_path):
    d = module("stage12_ra_g1_diagnostic")
    params = dict(
        source=ROOT,
        output=tmp_path / "diagnostic",
        input_path=tmp_path / "input.json",
        evidence=tmp_path / "binding",
    )
    assert d.open_allowed(tmp_path / "context.record", write=False, **params)
    assert not d.open_allowed(tmp_path / "context.record", write=True, **params)
    assert not d.open_allowed(tmp_path / "context.record.other", write=False, **params)
    assert not d.open_allowed(tmp_path / "other.record", write=False, **params)

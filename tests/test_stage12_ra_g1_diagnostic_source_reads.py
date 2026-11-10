"""Exact source-read delta; no service or live execution authority is issued."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
from test_stage12_ra_g1_production_binding import (  # noqa: F401
    private_source, production, installed_production_audit,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_read_diagnostic_under_test", ROOT / "scripts/stage12_ra_g1_diagnostic.py")
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)
H = "1" * 64


def row(path, raw):
    return dict(path=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


@pytest.fixture
def source(tmp_path):
    selected = tmp_path / "source"
    selected.mkdir(mode=0o700)
    rows = []
    for name in (".gitignore", "README.md", "AGENTS.md", "docs/PROJECT.md", "src/module.py"):
        path = selected / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = ("SYNTHETIC_ONLY " + name).encode()
        path.write_bytes(raw)
        path.chmod(0o644)  # Existing Git source files need not be private data files.
        rows.append(row(name, raw))
    rows.sort(key=lambda value: value["path"])
    return selected, rows


def policy(root, rows):
    return d._ReviewedSourceReads(root, rows, d.digest(rows))


def allowed(root, path, view=None, *, write=False):
    output = root.parent / "allocation" / "diagnostic"
    return d.open_allowed(path, write=write, source=root, output=output,
        input_path=output.parent / "input.json", evidence=output.parent / "binding", source_reads=view)


def test_new_domains_require_exact_bound_regular_file_membership(source):
    root, rows = source
    view = policy(root, rows)
    for name in (".gitignore", "README.md", "AGENTS.md", "docs/PROJECT.md"):
        assert not allowed(root, root / name)
        assert allowed(root, root / name, view)
        assert not allowed(root, root / name, view, write=True)
    for name in ("unselected.md", "docs/unselected.md", "docs", ".", "docs/missing.md"):
        path = root / name
        if name.endswith("unselected.md"):
            path.write_text("SYNTHETIC_ONLY")
        assert not allowed(root, path, view)
    # Existing bootstrap/import prefixes are retained, not falsely called exact-only.
    assert allowed(root, root / "src/not_selected.py")


@pytest.mark.parametrize("name", [".git/config", ".ssh/config", ".config/token", "credentials/key", ".env", ".env.example", "docs/bad\nname", "docs/bad\x7fname"])
def test_incompatible_selected_secret_and_control_names_reject_at_bind(source, name):
    root, rows = source
    extra = row(name, b"never opened")
    rows = sorted([*rows, extra], key=lambda value: value["path"])
    with pytest.raises(RuntimeError, match="RA_G1_SOURCE_INVENTORY"):
        policy(root, rows)
    assert not allowed(root, root / name)


def test_aliases_directories_and_missing_files_cannot_use_new_read_delta(source):
    root, rows = source
    view = policy(root, rows)
    selected = root / "README.md"
    outside = root.parent / "outside.txt"
    outside.write_text("SYNTHETIC_ONLY")
    selected.unlink()
    selected.symlink_to(outside)
    assert not allowed(root, selected, view)
    selected.unlink()
    selected.mkdir()
    assert not allowed(root, selected, view)
    selected.rmdir()
    assert not allowed(root, selected, view)
    alias = root.parent / "source_alias"
    alias.symlink_to(root, target_is_directory=True)
    assert not allowed(root, alias / "AGENTS.md", view)


def test_immutable_membership_has_no_filesystem_or_hash_acceptance_cache(source):
    root, rows = source
    view = policy(root, rows)
    original = root / "README.md"
    target = root / "not_selected.md"
    rows[3]["path"] = "not_selected.md"
    target.write_text("SYNTHETIC_ONLY")
    assert not allowed(root, target, view)
    original.write_text("changed; membership does not attest content")
    assert allowed(root, original, view)  # Actual source_fence still owns full hashes.
    with pytest.raises(AttributeError):
        view.anything = True
    with pytest.raises(RuntimeError, match="RA_G1_SOURCE_INVENTORY"):
        d._ReviewedSourceReads(root, rows, H)


@pytest.mark.parametrize("name", ["é" * 254 + ".md", "𐀀" * 126 + ".md", "quote\"slash\\.txt"])
def test_streaming_catalog_hash_matches_full_canonical_escaped_bytes(source, name):
    root, rows = source
    rows = sorted([*rows, row(name, b"")], key=lambda value: value["path"])
    view = policy(root, rows)
    entries = [(value["path"],value["bytes"],value["sha256"]) for value in rows]
    assert d._source_read_digest(entries) == d.digest(rows)
    assert tuple(value["path"] for value in rows) == view[1]


def test_oversized_and_noncanonical_catalogs_reject_without_permission(source):
    root, rows = source
    for bad in ([*rows, row("x" * 513,b"")], [row("docs/../README.md",b"")],
                [row("docs//bad.md",b"")], [row("/absolute.md",b"")], rows[::-1], [rows[0],rows[0]]):
        with pytest.raises(RuntimeError, match="RA_G1_SOURCE_INVENTORY"):
            policy(root, bad)
    view = policy(root, rows)
    huge = root / ("x" * 100000)
    assert not view.permits(huge, huge)


def test_streamed_frozen_review_hash_matches_actual_shape(source):
    root, rows = source
    metadata = dict(version=d.REVIEW_VERSION, scope=d.SCOPE, disposition="PASS",
        configuration_sha256=H, report_sha256=H, resource_evidence={"adoptions":(H,)})
    review = {**metadata, "source_files": rows}
    entries = [(value["path"],value["bytes"],value["sha256"]) for value in rows]
    assert d._source_read_digest(entries, metadata) == d.digest(review)
    d._ReviewedSourceReads(root, rows, d.digest(rows), metadata=metadata, review_sha256=d.digest(review))
    with pytest.raises(RuntimeError, match="RA_G1_SOURCE_INVENTORY"):
        d._ReviewedSourceReads(root, rows, d.digest(rows), metadata=metadata, review_sha256="0" * 64)


def test_actual_894_catalog_and_original_files_remain_exact():
    work = os.environ.get("STAGE12_SOURCE_READ_TEST_WORK")
    if work is None:
        pytest.skip("explicit retained original package required for this integration fixture")
    work = Path(work)
    rows = json.loads((work / "BASELINE_SOURCE_INVENTORY.record").read_bytes())
    root = work / "core-author/baseline-private/source"
    assert len(rows) == 894 and sum(value["bytes"] for value in rows) == 15027919
    view = policy(root, rows)
    for value in rows:
        assert allowed(root, root / value["path"], view)
    assert not allowed(root, root / "docs/unselected_private.md", view)
    assert not allowed(root, root / "docs", view)
    assert not allowed(root, root, view)


def test_real_caller_binds_only_after_predecessor_and_before_full_source_fence():
    import ast
    tree = ast.parse((ROOT / "scripts/stage12_ra_g1_diagnostic.py").read_text())
    node = next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef)
                and node.name == "initialize_first_runtime")
    calls = [ast.unparse(item) for item in node.body[:3]]
    assert calls == ["handoff['verify_before_data']()", "guard.bind_reviewed_source_reads(original, bound)", "original.source_fence()"]


def test_actual_controller_installed_legacy_callback_keeps_its_signature(request, monkeypatch):
    """Actual narrowed controller guard, including the real diagnostic hook.

    Native Linux enforcement and proc membership are explicit Mac fixtures in
    installed_production_audit; callbacks, charged file I/O and source fence run.
    """
    case = request.getfixturevalue("production")
    run = case.controller.Run(case.allocation, stage="bind", stage_seconds=720)
    try:
        with installed_production_audit(case, run, monkeypatch) as audit:
            run.mkdir(case.root)
            folder = case.root / "callback_compatibility"
            run.mkdir(folder)
            path = folder / "original.record"
            value = {"SYNTHETIC_ONLY": True}
            run.write(path, value)
            assert case.controller.parse(run.original(path)) == value
            assert list(folder.iterdir()) == [path]
            destination = folder / "renamed.record"
            os.rename(path, destination)
            destination.unlink()
            run.sources()  # Actual complete full-hash/EOF checks under legacy callback.
            assert audit["events"] > 0
            assert run.read_calls > 0 and run.read_bytes > 0
    finally:
        run.close()


@pytest.mark.parametrize("rep_admin", [False, True])
def test_real_ra_assets_use_frozen_common_wire_identity_without_fictional_ra_file(monkeypatch, rep_admin):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as wire
    actual_read = Path.read_bytes
    opened = []
    def read(path):
        opened.append(path.name)
        assert path.name != wire.RA_SCHEMA + ".json"
        return actual_read(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    runtime.verify_successor_assets(ROOT, contract=contract, rep_admin_successor=rep_admin)
    assert wire.SCHEMA + ".json" in opened
    assert len(opened) == (44 if rep_admin else 40)
    assert wire.RA_SCHEMA not in contract.descriptors(rep_admin_successor=rep_admin)


def test_non_ra_actual_asset_verification_and_frozen_descriptor_remain_unchanged():
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as wire
    runtime.verify_successor_assets(ROOT)
    raw = (ROOT / "docs/scientific_assets" / (wire.SCHEMA + ".json")).read_bytes()
    value = wire.descriptor()
    assert raw == runtime.c.canonical(value)
    assert value["descriptor_version"] == wire.SCHEMA
    assert value["header_schema"]["schema"] == "=" + wire.SCHEMA
    assert value["accounting"]["maximum_files"] == 1500


@pytest.mark.parametrize("target", ["common_wire", "selected_ra"])
def test_real_asset_reader_rejects_tampered_selected_or_shared_originals(tmp_path, target):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as wire
    directory = tmp_path / "docs/scientific_assets"
    directory.mkdir(parents=True)
    expected = contract.descriptors(rep_admin_successor=True)
    expected[wire.SCHEMA] = wire.descriptor()
    for name in expected:
        (directory / (name + ".json")).write_bytes((ROOT / "docs/scientific_assets" / (name + ".json")).read_bytes())
    name = wire.SCHEMA if target == "common_wire" else contract.PROFILE
    path = directory / (name + ".json")
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(runtime.c.Stage12Error, match="S12_ASSET_MISMATCH"):
        runtime.verify_successor_assets(tmp_path, contract=contract, rep_admin_successor=True)


@pytest.mark.parametrize("schema,policy,maximum", [
    ("stage12_public_path_timing_v3", "stage12_public_sampling_policy_v2", 1500),
    ("stage12_public_path_timing_ra_g1_v1", "stage12_public_sampling_policy_ra_g1_v1", 2980),
    ("stage12_public_path_timing_ra_g1_v1", "stage12_development_sampling_policy_b2_ap_ra_g1_v1", 1500),
])
def test_actual_instance_policy_pairs_and_file_caps_stay_separate(tmp_path, schema, policy, maximum):
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as wire
    assert wire.selected_max_files(schema, policy) == maximum
    other = wire.RA_POLICY if schema == wire.SCHEMA else wire.POLICY_VERSION
    with pytest.raises(wire.cp.CheckpointError):
        wire.validate_policy_version(other, schema=schema)
    with pytest.raises(wire.cp.CheckpointError, match="CHECKPOINT_LIMIT_INVALID"):
        wire.Checkpoints(tmp_path / "over-cap", timing_binding=dict(policy_sha256=H, source_sha256=H, task_sha256=H),
            phase_windows=[dict(phase_id=1, selected_phase_ms=20000)], cumulative_deadline_ns=100000000000,
            timing_schema=schema, timing_policy_version=policy, max_files=maximum + 1)
    assert not (tmp_path / "over-cap").exists()



def _actual_runtime_comparison_gate(actual, expected):
    """Execute the unchanged comparison statement from the real runner source."""
    import ast
    tree = ast.parse((ROOT / "scripts/stage12_ra_g1_diagnostic.py").read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                    and node.name == "initialize_current_runtime")
    statement = next(node for node in function.body
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name) and node.value.func.id == "require"
        and any(isinstance(argument, ast.Constant) and argument.value == "RA_G1_DIAGNOSTIC_RUNTIME_CHANGED"
                for argument in node.value.args))
    code = compile(ast.fix_missing_locations(ast.Module(body=[statement], type_ignores=[])),
                   str(ROOT / "scripts/stage12_ra_g1_diagnostic.py"), "exec")
    exec(code, {"require": d.require, "actual_runtime": actual,
                "data": {"runtime_inventory": expected}})


def test_runtime_inventory_json_native_rows_preserve_legacy_canonical_bytes(monkeypatch):
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
    distributions = [SimpleNamespace(metadata={"Name": "Zebra"}, version="2.0"),
                     SimpleNamespace(metadata={"Name": "Álpha"}, version="1.0")]
    monkeypatch.setenv("SLURM_JOB_ID", "TEST_ONLY_NOT_A_LIVE_JOB")
    monkeypatch.setattr(runtime.importlib.metadata, "distributions", lambda: iter(distributions))
    value = runtime.runtime_inventory(H)
    assert all(type(pair) is list and all(type(item) is str for item in pair)
               for pair in value["packages"])
    parsed = json.loads(runtime.c.canonical(value))
    assert value == parsed
    legacy = {**value, "packages": sorted((item.metadata["Name"], item.version)
                                          for item in distributions)}
    assert value["packages"] == [["Zebra", "2.0"], ["Álpha", "1.0"]]
    assert runtime.c.canonical(legacy) == runtime.c.canonical(value)
    assert hashlib.sha256(runtime.c.canonical(legacy)).hexdigest() == hashlib.sha256(runtime.c.canonical(value)).hexdigest()
    _actual_runtime_comparison_gate(value, parsed)


@pytest.mark.parametrize("field", ["package_version", "python_version", "backend_sha256"])
def test_fresh_runtime_fields_and_full_native_hashes_still_reject_changes(monkeypatch, field):
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    version = ["1.0"]
    monkeypatch.setenv("SLURM_JOB_ID", "TEST_ONLY_NOT_A_LIVE_JOB")
    monkeypatch.setattr(runtime.importlib.metadata, "distributions", lambda: iter([
        SimpleNamespace(metadata={"Name": "SyntheticVersionFixture"}, version=version[0])]))
    counts = {"calls": 0, "bytes": 0, "checks": 0}
    names = []
    def charge(calls, size):
        counts["calls"] += calls
        counts["bytes"] += size
    def check():
        counts["checks"] += 1
    actual_reader = assurance.bounded_backend_reader(charge)
    def reader(name, path, checkpoint):
        names.append(name)
        return actual_reader(name, path, checkpoint)
    def fresh():
        return runtime.runtime_inventory(H, successor=True, resource_assurance="RA-G1-r1",
            environment_observation_sha256=H, backend_reader=reader, check=check)
    initial = fresh()
    expected = json.loads(runtime.c.canonical(initial))
    before = dict(counts)
    if field == "package_version":
        version[0] = "2.0"
    elif field == "python_version":
        expected["python"] = "TEST_ONLY_DIFFERENT_VERSION"
    else:
        expected["wf_ap2_runtime"]["backends"][0]["binary_sha256"] = "f" * 64
    actual = fresh()
    assert all(counts[key] > before[key] for key in counts)
    assert names == ["_hashlib", "_ssl", "_sqlite3", "_duckdb", "pyarrow.lib"] * 2
    assert all(type(pair) is list for pair in actual["packages"])
    with pytest.raises(RuntimeError, match="RA_G1_DIAGNOSTIC_RUNTIME_CHANGED"):
        _actual_runtime_comparison_gate(actual, expected)

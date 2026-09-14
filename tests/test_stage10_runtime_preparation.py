"""Public-only preparation checks, independent of unfinished Stage 10 families."""

from __future__ import annotations

import copy
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_transliteration as t
from safe_geocoding_pipeline.preprocessing.stages import s10_runtime_lock as lock
from safe_geocoding_pipeline.preprocessing.stages import (
    s10_runtime_validation as checks,
)


@pytest.fixture(scope="module")
def public_runtime():
    configured = os.environ.get("STAGE10_TEST_RUNTIME_ROOT")
    if not configured:
        pytest.skip("Explicit exact public build required")
    root = Path(configured)
    repository = Path(__file__).resolve().parents[1]
    instance = t.ICUTransliterator(
        root,
        root / "runtime_build_lock.json",
        repository / "docs/scientific_assets" / t.SPEC_NAME,
        repository / lock.DEPENDENCIES["CPP_BRIDGE"],
    )
    yield instance, root, repository
    instance.close()


@pytest.mark.parametrize("text,target", checks.SCRIPT_CASES)
def test_pinned_script_gate(text, target):
    assert t.eligible_script(text, check_marks=True) == target


def test_preparation_public_gate_replay(public_runtime):
    instance, root, repository = public_runtime
    actual = checks.validate(root, repository)
    assert actual == c.read_json(root / "runtime_validation.json")
    assert actual["positive_checks"] == 25
    assert actual["fault_checks"] == 12
    assert actual["filter_codepoints_compared"] == 2228224
    assert actual["protected_payloads_accessed"] == 0
    assert actual["runtime_semantic_fingerprint"] == instance.semantic_fingerprint


def test_runtime_semantics_excludes_build_provenance_and_locations(public_runtime):
    instance, _, _ = public_runtime
    changed = copy.deepcopy(instance.lock)
    changed["build_execution"] = {
        "git_sha": "f" * 40,
        "slurm_job_id": "999",
        "timestamp_utc": "2099-01-01T00:00:00Z",
    }
    changed["configure_arguments"] = ["--prefix=/invented/new-location"]
    changed["link_arguments"] = ["/invented/new-location/compiler"]
    for asset in changed["artifacts"]:
        asset["relative_path"] = "invented/" + asset["role"]
    assert lock.semantic_fingerprint(changed) == instance.semantic_fingerprint
    # Exact lock identity is a separate binding and still changes.
    assert c.canonical(changed) != c.canonical(instance.lock)


@pytest.mark.parametrize(
    "field", ["icu_version", "unicode_version", "cldr_version", "direction"]
)
def test_semantic_dependencies_change_fingerprint(public_runtime, field):
    instance, _, _ = public_runtime
    changed = copy.deepcopy(instance.lock)
    changed[field] = "INVENTED_MISMATCH"
    assert lock.semantic_fingerprint(changed) != instance.semantic_fingerprint


def test_data_binary_changes_fingerprint(public_runtime):
    instance, _, _ = public_runtime
    changed = copy.deepcopy(instance.lock)
    changed["artifacts"][-1]["sha256"] = "0" * 64
    assert lock.semantic_fingerprint(changed) != instance.semantic_fingerprint


def test_batch_launcher_has_bounded_public_scope():
    repository = Path(__file__).resolve().parents[1]
    script = (
        repository / "cluster/goethe_nhr/stage10_build_transliteration_runtime.sbatch"
    ).read_text()
    assert "#SBATCH --no-requeue" in script
    assert "--immediate" not in script
    assert "SLURM_RESTART_COUNT" in script
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert "git status --porcelain" in script and "git symbolic-ref" in script
    assert "derived/controlled" not in script
    assert "stage10_build_runtime.py" in script
    assert all(
        command not in script
        for command in ("sbatch ", "scancel ", "git pull", "curl ")
    )


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[1] / "scripts/stage10_build_runtime.py"
    spec = importlib.util.spec_from_file_location("stage10_public_builder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_linux_guard_precedes_any_asset_read(builder, monkeypatch, tmp_path):
    from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError

    monkeypatch.setattr(builder.platform, "system", lambda: "Linux")
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(
        builder.c, "sha256_file", lambda *_: pytest.fail("asset read before guard")
    )
    with pytest.raises(ExecutionPolicyError):
        builder.build(tmp_path / "source", tmp_path / "root", tmp_path, 4)


def test_collision_does_not_write_failure_into_existing_runtime(
    builder, monkeypatch, tmp_path
):
    marker = tmp_path / "original"
    marker.write_text("public synthetic runtime marker")

    def collision(*args, **kwargs):
        raise c.Stage10Error("STAGE10_RUNTIME_BUILD_COLLISION")

    monkeypatch.setattr(builder, "build", collision)
    monkeypatch.setattr(
        "sys.argv",
        [
            "builder",
            "--archive",
            "public-source",
            "--output-root",
            str(tmp_path),
            "--repository",
            str(tmp_path),
        ],
    )
    assert builder.main() == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["original"]


def test_owned_failure_receipt_preserved(builder, monkeypatch, tmp_path):
    target = tmp_path / "new-public-build"

    def owned_failure(archive, root, repository, jobs, *, ownership):
        root.mkdir(mode=0o700)
        info = root.stat()
        ownership.append((info.st_dev, info.st_ino))
        raise c.Stage10Error("STAGE10_SYNTHETIC_BUILD_FAILURE")

    monkeypatch.setattr(builder, "build", owned_failure)
    monkeypatch.setattr(
        "sys.argv",
        [
            "builder",
            "--archive",
            "public-source",
            "--output-root",
            str(target),
            "--repository",
            str(tmp_path),
        ],
    )
    assert builder.main() == 1
    assert c.read_json(target / "runtime_failure_receipt.json") == {
        "status": "FAILED",
        "code": "STAGE10_SYNTHETIC_BUILD_FAILURE",
        "protected_payloads_accessed": 0,
    }


def test_exclusive_json_never_replaces(builder, tmp_path):
    path = tmp_path / "runtime_build_lock.json"
    builder.exclusive_json(path, {"public": "original"})
    with pytest.raises(FileExistsError):
        builder.exclusive_json(path, {"public": "replacement"})
    assert c.read_json(path) == {"public": "original"}


def test_launcher_resolves_only_configured_mount_anchor(tmp_path):
    repository = Path(__file__).resolve().parents[1]
    script = (
        repository / "cluster/goethe_nhr/stage10_build_transliteration_runtime.sbatch"
    ).read_text()
    function = (
        "stage10_public_path() {"
        + script.split("stage10_public_path() {", 1)[1].split("\n}", 1)[0]
        + "\n}"
    )
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    alias = tmp_path / "mount-alias"
    alias.symlink_to(canonical, target_is_directory=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (canonical / "artifact-link").symlink_to(outside, target_is_directory=True)
    environment = {
        **os.environ,
        "stage10_alias": str(alias),
        "stage10_project": str(canonical),
    }
    for source in (alias, canonical):
        completed = subprocess.run(
            [
                "bash",
                "-c",
                function + '\nstage10_public_path "$1"',
                "test",
                str(source / "artifact-link"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        selected = Path(completed.stdout.strip())
        assert selected == canonical / "artifact-link"
        assert selected != selected.resolve()  # Remaining symlink gate rejects it.
    rejected = subprocess.run(
        ["bash", "-c", function + '\nstage10_public_path "$1"', "test", str(outside)],
        env=environment,
        capture_output=True,
    )
    assert rejected.returncode != 0

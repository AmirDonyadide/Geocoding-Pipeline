from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s07_prelaunch
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    ELIGIBILITY_MANIFEST_RELATIVE_PATH,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_prelaunch import (
    BundlePreflightConfig,
    Stage07PrelaunchError,
    SubmissionPreflightConfig,
    run_bundle_preflight,
    run_submission_preflight,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_second_parser_bundle import (
    SecondParserBundleOutcome,
)


REPOSITORY = Path(__file__).resolve().parents[1]


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def _private_file(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def _git_worktree(root: Path) -> tuple[Path, str]:
    worktree = root / "worktree"
    _private_directory(worktree)
    subprocess.run(["git", "init", "-q"], cwd=worktree, check=True)
    subprocess.run(
        ["git", "config", "user.email", "public@example.invalid"],
        cwd=worktree,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Public Synthetic"],
        cwd=worktree,
        check=True,
    )
    marker = worktree / "marker.txt"
    marker.write_text("public synthetic\n", encoding="utf-8")
    subprocess.run(["git", "add", "marker.txt"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=worktree, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "--detach", sha], cwd=worktree, check=True)
    return worktree, sha


def _commit_execution_assets(
    worktree: Path, launcher_text: str
) -> tuple[Path, Path, str]:
    eligibility = worktree / ELIGIBILITY_MANIFEST_RELATIVE_PATH
    eligibility.parent.mkdir(parents=True, exist_ok=True)
    eligibility.write_bytes(
        (REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH).read_bytes()
    )
    launcher = worktree / "cluster/goethe_nhr/stage07_test_launcher.sbatch"
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text(launcher_text, encoding="utf-8")
    subprocess.run(
        [
            "git",
            "add",
            eligibility.relative_to(worktree),
            launcher.relative_to(worktree),
        ],
        cwd=worktree,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-qm", "execution assets"], cwd=worktree, check=True
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return eligibility, launcher, sha


def test_submission_preflight_catches_failures_before_scheduler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, _initial_sha = _git_worktree(controlled)
    required = controlled / "required"
    _private_directory(required)
    eligibility, launcher, sha = _commit_execution_assets(
        worktree,
        "#!/bin/bash\nset -euo pipefail\numask 077\n"
        "#SBATCH --cpus-per-task=4\n#SBATCH --mem=16G\n"
        "#SBATCH --time=00:30:00\n",
    )
    output_parent = controlled / "outputs"
    _private_directory(output_parent)
    output = output_parent / "new-output"
    result = run_submission_preflight(
        SubmissionPreflightConfig(
            controlled_root=controlled,
            integration_root=worktree,
            expected_git_sha=sha,
            new_paths=(output,),
            required_paths=(required,),
            eligibility_manifest_path=eligibility,
            launcher_path=launcher,
            requested_memory_gib=16,
            requested_cpus=4,
            requested_walltime="00:30:00",
            minimum_free_bytes=1,
            minimum_free_inodes=1,
        )
    )
    assert result["status"] == "STAGE07_PRELAUNCH_GATE_PASS"

    output.mkdir()
    with pytest.raises(Stage07PrelaunchError, match="OUTPUT_COLLISION"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(output,),
                required_paths=(required,),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=16,
                requested_cpus=4,
                requested_walltime="00:30:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )

    immutable_bundle = controlled / "immutable-bundle"
    immutable_bundle.mkdir(mode=0o555)
    monkeypatch.setattr(
        s07_prelaunch,
        "validate_second_parser_bundle_metadata_only",
        lambda _path: SimpleNamespace(
            second_parser_bundle_fingerprint="f" * 64,
            manifest_sha256="e" * 64,
            artifact_count=1,
            total_size_bytes=1,
        ),
    )
    with pytest.raises(Stage07PrelaunchError, match="RUNTIME_STATE_POLICY_FAILURE"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(immutable_bundle / "runtime-state",),
                required_paths=(),
                read_only_bundle_paths=(immutable_bundle,),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=16,
                requested_cpus=4,
                requested_walltime="00:30:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )


def test_preflight_rejects_worktree_outside_controlled_root(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, _initial_sha = _git_worktree(tmp_path / "outside")
    eligibility, launcher, sha = _commit_execution_assets(
        worktree,
        "set -euo pipefail\numask 077\n#SBATCH --cpus-per-task=1\n"
        "#SBATCH --mem=1G\n#SBATCH --time=00:01:00\n",
    )
    with pytest.raises(Stage07PrelaunchError, match="CONTROLLED_PATH"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(),
                required_paths=(),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=1,
                requested_cpus=1,
                requested_walltime="00:01:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )


def test_preflight_rejects_launcher_outside_exact_worktree(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, _initial_sha = _git_worktree(controlled)
    eligibility, _tracked_launcher, sha = _commit_execution_assets(
        worktree,
        "set -euo pipefail\numask 077\n#SBATCH --cpus-per-task=1\n"
        "#SBATCH --mem=1G\n#SBATCH --time=00:01:00\n",
    )
    external_launcher = controlled / "external.sbatch"
    _private_file(
        external_launcher,
        "set -euo pipefail\numask 077\n#SBATCH --cpus-per-task=1\n"
        "#SBATCH --mem=1G\n#SBATCH --time=00:01:00\n",
    )
    with pytest.raises(Stage07PrelaunchError, match="GIT_BOUND_PATH_REQUIRED"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(),
                required_paths=(),
                eligibility_manifest_path=eligibility,
                launcher_path=external_launcher,
                requested_memory_gib=1,
                requested_cpus=1,
                requested_walltime="00:01:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )


def test_preflight_rejects_overlapping_new_paths(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, _initial_sha = _git_worktree(controlled)
    eligibility, launcher, sha = _commit_execution_assets(
        worktree,
        "set -euo pipefail\numask 077\n#SBATCH --cpus-per-task=1\n"
        "#SBATCH --mem=1G\n#SBATCH --time=00:01:00\n",
    )
    output_parent = controlled / "outputs"
    _private_directory(output_parent)
    with pytest.raises(Stage07PrelaunchError, match="NEW_PATH_TOPOLOGY_INVALID"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(output_parent / "new", output_parent / "new/runtime"),
                required_paths=(),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=1,
                requested_cpus=1,
                requested_walltime="00:01:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )

    with pytest.raises(Stage07PrelaunchError, match="NEW_PATH_TOPOLOGY_INVALID"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(worktree / "runtime",),
                required_paths=(),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=1,
                requested_cpus=1,
                requested_walltime="00:01:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )


def test_bundle_gate_requires_exact_compute_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    _private_directory(bundle)
    fingerprint = "a" * 64
    monkeypatch.setattr(
        s07_prelaunch,
        "validate_second_parser_bundle",
        lambda *_args, **_kwargs: SecondParserBundleOutcome(
            output_directory=bundle,
            second_parser_bundle_fingerprint=fingerprint,
            second_parser_model_fingerprint="b" * 64,
            second_parser_runtime_fingerprint="c" * 64,
            manifest_sha256="d" * 64,
            artifact_count=12,
            total_size_bytes=34,
            complete_tree_fingerprint="e" * 64,
            complete_tree_entry_count=56,
        ),
    )
    with pytest.raises(Stage07PrelaunchError, match="COMPUTE_SMOKE_REQUIRED"):
        run_bundle_preflight(
            BundlePreflightConfig(
                bundle_directory=bundle,
                expected_bundle_fingerprint=fingerprint,
                expected_smoke_git_sha="f" * 40,
                expected_smoke_job_id="123",
            )
        )
    _private_file(
        bundle / "stage07_second_parser_bundle_manifest.json",
        json.dumps(
            {
                "scientific_identity": {"public_fixture": True},
                "second_parser_model_fingerprint": "b" * 64,
                "artifacts": [
                    {
                        "relative_path": "runtime/public.py",
                        "size_bytes": 1,
                        "sha256": "e" * 64,
                    },
                ],
            }
        ),
    )
    smoke = tmp_path / "smoke.json"
    _private_file(
        smoke,
        json.dumps(
            {
                "version": "stage07_second_parser_compute_smoke_v2",
                "status": "PASS",
                "execution_git_sha": "f" * 40,
                "slurm_job_id": "123",
                "execution_site": "goethe-nhr",
                "bundle_fingerprint": fingerprint,
                "network_attempts": 0,
                "unresolved_shared_libraries": 0,
                "synthetic_cases": 3,
                "synthetic_deterministic_matches": 3,
                "exact_input_acknowledgements": 3,
                "nonempty_structured_outputs": 3,
                "public_synthetic_selection_fingerprint": (
                    s07_prelaunch.PUBLIC_SYNTHETIC_SELECTION_FINGERPRINT
                ),
                "pre_runtime_tree_fingerprint": "e" * 64,
                "post_runtime_tree_fingerprint": "e" * 64,
                "pre_runtime_tree_entry_count": 56,
                "post_runtime_tree_entry_count": 56,
                "tree_fingerprint_match": True,
                "tree_difference": {
                    "added": 0,
                    "removed": 0,
                    "content_modified": 0,
                    "mode_modified": 0,
                    "new_directories": 0,
                    "removed_directories": 0,
                    "new_symlinks": 0,
                    "identical": True,
                },
                "external_mutable_runtime_state": "PASS",
                "external_runtime_root": "PASS",
                "external_mutable_environment_count": 17,
                "immutable_model_cache": "PASS",
                "python_dont_write_bytecode": "PASS",
                "effective_uid_is_root": False,
                "output_write_read": "PASS",
                "multiprocessing_spawn": "PASS",
                "model_revision": "4af74dad1d547804dfc2de8f40fb23fbbec5b811",
                "python_version": "3.13.15",
                "sqlite_version": "3.46.1",
                "installed_distribution_count": 79,
                "installed_distribution_manifest_sha256": (
                    "4f3c558613f5d13d21dea51a00e206272f522b8dd75be6fef1218127103fc8f4"
                ),
                "protected_inputs_opened": False,
                "holdout_accessed": False,
                "production_accessed": False,
            }
        ),
    )
    assert stat.S_IMODE(smoke.stat().st_mode) == 0o600
    result = run_bundle_preflight(
        BundlePreflightConfig(
            bundle_directory=bundle,
            expected_bundle_fingerprint=fingerprint,
            expected_smoke_git_sha="f" * 40,
            expected_smoke_job_id="123",
            smoke_evidence_path=smoke,
        )
    )
    assert result["compute_smoke"] == "PASS"
    assert result["bundle_runtime_mutations"] == 0
    assert result["python_bytecode_cache_tolerance"] == "NONE"

    raw = json.loads(smoke.read_text(encoding="utf-8"))
    raw["tree_difference"]["added"] = 1
    _private_file(smoke, json.dumps(raw))
    with pytest.raises(Stage07PrelaunchError, match="SMOKE"):
        run_bundle_preflight(
            BundlePreflightConfig(
                bundle_directory=bundle,
                expected_bundle_fingerprint=fingerprint,
                expected_smoke_git_sha="f" * 40,
                expected_smoke_job_id="123",
                smoke_evidence_path=smoke,
            )
        )


def test_bundle_gate_rejects_holdout_smoke_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    _private_directory(bundle)
    holdout_smoke = tmp_path / "HOLDOUT" / "smoke.json"
    _private_directory(holdout_smoke.parent)
    _private_file(holdout_smoke, "{}")
    monkeypatch.setattr(
        s07_prelaunch,
        "validate_second_parser_bundle",
        lambda *_args, **_kwargs: pytest.fail("bundle must not be opened"),
    )
    with pytest.raises(Stage07PrelaunchError, match="HOLDOUT_ACCESS_PROHIBITED"):
        run_bundle_preflight(
            BundlePreflightConfig(
                bundle_directory=bundle,
                expected_bundle_fingerprint="a" * 64,
                expected_smoke_git_sha="b" * 40,
                expected_smoke_job_id="123",
                smoke_evidence_path=holdout_smoke,
            )
        )


def test_compute_smoke_launcher_is_public_offline_and_small() -> None:
    script = (
        REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_compute_smoke.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --mem=16G" in script
    assert "#SBATCH --time=00:30:00" in script
    assert "HF_HUB_OFFLINE=1" in script
    assert "TRANSFORMERS_OFFLINE=1" in script
    assert "stage07_second_parser_bind_runtime_state" in script
    assert '"${BASE_PYTHON}" -B' in script
    assert '"${SECOND_PYTHON}" -B' in script
    assert "STAGE07_SECOND_SMOKE_TREE_FINGERPRINT" in script
    assert "protected_inputs_opened=false" in script
    assert "curl " not in script
    assert "wget " not in script
    assert "RLIMIT_AS" not in script
    assert "ulimit -v" not in script


def test_compute_smoke_launcher_establishes_real_execution_contract() -> None:
    launcher = (
        REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_compute_smoke.sbatch"
    )
    result = s07_prelaunch._validate_launcher(
        launcher,
        requested_memory_gib=16,
        requested_cpus=4,
        walltime="00:30:00",
        network_allowed=False,
        require_model_offline_environment=True,
        require_compute_smoke_environment=True,
    )
    environment = result["compute_smoke_environment"]
    assert isinstance(environment, dict)
    assert environment["execution_site"] == "goethe-nhr"
    assert environment["slurm_job_id_contract"] == "NONEMPTY_REQUIRED"
    assert environment["real_execution_guard"] == "PASS"
    assert environment["required_environment_guards"] == 9
    assert environment["external_runtime_state_before_guarded_call"] == "PASS"
    assert environment["python_minus_b"] == "PASS"


def test_public_bundle_launcher_establishes_guard_before_build() -> None:
    launcher = (
        REPOSITORY / "cluster/goethe_nhr/stage07_build_second_parser_bundle.sbatch"
    )
    result = s07_prelaunch._validate_launcher(
        launcher,
        requested_memory_gib=24,
        requested_cpus=8,
        walltime="06:00:00",
        network_allowed=True,
        require_model_offline_environment=False,
        require_compute_smoke_environment=False,
    )
    environment = result["public_build_environment"]
    assert isinstance(environment, dict)
    assert environment == {
        "execution_site": "goethe-nhr",
        "slurm_job_id_contract": "NONEMPTY_REQUIRED",
        "real_execution_guard": "PASS",
        "guard_before_network_and_build": "PASS",
    }


def test_runtime_state_helper_binds_mutable_paths_outside_bundle(
    tmp_path: Path,
) -> None:
    helper = REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_runtime_state.sh"
    bundle = tmp_path / "bundle"
    model_cache = bundle / "cache"
    model_cache.mkdir(parents=True)
    model_cache.chmod(0o555)
    bundle.chmod(0o555)
    runtime_root = tmp_path / "runtime-state"
    names = (
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "HF_HOME",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HF_ASSETS_CACHE",
        "HF_XET_CACHE",
        "TRANSFORMERS_CACHE",
        "TORCH_HOME",
        "TORCH_EXTENSIONS_DIR",
        "PYTHONPYCACHEPREFIX",
        "STAGE07_SECOND_PARSER_MODEL_CACHE",
        "PYTHONDONTWRITEBYTECODE",
    )
    shell = """
source "$1"
stage07_second_parser_bind_runtime_state "$2" "$3"
shift 3
for name in "$@"; do
  printf '%s=%s\\0' "$name" "${!name}"
done
"""
    completed = subprocess.run(
        [
            "bash",
            "-c",
            shell,
            "stage07-runtime-state-test",
            str(helper),
            str(runtime_root),
            str(model_cache),
            *names,
        ],
        check=True,
        capture_output=True,
    )
    values = dict(
        token.decode("utf-8").split("=", 1)
        for token in completed.stdout.split(b"\0")
        if token
    )
    assert set(values) == set(names)
    assert values["STAGE07_SECOND_PARSER_MODEL_CACHE"] == str(model_cache.resolve())
    assert values["PYTHONDONTWRITEBYTECODE"] == "1"
    for name in names[:-2]:
        path = Path(values[name])
        assert path.is_relative_to(runtime_root)
        assert stat.S_IMODE(path.stat().st_mode) == 0o700

    rejected = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; stage07_second_parser_bind_runtime_state "$2" "$3"',
            "stage07-runtime-state-overlap-test",
            str(helper),
            str(bundle / "runtime-state"),
            str(model_cache),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "STAGE07_SECOND_PARSER_RUNTIME_STATE_TOPOLOGY_INVALID" in rejected.stderr


def test_compute_smoke_launcher_missing_site_fails_real_execution_guard(
    tmp_path: Path,
) -> None:
    source = (
        REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_compute_smoke.sbatch"
    ).read_text(encoding="utf-8")
    launcher = tmp_path / "missing-site.sbatch"
    _private_file(
        tmp_path / "stage07_second_parser_runtime_state.sh",
        (
            REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_runtime_state.sh"
        ).read_text(encoding="utf-8"),
    )
    _private_file(
        launcher,
        source.replace("export SAFE_EXECUTION_SITE=goethe-nhr\n", "", 1),
    )
    with pytest.raises(Stage07PrelaunchError, match="EXECUTION_MARKER_FAILURE"):
        s07_prelaunch._validate_launcher(
            launcher,
            requested_memory_gib=16,
            requested_cpus=4,
            walltime="00:30:00",
            network_allowed=False,
            require_model_offline_environment=True,
            require_compute_smoke_environment=True,
        )


def test_submission_preflight_rejects_network_command_for_offline_job(
    tmp_path: Path,
) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, _initial_sha = _git_worktree(controlled)
    eligibility, launcher, sha = _commit_execution_assets(
        worktree,
        "set -euo pipefail\numask 077\n#SBATCH --cpus-per-task=1\n"
        "#SBATCH --mem=1G\n#SBATCH --time=00:01:00\n"
        "curl https://public.invalid/model\n",
    )
    with pytest.raises(Stage07PrelaunchError, match="NETWORK_POLICY_FAILURE"):
        run_submission_preflight(
            SubmissionPreflightConfig(
                controlled_root=controlled,
                integration_root=worktree,
                expected_git_sha=sha,
                new_paths=(),
                required_paths=(),
                eligibility_manifest_path=eligibility,
                launcher_path=launcher,
                requested_memory_gib=1,
                requested_cpus=1,
                requested_walltime="00:01:00",
                minimum_free_bytes=1,
                minimum_free_inodes=1,
            )
        )

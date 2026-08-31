from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

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


def test_submission_preflight_catches_failures_before_scheduler(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, sha = _git_worktree(controlled)
    required = controlled / "required"
    _private_directory(required)
    eligibility = controlled / "eligibility.json"
    eligibility.write_bytes(
        (REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH).read_bytes()
    )
    eligibility.chmod(0o600)
    launcher = controlled / "launcher.sbatch"
    _private_file(
        launcher,
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


def test_preflight_rejects_worktree_outside_controlled_root(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    _private_directory(controlled)
    worktree, sha = _git_worktree(tmp_path / "outside")
    eligibility = controlled / "eligibility.json"
    eligibility.write_bytes(
        (REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH).read_bytes()
    )
    launcher = controlled / "launcher.sbatch"
    _private_file(
        launcher,
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
        ),
    )
    with pytest.raises(Stage07PrelaunchError, match="COMPUTE_SMOKE_REQUIRED"):
        run_bundle_preflight(
            BundlePreflightConfig(
                bundle_directory=bundle,
                expected_bundle_fingerprint=fingerprint,
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
                    {
                        "relative_path": "runtime/__pycache__/public.pyc",
                        "size_bytes": 2,
                        "sha256": "f" * 64,
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
                "version": "stage07_second_parser_compute_smoke_v1",
                "status": "PASS",
                "bundle_fingerprint": fingerprint,
                "network_attempts": 0,
                "unresolved_shared_libraries": 0,
                "synthetic_cases": 3,
                "synthetic_deterministic_matches": 3,
            }
        ),
    )
    assert stat.S_IMODE(smoke.stat().st_mode) == 0o600
    result = run_bundle_preflight(
        BundlePreflightConfig(
            bundle_directory=bundle,
            expected_bundle_fingerprint=fingerprint,
            smoke_evidence_path=smoke,
        )
    )
    assert result["compute_smoke"] == "PASS"

    raw = json.loads(smoke.read_text(encoding="utf-8"))
    raw["network_attempts"] = 1
    _private_file(smoke, json.dumps(raw))
    with pytest.raises(Stage07PrelaunchError, match="SMOKE"):
        run_bundle_preflight(
            BundlePreflightConfig(
                bundle_directory=bundle,
                expected_bundle_fingerprint=fingerprint,
                smoke_evidence_path=smoke,
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
    assert environment["required_environment_guards"] == 8


def test_compute_smoke_launcher_missing_site_fails_real_execution_guard(
    tmp_path: Path,
) -> None:
    source = (
        REPOSITORY / "cluster/goethe_nhr/stage07_second_parser_compute_smoke.sbatch"
    ).read_text(encoding="utf-8")
    launcher = tmp_path / "missing-site.sbatch"
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
    worktree, sha = _git_worktree(controlled)
    eligibility = controlled / "eligibility.json"
    eligibility.write_bytes(
        (REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH).read_bytes()
    )
    launcher = controlled / "launcher.sbatch"
    _private_file(
        launcher,
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

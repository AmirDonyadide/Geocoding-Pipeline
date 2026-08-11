from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SYNC = REPOSITORY / "scripts" / "sync_to_goethe_nhr.sh"
BOOTSTRAP = REPOSITORY / "cluster" / "goethe_nhr" / "bootstrap_env.sh"
PREFLIGHT = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_preflight.sh"
SBATCH = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_development_pilot.sbatch"


def test_cluster_shell_assets_are_syntactically_valid() -> None:
    for path in (SYNC, BOOTSTRAP, PREFLIGHT, SBATCH):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_sync_is_allowlisted_non_destructive_and_excludes_paused_state() -> None:
    content = SYNC.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "--delete" not in "\n".join(
        line for line in content.splitlines() if not line.lstrip().startswith("#")
    )
    assert ".git .gitattributes .gitignore AGENTS.md README.md" in content
    assert "phase02_20260810T173851Z_1349152b" in content
    assert "phase01_20260810T151626Z_7df9bc8f" in content
    assert "phase01_anomalies.csv.gz" in content
    assert "candidate_state.sqlite3" not in "\n".join(
        line for line in content.splitlines() if not line.lstrip().startswith("#")
    )
    assert "derived/controlled/phase03" not in content
    assert ".venv" not in " ".join(
        line.strip() for line in content.splitlines() if line.strip().startswith("rsync ")
    )


def test_preflight_requires_cluster_runtime_snapshot_and_node_local_space() -> None:
    content = PREFLIGHT.read_text(encoding="utf-8")
    for required in (
        "SAFE_EXECUTION_SITE",
        "SLURM_JOB_ID",
        "PHASE03_GIT_COMMIT",
        "(3, 14, 3)",
        'unicodedata.unidata_version == "16.0.0"',
        "phase02_20260810T173851Z_1349152b",
        "20_600_000",
        "26843545600",
        "NO_SAFE_CLUSTER_TEMP_STORAGE",
        'plan["contract_version"]',
        'plan["contract_fingerprint"]',
        "SLURM_TMPDIR",
        "TMPDIR",
    ):
        assert required in content
    assert "/scratch|/scratch/*) continue" in content


def test_slurm_workflow_is_single_node_sequential_and_preserves_locked_firewall() -> None:
    content = SBATCH.read_text(encoding="utf-8")
    assert "#SBATCH --nodes=1" in content
    assert "#SBATCH --ntasks=1" in content
    assert "#SBATCH --cpus-per-task=4" in content
    assert "#SBATCH --mem=16G" in content
    assert "#SBATCH --time=12:00:00" in content
    assert "#SBATCH --partition" not in content
    assert "#SBATCH --account" not in content
    stages = (
        "pilot-plan",
        "pilot-profile",
        "pilot-select",
        "pilot-validate",
        "pilot-materialize-development",
        "development-transform",
        "development-review-sample",
    )
    positions = [content.index(stage) for stage in stages]
    assert positions == sorted(positions)
    assert "PHASE03_NODE_TMP_ROOT}/candidate_state.sqlite3" in content
    assert "--input-development-payload" in content
    assert "--locked-payload" not in content
    assert "locked_evaluation.identities.bin" in content
    assert "locked_evaluation.parquet" not in content
    assert "DEVELOPMENT_PILOT_PASS" in content

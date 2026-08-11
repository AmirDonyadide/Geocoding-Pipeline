from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SYNC = REPOSITORY / "scripts" / "sync_to_goethe_nhr.sh"
BOOTSTRAP = REPOSITORY / "cluster" / "goethe_nhr" / "bootstrap_env.sh"
PREFLIGHT = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_preflight.sh"
SBATCH = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_development_pilot.sbatch"


def _fake_rsync(path: Path, *, modern: bool, label: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    protect_help = "  --protect-args  no space-splitting" if modern else ""
    protect_probe = (
        f'echo "rsync {label} protocol version 31"' if modern else "exit 1"
    )
    path.write_text(
        f"""#!/usr/bin/env bash
set -euo pipefail
case "${{1:-}}" in
  --version)
    echo "rsync {label} protocol version 31"
    ;;
  --help)
    echo "rsync help"
    echo "{protect_help}"
    ;;
  --protect-args)
    [[ "${{2:-}}" == "--version" ]] || exit 2
    {protect_probe}
    ;;
  *)
    printf '%s\\0' "$@" >> "${{FAKE_RSYNC_LOG:?}}"
    printf '\\n' >> "${{FAKE_RSYNC_LOG:?}}"
    ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _run_sync_dry_run(
    tmp_path: Path,
    *,
    selected_rsync: Path | None = None,
    homebrew_prefix: Path | None = None,
    path_rsync: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], bytes]:
    log = tmp_path / "rsync-arguments.bin"
    environment = {
        **os.environ,
        "FAKE_RSYNC_LOG": str(log),
    }
    if selected_rsync is not None:
        environment["SAFE_RSYNC_EXECUTABLE"] = str(selected_rsync)
    else:
        environment.pop("SAFE_RSYNC_EXECUTABLE", None)
    if homebrew_prefix is not None:
        environment["HOMEBREW_PREFIX"] = str(homebrew_prefix)
    else:
        environment.pop("HOMEBREW_PREFIX", None)
    if path_rsync is not None:
        environment["PATH"] = f"{path_rsync.parent}:{environment['PATH']}"
    result = subprocess.run(
        ["bash", str(SYNC), "--dry-run"],
        cwd=REPOSITORY,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return result, log.read_bytes()


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


def test_sync_uses_protect_args_with_modern_rsync(tmp_path: Path) -> None:
    modern = _fake_rsync(tmp_path / "modern" / "rsync", modern=True, label="3.4.1")
    result, arguments = _run_sync_dry_run(tmp_path, selected_rsync=modern)
    assert f"rsync executable={modern}" in result.stdout
    assert "rsync version=rsync 3.4.1 protocol version 31" in result.stdout
    assert "dry-run=true" in result.stdout
    assert "rsync protect-args=true" in result.stdout
    assert arguments.count(b"--protect-args\0") == 3
    for forbidden in (
        b"csv_files",
        b"candidate_state.sqlite3",
        b"phase03_pilot_20260811T082940Z_025fb0ba",
        b".venv",
        b"secrets",
        b"parquet_files",
        b"--delete",
    ):
        assert forbidden not in arguments


def test_sync_omits_protect_args_with_old_rsync(tmp_path: Path) -> None:
    old = _fake_rsync(tmp_path / "old" / "rsync", modern=False, label="2.6.9")
    result, arguments = _run_sync_dry_run(tmp_path, selected_rsync=old)
    assert f"rsync executable={old}" in result.stdout
    assert "rsync version=rsync 2.6.9 protocol version 31" in result.stdout
    assert "dry-run=true" in result.stdout
    assert "rsync protect-args=false" in result.stdout
    assert b"--protect-args\0" not in arguments
    assert arguments.count(b"--dry-run\0") == 3


def test_sync_prefers_homebrew_rsync_over_path_rsync(tmp_path: Path) -> None:
    homebrew_prefix = tmp_path / "homebrew"
    homebrew = _fake_rsync(
        homebrew_prefix / "bin" / "rsync", modern=True, label="homebrew"
    )
    path_rsync = _fake_rsync(
        tmp_path / "system" / "rsync", modern=False, label="system"
    )
    result, arguments = _run_sync_dry_run(
        tmp_path,
        homebrew_prefix=homebrew_prefix,
        path_rsync=path_rsync,
    )
    assert f"rsync executable={homebrew}" in result.stdout
    assert "rsync version=rsync homebrew protocol version 31" in result.stdout
    assert arguments.count(b"--protect-args\0") == 3


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

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]
SYNC = REPOSITORY / "scripts" / "sync_to_goethe_nhr.sh"
BOOTSTRAP = REPOSITORY / "cluster" / "goethe_nhr" / "bootstrap_env.sh"
PREFLIGHT = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_preflight.sh"
SBATCH = REPOSITORY / "cluster" / "goethe_nhr" / "phase03_development_pilot.sbatch"
STAGE00_INVENTORY_SBATCH = (
    REPOSITORY / "cluster" / "goethe_nhr" / "stage00_inventory.sbatch"
)
PATTERN_PROFILE_SBATCH = (
    REPOSITORY / "cluster" / "goethe_nhr" / "phase03_development_pattern_profile.sbatch"
)
PHASE02_RUN = "staging/controlled/phase02_v1/runs/phase02_20260810T173851Z_1349152b"
PHASE01_ANOMALY = (
    "reports/generated/phase01/phase01_20260810T151626Z_7df9bc8f/"
    "phase01_anomalies.csv.gz"
)


def test_stage00_inventory_launcher_is_population_scope_driven() -> None:
    script = STAGE00_INVENTORY_SBATCH.read_text(encoding="utf-8")
    assert "--population-scope-file" in script
    assert "--expected-population-scope-sha256" in script
    assert "STAGE00_SOURCE_ROOT" in script
    assert "STAGE00_RUN_ID" in script
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert "FULL_INVENTORY" in script
    assert "206" not in script
    assert "2822" not in script


def _fake_rsync(path: Path, *, modern: bool, label: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    protect_help = "  --protect-args  no space-splitting" if modern else ""
    protect_probe = f'echo "rsync {label} protocol version 31"' if modern else "exit 1"
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


def _rsync_calls(arguments: bytes) -> list[list[str]]:
    return [
        [item.decode("utf-8") for item in line.split(b"\0") if item]
        for line in arguments.splitlines()
        if line
    ]


def _planned_sources(arguments: bytes) -> list[str]:
    sources: list[str] = []
    for call in _rsync_calls(arguments):
        assert call[-1].startswith("goethe:")
        sources.extend(item for item in call[:-1] if not item.startswith("-"))
    return sources


def test_cluster_shell_assets_are_syntactically_valid() -> None:
    for path in (SYNC, BOOTSTRAP, PREFLIGHT, SBATCH, PATTERN_PROFILE_SBATCH):
        subprocess.run(["bash", "-n", str(path)], check=True)


def _run_pattern_profile_path_guard(
    data_root: Path,
    input_path: Path,
    *,
    gnu_realpath: Path,
) -> subprocess.CompletedProcess[str]:
    guard = r"""
set -euo pipefail
DATA_ROOT="$1"
input="$2"
RESOLVED_DATA_ROOT="$(realpath -e -- "${DATA_ROOT}")"
CONTROLLED_PHASE03_ROOT="$(realpath -e -- "${RESOLVED_DATA_ROOT}/derived/controlled/phase03_v1")"
resolved_input="$(realpath -e -- "${input}")"
[[ "${resolved_input}" == "${CONTROLLED_PHASE03_ROOT}/"* ]] || exit 41
case "${resolved_input}" in
  *[Ll][Oo][Cc][Kk][Ee][Dd]*) exit 42 ;;
esac
"""
    return subprocess.run(
        [
            "bash",
            "-c",
            guard,
            "pattern-profile-path-guard",
            str(data_root),
            str(input_path),
        ],
        env={**os.environ, "PATH": f"{gnu_realpath.parent}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        check=False,
    )


def test_pattern_profile_guard_compares_canonical_root_and_input(
    tmp_path: Path,
) -> None:
    gnu_realpath = tmp_path / "bin" / "realpath"
    gnu_realpath.parent.mkdir()
    gnu_realpath.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        '[[ "${1:-}" == "-e" ]] && shift\n'
        '[[ "${1:-}" == "--" ]] && shift\n'
        f"exec {shlex.quote(sys.executable)} -c "
        "'import pathlib, sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' "
        '"$1"\n',
        encoding="utf-8",
    )
    gnu_realpath.chmod(0o755)

    physical_root = tmp_path / "panfs" / "project"
    controlled_root = physical_root / "derived" / "controlled" / "phase03_v1"
    valid_identity = controlled_root / "selection" / "development.identities.bin"
    valid_identity.parent.mkdir(parents=True)
    valid_identity.touch()

    work_alias = tmp_path / "work" / "project"
    work_alias.parent.mkdir()
    work_alias.symlink_to(physical_root, target_is_directory=True)

    outside = physical_root / "derived" / "controlled" / "phase03_v1-sibling" / "input"
    outside.parent.mkdir(parents=True)
    outside.touch()
    locked = controlled_root / "LoCkEd" / "input"
    locked.parent.mkdir()
    locked.touch()

    accepted = _run_pattern_profile_path_guard(
        work_alias,
        work_alias
        / "derived"
        / "controlled"
        / "phase03_v1"
        / "selection"
        / valid_identity.name,
        gnu_realpath=gnu_realpath,
    )
    rejected_outside = _run_pattern_profile_path_guard(
        work_alias,
        outside,
        gnu_realpath=gnu_realpath,
    )
    rejected_locked = _run_pattern_profile_path_guard(
        work_alias,
        locked,
        gnu_realpath=gnu_realpath,
    )

    assert accepted.returncode == 0
    assert rejected_outside.returncode == 41
    assert rejected_locked.returncode == 42

    content = PATTERN_PROFILE_SBATCH.read_text(encoding="utf-8")
    assert 'RESOLVED_DATA_ROOT="$(realpath -e -- "${DATA_ROOT}")"' in content
    assert (
        'CONTROLLED_PHASE03_ROOT="$(realpath -e -- '
        '"${RESOLVED_DATA_ROOT}/derived/controlled/phase03_v1")"'
    ) in content
    assert '[[ "${resolved_input}" == "${CONTROLLED_PHASE03_ROOT}/"* ]]' in content
    assert '[[ "${resolved_input,,}" != *locked* ]]' in content


def test_sync_is_data_only_non_destructive_and_excludes_paused_state() -> None:
    content = SYNC.read_text(encoding="utf-8")
    assert "--dry-run" in content
    assert "--delete" not in "\n".join(
        line for line in content.splitlines() if not line.lstrip().startswith("#")
    )
    assert "git ls-files -z" not in content
    assert ".git/refs/heads" not in content
    assert 'echo "code sync=GITHUB_ONLY"' in content
    assert 'echo "Source code and Git metadata transferred=false"' in content
    assert "CLUSTER_GIT_CLONE_REQUIRED" in content
    assert "phase02_20260810T173851Z_1349152b" in content
    assert "phase01_20260810T151626Z_7df9bc8f" in content
    assert "phase01_anomalies.csv.gz" in content
    assert "derived/controlled/phase03" not in content
    assert ".venv" not in " ".join(
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("rsync ")
    )


@pytest.mark.requires_production_transfer_payload
def test_sync_dry_run_plan_contains_only_approved_controlled_data(
    tmp_path: Path,
) -> None:
    modern = _fake_rsync(tmp_path / "modern" / "rsync", modern=True, label="3.4.1")
    result, arguments = _run_sync_dry_run(tmp_path, selected_rsync=modern)
    calls = _rsync_calls(arguments)
    sources = _planned_sources(arguments)
    assert len(calls) == 2
    assert "code sync=GITHUB_ONLY" in result.stdout
    assert "Source code and Git metadata transferred=false" in result.stdout
    assert "Phase 2 Parquet shards=206" in result.stdout
    required_exclusions = {
        "--exclude=.DS_Store",
        "--exclude=__pycache__/",
        "--exclude=*.pyc",
        "--exclude=*.pyo",
        "--exclude=*.egg-info/",
        "--exclude=.pytest_cache/",
        "--exclude=.mypy_cache/",
        "--exclude=.ruff_cache/",
        "--exclude=.agents/",
        "--exclude=.git/refs/codex/",
        "--exclude=logs/",
        "--exclude=.venv/",
        "--exclude=.venv-goethe-nhr/",
        "--exclude=.in_progress/",
        "--exclude=_work/",
        "--exclude=candidate_state.sqlite3",
        "--exclude=phase02_state.sqlite3",
        "--exclude=*duckdb_spill*/",
        "--exclude=.env",
        "--exclude=.env.*",
        "--exclude=*.pem",
        "--exclude=*.key",
    }
    for call in calls:
        assert required_exclusions.issubset(call)

    assert not any(source.startswith(".git/") for source in sources)
    assert not any(source.startswith("src/") for source in sources)
    assert not any(source.startswith("tests/") for source in sources)
    assert not any(source.startswith("docs/") for source in sources)
    assert "README.md" not in sources
    assert "pyproject.toml" not in sources

    phase02_sources = [source for source in sources if source.startswith(PHASE02_RUN)]
    parquet_sources = [
        source for source in phase02_sources if source.endswith(".parquet")
    ]
    assert len(parquet_sources) == 206
    assert len(set(parquet_sources)) == 206
    assert f"{PHASE02_RUN}/dataset_manifest.json" in phase02_sources
    assert f"{PHASE02_RUN}/_SUCCESS.json" in phase02_sources
    assert len(phase02_sources) == 208
    assert PHASE01_ANOMALY in sources
    assert [
        source for source in sources if source.startswith("reports/generated/phase01/")
    ] == [PHASE01_ANOMALY]

    prohibited_fragments = (
        ".DS_Store",
        "__pycache__",
        ".pyc",
        ".pyo",
        ".egg-info",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".agents",
        ".git/refs/codex",
        "logs/",
        ".venv/",
        ".venv-goethe-nhr/",
        "/.in_progress/",
        "/_work/",
        "phase02_state.sqlite3",
        "candidate_state.sqlite3",
        "duckdb",
        "phase03_pilot_20260811T082940Z_025fb0ba",
        "csv_files/",
        "parquet_files/",
    )
    for source in sources:
        assert not any(fragment in source for fragment in prohibited_fragments), source


@pytest.mark.requires_production_transfer_payload
def test_sync_uses_protect_args_with_modern_rsync(tmp_path: Path) -> None:
    modern = _fake_rsync(tmp_path / "modern" / "rsync", modern=True, label="3.4.1")
    result, arguments = _run_sync_dry_run(tmp_path, selected_rsync=modern)
    assert f"rsync executable={modern}" in result.stdout
    assert "rsync version=rsync 3.4.1 protocol version 31" in result.stdout
    assert "dry-run=true" in result.stdout
    assert "rsync protect-args=true" in result.stdout
    assert arguments.count(b"--protect-args\0") == 2
    planned_sources = "\0".join(_planned_sources(arguments)).encode("utf-8")
    for forbidden in (
        b"csv_files",
        b"candidate_state.sqlite3",
        b"phase03_pilot_20260811T082940Z_025fb0ba",
        b".venv",
        b"secrets",
        b"parquet_files",
        b"--delete",
    ):
        assert forbidden not in planned_sources


@pytest.mark.requires_production_transfer_payload
def test_sync_omits_protect_args_with_old_rsync(tmp_path: Path) -> None:
    old = _fake_rsync(tmp_path / "old" / "rsync", modern=False, label="2.6.9")
    result, arguments = _run_sync_dry_run(tmp_path, selected_rsync=old)
    assert f"rsync executable={old}" in result.stdout
    assert "rsync version=rsync 2.6.9 protocol version 31" in result.stdout
    assert "dry-run=true" in result.stdout
    assert "rsync protect-args=false" in result.stdout
    assert b"--protect-args\0" not in arguments
    assert arguments.count(b"--dry-run\0") == 2


@pytest.mark.requires_production_transfer_payload
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
    assert arguments.count(b"--protect-args\0") == 2


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


def test_slurm_workflow_is_single_node_sequential_and_preserves_locked_firewall() -> (
    None
):
    content = SBATCH.read_text(encoding="utf-8")
    assert "#SBATCH --nodes=1" in content
    assert "#SBATCH --ntasks=1" in content
    assert "#SBATCH --cpus-per-task=16" in content
    assert "#SBATCH --mem=64G" in content
    assert "#SBATCH --time=24:00:00" in content
    assert "#SBATCH --partition=general1" in content
    assert "#SBATCH --account" not in content
    assert "--selection-engine bounded-parallel" in content
    assert "--worker-count 16" in content
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

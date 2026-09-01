"""Fail-closed Stage 7 submission and public compute-smoke preflight."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from ...execution_policy import ExecutionPolicyError, require_goethe_nhr_slurm
from .s07_country_eligibility import load_eligibility_manifest
from .s07_second_parser_bundle import (
    validate_atomic_noreplace_filesystem,
    validate_second_parser_bundle,
    validate_second_parser_bundle_metadata_only,
)
from .s07_second_parser_smoke import (
    EXPECTED_DISTRIBUTION_COUNT,
    EXPECTED_DISTRIBUTION_MANIFEST_SHA256,
    EXPECTED_PYTHON_VERSION,
    EXPECTED_SQLITE_VERSION,
    MODEL_REVISION,
    PUBLIC_SYNTHETIC_SELECTION_FINGERPRINT,
)


PRELAUNCH_VERSION = "stage07_prelaunch_gate_v2"
PRELAUNCH_PASS = "STAGE07_PRELAUNCH_GATE_PASS"
PRELAUNCH_FAIL = "STAGE07_PRELAUNCH_GATE_FAIL"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SMOKE_REQUIRED_ENVIRONMENT = (
    "SLURM_JOB_ID",
    "SLURM_JOB_NAME",
    "STAGE07_SECOND_SMOKE_GIT_COMMIT",
    "STAGE07_SECOND_SMOKE_INTEGRATION_ROOT",
    "STAGE07_SECOND_SMOKE_BUNDLE_DIRECTORY",
    "STAGE07_SECOND_SMOKE_BUNDLE_FINGERPRINT",
    "STAGE07_SECOND_SMOKE_TREE_FINGERPRINT",
    "STAGE07_SECOND_SMOKE_OUTPUT_DIRECTORY",
    "STAGE07_SECOND_SMOKE_RUNTIME_ROOT",
)
_SMOKE_OFFLINE_EXPORTS = (
    "export HF_HUB_OFFLINE=1",
    "export TRANSFORMERS_OFFLINE=1",
    "export HF_HUB_DISABLE_TELEMETRY=1",
)


class Stage07PrelaunchError(RuntimeError):
    """Stable privacy-safe prelaunch error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07PrelaunchError(code, detail)


@dataclass(frozen=True, slots=True)
class SubmissionPreflightConfig:
    controlled_root: Path
    integration_root: Path
    expected_git_sha: str
    new_paths: tuple[Path, ...]
    required_paths: tuple[Path, ...]
    eligibility_manifest_path: Path
    launcher_path: Path
    requested_memory_gib: int
    requested_cpus: int
    requested_walltime: str
    minimum_free_bytes: int
    minimum_free_inodes: int
    read_only_bundle_paths: tuple[Path, ...] = ()
    require_detached: bool = True
    network_allowed: bool = False
    require_model_offline_environment: bool = False
    require_compute_smoke_environment: bool = False


@dataclass(frozen=True, slots=True)
class BundlePreflightConfig:
    bundle_directory: Path
    expected_bundle_fingerprint: str
    expected_smoke_git_sha: str
    expected_smoke_job_id: str
    smoke_evidence_path: Path | None = None


def _run_git(root: Path, *arguments: str, allow_exit_one: bool = False) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_GIT_FAILURE", "Git metadata could not be verified"
        ) from error
    if result.returncode != 0 and not (allow_exit_one and result.returncode == 1):
        _fail("PRELAUNCH_GIT_FAILURE", "Git metadata command failed")
    return result.stdout.strip()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def _reject_holdout(*paths: Path) -> None:
    if any(
        "holdout" in part.casefold()
        for path in paths
        for part in path.resolve(strict=False).parts
    ):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT path found")


def _require_owner_only(path: Path, *, directory: bool) -> None:
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        _fail("PRELAUNCH_PATH_INVALID", "A required path has invalid topology")
    expected = 0o700 if directory else 0o600
    if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode) != expected:
        _fail("PRELAUNCH_PERMISSION_FAILURE", "A controlled mode differs")
    if path.stat(follow_symlinks=False).st_uid != os.getuid():
        _fail("PRELAUNCH_OWNERSHIP_FAILURE", "A controlled owner differs")


def _validate_runtime_state_helper(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        _fail("PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE", "Runtime helper is absent")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE",
            "Runtime helper could not be read",
        ) from error
    required_exports = (
        "STAGE07_SECOND_PARSER_RUNTIME_ROOT",
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
    missing = [name for name in required_exports if f"export {name}=" not in text]
    if (
        missing
        or "install -d -m 0700" not in text
        or 'model_cache="$(cd "$2" && pwd -P)"' not in text
        or 'bundle_root="$(cd "${model_cache}/.." && pwd -P)"' not in text
    ):
        _fail(
            "PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE",
            "External mutable-state binding is incomplete",
        )
    return {
        "external_mutable_state_exports": 17,
        "external_runtime_root_binding": "PASS",
        "immutable_model_asset_binding": "PASS",
        "owner_only_runtime_directories": "PASS",
        "python_bytecode_policy": "PASS",
    }


def _validate_compute_smoke_environment(text: str) -> dict[str, object]:
    """Validate the real smoke launcher's environment before guarded execution."""
    guarded_call = text.find(
        "safe_geocoding_pipeline.preprocessing.stage07_second_parser_bundle_cli "
        "validate"
    )
    smoke_call = text.find(
        "safe_geocoding_pipeline.preprocessing.stages.s07_second_parser_smoke"
    )
    if guarded_call < 0 or smoke_call < 0 or smoke_call <= guarded_call:
        _fail(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "Guarded smoke call topology differs",
        )

    missing_guards = []
    late_guards = []
    for name in _SMOKE_REQUIRED_ENVIRONMENT:
        marker = f': "${{{name}:?'
        position = text.find(marker)
        if position < 0:
            missing_guards.append(name)
        elif position > guarded_call:
            late_guards.append(name)
    if missing_guards or late_guards:
        _fail(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "A required smoke environment guard is absent or late",
        )

    site_marker = "export SAFE_EXECUTION_SITE=goethe-nhr"
    site_position = text.find(site_marker)
    synthetic_environment = {"SLURM_JOB_ID": "PUBLIC_SYNTHETIC_PREFLIGHT"}
    if site_position >= 0:
        synthetic_environment["SAFE_EXECUTION_SITE"] = "goethe-nhr"
    try:
        require_goethe_nhr_slurm(
            "stage07-public-compute-smoke-preflight",
            environment=synthetic_environment,
        )
    except ExecutionPolicyError as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "The real execution guard rejects launcher-derived markers",
        ) from error
    if site_position > guarded_call:
        _fail(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "Execution-site marker is established after guarded execution",
        )

    runtime_binding = "stage07_second_parser_bind_runtime_state"
    runtime_binding_position = text.find(runtime_binding)
    if not 0 <= runtime_binding_position < guarded_call:
        _fail(
            "PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE",
            "External runtime state is not bound before bundle validation",
        )
    if '"${BASE_PYTHON}" -B' not in text or '"${SECOND_PYTHON}" -B' not in text:
        _fail(
            "PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE",
            "Post-publication Python does not enforce -B",
        )

    late_offline_exports = [
        value
        for value in _SMOKE_OFFLINE_EXPORTS
        if not 0 <= text.find(value) < smoke_call
    ]
    if late_offline_exports:
        _fail(
            "PRELAUNCH_NETWORK_POLICY_FAILURE",
            "A required offline model export is absent or late",
        )
    return {
        "execution_site": "goethe-nhr",
        "slurm_job_id_contract": "NONEMPTY_REQUIRED",
        "real_execution_guard": "PASS",
        "required_environment_guards": len(_SMOKE_REQUIRED_ENVIRONMENT),
        "required_environment_guard_result": "PASS",
        "offline_exports_before_model_execution": "PASS",
        "first_guarded_call_marker": "SECOND_PARSER_BUNDLE_VALIDATE",
        "external_runtime_state_before_guarded_call": "PASS",
        "python_minus_b": "PASS",
    }


def _validate_public_build_environment(text: str) -> dict[str, object]:
    site_marker = "export SAFE_EXECUTION_SITE=goethe-nhr"
    guard_marker = 'require_goethe_nhr_slurm("stage07-public-second-parser-bundle")'
    network_positions = [
        match.start()
        for pattern in (
            r"(?m)^curl\s+--fail\b",
            r'(?m)^"\$\{SECOND_PYTHON\}"\s+-B\s+-m\s+pip\s+install\b',
        )
        if (match := re.search(pattern, text)) is not None
    ]
    first_network = min(network_positions, default=-1)
    site_position = text.find(site_marker)
    guard_position = text.find(guard_marker)
    if (
        first_network < 0
        or site_position < 0
        or guard_position < 0
        or site_position > guard_position
        or guard_position > first_network
    ):
        _fail(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "Public build guard is absent or occurs after network/build work",
        )
    try:
        require_goethe_nhr_slurm(
            "stage07-public-build-preflight",
            environment={
                "SAFE_EXECUTION_SITE": "goethe-nhr",
                "SLURM_JOB_ID": "PUBLIC_SYNTHETIC_PREFLIGHT",
            },
        )
    except ExecutionPolicyError as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_EXECUTION_MARKER_FAILURE",
            "The real execution guard rejects public-build markers",
        ) from error
    return {
        "execution_site": "goethe-nhr",
        "slurm_job_id_contract": "NONEMPTY_REQUIRED",
        "real_execution_guard": "PASS",
        "guard_before_network_and_build": "PASS",
    }


def _validate_launcher(
    path: Path,
    *,
    requested_memory_gib: int,
    requested_cpus: int,
    walltime: str,
    network_allowed: bool,
    require_model_offline_environment: bool,
    require_compute_smoke_environment: bool,
) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        _fail("PRELAUNCH_LAUNCHER_INVALID", "Launcher is absent or a symlink")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_LAUNCHER_INVALID", "Launcher could not be read"
        ) from error
    required = (
        "set -euo pipefail",
        "umask 077",
        f"#SBATCH --cpus-per-task={requested_cpus}",
        f"#SBATCH --mem={requested_memory_gib}G",
        f"#SBATCH --time={walltime}",
    )
    if any(value not in text for value in required):
        _fail("PRELAUNCH_RESOURCE_MISMATCH", "Launcher resources/policy differ")
    if "RLIMIT_AS" in text or "ulimit -v" in text:
        _fail("PRELAUNCH_RESOURCE_CAP_PROHIBITED", "Address-space cap found")
    network_commands = re.findall(
        r"(?m)^[^#\n]*(?:\bcurl\b|\bwget\b|\bgit\s+clone\b|\bpip\s+install\b)",
        text,
    )
    if not network_allowed and network_commands:
        _fail("PRELAUNCH_NETWORK_POLICY_FAILURE", "Network-capable command found")
    if require_model_offline_environment and any(
        value not in text
        for value in (
            "HF_HUB_OFFLINE=1",
            "TRANSFORMERS_OFFLINE=1",
            "HF_HUB_DISABLE_TELEMETRY=1",
        )
    ):
        _fail("PRELAUNCH_NETWORK_POLICY_FAILURE", "Offline model controls differ")
    smoke_environment: dict[str, object] | str = "NOT_APPLICABLE"
    runtime_state: dict[str, object] | str = "NOT_APPLICABLE"
    if "stage07_second_parser_runtime_state.sh" in text:
        runtime_state = _validate_runtime_state_helper(
            path.with_name("stage07_second_parser_runtime_state.sh")
        )
    if require_compute_smoke_environment:
        smoke_environment = _validate_compute_smoke_environment(text)
    public_build_environment: dict[str, object] | str = "NOT_APPLICABLE"
    if network_allowed:
        public_build_environment = _validate_public_build_environment(text)
    return {
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "resource_directives": "PASS",
        "fail_closed_shell": "PASS",
        "address_space_cap_absent": "PASS",
        "network_policy": (
            "PUBLIC_BUILD_NETWORK_ALLOWED"
            if network_allowed
            else "OFFLINE_NO_NETWORK_COMMANDS"
        ),
        "offline_model_environment": (
            "PASS" if require_model_offline_environment else "NOT_APPLICABLE"
        ),
        "compute_smoke_environment": smoke_environment,
        "public_build_environment": public_build_environment,
        "external_runtime_state": runtime_state,
    }


def run_submission_preflight(config: SubmissionPreflightConfig) -> dict[str, object]:
    """Verify every check that can run before submitting a scheduled job."""
    if _GIT_SHA_RE.fullmatch(config.expected_git_sha) is None:
        _fail("PRELAUNCH_GIT_SHA_INVALID", "Expected Git SHA is malformed")
    if (
        config.requested_memory_gib < 1
        or config.requested_cpus < 1
        or re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}", config.requested_walltime)
        is None
        or config.minimum_free_bytes < 1
        or config.minimum_free_inodes < 1
    ):
        _fail("PRELAUNCH_RESOURCE_INVALID", "A requested resource is invalid")
    all_paths = (
        config.controlled_root,
        config.integration_root,
        config.eligibility_manifest_path,
        config.launcher_path,
        *config.new_paths,
        *config.required_paths,
        *config.read_only_bundle_paths,
    )
    _reject_holdout(*all_paths)
    controlled_root = config.controlled_root.resolve(strict=True)
    integration_root = config.integration_root.resolve(strict=True)
    _require_owner_only(controlled_root, directory=True)
    if not _is_within(integration_root, controlled_root):
        _fail("PRELAUNCH_CONTROLLED_PATH_REQUIRED", "Worktree is outside root")
    if _run_git(integration_root, "rev-parse", "HEAD") != config.expected_git_sha:
        _fail("PRELAUNCH_GIT_SHA_MISMATCH", "Worktree SHA differs")
    if _run_git(integration_root, "status", "--porcelain"):
        _fail("PRELAUNCH_WORKTREE_DIRTY", "Worktree is not clean")
    if _run_git(
        integration_root, "ls-files", "--others", "--ignored", "--exclude-standard"
    ):
        _fail(
            "PRELAUNCH_WORKTREE_IGNORED_FILES_PRESENT",
            "Detached worktree contains ignored files",
        )
    symbolic = _run_git(
        integration_root, "symbolic-ref", "-q", "HEAD", allow_exit_one=True
    )
    if config.require_detached and symbolic:
        _fail("PRELAUNCH_WORKTREE_NOT_DETACHED", "Worktree is not detached")
    launcher_path = config.launcher_path.resolve(strict=True)
    eligibility_path = config.eligibility_manifest_path.resolve(strict=True)
    for source_path in (launcher_path, eligibility_path):
        if not _is_within(source_path, integration_root):
            _fail(
                "PRELAUNCH_GIT_BOUND_PATH_REQUIRED",
                "A scientific execution asset is outside the exact worktree",
            )
        relative = source_path.relative_to(integration_root).as_posix()
        _run_git(integration_root, "ls-files", "--error-unmatch", "--", relative)
    expected_eligibility = (
        integration_root
        / "docs/scientific_assets/stage07_parser_country_eligibility_v1.json"
    )
    if eligibility_path != expected_eligibility:
        _fail(
            "PRELAUNCH_ELIGIBILITY_MANIFEST_PATH_MISMATCH",
            "Eligibility manifest is not the canonical tracked asset",
        )
    for path in config.required_paths:
        resolved = path.resolve(strict=True)
        if not _is_within(resolved, controlled_root):
            _fail("PRELAUNCH_CONTROLLED_PATH_REQUIRED", "Input is outside root")
        _require_owner_only(resolved, directory=resolved.is_dir())
    read_only_bundle_metadata: list[dict[str, object]] = []
    read_only_bundle_roots: list[Path] = []
    for path in config.read_only_bundle_paths:
        resolved = path.resolve(strict=True)
        if not _is_within(resolved, controlled_root):
            _fail("PRELAUNCH_CONTROLLED_PATH_REQUIRED", "Bundle is outside root")
        outcome = validate_second_parser_bundle_metadata_only(path)
        read_only_bundle_metadata.append(
            {
                "bundle_fingerprint": outcome.second_parser_bundle_fingerprint,
                "manifest_sha256": outcome.manifest_sha256,
                "artifact_count": outcome.artifact_count,
                "total_size_bytes": outcome.total_size_bytes,
                "validation_scope": "METADATA_ONLY_LOGIN_PREFLIGHT",
            }
        )
        read_only_bundle_roots.append(resolved)
    resolved_new_paths = [path.resolve(strict=False) for path in config.new_paths]
    for index, first in enumerate(resolved_new_paths):
        for second in resolved_new_paths[index + 1 :]:
            if (
                first == second
                or _is_within(first, second)
                or _is_within(second, first)
            ):
                _fail(
                    "PRELAUNCH_NEW_PATH_TOPOLOGY_INVALID",
                    "Planned new paths overlap",
                )
    for path, resolved in zip(config.new_paths, resolved_new_paths, strict=True):
        if not _is_within(resolved, controlled_root):
            _fail("PRELAUNCH_CONTROLLED_PATH_REQUIRED", "Output is outside root")
        if (
            resolved == integration_root
            or _is_within(resolved, integration_root)
            or _is_within(integration_root, resolved)
        ):
            _fail(
                "PRELAUNCH_NEW_PATH_TOPOLOGY_INVALID",
                "A planned output overlaps the exact worktree",
            )
        if any(
            resolved == bundle_root or _is_within(resolved, bundle_root)
            for bundle_root in read_only_bundle_roots
        ):
            _fail(
                "PRELAUNCH_RUNTIME_STATE_POLICY_FAILURE",
                "A planned output is inside an immutable bundle",
            )
        if path.exists() or path.is_symlink():
            _fail("PRELAUNCH_OUTPUT_COLLISION", "A planned new path already exists")
        parent = path.parent.resolve(strict=True)
        if not _is_within(parent, controlled_root) and parent != controlled_root:
            _fail("PRELAUNCH_CONTROLLED_PATH_REQUIRED", "Output parent is outside root")
        _require_owner_only(parent, directory=True)
    atomic_filesystem_results = [
        validate_atomic_noreplace_filesystem(parent)
        for parent in sorted(
            {path.parent.resolve(strict=True) for path in config.new_paths},
            key=lambda path: path.as_posix(),
        )
    ]
    disk = shutil.disk_usage(controlled_root)
    filesystem = os.statvfs(controlled_root)
    free_inodes = filesystem.f_favail
    if disk.free < config.minimum_free_bytes:
        _fail("PRELAUNCH_DISK_INSUFFICIENT", "Free bytes are below requirement")
    if free_inodes < config.minimum_free_inodes:
        _fail("PRELAUNCH_INODES_INSUFFICIENT", "Free inodes are below requirement")
    manifest = load_eligibility_manifest(eligibility_path)
    launcher = _validate_launcher(
        config.launcher_path,
        requested_memory_gib=config.requested_memory_gib,
        requested_cpus=config.requested_cpus,
        walltime=config.requested_walltime,
        network_allowed=config.network_allowed,
        require_model_offline_environment=config.require_model_offline_environment,
        require_compute_smoke_environment=config.require_compute_smoke_environment,
    )
    return {
        "version": PRELAUNCH_VERSION,
        "status": PRELAUNCH_PASS,
        "git": {
            "sha": config.expected_git_sha,
            "clean": True,
            "detached": config.require_detached,
            "controlled_path": True,
        },
        "paths": {
            "required_count": len(config.required_paths),
            "read_only_bundle_count": len(config.read_only_bundle_paths),
            "new_count": len(config.new_paths),
            "new_paths_absent": True,
            "owner_only": True,
            "read_only_bundle_metadata": read_only_bundle_metadata,
            "login_node_payload_rehash": False,
            "atomic_no_replace_filesystem_probes": atomic_filesystem_results,
        },
        "resources": {
            "requested_memory_gib": config.requested_memory_gib,
            "requested_cpus": config.requested_cpus,
            "requested_walltime": config.requested_walltime,
            "free_bytes": disk.free,
            "free_inodes": free_inodes,
            "disk_and_inode_gate": "PASS",
        },
        "eligibility_manifest_sha256": manifest.sha256,
        "launcher": launcher,
        "holdout_accessed": False,
    }


def run_bundle_preflight(config: BundlePreflightConfig) -> dict[str, object]:
    """Validate a frozen bundle and, when required, its compute-smoke evidence."""
    if _SHA256_RE.fullmatch(config.expected_bundle_fingerprint) is None:
        _fail("PRELAUNCH_BUNDLE_FINGERPRINT_INVALID", "Bundle hash is malformed")
    if _GIT_SHA_RE.fullmatch(config.expected_smoke_git_sha) is None:
        _fail("PRELAUNCH_GIT_SHA_INVALID", "Smoke Git SHA is malformed")
    if re.fullmatch(r"[0-9]+", config.expected_smoke_job_id) is None:
        _fail("PRELAUNCH_SMOKE_JOB_ID_INVALID", "Smoke job ID is malformed")
    if config.smoke_evidence_path is None:
        _fail("PRELAUNCH_COMPUTE_SMOKE_REQUIRED", "Compute-smoke evidence is absent")
    _reject_holdout(config.bundle_directory, config.smoke_evidence_path)
    outcome = validate_second_parser_bundle(
        config.bundle_directory,
        expected_second_parser_bundle_fingerprint=(config.expected_bundle_fingerprint),
    )
    _require_owner_only(config.smoke_evidence_path, directory=False)
    try:
        raw = json.loads(config.smoke_evidence_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07PrelaunchError(
            "PRELAUNCH_SMOKE_INVALID", "Smoke evidence is unreadable"
        ) from error
    if (
        not isinstance(raw, dict)
        or raw.get("version") != "stage07_second_parser_compute_smoke_v2"
        or raw.get("status") != "PASS"
        or raw.get("execution_git_sha") != config.expected_smoke_git_sha
        or raw.get("slurm_job_id") != config.expected_smoke_job_id
        or raw.get("execution_site") != "goethe-nhr"
        or raw.get("bundle_fingerprint") != config.expected_bundle_fingerprint
        or raw.get("network_attempts") != 0
        or raw.get("unresolved_shared_libraries") != 0
        or raw.get("synthetic_cases") != 3
        or raw.get("synthetic_deterministic_matches") != 3
        or raw.get("exact_input_acknowledgements") != 3
        or raw.get("nonempty_structured_outputs") != 3
        or raw.get("public_synthetic_selection_fingerprint")
        != PUBLIC_SYNTHETIC_SELECTION_FINGERPRINT
        or raw.get("pre_runtime_tree_fingerprint") != outcome.complete_tree_fingerprint
        or raw.get("post_runtime_tree_fingerprint") != outcome.complete_tree_fingerprint
        or raw.get("pre_runtime_tree_entry_count") != outcome.complete_tree_entry_count
        or raw.get("post_runtime_tree_entry_count") != outcome.complete_tree_entry_count
        or raw.get("tree_fingerprint_match") is not True
        or raw.get("external_mutable_runtime_state") != "PASS"
        or raw.get("external_runtime_root") != "PASS"
        or raw.get("external_mutable_environment_count") != 17
        or raw.get("immutable_model_cache") != "PASS"
        or raw.get("python_dont_write_bytecode") != "PASS"
        or raw.get("effective_uid_is_root") is not False
        or raw.get("output_write_read") != "PASS"
        or raw.get("multiprocessing_spawn") != "PASS"
        or raw.get("model_revision") != MODEL_REVISION
        or raw.get("python_version") != EXPECTED_PYTHON_VERSION
        or raw.get("sqlite_version") != EXPECTED_SQLITE_VERSION
        or raw.get("installed_distribution_count") != EXPECTED_DISTRIBUTION_COUNT
        or raw.get("installed_distribution_manifest_sha256")
        != EXPECTED_DISTRIBUTION_MANIFEST_SHA256
        or raw.get("protected_inputs_opened") is not False
        or raw.get("holdout_accessed") is not False
        or raw.get("production_accessed") is not False
    ):
        _fail("PRELAUNCH_SMOKE_INVALID", "Compute-smoke evidence differs")
    expected_difference = {
        "added": 0,
        "removed": 0,
        "content_modified": 0,
        "mode_modified": 0,
        "new_directories": 0,
        "removed_directories": 0,
        "new_symlinks": 0,
        "identical": True,
    }
    if raw.get("tree_difference") != expected_difference:
        _fail("PRELAUNCH_SMOKE_INVALID", "Bundle tree changed during smoke")
    return {
        "version": PRELAUNCH_VERSION,
        "status": PRELAUNCH_PASS,
        "bundle_fingerprint": outcome.second_parser_bundle_fingerprint,
        "bundle_manifest_sha256": outcome.manifest_sha256,
        "bundle_artifacts": outcome.artifact_count,
        "bundle_bytes": outcome.total_size_bytes,
        "complete_tree_fingerprint": outcome.complete_tree_fingerprint,
        "complete_tree_entry_count": outcome.complete_tree_entry_count,
        "bundle_runtime_mutations": 0,
        "python_bytecode_cache_tolerance": "NONE",
        "compute_smoke": "PASS",
    }


__all__ = [
    "BundlePreflightConfig",
    "PRELAUNCH_FAIL",
    "PRELAUNCH_PASS",
    "PRELAUNCH_VERSION",
    "Stage07PrelaunchError",
    "SubmissionPreflightConfig",
    "run_bundle_preflight",
    "run_submission_preflight",
]

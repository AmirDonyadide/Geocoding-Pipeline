"""Exact public libpostal/pypostal runtime-bundle identity for Stage 7."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn


STAGE07_PARSER_BUNDLE_MANIFEST_VERSION = "stage07_parser_bundle_manifest_v1"
STAGE07_PARSER_BUNDLE_PROFILE_VERSION = "stage07_parser_bundle_profile_v1"
STAGE07_PARSER_BUNDLE_FINGERPRINT_DOMAIN = b"SAFE_STAGE07_PARSER_BUNDLE_V1"
STAGE07_PARSER_BUNDLE_MANIFEST_NAME = "stage07_parser_bundle_manifest.json"
STAGE07_PARSER_BUNDLE_SUCCESS_MARKER = "_SUCCESS.json"

LIBPOSTAL_SOURCE_REPOSITORY = "https://github.com/openvenues/libpostal.git"
LIBPOSTAL_SOURCE_COMMIT = "25099c506612b34b23b1bfe286ca6321fcf06f35"
LIBPOSTAL_VERSION = "1.1.4"
LIBPOSTAL_SOURCE_DESCRIBE = "v1.1.4-2-g25099c50"
LIBPOSTAL_MODEL_FLAVOR = "default"
LIBPOSTAL_BASE_DATA_VERSION = "v1.0.0"
LIBPOSTAL_PARSER_MODEL_VERSION = "v1.0.0"
LIBPOSTAL_LANGUAGE_CLASSIFIER_MODEL_VERSION = "v1.0.0"

PYPPOSTAL_SOURCE_REPOSITORY = "https://github.com/openvenues/pypostal.git"
PYPPOSTAL_SOURCE_COMMIT = "d6666a4f6a2ae0e7b83e037a35412f0f6b45c318"
PYPPOSTAL_VERSION = "1.1.11"
PYPPOSTAL_SOURCE_DESCRIBE = "1.1-53-gd6666a4"
SIX_VERSION = "1.17.0"

PARSER_CALL = "postal.parser.parse_address(stage06_candidate_lower)"
PARSER_LANGUAGE_OPTION = "NONE"
PARSER_COUNTRY_OPTION = "NONE"
PARSER_CONTEXT_POLICY = "NO_SAFE_LANGUAGE_OR_COUNTRY_HINTS"
PARSER_INITIALIZATION_POLICY = "ONE_IMPORT_AND_LIBPOSTAL_SETUP_PER_PROCESS"
PARSER_COMPONENT_TUPLE_CONTRACT = "ORDERED_VALUE_LABEL_TUPLES"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_FILES = frozenset(
    {STAGE07_PARSER_BUNDLE_MANIFEST_NAME, STAGE07_PARSER_BUNDLE_SUCCESS_MARKER}
)


class Stage07ParserBundleError(RuntimeError):
    """Privacy-safe parser-bundle failure with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class ParserBundleArtifact:
    relative_path: str
    role: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ParserBundleBuildIdentity:
    execution_git_sha: str
    compiler_identity: str
    base_python_identity: str
    glibc_identity: str

    def validate(self) -> None:
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        for value in (
            self.compiler_identity,
            self.base_python_identity,
            self.glibc_identity,
        ):
            if not value or "\x00" in value or "\n" in value or len(value) > 500:
                _fail("INVALID_BUILD_IDENTITY", "Build identity is malformed")


@dataclass(frozen=True, slots=True)
class ParserBundleOutcome:
    output_directory: Path
    parser_bundle_fingerprint: str
    parser_model_data_fingerprint: str
    pypostal_runtime_fingerprint: str
    libpostal_shared_library_sha256: str
    manifest_sha256: str
    artifact_count: int
    total_size_bytes: int


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07ParserBundleError(code, detail)


def _reject_holdout_paths(*paths: Path) -> None:
    if any(
        "holdout" in part.casefold()
        for path in paths
        for part in path.resolve(strict=False).parts
    ):
        _fail("HOLDOUT_ACCESS_PROHIBITED", "HOLDOUT paths are prohibited")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(8 * 1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07ParserBundleError(
            "PARSER_BUNDLE_READ_FAILURE", "A public bundle artifact could not be read"
        ) from error
    return digest.hexdigest()


def _canonical_sha256(domain: bytes, value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(domain)
    digest.update(len(payload).to_bytes(8, "big"))
    digest.update(payload)
    return digest.hexdigest()


def _role_for(relative_path: str) -> str:
    if relative_path.startswith("data/libpostal/"):
        return "LIBPOSTAL_MODEL_DATA"
    if relative_path.startswith("lib/") and Path(relative_path).name.startswith(
        "libpostal.so"
    ):
        return "LIBPOSTAL_SHARED_LIBRARY"
    if relative_path.startswith("python/postal/"):
        return "PYPPOSTAL_RUNTIME"
    if relative_path.startswith("python/postal-"):
        return "PYPPOSTAL_PACKAGE_METADATA"
    if relative_path == "python/six.py" or relative_path.startswith("python/six-"):
        return "PYPPOSTAL_SIX_RUNTIME"
    if relative_path.startswith("licenses/"):
        return "LICENSE_EVIDENCE"
    _fail("PARSER_BUNDLE_TOPOLOGY_INVALID", "An artifact has an unapproved role")


def _require_private_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        _fail("PARSER_BUNDLE_DIRECTORY_INVALID", "Bundle root is not a directory")
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        if (
            current_path.is_symlink()
            or stat.S_IMODE(current_path.stat().st_mode) != 0o700
        ):
            _fail("PERMISSION_FAILURE", "Bundle directories must be owner-only")
        for name in directory_names:
            path = current_path / name
            if path.is_symlink():
                _fail("PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle contains a symlink")
        for name in file_names:
            path = current_path / name
            if path.is_symlink():
                _fail("PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle contains a symlink")
            if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
                _fail(
                    "PERMISSION_FAILURE", "Bundle files must be regular and owner-only"
                )


def _artifacts(root: Path) -> tuple[ParserBundleArtifact, ...]:
    artifacts: list[ParserBundleArtifact] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in _TERMINAL_FILES:
            continue
        if path.is_symlink() or not path.is_file():
            _fail("PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle contains a symlink")
        artifacts.append(
            ParserBundleArtifact(
                relative_path=relative,
                role=_role_for(relative),
                size_bytes=path.stat().st_size,
                sha256=_sha256_file(path),
            )
        )
    if not artifacts:
        _fail("PARSER_BUNDLE_EMPTY", "Parser bundle contains no artifacts")
    return tuple(artifacts)


def _role_fingerprint(
    artifacts: tuple[ParserBundleArtifact, ...], role: str, domain: bytes
) -> str:
    selected = [item.to_dict() for item in artifacts if item.role == role]
    if not selected:
        _fail("PARSER_BUNDLE_ARTIFACT_MISSING", "A required artifact role is absent")
    return _canonical_sha256(domain, selected)


def _shared_library_identity(
    artifacts: tuple[ParserBundleArtifact, ...],
) -> ParserBundleArtifact:
    selected = [
        item for item in artifacts if item.relative_path == "lib/libpostal.so.1.1.4"
    ]
    if len(selected) != 1:
        _fail(
            "PARSER_BUNDLE_ARTIFACT_MISSING",
            "Exact libpostal shared library binary is absent",
        )
    return selected[0]


def _scientific_identity(build: ParserBundleBuildIdentity) -> dict[str, object]:
    return {
        "parser_bundle_profile_version": STAGE07_PARSER_BUNDLE_PROFILE_VERSION,
        "libpostal": {
            "source_repository": LIBPOSTAL_SOURCE_REPOSITORY,
            "source_commit": LIBPOSTAL_SOURCE_COMMIT,
            "source_describe": LIBPOSTAL_SOURCE_DESCRIBE,
            "implementation_version": LIBPOSTAL_VERSION,
            "configure_arguments": [
                "--prefix=<private-build-prefix>",
                "--datadir=<private-data-prefix>",
            ],
            "model_flavor": LIBPOSTAL_MODEL_FLAVOR,
            "base_data_version": LIBPOSTAL_BASE_DATA_VERSION,
            "parser_model_version": LIBPOSTAL_PARSER_MODEL_VERSION,
            "language_classifier_model_version": (
                LIBPOSTAL_LANGUAGE_CLASSIFIER_MODEL_VERSION
            ),
            "sse2": "ENABLED_BY_UPSTREAM_X86_64_DEFAULT",
        },
        "pypostal": {
            "source_repository": PYPPOSTAL_SOURCE_REPOSITORY,
            "source_commit": PYPPOSTAL_SOURCE_COMMIT,
            "source_describe": PYPPOSTAL_SOURCE_DESCRIBE,
            "package_version": PYPPOSTAL_VERSION,
            "six_version": SIX_VERSION,
        },
        "parser_call": {
            "call": PARSER_CALL,
            "language": PARSER_LANGUAGE_OPTION,
            "country": PARSER_COUNTRY_OPTION,
            "context_policy": PARSER_CONTEXT_POLICY,
            "initialization_policy": PARSER_INITIALIZATION_POLICY,
            "wrapper_result_contract": PARSER_COMPONENT_TUPLE_CONTRACT,
        },
        "runtime": {
            "python": build.base_python_identity,
            "compiler": build.compiler_identity,
            "glibc": build.glibc_identity,
            "encoding": "UTF-8_STRICT",
            "environment": {
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "PYTHONUTF8": "1",
                "PYTHONHASHSEED": "0",
                "LIBPOSTAL_DATA_DIR": "data/libpostal",
                "LD_LIBRARY_PATH_ENTRY": "lib",
                "PYTHONPATH_ENTRY": "python",
            },
        },
    }


def _license_provenance(
    artifacts: tuple[ParserBundleArtifact, ...],
) -> dict[str, object]:
    model_license_files = [
        item.relative_path
        for item in artifacts
        if item.role == "LIBPOSTAL_MODEL_DATA"
        and any(
            marker in Path(item.relative_path).name.casefold()
            for marker in ("license", "copying", "notice")
        )
    ]
    return {
        "libpostal_code": {
            "license_file": "licenses/libpostal-LICENSE",
            "declared_license": "MIT",
        },
        "libpostal_bundled_sparkey": {
            "license_file": "licenses/libpostal-sparkey-LICENSE",
            "declared_license": "Apache-2.0",
        },
        "pypostal_code": {
            "license_file": "licenses/pypostal-LICENSE",
            "declared_license": "MIT",
        },
        "model_data_license_files_present": model_license_files,
        "model_data_license_status": (
            "LICENSE_FILES_PRESENT_IN_DOWNLOADED_DATA_ASSETS"
            if model_license_files
            else "NO_LICENSE_FILE_PRESENT_IN_DOWNLOADED_DATA_ASSETS"
        ),
        "license_interpretation_added_by_safe": False,
    }


def _fingerprint_payload(
    scientific_identity: Mapping[str, object],
    license_provenance: Mapping[str, object],
    artifacts: tuple[ParserBundleArtifact, ...],
) -> dict[str, object]:
    return {
        "profile": STAGE07_PARSER_BUNDLE_PROFILE_VERSION,
        "scientific_identity": scientific_identity,
        "license_provenance": license_provenance,
        "artifacts": [item.to_dict() for item in artifacts],
    }


def _write_json_exclusive(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        path.chmod(0o600)
    except OSError as error:
        raise Stage07ParserBundleError(
            "PARSER_BUNDLE_WRITE_FAILURE", "Bundle metadata could not be written"
        ) from error


def _fsync_directories(root: Path) -> None:
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(
        directories, key=lambda item: len(item.parts), reverse=True
    ):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_parser_bundle(
    staging_directory: Path,
    output_directory: Path,
    *,
    build_identity: ParserBundleBuildIdentity,
) -> ParserBundleOutcome:
    """Fingerprint and atomically publish a newly built public parser bundle."""
    build_identity.validate()
    _reject_holdout_paths(staging_directory, output_directory)
    if output_directory.exists() or output_directory.is_symlink():
        _fail("OUTPUT_COLLISION", "Parser bundle output already exists")
    if staging_directory.parent.resolve() != output_directory.parent.resolve():
        _fail("ATOMIC_PUBLICATION_REQUIRED", "Staging and output must share a parent")
    _require_private_tree(staging_directory)
    if any((staging_directory / name).exists() for name in _TERMINAL_FILES):
        _fail("OUTPUT_COLLISION", "Parser bundle terminal metadata already exists")
    artifacts = _artifacts(staging_directory)
    scientific = _scientific_identity(build_identity)
    license_provenance = _license_provenance(artifacts)
    model_fingerprint = _role_fingerprint(
        artifacts, "LIBPOSTAL_MODEL_DATA", b"SAFE_STAGE07_LIBPOSTAL_MODEL_DATA_V1"
    )
    pypostal_fingerprint = _canonical_sha256(
        b"SAFE_STAGE07_PYPPOSTAL_RUNTIME_V1",
        [
            item.to_dict()
            for item in artifacts
            if item.role
            in {
                "PYPPOSTAL_RUNTIME",
                "PYPPOSTAL_PACKAGE_METADATA",
                "PYPPOSTAL_SIX_RUNTIME",
            }
        ],
    )
    shared_library = _shared_library_identity(artifacts)
    bundle_fingerprint = _canonical_sha256(
        STAGE07_PARSER_BUNDLE_FINGERPRINT_DOMAIN,
        _fingerprint_payload(scientific, license_provenance, artifacts),
    )
    manifest = {
        "stage07_parser_bundle_manifest_version": (
            STAGE07_PARSER_BUNDLE_MANIFEST_VERSION
        ),
        "status": "STAGE07_PARSER_BUNDLE_FROZEN",
        "parser_bundle_fingerprint": bundle_fingerprint,
        "parser_model_data_fingerprint": model_fingerprint,
        "pypostal_runtime_fingerprint": pypostal_fingerprint,
        "libpostal_shared_library_sha256": shared_library.sha256,
        "scientific_identity": scientific,
        "license_provenance": license_provenance,
        "artifacts": [item.to_dict() for item in artifacts],
        "aggregate": {
            "artifact_count": len(artifacts),
            "total_size_bytes": sum(item.size_bytes for item in artifacts),
        },
        "operational_provenance": {
            "execution_git_sha": build_identity.execution_git_sha,
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", ""),
            "execution_site": os.environ.get("SAFE_EXECUTION_SITE", ""),
            "created_at_utc": _utc_now(),
            "python_platform": platform.platform(),
        },
    }
    manifest_path = staging_directory / STAGE07_PARSER_BUNDLE_MANIFEST_NAME
    _write_json_exclusive(manifest_path, manifest)
    manifest_sha = _sha256_file(manifest_path)
    _write_json_exclusive(
        staging_directory / STAGE07_PARSER_BUNDLE_SUCCESS_MARKER,
        {
            "status": "STAGE07_PARSER_BUNDLE_FROZEN",
            "parser_bundle_fingerprint": bundle_fingerprint,
            "parser_model_data_fingerprint": model_fingerprint,
            "pypostal_runtime_fingerprint": pypostal_fingerprint,
            "libpostal_shared_library_sha256": shared_library.sha256,
            "manifest_sha256": manifest_sha,
            "artifact_count": len(artifacts),
            "total_size_bytes": sum(item.size_bytes for item in artifacts),
        },
    )
    _require_private_tree(staging_directory)
    _fsync_directories(staging_directory)
    parent = output_directory.parent
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    os.replace(staging_directory, output_directory)
    parent_descriptor = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
    return validate_parser_bundle(
        output_directory, expected_parser_bundle_fingerprint=bundle_fingerprint
    )


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07ParserBundleError(
            "PARSER_BUNDLE_MANIFEST_INVALID", "Bundle metadata could not be read"
        ) from error
    if not isinstance(value, dict):
        _fail("PARSER_BUNDLE_MANIFEST_INVALID", "Bundle manifest is not an object")
    return value


def validate_parser_bundle(
    output_directory: Path,
    *,
    expected_parser_bundle_fingerprint: str,
) -> ParserBundleOutcome:
    """Reopen and hash every public runtime/model artifact in a frozen bundle."""
    _reject_holdout_paths(output_directory)
    if _SHA256_RE.fullmatch(expected_parser_bundle_fingerprint) is None:
        _fail("INVALID_FINGERPRINT", "Parser bundle fingerprint is malformed")
    _require_private_tree(output_directory)
    manifest_path = output_directory / STAGE07_PARSER_BUNDLE_MANIFEST_NAME
    success_path = output_directory / STAGE07_PARSER_BUNDLE_SUCCESS_MARKER
    if not manifest_path.is_file() or not success_path.is_file():
        _fail("PARSER_BUNDLE_TERMINAL_MISSING", "Bundle terminal metadata is absent")
    manifest = _load_json(manifest_path)
    success = _load_json(success_path)
    artifacts = _artifacts(output_directory)
    recorded = manifest.get("artifacts")
    scientific = manifest.get("scientific_identity")
    licenses = manifest.get("license_provenance")
    if (
        manifest.get("stage07_parser_bundle_manifest_version")
        != STAGE07_PARSER_BUNDLE_MANIFEST_VERSION
        or manifest.get("status") != "STAGE07_PARSER_BUNDLE_FROZEN"
        or not isinstance(scientific, dict)
        or not isinstance(licenses, dict)
        or recorded != [item.to_dict() for item in artifacts]
    ):
        _fail("PARSER_BUNDLE_MANIFEST_INVALID", "Bundle identity differs")
    bundle_fingerprint = _canonical_sha256(
        STAGE07_PARSER_BUNDLE_FINGERPRINT_DOMAIN,
        _fingerprint_payload(scientific, licenses, artifacts),
    )
    model_fingerprint = _role_fingerprint(
        artifacts, "LIBPOSTAL_MODEL_DATA", b"SAFE_STAGE07_LIBPOSTAL_MODEL_DATA_V1"
    )
    pypostal_fingerprint = _canonical_sha256(
        b"SAFE_STAGE07_PYPPOSTAL_RUNTIME_V1",
        [
            item.to_dict()
            for item in artifacts
            if item.role
            in {
                "PYPPOSTAL_RUNTIME",
                "PYPPOSTAL_PACKAGE_METADATA",
                "PYPPOSTAL_SIX_RUNTIME",
            }
        ],
    )
    shared = _shared_library_identity(artifacts)
    manifest_sha = _sha256_file(manifest_path)
    aggregate = manifest.get("aggregate")
    if (
        bundle_fingerprint != expected_parser_bundle_fingerprint
        or manifest.get("parser_bundle_fingerprint") != bundle_fingerprint
        or manifest.get("parser_model_data_fingerprint") != model_fingerprint
        or manifest.get("pypostal_runtime_fingerprint") != pypostal_fingerprint
        or manifest.get("libpostal_shared_library_sha256") != shared.sha256
        or not isinstance(aggregate, dict)
        or aggregate.get("artifact_count") != len(artifacts)
        or aggregate.get("total_size_bytes")
        != sum(item.size_bytes for item in artifacts)
        or success.get("status") != "STAGE07_PARSER_BUNDLE_FROZEN"
        or success.get("parser_bundle_fingerprint") != bundle_fingerprint
        or success.get("parser_model_data_fingerprint") != model_fingerprint
        or success.get("pypostal_runtime_fingerprint") != pypostal_fingerprint
        or success.get("libpostal_shared_library_sha256") != shared.sha256
        or success.get("manifest_sha256") != manifest_sha
        or success.get("artifact_count") != len(artifacts)
        or success.get("total_size_bytes") != sum(item.size_bytes for item in artifacts)
    ):
        _fail("PARSER_BUNDLE_FINGERPRINT_MISMATCH", "Bundle fingerprint differs")
    return ParserBundleOutcome(
        output_directory=output_directory,
        parser_bundle_fingerprint=bundle_fingerprint,
        parser_model_data_fingerprint=model_fingerprint,
        pypostal_runtime_fingerprint=pypostal_fingerprint,
        libpostal_shared_library_sha256=shared.sha256,
        manifest_sha256=manifest_sha,
        artifact_count=len(artifacts),
        total_size_bytes=sum(item.size_bytes for item in artifacts),
    )


__all__ = [
    "LIBPOSTAL_BASE_DATA_VERSION",
    "LIBPOSTAL_LANGUAGE_CLASSIFIER_MODEL_VERSION",
    "LIBPOSTAL_MODEL_FLAVOR",
    "LIBPOSTAL_PARSER_MODEL_VERSION",
    "LIBPOSTAL_SOURCE_COMMIT",
    "LIBPOSTAL_VERSION",
    "PARSER_CALL",
    "PARSER_CONTEXT_POLICY",
    "PARSER_INITIALIZATION_POLICY",
    "PYPPOSTAL_SOURCE_COMMIT",
    "PYPPOSTAL_VERSION",
    "ParserBundleBuildIdentity",
    "ParserBundleOutcome",
    "STAGE07_PARSER_BUNDLE_MANIFEST_NAME",
    "STAGE07_PARSER_BUNDLE_PROFILE_VERSION",
    "Stage07ParserBundleError",
    "publish_parser_bundle",
    "validate_parser_bundle",
]

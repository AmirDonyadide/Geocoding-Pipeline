"""Freeze and validate the public-only Stage 7 second-parser runtime bundle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn


SECOND_PARSER_BUNDLE_MANIFEST_VERSION = "stage07_second_parser_bundle_manifest_v1"
SECOND_PARSER_BUNDLE_PROFILE_VERSION = "stage07_second_parser_bundle_profile_v1"
SECOND_PARSER_BUNDLE_FINGERPRINT_DOMAIN = b"SAFE_STAGE07_SECOND_PARSER_BUNDLE_V1"
SECOND_PARSER_BUNDLE_MANIFEST_NAME = "stage07_second_parser_bundle_manifest.json"
SECOND_PARSER_BUNDLE_SUCCESS_MARKER = "_SUCCESS.json"

DEEPPARSE_VERSION = "0.10.0"
DEEPPARSE_SOURCE_COMMIT = "5b17c0bccd6773044f8a61da68a7b8c91c4fd1e8"
DEEPPARSE_WHEEL_SHA256 = (
    "0e4641147f0a27875edb715248d93277082f10610f237a5e2f8c296d576884bd"
)
BPEMB_VERSION = "0.3.6"
BPEMB_WHEEL_SHA256 = "6eabc133bbd0a7dbeb52b2cfed55ca5cacbb38b236ebb1f504b279a2d835e8b7"
DEEPPARSE_MODEL_REPOSITORY = "deepparse/bpemb-attention"
DEEPPARSE_MODEL_REVISION = "4af74dad1d547804dfc2de8f40fb23fbbec5b811"
DEEPPARSE_MODEL_CONFIG_SHA256 = (
    "60155c61595e5e968a860ff40ebf777979d80b4afd923333f121d342375dc219"
)
DEEPPARSE_MODEL_WEIGHTS_SHA256 = (
    "4d761100d70631a3cb53853a530ad39f5be09cedad0f8c3be0d968bd8accecb5"
)
BPEMB_SENTENCEPIECE_SHA256 = (
    "c6064152904900f91e04c97f95e591495f1c601eba70c3a46417f97283c2fdf1"
)
BPEMB_EMBEDDING_ARCHIVE_SHA256 = (
    "2132ce5bee66b04d39f6f013ccb766a2f595963a681da62fbb22b8aa5cce6ad8"
)
BPEMB_EMBEDDING_SHA256 = (
    "bb4d89f01e71046895fde0fe954845e3cc91ff888a63f06e6413328de308ad03"
)
CPYTHON_VERSION = "3.13.15"
CPYTHON_SOURCE_SHA256 = (
    "c28d9d213c09b5b5ab2c29812950e12f746999e099b82894231be954b26baed9"
)
SQLITE_VERSION = "3.46.1"
SQLITE_SOURCE_SHA256 = (
    "67d3fe6d268e6eaddcae3727fce58fcc8e9c53869bdd07a0c61e38ddf2965071"
)
PYTORCH_VERSION = "2.7.1+cpu"

PARSER_CALL = "deepparse.parser.AddressParser(exact_stage06_candidate_lower)"
PARSER_MODEL_TYPE = "bpemb"
PARSER_ATTENTION = True
PARSER_DEVICE = "cpu"
PARSER_WITH_PROBABILITY = True
PARSER_BATCH_SIZE = 1
PARSER_NUM_WORKERS = 0
PARSER_HYPHEN_SPLIT = False
PARSER_CALLER_PREPROCESSORS: tuple[str, ...] = ()
PARSER_INTERNAL_REPRESENTATION = (
    "DEEPPARSE_ALWAYS_LOWERCASES_AND_BPEMB_REPLACES_DIGITS_WITH_ZERO_FOR_FEATURE_LOOKUP"
)
PARSER_OUTPUT_CONTRACT = "ORDERED_NATIVE_TOKEN_TAG_PROBABILITY_STREAM"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TERMINAL_FILES = frozenset(
    {SECOND_PARSER_BUNDLE_MANIFEST_NAME, SECOND_PARSER_BUNDLE_SUCCESS_MARKER}
)


class Stage07SecondParserBundleError(RuntimeError):
    """Privacy-safe second-parser bundle failure with a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class SecondParserBundleArtifact:
    relative_path: str
    role: str
    size_bytes: int
    mode: str
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SecondParserBundleBuildIdentity:
    execution_git_sha: str
    compiler_identity: str
    glibc_identity: str
    python_configure_arguments: tuple[str, ...]

    def validate(self) -> None:
        if _GIT_SHA_RE.fullmatch(self.execution_git_sha) is None:
            _fail("INVALID_GIT_COMMIT", "Execution Git SHA must be a full SHA")
        for value in (self.compiler_identity, self.glibc_identity):
            if not value or "\x00" in value or "\n" in value or len(value) > 500:
                _fail("INVALID_BUILD_IDENTITY", "Build identity is malformed")
        if not self.python_configure_arguments or any(
            not value or "\x00" in value or "\n" in value
            for value in self.python_configure_arguments
        ):
            _fail("INVALID_BUILD_IDENTITY", "Python configure identity is malformed")


@dataclass(frozen=True, slots=True)
class SecondParserBundleOutcome:
    output_directory: Path
    second_parser_bundle_fingerprint: str
    second_parser_model_fingerprint: str
    second_parser_runtime_fingerprint: str
    manifest_sha256: str
    artifact_count: int
    total_size_bytes: int


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07SecondParserBundleError(code, detail)


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
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_READ_FAILURE",
            "A public bundle artifact could not be read",
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
    if relative_path.startswith("runtime/"):
        return "PINNED_PYTHON_AND_PACKAGE_RUNTIME"
    if relative_path.startswith("cache/models--deepparse--bpemb-attention/"):
        return "DEEPPARSE_ATTENTION_MODEL"
    if relative_path.startswith("cache/multi/"):
        return "BPEMB_MULTILINGUAL_MODEL"
    if relative_path.startswith("sources/"):
        return "PUBLIC_SOURCE_AND_INSTALL_PROVENANCE"
    if relative_path.startswith("licenses/"):
        return "LICENSE_EVIDENCE"
    if relative_path.startswith("metadata/"):
        return "RUNTIME_METADATA"
    _fail("SECOND_PARSER_BUNDLE_TOPOLOGY_INVALID", "Unapproved artifact role")


def _require_private_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_DIRECTORY_INVALID", "Root is not a directory")
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        if (
            current_path.is_symlink()
            or stat.S_IMODE(current_path.stat().st_mode) != 0o700
        ):
            _fail("PERMISSION_FAILURE", "Bundle directories must be owner-only")
        for name in directory_names:
            if (current_path / name).is_symlink():
                _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        for name in file_names:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
            mode = stat.S_IMODE(path.stat().st_mode)
            if mode not in {0o600, 0o700}:
                _fail("PERMISSION_FAILURE", "Bundle files must be owner-only")


def _artifacts(root: Path) -> tuple[SecondParserBundleArtifact, ...]:
    artifacts: list[SecondParserBundleArtifact] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in _TERMINAL_FILES:
            continue
        if path.is_symlink() or not path.is_file():
            _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        artifacts.append(
            SecondParserBundleArtifact(
                relative_path=relative,
                role=_role_for(relative),
                size_bytes=path.stat().st_size,
                mode=f"{stat.S_IMODE(path.stat().st_mode):04o}",
                sha256=_sha256_file(path),
            )
        )
    if not artifacts:
        _fail("SECOND_PARSER_BUNDLE_EMPTY", "Bundle contains no artifacts")
    return tuple(artifacts)


def _role_fingerprint(
    artifacts: tuple[SecondParserBundleArtifact, ...],
    roles: frozenset[str],
    domain: bytes,
) -> str:
    selected = [item.to_dict() for item in artifacts if item.role in roles]
    if not selected:
        _fail("SECOND_PARSER_BUNDLE_ARTIFACT_MISSING", "Required role is absent")
    return _canonical_sha256(domain, selected)


def _scientific_identity(
    build: SecondParserBundleBuildIdentity,
) -> dict[str, object]:
    return {
        "profile_version": SECOND_PARSER_BUNDLE_PROFILE_VERSION,
        "deepparse": {
            "version": DEEPPARSE_VERSION,
            "source_commit": DEEPPARSE_SOURCE_COMMIT,
            "wheel_sha256": DEEPPARSE_WHEEL_SHA256,
            "license": "LGPL-3.0",
        },
        "bpemb": {
            "version": BPEMB_VERSION,
            "wheel_sha256": BPEMB_WHEEL_SHA256,
            "sentencepiece_sha256": BPEMB_SENTENCEPIECE_SHA256,
            "embedding_archive_sha256": BPEMB_EMBEDDING_ARCHIVE_SHA256,
            "embedding_sha256": BPEMB_EMBEDDING_SHA256,
            "language": "multi",
            "vocabulary_size": 100000,
            "dimension": 300,
            "license": "MIT_CODE",
        },
        "model": {
            "repository": DEEPPARSE_MODEL_REPOSITORY,
            "revision": DEEPPARSE_MODEL_REVISION,
            "config_sha256": DEEPPARSE_MODEL_CONFIG_SHA256,
            "weights_sha256": DEEPPARSE_MODEL_WEIGHTS_SHA256,
            "architecture": "BPEMB_LSTM_SEQ2SEQ_WITH_ATTENTION",
            "separate_model_card_license_field": "NOT_DECLARED",
        },
        "python": {
            "implementation": "CPython",
            "version": CPYTHON_VERSION,
            "source_sha256": CPYTHON_SOURCE_SHA256,
            "configure_arguments": list(build.python_configure_arguments),
        },
        "sqlite": {
            "version": SQLITE_VERSION,
            "source_sha256": SQLITE_SOURCE_SHA256,
            "linkage": "STATIC_IN_CPYTHON_SQLITE3_EXTENSION",
            "configure_arguments": [
                "--disable-shared",
                "--enable-static",
                "CFLAGS=-O2 -fPIC",
                "LIBSQLITE3_LIBS=-lsqlite3 -lm -lz",
            ],
            "license": "PUBLIC_DOMAIN",
        },
        "pytorch_version": PYTORCH_VERSION,
        "parser_call": {
            "call": PARSER_CALL,
            "model_type": PARSER_MODEL_TYPE,
            "attention": PARSER_ATTENTION,
            "device": PARSER_DEVICE,
            "with_probability": PARSER_WITH_PROBABILITY,
            "batch_size": PARSER_BATCH_SIZE,
            "num_workers": PARSER_NUM_WORKERS,
            "with_hyphen_split": PARSER_HYPHEN_SPLIT,
            "caller_preprocessors": list(PARSER_CALLER_PREPROCESSORS),
            "internal_representation": PARSER_INTERNAL_REPRESENTATION,
            "output_contract": PARSER_OUTPUT_CONTRACT,
        },
        "determinism": {
            "pythonhashseed": "0",
            "random_seed": 0,
            "numpy_seed": 0,
            "torch_seed": 0,
            "torch_deterministic_algorithms": True,
            "torch_threads": 1,
            "torch_interop_threads": 1,
        },
        "network_policy": "ALL_PUBLIC_ASSETS_PRELOADED; PROTECTED_INFERENCE_NETWORK_DENIED",
        "python_runtime_completeness_gate": (
            "STDLIB_NATIVE_EXTENSIONS_PLUS_SELECTED_MODEL_IMPORT_CLOSURE"
        ),
        "python_bytecode_cache_policy": "EXCLUDED_FROM_PUBLISHED_BUNDLE",
        "binary_linkage_policy": "FULL_ELF_LDD_READELF_GATE_IN_COMPUTE_SMOKE",
        "build": {
            "execution_git_sha": build.execution_git_sha,
            "compiler_identity": build.compiler_identity,
            "glibc_identity": build.glibc_identity,
        },
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_WRITE_FAILURE",
            "A public bundle metadata file could not be written",
        ) from error


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _manifest_payload(
    *,
    artifacts: tuple[SecondParserBundleArtifact, ...],
    build: SecondParserBundleBuildIdentity,
) -> dict[str, object]:
    scientific_identity = _scientific_identity(build)
    model_fingerprint = _role_fingerprint(
        artifacts,
        frozenset({"DEEPPARSE_ATTENTION_MODEL", "BPEMB_MULTILINGUAL_MODEL"}),
        b"SAFE_STAGE07_SECOND_PARSER_MODEL_V1",
    )
    runtime_fingerprint = _role_fingerprint(
        artifacts,
        frozenset({"PINNED_PYTHON_AND_PACKAGE_RUNTIME"}),
        b"SAFE_STAGE07_SECOND_PARSER_RUNTIME_V1",
    )
    fingerprint_basis = {
        "scientific_identity": scientific_identity,
        "artifacts": [item.to_dict() for item in artifacts],
        "model_fingerprint": model_fingerprint,
        "runtime_fingerprint": runtime_fingerprint,
    }
    return {
        "version": SECOND_PARSER_BUNDLE_MANIFEST_VERSION,
        "created_at": _utc_now(),
        **fingerprint_basis,
        "second_parser_bundle_fingerprint": _canonical_sha256(
            SECOND_PARSER_BUNDLE_FINGERPRINT_DOMAIN, fingerprint_basis
        ),
        "artifact_count": len(artifacts),
        "total_size_bytes": sum(item.size_bytes for item in artifacts),
        "public_assets_only": True,
        "protected_inputs_opened": False,
    }


def _outcome(root: Path, manifest: Mapping[str, Any]) -> SecondParserBundleOutcome:
    return SecondParserBundleOutcome(
        output_directory=root,
        second_parser_bundle_fingerprint=str(
            manifest["second_parser_bundle_fingerprint"]
        ),
        second_parser_model_fingerprint=str(manifest["model_fingerprint"]),
        second_parser_runtime_fingerprint=str(manifest["runtime_fingerprint"]),
        manifest_sha256=_sha256_file(root / SECOND_PARSER_BUNDLE_MANIFEST_NAME),
        artifact_count=int(manifest["artifact_count"]),
        total_size_bytes=int(manifest["total_size_bytes"]),
    )


def publish_second_parser_bundle(
    staging_directory: Path,
    output_directory: Path,
    *,
    build_identity: SecondParserBundleBuildIdentity,
) -> SecondParserBundleOutcome:
    """Fingerprint and atomically publish a public-only parser bundle."""

    staging = staging_directory.resolve(strict=True)
    output = output_directory.resolve(strict=False)
    _reject_holdout_paths(staging, output)
    build_identity.validate()
    if output.exists():
        _fail("OUTPUT_COLLISION", "Second-parser bundle output already exists")
    if staging.parent != output.parent:
        _fail("PUBLICATION_PARENT_MISMATCH", "Atomic rename requires one parent")
    _require_private_tree(staging)
    artifacts = _artifacts(staging)
    manifest = _manifest_payload(artifacts=artifacts, build=build_identity)
    _atomic_write_json(staging / SECOND_PARSER_BUNDLE_MANIFEST_NAME, manifest)
    manifest_sha256 = _sha256_file(staging / SECOND_PARSER_BUNDLE_MANIFEST_NAME)
    _atomic_write_json(
        staging / SECOND_PARSER_BUNDLE_SUCCESS_MARKER,
        {
            "version": "stage07_second_parser_bundle_success_v1",
            "status": "STAGE07_SECOND_PARSER_BUNDLE_FROZEN",
            "second_parser_bundle_fingerprint": manifest[
                "second_parser_bundle_fingerprint"
            ],
            "manifest_sha256": manifest_sha256,
            "artifact_count": manifest["artifact_count"],
        },
    )
    _fsync_directory(staging)
    try:
        os.replace(staging, output)
        _fsync_directory(output.parent)
    except OSError as error:
        raise Stage07SecondParserBundleError(
            "ATOMIC_PUBLICATION_FAILURE", "Bundle could not be atomically published"
        ) from error
    return validate_second_parser_bundle(
        output,
        expected_second_parser_bundle_fingerprint=str(
            manifest["second_parser_bundle_fingerprint"]
        ),
    )


def validate_second_parser_bundle(
    output_directory: Path,
    *,
    expected_second_parser_bundle_fingerprint: str,
) -> SecondParserBundleOutcome:
    """Reopen and rehash every file in a frozen second-parser bundle."""

    output = output_directory.resolve(strict=True)
    _reject_holdout_paths(output)
    if _SHA256_RE.fullmatch(expected_second_parser_bundle_fingerprint) is None:
        _fail("INVALID_BUNDLE_FINGERPRINT", "Expected fingerprint is malformed")
    _require_private_tree(output)
    manifest_path = output / SECOND_PARSER_BUNDLE_MANIFEST_NAME
    success_path = output / SECOND_PARSER_BUNDLE_SUCCESS_MARKER
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        success = json.loads(success_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_METADATA_INVALID", "Terminal metadata is invalid"
        ) from error
    if manifest.get("version") != SECOND_PARSER_BUNDLE_MANIFEST_VERSION:
        _fail("SECOND_PARSER_BUNDLE_VERSION_MISMATCH", "Manifest version differs")
    build_data = manifest.get("scientific_identity", {}).get("build", {})
    python_data = manifest.get("scientific_identity", {}).get("python", {})
    try:
        build = SecondParserBundleBuildIdentity(
            execution_git_sha=str(build_data["execution_git_sha"]),
            compiler_identity=str(build_data["compiler_identity"]),
            glibc_identity=str(build_data["glibc_identity"]),
            python_configure_arguments=tuple(python_data["configure_arguments"]),
        )
    except (KeyError, TypeError) as error:
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_METADATA_INVALID", "Build identity is absent"
        ) from error
    build.validate()
    artifacts = _artifacts(output)
    expected = _manifest_payload(artifacts=artifacts, build=build)
    for key in (
        "scientific_identity",
        "artifacts",
        "model_fingerprint",
        "runtime_fingerprint",
        "second_parser_bundle_fingerprint",
        "artifact_count",
        "total_size_bytes",
        "public_assets_only",
        "protected_inputs_opened",
    ):
        if manifest.get(key) != expected.get(key):
            _fail("SECOND_PARSER_BUNDLE_MANIFEST_MISMATCH", "Bundle identity differs")
    actual_fingerprint = str(manifest["second_parser_bundle_fingerprint"])
    if actual_fingerprint != expected_second_parser_bundle_fingerprint:
        _fail("SECOND_PARSER_BUNDLE_FINGERPRINT_MISMATCH", "Fingerprint differs")
    manifest_sha256 = _sha256_file(manifest_path)
    if (
        success.get("status") != "STAGE07_SECOND_PARSER_BUNDLE_FROZEN"
        or success.get("second_parser_bundle_fingerprint") != actual_fingerprint
        or success.get("manifest_sha256") != manifest_sha256
        or success.get("artifact_count") != manifest.get("artifact_count")
    ):
        _fail("SECOND_PARSER_BUNDLE_SUCCESS_MISMATCH", "Success marker differs")
    return _outcome(output, manifest)

"""Freeze and validate the public-only Stage 7 second-parser runtime bundle."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import ctypes
import errno
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, NoReturn


SECOND_PARSER_BUNDLE_MANIFEST_VERSION = "stage07_second_parser_bundle_manifest_v2"
SECOND_PARSER_BUNDLE_PROFILE_VERSION = "stage07_second_parser_bundle_profile_v2"
SECOND_PARSER_BUNDLE_FINGERPRINT_DOMAIN = b"SAFE_STAGE07_SECOND_PARSER_BUNDLE_V2"
SECOND_PARSER_TREE_FINGERPRINT_DOMAIN = b"SAFE_STAGE07_SECOND_PARSER_TREE_V1"
SECOND_PARSER_BUNDLE_MANIFEST_NAME = "stage07_second_parser_bundle_manifest.json"
SECOND_PARSER_BUNDLE_SUCCESS_MARKER = "_SUCCESS.json"
SECOND_PARSER_BUNDLE_SUCCESS_VERSION = "stage07_second_parser_bundle_success_v2"
READ_ONLY_DIRECTORY_MODE = 0o555
READ_ONLY_FILE_MODE = 0o444
READ_ONLY_EXECUTABLE_MODE = 0o555

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
DEEPPARSE_RUNTIME_LOCK_VERSION = "stage07_deepparse_runtime_lock_v1"
DEEPPARSE_RUNTIME_LOCK_SHA256 = (
    "3a4fd33e5530c554125e11b040adeb97828a0381549ac8ca36ce2399711cdc83"
)
DEEPPARSE_RUNTIME_HASH_LOCK_VERSION = "stage07_deepparse_runtime_hash_lock_v1"
DEEPPARSE_RUNTIME_HASH_LOCK_SHA256 = (
    "b8663547cc790a05a1ce2ff21810134bea2b0494b5dd17c2fe07d669fdc2aae8"
)
DEEPPARSE_RUNTIME_HASH_LOCK_MANIFEST_SHA256 = (
    "78b1c6e277461c72c893789d9fa2dc91a3fd89c757a8b7026a9c237a28459f32"
)

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
_PINNED_PUBLIC_ARTIFACT_SHA256: Mapping[str, str] = {
    "cache/models--deepparse--bpemb-attention/refs/main": (
        "729862355b9564d0b3a4e90aded7215766fda33b83345fe3b03e10bc0e38075e"
    ),
    (
        "cache/models--deepparse--bpemb-attention/snapshots/"
        f"{DEEPPARSE_MODEL_REVISION}/config.json"
    ): DEEPPARSE_MODEL_CONFIG_SHA256,
    (
        "cache/models--deepparse--bpemb-attention/snapshots/"
        f"{DEEPPARSE_MODEL_REVISION}/model.safetensors"
    ): DEEPPARSE_MODEL_WEIGHTS_SHA256,
    "cache/multi/multi.wiki.bpe.vs100000.model": BPEMB_SENTENCEPIECE_SHA256,
    "cache/multi/multi.wiki.bpe.vs100000.d300.w2v.bin": BPEMB_EMBEDDING_SHA256,
    f"sources/Python-{CPYTHON_VERSION}.tgz": CPYTHON_SOURCE_SHA256,
    "sources/sqlite-autoconf-3460100.tar.gz": SQLITE_SOURCE_SHA256,
    f"sources/deepparse-{DEEPPARSE_VERSION}-py3-none-any.whl": (DEEPPARSE_WHEEL_SHA256),
    f"sources/bpemb-{BPEMB_VERSION}-py3-none-any.whl": BPEMB_WHEEL_SHA256,
    "sources/multi.wiki.bpe.vs100000.d300.w2v.bin.tar.gz": (
        BPEMB_EMBEDDING_ARCHIVE_SHA256
    ),
    "sources/pip-freeze.txt": DEEPPARSE_RUNTIME_LOCK_SHA256,
    "sources/stage07_deepparse_runtime_lock_v1.txt": (DEEPPARSE_RUNTIME_LOCK_SHA256),
    "sources/stage07_deepparse_runtime_hash_lock_v1.txt": (
        DEEPPARSE_RUNTIME_HASH_LOCK_SHA256
    ),
    "sources/stage07_deepparse_runtime_hash_lock_v1.json": (
        DEEPPARSE_RUNTIME_HASH_LOCK_MANIFEST_SHA256
    ),
    "licenses/BPEmb-LICENSE": (
        "a84baca145b26140aa03b6cf123da904a1c79f59cb007996e11544734cabec79"
    ),
    "licenses/CPython-LICENSE": (
        "78b12c3a81360b357002334f0e70ea0e92eebf7a9b358805c03c48484945f3bb"
    ),
    "licenses/DeepParse-LICENSE": (
        "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118"
    ),
    "licenses/DeepParse-model-card.md": (
        "ec40d6b5978fe1ed22e92abe5f9033b5147fc474209dc245df3b4fb8d4dfbf4c"
    ),
    "licenses/SQLite-PUBLIC-DOMAIN-NOTICE": (
        "85a5af182b96fd6917f6807346148632860816c1a180f3fe09f2ee8fa0fa2e1e"
    ),
}
_PINNED_MODEL_CACHE_FILES = frozenset(
    path for path in _PINNED_PUBLIC_ARTIFACT_SHA256 if path.startswith("cache/")
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
class SecondParserTreeEntry:
    relative_path: str
    artifact_type: str
    mode: str
    size_bytes: int
    sha256: str | None
    symlink_target: str | None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SecondParserTreeDifference:
    added: int
    removed: int
    content_modified: int
    mode_modified: int
    new_directories: int
    removed_directories: int
    new_symlinks: int

    @property
    def identical(self) -> bool:
        return not any(asdict(self).values())

    def to_dict(self) -> dict[str, int | bool]:
        return {**asdict(self), "identical": self.identical}


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
    complete_tree_fingerprint: str
    complete_tree_entry_count: int


@dataclass(frozen=True, slots=True)
class SecondParserBundleMetadataOutcome:
    output_directory: Path
    second_parser_bundle_fingerprint: str
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


def _reject_bytecode_cache(root: Path) -> None:
    for path in root.rglob("*"):
        if path.name == "__pycache__" or path.suffix in {".pyc", ".pyo"}:
            _fail(
                "SECOND_PARSER_BYTECODE_CACHE_PROHIBITED",
                "Python bytecode/cache is prohibited in the bundle",
            )


def _require_no_external_hard_links(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        if path.is_file() and path.stat(follow_symlinks=False).st_nlink != 1:
            _fail(
                "SECOND_PARSER_BUNDLE_HARD_LINK_PROHIBITED",
                "Bundle regular files must have exactly one link",
            )


def _require_pinned_public_assets(root: Path) -> None:
    actual_cache_files = frozenset(
        path.relative_to(root).as_posix()
        for path in (root / "cache").rglob("*")
        if path.is_file() and not path.is_symlink()
    )
    if actual_cache_files != _PINNED_MODEL_CACHE_FILES:
        _fail(
            "SECOND_PARSER_MODEL_ASSET_TOPOLOGY_MISMATCH",
            "Immutable model-asset paths differ from the pinned contract",
        )
    for relative_path, expected_sha256 in _PINNED_PUBLIC_ARTIFACT_SHA256.items():
        path = root / relative_path
        if path.is_symlink() or not path.is_file():
            _fail(
                "SECOND_PARSER_PINNED_ARTIFACT_MISSING",
                "A required pinned public artifact is absent",
            )
        if _sha256_file(path) != expected_sha256:
            _fail(
                "SECOND_PARSER_PINNED_ARTIFACT_HASH_MISMATCH",
                "A required pinned public artifact hash differs",
            )
    try:
        reference = root / "cache/models--deepparse--bpemb-attention/refs/main"
        reference_bytes = reference.read_bytes()
        freeze_bytes = (root / "sources/pip-freeze.txt").read_bytes()
        lock_bytes = (
            root / "sources/stage07_deepparse_runtime_lock_v1.txt"
        ).read_bytes()
    except OSError as error:
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_READ_FAILURE",
            "Pinned public bundle provenance could not be read",
        ) from error
    if reference_bytes != DEEPPARSE_MODEL_REVISION.encode("ascii"):
        _fail(
            "SECOND_PARSER_MODEL_REFERENCE_MISMATCH",
            "Model reference is not the exact no-newline revision",
        )
    if freeze_bytes != lock_bytes:
        _fail(
            "SECOND_PARSER_RUNTIME_LOCK_MISMATCH",
            "Installed package freeze differs from its exact runtime lock",
        )


def _require_read_only_tree(root: Path) -> None:
    if not root.is_dir() or root.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_DIRECTORY_INVALID", "Root is not a directory")
    _reject_bytecode_cache(root)
    _require_no_external_hard_links(root)
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        if (
            current_path.is_symlink()
            or stat.S_IMODE(current_path.stat().st_mode) != READ_ONLY_DIRECTORY_MODE
            or current_path.stat().st_uid != os.getuid()
        ):
            _fail(
                "READ_ONLY_BUNDLE_PERMISSION_FAILURE",
                "Bundle directories must be read-only",
            )
        for name in directory_names:
            if (current_path / name).is_symlink():
                _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        for name in file_names:
            path = current_path / name
            if path.is_symlink() or not path.is_file():
                _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
            if (
                stat.S_IMODE(path.stat().st_mode)
                not in {
                    READ_ONLY_FILE_MODE,
                    READ_ONLY_EXECUTABLE_MODE,
                }
                or path.stat().st_uid != os.getuid()
            ):
                _fail(
                    "READ_ONLY_BUNDLE_PERMISSION_FAILURE",
                    "Bundle files must be read-only",
                )
    for terminal_name in _TERMINAL_FILES:
        terminal = root / terminal_name
        if terminal.exists() and stat.S_IMODE(terminal.stat().st_mode) != (
            READ_ONLY_FILE_MODE
        ):
            _fail(
                "READ_ONLY_BUNDLE_PERMISSION_FAILURE",
                "Terminal metadata must be a non-executable read-only file",
            )


def _lock_payload_read_only(root: Path) -> None:
    _require_no_external_hard_links(root)
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_symlink():
            _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        if path.is_dir():
            path.chmod(READ_ONLY_DIRECTORY_MODE)
        elif path.is_file():
            current_mode = stat.S_IMODE(path.stat().st_mode)
            path.chmod(
                READ_ONLY_EXECUTABLE_MODE
                if current_mode & 0o111
                else READ_ONLY_FILE_MODE
            )
        else:
            _fail("SECOND_PARSER_BUNDLE_TOPOLOGY_INVALID", "Special file found")


def _fsync_tree(root: Path) -> None:
    files: list[Path] = []
    directories: list[Path] = [root]
    for path in root.rglob("*"):
        if path.is_symlink():
            _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            directories.append(path)
        else:
            _fail("SECOND_PARSER_BUNDLE_TOPOLOGY_INVALID", "Special file found")
    for path in files:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    for path in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(path)


def _atomic_rename_directory_no_replace(source: Path, destination: Path) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform.startswith("linux"):
        try:
            renameat2 = libc.renameat2
        except AttributeError:
            _fail(
                "ATOMIC_NOREPLACE_UNSUPPORTED",
                "Linux renameat2 is unavailable",
            )
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, source_bytes, -100, destination_bytes, 1)
    elif sys.platform == "darwin":
        try:
            renamex_np = libc.renamex_np
        except AttributeError:
            _fail(
                "ATOMIC_NOREPLACE_UNSUPPORTED",
                "Darwin renamex_np is unavailable",
            )
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        result = renamex_np(source_bytes, destination_bytes, 0x00000004)
    else:
        _fail(
            "ATOMIC_NOREPLACE_UNSUPPORTED",
            "No fail-closed no-replace rename is defined on this platform",
        )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        _fail("OUTPUT_COLLISION", "Publication destination appeared concurrently")
    raise Stage07SecondParserBundleError(
        "ATOMIC_PUBLICATION_FAILURE",
        "Bundle could not be atomically published without replacement",
    ) from OSError(error_number, os.strerror(error_number))


def validate_atomic_noreplace_filesystem(parent: Path) -> dict[str, object]:
    """Exercise atomic no-replace publication on an exact target filesystem."""

    if parent.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Parent is a symlink")
    resolved_parent = parent.resolve(strict=True)
    _reject_holdout_paths(resolved_parent)
    probe = Path(tempfile.mkdtemp(prefix=".stage07-atomic-probe-", dir=resolved_parent))
    probe.chmod(0o700)
    try:
        first_source = probe / "first-source"
        first_destination = probe / "first-destination"
        first_source.mkdir(mode=0o700)
        first_marker = first_source / "marker"
        first_marker.write_bytes(b"stage07-public-atomic-probe")
        first_marker.chmod(0o600)
        _fsync_tree(first_source)
        _atomic_rename_directory_no_replace(first_source, first_destination)
        if first_source.exists() or not (first_destination / "marker").is_file():
            _fail("ATOMIC_PUBLICATION_FAILURE", "No-replace probe identity differs")

        collision_source = probe / "collision-source"
        collision_destination = probe / "collision-destination"
        collision_source.mkdir(mode=0o700)
        collision_destination.mkdir(mode=0o700)
        (collision_source / "source-marker").write_bytes(b"source")
        (collision_destination / "destination-marker").write_bytes(b"destination")
        try:
            _atomic_rename_directory_no_replace(collision_source, collision_destination)
        except Stage07SecondParserBundleError as error:
            if error.code != "OUTPUT_COLLISION":
                raise
        else:
            _fail("ATOMIC_NOREPLACE_FAILURE", "Existing destination was replaced")
        if not (
            (collision_source / "source-marker").is_file()
            and (collision_destination / "destination-marker").is_file()
        ):
            _fail("ATOMIC_NOREPLACE_FAILURE", "Collision probe altered a tree")
        return {
            "atomic_no_replace_first_rename": "PASS",
            "atomic_no_replace_collision": "PASS",
            "existing_destination_preserved": True,
            "recursive_payload_fsync": "PASS",
        }
    finally:
        shutil.rmtree(probe, ignore_errors=False)


def _tree_entries(
    root: Path,
    *,
    include_terminal_files: bool,
    root_mode_override: int | None = None,
    permit_symlinks_for_difference: bool = False,
) -> tuple[SecondParserTreeEntry, ...]:
    root_mode = (
        root_mode_override
        if root_mode_override is not None
        else stat.S_IMODE(root.stat().st_mode)
    )
    entries = [
        SecondParserTreeEntry(
            relative_path=".",
            artifact_type="DIRECTORY",
            mode=f"{root_mode:04o}",
            size_bytes=0,
            sha256=None,
            symlink_target=None,
        )
    ]
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            if not permit_symlinks_for_difference:
                _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Symlink found")
            link_stat = path.lstat()
            entries.append(
                SecondParserTreeEntry(
                    relative_path=relative,
                    artifact_type="SYMLINK",
                    mode=f"{stat.S_IMODE(link_stat.st_mode):04o}",
                    size_bytes=link_stat.st_size,
                    sha256=None,
                    symlink_target=os.readlink(path),
                )
            )
            continue
        if path.is_dir():
            entries.append(
                SecondParserTreeEntry(
                    relative_path=relative,
                    artifact_type="DIRECTORY",
                    mode=f"{stat.S_IMODE(path.stat().st_mode):04o}",
                    size_bytes=0,
                    sha256=None,
                    symlink_target=None,
                )
            )
            continue
        if not path.is_file():
            _fail("SECOND_PARSER_BUNDLE_TOPOLOGY_INVALID", "Special file found")
        if not include_terminal_files and relative in _TERMINAL_FILES:
            continue
        entries.append(
            SecondParserTreeEntry(
                relative_path=relative,
                artifact_type="FILE",
                mode=f"{stat.S_IMODE(path.stat().st_mode):04o}",
                size_bytes=path.stat().st_size,
                sha256=_sha256_file(path),
                symlink_target=None,
            )
        )
    return tuple(entries)


def _tree_fingerprint(entries: tuple[SecondParserTreeEntry, ...]) -> str:
    return _canonical_sha256(
        SECOND_PARSER_TREE_FINGERPRINT_DOMAIN,
        [entry.to_dict() for entry in entries],
    )


def fingerprint_second_parser_bundle_tree(root: Path) -> tuple[str, int]:
    """Return the complete read-only bundle tree fingerprint and entry count."""

    if root.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle root is a symlink")
    resolved = root.resolve(strict=True)
    _reject_holdout_paths(resolved)
    _require_read_only_tree(resolved)
    entries = _tree_entries(resolved, include_terminal_files=True)
    return _tree_fingerprint(entries), len(entries)


def snapshot_second_parser_bundle_tree(
    root: Path,
    *,
    require_read_only: bool = True,
) -> tuple[SecondParserTreeEntry, ...]:
    """Capture a deterministic tree snapshot for pre/post runtime comparison."""

    if root.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle root is a symlink")
    resolved = root.resolve(strict=True)
    _reject_holdout_paths(resolved)
    if require_read_only:
        _require_read_only_tree(resolved)
    return _tree_entries(
        resolved,
        include_terminal_files=True,
        permit_symlinks_for_difference=not require_read_only,
    )


def compare_second_parser_bundle_trees(
    before: tuple[SecondParserTreeEntry, ...],
    after: tuple[SecondParserTreeEntry, ...],
) -> SecondParserTreeDifference:
    """Return privacy-safe counts describing two bundle-tree snapshots."""

    before_by_path = {entry.relative_path: entry for entry in before}
    after_by_path = {entry.relative_path: entry for entry in after}
    added_paths = set(after_by_path) - set(before_by_path)
    removed_paths = set(before_by_path) - set(after_by_path)
    shared_paths = set(before_by_path) & set(after_by_path)
    content_modified = 0
    mode_modified = 0
    for relative_path in shared_paths:
        earlier = before_by_path[relative_path]
        later = after_by_path[relative_path]
        if (
            earlier.artifact_type != later.artifact_type
            or earlier.size_bytes != later.size_bytes
            or earlier.sha256 != later.sha256
            or earlier.symlink_target != later.symlink_target
        ):
            content_modified += 1
        if earlier.mode != later.mode:
            mode_modified += 1
    return SecondParserTreeDifference(
        added=len(added_paths),
        removed=len(removed_paths),
        content_modified=content_modified,
        mode_modified=mode_modified,
        new_directories=sum(
            after_by_path[path].artifact_type == "DIRECTORY" for path in added_paths
        ),
        removed_directories=sum(
            before_by_path[path].artifact_type == "DIRECTORY" for path in removed_paths
        ),
        new_symlinks=sum(
            after_by_path[path].artifact_type == "SYMLINK" for path in added_paths
        ),
    )


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
        "runtime_dependency_lock": {
            "version": DEEPPARSE_RUNTIME_LOCK_VERSION,
            "sha256": DEEPPARSE_RUNTIME_LOCK_SHA256,
            "source": "MANIFEST_BOUND_PUBLIC_PIP_FREEZE_FROM_JOB_1762661",
            "exact_final_freeze_required": True,
        },
        "runtime_acquisition_hash_lock": {
            "version": DEEPPARSE_RUNTIME_HASH_LOCK_VERSION,
            "sha256": DEEPPARSE_RUNTIME_HASH_LOCK_SHA256,
            "require_hashes": True,
            "package_count": 79,
            "provenance_manifest_sha256": (DEEPPARSE_RUNTIME_HASH_LOCK_MANIFEST_SHA256),
        },
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
        "python_bytecode_cache_policy": (
            "PROHIBITED_IN_BUNDLE; PYTHONDONTWRITEBYTECODE=1; PYTHON_MINUS_B; "
            "EXTERNAL_PYTHONPYCACHEPREFIX"
        ),
        "immutability_policy": {
            "directories": "0555",
            "ordinary_files": "0444",
            "executables": "0555",
            "writable_paths_beneath_bundle": 0,
            "mutable_runtime_state": "EXTERNAL_OWNER_ONLY_DIRECTORY",
            "symlinks": "PROHIBITED",
        },
        "binary_linkage_policy": "FULL_ELF_LDD_READELF_GATE_IN_COMPUTE_SMOKE",
        "build": {
            "execution_git_sha": build.execution_git_sha,
            "compiler_identity": build.compiler_identity,
            "glibc_identity": build.glibc_identity,
        },
    }


def _atomic_write_json(
    path: Path, payload: Mapping[str, Any], *, mode: int = 0o600
) -> None:
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
        os.chmod(path, mode)
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
    immutable_payload_tree_fingerprint: str,
    immutable_payload_tree_entry_count: int,
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
        "immutable_payload_tree_fingerprint": immutable_payload_tree_fingerprint,
        "immutable_payload_tree_entry_count": immutable_payload_tree_entry_count,
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
    complete_tree_fingerprint, complete_tree_entry_count = (
        fingerprint_second_parser_bundle_tree(root)
    )
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
        complete_tree_fingerprint=complete_tree_fingerprint,
        complete_tree_entry_count=complete_tree_entry_count,
    )


def publish_second_parser_bundle(
    staging_directory: Path,
    output_directory: Path,
    *,
    build_identity: SecondParserBundleBuildIdentity,
) -> SecondParserBundleOutcome:
    """Fingerprint and atomically publish a public-only parser bundle."""

    if staging_directory.is_symlink() or output_directory.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle root is a symlink")
    staging = staging_directory.resolve(strict=True)
    output = output_directory.resolve(strict=False)
    _reject_holdout_paths(staging, output)
    build_identity.validate()
    if output.exists():
        _fail("OUTPUT_COLLISION", "Second-parser bundle output already exists")
    if staging.parent != output.parent:
        _fail("PUBLICATION_PARENT_MISMATCH", "Atomic rename requires one parent")
    _require_private_tree(staging)
    _reject_bytecode_cache(staging)
    _require_no_external_hard_links(staging)
    _require_pinned_public_assets(staging)
    if any((staging / name).exists() for name in _TERMINAL_FILES):
        _fail("STAGING_TERMINAL_COLLISION", "Terminal metadata already exists")
    _lock_payload_read_only(staging)
    artifacts = _artifacts(staging)
    payload_entries = _tree_entries(
        staging,
        include_terminal_files=False,
        root_mode_override=READ_ONLY_DIRECTORY_MODE,
    )
    payload_tree_fingerprint = _tree_fingerprint(payload_entries)
    payload_tree_entry_count = len(payload_entries)
    manifest = _manifest_payload(
        artifacts=artifacts,
        build=build_identity,
        immutable_payload_tree_fingerprint=payload_tree_fingerprint,
        immutable_payload_tree_entry_count=payload_tree_entry_count,
    )
    _atomic_write_json(
        staging / SECOND_PARSER_BUNDLE_MANIFEST_NAME,
        manifest,
        mode=READ_ONLY_FILE_MODE,
    )
    manifest_sha256 = _sha256_file(staging / SECOND_PARSER_BUNDLE_MANIFEST_NAME)
    _atomic_write_json(
        staging / SECOND_PARSER_BUNDLE_SUCCESS_MARKER,
        {
            "version": SECOND_PARSER_BUNDLE_SUCCESS_VERSION,
            "status": "STAGE07_SECOND_PARSER_BUNDLE_FROZEN",
            "second_parser_bundle_fingerprint": manifest[
                "second_parser_bundle_fingerprint"
            ],
            "manifest_sha256": manifest_sha256,
            "artifact_count": manifest["artifact_count"],
            "immutable_payload_tree_fingerprint": payload_tree_fingerprint,
            "immutable_payload_tree_entry_count": payload_tree_entry_count,
        },
        mode=READ_ONLY_FILE_MODE,
    )
    _fsync_directory(staging)
    staging.chmod(READ_ONLY_DIRECTORY_MODE)
    _fsync_tree(staging)
    _require_read_only_tree(staging)
    pre_publication_tree_fingerprint, pre_publication_tree_entry_count = (
        fingerprint_second_parser_bundle_tree(staging)
    )
    try:
        _atomic_rename_directory_no_replace(staging, output)
        _fsync_directory(output.parent)
    except OSError as error:
        raise Stage07SecondParserBundleError(
            "ATOMIC_PUBLICATION_FAILURE", "Bundle could not be atomically published"
        ) from error
    outcome = validate_second_parser_bundle(
        output,
        expected_second_parser_bundle_fingerprint=str(
            manifest["second_parser_bundle_fingerprint"]
        ),
    )
    if (
        outcome.complete_tree_fingerprint != pre_publication_tree_fingerprint
        or outcome.complete_tree_entry_count != pre_publication_tree_entry_count
    ):
        _fail("ATOMIC_PUBLICATION_IDENTITY_FAILURE", "Published tree identity differs")
    return outcome


def validate_second_parser_bundle(
    output_directory: Path,
    *,
    expected_second_parser_bundle_fingerprint: str,
) -> SecondParserBundleOutcome:
    """Reopen and rehash every file in a frozen second-parser bundle."""

    if output_directory.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle root is a symlink")
    output = output_directory.resolve(strict=True)
    _reject_holdout_paths(output)
    if _SHA256_RE.fullmatch(expected_second_parser_bundle_fingerprint) is None:
        _fail("INVALID_BUNDLE_FINGERPRINT", "Expected fingerprint is malformed")
    _require_read_only_tree(output)
    _require_pinned_public_assets(output)
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
    payload_entries = _tree_entries(output, include_terminal_files=False)
    payload_tree_fingerprint = _tree_fingerprint(payload_entries)
    payload_tree_entry_count = len(payload_entries)
    expected = _manifest_payload(
        artifacts=artifacts,
        build=build,
        immutable_payload_tree_fingerprint=payload_tree_fingerprint,
        immutable_payload_tree_entry_count=payload_tree_entry_count,
    )
    for key in (
        "scientific_identity",
        "artifacts",
        "model_fingerprint",
        "runtime_fingerprint",
        "immutable_payload_tree_fingerprint",
        "immutable_payload_tree_entry_count",
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
        success.get("version") != SECOND_PARSER_BUNDLE_SUCCESS_VERSION
        or success.get("status") != "STAGE07_SECOND_PARSER_BUNDLE_FROZEN"
        or success.get("second_parser_bundle_fingerprint") != actual_fingerprint
        or success.get("manifest_sha256") != manifest_sha256
        or success.get("artifact_count") != manifest.get("artifact_count")
        or success.get("immutable_payload_tree_fingerprint") != payload_tree_fingerprint
        or success.get("immutable_payload_tree_entry_count") != payload_tree_entry_count
    ):
        _fail("SECOND_PARSER_BUNDLE_SUCCESS_MISMATCH", "Success marker differs")
    return _outcome(output, manifest)


def validate_second_parser_bundle_metadata_only(
    output_directory: Path,
    *,
    expected_second_parser_bundle_fingerprint: str | None = None,
) -> SecondParserBundleMetadataOutcome:
    """Validate topology and terminal identity without hashing payload content."""

    if output_directory.is_symlink():
        _fail("SECOND_PARSER_BUNDLE_SYMLINK_PROHIBITED", "Bundle root is a symlink")
    output = output_directory.resolve(strict=True)
    _reject_holdout_paths(output)
    _require_read_only_tree(output)
    manifest_path = output / SECOND_PARSER_BUNDLE_MANIFEST_NAME
    success_path = output / SECOND_PARSER_BUNDLE_SUCCESS_MARKER
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        success = json.loads(success_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_METADATA_INVALID", "Terminal metadata is invalid"
        ) from error
    fingerprint = manifest.get("second_parser_bundle_fingerprint")
    manifest_sha256 = _sha256_file(manifest_path)
    if (
        manifest.get("version") != SECOND_PARSER_BUNDLE_MANIFEST_VERSION
        or _SHA256_RE.fullmatch(str(fingerprint)) is None
        or manifest.get("public_assets_only") is not True
        or manifest.get("protected_inputs_opened") is not False
        or success.get("version") != SECOND_PARSER_BUNDLE_SUCCESS_VERSION
        or success.get("status") != "STAGE07_SECOND_PARSER_BUNDLE_FROZEN"
        or success.get("second_parser_bundle_fingerprint") != fingerprint
        or success.get("manifest_sha256") != manifest_sha256
        or success.get("artifact_count") != manifest.get("artifact_count")
    ):
        _fail("SECOND_PARSER_BUNDLE_METADATA_INVALID", "Terminal identity differs")
    if (
        expected_second_parser_bundle_fingerprint is not None
        and fingerprint != expected_second_parser_bundle_fingerprint
    ):
        _fail("SECOND_PARSER_BUNDLE_FINGERPRINT_MISMATCH", "Fingerprint differs")
    try:
        artifact_count = int(manifest["artifact_count"])
        total_size_bytes = int(manifest["total_size_bytes"])
    except (KeyError, TypeError, ValueError) as error:
        raise Stage07SecondParserBundleError(
            "SECOND_PARSER_BUNDLE_METADATA_INVALID", "Aggregate identity is absent"
        ) from error
    return SecondParserBundleMetadataOutcome(
        output_directory=output,
        second_parser_bundle_fingerprint=str(fingerprint),
        manifest_sha256=manifest_sha256,
        artifact_count=artifact_count,
        total_size_bytes=total_size_bytes,
    )

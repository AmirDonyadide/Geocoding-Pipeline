"""Public-only compute-node smoke for the frozen DeepParse bundle."""

from __future__ import annotations

import argparse
import builtins
import bz2
import ctypes
import hashlib
import importlib
import importlib.metadata
import json
import lzma
import multiprocessing
import os
import random
import re
import resource
import socket
import sqlite3
import ssl
import subprocess
import sys
import zlib
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

from .s07_second_parser_bundle import (
    compare_second_parser_bundle_trees,
    fingerprint_second_parser_bundle_tree,
    snapshot_second_parser_bundle_tree,
)

SMOKE_VERSION = "stage07_second_parser_compute_smoke_v2"
MODEL_REVISION = "4af74dad1d547804dfc2de8f40fb23fbbec5b811"
EXPECTED_PYTHON_VERSION = "3.13.15"
EXPECTED_SQLITE_VERSION = "3.46.1"
EXPECTED_DISTRIBUTION_COUNT = 79
EXPECTED_DISTRIBUTION_MANIFEST_SHA256 = (
    "4f3c558613f5d13d21dea51a00e206272f522b8dd75be6fef1218127103fc8f4"
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SLURM_JOB_ID_RE = re.compile(r"^[0-9]+$")
_EXTERNAL_MUTABLE_DIRECTORY_ENVIRONMENT = (
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
)
PUBLIC_SYNTHETIC_ELIGIBLE_CASES = (
    "10 Synthetic Example Road, Testville NY 10001",
    "улица Примерная 10, Тестоград",
    "서울특별시 중구 예시로 10",
)
PUBLIC_SYNTHETIC_SELECTION_FINGERPRINT = hashlib.sha256(
    json.dumps(
        PUBLIC_SYNTHETIC_ELIGIBLE_CASES,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


def _multiprocessing_child(connection: Any) -> None:
    connection.send(("PASS", os.getpid()))
    connection.close()


def _atomic_write(path: Path, value: object) -> None:
    payload = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _binary_linkage(bundle: Path) -> dict[str, object]:
    candidates = sorted(
        {
            *bundle.joinpath("runtime").rglob("*.so"),
            *bundle.joinpath("runtime").rglob("*.so.*"),
            bundle / "runtime/bin/python3.13",
        }
    )
    elf_files = 0
    linked_files = 0
    dependency_lines = 0
    unresolved = 0
    resolved_libraries: dict[tuple[str, str], dict[str, object]] = {}
    for path in candidates:
        if not path.is_file() or path.is_symlink():
            continue
        header = subprocess.run(
            ["readelf", "-h", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if header.returncode != 0:
            continue
        elf_files += 1
        dynamic = subprocess.run(
            ["readelf", "-d", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if dynamic.returncode != 0 or "NEEDED" not in dynamic.stdout:
            continue
        linked_files += 1
        linkage = subprocess.run(
            ["ldd", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if linkage.returncode != 0:
            unresolved += 1
            continue
        lines = [line for line in linkage.stdout.splitlines() if line.strip()]
        dependency_lines += len(lines)
        unresolved += sum("not found" in line for line in lines)
        for line in lines:
            tokens = line.strip().split()
            library_path: Path | None = None
            if len(tokens) >= 3 and tokens[1] == "=>" and tokens[2].startswith("/"):
                library_path = Path(tokens[2])
            elif tokens and tokens[0].startswith("/"):
                library_path = Path(tokens[0])
            if library_path is None or not library_path.is_file():
                continue
            resolved = library_path.resolve(strict=True)
            digest = _sha256_file(resolved)
            key = (resolved.name, digest)
            resolved_libraries[key] = {
                "basename": resolved.name,
                "size_bytes": resolved.stat().st_size,
                "sha256": digest,
                "scope": (
                    "BUNDLED" if resolved.is_relative_to(bundle) else "COMPUTE_IMAGE"
                ),
            }
    if not elf_files or not linked_files:
        raise RuntimeError("BINARY_LINKAGE_AUDIT_EMPTY")
    library_manifest = [resolved_libraries[key] for key in sorted(resolved_libraries)]
    library_payload = json.dumps(
        library_manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "elf_files": elf_files,
        "dynamic_elf_files": linked_files,
        "dynamic_dependency_lines": dependency_lines,
        "unresolved_shared_libraries": unresolved,
        "resolved_library_count": len(library_manifest),
        "resolved_library_manifest": library_manifest,
        "resolved_library_manifest_sha256": hashlib.sha256(library_payload).hexdigest(),
    }


def _digest_components(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_external_runtime_state(bundle: Path) -> dict[str, object]:
    """Require every mutable runtime location to be owner-only and external."""

    resolved_bundle = bundle.resolve(strict=True)
    runtime_root_raw = os.environ.get("STAGE07_SECOND_PARSER_RUNTIME_ROOT", "")
    if not runtime_root_raw:
        raise RuntimeError("EXTERNAL_RUNTIME_STATE_ENVIRONMENT_MISSING")
    raw_runtime_root = Path(runtime_root_raw)
    if raw_runtime_root.is_symlink():
        raise RuntimeError("EXTERNAL_RUNTIME_STATE_INVALID")
    runtime_root = raw_runtime_root.resolve(strict=True)
    runtime_root_stat = runtime_root.stat(follow_symlinks=False)
    if (
        _is_within(runtime_root, resolved_bundle)
        or runtime_root == resolved_bundle
        or not runtime_root.is_dir()
        or (runtime_root_stat.st_mode & 0o777) != 0o700
        or runtime_root_stat.st_uid != os.getuid()
        or not os.access(runtime_root, os.W_OK)
    ):
        raise RuntimeError("EXTERNAL_RUNTIME_STATE_INVALID")
    resolved_paths: dict[str, str] = {}
    for name in _EXTERNAL_MUTABLE_DIRECTORY_ENVIRONMENT:
        raw_value = os.environ.get(name, "")
        if not raw_value:
            raise RuntimeError("EXTERNAL_RUNTIME_STATE_ENVIRONMENT_MISSING")
        raw_path = Path(raw_value)
        if raw_path.is_symlink():
            raise RuntimeError("EXTERNAL_RUNTIME_STATE_INVALID")
        path = raw_path.resolve(strict=True)
        if _is_within(path, resolved_bundle) or path == resolved_bundle:
            raise RuntimeError("MUTABLE_RUNTIME_STATE_INSIDE_BUNDLE")
        if not _is_within(path, runtime_root):
            raise RuntimeError("MUTABLE_RUNTIME_STATE_OUTSIDE_RUNTIME_ROOT")
        path_stat = path.stat(follow_symlinks=False)
        if (
            path.is_symlink()
            or not path.is_dir()
            or (path_stat.st_mode & 0o777) != 0o700
            or path_stat.st_uid != os.getuid()
            or not os.access(path, os.W_OK)
        ):
            raise RuntimeError("EXTERNAL_RUNTIME_STATE_INVALID")
        resolved_paths[name] = str(path)
    model_cache_raw = os.environ.get("STAGE07_SECOND_PARSER_MODEL_CACHE", "")
    if not model_cache_raw:
        raise RuntimeError("IMMUTABLE_MODEL_CACHE_ENVIRONMENT_MISSING")
    model_cache = Path(model_cache_raw).resolve(strict=True)
    if model_cache != resolved_bundle / "cache":
        raise RuntimeError("IMMUTABLE_MODEL_CACHE_IDENTITY_MISMATCH")
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1" or not sys.dont_write_bytecode:
        raise RuntimeError("PYTHON_BYTECODE_SUPPRESSION_REQUIRED")
    return {
        "external_mutable_environment_count": len(resolved_paths),
        "external_mutable_runtime_state": "PASS",
        "external_runtime_root": "PASS",
        "immutable_model_cache": "PASS",
        "python_dont_write_bytecode": "PASS",
    }


def run_smoke(
    bundle: Path,
    bundle_fingerprint: str,
    expected_tree_fingerprint: str,
    output: Path,
) -> dict[str, object]:
    if os.geteuid() == 0:
        raise RuntimeError("ORDINARY_EXECUTION_UID_REQUIRED")
    execution_git_sha = os.environ.get("STAGE07_SECOND_SMOKE_GIT_COMMIT", "")
    slurm_job_id = os.environ.get("SLURM_JOB_ID", "")
    execution_site = os.environ.get("SAFE_EXECUTION_SITE", "")
    if (
        _GIT_SHA_RE.fullmatch(execution_git_sha) is None
        or _SLURM_JOB_ID_RE.fullmatch(slurm_job_id) is None
        or execution_site != "goethe-nhr"
    ):
        raise RuntimeError("SMOKE_EXECUTION_PROVENANCE_INVALID")
    if output.exists() or output.is_symlink():
        raise RuntimeError("SMOKE_OUTPUT_COLLISION")
    if (
        "holdout" in output.as_posix().casefold()
        or "holdout" in bundle.as_posix().casefold()
    ):
        raise RuntimeError("HOLDOUT_ACCESS_PROHIBITED")
    if (
        os.environ.get("HF_HUB_OFFLINE") != "1"
        or os.environ.get("TRANSFORMERS_OFFLINE") != "1"
    ):
        raise RuntimeError("OFFLINE_ENVIRONMENT_REQUIRED")

    runtime_state = validate_external_runtime_state(bundle)
    pre_runtime_snapshot = snapshot_second_parser_bundle_tree(bundle)
    pre_runtime_tree_fingerprint, pre_runtime_tree_entry_count = (
        fingerprint_second_parser_bundle_tree(bundle)
    )
    if pre_runtime_tree_fingerprint != expected_tree_fingerprint:
        raise RuntimeError("PRE_RUNTIME_TREE_FINGERPRINT_MISMATCH")

    network_attempts = 0

    def deny_network(*_args: object, **_kwargs: object) -> None:
        nonlocal network_attempts
        network_attempts += 1
        raise AssertionError("NETWORK_ACCESS_DENIED_DURING_PUBLIC_SMOKE")

    socket.create_connection = deny_network  # type: ignore[assignment]
    socket.socket.connect = deny_network  # type: ignore[method-assign]

    required_imports = (
        "_hashlib",
        "_ssl",
        "bpemb",
        "cloudpathlib",
        "ctypes",
        "deepparse",
        "gensim",
        "huggingface_hub",
        "lzma",
        "multiprocessing",
        "numpy",
        "pandas",
        "poutyne",
        "pymagnitudelight",
        "requests",
        "scipy",
        "sentencepiece",
        "sqlite3",
        "tqdm",
        "torch",
        "transformers",
        "urllib3",
        "zlib",
    )
    imported: list[str] = []
    for name in required_imports:
        importlib.import_module(name)
        imported.append(name)

    import_roots: set[str] = set()
    original_import = builtins.__import__

    def traced_import(
        name: str,
        globals: Mapping[str, object] | None = None,
        locals: Mapping[str, object] | None = None,
        fromlist: Sequence[str] | None = (),
        level: int = 0,
    ) -> ModuleType:
        import_roots.add(name.partition(".")[0])
        return original_import(name, globals, locals, fromlist, level)

    builtins.__import__ = traced_import
    try:
        import numpy
        import torch
        from deepparse.parser import AddressParser

        random.seed(0)
        numpy.random.seed(0)
        torch.manual_seed(0)
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.use_deterministic_algorithms(True)
        parser = AddressParser(
            model_type="bpemb",
            attention_mechanism=True,
            device="cpu",
            verbose=False,
            cache_dir=os.environ["STAGE07_SECOND_PARSER_MODEL_CACHE"],
            offline=True,
        )
        if parser.version != MODEL_REVISION:
            raise RuntimeError("MODEL_REVISION_MISMATCH")
        digests: list[str] = []
        deterministic = 0
        exact_input_acknowledgements = 0
        nonempty_structured_outputs = 0
        for candidate in PUBLIC_SYNTHETIC_ELIGIBLE_CASES:
            first = parser(
                candidate,
                with_prob=True,
                batch_size=1,
                num_workers=0,
                with_hyphen_split=False,
                pre_processors=[],
            )
            second = parser(
                candidate,
                with_prob=True,
                batch_size=1,
                num_workers=0,
                with_hyphen_split=False,
                pre_processors=[],
            )
            if first.raw_address != candidate or second.raw_address != candidate:
                raise RuntimeError("EXACT_INPUT_ACKNOWLEDGEMENT_FAILURE")
            if first.address_parsed_components != second.address_parsed_components:
                raise RuntimeError("SECOND_PARSER_NONDETERMINISTIC")
            if not first.address_parsed_components:
                raise RuntimeError("PUBLIC_SYNTHETIC_PARSE_EMPTY")
            deterministic += 1
            exact_input_acknowledgements += 1
            nonempty_structured_outputs += 1
            digests.append(_digest_components(first.address_parsed_components))
    finally:
        builtins.__import__ = original_import

    parent, child = multiprocessing.get_context("spawn").Pipe(duplex=False)
    process = multiprocessing.get_context("spawn").Process(
        target=_multiprocessing_child, args=(child,)
    )
    process.start()
    child.close()
    message = parent.recv()
    process.join()
    parent.close()
    if process.exitcode != 0 or message[0] != "PASS":
        raise RuntimeError("MULTIPROCESSING_SPAWN_FAILURE")

    linkage = _binary_linkage(bundle)
    if linkage["unresolved_shared_libraries"]:
        raise RuntimeError("UNRESOLVED_SHARED_LIBRARY")
    if network_attempts:
        raise RuntimeError("PUBLIC_SMOKE_NETWORK_ATTEMPT")

    site_packages = bundle / "runtime/lib/python3.13/site-packages"
    if not site_packages.is_dir() or site_packages.is_symlink():
        raise RuntimeError("PINNED_SITE_PACKAGES_TOPOLOGY_INVALID")
    scoped_distributions = tuple(
        importlib.metadata.distributions(path=[str(site_packages)])
    )
    if any(
        not _is_within(
            Path(str(distribution.locate_file(""))).resolve(strict=True), bundle
        )
        for distribution in scoped_distributions
    ):
        raise RuntimeError("DISTRIBUTION_METADATA_OUTSIDE_BUNDLE")
    distributions = sorted(
        {
            (
                distribution.metadata["Name"] or "UNKNOWN",
                distribution.version,
            )
            for distribution in scoped_distributions
        }
    )
    distribution_manifest = [
        {"name": name, "version": version} for name, version in distributions
    ]
    distribution_payload = json.dumps(
        distribution_manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    distribution_manifest_sha256 = hashlib.sha256(distribution_payload).hexdigest()
    if (
        sys.version.split()[0] != EXPECTED_PYTHON_VERSION
        or sqlite3.sqlite_version != EXPECTED_SQLITE_VERSION
        or len(distribution_manifest) != EXPECTED_DISTRIBUTION_COUNT
        or distribution_manifest_sha256 != EXPECTED_DISTRIBUTION_MANIFEST_SHA256
    ):
        raise RuntimeError("PINNED_RUNTIME_IDENTITY_MISMATCH")
    post_runtime_snapshot = snapshot_second_parser_bundle_tree(
        bundle, require_read_only=False
    )
    tree_difference = compare_second_parser_bundle_trees(
        pre_runtime_snapshot, post_runtime_snapshot
    )
    if not tree_difference.identical:
        raise RuntimeError("IMMUTABLE_BUNDLE_RUNTIME_MUTATION")
    post_runtime_tree_fingerprint, post_runtime_tree_entry_count = (
        fingerprint_second_parser_bundle_tree(bundle)
    )
    if (
        post_runtime_tree_fingerprint != pre_runtime_tree_fingerprint
        or post_runtime_tree_entry_count != pre_runtime_tree_entry_count
    ):
        raise RuntimeError("IMMUTABLE_BUNDLE_RUNTIME_MUTATION")
    result: dict[str, object] = {
        "version": SMOKE_VERSION,
        "status": "PASS",
        "execution_git_sha": execution_git_sha,
        "slurm_job_id": slurm_job_id,
        "execution_site": execution_site,
        "bundle_fingerprint": bundle_fingerprint,
        "pre_runtime_tree_fingerprint": pre_runtime_tree_fingerprint,
        "post_runtime_tree_fingerprint": post_runtime_tree_fingerprint,
        "pre_runtime_tree_entry_count": pre_runtime_tree_entry_count,
        "post_runtime_tree_entry_count": post_runtime_tree_entry_count,
        "tree_fingerprint_match": True,
        "tree_difference": tree_difference.to_dict(),
        "python_version": sys.version.split()[0],
        "sqlite_version": sqlite3.sqlite_version,
        "openssl_version": ssl.OPENSSL_VERSION,
        "zlib_version": zlib.ZLIB_VERSION,
        "bz2_imported": bz2 is not None,
        "lzma_imported": lzma is not None,
        "ctypes_imported": ctypes is not None,
        "required_imports": sorted(imported),
        "observed_import_root_count": len(import_roots),
        "installed_distribution_count": len(distribution_manifest),
        "installed_distribution_manifest": distribution_manifest,
        "installed_distribution_manifest_sha256": distribution_manifest_sha256,
        "multiprocessing_spawn": "PASS",
        "network_attempts": network_attempts,
        "synthetic_cases": len(PUBLIC_SYNTHETIC_ELIGIBLE_CASES),
        "public_synthetic_selection_fingerprint": (
            PUBLIC_SYNTHETIC_SELECTION_FINGERPRINT
        ),
        "synthetic_deterministic_matches": deterministic,
        "exact_input_acknowledgements": exact_input_acknowledgements,
        "nonempty_structured_outputs": nonempty_structured_outputs,
        "synthetic_output_digest_count": len(set(digests)),
        "model_revision": MODEL_REVISION,
        "maximum_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "effective_uid_is_root": os.geteuid() == 0,
        "output_write_read": "PASS",
        **runtime_state,
        **linkage,
        "protected_inputs_opened": False,
        "holdout_accessed": False,
        "production_accessed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
    _atomic_write(output, result)
    reopened = json.loads(output.read_text(encoding="utf-8"))
    if reopened != result:
        raise RuntimeError("SMOKE_OUTPUT_REOPEN_MISMATCH")
    descriptor = os.open(output.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Public-only DeepParse compute smoke")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--bundle-fingerprint", required=True)
    parser.add_argument("--expected-tree-fingerprint", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_smoke(
        args.bundle,
        args.bundle_fingerprint,
        args.expected_tree_fingerprint,
        args.output,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


SMOKE_VERSION = "stage07_second_parser_compute_smoke_v1"
MODEL_REVISION = "4af74dad1d547804dfc2de8f40fb23fbbec5b811"
PUBLIC_SYNTHETIC_ELIGIBLE_CASES = (
    "10 Synthetic Example Road, Testville NY 10001",
    "улица Примерная 10, Тестоград",
    "서울특별시 중구 예시로 10",
)


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


def run_smoke(bundle: Path, bundle_fingerprint: str, output: Path) -> dict[str, object]:
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
            cache_dir=os.environ["HF_HOME"],
            offline=True,
        )
        if parser.version != MODEL_REVISION:
            raise RuntimeError("MODEL_REVISION_MISMATCH")
        digests: list[str] = []
        deterministic = 0
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
    distributions = sorted(
        {
            (
                distribution.metadata["Name"] or "UNKNOWN",
                distribution.version,
            )
            for distribution in importlib.metadata.distributions()
        }
    )
    distribution_manifest = [
        {"name": name, "version": version} for name, version in distributions
    ]
    distribution_payload = json.dumps(
        distribution_manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    result: dict[str, object] = {
        "version": SMOKE_VERSION,
        "status": "PASS",
        "bundle_fingerprint": bundle_fingerprint,
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
        "installed_distribution_manifest_sha256": hashlib.sha256(
            distribution_payload
        ).hexdigest(),
        "multiprocessing_spawn": "PASS",
        "network_attempts": network_attempts,
        "synthetic_cases": len(PUBLIC_SYNTHETIC_ELIGIBLE_CASES),
        "synthetic_deterministic_matches": deterministic,
        "synthetic_output_digest_count": len(set(digests)),
        "model_revision": MODEL_REVISION,
        "maximum_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        **linkage,
        "protected_inputs_opened": False,
        "holdout_accessed": False,
        "production_accessed": False,
    }
    output.parent.mkdir(parents=True, exist_ok=False, mode=0o700)
    _atomic_write(output, result)
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
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_smoke(args.bundle, args.bundle_fingerprint, args.output)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

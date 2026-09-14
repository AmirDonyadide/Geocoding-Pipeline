"""Public runtime identity; operational paths/times are not semantic keys."""

from __future__ import annotations

import hashlib
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import unicodedata
from pathlib import Path
from typing import Any

from . import s10_query_contract as c

SOURCE_COMMIT = "457157a92aa053e632cc7fcfd0e12f8a943b2d11"
SOURCE_URL = "https://codeload.github.com/unicode-org/icu/tar.gz/" + SOURCE_COMMIT
TRANSFORMS = ("Grek-Latn", "Cyrl-Latn")
DEPENDENCIES = {
    "CPP_BRIDGE": "src/safe_geocoding_pipeline/preprocessing/stage10_icu_bridge.cpp",
    "PYTHON_WRAPPER": "src/safe_geocoding_pipeline/preprocessing/stages/s10_query_transliteration.py",
    "RUNTIME_LOCK": "src/safe_geocoding_pipeline/preprocessing/stages/s10_runtime_lock.py",
    "IDENTITY_RUNTIME_GUARD": "src/safe_geocoding_pipeline/preprocessing/stages/s10_query_contract.py",
    "SCRIPT_LOADER": "src/safe_geocoding_pipeline/preprocessing/script_reference.py",
    "SCRIPT_DATA": "src/safe_geocoding_pipeline/preprocessing/resources/references/unicode_ucd_16_0_0/Scripts.txt",
    "SCRIPT_MANIFEST": "src/safe_geocoding_pipeline/preprocessing/resources/references/unicode_ucd_16_0_0/manifest.json",
}


def source_dependencies(repository: Path) -> dict[str, str]:
    return {
        role: c.sha256_file(repository / path) for role, path in DEPENDENCIES.items()
    }


def python_assets() -> dict[str, Path]:
    result = {
        "INTERPRETER": Path(sys.executable).resolve(strict=True),
        "UNICODEDATA_EXTENSION": Path(unicodedata.__file__).resolve(strict=True),
    }
    library = sysconfig.get_config_var("LDLIBRARY")
    directory = sysconfig.get_config_var("LIBDIR")
    if library and directory:
        path = Path(directory) / library
        if path.is_file():
            result["PYTHON_LIBRARY"] = path.resolve(strict=True)
    return result


def python_identity() -> dict[str, Any]:
    return {
        "version": platform.python_version(),
        "unicode_version": unicodedata.unidata_version,
        "implementation": platform.python_implementation(),
        "binary_sha256": {
            role: c.sha256_file(p) for role, p in python_assets().items()
        },
    }


def linked_libraries(bridge: Path) -> dict[str, str]:
    """Resolve trusted, already hash-checked ELF binaries, never user payloads."""
    if platform.system() != "Linux":
        # Mac tests do not establish the Linux runtime or its ELF dependencies.
        return {"scope": "MAC_PUBLIC_SYNTHETIC_ONLY"}
    ldd = shutil.which("ldd")
    c.require(ldd is not None, "STAGE10_RUNTIME_DEPENDENCY_INSPECTOR_MISSING")
    assert ldd is not None
    result: dict[str, str] = {}
    for path in (bridge, *python_assets().values()):
        if path.suffix == ".a":
            continue  # Static Python archive is already hashed separately.
        completed = subprocess.run([ldd, str(path)], capture_output=True, text=True)
        c.require(completed.returncode == 0, "STAGE10_ELF_DEPENDENCY_INSPECTION_FAILED")
        for line in completed.stdout.splitlines():
            line = line.strip()
            if line.startswith("linux-vdso.so."):
                continue
            match = re.fullmatch(r"(?:(\S+) => )?(/\S+) \(0x[0-9a-fA-F]+\)", line)
            c.require(match is not None, "STAGE10_ELF_DEPENDENCY_UNRESOLVED")
            assert match is not None
            target = Path(match[2]).resolve(strict=True)
            name = match[1] or target.name
            c.require("libicu" not in name, "STAGE10_DYNAMIC_ICU_PROHIBITED")
            digest = c.sha256_file(target)
            c.require(
                name not in result or result[name] == digest,
                "STAGE10_ELF_DEPENDENCY_CONFLICT",
            )
            result[name] = digest
    return dict(sorted(result.items()))


def semantic_fingerprint(lock: dict[str, Any]) -> str:
    # This is an additional runtime identity. The frozen Stage 10 asset-binding
    # formula still binds the exact complete lock file SHA, including provenance.
    keys = (
        "lock_version",
        "specification_sha256",
        "bridge_source_sha256",
        "source_archive_sha256",
        "source_commit",
        "icu_version",
        "unicode_version",
        "cldr_version",
        "platform",
        "runtime_source_sha256",
        "python_runtime",
        "linked_library_sha256",
        "transliterator_ids",
        "direction",
        "source_data_assets",
    )
    try:
        semantic = {key: lock[key] for key in keys}
        semantic["compiled_artifacts"] = sorted(
            (
                {key: asset[key] for key in ("role", "bytes", "sha256")}
                for asset in lock["artifacts"]
            ),
            key=lambda item: item["role"],
        )
    except (KeyError, TypeError):
        raise c.Stage10Error("STAGE10_RUNTIME_LOCK_FIELDS_INVALID") from None
    return hashlib.sha256(
        b"SAFE:stage10-runtime-semantics:v1\0" + c.canonical(semantic)
    ).hexdigest()

#!/usr/bin/env python3
"""Build exact public ICU sources; no address inputs or geocoding capability.

Linux execution requires Goethe SLURM. Mac use is public/synthetic preparation
only. All outputs are outside Git, exclusive, private and preserved on failure.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.execution_policy import require_goethe_nhr_slurm
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_transliteration as t


def build(archive: Path, root: Path, repository: Path, jobs: int) -> Path:
    if platform.system() == "Linux":
        require_goethe_nhr_slurm("stage10-public-icu-runtime-build")
        c.require_runtime()
    c.require(
        platform.system() in ("Linux", "Darwin"), "STAGE10_BUILD_PLATFORM_UNSUPPORTED"
    )
    c.require(1 <= jobs <= 4, "STAGE10_BUILD_CPU_BOUND_INVALID")
    c.require(
        not any(w in str(root).lower() for w in ("holdout", "production")),
        "STAGE10_BUILD_SCOPE_INVALID",
    )
    c.require(
        c.sha256_file(archive) == t.SOURCE_SHA256,
        "STAGE10_PUBLIC_SOURCE_ARCHIVE_MISMATCH",
    )
    spec_path = repository / "docs/scientific_assets" / t.SPEC_NAME
    c.require(
        c.sha256_file(spec_path) == t.SPEC_SHA256,
        "STAGE10_FROZEN_TRANSLITERATION_SPEC_MISMATCH",
    )
    spec = c.read_json(spec_path)
    source_prefix = "icu-" + spec["icu"]["source_commit"]
    c.require(not os.path.lexists(root), "STAGE10_RUNTIME_BUILD_COLLISION")
    root.mkdir(mode=0o700)
    source_root = root / "source"
    source_root.mkdir(mode=0o700)
    with tarfile.open(archive) as bundle:
        for member in bundle:
            c.require(
                member.name == source_prefix
                or member.name.startswith(source_prefix + "/"),
                "STAGE10_PUBLIC_ARCHIVE_PATH_INVALID",
            )
            license_link = (
                member.issym()
                and member.name == source_prefix + "/icu4c/LICENSE"
                and member.linkname == "../LICENSE"
            )
            c.require(
                license_link
                or (not member.islnk() and (member.isdir() or member.isfile())),
                "STAGE10_PUBLIC_ARCHIVE_TYPE_INVALID",
            )
        bundle.extractall(source_root, filter="data")
    source = source_root / source_prefix
    for asset in spec["source_data_assets"]:
        path = source / asset["path"]
        c.require(
            path.stat().st_size == asset["bytes"]
            and c.sha256_file(path) == asset["sha256"],
            "STAGE10_PUBLIC_TRANSFORM_SOURCE_MISMATCH",
        )
    build_root = root / "build"
    build_root.mkdir(mode=0o700)
    prefix = root / "installed"
    log_path = root / "build.log"
    compiler = shutil.which("c++")
    c.require(compiler is not None, "STAGE10_CXX_COMPILER_MISSING")
    assert compiler is not None
    compiler_version = subprocess.check_output([compiler, "--version"], text=True)
    configure = [
        str(source / "icu4c/source/configure"),
        "--prefix=" + str(prefix),
        "--disable-tests",
        "--disable-samples",
        "--disable-shared",
        "--enable-static",
        "--with-data-packaging=static",
        "CFLAGS=-O2 -fPIC",
        "CXXFLAGS=-O2 -fPIC",
    ]
    bridge_source = (
        repository / "src/safe_geocoding_pipeline/preprocessing/stage10_icu_bridge.cpp"
    )
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    bridge = prefix / "lib" / ("libsafe_stage10_icu" + suffix)
    libraries = [
        prefix / "lib" / name for name in ("libicui18n.a", "libicuuc.a", "libicudata.a")
    ]
    link = [
        compiler,
        "-std=c++17",
        "-O2",
        "-fPIC",
        *(
            ["-dynamiclib"]
            if platform.system() == "Darwin"
            else ["-shared", "-Wl,-Bsymbolic"]
        ),
        "-I" + str(prefix / "include"),
        str(bridge_source),
        *(str(p) for p in libraries),
        "-lpthread",
        "-lm",
        "-o",
        str(bridge),
    ]
    with log_path.open("xb") as log:
        for command in (configure, ["make", f"-j{jobs}"], ["make", "install"], link):
            subprocess.run(
                command,
                cwd=build_root,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
    # Runtime artifacts have no group/other access; build/source state is retained.
    for directory, _, files in os.walk(root):
        os.chmod(directory, 0o700)
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                os.chmod(path, 0o700 if os.access(path, os.X_OK) else 0o600)
    artifact_paths = dict(
        zip(
            ("BRIDGE", "ICU_I18N_STATIC", "ICU_COMMON_STATIC", "ICU_DATA_STATIC"),
            (bridge, *libraries),
            strict=True,
        )
    )
    lock: dict[str, Any] = {
        "lock_version": t.LOCK_VERSION,
        "specification_sha256": c.sha256_file(spec_path),
        "bridge_source_sha256": c.sha256_file(bridge_source),
        "source_archive_sha256": t.SOURCE_SHA256,
        "source_commit": spec["icu"]["source_commit"],
        "icu_version": "77.1",
        "unicode_version": "16.0.0",
        "cldr_version": "47",
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "compiler": compiler_version,
        "compiler_sha256": c.sha256_file(Path(compiler).resolve()),
        "configure_arguments": [
            s.replace(str(root), "${RUNTIME_ROOT}") for s in configure
        ],
        "link_arguments": [
            s.replace(str(root), "${RUNTIME_ROOT}").replace(
                str(repository), "${REPOSITORY}"
            )
            for s in link
        ],
        "synthetic_vectors": [list(v) for v in t.SYNTHETIC_VECTORS],
        "artifacts": [
            {
                "role": role,
                "relative_path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": c.sha256_file(path),
            }
            for role, path in artifact_paths.items()
        ],
        "build_execution": {
            "site": "goethe-nhr"
            if platform.system() == "Linux"
            else "MAC_PUBLIC_SYNTHETIC",
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "git_sha": subprocess.check_output(
                ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
            ).strip(),
        },
    }
    lock_path = root / "runtime_build_lock.json"
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(c.canonical(lock))
    runtime = t.ICUTransliterator(root, lock_path, spec_path, bridge_source)
    runtime.close()
    print("STAGE10_PUBLIC_ICU_RUNTIME_VERIFIED")
    print("runtime_lock_sha256=" + c.sha256_file(lock_path))
    return lock_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    try:
        build(args.archive, args.output_root, args.repository, args.jobs)
    except Exception as error:
        # Public build logs stay private. No arbitrary exception text is portable.
        code = str(error) if isinstance(error, c.Stage10Error) else type(error).__name__
        print("STAGE10_PUBLIC_RUNTIME_BUILD_FAILED:" + code)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

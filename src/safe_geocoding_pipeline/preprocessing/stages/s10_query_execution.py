"""Fail-closed Goethe execution and exact runtime/publication environment gates."""

from __future__ import annotations

import hashlib
import os
import re
import resource
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ...execution_policy import require_goethe_nhr_slurm
from . import s09_reference_io as generic_io
from . import s09_reference_publication as accepted_publication
from . import s10_query_contract as c
from . import s10_query_contexts as contexts
from . import s10_query_input as inputs
from . import s10_query_io as io
from . import s10_query_materializer as materializer
from . import s10_query_operations as ops
from . import s10_query_receipts as receipts
from . import s10_query_publication as pub
from . import s10_query_transliteration as t
from . import s10_publication_trace as trace

RUNTIME_LOCK_SHA = "20bfe735dca8b35b0ea10f1e3d729f2007e4cf3333dd5d5b5cdd527ef638d2cd"
READY_SHA = "7a1125109463d8e6ed10d905ed379f90c4b19025bfbcc4c1cc75f1b0b51700dc"
VALIDATION_SHA = "36fbc8c546f322e8a3e0b64e31411b900984cd9871ce7cf8c2941d90c479c0b9"
SEMANTIC_RUNTIME = "8b0a2232c28898f1dfd581e88fcbdbe8b7e7bebd458abcc852fab4cbfe225a8b"
RUNTIME_RELATIVE = "runtimes/stage10/icu77_linux_f7765d463e00"
PUBLISH_RELATIVE = "derived/controlled/stage10/development"
STAGE08_RELATIVE = "derived/controlled/stage08/development/stage08_development_20260902T132726Z_c04cb97214a9"
STAGE09_RELATIVE = "derived/controlled/stage09/development/stage09_development_20260910T155542Z_3e10ac7c1309"
REPOSITORY = Path(__file__).resolve().parents[4]


def project_quota_available() -> int:
    """PanFS project quota, distinct from filesystem-wide statvfs capacity."""
    try:
        result = subprocess.run(
            ["pan_df", "-k", "/work/footprint"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise c.Stage10Error("STAGE10_PROJECT_QUOTA_UNVERIFIED") from None
    rows = re.findall(
        r"^\s*(?:\S+\s+)?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%\s+/work/footprint\s*$",
        result.stdout,
        re.MULTILINE,
    )
    c.require(
        result.returncode == 0 and len(rows) == 1, "STAGE10_PROJECT_QUOTA_UNVERIFIED"
    )
    total, used, available, _ = map(int, rows[0])
    c.require(used <= total and available <= total, "STAGE10_PROJECT_QUOTA_UNVERIFIED")
    return available * 1024


def verify_design(repository: Path) -> None:
    record = c.read_json(
        repository / "docs/scientific_assets/stage10_design_freeze_v1.json"
    )
    c.require(
        record["design_package_sha256"] == c.DESIGN_PACKAGE_SHA256,
        "STAGE10_DESIGN_PACKAGE_MISMATCH",
    )
    for item in record["documents"]:
        path = repository / item["path"]
        c.require(
            path.stat().st_size == item["bytes"]
            and c.sha256_file(path) == item["sha256"],
            "STAGE10_FROZEN_DESIGN_CHANGED",
        )


def mount_signature(path: Path) -> tuple[str, str, str, str]:
    """Read mount metadata only; no filesystem capability experiment."""
    selected = None
    for line in Path("/proc/self/mountinfo").read_text(encoding="ascii").splitlines():
        left, right = line.split(" - ", 1)
        fields = left.split()
        mount = Path(fields[4].replace("\\040", " ").replace("\\134", "\\"))
        if path.is_relative_to(mount) and (
            selected is None or len(str(mount)) > selected[0]
        ):
            tail = right.split()
            selected = (len(str(mount)), (fields[2], fields[3], fields[4], tail[0]))
    c.require(selected is not None, "STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED")
    assert selected is not None
    return selected[1]


def publication_environment(output: Path, stage09: Path) -> None:
    pub.check_parent(output)
    anchor = inputs.PROJECT_ALIAS.resolve(strict=True)
    c.require(
        output.parent == anchor / PUBLISH_RELATIVE and not output.is_symlink(),
        "STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED",
    )
    observed = mount_signature(output.parent)
    c.require(
        observed == mount_signature(stage09)
        and observed[3] == "panfs"
        and output.parent.stat().st_dev == stage09.stat().st_dev
        and pub.create_seal is accepted_publication.create_seal
        and io.write_exclusive is generic_io.write_exclusive,
        "STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED",
    )


def runtime_ready(root: Path, repository: Path) -> t.ICUTransliterator:
    for name, expected in (
        ("runtime_build_lock.json", RUNTIME_LOCK_SHA),
        ("runtime_validation.json", VALIDATION_SHA),
        ("_READY.json", READY_SHA),
    ):
        raw = pub.read_private(root / name)

        c.require(
            hashlib.sha256(raw).hexdigest() == expected,
            "STAGE10_VERIFIED_RUNTIME_RECORD_MISMATCH",
        )
        c.require(
            (
                repository / "docs/scientific_assets/stage10_runtime_goethe_v1" / name
            ).read_bytes()
            == raw,
            "STAGE10_RUNTIME_EXTERNAL_PIN_MISMATCH",
        )
    c.require(
        not os.path.lexists(root / "runtime_failure_receipt.json"),
        "STAGE10_RUNTIME_FAILURE_RECEIPT_PRESENT",
    )
    runtime = t.ICUTransliterator(
        root,
        root / "runtime_build_lock.json",
        repository / "docs/scientific_assets/stage10_transliteration_spec_v1.json",
        repository / "src/safe_geocoding_pipeline/preprocessing/stage10_icu_bridge.cpp",
    )
    c.require(
        runtime.semantic_fingerprint == SEMANTIC_RUNTIME
        and runtime.lock_sha256 == RUNTIME_LOCK_SHA,
        "STAGE10_RUNTIME_SEMANTIC_MISMATCH",
    )
    return runtime


@dataclass(frozen=True)
class Stage10Config:
    stage06_root: Path
    output_directory: Path
    execution_git_sha: str
    expected_manifest_sha256: str | None = None
    resume_work_root: Path | None = None

    def preflight(self) -> tuple[Path, Path, Path]:
        require_goethe_nhr_slurm("stage10-query-execution")
        c.require_runtime()
        c.require(
            os.environ.get("SLURM_RESTART_COUNT", "0") == "0",
            "STAGE10_AUTOMATIC_RESTART_PROHIBITED",
        )
        c.require(
            bool(re.fullmatch("[a-f0-9]{40}", self.execution_git_sha)),
            "STAGE10_EXECUTABLE_SHA_INVALID",
        )
        verify_design(REPOSITORY)

        def git(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *args],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=False,
            )

        head, status, branch = (
            git("rev-parse", "HEAD"),
            git("status", "--porcelain"),
            git("symbolic-ref", "-q", "HEAD"),
        )
        c.require(
            head.returncode == status.returncode == 0
            and head.stdout.strip() == self.execution_git_sha
            and not status.stdout
            and branch.returncode == 1,
            "STAGE10_CLEAN_EXACT_DETACHED_EXECUTABLE_REQUIRED",
        )
        c.require(
            git("merge-base", "--is-ancestor", c.DESIGN_MERGE, "HEAD").returncode == 0,
            "STAGE10_DESIGN_ANCESTRY_MISMATCH",
        )
        anchor = inputs.PROJECT_ALIAS.resolve(strict=True)
        stage08, stage09, runtime = (
            inputs.controlled_path(anchor / name)
            for name in (STAGE08_RELATIVE, STAGE09_RELATIVE, RUNTIME_RELATIVE)
        )
        output = self.output_directory
        c.require(
            output.is_absolute()
            and not any(
                word in str(output).lower() for word in ("holdout", "production")
            ),
            "STAGE10_DEVELOPMENT_SCOPE_REQUIRED",
        )
        publication_environment(output, stage09)
        inputs.controlled_path(self.stage06_root)
        if self.resume_work_root is not None:
            selected = inputs.controlled_path(self.resume_work_root)
            c.require(
                selected.is_relative_to(output.parent / "work")
                and selected.name == "shards",
                "STAGE10_RESUME_SCOPE_INVALID",
            )
        c.require(
            shutil.disk_usage(output.parent).free >= 256 * 1024**3,
            "STAGE10_DISK_RESERVE_INSUFFICIENT",
        )
        c.require(
            project_quota_available() >= 256 * 1024**3,
            "STAGE10_PROJECT_QUOTA_RESERVE_INSUFFICIENT",
        )
        return stage08, stage09, runtime


@contextmanager
def offline_network() -> Iterator[None]:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise c.Stage10Error("STAGE10_NETWORK_ACCESS_PROHIBITED")

    with (
        patch.object(socket.socket, "connect", blocked),
        patch.object(socket.socket, "connect_ex", blocked),
        patch.object(socket, "create_connection", blocked),
        patch.object(socket, "getaddrinfo", blocked),
    ):
        yield


def run(
    config: Stage10Config, *, validate_only: bool = False
) -> generic_io.PublicationResult:
    with ops.termination_guard():
        return _run(config, validate_only=validate_only)


def _run(
    config: Stage10Config, *, validate_only: bool = False
) -> generic_io.PublicationResult:
    stage08, stage09, runtime_root = config.preflight()
    if not validate_only:
        c.require(
            not os.path.lexists(config.output_directory),
            "STAGE10_DESTINATION_RESERVED_NO_AUTOMATIC_ADOPTION",
        )
    start = time.monotonic()
    runtime = runtime_ready(runtime_root, REPOSITORY)
    work = None
    published = False
    publication_trace: trace.PublicationTrace | None = None
    try:
        with offline_network(), ExitStack() as guards:
            parent = config.output_directory.parent / "work"
            if not parent.exists():
                parent.mkdir(mode=0o700)
            pub.check_parent(parent / "reserved")
            # Retain every workspace/receipt; no overwritten attempt or cleanup.
            root = Path(
                tempfile.mkdtemp(prefix=config.output_directory.name + "_", dir=parent)
            )
            publication_trace = trace.PublicationTrace(
                root, config.output_directory, config.execution_git_sha
            )
            preparation = ops.Progress(root / "input_progress")
            guards.enter_context(
                ops.termination_guard(
                    lambda: work.progress if work is not None else preparation,
                    exit_process=True,
                    on_termination=lambda: publication_trace.failure(
                        c.Stage10Error("STAGE10_TERMINATED")
                    ),
                )
            )
            preparation.event("runtime_initialization_complete")
            preparation.phase = "input_validation"
            publication_trace("input_validation")
            preparation.record(announce=True)
            try:
                with preparation.measure("input_validation"):
                    accepted = inputs.consume_inputs(
                        stage08, stage09, config.stage06_root
                    )
            finally:
                preparation.record(announce=True)
            workspace_root = root / "workspace"
            work = contexts.ContextWorkspace(
                accepted, workspace_root, c.science_fingerprint(runtime.asset_binding)
            )
            publication_trace.counts = work.progress.counts
            io.write_json(
                root / "attempt.json",
                {
                    "execution_git_sha": config.execution_git_sha,
                    "job_id": os.environ["SLURM_JOB_ID"],
                    "input_binding_sha256": accepted.identifier.hex(),
                    "runtime_build_lock_sha256": runtime.lock_sha256,
                    "started_utc": datetime.now(timezone.utc).isoformat(),
                    "validate_only": validate_only,
                },
            )
            provenance = {
                "execution_git_sha": config.execution_git_sha,
                "job_id": os.environ["SLURM_JOB_ID"],
                "started_utc": datetime.now(timezone.utc).isoformat(),
                "workspace": str(root),
                "shard_count": len(materializer.SHARDS),
                "runtime_versions": list(c.RUNTIME),
                "cpus_requested": int(os.environ.get("SLURM_CPUS_PER_TASK", "4")),
                "memory_limit_bytes": 8 * 1024**3,
                "transformation_runtime_root": str(runtime_root),
            }
            runtime_identity = {
                "lock_sha256": runtime.lock_sha256,
                "semantic_fingerprint": runtime.semantic_fingerprint,
                "specification_sha256": t.SPEC_SHA256,
                "asset_binding": runtime.asset_binding.hex(),
                "preparation_executable_sha": "f7765d463e0053a0f062e333d77a75f5ce1bc6a8",
                "preparation_job_id": "1772341",
            }
            try:
                with work.progress.measure("workspace_preparation"):
                    work.prepare()
                work.progress.record(announce=True)
                if validate_only:
                    c.require(
                        config.expected_manifest_sha256 is not None,
                        "STAGE10_EXTERNAL_MANIFEST_PIN_REQUIRED",
                    )
                    assert config.expected_manifest_sha256 is not None
                    manifest = pub.validate_terminal(
                        config.output_directory, config.expected_manifest_sha256, True
                    )
                    materializer.register_outputs(
                        work, config.output_directory, manifest["relations"]
                    )
                    for _ in work.contexts():
                        pass
                    artifact = materializer.CatalogArtifact(
                        work, runtime, [], provenance, runtime_identity
                    )
                    result = pub.adopt(
                        config.output_directory,
                        config.expected_manifest_sha256,
                        artifact.validate,
                    )
                else:
                    c.require(
                        not os.path.lexists(config.output_directory),
                        "STAGE10_DESTINATION_RESERVED_NO_AUTOMATIC_ADOPTION",
                    )
                    work.progress.event("generation_start")
                    publication_trace("generation")
                    records = materializer.generate_catalog(
                        work,
                        runtime,
                        config.execution_git_sha,
                        resume=config.resume_work_root,
                    )
                    work.progress.event("generation_complete")
                    provenance["generation_elapsed_seconds"] = int(
                        time.monotonic() - start
                    )
                    provenance["peak_rss_kib_before_publication"] = resource.getrusage(
                        resource.RUSAGE_SELF
                    ).ru_maxrss
                    artifact = materializer.CatalogArtifact(
                        work, runtime, records, provenance, runtime_identity
                    )
                    work.progress.event("validation_start")
                    result = pub.publish(
                        config.output_directory,
                        artifact.build,
                        artifact.validate,
                        observer=publication_trace,
                    )
            except BaseException as error:
                try:
                    publication_trace.failure(error)
                except BaseException:
                    pass  # Keep the primary exception if storage is unavailable.
                try:
                    work.progress.event("terminal_failure")
                except BaseException:
                    pass
                raise
            published = True
            # Publication already succeeded; receipt/presentation must not turn
            # an adopted immutable artifact into a failed candidate.
            try:
                work.progress.event("validation_complete")
                receipts.write(
                    root / "completed.json",
                    {
                        "manifest_sha256": result.manifest_sha256,
                        "logical_sha256": result.manifest["logical_sha256"],
                        "elapsed_seconds": int(time.monotonic() - start),
                        "max_rss_kib": resource.getrusage(
                            resource.RUSAGE_SELF
                        ).ru_maxrss,
                        "progress": work.progress.snapshot(),
                    },
                )
                work.progress.event("terminal_success")
            except OSError:
                pass
            return result
    except BaseException as error:
        if publication_trace is not None:
            try:
                publication_trace.failure(error)
            except BaseException:
                pass
        raise
    finally:
        primary_error = sys.exc_info()[0] is not None
        try:
            if work is not None:
                work.close()
        except Exception:
            if not published and not primary_error:
                raise
        finally:
            try:
                runtime.close()
            except Exception:
                if not published and not primary_error:
                    raise

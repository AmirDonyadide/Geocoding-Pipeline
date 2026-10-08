"""One guarded offline DEVELOPMENT execution; closed, content-free reporting."""

from __future__ import annotations

import argparse
import os
import re
import resource
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ..execution_policy import require_goethe_nhr_slurm
from .stages import s10_query_execution as accepted_environment
from .stages import s11_semantic_assets as assets
from .stages import s11_semantic_contract as c
from .stages import s11_semantic_input as source
from .stages import s11_semantic_io as io
from .stages import s11_semantic_pipeline as pipeline
from .stages import s11_semantic_publication as publication
from .stages import s11_semantic_trace as trace

REPOSITORY = Path(__file__).resolve().parents[3]
RUNTIME = {"python": "3.14.3", "pyarrow": "25.0.0", "duckdb": "1.5.5"}
LOCAL_RESERVE = 2 * 1024**3
PANFS_RESERVE = 2 * 1024**3


def git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    c.require(result.returncode == 0, "S11_INPUT_BINDING_INVALID")
    return result.stdout.strip()


def no_network(*_: Any, **__: Any) -> Any:
    raise c.Stage11Error("S11_PRIVACY_GUARD_FAILURE")


def tree_bytes(root: Path) -> int:
    total = 0
    if root.exists():
        for parent, _, files in os.walk(root, followlinks=False):
            for name in files:
                try:
                    total += (Path(parent) / name).lstat().st_size
                except FileNotFoundError:
                    pass  # A transient spill file may disappear between samples.
    return total


class StorageMonitor:
    """Sampled transient high-water; never labeled as a continuous peak."""

    def __init__(self, local: Path) -> None:
        self.local = local
        self.maximum = 0
        self.samples = 0
        self.unavailable = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def sample(self) -> None:
        try:
            self.maximum = max(self.maximum, tree_bytes(self.local))
            self.samples += 1
        except OSError:
            self.unavailable += 1

    def _run(self) -> None:
        while not self.stop.wait(2):
            self.sample()

    def close(self) -> None:
        self.stop.set()
        self.thread.join(timeout=5)
        self.sample()


def preflight(executable: str, output: Path) -> tuple[Path, dict[str, Any]]:
    require_goethe_nhr_slurm("stage11-semantic-development")
    c.require(
        re.fullmatch(r"[0-9a-f]{40}", executable) is not None
        and re.fullmatch(r"[0-9]+", os.environ["SLURM_JOB_ID"]) is not None
        and os.environ.get("SLURM_RESTART_COUNT", "0") == "0",
        "S11_PRIVACY_GUARD_FAILURE",
    )
    c.require(
        git(REPOSITORY, "rev-parse", "HEAD") == executable
        and git(REPOSITORY, "status", "--porcelain") == "",
        "S11_INPUT_BINDING_INVALID",
    )
    git(REPOSITORY, "merge-base", "--is-ancestor", c.BASELINE_SHA, "HEAD")
    c.require(pipeline.runtime() == RUNTIME, "S11_INPUT_BINDING_INVALID")
    c.require(
        output.parent == source.PROJECT / "derived/controlled/stage11/development"
        and not os.path.lexists(output),
        "S11_PUBLICATION_INVALID",
    )
    publication.check_parent(output)
    c.require(
        source.PROJECT.resolve(strict=True) == source.PROJECT, "S11_PUBLICATION_INVALID"
    )
    # Same canonical PanFS mount/topology as the accepted adapter; no substitute
    # publication primitive or storage fallback if assumptions changed.
    c.require(
        accepted_environment.mount_signature(output.parent)
        == accepted_environment.mount_signature(source.ROOT),
        "S11_PUBLICATION_INVALID",
    )
    signature = accepted_environment.mount_signature(output.parent)
    c.require(signature[-1] == "panfs", "S11_PUBLICATION_INVALID")
    joblocal = Path("/local") / os.environ["SLURM_JOB_ID"]
    io.private(joblocal, directory=True)
    c.require(
        joblocal.resolve(strict=True) == joblocal
        and joblocal.stat().st_dev != output.parent.stat().st_dev
        and shutil.disk_usage(joblocal).free >= LOCAL_RESERVE,
        "S11_RESOURCE_FAILURE",
    )
    quota = accepted_environment.project_quota_available()
    c.require(
        quota >= PANFS_RESERVE
        and shutil.disk_usage(output.parent).free >= PANFS_RESERVE,
        "S11_RESOURCE_FAILURE",
    )
    local = joblocal / "stage11-semantic-request"
    local.mkdir(mode=0o700)
    return local, {
        "panfs_project_available_bytes": quota,
        "panfs_filesystem_available_bytes": shutil.disk_usage(output.parent).free,
        "local_available_before_bytes": shutil.disk_usage(joblocal).free,
        "local_requested_bytes": LOCAL_RESERVE,
        "local_reserve_bytes": LOCAL_RESERVE,
        "panfs_reserve_bytes": PANFS_RESERVE,
        "runtime": pipeline.runtime(),
        "mount_filesystem": signature[-1],
    }


def execute(
    executable: str, output: Path, resume: Path | None = None
) -> dict[str, Any]:
    require_goethe_nhr_slurm("stage11-semantic-development")
    local, environment = preflight(executable, output)
    if resume is not None:
        c.require(
            resume.parent.parent == output.parent
            and resume.name == "checkpoints"
            and resume.parent.name.endswith("_attempt")
            and resume.resolve(strict=True) == resume,
            "S11_CHECKPOINT_INVALID",
        )
        io.private(resume, directory=True)
    attempt = output.parent / (output.name + "_attempt")
    attempt.mkdir(mode=0o700)
    receipts = trace.PublicationTrace(attempt, output, executable)
    receipts.local_workspace = local
    receipts.counts = {
        "input_hypotheses_visited": 0,
        "input_hypotheses_expected": 142677,
    }

    def progress(count: int) -> None:
        receipts.counts["input_hypotheses_visited"] = count

    durable = attempt / "checkpoints"
    durable.mkdir(mode=0o700)
    monitor = StorageMonitor(local)
    monitor.thread.start()
    started = time.monotonic_ns()
    result = None
    try:
        receipts("initialization")
        io.write_json(attempt / "preflight.json", environment)
        asset_ids = assets.verify(REPOSITORY)
        assets.verify_implementation(REPOSITORY)
        receipts("input_validation")
        with (
            patch.object(socket, "create_connection", no_network),
            patch.object(socket.socket, "connect", no_network),
            patch.object(socket.socket, "connect_ex", no_network),
        ):
            inputs = source.load_accepted(REPOSITORY, asset_ids)
            result = pipeline.run(
                inputs,
                output,
                local,
                durable,
                asset_ids,
                executable,
                observer=receipts,
                resume=resume,
                progress=progress,
            )
        monitor.close()
        report = {
            "record_version": "stage11_development_execution_v1",
            "status": "DEVELOPMENT_CANDIDATE_PUBLISHED",
            "execution_git_sha": executable,
            "job_id": os.environ["SLURM_JOB_ID"],
            "elapsed_ns": time.monotonic_ns() - started,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "local_sampled_high_water_bytes": monitor.maximum,
            "local_storage_samples": monitor.samples,
            "local_storage_unavailable_samples": monitor.unavailable,
            "local_terminal_bytes": tree_bytes(local),
            "durable_checkpoint_bytes": tree_bytes(durable),
            "artifact_bytes": tree_bytes(output),
            "panfs_project_available_after_bytes": accepted_environment.project_quota_available(),
            "publication_key": output.name,
            "artifact_path": str(output),
            "manifest_sha256": result.manifest_sha256,
            "registration_sha256": result.registration_sha256,
            "commit_record_id": result.commit_record_id,
            "logical_sha256": result.manifest["logical_sha256"],
            "input_binding_sha256": inputs.identifier.hex(),
            "checkpoints": result.manifest["operational_provenance"]["checkpoints"],
            "bindings": asset_ids,
            "replay": "GENERATION_PREPARED_COMMITTED_FULL_PROJECTION_EQUAL",
            "privacy": "PASS_NO_NETWORK_NO_PAYLOAD_EXPORT",
            "technical_failures": int((attempt / "failure.json").exists()),
        }
        io.write_json(attempt / "completed.json", report)
        return report
    except BaseException as error:
        try:
            receipts.failure(error)
        except BaseException:
            pass  # Never mask the primary exception with receipt/quota failures.
        if result is not None:
            # A presentation/measurement failure cannot undo verified publication.
            return {
                "status": "PUBLISHED_PRESENTATION_INCOMPLETE",
                "manifest_sha256": result.manifest_sha256,
                "publication_key": output.name,
                "execution_git_sha": executable,
            }
        raise
    finally:
        try:
            monitor.close()
        except BaseException:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Guarded offline Stage 11 DEVELOPMENT catalog"
    )
    parser.add_argument("--execution-git-sha", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    parser.add_argument("--resume-checkpoints", type=Path)
    args = parser.parse_args(argv)
    try:
        report = execute(
            args.execution_git_sha, args.output_directory, args.resume_checkpoints
        )
    except BaseException as error:
        code = trace.exception_identity(error)
        print(
            c.canonical({"status": "STAGE11_DEVELOPMENT_FAILED", **code}).decode(
                "ascii"
            ),
            end="",
        )
        return 1
    print(c.canonical(report).decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

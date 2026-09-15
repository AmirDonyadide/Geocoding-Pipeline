"""Pre-input runtime/site guards, metadata topology gates and safe error paths."""

from __future__ import annotations

from typing import Any
import sys
from safe_geocoding_pipeline.preprocessing.stages import s10_query_io as io
from safe_geocoding_pipeline.preprocessing.stages import s10_query_transliteration as t

import hashlib
import socket
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing import stage10_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s10_query_input as i
from safe_geocoding_pipeline.preprocessing.stages import s10_query_publication as p


def args() -> Any:
    return [
        "materialize",
        "--stage06-root",
        "/invented-source",
        "--output-directory",
        "/invented-output",
        "--execution-git-sha",
        "a" * 40,
    ]


def test_pre_input_site_guard_has_no_local_bypass(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    monkeypatch.setattr(e, "run", lambda *a, **kw: pytest.fail("input path reached"))
    assert cli.main(args()) == 1
    assert (
        capsys.readouterr().err
        == "STAGE10_GUARD_OR_VALIDATION_FAILURE_ATTEMPT_PRESERVED\n"
    )
    with pytest.raises(Exception):
        i.consume_inputs(Path("/invented-8"), Path("/invented-9"), Path("/invented-6"))


@pytest.mark.parametrize(
    "failure,expected",
    [
        (
            ValueError("invented protected sentinel"),
            "STAGE10_OPERATIONAL_FAILURE_ATTEMPT_PRESERVED",
        ),
        (
            c.Stage10Error("FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION"),
            "STAGE10_COMMIT_OUTCOME_UNVERIFIED_RECONCILIATION_REQUIRED",
        ),
        (
            c.Stage10Error("STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED"),
            "STAGE10_PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED",
        ),
    ],
)
def test_cli_static_diagnostics_no_exception_payload(
    monkeypatch: Any, capsys: Any, failure: Any, expected: Any
) -> None:
    monkeypatch.setattr(cli, "require_goethe_nhr_slurm", lambda _: None)

    def fail(*a: Any, **kw: Any) -> Any:
        raise failure

    monkeypatch.setattr(e, "run", fail)
    assert cli.main(args()) == 1
    observed = capsys.readouterr()
    assert observed.err == expected + "\n"
    assert not observed.out and "sentinel" not in observed.err


def test_no_network_during_materialization() -> None:
    with e.offline_network():
        for operation in (
            lambda: socket.create_connection(("invalid.synthetic", 1)),
            lambda: socket.getaddrinfo("invalid.synthetic", 1),
        ):
            with pytest.raises(c.Stage10Error, match="NETWORK_ACCESS_PROHIBITED"):
                operation()


def test_runtime_external_pin_rejects_corrupt_record_before_loading(
    tmp_path: Any, monkeypatch: Any
) -> None:
    root = tmp_path / "runtime"
    root.mkdir(mode=0o700)
    io.write_json(root / "runtime_build_lock.json", {"invented": True})
    monkeypatch.setattr(
        t, "ICUTransliterator", lambda *a: pytest.fail("loader reached")
    )
    with pytest.raises(c.Stage10Error, match="VERIFIED_RUNTIME_RECORD_MISMATCH"):
        e.runtime_ready(root, tmp_path)


def test_committed_runtime_lock_source_dependencies_unchanged() -> None:
    from safe_geocoding_pipeline.preprocessing.stages import s10_runtime_lock as lock

    repository = Path(__file__).resolve().parents[1]
    root = repository / "docs/scientific_assets/stage10_runtime_goethe_v1"
    build = c.read_json(root / "runtime_build_lock.json")
    assert c.sha256_file(root / "runtime_build_lock.json") == e.RUNTIME_LOCK_SHA
    assert c.sha256_file(root / "_READY.json") == e.READY_SHA
    assert c.sha256_file(root / "runtime_validation.json") == e.VALIDATION_SHA
    assert lock.semantic_fingerprint(build) == e.SEMANTIC_RUNTIME
    assert lock.source_dependencies(repository) == build["runtime_source_sha256"]
    e.verify_design(repository)


@pytest.mark.parametrize("filesystem,other_mount", [("ext4", False), ("panfs", True)])
def test_changed_publication_filesystem_requires_owner_review(
    tmp_path: Any, monkeypatch: Any, filesystem: Any, other_mount: Any
) -> None:
    target = tmp_path / e.PUBLISH_RELATIVE / "invented"
    target.parent.mkdir(mode=0o700, parents=True)
    accepted = tmp_path / "accepted-stage09"
    accepted.mkdir(mode=0o700)
    monkeypatch.setattr(i, "PROJECT_ALIAS", tmp_path)
    monkeypatch.setattr(
        e,
        "mount_signature",
        lambda path: (
            "1:1",
            "/",
            "/different" if other_mount and path == accepted else "/same",
            filesystem,
        ),
    )
    with pytest.raises(c.Stage10Error, match="PUBLICATION_ENVIRONMENT_REVIEW_REQUIRED"):
        e.publication_environment(target, accepted)


def test_primitive_reuse_is_exact() -> None:
    from safe_geocoding_pipeline.preprocessing.stages import (
        s09_reference_publication as accepted,
    )

    assert p.create_seal is accepted.create_seal
    assert p.anchor is accepted.anchor
    assert p.ownership is accepted.ownership
    assert p.read_private is accepted.read_private


def test_presentation_failure_does_not_demote(monkeypatch: Any) -> None:
    from types import SimpleNamespace

    class Broken:
        def write(self, value: Any) -> Any:
            raise OSError("invented output failure")

    seen: list[str] = []
    monkeypatch.setattr(sys, "stdout", Broken())
    monkeypatch.setattr(cli, "_diagnostic", seen.append)
    result: Any = SimpleNamespace(
        path=Path("/invented"),
        manifest_sha256="a" * 64,
        disposition="PASS",
        commit_record_id="b" * 64,
        registration_sha256="c" * 64,
        manifest={
            "logical_sha256": "d" * 64,
            "profile_sha256": "e" * 64,
            "relations": [],
        },
    )
    cli._present(result)
    assert seen == ["STAGE10_PRESENTATION_FAILED_AFTER_PUBLICATION_SUCCESS"]


def test_summary_json_uses_frozen_compact_ascii() -> None:

    # c.canonical is deliberately different from historical Stage 9 pretty JSON.
    assert c.canonical({"invented": "α"}) == b'{"invented":"\\u03b1"}\n'
    assert hashlib.sha256(c.canonical({})).digest()
    assert io.write_json.__module__.endswith("s10_query_io")

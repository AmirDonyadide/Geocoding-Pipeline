"""Stage 12 adapter: permanent reservation, registration, exclusive seal, reopen.

The accepted Stage 9 filesystem primitives are reused without changing their
code or earlier semantics. An uncertain Stage 12 seal requires separately
authorized reconciliation; this adapter never automatically retries publication.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import s09_reference_io as accepted_io
from . import s09_reference_publication as accepted
from . import s12_retrieval_contract as c
from . import s12_storage as io

VERSION = "stage12_publication_record_v1"
CALIBRATION = "STAGE12_DEVELOPMENT_CALIBRATION_EVIDENCE"
FINAL = "STAGE12_DEVELOPMENT_PELIAS_CANDIDATE"
SEAL = "_COMMITTED"
BINDINGS = tuple(
    """
stage12_input_binding_sha256 manifest_sha256 inventory_sha256 executable_sha runtime_inventory_sha256
contract_sha256 profile_sha256 schema_sha256 validation_sha256 extraction_sha256 response_projection_id
campaign_manifest_sha256 projection_provenance_sha256 operations_sha256 retrieval_policy_id
pelias_deployment_fingerprint index_data_identity effective_behavior_id scientific_result_sha256
candidate_relation_sha256 summary_sha256 calibration_protocol_sha256 workload_sha256
adopted_checkpoint_inventory_sha256 owner_freeze_sha256
""".split()
)


def registration(
    namespace: str, publication_key: str, bindings: Mapping[str, Any]
) -> dict[str, Any]:
    c.require(
        namespace in (CALIBRATION, FINAL)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", publication_key)
        is not None
        and set(bindings) == set(BINDINGS),
        "S12_REGISTRATION_INVALID",
    )
    for key, value in bindings.items():
        if key == "owner_freeze_sha256" and namespace == CALIBRATION:
            c.require(value is None, "S12_REGISTRATION_INVALID")
        else:
            c.require(
                type(value) is str
                and re.fullmatch(
                    "[0-9a-f]{40}" if key == "executable_sha" else "[0-9a-f]{64}", value
                )
                is not None,
                "S12_REGISTRATION_INVALID",
            )
    body = {
        "record_version": VERSION,
        "namespace": namespace,
        "publication_key": publication_key,
        "bindings": dict(bindings),
    }
    return {
        "stage12_registration_id": c.identity(
            "SAFE:stage12-publication-record:v1",
            [("record_version", VERSION), ("record_body", c.canonical(body))],
        ).hex(),
        "body": body,
    }


def validate_terminal(
    root: Path,
    expected_manifest_sha256: bytes,
    *,
    committed: bool,
    validate_science: Callable[[Path, dict[str, Any]], None],
) -> dict[str, Any]:
    accepted.check_parent(root)
    accepted_io.topology(root)
    raw = io.read(root / "manifest.json")
    c.require(c.sha(raw) == c.digest(expected_manifest_sha256), "S12_MANIFEST_MISMATCH")
    manifest = io.metadata(raw)
    bindings = dict(manifest["publication_bindings"])
    bindings["manifest_sha256"] = expected_manifest_sha256.hex()
    expected = registration(manifest["kind"], root.name, bindings)
    c.require(
        io.read(root / "registration.json") == c.canonical(expected),
        "S12_REGISTRATION_INVALID",
    )
    c.require(
        manifest["failures"] == 0
        and manifest["unprocessed"] == 0
        and manifest["completed"] == manifest["planned"],
        "S12_PUBLICATION_INCOMPLETE",
    )
    c.require(
        manifest["deployment_intervals_closed"] is True,
        "S12_DEPLOYMENT_CONTINUITY_UNPROVEN",
    )
    if manifest["kind"] == FINAL:
        c.require(manifest["planned"] == 105805, "S12_PUBLICATION_INCOMPLETE")
    inventory = manifest["inventory"]
    c.require(
        c.sha(c.canonical(inventory)).hex() == bindings["inventory_sha256"],
        "S12_INVENTORY_INVALID",
    )
    io.verify_inventory(
        root,
        inventory,
        extra={"manifest.json", "registration.json"} | ({SEAL} if committed else set()),
    )
    if committed:
        c.require(io.read(root / SEAL, limit=0) == b"", "S12_COMMIT_SEAL_INVALID")
    validate_science(root, manifest)
    return manifest


def publish(
    root: Path,
    *,
    build: Callable[[Path], dict[str, Any]],
    validate_science: Callable[[Path, dict[str, Any]], None],
    fault: Callable[[str], None] = lambda _: None,
    failure_receipt: Callable[[], None] = lambda: None,
) -> bytes:
    """No existing reservation adoption and no overwrite, even after interruption."""
    seal_attempted = False
    try:
        with accepted.anchor(root) as parent_fd:
            os.mkdir(root.name, 0o700, dir_fd=parent_fd)
            run_fd = os.open(
                root.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                accepted.ownership(root, parent_fd, run_fd)
                os.fsync(parent_fd)
                fault("reserved")
                manifest = build(root)
                # A manifest cannot contain its own hash; registration supplies it.
                c.require(
                    "manifest_sha256" not in manifest["publication_bindings"],
                    "S12_REGISTRATION_INVALID",
                )
                io.write(root / "manifest.json", c.canonical(manifest))
                manifest_hash = c.sha(io.read(root / "manifest.json"))
                bindings = {
                    **manifest["publication_bindings"],
                    "manifest_sha256": manifest_hash.hex(),
                }
                record = registration(manifest["kind"], root.name, bindings)
                io.write(root / "registration.json", c.canonical(record))
                accepted_io.fsync_tree(root)
                os.fsync(parent_fd)
                validate_terminal(
                    root,
                    manifest_hash,
                    committed=False,
                    validate_science=validate_science,
                )
                fault("before_seal")
                accepted.ownership(root, parent_fd, run_fd)
                seal_attempted = True
                accepted.create_seal(root, run_fd)
                fault("after_seal")
                os.fsync(run_fd)
                os.fsync(parent_fd)
                validate_terminal(
                    root,
                    manifest_hash,
                    committed=True,
                    validate_science=validate_science,
                )
            finally:
                os.close(run_fd)
        validate_terminal(
            root, manifest_hash, committed=True, validate_science=validate_science
        )
        return manifest_hash
    except BaseException as primary:
        try:
            failure_receipt()
        except BaseException:
            pass
        if seal_attempted and isinstance(primary, Exception):
            raise c.Stage12Error(
                "S12_PUBLICATION_OUTCOME_UNKNOWN_REQUIRES_AUTHORIZED_RECONCILIATION"
            ) from None
        raise

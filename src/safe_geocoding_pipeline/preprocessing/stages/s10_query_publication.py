"""Stage 10 registration adapter for the accepted permanent-reservation protocol.

The state transitions below are intentionally frozen copies of Stage 9's
accepted transitions. Primitive operations are imported byte-unchanged. No
Stage 9 namespace, artifact or historical publication semantics are modified.
"""

from __future__ import annotations
import hashlib
import json
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from . import s09_reference_publication as accepted
from . import s09_reference_io as generic_io
from . import s10_query_contract as c
from . import s10_query_io as io

PROTOCOL = accepted.PROTOCOL
SEAL = accepted.SEAL
PROGRESS = accepted.PROGRESS
State = accepted.State
DEVELOPMENT = "STAGE10_DEVELOPMENT_QUERY_HYPOTHESES"
canonical = accepted.canonical
check_parent = accepted.check_parent
anchor = accepted.anchor
ownership = accepted.ownership
identity = accepted.identity
read_private = accepted.read_private
create_seal = accepted.create_seal
registration = accepted.registration
inventory_hash = accepted.inventory_hash


def inventory(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = [item for relation in manifest["relations"] for item in relation["files"]]
    files.extend(manifest["metadata_inventory"])
    result = []
    seen: set[str] = set()
    for item in files:
        name = item["relative_path"]
        c.require(
            isinstance(name, str)
            and name not in seen
            and not Path(name).is_absolute()
            and Path(name).as_posix() == name
            and all(part not in ("", ".", "..") for part in name.split("/"))
            and unicodedata.normalize("NFC", name) == name
            and "\\" not in name
            and name not in (io.MANIFEST_NAME, io.SUCCESS_NAME, SEAL, PROGRESS),
            "PUBLICATION_INVENTORY_PATH_INVALID",
        )
        seen.add(name)
        c.require(
            type(item["bytes"]) is int and item["bytes"] >= 0,
            "PUBLICATION_INVENTORY_SIZE_INVALID",
        )
        c.require(
            bool(re.fullmatch("[0-9a-f]{64}", item["sha256"])),
            "PUBLICATION_INVENTORY_HASH_INVALID",
        )
        result.append({"path": name, "bytes": item["bytes"], "sha256": item["sha256"]})
    return sorted(result, key=lambda item: item["path"].encode("utf-8"))


def bindings(
    root: Path, manifest: Mapping[str, Any], manifest_sha: str
) -> dict[str, Any]:
    c.require(manifest["kind"] == DEVELOPMENT, "STAGE10_PUBLICATION_NAMESPACE_INVALID")
    result = {
        "namespace": DEVELOPMENT,
        "publication_key": root.name,
        "manifest_sha256": manifest_sha,
        "logical_sha256": manifest["logical_sha256"],
        "contract_sha256": manifest["contract_sha256"],
        "profile_sha256": manifest["profile_sha256"],
        "schema_bundle_sha256": manifest["schema_bundle_sha256"],
        "executable_sha": manifest["operational_provenance"]["execution_git_sha"],
        "stage10_input_sha256": manifest["input_binding_sha256"],
        "stage10_science_sha256": manifest["science_sha256"],
        "stage10_budget_sha256": manifest["budget_policy_sha256"],
        "runtime_build_lock_sha256": manifest["runtime"]["lock_sha256"],
        "inventory_sha256": inventory_hash(inventory(manifest)),
    }
    for key, value in result.items():
        if key in ("namespace", "publication_key"):
            continue
        c.require(
            isinstance(value, str)
            and re.fullmatch(
                "[0-9a-f]{40}" if key == "executable_sha" else "[0-9a-f]{64}", value
            )
            is not None,
            "STAGE10_PUBLICATION_IDENTITY_SYNTAX_INVALID",
        )
    return result


def terminal_files(state: State) -> list[str]:
    return [
        io.MANIFEST_NAME,
        *(
            [PROGRESS]
            if state is False
            else [io.SUCCESS_NAME, *([SEAL] if state is True else [])]
        ),
    ]


def validate_terminal(
    root: Path, expected_manifest: str, state: State
) -> dict[str, Any]:
    c.require(
        state is True or state is False or state == "prepared",
        "PUBLICATION_STATE_INVALID",
    )
    check_parent(root)
    # Reject hostile topology before opening even the manifest or a data file.
    generic_io.topology(root)
    raw = read_private(root / io.MANIFEST_NAME)
    c.require(
        hashlib.sha256(raw).hexdigest() == expected_manifest, "MANIFEST_HASH_MISMATCH"
    )
    manifest = json.loads(
        raw,
        object_pairs_hook=c._pairs,
        parse_float=c._not_integer,
        parse_constant=c._not_integer,
    )
    c.require(isinstance(manifest, dict), "JSON_OBJECT_REQUIRED")
    items = inventory(manifest)
    generic_io.topology(
        root, [*terminal_files(state), *(item["path"] for item in items)]
    )
    if state is False:
        c.require(
            read_private(root / PROGRESS) == b"in_progress\n",
            "PRIVATE_PUBLICATION_STATE_INVALID",
        )
    else:
        expected = canonical(registration(bindings(root, manifest, expected_manifest)))
        c.require(
            read_private(root / io.SUCCESS_NAME) == expected, "SUCCESS_BINDING_MISMATCH"
        )
        if state is True:
            c.require(read_private(root / SEAL, limit=0) == b"", "COMMIT_SEAL_INVALID")
    return dict(manifest)


def fault(phase: str, root: Path) -> None:
    """Fixed synthetic fault seam; never configured by CLI/environment."""


def finish(
    final: Path,
    digest: str,
    validate: generic_io.Validate,
    parent_fd: int,
    run_fd: int,
    disposition: str,
) -> generic_io.PublicationResult:
    ownership(final, parent_fd, run_fd)
    fd = os.open(SEAL, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=run_fd)
    try:
        info = os.fstat(fd)
        c.require(
            stat.S_ISREG(info.st_mode) and info.st_size == 0, "COMMIT_SEAL_INVALID"
        )
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(run_fd)
    os.fsync(parent_fd)
    fault("reopen", final)
    manifest = validate(final, digest, True)
    record = registration(bindings(final, manifest, digest))
    result = generic_io.PublicationResult(
        final,
        digest,
        manifest,
        disposition,
        record["commit_record_id"],
        hashlib.sha256(canonical(record)).hexdigest(),
    )
    return result


def last_check(
    result: generic_io.PublicationResult, owned: tuple[tuple[int, int], tuple[int, int]]
) -> None:
    """Last rejection-capable operation, AFTER descriptor/context teardown."""
    fault("last_check", result.path)
    validate_terminal(result.path, result.manifest_sha256, True)
    c.require(
        identity(result.path.parent.lstat()) == owned[0]
        and identity(result.path.lstat()) == owned[1],
        "FINAL_PUBLICATION_OWNERSHIP_MISMATCH",
    )


def adopt(
    final: Path,
    expected_manifest: str,
    validate: generic_io.Validate,
    *,
    _owned: tuple[tuple[int, int], tuple[int, int]] | None = None,
    _disposition: str = "ADOPT_EXISTING_EXACT_COMMITTED",
) -> generic_io.PublicationResult:
    """External exact manifest pin required; optional ownership is invocation-local."""
    try:
        with anchor(final) as parent_fd:
            run_fd = os.open(
                final.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                observed = (identity(os.fstat(parent_fd)), identity(os.fstat(run_fd)))
                c.require(
                    _owned is None or observed == _owned,
                    "FINAL_PUBLICATION_OWNERSHIP_MISMATCH",
                )
                result = finish(
                    final, expected_manifest, validate, parent_fd, run_fd, _disposition
                )
            finally:
                os.close(run_fd)
        last_check(result, observed)
        return result
    except Exception:
        raise c.Stage10Error("FAIL_CLOSED_CONFLICT_OR_INCOMPLETE_RESERVATION") from None


class _ReservationExists(Exception):
    """Internal routing only; carries no artifact values."""


def publish(
    final: Path,
    build: generic_io.Build,
    validate: generic_io.Validate,
    *,
    expected_manifest: str | None = None,
) -> generic_io.PublicationResult:
    # No umask mutation: every publication object has explicit owner-only mode.
    commit_attempted = False
    reserved = False
    digest = ""
    owned = None
    try:
        with anchor(final) as parent_fd:
            try:
                os.mkdir(final.name, 0o700, dir_fd=parent_fd)
            except FileExistsError:
                raise _ReservationExists() from None
            except OSError:
                raise c.Stage10Error(
                    "FAIL_CLOSED_RESERVATION_OUTCOME_UNKNOWN"
                ) from None
            reserved = True
            run_fd = os.open(
                final.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent_fd,
            )
            try:
                owned = (identity(os.fstat(parent_fd)), identity(os.fstat(run_fd)))
                ownership(final, parent_fd, run_fd)
                os.fsync(parent_fd)
                fault("reserved", final)
                ownership(final, parent_fd, run_fd)
                io.write_exclusive(final / PROGRESS, b"in_progress\n")
                manifest = build(final)
                fault("data", final)
                io.write_json(final / io.MANIFEST_NAME, manifest)
                digest = c.sha256_file(final / io.MANIFEST_NAME)
                if expected_manifest is not None:
                    c.require(digest == expected_manifest, "EXPECTED_MANIFEST_MISMATCH")
                fault("manifest", final)
                generic_io.fsync_tree(final)
                validate(final, digest, False)
                record = registration(bindings(final, manifest, digest))
                io.write_exclusive(final / io.SUCCESS_NAME, canonical(record))
                fault("prepared_record", final)
                ownership(final, parent_fd, run_fd)
                os.unlink(PROGRESS, dir_fd=run_fd)
                generic_io.fsync_tree(final)
                os.fsync(parent_fd)
                validate(final, digest, "prepared")
                fault("before_commit", final)
                validate_terminal(final, digest, "prepared")
                ownership(final, parent_fd, run_fd)
                commit_attempted = True
                create_seal(final, run_fd)
                fault("after_commit", final)
                result = finish(final, digest, validate, parent_fd, run_fd, "PASS")
            finally:
                os.close(run_fd)
        last_check(result, owned)
        return result
    except _ReservationExists:
        c.require(
            expected_manifest is not None,
            "FAIL_CLOSED_INCOMPLETE_OR_UNPINNED_RESERVATION",
        )
        assert expected_manifest is not None
        return adopt(final, expected_manifest, validate)
    except Exception:
        if commit_attempted:
            try:
                assert owned is not None
                return adopt(
                    final,
                    digest,
                    validate,
                    _owned=owned,
                    _disposition="ADOPT_COMMITTED_AFTER_RECONCILIATION",
                )
            except Exception:
                raise c.Stage10Error(
                    "FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION"
                ) from None
        if not reserved:
            raise c.Stage10Error("FAIL_CLOSED_RESERVATION_OUTCOME_UNKNOWN") from None
        raise c.Stage10Error("FAIL_CLOSED_UNCOMMITTED_ATTEMPT_PRESERVED") from None

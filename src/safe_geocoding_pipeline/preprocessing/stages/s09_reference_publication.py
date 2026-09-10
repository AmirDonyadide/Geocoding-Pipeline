"""Owner-approved permanent reservation / exclusive commit seal (Stage 9 only).

No rename, lock takeover, destructive recovery or persistent inode identity.
Stage adapters still perform ALL scientific validation before and after commit.
The generic operational binding does not change scientific fingerprints.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Literal

from . import s09_reference_contract as c
from . import s09_reference_io as io

PROTOCOL = "exclusive_run_commit_seal_v2_candidate"
SEAL = "_COMMITTED"
PROGRESS = "_IN_PROGRESS"
State = bool | Literal["prepared"]
PUBLIC = "STAGE09_PUBLIC_REFERENCE_PACK"
DEVELOPMENT = "STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE"


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")


def check_parent(final: Path) -> None:
    c.require(final.is_absolute(), "ABSOLUTE_PUBLICATION_ANCHOR_REQUIRED")
    c.require(
        str(final) == os.path.normpath(str(final)), "PUBLICATION_PATH_NOT_NORMALIZED"
    )
    c.require(
        bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", final.name)),
        "PUBLICATION_KEY_INVALID",
    )
    # Only the caller may canonicalize the configured mount anchor, never a
    # path supplied by the artifact. Every subsequent ancestor is no-follow.
    for parent in reversed((final.parent, *final.parent.parents)):
        c.require(stat.S_ISDIR(parent.lstat().st_mode), "PUBLICATION_ANCESTOR_INVALID")
    info = final.parent.lstat()
    c.require(
        stat.S_IMODE(info.st_mode) == 0o700 and info.st_uid == os.geteuid(),
        "PUBLICATION_PARENT_NOT_PRIVATE",
    )


def identity(info: os.stat_result) -> tuple[int, int]:
    return info.st_dev, info.st_ino


@contextmanager
def anchor(final: Path) -> Iterator[int]:
    check_parent(final)
    fd = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        c.require(
            identity(os.fstat(fd)) == identity(final.parent.lstat()),
            "PUBLICATION_ANCHOR_CHANGED",
        )
        yield fd
    finally:
        os.close(fd)


def ownership(final: Path, parent_fd: int, run_fd: int) -> None:
    check_parent(final)
    c.require(
        identity(os.fstat(parent_fd)) == identity(final.parent.lstat()),
        "PUBLICATION_ANCHOR_CHANGED",
    )
    info = final.lstat()
    c.require(
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid()
        and identity(info) == identity(os.fstat(run_fd)),
        "FINAL_PUBLICATION_OWNERSHIP_MISMATCH",
    )


def read_private(path: Path, *, limit: int = 64 * 1024 * 1024) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        c.require(
            stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.geteuid()
            and info.st_nlink == 1
            and info.st_size <= limit,
            "PUBLICATION_RECORD_TOPOLOGY_INVALID",
        )
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(limit + 1)
        c.require(
            len(data) <= limit and len(data) == info.st_size,
            "PUBLICATION_RECORD_SIZE_CHANGED",
        )
        c.require(identity(info) == identity(path.lstat()), "PUBLICATION_FILE_CHANGED")
        return data
    finally:
        os.close(fd)


def inventory(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    files = [item for relation in manifest["relations"] for item in relation["files"]]
    if manifest["kind"] == PUBLIC:
        files.extend(manifest["reference_index"]["files"])
    else:
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


def inventory_hash(items: list[dict[str, Any]]) -> str:
    # One file-inventory entry at a time, never relation rows or payload bytes.
    digest = hashlib.sha256(b"[")
    for ordinal, item in enumerate(items):
        if ordinal:
            digest.update(b",")
        digest.update(canonical(item)[:-1])
    digest.update(b"]\n")
    return digest.hexdigest()


def bindings(
    root: Path, manifest: Mapping[str, Any], manifest_sha: str
) -> dict[str, Any]:
    public = manifest["kind"] == PUBLIC
    c.require(
        manifest["kind"] in (PUBLIC, DEVELOPMENT), "PUBLICATION_NAMESPACE_INVALID"
    )
    result = {
        "namespace": manifest["kind"],
        "publication_key": root.name,
        "manifest_sha256": manifest_sha,
        "logical_sha256": manifest["logical_sha256"],
        "contract_sha256": c.contract_fingerprint().hex()
        if public
        else manifest["contract_sha256"],
        "profile_sha256": None if public else manifest["profile_sha256"],
        "schema_bundle_sha256": c.schema_bundle_fingerprint().hex()
        if public
        else manifest["schema_bundle_sha256"],
        "executable_sha": manifest["operational_provenance"]["execution_git_sha"],
        "stage08_input_sha256": None if public else manifest["stage08_binding_sha256"],
        "reference_pack_sha256": manifest["lock_sha256"]
        if public
        else manifest["reference_pack"]["manifest_sha256"],
        "inventory_sha256": inventory_hash(inventory(manifest)),
    }
    for key, value in result.items():
        if key in ("namespace", "publication_key") or (
            public and key in ("profile_sha256", "stage08_input_sha256")
        ):
            continue
        c.require(
            isinstance(value, str)
            and bool(
                re.fullmatch(
                    "[0-9a-f]{40}" if key == "executable_sha" else "[0-9a-f]{64}", value
                )
            ),
            "PUBLICATION_IDENTITY_SYNTAX_INVALID",
        )
    return result


def registration(binding: Mapping[str, Any]) -> dict[str, Any]:
    body = {"protocol": PROTOCOL, "bindings": dict(binding)}
    return {
        **body,
        "commit_record_id": hashlib.sha256(
            b"SAFE:publication-commit:v2\0" + canonical(body)
        ).hexdigest(),
    }


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
    io.topology(root)
    raw = read_private(root / io.MANIFEST_NAME)
    c.require(
        hashlib.sha256(raw).hexdigest() == expected_manifest, "MANIFEST_HASH_MISMATCH"
    )
    manifest = json.loads(
        raw,
        object_pairs_hook=c._unique_pairs,
        parse_float=c._no_float,
        parse_constant=c._no_float,
    )
    c.require(isinstance(manifest, dict), "JSON_OBJECT_REQUIRED")
    items = inventory(manifest)
    io.topology(root, [*terminal_files(state), *(item["path"] for item in items)])
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


def create_seal(root: Path, run_fd: int) -> None:
    # Exact measured primitive. No write interval: intended content is empty.
    fd = os.open(
        SEAL, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=run_fd
    )
    os.close(fd)


def fault(phase: str, root: Path) -> None:
    """Fixed synthetic fault seam; never configured by CLI/environment."""


def finish(
    final: Path,
    digest: str,
    validate: io.Validate,
    parent_fd: int,
    run_fd: int,
    disposition: str,
) -> io.PublicationResult:
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
    result = io.PublicationResult(
        final,
        digest,
        manifest,
        disposition,
        record["commit_record_id"],
        hashlib.sha256(canonical(record)).hexdigest(),
    )
    return result


def last_check(
    result: io.PublicationResult, owned: tuple[tuple[int, int], tuple[int, int]]
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
    validate: io.Validate,
    *,
    _owned: tuple[tuple[int, int], tuple[int, int]] | None = None,
    _disposition: str = "ADOPT_EXISTING_EXACT_COMMITTED",
) -> io.PublicationResult:
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
        raise c.Stage09Error("FAIL_CLOSED_CONFLICT_OR_INCOMPLETE_RESERVATION") from None


class _ReservationExists(Exception):
    """Internal routing only; carries no artifact values."""


def publish(
    final: Path,
    build: io.Build,
    validate: io.Validate,
    *,
    expected_manifest: str | None = None,
) -> io.PublicationResult:
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
                raise c.Stage09Error(
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
                io.fsync_tree(final)
                validate(final, digest, False)
                record = registration(bindings(final, manifest, digest))
                io.write_exclusive(final / io.SUCCESS_NAME, canonical(record))
                fault("prepared_record", final)
                ownership(final, parent_fd, run_fd)
                os.unlink(PROGRESS, dir_fd=run_fd)
                io.fsync_tree(final)
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
                raise c.Stage09Error(
                    "FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION"
                ) from None
        if not reserved:
            raise c.Stage09Error("FAIL_CLOSED_RESERVATION_OUTCOME_UNKNOWN") from None
        raise c.Stage09Error("FAIL_CLOSED_UNCOMMITTED_ATTEMPT_PRESERVED") from None


def preflight(root: Path) -> None:
    """Small compute-node-only caller preflight, fixed synthetic bytes only."""
    target = root / "synthetic_exclusive_reservation"
    target.mkdir(mode=0o700)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        pass
    else:
        raise c.Stage09Error("SYNTHETIC_RESERVATION_COLLISION_FAILED")
    sentinel = b"synthetic filesystem preflight\n"
    io.write_exclusive(target / "sentinel", sentinel)
    fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        create_seal(target, fd)
        try:
            create_seal(target, fd)
        except FileExistsError:
            pass
        else:
            raise c.Stage09Error("SYNTHETIC_COMMIT_COLLISION_FAILED")
    finally:
        os.close(fd)
    for path in (target / "sentinel", target / SEAL):
        try:
            io.write_exclusive(path, b"must not overwrite")
        except FileExistsError:
            pass
        else:
            raise c.Stage09Error("SYNTHETIC_EXCLUSIVE_COLLISION_FAILED")
    c.require(
        read_private(target / "sentinel") == sentinel
        and read_private(target / SEAL, limit=0) == b"",
        "SYNTHETIC_CONTENT_CHANGED",
    )
    io.topology(target, ["sentinel", SEAL])
    io.fsync_tree(target)
    io.fsync_directory(root)

"""Executable DESIGN model, not an installed publication path or materializer.

Only the fixed invented fixture below can validate. No protected-data,
reference, Stage 8, networking or SLURM dependency. Production integration is
explicitly deferred until owner review of STAGE09_PUBLICATION_PROTOCOL_REVISION.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

PROTOCOL = "exclusive_run_commit_seal_v2_candidate"
MANIFEST = "stage09_reference_manifest.json"
RECORD = "_SUCCESS.json"
SEAL = "_COMMITTED"
PAYLOAD = b"invented publication fixture; no address data\n"
Hook = Callable[[str, Path], None]


class Closed(RuntimeError):
    """A fixed operational code; never a claim that a commit cannot exist."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise Closed(code)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class Binding:
    publication_key: str
    manifest_sha256: str
    logical_sha256: str
    contract_sha256: str
    profile_sha256: str | None
    schema_bundle_sha256: str
    executable_sha: str
    stage08_input_sha256: str | None
    reference_pack_sha256: str
    inventory_sha256: str
    namespace: str = "STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE"

    def fields(self) -> dict[str, str | None]:
        return dict(vars(self))


@dataclass(frozen=True)
class Fixture:
    binding: Binding
    manifest: bytes


@dataclass(frozen=True)
class Outcome:
    disposition: str
    binding: Binding
    commit_record_id: str


def fixture(
    key: str = "synthetic-run", edition: str = "one", *, public: bool = False
) -> Fixture:
    inventory = [
        {"path": "synthetic.txt", "bytes": len(PAYLOAD), "sha256": sha(PAYLOAD)}
    ]
    fields = {
        k: sha((k + edition).encode())
        for k in (
            "logical_sha256",
            "contract_sha256",
            "profile_sha256",
            "schema_bundle_sha256",
            "stage08_input_sha256",
            "reference_pack_sha256",
        )
    }
    binding = Binding(
        key,
        "0" * 64,
        **fields,
        executable_sha=sha(edition.encode())[:40],
        inventory_sha256=sha(canonical(inventory)),
    )
    if public:
        binding = replace(
            binding,
            namespace="STAGE09_PUBLIC_REFERENCE_PACK",
            stage08_input_sha256=None,
            profile_sha256=None,
        )
    manifest = canonical(
        {
            "kind": "SYNTHETIC_ONLY",
            "bindings": {
                k: v for k, v in binding.fields().items() if k != "manifest_sha256"
            },
            "inventory": inventory,
        }
    )
    return Fixture(replace(binding, manifest_sha256=sha(manifest)), manifest)


def record(binding: Binding) -> dict[str, object]:
    body = {"protocol": PROTOCOL, "bindings": binding.fields()}
    return {
        **body,
        "commit_record_id": sha(b"SAFE:publication-commit:v2\0" + canonical(body)),
    }


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def exclusive_file(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        position = 0
        while position < len(payload):
            count = os.write(fd, payload[position:])
            require(count > 0, "SHORT_WRITE")
            position += count
        os.fsync(fd)
    finally:
        os.close(fd)


def create_seal(path: Path) -> None:
    # The intended final content is already complete at exclusive creation.
    # There is deliberately no write, truncate, rename, link or chmod here.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)


def read_file(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(
            stat.S_ISREG(info.st_mode)
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.geteuid()
            and info.st_nlink == 1
            and info.st_size < 65536,
            "FILE_TOPOLOGY",
        )
        blocks = []
        total = 0
        while block := os.read(fd, 8192):
            total += len(block)
            require(total < 65536, "MODEL_SIZE_LIMIT")
            blocks.append(block)
        return b"".join(blocks)
    finally:
        os.close(fd)


def checked_parent(parent: Path, binding: Binding) -> Path:
    require(parent.is_absolute(), "ABSOLUTE_ANCHOR_REQUIRED")
    # The caller supplies the canonical approved anchor (e.g. resolved /work
    # mount alias). No untrusted component beneath it is resolved via symlink.
    for part in reversed((parent, *parent.parents)):
        require(stat.S_ISDIR(part.lstat().st_mode), "ANCESTOR_TYPE")
    require(stat.S_IMODE(parent.lstat().st_mode) == 0o700, "PARENT_MODE")
    require(parent.lstat().st_uid == os.geteuid(), "PARENT_OWNER")
    require(
        bool(
            re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,119}", binding.publication_key)
        ),
        "PUBLICATION_KEY",
    )
    require(
        binding.namespace
        in ("STAGE09_PUBLIC_REFERENCE_PACK", "STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE"),
        "NAMESPACE",
    )
    public = binding.namespace == "STAGE09_PUBLIC_REFERENCE_PACK"
    for key, value in binding.fields().items():
        if key in ("stage08_input_sha256", "profile_sha256") and public:
            require(value is None, "PUBLIC_NOT_APPLICABLE")
        elif key not in ("publication_key", "namespace"):
            require(
                isinstance(value, str)
                and bool(
                    re.fullmatch(
                        "[0-9a-f]{40}" if key == "executable_sha" else "[0-9a-f]{64}",
                        value,
                    )
                ),
                "IDENTITY_SYNTAX",
            )
    return parent / binding.publication_key


def identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    require(
        stat.S_ISDIR(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o700
        and info.st_uid == os.geteuid(),
        "ROOT_TOPOLOGY",
    )
    return info.st_dev, info.st_ino


def validate(parent: Path, binding: Binding, *, committed: bool) -> None:
    root = checked_parent(parent, binding)
    owned = identity(root)
    expected = {MANIFEST, RECORD, "synthetic.txt"} | ({SEAL} if committed else set())
    require({p.name for p in root.iterdir()} == expected, "EXACT_INVENTORY")
    require(
        read_file(root / RECORD) == canonical(record(binding)), "COMMIT_RECORD_BINDING"
    )
    raw = read_file(root / MANIFEST)
    require(sha(raw) == binding.manifest_sha256, "MANIFEST_BINDING")
    manifest = json.loads(raw)
    require(manifest["kind"] == "SYNTHETIC_ONLY", "SYNTHETIC_ONLY")
    require(
        manifest["bindings"]
        == {k: v for k, v in binding.fields().items() if k != "manifest_sha256"},
        "SEMANTIC_BINDING",
    )
    require(
        sha(canonical(manifest["inventory"])) == binding.inventory_sha256,
        "INVENTORY_BINDING",
    )
    require(
        manifest["inventory"]
        == [{"path": "synthetic.txt", "bytes": len(PAYLOAD), "sha256": sha(PAYLOAD)}],
        "SYNTHETIC_INVENTORY",
    )
    require(read_file(root / "synthetic.txt") == PAYLOAD, "PAYLOAD_HASH")
    if committed:
        require(read_file(root / SEAL) == b"", "SEAL_NOT_EMPTY")
    require(identity(root) == owned, "READ_OWNERSHIP_CHANGED")


def no_fault(phase: str, root: Path) -> None:
    pass


def finish(
    parent: Path,
    binding: Binding,
    disposition: str,
    owned: tuple[int, int] | None = None,
    hook: Hook = no_fault,
) -> Outcome:
    root = checked_parent(parent, binding)
    hook("reopen", root)
    validate(parent, binding, committed=True)
    # Durability acknowledgment is distinct from atomic namespace visibility.
    fd = os.open(root / SEAL, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    sync_directory(root)
    sync_directory(parent)
    result = Outcome(disposition, binding, str(record(binding)["commit_record_id"]))
    hook("last_check", root)
    validate(parent, binding, committed=True)
    require(owned is None or identity(root) == owned, "WRITE_OWNERSHIP_CHANGED")
    return result


def adopt(parent: Path, binding: Binding) -> Outcome:
    """No build/mutation/repair; external expected identity is mandatory."""
    try:
        return finish(parent, binding, "ADOPT")
    except Exception:
        raise Closed("FAIL_CLOSED_EXISTING_STATE_UNVERIFIED") from None


def publish(parent: Path, sample: Fixture, hook: Hook = no_fault) -> Outcome:
    """Test-only state machine. An uncatchable process death leaves its state.

    Exception reconciliation is bounded to one full attempt, never a retry loop.
    No path is removed/demoted after a seal might exist.
    """
    binding = sample.binding
    root = checked_parent(parent, binding)
    try:
        root.mkdir(mode=0o700)  # Atomic reservation, NOT exists()+mkdir(exist_ok).
    except FileExistsError:
        return adopt(parent, binding)
    except OSError:
        raise Closed("FAIL_CLOSED_RESERVATION_OUTCOME_UNKNOWN") from None
    owned = identity(root)
    commit_attempted = False
    try:
        sync_directory(parent)
        hook("reserved", root)
        require(identity(root) == owned, "WRITE_OWNERSHIP_CHANGED")
        exclusive_file(root / "_IN_PROGRESS", b"in_progress\n")
        exclusive_file(root / "synthetic.txt", PAYLOAD)
        hook("data", root)
        exclusive_file(root / MANIFEST, sample.manifest)
        hook("manifest", root)
        # Private scientific validation precedes even the preparation record.
        require(read_file(root / "synthetic.txt") == PAYLOAD, "PAYLOAD_HASH")
        require(
            sha(read_file(root / MANIFEST)) == binding.manifest_sha256,
            "MANIFEST_BINDING",
        )
        exclusive_file(root / RECORD, canonical(record(binding)))
        hook("prepared_record", root)
        require(identity(root) == owned, "WRITE_OWNERSHIP_CHANGED")
        (root / "_IN_PROGRESS").unlink()
        sync_directory(root)
        sync_directory(parent)
        validate(parent, binding, committed=False)
        hook("before_commit", root)
        # Recheck after the fault seam; fail on any pre-existing seal/extra item.
        validate(parent, binding, committed=False)
        require(identity(root) == owned, "WRITE_OWNERSHIP_CHANGED")
        commit_attempted = True
        create_seal(root / SEAL)
        hook("after_commit", root)
        return finish(parent, binding, "PASS", owned, hook)
    except Exception:
        if commit_attempted:
            try:
                require(identity(root) == owned, "WRITE_OWNERSHIP_CHANGED")
                return finish(parent, binding, "ADOPT", owned, hook)
            except Exception:
                raise Closed(
                    "FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION"
                ) from None
        raise Closed("FAIL_CLOSED_UNCOMMITTED_ATTEMPT_PRESERVED") from None


def present(outcome: Outcome, emit: Callable[[Outcome], None]) -> int:
    try:
        emit(outcome)
    except BaseException:
        pass
    return 0

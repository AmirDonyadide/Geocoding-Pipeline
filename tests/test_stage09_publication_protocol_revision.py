"""Owner-review model tests only: fixed invented bytes, no pipeline inputs."""

from __future__ import annotations

import errno
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Event

import pytest

import stage09_publication_protocol_model as model


@pytest.fixture
def anchor(tmp_path):
    return tmp_path.resolve()


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def test_fresh_publication_reopen_and_repeated_exact_adoption(anchor):
    sample = model.fixture()
    first = model.publish(anchor, sample)
    before = snapshot(anchor)
    assert first.disposition == "PASS"
    assert model.publish(anchor, sample).disposition == "ADOPT"
    assert (
        model.adopt(anchor, sample.binding).commit_record_id == first.commit_record_id
    )
    assert snapshot(anchor) == before


def test_public_pack_uses_same_seal_without_inventing_stage08_or_profile(anchor):
    sample = model.fixture(public=True)
    assert sample.binding.stage08_input_sha256 is None
    assert sample.binding.profile_sha256 is None
    model.publish(anchor, sample)
    assert model.adopt(anchor, sample.binding).disposition == "ADOPT"
    with pytest.raises(model.Closed):
        model.adopt(
            anchor,
            replace(sample.binding, namespace="STAGE09_DEVELOPMENT_REFERENCE_EVIDENCE"),
        )


def test_namespace_is_part_of_identity():
    sample = model.fixture()
    other = replace(sample.binding, namespace="STAGE09_PUBLIC_REFERENCE_PACK")
    assert (
        model.record(sample.binding)["commit_record_id"]
        != model.record(other)["commit_record_id"]
    )


@pytest.mark.parametrize(
    "field",
    [
        "manifest_sha256",
        "logical_sha256",
        "contract_sha256",
        "profile_sha256",
        "schema_bundle_sha256",
        "executable_sha",
        "stage08_input_sha256",
        "reference_pack_sha256",
        "inventory_sha256",
    ],
)
def test_every_external_binding_mismatch_fails_without_mutation(anchor, field):
    sample = model.fixture()
    model.publish(anchor, sample)
    before = snapshot(anchor)
    wrong = replace(
        sample.binding, **{field: "f" * (40 if field == "executable_sha" else 64)}
    )
    with pytest.raises(model.Closed, match="EXISTING_STATE_UNVERIFIED"):
        model.adopt(anchor, wrong)
    assert snapshot(anchor) == before


def test_conflicting_publisher_does_not_replace_accepted_artifact(anchor):
    model.publish(anchor, model.fixture())
    before = snapshot(anchor)
    with pytest.raises(model.Closed):
        model.publish(anchor, model.fixture(edition="conflicting"))
    assert snapshot(anchor) == before


@pytest.mark.parametrize(
    "kind", ["empty_dir", "incomplete", "file", "symlink", "dangling"]
)
def test_existing_target_never_claimed_or_overwritten(anchor, kind):
    sample = model.fixture()
    root = anchor / sample.binding.publication_key
    sentinel = anchor / "unrelated.txt"
    sentinel.write_bytes(b"invented unrelated sentinel")
    if kind == "empty_dir":
        root.mkdir(mode=0o700)
    elif kind == "incomplete":
        root.mkdir(mode=0o700)
        model.exclusive_file(root / "_IN_PROGRESS", b"in_progress\n")
    elif kind == "file":
        root.write_bytes(b"invented foreign file")
    else:
        root.symlink_to(sentinel if kind == "symlink" else anchor / "missing")
    before = snapshot(anchor)
    with pytest.raises(model.Closed):
        model.publish(anchor, sample)
    assert snapshot(anchor) == before
    if kind in ("symlink", "dangling"):
        assert root.is_symlink()


@pytest.mark.parametrize(
    "phase", ["reserved", "data", "manifest", "prepared_record", "before_commit"]
)
def test_precommit_exception_preserves_unaccepted_attempt(anchor, phase):
    sample = model.fixture()

    def fault(current, root):
        if current == phase:
            raise OSError("invented private error detail")

    with pytest.raises(model.Closed, match="UNCOMMITTED") as error:
        model.publish(anchor, sample, fault)
    assert "private error detail" not in str(error.value)
    assert not (anchor / sample.binding.publication_key / model.SEAL).exists()
    before = snapshot(anchor)
    with pytest.raises(model.Closed):
        model.publish(anchor, sample)
    assert snapshot(anchor) == before


class SimulatedProcessDeath(BaseException):
    pass


@pytest.mark.parametrize(
    "phase,accepted", [("before_commit", False), ("after_commit", True)]
)
def test_uncatchable_interruption_reconciles_from_bytes(anchor, phase, accepted):
    sample = model.fixture()

    def die(current, root):
        if current == phase:
            raise SimulatedProcessDeath()

    with pytest.raises(SimulatedProcessDeath):
        model.publish(anchor, sample, die)
    if accepted:
        assert model.adopt(anchor, sample.binding).disposition == "ADOPT"
    else:
        with pytest.raises(model.Closed):
            model.adopt(anchor, sample.binding)


@pytest.mark.parametrize("effect", [False, True])
def test_commit_error_effect_is_reconciled_not_guessed(anchor, monkeypatch, effect):
    original = model.create_seal

    def uncertain(path):
        if effect:
            original(path)
        raise OSError(errno.EIO, "invented uncertain result")

    monkeypatch.setattr(model, "create_seal", uncertain)
    sample = model.fixture()
    if effect:
        assert model.publish(anchor, sample).disposition == "ADOPT"
    else:
        with pytest.raises(model.Closed, match="REQUIRES_RECONCILIATION"):
            model.publish(anchor, sample)
        assert not (anchor / sample.binding.publication_key / model.SEAL).exists()


def test_false_syscall_success_cannot_publish(anchor, monkeypatch):
    monkeypatch.setattr(model, "create_seal", lambda path: None)
    with pytest.raises(model.Closed, match="REQUIRES_RECONCILIATION"):
        model.publish(anchor, model.fixture())


def test_error_after_commit_is_adopted_without_demotion(anchor):
    def fault(phase, root):
        if phase == "after_commit":
            raise RuntimeError("invented presentation-like interruption")

    sample = model.fixture()
    assert model.publish(anchor, sample, fault).disposition == "ADOPT"
    assert model.adopt(anchor, sample.binding).disposition == "ADOPT"


def test_postcommit_persistent_fsync_error_is_explicit_unknown_not_false_success(
    anchor, monkeypatch
):
    original = model.sync_directory

    def fail_after_seal(path):
        if (path / model.SEAL).exists():
            raise OSError(errno.EIO, "synthetic fsync error")
        original(path)

    monkeypatch.setattr(model, "sync_directory", fail_after_seal)
    sample = model.fixture()
    with pytest.raises(model.Closed, match="COMMIT_OUTCOME_REQUIRES_RECONCILIATION"):
        model.publish(anchor, sample)
    assert (anchor / sample.binding.publication_key / model.SEAL).is_file()
    before = snapshot(anchor)
    monkeypatch.setattr(model, "sync_directory", original)
    assert model.adopt(anchor, sample.binding).disposition == "ADOPT"
    assert snapshot(anchor) == before


@pytest.mark.parametrize(
    "name,content",
    [
        (model.RECORD, b'{"partial":'),
        (model.RECORD, b"{}\n"),
        (model.SEAL, b"not empty"),
        (model.MANIFEST, b"{}\n"),
        ("synthetic.txt", b"invented corrupted payload"),
    ],
)
def test_corrupt_record_seal_manifest_or_payload_cannot_be_adopted(
    anchor, name, content
):
    sample = model.fixture()
    model.publish(anchor, sample)
    (anchor / sample.binding.publication_key / name).write_bytes(content)
    before = snapshot(anchor)
    with pytest.raises(model.Closed):
        model.adopt(anchor, sample.binding)
    assert snapshot(anchor) == before


@pytest.mark.parametrize("kind", ["file", "directory", "symlink", "dangling"])
def test_exclusive_seal_collision_does_not_clobber(anchor, kind):
    seal = anchor / model.SEAL
    target = anchor / "invented.txt"
    target.write_bytes(b"invented target")
    if kind == "file":
        seal.write_bytes(b"invented existing seal")
    elif kind == "directory":
        seal.mkdir()
    else:
        seal.symlink_to(target if kind == "symlink" else anchor / "absent")
    before = snapshot(anchor)
    with pytest.raises(FileExistsError):
        model.create_seal(seal)
    assert snapshot(anchor) == before


def test_seal_injected_before_commit_is_not_silently_overwritten(anchor):
    def fault(phase, root):
        if phase == "before_commit":
            model.exclusive_file(root / model.SEAL, b"invented foreign seal")

    sample = model.fixture()
    with pytest.raises(model.Closed):
        model.publish(anchor, sample, fault)
    assert (
        anchor / sample.binding.publication_key / model.SEAL
    ).read_bytes() == b"invented foreign seal"


def test_concurrent_reservation_has_one_writer_and_loser_does_not_touch_attempt(anchor):
    reserved, release = Event(), Event()
    sample = model.fixture()

    def pause(phase, root):
        if phase == "reserved":
            reserved.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(model.publish, anchor, sample, pause)
        assert reserved.wait(5)
        try:
            second = workers.submit(model.publish, anchor, sample)
            with pytest.raises(model.Closed):
                second.result(timeout=5)
        finally:
            release.set()
        assert first.result(timeout=5).disposition == "PASS"
    assert model.publish(anchor, sample).disposition == "ADOPT"


def test_concurrent_seal_creators_have_exactly_one_winner(anchor):
    barrier = Barrier(8)

    def claim(_):
        barrier.wait(timeout=5)
        try:
            model.create_seal(anchor / model.SEAL)
            return "PASS"
        except FileExistsError:
            return "COLLISION"

    with ThreadPoolExecutor(max_workers=8) as workers:
        outcomes = list(workers.map(claim, range(8)))
    assert outcomes.count("PASS") == 1
    assert outcomes.count("COLLISION") == 7
    assert (anchor / model.SEAL).read_bytes() == b""


def test_private_modes_and_no_hardlinks(anchor):
    sample = model.fixture()
    model.publish(anchor, sample)
    root = anchor / sample.binding.publication_key
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(
        p.stat().st_mode & 0o777 == 0o600 and p.stat().st_nlink == 1
        for p in root.iterdir()
    )
    (root / model.RECORD).chmod(0o644)
    with pytest.raises(model.Closed):
        model.adopt(anchor, sample.binding)


@pytest.mark.parametrize(
    "name", [model.RECORD, model.MANIFEST, model.SEAL, "synthetic.txt"]
)
def test_symlink_file_never_opened(anchor, monkeypatch, name):
    sample = model.fixture()
    model.publish(anchor, sample)
    root = anchor / sample.binding.publication_key
    (root / name).unlink()
    (root / name).symlink_to(anchor / "never-read")
    with pytest.raises(model.Closed):
        model.adopt(anchor, sample.binding)
    assert not (anchor / "never-read").exists()


def test_parent_symlink_and_unsafe_key_rejected(anchor):
    link = anchor / "link"
    link.symlink_to(anchor, target_is_directory=True)
    with pytest.raises(model.Closed, match="ANCESTOR"):
        model.publish(link, model.fixture())
    with pytest.raises(model.Closed, match="PUBLICATION_KEY"):
        model.publish(anchor, model.fixture("../escape"))


def test_existing_hardlinked_record_is_rejected(anchor):
    sample = model.fixture()
    model.publish(anchor, sample)
    os.link(
        anchor / sample.binding.publication_key / model.RECORD, anchor / "foreign-link"
    )
    with pytest.raises(model.Closed):
        model.adopt(anchor, sample.binding)


def test_persistent_adoption_does_not_require_historical_inode(anchor):
    sample = model.fixture()
    model.publish(anchor, sample)
    other = anchor / "copied-anchor"
    other.mkdir(mode=0o700)
    root = anchor / sample.binding.publication_key
    copied = other / sample.binding.publication_key
    shutil.copytree(root, copied)
    assert model.identity(root) != model.identity(copied)
    assert model.adopt(other, sample.binding).disposition == "ADOPT"


def test_incomplete_record_never_readable_as_success(anchor):
    sample = model.fixture()
    observed = []

    def observe(phase, root):
        if phase in ("manifest", "prepared_record", "before_commit"):
            with pytest.raises(model.Closed):
                model.adopt(anchor, sample.binding)
            observed.append(phase)

    model.publish(anchor, sample, observe)
    assert observed == ["manifest", "prepared_record", "before_commit"]


def test_foreign_equal_tree_after_commit_is_not_owned_by_writer(anchor):
    sample = model.fixture()
    moved = anchor / "preserved-original"

    def swap(phase, root):
        if phase == "after_commit":
            root.rename(moved)  # Synthetic fault injection only, never protocol.
            shutil.copytree(moved, root)

    with pytest.raises(model.Closed, match="REQUIRES_RECONCILIATION"):
        model.publish(anchor, sample, swap)
    assert model.adopt(anchor, sample.binding).disposition == "ADOPT"
    assert (moved / model.SEAL).is_file()


def test_last_check_cannot_be_skipped_and_presentation_cannot_demote(anchor):
    def fault(phase, root):
        if phase == "last_check":
            raise OSError("synthetic validation unavailable")

    sample = model.fixture()
    with pytest.raises(model.Closed):
        model.publish(anchor, sample, fault)
    outcome = model.adopt(anchor, sample.binding)
    before = snapshot(anchor)
    assert (
        model.present(outcome, lambda _: (_ for _ in ()).throw(BrokenPipeError())) == 0
    )
    assert snapshot(anchor) == before


def test_model_has_no_pipeline_data_or_service_dependency():
    import ast

    tree = ast.parse(Path(model.__file__).read_text())
    imports = {
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports |= {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert imports <= {
        "__future__",
        "hashlib",
        "json",
        "os",
        "re",
        "stat",
        "dataclasses",
        "pathlib",
        "typing",
    }


@pytest.mark.parametrize("effect", [False, True])
def test_process_death_during_commit_has_no_partial_seal(anchor, monkeypatch, effect):
    original = model.create_seal

    def die(path):
        if effect:
            original(path)
        raise SimulatedProcessDeath()

    monkeypatch.setattr(model, "create_seal", die)
    sample = model.fixture()
    with pytest.raises(SimulatedProcessDeath):
        model.publish(anchor, sample)
    if effect:
        assert model.adopt(anchor, sample.binding).disposition == "ADOPT"
    else:
        with pytest.raises(model.Closed):
            model.adopt(anchor, sample.binding)


def test_precommit_sync_failure_cannot_create_seal(anchor, monkeypatch):
    def fail(path):
        raise OSError(errno.EIO, "invented sync failure")

    monkeypatch.setattr(model, "sync_directory", fail)
    sample = model.fixture()
    with pytest.raises(model.Closed, match="UNCOMMITTED"):
        model.publish(anchor, sample)
    assert not (anchor / sample.binding.publication_key / model.SEAL).exists()


def test_mkdir_error_after_effect_never_grants_construction_ownership(
    anchor, monkeypatch
):
    sample = model.fixture()
    root = anchor / sample.binding.publication_key
    original = Path.mkdir

    def uncertain(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == root:
            raise OSError(errno.EIO, "invented mkdir uncertainty")

    monkeypatch.setattr(Path, "mkdir", uncertain)
    with pytest.raises(model.Closed, match="RESERVATION_OUTCOME_UNKNOWN"):
        model.publish(anchor, sample)
    assert list(root.iterdir()) == []


def test_short_record_write_is_preserved_without_false_commit(anchor, monkeypatch):
    original = model.exclusive_file

    def partial(path, payload):
        if path.name == model.RECORD:
            original(path, payload[:10])
            raise OSError(errno.ENOSPC, "invented disk full")
        original(path, payload)

    monkeypatch.setattr(model, "exclusive_file", partial)
    sample = model.fixture()
    with pytest.raises(model.Closed):
        model.publish(anchor, sample)
    root = anchor / sample.binding.publication_key
    assert (root / model.RECORD).stat().st_size == 10
    assert not (root / model.SEAL).exists()
    with pytest.raises(model.Closed):
        model.adopt(anchor, sample.binding)


def test_zero_progress_write_cannot_hang_or_succeed(anchor, monkeypatch):
    monkeypatch.setattr(model.os, "write", lambda fd, data: 0)
    with pytest.raises(model.Closed, match="UNCOMMITTED"):
        model.publish(anchor, model.fixture())


def test_precommit_permission_mutation_prevents_seal(anchor):
    def fault(phase, root):
        if phase == "before_commit":
            (root / model.RECORD).chmod(0o644)

    sample = model.fixture()
    with pytest.raises(model.Closed):
        model.publish(anchor, sample, fault)
    assert not (anchor / sample.binding.publication_key / model.SEAL).exists()


def test_publication_key_and_record_id_are_not_order_dependent():
    sample = model.fixture()
    body = {"protocol": model.PROTOCOL, "bindings": sample.binding.fields()}
    reversed_body = {
        "bindings": dict(reversed(list(sample.binding.fields().items()))),
        "protocol": model.PROTOCOL,
    }
    assert model.canonical(body) == model.canonical(reversed_body)
    changed = replace(sample.binding, publication_key="different-run")
    assert (
        model.record(sample.binding)["commit_record_id"]
        != model.record(changed)["commit_record_id"]
    )

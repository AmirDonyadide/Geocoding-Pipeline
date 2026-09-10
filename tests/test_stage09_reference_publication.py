"""Integrated reservation/seal fault tests using invented bytes, never inputs."""

from __future__ import annotations

import copy
import errno
import hashlib
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as io
from safe_geocoding_pipeline.preprocessing.stages import (
    s09_reference_publication as pub,
)

PAYLOAD = b"synthetic public fixture\n"


def build(root):
    io.write_exclusive(root / "synthetic.txt", PAYLOAD)
    return {
        "kind": pub.DEVELOPMENT,
        "synthetic_only": True,
        "development_metrics": {"total_stage06_candidates": 1, "evidence_rows": 1},
        "logical_sha256": "0" * 64,
        "contract_sha256": "1" * 64,
        "profile_sha256": "2" * 64,
        "schema_bundle_sha256": "3" * 64,
        "stage08_binding_sha256": "4" * 64,
        "reference_pack": {"manifest_sha256": "5" * 64},
        "operational_provenance": {"execution_git_sha": "6" * 40},
        "metadata_inventory": [],
        "relations": [
            {
                "files": [
                    {
                        "relative_path": "synthetic.txt",
                        "bytes": len(PAYLOAD),
                        "sha256": hashlib.sha256(PAYLOAD).hexdigest(),
                    }
                ]
            }
        ],
    }


def validate(root, digest, state):
    manifest = io.validate_terminal(root, digest, state)
    c.require(manifest["synthetic_only"] is True, "SYNTHETIC_ONLY")
    c.require(
        pub.read_private(root / "synthetic.txt") == PAYLOAD, "CONTENT_HASH_MISMATCH"
    )
    return manifest


def snapshot(root):
    return {
        p.relative_to(root).as_posix(): (p.lstat().st_mode, p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def test_success_reopens_and_exact_existing_success_is_adopted(tmp_path):
    final = tmp_path / "published"
    first = io.publish(final, build, validate)
    assert first.disposition == "PASS"
    assert validate(final, first.manifest_sha256, True) == first.manifest
    before = snapshot(final)
    second = io.publish(
        final,
        lambda root: pytest.fail("adoption rebuilt"),
        validate,
        expected_manifest=first.manifest_sha256,
    )
    assert second.disposition == "ADOPT_EXISTING_EXACT_COMMITTED"
    assert second.commit_record_id == first.commit_record_id
    assert snapshot(final) == before
    with pytest.raises(c.Stage09Error, match="UNPINNED"):
        io.publish(final, build, validate)
    assert snapshot(final) == before


@pytest.mark.parametrize(
    "phase", ["reserved", "data", "manifest", "prepared_record", "before_commit"]
)
def test_precommit_failure_preserves_unaccepted_attempt(tmp_path, monkeypatch, phase):
    final = tmp_path / "published"

    def injected(actual, root):
        if actual == phase:
            raise ValueError("private sentinel must not escape")

    monkeypatch.setattr(pub, "fault", injected)
    with pytest.raises(c.Stage09Error, match="UNCOMMITTED") as error:
        io.publish(final, build, validate)
    assert "private sentinel" not in str(error.value)
    assert final.is_dir() and not (final / pub.SEAL).exists()
    before = snapshot(final)
    monkeypatch.setattr(pub, "fault", lambda *args: None)
    with pytest.raises(c.Stage09Error):
        io.publish(final, build, validate, expected_manifest="a" * 64)
    assert snapshot(final) == before


@pytest.mark.parametrize("phase", ["reserved", "before_commit", "after_commit"])
def test_uncatchable_death_leaves_exact_persistent_state(tmp_path, monkeypatch, phase):
    class Death(BaseException):
        pass

    final = tmp_path / "published"

    def injected(actual, root):
        if actual == phase:
            raise Death()

    monkeypatch.setattr(pub, "fault", injected)
    with pytest.raises(Death):
        io.publish(final, build, validate)
    assert (final / pub.SEAL).exists() == (phase == "after_commit")
    monkeypatch.setattr(pub, "fault", lambda *args: None)
    if phase == "after_commit":
        expected = c.sha256_file(final / io.MANIFEST_NAME)
        assert (
            pub.adopt(final, expected, validate).disposition
            == "ADOPT_EXISTING_EXACT_COMMITTED"
        )


@pytest.mark.parametrize("effect", [False, True, "false-success"])
def test_uncertain_seal_result_is_reconciled_once(tmp_path, monkeypatch, effect):
    real = pub.create_seal
    calls = []

    def uncertain(root, fd):
        calls.append(root)
        if effect is True:
            real(root, fd)
        if effect != "false-success":
            raise OSError(errno.EIO, "synthetic uncertain return")

    monkeypatch.setattr(pub, "create_seal", uncertain)
    final = tmp_path / "published"
    if effect is True:
        assert (
            io.publish(final, build, validate).disposition
            == "ADOPT_COMMITTED_AFTER_RECONCILIATION"
        )
    else:
        with pytest.raises(c.Stage09Error, match="OUTCOME_REQUIRES_RECONCILIATION"):
            io.publish(final, build, validate)
        assert not (final / pub.SEAL).exists()
    assert len(calls) == 1


@pytest.mark.parametrize("phase", ["after_commit", "reopen", "last_check"])
def test_transient_postcommit_error_adopts_without_demotion(
    tmp_path, monkeypatch, phase
):
    calls = []

    def once(actual, root):
        if actual == phase and not calls:
            calls.append(actual)
            raise OSError("synthetic one-shot")

    monkeypatch.setattr(pub, "fault", once)
    result = io.publish(tmp_path / "published", build, validate)
    assert result.disposition == "ADOPT_COMMITTED_AFTER_RECONCILIATION"
    assert pub.read_private(result.path / pub.SEAL, limit=0) == b""
    assert not (result.path / pub.PROGRESS).exists()


def test_persistent_postcommit_error_preserves_seal_for_later_adoption(
    tmp_path, monkeypatch
):
    def broken(actual, root):
        if actual == "reopen":
            raise OSError()

    monkeypatch.setattr(pub, "fault", broken)
    final = tmp_path / "published"
    with pytest.raises(c.Stage09Error, match="OUTCOME_REQUIRES_RECONCILIATION"):
        io.publish(final, build, validate)
    assert (final / pub.SEAL).exists()
    monkeypatch.setattr(pub, "fault", lambda *args: None)
    expected = c.sha256_file(final / io.MANIFEST_NAME)
    assert (
        pub.adopt(final, expected, validate).disposition
        == "ADOPT_EXISTING_EXACT_COMMITTED"
    )


@pytest.mark.parametrize(
    "slot",
    [
        "logical_sha256",
        "contract_sha256",
        "profile_sha256",
        "schema_bundle_sha256",
        "stage08_binding_sha256",
        "executable",
        "reference",
        "manifest",
    ],
)
def test_identity_mismatch_never_adopts(tmp_path, slot):
    result = io.publish(tmp_path / "published", build, validate)
    expected = result.manifest_sha256
    altered = copy.deepcopy(result.manifest)
    if slot == "executable":
        altered["operational_provenance"]["execution_git_sha"] = "a" * 40
    elif slot == "reference":
        altered["reference_pack"]["manifest_sha256"] = "a" * 64
    elif slot == "manifest":
        altered["unexpected"] = True
    else:
        altered[slot] = "a" * 64
    (result.path / io.MANIFEST_NAME).write_bytes(c.canonical_json(altered))
    before = snapshot(result.path)
    with pytest.raises(c.Stage09Error):
        pub.adopt(result.path, expected, validate)
    assert snapshot(result.path) == before


@pytest.mark.parametrize(
    "kind", ["empty", "progress", "prepared", "old", "file", "symlink"]
)
def test_existing_incomplete_or_foreign_reservation_never_taken_over(tmp_path, kind):
    final = tmp_path / "published"
    if kind == "file":
        io.write_exclusive(final, b"other owner")
    elif kind == "symlink":
        final.symlink_to(tmp_path / "absent")
    else:
        final.mkdir(mode=0o700)
        if kind == "progress":
            io.write_exclusive(final / pub.PROGRESS, b"in_progress\n")
        elif kind == "prepared":
            io.write_exclusive(final / io.SUCCESS_NAME, b"{}\n")
        elif kind == "old":
            os.utime(final, (1, 1))
    with pytest.raises(c.Stage09Error):
        io.publish(
            final,
            lambda root: pytest.fail("stolen reservation"),
            validate,
            expected_manifest="a" * 64,
        )
    assert os.path.lexists(final)


@pytest.mark.parametrize(
    "slot", [io.SUCCESS_NAME, pub.SEAL, io.MANIFEST_NAME, "synthetic.txt"]
)
def test_corruption_and_symlink_slots_fail_closed(tmp_path, slot):
    result = io.publish(tmp_path / "published", build, validate)
    path = result.path / slot
    path.write_bytes(b"corrupt")
    with pytest.raises(c.Stage09Error):
        pub.adopt(result.path, result.manifest_sha256, validate)
    path.unlink()
    referent = tmp_path / "referent"
    io.write_exclusive(referent, b"do not touch")
    path.symlink_to(referent)
    with pytest.raises(c.Stage09Error):
        pub.adopt(result.path, result.manifest_sha256, validate)
    assert referent.read_bytes() == b"do not touch"


def test_preexisting_seal_is_never_overwritten(tmp_path, monkeypatch):
    def inject(phase, root):
        if phase == "before_commit":
            io.write_exclusive(root / pub.SEAL, b"foreign")

    monkeypatch.setattr(pub, "fault", inject)
    with pytest.raises(c.Stage09Error, match="UNCOMMITTED"):
        io.publish(tmp_path / "published", build, validate)
    assert (tmp_path / "published" / pub.SEAL).read_bytes() == b"foreign"


def test_concurrent_duplicate_publishers_do_not_write_into_reservation(tmp_path):
    final = tmp_path / "published"
    held, release = Event(), Event()

    def owner(root):
        held.set()
        assert release.wait(10)
        return build(root)

    with ThreadPoolExecutor(2) as pool:
        winner = pool.submit(io.publish, final, owner, validate)
        assert held.wait(10)
        try:
            with pytest.raises(c.Stage09Error):
                io.publish(final, lambda root: pytest.fail("loser built"), validate)
        finally:
            release.set()
        result = winner.result(timeout=10)
    assert result.disposition == "PASS"
    assert (
        pub.adopt(final, result.manifest_sha256, validate).manifest == result.manifest
    )


def test_concurrent_commit_creators_have_one_winner(tmp_path):
    barrier = Barrier(4)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def contender(_):
        barrier.wait(timeout=10)
        try:
            pub.create_seal(tmp_path, fd)
        except FileExistsError as error:
            return error.errno
        return 0

    try:
        with ThreadPoolExecutor(4) as pool:
            results = list(pool.map(contender, range(4)))
    finally:
        os.close(fd)
    assert results.count(0) == 1 and results.count(errno.EEXIST) == 3
    assert pub.read_private(tmp_path / pub.SEAL, limit=0) == b""


def test_no_persistent_inode_gate_and_key_cannot_change(tmp_path):
    result = io.publish(tmp_path / "published", build, validate)
    parent = tmp_path / "other-anchor"
    parent.mkdir(mode=0o700)
    clone = parent / "published"
    shutil.copytree(result.path, clone)
    assert io.directory_identity(clone) != io.directory_identity(result.path)
    assert (
        pub.adopt(clone, result.manifest_sha256, validate).manifest == result.manifest
    )
    renamed = parent / "different-key"
    shutil.copytree(clone, renamed)
    with pytest.raises(c.Stage09Error):
        pub.adopt(renamed, result.manifest_sha256, validate)


@pytest.mark.parametrize("target", ["parent", "run", "file", "hardlink"])
def test_private_topology_enforced(tmp_path, target):
    result = io.publish(tmp_path / "published", build, validate)
    if target == "hardlink":
        os.link(result.path / "synthetic.txt", tmp_path / "extra-link")
    else:
        path = {
            "parent": tmp_path,
            "run": result.path,
            "file": result.path / "synthetic.txt",
        }[target]
        path.chmod(0o755 if target != "file" else 0o644)
    with pytest.raises(c.Stage09Error):
        pub.adopt(result.path, result.manifest_sha256, validate)


def test_synthetic_preflight_has_no_rename_dependency(tmp_path, monkeypatch):
    monkeypatch.setattr(
        io, "_atomic_rename", lambda *args: pytest.fail("old primitive")
    )
    pub.preflight(tmp_path)
    result = io.publish(tmp_path / "published", build, validate)
    assert result.commit_record_id and result.registration_sha256


def test_inventory_hash_matches_canonical_and_rejects_escaping_paths(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir(mode=0o700)
    manifest = build(root)
    items = pub.inventory(manifest)
    assert pub.inventory_hash(items) == hashlib.sha256(pub.canonical(items)).hexdigest()
    manifest["relations"][0]["files"][0]["relative_path"] = "../escape"
    with pytest.raises(c.Stage09Error):
        pub.inventory(manifest)


@pytest.mark.parametrize("slot", [io.MANIFEST_NAME, io.SUCCESS_NAME])
def test_incomplete_metadata_write_is_not_committed(tmp_path, monkeypatch, slot):
    real = io.write_exclusive

    def partial(path, payload):
        if path.name == slot:
            real(path, payload[:4])
            raise OSError("invented partial write")
        real(path, payload)

    monkeypatch.setattr(io, "write_exclusive", partial)
    final = tmp_path / "published"
    with pytest.raises(c.Stage09Error, match="UNCOMMITTED"):
        io.publish(final, build, validate)
    assert not (final / pub.SEAL).exists()
    assert len((final / slot).read_bytes()) == 4


@pytest.mark.parametrize("state", [False, "prepared", True])
def test_scientific_validation_failure_cannot_be_overruled_by_markers(tmp_path, state):
    final = tmp_path / "published"

    def invalid(root, digest, observed):
        if observed is state or observed == state:
            raise c.Stage09Error("SYNTHETIC_SCIENTIFIC_FAILURE")
        return validate(root, digest, observed)

    with pytest.raises(c.Stage09Error):
        io.publish(final, build, invalid)
    assert (final / pub.SEAL).exists() == (state is True)


@pytest.mark.parametrize("after_effect", [False, True])
def test_uncertain_reservation_does_not_grant_ownership(
    tmp_path, monkeypatch, after_effect
):
    real = os.mkdir

    def uncertain(*args, **kwargs):
        if after_effect:
            real(*args, **kwargs)
        raise OSError(errno.EIO, "invented mkdir uncertainty")

    monkeypatch.setattr(os, "mkdir", uncertain)
    final = tmp_path / "published"
    with pytest.raises(c.Stage09Error, match="RESERVATION_OUTCOME_UNKNOWN"):
        io.publish(final, lambda root: pytest.fail("unproved ownership"), validate)
    assert final.exists() == after_effect
    assert not (final / pub.PROGRESS).exists()


@pytest.mark.parametrize("directory", ["run", "parent"])
def test_close_after_effect_failure_after_commit_reconciles(
    tmp_path, monkeypatch, directory
):
    real = os.close
    final = tmp_path / "published"
    calls = []

    def close(fd):
        info = os.fstat(fd)
        target = final if directory == "run" else tmp_path
        selected = target.exists() and pub.identity(info) == pub.identity(
            target.lstat()
        )
        real(fd)
        if selected and (final / pub.SEAL).exists() and not calls:
            calls.append(fd)
            raise OSError("invented close after effect")

    monkeypatch.setattr(os, "close", close)
    result = io.publish(final, build, validate)
    assert calls and result.disposition == "ADOPT_COMMITTED_AFTER_RECONCILIATION"
    assert validate(final, result.manifest_sha256, True)


@pytest.mark.parametrize("postcommit", [False, True])
def test_persistent_fsync_failure_is_not_false_success(
    tmp_path, monkeypatch, postcommit
):
    real = os.fsync
    final = tmp_path / "published"

    def sync(fd):
        if (final / pub.SEAL).exists() == postcommit:
            raise OSError("invented sync failure")
        real(fd)

    monkeypatch.setattr(os, "fsync", sync)
    with pytest.raises(c.Stage09Error):
        io.publish(final, build, validate)
    assert (final / pub.SEAL).exists() == postcommit


def test_final_ownership_swap_cannot_adopt_foreign_equal_content(tmp_path, monkeypatch):
    final = tmp_path / "published"
    moved = tmp_path / "retained-original"
    calls = []

    def swap(phase, root):
        if phase == "last_check" and not calls:
            calls.append(phase)
            # Deliberate fault injection only, never a publication primitive.
            root.rename(moved)
            shutil.copytree(moved, root)

    monkeypatch.setattr(pub, "fault", swap)
    with pytest.raises(c.Stage09Error, match="OUTCOME_REQUIRES_RECONCILIATION"):
        io.publish(final, build, validate)
    assert (moved / pub.SEAL).is_file() and (final / pub.SEAL).is_file()


def test_symlink_ancestor_is_not_resolved_by_publication(tmp_path):
    link = tmp_path / "alias"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(c.Stage09Error):
        io.publish(link / "published", build, validate)
    assert not (tmp_path / "published").exists()


def test_registration_bytes_match_approved_design_model(tmp_path):
    import stage09_publication_protocol_model as model

    result = io.publish(tmp_path / "published", build, validate)
    bound = pub.bindings(result.path, result.manifest, result.manifest_sha256)
    assert pub.canonical(pub.registration(bound)) == model.canonical(
        model.record(model.Binding(**bound))
    )


def test_postcommit_presentation_failure_does_not_demote(tmp_path, monkeypatch):
    from safe_geocoding_pipeline.preprocessing import stage09_cli as cli

    result = io.publish(tmp_path / "published", build, validate)
    before = snapshot(result.path)
    writes = []

    class Broken:
        def write(self, value):
            writes.append(True)
            raise OSError("synthetic stdout failure")

    monkeypatch.setattr(cli.sys, "stdout", Broken())
    cli._present(result)
    assert writes == [True]
    assert snapshot(result.path) == before
    assert (
        pub.adopt(result.path, result.manifest_sha256, validate).manifest
        == result.manifest
    )


def test_cli_preserves_explicit_uncertain_commit_diagnostic(
    tmp_path, monkeypatch, capsys
):
    from safe_geocoding_pipeline.preprocessing import stage09_cli as cli

    monkeypatch.setattr(cli, "require_goethe_nhr_slurm", lambda *args: None)

    def fail(config):
        raise c.Stage09Error("FAIL_CLOSED_COMMIT_OUTCOME_REQUIRES_RECONCILIATION")

    monkeypatch.setattr(cli, "materialize_stage09", fail)
    args = ["materialize", "--execution-git-sha", "f" * 40]
    for flag in (
        "stage08-root",
        "reference-raw-root",
        "reference-lock",
        "reference-pack-root",
        "output-directory",
    ):
        args.extend(["--" + flag, str(tmp_path / "unused-synthetic-path")])
    assert cli.main(args) == 1
    assert (
        capsys.readouterr().err
        == "STAGE09_COMMIT_OUTCOME_UNVERIFIED_RECONCILIATION_REQUIRED\n"
    )


def test_canonical_relations_ignore_physical_layout_but_guard_collisions(tmp_path):
    name = "reference_match_member"
    rows = [
        {
            "match_set_id": bytes([i]) * 32,
            "member_ordinal": 0,
            "witness": {
                "reference_object_id": b"o" * 32,
                "witness_role": "SUPPORT",
                "fields": [],
            },
        }
        for i in range(6)
    ]
    input_paths = []
    for index, group in enumerate((rows[:2], rows[2:])):
        writer = io.RelationWriter(
            tmp_path / f"input{index}",
            c.relation_schema(name),
            batch_rows=1,
            target_file_bytes=1,
        )
        for row in reversed(group):
            writer.append(row)
        writer.close()
        input_paths.extend(writer.paths)
    with io.bounded_connection(tmp_path / "spill", memory="128MB", threads=1) as db:
        first = io.canonicalize(db, name, input_paths, tmp_path / "first")
        second = io.canonicalize(
            db, name, list(reversed(input_paths)), tmp_path / "second"
        )
        assert first["logical_sha256"] == second["logical_sha256"]
        with pytest.raises(c.Stage09Error, match="COLLISION"):
            io.canonicalize(db, name, input_paths + input_paths, tmp_path / "duplicate")
    io.validate_relation(tmp_path, first)


def test_umask_restored_on_success_and_failure(tmp_path):
    original = os.umask(0o077)
    try:
        io.publish(tmp_path / "success", build, validate)
        assert os.umask(0o077) == 0o077
        with pytest.raises(c.Stage09Error):
            io.publish(
                tmp_path / "failed",
                lambda root: (_ for _ in ()).throw(ValueError()),
                validate,
            )
        assert os.umask(0o077) == 0o077
    finally:
        os.umask(original)

"""Fault injection on invented bundles, including rename ambiguity and ownership."""

from __future__ import annotations

import os

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s09_reference_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s09_reference_io as io


def build(root):
    io.write_exclusive(root / "synthetic.txt", b"synthetic public fixture\n")
    return {
        "fixture": True,
        "content_sha256": c.sha256_file(root / "synthetic.txt"),
        "logical_sha256": "0" * 64,
    }


def validate(root, digest, published):
    manifest = io.validate_terminal(root, digest, published)
    c.require(
        c.sha256_file(root / "synthetic.txt") == manifest["content_sha256"],
        "CONTENT_HASH_MISMATCH",
    )
    io.topology(
        root,
        [
            io.MANIFEST_NAME,
            "synthetic.txt",
            io.SUCCESS_NAME if published else "_IN_PROGRESS",
        ],
    )
    return manifest


def test_success_reopens_and_existing_success_is_readonly(tmp_path):
    final = tmp_path / "published"
    result = io.publish(final, build, validate)
    assert result.manifest == validate(final, result.manifest_sha256, True)
    with pytest.raises(c.Stage09Error, match="TARGET_EXISTS"):
        io.publish(final, build, validate)
    assert validate(final, result.manifest_sha256, True) == result.manifest


@pytest.mark.parametrize(
    "fault",
    [
        "build",
        "manifest",
        "private_validation",
        "success_write",
        "rename_before",
        "parent_fsync",
        "final_validation",
        "ownership",
    ],
)
def test_failures_leave_no_false_success_and_preserve_attempt(
    tmp_path, monkeypatch, fault
):
    final = tmp_path / "published"
    build_call = build
    validate_call = validate
    if fault == "build":

        def build_call(root):
            io.write_exclusive(root / "partial.txt", b"partial synthetic output")
            raise ValueError("sensitive sentinel must not escape")

    if fault in ("manifest", "success_write"):
        original = io.write_json

        def write(path, value):
            if path.name == (
                io.MANIFEST_NAME if fault == "manifest" else io.SUCCESS_NAME
            ):
                raise OSError("sensitive sentinel must not escape")
            original(path, value)

        monkeypatch.setattr(io, "write_json", write)
    if fault in ("private_validation", "final_validation"):

        def validate_call(root, digest, published):
            if published == (fault == "final_validation"):
                raise c.Stage09Error("SYNTHETIC_VALIDATION_FAILURE")
            return validate(root, digest, published)

    if fault == "rename_before":
        monkeypatch.setattr(
            io, "_atomic_rename", lambda *args: (_ for _ in ()).throw(OSError("failed"))
        )
    if fault == "parent_fsync":
        original_sync = io.fsync_directory

        def sync(path):
            if path == final.parent and final.exists():
                raise OSError("synthetic parent fsync failure")
            original_sync(path)

        monkeypatch.setattr(io, "fsync_directory", sync)
    if fault == "ownership":
        monkeypatch.setattr(
            io,
            "_final_ownership",
            lambda *args: (_ for _ in ()).throw(
                c.Stage09Error("SYNTHETIC_OWNERSHIP_FAILURE")
            ),
        )
    with pytest.raises(c.Stage09Error) as error:
        io.publish(final, build_call, validate_call)
    assert "sensitive sentinel" not in str(error.value)
    attempts = list(tmp_path.iterdir())
    assert len(attempts) == 1
    assert (attempts[0] / "_IN_PROGRESS").is_file()
    assert not (attempts[0] / io.SUCCESS_NAME).exists()


def test_rename_then_raise_adopts_only_the_owned_success(tmp_path, monkeypatch):
    original = io._atomic_rename

    def rename(source, destination):
        original(source, destination)
        raise OSError("synthetic ambiguous return")

    monkeypatch.setattr(io, "_atomic_rename", rename)
    result = io.publish(tmp_path / "published", build, validate)
    assert validate(result.path, result.manifest_sha256, True)


def test_unrelated_final_directory_is_never_deleted_or_adopted(tmp_path, monkeypatch):
    final = tmp_path / "published"

    def rename(source, destination):
        destination.mkdir(mode=0o700)
        io.write_exclusive(destination / "owner.txt", b"owner data")
        raise OSError("synthetic competing publication")

    monkeypatch.setattr(io, "_atomic_rename", rename)
    with pytest.raises(c.Stage09Error):
        io.publish(final, build, validate)
    assert (final / "owner.txt").read_bytes() == b"owner data"
    assert not (final / "_IN_PROGRESS").exists()
    assert not (final / io.SUCCESS_NAME).exists()
    assert len(list(tmp_path.glob(".published.attempt-*"))) == 1


def test_no_persistent_inode_gate(tmp_path):
    import shutil

    result = io.publish(tmp_path / "published", build, validate)
    clone = tmp_path / "copied_verified_bundle"
    shutil.copytree(result.path, clone)
    assert io.directory_identity(clone) != io.directory_identity(result.path)
    assert validate(clone, result.manifest_sha256, True) == result.manifest


def test_equal_content_foreign_directory_is_not_adopted(tmp_path, monkeypatch):
    import shutil

    final = tmp_path / "published"

    def copy_then_raise(source, destination):
        shutil.copytree(source, destination)
        raise OSError("synthetic foreign equal-content publication")

    monkeypatch.setattr(io, "_atomic_rename", copy_then_raise)
    with pytest.raises(c.Stage09Error):
        io.publish(final, build, validate)
    # It is another publisher's directory: preserve it without claiming that
    # this invocation owns/adopts/demotes it, despite identical content.
    assert (final / io.SUCCESS_NAME).is_file()
    own_attempt = next(tmp_path.glob(".published.attempt-*"))
    assert (own_attempt / "_IN_PROGRESS").is_file()
    assert not (own_attempt / io.SUCCESS_NAME).exists()


def test_reopen_detects_corruption_and_incomplete_state(tmp_path):
    result = io.publish(tmp_path / "published", build, validate)
    (result.path / "synthetic.txt").write_bytes(b"changed synthetic payload")
    with pytest.raises(c.Stage09Error, match="CONTENT_HASH_MISMATCH"):
        validate(result.path, result.manifest_sha256, True)
    io.write_exclusive(result.path / "_IN_PROGRESS", b"in_progress\n")
    with pytest.raises(c.Stage09Error, match="IN_PROGRESS_CONFLICT"):
        validate(result.path, result.manifest_sha256, True)


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

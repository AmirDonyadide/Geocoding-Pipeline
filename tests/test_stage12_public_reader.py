"""Exact original reads, pathname bindings and bounded descriptor cleanup."""

import os
import threading

import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_reader as r
from safe_geocoding_pipeline.preprocessing.stages import s12_public_fresh_reads as f
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from test_stage12_public_operations_v2 import offline  # noqa:F401


def source(tmp_path):
    root = tmp_path / "root"
    io.reserve(root)
    for n, raw in enumerate((b"", b"abc", bytes(range(256)) * 300)):
        io.write(root / str(n), raw)
    return root


def test_exact_bytes_two_passes_and_reduced_physical_opens(tmp_path, monkeypatch):
    root = source(tmp_path)
    original_open = os.open
    opens = []

    def opened(path, *a, **kw):
        opens.append(os.fspath(path))
        return original_open(path, *a, **kw)

    monkeypatch.setattr(os, "open", opened)
    with r.PublicReader(root) as reader:
        for _ in range(2):
            for name in ("0", "1", "2"):
                assert reader.read(root / name) == io.accepted.read_private(root / name)
        assert len(reader.files) == 3
    assert len(opens) == 10  # root +3 retained opens +6 independent baseline reads
    assert reader.closed and not reader.files and not reader.dirs


@pytest.mark.parametrize(
    "kind",
    ["contents", "missing", "symlink", "directory", "replace", "mode", "hardlink"],
)
def test_changed_file_never_reuses_old_bytes(tmp_path, kind):
    root = source(tmp_path)
    path = root / "1"
    with r.PublicReader(root) as reader:
        assert reader.read(path) == b"abc"
        if kind == "contents":
            path.write_bytes(b"def")
            assert (
                reader.read(path) == b"def"
            )  # callers' independent hashes reject changes
            return
        if kind == "missing":
            path.unlink()
        elif kind == "symlink":
            path.unlink()
            path.symlink_to(root / "2")
        elif kind == "directory":
            path.unlink()
            path.mkdir(mode=0o700)
        elif kind == "replace":
            path.rename(root / "old")
            io.write(path, b"abc")
        elif kind == "mode":
            path.chmod(0o644)
        else:
            os.link(path, root / "alias")
        with pytest.raises((c.Stage12Error, OSError)):
            reader.read(path)
        assert reader.closed and not reader.files


@pytest.mark.parametrize(
    "kind", ["root", "ancestor", "same_inode_symlink", "root_mode", "parent_mode"]
)
def test_configured_path_binding_not_only_held_descriptor(tmp_path, kind):
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    root = source(parent)
    child = root / "child"
    child.mkdir(mode=0o700)
    path = child / "payload"
    io.write(path, b"xyz")
    with r.PublicReader(root) as reader:
        assert reader.read(path) == b"xyz"
        if kind == "root":
            root.rename(parent / "old")
            root.mkdir(mode=0o700)
        elif kind in ("ancestor", "same_inode_symlink"):
            moved = tmp_path / "moved"
            parent.rename(moved)
            if kind == "ancestor":
                parent.mkdir(mode=0o700)
            else:
                parent.symlink_to(moved, target_is_directory=True)
        elif kind == "root_mode":
            root.chmod(0o755)
        else:
            child.chmod(0o755)
        with pytest.raises((c.Stage12Error, OSError)):
            reader.read(path)
        assert reader.closed


def test_directory_cache_evicts_and_deep_paths_use_exact_fallback(
    tmp_path, monkeypatch
):
    root = source(tmp_path)
    monkeypatch.setattr(r, "MAX_DESCRIPTORS", 4)
    with r.PublicReader(root) as reader:
        for i in range(20):
            directory = root / f"d{i}"
            directory.mkdir(mode=0o700)
            path = directory / "data"
            io.write(path, b"x")
            assert reader.read(path) == b"x"
            assert len(reader.files) + len(reader.dirs) <= 4
        path = root
        for _ in range(5):
            path = path / "deep"
            path.mkdir(mode=0o700)
        path = path / "data"
        io.write(path, b"deep")
        assert reader.read(path) == b"deep"
        path.chmod(0o644)
        with pytest.raises(c.Stage12Error):
            reader.read(path)


def test_reader_deadline_unhooks_and_work_error_is_not_reclassified(tmp_path):
    root = source(tmp_path)
    with r.PublicReader(root) as reader, io.public_originals(reader):
        error = recovery.FinalizationExpired()

        def fail():
            raise error

        reader.check = fail
        with pytest.raises(recovery.FinalizationExpired) as found:
            f._work_read(root / "1")
        assert found.value is error and reader.closed
    assert io.public_original_reader() is None


@pytest.mark.parametrize("primary", [False, True])
def test_view_cleanup_fault_clears_metadata_and_preserves_primary(
    tmp_path, monkeypatch, primary
):
    root = source(tmp_path)
    view = f.FreshReads(root)
    view.__enter__()
    actual = view.reader.close

    def close():
        actual()
        raise OSError(5, "INVENTED_CLEANUP")

    monkeypatch.setattr(view.reader, "close", close)
    if primary:
        (root / "1").write_bytes(b"def")
        with pytest.raises(c.Stage12Error):
            view.finish()
    else:
        with pytest.raises(OSError):
            view.finish()
    assert view.state == "INVALID" and not view.cache and not view.hashes
    assert not view.inputs and not view.directories and view.reader is None
    assert not io.has_read_view() and io.public_original_reader() is None


def test_foreign_thread_rejection_does_not_close_owner_reader(tmp_path):
    root = source(tmp_path)
    errors = []
    with r.PublicReader(root) as reader:

        def foreign():
            try:
                reader.read(root / "1")
            except c.Stage12Error:
                errors.append(1)

        thread = threading.Thread(target=foreign)
        thread.start()
        thread.join()
        assert errors == [1] and reader.read(root / "1") == b"abc"


def test_work_reader_is_direct_only_and_rechecks_membership_ancestors(tmp_path):
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    root = source(parent)
    with r.PublicReader(root, direct_work=True) as reader:
        assert reader.read(root / "1") == b"abc"
        parent.rename(tmp_path / "moved")
        parent.symlink_to(tmp_path / "moved", target_is_directory=True)
        # Baseline work-manifest semantics check all ancestors at boundaries;
        # a held descriptor/root inode alone does not authorize membership.
        with pytest.raises(c.Stage12Error):
            reader.check_path()
    parent.unlink()
    (tmp_path / "moved").rename(parent)
    child = root / "child"
    child.mkdir(mode=0o700)
    io.write(child / "payload", b"x")
    with r.PublicReader(root, direct_work=True) as reader:
        with pytest.raises(c.Stage12Error):
            reader.read(child / "payload")


def test_root_replacement_during_physical_read_fails(tmp_path, monkeypatch):
    root = source(tmp_path)
    old = os.pread
    changed = False

    def changed_read(*args):
        nonlocal changed
        raw = old(*args)
        if not changed:
            changed = True
            root.rename(tmp_path / "detached")
            root.mkdir(mode=0o700)
            io.write(root / "1", b"abc")
        return raw

    with r.PublicReader(root, direct_work=True) as reader:
        monkeypatch.setattr(os, "pread", changed_read)
        with pytest.raises(c.Stage12Error):
            reader.read(root / "1")
        assert reader.closed

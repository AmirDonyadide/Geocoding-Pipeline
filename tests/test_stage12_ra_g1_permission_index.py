"""Permission membership tests: synthetic metadata/private files, no live grants."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from test_s12_ra_g1_accounting import inputs
from test_stage12_ra_g1_allocation_controller import world  # noqa: F401
from test_stage12_public_operations_v2 import offline  # noqa: F401


def selected_names(environment, names):
    selected = deepcopy(environment.s)
    selected["source_files"] = [
        dict(path=name, bytes=0, sha256="1" * 64) for name in sorted(names)
    ]
    _, backends = inputs()
    selected["accounting_inventory"], selected["accounting"] = accounting.compile_inventory(
        selected["source_files"], backends, environment.m.SCOPE)
    return selected


def indexed(environment, selected, path, write=False, index=None):
    index = environment.m._SourcePermissionIndex(selected) if index is None else index
    return environment.m.allocation_path_policy(
        selected, path, write, source_index=index)


def test_borrowed_frozen_membership_and_reference_bound(world):  # noqa: F811
    selected = selected_names(world, [f"pkg/{i:04}.py" for i in range(2048)])
    index = world.m._SourcePermissionIndex(selected)
    assert len(index[2]) == 2048
    assert all(name is row["path"] for name, row in zip(index[2], selected["source_files"]))
    assert all(entry[0] is row["path"] and entry[2] is row["sha256"]
               for entry, row in zip(index[3], selected["source_files"]))
    assert world.m.SOURCE_PERMISSION_LOGICAL_BYTES == 115712
    assert 393216 + world.m.SOURCE_PERMISSION_LOGICAL_BYTES < 5 * 2**20
    with pytest.raises(AttributeError):
        index.extra = True
    with pytest.raises(TypeError):
        index.policy["paths"]["source"] = "/UNTRUSTED_SYNTHETIC"
    with pytest.raises(TypeError):
        index[2] = ()


def test_files_ancestors_near_misses_unicode_and_legacy_equivalence(world):  # noqa: F811
    names = ["a.py", "pkg/a.py", "pkg/deep/b.py", "pkg/é.py", "pkg/東京.py"]
    selected = selected_names(world, names)
    index = world.m._SourcePermissionIndex(selected)
    source = Path(selected["paths"]["source"])
    cases = [(source / name, write) for name in names for write in (False, True)]
    cases += [
        (source, False), (source / "pkg", False), (source / "pkg/deep", False),
        (source / "pk", False), (source / "pkgx", False),
        (source / "pkg/a.py.extra", False), (source / "pkg/é.py.extra", False),
        (source / "pkg/unlisted.py", False), (Path("relative"), False),
        (str(source) + "/./pkg/a.py", False),
        (str(source) + "//pkg/a.py", False),
        (str(source) + "/../escape.py", False),
    ]
    for path, write in cases:
        assert indexed(world, selected, path, write, index) == world.m.allocation_path_policy(
            selected, path, write)


@pytest.mark.parametrize("mutation", [
    "path", "bytes", "bool_bytes", "hash", "append", "reorder", "source",
    "record", "version", "window", "extra", "source_list_replacement",
])
def test_stale_permission_binding_fails_closed(world, mutation):  # noqa: F811
    selected = selected_names(world, ["pkg/a.py", "pkg/b.py"])
    index = world.m._SourcePermissionIndex(selected)
    target = Path(selected["paths"]["source"]) / "pkg/a.py"
    if mutation == "path":
        selected["source_files"][0]["path"] = "pkg/new.py"
    elif mutation == "bytes":
        selected["source_files"][0]["bytes"] = 1
    elif mutation == "bool_bytes":
        selected["source_files"][0]["bytes"] = False
    elif mutation == "hash":
        selected["source_files"][0]["sha256"] = "2" * 64
    elif mutation == "append":
        selected["source_files"].append(dict(path="new.py", bytes=0, sha256="1" * 64))
    elif mutation == "reorder":
        selected["source_files"].reverse()
    elif mutation == "source":
        selected["paths"]["source"] += "_changed"
    elif mutation == "record":
        selected["records"]["adoption"] = "3" * 64
    elif mutation == "version":
        selected["version"] = "UNTRUSTED_SYNTHETIC"
    elif mutation == "window":
        selected["valid_until"] = "2026-01-03T00:00:00.000000Z"
    elif mutation == "extra":
        selected["untrusted_index"] = {}
    else:
        selected["source_files"] = list(selected["source_files"])
    with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
        indexed(world, selected, target, index=index)


def test_other_selection_or_untrusted_index_is_not_reused(world):  # noqa: F811
    selected = selected_names(world, ["pkg/a.py"])
    index = world.m._SourcePermissionIndex(selected)
    path = Path(selected["paths"]["source"]) / "pkg/a.py"
    with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
        indexed(world, deepcopy(selected), path, index=index)
    with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
        indexed(world, selected, path, index=SimpleNamespace(matches=lambda value: True))
    invalid = deepcopy(selected)
    invalid["untrusted_index"] = index
    with pytest.raises(RuntimeError, match="FIELDS"):
        world.m._SourcePermissionIndex(invalid)


@pytest.mark.parametrize("unsupported", ["root_length", "root_depth", "relative_length", "rows"])
def test_unsupported_execution_index_preserves_old_parser(world, unsupported):  # noqa: F811
    selected = deepcopy(world.s)
    if unsupported == "root_length":
        selected["paths"]["source"] = "/" + "x" * 513
        assert world.m.validate_selection(selected) is selected
    elif unsupported == "root_depth":
        selected["paths"]["source"] = "/" + "/".join(["x"] * 65)
        assert world.m.validate_selection(selected) is selected
    elif unsupported == "relative_length":
        selected["source_files"][0]["path"] = "x" * 513
    else:
        selected["source_files"] = selected["source_files"] * 2049
    with pytest.raises(RuntimeError, match="SOURCE_INDEX_UNSUPPORTED"):
        world.m._SourcePermissionIndex(selected)


def test_oversized_nonmember_rejected_before_relative_query(world, monkeypatch):  # noqa: F811
    selected = selected_names(world, ["pkg/a.py"])
    index = world.m._SourcePermissionIndex(selected)
    source = Path(selected["paths"]["source"])

    def no_bisect(*args, **kwargs):
        raise AssertionError("OVERSIZED_QUERY_REACHED_MEMBERSHIP")

    monkeypatch.setattr(world.m, "bisect_left", no_bisect)
    assert not index.contains(source / ("x" * 100000), source)
    assert not index.contains(source / "/".join(["x"] * 10000), source)
    assert not index.contains(Path("/outside") / "/".join(["x"] * 10000), source)


def test_filesystem_alias_changes_are_fresh_and_controls_unchanged(world):  # noqa: F811
    selected = deepcopy(world.s)
    index = world.m._SourcePermissionIndex(selected)
    path = world.source / "synthetic_only.py"
    outside = world.source.parent / "outside.py"
    outside.write_bytes(b"SYNTHETIC_ONLY")
    outside.chmod(0o600)
    assert indexed(world, selected, path, index=index)
    path.unlink()
    path.symlink_to(outside)
    assert not indexed(world, selected, path, index=index)
    path.unlink()
    path.write_bytes(b"SYNTHETIC_RESTORED")
    path.chmod(0o600)
    assert indexed(world, selected, path, index=index)
    for key in ("worker_return", "supervisor_state"):
        assert indexed(world, selected, selected["paths"][key], index=index)
        assert not indexed(world, selected, selected["paths"][key], True, index)
    for secret in (".ssh", ".config", "credentials", ".git", ".env.synthetic"):
        assert not indexed(world, selected, world.source / secret / "x", index=index)


def test_installed_callback_borrows_one_index_and_full_hash_eof_remain_fresh(
    world, monkeypatch  # noqa: F811
):
    m, selected = world.m, deepcopy(world.s)
    cgroup = world.records / "SYNTHETIC_ONLY.cgroup"
    cgroup.write_bytes(b"0::/SYNTHETIC_ONLY\n")
    cgroup.chmod(0o600)
    actual_open, actual_validate = m.os.open, m.validate_selection
    validations, audited_opens, charges = [], [], []
    guard = SimpleNamespace()
    selected_limit = [0]

    def native_install(*args):
        return (object(), "LINUX_X86_64_SECCOMP_NETWORK_ERRNO_PLUS_PYTHON_AUDIT",
                [0], selected_limit, lambda *args: None,
                lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("DENIED")))

    guard.install_denials = native_install

    def validate(value):
        validations.append(value)
        return actual_validate(value)

    def opening(path, flags, *args, **kwargs):
        if str(path) == f"/proc/{m.os.getpid()}/cgroup":
            return actual_open(cgroup, flags, *args, **kwargs)
        if str(path).startswith(str(world.source)):
            audited_opens.append(str(path))
            assert guard.open_allowed(
                path, write=False, source=world.source, output=world.root,
                input_path=world.root / "input", evidence=world.records)
        return actual_open(path, flags, *args, **kwargs)

    class Secret:
        pass

    import safe_geocoding_pipeline.preprocessing.stages as package
    monkeypatch.setattr(package, "s12_transport", SimpleNamespace(Secret=Secret))
    monkeypatch.setattr(m, "module", lambda source, name: guard)
    monkeypatch.setattr(m, "validate_selection", validate)
    monkeypatch.setattr(m.os, "open", opening)
    m.install_denials(selected, read_charge=lambda calls, size: charges.append((calls, size)))
    assert len(validations) == 1
    assert selected_limit[0] == 184184 + 1544
    assert guard.open_allowed(
        world.source / "synthetic_only.py", write=False, source=world.source,
        output=world.root, input_path=world.root / "input", evidence=world.records)
    assert not guard.open_allowed(
        world.source / "unlisted.py", write=False, source=world.source,
        output=world.root, input_path=world.root / "input", evidence=world.records)
    assert len(validations) == 1
    run = m.Run(selected, stage="ready", stage_seconds=30)
    try:
        run.sources()
        assert run.read_calls >= 2
        before = (run.read_calls, run.read_bytes)
        code = world.source / "synthetic_only.py"
        raw = code.read_bytes()
        code.write_bytes(b"X" + raw[1:])
        with pytest.raises(RuntimeError, match="SOURCE_CHANGED"):
            run.sources()
        assert run.read_calls > before[0] and run.read_bytes > before[1]
        opened = len(audited_opens)
        monkeypatch.setattr(m, "now", lambda: "2026-01-03T00:00:00.000000Z")
        with pytest.raises(RuntimeError, match="DEADLINE"):
            run.sources()
        assert len(audited_opens) == opened
    finally:
        run.close()
    assert len(charges) >= 4

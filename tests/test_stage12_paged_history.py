"""Invented private sources; no protected rows, provider or credentials."""

import os

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_paged_history as h
from safe_geocoding_pipeline.preprocessing.stages import s12_public_history as old
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_stage12_public_operations_v2 import offline  # noqa: F401


def limits(**kwargs):
    return {
        "maximum_entries": 50000,
        "maximum_name_bytes": 512,
        "maximum_total_name_bytes": 20 * 2**20,
        "page_entries": 3,
        "maximum_depth": 8,
        "maximum_file_bytes": 2**30,
        **kwargs,
    }


def source(root, count=20):
    io.reserve(root)
    io.reserve(root / "events")
    io.reserve(root / "attempts")
    for n in range(1, count + 1):
        io.write(root / "events" / f"{n:020d}.json", c.canonical({"seq": n}))
    for name in ("a", "a.json", "Ω", "z"):
        io.write(root / "attempts" / name, b"invented")
    return root


def test_all_actual_name_families_have_exact_path_order_in_small_pages(tmp_path):
    root = source(tmp_path / "source")
    selected = limits()
    actual = [root / name for name, _, _ in h.ordered(root, selected)]
    assert actual == [root, *sorted(root.rglob("*"))]
    # Selected finite roots exceed the historical ceiling; storage remains a
    # function of the page selection, never the complete member count.
    assert selected["maximum_entries"] > old.MAX_ENTRIES
    with h.selected(selected), h.Fresh(root) as stage:
        for path in actual:
            if path.is_file():
                assert io.read(path) == path.read_bytes()
                assert len(stage.page) <= 3
        assert stage._reserved == h.reservation(selected) < 2**20
    assert stage.state == "VERIFIED" and old._backing == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "content",
        "missing",
        "added",
        "reordered",
        "truncated",
        "mode",
        "hardlink",
        "symlink",
        "directory",
        "root",
    ],
)
def test_pre_persist_post_persist_and_independent_opener_reject_mutations(
    tmp_path, mutation
):
    root = source(tmp_path / "source", 8)
    selected = limits(page_entries=2)
    with h.Fresh(root, limits=selected):
        assert io.read(root / "events" / f"{1:020d}.json")
    with pytest.raises((c.Stage12Error, OSError)):
        with h.Fresh(root, limits=selected) as stage:
            one = root / "events" / f"{1:020d}.json"
            two = root / "events" / f"{2:020d}.json"
            if mutation == "content":
                one.write_bytes(b"changed")
            elif mutation == "missing":
                one.unlink()
            elif mutation == "added":
                io.write(root / "new", b"new")
            elif mutation == "reordered":
                raw = one.read_bytes()
                one.write_bytes(two.read_bytes())
                two.write_bytes(raw)
            elif mutation == "truncated":
                one.write_bytes(b"")
            elif mutation == "mode":
                one.chmod(0o644)
            elif mutation == "hardlink":
                os.link(one, root / "linked")
            elif mutation == "symlink":
                one.unlink()
                one.symlink_to(two)
            elif mutation == "directory":
                one.unlink()
                one.mkdir(mode=0o700)
            else:
                root.rename(tmp_path / "renamed")
                root.mkdir(mode=0o700)
    assert stage.state == "INVALID" and old._backing == 0
    assert not io.has_read_view()


def test_fresh_page_read_rejects_changed_then_restored_source(tmp_path):
    root = source(tmp_path / "source")
    with pytest.raises(c.Stage12Error):
        with h.Fresh(root, limits=limits()):
            path = root / "events" / f"{1:020d}.json"
            raw = io.read(path)
            path.write_bytes(b"modified")
            path.write_bytes(raw)
            io.read(path)  # Fresh file metadata/content binding survives a hit.
    assert old._backing == 0


def test_selected_caps_deadline_and_uncertain_output_preserve_originals(tmp_path):
    root = source(tmp_path / "source")
    with pytest.raises(c.Stage12Error):
        with h.Fresh(root, limits=limits(maximum_entries=5)):
            pass
    calls = [0]

    def deadline():
        calls[0] += 1
        c.require(calls[0] < 12, "SYNTHETIC_DEADLINE")

    with pytest.raises(c.Stage12Error, match="SYNTHETIC_DEADLINE"):
        with h.Fresh(root, limits=limits(), check=deadline):
            pass
    with pytest.raises(c.Stage12Error):
        with h.Fresh(root, limits=limits(), outputs={"output"}) as stage:
            io.write(root / "output", b"partial preserved")
            # An uncertain writer never registers the generated original.
    assert stage.state == "INVALID"
    assert (root / "output").read_bytes() == b"partial preserved"
    assert old._backing == 0 and not io.has_read_view()


def test_complete_source_larger_than_old_reader_enumerates_without_index(tmp_path):
    root = tmp_path / "events"
    io.reserve(root)
    # Sparse invented event bodies suffice to exercise actual filesystem
    # membership above the old fixed index; no workload/performance claim.
    for n in range(1, old.MAX_ENTRIES + 2):
        fd = os.open(
            root / f"{n:020d}.json", os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o600
        )
        os.close(fd)
    selected = limits(page_entries=2)
    assert sum(1 for _ in h.event_paths(root, selected)) == old.MAX_ENTRIES + 1
    assert old._backing == 0
    with pytest.raises(c.Stage12Error):
        list(h.event_paths(root, {**selected, "maximum_entries": old.MAX_ENTRIES}))


def test_chain_uses_one_shared_arena_and_reopens_each_original(tmp_path):
    first = source(tmp_path / "first", 4)
    second = source(tmp_path / "second", 4)

    def roots():
        return iter((first, second))

    with h.ChainFresh(tmp_path, roots, limits=limits()) as stage:
        assert io.read(first / "attempts" / "a") == b"invented"
        assert io.read(second / "attempts" / "Ω") == b"invented"
        assert old._backing == h.reservation(limits())
    assert stage.state == "VERIFIED" and old._backing == 0


def test_declared_streaming_output_is_unreadable_until_registered(tmp_path):
    root = source(tmp_path / "source", 4)
    with h.Fresh(root, limits=limits(page_entries=1), outputs={"ledger"}) as stage:
        io.write(root / "ledger", b"[")
        assert io.read(root / "attempts" / "Ω") == b"invented"
        assert "ledger" in stage.pending_outputs
        with pytest.raises(c.Stage12Error):
            io.read(root / "ledger")
        (root / "ledger").write_bytes(b"[]\n")
        io.record_read_output(root / "ledger", c.sha(b"[]\n").hex())
        assert io.read(root / "ledger") == b"[]\n"
    assert stage.state == "VERIFIED" and old._backing == 0


def test_numeric_directory_mutation_fails_before_next_page_return(tmp_path):
    root = source(tmp_path / "source", 20)
    with pytest.raises(c.Stage12Error):
        with h.Fresh(root, limits=limits(page_entries=1)):
            io.read(root / "events" / f"{1:020d}.json")
            extra = root / "events" / "foreign"
            io.write(extra, b"extra")
            extra.unlink()  # Restored membership cannot restore directory epoch.
            io.read(root / "events" / f"{20:020d}.json")
    assert old._backing == 0


@pytest.mark.parametrize("boundary", ["read", "page", "finish"])
def test_registered_output_replacement_with_identical_bytes_rejects(tmp_path, boundary):
    root = source(tmp_path / "source", 4)
    with pytest.raises(c.Stage12Error):
        with h.Fresh(root, limits=limits(page_entries=1), outputs={"ledger"}) as stage:
            output = root / "ledger"
            io.write(output, b"[]\n")
            io.record_read_output(output, c.sha(b"[]\n").hex())
            replacement = tmp_path / "replacement"
            io.write(replacement, b"[]\n")
            assert replacement.stat().st_ino != output.stat().st_ino
            os.replace(replacement, output)
            if boundary == "read":
                io.read(output)
            elif boundary == "page":
                io.read(root / "attempts" / "Ω")
    assert stage.state == "INVALID" and old._backing == 0
    assert not io.has_read_view()

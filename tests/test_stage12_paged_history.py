"""Invented private sources; no protected rows, provider or credentials."""

import hashlib
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


# Exact pre-repair partition oracle from bddb1ff; it changes no source reader.
_BASELINE_BUCKETS = 4096
def _baseline_bucket(self, name):
    buckets = min(
        _BASELINE_BUCKETS,
        max(1, self.limits["maximum_entries"] // self.limits["page_entries"]),
    )
    parent, _, filename = name.rpartition("/")
    if parent.rsplit("/", 1)[-1] == "events" or (
        self.root.name == "events" and not parent
    ):
        stem = filename[:-5] if filename.endswith(".json") else ""
        if len(stem) == 20 and stem.isascii() and stem.isdigit():
            n = int(stem)
            c.require(
                1 <= n <= self.limits["maximum_entries"], "S12_PUBLIC_HISTORY_LIMIT"
            )
            return min(
                buckets - 1, (n - 1) * buckets // self.limits["maximum_entries"]
            )
    return (
        int.from_bytes(hashlib.sha256(name.encode("utf8")).digest()[:2], "big")
        % buckets
    )


class _BaselineFresh(h.Fresh):
    _bucket = _baseline_bucket


def test_affinity_canonical_work_and_attempt_geometries_preserve_fallback(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    selected = limits(maximum_entries=4096, page_entries=128)
    stage = h.Fresh(tmp_path / "campaign", limits=selected)
    baseline = _BaselineFresh(tmp_path / "campaign", limits=selected)
    assert len({stage._bucket(f"work/{n:020d}.json") for n in range(1, 65)}) == 1
    arbitrary = ["", "other/file", "work/0.json", "work/00000000000000000000.json",
                 "work/00000000000000004097.json", "work/18446744073709551616.json",
                 "work/１２３.json", "work/" + "١" * 20 + ".json", "archive/work/00000000000000000001.json",
                 "archive/call_0001_attempt_1/work.json",
                 "attempts/call_0001_attempt_1/nested/deeper/file.json", "attempts/call_０００１_attempt_1/a",
                 "attempts/call_0000_attempt_1/a", "attempts/call_00001_attempt_1/a",
                 "attempts/call_0001_attempt_6/a", "attempts/call_18446744073709551616_attempt_1/a"]
    for name in arbitrary:
        assert stage._bucket(name) == baseline._bucket(name)
    leaves = ("work.json", "operations_profile.json", "call_0001_attempt_1.zst", "request_materialization.json")
    for number in (1, 9, 9999, 10000, 2**64-1):
        for attempt in range(1, 6):
            key = audit.name_for(number, attempt)
            assert h._attempt_key(key) == key
            stages = ((stage, lambda leaf: f"attempts/{key}/{leaf}"),
                      (h.Fresh(tmp_path / "attempts", limits=selected), lambda leaf: f"{key}/{leaf}"),
                      (h.Fresh(tmp_path / key, limits=selected), lambda leaf: leaf))
            for current, path in stages:
                assert len({current._bucket(path(leaf)) for leaf in leaves}) == 1
    # The event-specific eligibility/fast path is unchanged, including rejection.
    assert not stage._numeric_name("work/00000000000000000001.json")
    assert stage._numeric_name("events/00000000000000000001.json")
    for current in (stage, baseline):
        with pytest.raises(c.Stage12Error):
            current._bucket("events/00000000000000000000.json")


def _affinity_source(root):
    io.reserve(root)
    io.reserve(root / "work")
    io.reserve(root / "attempts")
    for n in range(1, 9):
        io.write(root / "work" / f"{n:020d}.json", c.canonical({"work_id": n}))
    for number in (1, 2):
        directory = root / "attempts" / f"call_{number:04d}_attempt_1"
        io.reserve(directory)
        for leaf in ("begin.json", "receipt.json", "work.json"):
            io.write(directory / leaf, c.canonical({"work_id": number, "part": leaf}))
    return root


@pytest.mark.parametrize("kind", ["work", "attempt"])
@pytest.mark.parametrize("mutation", ["content", "missing", "added_alias", "source_inode", "mode", "symlink", "root", "ancestor"])
def test_affinity_cached_pages_preserve_original_and_final_rejection(tmp_path, kind, mutation):
    outcomes = []
    for index, reader_type in enumerate((_BaselineFresh, h.Fresh)):
        parent = tmp_path / str(index)
        io.reserve(parent)
        root = _affinity_source(parent / "source")
        target = root / "work" / f"{1:020d}.json" if kind == "work" else root / "attempts/call_0001_attempt_1/work.json"
        selected = limits(maximum_entries=4096, page_entries=128)
        with pytest.raises((c.Stage12Error, OSError)) as failure:
            with reader_type(root, limits=selected, descriptor_relative=True) as stage:
                raw = io.read(target)
                if mutation == "content":
                    target.write_bytes(b"changed")
                elif mutation == "missing":
                    target.unlink()
                elif mutation == "added_alias":
                    io.write(target.parent / "extra_alias.json", raw)
                elif mutation == "source_inode":
                    temporary = parent / "replacement"
                    io.write(temporary, raw)
                    os.replace(temporary, target)
                elif mutation == "mode":
                    target.chmod(0o644)
                elif mutation == "symlink":
                    target.unlink()
                    target.symlink_to(root / "work" / f"{2:020d}.json")
                elif mutation == "root":
                    root.rename(parent / "old_source")
                    _affinity_source(root)
                else:
                    backup = tmp_path / f"old_parent_{index}"
                    parent.rename(backup)
                    parent.mkdir(mode=0o700)
                    (backup / "source").rename(root)
                io.read(target)
        outcomes.append((type(failure.value), failure.value.args))
        assert stage.state == "INVALID" and old._backing == 0 and not io.has_read_view()
    assert outcomes[0] == outcomes[1]


def test_affinity_deadline_cache_hits_and_uncertain_outputs_remain_fail_closed(tmp_path):
    for index, reader_type in enumerate((_BaselineFresh, h.Fresh)):
        root = _affinity_source(tmp_path / str(index))
        expired = [False]
        def check():
            if expired[0]:
                raise TimeoutError("SYNTHETIC_DEADLINE")
        with pytest.raises(TimeoutError):
            with reader_type(root, limits=limits(page_entries=128), check=check):
                assert io.read(root / "work" / f"{1:020d}.json")
                expired[0] = True
                io.read(root / "work" / f"{2:020d}.json")
        assert old._backing == 0 and not io.has_read_view()
        with pytest.raises(c.Stage12Error):
            with reader_type(root, limits=limits(), outputs={"partial"}):
                io.write(root / "partial", b"partial remains")
        assert (root / "partial").read_bytes() == b"partial remains"
        assert old._backing == 0 and not io.has_read_view()


def _live_report_replay(root, original, start, cut):
    """New invented unit journal/sole writer; never reconstruct live owner fields."""
    from test_stage12_public_operations_v2 import FakeClock
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as operations
    clock = FakeClock()
    writer = journal.Writer(root, 2, 5000, lambda: None)
    log = journal.Journal(writer, start, clock, event_budget=10000, storage_budget=2**28, closure_events=16)
    for name in ("work", "attempts"):
        io.reserve(root / name)
        for path in sorted((original / name).rglob("*")):
            destination = root / path.relative_to(original)
            if path.is_dir():
                io.reserve(destination)
            else:
                io.write(destination, path.read_bytes())
    io.write(root / "repeat_comparison.json", (original / "repeat_comparison.json").read_bytes())
    expected = []
    for event in journal.read_events(original, operations.digest(start)):
        if event["seq"] > cut:
            continue
        clock.advance(event["mono_ns"] - clock.now_ns())
        if event["kind"] == "SEGMENT_OPEN":
            body = event["body"]
            log.open_segment(event["segment_id"], event["epoch_id"], body)
        else:
            log.event(event["kind"], event["body"])
        expected.append(event)
    assert list(journal.read_events(root, operations.digest(start))) == expected
    return writer, log


@pytest.mark.parametrize("corrupt", [False, True])
def test_affinity_live_prefix_report_metrics_receipt_unknowns_and_physical_work_match(tmp_path, monkeypatch, corrupt, record_property):
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operations as operations
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_operational_audit as operational_audit
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_reporting as reporting
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_work_index as work_index
    from test_stage12_public_scheduler import run_offline
    import time
    # Existing legacy unit Authority/FakeClock and invented transport only prepare
    # valid originals. All replay/read/report/receipt validators below are real.
    campaign, original, (profile, plan, start, rows, _) = run_offline(tmp_path, count=4)
    results = []
    counts = []
    for index, reader_type in enumerate((_BaselineFresh, h.Fresh)):
        writer, log = _live_report_replay(tmp_path / f"replay_{index}", original, start, campaign["blocks"][0]["input_last_event_seq"])
        root = writer.root
        if corrupt:
            path = root / "attempts" / audit.name_for(1, 1) / (audit.name_for(1, 1) + "_receipt.json")
            path.write_bytes(b"{}\n")
        def works():
            for row in rows:
                yield io.metadata(io.read(root / "work" / f"{row['work_id']:020d}.json"))
        actual_index = work_index.WorkIndex(works, lambda key: io.metadata(io.read(root / "work" / f"{key:020d}.json")), plan)
        def verify_receipt(row, body):
            name = audit.name_for(row["work_id"], body["attempt"])
            attempt = root / "attempts" / name
            assert io.metadata(io.read(attempt / "work.json")) == row
            terminal = audit.reopen(attempt, name, validator=cli.public_shapes, context=operational_audit.DataContext(None))
            operations.require(c.sha(io.read(attempt / (name + "_receipt.json"))).hex() == body["receipt_inventory_sha256"])
            return terminal
        def repeat_evidence():
            comparisons = list(journal.read_array(root / "repeat_comparison.json"))
            return operations.digest(comparisons), all(row["equal"] for row in comparisons)
        observed = dict(member_rows=0, hash_calls=0, reads=0, read_bytes=0, opens=0)
        original_members = reader_type._members
        original_hash = old.hash_file
        original_read, original_pread, original_open = os.read, os.pread, os.open
        def members(self):
            for member in original_members(self):
                observed["member_rows"] += 1
                yield member
        def hashed(*args, **kwargs):
            observed["hash_calls"] += 1
            return original_hash(*args, **kwargs)
        def read(fd, count):
            value = original_read(fd, count)
            observed["reads"] += 1
            observed["read_bytes"] += len(value)
            return value
        def pread(fd, count, offset):
            value = original_pread(fd, count, offset)
            observed["reads"] += 1
            observed["read_bytes"] += len(value)
            return value
        def opening(*args, **kwargs):
            observed["opens"] += 1
            return original_open(*args, **kwargs)
        started = time.monotonic_ns()
        try:
            with monkeypatch.context() as patch:
                patch.setattr(reader_type, "_members", members)
                patch.setattr(old, "hash_file", hashed)
                patch.setattr(os, "read", read)
                patch.setattr(os, "pread", pread)
                patch.setattr(os, "open", opening)
                with reader_type(root, limits=limits(page_entries=128), outputs={"measurement_event_prefix.json"}, descriptor_relative=True) as stage:
                    prefix = journal.MeasurementPrefix(log)
                    assert prefix.journal is log and prefix.build()
                    result = reporting.block_report(plan, profile, 1, events=prefix.events, works=works,
                        verified_receipt=verify_receipt,
                        repeat_evidence=repeat_evidence,
                        monitoring_closed=lambda: profile["monitoring"]["mode"] == "PUBLIC_GAPS_ONLY", work_index=actual_index)
                    prefix.verify_original()
                    assert len(stage.page) <= 128 and stage._reserved == h.reservation(limits(page_entries=128))
            observed["elapsed_ns"] = time.monotonic_ns() - started
            results.append(result)
            counts.append(observed)
        finally:
            writer.abort()
        assert not writer.thread.is_alive() and old._backing == 0 and not io.has_read_view()
    assert c.canonical(results[0]) == c.canonical(results[1])
    assert results[0]["status"] == ("INCOMPLETE" if corrupt else "EXPLORATORY_ONLY")
    if corrupt:
        assert results[0]["counts"]["http_completions"]["value"] is None
    assert counts[1]["member_rows"] < counts[0]["member_rows"]
    assert counts[1]["read_bytes"] < counts[0]["read_bytes"]
    record_property("affinity_case", "corrupt" if corrupt else "valid")
    record_property("baseline_counts", counts[0])
    record_property("candidate_counts", counts[1])
    record_property("performance_scope", "SMALL_LOCAL_BASELINE_FIRST_REAL_IO_NOT_GOETHE_OR_FULL512_QUALIFICATION")


def test_affinity_work_stays_generic_across_event_work_attempt_transitions(tmp_path, monkeypatch):
    root = _affinity_source(tmp_path / "source")
    io.reserve(root / "events")
    for number in range(1, 7):
        io.write(root / "events" / f"{number:020d}.json", c.canonical({"seq": number}))
    numeric = []
    generic = []
    original_numeric = h.Fresh._numeric_page
    original_snapshot = h.Fresh._snapshot
    def numeric_page(self, target):
        numeric.append(target)
        return original_numeric(self, target)
    def snapshot(self, target=None):
        if target is not None and not self._numeric_name(target):
            generic.append(target)
        return original_snapshot(self, target)
    monkeypatch.setattr(h.Fresh, "_numeric_page", numeric_page)
    monkeypatch.setattr(h.Fresh, "_snapshot", snapshot)
    selected = limits(maximum_entries=4096, page_entries=128)
    with h.Fresh(root, limits=selected, descriptor_relative=True) as stage:
        for path in (root / "events" / f"{1:020d}.json", root / "work" / f"{1:020d}.json",
                     root / "attempts/call_0001_attempt_1/begin.json", root / "events" / f"{2:020d}.json"):
            assert io.read(path) == path.read_bytes()
            assert len(stage.page) <= 128
        assert stage._reserved == h.reservation(selected)
    assert any(value.startswith("work/") for value in generic)
    assert len(numeric) == 2 and all(value.startswith("events/") for value in numeric)
    assert old._backing == 0 and not io.has_read_view()

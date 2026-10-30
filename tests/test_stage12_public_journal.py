"""Single-writer and durable ordering faults; no socket or provider use."""

import threading

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as j
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from test_stage12_public_operations_v2 import H, FakeClock, inputs, offline  # noqa: F401


def setup(tmp_path):
    _, _, start, _, _ = inputs()
    stopped = threading.Event()
    writer = j.Writer(tmp_path / "journal", 2, 1000, stopped.set)
    log = j.Journal(
        writer,
        start,
        FakeClock(),
        event_budget=100,
        storage_budget=2**20,
        closure_events=10,
    )
    log.open_segment(
        1,
        H,
        {
            "authority_sha256": H,
            "predecessor_snapshot_sha256": None,
            "writer_exclusion_evidence_sha256": H,
            "block_id": 1,
            "state_id": 1,
        },
    )
    return writer, log, stopped


def test_T05_one_writer_and_complete_hash_chain(tmp_path):
    writer, log, stopped = setup(tmp_path)
    seen = []
    threads = [
        threading.Thread(
            target=lambda: writer.call(lambda: seen.append(threading.get_ident()))
        )
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(seen)) == 1 and seen[0] == writer.thread.ident
    log.event("BEGIN_DURABLE", {"work_id": 1, "attempt": 1, "begin_sha256": H})
    events = list(j.read_events(writer.root, log.start_hash))
    assert [e["seq"] for e in events] == [1, 2]
    assert events[1]["previous_event_sha256"] == c.sha(c.canonical(events[0])).hex()
    with pytest.raises(FileExistsError):
        j.Writer(writer.root, 2, 1000, stopped.set)
    writer.release({"scope": "SYNTHETIC_TEST_ONLY"})


@pytest.mark.parametrize("boundary", ["write", "fsync", "reopen"])
def test_T07_durability_failure_poison_and_no_reuse(monkeypatch, tmp_path, boundary):
    writer, log, stopped = setup(tmp_path)
    if boundary == "write":
        monkeypatch.setattr(
            io,
            "write",
            lambda *_: (_ for _ in ()).throw(OSError("synthetic write failure")),
        )
    elif boundary == "fsync":
        monkeypatch.setattr(
            io,
            "fsync_directory",
            lambda *_: (_ for _ in ()).throw(OSError("synthetic fsync failure")),
        )
    else:
        monkeypatch.setattr(
            io,
            "read",
            lambda *_a, **_k: (_ for _ in ()).throw(
                OSError("synthetic reopen failure")
            ),
        )
    with pytest.raises(OSError):
        log.event("BEGIN_DURABLE", {"work_id": 1, "attempt": 1, "begin_sha256": H})
    assert stopped.is_set() and writer.failed.is_set()
    with pytest.raises(c.Stage12Error):
        writer.call(lambda: None)


def test_T14_mutation_and_timing_closed_shapes(tmp_path):
    writer, log, _ = setup(tmp_path)
    with pytest.raises(c.Stage12Error):
        log.event("RESOURCE", {"observed_mono_ns": 0, "cause": "PERIODIC"})
    assert writer.failed.is_set()


def test_1804093_stream_derivation_is_outside_writer_and_exact(tmp_path):
    writer, log, stopped = setup(tmp_path)
    rows = [{"row": i, "scope": "SYNTHETIC_ONLY"} for i in range(8)]

    def derive():
        for i, row in enumerate(rows):
            assert threading.current_thread() is not writer.thread
            # Each previous row was written before the next was requested.
            if i:
                assert c.canonical(rows[i - 1])[:-1] in io.read(
                    writer.root / "rows.json"
                )
            yield row

    try:
        digest = log.stream_array("rows.json", derive())
        assert list(j.read_array(writer.root / "rows.json")) == rows
        assert digest == c.sha(c.canonical(rows)).hex()
        assert not stopped.is_set()
        with pytest.raises(FileExistsError):
            log.stream_array("rows.json", iter(rows))
    finally:
        writer.abort()


def test_1804093_stream_derivation_failure_survives_cleanup_failure(
    monkeypatch, tmp_path
):
    writer, log, _ = setup(tmp_path)

    def derive():
        yield {"row": 1}
        monkeypatch.setattr(
            j.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("SECONDARY"))
        )
        raise ValueError("PRIMARY")

    try:
        with pytest.raises(ValueError, match="PRIMARY"):
            log.stream_array("partial.json", derive())
        assert writer.failed.is_set()
        assert io.read(writer.root / "partial.json") == b'[{"row":1}'
        assert not (writer.root / "_WRITER_RELEASED.json").exists()
    finally:
        writer.abort()


def test_1804093_periodic_failure_at_safe_point_poison_is_bounded(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit

    writer, log, stopped = setup(tmp_path)
    io.write(writer.root / "synthetic", b"synthetic")
    entered, proceed = threading.Event(), threading.Event()
    result = []

    def transaction():
        entered.set()
        assert proceed.wait(1)

        def validate(_):
            io.read(writer.root / "synthetic")
            return ()

        # A sampler I/O error must escape the response rejection classifier.
        result.append(
            audit._validate(
                b"synthetic",
                {
                    "status": 200,
                    "content_type": "application/json",
                    "content_encoding": "absent",
                },
                1,
                validate,
            )
        )

    def run():
        try:
            writer.cooperative(transaction)
        except OSError as error:
            result.append(str(error))

    thread = threading.Thread(target=run)
    thread.start()
    assert entered.wait(1)
    sample = writer.submit(
        lambda: (_ for _ in ()).throw(OSError("SYNTHETIC_SAMPLE_WRITE_FAILURE")),
        periodic=True,
    )
    proceed.set()
    thread.join(1)
    assert not thread.is_alive()
    with pytest.raises(OSError, match="SYNTHETIC_SAMPLE_WRITE_FAILURE"):
        sample.result(1)
    assert result == ["PUBLIC_PROBE_EVIDENCE_WRITE_FAILED"]
    assert writer.failed.is_set() and stopped.is_set()
    with pytest.raises(c.Stage12Error):
        writer.submit(lambda: None)
    assert not (writer.root / "_WRITER_RELEASED.json").exists()
    writer.abort()

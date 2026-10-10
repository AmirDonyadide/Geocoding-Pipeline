from __future__ import annotations

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_operations as o
from safe_geocoding_pipeline.preprocessing.stages import s12_raw_packs as packs
from safe_geocoding_pipeline.preprocessing.stages import s12_response as r
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from stage12_synthetic import body


def sources(tmp_path, count):
    items = []
    for i in range(count):
        raw = body([]) + b" " * i
        path = tmp_path / f"fragment_{i}.zst"
        io.write(path, r.compress(raw))
        items.append((c.sha(str(i).encode()), path, len(raw), c.sha(raw)))
    return items


def test_pack_bounds_exact_replay_and_preserved_sources(tmp_path, monkeypatch):
    items = sources(tmp_path, 5)
    old = [io.read(row[1]) for row in items]
    monkeypatch.setattr(packs, "MAX_RESPONSES", 2)
    result = list(packs.pack(tmp_path / "packed", items))
    assert len(result) == 5
    assert len(list((tmp_path / "packed").iterdir())) == 3
    assert [io.read(row[1]) for row in items] == old
    for entry, source in zip(result, items, strict=True):
        path = tmp_path / "packed" / entry["raw_pack_key"]
        assert io.read(path.parent / "_SEALED") == b""
        physical = io.read(path)
        receipt = io.metadata(io.read(path.parent / "receipt.json"))
        assert receipt["physical_sha256"] == c.sha(physical).hex()
        assert receipt["codec_provider_version"]
        offset = entry["raw_frame_offset"]
        frame = physical[offset : offset + entry["raw_frame_length"]]
        assert r.decompress(frame, length=source[2], expected_hash=source[3]) == body(
            []
        ) + b" " * items.index(source)


def test_interrupted_pack_yields_no_adoptable_entries(tmp_path, monkeypatch):
    items = sources(tmp_path, 2)
    original = io.write

    def fail(path, data):
        if path.name == "_SEALED":
            raise OSError("invented fsync fault")
        original(path, data)

    monkeypatch.setattr(io, "write", fail)
    seen = []
    with pytest.raises(OSError):
        seen.extend(packs.pack(tmp_path / "failed", items))
    assert not seen
    assert not (tmp_path / "failed/pack_000001/_SEALED").exists()
    assert all(path.exists() for _, path, _, _ in items)


def test_corrupt_source_never_seals(tmp_path):
    items = sources(tmp_path, 1)
    execution, path, length, _ = items[0]
    with pytest.raises(c.Stage12Error):
        list(
            packs.pack(
                tmp_path / "failed", [(execution, path, length, c.sha(b"wrong"))]
            )
        )
    assert not list((tmp_path / "failed").iterdir())


def test_global_memory_reservation_precedes_admission():
    admission = o.Admission(o.Operations())
    admission.memory_capacity_bytes = admission.reservation_bytes
    admission.admit(0)
    with pytest.raises(c.Stage12Error, match="ADMISSION_NOT_READY"):
        admission.admit(1000)
    assert admission.active == 1
    admission.finish(1001, "SUCCESS_ZERO_CANDIDATES", 1001)
    assert admission.reserved_bytes == 0
    admission.admit(2000)

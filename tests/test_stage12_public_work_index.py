"""Exact bounded public lookup; no service, protected catalog or trusted cache."""

import copy
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_work_index as index
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from test_stage12_public_operations_v2 import inputs, offline  # noqa: F401


@pytest.mark.parametrize("count", [1, 128, 256, 257])
def test_source_bound_index_and_streaming_fallback(count):
    _, plan, _, rows, _ = inputs(count)
    reads = []

    def read(key):
        reads.append(key)
        return copy.deepcopy(rows[key - 1])

    value = index.WorkIndex(lambda: iter(rows), read, plan)
    assert (value.hashes is None) == (count > 256)
    if value.hashes is not None:
        assert len(value.hashes) <= 256
        assert all(type(x) is str and len(x) == 64 for x in value.hashes.values())
    assert value.row(count) == rows[-1]
    assert reads == ([] if count > 256 else [count])
    pairs = list(value.pairs(1))
    assert pairs == [(rows[0], row) for row in rows[1:]]
    value.verify()
    with pytest.raises(c.Stage12Error):
        value.row(count + 1)


@pytest.mark.parametrize(
    "mutation",
    ["edited", "swapped", "missing", "extra", "changed_manifest", "reader_only"],
)
def test_index_rejects_changed_original_work_or_reader(mutation):
    _, plan, _, rows, _ = inputs(3)
    source = copy.deepcopy(rows)
    value = index.WorkIndex(lambda: iter(source), lambda key: source[key - 1], plan)
    if mutation == "edited":
        source[1]["result_limit"] = 3
    elif mutation == "swapped":
        source[0], source[1] = source[1], source[0]
    elif mutation == "missing":
        source.pop()
    elif mutation == "extra":
        source.append(copy.deepcopy(source[-1]))
    elif mutation == "changed_manifest":
        plan["work_manifest_sha256"] = "0" * 64
    elif mutation == "reader_only":
        value.reader = lambda key: {**source[key - 1], "result_limit": 3}
        with pytest.raises(c.Stage12Error):
            value.row(1)
        return
    with pytest.raises((c.Stage12Error, IndexError)):
        value.verify()


@pytest.mark.parametrize("count", [1, 128, 129])
def test_bounded_ledger_matches_default_with_controls_retry_and_unknown(count):
    works = [
        {"work_id": i, "kind": "DATA" if i % 2 else "SERVICE_CONTROL"}
        for i in range(1, count + 1)
    ]
    events = []
    for row in works:
        key = row["work_id"]
        if (
            key % 5 == 0
        ):  # Unused/reserved work remains UNBEGUN for caller classification.
            continue
        events.append({"kind": "BEGIN_DURABLE", "body": {"work_id": key, "attempt": 1}})
        if key % 7 == 0:  # Unknown delivery remains unknown, never success.
            continue
        outcome = (
            "TECHNICAL_FAILURE_RETRYABLE"
            if key % 3 == 0
            else c.SUCCESS[0]
            if row["kind"] == "DATA"
            else "CONTROL_SUCCESS"
        )
        events.append(
            {
                "kind": "ATTEMPT_FINALIZED",
                "body": {
                    "work_id": key,
                    "attempt": 1,
                    "outcome": {"kind": row["kind"], "value": outcome},
                    "receipt_inventory_sha256": "a" * 64,
                    "retry_delay_ms": 500,
                },
            }
        )
    seen = []

    def receipt(work, event):
        seen.append((work["work_id"], event["attempt"]))

    expected = list(
        recovery.work_ledger(lambda: iter(works), lambda: iter(events), receipt)
    )
    first_seen = sorted(seen)
    seen.clear()
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from events

    actual = list(
        recovery.work_ledger(lambda: iter(works), source, receipt, batch_size=128)
    )
    assert actual == expected
    assert sorted(seen) == first_seen
    assert calls == (count + 127) // 128


@pytest.mark.parametrize(
    "bad",
    [
        "duplicate",
        "final_before_begin",
        "missing_receipt",
        "changed_prefix",
        "oversized_batch",
    ],
)
def test_bounded_ledger_rejects_invalid_evidence(bad):
    works = [{"work_id": i, "kind": "DATA"} for i in range(1, 130)]
    begin = {"kind": "BEGIN_DURABLE", "body": {"work_id": 1, "attempt": 1}}
    final = {
        "kind": "ATTEMPT_FINALIZED",
        "body": {
            "work_id": 1,
            "attempt": 1,
            "outcome": {"kind": "DATA", "value": c.SUCCESS[0]},
            "receipt_inventory_sha256": "a" * 64,
            "retry_delay_ms": None,
        },
    }
    events = [begin, final]
    if bad == "duplicate":
        events.append(final)
    if bad == "final_before_begin":
        events.reverse()
    calls = 0

    def source():
        nonlocal calls
        calls += 1
        yield from events
        if bad == "changed_prefix" and calls > 1:
            yield {"kind": "TEST_ONLY_CHANGED", "body": {}}

    def receipt(*_):
        if bad == "missing_receipt":
            raise c.Stage12Error("S12_CAPTURE_INCOMPLETE")

    with pytest.raises(c.Stage12Error):
        list(
            recovery.work_ledger(
                lambda: iter(works),
                source,
                receipt,
                batch_size=129 if bad == "oversized_batch" else 128,
            )
        )

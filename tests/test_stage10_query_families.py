"""Invented contexts only: challenge scientific boundaries and map-back."""

from __future__ import annotations

from typing import Any
import tempfile

import dataclasses
import io
import struct

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages.s10_query_evidence import FieldPolicy


class SyntheticTransform:
    asset_binding = b"a" * 32

    def transform(self, script: Any, value: Any) -> Any:
        # Explicit test double; exact ICU behavior has its own real-runtime tests.
        return value.replace("α", "a").replace("б", "b")


def context(
    tmp_path: Any,
    *,
    lines: Any = ("12 α road", "unit 5", "", ""),
    role: Any = "NATIVE",
    components: Any = None,
    country: Any = "DE",
    structured: Any = True,
) -> Any:
    if components is None:
        components = [("house_number", "12"), ("road", "α road"), ("unit", "unit 5")]
    rows = [
        {
            "stage08_component_ordinal": i,
            "stage08_raw_libpostal_label": label,
            "stage08_raw_libpostal_value": value,
        }
        for i, (label, value) in enumerate(components)
    ]

    def reader(reverse: Any) -> Any:
        yield from reversed(rows) if reverse else rows

    return f.QueryContext(
        b"u" * 32,
        b"i" * 32,
        b"s" * 32,
        b"r" * 32,
        role,
        b"c" * 32,
        " ".join(s for s in lines if s),
        lines,
        "".join("1" if s else "0" for s in lines),
        sum(bool(s) for s in lines),
        "PARSED_NONEMPTY",
        len(rows),
        reader,
        ("exampleville", "01234", "example region", "de"),
        "01234",
        "Exampleville",
        FieldPolicy(
            country,
            "Exampleville" if structured else None,
            None,
            (),
            ("INSUFFICIENT_TRUSTED_STRUCTURED_EVIDENCE",),
            (),
        ),
        {
            n: {
                "selector_id": n,
                "selected_count": 1,
                "selected_stream_sha256": bytes([i + 1]) * 32,
            }
            for i, n in enumerate(c.SELECTORS)
        },
        tmp_path,
    )


def decision(ctx: Any, family: Any, runtime: Any = None) -> Any:
    hypotheses, decisions = f.generate(ctx, runtime or SyntheticTransform())
    d = next(d for d in decisions if d["family"] == family)
    return d, next(
        (h for h in hypotheses if h["hypothesis_id"] == d["hypothesis_id"]), None
    )


def test_native_coexistence_reaches_five_without_chaining(tmp_path: Any) -> None:
    ctx = context(tmp_path)
    hypotheses, decisions = f.generate(ctx, SyntheticTransform())
    assert len(hypotheses) == 5 and len(decisions) == 6
    assert {d["family"] for d in decisions if d["eligibility_state"] == "ELIGIBLE"} == {
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "Q6",
    }
    assert sorted(h["generation_rank"] for h in hypotheses) == [1, 2, 3, 4, 5]
    assert decision(ctx, "Q5")[1]["intent"]["text"] == "12 α road"
    assert decision(ctx, "Q6")[1]["intent"]["text"] == "12 a road unit 5"
    assert all(h["intent"]["text"] != "12 a road" for h in hypotheses)
    assert {d["family"] for d in decisions} == set(c.FAMILIES)


def test_standard_maximum_four_source_row_reaches_nine(tmp_path: Any) -> None:
    native = context(tmp_path)
    standard = dataclasses.replace(native, role="STANDARD")
    n, nd = f.generate(native, SyntheticTransform())
    s, sd = f.generate(standard, SyntheticTransform())
    assert len(n) == 5 and len(s) == 4 and len(n + s) == 9 < c.ROW_CEILING
    assert len({h["query_context_id"] for h in n + s}) == 2
    assert len({h["hypothesis_id"] for h in n + s}) == 9
    assert len({h["representation_fingerprint"] for h in n + s}) < 9
    assert all(d["hypothesis_id"] is None for d in sd if d["family"] in ("Q2", "Q6"))
    assert next(d for d in nd if d["family"] == "Q1")["hypothesis_id"] is None


@pytest.mark.parametrize(
    "lines",
    [
        ("12 road", "", "", ""),
        ("12 road", "unit 5", "", ""),
        ("", "12 road", "", "unit 5"),
        ("12 road", "", "unit 5", ""),
        ("12\nroad", "unit 5", "", ""),
        ("12 road", "unit 5", "unit 5", ""),
    ],
)
def test_boundary_exact_slots_lf_and_lineage(tmp_path: Any, lines: Any) -> None:
    ctx = context(tmp_path, lines=lines, components=[])
    d, h = decision(ctx, "Q3")
    assert h["intent"]["text"] == "\n".join(s for s in lines if s)
    assert (
        next(s for s in d["lineage"] if s["selector_id"] == "SOURCE_LINES_V1")
        == ctx.certificates["SOURCE_LINES_V1"]
    )
    assert (d["membership_state"] == "CONVERGENT_MEMBER") == (
        sum(bool(s) for s in lines) == 1
    )
    assert ctx.lines == lines


def test_same_flat_candidate_different_boundaries_and_rows(tmp_path: Any) -> None:
    a = context(tmp_path, lines=("12 road", "unit 5", "", ""), components=[])
    b = context(tmp_path, lines=("12 road unit 5", "", "", ""), components=[])
    b = dataclasses.replace(b, source_id=b"b" * 32)
    assert a.text == b.text and a.candidate_id == b.candidate_id
    assert a.identifier != b.identifier
    assert decision(a, "Q3")[1]["intent"] != decision(b, "Q3")[1]["intent"]


@pytest.mark.parametrize(
    "role,baseline,unavailable", [("STANDARD", "Q1", "Q2"), ("NATIVE", "Q2", "Q1")]
)
def test_role_exact_baseline_and_country_independence(
    tmp_path: Any, role: Any, baseline: Any, unavailable: Any
) -> None:
    ctx = context(tmp_path, role=role)
    assert decision(ctx, baseline)[1]["intent"]["text"] == ctx.text
    assert (
        decision(ctx, unavailable)[0]["primary_reason"]
        == "REQUIRED_SOURCE_REPRESENTATION_UNAVAILABLE"
    )
    other = dataclasses.replace(
        ctx, source_id=b"z" * 32, fields=dataclasses.replace(ctx.fields, country="US")
    )
    assert decision(ctx, baseline)[1]["intent"]["boundary_country"] == "DE"
    assert decision(other, baseline)[1]["intent"]["boundary_country"] == "US"
    unavailable_country = dataclasses.replace(
        other, fields=dataclasses.replace(other.fields, country=None)
    )
    assert f.generate(unavailable_country, SyntheticTransform())[0] == []
    assert decision(ctx, baseline)[1]["intent"]["text"] == ctx.text


@pytest.mark.parametrize(
    "marker,label",
    [
        ("unit 5", "unit"),
        ("suite 5a", "unit"),
        ("apt 05", "unit"),
        ("apartment 7", "unit"),
        ("floor 2", "level"),
        ("level 0", "level"),
    ],
)
def test_whole_unit_level_only(tmp_path: Any, marker: Any, label: Any) -> None:
    ctx = context(
        tmp_path,
        lines=("12 example road", marker, "", ""),
        components=[("road", "12 example road"), (label, marker)],
    )
    d, h = decision(ctx, "Q5")
    assert h["intent"]["text"] == "12 example road"
    assert d["removed_lines"][0]["source_slot"] == 2
    assert d["removed_lines"][0]["category"] == label.upper()
    assert decision(ctx, "Q2")[1]["intent"]["text"] == ctx.text


@pytest.mark.parametrize(
    "marker",
    [
        "unit 5 example road",
        "building unit 5",
        "exampleville unit 5",
        "01234 unit 5",
        "de unit 5",
        "12 unit 5",
        "unit 5-7",
        "unit  5",
        "unit. 5",
    ],
)
def test_mixed_content_never_deleted(tmp_path: Any, marker: Any) -> None:
    ctx = context(
        tmp_path,
        lines=("12 example road", marker, "", ""),
        components=[("road", "12 example road"), ("unit", marker)],
    )
    d, h = decision(ctx, "Q5")
    assert h is None and d["primary_reason"] == "FAMILY_INELIGIBLE"
    assert decision(ctx, "Q2")[1]["intent"]["text"] == ctx.text


def test_missing_wrong_and_ambiguous_corroboration_abstain(tmp_path: Any) -> None:
    original = context(tmp_path)
    for components in [
        [("road", "12 α road")],
        [("road", "12 α road"), ("house", "unit 5")],
        [("road", "12 α road"), ("unit", "")],
    ]:
        d, h = decision(context(tmp_path, components=components), "Q5")
        assert h is None and d["primary_reason"] == "PARSER_EVIDENCE_UNUSABLE"
    ambiguous = context(
        tmp_path,
        lines=("12 α road 12", "unit 5", "", ""),
        components=[("house_number", "12"), ("unit", "unit 5")],
    )
    d, h = decision(ambiguous, "Q5")
    assert h is None and d["primary_reason"] == "UNIT_ALIGNMENT_AMBIGUOUS"
    assert decision(original, "Q5")[1] is not None


@pytest.mark.parametrize("value", ["unit 5", "5", "unit"])
def test_source_field_veto(tmp_path: Any, value: Any) -> None:
    ctx = dataclasses.replace(
        context(tmp_path), source_lower_geography=(value, "", "", "de")
    )
    d, h = decision(ctx, "Q5")
    assert h is None and d["primary_reason"] == "UNIT_SOURCE_FIELD_CONFLICT"


def test_remove_all_corroborated_lines_once_and_prevent_empty(tmp_path: Any) -> None:
    ctx = context(
        tmp_path,
        lines=("12 α road", "unit 5", "level 2", ""),
        components=[("road", "12 α road"), ("unit", "unit 5"), ("level", "level 2")],
    )
    d, h = decision(ctx, "Q5")
    assert h["intent"]["text"] == "12 α road" and len(d["removed_lines"]) == 2
    empty = context(
        tmp_path,
        lines=("unit 5", "level 2", "", ""),
        components=[("unit", "unit 5"), ("level", "level 2")],
    )
    d, h = decision(empty, "Q5")
    assert h is None and d["primary_reason"] == "EMPTY_RESULT_AFTER_TRANSFORMATION"


def test_convergence_retains_families_and_complete_intent(tmp_path: Any) -> None:
    ctx = context(tmp_path, lines=("12 α road", "", "", ""), components=[])
    h, d = f.generate(ctx, SyntheticTransform())
    full = next(x for x in d if x["family"] == "Q2")
    boundary = next(x for x in d if x["family"] == "Q3")
    assert full["hypothesis_id"] == boundary["hypothesis_id"]
    assert boundary["membership_state"] == "CONVERGENT_MEMBER"
    assert sum(x["membership_state"] == "FIRST_MEMBER" for x in d) == len(h)
    q4 = next(x for x in d if x["family"] == "Q4")
    assert q4["hypothesis_id"] != full["hypothesis_id"]


def test_reproducible_framing_order_and_identity(tmp_path: Any) -> None:
    ctx = context(tmp_path)
    assert f.generate(ctx, SyntheticTransform()) == f.generate(
        ctx, SyntheticTransform()
    )
    expected = (
        b"SAFE:test:v1\0"
        + struct.pack(">Q", 3)
        + b"\x00\x01"
        + struct.pack(">Q", 2)
        + b"ab\x02"
        + struct.pack(">Q", 2)
        + b"cd"
    )
    import hashlib

    assert c.identity("test:v1", None, "ab", b"cd") == hashlib.sha256(expected).digest()
    assert c.identity("test:v1", "ab", "c") != c.identity("test:v1", "a", "bc")
    text = c.full_intent("12 example road", "DE")
    other = dict(text, boundary_country="US")
    assert c.intent_fingerprint(text) != c.intent_fingerprint(other)


def test_overflow_and_corruption_fail_without_values(
    tmp_path: Any, monkeypatch: Any
) -> None:
    ctx = context(tmp_path)
    monkeypatch.setattr(c, "CONTEXT_CEILING", 4)
    with pytest.raises(c.Stage10Error, match="^STAGE10_ENGINEERING_CEILING_VIOLATION$"):
        f.generate(ctx, SyntheticTransform())
    with pytest.raises(
        c.Stage10Error, match="^STAGE10_SOURCE_BOUNDARY_LINEAGE_INVALID$"
    ):
        f.generate(dataclasses.replace(ctx, line_mask="0000"), SyntheticTransform())
    with pytest.raises(c.Stage10Error, match="^STAGE10_SELECTOR_SET_INVALID$"):
        f.generate(dataclasses.replace(ctx, certificates={}), SyntheticTransform())


def test_alignment_spills_offsets_instead_of_collecting_components(
    tmp_path: Any, monkeypatch: Any
) -> None:
    buffers = []

    class Tracked(io.BytesIO):
        def close(self) -> None:
            buffers.append(self.getvalue())
            super().close()

    monkeypatch.setattr(tempfile, "TemporaryFile", lambda **kwargs: Tracked())
    ctx = context(tmp_path)
    assert decision(ctx, "Q5")[1] is not None
    assert len(buffers[0]) == ctx.component_count * 24


def test_large_component_stream_has_bounded_python_memory(tmp_path: Any) -> None:
    import tracemalloc

    count = 20000
    prefix = "12 " + ("a " * count).rstrip()
    text = prefix + " unit 5"
    ctx = context(tmp_path)

    def reader(reverse: Any) -> Any:
        def row(ordinal: Any, label: Any, value: Any) -> Any:
            return {
                "stage08_component_ordinal": ordinal,
                "stage08_raw_libpostal_label": label,
                "stage08_raw_libpostal_value": value,
            }

        if reverse:
            yield row(count + 1, "unit", "unit 5")
            for ordinal in range(count, 0, -1):
                yield row(ordinal, "road", "a")
            yield row(0, "house_number", "12")
        else:
            yield row(0, "house_number", "12")
            for ordinal in range(1, count + 1):
                yield row(ordinal, "road", "a")
            yield row(count + 1, "unit", "unit 5")

    ctx = dataclasses.replace(
        ctx,
        text=text,
        lines=(prefix, "unit 5", "", ""),
        component_count=count + 2,
        components=reader,
    )
    tracemalloc.start()
    try:
        result = f.strip_units(ctx)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result.intent is not None
    assert result.intent["text"] == prefix
    assert peak < 2 * 1024 * 1024

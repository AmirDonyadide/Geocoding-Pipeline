"""Public/synthetic ICU verification, separate from any protected execution."""

from __future__ import annotations

from typing import Any
import ctypes
import sys

import dataclasses
import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stages import s10_query_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s10_query_families as f
from safe_geocoding_pipeline.preprocessing.stages import s10_query_transliteration as t
from test_stage10_query_families import context, decision


@pytest.fixture(scope="module")
def runtime_paths() -> Any:
    path = os.environ.get("STAGE10_TEST_RUNTIME_ROOT")
    if path is None:
        pytest.skip("Exact public ICU build required; set STAGE10_TEST_RUNTIME_ROOT")
    root = Path(path)
    repository = Path(__file__).resolve().parents[1]
    return (
        root,
        root / "runtime_build_lock.json",
        repository / "docs/scientific_assets" / t.SPEC_NAME,
        repository / "src/safe_geocoding_pipeline/preprocessing/stage10_icu_bridge.cpp",
    )


@pytest.fixture(scope="module")
def runtime(runtime_paths: Any) -> Any:
    instance = t.ICUTransliterator(*runtime_paths)
    yield instance
    instance.close()


@pytest.mark.parametrize("script,value,expected", t.SYNTHETIC_VECTORS)
def test_pinned_real_runtime_vectors(
    runtime: Any, script: Any, value: Any, expected: Any
) -> None:
    assert runtime.transform(script, value) == expected
    assert runtime.transform(script, value) == expected


@pytest.mark.parametrize(
    "text,target",
    [
        ("α", "Greek"),
        ("б", "Cyrillic"),
        ("Latin α 12", "Greek"),
        ("Latin б 12", "Cyrillic"),
        ("αб", None),
        ("Latin", None),
        ("ع", None),
        ("漢", None),
        ("α\u0301", "Greek"),
        ("α \u0301", None),
        ("a\u0301 α", None),
        ("\u0301α", None),
        ("α\u0378", None),
        ("α\u05b0", None),
    ],
)
def test_script_and_inherited_mark_gates(text: Any, target: Any) -> None:
    assert t.eligible_script(text, check_marks=True) == target


def test_q6_real_coexists_and_keeps_native(runtime: Any, tmp_path: Any) -> None:
    ctx = context(tmp_path)
    h, d = f.generate(ctx, runtime)
    assert len(h) == 5
    assert {v["family"] for v in d if v["eligibility_state"] == "ELIGIBLE"} == {
        "Q2",
        "Q3",
        "Q4",
        "Q5",
        "Q6",
    }
    assert decision(ctx, "Q2", runtime)[1]["intent"]["text"] == "12 α road unit 5"
    assert decision(ctx, "Q6", runtime)[1]["intent"]["text"] == "12 a road unit 5"


def test_nfc_order_and_transform_trace(runtime: Any, tmp_path: Any) -> None:
    ctx = context(tmp_path, lines=("12 α\u0301 road", "unit 5", "", ""), components=[])
    d, h = decision(ctx, "Q6", runtime)
    assert h is not None
    assert [s["transform_id"] for s in d["transformations"]] == [
        "NFC_U16_V1",
        "ICU_GREK_LATN_77_1",
        "NFC_U16_V1",
    ]
    assert all(
        s["transform_asset_binding"] == runtime.asset_binding
        for s in d["transformations"]
    )
    assert decision(ctx, "Q2", runtime)[1]["intent"]["text"] == ctx.text


@pytest.mark.parametrize(
    "output,reason",
    [
        ("", "EMPTY_RESULT_AFTER_TRANSFORMATION"),
        ("ع", "TRANSLITERATION_UNSUPPORTED_OUTPUT"),
    ],
)
def test_output_abstention_has_trace_without_hypothesis(
    tmp_path: Any, output: Any, reason: Any
) -> None:
    class Fake:
        asset_binding = b"a" * 32

        def transform(self, script: Any, value: Any) -> Any:
            return output

    d, h = decision(context(tmp_path), "Q6", Fake())
    assert h is None and d["primary_reason"] == reason
    assert len(d["transformations"]) == 3


def test_unchanged_precedes_unsupported_residual_gate(tmp_path: Any) -> None:
    class Unchanged:
        asset_binding = b"a" * 32

        def transform(self, script: Any, value: Any) -> Any:
            return value

    ctx = context(tmp_path)
    d, h = decision(ctx, "Q6", Unchanged())
    baseline = decision(ctx, "Q2", Unchanged())[1]
    assert d["membership_state"] == "CONVERGENT_MEMBER"
    assert d["primary_reason"] == "EXACT_SEMANTIC_DUPLICATE"
    assert h["hypothesis_id"] == baseline["hypothesis_id"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("icu_version", "78.3"),
        ("unicode_version", "17.0.0"),
        ("cldr_version", "48"),
        ("source_archive_sha256", "0" * 64),
        ("bridge_source_sha256", "0" * 64),
        ("specification_sha256", "0" * 64),
        ("synthetic_vectors", []),
    ],
)
def test_lock_mutations_fail_before_loading(
    runtime_paths: Any, tmp_path: Any, monkeypatch: Any, key: Any, value: Any
) -> None:
    root, lock, spec, bridge = runtime_paths
    data = c.read_json(lock)
    data[key] = value
    altered = tmp_path / "altered-lock.json"
    altered.write_bytes(c.canonical(data))

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("library must not load")

    monkeypatch.setattr(ctypes, "CDLL", forbidden)
    with pytest.raises(c.Stage10Error, match="STAGE10_"):
        t.ICUTransliterator(root, altered, spec, bridge)


def test_library_data_hash_mutation_fails_before_loading(
    runtime_paths: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    root, lock, spec, bridge = runtime_paths
    data = c.read_json(lock)
    data["artifacts"][-1]["sha256"] = "0" * 64
    altered = tmp_path / "altered-lock.json"
    altered.write_bytes(c.canonical(data))
    monkeypatch.setattr(
        ctypes, "CDLL", lambda *a, **k: pytest.fail("load before data validation")
    )
    with pytest.raises(c.Stage10Error, match="^STAGE10_RUNTIME_ASSET_HASH_MISMATCH$"):
        t.ICUTransliterator(root, altered, spec, bridge)


def test_runtime_override_and_native_role_prohibited(
    runtime_paths: Any, tmp_path: Any, monkeypatch: Any
) -> None:
    monkeypatch.setenv("ICU_DATA", "synthetic-untrusted-path")
    with pytest.raises(c.Stage10Error, match="^STAGE10_ICU_DATA_OVERRIDE_PROHIBITED$"):
        t.ICUTransliterator(*runtime_paths)
    ctx = dataclasses.replace(context(tmp_path), role="STANDARD")
    assert decision(ctx, "Q6")[1] is None


def test_exact_python_runtime_guard_fails(monkeypatch: Any) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 14, 7))
    with pytest.raises(c.Stage10Error, match="^STAGE10_EXACT_RUNTIME_REQUIRED$"):
        c.require_runtime()

from __future__ import annotations

import html
from pathlib import Path

import pytest

from safe_geocoding_pipeline.preprocessing.stage07_v2_readiness_cli import main
from safe_geocoding_pipeline.preprocessing.stages.s07_v2_readiness_audit import (
    ReadinessAuditConfig,
    Stage07V2ReadinessAuditError,
    _candidate_id_fingerprint,
    _iter_qualitative_html_rows,
)


def _config(tmp_path: Path, **changes: object) -> ReadinessAuditConfig:
    values: dict[str, object] = {
        "stage06_fixed500_path": tmp_path / "stage06.parquet",
        "stage07_fixed500_path": tmp_path / "stage07.parquet",
        "qualitative_selection_path": tmp_path / "selection.parquet",
        "classifications_path": tmp_path / "classifications.json",
        "root_cause_path": tmp_path / "root.parquet",
        "eligibility_path": tmp_path / "eligibility.parquet",
        "qualitative_html_path": tmp_path / "review.html",
        "output_directory": tmp_path / "output",
        "execution_git_sha": "1" * 40,
        "authoritative_development": False,
    }
    values.update(changes)
    return ReadinessAuditConfig(**values)  # type: ignore[arg-type]


def test_candidate_set_fingerprint_is_order_invariant_and_domain_bound() -> None:
    first = bytes.fromhex("01" * 32)
    second = bytes.fromhex("02" * 32)
    assert _candidate_id_fingerprint({first, second}) == _candidate_id_fingerprint(
        {second, first}
    )
    assert _candidate_id_fingerprint({first}) != _candidate_id_fingerprint({second})


def test_config_rejects_holdout(tmp_path: Path) -> None:
    with pytest.raises(Stage07V2ReadinessAuditError, match="HOLDOUT"):
        _config(tmp_path, output_directory=tmp_path / "HOLDOUT" / "output").validate()


def test_cli_requires_every_protected_input() -> None:
    with pytest.raises(SystemExit) as raised:
        main([])
    assert raised.value.code == 2


def _review_html(*, extra_section: bool = False, first_component_count: int = 2) -> str:
    sections: list[str] = []
    for order in range(1, 121):
        candidate = "synthetic & <candidate>" if order == 1 else f"synthetic {order}"
        values = (
            tuple(
                ("road", f"fragment-{index}") for index in range(first_component_count)
            )
            if order == 1
            else (("road", f"synthetic {order}"),)
        )
        rows = "".join(
            f"<tr><td>{index}</td><td>{html.escape(label)}</td>"
            f"<td class='value'>{html.escape(value)}</td></tr>"
            for index, (label, value) in enumerate(values, start=1)
        )
        sections.append(
            f"<section data-order='{order}'><h2>Review {order}</h2>"
            "<h3>Exact Stage 6 candidate</h3><div class='candidate'>"
            f"{html.escape(candidate)}</div>"
            "<h3>Ordered libpostal components</h3><table><thead><tr><th>#</th>"
            "<th>label</th><th>value</th></tr></thead><tbody>"
            f"{rows}</tbody></table></section>"
        )
    if extra_section:
        sections.append("<section data-order='121'></section>")
    return "<!doctype html><html><body>" + "".join(sections) + "</body></html>"


def test_existing_qualitative_html_is_the_only_semantic_input(tmp_path: Path) -> None:
    path = tmp_path / "review.html"
    path.write_text(_review_html(), encoding="utf-8")

    rows = list(_iter_qualitative_html_rows(path))

    assert len(rows) == 120
    assert rows[0].review_order == 1
    assert rows[0].candidate == "synthetic & <candidate>"
    assert [(item.label, item.value) for item in rows[0].components] == [
        ("road", "fragment-0"),
        ("road", "fragment-1"),
    ]
    assert rows[-1].review_order == 120


def test_qualitative_html_rejects_unknown_additional_review(tmp_path: Path) -> None:
    path = tmp_path / "review.html"
    path.write_text(_review_html(extra_section=True), encoding="utf-8")

    with pytest.raises(Stage07V2ReadinessAuditError, match="additional"):
        list(_iter_qualitative_html_rows(path))


def test_qualitative_html_extractor_handles_large_component_surface(
    tmp_path: Path,
) -> None:
    path = tmp_path / "review.html"
    path.write_text(_review_html(first_component_count=20_000), encoding="utf-8")

    rows = list(_iter_qualitative_html_rows(path))

    assert len(rows[0].components) == 20_000
    assert rows[0].components[-1].value == "fragment-19999"

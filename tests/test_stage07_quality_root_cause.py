from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages.s07_libpostal_adapter import (
    LibpostalComponent,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parsing import stage07_schema
from safe_geocoding_pipeline.preprocessing.stages import s07_quality_root_cause
from safe_geocoding_pipeline.preprocessing.stages.s07_quality_root_cause import (
    QualityDiagnosticConfig,
    Stage07QualityDiagnosticError,
    _controlling_conclusion,
    _reason_codes,
    _stage8_recoverability,
)


def test_abstract_reason_taxonomy_distinguishes_parser_and_upstream_causes() -> None:
    parser = _reason_codes(
        "Severe wrong label and mid-word split boundary.", "CLEAR_MISPARSE"
    )
    assert parser == {
        "TRUE_LIBPOSTAL_LABEL_ERROR",
        "TRUE_LIBPOSTAL_BOUNDARY_ERROR",
    }
    upstream = _reason_codes(
        "Upstream transliteration and multi-record concatenation.",
        "QUESTIONABLE_PARSE",
    )
    assert upstream == {
        "TRANSLITERATION_OR_ROMANIZATION_DAMAGE",
        "MULTI_ADDRESS_OR_MULTI_RECORD_INPUT",
        "AMBIGUOUS_BUT_INFORMATION_PRESERVED",
    }


def test_questionable_without_true_parser_error_remains_ambiguous() -> None:
    assert _reason_codes("Uncertain interpretation.", "QUESTIONABLE_PARSE") == {
        "AMBIGUOUS_BUT_INFORMATION_PRESERVED"
    }


def test_fixed_stage8_mapping_cannot_repair_true_parser_or_upstream_damage() -> None:
    assert (
        _stage8_recoverability(
            comment="Wrong label.", codes={"TRUE_LIBPOSTAL_LABEL_ERROR"}
        )
        == "NOT_SAFELY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
    )
    assert (
        _stage8_recoverability(
            comment="Upstream transliteration damage.",
            codes={"TRANSLITERATION_OR_ROMANIZATION_DAMAGE"},
        )
        == "UPSTREAM_INPUT_REQUIRES_NON_STAGE8_REPAIR"
    )


def test_controlling_conclusion_is_derived_from_mixed_evidence() -> None:
    records: list[dict[str, object]] = [
        {
            "root_cause_codes": [
                "TRUE_LIBPOSTAL_BOUNDARY_ERROR",
                "SCRIPT_SPECIFIC_PARSER_WEAKNESS",
            ],
            "upstream_cause_indicated": False,
            "stage8_recoverability_assessment": (
                "NOT_SAFELY_RECOVERABLE_WITH_FIXED_LABEL_MAPPING"
            ),
        },
        {
            "root_cause_codes": ["AMBIGUOUS_BUT_INFORMATION_PRESERVED"],
            "upstream_cause_indicated": False,
            "stage8_recoverability_assessment": "INCONCLUSIVE",
        },
    ]
    assert (
        _controlling_conclusion(records)
        == "MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE"
    )


def test_quality_diagnostic_rejects_holdout_and_empty_registry() -> None:
    common = dict(
        selection_path=Path("selection.parquet"),
        classifications_path=Path("classifications.json"),
        comments_path=Path("comments.json"),
        stage07_registry_paths=(Path("registry.parquet"),),
        output_directory=Path("output"),
        execution_git_sha="a" * 40,
        production=False,
    )
    QualityDiagnosticConfig(**common).validate()
    with pytest.raises(Stage07QualityDiagnosticError, match="HOLDOUT"):
        QualityDiagnosticConfig(
            **{**common, "output_directory": Path("HOLDOUT") / "output"}
        ).validate()
    with pytest.raises(Stage07QualityDiagnosticError, match="REGISTRY_ABSENT"):
        QualityDiagnosticConfig(**{**common, "stage07_registry_paths": ()}).validate()


def test_quality_launcher_uses_clean_bundle_view_without_resource_cap() -> None:
    repository = Path(__file__).resolve().parents[1]
    script = (
        repository / "cluster/goethe_nhr/stage07_quality_root_cause.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --mem=180G" in script
    assert "one_synchronous_supervised_child" in script
    assert "PYTHONDONTWRITEBYTECODE=1" in script
    assert "SOURCE_PARSER_BUNDLE_ROOT" in script
    assert "parser_bundle_view_excludes_runtime_cache=true" in script
    assert "source_parser_bundle_modified=false" in script
    assert "__pycache__" in script
    assert "cp --reflink=auto --preserve=mode,timestamps" in script
    assert "RLIMIT_AS" not in script
    assert "setrlimit" not in script
    assert "ulimit -v" not in script


def test_quality_diagnostic_publishes_only_protected_technical_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = [index.to_bytes(32, "big") for index in range(1, 121)]
    selection_path = tmp_path / "selection.parquet"
    pq.write_table(
        pa.table(
            {
                "review_order": pa.array(range(1, 121), type=pa.uint32()),
                "stage06_exact_candidate_id": pa.array(ids, type=pa.binary(32)),
                "selection_reasons": pa.array(
                    [["baseline"] for _ in ids], type=pa.list_(pa.string())
                ),
            }
        ),
        selection_path,
        write_page_checksum=True,
    )
    selection_path.chmod(0o600)
    synthetic_selection_fingerprint = s07_quality_root_cause._selection_fingerprint(
        pq.read_table(selection_path)
    )
    monkeypatch.setattr(
        s07_quality_root_cause,
        "SELECTION_FINGERPRINT",
        synthetic_selection_fingerprint,
    )
    classifications_path = tmp_path / "classifications.json"
    comments_path = tmp_path / "comments.json"
    classifications = []
    comments = []
    for review_order in range(1, 121):
        classification = (
            "CLEAR_MISPARSE"
            if review_order <= 11
            else "QUESTIONABLE_PARSE"
            if review_order <= 18
            else "PLAUSIBLE_PARSE"
        )
        classifications.append(
            {"review_order": review_order, "classification": classification}
        )
        comments.append(
            {
                "review_order": review_order,
                "classification": classification,
                "comment": (
                    "Severe wrong label."
                    if classification == "CLEAR_MISPARSE"
                    else "Uncertain interpretation."
                ),
            }
        )
    classifications_path.write_text(
        json.dumps(
            {
                "selection_fingerprint": synthetic_selection_fingerprint,
                "classifications": classifications,
            }
        ),
        encoding="utf-8",
    )
    comments_path.write_text(json.dumps(comments), encoding="utf-8")
    classifications_path.chmod(0o600)
    comments_path.chmod(0o600)
    registry_path = tmp_path / "registry.parquet"
    candidates = {
        candidate_id: f"synthetic road {index}"
        for index, candidate_id in enumerate(ids, 1)
    }
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "stage06_exact_candidate_id": candidate_id,
                    "stage06_candidate_lower": candidate,
                    "stage06_occurrence_count": 1,
                    "stage06_standard_occurrence_count": 1,
                    "stage06_native_occurrence_count": 0,
                    "stage07_parse_status": "PARSED_NONEMPTY",
                    "stage07_libpostal_components": [
                        {"label": "road", "value": candidate}
                    ],
                }
                for candidate_id, candidate in candidates.items()
            ],
            schema=stage07_schema(),
        ),
        registry_path,
        write_page_checksum=True,
    )
    registry_path.chmod(0o600)

    class FakeReference:
        def distinctive_scripts(self, value: str) -> set[str]:
            del value
            return {"Latin"}

    class FakeSupervisor:
        first_attempt_crashes = 0
        worker_restarts = 0

        def __enter__(self) -> FakeSupervisor:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def parse(self, candidate: str) -> SimpleNamespace:
            parsed_candidates.append(candidate)
            return SimpleNamespace(
                status="PARSED_NONEMPTY",
                components=(LibpostalComponent(label="road", value=candidate),),
            )

    parsed_candidates: list[str] = []
    monkeypatch.setattr(s07_quality_root_cause, "_scripts", FakeReference)
    monkeypatch.setattr(s07_quality_root_cause, "SupervisedParser", FakeSupervisor)

    output = tmp_path / "diagnostic"
    aggregate = s07_quality_root_cause.run_quality_root_cause_diagnostic(
        QualityDiagnosticConfig(
            selection_path=selection_path,
            classifications_path=classifications_path,
            comments_path=comments_path,
            stage07_registry_paths=(registry_path,),
            output_directory=output,
            execution_git_sha="a" * 40,
            production=False,
        )
    )
    assert aggregate["cases"] == 18
    assert aggregate["deterministic_exact_reparse"] == 18
    assert parsed_candidates == list(candidates.values())[:18]
    assert aggregate["information_lost_from_stage07_row"] == 0
    assert (
        aggregate["controlling_conclusion"]
        == "MIXED_ROOT_CAUSES_REQUIRING_TARGETED_STAGE07_DESIGN_CHANGE"
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert not list(tmp_path.glob(".diagnostic.partial.*"))
    table_path = output / "stage07_quality_root_cause_cases.parquet"
    assert stat.S_IMODE(table_path.stat().st_mode) == 0o600
    assert "stage06_candidate_lower" not in pq.read_schema(table_path).names
    aggregate_text = (output / "stage07_quality_root_cause_aggregate.json").read_text(
        encoding="utf-8"
    )
    assert all(candidate not in aggregate_text for candidate in candidates.values())

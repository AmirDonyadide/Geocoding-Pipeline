from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from phase03_helpers import engine, phase02_row
from safe_geocoding_pipeline.phase03.constants import (
    MANUAL_REVIEW_REASON_CODES_VERSION,
    PARSER_VERSION_V2_1,
    PARSER_VERSION_V3_1,
    PARSER_VERSION_V3_2,
)
from safe_geocoding_pipeline.phase03.development_comparison import (
    compare_development_parser_v2_1_v3_2_outputs,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema
from safe_geocoding_pipeline.phase03.targeted_experiment_review import (
    TARGETED_LABEL_FIELDS,
    TARGETED_LABEL_VOCABULARY_VERSION,
    TARGETED_REVIEW_SCHEMA_VERSION,
    targeted_review_context_schema,
    targeted_review_label_schema,
)
from safe_geocoding_pipeline.phase03.targeted_review_population import file_sha256
from safe_geocoding_pipeline.phase03.targeted_v3_2_evaluation import (
    V3_2_REUSE_REPORT_VERSION,
    V3_2_SCORE_REPORT_VERSION,
    evaluate_targeted_v3_2_label_reuse,
)

_ITERATION = (
    "phase03_development_country_method_repair_20260816T001155Z_1749448_e4a47253"
)


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-v3-2:{index}".encode()).digest()


def _review_id(identity: bytes) -> str:
    encoded = _ITERATION.encode()
    return hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_parser_v3_targeted_review_id_v1\0"
        + len(encoded).to_bytes(8, "big")
        + encoded
        + identity
    ).hexdigest()


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _row(index: int, raw: str) -> dict[str, Any]:
    return phase02_row(
        id=f"fictional-provider-{index}",
        stable_source_row_id_v1=_identity(index),
        source_logical_record_number=index + 1,
        street_address_line_1=raw,
        postcode="12345",
        city="Fiction City",
        region_in_country="Fiction Region",
        country_iso_code="XZ",
    )


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        compression="zstd",
        compression_level=3,
        version="2.4",
        data_page_version="1.0",
        write_statistics=False,
        write_page_checksum=True,
    )
    path.chmod(0o600)


def _label(identity: bytes, *, correct: bool) -> dict[str, Any]:
    values = {
        "street_label": "CORRECT" if correct else "INCORRECT",
        "house_number_label": "CORRECT" if correct else "INCORRECT",
        "joint_street_house_label": "CORRECT" if correct else "INCORRECT",
        "residual_role_label": "UNKNOWN_RESIDUAL",
        "candidate_support_label": "SUPPORTED" if correct else "NOT_SUPPORTED",
        "blind_parse_comparison_label": (
            "PARSE_A_CORRECT_ONLY" if correct else "BOTH_INCORRECT"
        ),
        "parser_overreach_label": "ABSENT" if correct else "PRESENT",
        "missed_information_label": "ABSENT",
        "overall_parse_acceptability_label": (
            "ACCEPTABLE" if correct else "NOT_ACCEPTABLE"
        ),
    }
    assert set(values) == set(TARGETED_LABEL_FIELDS)
    return {
        "hashed_review_id": _review_id(identity),
        "experiment_iteration": _ITERATION,
        "reviewer_id": "Targeted-R01",
        "review_round": 1,
        "is_independent_review": True,
        "assignment_role": "PRIMARY",
        **values,
        "reason_codes": ["CORRECT_AS_IS" if correct else "FALSE_POSITIVE_EXTRACTION"],
        "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
        "label_vocabulary_version": TARGETED_LABEL_VOCABULARY_VERSION,
        "label_schema_version": TARGETED_REVIEW_SCHEMA_VERSION,
    }


def _inputs(tmp_path: Path) -> tuple[dict[str, Path], tuple[str, ...]]:
    tmp_path.chmod(0o700)
    source = [
        _row(0, "Example Street 12 Annex"),
        _row(1, "Annex 12 Example Street"),
    ]
    results: dict[str, list[Any]] = {}
    for name, version in (
        ("baseline", PARSER_VERSION_V2_1),
        ("historical", PARSER_VERSION_V3_1),
        ("narrowed", PARSER_VERSION_V3_2),
    ):
        root = tmp_path / name
        root.mkdir()
        parser = engine(root, parser_version=version)
        results[name] = [parser.transform(row) for row in source]
    paths = {
        "baseline_core": tmp_path / "baseline-core.parquet",
        "baseline_evidence": tmp_path / "baseline-evidence.parquet",
        "v3_2_core": tmp_path / "v3-2-core.parquet",
        "v3_2_evidence": tmp_path / "v3-2-evidence.parquet",
    }
    _write_parquet(
        paths["baseline_core"],
        [item.core_row for item in results["baseline"]],
        core_schema(),
    )
    _write_parquet(
        paths["baseline_evidence"],
        [row for item in results["baseline"] for row in item.evidence_rows],
        evidence_schema(),
    )
    _write_parquet(
        paths["v3_2_core"],
        [item.core_row for item in results["narrowed"]],
        core_schema(),
    )
    _write_parquet(
        paths["v3_2_evidence"],
        [row for item in results["narrowed"] for row in item.evidence_rows],
        evidence_schema(),
    )
    paths["comparison_report"] = tmp_path / "comparison.json"
    compare_development_parser_v2_1_v3_2_outputs(
        paths["baseline_core"],
        paths["baseline_evidence"],
        paths["v3_2_core"],
        paths["v3_2_evidence"],
        paths["comparison_report"],
        expected_rows=2,
    )
    paths["comparison_report"].chmod(0o600)
    paths["development_identities"] = tmp_path / "development.identities.bin"
    write_identity_set(
        paths["development_identities"],
        (_identity(0), _identity(1)),
        partition="DEVELOPMENT",
        manifest_identity="a" * 64,
        sampling_config_fingerprint="b" * 64,
    )

    context_rows = []
    for index, row in enumerate(source):
        phase02 = {
            **row,
            "batch_priority": "fictional",
            "location_information": "no_geocoding_information",
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_phase02_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
        historical = results["historical"][index]
        phase02.update(
            {
                "baseline_core_json": json.dumps(
                    _json_safe(results["baseline"][index].core_row),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "experimental_core_json": json.dumps(
                    _json_safe(historical.core_row),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "baseline_evidence_json": json.dumps(
                    _json_safe(results["baseline"][index].evidence_rows),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "experimental_evidence_json": json.dumps(
                    _json_safe(historical.evidence_rows),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "targeted_case_metadata_json": json.dumps(
                    {
                        "scientific_output_changed": True,
                        "experimental_evidence_present": True,
                        "experimental_candidate_group_count": 1,
                        "experimental_selected": True,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
        context_rows.append(phase02)
    paths["protected_context"] = tmp_path / "protected-context.parquet"
    _write_parquet(
        paths["protected_context"], context_rows, targeted_review_context_schema()
    )
    paths["controlled_labels"] = tmp_path / "controlled-labels.parquet"
    metadata = {
        b"review_design": b"SINGLE_REVIEWER",
        b"primary_reviewer": b"Targeted-R01",
        b"primary_review_complete": b"true",
        b"primary_review_rows": b"2",
        b"independent_second_review": b"SKIPPED_BY_EXPLICIT_DECISION",
        b"locked_rows_read": b"0",
    }
    table = pa.Table.from_pylist(
        [_label(_identity(0), correct=True), _label(_identity(1), correct=False)],
        schema=targeted_review_label_schema(),
    ).replace_schema_metadata(metadata)
    pq.write_table(
        table,
        paths["controlled_labels"],
        write_statistics=False,
        write_page_checksum=True,
    )
    paths["controlled_labels"].chmod(0o600)
    paths["input_manifest"] = tmp_path / "input-manifest.json"
    paths["input_manifest"].write_text(
        json.dumps(
            {
                "experiment_iteration": _ITERATION,
                "targeted_review_population_rows": 2,
                "locked_rows_read": 0,
                "output_artifacts": {
                    "protected_context": {
                        "sha256": file_sha256(paths["protected_context"])
                    }
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    paths["input_manifest"].chmod(0o600)
    return paths, tuple(row["street_address_line_1"] for row in source)


def test_v3_2_reuse_is_exact_sanitized_and_neutral(tmp_path: Path) -> None:
    paths, raw_values = _inputs(tmp_path)
    output = tmp_path / "evaluation"
    artifacts = evaluate_targeted_v3_2_label_reuse(
        input_manifest_path=paths["input_manifest"],
        protected_context_path=paths["protected_context"],
        controlled_labels_path=paths["controlled_labels"],
        development_identities_path=paths["development_identities"],
        baseline_core_path=paths["baseline_core"],
        baseline_evidence_path=paths["baseline_evidence"],
        v3_2_core_path=paths["v3_2_core"],
        v3_2_evidence_path=paths["v3_2_evidence"],
        comparison_report_path=paths["comparison_report"],
        output_directory=output,
        implementation_commit="c" * 40,
        production=False,
        expected_development_rows=2,
        expected_review_rows=2,
        expected_changed_rows=1,
    )
    reuse = json.loads(artifacts["reuse_verification"].read_text(encoding="utf-8"))
    score = json.loads(artifacts["score"].read_text(encoding="utf-8"))
    manifest = json.loads(artifacts["manifest"].read_text(encoding="utf-8"))
    assert reuse["report_version"] == V3_2_REUSE_REPORT_VERSION
    assert reuse["v3_2_selected_identity_count"] == 1
    assert reuse["unseen_selected_identity_count"] == 0
    assert reuse["unseen_candidate_semantic_count"] == 0
    assert score["report_version"] == V3_2_SCORE_REPORT_VERSION
    assert score["status"] == (
        "TARGETED_SINGLE_REVIEWER_V3_2_SCORED_NO_PROMOTION_DECISION"
    )
    assert score["selected_experimental_rows"]["selected_rows"] == 1
    assert score["selected_experimental_rows"]["joint_street_house_exact_correct"] == 1
    assert score["false_positive_count"] == 0
    assert score["scientific_promotion_decision"] == "NOT_EVALUATED"
    assert score["inter_reviewer_agreement"] == "NOT_EVALUATED"
    assert manifest["locked_rows_read"] == 0
    serialized = "".join(
        path.read_text(encoding="utf-8") for path in artifacts.values()
    )
    assert not any(raw in serialized for raw in raw_values)
    assert not any(_review_id(_identity(index)) in serialized for index in range(2))
    assert str(tmp_path) not in serialized
    assert '"candidate_value":' not in serialized


def test_v3_2_reuse_rejects_locked_path_before_open(tmp_path: Path) -> None:
    paths, _ = _inputs(tmp_path)
    locked = tmp_path / "locked-evaluation.parquet"
    locked.write_bytes(b"must-not-be-opened")
    locked.chmod(0o600)
    try:
        evaluate_targeted_v3_2_label_reuse(
            input_manifest_path=paths["input_manifest"],
            protected_context_path=locked,
            controlled_labels_path=paths["controlled_labels"],
            development_identities_path=paths["development_identities"],
            baseline_core_path=paths["baseline_core"],
            baseline_evidence_path=paths["baseline_evidence"],
            v3_2_core_path=paths["v3_2_core"],
            v3_2_evidence_path=paths["v3_2_evidence"],
            comparison_report_path=paths["comparison_report"],
            output_directory=tmp_path / "output",
            implementation_commit="c" * 40,
            production=False,
            expected_development_rows=2,
            expected_review_rows=2,
            expected_changed_rows=1,
        )
    except ValueError as error:
        assert (
            str(error) == "LOCKED paths are prohibited in targeted DEVELOPMENT review"
        )
    else:
        raise AssertionError("LOCKED input was not rejected")

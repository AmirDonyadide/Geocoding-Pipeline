from __future__ import annotations

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility import (
    COUNTRY_CONFLICTING,
    COUNTRY_INVALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_UNANIMOUS_VALID,
    DEEPPARSE,
    ELIGIBILITY_MANIFEST_RELATIVE_PATH,
    LIBPOSTAL,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBLE_COUNTRY,
    PARSER_NOT_APPLICABLE_COUNTRY,
    load_eligibility_manifest,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_country_eligibility_audit import (
    _build_relations,
    _count_by,
    _parser_metrics,
)


REPOSITORY = Path(__file__).resolve().parents[1]


def _candidate_id(index: int) -> bytes:
    return index.to_bytes(32, "big")


def test_metadata_relations_separate_provenance_coverage_and_quality(
    tmp_path: Path,
) -> None:
    ids = [_candidate_id(index) for index in range(1, 7)]
    row_records = [
        {
            "stable_source_row_id_v1": _candidate_id(101),
            "stage06_standard_exact_candidate_id": ids[0],
            "stage06_native_exact_candidate_id": ids[0],
            "stage04_lower_country_iso_code": "de",
        },
        {
            "stable_source_row_id_v1": _candidate_id(102),
            "stage06_standard_exact_candidate_id": ids[1],
            "stage06_native_exact_candidate_id": None,
            "stage04_lower_country_iso_code": "jp",
        },
        {
            "stable_source_row_id_v1": _candidate_id(103),
            "stage06_standard_exact_candidate_id": ids[2],
            "stage06_native_exact_candidate_id": None,
            "stage04_lower_country_iso_code": "",
        },
        {
            "stable_source_row_id_v1": _candidate_id(104),
            "stage06_standard_exact_candidate_id": ids[3],
            "stage06_native_exact_candidate_id": None,
            "stage04_lower_country_iso_code": "zz",
        },
        {
            "stable_source_row_id_v1": _candidate_id(105),
            "stage06_standard_exact_candidate_id": ids[4],
            "stage06_native_exact_candidate_id": None,
            "stage04_lower_country_iso_code": "de",
        },
        {
            "stable_source_row_id_v1": _candidate_id(106),
            "stage06_standard_exact_candidate_id": ids[4],
            "stage06_native_exact_candidate_id": ids[5],
            "stage04_lower_country_iso_code": "",
        },
        {
            "stable_source_row_id_v1": _candidate_id(107),
            "stage06_standard_exact_candidate_id": None,
            "stage06_native_exact_candidate_id": ids[5],
            "stage04_lower_country_iso_code": "fr",
        },
        {
            "stable_source_row_id_v1": _candidate_id(108),
            "stage06_standard_exact_candidate_id": None,
            "stage06_native_exact_candidate_id": ids[5],
            "stage04_lower_country_iso_code": "de",
        },
    ]
    row_path = tmp_path / "row.parquet"
    pq.write_table(pa.Table.from_pylist(row_records), row_path)

    occurrence_counts = {ids[0]: (2, 1, 1), ids[4]: (2, 2, 0), ids[5]: (3, 0, 3)}
    registry_records = []
    for candidate_id in ids:
        total, standard, native = occurrence_counts.get(candidate_id, (1, 1, 0))
        registry_records.append(
            {
                "stage06_exact_candidate_id": candidate_id,
                "stage06_candidate_lower": "public synthetic candidate",
                "stage06_occurrence_count": total,
                "stage06_standard_occurrence_count": standard,
                "stage06_native_occurrence_count": native,
            }
        )
    registry_path = tmp_path / "registry.parquet"
    pq.write_table(pa.Table.from_pylist(registry_records), registry_path)
    stage07_path = tmp_path / "stage07.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "stage06_exact_candidate_id": candidate_id,
                    "stage07_parse_status": (
                        "PARSED_EMPTY" if candidate_id == ids[1] else "PARSED_NONEMPTY"
                    ),
                }
                for candidate_id in ids
            ]
        ),
        stage07_path,
    )
    selection = pa.table(
        {
            "review_order": list(range(1, 7)),
            "stage06_exact_candidate_id": ids,
            "selection_reasons": [["PUBLIC_SYNTHETIC"]] * 6,
            "input_codepoints": [10, 20, 30, 40, 50, 60],
        }
    )
    classifications = pa.table(
        {
            "review_order": list(range(1, 7)),
            "classification": [
                "PLAUSIBLE_PARSE",
                "PARTIAL_BUT_USABLE_PARSE",
                "QUESTIONABLE_PARSE",
                "CLEAR_MISPARSE",
                "PLAUSIBLE_PARSE",
                "UPSTREAM_SOURCE_CORRUPTION_OR_UNASSESSABLE",
            ],
        }
    )
    manifest = load_eligibility_manifest(
        REPOSITORY / ELIGIBILITY_MANIFEST_RELATIVE_PATH
    )
    connection = duckdb.connect(":memory:")
    try:
        _build_relations(
            connection,
            row_paths=(row_path,),
            registry_paths=(registry_path,),
            stage07_paths=(stage07_path,),
            selection=selection,
            classifications=classifications,
            valid_country_codes=manifest.valid_iso_alpha2_codes,
            deepparse_trained_country_codes=(manifest.deepparse_trained_country_codes),
        )
        assert _count_by(
            connection, "candidate_eligibility_audit", "country_provenance_status"
        ) == {
            COUNTRY_CONFLICTING: 1,
            COUNTRY_INVALID: 1,
            COUNTRY_MISSING: 1,
            COUNTRY_PARTIAL: 1,
            COUNTRY_UNANIMOUS_VALID: 2,
        }
        assert _count_by(
            connection, "candidate_eligibility_audit", "libpostal_eligibility"
        ) == {
            PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY: 1,
            PARSER_ELIGIBILITY_INVALID_COUNTRY: 1,
            PARSER_ELIGIBILITY_MISSING_COUNTRY: 1,
            PARSER_ELIGIBILITY_PARTIAL_COUNTRY: 1,
            PARSER_ELIGIBLE_COUNTRY: 2,
        }
        assert _count_by(
            connection, "candidate_eligibility_audit", "deepparse_eligibility"
        ) == {
            PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY: 1,
            PARSER_ELIGIBILITY_INVALID_COUNTRY: 1,
            PARSER_ELIGIBILITY_MISSING_COUNTRY: 1,
            PARSER_ELIGIBILITY_PARTIAL_COUNTRY: 1,
            PARSER_ELIGIBLE_COUNTRY: 1,
            PARSER_NOT_APPLICABLE_COUNTRY: 1,
        }
        libpostal = _parser_metrics(connection, parser=LIBPOSTAL)
        deepparse = _parser_metrics(connection, parser=DEEPPARSE)
        assert libpostal["eligible_candidates"] == 2
        assert libpostal["eligibility_matched_technical_status_counts"] == {
            "PARSED_EMPTY": 1,
            "PARSED_NONEMPTY": 1,
        }
        assert deepparse["eligible_candidates"] == 1
        candidate_schema = (
            connection.execute("SELECT * FROM candidate_eligibility_audit LIMIT 0")
            .arrow()
            .read_all()
            .schema
        )
        assert "stage06_candidate_lower" not in candidate_schema.names
    finally:
        connection.close()

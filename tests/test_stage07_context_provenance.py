from __future__ import annotations

import hashlib
import json
import stat
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s07_context_provenance
from safe_geocoding_pipeline.preprocessing.stages import s07_quality_root_cause
from safe_geocoding_pipeline.preprocessing.stages.s07_context_provenance import (
    ContextProvenanceConfig,
    Stage07ContextDiagnosticError,
    run_context_provenance_diagnostic,
)
from safe_geocoding_pipeline.preprocessing.stages.s07_parser_bundle import (
    ParserBundleOutcome,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def _private_file(path: Path) -> None:
    path.chmod(0o600)


def _review_artifacts(root: Path) -> tuple[Path, Path, str, list[bytes]]:
    ids = [index.to_bytes(32, "big") for index in range(1, 121)]
    selection = root / "selection.parquet"
    pq.write_table(
        pa.table(
            {
                "review_order": pa.array(range(1, 121), type=pa.uint32()),
                "stage06_exact_candidate_id": pa.array(ids, type=pa.binary(32)),
                "selection_reasons": pa.array(
                    [["synthetic_baseline"] for _ in ids],
                    type=pa.list_(pa.string()),
                ),
            }
        ),
        selection,
        write_page_checksum=True,
    )
    _private_file(selection)
    fingerprint = s07_quality_root_cause._selection_fingerprint(
        pq.read_table(selection)
    )
    classifications = root / "classifications.json"
    rows = []
    for order in range(1, 121):
        classification = (
            "CLEAR_MISPARSE"
            if order <= 11
            else "QUESTIONABLE_PARSE"
            if order <= 18
            else "PLAUSIBLE_PARSE"
        )
        rows.append({"review_order": order, "classification": classification})
    classifications.write_text(
        json.dumps(
            {
                "selection_fingerprint": fingerprint,
                "classifications": rows,
            }
        ),
        encoding="utf-8",
    )
    _private_file(classifications)
    return selection, classifications, fingerprint, ids


def _stage06_bundle(root: Path, ids: list[bytes]) -> tuple[Path, str, int, int]:
    stage06 = root / "stage06"
    row_directory = stage06 / "row_map" / "data"
    registry_directory = stage06 / "registry" / "data"
    for path in (
        stage06,
        stage06 / "row_map",
        row_directory,
        stage06 / "registry",
        registry_directory,
    ):
        _private_directory(path)

    row_records: list[dict[str, object]] = []
    for index, candidate_id in enumerate(ids, 1):
        row_records.append(
            {
                "stage06_standard_exact_candidate_id": candidate_id,
                "stage06_native_exact_candidate_id": None,
                "stage04_lower_country_iso_code": "" if index == 1 else "de",
            }
        )
    row_records.extend(
        [
            {
                "stage06_standard_exact_candidate_id": None,
                "stage06_native_exact_candidate_id": ids[2],
                "stage04_lower_country_iso_code": "",
            },
            {
                "stage06_standard_exact_candidate_id": None,
                "stage06_native_exact_candidate_id": ids[3],
                "stage04_lower_country_iso_code": "fr",
            },
            {
                "stage06_standard_exact_candidate_id": None,
                "stage06_native_exact_candidate_id": ids[4],
                "stage04_lower_country_iso_code": "de",
            },
            {
                "stage06_standard_exact_candidate_id": None,
                "stage06_native_exact_candidate_id": ids[5],
                "stage04_lower_country_iso_code": "",
            },
        ]
    )
    row_path = row_directory / "part-000001.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            row_records,
            schema=pa.schema(
                [
                    pa.field(
                        "stage06_standard_exact_candidate_id", pa.binary(32), True
                    ),
                    pa.field("stage06_native_exact_candidate_id", pa.binary(32), True),
                    pa.field("stage04_lower_country_iso_code", pa.string(), True),
                ]
            ),
        ),
        row_path,
    )
    _private_file(row_path)

    extra_native = {ids[2], ids[3], ids[4], ids[5]}
    registry_records = []
    for candidate_id in ids:
        native = int(candidate_id in extra_native)
        registry_records.append(
            {
                "stage06_exact_candidate_id": candidate_id,
                "stage06_candidate_lower": "public synthetic candidate",
                "stage06_occurrence_count": 1 + native,
                "stage06_standard_occurrence_count": 1,
                "stage06_native_occurrence_count": native,
            }
        )
    registry_path = registry_directory / "part-000001.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            registry_records,
            schema=pa.schema(
                [
                    pa.field("stage06_exact_candidate_id", pa.binary(32), False),
                    pa.field("stage06_candidate_lower", pa.string(), False),
                    pa.field("stage06_occurrence_count", pa.uint64(), False),
                    pa.field("stage06_standard_occurrence_count", pa.uint64(), False),
                    pa.field("stage06_native_occurrence_count", pa.uint64(), False),
                ]
            ),
        ),
        registry_path,
    )
    _private_file(registry_path)

    source_rows = len(row_records)
    occurrences = len(ids) + len(extra_native)
    manifest = {
        "stage06_manifest_version": "stage06_manifest_v1",
        "status": "STAGE_6_DEVELOPMENT_CANDIDATE_MATERIALIZED",
        "scientific_identity": {
            "stage06_contract_version": "stage06_early_exact_deduplication_contract_v1",
            "stage06_profile_version": "stage06_early_exact_deduplication_profile_v1",
            "stage06_schema_fingerprint": "synthetic",
            "stage06_logical_dataset_sha256_v1": "synthetic",
            "source_row_count": source_rows,
            "unique_candidate_count": len(ids),
            "registry_columns": [
                "stage06_exact_candidate_id",
                "stage06_candidate_lower",
                "stage06_occurrence_count",
                "stage06_standard_occurrence_count",
                "stage06_native_occurrence_count",
            ],
            "row_map_id_columns": [
                "stage06_standard_exact_candidate_id",
                "stage06_native_exact_candidate_id",
            ],
        },
        "physical_identity": {
            "row_map_artifacts": [
                {
                    "relative_path": "row_map/data/part-000001.parquet",
                    "row_count": source_rows,
                    "sha256": _sha256(row_path),
                    "size_bytes": row_path.stat().st_size,
                }
            ],
            "registry_artifacts": [
                {
                    "relative_path": "registry/data/part-000001.parquet",
                    "row_count": len(ids),
                    "sha256": _sha256(registry_path),
                    "size_bytes": registry_path.stat().st_size,
                }
            ],
        },
    }
    manifest_path = stage06 / "stage06_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _private_file(manifest_path)
    return stage06, _sha256(manifest_path), source_rows, occurrences


def _source_evidence(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    pypostal = root / "parser.py"
    header = root / "libpostal.h"
    implementation = root / "address_parser.c"
    pypostal.write_text(
        "def parse_address(address, language=None, country=None):\n"
        "    return _parser.parse_address(address, language=language, country=country)\n",
        encoding="utf-8",
    )
    header.write_text(
        "typedef struct libpostal_address_parser_options {\n"
        "char *language;\nchar *country;\n"
        "} libpostal_address_parser_options_t;\n",
        encoding="utf-8",
    )
    implementation.write_text(
        "// This parser was trained without knowing language/country.\n"
        "language = NULL;\ncountry = NULL;\n"
        "address_parser_context_fill(context, parser, tokenized_str, language, country);\n",
        encoding="utf-8",
    )
    for path in (pypostal, header, implementation):
        _private_file(path)
    monkeypatch.setattr(
        s07_context_provenance, "PYPPOSTAL_PARSER_SOURCE_SHA256", _sha256(pypostal)
    )
    monkeypatch.setattr(
        s07_context_provenance, "LIBPOSTAL_HEADER_SOURCE_SHA256", _sha256(header)
    )
    monkeypatch.setattr(
        s07_context_provenance,
        "LIBPOSTAL_ADDRESS_PARSER_SOURCE_SHA256",
        _sha256(implementation),
    )
    return pypostal, header, implementation


def test_context_diagnostic_proves_no_effective_variants_and_audits_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection, classifications, fingerprint, ids = _review_artifacts(tmp_path)
    stage06, manifest_sha, source_rows, occurrences = _stage06_bundle(tmp_path, ids)
    pypostal, header, implementation = _source_evidence(tmp_path, monkeypatch)
    parser_bundle = tmp_path / "parser_bundle"
    _private_directory(parser_bundle)
    monkeypatch.setattr(
        s07_context_provenance,
        "validate_parser_bundle",
        lambda *_args, **_kwargs: ParserBundleOutcome(
            output_directory=parser_bundle,
            parser_bundle_fingerprint="b" * 64,
            parser_model_data_fingerprint="c" * 64,
            pypostal_runtime_fingerprint="d" * 64,
            libpostal_shared_library_sha256="e" * 64,
            manifest_sha256="f" * 64,
            artifact_count=1,
            total_size_bytes=1,
        ),
    )
    output = tmp_path / "context_audit"
    aggregate = run_context_provenance_diagnostic(
        ContextProvenanceConfig(
            stage06_output_directory=stage06,
            parser_bundle_directory=parser_bundle,
            selection_path=selection,
            classifications_path=classifications,
            pypostal_parser_source=pypostal,
            libpostal_header_source=header,
            libpostal_address_parser_source=implementation,
            output_directory=output,
            execution_git_sha="a" * 40,
            expected_stage06_manifest_sha256=manifest_sha,
            expected_parser_bundle_fingerprint="b" * 64,
            expected_selection_fingerprint=fingerprint,
            expected_source_rows=source_rows,
            expected_registry_rows=120,
            expected_occurrences=occurrences,
            expected_standard_occurrences=120,
            expected_native_occurrences=4,
            production=False,
        )
    )

    assert aggregate["decision"] == "CONTEXT_AWARE_LIBPOSTAL_NOT_SUFFICIENT"
    api = cast(dict[str, object], aggregate["api_evidence"])
    variants = cast(dict[str, object], aggregate["variant_execution"])
    population = cast(dict[str, object], aggregate["population_audit"])
    future_key = cast(dict[str, object], aggregate["future_parse_key"])
    assert api["effective_context_parameters"] == []
    assert variants["protected_parser_calls"] == 0
    assert population["no_usable_explicit_country"] == 1
    assert population["unanimous_one_country"] == 116
    assert population["partial_one_country"] == 2
    assert population["conflicting_countries"] == 1
    assert population["country_only_parse_once_eligible"] == 116
    assert population["candidates_with_missing_country_occurrences"] == 3
    assert population["candidates_with_invalid_country_occurrences"] == 0
    assert population["missing_country_occurrences"] == 3
    assert population["invalid_country_occurrences"] == 0
    assert population["no_explicit_language"] == 120
    assert population["both_representation_candidates"] == 4
    assert population["context_differs_across_standard_native"] == 3
    assert (
        future_key[
            "candidate_plus_context_required_for_conflicting_candidates_if_future_"
            "effective_context_exists"
        ]
        is True
    )
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert not list(tmp_path.glob(".context_audit.partial.*"))
    candidate_path = output / "stage07_context_candidate_audit.parquet"
    assert stat.S_IMODE(candidate_path.stat().st_mode) == 0o600
    schema = pq.read_schema(candidate_path)
    assert "stage06_candidate_lower" not in schema.names
    assert "country_context" not in schema.names
    aggregate_text = (output / "stage07_context_provenance_aggregate.json").read_text(
        encoding="utf-8"
    )
    assert "public synthetic candidate" not in aggregate_text


def test_context_config_rejects_holdout() -> None:
    with pytest.raises(Stage07ContextDiagnosticError, match="HOLDOUT"):
        ContextProvenanceConfig(
            stage06_output_directory=Path("stage06"),
            parser_bundle_directory=Path("bundle"),
            selection_path=Path("selection.parquet"),
            classifications_path=Path("classifications.json"),
            pypostal_parser_source=Path("parser.py"),
            libpostal_header_source=Path("libpostal.h"),
            libpostal_address_parser_source=Path("address_parser.c"),
            output_directory=Path("HOLDOUT") / "output",
            execution_git_sha="a" * 40,
            production=False,
        ).validate()


def test_context_api_gate_rejects_wrapper_options_without_native_forced_null(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pypostal, header, implementation = _source_evidence(tmp_path, monkeypatch)
    implementation.write_text(
        "// This parser was trained without knowing language/country.\n"
        "address_parser_context_fill(context, parser, tokenized_str, language, country);\n",
        encoding="utf-8",
    )
    _private_file(implementation)
    monkeypatch.setattr(
        s07_context_provenance,
        "LIBPOSTAL_ADDRESS_PARSER_SOURCE_SHA256",
        _sha256(implementation),
    )
    config = ContextProvenanceConfig(
        stage06_output_directory=tmp_path / "stage06",
        parser_bundle_directory=tmp_path / "bundle",
        selection_path=tmp_path / "selection.parquet",
        classifications_path=tmp_path / "classifications.json",
        pypostal_parser_source=pypostal,
        libpostal_header_source=header,
        libpostal_address_parser_source=implementation,
        output_directory=tmp_path / "output",
        execution_git_sha="a" * 40,
        production=False,
    )
    with pytest.raises(Stage07ContextDiagnosticError, match="API_EVIDENCE"):
        s07_context_provenance._validate_parser_api_sources(config)


def test_context_launcher_is_metadata_only_and_has_no_parser_call() -> None:
    repository = Path(__file__).resolve().parents[1]
    script = (
        repository / "cluster/goethe_nhr/stage07_context_provenance.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --mem=16G" in script
    assert "parser_calls=0" in script
    assert "candidate_text_inspection=false" in script
    assert "protected_network_calls=false" in script
    assert "stage07_context_cli" in script
    assert "postal.parser" not in script
    assert "stage07_libpostal_parsing" not in script
    assert "RLIMIT_AS" not in script
    assert "ulimit -v" not in script

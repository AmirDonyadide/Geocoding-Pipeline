from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import engine, phase02_row
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase03.constants import (
    CORE_COLUMNS,
    DIAGNOSTIC_FLAGS,
    PARSER_VERSION_V2,
    PARSER_VERSION_V3,
)
from safe_geocoding_pipeline.phase03.cli import build_parser
from safe_geocoding_pipeline.phase03.development_v3_change_diagnostic import (
    DIAGNOSTIC_VERSION,
    EXPERIMENTAL_RULE_IDS,
    PRODUCTION_EXPECTATION,
    REPORT_SCHEMA_VERSION,
    SCIENTIFIC_CORE_FIELDS,
    PopulationExpectation,
    _combination_summary,
    _evidence_population_summary,
    _exact_evidence_topology,
    _experimental_evidence_groups,
    _family_change_counts,
    _field_change_counts,
    _provenance_summary,
    diagnose_development_v3_changes,
)
from safe_geocoding_pipeline.phase03.development_comparison import (
    _SCIENTIFIC_CORE_FIELDS as COMPARISON_SCIENTIFIC_CORE_FIELDS,
)
from safe_geocoding_pipeline.phase03.pilot_runner import write_identity_set
from safe_geocoding_pipeline.phase03.schema import core_schema, evidence_schema
from safe_geocoding_pipeline.phase03.targeted_experiment_review import (
    _SCIENTIFIC_CORE_FIELDS as REVIEW_SCIENTIFIC_CORE_FIELDS,
)


def _identity(index: int) -> bytes:
    return hashlib.sha256(f"fictional-v3-diagnostic:{index}".encode()).digest()


def _write(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        compression="zstd",
        compression_level=3,
        version="2.4",
        data_page_version="1.0",
        write_page_checksum=True,
        write_statistics=False,
    )
    path.chmod(0o600)


def _ordered_diagnostics(values: set[str]) -> list[str]:
    return [item for item in DIAGNOSTIC_FLAGS if item in values]


def _fixture(tmp_path: Path) -> tuple[dict[str, Path], tuple[str, ...]]:
    root = tmp_path / "controlled"
    v2_root = root / "v2-reference"
    v3_root = root / "v3-experiment"
    root.mkdir(parents=True, mode=0o700)
    v2_root.mkdir()
    v3_root.mkdir()
    v2 = engine(v2_root, parser_version=PARSER_VERSION_V2)
    v3 = engine(v3_root, parser_version=PARSER_VERSION_V3)

    raw_values: list[str] = []
    source_rows: list[dict[str, Any]] = []
    # Five rows overlap A and B: V4 evidence is present and selected.
    for index in range(5):
        raw = f"Annex {index + 10} Fictional Street"
        raw_values.append(raw)
        source_rows.append(
            phase02_row(
                id=f"fictional-provider-{index}",
                stable_source_row_id_v1=_identity(index),
                source_logical_record_number=index + 1,
                street_address_line_1=raw,
                postcode="12345",
                city="Fiction City",
                country_iso_code="XZ",
            )
        )
    # Five rows are changed-only after a valid fixed-vocabulary diagnostic
    # mutation. They deliberately contain no experimental V4 evidence.
    for index in range(5, 10):
        raw = f"{index + 30} Fiction Avenue"
        raw_values.append(raw)
        source_rows.append(
            phase02_row(
                id=f"fictional-provider-{index}",
                stable_source_row_id_v1=_identity(index),
                source_logical_record_number=index + 1,
                street_address_line_1=raw,
                postcode="54321",
                city="Sample City",
                country_iso_code="XZ",
            )
        )
    # One evidence-only row emits unselected V4 candidates because structured
    # support is absent; one ordinary row belongs to neither population.
    raw_values.extend(("Wing 7 Sample Road", "44 Ordinary Road"))
    source_rows.extend(
        (
            phase02_row(
                id="fictional-provider-10",
                stable_source_row_id_v1=_identity(10),
                source_logical_record_number=11,
                street_address_line_1=raw_values[10],
            ),
            phase02_row(
                id="fictional-provider-11",
                stable_source_row_id_v1=_identity(11),
                source_logical_record_number=12,
                street_address_line_1=raw_values[11],
                postcode="77777",
                city="Other City",
                country_iso_code="XZ",
            ),
        )
    )

    v2_results = [v2.transform(row) for row in source_rows]
    v3_results = [v3.transform(row) for row in source_rows]
    v2_core_rows = [deepcopy(item.core_row) for item in v2_results]
    v3_core_rows = [deepcopy(item.core_row) for item in v3_results]
    for row in v3_core_rows[5:10]:
        existing = set(row["address_diagnostic_flags"])
        existing.add("HISTORICAL_EVIDENCE")
        row["address_diagnostic_flags"] = _ordered_diagnostics(existing)

    paths = {
        "root": root,
        "identities": root / "development.identities.bin",
        "v2_core": root / "v2-core.parquet",
        "v2_evidence": root / "v2-evidence.parquet",
        "v3_core": root / "v3-core.parquet",
        "v3_evidence": root / "v3-evidence.parquet",
    }
    _write(paths["v2_core"], v2_core_rows, core_schema())
    _write(
        paths["v2_evidence"],
        [row for result in v2_results for row in result.evidence_rows],
        evidence_schema(),
    )
    _write(paths["v3_core"], v3_core_rows, core_schema())
    _write(
        paths["v3_evidence"],
        [row for result in v3_results for row in result.evidence_rows],
        evidence_schema(),
    )
    write_identity_set(
        paths["identities"],
        (_identity(index) for index in range(12)),
        partition="DEVELOPMENT",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    return paths, tuple(raw_values)


_EXPECTATION = PopulationExpectation(
    development_rows=12,
    scientific_change_rows=10,
    experimental_evidence_rows=6,
    overlap_rows=5,
    changed_only_rows=5,
    evidence_only_rows=1,
    union_rows=11,
)


def _run(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Path], tuple[str, ...]]:
    paths, raw_values = _fixture(tmp_path)
    output = paths["root"] / "report"
    diagnose_development_v3_changes(
        baseline_core_path=paths["v2_core"],
        baseline_evidence_path=paths["v2_evidence"],
        experimental_core_path=paths["v3_core"],
        experimental_evidence_path=paths["v3_evidence"],
        development_identities_path=paths["identities"],
        output_directory=output,
        controlled_root=paths["root"],
        report_root=paths["root"],
        implementation_commit="a" * 40,
        production=False,
        expectation=_EXPECTATION,
    )
    payload = json.loads(
        (output / "phase03_parser_v3_change_diagnostic.json").read_text()
    )
    return payload, paths, raw_values


def test_decomposition_field_families_and_evidence_are_exact(tmp_path: Path) -> None:
    payload, _, _ = _run(tmp_path)
    assert SCIENTIFIC_CORE_FIELDS == CORE_COLUMNS[5:41]
    assert SCIENTIFIC_CORE_FIELDS == COMPARISON_SCIENTIFIC_CORE_FIELDS
    assert SCIENTIFIC_CORE_FIELDS == REVIEW_SCIENTIFIC_CORE_FIELDS
    assert payload["population"] == {
        "development": 12,
        "scientific_change": 10,
        "experimental_evidence": 6,
        "overlap": 5,
        "changed_only": 5,
        "evidence_only": 1,
        "union": 11,
        "neither": 1,
    }
    assert (
        payload["field_change_counts"]["changed_only"]["address_diagnostic_flags"] == 5
    )
    assert sum(payload["field_change_counts"]["evidence_only"].values()) == 0
    assert payload["family_change_counts"]["changed_only"]["diagnostics"] == 5
    assert payload["changed_only_field_combinations"]["reported"] == [
        {"fields": ["address_diagnostic_flags"], "rows": 5}
    ]
    evidence = payload["experimental_evidence_metrics"]
    assert evidence["by_population"]["all_experimental_evidence"][
        "rule_presence"
    ]["counts"] == {
        "both_v4_rules_present": 6,
        "house_number_v4_only": 0,
        "street_v4_only": 0,
    }
    assert evidence["by_population"]["overlap"]["selection_outcome"][
        "counts"
    ] == {
        "both_selected": 5,
        "house_selected_street_unselected": 0,
        "street_selected_house_unselected": 0,
        "both_unselected": 0,
        "mixed_or_multiple_evidence_state": 0,
    }
    evidence_only = evidence["by_population"]["evidence_only"]
    assert evidence_only["selection_outcome"]["counts"]["both_unselected"] is None
    assert evidence_only["selection_outcome"]["suppressed_categories"] == [
        "both_unselected"
    ]
    assert evidence_only["selection_outcome"]["reconciliation_total"] == 1
    assert evidence["by_population"]["changed_only"] == {
        "population_rows": 5,
        "experimental_evidence_identities": 0,
        "identities_without_experimental_evidence": 5,
        "rule_presence": {
            "counts": {
                "both_v4_rules_present": 0,
                "house_number_v4_only": 0,
                "street_v4_only": 0,
            },
            "suppressed_categories": [],
            "suppression_threshold": 5,
            "reconciliation_total": 0,
            "reconciliation_passed": True,
        },
        "selection_outcome": {
            "counts": {
                "both_selected": 0,
                "house_selected_street_unselected": 0,
                "street_selected_house_unselected": 0,
                "both_unselected": 0,
                "mixed_or_multiple_evidence_state": 0,
            },
            "suppressed_categories": [],
            "suppression_threshold": 5,
            "reconciliation_total": 0,
            "reconciliation_passed": True,
        },
    }
    assert evidence["pairing_or_selection_assumed"] is False
    assert evidence["topology_is_diagnostic_result"] is True
    assert set(evidence["selected_candidate_groups_by_rule"]) == set(
        EXPERIMENTAL_RULE_IDS
    )
    assert DIAGNOSTIC_VERSION == "phase03_parser_v3_change_diagnostic_v2"
    assert REPORT_SCHEMA_VERSION == "phase03_parser_v3_change_diagnostic_report_v2"
    assert payload["root_cause_assessment"]["classification"] == (
        "B_V3_PATH_CHANGED_SCIENTIFIC_METADATA_WITHOUT_V4_EVIDENCE"
    )
    assert payload["change_definition_consistency"] == {
        "definition": "CORE_COLUMNS[5:41]",
        "field_count": 36,
        "comparison_matches": True,
        "targeted_review_matches": True,
    }


def test_asymmetric_experimental_evidence_topologies_are_diagnostic_results() -> (
    None
):
    house_rule, street_rule = EXPERIMENTAL_RULE_IDS
    rows: list[dict[str, Any]] = []

    def add(
        identity_index: int,
        evidence_id: int,
        rule_id: str,
        selected: bool,
        *,
        repeat_span: bool = False,
    ) -> None:
        row = {
            "stable_source_row_id_v1": _identity(identity_index),
            "evidence_id": evidence_id,
            "rule_id": rule_id,
            "selected": selected,
        }
        rows.append(row)
        if repeat_span:
            rows.append(dict(row))

    # Exercise paired selection, asymmetric selection, paired rejection,
    # one-rule evidence, and multiple candidate groups without changing rules.
    add(0, 1, house_rule, True)
    add(0, 2, street_rule, True)
    add(1, 1, house_rule, True)
    add(1, 2, street_rule, False)
    add(2, 1, house_rule, False)
    add(2, 2, street_rule, True)
    add(3, 1, house_rule, False)
    add(3, 2, street_rule, False)
    add(4, 1, house_rule, True)
    add(5, 1, street_rule, False)
    add(6, 1, house_rule, True)
    add(6, 2, house_rule, False)
    add(6, 3, street_rule, True)
    # Repeated span rows share one evidence_id and remain one candidate group.
    add(8, 1, house_rule, True, repeat_span=True)
    add(8, 2, street_rule, True)

    changed_ids = {_identity(index) for index in range(8)}
    groups = _experimental_evidence_groups(rows)
    exact_overlap = _exact_evidence_topology(changed_ids & set(groups), groups)
    assert exact_overlap == {
        "population_rows": 7,
        "experimental_evidence_identities": 7,
        "identities_without_experimental_evidence": 0,
        "rule_presence": {
            "both_v4_rules_present": 5,
            "house_number_v4_only": 1,
            "street_v4_only": 1,
        },
        "selection_outcome": {
            "both_selected": 1,
            "house_selected_street_unselected": 2,
            "street_selected_house_unselected": 1,
            "both_unselected": 2,
            "mixed_or_multiple_evidence_state": 1,
        },
    }

    evidence_ids, summary = _evidence_population_summary(rows, changed_ids=changed_ids)
    assert evidence_ids == {*(_identity(index) for index in range(7)), _identity(8)}
    assert summary["by_population"]["overlap"]["rule_presence"]["counts"] == {
        "both_v4_rules_present": 5,
        "house_number_v4_only": None,
        "street_v4_only": None,
    }
    assert summary["by_population"]["overlap"]["rule_presence"][
        "reconciliation_total"
    ] == 7
    assert summary["by_population"]["changed_only"]["population_rows"] == 1
    assert summary["by_population"]["changed_only"][
        "experimental_evidence_identities"
    ] == 0
    assert summary["by_population"]["evidence_only"][
        "experimental_evidence_identities"
    ] == 1
    assert summary["pairing_or_selection_assumed"] is False


def test_unknown_experimental_rule_and_inconsistent_group_fail_closed() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_EXPERIMENTAL_RULE_ID"):
        _experimental_evidence_groups(
            [
                {
                    "stable_source_row_id_v1": _identity(0),
                    "evidence_id": 1,
                    "rule_id": "FICTIONAL_UNKNOWN_EXPERIMENT_V4",
                    "selected": False,
                }
            ]
        )

    house_rule = EXPERIMENTAL_RULE_IDS[0]
    with pytest.raises(ValueError, match="selection is inconsistent"):
        _experimental_evidence_groups(
            [
                {
                    "stable_source_row_id_v1": _identity(0),
                    "evidence_id": 1,
                    "rule_id": house_rule,
                    "selected": False,
                },
                {
                    "stable_source_row_id_v1": _identity(0),
                    "evidence_id": 1,
                    "rule_id": house_rule,
                    "selected": True,
                },
            ]
        )


def test_report_is_deterministic_bounded_and_privacy_safe(tmp_path: Path) -> None:
    first, first_paths, raw_values = _run(tmp_path / "first")
    second, _, _ = _run(tmp_path / "second")
    assert first == second
    output = first_paths["root"] / "report"
    serialized = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            output / "phase03_parser_v3_change_diagnostic.json",
            output / "phase03_parser_v3_change_diagnostic.md",
        )
    )
    assert not any(value in serialized for value in raw_values)
    assert "fictional-provider" not in serialized
    assert str(tmp_path) not in serialized
    assert not any(_identity(index).hex() in serialized for index in range(12))
    assert first["privacy"] == {
        "aggregate_only": True,
        "raw_values_reported": False,
        "identities_reported": False,
        "source_spans_reported": False,
        "paths_reported": False,
        "human_labels_read": False,
        "locked_rows_read": 0,
        "rare_field_combination_suppression_threshold": 5,
        "evidence_topology_small_cell_suppression_threshold": 5,
    }
    assert first["scientific_rule_change"] is False
    assert first["human_labels"] is False
    assert first["locked_rows_read"] == 0
    assert set(first["inputs"]) == {
        "baseline_core",
        "baseline_evidence",
        "experimental_core",
        "experimental_evidence",
        "development_identities",
    }
    for role, artifact in first["inputs"].items():
        assert (
            artifact["sha256"]
            == hashlib.sha256(
                first_paths[
                    {
                        "baseline_core": "v2_core",
                        "baseline_evidence": "v2_evidence",
                        "experimental_core": "v3_core",
                        "experimental_evidence": "v3_evidence",
                        "development_identities": "identities",
                    }[role]
                ].read_bytes()
            ).hexdigest()
        )
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in output.iterdir())


def test_rare_combinations_are_suppressed_and_cardinality_is_bounded() -> None:
    baseline: dict[bytes, dict[str, Any]] = {}
    experimental: dict[bytes, dict[str, Any]] = {}
    for index in range(40):
        identity = _identity(index)
        before: dict[str, Any] = {field: None for field in SCIENTIFIC_CORE_FIELDS}
        after = dict(before)
        first = SCIENTIFIC_CORE_FIELDS[index % len(SCIENTIFIC_CORE_FIELDS)]
        second = SCIENTIFIC_CORE_FIELDS[
            (index // len(SCIENTIFIC_CORE_FIELDS)) % len(SCIENTIFIC_CORE_FIELDS)
        ]
        after[first] = "changed"
        after[second] = "also-changed"
        baseline[identity] = before
        experimental[identity] = after
    summary = _combination_summary(set(baseline), baseline, experimental)
    assert len(summary["reported"]) <= 32
    assert summary["suppressed_rows"] > 0
    assert summary["total_rows"] == 40

    repeated_baseline: dict[bytes, dict[str, Any]] = {}
    repeated_experimental: dict[bytes, dict[str, Any]] = {}
    for index in range(5):
        identity = _identity(100 + index)
        before = {field: None for field in SCIENTIFIC_CORE_FIELDS}
        after = dict(before)
        after["address_parse_status"] = "PARTIAL"
        after["address_completeness_class"] = "G_OTHER_PARTIAL"
        repeated_baseline[identity] = before
        repeated_experimental[identity] = after
    repeated = _combination_summary(
        set(repeated_baseline), repeated_baseline, repeated_experimental
    )
    assert repeated["reported"] == [
        {
            "fields": ["address_parse_status", "address_completeness_class"],
            "rows": 5,
        }
    ]


def test_provenance_diagnostic_completeness_selected_and_representation_metrics() -> (
    None
):
    identities = {_identity(index) for index in range(5)}
    baseline: dict[bytes, dict[str, Any]] = {}
    experimental: dict[bytes, dict[str, Any]] = {}
    for index, identity in enumerate(sorted(identities)):
        before: dict[str, Any] = {field: None for field in SCIENTIFIC_CORE_FIELDS}
        before.update(
            {
                "selected_component_provenance": [],
                "address_diagnostic_flags": [],
                "address_completeness_class": "Z_NO_COMPONENTS",
            }
        )
        after = deepcopy(before)
        if index == 0:
            after["address_diagnostic_flags"] = ["UNASSIGNED_CONTENT_PRESENT"]
        elif index == 1:
            after["address_completeness_class"] = "G_OTHER_PARTIAL"
        elif index == 2:
            after["street_clean"] = "fictional-selected-value"
        elif index == 3:
            before["street_clean"] = after["street_clean"] = "same-value"
            before["selected_component_provenance"] = [
                {
                    "component": "STREET",
                    "representation": "NATIVE",
                    "source_fields": ["street_address_line_1_native"],
                    "rule_ids": ["FICTIONAL_RULE"],
                    "confidence": "HIGH",
                }
            ]
            after["selected_component_provenance"] = [
                {
                    "component": "STREET",
                    "representation": "NON_NATIVE",
                    "source_fields": ["street_address_line_1"],
                    "rule_ids": ["FICTIONAL_RULE"],
                    "confidence": "HIGH",
                }
            ]
        else:
            before["street_clean"] = after["street_clean"] = "same-value"
            before["selected_component_provenance"] = [
                {
                    "component": "STREET",
                    "representation": "NON_NATIVE",
                    "source_fields": ["street_address_line_1"],
                    "rule_ids": ["FICTIONAL_RULE_A"],
                    "confidence": "HIGH",
                }
            ]
            after["selected_component_provenance"] = [
                {
                    "component": "STREET",
                    "representation": "NON_NATIVE",
                    "source_fields": ["street_address_line_1"],
                    "rule_ids": ["FICTIONAL_RULE_B"],
                    "confidence": "HIGH",
                }
            ]
        baseline[identity] = before
        experimental[identity] = after
    fields = _field_change_counts(identities, baseline, experimental)
    families = _family_change_counts(identities, baseline, experimental)
    provenance = _provenance_summary(identities, baseline, experimental)
    assert fields["address_diagnostic_flags"] == 1
    assert fields["address_completeness_class"] == 1
    assert fields["street_clean"] == 1
    assert families["selected_component_provenance"] == 2
    assert provenance["rows"]["representation_changed_selected_values_same"] == 1
    assert provenance["rows"]["source_fields_changed"] == 1
    assert provenance["rows"]["rule_ids_changed"] == 1


def test_prohibited_paths_and_wrong_partition_fail_closed(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path / "fixture")
    with pytest.raises(ValueError, match="LOCKED paths"):
        diagnose_development_v3_changes(
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            development_identities_path=paths["identities"],
            output_directory=paths["root"] / "locked-output",
            controlled_root=paths["root"],
            report_root=paths["root"],
            implementation_commit="a" * 40,
            production=False,
            expectation=_EXPECTATION,
        )
    assert not (paths["root"] / "locked-output").exists()

    wrong = paths["root"] / "wrong.identities.bin"
    write_identity_set(
        wrong,
        (_identity(index) for index in range(12)),
        partition="LOCKED_EVALUATION",
        manifest_identity="fictional-phase02-manifest",
        sampling_config_fingerprint="fictional-sampling-config",
    )
    with pytest.raises(ValueError, match="not DEVELOPMENT"):
        diagnose_development_v3_changes(
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            development_identities_path=wrong,
            output_directory=paths["root"] / "wrong-output",
            controlled_root=paths["root"],
            report_root=paths["root"],
            implementation_commit="a" * 40,
            production=False,
            expectation=_EXPECTATION,
        )


def test_production_guard_runs_before_any_input_access(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        diagnose_development_v3_changes(
            baseline_core_path=missing / "v2-core.parquet",
            baseline_evidence_path=missing / "v2-evidence.parquet",
            experimental_core_path=missing / "v3-core.parquet",
            experimental_evidence_path=missing / "v3-evidence.parquet",
            development_identities_path=missing / "development.identities.bin",
            output_directory=missing / "output",
            controlled_root=missing,
            report_root=missing,
            implementation_commit="a" * 40,
            production=True,
        )


def test_resolved_prohibited_path_fails_closed(tmp_path: Path) -> None:
    paths, _ = _fixture(tmp_path / "fixture")
    prohibited = tmp_path / "locked-evaluation-artifacts"
    prohibited.mkdir()
    copied_core = prohibited / "v2-core.parquet"
    copied_core.write_bytes(paths["v2_core"].read_bytes())
    alias = tmp_path / "development-alias"
    alias.symlink_to(prohibited, target_is_directory=True)
    with pytest.raises(ValueError, match="LOCKED paths"):
        diagnose_development_v3_changes(
            baseline_core_path=alias / "v2-core.parquet",
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            development_identities_path=paths["identities"],
            output_directory=paths["root"] / "must-not-exist",
            controlled_root=tmp_path,
            report_root=paths["root"],
            implementation_commit="a" * 40,
            production=False,
            expectation=_EXPECTATION,
        )
    assert not (paths["root"] / "must-not-exist").exists()


def test_cli_and_slurm_contract_are_frozen_and_privacy_safe() -> None:
    args = build_parser().parse_args(
        [
            "development-diagnose-parser-v2-v3-changes",
            "--baseline-core",
            "v2-core.parquet",
            "--baseline-evidence",
            "v2-evidence.parquet",
            "--experimental-core",
            "v3-core.parquet",
            "--experimental-evidence",
            "v3-evidence.parquet",
            "--development-identities",
            "development.identities.bin",
            "--controlled-root",
            "controlled",
            "--report-root",
            "reports",
            "--output-directory",
            "reports/output",
            "--implementation-commit",
            "a" * 40,
        ]
    )
    assert args.command == "development-diagnose-parser-v2-v3-changes"
    assert PRODUCTION_EXPECTATION == PopulationExpectation(
        development_rows=8_000,
        scientific_change_rows=26,
        experimental_evidence_rows=11,
        overlap_rows=9,
        changed_only_rows=17,
        evidence_only_rows=2,
        union_rows=28,
    )
    script = Path(
        "cluster/goethe_nhr/phase03_parser_v3_change_diagnostic.sbatch"
    ).read_text(encoding="utf-8")
    assert "#SBATCH --partition=general1" in script
    assert "SAFE_EXECUTION_SITE=goethe-nhr" in script
    assert "development-diagnose-parser-v2-v3-changes" in script
    assert "PHASE03_DEVELOPMENT_PAYLOAD" not in script
    assert "PHASE03_TARGETED_REVIEW_EXPECTED_COUNT" not in script
    assert "locked_payload_access=PROHIBITED" in script
    assert "human_labels_read=false" in script
    assert "scientific_change_rows_expected=26" in script
    assert "union_rows_expected=28" in script


def test_input_change_during_read_fails_before_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths, _ = _fixture(tmp_path)
    from safe_geocoding_pipeline.phase03 import (
        development_v3_change_diagnostic as module,
    )

    real_state = module._artifact_state
    calls = 0

    def unstable_state(path: Path) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        size, digest = real_state(path)
        return (size, digest) if calls <= 5 else (size, "f" * 64)

    monkeypatch.setattr(module, "_artifact_state", unstable_state)
    output = paths["root"] / "must-not-exist"
    with pytest.raises(ValueError, match="INPUT_CHANGED_DURING_READ"):
        diagnose_development_v3_changes(
            baseline_core_path=paths["v2_core"],
            baseline_evidence_path=paths["v2_evidence"],
            experimental_core_path=paths["v3_core"],
            experimental_evidence_path=paths["v3_evidence"],
            development_identities_path=paths["identities"],
            output_directory=output,
            controlled_root=paths["root"],
            report_root=paths["root"],
            implementation_commit="a" * 40,
            production=False,
            expectation=_EXPECTATION,
        )
    assert not output.exists()

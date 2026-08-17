from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from phase03_helpers import (
    fictional_country_reference,
    fictional_script_reference,
    phase02_row,
)
from safe_geocoding_pipeline.execution_policy import ExecutionPolicyError
from safe_geocoding_pipeline.phase02.schema import base_staging_schema
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.constants import (
    LOCKED_EVALUATION_PROTOCOL_VERSION,
    PARSER_VERSION_V3_2,
)
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.locked_evaluation import (
    FROZEN_CANDIDATE_COMMIT,
    FROZEN_LOCKED_CONFIGURATION_SHA256,
    LOCKED_AGREEMENT_FIELDS,
    LOCKED_LABEL_FIELDS,
    LOCKED_REVIEW_SCHEMA_VERSION,
    AgreementResult,
    LockedDecisionInputs,
    LockedEvaluationContract,
    LockedMetricSet,
    LockedReviewBinding,
    LockedReviewCandidate,
    LockedReviewStore,
    MetricFraction,
    cohen_kappa,
    compare_locked_outputs,
    decide_locked_evaluation,
    locked_review_label_schema,
    locked_review_context_schema,
    materialize_locked_payload,
    protocol_summary,
    score_completed_locked_review,
    select_locked_review_population,
    transform_locked_pair_atomically,
    validate_preflight_report,
    validate_locked_preflight,
    validate_locked_review_labels,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry
from safe_geocoding_pipeline.phase03.references import load_production_references
from safe_geocoding_pipeline.phase03.targeted_review_population import (
    SCIENTIFIC_CORE_FIELDS,
)
from safe_geocoding_pipeline.phase03.writer import ShardWriteResult


def _identity(number: int) -> bytes:
    return number.to_bytes(32, "big")


def _candidate(number: int) -> LockedReviewCandidate:
    return LockedReviewCandidate(
        _identity(number),
        parser_changed=number < 30,
        experimental_evidence_state=(
            "SELECTED" if number < 120 else "UNSELECTED" if number < 260 else "NONE"
        ),
        country_group=f"COUNTRY:{number % 17:02d}",
        script_family=("LATIN", "NON_LATIN:Arabic", "MIXED")[number % 3],
        parse_status=("PARSED", "PARTIAL", "UNPARSEABLE")[number % 3],
        completeness=("A_POINT_CORE_WITH_POSTCODE", "G_OTHER_PARTIAL")[number % 2],
        conflict_state="CONFLICT_PRESENT" if number % 13 == 0 else "NO_CONFLICT",
    )


def _passing_agreements() -> tuple[AgreementResult, ...]:
    return tuple(
        AgreementResult(
            field,
            100,
            100,
            None,
            None,
            "UNDEFINED_DEGENERATE_MARGINALS",
            "PASS_FALLBACK_PERCENT_AGREEMENT",
        )
        for field in LOCKED_AGREEMENT_FIELDS
    )


def _passing_metrics() -> LockedMetricSet:
    return LockedMetricSet(
        MetricFraction(19, 20),
        MetricFraction(19, 20),
        MetricFraction(19, 20),
        MetricFraction(1, 20),
        MetricFraction(3, 100),
        3,
        MetricFraction(9, 10),
        MetricFraction(8, 10),
        MetricFraction(90, 100),
    )


def _valid_labels() -> dict[str, str]:
    return {
        "street_label": "CORRECT",
        "house_number_label": "CORRECT",
        "joint_street_house_label": "CORRECT",
        "residual_role_label": "NO_MEANINGFUL_RESIDUAL",
        "candidate_support_label": "SUPPORTED",
        "conflict_correctness_label": "NOT_APPLICABLE",
        "parser_overreach_label": "ABSENT",
        "missed_information_label": "ABSENT",
        "unsafe_handling_label": "ABSENT",
        "overall_parse_acceptability_label": "ACCEPTABLE",
    }


def _passing_machine_checks() -> dict[str, int | bool]:
    return {
        "unexplained_scientific_changes": 0,
        "unrelated_component_regressions": 0,
        "lost_existing_selections": 0,
        "provenance_failures": 0,
        "privacy_governance_failures": 0,
        "systematic_methodological_defect_detected": False,
        "unsafe_extraction_pattern_detected": False,
        "required_parser_rule_modification": False,
    }


def _staging_row(index: int, *, private_value: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for field in base_staging_schema():
        if pa.types.is_string(field.type):
            row[field.name] = ""
        elif pa.types.is_uint64(field.type):
            row[field.name] = index + 1
        else:
            row[field.name] = _identity(index)
    row.update(
        phase02_row(
            id=f"fictional-provider-{index}",
            street_address_line_1=private_value,
            source_file="fictional_locked.parquet",
            source_logical_record_number=index + 1,
            stable_source_row_id_v1=_identity(index),
            source_file_sha256=b"s" * 32,
        )
    )
    row.update(
        {
            "batch_priority": "fictional",
            "location_information": "no_geocoding_information",
            "source_schema_version": "fictional_source_v1",
            "parser_version": "fictional_phase02_parser_v1",
            "staging_version": "fictional_staging_v1",
        }
    )
    return row


def _portable_label_row(
    index: int, *, reviewer_id: str, independent: bool
) -> dict[str, Any]:
    return {
        "hashed_review_id": f"{index:064x}",
        "locked_evaluation_version": "fictional_locked_evaluation_v1",
        "reviewer_id": reviewer_id,
        "review_round": 1,
        "is_independent_review": independent,
        "assignment_role": (
            "PRIMARY" if reviewer_id == "LOCKED-R01" else "INDEPENDENT_SECOND"
        ),
        **_valid_labels(),
        "reason_codes": ["CORRECT_AS_IS"],
        "reason_codes_version": "manual_review_reason_codes_v1",
        "label_vocabulary_version": "phase03_locked_review_label_vocabularies_v1",
        "label_schema_version": LOCKED_REVIEW_SCHEMA_VERSION,
    }


def test_locked_contract_and_protocol_summary_are_frozen_and_sanitized() -> None:
    contract = LockedEvaluationContract()
    contract.validate()
    first = protocol_summary(locked_configuration_fingerprint=None)
    second = protocol_summary(locked_configuration_fingerprint=None)
    assert first == second
    assert first["protocol_fingerprint"] == (
        "c1b53fa6debfed25a2662c1130d06881bfbb07666b87263d791cfb5a444a9644"
    )
    assert first["candidate_commit"] == FROZEN_CANDIDATE_COMMIT
    assert first["locked_identity_count"] == 4_000
    assert first["review_population_count"] == 400
    assert first["independent_double_review_count"] == 100
    assert first["locked_effective_configuration_sha256"] == (
        FROZEN_LOCKED_CONFIGURATION_SHA256
    )
    assert first["locked_rows_read"] == 0
    serialized = json.dumps(first, sort_keys=True)
    for prohibited in ("/Users/", "/home/", "/work/", "street_address_line_1"):
        assert prohibited not in serialized


def test_locked_review_selection_is_exact_input_order_invariant_and_blinded() -> None:
    candidates = [_candidate(index) for index in range(4_000)]
    first = select_locked_review_population(candidates)
    second = select_locked_review_population(reversed(candidates))
    assert first == second
    assert len(first.review_ids) == 400
    assert len(first.double_review_ids) == 100
    assert set(first.double_review_ids) <= set(first.review_ids)
    assert set(first.reviewer_one_order) == set(first.review_ids)
    assert set(first.reviewer_two_order) == set(first.double_review_ids)
    assert first.reviewer_one_order != first.review_ids
    assert first.reviewer_two_order != first.double_review_ids
    assert set(_identity(index) for index in range(260)) <= set(first.review_ids)
    selected_by_id = {
        candidate.stable_source_row_id_v1: candidate for candidate in candidates
    }
    double = [selected_by_id[identity] for identity in first.double_review_ids]
    assert sum(item.experimental_evidence_state == "SELECTED" for item in double) >= 50
    assert (
        sum(item.experimental_evidence_state == "UNSELECTED" for item in double) >= 25
    )
    assert sum(item.parser_changed for item in double) >= 25


def test_locked_review_selection_fails_when_population_is_too_small() -> None:
    with pytest.raises(ValueError, match="fewer than 400"):
        select_locked_review_population(_candidate(index) for index in range(399))


def test_kappa_defined_undefined_and_insufficient_cases() -> None:
    first = ["CORRECT"] * 50 + ["INCORRECT"] * 50
    second = ["CORRECT"] * 45 + ["INCORRECT"] * 5 + ["INCORRECT"] * 45 + ["CORRECT"] * 5
    defined = cohen_kappa(first, second, field="street_label")
    assert defined.kappa_status == "DEFINED"
    assert defined.gate_status == "PASS"
    undefined = cohen_kappa(["CORRECT"] * 100, ["CORRECT"] * 100, field="street_label")
    assert undefined.kappa_status == "UNDEFINED_DEGENERATE_MARGINALS"
    assert undefined.gate_status == "PASS_FALLBACK_PERCENT_AGREEMENT"
    fallback_fail = cohen_kappa(
        ["CORRECT"] * 100,
        ["CORRECT"] * 94 + ["INCORRECT"] * 6,
        field="street_label",
    )
    assert fallback_fail.gate_status == "FAIL"
    insufficient = cohen_kappa(
        ["CANNOT_ASSESS"] * 21 + ["CORRECT"] * 79,
        ["CORRECT"] * 100,
        field="street_label",
    )
    assert insufficient.kappa_status == "INSUFFICIENT_DENOMINATOR"
    assert insufficient.gate_status == "FAIL"


def test_exact_precision_and_overreach_boundaries() -> None:
    assert (
        decide_locked_evaluation(
            LockedDecisionInputs(_passing_metrics(), _passing_agreements())
        )["status"]
        == "LOCKED_PASS"
    )
    below = _passing_metrics()
    below = LockedMetricSet(
        MetricFraction(18, 19),
        below.street_exact_precision,
        below.house_number_exact_precision,
        below.false_structure_overreach_rate,
        below.missed_information_rate,
        below.false_negative_opportunities,
        below.conflict_precision,
        below.conflict_recall,
        below.evidence_sidecar_coverage,
    )
    result = decide_locked_evaluation(
        LockedDecisionInputs(below, _passing_agreements())
    )
    assert result["status"] == "LOCKED_FAIL_REVISE"
    assert "JOINT_STREET_HOUSE_PRECISION_BELOW_0_95" in result["hard_gate_failures"]
    above_overreach = _passing_metrics()
    above_overreach = LockedMetricSet(
        above_overreach.joint_street_house_precision,
        above_overreach.street_exact_precision,
        above_overreach.house_number_exact_precision,
        MetricFraction(2, 39),
        above_overreach.missed_information_rate,
        above_overreach.false_negative_opportunities,
        above_overreach.conflict_precision,
        above_overreach.conflict_recall,
        above_overreach.evidence_sidecar_coverage,
    )
    result = decide_locked_evaluation(
        LockedDecisionInputs(above_overreach, _passing_agreements())
    )
    assert "FALSE_STRUCTURE_OVERREACH_ABOVE_0_05" in result["hard_gate_failures"]


@pytest.mark.parametrize(
    ("kwargs", "failure"),
    [
        ({"unexplained_scientific_changes": 1}, "UNEXPLAINED_SCIENTIFIC_OUTPUT_CHANGE"),
        ({"unrelated_component_regressions": 1}, "UNRELATED_COMPONENT_REGRESSION"),
        ({"provenance_failures": 1}, "PROVENANCE_HASH_OR_SEAL_FAILURE"),
        ({"privacy_governance_failures": 1}, "PRIVACY_OR_GOVERNANCE_FAILURE"),
        (
            {"methodological_defect_requires_change": True},
            "METHODOLOGICAL_DEFECT_REQUIRES_CHANGE",
        ),
    ],
)
def test_every_nonquantitative_hard_gate_fails(
    kwargs: dict[str, Any], failure: str
) -> None:
    inputs = LockedDecisionInputs(_passing_metrics(), _passing_agreements(), **kwargs)
    result = decide_locked_evaluation(inputs)
    assert result["status"] == "LOCKED_FAIL_REVISE"
    assert failure in result["hard_gate_failures"]
    assert result["automatic_parser_promotion"] is False


def test_locked_labels_are_closed_and_notes_never_enter_portable_schema() -> None:
    assert set(_valid_labels()) == set(LOCKED_LABEL_FIELDS)
    assert validate_locked_review_labels(
        _valid_labels(), ["CORRECT_AS_IS"], protected_note=None
    ) == ("CORRECT_AS_IS",)
    assert locked_review_label_schema().metadata is None
    assert "protected_note" not in locked_review_label_schema().names
    with pytest.raises(ValueError, match="invalid LOCKED review value"):
        validate_locked_review_labels(
            {**_valid_labels(), "street_label": "MAYBE"},
            ["CORRECT_AS_IS"],
            protected_note=None,
        )


def test_isolated_reviewer_stores_preserve_double_review_design(tmp_path: Path) -> None:
    binding = LockedReviewBinding(
        locked_evaluation_version="fictional_locked_v1",
        context_sha256="11" * 32,
        context_size_bytes=1,
        template_sha256="22" * 32,
        template_size_bytes=1,
        population_digest="33" * 32,
        implementation_commit="44" * 20,
        implementation_fingerprint="55" * 32,
    )
    first_ids = [f"{number:064x}" for number in range(400)]
    second_ids = set(first_ids[:100])
    with LockedReviewStore.create(
        tmp_path / "R01" / "progress.sqlite3",
        binding=binding,
        reviewer_id="LOCKED-R01",
        ordered_hashed_ids=first_ids,
        double_review_hashed_ids=second_ids,
    ) as first:
        assert first.summary()["assignment_count"] == 400
        first.save_completed(
            first_ids[0],
            _valid_labels(),
            ["CORRECT_AS_IS"],
            protected_note=None,
            timestamp_utc="2026-01-01T00:00:00Z",
        )
        assert first.summary()["complete_count"] == 1
    with LockedReviewStore.create(
        tmp_path / "R02" / "progress.sqlite3",
        binding=binding,
        reviewer_id="LOCKED-R02",
        ordered_hashed_ids=sorted(second_ids),
        double_review_hashed_ids=second_ids,
    ) as second:
        assert second.summary()["assignment_count"] == 100
        assert second.summary()["complete_count"] == 0


def test_v3_2_locked_scope_requires_exact_protocol_token(tmp_path: Path) -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
    registry = load_rule_registry(registry_version=config.rule_registry_version)
    country = fictional_country_reference(tmp_path)
    scripts = fictional_script_reference(tmp_path)
    with pytest.raises(Phase03Error, match="PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY"):
        Phase03Engine(
            config,
            registry,
            country_reference=country,
            script_reference=scripts,
            implementation_fingerprint=b"i" * 32,
            execution_scope="LOCKED_EVALUATION",
        )


def test_locked_production_reference_configuration_fingerprint_is_exact() -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
    registry = load_rule_registry(registry_version=config.rule_registry_version)
    country, scripts = load_production_references(
        expected_country_reference_id=config.country_reference_version,
        expected_unicode_reference_id=config.unicode_reference_version,
    )
    engine = Phase03Engine(
        config,
        registry,
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes(32),
        execution_scope="LOCKED_EVALUATION",
        locked_evaluation_protocol_version=LOCKED_EVALUATION_PROTOCOL_VERSION,
    )
    assert engine.configuration_fingerprint.hex() == (
        FROZEN_LOCKED_CONFIGURATION_SHA256
    )
    engine = Phase03Engine(
        config,
        registry,
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=b"i" * 32,
        execution_scope="LOCKED_EVALUATION",
        locked_evaluation_protocol_version=LOCKED_EVALUATION_PROTOCOL_VERSION,
    )
    assert engine.execution_scope == "LOCKED_EVALUATION"
    assert engine.configuration_fingerprint.hex() != (
        "89370fddf5f9dae8f381f62344df4da96f0b3dc34627cff23a8068555b909a73"
    )
    with pytest.raises(Phase03Error, match="PARSER_V3_EXPERIMENT_DEVELOPMENT_ONLY"):
        Phase03Engine(
            config,
            registry,
            country_reference=country,
            script_reference=scripts,
            implementation_fingerprint=b"i" * 32,
            execution_scope="AUTHORITATIVE",
            locked_evaluation_protocol_version=LOCKED_EVALUATION_PROTOCOL_VERSION,
        )


def test_production_locked_guards_run_before_input_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SAFE_EXECUTION_SITE", raising=False)
    monkeypatch.delenv("SLURM_JOB_ID", raising=False)
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        validate_locked_preflight(
            phase02_manifest_path=tmp_path / "missing-manifest.json",
            phase02_input_paths=[tmp_path / "missing.parquet"],
            locked_identities_path=tmp_path / "missing-identities.bin",
            pilot_seal_path=tmp_path / "missing-seal.json",
            output_path=tmp_path / "preflight.json",
            workflow_git_commit="66" * 20,
            production=True,
        )
    with pytest.raises(ExecutionPolicyError, match="HEAVY_PROCESS_CLUSTER_REQUIRED"):
        materialize_locked_payload(
            [tmp_path / "missing.parquet"],
            tmp_path / "payload.parquet",
            locked_ids={_identity(index) for index in range(4_000)},
            production=True,
        )


def test_review_schema_version_is_explicit() -> None:
    assert LOCKED_REVIEW_SCHEMA_VERSION == "phase03_locked_review_labels_v1"
    assert locked_review_label_schema().names == [
        "hashed_review_id",
        "locked_evaluation_version",
        "reviewer_id",
        "review_round",
        "is_independent_review",
        "assignment_role",
        *LOCKED_LABEL_FIELDS,
        "reason_codes",
        "reason_codes_version",
        "label_vocabulary_version",
        "label_schema_version",
    ]


def test_locked_domain_token_cannot_be_used_for_development(tmp_path: Path) -> None:
    config = Phase03Config.for_parser_version(PARSER_VERSION_V3_2)
    with pytest.raises(Phase03Error, match="LOCKED_EVALUATION_PROTOCOL_SCOPE_MISMATCH"):
        Phase03Engine(
            config,
            load_rule_registry(registry_version=config.rule_registry_version),
            country_reference=fictional_country_reference(tmp_path),
            script_reference=fictional_script_reference(tmp_path),
            implementation_fingerprint=b"i" * 32,
            execution_scope="DEVELOPMENT",
            locked_evaluation_protocol_version=LOCKED_EVALUATION_PROTOCOL_VERSION,
        )


def test_frozen_identity_digest_is_checked_before_payload_open(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="identity digest"):
        materialize_locked_payload(
            [tmp_path / "must-not-open.parquet"],
            tmp_path / "payload.parquet",
            locked_ids={_identity(index) for index in range(4_000)},
            production=False,
        )


def test_preflight_report_is_exact_and_fail_closed(tmp_path: Path) -> None:
    commit = "77" * 20
    summary = protocol_summary(locked_configuration_fingerprint=None)
    report = {
        "preflight_version": "phase03_locked_preflight_v1",
        "status": "PASS_NO_LOCKED_PAYLOAD_ROWS_READ",
        "protocol_version": LOCKED_EVALUATION_PROTOCOL_VERSION,
        "protocol_fingerprint": summary["protocol_fingerprint"],
        "workflow_git_commit": commit,
        "candidate_git_commit": FROZEN_CANDIDATE_COMMIT,
        "phase02_shard_count": 206,
        "locked_identity_count": 4_000,
        "locked_identity_digest": summary["locked_identity_digest"],
        "pilot_seal_sha256": (
            "ae1e9dd6eb927301eeaa33561aefc6c5197b22ab9eeea5bd8d37fcccce6616e7"
        ),
        "sampling_contract_sha256": (
            "0fb7527db5b6a7eb1c7d7eb86d4a038abf4d605728bfe9cf761c74cd33c6d1c7"
        ),
        "registry_version": "phase03_rule_registry_v5_experimental",
        "registry_sha256": (
            "4e66e0be62c3d0aae3e9452babe7d16f312c7bb49c69af1a2a0e6839cc3bb1fd"
        ),
        "locked_payload_rows_read": 0,
        "locked_payload_opened": False,
    }
    path = tmp_path / "preflight.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    assert validate_preflight_report(path, workflow_git_commit=commit) == report
    report["locked_payload_rows_read"] = 1
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="frozen protocol"):
        validate_preflight_report(path, workflow_git_commit=commit)


def test_locked_comparison_reports_every_changed_field_without_raw_values() -> None:
    baseline: list[dict[str, Any]] = []
    candidate: list[dict[str, Any]] = []
    for index in range(2):
        base = {field: None for field in SCIENTIFIC_CORE_FIELDS}
        base["stable_source_row_id_v1"] = _identity(index)
        base["street_clean"] = None
        base["house_number_clean"] = None
        base["country_parse_method"] = "CLDR_REFERENCE_EXACT"
        baseline.append(base)
        candidate.append(dict(base))
    candidate[0]["street_clean"] = "Fictional Street"
    candidate[0]["house_number_clean"] = "12"
    candidate[1]["country_parse_method"] = "STRUCTURED_ALPHA2_EXACT"
    evidence = [
        {
            "stable_source_row_id_v1": _identity(0),
            "rule_id": "STREET_EMBEDDED_DESIGNATOR_EXPERIMENT_V5",
            "selected": True,
        }
    ]
    result = compare_locked_outputs(baseline, candidate, evidence, expected_rows=2)
    assert result.scientific_change_rows == 2
    assert result.overlap_rows == 1
    assert result.changed_without_experimental_evidence == 1
    assert result.unrelated_component_regressions == 1
    assert result.country_parse_method_change_rows == 1
    assert result.native_component_change_rows == 0
    assert dict(result.changed_field_counts) == {
        "country_parse_method": 1,
        "house_number_clean": 1,
        "street_clean": 1,
    }
    assert dict(result.unrelated_changed_field_counts) == {"country_parse_method": 1}


def test_score_requires_all_machine_gates_and_emits_no_protected_values(
    tmp_path: Path,
) -> None:
    private_value = "Private Fictional Locked Address"
    context_rows: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    second_rows: list[dict[str, Any]] = []
    for index in range(400):
        context_rows.append(
            {
                **_staging_row(index, private_value=private_value),
                "hashed_review_id": f"{index:064x}",
                "baseline_core_json": "{}",
                "candidate_core_json": "{}",
                "baseline_evidence_json": "[]",
                "candidate_evidence_json": "[]",
                "locked_case_metadata_json": json.dumps(
                    {
                        "scientific_output_changed": index < 10,
                        "experimental_evidence_present": index < 200,
                        "experimental_selected": index < 100,
                        "street_selected": True,
                        "house_number_selected": True,
                        "conflict_present": False,
                        "evidence_sidecar_present": index < 200,
                        "country_group": f"COUNTRY:{index % 2}",
                        "script_family": "LATIN",
                        "parse_status": "PARTIAL",
                        "completeness": "G_OTHER_PARTIAL",
                        "conflict_state": "NO_CONFLICT",
                        "experimental_evidence_state": (
                            "SELECTED"
                            if index < 100
                            else "UNSELECTED"
                            if index < 200
                            else "NONE"
                        ),
                        "parser_change_state": (
                            "CHANGED" if index < 10 else "UNCHANGED"
                        ),
                    },
                    sort_keys=True,
                ),
            }
        )
        first_rows.append(
            _portable_label_row(
                index, reviewer_id="LOCKED-R01", independent=index < 100
            )
        )
        if index < 100:
            second_rows.append(
                _portable_label_row(index, reviewer_id="LOCKED-R02", independent=True)
            )
    context_path = tmp_path / "protected_context.parquet"
    labels_path = tmp_path / "controlled_labels.parquet"
    pq.write_table(
        pa.Table.from_pylist(context_rows, schema=locked_review_context_schema()),
        context_path,
        write_statistics=False,
        write_page_checksum=True,
    )
    pq.write_table(
        pa.Table.from_pylist(
            sorted(
                [*first_rows, *second_rows],
                key=lambda row: (row["hashed_review_id"], row["reviewer_id"]),
            ),
            schema=locked_review_label_schema(),
        ),
        labels_path,
        write_statistics=False,
        write_page_checksum=True,
    )
    review_manifest_path = tmp_path / "review_input_manifest.json"
    review_manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": "phase03_locked_review_input_manifest_v1",
                "status": "LOCKED_REVIEW_INPUT_PREPARED_NO_LABELS",
                "comparison": {
                    "changed_without_experimental_evidence": 0,
                    "unrelated_component_regressions": 0,
                    "lost_existing_selections": 0,
                },
                "output_artifacts": {
                    "protected_context": {
                        "sha256": hashlib.sha256(context_path.read_bytes()).hexdigest()
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="machine-check field mismatch"):
        score_completed_locked_review(
            controlled_labels_path=labels_path,
            context_path=context_path,
            review_input_manifest_path=review_manifest_path,
            output_path=tmp_path / "must-not-exist.json",
            machine_checks={},
        )
    output_path = tmp_path / "score.json"
    score = score_completed_locked_review(
        controlled_labels_path=labels_path,
        context_path=context_path,
        review_input_manifest_path=review_manifest_path,
        output_path=output_path,
        machine_checks=_passing_machine_checks(),
    )
    assert score["status"] == "LOCKED_PASS"
    assert score["stratified_metrics"]["country_group"]["reconciled_rows"] == 400
    serialized = output_path.read_text(encoding="utf-8")
    assert private_value not in serialized
    assert "fictional-provider" not in serialized
    assert '"automatic_promotion":false' in serialized


def test_atomic_pair_removes_partial_attempt_on_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = 0

    def fake_transform(
        _input: Path,
        output: Path,
        **_kwargs: Any,
    ) -> ShardWriteResult:
        nonlocal calls
        calls += 1
        output.mkdir(parents=True)
        if calls == 2:
            raise RuntimeError("fictional interruption")
        return ShardWriteResult(0, 0, "a", "b", "c", "d", 0, 0, True, ())

    monkeypatch.setattr(
        "safe_geocoding_pipeline.phase03.locked_evaluation.transform_locked_payload",
        fake_transform,
    )
    output = tmp_path / "final"
    with pytest.raises(RuntimeError, match="fictional interruption"):
        transform_locked_pair_atomically(
            tmp_path / "input.parquet",
            output,
            baseline_engine=object(),  # type: ignore[arg-type]
            candidate_engine=object(),  # type: ignore[arg-type]
            expected_locked_ids=set(),
            metadata={},
            production=False,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".final.transform.*"))


def test_locked_sbatch_separates_preflight_from_explicit_unseal() -> None:
    script = Path("cluster/goethe_nhr/phase03_locked_evaluation.sbatch").read_text(
        encoding="utf-8"
    )
    preflight_position = script.index('== "PREFLIGHT"')
    authorization_position = script.index("LOCKED_EVALUATION_EXPLICITLY_AUTHORIZED")
    open_position = script.index('== "OPEN_AND_PREPARE"')
    assert preflight_position < authorization_position < open_position
    assert "--preflight-report" in script
    assert "--locked-identities" in script
    assert "SCORE_AND_FINALIZE" in script
    assert "pilot-select" not in script
    assert "pelias" not in script.lower()
    assert "phase04" not in script.lower()

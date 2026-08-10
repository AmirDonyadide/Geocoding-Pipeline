from __future__ import annotations

import json
from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase03.errors import Phase03Error, ReferenceNotReadyError
from safe_geocoding_pipeline.phase03.references import (
    CountryReference,
    ReferenceManifest,
    require_production_country_reference,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

from phase03_helpers import fictional_country_reference, fictional_script_reference


def test_bundled_rule_registry_is_canonical_deterministic_and_closed() -> None:
    first = load_rule_registry()
    second = load_rule_registry()
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint == (
        "d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5"
    )
    assert first.registry_version == "phase03_rule_registry_v2"
    assert len(first.rules) == 12
    assert [rule.rule_id for rule in first.ordered_rules()] == [
        rule.rule_id for rule in first.rules
    ]
    assert all(rule.required_tests for rule in first.rules)
    assert all(rule.confidence in {"HIGH", "MEDIUM", "LOW"} for rule in first.rules)
    assert all(not rule.rule_id.startswith("<function") for rule in first.rules)


def test_rule_registry_rejects_undocumented_matcher(tmp_path: Path) -> None:
    value = json.loads(
        Path(
            "src/safe_geocoding_pipeline/phase03/resources/rule_registry_v2.json"
        ).read_text()
    )
    value["rules"][0]["matching_condition"]["matcher"] = "ARBITRARY_PYTHON"
    path = tmp_path / "bad_registry.json"
    path.write_text(json.dumps(value))
    with pytest.raises(Phase03Error, match="RULE_REGISTRY_INVALID"):
        load_rule_registry(path)


def test_rule_registry_rejects_untyped_or_extra_matcher_parameters(
    tmp_path: Path,
) -> None:
    value = json.loads(
        Path(
            "src/safe_geocoding_pipeline/phase03/resources/rule_registry_v2.json"
        ).read_text()
    )
    value["rules"][5]["matching_condition"]["parameters"][
        "identifier_max_codepoints"
    ] = "32"
    path = tmp_path / "wrong_type_registry.json"
    path.write_text(json.dumps(value))
    with pytest.raises(Phase03Error, match="RULE_REGISTRY_INVALID"):
        load_rule_registry(path)
    value["rules"][5]["matching_condition"]["parameters"][
        "identifier_max_codepoints"
    ] = 32
    value["rules"][5]["matching_condition"]["parameters"]["extra"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(Phase03Error, match="RULE_REGISTRY_INVALID"):
        load_rule_registry(path)


def test_country_reference_roles_hashes_and_exact_lookup(tmp_path: Path) -> None:
    reference = fictional_country_reference(tmp_path)
    record, kind = reference.exact_lookup("NA")
    assert record is not None and record.alpha2 == "NA" and kind == "ALPHA2"
    record, kind = reference.exact_lookup("Namibia")
    assert record is not None and record.alpha3 == "NAM" and kind == "NAME"
    assert reference.exact_lookup("na") == (None, "NONE")
    assert "fictional" in reference.version


def test_reference_manifest_and_missing_production_reference_fail_closed() -> None:
    with pytest.raises(Phase03Error, match="REFERENCE_MANIFEST_INVALID"):
        ReferenceManifest.from_mapping({"reference_id": "incomplete"})
    with pytest.raises(Phase03Error, match="REFERENCE_MANIFEST_INVALID"):
        ReferenceManifest.from_mapping(
            {
                "reference_id": "fictional",
                "authority_role": "NAME_MAPPING",
                "source": None,
                "vintage": "v1",
                "retrieved_at_utc": "2026-01-01T00:00:00Z",
                "artifact_file_name": "fictional.json",
                "artifact_sha256": "00" * 32,
                "artifact_size_bytes": 1,
                "loader_schema_version": "fictional_v1",
                "license_name": "Fictional",
                "license_identifier": "LicenseRef-Fictional",
                "license_note": "fictional",
                "redistribution_policy": "VENDORED",
                "validation_status": "PASS",
            }
        )
    with pytest.raises(ReferenceNotReadyError, match="COUNTRY_REFERENCE_NOT_READY"):
        require_production_country_reference(None)


def test_reference_manifest_rejects_noncanonical_uppercase_hash() -> None:
    with pytest.raises(Phase03Error, match="REFERENCE_MANIFEST_INVALID"):
        ReferenceManifest.from_mapping(
            {
                "reference_id": "fictional",
                "authority_role": "NAME_MAPPING",
                "source": "fictional:test",
                "vintage": "v1",
                "retrieved_at_utc": "2026-01-01T00:00:00Z",
                "artifact_file_name": "fictional.json",
                "artifact_sha256": "AB" * 32,
                "artifact_size_bytes": 1,
                "loader_schema_version": "fictional_v1",
                "license_name": "Fictional",
                "license_identifier": "LicenseRef-Fictional",
                "license_note": "fictional",
                "redistribution_policy": "VENDORED",
                "validation_status": "PASS",
            }
        )


def test_script_reference_ignores_common_inherited_and_classifies(
    tmp_path: Path,
) -> None:
    scripts = fictional_script_reference(tmp_path)
    assert scripts.distinctive_scripts("ABC123") == {"Latin"}
    assert scripts.distinctive_scripts("123") == set()
    assert scripts.distinctive_scripts("AБ") == {"Latin", "Cyrillic"}
    assert scripts.script_for("\u0301") == "Inherited"


def test_reference_artifact_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    reference = fictional_country_reference(tmp_path)
    assert reference.records
    assignment_manifest = tmp_path / "assignment_manifest.json"
    assignments = tmp_path / "fictional_assignments.json"
    assignments.write_text("[]")
    name_manifest = tmp_path / "name_manifest.json"
    names = tmp_path / "fictional_names.json"
    with pytest.raises(Phase03Error, match="REFERENCE_ARTIFACT_HASH_MISMATCH"):
        CountryReference.from_artifacts(
            assignment_manifest, assignments, name_manifest, names
        )

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import (
    CountryReference,
    ScriptReference,
    load_manifest,
    load_production_references,
    production_reference_paths,
    validate_country_authority_manifest,
)
from safe_geocoding_pipeline.phase03.reference_pinning import (
    extract_un_m49_country_area_json,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

from phase03_helpers import phase02_row

EXPECTED_UNICODE_SHA256 = (
    "9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039"
)
EXPECTED_COUNTRY_SHA256 = (
    "c6bb72998f4cbdd174a941115556b1370d464471fb08ba36ec80f59f7e9581bb"
)
DEFAULT_COUNTRY_ARTIFACT = Path(
    "external_data/phase03/references/un_m49_20260810T203327Z/"
    "un_m49_country_area_codes_v1.json"
)
DEFAULT_COUNTRY_SOURCE_SNAPSHOT = Path(
    "external_data/phase03/references/un_m49_20260810T203327Z/"
    "UNSD_M49_overview_20260810.html"
)


def _country_artifact() -> Path:
    configured = os.environ.get("PHASE03_COUNTRY_REFERENCE_ARTIFACT")
    return Path(configured) if configured else DEFAULT_COUNTRY_ARTIFACT


def test_production_reference_manifests_pin_exact_identities_and_roles() -> None:
    paths = production_reference_paths()
    unicode_manifest = load_manifest(paths["unicode_manifest"])
    country_manifest = load_manifest(paths["country_manifest"])
    assert unicode_manifest.artifact_sha256 == EXPECTED_UNICODE_SHA256
    assert unicode_manifest.artifact_size_bytes == 189_588
    assert unicode_manifest.unicode_version == "16.0.0"
    assert unicode_manifest.authority_role == "UNICODE_SCRIPT_PROPERTY"
    assert unicode_manifest.license_identifier == "Unicode-3.0"
    assert hashlib.sha256(paths["unicode_license"].read_bytes()).hexdigest() == (
        "e7a93b009565cfce55919a381437ac4db883e9da2126fa28b91d12732bc53d96"
    )
    assert country_manifest.artifact_sha256 == EXPECTED_COUNTRY_SHA256
    assert country_manifest.artifact_size_bytes == 23_218
    assert country_manifest.row_count == 248
    assert country_manifest.authority_role == "OPERATIONAL_COUNTRY_MAPPING"
    authority = json.loads(paths["country_authority_manifest"].read_text())
    assert authority["normative_authority"]["organization"].startswith(
        "International Organization for Standardization"
    )
    assert authority["operational_reference"]["organization"] == (
        "United Nations Statistics Division"
    )
    validated = validate_country_authority_manifest(
        paths["country_authority_manifest"], country_manifest
    )
    assert validated["country_reference_id"] == authority["country_reference_id"]


def test_production_unicode_scripts_load_completely_and_match_runtime() -> None:
    import unicodedata

    paths = production_reference_paths()
    data = paths["unicode_artifact"].read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED_UNICODE_SHA256
    scripts = ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )
    assert unicodedata.unidata_version == "16.0.0"
    assert len(scripts.ranges) == 2_253
    assert scripts.script_for("A") == "Latin"
    assert scripts.script_for("Б") == "Cyrillic"
    assert scripts.script_for("1") == "Common"
    assert scripts.script_for("\u0301") == "Inherited"
    assert scripts.distinctive_scripts("A1\u0301") == {"Latin"}


def test_production_country_mapping_is_exact_unique_and_consistent() -> None:
    artifact = _country_artifact()
    if not artifact.exists():
        pytest.skip("controlled UN M49 operational artifact is not provisioned")
    paths = production_reference_paths()
    data = artifact.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED_COUNTRY_SHA256
    reference = CountryReference.from_operational_artifact(
        paths["country_manifest"], artifact
    )
    assert len(reference.records) == 248
    assert len({record.alpha2 for record in reference.records}) == 248
    assert len({record.alpha3 for record in reference.records}) == 248
    assert len({record.m49_code for record in reference.records}) == 248
    assert len({record.names[0] for record in reference.records}) == 248
    namibia, kind = reference.exact_lookup("NA")
    assert namibia is not None and namibia.alpha3 == "NAM" and kind == "ALPHA2"
    assert reference.exact_lookup("Na") == (None, "NONE")


def test_controlled_un_source_snapshot_reproduces_canonical_artifact() -> None:
    artifact = _country_artifact()
    if not artifact.exists() or not DEFAULT_COUNTRY_SOURCE_SNAPSHOT.exists():
        pytest.skip("controlled UN M49 source snapshot is not provisioned")
    extracted = extract_un_m49_country_area_json(
        DEFAULT_COUNTRY_SOURCE_SNAPSHOT.read_bytes()
    )
    assert extracted == artifact.read_bytes()
    assert hashlib.sha256(extracted).hexdigest() == EXPECTED_COUNTRY_SHA256


def test_production_references_reject_corruption_role_and_version(
    tmp_path: Path,
) -> None:
    artifact = _country_artifact()
    if not artifact.exists():
        pytest.skip("controlled UN M49 operational artifact is not provisioned")
    paths = production_reference_paths()
    corrupt = tmp_path / artifact.name
    corrupt.write_bytes(artifact.read_bytes() + b"\n")
    with pytest.raises(Phase03Error, match="REFERENCE_ARTIFACT_HASH_MISMATCH"):
        CountryReference.from_operational_artifact(paths["country_manifest"], corrupt)

    manifest_value = json.loads(paths["country_manifest"].read_text())
    wrong_role = tmp_path / "wrong-role.json"
    manifest_value["authority_role"] = "NORMATIVE_CODE_VALIDATION"
    wrong_role.write_text(json.dumps(manifest_value))
    with pytest.raises(Phase03Error, match="COUNTRY_REFERENCE_ROLE_MISMATCH"):
        CountryReference.from_operational_artifact(wrong_role, artifact)

    manifest_value["authority_role"] = "OPERATIONAL_COUNTRY_MAPPING"
    manifest_value["loader_schema_version"] = "un_m49_country_area_json_v2"
    wrong_version = tmp_path / "wrong-version.json"
    wrong_version.write_text(json.dumps(manifest_value))
    with pytest.raises(Phase03Error, match="COUNTRY_REFERENCE_SCHEMA_UNSUPPORTED"):
        CountryReference.from_operational_artifact(wrong_version, artifact)

    unicode_value = json.loads(paths["unicode_manifest"].read_text())
    unicode_value["unicode_version"] = "17.0.0"
    wrong_unicode = tmp_path / "wrong-unicode.json"
    wrong_unicode.write_text(json.dumps(unicode_value))
    with pytest.raises(Phase03Error, match="SCRIPT_REFERENCE_VERSION_OR_ROLE_MISMATCH"):
        ScriptReference.from_artifact(wrong_unicode, paths["unicode_artifact"])


def test_production_country_behavior_is_exact_and_collision_guarded() -> None:
    artifact = _country_artifact()
    if not artifact.exists():
        pytest.skip("controlled UN M49 operational artifact is not provisioned")
    paths = production_reference_paths()
    country = CountryReference.from_operational_artifact(
        paths["country_manifest"], artifact
    )
    scripts = ScriptReference.from_artifact(
        paths["unicode_manifest"], paths["unicode_artifact"]
    )
    parser = Phase03Engine(
        Phase03Config(),
        load_rule_registry(),
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes.fromhex("44" * 32),
        execution_scope="DEVELOPMENT",
    )

    expectations = {
        "NA": ("NA", "ALPHA2_ASSIGNED_EXACT"),
        "NAM": ("NA", "ALPHA3_ASSIGNED_EXACT"),
        "Namibia": ("NA", "COUNTRY_NAME_EXACT"),
        "na": (None, "ALPHA2_CASE_VARIANT"),
        "nA": (None, "ALPHA2_CASE_VARIANT"),
        "ZZ": (None, "UNKNOWN_TEXT"),
        "Southern Africa": (None, "REGION_LIKE"),
        ".": (None, "SEMANTIC_MISSING"),
        "Na": (None, "AMBIGUOUS_PLACEHOLDER_LIKE"),
    }
    for raw, (selected, input_class) in expectations.items():
        result = parser.transform(phase02_row(country_iso_code=raw))
        assert result.core_row["country_clean"] == selected
        assert result.core_row["country_input_class"] == input_class

    corroborated = parser.transform(
        phase02_row(country_iso_code="Na", street_address_line_4="Namibia")
    )
    assert corroborated.core_row["country_clean"] == "NA"
    assert corroborated.core_row["country_parse_method"] == (
        "MULTISOURCE_CORROBORATED_PLACEHOLDER_COLLISION"
    )


def test_production_startup_binds_configured_reference_identities() -> None:
    artifact = _country_artifact()
    if not artifact.exists():
        pytest.skip("controlled UN M49 operational artifact is not provisioned")
    country, scripts = load_production_references(
        artifact,
        expected_country_reference_id=(
            "country_reference_v1_iso_normative_unsd_m49_operational_20260810"
        ),
        expected_unicode_reference_id="unicode_ucd_16_0_0_scripts_20240430",
    )
    assert len(country.records) == 248
    assert scripts.version == "unicode_ucd_16_0_0_scripts_20240430"
    with pytest.raises(Phase03Error, match="COUNTRY_AUTHORITY_MANIFEST_INVALID"):
        load_production_references(
            artifact,
            expected_country_reference_id="wrong_country_reference",
            expected_unicode_reference_id="unicode_ucd_16_0_0_scripts_20240430",
        )
    with pytest.raises(Phase03Error, match="PRODUCTION_UNICODE_REFERENCE_ID_MISMATCH"):
        load_production_references(
            artifact,
            expected_country_reference_id=(
                "country_reference_v1_iso_normative_unsd_m49_operational_20260810"
            ),
            expected_unicode_reference_id="wrong_unicode_reference",
        )

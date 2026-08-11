from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.errors import Phase03Error
from safe_geocoding_pipeline.phase03.reference_pinning import (
    CLDR_COUNTRY_REFERENCE_ID,
    CLDR_COUNTRY_SCHEMA_VERSION,
    CLDR_COUNTRY_EXTRACTOR_VERSION,
    CLDR_RELEASE,
    CLDR_SELECTABLE_POLICY_VERSION,
    CldrCountryExtraction,
    cldr_extractor_configuration_fingerprint,
    extract_cldr_country_reference,
)
from safe_geocoding_pipeline.phase03.references import (
    CountryReference,
    ScriptReference,
    load_manifest,
    load_production_references,
    production_reference_paths,
    validate_country_authority_manifest,
    verify_cldr_reference_bundle,
)
from safe_geocoding_pipeline.phase03.rules import load_rule_registry

from phase03_helpers import phase02_row

EXPECTED_UNICODE_SHA256 = (
    "9e88f0a677df47311106340be8ede2ecdacd9c1c931831218d2be6d5508e0039"
)
EXPECTED_CLDR_ARCHIVE_SHA256 = (
    "c3828c9280c6b3bb921bc96baf53be2174b5416d72e740ec3915c1ff91a50a80"
)
EXPECTED_CLDR_CANONICAL_SHA256 = (
    "6d38c9431a97dff511da8048381de42b27c5eef7b9a94409400f16f3d332325a"
)
EXPECTED_CLDR_SOURCE_HASHES = {
    "supplementalData.xml": (
        "277105238ecaab5b0e476f3bc7d25a26358227c5c77d02b0921d311c3f940dbf"
    ),
    "en.xml": "5ac57cec48ab8d9a87cbd920444024ccdcc914ae6ffa4353f6e17bc0a9f8d6e7",
    "region.xml": (
        "e751e0eedd46b52c38f3cdb72b0fab61ac8b48e052e8b28ba74b6ac26c4c8cb1"
    ),
}


def _extract() -> CldrCountryExtraction:
    paths = production_reference_paths()
    return extract_cldr_country_reference(
        supplemental_data_xml=paths["country_supplemental_data"].read_bytes(),
        english_territories_xml=paths["country_english_names"].read_bytes(),
        region_validity_xml=paths["country_region_validity"].read_bytes(),
    )


def test_production_reference_manifests_pin_exact_identities_and_roles() -> None:
    paths = production_reference_paths()
    assert all("un_m49" not in path.as_posix().lower() for path in paths.values())
    unicode_manifest = load_manifest(paths["unicode_manifest"])
    country_manifest = verify_cldr_reference_bundle(
        paths["country_manifest"], paths["country_directory"]
    )
    assert unicode_manifest.artifact_sha256 == EXPECTED_UNICODE_SHA256
    assert unicode_manifest.artifact_size_bytes == 189_588
    assert unicode_manifest.unicode_version == "16.0.0"
    assert unicode_manifest.authority_role == "UNICODE_SCRIPT_PROPERTY"
    assert unicode_manifest.license_identifier == "Unicode-3.0"
    assert country_manifest.reference_id == CLDR_COUNTRY_REFERENCE_ID
    assert country_manifest.artifact_sha256 == EXPECTED_CLDR_CANONICAL_SHA256
    assert country_manifest.artifact_size_bytes == 23_477
    assert country_manifest.row_count == 249
    assert country_manifest.authority_role == "OPERATIONAL_COUNTRY_MAPPING"
    assert country_manifest.license_identifier == "Unicode-3.0"
    authority = validate_country_authority_manifest(
        paths["country_authority_manifest"],
        country_manifest,
        operational_manifest_path=paths["country_manifest"],
        expected_country_reference_id=CLDR_COUNTRY_REFERENCE_ID,
    )
    assert authority["normative_authority"]["role"] == "normative_code_system"
    assert authority["operational_reference"]["organization"] == (
        "Unicode Consortium"
    )
    assert "superseded_operational_reference" not in authority


def test_cldr_release_sources_license_and_extractor_are_exactly_pinned() -> None:
    paths = production_reference_paths()
    manifest = json.loads(paths["country_manifest"].read_text(encoding="utf-8"))
    assert manifest["cldr_release"] == CLDR_RELEASE == "46.1"
    assert manifest["release_artifact"]["artifact_sha256"] == (
        EXPECTED_CLDR_ARCHIVE_SHA256
    )
    assert manifest["release_artifact"]["artifact_size_bytes"] == 34_308_024
    assert manifest["extractor"] == {
        "configuration_fingerprint": cldr_extractor_configuration_fingerprint(),
        "version": CLDR_COUNTRY_EXTRACTOR_VERSION,
    }
    assert manifest["loader_schema_version"] == CLDR_COUNTRY_SCHEMA_VERSION
    assert manifest["license_identifier"] == "Unicode-3.0"
    for name, expected_hash in EXPECTED_CLDR_SOURCE_HASHES.items():
        assert hashlib.sha256((paths["country_directory"] / name).read_bytes()).hexdigest() == expected_hash
    license_data = paths["country_license"].read_bytes()
    assert hashlib.sha256(license_data).hexdigest() == (
        "4e6e762822c88cf41c072b93568f3e1a6784b5b013e82bf42a61bb7a018d9239"
    )
    assert b"SPDX-License-Identifier: Unicode-3.0" in license_data


def test_cldr_extraction_is_reproducible_unique_and_conservative() -> None:
    first = _extract()
    second = _extract()
    assert first == second
    assert first.row_count == 249
    assert hashlib.sha256(first.canonical_artifact).hexdigest() == (
        EXPECTED_CLDR_CANONICAL_SHA256
    )
    assert first.status_counts == {
        "deprecated": 12,
        "macroregion": 35,
        "private_use": 23,
        "regular": 257,
        "reserved": 13,
        "special": 2,
        "unknown": 1,
    }
    assert first.excluded_identifiers["regular_missing_required_mapping"] == (
        "AC",
        "CP",
        "CQ",
        "DG",
        "EA",
        "IC",
        "TA",
    )
    assert first.excluded_identifiers["iso_user_assigned"] == ("XK",)
    value = json.loads(first.canonical_artifact)
    records = value["records"]
    assert len({row["territory_code"] for row in records}) == 249
    assert len({row["alpha3_code"] for row in records}) == 249
    assert len({row["numeric_code"] for row in records}) == 249
    assert len({row["english_name"] for row in records}) == 249
    assert all(isinstance(row["numeric_code"], str) for row in records)
    assert {"001", "EU", "XA", "XK", "ZZ"}.isdisjoint(
        {row["territory_code"] for row in records}
    )


def test_production_unicode_scripts_load_completely_and_match_runtime() -> None:
    import unicodedata

    paths = production_reference_paths()
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
    paths = production_reference_paths()
    reference = CountryReference.from_cldr_artifact(
        paths["country_manifest"], paths["country_artifact"]
    )
    assert len(reference.records) == 249
    assert len({record.alpha2 for record in reference.records}) == 249
    assert len({record.alpha3 for record in reference.records}) == 249
    assert len({record.numeric_code for record in reference.records}) == 249
    assert len({record.names[0] for record in reference.records}) == 249
    namibia, kind = reference.exact_lookup("NA")
    assert namibia is not None and namibia.alpha3 == "NAM" and kind == "ALPHA2"
    assert reference.exact_lookup("Na") == (None, "NONE")
    assert reference.exact_lookup("XK") == (None, "NONE")
    assert reference.exact_lookup("Aotearoa New Zealand") == (None, "NONE")


def test_cldr_fail_closed_for_malformed_missing_duplicate_and_changed_sources() -> None:
    paths = production_reference_paths()
    with pytest.raises(Phase03Error, match="CLDR_SOURCE_XML_INVALID"):
        extract_cldr_country_reference(
            supplemental_data_xml=b"<broken>",
            english_territories_xml=paths["country_english_names"].read_bytes(),
            region_validity_xml=paths["country_region_validity"].read_bytes(),
        )
    missing = paths["country_supplemental_data"].read_bytes().replace(
        b'<territoryCodes type="NA" numeric="516" alpha3="NAM" fips10="WA"/>',
        b'<territoryCodes type="NA" alpha3="NAM" fips10="WA"/>',
    )
    result = extract_cldr_country_reference(
        supplemental_data_xml=missing,
        english_territories_xml=paths["country_english_names"].read_bytes(),
        region_validity_xml=paths["country_region_validity"].read_bytes(),
    )
    assert "NA" in result.excluded_identifiers["regular_missing_required_mapping"]
    duplicate = paths["country_supplemental_data"].read_bytes().replace(
        b"</codeMappings>",
        b'<territoryCodes type="NA" numeric="516" alpha3="NAM"/></codeMappings>',
    )
    with pytest.raises(Phase03Error, match="CLDR_CODE_MAPPING_DUPLICATE"):
        extract_cldr_country_reference(
            supplemental_data_xml=duplicate,
            english_territories_xml=paths["country_english_names"].read_bytes(),
            region_validity_xml=paths["country_region_validity"].read_bytes(),
        )


@pytest.mark.parametrize(
    ("old", "new", "detail"),
    [
        (b'numeric="554"', b'numeric="516"', "numeric_code"),
        (b'alpha3="NZL"', b'alpha3="NAM"', "alpha3_code"),
    ],
)
def test_cldr_extraction_rejects_duplicate_mapped_codes(
    old: bytes, new: bytes, detail: str
) -> None:
    paths = production_reference_paths()
    source = paths["country_supplemental_data"].read_bytes()
    old_row = b'<territoryCodes type="NZ" numeric="554" alpha3="NZL"/>'
    changed_row = old_row.replace(old, new)
    changed = source.replace(old_row, changed_row)
    with pytest.raises(Phase03Error) as failure:
        extract_cldr_country_reference(
            supplemental_data_xml=changed,
            english_territories_xml=paths["country_english_names"].read_bytes(),
            region_validity_xml=paths["country_region_validity"].read_bytes(),
        )
    assert failure.value.code == "CLDR_CANONICAL_MAPPING_DUPLICATE"
    assert failure.value.detail == detail


def test_cldr_extraction_rejects_duplicate_canonical_name() -> None:
    paths = production_reference_paths()
    names = paths["country_english_names"].read_bytes().replace(
        b'<territory type="NZ">New Zealand</territory>',
        b'<territory type="NZ">Namibia</territory>',
    )
    with pytest.raises(Phase03Error) as failure:
        extract_cldr_country_reference(
            supplemental_data_xml=paths["country_supplemental_data"].read_bytes(),
            english_territories_xml=names,
            region_validity_xml=paths["country_region_validity"].read_bytes(),
        )
    assert failure.value.code == "CLDR_CANONICAL_MAPPING_DUPLICATE"
    assert failure.value.detail == "english_name"


def test_cldr_bundle_rejects_corruption_wrong_role_and_wrong_release(
    tmp_path: Path,
) -> None:
    paths = production_reference_paths()
    copied = tmp_path / "cldr"
    shutil.copytree(paths["country_directory"], copied)
    (copied / "en.xml").write_bytes((copied / "en.xml").read_bytes() + b"\n")
    with pytest.raises(Phase03Error, match="CLDR_SOURCE_ARTIFACT_MISMATCH"):
        verify_cldr_reference_bundle(copied / "manifest.json", copied)

    manifest_value = json.loads(paths["country_manifest"].read_text())
    manifest_value["authority_role"] = "NORMATIVE_CODE_VALIDATION"
    wrong_role = tmp_path / "wrong-role.json"
    wrong_role.write_text(json.dumps(manifest_value), encoding="utf-8")
    with pytest.raises(Phase03Error, match="CLDR_MANIFEST_INVALID"):
        verify_cldr_reference_bundle(wrong_role, paths["country_directory"])

    manifest_value["authority_role"] = "OPERATIONAL_COUNTRY_MAPPING"
    manifest_value["cldr_release"] = "48"
    wrong_release = tmp_path / "wrong-release.json"
    wrong_release.write_text(json.dumps(manifest_value), encoding="utf-8")
    with pytest.raises(Phase03Error, match="CLDR_MANIFEST_INVALID"):
        verify_cldr_reference_bundle(wrong_release, paths["country_directory"])


def test_production_country_behavior_is_exact_and_collision_guarded() -> None:
    country, scripts = load_production_references(
        expected_country_reference_id=CLDR_COUNTRY_REFERENCE_ID,
        expected_unicode_reference_id="unicode_ucd_16_0_0_scripts_20240430",
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
        "namibia": (None, "UNKNOWN_TEXT"),
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


def test_production_startup_binds_reference_identity_and_fails_closed() -> None:
    country, scripts = load_production_references(
        expected_country_reference_id=CLDR_COUNTRY_REFERENCE_ID,
        expected_unicode_reference_id="unicode_ucd_16_0_0_scripts_20240430",
    )
    assert len(country.records) == 249
    assert scripts.version == "unicode_ucd_16_0_0_scripts_20240430"
    with pytest.raises(Phase03Error, match="COUNTRY_AUTHORITY_MANIFEST_INVALID"):
        load_production_references(
            expected_country_reference_id="wrong_country_reference",
            expected_unicode_reference_id="unicode_ucd_16_0_0_scripts_20240430",
        )
    with pytest.raises(Phase03Error, match="PRODUCTION_UNICODE_REFERENCE_ID_MISMATCH"):
        load_production_references(
            expected_country_reference_id=CLDR_COUNTRY_REFERENCE_ID,
            expected_unicode_reference_id="wrong_unicode_reference",
        )


def test_country_reference_change_is_bound_into_configuration_fingerprint() -> None:
    cldr = Phase03Config()
    historical = Phase03Config(
        country_reference_version=(
            "country_reference_v1_iso_normative_unsd_m49_operational_20260810"
        )
    )
    assert cldr.configuration_fingerprint() != historical.configuration_fingerprint()
    assert cldr.configuration_fingerprint().hex() == (
        "e5d8821750f6454fa9e9d4d12c9181412438eda6e0f74a191a5a9fdbc4f00002"
    )
    assert cldr.country_reference_version == CLDR_COUNTRY_REFERENCE_ID
    assert CLDR_SELECTABLE_POLICY_VERSION == "cldr_country_selectability_v1"

    country, scripts = load_production_references(
        expected_country_reference_id=cldr.country_reference_version,
        expected_unicode_reference_id=cldr.unicode_reference_version,
    )
    effective = Phase03Engine(
        cldr,
        load_rule_registry(),
        country_reference=country,
        script_reference=scripts,
        implementation_fingerprint=bytes.fromhex("44" * 32),
        execution_scope="DEVELOPMENT",
    )
    assert effective.configuration_fingerprint.hex() == (
        "92c80594f547716359318924522a1a2ef76dbd1b96b397ec070674e0437a48cc"
    )

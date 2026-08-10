from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from safe_geocoding_pipeline.phase03.config import Phase03Config
from safe_geocoding_pipeline.phase03.engine import Phase03Engine
from safe_geocoding_pipeline.phase03.references import CountryReference, ScriptReference
from safe_geocoding_pipeline.phase03.rules import load_rule_registry


def phase02_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": "fictional-provider-0001",
        "street_address_line_1": "",
        "street_address_line_2": "",
        "street_address_line_3": "",
        "street_address_line_4": "",
        "street_address_line_1_native": "",
        "street_address_line_2_native": "",
        "street_address_line_3_native": "",
        "street_address_line_4_native": "",
        "postcode": "",
        "city": "",
        "region_in_country": "",
        "country_iso_code": "",
        "source_file": "fictional_00001.parquet",
        "source_logical_record_number": 1,
        "stable_source_row_id_v1": bytes.fromhex("11" * 32),
        "source_file_sha256": bytes.fromhex("22" * 32),
    }
    row.update(overrides)
    return row


def _write_artifact(path: Path, value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _write_manifest(
    path: Path,
    *,
    reference_id: str,
    authority_role: str,
    artifact_sha256: str,
    loader_schema_version: str,
    unicode_version: str | None = None,
) -> None:
    artifact_file_name = {
        "country_assignments_json_v1": "fictional_assignments.json",
        "country_names_json_v1": "fictional_names.json",
        "unicode_scripts_txt_v1": "FictionalScripts.txt",
    }[loader_schema_version]
    payload: dict[str, object] = {
        "reference_id": reference_id,
        "authority_role": authority_role,
        "source": "fictional:test-only",
        "vintage": "fictional-v1",
        "retrieved_at_utc": "2026-01-01T00:00:00Z",
        "artifact_file_name": artifact_file_name,
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": (path.parent / artifact_file_name).stat().st_size,
        "loader_schema_version": loader_schema_version,
        "license_name": "Fictional test license",
        "license_identifier": "LicenseRef-Fictional-Test",
        "license_note": "fictional test fixture; no production authority",
        "redistribution_policy": "VENDORED",
        "validation_status": "PASS",
    }
    if unicode_version is not None:
        payload["unicode_version"] = unicode_version
    path.write_text(json.dumps(payload), encoding="utf-8")


def fictional_country_reference(tmp_path: Path) -> CountryReference:
    assignments = tmp_path / "fictional_assignments.json"
    names = tmp_path / "fictional_names.json"
    assignment_hash = _write_artifact(
        assignments,
        [
            {"alpha2": "NA", "alpha3": "NAM"},
            {"alpha2": "XZ", "alpha3": "XZZ"},
        ],
    )
    name_hash = _write_artifact(
        names,
        [
            {"alpha2": "NA", "names": ["Namibia"]},
            {"alpha2": "XZ", "names": ["Fictionland"]},
        ],
    )
    assignment_manifest = tmp_path / "assignment_manifest.json"
    name_manifest = tmp_path / "name_manifest.json"
    _write_manifest(
        assignment_manifest,
        reference_id="fictional_assignments_v1",
        authority_role="NORMATIVE_CODE_VALIDATION",
        artifact_sha256=assignment_hash,
        loader_schema_version="country_assignments_json_v1",
    )
    _write_manifest(
        name_manifest,
        reference_id="fictional_names_v1",
        authority_role="NAME_MAPPING",
        artifact_sha256=name_hash,
        loader_schema_version="country_names_json_v1",
    )
    return CountryReference.from_artifacts(
        assignment_manifest, assignments, name_manifest, names
    )


def fictional_script_reference(tmp_path: Path) -> ScriptReference:
    artifact = tmp_path / "FictionalScripts.txt"
    data = (
        "0030..0039 ; Common\n"
        "0041..005A ; Latin\n"
        "0061..007A ; Latin\n"
        "0300..036F ; Inherited\n"
        "0400..04FF ; Cyrillic\n"
        "0600..06FF ; Arabic\n"
    ).encode()
    artifact.write_bytes(data)
    manifest = tmp_path / "script_manifest.json"
    _write_manifest(
        manifest,
        reference_id="fictional_unicode_scripts_16_v1",
        authority_role="UNICODE_SCRIPT_PROPERTY",
        artifact_sha256=hashlib.sha256(data).hexdigest(),
        loader_schema_version="unicode_scripts_txt_v1",
        unicode_version="16.0.0",
    )
    return ScriptReference.from_artifact(manifest, artifact)


def engine(
    tmp_path: Path,
    *,
    config: Phase03Config | None = None,
    with_country: bool = True,
    with_scripts: bool = True,
    execution_scope: str = "DEVELOPMENT",
) -> Phase03Engine:
    return Phase03Engine(
        config or Phase03Config(),
        load_rule_registry(),
        country_reference=fictional_country_reference(tmp_path)
        if with_country
        else None,
        script_reference=fictional_script_reference(tmp_path) if with_scripts else None,
        implementation_fingerprint=bytes.fromhex("33" * 32),
        execution_scope=execution_scope,
    )

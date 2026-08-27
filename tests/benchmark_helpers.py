from __future__ import annotations

import hashlib
import json
from pathlib import Path
from safe_geocoding_pipeline.preprocessing.script_reference import ScriptReference


def _write_manifest(
    path: Path,
    *,
    reference_id: str,
    authority_role: str,
    artifact_sha256: str,
    loader_schema_version: str,
    unicode_version: str | None = None,
) -> None:
    artifact_file_name = "FictionalScripts.txt"
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

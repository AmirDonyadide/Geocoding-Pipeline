from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .config import Phase03Config
from .constants import RULE_EXECUTION_DISPOSITIONS
from .references import (
    CountryReference,
    ScriptReference,
    load_production_references,
)
from .review import manual_review_schema
from .rules import load_rule_registry
from .schema import core_schema, evidence_schema
from .text import enforce_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the Phase 3 framework without reading real Phase 2 address rows"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("framework-info")
    registry = subparsers.add_parser("validate-rule-registry")
    registry.add_argument("--path", type=Path)
    country = subparsers.add_parser("validate-country-reference")
    country.add_argument("--manifest", type=Path, required=True)
    country.add_argument("--artifact", type=Path, required=True)
    scripts = subparsers.add_parser("validate-script-reference")
    scripts.add_argument("--manifest", type=Path, required=True)
    scripts.add_argument("--artifact", type=Path, required=True)
    production = subparsers.add_parser("validate-production-references")
    production.add_argument("--country-artifact", type=Path, required=True)
    subparsers.add_parser("manual-review-schema")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    enforce_runtime_contract()
    config = Phase03Config()
    config.validate()
    if args.command == "framework-info":
        registry = load_rule_registry()
        payload = {
            "status": "FRAMEWORK_ONLY",
            "pilot_ready": False,
            "phase03_version": config.phase03_version,
            "rule_registry_version": registry.registry_version,
            "rule_registry_sha256": registry.fingerprint,
            "rule_execution_dispositions": list(RULE_EXECUTION_DISPOSITIONS),
            "manual_review_reason_codes_version": (
                config.manual_review_reason_codes_version
            ),
            "manual_review_label_schema_version": (
                config.manual_review_label_schema_version
            ),
            "core_columns": len(core_schema()),
            "evidence_columns": len(evidence_schema()),
            "production_country_reference": config.country_reference_version,
            "production_script_reference": config.unicode_reference_version,
        }
    elif args.command == "validate-rule-registry":
        registry = load_rule_registry(args.path)
        payload = {
            "status": "PASS",
            "registry_version": registry.registry_version,
            "sha256": registry.fingerprint,
            "rule_count": len(registry.rules),
        }
    elif args.command == "validate-country-reference":
        country_reference = CountryReference.from_operational_artifact(
            args.manifest, args.artifact
        )
        payload = {
            "status": "PASS",
            "reference_version": country_reference.version,
            "record_count": len(country_reference.records),
        }
    elif args.command == "validate-script-reference":
        script_reference = ScriptReference.from_artifact(args.manifest, args.artifact)
        payload = {
            "status": "PASS",
            "reference_version": script_reference.version,
            "range_count": len(script_reference.ranges),
        }
    elif args.command == "validate-production-references":
        country_reference, script_reference = load_production_references(
            args.country_artifact,
            expected_country_reference_id=config.country_reference_version,
            expected_unicode_reference_id=config.unicode_reference_version,
        )
        payload = {
            "status": "PASS",
            "country_reference_version": country_reference.version,
            "country_record_count": len(country_reference.records),
            "script_reference_version": script_reference.version,
            "script_range_count": len(script_reference.ranges),
        }
    else:
        payload = {
            "status": "PASS",
            "schema": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                }
                for field in manual_review_schema()
            ],
        }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from .config import Phase03Config
from .constants import (
    PARSER_VERSION_V1,
    PARSER_VERSION_V2,
    RULE_EXECUTION_DISPOSITIONS,
)
from .development_comparison import compare_development_parser_outputs
from .development_pattern_profiler import profile_development_patterns
from .references import (
    ScriptReference,
    load_production_references,
    production_reference_paths,
    verify_cldr_reference_bundle,
)
from .pilot_runner import (
    SAMPLING_COLUMNS,
    ProductionSamplingContract,
    identity_digest,
    materialize_development_payload,
    proposed_production_pilot_config,
    read_identity_set,
    sampling_contract_summary,
)
from .pilot_orchestration import (
    materialize_development_review,
    select_production_pilot,
    transform_development_payload,
    validate_explicit_phase02_inputs,
    write_country_profile,
)
from .engine import Phase03Engine
from .review import manual_review_schema
from .rules import load_rule_registry
from .schema import core_schema, evidence_schema
from .text import enforce_runtime_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run explicit, fail-closed Phase 3 framework and pilot stages"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("framework-info")
    registry = subparsers.add_parser("validate-rule-registry")
    registry.add_argument("--path", type=Path)
    country = subparsers.add_parser("validate-country-reference")
    country.add_argument("--manifest", type=Path)
    country.add_argument("--reference-directory", type=Path)
    scripts = subparsers.add_parser("validate-script-reference")
    scripts.add_argument("--manifest", type=Path, required=True)
    scripts.add_argument("--artifact", type=Path, required=True)
    subparsers.add_parser("validate-production-references")
    subparsers.add_parser("manual-review-schema")
    plan = subparsers.add_parser(
        "pilot-plan", help="report the pilot plan without reading input data"
    )
    plan.add_argument("--input-path", type=Path, required=True)
    plan.add_argument("--output-path", type=Path, required=True)
    plan.add_argument("--git-commit", required=True)
    profile = subparsers.add_parser("pilot-profile")
    profile.add_argument("--phase02-manifest", type=Path, required=True)
    profile.add_argument("--input-path", type=Path, action="append", required=True)
    profile.add_argument("--output-path", type=Path, required=True)
    select = subparsers.add_parser("pilot-select")
    select.add_argument("--phase02-manifest", type=Path, required=True)
    select.add_argument("--input-path", type=Path, action="append", required=True)
    select.add_argument("--country-profile", type=Path, required=True)
    select.add_argument("--phase01-anomalies", type=Path, required=True)
    select.add_argument("--state-path", type=Path, required=True)
    select.add_argument("--output-directory", type=Path, required=True)
    select.add_argument("--selection-timestamp", required=True)
    select.add_argument("--git-commit", required=True)
    select.add_argument(
        "--selection-engine",
        choices=("baseline-sqlite", "optimized-sqlite", "bounded-parallel"),
        default="baseline-sqlite",
    )
    select.add_argument("--worker-count", type=int, default=1)
    select.add_argument("--sqlite-cache-size-mib", type=int, default=8_192)
    select.add_argument("--sqlite-mmap-size-mib", type=int, default=0)
    select.add_argument("--sqlite-insertion-batch-size", type=int, default=10_000)
    identity = subparsers.add_parser("pilot-validate-identity-set")
    identity.add_argument("--path", type=Path, required=True)
    materialize = subparsers.add_parser("pilot-materialize-development")
    materialize.add_argument("--phase02-manifest", type=Path, required=True)
    materialize.add_argument("--input-path", type=Path, action="append", required=True)
    materialize.add_argument("--output-path", type=Path, required=True)
    materialize.add_argument("--development-identities", type=Path, required=True)
    materialize.add_argument("--locked-identities", type=Path, required=True)
    transform = subparsers.add_parser("development-transform")
    transform.add_argument("--input-development-payload", type=Path, required=True)
    transform.add_argument("--development-identities", type=Path, required=True)
    transform.add_argument("--output-directory", type=Path, required=True)
    transform.add_argument("--git-commit", required=True)
    transform.add_argument(
        "--parser-version",
        choices=(PARSER_VERSION_V1, PARSER_VERSION_V2),
        default=PARSER_VERSION_V1,
    )
    comparison = subparsers.add_parser("development-compare-parsers")
    comparison.add_argument("--baseline-core", type=Path, required=True)
    comparison.add_argument("--revised-core", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)
    comparison.add_argument("--expected-rows", type=int, default=8_000)
    review_sample = subparsers.add_parser("development-review-sample")
    review_sample.add_argument("--state-path", type=Path, required=True)
    review_sample.add_argument("--development-payload", type=Path, required=True)
    review_sample.add_argument("--development-core", type=Path, required=True)
    review_sample.add_argument("--development-evidence", type=Path, required=True)
    review_sample.add_argument("--development-identities", type=Path, required=True)
    review_sample.add_argument("--output-directory", type=Path, required=True)
    pattern_profile = subparsers.add_parser("development-pattern-profile")
    pattern_profile.add_argument("--development-payload", type=Path, required=True)
    pattern_profile.add_argument("--development-core", type=Path, required=True)
    pattern_profile.add_argument("--development-evidence", type=Path, required=True)
    pattern_profile.add_argument("--development-identities", type=Path, required=True)
    pattern_profile.add_argument("--output-directory", type=Path, required=True)
    validate = subparsers.add_parser("pilot-validate")
    validate.add_argument("--phase02-manifest", type=Path, required=True)
    validate.add_argument("--input-path", type=Path, action="append", required=True)
    validate.add_argument("--development-identities", type=Path, required=True)
    validate.add_argument("--locked-identities", type=Path, required=True)
    validate.add_argument("--pilot-seal", type=Path, required=True)
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
            "pilot_ready": True,
            "real_pilot_authorized": False,
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
        paths = production_reference_paths()
        manifest_path = args.manifest or paths["country_manifest"]
        reference_directory = (
            args.reference_directory or paths["country_directory"]
        )
        manifest = verify_cldr_reference_bundle(manifest_path, reference_directory)
        payload = {
            "status": "PASS",
            "reference_version": manifest.reference_id,
            "record_count": manifest.row_count,
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
    elif args.command == "manual-review-schema":
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
    elif args.command == "pilot-plan":
        contract = ProductionSamplingContract()
        registry = load_rule_registry()
        country_reference, script_reference = load_production_references(
            expected_country_reference_id=config.country_reference_version,
            expected_unicode_reference_id=config.unicode_reference_version,
        )
        pilot_config = proposed_production_pilot_config()
        payload = {
            **sampling_contract_summary(contract),
            "input_path": str(args.input_path),
            "output_path": str(args.output_path),
            "git_commit": args.git_commit,
            "data_read": False,
            "automatic_progression": False,
            "pilot_sampling_config_fingerprint": pilot_config.fingerprint(),
            "seed": pilot_config.seed_domain.decode("utf-8"),
            "rule_registry_version": registry.registry_version,
            "rule_registry_sha256": registry.fingerprint,
            "country_reference_version": config.country_reference_version,
            "country_reference_sha256": (
                country_reference.assignment_manifest.artifact_sha256
            ),
            "unicode_reference_version": config.unicode_reference_version,
            "unicode_reference_sha256": script_reference.manifest.artifact_sha256,
            "pass_1_columns": ["country_iso_code"],
            "pass_2_columns": list(SAMPLING_COLUMNS),
            "planned_sampling_passes": 2,
            "development_materialization_pass": 1,
            "country_thresholds": {"rare_lt": 50, "medium_lt": 500},
            "review_target": 800,
            "double_review_target": 200,
            "candidate_state_backend": "SQLite",
            "candidate_state_schema_version": "phase03_pilot_candidate_state_v1",
            "minimum_free_disk_bytes": contract.minimum_free_bytes,
            "planned_controlled_input": str(args.input_path),
            "planned_controlled_output": str(args.output_path),
        }
    elif args.command == "pilot-profile":
        country_reference, _ = load_production_references(
            expected_country_reference_id=config.country_reference_version,
            expected_unicode_reference_id=config.unicode_reference_version,
        )
        profile_payload = write_country_profile(
            args.phase02_manifest,
            args.input_path,
            args.output_path,
            country_reference=country_reference,
            production=True,
        )
        payload = {
            "status": "PASS",
            "output_path": str(args.output_path),
            "profile_version": profile_payload["profile_version"],
            "row_count": profile_payload["row_count"],
            "group_count": profile_payload["group_count"],
            "raw_values_reported": False,
            "per_value_hashes_reported": False,
        }
    elif args.command == "pilot-select":
        country_reference, script_reference = load_production_references(
            expected_country_reference_id=config.country_reference_version,
            expected_unicode_reference_id=config.unicode_reference_version,
        )
        registry = load_rule_registry()
        payload = select_production_pilot(
            manifest_path=args.phase02_manifest,
            input_paths=args.input_path,
            country_profile_path=args.country_profile,
            phase01_anomalies_path=args.phase01_anomalies,
            state_path=args.state_path,
            output_directory=args.output_directory,
            country_reference=country_reference,
            script_reference=script_reference,
            rule_registry=registry,
            selection_timestamp=args.selection_timestamp,
            git_commit=args.git_commit,
            phase03_configuration_fingerprint=config.configuration_fingerprint().hex(),
            reference_configuration_fingerprint=hashlib.sha256(
                (
                    country_reference.version + "\0" + script_reference.version
                ).encode()
            ).hexdigest(),
            production=True,
            selection_engine=args.selection_engine,
            worker_count=args.worker_count,
            sqlite_cache_size_mib=args.sqlite_cache_size_mib,
            sqlite_mmap_size_mib=args.sqlite_mmap_size_mib,
            sqlite_insertion_batch_size=args.sqlite_insertion_batch_size,
        )
    elif args.command == "pilot-validate-identity-set":
        metadata, identities = read_identity_set(args.path)
        payload = {
            "status": "PASS",
            "path": str(args.path),
            "count": len(identities),
            "partition": metadata["partition"],
            "identity_digest": metadata["identity_digest"],
        }
    elif args.command == "pilot-materialize-development":
        _, manifest_identity = validate_explicit_phase02_inputs(
            args.phase02_manifest, args.input_path, production=True
        )
        development_metadata, development = read_identity_set(
            args.development_identities
        )
        locked_metadata, locked = read_identity_set(args.locked_identities)
        if development_metadata["partition"] != "DEVELOPMENT":
            raise ValueError("development identity partition mismatch")
        if locked_metadata["partition"] != "LOCKED_EVALUATION":
            raise ValueError("locked identity partition mismatch")
        if len(development) != 8_000 or len(locked) != 4_000:
            raise ValueError("pilot identity counts differ from approved contract")
        for key in ("manifest_identity", "sampling_config_fingerprint"):
            if development_metadata[key] != locked_metadata[key]:
                raise ValueError("identity-set metadata mismatch")
        if development_metadata["manifest_identity"] != manifest_identity:
            raise ValueError("identity sets do not bind the approved Phase 2 manifest")
        rows = materialize_development_payload(
            args.input_path,
            args.output_path,
            development_ids=set(development),
            locked_ids=set(locked),
            production=True,
        )
        payload = {
            "status": "PASS",
            "output_path": str(args.output_path),
            "development_rows": rows,
            "locked_rows_materialized": 0,
        }
    elif args.command == "development-transform":
        config = Phase03Config.for_parser_version(args.parser_version)
        config.validate()
        development_metadata, development = read_identity_set(
            args.development_identities
        )
        if development_metadata["partition"] != "DEVELOPMENT" or len(development) != 8_000:
            raise ValueError("development identity-set mismatch")
        country_reference, script_reference = load_production_references(
            expected_country_reference_id=config.country_reference_version,
            expected_unicode_reference_id=config.unicode_reference_version,
        )
        registry = load_rule_registry(
            registry_version=config.rule_registry_version
        )
        implementation = hashlib.sha256(args.git_commit.encode()).digest()
        engine = Phase03Engine(
            config,
            registry,
            country_reference=country_reference,
            script_reference=script_reference,
            implementation_fingerprint=implementation,
            execution_scope="DEVELOPMENT",
        )
        result = transform_development_payload(
            args.input_development_payload,
            args.output_directory,
            engine=engine,
            config=config,
            metadata={
                "pilot_partition": "DEVELOPMENT",
                "git_commit": args.git_commit,
                "parser_version": config.parser_version,
                "rule_registry_version": config.rule_registry_version,
            },
            expected_development_ids=set(development),
        )
        payload = {
            "status": "PASS",
            "core_rows": result.core_rows,
            "evidence_rows": result.evidence_rows,
            "core_semantic_digest": result.core_semantic_digest,
            "evidence_semantic_digest": result.evidence_semantic_digest,
            "page_checksums_verified": result.page_checksums_verified,
            "parser_version": config.parser_version,
            "rule_registry_version": config.rule_registry_version,
            "configuration_fingerprint": engine.configuration_fingerprint.hex(),
        }
    elif args.command == "development-compare-parsers":
        payload = compare_development_parser_outputs(
            args.baseline_core,
            args.revised_core,
            args.output,
            expected_rows=args.expected_rows,
        )
    elif args.command == "development-review-sample":
        metadata, development = read_identity_set(args.development_identities)
        if metadata["partition"] != "DEVELOPMENT" or len(development) != 8_000:
            raise ValueError("development identity-set mismatch")
        payload = materialize_development_review(
            state_path=args.state_path,
            development_payload_path=args.development_payload,
            core_path=args.development_core,
            evidence_path=args.development_evidence,
            development_ids=set(development),
            output_directory=args.output_directory,
            pilot_version=proposed_production_pilot_config().pilot_version,
        )
    elif args.command == "development-pattern-profile":
        profile_config = Phase03Config.for_parser_version(PARSER_VERSION_V2)
        profile_config.validate()
        _, script_reference = load_production_references(
            expected_country_reference_id=profile_config.country_reference_version,
            expected_unicode_reference_id=profile_config.unicode_reference_version,
        )
        registry = load_rule_registry(
            registry_version=profile_config.rule_registry_version
        )
        profile_result = profile_development_patterns(
            development_payload_path=args.development_payload,
            core_path=args.development_core,
            evidence_path=args.development_evidence,
            development_identities_path=args.development_identities,
            output_directory=args.output_directory,
            script_reference=script_reference,
            rule_ids=tuple(rule.rule_id for rule in registry.ordered_rules()),
            rule_registry_fingerprint=registry.fingerprint,
            production=True,
        )
        payload = {
            "status": "PASS",
            "profiler_version": "phase03_development_pattern_profiler_v1",
            "rows": profile_result.rows,
            "profile_fingerprint": profile_result.profile_fingerprint,
            "report_files": [
                profile_result.report_json.name,
                profile_result.opportunities_csv.name,
                profile_result.interpretation_markdown.name,
            ],
            "locked_rows_read": 0,
            "raw_values_reported": False,
        }
    else:
        _, manifest_identity = validate_explicit_phase02_inputs(
            args.phase02_manifest,
            args.input_path,
            production=True,
        )
        development_metadata, development = read_identity_set(args.development_identities)
        locked_metadata, locked = read_identity_set(args.locked_identities)
        if (
            development_metadata["partition"] != "DEVELOPMENT"
            or locked_metadata["partition"] != "LOCKED_EVALUATION"
            or development_metadata["manifest_identity"] != manifest_identity
            or locked_metadata["manifest_identity"] != manifest_identity
            or set(development) & set(locked)
            or len(development) != 8_000
            or len(locked) != 4_000
        ):
            raise ValueError("pilot identity validation failed")
        seal = json.loads(args.pilot_seal.read_text(encoding="utf-8"))
        if (
            seal.get("pilot_seal_version") != "phase03_pilot_seal_v1"
            or seal.get("development_count") != len(development)
            or seal.get("locked_evaluation_count") != len(locked)
            or seal.get("development_identity_digest")
            != identity_digest(
                b"phase03:development_identities_v1\0", development
            )
            or seal.get("locked_evaluation_identity_digest")
            != identity_digest(b"phase03:locked_identities_v1\0", locked)
            or seal.get("input_phase02_manifest_identity") != manifest_identity
            or seal.get("sampling_config_fingerprint")
            != development_metadata["sampling_config_fingerprint"]
        ):
            raise ValueError("pilot seal validation failed")
        payload = {
            "status": "PASS",
            "development_count": len(development),
            "locked_evaluation_count": len(locked),
            "disjoint": True,
            "locked_payload_rows_read": 0,
        }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

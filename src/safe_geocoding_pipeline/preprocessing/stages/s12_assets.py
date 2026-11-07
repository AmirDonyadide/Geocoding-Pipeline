"""Canonical Stage 12 machine-readable descriptors, separate identity lifetimes."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import s12_campaign as campaign
from . import s12_deployment as deployment
from . import s12_operations as operations
from . import s12_publication as publication
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as storage


def objects(
    *, public_operations: bool = False, public_sampling: bool = False
) -> dict[str, dict[str, Any]]:
    """Descriptors have no self hash, executable SHA, path-dependent ID or secret."""
    result: dict[str, dict[str, Any]] = {
        c.CONTRACT: {
            "contract_version": c.CONTRACT,
            "design_documents": [
                {"path": "docs/stages/" + name, "sha256": value}
                for name, value in sorted(c.DESIGN_HASHES.items())
            ],
        },
        c.PROFILE: {
            "profile_version": c.PROFILE,
            "split": "DEVELOPMENT",
            "accepted_stage11_publication": "stage11_development_20261004T095201Z_8dce0e1078e1",
            "semantic_requests": 105805,
            "hypothesis_mappings": 142677,
            "semantic_request_sha256": "01b1c6f243e12c407d9df86b77d3068be46a11f3511e4d77170db39f73e83f5e",
            "hypothesis_request_map_sha256": "ea23792566398856cba1372c914cec5c70e00412c80dac7f5fec259d663dfcc3",
            "stage11_dataset_sha256": "e110ff3eb2ad01ac6bf298c48f6c489b3b79bc067f28b41deab8d1bc1e46f337",
            "C": "UNSELECTED",
            "T": "UNSELECTED",
            "N": "UNSELECTED",
            "protected_execution_authorized": False,
            "publication_roles": [publication.CALIBRATION, publication.FINAL],
        },
        c.SCHEMA: {
            "schema_version": c.SCHEMA,
            "types": {
                "D": "fixed_size_binary[32]",
                "T": "large_string",
                "U": "uint64",
                "F": "float64",
                "Z": "timestamp[us,UTC]",
                "B": "bool",
                "L": "list<struct<>>;empty-only",
            },
            "relations": [c.descriptor(name) for name in c.RELATIONS],
            "scientific_projections": [
                c.descriptor(name, scientific=True)
                for name in c.RELATIONS
                if name != "request_attempt"
            ],
            "terminal_states": list(c.TERMINAL),
            "attempt_outcomes": list(c.OUTCOMES),
            "rank": "ONE_BASED_ORIGINAL_ARRAY_POSITION",
            "candidate_count_on_failure": None,
            "duplicates": "PRESERVE_EVERY_POSITION",
            "foreign_keys": {
                "request_execution": [
                    "query_semantic_id->accepted_stage11.semantic_request",
                    "retrieval_policy_id->retrieval_policy",
                    "terminal_attempt_id->request_attempt:same_execution",
                    "deployment/index/effective->manifest",
                ],
                "request_attempt": [
                    "request_execution_id->request_execution",
                    "campaign_start_sha256->campaign_start",
                    "identity_verification_receipt_sha256->campaign_evidence",
                ],
                "request_candidate": [
                    "request_execution_id->successful_request_execution:same_projection",
                    "response_sha256->request_execution.response_sha256",
                ],
            },
        },
        c.POLICY: {
            "policy_version": c.POLICY,
            "ordered_identity_fields": [
                "policy_version",
                "result_limit",
                "retention",
                "result_options",
            ],
            "domain": "SAFE:stage12-retrieval-policy:v1",
            "result_limit": "EXPLICIT_APPROVED_POSITIVE_UINT64",
            "retention": "ALL_RETURNED_IN_ORDER",
            "result_options": [],
            "purpose_outside_identity": True,
        },
        c.IDENTITY: {
            "identity_version": c.IDENTITY,
            "framing": "STAGE11_E_NAMED_ASCII_FIELDS_STRICT_UTF8_UINT64_BE",
            "algorithm": "SHA256",
            "domain": "SAFE:stage12-request-execution:v1",
            "ordered_fields": list(c.EXECUTION_FIELDS),
            "collision_rule": "FULL_PREIMAGE_EQUALITY_OR_FAIL",
            "row_float_extension": "TAG_06_FINITE_IEEE754_BINARY64_BIG_ENDIAN",
        },
        c.MATERIALIZATION: {
            "materialization_version": c.MATERIALIZATION,
            "method": "GET",
            "http_version": "1.1",
            "body": None,
            "paths": {"FULL_TEXT": "/v1/search", "STRUCTURED": "/v1/search/structured"},
            "parameters_order": [
                "address",
                "boundary.country",
                "country",
                "locality",
                "postalcode",
                "region",
                "size",
                "text",
            ],
            "upstream_null_slots": ["country", "region"],
            "boundary_country": "EXACT_UPPERCASE_ALPHA2_SEPARATE_FILTER",
            "size_source": "retrieval_policy.result_limit",
            "value_rule": "EXACT_STAGE11_STRINGS_NO_TRANSFORMATION",
            "encoding": "STRICT_UTF8_RFC3986_UNRESERVED_UPPERCASE_PERCENT_HEX",
            "space": "%20",
            "null_slots": "OMIT",
            "headers_order": [
                "Host",
                "Accept",
                "Accept-Encoding",
                "User-Agent",
                "X-API-Key",
            ],
            "accept": "application/json",
            "accept_encoding": "identity",
            "user_agent": "SAFE-stage12-retrieval/1",
            "authentication": "RUNTIME_ONLY_X_API_KEY_PENDING_DEPLOYMENT_VERIFICATION",
            "forbidden": [
                "extra_parameters",
                "Accept-Language",
                "lang",
                "layers",
                "sources",
                "Cookie",
                "Referer",
                "redirect",
                "proxy_injection",
                "library_retry",
                "credential_url",
                "arbitrary_host",
            ],
            "routing": "OWNER_APPROVED_SAFE_HTTPS_ORIGIN_AND_NONSECRET_DATA_VIEW",
        },
        deployment.MANIFEST: {
            "manifest_version": deployment.MANIFEST,
            "closed_core_keys": {k: list(v) for k, v in deployment.CORE_KEYS.items()},
            "core_versions": deployment.VERSIONS,
            "canonical_json": "SORTED_KEYS_ASCII_COMPACT_INTEGER_NUMBERS_FINAL_LF",
            "inventory_sets": "SORT_FULL_IDENTIFIER_UTF8_REJECT_DUPLICATES",
            "configuration_arrays": "PRESERVE_ORDER",
            "identity": "CANONICAL_RESULT_AFFECTING_CONTENT_ONLY",
            "authenticity": "SEPARATE_OPERATOR_SIGNATURE_PINNED_APPROVED_KEY",
            "immutable_index_requirement": "UUID_AND_IMMUTABLE_SNAPSHOT_CONTENT_AND_IMPORT_AUXILIARY_IDENTITIES",
            "aliases": "EXACT_MAPPINGS_NOT_IMMUTABLE_IDENTITIES",
            "observability": list(deployment.OBSERVABILITY),
            "drift_modes": ["PER_RESPONSE_GENERATION", "CONTROLLED_CAMPAIGN"],
            "periodic_max_seconds": 60,
            "periodic_max_responses": 100,
            "unknown_identity": "FAIL_CLOSED",
            "drift": "STOP_AND_QUARANTINE_WHOLE_CAMPAIGN",
        },
        response.VALIDATION: {
            "validation_version": response.VALIDATION,
            "successful_status": 200,
            "content_types": list(response.MEDIA),
            "content_encodings": ["identity", "absent"],
            "json": "STRICT_UTF8_NO_BOM_DUPLICATE_KEYS_SURROGATES_NONFINITE_OR_TRAILING_DATA",
            "type": "FeatureCollection",
            "features": "ARRAY_LENGTH_ZERO_THROUGH_POLICY_LIMIT",
            "errors_warnings": "ABSENT_OR_EMPTY_ARRAY_AT_TOP_AND_GEOCODING",
            "feature": "OBJECT_TYPE_FEATURE_PROPERTIES_OBJECT_POINT_GEOMETRY",
            "geometry": "EXACTLY_TWO_FINITE_BINARY64_LONGITUDE_LATITUDE",
            "longitude_range": [-180, 180],
            "latitude_range": [-90, 90],
            "crs": "REJECT",
            "bbox": "FOUR_FINITE_COORDINATES_SOUTH_LE_NORTH_ANTIMERIDIAN_ALLOWED",
            "source_layer": "NONEMPTY_STRINGS_IN_VERIFIED_DEPLOYMENT_VOCABULARY",
            "optional_fields": "NULL_OR_EXACT_DECLARED_TYPE",
            "confidence": "NULL_OR_FINITE_NUMBER_ZERO_THROUGH_ONE_DESCRIPTIVE",
            "feature_id": "NULL_OR_STRING_NO_COERCION",
            "echo": "PINNED_DEPLOYMENT_EXACT_ADAPTER_OR_ATTESTED_ABSENCE",
            "malformed_feature": "WHOLE_RESPONSE_CONTRACT_FAILURE_ZERO_CANDIDATE_ROWS_NULL_COUNT_RETAIN_SAFE_RAW_AUDIT",
        },
        response.EXTRACTION: {
            "extraction_version": response.EXTRACTION,
            "candidate_schema": c.descriptor("request_candidate"),
            "rank": "ONE_BASED_ARRAY_ORDER_NO_FILTER_NO_DEDUP",
            "source_fields": "IDENTICALLY_NAMED_PROPERTIES_EXCEPT_FEATURE_ID_FROM_FEATURE_ID",
            "unknown_fields": "RAW_ONLY_COUNTED",
            "missing_optional_and_null": "EXTRACT_NULL_RAW_PRESERVES_DIFFERENCE",
            "empty_optional": "PRESERVE_EMPTY_STRING",
            "coordinates": "ROUND_ONCE_TIES_TO_EVEN_BINARY64_PRESERVE_NEGATIVE_ZERO",
            "raw_response_sha256": "EXACT_DECODED_UNCOMPRESSED_APPLICATION_ENTITY_BYTES_BEFORE_JSON",
            "raw_feature_sha256": "EXACT_CONTIGUOUS_JSON_FEATURE_OBJECT_BYTE_SLICE",
            "feature_offset": "ZERO_BASED_BYTE_OFFSET",
            "storage_compression": "SCIENTIFICALLY_IRRELEVANT",
            "point_confidence_match_accuracy": "DESCRIPTIVE_ONLY_NO_TRUTH_OR_ROOFTOP_INFERENCE",
        },
        c.PROJECTION: {
            "projection_version": c.PROJECTION,
            "scope": "DATASET_LEVEL_ONE_PER_ARTIFACT",
            "domain": "SAFE:stage12-response-projection:v1",
            "ordered_fields": [
                "projection_version",
                "raw_response_set_sha256",
                "capture_context_sha256",
                "response_validation_contract_sha256",
                "response_extraction_contract_sha256",
                "candidate_schema_sha256",
            ],
            "raw_set": "SORTED_EXECUTION_ID_RESPONSE_SHA256_APPLICATION_LENGTH_ALL_COMPLETE_RETAINED_PAYLOADS",
            "capture_context": "SORTED_EXECUTION_ID_REQUEST_TARGET_HASH_STATUS_MEDIA_ENCODING_COMPLETE",
            "changed_extraction": "NEW_IMMUTABLE_PROJECTION_NO_NEW_NETWORK_EXECUTION",
            "original_attempt_receipts": "IMMUTABLE",
        },
        campaign.VERSION: {
            "campaign_version": campaign.VERSION,
            "start_keys": list(campaign.START_KEYS),
            "checkpoint_keys": list(storage.BINDING_KEYS),
            "campaign_id": "PERSISTED_RANDOM_32_BYTES",
            "jobs": "APPEND_ONLY_SEPARATELY_AUTHORIZED_SEQUENTIAL_SEGMENTS",
            "attempt_budget": "CUMULATIVE_INCLUDING_UNKNOWN_DELIVERY",
            "adoption": "EXACT_CLIENT_RUNTIME_OPERATIONS_SCIENTIFIC_BINDINGS_AND_VERIFIED_CLOSED_CONTINUITY",
            "incomplete": "NEVER_ADOPT",
            "offline_replay": "SEPARATE_EXTRACTOR_PROVENANCE_NOT_NETWORK_ADOPTION",
        },
        operations.VERSION: {
            "operations_version": operations.VERSION,
            "initial_public_policy": asdict(operations.Operations()),
            "protected_policy": "UNSELECTED_PENDING_OWNER_REVIEW",
            "base_retry_wait_ms": [2000, 4000, 8000, 16000],
            "spacing": "FIRST_TWO_SHA256_BYTES_MOD_1000_OF_DOMAIN_NUL_E_EXECUTION_AND_NEXT_ATTEMPT",
            "retry_after": "MAX_BASE_PLUS_SPACING_AND_PARSED_DELTA_OR_HTTP_DATE",
            "retry_date_owner_clarification": "UNUSABLE_OR_MISSING_RESPONSE_DATE_USES_CLIENT_RECEIPT_UTC",
            "retry_clock_audit": "SEPARATE_OPERATIONAL_RECEIPT_NOT_SCIENTIFIC_IDENTITY",
            "memory_reservation_multiplier": 128,
            "memory_admission_capacity_bytes": 4 * 1024**3,
            "max_retry_after_ms": 300000,
            "overload_cooldown_min_ms": 30000,
            "breaker_consecutive_errors": 3,
            "breaker_errors_last_20": 5,
            "breaker_overloads_in_60_seconds": 2,
            "breaker_slow_over_30_seconds_in_20": 10,
            "automatic_breaker_recovery": False,
            "automatic_job_submission": False,
            "hard_connection_ceiling": 4,
            "library_retries": False,
        },
        c.ATTEMPT: {
            "receipt_version": c.ATTEMPT,
            "domain": "SAFE:stage12-request-attempt:v1",
            "ordered_identity_fields": [
                "receipt_version",
                "request_execution_id",
                "campaign_id",
                "attempt_number",
            ],
            "relation": c.descriptor("request_attempt"),
            "protocol": [
                "EXCLUSIVE_BEGIN_FSYNC_BEFORE_DISPATCH",
                "SAFE_COMPLETE_RAW_AND_PROJECTION_FSYNC",
                "EXCLUSIVE_FINISH_INVENTORY_FULL_REOPEN",
                "EXCLUSIVE_SEAL_DIRECTORY_FSYNC_FULL_REOPEN",
            ],
            "unknown_delivery_consumes_attempt": True,
            "http_metadata_allowlist": [
                "status",
                "content_type_enum",
                "content_encoding_enum",
                "parsed_retry_after",
                "approved_nonsecret_identity",
            ],
            "secret_persistence": "FORBIDDEN",
        },
        "stage12_calibration_protocol_v1": {
            "calibration_version": "stage12_calibration_protocol_v1",
            "C": "UNSELECTED",
            "T": "UNSELECTED",
            "N": "UNSELECTED",
            "protected_calibration_started": False,
            "tail_max_requests": 2000,
            "tail_depth": "T_GREATER_THAN_MAX_C_10",
            "paired_max_requests": 400,
            "full_population": 105805,
            "public_cases": 64,
            "public_cases_per_mode": 32,
            "public_base_sizes": [1, 3, 5, 10],
            "public_repetitions": 2,
            "public_deep_cases": 16,
            "public_max_deeper_sizes": 2,
            "public_deeper_sizes": "CONTROLLED_SAFE_BOUND_REQUIRED_ONLY_BEFORE_ABOVE10_DISPATCH",
            "public_empty_deeper_ladder": "OWNER_CLARIFIED_BASE_PROBE_ALLOWED_PROTECTED_T_STILL_BLOCKED",
            "public_additional_checks_ceiling": 16,
            "public_ordinary_call_ceiling": 592,
            "public_attempt_ceiling": 2960,
            "protected_workload_fingerprint": "DEFERRED_TO_AUTHORIZED_OFFLINE_PREFLIGHT",
        },
        "stage12_pelias_retrieval_manifest_v1": {
            "manifest_version": "stage12_pelias_retrieval_manifest_v1",
            "relations": list(c.RELATIONS),
            "publication_binding_keys": list(publication.BINDINGS),
            "response_projection_scope": "ONE_DATASET",
            "complete_final_executions": 105805,
            "dataset_scientific_domain": "SAFE:stage12-dataset:v1",
            "dataset_ordered_binding_fields": list(c.DATASET_BINDINGS),
            "dataset_scientific_relations": [
                "retrieval_policy",
                "request_execution",
                "request_candidate",
            ],
            "policy_physical_format": "CANONICAL_JSON_EMPTY_OPTIONS_LOGICAL_SCHEMA_UNCHANGED",
            "terminal_failures_allowed": 0,
            "full_reopen_required": True,
            "raw_storage": "INDEPENDENT_ZSTD_FRAMES_LEVEL_3_INITIALLY",
            "pack_compressed_max_bytes": 64 * 1024 * 1024,
            "pack_max_responses": 256,
        },
        "stage12_pelias_retrieval_summary_v1": {
            "summary_version": "stage12_pelias_retrieval_summary_v1",
            "sections": ["scientific", "operations"],
            "portable_values": "ALLOWLISTED_AGGREGATES_ONLY",
            "protected_text_or_row_ids": "FORBIDDEN",
            "small_cell_min_distinct_source_rows": 20,
            "complementary_suppression": "REQUIRED",
            "release_plan": "OWNER_FREEZE_BEFORE_PROTECTED_PREFLIGHT",
        },
        publication.VERSION: {
            "record_version": publication.VERSION,
            "body_keys": ["record_version", "namespace", "publication_key", "bindings"],
            "namespaces": [publication.CALIBRATION, publication.FINAL],
            "binding_keys": list(publication.BINDINGS),
            "domain": "SAFE:stage12-publication-record:v1",
            "ordered_identity_fields": ["record_version", "record_body"],
            "protocol": [
                "PERMANENT_EXCLUSIVE_RESERVATION",
                "IMMUTABLE_VALIDATED_ARTIFACT",
                "STAGE12_REGISTRATION",
                "EXCLUSIVE_EMPTY_COMMITTED_SEAL",
                "FULL_REOPEN",
            ],
            "uncertain_seal": "SEPARATELY_AUTHORIZED_RECONCILIATION_REQUIRED",
        },
    }
    if public_operations:
        from . import s12_public_operations

        result.update(s12_public_operations.descriptors())
    if public_sampling:
        from . import s12_public_sampling_contract

        result.update(s12_public_sampling_contract.descriptors())
    return result


def hashes() -> dict[str, bytes]:
    return {name: c.sha(c.canonical(value)) for name, value in objects().items()}


def verify(
    root: Path, *, public_operations: bool = False, public_sampling: bool = False
) -> dict[str, str]:
    for filename, expected in c.DESIGN_HASHES.items():
        c.require(
            c.sha((root / "docs/stages" / filename).read_bytes()).hex() == expected,
            "S12_FROZEN_DESIGN_MISMATCH",
        )
    result = {}
    for name, value in objects(
        public_operations=public_operations, public_sampling=public_sampling
    ).items():
        raw = (root / "docs/scientific_assets" / (name + ".json")).read_bytes()
        c.require(raw == c.canonical(value), "S12_ASSET_MISMATCH")
        result[name] = c.sha(raw).hex()
    return result

from __future__ import annotations

PHASE03_VERSION = "phase03_v1"
PARSER_VERSION = "conservative_address_parser_v1"
RULE_REGISTRY_VERSION = "phase03_rule_registry_v2"
CLEANING_RULES_VERSION = "derived_text_nfc_ws_v1_ucd16.0.0"
PLACEHOLDER_POLICY_VERSION = "placeholder_policy_v1"
DIAGNOSTIC_VOCABULARY_VERSION = "diagnostic_vocabulary_v1"
COMPONENT_SCHEMA_VERSION = "phase03_component_core_v1"
EVIDENCE_SCHEMA_VERSION = "phase03_component_evidence_v1"
EVIDENCE_SIDECAR_POLICY_VERSION = "evidence_sidecar_policy_v1"
MANUAL_REVIEW_REASON_CODES_VERSION = "manual_review_reason_codes_v1"
MANUAL_REVIEW_LABEL_SCHEMA_VERSION = "phase03_manual_review_labels_v1"
EXPECTED_PYTHON_VERSION = (3, 14, 3)
EXPECTED_UNICODE_VERSION = "16.0.0"

RULE_EXECUTION_DISPOSITIONS = (
    "AUTHORITATIVE_SELECTABLE",
    "AUTHORITATIVE_CANDIDATE_ONLY",
    "AUTHORITATIVE_DIAGNOSTIC_ONLY",
    "DEVELOPMENT_SHADOW_ONLY",
)
EXECUTION_SCOPES = ("DEVELOPMENT", "LOCKED_EVALUATION", "AUTHORITATIVE")

ADDRESS_FIELDS = (
    "street_address_line_1",
    "street_address_line_2",
    "street_address_line_3",
    "street_address_line_4",
    "street_address_line_1_native",
    "street_address_line_2_native",
    "street_address_line_3_native",
    "street_address_line_4_native",
)
STRUCTURED_GEOGRAPHY_FIELDS = (
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
)
ELIGIBLE_FIELDS = ADDRESS_FIELDS + STRUCTURED_GEOGRAPHY_FIELDS

COMPONENTS = (
    "STREET",
    "HOUSE_NUMBER",
    "UNIT",
    "FLOOR",
    "BUILDING",
    "ORGANIZATION",
    "POSTCODE",
    "LOCALITY",
    "REGION",
    "COUNTRY",
    "PO_BOX",
)
REPRESENTATIONS = ("NON_NATIVE", "NATIVE", "SHARED")
CONFIDENCES = ("HIGH", "MEDIUM", "LOW", "UNRESOLVED")
SEMANTIC_STATES = ("SEMANTIC_MISSING", "AMBIGUOUS_PLACEHOLDER_LIKE", "CONTENT")
EVALUATION_STATUSES = (
    "FULLY_EVALUATED",
    "PARTIALLY_SKIPPED_OVERSIZED",
    "NOT_EVALUATED_OVERSIZED",
)
PARSE_STATUSES = (
    "PARSED",
    "PARTIAL",
    "AMBIGUOUS",
    "CONFLICT",
    "UNPARSEABLE",
    "INSUFFICIENT",
)
COMPLETENESS_CLASSES = (
    "A_POINT_CORE_WITH_POSTCODE",
    "B_POINT_CORE",
    "C_STREET_LEVEL",
    "D_LOCALITY_LEVEL",
    "E_COUNTRY_ONLY",
    "F_ADDRESS_WITH_GEOGRAPHY_GAPS",
    "G_OTHER_PARTIAL",
    "Z_NO_COMPONENTS",
)
NATIVE_RELATIONSHIPS = (
    "BOTH_SEMANTICALLY_MISSING",
    "NATIVE_ONLY",
    "NON_NATIVE_ONLY",
    "EXACT_EQUAL",
    "NFC_EQUAL",
    "SAME_SCRIPT_DIFFERENT",
    "DIFFERENT_SCRIPT",
    "MIXED_OR_UNDETERMINED",
)

CONFLICT_FLAGS = (
    "COUNTRY_SOURCE_CONFLICT",
    "COUNTRY_MULTIPLE_CANDIDATES",
    "POSTCODE_SOURCE_CONFLICT",
    "POSTCODE_MULTIPLE_CANDIDATES",
    "LOCALITY_SOURCE_CONFLICT",
    "LOCALITY_MULTIPLE_CANDIDATES",
    "REGION_SOURCE_CONFLICT",
    "REGION_MULTIPLE_CANDIDATES",
    "STREET_MULTIPLE_CANDIDATES",
    "HOUSE_NUMBER_MULTIPLE_CANDIDATES",
    "HOUSE_NUMBER_POSTCODE_ROLE_CONFLICT",
    "UNIT_HOUSE_NUMBER_ROLE_CONFLICT",
    "BUILDING_ORGANIZATION_ROLE_CONFLICT",
    "COMPONENT_SPAN_OVERLAP_CONFLICT",
    "NATIVE_NON_NATIVE_HOUSE_NUMBER_CONFLICT",
    "NATIVE_NON_NATIVE_POSTCODE_CONFLICT",
    "NATIVE_NON_NATIVE_COUNTRY_CONFLICT",
)
DIAGNOSTIC_FLAGS = (
    "STRUCTURED_GEOGRAPHY_MISSING_FREEFORM_PRESENT",
    "COUNTRY_STRUCTURED_UNRECOGNIZED",
    "COUNTRY_STRUCTURED_REGION_LIKE",
    "POSTCODE_FREEFORM_PRESENT",
    "AMBIGUOUS_PLACEHOLDER_LIKE_PRESENT",
    "PLACEHOLDER_REFERENCE_COLLISION_UNRESOLVED",
    "PLACEHOLDER_REFERENCE_COLLISION_CORROBORATED",
    "PLACEHOLDER_VARIANT_PRESENT",
    "UNASSIGNED_CONTENT_PRESENT",
    "NATIVE_ONLY_CONTENT",
    "NON_NATIVE_ONLY_CONTENT",
    "NATIVE_NON_NATIVE_TEXT_DIFFERENT",
    "PROBABLE_ORGANIZATION_TEXT",
    "PO_BOX_EVIDENCE",
    "HISTORICAL_EVIDENCE",
    "PROBABLE_NON_PHYSICAL",
    "POSSIBLE_COMPANY_ONLY",
    "OVERSIZED_INPUT",
    "CANDIDATE_LIMIT_EXCEEDED",
)
POSTCODE_FLAGS = (
    "POSTCODE_SOURCE_EMPTY",
    "POSTCODE_SEMANTIC_MISSING",
    "POSTCODE_AMBIGUOUS_PLACEHOLDER_LIKE",
    "POSTCODE_DIGITS_ONLY",
    "POSTCODE_LEADING_ZERO",
    "POSTCODE_DECIMAL_LOOKING",
    "POSTCODE_ALPHABETIC",
    "POSTCODE_ALPHANUMERIC",
    "POSTCODE_CONTAINS_WHITESPACE",
    "POSTCODE_CONTAINS_HYPHEN",
    "POSTCODE_OTHER",
    "POSTCODE_FREEFORM_PRESENT",
    "POSTCODE_NORMALIZED_WHITESPACE",
)
EVIDENCE_KINDS = (
    "SELECTED_NONTRIVIAL_COMPONENT",
    "UNSELECTED_CANDIDATE",
    "COMPETING_CANDIDATE",
    "CONFLICTING_EVIDENCE",
    "UNASSIGNED_MATERIAL_CONTENT",
    "AMBIGUOUS_PLACEHOLDER",
    "MANUAL_REVIEW_CONTEXT",
)
COUNTRY_INPUT_CLASSES = (
    "SEMANTIC_MISSING",
    "AMBIGUOUS_PLACEHOLDER_LIKE",
    "ALPHA2_ASSIGNED_EXACT",
    "ALPHA2_CASE_VARIANT",
    "ALPHA3_ASSIGNED_EXACT",
    "COUNTRY_NAME_EXACT",
    "REGION_LIKE",
    "UNKNOWN_TEXT",
)
COUNTRY_PARSE_METHODS = (
    "STRUCTURED_ALPHA2_EXACT",
    "STRUCTURED_ALPHA2_CASE_NORMALIZED",
    "STRUCTURED_ALPHA3_EXACT",
    "STRUCTURED_COUNTRY_NAME_EXACT",
    "FREEFORM_ALPHA2_EXACT",
    "FREEFORM_ALPHA3_EXACT",
    "FREEFORM_COUNTRY_NAME_EXACT",
    "MULTISOURCE_AGREEMENT",
    "MULTISOURCE_CORROBORATED_PLACEHOLDER_COLLISION",
    "CONFLICT",
    "UNRESOLVED",
)

CORE_COLUMNS = (
    "stable_source_row_id_v1",
    "id",
    "source_file",
    "source_logical_record_number",
    "source_file_sha256",
    "street_clean",
    "house_number_clean",
    "unit_clean",
    "floor_clean",
    "building_clean",
    "organization_clean",
    "postcode_clean",
    "locality_clean",
    "region_clean",
    "country_clean",
    "street_native_clean",
    "house_number_native_clean",
    "unit_native_clean",
    "floor_native_clean",
    "building_native_clean",
    "organization_native_clean",
    "locality_native_clean",
    "region_native_clean",
    "country_native_clean",
    "country_input_class",
    "country_parse_method",
    "country_parse_confidence",
    "address_parse_status",
    "address_completeness_class",
    "address_conflict_flags",
    "address_diagnostic_flags",
    "postcode_diagnostic_flags",
    "selected_component_provenance",
    "native_non_native_relationships",
    "diagnostic_evaluation_status",
    "skipped_oversized_fields",
    "is_po_box",
    "is_historical",
    "probable_non_physical_address",
    "possible_company_only",
    "input_max_field_utf8_bytes",
    "parser_version",
    "rule_registry_version",
    "cleaning_rules_version",
    "placeholder_policy_version",
    "country_reference_version",
    "unicode_reference_version",
    "diagnostic_vocabulary_version",
    "component_schema_version",
    "phase03_version",
    "configuration_fingerprint",
    "implementation_fingerprint",
)
EVIDENCE_COLUMNS = (
    "stable_source_row_id_v1",
    "source_file",
    "source_logical_record_number",
    "evidence_id",
    "span_ordinal",
    "evidence_kind",
    "component",
    "representation",
    "candidate_value",
    "selected",
    "confidence",
    "rule_id",
    "source_field",
    "start_character",
    "end_character_exclusive",
    "conflict_flag",
    "diagnostic_flag",
    "parser_version",
    "rule_registry_version",
    "phase03_version",
)

FILE_STATUSES = ("PENDING", "WRITING", "VALIDATING", "COMPLETE", "FAILED")
PILOT_SEED_DOMAIN = b"safe_geocoding_pipeline:phase03_pilot_v1:seed:1"

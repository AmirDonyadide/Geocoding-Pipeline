from __future__ import annotations

import hashlib
import csv
import gzip
import json
import os
import re
import shutil
import sqlite3
import struct
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from ..phase02.fingerprints import JsonValue, canonical_json_bytes, fingerprint
from ..phase02.schema import base_staging_schema, exact_schema_matches
from .constants import (
    ADDRESS_FIELDS,
    MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
    MANUAL_REVIEW_REASON_CODES_VERSION,
    PILOT_SEED_DOMAIN,
)
from .errors import Phase03Error
from .models import PilotCandidate, PilotSeal
from .references import CountryReference, ScriptReference
from .review import hashed_review_id, manual_review_schema
from .rules import RuleRegistry
from .sampler import PilotSamplingConfig, PilotSelection
from .text import classify_placeholder, tokenize_with_spans

PILOT_RUNNER_VERSION = "phase03_pilot_runner_v1"
SAMPLING_CONTRACT_VERSION = "phase03_sampling_contract_v1"
COUNTRY_SAMPLING_CLASSIFIER_VERSION = "phase03_sampling_country_group_v1"
STRUCTURED_COMPLETENESS_CLASSIFIER_VERSION = "sampling_structured_completeness_v1"
POSTCODE_SAMPLING_CLASSIFIER_VERSION = "postcode_lexical_v1"
REPRESENTATION_SAMPLING_CLASSIFIER_VERSION = "representation_sampling_v2"
ADDRESS_LINE_SAMPLING_CLASSIFIER_VERSION = "address_line_structure_v1"
SAMPLING_MARKER_CLASSIFIER_VERSION = "phase03_sampling_markers_v1"
LOCATION_SAMPLING_CLASSIFIER_VERSION = "location_information_cohort_v1"
IDENTITY_SET_VERSION = "phase03_identity_set_v1"
REVIEW_SAMPLER_VERSION = "phase03_development_review_sampler_v1"
PILOT_CANDIDATE_STATE_SCHEMA_VERSION = "phase03_pilot_candidate_state_v1"
PILOT_MINIMUM_FREE_BYTES = 25 * 1024**3

REVIEW_TOTAL_COUNT = 800
REVIEW_BROAD_COUNT = 400
DOUBLE_REVIEW_COUNT = 200
REVIEW_TARGETS: tuple[tuple[str, str, int], ...] = (
    ("address_parse_status", "PARTIAL", 60),
    ("address_parse_status", "AMBIGUOUS", 40),
    ("address_parse_status", "CONFLICT", 40),
    ("address_parse_status", "UNPARSEABLE", 30),
    ("address_parse_status", "INSUFFICIENT", 30),
    ("review_case", "NATIVE_NON_NATIVE_DIFFERENCE", 30),
    ("review_case", "COUNTRY_REFERENCE_CASE", 30),
    ("review_case", "PO_BOX_CASE", 20),
    ("review_case", "UNIT_FLOOR_BUILDING_CASE", 30),
    ("review_case", "ORGANIZATION_CASE", 20),
    ("review_case", "SHADOW_HOUSE_CANDIDATE", 50),
    ("review_case", "PLACEHOLDER_LIKE_CASE", 10),
    ("review_case", "OVERSIZED_OR_SAFETY_CASE", 10),
)

SAMPLING_COLUMNS = (
    "stable_source_row_id_v1",
    "source_file",
    "source_logical_record_number",
    *ADDRESS_FIELDS,
    "postcode",
    "city",
    "region_in_country",
    "country_iso_code",
    "location_information",
)

PHASE01_SAFETY_ANOMALY_TYPES = frozenset(
    {"MULTILINE_RECORD", "OVERSIZED_FIELD", "OVERSIZED_LOGICAL_RECORD"}
)


def _score(domain: bytes, identity: bytes) -> bytes:
    return hashlib.sha256(domain + b"\0" + identity).digest()


def identity_digest(domain: bytes, identities: Iterable[bytes]) -> str:
    values = sorted(identities)
    digest = hashlib.sha256(domain)
    digest.update(len(values).to_bytes(8, "big"))
    for value in values:
        if len(value) != 32:
            raise ValueError("stable source row ID must be 32 bytes")
        digest.update(value)
    return digest.hexdigest()


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def require_pilot_free_space(
    path: Path, *, minimum_free_bytes: int = 25 * 1024**3
) -> int:
    """Fail closed before production Pass 2 if controlled storage is too small."""
    if minimum_free_bytes < 1:
        raise ValueError("minimum free bytes must be positive")
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            raise FileNotFoundError(path)
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < minimum_free_bytes:
        raise Phase03Error(
            "PILOT_INSUFFICIENT_FREE_DISK",
            f"available={free},required={minimum_free_bytes}",
        )
    return free


@dataclass(frozen=True, slots=True)
class ProductionSamplingContract:
    country_large_min_count: int = 500
    country_medium_min_count: int = 50
    structured_high_min_fields: int = 3
    structured_medium_min_fields: int = 2
    review_allocations: tuple[tuple[str, str, int], ...] = REVIEW_TARGETS
    sampling_field_safety_limit_bytes: int = 65_536
    minimum_free_bytes: int = PILOT_MINIMUM_FREE_BYTES
    approval_status: str = "APPROVED"
    contract_version: str = SAMPLING_CONTRACT_VERSION

    def validate(self, *, production: bool) -> None:
        thresholds = (
            self.country_large_min_count,
            self.country_medium_min_count,
            self.structured_high_min_fields,
            self.structured_medium_min_fields,
        )
        if any(value < 1 for value in thresholds):
            raise ValueError("sampling thresholds must be positive")
        if self.approval_status not in {"REQUIRES_APPROVAL", "APPROVED"}:
            raise ValueError("unsupported sampling approval status")
        if self.contract_version != SAMPLING_CONTRACT_VERSION:
            raise ValueError("unsupported sampling contract version")
        if (
            self.country_large_min_count <= self.country_medium_min_count
        ):
            raise ValueError("large-country threshold must exceed medium threshold")
        if (
            self.structured_high_min_fields <= self.structured_medium_min_fields
        ):
            raise ValueError("high completeness threshold must exceed medium")
        if any(count < 1 for _, _, count in self.review_allocations):
            raise ValueError("review allocations must be positive")
        if any(
            not dimension or not category
            for dimension, category, _ in self.review_allocations
        ) or len({(dimension, category) for dimension, category, _ in self.review_allocations}) != len(
            self.review_allocations
        ):
            raise ValueError("review allocations must be unique and named")
        if any(
            value > 4
            for value in (
                self.structured_high_min_fields,
                self.structured_medium_min_fields,
            )
        ):
            raise ValueError("structured completeness thresholds cannot exceed four")
        if self.sampling_field_safety_limit_bytes < 1:
            raise ValueError("sampling field safety limit must be positive")
        if self.minimum_free_bytes < 1:
            raise ValueError("minimum free bytes must be positive")
        if production and self.approval_status != "APPROVED":
            raise Phase03Error("PILOT_SCIENTIFIC_CONTRACT_REQUIRES_APPROVAL")

    def fingerprint(self) -> str:
        return fingerprint(
            {
                "approval_status": self.approval_status,
                "contract_version": self.contract_version,
                "country_large_min_count": self.country_large_min_count,
                "country_medium_min_count": self.country_medium_min_count,
                "structured_high_min_fields": self.structured_high_min_fields,
                "structured_medium_min_fields": self.structured_medium_min_fields,
                "review_allocations": [list(value) for value in self.review_allocations],
                "sampling_field_safety_limit_bytes": self.sampling_field_safety_limit_bytes,
                "minimum_free_bytes": self.minimum_free_bytes,
                "sampling_passes": [
                    ["country_iso_code"],
                    list(SAMPLING_COLUMNS),
                    ["development_payload_join_only"],
                ],
                "country_group_policy": {
                    "missing": ["", ".", "-"],
                    "ambiguous": ["Na", "Nan", "Null"],
                    "assigned": "exact_CLDR_alpha2_alpha3_canonical_English_name",
                    "unusual": "domain_separated_SHA256_exact_UTF8",
                },
                "country_cohort_thresholds": {"rare_lt": 50, "medium_lt": 500},
                "rare_primary_groups": "include_all_or_fail",
                "review_total_count": REVIEW_TOTAL_COUNT,
                "review_broad_count": REVIEW_BROAD_COUNT,
                "double_review_count": DOUBLE_REVIEW_COUNT,
                "candidate_state_schema_version": PILOT_CANDIDATE_STATE_SCHEMA_VERSION,
                "identity_set_version": IDENTITY_SET_VERSION,
                "seal_version": "phase03_pilot_seal_v1",
                "classifier_versions": [
                    COUNTRY_SAMPLING_CLASSIFIER_VERSION,
                    STRUCTURED_COMPLETENESS_CLASSIFIER_VERSION,
                    POSTCODE_SAMPLING_CLASSIFIER_VERSION,
                    REPRESENTATION_SAMPLING_CLASSIFIER_VERSION,
                    ADDRESS_LINE_SAMPLING_CLASSIFIER_VERSION,
                    SAMPLING_MARKER_CLASSIFIER_VERSION,
                    LOCATION_SAMPLING_CLASSIFIER_VERSION,
                ],
                "reference_identities": {
                    "country": "country_reference_v2_iso_normative_cldr_46_1_operational",
                    "scripts": "unicode_ucd_16_0_0_scripts_20240430",
                },
                "rule_registry": {
                    "version": "phase03_rule_registry_v2",
                    "sha256": "d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5",
                },
                "pilot_sampling": {
                    "total": 12000,
                    "development": 8000,
                    "locked_evaluation": 4000,
                    "secondary_minimum": 50,
                    "primary_group_maximum": 500,
                    "seed_domain_hex": PILOT_SEED_DOMAIN.hex(),
                    "ranking": "SHA256_domain_NUL_stable_source_row_id_v1",
                },
                "materialization": {
                    "development_only": True,
                    "locked_payload_prohibited": True,
                    "atomic_owner_only": True,
                },
            }
        )


def sampling_contract_summary(contract: ProductionSamplingContract) -> dict[str, Any]:
    pilot_config = proposed_production_pilot_config()
    return {
        "status": contract.approval_status,
        "runner_version": PILOT_RUNNER_VERSION,
        "contract_version": contract.contract_version,
        "contract_fingerprint": contract.fingerprint(),
        "selected_columns": list(SAMPLING_COLUMNS),
        "expected_selected_column_passes": 2,
        "future_payload_passes": 1,
        "pilot_total_count": pilot_config.total_count,
        "development_count": pilot_config.development_count,
        "locked_evaluation_count": pilot_config.locked_evaluation_count,
        "minimum_per_secondary_stratum": pilot_config.minimum_per_stratum,
        "maximum_per_primary_group": pilot_config.maximum_primary_stratum,
        "proposed_primary_stratum": pilot_config.primary_stratum,
        "unresolved_scientific_decisions": [],
    }


def proposed_production_pilot_config() -> PilotSamplingConfig:
    return PilotSamplingConfig(primary_stratum="primary_country_group")


def load_phase01_safety_locations(
    path: Path,
) -> dict[tuple[str, int], tuple[str, ...]]:
    """Load sanitized Phase 1 anomaly locations without reading any raw values."""
    try:
        stream = (
            gzip.open(path, "rt", encoding="utf-8", newline="")
            if path.suffix == ".gz"
            else path.open("rt", encoding="utf-8", newline="")
        )
        with stream:
            reader = csv.DictReader(stream)
            required = {"relative_path", "logical_record_number", "anomaly_type"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ValueError("Phase 1 safety report schema mismatch")
            locations: dict[tuple[str, int], set[str]] = {}
            for row in reader:
                anomaly_type = row["anomaly_type"]
                if anomaly_type not in PHASE01_SAFETY_ANOMALY_TYPES:
                    continue
                try:
                    logical_record_number = int(row["logical_record_number"])
                except (TypeError, ValueError) as error:
                    raise ValueError("invalid Phase 1 logical record number") from error
                relative_path = row["relative_path"]
                if not relative_path or logical_record_number < 1:
                    raise ValueError("invalid Phase 1 safety location")
                locations.setdefault(
                    (relative_path, logical_record_number), set()
                ).add(anomaly_type)
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("cannot read Phase 1 safety report") from error
    return {
        location: tuple(sorted(anomaly_types))
        for location, anomaly_types in sorted(locations.items())
    }


@dataclass(slots=True)
class Phase01SafetyLocationTracker:
    expected: Mapping[tuple[str, int], tuple[str, ...]]
    seen: Counter[tuple[str, int]]

    @classmethod
    def from_report(cls, path: Path) -> "Phase01SafetyLocationTracker":
        return cls(load_phase01_safety_locations(path), Counter())

    def observe(self, source_file: str, logical_record_number: int) -> bool:
        location = (source_file, logical_record_number)
        if location not in self.expected:
            return False
        self.seen[location] += 1
        if self.seen[location] > 1:
            raise ValueError("Phase 1 safety location matched more than once")
        return True

    def validate_complete(self) -> None:
        missing = set(self.expected) - set(self.seen)
        unexpected = set(self.seen) - set(self.expected)
        if missing or unexpected or any(count != 1 for count in self.seen.values()):
            raise ValueError("Phase 1 safety location reconciliation failed")


def classify_postcode_v1(raw: str) -> str:
    state = classify_placeholder(raw)
    if state == "SEMANTIC_MISSING":
        return "SEMANTIC_MISSING"
    if state == "AMBIGUOUS_PLACEHOLDER_LIKE":
        return "AMBIGUOUS_PLACEHOLDER_LIKE"
    if re.fullmatch(r"[0-9]+\.[0-9]+", raw):
        return "DECIMAL_LOOKING"
    if any(character.isspace() for character in raw):
        return "CONTAINS_UNICODE_WHITESPACE"
    if "-" in raw:
        return "CONTAINS_ASCII_HYPHEN"
    if len(raw) > 1 and raw.startswith("0") and raw.isascii() and raw.isdigit():
        return "LEADING_ZERO_ASCII_DIGITS"
    if raw.isascii() and raw.isdigit():
        return "ASCII_DIGITS"
    if raw.isascii() and raw.isalpha():
        return "ASCII_LETTERS"
    if (
        raw.isascii()
        and raw.isalnum()
        and any(character.isalpha() for character in raw)
        and any(character.isdigit() for character in raw)
    ):
        return "ASCII_ALPHANUMERIC"
    return "OTHER"


def country_sampling_group_v1(
    raw: str, country_reference: CountryReference
) -> tuple[str, str]:
    state = classify_placeholder(raw)
    if state == "SEMANTIC_MISSING":
        return "MISSING", "MISSING"
    if state == "AMBIGUOUS_PLACEHOLDER_LIKE":
        return "AMBIGUOUS_PLACEHOLDER", "AMBIGUOUS_PLACEHOLDER"
    record, _ = country_reference.exact_lookup(raw)
    if record is not None:
        return f"ASSIGNED:{record.alpha2}", "ASSIGNED_EXACT"
    digest = hashlib.sha256(
        b"safe_geocoding_pipeline:phase03_sampling_country_group_v1\0"
        + raw.encode("utf-8")
    ).hexdigest()
    return f"UNUSUAL:{digest}", "UNUSUAL"


def country_cohort_bucket_v1(
    primary_group: str,
    population_count: int,
    contract: ProductionSamplingContract,
) -> str:
    large = contract.country_large_min_count
    medium = contract.country_medium_min_count
    if population_count >= large:
        return "LARGE"
    if population_count >= medium:
        return "MEDIUM"
    return "RARE"


def structured_completeness_v1(
    row: Mapping[str, Any], contract: ProductionSamplingContract
) -> tuple[str, str]:
    populated = sum(
        classify_placeholder(str(row[name])) == "CONTENT"
        for name in ("postcode", "city", "region_in_country", "country_iso_code")
    )
    ambiguous = any(
        classify_placeholder(str(row[name])) == "AMBIGUOUS_PLACEHOLDER_LIKE"
        for name in ("postcode", "city", "region_in_country", "country_iso_code")
    )
    if populated >= contract.structured_high_min_fields:
        category = "HIGH"
    elif populated >= contract.structured_medium_min_fields:
        category = "MEDIUM"
    elif populated == 1:
        category = "LOW"
    else:
        category = "NONE"
    return category, "AMBIGUOUS_PRESENT" if ambiguous else "AMBIGUOUS_ABSENT"


def address_line_structure_v1(row: Mapping[str, Any]) -> dict[str, str]:
    non_native = sum(
        classify_placeholder(str(row[f"street_address_line_{index}"])) == "CONTENT"
        for index in range(1, 5)
    )
    native = sum(
        classify_placeholder(str(row[f"street_address_line_{index}_native"])) == "CONTENT"
        for index in range(1, 5)
    )
    relationship = (
        "EQUAL"
        if native == non_native
        else "MORE_NATIVE"
        if native > non_native
        else "MORE_NON_NATIVE"
    )
    ambiguous_non_native = any(
        classify_placeholder(str(row[f"street_address_line_{index}"]))
        == "AMBIGUOUS_PLACEHOLDER_LIKE"
        for index in range(1, 5)
    )
    ambiguous_native = any(
        classify_placeholder(str(row[f"street_address_line_{index}_native"]))
        == "AMBIGUOUS_PLACEHOLDER_LIKE"
        for index in range(1, 5)
    )
    return {
        "non_native_line_count": str(non_native),
        "native_line_count": str(native),
        "line_count_relationship": relationship,
        "non_native_ambiguous_present": str(ambiguous_non_native).upper(),
        "native_ambiguous_present": str(ambiguous_native).upper(),
    }


def representation_strata_v1(
    row: Mapping[str, Any],
    script_reference: ScriptReference,
    *,
    maximum_field_utf8_bytes: int = 65_536,
) -> dict[str, str]:
    non_native_values = [str(row[f"street_address_line_{index}"]) for index in range(1, 5)]
    native_values = [str(row[f"street_address_line_{index}_native"]) for index in range(1, 5)]
    non_native_present = [value for value in non_native_values if classify_placeholder(value) == "CONTENT"]
    native_present = [value for value in native_values if classify_placeholder(value) == "CONTENT"]
    oversized_non_native = any(
        len(value.encode("utf-8")) > maximum_field_utf8_bytes
        for value in non_native_present
    )
    oversized_native = any(
        len(value.encode("utf-8")) > maximum_field_utf8_bytes
        for value in native_present
    )
    if not native_present and not non_native_present:
        relationship = "NO_ADDRESS_LINE_CONTENT"
    elif native_present and not non_native_present:
        relationship = "NATIVE_ONLY"
    elif non_native_present and not native_present:
        relationship = "NO_NATIVE_CONTENT"
    elif [classify_placeholder(value) == "CONTENT" for value in native_values] == [
        classify_placeholder(value) == "CONTENT" for value in non_native_values
    ] and all(
        unicodedata.normalize("NFC", native) == unicodedata.normalize("NFC", non_native)
        for native, non_native in zip(native_values, non_native_values, strict=True)
        if classify_placeholder(native) == "CONTENT"
    ):
        relationship = "NFC_EQUIVALENT"
    elif [classify_placeholder(value) == "CONTENT" for value in native_values] == [
        classify_placeholder(value) == "CONTENT" for value in non_native_values
    ]:
        relationship = "DIFFERENT_SAME_STRUCTURE"
    else:
        relationship = "PARTIAL_DIFFERENT_STRUCTURE"

    def script_category(values: Sequence[str], oversized: bool) -> str:
        if oversized:
            return "OVERSIZED_SKIPPED"
        combined = "".join(values)
        if not combined:
            return "NO_CONTENT"
        scripts = script_reference.distinctive_scripts(combined)
        if not scripts:
            return "UNDETERMINED"
        if scripts == {"Latin"}:
            return "LATIN_ONLY"
        if len(scripts) == 1:
            return "SINGLE_NON_LATIN"
        return "MIXED_DISTINCTIVE"

    return {
        "native_relationship": relationship,
        "non_native_script": script_category(non_native_present, oversized_non_native),
        "native_script": script_category(native_present, oversized_native),
        "representation_oversized_skipped": str(
            oversized_non_native or oversized_native
        ).upper(),
    }


def marker_strata_v1(
    row: Mapping[str, Any], registry: RuleRegistry
) -> dict[str, str]:
    # Importing the engine matcher avoids a second marker grammar. This helper emits
    # only presence strata; it cannot create parser candidates or core components.
    from .engine import _marker_matches

    marker_names = {
        "PO_BOX_MARKER_EN_V1": "marker_po_box",
        "UNIT_MARKER_EN_V1": "marker_unit",
        "FLOOR_MARKER_EN_V1": "marker_floor",
        "BUILDING_MARKER_EN_V1": "marker_building",
        "ORGANIZATION_LEGAL_FORM_EN_V1": "marker_organization",
        "HISTORICAL_MARKER_EN_V1": "marker_historical",
        "HOUSE_NUMBER_EDGE_CANDIDATE_V1": "shadow_house_candidate",
    }
    values: dict[str, str] = {}
    utf8_lengths = {
        field: len(str(row[field]).encode("utf-8")) for field in ADDRESS_FIELDS
    }
    for rule in registry.ordered_rules():
        if rule.matcher not in {
            "MARKER_WITH_IDENTIFIER",
            "SEGMENT_LEADING_MARKER_WITH_NAME",
            "SEGMENT_ENDING_LEGAL_FORM",
            "PHRASE_PRESENT",
            "BOUNDED_EDGE_HOUSE_NUMBER",
        }:
            continue
        present = False
        for field in rule.eligible_source_fields:
            raw = str(row[field])
            if utf8_lengths[field] > rule.maximum_input_utf8_bytes:
                continue
            if _marker_matches(raw, tokenize_with_spans(raw), rule):
                present = True
                break
        name = marker_names.get(rule.rule_id)
        if name is None:
            raise Phase03Error("SAMPLING_MARKER_RULE_UNREGISTERED", rule.rule_id)
        if name == "shadow_house_candidate":
            values[name] = (
                "SHADOW_HOUSE_CANDIDATE_PRESENT"
                if present
                else "SHADOW_HOUSE_CANDIDATE_ABSENT"
            )
        else:
            values[name] = f"{'_'.join(name.split('_')[1:]).upper()}_MARKER_{'PRESENT' if present else 'ABSENT'}"
    return values


def location_information_cohort_v1(raw: str) -> str:
    expected = {
        "previous_geocoding_failure": "PREVIOUS_GEOCODING_FAILURE",
        "no_geocoding_information": "NO_GEOCODING_INFORMATION",
        "region_interpolated": "REGION_INTERPOLATED",
    }
    return expected.get(raw, "OTHER_UNEXPECTED")


def classify_sampling_row_v1(
    row: Mapping[str, Any],
    *,
    contract: ProductionSamplingContract,
    country_reference: CountryReference,
    script_reference: ScriptReference,
    rule_registry: RuleRegistry,
    country_counts: Mapping[str, int],
    targeted_safety_case: bool = False,
) -> PilotCandidate:
    if set(SAMPLING_COLUMNS) - set(row):
        raise ValueError("sampling row is missing required selected columns")
    stable_id = bytes(row["stable_source_row_id_v1"])
    primary_group, country_class = country_sampling_group_v1(
        str(row["country_iso_code"]), country_reference
    )
    line_structure = address_line_structure_v1(row)
    representation = representation_strata_v1(
        row,
        script_reference,
        maximum_field_utf8_bytes=contract.sampling_field_safety_limit_bytes,
    )
    completeness, structured_ambiguous = structured_completeness_v1(row, contract)
    combined_script_category = (
        f"NON_NATIVE={representation['non_native_script']}|"
        f"NATIVE={representation['native_script']}"
    )
    strata = {
        "primary_country_group": primary_group,
        "country_sampling_class": country_class,
        "country_cohort": country_cohort_bucket_v1(
            primary_group, country_counts[primary_group], contract
        ),
        "structured_completeness": completeness,
        "structured_ambiguous": structured_ambiguous,
        "postcode_lexical": classify_postcode_v1(str(row["postcode"])),
        **representation,
        "script_category": combined_script_category,
        **line_structure,
        "location_information": location_information_cohort_v1(
            str(row["location_information"])
        ),
        **marker_strata_v1(row, rule_registry),
    }
    return PilotCandidate(
        stable_id,
        strata,
        targeted_safety_case,
        str(row["source_file"]) if targeted_safety_case else None,
        int(row["source_logical_record_number"]) if targeted_safety_case else None,
    )


class SQLitePilotCandidateStore:
    """Exact out-of-core pilot candidate and membership store."""

    def __init__(
        self,
        path: Path,
        *,
        config: PilotSamplingConfig,
        classification_contract_fingerprint: str = "SYNTHETIC_UNAPPROVED",
        data_scope: str = "SYNTHETIC_ONLY",
        classification_contract: ProductionSamplingContract | None = None,
        production_binding_fingerprint: str | None = None,
    ) -> None:
        if data_scope not in {"SYNTHETIC_ONLY", "PRODUCTION"}:
            raise ValueError("unsupported pilot candidate-store data scope")
        if data_scope == "PRODUCTION":
            if classification_contract is None:
                raise Phase03Error("PILOT_PRODUCTION_CONTRACT_NOT_APPROVED")
            classification_contract.validate(production=True)
            if production_binding_fingerprint is None:
                raise Phase03Error("PILOT_PRODUCTION_STATE_BINDING_MISSING")
            classification_contract_fingerprint = fingerprint(
                {
                    "sampling_contract_fingerprint": classification_contract.fingerprint(),
                    "production_binding_fingerprint": production_binding_fingerprint,
                }
            )
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        self.connection = sqlite3.connect(path)
        path.chmod(0o600)
        self.connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            PRAGMA temp_store=FILE;
            CREATE TABLE IF NOT EXISTS candidate (
              stable_id BLOB PRIMARY KEY CHECK(length(stable_id)=32),
              primary_group TEXT NOT NULL,
              quota_score BLOB NOT NULL,
              fill_score BLOB NOT NULL,
              split_score BLOB NOT NULL,
              targeted INTEGER NOT NULL CHECK(targeted IN (0,1))
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS membership (
              dimension TEXT NOT NULL,
              category TEXT NOT NULL,
              stable_id BLOB NOT NULL,
              PRIMARY KEY(dimension, category, stable_id)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS selected (
              stable_id BLOB PRIMARY KEY CHECK(length(stable_id)=32),
              primary_group TEXT NOT NULL
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS safety_location (
              source_file TEXT NOT NULL,
              logical_record_number INTEGER NOT NULL CHECK(logical_record_number >= 1),
              PRIMARY KEY(source_file, logical_record_number)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS checkpoint (
              shard_id TEXT PRIMARY KEY,
              shard_identity TEXT NOT NULL,
              row_count INTEGER NOT NULL CHECK(row_count >= 0),
              status TEXT NOT NULL CHECK(status = 'COMPLETE')
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS run_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            ) WITHOUT ROWID;
            """
        )
        self.config = config
        self.effective_sampling_fingerprint = fingerprint(
            {
                "classification_contract_fingerprint": (
                    classification_contract_fingerprint
                ),
                "pilot_sampling_config_fingerprint": config.fingerprint(),
                "pilot_runner_version": PILOT_RUNNER_VERSION,
            }
        )
        expected_metadata = {
            "candidate_state_schema_version": PILOT_CANDIDATE_STATE_SCHEMA_VERSION,
            "pilot_runner_version": PILOT_RUNNER_VERSION,
            "sampling_config_fingerprint": config.fingerprint(),
            "classification_contract_fingerprint": (
                classification_contract_fingerprint
            ),
            "effective_sampling_fingerprint": self.effective_sampling_fingerprint,
            "data_scope": data_scope,
        }
        with self.connection:
            for key, value in expected_metadata.items():
                observed = self.connection.execute(
                    "SELECT value FROM run_metadata WHERE key=?", (key,)
                ).fetchone()
                if observed is None:
                    self.connection.execute(
                        "INSERT INTO run_metadata VALUES (?,?)", (key, value)
                    )
                elif observed[0] != value:
                    raise ValueError("candidate-store configuration mismatch")
        self._selection_total = 0
        self._primary_counts: Counter[str] = Counter()

    def close(self) -> None:
        self.connection.close()

    def validate_integrity(self) -> None:
        result = self.connection.execute("PRAGMA integrity_check").fetchone()
        if result != ("ok",):
            raise ValueError("pilot candidate-state SQLite integrity check failed")

    def ingest(self, candidates: Iterable[PilotCandidate], *, batch_size: int = 1000) -> int:
        quota_domain = self.config.seed_domain + b":quota"
        fill_domain = self.config.seed_domain + b":fill"
        split_domain = self.config.seed_domain + b":split"
        count = 0
        pending_candidates: list[tuple[Any, ...]] = []
        pending_memberships: list[tuple[str, str, bytes]] = []
        pending_safety: list[tuple[str, int]] = []

        def flush() -> None:
            if not pending_candidates:
                return
            try:
                with self.connection:
                    self.connection.executemany(
                        "INSERT INTO candidate VALUES (?,?,?,?,?,?)", pending_candidates
                    )
                    self.connection.executemany(
                        "INSERT INTO membership VALUES (?,?,?)", pending_memberships
                    )
                    self.connection.executemany(
                        "INSERT INTO safety_location VALUES (?,?)", pending_safety
                    )
            except sqlite3.IntegrityError as error:
                raise ValueError("pilot population contains duplicate stable IDs") from error
            pending_candidates.clear()
            pending_memberships.clear()
            pending_safety.clear()

        for candidate in candidates:
            identity = candidate.stable_source_row_id_v1
            primary = candidate.strata.get(self.config.primary_stratum)
            if not primary:
                raise ValueError("pilot candidate lacks configured primary stratum")
            pending_candidates.append(
                (
                    identity,
                    primary,
                    _score(quota_domain, identity),
                    _score(fill_domain, identity),
                    _score(split_domain, identity),
                    int(candidate.targeted_safety_case),
                )
            )
            pending_memberships.extend(
                (dimension, category, identity)
                for dimension, category in sorted(candidate.strata.items())
            )
            if candidate.safety_source_file is not None:
                pending_safety.append(
                    (
                        candidate.safety_source_file,
                        cast(int, candidate.safety_logical_record_number),
                    )
                )
            count += 1
            if len(pending_candidates) >= batch_size:
                flush()
        flush()
        return count

    def ingest_shard(
        self,
        shard_id: str,
        shard_identity: str,
        candidates: Iterable[PilotCandidate],
        *,
        batch_size: int = 1_000,
    ) -> tuple[int, bool]:
        """Atomically ingest or resume one exact input shard.

        A completed matching checkpoint is reused. An interruption rolls back the
        entire shard, so a partial candidate population cannot look resumable.
        """
        if not shard_id or not shard_identity:
            raise ValueError("shard identity cannot be empty")
        observed = self.connection.execute(
            "SELECT shard_identity, row_count, status FROM checkpoint WHERE shard_id=?",
            (shard_id,),
        ).fetchone()
        if observed is not None:
            if observed[0] != shard_identity or observed[2] != "COMPLETE":
                raise ValueError("candidate-store shard checkpoint mismatch")
            return int(observed[1]), True

        quota_domain = self.config.seed_domain + b":quota"
        fill_domain = self.config.seed_domain + b":fill"
        split_domain = self.config.seed_domain + b":split"
        pending_candidates: list[tuple[Any, ...]] = []
        pending_memberships: list[tuple[str, str, bytes]] = []
        pending_safety: list[tuple[str, int]] = []
        count = 0

        def flush() -> None:
            self.connection.executemany(
                "INSERT INTO candidate VALUES (?,?,?,?,?,?)", pending_candidates
            )
            self.connection.executemany(
                "INSERT INTO membership VALUES (?,?,?)", pending_memberships
            )
            self.connection.executemany(
                "INSERT INTO safety_location VALUES (?,?)", pending_safety
            )
            pending_candidates.clear()
            pending_memberships.clear()
            pending_safety.clear()

        try:
            self.connection.execute("BEGIN IMMEDIATE")
            for candidate in candidates:
                identity = candidate.stable_source_row_id_v1
                primary = candidate.strata.get(self.config.primary_stratum)
                if not primary:
                    raise ValueError("pilot candidate lacks configured primary stratum")
                pending_candidates.append(
                    (
                        identity,
                        primary,
                        _score(quota_domain, identity),
                        _score(fill_domain, identity),
                        _score(split_domain, identity),
                        int(candidate.targeted_safety_case),
                    )
                )
                pending_memberships.extend(
                    (dimension, category, identity)
                    for dimension, category in sorted(candidate.strata.items())
                )
                if candidate.safety_source_file is not None:
                    pending_safety.append(
                        (
                            candidate.safety_source_file,
                            cast(int, candidate.safety_logical_record_number),
                        )
                    )
                count += 1
                if len(pending_candidates) >= batch_size:
                    flush()
            flush()
            self.connection.execute(
                "INSERT INTO checkpoint VALUES (?,?,?,'COMPLETE')",
                (shard_id, shard_identity, count),
            )
            self.connection.commit()
        except (sqlite3.Error, ValueError) as error:
            self.connection.rollback()
            if isinstance(error, sqlite3.IntegrityError):
                raise ValueError("pilot population contains duplicate stable IDs") from error
            raise
        return count, False

    def safety_locations(self) -> set[tuple[str, int]]:
        return {
            (str(source_file), int(record_number))
            for source_file, record_number in self.connection.execute(
                "SELECT source_file, logical_record_number FROM safety_location"
            )
        }

    def _add(self, identity: bytes, primary: str) -> bool:
        if self._selection_total >= self.config.total_count:
            return False
        if self._primary_counts[primary] >= self.config.maximum_primary_stratum:
            return False
        with self.connection:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO selected VALUES (?,?)", (identity, primary)
            )
        if cursor.rowcount == 1:
            self._selection_total += 1
            self._primary_counts[primary] += 1
            return True
        return False

    def select(
        self, *, input_phase02_manifest_identity: str, selection_timestamp: str
    ) -> PilotSelection:
        with self.connection:
            self.connection.execute("DELETE FROM selected")
        self._selection_total = 0
        self._primary_counts.clear()
        population_count = int(
            self.connection.execute("SELECT COUNT(*) FROM candidate").fetchone()[0]
        )
        if population_count < self.config.total_count:
            raise ValueError("pilot population is smaller than requested sample")
        for identity, primary in self.connection.execute(
            "SELECT stable_id, primary_group FROM candidate WHERE targeted=1 "
            "ORDER BY stable_id"
        ):
            if not self._add(bytes(identity), str(primary)):
                raise ValueError("targeted safety cases violate primary cap")
        # Every row from every rare exact primary-country group is mandatory.
        # Country groups have fewer than 50 members by definition, so this is
        # compatible with the 500-row per-primary-group cap unless the overall
        # 12,000-row sample itself is infeasible.
        for identity, primary in self.connection.execute(
            "SELECT c.stable_id, c.primary_group FROM membership m "
            "JOIN candidate c USING(stable_id) "
            "WHERE m.dimension='country_cohort' AND m.category='RARE' "
            "ORDER BY c.primary_group, c.stable_id"
        ):
            if not self._add(bytes(identity), str(primary)):
                already_selected = self.connection.execute(
                    "SELECT 1 FROM selected WHERE stable_id=?", (identity,)
                ).fetchone()
                if already_selected is None:
                    raise ValueError("rare primary-group inclusion is infeasible")
        groups = self.connection.execute(
            "SELECT dimension, category, COUNT(*) FROM membership "
            "WHERE dimension != ? GROUP BY dimension, category "
            "ORDER BY dimension, category",
            (self.config.primary_stratum,),
        ).fetchall()
        for dimension, category, available in groups:
            target = min(int(available), self.config.minimum_per_stratum)
            represented = int(
                self.connection.execute(
                    "SELECT COUNT(*) FROM membership m JOIN selected s USING(stable_id) "
                    "WHERE m.dimension=? AND m.category=?",
                    (dimension, category),
                ).fetchone()[0]
            )
            cursor = self.connection.execute(
                "SELECT c.stable_id, c.primary_group FROM membership m "
                "JOIN candidate c USING(stable_id) LEFT JOIN selected s USING(stable_id) "
                "WHERE m.dimension=? AND m.category=? AND s.stable_id IS NULL "
                "ORDER BY c.quota_score, c.stable_id",
                (dimension, category),
            )
            for identity, primary in cursor:
                if self._add(bytes(identity), str(primary)):
                    represented += 1
                if represented >= target:
                    break
            if represented < target:
                raise ValueError("pilot quotas/caps cannot satisfy minimum stratum quota")
        selected_count = int(
            self.connection.execute("SELECT COUNT(*) FROM selected").fetchone()[0]
        )
        if selected_count > self.config.total_count:
            raise ValueError("targeted/quota selection exceeds pilot total")
        for identity, primary in self.connection.execute(
            "SELECT c.stable_id, c.primary_group FROM candidate c "
            "LEFT JOIN selected s USING(stable_id) WHERE s.stable_id IS NULL "
            "ORDER BY c.fill_score, c.stable_id"
        ):
            if self._add(bytes(identity), str(primary)):
                selected_count += 1
            if selected_count == self.config.total_count:
                break
        if selected_count != self.config.total_count:
            raise ValueError("pilot quotas/caps cannot produce the requested sample")
        ordered = [
            bytes(row[0])
            for row in self.connection.execute(
                "SELECT s.stable_id FROM selected s JOIN candidate c USING(stable_id) "
                "ORDER BY c.split_score, s.stable_id"
            )
        ]
        development = tuple(ordered[: self.config.development_count])
        locked = tuple(ordered[self.config.development_count :])
        seal = PilotSeal(
            pilot_version=self.config.pilot_version,
            sampling_config_fingerprint=self.effective_sampling_fingerprint,
            seed=self.config.seed_domain.decode("utf-8"),
            development_identity_digest=identity_digest(
                b"phase03:development_identities_v1\0", development
            ),
            locked_evaluation_identity_digest=identity_digest(
                b"phase03:locked_identities_v1\0", locked
            ),
            selection_timestamp=selection_timestamp,
            input_phase02_manifest_identity=input_phase02_manifest_identity,
            development_count=len(development),
            locked_evaluation_count=len(locked),
        )
        return PilotSelection(development, locked, seal)


_IDENTITY_MAGIC = b"SGP3IDS1"


def write_identity_set(
    path: Path,
    identities: Iterable[bytes],
    *,
    partition: str,
    manifest_identity: str,
    sampling_config_fingerprint: str,
) -> dict[str, Any]:
    values = sorted(identities)
    if len(values) != len(set(values)) or any(len(value) != 32 for value in values):
        raise ValueError("identity set must contain unique 32-byte values")
    metadata: dict[str, JsonValue] = {
        "identity_set_version": IDENTITY_SET_VERSION,
        "partition": partition,
        "count": len(values),
        "manifest_identity": manifest_identity,
        "sampling_config_fingerprint": sampling_config_fingerprint,
        "identity_digest": identity_digest(
            f"phase03:{partition.lower()}_identity_file_v1\0".encode(), values
        ),
    }
    metadata_bytes = canonical_json_bytes(metadata)
    payload = (
        _IDENTITY_MAGIC
        + struct.pack(">Q", len(metadata_bytes))
        + metadata_bytes
        + struct.pack(">Q", len(values))
        + b"".join(values)
    )
    checksum = hashlib.sha256(payload).digest()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError("identity output already exists")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(payload)
        stream.write(checksum)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)
    _fsync_parent(path)
    return metadata


def read_identity_set(path: Path) -> tuple[dict[str, Any], tuple[bytes, ...]]:
    data = path.read_bytes()
    if len(data) < 56 or data[:8] != _IDENTITY_MAGIC:
        raise ValueError("invalid identity-set file")
    payload, expected = data[:-32], data[-32:]
    if hashlib.sha256(payload).digest() != expected:
        raise ValueError("identity-set checksum mismatch")
    metadata_size = struct.unpack(">Q", payload[8:16])[0]
    metadata_end = 16 + metadata_size
    metadata = json.loads(payload[16:metadata_end])
    if not isinstance(metadata, dict) or metadata.get("identity_set_version") != IDENTITY_SET_VERSION:
        raise ValueError("identity-set version mismatch")
    count = struct.unpack(">Q", payload[metadata_end : metadata_end + 8])[0]
    identity_bytes = payload[metadata_end + 8 :]
    if len(identity_bytes) != count * 32:
        raise ValueError("identity-set count mismatch")
    values = tuple(
        identity_bytes[index : index + 32]
        for index in range(0, len(identity_bytes), 32)
    )
    if values != tuple(sorted(set(values))) or metadata.get("count") != count:
        raise ValueError("identity-set ordering/uniqueness mismatch")
    partition = metadata.get("partition")
    if not isinstance(partition, str):
        raise ValueError("identity-set partition metadata mismatch")
    expected_digest = identity_digest(
        f"phase03:{partition.lower()}_identity_file_v1\0".encode(), values
    )
    if metadata.get("identity_digest") != expected_digest:
        raise ValueError("identity-set semantic digest mismatch")
    return cast(dict[str, Any], metadata), values


def write_pilot_seal(
    path: Path,
    seal: PilotSeal,
    *,
    sampler_version: str,
    git_commit: str,
    reference_configuration_fingerprint: str,
    sampling_contract: ProductionSamplingContract | None = None,
    phase03_configuration_fingerprint: str = "",
    rule_registry_fingerprint: str = (
        "d1448859f8436dbe466cab81aee926ab6851b294f5ec664491840bac84627fd5"
    ),
) -> None:
    contract = sampling_contract or ProductionSamplingContract()
    contract.validate(production=True)
    payload: dict[str, JsonValue] = {
        **seal.portable_dict(),
        "pilot_seal_version": "phase03_pilot_seal_v1",
        "sampler_version": sampler_version,
        "git_commit": git_commit,
        "reference_configuration_fingerprint": reference_configuration_fingerprint,
        "sampling_contract_version": contract.contract_version,
        "sampling_contract_fingerprint": contract.fingerprint(),
        "phase03_configuration_fingerprint": phase03_configuration_fingerprint,
        "rule_registry_fingerprint": rule_registry_fingerprint,
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    temporary = path.with_name(f".{path.name}.tmp")
    if path.exists() or temporary.exists():
        raise FileExistsError("pilot seal already exists")
    with temporary.open("xb") as stream:
        os.chmod(temporary, 0o600)
        stream.write(canonical_json_bytes(payload) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o600)
    _fsync_parent(path)


def materialize_development_payload(
    input_paths: Sequence[Path],
    output_path: Path,
    *,
    development_ids: set[bytes],
    locked_ids: set[bytes],
    batch_rows: int = 25_000,
    expected_development_count: int = 8_000,
) -> int:
    if development_ids & locked_ids:
        raise ValueError("development and locked identities overlap")
    if len(development_ids) != expected_development_count:
        raise ValueError("development identity count differs from approved count")
    found: set[bytes] = set()
    output_batches: list[pa.RecordBatch] = []
    for path in input_paths:
        parquet = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=True)
        if not exact_schema_matches(parquet.schema_arrow):
            raise Phase03Error("PHASE02_SCHEMA_MISMATCH")
        for batch in parquet.iter_batches(batch_size=batch_rows, use_threads=False):
            ids = batch.column(batch.schema.get_field_index("stable_source_row_id_v1"))
            keep: list[int] = []
            for index, value in enumerate(ids.to_pylist()):
                identity = bytes(value)
                if identity in locked_ids:
                    continue
                if identity in development_ids:
                    if identity in found:
                        raise ValueError("development identity appears more than once")
                    found.add(identity)
                    keep.append(index)
            if keep:
                output_batches.append(batch.take(pa.array(keep, type=pa.int64())))
    missing = development_ids - found
    if missing or len(found) != len(development_ids):
        raise ValueError("expected development identity is missing")
    table = pa.Table.from_batches(output_batches, schema=base_staging_schema())
    observed_ids = {bytes(value) for value in table["stable_source_row_id_v1"].to_pylist()}
    if observed_ids & locked_ids or observed_ids != development_ids:
        raise ValueError("development-only join reconciliation failed")
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_path.parent.chmod(0o700)
    temporary = output_path.with_name(f".{output_path.name}.tmp")
    if output_path.exists() or temporary.exists():
        raise FileExistsError("development payload output exists")
    pq.write_table(
        table,
        temporary,
        compression="zstd",
        compression_level=3,
        row_group_size=batch_rows,
        write_statistics=False,
        write_page_checksum=True,
    )
    temporary.chmod(0o600)
    verified = pq.ParquetFile(
        temporary, page_checksum_verification=True, pre_buffer=True
    ).read(use_threads=False)
    if verified.num_rows != len(development_ids):
        raise ValueError("development payload read-back row mismatch")
    os.replace(temporary, output_path)
    output_path.chmod(0o600)
    with output_path.open("rb") as stream:
        os.fsync(stream.fileno())
    _fsync_parent(output_path)
    return int(verified.num_rows)


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    stable_source_row_id_v1: bytes
    strata: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class DevelopmentReviewSelection:
    review_ids: tuple[bytes, ...]
    broad_representation_ids: tuple[bytes, ...]
    targeted_ids: tuple[bytes, ...]
    independent_double_review_ids: tuple[bytes, ...]
    diagnostics: tuple[str, ...]


def select_development_review_sample_plan(
    candidates: Iterable[ReviewCandidate],
    *,
    target_count: int = REVIEW_TOTAL_COUNT,
    broad_count: int = REVIEW_BROAD_COUNT,
    allocations: Sequence[tuple[str, str, int]] = REVIEW_TARGETS,
    double_review_count: int = DOUBLE_REVIEW_COUNT,
    seed_domain: bytes = PILOT_SEED_DOMAIN + b":review",
) -> DevelopmentReviewSelection:
    values = sorted(candidates, key=lambda value: value.stable_source_row_id_v1)
    if len(values) < target_count:
        raise ValueError("review population is smaller than requested sample")
    if len({value.stable_source_row_id_v1 for value in values}) != len(values):
        raise ValueError("review population contains duplicate identities")
    if not 0 < broad_count <= target_count or not 0 <= double_review_count <= target_count:
        raise ValueError("invalid review sample counts")

    broad_dimensions = (
        "primary_country_cohort",
        "structured_completeness",
        "script_category",
    )
    broad_groups: dict[tuple[str, str], list[ReviewCandidate]] = {}
    for value in values:
        for dimension in broad_dimensions:
            category = value.strata.get(dimension)
            if category:
                broad_groups.setdefault((dimension, category), []).append(value)
    broad: set[bytes] = set()
    for group_key, group in sorted(broad_groups.items()):
        ranked = sorted(
            group,
            key=lambda value: (
                _score(
                    seed_domain + b":broad:" + "=".join(group_key).encode(),
                    value.stable_source_row_id_v1,
                ),
                value.stable_source_row_id_v1,
            ),
        )
        if ranked and len(broad) < broad_count:
            broad.add(ranked[0].stable_source_row_id_v1)
    for value in sorted(
        values,
        key=lambda item: (
            _score(seed_domain + b":broad-fill", item.stable_source_row_id_v1),
            item.stable_source_row_id_v1,
        ),
    ):
        if len(broad) == broad_count:
            break
        broad.add(value.stable_source_row_id_v1)

    by_id = {value.stable_source_row_id_v1: value for value in values}
    targets = {(dimension, category): count for dimension, category, count in allocations}

    def matches(value: ReviewCandidate, key: tuple[str, str]) -> bool:
        dimension, category = key
        return value.strata.get(dimension) == category or value.strata.get(
            f"{dimension}:{category}"
        ) == "TRUE"

    selected = set(broad)
    diagnostics: list[str] = []
    effective_targets: dict[tuple[str, str], int] = {}
    for key, target in sorted(targets.items()):
        available = sum(matches(value, key) for value in values)
        effective_targets[key] = min(target, available)
        if available < target:
            diagnostics.append(
                f"TARGET_NOT_FULLY_AVAILABLE:{key[0]}={key[1]}:{available}/{target}"
            )
    while True:
        represented = {
            key: sum(matches(by_id[identity], key) for identity in selected)
            for key in targets
        }
        unmet = {
            key for key in targets if represented[key] < effective_targets[key]
        }
        if not unmet:
            break
        gain_ranked: list[tuple[int, bytes, bytes]] = []
        for value in values:
            identity = value.stable_source_row_id_v1
            if identity in selected:
                continue
            gain = sum(matches(value, key) for key in unmet)
            if gain:
                gain_ranked.append(
                    (-gain, _score(seed_domain + b":target", identity), identity)
                )
        if not gain_ranked:
            raise ValueError("review target selection made no progress")
        selected.add(min(gain_ranked)[2])
        if len(selected) > target_count:
            raise ValueError("review targets exceed requested sample")
    targeted = selected - broad
    for value in sorted(
        values,
        key=lambda item: (
            _score(seed_domain + b":fill", item.stable_source_row_id_v1),
            item.stable_source_row_id_v1,
        ),
    ):
        if len(selected) == target_count:
            break
        selected.add(value.stable_source_row_id_v1)
    if len(selected) != target_count:
        raise ValueError("review sampler cannot produce requested count")

    double: set[bytes] = set()
    if broad:
        double.add(
            min(broad, key=lambda item: (_score(seed_domain + b":double-broad", item), item))
        )
    targeted_matches = {
        identity
        for identity in selected
        if any(matches(by_id[identity], key) for key in targets)
    }
    if targeted_matches:
        double.add(
            min(
                targeted_matches,
                key=lambda item: (_score(seed_domain + b":double-target", item), item),
            )
        )
    for identity in sorted(
        selected, key=lambda item: (_score(seed_domain + b":double-fill", item), item)
    ):
        if len(double) == double_review_count:
            break
        double.add(identity)
    if len(double) != double_review_count:
        raise ValueError("double-review sampler cannot produce requested count")
    return DevelopmentReviewSelection(
        tuple(sorted(selected)),
        tuple(sorted(broad)),
        tuple(sorted(targeted)),
        tuple(sorted(double)),
        tuple(diagnostics),
    )


def select_development_review_sample(
    candidates: Iterable[ReviewCandidate],
    *,
    target_count: int,
    allocations: Sequence[tuple[str, str, int]],
    seed_domain: bytes = PILOT_SEED_DOMAIN + b":review",
) -> tuple[bytes, ...]:
    return select_development_review_sample_plan(
        candidates,
        target_count=target_count,
        broad_count=min(REVIEW_BROAD_COUNT, max(1, target_count // 2)),
        allocations=allocations,
        double_review_count=min(DOUBLE_REVIEW_COUNT, target_count),
        seed_domain=seed_domain,
    ).review_ids


def write_review_artifacts(
    directory: Path,
    *,
    protected_rows: list[dict[str, Any]],
    review_ids: Sequence[bytes],
    pilot_version: str,
    independent_double_review_ids: Sequence[bytes] = (),
) -> tuple[Path, Path]:
    expected_ids = set(review_ids)
    if len(expected_ids) != len(review_ids) or any(len(value) != 32 for value in review_ids):
        raise ValueError("review identities must be unique 32-byte values")
    observed_context_ids = {
        bytes(row["stable_source_row_id_v1"]) for row in protected_rows
    }
    if observed_context_ids != expected_ids or len(protected_rows) != len(expected_ids):
        raise ValueError("protected review context identity mismatch")
    double_ids = set(independent_double_review_ids)
    if not double_ids.issubset(expected_ids):
        raise ValueError("double-review identities are outside review sample")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    directory.chmod(0o700)
    context_path = directory / "protected_review_context.parquet"
    labels_path = directory / "portable_review_labels.parquet"
    temporary_context = directory / ".protected_review_context.parquet.tmp"
    temporary_labels = directory / ".portable_review_labels.parquet.tmp"
    context = pa.Table.from_pylist(protected_rows)
    pq.write_table(
        context,
        temporary_context,
        compression="zstd",
        write_statistics=False,
        write_page_checksum=True,
    )
    label_rows = []
    for identity in review_ids:
        label_rows.append(
            {
                "hashed_review_id": hashed_review_id(identity, pilot_version),
                "pilot_version": pilot_version,
                "sample_partition": "DEVELOPMENT",
                "reviewer_id": "",
                "review_round": 1,
                "is_independent_review": identity in double_ids,
                "street_label": None,
                "house_number_label": None,
                "unit_floor_building_label": None,
                "organization_address_role_label": None,
                "postcode_locality_region_country_label": None,
                "conflict_correctness_label": None,
                "parser_overreach_label": None,
                "missed_information_label": None,
                "unsafe_handling_label": None,
                "overall_parse_acceptability_label": None,
                "reason_codes": [],
                "reason_codes_version": MANUAL_REVIEW_REASON_CODES_VERSION,
                "adjudicated_label": None,
                "adjudicator_id": None,
                "label_schema_version": MANUAL_REVIEW_LABEL_SCHEMA_VERSION,
            }
        )
    pq.write_table(
        pa.Table.from_pylist(label_rows, schema=manual_review_schema()),
        temporary_labels,
        compression="zstd",
        write_statistics=False,
        write_page_checksum=True,
    )
    temporary_context.chmod(0o600)
    temporary_labels.chmod(0o600)
    verified_context = pq.ParquetFile(
        temporary_context, page_checksum_verification=True, pre_buffer=True
    )
    verified_labels = pq.ParquetFile(
        temporary_labels, page_checksum_verification=True, pre_buffer=True
    )
    if (
        verified_context.metadata.num_rows != len(expected_ids)
        or verified_labels.metadata.num_rows != len(expected_ids)
        or verified_labels.schema_arrow.remove_metadata()
        != manual_review_schema().remove_metadata()
    ):
        raise ValueError("review artifact read-back validation failed")
    os.replace(temporary_context, context_path)
    os.replace(temporary_labels, labels_path)
    context_path.chmod(0o600)
    labels_path.chmod(0o600)
    _fsync_parent(context_path)
    return context_path, labels_path


def population_country_counts(
    rows: Iterable[Mapping[str, Any]], country_reference: CountryReference
) -> Counter[str]:
    return Counter(
        country_sampling_group_v1(str(row["country_iso_code"]), country_reference)[0]
        for row in rows
    )

"""Country-provenance and parser-eligibility rules for Stage 7 diagnostics.

This module is deliberately independent of address text.  It classifies only
the accepted Stage 4 country provenance attached to Stage 6 occurrences and a
versioned public parser-support manifest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, NoReturn, cast


ELIGIBILITY_MANIFEST_VERSION = "stage07_parser_country_eligibility_v1"
ELIGIBILITY_MANIFEST_RELATIVE_PATH = Path(
    "docs/scientific_assets/stage07_parser_country_eligibility_v1.json"
)
TRUSTED_COUNTRY_FIELD = "stage04_lower_country_iso_code"

LIBPOSTAL = "LIBPOSTAL"
DEEPPARSE = "DEEPPARSE"
PARSER_NAMES = (LIBPOSTAL, DEEPPARSE)

CountryProvenanceStatus = Literal[
    "COUNTRY_UNANIMOUS_VALID",
    "COUNTRY_MISSING",
    "COUNTRY_PARTIAL",
    "COUNTRY_INVALID",
    "COUNTRY_CONFLICTING",
]
ParserName = Literal["LIBPOSTAL", "DEEPPARSE"]
ParserEligibilityStatus = Literal[
    "PARSER_ELIGIBLE_COUNTRY",
    "PARSER_NOT_APPLICABLE_COUNTRY",
    "PARSER_ELIGIBILITY_MISSING_COUNTRY",
    "PARSER_ELIGIBILITY_PARTIAL_COUNTRY",
    "PARSER_ELIGIBILITY_INVALID_COUNTRY",
    "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY",
]

COUNTRY_UNANIMOUS_VALID: CountryProvenanceStatus = "COUNTRY_UNANIMOUS_VALID"
COUNTRY_MISSING: CountryProvenanceStatus = "COUNTRY_MISSING"
COUNTRY_PARTIAL: CountryProvenanceStatus = "COUNTRY_PARTIAL"
COUNTRY_INVALID: CountryProvenanceStatus = "COUNTRY_INVALID"
COUNTRY_CONFLICTING: CountryProvenanceStatus = "COUNTRY_CONFLICTING"
COUNTRY_PROVENANCE_STATUSES = (
    COUNTRY_UNANIMOUS_VALID,
    COUNTRY_MISSING,
    COUNTRY_PARTIAL,
    COUNTRY_INVALID,
    COUNTRY_CONFLICTING,
)

PARSER_ELIGIBLE_COUNTRY: ParserEligibilityStatus = "PARSER_ELIGIBLE_COUNTRY"
PARSER_NOT_APPLICABLE_COUNTRY: ParserEligibilityStatus = "PARSER_NOT_APPLICABLE_COUNTRY"
PARSER_ELIGIBILITY_MISSING_COUNTRY: ParserEligibilityStatus = (
    "PARSER_ELIGIBILITY_MISSING_COUNTRY"
)
PARSER_ELIGIBILITY_PARTIAL_COUNTRY: ParserEligibilityStatus = (
    "PARSER_ELIGIBILITY_PARTIAL_COUNTRY"
)
PARSER_ELIGIBILITY_INVALID_COUNTRY: ParserEligibilityStatus = (
    "PARSER_ELIGIBILITY_INVALID_COUNTRY"
)
PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY: ParserEligibilityStatus = (
    "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY"
)
PARSER_ELIGIBILITY_STATUSES = (
    PARSER_ELIGIBLE_COUNTRY,
    PARSER_NOT_APPLICABLE_COUNTRY,
    PARSER_ELIGIBILITY_MISSING_COUNTRY,
    PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
    PARSER_ELIGIBILITY_INVALID_COUNTRY,
    PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
)

ELIGIBLE_BOTH = "ELIGIBLE_BOTH"
ELIGIBLE_LIBPOSTAL_ONLY = "ELIGIBLE_LIBPOSTAL_ONLY"
ELIGIBLE_DEEPPARSE_ONLY = "ELIGIBLE_DEEPPARSE_ONLY"
ELIGIBLE_NEITHER = "ELIGIBLE_NEITHER"
COUNTRY_CONTEXT_UNRESOLVED = "COUNTRY_CONTEXT_UNRESOLVED"
JOINT_ELIGIBILITY_STATUSES = (
    ELIGIBLE_BOTH,
    ELIGIBLE_LIBPOSTAL_ONLY,
    ELIGIBLE_DEEPPARSE_ONLY,
    ELIGIBLE_NEITHER,
    COUNTRY_CONTEXT_UNRESOLVED,
)


class Stage07CountryEligibilityError(RuntimeError):
    """Fail-closed public eligibility or country-provenance error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _fail(code: str, detail: str) -> NoReturn:
    raise Stage07CountryEligibilityError(code, detail)


@dataclass(frozen=True, slots=True)
class CountryProvenance:
    status: CountryProvenanceStatus
    country_code: str | None
    occurrence_count: int
    valid_occurrence_count: int
    missing_occurrence_count: int
    invalid_occurrence_count: int
    distinct_valid_country_count: int


@dataclass(frozen=True, slots=True)
class EligibilityManifest:
    path: Path
    sha256: str
    raw: Mapping[str, Any]
    valid_iso_alpha2_codes: frozenset[str]
    deepparse_trained_country_codes: frozenset[str]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise Stage07CountryEligibilityError(
            "ELIGIBILITY_MANIFEST_READ_FAILURE",
            "The public eligibility manifest could not be read",
        ) from error
    return digest.hexdigest()


def _require_exact_string_set(value: object, expected: tuple[str, ...]) -> None:
    if not isinstance(value, list) or tuple(value) != expected:
        _fail("ELIGIBILITY_MANIFEST_INVALID", "A status vocabulary differs")


def load_eligibility_manifest(path: Path) -> EligibilityManifest:
    """Load and structurally verify the public versioned eligibility manifest."""
    if path.is_symlink() or not path.is_file():
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Manifest is absent or a symlink")
    try:
        raw_object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Stage07CountryEligibilityError(
            "ELIGIBILITY_MANIFEST_INVALID", "Manifest JSON is unreadable"
        ) from error
    if not isinstance(raw_object, dict):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Manifest is not an object")
    raw = cast(dict[str, Any], raw_object)
    _require_exact_string_set(
        raw.get("country_provenance_statuses"), COUNTRY_PROVENANCE_STATUSES
    )
    _require_exact_string_set(
        raw.get("parser_eligibility_statuses"), PARSER_ELIGIBILITY_STATUSES
    )
    if (
        raw.get("version") != ELIGIBILITY_MANIFEST_VERSION
        or raw.get("trusted_country_field") != TRUSTED_COUNTRY_FIELD
        or not isinstance(raw.get("iso_3166_1_reference"), dict)
        or not isinstance(raw.get("parsers"), dict)
    ):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Manifest framing differs")

    iso = cast(dict[str, Any], raw["iso_3166_1_reference"])
    csv_codes = iso.get("alpha2_codes_csv")
    if not isinstance(csv_codes, str):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "ISO code material is absent")
    ordered_codes = csv_codes.split(",")
    valid_codes = frozenset(ordered_codes)
    if (
        ordered_codes != sorted(ordered_codes)
        or len(ordered_codes) != 249
        or len(valid_codes) != 249
        or iso.get("alpha2_code_count") != 249
        or any(
            len(code) != 2 or not code.isascii() or not code.islower()
            for code in valid_codes
        )
    ):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "ISO code set differs")

    parsers = cast(dict[str, Any], raw["parsers"])
    if set(parsers) != set(PARSER_NAMES):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Parser set differs")
    libpostal = parsers[LIBPOSTAL]
    deepparse = parsers[DEEPPARSE]
    if not isinstance(libpostal, dict) or not isinstance(deepparse, dict):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Parser evidence is malformed")
    if (
        libpostal.get("support_definition")
        != "DOCUMENTED_EVERY_INHABITED_COUNTRY_WORLDWIDE"
        or libpostal.get("enumerable_model_country_manifest_present") is not False
        or deepparse.get("support_definition") != "TRAINED_COUNTRY_ONLY"
        or deepparse.get("zero_shot_countries_eligible") is not False
        or not isinstance(deepparse.get("trained_countries"), list)
    ):
        _fail("ELIGIBILITY_MANIFEST_INVALID", "Parser support semantics differ")
    trained_rows = cast(list[Any], deepparse["trained_countries"])
    trained_codes: list[str] = []
    for row in trained_rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"documented_name", "iso_alpha2"}
            or not isinstance(row["documented_name"], str)
            or not isinstance(row["iso_alpha2"], str)
            or row["iso_alpha2"] not in valid_codes
        ):
            _fail("ELIGIBILITY_MANIFEST_INVALID", "A trained-country row differs")
        trained_codes.append(row["iso_alpha2"])
    if len(trained_codes) != 20 or len(set(trained_codes)) != 20:
        _fail("ELIGIBILITY_MANIFEST_INVALID", "DeepParse trained set differs")
    return EligibilityManifest(
        path=path,
        sha256=_sha256_file(path),
        raw=raw,
        valid_iso_alpha2_codes=valid_codes,
        deepparse_trained_country_codes=frozenset(trained_codes),
    )


def classify_country_provenance(
    country_values: Iterable[str | None], *, valid_codes: frozenset[str]
) -> CountryProvenance:
    """Classify all occurrence countries for one exact Stage 6 candidate."""
    values = tuple(country_values)
    if not values:
        _fail("COUNTRY_PROVENANCE_EMPTY", "A candidate has no occurrences")
    missing = sum(value is None or value == "" for value in values)
    valid_values = [value for value in values if value in valid_codes]
    invalid = len(values) - missing - len(valid_values)
    distinct = frozenset(valid_values)
    if len(distinct) >= 2:
        status: CountryProvenanceStatus = COUNTRY_CONFLICTING
        country_code = None
    elif len(distinct) == 1 and (missing or invalid):
        status = COUNTRY_PARTIAL
        country_code = None
    elif len(distinct) == 1:
        status = COUNTRY_UNANIMOUS_VALID
        country_code = next(iter(distinct))
    elif invalid:
        status = COUNTRY_INVALID
        country_code = None
    else:
        status = COUNTRY_MISSING
        country_code = None
    return CountryProvenance(
        status=status,
        country_code=country_code,
        occurrence_count=len(values),
        valid_occurrence_count=len(valid_values),
        missing_occurrence_count=missing,
        invalid_occurrence_count=invalid,
        distinct_valid_country_count=len(distinct),
    )


def parser_eligibility(
    parser: ParserName,
    provenance: CountryProvenance,
    *,
    deepparse_trained_country_codes: frozenset[str],
) -> ParserEligibilityStatus:
    """Classify one parser call without inspecting candidate text."""
    unresolved: dict[str, ParserEligibilityStatus] = {
        COUNTRY_MISSING: PARSER_ELIGIBILITY_MISSING_COUNTRY,
        COUNTRY_PARTIAL: PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
        COUNTRY_INVALID: PARSER_ELIGIBILITY_INVALID_COUNTRY,
        COUNTRY_CONFLICTING: PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
    }
    if provenance.status in unresolved:
        return unresolved[provenance.status]
    if provenance.status != COUNTRY_UNANIMOUS_VALID or provenance.country_code is None:
        _fail("COUNTRY_PROVENANCE_INVALID", "Country status/code invariant differs")
    if parser == LIBPOSTAL:
        return PARSER_ELIGIBLE_COUNTRY
    if parser == DEEPPARSE:
        if provenance.country_code in deepparse_trained_country_codes:
            return PARSER_ELIGIBLE_COUNTRY
        return PARSER_NOT_APPLICABLE_COUNTRY
    _fail("PARSER_IDENTITY_INVALID", "Unknown parser")


def joint_eligibility(libpostal_status: str, deepparse_status: str) -> str:
    """Create the aggregate overlap category used by eligibility reports."""
    unresolved = frozenset(
        {
            PARSER_ELIGIBILITY_MISSING_COUNTRY,
            PARSER_ELIGIBILITY_PARTIAL_COUNTRY,
            PARSER_ELIGIBILITY_INVALID_COUNTRY,
            PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY,
        }
    )
    if libpostal_status in unresolved or deepparse_status in unresolved:
        return COUNTRY_CONTEXT_UNRESOLVED
    libpostal_eligible = libpostal_status == PARSER_ELIGIBLE_COUNTRY
    deepparse_eligible = deepparse_status == PARSER_ELIGIBLE_COUNTRY
    if libpostal_eligible and deepparse_eligible:
        return ELIGIBLE_BOTH
    if libpostal_eligible:
        return ELIGIBLE_LIBPOSTAL_ONLY
    if deepparse_eligible:
        return ELIGIBLE_DEEPPARSE_ONLY
    return ELIGIBLE_NEITHER


__all__ = [
    "COUNTRY_CONFLICTING",
    "COUNTRY_CONTEXT_UNRESOLVED",
    "COUNTRY_INVALID",
    "COUNTRY_MISSING",
    "COUNTRY_PARTIAL",
    "COUNTRY_PROVENANCE_STATUSES",
    "COUNTRY_UNANIMOUS_VALID",
    "DEEPPARSE",
    "ELIGIBILITY_MANIFEST_RELATIVE_PATH",
    "ELIGIBILITY_MANIFEST_VERSION",
    "ELIGIBLE_BOTH",
    "ELIGIBLE_DEEPPARSE_ONLY",
    "ELIGIBLE_LIBPOSTAL_ONLY",
    "ELIGIBLE_NEITHER",
    "EligibilityManifest",
    "JOINT_ELIGIBILITY_STATUSES",
    "LIBPOSTAL",
    "PARSER_ELIGIBILITY_AMBIGUOUS_COUNTRY",
    "PARSER_ELIGIBILITY_INVALID_COUNTRY",
    "PARSER_ELIGIBILITY_MISSING_COUNTRY",
    "PARSER_ELIGIBILITY_PARTIAL_COUNTRY",
    "PARSER_ELIGIBILITY_STATUSES",
    "PARSER_ELIGIBLE_COUNTRY",
    "PARSER_NAMES",
    "PARSER_NOT_APPLICABLE_COUNTRY",
    "Stage07CountryEligibilityError",
    "TRUSTED_COUNTRY_FIELD",
    "classify_country_provenance",
    "joint_eligibility",
    "load_eligibility_manifest",
    "parser_eligibility",
]

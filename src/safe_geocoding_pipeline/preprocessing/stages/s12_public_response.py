"""Explicit public operational shapes; no scientific validator activation.

The exact Berlin warning is an observed coverage limitation. No deployment,
source vocabulary, immutable generation or continuous-state identity is proved.
"""

from __future__ import annotations
from . import s12_probe as probe
from . import s12_response as response
from . import s12_retrieval_contract as c
from . import s12_storage as io
from . import s12_public_corpus_policy as corpus

# Public constants do not activate/import the inactive scientific successor.
BASE_SCIENTIFIC_SHA256 = (
    "3acfb6cb6888a6b16903f0b132b071f6bac82277263b9d17fd368bbe9449994e"
)
WARNING = "performance optimization: excluding 'address' layer"
SIZE1_TARGET = b"/v1/search?boundary.country=DE&size=1&text=Berlin"

VERSION = "stage12_public_observation_validation_v1"
FAMILY_VERSION = "stage12_public_observation_validation_v2"
CORPUS_VERSION = "stage12_public_observation_validation_v3"
FAMILY_SIZES = (1, 3, 5, 10, 20, 40)
SCOPE = "PUBLIC_SHAPES_WITH_EXACT_BERLIN_LIMITATION_SCIENTIFIC_IDENTITY_UNVERIFIED"
CORPUS_SCOPE = (
    "PUBLIC_SHAPES_WITH_EXACT_CORPUS_LIMITATION_SCIENTIFIC_IDENTITY_UNVERIFIED"
)
VERSIONS = (VERSION, FAMILY_VERSION, CORPUS_VERSION)


def descriptor(version=VERSION):
    io._checkpoint()
    c.require(version in VERSIONS, "RESPONSE_CONTRACT_INVALID")
    value = {
        "version": VERSION,
        "scope": SCOPE,
        "base_scientific_validation_sha256": BASE_SCIENTIFIC_SHA256,
        "scientific_validator_activation": False,
        "scientific_identity_verified": False,
        "ordinary_checks": "UNCHANGED_PUBLIC_SHAPES_PLUS_REQUEST_SIZE_BOUND",
        "exception_target_ascii": SIZE1_TARGET.decode("ascii"),
        "exception_warning": WARNING,
        "exception_location": "geocoding.warnings_SINGLETON_ONLY",
        "echo": {"text": "Berlin", "size": 1, "boundary.country": ["DEU"]},
        "echo_basis": "HISTORICAL_PUBLIC_OBSERVATION_NOT_VERIFIED_DEPLOYMENT_DEFAULT",
        "layers": "OBSERVED_NONEMPTY_UNIQUE_QUERY_LAYERS_EXCLUDING_ADDRESS;RETURNED_LAYERS_MUST_BELONG",
        "unknowns": [
            "DEPLOYMENT_CONTENT",
            "SOURCE_VOCABULARY",
            "OMITTED_DEFAULTS",
            "CONTINUOUS_STATE",
            "IDENTICAL_FUTURE_RESULTS",
        ],
        "raw_handling": "UNCHANGED_BYTES_NO_REMOVAL_OR_RESERIALIZATION",
        "limitation": "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED",
        "top_warnings_all_errors_other_warnings": "ABSENT_OR_EMPTY_ARRAY_ONLY",
        "accepted_scope": "PUBLIC_OBSERVATIONS_ONLY_NO_SCIENTIFIC_RELATIONS",
    }

    if version == FAMILY_VERSION:
        value.update(
            version=FAMILY_VERSION,
            exception_target_ascii=[
                f"/v1/search?boundary.country=DE&size={size}&text=Berlin"
                for size in FAMILY_SIZES
            ],
            echo={
                "text": "Berlin",
                "size": "EXACT_REQUEST_INTEGER_TOKEN",
                "boundary.country": ["DEU"],
            },
            echo_basis="PROSPECTIVE_OWNER_PUBLIC_POLICY_NOT_OBSERVED_RECURRENCE",
        )
    if version == CORPUS_VERSION:
        check_corpus()
        targets = corpus.allowlist()
        del value["exception_target_ascii"]
        value.update(
            version=CORPUS_VERSION,
            scope=CORPUS_SCOPE,
            approved_matrix_manifest_sha256=corpus.MANIFEST_SHA256,
            fixture_inventory_sha256=corpus.FIXTURE_SHA256,
            request_allowlist=targets,
            request_allowlist_sha256=c.sha(c.canonical(targets)).hex(),
            request_allowlist_count=len(targets),
            request_eligibility="EXACT_GET_FULL_TEXT_DATA_FIXTURE_AND_PLANNED_TARGET_ONLY",
            echo={
                "text": "EXACT_BOUND_REQUEST_TEXT_NO_NORMALIZATION",
                "size": "EXACT_REQUEST_INTEGER_TOKEN",
                "boundary.country": "EXACT_BOUND_ALPHA3_SINGLETON_NO_DEFAULT",
            },
            echo_basis="PROSPECTIVE_OWNER_CORPUS_POLICY_NOT_OBSERVED_RECURRENCE",
            limitation_receipt_version="stage12_public_limitation_receipt_v2",
            protected_and_controls="INELIGIBLE_UNCHANGED_STRICT_VALIDATION",
        )
    io._checkpoint()
    return value


def check_corpus():
    """The fixed table cannot silently follow a later fixture/corpus edit."""
    io._checkpoint()
    c.require(
        c.sha(c.canonical(probe.fixtures())).hex() == corpus.FIXTURE_SHA256,
        "RESPONSE_CONTRACT_INVALID",
    )
    io._checkpoint()


def corpus_entry(work):
    if work.get("kind") != "DATA":
        return None
    entry = corpus.entry(work.get("fixture_id"), work.get("result_limit"))
    if entry is None:
        return None
    check_corpus()
    c.require(
        target(work) == entry["target_ascii"].encode("ascii"),
        "RESPONSE_CONTRACT_INVALID",
    )
    return entry


def eligible(work, version):
    c.require(version in VERSIONS, "RESPONSE_CONTRACT_INVALID")
    if version == CORPUS_VERSION:
        return corpus_entry(work) is not None
    size = work["result_limit"]
    sizes = (1,) if version == VERSION else FAMILY_SIZES
    return (
        type(size) is int
        and size in sizes
        and work["kind"] == "DATA"
        and target(work)
        == f"/v1/search?boundary.country=DE&size={size}&text=Berlin".encode("ascii")
    )


def target(work):
    io._checkpoint()
    fixture = next(
        (f for f in probe.fixtures() if f["fixture_id"] == work["fixture_id"]), None
    )
    c.require(
        fixture is not None and work["kind"] == "DATA", "RESPONSE_CONTRACT_INVALID"
    )
    value = c.materialize(
        fixture["core"],
        bytes.fromhex(work["fixture_id"]),
        c.policy(work["result_limit"]),
        target_limit=4096,
    )[0]
    io._checkpoint()
    return value


def messages(obj, *, berlin=False):
    for name in ("errors", "warnings"):
        if name not in obj:
            continue
        value = obj[name]
        c.require(type(value) is list, "RESPONSE_CONTRACT_INVALID")
        c.require(
            value == [] or (berlin and name == "warnings" and value == [WARNING]),
            "RESPONSE_CONTRACT_INVALID",
        )


def shapes(raw, work, *, version=VERSION):
    return _shapes(raw, work, version=version, ordinary=False)


def ordinary_shapes(raw, size):
    """Strict public control shapes: no request can acquire a warning exception."""
    c.require(type(size) is int and 0 < size <= 40, "RESPONSE_CONTRACT_INVALID")
    return _shapes(raw, {"result_limit": size}, version=VERSION, ordinary=True)


def _shapes(raw, work, *, version, ordinary):
    c.require(version in VERSIONS, "RESPONSE_CONTRACT_INVALID")
    io._checkpoint()
    obj = response.Parser(raw).parse().value
    io._checkpoint()
    response.envelope(obj)
    c.require(
        obj.get("type") == "FeatureCollection" and type(obj.get("features")) is list,
        "RESPONSE_CONTRACT_INVALID",
    )
    features = obj["features"]
    c.require(len(features) <= work["result_limit"], "RESPONSE_CONTRACT_INVALID")
    allowed_layers = None
    if "geocoding" in obj:
        geo = obj["geocoding"]
        c.require(type(geo) is dict, "RESPONSE_CONTRACT_INVALID")
        response.envelope(geo, messages=False, bbox=False)
        allowed_warning = (
            not ordinary
            and eligible(work, version)
            and geo.get("warnings") == [WARNING]
        )
        messages(geo, berlin=allowed_warning)
        for key in ("version", "attribution"):
            if key in geo:
                c.require(type(geo[key]) is str, "RESPONSE_CONTRACT_INVALID")
        if "query" in geo:
            c.require(type(geo["query"]) is dict, "RESPONSE_CONTRACT_INVALID")
        if "timestamp" in geo:
            value = geo["timestamp"]
            c.require(
                type(value) is response.Number
                and response.NUMBER.fullmatch(value.token.encode()) is not None
                and all(ch not in value.token for ch in ".eE"),
                "RESPONSE_CONTRACT_INVALID",
            )
        if allowed_warning:
            query = geo.get("query")
            expected_text, expected_country = "Berlin", ["DEU"]
            if version == CORPUS_VERSION:
                entry = corpus_entry(work)
                expected_text = entry["text"]
                expected_country = entry["country_echo"]
            c.require(
                type(query) is dict
                and query.get("text") == expected_text
                and query.get("size") == response.Number(str(work["result_limit"]))
                and query.get("boundary.country") == expected_country,
                "RESPONSE_CONTRACT_INVALID",
            )
            layers = query.get("layers")
            c.require(
                type(layers) is list
                and layers
                and all(type(x) is str and x for x in layers)
                and len(set(layers)) == len(layers)
                and "address" not in layers,
                "RESPONSE_CONTRACT_INVALID",
            )
            c.require(
                type(query.get("lang")) is dict and bool(query["lang"]),
                "RESPONSE_CONTRACT_INVALID",
            )
            allowed_layers = set(layers)
    for feature in features:
        io._checkpoint()
        c.require(
            type(feature) is dict
            and feature.get("type") == "Feature"
            and type(feature.get("properties")) is dict
            and type(feature.get("geometry")) is dict,
            "RESPONSE_CONTRACT_INVALID",
        )
        response.envelope(feature, messages=False)
        geometry = feature["geometry"]
        c.require("crs" not in geometry, "RESPONSE_CONTRACT_INVALID")
        coord = geometry.get("coordinates")
        c.require(
            geometry.get("type") == "Point" and type(coord) is list and len(coord) == 2,
            "RESPONSE_CONTRACT_INVALID",
        )
        response.numeric(coord[0], -180, 180)
        response.numeric(coord[1], -90, 90)
        properties = feature["properties"]
        for name in ("source", "layer"):
            c.require(
                type(properties.get(name)) is str and properties[name],
                "RESPONSE_CONTRACT_INVALID",
            )
        if allowed_layers is not None:
            c.require(
                properties["layer"] in allowed_layers, "RESPONSE_CONTRACT_INVALID"
            )
        for name in response.STRINGS:
            response.optional_string(properties.get(name))
        response.optional_string(feature.get("id"))
        if properties.get("confidence") is not None:
            response.numeric(properties["confidence"], 0, 1)
    structures = []
    for feature in features:
        io._checkpoint()
        structures.append(response.structural(feature))
    io._checkpoint()
    return tuple(structures)


class Validation:
    VERSION, SCOPE = VERSION, SCOPE

    def __init__(self, version=VERSION):
        descriptor(version)  # Reject unknown versions before evidence use.
        self.VERSION = version
        self.SCOPE = CORPUS_SCOPE if version == CORPUS_VERSION else SCOPE

    def descriptor(self):
        return descriptor(self.VERSION)

    def limitation(self, raw, work):
        observed = False
        layers = None
        valid = False
        if raw is not None:
            try:
                io._checkpoint()
                obj = response.Parser(raw).parse().value
                io._checkpoint()
                observed = type(obj.get("geocoding")) is dict and obj["geocoding"].get(
                    "warnings"
                ) == [WARNING]
                shapes(raw, work, version=self.VERSION)
                valid = True
                if observed:
                    layers = obj["geocoding"]["query"]["layers"]
            except (c.Stage12Error, KeyError, TypeError, AttributeError):
                pass
        applied = bool(valid and observed and eligible(work, self.VERSION))
        value = {
            "version": "stage12_public_limitation_receipt_v1",
            "validation_sha256": c.sha(c.canonical(self.descriptor())).hex(),
            "work_sha256": c.sha(c.canonical(work)).hex(),
            "raw_sha256": c.sha(raw).hex() if raw is not None else None,
            "exception_applied": applied,
            "warning": WARNING if applied else None,
            "observed_effective_layers": layers if applied else None,
            "coverage_limitation": "ADDRESS_LAYER_EXCLUDED_COVERAGE_MAY_BE_REDUCED"
            if applied
            else None,
            "scientific_identity_verified": False,
            "continuous_service_state": "NOT_VERIFIED",
            "scientific_publication_authorized": False,
            "harmlessness_established": False,
            "live_determinism_established": False,
        }
        if self.VERSION == CORPUS_VERSION:
            entry = corpus_entry(work)
            value.update(
                version="stage12_public_limitation_receipt_v2",
                approved_matrix_manifest_sha256=corpus.MANIFEST_SHA256,
                fixture_inventory_sha256=corpus.FIXTURE_SHA256,
                request_allowlist_sha256=c.sha(c.canonical(corpus.allowlist())).hex(),
                eligible_request_target_sha256=entry["target_sha256"]
                if entry is not None
                else None,
            )
        return value

    def verify_limitation(self, root, work, record):
        value = io.metadata(io.read(root / "public_limitation.json"))
        base = self.limitation(None, work)
        c.require(
            set(value) == set(base)
            and value["work_sha256"] == base["work_sha256"]
            and value["validation_sha256"] == base["validation_sha256"],
            "S12_CAPTURE_BINDING_INVALID",
        )
        if self.VERSION == CORPUS_VERSION:
            for key in (
                "version",
                "approved_matrix_manifest_sha256",
                "fixture_inventory_sha256",
                "request_allowlist_sha256",
                "eligible_request_target_sha256",
            ):
                c.require(value[key] == base[key], "S12_CAPTURE_BINDING_INVALID")
        for k in (
            "scientific_identity_verified",
            "scientific_publication_authorized",
            "harmlessness_established",
            "live_determinism_established",
        ):
            c.require(value[k] is False, "S12_CAPTURE_BINDING_INVALID")
        c.require(
            value["continuous_service_state"] == "NOT_VERIFIED",
            "S12_CAPTURE_BINDING_INVALID",
        )
        if value["raw_sha256"] is None:
            c.require(value == base, "S12_CAPTURE_BINDING_INVALID")

    def validator(self, work, root):
        def validate(raw):
            c.require(
                io.read(root / "public_limitation.json")
                == c.canonical(self.limitation(raw, work)),
                "S12_CAPTURE_BINDING_INVALID",
            )
            return shapes(raw, work, version=self.VERSION)

        return validate

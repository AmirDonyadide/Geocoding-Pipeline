"""Public/invented workload planning only; never reads Stage 11 artifact payloads.

The frozen 64-case workload is fixed. Deeper sizes require controlled evidence.
Planning this workload does not authorize submission or establish deployment
identity. Scientific DEVELOPMENT policies C, T and N remain unselected.
"""

from __future__ import annotations

from typing import Any

from . import s11_semantic_contract as s11
from . import s12_retrieval_contract as c

PLACES = (
    ("DE", "Berlin"),
    ("FR", "Paris"),
    ("JP", "東京"),
    ("GR", "Αθήνα"),
    ("EG", "القاهرة"),
    ("IN", "मुंबई"),
    ("KR", "서울"),
    ("BR", "São Paulo"),
)


def fixtures() -> list[dict[str, Any]]:
    """Public city names plus manually invented strings; no source-data origin."""
    cases = []
    for mode in ("FULL_TEXT", "STRUCTURED"):
        for ordinal in range(32):
            country, locality = PLACES[ordinal % len(PLACES)]
            invented = f"Invented ZQX Stage12 passage {ordinal:02d} + 7%\n{locality}"
            text = locality if ordinal < 8 else invented
            core = {
                **s11.CONSTANTS,
                "endpoint": "/v1/search"
                if mode == "FULL_TEXT"
                else "/v1/search/structured",
                "search_mode": mode,
                "text": text if mode == "FULL_TEXT" else None,
                "address": invented if mode == "STRUCTURED" else None,
                "postalcode": None,
                "locality": locality if mode == "STRUCTURED" else None,
                "boundary_country": country,
            }
            semantic = s11.semantic_id(s11.core_bytes(core))
            cases.append(
                {
                    "fixture_id": semantic.hex(),
                    "provenance": "MANUALLY_AUTHORED_INVENTED_STRINGS_AND_PUBLIC_CITY_NAMES_NO_SOURCE_DATA",
                    "core": core,
                    "deep_case": ordinal < 8,
                    "zero_intended_not_guaranteed": ordinal >= 8,
                }
            )
    return sorted(cases, key=lambda row: row["fixture_id"])


def workload(
    deeper_sizes: list[int],
    *,
    operator_max_size: int,
    operator_size_evidence_sha256: bytes | None,
    workload_authorization_sha256: bytes,
) -> dict[str, Any]:
    if deeper_sizes:
        c.digest(operator_size_evidence_sha256)
    else:
        c.require(
            operator_size_evidence_sha256 is None, "PUBLIC_PROBE_DEEP_LADDER_INVALID"
        )
    c.digest(workload_authorization_sha256)
    c.require(
        type(operator_max_size) is int and operator_max_size >= 10,
        "PUBLIC_PROBE_SAFE_DEEP_SIZE_UNDOCUMENTED",
    )
    c.require(
        type(deeper_sizes) is list
        and 0 <= len(deeper_sizes) <= 2
        and all(type(v) is int and 10 < v <= operator_max_size for v in deeper_sizes),
        "PUBLIC_PROBE_DEEP_LADDER_INVALID",
    )
    c.require(
        deeper_sizes == sorted(set(deeper_sizes)), "PUBLIC_PROBE_DEEP_LADDER_INVALID"
    )
    cases = fixtures()
    main = [1, 3, 5, 10]
    calls = 64 * len(main) * 2 + 16 * len(deeper_sizes) * 2
    return {
        "protocol_version": "stage12_calibration_protocol_v1",
        "scope": "PUBLIC_SYNTHETIC_ONLY",
        "fixture_sha256": c.sha(c.canonical(cases)).hex(),
        "operator_size_evidence_sha256": operator_size_evidence_sha256.hex()
        if operator_size_evidence_sha256
        else None,
        "above10_capability": "OPERATOR_BOUND_DOCUMENTED_PENDING_PROBE"
        if deeper_sizes
        else "ABOVE10_SAFE_SIZE_NOT_YET_OPERATOR_VERIFIED",
        "workload_authorization_sha256": workload_authorization_sha256.hex(),
        "base_sizes": main,
        "deeper_sizes": deeper_sizes,
        "operator_max_size": operator_max_size,
        "repetitions": 2,
        "ordinary_calls": calls,
        "maximum_attempts": calls * 5,
        "additional_control_calls": 0,
        "requests_per_second": 1,
        "connection_bound": 2,
        "protected_network_requests": 0,
        "C": "UNSELECTED",
        "T": "UNSELECTED",
        "N": "UNSELECTED",
    }


def planned_calls(plan: dict[str, Any]) -> list[tuple[int, int, dict[str, Any]]]:
    c.require(plan["scope"] == "PUBLIC_SYNTHETIC_ONLY", "PUBLIC_PROBE_SCOPE_INVALID")
    cases = fixtures()
    c.require(
        c.sha(c.canonical(cases)).hex() == plan["fixture_sha256"],
        "PUBLIC_PROBE_FIXTURE_MISMATCH",
    )
    result = []
    for size in plan["base_sizes"] + plan["deeper_sizes"]:
        for repetition in range(2):
            for case in cases:
                if size <= 10 or case["deep_case"]:
                    result.append((size, repetition, case))
    c.require(
        len(result) == plan["ordinary_calls"] <= 576, "PUBLIC_PROBE_BUDGET_INVALID"
    )
    return result

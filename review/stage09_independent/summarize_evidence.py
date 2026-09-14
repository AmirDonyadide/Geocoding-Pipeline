"""Summarize the exact completed aggregate receipt; no row-level input access.

Usage: python summarize_evidence.py /private/path/1772139_complete.json
Outputs global aggregates and the twelve largest country Q04 conflict totals.
The full country/scope/rule cross-tab remains in the controlled job receipt.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

RECEIPT_SHA256 = "9ce865fbaf7c6b7acf769a9e9c5c7e76a112eb3dd8bf4b6630867fca0f736a4b"


def main():
    payload = Path(sys.argv[1]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == RECEIPT_SHA256
    receipt = json.loads(payload)
    assert receipt["review_job_id"] == "1772139"
    assert receipt["review_sha"] == "89cc9f9667cacac7ff26e70e14ee651af27b2e36"
    assert receipt["executable"] == "3e10ac7c1309c2636f35c0709fa283305d60d998"
    assert len(receipt["checks"]) == 100
    assert all(receipt["checks"].values()) and receipt["failed_checks"] == []
    assert receipt["phases"][-1]["phase"] == "complete"
    diagnostics = receipt["diagnostics"]
    rows = diagnostics["q04_rule_representation"]

    def state_counts(group):
        states = Counter()
        for row in group:
            states[row["state"]] += row["n"]
        evaluable = states["SUPPORTED"] + states["CONTRADICTED"]
        return {
            "supported": states["SUPPORTED"],
            "contradicted": states["CONTRADICTED"],
            "not_evaluable": states["NOT_EVALUABLE"],
            "evaluable": evaluable,
            "conflict_percent": round(100 * states["CONTRADICTED"] / evaluable, 6)
            if evaluable else None,
        }

    def grouped(field):
        values = sorted({row[field] for row in rows})
        return {value: state_counts([r for r in rows if r[field] == value])
                for value in values}

    countries = grouped("country")
    top_countries = sorted(countries, key=lambda key: (-countries[key]["contradicted"], key))[:12]
    shapes, counterfactuals = Counter(), Counter()
    for row in diagnostics["q04_conflict_shapes"]:
        shapes[row["shape"]] += row["n"]
    for row in diagnostics["q04_counterfactual_diagnostics"]:
        counterfactuals[row["diagnostic"]] += row["n"]
    counterfactuals.setdefault("trim_whitespace", 0)
    concentration = defaultdict(Counter)
    for row in diagnostics["q04_candidate_concentration"]:
        for field in ("evaluable_checks", "candidates", "conflicts", "conflict_candidates", "unique_candidate_values"):
            concentration[row["evidence_scope"]][field] += row[field]
    for scope in concentration:
        selected = [r for r in diagnostics["q04_largest_candidate_bins"] if r["evidence_scope"] == scope]
        for field in ("max_checks_per_candidate", "max_conflicts_per_candidate"):
            concentration[scope][field] = max(r[field] for r in selected)
    q08 = Counter()
    for row in diagnostics["q08"]:
        q08[row["result_state"]] += row["n"]
    summary = {
        "source_receipt_sha256": RECEIPT_SHA256,
        "review_job_id": receipt["review_job_id"],
        "review_sha": receipt["review_sha"],
        "executable": receipt["executable"],
        "checks_passed": len(receipt["checks"]),
        "failed_checks": receipt["failed_checks"],
        "phases": receipt["phases"],
        "candidate_integrity_validator": diagnostics["candidate_integrity_validator"],
        "states": diagnostics["states"],
        "family_states": diagnostics["family_states"],
        "candidate_evaluable": diagnostics["candidate_evaluable"],
        "gn_association_mismatches": diagnostics["gn_association_mismatches"],
        "source_full_iso_witnesses": diagnostics["source_full_iso_witnesses"],
        "q04": {
            "capability": "POSTCODE_PATTERN", "family": "LIBADDRESSINPUT_METADATA",
            "totals": state_counts(rows), "by_scope": grouped("scope"),
            "by_representation": grouped("representation"),
            "by_normalization": grouped("normalization"),
            "largest_country_rules": [{"country": country, "rule_locator": country + "/zip", **countries[country]}
                                      for country in top_countries],
            "conflict_shapes_global": dict(sorted(shapes.items())),
            "counterfactual_diagnostics_global": dict(sorted(counterfactuals.items())),
            "concentration_by_scope": {scope: dict(values) for scope, values in sorted(concentration.items())},
        },
        "q08_states": dict(sorted(q08.items())),
    }
    print(json.dumps(summary, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

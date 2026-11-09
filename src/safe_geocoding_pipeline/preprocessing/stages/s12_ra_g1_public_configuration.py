"""Closed native RA-G1 public matrix validation; no strict-family projection."""

from . import s12_ra_g1_contract as a
from . import s12_public_matrix as matrix
from . import s12_public_response as validation
from . import s12_probe as probe
from . import s12_ra_g1_execution as execution
from . import s12_transport as transport

FIELDS = set(
    "version scope task_id output_directory window_start window_end maximum_attempts active_seconds review_wait_seconds transport resources sources campaigns public_validation_sha256 capability resource_execution representative_validation_sha256".split()
)


def validate(config):
    a.require(
        type(config) is dict
        and set(config) == FIELDS
        and config["version"] == a.CONFIG
        and config["scope"] == a.SCOPE,
        "RA_G1_CONFIGURATION_FIELDS",
    )
    a.validate_type(config["task_id"], "N32")
    a.require(
        type(config["output_directory"]) is str
        and config["output_directory"].endswith("/or2_" + config["task_id"]),
        "RA_G1_PATH",
    )
    for key in ("window_start", "window_end"):
        a.validate_type(config[key], "Z")
    a.require(config["window_start"] < config["window_end"], "RA_G1_EXPIRED")
    a.require(
        type(config["maximum_attempts"]) is int
        and config["maximum_attempts"] == 2960
        and type(config["active_seconds"]) is int
        and config["active_seconds"] == 7200
        and type(config["review_wait_seconds"]) is int
        and 0 < config["review_wait_seconds"] <= 180,
        "RA_G1_LIMITS",
    )
    execution.validate_execution_request(config["resource_execution"])
    a.validate_type(config["representative_validation_sha256"], "D")
    a.require(
        config["public_validation_sha256"]
        == a.digest(validation.descriptor(validation.CORPUS_VERSION)),
        "RA_G1_PUBLIC_VALIDATOR",
    )
    source = config["sources"]
    a.require(
        type(source) is dict
        and set(source)
        == {
            "owner",
            "policy_freeze",
            "operator",
            "selection",
            "transport",
            "size_allowance",
        },
        "RA_G1_AUTHORITY_SCOPE",
    )
    for identity in source.values():
        a.validate_type(identity, "D")
    a.require(
        config["capability"] == matrix.binding(source["size_allowance"]),
        "RA_G1_CAPABILITY_BINDING",
    )
    t = config["transport"]
    a.require(
        type(t) is dict
        and set(t)
        == {
            "origin",
            "approved_ip",
            "configuration_evidence_sha256",
            "target_limit",
            "header_limit",
        },
        "RA_G1_TRANSPORT",
    )
    a.require(
        t["origin"] == "https://geocode.safe-frankfurt.de"
        and t["target_limit"] == 4096
        and t["header_limit"] == 16384,
        "RA_G1_TRANSPORT",
    )
    transport.TransportProfile(
        t["origin"],
        t["approved_ip"],
        bytes.fromhex(t["configuration_evidence_sha256"]),
        t["target_limit"],
        t["header_limit"],
    ).validate()
    r = config["resources"]
    a.validate_type(r, "Resources")
    a.require(
        r["application_admission_memory_bytes"] == a.MEMORY
        and r["requested_memory_bytes"] == 6 * 2**30
        and r["logical_pending_request_bytes"] == 2**20
        and r["logical_process_overhead_bytes"] == 2**30
        and r["per_attempt_logical_write_ceiling_bytes"] == 128 * 2**20
        and r["fixed_campaign_logical_write_ceiling_bytes"] == 128 * 2**20
        and r["task_logical_write_ceiling_bytes"] <= 512 * 2**30
        and r["writer_guard_ms"] == 5000,
        "RA_G1_LIMITS",
    )
    expected = matrix.fragments()
    campaigns = config["campaigns"]
    a.require(
        type(campaigns) is list and len(campaigns) == len(expected) == 11,
        "RA_G1_MATRIX_COVERAGE",
    )
    totals = {"attempts": 0, "events": 0, "storage_bytes": 0, "phase_duration_ms": 0}
    for index, (item, (label, _, group)) in enumerate(
        zip(campaigns, expected, strict=True)
    ):
        a.require(
            type(item) is dict
            and set(item) == {"label", "profile", "plan", "work", "ascending_sizes"}
            and item["label"] == label
            and item["ascending_sizes"] is False,
            "RA_G1_MATRIX_COVERAGE",
        )
        p, plan = item["profile"], item["plan"]
        a.validate_plan(plan, p)
        a.verify_work_manifest(lambda: iter(item["work"]), plan)
        a.require(
            p["resources"] == r
            and p["policy_freeze_record_sha256"] == source["policy_freeze"]
            and p["transport_profile_sha256"] == a.digest(t)
            and p["monitoring"]
            == {"mode": "PUBLIC_GAPS_ONLY", "gaps_record_sha256": source["selection"]},
            "RA_G1_CONFIGURATION_BINDING",
        )
        a.require(
            len(p["states"]) == 1
            and p["states"][0]["rate"] == {"num": 1, "den": 1}
            and p["states"][0]["connections"] == 2
            and p["states"][0]["admitted_operations"] == 2
            and p["states"][0]["evidence_sha256"] == source["selection"],
            "RA_G1_LIMITS",
        )
        a.require(
            p["operator_allowance"]["record_sha256"] == source["operator"],
            "RA_G1_CONFIGURATION_BINDING",
        )
        rows, recipes = matrix.work_for(index, a.digest(t))
        a.require(
            item["work"] == rows and plan["control_recipes"] == recipes,
            "RA_G1_MATRIX_COVERAGE",
        )
        a.require(
            plan["fixture_inventory_sha256"] == a.digest(probe.fixtures())
            and plan["capability_parent_sha256"] is None
            and plan["experiment_kind"] == "PERFORMANCE"
            and len(plan["blocks"]) == 1
            and plan["blocks"][0]["evaluation"] == "EXPLORATORY"
            and plan["blocks"][0]["criteria"] is None
            and plan["selection_basis_sha256"] == source["selection"],
            "RA_G1_CONFIGURATION_BINDING",
        )
        a.require(
            plan["window_start"] == config["window_start"]
            and plan["window_end"] == config["window_end"]
            and plan["shutdown_reserve_ms"] == 80000,
            "RA_G1_DEADLINE",
        )
        b = plan["budgets"]
        a.require(
            b == plan["blocks"][0]["budget"]
            and b["administrative_operations"] == 0
            and b["administrative_duration_ms"] == 0
            and b["data_observations"] == (len(rows) if group else 0)
            and b["required_control_observations"] == (0 if group else 8)
            and b["reserved_control_observations"] == 0
            and b["data_attempts"] == 5 * b["data_observations"]
            and b["control_http_attempts"] == 5 * b["required_control_observations"],
            "RA_G1_MATRIX_COVERAGE",
        )
        duration = 500000 if group else 180000
        a.require(b["active_duration_ms"] == duration, "RA_G1_DEADLINE")
        q = b["data_attempts"] + b["control_http_attempts"]
        observations = (duration + 49) // 50 + 2
        files = 4 * observations + 8
        sample_bytes = 4096 * files + 8 * (512 * files + 4096)
        ordinary = (52 if len(rows) == 64 else 28 if len(rows) == 32 else 8) * 2**30
        a.require(
            b["event_count"] <= 19 * q + 40 + 2 * observations + 4
            and b["storage_bytes"] <= ordinary + sample_bytes,
            "RA_G1_LIMITS",
        )
        totals["attempts"] += q
        totals["events"] += b["event_count"]
        totals["storage_bytes"] += b["storage_bytes"]
        totals["phase_duration_ms"] += duration
    a.require(
        totals["attempts"] == 2920
        and totals["phase_duration_ms"] == 5180000
        and totals["storage_bytes"] <= r["task_logical_write_ceiling_bytes"],
        "RA_G1_LIMITS",
    )
    return totals

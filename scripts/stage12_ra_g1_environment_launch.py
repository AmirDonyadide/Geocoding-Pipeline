"""Environment-specific admission for one existing representative diagnostic grant.

This companion never turns a local failure, hash reference or role intent into
native qualification or authority. The controller's original ready() remains.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

VERSION = "stage12_environment_specific_diagnostic_launch_gate_v1"
BINDING = "stage12_environment_specific_diagnostic_binding_v1"
SCOPE = "REPRESENTATIVE_NO_SERVICE"
ALLOCATION = "stage12_ra_g1_rep_first64_512_allocation_selection_v1"
POLICY = "RA_G1_ENVIRONMENT_DIAGNOSTIC_GATE_r1"
DOCUMENT = "docs/stages/STAGE12_ENVIRONMENT_DIAGNOSTIC_GATE_SUCCESSOR.md"
REQUIRED_SOURCE = (
    DOCUMENT,
    "scripts/stage12_ra_g1_environment_launch.py",
    "scripts/stage12_ra_g1_allocation.py",
)
WINDOW_END = "2026-11-11T19:13:21.620987Z"
MAX_BYTES = 16384
REQUIRED_REMAINING_SECONDS = 10320
BUDGET = dict(
    scheduler_seconds=8400,
    processing_seconds=8160,
    diagnostic_seconds=7200,
    collection_seconds=1800,
    collection_role_seconds=900,
    independent_terminal_review_seconds=120,
    collector_seconds=120,
    review_seconds=480,
    binder_seconds=240,
    binder_process_seconds=720,
    final_seconds=120,
    first64_seconds=512,
    event_files=57237,
    application_creations=204860,
    writer_guard_ms=5000,
    administrative_gap_ms=1000,
    AP_acquisition_gap_ms=100,
    AP_ACK_age_ms=500,
    AP_outstanding=16,
    sampler_close_ms=5000,
    scoped_startup_ms=30000,
)
HISTORY = dict(
    package_manifest_sha256="1bc6583e68abd6a9b814ba395c4d0c8546fc1c9feb694a470e559d19e987cbc1",
    package_source="a1a85956886d3a9c2686390288ea687a26b74219",
    executed_diagnostic_source="5fbd8188b9badd38ed0b11e017c6bd0fb58e0162",
    AP_first_code="ACQUISITION_GAP",
    rejected_AP_interval="NOT_RETAINED",
    AP_cause="UNKNOWN",
    later_administrative_delay_ns=12385255958,
    administrative_cause="UNKNOWN",
    environment_cause_established=False,
    local_result="FAILED_INCOMPLETE",
    local_timing_qualification=False,
)
BINDING_HASHES = (
    "policy_sha256",
    "amendment_sha256",
    "adoption_sha256",
    "gate_review_sha256",
    "collection_plan_sha256",
    "collection_review_sha256",
    "handoff_assets_sha256",
    "handoff_review_sha256",
    "grant_nonce",
)
GATE_HASHES = (
    *BINDING_HASHES,
    "selection_sha256",
    "resource_selection_sha256",
    "software_review_sha256",
    "resource_review_sha256",
    "source_inventory_sha256",
)


def need(value, code="RA_G1_SELECTION_BINDING"):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_hash(value, length=64):
    return (
        type(value) is str
        and len(value) == length
        and set(value) <= set("0123456789abcdef")
        and set(value) != {"0"}
    )


def epoch_ns(text):
    need(type(text) is str, "RA_G1_WINDOW")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, OverflowError):
        raise RuntimeError("RA_G1_WINDOW") from None
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds) * 1000


def descriptor():
    return dict(
        version=VERSION,
        policy=POLICY,
        scope=SCOPE,
        allocation_version=ALLOCATION,
        amendment_document=DOCUMENT,
        maximum_existing_grant_submissions=1,
        grant_kind="EXISTING_SINGLE_UNUSED_NATIVE_SYNTHETIC_GRANT",
        local_timing_pass_replaced_only=True,
        native_acceptance_unchanged=True,
        no_new_representative_or_public_slot=True,
        no_full_local_timing_run=True,
        public_protected_eligible=False,
        task_profiling="DISABLED",
        whole_workflow_qualification="NOT_ESTABLISHED",
        budget=dict(BUDGET),
        history=dict(HISTORY),
        outer_window_end=WINDOW_END,
        required_remaining_seconds=REQUIRED_REMAINING_SECONDS,
    )


def validate_binding(binding, selected):
    need(
        type(binding) is dict
        and set(binding) == {"version", "source_tree", *BINDING_HASHES},
        "RA_G1_FIELDS",
    )
    need(binding["version"] == BINDING and is_hash(binding["source_tree"], 40))
    need(all(is_hash(binding[key]) for key in BINDING_HASHES))
    need(binding["policy_sha256"] == digest(descriptor()))
    rows = selected.get("source_files")
    need(type(rows) is list and len(rows) <= 2048, "RA_G1_SOURCE_INVENTORY")
    for required in REQUIRED_SOURCE:
        matches = [
            row for row in rows if type(row) is dict and row.get("path") == required
        ]
        need(
            len(matches) == 1 and is_hash(matches[0].get("sha256")),
            "RA_G1_SOURCE_INVENTORY",
        )
    docs = [row for row in rows if type(row) is dict and row.get("path") == DOCUMENT]
    need(
        len(docs) == 1 and docs[0].get("sha256") == binding["amendment_sha256"],
        "RA_G1_SOURCE_CHANGED",
    )
    need(
        selected.get("version") == ALLOCATION and selected.get("scope") == SCOPE,
        "RA_G1_AUTHORITY_REQUIRED",
    )
    return binding


def gate_path(selected, identity):
    need(is_hash(identity), "RA_G1_SELECTION_BINDING")
    root = Path(selected["paths"]["records"])
    need(root.is_absolute() and ".." not in root.parts, "RA_G1_PATH")
    need(
        not any(
            part in {".ssh", ".config", "credentials", ".git"}
            or part.startswith(".env")
            for part in root.parts
        ),
        "RA_G1_PATH",
    )
    return root / (identity + ".environment-gate.record")


def selection_digest(selected):
    """Fresh canonical SHA without a selection-sized Unicode/bytes copy."""
    nodes = 0

    def bounded(value, depth=0):
        nonlocal nodes
        nodes += 1
        need(nodes <= 50000 and depth <= 16, "RA_G1_READ_LIMIT")
        if value is None or type(value) is bool:
            return
        if type(value) is str:
            need(len(value) <= 1024, "RA_G1_READ_LIMIT")
        elif type(value) is int:
            need(-(2**64) < value < 2**64, "RA_G1_READ_LIMIT")
        elif type(value) is list:
            need(len(value) <= 2048, "RA_G1_READ_LIMIT")
            for item in value:
                bounded(item, depth + 1)
        elif type(value) is dict:
            need(
                len(value) <= 128 and all(type(key) is str for key in value),
                "RA_G1_FIELDS",
            )
            for key, item in value.items():
                bounded(key, depth + 1)
                bounded(item, depth + 1)
        else:
            need(False, "RA_G1_FIELDS")

    bounded(selected)
    result, size = hashlib.sha256(), 1
    encoder = json.JSONEncoder(
        ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    for chunk in encoder.iterencode(selected):
        # A prevalidated <=1024-character scalar escapes to at most12290 ASCII bytes.
        need(chunk.isascii() and len(chunk) <= 12290, "RA_G1_READ_LIMIT")
        size += len(chunk)
        need(size <= 4 * 2**20, "RA_G1_READ_LIMIT")
        result.update(chunk.encode("ascii"))
    result.update(b"\n")
    return result.hexdigest()


def validate_gate(gate, selected, binding, *, now_epoch_ns):
    validate_binding(binding, selected)
    keys = {
        "version",
        "scope",
        "state",
        "source_git_sha",
        "source_tree",
        "valid_from",
        "valid_until",
        "outer_window_end",
        "grant_kind",
        "maximum_submissions",
        "task_profiling",
        "budget",
        "history",
        *GATE_HASHES,
    }
    need(type(gate) is dict and set(gate) == keys, "RA_G1_FIELDS")
    need(
        gate["version"] == VERSION
        and gate["scope"] == SCOPE
        and gate["state"] == "ISSUED_FOR_EXISTING_SINGLE_SYNTHETIC_GRANT",
        "RA_G1_AUTHORITY_REQUIRED",
    )
    need(all(is_hash(gate[key]) for key in GATE_HASHES))
    need(is_hash(gate["source_git_sha"], 40) and is_hash(gate["source_tree"], 40))
    need(all(gate[key] == binding[key] for key in (*BINDING_HASHES, "source_tree")))
    actual_selection_sha256 = selection_digest(selected)
    need(
        gate["source_git_sha"] == selected["source_sha"]
        and gate["selection_sha256"] == actual_selection_sha256
        and gate["resource_selection_sha256"] == selected["resource_selection_sha256"]
        and gate["software_review_sha256"] == selected["records"]["software_review"]
        and gate["resource_review_sha256"] == selected["records"]["resource_review"]
        and gate["source_inventory_sha256"]
        == selected["accounting_inventory"]["source_inventory_sha256"]
    )
    need(
        gate["grant_kind"] == "EXISTING_SINGLE_UNUSED_NATIVE_SYNTHETIC_GRANT"
        and type(gate["maximum_submissions"]) is int
        and gate["maximum_submissions"] == 1
        and gate["task_profiling"] == "DISABLED",
        "RA_G1_AUTHORITY_REQUIRED",
    )
    need(
        gate["budget"] == BUDGET
        and canonical(gate["budget"]) == canonical(BUDGET)
        and gate["history"] == HISTORY
        and canonical(gate["history"]) == canonical(HISTORY),
        "RA_G1_LIMITS",
    )
    need(
        gate["valid_from"] == selected["valid_from"]
        and gate["valid_until"] == selected["valid_until"]
        and gate["outer_window_end"] == WINDOW_END,
        "RA_G1_WINDOW",
    )
    start, end = epoch_ns(gate["valid_from"]), epoch_ns(gate["valid_until"])
    need(
        end <= epoch_ns(WINDOW_END)
        and type(now_epoch_ns) is int
        and start <= now_epoch_ns < end,
        "RA_G1_DEADLINE",
    )
    need(now_epoch_ns + REQUIRED_REMAINING_SECONDS * 10**9 <= end, "RA_G1_DEADLINE")
    return dict(
        status="ENVIRONMENT_SPECIFIC_DIAGNOSTIC_ELIGIBLE_NOT_QUALIFIED",
        gate_sha256=digest(gate),
        selection_sha256=actual_selection_sha256,
        resource_selection_sha256=selected["resource_selection_sha256"],
        policy_sha256=binding["policy_sha256"],
        grant_nonce=binding["grant_nonce"],
        checked_epoch_ns=now_epoch_ns,
        remaining_ns=end - now_epoch_ns,
        required_remaining_ns=REQUIRED_REMAINING_SECONDS * 10**9,
        native_timing_PASS=False,
        service_or_protected_authority=False,
    )


def validate_original_gate(run):
    """Fresh counted control reads; exact opt-in path was admitted by the hook."""
    run.check()
    identity = run.environment_gate_sha256
    review_identity = run.s["records"]["software_review"]
    review_raw = run.original(
        Path(run.s["paths"]["records"]) / (review_identity + ".record"), limit=MAX_BYTES
    )
    need(
        hashlib.sha256(review_raw).hexdigest() == review_identity,
        "RA_G1_ORIGINAL_CHANGED",
    )
    review = run.environment_gate_parser(review_raw)
    need(
        review.get("disposition") == "PASS"
        and review.get("source_sha") == run.s["source_sha"],
        "RA_G1_REVIEW_REQUIRED",
    )
    binding = validate_binding(review.get("environment_gate_binding"), run.s)
    raw = run.original(gate_path(run.s, identity), limit=MAX_BYTES)
    need(hashlib.sha256(raw).hexdigest() == identity, "RA_G1_ORIGINAL_CHANGED")
    # Use the actual production canonical parser rather than a parallel permissive one.
    gate = run.environment_gate_parser(raw)
    proof = validate_gate(gate, run.s, binding, now_epoch_ns=time.time_ns())
    run.check()
    return proof


def precheck(run):
    proof = validate_original_gate(run)
    run.environment_gate_initial = dict(proof)
    return proof


def after_ready(run):
    """Only called after original ready() has validated source and authority."""
    previous = getattr(run, "environment_gate_initial", None)
    need(type(previous) is dict, "RA_G1_REVIEW_REQUIRED")
    proof = validate_original_gate(run)
    stable = (
        "gate_sha256",
        "selection_sha256",
        "resource_selection_sha256",
        "policy_sha256",
        "grant_nonce",
    )
    need(all(proof[key] == previous[key] for key in stable), "RA_G1_ORIGINAL_CHANGED")
    run.check()
    return proof

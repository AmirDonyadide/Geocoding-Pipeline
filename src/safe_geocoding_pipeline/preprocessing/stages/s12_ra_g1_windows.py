"""Closed prospective synthetic/collection window; historical windows stay intact."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json

WINDOW_VERSION = "SYNTHETIC_AND_COLLECTION_WINDOW_r1"
WINDOW_START = "2026-11-11T16:49:36.000000Z"
WINDOW_END = "2026-11-12T19:13:21.620987Z"
PUBLIC_WINDOW_END = "2026-11-11T19:13:21.620987Z"
REP_GRANT = "COLLEC_QUALIFIED_ONE_FRESH_REP"
WINDOW_ADOPTION = "stage12_collection_first_rep_admin_window_adoption_v1"
ORIGINAL_SOURCE = "4a154308474dc8bfdbdd113322dd1335e41ce8fc"
ORIGINAL_JOB = "1812987"
ORIGINAL_SELECTION = "875aee40be3c1564431bd3755dcb4d9a30f322d2a9c592807127ec213a8dc2f0"
SCOPES = ("REPRESENTATIVE_NO_SERVICE", "TERMINAL_COLLECTION_NO_SERVICE")
INITIAL_REMAINING = 12240
REP_REMAINING = 10320
FINAL_REMAINING = 1920


def need(value, code="RA_G1_COLLECTION_FIRST_WINDOW"):
    if not value:
        raise RuntimeError(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def is_hash(value, length=64):
    return type(value) is str and len(value) == length and set(value) <= set("0123456789abcdef") and set(value) != {"0"}


def epoch_ns(value):
    need(type(value) is str)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError):
        raise RuntimeError("RA_G1_COLLECTION_FIRST_WINDOW") from None
    delta = parsed - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds) * 1000


def descriptor():
    return dict(version=WINDOW_VERSION, valid_from=WINDOW_START, valid_until=WINDOW_END,
        scopes=list(SCOPES), representative_grant_kind=REP_GRANT,
        maximum_representative_allocations=1, maximum_collection_allocations=2,
        initial_collection_required=True, qualification_independent_PASS_required=True,
        initial_remaining_seconds=INITIAL_REMAINING, representative_remaining_seconds=REP_REMAINING,
        final_collection_remaining_seconds=FINAL_REMAINING,
        no_replacement_or_requeue=True, no_new_public_slots=True, protected_authority=False,
        historical_deadlines_unchanged=True, public_window_end=PUBLIC_WINDOW_END,
        original_failed_source=ORIGINAL_SOURCE, original_failed_job=ORIGINAL_JOB,
        original_failed_selection_sha256=ORIGINAL_SELECTION)


def validate_window(value, *, scope, now_epoch_ns, required_remaining_seconds):
    need(type(value) is dict and set(value) == {"version", "scope", "valid_from", "valid_until", "policy_sha256", "owner_authority_sha256", "grant_nonce"})
    need(scope in SCOPES and value["scope"] == scope and value["version"] == WINDOW_VERSION)
    need(value["valid_from"] == WINDOW_START and value["valid_until"] == WINDOW_END)
    need(value["policy_sha256"] == digest(descriptor()) and all(is_hash(value[key]) for key in ("owner_authority_sha256", "grant_nonce")))
    need(type(now_epoch_ns) is int and type(required_remaining_seconds) is int and required_remaining_seconds in (INITIAL_REMAINING, REP_REMAINING, FINAL_REMAINING))
    start, end = epoch_ns(WINDOW_START), epoch_ns(WINDOW_END)
    need(start <= now_epoch_ns < end and now_epoch_ns + required_remaining_seconds * 10**9 <= end, "RA_G1_DEADLINE")
    return value


def validate_adoption(value, selected, *, original_validator, budget_policy_sha256):
    keys = {"schema_version", "scope", "window", "original_adoption", "original_adoption_sha256", "grant_kind", "maximum_submissions", "qualification_bundle_sha256", "qualification_review_sha256", "historical_grant_consumed", "original_budget_terms_unchanged"}
    need(type(value) is dict and set(value) == keys)
    need(value["schema_version"] == WINDOW_ADOPTION and value["scope"] == SCOPES[0])
    original = value["original_adoption"]
    need(type(original) is dict and original.get("schema_version") != WINDOW_ADOPTION)
    need(is_hash(value["original_adoption_sha256"]) and digest(original) == value["original_adoption_sha256"])
    original_validator(original, {"rep_admin_budget_adoption_sha256": value["original_adoption_sha256"], "rep_admin_budget_policy_sha256": budget_policy_sha256, "valid_until": PUBLIC_WINDOW_END})
    window = value["window"]
    validate_window(window, scope=SCOPES[0], now_epoch_ns=epoch_ns(WINDOW_START), required_remaining_seconds=REP_REMAINING)
    need(value["grant_kind"] == REP_GRANT and type(value["maximum_submissions"]) is int and value["maximum_submissions"] == 1)
    need(value["historical_grant_consumed"] is True and value["original_budget_terms_unchanged"] is True)
    need(all(is_hash(value[key]) for key in ("qualification_bundle_sha256", "qualification_review_sha256")))
    need(selected.get("scope", SCOPES[0]) == SCOPES[0])
    need(digest(value) == selected["rep_admin_budget_adoption_sha256"] and selected["rep_admin_budget_policy_sha256"] == budget_policy_sha256)
    if "valid_from" in selected:
        need(selected["valid_from"] == WINDOW_START)
    if "valid_until" in selected:
        need(selected["valid_until"] == WINDOW_END)
    return value

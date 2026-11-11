"""Invented authority records exercise exact prospective window contracts only."""
from copy import deepcopy
import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as w
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from test_stage12_ra_g1_rep_admin_budget import synthetic_adoption

H = "b" * 64


def window(scope="REPRESENTATIVE_NO_SERVICE"):
    return dict(version=w.WINDOW_VERSION, scope=scope, valid_from=w.WINDOW_START,
        valid_until=w.WINDOW_END, policy_sha256=w.digest(w.descriptor()),
        owner_authority_sha256=H, grant_nonce=H)


def adoption():
    original=synthetic_adoption()
    value=dict(schema_version=w.WINDOW_ADOPTION, scope=w.SCOPES[0], window=window(),
        original_adoption=original, original_adoption_sha256=w.digest(original),
        grant_kind=w.REP_GRANT, maximum_submissions=1, qualification_bundle_sha256=H,
        qualification_review_sha256=H, historical_grant_consumed=True,
        original_budget_terms_unchanged=True)
    selected=dict(rep_admin_budget_adoption_sha256=w.digest(value),
        rep_admin_budget_policy_sha256=w.digest(a.rep_admin_policy_descriptor()),
        valid_from=w.WINDOW_START, valid_until=w.WINDOW_END, scope=w.SCOPES[0])
    return value,selected


@pytest.mark.parametrize("scope,remaining", [(w.SCOPES[1],12240),(w.SCOPES[0],10320),(w.SCOPES[1],1920)])
def test_exact_entry_boundary_and_queue_expiry(scope,remaining):
    chosen=window(scope); latest=w.epoch_ns(w.WINDOW_END)-remaining*10**9
    assert w.validate_window(chosen,scope=scope,now_epoch_ns=latest,required_remaining_seconds=remaining)==chosen
    with pytest.raises(RuntimeError,match="RA_G1_DEADLINE"):
        w.validate_window(chosen,scope=scope,now_epoch_ns=latest+1,required_remaining_seconds=remaining)


@pytest.mark.parametrize("field,change", [("valid_from","2026-11-11T16:49:35.000000Z"),
    ("valid_until",w.PUBLIC_WINDOW_END),("scope","PUBLIC_SYNTHETIC_ONLY"),
    ("version","HISTORICAL_WINDOW"),("policy_sha256","c"*64),("grant_nonce","0"*64)])
def test_closed_window_rejects_mixed_or_unsupported_authority(field,change):
    chosen=window();chosen[field]=change
    with pytest.raises(RuntimeError):
        w.validate_window(chosen,scope=w.SCOPES[0],now_epoch_ns=w.epoch_ns(w.WINDOW_START),required_remaining_seconds=10320)


def test_explicit_wrapper_preserves_immutable_historical_budget_adoption():
    value,selected=adoption();before=deepcopy(value["original_adoption"])
    assert a.validate_rep_admin_adoption(value,selected)==value
    assert value["original_adoption"]==before
    historical=dict(rep_admin_budget_adoption_sha256=w.digest(before),
        rep_admin_budget_policy_sha256=selected["rep_admin_budget_policy_sha256"],valid_until=w.PUBLIC_WINDOW_END)
    assert a.validate_rep_admin_adoption(before,historical)==before
    historical["valid_until"]=w.WINDOW_END
    with pytest.raises(a.c.Stage12Error):
        a.validate_rep_admin_adoption(before,historical)


@pytest.mark.parametrize("field,change", [("grant_kind","EXISTING_SINGLE_UNUSED_NATIVE_SYNTHETIC_GRANT"),
    ("maximum_submissions",True),("maximum_submissions",2),("historical_grant_consumed",False),
    ("qualification_bundle_sha256","0"*64),("qualification_review_sha256","0"*64),
    ("original_adoption_sha256","c"*64)])
def test_wrapper_rejects_historical_grant_and_false_qualification(field,change):
    value,selected=adoption();value[field]=change;selected["rep_admin_budget_adoption_sha256"]=w.digest(value)
    with pytest.raises((RuntimeError,a.c.Stage12Error)):
        a.validate_rep_admin_adoption(value,selected)


def test_wrapper_rejects_nested_or_altered_original_and_foreign_scope():
    value,selected=adoption()
    for change in ("original","nested","scope","extra"):
        current=deepcopy(value);chosen=deepcopy(selected)
        if change=="original":current["original_adoption"]["unchanged_window_end"]=w.WINDOW_END
        elif change=="nested":current["original_adoption"]=deepcopy(value)
        elif change=="scope":chosen["scope"]="PUBLIC_SYNTHETIC_ONLY"
        else:current["permission"]=True
        current["original_adoption_sha256"]=w.digest(current["original_adoption"])
        chosen["rep_admin_budget_adoption_sha256"]=w.digest(current)
        with pytest.raises((RuntimeError,a.c.Stage12Error)):
            a.validate_rep_admin_adoption(current,chosen)

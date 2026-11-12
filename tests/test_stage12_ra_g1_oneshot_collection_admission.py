"""Focused invented admission and actual-fd selected read accounting checks."""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import sys
import time
import types
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_collection_driver as driver

def invented(version="stage12_collection_only_admission_v1"):
    """No issued authority or executable workload: parser fixtures only."""
    binding=dict(source_git_sha="1"*40,original_job_id=0,original_source_git_sha="2"*40,
        original_selection_sha256="3"*64,original_source_root="/invented/source",
        allocation_producer_sha256="4"*64,window={"scope":"TEST_ONLY"},grant_nonce="5"*32,
        helper_sha256="6"*64,parent_sha256="7"*64,verifier_sha256="8"*64,
        collection_purpose="POST_B",historical_collection=None)
    authority=dict(max_collection_jobs=1,max_collection_seconds=1800,
        collection_pool_bytes=25769803776,collection_pool_creations=450000,control_pool_bytes=67108864)
    value=dict(version=version,scope="TERMINAL_COLLECTION_NO_SERVICE",state="TEST_ONLY",**{k:v for k,v in binding.items() if k!="historical_collection"},
        historical_collection_sha256=pair.digest(pair.tc.canonical(None)),collection_plan_sha256="9"*64,
        collection_review_sha256="a"*64,software_review_sha256="b"*64,process_graph_sha256="c"*64,
        maximum_preparation_and_native_processes=69,**authority,B_authorized=False,public_authorized=False,
        protected_authorized=False,scientific_acceptance=False)
    if version==pair.ONESHOT_ADMISSION_VERSION:
        policy=dict(pair.ONESHOT_CONTROL_LIMITS)
        for filename,key in pair.ONESHOT_SOURCE_FIELDS:
            policy[key]=hashlib.sha256((ROOT/"scripts"/filename).read_bytes()).hexdigest()
        value.update(maximum_preparation_and_native_processes=208,one_shot_control_policy=policy)
    return value,binding,authority

def reject(value,binding,authority,code="AUTHORITY"):
    with pytest.raises(pair.tc.Stop) as e:
        pair.validate_collection_admission(value,binding,authority,True)
    assert e.value.args==(code,)

def test_exact_legacy_and_successor_canonical_records():
    for version in ("stage12_collection_only_admission_v1",pair.ONESHOT_ADMISSION_VERSION):
        value,binding,authority=invented(version)
        raw=pair.tc.canonical(value)
        actual=pair.tc.parse(raw)
        assert pair.validate_collection_admission(actual,binding,authority,True)==value

def test_version_and_counter_separation():
    legacy,binding,authority=invented()
    new,_,_=invented(pair.ONESHOT_ADMISSION_VERSION)
    value=copy.deepcopy(legacy);value["maximum_preparation_and_native_processes"]=208;reject(value,binding,authority)
    value=copy.deepcopy(new);value["maximum_preparation_and_native_processes"]=69;reject(value,binding,authority)
    value=copy.deepcopy(legacy);value["one_shot_control_policy"]=new["one_shot_control_policy"];reject(value,binding,authority)
    value=copy.deepcopy(new);value.pop("one_shot_control_policy");reject(value,binding,authority)
    value=copy.deepcopy(legacy);value["version"]="unknown";reject(value,binding,authority)
    reject(None,binding,authority)

def test_every_new_numeric_and_identity_policy_bound():
    new,binding,authority=invented(pair.ONESHOT_ADMISSION_VERSION)
    for key,expected in pair.ONESHOT_CONTROL_LIMITS:
        for wrong in ([True,float(expected),expected+1] if type(expected) is int else [None,expected+"_changed"]):
            value=copy.deepcopy(new);value["one_shot_control_policy"][key]=wrong;reject(value,binding,authority)
    for _,key in pair.ONESHOT_SOURCE_FIELDS:
        for wrong in (None,"0"*64,"not-a-hash"):
            value=copy.deepcopy(new);value["one_shot_control_policy"][key]=wrong;reject(value,binding,authority,"BINDING" if wrong in (None,"not-a-hash") else "AUTHORITY")
    value=copy.deepcopy(new);value["one_shot_control_policy"]["unselected"]=1;reject(value,binding,authority)

def test_scope_and_actual_binding_mismatch():
    new,binding,authority=invented(pair.ONESHOT_ADMISSION_VERSION)
    for key in ("B_authorized","public_authorized","protected_authorized","scientific_acceptance"):
        value=copy.deepcopy(new);value[key]=True;reject(value,binding,authority,"SCOPE")
    for key in ("source_git_sha","original_source_git_sha","original_selection_sha256","grant_nonce"):
        value=copy.deepcopy(new);value[key]="d"*len(value[key]);reject(value,binding,authority)
    value=copy.deepcopy(new);value["collection_pool_bytes"]+=1;reject(value,binding,authority)

def make_control():
    c=pair.Control(time.monotonic_ns(),time.time_ns()+30*10**9,30)
    driver.install_selected_read_limit(c,pair)
    return c

def test_short_read_eof_exact_selected_attempt_boundary(tmp_path):
    p=tmp_path/"actual.bin";p.write_bytes(b"ab");fd=os.open(p,os.O_RDONLY)
    try:
        c=make_control()
        assert c.read(fd,65536)==b"ab" and c.read_bytes==2
        assert c.read(fd,1)==b"" and c.selected_read_attempts==2
        c.selected_read_attempts=driver.SELECTED_OVERALL_READ_ATTEMPTS-1
        assert c.read(fd,1)==b""
        assert c.selected_read_attempts==driver.SELECTED_OVERALL_READ_ATTEMPTS
        before=c.read_calls
        with pytest.raises(pair.tc.Stop) as e:c.read(fd,1)
        assert e.value.args==("READ_CALLS",) and c.read_calls==before and os.lseek(fd,0,os.SEEK_CUR)==2
        with pytest.raises(pair.tc.Stop):driver.install_selected_read_limit(c,pair)
        assert c.selected_read_attempts==driver.SELECTED_OVERALL_READ_ATTEMPTS
    finally:os.close(fd)

def test_nested_reentry_reserves_outer_attempt_before_base_check(tmp_path):
    p=tmp_path/"nested.bin";p.write_bytes(b"abcd");fd=os.open(p,os.O_RDONLY)
    try:
        c=make_control();once=False
        def serviced(self):
            nonlocal once
            if not once:once=True;assert self.read(fd,1)==b"a"
            pair.Control.check(self)
        c.check=types.MethodType(serviced,c)
        assert c.read(fd,1)==b"b"
        assert c.selected_read_attempts==c.read_calls==2
        assert c.read_bytes==2
        os.lseek(fd,0,os.SEEK_SET)
        c=make_control();c.selected_read_attempts=driver.SELECTED_OVERALL_READ_ATTEMPTS-1;once=False
        def near_limit(self):
            nonlocal once
            if not once:once=True;self.read(fd,1)
            pair.Control.check(self)
        c.check=types.MethodType(near_limit,c)
        with pytest.raises(pair.tc.Stop) as e:c.read(fd,1)
        assert e.value.args==("READ_CALLS",)
        assert c.selected_read_attempts==driver.SELECTED_OVERALL_READ_ATTEMPTS and c.read_calls==0
        assert os.lseek(fd,0,os.SEEK_CUR)==0
    finally:os.close(fd)

def test_base_primary_failure_is_preserved_and_never_refunded(tmp_path):
    p=tmp_path/"primary.bin";p.write_bytes(b"x");fd=os.open(p,os.O_RDONLY)
    try:
        c=make_control();primary=pair.tc.Stop("SOURCE_CHANGED")
        def failed(self):raise primary
        c.check=types.MethodType(failed,c)
        with pytest.raises(pair.tc.Stop) as e:c.read(fd,1)
        assert e.value is primary and c.selected_read_attempts==1 and c.read_calls==0
        assert os.lseek(fd,0,os.SEEK_CUR)==0
    finally:os.close(fd)

def test_driver_rejects_old_scalar_before_original_access():
    value,binding,authority=invented()
    with pytest.raises(pair.tc.Stop) as e:
        driver.load_verified_admission({}, {"actual_admission_process_cap":208},None,pair,None,None)
    assert e.value.args==("AUTHORITY",)

def test_actual_source_hash_rejects_changed_original(tmp_path):
    p=tmp_path/"source.py";p.write_bytes(b"original\n");p.chmod(0o600)
    expected=hashlib.sha256(p.read_bytes()).hexdigest();c=make_control()
    pair.source_hash(p,expected,c)
    p.write_bytes(b"changed!\n")
    with pytest.raises(pair.tc.Stop) as e:pair.source_hash(p,expected,c)
    assert e.value.args==("SOURCE_CHANGED",)


def test_phase_and_overall_share_exact_attempt_limit(tmp_path):
    p=tmp_path/"shared.bin";p.write_bytes(b"ab");fd=os.open(p,os.O_RDONLY)
    try:
        c=make_control();phase=driver.phase_control(pair,c,20,c.epoch_end)
        assert phase.read(fd,1)==b"a" and c.read(fd,1)==b"b"
        assert phase.read_calls==c.read_calls==1 and c.selected_read_attempts==2
        c.selected_read_attempts=driver.SELECTED_OVERALL_READ_ATTEMPTS-1
        assert phase.read(fd,1)==b""
        assert c.selected_read_attempts==driver.SELECTED_OVERALL_READ_ATTEMPTS
        for owner in (phase,c):
            before=owner.read_calls
            with pytest.raises(pair.tc.Stop) as e:owner.read(fd,1)
            assert e.value.args==("READ_CALLS",) and owner.read_calls==before
        assert os.lseek(fd,0,os.SEEK_CUR)==2
    finally:os.close(fd)


def test_phase_precharge_before_reentrant_overall_check_and_primary_failure(tmp_path):
    p=tmp_path/"phase_nested.bin";p.write_bytes(b"ab");fd=os.open(p,os.O_RDONLY)
    try:
        c=make_control();once=False
        def service(self):
            nonlocal once
            if not once:once=True;assert self.read(fd,1)==b"a"
            pair.Control.check(self)
        c.check=types.MethodType(service,c)
        phase=driver.phase_control(pair,c,20,c.epoch_end)
        assert phase.read(fd,1)==b"b"
        assert c.selected_read_attempts==2 and phase.read_calls==c.read_calls==1
        c.selected_read_attempts=driver.SELECTED_OVERALL_READ_ATTEMPTS-1;once=False
        before=(phase.read_calls,c.read_calls,os.lseek(fd,0,os.SEEK_CUR))
        with pytest.raises(pair.tc.Stop) as e:phase.read(fd,1)
        assert e.value.args==("READ_CALLS",) and c.selected_read_attempts==driver.SELECTED_OVERALL_READ_ATTEMPTS
        assert (phase.read_calls,c.read_calls,os.lseek(fd,0,os.SEEK_CUR))==before
        # Fresh invented owner: original exception and failed attempt are retained.
        c=make_control();primary=pair.tc.Stop("SOURCE_CHANGED")
        def fail(self):raise primary
        c.check=types.MethodType(fail,c);phase=driver.phase_control(pair,c,20,c.epoch_end)
        with pytest.raises(pair.tc.Stop) as e:phase.read(fd,1)
        assert e.value is primary and c.selected_read_attempts==1 and phase.read_calls==0
    finally:os.close(fd)

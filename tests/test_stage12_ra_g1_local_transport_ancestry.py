"""Selected local-directory identity tests; invented remote facts, real guards/FDs."""
from __future__ import annotations
import ast
import base64
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import sys
import time
import types
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tests')]
import stage12_ra_g1_terminal_collect as tc
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_one_shot_controls as observer
import test_stage12_ra_g1_selected_pair_readiness as selected
import test_stage12_ra_g1_terminal_transport as existing
SCOPE=transport.TASK_LOCAL_DIRECTORY_SCOPE
PYTHON=str(ROOT/'.venv/bin/python')


def owner():
    return pair.Control(time.monotonic_ns(),time.time_ns()+30*10**9,30)


def arm_callback(monkeypatch,control,target,callback,*,links=False):
    original_capture=tc.ancestors;original_check=control.check
    state=dict(armed=False,fired=False,capture=None)
    def capture(path,links=True):
        chain=original_capture(path,links=links)
        if Path(path)==target and links is capture_links and not state['armed']:
            state.update(armed=True,capture=[(str(p),list(i)) for p,i in chain])
        return chain
    capture_links=links
    def check(self):
        original_check()
        if state['armed'] and not state['fired']:
            state['fired']=True;callback()
    monkeypatch.setattr(tc,'ancestors',capture)
    control.check=types.MethodType(check,control)
    return state


def actual_child(monkeypatch,wire,errors=b'',*,read_input=None):
    monkeypatch.setenv('SAFE_STAGE12_INVENTED_TRANSPORT','1')
    prefix='import sys,os;'
    if read_input is not None:
        prefix+='raw=sys.stdin.buffer.read();assert raw==bytes.fromhex('+repr(read_input.hex())+');'
    return [PYTHON,'-u','-c',prefix+'os.write(1,bytes.fromhex('+repr(wire.hex())+'));os.write(2,bytes.fromhex('+repr(errors.hex())+'))']


@pytest.mark.parametrize('selected_mode',[True,False])
def test_real_observer_callback_sibling_and_legacy_boundary(tmp_path,monkeypatch,selected_mode):
    out=tmp_path/'out';out.mkdir(mode=0o700)
    records=tmp_path/'records';records.mkdir(mode=0o700)
    c=owner();target=out/'probe-01'
    def callback():
        c.claim(0,True);(out/'sibling').mkdir(mode=0o700)
    state=arm_callback(monkeypatch,c,target,callback,links=not selected_mode)
    _,_,wire,errors=selected._transcript(directory_absent=True)
    argv=actual_child(monkeypatch,wire,errors)
    plan=dict(selected.PLAN)
    if selected_mode:plan['local_directory_scope']=SCOPE
    options=dict(local_directory_scope=SCOPE) if selected_mode else {}
    def record(name,value):return c.record(records/name,value)
    if selected_mode:
        result=observer.probe(plan,out,c,transport,pair,tc,record,lambda *args:None,
                              testing_argv=argv,nonce='1'*32,**options)
        assert result['status']=='PENDING' and not c.cleanup_uncertain
        d=result['transport_diagnostic'];p=d['pending_check']
        assert p['child_exit']==0 and p['observed_joined'] and p['stdout_eof'] and p['stderr_eof']
        assert d['metadata_before']==d['metadata_after'] and d['domain_before']==d['domain_after']
    else:
        with pytest.raises(tc.Stop) as caught:
            observer.probe(plan,out,c,transport,pair,tc,record,lambda *args:None,
                           testing_argv=argv,nonce='1'*32)
        assert caught.value.args==('ANCESTOR_CHANGED',)
        assert caught.value.transport_diagnostic['first_phase']=='JOIN'
    assert state['armed'] and state['fired']


@pytest.mark.parametrize('kind',['artifact','receipt','hardlink'])
def test_real_artifact_and_receipt_paths_keep_original_file_invariants(tmp_path,monkeypatch,kind):
    payload=b'INVENTED-ONLY-payload'
    source=tmp_path/'source';source.write_bytes(payload);source.chmod(0o600)
    out=tmp_path/'out';out.mkdir(mode=0o700)
    row=dict(label='payload',path=str(source),bytes=len(payload),sha256=pair.digest(payload))
    existing.framed_fixture(tmp_path,[row])
    wire=(tmp_path/'fixture.wire').read_bytes()
    c=owner();target=out/'payload.original'
    if kind=='hardlink':
        original_check=c.check;fired=[]
        def check(self):
            original_check()
            if target.exists() and not fired:
                fired.append(True);os.link(target,out/'hardlink')
        c.check=types.MethodType(check,c)
        state=None
    else:
        def callback():
            c.claim(0,True);(out/'sibling').mkdir(mode=0o700)
        state=arm_callback(monkeypatch,c,out,callback)
    options={}
    if kind=='receipt':
        options=dict(publication=dict(bytes=len(payload)),input_bytes=payload)
    argv=actual_child(monkeypatch,wire,read_input=payload if kind=='receipt' else None)
    if kind=='hardlink':
        with pytest.raises(tc.Stop) as caught:
            transport.fetch_batch([row],out,c,expected_uid=os.geteuid(),expected_gid=os.getegid(),
                testing_argv=argv,nonce='1'*32,local_directory_scope=SCOPE)
        assert target.lstat().st_nlink==2 and caught.value.args==('LINK',)
    else:
        evidence,extras=transport.fetch_batch([row],out,c,expected_uid=os.geteuid(),expected_gid=os.getegid(),
            testing_argv=argv,nonce='1'*32,local_directory_scope=SCOPE,**options)
        pair.validate_transport_evidence(evidence)
        assert evidence['exit_code']==0 and evidence['observed_joined'] and not extras
        assert target.read_bytes()==payload and target.lstat().st_nlink==1
        assert evidence['files'][0]['sha256']==pair.digest(payload) and not c.cleanup_uncertain
        assert state['fired']


@pytest.mark.parametrize('change',['mode','replacement','symlink','missing'])
def test_prechild_callback_unsafe_target_keeps_exact_first_mismatch(tmp_path,monkeypatch,change):
    out=tmp_path/'out';out.mkdir(mode=0o700);c=owner()
    def callback():
        if change=='mode':out.chmod(0o755)
        else:
            out.rename(tmp_path/'old')
            if change=='replacement':out.mkdir(mode=0o700)
            if change=='symlink':out.symlink_to(tmp_path/'old',target_is_directory=True)
    state=arm_callback(monkeypatch,c,out,callback)
    monkeypatch.setattr(transport.subprocess,'Popen',lambda *a,**k:pytest.fail('no child on changed ancestry'))
    row=dict(label='x',path='/invented/x',bytes=0,sha256=pair.digest(b''))
    with pytest.raises((tc.Stop,OSError)) as caught:
        transport.fetch_batch([row],out,c,expected_uid=os.geteuid(),local_directory_scope=SCOPE)
    d=caught.value.transport_diagnostic['local_ancestry']
    assert state['fired'] and d['retention']=='COMPLETE' and d['kind']=='TARGET'
    assert base64.b64decode(d['path_fsencode_base64'])==os.fsencode(out)
    assert d['expected'] and d['predicate']=={'mode':'MODE','replacement':'INODE','symlink':'INODE','missing':'LSTAT_FAILED'}[change]
    if change=='missing':assert isinstance(caught.value,FileNotFoundError) and d['current'] is None
    else:assert caught.value.args==('SOURCE_CHANGED',)
    assert not caught.value.transport_diagnostic['remote_cleanup_status']=='JOINED_NATIVE_EXIT_ZERO'


@pytest.mark.parametrize('field',['st_dev','st_ino','st_mode','st_uid','st_gid'])
def test_actual_comparator_rejects_each_bound_kernel_field(tmp_path,monkeypatch,field):
    # Explicit simulated kernel metadata for otherwise unavailable device/UID/GID changes.
    out=tmp_path/'out';out.mkdir(mode=0o700)
    original=Path.lstat;before=out.lstat();expected=tc.ident(before)[:5]
    attrs={name:getattr(before,name) for name in dir(before) if name.startswith('st_')}
    attrs[field]+=1
    def lstat(path,*args,**kwargs):
        return types.SimpleNamespace(**attrs) if path==out else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'lstat',lstat)
    with pytest.raises(tc.Stop) as caught:transport._check_task_local_directories([],out,expected)
    assert caught.value.args==('SOURCE_CHANGED',)
    d=caught.value.local_ancestry_diagnostic
    assert d['expected']==list(expected) and d['current']==list(tc.ident(types.SimpleNamespace(**attrs))[:5])
    assert d['predicate']=={'st_dev':'DEVICE','st_ino':'INODE','st_mode':'MODE','st_uid':'UID','st_gid':'GID'}[field]


def test_ancestor_mismatch_ordinal_and_first_diagnostic_precedence(tmp_path):
    parent=tmp_path/'parent';parent.mkdir(mode=0o700)
    target=parent/'target';target.mkdir(mode=0o700)
    expected=tc.ident(parent.lstat())[:5];parent.chmod(0o755)
    with pytest.raises(tc.Stop) as caught:
        transport._check_task_local_directories([(parent,expected)],target,tc.ident(target.lstat())[:5])
    error=caught.value;first=error.local_ancestry_diagnostic
    assert first['kind']=='ANCESTOR' and first['ordinal']==0 and first['predicate']=='MODE'
    assert error.args==('ANCESTOR_CHANGED',)
    assert transport._local_mismatch(error,target,1,'TARGET',expected,expected,'INODE') is error
    assert error.local_ancestry_diagnostic is first


def test_diagnostic_encoding_is_bounded_and_never_replaces_primary(monkeypatch):
    error=tc.Stop('SOURCE_CHANGED');raw=b'/'+b'x'*8191
    transport._local_mismatch(error,Path(os.fsdecode(raw)),0,'TARGET',(1,2,3,4,5),(2,2,3,4,5),'DEVICE')
    d=error.local_ancestry_diagnostic
    assert len(d['path_fsencode_base64'])==10924 and base64.b64decode(d['path_fsencode_base64'])==raw
    assert len(tc.canonical(d))<12000 and not d['path_truncated']
    secret='SECRET MUST NOT BE RETAINED'
    def fail(*args):raise ValueError(secret)
    monkeypatch.setattr(transport.base64,'b64encode',fail)
    primary=FileNotFoundError(2,secret)
    assert transport._local_mismatch(primary,Path('/invented'),0,'TARGET',(1,2,3,4,5),None,'LSTAT_FAILED') is primary
    assert primary.local_ancestry_diagnostic==dict(version=transport.LOCAL_ANCESTRY_DIAGNOSTIC_VERSION,retention='INCOMPLETE')
    assert secret not in str(primary.local_ancestry_diagnostic)


@pytest.mark.parametrize('value',[False,True,1,{},'unknown'])
def test_unknown_scope_rejected_before_paths_or_children(value):
    with pytest.raises(tc.Stop) as caught:transport._local_scope(value)
    assert caught.value.args==('SCOPE',)
    assert transport._local_scope(None) is False and transport._local_scope(SCOPE) is True


def test_missing_or_mixed_plan_scope_cannot_enter_probe(tmp_path):
    out=tmp_path/'out';out.mkdir(mode=0o700)
    for plan,mode in ((dict(selected.PLAN),SCOPE),(dict(selected.PLAN,local_directory_scope=SCOPE),None)):
        with pytest.raises(observer.Stop) as caught:
            observer.probe(plan,out,owner(),transport,pair,tc,lambda *a:None,lambda *a:None,
                           local_directory_scope=mode)
        assert caught.value.args==('POLL_CONFIG',) and list(out.iterdir())==[]


def test_selected_caller_propagation_and_frozen_helper_contract():
    # Structural plumbing plus real helper fail-closed entry; no live facts granted.
    expected={'stage12_ra_g1_collection_driver.py':3,'stage12_ra_g1_one_shot_controls.py':2}
    for name,count in expected.items():
        tree=ast.parse((ROOT/'scripts'/name).read_text())
        calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ((isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id in ('transport','observer') and n.func.attr in ('fetch_batch','fetch_ready','probe','poll')) or (isinstance(n.func,ast.Name) and n.func.id=='probe'))]
        assert len(calls)==count and all(any(k.arg=='local_directory_scope' for k in n.keywords) for n in calls)
    path=os.environ.get('SAFE_STAGE12_TEST_HANDOFF_CANDIDATE')
    if path is None:pytest.skip('task-frozen helper path supplied only for release verification')
    raw=Path(path).read_bytes()
    tree=ast.parse(raw)
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
           and n.func.attr in ('fetch_batch','fetch_ready')]
    assert len(calls)==5 and all(any(k.arg=='local_directory_scope' for k in n.keywords) for n in calls)
    spec=importlib.util.spec_from_file_location('task_local_ancestry_handoff',path)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    for plan in ({},{'local_directory_scope':None},{'local_directory_scope':'unknown'}):
        with pytest.raises(RuntimeError) as caught:helper.components(plan)
        assert caught.value.args==('TASK_BINDING',)

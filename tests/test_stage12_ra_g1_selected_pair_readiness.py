"""Selected-directory readiness transcripts; actual FD parser, no native jobs."""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import stat
import sys
import time
import types
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_one_shot_controls as observer
import stage12_ra_g1_collection_driver as driver
tc=pair.tc

PLAN=dict(remote_pair='/invented/owner/pair',source_uid=os.geteuid(),source_gid=os.getegid())


def _transcript(*, directory_absent=True, ready=False, mutation=None):
    """Invented remote metadata only; actual parser/FD/hash/fsync remain live."""
    rows,ancestors=observer.rows_for(PLAN,transport)
    paths,_,_=transport.batch_paths(rows)
    snapshot=paths+ancestors
    uid,gid=PLAN['source_uid'],PLAN['source_gid']
    stamp='2026-11-12 00:00:00.000000000 +0000'
    selected=len(rows)+ancestors.index(Path(PLAN['remote_pair']))
    higher=len(rows)+ancestors.index(Path(PLAN['remote_pair']).parent)
    absent={0,1,2}
    if ready:absent.remove(0)
    if directory_absent:absent.add(selected)
    if mutation=='higher_absent':absent.add(higher)
    info=[]
    for i,path in enumerate(snapshot):
        mode=0o100600 if i<len(rows) else 0o40700 if i in (selected,higher) else 0o40755
        if mutation=='link' and i==selected:mode=0o120700
        if mutation=='not_dir' and i==selected:mode=0o100600
        if mutation=='parent_public' and i==higher:mode=0o40755
        size=2 if ready and i==0 else 0
        kind='directory' if stat.S_ISDIR(mode) else 'symbolic link' if stat.S_ISLNK(mode) else 'regular file' if size else 'regular empty file'
        info.append(f'1|{100+i}|{mode:x}|{uid}|{gid}|{1 if i<len(rows) else 2}|{size}|{stamp}|{stamp}|{kind}')
    def block(stage):
        data=bytearray(f'{stage}_STATUS|1\n'.encode())
        for i,path in enumerate(snapshot):
            if i not in absent:
                value=info[i]
                if stage=='AFTER' and mutation=='changed' and i==higher:value=value.replace(f'|{100+i}|',f'|{200+i}|',1)
                data.extend((str(path)+'|'+value+'\n').encode())
        if stage=='AFTER' and mutation=='appeared':
            data.extend((str(snapshot[selected])+'|'+info[selected]+'\n').encode())
        return bytes(data)+f'END_{stage}\n'.encode()
    nonce='1'*32
    domain=f'DOMAIN|invented-host|11111111-1111-1111-1111-111111111111|mnt:[11]|{nonce}|11\n'.encode()
    wire=f'S12B3|{nonce}|3|0|{len(ancestors)}\n'.encode()+domain+block('BEFORE')
    for i in range(3):wire+=(f'DATA|{i}|2\n{{}}\nEND_DATA|{i}\n' if i not in absent else f'ABSENT_DATA|{i}\n').encode()
    wire+=block('AFTER')+domain+f'END|{nonce}\n'.encode()
    errors=b''.join((f"stat: cannot statx '{snapshot[i]}': No such file or directory\n").encode() for i in sorted(absent))*2
    if mutation=='denied':errors=errors.replace(b'No such file or directory',b'Permission denied')
    if mutation=='truncated':wire=wire[:-10]
    return rows,ancestors,wire,errors


def _pipe_process(monkeypatch, wire, errors, exit_code=0):
    # Complete, bounded, already-exited invented producer using genuine pipe EOF.
    assert len(wire)<=8192 and len(errors)<=4096
    stdout,write=os.pipe();stderr,ewrite=os.pipe()
    try:
        assert os.write(write,wire)==len(wire)
        assert os.write(ewrite,errors)==len(errors)
    finally:os.close(write);os.close(ewrite)
    class Process:
        pid=0
        stdin=None
        def __init__(self):
            self.stdout=os.fdopen(stdout,'rb',buffering=0)
            self.stderr=os.fdopen(stderr,'rb',buffering=0)
        def poll(self):return exit_code
        def wait(self,timeout=None):return exit_code
    proc=Process()
    monkeypatch.setattr(transport.subprocess,'Popen',lambda *args,**kwargs:proc)
    monkeypatch.setenv('SAFE_STAGE12_INVENTED_TRANSPORT','1')
    return proc


def _read(tmp_path,monkeypatch,*,opt_in=True,exit_code=0,**kwargs):
    rows,ancestors,wire,errors=_transcript(**kwargs)
    proc=_pipe_process(monkeypatch,wire,errors,exit_code)
    out=tmp_path/'retained';out.mkdir(mode=0o700)
    c=pair.Control(time.monotonic_ns(),time.time_ns()+10**10,10)
    options=dict(pending_final_directory=PLAN['remote_pair']) if opt_in else {}
    with pytest.raises(tc.Stop) as caught:
        transport.fetch_batch(rows,out,c,expected_uid=PLAN['source_uid'],expected_gid=PLAN['source_gid'],
            testing_argv=['invented-closed-pipes'],nonce='1'*32,pending_labels=observer.LABELS,
            keep_stdin_open=True,**options)
    assert proc.stdout.closed and proc.stderr.closed
    return caught.value,rows,ancestors,c,out


def test_selected_absent_exact_enoent_complete_pending(tmp_path,monkeypatch):
    error,rows,ancestors,c,_=_read(tmp_path,monkeypatch)
    states,files,evidence,diagnostic=observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])
    assert observer._classify(states,files)=='PENDING' and evidence is None
    pending=diagnostic['pending_check']
    assert pending['verified_missing_final_directory']==PLAN['remote_pair']
    assert pending['verified_missing_errno_labels']==list(observer.LABELS)
    assert pending['child_exit']==0 and pending['observed_joined'] and pending['stdout_eof'] and pending['stderr_eof']
    assert diagnostic['remote_cleanup_status']=='JOINED_NATIVE_EXIT_ZERO' and not c.cleanup_uncertain


def test_legacy_reader_still_rejects_missing_directory(tmp_path,monkeypatch):
    error,rows,ancestors,c,_=_read(tmp_path,monkeypatch,opt_in=False)
    assert error.args==('ANCESTOR',)
    assert error.transport_diagnostic['pending_check']['version']=='stage12_task_named_control_absence_v1'
    assert 'selected_final_directory' not in error.transport_diagnostic['pending_check']
    with pytest.raises(observer.Stop):observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])


def test_existing_private_empty_directory_uses_strict_controls(tmp_path,monkeypatch):
    error,rows,ancestors,c,_=_read(tmp_path,monkeypatch,directory_absent=False)
    states,files,evidence,diagnostic=observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])
    assert observer._classify(states,files)=='PENDING'
    assert diagnostic['pending_check']['verified_missing_final_directory'] is None
    assert not c.cleanup_uncertain


def test_existing_ready_keeps_original_hash_and_same_domain(tmp_path,monkeypatch):
    error,rows,ancestors,c,out=_read(tmp_path,monkeypatch,directory_absent=False,ready=True)
    states,files,evidence,diagnostic=observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])
    assert observer._classify(states,files)=='READY_ORIGINAL_AWAITING_CONTEXT_VALIDATION'
    assert (out/'ready.original').read_bytes()==b'{}'
    assert files['ready']['sha256']==hashlib.sha256(b'{}').hexdigest()
    pair.validate_transport_evidence(evidence)
    assert not c.cleanup_uncertain


def test_missing_higher_denial_link_type_change_and_truncation_never_pending(tmp_path,monkeypatch):
    for index,mutation in enumerate(('higher_absent','denied','link','not_dir','parent_public','changed','appeared','truncated')):
        root=tmp_path/str(index);root.mkdir(mode=0o700)
        error,rows,ancestors,c,_=_read(root,monkeypatch,mutation=mutation,
            directory_absent=mutation not in ('link','not_dir'))
        with pytest.raises(observer.Stop):observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])


def test_nonzero_exit_never_pending(tmp_path,monkeypatch):
    error,rows,ancestors,c,_=_read(tmp_path,monkeypatch,exit_code=7)
    with pytest.raises(observer.Stop):observer._missing_result(error,rows,ancestors,pair,tc,PLAN['remote_pair'])
    assert error.transport_diagnostic['pending_check']['child_exit']==7


def test_generator_exact_opt_in_and_unchanged_process_graph():
    rows,ancestors=observer.rows_for(PLAN,transport)
    old=transport.batch_remote_argv(rows,'1'*32,expected_uid=PLAN['source_uid'],expected_gid=PLAN['source_gid'])
    explicit_none=transport.batch_remote_argv(rows,'1'*32,expected_uid=PLAN['source_uid'],expected_gid=PLAN['source_gid'],pending_final_directory=None)
    selected=transport.batch_remote_argv(rows,'1'*32,expected_uid=PLAN['source_uid'],expected_gid=PLAN['source_gid'],pending_final_directory=PLAN['remote_pair'])
    assert old==explicit_none
    assert selected[-1].count('stat --printf=')==2 and selected[-1].count('dd if=')==3
    assert selected[:7]==old[:7] and 'mkdir' not in selected[-1]
    for invalid in ('/invented/owner','/invented/owner/other','/','/invented/owner/pair/../other'):
        with pytest.raises(tc.Stop):transport.batch_remote_argv(rows,'1'*32,expected_uid=PLAN['source_uid'],pending_final_directory=invalid)
    with pytest.raises(tc.Stop):transport.batch_remote_argv(rows[:1],'1'*32,expected_uid=PLAN['source_uid'],pending_final_directory=PLAN['remote_pair'])


def _admission():
    # Existing parser-only legacy fixture; no executable permission facts.
    import importlib.util
    spec=importlib.util.spec_from_file_location('legacy_admission_fixture',ROOT/'tests/test_stage12_ra_g1_oneshot_collection_admission.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    value,binding,authority=fixture.invented(pair.ONESHOT_ADMISSION_VERSION)
    binding['output_path']=PLAN['remote_pair']
    value['version']=pair.SELECTED_PAIR_ADMISSION_VERSION
    value['maximum_preparation_and_native_processes']=228
    policy=dict(pair.SELECTED_PAIR_CONTROL_LIMITS)
    policy['selected_remote_pair']=binding['output_path']
    for filename,key in pair.ONESHOT_SOURCE_FIELDS:policy[key]=hashlib.sha256((ROOT/'scripts'/filename).read_bytes()).hexdigest()
    value['one_shot_control_policy']=policy
    return value,binding,authority,fixture


def test_closed_selected_admission_preserves_69_208_228_families():
    value,binding,authority,fixture=_admission()
    assert pair.validate_collection_admission(tc.parse(tc.canonical(value)),binding,authority,True)==value
    for legacy in ('stage12_collection_only_admission_v1',pair.ONESHOT_ADMISSION_VERSION):
        old,old_binding,old_authority=fixture.invented(legacy)
        assert pair.validate_collection_admission(old,old_binding,old_authority,True)==old
    for mutate in ('path','version','underfund','policy','extra'):
        bad=copy.deepcopy(value)
        if mutate=='path':bad['one_shot_control_policy']['selected_remote_pair']+='/other'
        if mutate=='version':bad['version']=pair.ONESHOT_ADMISSION_VERSION
        if mutate=='underfund':bad['maximum_preparation_and_native_processes']=208
        if mutate=='policy':bad['one_shot_control_policy']['version']='stage12_task_oneshot_controls_v1'
        if mutate=='extra':bad['one_shot_control_policy']['unknown']=True
        with pytest.raises(tc.Stop):pair.validate_collection_admission(bad,binding,authority,True)


def test_optional_failure_hook_preserves_primary_and_original_clock():
    owner=pair.Control(time.monotonic_ns(),time.time_ns()+30*10**9,30)
    primary=dict(stage='OBSERVE',code='RETENTION',transport=dict(metadata_before=[[1,2,3]]))
    before=copy.deepcopy(primary);end=owner.end;calls=[]
    def callback(**kwargs):
        calls.append(kwargs)
        assert kwargs['overall'] is owner and kwargs['overall'].end==end
        kwargs['first_failure_copy']['transport']['metadata_before'][0][0]=99
        raise ValueError('secret must never be retained')
    result=driver.run_irreversible_failure_hook(callback,overall=owner,streams=None,proc=None,
        plan={'test':True},command={'test':True},first_failure=primary,pair=pair,tc=tc)
    assert primary==before and owner.end==end and len(calls)==1
    assert result['status']=='FAILED_OR_UNCERTAIN' and result['invoked'] and result['safe_error']=='UNCLASSIFIED'
    assert 'secret' not in str(result) and result['original_deadline_mono_ns']==end
    assert result['complete_mono_ns']>=result['entry_mono_ns']
    assert driver.execute.__kwdefaults__=={'on_irreversible_failure':None}


def test_failure_hook_success_is_separate_not_acceptance():
    owner=pair.Control(time.monotonic_ns(),time.time_ns()+30*10**9,30)
    called=[]
    result=driver.run_irreversible_failure_hook(lambda **kwargs:called.append(kwargs),
        overall=owner,streams=None,proc=None,plan={},command={},first_failure={'stage':'OBSERVE','code':'RETENTION'},pair=pair,tc=tc)
    assert len(called)==1 and result['status']=='RETURNED_PENDING_INDEPENDENT_VERIFICATION'
    assert 'scientific_acceptance' not in result and 'COMPLETE' not in result['status']


def test_execute_calls_hook_once_after_primary_capture_without_submission(tmp_path):
    calls=[];records=[];marks=[]
    def callback(**kwargs):
        calls.append(kwargs)
        assert records[0][0]=='FIRST_FAILURE.record'
        kwargs['first_failure_copy']['stage']='MUTATED_COPY'
        raise ValueError('must remain redacted')
    plan=dict(window_end_epoch_ns=time.time_ns()+30*10**9)
    command=dict(observer_argv=['incompatible-unselected-observer'])
    out=driver.execute(plan,command,[],[],tmp_path,(tc,pair,transport,None),observer,None,None,
        lambda *a:None,lambda:marks.append(True),lambda name,value:records.append((name,copy.deepcopy(value))),{},
        on_irreversible_failure=callback)
    assert len(calls)==1 and not marks and out['actual_client_exit'] is None
    assert out['status']=='INCOMPLETE' and out['first_failure']['stage']=='SUBMIT'
    assert records[0][1]==out['first_failure']
    assert out['irreversible_failure_hook']['status']=='FAILED_OR_UNCERTAIN'
    assert out['irreversible_failure_hook']['safe_error']=='UNCLASSIFIED'
    assert out['role_deadline_mono_ns']==calls[0]['overall'].end
    assert 'must remain redacted' not in str(out)


def test_execute_default_hook_none_preserves_failure_disposition(tmp_path):
    records=[]
    out=driver.execute(dict(window_end_epoch_ns=time.time_ns()+30*10**9),
        dict(observer_argv=[]),[],[],tmp_path,(tc,pair,transport,None),observer,None,None,
        lambda *a:None,lambda:pytest.fail('must not submit'),lambda name,value:records.append(name),{})
    assert out['status']=='INCOMPLETE' and out['first_failure']['stage']=='SUBMIT'
    assert 'irreversible_failure_hook' not in out
    assert records==['FIRST_FAILURE.record','COORDINATOR_OUTCOME.record']

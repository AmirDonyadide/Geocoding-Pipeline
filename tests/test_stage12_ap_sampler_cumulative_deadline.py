"""Focused cumulative deadline initialization; invented unit controls only.

The separate connected driver exercises the genuine Authority and installed
Python audit hook with the full selected first64 hold/work/reopen path.
"""
from datetime import datetime, timedelta, timezone
import threading
import time

import pytest
from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_ra_g1_integration import H, KEY, RealClock, SyntheticAuthority, Validation, ra_inputs
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_recovery as recovery
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract


def run_paused(tmp_path,monkeypatch,*,task_seconds=120,block_ms=None,window_seconds=None):
    profile,plan,start,record,selected,rows,inventory=ra_inputs()
    if block_ms is not None:
        plan['blocks'][0]['budget']['active_duration_ms']=block_ms
    if window_seconds is not None:
        plan['window_end']=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=window_seconds)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    start['plan_sha256']=contract.digest(plan)
    clock=RealClock()
    owner=SyntheticAuthority(profile,plan,start,record,selected,rows,clock)
    actual_sampler_init=sampling.Sampler.__init__
    actual_coordinator_init=scheduler.Coordinator.__init__
    observed={}
    holder=[]
    dispatched=[]
    def sampler_init(self,coordinator):
        observed['before_remaining']=coordinator.writer.remaining_seconds()
        actual_sampler_init(self,coordinator)
        observed['captured_before_post_constructor']=self.deadline_ns
        observed['sampler']=self
    def coordinator_init(self,*args,**kwargs):
        actual_coordinator_init(self,*args,**kwargs)
        holder.append(self)
        observed['coordinator']=self
        observed['callback_check']=kwargs.get('cumulative_check')
        observed['callback_remaining']=kwargs.get('cumulative_remaining')
    monkeypatch.setattr(sampling.Sampler,'__init__',sampler_init)
    monkeypatch.setattr(scheduler.Coordinator,'__init__',coordinator_init)
    deadline=None if task_seconds is None else clock.now_ns()+int(task_seconds*10**9)
    def pause():
        co=holder[0]
        if 'post_bound' not in observed:
            observed.update(post_bound=co.writer.remaining_seconds.__self__.end_ns,
                sampler_after_post=co.ap_sampler.deadline_ns,opened_ns=co.opened_ns,
                writer_guard_ms=co.writer.guard_ms,now_ns=clock.now_ns())
        return True
    report=cli.run_operations_block(profile,plan,start,work_factory=lambda:iter(rows),
        output=tmp_path/'phase',block_id=1,authority=owner,clock=clock,
        dispatch=lambda *args:dispatched.append(args),runtime_inventory=inventory,
        runtime_key=KEY,control_adapters={},monitor=None,free_bytes=lambda:2**40,
        segment_authority=H,writer_exclusion_evidence=H,epoch='1'*64,
        writer_release_evidence=H,public_validation=Validation(),
        pause_requested=pause,task_deadline_ns=deadline)
    assert not dispatched and report['disposition'] != 'COMPLETED'
    return observed,deadline,report


def test_explicit_task_bound_is_installed_before_real_sampler_snapshot(tmp_path,monkeypatch):
    got,deadline,_=run_paused(tmp_path,monkeypatch)
    assert got['callback_check'] is not None and got['callback_remaining'] is not None
    assert got['before_remaining']>100
    assert 0<=deadline-got['captured_before_post_constructor']<100_000_000
    assert got['sampler_after_post']<=got['captured_before_post_constructor']
    assert got['post_bound']<=deadline
    assert got['writer_guard_ms']==5000


def test_post_constructor_earlier_block_only_tightens_cached_sampler(tmp_path,monkeypatch):
    got,deadline,_=run_paused(tmp_path,monkeypatch,task_seconds=120,block_ms=90_000)
    assert got['captured_before_post_constructor']>got['opened_ns']+100_000_000_000
    assert got['post_bound']==got['opened_ns']+90_000_000_000
    assert got['sampler_after_post']==min(got['captured_before_post_constructor'],got['post_bound'])
    assert got['post_bound']<deadline


def test_authorization_window_remains_an_earlier_bound(tmp_path,monkeypatch):
    got,deadline,_=run_paused(tmp_path,monkeypatch,task_seconds=120,window_seconds=30)
    assert got['before_remaining']<31
    assert got['post_bound']<deadline
    assert got['sampler_after_post']<=31_000_000_000


def test_none_legacy_constructor_callbacks_and_snapshot_remain_unchanged(tmp_path,monkeypatch):
    got,deadline,_=run_paused(tmp_path,monkeypatch,task_seconds=None)
    assert deadline is None and got['callback_check'] is None and got['callback_remaining'] is None
    assert got['before_remaining']==5
    assert got['captured_before_post_constructor']<6_000_000_000
    assert got['sampler_after_post']==got['captured_before_post_constructor']


def test_expired_explicit_task_fails_before_writer_or_sampler_start(tmp_path):
    profile,plan,start,record,selected,rows,inventory=ra_inputs()
    clock=RealClock()
    owner=SyntheticAuthority(profile,plan,start,record,selected,rows,clock)
    with pytest.raises(recovery.FinalizationExpired):
        cli.run_operations_block(profile,plan,start,work_factory=lambda:iter(rows),
            output=tmp_path/'phase',block_id=1,authority=owner,clock=clock,
            dispatch=lambda *args:pytest.fail('late dispatch'),runtime_inventory=inventory,
            runtime_key=KEY,control_adapters={},monitor=None,free_bytes=lambda:2**40,
            segment_authority=H,writer_exclusion_evidence=H,epoch='1'*64,
            writer_release_evidence=H,public_validation=Validation(),task_deadline_ns=1)
    assert not (tmp_path/'phase').exists()


def test_constructor_crossing_selected_deadline_cannot_leave_success(tmp_path,monkeypatch):
    profile,plan,start,record,selected,rows,inventory=ra_inputs()
    clock=RealClock()
    owner=SyntheticAuthority(profile,plan,start,record,selected,rows,clock)
    original=sampling.Sampler.__init__
    captured=[]
    def delayed(self,coordinator):
        captured.append(coordinator)
        time.sleep(0.35)
        original(self,coordinator)
    monkeypatch.setattr(sampling.Sampler,'__init__',delayed)
    deadline=clock.now_ns()+250_000_000
    with pytest.raises(recovery.FinalizationExpired):
        cli.run_operations_block(profile,plan,start,work_factory=lambda:iter(rows),
            output=tmp_path/'phase',block_id=1,authority=owner,clock=clock,
            dispatch=lambda *args:pytest.fail('expired constructor dispatched'),runtime_inventory=inventory,
            runtime_key=KEY,control_adapters={},monitor=None,free_bytes=lambda:2**40,
            segment_authority=H,writer_exclusion_evidence=H,epoch='1'*64,
            writer_release_evidence=H,public_validation=Validation(),task_deadline_ns=deadline)
    assert captured
    writer=captured[0].writer
    # This join only observes bounded test cleanup; it creates no release/seal.
    writer.thread.join(0.5)
    assert not writer.thread.is_alive() and writer.failed.is_set()
    assert not (tmp_path/'phase'/'_WRITER_RELEASED.json').exists()
    assert not (tmp_path/'phase'/'_SEGMENT_SEALED').exists()


def test_true_cumulative_expiry_poisoning_preserves_original_and_no_release(tmp_path):
    from safe_geocoding_pipeline.preprocessing.stages import s12_storage as storage
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_diagnostics import Failures
    clock=RealClock()
    stopped=threading.Event()
    writer=journal.Writer(tmp_path/'writer',1,5000,stopped.set)
    bound=recovery.Deadline(clock,clock.now_ns()+150_000_000)
    writer.check_deadline=bound.check
    writer.remaining_seconds=bound.remaining_seconds
    writer.failures=Failures(clock)
    original=b'INVENTED_ORIGINAL_REMAINS'
    writer.call(lambda:storage.write(writer.root/'original.record',original))
    entered=threading.Event()
    release=threading.Event()
    def action():
        entered.set()
        release.wait(0.4)
    try:
        with pytest.raises((TimeoutError,recovery.FinalizationExpired)):
            writer.call(action)
        assert entered.is_set() and writer.failed.is_set() and stopped.is_set()
        assert writer.failures.snapshot()['first_initiating_failure'] is not None
        assert (writer.root/'original.record').read_bytes()==original
    finally:
        release.set()
        writer.abort()
        writer.thread.join(0.5)
    assert not writer.thread.is_alive()
    assert not (writer.root/'_WRITER_RELEASED.json').exists()
    assert not (writer.root/'_SEGMENT_SEALED').exists()


def test_five_second_action_guard_remains_smaller_than_long_cumulative_bound(tmp_path,monkeypatch):
    from concurrent.futures import Future
    clock=RealClock()
    writer=journal.Writer(tmp_path/'writer',1,5000,lambda:None)
    bound=recovery.Deadline(clock,clock.now_ns()+20_000_000_000)
    writer.check_deadline=bound.check
    writer.remaining_seconds=bound.remaining_seconds
    actual=Future.result
    timeouts=[]
    def observed(future,timeout=None):
        timeouts.append(timeout)
        return actual(future,timeout=timeout)
    monkeypatch.setattr(Future,'result',observed)
    try:
        assert writer.call(lambda:42)==42
        assert timeouts==[5] and writer.guard_ms==5000
        assert writer.remaining_seconds()>19
    finally:
        writer.abort()
    assert not writer.thread.is_alive()

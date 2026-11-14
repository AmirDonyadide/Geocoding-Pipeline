"""Representative checkpoint service; controlled clocks, real durable originals."""
from copy import deepcopy
import json
import threading
import time
from pathlib import Path

import pytest
from test_stage12_public_operations_v2 import FakeClock,H,KEY,offline  # noqa:F401
from test_stage12_rep_ack_queue import selected_inputs as ack_inputs
from test_stage12_public_operational_audit import capture
from test_stage12_ra_g1_integration import SyntheticAuthority,ra_inputs
from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_ack_contract as ack
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract as fair
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_public_operational_audit as oa
from safe_geocoding_pipeline.preprocessing.stages import s12_public_audit as audit
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_timing as timing
from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_timing as compact
from safe_geocoding_pipeline.preprocessing.stages import s12_public_checkpoints as cp
from safe_geocoding_pipeline.preprocessing.stages import s12_storage as io
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages.s12_wf_ap2_scratch import lease
from test_s12_ra_g1_core import capacity
from stage12_synthetic import body,feature


def selected_inputs(clock):
 p,plan,start,old=ack_inputs(ack,clock)
 selected=deepcopy(old.selected);record=deepcopy(old.record)
 selected.update(schema_version=assurance.REP_FAIR_SELECTION,
  rep_fair_policy_sha256=fair.POLICY_SHA,rep_fair_policy_adoption_sha256=H)
 selected.pop('rep_ack_policy_sha256');selected.pop('rep_ack_policy_adoption_sha256')
 assurance.validate_selection(selected)
 record['selection_sha256']=fair.digest(selected)
 p['resources'].update(resource_selection_sha256=fair.digest(selected),initial_capacity_observation_sha256=fair.digest(capacity(selected)))
 p.update(schema_version=fair.PROFILE,rule_bundle_sha256=fair.RULE_BUNDLE,sampling_policy_sha256=fair.POLICY_SHA,sampling_runtime_bound_sha256=fair.digest(record))
 plan.update(schema_version=fair.PLAN,operations_profile_sha256=fair.digest(p))
 start.update(schema_version=fair.START,profile_sha256=fair.digest(p),plan_sha256=fair.digest(plan),rule_bundle_sha256=fair.RULE_BUNDLE,sampling_policy_sha256=fair.POLICY_SHA)
 authority=SyntheticAuthority(p,plan,start,record,selected,old.rows,clock)
 authority.diagnostic_scope='REPRESENTATIVE_NO_SERVICE';authority.service_authority=False
 return p,plan,start,authority


@pytest.mark.parametrize('wire,cooperative',[(ack,True),(fair,True),(fair,False)],ids=['old_action_quota','selected_outer_checkpoint','fair_without_eligible_checkpoint'])
def test_real_finish_DATA_connected_before_after(offline,tmp_path,monkeypatch,wire,cooperative):
 clock=FakeClock();p,plan,start,authority=selected_inputs(clock)if wire is fair else ack_inputs(ack,clock)
 observer=timing.SamplingTiming(tmp_path/'timing',phase_count=1,timing_schema=cp.RA_SCHEMA,
  timing_policy_version=wire.POLICY_VERSION,timing_binding=dict(policy_sha256=wire.POLICY_SHA,source_sha256=H,task_sha256=H),
  phase_windows=[dict(phase_id=1,selected_phase_ms=20000)],cumulative_deadline_ns=100_000_000_000,clock_ns=clock.now_ns,max_files=2980)
 observer.phase_open(1,phase_deadline_ns=20_000_000_000,timeout_seconds=2)
 co=scheduler.Coordinator(p,plan,start,authority=authority,clock=clock,root=tmp_path/'run',block_id=1,segment_authority=H,writer_exclusion_evidence=H,epoch=H,free_bytes=lambda:2**42,contract=wire,timing_observer=observer)
 ap=co.ap_sampler;root=tmp_path/'run'/'invented_data';runtime=ra_inputs()[-1];work=authority.rows[0]
 active=False;steps=0;peak=0;progress=[];released=False
 original_read=io.original_read;original_write=io.write
 def advance(path):
  nonlocal steps,peak
  if not active or not path.is_relative_to(root)or steps>=22:return
  steps+=1;clock.advance(50_000_000);target=clock.now_ns();until=time.monotonic()+.5
  while ap.last_observed<target and ap.failure is None and time.monotonic()<until:time.sleep(.001)
  peak=max(peak,ap.occupied);progress.append((steps,ap.occupied,ap.witnessed,ap.failure))
 def read(path,**kw):
  result=original_read(path,**kw);advance(path);return result
 def write(path,raw):
  result=original_write(path,raw);advance(path);return result
 try:
  co.writer.cooperative(lambda:oa.begin_data(root,p,plan,start,work,1,runtime))
  raw=body([feature()]);record=oa.transport_record(work,1,capture(raw),clock.utc())
  monkeypatch.setattr(io,'original_read',read);monkeypatch.setattr(io,'write',write)
  def commit():
   nonlocal active
   active=True
   try:return oa.finish_data(root,work,record,raw,key=KEY,validator=cli.public_shapes)
   finally:active=False
  terminal,receipt=(co.writer.cooperative(commit)if cooperative else co.writer.call(commit))
  assert terminal['outcome']in c.SUCCESS and steps==22
  assert audit.reopen(root,audit.name_for(work['work_id'],1),validator=cli.public_shapes,context=oa.DataContext())==terminal
  if wire is ack or not cooperative:assert ap.failure=='OBSERVATION_COUNT_LIMIT'and peak==16
  else:
   assert ap.failure is None and peak<=2 and ap.maximum_gap==50_000_000
   assert all(b[0]==a[0]+1 and b[2]>=a[2]for a,b in zip(progress,progress[1:]))
   with ap.condition:assert ap.condition.wait_for(lambda:ap.occupied==0,timeout=2)
   clock.advance(1);closed=ap.close();assert closed['result']=='COMPLETE'
   co.writer.release(dict(scope='TEST_ONLY_FINISH_DATA_AP_COMPONENT',scientific_pass=False));released=True
   events=list(journal.read_events(tmp_path/'run',wire.digest(start),contract=wire))
   summaries=sampling.inspect(lambda:iter(events),p,start,maximum_segments=1,contract=wire)
   assert summaries[0]['complete']and ap.witnessed==ap.acquired
   with pytest.raises(c.Stage12Error):list(journal.read_events(tmp_path/'run',ack.digest(start),contract=ack))
  observer.phase_close(1,quiescent=True,timeout_seconds=2);obs=observer.close(timeout_seconds=2)
  prefix=compact.read_prefix(tmp_path/'timing',timing_schema=cp.RA_SCHEMA,max_files=2980,
   expected_binding=dict(policy_sha256=wire.POLICY_SHA,source_sha256=H,task_sha256=H))
  assert prefix['last_payload']['policy_version']==wire.POLICY_VERSION
  result=dict(scope='TEST_ONLY_ACTUAL_FINISH_DATA_COMPONENT_NOT_NATIVE_OR_CAMPAIGN_PASS',policy=wire.POLICY_VERSION,
   steps=steps,explicit_outer_checkpoints=cooperative,peak_outstanding=peak,acquired=ap.acquired,witnessed=ap.witnessed,failure=ap.failure,progress=progress,
   maximum_gap_ns=ap.maximum_gap,writer_released=released,timing_complete=obs['persistence_complete'])
  (tmp_path/'OBSERVED.record').write_bytes(c.canonical(result));(tmp_path/'OBSERVED.record').chmod(0o600)
 finally:
  if not released:co.writer.abort()
  if not observer.closed:observer.close(timeout_seconds=2)
 assert not co.writer.thread.is_alive()and not ap.thread.is_alive()


def coordinator_at(tmp_path,clock):
 p,plan,start,authority=selected_inputs(clock)
 co=scheduler.Coordinator(p,plan,start,authority=authority,clock=clock,root=tmp_path/'run',block_id=1,
  segment_authority=H,writer_exclusion_evidence=H,epoch=H,free_bytes=lambda:2**42,contract=fair)
 return co


def queue_one(co,clock):
 before=co.ap_sampler.acquired;clock.advance(50_000_000);until=time.monotonic()+1
 while co.ap_sampler.acquired==before and co.ap_sampler.failure is None and time.monotonic()<until:time.sleep(.001)
 assert co.ap_sampler.acquired==before+1


def test_direct_and_callback_entry_share_scratch_exclusion(offline,tmp_path):
 clock=FakeClock();co=coordinator_at(tmp_path,clock);ap=co.ap_sampler;observed=[]
 def action():
  queue_one(co,clock);origin=co.writer.ap_active_started
  for kind in ('EVENT','OBSERVATION'):
   before=(ap.appended,ap.witnessed,ap.occupied)
   with lease(kind):
    assert co.writer.sampling_pair()is False
    co.writer.service_periodic();co.writer.cooperative_checkpoint()
    assert (ap.appended,ap.witnessed,ap.occupied)==before
    assert not co.writer.ap_pair_active and co.writer.ap_active_started==origin
   observed.append(kind)
  co.writer.cooperative_checkpoint()
  assert ap.occupied==0 and ap.witnessed==1 and co.writer.ap_active_started==origin
 try:co.writer.cooperative(action)
 finally:co.writer.abort()
 assert observed==['EVENT','OBSERVATION']and not co.writer.thread.is_alive()and not ap.thread.is_alive()


def test_pair_guard_spans_direct_recursion_return_guards_retirement_and_observer(offline,tmp_path,monkeypatch):
 clock=FakeClock();co=coordinator_at(tmp_path,clock);ap=co.ap_sampler;sites=[];origin=[None]
 def recursion(site):
  assert co.writer.ap_pair_active and co.writer.ap_active_started==origin[0]
  before=(ap.appended,ap.witnessed,ap.occupied)
  co.writer.service_periodic();co.writer.cooperative_checkpoint()
  assert co.writer.sampling_pair()is False
  co.writer._execute_periodic()
  assert co.writer.ap_active_started==origin[0]and(ap.appended,ap.witnessed,ap.occupied)==before
  sites.append(site)
 for name in ('service','pair_return','after_turn'):
  original=getattr(ap,name)
  def wrapper(original=original,name=name):
   if origin[0] is not None:recursion(name)
   return original()
  monkeypatch.setattr(ap,name,wrapper)
 original_guard=co.writer.storage_guard
 def guard():
  if co.writer.ap_pair_active and origin[0]is not None:recursion('post_storage')
  return original_guard()
 monkeypatch.setattr(co.writer,'storage_guard',guard)
 class Observer:
  phase_id=1
  def periodic(self,row):recursion('observer')
 # Ensure a real immutable trace exists for the terminal observer callback.
 observer=Observer();co.timing_observer=observer
 def action():
  queue_one(co,clock);origin[0]=co.writer.ap_active_started
  co.writer.cooperative_checkpoint()
  assert ap.witnessed==1 and ap.occupied==0
 try:co.writer.cooperative(action)
 finally:co.writer.abort()
 assert {'service','pair_return','after_turn','post_storage','observer'}<=set(sites)
 assert not co.writer.ap_pair_active and not co.writer.thread.is_alive()and not ap.thread.is_alive()


def test_nested_pair_consumes_original_deadline_and_keeps_poisoned_credit(offline,tmp_path,monkeypatch):
 clock=FakeClock();co=coordinator_at(tmp_path,clock);ap=co.ap_sampler;origin=[];seen=[]
 original=ap.service
 def service():
  seen.append(co.writer.ap_active_started);return original()
 monkeypatch.setattr(ap,'service',service)
 original_guard=co.writer.storage_guard
 from safe_geocoding_pipeline.preprocessing.stages.s12_public_recovery import Deadline,FinalizationExpired
 co.writer.check_deadline=Deadline(clock,100_000_000).check
 def guard():
  if co.writer.ap_pair_active and ap.pending_release is not None:
   assert co.writer.ap_active_started==origin[0]
   clock.advance(100_000_000-clock.now_ns())
   # The existing absolute deadline expires inside the original outer action.
   co.writer.check_deadline()
  return original_guard()
 monkeypatch.setattr(co.writer,'storage_guard',guard)
 def action():
  origin.append(co.writer.ap_active_started);queue_one(co,clock);co.writer.cooperative_checkpoint()
 try:
  with pytest.raises(FinalizationExpired):co.writer.cooperative(action)
  assert seen==origin
  assert ap.occupied==1 and ap.pending_release is not None and ap.states[ap.pending_release]==4
  assert not co.writer.ap_pair_active and co.writer.failed.is_set()
 finally:co.writer.abort()
 assert not co.writer.thread.is_alive()and not ap.thread.is_alive()


@pytest.mark.parametrize('policy,digest',[(fair.POLICY_VERSION,H),(ack.POLICY_VERSION,fair.POLICY_SHA),(fair.POLICY_VERSION,ack.POLICY_SHA),(compact.RA_POLICY,fair.POLICY_SHA)])
def test_timing_constructor_rejects_mixed_family_before_creation(tmp_path,policy,digest):
 with pytest.raises(cp.CheckpointError,match='CHECKPOINT_BINDING_INVALID'):
  timing.SamplingTiming(tmp_path/'timing',phase_count=1,timing_schema=cp.RA_SCHEMA,timing_policy_version=policy,
   timing_binding=dict(policy_sha256=digest,source_sha256=H,task_sha256=H),phase_windows=[dict(phase_id=1,selected_phase_ms=20000)],
   cumulative_deadline_ns=100_000_000_000,max_files=2980)
 assert not(tmp_path/'timing').exists()


def test_storage_tail_pin_is_atomic_when_outer_action_is_cooperative(offline,tmp_path,monkeypatch):
 clock=FakeClock();co=coordinator_at(tmp_path,clock);ap=co.ap_sampler
 assert co.journal.accounted_bytes is not None
 for i in range(3):co.writer.call(lambda i=i:io.write(co.writer.root/f'invented_{i}',b'invented'))
 original_tree=journal.tree_bytes;original_read=io.original_read;scan_steps=0;tail_queued=False
 def tree(root,exclude=frozenset(),*,check=lambda:None,**kw):
  def step():
   nonlocal scan_steps
   if root==co.writer.root and scan_steps<2:
    scan_steps+=1;queue_one(co,clock)
   check()
  return original_tree(root,exclude,check=step,**kw)
 def read(path,**kw):
  nonlocal tail_queued
  result=original_read(path,**kw)
  if path.parent.name=='events'and not co.writer.ap_pair_active and not tail_queued:
   tail_queued=True;queue_one(co,clock)
  return result
 monkeypatch.setattr(journal,'tree_bytes',tree);monkeypatch.setattr(io,'original_read',read)
 try:
  def action():
   total=co.journal.verify_storage()
   assert total==co.journal.accounted_bytes
   return total
  total=co.writer.cooperative(action)
  assert scan_steps==2 and tail_queued and total<=co.journal.accounted_bytes
  assert not co.writer.failed.is_set()
 finally:co.writer.abort()
 assert not co.writer.thread.is_alive()and not ap.thread.is_alive()


def test_selected_fair_caller_report_and_actual_reopening(offline,tmp_path):
 from test_stage12_public_sampling_integration import RealClock
 from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
 from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
 from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
 clock=RealClock();p,plan,start,authority=selected_inputs(clock);calls=[]
 def invented_dispatch(work,target,hooks):
  hooks.started(clock.now_ns());hooks.emit(lambda:None,lambda:None);calls.append(work['work_id'])
  raw=body([feature()]);record=transport.Capture('VALIDATION_REQUIRED','OK',200,'application/json','identity',None,raw,len(raw),1)
  hooks.completed(record);return record
 report=cli.run_operations_block(p,plan,start,work_factory=lambda:iter(authority.rows),output=tmp_path/'phase',block_id=1,
  authority=authority,clock=clock,dispatch=invented_dispatch,runtime_inventory=ra_inputs()[-1],runtime_key=KEY,
  control_adapters={},monitor=None,free_bytes=lambda:2**40,segment_authority=H,writer_exclusion_evidence=H,
  epoch='1'*64,writer_release_evidence=H,public_validation=Validation(),task_deadline_ns=clock.now_ns()+180*10**9)
 assert calls==[1,2]and report['schema_version']==fair.REPORT and report['report_complete']is True
 assert runtime.reopen_completed(tmp_path/'phase',p,plan,start,validation_sha256=fair.digest(Validation().descriptor()))==report['blocks'][0]
 assert report['sampling_segments']and all(row['complete']for row in report['sampling_segments'])


def fair_adoption():
 from test_stage12_rep_ack_queue import policy_adoption
 return dict(policy_adoption(),schema_version=assurance.REP_FAIR_ADOPTION,policy_sha256=fair.POLICY_SHA,
  old_fairness_assertions_withdrawn=True,maximum_pairs_per_outer_checkpoint=1,
  pair_active_through_credit_retirement=True,original_action_deadline_preserved=True)


def fair_upgrade(value):
 from test_stage12_rep_ack_queue import ack_upgrade
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
 from test_stage12_foreground_accounting import FLAGS
 from test_stage12_ra_g1_rep_admin_budget import allocation
 result=ack_upgrade(value);result['version']=allocation.REP_FAIR_VERSION
 result.pop('rep_ack_policy_adoption');result.pop('rep_ack_policy_adoption_sha256')
 result.update(rep_fair_policy_adoption=fair_adoption(),rep_fair_policy_adoption_sha256=fair.digest(fair_adoption()))
 result['accounting_inventory'],result['accounting']=ac.compile_inventory(result['source_files'],result['accounting_inventory']['backends'],allocation.SCOPE,
  foreground_successor=True,fair_service_successor=True,**FLAGS)
 return result


from test_stage12_ra_g1_production_binding import private_source,production  # noqa:E402,F401


def test_actual_builder_grants_and_matched_handoff_boundaries(production,monkeypatch):
 import test_stage12_ra_g1_review_handoff as prior
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
 from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
 production.bootstrap['created_utc']=windows.SIMPLE_WINDOW_START
 monkeypatch.setattr(prior,'upgrade',fair_upgrade)
 case=prior.handoff.__wrapped__(production)
 data=case.controller.parse(case.originals['input']);selected=case.controller.parse(case.selection_raw)
 assert selected['version']==case.controller.REP_FAIR_VERSION and data['version']==case.diagnostic.REP_FAIR_VERSION
 case.controller.validate_selection(selected);case.diagnostic.validate_envelope(data,selected['source_sha'],for_execution=True)
 case.diagnostic.validate_workloads(data)
 assert data['configuration']['version']==case.preparer.REP_FAIR_CONFIG_VERSION
 assert all(item['profile']['schema_version']==fair.PROFILE and item['profile']['sampling_policy_sha256']==fair.POLICY_SHA for item in data['configuration']['campaigns'])
 runtime.verify_successor_assets(case.source,contract=fair,rep_admin_successor=True,first64_512_successor=True,foreground_successor=True,fair_service_successor=True)
 bundle=Path(case.allocation['paths']['binding'])
 for name,value in case.objects['role_records'].items():prior.put(bundle/(name+'.record'),case.controller.canonical(value))
 for name in ('diagnostic_selection','diagnostic_resources'):prior.put(bundle/(name+'.record'),case.controller.canonical(case.objects[name]))
 case.diagnostic.validate_grants(data,bundle)
 case.plan_kwargs['observed_utc']=windows.SIMPLE_WINDOW_START
 plan=case.plan();assert plan['raw_sha256']==prior.helper.sha(case.release)
 fetch=prior.helper.preparation_plan(case.selection_raw,**{k:case.plan_kwargs[k]for k in('selection_sha256','source_sha','job_id')})
 assert fetch['max_external_units']==5
 for family in (case.controller.REP_ACK_VERSION,case.controller.REP_FOREGROUND_VERSION):
  broken=deepcopy(selected);broken['version']=family
  with pytest.raises(RuntimeError):prior.helper.preparation_plan(case.controller.canonical(broken),selection_sha256=case.controller.digest(broken),source_sha=broken['source_sha'],job_id=777)


def test_uncertain_ACK_still_poisoned_and_credit_not_retired(offline,tmp_path,monkeypatch):
 clock=FakeClock();co=coordinator_at(tmp_path,clock);ap=co.ap_sampler;original=io.write;broken=threading.Event()
 def partial(path,raw):
  if path.parent.name=='events'and b'"kind":"SAMPLE_ACK"'in raw:
   original(path,raw[:len(raw)//2]);broken.set();raise OSError(5)
  return original(path,raw)
 monkeypatch.setattr(io,'write',partial)
 try:
  clock.advance(50_000_000);assert broken.wait(1)and co.writer.failed.wait(1)
  with ap.condition:assert ap.condition.wait_for(lambda:ap.failure is not None,timeout=1)
  assert ap.occupied==1 and ap.states[0]==4 and ap.witnessed==0 and not ap.closed
  assert not co.writer.ap_pair_active
  with pytest.raises(sampling.SamplingFailure):ap.close()
  assert not(co.writer.root/'_WRITER_RELEASED.json').exists()
 finally:co.writer.abort()
 assert not co.writer.thread.is_alive()and not ap.thread.is_alive()


@pytest.mark.parametrize('gap,expected',[(-1,'CLOCK_INVALID'),(100_000_000,None),(100_000_001,'ACQUISITION_GAP')])
def test_selected_fair_keeps_inclusive_true_acquisition_and_clock_guards(gap,expected):
 from test_stage12_public_sampling import component
 _,co,_,clock=component();co.contract=fair;ap=sampling.Sampler(co)
 ap.anchor=ap.last_observed=0;clock.value=gap
 ap.health();assert ap.failure==expected


@pytest.mark.parametrize('guard,expected',[('action','WRITE_UNCERTAIN'),('close','DRAIN_EXPIRED')])
def test_selected_fair_five_second_guards_remain(guard,expected):
 from test_stage12_public_sampling import component
 _,co,_,clock=component();co.contract=fair;ap=sampling.Sampler(co)
 ap.anchor=0;clock.value=ap.last_observed=5_000_000_000
 if guard=='action':co.writer.ap_active_started=0
 else:ap.close_requested=0
 ap.health();assert ap.failure==expected


def metadata_allocation():
 from test_stage12_rep_ack_queue import metadata_allocation as base
 from test_stage12_foreground_accounting import FLAGS
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
 value,allocation,preparer=base(True);value['version']=allocation.REP_FAIR_VERSION
 rows=[dict(row,path=row['path'].replace('/s12_ra_g1_rep_ack_contract.py','/s12_ra_g1_rep_fair_contract.py'))for row in value['source_files']]
 rows.sort(key=lambda row:row['path']);value['source_files']=rows
 value['accounting_inventory'],value['accounting']=ac.compile_inventory(rows,value['accounting_inventory']['backends'],allocation.SCOPE,
  foreground_successor=True,fair_service_successor=True,**FLAGS)
 value.pop('rep_ack_policy_adoption');value.pop('rep_ack_policy_adoption_sha256')
 value.update(rep_fair_policy_adoption=fair_adoption(),rep_fair_policy_adoption_sha256=allocation.digest(fair_adoption()))
 return value,allocation,preparer


def test_compiler_family_cost_conservation_and_finite_tail_quote():
 from test_stage12_rep_ack_queue import metadata_allocation as ack_metadata
 from test_stage12_foreground_accounting import FLAGS
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac,s12_public_diagnostics as diagnostics
 old,_,_=ack_metadata(True);value,allocation,preparer=metadata_allocation();inv=value['accounting_inventory']
 assert ac.validate_inventory(inv)==inv
 # Same tiny equal-size fixtures give an exact numeric comparison. Actual
 # released source bytes are independently rebound after all source edits.
 assert inv['accounting']==old['accounting']and inv['stage_accounting']==old['accounting_inventory']['stage_accounting']
 assert tuple(ac.REP_FAIR_FOREGROUND_MEMBERS)==diagnostics.REP_FAIR_FOREGROUND_MODULES
 assert len(inv['rep_foreground']['selected_members'])==14 and inv['rep_foreground']['maximum_passes_per_process']==1
 assert inv['rep_first64_512']==old['accounting_inventory']['rep_first64_512']
 rows=inv['rep_fair_service']['checkpoint_guard_bounds']
 assert sum(row['maximum_pairs']for row in rows)==23448
 assert sum(row['scientific_tail_originals']for row in rows)==46896
 assert sum(row['scientific_tail_valid_original_bytes']for row in rows)==192086016
 assert sum(row['scientific_tail_positive_one_byte_EOF_reads']for row in rows)==192132912
 assert sum(row['scientific_tail_failure_inclusive_returned_bytes']for row in rows)==192132912
 assert all(row['charged_source_check_call_delta']==row['charged_source_original_read_call_delta']==0 for row in rows)
 assert not any(row['component'].endswith('CHECKPOINT_GUARDS')for row in inv['cost_rows'])
 for wrong in (ac.REP_ACK_VERSION,ac.REP_FOREGROUND_VERSION):
  damaged=deepcopy(inv);damaged['schema_version']=wrong
  with pytest.raises(ac.AccountingError):ac.validate_inventory(damaged)
 with pytest.raises(ac.AccountingError):ac.compile_inventory(inv['sources'],inv['backends'],allocation.SCOPE,
  foreground_successor=True,ack_queue_successor=True,fair_service_successor=True,**FLAGS)
 selected=preparer.resource_selection(value,policy_sha256=fair.digest(fair.descriptors()[assurance.POLICY]),
  adoption_sha256=H,descriptor_inventory_sha256=H,graph_sha256=H,paths_sha256=H,implementation_review_sha256=H)
 assert selected['schema_version']==assurance.REP_FAIR_SELECTION
 assert selected['limits']['creations']==204860 and selected['limits']['logical_write_bytes']==72*2**30
 assert selected['limits']['application_counters']['EVENT_FILE']==57237
 assert selected['limits']['application_counters']['EXCLUSIVE_FILE']==204860
 from test_stage12_ra_g1_rep_admin_budget import diagnostic
 diagnostic.validate_resource_family(diagnostic.REP_FAIR_VERSION,selected)
 for wrong in (diagnostic.REP_ACK_VERSION,diagnostic.REP_FOREGROUND_VERSION):
  with pytest.raises(RuntimeError):diagnostic.validate_resource_family(wrong,selected)


def test_terminal_original_reader_selects_only_exact_family(tmp_path):
 import stage12_ra_g1_terminal_verify as verifier
 assert verifier.workload_contract(dict(scope='REPRESENTATIVE_NO_SERVICE',version='stage12_ra_g1_rep_fair_service_allocation_selection_v1'))is fair
 assert verifier.workload_contract(dict(scope='REPRESENTATIVE_NO_SERVICE',version='stage12_ra_g1_rep_ack_queue_allocation_selection_v1'))is ack
 selection=dict(scope='REPRESENTATIVE_NO_SERVICE',version='stage12_ra_g1_rep_fair_service_allocation_selection_v1',source_sha='a'*40,paths=dict(output=str(tmp_path/'absent'),source=str(tmp_path/'source'),tail=str(tmp_path/'tail')))
 report=verifier.verify_original_workload(selection,check=lambda:None,charge_read=lambda _:None)
 assert report['schema']==verifier.FAIR_VERSION and report['sampling_policy_sha256']==fair.POLICY_SHA
 assert report['sampling_policy_version']==fair.POLICY_VERSION and report['complete']is False and report['status']=='ORIGINAL_WORKLOAD_INCOMPLETE'
 for version in (fair.PROFILE,'UNKNOWN'):
  with pytest.raises(RuntimeError):verifier.workload_contract(dict(scope='REPRESENTATIVE_NO_SERVICE',version=version))


def test_fair_direct_gate_reuses_exact_old_integrity_without_relabelling(tmp_path):
 """Retained metadata rehearsal; synthetic current source/window, no activation."""
 import stage12_ra_g1_environment_launch as gate
 import stage12_ra_g1_terminal_verify as verifier
 import stage12_ra_g1_direct_recovery as direct
 from test_stage12_handoff_execution_window import retained_bytes
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows,s12_ra_g1_accounting as ac
 from test_stage12_foreground_accounting import FLAGS
 original=json.loads(retained_bytes('STAGE12_HANDOFF_RETAINED_Q2',windows.Q2_BUNDLE,65536))
 proof=json.loads(retained_bytes('STAGE12_FAIR_RETAINED_DIRECT_RESULT','fa7006c0ec54d4aee8b33695c35d82f72acaf54522b9525402072f0e897f349c',65536))
 review=json.loads(retained_bytes('STAGE12_FAIR_RETAINED_DIRECT_REVIEW','44066a78243e12d408628ee495b8afa735c2572bf0748c696988f21086dc56af',65536))
 selected,allocation,_=metadata_allocation()
 window=dict(version=windows.SIMPLE_WINDOW_VERSION,scope=allocation.SCOPE,valid_from=windows.SIMPLE_WINDOW_START,
  valid_until=windows.SIMPLE_WINDOW_END,policy_sha256=windows.digest(windows.simple_descriptor()),owner_authority_sha256=H,grant_nonce=H)
 old=selected['rep_admin_budget_adoption']
 selected['rep_admin_budget_adoption']=dict(schema_version=windows.SIMPLE_WINDOW_ADOPTION,scope=allocation.SCOPE,window=window,
  original_adoption=old,original_adoption_sha256=gate.digest(old),grant_kind=windows.REP_GRANT,maximum_submissions=1,
  qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW,
  historical_grant_consumed=True,original_budget_terms_unchanged=True)
 selected.update(valid_from=window['valid_from'],valid_until=window['valid_until'],resource_selection_sha256=H,
  records=dict(selected['records'],software_review=H,resource_review=H))
 rows={row['path']:row for row in selected['source_files']};repo=Path(__file__).resolve().parents[1]
 for name in (*gate.REQUIRED_SOURCE,gate.COLLECTION_DOCUMENT,*gate.DIRECT_CONSUMER_PATHS,
  'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_rep_fair_contract.py'):
  raw=(repo/name).read_bytes();rows[name]=dict(path=name,bytes=len(raw),sha256=__import__('hashlib').sha256(raw).hexdigest())
 selected['source_files']=sorted(rows.values(),key=lambda row:row['path'])
 selected['accounting_inventory'],selected['accounting']=ac.compile_inventory(selected['source_files'],selected['accounting_inventory']['backends'],allocation.SCOPE,
  foreground_successor=True,fair_service_successor=True,**FLAGS)
 binding=dict(version=gate.FAIR_DIRECT_COLLECTION_BINDING,source_tree='c'*40,**{key:H for key in gate.DIRECT_BINDING_HASHES},
  remote_directory_scope=gate.REMOTE_DIRECTORY_SCOPE,transport_evidence_version=gate.REMOTE_TRANSPORT_VERSION,remote_directory_adoption_sha256=H,
  direct_recovery_software_source_sha=proof['software_source_sha'])
 binding.update(policy_sha256=gate.digest(gate.direct_collection_descriptor(fair_service_successor=True)),amendment_sha256=rows[gate.COLLECTION_DOCUMENT]['sha256'],
  window_policy_sha256=window['policy_sha256'],owner_authority_sha256=H,qualification_bundle_sha256=windows.Q2_BUNDLE,
  qualification_review_sha256=windows.Q2_REVIEW,direct_recovery_plan_sha256=proof['plan_sha256'],direct_recovery_result_sha256=gate.digest(proof),
  direct_recovery_review_sha256=gate.digest(review),direct_recovery_software_inventory_sha256=proof['software_inventory_sha256'],
  direct_recovery_consumer_inventory_sha256=proof['recovery_consumer_inventory_sha256'])
 current=[rows[name]for name in sorted(gate.DIRECT_CONSUMER_PATHS)]
 prior={row['path']:row for row in proof['recovery_consumer_inventory']}
 compatibility=dict(version=gate.FAIR_COMPATIBILITY_VERSION,current_source_sha=selected['source_sha'],
  current_source_inventory_sha256=selected['accounting_inventory']['source_inventory_sha256'],old_result_sha256=gate.digest(proof),
  old_review_sha256=gate.digest(review),old_source_sha=proof['software_source_sha'],old_consumer_inventory_sha256=proof['recovery_consumer_inventory_sha256'],
  current_consumer_inventory=current,changed_paths=sorted(row['path']for row in current if row!=prior[row['path']]),focused_compatibility_review_sha256=H)
 assert compatibility['changed_paths']==sorted(gate.FAIR_COMPATIBILITY_ALLOWED_CHANGED)
 binding.update(direct_recovery_consumer_compatibility=compatibility,direct_recovery_consumer_compatibility_sha256=gate.digest(compatibility))
 value=dict(version=gate.FAIR_DIRECT_COLLECTION_VERSION,scope=allocation.SCOPE,state='ISSUED_FOR_DIRECT_RECOVERY_REVIEWED_REP_FAIR_DIAGNOSTIC',
  source_git_sha=selected['source_sha'],source_tree=binding['source_tree'],
  **{key:binding[key]for key in(*gate.DIRECT_BINDING_HASHES,*gate.REMOTE_COLLECTION_FIELDS,gate.DIRECT_SOFTWARE_FIELD,*gate.FAIR_COMPATIBILITY_FIELDS)},
  selection_sha256=gate.selection_digest(selected),resource_selection_sha256=H,software_review_sha256=H,resource_review_sha256=H,
  source_inventory_sha256=selected['accounting_inventory']['source_inventory_sha256'],valid_from=window['valid_from'],valid_until=window['valid_until'],
  outer_window_end=window['valid_until'],window=window,grant_kind=windows.REP_GRANT,maximum_submissions=1,task_profiling='DISABLED',budget=gate.DIRECT_BUDGET,history=gate.DIRECT_HISTORY)
 now=windows.epoch_ns(window['valid_until'])-11220*10**9
 kwargs=dict(now_epoch_ns=now,qualification=original,qualification_validator=verifier.validate_qualification,
  direct_recovery=proof,direct_review=review,direct_validator=direct.validate_recovery_proof)
 result=gate.validate_gate(value,selected,binding,**kwargs)
 assert not result['native_timing_PASS']and result['required_remaining_ns']==11220*10**9
 for wrong in ('mixed_binding','mixed_allocation','mixed_gate','changed_source','old_proof','unknown_path','omitted_change','compat_hash','unknown_field'):
  b,v,sel=deepcopy(binding),deepcopy(value),deepcopy(selected)
  if wrong=='mixed_binding':b['version']=gate.DIRECT_COLLECTION_BINDING
  elif wrong=='mixed_allocation':sel['version']=allocation.REP_ACK_VERSION
  elif wrong=='mixed_gate':v['version']=gate.DIRECT_COLLECTION_VERSION
  else:
   cx=b['direct_recovery_consumer_compatibility']
   if wrong=='changed_source':cx['current_source_sha']='f'*40
   elif wrong=='old_proof':cx['old_result_sha256']=H
   elif wrong=='unknown_path':cx['changed_paths'].append('scripts/unselected.py')
   elif wrong=='omitted_change':cx['changed_paths']=[]
   elif wrong=='unknown_field':cx['unsafe']=True
   if wrong!='compat_hash':b['direct_recovery_consumer_compatibility_sha256']=gate.digest(cx)
   else:b['direct_recovery_consumer_compatibility_sha256']=H
   for key in gate.FAIR_COMPATIBILITY_FIELDS:v[key]=deepcopy(b[key])
  with pytest.raises(RuntimeError):gate.validate_gate(v,sel,b,**kwargs)
 with pytest.raises(RuntimeError):gate.validate_gate(value,selected,binding,**dict(kwargs,now_epoch_ns=now+1))

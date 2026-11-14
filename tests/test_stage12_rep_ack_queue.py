"""Representative-only ACK queue policy; invented facts, no provider/native work."""
from copy import deepcopy
import importlib.util,json,threading,time,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from test_stage12_public_operations_v2 import FakeClock,H,offline # noqa:F401
from test_stage12_ra_g1_integration import ra_inputs,SyntheticAuthority
from test_s12_ra_g1_core import binding,capacity
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_ack_contract as rep
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as strict
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler
from safe_geocoding_pipeline.preprocessing.stages import s12_public_journal as journal
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))


def selected_inputs(wire,clock):
 p,pl,s,old_record,selected,work,inventory=ra_inputs()
 if wire is strict:
  return p,pl,s,SyntheticAuthority(p,pl,s,old_record,selected,work,clock)
 # Portable source-owned structural fixture. Kernel, service/source/date and
 # authorities below are explicitly invented TEST_ONLY facts.
 from test_stage12_ra_g1_rep_first64_512 import selected as synthetic_rep512
 selected=synthetic_rep512()
 selected.update(schema_version=assurance.REP_ACK_SELECTION,source_git_sha=s['client_git_sha'],
  valid_from=old_record['valid_from'],valid_until=old_record['valid_until'],
  rep_ack_policy_sha256=rep.POLICY_SHA,rep_ack_policy_adoption_sha256=H)
 assurance.validate_selection(selected)
 record=binding(selected)
 record.update(source_git_sha=s['client_git_sha'],runtime_inventory_sha256=rep.digest(inventory),
  maximum_identity_checks=100000,policy_sha256=selected['policy_sha256'],adoption_sha256=selected['adoption_sha256'])
 p['resources'].update(resource_selection_sha256=rep.digest(selected),initial_capacity_observation_sha256=rep.digest(capacity(selected)))
 p.update(schema_version=rep.PROFILE,rule_bundle_sha256=rep.RULE_BUNDLE,sampling_policy_sha256=rep.POLICY_SHA,sampling_runtime_bound_sha256=rep.digest(record))
 pl.update(schema_version=rep.PLAN,operations_profile_sha256=rep.digest(p))
 s.update(schema_version=rep.START,profile_sha256=rep.digest(p),plan_sha256=rep.digest(pl),rule_bundle_sha256=rep.RULE_BUNDLE,sampling_policy_sha256=rep.POLICY_SHA)
 authority=SyntheticAuthority(p,pl,s,record,selected,work,clock)
 authority.diagnostic_scope='REPRESENTATIVE_NO_SERVICE';authority.service_authority=False
 return p,pl,s,authority


@pytest.mark.parametrize('wire',[strict,rep],ids=['legacy_strict','selected_representative'])
def test_real_writer_700ms_delay_policy_is_selected_and_originals_reopened(offline,tmp_path,monkeypatch,wire):
 clock=FakeClock();p,pl,s,authority=selected_inputs(wire,clock)
 entered,returned=threading.Event(),threading.Event();timing={};original_write=journal.io.write
 def delayed(path,raw):
  if not entered.is_set()and path.parent.name=='events'and b'"kind":"RESOURCE_SAMPLE"'in raw:
   timing['entry_wall_ns']=time.monotonic_ns();entered.set();time.sleep(.7)
   result=original_write(path,raw);timing['returned_wall_ns']=time.monotonic_ns();returned.set();return result
  return original_write(path,raw)
 monkeypatch.setattr(journal.io,'write',delayed)
 co=scheduler.Coordinator(p,pl,s,authority=authority,clock=clock,root=tmp_path/'run',block_id=1,
  segment_authority=H,writer_exclusion_evidence=H,epoch=H,free_bytes=lambda:2**42,contract=wire)
 ap=co.ap_sampler;closed=None;released=False
 try:
  clock.advance(50_000_000);assert entered.wait(1)
  with ap.lock:initial=ap.acquired
  for target in range(100_000_000,701_000_000,50_000_000):
   clock.advance(target-clock.now_ns());end=time.monotonic()+.025
   while co.last_sample_ns<target and ap.failure is None and time.monotonic()<end:time.sleep(.001)
  if wire is strict:assert ap.failure=='ACK_AGE_LIMIT'
  else:
   assert ap.failure is None and co._sampling_gate()is True
   assert ap.acquired-initial>=10 and ap.occupied<=16 and ap.maximum_gap<=100_000_000
  assert returned.wait(1);time.sleep(.03)
  if wire is rep:
   with ap.condition:
    assert ap.condition.wait_for(lambda:ap.witnessed==ap.acquired and ap.occupied==0,timeout=1)
   # The controlled clock must distinguish the post-drain FINAL from earlier
   # ACKheaders; native clocks are not replaced or backdated by this fixture.
   clock.advance(1)
   closed=ap.close();co.writer.release(dict(scope='TEST_ONLY_SAMPLER_WRITER',scientific_pass=False));released=True
   assert closed['result']=='COMPLETE'and ap.maximum_age>500_000_000
   events=list(journal.read_events(tmp_path/'run',rep.digest(s),contract=rep))
   summaries=sampling.inspect(lambda:iter(events),p,s,maximum_segments=1,contract=rep)
   assert summaries[0]['complete']is True and summaries[0]['maximum_ack_age_ns']==ap.maximum_age
   samples={e['body']['observation']['acquisition_seq']:e for e in events if e['kind']=='RESOURCE_SAMPLE'}
   acks=[e for e in events if e['kind']=='SAMPLE_ACK'];assert len(samples)==len(acks)==ap.witnessed
   for ack in acks:
    b=ack['body'];sample=samples[b['acquisition_seq']]
    assert sample['seq']<ack['seq']and b['sample_event_sha256']==rep.digest(sample)
    assert b['observation_sha256']==rep.digest(sample['body']['observation'])
   with pytest.raises(c.Stage12Error):sampling.inspect(lambda:iter(events),p,s,maximum_segments=1,contract=strict)
   # The selected policy withdraws age acceptance, never ACK completeness or
   # association/terminal requirements in the independent original reader.
   first_ack=next(e['seq']for e in events if e['kind']=='SAMPLE_ACK')
   for missing in ('SAMPLE_ACK','SAMPLING_CLOSE'):
    damaged=[e for e in events if not(e['kind']==missing and (missing!='SAMPLE_ACK'or e['seq']==first_ack))]
    try:rejected=sampling.inspect(lambda:iter(damaged),p,s,maximum_segments=1,contract=rep)
    except c.Stage12Error:pass
    else:assert rejected and not all(row['complete']for row in rejected)
   damaged=deepcopy(events);ack=next(e for e in damaged if e['kind']=='SAMPLE_ACK');ack['body']['observation_sha256']=H
   with pytest.raises(c.Stage12Error):sampling.inspect(lambda:iter(damaged),p,s,maximum_segments=1,contract=rep)
  result=dict(scope='TEST_ONLY_ACTUAL_SAMPLER_WRITER_ORIGINALS',wire=wire.POLICY_VERSION,
   maximum_ack_age_ns=ap.maximum_age,maximum_gap_ns=ap.maximum_gap,acquired=ap.acquired,witnessed=ap.witnessed,
   failure=ap.failure,closed=closed,released=released,timing=timing,attempts=0,native_qualification=False)
  (tmp_path/'OBSERVED.record').write_bytes(c.canonical(result));(tmp_path/'OBSERVED.record').chmod(0o600)
 finally:
  if not released:co.writer.abort()
 assert not co.writer.thread.is_alive()and not ap.thread.is_alive()
 assert timing['returned_wall_ns']-timing['entry_wall_ns']>=700_000_000


def test_closed_policy_and_public_family_boundaries():
 rep.validate(rep.POLICY,rep.POLICY_VERSION);strict.validate(strict.POLICY,strict.POLICY_VERSION)
 assert sampling.maximum_ack_age_ns(rep)is None and sampling.maximum_ack_age_ns(strict)==500_000_000
 fake=SimpleNamespace(POLICY=dict(strict.POLICY,maximum_unacknowledged_age_ms=None),require=c.require)
 with pytest.raises(c.Stage12Error):sampling.maximum_ack_age_ns(fake)
 assert runtime.sampling_contract(dict(schema_version=rep.PROFILE))is rep
 assert runtime.sampling_contract(dict(schema_version=strict.PROFILE))is strict
 assert rep.CONFIG not in runtime.WF_CONFIGS and rep.CONFIG not in runtime.SAMPLING_CONFIGS
 with pytest.raises(c.Stage12Error):runtime.validate_config(dict(version=rep.CONFIG))


def test_new_policy_cannot_remove_16_slot_backlog_limit():
 from test_stage12_public_sampling import component
 _,co,_,_=component();co.contract=rep;ap=sampling.Sampler(co)
 for i in range(16):
  assert ap._reserve()==(i,i+1);ap.owner_busy=False;ap.states[i]=2
 assert ap._reserve()is None and ap.failure=='OBSERVATION_COUNT_LIMIT'and ap.occupied==16
 assert len(ap.arena)==32768 and rep.POLICY['reserved_bytes_per_observation']==4096


def test_uncertain_ACK_write_is_still_incomplete(offline,tmp_path,monkeypatch):
 clock=FakeClock();p,pl,s,authority=selected_inputs(rep,clock)
 original=journal.io.write;broken=threading.Event()
 def partial(path,raw):
  if path.parent.name=='events'and b'"kind":"SAMPLE_ACK"'in raw:
   original(path,raw[:len(raw)//2]);broken.set();raise OSError(5)
  return original(path,raw)
 monkeypatch.setattr(journal.io,'write',partial)
 co=scheduler.Coordinator(p,pl,s,authority=authority,clock=clock,root=tmp_path/'run',block_id=1,
  segment_authority=H,writer_exclusion_evidence=H,epoch=H,free_bytes=lambda:2**42,contract=rep)
 try:
  clock.advance(50_000_000);assert broken.wait(1)and co.writer.failed.wait(1)
  with co.ap_sampler.condition:assert co.ap_sampler.condition.wait_for(lambda:co.ap_sampler.failure is not None,timeout=1)
  ap=co.ap_sampler
  assert ap.occupied==1 and ap.states[0]==4 and ap.witnessed==0 and not ap.closed
  with pytest.raises(sampling.SamplingFailure):ap.close()
  with pytest.raises((ValueError,c.Stage12Error)):list(journal.read_events(tmp_path/'run',rep.digest(s),contract=rep))
  assert not(tmp_path/'run/_WRITER_RELEASED.json').exists()
 finally:co.writer.abort()
 assert not co.writer.thread.is_alive()and not co.ap_sampler.thread.is_alive()


def component_rep():
 from test_stage12_public_sampling import component
 _,co,log,clock=component();co.contract=rep;ap=sampling.Sampler(co)
 ap.anchor=ap.last_observed=0;ap.owner_ident=threading.get_ident();ap.head=ap.association=H
 return ap,co,log,clock


@pytest.mark.parametrize('gap,expected',[(-1,'CLOCK_INVALID'),(100_000_000,None),(100_000_001,'ACQUISITION_GAP')])
def test_new_policy_keeps_true_clock_and_inclusive_acquisition_guards(gap,expected):
 ap,co,_,clock=component_rep();clock.value=gap;ap.health();assert ap.failure==expected


@pytest.mark.parametrize('guard,expected',[('cumulative','DRAIN_EXPIRED'),('action','WRITE_UNCERTAIN'),('close','DRAIN_EXPIRED')])
def test_new_policy_keeps_cumulative_and_five_second_guards(guard,expected):
 ap,co,_,clock=component_rep();clock.value=5_000_000_000;ap.last_observed=clock.value
 if guard=='cumulative':ap.deadline_ns=clock.value
 elif guard=='action':co.writer.ap_active_started=0
 else:ap.close_requested=0
 ap.health();assert ap.failure==expected


def test_actual_new_caller_report_and_reopening_are_matched(offline,tmp_path):
 from test_stage12_public_sampling_integration import RealClock
 from stage12_synthetic import body,feature
 from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
 from safe_geocoding_pipeline.preprocessing.stages import s12_transport as transport
 from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
 from test_stage12_public_operations_v2 import KEY
 clock=RealClock();p,pl,s,authority=selected_inputs(rep,clock);calls=[]
 def invented_dispatch(work,target,hooks):
  hooks.started(clock.now_ns());hooks.emit(lambda:None,lambda:None);calls.append(work['work_id'])
  raw=body([feature()]);capture=transport.Capture('VALIDATION_REQUIRED','OK',200,'application/json','identity',None,raw,len(raw),1)
  hooks.completed(capture);return capture
 report=cli.run_operations_block(p,pl,s,work_factory=lambda:iter(authority.rows),output=tmp_path/'phase',block_id=1,
  authority=authority,clock=clock,dispatch=invented_dispatch,runtime_inventory=json.loads(c.canonical(__import__('test_stage12_ra_g1_integration').ra_inputs()[-1])),runtime_key=KEY,
  control_adapters={},monitor=None,free_bytes=lambda:2**40,segment_authority=H,writer_exclusion_evidence=H,
  epoch='1'*64,writer_release_evidence=H,public_validation=Validation(),task_deadline_ns=clock.now_ns()+180*10**9)
 assert calls==[1,2]and report['schema_version']==rep.REPORT and report['report_complete']is True
 assert runtime.reopen_completed(tmp_path/'phase',p,pl,s,validation_sha256=rep.digest(Validation().descriptor()))==report['blocks'][0]
 # This tiny invented programmatic fixture does not run selected512/T3/hold.
 assert report['sampling_segments']and all(x['complete']for x in report['sampling_segments'])


def policy_adoption():
 return dict(schema_version=assurance.REP_ACK_ADOPTION,scope='REPRESENTATIVE_NO_SERVICE',policy_sha256=rep.POLICY_SHA,
  decision_delta_sha256=H,prospective_only=True,withdrawn_maximum_ack_age_ms=500,actual_ack_age_retained=True,
  maximum_outstanding_observations=16,maximum_writer_action_ms=5000,maximum_close_ms=5000)


def metadata_allocation(new=True):
 from test_stage12_foreground_accounting import inputs,FLAGS
 from test_s12_ra_g1_bootstrap30 import bootstrap_inputs
 from test_stage12_ra_g1_rep_admin_budget import allocation,preparer,synthetic_adoption as admin
 from test_stage12_ra_g1_rep_first64_512 import synthetic_adoption as first64
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
 rows,back=inputs()
 if new:
  for row in rows:
   if row['path'].endswith('/s12_ra_g1_contract.py'):row['path']=row['path'].replace('/s12_ra_g1_contract.py','/s12_ra_g1_rep_ack_contract.py')
  rows.sort(key=lambda r:r['path'])
 inv,total=ac.compile_inventory(rows,back,allocation.SCOPE,foreground_successor=True,**FLAGS,**({'ack_queue_successor':True}if new else {}))
 _,prefix,_=bootstrap_inputs()
 value=dict(version=allocation.REP_ACK_VERSION if new else allocation.REP_FOREGROUND_VERSION,
  scope=allocation.SCOPE,source_files=rows,source_sha='2'*40,accounting_inventory=inv,accounting=total,
  valid_from='2026-01-01T00:00:00.000000Z',valid_until='2026-01-02T00:00:00.000000Z',
  bootstrap_prefix_adoption=prefix,bootstrap_prefix_adoption_sha256=allocation.digest(prefix),
  rep_admin_budget_adoption=admin(),rep_admin_budget_adoption_sha256=allocation.digest(admin()),
  rep_first64_512_adoption=first64(),rep_first64_512_adoption_sha256=allocation.digest(first64()),
  paths=dict(source=str(ROOT)),records=dict(adoption=H))
 if new:value.update(rep_ack_policy_adoption=policy_adoption(),rep_ack_policy_adoption_sha256=allocation.digest(policy_adoption()))
 return value,allocation,preparer


@pytest.mark.parametrize('new',[False,True],ids=['strict_foreground','ACK_queue'])
def test_actual_uncached_controller_resource_selection_and_exact_families(new):
 value,allocation,preparer=metadata_allocation(new)
 selected_contract=preparer.contract_for_allocation(value)
 selected=preparer.resource_selection(value,policy_sha256=selected_contract.digest(selected_contract.descriptors()[assurance.POLICY]),
  adoption_sha256=H,descriptor_inventory_sha256=H,graph_sha256=H,paths_sha256=H,implementation_review_sha256=H)
 value['resource_selection_sha256']=allocation.digest(selected)
 class FixtureRun:
  s=value
  selected_resource=None
  def record(self,role):
   return dict(descriptor_inventory_sha256=H,workload_graph_sha256=H,paths_sha256=H)if role=='resource_review'else dict(report_sha256=H)
 run=FixtureRun();actual=allocation.resource_selection(run)
 assert actual==selected and run.selected_resource is actual
 assert actual['schema_version']==(assurance.REP_ACK_SELECTION if new else assurance.REP_FOREGROUND_SELECTION)
 from test_stage12_ra_g1_rep_admin_budget import diagnostic
 diagnostic.validate_resource_family(diagnostic.REP_ACK_VERSION if new else diagnostic.REP_FOREGROUND_VERSION,actual)
 with pytest.raises(RuntimeError):diagnostic.validate_resource_family(diagnostic.REP_FOREGROUND_VERSION if new else diagnostic.REP_ACK_VERSION,actual)
 assert preparer.contract_for_allocation(value)is(rep if new else strict)


def test_compiler_counter_model_map_members_and_legacy_assets():
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac,s12_public_diagnostics as diagnostics
 from test_stage12_foreground_accounting import inputs,FLAGS,LEGACY_GOLDEN
 rows,back=inputs()
 # Genuine old family compiler bytes remain exact for all frozen golden cases.
 for name,scope,flags in [('strict_rep',ac.SCOPES[0],{}),('bootstrap_rep',ac.SCOPES[0],dict(bootstrap_successor=True)),
  ('shared_rep',ac.SCOPES[0],dict(shared_lease_successor=True)),('admin_rep',ac.SCOPES[0],dict(bootstrap_successor=True,shared_lease_successor=True,rep_admin_successor=True)),
  ('rep512',ac.SCOPES[0],FLAGS),('public_shared',ac.SCOPES[1],dict(shared_lease_successor=True))]:
  inv,_=ac.compile_inventory(rows,back,scope,**flags);assert ac.digest(inv)==LEGACY_GOLDEN[name]
 for name,value in strict.descriptors(rep_admin_successor=True,first64_512_successor=True,foreground_successor=True).items():
  assert(ROOT/'docs/scientific_assets'/(name+'.json')).read_bytes()==c.canonical(value)
 value,_,_=metadata_allocation(True);inv=value['accounting_inventory'];ac.validate_inventory(inv)
 assert tuple(ac.REP_ACK_FOREGROUND_MEMBERS)==diagnostics.REP_ACK_FOREGROUND_MODULES
 assert len(inv['rep_foreground']['selected_members'])==14 and inv['rep_foreground']['maximum_source_bytes']==2**20
 one=[r for r in inv['cost_rows']if r['component']=='REP_FOREGROUND_ONCE_SELECTED_SOURCE_MAP'];assert len(one)==1 and one[0]['stage_id']==1 and one[0]['invocations']==1
 actual=inv['rep_foreground'];R=actual['selected_source_bytes']+14
 assert one[0]['original_read_calls']==one[0]['original_read_bytes']==R
 assert one[0]['check_calls']==8*R+4*actual['selected_internal_parent_entries']+272*14
 assert len([r for r in inv['cost_rows']if r['component'].startswith('REP_ACK_ADOPTION')])==9
 direct=[r for r in inv['cost_rows']if r['component']=='REP_ACK_DIRECT_GATE_FRESH_PROOF_REVIEW_AND_VALIDATOR'];assert len(direct)==1 and direct[0]['stage_id']==6 and direct[0]['invocations']==2
 assert direct[0]['original_read_calls']==2*(2**20+65536+131072+3)
 assert inv['rep_first64_512']==ac.compile_inventory(rows,back,ac.SCOPES[0],**FLAGS)[0]['rep_first64_512']
 for family in (ac.REP_FOREGROUND_VERSION,ac.REP512_VERSION):
  changed=deepcopy(inv);changed['schema_version']=family
  with pytest.raises(ac.AccountingError):ac.validate_inventory(changed)
 changed=deepcopy(inv);changed['rep_ack_policy_sha256']=strict.POLICY_SHA
 with pytest.raises(ac.AccountingError):ac.validate_inventory(changed)
 for missing in (*FLAGS,'foreground_successor'):
  flags=dict(FLAGS,foreground_successor=True,ack_queue_successor=True);flags[missing]=False
  with pytest.raises(ac.AccountingError):ac.compile_inventory(inv['sources'],back,ac.SCOPES[0],**flags)
 for scope in ac.SCOPES[1:]:
  with pytest.raises(ac.AccountingError):ac.compile_inventory(inv['sources'],back,scope,foreground_successor=True,ack_queue_successor=True,**FLAGS)


# Actual builder/handoff fixtures use private source copies and invented records;
# no shell is run and no produced enum is an execution/reviewer authorization.
from test_stage12_ra_g1_production_binding import private_source,production # noqa:E402,F401


def ack_upgrade(value):
 from test_stage12_foreground_accounting import upgrade as foreground_upgrade,FLAGS
 from test_stage12_ra_g1_rep_admin_budget import allocation
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac,s12_ra_g1_windows as windows
 result=foreground_upgrade(value);result['version']=allocation.REP_ACK_VERSION
 original=result['rep_admin_budget_adoption'];original_hash=allocation.digest(original)
 window=dict(version=windows.SIMPLE_WINDOW_VERSION,scope=allocation.SCOPE,valid_from=windows.SIMPLE_WINDOW_START,valid_until=windows.SIMPLE_WINDOW_END,
  policy_sha256=windows.digest(windows.simple_descriptor()),owner_authority_sha256=H,grant_nonce=H)
 result.update(valid_from=window['valid_from'],valid_until=window['valid_until'])
 result['rep_admin_budget_adoption']=dict(schema_version=windows.SIMPLE_WINDOW_ADOPTION,scope=allocation.SCOPE,
  window=window,original_adoption=original,original_adoption_sha256=original_hash,grant_kind=windows.REP_GRANT,maximum_submissions=1,
  qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW,historical_grant_consumed=True,original_budget_terms_unchanged=True)
 result['rep_admin_budget_adoption_sha256']=allocation.digest(result['rep_admin_budget_adoption'])
 result['rep_ack_policy_adoption']=policy_adoption();result['rep_ack_policy_adoption_sha256']=allocation.digest(policy_adoption())
 result['accounting_inventory'],result['accounting']=ac.compile_inventory(result['source_files'],result['accounting_inventory']['backends'],allocation.SCOPE,
  foreground_successor=True,ack_queue_successor=True,**FLAGS)
 return result


def test_actual_builder_new_initializer_assets_grants_and_publication_boundary(production,monkeypatch):
 import test_stage12_ra_g1_review_handoff as prior
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
 production.bootstrap['created_utc']=windows.SIMPLE_WINDOW_START
 monkeypatch.setattr(prior,'upgrade',ack_upgrade)
 case=prior.handoff.__wrapped__(production)
 data=case.controller.parse(case.originals['input']);selected=case.controller.parse(case.selection_raw)
 assert selected['version']==case.controller.REP_ACK_VERSION and data['version']==case.diagnostic.REP_ACK_VERSION
 case.controller.validate_selection(selected)
 case.diagnostic.validate_envelope(data,selected['source_sha'],for_execution=True)
 case.diagnostic.validate_workloads(data)
 assert data['configuration']['version']==case.preparer.REP_ACK_CONFIG_VERSION
 assert all(item['profile']['schema_version']==rep.PROFILE and item['profile']['sampling_policy_sha256']==rep.POLICY_SHA for item in data['configuration']['campaigns'])
 # The actual selected local initializer begins with these real source calls.
 runtime.verify_successor_assets(case.source,contract=rep,rep_admin_successor=True,first64_512_successor=True,foreground_successor=True,ack_queue_successor=True)
 bundle=Path(case.allocation['paths']['binding'])
 for name,value in case.objects['role_records'].items():prior.put(bundle/(name+'.record'),case.controller.canonical(value))
 for name in ('diagnostic_selection','diagnostic_resources'):prior.put(bundle/(name+'.record'),case.controller.canonical(case.objects[name]))
 case.diagnostic.validate_grants(data,bundle)
 # Publication uses a genuine exact produced input and fixture sealed bytes.
 case.plan_kwargs['observed_utc']=windows.SIMPLE_WINDOW_START
 plan=case.plan();assert plan['raw_sha256']==prior.helper.sha(case.release)
 fetch=prior.helper.preparation_plan(case.selection_raw,**{k:case.plan_kwargs[k]for k in('selection_sha256','source_sha','job_id')})
 assert fetch['max_external_units']==5 and plan['max_external_units']==11
 for changes in ({'rep_ack_policy_adoption_sha256':H},{'accounting_inventory':deepcopy(selected['accounting_inventory'])}):
  bad=deepcopy(selected)
  if 'accounting_inventory'in changes:bad['accounting_inventory']['schema_version']='stage12_ra_g1_rep_foreground_accounting_inventory_v1'
  else:bad.update(changes)
  with pytest.raises((RuntimeError,c.Stage12Error)):case.controller.validate_selection(bad)


@pytest.mark.parametrize("new", [False, True], ids=["legacy_strict", "selected_ACK_queue"])
def test_actual_native_original_verifier_contract_and_incomplete_disposition(tmp_path,new):
 import stage12_ra_g1_terminal_verify as verifier
 root=tmp_path/"native_original";root.mkdir(mode=0o700)
 selection=dict(version="stage12_ra_g1_rep_ack_queue_allocation_selection_v1" if new else "stage12_ra_g1_rep_first64_512_allocation_selection_v1",
  scope="REPRESENTATIVE_NO_SERVICE",source_sha="2"*40,paths=dict(output=str(root),tail=str(root/"tail.record"),source=str(ROOT)))
 wire=rep if new else strict
 assert verifier.workload_contract(selection)is wire
 report=verifier.verify_original_workload(selection,check=lambda:None,charge_read=lambda amount:None,
  check_read=lambda amount:(_ for _ in()).throw(AssertionError("missing originals must not be read")))
 assert report["complete"]is False and report["schema"]==(verifier.ACK_VERSION if new else verifier.VERSION)
 assert report["status"]=="ORIGINAL_WORKLOAD_INCOMPLETE" and not report["original_timed_acceptance_repaired"]
 for version in ("stage12_ra_g1_rep_foreground_allocation_selection_v1","UNKNOWN",rep.PROFILE):
  with pytest.raises(RuntimeError):verifier.workload_contract(dict(selection,version=version))
 with pytest.raises(RuntimeError):verifier.workload_contract(dict(selection,scope="PUBLIC_SYNTHETIC_ONLY"))


def test_native_verifier_shares_pre_read_budget_without_reset_or_read_after_rejection(tmp_path):
 import os
 import stage12_ra_g1_terminal_verify as verifier
 path=tmp_path/"ORIGINAL";path.write_bytes(b"abcdef")
 checks=[];charges=[];fd=os.open(path,os.O_RDONLY)
 def before(amount):
  checks.append((amount,os.lseek(fd,0,os.SEEK_CUR)))
  if len(checks)==3:raise RuntimeError("TEST_ONLY_SHARED_EXPORT_READ_STOP")
 try:
  with verifier.bounded_reads(lambda:None,charges.append,check_read=before)as counts:
   assert os.read(fd,2)==b"ab"
   assert os.pread(fd,1,4)==b"e"
   with pytest.raises(RuntimeError,match="TEST_ONLY_SHARED_EXPORT_READ_STOP"):os.readv(fd,[bytearray(2)])
   assert os.lseek(fd,0,os.SEEK_CUR)==2
  assert checks==[(2,0),(1,2),(2,2)] and charges==[2,1]
  assert counts==dict(read_calls=3,returned_bytes=3,opens=0)
 finally:os.close(fd)

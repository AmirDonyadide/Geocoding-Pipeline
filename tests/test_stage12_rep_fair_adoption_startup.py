"""Missing FAIR adoption regression: real builder/Authority/session/START path.

All kernel, scheduler, clock-window and approvals in the connected case are
explicit synthetic fixtures. This is neither a native nor workload qualification.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import os
import sys
import time

import pytest
from test_stage12_ra_g1_production_binding import private_source,production,installed_production_audit  # noqa:F401
from test_stage12_rep_fair_service import fair_upgrade
from test_stage12_ra_g1_native_root_sessions import KernelSession
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public as public,s12_ra_g1_execution as execution,s12_ra_g1_assurance as assurance,s12_ra_g1_monitor as monitor,s12_ra_g1_windows as windows,s12_retrieval_contract as c


def put(path,raw):
 path=Path(path);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'wb')as f:f.write(raw);f.flush();os.fsync(f.fileno())


class FixtureWindowClock:
 def utc(self):return windows.SIMPLE_WINDOW_START


@pytest.fixture
def connected(production,monkeypatch):
 case=production;case.allocation=fair_upgrade(case.allocation)
 case.bootstrap['created_utc']=windows.SIMPLE_WINDOW_START
 data,objects=case.preparer.build(case.allocation,case.bootstrap,**case.kwargs)
 case.allocation['resource_selection_sha256']=case.controller.digest(objects['resource_selection'])
 case.controller.validate_selection(case.allocation)
 case.root.mkdir(mode=0o700);output=Path(case.allocation['paths']['output']);output.mkdir(mode=0o700)
 environment=output/'TEST_ONLY_KERNEL';environment.mkdir(mode=0o700)
 case.host_platform=sys.platform
 kernel=KernelSession(environment,monkeypatch)
 selected=objects['resource_selection'];ctx=execution.capture_supervisor_context(scope=case.controller.SCOPE,
  source_git_sha=case.allocation['source_sha'],selection=selected,private_paths=dict(allocation_root=str(case.root),resource_evidence_root=str(output),scratch_root=str(output)),
  supervisor_pid=kernel.supervisor,run_nonce=case.allocation['intent_id'],check=lambda:None,read_charge=lambda *args:None)
 context_path=Path(case.allocation['paths']['context']);put(context_path,c.canonical(ctx))
 case.bootstrap['resource_execution']=dict(schema_version=execution.EXECUTION_REQUEST,supervisor_context_path=str(context_path),supervisor_context_sha256=c.sha(c.canonical(ctx)).hex())
 data,new=case.preparer.build(case.allocation,case.bootstrap,**case.kwargs)
 assert new['resource_selection']==selected
 bundle=Path(case.allocation['paths']['binding']);bundle.mkdir(mode=0o700)
 for role,value in new['role_records'].items():put(bundle/(role+'.record'),c.canonical(value))
 for values in new['resource_evidence'].values():
  for identity,value in values.items():
   path=bundle/'resource_evidence'/(identity+'.record')
   if path.exists():assert path.read_bytes()==c.canonical(value)
   else:put(path,c.canonical(value))
 put(bundle/'integration_review.binding.json',c.canonical(new['integration_review']))
 put(bundle/'integration_review.md',new['integration_report_utf8'].encode())
 put(case.allocation['paths']['input'],c.canonical(data))
 case.native=output/'TEST_ONLY_registered.db';put(case.native,b'SYNTHETIC_ONLY_NATIVE_FILE')
 case.objects=new;case.data=data;case.output=output;case.kernel=kernel;case.bundle=bundle
 case.control=SimpleNamespace(check=lambda:None,read_charge=lambda *args:None)
 yield case
 kernel.cleanup()


def actual_authority(case):
 return public.Authority(case.data['configuration'],case.bundle,case.objects['integration_review'],
  c.sha(c.canonical(case.objects['integration_review'])).hex(),case.source,case.allocation['source_sha'],
  FixtureWindowClock(),diagnostic=True)


def start(case,authority):
 entered=time.monotonic_ns()
 return case.diagnostic.start_phase_resource(execution,source_entry_ns=entered,input_version=case.diagnostic.REP_FAIR_VERSION,
  phase_id=1,clock_ns=time.monotonic_ns,authority=authority,config=case.data['configuration'],binding=case.objects['binding'],
  selection=case.objects['resource_selection'],evidence_root=case.output/'first64_resources',deadline_ns=entered+5_000_000_000,
  check=lambda:None,counters=lambda:{key:0 for key in monitor.COUNTERS},charge=lambda *args:None,read_charge=lambda *args:None,
  native_paths=(case.native,),native_roots=(case.output,),scope_start_ns=entered)


def test_actual_builder_authority_session_start_ack_and_original_reopening(connected):
 case=connected;selected=case.objects['resource_selection'];identity=selected['rep_fair_policy_adoption_sha256']
 expected=case.allocation['rep_fair_policy_adoption'];raw=(case.bundle/'resource_evidence'/(identity+'.record')).read_bytes()
 assert identity in case.objects['integration_review']['resource_evidence']['adoptions']
 assert raw==c.canonical(expected)and hashlib.sha256(raw).hexdigest()==identity
 # Full copied-source fence is real; kernel namespace/tool facts only are fixtures.
 authority=actual_authority(case);assert authority._source_verified is True
 assert authority._resource_evidence(identity,'adoptions')==expected
 value=start(case,authority);case.kernel.sessions.append(value)
 assert type(value.observer)is monitor.LinuxObserver
 first=value.require_start_acknowledged()
 assert first['first_start_seq']==1 and first['first_start_ack_mono_ns']<value.deadline
 row=value.monitor.first_start_receipt['row']
 original=value.original_reader(row['visible_identity_inventory_sha256'])
 assert original['origin']=='LIVE_KERNEL_OBSERVATION'  # private fake backing, not native qualification
 assert value.writer.acked>=1 and value.writer.path.stat().st_size>=monitor.CODEC_BYTES
 # No workload is invented to claim complete scientific acceptance. The real
 # owned session is aborted truthfully after original START/ACK reopening.
 value.abort();value.monitor.thread.join(1);value.writer.thread.join(1)
 assert not value.writer.thread.is_alive()and not value.monitor.thread.is_alive()
 assert not value.completed and value.protocol.state in('INCOMPLETE','UNCERTAIN')
 assert authority._original_read_calls>0
 observed=dict(scope='TEST_ONLY_SOURCE_AND_CONTROLLED_KERNEL_SESSION_NOT_NATIVE_QUALIFICATION',
  actual_Authority=True,full_copied_source_fence=True,actual_PhaseSession=True,actual_LinuxObserver=True,
  installed_audit_combined_with_kernel_fixture=False,adoption_sha256=identity,
  first_START_seq=first['first_start_seq'],first_START_enter_ns=first['first_start_enter_mono_ns'],
  first_START_exit_ns=first['first_start_exit_mono_ns'],first_START_ACK_ns=first['first_start_ack_mono_ns'],
  original_phase_deadline_ns=value.deadline,writer_rows=value.writer.rows,writer_acked=value.writer.acked,
  monitor_thread_joined=not value.monitor.thread.is_alive(),writer_thread_joined=not value.writer.thread.is_alive(),
  disposition=value.protocol.state,scientific_complete=value.completed,source_reads=authority._original_read_calls)
 put(case.private/'OBSERVED_START.record',c.canonical(observed))


def test_produced_FAIR_original_read_through_installed_audit(connected,monkeypatch):
 case=connected
 # The Linux kernel fixture and native syscall-denial simulator have separate
 # host assumptions. Keep the real host for this exact control/source-read
 # boundary; this test makes no native kernel permission or timing claim.
 monkeypatch.setattr(sys,'platform',case.host_platform)
 with installed_production_audit(case,case.control,monkeypatch)as audit_state:
  authority=actual_authority(case);assert authority._source_verified is True
  selected=case.objects['resource_selection'];identity=selected['rep_fair_policy_adoption_sha256']
  actual=authority._resource_evidence(identity,'adoptions')
  assert actual==case.allocation['rep_fair_policy_adoption']
  assurance.validate_rep_fair_adoption(actual,selected)
  with pytest.raises(c.Stage12Error,match='RA_G1_EVIDENCE_SCOPE'):
   authority._resource_evidence('f'*64,'adoptions')
  assert audit_state['events']>0 and authority._original_read_calls>0


@pytest.mark.parametrize('damage',['missing_membership','missing_file','changed_original','wrong_identity','mixed_family','stale_window'])
def test_actual_adoption_reader_refuses_missing_changed_stale_or_mixed(connected,damage):
 case=connected;identity=case.objects['resource_selection']['rep_fair_policy_adoption_sha256'];path=case.bundle/'resource_evidence'/(identity+'.record')
 authority=actual_authority(case)
 if damage=='missing_membership':authority.review=deepcopy(authority.review);authority.review['resource_evidence']['adoptions'].remove(identity)
 elif damage=='missing_file':path.rename(path.with_suffix('.preserved-missing-fixture'))
 elif damage=='changed_original':path.write_bytes(c.canonical(dict(case.allocation['rep_fair_policy_adoption'],maximum_pairs_per_outer_checkpoint=2)))
 elif damage=='wrong_identity':
  with pytest.raises(c.Stage12Error,match='RA_G1_EVIDENCE_SCOPE'):authority._resource_evidence('f'*64,'adoptions')
  return
 elif damage=='mixed_family':
  selected=deepcopy(case.objects['resource_selection']);selected['schema_version']=assurance.REP_ACK_SELECTION
  with pytest.raises(c.Stage12Error):assurance.validate_selection(selected)
  return
 else:
  authority.clock=SimpleNamespace(utc=lambda:'9999-01-01T00:00:00.000000Z')
  with pytest.raises(c.Stage12Error,match='RA_G1_EXPIRED'):authority.recheck()
  return
 with pytest.raises((c.Stage12Error,OSError,ValueError)):start(case,authority)
 assert not [thread for thread in __import__('threading').enumerate()if thread.name=='ra-g1-evidence-writer']



def test_FAIR_all_adoption_originals_exact_and_existing_read_precharge(connected):
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
 case=connected;values=case.objects['resource_evidence']['adoptions']
 originals=[case.kwargs['adoption'],case.allocation['bootstrap_prefix_adoption'],
  case.allocation['rep_admin_budget_adoption'],case.allocation['rep_first64_512_adoption'],
  case.allocation['rep_fair_policy_adoption']]
 assert set(values)=={case.controller.digest(value)for value in originals}
 for value in originals:
  identity=case.controller.digest(value)
  assert values[identity]==value
  assert(case.bundle/'resource_evidence'/(identity+'.record')).read_bytes()==c.canonical(value)
 rows=[row for row in case.allocation['accounting_inventory']['cost_rows']if row['component'].startswith('REP_FAIR_ADOPTION')]
 assert len(rows)==9 and sum(row['invocations']for row in rows)==17
 assert len(c.canonical(case.allocation['rep_fair_policy_adoption']))<=8192
 assert all(row['per_invocation_read_bytes']>=8192 for row in rows)
 inv=case.allocation['accounting_inventory'];accounting.validate_inventory(inv)
 assert inv['rep_first64_512']['global_events']==57237 and inv['rep_first64_512']['global_creations']==204860

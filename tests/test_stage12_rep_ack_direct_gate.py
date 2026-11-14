"""TEST_ONLY real direct-recovery child and matched gate; no live approval."""
from copy import deepcopy
import json,sys
from pathlib import Path
import pytest
from test_stage12_rep_ack_queue import H,metadata_allocation
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))

@pytest.fixture
def genuine_q2():
 from test_stage12_handoff_execution_window import retained_bytes
 import stage12_ra_g1_terminal_verify as verifier
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
 raw=retained_bytes("STAGE12_HANDOFF_RETAINED_Q2",windows.Q2_BUNDLE,65536)
 value=json.loads(raw)
 verifier.validate_qualification(value,expected_window=value['window'],expected_original_source_git_sha=windows.ORIGINAL_SOURCE,
  expected_original_job_id=int(windows.ORIGINAL_JOB),expected_original_selection_sha256=windows.ORIGINAL_SELECTION,
  expected_collector_source_git_sha=windows.Q2_SOURCE,expected_qualification_review_sha256=windows.Q2_REVIEW,
  expected_remote_directory_scope="stage12_task_remote_directory_identity_v1")
 return value


def test_actual_direct_recovery_proof_and_closed_ACK_gate(genuine_q2,tmp_path,monkeypatch):
 # The actual exporter, transport, codec, archive/mirror readers and pure
 # validators run on invented TEST_ONLY controls. Retained Q2 stays historical.
 import stage12_ra_g1_environment_launch as gate
 import stage12_ra_g1_terminal_verify as verifier
 import stage12_ra_g1_direct_recovery as direct
 from test_stage12_direct_recovery import complete_fixture
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
 from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
 from test_stage12_foreground_accounting import FLAGS
 _,plan,proof,review=complete_fixture(tmp_path,monkeypatch)
 selected,allocation,_=metadata_allocation(True)
 window=dict(version=windows.SIMPLE_WINDOW_VERSION,scope=allocation.SCOPE,valid_from=windows.SIMPLE_WINDOW_START,
  valid_until=windows.SIMPLE_WINDOW_END,policy_sha256=windows.digest(windows.simple_descriptor()),owner_authority_sha256=H,grant_nonce=H)
 old=selected['rep_admin_budget_adoption']
 selected['rep_admin_budget_adoption']=dict(schema_version=windows.SIMPLE_WINDOW_ADOPTION,scope=allocation.SCOPE,window=window,
  original_adoption=old,original_adoption_sha256=gate.digest(old),grant_kind=windows.REP_GRANT,maximum_submissions=1,
  qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW,
  historical_grant_consumed=True,original_budget_terms_unchanged=True)
 selected.update(valid_from=window['valid_from'],valid_until=window['valid_until'],resource_selection_sha256=H,
  records=dict(selected['records'],software_review=H,resource_review=H))
 rows={row['path']:row for row in selected['source_files']}
 for name in (*gate.REQUIRED_SOURCE,gate.COLLECTION_DOCUMENT,*gate.DIRECT_CONSUMER_PATHS,
  'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_rep_ack_contract.py'):
  raw=(ROOT/name).read_bytes();rows[name]=dict(path=name,bytes=len(raw),sha256=__import__('hashlib').sha256(raw).hexdigest())
 selected['source_files']=sorted(rows.values(),key=lambda row:row['path'])
 selected['accounting_inventory'],selected['accounting']=ac.compile_inventory(selected['source_files'],selected['accounting_inventory']['backends'],allocation.SCOPE,
  foreground_successor=True,ack_queue_successor=True,**FLAGS)
 binding=dict(version=gate.DIRECT_COLLECTION_BINDING,source_tree='c'*40,**{key:H for key in gate.DIRECT_BINDING_HASHES},
  remote_directory_scope=gate.REMOTE_DIRECTORY_SCOPE,transport_evidence_version=gate.REMOTE_TRANSPORT_VERSION,remote_directory_adoption_sha256=H,
  direct_recovery_software_source_sha=proof['software_source_sha'])
 binding.update(policy_sha256=gate.digest(gate.direct_collection_descriptor()),amendment_sha256=rows[gate.COLLECTION_DOCUMENT]['sha256'],
  window_policy_sha256=window['policy_sha256'],owner_authority_sha256=H,qualification_bundle_sha256=windows.Q2_BUNDLE,
  qualification_review_sha256=windows.Q2_REVIEW,direct_recovery_plan_sha256=proof['plan_sha256'],direct_recovery_result_sha256=gate.digest(proof),
  direct_recovery_review_sha256=gate.digest(review),direct_recovery_software_inventory_sha256=proof['software_inventory_sha256'],
  direct_recovery_consumer_inventory_sha256=proof['recovery_consumer_inventory_sha256'])
 value=dict(version=gate.DIRECT_COLLECTION_VERSION,scope=allocation.SCOPE,state='ISSUED_FOR_DIRECT_RECOVERY_REVIEWED_REP_ACK_DIAGNOSTIC',
  source_git_sha=selected['source_sha'],source_tree=binding['source_tree'],
  **{key:binding[key]for key in(*gate.DIRECT_BINDING_HASHES,*gate.REMOTE_COLLECTION_FIELDS,gate.DIRECT_SOFTWARE_FIELD)},
  selection_sha256=gate.selection_digest(selected),resource_selection_sha256=H,software_review_sha256=H,resource_review_sha256=H,
  source_inventory_sha256=selected['accounting_inventory']['source_inventory_sha256'],
  valid_from=window['valid_from'],valid_until=window['valid_until'],outer_window_end=window['valid_until'],window=window,
  grant_kind=windows.REP_GRANT,maximum_submissions=1,task_profiling='DISABLED',budget=gate.DIRECT_BUDGET,history=gate.DIRECT_HISTORY)
 now=windows.epoch_ns(window['valid_until'])-11220*10**9
 kwargs=dict(now_epoch_ns=now,qualification=genuine_q2,qualification_validator=verifier.validate_qualification,
  direct_recovery=proof,direct_review=review,direct_validator=lambda *args,**kw:direct.validate_recovery_proof(*args,allow_test_only=True,**kw))
 result=gate.validate_gate(value,selected,binding,**kwargs)
 assert result['required_remaining_ns']==11220*10**9 and not result['native_timing_PASS']
 assert len(gate.DIRECT_CONSUMER_PATHS)==7 and not proof['native_or_scientific_acceptance']
 with pytest.raises(RuntimeError):gate.validate_gate(value,selected,binding,**dict(kwargs,now_epoch_ns=now+1))
 # Production never accepts the TEST_ONLY result used by this unit fixture.
 with pytest.raises(RuntimeError):gate.validate_gate(value,selected,binding,**dict(kwargs,direct_validator=direct.validate_recovery_proof))
 for kind in ('old_binding','old_allocation','old_gate','review','source','policy','unknown'):
  b,v,sel,kw=deepcopy(binding),deepcopy(value),deepcopy(selected),dict(kwargs)
  if kind=='old_binding':b['version']=gate.SIMPLE_COLLECTION_BINDING
  elif kind=='old_allocation':sel['version']=allocation.REP_FOREGROUND_VERSION
  elif kind=='old_gate':v['version']=gate.SIMPLE_COLLECTION_VERSION
  elif kind=='review':kw['direct_review']=dict(review,result_sha256=H)
  elif kind=='source':sel['source_files'][next(i for i,r in enumerate(sel['source_files'])if r['path']==gate.DIRECT_CONSUMER_PATHS[0])]['sha256']=H
  elif kind=='policy':v['budget']=dict(v['budget'],AP_ACK_age_ms=500)
  else:v['unreviewed_authority']=True
  with pytest.raises(RuntimeError):gate.validate_gate(v,sel,b,**kw)

"""Matched coverage producer/handoff/assets. All approvals and clocks TEST_ONLY."""
from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from test_stage12_public_operations_v2 import offline  # noqa:F401
from test_stage12_ra_g1_production_binding import private_source, production  # noqa:F401
from test_stage12_rep_fair_service import fair_upgrade, fair_adoption
from test_stage12_foreground_accounting import FLAGS
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract as fair
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_coverage_contract as coverage
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as accounting
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

ROOT=Path(__file__).resolve().parents[1]


def coverage_adoption():
    return dict(fair_adoption(),schema_version=assurance.REP_COVERAGE_ADOPTION,
        policy_sha256=coverage.POLICY_SHA,prior_policy_sha256=fair.POLICY_SHA,
        positive_AP_gap_fail_stop_withdrawn=True,coverage_limit_ms=100,
        workload_evidence_and_AP_coverage_separate=True,direct_admission_start_emission_checks=True,
        administrative_monitor_limit_ms=1000,historical_strict_families_preserved=True)


def coverage_upgrade(value):
    from test_stage12_ra_g1_rep_admin_budget import allocation
    result=fair_upgrade(value);result['version']=allocation.REP_COVERAGE_VERSION
    result.pop('rep_fair_policy_adoption');result.pop('rep_fair_policy_adoption_sha256')
    adoption=coverage_adoption()
    result.update(rep_coverage_policy_adoption=adoption,rep_coverage_policy_adoption_sha256=coverage.digest(adoption))
    result['accounting_inventory'],result['accounting']=accounting.compile_inventory(
        result['source_files'],result['accounting_inventory']['backends'],allocation.SCOPE,
        foreground_successor=True,fair_service_successor=True,coverage_successor=True,**FLAGS)
    return result


@pytest.fixture
def matched(production,monkeypatch):
    import test_stage12_ra_g1_review_handoff as prior
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    production.bootstrap['created_utc']=windows.SIMPLE_WINDOW_START
    monkeypatch.setattr(prior,'upgrade',coverage_upgrade)
    case=prior.handoff.__wrapped__(production)
    case.plan_kwargs['observed_utc']=windows.SIMPLE_WINDOW_START
    return case


def test_actual_matched_builder_handoff_and_exact_resource_family(matched):
    import test_stage12_ra_g1_review_handoff as prior
    case=matched;data=case.controller.parse(case.originals['input']);selected=case.controller.parse(case.selection_raw)
    assert selected['version']==case.controller.REP_COVERAGE_VERSION
    assert data['version']==case.diagnostic.REP_COVERAGE_VERSION
    assert case.preparer.contract_for_allocation(selected)is coverage
    assert case.diagnostic.contract_for_input(data)is coverage
    assert data['configuration']['version']==case.preparer.REP_COVERAGE_CONFIG_VERSION
    case.controller.validate_selection(selected)
    case.diagnostic.validate_envelope(data,selected['source_sha'],for_execution=True)
    case.diagnostic.validate_workloads(data)
    resource=case.controller.parse(case.originals['resource_selection'])
    assert resource['schema_version']==assurance.REP_COVERAGE_SELECTION
    case.diagnostic.validate_resource_family(data['version'],resource)
    assert all(row['profile']['schema_version']==coverage.PROFILE
               and row['profile']['sampling_policy_sha256']==coverage.POLICY_SHA
               for row in data['configuration']['campaigns'])
    plan=case.plan()
    assert plan['raw_sha256']==prior.helper.sha(case.release)
    prepared=prior.helper.preparation_plan(case.selection_raw,
        **{k:case.plan_kwargs[k]for k in('selection_sha256','source_sha','job_id')})
    assert prepared['selection_sha256']==case.plan_kwargs['selection_sha256']
    assert plan['original_binder_deadline_ns']-plan['original_binder_start_ns']==240_000_000_000
    # These true parser/runtime checks use synthetic originals, never live approval.
    runtime.verify_successor_assets(case.source,contract=coverage,
        rep_admin_successor=True,first64_512_successor=True,foreground_successor=True,
        fair_service_successor=True,coverage_successor=True)


@pytest.mark.parametrize('damage',['allocation_family','input_family','resource_family','adoption','source','window','hash'])
def test_actual_production_handoff_rejects_mixed_or_stale(matched,damage):
    case=matched
    if damage=='allocation_family':
        selected=case.controller.parse(case.selection_raw);selected['version']=case.controller.REP_FAIR_VERSION
        case.selection_raw=case.controller.canonical(selected);case.plan_kwargs['selection_sha256']=hashlib.sha256(case.selection_raw).hexdigest()
    elif damage=='input_family':
        data=case.controller.parse(case.originals['input']);data['version']=case.diagnostic.REP_FAIR_VERSION
        case.originals['input']=case.controller.canonical(data)
    elif damage=='resource_family':
        value=case.controller.parse(case.originals['resource_selection']);value['schema_version']=assurance.REP_FAIR_SELECTION
        case.originals['resource_selection']=case.controller.canonical(value)
    elif damage=='adoption':
        selected=case.controller.parse(case.selection_raw);selected['rep_coverage_policy_adoption']['coverage_limit_ms']=101
        selected['rep_coverage_policy_adoption_sha256']=case.controller.digest(selected['rep_coverage_policy_adoption'])
        case.selection_raw=case.controller.canonical(selected);case.plan_kwargs['selection_sha256']=hashlib.sha256(case.selection_raw).hexdigest()
    elif damage=='source':case.plan_kwargs['source_sha']='a'*40
    elif damage=='window':case.plan_kwargs['observed_utc']=case.allocation['valid_until']
    else:case.plan_kwargs['selection_sha256']='a'*64
    with pytest.raises((RuntimeError,ValueError)):case.plan()


def test_exact_new_descriptor_asset_and_historical_assets_unchanged():
    from test_stage12_ra_g1_rep_admin_budget import allocation,diagnostic
    for wire,producer in ((allocation.REP_COVERAGE_VERSION,allocation.descriptor),(diagnostic.REP_COVERAGE_VERSION,diagnostic.descriptor)):
        assert(ROOT/'docs/scientific_assets'/(wire+'.json')).read_bytes()==c.canonical(producer(wire))
    desc=diagnostic.descriptor(diagnostic.REP_COVERAGE_VERSION)
    assert desc['maximum_creations']==204860 and desc['maximum_event_files']==57237
    assert desc['workload_and_AP_coverage_separate'] is True and desc['positive_AP_gap_fail_stop'] is False
    for wire in (diagnostic.REP512_VERSION,diagnostic.REP_FOREGROUND_VERSION,diagnostic.REP_ACK_VERSION,diagnostic.REP_FAIR_VERSION):
        assert(ROOT/'docs/scientific_assets'/(wire+'.json')).read_bytes()==c.canonical(diagnostic.descriptor(wire))


@pytest.fixture
def connected_start(production,monkeypatch):
    import test_stage12_rep_fair_adoption_startup as prior
    monkeypatch.setattr(prior,'fair_upgrade',coverage_upgrade)
    lifecycle=prior.connected.__wrapped__(production,monkeypatch)
    case=next(lifecycle)
    try:yield case
    finally:
        try:next(lifecycle)
        except StopIteration:pass


def start_coverage(case,authority):
    import time
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution,s12_ra_g1_monitor as monitor
    entered=time.monotonic_ns()
    return case.diagnostic.start_phase_resource(execution,source_entry_ns=entered,input_version=case.diagnostic.REP_COVERAGE_VERSION,
      phase_id=1,clock_ns=time.monotonic_ns,authority=authority,config=case.data['configuration'],binding=case.objects['binding'],
      selection=case.objects['resource_selection'],evidence_root=case.output/'first64_resources',deadline_ns=entered+5_000_000_000,
      check=lambda:None,counters=lambda:{key:0 for key in monitor.COUNTERS},charge=lambda *args:None,read_charge=lambda *args:None,
      native_paths=(case.native,),native_roots=(case.output,),scope_start_ns=entered)


def test_coverage_actual_authority_adoption_session_START_ACK(connected_start):
    import test_stage12_rep_fair_adoption_startup as prior
    case=connected_start;authority=prior.actual_authority(case)
    selected=case.objects['resource_selection'];identity=selected['rep_coverage_policy_adoption_sha256']
    assert authority._resource_evidence(identity,'adoptions')==case.allocation['rep_coverage_policy_adoption']
    value=start_coverage(case,authority);case.kernel.sessions.append(value)
    first=value.require_start_acknowledged()
    assert first['first_start_seq']==1 and first['first_start_ack_mono_ns']<value.deadline
    row=value.monitor.first_start_receipt['row']
    assert value.original_reader(row['visible_identity_inventory_sha256'])['origin']=='LIVE_KERNEL_OBSERVATION'
    assert value.writer.acked>=1
    value.abort();value.monitor.thread.join(1);value.writer.thread.join(1)
    assert not value.writer.thread.is_alive() and not value.monitor.thread.is_alive()
    assert not value.completed  # Truthful abort; no whole workload/native qualification.


@pytest.mark.parametrize('damage',['missing','changed','mixed'])
def test_coverage_actual_adoption_original_rejected_before_START(connected_start,damage):
    import test_stage12_rep_fair_adoption_startup as prior
    case=connected_start;authority=prior.actual_authority(case)
    selected=case.objects['resource_selection'];identity=selected['rep_coverage_policy_adoption_sha256']
    path=case.bundle/'resource_evidence'/(identity+'.record')
    if damage=='missing':path.rename(path.with_suffix('.preserved-missing'))
    elif damage=='changed':path.write_bytes(c.canonical(dict(case.allocation['rep_coverage_policy_adoption'],coverage_limit_ms=101)))
    else:
        selected['schema_version']=assurance.REP_FAIR_SELECTION
        with pytest.raises(c.Stage12Error):assurance.validate_selection(selected)
        return
    with pytest.raises((c.Stage12Error,OSError,ValueError)):start_coverage(case,authority)


def test_coverage_adoption_read_through_actual_installed_audit(connected_start,monkeypatch):
    import sys
    import test_stage12_rep_fair_adoption_startup as prior
    from test_stage12_ra_g1_production_binding import installed_production_audit
    case=connected_start;monkeypatch.setattr(sys,'platform',case.host_platform)
    with installed_production_audit(case,case.control,monkeypatch)as state:
        authority=prior.actual_authority(case)
        selected=case.objects['resource_selection'];identity=selected['rep_coverage_policy_adoption_sha256']
        value=authority._resource_evidence(identity,'adoptions')
        assurance.validate_rep_coverage_adoption(value,selected)
        with pytest.raises(c.Stage12Error):authority._resource_evidence('f'*64,'adoptions')
        assert state['events']>0 and authority._source_verified


def coverage_gate_binding(case):
    import stage12_ra_g1_environment_launch as gate
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_windows as windows
    H='a'*64;selected=deepcopy(case.allocation)
    rows={r['path']:r for r in selected['source_files']}
    for name in (*gate.REQUIRED_SOURCE,gate.COLLECTION_DOCUMENT,*gate.DIRECT_CONSUMER_PATHS,
                 'src/safe_geocoding_pipeline/preprocessing/stages/s12_ra_g1_rep_coverage_contract.py'):
        raw=(ROOT/name).read_bytes();rows[name]=dict(path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    selected['source_files']=sorted(rows.values(),key=lambda r:r['path'])
    selected['accounting_inventory'],selected['accounting']=accounting.compile_inventory(
        selected['source_files'],selected['accounting_inventory']['backends'],selected['scope'],
        foreground_successor=True,fair_service_successor=True,coverage_successor=True,**FLAGS)
    window=selected['rep_admin_budget_adoption']['window']
    binding=dict(version=gate.COVERAGE_DIRECT_COLLECTION_BINDING,source_tree='c'*40,
      **{key:H for key in gate.DIRECT_BINDING_HASHES},
      remote_directory_scope=gate.REMOTE_DIRECTORY_SCOPE,transport_evidence_version=gate.REMOTE_TRANSPORT_VERSION,
      remote_directory_adoption_sha256=H,direct_recovery_software_source_sha='d'*40)
    binding.update(policy_sha256=gate.digest(gate.direct_collection_descriptor(fair_service_successor=True,coverage_successor=True)),
      amendment_sha256=rows[gate.COLLECTION_DOCUMENT]['sha256'],window_policy_sha256=windows.digest(windows.selected_descriptor(window)),
      owner_authority_sha256=window['owner_authority_sha256'],grant_nonce=window['grant_nonce'],
      qualification_bundle_sha256=windows.Q2_BUNDLE,qualification_review_sha256=windows.Q2_REVIEW)
    current=[rows[name]for name in sorted(gate.DIRECT_CONSUMER_PATHS)]
    compatibility=dict(version=gate.COVERAGE_COMPATIBILITY_VERSION,current_source_sha=selected['source_sha'],
      current_source_inventory_sha256=selected['accounting_inventory']['source_inventory_sha256'],
      old_result_sha256=binding['direct_recovery_result_sha256'],old_review_sha256=binding['direct_recovery_review_sha256'],
      old_source_sha=binding[gate.DIRECT_SOFTWARE_FIELD],old_consumer_inventory_sha256=binding['direct_recovery_consumer_inventory_sha256'],
      current_consumer_inventory=current,changed_paths=[],focused_compatibility_review_sha256=H)
    binding.update(direct_recovery_consumer_compatibility=compatibility,direct_recovery_consumer_compatibility_sha256=gate.digest(compatibility))
    return gate,selected,binding


def test_coverage_gate_binding_is_explicit_and_not_legacy(matched):
    gate,selected,binding=coverage_gate_binding(matched)
    assert gate.validate_binding(binding,selected)==binding
    descriptor=gate.direct_collection_descriptor(fair_service_successor=True,coverage_successor=True)
    assert descriptor['positive_AP_gap_fail_stop'] is False
    assert descriptor['budget']['AP_acquisition_gap_ms']==100 and descriptor['budget']['administrative_gap_ms']==1000
    for family in (gate.DIRECT_COLLECTION_BINDING,gate.FAIR_DIRECT_COLLECTION_BINDING):
        wrong=dict(binding,version=family)
        with pytest.raises(RuntimeError):gate.validate_binding(wrong,selected)
    for field in ('policy_sha256','source_tree','direct_recovery_consumer_compatibility_sha256'):
        wrong=dict(binding,**{field:'f'*64})
        with pytest.raises(RuntimeError):gate.validate_binding(wrong,selected)


def test_actual_terminal_producer_assignment_has_versioned_separate_outcomes():
    """Actual emitter expression only; no invented complete native workflow."""
    import ast
    from types import SimpleNamespace
    import stage12_ra_g1_allocation as controller
    tree=ast.parse(Path(controller.__file__).read_bytes())
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='verify')
    assignments=[node for node in function.body if isinstance(node,ast.Assign)
        and any(isinstance(target,ast.Name) and target.id=='result' for target in node.targets)]
    assert len(assignments)==1
    summary=dict(complete=True,workload_complete=True,ap_coverage_complete=False,
        administrative_monitor_coverage_complete=True,qualification_outcome='WORKLOAD_COMPLETE_AP_COVERAGE_INCOMPLETE')
    for version in (controller.REP_COVERAGE_VERSION,controller.REP_FAIR_VERSION):
        env=dict(controller.__dict__,s=dict(version=version,source_sha='a'*40),data={},summary=summary,
            child={},reports=[],administrative_reports=[],counter_originals={},run=SimpleNamespace(end=10**18))
        exec(compile(ast.Module(body=assignments,type_ignores=[]),str(controller.__file__),'exec'),env)
        value=env['result']
        if version==controller.REP_COVERAGE_VERSION:
            assert value['version']=='stage12_ra_g1_coverage_allocation_terminal_v1'
            assert all(value[key]==summary[key] for key in('workload_complete','ap_coverage_complete','administrative_monitor_coverage_complete','qualification_outcome'))
        else:
            assert value['version']=='stage12_ra_g1_allocation_terminal_v1'
            assert all(key not in value for key in('workload_complete','ap_coverage_complete','administrative_monitor_coverage_complete','qualification_outcome'))

"""Prospective bootstrap successor author fixtures; never live authority."""
from copy import deepcopy
import pytest
from test_s12_ra_g1_core import selection, binding, Authority, observation, original_observation, H
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as a
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as e
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_monitor as m
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c


def bootstrap_inputs():
    selected = selection("REPRESENTATIVE_NO_SERVICE")
    selected["limits"].update(a.SCOPE_CEILINGS["REPRESENTATIVE_NO_SERVICE"])
    stage = selected["limits"]["stages"][0]
    selected["limits"]["stages"] = [{**stage,"id":i,"phase":i,"deadline_ms":60000,
        "reserve_ms":1,"attempts":10 if i<5 else 0,"events":100 if i<5 else 0,
        "logical_write_bytes":16*2**20,"creations":2000} for i in range(1,8)]
    adoption = dict(schema_version=a.BOOTSTRAP_ADOPTION,scope="REPRESENTATIVE_NO_SERVICE",
        policy_sha256=a.old.digest(a.bootstrap_policy_descriptor()),owner_decision_original_sha256=H,
        owner_decision_canonical_sha256=H,provenance="CURRENT_USER_DIRECT_RELAY_NOT_INDEPENDENT_AUTHENTICATION",
        prospective_only=True,startup_ceiling_ns=30_000_000_000,historical_job1811420_cause="UNKNOWN")
    selected.update(schema_version=a.BOOTSTRAP_SELECTION,
        bootstrap_prefix_policy_sha256=a.old.digest(a.bootstrap_policy_descriptor()),
        bootstrap_prefix_adoption_sha256=a.old.digest(adoption))
    def reader(identity):
        assert identity == a.old.digest(adoption)
        return deepcopy(adoption)
    return selected,adoption,reader


def actual_session(tmp_path,phase=1,ack=9_000_000_000,deadline=60_000_000_000):
    selected,adoption,reader=bootstrap_inputs()
    entry=100
    end=entry+min(ack,29_999_999_999)
    clock=[end]
    authority=Authority(selected)
    def factory(retain):
        def observer(kind):
            if kind != "START":
                clock[0] += 1
            enter=clock[0]
            row=observation(selected,enter=enter,kind=kind)
            row["phase_id"]=phase
            row["visible_identity_inventory_sha256"]=retain(original_observation(row))
            if kind=="START":
                clock[0]=entry+ack
            return {k:row[k] for k in ("readings","counters","native_visibility","visible_identity_inventory_sha256")}
        return observer
    bound=binding(selected)
    session_type=e.PhaseSession
    if phase in (6,7):
        session_type=e.AdministrativePhaseSession
        bound=dict(schema_version=e.ADMIN_BINDING,scope="REPRESENTATIVE_NO_SERVICE",method=a.METHOD,
            role=a.BOOTSTRAP_ROLES[phase],phase_id=phase,source_git_sha=selected["source_git_sha"],
            selection_sha256=a.old.digest(selected),adoption_sha256=H,supervisor_context_sha256=H,
            risk_inventory_sha256=H,process_pid=123,process_start_ticks=1,process_uid=1,
            scope_start_mono_ns=entry,deadline_mono_ns=entry+deadline,
            service_authority="DENIED",protected_input_authority="DENIED",ap_dispatch_authority="DENIED")
    value=session_type(authority=authority,binding=bound,selection=selected,
        resource_evidence_root=tmp_path/("phase"+str(phase)),pids=(123,),
        counter_provider=lambda:{k:0 for k in m.COUNTERS},charge=lambda *x:None,check=lambda:None,
        deadline_ns=entry+deadline,phase_id=phase,admitted_process_provider=lambda:(123,),
        read_charge=lambda *x:None,observer_factory=factory,clock_ns=lambda:clock[0],scope_start_ns=entry,
        bootstrap_prefix=dict(role=a.BOOTSTRAP_ROLES.get(phase,"PHASE_RUNNER"),source_entry_ns=entry,bootstrap_end_ns=end),
        bootstrap_adoption_reader=reader)
    return value,clock


@pytest.mark.parametrize("phase",[1,6,7])
@pytest.mark.parametrize("ack",[9_000_000_000,30_000_000_000])
def test_genuine_bootstrap_start_and_inclusive_ceiling(tmp_path,phase,ack):
    value,clock=actual_session(tmp_path,phase=phase,ack=ack)
    try:
        value.start()
        proof=value.require_start_acknowledged()
        assert proof["first_start_ack_mono_ns"]==100+ack
        assert value.deadline==100+60_000_000_000
        assert value.monitor.scope_start==proof["bootstrap_end_mono_ns"]
        assert proof["source_entry_mono_ns"]==100
        assert proof["first_start_seq"]==1
    finally:
        value.abort()


@pytest.mark.parametrize("ack,deadline",[(30_000_000_001,60_000_000_000),(30_000_000_000,30_000_000_000)])
def test_late_ack_or_earlier_original_deadline_never_qualifies(tmp_path,ack,deadline):
    value,clock=actual_session(tmp_path,ack=ack,deadline=deadline)
    with pytest.raises(c.Stage12Error):
        value.start()
    assert value.bootstrap_record is None


def test_missing_or_tampered_original_prevents_readiness_and_actual_opener(tmp_path):
    value,clock=actual_session(tmp_path)
    try:
        value.start()
        path=value.root/"bootstrap_prefix.record"
        path.write_bytes(path.read_bytes()+b" ")
        opened=[]
        with pytest.raises(c.Stage12Error):
            value.freeze_and_open(frozen_data_inventory_sha256=H,actual_opener=lambda:opened.append(True))
        assert opened==[]
    finally:
        value.abort()


def test_later_phase_no_exception_and_strict_old_selection(tmp_path):
    with pytest.raises(c.Stage12Error):
        actual_session(tmp_path,phase=2)
    selected,adoption,reader=bootstrap_inputs()
    selected["schema_version"]=a.SELECTION
    selected.pop("bootstrap_prefix_policy_sha256")
    selected.pop("bootstrap_prefix_adoption_sha256")
    assert a.validate_selection(selected)["schema_version"]==a.SELECTION
    scope=m.Coverage(binding_sha256=H,selection_sha256=a.old.digest(selected),phase_id=1,
        seed_sha256=H,selected=selected,scope_start_ns=100)
    row=observation(selected,enter=1_000_000_101)
    with pytest.raises(c.Stage12Error,match="RA_G1_MONITOR_GAP"):
        scope.add(row)


def test_fresh_worker_opener_and_parent_require_bootstrap_sidecar(tmp_path):
    value,clock=actual_session(tmp_path)
    value.start()
    _,records=value.freeze_and_open(frozen_data_inventory_sha256=H,actual_opener=lambda:None)
    assert records["preopening"]["schema_version"]==m.BOOTSTRAP_PROTOCOL_IDS[m.CLOSURE]
    with pytest.raises(c.Stage12Error):
        m.validate(records["preopening"],m.CLOSURE)
    protocol=m.reopen_phase_protocol(binding_sha256=a.old.digest(value.binding),selection_sha256=a.old.digest(value.selection),
        phase_id=1,closure=records["preopening"],opener_return=records["opener_return"],monitor_terminal=records["monitor_terminal"],
        deadline_ns=value.deadline,check=lambda:None,clock_ns=lambda:clock[0])
    (value.root/"bootstrap_prefix.record").unlink()
    with pytest.raises((OSError,c.Stage12Error)):
        m.verify_tail(protocol=protocol,monitor_path=value.writer.path,selected=value.selection,seed_sha256=value.seed,
            child_result=dict(pid=123,wait_status=0,acquired_mono_ns=clock[0]),genuine_wait_status=0,
            expected_child_pid=123,current_counter_sha256=H,persist_terminal=lambda r,check:r,
            original_observation_reader=value.original_reader,worker_validation=records["worker_validation"],test_only=True)

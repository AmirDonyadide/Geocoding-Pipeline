"""Deterministic TEST_ONLY faults; not live timing or native qualification."""
import threading
from types import ModuleType
from pathlib import Path
import pytest
from test_stage12_public_sampling import component
from test_stage12_public_operations_v2 import offline  # noqa: F401
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as d
from safe_geocoding_pipeline.preprocessing.stages import s12_public_sampling as sampling
from safe_geocoding_pipeline.preprocessing.stages import s12_public_scheduler as scheduler


def owned():
    s, co, log, clock = component()
    co.failures = d.Failures(clock, sampling=True)
    return s, co, log, clock


@pytest.mark.parametrize("gap", [100_000_001, -1])
def test_actual_acquisition_retains_pre_assignment_operands(gap):
    s, co, log, clock = owned()
    s.last_observed = 1_000_000_000
    clock.value = s.last_observed + gap
    assert s.acquire() is True  # Original control outcome is preserved.
    row = s.first_fault
    assert s.failure == "ACQUISITION_GAP"
    assert row["predicate_origin"] == "ACQUISITION_INTERVAL"
    assert row["caller_context"] == "ACQUIRE"
    assert row["previous_observed_mono_ns"] == 1_000_000_000
    assert row["candidate_observed_mono_ns"] == clock.value
    assert row["health_time_mono_ns"] is None
    assert row["check_mono_ns"] == clock.value
    assert row["bound_ns"] == 100_000_000 and row["reserved_seq"] == 1
    assert s.last_observed == clock.value
    assert co.failures.snapshot()["sampling_first_fault"]["first_fault"] == row


def test_inclusive_exact_acquisition_boundary_has_no_descriptor():
    s, co, log, clock = owned()
    clock.value = 100_000_000
    assert s.acquire() is True and s.failure is None
    assert s.first_fault is None
    assert co.failures.snapshot()["sampling_first_fault"]["first_fault"] is None


def test_real_owner_loop_context_not_a_direct_duplicate_predicate():
    s, co, log, clock = owned()
    clock.value = 100_000_001
    s._owner()
    assert s.failure == "ACQUISITION_GAP"
    assert s.first_fault["caller_context"] == "OWNER"
    assert s.first_fault["predicate_origin"] == "HEALTH_FRESHNESS"
    assert s.first_fault["previous_observed_mono_ns"] == 0
    assert s.first_fault["health_time_mono_ns"] == 100_000_001


def test_actual_coordinator_safe_point_context():
    s, co, log, clock = owned()
    co.ap_enabled = True
    co.ap_sampler = s
    clock.value = 100_000_001
    assert scheduler.Coordinator.sample_if_due(co) is False
    assert s.first_fault["caller_context"] == "COORDINATOR_SNAPSHOT"


def test_actual_writer_service_health_and_same_persistence_exception():
    s, co, log, clock = owned()
    assert s.acquire()
    s.opened = True  # TEST_ONLY component OPEN fixture; no ACK success is mocked.
    original = OSError(5, "SECRET_NOT_A_DIAGNOSTIC")
    def uncertain(*args, **kwargs):
        raise original
    log.event = uncertain
    clock.value = 100_000_001
    with pytest.raises(OSError) as caught:
        s.service()
    assert caught.value is original
    assert s.failure == "ACQUISITION_GAP"
    assert s.first_fault["caller_context"] == "SERVICE"
    assert s.first_fault["health_time_mono_ns"] == 100_000_001
    assert "SECRET" not in str(co.failures.snapshot())


def test_actual_close_health_and_later_emission_are_distinct():
    s, co, log, clock = owned()
    events=[]
    log.event=lambda kind,body,**kwargs: events.append((kind,body))
    clock.value = 100_000_001
    body=s.close()
    assert body["result"] == "INCOMPLETE"
    assert s.first_fault["caller_context"] == "CLOSE"
    assert s.first_fault["predicate_origin"] == "HEALTH_FRESHNESS"
    first=dict(s.first_fault)
    clock.value = 500_000_000
    s.health(caller_context="SERVICE")
    assert s.first_fault == first
    # A second sampler demonstrates a first fault and a later journal emission.
    s2, co2, log2, clock2=owned();events2=[]
    log2.event=lambda kind,body,**kwargs: events2.append((kind,body))
    clock2.value=100_000_001;s2.health(caller_context="OWNER")
    clock2.value=500_000_000;s2.close()
    assert s2.first_fault["check_mono_ns"] == 100_000_001
    assert next(v for k,v in events2 if k=="SAMPLING_FAULT")["at_mono_ns"] == 500_000_000
    assert set(next(v for k,v in events2 if k=="SAMPLING_FAULT")) == {"code","at_mono_ns","stage","reserved_seq","trigger_sample_event_seq"}


def test_negative_health_interval_preserves_actual_positive_operands():
    s, co, log, clock=owned();s.last_observed=100;clock.value=99
    s.health(caller_context="CLOSE")
    assert s.failure=="CLOCK_INVALID"
    assert s.first_fault["predicate_origin"]=="HEALTH_CLOCK_ORDER"
    assert s.first_fault["previous_observed_mono_ns"]==100
    assert s.first_fault["health_time_mono_ns"]==99


def test_unknown_context_and_secondary_fault_cannot_inject_payload_or_overwrite():
    s, co, log, clock=owned();clock.value=100_000_001
    s.health(caller_context="SECRET_PAYLOAD")
    first=dict(s.first_fault);s.fail("DRAIN_EXPIRED","DRAIN")
    assert s.first_fault==first and first["caller_context"]=="UNSPECIFIED"
    assert "SECRET" not in str(co.failures.snapshot())


def test_concurrent_first_fault_owner_is_atomic():
    s, co, log, clock=owned();gate=threading.Barrier(3)
    def fault(code):gate.wait();s.fail(code)
    threads=[threading.Thread(target=fault,args=(code,)) for code in ("ACQUISITION_FAILED","OWNER_FAILED")]
    for t in threads:t.start()
    gate.wait()
    for t in threads:t.join(1);assert not t.is_alive()
    assert s.first_fault["code"]==s.failure
    assert co.failures.snapshot()["sampling_first_fault"]["first_fault"]["code"]==s.failure


def test_healthy_actual_guards_match_pinned_preimage(tmp_path):
    # Explicit deterministic old-code control, not a replacement production module.
    import os
    selected=os.environ.get("STAGE12_SAMPLER_PREIMAGE")
    if selected is None:
        pytest.skip("Explicit pinned historical control artifact is required")
    preimage=Path(selected)
    import hashlib
    assert hashlib.sha256(preimage.read_bytes()).hexdigest()=="bef1dae7c62aa681788e2ee3e0dc8fb8376972f2f86c2890d2ac3f7addefa8de"
    legacy=ModuleType("safe_geocoding_pipeline.preprocessing.stages._legacy_sampling_control")
    legacy.__package__="safe_geocoding_pipeline.preprocessing.stages"
    exec(compile(preimage.read_bytes(),str(preimage),"exec"),legacy.__dict__)
    current,co,log,clock=owned()
    other,co2,log2,clock2=owned();old=legacy.Sampler(co2)
    old.owner_ident=threading.get_ident();old.anchor=0;old.last_observed=0;old.head=other.head;old.association=other.association
    clock.value=clock2.value=100_000_000
    assert current.acquire()==old.acquire()
    assert bytes(current.arena)==bytes(old.arena)
    assert (current.failure,current.acquired,current.reserved,current.maximum_gap)==(old.failure,old.acquired,old.reserved,old.maximum_gap)
    current.health();old.health()
    assert current.failure==old.failure is None


def source_authority(root, rows):
    from safe_geocoding_pipeline.preprocessing.stages.s12_ra_g1_public import Authority
    from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
    auth=Authority.__new__(Authority)  # TEST_ONLY isolated source-reader state.
    auth.repository=root;auth.review={"source_files":rows}
    auth._source_root_identity=assurance.private_root_identity(root)
    auth._source_verified=False;auth._deadline_check=lambda:None
    auth._lock=threading.RLock();auth._source_counter_ledger=None
    auth._local_read_calls=auth._local_read_bytes=auth._local_enforcement_checks=0
    auth._read_call_limit=2**20;auth._read_byte_limit=2**20
    return auth


def real_descriptor():
    import importlib,hashlib
    root=Path(__file__).resolve().parents[1];specs=[];rows=[]
    if root.stat().st_mode & 0o077:
        pytest.skip("Actual Authority source pins require an explicit private0700 checkout fixture")
    for module_id,relative in d.FOREGROUND_MODULES:
        name="stage12_ra_g1_diagnostic" if module_id=="DIAGNOSTIC" else relative.removeprefix("src/").removesuffix(".py").replace("/",".")
        if module_id == "DIAGNOSTIC":
            import importlib.util,sys
            spec=importlib.util.spec_from_file_location(name,root/relative)
            module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
        else:
            module=importlib.import_module(name)
        specs.append((module_id,module))
        raw=(root/relative).read_bytes()
        rows.append({"path":relative,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
    auth=source_authority(root,rows)
    descriptor=d.prepare_first_failure_descriptor(specs,rows,source_root=root,verify_source=auth.verify_diagnostic_source)
    return descriptor,auth


def test_full_real_selected_modules_use_actual_streaming_authority_verifier():
    descriptor,auth=real_descriptor()
    assert not descriptor.preparation_uncertain
    assert descriptor.source_map_sha256 is not None and descriptor._codes
    assert auth._original_read_bytes==sum(r["bytes"] for r in auth.review["source_files"])
    assert auth._original_read_calls>=len(auth.review["source_files"])*2
    assert auth._source_verified is False  # Pinning never substitutes for full fence.


def test_actual_source_reader_rejects_unselected_changed_symlink_and_root(tmp_path):
    import hashlib
    from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
    root=tmp_path/"private-source";root.mkdir(mode=0o700)
    p=root/"one.py";p.write_bytes(b"VALUE=1\n")
    row={"path":"one.py","bytes":8,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
    auth=source_authority(root,[row])
    assert auth.verify_diagnostic_source(p,row) is True
    charged=auth._original_read_calls
    with pytest.raises(c.Stage12Error):auth.verify_diagnostic_source(root/"unselected.py",dict(row,path="unselected.py"))
    assert auth._original_read_calls==charged
    p.write_bytes(b"VALUE=2\n")
    with pytest.raises(c.Stage12Error):auth.verify_diagnostic_source(p,row)
    p.unlink();p.symlink_to(tmp_path/"never-opened-secret")
    with pytest.raises(c.Stage12Error):auth.verify_diagnostic_source(p,row)
    p.unlink();p.write_bytes(b"VALUE=1\n")
    root.rename(tmp_path/"retained-source-before-replacement");root.mkdir(mode=0o700);(root/"one.py").write_bytes(b"VALUE=1\n")
    with pytest.raises(c.Stage12Error):auth.verify_diagnostic_source(root/"one.py",row)


def test_real_cli_admission_owner_precedes_later_actual_close_health(offline,tmp_path,monkeypatch):
    from test_stage12_public_sampling_contract import ap_inputs,TestOnlyAuthority
    from test_stage12_public_operations_v2 import FakeClock,H,KEY
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
    p,plan,start,rows,inventory,bound=ap_inputs();clock=FakeClock()
    descriptor,_=real_descriptor();owner=d.Failures(clock,closure=True,first_failure_descriptor=descriptor,sampling=True)
    original=RuntimeError("SECRET_ADMISSION_ARGUMENT")
    seen=[];original_record=owner.record
    def record(tag,error,**kwargs):
        if tag=="ADMISSION":seen.append(error)
        return original_record(tag,error,**kwargs)
    owner.record=record
    class AdmissionAuthority(TestOnlyAuthority):
        def require(self,purpose,evidence,context):
            if purpose=="dispatch":raise original
            return super().require(purpose,evidence,context)
    original_close=sampling.Sampler.close
    def close_injected(s):
        # Deterministic test-only injection under the actual ownership lock;
        # force the close-health predicate before its normal producer join.
        with s.lock:
            clock.value=max(clock.value,s.last_observed+100_000_001)
            s.health(caller_context="CLOSE")
        return original_close(s)
    monkeypatch.setattr(sampling.Sampler,"close",close_injected)
    dispatches=[]
    def forbidden_dispatch(*args):dispatches.append(1);raise AssertionError("NO_PROVIDER_TEST")
    result=cli.run_operations_block(p,plan,start,work_factory=lambda:iter(rows),output=tmp_path/"actual-guard-run",block_id=1,authority=AdmissionAuthority(bound),clock=clock,dispatch=forbidden_dispatch,runtime_inventory=inventory,runtime_key=KEY,control_adapters={},monitor=None,free_bytes=lambda:2**42,segment_authority=H,writer_exclusion_evidence=H,epoch=H,writer_release_evidence=H,task_deadline_ns=180_000_000_000,diagnostics=owner,public_validation=Validation())
    snapshot=owner.snapshot()
    assert seen and seen[0] is original and not dispatches
    assert snapshot["first_initiating_failure"]["operation"]=="ADMISSION"
    assert snapshot["first_initiating_failure"]["writer_failed"] is False
    fg=snapshot["foreground_first_failure"]["first_failure"]
    assert fg["exception_class"]=="RUNTIME_ERROR" and fg["frames"]
    fault=snapshot["sampling_first_fault"]["first_fault"]
    assert fault["caller_context"]=="CLOSE" and fault["predicate_origin"]=="HEALTH_FRESHNESS"
    assert snapshot["first_initiating_failure"]["mono_ns"]<fault["check_mono_ns"]
    assert not result["report_complete"] and "SECRET" not in str(snapshot)


@pytest.fixture(scope="module")
def private_source():
    # TEST_ONLY reuse of the existing private candidate fixture, not another copy
    # or a native source/authority binding. The actual fixture catalog is fresh.
    from test_stage12_ra_g1_production_binding import source_inventory
    root=Path(__file__).resolve().parents[1]
    if root.stat().st_mode & 0o077:
        pytest.skip("Installed audit case requires the explicit private0700 source fixture")
    return root, source_inventory()


from test_stage12_ra_g1_production_binding import production, installed_production_audit  # noqa: E402,F401


def test_map_and_real_admission_capture_under_installed_production_audit(production,offline,monkeypatch):
    from test_stage12_public_sampling_contract import ap_inputs,TestOnlyAuthority
    from test_stage12_public_operations_v2 import FakeClock,H,KEY
    from safe_geocoding_pipeline.preprocessing import stage12_probe_cli as cli
    from safe_geocoding_pipeline.preprocessing.stages.s12_public_response import Validation
    case=production
    run=case.controller.Run(case.allocation,stage="bind",stage_seconds=720)
    p,plan,start,rows,inventory,bound=ap_inputs();clock=FakeClock()
    original=RuntimeError("SECRET_AUDITED_ADMISSION")
    class AdmissionAuthority(TestOnlyAuthority):
        def require(self,purpose,evidence,context):
            if purpose=="dispatch":raise original
            return super().require(purpose,evidence,context)
    real_close=sampling.Sampler.close
    def close_injected(s):
        with s.lock:
            clock.value=max(clock.value,s.last_observed+100_000_001)
            s.health(caller_context="CLOSE")
        return real_close(s)
    monkeypatch.setattr(sampling.Sampler,"close",close_injected)
    dispatches=[];seen=[]
    def forbidden_dispatch(*args):dispatches.append(1);raise AssertionError("NO_PROVIDER_TEST")
    try:
        with installed_production_audit(case,run,monkeypatch) as audit:
            run.mkdir(case.root)
            descriptor,auth=real_descriptor()
            assert not descriptor.preparation_uncertain
            owner=d.Failures(clock,closure=True,first_failure_descriptor=descriptor,sampling=True)
            original_record=owner.record
            def record(tag,error,**kwargs):
                if tag=="ADMISSION":seen.append(error)
                return original_record(tag,error,**kwargs)
            owner.record=record
            result=cli.run_operations_block(p,plan,start,work_factory=lambda:iter(rows),output=case.root/"audited_component",block_id=1,authority=AdmissionAuthority(bound),clock=clock,dispatch=forbidden_dispatch,runtime_inventory=inventory,runtime_key=KEY,control_adapters={},monitor=None,free_bytes=lambda:2**42,segment_authority=H,writer_exclusion_evidence=H,epoch=H,writer_release_evidence=H,task_deadline_ns=180_000_000_000,diagnostics=owner,public_validation=Validation())
            snapshot=owner.snapshot()
            assert audit["events"]>0 and auth._original_read_bytes>0
            assert seen[0] is original and not dispatches
            assert snapshot["first_initiating_failure"]["operation"]=="ADMISSION"
            assert snapshot["foreground_first_failure"]["first_failure"]["exception_class"]=="RUNTIME_ERROR"
            assert snapshot["foreground_first_failure"]["first_failure"]["frames"]
            assert snapshot["sampling_first_fault"]["first_fault"]["caller_context"]=="CLOSE"
            assert not result["report_complete"] and "SECRET" not in str(snapshot)
    finally:
        run.close()


def test_actual_acquisition_fault_precedes_later_foreground_observation():
    s,co,log,clock=owned()
    clock.value=100_000_001
    assert s.acquire() is True and s.failure=="ACQUISITION_GAP"
    first=dict(s.first_fault)
    clock.value+=17
    error=RuntimeError("SECRET_LATER_FOREGROUND")
    co.failures.record("ADMISSION",error,writer=s.writer)
    snapshot=co.failures.snapshot()
    assert snapshot["sampling_first_fault"]["first_fault"]==first
    assert first["check_mono_ns"]<snapshot["first_initiating_failure"]["mono_ns"]
    clock.value+=100_000_001
    s.health(caller_context="CLOSE")
    assert s.first_fault==first
    assert "SECRET" not in str(co.failures.snapshot())

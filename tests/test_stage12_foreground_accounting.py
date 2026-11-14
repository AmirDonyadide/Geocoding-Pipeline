"""TEST_ONLY accounted foreground pass; no live facts, workload or authority."""
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import threading
import types

import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_accounting as ac
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_assurance as assurance
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_contract as contract
from safe_geocoding_pipeline.preprocessing.stages import s12_public_diagnostics as diagnostics
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_public as public
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c
from safe_geocoding_pipeline.preprocessing.stages import s12_storage
from test_stage12_ra_g1_rep_first64_512 import upgrade as old_upgrade
from test_stage12_ra_g1_rep_admin_budget import allocation, preparer, diagnostic
from test_stage12_ra_g1_production_binding import (
    private_source, production, installed_production_audit, materialize,
)

ROOT = Path(__file__).resolve().parents[1]
FLAGS = dict(bootstrap_successor=True, shared_lease_successor=True,
             rep_admin_successor=True, first64_512_successor=True)
LEGACY_GOLDEN = {'strict_rep': '821afadc1d12b63128d9cfce070a4fd1ef046b58f2104f04e8c6059dc8e554dd', 'bootstrap_rep': 'dc477952f395a83ed634f86b844c86e77bf90a71c39c263b38c6de5e9e771d52', 'shared_rep': '2cfabe2ad63aa6e1e44c4cd9586f465f52c8d3711002c07ad740c74143c2fad6', 'admin_rep': 'cb88bbc11b42850a98b90df33a23ac7a8e6a7a54532aaf811ceacf2042ce8c82', 'rep512': '3f260fb4c780c9c0bbd7637705fbd1c04bcc0a9be7884b24ae299fe6928f566e', 'public_shared': 'a72a6d7f486c4a4149925e4689a924c6c00488d0eafafaa4ec861ccf990e5de9'}


def inputs():
    rows = [dict(path=p, bytes=i+1, sha256="a"*64)
            for i, (_,p) in enumerate(ac.FOREGROUND_MEMBERS)]
    rows.sort(key=lambda row:row["path"])
    backends = [dict(ordinal=i,module=m,path="/fixture/linux/"+m+".so",
        identity=dict(device=1,inode=i,mode=0o100600,uid=1,gid=1,nlink=1,
                      bytes=17,mtime_ns=1,ctime_ns=1),
        stat_scope="PREPARATION_HOST_SNAPSHOT",sha256="a"*64)
        for i,m in enumerate(ac.MODULES,1)]
    return rows, backends


def compile_new(rows, backends):
    return ac.compile_inventory(rows,backends,ac.SCOPES[0],foreground_successor=True,**FLAGS)


def upgrade(value):
    value = old_upgrade(value)
    value["version"] = allocation.REP_FOREGROUND_VERSION
    value["accounting_inventory"], value["accounting"] = compile_new(
        value["source_files"],value["accounting_inventory"]["backends"])
    return value


def test_legacy_compiler_bytes_and_descriptors_are_frozen():
    rows, backends = inputs()
    cases = [("strict_rep",ac.SCOPES[0],{}),
        ("bootstrap_rep",ac.SCOPES[0],dict(bootstrap_successor=True)),
        ("shared_rep",ac.SCOPES[0],dict(shared_lease_successor=True)),
        ("admin_rep",ac.SCOPES[0],dict(bootstrap_successor=True,shared_lease_successor=True,rep_admin_successor=True)),
        ("rep512",ac.SCOPES[0],FLAGS),("public_shared",ac.SCOPES[1],dict(shared_lease_successor=True))]
    for name,scope,flags in cases:
        inv,_ = ac.compile_inventory(rows,backends,scope,**flags)
        assert ac.digest(inv) == LEGACY_GOLDEN[name]
        assert not any(row["component"].startswith("REP_FOREGROUND") for row in inv["cost_rows"])
    for name,value in contract.descriptors(rep_admin_successor=True,first64_512_successor=True).items():
        assert (ROOT/"docs/scientific_assets"/(name+".json")).read_bytes()==c.canonical(value)


def test_only_stage1_is_funded_once_with_exact_selected_bytes():
    rows, backends = inputs()
    old,oldtotals = ac.compile_inventory(rows,backends,ac.SCOPES[0],**FLAGS)
    new,totals = compile_new(rows,backends)
    assert ac.validate_inventory(new)==new
    assert tuple(ac.FOREGROUND_MEMBERS)==diagnostics.FOREGROUND_MODULES
    assert new["schema_version"]==ac.REP_FOREGROUND_VERSION
    assert new["cost_rows"][:-1]==old["cost_rows"]
    added = new["cost_rows"][-1]
    n,s=len(rows),sum(row["bytes"] for row in rows)
    parents=sum(len(Path(row["path"]).parts)-1 for row in rows)
    assert added["stage_id"]==1 and added["invocations"]==1
    assert added["original_read_calls"]==added["original_read_bytes"]==s+n
    assert added["check_calls"]==8*(s+n)+4*parents+272*n
    assert new["stage_accounting"][1:]==old["stage_accounting"][1:]
    for key in ac.ACCOUNTING_KEYS:
        delta=added["check_calls"] if key in ("identity_calls","check_calls") else added[key]
        assert totals[key]-oldtotals[key]==delta
        assert new["stage_accounting"][0][key]-old["stage_accounting"][0][key]==delta
    assert new["monitor_streams"]==old["monitor_streams"]
    assert new["rep_first64_512"]==old["rep_first64_512"]
    assert new["rep_foreground"]["maximum_extra_snapshot_bytes"]==4096
    assert new["rep_foreground"]["existing_summary_reservation_bytes"]==2**20


@pytest.mark.parametrize("missing",tuple(FLAGS))
def test_no_partial_successor_flags(missing):
    rows,backends=inputs();flags=dict(FLAGS);flags[missing]=False
    with pytest.raises(ac.AccountingError):
        ac.compile_inventory(rows,backends,ac.SCOPES[0],foreground_successor=True,**flags)


@pytest.mark.parametrize("scope",ac.SCOPES[1:])
def test_no_public_or_protected_map_funding(scope):
    rows,backends=inputs()
    with pytest.raises(ac.AccountingError):
        ac.compile_inventory(rows,backends,scope,foreground_successor=True,**FLAGS)


def test_exact_1mib_and_missing_member_and_mutated_inventory():
    rows,backends=inputs()
    for row in rows:row["bytes"]=0
    rows[0]["bytes"]=2**20
    inv,_=compile_new(rows,backends)
    assert inv["rep_foreground"]["selected_source_bytes"]==2**20
    rows[0]["bytes"]+=1
    with pytest.raises(ac.AccountingError):compile_new(rows,backends)
    rows,backends=inputs()
    with pytest.raises(ac.AccountingError):compile_new(rows[:-1],backends)
    inv,_=compile_new(rows,backends)
    for field in ("selected_source_bytes","maximum_passes_per_process","maximum_extra_snapshot_bytes"):
        changed=deepcopy(inv);changed["rep_foreground"][field]+=1
        with pytest.raises(ac.AccountingError):ac.validate_inventory(changed)
    changed=deepcopy(inv);changed["schema_version"]=ac.REP512_VERSION
    with pytest.raises(ac.AccountingError):ac.validate_inventory(changed)


@pytest.mark.parametrize("input_version,resource_version,valid",[
    (diagnostic.REP512_VERSION,assurance.REP512_SELECTION,True),
    (diagnostic.REP_FOREGROUND_VERSION,assurance.REP_FOREGROUND_SELECTION,True),
    (diagnostic.REP512_VERSION,assurance.REP_FOREGROUND_SELECTION,False),
    (diagnostic.REP_FOREGROUND_VERSION,assurance.REP512_SELECTION,False),
])
def test_exact_input_resource_pair(input_version,resource_version,valid):
    selected=dict(scope=allocation.SCOPE,schema_version=resource_version)
    if valid:diagnostic.validate_resource_family(input_version,selected)
    else:
        with pytest.raises(RuntimeError):diagnostic.validate_resource_family(input_version,selected)


def source_authority(root,rows,deadline):
    owner=public.Authority.__new__(public.Authority)
    owner.repository=root;owner.review={"source_files":rows}
    owner._source_root_identity=assurance.private_root_identity(root)
    owner._deadline_check=deadline;owner._lock=threading.RLock()
    owner._source_counter_ledger=None;owner._local_read_calls=owner._local_read_bytes=0
    owner._local_enforcement_checks=0;owner._read_call_limit=owner._read_byte_limit=None
    return owner


def test_actual_source_map_positive_one_byte_eof_and_prefix_carry(tmp_path,monkeypatch):
    root=tmp_path/"TEST_ONLY_SOURCE";root.mkdir(mode=0o700)
    rows=[];specs=[]
    for module_id,relative in diagnostics.FOREGROUND_MODULES:
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        raw=b"def fail():\n    raise RuntimeError('TEST_ONLY')\n"
        path.write_bytes(raw);path.chmod(0o600)
        rows.append(dict(path=relative,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        module=types.ModuleType("TEST_ONLY_"+module_id);module.__file__=str(path)
        exec(compile(raw,str(path),"exec"),module.__dict__);specs.append((module_id,module))
    rows.sort(key=lambda row:row["path"])
    checks=[0];real_require=c.require;real_read=os.read
    def counted_require(ok,code="STAGE12_INVALID"):
        checks[0]+=1;return real_require(ok,code)
    monkeypatch.setattr(c,"require",counted_require)
    owner=source_authority(root,rows,lambda: c.require(True))
    before=owner.source_counter_snapshot()
    monkeypatch.setattr(os,"read",lambda fd,n:real_read(fd,min(n,1)))
    descriptor=diagnostics.prepare_first_failure_descriptor(specs,rows,source_root=root,
        verify_source=owner.verify_diagnostic_source)
    assert descriptor.preparation_uncertain is False
    after=owner.source_counter_snapshot()
    total=sum(row["bytes"] for row in rows)
    assert after["source_read_calls"]-before["source_read_calls"]==total+14
    assert after["source_read_bytes"]-before["source_read_bytes"]==total
    parents=sum(len(Path(row["path"]).parts)-1 for row in rows)
    assert checks[0] <= 8*(total+14)+4*parents+272*14
    # The existing handoff adds rather than overwrites local counters. Later
    # empty phases retain them; neither the descriptor nor its reads repeat.
    owner.add_source_counter_prefix(dict(source_read_calls=7,source_read_bytes=11,identity_checks=3))
    carried=owner.source_counter_snapshot()
    assert carried["source_read_calls"]==total+14+7
    assert carried["source_read_bytes"]==total+11
    assert owner.source_counter_snapshot()==carried
    try:specs[0][1].fail()
    except RuntimeError as error:captured=descriptor.capture(error)
    assert len(c.canonical(captured))<4096


@pytest.mark.parametrize("change",["grow","truncate","mutate","unsafe_parent","deadline"])
def test_actual_reader_failures_stay_failures(tmp_path,monkeypatch,change):
    root=tmp_path/"TEST_ONLY_SOURCE";root.mkdir(mode=0o700)
    path=root/"src/member.py";path.parent.mkdir(mode=0o700)
    raw=b"abcdefgh";path.write_bytes(raw);path.chmod(0o600)
    row=dict(path="src/member.py",bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    ticks=[0]
    def deadline():
        ticks[0]+=1
        if change=="deadline" and ticks[0]>=3:raise TimeoutError()
    owner=source_authority(root,[row],deadline)
    if change=="unsafe_parent":path.parent.chmod(0o777)
    real_read=os.read;changed=[False]
    def read(fd,n):
        value=real_read(fd,min(n,1))
        if value and not changed[0]:
            changed[0]=True
            if change=="grow":path.write_bytes(raw+b"z")
            elif change=="truncate":path.write_bytes(b"")
            elif change=="mutate":path.write_bytes(b"XXXXXXXX")
        return value
    monkeypatch.setattr(os,"read",read)
    with pytest.raises((c.Stage12Error,TimeoutError)):
        owner.verify_diagnostic_source(path,row)
    counts=owner.source_counter_snapshot()
    assert counts["source_read_calls"]<=len(raw)+1
    assert counts["source_read_bytes"]<=len(raw)+1


def test_actual_new_builder_audit_exact_gates_and_mixed_accounting(production,monkeypatch):
    case=production;case.allocation=upgrade(case.allocation)
    data,objects=case.preparer.build(case.allocation,case.bootstrap,**case.kwargs)
    case.allocation["resource_selection_sha256"]=allocation.digest(objects["resource_selection"])
    case.controller.validate_selection(case.allocation)
    assert data["version"]==diagnostic.REP_FOREGROUND_VERSION
    assert objects["resource_selection"]["schema_version"]==assurance.REP_FOREGROUND_SELECTION
    assert data["limits"]["summary_reserve_bytes"]==2**20
    run=case.controller.Run(case.allocation,stage="bind",stage_seconds=720)
    try:
        with installed_production_audit(case,run,monkeypatch):
            bundle=materialize(run,case,data,objects)
            actual=case.controller.parse(run.original(case.allocation["paths"]["input"]))
            case.diagnostic.validate_envelope(actual,case.allocation["source_sha"],for_execution=False)
            case.diagnostic.validate_resource_family(actual["version"],objects["resource_selection"])
            class Originals:
                def read(self,path,*,limit,original):return run.original(path,limit=limit)
            with s12_storage.read_view(Originals()):case.diagnostic.validate_grants(actual,bundle)
    finally:run.close()
    for allocation_version,inventory_new in [(allocation.REP512_VERSION,True),(allocation.REP_FOREGROUND_VERSION,False)]:
        changed=deepcopy(case.allocation);changed["version"]=allocation_version
        if not inventory_new:
            changed["accounting_inventory"],changed["accounting"]=ac.compile_inventory(changed["source_files"],changed["accounting_inventory"]["backends"],allocation.SCOPE,**FLAGS)
        with pytest.raises(RuntimeError):case.controller.validate_selection(changed)


def test_new_assets_exact_and_no_legacy_map_call():
    assert allocation.descriptor(allocation.REP_FOREGROUND_VERSION)["required_resource_selection"]==assurance.REP_FOREGROUND_SELECTION
    runtime.verify_successor_assets(ROOT,contract=contract,rep_admin_successor=True,
        first64_512_successor=True,foreground_successor=True)
    for version,value in [(allocation.REP_FOREGROUND_VERSION,allocation.descriptor(allocation.REP_FOREGROUND_VERSION)),
                          (diagnostic.REP_FOREGROUND_VERSION,diagnostic.descriptor(diagnostic.REP_FOREGROUND_VERSION))]:
        assert (ROOT/"docs/scientific_assets"/(version+".json")).read_bytes()==c.canonical(value)
    # Actual map invocation expression is guarded by the explicit funded family.
    import ast
    tree=ast.parse((ROOT/"scripts/stage12_ra_g1_diagnostic.py").read_text())
    execute=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=="execute")
    value=next(n.value for n in execute.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=="foreground_descriptor" for t in n.targets))
    assert isinstance(value,ast.IfExp)
    calls=[]
    env=dict(prepare_first_failure_descriptor=lambda *a,**k:calls.append(True),foreground_specs=[],original=types.SimpleNamespace(review={"source_files":[]},verify_diagnostic_source=None),source=ROOT,
        REP_FOREGROUND_VERSION=diagnostic.REP_FOREGROUND_VERSION,
        REP_ACK_VERSION=diagnostic.REP_ACK_VERSION,
        REP_FAIR_VERSION=diagnostic.REP_FAIR_VERSION,
        REP_COVERAGE_VERSION=diagnostic.REP_COVERAGE_VERSION)
    expression=ast.Expression(value);ast.fix_missing_locations(expression)
    for version in (diagnostic.REP512_VERSION,diagnostic.REP_FOREGROUND_VERSION):
        env["data"]={"version":version};eval(compile(expression,"TEST_ONLY_ACTUAL_FUNDED_EXPRESSION","eval"),env)
    assert calls==[True]


def test_actual_foreground_handoff_and_resealed_cross_families(production,monkeypatch):
    import test_stage12_ra_g1_review_handoff as legacy
    monkeypatch.setattr(legacy,"upgrade",upgrade)
    case=legacy.handoff.__wrapped__(production)
    selected=case.controller.parse(case.selection_raw)
    assert selected["version"]==allocation.REP_FOREGROUND_VERSION
    resource=case.controller.parse(case.originals["resource_selection"])
    assert resource["schema_version"]==assurance.REP_FOREGROUND_SELECTION
    keys={key:case.plan_kwargs[key] for key in ("selection_sha256","source_sha","job_id")}
    prepared=legacy.helper.preparation_plan(case.selection_raw,**keys)
    assert prepared["max_external_units"]==5
    planned=case.plan()
    assert planned["raw_sha256"]==hashlib.sha256(case.release).hexdigest()
    assert planned["max_external_units"]==11
    for old_selection,new_resource in ((False,False),(True,True)):
        chosen=deepcopy(case.allocation)
        chosen["version"]=allocation.REP512_VERSION if old_selection else allocation.REP_FOREGROUND_VERSION
        chosen["accounting_inventory"],chosen["accounting"]=ac.compile_inventory(
            chosen["source_files"],chosen["accounting_inventory"]["backends"],allocation.SCOPE,
            foreground_successor=not old_selection,**FLAGS)
        other=deepcopy(resource)
        other["schema_version"]=assurance.REP_FOREGROUND_SELECTION if new_resource else assurance.REP512_SELECTION
        assurance.validate_selection(other)
        originals=dict(case.originals,resource_selection=case.controller.canonical(other))
        chosen["resource_selection_sha256"]=case.controller.digest(other)
        selected_raw=case.controller.canonical(chosen)
        release=case.controller.parse(case.release)
        release["selection_sha256"]=legacy.helper.sha(selected_raw)
        release["resource_selection_sha256"]=case.controller.digest(other)
        release_raw=case.controller.canonical(release)
        kwargs=dict(case.plan_kwargs,selection_sha256=legacy.helper.sha(selected_raw),
                    reviewer_release_sha256=legacy.helper.sha(release_raw))
        with pytest.raises(RuntimeError,match="^RA_G1_HANDOFF_POLICY$"):
            legacy.helper.publication_plan(selected_raw,release_raw,originals,**kwargs)


def test_fixed_snapshot_schema_maximum_stays_inside_4k_summary_sublimit():
    # Deliberately maximal fixed-schema scalar fixture. These are TEST_ONLY
    # serialization operands, never captured facts or a permissible live record.
    descriptor=diagnostics.FirstFailureDescriptor()
    descriptor.source_map_sha256="f"*64
    descriptor.preparation_uncertain=False
    class Clock:
        def now_ns(self):return 1
    owner=diagnostics.Failures(Clock(),first_failure_descriptor=descriptor,sampling=True)
    owner.foreground_first=dict(exception_class=max((label for _,label in diagnostics._FOREGROUND_CLASSES),key=len),
        frames=[dict(module=max((m for m,_ in diagnostics.FOREGROUND_MODULES),key=len),
                     function="f"*128,source_sha256="f"*64,line=2**32-1) for _ in range(4)],
        visited=32,mapped=32,unmapped=32,traceback_unavailable=False,
        traversal_truncated=False,leaf_frames_truncated=False,retention_uncertain=False)
    owner.foreground_faults=2**64-1
    row=dict(version=diagnostics.SAMPLING_FAULT_VERSION,bound_ns=100000000)
    row.update((key,max(values,key=len)) for key,values in diagnostics._SAMPLING_TAGS.items())
    row.update((key,2**64-1) for key in diagnostics._SAMPLING_NUMBERS)
    owner.record_sampling_fault(row);owner.sampling_faults=2**64-1
    value=owner.snapshot()
    added={key:value[key] for key in ("foreground_first_failure","sampling_first_fault")}
    assert len(c.canonical(added))<=4096
    assert ac.descriptor(first64_512_successor=True,foreground_successor=True)["maximum_extra_snapshot_bytes"]==4096

"""Invented A-only accounting fixtures; no live authority/runtime proof."""
from copy import deepcopy
from pathlib import Path
import hashlib
import os
import pytest

from safe_geocoding_pipeline.preprocessing.stages import s12_a2_accounting as c
from test_stage12_wf_ap2_bootstrap_a2 import a, environment, denied, private, write, kernel, make_review


@pytest.fixture(autouse=True)
def invented_runtime_location(tmp_path,monkeypatch):
    # Explicit synthetic runtime directory; no live record or CLI bypass.
    monkeypatch.setattr(c,'runtime_roots',lambda:(tmp_path.resolve(),))


def inventory(root, *, blocks=2):
    backends=[]
    for ordinal,name in enumerate(c.MODULES,1):
        p=root/('native_'+str(ordinal));p.write_bytes(bytes([ordinal])*4096*blocks);p.chmod(0o600)
        backends.append(dict(ordinal=ordinal,module=name,path=str(p),identity=c.identity(p.stat()),stat_scope='PREPARATION_HOST_SNAPSHOT',sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    source=root/'source';source.write_bytes(b'original source');source.chmod(0o600)
    return dict(version=c.VERSION,backends=backends,sources=[dict(path='source',bytes=source.stat().st_size)])


def test_all_backends_beyond_old_4096_checks_real_bytes(tmp_path):
    v=inventory(tmp_path.resolve(),blocks=1025)  #20MiB, finite disk/buffers
    ledger=c.Ledger(v,'collect');calls=0
    def check():
        nonlocal calls
        calls+=1;ledger.tick()
    for row in v['backends']:
        got=ledger.backend(row['module'],Path(row['path']),check)
        h=hashlib.sha256()
        with Path(row['path']).open('rb') as f:
            while data:=f.read(4096):h.update(data)
        assert got==h.hexdigest()
    assert calls>4096 and ledger.completed_bytes==5*1025*4096
    assert ledger.backend_calls==5 and ledger.read_calls==5*(1025+1)


def test_derived_exact_check_boundary_and_no_final_refund(tmp_path):
    v=inventory(tmp_path.resolve());x=c.Ledger(v,'collect');x.checks=x.bound['collect_checks']-1
    x.tick();assert x.checks==x.bound['collect_checks']
    with pytest.raises(c.AccountingError,match='DERIVED_CHECK_LIMIT'):x.tick()
    final=c.Ledger(v,'final');assert final.snapshot()['cumulative_checks_reserved']==x.bound['collect_checks']+x.bound['final_checks']


@pytest.mark.parametrize('change',['grow','truncate','content','ancestor'])
def test_change_during_original_read_rejected_and_fd_closed(tmp_path,change):
    root=private(tmp_path.resolve()/'base');v=inventory(root);row=v['backends'][0];x=c.Ledger(v,'collect');first=True;seen=[]
    def read(fd,buffers):
        nonlocal first
        seen.append(fd)
        n=os.readv(fd,buffers)
        if first:
            first=False
            p=Path(row['path'])
            if change=='grow':
                with p.open('ab') as f:f.write(b'new')
            elif change=='truncate':p.write_bytes(b'short')
            elif change=='content':
                with p.open('r+b') as f:f.write(b'changed')
            else:
                other=root.with_name('moved');root.rename(other);root.symlink_to(other,target_is_directory=True)
        return n
    with pytest.raises(c.AccountingError):
        x._hash(row['path'],row['identity']['bytes'],x.tick,row['identity'],reader=read)
    for fd in set(seen):
        with pytest.raises(OSError):os.fstat(fd)


@pytest.mark.parametrize('failure',['deadline','resource'])
def test_per_read_guards_propagate_and_progress_is_retained(tmp_path,failure):
    v=inventory(tmp_path.resolve());x=c.Ledger(v,'collect');n=0
    def check():
        nonlocal n
        n+=1;x.tick()
        if n==3:raise RuntimeError(failure)
    with pytest.raises(RuntimeError,match=failure):x.backend(c.MODULES[0],Path(v['backends'][0]['path']),check)
    row=x.snapshot();assert row['backend_ordinal']==1 and row['completed_bytes']==4096 and row['checks']==3


@pytest.mark.parametrize('mutation',['missing','duplicate','extra','bad_size','bool_size','uint64_inode'])
def test_closed_inventory_no_missing_defaults(tmp_path,mutation):
    v=inventory(tmp_path.resolve());rows=[dict(path='source',sha256='a'*64)]
    if mutation=='missing':del v['backends'][0]['identity']['bytes']
    if mutation=='duplicate':v['backends'][1]=deepcopy(v['backends'][0])
    if mutation=='extra':v['backends'].append(deepcopy(v['backends'][0]))
    if mutation=='bad_size':v['sources'][0]['bytes']=-1
    if mutation=='bool_size':v['sources'][0]['bytes']=True
    if mutation=='uint64_inode':
        v['backends'][0]['identity']['inode']=2**63+17;c.validate(v,rows);return
    with pytest.raises(c.AccountingError):c.validate(v,rows)


def test_short_reads_and_eof_are_finitely_accounted(tmp_path):
    v=inventory(tmp_path.resolve());x=c.Ledger(v,'collect');row=v['backends'][0]
    def short(fd,buffers):return os.readv(fd,[buffers[0][:1]])
    got=x._hash(row['path'],row['identity']['bytes'],x.tick,row['identity'],reader=short)
    assert got==hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()
    assert x.read_calls==row['identity']['bytes']+1


def version2(e,tmp_path,*,blocks=3):
    root=private(tmp_path.resolve()/'backends');v=inventory(root,blocks=blocks)
    selected=a.s.parse((Path.cwd()/a.ACCOUNTING_ASSET).read_bytes())['source_paths']
    rows=[]
    for name in selected:
        p=Path(e.value['paths']['source'])/name;p.parent.mkdir(parents=True,exist_ok=True)
        write(p,(Path.cwd()/name).read_bytes(),raw=True)
        rows.append(dict(path=name,sha256=a.s.sha(p.read_bytes())))
    e.value['source_files']=rows
    v['sources']=[dict(path=r['path'],bytes=(Path(e.value['paths']['source'])/r['path']).stat().st_size) for r in e.value['source_files']]
    e.value.update(version=a.VERSION2,accounting_inventory=v)
    old=next(p for p in e.records.iterdir() if p.suffix=='.json');own=a.s.parse(old.read_bytes());own['selection_scope_sha256']=a.selection_scope(e.value)
    raw=a.s.canonical(own);token=a.s.sha(raw);write(e.records/(token+'.json'),raw,raw=True);e.value['owner_sha256']=token
    e.token=write(e.selection,e.value);a.validate_selection(e.value)
    return v


def test_full_collection_to_final_actual_opener_with_fresh_backend_passes(environment,tmp_path):
    e=environment;v=version2(e,tmp_path,blocks=1025)
    def runtime(*args,**kw):
        backends=[]
        for row in v['backends']:
            digest=kw['backend_reader'](row['module'],Path(row['path']),kw['check'])
            backends.append(dict(module=row['module'],binary_name=Path(row['path']).name,binary_sha256=digest))
        return dict(scope='INVENTED_TEST_ONLY',wf_ap2_runtime=dict(backends=backends))
    def guarded_kernel(**kw):
        for _ in range(256):kw['check']()
        return kernel()
    result=a.collect(e.value,e.selection,e.token,kernel_reader=guarded_kernel,inventory_reader=runtime,probe=e.probe,thread_reader=lambda:1,install_guard=False)
    assert result['accounting']['backend_calls']==5 and result['accounting']['source_calls']==2
    make_review(e)
    final=a.finalize(e.value,e.selection,e.token,thread_reader=lambda:1,probe=e.probe,install_guard=False)
    assert final['result']['B']=='DISABLED'
    assert final['accounting']['backend_calls']==15 and final['accounting']['source_calls']==3
    assert final['accounting']['phase_ordinal']==c.PHASES.index('FINISHED')
    bounds=c.bounds(v)
    assert final['accounting']['cumulative_checks_reserved']==bounds['collect_checks']+bounds['final_checks']
    assert final['accounting']['completed_bytes']==3*bounds['backend_bytes_per_pass']+3*bounds['source_bytes_per_pass']
    c.validate_prefix(final['accounting'],v,'terminal')
    with pytest.raises(a.s.AllocationError,match='REOPEN_ACCOUNTING_REQUIRED'):
        a.open_completed(e.value,e.token,probe=e.probe)
    mirror=a.open_completed(e.value,e.token,bootstrap_root=e.value['paths']['bootstrap'],records_root=e.value['paths']['records'],final_root=e.value['paths']['final'],mirror_only=True)
    assert mirror['verification_scope']=='STRUCTURAL_MIRROR_ONLY_NOT_EXECUTION_QUALIFICATION'
    with pytest.raises(a.s.AllocationError):a.s.validate_selection(e.value)


@pytest.mark.parametrize('kind',['deadline','resource'])
def test_actual_phase_guard_fails_during_hash(environment,tmp_path,monkeypatch,kind):
    from types import SimpleNamespace
    e=environment;v=version2(e,tmp_path);clock=[1];rss=[1]
    monkeypatch.setattr(a.resource,'getrusage',lambda *x:SimpleNamespace(ru_maxrss=rss[0]))
    check,_,_=a.phase_checks(e.value,0,120,clock=lambda:clock[0],thread_reader=lambda:1)
    ledger=a._ACTIVE_LEDGER;read=os.readv
    def injected(fd,buffers):
        n=read(fd,buffers)
        if kind=='deadline':clock[0]=121*10**9
        else:rss[0]=2**40
        return n
    monkeypatch.setattr(c.os,'readv',injected)
    with pytest.raises(a.s.AllocationError,match='PHASE_DEADLINE' if kind=='deadline' else 'OBSERVED_RESOURCE_LIMIT'):
        ledger.backend(c.MODULES[0],Path(v['backends'][0]['path']),check)
    assert ledger.snapshot()['completed_bytes']==4096


def test_cross_host_stat_scope_still_checks_exact_content(tmp_path):
    v=inventory(tmp_path.resolve());row=v['backends'][0]
    row['identity']['device']+=17;row['identity']['inode']=2**63+128
    x=c.Ledger(v,'collect');assert x.backend(c.MODULES[0],Path(row['path']),x.tick)==row['sha256']
    x=c.Ledger(v,'collect');row['sha256']='0'*64
    with pytest.raises(c.AccountingError,match='BACKEND_HASH_CHANGED'):
        x.backend(c.MODULES[0],Path(row['path']),x.tick)


def test_legacy_and_optin_runtime_facts_exact_native_hash_equivalence(tmp_path,monkeypatch):
    import importlib
    from types import SimpleNamespace
    from safe_geocoding_pipeline.preprocessing.stages import s12_wf_ap2_assurance as m
    v=inventory(tmp_path.resolve());paths={row['module']:row['path'] for row in v['backends']}
    load=importlib.import_module
    monkeypatch.setattr(importlib,'import_module',lambda name:SimpleNamespace(__file__=paths[name]) if name in paths else load(name))
    legacy=m.runtime_facts()
    x=c.Ledger(v,'collect');selected=m.runtime_facts(check=x.tick,backend_reader=x.backend)
    assert legacy==selected


def test_v2_uncertain_writer_never_publishes(environment,tmp_path,monkeypatch):
    e=environment;version2(e,tmp_path);old=a.MetadataWriter.call;calls=[0]
    def uncertain(self,action):
        calls[0]+=1
        if calls[0]==3:
            self.poisoned.set();raise a.FutureTimeout()
        return old(self,action)
    monkeypatch.setattr(a.MetadataWriter,'call',uncertain)
    with pytest.raises(a.FutureTimeout):
        a.collect(e.value,e.selection,e.token,kernel_reader=kernel,inventory_reader=lambda *x,**kw:None,probe=e.probe,thread_reader=lambda:1,install_guard=False)
    assert not Path(e.value['paths']['bootstrap'],'manifest.json').exists()
    assert not Path(e.value['paths']['final']).exists()
    assert a._ACTIVE_LEDGER.snapshot()['phase_ordinal']==c.PHASES.index('KERNEL_PRE')


def test_v2_missing_imported_source_rejected(environment,tmp_path):
    e=environment;version2(e,tmp_path)
    # Remove an actual imported dependency that legacy minimum did not list.
    name=next(r['path'] for r in e.value['source_files'] if r['path'] not in a.REQUIRED and r['path'] not in (a.ACCOUNTING_SOURCE,a.ACCOUNTING_ASSET))
    e.value['source_files']=[r for r in e.value['source_files'] if r['path']!=name]
    e.value['accounting_inventory']['sources']=[r for r in e.value['accounting_inventory']['sources'] if r['path']!=name]
    with pytest.raises(a.s.AllocationError,match='ACCOUNTING_SOURCE_SET'):a.validate_selection(e.value)


def test_impossible_byte_chunk_read_check_watermarks_rejected(tmp_path):
    v=inventory(tmp_path.resolve());x=c.Ledger(v,'collect');row=x.snapshot()
    row.update(phase_ordinal=c.PHASES.index('CAPTURE_CLOSE'),backend_calls=5,backend_pass_ordinal=1,source_calls=2,completed_bytes=23,read_bytes=23,completed_chunks=0,read_calls=0,checks=0)
    with pytest.raises(c.AccountingError):c.validate_watermarks(row,v)
    with pytest.raises(c.AccountingError):c.validate_prefix(row,v,'capture')


def test_arbitrary_accounting_exception_argument_never_echoed(environment,tmp_path,monkeypatch,capsys):
    e=environment;version2(e,tmp_path);marker='SYNTHETIC_TOKEN_MUST_NOT_ECHO'
    monkeypatch.setattr(a.sys,'argv',['a2','collect','--selection',str(e.selection),'--selection-sha256',e.token])
    monkeypatch.setattr(a,'validate_environment',lambda *x:None)
    def bad(*x,**kw):raise c.AccountingError(marker)
    monkeypatch.setattr(a,'collect',bad)
    assert a.main()==2
    captured=capsys.readouterr();assert marker not in captured.out+captured.err
    assert 'A2_UNKNOWN_FAILURE' in captured.err

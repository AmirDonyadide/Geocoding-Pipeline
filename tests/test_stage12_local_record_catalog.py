"""Portable catalog boundary checks with actual controller/readers.

All roles, source hashes and permissions here are TEST_ONLY fixtures. The
separate connected task replay exercises the genuine native-path configuration.
"""
from pathlib import Path
import hashlib
import types
import pytest
from test_stage12_ra_g1_allocation_controller import world
from test_stage12_public_operations_v2 import offline

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'scripts/stage12_ra_g1_task_assets/prearmed_handoff.py'
BASE_SOURCE='9952818fdbdc7df55e73dd11536165af2dc46eb6'


def operations(world):
    raw=TEMPLATE.read_bytes()
    old=('SOURCE = "'+BASE_SOURCE+'"').encode()
    assert raw.count(old)==1
    # Exact, explicit TEST_ONLY instance of the existing closed source render.
    rendered=raw.replace(old,('SOURCE = "'+world.s['source_sha']+'"').encode(),1)
    module=types.ModuleType('TEST_ONLY_local_catalog_operations')
    module.__file__=str(TEMPLATE)
    exec(compile(rendered,str(TEMPLATE),'exec'),module.__dict__)
    return module


def make_catalog(world):
    h=operations(world)
    world.root.mkdir(mode=0o700)
    raw=world.m.canonical(world.s)
    reference=h.create_local_catalog(raw,world.records,world.root/'catalog',world.root/'CATALOG.record',world.m)
    value=h.LocalRecordCatalog(reference,world.s,h.sha(raw),world.m)
    return h,value,reference


def test_catalog_complete_originals_and_native_path_remain_distinct(world):
    h,value,reference=make_catalog(world)
    for name,expected in world.objects.items():
        assert value.role(name)==expected
    expected=world.objects['software_review']['report_sha256']
    assert h.sha(value.report(expected))==expected
    manifest=h.parse(h.ref(reference,65536))
    assert manifest['native_records_dir']==world.s['paths']['records']
    assert value.root!=world.records and set(value.rows)==set(h.LOCAL_CATALOG_ROLES)
    assert all(len(row['identity'])==9 for row in value.rows.values())


@pytest.mark.parametrize('role',['adoption','project_approval','resource_review','software_review'])
def test_fresh_role_mutation_is_rejected_without_cached_acceptance(world,role):
    h,value,_=make_catalog(world)
    target=value.root/value.rows[role]['filename']
    target.write_bytes(b'TEST_ONLY_SECRET')
    with pytest.raises(RuntimeError) as caught:value.role(role)
    diagnostic=h.catalog_diagnostic(caught.value)
    assert diagnostic['operation']=='ROLE_READ' and diagnostic['role']==role
    assert 'TEST_ONLY_SECRET' not in repr(diagnostic)


def test_catalog_reference_source_and_membership_cannot_be_reinterpreted(world):
    h,value,reference=make_catalog(world)
    manifest=h.parse(h.ref(reference,65536))
    manifest['source_sha']='f'*40
    bad=world.root/'WRONG_CATALOG.record'
    h.put(bad,h.canonical(manifest))
    with pytest.raises(RuntimeError,match='PREARMED_LOCAL_CATALOG_BINDING'):
        h.LocalRecordCatalog(dict(path=str(bad),sha256=h.sha(h.canonical(manifest))),world.s,h.sha(world.m.canonical(world.s)),world.m)
    h.put(value.root/'unselected.record',b'{}\n')
    with pytest.raises(RuntimeError):value.role('adoption')


def test_partial_catalog_write_preserves_originals_prefix_and_first_error(world,monkeypatch):
    h=operations(world);world.root.mkdir(mode=0o700)
    originals={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in world.records.iterdir()}
    actual=h.os.write;calls=0;primary=OSError(28,'TEST_ONLY_SECRET')
    def partial(fd,raw):
        nonlocal calls
        calls+=1
        if calls==1:return actual(fd,raw[:4])
        raise primary
    monkeypatch.setattr(h.os,'write',partial)
    with pytest.raises(OSError) as caught:
        h.create_local_catalog(world.m.canonical(world.s),world.records,world.root/'catalog',world.root/'CATALOG.record',world.m)
    assert caught.value is primary
    assert not (world.root/'CATALOG.record').exists()
    prefixes=list((world.root/'catalog').iterdir())
    assert len(prefixes)==1 and prefixes[0].stat().st_size==4
    assert {path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in world.records.iterdir()}==originals
    diagnostic=h.catalog_diagnostic(primary)
    assert diagnostic['operation']=='CREATE' and diagnostic['errno']==28 and 'TEST_ONLY_SECRET' not in repr(diagnostic)


def test_catalog_diagnostics_keep_first_safe_fields_and_drop_forged_attributes(world):
    h=operations(world);error=RuntimeError('PREARMED_LOCAL_CATALOG_CONTENT')
    h.catalog_error(error,'ROLE_READ','adoption');first=h.catalog_diagnostic(error)
    h.catalog_error(error,'BIND');assert h.catalog_diagnostic(error)==first
    forged=RuntimeError('TEST_ONLY_SECRET');forged.local_catalog_failure={'payload':'TEST_ONLY_SECRET'}
    assert h.catalog_diagnostic(forged) is None
    h.catalog_error(forged,'BIND')
    assert h.catalog_diagnostic(forged)['code']=='UNCLASSIFIED'
    assert 'TEST_ONLY_SECRET' not in repr(h.catalog_diagnostic(forged))

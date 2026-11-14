"""Exact missing FAIR diagnostic asset; no whole initializer/runtime claim."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest
from safe_geocoding_pipeline.preprocessing.stages import s12_public_runtime as runtime
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_rep_fair_contract as fair
from safe_geocoding_pipeline.preprocessing.stages import s12_retrieval_contract as c

REPO=Path(__file__).resolve().parents[1]
SOURCE=REPO/'scripts/stage12_ra_g1_diagnostic.py'
spec=importlib.util.spec_from_file_location('FAIR_asset_actual_diagnostic',SOURCE)
diagnostic=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostic)
MEMBER='docs/scientific_assets/'+diagnostic.REP_FAIR_VERSION+'.json'


def actual_lookup(source,data,*,include_asset_inventory=False):
 """Replay unchanged source-owned statements, explicitly not the initializer."""
 functions=[node for node in ast.walk(ast.parse(SOURCE.read_bytes()))if isinstance(node,ast.FunctionDef)and node.name=='initialize_current_runtime']
 assert len(functions)==1
 statements=functions[0].body[:2]if include_asset_inventory else functions[0].body[1:2]
 assert all(isinstance(node,ast.Expr)for node in statements)
 namespace=dict(diagnostic.__dict__,source=source,data=data,runtime=runtime,ap=diagnostic.contract_for_input(data))
 exec(compile(ast.Module(body=statements,type_ignores=[]),str(SOURCE),'exec'),namespace)


def test_committed_asset_is_exact_actual_canonical_producer_and_existing_caps():
 raw=(REPO/MEMBER).read_bytes();value=diagnostic.descriptor(diagnostic.REP_FAIR_VERSION)
 assert raw==diagnostic.canonical(value)
 assert hashlib.sha256(raw).hexdigest()=='17da65ae634fd16feb218cd4597856504f85873a9685212e6514287c34560a29'
 assert json.loads(raw)==value and raw.endswith(b'\n')
 assert value['maximum_creations']==204860 and value['maximum_event_files']==57237
 assert value['sampling_contract']=='s12_ra_g1_rep_fair_contract'
 assert value['representative_admin_seconds']==dict(collector=120,review=480,binder_complete=240,binder_process=720)
 assert value['required_resource_selection']==diagnostic.REP_FAIR_SELECTION
 # Existing public/strict/historical matched assets remain their original bytes.
 for version in (diagnostic.REP512_VERSION,diagnostic.REP_FOREGROUND_VERSION,diagnostic.REP_ACK_VERSION):
  assert(REPO/'docs/scientific_assets'/(version+'.json')).read_bytes()==diagnostic.canonical(diagnostic.descriptor(version))


@pytest.fixture
def genuine_input():
 path=os.environ.get('STAGE12_FAIR_MISSING_ASSET_INPUT')
 if path is None:pytest.skip('requires the exact retained input, never an invented historical replacement')
 p=Path(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
 try:
  before=os.fstat(fd);assert before.st_nlink==1 and before.st_size<=4*2**20
  raw=b''
  while len(raw)<before.st_size:
   part=os.read(fd,min(65536,before.st_size-len(raw)));assert part;raw+=part
  assert not os.read(fd,1)
  key=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  assert key(before)==key(os.fstat(fd))==key(p.lstat())
 finally:os.close(fd)
 assert hashlib.sha256(raw).hexdigest()=='b2af29634a97bf043e0ea29c9eea3333d51881f3aff71054d43ae849d971266d'
 value=json.loads(raw);assert value['version']==diagnostic.REP_FAIR_VERSION
 return value


def test_genuine_input_actual_two_statement_asset_boundary(genuine_input):
 actual_lookup(REPO,genuine_input,include_asset_inventory=True)
 diagnostic.validate_envelope(genuine_input,genuine_input['source_sha'],for_execution=True)
 assert diagnostic.contract_for_input(genuine_input)is fair


@pytest.mark.parametrize('damage',['missing','mutated','truncated','wrong_family'])
def test_actual_private_lookup_rejects_absent_or_changed_bytes(tmp_path,genuine_input,damage):
 target=tmp_path/MEMBER;target.parent.mkdir(mode=0o700,parents=True)
 raw=(REPO/MEMBER).read_bytes()
 if damage=='mutated':raw=raw.replace(b'204860',b'204861')
 elif damage=='truncated':raw=raw[:-1]
 elif damage=='wrong_family':raw=diagnostic.canonical(diagnostic.descriptor(diagnostic.REP_ACK_VERSION))
 if damage!='missing':target.write_bytes(raw);target.chmod(0o600)
 if damage=='missing':
  with pytest.raises(FileNotFoundError):actual_lookup(tmp_path,genuine_input)
 else:
  with pytest.raises(RuntimeError,match='RA_G1_DIAGNOSTIC_DESCRIPTOR_CHANGED'):actual_lookup(tmp_path,genuine_input)


@pytest.mark.parametrize('version',[diagnostic.REP_ACK_VERSION,diagnostic.REP_FOREGROUND_VERSION,'UNKNOWN'])
def test_actual_envelope_rejects_mixed_or_unknown_family(genuine_input,version):
 changed=deepcopy(genuine_input);changed['version']=version
 with pytest.raises(RuntimeError):diagnostic.validate_envelope(changed,changed['source_sha'],for_execution=True)

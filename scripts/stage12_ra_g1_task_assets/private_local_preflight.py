import os,stat,time
from pathlib import Path
VERSION="stage12_private_collection_preconditions_v3"
ROLES=("driver","driver/cancellation","final-originals","retained","transport")
class Rejected(RuntimeError):pass
def need(value,code):
 if not value:raise Rejected(code)
def prepare(root,tc,state=None):
 if state is None:state={}
 state.update(operation="ROOT_IDENTITY",role="ROOT")
 root=Path(root);need(root.is_absolute(),"LOCAL_SETUP_PATH")
 chain=tc.ancestors(root,links=False);before=root.lstat();tc.private(before,"DIR",os.geteuid(),os.getegid());root_identity=tc.ident(before)[:5]
 rows=[]
 for role in ROLES:
  state.update(operation="ROLE_PREPARE",role=role)
  path=root/role;tc.check_ancestors(chain);need(tc.ident(root.lstat())[:5]==root_identity,"LOCAL_SETUP_REPLACED")
  try:prior=path.lstat()
  except FileNotFoundError:prior=None
  if prior is None:
   path.mkdir(mode=0o700);created=True
   fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
   try:os.fsync(fd)
   finally:os.close(fd)
  else:created=False
  info=path.lstat();tc.private(info,"DIR",os.geteuid(),os.getegid())
  fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:
   need(tc.ident(os.fstat(fd))[:5]==tc.ident(info)[:5],"LOCAL_SETUP_REPLACED")
   members=[]
   with os.scandir(fd) as scan:
    for entry in scan:
     need(len(members)<2,"LOCAL_SETUP_UNEXPECTED_MEMBER");members.append(entry.name)
   need(set(members)<=({"cancellation"} if role=="driver" else set()),"LOCAL_SETUP_UNEXPECTED_MEMBER")
   need(tc.ident(path.lstat())[:5]==tc.ident(info)[:5],"LOCAL_SETUP_REPLACED")
  finally:os.close(fd)
  rows.append(dict(role=role,path=str(path),created=created,identity=list(tc.ident(info)[:5])))
 state.update(operation="FINAL_ROOT_VERIFY",role="ROOT")
 tc.check_ancestors(chain);need(tc.ident(root.lstat())[:5]==root_identity,"LOCAL_SETUP_REPLACED")
 for row in rows:
  state.update(operation="FINAL_ROLE_VERIFY",role=row["role"])
  path=Path(row["path"]);info=path.lstat();tc.private(info,"DIR",os.geteuid(),os.getegid())
  need(list(tc.ident(info)[:5])==row["identity"],"LOCAL_SETUP_REPLACED")
  fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:
   need(list(tc.ident(os.fstat(fd))[:5])==row["identity"],"LOCAL_SETUP_REPLACED")
   names=[]
   with os.scandir(fd) as scan:
    for ent in scan:
     need(len(names)<2,"LOCAL_SETUP_UNEXPECTED_MEMBER");names.append(ent.name)
   need(set(names)<=({"cancellation"} if row["role"]=="driver" else set()),"LOCAL_SETUP_UNEXPECTED_MEMBER")
   need(list(tc.ident(path.lstat())[:5])==row["identity"],"LOCAL_SETUP_REPLACED")
  finally:os.close(fd)
 state.update(operation="FINAL_ROOT_OBSERVATION",role="ROOT")
 need(tc.ident(root.lstat())[:5]==root_identity,"LOCAL_SETUP_REPLACED")
 state.update(operation="PROTOCOL_OWNERSHIP",role="driver")
 forbidden=root/"driver/one-shot-probes"
 need(not forbidden.exists() and not forbidden.is_symlink(),"LOCAL_SETUP_PROTOCOL_OWNERSHIP")
 return dict(version=VERSION,status="PASS_PRIVATE_ACTUAL_PRECONDITIONS",root=str(root),root_identity=list(root_identity),rows=rows,one_shot_probes_not_precreated=True,observed_mono_ns=time.monotonic_ns())

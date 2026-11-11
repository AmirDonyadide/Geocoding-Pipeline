# ruff: noqa: E402
"""Small invented stream checks; no SSH or native allowance is used."""

import hashlib
from pathlib import Path
import sys
import time
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_collect as tc


def test_actual_small_stream_child_complete_identity_and_eof(tmp_path):
    source = tmp_path / "invented"
    source.write_bytes(b"invented\0payload")
    out = tmp_path / "retained"
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**10, 10)
    expected = dict(
        bytes=source.stat().st_size,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    actual = transport.copy_process(["/bin/cat", str(source)], out, expected, control)
    assert (
        out.read_bytes() == source.read_bytes()
        and actual["exit_code"] == 0
        and actual["observed_joined"]
    )
    assert actual["opaque_remote_fd_identity"] == "UNOBSERVED"


@pytest.mark.parametrize("kind", ["truncated", "excess", "wrong-hash"])
def test_stream_failure_preserves_prefix_and_never_receipt(tmp_path, kind):
    source = tmp_path / "invented"
    source.write_bytes(b"01234567")
    size = 8 if kind == "wrong-hash" else 9 if kind == "truncated" else 7
    expected = dict(bytes=size, sha256="0" * 64)
    out = tmp_path / "partial"
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 10**10, 10)
    with pytest.raises(tc.Stop):
        transport.copy_process(["/bin/cat", str(source)], out, expected, control)
    assert out.is_file() and out.stat().st_size <= size


def test_fixed_remote_command_quotes_and_never_changes_host():
    argv = transport.remote_argv("goethe", "/controlled/public invented/file's.bin")
    assert argv[:6] == ["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]
    assert "iflag=nofollow" in argv[-1]
    with pytest.raises(tc.Stop):
        transport.remote_argv("other-host", "/controlled/path")
    with pytest.raises(tc.Stop):
        transport.remote_argv("goethe", "/controlled/../unsafe")


def test_cleanup_reserve_expired_before_open_or_child(tmp_path, monkeypatch):
    control = pair.Control(time.monotonic_ns(), time.time_ns() + 1_000_000_000, 1)

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_CHILD")

    monkeypatch.setattr(transport.subprocess, "Popen", forbidden)
    output = tmp_path / "not-created"
    with pytest.raises(tc.Stop):
        transport.copy_process(
            ["unused"], output, dict(bytes=0, sha256="0" * 64), control
        )
    assert not output.exists()


def framed_fixture(tmp_path, rows, *, nonce="1"*32, mutation=None):
    """Finite source-framed bytes for the actual parser, served by one cat."""
    import datetime as dt
    import os
    import stat
    paths,extra,ancestors=transport.batch_paths(rows)
    snapshots=[list(tc.ident(p.lstat())) for p in paths+extra+ancestors]
    def line(info):
        def stamp(ns):
            sec,sub=divmod(ns,10**9)
            return dt.datetime.fromtimestamp(sec,dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")+f".{sub:09d} +0000"
        kind="directory" if stat.S_ISDIR(info[2]) else "regular file" if info[6] else "regular empty file"
        return "|".join([str(info[0]),str(info[1]),format(info[2],"x"),*[str(n) for n in info[3:7]],stamp(info[7]),stamp(info[8]),kind]).encode()+b"\n"
    domain=b"DOMAIN|invented-host|11111111-1111-1111-1111-111111111111|mnt:[11]|"+nonce.encode()+b"|11\n"
    raw=bytearray(f"S12B2|{nonce}|{len(paths)}|0|{len(ancestors)}\n".encode()+domain+b"BEFORE\n")
    for info in snapshots:
        raw.extend(line(info))
    for i,path in enumerate(paths):
        content=path.read_bytes()
        raw.extend(f"DATA|{i}|{len(content)}\n".encode()+content+b"\n"+f"END_DATA|{i}\n".encode())
    raw.extend(b"AFTER\n")
    for i,info in enumerate(snapshots):
        info=list(info)
        if mutation=="metadata" and i==0:
            info[0]+=1
        raw.extend(line(info))
    raw.extend(domain.replace(b"invented-host",b"different-host") if mutation=="domain" else domain)
    raw.extend(f"END|{nonce}\n".encode())
    if mutation=="truncated":
        raw=raw[:len(raw)//2]
    elif mutation=="malformed":
        raw[:5]=b"WRONG"
    elif mutation=="excess":
        raw.extend(b"EXTRA")
    wire=tmp_path/"fixture.wire"
    fd=os.open(wire,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        os.write(fd,raw)
    finally:
        os.close(fd)
    return ["/bin/cat",str(wire)]


def test_same_domain_actual_interface_retains_full_identity_and_hash(tmp_path,monkeypatch):
    import os
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT","1")
    source=tmp_path/"invented"
    source.write_bytes(b"INVENTED\0ONLY")
    os.chmod(source,0o600)
    out=tmp_path/"out"
    out.mkdir(mode=0o700)
    row=dict(label="payload",path=str(source),bytes=source.stat().st_size,sha256=pair.digest(source.read_bytes()))
    argv=framed_fixture(tmp_path,[row])
    control=pair.Control(time.monotonic_ns(),time.time_ns()+10**10,10)
    evidence,extra=transport.fetch_batch([row],out,control,expected_uid=os.geteuid(),expected_gid=os.getegid(),testing_argv=argv,nonce="1"*32)
    assert not extra and evidence["files"][0]["before"] == evidence["files"][0]["after"] == list(tc.ident(source.lstat()))
    assert (out/"payload.original").read_bytes()==source.read_bytes()
    assert evidence["domain_before"] == evidence["domain_after"] and not control.cleanup_uncertain


@pytest.mark.parametrize("mutation",["domain","metadata","truncated","malformed","excess"])
def test_same_domain_failure_has_safe_first_evidence_and_cleanup(tmp_path,monkeypatch,mutation):
    import os
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT","1")
    source=tmp_path/"invented"
    source.write_bytes(b"INVENTED")
    os.chmod(source,0o600)
    out=tmp_path/"out"
    out.mkdir(mode=0o700)
    row=dict(label="payload",path=str(source),bytes=8,sha256=pair.digest(b"INVENTED"))
    argv=framed_fixture(tmp_path,[row],mutation=mutation)
    control=pair.Control(time.monotonic_ns(),time.time_ns()+10**10,10)
    with pytest.raises(tc.Stop) as caught:
        transport.fetch_batch([row],out,control,expected_uid=os.geteuid(),testing_argv=argv,nonce="1"*32)
    diagnostic=caught.value.transport_diagnostic
    assert diagnostic["status"]=="INCOMPLETE" and diagnostic["code"] in pair.SAFE_CODES
    assert diagnostic["cleanup_completed_mono_ns"] >= diagnostic["first_mono_ns"]
    assert diagnostic["remote_cleanup_status"]=="UNKNOWN" and diagnostic["cleanup_uncertain"]
    assert "INVENTED" not in str(diagnostic)


def test_same_domain_deadline_rejects_before_child(tmp_path,monkeypatch):
    import os
    source=tmp_path/"invented"
    source.write_bytes(b"")
    os.chmod(source,0o600)
    out=tmp_path/"out"
    out.mkdir(mode=0o700)
    monkeypatch.setattr(transport.subprocess,"Popen",lambda *a,**k:pytest.fail("no child before deadline"))
    control=pair.Control(time.monotonic_ns(),time.time_ns()+10**9,1)
    with pytest.raises(tc.Stop):
        transport.fetch_batch([dict(label="x",path=str(source),bytes=0,sha256=pair.digest(b""))],out,control,expected_uid=os.geteuid())


def test_fixed_batch_command_has_one_session_and_only_metadata_dd():
    argv=transport.batch_remote_argv([dict(label="x",path="/controlled/x",bytes=0,sha256="1"*64)],"2"*32,expected_uid=1)
    command=argv[-1]
    assert argv.count("goethe")==1
    assert command.count("stat --printf")==2 and command.count("readlink --")==1
    assert "dd if=" in command and "python" not in command and "sha256" not in command


def archive_fixture(tmp_path, corruption=None):
    """Small actual collection wire; mutating archive hash too proves parser checks."""
    import os
    import struct
    source=tmp_path/"source"
    source.mkdir(mode=0o700)
    payload=b"INVENTED"
    log=source/"log"
    log.write_bytes(payload)
    os.chmod(log,0o600)
    limits=dict(members=64,payload_bytes=1048576,manifest_bytes=262144,record_bytes=4096,path_bytes=512,
                name_bytes=255,depth=16,sort_records=2,sort_buffer_bytes=16384,merge_fan_in=2,chunk_bytes=4096,
                wire_bytes=2097152,read_bytes=33554432,write_bytes=33554432,creations=512,operations=100000,scanned_entries=2048,seconds=20)
    selection=dict(version=tc.FIFO_VERSION,scope="TEST_ONLY_INVENTED",state="TEST_ONLY",approval_sha256=None,
                   job_id=0,source_git_sha="0"*40,source_uid=os.geteuid(),source_gid=os.getegid(),
                   roots=[dict(label="data",path=str(source))],external_files=[],required_logs=["data/log"],inert_fifos=[],
                   limits=limits,valid_until_epoch_ns=time.time_ns()+20*10**9)
    selected=tc.Selection(selection,True,tmp_path)
    rows=[dict(path="data",kind="DIR",size=0,sha256=None,identity=list(tc.ident(source.lstat()))),
          dict(path="data/log",kind="FILE",size=len(payload),sha256=pair.digest(payload),identity=list(tc.ident(log.lstat())))]
    lines=[tc.canonical(row) for row in rows]
    manifest=b"".join(lines)
    summary=dict(members=2,payload_bytes=len(payload),manifest_bytes=len(manifest),manifest_sha256=pair.digest(manifest))
    def frame(value):
        raw=tc.canonical(value)
        return struct.pack(">I",len(raw))+raw
    entry=[frame(dict(kind="ENTRY",entry=r)) for r in rows]
    if corruption=="data_missing_frame":
        entry[1]=b""
    elif corruption=="data_reordered":
        entry.reverse()
    wire=bytearray(selected.magic+frame(dict(kind="BEGIN",version=selected.version,scope=tc.SCOPE,selection_sha256=selected.sha))
                   +frame(dict(kind="BEFORE",summary=summary)))
    for row in rows:
        wire.extend(frame(dict(kind="MEMBER",entry=row)))
    wire.extend(frame(dict(kind="DATA",summary=summary))+entry[0]+entry[1])
    wire.extend(b"CORRUPTE" if corruption=="data_corrupt" else payload)
    wire.extend(frame(dict(kind="AFTER",summary=summary)))
    for row in rows:
        wire.extend(frame(dict(kind="MEMBER",entry=row)))
    wire.extend(frame(dict(kind="END",summary=summary,scope=tc.SCOPE)))
    if corruption=="data_truncated":
        wire=wire[:len(wire)//2]
    elif corruption=="trailing":
        wire.extend(b"EXCESS")
    before=manifest
    after=manifest
    if corruption=="manifest_missing":
        before=lines[0]
    elif corruption=="manifest_reordered":
        before=b"".join(reversed(lines))
    elif corruption=="manifest_corrupt":
        changed=dict(rows[1],sha256="1"*64)
        before=lines[0]+tc.canonical(changed)
    elif corruption=="after_corrupt":
        after=lines[0]
    retained=tmp_path/"retained"
    retained.mkdir(mode=0o700)
    artifacts=[]
    for label,raw in (("archive",bytes(wire)),("before",before),("after",after),("verification",b"{}\n")):
        path=retained/(label+".original")
        path.write_bytes(raw)
        os.chmod(path,0o600)
        artifacts.append(dict(label=label,path="/invented/"+label,bytes=len(raw),sha256=pair.digest(raw),identity=list(tc.ident(path.lstat()))))
    ready=dict(scope=pair.TEST,collection_selection=selection,context=dict(selection_sha256=selected.sha),artifacts=artifacts)
    return ready,retained,summary


def test_actual_readonly_archive_opener_complete_semantic_pass(tmp_path):
    ready,retained,summary=archive_fixture(tmp_path)
    control=pair.Control(time.monotonic_ns(),time.time_ns()+20*10**9,20)
    got,proof=pair.open_retained_archive(ready,retained,control)
    assert proof["status"]=="COMPLETE" and proof["summary"]==summary and proof["archive_sha256"]==ready["artifacts"][0]["sha256"]
    assert got["bytes"]==ready["artifacts"][0]["bytes"] and control.read_bytes < 1048576
    assert sorted(p.name for p in retained.iterdir())==["after.original","archive.original","before.original","verification.original"]


@pytest.mark.parametrize("corruption",["manifest_missing","manifest_reordered","manifest_corrupt","data_corrupt",
                                      "data_truncated","data_missing_frame","data_reordered","trailing","after_corrupt"])
def test_actual_readonly_archive_opener_rejects_semantic_corruption(tmp_path,corruption):
    ready,retained,_=archive_fixture(tmp_path,corruption)
    # READY's archive digest equals the deliberately corrupted current bytes:
    # rejection must occur in a frame/member/payload guard before final hash.
    assert pair.digest((retained/"archive.original").read_bytes())==ready["artifacts"][0]["sha256"]
    control=pair.Control(time.monotonic_ns(),time.time_ns()+20*10**9,20)
    with pytest.raises(tc.Stop) as caught:
        pair.open_retained_archive(ready,retained,control)
    assert pair.safe_code(caught.value) in {"FRAME","PROTOCOL","TRUNCATED","PAYLOAD_HASH","SOURCE_CHANGED"}
    assert not control.cleanup_uncertain


def test_actual_bash_metadata_guards_fail_before_fifo_dd():
    import shlex
    import subprocess
    argv=transport.batch_remote_argv([dict(label="x",path="/controlled/x",bytes=0,sha256="1"*64)],"2"*32,expected_uid=1)
    script=shlex.split(argv[-1])[-1]
    start=script.index("[[ ${#meta[@]} -eq")
    end=script.index("printf 'DATA|")
    guards=script[start:end]
    regular="1|3|8180|1|1|1|0|unused|unused|regular empty file"
    directory="1|2|41c0|1|1|2|0|unused|unused|directory"
    fifo=regular.replace("|8180|","|1180|")
    body="set -euo pipefail\nmeta=("+shlex.quote(regular)+" "+shlex.quote(directory)+" "+shlex.quote(directory)+")\n"
    body+=guards+"printf 'VALID\\n'\nmeta[0]="+shlex.quote(fifo)+"\n"+guards+"printf 'UNSAFE_DD_REACHED\\n'\n"
    done=subprocess.run(["/bin/bash","-s"],input=body,text=True,capture_output=True,timeout=5,check=False)
    assert done.returncode!=0 and done.stdout=="VALID\n" and not done.stderr

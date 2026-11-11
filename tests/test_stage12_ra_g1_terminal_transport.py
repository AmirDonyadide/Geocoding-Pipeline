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


# Successor parser unit transcripts use actual OS pipes and the real read/hash/
# fsync path. Their finite pipe owner substitutes only OS child lifecycle;
# generated GNU-stat producer execution is a separate native metadata probe.
def named_fixture_wire(rows, *, metadata_paths=(), missing_before=(), missing_after=(), mutation=None):
    import datetime as dt
    import os
    import stat
    paths, extra, ancestors = transport.batch_paths(rows, metadata_paths)
    snapshot = paths + extra + ancestors
    nonce = "1" * 32
    domain = ("DOMAIN|invented-host|11111111-1111-1111-1111-111111111111|mnt:[11]|" + nonce + "|11\n").encode()
    values = [None if i in missing_before else list(tc.ident(p.lstat())) for i, p in enumerate(snapshot)]
    def stat_line(value):
        def stamp(ns):
            sec, sub = divmod(ns, 10**9)
            return dt.datetime.fromtimestamp(sec, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + f".{sub:09d} +0000"
        kind = "directory" if stat.S_ISDIR(value[2]) else "regular file" if value[6] else "regular empty file"
        return "|".join([str(value[0]), str(value[1]), format(value[2], "x"), *map(str, value[3:7]), stamp(value[7]), stamp(value[8]), kind]).encode() + b"\n"
    def block(stage, infos, missing):
        raw = bytearray(f"{stage}_STATUS|{1 if missing else 0}\n".encode())
        for i, (path, value) in enumerate(zip(snapshot, infos, strict=True)):
            if i not in missing:
                raw.extend(os.fsencode(path) + b"|" + stat_line(value))
        raw.extend(f"END_{stage}\n".encode())
        return raw
    raw = bytearray(f"S12B3|{nonce}|{len(paths)}|{len(extra)}|{len(ancestors)}\n".encode() + domain)
    raw.extend(block("BEFORE", values, missing_before))
    for i, path in enumerate(paths):
        if i in missing_before:
            raw.extend(f"ABSENT_DATA|{i}\n".encode())
            continue
        payload = path.read_bytes()
        raw.extend(f"DATA|{i}|{len(payload)}\n".encode() + payload + b"\n" + f"END_DATA|{i}\n".encode())
    after = [list(value) if value is not None else None for value in values]
    if mutation == "device":
        after[0][0] += 1
    absent_after = set(missing_before) | set(missing_after)
    raw.extend(block("AFTER", after, absent_after))
    raw.extend(domain + f"END|{nonce}\n".encode())
    if mutation == "truncated":
        raw = raw[:len(raw)//2]
    elif mutation == "badstatus":
        raw = raw.replace(b"BEFORE_STATUS|0", b"BEFORE_STATUS|999", 1)
    elif mutation == "statuszero_missing":
        raw = raw.replace(b"BEFORE_STATUS|1", b"BEFORE_STATUS|0", 1)
    elif mutation == "duplicate":
        line = os.fsencode(paths[0]) + b"|" + stat_line(values[0])
        raw = raw.replace(b"END_BEFORE\n", line + b"END_BEFORE\n", 1)
    elif mutation == "unknown":
        raw = raw.replace(os.fsencode(paths[0])+b"|", b"/unselected|", 1)
    return bytes(raw)


def finite_pipe_owner(monkeypatch, raw):
    """No child process: one joined test-only producer, genuine bounded OS pipes."""
    import os
    import threading
    rfd, wfd = os.pipe()
    erfd, ewfd = os.pipe()
    os.close(ewfd)
    class PipeProcess:
        stdin = None
        stdout = os.fdopen(rfd, "rb", buffering=0)
        stderr = os.fdopen(erfd, "rb", buffering=0)
        pid = 0
        def poll(self):
            return 0
        def wait(self, timeout=None):
            return 0
    def emit():
        try:
            view = memoryview(raw)
            while view:
                count = os.write(wfd, view[:1024])
                view = view[count:]
        except BrokenPipeError:
            pass
        finally:
            os.close(wfd)
    owner = threading.Thread(target=emit, name="invented-finite-pipe-owner", daemon=False)
    owner.start()
    monkeypatch.setattr(transport.subprocess, "Popen", lambda *args, **kwargs: PipeProcess())
    return owner


def named_inputs(tmp_path):
    import os
    source = tmp_path / "present"
    source.write_bytes(b"INVENTED")
    os.chmod(source, 0o600)
    out = tmp_path / "out"
    out.mkdir(mode=0o700)
    return source, out, dict(label="present", path=str(source), bytes=8, sha256=pair.digest(b"INVENTED"))


def test_named_pipe_full_identity_hash_and_legacy_evidence(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT", "1")
    source, out, row = named_inputs(tmp_path)
    raw = named_fixture_wire([row], metadata_paths=[source.parent])
    owner = finite_pipe_owner(monkeypatch, raw)
    try:
        control = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
        evidence, extra = transport.fetch_batch([row], out, control, expected_uid=os.geteuid(),
                                               metadata_paths=[source.parent], testing_argv=["invented-finite-pipe"], nonce="1"*32)
        assert evidence["files"][0]["before"] == evidence["files"][0]["after"] == list(tc.ident(source.lstat()))
        assert extra[str(source.parent)] == list(tc.ident(source.parent.lstat()))
        assert (out / "present.original").read_bytes() == source.read_bytes()
        pair.validate_transport_evidence(evidence)
        assert not control.cleanup_uncertain
    finally:
        owner.join(timeout=1)
        assert not owner.is_alive()


    legacy_out = tmp_path / "legacy_out"
    legacy_out.mkdir(mode=0o700)
    legacy_argv = framed_fixture(tmp_path, [row])
    legacy_wire = Path(legacy_argv[1]).read_bytes()
    legacy_owner = finite_pipe_owner(monkeypatch, legacy_wire)
    try:
        legacy_control = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
        legacy, extra = transport.fetch_batch([row], legacy_out, legacy_control, expected_uid=os.geteuid(),
                                              testing_argv=["invented-finite-pipe"], nonce="1"*32)
        assert not extra and not legacy_control.cleanup_uncertain
        assert legacy["files"] == evidence["files"]
        assert (legacy_out / "present.original").read_bytes() == source.read_bytes()
    finally:
        legacy_owner.join(timeout=1)
        assert not legacy_owner.is_alive()


def test_named_pipe_missing_required_preserves_each_status_before_content(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT", "1")
    source, out, row = named_inputs(tmp_path)
    rows = [row, dict(label="not_yet", path=str(tmp_path / "not_yet"), maximum=65536)]
    raw = named_fixture_wire(rows, missing_before=[1])
    owner = finite_pipe_owner(monkeypatch, raw)
    try:
        control = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
        with pytest.raises(tc.Stop) as caught:
            transport.fetch_batch(rows, out, control, expected_uid=os.geteuid(), testing_argv=["invented-finite-pipe"], nonce="1"*32, terminal_log_labels=["present", "not_yet"])
        detail = caught.value.transport_diagnostic
        assert detail["code"] == "RETENTION" and detail["presence"]["before_stat_exit"] == 1
        assert detail["presence"]["entries"][0]["before"] == "PRESENT"
        assert detail["presence"]["entries"][1]["before"] == "UNAVAILABLE"
        assert detail["metadata_before"][0] == list(tc.ident(source.lstat()))
        assert detail["metadata_before"][1] is None
        assert (out / "present.original").read_bytes() == source.read_bytes()
        assert detail["retained_files"][0]["sha256"] == pair.digest(source.read_bytes())
        assert detail["retained_files"][0]["before"] == detail["retained_files"][0]["after"] == list(tc.ident(source.lstat()))
        assert not control.cleanup_uncertain
        assert detail["remote_cleanup_status"] == "JOINED_NATIVE_EXIT_ZERO"
    finally:
        owner.join(timeout=1)
        assert not owner.is_alive()


    # A missing first member must not shift a later retained file's AFTER slot.
    flipped_out = tmp_path / "flipped_out"
    flipped_out.mkdir(mode=0o700)
    flipped_rows = [rows[1], rows[0]]
    flipped_wire = named_fixture_wire(flipped_rows, missing_before=[0])
    flipped_owner = finite_pipe_owner(monkeypatch, flipped_wire)
    try:
        flipped_control = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
        with pytest.raises(tc.Stop) as flipped:
            transport.fetch_batch(flipped_rows, flipped_out, flipped_control, expected_uid=os.geteuid(),
                                  testing_argv=["invented-finite-pipe"], nonce="1"*32,
                                  terminal_log_labels=["present", "not_yet"])
        detail = flipped.value.transport_diagnostic
        assert detail["code"] == "RETENTION"
        assert [r["before"] for r in detail["presence"]["entries"][:2]] == ["UNAVAILABLE", "PRESENT"]
        assert detail["retained_files"][0]["label"] == "present"
        assert detail["retained_files"][0]["before"] == detail["retained_files"][0]["after"] == list(tc.ident(source.lstat()))
        assert (flipped_out / "present.original").read_bytes() == source.read_bytes()
        assert not (flipped_out / "not_yet.original").exists()
        assert not flipped_control.cleanup_uncertain
    finally:
        flipped_owner.join(timeout=1)
        assert not flipped_owner.is_alive()


@pytest.mark.parametrize("mutation", ["device", "truncated", "badstatus", "duplicate", "unknown", "statuszero_missing", "missing_after"])
def test_named_pipe_rejects_mutation_and_invalid_or_incomplete_metadata(tmp_path, monkeypatch, mutation):
    import os
    monkeypatch.setenv("SAFE_STAGE12_INVENTED_TRANSPORT", "1")
    source, out, row = named_inputs(tmp_path)
    rows = [row]
    kwargs = dict(mutation=mutation)
    if mutation == "statuszero_missing":
        rows.append(dict(label="not_yet", path=str(tmp_path / "not_yet"), maximum=65536))
        kwargs["missing_before"] = [1]
    if mutation == "missing_after":
        kwargs["missing_after"] = [0]
    raw = named_fixture_wire(rows, **kwargs)
    owner = finite_pipe_owner(monkeypatch, raw)
    try:
        control = pair.Control(time.monotonic_ns(), time.time_ns()+10**10, 10)
        with pytest.raises(tc.Stop) as caught:
            transport.fetch_batch(rows, out, control, expected_uid=os.geteuid(), testing_argv=["invented-finite-pipe"], nonce="1"*32)
        detail = caught.value.transport_diagnostic
        assert detail["code"] in {"SOURCE_CHANGED", "TRUNCATED", "FRAME", "LIMITS"}
        assert detail["presence"]["entries"][0]["label"] == "present"
        if mutation == "missing_after":
            assert detail["presence"]["entries"][0]["after"] == "UNAVAILABLE"
        assert detail["status"] == "INCOMPLETE"
    finally:
        owner.join(timeout=1)
        assert not owner.is_alive()


def test_named_generator_preserves_surviving_stats_and_exact_process_bound(monkeypatch):
    argv = transport.batch_remote_argv([dict(label="x", path="/controlled/x", maximum=65536),
                                       dict(label="pending", path="/controlled/pending", maximum=65536)], "2"*32, expected_uid=1)
    command = argv[-1]
    assert "S12B3|" in command and "BEFORE_STATUS|" in command and "AFTER_STATUS|" in command
    assert "if before=$(stat --printf=" in command and "before_status=$?" in command
    assert "ABSENT_DATA|" in command and command.count("stat --printf=") == 2
    assert "PENDING" not in command and "ENOENT" not in command
    assert command.index("BEFORE_STATUS|") < command.index("dd if=")
    assert "meta=(" in command and "case" in command

    # The named representation is selected before launching any remote process.
    selected = [dict(label="x", path="/controlled/x", maximum=65536),
                dict(label="pending", path="/controlled/pending", maximum=65536)]
    paths, extras, ancestors = transport.batch_paths(selected)
    import os
    charge = sum(len(os.fsencode(path)) + 513 for path in paths + extras + ancestors)
    for ceiling in (charge + 1, charge):
        monkeypatch.setattr(transport, "MAX_METADATA", ceiling)
        assert transport.batch_remote_argv(selected, "2"*32, expected_uid=1)
    monkeypatch.setattr(transport, "MAX_METADATA", charge - 1)
    with pytest.raises(tc.Stop) as caught:
        transport.batch_remote_argv(selected, "2"*32, expected_uid=1)
    assert pair.safe_code(caught.value) == "LIMITS"

"""Selected remote directory identity tests; invented facts are never authority."""
import copy
import stat
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stage12_ra_g1_terminal_parent as pair
import stage12_ra_g1_terminal_transport as transport
import stage12_ra_g1_terminal_verify as verify

def remote_qualification():
    from test_stage12_ra_g1_terminal_verify import invented_qualification
    bundle, kwargs = invented_qualification()
    scope = verify.REMOTE_DIRECTORY_SCOPE
    bundle["version"] = verify.REMOTE_QUALIFICATION_VERSION
    bundle["remote_directory_scope"] = scope
    ready = bundle["ready"]
    ready["version"] = pair.REMOTE_IDENTITY_READY_VERSION
    ready["context"].update(remote_directory_scope=scope, transport_evidence_version=verify.REMOTE_TRANSPORT_VERSION)
    for key in ("receipt", "index"):
        ev = bundle[key]["transport_evidence"]
        ev.update(version=verify.REMOTE_TRANSPORT_VERSION, remote_directory_scope=scope)
        ev["ancestors"][0]["before"][5] = 25
        ev["ancestors"][0]["after"][5] = 24
    bundle["transport"]["version"] = "stage12_terminal_remote_directory_bounded_transport_v3"
    refresh_qualification(bundle, kwargs)
    kwargs["expected_remote_directory_scope"] = scope
    return bundle, kwargs

def refresh_qualification(bundle, kwargs):
    digest = verify._q_digest
    bundle["receipt"]["ready_sha256"] = digest(bundle["ready"])
    bundle["ack"]["ready_sha256"] = digest(bundle["ready"])
    bundle["ack"]["receipt_sha256"] = digest(bundle["receipt"])
    for name, key in (("ready", "ready_sha256"), ("receipt", "receipt_sha256"), ("ack", "receipt_ack_sha256")):
        bundle["provisional"][key] = digest(bundle[name])
    bundle["index"]["context_sha256"] = digest(bundle["ready"]["context"])
    bundle["final"]["provisional_sha256"] = digest(bundle["provisional"])
    bundle["final"]["log_index_sha256"] = digest(bundle["index"])
    bundle["transport"]["ready_sha256"] = digest(bundle["ready"])
    bundle["transport"]["receipt_sha256"] = digest(bundle["receipt"])
    for name, key in (("final", "final_sha256"), ("ready", "ready_sha256"), ("ack", "receipt_ack_sha256"), ("terminal", "terminal_sha256"), ("index", "index_sha256"), ("transport", "transport_sha256"), ("opener", "opener_sha256")):
        bundle["review"][key] = digest(bundle[name])
    kwargs["expected_qualification_review_sha256"] = digest(bundle["review"])

def test_explicit_successor_qualification_and_legacy_are_separate():
    from test_stage12_ra_g1_terminal_verify import invented_qualification
    old, old_kw = invented_qualification()
    assert verify.validate_qualification(old, **old_kw) is old
    new, new_kw = remote_qualification()
    assert verify.validate_qualification(new, **new_kw) is new
    with pytest.raises(RuntimeError):
        verify.validate_qualification(new, **{k:v for k,v in new_kw.items() if k != "expected_remote_directory_scope"})
    with pytest.raises(RuntimeError):
        verify.validate_qualification(old, **dict(old_kw, expected_remote_directory_scope=verify.REMOTE_DIRECTORY_SCOPE))

@pytest.mark.parametrize("field", range(5))
def test_directory_identity_fields_still_fail(field):
    bundle, kwargs = remote_qualification()
    ev = bundle["receipt"]["transport_evidence"]
    ev["ancestors"][0]["after"][field] += 1
    with pytest.raises(RuntimeError):
        pair.validate_transport_evidence(ev, remote_directory_scope=pair.REMOTE_DIRECTORY_SCOPE)
    with pytest.raises(RuntimeError):
        verify._q_transfer(ev, bundle["ready"]["artifacts"], remote_directory_scope=pair.REMOTE_DIRECTORY_SCOPE)

@pytest.mark.parametrize("kind", ["symlink", "regular", "file_nlink", "file_mutation", "file_size", "duplicate_ancestor", "missing_ancestor", "duplicate_file", "missing_file", "scope", "version", "domain"])
def test_selected_evidence_rejects_unsafe_or_incompatible_membership(kind):
    bundle, kwargs = remote_qualification()
    ev = bundle["receipt"]["transport_evidence"]
    if kind in ("symlink", "regular"):
        ev["ancestors"][0]["before"][2] = ev["ancestors"][0]["after"][2] = (stat.S_IFLNK if kind == "symlink" else stat.S_IFREG) | 0o700
    elif kind == "file_nlink":
        ev["files"][0]["before"][5] = ev["files"][0]["after"][5] = 2
    elif kind == "file_mutation": ev["files"][0]["after"][1] += 1
    elif kind == "file_size": ev["files"][0]["bytes"] += 1
    elif kind == "duplicate_ancestor": ev["ancestors"].append(copy.deepcopy(ev["ancestors"][0]))
    elif kind == "missing_ancestor": ev["ancestors"].pop()
    elif kind == "duplicate_file": ev["files"].append(copy.deepcopy(ev["files"][0]))
    elif kind == "missing_file": ev["files"].pop()
    elif kind == "scope": ev["remote_directory_scope"] = "wrong"
    elif kind == "version": ev["version"] = "stage12_same_session_transfer_v2"
    elif kind == "domain": ev["domain_after"] = dict(ev["domain_after"], session_pid=12)
    with pytest.raises(RuntimeError):
        pair.validate_transport_evidence(ev, bundle["ready"])
    refresh_qualification(bundle, kwargs)
    with pytest.raises(RuntimeError): verify.validate_qualification(bundle, **kwargs)

def test_raw_nine_fields_retained_and_strict_v2_rejects_nlink_delta():
    bundle, kwargs = remote_qualification()
    ev = bundle["receipt"]["transport_evidence"]
    assert all(len(row[k]) == 9 for row in ev["ancestors"] for k in ("before", "after"))
    assert pair.validate_transport_evidence(ev, bundle["ready"]) is ev
    legacy = copy.deepcopy(ev)
    legacy["version"] = transport.BATCH_VERSION
    legacy.pop("remote_directory_scope")
    with pytest.raises(RuntimeError): pair.validate_transport_evidence(legacy)
    legacy["ancestors"][0]["after"][5] = 25
    assert pair.validate_transport_evidence(legacy) is legacy

def test_closed_oneshot_policy_explicit_selection():
    policy = dict(pair.REMOTE_IDENTITY_PAIR_CONTROL_LIMITS)
    policy.update({key:"a"*64 for _,key in pair.ONESHOT_SOURCE_FIELDS})
    policy["selected_remote_pair"] = "/controlled/selected"
    assert pair.validate_oneshot_control_policy(policy, selected_remote_pair="/controlled/selected", nonwaiting=True, remote_directory_scope=pair.REMOTE_DIRECTORY_SCOPE) is policy
    with pytest.raises(RuntimeError): pair.validate_oneshot_control_policy(policy, selected_remote_pair="/controlled/selected", nonwaiting=True)
    for key in ("remote_directory_scope", "transport_evidence_version", "readiness_reader_version"):
        bad = dict(policy); bad[key] = "wrong"
        with pytest.raises(RuntimeError): pair.validate_oneshot_control_policy(bad, selected_remote_pair="/controlled/selected", nonwaiting=True, remote_directory_scope=pair.REMOTE_DIRECTORY_SCOPE)


def test_ready_and_evidence_cannot_mix_contract_families():
    bundle, _ = remote_qualification()
    ev = bundle["receipt"]["transport_evidence"]
    old_ready = copy.deepcopy(bundle["ready"])
    old_ready["version"] = pair.SUCCESSOR_READY_VERSION
    old_ready["context"].pop("remote_directory_scope")
    old_ready["context"].pop("transport_evidence_version")
    with pytest.raises(RuntimeError):
        pair.validate_transport_evidence(ev, old_ready, remote_directory_scope=pair.REMOTE_DIRECTORY_SCOPE)
    old_ev = copy.deepcopy(ev)
    old_ev["version"] = transport.BATCH_VERSION
    old_ev.pop("remote_directory_scope")
    with pytest.raises(RuntimeError): pair.validate_transport_evidence(old_ev, bundle["ready"])


def test_selected_pending_probe_uses_actual_reader_and_missing_classifier(tmp_path, monkeypatch):
    import os, time
    import stage12_ra_g1_one_shot_controls as observer
    from test_stage12_ra_g1_selected_pair_readiness import PLAN, _transcript, _pipe_process
    # Existing invented errno+raw-stat transcript, actual FD parser and probe.
    rows, ancestors, raw, errors = _transcript(directory_absent=False)
    plan = dict(PLAN, local_directory_scope=transport.TASK_LOCAL_DIRECTORY_SCOPE,
                remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE,
                transport_evidence_version=transport.REMOTE_TRANSPORT_VERSION)
    at = raw.index(b"AFTER_STATUS")
    head, tail = raw[:at], raw[at:]
    path = os.fsencode(PLAN["remote_pair"]) + b"|"
    start = tail.index(path) + len(path)
    end = tail.index(b"\n", start)
    parts = tail[start:end].split(b"|")
    parts[5] = str(int(parts[5])+1).encode()
    raw = head + tail[:start] + b"|".join(parts) + tail[end:]
    proc = _pipe_process(monkeypatch, raw, errors)
    out = tmp_path / "probes"; out.mkdir(mode=0o700)
    overall = pair.Control(time.monotonic_ns(), time.time_ns()+20*10**9, 20)
    records = []
    result = observer.probe(plan, out, overall, transport, pair, pair.tc,
                            lambda name,value: records.append((name,value)), lambda *args: None,
                            testing_argv=["TEST_ONLY_FINITE_PIPE"], nonce="1"*32,
                            local_directory_scope=transport.TASK_LOCAL_DIRECTORY_SCOPE,
                            remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)
    assert result["status"] == "PENDING" and not result["cleanup_uncertain"]
    assert result["version"] == observer.REMOTE_VERSION
    assert result["transport_diagnostic"]["remote_directory_scope"] == transport.REMOTE_DIRECTORY_SCOPE
    assert all(r["before"] == r["after"] == "ABSENT_ENOENT" for r in result["present_absent"])
    assert proc.stdout.closed and proc.stderr.closed


def test_actual_prelude_consumer_selected_and_legacy_shapes():
    import datetime as dt
    import stage12_ra_g1_collection_driver as driver
    def line(v):
        def stamp(n):
            sec,sub=divmod(n,10**9)
            return dt.datetime.fromtimestamp(sec,dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")+f".{sub:09d} +0000"
        return ("|".join([str(v[0]),str(v[1]),format(v[2],"x"),*map(str,v[3:7]),stamp(v[7]),stamp(v[8]),"directory" if stat.S_ISDIR(v[2]) else "regular file"])+"\n").encode()
    rows=[dict(path="/private/control.record",bytes=8)]
    ancestors=[Path("/"),Path("/private")]
    file=[1,3,stat.S_IFREG|0o600,1,1,1,8,1,1]
    directory=[1,2,stat.S_IFDIR|0o700,1,1,25,0,1,1]
    ids=[file,list(directory),list(directory)]
    before=b"BEFORE\n"+b"".join(map(line,ids))+b"/private/control.record: OK\n"
    marker=b"S12_CANONICAL_BINDINGS_AND_SOURCE_VERIFIED\n"
    assert driver.validate_prelude(before+marker,rows,ancestors,transport,1,1)==ids
    after=copy.deepcopy(ids);after[1][5]=24
    selected=before+b"AFTER\n"+b"".join(map(line,after))+("REMOTE_DIRECTORY_POLICY|"+transport.REMOTE_DIRECTORY_SCOPE+"\n").encode()+marker
    assert driver.validate_prelude(selected,rows,ancestors,transport,1,1,remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)==ids
    with pytest.raises(AssertionError): driver.validate_prelude(selected,rows,ancestors,transport,1,1)
    for index,field in ((0,5),(1,0),(1,1),(1,2),(1,3),(1,4)):
        bad=copy.deepcopy(after);bad[index][field]+=1
        raw=before+b"AFTER\n"+b"".join(map(line,bad))+("REMOTE_DIRECTORY_POLICY|"+transport.REMOTE_DIRECTORY_SCOPE+"\n").encode()+marker
        with pytest.raises(AssertionError): driver.validate_prelude(raw,rows,ancestors,transport,1,1,remote_directory_scope=transport.REMOTE_DIRECTORY_SCOPE)

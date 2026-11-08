"""A2 synthetic boundaries; these fixtures are not live authority or kernel facts."""

from copy import deepcopy
import errno
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_a2_test", ROOT / "scripts/stage12_wf_ap2_bootstrap_a2.py"
)
a = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)
NOW = "2026-11-08T13:00:00.000000Z"


@pytest.fixture(autouse=True)
def denied(monkeypatch, request):
    from safe_geocoding_pipeline.preprocessing.stages import s12_transport

    def no(*args, **kwargs):
        raise AssertionError("prohibited external/process/provider access")

    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyaddr"):
        monkeypatch.setattr(socket, name, no)
    for name in ("connect", "connect_ex", "bind", "sendto"):
        monkeypatch.setattr(socket.socket, name, no)
    monkeypatch.setattr(s12_transport.Secret, "runtime", no)
    monkeypatch.setattr(s12_transport.Secret, "private_file", no)
    if request.node.name != "test_real_installed_audit_and_guarded_writer" and not request.node.name.startswith("test_shell_logwrite"):
        for name in ("Popen", "run", "check_output", "check_call", "call"):
            monkeypatch.setattr(subprocess, name, no)


def private(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def write(path, value, raw=False):
    data = value if raw else a.s.canonical(value)
    path.write_bytes(data)
    path.chmod(0o600)
    return a.s.sha(data)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from safe_geocoding_pipeline import execution_policy

    project = private(tmp_path / "project")
    parent = private(project / "controlled")
    source = private(project / "integration_stage12/source")
    records = private(parent / "records")
    monkeypatch.setattr(a.s, "PROJECT", project)
    monkeypatch.setattr(a.s, "PARENT", parent)
    monkeypatch.setattr(a.s, "now_utc", lambda: NOW)
    monkeypatch.setattr(
        a, "global_deadline", lambda: None
    )  # Explicit fake clock, not CLI bypass.
    monkeypatch.setattr(a, "boot_centiseconds", lambda: 100600)
    monkeypatch.setattr(
        execution_policy, "require_goethe_nhr_slurm", lambda purpose: None
    )
    monkeypatch.setenv("SLURM_JOB_ID", "99999999")  # Invented, compute guard mocked.
    rows = []
    for name in sorted(a.REQUIRED):
        dest = source / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / name).read_bytes()
        write(dest, raw, raw=True)
        rows.append(dict(path=name, sha256=a.s.sha(raw)))
    proof = write(
        records / "proof.tmp", b"TEST_ONLY_NOT_LIVE_OWNER_AUTHORITY", raw=True
    )
    (records / "proof.tmp").rename(records / (proof + ".evidence"))
    v = dict(
        version=a.VERSION,
        scope=a.SCOPE,
        policy_sha256=a.POLICY_SHA,
        source_sha="a" * 40,
        source_files=rows,
        paths=dict(
            source=str(source),
            records=str(records),
            bootstrap=str(parent / "A"),
            review=str(records / "a2_review.json"),
            collector_ack=str(records / "collector_ack.json"),
            final=str(parent / "final"),
            outcome=str(parent / "outcome.json"),
        ),
        owner_sha256="b" * 64,
        implementation_review_sha256=proof,
        valid_from="2026-11-08T00:00:00.000000Z",
        valid_until="2026-11-10T00:00:00.000000Z",
        limits=deepcopy(a.POLICY["limits"]),
        B="DISABLED",
    )
    own = dict(
        version=a.OWNER,
        scope=a.SCOPE,
        source_sha=v["source_sha"],
        selection_scope_sha256=a.selection_scope(v),
        approval_source_sha256=proof,
        approval_type="OWNER_REPORTED_MANAGER_APPROVAL",
        manager_approval_reported=True,
        administrator_attestation=False,
        maximum_allocations=1,
        B="DISABLED",
        independent_reviewer="INDEPENDENT_TEST_ONLY_REVIEWER",
        valid_from=v["valid_from"],
        valid_until=v["valid_until"],
    )
    v["owner_sha256"] = write(records / "owner.tmp", own)
    (records / "owner.tmp").rename(records / (v["owner_sha256"] + ".json"))
    selection = parent / "selection.json"
    token = write(selection, v)

    def probe(path):
        c = dict(
            f_frsize=4096,
            f_blocks=10**8,
            f_bavail=10**7,
            f_files=10**6,
            f_favail=10**5,
            f_flag=0,
        )
        return dict(
            version="stage12_a2_filesystem_observation_v1",
            parent=str(parent),
            parent_identity=list(a.directory_binding(path)),
            filesystem_type="panfs",
            statvfs=c,
            reported_shared_available_bytes=c["f_bavail"] * 4096,
            coarse_rejection_threshold_bytes=240 * 2**20 + 1544 * 4096,
            meaning="SHARED_SNAPSHOT_NOT_ENTITLEMENT_OR_PHYSICAL_BOUND",
            group_quota_and_reservation="UNKNOWN_NOT_ASSUMED",
            rounding_metadata_native_transients="NOT_GUARANTEED",
            observed_mono_ns=1,
        )

    return SimpleNamespace(
        value=v,
        token=token,
        selection=selection,
        records=records,
        parent=parent,
        probe=probe,
    )


def kernel(**kwargs):
    return dict(
        boot_id="TEST_ONLY",
        namespaces={"mnt": 1},
        membership="0::/TEST_ONLY",
        leaf_identity={"inode": 1},
        leaf="/TEST_ONLY_NO_LIVE_DOMAIN",
    )


def collect(env):
    return a.collect(
        env.value,
        env.selection,
        env.token,
        kernel_reader=kernel,
        inventory_reader=lambda *x, **kw: {"scope": "SYNTHETIC_TEST_ONLY"},
        probe=env.probe,
        thread_reader=lambda: 1,
        install_guard=False,
    )


def make_review(env):
    p = env.value["paths"]
    ack = dict(
        version="stage12_a2_collector_ack_v1",
        source_sha=env.value["source_sha"],
        selection_sha256=env.token,
        manifest_sha256=a.s.sha(Path(p["bootstrap"], "manifest.json").read_bytes()),
        job_id="99999999",
        collector_exit=0,
        completed_centiseconds=100100,
        capture_started_centiseconds=100010,
        epoch_centiseconds=100000,
        B="DISABLED",
    )
    h = write(Path(p["collector_ack"]), ack)
    r = dict(
        version="stage12_a2_independent_outcome_v1",
        scope=a.SCOPE,
        source_sha=env.value["source_sha"],
        selection_sha256=env.token,
        manifest_sha256=ack["manifest_sha256"],
        collector_ack_sha256=h,
        reviewer="INDEPENDENT_TEST_ONLY_REVIEWER",
        reviewed_utc=NOW,
        disposition="A_ORIGINALS_VERIFIED_B_DISABLED",
        B="DISABLED",
    )
    write(Path(p["review"]), r)
    return ack, r


def complete(env):
    collect(env)
    make_review(env)
    return a.finalize(
        env.value,
        env.selection,
        env.token,
        thread_reader=lambda: 1,
        probe=env.probe,
        install_guard=False,
    )


def rewrite_original(root, name, mutate):
    f = Path(root) / name
    v = a.s.parse(f.read_bytes())
    mutate(v)
    write(f, v)
    mf = Path(root) / "manifest.json"
    m = a.s.parse(mf.read_bytes())
    for row in m["inventory"]:
        if row["name"] == name:
            row.update(bytes=f.stat().st_size, sha256=a.s.sha(f.read_bytes()))
    m["charged_bytes_before_manifest"] = sum(row["bytes"] for row in m["inventory"])
    write(mf, m)


def test_successful_collect_review_closure_real_original_reopening(environment):
    e = environment
    r = complete(e)
    assert r["status"] == "A2_ACTUAL_STRUCTURAL_REOPEN_PASS_PENDING_TERMINAL"
    opened = a.open_completed(e.value, e.token, probe=e.probe)
    assert opened["B"] == "DISABLED" and opened["M2"] == "NOT_QUALIFIED_BY_BOOTSTRAP"
    with pytest.raises(a.s.AllocationError):
        a.s.validate_selection(e.value)
    with pytest.raises(a.s.AllocationError):
        a.s.verify_stage(
            e.value["paths"]["bootstrap"],
            expected_status="BOOTSTRAP_COLLECTED_DIAGNOSTIC_NOT_RELEASED",
        )


@pytest.mark.parametrize(
    "change", ["B", "capacity", "limit", "scope", "owner", "source", "expiry"]
)
def test_closed_successor_and_real_owner_gates(environment, change):
    e = environment
    v = deepcopy(e.value)
    if change == "B":
        v["B"] = "ENABLED"
    elif change == "capacity":
        v["a_capacity"] = "f" * 64
    elif change == "limit":
        v["limits"]["non_B_bytes"] += 1
    elif change == "scope":
        v["scope"] = a.s.SCOPE
    elif change == "owner":
        v["owner_sha256"] = "c" * 64
    elif change == "source":
        v["source_files"][0]["sha256"] = "f" * 64
    else:
        v["valid_until"] = v["valid_from"]
    with pytest.raises((a.s.AllocationError, OSError)):
        a.ready(v, a.s.Records(e.records), NOW, probe=e.probe)


@pytest.mark.parametrize(
    "field,value",
    [
        ("f_favail", 0),
        ("f_favail", 2**64 - 1),
        ("f_files", 2**64 - 1),
        ("f_bavail", 0),
        ("f_frsize", 0),
        ("f_flag", 1),
    ],
)
def test_unusable_accounting_cannot_start(environment, field, value, monkeypatch):
    e = environment
    c = e.probe(e.parent)["statvfs"]
    c[field] = value
    monkeypatch.setattr(os, "fstatvfs", lambda fd: SimpleNamespace(**c))
    monkeypatch.setattr(a, "mount_type", lambda path: "panfs")
    with pytest.raises(a.s.AllocationError):
        a.filesystem_probe(e.parent)


def test_positive_accounting_explicitly_shared_not_entitled(environment, monkeypatch):
    e = environment
    c = e.probe(e.parent)["statvfs"]
    monkeypatch.setattr(os, "fstatvfs", lambda fd: SimpleNamespace(**c))
    monkeypatch.setattr(a, "mount_type", lambda path: "panfs")
    row = a.filesystem_probe(e.parent)
    a.validate_storage_observation(row)
    assert row["group_quota_and_reservation"] == "UNKNOWN_NOT_ASSUMED"


def test_changed_parent_during_collection_stops(environment):
    e = environment
    calls = 0

    def changed(path):
        nonlocal calls
        calls += 1
        r = e.probe(path)
        if calls >= 2:
            r["parent_identity"][1] += 1
        return r

    with pytest.raises(a.s.AllocationError, match="PARENT_CHANGED"):
        a.collect(
            e.value,
            e.selection,
            e.token,
            kernel_reader=kernel,
            inventory_reader=lambda *x, **kw: {},
            probe=changed,
            thread_reader=lambda: 1,
            install_guard=False,
        )
    assert not Path(e.value["paths"]["bootstrap"], "manifest.json").exists()


def test_parent_replacement_before_finalize_rejected(environment):
    e = environment
    collect(e)
    make_review(e)

    def changed(path):
        r = e.probe(path)
        r["parent_identity"][1] += 1
        return r

    with pytest.raises(a.s.AllocationError, match="PARENT_CHANGED"):
        a.finalize(
            e.value,
            e.selection,
            e.token,
            thread_reader=lambda: 1,
            probe=changed,
            install_guard=False,
        )
    assert not Path(e.value["paths"]["final"]).exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(M2="QUALIFIED"),
        lambda r: r.update(capacity_assurance="RESERVED"),
        lambda r: r.update(unsupported=True),
    ],
)
def test_recomputed_final_cannot_promote_assurance(environment, mutate):
    e = environment
    complete(e)
    rewrite_original(e.value["paths"]["final"], "result.json", mutate)
    with pytest.raises(a.s.AllocationError):
        a.open_completed(e.value, e.token, probe=e.probe)


def test_changed_original_rejected(environment):
    e = environment
    complete(e)
    Path(e.value["paths"]["bootstrap"], "kernel.json").write_bytes(b"changed")
    with pytest.raises(a.s.AllocationError):
        a.open_completed(e.value, e.token, probe=e.probe)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(completed_centiseconds="secret"),
        lambda r: r.update(collector_exit=2),
        lambda r: r.update(completed_centiseconds=99999),
        lambda r: r.update(completed_centiseconds=112010),
        lambda r: r.update(epoch_centiseconds=True),
    ],
)
def test_invalid_collector_receipt_rejected(environment, mutate):
    e = environment
    collect(e)
    ack, r = make_review(e)
    mutate(ack)
    r["collector_ack_sha256"] = write(Path(e.value["paths"]["collector_ack"]), ack)
    write(Path(e.value["paths"]["review"]), r)
    with pytest.raises(a.s.AllocationError):
        a.verify_review(e.value, e.token)


def test_missing_review_late_acceptance(environment):
    e = environment
    collect(e)
    with pytest.raises(OSError):
        a.verify_review(e.value, e.token)
    make_review(e)
    with pytest.raises(a.s.AllocationError, match="REVIEW_DEADLINE"):
        a.verify_review(e.value, e.token, acceptance_centiseconds=160100)


def test_partial_write_uncertainty_keeps_charge(tmp_path, monkeypatch):
    root = private(tmp_path / "private") / "out"
    w = a.MetadataWriter(lambda: None, guard_seconds=0.01)
    b = w.call(
        lambda: a.GuardedBudget(
            root,
            max_bytes=6,
            max_creations=4,
            deadline=time.monotonic_ns() + 10**9,
            check=w.health,
        )
    )
    original = os.write

    def slow(fd, data):
        n = original(fd, data[:1])
        time.sleep(0.06)
        return n

    monkeypatch.setattr(os, "write", slow)
    with pytest.raises(TimeoutError):
        w.call(lambda: b.write_raw("partial", b"abcdef"))
    time.sleep(0.09)
    w.abandon()
    w.thread.join(1)
    assert (
        (root / "partial").read_bytes() == b"a"
        and b.bytes == 6
        and not (root / "manifest.json").exists()
    )
    with pytest.raises(a.s.AllocationError):
        w.call(lambda: b.close(a.COLLECTED))


def test_enospc_no_refund_or_seal(tmp_path, monkeypatch):
    root = private(tmp_path / "private") / "out"
    b = a.GuardedBudget(
        root, max_bytes=8, max_creations=8, deadline=time.monotonic_ns() + 10**9
    )

    def full(fd, data):
        raise OSError(errno.ENOSPC, "do not log arbitrary text")

    monkeypatch.setattr(os, "write", full)
    with pytest.raises(OSError):
        b.write_raw("partial", b"1234")
    assert b.bytes == 4 and b.creations == 2 and b.poisoned
    with pytest.raises(a.s.AllocationError):
        b.close(a.COLLECTED)


def test_global_expiry_before_output(environment, monkeypatch):
    e = environment
    monkeypatch.setattr(
        a, "global_deadline", lambda: a.need(False, "A2_GLOBAL_DEADLINE")
    )
    with pytest.raises(a.s.AllocationError, match="GLOBAL_DEADLINE"):
        collect(e)
    assert not Path(e.value["paths"]["bootstrap"]).exists()


def test_secret_errno_omitted(environment, monkeypatch, capsys):
    e = environment
    monkeypatch.setattr(a, "load_selection", lambda *x: e.value)
    monkeypatch.setattr(a, "ROOT", Path(e.value["paths"]["source"]))
    for key, name in {
        "source": "STAGE12_AP2_SOURCE",
        "bootstrap": "STAGE12_AP2_BOOTSTRAP",
        "records": "STAGE12_A2_RECORDS",
        "final": "STAGE12_A2_FINAL",
        "outcome": "STAGE12_AP2_OUTCOME",
    }.items():
        monkeypatch.setenv(name, e.value["paths"][key])

    monkeypatch.setenv("STAGE12_AP2_SOURCE_SHA", e.value["source_sha"])
    monkeypatch.setenv("STAGE12_AP2_SELECTION", str(e.selection))
    monkeypatch.setenv("STAGE12_AP2_SELECTION_SHA256", e.token)

    def bad(*x, **kw):
        raise OSError("SECRET_CANARY", "unsafe")

    monkeypatch.setattr(a, "collect", bad)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "a2",
            "collect",
            "--selection",
            str(e.selection),
            "--selection-sha256",
            e.token,
        ],
    )
    assert a.main() == 2
    out = capsys.readouterr().err
    assert "SECRET_CANARY" not in out and json.loads(out)["errno"] is None


def test_real_installed_audit_and_guarded_writer(tmp_path):
    parent = private(tmp_path / "private")
    records = private(parent / "records")
    selection = parent / "input.json"
    write(selection, {})
    code = f"""
import importlib.util,pathlib,sys,time
sys.path.insert(0,{str(ROOT / "src")!r})
spec=importlib.util.spec_from_file_location('a2guard',{str(ROOT / "scripts/stage12_wf_ap2_bootstrap_a2.py")!r});m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
root=pathlib.Path({str(parent / "out")!r})
m.s.collection_guard(pathlib.Path({str(ROOT)!r}),root,pathlib.Path({str(records)!r}),pathlib.Path({str(selection)!r}))
w=m.MetadataWriter(lambda:None);b=w.call(lambda:m.GuardedBudget(root,max_bytes=4096,max_creations=8,deadline=time.monotonic_ns()+10**9,check=w.health));w.call(lambda:b.write('original.json',{{'test_only':True}}));w.call(lambda:b.close(m.COLLECTED));m.s.verify_stage(root);w.close()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
        env={
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "name,mutate",
    [
        ("facts.json", lambda r: r.update(M2="QUALIFIED")),
        ("facts.json", lambda r: r.update(capacity_assurance="VERIFIED_RESERVED")),
        ("storage_after.json", lambda r: r.update(meaning="ATTRIBUTABLE_ENTITLEMENT")),
        ("storage_after.json", lambda r: r.update(reported_shared_available_bytes=0)),
    ],
)
def test_self_consistent_rewritten_A_claims_reject(environment, name, mutate):
    e = environment
    collect(e)
    rewrite_original(e.value["paths"]["bootstrap"], name, mutate)
    with pytest.raises(a.s.AllocationError):
        a.verify_bootstrap(e.value["paths"]["bootstrap"], e.value, e.token)


def test_surplus_directory_and_changed_budget_counters_reject(environment):
    e = environment
    collect(e)
    root = Path(e.value["paths"]["bootstrap"])
    m = a.s.parse((root / "manifest.json").read_bytes())
    m["charged_creations_before_manifest"] += 1
    write(root / "manifest.json", m)
    with pytest.raises(a.s.AllocationError, match="ACCOUNTING_CHANGED"):
        a.verify_bootstrap(root, e.value, e.token)


def test_missing_final_closure_and_expired_opener_reject(environment):
    e = environment
    complete(e)

    def expired():
        a.need(False, "A2_GLOBAL_DEADLINE")

    with pytest.raises(a.s.AllocationError, match="GLOBAL_DEADLINE"):
        a.open_completed(e.value, e.token, probe=e.probe, check=expired)
    Path(e.value["paths"]["final"], "manifest.json").unlink()
    with pytest.raises(OSError):
        a.open_completed(e.value, e.token, probe=e.probe)


@pytest.mark.parametrize(
    "field",
    [
        "STAGE12_AP2_SOURCE",
        "STAGE12_AP2_SOURCE_SHA",
        "STAGE12_AP2_SELECTION",
        "STAGE12_AP2_SELECTION_SHA256",
        "STAGE12_AP2_BOOTSTRAP",
        "STAGE12_A2_RECORDS",
        "STAGE12_A2_FINAL",
        "STAGE12_AP2_OUTCOME",
    ],
)
def test_environment_mismatch_rejects_before_output(environment, monkeypatch, field):
    e = environment
    monkeypatch.setattr(a, "ROOT", Path(e.value["paths"]["source"]))
    for key, name in {
        "source": "STAGE12_AP2_SOURCE",
        "bootstrap": "STAGE12_AP2_BOOTSTRAP",
        "records": "STAGE12_A2_RECORDS",
        "final": "STAGE12_A2_FINAL",
        "outcome": "STAGE12_AP2_OUTCOME",
    }.items():
        monkeypatch.setenv(name, e.value["paths"][key])
    monkeypatch.setenv("STAGE12_AP2_SOURCE_SHA", e.value["source_sha"])
    monkeypatch.setenv("STAGE12_AP2_SELECTION", str(e.selection))
    monkeypatch.setenv("STAGE12_AP2_SELECTION_SHA256", e.token)
    monkeypatch.setenv(field, "WRONG_SCOPE")
    with pytest.raises(a.s.AllocationError):
        a.validate_environment(e.value, e.selection, e.token)
    assert not Path(e.value["paths"]["bootstrap"]).exists()


def test_phase_deadline_boundary_and_fixed_aggregate(environment):
    e = environment
    t = [0]
    check, _, _ = a.phase_checks(
        e.value, 0, 120, clock=lambda: t[0], thread_reader=lambda: 1
    )
    t[0] = 120 * 10**9 - 1
    check()
    t[0] += 1
    with pytest.raises(a.s.AllocationError, match="PHASE_DEADLINE"):
        check()
    limits = a.POLICY["limits"]
    assert (
        sum(r["bytes"] for r in limits["stages"].values()) + limits["logs_bytes"]
        == 240 * 2**20
    )
    assert (
        sum(r["creations"] for r in limits["stages"].values())
        + limits["logs_creations"]
        == 1544
    )


def test_no_B_entrypoint_and_original_epoch_before_external_chain():
    text = (ROOT / "cluster/goethe_nhr/stage12_wf_ap2_bootstrap_a2.sbatch").read_text()
    assert (
        "stage12_diverse_offline_diagnostic.py" not in text and "--wf-ap2" not in text
    )
    assert text.index("export STAGE12_EPOCH_START=") < text.index("exec timeout")
    assert "stage12_a2_run 120" in text and "stage12_run 7200" not in text
    assert "storage_observations" in text and "5s bash -c" in text


@pytest.mark.parametrize("scenario", ["allowed", "symlink", "nonprivate", "replacement", "root_replacement", "unbound", "sync_failure", "trap_failure"])
def test_shell_logwrite_private_binding(tmp_path, scenario):
    """Real bash helper; Darwin uses labelled GNU stat/sync API adapters only."""
    import platform
    import shlex

    base = private(tmp_path.resolve() / "shell")
    records = private(base / "records")
    bindir = private(tmp_path.resolve() / "bin")
    environment = dict(os.environ)
    environment["PATH"] = str(bindir) + os.pathsep + environment["PATH"]
    if platform.system() == "Darwin":
        (bindir / "stat").write_text('#!/bin/bash\nexec /usr/bin/stat -f "%u:%Lp:%d:%i" "$4"\n')
        (bindir / "stat").chmod(0o700)
        (bindir / "realpath").write_text('#!/bin/bash\n[[ -e "$3" ]] || exit 2\nexec /bin/realpath "$3"\n')
        (bindir / "realpath").chmod(0o700)
        sync_command = "/bin/sync"
    else:
        sync_command = "/usr/bin/sync -f \"$2\""
    (bindir / "sync").write_text('#!/bin/bash\n[[ "${A2_TEST_SYNC_FAILURE:-0}" != 1 ]] || exit 74\nexec ' + sync_command + '\n')
    (bindir / "sync").chmod(0o700)
    q = shlex.quote
    script = 'source ' + q(str(ROOT / 'cluster/goethe_nhr/stage12_wf_ap2_bootstrap_a2.sbatch')) + '\n'
    script += 'stage12_check() { return 0; }\nSTAGE12_UTILITIES=0\n'
    script += 'STAGE12_A2_PARENT=' + q(str(base)) + '\nSTAGE12_A2_RECORDS=' + q(str(records)) + '\n'
    if scenario != "unbound":
        script += 'stage12_a2_bind_log_parents\n'
    if scenario == "symlink":
        script += 'mv "$STAGE12_A2_RECORDS" "${STAGE12_A2_RECORDS}_old"\nln -s "${STAGE12_A2_RECORDS}_old" "$STAGE12_A2_RECORDS"\n'
    elif scenario == "nonprivate":
        script += 'chmod 755 "$STAGE12_A2_RECORDS"\n'
    elif scenario == "replacement":
        script += 'mv "$STAGE12_A2_RECORDS" "${STAGE12_A2_RECORDS}_old"\nmkdir -m 700 "$STAGE12_A2_RECORDS"\n'
    elif scenario == "root_replacement":
        script += 'mv "$STAGE12_A2_PARENT" "${STAGE12_A2_PARENT}_old"\nmkdir -m 700 "$STAGE12_A2_PARENT"\nmkdir -m 700 "$STAGE12_A2_RECORDS"\n'
    if scenario in ("sync_failure", "trap_failure"):
        script += 'export A2_TEST_SYNC_FAILURE=1\n'
    if scenario == "trap_failure":
        script += 'STAGE12_AP2_OUTCOME="$STAGE12_A2_PARENT/outcome.json"\nSTAGE12_STATUS=INCOMPLETE\nSTAGE12_START=1\nSTAGE12_NOW=2\nstage12_tick() { return 0; }\ntrap stage12_a2_record EXIT\nexit 19\n'
    else:
        script += 'set +e\nstage12_a2_logwrite "$STAGE12_A2_RECORDS/probe.json" "{}"\nstatus=$?\nprintf "status=%d utilities=%d\\n" "$status" "$STAGE12_UTILITIES"\nexit "$status"\n'
    result = subprocess.run(["bash", "-c", script], env=environment, capture_output=True, text=True, timeout=15)
    if scenario == "allowed":
        assert result.returncode == 0, result.stderr
        assert (records / "probe.json").read_bytes() == b"{}\n"
        assert "utilities=22" in result.stdout  # four binding +18 action calls
    else:
        assert result.returncode != 0
        if scenario not in ("sync_failure", "trap_failure"):
            assert not (records / "probe.json").exists()
        if scenario == "trap_failure":
            assert result.returncode == 19  # primary survives failed cleanup
            assert "A2_SUPERVISOR_TERMINAL exit=19" in result.stdout

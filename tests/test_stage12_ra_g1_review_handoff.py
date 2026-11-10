"""Synthetic sealed release plans; local publication never earns native acceptance.

The literal ISSUED/PASS enums exercise real diagnostic schemas. No actual job,
owner grant, kernel fact, independent release or service authority is created.
Shell tests require a separately precharged opt-in and use explicit Mac shims.
"""

from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest

from test_stage12_public_operations_v2 import offline  # noqa: F401
from test_stage12_ra_g1_production_binding import production, private_source  # noqa: F401
from test_stage12_ra_g1_rep_admin_budget import upgrade
from safe_geocoding_pipeline.preprocessing.stages import s12_ra_g1_execution as execution

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_handoff", ROOT / "scripts/stage12_ra_g1_review_handoff.py")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture(autouse=True)
def narrow_process_guard():
    """Deny network/provider/protected access; fund only the exact planned Bash."""
    state = dict(active=True, allowed=None, remaining=0)

    def audit(event, args):
        if not state["active"]:
            return
        if event == "os.posix_spawn":
            expected = state["allowed"]
            if expected is None or state["remaining"] <= 0 or args != expected:
                raise RuntimeError("HANDOFF_TEST_UNPLANNED_PROCESS_DENIED")
            state["remaining"] -= 1
        elif event.startswith(("socket.", "subprocess.", "os.exec", "os.spawn")) or event in (
            "os.system", "os.fork", "os.forkpty", "pty.spawn",
        ):
            raise RuntimeError("HANDOFF_TEST_NETWORK_OR_PROCESS_DENIED")
        elif event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.fsdecode(args[0]).lower()
            if any(part in path for part in ("/holdout/", "/panfs/", "/.ssh/", "pelias_api_key", "/derived/controlled/")):
                raise RuntimeError("HANDOFF_TEST_PROTECTED_OR_PROVIDER_DENIED")

    sys.addaudithook(audit)
    try:
        yield state
    finally:
        state["active"] = False


def put(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


@pytest.fixture
def handoff(production):  # noqa: F811 - reuse the imported pytest fixture by its name
    case = production
    case.allocation = upgrade(case.allocation)
    _, objects = case.preparer.build(case.allocation, case.bootstrap, **case.kwargs)
    resource = objects["resource_selection"]
    resource_sha = case.controller.digest(resource)
    case.allocation["resource_selection_sha256"] = resource_sha
    uid = os.geteuid()
    context = dict(
        schema_version=execution.SUPERVISOR_CONTEXT, scope=case.controller.SCOPE,
        run_nonce=case.allocation["intent_id"], source_git_sha=case.allocation["source_sha"],
        selection_sha256=resource_sha, adoption_sha256=resource["adoption_sha256"],
        slurm_job_id=777, boot_id="1" * 32, created_mono_ns=10, worker_uid=uid,
        cgroup_namespace_inode=1, mount_namespace_inode=2,
        visible_cgroup_path="/sys/fs/cgroup/SYNTHETIC_NOT_AN_ACTUAL_JOB",
        supervisor=dict(pid=111, start_ticks=1, uid=uid), timeout=None,
        private_paths=dict(allocation_root=str(case.root),
                           resource_evidence_root=case.allocation["paths"]["output"],
                           scratch_root=str(case.root)), protected_paths=None,
    )
    execution.validate_supervisor_context(context)
    case.bootstrap["resource_execution"]["supervisor_context_sha256"] = case.controller.digest(context)
    data, objects = case.preparer.build(case.allocation, case.bootstrap, **case.kwargs)
    # Exercise the complete production metadata grammar with explicit synthetic
    # enums, then use the real input-scope projection to preserve its acyclic DAG.
    data["selection"]["status"] = "ISSUED"
    objects["diagnostic_selection"]["input_scope_sha256"] = case.diagnostic.input_scope(data)
    data["selection"]["authority_sha256"] = case.controller.digest(objects["diagnostic_selection"])
    case.diagnostic.validate_envelope(data, case.allocation["source_sha"], for_execution=True)
    case.diagnostic.validate_workloads(data)
    factual = dict(disposition="PASS", origin="SYNTHETIC_NOT_INDEPENDENT_AUTHORITY",
                   source_sha=case.allocation["source_sha"], selection_sha256=case.controller.digest(case.allocation))
    native_start = 10**18  # Deliberately incomparable with the reviewer's local clock.
    phase = dict(
        schema_version=execution.ADMIN_BINDING, scope=case.controller.SCOPE,
        method="LOGICAL_LIMITS_AND_SCOPED_MONITORING", role="BINDER", phase_id=8,
        source_git_sha=case.allocation["source_sha"], selection_sha256=resource_sha,
        adoption_sha256=resource["adoption_sha256"], supervisor_context_sha256=case.controller.digest(context),
        risk_inventory_sha256="1" * 64, process_pid=222, process_start_ticks=1, process_uid=uid,
        scope_start_mono_ns=native_start, deadline_mono_ns=native_start + 240_000_000_000,
        service_authority="DENIED", protected_input_authority="DENIED", ap_dispatch_authority="DENIED",
    )
    originals = {key: case.controller.canonical(value) for key, value in dict(
        input=data, review_binding=objects["integration_review"], factual_review=factual,
        context=context, resource_selection=resource, phase8_binding=phase,
    ).items()}
    release = case.controller.canonical(dict(
        schema_version=helper.RELEASE, disposition="PASS",
        selection_sha256=case.controller.digest(case.allocation), source_sha=case.allocation["source_sha"],
        input_sha256=helper.sha(originals["input"]), review_binding_sha256=helper.sha(originals["review_binding"]),
        bootstrap_review_sha256=helper.sha(originals["factual_review"]), resource_selection_sha256=resource_sha,
    ))
    kwargs = dict(selection_sha256=case.controller.digest(case.allocation), source_sha=case.allocation["source_sha"],
                  job_id="777", reviewer_release_sha256=helper.sha(release),
                  observed_utc="2026-01-01T00:00:01.000000Z", slurm_state="RUNNING",
                  local_factual_command_start_ns=100, local_observed_ns=100 + 170_000_000_000)
    case.selection_raw = case.controller.canonical(case.allocation)
    case.release, case.originals, case.plan_kwargs, case.objects = release, originals, kwargs, objects
    case.plan = lambda **changes: helper.publication_plan(
        case.selection_raw, case.release, case.originals, **{**case.plan_kwargs, **changes})
    case.root.mkdir(mode=0o700)
    paths = dict(
        input=case.allocation["paths"]["input"],
        review_binding=case.allocation["paths"]["binding"] + "/integration_review.binding.json",
        factual_review=case.allocation["paths"]["review"], context=case.allocation["paths"]["context"],
        resource_selection=case.allocation["paths"]["binding"] + "/resource_evidence/" + resource_sha + ".record",
        phase8_binding=str(case.root / "binder_resources/admin_binding.record"),
    )
    for key, path in paths.items():
        put(path, originals[key])
    for path in case.root.rglob("*"):
        if path.is_dir():
            path.chmod(0o700)
    return case


def test_real_production_plan_preserves_sealed_bytes_and_native_anchors(handoff):
    bundle = Path(handoff.allocation["paths"]["binding"])
    for name, value in handoff.objects["role_records"].items():
        put(bundle / (name + ".record"), handoff.controller.canonical(value))
    for name in ("diagnostic_selection", "diagnostic_resources"):
        put(bundle / (name + ".record"), handoff.controller.canonical(handoff.objects[name]))
    handoff.diagnostic.validate_grants(handoff.controller.parse(handoff.originals["input"]), bundle)
    plan = handoff.plan()
    assert plan["raw_sha256"] == helper.sha(handoff.release)
    assert plan["max_external_units"] == sum(plan["components"].values()) == 11
    assert plan["creation_attempts_precharged"] == 3
    assert plan["logical_write_bytes_precharged"] == len(handoff.release) + plan["possible_heredoc_storage"]["bytes"]
    assert plan["original_binder_start_ns"] == 10**18
    assert plan["original_binder_deadline_ns"] == 10**18 + 240_000_000_000
    assert plan["operational_target_native_anchor_ns"] == 10**18 + 180_000_000_000
    assert plan["target_status"] == "LOCAL_ESTIMATE_WITHIN_180S"
    assert "/proc/uptime" not in plan["command"]
    assert plan["destination"] == handoff.allocation["paths"]["release"]
    assert "test ! -e " in plan["command"] and "--no-clobber --no-target-directory" in plan["command"]
    assert helper.validate_publication_result(plan, returncode=0, stdout=plan["expected_stdout_utf8"].encode())[
        "native_acceptance"] == "NOT_OBSERVED"
    fetch = helper.preparation_plan(handoff.selection_raw, **{
        key: handoff.plan_kwargs[key] for key in ("selection_sha256", "source_sha", "job_id")})
    assert fetch["max_external_units"] == 5
    assert "binder_resources/admin_binding.record" in fetch["expected_relative_roots"]
    assert "PUBLISH" not in fetch["operation"]


@pytest.mark.parametrize("binding", ["input_path", "factual_source", "phase_id"])
def test_resealed_cross_allocation_metadata_still_refuses(handoff, binding):
    case = handoff
    key = {"input_path": "input", "factual_source": "factual_review", "phase_id": "phase8_binding"}[binding]
    value = case.controller.parse(case.originals[key])
    if binding == "input_path":
        value["configuration"]["command_paths"]["evidence_bundle"] += ".foreign"
        review = case.controller.parse(case.originals["review_binding"])
        review["configuration_sha256"] = case.controller.digest(value["configuration"])
        case.originals["review_binding"] = case.controller.canonical(review)
    elif binding == "factual_source":
        value["source_sha"] = "3" * 40
    else:
        value["phase_id"] = 7
    case.originals[key] = case.controller.canonical(value)
    release = case.controller.parse(case.release)
    for name, field in (("input", "input_sha256"), ("review_binding", "review_binding_sha256"),
                        ("factual_review", "bootstrap_review_sha256")):
        release[field] = helper.sha(case.originals[name])
    case.release = case.controller.canonical(release)
    case.plan_kwargs["reviewer_release_sha256"] = helper.sha(case.release)
    with pytest.raises(RuntimeError):
        case.plan()


@pytest.mark.parametrize("name", sorted(helper.ORIGINAL_NAMES))
def test_wrong_same_allocation_original_is_refused(handoff, name):
    handoff.originals[name] += b" "
    with pytest.raises(RuntimeError):
        handoff.plan()


@pytest.mark.parametrize("change", ["source", "path", "factual", "phase", "sealed", "typed", "schema"])
def test_wrong_binding_or_sealed_release_is_refused(handoff, change):
    case = handoff
    if change in ("source", "path"):
        allocation = deepcopy(case.allocation)
        if change == "source":
            allocation["source_sha"] = "3" * 40
        else:
            allocation["paths"]["evidence"] = allocation["paths"]["binding"]
        case.selection_raw = case.controller.canonical(allocation)
        case.plan_kwargs["selection_sha256"] = helper.sha(case.selection_raw)
    elif change in ("factual", "phase"):
        key = "factual_review" if change == "factual" else "phase8_binding"
        value = case.controller.parse(case.originals[key])
        value["selection_sha256"] = "3" * 64
        case.originals[key] = case.controller.canonical(value)
    elif change == "sealed":
        case.release += b" "
    else:
        value = case.controller.parse(case.release)
        value["disposition" if change == "typed" else "schema_version"] = True
        case.release = case.controller.canonical(value)
        case.plan_kwargs["reviewer_release_sha256"] = helper.sha(case.release)
    with pytest.raises((RuntimeError, ValueError)):
        case.plan()


def test_terminated_native_scope_and_readback_uncertainty_refuse_without_clock_reset(handoff):
    for state in ("COMPLETED", "CANCELLED", "FAILED", "PENDING", "RUNNING\nRUNNING"):
        with pytest.raises(RuntimeError, match="RA_G1_HANDOFF_INELIGIBLE"):
            handoff.plan(slurm_state=state)
    for path in helper.refusal_paths(handoff.allocation):
        with pytest.raises(RuntimeError, match="RA_G1_HANDOFF_INELIGIBLE"):
            handoff.plan(existing_paths=[path])
    late = handoff.plan(local_observed_ns=100 + 300_000_000_000)
    assert late["target_status"] == "LOCAL_ESTIMATE_EXCEEDS_180S_NATIVE_ELIGIBILITY_UNKNOWN"
    assert late["original_binder_start_ns"] == 10**18
    assert late["current_native_elapsed"] == "NOT_OBSERVED_NO_CROSS_HOST_CLOCK_COMPARISON"
    for code, stdout in ((1, late["expected_stdout_utf8"].encode()), (0, b"wrong\n")):
        with pytest.raises(RuntimeError, match="RA_G1_HANDOFF_PUBLICATION_UNCERTAIN"):
            helper.validate_publication_result(late, returncode=code, stdout=stdout)


# Each executable is one Python process via an absolute shebang; timeout creates
# exactly one sync child. No env, shell, network or helper processes are hidden.
MAC_SHIM = r'''import ctypes,hashlib,json,os,signal,sys,time
from pathlib import Path
name=Path(sys.argv[0]).name
a=sys.argv[1:]
def audit(event,args):
    if event=='os.posix_spawn':
        expected=str(Path(sys.argv[0]).parent/'sync')
        allowed=json.loads(os.environ['HANDOFF_ALLOWED_SYNC_PATHS'])
        if not (name=='timeout' and args[0]==expected and args[1] in [[expected,'-f',p] for p in allowed]
                and hashlib.sha256(Path(expected).read_bytes()).hexdigest()==os.environ['HANDOFF_EXPECTED_SHIM_SHA']):
            raise RuntimeError('HANDOFF_SHIM_UNPLANNED_PROCESS_DENIED')
    elif event.startswith(('socket.','subprocess.','os.exec','os.spawn')) or event in ('os.system','os.fork','os.forkpty'):
        raise RuntimeError('HANDOFF_SHIM_NETWORK_OR_PROCESS_DENIED')
    elif event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
        p=os.fsdecode(args[0]).lower()
        if any(x in p for x in ('/holdout/','/panfs/','/.ssh/','pelias_api_key','/derived/controlled/')):
            raise RuntimeError('HANDOFF_SHIM_PROTECTED_OR_PROVIDER_DENIED')
sys.addaudithook(audit)
if name=='squeue':
    assert a==['-h','-j','777','-o','%i|%T']
    print('777|'+os.environ.get('HANDOFF_TEST_STATE','RUNNING'))
elif name=='sha256sum':
    def digest(p):
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
        try:
            h=hashlib.sha256()
            while True:
                b=os.read(fd,4096)
                if not b: return h.hexdigest()
                h.update(b)
        finally: os.close(fd)
    if a==['--check','--status']:
        for line in sys.stdin:
            d,p=line.rstrip('\n').split('  ',1)
            if digest(p)!=d: sys.exit(1)
    else:
        assert len(a)==2 and a[0]=='--'
        print(digest(a[1])+'  '+a[1])
elif name=='sync':
    assert len(a)==2 and a[0]=='-f'
    fd=os.open(a[1],os.O_RDONLY|os.O_NOFOLLOW)
    try: os.fsync(fd)
    finally: os.close(fd)
    if os.environ.get('HANDOFF_TEST_FAIL_SYNC')=='1' and Path(a[1]).is_file(): sys.exit(74)
elif name=='timeout':
    assert a[:3]==['--signal=TERM','--kill-after=1s','5s'] and a[3]=='sync'
    path=str(Path(sys.argv[0]).parent/'sync')
    pid=os.posix_spawn(path,[path]+a[4:],dict(os.environ)); end=time.monotonic()+5
    while True:
        child,status=os.waitpid(pid,os.WNOHANG)
        if child: sys.exit(os.waitstatus_to_exitcode(status))
        if time.monotonic()>=end:
            os.kill(pid,signal.SIGTERM); time.sleep(.05)
            child,status=os.waitpid(pid,os.WNOHANG)
            if not child: os.kill(pid,signal.SIGKILL); os.waitpid(pid,0)
            sys.exit(124)
        time.sleep(.005)
elif name=='mv':
    assert len(a)==5 and a[:3]==['--no-clobber','--no-target-directory','--']
    assert sys.platform=='darwin'
    libc=ctypes.CDLL(None,use_errno=True)
    rename=libc.renamex_np; rename.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_uint]
    # Local SDK sys/stdio.h: RENAME_EXCL = 0x00000004. Actual exclusive rename.
    if rename(os.fsencode(a[3]),os.fsencode(a[4]),4): sys.exit(74)
else: sys.exit(75)
'''


@pytest.mark.skipif(os.environ.get("STAGE12_HANDOFF_SHELL_TESTS") != "PRECHARGED_OFFLINE_ONLY"
                    or sys.platform != "darwin", reason="requires exact external-process precharge; Mac test shims")
@pytest.mark.parametrize("scenario", ["success_noclobber", "partial_sync", "terminated"])
def test_actual_selected_shell_publication_with_explicit_mac_shims(handoff, tmp_path, scenario, narrow_process_guard):
    """Maximum20 external units across all three cases, plus caller if newly launched."""
    plan = handoff.plan()
    shims = tmp_path / "shims"
    shims.mkdir(mode=0o700)
    shim_raw = ("#!" + sys.executable + " -I\n" + MAC_SHIM).encode()
    for name in ("squeue", "sha256sum", "sync", "timeout", "mv"):
        path = put(shims / name, shim_raw)
        path.chmod(0o700)
    environment = {"PATH": str(shims), "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONNOUSERSITE": "1", "HANDOFF_EXPECTED_SHIM_SHA": hashlib.sha256(shim_raw).hexdigest(),
                   "HANDOFF_ALLOWED_SYNC_PATHS": json.dumps([plan["temporary"], str(Path(plan["destination"]).parent)])}
    if scenario == "partial_sync":
        environment["HANDOFF_TEST_FAIL_SYNC"] = "1"
    if scenario == "terminated":
        environment["HANDOFF_TEST_STATE"] = "COMPLETED"

    def launch(suffix):
        stdout, stderr = tmp_path / (suffix + ".stdout"), tmp_path / (suffix + ".stderr")
        outfd = os.open(stdout, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        errfd = os.open(stderr, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            argv = ["/bin/bash", "-c", plan["command"]]
            assert all(path.read_bytes() == shim_raw and path.stat().st_mode & 0o777 == 0o700
                       and not path.is_symlink() for path in shims.iterdir())
            narrow_process_guard["allowed"] = ("/bin/bash", argv, environment)
            narrow_process_guard["remaining"] = 1
            pid = os.posix_spawn("/bin/bash", argv, environment,
                                 file_actions=[(os.POSIX_SPAWN_DUP2, outfd, 1), (os.POSIX_SPAWN_DUP2, errfd, 2)])
        finally:
            os.close(outfd)
            os.close(errfd)
        _, status = os.waitpid(pid, 0)
        return os.waitstatus_to_exitcode(status), stdout.read_bytes()

    code, stdout = launch("first")
    destination, temporary = Path(plan["destination"]), Path(plan["temporary"])
    if scenario == "success_noclobber":
        helper.validate_publication_result(plan, returncode=code, stdout=stdout)
        assert destination.read_bytes() == handoff.release
        assert destination.stat().st_mode & 0o777 == 0o600 and not temporary.exists()
        assert launch("second")[0] != 0 and destination.read_bytes() == handoff.release
    else:
        assert code != 0 and not destination.exists()
        assert temporary.exists() == (scenario == "partial_sync")
        if temporary.exists():
            assert temporary.read_bytes() == handoff.release and temporary.stat().st_mode & 0o777 == 0o600
